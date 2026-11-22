# File Descriptor Policies via `jdk.crac.resource-policies`

Before creating a checkpoint, CRaC needs to bring the process into a state that can be safely restored. On Linux, open files, pipes, and sockets are represented by **file descriptors (FDs)**. An open FD can cause a checkpoint to fail because that resource is still tied to the external environment or cannot be restored properly.

The preferred approach is for the application to proactively manage the resource lifecycle using CRaC `Resource`: closing or pausing before checkpoint, then reopening or revalidating after restore. However, sometimes an FD is opened inside a library that the development team cannot modify, or the library does not yet have CRaC integration. In those cases, some CRaC builds provide the `jdk.crac.resource-policies` configuration to specify how the runtime should handle FDs opened through JDK APIs.

This is a limited support mechanism. It does not replace resource management in the application and does not handle FDs created directly from native code. To use it safely, you need to understand the FD types, supported actions, rule ordering, and post-restore behavior of the exact JDK build being run.

## 1. What is a file descriptor and why does it affect checkpointing?

A file descriptor is an identifier that a process uses to access a resource managed by the operating system. On Linux, an FD can represent:

- A file being read or written.
- A directory opened for traversal.
- A pipe used to transfer data between processes or threads.
- A TCP, UDP, or Unix domain socket.
- Another resource opened at the operating system level.

In Java, an FD can be owned indirectly by `FileInputStream`, `FileOutputStream`, `RandomAccessFile`, an NIO channel, a socket, or a higher-level library. For example, a logger may keep a file handle open throughout the application's lifecycle; an HTTP client may maintain sockets in a connection pool; a library may keep a pipe to communicate with a child process.

At checkpoint, the process is saved to resume at another time or in another environment. If an open file points to a path that no longer exists, a socket is still tied to an old network session, or a pipe has an invalid other end, continuing to use the FD after restore may fail or cause incorrect behavior.

Therefore, CRaC usually requires the application to close files and network connections before checkpoint, except for certain resources handled by the platform according to specific rules. If unhandled FDs remain, the checkpoint may be rejected with a `CheckpointException` and a suppressed exception indicating which FD is still open.

## 2. What does `jdk.crac.resource-policies` solve?

`jdk.crac.resource-policies` is a system property used to specify the path to a file containing FD handling rules. The runtime reads the rule file when performing a checkpoint and applies the corresponding action to each FD that matches a rule.

This configuration is useful when:

- A third-party library holds a file handle but does not provide callbacks to close/open according to CRaC.
- The application cannot change the source code of the component opening the FD.
- There are stable files that can be closed before checkpoint and reopened after restore.
- You need to restrict or classify certain FDs during the migration of an application to CRaC.

For example, a logging library opens a log file and does not allow the development team to intervene in the lifecycle of the file handle. If the runtime and library version support it, a policy can request closing the file before checkpoint and reopening the file at its previous position after restore.

The property is passed to the JVM using `-D`:

```bash
java \
  -Djdk.crac.resource-policies=/etc/orders/crac-resource-policies.yml \
  -XX:CRaCCheckpointTo=/var/lib/orders/checkpoint \
  -jar orders-service.jar
```

`/etc/orders/crac-resource-policies.yml` is an example path. The file must exist, have appropriate read permissions, and use the syntax supported by that CRaC JDK build. Checkpoint and engine option names also depend on the distribution; check the specific runtime documentation before applying the command in a deployment environment.

`jdk.crac.resource-policies` is not an API that replaces `org.crac.Resource`. The policy controls how the runtime handles certain open FDs. It does not know the business meaning of transactions, requests, consumers, or connection pools. If the application owns the resource and can modify the code, it should manage the resource explicitly in callbacks.

## 3. Policy file structure

A policy file consists of multiple rules. Each rule is a group of `key: value` pairs; rules are separated by a line containing three hyphens `---`. Lines starting with `#` are comments. The syntax is a subset of YAML, so you should use a simple `.yml` or `.yaml` file and avoid complex YAML features that the runtime's parser may not support.

The two required attributes of each rule are:

- `type`: the type of file descriptor to match.
- `action`: the action the runtime will perform.

Example:

```yaml
type: file
path: /var/log/orders/application.log
action: reopen
---
# Close temporary application files before checkpoint.
type: file
path: /tmp/orders/**
action: close
```

The values of `type` and `action` are case-insensitive according to implementation documentation. It is best to use lowercase consistently to keep the file easy to read.

### 3.1. Rule order matters

