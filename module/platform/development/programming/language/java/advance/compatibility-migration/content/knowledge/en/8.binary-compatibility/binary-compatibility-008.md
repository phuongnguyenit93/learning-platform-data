# Adding Abstract or Default Methods and When Errors Occur

When a Java library modifies an interface or abstract class, two versions can **compile independently without error** yet fail to run together. A common situation is when the new version adds an `abstract` method that old implementations have not implemented yet, or adds a `default` method to an interface causing multiple implementations to inherit two conflicting default methods. Notably, the error does not necessarily appear when the JVM starts up or when classes are loaded; it may appear only when a specific method call is executed.

To properly evaluate binary compatibility, it is necessary to distinguish **recompiling source**, **running previously compiled class files**, **method lookup and resolution**, and **the time the JVM actually invokes the method**. The same API change can be safe for old consumers that do not use the new feature, yet cause errors for new consumers when they invoke that feature on an old implementation.

## 1. Distinguishing Abstract Methods, Default Methods, and Implementations

In Java, an interface can declare abstract methods or default methods:

~~~java
public interface NotificationSender {
    void send(String message);  // abstract method

    default boolean supportsRetry() {
        return false;
    }
}
~~~

- **Abstract method:** publishes only the contract, providing no method body. A concrete class implementing the interface must normally have a matching implementation, directly or via a parent class.
- **Default method:** has a method body directly in the interface. A class implementing the interface can inherit this implementation if there is no matching method in the class hierarchy or conflict between interfaces.
- **Concrete class method:** a method with an implementation in a class or superclass. When resolving the same signature, matching instance methods from the class hierarchy take precedence over default methods from interfaces.

An abstract class can also contain abstract methods:

~~~java
public abstract class ReportGenerator {
    public abstract byte[] generate();
}
~~~

Unlike interfaces, Java classes do not use the `default` keyword to declare default methods. A normal concrete method in a superclass provides an inherited implementation for subclasses; interface default methods are a separate mechanism added in Java 8.

In terms of bytecode, an abstract method has the `ACC_ABSTRACT` flag and no `Code` body. An interface default method is an interface instance method that has a `Code` body and does not carry `ACC_ABSTRACT`; `default` is a language concept, not an independent `ACC_DEFAULT` flag in the class file.

## 2. Why Can Adding an Abstract Method Cause Late Errors?

Suppose a library releases version 1 of an interface:

~~~java
// api-v1/demo/Job.java
package demo;

public interface Job {
}
~~~

Another application compiles an implementation against this version:

~~~java
// impl-v1/demo/LegacyJob.java
package demo;

public final class LegacyJob implements Job {
}
~~~

At that point, `LegacyJob` is a valid concrete class because the `Job` interface requires no methods yet. Its class file records that it implements `demo.Job`, but has no `run()` method.

Later, the vendor releases version 2 of the interface:

~~~java
// api-v2/demo/Job.java
package demo;

public interface Job {
    void run();
}
~~~

If you take the **source** of `LegacyJob` and recompile it with `Job` v2, the compiler reports an error because the concrete class does not implement `run()`. This is a **source compatibility** issue.

However, **the `LegacyJob` class file compiled against v1 may still be loaded and instantiated** when runtime uses `Job` v2. The JVM does not require all old concrete class files to re-pass all source-level checks of the new compiler when classes are loaded. This change is generally considered binary-compatible for old binaries insofar as they continue using pre-existing calls.

A consumer compiled against API v2 might be written as:

~~~java
// client-v2/demo/NewCaller.java
package demo;

public final class NewCaller {
    public static void main(String[] args) {
        Job job = new LegacyJob(); // LegacyJob class file from v1
        job.run();                  // new method in Job v2
    }
}
~~~

When running with `Job` v2 and the `LegacyJob` v1 binary, the `job.run()` call cannot find a matching concrete implementation on the receiver object. The JVM may throw:

~~~text
java.lang.AbstractMethodError
~~~

The key point to remember: **the error occurs at the call to the new method on the old implementation**. The fact that the class loaded, the constructor ran, or another old method works normally does not prove `run()` can be called.

### 2.1. Why Is This Not Necessarily NoSuchMethodError?

