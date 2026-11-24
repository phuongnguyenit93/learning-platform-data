# Distinguishing Source, Binary, and Behavioral Compatibility of an API Contract

## 1. An API change can be “compatible” in three different senses

In Java, a library or plugin host typically has a **contract** between the API/SPI provider and the consumer. When upgrading the contract version, saying “this change is backward compatible” is **not precise enough**: you must specify the **compatibility type**, the **version replacement direction**, and **which components have or have not been recompiled**.

Three key levels:

1. **Source compatibility:** can consumer/provider source code written for the old API still **compile** when switching to the new API in a defined compilation environment?
2. **Binary compatibility:** do **precompiled** `.class` files or JARs link and run with the new API version **without requiring recompilation**, at least for existing references?
3. **Behavioral compatibility:** even when code compiles and the JVM links successfully, do the results, side effects, and business guarantees still **match the expectations that old clients rely on**?

These are three independent questions. **Successful compilation does not prove binary compatibility for old bytecode; successful bytecode loading and linking does not prove behavioral compatibility.**

For example, a plugin host publishes:

~~~java
public interface PricePolicy {
    int fee(int amount);
}
~~~

This is only **a Java signature**, not the full contract: how much should `fee(100)` return, how are negative arguments handled, may it mutate state, can it be called concurrently, and what exception type signals an error? Those rules may live in Javadoc, a specification, or contract tests; changing them can break clients **even though the interface stays identical**.

## 2. Comparison table: what is tested and how does it break?

