# Adding final, sealed, or Changing Inheritability

In the **Binary Compatibility** group of the **Java Advance Compatibility Migration** topic, changing inheritability is one of the API change types most easily misjudged. A class may keep its exact name, constructors, and public methods, yet merely adding **final** or **sealed** can prevent previously compiled plugins or subclasses from loading when the library JAR is swapped.

The problem typically surfaces when components have independent release lifecycles: a framework providing base classes, an organization shipping an SDK, partners writing subclasses, or a module generating proxies with runtime tools. When upgrading the library, a team can recompile the library successfully and pass internal unit tests, yet the old consumer's bytecode still contains **extends**, **implements**, or **override** relationships that the new version forbids.

This lesson analyzes the exact impact of **final**, **sealed**, **non-sealed**, **permits** sets, related class/interface changes, and migration approaches to keep old consumers functioning.

## 1. Binary Compatibility and Inheritance Contracts

Binary compatibility answers the question: can a program compiled against an old API version continue to link and run with a new API version **without recompiling that program**?

For a library supporting inheritance, the contract does not consist solely of methods to call. It also includes:

- Whether a class is permitted to be a superclass.
- Whether an interface allows new classes or subinterfaces to implement/extend it.
- Whether instance methods can be overridden.
- Which constructors subclasses can call via **super(...)**.
- Which members subclasses can inherit and with what access permissions.
- Whether the type is restricted by **sealed** and **permits**.
- Whether existing consumers are built and deployed independently of the library.

For example, API version 1 provides:

~~~java
package example.api;

public class BaseHandler {
    public String handle(String input) {
        return input;
    }
}
~~~

A precompiled external plugin:

~~~java
package example.plugin;

import example.api.BaseHandler;

public class CustomHandler extends BaseHandler {
    @Override
    public String handle(String input) {
        return "custom:" + input;
    }
}
~~~

The bytecode of **CustomHandler** records its superclass as **example.api.BaseHandler** and has a corresponding overridden method. If version 2 turns **BaseHandler** into **final**, preserving the **handle(String)** signature cannot rescue the forbidden inheritance relationship.

### 1.1. Three aspects to verify separately

| Aspect | Question | How to verify |
|---|---|---|
| Source compatibility | Does the old subclass source compile against the new library? | Compile consumer source on the new API |
| Binary compatibility | Does the old subclass class file load and run with the new library? | Keep consumer bytecode unchanged and swap only the library JAR |
| Behavioral compatibility | Do overrides, dynamic dispatch, and extension contracts still work properly? | Test in practice with representative subclasses and plugins |

A change may prevent source from compiling while old bytecode still links; another case may cause runtime errors from changing a single modifier. Therefore, do not use full source rebuild results to conclude binary compatibility.

## 2. Modifiers That Govern Inheritability

Java has several mechanisms controlling inheritance relationships. They carry different meanings and create different constraints for consumers.

| Declaration | Ability to inherit or implement | Upgrade implication |
|---|---|---|
| Regular class, non-final/non-sealed | Can be subclassed if constructors and access allow | Extensibility is part of actual API behavior |
| **final class** | Cannot have subclasses | Adding final can break old subclasses |
| **sealed class** | Only allows direct subclasses listed in the permitted set | Adding sealed can break unpermitted old subclasses |
| **non-sealed class** | Re-opens ability to have subclasses when this class is a direct child of a sealed type | Can create an extension point beneath a sealed hierarchy |
| **sealed interface** | Only allows direct classes or subinterfaces in the permitted set | Adding sealed can break old implementations or subinterfaces |
| **non-sealed interface** | Re-opens ability to be implemented/extended beneath a sealed interface | Useful for keeping one extension branch open |
| **final instance method** | Cannot be overridden | Adding final can break subclass class files that override it |
| **final static method** | No dynamic overriding; static methods use method hiding | Binary impact differs from final instance methods |

**final**, **sealed**, and **non-sealed** are mechanisms at different levels. **final** cannot be used on an interface. **non-sealed** is also not a modifier that can be added arbitrarily to any class/interface; it is only valid when the type has an appropriate direct sealed supertype.

**Sealed classes and interfaces** became a standard feature starting in Java 17. If a system still must run on an older JDK that does not support this release's class files, adding sealed may bring runtime requirement changes in addition to consumer compatibility concerns.

## 3. Adding final to a Class That Already Has Subclasses

### 3.1. Change seen from source