In the situation above, interface v2 **does** declare `Job.run()`. The method reference in the caller's bytecode can resolve to that declaration. The problem appears when the JVM needs to find a concrete implementation to execute the call on the `LegacyJob` object and fails to find one.

Therefore, the typical case is `AbstractMethodError`. Conversely, if an old call references a method that was deleted or had its descriptor changed and lookup cannot find a matching method, `NoSuchMethodError` may occur. The two errors indicate two different forms of method linkage/selection failure.

### 2.2. When Does No Error Occur?

Adding an abstract method to an interface does not mean every old implementation immediately fails:

- Old consumers with no calls to the new method can continue running normally.
- If an old implementation happens to already have a public instance method with a matching signature and return type, that method can satisfy the new contract.
- If the new implementation is recompiled and implements the method, the call has a valid implementation.
- An intermediate abstract class can continue leaving the method unimplemented for concrete subclasses to implement by design.

Therefore, you must specify the **version pair** and **actual call path**, rather than broadly concluding that “adding an abstract method always breaks binary compatibility” or “adding a method is always safe”.

## 3. Distinguishing Compile Time, Class Loading, and Method Invocation

Using the same `Job` example above, the milestones can be illustrated as follows:

~~~text
Time A: Compile implementation with Job v1
  Job v1 {} + LegacyJob implements Job
                     |
                     v
            Valid LegacyJob.class

Time B: Provider releases Job v2
  Job v2 { abstract void run(); }
                     |
                     v
         LegacyJob v1 binary still exists

Time C: Run with Job v2 + LegacyJob.class v1
  Load Job v2, load LegacyJob, instantiate object
                     |
                     v
                May succeed
                     |
                     v
           invokeinterface Job.run()
                     |
                     v
          No concrete implementation
                     |
                     v
               AbstractMethodError
~~~

The JVM may perform some linkage and reference resolution operations eagerly or lazily. Therefore, **do not treat class loading time as an absolute rule for all errors**. In this example, the important thing at the observational level is that the program only needs the new method when executing the call, and the missing-implementation error can appear at that call.

For large systems, a call path may only be executed upon a special request, a rare message, a scheduled job, or a new feature enabled by a feature flag. An application running for days without errors can still contain an incompatible binary combination.

## 4. Practical Example Reproducing the Error with Two API Versions

You can create four source directories as in the earlier example and compile in order: API v1, implementation v1, API v2, caller v2. The commands below illustrate this on Windows PowerShell, where classpath uses `;`:

~~~powershell
javac -d build\api-v1 api-v1\demo\Job.java
javac -cp build\api-v1 -d build\impl-v1 impl-v1\demo\LegacyJob.java
javac -d build\api-v2 api-v2\demo\Job.java

javac -cp 'build\api-v2;build\impl-v1' -d build\client-v2 client-v2\demo\NewCaller.java

java -cp 'build\api-v2;build\impl-v1;build\client-v2' demo.NewCaller
~~~

On Linux/macOS, classpath usually uses `:`. The paths in the example assume the corresponding source and output directories have already been created. The goal is to **keep the implementation class file compiled against API v1 unchanged**, then run it with API v2. If you recompile the implementation against v2, the error will be caught at compile time and will no longer reproduce the old binary situation.

To inspect the caller's references and method declarations, you can use:

~~~powershell
javap -classpath build\client-v2 -c -v demo.NewCaller
javap -classpath build\api-v2 -p -s demo.Job
javap -classpath build\impl-v1 -p -s demo.LegacyJob
~~~

In the caller bytecode, look for the `invokeinterface` instruction and the symbolic reference to `demo.Job.run:()V`. In interface v2, `run()` exists without an implementation; in `LegacyJob.class` v1, the corresponding method is not declared. This is direct evidence for the `AbstractMethodError` scenario.

## 5. Adding a Default Method: Cases Where Extension Works

One way to extend an interface without forcing old implementations to add code is to provide default behavior:

~~~java
// api-v1/demo/Task.java
package demo;

public interface Task {
    void execute();
}
~~~

Old implementation:

~~~java
package demo;

public final class OldTask implements Task {
    @Override
    public void execute() {
        System.out.println("executed");
    }
}
~~~

