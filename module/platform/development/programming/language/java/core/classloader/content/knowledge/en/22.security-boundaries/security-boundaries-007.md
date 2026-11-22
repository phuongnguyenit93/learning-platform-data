# Process Separation When a Stronger Security Boundary Than ClassLoader Is Needed

`ClassLoader` is a tool for **loading and isolating Java type names**, not a reliable sandbox for arbitrary code. If the host loads a plugin using `URLClassLoader`, the plugin still **runs in the same JVM process** as the host: sharing the same heap/process, usually the same operating system permissions, able to affect shared resources, and not isolated from JVM-level failures such as exhausting memory or stopping the process.

When a plugin, document processor, script engine, or partner library is **not fully trusted**, a stronger approach is to **move the risky execution into a separate JVM/process**, communicate with the host over a controlled protocol, and apply **operating system or container/VM environment limits**. However, **simply calling `ProcessBuilder.start()` does not turn a subprocess into a sandbox**. If the child JVM runs under the same OS account, sees the same directories/secrets, and has no network/CPU/memory limits, the security boundary remains weak.

This Knowledge article belongs to **Java core – classloader / Security Boundaries**. The focus is on **when to separate processes, what the new boundary can and cannot prevent, how to design IPC, lifecycle, timeouts, resource limits, testing, and how to apply this in Java 17+**.

## 1. Distinguishing Four Levels of Isolation

| Mechanism | Primary Isolation | Not Automatically Guaranteed |
| --- | --- | --- |
| **A different `ClassLoader` in the same JVM** | Class namespace, dependency versions, runtime class identity, some static state | Heap/process/OS permissions/secrets, defense against malicious code, CPU/RAM limits |
| **A separate JVM process** | Separate JVM address space/heap, GC and JVM crashes largely do not directly corrupt the host heap, separate threads and exit status | File/network permissions, machine-wide CPU/RAM, secret data if sharing the same OS identity |
| **Separate process under an OS account/sandbox/container with a restrictive policy** | Can restrict filesystem, network, CPU/memory/process count, credentials/capabilities | Not automatically absolute: kernel/container escape, misconfiguration, IPC vulnerabilities |
| **Separate VM/machine and strict network/storage policy** | More independent kernel/machine boundary, blast radius can be greatly reduced | Does not eliminate hypervisor, OS, protocol, or permission configuration vulnerabilities |

**Boundaries are not boolean.** You need to look at the **threat model**: does the adversary control bytecode, input, plugin dependencies, protocol payloads, or is it just a potentially buggy library? What files can they read, where can they make network calls, what information can they access, and what level of resource damage can they cause?

If the goal is merely to use two different library versions in a trusted application, `ClassLoader` may be a lighter-weight choice. If the goal is to **prevent potentially malicious code from reading the host's tokens or calling OS resources**, merely swapping the loader is not enough.

## 2. Why Is ClassLoader Not a Complete Security Boundary?

A class loaded via a child loader:

```java
Class<?> pluginType = pluginLoader.loadClass("plugin.Task");
Object plugin = pluginType.getDeclaredConstructor().newInstance();
```

This is a **snippet**, assuming the `pluginLoader` variable is already declared and the caller handles exceptions. Even though `pluginType.getClassLoader()` is a separate loader, the plugin code still executes **within the current JVM process**.

What can happen if the plugin is able to call APIs matching the runtime permissions:

- Read/write files and directories that the **host process** has permission to access.
- Make network calls to destinations permitted by the network policy.
- View system properties/environment variables passed into the process.
- Create threads/executors, keep threads alive, and use CPU and memory.
- Call `System.exit(...)` to request stopping the **host JVM**.
- Use reflection/method handles, native interfaces, or other runtime capabilities within the practical limits of the JDK and environment.
- Cause `OutOfMemoryError`, retain object references, and cause garbage collection or the JVM process to become overloaded.
- Hold `ThreadLocal`/TCCL/callback references that prevent the class loader from unloading, causing a memory leak.

You can restrict the APIs that the host **itself grants via an interface**, but do not confuse “host-defined API capabilities” with removing the OS/JDK capabilities that plugin code already has when executed in the same process.

### Security Manager Is No Longer a Long-Term Sandboxing Option

