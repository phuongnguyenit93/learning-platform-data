# Changing static to instance or changing class to interface

## 1. Why do these changes affect binary compatibility?

In Java, a library is not used solely through source code. After compilation, the client application's source code becomes class files containing references to types, methods, fields, and corresponding invocation instructions. When a library is upgraded to a new version, the JVM must link those compiled references to the new definitions.

Binary compatibility describes the ability of previously compiled class files to continue linking and running with a new version of a library without needing to be recompiled. A change may look small in source code yet alter how the JVM interprets references in bytecode.

Two changes requiring special attention in Java migration are:

- Changing a method from static to instance or from instance to static.
- Changing a type declared as a class to an interface or vice versa.

These changes affect the kind of operation that old bytecode uses. If old bytecode expects a static method while the runtime provides an instance method, or bytecode expects a class while the runtime provides an interface, linking can fail with IncompatibleClassChangeError.

Therefore, compatibility should not be evaluated solely by checking whether new source code compiles. Previously compiled clients, bytecode, type structures, and runtime behavior against the new library must all be examined.

## 2. Distinguishing source compatibility, binary compatibility, and behavioral compatibility

These three concepts answer three different questions:

| Compatibility type | Question | How to verify |
|---|---|---|
| Source compatibility | Can old client source code recompile against the new API? | Recompile dependent clients or modules. |
| Binary compatibility | Can old client class files link with the new library without recompilation? | Run old binaries against the new library; use binary compatibility checking tools. |
| Behavioral compatibility | After linking, does the client still receive the expected behavior and results? | Unit tests, integration tests, contract tests, and runtime testing. |

A change may keep the method name and parameters unchanged yet break binary compatibility. Conversely, a library may preserve binary compatibility yet alter processing results, callback invocation order, or synchronization, affecting behavioral compatibility.

In migration documentation, clearly state which type of compatibility is being evaluated. "Build succeeded" usually proves only part of source/build compatibility; it does not by itself prove that previously released client binaries still run.

## 3. Changing a static method to an instance method

### 3.1. Differences in invocation

A static method belongs to the class. It is called through the class name and has no receiver object. An instance method is called on a specific object and has a receiver for the JVM to perform dispatch.

Initial API example:

~~~java
package com.example.pricing;

public class PriceCalculator {
    public static long calculate(long amount, int percent) {
        return amount * percent / 100;
    }
}
~~~

Client using the static API:

~~~java
long result = PriceCalculator.calculate(10_000, 5);
~~~

In the new library version, the development team wants to convert the calculation into the behavior of an object:

~~~java
package com.example.pricing;

public class PriceCalculator {
    public long calculate(long amount, int percent) {
        return amount * percent / 100;
    }
}
~~~

The client source code needs to change to create or receive an object:

~~~java
PriceCalculator calculator = new PriceCalculator();
long result = calculator.calculate(10_000, 5);
~~~

At the language level, this is a change in how the API is used. At the bytecode level, this change also alters the opcode used to invoke the method.

### 3.2. Bytecode uses different opcodes

When compiling a static call, the compiler generates an invokestatic instruction. When calling an instance method of a class, the compiler typically generates invokevirtual; for an instance method declared via an interface, the compiler uses invokeinterface. Certain special cases such as constructors, private methods, or super calls use invokespecial.

Illustrative example:

~~~text
Client compiled against the static API:

  invokestatic
    com/example/pricing/PriceCalculator.calculate:(JI)J

Client compiled against the instance API:

  invokevirtual
    com/example/pricing/PriceCalculator.calculate:(JI)J
~~~

The method name and parameter/return-value descriptor can remain unchanged. However, the opcode in the compiled client reflects whether the call is static or instance. The JVM checks consistency between the invocation kind and the actual resolved method.

If the old client still contains invokestatic while the new library version declares that method as instance, the JVM can throw IncompatibleClassChangeError when the execution path links that call. The reverse case also causes errors: an old client uses invokevirtual or invokeinterface while the new library provides a static method.

When the specific error appears depends on when the JVM resolves the reference and which code path is executed. Do not assume all errors appear immediately at process startup.

### 3.3. Why keeping the same name and signature is still not enough

The descriptor of a method in a class file mainly describes the name, parameter types, and return type. Staticness is not represented as part of the descriptor in a way that enables the JVM to automatically convert an old call into a new call. Invocation information resides in the bytecode instruction and the method reference kind.

Therefore, the following two versions cannot be regarded as binary equivalent just because they have the same name and parameter types:

~~~java
// Version A
public static Result execute(Request request) { ... }

// Version B
public Result execute(Request request) { ... }
~~~

