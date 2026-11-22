# Why Binary Compatibility Does Not Guarantee Source or Behavioral Compatibility

When upgrading Java or changing a library version, an application may continue running using pre-compiled `.class` files yet fail to compile when rebuilt from source. There are also cases where an application compiles and links successfully, yet business results change at runtime. These situations arise because **source compatibility, binary compatibility, and behavioral compatibility are three distinct dimensions**.

Binary compatibility focuses on the ability of existing bytecode to keep referencing and linking to the classes, fields, and methods it needs. It does not prove that a new compiler still accepts all old source code, nor does it prove that invoked methods still produce the same results as before. When evaluating a JDK or dependency upgrade, all three dimensions must be verified separately.

## 1. Three Compatibility Concepts to Distinguish

### 1.1. Source compatibility

Source compatibility answers the question: **can the program's source code be recompiled successfully with the new library, JDK, or compiler version?**

The compiler re-analyzes all expressions and types in the source code. It checks access modifiers, parameter types, return types, generics, overloads, type conversions, type inference, and many Java language rules. Therefore, an API change can make a previously valid call ambiguous or no longer type-correct, even when the method descriptors used by old bytecode still exist.

For example, a library adding a new overload can make a `send(null)` call ambiguous upon recompilation. The old source code did not change, yet the new compiler cannot select a unique matching method.

### 1.2. Binary compatibility

Binary compatibility focuses on the ability of already-compiled `.class` files to continue being loaded by the JVM, have their references resolved, and link with the new library version. Bytecode contains symbolic references to classes, fields, and methods; at runtime, the JVM must find the corresponding element matching the name and descriptor requested by bytecode.

For example, an already-compiled application's bytecode may call `send(Object)`. If the new library version keeps that method with the matching descriptor, the old call can continue linking successfully, even if the library added overloads that cause source calling `send(null)` to fail recompilation.

Binary compatibility therefore concerns contracts at the class-file and linkage level. It does not re-run source-level type checking, nor does it verify the business semantics of methods.

### 1.3. Behavioral compatibility

Behavioral compatibility answers the question: **when running under the same conditions and with the same inputs, does the program continue producing the results and side effects expected by callers?**

Behavior can include:

- Return values and how those values are interpreted.
- Data read, written, converted, or ordered.
- Exceptions thrown, when they are thrown, and how errors are handled.
- Side effects such as writing to a database, sending messages, or calling external services.
- Processing order, concurrency, and thread-safety guarantees.
- Response latency, memory consumption, and operational characteristics depended on by the system.

A method can keep the same name, parameter types, and return type so old bytecode still calls it. However, if internal calculation changes, the application can still produce different results. That is a behavioral change even without any binary linkage error.

| Dimension | Subject Verified | Core Question |
|---|---|---|
| Source compatibility | Source code and compilation rules | Can old source code be recompiled? |
| Binary compatibility | Bytecode and class-file references | Can existing bytecode still link with the new library? |
| Behavioral compatibility | Execution results and side effects | Does the program still do what users and the system expect? |

## 2. Why Does Binary Compatibility Not Guarantee Source Compatibility?

The main reason lies in when and what kind of information the JVM and compiler use. Old bytecode already recorded the method call and the descriptor selected at compile time. The JVM does not need to re-perform overload resolution on the original source expression. Conversely, when recompiling, the compiler must inspect the entire new API and apply Java's type rules.

### 2.1. Adding overloads can make old source code ambiguous

Suppose the first version of a library has the following class:

```java
public class MessageSender {
    public void send(Object value) {
        System.out.println("Send object: " + value);
    }
}
```

An application uses the library:

```java
MessageSender sender = new MessageSender();
sender.send(null);
```

In the first version, only `send(Object)` exists, so the compiler picks this method. The application's bytecode records a call to the method with an `Object` parameter.

Later, the library vendor adds two overloads while keeping the old method:

```java
public class MessageSender {
    public void send(Object value) {
        System.out.println("Send object: " + value);
    }

    public void send(String value) {
        System.out.println("Send text: " + value);
    }

    public void send(Integer value) {
        System.out.println("Send number: " + value);
    }
}
```

When recompiling the line:

```java
sender.send(null);
```

the compiler sees that both `send(String)` and `send(Integer)` can accept `null`. Neither `String` nor `Integer` is a subtype of the other, so no single most specific overload is selected. The compiler reports an ambiguous call error, typically with the message `reference to send is ambiguous`.

