# Designing Java APIs Exposed to Scripts with Least Privilege

A Java application can allow **script** snippets to evaluate rules, generate reports, customize workflows, or invoke selected host-provided capabilities. A common integration pattern is exposing a Java object to the scripting environment so the script can call methods on that object. For example, a script may only be permitted to read notes belonging to the current tenant and create a new note, **not** receive an entire `DataSource`, `EntityManager`, `ApplicationContext`, `HttpClient`, `ClassLoader`, or filesystem access.

The core design questions are: **which objects are exposed, what permissions does each method grant, who enforces authorization and resource limits, and does the script engine genuinely prevent the script from bypassing that API?**

Guiding principle: **provide small, task-scoped capabilities; deny by default; validate on the Java side on every call; and never mistake a narrow interface for a security sandbox.**

## 1. Define the Trust Model Before Writing the API

There are at least three distinct scenarios:

| Script Source | Trust Level | Approach |
|---|---|---|
| Scripts written, reviewed, and deployed by the dev team alongside the app | Equivalent to internal code once release controls are applied | Narrow APIs reduce coupling and operational bugs; still enforce logic and versioning |
| Scripts configured in the product by admins or partners | **Partially** trusted; may be buggy or exceed intended scope | Dedicated capabilities, tenant/permission checks, auditing, quotas, restricted engine host interop |
| Scripts submitted by untrusted users | **Untrusted** input | Do not treat `Bindings` or Java interfaces as a security boundary; use an isolated execution environment and a capability-checking gateway |

**Distinguishing "API restriction" from a "sandbox":**

- A small Java interface only describes the operations the application **intends** to expose.
- A script engine may allow access to Java classes, reflection, built-in methods, global bindings, runtime internals, or other libraries. If so, the script **does not need** to go through the interface you designed.
- Code running in the same JVM shares the heap, threads, process identity, and OS privileges unless a real isolation mechanism is in place. `ClassLoader`/JPMS is not a sandbox for untrusted code.
- An engine that disables host interop can help narrow access under specific configurations, but you must verify the exact engine/version and all escape hatches (callbacks, objects, globals, imports, native access). Merely calling `engine.put("api", facade)` does not prove sandboxing.
- For untrusted scripts, run inside an **isolated process/container** with CPU, memory, time, network, filesystem, and secret restrictions; communicate with the host only through a validated request protocol.

**This lesson focuses on designing the Java capability surface and exposing it to scripts.** OS-level isolation is a mandatory additional defense layer when the threat model demands it, and cannot be replaced by writing clean interfaces.

## 2. Difference Between a Business API and Host Access

An overly broad integration is easy to spot:

```java
// Illustrates a design that MUST NOT be used for least-privilege scripts:
bindings.put("app", applicationContext);
bindings.put("database", dataSource);
bindings.put("fileSystem", fileService);
bindings.put("http", httpClient);
```

The snippet above only illustrates the anti-pattern and is **not a standalone runnable program**. Exposing general-purpose services to scripts typically introduces severe risks:

- `applicationContext` allows retrieving additional beans/services beyond the approved purpose.
- `dataSource` or a generic repository can read/modify multiple tables, bypassing business authorization layers.
- `fileService` accepting arbitrary paths opens the door to path traversal, reading secrets, or writing out-of-scope files.
- `httpClient` accepting arbitrary URLs can make requests to internal endpoints or sensitive resources (SSRF).
- Returning entities with lazy relationships, object managers, or runtime objects can expose far more functionality than originally intended.

Instead, publish APIs around **explicitly scoped business verbs**:

```text
Script
  |
  +-- notesRead.list(limit)
  +-- notesRead.find(id)
  |
  +-- notesWrite.add(text)    [only when granted]
  |
  X-- database.query(sql)
  X-- files.read(path)
  X-- http.request(url)
  X-- runtime.getClassLoader()
```

A well-designed API surface is **not** a single `NotesService` interface containing every operation gated by an `admin` flag. Split capabilities independently so the script receives only the functions permitted for the current execution.

## 3. Designing Narrow Capabilities Following Deny-by-Default

