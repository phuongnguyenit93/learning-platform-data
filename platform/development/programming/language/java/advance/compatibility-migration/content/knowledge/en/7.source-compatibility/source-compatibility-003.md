# New Overloads Causing Changed Method Selection or Ambiguous Calls

In Java, a method call is selected at compile time based on the static type of the receiver, the static types of the arguments, accessible methods, and the language's overload resolution rules. The JVM does not wait until runtime to inspect the actual argument values and pick a matching overload. Once the compiler selects a signature, the bytecode records a reference to that exact method name and descriptor.

Consequently, adding an overload to a library can change how existing source code recompiles. A call that was previously valid can become ambiguous; a call that still compiles can switch to a different overload and produce different behavior. Meanwhile, binaries already compiled against the old API version usually continue calling the old descriptor if the old method is preserved.

This is an important source compatibility risk when upgrading libraries or frameworks. It can also appear when a JDK version adds a new overload to a platform API, or when a project adds an overload to a shared class called by multiple modules.

## 1. Overloads Are Selected at Compile Time

### 1.1. Overloading and Overriding Are Different Mechanisms

**Overloading** is declaring multiple methods with the same name in the same scope but different parameter lists. Differences can be in parameter count, parameter types, or parameter type order. Differing only in return type does not constitute a valid overload.

```java
class MessageSender {
    void send(String text) { }
    void send(byte[] bytes) { }
    void send(String text, boolean urgent) { }
}
```

The compiler selects the matching overload when compiling each call. Selection depends on static types and applicability rules, not on runtime variable values.

**Overriding** is a subclass providing an alternative implementation for an inherited method with a compatible signature. At runtime, dynamic dispatch chooses the overriding implementation based on the object's actual class, yet the method signature was already fixed at compile time.

Example:

```java
class Base {
    void handle(Object value) {
        System.out.println("Base Object");
    }
}

class Child extends Base {
    @Override
    void handle(Object value) {
        System.out.println("Child Object");
    }

    void handle(String value) {
        System.out.println("Child String");
    }
}

Base target = new Child();
target.handle("hello");
```

The compiler sees only the methods available through the static type `Base`, so it selects the `handle(Object)` signature. At runtime, the JVM dispatches to `Child.handle(Object)`. The `Child.handle(String)` overload is not selected because the receiver's static type is `Base`.

This distinction matters when evaluating API changes: overload resolution is a compile-time decision; overriding is runtime implementation selection for the already-compiled descriptor.

### 1.2. Static Argument Types Determine Overload Selection

```java
class Converter {
    String convert(Object value) {
        return "object";
    }

    String convert(String value) {
        return "string";
    }
}

Converter converter = new Converter();
String text = "Java";
Object object = text;

converter.convert(text);   // convert(String)
converter.convert(object); // convert(Object)
```

Both variables hold the same `String` object, yet the second call selects `convert(Object)` because the variable's declared type is `Object`. The compiler does not use the object's runtime type to revisit and choose a more specific overload.

Therefore, when an API adds overloads, inspect static types at real call sites—including generic types, lambda expressions, method reference return types, and types inferred via `var`.

## 2. Which Phases Does the Compiler Use to Find Overloads?

The JLS specifies a process of finding applicable methods and then choosing the most specific method. Broadly, this proceeds through three phases:

1. **Strict invocation:** looks for matching methods without boxing/unboxing and without varargs expansion.
2. **Loose invocation:** if the first phase finds none, permits conversions such as boxing, unboxing, and related conversions.
3. **Variable arity invocation:** if the first two phases yield no match, considers varargs calls with flexible argument counts.

The compiler stops at the first phase that yields a set of applicable methods, then chooses the most specific method within that set. Consequently, you cannot simply count how many parameter types look close to the arguments to guess the outcome.

Example:

```java
class NumberHandler {
    void handle(long value) {
        System.out.println("long");
    }

    void handle(Integer value) {
        System.out.println("Integer");
    }
}

new NumberHandler().handle(10);
```

For literal `10` of type `int`, `handle(long)` is applicable via primitive widening right in strict invocation. `handle(Integer)` requires boxing and is therefore considered only during loose invocation. The compiler picks `handle(long)` in the first phase and does not continue searching in later phases.

This shows that adding an overload does not automatically alter selection. Impact depends on the new method set, static argument types, and the phase in which a method becomes applicable.

