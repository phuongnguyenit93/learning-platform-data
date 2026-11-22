# Binary compatibility testing using a precompiled consumer artifact

A JDK or Java library upgrade can look spotless in CI: source compiles, new unit tests pass, and application startup succeeds. Yet a plugin released months earlier or an un-recompiled downstream application can throw `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, or `IllegalAccessError` as soon as it runs with the new library. The problem is that **testing fresh source code does not automatically verify compatibility with already-released consumer bytecode**.

In **Java Advance Compatibility Migration**, a particularly valuable test is **keeping the consumer artifact compiled against the older provider/library version, swapping only the provider JAR at runtime, and running that exact consumer artifact**. This simulates a common enterprise scenario: the library provider upgrades while clients, plugins, or dependent services have not upgraded and are not rebuilt immediately.

This lesson explains the differences between source and binary compatibility, JVM method/field descriptors, designing *compile once – run against old and new provider* tests, common linkage failure scenarios, artifact freezing mechanisms, Maven/Gradle/CI integration, and strategies for fixing APIs or declaring a breaking migration.

## 1. Why running `mvn test` or `gradlew test` alone is not enough

A common workflow:

```text
Provider v2 source
        +
Current consumer source
        |
        v
   Rebuild all
        |
        v
   Tests pass
```

shows that **consumer source compiles and runs when rebuilt against the new provider**. It does not prove old class files still link against provider v2.

A binary test requires:

```text
Provider v1.jar ----+
                    |
                    v
Consumer source --> javac --> consumer-old.jar
                              (frozen bytes)
                                  |
                +-----------------+------------------+
                |                                    |
                v                                    v
    Run with provider v1.jar            Run with provider v2.jar
       Baseline control                      Candidate test
                |                                    |
                +--------------- compare ------------+
```

Critical rule: **never invoke the compiler on the consumer again between the two runs**. Doing so can generate fresh method references or catch errors prior to runtime, altering what binary testing is meant to prove.

### 1.1. When is this test especially critical?

- Upgrading SDK libraries embedded across multiple Java apps.
- Swapping implementations/APIs compiled against by third-party plugins.
- Upgrading application servers, framework extensions, or container-supplied providers.
- Upgrading the JDK while continuing to support older JARs.
- Migrating a core library in a multi-module system not deployed atomically.
- Verifying drop-in JAR replacement at runtime without rebuilding consumers.
- Validating compatibility guarantees of a public Java library.
- Testing batch jobs, desktop clients, agents, or hard-to-recompile vendor integrations.

### 1.2. The experiment must include a control run

If `consumer-old.jar` fails against provider v2, first verify it succeeds against provider v1 in the identical environment. If the baseline already fails due to a missing dependency, wrong JVM, or broken fixture, the failure cannot be blamed on v2.

## 2. Four commonly confused layers of compatibility

| Layer | Question | Test method |
|---|---|---|
| **Source compatibility** | Does old consumer source still compile against the new library? | Recompile source with the new library |
| **Binary compatibility** | Do old consumer `.class`/JAR binaries still link against the new library? | Freeze consumer JAR, swap provider |
| **Behavioral compatibility** | Do outputs, exceptions, and side effects still hold? | Assertions, regression, and integration tests |
| **Deployment/runtime compatibility** | Do JDK, provider, classpath, module path, and containers align? | Run final artifact via real launcher/runtime |

A library can preserve source compatibility yet break binary compatibility. Conversely, adding a new overload can make `method(null)` ambiguous when recompiling source even though precompiled calls still target a fixed descriptor and execute fine.

An API keeping every public signature can still alter business logic: for instance, changing from rounding down to rounding to nearest. Therefore, **passing binary linkage tests does not mean behavioral regression tests pass**.

### 2.1. Two questions requiring separate checks

**Question A:** Does already-released consumer version 1.0 run against provider v2 without rebuilding?

**Question B:** Does consumer source version 1.0 still compile against provider v2?

These are distinct goals. Reports must state clearly which one was proven and which tests ran.

## 3. The JVM links calls via symbolic references

In a Java class file, the compiler emits references into the constant pool and bytecode instructions. Example source:

```java
String text = new com.example.api.LabelService().format(10);
```

Bytecode can carry a symbolic method reference:

```text
com/example/api/LabelService.format:(I)Ljava/lang/String;
```

The reference encodes the owner class, method name, and **descriptor**. The descriptor captures parameter types and the return type, not solely the method name.

Common descriptors:

| Java type | JVM descriptor |
|---|---|
| `int` | `I` |
| `long` | `J` |
| `boolean` | `Z` |
| `void` | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Example:

```java
String read(int id, boolean active);
```

maps to descriptor:

```text
(IZ)Ljava/lang/String;
```

If a new provider alters the return type to `Object`, the descriptor changes from `Ljava/lang/String;` to `Ljava/lang/Object;`. A precompiled binary consumer does not regenerate its symbolic reference. Calling the old method can throw `NoSuchMethodError`.

### 3.1. Static vs. instance is also part of the JVM contract

For static methods, the compiler emits `invokestatic`; for instance methods, `invokevirtual` or `invokeinterface` depending on context. Turning a static method into an instance method with the same name can trigger `IncompatibleClassChangeError`.

### 3.2. Field references differ from method references

For fields, the compiler encodes owner, field name, and type descriptor. Deleting a field, changing its type, or narrowing access can break binary consumers. Yet certain compile-time constants are inlined directly into consumer bytecode, causing issues to appear silently as **stale values still used** rather than linkage exceptions.

### 3.3. Linkage errors can surface lazily

The JVM can defer resolution until an execution path runs. Consequently, clean startup does not prove every call inside a consumer remains valid. Tests must exercise every supported code path.

## 4. Complete example: provider renames a method

Consider a simple project:

```text
binary-test-demo/
├── provider-v1/
│   └── com/example/api/GreetingApi.java
├── provider-v2/
│   └── com/example/api/GreetingApi.java
├── consumer/
│   └── com/example/client/LegacyClient.java
├── build/
└── artifacts/
```

### 4.1. Provider version 1

File `provider-v1/com/example/api/GreetingApi.java`:

```java
package com.example.api;