For each open FD, the runtime checks the rules in order from top to bottom. **The first matching rule is applied; subsequent rules are not evaluated for that FD.** Therefore, place specific rules before general rules.

Example:

```yaml
# Important log file to be reopened after restore.
type: file
path: /var/log/orders/audit.log
action: reopen
---
# Other files in the log directory are handled as a group.
type: file
path: /var/log/orders/**
action: close
```

If the order is reversed, the `/var/log/orders/**` rule will also match `audit.log`, causing the specific rule below it to never be applied to that file.

If no rule matches, the default behavior is `error`: the runtime reports an error and the checkpoint fails. This is intentional so that an unclassified FD does not silently end up in the image.

### 3.2. `warn: false`

For actions other than `error`, the runtime usually logs a warning when it finds an FD handled by a policy. You can add:

```yaml
warn: false
```

to disable the warning for that rule. This attribute only controls the warning message; it does not change the action and does not make an FD safer. During initial setup, you should keep warnings enabled to observe which FDs are being handled by policies. Only disable them after you have understood and accepted the impact.

## 4. File descriptor types

Policies support four main types. Each type has its own identification criteria and set of appropriate actions.

| `type` | Meaning | Commonly used identification |
|---|---|---|
| `file` | File or directory on the local filesystem | `path` |
| `pipe` | Anonymous pipe | FD type; no path to distinguish individual pipes |
| `socket` | TCP, UDP, or Unix domain socket | Family, address, port, or path |
| `filedescriptor` | Raw FD not recognized as file/pipe/socket at a higher level | FD number `value` or native description `regex` |

The type name `filedescriptor` is used for raw FDs. Do not confuse it with the `file` type, which can be identified by a filesystem path.

## 5. Policies for files and directories

### 5.1. Selecting files by `path`

A `file` type rule uses `path` to specify a file or directory. You can use a specific path or a glob pattern following Java's `FileSystem.getPathMatcher()` mechanism.

Example:

```yaml
type: file
path: /etc/orders/application.yml
action: reopen
---
type: file
path: /var/log/orders/*.log
action: reopen
---
type: file
path: /tmp/orders/**
action: close
```

Meaning:

- The specific configuration file is closed before checkpoint and reopened after restore.
- Log files matching the glob are handled by the second rule.
- Files located in the application's temporary directory tree are closed; code must not continue using those handles after restore.

The `*` glob is commonly used to match names within a single path level; `**` can match across multiple directory levels according to Java's glob rules. Verify patterns with `PathMatcher` and test on the actual filesystem, especially when paths contain spaces, special characters, or differences between operating systems.

### 5.2. Actions for files

| Action | What the runtime does | Consequence after restore |
|---|---|---|
| `error` | Reports an error and fails the checkpoint | No valid image from that checkpoint attempt |
| `ignore` | Lets the checkpoint/restore engine handle the FD | The engine may validate and reopen the file on restore; the result depends on the environment |
| `close` | Closes the file before checkpoint | If code continues to use the old handle after restore, the operation will throw a runtime error |
| `reopen` | Closes the file before checkpoint and attempts to reopen it after restore | The file is reopened at its previous position if reopening succeeds |

`reopen` is suitable for a file with a stable path where the application can continue using the same handle after it is reopened. If the file is deleted, renamed, mounted differently, or has its permissions changed while the image is saved, the reopen operation may fail.

`close` is only suitable when the component owning the FD will not use that handle after restore, or the application has another mechanism to create a new handle. Closing an FD while keeping the Java object referencing it does not automatically give the object a new FD.

`ignore` delegates responsibility to the engine. This is not a guarantee that every file will always be restored successfully. The file may be checked against the filesystem state and restore conditions; test in the actual environment.

### 5.3. Example for logs and temporary files

A sample configuration might look like:

```yaml
# Logger needs to continue writing to the file after restore.
type: file
path: /var/log/orders/application.log
action: reopen
---
# Temporary files used only before checkpoint.
type: file
path: /tmp/orders/**
action: close
---
# Other log files left for the checkpoint engine to handle.
type: file
path: /var/log/orders/*.log
action: ignore
```

The specific rule for `application.log` must come before the general log glob. Otherwise, the general rule may match first and change the intended behavior.

In real-world applications, prefer configuring a logger that has official close/reopen callbacks. Glob policies should only be used when you cannot manage the resource directly and have verified that the logger does not hold other FDs.

## 6. Policies for pipes

