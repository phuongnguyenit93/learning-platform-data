# Type Erasure, Bridge Methods, and Changing Generic APIs

Java generics help the compiler check data types before a program runs. However, at the class file level, most information about type arguments such as `String`, `Integer`, or `Customer` does not become independent runtime types. The compiler applies **type erasure**, inserts casts when necessary, and sometimes generates **bridge methods** to preserve overriding behavior after generic types are erased.

This creates an important characteristic of Java compatibility migration: **a seemingly small change in a generic declaration may preserve or break the binary contract depending on whether it alters a method's name, descriptor, or inheritance relationship**. Conversely, a change with the same descriptor after erasure can still prevent old source from compiling or make runtime behavior differ from before.

This lesson explains how `javac` transforms generic source into bytecode, why bridge methods appear, how to distinguish `Signature` metadata from JVM method descriptors, and how to evaluate risk when upgrading JDKs, libraries, frameworks, or modifying APIs that use generics.

## 1. Four Contract Layers to Distinguish

When evaluating a generic API, do not look only at the Java declaration in the IDE. Examine at least four layers:

| Contract Layer | Meaning | Example |
|---|---|---|
| Source API | How the compiler sees type parameters, type arguments, bounds, and overloads | `List<String>` or `<T extends Number> T get()` |
| Erased API | Types remaining after erasing type parameters | `List` or `Number get()` |
| Binary descriptor | Name and parameter/return types used by the JVM to link a method | `(Ljava/lang/Number;)Ljava/lang/Number;` |
| Runtime behavior | Casts, dispatch, reflection, and how libraries process data | `ClassCastException` or `AbstractMethodError` |

**Source compatibility** asks whether old consumer source still compiles against the new API version. **Binary compatibility** asks whether previously compiled consumer bytecode still links and runs against the new library version. **Behavioral compatibility** asks whether results, exceptions, serialization, and side effects uphold the contract.

These three concepts do not replace each other. An API can be binary-compatible yet source-incompatible; or both can be valid while business logic still changes.

## 2. How Does Type Erasure Work?

### 2.1. Erasure of an Unbounded Type Parameter

Given the class:

```java
public class Box<T> {
    private T value;

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

If `T` has no explicit upper bound, the erasure of `T` is `Object`. The type-equivalent bytecode model looks like:

```java
public class Box {
    private Object value;

    public Object get() {
        return value;
    }