## 3. Adding Overloads Can Make Existing Calls Ambiguous

### 3.1. `null` Arguments and Two Unrelated Types

Suppose the first library version has the API:

```java
import java.util.Objects;

public class DestinationSender {
    public void send(String destination) {
        Objects.requireNonNull(destination);
        System.out.println("Send to text destination");
    }
}
```

Client calls:

```java
DestinationSender sender = new DestinationSender();
sender.send(null);
```

In the first version, only `send(String)` exists, so the call is valid. Later, the library adds an overload:

```java
public void send(java.nio.file.Path destination) {
    Objects.requireNonNull(destination);
    System.out.println("Send to path destination");
}
```

`String` and `Path` are both reference types with no subtype relationship between them. The `null` literal can convert to either type. Neither method is more specific than the other, so recompiling old source against the new library fails with:

```text
reference to send is ambiguous
  both method send(String) and method send(Path) match
```

This is source incompatibility: source code that previously compiled no longer compiles.

Intent can be clarified at the call site using a cast:

```java
sender.send((String) null);
sender.send((Path) null);
```

However, if `null` represents a business state, a better design may be an overload with a distinct name, a value object, or an API expressing clear intent rather than forcing every consumer to add casts.

### 3.2. Overloads Taking Functional Interfaces Make Lambdas Ambiguous

A lambda has no standalone type like a normal variable. It is a poly expression checked against the functional interface the compiler considers as the target type.

Initial API version:

```java
import java.util.function.Supplier;

public class TaskRunner {
    public void submit(Supplier<String> task) {
        System.out.println(task.get());
    }
}
```

Client calls:

```java
new TaskRunner().submit(() -> "completed");
```

Later, the API adds:

```java
import java.util.concurrent.Callable;

public void submit(Callable<String> task) throws Exception {
    System.out.println(task.call());
}
```

`Supplier<String>` and `Callable<String>` are both functional interfaces whose function descriptors take no parameters and return `String`. The lambda `() -> "completed"` fits both. Neither interface is a subtype of the other, so the compiler lacks a unique most specific overload. The existing call becomes ambiguous.

The client can specify the target type using an intermediate variable or a cast:

```java
Supplier<String> supplier = () -> "completed";
new TaskRunner().submit(supplier);

new TaskRunner().submit((Supplier<String>) () -> "completed");
```

Adding overloads between functional interfaces with matching shapes is a notable source compatibility risk. Similar cases arise with `Runnable`, `Callable`, `Supplier`, `Function`, `Consumer`, custom callback interfaces, and method references.

### 3.3. Method References Can Also Lose Unique Resolution

Method references are target-typed against the candidate overload. Example:

```java
class ActionRegistry {
    void register(java.util.function.Supplier<String> action) { }
}

class Actions {
    static String create() {
        return "created";
    }
}

new ActionRegistry().register(Actions::create);
```

If the API adds an overload taking another functional interface whose function descriptor also matches `Actions::create`, the compiler may be unable to pick a most specific overload. Complexity grows when the method reference points to an overloaded method itself, or when target interfaces have differing parameter/return types.

When changing APIs that accept callbacks, compile representative call sites containing lambdas and method references, including call sites outside the library's repository. An API can compile internally yet break consumer source in another repository.

## 4. Adding Overloads Can Change Selected Overloads While Still Compiling

### 4.1. A More Specific New Overload

Initial version:

```java
public class Formatter {
    public String format(Object value) {
        return "object:" + value;
    }
}
```

Client:

```java
Formatter formatter = new Formatter();
String result = formatter.format("Java");
```

When only `format(Object)` exists, the compiler records a call to descriptor `format(Object)`. Later, the library adds:

```java
public String format(String value) {
    return "string:" + value;
}
```

When recompiling the client against the new library, `String` is more specific than `Object`, so the compiler picks `format(String)`. The source still compiles, yet results and side effects can change.

Illustration of the shift:

| API Version | Selected Overload for `String` Variable | Result |
|---|---|---|
| Before adding overload | `format(Object)` | `object:Java` |
| After adding overload and recompiling | `format(String)` | `string:Java` |

If the two overloads differ in logging, validation, caching, transactions, or null rules, changing selection can cause a business regression even when compilation and simple tests pass.

### 4.2. Varargs Overloads Can Change the Meaning of `null`

Initial version:

```java
public class LoggerApi {
    public void log(Object value) {
        System.out.println("single value: " + value);
    }
}
```