API v2 adds a method with an implementation body:

~~~java
// api-v2/demo/Task.java
package demo;

public interface Task {
    void execute();

    default boolean isCancelable() {
        return false;
    }
}
~~~

When a new caller invokes `isCancelable()` on `OldTask.class` compiled against API v1, the JVM can select the default implementation from `Task` v2. `OldTask` does not necessarily have to be recompiled to inherit this method.

The default behavior `false` here is just an example: it carries the meaning “old implementations do not support cancellation”. An added default method should have safe behavior that conforms to the contract. A default method that silently skips a payment operation, permission check, or data update can cause the system to produce wrong results even though no linkage error occurs at all.

### 5.1. When the Class Already Has a Method with a Matching Signature

If `OldTask` or its superclass already has a compatible public instance method `isCancelable()`, the class's implementation takes precedence over the default method in the interface. This allows class-specific behavior to remain in effect, but can also turn a method not originally designed to implement the new contract into the implementation of that contract.

For example, an old class has a `reset()` method used to reset the UI; the new interface adds `default reset()` meaning to reset a transaction. The JVM may use the class's method because the name and descriptor match, yet the semantics are not the same. This is a **behavioral compatibility risk**, which cannot be detected merely by the program running without errors.

### 5.2. When a Subinterface Has a More Specific Default Method

Suppose:

~~~java
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

final class Example implements Child {
}
~~~

`Example` inherits `Child.label()` because it is the more specific default declaration in the interface inheritance relationship. Do not assume that every interface with a default of the same signature causes a conflict: **inheritance relationships and method selection rules** determine which method applies.

## 6. Adding a Default Method Can Also Create Runtime Conflicts

A dangerous case is when an old implementation already implements two independent interfaces. When one interface is upgraded and adds a default method matching the signature of a default method in the other interface, the old binary can become ambiguous when calling the method.

Version 1 of the two interfaces:

~~~java
// Interface A v1
public interface A {
    default String label() {
        return "A";
    }
}
~~~

~~~java
// Interface B v1
public interface B {
}
~~~

The implementation compiled against A v1 and B v1:

~~~java
public final class Legacy implements A, B {
    // Does not declare label(); inherits A.label().
}
~~~

An old caller can invoke:

~~~java
Legacy legacy = new Legacy();
System.out.println(legacy.label());
~~~

Later, B v2 adds a default method with the same name and descriptor:

~~~java
// Interface B v2
public interface B {
    default String label() {
        return "B";
    }
}
~~~

If **`Legacy.class` and the old caller are kept unchanged**, replacing only B v1 with B v2, class `Legacy` may still load. However, when the `label()` call needs to select an implementation, the JVM has two default methods of equal priority from two independent interfaces A and B. Such a conflict case may throw:

~~~text
java.lang.IncompatibleClassChangeError: Conflicting default methods
~~~

If you take the `Legacy` **source** and recompile it with A v1/B v2, `javac` detects the default method conflict and requires the class to resolve it. Thus, the recompilation error and the error running the old binary occur at **two different times**.

### 6.1. Resolving Conflicts with an Explicit Implementation

When you have permission to modify the class, you can override the method and specify the intended behavior:

~~~java
public final class Legacy implements A, B {
    @Override
    public String label() {
        return A.super.label();
    }
}
~~~

At this point the class has its own implementation, so the JVM no longer needs to choose between two independent defaults. `A.super.label()` is the syntax used to directly invoke the desired default method from an interface when permitted by inheritance rules.

If the old class was released by a third party and cannot be recompiled immediately, the provider must consider keeping the old API, redesigning the new method, or providing another compatible version. Simply bumping the dependency version and expecting the conflict to vanish on its own is not enough.

## 7. Adding an Abstract Method to an Abstract Class

A similar situation occurs with an abstract superclass extended externally.

Version 1:

~~~java
public abstract class Workflow {
    public void start() {
        System.out.println("started");
    }
}
~~~

Subclass compiled with v1:

~~~java
public final class LegacyWorkflow extends Workflow {
}
~~~

Version 2 adds an abstract method to a **class that was already abstract**:

~~~java
public abstract class Workflow {
    public void start() {
        System.out.println("started");
    }