However, the application compiled against the first version can still run with the new library: its bytecode still references `send(Object)`, and that method remains intact. Adding overloads did not remove the old descriptor.

```text
Old source code: sender.send(null)
          |
          v
Compile with API version 1
          |
          v
Bytecode calls send(Object)
          |
          v
Run with API version 2: still finds send(Object)

Recompile old source code with API version 2
          |
          v
send(String) and send(Integer) both match
          |
          v
Compile error: ambiguous call
```

This is a classic example where binary compatibility is preserved while source compatibility is broken. If recompilation is needed, the application can update the call to specify the desired type or overload explicitly, such as `sender.send((Object) null)`. Such a fix should be based on the business intent of the call, not merely to stop the compiler from complaining.

### 2.2. Generic changes can preserve descriptors while changing type-check outcomes

Java uses type erasure for generics. Much generic information is retained in class-file metadata for the compiler and tools to read, yet the descriptor the JVM uses to link methods is based on erased types.

Suppose the library initially declares:

```java
import java.util.List;

public class Catalog {
    public List<String> names() {
        return List.of("Java", "Spring");
    }
}
```

The application calls:

```java
String firstName = catalog.names().get(0);
```

The new version changes the generic return type:

```java
import java.util.List;

public class Catalog {
    public List<Object> names() {
        return List.of("Java", "Spring");
    }
}
```

At the JVM descriptor level, both versions have the erased return type `java.util.List`. Therefore, if the method name and other descriptor parts remain unchanged, old bytecode can still resolve the `names()` call.

When recompiling source code, the compiler reads the new API's generic metadata and sees `get(0)` returning `Object`. `Object` cannot be directly assigned to a `String` variable, so that source line no longer compiles without an appropriate check/cast.

This example shows that type metadata used by the compiler can change while the JVM linkage descriptor stays unchanged. It also shows that old bytecode linking successfully does not guarantee actual runtime data still satisfies the type assumptions old source once made. If the new library actually returns a non-`String` element, old bytecode can encounter `ClassCastException` at compiler-inserted checkcast points.

### 2.3. Overload resolution, type inference, and conversions belong to the compiler

Beyond the two cases above, API changes can affect source code through:

- Adding overloads that alter method selection or create ambiguous calls.
- Changing generic bounds so a previously valid type argument no longer satisfies constraints.
- Changing generic return types so results can no longer be assigned to variables or passed to another method.
- Adding members to interfaces or superclasses that introduce name conflicts, inheritance rules, or method selection changes in source.
- Changing access modifiers or package/module structure causing the compiler to deny access.
- Changing required language versions or standard APIs the compiler is allowed to use.

These rules are enforced at compile time. A JVM executing bytecode does not re-run full source analysis, so an old binary may still run even when its corresponding source code can no longer compile.

## 3. Why Does Binary Compatibility Not Guarantee Behavioral Compatibility?

Successful linkage only proves the JVM found the elements bytecode references by name and descriptor. The JVM does not know the business contract expected by the application, such as whether a unit price includes tax, which encoding decodes a string, or which rule sorts a list.

### 3.1. Same method signature, changed meaning of results

Suppose a fee-calculation library has the API:

```java
public class FeeCalculator {
    public long calculate(long amount) {
        return amount * 2 / 100;
    }
}
```

An application was built on the contract that the method returns a fee equal to 2% of the input amount. The new library version preserves the `calculate(long)` method and `long` return type, yet changes the calculation because product policy shifted to a 3% fee rate:

```java
public class FeeCalculator {
    public long calculate(long amount) {
        return amount * 3 / 100;
    }
}
```

The method name, parameter type, and return type remain the same. Old bytecode continues linking and calling the method. However, the same input produces a different result. If the application is not updated to accept the new policy, invoicing or reconciliation results can deviate from expectations.

The issue here is not in the class file. It is a behavioral contract change that Java signatures do not fully describe.

### 3.2. Default values or environment data change

A method can keep the same signature while depending on JDK or OS defaults. For example, an application uses `new String(bytes)` to decode data without specifying a charset. Since Java 18, UTF-8 became the default charset across standard environments per JEP 400. If the application previously ran in an environment with a non-UTF-8 default charset, the same byte array may be interpreted as a different string after upgrading.

Bytecode still calls the `String(byte[])` constructor; binary compatibility is unaffected. However, the resulting text content can differ, corrupting imported, exported, or compared data.

To avoid relying on defaults, specify the encoding according to the data contract:

```java
import java.nio.charset.StandardCharsets;

String content = new String(bytes, StandardCharsets.UTF_8);
```