Client:

```java
new LoggerApi().log(null);
```

Later, the API adds:

```java
public void log(Object... values) {
    System.out.println("number of values: " + values.length);
}
```

During overload resolution, a varargs declaration can be viewed as a method taking a single `Object[]` parameter during fixed-arity phases. `Object[]` is a subtype of `Object`, so for a `null` literal, the varargs overload can be more specific than `log(Object)`. The compiler can select the varargs overload as a fixed-arity call and pass `null` as the array itself rather than wrapping it in a one-element null array.

The compiler usually emits a warning about an inexact varargs call. If the implementation accesses `values.length`, the program can throw `NullPointerException`.

The client can clarify intent:

```java
logger.log((Object) null);   // one null object
logger.log((Object[]) null); // the null array itself
logger.log(new Object[]{null}); // an array with one null element
```

This case is especially critical when an API has overloads accepting `Object`, `Object[]`, or varargs. Adding an overload can change both the method invoked and the shape of the passed argument.

### 4.3. Inherited Overloads and Superclass API Changes

Overloads can be added in a superclass or interface used by a client. When source is recompiled, the candidate method set can change even though the client class was not edited. For example, a library adding an overload to a shared base class can impact subclasses and call sites invoking through the base type.

When analyzing, check:

- Whether the method is declared directly or inherited.
- Whether same-named methods exist in superclasses, interfaces, or subclasses.
- Whether the new method is an instance, static, or default method.
- Whether the receiver's static type at the call site is a concrete type or an interface/base type.
- Whether generic type parameters or compiler-generated bridge methods exist.

Do not reason from method names alone. Inspect the full set of accessible methods at the call site and compile against the exact new API version.

## 5. Generic Inference and Overload Resolution

Generic methods complicate overload resolution because the compiler must infer type arguments, apply bounds, and check convertibility. Adding a generic overload can alter the candidate set or prevent unique call resolution.

Initial API example:

```java
class ValueReader {
    <T> T read(Object source) {
        return null;
    }
}
```

Later, the library adds another overload whose type parameter or parameterized type matches the call site. The compiler may infer different type arguments or select a different overload. If two methods share the same erasure, Java rejects the declaration outright due to name clash; generics do not allow overloads differing solely in type arguments erased by type erasure.

When changing generic APIs, verify:

- Type inference with concrete type arguments, wildcards, and raw types.
- Bounds such as `<T extends Number>` and relationships between bounds.
- Generic varargs and `@SafeVarargs`.
- Method invocations taking a target type from assignment or return context.
- Lambdas/method references, which are poly expressions and can depend on target types.
- Erasure, bridge methods, and name clashes.

For example, `List<String>` and `List<Integer>` cannot form two separate overloads because after type erasure both erase to `List`. To overload by element type, the API needs a different design such as distinct method names or dedicated wrapper types.

## 6. Overload Resolution and Type Conversions

When evaluating a change, consider the conversions that can make a new overload applicable:

| Conversion | Example | Notes |
|---|---|---|
| Identity | `String` → `String` | Usually the direct preferred choice |
| Primitive widening | `int` → `long` | Considered in strict invocation |
| Reference widening | `String` → `Object` | Follows subtype relationships |
| Boxing | `int` → `Integer` | Considered in loose invocation |
| Unboxing | `Integer` → `int` | Can throw NPE at runtime if value is null |
| Reference widening after boxing | `int` → `Integer` → `Number` | Can make generic/reference methods candidates |
| Variable arity | multiple arguments → varargs array | Considered only in variable-arity phase if prior phases had no match |

The compiler does not simply score each conversion. It executes the JLS phases and selects the most specific method. Therefore, when adding overloads, compile real examples instead of relying on intuition that "the closer type will be called".

### 6.1. Primitive Widening and Boxing

```java
class NumericApi {
    void accept(long value) { }
    void accept(Integer value) { }
}

new NumericApi().accept(1);
```

For literal `1` of type `int`, `accept(long)` can apply via primitive widening in strict invocation. `accept(Integer)` requires boxing and is considered only in loose invocation. Thus, a new `Integer` overload is not necessarily chosen just because it looks close to `int`.

If `accept(int)` is added, identity conversion selects that method. If `accept(Number)` is added, boxing and reference widening apply. These changes can alter selection depending on the expression's static type.

### 6.2. Null and Reference Types

