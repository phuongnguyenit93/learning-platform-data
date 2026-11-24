# 21.5. Managing Access to Heap Dumps, JFR, Command Lines, System Properties, and Management Ports

## Objectives

Diagnostic collection is a **privileged operational action**: a heap dump file can contain all business data remaining in memory; a JFR recording can contain stack traces, process info, launch arguments, and configuration details; `jcmd` can read system properties or instruct the JVM to write additional files; JMX/JDWP ports can expose powerful observability and control capabilities.

After this lesson, you will be able to:

1. **Classify sensitivity levels** and access scope for heap dumps, `.jfr` files, command lines, system properties, diagnostic logs, and management endpoints.
2. Design **least privilege, approvals, audit trails, and retention limits** across collection → staging → transfer → analysis → deletion.
3. Explain accurately the risks of `jcmd VM.command_line`, `VM.system_properties`, `GC.heap_dump`, `JFR.dump`, `ps`, `/proc`, `-D...`, and runtime arguments.
4. Distinguish **local attach** from **remote JMX** and **JDWP debugging**; configure security appropriately at the OS, container, network, and account layers.
5. Practice with **Java 17+** to observe how a synthetic system property can appear in JVM arguments and inside the process without using any real passwords or tokens.
6. Build a response checklist for artifact leaks, unexpected open ports, and controls that **are insufficient on their own**.

> **Operational principle:** treat dumps, recordings, and diagnostic tool outputs as **data that may contain secrets**, even when filenames say `debug`, `profile`, or the goal is purely performance tuning. Protect them from request approval, through JVM file creation, transfer, analysis, and final destruction.

## 1. Access Surface Map: Who Can See What?

Before running any tool, identify two things: **what the tool can do** and **what application data could be exposed through that capability**.

| Surface | Accessible Data / Capabilities | Why Control Is Needed |
| --- | --- | --- |
| **Heap dump** (`.hprof`) | Contents of objects/arrays in heap: strings, tokens, caches, requests, customer data, in-memory credentials; object graph and references. | Exposes real live data, potentially including valid secrets; files are large and easily copied. |
| **JFR recording** (`.jfr`) | Runtime events, classes/methods, threads/stacks, file paths, network endpoints; depending on event settings, JVM arguments, environment, and system properties. | Can reveal topology, config details, and sensitive data; never assume "JFR only holds performance metrics." |
| **Command line / JVM flags** | `-D...`, `-X...`, `-XX...`, application args, certificate/config paths, endpoints, and any secrets passed on the command line. | Users/processes allowed to inspect command lines or run diagnostic commands can read the contents. |
| **System properties** | Java properties like `java.home`, `user.home`, paths/configs, endpoints; some apps set credentials via `-D...` or `System.setProperty`. | `VM.system_properties`, MBeans, and in-JVM code can read values; not a secure secret store. |
| **Environment variables** | Endpoints, tokens, or credentials if configured via environment; values may enter JFR events depending on settings. | Environment variables should not be assumed secret from anyone permitted to inspect processes/containers. |
| **Local attach** (`jcmd`, `jmap`, `jstack`, local JConsole) | Inspects rich state, requests recordings/dumps, and includes commands affecting runtime. | Typically operates under the JVM's OS user permissions; not purely "risk-free read-only." |
| **Remote JMX** | Reads MBeans/metrics; depending on role/MBean, can invoke operations or alter configuration. | Network management endpoint; weak configuration exposes data or control. |
| **JDWP debug port** | Breakpoints, thread suspension, field reads, method invocation inside the JVM, state modification via debugger. | Extremely powerful access; unsafe to leave openly reachable on a network. |
| **Logs, tickets, CI artifacts, backups** | Copies or excerpts of any of the above. | Downstream system permissions may be far broader than access to the original JVM. |

Actual sensitivity depends on the application, data, and capture timing, yet **by default every artifact must be controlled as restricted-access data**. "I only grabbed JFR," "the file ends in `.txt`," or "the filename doesn't contain `secret`" **is not a classification mechanism**.

### Distinguishing Raw Data From Sanitized Reports

- **Raw HPROF/JFR:** contains rich technical evidence and potentially user data. Only specifically authorized personnel should access it.
- **Raw `VM.system_properties` / command-line output:** may directly contain sensitive values. Never paste verbatim into tickets or chat.
- **Sanitized reports:** aggregate metrics, error groupings, stacks stripped of sensitive data, and duration/count distributions. Suitable for wider team sharing **after review**.
- **Files "anonymized" by renaming:** still raw data; renaming does not scrub payloads.
- **Compressed or encrypted files:** reduce transfer risk when keys/permissions are sound, yet do not turn the file into public data.

## 2. Least-Privilege Model for a Single Collection

Design permissions around actions, not job titles alone. Someone allowed to view dashboards **does not automatically need heap-dump privileges**. Separate roles:

| Role / Action | Recommended Permissions | Boundaries |
| --- | --- | --- |
| **Incident detector** | View sanitized metrics/logs; submit diagnostic requests. | No permission to generate or download raw dumps directly. |
| **Approver** | Validate scope, timing, data sensitivity, recipients, and retention window. | Approvals bind to a specific incident/JVM, never open-ended environment-wide grants. |
| **Authorized collector (SRE/on-call)** | Attach to the target process or run actions via a controlled management plane. | Limited to approved environment, window, and commands; audit-logged. |
| **Analyst** | Read raw files in an isolated environment if required; otherwise read sanitized summaries only. | Needs no remote debugger or JMX access to live production apps. |
| **Result sharer** | Publish reviewed figures and conclusions. | Never send raw files, passwords, tokens, or secret-bearing command lines to broad channels. |
| **Cleanup custodian** | Verify deletion across staging, storage, analyst machines, shares, and retention/backups per policy. | Must track derived copies as well, not just the source file. |

**A well-formed collection request** must state: business justification, system/JVM, environment, PID or exact identity, artifact type, owner, permitted time window, expected impact (pauses, disk, CPU), secure storage path, read permissions, expiration date, and ticket/audit ID. For emergencies, use an approved/audited **break-glass** workflow followed by post-incident review.

**Separate read permissions from control permissions:** a read-only JMX MBean is not equivalent to running diagnostic commands; "permission to view metrics" does not mean "permission to dump the heap." Even read-only management interfaces can still return sensitive information.

## 3. Heap Dumps: Often the Most Sensitive File in an Investigation

An HPROF heap dump snapshots JVM heap objects at capture time. It may contain:

- Credentials, API tokens, and session cookies in `String`, `char[]`, `byte[]`, maps, or other objects (depending on application design).
- In-flight request/response payloads, account records, or cached customer data.
- URLs, hosts, keys, and object graphs revealing internal relationships.
- Data omitted from application logs because log masking hid it.

Nothing guarantees an HPROF file is **automatically redacted**. Even if the application masks passwords when logging, objects holding the original values can still sit in memory at dump time. Also note dumps are often huge and carry **Impact: High**, potentially causing pauses and disk pressure.

### 3.1. Pre-Collection Permission Checks

On Linux, one way to prepare a **pre-approved private directory** is:

```bash
umask 077
install -d -m 0700 /var/lib/app-diag
```

This assumes a host where you are **authorized** to create `/var/lib/app-diag`. Verify directory owner/permissions, quotas, free disk, filesystem encryption, retention, and whether the target JVM can write there. `umask 077` prevents newly created files from inadvertently granting group/other access via shell defaults; **it does not replace ACLs or service policies**.

**Illustrative command** on a lab/approved JVM (PID `12345` is an example):

```bash
jcmd 12345 help GC.heap_dump
jcmd 12345 GC.heap_dump /var/lib/app-diag/incident-20261029.hprof
```

Here the **target JVM** creates the file inside its visible filesystem using the JVM process's permissions. The `jcmd` shell is not writing the file like a `>` shell redirect. Inside a container, `/var/lib/app-diag` inside the JVM container may differ from host paths.

**Never run blindly in production:** weigh GC/pauses, heap size, data sensitivity, and user permissions. `jcmd` documentation notes the command triggers a Full GC by default; `-all` changes object scope and collection behavior yet still carries substantial cost.

### 3.2. Automatic OOME Dumps Also Need Access Governance