In **JDK 17**, the Security Manager was **deprecated for removal** (JEP 411); new sandboxes should not be designed to depend on it. Starting in **JDK 24**, the Security Manager is **permanently disabled** (JEP 486) and cannot be enabled to restore the old Java permission model.

Therefore, when a real boundary is needed for untrusted code, think in terms of **OS process identity, sandboxes, containers, VMs, permissions, firewalls, and restrictive protocols**, rather than a `SecurityManager` installed by the host in the JVM.

## 3. When Should a Plugin Be Moved to a Separate Process?

Scenarios with clear reasons:

1. **Running low-trust third-party code**: marketplace plugins, scripts, or partner-provided bytecode.
2. **Parsing untrusted input** with complex libraries: document, image, or media parsers, or converter tools that may crash/hang.
3. **Tasks with unpredictable CPU/RAM**: running customer algorithms, code-judging engines, or batch processing.
4. **Need to reduce blast radius** when a native library, JNI, FFM, or JVM component fails: crashing the worker does not also bring down the host heap.
5. **Separating credentials and network access**: the worker can only read data supplied over IPC; the host keeps database tokens/payment secrets in another environment.
6. **Independent runtime version isolation**: the worker can run different JDK/dependency versions within a controlled deployment.
7. **Wanting to replace/restart plugins independently**: having health checks, process supervision, graceful shutdown, and policy-based restarts.

Cases where process separation is **not necessarily needed**:

- Trusted internal plugins that only conflict over two versions of a JSON library.
- Call paths that are extremely latency-sensitive and depend on many synchronous object references.
- Needing to share a large object graph, JVM heap state, or `synchronized` monitors, where a data-transfer protocol is not easy to design.
- The required permission mechanism is not very strict and all code has been reviewed.

Separating processes has **startup cost, separate memory, serialization, IPC latency, and deployment/lifecycle overhead**. Specify the threat model and response limits before choosing an architecture.

## 4. Standard Architecture: Host Holds Privileges, Worker Receives Only Minimal Jobs

```text
                        HOST PROCESS
             ┌──────────────────────────────┐
request ---> │ AuthN/AuthZ, business rules  │
             │ secrets / DB credentials     │
             │ validate + rate limit        │
             └────────────┬─────────────────┘
                          │ narrowed request
                          │ IPC with framing, size/time limits
                          ▼
             ┌──────────────────────────────┐
             │ WORKER PROCESS / separate JVM│
             │ low-privilege OS identity    │
             │ filesystem/network allowlist │
             │ CPU, memory, process quotas  │
             │ run plugin/parser/library    │
             └────────────┬─────────────────┘
                          │ untrusted result
                          ▼
             ┌──────────────────────────────┐
             │ HOST: parse / validate       │
             │ policy check / persist       │
             └──────────────────────────────┘
```

**Principle of least privilege:** the worker does not need direct access to the production database, secret store, or host source tree to process a piece of text. The host can pass **bounded input content** instead of mounting the entire filesystem containing the original files.

**Data from the worker is not automatically trusted** just because the worker is a child process launched by the host. If the worker runs untrusted code, output must be parsed/validated like input from an external party.

### Capability Suggestions

Instead of handing over a “filesystem path” and letting the worker open it arbitrarily, you can design an API:

```text
Host → Worker:
  job_id = "task-42"
  op = "parse-text"
  bounded_input = <size-limited content>
  format = "plain"

Worker → Host:
  job_id = "task-42"
  status = "ok" | "error"
  bounded_result = <result>
```

This is a **protocol model**, not an implemented wire format. A production implementation requires framing, validation, versioning, encoding, timeouts, and authentication/authorization mechanisms appropriate to the communication channel.

## 5. `ProcessBuilder` Creates a Subprocess; It Does Not Automatically Sandbox

Java SE provides `java.lang.ProcessBuilder`:

```java
ProcessBuilder builder =
        new ProcessBuilder(javaExecutable, "-cp", classPath,
                           "worker.Main", "job-123");
Process process = builder.start();
```

This is a **snippet**, requiring the variables and `IOException` handling. Each argument is **a separate element** of the command list, rather than concatenating a shell command string and hoping spaces/quotes are resolved properly.

Important configurations:

- **`command(...)`**: the executable and each argument. Do not run through `cmd /c` or `sh -c` unless a shell is truly needed; passing user input to a shell creates a command injection risk.
- **`directory(File)`**: the child's working directory, not a sandbox root.
- **`environment()`**: map of the child's environment variables. By default, it is a **copy** of the parent's environment. Secrets should be stripped and genuinely needed variables allowlisted, though a few system variables may be required to run.
- **`redirectInput`/`redirectOutput`/`redirectError`**: specify source/destination streams.
- **`redirectErrorStream(true)`**: merges stderr into stdout; convenient when reading logs, **unsuitable if stdout is a machine-readable protocol**.
- **`start()`**: starts the subprocess; may throw `IOException`.
- **`Process.waitFor()`**, `waitFor(timeout, unit)`, `exitValue()`, `isAlive()`, `destroy()`, `destroyForcibly()`: lifecycle management.
- **`ProcessHandle`**: PID, status, and descendants at the API level; managing **the entire process tree** depends on the operating system and sandbox policy.

**Crucially:** `ProcessBuilder` starts a process **with the OS credentials/permissions that the launcher provides**. Java does not automatically switch to a less-privileged user, enable seccomp, or restrict network or memory when calling `start()`. Those restrictions require reliable OS/container/orchestrator configuration.

## 6. Lab A — Host JVM Invoking an Independent Worker JVM

This lab demonstrates the **launch → stdout → exit status** flow of a separate Java process. It is **not a sandbox example**; it only lays the foundation for IPC/lifecycle.

Structure:

```text
process-lab/
└── src/
    └── demo/
        ├── EchoWorker.java
        └── ProcessHost.java
```

**`src/demo/EchoWorker.java`:**

```java
package demo;

public final class EchoWorker {
    public static void main(String[] args) {
        if (args.length != 1 || !"PING".equals(args[0])) {
            System.err.println("invalid request");
            System.exit(2);
        }

        System.out.println("PONG");
    }
}
```

**`src/demo/ProcessHost.java`:**

```java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;

public final class ProcessHost {
    private static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        String file = windows ? "java.exe" : "java";
        return Path.of(System.getProperty("java.home"), "bin", file)
                .toString();
    }

    public static void main(String[] args) throws Exception {
        String classes = Path.of("out").toAbsolutePath().toString();

        Process process = new ProcessBuilder(
                javaExecutable(), "-cp", classes,
                "demo.EchoWorker", "PING")
                .redirectErrorStream(true)
                .start();

        String reply;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        process.getInputStream(),
                        StandardCharsets.UTF_8))) {
            reply = reader.readLine();
        }

        int exit = process.waitFor();

        System.out.println("worker says=" + reply);
        System.out.println("exit=" + exit);
    }
}
```

Compile and run from the `process-lab` directory with **JDK 17+**:

```sh
javac --release 17 -d out src/demo/EchoWorker.java src/demo/ProcessHost.java
java -cp out demo.ProcessHost
```

**Host stdout on a system that allows spawning child processes:**

```text
worker says=PONG
exit=0
```

### What This Lab Demonstrates

1. The host and worker are **two JVM processes**; the worker has its own `main`, heap, threads, and process exit status.
2. `ProcessBuilder` receives the path to the `java` executable from the host's `java.home`, avoiding dependence on the shell `PATH`. The filename differs on Windows and Unix-like platforms.
3. `-cp` points to **the absolute path of `out`**, so the worker sees `demo.EchoWorker`.
4. `"PING"` is a fixed argument. `EchoWorker` validates it and then returns `PONG` to stdout.
5. `ProcessHost` reads one UTF-8 line, waits for the child to finish, and prints exit code 0.
6. Data is passed through a **stdout pipe**, **not by calling a method directly within the same heap**.

**Intentional limitations:** the example only has a small single line of output from a trusted worker. With an arbitrary worker, `readLine()` **has no length limit**, and reading until EOF can block if the worker does not close stdout. Size limits, timeouts, pumping stdout/stderr, and cancellation/cleanup rules are needed, as covered in the following sections.

**Deployment note:** looking up `java.home/bin/java` works in many standard JDK/JRE distributions; containers or custom runtime images may not include the executable or may not allow exec. A real-world application needs a **configured and validated** worker runtime path, rather than assuming it always has permission to spawn processes.
