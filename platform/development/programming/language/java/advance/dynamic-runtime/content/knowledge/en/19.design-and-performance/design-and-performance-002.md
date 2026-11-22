# 19.2 Separating Discovery and Validation from the Repeated Execution Path

In a Java runtime, a system using Reflection, `MethodHandle`, `VarHandle`, annotations, or plugins often has to execute an operation many thousands of times, while the **method name, signature, metadata, and mapping policy** rarely change between requests. If every execution scans annotations, looks up the member again, checks modifiers, builds a `MethodType`, and selects an adapter, we are repeating work that only depends on the **program structure**.

The solution is to clearly separate:

> **Discovery → stable contract validation → preparation (link/prepare) → plan publication (publish) → repeated execution (execute).**

The result of the preparation phase is usually an **immutable execution plan**: an object containing the selected `MethodHandle`, converters, descriptors, and validated metadata. The hot path receives the request data, checks the conditions that **actually vary per request**, and then uses the prepared plan.

This helps detect configuration errors early, reduces repeated work, and clarifies access permissions. However, **there is no fixed guarantee that MethodHandle is faster than every Reflection approach**; the cost must be measured with the specific JDK, CPU, and workload. This is a Knowledge article for topic **19. Design and Performance** on Java 17+, with two complete programs that have been compiled and output-verified.

## 1. Distinguishing preparation cost from execution cost

| Activity | Example | When performed? |
| --- | --- | --- |
| Structure discovery | `getDeclaredMethods()`, reading annotations, finding getters, traversing fields and record components | When creating descriptor/plan or when schema changes |
| Stable contract validation | Correct owner, name, overload, static/instance, parameter types, return type, modifier, access permissions | Before publishing the plan |
| Call path preparation | `Lookup.unreflect`, `findVirtual`, `findStatic`, `asType`, `permuteArguments`, attaching converters | Once per appropriate key/version |
| Publication and caching | `ClassValue`, `ConcurrentHashMap`, immutable registry, `AtomicReference` | When the plan is valid and ready |
| Execution | Input validation, current authorization, decode, `invokeExact`, serialize result, target exception | Every required request |

“Validate once” should not be understood as skipping all checks on the hot path. **Validation has two layers**:

- **Structurally stable**: unique `total` route, method takes two `int`s and returns `int`, Lookup has access, schema has valid converters. These can be moved to the `prepare` step.
- **Request-variant**: negative amounts, revoked user permissions, expired tokens, null current object, transaction limits, mutable state, and oversized payloads. **Must still be checked on every call** or according to a valid state protocol.

In a secure system, reusing a plan **does not mean reusing the previous user's authorization result**.

### 1.1. A verifiable two-phase architecture

```text
MODULE / SCHEMA / ROUTE DEFINITION
                |
        [ DISCOVER METADATA ]
                |
        [ VALIDATE CONTRACT ]
                |
        [ BUILD TYPED HANDLES ]
                |
        [ IMMUTABLE PLAN ]
                |
        [ SAFE PUBLICATION ]
                |
        +-------+-------+--------+
        |       |       |        |
      Req1    Req2    Req3     ReqN
        |       |       |        |
     validate current data / current permission
        |       |       |        |
        +---- plan.execute(...) ----+
                       |
                   target logic
```

The prepare phase can happen at startup, when opening a plugin, on a cache miss with an appropriate key, or when loading a new revision. It is not necessary to prepare **every** route at startup if only a small subset is used. What matters is that **every repeated execution does not needlessly redo discovery from scratch**.

## 2. Anti-pattern: looking up the member on every request

Consider a `Checkout` service with an instance method `int total(int units,int unitPrice)`. A dispatcher might write:

```java
static int callEveryTime(Object service, int units, int unitPrice)
        throws ReflectiveOperationException {
    Method member = service.getClass().getDeclaredMethod(
            "total", int.class, int.class);
    Object value = member.invoke(service, units, unitPrice);
    return (Integer) value;
}
```

This is an **illustrative method**, requiring `import java.lang.reflect.Method`, and is not a standalone program.

On every call, this code looks up the method by name again, goes through the Reflection path with `Object`/boxing, and may encounter configuration errors right in the middle of handling a request. If the system also has to read annotations, find converters, or select overloads, even more work is repeated. Exceptions thrown by the target via `Method.invoke` are wrapped in `InvocationTargetException`, which also needs separate handling.

**Do not automatically conclude that `getDeclaredMethod` is “always very slow”.** The JVM has caches/JIT; Reflection on Java 18+ is also reimplemented on top of MethodHandle per JEP 416. What can be stated with certainty about the design is that **the system is requiring the discovery step to be redone on every call**, even though the member/metadata remains the same.