A pipe is a data communication channel. Anonymous pipes do not have a path or stable address to distinguish them like files or sockets. Therefore, CRaC documentation recommends having at most one rule for anonymous pipes.

Example:

```yaml
type: pipe
action: close
```

Supported actions for pipes are:

- `error`: default, reports an error and fails the checkpoint.
- `ignore`: lets the checkpoint/restore engine handle the pipe.
- `close`: closes the pipe before checkpoint.

Pipes can be used internally by libraries, executors, or child processes. If a pipe is closed while a component is still waiting to read/write, the thread may receive EOF, an I/O error, or hang depending on how the library handles it. Therefore, identify the pipe owner and the state of related threads before choosing `close`.

Named pipes are recognized as type `file` and handled with a `type: file` rule by path.

## 7. Policies for sockets

A socket represents a network connection or a Unix domain socket. A `socket` rule can be refined with attributes so that it only applies to the appropriate group of sockets.

Commonly encountered identification attributes:

| Attribute | Meaning |
|---|---|
| `family` | Address family: IPv4, IPv6, or Unix domain |
| `localAddress` | Local address; `*` can match any bound address |
| `remoteAddress` | Peer address at the other end; `*` can match any address |
| `localPort` | Local port; can be a number or `*` |
| `remotePort` | Remote port; can be a number or `*` |
| `localPath` | Local path of a Unix domain socket; supports glob |
| `remotePath` | Remote path of a Unix domain socket; supports glob |
| `listening` | In versions supporting this attribute, selects listening/server sockets |

The `family` value usually has aliases:

- `ipv6` or `inet6`: IPv6 socket.
- `ipv4` or `inet4`: IPv4 socket.
- `ip` or `inet`: IPv4 or IPv6.
- `unix`: Unix domain socket.

### 7.1. Socket filtering examples

Example selecting a TCP socket on local port 8080:

```yaml
type: socket
family: ipv4
localPort: 8080
action: close
```

Example selecting a Unix domain socket by path:

```yaml
type: socket
family: unix
localPath: /run/orders/*.sock
action: close
```

Additional conditions help the policy affect only the intended sockets. Do not use a broad rule like `type: socket` and `action: close` if the application still needs those sockets to serve requests or manage connections after restore.

### 7.2. Limitations of `reopen` for sockets

`reopen` behavior for sockets depends on the JDK/CRaC version. Current Azul implementation documentation supports the `listening: true` attribute to select listening server sockets; on supported builds, `action: reopen` closes the listening socket before checkpoint and reopens the socket on the same local address after restore.

Two-way connected sockets between client and server cannot be restored this way; Azul documentation explicitly states that `reopen` for that socket type will report an error. Community CRaC reference documentation also describes socket reopen limitations in implementations that do not yet support reopening. Therefore, do not assume every CRaC JDK supports `reopen` for sockets. Check the exact version and vendor.

Example for a runtime that supports `listening: true`:

```yaml
type: socket
family: inet
localPort: 8080
listening: true
action: reopen
```

If the runtime does not support the `listening` attribute or socket reopen, manage the server socket using CRaC `Resource` or use an action permitted by that version's documentation. For client connections, it is usually necessary to close them before checkpoint and create new connections after restore through application logic.

## 8. Policies for raw file descriptors

Some FDs do not have a corresponding high-level Java object for the runtime to recognize as a file, pipe, or socket. For example, an FD created by a native library or passed from native code into the JVM. Policies can identify this type of FD using:

- `value`: a specific FD number.
- `regex`: a regular expression matching the FD's native description, using `java.util.regex.Pattern` syntax.

Example:

```yaml
type: filedescriptor
value: 123
action: close
---
type: filedescriptor
regex: .*eventfd.*
action: ignore
```

FD numbers like `123` can change between launches due to differences in the order resources are opened. Therefore, rules based on FD numbers can easily become inaccurate if the environment is not fixed. Regex matching on the native description can be more flexible, but it still depends on how the kernel and runtime display the description; check actual logs.

For raw FDs, only `error`, `ignore`, and `close` are available; there is no `reopen`, because the runtime does not have enough high-level information to recreate the object owning the FD.

## 9. Combined configuration example

The example below illustrates how to order specific rules before general rules and use different actions for each FD group:

```yaml
# 1. Main log file: reopen after restore.
type: file
path: /var/log/orders/application.log
action: reopen
---
# 2. Temporary files: close, application will not reuse old handles.
type: file
path: /tmp/orders/**
action: close
---
# 3. Named pipes represented as files.
type: file
path: /run/orders/*.pipe
action: close
---
# 4. Anonymous pipe: applies to unidentifiable pipes.
type: pipe
action: close
---
# 5. Listening socket: only use on runtimes supporting this attribute.
type: socket
family: inet
localPort: 8080
listening: true
action: reopen
---
# 6. Raw descriptor: reject by default if no clear decision has been made.
type: filedescriptor
regex: .*eventfd.*
action: error
```

This is an illustrative example, not a policy that can be applied as-is to every application. In particular, the socket `reopen` rule requires runtime support; pipes and raw FDs should only be handled after identifying the component that owns them. Start with a narrow policy, observe logs, and then add rules incrementally once you know which FDs are open and why.

## 10. Diagnosing open FDs when checkpoint fails

When checkpoint fails, the exception may indicate the FD type, FD number, and path or resource description. Use that information to find the component that opened the FD and choose the right way to handle it.

### 10.1. Enabling stack traces for FDs opened via Java APIs

Some CRaC builds provide the property:

```bash
-Djdk.crac.collect-fd-stacktraces=true
```

This property records the stack trace at the time an FD is created via a Java API. When checkpoint reports an open FD, the stack trace can point to the thread and the location in code that opened the file or socket.

Example diagnostic launch command:

```bash
java \
  -Djdk.crac.collect-fd-stacktraces=true \
  -XX:CRaCCheckpointTo=/tmp/orders-checkpoint \
  -jar orders-service.jar
```

After identifying the source that opened the FD, prefer fixing the component's lifecycle or using CRaC callbacks provided by the library. A policy should only be the solution for resources that cannot be modified directly.

### 10.2. Investigating FDs created by native code

`jdk.crac.resource-policies` does not handle FDs opened directly from native code. When logs indicate a native FD or there is no Java stack, you need to investigate the syscall that created the FD. On Linux, `strace` can trace the process and threads:

```bash
strace -f -o /tmp/orders-strace.log java -jar orders-service.jar
```

You can filter resource-opening syscalls such as `openat`, `socket`, `pipe2`, `dup`, or `dup2` to find where the FD is created. Depending on the build and system permissions, capturing native stacks may require appropriate symbol/debug packages.

After finding the source, use the native/library API to close the resource at the right time or add lifecycle integration. Do not try to apply Java policy rules to FDs that policies cannot manage.

### 10.3. Distinguishing policy issues from Resource callback errors

`CheckpointException` can aggregate multiple different errors: failed Resource callbacks, open FDs, or unmet platform conditions. Read both the main exception and suppressed exceptions. If a `Resource.beforeCheckpoint()` fails to close a pool, adding a file policy will not resolve that lifecycle error.

## 11. Principles for choosing policies safely

Before adding a rule, answer these questions:

1. What type is the FD: file, pipe, socket, or raw descriptor?
2. Which component opened it and who owns its lifecycle?
3. Can the FD be closed using an official library API?
4. If using `close`, will the code still use the old object after restore?
5. If using `reopen`, will the path or address still exist and be valid after restore?
6. If using `ignore`, can the engine restore the resource in the target environment?
7. Could the rule accidentally match other FDs due to an overly broad glob or condition?
8. Does the runtime being used support the exact action and attributes in the rule?

Some practical principles:

- Prefer modifying the application or library to close/open resources via `Resource`.
- Use policies for parts that cannot be directly intervened in, not to hide FD leaks.
- Place specific rules before general rules.
- Keep the default `error` action for unclassified FDs.
- Use `reopen` for files when you need to continue using the handle and have verified the path/position.
- Use `close` when you are certain the code will not continue using the old handle.
- Only use socket `reopen` for socket types that the exact runtime explicitly supports.
- Do not use Java policies for FDs opened from native code.
- Keep warnings enabled during the observation phase and record every FD handled by policies.
- Test both checkpoint and restore; a rule that only makes checkpoint succeed does not prove the application works properly after restore.

## 12. Policy deployment workflow

`jdk.crac.resource-policies` can be introduced into a project in the following sequence:

**Step 1 — Collect FDs.** Run the application on the CRaC runtime and record checkpoint errors or the list of open FDs. Enable stack traces if FDs are created via Java APIs.

**Step 2 — Identify owners.** Find the class, library, thread, or native component that opened the FD. Determine whether the FD needs to exist after restore.

**Step 3 — Prefer lifecycle APIs.** If the application or library can be modified, register a Resource to close before checkpoint and reopen after restore. If not, choose a policy suitable for the FD.

