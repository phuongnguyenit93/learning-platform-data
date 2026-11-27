# Distinguishing Source, Binary, and Behavioral Compatibility in Java 17

**Topic:** Java 17  
**Chapter:** Compilation and Documentation  
**Lesson:** Distinguishing Source, Binary, and Behavioral Compatibility

When releasing a new version of a Java library, asking "is it backward compatible?" is not specific enough. A change can break compilation of old source code, prevent previously compiled `.class` files from running, or still compile and run while producing different results than before.

To evaluate an API change, separate three distinct concepts:

- **Source compatibility:** whether existing client source code can be recompiled against the new library version without modification.
- **Binary compatibility:** whether a client already compiled against the old library version can link and run against the new library version without linkage errors caused by API changes.
- **Behavioral compatibility:** whether a program using the new version continues to exhibit the behavior that clients are entitled to expect under the API contract.

These three criteria are independent. A change can preserve binary compatibility while breaking source compatibility; preserve both while changing behavior; or break all three.

In Java 17, you must understand Java language rules, bytecode structure, and API contracts. This lesson uses examples involving methods, fields, interfaces, exceptions, generics, and compile-time constants to show how to evaluate a change before release.

## 1. Three types of compatibility are three different questions

Suppose a library provides this API:

```java
package com.example;

public class Greeting {
    public String message(String name) {
        return "Hello, " + name;
    }
}
```

A client uses the API:

```java
import com.example.Greeting;

public class App {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        String text = greeting.message("Lan");
        System.out.println(text);
    }
}
```

When the library is upgraded, ask three separate questions.

### 1.1. Source compatibility

Take the old `App.java` source code, place it on the classpath/module path with the new library, and recompile. If the source compiles without edits, the change preserves source compatibility for that client.

This says nothing about a previously compiled `App.class` file. A change might force the client to recompile even though its source remains valid.

### 1.2. Binary compatibility

Keep the `App.class` file compiled against the old library version, swap the old JAR for the new JAR, and run it. If the JVM can still resolve and link the classes, fields, and methods referenced in the bytecode, the change preserves binary compatibility in that scenario.

Binary compatibility concerns the contract at the class file and JVM linkage level, not merely whether source code recompiles.

### 1.3. Behavioral compatibility

Even when old source compiles and old bytecode runs, the outcome can still change.

For example, `message("Lan")` previously returned `"Hello, Lan"`, whereas the new version returns `"Welcome, Lan"`. The signature is unchanged, so source and binary compatibility are preserved; however, clients relying on the message content may be affected.

Behavioral compatibility depends on the published contract: return values, exceptions, side effects, ordering, null rules, thread safety, and other guarantees.

### 1.4. Quick comparison table

| Criterion | Test question | Subject tested |
|---|---|---|
| Source compatibility | Does old source recompile against the new API? | `.java` files |
| Binary compatibility | Does old bytecode link and run against the new API? | `.class` files, JARs |
| Behavioral compatibility | Does the program continue to satisfy the old contract? | Runtime output and behavior |

A good library release states clearly which kinds of compatibility are promised. Saying "backward compatible" without specifying source, binary, or behavior is easy to misinterpret.

## 2. Why does Java have different types of compatibility?

Java source code is translated by the compiler into bytecode inside `.class` files. During compilation, the compiler records symbolic references in the constant pool to the classes, fields, and methods the code uses.

At runtime, the JVM resolves those references by class name, member name, and descriptor. A descriptor encodes a method's parameter types and return type, or a field's type.

For example, the method:

```java
public String message(String name)
```

has the JVM descriptor:

```text
(Ljava/lang/String;)Ljava/lang/String;
```

In this descriptor:

- `(` begins the parameter list.
- `Ljava/lang/String;` is the `String` parameter.
- `)` ends the parameter list.
- `Ljava/lang/String;` after `)` is the return type.

Method name and descriptor together identify a method at the bytecode level. Consequently, changing a parameter type or return type can cause references in old bytecode to no longer match.

### 2.1. Source signatures and bytecode descriptors are not identical

At the Java language level, a method signature is based primarily on the method name and parameter types after applying generic/erasure rules. Return type does not allow creating a separate overload.

At the JVM level, a method descriptor includes the return type. That is why changing a return type can break binary compatibility even when the method name and parameter list stay identical.

For example, these two declarations cannot coexist as overloads in Java:

```java
String find(String key);
Object find(String key); // Cannot overload by return type alone
```

Yet if a library changes a method's return type from `String` to `Object`, the bytecode descriptor changes. Previously compiled clients may still reference the old descriptor and hit `NoSuchMethodError`.

### 2.2. Throws clauses are not part of method descriptors

The list of checked exceptions in `throws` is not part of a JVM descriptor.

For example:

```java
public String read() {
    return "data";
}
```

changed to:

```java
public String read() throws java.io.IOException {
    return "data";
}
```

The method name, parameters, and return type remain the same, so the descriptor does not change. Old binary clients can still link the method. However, recompiling source clients may now have to catch or declare `IOException`.

This is a classic example showing that source compatibility and binary compatibility are not the same.

### 2.3. Generics are erased when producing bytecode

Java uses type erasure to implement generics. For example:

```java
public void addAll(List<String> values)
```

typically has a descriptor using the erased `List` type:

```text
(Ljava/util/List;)V
```

If `List<String>` is changed to `List<Object>`, the erased descriptor may remain unchanged, so binary linkage still succeeds. However, client source may fail to compile due to different generic rules; generic metadata also changes and can affect code using reflection.

Do not compare method names alone to conclude binary compatibility. Inspect the actual class file descriptors when verifying.

## 3. Source compatibility: can old source be recompiled?

Source compatibility evaluates the experience of users upgrading a dependency and recompiling their application. The following changes commonly affect source compilation.

### 3.1. Removing or renaming a method

Version 1:

```java
public class UserService {
    public User findById(long id) {
        return load(id);
    }
}
```

Version 2 removes `findById` and provides only `find`:

```java
public class UserService {
    public User find(long id) {
        return load(id);
    }
}
```

Client source calling `findById(10)` no longer compiles. This is a source incompatibility. Old bytecode also cannot find the old method and will encounter a linkage error if that call path executes.

A smoother transition is to keep the old method and mark it deprecated for a transitional period:

```java
public class UserService {
    public User find(long id) {
        return load(id);
    }

    @Deprecated(since = "2.0", forRemoval = true)
    public User findById(long id) {
        return find(id);
    }
}
```

Keeping the old method gives clients time to migrate. Remove it only once the compatibility policy allows.

### 3.2. Changing parameter types

Suppose the old version has:

```java
public User find(long id)
```

and the new version has only:

```java
public User find(String id)
```

Client source passing `long` will no longer compile. The binary descriptor also changes, so old bytecode referencing the `long` parameter method can no longer find the matching method.

To support both forms during migration, keep the old overload and add the new overload:

```java
public User find(long id) {
    return find(Long.toString(id));
}

public User find(String id) {
    return loadByExternalId(id);
}
```

However, adding an overload also requires checking its impact on method resolution.

### 3.3. Adding an overload can make old source ambiguous

Old version:

```java
public void send(String value) {
    // ...
}
```

Client:

```java
sender.send(null);
```

New version adds an overload:

```java
public void send(String value) {
    // ...
}

public void send(Integer value) {
    // ...
}
```

Upon recompilation, `send(null)` becomes ambiguous because `null` is convertible to both `String` and `Integer`, neither of which is a subtype of the other. Existing client source no longer compiles.

Old bytecode that already resolved to `send(String)` during an earlier compilation still references that descriptor and can continue running. Thus, adding an overload can break source compatibility while preserving binary compatibility.

### 3.4. Adding a checked exception can break source compatibility

Old version:

```java
public String load() {
    return readValue();
}
```

New version:

```java
public String load() throws IOException {
    return readValue();
}
```

Old client source:

```java
String value = service.load();
```

may fail to recompile because the caller must catch `IOException` or declare it in `throws`.

The binary descriptor does not include `throws IOException`, so old bytecode still links. If the new method actually throws `IOException`, the exception can propagate out of the old caller at runtime even though the caller's source never declared it; the JVM does not enforce checked exceptions at runtime.

### 3.5. Reducing visibility

If a public method becomes protected or package-private, client source outside the package may fail to compile. Old bytecode still invoking that member may encounter `IllegalAccessError` at runtime.

Widening visibility is generally less risky than narrowing it, though you still need to review API contracts and naming/inheritance conflicts.

### 3.6. Changing generics can break source compatibility

Old version:

```java
public List<String> names() {
    return List.of("Alice", "Bob");
}
```

New version:

```java
public List<Object> names() {
    return List.of("Alice", "Bob");
}
```

Client source:

```java
List<String> names = service.names();
```

no longer compiles because `List<Object>` is not assignable to `List<String>`. Due to type erasure, the method descriptor may still be `()Ljava/util/List;`, so binary linkage may remain unchanged. Nonetheless, changing generic metadata and type contracts affects clients.

### 3.7. Interface changes can affect implementors

If you add an abstract method to an interface:

```java
public interface PaymentProvider {
    Receipt pay(Invoice invoice);

    void cancel(Receipt receipt); // New method
}
```

Existing source classes implementing `PaymentProvider` without defining `cancel` will fail to recompile until they supply an implementation.

Old binaries can still load, but if the program invokes the new method on an implementation that does not provide it, the JVM can throw `AbstractMethodError`.

A default method can reduce the burden on implementors:

```java
public interface PaymentProvider {
    Receipt pay(Invoice invoice);

    default void cancel(Receipt receipt) {
        throw new UnsupportedOperationException("Cancellation is not supported");
    }
}
```

However, adding a default method also requires checking for conflicts with methods of the same signature from other interfaces or superclasses. In some inheritance hierarchies, adding a default method can make source compilation ambiguous or cause linkage errors when a call no longer has a single unique default implementation.

## 4. Changes that usually preserve source compatibility

No rule replaces compiling actual client source, yet the following changes typically preserve source compatibility if they introduce no other conflicts:

- Adding a new method without altering existing overload resolution.
- Adding a new public class.
- Adding an overload that does not make existing calls ambiguous or silently select a different overload.
- Adding a new static method whose name does not collide with conflicting members.
- Modifying internal implementation without altering the API or compilation rules.

"Without altering existing overload resolution" is an important condition here: adding a new method is usually safe, whereas adding an overload can change how the compiler resolves existing source calls.

Source compatibility also does not guarantee clients receive no new warnings. For instance, marking a method `@Deprecated` may still compile while producing a warning; if the build enables `-Werror`, new warnings can fail the build. That is a build-process impact worth noting separately.


## 5. Binary compatibility: does old bytecode run with the new library?

Binary compatibility focuses on whether the JVM can resolve the references the compiler recorded in existing bytecode. A client can avoid recompilation if the new library still provides classes and members with matching names, descriptors, access permissions, and member kinds.

### 5.1. Removing a method or changing its descriptor

Library version 1:

```java
public class AccountService {
    public Account find(long id) {
        return load(id);
    }
}
```

The client is compiled with the method descriptor corresponding to the `long` parameter:

```java
Account account = service.find(42L);
```

If version 2 provides only:

```java
public Account find(String id) {
    return loadByExternalId(id);
}
```

old bytecode still demands the method with the old descriptor. The JVM does not automatically convert `long` to `String` when resolving a symbolic reference. When the call runs, the client can encounter `NoSuchMethodError`.

Renaming a method, removing a method, or changing a parameter type is usually binary incompatible unless the old member is retained.

### 5.2. Changing the return type also changes the descriptor

Old version:

```java
public String version() {
    return "1.0";
}
```

New version:

```java
public CharSequence version() {
    return "2.0";
}
```

Source code might be adjusted depending on usage, yet old bytecode references the descriptor returning `String`. The JVM looks up methods by descriptor, fails to find the old method, and can throw `NoSuchMethodError`.

To preserve binary compatibility, keep the old method or design a transition API using a differently named method. Java does not allow overloading solely by return type.

### 5.3. Narrowing visibility can cause access errors

If a previously public method is narrowed to protected or package-private, bytecode outside the package may still contain references to that method. When the JVM performs access checks, `IllegalAccessError` can occur.

Similarly, visibility changes on classes or fields must be evaluated. Not every visibility change triggers the same error at the same moment; errors may surface when a class is linked or when the access path actually executes.

### 5.4. Switching a method between static and instance

Old version:

```java
public static Config current() {
    return INSTANCE;
}
```

New version changes it to an instance method:

```java
public Config current() {
    return this.config;
}
```

Bytecode calling a static method uses a different invocation instruction than calling an instance method. When the new class file no longer has a member matching the invocation kind expected by old bytecode, the JVM can throw `IncompatibleClassChangeError`.

Changing in the opposite direction (instance to static) carries the same risk. Keeping the same name and parameters is not sufficient for binary compatibility.

### 5.5. Changing a field type

Bytecode references fields by name and field descriptor. If `public int count` changes to `public long count`, the descriptor changes. Old clients still request an `int` field and can encounter `NoSuchFieldError`.

```java
// Version 1
public int count;

// Version 2
public long count;
```

Public/protected fields are part of the binary API and should be changed cautiously. For new APIs, consider encapsulating state behind private fields and accessors to reduce direct coupling to field descriptors.

### 5.6. Adding an abstract method to an interface

When adding an abstract method to an interface, previously compiled classes can still be loaded. However, if a new call requires an implementation that an old class does not provide, the JVM can throw `AbstractMethodError`.

This is why adding a method to an interface differs from adding a method to a concrete class. You must consider external implementations that the library does not control.

If the new method can have a sensible default behavior, a default method can sometimes preserve compatibility. Even then, check for default method conflicts across realistic inheritance hierarchies.

### 5.7. Removing a class, changing class/interface kind, or changing superclass

Binary compatibility also depends on class structure:

- Removing a class referenced by a client can cause `NoClassDefFoundError`.
- Changing between class and interface can cause `IncompatibleClassChangeError`.
- Changing the superclass or implemented interfaces can affect method resolution, verification, and previously compiled subclasses.
- Changing a member from instance to static or vice versa can cause bytecode to invoke the wrong kind of member.