### 2.1. Three levels of improvement

1. **Least change:** look up `Method` once, keep it in the plan, and continue using `Method.invoke`. Repeated discovery is eliminated.
2. **Stronger typing:** from the validated `Method`, call `Lookup.unreflect(method)` or `findVirtual` once; store the `MethodHandle` and use `invokeExact` on the typed call path.
3. **Need a pipeline:** pre-build converters, validators, selectors, and method-handle adapters into a single plan, reusing the entire chain for many requests.

Level 3 should only be done if complexity and workload justify it. A direct Java call with available static types is sometimes better than building a dynamic dispatcher.

## 3. Result of preparation: an execution plan with a clear contract

A published plan should satisfy:

- **Correct target selected**: method name, signature, overload, receiver, static/instance, and declaring class are clear.
- **Access permissions validly granted**: does not rely on arbitrary `setAccessible(true)`; uses a `Lookup` appropriate for the caller/module.
- **`MethodType` matched**: parameter types list and return type are exact; for an instance method, the receiver is the first parameter.
- **Adapters fixed**: if `asType`, `bindTo`, `insertArguments`, or `permuteArguments` are needed, prepare them before publishing.
- **Structurally immutable**: the plan holds target, revision, converters, and metadata of the same version; do not mutate those fields piecemeal.
- **Runtime data still validated**: a correctly typed plan must still reject bad input and invalid authorization.
- **Has a lifecycle**: tied to schema/classloader/generation, with an invalidation policy when code or policy changes.

In particular, **a `MethodHandle` does not contain all input values**. It contains the binding to the computation; the runtime still has to supply the receiver and the request arguments. If a receiver is bound into the handle, the plan becomes tied to **one specific instance**, which can be wrong when requests need a different receiver.

### 3.1. Errors should surface early

Suppose the router configures `route="total"` and requires type `(Checkout,int,int)int`, but the implementation changed to `total(String)`. That is a **configuration/schema error** and should fail during plan initialization. If the builder silently ignores the error and waits for the first real request to make a bad call, a design error gets mixed up with a user data error.

If **lazy** preparation is allowed, successful results must be cached and error/retry policies managed. Each request should not independently retry a failing discovery without limits or diagnostics.

## 4. Complete Java 17+ example: scan annotations once, invokeExact many times

This program uses Reflection **for discovery**, verifies the member, and then creates a `MethodHandle`. `Plan.execute` does not scan annotations and does not look up method names. The `SCANS` counter illustrates the separation; it is **not a timing benchmark**.

Create file **`PreparedDispatchDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.invoke.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class PreparedDispatchDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Route { String value(); }

    public static final class Checkout {
        @Route("total")
        public int total(int units, int unitPrice) { return units * unitPrice; }
        @Route("info")
        public String info(String item) { return "item=" + item; }
    }

    private static final AtomicInteger SCANS = new AtomicInteger();
    private static final MethodType EXPECTED = MethodType.methodType(
            int.class, Checkout.class, int.class, int.class);

    record Plan(String route, MethodHandle handle) {
        Plan {
            if (!handle.type().equals(EXPECTED))
                throw new IllegalArgumentException("wrong handle type");
        }
        int execute(Checkout service, int units, int unitPrice) throws Throwable {
            if (service == null || units < 0 || unitPrice < 0)
                throw new IllegalArgumentException("invalid request");
            return (int) handle.invokeExact(service, units, unitPrice);
        }
    }

    static Plan prepare(String route) throws IllegalAccessException {
        SCANS.incrementAndGet();
        List<Method> methods = Arrays.stream(Checkout.class.getDeclaredMethods())
                .filter(m -> {
                    Route annotation = m.getAnnotation(Route.class);
                    return annotation != null && annotation.value().equals(route);
                }).toList();
        if (methods.size() != 1)
            throw new IllegalArgumentException("route must be unique");
        Method method = methods.get(0);
        if (!Modifier.isPublic(method.getModifiers())
                || Modifier.isStatic(method.getModifiers())
                || method.getReturnType() != int.class
                || !Arrays.equals(method.getParameterTypes(),
                        new Class<?>[] { int.class, int.class }))
            throw new IllegalArgumentException("unsupported signature");
        MethodHandle handle = MethodHandles.lookup().unreflect(method);
        return new Plan(route, handle);
    }

    public static void main(String[] args) throws Throwable {
        Checkout service = new Checkout();
        Plan plan = prepare("total");
        System.out.println("planType=" + plan.handle().type());
        System.out.println("call1=" + plan.execute(service, 2, 5));
        System.out.println("call2=" + plan.execute(service, 3, 7));
        System.out.println("scans=" + SCANS.get());
        try {
            prepare("info");
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getClass().getSimpleName());
        }
        System.out.println("scansAfterRejected=" + SCANS.get());
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac --release 17 PreparedDispatchDemo.java
java PreparedDispatchDemo
```