    public void set(Object value) {
        this.value = value;
    }
}
```

This is a conceptual representation to understand erasure, not an actual Java source file emitted by the compiler. The class file can still store generic `Signature` metadata so that other compilers and reflection APIs can read the original generic declaration.

When a client writes:

```java
Box<String> box = new Box<>();
box.set("Java");
String text = box.get();
```

the compiler knows `box.get()` yields a result of type `String` per the generic source API, yet the runtime method returns `Object`. Therefore, the client's bytecode may contain a `checkcast java/lang/String` operation before assigning the result to the `String` variable.

### 2.2. Erasure of a Bounded Type Parameter

When a type parameter has an upper bound, erasure is determined by the first bound:

```java
public class NumericBox<T extends Number> {
    private T value;

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Because `T extends Number`, the methods at the bytecode level take the form:

```text
get()Ljava/lang/Number;
set(Ljava/lang/Number;)V
```

It is no longer `Object` like an unbounded `Box<T>`. This is why changing a generic bound can be a real breaking change.

With multiple bounds:

```java
class Key<T extends Comparable<T> & java.io.Serializable> {
    T copy(T key) {
        return key;
    }
}
```

The erasure of `T` is `Comparable` because it is the first bound. Swapping the order of the two interface bounds to `Serializable & Comparable<T>` can change the erasure to `Serializable`. Although the set of constraints in source looks similar, the JVM method descriptor can change.

### 2.3. Erasure of a Parameterized Type

Both `List<String>` and `List<Integer>` erase to `List`. Similarly:

| Source declaration | Erasure |
|---|---|
| `List<String>` | `List` |
| `Map<String, Customer>` | `Map` |
| Unbounded `T` | `Object` |
| `T extends Number` | `Number` |
| `T extends Serializable & Cloneable` | `Serializable` |
| `List<? extends Number>` | `List` |

Generic type arguments are typically not stored as runtime parameters in JVM descriptors. This is why `List<String>` and `List<Integer>` cannot be used to define two overloads differing only in type arguments.

### 2.4. Consequences When Using Generics

The familiar limitations of Java generics stem from the fact that most type arguments are not reified into distinct runtime types:

- You cannot write `new T()` without an appropriate factory, constructor reference, or `Class<T>`.
- You cannot use `T.class`.
- You cannot directly create `new T[10]`.
- You cannot check `instanceof List<String>`; the form `List<?>` can be used in suitable contexts.
- You cannot overload two methods differing only between `List<String>` and `List<Integer>`.
- Raw types and unchecked casts can cause type errors to appear only when runtime executes a cast.

Generics can carry additional information in class-file attributes, but the JVM does not automatically enforce `String` or `Integer` type arguments on every runtime operation.

## 3. JVM Descriptors Differ from Generic Signature Metadata

A class file can store both a **descriptor** and a **Signature attribute** simultaneously. The two kinds of information serve different purposes.

Consider the method:

```java
public java.util.List<String> findAll() {
    return java.util.List.of("A", "B");
}
```

At the class file level, the method descriptor reflects only `List`:

```text
descriptor: ()Ljava/util/List;
```

The generic `Signature` can additionally store the type argument:

```text
Signature: ()Ljava/util/List<Ljava/lang/String;>;
```

The descriptor is used by the JVM when linking methods. `Signature` metadata is used by compilers and reflection APIs to represent source-level generic information; it does not make the JVM treat `List<String>` as a separate runtime class from `List<Integer>`.

This leads to two cases that must be distinguished:

1. Changing `List<String> findAll()` to `List<Integer> findAll()` usually preserves the descriptor `()Ljava/util/List;`. Old bytecode may continue linking, but consumer source upon recompilation and runtime processing may be affected.
2. Changing `T get()` from unbounded `T` to `T extends Number` changes the descriptor from `()Ljava/lang/Object;` to `()Ljava/lang/Number;`. This can break binary compatibility.

To inspect both layers of information:

```bash
javap -classpath build/classes -p -s com.example.Box
javap -classpath build/classes -p -v com.example.Box
```

Depending on compiler version and class, `-s` shows descriptors; `-v` shows the constant pool, `Signature`, flags, and additional metadata. Inspect the actual class files of the released artifact, not just source in the IDE.

## 4. Why Must the Compiler Generate Bridge Methods?

### 4.1. The Post-Erasure Problem: Overriding Methods Have Different Descriptors

Consider a generic superclass:

```java
public class Node<T> {
    private T data;

    public void setData(T data) {
        this.data = data;
    }

    public T getData() {
        return data;
    }
}
```

A subclass using a concrete type:

```java
public class MyNode extends Node<Integer> {
    @Override
    public void setData(Integer data) {
        super.setData(data);
    }

    @Override
    public Integer getData() {
        return super.getData();
    }
}
```

In Java's source type system, `MyNode.setData(Integer)` is a valid override of `Node<Integer>.setData(Integer)`. However, after erasure, the method declared in `Node` has parameter `Object`, whereas the method in `MyNode` has parameter `Integer`.

The corresponding method descriptors are:

```text
Node.setData(Ljava/lang/Object;)V
MyNode.setData(Ljava/lang/Integer;)V

Node.getData()Ljava/lang/Object;
MyNode.getData()Ljava/lang/Integer;
```

Without an additional mechanism, the JVM might not dispatch an old call to the overriding implementation required by source code. The compiler resolves that mismatch using bridge methods.

### 4.2. Compiler-Generated Bridge Methods

Conceptually, the compiler adds methods in `MyNode` looking like:

```java
// Simulating bridge logic, not source to write manually.
public void setData(Object data) {
    setData((Integer) data);
}

public Object getData() {
    return getData();
}
```

The example above only illustrates the forwarding flow; ordinary Java source cannot verbatim duplicate every bridge alongside a method with a different return type due to source signature rules. The compiler generates bridges directly at the bytecode level.

The `setData(Object)` bridge casts to `Integer` and calls `setData(Integer)`. The `getData():Object` bridge calls the method returning `Integer`, then returns the result as `Object`. Consequently, binaries referencing the erased descriptor of the superclass still dispatch to the subclass.

With bridges for covariant return types, the JVM may need two methods with the same name and parameter descriptors but different return descriptors. Java source does not allow declaring overloads differing only in return type, yet a class file can contain compiler-generated bridge methods to maintain proper linkage.

### 4.3. Bridges Are Real Methods in the Class File

A bridge method is not merely a compiler concept. It is released as a method in `.class` and usually carries flags:

```text
ACC_PUBLIC
ACC_BRIDGE
ACC_SYNTHETIC
```

Exact flags depend on visibility and the specific case. Use:

```bash
javap -classpath build/classes -p -c -s -v com.example.MyNode
```

to inspect methods, descriptors, cast/delegate bytecode, and flags. In Java reflection, `Method.isBridge()` and `Method.isSynthetic()` help identify bridges.

The important point for migration: **bridges are part of the binary that compiled clients may already depend on**. If build processes, instrumentation, bytecode shading, minimization, or hierarchy changes inadvertently strip a required bridge, consumers may suffer linkage errors or incorrect dispatch.

### 4.4. Casts in Bridges Can Expose Raw Type Bugs

Example:

```java
MyNode myNode = new MyNode();
Node raw = myNode; // raw type

raw.setData("text");
```

The compiler may warn about raw/unchecked usage yet still permit the call. Bytecode invokes `Node.setData(Object)`. The JVM dispatches to the corresponding bridge in `MyNode`, the bridge casts `String` to `Integer`, and throws `ClassCastException`.

The error does not prove the bridge works improperly. The bridge is enforcing `MyNode`'s type contract at runtime as best as possible after type arguments were erased. The root cause is a client bypassing generic type safety.

Do not add `@SuppressWarnings("unchecked")` to mask the issue if the data is not genuinely of the promised type.

## 5. Bridge Methods Do Not Appear Only Because of Generic Parameters

Another situation that creates bridges is a **covariant return type**: a subclass overrides a method while returning a more specific subtype.

```java
class Animal {
}

class Dog extends Animal {
}

class AnimalFactory {
    public Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    public Dog create() {
        return new Dog();
    }
}
```

In Java source, `DogFactory.create():Dog` validly overrides `AnimalFactory.create():Animal`. In the JVM, the return type is part of the method descriptor. The compiler can generate a `create():Animal` bridge so that calls compiled against the superclass still dispatch properly to `create():Dog`.

This is an example that does not require type parameters. It helps separate two points:

- Type erasure is the general mechanism of generics.
- Bridge methods are the compiler's solution when overriding/dispatch must be preserved after erasure or with covariant returns.

Do not assume every synthetic method is a generic bridge; many other tools also generate synthetic methods or supporting bytecode.

## 6. Which Generic API Changes Preserve Descriptors, and Which Break Descriptors?

### 6.1. Changing Only a Collection's Type Argument

API v1:

```java
public List<String> names();
```

API v2:

```java
public List<CharSequence> names();
```

Both have the erased return type `List`. The descriptor remains:

```text
()Ljava/util/List;
```

Therefore, an old binary usually still links if classes/methods, visibility, hierarchy, and other conditions stay unchanged. However, old consumer source:

```java
List<String> values = api.names();
```

may fail to compile against v2 because `List<CharSequence>` cannot be assigned to `List<String>`. Generics in Java are invariant for ordinary type arguments.

Even when merely replacing `List<String>` with `List<Integer>` and old binaries still link, old code may retrieve elements and cast them to `String`, leading to `ClassCastException` if the new library returns `Integer`.

**Unchanged descriptor** does not mean **unchanged source contract or behavior**.

### 6.2. Changing an Upper Bound That Alters Erasure

API v1:

```java
public class Identity<T> {
    public T echo(T value) {
        return value;
    }
}
```

Method v1 after erasure:

```text
echo(Ljava/lang/Object;)Ljava/lang/Object;
```

API v2:

```java
public class Identity<T extends Number> {
    public T echo(T value) {
        return value;
    }
}
```

Method v2 after erasure:

```text
echo(Ljava/lang/Number;)Ljava/lang/Number;
```

Client v1 compiled a reference to the descriptor `echo(Object):Object`. When running that binary with library v2 that only has `echo(Number):Number`, the JVM does not automatically pick the new method based on type assignability; the binary may throw `NoSuchMethodError`.

This is a binary breaking change, even though both the class name and method name remain unchanged.

### 6.3. Changing a Bound Where the Erased Descriptor May Not Change

Not every bound change alters the descriptor. Example:

```java
public class Store<T> {
    public void add(List<T> items) {
    }
}
```

Changing `T` to `T extends Number`, the method still takes `List` at the descriptor level:

```text
add(Ljava/util/List;)V
```

However, generic `Signature` metadata and the types consumers are allowed to pass have changed. Therefore, source compatibility and runtime behavior still need checking.

Evaluate **erasure at every position in the descriptor**, rather than concluding that every bound change breaks binary compatibility or every generic change is safe.

### 6.4. Order of Multiple Bounds Can Affect the ABI

API v1:

```java
class KeyStore<T extends Comparable<T> & java.io.Serializable> {
    public T normalize(T key) {
        return key;
    }
}
```

The erasure of `T` is `Comparable`. If modified to:

```java
class KeyStore<T extends java.io.Serializable & Comparable<T>> {
    public T normalize(T key) {
        return key;
    }
}
```

the erasure of `T` becomes `Serializable`. The method descriptor can change according to the first bound, even though both interfaces remain declared constraints.

With multiple interface bounds, declaration order matters at the erasure level. If there is a class bound, the class bound must precede interface bounds according to Java rules.

### 6.5. Changing Class/Interface Hierarchies

Changing generic superclasses, generic interfaces, type arguments, or override positions can cause the compiler to generate a different set of bridges upon recompilation. An API that previously had a bridge for an old descriptor may no longer have that bridge in the new version.

What must be compared is not only source declarations, but also:

- Actual methods in the binary, including synthetic/bridge methods.
- Descriptors of every method.
- Superclass, implemented interfaces, and generic supertypes.
- Visibility, `static`/instance, `abstract`/concrete, and `final`.
- Inherited or overridden methods.
- Whether old consumer code uses `invokevirtual`, `invokeinterface`, or another invocation form.

A hierarchy change may sometimes remain source-compatible upon recompilation, yet old binaries may encounter `NoSuchMethodError` or `AbstractMethodError`. Results must be verified on the exact binary combination.

## 7. Runtime Errors When Bridges or Erased Methods No Longer Match

### 7.1. NoSuchMethodError

Typically occurs when bytecode references a method with a name/descriptor that runtime no longer provides during resolution.

For example, an old consumer references:

```text
Identity.echo(Ljava/lang/Object;)Ljava/lang/Object;
```

but the new version only has:

```text
Identity.echo(Ljava/lang/Number;)Ljava/lang/Number;
```

When the call is resolved, the JVM may throw `NoSuchMethodError`. Return descriptor changes also matter because JVM descriptors include the return type.

### 7.2. AbstractMethodError

Can occur when an interface/class method is resolved, but the actual receiver has no concrete implementation matching the requested method.

For example, a library changes a generic interface resulting in a different erased method descriptor, while an implementation built from the old version has not been recompiled. Depending on the hierarchy and call site, an interface call may lead to `AbstractMethodError`.

Inspect interface v1/v2, implementation class v1/v2, and compiler-generated bridge methods. Do not fix the error by adding casts in the consumer before understanding which runtime method is missing.

### 7.3. ClassCastException

Bridges often contain casts to convert erased parameters to the concrete type of the implementation. Raw-type clients or invalid unchecked casts can push wrong-typed values through the bridge and cause runtime failures.

For generic return types, the consumer compiler can also insert `checkcast` where the return value is used. If a library changes element types while preserving the descriptor, casts in old consumers may fail.

### 7.4. IncompatibleClassChangeError and Other Linkage Errors

Changing a class to an interface, an instance method to a static method, changing access, or changing hierarchies can lead to other linkage errors. `NoSuchMethodError` and `AbstractMethodError` are subcases of linkage errors; do not attribute everything to type erasure.

Before concluding the root cause, read the stack trace, check which JAR is actually loaded, and compare the class-file APIs of the participating versions.

## 8. Generic Overloads and Name Clashes Due to Erasure

Java does not allow two methods in the same class to differ only in type arguments after erasure:

```java
class Processor {
    void process(List<String> values) {
    }

    // Invalid: same erasure as the method above.
    void process(List<Integer> values) {
    }
}
```

Both erase to `process(List)`. The compiler reports a name clash because the JVM cannot distinguish two overloads solely by erased type arguments.

Similarly, when extending a generic superclass, a subclass might accidentally declare a method with the same erasure as an inherited method without validly overriding it under source rules. This is why the compiler produces errors like “name clash: same erasure, yet neither overrides the other”.

Example illustrating the risk:

```java
class Parent<T> {
    void consume(T value) {
    }
}

// When inspecting source, compare erasure and override rules of the new method.
class Child extends Parent<String> {
    // A method with the same name taking Object can collide with the erasure
    // of the inherited method and lead to a name clash error.
    void consume(Object value) {
    }
}
```

The goal is not to force extra overloads at all costs. Determine whether the change should be a properly typed override, a method with a different name, a separate interface, or an adapter.

### 8.1. Generics and Overload Resolution Are Two Distinct Layers

Type erasure occurs when the compiler emits bytecode. Prior to that, source overload resolution uses type arguments, upper bounds, wildcards, inference, and Java rules. Adding or modifying generic overloads can make old calls ambiguous or select a different method when recompiled.

For instance, if an API has:

```java
void handle(Object value) {
}

void handle(Number value) {
}
```

and a client has a variable of type `Integer`, then `handle(Number)` is the more specific overload. However, if a new generic method has complex constraints, the compiler needs to infer type parameters before selecting an overload. You cannot look at two erased descriptors and deduce what the source compiler will choose.

When evaluating a generic API change, also check:

- Method invocations with a `null` argument.
- Type inference from assignment/return contexts.
- Wildcards such as `? extends Number` and `? super Integer`.
- Raw types and unchecked conversions.
- Lambdas and method references with target functional interfaces.
- Generic varargs, boxing, and primitive widening.
- Erasure name clashes and generated bridge methods.

## 9. Raw Types, Heap Pollution, and Binary Compatibility

Raw types allow interoperability with pre-generics code or code that dropped type arguments. Example:

```java
List<String> names = new ArrayList<>();
List raw = names;

raw.add(123); // unchecked warning

String first = names.get(0); // possible ClassCastException
```

At runtime, the collection is still an `ArrayList` and most of the `String` type argument is not reified. The compiler promised `names.get(0)` is a `String`, so it can insert a cast in the consumer. The `Integer` value inserted via raw access causes the cast to fail.

In migrations, old code often contains raw types, unchecked casts, or generic varargs. When a library changes its generic contract, these spots risk causing runtime errors even if the API does not change at the descriptor level.

Signs to audit:

- Compiler warnings `rawtypes` and `unchecked`.
- Casts from raw collections to parameterized collections.
- Generic varargs and heap pollution scenarios.
- Reflection creating `List`/`Map` and casting to generic types.
- Data from JSON, databases, or message queues mapped into generic types.
- Generated source using raw types to interact with old frameworks or libraries.

Do not treat adding `@SuppressWarnings` as a way to guarantee compatibility. If an unchecked operation must be accepted, explicitly document assumptions about the data and have tests verifying them.

## 10. Reflection and Frameworks See Generics Differently from JVM Linkage

The JVM uses erased descriptors to link methods, whereas reflection can read generic `Signature` metadata:

```java
Method method = Repository.class.getMethod("findAll");

System.out.println(method.getReturnType());
System.out.println(method.getGenericReturnType());
```

For a return type of `List<Customer>`, `getReturnType()` typically returns `List.class`; `getGenericReturnType()` can return a `ParameterizedType` containing `Customer`.

Frameworks such as JSON serializers/deserializers, dependency injection, ORMs, HTTP clients, type token libraries, and validation frameworks may use generic metadata to infer models, converters, or bindings.

Therefore, changing `List<Customer>` to `List<Order>` may preserve the descriptor yet cause frameworks to choose a different deserialization type. That is a behavioral compatibility risk even though the JVM does not report `NoSuchMethodError`.

### 10.1. Bridge Methods in Reflection

A class with bridges can display multiple methods with the same name in `getDeclaredMethods()` results. If a framework iterates over methods without distinguishing bridges from original methods, it may:

- Register the same handler twice.
- Pick the wrong method for a serializer or mapper.
- Miscount the number of methods in the API.
- Mishandle annotations or generic metadata.
- Apply validation, security, or transaction advice unexpectedly.

Modern frameworks usually have strategies to recognize bridges, yet when upgrading JDKs/frameworks or changing annotation processors, verify the exact version and actual behavior.

### 10.2. Generic Metadata Can Be Stripped by Build Tools

Bytecode optimizers, obfuscators, shading, minimizers, or class transformation tools can interfere with `Signature` attributes or synthetic/bridge methods. If generic metadata is stripped, the JVM may still load the class, but reflection-based frameworks will lack required type information.

In release builds, compare artifacts after all packaging steps against freshly compiled class files. Do not inspect only the `build/classes` directory if production actually runs a shaded JAR or a container image holding transformed artifacts.

## 11. Generics in APIs Published to Consumers in Other Modules

When a Java module publishes a shared library, generic APIs can become a contract with many consumers compiled at different times.

Three consumer groups must be identified:

1. **Compiled consumers:** have only old classes/JARs and must continue linking against the new library.
2. **Source consumers that will recompile:** affected by type checking, inference, and overload resolution of the new API.
3. **Reflection/code-generation consumers:** may depend on generic `Signature`, annotations, bridges, and method names at runtime.

If you only run unit tests inside the library repository, the team typically has not verified consumers compiled against earlier versions. That is especially risky for plugin APIs, public SDKs, framework extension points, and shared libraries used across multiple services.

When upgrading frameworks or JDKs, record the versions of both provider and consumer. One module might be compiled on JDK 21 targeting Java 17; another module still runs JDK 17; additionally, a transitive dependency may have been compiled with different erased descriptors.

## 12. Process for Analyzing a Generic API Change

### Step 1: Lock Down the Two Artifacts to Compare

Identify library v1 and v2 by group/artifact/version, commit, and checksum. Verify the exact artifacts present on compile/runtime classpaths. If multiple versions are present, first determine which version the class loader selects.

### Step 2: Record Before and After Source Declarations

Save class/interface declarations, type parameters, upper bounds, generic methods, return types, parameter types, superclasses, and implemented interfaces.

Example tracking table:

| Element | v1 | v2 |
|---|---|---|
| Type parameter | `T` | `T extends Number` |
| Method | `T echo(T)` | `T echo(T)` |
| Erasure of T | `Object` | `Number` |
| Descriptor | `(Object)Object` | `(Number)Number` |
| Risk | Baseline | May break binary compatibility |

### Step 3: Compare JVM Descriptors

Use `javap -s` or an API diff tool on both artifacts:

```bash
javap -classpath lib-v1.jar -p -s com.example.Identity
javap -classpath lib-v2.jar -p -s com.example.Identity
```

Do not look only at `T echo(T)` in source; determine the erased parameter and return descriptors of the method.

### Step 4: Compare Bridge and Synthetic Methods

Inspect class files using:

```bash
javap -classpath lib-v1.jar -p -v com.example.MyNode
javap -classpath lib-v2.jar -p -v com.example.MyNode
```

Look for `ACC_BRIDGE`, `ACC_SYNTHETIC`, and old/new descriptors. If hierarchies or method return types changed, pay special attention to added, removed, or altered-body bridges.

### Step 5: Compile Old Consumer Source Against v2

Keep consumer v1 source, switch the dependency to v2, and recompile. Record:

- Generic type inference errors.
- Incompatible types or missing methods.
- Name clashes.
- Ambiguous overloads.
- New unchecked warnings.
- Changes in which method the compiler selects.

This result evaluates source compatibility and does not replace binary testing.

### Step 6: Run Old Consumer Binaries Against v2

Use consumer class files compiled against v1, replace v1 with v2 on the runtime classpath without recompiling the consumer, and run the relevant flows.

This is the binary compatibility check. If it fails, identify the actual class name, method descriptor, method owner, and class loader in the stack trace.

### Step 7: Run Behavioral and Integration Tests

Test real data flowing through casts, generic collections, serializers, dependency injection, reflection, plugin loading, and bridge dispatch. Passing source/binary checks does not prove serialization, validation, or transaction semantics remained intact.

### Step 8: Record Results in the Compatibility Matrix

Each issue needs component, version, affected method, source/binary/runtime impact, evidence, owner, mitigation plan, and closure criteria.

## 13. Supporting Analysis Tools

### 13.1. javap

`javap` is the most direct tool for inspecting erasure/bridge details:

```bash
javap -classpath library.jar -p -s com.example.Api
javap -classpath library.jar -p -c -v com.example.Api
```

Focus on descriptors, `Signature`, `ACC_BRIDGE`, `ACC_SYNTHETIC`, inheritance, and invocation instructions.

### 13.2. japicmp and Revapi

API comparison tools like japicmp or Revapi can detect removed methods, return/parameter type changes, hierarchy, visibility, and binary/source differences. Configure baseline artifacts, plugin versions, and public API scope properly.

Some generic `Signature` changes may be flagged as source compatibility changes even when the descriptor stays unchanged. Read the warning categories emitted by the tool rather than collapsing every change into a single “breaking” or “non-breaking” label.

### 13.3. Dependency Graph

Gradle and Maven may select dependency versions different from directly declared versions. Reference commands:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency example-library --configuration runtimeClasspath
./mvnw dependency:tree
```

Compare compile and runtime graphs, including transitive dependencies. `NoSuchMethodError` can result from a consumer compiling against one version while runtime loads another, rather than a new generic bug.

### 13.4. jdeps

`jdeps` helps analyze class, package, and module dependencies; it is not a tool for checking all generic `Signature` metadata, bridge dispatch, or source compatibility. It can assist in understanding dependencies, but `javap`, API diffs, and consumer tests are needed to evaluate erasure/bridge scenarios.

## 14. Build and JDK Configuration During Verification

Record the JDK running the build, the JDK compiling code, and the JVM running consumers separately. For example, when building with JDK 21 while still releasing a library supporting Java 17, `--release 17` restricts the Java platform APIs and bytecode emitted by the compiler. It does not automatically guarantee third-party dependencies preserve binary API compatibility.

Gradle Groovy DSL example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Maven Compiler Plugin example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Even with proper configuration, still compare library binaries and bridge methods. `--release` does not stop dependency providers from removing erased methods or changing generic bounds.

In multi-module builds, check generated sources, annotation processors, Kotlin/Groovy/Scala compilation, and custom source sets as well. Each compiler has its own configuration; do not assume `JavaCompile`'s `options.release` applies to every task.

## 15. API Design Strategies to Maintain Compatibility

### 15.1. Avoid Changing Type Parameter Bounds in Released APIs

Changing `T` to `T extends Number` can alter erased descriptors. If data needs to be constrained, you can add a new method with a clear name, a value object, or an adapter while keeping the old method during the transition period.

### 15.2. Do Not Treat Type Arguments as Internal Details When Public APIs Have Generic Signatures

Changing `List<String>` to `List<Integer>` keeps the descriptor yet can break source consumers and runtime behavior. If the data contract changes, provide a migration guide, compatibility tests, and sometimes create a new method/DTO.

### 15.3. Do Not Depend on Accidentally Generated Bridges

Bridge methods are a compiler mechanism supporting overriding under Java standards. Do not design APIs by calling bridges directly via reflection or relying on unpublished names/flags as contracts. If a bridge is already required by old binaries, preserve ABI compatibility across migrations.

### 15.4. Use Adapters When Breaking a Generic Contract Is Necessary

If v2 must change from `Object` to `Number`, keeping a method with the old descriptor and forwarding data in a controlled manner is one strategy. However, design it so source declarations do not collide on erasure or create name clashes. Often a different method name, wrapper type, or separate compatibility class is required.

Do not simply add an `echo(Object)` method alongside `echo(T extends Number)` without checking erasure, overriding, and overloading; doing so can introduce a new overload with different semantics or declaration conflicts in the hierarchy.

### 15.5. Use Major Versions for Intentional Breaking Changes

If old descriptors, source contracts, or behavior cannot be preserved, publish the breaking change, define transition versions, and instruct consumers to recompile. For APIs used outside the organization, also announce changes that do not cause compile errors yet alter returned data.

## 16. End-to-End Example: Changing a Generic Bound in a Shared Library

Suppose v1 of the `core-api` library has:

```java
package com.example.core;

public class ValueHolder<T> {
    private T value;