These are type-structure changes and generally carry higher risk than internal method-body changes.

## 6. Changes that usually preserve binary compatibility

Some changes usually preserve binary linkage for existing clients if they do not introduce other changes:

- Adding a new class or interface.
- Adding a new method to a class without altering existing members.
- Adding a new field.
- Adding a new overload, provided the old member remains with a compatible descriptor and visibility.
- Changing a method body without altering its name, descriptor, or accessibility.
- Adding a checked exception to a `throws` clause, because checked exceptions are not part of the JVM descriptor.

However, "binary compatible" does not mean every client runs properly. A new method body can throw different exceptions, return different data, or violate an earlier invariant.

### 6.1. Checked exceptions: binary compatible yet still able to change runtime experience

Suppose a client was compiled against a method declaring no checked exception:

```java
String value = service.load();
```

The new library version declares `throws IOException` and in some cases actually throws it. Old bytecode still links because the descriptor is unchanged, yet the exception can propagate out of the caller.

The JVM does not enforce checked exception rules. Catch-or-declare rules are compile-time checks performed on source code.

Therefore, adding a checked exception typically preserves binary compatibility while potentially breaking source compatibility and changing observable behavior for old clients.

### 6.2. Changing generic metadata

Generic signatures are stored in separate metadata; the JVM links methods by erased descriptors. Consequently, changing generic type parameters while keeping the erasure unchanged can preserve binary linkage.

However, client source may fail to compile, reflection code reading generic metadata can observe changes, and callers using raw types can hit runtime type errors. Do not treat an unchanged descriptor as proof that a generic API remains fully compatible.

## 7. Compile-time constants and inlined values

A `public static final` field of primitive type or `String` initialized with a constant expression can be a *constant variable*. Compilers typically inline the constant value directly into client bytecode.

Version 1:

```java
public final class Limits {
    public static final int MAX_RETRIES = 3;
}
```

Client:

```java
if (attempt < Limits.MAX_RETRIES) {
    retry();
}
```

After compilation, the client's bytecode may embed the literal value `3` instead of reading `Limits.MAX_RETRIES` at runtime.

If the library changes to:

```java
public final class Limits {
    public static final int MAX_RETRIES = 5;
}
```

old clients may continue using `3` until recompiled. Swapping in the new JAR does not automatically update values already inlined into existing `.class` files.

This is usually not a binary incompatibility because the field still exists, yet it can create behavioral divergence between old clients and newly compiled clients.

If a value may change across library versions or runtime configurations, consider an accessor method:

```java
public final class Limits {
    private Limits() {
    }

    public static int maxRetries() {
        return 5;
    }
}
```

Method calls execute at runtime, so existing clients receive the new value without needing recompilation to pick up an inlined constant.

## 8. Adding new methods: how safe is it?

Adding a method to a class generally preserves source and binary compatibility, though method resolution and inheritance still require attention.

### 8.1. Adding an overload can change behavior after recompilation

Old version had only:

```java
public void log(Object value) {
    System.out.println("object");
}
```

New version adds:

```java
public void log(String value) {
    System.out.println("string");
}
```

Old source:

```java
log(null);
```

previously called `log(Object)`. After recompiling against the new version, the compiler chooses `log(String)` because `String` is more specific than `Object`. The source still compiles, yet behavior has changed.

Old bytecode still invokes the descriptor for `log(Object)`, so it continues behaving as before. This shows how adding an overload can preserve both source and binary compatibility while altering behavior upon recompilation.

### 8.2. A new method can collide with inherited methods

When adding a method to a superclass or interface, that method can be inherited by subclasses the library does not control. This can:

- Change which method is selected when called on a subclass instance.
- Conflict with a method of the same signature having different static/instance status or visibility.
- Create default method conflicts in interface hierarchies.
- Prevent subclass source from recompiling or cause runtime errors for old binaries when called.

Therefore, before adding a method to a public base class or interface, check inheritance hierarchies and common implementors, not just the library class in isolation.

## 9. Behavioral compatibility: the program still runs, but has the contract changed?

Behavioral compatibility concerns everything observable by callers. A change can leave source and binary linkage intact while still breaking applications that rely on the prior contract.

### 9.1. Changing return values

A method keeps the same signature but returns different data:

```java
public BigDecimal calculateTax(BigDecimal amount) {
    // Old version: uses 8% tax rate
    // New version: uses 10% tax rate
}
```

Source and binary remain unchanged, yet business results change. If the tax rate is part of the published contract, this is an important behavioral change.

### 9.2. Changing exceptions

A method previously returned `null` when data was not found, whereas the new version throws `NoSuchElementException`. The signature can remain unchanged; source and binaries still compile and link, yet callers relying on the old behavior can fail.