HotSpot supports:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/lib/app-diag
```

These are **JVM configuration flags**, not a complete shell script. When triggered, the JVM can write a heap dump without interactive action. Organizations must therefore **pre-approve**: a restricted storage path, adequate capacity, retention, alerts, and handling workflows for new files.

If `HeapDumpPath` is left at default or points to a shared volume or public bucket, a memory exhaustion incident can simultaneously become a **data breach**. Check volume snapshots and backups as well.

### 3.3. Post-Collection Handling

- Verify the file landed in the approved location with the right owner and permissions. Linux example: `stat /var/lib/app-diag/incident-20261029.hprof`; inspect metadata only, **never print contents**.
- Never open the file directly in unapproved browsers, plugins, or external online services.
- When transferring to an analysis workstation, use encrypted transport, strong authentication, access controls, and audit logging; never use public share links.
- The analysis environment must also safeguard temporary files, caches, logs, and heap-analyzer outputs.
- When finished, delete per retention policy and track copies. Deleting from one directory does not guarantee removal from snapshots, backups, or other hosts' logs.

## 4. JFR: Telemetry Is Not Always Benign

JFR captures performance/runtime events. Depending on **JDK, `.jfc`, event settings, and capture timing**, a recording may contain:

- JVM startup information and **command-line arguments**.
- Initial environment variables and **system properties** when corresponding events are enabled.
- Package/class/method names, stack traces, and threads.
- File paths, socket endpoints, host addresses, exception types/messages, or payloads of **custom JFR events**.
- Application-supplied fields; if a developer writes a token into an event field, it enters the recording.

Never assume every `.jfr` contains all of the above—nor may you assume they are absent. Use `jfr summary`/`jfr metadata` in a controlled environment to see which event types were recorded. Oracle explicitly notes that JFR recordings **can contain confidential information** such as command lines and environments.

### 4.1. Scoped JFR Capture

On an authorized JVM:

```bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=incident settings=default
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=incident filename=/var/lib/app-diag/incident-20261029.jfr
jcmd 12345 JFR.stop name=incident
```

`JFR.dump` writes the file on the **target JVM's** filesystem and **the recording continues after dumping** until stopped via `JFR.stop` or another end condition. `settings=default` is a general collection profile; **it is not a guarantee of non-sensitive data**. `settings=profile` captures more, increasing both overhead and information exposure.

Control **both command execution permissions** and **read access to `.jfr` files**. Someone unauthorized to inspect raw recordings should not be handed the file merely because they asked for a flame graph.

### 4.2. Minimizing Captured Data and Published Details

- Enable only events needed for the investigation; disabling `JVM Information`/environment/system-property events via config reduces certain risks, **yet does not guarantee the remaining file is harmless**.
- Never put secrets or PII into **custom event payloads**, exception messages, or debug tags.
- If only CPU/latency evaluation is needed, consider sharing a reviewed **summary report** instead of the raw `.jfr`.
- If the full file is needed, transfer only to approved environments/teams with restricted readership.
- Inspect files after writing and **before sharing**; renaming or compressing is not redaction.

Like heap dumps, recordings can linger in temp directories, containers, CI/artifact stores, or ticket attachments; all such locations belong inside the **data lifecycle**.

## 5. Command Lines and System Properties: Values Leak Through Multiple Paths

### 5.1. Why Passing Secrets via `-D...` Is Risky

Lab-only example, **not a real credential**:

```bash
java -Ddemo.accessToken=LAB_FAKE_VALUE_NOT_A_SECRET DiagnosticExposureDemo
```

Even if the program **never intentionally prints the value**, a JVM can expose arguments/properties through authorized channels:

- `jcmd 12345 VM.command_line`: prints JVM launch command-line flags, potentially including `-Ddemo.accessToken=...`.
- `jcmd 12345 VM.system_properties`: prints active system properties, potentially including `demo.accessToken=...`.
- `ManagementFactory.getRuntimeMXBean().getInputArguments()` or `System.getProperties()`/`System.getProperty(...)` inside app/agent code.
- OS/process-inspection tools such as `ps` and `/proc/<pid>/cmdline` on Linux, subject to **permissions, OS hardening, and namespaces**.
- JFR events for JVM information or system properties, if enabled.

**`-Dpassword=...` cannot serve as a secret store.** Even moving from `-D` to environment variables still requires classification and protection, because same-user, root, container-admin, or runtime instrumentation may read them. Better options include **managed identities, secret managers, credential providers, or least-privilege mounted secret files/volumes**, never printing secrets to logs or command lines.

### 5.2. `jcmd` Surface Areas to Recognize

| Command / Capability | Nature | Handling Guidance |
| --- | --- | --- |
| `jcmd -l` | Lists visible JVMs, often with main class/arguments. | Treat output as restricted metadata; never paste blindly into broad channels. |
| `jcmd 12345 VM.command_line` | Prints JVM command-line arguments. | May expose `-D`/paths; run and store output only in approved environments. |
| `jcmd 12345 VM.system_properties` | Prints active properties. | Easily exposes sensitive values; **never** redirect into tickets or paste publicly. |
| `jcmd 12345 VM.flags` | Shows VM flags. | May reveal configs/paths; classify appropriately. |
| `jcmd 12345 GC.heap_dump ...` | Instructs JVM to write HPROF; high impact. | Require approval for operation and path; prepare storage/resources. |
| `jcmd 12345 JFR.start` / `JFR.dump` | Controls recordings and writes `.jfr`. | Gate collector permissions and protect resulting artifacts. |
| `jcmd 12345 help` | Lists supported commands. | Usually less sensitive, yet still an attach operation; verify permissions. |

These commands are **examples for PID `12345` only**; never run them against a live JVM without authorized scope. In particular, `VM.command_line` and `VM.system_properties` can **print secrets directly to your terminal**, flowing into session recordings, shell redirects, screen shares, or audit logs.

### 5.3. Rules to Prevent Configuration Value Exposure

1. **Never pass tokens/passwords in launch commands** when stronger secret management exists. Avoid keystore/truststore passwords in `-D...` too.
2. Never log all of `System.getProperties()`, runtime arguments, environment variables, or `ProcessHandle.Info.arguments()` inside the app.
3. If you only need to know **whether a setting is present**, log a boolean or allowlisted key name, **never the value**.
4. For config auditing, record only version/profile and keys classified as safe, or apply a reviewed redaction pipeline.
5. Do not treat **a regex replacing `password=`** as complete redaction: secrets hide inside URLs, differently named tokens, objects, messages, and custom fields.
6. Audit copies across logs, crash reports, JFR, CI artifacts, command history, container specs, and dashboards.

## 6. Java 17+ Lab: Observing Presence Without Printing the Value

The example below uses **a synthetic token**, opens no network ports, performs no self-attach from inside the program, and **never prints the property value**. It illustrates how Java system properties differ from JVM input arguments.

Create **`DiagnosticExposureDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.List;

