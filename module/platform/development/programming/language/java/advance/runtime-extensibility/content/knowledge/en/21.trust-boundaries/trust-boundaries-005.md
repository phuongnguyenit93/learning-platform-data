# Trust Boundaries: Restricting Objects, Paths, and Host Application Services Exposed to Extensions

## 1. Core Problem: The Host Must Not Grant Its Full Authority

In a Java system with **extensions/plugins**, the host often grants extensions capabilities such as reading templates, viewing parts of configuration, invoking business services, emitting events, or saving results. Extensions may be loaded via `ServiceLoader`, custom `ClassLoader`, `ModuleLayer`, or factories.

A dangerous mistake is handing plugins overly privileged objects directly: `ApplicationContext`, `DataSource`, a `Path` to the root directory, `HttpClient`, `ExecutorService`, service locators, raw credentials, or application-wide registries. Once handed these, an extension can traverse public methods, callbacks, and objects accidentally returned by the host to reach resources **unrelated to its task**.

The goal of this lesson is to design a **trust boundary** grounded in **least authority / least privilege**:

- Grant **only the exact operations** needed for approved work.
- Allow access **only to the exact data, resources, tenants, and paths**.
- Check **scope, quotas, lifecycle, and current permissions** on every invocation.
- Never hand out objects that allow reaching administrative host privileges or secrets.
- Provide **revocation, auditing, and cleanup** workflows when a plugin is disabled or replaced.
- Never confuse a narrow API structure with **a sandbox for malicious Java code**.

That last point is especially critical: if an untrusted Java extension runs **inside the same JVM as the host**, it can still attempt to call system APIs directly—such as `java.nio.file.Files`, `Socket`, reflection, or native libraries—with the process's privileges. A narrow facade only limits **privileges the host explicitly grants through parameters**; it does not eliminate ambient authority. For adversarial code, you need separate processes, OS permissions, network policies, quotas, and clear IPC.

### 1.1. Properly Scoped Delegation Diagram

```text
              HOST (trusted application)
    +---------------------------------------------+
    | authenticated identity, plugin generation   |
    | tenant, permissions, secrets, config        |
    | internal DataSource, file root, HTTP client |
    | pricing and other privileged services      |
    +---------------------------------------------+
            |  issue only approved capabilities
            v
       HostAccess facade
       +----------------------------------+
       | readNote("welcome.txt")          |
       | quote(units: 1..10)              |
       | authorize, validate, audit       |
       | revoke/cleanup (host side only)  |
       +----------------------------------+
            |
            v
       Extension / plugin
       +----------------------------------+
       | run(HostAccess)                  |
       | does not receive raw root Path,  |
       | DataSource or PricingService     |
       +----------------------------------+
```

This is a **minimal-API delegation model for cooperative extensions**. Do not treat the fact that an extension cannot see a private field in an interface as proof that it cannot achieve the same thing via the JDK or runtime when running in the same process.

### 1.2. Six Questions to Answer Before Granting an Object

| Question | What must be determined |
| --- | --- |
| **Who receives the capability?** | Plugin ID, version, generation, tenant, host-authenticated principal |
| **What may it do?** | Read, write, lookup, publish, schedule, transfer, or administer |
| **On which data?** | Logical IDs, allowlists, directory trees, record ownership, services/topics |
| **With what limits?** | Byte limits, connections, rates, concurrency, CPU/time, and request counts |
| **For how long?** | Single invocation, session, generation, lease, or until revoked |
| **Who checks and audits?** | The host-side facade/service at execution time, not only at plugin initialization |

These answers form part of the **extension contract** and should be expressed in APIs, config metadata, execution policies, and test suites. An object reference handed out can be retained indefinitely in fields/static caches; therefore, "issuing once" does not by itself constrain its usage lifetime.

## 2. Restrict the Object Graph, Not Just Type Names

A Java method returning an object can open paths to other objects. If a plugin receives a seemingly narrow interface that includes `getRawService()`, `getDelegate()`, `getApplicationContext()`, `getConnection()`, or `getRootPath()`, hiding behind the initial abstraction loses most of its value.

### 2.1. References That Should Never Be Handed Out Unconditionally