Verified `stdout` output:

```text
planType=(Checkout,int,int)int
call1=10
call2=21
scans=1
rejected=IllegalArgumentException
scansAfterRejected=2
```

### 4.1. Steps belonging only to prepare

`prepare("total")`:

1. Calls `Checkout.class.getDeclaredMethods()`.
2. Reads `@Route` and selects **exactly one** matching method; does not rely on Reflection array ordering.
3. Checks that the method is public, non-static, returns `int`, and takes two `int`s; routes with other signatures are rejected.
4. Calls `MethodHandles.lookup().unreflect(method)` to create a capability with valid access.
5. Uses the `Plan` record to confirm `handle.type()` is `(Checkout,int,int)int`.

`Checkout.total` is an instance method, so the `Checkout` receiver is the **first parameter** of the handle. If the method were static, the handle would have **no** receiver. When supporting overloads, a clear key including name, parameter types, return type, and policy is needed; `getDeclaredMethods()` does not guarantee order and may contain synthetic/bridge methods.

### 4.2. Steps still belonging to execute

`execute` checks that service is non-null, and units and unitPrice are non-negative, then calls:

```java
return (int) handle.invokeExact(service, units, unitPrice);
```

The return value is a primitive `int`; no annotation scanning, no `MethodType` creation, and no overload lookup again. Two calls to `execute` leave `SCANS` at **1**. Afterward, the program tries `prepare("info")` once more, scans and rejects the `(String)String` signature, so `scansAfterRejected=2` — **not** because the two execute calls scanned.

The example simplifies the router: it only supports a single contract. A production router with diverse types can return a plan per route/signature. The main point is that **each plan is only bound to its verified contract**, not that all routes have the same type.

### 4.3. Why does `handle.type()` matter?

`MethodType` represents the JVM signature of the handle. Type `(Checkout,int,int)int` differs from `(Object,int,int)Object` even though Java can cast/box at the boundary. If the caller writes:

```java
Object result = handle.invokeExact(service, units, unitPrice);
```

then the call site expects return type `Object`, **which does not match `int`**, leading to `WrongMethodTypeException`. This is an illustrative snippet depending on the existing variables `handle`, `service`, `units`, and `unitPrice`; it is not a standalone program.

If an adapter accepting `Object` is needed, you can create `handle.asType(...)` properly **once during preparation**. However, boxing, casts, and runtime checks may still occur; creating an adapter does not make every conversion free.

## 5. Reducing repeated adaptations

`MethodHandle` has combinators/adapters. When the mapping layout is fixed, they should be prepared in the same place as the lookup.

| Need | API | Done before hot path |
| --- | --- | --- |
| Select method | `findVirtual` / `findStatic` / `unreflect` | Find target and check access |
| Select field | `findGetter`, `unreflectGetter`, `VarHandle` | Select field, static/final kind, mode |
| Match target API type | `asType`, `explicitCastArguments` | Design conversion per contract |
| Reorder or repeat arguments | `permuteArguments` | Build mapping index table once |
| Bind fixed argument/config | `bindTo`, `insertArguments` | Avoid supplying the same value on every request |
| Filter inputs | `filterArguments` | Attach converter/normalizer |
| Filter result | `filterReturnValue` | Attach result mapper |
| Emulate Object[] call | `asSpreader`, `invokeWithArguments` | Use only when a dynamic interface is truly needed |

For example, given a typed `handle` as in `PreparedDispatchDemo`, if the runtime API only passes `Object` values, a pre-built adapter can be:

```java
MethodHandle generic = handle.asType(
        MethodType.methodType(Object.class,
                Object.class, Object.class, Object.class));
```

This snippet illustrates the API and requires a prepared `handle`. `generic` has type `(Object,Object,Object)Object`; at runtime it casts the receiver, unboxes two integers, and boxes the result. This is not proof that it is faster than the typed version; if source data is already primitive, keeping typed `invokeExact` can avoid those conversions.

**Do not recreate the adapter on every request just because the same `MethodType` is needed**, nor apply an overly broad adapter to invalid type mismatches. Prepare and validate conversions before publishing.

## 6. Caching must be based on the right identity and version

The phrase “cache MethodHandle” often hides a more important question: **what unit can safely share the exact same plan?**

