# Default Methods, Inheritance Conflicts, and Service Contract Evolution

In a Java plugin platform, **the host and providers are often released independently**. The host defines the service interface, while third-party plugins implement that interface and are loaded via `ServiceLoader` or a custom plugin manager. When an interface needs new capabilities, seemingly simple contract edits can break old plugin compilation, silently alter behavior, or even trigger linkage errors at runtime.

Java supports **`default` methods** in interfaces to supply default behavior for classes that do not implement the method themselves. This is a useful API evolution tool, yet **adding a default method is not unconditionally safe**. Inheritance conflicts between interfaces, differences among source/binary/behavioral compatibility, and class identity must still be accounted for.

This lesson explains method resolution rules in Java 17+, builds two compilable experiments: one program demonstrating inheritance rules, and one plugin JAR **compiled against API v1** running with a host **compiled against API v2**. A final experiment reproduces a scenario where old binary code hits a default conflict at runtime.

## 1. Properly understanding the three layers of API compatibility

When upgrading an SPI/interface, distinguish:

| Compatibility type | Question to answer | Example |
| --- | --- | --- |
| **Source compatibility** | Does old plugin source code still compile against the new API? | An old class implementing two interfaces that now both have defaults with the same signature may be rejected by `javac` |
| **Binary compatibility** | Can `.class` files compiled against the old API link with the new API under JVM rules? | Adding a default method is a binary-compatible change per the JLS, yet an invocation may hit `IncompatibleClassChangeError` |
| **Behavioral compatibility** | Even when loaded and invoked, do results/side effects/error contracts still match expectations? | An overly broad default `supports(...)` causes the host to select an old provider for a capability it does not actually support |

**Binary-compatible is not a promise that every invocation will succeed.** Specifically, JLS §13.5.7 states that adding a default method or changing an abstract method to default generally preserves binary compatibility with existing classes, yet in certain inheritance conflicts can throw `IncompatibleClassChangeError` **when the method is invoked**. Corresponding source code may report the error earlier upon recompilation.

**Source-compatible also does not guarantee behavioral-compatible.** If API v2 defaults a data-writing operation that API v1 never promised, old plugins may "run" yet corrupt business logic. Therefore, evaluate default methods across all three layers, not merely by checking that `javac` reports no errors.

## 2. How do default methods work?

An interface can declare an instance method with **`default`** and a body:

~~~java
public interface MessageService {
    String transform(String input); // Mandatory abstract method.

    default boolean supportsAdvanced() {
        return false;               // Conservative behavior for old providers.
    }
}
~~~

The snippet above is a syntactically standalone interface, not a complete runnable program. A class implementing `MessageService` is only required to write `transform(String)`. If it does not override `supportsAdvanced()`, it inherits the default implementation returning `false`.

Key properties of default methods:

- They are **instance methods** belonging to the interface, not static utility methods and not constructors.
- They have a body and can invoke other abstract methods of the interface via `this`, provided types/results match.
- When a class provides a valid overriding implementation, the class method is used instead of the default.
- They **do not add a new abstract method obligation onto old providers** the way a regular abstract method does.
- They can be overridden in subinterfaces or concrete classes; the syntax `InterfaceName.super.method()` works where a suitable direct superinterface exists to call a known default implementation.
- You cannot define a default method whose signature is override-equivalent to a public instance method of `Object`, such as `default String toString()` or `default boolean equals(Object)`. An interface can still declare the corresponding abstract method or a helper method with a different name per language rules.
- Interface `static` methods and `private` helper methods (Java 9+) serve separate roles; `static` methods do not become inherited instance methods like `default` methods.

A conservative default like **`supportsAdvanced() = false`** has strategic value: providers that have not opted into an upgrade will not advertise a new capability. Defaulting to **`true`** may be convenient to write, yet is safe only when you are certain all existing implementations genuinely support that behavior.

## 3. Default inheritance resolution rules

When multiple sources define methods with the same signature, Java does not simply "pick the first interface listed." There are four foundational cases.