### 3.1. Input/Output Contract

Example for a notes domain:

| Capability | Method | Granted Permission | Constraints |
|---|---|---|---|
| `NotesRead` | `list(int limit)` | View notes **of the current tenant** | `1 <= limit <= 5` in the demo |
| `NotesRead` | `find(String id)` | Look up **an ID belonging to the current tenant** | Do not reveal whether the ID exists in another tenant |
| `NotesWrite` | `add(String text)` | Create a note **for the current tenant** | Validate text, write quota, and audit |
| **Not exposed** | `deleteAll()` | None | Never expose destructive operations |
| **Not exposed** | `findByTenant(String tenantId)` | None | Tenant is determined by the host, not supplied by the script |
| **Not exposed** | `executeSql(String sql)` | None | Never accept arbitrary SQL statements |

A read-only script must receive only a **reader**, not a writer by default. If writing is required, the host supplies a **writer only within an authorized context**; the writer implementation still enforces quotas, scope, and business rules.

APIs should return **small, immutable DTOs** (records containing Strings/numbers/booleans, immutable lists) rather than entities, repositories, `Connection` objects, or objects holding handles, callbacks, or open streams. DTOs should include only fields the script genuinely needs. Never expose tokens, secret configs, server paths, or full principal objects.

### 3.2. Authorization Context Must Be Created by the Host

Do not do this:

```java
// WRONG: the script gets to decide the data's tenant.
List<NoteView> listNotes(String tenantId);
```

Instead, create capabilities already bound to the authenticated context:

```java
// Idea: the host builds a context from the authenticated request,
// then exposes an API that does not let the script pass tenantId.
NotesRead read = capabilityFactory.readFor(authenticatedTenant);
```

Both snippets are **contract illustrations**. `authenticatedTenant` must not come from a script-declared variable; `capabilityFactory` is merely an illustrative name for a real host class.

A trustworthy execution context typically includes: `runId`, `actorId`, `tenantId`, the granted operation set, quotas, and deadlines. A crucial rule is that **every method capable of performing side effects checks the context at invocation time**, rather than treating placing an object into `Bindings` as sufficient authorization for the entire lifecycle.

### 3.3. Least Privilege Across Four Dimensions

1. **Actions**: allow reading, creating new records, or emitting events without expanding to deleting, transferring ownership, or admin actions.
2. **Data**: tenant, owner, ID set, readable fields; enforce directly in host-side repository queries.
3. **Resources**: call counts, record counts, data bytes, duration, concurrency, external API budgets.
4. **Time**: capabilities are valid for a single run or short window; support revocation, and never reuse permission-bound objects across requests.

Do not equate "the script can see the method" with "the script is allowed to execute the method." An authorization check held inside the service/gateway and re-verified at the operation boundary is vital for defense in depth.

## 4. Runnable Java 17 Example: Exposing Only Scoped Reader/Writer

This example focuses on the **host-side Java API**. It **does not require a JavaScript engine**: `main` stands in for a script-environment call to verify the contract and stdout on JDK 17. In a real application, the host decides whether to inject `NotesRead` and `NotesWrite` into the script.

Policies:

- The reader fixes the tenant to `acme`, with no method allowing the script to specify a tenant.
- `find` returns `Optional.empty()` for an ID in another tenant **just like a non-existent ID**, avoiding existence leaks via responses.
- `list` allows at most 5 records.
- The writer only exposes `add`; it validates input, enforces write budget, and attaches the tenant automatically on save.
- The `NoteView` DTO is a Java record containing two Strings; internal `StoredNote` data is never returned directly.