| Host object passed directly | Resulting privilege / risk | Better alternative to provide |
| --- | --- | --- |
| `ApplicationContext` / service locator | Look up arbitrary beans and subsystems | Facade with a small set of approved methods |
| `DataSource` or raw JDBC `Connection` | Query/modify data across tenants; open arbitrary transactions | Tenant- and operation-scoped business methods |
| Root `Path`, `File`, `FileSystem` | Find/open files outside target list | Logical resource names and allowlisted read/write APIs |
| `HttpClient`, arbitrary-URL HTTP gateway | SSRF, token leaks, uncontrolled egress | `fetchApprovedCatalog(catalogId)` or service gateway |
| Global `ExecutorService` / scheduler | Submit unbounded jobs that outlive unload | `scheduleApprovedJob(spec)` with quotas and cancellation |
| General event bus | Subscribe to or publish on any topic | Topic- and tenant-scoped publisher/subscriber |
| Mutable config, `Map` holding secrets | Modify shared state, read credentials | Immutable snapshot; very narrow opaque secret capability |
| `ClassLoader`, `ModuleLayer.Controller` | Interfere with loading/module graph unnecessarily | Business-layer host API |
| Mutable domain objects | Alter host state via getters/aliases | Immutable DTOs and defensive copies |
| Logger with privileged writer/storage | Write sensitive logs, generate high load | Host logging facade with schema/quotas |

**Never design generic APIs like `invoke(serviceName, methodName, args)`** for arbitrary calls. That simply repackages a service locator under another name, turning authorization into an unnecessarily hard problem.

### 2.2. Capability-Based Facade APIs

Suppose a plugin only needs to read a document and calculate a price for a valid unit count:

```java
public interface HostAccess {
    String readNote(String relativeName) throws java.io.IOException;
    int quote(int units);
}
```

This is an **illustrative interface snippet**, not a standalone runnable Java file. `HostAccess` declares exactly two operations; it does **not** expose `getRootPath()`, `getPricingService()`, or `getAnyBean()`.

Compare:

```java
// Overly broad privileges if the plugin does not genuinely need them:
void initialize(java.nio.file.Path appRoot,
                javax.sql.DataSource dataSource);

// Narrower contract scope:
void initialize(HostAccess access);
```

These are two **illustrative** method signatures; they must be placed inside a suitable class/interface to compile. A narrow API is only effective when its implementation **actually validates inputs and context**, rather than blindly forwarding to raw services.

### 2.3. Be Careful with Returned Objects

- `List.copyOf(list)` and `Map.copyOf(map)` provide immutable container snapshots, but are **shallow copies**: mutable elements or values inside can still be modified.
- `Collections.unmodifiableList(original)` forbids modification via the wrapper yet continues reflecting changes from the underlying list.
- Java `record` types do not automatically deep-copy `byte[]`, `Map<String, MutableItem>`, or internal mutable objects.
- Returning an `InputStream` or `Iterator` backed by a DB cursor/transaction can extend access duration and keep resources alive past the intended lifecycle; byte limits, time limits, and close ownership must be defined.
- Never return `Connection`, `Statement`, `ClassLoader`, `Class<?>`, or a dynamic proxy exposing its delegate when the task only needs a value.
- For secrets, do not hand out credentials and expect the plugin "not to read them"; the API should perform the secret-requiring operation on the host and return minimal results.

If an extension needs to read a few fields, it is better to return an immutable DTO filtered by policy. When DTOs contain nested objects, ensure defensive copies or truly immutable data structures all the way across the boundary.

### 2.4. Shared Class Identity for Interfaces Between Host and Plugin

If the host and plugin implementation are loaded by different class loaders, the shared `HostAccess` contract, request/response DTOs, callbacks, and exceptions must have **a single unified runtime definition**. Typically, place the API in a parent loader and have the plugin depend on that API without bundling its own duplicate copy. Two classes with the same binary name defined by different class loaders are not the same runtime type.

Separate granting access via a facade from controlling class loading: a plugin does not need a `URLClassLoader` handed to it just so the host can invoke `run(HostAccess)`.

## 3. Authenticating Identity and Permission Scope on the Host Side

A capability can be bound to:

- The plugin ID/version/generation selected by the host.
- The tenant/user/session authenticated from the host environment.
- Resource scope (allowed note IDs, record IDs, event topics).
- The allowed set of methods/operations.
- Quotas, concurrency, deadlines, and expiration times.
- Revocation mechanisms, audit context, and trace IDs.

Never trust an identity self-declared by a plugin. For example:

```java
// Risk if the plugin can supply "admin" itself:
internalService.listRecords(pluginSuppliedTenantId);

// Better contract direction:
HostAccess scoped = hostPolicy.issue(authenticatedTenant, pluginGeneration);
scoped.readNote("welcome.txt");
```

This is **architectural pseudocode**: `internalService`, `hostPolicy`, and `authenticatedTenant` are not JDK-defined variables. The host must bind the tenant inside its own capability and enforce authorization upon data access, never trusting a `tenantId` inside a plugin's request payload.

### 3.1. Separate Distinct Operation Permissions

Permission to read a file does not imply permission to **list directories, inspect metadata of all files, write, delete, rename, or register watchers**. For data, `readById` permission does not imply `listAll` or `searchAllTenants`. For an event bus, permission to publish to topic A does not imply subscribing to topic A or publishing to topic B.

Interfaces can be split to avoid accidentally widening permissions:

```java
interface ApprovedReader {
    String read(String logicalName) throws java.io.IOException;
}

interface ApprovedPublisher {
    void publish(String topic, byte[] payload);
}
```

This is only an **illustrative API snippet**; implementations must enforce policy/tenant/topic/byte checks. Merely prefixing a name with "Approved" provides no protection on its own.

### 3.2. Preventing Confused Deputy

**Confused deputy** occurs when a low-privilege plugin uses a high-privilege host to act outside its scope. For example, `readAnyUri("file:///sensitive/config")` executed by the host with the host's own file-reading privileges and returning the data to the plugin.

Mitigate this by using logical resource IDs instead of arbitrary URIs, checking operation/resource/tenant right at the boundary, not passing raw tokens, and genuinely restricting process/gateway permissions. Checking only at plugin discovery time **is insufficient** if each subsequent request can carry a new path or ID.

## 4. Restricting Accessible Paths

Paths are sensitive inputs due to absolute paths, `..` traversal, symbolic links, mount points, case folding, and races when the filesystem changes.

### 4.1. Prefer Logical Names Over Raw `Path`s

If a plugin only needs the "welcome" document, the host should accept `"welcome"` or `"welcome.txt"` and map it internally to an allowlisted directory. Do not give the plugin the absolute root path or allow arbitrary file URIs.

Minimum procedure for a relative path:

1. The host selects `root` itself and resolves the real/canonical path via `root.toRealPath()`.
2. Parse input with `Path.of(name)`, rejecting null/blank values, malformed paths, and absolute paths.
3. Build the candidate with `rootReal.resolve(requested).normalize()`.
4. Compare paths structurally using **`Path` components**: `candidate.startsWith(rootReal)`; do not check with `candidate.toString().startsWith(rootText)`.
5. Apply an allowlist of specific **logical names** or granted resource IDs; do not assume every file inside `root` is valid.
6. Before opening, resolve `candidate.toRealPath()` and confirm the real path still stays inside the allowed root to reduce symlink-escape risk.
7. Also check file type, maximum size, OS permissions, byte limits, timeouts, and stream/handle cleanup.
8. Audit outcomes by resource ID and operation without leaking full system paths in errors returned to the plugin.

Example check:

```java
Path rootReal = root.toRealPath();
Path requested = Path.of(relativeName);
if (requested.isAbsolute()) throw new SecurityException("absolute path");
Path candidate = rootReal.resolve(requested).normalize();
if (!candidate.startsWith(rootReal)) throw new SecurityException("outside root");
Path real = candidate.toRealPath();
if (!real.startsWith(rootReal)) throw new SecurityException("symlink outside root");
```

This is **illustrative code requiring imports, variables, and `IOException` handling**; section 8 contains a complete runnable program.

`Path.startsWith` compares by path components (according to the file-system provider). By contrast, a string check `"/data/app-backup".startsWith("/data/app")` returns `true` even though `/data/app-backup` is a different directory.

### 4.2. `normalize` and Real Paths Are Still Insufficient Against TOCTOU

`normalize` resolves `.`/`..` syntactically; it does **not** recognize symlinks, hard links, or mounts. `toRealPath()` follows the physical path at check time, but if another process alters a symlink/file **after the check** and **before open/read**, the application can still suffer a **time-of-check to time-of-use (TOCTOU)** flaw.

Therefore, **do not claim** that `normalize + toRealPath + startsWith` creates an airtight sandbox. Strengthening measures:

- Ensure OS permissions prevent untrusted code from modifying directory components trusted by the host.
- If the threat model includes an adversarial writer, prefer access relative to a **directory handle** with explicit permissions; `SecureDirectoryStream` helps **when supported by the filesystem provider**.
- Specify whether symlinks are permitted or forbidden. `NOFOLLOW_LINKS` on the final path alone does not guarantee all parent components and races are handled.
- For file writes, handle create-only, overwrite, atomic move, races, quotas, ownership, and cleanup separately; never blindly copy read logic to writes.
- Account for case-insensitive filesystems, Windows drive letters/UNC paths, Unicode normalization, hard links, mount points, and network filesystems according to deployment environments.
- Limit size, duration, and open handle counts; even a valid file can be huge or cause an I/O stall.
- If safety against malicious code is required, sensitive data must stay **outside the read permissions of the OS identity used by the plugin worker**.

### 4.3. Logical Allowlists Define the Business Boundary

If a plugin only needs `welcome.txt`, rejecting `private.txt` at allowlist validation is better than attempting a read and waiting for `NoSuchFileException`. An allowlist of file IDs is a business policy, while canonical path and filesystem checks are the path-protection layer.

Do not return error messages to the plugin such as "the file exists but you are not allowed to read it". That can turn the API into an oracle for enumerating files. Plugin-facing errors should be minimal, while internal logs retain sufficient debugging and audit details under access control.

### 4.4. Do Not Return Arbitrary `Path`/`URI` Just Because It Is a Value

A `Path` itself only describes an address, yet an extension running with host privileges can use that address to access the file directly. Returning a root path or a path to secrets accidentally leaks information and gives a tool to bypass the facade. Better to use logical IDs and return bounded content/DTOs, or opaque handles whose entire lifetime is managed by the host.

## 5. Restricting Host Application Services

An internal service may expose far more methods than a plugin actually needs. For example, a pricing service might have methods to view prices, replace price tables, edit discount policies, and manage caches; the extension should only invoke a single controlled lookup/pricing operation.

```text
Plugin                 Host façade                 Internal service
   | quote(3)               |                             |
   |----------------------->| check active/tenant/quota    |
   |                        | validate units in 1..10     |
   |                        | calculatePrice(3)           |
   |                        |---------------------------->|
   |                        |<----------------------------|
   |<-----------------------| return minimal result        |
```

### 5.1. Check at Every Operation

A business facade should verify:

- The caller/plugin generation is still authorized to use the service.
- The current operation is within the permitted capability set.
- The resource/tenant is within the granted scope; user IDs must not be trusted from plugin payloads.
- Parameters match valid schemas, lengths/ranges, and injection guards.
- Outputs restrict fields, record counts, bytes, and sensitivity.
- Request time/quotas/rates/concurrency are controlled with timeouts and rejection policies.
- Side effects obey transactions/idempotency/auditing.
- Revoked old handles no longer forward commands.
- Returned errors do not contain secrets, connection strings, internal stack traces, or full paths.

The `quote(units)` example in section 8 only allows `1..10`. That is an **input range policy**, not a total budget or rate limit; real quotas require counters/identities over time windows and an appropriate source of truth (especially across multiple processes).

### 5.2. Take Special Care with Databases and Secrets

Never hand out a `DataSource`/`Connection` just so a plugin can run a preset query. Replace it with `findAllowedDocument(id)`, `calculateApprovedQuote(request)`, or a domain service that verifies tenant row ownership inside a privileged layer.

Do not expose `getSecret(name)` when the goal is merely signing a message: the host can expose `signApprovedPayload(payload)` or a tightly scoped token capability without returning the raw secret. Scope secrets by tenant, purpose, TTL, rotation, and auditing.

If a plugin runs in the same process with ambient access to environment variables or config files, merely hiding facade getters is insufficient against an attacker. Ensure the worker/plugin process does not possess out-of-scope secrets at all.

### 5.3. HTTP Gateways and SSRF

If an extension needs online data, an API like `fetchAnyUrl(url)` is a major risk. A host HTTP gateway should use an allowlist of service IDs/endpoints and validate:

- Allowed schemes, hostnames, ports, paths, and HTTP methods.
- DNS resolution and private/loopback/link-local/metadata addresses per the threat model.
- Redirect destinations across every hop, preventing redirects from bypassing policy.
- Timeouts, max response bytes, content types, and retry limits.
- Correct-destination secret/token injection, never attaching host tokens to unapproved URLs.
- Network egress at the OS/gateway layer, not merely string checks on URLs.

A request whose hostname is allowlisted can still cause SSRF if DNS resolves or redirects to an internal endpoint unless actually checked. Therefore, policies based solely on URL strings are insufficient.

### 5.4. Event Bus, Schedulers, and Callbacks

Avoid handing out a raw `ExecutorService` or the entire event bus; an extension can pin threads, queue unbounded tasks, subscribe to sensitive topics, or keep callbacks firing after unload. Replace them with facades like `scheduleApprovedJob(spec)` and `publishApprovedEvent(topic, payload)` enforcing namespaces, quotas, cancellation, and generation ownership.

Every listener, thread context class loader, stream, and task must be tracked by the host; when stopping a plugin, unregister/cancel/close them within a deadline. Never invoke arbitrary plugin code while holding a global registry lock if doing so could deadlock or stall other requests.

## 6. Lifecycle and Capability Revocation Mechanisms

Handed-out references may be retained by an extension in fields or static caches. Thus, policy needs **revocation** enforced at every operation, not merely removing the capability from a registry.

A suggested state machine:

```text
CREATED -> ACTIVE -> REVOKING -> REVOKED
             |            |
             |            +-- new admissions rejected
             |            +-- in-flight complete/cancel according to policy
             |
             +-- operations validate permissions and lifetime
```

This is a **business model**, not a built-in JDK class. Upon revocation, decide whether in-flight operations finish, are cooperatively cancelled, or wait for a timeout—especially if operations involve I/O or transactions.

### 6.1. Why a Volatile Flag Alone Is Insufficient

A racy sequence:

```text
Thread A: sees active == true
Thread B: active = false; closes service
Thread A: uses service after it was closed
```

`volatile` improves visibility; it does not make check-and-enter atomic. You can use a **lifecycle gate** with a read/write lock or active leases/reference counts and conditions. The goal is coordinating **admission + actual use + revoke/close**.

The demo in section 8 uses `ReentrantReadWriteLock`: each operation holds the read lock throughout execution; `revoke` acquires the write lock and flips the active flag. Because the write lock waits for active read locks to be released, once `revoke` completes, no legacy facade operations remain running inside the gate. **Trade-off:** hanging I/O can hang revocation; production solutions need deadlines, cancellation, and avoiding read-to-write lock upgrades from callbacks.

### 6.2. Generations, Tenants, and Cleanup

When a new plugin version is loaded, issue fresh capabilities for the new **generation** instead of reusing revoked references from the previous generation. Registries, callbacks, and thread pools must drop references to old class loaders and instances so GC can reclaim them.

If a resource is owned by the host (DB pool, scheduler, shared cache), the plugin must never `close()` it. When a plugin owns private resources, the contract must state who closes them, when they close, and how exceptions are handled. "Revoked access" also does not automatically erase data the plugin already read or copies it made earlier.

## 7. `ClassLoader`, `ModuleLayer`, and Practical Security Limits

`ClassLoader` establishes namespaces and class identity, aiding version isolation; `ModuleLayer` manages named modules, reads/exports/opens. Neither provides a sandbox to restrict arbitrary file, DB, network, or native operations.

Do not rely on `SecurityManager` as a new plugin isolation architecture on modern JDKs. Strong boundaries for **untrusted code** generally require:

```text
Host process (secrets, internal DB, privileged services)
       |
       | IPC with explicit request schema and auth
       | per-operation authorization + audit + quotas
       v
Plugin worker process (separate OS identity)
  - restricted filesystem mounts/ACL
  - controlled network egress
  - memory/CPU/time limits
  - no direct host secrets
  - kill/restart/revoke via host
```

A host API facade remains very useful for trusted plugins: reducing coupling, avoiding bugs, curbing accidental privileges, scoping tenant data, and enabling implementation swaps. To defend against adversarial code, however, OS/process boundaries must genuinely restrict actions taken outside the facade.

## 8. Runnable Java 17+ Example: Narrow `HostAccess`, Allowlisted Paths, Quotas, and Revocation

The following demo builds a **host port** `HostAccess` exposing only `readNote` and `quote`. `ScopedAccess` holds the real root path, the list of allowed files, and an internal `PricingService`, while only the host knows about those objects. `SampleExtension` calls the port without ever receiving the raw `Path` or service.