Version 1:

~~~java
package example.api;

public class Engine {
    public String run() {
        return "running";
    }
}
~~~

Already-released plugin:

~~~java
package example.plugin;

import example.api.Engine;

public class FastEngine extends Engine {
    @Override
    public String run() {
        return "fast";
    }
}
~~~

Version 2 only edits the modifier:

~~~java
package example.api;

public final class Engine {
    public String run() {
        return "running";
    }
}
~~~

If **FastEngine** is recompiled against version 2, **javac** reports an error because a final class cannot be extended. Yet the more important migration scenario is when **FastEngine.class** was previously compiled and is not rebuilt.

According to the Java Language Specification, when the JVM loads the old subclass class file against the new superclass that became final, the JVM throws **IncompatibleClassChangeError** because the inheritance relationship is no longer valid. The error may only appear when the plugin is loaded, not necessarily when the application starts up.

### 3.2. Why is keeping methods intact not enough?

In a class file, the superclass relationship is stored separately from method references. The runtime must validate the inheritance relationship when loading/linking classes. Even though **Engine.run()** retains its exact descriptor, **FastEngine** still attempts to extend a class that became final.

~~~text
Initial compilation:
    FastEngine.class  ----extends----> Engine v1 (open)
                                           |
                                           v
                                         Valid

Swap JAR, keep FastEngine.class unchanged:
    FastEngine.class  ----extends----> Engine v2 (final)
                                           |
                                           v
                             IncompatibleClassChangeError
~~~

Practical conclusion: **Adding final to a public/protected base class inherited by others is a binary-incompatible change**, even without deleting any methods.

### 3.3. Lower-risk cases

If a class is strictly internal, has no subclasses outside controlled scope, and all consumers can be rebuilt or thoroughly verified, adding final can be a reasonable design choice.

However, merely looking at source in the repository to say "there are no subclasses" can miss:

- Independently released plugins.
- Partner libraries or modules not residing in the same repository.
- Frameworks generating subclasses/proxies via bytecode at runtime.
- Consumers using reflection or class names from configuration.
- Binaries built from older versions no longer present in the repository.

Both dependencies and runtime artifacts must be inventoried, not just searching for the **extends** keyword in current source.

## 4. Adding final to an Instance Method

Adding **final** to a class and adding **final** to a method are two distinct changes.

### 4.1. Method previously allowed to be overridden

Version 1:

~~~java
package example.api;

public class Formatter {
    public String format(String value) {
        return value;
    }
}
~~~

Old consumer:

~~~java
package example.plugin;

import example.api.Formatter;

public class HtmlFormatter extends Formatter {
    @Override
    public String format(String value) {
        return "<p>" + value + "</p>";
    }
}
~~~

Version 2:

~~~java
package example.api;

public class Formatter {
    public final String format(String value) {
        return value;
    }
}
~~~

The source of **HtmlFormatter** fails to recompile against version 2. More importantly, when the JVM loads an old class file containing a newly forbidden method override, it can throw **IncompatibleClassChangeError**. This is the scenario described in JLS §13.4.17.

The library team might think adding final aids optimization or prevents subclasses from altering behavior. Yet once the API is published and consumers are overriding it, this modifier alters the extension contract.

### 4.2. Final on static methods

A static method does not participate in polymorphic overriding like an instance method. Java uses method hiding for static methods. Therefore, under JLS binary compatibility rules, adding **final** to a static method does not produce the same kind of binary error as adding final to an overridden instance method.

However, subclass source containing a static method with the same name/signature may fail to compile in certain cases. This is an example of why **source compatibility** must be tested separately from binary compatibility.

### 4.3. Do not confuse with final fields

**final fields** mainly govern assignability, not directly inheritance relationships. For a **public static final** primitive/String initialized with a constant expression, the compiler can even inline the value into consumer bytecode. Risks of this field type belong to data/constant contracts, differing from errors when classes or methods become final.

This lesson focuses on **final classes** and **final methods** because they directly affect inheritance and overriding.

## 5. Sealed Classes: Restricting the Set of Direct Subclasses

A **sealed class** specifies the exact types permitted to extend it directly.

Example with Java 17 and later:

~~~java
package example.model;

public sealed abstract class Payment
        permits CardPayment, CashPayment {
}

public final class CardPayment extends Payment {
}

public non-sealed class CashPayment extends Payment {
}
~~~

In the example:

- **Payment** only allows **CardPayment** and **CashPayment** as direct subclasses.
- **CardPayment** is marked **final**, because this branch is not extensible.
- **CashPayment** is marked **non-sealed**, re-opening the ability to have subclasses beneath the CashPayment branch.

A permitted direct subclass of a sealed class must choose an appropriate inheritance state: **final**, **sealed**, or **non-sealed**. If choosing **sealed**, it must in turn specify its own permitted direct subclasses.

### 5.1. Sealed interfaces

Interfaces can also be sealed:

~~~java
package example.event;

public sealed interface Event
        permits CreatedEvent, CancelledEvent {
}

public record CreatedEvent(String id) implements Event {
}

public final class CancelledEvent implements Event {
}
~~~

**CreatedEvent** is a record; records are final under Java semantics and can serve as permitted implementations. The **Event** interface forbids other implementations from arbitrarily joining as direct children.

### 5.2. Package and module boundaries

Java requires permitted direct subclasses/subinterfaces to reside within permitted boundaries:

- With **named modules**, permitted direct subclasses must belong to the **same module** as the sealed parent.
- With **unnamed modules**, permitted direct subclasses must belong to the **same package** as the sealed parent.

This rule matters for public libraries: if previously consumers outside the package/module could inherit a class, adding sealed does not merely require updating the **permits** list; it can make the consumer's location invalid under language rules.

Do not suggest "just add all external plugin names to permits" when plugins reside in different packages in an unnamed module or in different named modules. An appropriate extension point must be redesigned.

### 5.3. Permits controls only direct subclasses

~~~text
                 sealed Payment
                 /            \
                /              \
       final CardPayment     non-sealed CashPayment
                                    |
                                    v
                              LegacyCashPayment
                                    |
                                    v
                               MoreCashPayment
~~~

**Payment** only needs to permit **CardPayment** and **CashPayment** directly. Because **CashPayment** is non-sealed, indirect subclasses beneath it can continue extending under ordinary Java rules.

This is one option to keep an extension area open: lock down the top-level set of branches while allowing consumers to customize via an intentionally designed **non-sealed** branch.

## 6. Adding sealed to an Already-Released Class or Interface

### 6.1. Adding sealed to a previously open class

Version 1:

~~~java
package example.api;

public abstract class Job {
    public abstract void execute();
}
~~~

Precompiled external plugin:

~~~java
package example.plugin;

import example.api.Job;

public class CleanupJob extends Job {
    @Override
    public void execute() {
        System.out.println("cleanup");
    }
}
~~~

Version 2 may turn **Job** into sealed and restrict direct subclasses:

~~~java
package example.api;

public sealed abstract class Job permits BuiltInJob {
    public abstract void execute();
}

final class BuiltInJob extends Job {
    @Override
    public void execute() {
        System.out.println("built-in");
    }
}
~~~

The old **CleanupJob.class** still references **Job** as its superclass, yet it is not in the permitted direct subclass set. When the JVM loads the old class, **IncompatibleClassChangeError** occurs.

The fact that Job's source still has the **execute()** method does not change the conclusion. The inheritance relationship has become part of the linking conditions.

### 6.2. What if the old subclass is listed in permits?

A **precompiled** old subclass can continue linking if it is a valid permitted direct subclass and other binary conditions are met. However, the subclass source when **recompiled** must obey the new sealed hierarchy rules, such as declaring **final**, **sealed**, or **non-sealed**.

Do not equate two things:

- Old bytecode being accepted by the JVM because the permitted list matches.
- Old source continuing to compile without updating modifiers.

Adding sealed also requires checking whether old consumers can be validly listed within package/module boundaries.

### 6.3. Adding sealed to an interface

A previously open interface may be implemented by many independent classes or subinterfaces:

~~~java
package example.spi;

public interface Plugin {
    void start();
}
~~~

If the new version changes to:

~~~java
package example.spi;

public sealed interface Plugin permits BuiltInPlugin {
    void start();
}
~~~

then old plugins that **implements Plugin** yet are not in the permitted set may hit **IncompatibleClassChangeError** when loaded. This rule applies to both direct class implementations and direct subinterfaces.

For a public SPI or SDK, adding sealed is usually a major change because the extension point may be used by consumers outside the library release team's control.

## 7. Changing the permits List Across Versions

Adding sealed is not the only thing that matters. Modifying the permitted set of a sealed type also has varying consequences.