### 3.1. A class method wins over an interface default

If a superclass already has a matching instance method, the class method takes priority over a default method inherited from an interface.

~~~java
class Base {
    public String name() {
        return "base";
    }
}

interface Named {
    default String name() {
        return "interface";
    }
}

class Concrete extends Base implements Named {
    // No need to override name().
}
~~~

Here `new Concrete().name()` returns **`base`**. This rule is commonly summarized as **class wins**. For an abstract class method with the same signature, do not assume an interface default automatically removes the obligation to implement the class's abstract method; concrete subclasses must still satisfy Java overriding rules.

Watch out when upgrading an API: a plugin class that already has a public method matching a new default's signature **can accidentally override** that default and run its pre-existing behavior. The absence of a compile-time conflict does not guarantee the new behavior matches the interface author's intent.

### 3.2. A more specific subinterface is allowed to override

~~~java
interface ParentName {
    default String name() {
        return "parent";
    }
}
interface ChildName extends ParentName {
    @Override
    default String name() {
        return "child";
    }
}
class Specific implements ChildName {}
~~~

`new Specific().name()` returns **`child`**. `ChildName` is a more specific subinterface and overrode `ParentName`'s default; this is not a conflict between two unrelated interfaces.

If an interface is inherited along two paths that converge on **one single default declaration**, diamond inheritance itself does not necessarily cause an error. The problem is **distinct declarations with equivalent signatures and no clear override relationship**.

### 3.3. Two unrelated defaults cause a compile error

~~~java
interface AuditName {
    default String name() {
        return "audit";
    }
}
interface MetricName {
    default String name() {
        return "metric";
    }
}

// INTENTIONALLY BROKEN CODE, DOES NOT compile:
class Conflicted implements AuditName, MetricName {}
~~~

Both `AuditName` and `MetricName` declare `default name()` with the same signature, and neither interface is more specific than the other. Concrete class `Conflicted` must resolve this explicitly rather than Java picking based on `implements` order.

Proper fix:

~~~java
class Resolved implements AuditName, MetricName {
    @Override
    public String name() {
        return AuditName.super.name()
                + "+" + MetricName.super.name();
    }
}
~~~

This replaces `Conflicted` in the same context where `AuditName` and `MetricName` are declared; do not keep the uncompilable class in a built program. In `Resolved`, calls to each default are written explicitly, and the class decides how to combine them. You can equally choose just one default or implement new logic, provided the contract is satisfied.

**You cannot fix this by reordering `implements`**. Java does not use interface position in the list to arbitrate between two conflicting defaults.

### 3.4. One abstract and one unrelated default can still conflict

~~~java
interface A {
    default void execute() {}
}
interface B {
    void execute();
}

// INTENTIONALLY BROKEN CODE: inheritance conflict must be resolved.
abstract class Unresolved implements A, B {}
~~~

When an interface or class simultaneously inherits override-equivalent methods from two unrelated superinterfaces—one default and the other abstract—**you cannot assume the default automatically satisfies the abstract one**. This also requires an explicit override:

~~~java
class Fixed implements A, B {
    @Override
    public void execute() {
        A.super.execute();
    }
}
~~~

Choosing to delegate to `A.super.execute()` is a **semantic decision**. Sometimes `B` imposes requirements that `A`'s implementation does not fulfill; in that case write custom logic rather than delegating to the default merely to satisfy `javac`.

JLS §9.4.1.3 specifies signature equivalence rules when inheriting multiple methods. More complex cases also depend on erasure, covariant returns, generic methods, bridge methods, and accessibility; verify actual signatures in both source and bytecode before changing an API.

## 4. Java 17+ program demonstrating the rules

Create **`DefaultRulesDemo.java`** with the following complete contents:

~~~java
import java.util.Locale;

public final class DefaultRulesDemo {
    interface MessageService {
        String transform(String input);

        default boolean supportsAdvanced() {
            return false;
        }
    }

