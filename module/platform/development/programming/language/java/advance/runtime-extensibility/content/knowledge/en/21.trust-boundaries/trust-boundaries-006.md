# Isolating Untrusted Code in a Separate Process with an Explicit Communication Protocol

## 1. Why Separate Processes?

In a dynamically extensible Java system, plugins may be loaded via `URLClassLoader`, `ServiceLoader`, `ModuleLayer`, in-memory compilation, or JShell. Those techniques isolate *class names, dependencies, and logical lifecycles*, but do not automatically restrict the OS privileges of code running inside the same JVM. A malicious or buggy plugin can read any file the process is permitted to read, open network connections, mutate `System` properties, exhaust heap/CPU, spawn unbounded threads, or crash the process via native code.

A more appropriate boundary for **untrusted code** is running it in a **separate process** under restricted OS privileges, communicating over a protocol with an explicit format and clear quotas. A separate process isolates heap, threads, static state, system properties, and JVM crashes, yet it only becomes a real security boundary when paired with OS permissions, filesystem/network isolation, and resource limits.

```text
                 Trust boundary
Host JVM               |         Worker JVM / sandbox
business logic         |         untrusted plugin code
    |                   |                   |
    +-- request ------->| IPC codec ------->|
    |                   |                   |
    +<-- response ------| IPC codec <-------+
    |                   |
timeout / circuit      |     minimal OS privileges, CPU/RAM limits
breaker / audit        |     namespace/container/VM per risk level
```

**Key point:** IPC does not make a plugin trustworthy; IPC merely narrows the interaction surface. The host must still treat responses from the plugin as untrusted data, validate every field, and handle cases where the process dies, hangs, or returns malformed data.

## 2. Define Privilege Boundaries Before Choosing an IPC Technology

A new process typically inherits the privileges of the user running the spawning process unless configured otherwise at the OS/container level. Therefore, **`new ProcessBuilder(...)` does not create a sandbox by itself**. Choose an appropriate enforcement mechanism:

| Goal | Measures to consider |
| --- | --- |
| Prevent reading host secrets | Dedicated OS user, filesystem permissions, restricted mounts |
| Prevent arbitrary network access | Network policies, namespaces, firewall/egress allowlists |
| Prevent exhausting CPU/RAM | cgroups/container limits, job objects, process quotas |
| Prevent spawning uncontrolled child processes | Sandbox policies, process limits, process-tree cleanup |
| Prevent crashing the host JVM | Process boundary and input/output validation |
| Prevent exploiting privileged host APIs | Expose only minimal IPC operations; authorize every request |
| Prevent dragging the host into deadlock | Timeouts, bounded queues, cancellation, process kill policies |

Running a child process under the same OS account, same mounts, and full network access may achieve only **fault isolation**, not sufficient **privilege isolation**. On Linux, you can use user/container/namespaces, seccomp, and MAC mechanisms; on Windows, consider restricted tokens, job objects, AppContainer, or VMs; the practical choice depends on the environment. Never claim a secure sandbox merely because code lives in another JAR.

## 3. Protocol Design: Smaller and More Explicit Is Better

An IPC protocol should have explicit fields and rules:

- **Version:** `protocolVersion` or message types that can be upgraded safely.
- **Request ID:** matches requests to responses, especially under concurrency or retries.
- **Operation:** an allowlist of commands such as `ECHO`, `CALCULATE`, `TRANSFORM`; never let a worker accept arbitrary shell commands.
- **Payload:** clear schema, types, and maximum sizes; validate both before sending and after receiving.
- **Status/error:** distinguish success, business errors, schema errors, and worker failures.
- **Framing:** how messages are delimited, e.g., newline-delimited JSON or length-prefixed frames.
- **Deadline/cancellation:** per-request timeouts; strategy to kill/restart unresponsive workers.
- **Encoding:** UTF-8 and rules for escaping, newlines, and null bytes.
- **Backpressure:** bounded queues / limits on concurrent requests.

A JSON Lines example might look like:

```json
{"version":1,"requestId":"r-123","op":"ECHO","payload":{"text":"hello"}}
{"version":1,"requestId":"r-123","ok":true,"result":{"text":"hello"}}
```