Within the same class, Java also does not allow declaring two methods differing only in the static modifier while having the same signature. Therefore, you cannot keep the old static method and add an instance method with the same name/parameters in that same class to support both invocation styles.

### 3.4. Impact on inheritance and dispatch

Static methods are not overridden according to the polymorphism mechanism of instance methods. A static method with the same signature in a subclass can hide the superclass's static method. Instance methods can be overridden, and selecting an implementation depends on the actual runtime type of the receiver.

Example:

~~~java
class BaseFormatter {
    static String format(String value) {
        return "base:" + value;
    }
}

class CustomFormatter extends BaseFormatter {
    static String format(String value) {
        return "custom:" + value;
    }
}
~~~

This is static method hiding. If the API is converted to an instance method, the relationship between superclass and subclass can become overriding with object-based dispatch. That change can affect:

- Which implementation gets called when using a variable whose declared type is the superclass.
- Previously compiled subclasses.
- The @Override annotation and declarations with matching signatures.
- Method references, method handles, proxies, or framework-generated code.
- Object lifecycle and where configuration state is stored.

A static method also has no per-object monitor. If the old method was declared synchronized static, the synchronization lock is the Class monitor; when changed to synchronized instance, the lock is each object's monitor. This change can alter the degree of synchronization between calls, even if the method body is identical.

### 3.5. Impact on source code and client APIs

After converting static to instance, clients need to change how they call the method and create dependencies. Calls via the class name will no longer be valid when recompiling. Clients may need dependency injection, factories, or object lifecycle configuration.

Situations to review include:

- Direct calls via the class name.
- Calls inside static initializers or other static methods.
- Method references of the form Type::method.
- Reflection looking up methods and invoking via Method.invoke.
- Method handles created with REF_invokeStatic.
- Auto-generated source code or code compiled separately in other modules.

With reflection, finding a Method with the same name does not guarantee the old invocation still works. Clients may need to update how they obtain the receiver and perform the invocation. With method handles, the reference kind and lookup type also need to be adjusted.

## 4. Changing an instance method to a static method

The reverse direction of change also breaks old binary assumptions.

Old version example:

~~~java
public class TokenValidator {
    public boolean isValid(String token) {
        return token != null && !token.isBlank();
    }
}
~~~

Compiled client:

~~~java
TokenValidator validator = new TokenValidator();
boolean valid = validator.isValid(token);
~~~

The new version converts the method to static:

~~~java
public class TokenValidator {
    public static boolean isValid(String token) {
        return token != null && !token.isBlank();
    }
}
~~~

New clients can call:

~~~java
boolean valid = TokenValidator.isValid(token);
~~~

Old clients still carry an instance-style invocation. When running against the new library, the JVM can throw IncompatibleClassChangeError because bytecode expects an instance method whereas the resolved method is static.

In Java source, a static method can be called via an instance expression in certain cases, although that style is discouraged. However, the fact that client source code recompiles does not prove that old binaries are compatible. The compiler will emit new bytecode according to the current definition; previously released binaries still retain the old opcode.

Additionally, converting instance to static removes the receiver object. If the implementation previously relied on fields, dependencies, state, or subclass overrides, behavior must be redesigned and impacts on tests, concurrency, and lifecycle evaluated.

## 5. Changing a class to an interface

### 5.1. Classes and interfaces have different type contracts

A class is a type that can define constructors, instance state, implementations, and single-superclass inheritance. An interface defines a contract that classes can implement; interfaces do not have constructors and cannot be instantiated directly with new.

Example where the initial API is a class:

~~~java
package com.example.storage;

public class RecordStore {
    public Record find(String id) {
        // Implementation
        return null;
    }
}
~~~

Clients can instantiate the class:

~~~java
RecordStore store = new RecordStore();
Record record = store.find("A-100");
~~~

If the new library version changes the same type name to an interface:

~~~java
package com.example.storage;

public interface RecordStore {
    Record find(String id);
}
~~~

New clients can no longer use new RecordStore(). They need a concrete implementation or a factory:

~~~java
RecordStore store = new DefaultRecordStore();
Record record = store.find("A-100");
~~~

This is not just a syntax change. Previously compiled class files contain the assumption that RecordStore is a class. When the runtime provides an interface with the same binary name, operations requiring a class may no longer be valid.

### 5.2. Changing a class to an interface

Old clients may contain the following constructs:

- The new RecordStore() instruction to instantiate an object.
- A subclass declaring extends RecordStore.
- Instance method invocations via invokevirtual.
- References to constructors or members that only make sense in a class.