The `null` literal converts to any reference type. If one overload accepts a subtype of another overload's parameter, the subtype is generally more specific. If the two types are unrelated, the call can become ambiguous.

```java
void process(Object value) { }
void process(String value) { }

process(null); // process(String) because String is more specific than Object
```

In the case:

```java
void process(String value) { }
void process(java.nio.file.Path value) { }

process(null); // ambiguous
```

The two types have no subtype relationship, so the compiler cannot pick a unique method.

### 6.3. Lambdas and Target Typing

Lambdas are checked against the functional interface the compiler is evaluating. When an API adds an overload accepting another functional interface of the same shape, a prior lambda call can become ambiguous.

```java
void run(java.util.function.Supplier<String> supplier) { }
void run(java.util.concurrent.Callable<String> callable) { }

run(() -> "done"); // ambiguous
```

If an API accepts callbacks, consider distinct method names to express semantics. `runAsync(Supplier<T>)` and `submit(Callable<T>)` are clearer than two `run(...)` overloads with near-identical functional interfaces.

## 7. Source Compatibility and Binary Compatibility

An overload change must be evaluated from two perspectives.

**Source compatibility** is the ability of existing source code to continue compiling against the new API. Adding an overload can break source compatibility because:

- An old call becomes ambiguous.
- A call still compiles yet picks the new overload.
- A lambda or method reference loses a unique target type.
- Generic inference picks a different type or method.
- Varargs and `null` alter the call shape.

**Binary compatibility** is the ability of already-compiled bytecode to continue linking against the new API. When merely adding an overload while preserving the old method, existing binaries continue referencing the old descriptor. The JVM does not re-run overload resolution on already-compiled bytecode.

For example, a client compiled when only `format(Object)` existed embeds a reference to the method descriptor `format(Ljava/lang/Object;)Ljava/lang/String;`. After the library adds `format(String)`, old bytecode continues invoking `format(Object)` if that method remains intact. Recompiling the source may cause the compiler to choose `format(String)`.

| Scenario | Recompiled Old Source | Old Binary Running with New Library |
|---|---|---|
| Add a more specific overload | May select a different method | Usually continues calling old descriptor |
| Add an equally applicable overload | May become ambiguous | Usually continues calling old descriptor |
| Keep old method, change implementation | Still compiles | Executes the new implementation of the old method |
| Remove or change old method descriptor | May fail compilation | May fail linkage such as `NoSuchMethodError` |

"Usually" here assumes the old method still exists, retains its descriptor and appropriate accessibility, and meets other binary compatibility conditions. Adding an overload does not protect clients if you simultaneously remove the old method, alter parameter/return types, change accessibility, or break inheritance relationships.

## 8. Why Do Overload Changes Appear During Migration?

### 8.1. Upgrading Third-Party Libraries

Vendors may add overloads to support new data types, callbacks, or APIs. For example, an HTTP library adds overloads taking `Path`, `URI`, `InputStream`, or a new functional interface. Legacy client source containing `null`, lambdas, or method references can be affected upon recompilation.

### 8.2. Upgrading Frameworks or BOMs

Frameworks may add overloads to utility classes, builders, callback registries, configuration APIs, or base classes. Upgrading a BOM updates many modules to newer versions together. An untouched call site can pick a different overload because the available method set changed.

### 8.3. Upgrading the JDK

Java platform APIs may add new overloaded methods or interface/default methods. When a newer compiler release sees new APIs, source code can select a different method. When still targeting an older runtime, setting `--release` appropriately prevents source from referencing APIs absent on that runtime. If moving runtime completely to the newer version, evaluate source compatibility of JDK APIs called by the application.

### 8.4. Upgrading the Compiler or Source Level

A newer compiler may implement updated language rules, improved type inference, or recognize more expression types. When the source level changes, an invocation can be analyzed under different rules or receive new target typing. Review both JLS changes and compiler release notes.

### 8.5. Internal Project API Changes

A team may add an overload to a shared service, utility, or base class to accept an additional input type. If multiple modules call that API, a small change can break other modules that the author did not directly compile. This frequently happens in multi-module repositories or shared internal libraries.

## 9. How to Detect Changed Overload Resolution

### 9.1. Locate Sensitive Call Sites

Prioritize auditing calls involving:

- Null literals: `method(null)`.
- Untyped lambda parameters: `method(x -> ...)` or `method(() -> ...)`.
- Method references: `method(Type::name)` or `method(object::name)`.
- Varargs: calls with varying argument counts or `null` in the trailing position.
- Generic methods: type inference, wildcards, raw types, and overloaded generic methods.
- Primitives/wrappers: boxing, unboxing, and primitive widening.
- Receivers typed as a superclass/interface whose runtime object is a subclass.
- APIs taking `Object`, `CharSequence`, `Serializable`, `Comparable`, or unrelated interfaces.

IDE or code search can locate candidate call sites, yet cannot replace compiling against the new dependency version. A lambda expression may turn ambiguous only once the new classpath is applied.

### 9.2. Compile Old Source Against the New API

Maintain a suite of source fixtures or consumer samples representing how the API is called. Compile them against both the old and new library versions with the agreed JDK/source level. Compare:

- Which calls previously compiled yet fail on the new version.
- Which calls switched to a different overload.
- Which lambda/method reference calls became ambiguous.
- Which new warnings appear, especially varargs and unchecked conversions.
- Which method descriptors the compiler emits in bytecode.

You can use `javap -c -s` to inspect compiled calls:

```bash
javap -classpath build/classes -c -s com.example.Client
```

The output displays invocation instructions and the called method descriptor. Comparing outputs when compiling the same source against two API versions confirms which overload the compiler selected.

### 9.3. Run Behavioral Regression Tests, Not Only Compilation

When a new overload changes selection while source still compiles, compile-only tests will not catch semantic shifts. Verify:

- Return values and exceptions.
- Validation and null handling.
- Logging, auditing, and metrics.
- Transactions, retries, timeouts, and side effects.
- Which serializer/formatter/converter is chosen.
- Whether callbacks run synchronously or asynchronously, call counts, and ordering.
- Whether the new overload handles resource/lifecycle management differently from the old one.

If an API is used by multiple consumers, maintain contract tests or consumer compilation tests covering key call patterns.

## 10. Designing APIs to Reduce Risk When Adding Overloads

API authors can reduce source compatibility risks at design time.

### 10.1. Avoid Overloads Taking Unrelated Types When `null` Is Valid Input

If two overloads accept `String` and `Path`, a `null` literal easily triggers ambiguity. Consider:

```java
void sendToName(String name) { }
void sendToPath(Path path) { }
```

Distinct method names let consumers express intent without casting just to satisfy the compiler.

### 10.2. Avoid Overloading Functional Interfaces with Similar Shapes

Instead of:

```java
void execute(Supplier<String> action) { }
void execute(Callable<String> action) throws Exception { }
```

design method names expressing distinct contracts:

```java
void executeValue(Supplier<String> action) { }
void executeChecked(Callable<String> action) throws Exception { }
```

Separate names prevent lambdas/method references from turning ambiguous and clarify semantics for API users.

### 10.3. Be Careful When Adding Varargs Overloads

Varargs overloads can interact with array overloads and `Object` overloads. Test call sites with `null`, arrays, one argument, and multiple arguments. When distinguishing "one null value" from "null array" matters, provide distinct APIs or use wrapper types.

### 10.4. Do Not Add Overloads Solely to Silently Change Semantics

If an existing method's behavior is relied upon by consumers, do not add a more specific overload with the same name solely to alter how that type is handled. Use a new method with a clear name, builder option, or versioned API.

### 10.5. Keep the Old Method and Provide a Migration Path

When evolving an API, keep the old method during a transition period if possible, deprecate it with replacement guidance, add compatibility tests, and document the planned removal version. Keeping the old method lets binary consumers continue linking, though source consumers can still hit ambiguity if the new overload conflicts. Evaluate call sites before releasing.

## 11. Strategies for Fixing Call Sites When New Overloads Cause Issues

If upgrading to the new library is required, consumers can clarify input types:

**Use an explicitly typed variable:**

```java
String destination = null;
sender.send(destination);
```

**Use a cast to specify the overload:**

```java
sender.send((String) null);
```

**Declare the target type for a lambda:**

```java
Supplier<String> task = () -> "done";
runner.submit(task);
```

**Use a distinct method name if provided by the API:**

```java
runner.submitCallable(() -> loadValue());
```

**Turn varargs into an explicit array or typed element:**

```java
logger.log((Object) null);
logger.log(new Object[]{null});
```

Casting is a local fix, yet you must cast to the exact type intended by business logic. Do not cast arbitrarily just to pass compilation, as that could force the compiler to select an overload with different semantics. Add tests asserting the expected method/behavior.