These are **two separate messages**, not one JSON object: a request from the host and a response from the worker. When using JSON Lines, payloads containing newline characters must be escaped inside JSON, never concatenated with raw newlines. For production, use a reliable JSON parser/schema validator rather than parsing JSON with `split` or regex.

### Why Is Versioning Needed?

An older worker might understand `payload.text` but not `payload.encoding`. If the host sends a new schema without negotiation, the worker could misprocess data instead of rejecting it. A good rule is failing closed when `version` is unsupported, or explicitly specifying which fields are optional and backward-compatible.

## 4. Runnable Java 17+ Demo: Two JVMs, Minimal Line Protocol

This example intentionally uses a **single-line text protocol** (`PING`/`ECHO`/`QUIT`) so it runs with Java SE alone and requires no JSON library. It illustrates a process boundary and stdin/stdout communication, **not a complete security sandbox**. A production version should replace this with a schema featuring versions/request IDs, framing, and a real codec.

File `WorkerMain.java` runs in the child process:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public final class WorkerMain {
    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        PrintWriter out = new PrintWriter(
                new java.io.OutputStreamWriter(System.out, StandardCharsets.UTF_8), true);
        String line;
        while ((line = in.readLine()) != null) {
            if (line.equals("PING")) {
                out.println("OK:PONG");
            } else if (line.startsWith("ECHO:")) {
                String payload = line.substring(5);
                if (payload.length() > 100) {
                    out.println("ERR:TOO_LONG");
                } else {
                    out.println("OK:" + payload);
                }
            } else if (line.equals("QUIT")) {
                out.println("OK:BYE");
                return;
            } else {
                out.println("ERR:UNKNOWN_COMMAND");
            }
        }
    }
}
```

File `HostMain.java` spawns another JVM, sends requests, and waits for responses:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.*;

public final class HostMain {
    public static void main(String[] args) throws Exception {
        String javaBinary = Path.of(System.getProperty("java.home"),
                "bin", "java").toString();
        Process process = new ProcessBuilder(
                javaBinary, "-cp", ".", "WorkerMain")
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();
        ExecutorService readerThread = Executors.newSingleThreadExecutor();
        try (BufferedWriter toWorker = new BufferedWriter(
                    new OutputStreamWriter(
                            process.getOutputStream(), StandardCharsets.UTF_8));
             BufferedReader fromWorker = new BufferedReader(
                    new InputStreamReader(
                            process.getInputStream(), StandardCharsets.UTF_8))) {

            String[] requests = {"PING", "ECHO:hello", "QUIT"};
            for (String request : requests) {
                toWorker.write(request);
                toWorker.newLine();
                toWorker.flush();

                Future<String> response = readerThread.submit(fromWorker::readLine);
                String line = response.get(3, TimeUnit.SECONDS);
                if (line == null) throw new IllegalStateException("Worker EOF");
                System.out.println(request + " -> " + line);
            }
            if (!process.waitFor(3, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                throw new IllegalStateException("Worker did not exit");
            }
            if (process.exitValue() != 0) {
                throw new IllegalStateException("Worker exit=" + process.exitValue());
            }
        } catch (TimeoutException timeout) {
            process.destroyForcibly();
            throw new IllegalStateException("Worker response timed out", timeout);
        } finally {
            if (process.isAlive()) process.destroyForcibly();
            readerThread.shutdownNow();
        }
    }
}
```

Run both files in the same directory on JDK 17+:

```bash
javac --release 17 WorkerMain.java HostMain.java
java HostMain
```

Output:

```text
PING -> OK:PONG
ECHO:hello -> OK:hello
QUIT -> OK:BYE
```

Explanation: `ProcessBuilder` launches a second JVM; the host writes UTF-8 to stdin and reads one line from stdout. Each response has a 3-second timeout. `QUIT` terminates the worker; the host checks the exit code. For simplicity, requests are sent sequentially, only one request is in flight, and there are no request IDs; therefore, you **cannot** use this demo as-is for multi-request concurrency.

