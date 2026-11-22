# 18.3. Creating a DynamicLinker from DynamicLinkerFactory and Integrating into Bootstrap

## Learning Objectives

This lesson belongs to **Java Advance – dynamic-runtime**, part **18. Dynalink**. After this lesson, you can:

- Explain the relationship between `DynamicLinkerFactory`, `DynamicLinker`, `CallSiteDescriptor`, `Operation`, `RelinkableCallSite`, and `GuardedInvocation`.
- Create a linker using `DynamicLinkerFactory.createLinker()`; understand configuring prioritized linkers, fallback linkers, the class loader used for linker discovery, the unstable relink threshold, and synchronization when updating a call site.
- Build a bootstrap method with the familiar signature `(MethodHandles.Lookup, String, MethodType) -> CallSite`, normalizing the operation name and type before handing the call site to Dynalink.
- Create a `SimpleRelinkableCallSite` with a `CallSiteDescriptor` and call `dynamicLinker.link(callSite)` in the proper sequence.
- Understand **lazy linking**: `link` initially attaches a call path to perform linking when the **first runtime argument** arrives, then invokes the appropriate linker; a failed guard can trigger a relink.
- Use `StandardOperation.GET/SET`, `StandardNamespace.PROPERTY/ELEMENT`, and `NamedOperation` to describe operations without writing arbitrary operation strings in the linker layer.
- Create a custom linker using `GuardingDynamicLinker` and place it before the default `BeansLinker` with `setPrioritizedLinker`; return `null` when the type/operation is not recognized so fallback handles it.
- Distinguish between a program that **calls bootstrap manually to learn Dynalink** and a **real `invokedynamic` instruction in a class file**; know what must be handled by the compiler/bytecode generator.
- Diagnose `MethodType` mismatch errors, access errors, wrong guards, unsupported operations, cache thrashing, stale targets, and risks when defining a dynamic language runtime.

**Environment:** JDK 17 or later has the `jdk.dynalink` module. The three Java 17 examples are verified with `javac --release 17` and `java`, requiring no external libraries. If building an application as a named Java module, declare `requires jdk.dynalink;` in `module-info.java`. The demonstration programs below run on the **classpath**, so the short commands do not need a module-info file.

## 1. The Problem Dynalink Solves

A dynamic language has the expression:

~~~text
value.name
~~~

But at compile time, `value` could be:

- A Java bean with `getName()`;
- An object from a custom language runtime;
- A Map or an object with property/element access rules;
- An implementation whose type is only known at execution time.

At each call site, the runtime wants to:

1. Know the **operation** to perform (for example, getting the property `name`).
2. Inspect the **actual runtime object** and choose the appropriate handling.
3. Attach the executing MethodHandle, ideally with a **guard** indicating when the link is still valid.
4. When the type/shape changes, relink while preserving the meaning of the same call site.

Dynalink in the `jdk.dynalink` module is a library that helps coordinate that process. It provides ways to describe operations, select guarding linkers, and update call sites. It is **not a compiler or bytecode generator**: generating an `invokedynamic` instruction in a classfile is the responsibility of a separate compiler/tool.

### 1.1. The Big Picture

~~~text
Dynamic language compiler / interpreter
             |
             | creates CallSiteDescriptor from Lookup + Operation + MethodType
             v
Bootstrap method
             |
             | new SimpleRelinkableCallSite(descriptor)
             v
       DynamicLinker.link(callSite)
             |
             | sets initial target: relink-and-invoke
             v
First call with runtime arguments (receiver)
             |
             | Dynalink queries GuardingDynamicLinkers in order
             v
  prioritized -> autodiscovered -> fallback/BeansLinker
             |
             | GuardedInvocation { invocation, guard, ... }
             v
 RelinkableCallSite stores the guarded invocation strategy
             |
             +------ guard true ------> invoke linked MethodHandle
             |
             +------ guard false -----> relink for new type/shape
~~~

When using Dynalink properly, the **factory** only needs to create the linker during runtime setup; **bootstrap** creates the call site for each operation site; **DynamicLinker** coordinates; **guarding linkers** know specifically how to invoke the object.

### 1.2. Role of Each Class

| Component | Role | What NOT to confuse it with |
| --- | --- | --- |
| `DynamicLinkerFactory` | Configures and creates `DynamicLinker` | Not a CallSite or bootstrap method |
| `DynamicLinker` | Coordinates linkers, sets up relinking for call sites | Not directly the MethodHandle of a business method |
| `CallSiteDescriptor` | Holds `Lookup`, `Operation`, and immutable `MethodType` of the call site | Does not hold the runtime receiver |
| `Operation` | Expresses GET/SET/CALL/NEW... and namespace/name | Not just an arbitrary string |
| `RelinkableCallSite` | A CallSite that can receive new targets from Dynalink | Not `ConstantCallSite` |
| `SimpleRelinkableCallSite` | Strategy storing **one** current guarded invocation (monomorphic) | Does not cache unlimited types |
| `ChainedCallSite` | Strategy storing a chain of guarded invocations (polymorphic) | Not always the best choice |
| `GuardingDynamicLinker` | Proposes a link for a receiver/operation it can handle | Returns `null` if not recognized, does not force-claim all calls |
| `GuardedInvocation` | Combines invocation handle, guard, and optional invalidation | Not just an unconditional MethodHandle |
| `BeansLinker` | General-purpose fallback for operating on Java objects | Does not automatically know all semantics of a custom language |

## 2. Creating a DynamicLinker with the Factory

Core code:

~~~java
// Fragment: with import jdk.dynalink.DynamicLinkerFactory/DynamicLinker.
DynamicLinkerFactory factory = new DynamicLinkerFactory();
DynamicLinker linker = factory.createLinker();
~~~

The factory creates a linker according to the configuration **at the time of `createLinker()`**. Finishing configuring a factory does not mean any previously created DynamicLinker immediately mutates. Usually, you should build, configure, then create one linker and reuse it across many call sites in the runtime.

Creating a default linker is sufficient for testing **Java objects** because `DynamicLinkerFactory` defaults to having `BeansLinker` as a fallback if the user does not configure another fallback list. This is a good starting point: you do not need to write a `GuardingDynamicLinker` immediately when the goal is just reading Java bean properties.

### 2.1. A More Realistic Configuration

~~~java
// Fragment: used inside createLinker() of the full example.
DynamicLinkerFactory factory = new DynamicLinkerFactory();
factory.setSyncOnRelink(true);
factory.setUnstableRelinkThreshold(4);
DynamicLinker linker = factory.createLinker();
~~~

Meaning:

- `setSyncOnRelink(true)` causes DynamicLinker to invoke the `MutableCallSite.syncAll` mechanism after relinking per its contract. The goal is to support publication/visibility of the new target in a multi-threaded environment; it does **not** make the receiver's state thread-safe.
- `setUnstableRelinkThreshold(4)` sets the threshold after which a site, following a number of relinks, is considered "unstable", so linkers can be notified via `LinkRequest.isCallSiteUnstable()` and choose appropriate handling. It is not a limit meaning "allow at most 4 relinks".
- The default for this threshold is **8** if unconfigured; a value of **0** means never marking a call site unstable according to that configuration.
- `createLinker()` returns a `DynamicLinker` with the configured pipeline.