## 12. Analyzing Overload Changes in Dependency/Framework Migrations

When upgrading a library version, record an API diff between old and new versions. Tools like `japicmp` or Revapi help detect declarative binary/source API changes. However, adding an overload is usually binary compatible when the old method remains intact, so binary API diff reports may not flag it as a breaking change.

Therefore, the evaluation process should have two layers:

1. **API surface diff:** detect added methods, removed methods, modifier changes, generic signatures, inheritance, and descriptors.
2. **Consumer source compilation:** compile representative call sites against the new API version to detect ambiguities or changed overload selections.

For internal libraries, maintain a consumer compatibility fixture covering common call shapes: `null`, lambdas, method references, primitives/wrappers, generics, varargs, and base-typed receivers. Run this fixture as a verification gate whenever adding overloads.

If no consumer fixture exists, at minimum search for call sites with the same method name across the repository and compile all dependent modules. For libraries consumed outside the repository, publish migration notes for consumers because your team cannot compile their code on their behalf.

## 13. Complete Example: `null` Overload Breaks Compilation of Old Source

Suppose version 1 of a library has:

```java
package com.example.api;

public class DestinationApi {
    public String resolve(String value) {
        return "text:" + value;
    }
}
```

Consumer:

```java
DestinationApi api = new DestinationApi();
String result = api.resolve(null);
```

The consumer compiles cleanly and its bytecode embeds the descriptor taking `String`. Version 2 adds:

```java
public String resolve(java.net.URI value) {
    return "uri:" + value;
}
```

`String` and `URI` have no subtype relationship. When recompiling the consumer against version 2, `resolve(null)` becomes ambiguous.

One consumer fix:

```java
String result = api.resolve((String) null);
```

Yet if `null` was never meant to be valid input, the API should specify a null contract and consumers should avoid passing `null`. If `null` has business meaning, the new method should use a distinct name or wrapper type to make the target kind explicit.

For binary consumers already compiled against version 1, if version 2 preserves `resolve(String)` with the same descriptor and accessibility, existing bytecode continues linking to that method. This demonstrates how binary compatibility can hold while source compatibility breaks.

## 14. Complete Example: Lambda Becomes Ambiguous After Adding an Overload

Version 1:

```java
public class AsyncApi {
    public void execute(java.util.function.Supplier<String> action) {
        System.out.println(action.get());
    }
}
```

Consumer:

```java
new AsyncApi().execute(() -> "OK");
```

Version 2 adds:

```java
public void execute(java.util.concurrent.Callable<String> action)
        throws Exception {
    System.out.println(action.call());
}
```

A lambda with no parameters returning `String` matches both `Supplier<String>` and `Callable<String>`. Neither functional interface is a subtype of the other, so the compiler cannot pick a unique most specific overload.

The consumer can write:

```java
Supplier<String> action = () -> "OK";
new AsyncApi().execute(action);
```

However, from an API design standpoint, separating method names is easier to use and more stable:

```java
executeValue(() -> "OK");
executeChecked(() -> readWithCheckedException());
```

## 15. Checklist When Adding Overloads or Upgrading Libraries

- [ ] Listed overloaded methods added, modified, or inherited in the new version.
- [ ] Audited call sites passing `null` literals or null-typed variables.
- [ ] Audited lambdas and method references against target functional interfaces.
- [ ] Checked generic inference, wildcards, raw types, and type erasure.
- [ ] Checked primitive widening, boxing/unboxing, and varargs.
- [ ] Confirmed static types of receivers and arguments at key call sites.
- [ ] Compiled consumer fixtures against both old and new API versions.
- [ ] Compared bytecode descriptors via `javap` where overload selection needed confirmation.
- [ ] Ran regression tests to detect behavioral shifts even when source still compiles.
- [ ] Distinguished source compatibility from binary compatibility.
- [ ] Considered alternative API designs such as separate method names or wrapper types.
- [ ] Updated migration notes for external consumers if needed.

Adding an overload can preserve binary compatibility while still breaking compilation of existing source code or silently altering runtime behavior after recompilation. Evaluating API changes must therefore cover both consumer source compilation and runtime behavior, especially around `null`, lambdas, method references, generics, and varargs. When APIs have clear semantics, consumer fixtures, and verification against new versions, teams can catch overload shifts early before they propagate to dependent modules or library customers.