| Change | Binary impact on old binaries | Non-binary notes |
|---|---|---|
| Open regular class to **sealed** | Can fail for unpermitted old direct subclasses | Must respect package/module and subclass modifiers |
| Open regular interface to **sealed** | Can fail for unpermitted old implementations/subinterfaces | Especially risky for public SPIs |
| Add a permitted direct subclass | Under JLS, does not break linking of old binaries | Can affect exhaustive switches and handling completeness |
| Remove a permitted direct subclass | Old binaries of the revoked subclass can hit **IncompatibleClassChangeError** | Requires replacement/consumer migration plan |
| **sealed** to **non-sealed** | Usually preserves binary compatibility | Re-opens inheritance tree; review behavioral risks |
| **final** to **sealed** | Does not break old binaries solely from modifier change | Adds possibility of new subclasses |
| **final** to open class | Usually does not break binaries, unless violating sealed parent constraints | Expands extension contract, needs support design |

### 7.1. Adding a permitted subtype and exhaustive switches

Java 21 example with pattern matching for switch:

~~~java
sealed interface Response permits Success, Failure {}

record Success(String value) implements Response {}

record Failure(String message) implements Response {}

static String describe(Response response) {
    return switch (response) {
        case Success s -> s.value();
        case Failure f -> f.message();
    };
}
~~~

At compile time, the compiler sees the permitted subtypes and determines the switch is exhaustive.

If a new version expands the hierarchy with a third subtype while the old program keeps the switch bytecode, **adding** a subtype is generally considered binary compatible under JLS: the old class file can still link.

However, when the old switch actually receives an instance of the uncovered new subtype, **MatchException** can arise at runtime. This is a behavioral/migration compatibility risk even though it does not break binary linkage of the sealed type.

Therefore, when expanding **permits**, in addition to checking the binary API, search for switch expressions/pattern switches relying on exhaustiveness, and run compatibility tests with the new type.

### 7.2. Removing a permitted subtype

When a previously permitted subclass is removed from **permits**, the old class file of that subclass itself may fail to load. This is not merely a compiler warning; the JVM enforces inheritance structure checks at link time.

Before removing a subtype, you must know:

- Are consumers instantiating the subtype?
- Does serialized data contain the subtype name?
- Do ServiceLoader, reflection, or DI containers load the subtype?
- Are there independently compiled consumers?
- Can the subtype be supported for one more release cycle?

If consumers cannot be controlled, a major release with a migration guide and support timeline is a clearer choice.

## 8. Non-sealed as a Controlled Extension Point

A sealed hierarchy does not have to lock down every level. You can restrict high-level type groups while reserving a **non-sealed** branch for third parties to extend.

~~~java
package example.api;

public sealed interface Message
        permits SystemMessage, ExternalMessage {
}

public record SystemMessage(String text) implements Message {
}

public non-sealed interface ExternalMessage extends Message {
}
~~~

External consumers can implement **ExternalMessage**:

~~~java
package partner.plugin;

import example.api.ExternalMessage;

public final class PartnerMessage implements ExternalMessage {
}
~~~

Benefits:

- The direct subtype set of **Message** remains controlled.
- The public API provides a clear extension point.
- Third parties do not need to be listed directly in **Message.permits**.
- Modules can be upgraded independently through the **ExternalMessage** branch.

However, **non-sealed** does not automatically make all future changes safe. If later on the library turns **ExternalMessage** into sealed or final, it can still break already-released plugins. An open branch should be treated as a long-term support contract.

### 8.1. Non-sealed is only valid inside a sealed hierarchy

You cannot arbitrarily write:

~~~java
public non-sealed class Utility {
}
~~~

if Utility has no sealed direct superclass or sealed direct superinterface. The compiler will reject it. Therefore, when removing **final** inside a sealed hierarchy, choose valid modifiers and inheritance relationships; do not just delete the keyword and assume source still compiles.

## 9. Changing Superclasses, Interfaces, and Constructors

**final** and **sealed** are the clearest manifestations of inheritance risk, yet other changes can also break old consumers.

### 9.1. Changing superclass or dropping an interface

A compiled subclass may rely on a type remaining a subtype of a specific class/interface. If the library changes the hierarchy and removes a supertype that old binaries use in calls or casts, linkage errors or **VerifyError** can appear.

Do not conclude "nobody directly calls the superclass" from source alone. Type relationships are also used in bytecode to verify type safety and method dispatch.

