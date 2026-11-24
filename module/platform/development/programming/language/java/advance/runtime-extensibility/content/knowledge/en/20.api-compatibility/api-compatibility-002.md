# Impact of Adding, Removing, or Changing Interface Method Signatures

## 1. Why do interface changes break old plugins?

In runtime-extensible applications, host and plugins are often compiled, released, and deployed at different times. A library publishes an interface for third parties to implement, and later the library changes its API. The JVM does not automatically recompile already-released plugin JARs; it executes `.class` files and method references recorded in bytecode.

Suppose API v1 publishes:

~~~java
package demo.spi;

public interface Handler {
    String execute();
}
~~~

A plugin is compiled against API v1:

~~~java
package demo.impl;

import demo.spi.Handler;

public final class LegacyHandler implements Handler {
    @Override
    public String execute() {
        return "legacy";
    }
}
~~~

Later, API v2 adds a mandatory method:

~~~java
package demo.spi;

public interface Handler {
    String execute();
    String version();
}
~~~

Recompiling `LegacyHandler` source against API v2 will fail because the class does not implement `version()`. However, **v1 `LegacyHandler.class`** can still be loaded and have `execute()` invoked. Only when the new host calls `version()` on the old object does the JVM fail to find a concrete implementation and possibly throw **`AbstractMethodError`**.

**The question to ask is not only “does the new API compile?”, but “do old source, old binaries, and runtime behavior remain compatible?”** That is the core of Java API compatibility.

## 2. Three layers of compatibility to distinguish

| Layer | Question | Testing |
|---|---|---|
| **Source compatibility** | Does old client/implementer source recompile against the new interface? | Recompile old source + API v2 |
| **Binary compatibility** | Do old `Client.class` and `plugin.class` continue linking against the new interface without rebuilding? | Keep old binaries, swap runtime API |
| **Behavioral compatibility** | Do methods still perform the right work, returning values and errors per the old contract? | Contract/integration tests across versions |

According to the **Java Language Specification (JLS) Chapter 13**, binary compatibility focuses on whether pre-existing binaries continue to link. A change may be deemed **binary-compatible** by the JLS while recompiling old source fails or a new call on an old instance throws an error.

Examples of such differences:

- Adding an abstract method can preserve binary compatibility yet break source compatibility for old concrete implementers.
- Adding a default method can preserve calling the new method yet change semantics or cause default conflicts.
- Adding an overload preserves old bytecode calls, yet old code upon recompilation may pick the new overload.
- Changing a return type can look “reasonable” in Java source yet alter the JVM descriptor.

With SPI/`ServiceLoader`/`URLClassLoader`, it is even more critical to test **old plugin JAR + new host API**, because plugins may be released by third parties outside your source repository.

## 3. Java source signatures and JVM descriptors are not identical

In Java source, methods are distinguished by method signature (name and parameter types per JLS rules); **return type alone is not enough to overload**:

~~~java
// Invalid: two declarations with the same Java signature.
interface Wrong {
    String get();
    Object get();
}
~~~

In a class file, the **JVM method descriptor** contains **parameter descriptors and the return descriptor**. Examples:

| Java method | JVM descriptor |
|---|---|
| **void reset()** | **()V** |
| **String execute()** | **()Ljava/lang/String;** |
| **Object execute()** | **()Ljava/lang/Object;** |
| **void save(int n)** | **(I)V** |
| **void save(long n)** | **(J)V** |
| **String find(String id)** | **(Ljava/lang/String;)Ljava/lang/String;** |
| **void send(String... names)** | **([Ljava/lang/String;)V** |

**V** denotes `void`, **I** is `int`, **J** is `long`, **L...;** denotes a reference type, and **[** is an array. Class names in descriptors use forward slashes between package segments.

Because the descriptor includes the return type, two interfaces with methods:

~~~java
// V1:
String execute();

// V2:
Object execute();
~~~

do not have the same descriptor, even though the Java source methods share the same name and parameter list. An old `caller.class` may still reference **`execute:()Ljava/lang/String;`**; it does not automatically switch to **`execute:()Ljava/lang/Object;`** when the JVM loads the new API. Covariant returns in certain overriding scenarios can cause the compiler to emit a bridge, yet **you cannot assume by default that a bridge preserves the ABI of an interface whose declaration was altered**.

Similarly, changing **`save(int)`** to **`save(long)`** changes the descriptor from **`(I)V`** to **`(J)V`**. The Java compiler can widen `int` to `long` in a new source call, but an old `.class` file does not re-run overload resolution.

**Command to inspect an API's descriptors:**

~~~bash
javap -classpath api.jar -s -p demo.spi.Handler
~~~

The **`javap -c -p`** command helps inspect instructions of an old caller, especially **`invokeinterface`**, and confirm the exact symbol the client compiled against.

## 4. Impact matrix of interface changes

| Change | Recompiling old source | Old binaries | Runtime risk |
|---|---|---|---|
| **Add abstract method** | Concrete implementer missing the method usually fails to compile | Binary-compatible per JLS | New caller calling old object: **`AbstractMethodError`** |
| **Add default method** | Usually requires no implementation; may clash | Binary-compatible per JLS rules | Default conflict: **`IncompatibleClassChangeError`**; behavior changes |
| **Add static/private method** | Creates no extra instance obligation | Binary-compatible | Source naming/overloads or internal logic may be affected |
| **Add overload with different parameters** | May alter overload resolution or cause ambiguity | Old callers keep invoking the already-chosen descriptor | Behavior differs between old and rebuilt callers |
| **Remove method** | Old clients calling the method fail to compile | Can be binary-incompatible | **`NoSuchMethodError`** if symbol no longer resolves |
| **Rename method** | Clients and implementers must update | Equivalent to removing old name + adding new name | **`NoSuchMethodError`** |
| **Change parameter count/types** | Call sites may need updates | Old descriptor disappears unless overload is kept | **`NoSuchMethodError`** |
| **Change return type with different erasure** | Both callers and providers may need updates | Return descriptor changes | **`NoSuchMethodError`** or dispatch errors |
| **Change throws clause** | Callers may need to update catch/throws | Descriptor unchanged | Behavior/checked exception contract changes |
| **Change generic arguments with same erasure** | Type compatibility may break | Usually preserves descriptor | Cast errors/semantics issues can occur |
| **Change default to abstract** | Old implementations may lack a body | Not a safe evolution at invocation level | Possible **`AbstractMethodError`** |

This table is a guiding rule, **not a guarantee that every situation throws one exact error type**. For example, removing a method from a specific interface while a matching declaration remains in a superinterface may still resolve. When diagnosing, inspect the actual runtime hierarchy and bytecode.

## 5. Adding an abstract method: being linkable does not mean callable

API v1 has only **`execute()`**; API v2 adds abstract **`String version()`**. Two tests produce different results:

**A. Recompile `LegacyHandler.java` against API v2.** The Java compiler requires concrete classes to provide an implementation for `version()`. This is a **source compatibility** failure.

**B. Do not recompile v1 `LegacyHandler.class`; run against API v2.** Per JLS §13.5.4, adding an abstract interface method does not by itself break binary compatibility of pre-existing binaries. The old plugin class can still load and run `execute()`.

However, a new host compiled against API v2 calling **`Handler.version()`** on v1 `LegacyHandler` will not find a suitable implementation and may throw **`AbstractMethodError`**. The error occurs at **invocation**, not necessarily at class load time.

~~~text
Handler v1: execute()
       |
       +---- LegacyHandler v1: implements execute()
                         |
                         +---- Handler v2: execute(), version()
                                            |
                                            +-- execute() -> OK
                                            +-- version() -> AbstractMethodError
~~~

Therefore, if an interface is a **third-party implemented SPI**, do not add an abstract method and assume all old plugins can fulfill it. Use a **semantically valid default method**, a **capability interface**, or a policy requiring plugin upgrades.

## 6. Adding a default method: usually safer, not absolute

A default method has an implementation in the interface:

~~~java
public interface Handler {
    String execute();

    default String version() {
        return "unknown";
    }
}
~~~

Old plugins can inherit the default `version()`. Yet important conditions apply:

1. **Fallback behavior must be valid.** `"unknown"` must not be treated as a verified version if the host requires an exact version.
2. **Class methods can beat interface defaults.** Methods on a class or superclass are selected according to the corresponding dispatch rules.
3. **Conflicts among multiple defaults.** An old class implements two independent interfaces; when both later add defaults with the same signature, the JVM may throw **`IncompatibleClassChangeError`** at call time.
4. **Changing a default's implementation** alters behavior even though the descriptor stays unchanged.
5. **A same-named method already present in a class** may unexpectedly count as an override of the new interface method, producing unintended semantics.

Conceptual example:

~~~java
interface Left {
    default String label() { return "left"; }
}

interface Right { }

final class Both implements Left, Right { }
~~~

If a new version of `Right` also provides **`default String label()`**, a `Both.class` compiled against old `Right` can hit a conflict when the JVM resolves the method. JLS §13.5.7 describes how this throws **`IncompatibleClassChangeError`**; rebuilding source may report a compile error before runtime. The two error types do not contradict each other because one is new source and the other is old binary.

**Practical rule:** Default methods are useful for extending an ABI, yet they do not eliminate business-contract design or testing every released plugin.

## 7. Adding static, private methods, or overloads

A Java 17 interface can contain static methods and private helpers:

~~~java
public interface Handler {
    String execute();

    static String normalize(String s) {
        return s == null ? "" : s.strip();
    }

    private static String fallback() {
        return "none";
    }

    default String display() {
        String text = normalize(execute());
        return text.isEmpty() ? fallback() : text;
    }
}
~~~

Adding static or private methods **does not force plugins to implement an extra instance abstract method**, and the JLS treats it as binary-compatible. However, **`display()`** is a new default method, so conflicts and behavior still need evaluation as in section 6.

Adding an overload carries a different kind of risk:

~~~java
// V1:
interface Format {
    String apply(Object value);
}

// V2 adds overload:
interface Format {
    String apply(Object value);
    String apply(String value);
}
~~~

An old caller compiled **`apply("hello")`** when only **`apply(Object)`** existed. The old binary still references the `apply(Object)` descriptor. If the client is recompiled against API v2, the Java compiler may select `apply(String)`, and the two versions run with different behavior. Adding an **`apply(Integer)`** overload alongside `apply(String)` can also make **`apply(null)`** ambiguous upon recompilation.

**Overload resolution happens at compile time**, not re-evaluated whenever an API JAR is swapped.

## 8. Removing a method: impact on old `caller.class`

Suppose v1 has:

~~~java
public interface Handler {
    String execute();
}
~~~

V3 removes `execute()`:

~~~java
public interface Handler {
    // No longer has execute().
}
~~~

An old `client.class` already contains a symbolic reference to **`demo/spi/Handler.execute:()Ljava/lang/String;`**. If the runtime interface/hierarchy no longer has a matching method, that reference fails to resolve, so the JVM can throw **`NoSuchMethodError`**.

A common misconception is that **old `LegacyHandler.class` still defines `execute()`**. That does not rescue an old client's **`invokeinterface Handler.execute`** call: the JVM must resolve the method declaration on the interface first before dispatching to an implementation.

**Distinguish the two errors:**

- **`NoSuchMethodError`:** symbolic method reference can no longer be resolved with that name/descriptor in the runtime API.
- **`AbstractMethodError`:** the method declaration resolves, yet no concrete method implementation exists for the receiver object.

Do not delete a public method simply because current host source no longer calls it. Old client/plugin JARs outside the repository may still reference that binary entry point.

## 9. Changing names, parameters, or return types is an ABI risk

### Renaming a method

~~~java
// V1:
String execute();

// V2:
String run();
~~~

If `execute()` is deleted and only `run()` remains, old callers do not automatically rename themselves. Compatible expansion:

~~~java
interface Handler {
    String execute();

    default String run() {
        return execute();
    }
}
~~~

Default behavior and conflicts still need checking. If the two names do not share the same semantics, create a new capability instead of a misleading adapter.

### Changing parameters

~~~java
// V1:
void publish(String text);

// V2:
void publish(String text, boolean urgent);
~~~

The old and new JVM descriptors differ. To preserve old clients:

~~~java
interface Publisher {
    void publish(String text);

    default void publish(String text, boolean urgent) {
        publish(text);
    }
}
~~~

However, the default ignores `urgent`; **if `urgent` has mandatory meaning**, the approach above can be functionally wrong. A new **`UrgentPublisher`** interface is more transparent.

### Changing return type

~~~java
// V1:
String execute();

// V2:
Object execute();
~~~

Even though `String` is a subtype of `Object`, the descriptor changes. Java source cannot declare two methods with the same name and parameters differing only by return type. To keep the old path, add a **different name**:

~~~java
interface Handler {
    String execute();

    default Object executeValue() {
        return execute();
    }
}
~~~

In some cases, the compiler may generate a **bridge method** to preserve polymorphism due to generics or covariant overriding. Do not assume that every interface ABI with a changed return type receives a proper bridge; verify with **`javap -v`** and test old `client.class`. Similarly, changing **`void refresh()`** to **`boolean refresh()`** changes the descriptor from **`()V`** to **`()Z`**.

## 10. Changes that do not necessarily alter descriptors

### Generics and type erasure

~~~java
// V1:
void accept(java.util.List<String> values);

// V2:
void accept(java.util.List<Integer> values);
~~~

Ordinarily both share the erased descriptor **`(Ljava/util/List;)V`**. Even so, source code may become incompatible, element-handling logic changes, and runtime may hit `ClassCastException`. Conversely, changing **`List<String>`** to **`Collection<String>`** changes the erasure and therefore changes the descriptor.

Changing a type variable's **first bound** can also change erasure even when generic names look identical.

### Throws clause

~~~java
// V1:
String read() throws java.io.IOException;

// V2:
String read() throws java.sql.SQLException;
~~~

Checked `throws` clauses are not in the JVM method descriptor. Changing `throws` usually does not break binary linkage yet can break source compatibility when callers recompile due to different checked exception handling. Runtime semantics of the thrown error type must also be evaluated.

### Varargs

~~~java
// V1:
void send(String[] values);

// V2:
void send(String... values);
~~~

Both share the JVM descriptor **`([Ljava/lang/String;)V`**. However, call syntax accepted by the compiler upon recompilation can differ, such as allowing multiple individual `String` arguments.

### Parameter names

Renaming parameters **`left, right`** to **`a, b`** does not change the descriptor. Yet frameworks relying on reflection parameter metadata, annotations, or data binding can still see behavioral impacts.

## 11. Java 17 example: one old `plugin.class` with three runtime APIs

The goal of this lab is **not recompiling the old `plugin.class`**. We build versions of `Handler.class` in separate directories and run them sequentially with old/new callers. The entire example uses Java 17+ and requires no external libraries.

### 11.1. Directory tree

~~~text
interface-evolution-demo/
├── src/
│   ├── v1/
│   │   ├── api/demo/spi/Handler.java
│   │   ├── impl/demo/impl/LegacyHandler.java
│   │   └── client/demo/client/OldClient.java
│   ├── v2/
│   │   ├── api/demo/spi/Handler.java
│   │   └── client/demo/client/NewClient.java
│   ├── v2-default/api/demo/spi/Handler.java
│   └── v3/api/demo/spi/Handler.java
└── build/     # created by compile commands
~~~

### 11.2. API v1 and plugin v1

**src/v1/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    String execute();
}
~~~

**src/v1/impl/demo/impl/LegacyHandler.java**

~~~java
package demo.impl;

import demo.spi.Handler;

public final class LegacyHandler implements Handler {
    @Override
    public String execute() {
        return "legacy";
    }
}
~~~

**src/v1/client/demo/client/OldClient.java**

~~~java
package demo.client;

import demo.spi.Handler;
import demo.impl.LegacyHandler;

public final class OldClient {
    public static void main(String[] args) {
        Handler handler = new LegacyHandler();
        try {
            System.out.println("removed=" + handler.execute());
        } catch (NoSuchMethodError error) {
            System.out.println("removed=NoSuchMethodError");
        }
    }
}
~~~

`OldClient` is compiled against API v1; it holds an old method reference to `Handler.execute()`. Catching `Error` in this example only demonstrates the failure mode and is not recommended production handling.

### 11.3. Abstract API v2 and new caller

**src/v2/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    String execute();
    String version();
}
~~~