Likewise, changing the exception type, the condition under which it is thrown, or throwing an exception earlier can constitute a behavioral incompatibility.

### 9.3. Changing null rules and validation

For example, a method previously accepted empty strings, whereas the new version rejects them:

```java
public User findByName(String name) {
    Objects.requireNonNull(name);
    if (name.isBlank()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    // ...
}
```

Tightening validation can make sense, yet callers that previously passed empty strings may be affected. Check whether null/blank rules were documented in the API contract or were merely accidental behavior.

### 9.4. Changing ordering or result stability

An API returning a list might previously have preserved insertion order, while the new version returns a different order. If the contract did not guarantee order, callers should not rely on it; nevertheless, the change can still expose implicit assumptions in applications.

If order is guaranteed, state it explicitly in Javadoc and cover it with tests.

### 9.5. Changing side effects or transaction boundaries

A method that previously only read data now updates `lastAccessedAt`; or one that previously committed a transaction now leaves transaction management to the caller. The signature stays the same, yet side effects change, affecting caller logic and retryability.

### 9.6. Changing synchronization, thread safety, or timing

An API that was previously thread-safe now uses unsynchronized mutable state; or callbacks that previously ran sequentially now execute on another executor. This can be a behavioral incompatibility even with identical bytecode.

Performance characteristics and latency can also form part of an operational contract if the system has SLAs. Not every performance difference is a breaking change, but foundational libraries should not ignore them.


## 10. Example matrix: which axes does a change affect?

The following table is a starting guide for analysis. Exact outcomes also depend on inheritance hierarchies, how clients call the API, and the published contract.

| Change | Source compatibility | Binary compatibility | Behavioral compatibility |
|---|---|---|---|
| Modify method body, keep API unchanged | Usually preserved | Usually preserved | May change |
| Remove public method | Broken | Broken if client references it | Not applicable since client may fail to run |
| Change parameter type without keeping old overload | Broken | Broken | May change |
| Change return type | May break | Broken due to descriptor change | May change |
| Narrow visibility | Broken for callers losing access | May break for old bytecode | May change |
| Add unambiguous overload | Usually preserved | Usually preserved | May change selected overload upon recompile |
| Add ambiguous overload | Broken for affected source | Old bytecode usually preserved | May change if new overload is chosen |
| Add checked exception | May break | Usually preserved | May throw new exception |
| Add abstract method to interface | Broken for implementors upon recompile | May fail when new method is called | May change |
| Change generic while preserving erasure | May break | Usually preserves descriptor | May affect reflection/type safety |
| Change compile-time constant value | Usually preserved | Usually preserved | Old clients may still use inlined value |
| Change result ordering | Preserved | Preserved | May break contract |
| Tighten validation | Preserved | Preserved | May break old callers |

Do not treat this table as an absolute rulebook. It helps identify which questions to verify; final conclusions must rest on the JLS, bytecode, client source, and behavioral tests.

## 11. Testing source compatibility

Source compatibility is tested by compiling representative client source against the new library version.

A controlled approach:

1. Preserve client source from the previous version.
2. Replace the dependency with the new artifact.
3. Recompile the old source without editing it.
4. Record compiler errors and new warnings.
5. Also verify real build flags, such as `-Werror`, annotation processors, and module paths.

Example:

```bash
javac -cp library-v2.jar -d client-classes src/com/example/client/App.java
```

If the real build uses the module path:

```bash
javac --module-path mods \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/App.java
```

Maintain a small source fixture suite representing how clients use the public API:

- Calling common methods and constructors.
- Extending open classes.
- Implementing interfaces.
- Using overloads with `null`, lambdas, method references, and generics.
- Catching checked exceptions.
- Accessing exposed fields or constants.
- Using reflection if the library commits that metadata as part of its contract.

### 11.1. Recompile the exact old source

If the source fixture has been edited to adapt to the new API, that test no longer proves source compatibility. Keep an unmodified baseline source set and run it as an independent check.

You can have a separate test suite for a migration guide, while keeping the distinction clear:

- **Compatibility compile test:** old source must compile as-is.
- **Migration test:** source updated per the upgrade guide must compile and work.

These two tests answer different questions.

### 11.2. Checking warnings and build tools

A change may produce no compile error yet introduce deprecation, unchecked, or annotation warnings. If a project enables `-Werror`, new warnings can cause the build to fail.

Also check real build settings: annotation processors, compiler plugins, module paths, target release, and lint flags can produce different results from a minimal `javac` command.

## 12. Testing binary compatibility

Binary compatibility requires a client compiled against the old library. Do not recompile the client between runs.

Sample workflow:

1. Compile version 1 of the library.
2. Compile the client against the version 1 JAR.
3. Keep the client `.class` files untouched.
4. Replace the version 1 JAR with the version 2 JAR.
5. Run the old client with the version 2 JAR.
6. Confirm no linkage errors occur from API changes.