| Reuse unit | Usually required key | Risk if missing |
| --- | --- | --- |
| Route in a module | `moduleRevision + routeId + signature` | Old route used after reload |
| Runtime type | `Class<?> + method descriptor` | Two class loaders with the same binary name get mixed |
| Schema/serializer | `Class<?> + schemaVersion + converterPolicy` | Field mapping from wrong generation |
| Tenant/policy | `tenantPolicyVersion + operation` | Mixing tenant permissions or converters |
| Plugin generation | `generationId + Class<?> + MethodType` | Cache retains old MethodHandle/loader |
| Immutable per-class metadata | `ClassValue<Descriptor>` | Cannot see changes outside the class |

Class identity in the JVM **is not just a string name**. Two versions of `pkg.Service` defined by two different defining class loaders are **two different `Class<?>` instances**. A `MethodHandle` from v1 cannot be arbitrarily substituted with a v2 handle just because the class name is the same. An unbounded static cache can also keep old method handles, classes, and classloaders alive longer than expected.

### 6.1. `ClassValue` and compute races

When metadata depends only on `Class<?>`, `ClassValue<T>` is designed for associating computed values with a class:

```java
static final ClassValue<List<String>> METHODS = new ClassValue<>() {
    @Override protected List<String> computeValue(Class<?> type) {
        return Arrays.stream(type.getDeclaredMethods())
                .map(Method::getName).sorted().toList();
    }
};
// When needed: List<String> names = METHODS.get(actualClass);
```

This is an **illustrative snippet**, requiring imports for `List`, `Arrays`, and `Method`; it is not a standalone Java file. It caches associations by class, not by text name.

An important technical point in the Java 17 documentation: if multiple threads call `get(type)` concurrently for the first time, **`computeValue` may be invoked concurrently by competing threads**. One value is atomically installed for the association; extra computed values are not necessarily used. `remove` can also trigger recomputation. Therefore, the mapping function should be **pure/idempotent**, and must not directly send emails, process payments, or register resources that may only happen once.

`ClassValue` helps tie the cache to class identity, but **does not automatically clear** external references such as static maps, threads, or loader references. Managing the full plugin lifecycle is still necessary.

### 6.2. `ConcurrentHashMap.computeIfAbsent`

For caching by a composite key:

```java
record Key(Class<?> owner, String route, MethodType type, long revision) {}

ConcurrentHashMap<Key, ExecutionPlan> cache = new ConcurrentHashMap<>();
// Illustrative skeleton: cache.computeIfAbsent(key, k -> buildValidatedPlan(k));
```

This snippet illustrates the structure and requires an `ExecutionPlan` class and `buildValidatedPlan` to be defined; it is not a standalone program. In real code, the value should be immutable and only published after building succeeds.

`computeIfAbsent` coordinates installing the result for the same key, but the mapping function must not recursively modify the map, should be concise, and if it throws an exception, no association is installed so subsequent requests can retry. If building is very expensive or requires timeout/cancellation, consider a per-key coordinator with `CompletableFuture<Plan>` and an error/retry policy.

**Do not equate “mapping is installed once” with “external side effects are executed exactly-once”** in the presence of exceptions, crashes/restarts, or multiple processes.

### 6.3. Invalidation and negative caching

- When the schema changes, an old plan **is not automatically re-validated**. Include the revision in the key or publish a new generation.
- When a route does not exist, you can **negative-cache configuration errors** with a TTL/revision if the contract allows; do not cache failures permanently when plugins can be updated.
- When a module is unloaded, release references to `Class<?>`/`MethodHandle`/converters and shut down in-flight tasks properly.
- If authorization depends on the current user, **do not** cache “user A is allowed” as static per-method metadata.
- Bound the cache capacity; a metadata key with too many fields and millions of class loaders can turn a CPU optimization into a heap/metaspace risk.

## 7. Publish a plan snapshot, do not mutate individual fields separately

Separating preparation from execution is especially important when the system **reloads configuration or code** while serving many requests.

Anti-pattern:

```java
// Two volatile fields updated separately: does not form a single transaction.
volatile MethodHandle activeHandle;
volatile String activeRevision;

// Writer
activeHandle = newHandle;
activeRevision = "v2";

// Reader
MethodHandle h = activeHandle;
String rev = activeRevision; // May receive two different versions.
```

The snippet above is illustrative only, not a standalone Java file. A reader can observe `activeHandle` from v2 and `activeRevision` from v1 due to interleaving. If the plan has many converter/schema fields, the risk of “half v1, half v2” becomes even more severe.

Solution: **bundle all validated metadata and handles into a single immutable object**, then publish **one reference** via `AtomicReference` or a volatile field. Readers grab **a single snapshot** for the entire call.