    public ValueHolder(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Consumer v1:

```java
ValueHolder<Integer> holder = new ValueHolder<>(10);
holder.set(20);
Integer current = holder.get();
```

In v1, the constructor, `get`, and `set` use erasure `Object`. Later, v2 changes the class to:

```java
package com.example.core;

public class ValueHolder<T extends Number> {
    private T value;

    public ValueHolder(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

The related descriptors change:

| Element | v1 | v2 |
|---|---|---|
| Constructor | `(Ljava/lang/Object;)V` | `(Ljava/lang/Number;)V` |
| `get` | `()Ljava/lang/Object;` | `()Ljava/lang/Number;` |
| `set` | `(Ljava/lang/Object;)V` | `(Ljava/lang/Number;)V` |

Old consumers still hold symbolic references to v1's constructor and methods. Running that binary against v2 can lead to `NoSuchMethodError` when resolving the old descriptors.

On the other hand, consumer source using `ValueHolder<Integer>` can compile successfully against v2 when recompiled. This demonstrates:

- Similar source code may still compile.
- Old binaries may no longer link.
- Binary compatibility cannot be inferred from the fact that new consumer source compiles.

A controlled migration option is to retain the v1 class/API for a period and add a new API, such as `NumericValueHolder<T extends Number>`. New consumers use the new API; old consumers still have the previous class and descriptors. The team can remove the old API in a later major version after an upgrade plan is in place.

## 17. Common Mistakes

| Misconception | Why it is dangerous | How to handle |
|---|---|---|
| “Generics are erased so changing generic declarations is always binary-safe” | The first bound can change erasure and descriptors | Compare erased method/constructor descriptors |
| “`List<String>` and `List<Integer>` are two distinct runtime types” | Both typically share the same erasure `List` | Separate source type contracts from runtime descriptors |
| “Bridge methods are just metadata and can be removed” | Consumer bytecode may need bridges to dispatch correctly | Check `ACC_BRIDGE` and preserve proper ABI |
| “Changing a bound only affects compiler warnings” | Can cause `NoSuchMethodError` | Run old binaries against the new library |
| “Recompiling everything and passing is enough” | Does not test already-released consumer binaries | Separate source and binary compatibility tests |
| “Keeping the descriptor guarantees behavior remains unchanged” | Casts, generic metadata, and serializers can change | Test behavior/reflection/serialization |
| “Every bridge is generated by generics” | Covariant returns may require bridges | Inspect actual bytecode and hierarchies |
| “Test only main classes, ignore shaded JARs” | Packaging can alter metadata or bridges | Test final artifacts after transformation |
| “`--release 17` guarantees all dependencies run on Java 17” | It only controls source/platform APIs in that compiler's compilation | Check dependency graphs and runtime targets |
| “Use raw types to fix generic errors” | Bypasses type checking and defers errors to runtime casts | Keep explicit types, use verified adapters |

## 18. Handoff Package for a Generic API Change

For a library/framework update modifying type parameters, bounds, or method overrides, the minimum handoff record should contain:

1. **Baseline:** v1/v2 artifacts, versions, commits, checksums, and JDK/build tool.
2. **Generic API diff:** changes to type parameters, bounds, wildcards, generic methods, and return/parameter types.
3. **Erasure diff:** before and after method/constructor descriptors.
4. **Bridge inventory:** added, removed, or modified `ACC_BRIDGE`/`ACC_SYNTHETIC` methods.
5. **Hierarchy diff:** superclasses, interfaces, overrides, and important implementations.
6. **Consumer source report:** compiling old source against the new API.
7. **Consumer binary report:** running old binaries against the new API without recompiling.
8. **Behavior report:** raw types, casts, reflection, serializers, DI, plugins, and generated code.
9. **Dependency evidence:** compiled versions and runtime-loaded versions.
10. **Migration decision:** plan for ABI retention, adapters, deprecation, or major breaking release.

### Pre-Release Checklist

- [ ] Identified which type parameters changed and their corresponding erasure.
- [ ] Checked first bounds, including multiple bounds.
- [ ] Compared JVM descriptors of methods and constructors.
- [ ] Checked generic `Signature` metadata and reflection-based consumers.
- [ ] Checked bridge/synthetic methods after compilation and packaging.
- [ ] Reviewed overriding, covariant returns, and generic interface hierarchies.
- [ ] Checked name clashes and overload resolution when compiling consumers.
- [ ] Evaluated raw types, unchecked casts, and heap pollution.
- [ ] Distinguished source, binary, and behavioral compatibility.
- [ ] Compiled old consumer source against the new library.
- [ ] Ran old consumer binaries against the new library.
- [ ] Ran artifacts on the minimum supported runtime.
- [ ] Verified the dependency graph and actually loaded artifacts.
- [ ] Prepared migration notes and compatibility plans if needed.

**Type erasure** determines the types the JVM actually sees; **bridge methods** preserve proper overriding/dispatch when source generics or covariant returns produce differing descriptors. When modifying APIs using generics, the team needs to evaluate descriptors, bridges, generic metadata, and runtime behavior alike. A change solely in type arguments may preserve binary linkage while breaking source/behavior, whereas changing bounds or hierarchies can prevent old binaries from linking. Independent source, binary, and runtime checks provide the evidence-based foundation for releasing Java migrations.