### 9.2. Narrowing constructors

Subclasses invoke superclass constructors via **super(...)**. If a public or protected constructor in the old version is removed, changes descriptor, or narrows access in the new version, old subclasses may encounter **NoSuchMethodError** or **IllegalAccessError** when linking constructor calls.

Example:

~~~java
public class Base {
    protected Base(String configuration) {
    }
}
~~~

Old consumer:

~~~java
public class CustomBase extends Base {
    public CustomBase() {
        super("custom");
    }
}
~~~

If v2 only retains **Base(int)**, old bytecode still references the String-taking constructor and may fail to link. This is an issue independent of whether the class is final or sealed.

### 9.3. Adding abstract or changing method overrides

Turning a concrete method into abstract or adding an abstract member to a class/interface contract can leave old consumers missing an implementation when an actual call path is exercised. The error can be **AbstractMethodError**.

Adding a default method to an interface usually does not directly break old linkage, yet can create conflicts when multiple interfaces supply default methods with the same signature. When a conflicting call path runs, **IncompatibleClassChangeError** may appear.

That is why evaluating inheritability requires inspecting the entire hierarchy and method resolution, not just searching for final/sealed modifiers.

## 10. Risks with Frameworks, Proxies, and Runtime-Generated Code

A framework can generate subclasses not present in the source repository. For example:

- Spring AOP using class-based proxies.
- ORMs or lazy-loading libraries creating proxies by subclassing.
- Byte Buddy, CGLIB, or instrumentation tools generating bytecode.
- Plugin frameworks loading classes by name from configuration.
- Serialization/deserialization frameworks needing to instantiate or resolve subtypes.
- ServiceLoader discovering implementations at runtime.

If a class becomes **final**, mechanisms needing to subclass that class may stop working. If a method becomes **final**, class-based proxies generally cannot override that method to insert interception logic. If an interface becomes **sealed**, a generated class trying to directly implement the interface may be rejected unless it is a valid permitted subtype.

This risk category requires integration tests, because unit tests invoking classes directly may still succeed.

### 10.1. Not every proxy uses subclassing

Java has interface-based proxies and class-based proxies with different constraints. If a framework uses proxies based on a regular interface, making the implementation class final does not necessarily stop interface proxies from working. Conversely, if the interface itself becomes sealed, generated implementations must be examined under permits rules.

Therefore, confirm the actual proxy mechanism of each framework and project configuration. Do not apply a blanket conclusion to all proxies.

### 10.2. Testing by extension mechanism

| Mechanism | Scenario to test |
|---|---|
| Subclass source | Consumers directly extending |
| Interface implementation | Consumers directly implementing |
| Reflection | Loading class by name, calling constructors, checking modifiers |
| ServiceLoader | Old providers can be discovered and loaded |
| Class-based proxy | Does framework create subclasses of newly final/sealed classes |
| Method interception | Does newly final method block interception |
| Serialization | Does old data reference a subtype removed from permits |
| Pattern switch | Do old exhaustive switches handle new subtypes |

A risk is considered resolved only when evidence exists on the actual failure mechanism, not merely when source recompiles cleanly.

## 11. Lab: Running an Old Subclass Against a Newly final Class

The following example shows how to truly verify binary compatibility. We will compile a plugin once against library v1 and then keep the plugin's class files unchanged when swapping in library v2.

### Step 1: Create library v1

File **v1/example/api/Engine.java**:

~~~java
package example.api;

public class Engine {
    public String run() {
        return "Engine v1";
    }
}
~~~

Create JAR:

~~~bash
javac -d out-v1 v1/example/api/Engine.java
jar --create --file engine-v1.jar -C out-v1 .
~~~

### Step 2: Create plugin and client

File **consumer/example/plugin/CustomEngine.java**:

~~~java
package example.plugin;

import example.api.Engine;

public class CustomEngine extends Engine {
    @Override
    public String run() {
        return "Plugin";
    }
}
~~~

File **consumer/example/app/Main.java**:

~~~java
package example.app;

import example.plugin.CustomEngine;

public class Main {
    public static void main(String[] args) {
        System.out.println(new CustomEngine().run());
    }
}
~~~

Compile consumer with JAR v1:

~~~bash
javac -cp engine-v1.jar -d consumer-out consumer/example/plugin/CustomEngine.java consumer/example/app/Main.java
~~~

Here **consumer-out** contains old bytecode. Do not recompile those files in subsequent steps.