Other defaults such as locale, timezone, timezone data, TLS policies, or cryptographic algorithms can also affect behavior while method descriptors stay unchanged.

### 3.3. Exception handling and side effects can change

A library may still provide `load(String)` yet change how it handles invalid input. Previously the method returned an empty value; the new version throws `IllegalArgumentException`. Bytecode invoking the method sees no linkage error, yet application control flow changes because a new exception appears.

Similarly, a method may continue taking the same parameters while altering side effects: writing an extra audit record, sending a message before transaction commit, calling an external service, or changing data update order. These changes can affect consistency and integration across the whole system.

When evaluating behavior, observe return values as well as exceptions, persisted data, outbound requests, and post-execution state. Checking only that the method throws no linkage error is insufficient.

### 3.4. Performance and concurrency can also change real-world experience

Two versions may preserve the API and produce the same outcome in a simple test, yet differ in performance or synchronization. An algorithm change can increase complexity; a change in thread management or caching can expose a previously rare race condition.

In a live system, higher latency, changed message ordering, or greater resource consumption can also break operational assumptions of other components. These differences are not expressed in method descriptors and often appear only under load or high concurrency.

## 4. Compatibility Dimensions Can Be Independent of One Another

Do not treat the three compatibility types as a ladder where passing one automatically passes the next. A change can preserve one dimension while breaking another.

| Scenario | Old Source Recompiles | Old Bytecode Links | Behavior Preserved | Explanation |
|---|---|---|---|---|
| Add `send(String)` and `send(Integer)` overloads, keep `send(Object)` | No, if source calls `send(null)` | Yes | Possibly yes, if the old call still enters `send(Object)` and logic is unchanged | The source call becomes ambiguous, while old bytecode still calls the previously chosen descriptor. |
| Change `process(int)` to `process(long)` | Possibly yes, if source passes `int` and it widens | No for old binaries referencing only `process(int)` | Cannot be concluded yet | The compiler can compile new calls to `process(long)`, yet old bytecode still looks for descriptor `process(int)`. |
| Keep signature unchanged but change fee calculation | Yes | Yes | No | The JVM can link, yet business results change. |
| Keep API, descriptors, and processing contract | Yes | Yes | Yes, within verified scope | All three dimensions are maintained. |

The example of changing `process(int)` to `process(long)` shows the reverse direction also matters: **source compatibility does not automatically guarantee binary compatibility**. Recompiled source can leverage `int`-to-`long` widening conversion, while old bytecode still requires the method descriptor with an `int` parameter. If the old descriptor was removed, the JVM can throw `NoSuchMethodError` when executing the call.

Therefore, when a library is used by multiple applications or plugins compiled at different times, rebuilding a single representative application does not prove every existing binary is compatible.

## 5. Within What Scope Is Binary Compatibility Guaranteed?

Binary compatibility is a concept with a concrete scope. It depends on the class files, APIs, and library versions actually used. A library may be binary-compatible for common calls yet still fail on a rarely executed branch, when classes are loaded dynamically, or when a dependency of another version appears.

Limitations to keep in mind:

1. **Only verifies references actually present in the binary.** A class or method invoked via reflection, configuration, string names, or plugins may not appear as ordinary bytecode calls.
2. **Classpath and transitive dependencies still matter.** A binary may link with library A yet fail if library B that A depends on is changed or loaded at the wrong version.
3. **Class loaders can change which class is found.** Two classes with the same name loaded by different class loaders are not necessarily the same type in the JVM.
4. **Native code and Java agents have separate contracts.** JNI/JNA, bytecode-transforming agents, or OS-coupled libraries can be incompatible even when the surface Java API remains unchanged.
5. **Errors may surface only when executing a specific branch.** A binary that starts up does not prove every method, plugin, reflection path, and processing flow links successfully.

In addition, binary compatibility of one library does not equal compatibility of the entire application. An application is a composition of many components; updating one dependency can pull in changes to other dependencies, runtime configuration, or data exchanged between services.

## 6. How to Test Each Type of Compatibility Separately When Upgrading

A migration plan should clearly state which binaries must keep running, which sources must recompile, and which behaviors must remain preserved. The following steps gather evidence for each question.

### Step 1: Identify API consumers

List applications, modules, plugins, background jobs, and services using the library. Distinguish components that can be rebuilt together from components deployed independently only as binaries.

This is especially important when upgrading a shared library. One module may be recompiled immediately, while a third-party plugin or legacy application still uses a previously released JAR.