In this practice lesson, these settings help show the code in the right place. **Do not infer better performance merely from enabling sync or lowering the threshold**. The optimal level depends on workload, receiver type distribution, guard strategy, and concurrency.

### 2.2. Prioritized Linkers and Fallback

Frameworks with their own object model usually register a `GuardingDynamicLinker`:

~~~java
// Fragment: customLinker implements GuardingDynamicLinker.
factory.setPrioritizedLinker(customLinker);
DynamicLinker linker = factory.createLinker();
~~~

Dynalink queries linker groups in a defined order: **prioritized**, linkers **auto-discovered** via class loader/service provider, then **fallback**. By default, `BeansLinker` is usually at the end to handle Java objects.

The key is to **return null to yield** when the custom linker does not understand the operation or receiver. If the custom linker returns an incorrect `GuardedInvocation` for a type outside its domain, the Java fallback linkers will no longer be queried and the call site may behave incorrectly.

### 2.3. Factory Configurations Worth Knowing

| API | Purpose | Notes |
| --- | --- | --- |
| `setPrioritizedLinker(linker)` / `setPrioritizedLinkers(...)` | Places the linker for the runtime's object model in front | Custom linker should check both operation and receiver |
| `setFallbackLinkers(...)` | Specifies the fallback list | An empty list can remove the default BeansLinker |
| `setClassLoader(loader)` | ClassLoader to discover `GuardingDynamicLinkerExporter` | Defaults to the thread's context class loader at `createLinker` |
| `getAutoLoadingErrors()` | Views autoloading errors from the most recent `createLinker()` | Useful when deployment/service provider is not found |
| `setSyncOnRelink(true/false)` | Synchronizes publication after relink | Does not synchronize the target object's state |
| `setUnstableRelinkThreshold(n)` | Marks site unstable after enough relinks | Does not "lock the site" after n times |
| `setPrelinkTransformer(...)` | Customizes the guarded invocation right before attaching to the call site | Advanced; by default types are already adapted via LinkerServices |
| `setAutoConversionStrategy(...)` | Adds type conversion strategy at the linker layer | Not an arbitrary cast bypassing type safety |
| `setInternalObjectsFilter(...)` | Filters internal objects in handles appropriate for a language runtime | Requires clear understanding of language boundaries |

**Do not configure `setFallbackLinkers` with an empty list in a simple Java-bean example**, because that removes the mechanism needed to read Java properties via BeansLinker. If you want to control fallback yourself, create and explicitly register the corresponding linker.

## 3. Describing Operations: From Bootstrap Name to CallSiteDescriptor

`CallSiteDescriptor` records:

1. `MethodHandles.Lookup`: the caller context and appropriate access privileges.
2. `Operation`: the nature of the dynamic operation.
3. `MethodType`: the fixed signature at the dynamic call site.

A descriptor looks like this:

~~~java
// Fragment: caller and type are received from the bootstrap method.
Operation operation = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("name");
CallSiteDescriptor descriptor =
        new CallSiteDescriptor(caller, operation, type);
~~~

The interpretation is: **get the property named "name" of the receiver**. `Operation.withNamespace` attaches `StandardNamespace.PROPERTY` to GET; `named("name")` freezes the property name in the descriptor instead of receiving it from a runtime operand.

### 3.1. Why Does GET Need a Namespace?

`StandardOperation.GET` is used to retrieve a value from a namespace defined by the object model. In Dynalink, GET/SET must be attached to an appropriate namespace:

| Typical Namespace | Meaning |
| --- | --- |
| `StandardNamespace.PROPERTY` | Property/bean property/field semantics |
| `StandardNamespace.ELEMENT` | Indexed/keyed element, such as Map/list/array per linker rules |
| `StandardNamespace.METHOD` | Look up a method as a callable attribute, per object model and linker |

There is no rule that "every object supports all three namespaces in the same way". Language-specific linkers can have different lookup semantics. The `jdk.dynalink` documentation only provides a standard way to represent operations, not a single unified object model for all runtimes.

### 3.2. Named GET and Unnamed GET Have Different Signatures

| Operation | Logical Signature | Example |
| --- | --- | --- |
| `GET.withNamespace(PROPERTY)` | `(receiver,name) -> value` | Property name is a runtime operand |
| `GET.withNamespace(PROPERTY).named("name")` | `(receiver) -> value` | Name is held in the descriptor |
| `SET.withNamespace(ELEMENT)` | `(receiver,key,value) -> void` | Key from runtime operand |
| `SET.withNamespace(ELEMENT).named("id")` | `(receiver,value) -> void` | Fixed key "id" |
| `CALL` | `(callable,receiver,args...) -> value` | Needs callable object and receiver per Dynalink's contract |
| `NEW` | `(constructor,args...) -> value` | Creates instance via callable constructor |

The two parameters `receiver`/`name` are **dynamic positions per contract**, not saying every parameter must be `Object.class` in MethodType. You can choose specific types, as long as the linker and conversions support them. In the examples, `Object` is used so one site accepts multiple runtime classes.

### 3.3. Operation Is Structured Data, Do Not Parse Arbitrarily

For example, bootstrap receives `name="getName"`; in code, we use a fixed mapping table to convert it into:

~~~java
// Fragment:
if (!name.equals("getName")) {
    throw new IllegalArgumentException("Unknown operation: " + name);
}
Operation operation = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY).named("name");
~~~

This is the policy of the **language runtime**: the symbolic name at an invokedynamic call site does not by itself carry full Dynalink semantics. The runtime must define a verifiable mapping from name/static bootstrap args to `Operation`.

Avoid letting external input specify arbitrary property/method names without passing through a policy. `BeansLinker` accesses Java members according to its semantics/visibility; do not treat a named operation as a permission check.

## 4. Integrating into the Bootstrap Method

A typical bootstrap method for invokedynamic has the form:

~~~java
// Reference signature, not the full program:
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name, MethodType type) {
    ...
}
~~~

When the JVM links an `invokedynamic` instruction, it provides the caller context, symbolic name, site MethodType, and other static bootstrap arguments (if specified by bytecode). Bootstrap **must return a CallSite** whose target/type satisfies the JVM's requirements.

The path with Dynalink:

~~~text
JVM links invokedynamic
    |
    | Lookup caller, symbolic name, MethodType
    v
Runtime.bootstrap(caller,name,type)
    |
    | parse/validate operation
    v
new CallSiteDescriptor(caller,operation,type)
    |
    v
new SimpleRelinkableCallSite(descriptor)
    |
    v
dynamicLinker.link(callSite)
    |
    v
return CallSite to JVM
    |
    v
First actual invoke -> Dynalink links with actual receiver
~~~

Key point to remember: **`DynamicLinker.link` accepts a `RelinkableCallSite`, not a `ConstantCallSite`**. `ConstantCallSite` has an immutable target; Dynalink needs the ability to update the target when a guard becomes invalid.

### 4.1. Correct Bootstrap Pattern