Run baseline:

~~~bash
# Windows
java -cp "engine-v1.jar;consumer-out" example.app.Main

# Linux/macOS
java -cp "engine-v1.jar:consumer-out" example.app.Main
~~~

Output:

~~~text
Plugin
~~~

### Step 3: Replace Engine with the final version

File **v2/example/api/Engine.java**:

~~~java
package example.api;

public final class Engine {
    public String run() {
        return "Engine v2";
    }
}
~~~

Create JAR v2:

~~~bash
javac -d out-v2 v2/example/api/Engine.java
jar --create --file engine-v2.jar -C out-v2 .
~~~

### Step 4: Run the old consumer without recompiling

~~~bash
# Windows
java -cp "engine-v2.jar;consumer-out" example.app.Main

# Linux/macOS
java -cp "engine-v2.jar:consumer-out" example.app.Main
~~~

The JVM must load **CustomEngine.class** compiled against Engine v1. Yet **Engine v2** is final. The expected result is **IncompatibleClassChangeError** reporting that a class attempts to inherit from a final class.

Point to note: library v2 compiles cleanly on its own, still has the **run()** method, and an application that only calls **new Engine()** can run normally. The error appears only when an old consumer with an extends relationship is loaded.

### Step 5: Inspect class files

Use **javap**:

~~~bash
javap -classpath engine-v1.jar -v example.api.Engine
javap -classpath engine-v2.jar -v example.api.Engine
javap -classpath consumer-out -v example.plugin.CustomEngine
~~~

In the class file, a **final** class has the **ACC_FINAL** flag. CustomEngine's class file still declares Engine as its superclass. When swapping the JAR, the new class file combination fails inheritance conditions.

This example helps separate binary errors from compile errors. Do not invoke **javac** again on the consumer during the binary compatibility test step.

## 12. Lab with sealed and permits

A similar test can illustrate sealed. To keep the example compliant with package rules in an unnamed module, the new sealed library and permitted direct subclasses reside in the same package **example.model**.

Version 1:

~~~java
package example.model;

public interface Operation {
    String name();
}
~~~

An already-compiled old implementation:

~~~java
package example.external;

import example.model.Operation;

public class UnknownOperation implements Operation {
    @Override
    public String name() {
        return "unknown";
    }
}
~~~

Version 2 of the interface:

~~~java
package example.model;

public sealed interface Operation permits KnownOperation {
    String name();
}

final class KnownOperation implements Operation {
    @Override
    public String name() {
        return "known";
    }
}
~~~

When the runtime uses **Operation v2** and loads the old binary **UnknownOperation**, that implementation is not a permitted direct subtype. The JVM can throw **IncompatibleClassChangeError**.

The fix cannot simply be adding **UnknownOperation** to permits if the actual implementation resides in a different package in an unnamed module. Design changes are needed, such as:

- Continue keeping Operation as an open interface in versions needing compatibility.
- Create a new sealed hierarchy for internal built-in types, while leaving old Operation intact.
- Create a **non-sealed** extension branch in the new hierarchy to let external consumers implement it.
- Release a major version and require consumers to update if locking down the extension point is intentional.

## 13. Migration Strategies to Reduce Breakage

### 13.1. Keep the API open during the transition period

If a public base class is already subclassed by consumers, a safe approach is to keep the old class non-final during a transition cycle while introducing a new API with a more restricted design.

Example:

~~~java
package example.api;

@Deprecated(since = "2.0")
public class LegacyProcessor {
    public String process(String text) {
        return text;
    }
}

public final class NewProcessor {
    public String process(String text) {
        return text;
    }
}
~~~

Old consumers can still extend **LegacyProcessor**. New consumers use **NewProcessor** if inheritance is not needed. Once a migration plan is in place, the library can decide when to remove the old API.

Marking deprecated does not by itself break binary compatibility. It provides a migration signal before dropping the contract.

### 13.2. Use composition instead of inheritance

If the goal of final is to prevent subclasses from altering internal logic, you can preserve the old open contract while moving execution to an encapsulated object.

~~~java
public final class ProcessingCore {
    public String execute(String input) {
        return input.trim();
    }
}

@Deprecated
public class LegacyProcessor {
    private final ProcessingCore core = new ProcessingCore();

    public String process(String input) {
        return core.execute(input);
    }
}
~~~