public class GreetingApi {
    public String greeting(String name) {
        return "Hello, " + name;
    }
}
```

### 4.2. Legacy consumer using API v1

File `consumer/com/example/client/LegacyClient.java`:

```java
package com.example.client;

import com.example.api.GreetingApi;

public final class LegacyClient {
    public static void main(String[] args) {
        GreetingApi api = new GreetingApi();
        String message = api.greeting("Java");
        if (!"Hello, Java".equals(message)) {
            throw new AssertionError("Unexpected greeting: " + message);
        }
        System.out.println("PASS: " + message);
    }
}
```

The consumer invokes the API with descriptor:

```text
greeting(Ljava/lang/String;)Ljava/lang/String;
```

### 4.3. Compile provider v1

Using a Linux/macOS shell from the demo root directory:

```bash
mkdir -p build/provider-v1 build/consumer artifacts

javac --release 11 \
  -d build/provider-v1 \
  provider-v1/com/example/api/GreetingApi.java

jar --create \
  --file artifacts/provider-v1.jar \
  -C build/provider-v1 .
```

Use a JDK supporting `javac --release 11` for this sample. Real environments should match their actual target compiler/toolchain.

### 4.4. Compile the consumer **exactly once**

```bash
javac --release 11 \
  -cp artifacts/provider-v1.jar \
  -d build/consumer \
  consumer/com/example/client/LegacyClient.java

jar --create \
  --file artifacts/consumer-old.jar \
  -C build/consumer .
```

**After this step, never delete, edit, or recompile `consumer-old.jar`** during candidate checks. Store the artifact in an immutable repository with a recorded hash.

### 4.5. Run baseline against provider v1

```bash
java \
  -cp "artifacts/consumer-old.jar:artifacts/provider-v1.jar" \
  com.example.client.LegacyClient
```

Expected output:

```text
PASS: Hello, Java
```

On Windows PowerShell, separate classpath entries with `;`:

```powershell
java -cp "artifacts/consumer-old.jar;artifacts/provider-v1.jar" com.example.client.LegacyClient
```

### 4.6. Provider v2 breaks the binary contract

File `provider-v2/com/example/api/GreetingApi.java`:

```java
package com.example.api;

public class GreetingApi {
    public String sayHello(String name) {
        return "Hello, " + name;
    }
}
```

Provider v2 renamed `greeting` to `sayHello`, dropping the prior method signature.

```bash
mkdir -p build/provider-v2

javac --release 11 \
  -d build/provider-v2 \
  provider-v2/com/example/api/GreetingApi.java

jar --create \
  --file artifacts/provider-v2.jar \
  -C build/provider-v2 .
```

### 4.7. Run **the exact same consumer-old.jar** against provider v2

```bash
java \
  -cp "artifacts/consumer-old.jar:artifacts/provider-v2.jar" \
  com.example.client.LegacyClient
```

When the path calling the method executes, expect an error like:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.GreetingApi.greeting(java.lang.String)'
```

Exact message wording varies slightly by JDK. Fundamentally, the compiled consumer's method descriptor no longer exists in provider v2.

Simply running `javac` again on the consumer against provider v2 triggers a **compiler error**, which is no substitute for testing the released consumer artifact.

## 5. Fixing via a compatibility method

If provider v2 should act as a drop-in replacement, **retain the old API and delegate**:

```java
package com.example.api;

public class GreetingApi {
    public String sayHello(String name) {
        return "Hello, " + name;
    }

    @Deprecated
    public String greeting(String name) {
        return sayHello(name);
    }
}
```

After rebuilding only provider v2, re-run the unchanged `consumer-old.jar`. Provided the new API preserves expected outputs, the binary consumer keeps functioning.

This follows the **deprecate → preserve bridge → migrate consumers → remove in planned breaking release** pattern.

### 5.1. When can a simple bridge not work?