## 8. Complete Java 17+ example: switching v1→v2 with AtomicReference

Create file **`VersionedPlanDemo.java`**:

```java
import java.lang.invoke.*;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

public class VersionedPlanDemo {
    public static String oldLogic(String text) {
        return "v1:" + text.toUpperCase(Locale.ROOT);
    }
    public static String newLogic(String text) {
        return "v2:" + text.toLowerCase(Locale.ROOT);
    }
    record Plan(String revision, MethodHandle handle) {
        Plan {
            MethodType expected = MethodType.methodType(String.class, String.class);
            if (!handle.type().equals(expected))
                throw new IllegalArgumentException("wrong type");
        }
        String run(String text) throws Throwable {
            if (text == null) throw new IllegalArgumentException("null text");
            return (String) handle.invokeExact(text);
        }
    }
    static Plan prepare(String revision) throws ReflectiveOperationException {
        String member = switch (revision) {
            case "v1" -> "oldLogic";
            case "v2" -> "newLogic";
            default -> throw new IllegalArgumentException("unknown revision");
        };
        MethodHandle target = MethodHandles.lookup().findStatic(
                VersionedPlanDemo.class, member,
                MethodType.methodType(String.class, String.class));
        return new Plan(revision, target);
    }
    static final class Router {
        private final AtomicReference<Plan> current;
        Router(Plan initial) { current = new AtomicReference<>(initial); }
        String call(String input) throws Throwable {
            Plan snapshot = current.get();
            return snapshot.run(input);
        }
        Plan snapshot() { return current.get(); }
        void publish(Plan ready) { current.set(ready); }
    }
    public static void main(String[] args) throws Throwable {
        Router router = new Router(prepare("v1"));
        Plan previous = router.snapshot();
        System.out.println("before=" + router.call("MiXeD"));
        router.publish(prepare("v2"));
        System.out.println("after=" + router.call("MiXeD"));
        System.out.println("oldSnapshot=" + previous.run("MiXeD"));
        System.out.println("currentRevision=" + router.snapshot().revision());
        System.out.println("type=" + router.snapshot().handle().type());
    }
}
```

Compile and run:

```bash
javac --release 17 VersionedPlanDemo.java
java VersionedPlanDemo
```

Exact `stdout` output:

```text
before=v1:MIXED
after=v2:mixed
oldSnapshot=v1:MIXED
currentRevision=v2
type=(String)String
```

**Explanation:**

1. `prepare("v1")` selects the method from a **whitelisted** set of names (does not take arbitrary names from the user), creates a `(String)String` handle, and checks the type before publishing.
2. Each `Router.call` reads `current.get()` **once**, using the plan snapshot; it does not look up the method again on every request.
3. The writer builds and verifies **v2 before** calling `publish`. If `prepare` fails, v1 remains in use.
4. `AtomicReference.set` publishes the reference along with its initialized fields. Readers use a consistent revision+handle pair, rather than reading them from two separate volatile fields.
5. `previous.run` still executes according to v1 even though v2 is active; this allows requests that started before the reload to finish, provided the lifecycle permits it.
6. This single-threaded program illustrates the safe structure; a system with **multiple writers** also needs CAS, monotonically increasing revision checks, or a coordinator so v1 is not published after v2.

**Do not assume an immutable object cannot hold mutable state.** `MethodHandle` itself is immutable, but the target method may read static state, a mutable receiver, or external resources. A plan ensures metadata/handles are not mixed, **not** a replacement for synchronizing underlying business data.

### 8.1. The reload process should be explicit

```text
v1 ACTIVE
   |
   +-- prepare v2 off the hot path
   |      discover -> validate -> build adapters -> immutable plan
   |
   +-- atomic publish v2
   |      new requests use v2
   |      in-flight v1 requests may finish using old snapshot
   |
   +-- retire v1 after usage drains
          release handles, loaders, listeners and resources
```

When authorization is revoked, policy may require **blocking even in-flight v1**, depending on security requirements. Snapshotting to optimize method lookup is not a reason to defer business permission checks.

## 9. MethodHandle and access permissions: capabilities must be kept private

`Lookup` checks accessibility when creating a `MethodHandle`. Afterward, code holding the handle can invoke the underlying member using the granted capability without needing the original `Lookup`. This is a powerful and useful property for separating prepare from execute, but it is also a risk if the cache has no access policy.

- Trusted builders can use a privileged `Lookup` to find private members per module rules.
- Only expose handles/plans to callers allowed to use that operation.
- **Do not** put full-privilege `Lookup`s or private handles into a public registry that untrusted plugins can read.
- Runtime data still needs authorization; `hasFullPrivilegeAccess()` or a member access check does not prove the end user has business permission.
- If permissions change, invalidation/guards at the invoke point must protect appropriately. A plan must not turn into a “permanent ticket” bypassing revocation mechanisms.
- A handle from v1's class loader must not be placed into a v2 plan just because the class and method names look identical.