**LegacyProcessor** stays open for old consumers, while **ProcessingCore** uses final since it is not designed as an extension point. The team can gradually guide consumers toward composition without abruptly banning existing subclasses.

### 13.3. Maintain valid protected hooks

If a framework needs to permit customization, clearly define which methods are extension points:

~~~java
public class TaskRunner {
    public final void runTask() {
        beforeRun();
        executeCore();
        afterRun();
    }

    protected void beforeRun() {
    }

    protected void afterRun() {
    }

    private void executeCore() {
        System.out.println("core");
    }
}
~~~

This pattern works well **when designing a new API**: a final orchestration method preserves invariants, while protected hooks remain overridable.

However, if **runTask()** previously allowed subclasses to override and old consumers are doing so, changing it directly to final can still break binary compatibility. Phased migration must be rolled out, keeping the old method or creating a new API rather than assuming a cleaner design pattern makes an old breaking change safe.

### 13.4. Add a parallel sealed hierarchy

Instead of turning an open SPI interface into sealed:

~~~java
public interface Plugin {
    void execute();
}
~~~

keep **Plugin** for old consumers while adding a separate sealed hierarchy for controlled system types:

~~~java
public sealed interface BuiltInAction
        permits ReadAction, WriteAction {
}

public record ReadAction(String path) implements BuiltInAction {
}

public record WriteAction(String path, String data) implements BuiltInAction {
}
~~~

Built-in types have a well-defined scope, while Plugin continues as an external extension point. This separates exhaustive modeling needs from public plugin support requirements.

### 13.5. Intentional versioning

If the product decides inheritance must be locked down:

1. Announce the upcoming change.
2. Mark the old API deprecated.
3. Provide adapters or new APIs for consumers to migrate.
4. Inventory actual subclasses/implementations.
5. Create compatibility tests against old artifacts.
6. Define a support window and a major release for breaking changes.
7. Update migration guides and release notes.
8. Change the contract only once consumer impact is explicitly accepted.

**Semantic Versioning** helps communicate the degree of change, yet major/minor labels do not by themselves guarantee the JVM will link. Test evidence on concrete artifacts remains necessary.

## 14. Testing Binary Compatibility and Extensibility

### 14.1. Testing workflow

1. **Lock baseline:** save library/API v1 JAR, commit, checksum, and the JDK used to compile.
2. **Preserve old consumers:** obtain released binary plugins/subclasses/implementations.
3. **Identify changes:** compare final, sealed, non-sealed, permits, method modifiers, constructors, and hierarchy.
4. **Build new library:** create JAR v2 from new source.
5. **Run old binaries:** keep consumer class files intact, swapping only library v1 for v2 on classpath/module path.
6. **Test class loading:** trigger loading of key plugins, ServiceLoader providers, proxies, and subclasses.
7. **Test behavior:** exercise related overrides, hooks, and pattern switches.
8. **Save evidence:** record JDK, JAR checksums, classpath, launch commands, and error logs.
9. **Assess remaining risk:** clearly note any consumers without a representative binary.

For Java 17+ libraries, **javap** can be used to inspect modifiers and the permitted subclasses list:

~~~bash
javap -classpath api-v2.jar -v -p example.api.SomeType
~~~

Signals to look for:

- **ACC_FINAL** for final classes or methods.
- **PermittedSubclasses** attribute for sealed types.
- **super_class** and **interfaces** of old consumer class files.
- Method descriptors and access flags for cross-checking.

API comparison tools like Revapi or japicmp can help identify changes. However, API reports do not replace running the old artifacts themselves, especially when plugins, generated proxies, and runtime-only dependencies exist.

### 14.2. Recommended test matrix

| Case | Old source + new API | Old binary + new API | Meaning |
|---|---|---|---|
| Class v1 open, v2 final; consumer extends | Compile fails | Possible ICCE when loading subclass | Breaking inheritance |
| Instance method v1 open, v2 final; consumer overrides | Compile fails | Possible ICCE when loading class | Breaking override |
| Static method v1 open, v2 final | Source hiding may be restricted | Usually does not break binary per JLS | Source and binary differ |
| Class v1 open, v2 sealed; consumer not permitted | Compile fails | ICCE when loading subclass | Breaking permits |
| Sealed v1, v2 adds subtype | Old consumer usually compiles if not relying on exhaustive source | Old binary can still link | Must test exhaustive switch/behavior |
| Sealed v1, v2 removes a permitted subtype | Old consumer may fail to compile | ICCE when loading old subtype | Breaking permits |
| Final v1, v2 legally removes final | Usually adds extensibility | Old binary can still link | Generally binary safe |
| Concrete method v1 becomes abstract | Compile may fail depending on class | Possible AbstractMethodError on call | Breaking implementation contract |