Save as **`ScriptApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class ScriptApiDemo {

    private record StoredNote(String id, String tenant, String text) {}

    // Immutable DTO: only data allowed to be returned to the script.
    public record NoteView(String id, String text) {}

    public interface NotesRead {
        List<NoteView> list(int limit);
        Optional<NoteView> find(String id);
    }

    public interface NotesWrite {
        String add(String text);
    }

    // Simulated host-side data store, not exposed to the script.
    private static final class Store {
        final List<StoredNote> notes = new ArrayList<>(List.of(
                new StoredNote("n1", "acme", "Alpha"),
                new StoredNote("n2", "other", "Private")));
        int sequence = 3;
    }

    private static final class ScopedRead implements NotesRead {
        private final Store store;
        private final String tenant;

        ScopedRead(Store store, String tenant) {
            this.store = store;
            this.tenant = tenant;
        }

        @Override
        public List<NoteView> list(int limit) {
            if (limit < 1 || limit > 5) {
                throw new IllegalArgumentException("LIMIT_OUT_OF_RANGE");
            }
            return store.notes.stream()
                    .filter(n -> tenant.equals(n.tenant()))
                    .limit(limit)
                    .map(n -> new NoteView(n.id(), n.text()))
                    .toList();
        }

        @Override
        public Optional<NoteView> find(String id) {
            if (id == null || !id.matches("n[0-9]+")) {
                throw new IllegalArgumentException("INVALID_ID");
            }
            return store.notes.stream()
                    .filter(n -> tenant.equals(n.tenant())
                            && id.equals(n.id()))
                    .findFirst()
                    .map(n -> new NoteView(n.id(), n.text()));
        }
    }

    private static final class ScopedWrite implements NotesWrite {
        private final Store store;
        private final String tenant;
        private int remainingWrites;

        ScopedWrite(Store store, String tenant, int writeBudget) {
            this.store = store;
            this.tenant = tenant;
            this.remainingWrites = writeBudget;
        }

        @Override
        public String add(String text) {
            if (remainingWrites == 0) {
                throw new SecurityException("WRITE_BUDGET_EXCEEDED");
            }
            if (text == null || text.isBlank() || text.length() > 40) {
                throw new IllegalArgumentException("INVALID_TEXT");
            }

            String id = "n" + store.sequence++;
            store.notes.add(new StoredNote(id, tenant, text.trim()));
            remainingWrites--;
            return id;
        }
    }

    public static void main(String[] args) {
        Store store = new Store();

        // In a real application: the tenant must come from the authenticated host.
        NotesRead read = new ScopedRead(store, "acme");
        NotesWrite write = new ScopedWrite(store, "acme", 1);

        System.out.println("before=" + read.list(5));
        System.out.println("otherTenant=" + read.find("n2").isPresent());

        try {
            write.add("  ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        System.out.println("created=" + write.add("Beta"));
        System.out.println("after=" + read.list(5));

        try {
            write.add("Gamma");
        } catch (SecurityException ex) {
            System.out.println("blocked=" + ex.getMessage());
        }
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac -encoding UTF-8 ScriptApiDemo.java
java ScriptApiDemo
```

Stdout verified on a JDK supporting Java 17:

```text
before=[NoteView[id=n1, text=Alpha]]
otherTenant=false
invalid=INVALID_TEXT
created=n3
after=[NoteView[id=n1, text=Alpha], NoteView[id=n3, text=Beta]]
blocked=WRITE_BUDGET_EXCEEDED
```

**Explanation:**

- `before` contains only `n1` for tenant `acme`; `n2` belonging to tenant `other` does not appear.
- `otherTenant=false` demonstrates that looking up ID `n2` neither leaks content nor confirms whether the ID exists in another tenant.
- A whitespace-only text is rejected before creating data and does not consume the write budget.
- `created=n3` and `after` confirm a valid write is bound to the current tenant.
- Once the single write allowance is exhausted, the subsequent call is rejected.

**Boundaries of the example:** data lives in an `ArrayList`, the simulation runs single-threaded, and the quota is an integer inside the instance. This is **not** a production repository, authorization framework, or sandbox. In a multi-threaded or multi-instance system, access permissions, IDs, write counts, and quotas must be enforced **atomically** in transactions/stores/gateways; do not grant permissions via local variables that could be cloned or reused outside a run.

**Important:** even when exposing an object strictly typed as `NotesRead` to a script engine, that **does not guarantee** the engine cannot introspect the implementation class, invoke `getClass()`, or leverage other Java interop features. Narrowing Java interfaces defines the approved API; defending against malicious scripts requires controlling host invocation mechanisms and execution privileges at the engine/process layer.