With `Method.invoke`, an exception thrown by the target method is wrapped in `InvocationTargetException`; with `MethodHandle.invokeExact`, exceptions from the target propagate directly. This should also be decided at the execute boundary rather than having each request guess which exception means “lookup failed”.

## 10. Applying to VarHandle, Reflection serializers, and runtime compilation

### 10.1. VarHandle and field mapping

A mapper/serializer can discover `Field` or `RecordComponent` and converters once, then build an immutable descriptor:

```text
Class<?> / schemaVersion
    |
    +-- inspect fields, types, annotations
    +-- validate ordering / accessibility / converters
    +-- create MethodHandle getters and/or VarHandles
    +-- descriptor = immutable array/list of accessors
                          |
                       request object
                          |
                validate values, read/write
                          |
                       output
```

If an object has 30 fields and is serialized a million times, you should not default to calling `getDeclaredFields` a million times. However, **caching a VarHandle does not make every access automatically synchronized**: `get`, `getAcquire`, `getVolatile`, and atomic access modes have different semantics. Choose the mode based on the Java Memory Model, not the desire for “fastest”.

For `final` fields, setters may be rejected; if data is immutable, initialize via constructor/factory instead of trying to mutate the field. For generic types, raw/erased `Class<?>` metadata is not enough to replace `Type` and annotations; converters must be verified against the schema.

### 10.2. invokedynamic and CallSite

`invokedynamic` already embodies the two-phase idea: the bootstrap creates a `CallSite` at link time, and subsequent calls go through the CallSite target. Separating discovery/bootstrap from repeated execution can reduce dispatch cost. However:

- Bootstrap may be run **concurrently** by the JVM during linking; do not place once-only side effects in bootstrap without an idempotent protocol.
- `MutableCallSite` can change its target after linking; switching targets requires an appropriate visibility/synchronization policy (e.g. `MutableCallSite.syncAll`).
- If using `VolatileCallSite`, observing the target has volatile semantics, but changing related classloaders/plans must be managed synchronously.
- A `CallSite` does not automatically check user authorization on every target invocation; the runtime boundary still needs that logic.

### 10.3. Dynamic compilation and generated class loaders

When a system generates bytecode using `JavaCompiler` or defines hidden classes, preparation can be very expensive: parsing source, compiling, verifying, loading, linking, and finding methods. Those steps should even more strictly be **separated from request execution**, preparing artifacts and plans per generation. A failure before publishing must not corrupt the currently active generation.

Note: class identity depends on the defining loader; hot reload should use a new **bundle + loader generation**. Do not try to redefine the same binary name in an already-used loader or replace `.class` files and expect the JVM to auto-update. Keep shared APIs in a parent loader if objects need to be passed between generations.

## 11. When is caching not worth it?

Separating phases does not mean creating every cache imaginable:

- The method is used only **once** and the existing code is simple enough.
- The lookup is already optimized by the JVM/JDK, and its cost is a tiny fraction of the total request.
- The set of classes/schemas is huge while most are never called, making preloading costly in startup time and memory.
- The key or policy changes on nearly every request, resulting in a very low cache hit rate.
- The cache extends the lifetime of class loaders, `MethodHandle`s, resources, or threads; memory/GC cost outweighs time saved.
- An `Object...` adapter causes significant boxing/spreading compared to a direct type-safe call.
- Using a generic dispatcher makes the code harder to debug than a statically typed Java call.

Whenever possible, a **direct Java call** remains the simple baseline to see whether a dynamic invocation mechanism is needed at all.

## 12. Cost model and how to measure properly

Notation:

- `D`: discovery + validation + preparing one plan.
- `L`: repeated discovery/validation cost per request if not separated.
- `E`: execution cost through an existing plan.
- `R`: invocation cost when looking up and calling every time.
- `N`: number of calls in the plan's lifetime.

First-order model:

```text
Without plan:    T_naive(N) ~ N * (L + R)
With plan:       T_ready(N) ~ D + N * E

Assumed benefit ~ N * (L + R - E) - D
```

If `N` is large, `L` is significant, and `E` is reasonable, amortization can pay off. If `N` is small or setup/cache misses are frequent, it is uncertain. In practice, one must also include cache lookup cost, allocation, locks, JIT warmup, GC, class loader retention, and tail latency.