    static class LegacyPlugin implements MessageService {
        @Override
        public String transform(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    static final class NewPlugin extends LegacyPlugin {
        @Override
        public boolean supportsAdvanced() {
            return true;
        }
    }

    interface Audit {
        default String label() {
            return "audit";
        }
    }

    interface Metric {
        default String label() {
            return "metric";
        }
    }

    static final class Combined implements Audit, Metric {
        @Override
        public String label() {
            return Audit.super.label() + "+" + Metric.super.label();
        }
    }

    static class ParentClass {
        public String label() {
            return "class";
        }
    }

    interface Tagged {
        default String label() {
            return "interface";
        }
    }

    static final class ClassWins
            extends ParentClass implements Tagged {}

    interface Parent {
        default String label() {
            return "parent";
        }
    }

    interface Child extends Parent {
        @Override
        default String label() {
            return "child";
        }
    }

    static final class MostSpecific implements Child {}

    public static void main(String[] args) {
        MessageService legacy = new LegacyPlugin();
        MessageService modern = new NewPlugin();

        System.out.println("legacy=" + legacy.transform("hello"));
        System.out.println("legacy-advanced="
                + legacy.supportsAdvanced());
        System.out.println("modern=" + modern.transform("world"));
        System.out.println("modern-advanced="
                + modern.supportsAdvanced());

        System.out.println("combined=" + new Combined().label());
        System.out.println("class-wins=" + new ClassWins().label());
        System.out.println("specific=" + new MostSpecific().label());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 DefaultRulesDemo.java
java DefaultRulesDemo
~~~

**Exact expected stdout:**

~~~text
legacy=HELLO
legacy-advanced=false
modern=WORLD
modern-advanced=true
combined=audit+metric
class-wins=class
specific=child
~~~

Explanation of each output group:

- `LegacyPlugin` implements only `transform`, yet `supportsAdvanced` can be called via the default. It returns `false`, not claiming support for the new feature.
- `NewPlugin` inherits `transform`'s implementation and overrides `supportsAdvanced` to return `true`. This is **explicit opt-in**.
- `Combined` is forced to arbitrate between `Audit` and `Metric`, calling both defaults via `Audit.super` and `Metric.super`.
- `ClassWins` inherits `ParentClass.label()`; the class method is chosen over `Tagged`'s default.
- `MostSpecific` receives `label()` from `Child` because `Child` overrides `Parent`.

This program runs in a single compilation unit with interfaces and classes as **nested types** for convenient experimentation. In real plugins, API interfaces should be public top-level types in a shared artifact, not nested inside a demo class.

## 5. Why defaults help evolve a service contract

Suppose a platform initially defines only:

~~~java
// API v1: demo.api.TextService
package demo.api;

public interface TextService {
    String apply(String text);
}
~~~

Prebuilt v1 plugins provide `apply`. In API v2, the host wants to ask providers whether they support an advanced mode. If it adds:

~~~java
// API v2: demo.api.TextService
package demo.api;

public interface TextService {
    String apply(String text);

    default boolean supportsAdvanced() {
        return false;
    }
}
~~~

For v1 provider classes **with no method conflict**, the default allows host v2 to invoke `supportsAdvanced()` even though the plugin class was never recompiled. The host can continue calling `apply(...)` on old providers. This is a major advantage when deploying plugins independently.

However, three questions must be answered:

1. **Does the new name/signature conflict with any public method on providers or other interfaces?** If a provider has a method of the same name with an incompatible return type, recompiling can fail; if an unrelated interface adds an equivalent default, a conflict can arise.
2. **Is the default semantically valid?** For a new capability, returning `false` or a strictly specified no-op is usually safer than turning the feature on automatically.
3. **Is API v2 actually loaded at runtime?** A plugin manager/class loader might accidentally load API v1 from another JAR; a v2 client calling a method absent from the runtime interface risks `NoSuchMethodError`. Defaults cannot fix classpath/class identity bugs.

Preserve the interface's **binary name**, method names, and descriptors of existing methods so old callers do not break. Changing parameter types, return types, static/instance kinds, or removing a method is not a simple "minor version bump"; it requires a migration plan and bytecode verification.

## 6. Two-version experiment: old plugin, new host

The following experiment genuinely compiles **`plugin-old.jar` against `api-v1.jar`**, then never rebuilds the plugin. Next, it compiles only the host against `api-v2.jar` and runs with the v2 API. That tests compatibility of **an old binary**, not merely compiling all source together once.

### 6.1. File tree

Paths relative to **`spi-evolution/`**:

~~~text
spi-evolution/
├── api-v1/demo/api/TextService.java
├── api-v2/demo/api/TextService.java
├── plugin/demo/plugin/UpperPlugin.java
├── host/demo/host/Host.java
├── resources/META-INF/services/demo.api.TextService
├── build/                          (created by javac)
└── dist/                           (created by jar)
~~~

Both `TextService.java` files share the **same package and binary name**, living in independent directories. Put **only one API version at a time** on the compile or runtime classpath. Do not bundle both `api-v1.jar` and `api-v2.jar` together expecting "Java to pick the newer one automatically."

### 6.2. API v1

File **`api-v1/demo/api/TextService.java`**:

~~~java
package demo.api;

public interface TextService {
    String apply(String text);
}
~~~

### 6.3. API v2 adding a default

File **`api-v2/demo/api/TextService.java`**:

~~~java
package demo.api;

public interface TextService {
    String apply(String text);

    default boolean supportsAdvanced() {
        return false;
    }
}
~~~

Note that **`apply(String)`** keeps the exact same signature across both versions. V2 only adds an instance method with a default implementation.

### 6.4. Provider built exclusively against API v1

File **`plugin/demo/plugin/UpperPlugin.java`**:

~~~java
package demo.plugin;

import demo.api.TextService;
import java.util.Locale;

public final class UpperPlugin implements TextService {
    public UpperPlugin() {}

    @Override
    public String apply(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

File **`resources/META-INF/services/demo.api.TextService`** contains one line:

~~~text
demo.plugin.UpperPlugin
~~~

The classpath SPI descriptor is named after the **fully qualified name of the interface**; its content is the binary name of the implementation. The plugin JAR **contains no copy of `TextService.class`**: the API must come from the host's shared classpath. The public no-arg constructor lets `ServiceLoader` on the classpath instantiate the provider.

### 6.5. Host compiled against API v2

File **`host/demo/host/Host.java`**:

~~~java
package demo.host;

import demo.api.TextService;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        int providers = 0;

        for (TextService provider :
                ServiceLoader.load(TextService.class)) {
            System.out.println("provider="
                    + provider.getClass().getName());
            System.out.println("basic=" + provider.apply("hi"));
            System.out.println("advanced="
                    + provider.supportsAdvanced());
            providers++;
        }
        System.out.println("count=" + providers);
    }
}
~~~

The host knows only the v2 `TextService` interface. It does not import `UpperPlugin` at compile time and does not reference the implementation class by name.

### 6.6. Build commands in exact version order

Using JDK 17+ and a bash/POSIX shell, inside **`spi-evolution/`**:

~~~bash
mkdir -p build/api-v1 build/api-v2 build/plugin build/host dist

javac --release 17 -encoding UTF-8 -d build/api-v1 api-v1/demo/api/TextService.java
jar --create --file dist/api-v1.jar -C build/api-v1 .

# Old plugin: compiled against API v1.
javac --release 17 -encoding UTF-8 -cp dist/api-v1.jar -d build/plugin plugin/demo/plugin/UpperPlugin.java
jar --create --file dist/plugin-old.jar -C build/plugin . -C resources .

# New API and new host: do NOT recompile plugin-old.jar.
javac --release 17 -encoding UTF-8 -d build/api-v2 api-v2/demo/api/TextService.java
jar --create --file dist/api-v2.jar -C build/api-v2 .
javac --release 17 -encoding UTF-8 -cp dist/api-v2.jar -d build/host host/demo/host/Host.java

# Runtime has only API v2 and the old plugin JAR.
java -cp "build/host:dist/api-v2.jar:dist/plugin-old.jar" demo.host.Host
~~~

**Exact expected stdout:**

~~~text
provider=demo.plugin.UpperPlugin
basic=HI
advanced=false
count=1
~~~

When `UpperPlugin` was compiled, `supportsAdvanced()` **did not yet exist**. At runtime, the JVM sees the v2 `TextService` API and the provider compiled against v1. Because the provider does not override the new method, the call resolves to the default implementation returning `false`.

On Windows in PowerShell/CMD, the classpath separator is **;** instead of **:**; `mkdir -p` is bash syntax. Directories and files must match the stated paths; do not include a duplicate copy of `TextService.class` inside `plugin-old.jar`.

Inspection commands:

~~~bash
jar --list --file dist/api-v2.jar
jar --list --file dist/plugin-old.jar
javap -public -classpath dist/api-v2.jar demo.api.TextService
javap -public -classpath dist/plugin-old.jar demo.plugin.UpperPlugin
~~~

Look for `TextService.class` in **`api-v2.jar`**, and `UpperPlugin.class` plus `META-INF/services/demo.api.TextService` in **`plugin-old.jar`**. `javap` on API v2 shows `supportsAdvanced()`; `javap` on `plugin-old` does not list a compiler-injected implementation inside the plugin, because the default resides on the **runtime interface**.

This is a **binary reuse** experiment, not a proof that every default change on every API is safe. It intentionally uses a single interface with no method name conflicts and no other dependencies.

## 7. Default collision during upgrades: a more dangerous scenario

### 7.1. Source collision

Consider a third-party plugin:

~~~java
interface Red {
    default String label() {
        return "red";
    }
}
interface Blue {
    default String label() {
        return "blue";
    }
}

// Does not compile if Red and Blue have no override relationship.
class Dual implements Red, Blue {}
~~~

If `Blue` previously lacked `label()`, the old `Dual` class may have compiled cleanly and used `Red.label()`. When `Blue`'s author **adds `default label()`**, recompiling `Dual` fails because the class inherits two conflicting methods from two unrelated interfaces.

The same can happen with a public method in another library sharing the signature of a newly added method. Migration testing must cover realistic combinations of interfaces that third-party plugins implement, not just host-owned sample classes.

### 7.2. Binary collision with an un-recompiled plugin class

Java SE 17 JLS §13.5.7 gives an example: **adding a default method** is defined as a binary-compatible change, yet when an old binary invokes a method in a situation with two conflicting defaults, the invocation can throw **`IncompatibleClassChangeError`**.

The standalone lab reproduces this by replacing only `Right.class` at runtime while keeping **`Both.class` and `Run.class` as old binaries**. Example root directory **`binary-clash/`**:

~~~text
binary-clash/
├── old/Left.java
├── old/Right.java
├── old/Both.java
├── old/Run.java
├── new/Right.java
└── build/                (created on compile)
~~~

File **`old/Left.java`**:

~~~java
public interface Left {
    default String name() {
        return "left";
    }
}
~~~

File **`old/Right.java`**:

~~~java
public interface Right {
}
~~~

File **`old/Both.java`**:

~~~java
public final class Both implements Left, Right {
}
~~~

File **`old/Run.java`**:

~~~java
public final class Run {
    public static void main(String[] args) {
        System.out.println(new Both().name());
    }
}
~~~

File **`new/Right.java`**:

~~~java
public interface Right {
    default String name() {
        return "right";
    }
}
~~~

These files sit in the **default package** only to keep the example short and the binary upgrade easy to observe; real products should use packages under a stable namespace.

Compile the old version first, then compile **only the new interface**:

~~~bash
mkdir -p build/old build/new

javac --release 17 -encoding UTF-8 -d build/old old/*.java
java -cp build/old Run

javac --release 17 -encoding UTF-8 -d build/new new/Right.java
java -cp "build/new:build/old" Run
~~~

The first run prints exactly:

~~~text
left
~~~

The second run is **expected to fail with `IncompatibleClassChangeError` at invocation** when the JVM has to resolve `name()` defaults from `Left` and `Right` with no precedence relationship. Exact error messages and stack traces vary across JDK versions, so there is **no fixed stdout** for the failing run. The new `Right.class` is first on the classpath while old `Both.class` and `Run.class` remain untouched.

If instead of keeping old binaries you try **recompiling `Both.java` against the new `Right`**, `javac` reports the inheritance conflict earlier. This is a crucial distinction between **source compatibility** and **binary compatibility that fails at call time**.

There is one canonical fix: update `Both`'s code to explicitly implement/override `name()`, and rebuild the provider. If you do not control the old plugin's source, the API author must consider **renaming the new method, using a separate extension interface, or rolling back the conflicting default**. Do not attempt to work around it by haphazardly reordering the classpath, as that merely picks the wrong API version.

## 8. Choosing how to evolve an SPI: default or extension interface?

A service contract can grow capabilities in several ways:

**Approach A — add a conservative default:** use when a **semantically valid** fallback exists and the host can operate validly with un-upgraded plugins. For instance, `supportsAdvanced()` returning `false`. The advantage is preserving runtime compatibility for old providers when no method collision exists.

**Approach B — create an extension interface:** if a capability is genuinely new and cannot have a safe default implementation, declare a new interface extending the original:

~~~java
// Illustrative code: these are top-level interfaces in separate files.
public interface TextService {
    String apply(String input);
}

public interface BatchTextService extends TextService {
    java.util.List<String> applyBatch(
            java.util.List<String> inputs);
}
~~~

The snippet above illustrates **two separate files**; you cannot place both public top-level interfaces verbatim into a single `.java` file. An old plugin implementing only `TextService` keeps using basic functionality. A new plugin implementing `BatchTextService` is obligated to provide `applyBatch(...)`.

When the host looks up providers, it must check the capability explicitly, for example:

~~~java
// Integration code: assumes provider is an already-instantiated TextService.
if (provider instanceof BatchTextService batch) {
    var outputs = batch.applyBatch(java.util.List.of("a", "b"));
    // Handle batch results per contract.
}
~~~

This condition relies on `BatchTextService`'s type identity. If plugin and host load two copies of the API via different `ClassLoader`s, even the same fully qualified name is **not necessarily the same type**; the stable API must be shared in a common loader. For SPIs with custom registries, the host can separate old/new service types and perform versioned discovery.

**Approach C — new interface version or adapter:** when core semantics change (data types, error model, sync/async, security), create a separate V2 contract and a tested adapter. Do not force every plugin to receive a no-op default while advertising full V2 compliance.

**Approach D — add an abstract method:** can preserve JLS binary compatibility for old `.class` files, yet old provider source usually **cannot recompile** without implementing the method; and if the host invokes the new abstract method on an old provider lacking an implementation, **`AbstractMethodError`** can occur. Do not confuse the binary compatibility of "adding an abstract declaration" with actual runtime usability of plugins.

## 9. Other changes that also affect contracts even without defaults

| Change | Risk | How to manage |
| --- | --- | --- |
| Add default method | Signature collision or changed semantics when provider does not override | Choose low-collision names, conservative behavior, matrix testing |
| Add abstract method | Old providers lack implementation at compile/invoke time | Extension interface or new adapter/version |
| Remove/rename method | Old callers may hit `NoSuchMethodError` | Keep wrapper/deprecation, phased migration |
| Change parameters or return type | Alters JVM descriptor; overload/override behavior may change | Build new method, retain old method via adapter |
| Change instance to static or vice versa | Can cause `IncompatibleClassChangeError` | Do not change method kind in a stable API |
| Change declared checked exceptions | Affects source compatibility, though JVM does not put `throws` in descriptor | Define migration, compile-test clients |
| Change default semantics | Old plugins run yet business behavior is wrong | Contract tests on old versions |
| Add default matching `Object` methods like `toString` | Java forbids declaring such defaults | Use a helper name or override in a class |
| Add method with conflicting erasure/return | Compile errors, bridge/generic incompatibility | Test generic subtyping and bytecode descriptors |
| Bundle another copy of API in plugin JAR | Different class identity if loaders differ | Shared API provided by host/parent loader |
| Change Java target/runtime requirement | Plugin/host cannot run on older JRE | Publish JDK baseline, build with appropriate `--release` |

**Do not diagnose an exception by name alone.** `NoSuchMethodError` usually suggests a method reference could not be found in the runtime ABI; `AbstractMethodError` usually suggests an abstract contract was found yet the implementation lacked a suitable body; `IncompatibleClassChangeError` has multiple causes, including default conflicts and static/instance mismatches. Preserve stack traces, inspect the runtime API JAR, class loaders, and source/bytecode versions before deciding on a fix.

## 10. Steps for safely upgrading a plugin contract

A practical plan should follow this order:

1. **Document the v1 contract:** fully qualified interface names, public methods, generic signatures, exception semantics, nullability, thread-safety, callback lifecycle, and supported capabilities. Archive the API v1 artifact.
2. **Inventory existing providers:** which classes implement additional interfaces, whether any have public methods matching new names, which JVM/JDK versions are used, and which class loader owns the API.
3. **Evaluate the new method:** is there a business-valid fallback? Can a conservative `false`/no-op default work safely? Is a separate extension interface needed?
4. **Design source-compatibility tests:** recompile representative provider sources against API v2; catch override/covariant return/generic erasure errors early.
5. **Design binary-compatibility tests:** keep `plugin-old.jar` built against API v1 unchanged and run under host v2. This is essential: rebuilding everything together against API v2 does not test independent upgrades.
6. **Test multiple superinterfaces:** include providers implementing multiple independent interfaces, especially with matching method names/signatures; check both compile-time conflicts and invocation-time failures.
7. **Test `ServiceLoader`/runtime:** provide only one copy of the API in the proper shared loader; verify descriptors, public constructors on the classpath, dependencies, and real provider loading.
8. **Test default behavior:** old plugins lacking the new capability must be filtered/selected properly rather than routed into unsupported features. Check nulls, edge inputs, error handling, and side effects.
9. **Establish a version policy:** distinguish main API versions from optional capabilities; deprecate old methods before removal; publish a compatibility matrix and support window.
10. **Observe and prepare rollback:** log plugin ID, API version, loader, linkage errors, and capability negotiation; if an upgrade hits a collision, be ready to roll back to a compatible artifact/API or isolate via a separate adapter/version.

A repository can use Maven/Gradle to automate tests across multiple JDKs; the rule stays unchanged: **keep old provider binaries** as fixtures. Tests containing only new provider source cannot catch every runtime failure in environments where users have not upgraded plugins.

## 11. Distinguishing deployment errors from API evolution errors

If a plugin is not found by `ServiceLoader`, do not jump to blaming a new default method:

| Symptom | Primary suspect | Verification step |
| --- | --- | --- |
| 0 providers | Missing or misnamed `META-INF/services`, JAR not on classpath/loader | `jar --list`, loader context, descriptor |
| `ServiceConfigurationError` while iterating | Wrong provider class, unsuitable constructor, different API identity, or init error | Stack trace/cause and provider name |
| `NoSuchMethodError` when host calls new method | Old runtime API, or method removed/changed descriptor | `javap` on actual loaded API, JAR version |
| `AbstractMethodError` | Host calls abstract method lacking a suitable implementation on runtime provider | Compare abstract/default methods in API vs provider binary |
| `IncompatibleClassChangeError` on default method | Possible two unrelated defaults or static/instance change | Inspect superinterfaces and JLS method resolution |
| `javac` error when rebuilding plugin | Default conflict, return type/generic/visibility mismatch, or new abstract method | Compile fixture provider against API v2 |
| Runs yet capability is wrong | Default semantics unsuitable for old plugin | Behavioral contract tests and opt-in |
| `ClassCastException` or "not a subtype" | Host/plugin loaded interface copies through different `ClassLoader`s | Compare defining loaders and API class origin |
| Right method yet strange behavior | Changed default body, accidental override, dependency mismatch | Log selected implementation, diff semantics tests |

Useful commands:

~~~bash
jar --list --file dist/plugin-old.jar
javap -public -classpath dist/api-v1.jar demo.api.TextService
javap -public -classpath dist/api-v2.jar demo.api.TextService
javap -public -classpath dist/plugin-old.jar demo.plugin.UpperPlugin
~~~

For complex classes, add `javap -c -p` to inspect bytecode and bridge methods (if any). Always inspect the **actual runtime JAR being loaded**, not random files on disk; classpath order, parent delegation, and `ModuleLayer` can cause Java to load a different artifact than operators assume.

## 12. Exercises and knowledge check criteria

**Exercise A — conservative upgrade:** In the `spi-evolution` lab, keep `plugin-old.jar` unchanged and change `supportsAdvanced()`'s default from `false` to `true`. The host still runs, yet explain why `advanced=true` **does not prove the old provider supports a new operation**. Choose a better contract accordingly.

**Exercise B — override from a new provider:** Write a v2 plugin overriding `supportsAdvanced()` to return `true`; build it separately against `api-v2.jar` and compare with `plugin-old.jar`. Ensure you do not accidentally place two conflicting descriptors into the same JAR/classpath.

**Exercise C — source conflict:** Add an independent interface with a default `supportsAdvanced()` to the provider's `implements` list; recompile against API v2. Resolve the collision with an explicit override and evaluate the semantics of both interfaces.

**Exercise D — binary conflict:** In `binary-clash`, keep old `Both.class`/`Run.class` and replace only `Right.class`. Record the runtime error, then rebuild `Both` with a valid `name()` override; compare compile-time and runtime behavior.

**Exercise E — class wins:** In `DefaultRulesDemo`, change `ParentClass.label()` to another value and re-run. Observe that the class method wins even though `Tagged` has a default.

**Exercise F — abstract vs default:** Add a new abstract method to `TextService` v2, recompile the old plugin, and analyze the error. If old plugins must keep running while the host does not yet require the new capability, weigh a conservative default, an extension interface, or an adapter.

**Exercise G — class loader:** Intentionally package `api-v1.jar` inside the plugin JAR and have the plugin loader define its own interface instead of sharing the host-supplied API. Analyze why two types with the exact same binary name still cannot be assigned to each other. Do this only in an isolated lab.

**Completion criteria:** you should accurately explain (1) why defaults can preserve old provider binaries, (2) when conflicts between two defaults require an override, (3) how class-wins and most-specific-interface rules work, (4) differences among source/binary/behavioral compatibility, (5) the meaning of `NoSuchMethodError`, `AbstractMethodError`, and `IncompatibleClassChangeError`, (6) when to prefer an extension interface over a default, and (7) why upgrade tests must use genuine old plugin binaries.

## 13. References

- [Java Language Specification SE 17 — Chapter 9: Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html), especially §9.4 and §9.4.1.3 on defaults, overriding, and signature conflicts.
- [Java Language Specification SE 17 — Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html), especially §13.5.4 and §13.5.7 on interface evolution and default methods.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) on provider discovery and instantiation.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html) on inspecting classfiles and method declarations.

**Conclusion:** default methods are a powerful SPI upgrade tool when paired with **correct, conservative fallbacks**, yet they do not eliminate multiple-inheritance conflicts or semantic risks. Use explicit overrides to resolve conflicts, keep one shared API copy at runtime, test both source and binaries of old plugins, and choose an extension interface or new version when a capability has no valid default.