    public abstract void stop();
}
~~~

When recompiling `LegacyWorkflow` source with v2, the compiler requires the concrete class to implement `stop()`. However, the old binary of `LegacyWorkflow` may still load and instantiate objects with the new superclass; it will not necessarily fail at instantiation time. When a new caller actually calls `stop()` without a concrete implementation, `AbstractMethodError` may occur.

Distinguish this case from **turning a previously concrete class into an abstract class**. If an old binary contains a `new Workflow` instruction and the runtime class is now abstract, creating an instance can cause `InstantiationError`. That is a different change regarding the instantiability of the class, not merely adding an abstract method to an existing abstract superclass.

## 8. When an Interface Is Used as a Functional Interface

A functional interface has exactly one abstract method according to Java rules, allowing lambdas or method references to be used as implementations. Adding an abstract method can cause the interface to no longer be a functional interface when compiling new source code.

Initial example:

~~~java
@FunctionalInterface
public interface Processor {
    void process(String value);
}

Processor p = value -> System.out.println(value);
~~~

If the new version adds:

~~~java
void cancel();
~~~

The compiler may report that the interface is no longer a functional interface; source code using lambdas will fail to recompile. Removing `@FunctionalInterface` does not solve the issue either: with two independent abstract methods, a lambda can no longer satisfy the contract.

A lambda compiled with an old version uses a runtime mechanism corresponding to the compiler version that produced it. Do not assume that loading and all calls on this binary will fail immediately; the notable risk is calling the new method that the old implementation does not provide. Test with actual artifacts if the application mixes library generations.

If the new method can provide default behavior, adding `default void cancel() { ... }` can keep the count of abstract methods unchanged. Even so, the default implementation must be valid in business terms. Do not create a no-op method just to keep the compiler silent when consumers need to know whether cancellation was performed.

## 9. Comparison Table of Impact and Error Timing

| Change in API | Recompile old implementation | Run old implementation binary | Typical error and timing |
|---|---|---|---|
| Add abstract method to interface | Concrete classes usually must implement new method | May load/run old methods | `AbstractMethodError` when calling new method without implementation |
| Add non-conflicting default method | Usually no new implementation needed | Can inherit default method | No linkage error if lookup/dispatch is valid; still need to verify behavior |
| Add default colliding with independent default | May report conflict error on recompile | Old binary may load | `IncompatibleClassChangeError` when a call must choose between conflicting defaults |
| Add abstract method to abstract superclass | Concrete subclasses must implement on recompile | Old subclass binary may load | `AbstractMethodError` when a call needs the unimplemented method |
| Change concrete class to abstract | Instantiation source no longer compiles | Old binary may contain `new` instruction | `InstantiationError` when attempting to instantiate the now-abstract class |
| Remove method or change descriptor | Old caller source may not compile | Old caller binary carries non-matching reference | `NoSuchMethodError` when the reference cannot be resolved |

These are **typical** situations, not assertions that every change always produces one exact error type. Results also depend on which method is called, the class hierarchy, inherited implementations, signatures, access privileges, class loaders, and the actual version combination.

## 10. Why Can Errors Appear Only in Production?

During development, teams usually recompile all modules together with a single dependency version. At that time, the compiler catches classes missing abstract methods or conflicts between two defaults. Production, however, can differ:

- **Old plugins:** the core system upgrades the interface while partner plugins retain old binaries.
- **Rolling deployment:** some instances use the new API while some components are still old implementations.
- **Mobile apps or slowly updated clients:** consumers/adapters are released independently and are not recompiled alongside the backend.
- **Classpath conflict:** runtime selects a different JAR than the one used at compile time.
- **Containers and app servers:** classes are loaded from a different loader or deployment than expected.
- **Rare call paths:** the new method is only used for a specific task or feature flag.
- **Generated code:** a framework/plugin generated the implementation in an earlier build, while runtime later upgraded the API.

A test that only checks application startup can miss all of the cases above. It is necessary to run actual calls traversing the changed interface or abstract superclass, including implementations from versions that are still supported.

## 11. How to Investigate AbstractMethodError and Default-Method Conflicts