public final class DiagnosticExposureDemo {
    public static void main(String[] args) throws Exception {
        long pid = ProcessHandle.current().pid();

        List<String> inputArguments =
                ManagementFactory.getRuntimeMXBean().getInputArguments();
        boolean argumentPresent = inputArguments.stream()
                .anyMatch(value -> value.startsWith("-Ddemo.accessToken="));
        boolean propertyPresent =
                System.getProperty("demo.accessToken") != null;

        System.out.println("pid=" + pid);
        System.out.println("propertyPresent=" + propertyPresent);
        System.out.println("argumentPresent=" + argumentPresent);
        System.out.println("Only synthetic lab values were used.");
        System.out.println("Press Enter to exit.");
        System.in.read();
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 DiagnosticExposureDemo.java
java -Ddemo.accessToken=LAB_FAKE_VALUE_NOT_A_SECRET DiagnosticExposureDemo
```

Expected output (the process PID depends on your OS):

```text
pid=38448
propertyPresent=true
argumentPresent=true
Only synthetic lab values were used.
Press Enter to exit.
```

The line `pid=38448` **is from one illustrative run**, not a fixed PID. This sample was compiled and verified with `javac --release 17` on JDK 24; the boolean lines and messages match as shown.

### 6.1. Inspecting With `jcmd` on the Lab JVM

While the program **waits at `System.in.read()`**, open a second terminal on the same host with valid permissions. Use **the PID printed by your run**, not the illustrative PID if different.

```bash
jcmd -l
jcmd 38448 VM.command_line
jcmd 38448 VM.system_properties
```

These commands can **print the synthetic token directly to the terminal**, so practice only against the lab process using `LAB_FAKE_VALUE_NOT_A_SECRET`. On real systems, **never run or save full outputs without an approved diagnostic request**.

Once you see the synthetic token appear in one or both outputs, note the lesson: **the fact that an app never prints a token does not prevent someone with attach rights from reading it via JVM startup/configuration**. For a system property added after startup via `System.setProperty`, it can appear in `VM.system_properties` without necessarily appearing in initial input arguments.

Return to the first terminal and press Enter so the JVM exits. Once exited, `jcmd` can no longer attach to that PID.

### 6.2. Additional Cases to Reason About

- If run **without** `-Ddemo.accessToken=...`, `propertyPresent` and `argumentPresent` are normally `false`.
- If the application calls `System.setProperty("demo.accessToken", ...)` **at runtime**, the property can show up in `VM.system_properties`, while `RuntimeMXBean.getInputArguments()` does not reflect post-startup calls.
- If an application argument looks like `--api-token=...`, it is not a JVM system property by default; **it can still leak via command lines or the application**, yet will not appear automatically under key `demo.accessToken` in `System.getProperties()`.
- In containers, the PID seen inside the JVM may differ from the host PID, and `jcmd` may be absent from minimal runtime images. Never relax permissions or namespaces recklessly just to force attach to work.

## 7. Attach API and OS Account Permissions

On HotSpot/JDK, tools like `jcmd` typically rely on the **local attach** mechanism. JDK documentation requires running with matching privileges (normally **the same effective user/group** as the Java process, on the same host and namespace). This relies on **OS user/process boundaries**, not a built-in role system saying "only Java-approved operators may run `jcmd`."

### Practical Controls

- Run services under **dedicated OS accounts**; never share a single UID across workloads of different trust levels.
- Restrict who can `sudo -u`, `kubectl exec`, or spawn shells under the service UID.
- Avoid running containers as `root` or overly privileged; enforce cluster RBAC, disallow unnecessary `hostPID`/privileged containers, and restrict volume permissions.
- Control attach socket/agent paths and filesystem permissions per OS policy; never loosen permissions broadly just to "make tools work."
- Audit who attached to which PID, when, with what command, target, and approval; **never log secret values inside audit outputs**.
- Isolate production, staging, and development. Sharing a UID or host/container across workloads widens blast radius if one workload is compromised.

### `-XX:+DisableAttachMechanism`: Useful, Not a Standalone Defense

HotSpot can be launched with:

```text
-XX:+DisableAttachMechanism
```

This flag disables the standard attach mechanism used by `jcmd`, `jstack`, `jmap`, and `jinfo`; **in exchange, it can remove critical diagnostic options during incidents**. Do not roll it out broadly without testing OOME/hang handling alternatives. It **does not** block memory/config reads by OS root, hypervisors, container hosts, or other enabled management ports.

**Right decision:** treat attach as a capability requiring OS boundaries and approval; if you disable attach, maintain working alternatives (bounded startup JFR, logs, metrics, protected OOME dump paths, and restart/capture procedures).

## 8. JMX Ports: Network Management Endpoints Needing Defense in Depth

**JMX (Java Management Extensions)** lets clients access MBeans. For HotSpot's built-in agent, common properties include:

| Property / Setting | Purpose | What to Control |
| --- | --- | --- |
| `com.sun.management.jmxremote.port` | Opens the remote JMX connector/registry on a specified port. | Enable only when genuinely needed; restrict network ACLs and client identity. |
| `com.sun.management.jmxremote.rmi.port` | Pins the RMI connector port for controlled firewall/NAT traversal. | Inspect **both registry port and connector port**, not just one. |
| `java.rmi.server.hostname` | Sets the host/address advertised in RMI stubs. | Configure for internal networks; avoid advertising public or wrong IPs. |
| `com.sun.management.jmxremote.authenticate` | Enables identity authentication on the remote agent. | Never set `false` in production. |
| `com.sun.management.jmxremote.ssl` | Encrypts the connector channel with TLS/SSL. | Never set `false` over networks; verify certs, truststores, and handshakes. |
| `com.sun.management.jmxremote.registry.ssl` | Protects the RMI registry channel with SSL when properly configured. | Avoid exposed unprotected registries; pair with client authentication. |
| `com.sun.management.jmxremote.ssl.need.client.auth` | Requires TLS client certificates when SSL is enabled. | Maintain issuance, rotation, and revocation plans. |
| `com.sun.management.jmxremote.password.file` | File holding roles/passwords for file-based authentication. | Owner-only read/write; avoid reused passwords. |
| `com.sun.management.jmxremote.access.file` | Maps `readonly`/`readwrite` permissions to roles. | Use **readonly** for monitoring; strictly limit `readwrite` holders. |

**Important:** opening a JMX port does more than "expose metrics." Remote MBeans can disclose config, runtime internals, and (depending on privileges) invoke administrative operations. `readwrite` and custom MBean operations can be dangerous. Even `readonly` can leak sensitive data if exposed by MBeans.

### 8.1. What Does a Responsible JMX Setup Require?

1. **Network-layer protection:** private networks, firewalls/security groups, approved VPN/bastion, never exposed to the Internet. Allow only specific sources.
2. **Working TLS:** valid certificates, truststore/cert rotation, and server verification by clients. Never assume `ssl=true` alone guarantees security.
3. **Authentication and authorization:** individual identities for users/tools, minimal roles; never let everyone who reaches the port become admin.
4. **RMI registry protection:** Oracle warns of unprotected registry risks and recommends `jmxremote.registry.ssl=true` paired with TLS client auth where appropriate; evaluate the full registry and connector path.
5. **Admin accounts and secrets:** traditional file-based password files store plaintext and require strict permissions such as `0600` on Linux. Never place real passwords in shell history, chat, or command arguments.
6. **Auditability:** log who connected, with what role, when, and what actions ran, using infrastructure and JMX audit capabilities.
7. **Test from real network positions:** test from both authorized and unauthorized hosts; verify no bypass exists from other pods or namespaces.

Illustrative access file showing **role separation**:

```properties
monitorRole readonly
operatorRole readwrite
```

This is **not** a complete secure JMX configuration. You still need authentication, certificates/TLS, password/access files, ACLs, and RMI port verification. Never copy an example and open ports in production before completing all protective layers.

### 8.2. Never Disable Security Over the Network

```properties
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
```

These two lines are an **anti-pattern to avoid**, not deployment instructions. Oracle warns such settings can hand network clients powerful control over the JVM. They are shown only so operators know how to **detect and eliminate them**—never test them in shared environments.

**Note:** the local JMX connector for same-host/same-OS-user tools uses an authentication model **distinct** from the remote connector. Never assume enabling TLS on remote JMX restricts local attach via remote JMX passwords/roles.

## 9. JDWP Debug Ports: Different From JMX and Even More Dangerous to Expose

**JDWP** is the debugger wire protocol supporting state inspection, thread suspension, breakpoints, and method evaluation/invocation inside the JVM. It is not a read-only metrics port.

**Lab-only** example:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DiagnosticExposureDemo
```

This assumes `DiagnosticExposureDemo.java` is compiled; it passes no real tokens and binds only **loopback** for local IDE debugging. `127.0.0.1` reduces external network exposure, yet on shared hosts you must still control who can connect to local sockets.

Never use `address=*:5005` or expose the port via Services/NodePorts/uncontrolled port-forwards in production. Anyone reaching JDWP can alter execution, not just read stacks; never treat a lone firewall as a substitute for strict access governance.

If remote debugging is unavoidable: prefer staging; use an authenticated, time-limited, audited tunnel/bastion. When done, close the session and disable the port. **Never assume JDWP itself provides a TLS authentication/authorization model comparable to JMX.**

### Brief Comparison: JMX vs. JDWP

| Attribute | JMX | JDWP |
| --- | --- | --- |
| Primary purpose | Monitor/manage MBeans. | Debug program execution at thread/stack/breakpoint/method level. |
| Permission model | Supports auth, TLS, roles (`readonly`/`readwrite`) depending on agent/config. | Powerful debug control; requires network isolation and strict endpoint control. |
| Exposure risk | Leaks metrics/configs or permits admin operations. | Suspend threads, read/modify state, invoke methods, disrupt service. |
| Recommendation | Enable only when needed with auth + TLS + ACL + audit. | Never enable in production outside tightly governed exception workflows. |

## 10. Host, Container, and Kubernetes: Boundaries Matter More Than Tool Names

In container orchestration, two permission planes are often overlooked:

1. **Inside container/host:** UID, filesystem ACLs, Linux capabilities, mount namespaces, PID namespaces, `privileged`, `hostPID`, `ptrace`, or attach ability.
2. **Control-plane permissions:** who may `exec` into pods, copy files out (`cp`), launch debug/ephemeral containers, inspect volumes/PVCs, upload artifacts to buckets, or read logs/secrets.

For example, if several services share one broad UID on a host, merely "not publishing a JMX port" does not eliminate attach or dump-reading risks. Conversely, an account unable to touch the JVM directly yet permitted to **download dumps from object storage** can still read sensitive data.

### Controls to Verify

- `runAsNonRoot`/per-workload UID isolation, privilege-escalation restrictions, and minimal capabilities.
- RBAC for `exec`, `cp`, `port-forward`, ephemeral debug containers, and node administration.
- Namespace/network policies or firewalls restricting JMX/JDWP—never rely solely on "the service has no Ingress."
- Private diagnostics PVCs/buckets not mounted across unrelated services.
- Disk quotas, encryption at rest, object-level permissions, access logs, and lifecycle retention.
- Never push HPROF/JFR files to CI public artifacts, chat attachments, public issues, or unapproved personal laptops.
- Track container **PID and filesystem views** when using `jcmd`; identical path names do not mean identical host volumes.

Against users holding root/host-admin privileges, many in-JVM controls cannot stop memory or file inspection. You must therefore secure **both hosts and management infrastructure**, not just JVM flags.

## 11. End-to-End Secure Collection and Sharing Workflow

### Phase A — Approval and Preparation

1. State the diagnostic objective: CPU, GC, classloaders, memory leak, hung threads, or latency. **Pick the least sensitive data** capable of answering the question.
2. Check existing sources such as metrics/logs/aggregated JFR. Never create an HPROF just to "have extra context."
3. Request approval for **the specific JVM, time window, file type, and recipients**, assessing performance impact at the same time.
4. Confirm secure storage: owner, file permissions, quota, encryption, retention, and container/host reachability.
5. Prepare a **secret-free** report template. If checking flags/features, record key/status rather than dumping all properties.

### Phase B — Capture and Verification

6. Run commands under the approved identity after verifying the target JVM's PID and actual command.
7. Capture only the planned recording/dump; never run unbounded loops.
8. Never pipe raw `VM.system_properties`/`VM.command_line` stdout into CI logs or tickets; output may contain secrets.
9. Verify the file landed in the right path with expected permissions/size; inspect **metadata** first, and inspect contents only in a closed analysis environment.
10. Record a manifest: timestamps, JVM/app, collector, tool/JDK version, purpose, storage path, hash if required by policy, and expiration date.

### Phase C — Transfer and Analysis

11. Use approved encrypted channels with authentication and audit trails. Never use public "anyone with the link" URLs.
12. Use hardened analysis machines with disk encryption and least privilege; avoid unverified plugins and public online upload analyzers.
13. Limit copies of raw files; when sharing findings with larger teams, use classified summaries and manually inspect for PII/secrets.
14. Never upload raw HPROF/JFR files to third-party analyzers without contractual, security, and data-handling approvals.

### Phase D — Wrap-Up

15. Document technical findings and conclusions: which findings have evidence, which artifacts were used, and who retains access.
16. Revoke temporary privileges, close incident JMX/JDWP ports, delete temporary copies per retention, and handle backups/snapshots per policy.
17. If secret exposure is discovered, treat it as a security incident: locate exposure, halt sharing, **rotate/revoke credentials** as needed, and review audit trails.
18. Review startup configs, file paths, IAM/RBAC, and network controls so future collections do not repeat mistakes.

### Quick Decision Table

| Question | Preferred Approach | When Escalation Is Justified |
| --- | --- | --- |
| Long JVM GC pauses? | GC logs, metrics, controlled JFR. | HPROF only if an object graph for a real memory leak is needed. |
| Want active JDK/flags? | Classified config inventory or allowlisted keys. | Raw `VM.command_line`/`VM.system_properties` only with approval, never broadly shared. |
| Where is CPU hot? | Safely configured JFR CPU samples / profiler. | Request extra events/stacks only when needed; inspect payload sensitivity. |
| App hung on threads? | JFR/thread dumps and logs per runbook. | Remote debugger only when indispensable under strict exception approval. |
| Need ongoing monitoring? | Metrics/exporters and managed JMX with TLS/auth/ACLs. | Never expose JDWP or take periodic heap dumps just for monitoring. |

## 12. Mistakes That Commonly Cause Security Incidents

| Mistake | Why It Is Wrong | Better Practice |
| --- | --- | --- |
| "Heap dumps are just technical diagnostics." | Can contain live objects, customer data, and secrets. | Treat as restricted artifacts; block public sharing, enforce retention and audits. |
| "JFR has no private data because it only measures performance." | May include args/env/properties/stacks/paths/custom payloads depending on events. | Audit settings, classify, and sanitize before sharing. |
| "`-Dtoken` will not leak if the app never logs it." | Values still appear in launch args/properties and inspection tools. | Use secret managers/credential providers; never pass secrets via CLI. |
| "Putting secrets in env vars is completely safe." | Env vars can still be read by privileged process/container tools or leak into events/logs. | Least privilege, minimize lifetime, prevent log/diagnostic leakage. |
| "Sharing one UID across apps makes management easy." | Anyone holding that UID gains inspect/attach reach across apps. | Separate service identities and restrict `sudo`/`exec`. |
| "`DisableAttachMechanism` makes JVM data unreadable." | Blocks standard attach only; does not stop root/host/JMX/JDWP/file access. | Defense in depth plus alternative preconfigured diagnostics. |
| "Opening the JMX port is enough for remote JMX." | Must govern RMI port, TLS/certs, auth, registry, roles, and network ACLs. | End-to-end testing from both allowed and denied clients. |
| "JMX `readonly` is always safe for everyone." | Readable MBeans can still expose sensitive configuration. | Restrict viewers and expose only safe metrics. |
| "Set `authenticate=false` because there is a firewall." | Any host reaching the port/network gains broad control. | Keep auth enabled; layer TLS + identity + network ACLs. |
| "JDWP is just for viewing stacks." | Debuggers can suspend/invoke methods and disrupt execution. | Isolate to loopback/tunnels; never expose to the Internet. |
| "Compressing HPROF/JFR and sending a link is secure." | Compression is not encryption; link permissions govern who reads it. | Encrypt + authenticate + audit + enforce retention. |
| "Deleting a file in a pod removes all copies." | Copies may remain in PVCs, buckets, backups, tickets, and analyst laptops. | Manage lifecycle across every copy. |
| "One regex hiding `password=` makes raw artifacts safe to publish." | Secrets may not be named `password`, hiding in objects or custom fields. | Guard raw artifacts; share reviewed summary reports instead. |

## 13. Practical Verification and Permission Troubleshooting

### 13.1. `jcmd` Cannot Attach: Do Not "Fix" by Loosening Permissions Recklessly

If attach fails or `jcmd -l` does not list the process:

1. Confirm the JDK tools and target JVM are compatible versions.
2. Verify exact PID, OS user, PID namespace, and process state.
3. Check `-XX:+DisableAttachMechanism`, OS/container security policies, and supported attach mechanisms.
4. Follow approved procedures before changing config, using pre-existing diagnostics, or scheduling a restart.
5. **Never** `chown` entire volumes, enable `privileged`/`hostPID`, or grant users root merely to "make `jcmd` work."

Attach failure can mean **security controls are working as designed**, not a bug to disable.

### 13.2. Discovering an Unexpected Open JMX/JDWP Port

Identify **which port is listening, on which interface, which process owns it, and who can reach it**. On Linux hosts you lawfully administer:

```bash
ss -ltnp
```

Appropriate privileges may be needed to display process names/PIDs. Inspect only **listening-socket metadata**; never transmit sensitive data externally. Also review firewalls/security groups, Pod Services/port-forwards, and network policies at every layer.

If an endpoint is missing from the approved inventory: restrict network exposure immediately per procedure, preserve audit logs, identify how it was enabled (`-D...`, JVM flags, sidecar/agent), disable safely, and check for suspicious connections. **Never assume closing a port secures everything**: dump files and local attach carry their own risks.

### 13.3. Discovering an HPROF/JFR Shared Out of Scope

Prioritize:

1. **Restrict or revoke** read access on the link/bucket/volume to stop further copying.
2. Open a security log/ticket with minimal details—never paste sensitive dump contents.
3. Audit who accessed or downloaded the file, check all copies, and verify retention policies.
4. Determine what data types could reside in the artifact and assess customer/credential impact.
5. Rotate/revoke tokens, credentials, and certificates potentially exposed per IR procedures.
6. Fix the root cause: dump directory, CI artifact rules, ACLs, public object-storage access, debug ports, or launch scripts.
7. Evaluate notification obligations under applicable legal/policy rules.

**Never** just delete the file and close the case: live credentials, access logs, snapshots, and copies may still exist.

## 14. Final Checklist for Production Java Diagnostics

- [ ] Clear justification and approval, selecting **the least sensitive data type** sufficient to solve the issue.
- [ ] Verified exact PID, OS user, namespace, JDK, impact, and time window.
- [ ] Heap dumps/JFR written to **a dedicated area** with restricted owner/ACLs, encryption, and quotas.
- [ ] `-XX:+HeapDumpOnOutOfMemoryError` paired with a reviewed `HeapDumpPath` and retention policy.
- [ ] No real tokens/passwords in JVM `-D...` args, app command-line args, or debug logs.
- [ ] No raw `VM.command_line`, `VM.system_properties`, or environment outputs dumped into tickets/CI logs.
- [ ] Local attach, `sudo`, `kubectl exec`, `cp`, and debug containers strictly controlled.
- [ ] Remote JMX protected by network controls, TLS/auth, certs, registry/RMI ports, and roles.
- [ ] JDWP disabled publicly; if ever needed, enabled only via temporary audited exception workflows.
- [ ] Analysts hold minimum required access, and shared reports undergo review.
- [ ] Post-incident cleanup revokes temporary access, closes ports, and disposes of dumps/recordings/copies/backups.
- [ ] Suspected secret exposure triggers security incident response and credential rotation.

## Self-Check Questions

1. **Why must an `.hprof` be treated as sensitive even when captured only for a memory leak?** Because it can contain live data payloads and credentials in objects/arrays, with no default redaction.
2. **Why can `-Ddemo.accessToken=...` leak even if Java code never prints its value?** Because launch arguments and system properties remain visible via authorized paths like `VM.command_line`, `VM.system_properties`, JMX/`RuntimeMXBean`, and OS tools.
3. **Does `-XX:+DisableAttachMechanism` replace ACLs, closing JMX/JDWP, and file protection?** No. It only disables standard attach mechanisms and introduces operational trade-offs.
4. **Does `JFR.dump` write its file in the `jcmd` shell or on the target JVM?** On the filesystem visible to the target JVM at the specified path; verify container namespaces.
5. **What two ports must be checked for JMX?** Typically the **registry port** and the **RMI connector port** (`jmxremote.port`, `jmxremote.rmi.port`); inspect actual config alongside TLS/auth and network policies.
6. **Why must JMX `readonly` still be restricted to authorized users?** Because readable MBeans can still expose sensitive configuration and metadata.
7. **Why is JDWP riskier than a metrics endpoint?** Because a debugger can control execution, suspend threads, and invoke methods.
8. **Can a raw JFR file be posted in public chat if system-property events are disabled?** No: it can still hold stacks, paths, endpoints, JVM args/custom events, and other sensitive details.
9. **If an HPROF was downloaded without authorization, is deleting it from the server enough?** No; audit access logs, track copies, and evaluate revoking/rotating exposed secrets.
10. **What are three steps to remember before sharing an artifact?** Classify contents, restrict recipients/transfer channels, and enforce retention and auditing.

## Official References

- [Oracle Java 21 — `jcmd` (`VM.command_line`, `VM.system_properties`, `GC.heap_dump`, `JFR.dump`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle Java 21 — `java` command (`-XX:+DisableAttachMechanism`, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle Java — Monitoring and Management Using JMX Technology: authentication, SSL/TLS, roles, password/access files, and RMI registry](https://docs.oracle.com/en/java/javase/22/management/monitoring-and-management-using-jmx-technology.html).
- [Oracle Java Flight Recorder — Security (recordings can contain command lines and environment)](https://docs.oracle.com/javacomponents/jmc-5-5/jfr-runtime-guide/run.htm).
- [Oracle Java 21 — JDWP connection/invocation and debugger configuration](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html).
- [Oracle Java 21 — `RuntimeMXBean` (JVM input arguments)](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html).
- [Oracle Java 21 — `Properties` and `System.getProperties()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html).