When RecordStore becomes an interface, the JVM can detect a type kind mismatch when resolving or executing old references. For example, an old client using new on a type that is now an interface may encounter IncompatibleClassChangeError. A class compiled with RecordStore as its superclass also cannot continue treating the new interface as a superclass.

If a method was called through the old class type, bytecode may use invokevirtual. Once the runtime type has changed to an interface, the reference and opcode no longer match the resolved type kind. The JVM can throw IncompatibleClassChangeError.

### 5.3. Changing an interface to a class

The reverse direction is also incompatible with old binaries.

Suppose the old version declares:

~~~java
public interface EventHandler {
    void handle(Event event);
}
~~~

A client implements the interface:

~~~java
public class AuditHandler implements EventHandler {
    @Override
    public void handle(Event event) {
        // Handle event
    }
}
~~~

The compiled client records EventHandler as an interface. If the new library replaces that same name with a class, the implements relationship in the old binary will no longer be valid. The JVM can throw IncompatibleClassChangeError because the client expects an interface while the runtime provides a class.

Instance method calls through the old interface typically use invokeinterface. When the type resolves to a class, the old bytecode's interface assumption is broken.

### 5.4. Structural and semantic differences

When changing a class to an interface or vice versa, review the following characteristics:

| Characteristic | Class | Interface |
|---|---|---|
| Instantiation | Can have constructors and use new if not abstract. | No constructors; cannot be instantiated directly. |
| Inheritance | A class can extend only one class directly. | An interface can extend multiple interfaces. |
| Implementation | A class can implement multiple interfaces. | Classes implement an interface using implements. |
| Instance state | Can have instance fields. | No instance fields; fields declared in an interface are public static final. |
| Method implementations | Can have abstract and concrete methods. | Has abstract, default, static, and private methods depending on supported Java version. |
| Static methods | Called via class name; can be hidden in subclasses. | Called via interface name and are not inherited like instance/default methods. |
| Constructor chain | Has superclass constructor calls. | No constructor chain. |
| Dispatch | Instance methods use class inheritance and virtual dispatch. | Instance methods can be executed by implementing classes; default methods have specific implementation selection rules. |

Changing type kind can alter factory design, dependency injection, mocks, proxies, serialization, reflection, annotation processing, and how frameworks discover implementations. Even if a new implementation provides the same methods, old clients may still fail to link because the type kind in the API changed.

### 5.5. Default methods do not make changing class/interface compatible

An interface can provide default methods to add a shared implementation for implementing classes. This mechanism is useful when designing an interface API that evolves over time, but it does not turn an existing class into an interface in a binary-compatible way.

Example:

~~~java
public interface EventHandler {
    void handle(Event event);

    default boolean supports(Event event) {
        return true;
    }
}
~~~

Adding a default method to an existing interface is generally more likely to be binary compatible than replacing a class with an interface. Nevertheless, conflicts with methods having the same signature in superclasses or other interfaces must still be examined, and behavior checked when multiple default methods compete.

Do not use default methods as an automatic fix for every binary break. Analyze the specific hierarchy and existing implementations.

## 6. Common linking errors

When a library version is replaced without recompiling clients, changes to method kinds or type kinds can manifest as runtime errors.

| Error | Common cause in this context | Investigation direction |
|---|---|---|
| IncompatibleClassChangeError | Old binary expects static but encounters instance or vice versa; client expects a class while runtime provides an interface or vice versa. | Check bytecode invocation, type kind in the runtime JAR, and loaded class version. |
| NoSuchMethodError | Method descriptor or method name referenced by the binary is no longer provided. | Compare name, parameters, return type, and actual API in the loaded JAR. |
| AbstractMethodError | Runtime dispatches to an abstract method, but the actual implementation does not provide the required implementation, often due to mismatched interface/implementation combinations. | Check versions of the interface, implementation, and hierarchy. |
| NoClassDefFoundError | Required class/interface is missing from the runtime classpath or cannot be loaded. | Check dependencies, classloaders, and actual artifacts. |

Do not conclude the root cause based solely on the exception name. Collect the full stack trace, classloader, loaded JAR location, and client bytecode.

### 6.1. Inspecting bytecode with javap

When you have old client class files, use javap to inspect invocation instructions:

~~~bash
javap -classpath client-old.jar -c -verbose com.example.Client
~~~

Look for opcodes such as:

- invokestatic: client was compiled to call a static method.
- invokevirtual: client was compiled to call a class instance method.
- invokeinterface: client was compiled to call an instance method via an interface.
- invokespecial: typically used for constructors, private methods, or super calls.

For class/interface types, inspect the constant pool, class declaration, and superclass/interfaces structure in verbose output. You can run javap -verbose on old and new library classes to compare metadata, while ensuring you check the exact artifact actually loaded by the application.