The demo creates a temporary directory so it can run standalone. It tests an allowed operation, path traversal, a file not on the allowlist, an over-quota request, and a call after revocation.

**Known limitations:** for simplicity, the code calls `toRealPath()` before `Files.readString()` and **does not fully solve TOCTOU if an attacker has permission to swap symlinks/files between those two steps**. It also does not stop malicious Java code from calling the filesystem directly outside the interface. Do not use this program as a sandbox.

Save the file as **`HostBoundaryDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class HostBoundaryDemo {
    public interface HostAccess {
        String readNote(String relativeName) throws IOException;
        int quote(int units);
    }

    public interface Extension {
        String run(HostAccess access) throws IOException;
    }

    private static final class PricingService {
        private int quote(int units) {
            return Math.multiplyExact(units, 5);
        }
    }

    private static final class ScopedAccess implements HostAccess {
        private final Path rootReal;
        private final Set<String> allowedFiles = Set.of("welcome.txt");
        private final PricingService pricing = new PricingService();
        private final ReentrantReadWriteLock gate = new ReentrantReadWriteLock();
        private boolean active = true;

        ScopedAccess(Path root) throws IOException {
            this.rootReal = root.toRealPath();
        }

        private void checkActive() {
            if (!active) throw new SecurityException("capability revoked");
        }

        @Override
        public String readNote(String name) throws IOException {
            Lock read = gate.readLock();
            read.lock();
            try {
                checkActive();
                if (name == null || name.isBlank()) {
                    throw new SecurityException("invalid path");
                }
                final Path requested;
                try {
                    requested = Path.of(name);
                } catch (InvalidPathException ex) {
                    throw new SecurityException("invalid path", ex);
                }
                if (requested.isAbsolute()) {
                    throw new SecurityException("absolute path denied");
                }
                Path candidate = rootReal.resolve(requested).normalize();
                if (!candidate.startsWith(rootReal)) {
                    throw new SecurityException("outside root");
                }
                String logical = rootReal.relativize(candidate)
                        .toString().replace('\\', '/');
                if (!allowedFiles.contains(logical)) {
                    throw new SecurityException("file not allowlisted");
                }
                Path real = candidate.toRealPath();
                if (!real.startsWith(rootReal) || !Files.isRegularFile(real)) {
                    throw new SecurityException("unsafe target");
                }
                return Files.readString(real, StandardCharsets.UTF_8);
            } finally {
                read.unlock();
            }
        }

        @Override
        public int quote(int units) {
            Lock read = gate.readLock();
            read.lock();
            try {
                checkActive();
                if (units < 1 || units > 10) {
                    throw new SecurityException("units outside policy");
                }
                return pricing.quote(units);
            } finally {
                read.unlock();
            }
        }

        void revoke() {
            Lock write = gate.writeLock();
            write.lock();
            try {
                active = false;
            } finally {
                write.unlock();
            }
        }
    }

    private static final class SampleExtension implements Extension {
        @Override
        public String run(HostAccess access) throws IOException {
            return access.readNote("welcome.txt") + " | " + access.quote(3);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("boundary-demo-");
        try {
            Files.writeString(dir.resolve("welcome.txt"),
                    "Hello, plugin", StandardCharsets.UTF_8);
            ScopedAccess access = new ScopedAccess(dir);
            Extension plugin = new SampleExtension();
            System.out.println("allowed: " + plugin.run(access));

            try {
                access.readNote("../outside.txt");
                System.out.println("path traversal: allowed");
            } catch (SecurityException expected) {
                System.out.println("path traversal: denied");
            }

            try {
                access.readNote("private.txt");
                System.out.println("unlisted file: allowed");
            } catch (SecurityException expected) {
                System.out.println("unlisted file: denied");
            }

            try {
                access.quote(100);
                System.out.println("excess request: allowed");
            } catch (SecurityException expected) {
                System.out.println("excess request: denied");
            }

            access.revoke();
            try {
                access.quote(2);
                System.out.println("revoked: allowed");
            } catch (SecurityException expected) {
                System.out.println("revoked: denied");
            }
        } finally {
            Files.deleteIfExists(dir.resolve("welcome.txt"));
            Files.deleteIfExists(dir);
        }
    }
}
```