**Do not state numbers like “10x faster” without benchmarking.** Both Reflection and MethodHandle have many optimizations depending on the JDK version. JEP 416 replaced the Core Reflection implementation starting in JDK 18, so results on JDK 17 do not automatically carry over to JDK 21/26.

### 12.1. Three different measurements

1. **Cold path**: time to create the plan, scan annotations, check signatures, load classes, build adapters, and memory growth.
2. **Steady-state invoke-only**: with a cached plan/Method already ready, feed varying inputs, consume outputs, and measure allocation/throughput/latency. This measures only the invocation part.
3. **End-to-end request**: route selection, cache access, current data validation, invoke, output. Measure p50/p95/p99 and GC under a production-like workload.

JMH is the right tool for JVM microbenchmarks thanks to warmup, forks, and result handling. For production load, profiling/tracing and whole-system benchmarks are also needed.

| Benchmark mistake | Why it misleads |
| --- | --- |
| Putting `getDeclaredMethod` in every Reflection iteration without equivalent setup | Measures discovery+invoke, not invoke-only; valid only if labeled accurately |
| Measuring without warmup, without forks | Results are skewed by compilation/JIT and pre-test state |
| Using constant inputs, not consuming output | The JVM may constant-fold and eliminate the computation |
| Printing logs/console inside the hot loop | I/O masks dispatch differences |
| Comparing `invokeWithArguments` to a direct typed call while ignoring boxing | Measuring two different call contracts |
| Measuring one JDK and applying it to all releases | Reflection internals and JIT change |
| Ignoring memory/cache hits/class loaders | CPU optimization may cause memory leaks or cold-start regressions |

**Do not label simply swapping an API as a “performance improvement”.** Define the success metric upfront: reducing dispatch CPU at p95, reducing allocations, or reducing cold startup? If after benchmarking the real bottleneck is network/database, optimizing lookup will not help significantly.

## 13. Common failures: catching mistakes at the right phase

| Symptom | Cause | Where to handle |
| --- | --- | --- |
| `NoSuchMethodException` on first request | Not discovered/validated early | Builder/prepare |
| Wrong overload/synthetic bridge picked | Selecting by `getDeclaredMethods` order or by name only | Discovery/validation |
| `IllegalAccessException` during unreflect | Lookup lacks access or module is not opened properly | Prepare; fix permission design |
| `WrongMethodTypeException` on call | `invokeExact` signature at call site does not match handle type | Prepare check + compile-time callsite QA |
| `ClassCastException` in adapter | Data/runtime type cannot be converted | Per-request input validation and converter policy |
| Null/negative values still pass through plan | Moved even input validation to startup | Execute |
| Target method error mistaken for lookup error | Preparation exceptions and runtime exceptions not separated | Error boundary |
| Classes from different loaders with same name | Caching by binary name String without identity | Cache key/generation |
| Multiple requests build plan for same key | Unsynchronized cache or side effects in builder | Concurrent cache/initialization |
| Invalid config still publishes half-built plan | Mutating separate fields or mishandling exceptions | Build-before-publish atomic snapshot |
| User permissions revoked but handle still callable | Caching capability without matching authorization | Runtime permission/guard |
| Cache retains old loader forever | Static map/MethodHandle/threads holding references | Retirement/lifecycle |
| “Optimized” yet lower throughput | Adapter boxing, cache contention, startup, JIT | JMH + real workload profiling |

**Do not catch `Throwable` and silently return “missing route”.** Configuration errors, permission errors, callsite type errors, and exceptions thrown by the target have different meanings and should go through separate error reporting mechanisms. In the examples, `main throws Throwable` is only for code readability.

## 14. Production readiness review checklist

1. **Stability:** which parts depend on class/schema/revision, and which depend on the request?
2. **Discovery:** how many times are methods/fields/annotations scanned per version? Does any leak into the hot path?
3. **Member selection:** does the key include class, name, param types, return type, static/instance, and class loader?
4. **Type:** is `handle.type()` checked before publishing? Are receiver and primitive return correct?
5. **Type conversion:** are necessary converters/adapters built during preparation rather than scattered across requests?
6. **Permissions:** does Lookup have valid access? Can a private MethodHandle leak to another plugin or tenant?
7. **Input:** which validations must still run on every request? Is there dynamic permission/quota revocation?
8. **Cache:** are ClassValue/CHM used with proper concurrency semantics? Is the builder free of non-repeatable side effects?
9. **Identity:** could two classes with the same binary name but different loaders collide in one cache entry?
10. **Publish:** does the plan bundle target+metadata/version into **one immutable snapshot**? Do readers fetch a single snapshot?
11. **Reload:** if building v2 fails, does v1 stay active? Is there a policy for multiple concurrent writers?
12. **Cleanup:** who retires old plans and releases loaders, handles, resources, and in-flight requests?
13. **Observability:** do metrics distinguish prepare count, hit/miss, execute count, and latency of each phase?
14. **Measurement:** are there steady-state microbenchmarks as well as end-to-end and cold startup measurements on the target JDK?
15. **Simplicity:** could the whole thing be replaced with a direct call or a simpler cached `Method`?