### 6.2. Ruling out errors from loading the wrong version

Some errors that look like binary incompatibility are actually caused by the runtime loading the wrong JAR:

- Multiple versions of the same artifact are on the classpath.
- A fat JAR or application server contains an old library version.
- Container image has not been updated even though the build produced a new artifact.
- A plugin, application server, or module layer classloader selects a different version.
- A cache or deployment directory still holds old class files.

Identify where the class is actually loaded from, for example via Class.getProtectionDomain().getCodeSource() in appropriate diagnostics, JVM class-loading logs, or runtime inspection tools. Then cross-check the artifact's checksum/version.

## 7. Why published APIs should not be changed directly

A public API may be used by many clients outside the library team's control: internal applications, plugins, integration modules, batch jobs, or partner libraries. These clients may have been compiled long ago and cannot all be updated simultaneously.

Changing static to instance changes the invocation contract. Changing a class to an interface changes the type contract. Even if the new library source code looks cleaner or more flexible in design, old binaries still embed the assumptions of the previous version.

If a library is distributed as a stable API, treat these changes as compatibility-breaking changes. Releasing a new major version may be an appropriate choice, but it does not automatically make old binaries run against the new API. Clients must either be upgraded or given a compatibility layer.

## 8. Safe migration strategies

### 8.1. Keeping a static facade and introducing a new instance service

If you want to move from a static utility to an instance service with dependencies or configuration, you can keep the old class as a facade during the transition period.

Example:

~~~java
public final class PriceCalculator {
    private static final PriceCalculationService DEFAULT =
            new PriceCalculationService(DefaultRateProvider.INSTANCE);

    private PriceCalculator() {
    }

    /**
     * @deprecated Use PriceCalculationService instead.
     */
    @Deprecated(since = "2.0", forRemoval = true)
    public static long calculate(long amount, int percent) {
        return DEFAULT.calculate(amount, percent);
    }
}
~~~

The new API is provided in a separate type:

~~~java
public final class PriceCalculationService {
    private final RateProvider rateProvider;

    public PriceCalculationService(RateProvider rateProvider) {
        this.rateProvider = rateProvider;
    }

    public long calculate(long amount, int percent) {
        return rateProvider.apply(amount, percent);
    }
}
~~~

Old clients still call PriceCalculator.calculate(...), so old bytecode continues to find the static method with the same descriptor. New clients can inject PriceCalculationService. Once there is a plan to remove the facade, the library can execute the breaking change in a later major release, following its published compatibility policy.

You cannot declare an additional instance method with the same name and parameters directly inside PriceCalculator while keeping the old static method. Separating the instance API into a new class/service is how both contracts can coexist.

### 8.2. Keeping the old class and introducing a new interface

If you want to abstract a class into an interface, introduce an interface with a new binary name, and then have the existing class implement that interface:

~~~java
public interface RecordStoreContract {
    Record find(String id);
}
~~~

~~~java
public class RecordStore implements RecordStoreContract {
    @Override
    public Record find(String id) {
        // Existing implementation
        return null;
    }
}
~~~

New clients can depend on RecordStoreContract, while old clients still use RecordStore as a class. This approach expands abstraction without changing the type kind of the published name.

If the desired interface name must be RecordStore, you can introduce that interface in a new package or artifact while keeping the old class in the old package as an adapter. Avoid duplicate fully qualified names within the same classloader.

### 8.3. Using an adapter or facade to maintain the old contract

An adapter can forward calls from the old API to the new implementation. When designing an adapter, preserve:

- The binary name and descriptor of the old method.
- The static/instance method kind expected by old clients.
- The class/interface type kind of the old types.
- Exception rules, null handling, call ordering, and semantics used by clients.
- Required lifecycle and thread-safety behavior.

An adapter only maintains compatibility if it actually preserves the linkage points referenced by old binaries. Renaming a method or changing the type kind at the same fully qualified name cannot be compensated merely by keeping the implementation body.

### 8.4. Releasing a major version and migration guide

If architectural goals require changing static to instance or class to interface under the same API name, classify this as a breaking change:

1. Publish a new major version or a new artifact/package according to the release policy.
2. Provide a migration guide explaining how to construct objects, inject dependencies, or implement the new interface.
3. List the changed APIs and binary contracts.
4. Provide adapters/facades if a compatibility period can be maintained.
5. Give clients transition time and define the milestone for removing the old API.
6. Verify dependent applications/plugins before rolling out uniformly.

A major version is a signal to library users that breaking changes exist; it is not a runtime compatibility mechanism.

## 9. Testing binary compatibility