### Step 2: Check source compatibility

Recompile consumers against the target JDK, compiler options, and dependency versions. Inspect errors involving overloads, generics, return types, access rights, modules, and removed APIs.

If errors occur, determine which API change made the old call invalid. Fix source code according to intended semantics, while considering whether the API change can be designed in a less disruptive way.

### Step 3: Check binary compatibility

If previously compiled applications must be supported, try running old artifacts with the new dependencies in the matching environment. Check for linkage errors such as:

- `NoSuchMethodError`: bytecode requests a method yet the JVM cannot find the matching descriptor.
- `NoSuchFieldError`: a field referenced by bytecode no longer exists with the required name and descriptor.
- `AbstractMethodError`: a method invocation cannot find an appropriate implementation at runtime.
- `IncompatibleClassChangeError`: class or member structure/usage no longer matches the compiled binary.
- `UnsupportedClassVersionError`: the running JVM does not support the class-file version of a loaded class.

API analysis tools such as Revapi or japicmp can compare two library versions to flag potentially compatibility-breaking changes. Analysis findings should be cross-checked against how the application actually uses the API; tools cannot by themselves prove every execution path is safe.

### Step 4: Check behavioral compatibility

Define which contracts must be preserved before testing: valid inputs, boundary inputs, expected results, exceptions, side effects, processing order, data formats, timeouts, and performance requirements.

Create regression tests or contract tests for those contracts. For a fee-calculation service, for example, check rounding rules, currency units, fee rates, small amounts, and boundary values; checking only that the method returns a `long` is not enough.

When possible, run the same dataset on both the old and new versions and compare results. If differences are intentional, document the contract change and update consumers relying on the new behavior.

### Step 5: Evaluate JDK and dependency impact separately

If an upgrade changes the JDK, framework, and multiple libraries simultaneously, isolating root causes becomes difficult when errors arise. Record each component's version and split verification by change group. For critical applications, keep dependencies unchanged to test the new JDK first, then upgrade dependencies in controlled batches.

Also verify runtime factors such as charsets, timezones, TLS, JVM flags, garbage collectors, and container limits. These changes can alter behavior even when application APIs have not changed.

### Step 6: Canary deploy and monitor

Deploy to staging or a small group of instances with production-like configuration. Monitor compile errors, linkage errors, business exceptions, data discrepancies, request failure rates, latency, and resource usage. Keep old artifacts and configurations ready to roll back if discrepancies exceed acceptable thresholds.

| Question to Confirm | Appropriate Evidence |
|---|---|
| Can old source recompile? | Compilation results of consumers with the target compiler and API. |
| Can old binaries keep running? | Testing compiled artifacts against the new dependencies and runtime; API diff analysis. |
| Is behavior preserved? | Regression tests, contract tests, data comparisons, and load tests. |
| Does the whole system operate stably? | Staging/canary, logs, metrics, tracing, and real error monitoring. |

## 7. Common Confusions

**"No `NoSuchMethodError` means it is compatible."** Absence of linkage errors is only a binary signal along paths that actually executed. Source code might still fail to compile, and behavior might still change.

**"Adding a new method is always safe because the old API wasn't removed."** Keeping the old method may preserve binary linkage, yet new overloads can make source ambiguous or change overload resolution during future compilations.

**"Same Java signature means same behavior."** A signature describes invocation at the type level. It does not fully describe algorithms, business rules, exceptions, side effects, ordering, or performance.

**"A passing build proves all released binaries can run."** A build typically produces new binaries. It does not automatically test every old artifact still deployed, standalone plugins, or consumers outside the current workspace.

**"A passing unit test suite proves full compatibility."** Unit tests cover only the cases written. Combine API analysis, integration tests, contract tests, and observation in production-like environments.

## 8. Conclusion

Binary compatibility, source compatibility, and behavioral compatibility answer three different questions. Binary compatibility tells whether compiled bytecode can continue linking with a new API. Source compatibility tells whether source code can be accepted by the compiler upon rebuilding. Behavioral compatibility tells whether the program still produces results, exceptions, and side effects matching the contract the system expects.

A change can keep method descriptors intact yet make source code ambiguous, alter the generic types seen by the compiler, or change business results. Conversely, source code may recompile via type widening while old binaries cannot find the descriptor they referenced. Therefore, JDK or dependency migrations must verify each layer independently: compile sources, run released binaries, and validate behavior via tests with representative data. Only when all three bodies of evidence meet system requirements is there a solid basis to conclude the upgrade is compatible.