Example directory layout:

```text
compat-test/
├── library-v1.jar
├── library-v2.jar
├── client-src/
│   └── App.java
└── client-classes/
    └── App.class
```

Compile the client once against version 1:

```bash
javac -cp library-v1.jar -d client-classes client-src/App.java
```

Run the old bytecode against the new library:

```bash
java -cp library-v2.jar:client-classes App
```

On Windows, use the `;` classpath separator:

```powershell
java -cp "library-v2.jar;client-classes" App
```

The crucial rule is not to re-run `javac` after swapping the JAR. Recompiling lets the compiler resolve against the new API and emit new bytecode, masking binary compatibility issues.

### 12.1. Linkage errors to recognize

| Error | Common cause |
|---|---|
| `NoSuchMethodError` | Method referenced by bytecode no longer exists with matching descriptor |
| `NoSuchFieldError` | Referenced field was removed or changed descriptor |
| `NoClassDefFoundError` | Required class is absent or cannot be defined |
| `IllegalAccessError` | Bytecode accesses a member that is no longer accessible |
| `IncompatibleClassChangeError` | Class/member kind no longer matches how bytecode invokes it |
| `AbstractMethodError` | Call requires an implementation not provided by the runtime class |

Not every occurrence of these errors is necessarily an API change. Missing dependencies, duplicate classpath versions, or incorrect module configurations can also cause them. Identify the exact class and member in the message before drawing conclusions.

### 12.2. Testing multiple client versions

A library may be consumed by clients compiled with different JDKs or library versions. If support policy requires it, retain binary fixtures from key client versions and run them against new artifacts.

Control the classpath/module path to be sure the JVM loads the intended new JAR. You can print `CodeSource` or use class-loading diagnostics in tests when investigating dependency conflicts.

## 13. Testing behavioral compatibility

Behavioral compatibility must be tested against the API contract. It cannot be deduced from source diffs or bytecode diffs alone.

### 13.1. Maintaining contract tests

For each public API, document what callers are entitled to expect:

- Valid and invalid inputs.
- Return values and null rules.
- Exceptions thrown in each scenario.
- Side effects and transaction boundaries.
- Element or callback ordering if promised.
- Synchronization and thread-safety rules.
- Charset, timezone, rounding, or locale rules where relevant.

Contract tests should express these guarantees via observable inputs and outcomes without depending on internal implementation details.

### 13.2. Comparing results between old and new versions

For APIs that can run side by side across two versions, use the same fixture set to record:

- Return values.
- Exception types.
- Side effects.
- Output ordering.
- Timing or resource usage if part of an SLA.

Not every output must be identical. If a change is intentional, decide upfront which differences are acceptable and update the contract, migration documentation, and tests accordingly.

### 13.3. Testing edge cases

Behavioral regressions appear in edge cases more often than on the happy path:

- `null`, empty strings, negative numbers, or extreme values.
- Empty collections and collections with duplicate elements.
- Malformed input or missing fields.
- Timeouts, retries, and cancellation.
- Large datasets or concurrency.
- Different locales, timezones, and charsets.

If an API alters validation or error handling, write explicit tests for these cases.

### 13.4. Distinguishing guaranteed behavior from implementation details

Not every behavior observed once becomes a contract. For example, iteration order of a collection without an ordering guarantee can change without violating the API contract. Even so, if real clients depended on that behavior, changing it can still break deployments.

API documentation should clearly state what is guaranteed and what is not. That helps clients avoid depending on internal details and gives maintainers room to evolve the implementation safely.

## 14. Tools for checking APIs and bytecode

### 14.1. Using javap to inspect descriptors

`javap`, included with JDK 17, displays signatures and bytecode descriptors:

```bash
javap -classpath library-v1.jar -s -p com.example.AccountService
```

- `-s` displays descriptors.
- `-p` includes non-public members.
- `-classpath` selects the artifact to inspect.

Running this on both old and new versions and comparing descriptors reveals methods or fields whose bytecode representation changed.

`javap` is a class file inspection tool; it does not draw complete conclusions about behavioral compatibility or every source compatibility rule.

### 14.2. Using API diff tools

Tools such as **Revapi** and **japicmp** compare APIs between two artifacts, reporting changes to classes, methods, fields, visibility, and certain binary/source incompatibilities.

They are valuable in CI for catching unintended changes before publishing. Configure public API scope, modules, dependencies, and severity rules properly; do not assume every flagged change is a breaking change under every contract.

### 14.3. Using jdeps for dependency analysis

`jdeps`, included in the JDK, analyzes class/package/module dependencies of an artifact. It helps detect dependencies on JDK internals or inspect module dependencies, though it does not replace API compatibility diff tools.

### 14.4. Combining tools and tests