## 5. Injecting Capabilities into Scripts via javax.script: Just a Binding Mechanism

`javax.script` (JSR 223, `java.scripting` module) provides `ScriptEngine`, `ScriptEngineManager`, and `Bindings`. This mechanism lets an application pass values into a scripting environment, but **does not inherently provide a sandbox**.

The following is an **illustrative snippet inside a method** with `engine`, `scriptSource`, `notesRead`, `notesWrite`, and `canWrite` already supplied by the host:

```java
Bindings bindings = engine.createBindings();
bindings.put("notesRead", notesRead);

if (canWrite) {
    bindings.put("notesWrite", notesWrite);
}

Object result = engine.eval(scriptSource, bindings);
```

To use it, import `javax.script.Bindings`, `javax.script.ScriptEngine`, and `javax.script.ScriptException`, and select/initialize a suitable engine. This is an **example for trusted scripts with a separately configured and audited engine**, not a defense for untrusted scripts.

### 5.1. Important Notes on Engines and Java 17

- **JDK 17 no longer bundles the Nashorn JavaScript engine** (Nashorn was removed from the JDK in version 15). Thus `new ScriptEngineManager().getEngineByName("JavaScript")` can return `null` unless the application places a compatible script engine on the classpath or module path.
- JSR 223 is an integration API; rules for host access, class lookup, reflection, thread behavior, timeouts, and available builtins **depend on the specific engine** and cannot be inferred from `Bindings` alone.
- If using an external engine (e.g., a JSR 223-compatible JS engine or another scripting runtime), read the documentation for that **exact engine and version** and configure host access with an allowlist. Never assume every engine honors Java interfaces as permission boundaries.
- `engine.createBindings()` creates a binding map for a single evaluation, yet **global bindings, objects retained by the engine, libraries/extensions, and reused engine memory** can still undermine isolation. Never reuse an engine or context across different tenants without explicit isolation guarantees.
- `engine.eval(...)` can throw `ScriptException`; a script can also trigger runtime errors from the Java capabilities it calls. Distinguish script errors from `PERMISSION_DENIED` or infrastructure failures.

A snippet to check engine availability **without executing a script**:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");

if (engine == null) {
    throw new IllegalStateException("SCRIPT_ENGINE_UNAVAILABLE");
}
```

This is an illustrative snippet requiring imports for `javax.script.ScriptEngine` and `javax.script.ScriptEngineManager`. **Do not automatically install/download engines** at request time to recover from errors; engines and dependencies must be managed, verified, and deployed through a trusted pipeline.

### 5.2. For Untrusted Scripts: Send Commands Instead of Java Objects

A stronger defensive architecture:

```text
Untrusted client / script
             |
             v
      Sandbox process
 (no host Java classpath,
  no secrets, restricted network/FS)
             |
             | JSON/IPC: op + arguments
             v
      Host capability gateway
    - authenticate caller/run/tenant
    - allowlist operation
    - validate input and quota
    - enforce ACL/row-level scope
    - audit and cap output
             |
             v
        Java business logic
             |
             v
       Filtered DTO