| Dimension | Test question | Typical test method | Signs of incompatibility |
|---|---|---|---|
| **Source** | Does old source code still build against the new API? | Compile **old source** with the new API using `javac`/Maven/Gradle | Compiler errors: missing method, ambiguous overload, type mismatch, unimplemented/unoverridden method |
| **Binary** | Do **precompiled** JARs/classes run with the new API? | Keep old client/provider bytecode unchanged; swap only the runtime API JAR and run | `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, `IncompatibleClassChangeError`, `AbstractMethodError`, or related linkage errors |
| **Behavior** | Are results and contract guarantees still valid? | Contract tests, integration tests, golden outputs, concurrency/error-path tests | Different return value, different ordering/exception, broken invariant, violated thread-safety/idempotence/timeout commitment |

**The relationship among the three types is not a one-way implication:**

- A change can be **binary-compatible but source-incompatible**: adding an overload can make a `method(null)` call ambiguous upon rebuild; old bytecode still calls the previously selected descriptor.
- A change can be **source-compatible for a client but binary-incompatible**: changing the return type from `int` to `long` still compiles when the client assigns to `long`, but old bytecode calling the `()I` descriptor can hit `NoSuchMethodError`.
- A change can be **source- and binary-compatible but behavior-incompatible**: changing a fee calculation algorithm from 10% to 20% while keeping the public signature unchanged.
- A change can **preserve current behavior** yet break source/binary compatibility (for example, renaming a method and adding migration code on only one side). Therefore, behavioral testing does not replace build/linkage checks.

### Clarifying the “direction” of the test

Notation:

- `API v1`: the old version of the contract.
- `API v2`: the new version.
- `Client v1.class`: bytecode compiled against API v1.
- `Provider v1.class`: plugin bytecode implementing SPI v1.

Two distinct scenarios:

~~~text
SOURCE check:
    client-v1.java + API v2  --> does javac succeed?

BINARY check:
    client-v1.class + API v2 --> does the JVM find the old method/field/type?

BEHAVIOR check:
    client-v1.class + API v2 --> does the result still match the v1 specification?
~~~

For plugins, **both directions** must be tested when the system's version policy requires it: *new host running old plugin* and *old host running new plugin*. The two directions can yield different results; “v2 is compatible with v1” is not automatically a symmetric relation.

## 3. Source compatibility: when recompiling old code

At the source level, the compiler evaluates all Java syntax, overload resolution, access control, type inference, generics, annotation processors, module readability, and many other rules at **build time**.

Common source breaks:

- Removing or renaming a public method that client source code calls.
- Adding an abstract method to an SPI interface so old implementation source no longer implements every method.
- Renaming a package or class without providing a corresponding class/adapter.
- Adding an overload that creates an ambiguous choice at compile time.
- Tightening visibility/access of an API imported by clients.
- Changing generic bounds or signatures so old source no longer type-checks.
- Adding a checked exception to `throws` so client code that does not catch/declare it fails to build; changing `throws` can also affect source code catching a checked exception that is no longer declared.
- Changing module descriptor `exports`/`requires` so a named client module can no longer read or access a package.

**Subtle point:** source compatibility is not merely “all old methods still exist.” Adding an overload **can prevent an old client from building** because the compiler must re-select among multiple overloads, whereas old bytecode already recorded the selection from the previous compilation.

In addition, build outcomes depend on the **classpath/module path, JDK release, compiler options, and module graph**. Testing “v1 code builds on my machine” is insufficient; you need to test actual source with production dependencies and settings, such as `javac --release 17` when committing to Java 17 support.

## 4. Binary compatibility: the JVM links via compiled references

Java source compiles into bytecode containing **symbolic references** to classes, fields, and methods, which are resolved when needed. At the JVM level, a method descriptor includes **parameter types and return type**. For example:

~~~text
Java source                    JVM method descriptor
public static int max()        max:()I
public static long max()       max:()J
public String greet(String x)  greet:(Ljava/lang/String;)Ljava/lang/String;
~~~

Because `()I` and `()J` differ, changing a return type **without keeping the old method** can break client bytecode that recorded a reference to `max:()I`. The source compiler for new code can automatically widen `int` to `long` at an assignment; however, the JVM **does not rewrite method references inside old client classes**.

Common symptoms:

- `NoSuchMethodError`: bytecode invokes a method descriptor that is no longer found in the class/interface in the way the JVM requires.
- `NoSuchFieldError`: a field referenced by bytecode no longer exists with the old name/descriptor.
- `IllegalAccessError`: linking to a class/member that was previously accessible but is now denied.
- `IncompatibleClassChangeError`: class/interface/static/instance shape no longer matches how old bytecode uses it.
- `AbstractMethodError`: a valid call site exists, but the dispatched implementation does not provide the required concrete method.
- `NoClassDefFoundError`: a type that compiled code depends on is unavailable or cannot be defined/initialized in the runtime environment; inspect the cause rather than assuming every case is an API version mismatch.

These errors belong to the `LinkageError` family or related loading/linking failures, **distinct** from compiler diagnostics and distinct from business exceptions thrown by an implementation.

### Binary compatibility does not mean “every new call works”

Some changes are considered by the JLS to be binary-compatible with **pre-existing references**. However, if a new host invokes a **newly added** method on an interface against an old plugin implementation, it can still hit `AbstractMethodError`. Thus, JLS-level compatibility does not replace an operational “host-v2 ↔ provider-v1” support matrix.

### Bytecode and generic types

Source-level generics information does not always appear verbatim in method descriptors due to **type erasure**. Some generic signature changes affect only source, but changing bounds/erasure, bridge methods, or overridden methods can affect binary dispatch. You should not classify “changing generics is always binary-compatible” without comparing actual descriptors and testing compiled artifacts.

## 5. Behavioral compatibility: keeping the contract's promises

The compatibility types above only state whether code can **compile and link**, not whether the program remains functionally correct.

A behavioral contract may include:

- **Preconditions:** which inputs are valid, whether `null` is accepted, value ranges, when exceptions are thrown.
- **Postconditions:** what outputs mean; rates, units, rounding, string formatting, encoding, result ordering.
- **Invariants:** state that must not be violated after a call, consistency across methods.
- **Side effects:** writing files, sending network traffic, invoking callbacks, creating transactions, updating state, or emitting events.
- **Error semantics:** exception types, failure conditions, retry behavior, error code mapping, whether errors may be ignored.
- **Ordering and concurrency:** whether result order is guaranteed, thread-safety, visibility/happens-before, whether callbacks are invoked once or multiple times.
- **Idempotence and transaction semantics:** whether re-invoking the same request causes additional effects; whether rollback changes.
- **Performance/resource promises:** latency, memory, timeouts, blocking/non-blocking behavior, backpressure if promised as part of the API.
- **Protocol/data compatibility:** JSON/serialization/schema formats and the ability of old clients to read new data.

For example, `int fee(int amount)` keeps the same source and JVM descriptor, yet changing it from 10% to 20% breaks applications relying on the 10% rule. Changing rounding mode, plugin provider ordering, failure on negative input, or thread-safety can also be a behavioral break—even if all integration tests that only check “does not throw an exception” pass.

A **behavioral contract** should be expressed in Javadoc, acceptance criteria, and **contract tests with assertions**; if it lives only in a developer's head, backward compatibility is very hard to prove.

## 6. Example A: adding an overload — binary still runs, old source fails to rebuild

The first scenario illustrates a change that *expands the API* yet still causes source incompatibility.

Suppose project `case-a/` has three source areas. The following Java files are all valid on Java 17.

### API v1 — `v1/src/demo/api/Selector.java`

~~~java
package demo.api;

public final class Selector {
    private Selector() {}

    public static String select(String value) {
        return "string";
    }
}
~~~

### API v2 — `v2/src/demo/api/Selector.java`

~~~java
package demo.api;

public final class Selector {
    private Selector() {}

    public static String select(String value) {
        return "string";
    }

    public static String select(Integer value) {
        return "integer";
    }
}
~~~

The `select(String)` signature **is still preserved** in v2. However, the Java compiler now has two overloads with no “more specific” relationship when the argument is `null`: `String` and `Integer`.

### Old client — `client/src/demo/app/Client.java`

~~~java
package demo.app;

import demo.api.Selector;

public final class Client {
    public static void main(String[] args) {
        System.out.println("selected=" + Selector.select(null));
    }
}
~~~

From directory `case-a/` using Bash:

~~~bash
mkdir -p out/v1 out/v2 out/client-old out/client-new

javac --release 17 -d out/v1 v1/src/demo/api/Selector.java
javac --release 17 -d out/v2 v2/src/demo/api/Selector.java

# Compile old client against API v1
javac --release 17 -cp out/v1 -d out/client-old \
  client/src/demo/app/Client.java

# Without recompiling client: run against each API runtime
java -cp "out/v1:out/client-old" demo.app.Client
java -cp "out/v2:out/client-old" demo.app.Client

# Try rebuilding the exact same old source, but against API v2
javac --release 17 -cp out/v2 -d out/client-new \
  client/src/demo/app/Client.java
~~~

On Linux/macOS, `:` separates classpath entries; on Windows, change `:` to `;`. The two `java` commands produce identical output:

~~~text
selected=string
selected=string
~~~

Each line is the result of **a separate run**. The final `javac` command **fails**, with a diagnostic whose core message is:

~~~text
reference to select is ambiguous
both method select(String) and method select(Integer) match
~~~

Exact line numbers/paths in the diagnostic depend on the file and compiler, so do not treat this as fixed Java application stdout.

**Explanation:** the old `Client.class` bytecode already contains a reference to `Selector.select:(Ljava/lang/String;)Ljava/lang/String;`. API v2 still provides this method, so it links and runs. However, when recompiling `Selector.select(null)`, the compiler must re-resolve the overload and finds two ambiguous candidates.

**Lesson:** “just adding an overload” does not automatically guarantee *source compatibility*. Safer ways to evolve an API when expansion is needed: choose a different name, use a factory/options object, or compile-test old client source in CI as well.

## 7. Example B: changing return type — client source still compiles, old binary breaks

The second scenario intentionally changes the **JVM** signature while a specific client still rebuilds from source because Java allows widening from `int` to `long`.

Independent layout `case-b/`:

### API v1 — `v1/src/demo/api/Quota.java`

~~~java
package demo.api;

public final class Quota {
    private Quota() {}

    public static int max() {
        return 10;
    }
}
~~~

### API v2 — `v2/src/demo/api/Quota.java`

~~~java
package demo.api;

public final class Quota {
    private Quota() {}

    public static long max() {
        return 10L;
    }
}
~~~

### Client — `client/src/demo/app/Client.java`

~~~java
package demo.app;

import demo.api.Quota;

public final class Client {
    public static void main(String[] args) {
        try {
            long q = Quota.max();
            System.out.println("quota=" + q);
        } catch (NoSuchMethodError e) {
            System.out.println("linkage=NoSuchMethodError");
        }
    }
}
~~~

The `catch` in this example is **only to demonstrate the linkage error deterministically**. In real applications, do not treat `NoSuchMethodError` as a business exception and continue running normally; fix the runtime API/implementation version coordination instead.

Bash commands in `case-b/`:

~~~bash
mkdir -p out/v1 out/v2 out/client-old out/client-new

javac --release 17 -d out/v1 v1/src/demo/api/Quota.java
javac --release 17 -d out/v2 v2/src/demo/api/Quota.java

javac --release 17 -cp out/v1 -d out/client-old \
  client/src/demo/app/Client.java

java -cp "out/v1:out/client-old" demo.app.Client
java -cp "out/v2:out/client-old" demo.app.Client

# Recompile old source against v2
javac --release 17 -cp out/v2 -d out/client-new \
  client/src/demo/app/Client.java

java -cp "out/v2:out/client-new" demo.app.Client
~~~

Output for each `java` command respectively:

~~~text
quota=10
linkage=NoSuchMethodError
quota=10
~~~

Why?

1. With API v1, the compiler emits bytecode calling `Quota.max:()I` and then widens `int` to `long` to store in variable `q`.
2. When replacing **only the runtime API** with v2, method `Quota.max:()I` no longer exists; v2 has only `Quota.max:()J`. Old bytecode is not rewritten → `NoSuchMethodError`.
3. When **rebuilding client source** against v2, the compiler emits a call to `max:()J`; compilation succeeds and the program prints `quota=10` again.

**Conclusion for this change:** the example client's source is **compatible** upon recompilation; the old client's binary is **incompatible** when swapping the runtime API. Source compatibility must be evaluated per source set and context, without generalizing that all other sources are compatible.

If a library must widen a value type from `int` to `long` while preserving old binaries, a common path is to **keep the old method** and add a newly named method, such as `maxLong()`, then deprecate the old method over release cycles.

## 8. Example C: no source or binary errors, but the behavioral contract is broken

Suppose specification v1 promises: **`fee(amount)` equals 10% of `amount` when amount is a non-negative multiple of 10**. The client has tests relying on this rule.

### API v1 — `v1/src/demo/api/Policy.java`

~~~java
package demo.api;

public final class Policy {
    private Policy() {}

    public static int fee(int amount) {
        return amount / 10;
    }
}
~~~

### API v2 — `v2/src/demo/api/Policy.java`

~~~java
package demo.api;

public final class Policy {
    private Policy() {}

    public static int fee(int amount) {
        return amount / 5;
    }
}
~~~

### Client — `client/src/demo/app/Client.java`

~~~java
package demo.app;

import demo.api.Policy;

public final class Client {
    public static void main(String[] args) {
        int fee = Policy.fee(100);
        System.out.println("fee=" + fee);
        System.out.println("rule-ok=" + (fee == 10));
    }
}
~~~

Bash commands in `case-c/`:

~~~bash
mkdir -p out/v1 out/v2 out/client-old out/client-new

javac --release 17 -d out/v1 v1/src/demo/api/Policy.java
javac --release 17 -d out/v2 v2/src/demo/api/Policy.java

javac --release 17 -cp out/v1 -d out/client-old \
  client/src/demo/app/Client.java

java -cp "out/v1:out/client-old" demo.app.Client
java -cp "out/v2:out/client-old" demo.app.Client

javac --release 17 -cp out/v2 -d out/client-new \
  client/src/demo/app/Client.java

java -cp "out/v2:out/client-new" demo.app.Client
~~~

Output for each run:

~~~text
fee=10
rule-ok=true
fee=20
rule-ok=false
fee=20
rule-ok=false
~~~

There is no compiler error or `LinkageError`; the method is still `Policy.fee:(I)I`. However, the output `fee=20` **does not satisfy the old 10% specification**. Regardless of whether the client is rebuilt, the behavior has changed.

In a real system, such a change can corrupt invoices, reports, cache keys, or payment workflows even while deployment and startup smoke tests stay green. To prevent this: write **contract tests** expressing rules that must not break; if a rule must change, publish a new policy/endpoint/version with a clear migration plan.

> Do not use “no exception thrown” as the sole criterion for behavioral compatibility. A system returning **wrong results that are still type-valid** can be more dangerous than an easily detected linkage error.

## 9. Example D: SPI interface adds an abstract method — old plugin hits `AbstractMethodError`

This is the most critical scenario when designing a **runtime extensibility** system. Host and plugin are built separately and share a service interface. The SPI v2 author adds a new method:

### SPI v1 — `spi-v1/src/demo/spi/Plugin.java`

~~~java
package demo.spi;

public interface Plugin {
    String id();
}
~~~

### SPI v2 — `spi-v2/src/demo/spi/Plugin.java`

~~~java
package demo.spi;

public interface Plugin {
    String id();
    String description();
}
~~~

### Old provider — `provider/src/demo/provider/OldPlugin.java`

~~~java
package demo.provider;

import demo.spi.Plugin;

public final class OldPlugin implements Plugin {
    @Override
    public String id() {
        return "old";
    }
}
~~~

### New host — `host/src/demo/host/Main.java`

~~~java
package demo.host;

import demo.spi.Plugin;
import demo.provider.OldPlugin;

public final class Main {
    public static void main(String[] args) {
        Plugin p = new OldPlugin();
        System.out.println("id=" + p.id());
        try {
            System.out.println("description=" + p.description());
        } catch (AbstractMethodError e) {
            System.out.println("failure=AbstractMethodError");
        }
    }
}
~~~

The following commands run from the directory containing the four source trees above; using Bash:

~~~bash
mkdir -p out/spi-v1 out/spi-v2 out/provider-old out/host

javac --release 17 -d out/spi-v1 \
  spi-v1/src/demo/spi/Plugin.java
javac --release 17 -d out/spi-v2 \
  spi-v2/src/demo/spi/Plugin.java

# Plugin already built against interface v1
javac --release 17 -cp out/spi-v1 -d out/provider-old \
  provider/src/demo/provider/OldPlugin.java

# New host built with SPI v2 and old plugin bytecode
javac --release 17 -cp "out/spi-v2:out/provider-old" -d out/host \
  host/src/demo/host/Main.java

java -cp "out/spi-v2:out/provider-old:out/host" demo.host.Main

# Try recompiling old provider source against SPI v2
javac --release 17 -cp out/spi-v2 -d out/provider-new \
  provider/src/demo/provider/OldPlugin.java
~~~

The `java` command prints:

~~~text
id=old
failure=AbstractMethodError
~~~

The final `javac` command fails: `OldPlugin` does not implement the abstract `description()` method added in interface v2.

**Distinguish the two phenomena:**

- **Source compatibility for old implementations:** broken because a concrete Java class must implement all abstract methods when rebuilt.
- **Binary compatibility with existing references:** adding an abstract method to an interface is described by the JLS as binary-compatible in the sense that existing references can still link; in fact, `id()` still runs with v1 provider bytecode. **However, once host v2 starts calling the new method** `description()` on a v1 implementation, dispatch finds no implementation → `AbstractMethodError`.

Saying “adding an abstract method to an SPI is binary-compatible, so it is safe for all old plugins” leads to mistakes. For host/plugin rollouts, safety also depends on **which methods the new host calls** and whether old plugins can satisfy them.

### Using a `default method` can reduce risk — but behavior must be evaluated

One way to evolve the interface is:

~~~java
package demo.spi;

public interface Plugin {
    String id();

    default String description() {
        return id();
    }
}
~~~

When not overridden, old implementations can inherit the default implementation, avoiding the need to force old plugins to implement the new method. However:

- The default must have **valid semantics** for every old provider. `description()` returning `id()` may or may not be acceptable depending on the contract.
- Adding a default method can cause **inheritance conflicts** when a class already implements multiple interfaces with matching method signatures, or interact unexpectedly with old hierarchies. Both source and binary must be tested.
- A default method does not guarantee that old providers actually support a brand-new feature; the method should design an explicit fallback (or use an optional capability interface).
- Do not use a default merely to dodge `AbstractMethodError` if the fallback behavior is wrong.

Another approach is to add an extension interface:

~~~java
public interface PluginV2 extends Plugin {
    String description();
}
~~~

This is an **illustrative snippet**: when implemented, place it in the appropriate package/module, keep the original `Plugin` unchanged, and have the host check `instanceof PluginV2` before using the new feature. Old plugins continue serving the old contract; new plugins can opt into the new capability. This avoids forcing all old providers to adopt changes at once.

## 10. Applying this to real-world host–plugin and SPI contracts

In a Java plugin system, independent parties may coexist:

~~~text
Host v2
  |
  +-- public SPI/API artifact v2
  |
  +-- Plugin A (JAR built against SPI v1)
  +-- Plugin B (JAR built against SPI v2)
  |
  +-- class loader or module layer
  |
  +-- ServiceLoader / factory / discovery registry
~~~

For old plugins to work when the host is upgraded, verify:

1. **Type identity:** host and plugin share the exact **same runtime class object** of the SPI interface. Two classes with the same binary name defined by two different defining class loaders **are not the same type**.
2. **Binary signatures:** host v2 still provides the class/method/field descriptors that plugin v1 was compiled to call.
3. **Instantiation:** constructors, provider factories, `ServiceLoader` service descriptors, or `module-info.java` `provides` clauses remain compatible.
4. **Module readability/exports:** if using JPMS, the API package is still exported to the appropriate plugin modules; host/plugin modules read the right dependencies.
5. **Provider capabilities:** the new host does not require old plugins to have new mandatory methods without fallback or version-gating.
6. **Behavior contract:** callbacks, invocation order, lifecycle, thread-safety, exception semantics, and resource ownership that provider v1 relies on are preserved or explicitly migrated.

In particular, “replacing classes in the plugin directory without restarting the host” is a **class loading/lifecycle** issue—separate from, yet capable of masking, compatibility bugs. The JVM does not automatically update bytecode of a class already defined by a loader. You generally must stop the old plugin, drop references, and create a new class loader/module layer for the new version; otherwise, tests may still be running against old classes.

### Source compatibility can differ between consumer and provider

An SPI change might not break the source of a client that only *calls* `Plugin.id()`, yet break the source of an old provider that `implements Plugin`. Conversely, adding an overload to a host API can break consumer code due to overload resolution even if plugin implementations are unchanged.

Therefore, compatibility reports should always state clearly:

~~~text
Check targets:
  host API consumer source
  plugin provider source
  old host bytecode
  old plugin bytecode
  module/ServiceLoader metadata
  runtime behavior contract

Check directions:
  host v2 + plugin v1
  host v1 + plugin v2 (if supported)
~~~

Do not collapse all of these into a single boolean label.

## 11. API changes commonly misjudged

| Change | Source compatibility | Binary compatibility | Behavioral contract |
|---|---|---|---|
| Add overload `select(Integer)` alongside `select(String)` | **May break** source calling `select(null)` due to ambiguity | Old call sites to `select(String)` usually still link | Preserved old method can behave as before |
| Change `int max()` → `long max()` | Some source still builds via widening; other source may break | **Breaks** old method descriptor `()I` | Numeric value may stay the same, which is not enough |
| Change implementation of `int fee(int)` | Usually unchanged at source | Usually unchanged at ABI | May break business rules |
| Add abstract method to SPI interface | **Breaks** source of concrete providers that do not implement it | Adding the method can be binary-compatible for old references; **new call site** on old provider can throw `AbstractMethodError` | New capability is not guaranteed |
| Add default method to interface | Usually friendlier, though source/override conflicts can happen | Must check dispatch conflicts and actual hierarchy | Fallback must have valid semantics |
| Remove public method/field in use | Old source usually breaks | Old bytecode can throw `NoSuchMethodError`/`NoSuchFieldError` | Not guaranteed |
| Reduce visibility public → package-private/private | Source outside package/module breaks | Old bytecode can throw `IllegalAccessError` | Not guaranteed |
| Change static method to instance method (or vice versa) | Old call syntax may break | Can throw `IncompatibleClassChangeError` | Not guaranteed |
| Add checked exception to `throws` declaration | Can force callers to catch/declare, breaking source | `throws` is not part of the JVM method descriptor, so it does not directly break linkage | Error behavior may change |
| Change compile-time `public static final` constant | Source usually remains valid | Old binaries may still use the **inlined** value | Clients may observe **different values depending on compile time** |
| Change generic type parameters/bounds | May cause compile errors or warnings | Depends on erasure, bridge methods, and specific descriptors | May cause runtime cast errors |
| Change `exports` or module dependencies | Named-module source may lose access | Runtime access/linkage may break due to module graph configuration | May change discovery/access |
| Rename package/class | Old source imports break | Old symbolic references to old names fail to resolve without a compatibility shim | Not guaranteed |

The words **“usually”, “may”, “depends”** in the table are intentional: many changes have exceptions under the JLS/JVMS, compiler behavior, and how clients use the API. For a public library, prove compatibility with **actual source + actual bytecode + runtime tests**, not just the heuristic “the method name is the same.”

### Compile-time constants and observable behavior

For example:

~~~java
public static final String VERSION = "v1";
~~~

If `VERSION` is a *constant variable* used in a constant expression, `javac` can embed `"v1"` directly into client bytecode. After changing the field to `"v2"`, an old client **may still print `"v1"`** even though the runtime contains the new API; only a rebuilt client uses `"v2"`. This is a case where “the binary throws no error, yet behavioral version skew appears.” If a value is runtime data that must update, consider providing an accessor method instead of relying on constant inlining.

### Checked exceptions and binary descriptors

Checked `throws` information does not participate in the JVM method descriptor `(parameterTypes)returnType`. Thus, changing `throws IOException` in source is not like changing a return type or parameter type. However, the source compiler still checks checked exceptions; a client that caught only the old exception or does not handle the new one may fail to rebuild. Runtime behavior regarding which error types are thrown can also change.

## 12. Setting compatibility standards in versioning and rollouts

No single test fits every public API. A concrete release plan should include:

### 12.1. Policy definition

Example compatibility policy for an SPI:

- Host v2 must continue **running** plugin JARs built against SPI v1 without requiring a rebuild.
- Plugin v1 code rebuilt against API v2 must compile without errors (if source compatibility is promised).
- Methods published in v1 must preserve key postconditions, exception semantics, and lifecycle hooks.
- New features are enabled only for plugins declaring the corresponding capability/version.
- Intentional contract-breaking changes must have a deprecation/migration guide and clear version boundaries.

**Semantic Versioning** is a convention about version numbers and API breakage levels; it **does not automatically detect** every source/binary/behavior break. Even in a minor version bump, a change considered “additive” can make overload resolution ambiguous or cause default method conflicts. Verify the actual contract rather than inferring from version numbers.

### 12.2. Safer evolution strategies

- **Add a new method with a new name** instead of altering the descriptor of an in-use public method; keep the old shim method if possible.
- **Deprecate before removing:** give clients time to migrate; deprecation does not delete the method, so it does not itself break binaries.
- **Use an extension capability interface** or a default method with a valid fallback when adding capabilities to an SPI.
- **Use a request/config object** to add options instead of adding uncontrolled overloads; design that object with sensible versioning as well.
- **Version-gate by actual capability** rather than just comparing version strings; check `instanceof`/feature negotiation where appropriate.
- **Separate contract behavior from implementation details:** test published outputs, errors, state transitions, and side effects, avoiding tests on unpromised details.
- **Add matrix-based integration tests** when host/client/provider are deployed or upgraded independently.
- **Keep one shared SPI copy per class loader:** if a plugin bundles its own copy of the API with the same binary name and a child-first loader loads it, `ClassCastException` can occur—this is not a simple semver bug.

### 12.3. Minimum test matrix

| Combination | Purpose |
|---|---|
| API v1 + client/provider v1 source | Baseline: old sample builds |
| API v2 + client/provider v1 **source** | Evaluate **source compatibility** |
| API v2 runtime + **client/provider v1 `.class`/JAR**, no rebuild | Evaluate **binary compatibility** and ability to load old plugins |
| API v2 runtime + new implementation | Confirm v2 functionality |
| Host v2 + plugin v1 | Backward compatibility in plugin deployment |
| Host v1 + plugin v2 (if policy promises it) | Forward compatibility or graceful rejection |
| Contract tests run across supported combinations | Evaluate **behavior** for inputs/outputs, side effects, errors, and concurrency |

**Do not accidentally recompile old plugins in binary tests.** If your build tool automatically recompiles the entire workspace against API v2, you have tested source compatibility and may no longer reproduce `NoSuchMethodError`/`AbstractMethodError` from real artifacts running at customer sites.

## 13. Java 17+ tools to verify changes

### `javac`: testing source compatibility

Take **v1 source code**, switch the compile classpath/module path to API v2, and run:

~~~bash
javac --release 17 -cp path/to/api-v2.jar -d out/client-rebuild \
  client/src/demo/app/Client.java
~~~

Or apply the same logic in Maven/Gradle CI. For modular source, preserve the corresponding module graph; use `--module-path` and `--module`/`--module-source-path` as designed rather than forcing a JPMS setup into this classpath example.

### `javap`: inspecting bytecode signatures and method descriptors

Assuming the classes from Example B are compiled:

~~~bash
javap -classpath out/v1 -s -public demo.api.Quota
javap -classpath out/v2 -s -public demo.api.Quota
javap -classpath out/client-old -c -p demo.app.Client
~~~

Look for `descriptor: ()I` in API v1, `descriptor: ()J` in v2, and the compiled call in the old client. `javap -s` shows JVM descriptors; `javap -c` shows bytecode instructions; `-p` includes private members of the inspected class.

Do not rely solely on source diffs: a seemingly small change in Java can alter a JVM descriptor or emit/remove a bridge method. Especially with covariant return types, the compiler may generate synthetic **bridge methods** to support binary dispatch; inspect the actual artifacts rather than assuming all return-type changes have identical impact.

### `jdeps` and module metadata: checking dependencies

`jdeps` analyzes class/module-level dependencies of a JAR, helping spot classes referencing dependencies that are no longer present. With JPMS, `java --describe-module` or `jar --describe-module` is also useful to cross-check `requires`, `exports`, `uses`, and `provides`.

However, static dependency analysis tools cannot prove reflection paths, class names constructed from strings, `ServiceLoader` providers in runtime layers, or behavioral contracts. They must be combined with **runtime tests**.

### Contract tests and differential tests

Run the same business test suite against API v1 and v2. Assertions must reflect the specification, for example:

~~~java
int fee = Policy.fee(100);
if (fee != 10) {
    throw new AssertionError("10% fee contract broken: " + fee);
}
~~~

This is an **integration test snippet**, assuming `demo.api.Policy` is imported from Example C. Running the test against v1 passes; against v2 returning `20`, it fails. This is a clearer behavioral regression signal than a test that only checks that the method returns an `int`.

For APIs with concurrency, contract tests must also check race conditions, ordering, and resource ownership, not just a single sequential call.

## 14. Troubleshooting guide when errors appear in production

| Symptom | Suspected dimension | What to inspect |
|---|---|---|
| Client rebuild fails because `method(null)` is ambiguous | Source | New overloads and overload resolution; test with exact JDK/compiler flags |
| `NoSuchMethodError: ...()I` | Binary | Whether the runtime JAR still has the exact method descriptor; classpath order and class loaders |
| `NoSuchFieldError` | Binary | Whether old field name/type/static-ness still matches; whether a compile-time constant was inlined |
| `IncompatibleClassChangeError` | Binary | Class/interface shape, static/instance invocations, inherited defaults/dispatch |
| `AbstractMethodError` when new host calls old plugin | SPI evolution | Is the new method abstract? Does the old plugin have an implementation? Is capability negotiation right? |
| `IllegalAccessError` on module/class | Module access / binary | Public visibility, JPMS `exports`/`opens`, module graph, class loader |
| `ClassCastException` despite identical class names | Loader identity | Are two copies of the SPI defined by different loaders? |
| Plugin runs but computes differently from previous version | Behavior | Contract tests, semantics, rounding/units/exceptions, feature flags, and data |
| Old client reads old constant even though API changed | Build-time constant | Was the `static final` constant inlined when compiling the client? |
| Only some plugins fail | Mixed-version matrix | Which SPI each plugin built against, which host/API runtime, which loader, and which capability was called |

When debugging, record the **artifact version, class loader, JAR/module source, and JVM descriptor**. If possible, preserve the exact **old plugin JAR** that triggered the error to reproduce without recompiling. A log containing only a method name is not enough to identify the binary break type.

## 15. Decision checklist when reviewing a contract change

Before merging/releasing a public API/SPI change, answer:

1. **Which consumers use the API?** Are there sources, bytecodes, or independently built third-party plugins?
2. **Which direction is promised?** New host + old plugin, old host + new plugin, or both?
3. **Source check:** does old-version client/provider source compile against the new API in the exact JDK/JPMS graph?
4. **Binary check:** keeping old `.class`/JAR files unchanged and swapping only the new API/runtime, do old call sites run without `LinkageError`?
5. **Behavior check:** do tests for inputs/outputs, side effects, exceptions, rounding, timing, and concurrency preserve commitments?
6. **SPI check:** if an interface changed, can old providers still instantiate and handle every new call that may occur?
7. **Reflection/ServiceLoader:** do interface/provider names, constructors/factories, `META-INF/services`, or `module-info.java` match the new classes/loaders?
8. **Versioning:** do we need a default method, adapter, new capability API, deprecation, or major version bump?
9. **Rollout:** is there a way to detect incompatible plugins and reject them cleanly before running business logic?
10. **Rollback:** can we revert to API/host v1 without corrupting data or already-updated plugins?

A release that merely “compiles” does **not** mean it passed API compatibility testing. When an environment supports runtime extensibility, testing must keep old artifacts intact, because many failures surface only at load/link/invoke time.

## 16. Self-check questions

1. **Is adding an overload `select(Integer)` while keeping `select(String)` guaranteed to be source-compatible?** No. `select(null)` can become ambiguous upon recompilation.
2. **Why does old client bytecode still call `select(String)` properly after the API adds an overload?** Because the call site already contains the method reference/descriptor to the old overload and does not re-run overload resolution at runtime.
3. **`long q = Quota.max();` compiles with both `int max()` and `long max()`, so will the old binary always run?** No. The JVM descriptor includes the return type; `()I` differs from `()J`.
4. **Why can `Policy.fee(int)` break a contract without `javac` or the JVM reporting an error?** Because the signature is unchanged, yet changing the fee from 10% to 20% is a semantic change.
5. **How does adding an abstract method to an SPI interface affect old plugins?** Old provider source may fail to compile; old bytecode may still run old calls, but a new host invoking the new method can hit `AbstractMethodError`.
6. **Does a default method guarantee complete compatibility for all old plugins?** No. You must check fallback behavior, method conflicts, and provider lifecycle.
7. **Is `NoSuchMethodError` a source or binary error?** A bytecode linkage error at runtime; source compatibility is tested by recompiling.
8. **If `public static final String VERSION` changes value, do old clients automatically see the new value?** Not necessarily, because a compile-time constant may have been inlined into client classes.
9. **Can `jdeps` or `javap` prove a behavioral contract?** No. They primarily help analyze dependencies/bytecode; actual contract tests must be executed.
10. **For host v2 + plugin v1, is rebuilding plugin v1 against SPI v2 once enough to prove binary compatibility?** No. You must run the **exact compiled plugin v1 artifact** against the v2 runtime.

**Takeaway:** test *source* by **recompiling old code**, test *binary* by **running un-recompiled old bytecode** against the new API, and test *behavior* with **assertions on contract meaning**. All three must state the version direction and host/consumer/provider target. This is the foundation for upgrading APIs/SPIs without accidentally breaking released plugins.

## References

- [Java Language Specification 17 — Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): binary compatibility rules when changing classes, interfaces, methods, and fields.
- [Java Language Specification 17 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution and why adding an overload can cause source ambiguity.
- [Java Virtual Machine Specification 17 — `4.3 Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): field/method descriptors; method descriptors include return types.
- [Java SE 17 — `NoSuchMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html) and [`AbstractMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractMethodError.html): linkage errors when API/implementation are incompatible.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): discovery and provider contracts in runtime-extensible applications.
- [JDK 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspect bytecode/descriptors; [`jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): check dependencies.