### 8.1. Running and Stdout

On JDK 17+:

```bash
javac --release 17 HostBoundaryDemo.java
java HostBoundaryDemo
```

**Verified output** when compiled with `javac --release 17` and run with `java`:

```text
allowed: Hello, plugin | 15
path traversal: denied
unlisted file: denied
excess request: denied
revoked: denied
```

Explanation:

1. **`allowed`:** `readNote("welcome.txt")` is allowlisted; `quote(3)` computes `3 × 5 = 15`.
2. **`path traversal`:** after `normalize()`, `../outside.txt` escapes root and is rejected by `Path.startsWith(rootReal)`.
3. **`unlisted file`:** `private.txt` is not in `Set.of("welcome.txt")`, so it is rejected **even if that file exists**.
4. **`excess request`:** `quote(100)` never reaches `PricingService` because it exceeds the `1..10` policy.
5. **`revoked`:** after `revoke()`, `active=false` and every new facade invocation is denied under the lifecycle lock.

### 8.2. Verifiable Invariants

- `HostAccess` publishes only **two methods**; there are no getters for the root directory, `PricingService`, or credentials.
- `ScopedAccess` keeps the root, allowlist, policy, and revocation state on the host side.
- `revoke()` is not in `HostAccess`, so the plugin **is not given an operation to revoke the host's capability through the interface**.
- Every facade call checks `active` while holding the read lock; the write lock for revocation prevents closing state while an operation holds the lock.
- Valid operations are not blocked by missing external libraries; the program uses only JDK 17.
- Ensuring input has no traversal and is in the allowlist is one protection layer, yet it does **not** prevent arbitrary code from using other means outside the facade.

### 8.3. What Must Be Added for Production?

The example uses `Files.readString` (reading the whole file) without a byte limit; production code must enforce file-size/streaming limits, deadlines, proper closing/`IOException` handling, and root directory permissions. If the filesystem can be modified by an adversary, race-mitigation mechanisms such as policy-enforced directory handles combined with OS-level restrictions are needed. If capabilities handle long-running tasks, the read/write gate should be replaced or supplemented with appropriate leases/cancellation and timeouts.

`quote` only limits **per-call parameters**; it is not a total rate quota, tenant policy, or distributed cost control. Production requires authenticated host contexts and quota tracking. Private class names are not a security boundary against untrusted code holding ambient process privileges.

## 9. Troubleshooting and Anti-Patterns

| Scenario | Cause / risk | How to fix |
| --- | --- | --- |
| Plugin receives `ApplicationContext` | Can access out-of-scope services | Grant a narrow capability-based facade |
| Plugin receives root `Path` | Can discover/access files outside target | Logical names + host-controlled root |
| Checking with `String.startsWith` | Prefix collisions occur | `Path.startsWith` and canonical policy |
| Using `normalize()` alone | Insufficient against symlinks/mounts/races | Check real path + directory handle / OS permissions |
| Returning raw `Connection` | Plugin runs SQL with host privileges | Business API and tenant validation |
| Checking only at injection time | Handle stays alive after revocation | Authorize on every operation + lifecycle gate |
| Plugin chooses `tenantId` | Tenant spoofing / confused deputy | Host binds authenticated identity |
| `getRawService()` on facade | Exposes the delegate | Return result data, not raw objects |
| Returning mutable entities | Plugin mutates host state out of control | Deep immutable DTOs / defensive copies |
| `fetchAnyUrl` | SSRF and token leaks via redirects | Allowlist gateway + network egress |
| Plugin keeps global executor | Pins threads / survives reload | Scoped scheduler, task quotas, cleanup |
| Relying on `ClassLoader` as sandbox | Does not block ambient filesystem/network | Process isolation, OS ACLs / network policies |
| Logging full paths/secrets | Leaks metadata/credentials | Minimal structured audits and masking |

### 9.1. Troubleshoot Authorization Failures in Order

1. Which plugin ID/generation/tenant received the capability? Was identity authenticated by the host?
2. Is the current operation within the policy for this plugin?
3. Is the resource ID/path in the allowlist for the right tenant?
4. Do `normalize`, real path, and symlink resolution handle the right filesystem semantics?
5. Did quotas/TTL/revocation change between capability issuance and invocation?
6. Did the error come from policy, filesystem, or an internal service? Should logs distinguish them?
7. Does the result or error message leak full paths, secrets, or another tenant's data?