One sentence describing a good design: **“Each route is discovered, validated, and bound to a handle when building a plan per revision; each request only fetches the snapshot, validates current data/permissions, and executes.”**

## 15. Self-check exercises

**Exercise 1.** A JSON serializer has 20 fields, currently reads field annotations on every object, and checks `age >= 0`. Which operations move to prepare?

**Answer:** Discovering fields/annotations, selecting converters, field access, JSON name mapping, and schema types can be cached per class/schema. Checking the **`age` value** still runs per object.

**Exercise 2.** Instance method `int charge(int amount)` of `Account` is converted via `Lookup.unreflect`. What is the typical MethodHandle type?

**Answer:** `(Account,int)int`. The receiver appears first; validate `handle.type` during prepare.

**Exercise 3.** How many times do the two `Plan.execute` calls in `PreparedDispatchDemo` increment `SCANS`?

**Answer:** Zero times. `SCANS` increments when calling `prepare`, once for `total` and again for the rejected `info`.

**Exercise 4.** Two threads call `ClassValue.get(C.class)` concurrently, and the mapping function writes an external file outside the JVM. Is it guaranteed to write only once?

**Answer:** No. `computeValue` may run concurrently; only the installed cache value is chosen. Avoid non-idempotent side effects in compute.

**Exercise 5.** Two plugins have a class with the same name `pkg.Widget` loaded by two different class loaders. Is using `Map<String,MethodHandle>` by name safe?

**Answer:** Insufficient; it may return a handle from the wrong generation. Key by `Class<?>`/loader identity, signature, and revision; manage cleanup.

**Exercise 6.** A writer updates `activeHandle` and then `activeRevision` via two volatile fields. Is a reader guaranteed to receive both from the same version?

**Answer:** No. Use an immutable plan containing handle/revision and publish via a single volatile/atomic reference.

**Exercise 7.** The plan already verified that the method is public, but the user's token was revoked. Can token validation be skipped because the plan is still valid?

**Answer:** No. Member access is structural validity; runtime authorization is a request-variant condition.

**Exercise 8.** Call `MethodHandles.lookup().unreflect(m)` once, then use `invokeExact` but cast/assign the result to `Object` while the handle returns `int`. Result?

**Answer:** `WrongMethodTypeException` because the callsite return type does not match `MethodType`, even though method lookup was done properly.

**Exercise 9.** A route is called only once at startup. Are `ClassValue` and a complex adapter chain needed?

**Answer:** Not necessarily. Optimization is only justified when there is reuse and the savings can be shown to exceed prepare/cache/lifecycle costs.

**Exercise 10.** A benchmark calls Reflection including discovery on every iteration against a pre-prepared MethodHandle. Can we conclude that `Method.invoke` alone is slower than `invokeExact`?

**Answer:** No. The benchmark is measuring **per-request discovery + invoke** against prepared invoke. To measure invocation cost alone, cache `Method` in the Reflection case and clearly report setup/callsite types, warmup, inputs, and results.

## 16. Official references

- [Oracle JDK 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType`, and access checking when forming a handle.
- [Oracle JDK 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVirtual`, `findStatic`, `unreflect`, caller/member access.
- [Oracle JDK 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): combinators and adapter methods.
- [Oracle JDK 17 — ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): per-Class caching, concurrent `computeValue`, and `remove`.
- [Oracle JDK 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `computeIfAbsent`, atomic map updates, and restrictions.
- [Oracle JDK 17 — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): publication and fetching a single snapshot reference.
- [Oracle JDK 17 — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): distinguishing access modes and memory effects; caching metadata does not synchronize automatically.
- [OpenJDK JEP 416](https://openjdk.org/jeps/416): Core Reflection reimplemented with MethodHandles since Java 18.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): methodology for writing JVM microbenchmarks with warmup/forks/measurement.

**In summary:** separating **discovery and structural validation** from the repeated execution path makes the system clearer, catches errors early, and avoids unnecessary metadata processing. Prepare typed MethodHandles/VarHandles/converters for the **exact class + version**, publish immutable plans safely, and only invoke the plan on the hot path. **Do not** hoist data validation or dynamic authorization; do not mix plans across class loaders; and **measure in practice** before claiming speedups.