```

Example request protocol:

```json
{"op":"notes.list","args":{"limit":3}}
```

or:

```json
{"op":"notes.add","args":{"text":"Hello team"}}
```

These are **protocol payload examples**, not live network requests in the demo program. The gateway accepts only registered `op` names. It has **no** arbitrary `className`, `methodName`, `javaExpression`, or `url` letting the script ask the host to run reflection or read arbitrary resources.

Tenant/actor permissions are bound to an authenticated identity on the IPC channel/session/scoped token controlled by the **host**, never trusting a self-asserted `tenantId` field in JSON. For data changes with side effects, use operation IDs/idempotency keys and appropriate audit logs. Avoid returning raw stack traces or internal details across the gateway.

## 6. Closing Privilege-Escalation Paths Through Parameters, Return Values, and Errors

### 6.1. Validate Parameters on Every Call

An API following least privilege never accepts overly generic parameters. For example:

- Replace `readFile(String path)` with `readApprovedTemplate(TemplateId id)`; the host maps the ID to a registered template.
- Replace `httpGet(String arbitraryUrl)` with `fetchExchangeRate(CurrencyCode code)` targeting a fixed endpoint.
- Replace `runSql(String sql)` with `getSalesTotal(ReportScope scope)` with built-in authorization checks.
- Replace `sendEmail(String to, String body)` with `requestApprovedNotification(RecipientId id, TemplateId template, Variables vars)` with delivery scope and rate limits.
- Replace `queryUsers(String tenant)` with `listVisibleUsers(int limit)`, deriving tenant/actor from the server-side context.

Validators must verify format/length/range/enums and business preconditions. For resource names, avoid concatenating script strings into paths, URLs, or query statements. Validate against an **allowlist** after appropriate normalization; treat escaping/parameterized queries as a defense-in-depth layer, not a replacement for authorization.

### 6.2. Do Not Return Privileged Objects

Even when an API exposes only a single read method, the return type can expand what the script can actually do:

| Return Type | Problem | Better Alternative |
|---|---|---|
| `DataSource` / `Connection` | Full query power or unintended transactions | Computed metrics or DTOs |
| ORM entity with lazy references | Can expose object graphs and trigger hidden queries | Immutable record/projection |
| `InputStream` / `Path` / `File` | I/O lifecycle issues and filesystem disclosure | Size-bounded bytes/strings or vetted IDs |
| `HttpClient` / client SDK | Enables calling arbitrary endpoints | Business method using a fixed endpoint |
| `Class` / `ClassLoader` | Opens reflection/class-lookup mechanisms | Never return host runtime internals |
| Full `Throwable` | May contain stack traces, paths, sensitive details | Normalized error: code, safe message, correlation ID |

Even "harmless" DTOs are still Java objects if the engine allows host interop. Engine restrictions must be configured and tested independently; if isolation cannot be trusted, **communicate over JSON/IPC** with simple data types.

### 6.3. Do Not Leak Tenant Existence via Responses

When looking up an out-of-scope ID, returning distinct errors for "ID exists but unauthorized" versus "ID does not exist" can be abused to probe data. Many APIs should return the same `NOT_FOUND` for both cases while internal audit logs record the real reason. Exact behavior depends on product contracts, but never let scripts query a wide data namespace and filter on the client side.

### 6.4. Handling Side Effects and Retries

A `notes.add` command may succeed on the server while the IPC transport times out. If the script retries indefinitely, duplicate notes may be created. For operations with side effects, address:

- Idempotency keys attached or accepted by the host per authenticated run/request.
- Limits on retry counts, deadlines, and ambiguous states.
- Transactions/unique constraints or appropriate deduplication.
- Preventing scripts from changing principal/tenant across retries.
- Consistent budget accounting: per request, per successful task, or per committed side effect.

## 7. Quotas, Time, Concurrency, and Lifecycle

Even a narrow API can be abused by calling it in a tight loop or requesting excessive data. Enforce limits **both inside the capability and in the execution environment**.

| Risk | Enforcement Point |
|---|---|
| `list(1_000_000)` | Cap `limit` in the API and DB query; paginated access with a maximum page size |
| Calling `add` thousands of times | Quotas at the gateway/store and per-actor/tenant rate limiters |
| Infinite loop in script | Deadline in the sandbox process; CPU limits and ability to terminate the process |
| Allocating huge objects | Memory and output-byte limits at the process/IPC boundary |
| Arbitrary network access | Network policy/egress allowlist in the sandbox; never inject an HTTP client |
| Retaining a capability after session end | Run-scoped lifetime; check expiry/revocation on every call |
| Parallel script races | Concurrency-safe quotas, transactions, and counters in storage/gateway |
| Secrets in logs | Redaction, field allowlists, and retention policies |

**Do not rely on `Future.cancel(true)` or `Thread.interrupt()` as a way to "kill" malicious scripts.** Interrupts are cooperative; CPU-bound code can ignore them, and Java threads inside the same JVM are not a hard resource boundary. When untrusted code must be stopped, use **process isolation and host/OS-enforced timeouts** with post-termination cleanup policies.

**Do not accidentally share facades/state across runs.** A `NotesRead` bound to tenant A must never be stored as a global object and reused by tenant B's script. Instantiate capabilities per run, and verify that instances, caches, and thread-locals do not leak data or permissions when pooling engines or workers.

## 8. Per-Operation Authorization and Auditing

Recommended flow for a capability call:

```text
script asks notes.add("Beta")
             |
             v