**src/v2/client/demo/client/NewClient.java**

~~~java
package demo.client;

import demo.spi.Handler;
import demo.impl.LegacyHandler;

public final class NewClient {
    public static void main(String[] args) {
        Handler handler = new LegacyHandler();
        System.out.println("execute=" + handler.execute());

        try {
            System.out.println("version=" + handler.version());
        } catch (AbstractMethodError error) {
            System.out.println("version=AbstractMethodError");
        }
    }
}
~~~

### 11.4. API v2 with default `version()`

**src/v2-default/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    String execute();

    default String version() {
        return "v2-default";
    }
}
~~~

This is a drop-in replacement for abstract API v2, keeping **`version:()Ljava/lang/String;`** while providing a body. We will reuse the same `NewClient.class` and `LegacyHandler.class` to compare results.

### 11.5. API v3 removing `execute()`

**src/v3/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    // No longer has execute().
}
~~~

No superinterface provides an `execute()` declaration, so v1 `OldClient`'s method reference has nowhere to resolve.

### 11.6. Compile on Linux/macOS

Run from the **`interface-evolution-demo`** root:

~~~bash
mkdir -p build/v1-api build/impl build/old-client
mkdir -p build/v2-api build/new-client build/v2-default-api build/v3-api

javac --release 17 -encoding UTF-8 \
  -d build/v1-api src/v1/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 \
  -cp build/v1-api -d build/impl \
  src/v1/impl/demo/impl/LegacyHandler.java