~~~java
// Fragment: LINKER is pre-created, parseOperation(name) is defined by the runtime.
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name, MethodType type) {
    Operation op = parseOperation(name);
    CallSiteDescriptor desc = new CallSiteDescriptor(caller, op, type);
    return LINKER.link(new SimpleRelinkableCallSite(desc));
}
~~~

`DynamicLinker.link(callSite)` attaches the initial **relink-and-invoke handle** and then returns the configured callSite itself. It **does not yet need to know the concrete receiver** when bootstrap is only called with Lookup/name/type. The receiver appears later, at the **first execution** of the call site.

This is the difference between:
- **bootstrap/link call site**: preparing the mechanism.
- **runtime guard linking**: choosing the strategy for the actual receiver.
- **invoke business operation**: running the linked handle.

### 4.2. Why Keep One Reusable DynamicLinker?

In the complete example, `LINKER` is `private static final` and created once:

~~~java
// Fragment:
private static final DynamicLinker LINKER = makeLinker();
~~~

Many bootstrap calls can use the same DynamicLinker to create **separate call sites** for many bytecode locations. Having a shared linker does **not** mean every call site shares the same `CallSite` or the same receiver cache.

In runtimes with multiple plugins/language environments or classloaders, you may need one DynamicLinker per context classloader/runtime module to avoid mixing incompatible linker discoveries. Managing cache/lifetime is the application's responsibility.

## 5. Complete Example 1: Default Factory, Bootstrap, and Java Beans