When encountering `AbstractMethodError` or `IncompatibleClassChangeError` after a migration, you can investigate in sequence:

1. **Record the stack trace and called method.** Identify the owner type, name, and descriptor appearing in the message or relevant frames.
2. **Identify the caller binary.** Which API version was the call compiled against? Is there compiler output or an artifact checksum to trace it?
3. **Identify the runtime API.** Which interface/abstract class JAR is the JVM actually loading?
4. **Identify the actual implementation.** Which class does the object belong to, which loader defined it, and which version was that class built from?
5. **Read the hierarchy.** Does the class/superclass have a matching concrete method? Do the interfaces have any default methods that could conflict?
6. **Inspect bytecode.** Use `javap -v -c -s` to read symbolic references and method invocation instructions.
7. **Reproduce the version combination.** Keep the old binary unchanged and replace only the target dependency to verify the result.
8. **Fix according to the contract.** Add the implementation, adjust the default method, keep the old API, or upgrade consumers in sync as planned.

Supporting commands:

~~~bash
# Inspect signature and descriptor of interface/abstract class
javap -classpath api-v2.jar -p -s com.example.api.Task

# Inspect method and bytecode of caller
javap -classpath client.jar -v -c -s com.example.client.TaskCaller

# Inspect implementation compiled from old version
javap -classpath legacy-implementation.jar -p -s com.example.impl.OldTask

# List classes in artifact
jar tf legacy-implementation.jar
~~~

The commands above only illustrate how to inspect; replace package, class, and artifact names with your actual system. For modular JARs, also inspect `module-info`, exports, and module readability. With custom class loaders, do not deduce which JAR is loaded from the classpath based on filenames in build scripts.

For JDKs with unified logging, class loading logs can be used when appropriate:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

This log helps trace class loading sources but can generate a large volume of data. Only enable it in an appropriate environment and timeframe, then search for the relevant class/interface in the log.

## 12. Designing APIs to Limit Risks on Release

### 12.1. If New Behavior Must Be Added

When new behavior is genuinely mandatory for every implementation, the provider may need to release a source-incompatible change or require implementations to upgrade. Announce support conditions in advance, list impacted consumer/plugin groups, and run tests with remaining old implementations.

Another option is to create an extension interface:

~~~java
public interface Job {
    void run();
}

public interface CancelableJob extends Job {
    void cancel();
}
~~~

Consumers can check capability instead of calling `cancel()` on every `Job`:

~~~java
public void requestCancel(Job job) {
    if (job instanceof CancelableJob) {
        ((CancelableJob) job).cancel();
    } else {
        throw new UnsupportedOperationException("Job không hỗ trợ hủy");
    }
}
~~~

This approach makes clear that not every old implementation supports cancellation. There is no need to add an abstract method directly to `Job`, helping preserve the contract for existing implementors.

### 12.2. If Adding a Default Method

Only use a default method when you can provide an implementation with consistent semantics for all old implementors. Check:

- Does the new method match the name/descriptor of a method in another interface that consumers implement?
- Does any class or superclass provide a method with the same signature and different semantics?
- Is the default implementation valid for all old implementations?
- Does it change behavior, side effects, security, or transactions?
- Is it suitable when callers use reflection, proxies, AOP, or generated code?
- Does it affect method selection order when frameworks introspect interfaces?

If default behavior cannot satisfy safety requirements, use a new interface, capability discovery, or phased migration. A default method that only throws `UnsupportedOperationException` may clarify the contract regarding unsupported capabilities, but still requires consumers to handle it proactively; it is not a promise that every new call will succeed.

### 12.3. Versioning and Deprecation Policy

Adding an abstract method can be classified as binary-compatible in a certain sense of the specification, yet cause source incompatibility for old implementations and `AbstractMethodError` when new callers exist. Therefore, version numbering and release notes need to account for library users and supported deployment combinations.

Marking an old API `@Deprecated` is a step to communicate intent; it does not automatically help old implementations support new abstract methods. If an incompatible change is intentional, publish migration milestones, required consumer upgrades, rollback conditions, and the period during which both versions coexist.

## 13. Testing a Version Matrix Instead of Only Clean Builds

With a new API and old implementations, test at least the combinations that can actually occur:

| Runtime API | Implementation binary | Caller | Goal |
|---|---|---|---|
| V1 | V1 | Caller V1 | Confirm baseline before change |
| V2 | V1 | Caller V1 | See whether old behavior continues working |
| V2 | V1 | Caller V2 calling new method | Detect `AbstractMethodError` or default conflict |
| V2 | V2 | Caller V2 | Confirm new implementation works properly |

If rollbacks can occur where API and implementation are not deployed simultaneously, add the V1/V2 combination if the actual system can produce it. Not every combination is supported, but support boundaries must be clearly documented in release contracts and deployment guides.

Appropriate test layers:

1. **Source compatibility:** recompile old implementation source against the new API to detect missing abstract methods or default conflicts.
2. **Binary compatibility:** run actual released implementation/caller class files without recompiling against the new API.
3. **Dispatch tests:** call the new methods directly, especially when the receiver is an old implementation or implements multiple interfaces.
4. **Behavioral tests:** confirm default implementations, method selection order, and business results match expectations.
5. **Integration tests:** invoke via dependency injection, proxies, reflection, plugin loaders, or frameworks that production actually uses.
6. **Rollback tests:** confirm the old version can operate with data and artifacts remaining after a new deployment if that is a requirement.

API comparison tools such as japicmp or Revapi help detect new members, modifier changes, and signature differences, but are not sufficient to determine full method selection behavior in real applications. Therefore, API diff results should be combined with tests using **old binaries** and new call paths.

## 14. Misleading Assumptions

**“Adding an abstract method to an interface is binary-incompatible so all old classes will fail on load.”** Inaccurate. Old binaries can continue loading and using old methods; missing implementations typically surface when the new method is called.

**“Adding an abstract method is completely safe because the specification considers it binary-compatible.”** Also inaccurate. It can break source compatibility and cause `AbstractMethodError` with new callers + old implementations.

**“Having a default method is always safe.”** Incorrect. Two defaults from independent interfaces can conflict; a class method may be selected with different semantics; the default implementation may be wrong for business logic.

**“If the application starts without errors, the interface is compatible.”** Insufficient. Some errors only appear when calling a specific method, loading a plugin, or when a feature flag activates a rare path.

**“Just running tests after recompiling the entire project is enough.”** Insufficient for systems releasing multiple independent artifacts. Recompiling can catch source errors, but does not reproduce linkage failures of old class files in production.

**“AbstractMethodError and NoSuchMethodError have the same root cause.”** Incorrect. One case is usually that the method is declared without a concrete implementation to call; the other is usually that lookup/resolution can no longer find a member matching the expected name and descriptor.

## 15. Checklist Before Adding a Method to an API

- [ ] Identified which interfaces/abstract classes are published to consumers.
- [ ] Listed current implementations, including plugins and binaries released by third parties.
- [ ] Distinguished new abstract methods from default methods with implementations.
- [ ] Determined source compatibility when recompiling old implementations.
- [ ] Determined scenarios running old binaries with the new runtime API.
- [ ] Searched for methods with the same name/descriptor in class hierarchies and other interfaces.
- [ ] Evaluated conflicts between two independent default methods.
- [ ] Reviewed functional interfaces and lambdas/method references in use.
- [ ] Checked when the new method is actually invoked, including rare execution paths.
- [ ] Ran tests using artifacts/callers/implementations of the versions requiring support.
- [ ] Defined default behavior and error reporting when the new feature is not yet supported.
- [ ] Documented versioning policy, migration instructions, and rollback plan.

## 16. Conclusion

Adding an abstract method and adding a default method are two ways to extend an API with different consequences. **A new abstract method** forces recompiled implementations to satisfy the contract, while old implementation binaries may continue loading and only trigger `AbstractMethodError` when new callers invoke the unimplemented method. **A new default method** can supply behavior to old binaries, yet risks creating conflicts across multiple interfaces leading to `IncompatibleClassChangeError` when a call needs to select an implementation.

In Java migrations, compatibility conclusions must explicitly state the API version, implementation binary version, caller version, and executed methods. Combine source checks, class file analysis, old binary testing, and testing of real call paths to catch errors right where they can occur.