javac --release 17 -encoding UTF-8 \
  -cp build/v1-api:build/impl -d build/old-client \
  src/v1/client/demo/client/OldClient.java

javac --release 17 -encoding UTF-8 \
  -d build/v2-api src/v2/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 \
  -cp build/v2-api:build/impl -d build/new-client \
  src/v2/client/demo/client/NewClient.java

javac --release 17 -encoding UTF-8 \
  -d build/v2-default-api \
  src/v2-default/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 \
  -d build/v3-api src/v3/api/demo/spi/Handler.java
~~~

Note the order: `build/impl` and `build/old-client` are built against API v1. Afterward, **do not recompile** those two artifacts. `NewClient` is compiled against API v2 while using the `LegacyHandler.class` already compiled from v1.

### 11.7. Compile on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/v1-api, build/impl, build/old-client, build/v2-api, build/new-client, build/v2-default-api, build/v3-api | Out-Null

javac --release 17 -encoding UTF-8 -d build/v1-api src/v1/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 -cp build/v1-api -d build/impl src/v1/impl/demo/impl/LegacyHandler.java

javac --release 17 -encoding UTF-8 -cp "build/v1-api;build/impl" -d build/old-client src/v1/client/demo/client/OldClient.java

javac --release 17 -encoding UTF-8 -d build/v2-api src/v2/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 -cp "build/v2-api;build/impl" -d build/new-client src/v2/client/demo/client/NewClient.java