Save the file **DynalinkBootstrapDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkBootstrapDemo {
    public static final class Customer {
        private final String name;
        public Customer(String name) { this.name = name; }
        public String getName() { return name; }
    }

    public static final class Employee {
        private final String name;
        public Employee(String name) { this.name = name; }
        public String getName() { return name; }
    }

    private static final DynamicLinker LINKER = makeLinker();

    private static DynamicLinker makeLinker() {
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setSyncOnRelink(true);
        factory.setUnstableRelinkThreshold(4);
        return factory.createLinker();
    }

    // Signature matching the invokedynamic bootstrap model.
    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name, MethodType type) {
        if (!name.equals("getName")) {
            throw new IllegalArgumentException("Unknown operation: " + name);
        }
        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY).named("name");
        CallSiteDescriptor descriptor = new CallSiteDescriptor(caller, operation, type);
        return LINKER.link(new SimpleRelinkableCallSite(descriptor));
    }

    public static void main(String[] args) throws Throwable {
        MethodType siteType = MethodType.methodType(Object.class, Object.class);
        CallSite site = bootstrap(MethodHandles.lookup(), "getName", siteType);
        MethodHandle invoker = site.dynamicInvoker();

        System.out.println("siteType=" + site.type());
        System.out.println("callSiteClass=" + site.getClass().getSimpleName());
        System.out.println("customer1="
                + (Object) invoker.invokeExact((Object) new Customer("Mai")));
        System.out.println("customer2="
                + (Object) invoker.invokeExact((Object) new Customer("An")));
        System.out.println("employee="
                + (Object) invoker.invokeExact((Object) new Employee("Binh")));
        System.out.println("customer3="
                + (Object) invoker.invokeExact((Object) new Customer("Hoa")));
        try {
            bootstrap(MethodHandles.lookup(), "missing", siteType);
        } catch (IllegalArgumentException ex) {
            System.out.println("badOperation=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run on **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 DynalinkBootstrapDemo.java
java DynalinkBootstrapDemo
~~~

**Exact stdout**:

~~~text
siteType=(Object)Object
callSiteClass=SimpleRelinkableCallSite
customer1=Mai
customer2=An
employee=Binh
customer3=Hoa
badOperation=IllegalArgumentException
~~~

### 5.1. Explaining the First-Time Flow

`bootstrap(...)` creates the descriptor:

~~~text
lookup      = MethodHandles.lookup() of the demo caller
operation   = GET PROPERTY named "name"
method type = (Object)Object
~~~

Returns a `SimpleRelinkableCallSite` passed through `LINKER.link`. At this point, the code **has not passed** `Customer("Mai")` into bootstrap.

The first call:

~~~java
// Fragment from main:
Object value = (Object) invoker.invokeExact((Object) new Customer("Mai"));
~~~

passes a runtime receiver of type `Customer` into the call site. Dynalink selects the appropriate linker; by default `BeansLinker` can read the public JavaBean-style getter `Customer.getName()`. The result is `Mai`.

### 5.2. Same-Type and Different-Type Calls

The second call is `Customer("An")`, the same runtime class as the first; if the guard for the class is still valid, the call site can reuse the already linked guarded invocation.

The third call is `Employee("Binh")`, a different runtime type. With `SimpleRelinkableCallSite`, the old type guard may not accept it, so Dynalink chooses a new link path; `Employee.getName()` still returns a valid value. The fourth call returns to `Customer("Hoa")` and may relink once more.

**Do not write tests relying on a fixed number of relinks** unless you are controlling the `GuardingDynamicLinker` itself and the guard algorithm. A cache can optimize by receiver type/shape. The goal of this test is to verify the **behavior** of both Java object types, not to define the internals of BeansLinker.

### 5.3. Why Use `(Object)Object`?

CallSiteDescriptor contains `MethodType.methodType(Object.class,Object.class)`. This is the type of a **dynamic operation GET named property**:

~~~text
(receiver Object) -> result Object
~~~

Even though the actual getter returns `String`, BeansLinker/DynamicLinker can adapt the return type to match the site's signature. The Java snippet calling `invokeExact` writes `(Object)` casts on both parameter and result **so the descriptor at the call site matches exactly**.

Do not write:

~~~java
// Fragment INTENTIONALLY WRONG when invoker has type (Object)Object:
String x = (String) invoker.invokeExact((Object) new Customer("Mai"));
~~~

In Java source, casting the result directly to `String` creates an expected call-site return type of `String` and may throw `WrongMethodTypeException`, because the site's handle returns `Object`. The right way is to **get Object first**, then cast to String afterward if you know the contract:

~~~java
// Valid fragment:
Object raw = (Object) invoker.invokeExact((Object) new Customer("Mai"));
String x = (String) raw;
~~~

### 5.4. Is Java Code Calling Bootstrap Manually `invokedynamic`?

**No.** The example uses Java source to call `bootstrap(...)` in `main`, then calls `site.dynamicInvoker()`. It creates a **free-floating Dynalink call site**, sufficient to test the factory, descriptor, linker, and relinking.

To use **real `invokedynamic`** in a class file, a compiler or bytecode generator must emit an instruction with a bootstrap method handle pointing to `DynalinkBootstrapDemo.bootstrap`, an appropriate symbolic name, and MethodType `(Object)Object` (or a supported type). When the JVM runs that instruction, it calls bootstrap per the classfile protocol. Dynalink **does not write class files for you**.

This is a mandatory distinction when studying "integrating into bootstrap": **a correct bootstrap model** does not mean the Java source demo already contains a custom invokedynamic opcode.

## 6. From `DynamicLinker.link` to Guarded Invocation and Relinking

Dynalink does not necessarily know the receiver's type at bootstrap time. After the site is attached with relink-and-invoke, the first call with a receiver allows the library to:

1. Create a `LinkRequest` containing the descriptor, actual arguments, and site info (e.g., unstable state).
2. Query the first `GuardingDynamicLinker` that can handle it.
3. Receive a `GuardedInvocation` with an invocation MethodHandle and corresponding guard MethodHandle.
4. Adapt types if needed via `LinkerServices` and the prelink transformer.
5. Install the guarded invocation into `RelinkableCallSite`.
6. Execute the operation; subsequent calls go through the guard to decide whether to use the current target or relink.

### 6.1. What Does GuardedInvocation Contain?

| Component | Role |
| --- | --- |
| Invocation handle | Executes the operation on matching receiver/arguments |
| Guard handle | Returns boolean; if false, the current link is not suitable |
| Optional `SwitchPoint` | Allows out-of-band invalidation, e.g., when shape cache or configuration changes |
| Optional exception invalidation | Selects exception types that, when thrown, should invalidate the link |
| Relink-and-invoke fallback | Path back to Dynalink to choose a new strategy when the guard/invalidation is no longer valid |

A `GuardedInvocation` without a guard/invalidation can be valid **unconditionally**. In a dynamic object model with multiple types, returning an unconditional invocation for a receiver-specific method is usually wrong: another type entering the target could cause a `ClassCastException` instead of being relinked as designed.

### 6.2. SimpleRelinkableCallSite and ChainedCallSite

`SimpleRelinkableCallSite` uses a **monomorphic inline cache**: typically holding only one guarded invocation at a time. If it receives `Customer` then `Employee` then `Customer` in sequence, it may have to relink multiple times as the type guard changes.

`ChainedCallSite` uses a **polymorphic inline cache**: holding a bounded chain of guarded invocations. When a receiver matches a stored guard, the call site can avoid querying the linker again. In Java 17, Dynalink provides both in `jdk.dynalink.support`.

Comparison:

| Criterion | SimpleRelinkableCallSite | ChainedCallSite |
| --- | --- | --- |
| Typical cached strategies | One | Multiple |
| Simplicity | High | More complex guard chain |
| Call site usually sees one type | Suitable | May be unnecessary |
| Call site sees a few alternating types | May thrash/relink | Usually worth trying |
| Guaranteed faster in all cases | No | No |
| Fixed call site type | Yes | Yes |

**Do not guess performance from the name alone.** A long chain has guard-checking overhead; a monomorphic site can be very efficient when the receiver is stable. Measure in a real workload with JMH/profiler and observe the relink rate.

### 6.3. Relinking Does Not Change the Site's MethodType

Even though the target MethodHandle is replaced to support a new receiver type, **`CallSite.type()` remains unchanged**. For example, the lesson's site is always `(Object)Object`; the call paths for Customer and Employee must be adapted to this exact signature.

This is why `CallSiteDescriptor` holds the immutable `MethodType` of the call site. Relinking replaces the **implementation target**, not the signature of the bytecode call site.

## 7. Custom Language Linker: Prioritize Custom, Fallback for Java Objects

When a custom object model does not follow JavaBeans, `BeansLinker` cannot guess private internals inside the object. We can provide a custom `GuardingDynamicLinker` and use it **before** fallback.

An example: a `Box` object has an internal string `value`, only a package-private method `text()`, and no public `getName()`. The runtime wants `GET PROPERTY "name"` on Box to return text; on a Java bean Person, it should still call `getName()`.

This is the ideal role for:

~~~java
// Fragment:
factory.setPrioritizedLinker(boxLinker);
DynamicLinker linker = factory.createLinker();
~~~

The linker must check both the **Operation** and the **receiver**; if it is not a type it handles, it returns `null` so fallback continues.

## 8. Complete Example 2: Custom GuardingDynamicLinker with Guard

Save the file **DynalinkCustomLinkerDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkCustomLinkerDemo {
    public static final class Box {
        private final String value;
        public Box(String value) { this.value = value; }
        String text() { return value; }
    }

    public static final class Person {
        private final String name;
        public Person(String name) { this.name = name; }
        public String getName() { return name; }
    }

    private static int customLinks;
    private static final Operation GET_NAME =
            StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY)
                    .named("name");

    private static Object nameFromBox(Object receiver) {
        return ((Box) receiver).text();
    }

    private static boolean isBox(Object receiver) {
        return receiver instanceof Box;
    }

    private static DynamicLinker createLinker() {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            MethodHandle invocation = lookup.findStatic(
                    DynalinkCustomLinkerDemo.class, "nameFromBox",
                    MethodType.methodType(Object.class, Object.class));
            MethodHandle guard = lookup.findStatic(
                    DynalinkCustomLinkerDemo.class, "isBox",
                    MethodType.methodType(boolean.class, Object.class));

            GuardingDynamicLinker boxLinker = (request, services) -> {
                if (!GET_NAME.equals(request.getCallSiteDescriptor().getOperation())
                        || !(request.getReceiver() instanceof Box)) {
                    return null;
                }
                customLinks++;
                return new GuardedInvocation(invocation, guard);
            };

            DynamicLinkerFactory factory = new DynamicLinkerFactory();
            factory.setPrioritizedLinker(boxLinker);
            factory.setSyncOnRelink(true);
            return factory.createLinker();
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static final DynamicLinker LINKER = createLinker();

    public static CallSite bootstrap(MethodHandles.Lookup caller, String name,
                                     MethodType type) {
        if (!"getName".equals(name)) {
            throw new IllegalArgumentException("Unsupported: " + name);
        }
        CallSiteDescriptor descriptor = new CallSiteDescriptor(caller, GET_NAME, type);
        return LINKER.link(new SimpleRelinkableCallSite(descriptor));
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(Object.class, Object.class);
        CallSite site = bootstrap(MethodHandles.lookup(), "getName", type);
        MethodHandle invoke = site.dynamicInvoker();
        System.out.println("beforeLink=" + customLinks);
        System.out.println("box1="
                + (Object) invoke.invokeExact((Object) new Box("alpha")));
        System.out.println("afterBoxLink=" + (customLinks > 0));
        System.out.println("box2="
                + (Object) invoke.invokeExact((Object) new Box("beta")));
        System.out.println("person="
                + (Object) invoke.invokeExact((Object) new Person("Mai")));
        System.out.println("box3="
                + (Object) invoke.invokeExact((Object) new Box("gamma")));
        System.out.println("linkCountPositive=" + (customLinks > 0));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 DynalinkCustomLinkerDemo.java
java DynalinkCustomLinkerDemo
~~~

**Exact stdout**:

~~~text
beforeLink=0
box1=alpha
afterBoxLink=true
box2=beta
person=Mai
box3=gamma
linkCountPositive=true
~~~

### 8.1. Why Is customLinks 0 Before the First Invoke?

In `createLinker()`, we create the MethodHandles and register the `GuardingDynamicLinker` lambda; in `bootstrap(...)`, `LINKER.link(...)` only creates and attaches the **relink-and-invoke** path. There is no runtime argument of type `Box` yet, so the custom linker has not created a `GuardedInvocation` for Box.

The line `beforeLink=0` is practical proof of **lazy linking** in the demo. After the first invoke with Box, `afterBoxLink=true` shows that `getGuardedInvocation` was queried at least once.

Do not use this counter to conclude that every site/VM must have exactly one linker call: a guard miss, invalidation, or cache strategy can cause the callback to be queried multiple times.

### 8.2. Why Must the Custom Linker Return null for Person?

The code checks:

~~~java
// Fragment from GuardingDynamicLinker lambda:
if (!GET_NAME.equals(request.getCallSiteDescriptor().getOperation())
        || !(request.getReceiver() instanceof Box)) {
    return null;
}
~~~

If the operation does not match or the receiver is not `Box`, the linker yields to the next part of the pipeline. `Person` is a public Java bean with `getName()`, so the default `BeansLinker` can handle it. The output `person=Mai` proves custom + fallback work together on **one call site**.

A serious bug is writing a linker that always returns an invocation accepting only Box, even when the receiver is Person. Then the prioritized linker "swallows" the operation, causing a cast error or wrong behavior instead of falling back.

### 8.3. Invocation and Guard Must Have Compatible Signatures

In the demo:

~~~text
Call site:   (Object)Object
Invocation:  (Object)Object   -> nameFromBox(receiver)
Guard:       (Object)boolean  -> isBox(receiver)
~~~

`GuardedInvocation(invocation,guard)` fits because the guard decides when the invocation is used. When the receiver is Box, the method receives the Box value. When the receiver changes to Person, the guard is false; Dynalink can relink using BeansLinker.

Do not return an always-true guard if the invocation casts the receiver to Box. Do not create a guard with a signature returning `Object` or an incompatible parameter count and expect Dynalink to figure it out.

### 8.4. Why Can the Helper Methods Be Private?

`nameFromBox` and `isBox` are private static methods of the demo class itself. `MethodHandles.lookup()` is called inside the exact class that has permission to create MethodHandles to them. The linker holds **already-privileged MethodHandles** and uses them in GuardedInvocation; external callers do not automatically gain permission to create new handles to those private methods.

In a real runtime, publishing handles and Lookups is a capability/security concern. Do not unnecessarily expose private access privileges through the dynamic language's API.

## 9. Property and Element: Adding Named GET/SET Operations

Not every GET/SET is a JavaBean property. Dynalink has `StandardNamespace.ELEMENT` and named operation support, useful for Maps or indexed structures.

Illustrative example:

~~~java
// Fragment: get element "id" on a receiver object.
Operation readId = StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT).named("id");
MethodType readType = MethodType.methodType(Object.class, Object.class);

// Fragment: set element "id" with a value object.
Operation writeId = StandardOperation.SET
        .withNamespace(StandardNamespace.ELEMENT).named("id");
MethodType writeType =
        MethodType.methodType(void.class, Object.class, Object.class);
~~~

Here:

- `GET ELEMENT named "id"` takes one receiver operand, no runtime key argument needed.
- `SET ELEMENT named "id"` takes receiver and value; the key name is in the descriptor.
- The SET return type is `void` per the standard operation contract.
- For Java `Map<String,Object>`, the default BeansLinker knows how to handle element access using built-in rules.

## 10. Complete Example 3: Bootstrap for Named Map Element GET/SET

Save the file **DynalinkMapOperationsDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.HashMap;
import java.util.Map;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkMapOperationsDemo {
    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    private static CallSite bootstrap(MethodHandles.Lookup caller, String name,
                                      MethodType type) {
        Operation operation = switch (name) {
            case "getId" -> StandardOperation.GET
                    .withNamespace(StandardNamespace.ELEMENT).named("id");
            case "setId" -> StandardOperation.SET
                    .withNamespace(StandardNamespace.ELEMENT).named("id");
            default -> throw new IllegalArgumentException(name);
        };
        return LINKER.link(new SimpleRelinkableCallSite(
                new CallSiteDescriptor(caller, operation, type)));
    }

    public static void main(String[] args) throws Throwable {
        Map<String, Object> values = new HashMap<>();
        values.put("id", "initial");
        CallSite get = bootstrap(MethodHandles.lookup(), "getId",
                MethodType.methodType(Object.class, Object.class));
        CallSite set = bootstrap(MethodHandles.lookup(), "setId",
                MethodType.methodType(void.class, Object.class, Object.class));
        MethodHandle reader = get.dynamicInvoker();
        MethodHandle writer = set.dynamicInvoker();

        System.out.println("getType=" + get.type());
        System.out.println("setType=" + set.type());
        System.out.println("before="
                + (Object) reader.invokeExact((Object) values));
        writer.invokeExact((Object) values, (Object) "updated");
        System.out.println("after="
                + (Object) reader.invokeExact((Object) values));
        System.out.println("mapValue=" + values.get("id"));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 DynalinkMapOperationsDemo.java
java DynalinkMapOperationsDemo
~~~

**Exact stdout**:

~~~text
getType=(Object)Object
setType=(Object,Object)void
before=initial
after=updated
mapValue=updated
~~~

### 10.1. Takeaways from the Map Example

`bootstrap` builds **two descriptors with two different MethodTypes**, corresponding to read and write. Both use the same `LINKER` but have **two separate CallSites**: one for GET, one for SET.

`writer.invokeExact((Object) values, (Object) "updated")` has return type `void`, matching `SET ELEMENT named "id"`. After writing, reader uses the GET site to read the new value. The Map variable actually changed, as `values.get("id")` gives the same value.

If you omit `named("id")` while keeping SET's two-parameter signature, you will be missing the key operand required by the `SET ELEMENT` contract (when unnamed, the signature needs receiver + key + value). This is one of the easiest mistakes to make when writing your own bootstrap parser.

### 10.2. Seeing a Map Does Not Mean You Must Use PROPERTY

For a Map, `ELEMENT` is more appropriate if the language semantics are key-based lookup. `PROPERTY` is designed for property-style access; there may be overlapping behaviors depending on the linker, but **do not rely on coincidence** when designing a language contract.

When building a DSL/dynamic language, clearly decide whether `obj.name` and `obj["name"]` have the same semantics. If not, parse them into different operations/namespaces, and test consistently with Map/list/bean and custom object models.

## 11. Real invokedynamic: Who Calls Bootstrap?

All three demos above call `bootstrap(...)` **directly** in Java main, then `dynamicInvoker()`. This is **real Dynalink experimentation**, but **it does not emit custom invokedynamic bytecode**.

For the JVM itself to invoke bootstrap:

1. A compiler or bytecode generator creates a class file with an `invokedynamic` instruction at the dynamic operation site.
2. The instruction has a **symbolic name**, **method descriptor**, and references an entry in `BootstrapMethods`.
3. The bootstrap method handle must point to an appropriate method, e.g., `DynalinkBootstrapDemo.bootstrap` returning `CallSite`.
4. The JVM performs linkage of the invokedynamic site per JVMS: passing `Lookup`, name, `MethodType`, and static args to bootstrap as needed.
5. Bootstrap constructs `CallSiteDescriptor`/`RelinkableCallSite`, calls `DynamicLinker.link`, and returns the site.
6. When the instruction is executed with a runtime receiver, the initial target performs relink-and-invoke and then enters the selected target.

Illustrative classfile diagram:

~~~text
Constant pool:
    CONSTANT_InvokeDynamic [bootstrap #N, "getName", "(Ljava/lang/Object;)Ljava/lang/Object;"]

BootstrapMethods:
    #N MethodHandle REF_invokeStatic RuntimeBootstrap.bootstrap(
           MethodHandles.Lookup, String, MethodType)CallSite

Code:
    aload receiver
    invokedynamic getName:(Ljava/lang/Object;)Ljava/lang/Object;
    ... use resulting Object
~~~

**This diagram is not Java source syntax or a verbatim javap dump.** It describes the meaning of the classfile; indices/offsets depend on the bytecode-emitting tool. To inspect an actual custom invokedynamic, you need to generate a classfile with a compiler/bytecode library or bytecode generator tool and inspect it with `javap -v -c`.

### 11.1. CallSiteDescriptor Is Not Just Three Parameters "for Looks"

When relinking happens **after bootstrap**, Dynalink needs to know the original operation and caller context, rather than guessing them again from an object class name string. The descriptor stores immutable information:

- `Lookup` (the caller's privileges/lookup context);
- `Operation` (GET PROPERTY named..., SET ELEMENT..., custom operation...);
- `MethodType` (the signature that the target on every relink must satisfy).

This is why you should not write a call site holding only a "half-right" `MethodHandle` and call `setTarget` ad-hoc without keeping the descriptor. Dynalink provides the relink protocol to use the right context.

### 11.2. One Bytecode Site Is Different from One DynamicLinker Instance

One `DynamicLinker` can serve **many** call sites. Each `invokedynamic` site is linked by the JVM and has its own CallSite; the site has its own target/cache. Multiple sites may perform the same GET "name" operation yet encounter different receiver types.

Do not place a single static `CallSite` and reuse it for all AST nodes/bytecode sites if semantics or caches need to be separated. In an interpreter, you can keep **one call site per AST node**; in a bytecode compiler, the JVM has linkage sites corresponding to each instruction.

### 11.3. Does Bootstrap Run on Every Call?

No. Bootstrap participates in **dynamic linkage** when the JVM links the invokedynamic site. Once linked, subsequent executions use the CallSite target. **A guard miss can trigger a Dynalink relink**, but that does not mean the JVM calls bootstrap from scratch for every new receiver.

These are two different phases:

~~~text
JVM bootstrap linkage: creates CallSite once for the site being linked.
Dynalink runtime relink: updates the CallSite's target when the guard no longer matches.
~~~

If you call bootstrap manually in Java code multiple times, you are actively creating multiple free-floating sites; that does not prove the JVM runs bootstrap repeatedly at the same instruction.

## 12. Keeping Signatures Right: MethodType and invokeExact

CallSiteDescriptor has an immutable `MethodType`. For named GET PROPERTY "name":

~~~java
// Fragment:
MethodType type = MethodType.methodType(Object.class, Object.class);
~~~

is one Object receiver and returns Object. For named SET ELEMENT "id":

~~~java
// Fragment:
MethodType type = MethodType.methodType(void.class, Object.class, Object.class);
~~~

is receiver, value, and returns void. A new `CallSite` is created with that exact type. Every target installed by a linker/transformer must match the site's type.

### 12.1. Three Common Types of Mismatches

**(1) Wrong parameter count when adding NamedOperation.** If `name` is already fixed in the operation, there is no longer a name operand at execution time.

**(2) Wrong return type at `invokeExact`.** Even when the actual Java getter returns `String`, the site handle has type `(Object)Object`. A direct cast expression making the compiler expect String can fail; retrieve Object first and cast afterward.

**(3) Wrong static/instance or receiver type.** If a custom invocation MethodHandle only accepts `Box` while the site needs `(Object)Object`, the linker's guard/adaptation must handle it properly. Returning an incompatible handle without adapting can lead to `WrongMethodTypeException` or errors during relinking.

`LinkerServices` conversions are responsible for adapting types, but they cannot fix every invalid type request. When debugging, print `site.type()`, `descriptor.getMethodType()`, and the `MethodHandle.type()` of both invocation and guard.

### 12.2. Returning null and Unsupported Operation Errors Are Not the Same

`GuardingDynamicLinker.getGuardedInvocation` returns `null` when **that specific linker** does not handle the request; Dynalink will try other linkers. If **no linker** can handle it, the dynamic operation may fail at link or invoke time depending on the situation, such as `NoSuchDynamicMethodException` or a runtime exception.

In the demo's bootstrap parser, `name="missing"` is proactively rejected early with `IllegalArgumentException` **before handing off to Dynalink**. Do not equate a parser error we chose with a linker error where an operation cannot be found at runtime.

## 13. Upgrading Cache from Monomorphic to Polymorphic

In the examples with Customer/Employee or Box/Person, the site receives multiple receiver types. `SimpleRelinkableCallSite` is easy to understand, but if receiver types alternate frequently, it can repeatedly discard old links.

For runtimes with a few common types, you can try:

~~~java
// Fragment replacing call-site implementation, keeping descriptor and linker:
return LINKER.link(new jdk.dynalink.support.ChainedCallSite(descriptor));
~~~

`ChainedCallSite` maintains multiple guarded invocations in a bounded chain and tries to use a matching strategy before calling fallback. Check the specific version's documentation for chain limits and invalidation policy; **do not pick a chain length arbitrarily**.

Trade-offs:

- Fewer relinks for some workloads with a few receiver types.
- Higher guard-chain checking cost when there is no type match near the front.
- May increase retention of MethodHandles, classes, or dynamic shapes in the cache.
- When the unstable relink threshold is exceeded, a linker may switch to a less specialized strategy, depending on implementation.
- Concurrency still must be considered alongside `setSyncOnRelink` and publication policy.

A benchmark must be realistic: type frequency, number of sites, chain length, guard cost, and warmup. Do not turn "Chained is always better than Simple" into a rule.

## 14. Auto-Discovery of Linkers and Cross-Language Interoperability

`DynamicLinkerFactory.setClassLoader` specifies the class loader used to find `GuardingDynamicLinkerExporter` implementations via service-loading. This is useful when multiple language runtimes share the same JVM and want to link each other's objects.

Conceptually:

~~~text
Runtime A:
  prioritized linker of A
  + autodiscovered linkers of B, C...
  + fallback BeansLinker
        |
        v
 DynamicLinker shared within runtime A
        |
        v
 object of model B -> B's linker can link it
~~~

The documentation emphasizes the caller's control over class loaders/service providers. In applications using plugin class loaders, if a service exporter is not loaded due to visibility/module metadata, check `getAutoLoadingErrors()` and the context classloader at the time of `createLinker()`.

Do not assume discovery works just because a JAR is on disk. You must configure service providers and the appropriate classloader/module layer. Also do not automatically trust every exporter just because ServiceLoader finds it: treat it as **code that can execute in-process**, requiring dependency and trust control.

### 14.1. Prioritized, Autodiscovered, and Fallback Must Make Sense

A prioritized language runtime linker should be a **narrow specialist**:
- Only accept the exact operation kinds relevant to the language.
- Only accept receivers belonging to its object model.
- Return a `GuardedInvocation` with a compatible guard to check the receiver on subsequent calls.
- Return `null` immediately when it cannot handle the request.

The fallback `BeansLinker` provides Java interoperability. However, an object model different from Java needs its own linker; do not expect `BeansLinker` to automatically understand private members or specialized dynamic dictionary semantics.

## 15. Concurrency, Visibility, and Lifecycle Management

### 15.1. Why setSyncOnRelink Usually Matters with Multiple Threads

`SimpleRelinkableCallSite` is a form of relinkable mutable call site. When the target changes, the Java Memory Model and publication mechanisms determine how other threads observe the update. `DynamicLinkerFactory.setSyncOnRelink(true)` requests synchronization via the `MutableCallSite.syncAll` mechanism after relinking.

This does **not** mean:
- All runtime operations are atomic.
- The guard automatically protects all mutable data of the receiver.
- All operations on the Map in the demo are thread-safe.
- Two threads cannot trigger a relink at the same time.
- Locks/synchronization are never needed for a custom object model.

Depending on the problem, you may need to design state publication, guard checks, and invalidation. Do not replace concurrency policy with a single boolean without understanding actual data sharing.

### 15.2. Shape Changes May Require SwitchPoint

For fixed Java bean types, a type guard may be enough. But dynamic languages have object shapes/shape versions that can change **on the same runtime class**. A guard checking only `instanceof DynamicObject` could keep returning true even though the property layout has changed.

An advanced linker can attach a `SwitchPoint` to `GuardedInvocation`, invalidating it when the schema/shape is no longer valid, so the call site is forced to relink. Not every custom linker needs a SwitchPoint; you need it when validity conditions cannot be described solely by a simple receiver type/guard.

### 15.3. Caches Hold Runtime Classes and Handles

A `DynamicLinker`, `CallSite`, or `GuardedInvocation` can hold references to `MethodHandle`s, Class objects, class loaders, and runtime descriptors. If an application supports plugin hot-reload, do not keep unbounded static caches of all versions. Design lifecycle cleanup to clear references/weak keys where appropriate, while ensuring you do not break links actively used by threads.

## 16. Logging, Errors, and API Safety

### 16.1. Do Not Log Every Receiver in the Linker

`getGuardedInvocation` can run on a performance-sensitive relink path. Calling `receiver.toString()` can:
- Leak information;
- Have side effects;
- Throw object-model exceptions;
- Re-trigger dynamic operations and recursion in the logger.

Log the operation, type, and relink reason using safe metadata instead. When observing production, use sampling and measure relink frequency rather than printing all arguments.

### 16.2. Error Handling by Stage

| Stage | Symptom | What to Check |
| --- | --- | --- |
| Factory setup | Service exporter fails to load | ClassLoader, provider configuration, `getAutoLoadingErrors()` |
| Bootstrap parser | `IllegalArgumentException` due to unsupported operation name | Symbolic name -> Operation mapping |
| Descriptor creation | Type has wrong operand count for operation | Named vs unnamed, receiver/name/value |
| Initial link | Site is not a `RelinkableCallSite` | Use SimpleRelinkable/Chained, not ConstantCallSite |
| First runtime invoke | No linker accepts operation/receiver | prioritized/fallback and operation namespace |
| Custom linker | `WrongMethodTypeException`, `ClassCastException` | Invocation/guard signatures, adaptation, receiver |
| Guard miss | Excessive relinking | Overly narrow guard, monomorphic cache strategy, alternating types |
| Shape changes | Target uses stale layout | Guard/switchpoint/invalidation policy |
| Multithread | Threads observe inconsistent behavior | Target publication, `syncAll`, state concurrency |
| Code security | Callable method outside policy | High-privilege Lookup, operation validation, trust boundary |

A common mistake is "catching all Throwables and returning null": it erases the difference between **the linker not claiming the operation** (returning null is the contract) and **the linker claiming the operation but its own code failing** (needs exception handling as a bug/contract failure). A custom linker should have a clear diagnostic strategy.

### 16.3. Do Not Let Operation Names Become an Arbitrary Access Path

A bootstrap method can receive `name` and static args from a class file/linker, or interpreter code can pass data from an AST. If users can construct arbitrary names/receivers, you need an explicit API access policy. Simply configuring a `BeansLinker` does not create a permission sandbox for user-supplied objects.

Separate "allowing property A to be read in the DSL" from "a Java object having public getter B". You can use an operation-name whitelist mapping and restrict object models/types before passing them into Dynalink.

## 17. Misconceptions to Fix Immediately

**Misconception 1: `DynamicLinkerFactory` is a bootstrap method.** False. The factory configures and creates DynamicLinker. Bootstrap uses that linker to build/link a CallSite.

**Misconception 2: `LINKER.link(site)` has already finished linking to a Customer method.** Not necessarily. Dynalink attaches the relink-and-invoke path, while the actual receiver arrives on the first call.

**Misconception 3: With `invokedynamic`, the bootstrap method is automatically called on every invoke.** False. JVM linkage is different from subsequent Dynalink relinking.

**Misconception 4: Using `ConstantCallSite` is fine too because it extends CallSite.** False for `DynamicLinker.link`: the API takes a `RelinkableCallSite`, which needs target updates on guard misses.

**Misconception 5: `GET PROPERTY` is identical to `GET ELEMENT`.** False. Namespaces carry different semantics, depending on the linker.

**Misconception 6: `NamedOperation` still requires passing the key on every call.** False. The name is fixed in the descriptor; the signature removes the name operand from GET/SET.

**Misconception 7: A custom linker must throw an error if the receiver does not belong to it.** No. If it does not handle it, **return null** to yield to other linkers. Throwing is valid when policy explicitly requires rejection or a real error occurs, not as default fallback behavior.

**Misconception 8: A type-only guard will always be right when object shapes are mutable.** No. Shape/property mappings can change for the same class; consider stronger guards or invalidation.

**Misconception 9: `setSyncOnRelink(true)` automatically makes every object thread-safe.** No. It relates to publication on relink, not turning `HashMap` into a concurrent map.

**Misconception 10: `SimpleRelinkableCallSite` caches every class it has seen.** No. It is monomorphic; if you need a polymorphic inline cache, look at `ChainedCallSite`.

**Misconception 11: Printing `site.type()` as `(Object)Object` means the target Java getter must return Object.** No. Getters can return String/int; the linker adapts the target to the call-site type.

**Misconception 12: A demo calling `bootstrap(...)` manually proves the class contains a custom `invokedynamic`.** No. It proves the Dynalink pipeline works. To actually have the opcode, you must emit bytecode and inspect it with `javap`.

## 18. Checklist for Designing Dynalink Bootstrap in a Real Project

1. **Define the operation model.** Document the DSL: GET/SET PROPERTY/ELEMENT, CALL/NEW, named/unnamed, access permissions.
2. **Set up classloader/module context.** If plugin linkers need auto-discovery, configure the right loader and check errors when creating the linker.
3. **Create DynamicLinkerFactory once per context.** Configure `setPrioritizedLinker`/fallback/sync/threshold with justification.
4. **Call createLinker, store DynamicLinker.** Do not instantiate a new factory/linker for each dynamic invocation.
5. **Write the bootstrap method per protocol.** `Lookup`, name, `MethodType`; validate name/args.
6. **Map symbolic names to Operations in a controlled way.** Use `StandardOperation`, `StandardNamespace`, `NamedOperation`, or documented custom operations.
7. **Create CallSiteDescriptor.** Store caller lookup + operation + immutable type.
8. **Choose RelinkableCallSite.** Simple if monomorphic, Chained if polymorphic is needed; do not use ConstantCallSite.
9. **Call dynamicLinker.link(callSite) and return the CallSite.** Do not manually set the final target and lose the relink callback.
10. **Write a domain-accurate custom GuardingDynamicLinker.** Check receiver+operation, return null when unhandled, use an appropriate guard.
11. **Verify lazy link/relink.** Test first call, same type, different type, returning to old type, invalidation on shape change.
12. **Check MethodType.** Named GET/SET have different operand counts than unnamed; `invokeExact` cares about the return type too.
13. **Test BeansLinker fallback.** E.g., public Java bean getter and Map element; avoid unintentional empty fallback configurations.
14. **Concurrency/lifetime.** Consider `setSyncOnRelink`, mutable state, classloader unloading, and cache eviction.
15. **Test custom invokedynamic separately.** If the project generates bytecode, inspect `javap -v -c`: bootstrap index, name/descriptor, and bootstrap MethodHandle.
16. **Do not guess performance.** Use a profiler/JMH to measure relink frequency, guard cost, chain cache, and hot path.

## 19. Self-Check Questions with Answers

**Question 1.** Does `DynamicLinkerFactory` directly create a `CallSite`?

**Answer:** No. The factory creates `DynamicLinker`; bootstrap creates `CallSiteDescriptor` and `RelinkableCallSite`, then hands them to `DynamicLinker.link`.

**Question 2.** Why can `link(site)` be called before knowing the actual receiver?

**Answer:** `link` attaches the initial relink-and-invoke path. The receiver arrives on the first runtime call; at that point Dynalink queries linkers to select an appropriate `GuardedInvocation`.

**Question 3.** To read a fixed JavaBean property "name", which Operation is appropriate?

**Answer:** `StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("name")`.

**Question 4.** How many parameters does Named GET PROPERTY's method type have when there is only a receiver?

**Answer:** One receiver, e.g., `(Object)Object`. The property name is already held in the NamedOperation, so there is no name argument.

**Question 5.** What should a custom linker do when it encounters a Person receiver instead of Box?

**Answer:** Return `null` if it does not handle it, so remaining linkers like BeansLinker can handle it.

**Question 6.** Are guard `(Object)boolean` and invocation `(Object)Object` compatible with call site `(Object)Object`?

**Answer:** Yes. The guard is used to decide whether the invocation can be used, and the invocation returns Object matching the call-site type.

**Question 7.** Does `SimpleRelinkableCallSite` keep multiple guarded invocations?

**Answer:** It uses a monomorphic cache, keeping only one current strategy. `ChainedCallSite` can keep a chain of strategies if needed.

**Question 8.** Does `setUnstableRelinkThreshold(4)` cause the fifth relink to be rejected?

**Answer:** No. It affects the unstable notification when a site is relinked enough times; it does not forbid further relinking.

**Question 9.** Can `ConstantCallSite` be used with `DynamicLinker.link`?

**Answer:** No. `DynamicLinker.link` takes a `RelinkableCallSite`, not any CallSite. ConstantCallSite does not allow changing targets.

**Question 10.** If Java source code calls `bootstrap(...)` itself, is there already a custom invokedynamic instruction?

**Answer:** Not yet. That is an illustrative free-floating call site. A bytecode generator/compiler must emit `invokedynamic` pointing to bootstrap for the JVM to invoke bootstrap per the linkage protocol.

**Question 11.** What does `setSyncOnRelink(true)` guarantee?

**Answer:** It requests target publication synchronization after relinking using the `MutableCallSite.syncAll` mechanism per the API; it does not guarantee thread safety for object state or unsynchronized Maps.

**Question 12.** Do two GET name sites sharing one DynamicLinker share the same CallSite?

**Answer:** Not necessarily. One linker can serve many call sites; each linked operation site has its own site/cache.

**Question 13.** What MethodTypes do `GET ELEMENT named "id"` and `SET ELEMENT named "id"` have in the demo?

**Answer:** GET `(Object)Object`; SET `(Object,Object)void`, because the key name is fixed and SET needs receiver + value.

**Question 14.** Why should `getGuardedInvocation` not return an unconditional invocation for all types when the inner code casts to Box?

**Answer:** When the receiver is not a Box, the call could hit `ClassCastException` instead of being relinked. A guard is needed to protect the link, or return null to reject the request when outside its domain.

**Question 15.** When should a `SwitchPoint` be added to GuardedInvocation?

**Answer:** When the link can become invalid due to changes outside the guard, such as object layout/shape or runtime configuration changing even though the receiver class stays the same.

## Key Takeaways

- **`DynamicLinkerFactory` creates `DynamicLinker`; bootstrap creates `CallSiteDescriptor` and `RelinkableCallSite`; `DynamicLinker.link` attaches the linking mechanism.**
- **Initial linking is lazy.** The runtime receiver arrives at invoke time, when `GuardingDynamicLinker`s are queried; a failed guard can request a relink.
- **Operations must have the right semantics and MethodType.** `GET/SET` need a namespace; a named operation already holds the name, reducing operands by one.
- **`SimpleRelinkableCallSite` is monomorphic; `ChainedCallSite` is polymorphic.** Choose based on type distribution, not guesswork.
- **Register a custom linker with `setPrioritizedLinker`** and return null for unsupported receivers/operations so the fallback `BeansLinker` can work.
- **Separate JVM bootstrap linkage from Dynalink runtime relinking.** Calling bootstrap from Java source does not automatically generate an `invokedynamic` opcode.
- **Pay attention to concurrency, privileges, classloaders, and invalidation.** Dynalink helps connect dynamic operations, but does not replace the runtime's responsibility for security, state, and performance control.

## References

- Java SE 17, **jdk.dynalink module overview**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html
- Java SE 17, **DynamicLinkerFactory**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html
- Java SE 17, **DynamicLinker**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html
- Java SE 17, **CallSiteDescriptor**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/CallSiteDescriptor.html
- Java SE 17, **StandardOperation** and **StandardNamespace**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html
- Java SE 17, **Operation** (withNamespace/named): https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/Operation.html
- Java SE 17, **SimpleRelinkableCallSite**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html
- Java SE 17, **ChainedCallSite**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html
- Java SE 17, **GuardedInvocation**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html
- Java SE 17, **GuardingDynamicLinker**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html
- Java Virtual Machine Specification SE 17, **invokedynamic instruction**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