- The legacy method depended on a deleted transaction or data model.
- Semantics under the same name/descriptor changed incompatibly.
- Legacy behavior introduces a security vulnerability.
- Interface or class hierarchy changes cannot be masked by a simple overload.
- Public fields/compile-time constants were inlined into consumers.
- The new provider switched namespaces such as `javax.servlet.*` to `jakarta.servlet.*`.

In those cases, announce a **breaking change** and prepare a consumer migration plan; never write a misleading stub just to force green tests.

## 6. Linkage errors to cover in test scenarios

| Provider change | Likely consumer symptom | Explanation |
|---|---|---|
| Remove or alter method descriptor | `NoSuchMethodError` | Consumer invokes obsolete symbolic reference |
| Remove field or change descriptor | `NoSuchFieldError` | Field reference fails resolution |
| Narrow member visibility | `IllegalAccessError` | Existing bytecode accesses now-inaccessible member |
| Switch static ↔ instance | `IncompatibleClassChangeError` | Invocation opcode/contract changed |
| Change class ↔ interface | `IncompatibleClassChangeError` | Binary type kind mismatch |
| Alter hierarchy or interface implementation | `AbstractMethodError`, `ClassCastException`, linkage errors | Dynamic dispatch or casts violate contract |
| Remove/rename binary class name | `NoClassDefFoundError` or `ClassNotFoundException` | Classpath, loader, or reflective lookup misses class |
| Change constructor parameters | `NoSuchMethodError` for `<init>` | Consumer references old constructor descriptor |
| API exists yet throws different exception | Behavioral regression | Linkage passes while semantics differ |
| Change constant inlined by javac | Stale value used | No linkage exception necessarily thrown |

Exact exceptions depend on call sites and JVM resolution; the table is not a strict one-to-one mapping.

### 6.1. Load-time exceptions differ from call-time exceptions

`ClassNotFoundException` usually arises when code explicitly loads a class by name, e.g., `Class.forName`. `NoClassDefFoundError` can arise when the JVM fails to locate a class during linkage or when static initialization failed previously. Inspect `Caused by` and class-loading logs rather than assuming every case means "missing JAR".

### 6.2. Do not apply `--add-opens` for a removed method

`--add-opens` controls deep reflection in JPMS. It neither restores removed methods nor rewrites descriptors. For a genuine `NoSuchMethodError`, verify which provider version is actually loaded first.

## 7. Return types, parameter types, and constructors

### 7.1. Return types belong to descriptors

Old version:

```java
public String status();
```

New version:

```java
public Object status();
```

Descriptors:

```text
v1: ()Ljava/lang/String;
v2: ()Ljava/lang/Object;
```

Precompiled consumers expect the v1 descriptor, which v2 lacks. Making the new return type a supertype does not make the method binary-compatible.

### 7.2. Replacing parameter overloads

Provider v1:

```java
public void send(String endpoint);
```

Provider v2:

```java
public void send(URI endpoint);
```

A precompiled consumer still calls `send(Ljava/lang/String;)V` compiled under v1. If v2 leaves only the `URI` overload, older calls fail resolution.

Keeping the overload works:

```java
public void send(String endpoint) {
    send(URI.create(endpoint));
}
```

provided differences in validation and error handling are carefully tested.

### 7.3. Constructors are compatibility-critical members

Old provider:

```java
public Client(String host, int port);
```

New provider keeps only:

```java
public Client(URI endpoint);
```

Older consumers emit `<init>(Ljava/lang/String;I)V`. Once gone, runtime throws `NoSuchMethodError` even though `Client` still exists.

## 8. Inheritance, interfaces, and bridge methods

Hierarchy changes are easy to miss when scanning only public methods.

### 8.1. Consumer-implemented API interfaces

Provider v1:

```java
public interface PaymentPlugin {
    void charge(int amount);
}
```

External plugins compiled implementations of this interface. Provider v2 adds an abstract method:

```java
public interface PaymentPlugin {
    void charge(int amount);
    void refund(int amount);
}
```

Precompiled plugins lack a `refund` implementation. Depending on how new code invokes the method and the class hierarchy, `AbstractMethodError` can occur.

Where semantics allow, a default method preserves compatibility:

```java
public interface PaymentPlugin {
    void charge(int amount);

    default void refund(int amount) {
        throw new UnsupportedOperationException(
                "Refund is not supported by this plugin");
    }
}
```

Still, adding default methods can introduce multiple-inheritance or behavioral quirks. Test precompiled plugin implementations directly rather than merely compiling the updated interface.

### 8.2. Changing superclasses or dropping interfaces

An older consumer may cast an object to an interface the provider class previously implemented. Dropping that interface breaks casts or interface invocations.

In plugin systems, binary APIs include the full **supertype graph**, not only a class's declared method list.

### 8.3. Generics, erasure, and bridge methods

Generics use type erasure; the compiler generates synthetic **bridge methods** to preserve overriding semantics.

Example:

```java
public interface Repository<T> {
    T find(String id);
}
```