**ICCE** stands for **IncompatibleClassChangeError**. The table expresses typical error mechanisms; when the error arises depends on which classes are loaded and which code paths are executed.

### 14.3. Consumers to include in tests

- Subclasses built within the same repository.
- Independently released plugins.
- Implementations of public interfaces/SPIs.
- Framework extensions or interceptors.
- Runtime proxies generated by ORM/AOP.
- Consumers using reflection, ServiceLoader, or class names from configuration.
- Consumers containing exhaustive switches over sealed hierarchies.
- Scheduled batch jobs rarely triggered by normal tests.

Having only library v2 tests without testing old consumers is insufficient evidence for binary compatibility.

## 15. Risks in Module Systems and Class Loaders

Sealed hierarchies have package/module rules, while class loading depends on the actual classpath, module path, and class loaders. These factors must be recorded during migration.

For example:

- A plugin running in a different named module may not be valid as a permitted direct subtype of a sealed API.
- Frameworks using separate class loaders may load a library version other than the one the team intended.
- Multiple JARs containing the same class with different modifiers or permits.
- Shadowed dependencies causing the runtime API to differ from the compile-time API.
- A plugin loaded only during a specialized task, causing errors to appear late.

When investigating, verify which artifact was actually loaded by the JVM, its version/checksum, and the actual path. Do not draw conclusions solely from dependency declarations in build files.

Options such as opening modules for reflection or adding command-line flags cannot turn an unpermitted subclass into a valid one under a sealed hierarchy. **Permits** is a language and JVM constraint; it is not a reflection configuration error that can be bypassed with an arbitrary runtime flag.

## 16. Evaluation Checklist Before Changing final/sealed

### Identify API and consumers

- [ ] Locked down the library baseline artifact.
- [ ] Inventoried classes/interfaces published as extension points.
- [ ] Searched for subclasses or implementations in the repository.
- [ ] Reviewed plugins, SDK consumers, and external modules.
- [ ] Checked proxies, ServiceLoader, and reflection.
- [ ] Recorded JDK version and actual class loading mechanism.

### Evaluate modifiers

- [ ] Does the newly final class have old subclasses?
- [ ] Does the newly final instance method have consumers overriding it?
- [ ] Does the newly sealed class/interface exclude old direct children?
- [ ] Do all permitted direct subtypes reside in the right package/module?
- [ ] Do children of the sealed type have valid final/sealed/non-sealed modifiers when recompiled?
- [ ] Is there an appropriate non-sealed branch if external extension support is needed?
- [ ] Was an already-released permitted subtype removed?
- [ ] Does adding a subtype require checking old exhaustive switches?

### Testing and release

- [ ] Compared API binaries and classfile flags.
- [ ] Ran old consumer class files against the new JAR without recompiling consumers.
- [ ] Tested plugin loading paths and runtime proxies.
- [ ] Tested method overrides, constructors, and hierarchies.
- [ ] Tested exhaustive switches if the permitted set expanded.
- [ ] Recorded failures and test evidence.
- [ ] Prepared a migration/adapter/deprecation plan if breaking.
- [ ] Defined rollback and consumer support responsibilities.

## 17. Specification Reference for Cross-Checking

Binary compatibility rules are specified in **Java Language Specification, Chapter 13: Binary Compatibility**:

- **§13.4.2:** sealed, non-sealed, and final classes.
- **§13.4.17:** final methods.
- **§13.4.4:** changing superclasses and superinterfaces.
- **§13.5.2:** sealed and non-sealed interfaces.
- **§13.5.7:** changing interface methods, including default methods.

Refer directly to the official specification for Java 17 and later: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html

When evaluating a specific migration, read the specification of the release corresponding to the target compiler and runtime. If a project uses a newer Java version and needs detailed rules for a new feature, check the relevant chapter in that release's JLS.

---

**Key takeaway:** The ability to be subclassed, implemented, or overridden is part of the API contract. Adding **final** or **sealed** can alter that contract even when method names and descriptors remain intact. To migrate safely, test precompiled binary consumers, evaluate **permits** sets and extension points, and provide a transition path or replacement API before locking down the inheritance hierarchy.