javac --release 17 -encoding UTF-8 -d build/v2-default-api src/v2-default/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 -d build/v3-api src/v3/api/demo/spi/Handler.java
~~~

The **classpath separator** is **:** on Linux/macOS and **;** on Windows. In each run command, always put **exactly one** directory containing `demo/spi/Handler.class` on the classpath. Putting multiple API versions with the same name on the classpath can load an unintended copy.

### 11.8. Case A: adding an abstract method

Linux/macOS:

~~~bash
java -cp build/v2-api:build/impl:build/new-client demo.client.NewClient
~~~

Windows:

~~~powershell
java -cp "build/v2-api;build/impl;build/new-client" demo.client.NewClient
~~~

**Stdout:**

~~~text
execute=legacy
version=AbstractMethodError
~~~

`LegacyHandler.class` still runs `execute()`. The `version` declaration on `Handler` v2 exists, yet the old class does not implement `version()`, leading to `AbstractMethodError` when the new caller invokes it.

### 11.9. Case B: adding a default method

Linux/macOS:

~~~bash
java -cp build/v2-default-api:build/impl:build/new-client demo.client.NewClient
~~~

Windows:

~~~powershell
java -cp "build/v2-default-api;build/impl;build/new-client" demo.client.NewClient
~~~

**Stdout:**

~~~text
execute=legacy
version=v2-default
~~~

`NewClient.class` and `LegacyHandler.class` are kept unchanged. The runtime interface supplies a default `version()`, so Java has a suitable implementation to dispatch.

### 11.10. Case C: removing a method

Linux/macOS:

~~~bash
java -cp build/v3-api:build/impl:build/old-client demo.client.OldClient
~~~

Windows:

~~~powershell
java -cp "build/v3-api;build/impl;build/old-client" demo.client.OldClient
~~~