An implementation `Repository<Customer>` may contain a bridge method matching the erased signature. Refactoring generic inheritance, covariant return types, or visibility can alter bridge methods while older binary consumers still invoke the previously compiled descriptor.

Run `javap -s` and `javap -v` to inspect method descriptors and flags, including bridge/synthetic markers.

## 9. Public constants and compile-time inlining

Provider v1:

```java
public final class Settings {
    public static final int RETRY_LIMIT = 3;
}
```

Legacy consumer:

```java
int retries = Settings.RETRY_LIMIT;
```

When a field qualifies as a compile-time constant, `javac` embeds `3` straight into the consumer's class file. Updating provider v2 to:

```java
public static final int RETRY_LIMIT = 5;
```

leaves the precompiled consumer using `3`, even when both JARs load cleanly with zero linkage errors.

Therefore, tests must assert **business behavior**, not merely exit codes.

### 9.1. Binary-compatible yet behaviorally incompatible APIs

If a new constant value must apply across existing consumers, swapping the provider JAR alone fails. Expose a runtime accessor like `retryLimit()` alongside a migration plan, or keep legacy semantics until the compatibility window closes.

## 10. Why artifacts must remain immutable

To prove binary compatibility, the candidate run must use the **exact consumer bytes** used in baseline. If Gradle or Maven silently recompiles the consumer against the new dependency, the test loses validity.

### 10.1. Record SHA-256 checksums

On Linux/macOS:

```bash
sha256sum artifacts/consumer-old.jar
```

On Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 artifacts/consumer-old.jar
```

Record the checksum alongside the provider version used during compilation. Verify after the candidate run that the artifact stayed untouched.

### 10.2. Illustrative artifact manifest

```yaml
consumer:
  name: legacy-checkout-client
  version: 2.3.1
  path: fixtures/consumer-old.jar
  builtAgainst: provider-1.4.0.jar
  compiledWithJdk: "17.0.x"
  releaseTarget: 11
  sha256: "<calculated-hash>"
candidate:
  artifact: provider-2.0.0-rc1.jar
  sha256: "<calculated-hash>"
runtime:
  jdk: "17.0.x"
  mode: classpath
```

These values are placeholders. Real reports must log actual checksums, compilers, runtimes, and artifacts from your pipeline.

### 10.3. Avoid mutable artifact tags

Container `latest` tags, overwritten snapshot JARs, or an unversioned `provider.jar` whose bytes change are unstable identities. Prefer immutable versions and SHA-256 digests.

### 10.4. Use genuine released artifacts

Ideal consumer fixtures are actual JARs/WARs/plugins pulled from your artifact repository representing the **installed base**. Self-written provider demo consumers help yet often miss how real clients use reflection, subclassing, or service providers.

## 11. Classpath: prevent accidentally loading provider v1

A frequent testing mistake:

```text
consumer-old.jar
provider-v1.jar
provider-v2.jar
```

The JVM may load `com.example.api.GreetingApi` from v1, turning the candidate test green without ever testing v2.

Put **only one provider version** on the classpath, or design explicit classloader isolation.

### 11.1. Verify class origin

Inside a diagnostic test:

```java
Class<?> type = com.example.api.GreetingApi.class;
System.out.println("Loader: " + type.getClassLoader());

var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "<unknown code source>"
        : source.getLocation());
```

`CodeSource` may be null with custom classloaders, nested JARs, or bytecode instrumentation, so pair it with artifact inspection and class-loading logs.

### 11.2. JDK 9+ class loading logs

```bash
java -Xlog:class+load=info \
  -cp "artifacts/consumer-old.jar:artifacts/provider-v2.jar" \
  com.example.client.LegacyClient
```

This reveals which archive supplied each loaded class. For Spring Boot executable JARs, servlet containers, or plugin frameworks, launch via **the real runtime launcher**, since their classloader hierarchy differs from a flat classpath command.

### 11.3. Never rely on wildcard ordering

```bash
java -cp "consumer-old.jar:lib/*" com.example.client.LegacyClient
```

Do not leave both old and new providers inside `lib` and depend on wildcard or filesystem ordering. Construct a clean directory holding pinned dependencies.

## 12. Testing across multiple classloaders

Class identity in the JVM depends on both binary name and defining classloader. Two classes with identical FQCNs defined by distinct loaders are distinct types.

Plugin system example:

```text
Application Loader
  |
  +-- Plugin Loader A
  |      +-- api-legacy.jar
  |
  +-- Plugin Loader B
         +-- api-new.jar