**Demo limitations:** if the reader task is blocked in `readLine()` and times out, it is unblocked by cancelling/closing the process streams when the process is killed; in production, design an independent reader loop and bounded queues to manage cancellation reliably. The demo also runs the worker under the same OS account without sandboxing: to use it with untrusted code, you must launch it inside a privilege-restricted environment.

## 5. Why Not Mix stderr into stdout?

If stdout is the protocol channel, any log line written by the worker to stdout can be misinterpreted as a response, breaking framing. Enforce the convention:

- **stdout**: protocol messages only.
- **stderr**: diagnostics/logs, with volume limits and a redaction policy.
- If stdout carries binary frames, never write arbitrary text to this stream.

`redirectErrorStream(true)` is convenient for simple shell invocations, but should **not** be used with a protocol relying on stdout, as stderr will mingle into responses. The demo uses `.redirectError(INHERIT)` to avoid touching the protocol; production systems can capture stderr separately into a bounded buffer and forward it to a logging pipeline.

## 6. Timeouts, Cancellation, Retries, and Process Lifecycle

A process can hang due to deadlocks, infinite loops, I/O waits, garbage collection, or malicious code intentionally withholding responses. A safe protocol needs two separate timeouts:

1. **Request deadline:** maximum time to wait for a response.
2. **Shutdown deadline:** maximum time to wait for the worker to exit after a stop command.

On timeout:

- Mark the request as failed; never accept a late response as the response to a new request.
- Send a cancellation if supported by the protocol; if untrusted or past the deadline, kill the process.
- Reap/clean up the process, close input/output streams, and cancel reader/writer tasks.
- If the worker holds state, determine whether retrying is safe; requests with side effects need idempotency keys or transaction IDs.
- A circuit breaker can pause dispatching to a repeatedly failing plugin, paired with a recovery policy.

Retry decisions must rest on semantics. `ECHO` has no side effects and is easy to retry; `TRANSFER_FUNDS` may require deduplication and exactly-once *business semantics* backed by durable storage rather than blindly retrying after a timeout.

### When a Worker Crashes Mid-Request

The host must distinguish EOF, broken pipes, nonzero exit codes, protocol violations, and timeouts. An EOF does not prove whether a task completed or rolled back: if the worker already wrote external data before crashing, state may be indeterminate. The contract must define an `UNKNOWN` outcome / reconciliation path for operations with side effects.

## 7. Validating Inputs/Outputs, Message Sizes, and Framing

With JSON Lines, each line is one JSON document. Enforce size limits before parsing: `BufferedReader.readLine()` imposes no default byte cap, so if a worker intentionally sends a massive line, the host can exhaust memory. With length-prefixed binary protocols, validate frame length before allocating buffers.

Establish at least:

| Item | Example rule |
| --- | --- |
| Protocol version | Reject unknown versions |
| Request ID | Unique within session; never reused while still pending |
| Operation | Allowlisted enum; never execute raw shell expressions |
| Payload | Schema validation and byte limit |
| Response | Strict parsing; verify ID, status, and size |
| Deadlines | Per-request timeout and shutdown timeout |
| Concurrency | Bounded in-flight requests and queue length |
| Encoding | UTF-8, proper escaping for JSON |
| Logging | Dedicated stderr, free of unnecessary secrets |

Do not use Java serialization (`ObjectInputStream`) as a default IPC choice for untrusted data: deserialization carries gadget/object-graph risks and tight coupling to class versions. JSON/Protobuf/CBOR with explicit schemas and validators are usually easier to control; you must still configure parsers safely, cap nesting/sizes, and validate required fields.

## 8. Version and Capability Negotiation

The host needs to know which protocol the worker speaks before sending business requests. You can open with a handshake:

```json
{"version":1,"requestId":"init-1","op":"HELLO","payload":{"supportedVersions":[1]}}
{"version":1,"requestId":"init-1","ok":true,"result":{"selectedVersion":1,"capabilities":["ECHO"]}}
```

If there is no overlapping version or a required capability is missing, **do not activate the worker**. Distinguish protocol version (IPC format and semantics) from plugin implementation version or business contract version.