[1] Run still valid? actor/tenant authenticated?
             |
             v
[2] Is operation notes.add granted?
             |
             v
[3] Validate text + size + schema
             |
             v
[4] Enforce scope, quota, deadline
             |
             v
[5] Execute via service/repository with transaction
             |
             v
[6] Audit + return DTO / safe error code
```

A system can record the following fields server-side:

```json
{
  "runId": "run-42",
  "scriptId": "invoice-rule-v3",
  "operation": "notes.add",
  "tenant": "acme",
  "decision": "DENIED",
  "reason": "WRITE_BUDGET_EXCEEDED",
  "durationMs": 2
}
```

This is only a sample log; **you do not need to store note contents, SQL, tokens, or stack traces** to record an authorization decision. `runId` and `scriptId` should come from host orchestration rather than self-declared script fields when logs are used for auditing.

Errors returned to scripts should follow an explicit contract:

| Error Code | Meaning | Script Reaction |
|---|---|---|
| `OPERATION_NOT_GRANTED` | Script/run is not permitted to call the capability | Stop or request permission configuration; do not retry |
| `VALIDATION_FAILED` | Invalid input type, length, or format | Fix parameters |
| `NOT_FOUND` | Resource does not exist within the accessible scope | Do not probe IDs in other tenants |
| `QUOTA_EXCEEDED` | Exceeded per-run or tenant-wide limit | Stop; wait for a new run if policy allows |
| `RUN_EXPIRED` | Execution context expired or was revoked | Stop using the capability |
| `OPERATION_CONFLICT` | Idempotency/transaction conflict | Follow business policy |
| `SCRIPT_ENGINE_UNAVAILABLE` | Engine does not exist or is disallowed | Deployment error; do not swap engines arbitrarily |
| `SCRIPT_EXECUTION_FAILED` | Script failed during execution | Record correlation ID; do not leak host details |

If permission is missing, **fail closed**—never auto-create a higher-privilege writer or fall back to admin credentials to "help the script finish."

## 9. Testing APIs and Security Boundaries

There are two **distinct** test groups: testing whether the Java facade enforces business rules, and testing whether the engine/sandbox allows bypassing the facade.

| Test Scenario | Expected Outcome |
|---|---|
| Tenant A's reader calls `list(5)` | Sees only Tenant A's notes |
| Reader A looks up Tenant B's ID | Returns no content from B; typically `NOT_FOUND` |
| Read-only script tries to call a write operation | Operation is absent from granted capabilities or rejected by gateway |
| Passing `list(0)`, `list(-1)`, or `list(1000)` | Rejected by parameter bounds |
| `add(null)`, blank string, oversized content | Rejected by validation |
| Calling `add` beyond budget | Rejected with no additional side effects |
| Attempting to pass another tenant in the request | Tenant is host-determined and cannot be altered by script input |
| Script retained after the run expires | Capability can no longer execute |
| Engine with reflection/Java class access | Test to verify host access policy truly blocks it; otherwise reject untrusted scripts |
| Reusing an engine from a pool for another tenant | No leftover bindings, globals, or capabilities from the previous tenant |
| Script enters an infinite loop | Sandbox is terminated at deadline without hanging the host |
| Two concurrent write requests | Quotas, IDs, and transactions do not race or duplicate side effects |
| Script tries to read unauthorized files or internal URLs | Blocked by OS/network sandbox and gateway |
| Service error contains paths/secrets in exception | Script receives a safe error code; server logs are redacted |
| Script spoofs `runId`/`tenantId` in JSON | Host ignores or rejects it without elevating privileges |
| ScriptEngine missing in JDK | Deterministic error; never falls back to an engine outside the allowlist |

Unit tests can use fake implementations like `Store` in the Java example; integration tests must run on the **exact engine**, exact dependencies, exact host access config, and deployment environment. Never treat tests passing through the facade as proof that bypassing via reflection is impossible.

## 10. Common Design Mistakes

1. **Injecting `ApplicationContext` or a service container into scripts.** That usually grants far more privilege than business needs require.
2. **Using a single large interface with an `isAdmin` flag.** Separating read/write capabilities and scoping permissions per run is far easier to review and test.
3. **Letting scripts pass `tenantId`, `userId`, or connection strings.** Authorization-determining values must originate from the trusted host context.
4. **Returning ORM entities, `Path`, `File`, `Connection`, or `ClassLoader`.** Returned objects can carry broader functionality and metadata than intended.
5. **Believing `Bindings.put("api", facade)` is a sandbox.** Script engines may still allow Java interop, global bindings, and other access paths.
6. **Assuming Java 17 always includes a JavaScript engine.** JDK 17 no longer bundles Nashorn by default; compatible engines must be managed explicitly.
7. **Blocking class loading with a simple class loader and thinking malicious code is isolated.** ClassLoader/JPMS does not automatically restrict network, file, and CPU access for code in the same JVM.
8. **Limiting methods without limiting call counts.** Even `list(1)` can be called endlessly; enforce budgets, deadlines, and rate limits.
9. **Checking permissions only when creating the facade.** Permissions can expire, be revoked, or race; enforce on every critical operation/transaction.
10. **Validating inputs only in the UI.** Scripts can call host APIs directly; validation must live on the Java/gateway side.
11. **Fixing script errors by blindly retrying side-effecting operations.** A timeout does not prove the server never committed; use idempotency.
12. **Using `Thread.interrupt()` as a security boundary.** Insufficient for uncooperative code; use process isolation and OS quotas.
13. **Sharing the same script engine/context across multiple tenants without checking for state leaks.** Bindings or global objects from prior runs may linger.
14. **Including stack traces or secrets in returned error messages.** Return error codes and correlation IDs; keep sensitive details in controlled logs only.

## 11. Checklist Before Exposing an API to Scripts

- **Trust model:** is the script internal and reviewed, partially trusted from a partner, or untrusted user code?
- **Operation list:** expose only required business verbs; never provide reflection or arbitrary SQL, file, or HTTP access.
- **Permission source:** the host determines actor, tenant, and grants; scripts cannot self-declare identity.
- **Inputs:** schemas, types, length limits, filters, and allowlists are enforced host-side.
- **Outputs:** small, immutable DTOs containing no privileged host objects or out-of-scope data.
- **Per-call authorization:** enforce grants, tenant, expiration, quotas, and transactions on every operation.
- **Execution state:** capabilities are never reused across wrong tenants/runs; watch out for engine pooling and globals.
- **Side-effect semantics:** auditing, idempotency, retries, conflicts, and rollbacks have explicit policies.
- **Engine:** version, JS/DSL semantics, and host interop are evaluated and configuration-locked.
- **Isolation:** if scripts are untrusted, use process/OS sandboxing restricting network, files, secrets, CPU, and RAM.
- **Observability:** log allow/deny decisions, error codes, latency, and run IDs; do not log sensitive payloads.
- **Privilege-escalation testing:** run negative tests where scripts attempt to access ungranted objects/operations, not just happy paths.

### Reference API Documentation (Java SE 17)

- [ScriptEngine — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [ScriptEngineManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [Bindings — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html)
- [ScriptException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html)

**Conclusion:** designing a Java API for scripts with **least privilege** means each script receives only the capabilities needed for the exact user/tenant, within the exact timeframe and quota; Java methods validate inputs, authorization scope, and impact themselves. **A minimal facade helps control business logic, but is not a standalone security boundary**: for untrusted scripts, combine secure engine configuration with process/OS-level isolation and an authenticating, per-operation gateway.