```

If both plugins bundle their own copy of `com.example.api.Event`, passing instances across loader boundaries throws `ClassCastException` even when definitions look identical.

A realistic binary compatibility test simulates:

- Shared API classes in the parent loader if required by the framework.
- Plugin implementations in child loaders per isolation contract.
- Runtime delegation policy (parent-first vs. child-first).
- The API version exposed by the host container.
- Cross-boundary object passing.

Running all JARs on one flat application classpath can miss classloader bugs that appear under plugin classloaders in production.

## 13. JPMS/module path and the public API contract

From Java 9 onward, module descriptors are part of deployment compatibility.

Provider:

```java
module com.example.api {
    exports com.example.api;
}
```

If provider v2 removes an `exports` directive for a public package, named-module consumers lose access even if the classes and methods remain in bytecode.

Check:

- `requires` and module readability.
- `exports` for compile-time/runtime access.
- `opens` for deep reflection.
- `uses`/`provides` for `ServiceLoader`.
- Module names and split/duplicate packages.
- Automatic modules and classpath/unnamed module interaction.

**Test in production's launch mode.** If production runs `--module-path`, testing solely with `-cp` skips module resolution completely.

Flags like `--add-exports`/`--add-opens` can serve as temporary bridges for encapsulation shifts, yet **never restore removed method descriptors**.

## 14. Reflection, SPI, and runtime metadata

Not every binary contract is a static Java call.

### 14.1. Reflection

An older consumer might run:

```java
Class<?> type =
        Class.forName("com.example.api.MessagePlugin");

var method = type.getMethod("create", String.class);
```

If provider v2 renames the class or method, runtime throws `ClassNotFoundException` or `NoSuchMethodException` even when an API diff tool scans only a subset of public APIs.

### 14.2. ServiceLoader

A provider may register metadata:

```text
META-INF/services/com.example.spi.Parser
```

If the SPI interface name, provider class, no-arg constructor, or descriptor changes, runtime service discovery breaks or omits the provider.

Tests must invoke `ServiceLoader.load(...)` inside real consumer fixtures rather than just verifying the class file sits in the JAR.

### 14.3. Annotations and framework integration

Frameworks inspect annotations, generic signatures, persistence mappings, validation constraints, and component metadata. Changing annotation retention, package names, or provider lookup rules causes regressions even when method signatures survive.

### 14.4. Java serialization

An older consumer artifact might deserialize Java objects written under library v1. Changing class fields or `serialVersionUID` can break reading legacy payloads (`InvalidClassException`) or change decoded semantics.

Verify using **frozen serialized byte fixtures generated by the prior version**, never freshly serialized outputs from the new provider.

## 15. Class file version vs. binary API compatibility

Suppose:

```text
Consumer old.jar:  major 55  (Java 11)
Provider new.jar:  major 65  (Java 21)
Runtime JVM:       Java 17
```

JVM 17 cannot load major-65 provider class files. This fails at the **runtime class-file level** regardless of whether public APIs changed.

### 15.1. Check major versions

```bash
javap -verbose \
  -classpath artifacts/provider-v2.jar \
  com.example.api.GreetingApi
```

Look for:

```text
major version: 65
```

Common milestones:

| Release | Major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

### 15.2. Verify dependencies were not built for newer JDKs

`javac --release 11` constrains bytecode and Java SE APIs of currently compiled source; it does not downgrade preexisting dependency JARs. A major-55 JAR can still pull in a major-65 transitive library at runtime.

Test on the lowest JDK version the provider claims to support and inspect the full runtime artifact graph.

## 16. Using `javap` to diagnose binary breaks

Run:

```bash
javap -classpath artifacts/provider-v1.jar \
  -s com.example.api.GreetingApi

javap -classpath artifacts/provider-v2.jar \
  -s com.example.api.GreetingApi