**Stdout:**

~~~text
removed=NoSuchMethodError
~~~

`OldClient.class` was compiled when `Handler.execute()` existed. `Handler` v3 no longer has a matching method declaration, so the old `invokeinterface` reference cannot resolve. Having `execute()` in `LegacyHandler.class` does not replace the declaration removed from the interface.

### 11.11. Inspecting class files with `javap`

~~~bash
javap -classpath build/v1-api -s demo.spi.Handler
javap -classpath build/v2-api -s demo.spi.Handler
javap -classpath build/v2-default-api -s demo.spi.Handler
javap -classpath build/v3-api -s demo.spi.Handler
javap -classpath build/old-client -c demo.client.OldClient
~~~

You will see `execute()` in v1/v2/v2-default, `version()` in v2/v2-default, and no `execute()` in v3. `OldClient.class` still references `Handler.execute()` exactly as compiled initially.

## 12. JVM errors to distinguish

| Error | Common cause | How to debug |
|---|---|---|
| **`AbstractMethodError`** | Method declaration exists, yet receiver lacks a concrete implementation | Inspect old implementer and method dispatch |
| **`NoSuchMethodError`** | Symbolic method reference name/descriptor cannot be resolved | Compare `javap` of v1 caller and v2 interface |
| **`IncompatibleClassChangeError`** | Incompatible invocation kind/hierarchy/default conflict | Inspect instance vs static, class/interface hierarchy |
| **`IllegalAccessError`** | Visibility/module access of method/type changed | Inspect public/export/encapsulation |
| **`VerifyError`** | Bytecode/hierarchy after change fails verification | Inspect classfile and superinterface relationships |

**`AbstractMethodError`** and **`NoSuchMethodError`** are subclasses of **`IncompatibleClassChangeError`**. They are `LinkageError`s, not checked business exceptions.

Reflection's **`NoSuchMethodException`** is a different exception from **`NoSuchMethodError`** when the JVM resolves a compiled call.

Binary evolution errors may surface lazily on the first time the JVM resolves/invokes a method; an application starting up does not prove all plugins/APIs are compatible.

## 13. Safe evolution approaches for public libraries

**Keep the old method and add an adapter method:**

~~~java
interface Handler {
    String execute();

    default String run() {
        return execute();
    }
}
~~~

This gives old callers and old plugins the existing entry point while new clients use `run()` if semantics are equivalent.

**Split a separate interface for new capabilities:**

~~~java
interface Handler {
    String execute();
}

interface VersionedHandler extends Handler {
    String version();
}
~~~

Host:

~~~java
// Illustrative snippet: handler obtained from plugin host.
if (handler instanceof VersionedHandler versioned) {
    System.out.println(versioned.version());
} else {
    System.out.println("Legacy plugin: version capability unavailable");
}
~~~

Old plugins continue implementing `Handler`; new plugins can implement `VersionedHandler`. The host knows when the capability is present without guessing.

**Deprecate before removing:**

~~~java
interface Handler {
    @Deprecated(since = "2.0", forRemoval = false)
    String execute();

    default String run() {
        return execute();
    }
}
~~~

The **`@Deprecated`** annotation is a migration signal, not an automatic ABI fix. Keep the old entry point if old binaries must be supported. Remove it only after a clear migration policy and release/version boundary.

**Version contracts when changes cannot be adapted:** Split `HandlerV1` and `HandlerV2` interfaces or publish a separate adapter rather than changing the descriptor of the same method name and assuming old plugins stay compatible.

**Do not use business-invalid fallbacks:** A default **`pay(amount, currency)`** that merely calls **`pay(amount)`** and ignores `currency` can be wrong in multi-currency transactions. Type/binary safety does not compensate for business logic bugs; use a capability interface or require a plugin upgrade if the new feature is mandatory.

## 14. Pre-release test matrix

| Build/run | To verify |
|---|---|
| Recompile old plugin source against new API | Implementer source compatibility |
| Recompile old client source against new API | Caller source compatibility, overload ambiguity |
| Old `plugin.class` + new API | Binary/link compatibility and method implementations |
| Old `client.class` + new API | Whether old symbolic references remain valid |
| New `client.class` + old `plugin.class` + new API | Default/capability/`AbstractMethodError` |
| Plugin implementing multiple interfaces | Default conflicts and dispatch |
| Compare method descriptors in API v1/v2 | Concrete ABI changes |
| Contract/integration tests | Behavioral compatibility |