**Step 4 — Write narrow rules.** Specify `type`, `path`, socket filters, or raw FD matchers and the action. Place specific rules first. Avoid overly broad wildcards.

**Step 5 — Pass the system property.** Add `-Djdk.crac.resource-policies=/path/to/policy.yml` to the JVM configuration used at checkpoint. Ensure the policy file is present and readable in the image creation environment.

**Step 6 — Check logs.** Review warnings and confirm the right FDs are matched by the right rules. If a policy does not match, the default `error` behavior will help detect unhandled FDs.

**Step 7 — Test restore.** Verify that reopened files work, closed handles are not reused, sockets/pipes are restored according to actual support, and the application reaches readiness.

**Step 8 — Lock configuration by runtime.** Record the JDK/vendor version, policy file, checksum, and test results. When upgrading the JDK, re-verify the parser, attributes, and behavior of each action.

## 13. Common mistakes

**Treating policies as a complete replacement for CRaC Resource.** Policies only handle FDs within their supported scope; they do not coordinate transactions, schedulers, threads, or business logic. Use Resource for lifecycles that the application can control.

**Thinking policies can handle native FDs.** This mechanism only applies to FDs opened through JDK APIs. FDs created by native code must be handled in native/library code or investigated separately.

**Placing wildcard rules before specific rules.** The first matching rule wins. A general rule placed at the top can prevent specific rules from ever running.

**Using `close` and then continuing to use the old object.** A closed handle does not reopen itself. If code needs to continue accessing it, use `reopen` when appropriate or create a new resource via callbacks.

**Using `ignore` without checking the engine.** Delegating to CRIU/engine does not guarantee that the resource can always be restored in a different environment. Check paths, mounts, and restore conditions.

**Using `reopen` for all sockets.** Two-way client/server sockets cannot be reopened like files. Only use listening socket reopen capability when the exact runtime supports it.

**Disabling warnings too early.** Warnings are an important signal to know which FDs the policy is handling. Keep the logs during setup and testing.

**Not testing after restore.** A successful checkpoint only proves that the image creation step passed the conditions at that time. The application can still fail when using file handles, pipes, or sockets after restore.

## 14. Self-check for understanding

1. **What value does `jdk.crac.resource-policies` accept?** The path to a rule file containing file descriptor handling policies.
2. **What are the two required attributes of a rule?** `type` and `action`.
3. **If multiple rules match an FD, which rule is applied?** The first rule in file order; subsequent rules are skipped for that FD.
4. **What does the `reopen` action do for a file?** Closes the file before checkpoint and attempts to reopen it at its previous position after restore.
5. **Why can `close` cause errors after restore?** The old Java object may still be used by code even though the FD it owns has been closed.
6. **Can policies handle FDs opened by JNI/native code?** No. They must be handled in the native component or investigated using syscall tracing tools.
7. **Can `reopen` be used for all sockets?** No. Support depends on the runtime; some builds only support listening sockets, while two-way client-server sockets cannot be reopened via policy.
8. **Do policies replace registering a `Resource`?** No. Resource remains the primary mechanism for applications to manage lifecycles; policies are limited support for FDs that are difficult to intervene in.

## References

- [CRaC — File descriptor policies](https://crac.org/reference/fd-policies/): rule syntax, FD types, and actions according to CRaC project documentation.
- [Azul — File Descriptor Policies](https://docs.azul.com/crac/usage/fd-policies): attribute details and limitations across Azul Zulu/Zing builds.
- [CRaC — Debugging failures](https://crac.org/reference/debugging/): diagnosing open FDs across Java and native code.
- [Azul — CRaC VM options and system properties](https://docs.azul.com/crac/usage/vm-options): how to pass `jdk.crac.resource-policies` and diagnostic options.

## Conclusion

`jdk.crac.resource-policies` allows configuring how CRaC handles certain open file descriptors at checkpoint. A policy file consists of rules with `type` and `action`, separated by `---`; rule order determines that the first matching rule is applied. FD types include file, pipe, socket, and raw file descriptor; actions can be `error`, `ignore`, `close`, or `reopen` depending on the type and runtime version.

Use policies as a controlled solution for FDs opened via JDK APIs that the application cannot easily manage directly. For resources owned by the application, still use CRaC Resource to close/open according to lifecycle. For native FDs, handle them at the native layer. Always verify the exact JDK version, checkpoint logs, restore behavior, and readiness before deploying a policy to production.