```

Inspecting the method:

```text
greeting(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
```

If v2 no longer defines this descriptor, binary consumers fail to resolve calls against it.

Use `javap -v` to inspect:

- Constant pool references.
- `ACC_PUBLIC`, `ACC_STATIC`, synthetic/bridge flags.
- Superclass/interfaces.
- Method handles, `invokedynamic`, and bootstrap metadata.
- Class file major version.

### 16.1. Inspecting consumer bytecode helps too

```bash
javap -c -v \
  -classpath artifacts/consumer-old.jar \
  com.example.client.LegacyClient
```

This confirms the exact descriptor the consumer calls. When v2 keeps the method name with an altered return type, comparing descriptors on both sides pinpoints the mismatch.

### 16.2. Distinguish a binary break from loading the wrong provider JAR

If v2 preserves the method yet `NoSuchMethodError` still fires, inspect the loaded artifact source and classloader. The runtime may still be pulling provider v1 or v3 from a shared directory.

## 17. Maven workflow: build the fixture once, run candidates separately

Example legacy consumer `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>greeting-api</artifactId>
        <version>1.4.0</version>
    </dependency>
</dependencies>
```

At the **fixture creation stage**:

```bash
mvn -B clean package
```

Store the resulting consumer JAR in an artifact repository or immutable fixtures directory.

At the **provider v2 test stage**:

1. Fetch `consumer-old.jar` from the artifact repository.
2. Fetch `provider-v1.jar` for the baseline control run.
3. Fetch `provider-v2.jar` for the candidate run.
4. Assemble a clean classpath with no duplicate providers.
5. Run the unchanged consumer against each provider separately and compare results.

Never run `mvn package` on consumer sources during the candidate stage. Rebuilding turns it into a different test.

### 17.1. Maven dependency trees do not prove production classpaths

Running:

```bash
mvn dependency:tree
```

shows build resolution, yet containers or custom packaging tasks can inject external JARs. Inspect the final WAR/JAR contents and class-loading sources directly.

### 17.2. Plugin classpaths differ from application classpaths

When a Maven plugin fails, its dependencies reside in an isolated class realm. Bumping a library inside application `<dependencies>` may leave the plugin's binary components untouched.

## 18. Gradle workflow: avoid auto-recompiling the consumer

If `:consumer` is a Gradle subproject depending on `:provider`, invoking `build` recompiles `:consumer` against the new provider. Use a **frozen JAR** instead.

Groovy DSL example:

```groovy
tasks.register('binaryCompatibilityRun', JavaExec) {
    group = 'verification'

    classpath = files(
        'fixtures/consumer-old.jar',
        'candidate/provider-v2.jar'
    )

    mainClass = 'com.example.client.LegacyClient'
}
```

This snippet suits consumers with no extra runtime dependencies. Real apps must declare pinned runtime dependencies while excluding `provider-v1.jar` from the candidate classpath.

### 18.1. Select the test execution JVM

```groovy
tasks.named('binaryCompatibilityRun', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This configures `JavaExec`'s runtime JVM **without recompiling the consumer**. The Gradle daemon JVM and `JavaCompile` toolchain can be separate.

### 18.2. Do not pull test fixtures from freshly built classes

Avoid:

```groovy
classpath = sourceSets.main.runtimeClasspath
```

when that source set holds mutable consumer code and gets rebuilt. Candidate test classpaths should combine frozen consumer artifacts with explicitly identified candidate dependencies.

### 18.3. Gradle dependency graphs aid investigation

Commands:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency greeting-api \
  --configuration runtimeClasspath
```

clarify dependency resolution. Still, explicit `files(...)` paths in `JavaExec.classpath` differ from resolved configurations; inspect the executed classpath directly.

## 19. Split CI/CD into two distinct stages

Recommended pipeline structure:

```text
Stage A — Fixture preparation (run on consumer release)
  Read released consumer source/tag
  Compile against released provider v1
  Package consumer-old.jar
  Record JDK, --release, dependency versions
  Store immutable artifact and SHA-256

Stage B — Provider candidate validation (run on every provider PR)
  Download consumer-old.jar
  Verify checksum
  Download provider v1 and provider candidate
  Run baseline
  Run candidate
  Collect exit codes, logs, class origins
  Publish compatibility report
```

Stage B must **contain zero `javac` invocations, Maven/Gradle consumer builds**, or any step mutating fixture bytes.

### 19.1. Ensure test jobs fail accurately

- Assertions and uncaught exceptions must exit non-zero.
- CI must inspect exit codes rather than merely grepping logs for "PASS".
- Capture full stack traces and class-loading sources.
- Distinguish baseline failures from candidate failures clearly.
- Never mask failures with `|| true` or equivalent settings.
- Match test environment JDK and OS to target specs.
- Where consumers require databases/services, use production-contract test environments.

### 19.2. Manage artifact provenance and release metadata

Record artifact filenames, versions, checksums, and repository sources. Check JAR signatures where applicable. Never treat unverified external downloads as official fixtures.

## 20. API diff tools supplement, never replace, real consumer tests

Helpful static tools:

- **japicmp:** compares JAR API changes across binary and source rules.
- **Revapi:** evaluates API diffs with extensible compatibility policies.
- **`javap`:** inspects public members, descriptors, and bytecode.
- **`jdeps`:** analyzes static package/module dependencies.

Effective combined workflow:

```text
Provider v1.jar ----> Static API diff <---- Provider v2.jar
                                                  |
                                                  v
                                     Potential binary break report
                                                  |
                                                  v
Consumer-old.jar + Provider v2.jar ----> Runtime compatibility test
                                                  |
                                                  v
                                         Behavioral assertions
```

### 20.1. Why static API diffs alone fall short

- Runtime classpaths may load unintended artifacts.
- Consumers use reflection or string-based class lookups.
- `ServiceLoader` descriptors may change.
- Runtime behavior shifts despite unchanged signatures.
- External schemas or serialization formats change.
- Providers carry native dependencies or agents.
- Classloader or module setups differ.
- Failures happen only along specific consumer business flows.

### 20.2. Why runtime consumer tests alone fall short

They exercise only APIs called by selected fixtures. Deleting a public method unused by fixtures still breaks unknown external callers. Pair runtime tests with static API checks whenever promising broad public binary compatibility.

## 21. Multiple consumer artifacts: compatibility matrix

When a provider serves multiple products, run a test matrix.

| Compiled consumer | Provider baseline | Provider candidate | Runtime | Hypothetical result |
|---|---|---|---|---|
| Desktop 1.9 | 1.2 | 2.0 | JDK 17 | Pass |
| Batch 2.1 | 1.4 | 2.0 | JDK 17 | `NoSuchMethodError` |
| Plugin 3.0 | 1.5 | 2.0 | JDK 21 | Pass |
| Web app 4.2 | 1.5 | 2.0 | JDK 17 | Semantic regression |

These rows are illustrative. Actual reports must cite verified artifacts and observed evidence.

### 21.1. Which consumers belong in fixtures?

- Oldest still-supported release.
- Most widely deployed version in production.
- Latest release.
- Consumers relying on deprecated APIs.
- Plugins isolated behind custom classloaders.
- Consumers utilizing reflection, SPI, or Java serialization.
- Deployments running across contracted JDK/OS/container matrices.

You need not test every historical commit, yet you must keep an approved, periodically refreshed compatibility matrix.

### 21.2. Retiring support for a consumer

Never overwrite or delete a fixture merely because it started failing. If the business decides to drop support, document the sunset date, replacement version, migration notice, and explicit compatibility gate change. Dropping fixtures is a versioning policy decision, never a CI shortcut.

## 22. Javax → Jakarta is an example of a major contract break

When Java EE APIs moved from `javax.servlet.Filter` to `jakarta.servlet.Filter`, the JVM treats them as **completely distinct types**. A precompiled filter implementing the Javax interface does not implement the Jakarta interface even when method names align.

When new containers/providers require Jakarta types, legacy Javax artifacts cannot link or integrate directly.

A binary test can compare:

1. Old plugin/filter JAR compiled against Javax.
2. Javax container/framework baseline.
3. Jakarta container/framework candidate.
4. Classloading, registration, lifecycle, and runtime behavior.

Without an officially supported bridge or bytecode transformer, a breaking migration is required; never promise drop-in binary compatibility.

### 22.1. Do not confuse JDK upgrades with the Jakarta namespace transition

A Javax app can often run on a newer JDK inside a supported Javax container. Conversely, a Jakarta app can require newer containers/frameworks even when the JDK version already meets requirements. Test these two dimensions independently.

## 23. Agents, JNI, and serialized data: boundaries beyond pure Java ABI

### 23.1. Java agents

Previously compiled agents may embed outdated ASM/Byte Buddy unable to parse newer bytecode. `Unsupported class file major version` failures commonly come from instrumentation parsers rather than missing public APIs.

Test agent startup, class transformation, class loading, and monitoring/security telemetry on the target JDK.

### 23.2. JNI/native libraries

A Java library keeping unchanged method signatures can still fail against updated `.dll`, `.so`, or `.dylib` binaries due to CPU architecture, native ABI, symbol mismatches, or driver updates. Execute binary tests on real target OS/hardware whenever JNI is involved.

### 23.3. Persisted Java data

When apps write serialized objects or cache entries under old class layouts, binary linkage of the new provider does not prove legacy data still deserializes cleanly. Keep frozen serialized byte fixtures written by older releases and test reading them under the new provider.

## 24. Common misconceptions

### "Recompiling the consumer cleanly proves binary compatibility"

False. Recompiling regenerates symbolic references. Binary compatibility requires testing unchanged consumer bytecode.

### "Identical method names mean an unchanged contract"

Insufficient. Descriptors encode parameter and return types; visibility, staticness, and declaring types matter too.

### "Clean startup without linkage errors means everything passes"

Insufficient. JVM class/method resolution often runs lazily when paths execute.

### "Put both v1 and v2 on the classpath to stay safe"

The opposite: loading order masks regressions by resolving classes from the wrong version. Isolate one provider per test run.

### "A clean static API diff guarantees identical behavior"

False. Constant inlining, exception semantics, serialization, and external state can still diverge.

### "Just adjust `--release`"

False. `--release` neither restores deleted APIs nor updates binary references inside precompiled consumers.

### "`UnsupportedClassVersionError` is always an API breaking change"

Not necessarily. The provider may simply have been compiled for a newer Java release than the runtime JVM; inspect class majors and runtime targets.

### "One minimal dummy consumer is enough"

A dummy exercises minimal surface area. Widely consumed libraries need real-world consumer fixtures paired with static API diffs.

### "On red CI, just rebuild the fixture against the new release"

When binary compatibility is promised, updating the fixture erases regression evidence. Fix the provider or deliberately announce a policy/major-version break.

## 25. Handling binary test failures

First classify the failure:

**Group A — Unintended API break with backward-compatible fix.** Restore the legacy method/constructor, add a delegating bridge, annotate `@Deprecated`, and re-run against the unchanged consumer binary.

**Group B — Intentional breaking change.** Publish minimum consumer versions, compatibility matrices, migration guides, and rollback paths; never market the new provider as drop-in.

**Group C — Runtime/classpath mismatch.** Fix classpaths, module paths, JDK versions, or classloaders so the intended artifacts run. Never warp APIs to paper over loading the wrong JAR.

**Group D — Behavioral regression.** Identify altered semantics, fix logic or version/flag behavior intentionally, and expand regression suites.

**Group E — Security-driven removal.** If retaining an old API introduces security risk, design a controlled migration rather than re-enabling unsafe behavior merely for compatibility.

### 25.1. Failure diagnosis workflow

1. Identify the class, method, or field named in the exception.
2. Inspect the full stack trace and nested `Caused by` chains.
3. Verify exact JVM version, launch command, and classpath/module path.
4. Confirm which JAR supplied the loaded provider class.
5. Diff `javap -s` output between provider v1 and provider v2.
6. Inspect consumer bytecode to see the exact referenced descriptor.
7. Cross-check API diffs alongside behavioral assertions.
8. Decide between maintaining compatibility bridges or declaring a breaking release.
9. Re-test against the same immutable consumer fixture.
10. Archive artifact hashes and full reports for reproducibility.

## 26. Rollout and rollback for a new provider

Binary compatibility tests belong in **pre-release gates**, yet production can still surface unknown callers or rare code paths.

When the provider acts as a shared library inside application servers or plugin platforms:

- Keep provider v1 artifacts ready for rollback.
- Pin runtime image/container versions.
- Verify which classloader supplies the shared API.
- Account for in-flight tasks and persisted state.
- Avoid bundling database/event schema breaks into the same step whenever possible.
- Track linkage errors segmented by release and consumer version.
- Prepare automated rollback if error rates breach thresholds.

If provider v2 persisted data unreadable by v1, reverting JARs alone cannot guarantee clean rollback. Account for data versioning and compatibility windows.

### 26.1. Rollback vs. recompiling consumers

When consumers are deployed across many sites, rolling back a provider is often far faster than forcing every consumer to rebuild. That speed is a major reason to preserve binary compatibility whenever practical.

Even so, never maintain dangerous or unsupported APIs forever just to avoid breaking releases; publish clear deprecation timelines and consumer upgrade roadmaps.

## 27. Binary compatibility test report template

```text
TEST:
  provider-binary-regression-2026-11

CONSUMER:
  name: checkout-client
  version: 2.3.1
  compiled-against: greeting-api-1.4.0.jar
  binary: consumer-old.jar
  sha256: <recorded-hash>
  recompiled-in-candidate-stage: NO

BASELINE:
  provider: greeting-api-1.4.0.jar
  runtime: JDK 17
  outcome: PASS

CANDIDATE:
  provider: greeting-api-2.0.0-rc1.jar
  runtime: JDK 17
  outcome: FAIL
  error: NoSuchMethodError
  reference: GreetingApi.greeting(String):String

EVIDENCE:
  provider-class-origin: provider-v2.jar
  consumer-checksum-unchanged: YES
  descriptor-diff: captured

DECISION:
  Restore compatibility method, or declare breaking release.
```

This report is illustrative, not telemetry from a live system.

## 28. Checklist before certifying binary compatibility

- [ ] Distinguished source, binary, behavioral, and runtime compatibility.
- [ ] Identified every supported consumer version still in service.
- [ ] Preserved consumer artifacts **compiled against the older provider**.
- [ ] Verified consumer checksums stayed unchanged across baseline and candidate runs.
- [ ] Recorded consumer compiler JDK, `--release`, and dependency versions.
- [ ] Pinned provider v1 baseline and v2 candidate versions and hashes.
- [ ] Ran baseline control using old consumer + provider v1.
- [ ] Ran the unchanged old consumer + provider v2 without recompiling.
- [ ] Used clean classpaths/module paths matching production launch mode.
- [ ] Verified active classloaders and loaded code sources.
- [ ] Exercised critical public methods, constructors, fields, and type hierarchies.
- [ ] Tested reflection, SPI, annotations, and serialization where relevant.
- [ ] Inspected return/parameter descriptors and bridge methods on failures.
- [ ] Checked for constant inlining and behavioral semantics regressions.
- [ ] Confirmed class-file major versions match target JVMs.
- [ ] Added static API diff checks as complementary verification.
- [ ] Built a compatibility matrix covering relevant consumer versions and runtimes.
- [ ] Classified failures accurately into ABI breaks, runtime mismatches, or semantic shifts.
- [ ] Documented clear decisions for compatibility bridges vs. breaking migrations.
- [ ] Archived stack traces, logs, checksums, build metadata, and CI reports.
- [ ] Established rollout and rollback procedures before updating production providers.

## 29. Conclusion

**Binary compatibility testing using a precompiled consumer artifact** validates a concrete guarantee: released consumers continue linking and running cleanly when underlying providers/libraries upgrade without consumer rebuilds. JVM linkage depends on binary names, method/field descriptors, visibility, staticness, and classloaders — details that can break even when source code appears compatible.

In Java Advance Compatibility Migration, **freeze consumer JARs and checksums, run baselines against old providers, swap only candidate providers, isolate classpaths, and execute realistic business flows**. Combine static API diffs with runtime contract tests and behavioral assertions. When breaks emerge, either maintain controlled compatibility bridges or declare breaking releases backed by consumer upgrade, rollout, and rollback plans. Never resolve failures by silently recompiling released artifacts: doing so hides the exact risk binary testing exists to catch.