In runtime extensibility, **keep old `.class`/JAR artifacts intact** rather than doing a clean rebuild of everything and concluding old binaries are still compatible. Run only against the **exact API version** you intend to test; two copies of an identically named interface from two class loaders can also cause class identity issues distinct from method signatures.

## 15. Misconceptions and self-check questions

**Misconception: “Adding an abstract method is binary-compatible, so it is definitely safe.”** False at invocation time: old implementers do not automatically gain the new body.

**Misconception: “Adding a default method never causes errors.”** Default conflicts and semantic changes can still occur.

**Misconception: “Changing return `String` to `Object` is merely widening the type.”** The JVM descriptor changes; old callers still reference the old descriptor.

**Misconception: “Changing `int` to `long` is widened by Java at runtime.”** A source compiler on new code can widen, yet old binaries do not re-select methods.

**Misconception: “The old class still has `execute()`, so `execute()` can be removed from the interface.”** Old `invokeinterface` references must resolve against the runtime interface/hierarchy.

**Misconception: “Changing `List<String>` to `List<Integer>` has no risk due to erasure.”** Erasure may preserve the descriptor, yet the source contract and runtime type safety still change.

**Question 1.** Does adding **`abstract flush()`** to an interface allow old `plugin.class` to link? What happens when host v2 calls `flush()`?

**Answer:** The JLS allows old binaries to continue linking when an abstract interface member is added, yet if the old class has no implementation, invoking it can throw `AbstractMethodError`.

**Question 2.** Why does removing a method from an interface cause `NoSuchMethodError` even when the implementing class has a method of the same name?

**Answer:** Old binaries use a symbolic reference to the interface method. If the method can no longer be resolved with the exact descriptor in the interface/hierarchy, the JVM cannot use that reference.

**Question 3.** Does adding an `apply(String)` overload cause old bytecode calling `apply(Object)` to switch to `String`?

**Answer:** No. The overload was already chosen by the compiler and its descriptor recorded at compile time. Recompiling source may select the new overload.

**Question 4.** Do different checked `throws` clauses change the descriptor?

**Answer:** No. Yet they can break source compatibility and change the exception contract.

**Question 5.** Can default methods emulate every new capability?

**Answer:** No. A default must have valid semantics and avoid conflicts; when a capability is mandatory and old plugins lack it, use an extension/new-version interface or upgrade plugins.

## 16. Checklist before modifying a public interface

1. Classify the change: adding abstract/default/static/private/overload, or removing/changing descriptors.
2. Compare JVM descriptors with **`javap -s`**, paying attention to return types, erasure, and bridges.
3. Recompile old source to test source compatibility.
4. Run old `caller.class` and old `plugin.class` **without recompiling** against the new runtime API.
5. Check for `AbstractMethodError` when new callers invoke abstract methods on old plugins.
6. Check for `NoSuchMethodError` when old callers reference removed/changed methods.
7. Check for default conflicts and fallback semantics.
8. Review checked `throws`, generics, and framework reflection even if descriptors are unchanged.
9. Prefer meaningful adapters/defaults, capability interfaces, deprecation, and migration policies.
10. Keep old JARs as test fixtures and publish clear host and plugin version compatibility matrices.

**Conclusion:** Adding an abstract method to an interface does not necessarily break binary linking, yet it can throw **`AbstractMethodError`** when invoked on old implementations. Adding a default method often aids contract evolution, yet carries risks of **`IncompatibleClassChangeError`** and behavioral changes. Removing or altering a method's name, parameters, or return descriptor can lead to **`NoSuchMethodError`** in old `caller.class` files. To ship a stable API, test **source, binary, and behavior** using actual old binaries—not just a successful build of the new version.

### Java 17 standard references

- Java Language Specification, Chapter 13, Binary Compatibility, especially §13.2, §13.5.4, and §13.5.7: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- JVM Specification, Method Descriptors §4.3.3: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3
- JVMS, Interface Method Resolution §5.4.3.4: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.4
- JVMS, invokeinterface §6.5: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokeinterface
- Java SE 17 AbstractMethodError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractMethodError.html
- Java SE 17 NoSuchMethodError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html