An effective verification workflow may include:

- API diffs to catch structural API changes.
- Compile fixtures to check source compatibility.
- Running binary fixtures to check binary compatibility.
- Contract/regression tests to check behavioral compatibility.
- Integration tests to check dependencies, module paths, and runtime configuration.

No single tool proves all three kinds of compatibility.


## 15. Managing compatibility in the release process

Compatibility should be considered during API design and in every pull request, rather than waiting until release time.

### 15.1. Defining public API scope

Before setting a compatibility policy, define which elements belong to the supported API:

- Public/protected classes, interfaces, methods, constructors, and fields.
- Packages documented as public.
- Exported module packages.
- SPIs that third parties are permitted to implement.
- Annotations, generic contracts, and reflection metadata if committed.
- Long-lived stored or exchanged data formats and protocols.

Not every public class in an implementation is necessarily part of the supported API. You can use internal packages or unexported modules to hide implementation details, while documenting those boundaries clearly.

### 15.2. Using deprecation as a transition phase

If you want to replace a published API, retain the old API and mark it deprecated:

```java
@Deprecated(since = "3.1", forRemoval = true)
public User findById(long id) {
    return find(longIdToKey(id));
}
```

Javadoc should point to the replacement API:

```java
/**
 * Finds a user by its numeric identifier.
 *
 * @deprecated Use {@link #find(String)} instead.
 */
@Deprecated(since = "3.1", forRemoval = true)
public User findById(long id) {
    return find(Long.toString(id));
}
```

Deprecation does not by itself guarantee source or binary compatibility in every scenario, yet it helps clients discover the migration path in IDEs and compilers. Remove the API only when your versioning policy permits and an appropriate migration guide is available.

### 15.3. Maintaining an API baseline

For widely consumed libraries, keep the previously released artifact as a baseline. Each build can:

1. Compare the new public API against the baseline.
2. Flag notable binary/source changes.
3. Require maintainers to classify changes.
4. Run compile fixtures and binary fixtures.
5. Run contract tests.
6. Document release notes and migration notes.

A baseline prevents accidentally deleting a method or changing a descriptor during a supposedly internal refactor.

### 15.4. Stating compatibility types in release notes

Rather than merely writing "API compatible", release notes should specify:

- Source compatibility: are source edits or new warning fixes required?
- Binary compatibility: clients compiled against which versions remain supported?
- Behavioral compatibility: did results, exceptions, defaults, ordering, or side effects change?
- Migration: if there is a breaking change, what must be updated and why?

If a change intentionally breaks compatibility, document the upgrade path and when the old API is removed.

## 16. SemVer and compatibility in Java libraries

Semantic Versioning (SemVer) is a common convention for communicating change impact:

- **PATCH:** bug fixes compatible with the existing contract.
- **MINOR:** backward-compatible additions within the committed public API.
- **MAJOR:** incompatible changes requiring client adjustments.

However, version numbers do not prove compatibility by themselves. A small change can accidentally make old source ambiguous; a major release might still preserve most of the old API. Establish explicit rules for the public API, modules, SPIs, and behavior your project commits to.

For Java libraries, specify whether the project guarantees source compatibility, binary compatibility, or both within a release line. When supporting multiple JDKs, state the tested JDK range and module configurations.

## 17. Workflow for reviewing an API change

When reviewing a pull request with API changes, follow this sequence:

1. **Identify scope:** which members/packages/modules belong to the public API or SPI?
2. **Check source:** does old client source still recompile? Did overload resolution, generics, checked exceptions, or inheritance change?
3. **Check binary:** did names, descriptors, visibility, static/instance status, or superclass/interfaces change?
4. **Check behavior:** did return values, exceptions, side effects, ordering, null handling, concurrency, or timing change?
5. **Run tools:** API diff, `javap`, and any required dependency checks.
6. **Run fixtures:** compile old source, run old bytecode against the new artifact, and run contract tests.
7. **Decide version impact:** classify as compatible or breaking under project policy.
8. **Update documentation:** Javadoc, migration guides, and release notes must reflect the new contract.

If a change only modifies an implementation, still run behavioral tests. If it alters descriptors, test previously compiled clients. If it adds an overload, recompile source fixtures containing ambiguous calls or literals such as `null`.

## 18. Common misconceptions

### Misconception 1. Source compatibility implies binary compatibility

False. Source may recompile after an API change, yet old bytecode may require a descriptor that no longer exists. Conversely, adding a checked exception can preserve binary linkage while breaking recompilation of old source.

### Misconception 2. Binary compatible means the application runs identically to before

False. Bytecode can link successfully while the method returns different values, throws new exceptions, or changes side effects.

### Misconception 3. Keeping the method name is enough

False. Descriptors include parameter types and return types; static/instance invocation kind and visibility also matter.

### Misconception 4. Adding a method is always safe