Never let a worker arbitrarily ask the host to open any file/URL: if the protocol includes an operation like `READ_FILE`, the host must check allowlists, path canonicalization, and permissions on every request and grant no broader rights than needed. When the worker receives requests from the host, the host must likewise validate responses and never trust self-reported worker metadata.

## 9. IPC Architectures and Choices

| Option | Best suited for | Risks to manage |
| --- | --- | --- |
| stdin/stdout | Local workers, simple startup | Framing, backpressure, stderr isolation, reader threads |
| Unix domain socket / named pipe | Local-machine IPC, multiple requests | Filesystem/pipe permissions, authentication |
| Loopback HTTP/gRPC | Clear APIs and strong tooling support | Bind address, mTLS/token auth, port leakage, timeouts |
| Message queue | Distributed workers, retries/durability | Duplicate delivery, idempotency, ordering, poison messages |

No transport solves the trust boundary on its own. Choose based on latency, concurrency needs, portability, authentication, and operational complexity.

## 10. Contract Testing and Destructive Testing

Tests to have before running untrusted code:

- **Happy path:** requests/responses match schema, version, ID, and expected results.
- **Malformed frames:** worker sends invalid JSON, missing fields, wrong version, mismatched ID.
- **Large payloads/outputs:** exceeding byte limits, deep nesting, output spam.
- **Timeouts/hangs:** worker stops responding; host kills and cleans up on deadline.
- **Crashes:** worker exits nonzero or dies mid-message.
- **Concurrency:** multiple simultaneous requests never cross-match responses.
- **Retries/idempotency:** timeout after a side effect does not duplicate actions.
- **Permission tests:** worker cannot read secret paths or open forbidden egress.
- **Resource quotas:** worker exceeding CPU/memory limits is throttled or killed.
- **Restarts/reloads:** a different worker version re-handshakes cleanly; old processes drain.

Test permissions in the **actual deployment environment**, not only in Java unit tests. A misconfigured container policy can let a worker read the host filesystem even when the protocol is coded flawlessly.

## 11. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `ClassLoader` as a sandbox | Code still uses process privileges | Separate processes and apply OS isolation |
| Assuming `ProcessBuilder` restricts privileges automatically | Worker runs under the same user and rights | Restricted OS identity / container policy |
| Using stdout for both logs and protocol | Mis-parsed responses | Separate stderr, strict framing |
| Unbounded message lengths | OOM from oversized payloads/outputs | Bounded decoding |
| Missing request ID/version | Mismatched responses, hard protocol upgrades | Handshake and correlation |
| Retrying every request after timeout | Repeated side effects | Idempotency keys and reconciliation |
| Using default Java object deserialization | Security risks and tight coupling | Explicit codec/schema validation |
| Failing to kill hung processes | Resource leaks and backed-up queues | Deadlines and process-tree cleanup |
| Trusting worker results unverified | Injection / data corruption | Output validation and authorization |

## 12. Implementation Checklist

- [ ] Place untrusted code in a process/container/VM with minimal privileges.
- [ ] Cap worker CPU, RAM, file/network/process resources.
- [ ] Define protocol version, request ID, operations, schema, and framing.
- [ ] Enforce limits on input/output bytes, depth, concurrency, and queues.
- [ ] Dedicate stdout to protocol messages and stderr to logs.
- [ ] Enforce timeouts, cancellation, kill/restart, and process cleanup.
- [ ] Validate all responses; never treat raw data as privileged commands.
- [ ] Negotiate capabilities before routing requests.
- [ ] Design retries around idempotency and distinguish `UNKNOWN` outcomes.
- [ ] Test crashes, malformed outputs, hangs, quotas, and permission denials.

**Conclusion:** Moving an untrusted plugin into a separate JVM/process is a necessary step to establish a fault boundary and enable OS privilege enforcement. To become a true security solution, it requires **OS/container-level sandboxing** alongside a **small, versioned IPC protocol with clear schemas, framing, deadlines, validation, and error handling**. Neither a class loader nor a simple text protocol guarantees safety for untrusted code on its own.