To detect these kinds of errors, test previously compiled clients against the new library. Simply recompiling the entire workspace produces bytecode targeting the new API and can mask errors in old binaries.

### 9.1. Testing old clients against the new library

Minimum testing process:

1. Build the old library version, for example version 1.
2. Compile a client fixture against version 1.
3. Keep the client class files unchanged without recompiling.
4. Replace the runtime library with version 2.
5. Run the old client with version 2 on the classpath.
6. Record linkage errors or incorrect behavior.

Example runtime classpath:

~~~bash
java -cp "client-old.jar:library-v2.jar" com.example.Client
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "client-old.jar;library-v2.jar" com.example.Client
~~~

If the old client runs, that is evidence for the code paths executed in the fixture; other entry points and call paths must still be tested.

### 9.2. Testing source compatibility separately

After the binary test, compile the old client source against the new library. This helps identify which APIs no longer compile, though the results must be recorded separately from the binary test.

Example:

~~~bash
javac -cp library-v2.jar Client.java
~~~

If source compilation fails because the client still calls a static method or uses extends/implements according to the old type kind, that is evidence of source incompatibility. If source compilation succeeds while the old binary fails, the cause lies in the difference between the old bytecode and the new runtime contract.

### 9.3. Using javap to confirm opcodes and type metadata

You can inspect the client fixture compiled against the old library:

~~~bash
javap -classpath client-old.jar -c -verbose com.example.Client
~~~

For static/instance changes, identify the invocation opcode. For class/interface changes, inspect the type metadata and how the client uses that type. Also check the class files of the old and new libraries to verify the right versions are being compared.

### 9.4. Using API checking tools

In libraries with stable API commitments, tools such as japicmp or Revapi can be integrated to compare APIs between two versions. These tools help detect changes to signatures, modifiers, hierarchies, and other API changes before release.

API comparison tool results should be combined with binary fixture tests. Metadata comparison detects changes early, while running the old binary against the new library confirms the runtime impact on the tested code paths.

## 10. Change assessment matrix

| Change | Old client source upon recompilation | Old client binary against new library | Migration direction |
|---|---|---|---|
| Static method → instance method | Calls via class name are no longer valid; requires an object/receiver. | May throw IncompatibleClassChangeError because invokestatic encounters an instance method. | Keep static facade; introduce instance service in a new type. |
| Instance method → static method | Requires changing call sites and evaluating receiver/state; some object-based call syntax may still compile but semantics change. | May throw IncompatibleClassChangeError because invokevirtual/invokeinterface encounters a static method. | Keep instance adapter or move the new API to a separate name/type. |
| Class → interface | new and extends are no longer valid; requires an implementation and implements. | Binaries expecting a class may throw IncompatibleClassChangeError when the runtime provides an interface. | Keep the old class; introduce a new interface with a different name/package. |
| Interface → class | implements is no longer valid; clients must extend the class or use a new API. | Binaries expecting an interface may throw IncompatibleClassChangeError when the runtime provides a class. | Keep the old interface; introduce a new implementation/class or new API. |

This is a general assessment. Actual results also depend on method descriptors, hierarchy, classloaders, executed references, and the artifact version being loaded.

## 11. Assessment process before approving a change

When reviewing a proposal to change static to instance or class to interface, proceed in order:

1. Identify the affected public APIs and the type's fully qualified name.
2. Locate all directly and indirectly dependent clients/modules.
3. Identify clients that can be recompiled and previously released binaries that must continue to be supported.
4. Compare old/new class files and invocation opcodes or type metadata.
5. Run the old binary fixture against the new library.
6. Compile client source against the new library to check source compatibility separately.
7. Test behavior, especially dispatch, lifecycle, synchronization, reflection, and framework integration.
8. Choose an adapter/facade strategy, supplementary API, or major version.
9. Document which clients must upgrade, the transition deadline, and conditions for removing the old API.

In multi-module systems, check both modules built in the same repository and modules distributed separately. One module may be recompiled in CI, while external plugins or integrated applications still hold old binaries. Do not treat a full-repository build result as representative of every consumer.

## 12. Conclusion

Changing static to instance changes how bytecode invokes a method; changing a class to an interface changes the type kind that old bytecode expects. Both can break binary compatibility and lead to IncompatibleClassChangeError when old clients link against the new library.

For a safe migration, clearly identify published contracts, keep adapters/facades when compatibility is required, or announce breaking changes with a transition guide. Testing old client binaries against the new library, inspecting bytecode with javap, and comparing APIs with dedicated tools help detect risks before release. Source compatibility, binary compatibility, and behavioral compatibility must be evaluated separately to decide whether the migration can be deployed safely.