**Never** default to returning "the file exists but reading is forbidden" to the plugin; that can create a side channel for probing filenames. Internal logs can record decision codes, correlation IDs, and logical resource IDs without exposing physical paths.

## 10. Trust Boundary Test Matrix

### 10.1. Paths and Resources

| Input | What to verify |
| --- | --- |
| `welcome.txt` on allowlist | Permitted when capability is active and file is valid |
| `private.txt` not allowlisted | Denied even if the file exists |
| `../outside.txt` | Does not escape root |
| Absolute Unix/Windows path | Cannot bypass root |
| Sibling prefix of root | Not mistaken for a child path |
| Symlink pointing outside | Canonical check denies when no race occurs |
| Symlink altered between check and open | Threat model requires directory-handle/OS policy |
| Invalid path / Unicode / case | Consistent provider-specific policy with clear errors |
| Huge file | Bounded bytes, timeout, no OOM |
| Directory instead of file | Not read as a regular file |
| Revoked capability | New operations denied |
| Changed OS permissions | Not bypassed via a higher-privilege fallback |

### 10.2. Services and Object Graphs

- Extension attempts to call write/delete methods while granted only read: no access path is provided by the host or policy denies it.
- Extension sends a forged tenant ID: does not alter the host-bound tenant.
- Extension attempts to retrieve raw services/delegates/`DataSource`/`ExecutorService` via getters: the API never returns them.
- Extension receives a DTO and mutates nested fields: does not alter mutable host state.
- Extension spams requests/payloads: rate/size/concurrency quotas and rejection policies take effect.
- Extension calls another service after revocation: every facade operation checks permissions at use time.
- Extension registers listeners/tasks and unloads: host cleans up all registrations/threads/resources.
- Old and new extension versions coexist: permissions/audits remain isolated by generation.
- Extension attempts SSRF through the gateway: allowlist/DNS/redirects/egress block it.
- For adversarial code: the worker cannot reach secrets/files/networks isolated by OS policy **even outside host APIs**.

### 10.3. Auditing and Observability

Minimal decision logging should record:

```text
pluginId=report-extension
generation=42
operation=readNote
resourceId=welcome
decision=DENY
reason=NOT_ALLOWLISTED
traceId=<correlation-id>
```

This is an **illustrative log format**, not the Java program's output. Logs must obey retention, read permissions, and masking, avoiding full absolute paths, source contents, credentials, or request payloads containing sensitive data.

## 11. Pre-Grant Plugin Permission Checklist

1. **Trust model:** internal, reviewed, or untrusted extension? If adversarial, is OS/process isolation genuine?
2. **Object inventory:** have all parameters, getters, callbacks, and overly privileged object references been reviewed?
3. **Least authority:** only strictly necessary methods, avoiding `ApplicationContext`, raw `DataSource`, or `Path root` unless essential?
4. **Identity:** does the host bind plugin/generation/tenant from a trusted source so plugins cannot self-declare privileges?
5. **Resource scope:** are operations, logical IDs, allowlists, and tenant ownership verified at use time?
6. **Path policy:** are absolute/traversal/prefix/symlink/mount/TOCTOU edge cases handled alongside proper OS ACLs and filesystem semantics?
7. **Service policy:** are schemas, output filtering, quotas, concurrency, timeouts, retries, auditing, and idempotency defined?
8. **Data objects:** are DTOs/collections genuinely immutable, with defensive copies even for nested objects, avoiding secret leaks?
9. **Lifecycle:** are revocation, in-flight handling, resource cleanup, listener/task cancellation, and generation replacement clear?
10. **Class identity:** are API/SPI loaders/modules shared correctly with no duplicate types causing `ClassCastException`?
11. **Defense in depth:** process identity, filesystem permissions, network egress, secrets separation, and constrained IPC?
12. **Tests:** allow/deny, traversal, symlink races, forged identities, quotas, revocation, and adversarial behavior?

**Conclusion:** The host must restrict **objects**, **paths**, and **services** granted to extensions using narrow-functionality facades/capabilities, enforce policies on every operation, map resources from logical IDs, and coordinate revocation across the lifecycle. Class loaders and modules only organize code and API boundaries; defending against adversarial plugins requires adding process isolation and OS permissions, because a narrow interface does not eliminate system privileges available to code running inside the same JVM.