Not always. Adding an overload can make existing source ambiguous or alter which overload is chosen upon recompilation. Adding a method to an interface or base class can affect implementors and subclasses.

### Misconception 5. Adding a checked exception is just a documentation change

False. `throws` is absent from descriptors, so binary linkage is usually preserved; however, recompiling client source may have to handle the exception, and old clients may observe the new exception at runtime.

### Misconception 6. Generic changes do not affect binary compatibility, so they are completely safe

False. Erasure can preserve the descriptor, yet source type checking, reflection metadata, and type safety can still change.

### Misconception 7. API diff tools can prove behavioral compatibility

False. Structural API analysis tools cannot understand all business contracts. Contract tests and integration tests are required.

### Misconception 8. If the source fixture compiles, there is no need to run binary fixtures

False. Compile tests verify source compatibility. Binary fixtures must be compiled against the old artifact and executed without recompiling against the new artifact.

### Misconception 9. public static final constants are always read from the new JAR

False. Constant variables may be inlined into client bytecode by the compiler. Old clients can retain the old value until recompiled.

### Misconception 10. Version numbers automatically guarantee compatibility

False. Versioning is only a project commitment/convention. You must inspect APIs, bytecode, and behavior to verify actual changes.

## 19. Self-practice exercises

### Exercise 1. Classify the three compatibility types

A method keeps its name and descriptor but changes its result from `"A"` to `"B"`.

**Answer:** Source compatibility and binary compatibility are usually preserved; behavioral compatibility changes if callers depend on the old result.

### Exercise 2. Adding an overload with null

A library has `send(String)`. The new version adds `send(Integer)`. An existing client calls `send(null)`.

**Answer:** Client source may fail to recompile because the call becomes ambiguous. Old bytecode still calls the `send(String)` descriptor if the old method remains present.

### Exercise 3. Adding a checked exception

Method `load()` adds `throws IOException` while keeping its name, parameters, and return type.

**Answer:** The binary descriptor usually does not change, so binary compatibility is preserved. Client source may need to catch or declare the exception; runtime behavior may change if the exception is actually thrown.

### Exercise 4. Changing the return type

A method changes from `String value()` to `CharSequence value()`.

**Answer:** The descriptor changes because JVM method descriptors include the return type. Old client bytecode may hit `NoSuchMethodError`; client source must be re-checked against how the return value is used.

### Exercise 5. Changing a constant value

A library changes `public static final int LIMIT = 10` to `20`.

**Answer:** Old clients may still use `10` due to compiler constant inlining. This is typically a behavioral difference between old clients and newly compiled clients rather than a binary incompatibility.

### Exercise 6. Adding an abstract method to an interface

An abstract method is added to an interface. An old class implements the interface without defining that method.

**Answer:** Old class source will not recompile until it implements the method. Old binaries can load, but calling the new method can throw `AbstractMethodError`.

### Exercise 7. Testing binary compatibility

To verify whether a client compiled against library v1 runs with library v2, should you recompile the client against v2 before running?

**Answer:** No. You must keep the bytecode produced with v1 unchanged and swap only the library at runtime; recompiling means the test no longer measures binary compatibility.

### Exercise 8. Choosing the right test type

A change only alters the ordering of elements in a result without changing API signatures.

**Answer:** Both source and binary tests may pass. Contract/behavioral tests are required to verify whether ordering was guaranteed.

### Exercise 9. Choosing a tool

Which tool inspects method descriptors inside a Java 17 JAR?

**Answer:** `javap -s`, typically combined with `-p` and `-classpath` to view descriptors and members.

### Exercise 10. Writing release notes

A release adds a new overload that makes calls like `send(null)` ambiguous.

**Answer:** Explicitly note the source incompatibility, explain fixes such as casting the argument to the intended type or calling a distinctly named method, and add a compile fixture to prevent regressions.

## 20. Official references

- [Java Language Specification 17 — Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): binary compatibility rules when changing classes and interfaces.
- [Java Language Specification 17 — Chapter 15: Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): overload resolution, method invocation, and source-level expressions.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, field/method descriptors, and class file structure.
- [JDK 17 Tool Specifications — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): tool for inspecting class file info and descriptors.
- [JDK 17 Tool Specifications — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): class, package, and module dependency analysis.
- [OpenJDK Revapi](https://revapi.org/): tool for comparing APIs across artifact versions.
- [japicmp](https://siom79.github.io/japicmp/): tool for comparing binary APIs across JARs.

**Remember:** Source compatibility asks whether old source recompiles; binary compatibility asks whether old bytecode links with the new library; behavioral compatibility asks whether the program continues to uphold its observable contract. Verify all three: compile source fixtures, run binary fixtures compiled from the old version, and run contract/regression tests. A change is safe only when it meets the compatibility policy your library has committed to.
