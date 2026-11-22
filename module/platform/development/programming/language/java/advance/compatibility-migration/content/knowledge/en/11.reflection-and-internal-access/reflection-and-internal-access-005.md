# setAccessible, MethodHandles, and module access permissions

When upgrading a Java application from an older JDK to Java 17, 21, or a newer version, hard-to-spot errors often come from reflection and internal member access. Source code may compile successfully, yet the program only fails when a framework instantiates objects, maps data, invokes private methods, or loads a plugin. A typical error is InaccessibleObjectException: previously a library could use setAccessible(true) to open a private field, whereas on the newer runtime the package containing the field is not opened by its owning module to that library.

At the same time, Java provides MethodHandles and VarHandle to represent methods, constructors, and variables as typed handles. These are powerful tools for frameworks, performance libraries, or dynamic invocation mechanisms, but **not a way to bypass module access rules**. MethodHandles.Lookup is also permission-checked by class, package, module, and lookup scope.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **Reflection and Internal APIs**. It covers how setAccessible, MethodHandles, MethodHandles.Lookup, and privateLookupIn work, distinguishes exports from opens in the Java Platform Module System (JPMS), explains how to diagnose errors when upgrading the JDK, and presents design, configuration, and testing practices for a safe migration.

## 1. Map of access mechanisms in Java

Java has several access mechanisms, each serving a different need:

- **Direct calls:** the compiler checks public, protected, package-private, private, inheritance, and package/module scope.
- **Core reflection:** uses Class, Field, Method, and Constructor to inspect and manipulate members at runtime.
- **Method handles:** uses MethodHandle and MethodHandles.Lookup to look up and invoke methods or constructors with specified types.
- **Variable handles:** uses VarHandle to access variables, potentially providing memory-ordering and atomic operations where appropriate.
- **JPMS:** module-info.java defines which modules can be read, which packages are exported, and which packages are opened for deep reflection.
- **Runtime command-line options:** can adjust certain access boundaries at JVM startup, but do not replace supported API contracts.

The access permission layers are commonly understood through this diagram:

~~~text
Source code / library / framework
             |
             v
    Compiler and Java access
             |
             v
   Module readability + exports
             |
       +-----+------+
       |            |
       v            v
   Normal       Deep reflection
   invocation   / private lookup
       |            |
       |            v
       |      opens / open module
       |            |
       +-----+------+
             |
             v
       JVM execution
~~~

The diagram is conceptual. Each API has specific access conditions; not every reflection operation requires opens. **Public reflective access** and **deep reflection into private members** must be kept separate.

## 2. Distinguishing four kinds of access control

### 2.1. Language-level access control

Java defines:

| Modifier | Normal access scope |
|---|---|
| public | Places that can see the enclosing type, subject to additional module rules |
| protected | Same package and permitted subclass contexts |
| No modifier | Classes within the same package |
| private | Scope permitted by the language within the corresponding type/nest |

A public method in a public class is not necessarily accessible from another module if the package containing the class is not exported.

### 2.2. Module readability

In JPMS, a module typically needs to declare requires on the module containing the APIs it uses:

~~~java
module com.example.client {
    requires com.example.library;
}
~~~

This establishes a readability relationship. However, requires does not automatically open all packages of the module being read.

### 2.3. Standard package access: exports

A library module can expose its API:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Consumers can use public types in the exported package under normal Java rules. A non-exported package can still exist inside the module, but it is not implicitly public API for other modules.

### 2.4. Deep reflection permission: opens

A module can open a package to permit deep reflective access:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.model to com.example.serializer;
}
~~~

When the model package is opened to the serializer module, the framework may be permitted to perform appropriate reflection operations on non-public members in that package. However, opens is not synonymous with public source API: the compiler for the serializer module is not automatically allowed to import public types from the model package if that package has not been exported.

If both public compile-time access and deep reflection are needed, the same package can be both exported and opened, depending on the requirement.

## 3. How do standard reflection and deep reflection differ?

Java reflection provides two categories of actions:

1. **Inspection:** retrieving Field, Method, Constructor, and metadata from Class.
2. **Access/invocation:** reading fields, writing fields, invoking methods, or creating instances.

Example:

~~~java
Class<?> type = Class.forName("com.example.model.Customer");

for (java.lang.reflect.Field field : type.getDeclaredFields()) {
    System.out.println(field.getName());
}
~~~

getDeclaredFields can return metadata for fields declared in the class, including private fields. However, **discovering a member does not mean having permission to read or write that member's value**.

For example, after finding a private field:

~~~java
java.lang.reflect.Field field = type.getDeclaredField("secret");
Object value = field.get(customer);
~~~

The field.get call can throw IllegalAccessException if the calling code lacks permission. The fact that Class allows listing field names does not automatically grant access to private fields.

### 3.1. getField and getDeclaredField

| API | Target members searched |
|---|---|
| getField(name) | Public fields, including inherited ones |
| getDeclaredField(name) | Fields declared directly in the class, regardless of modifier |
| getMethod(name, types) | Matching public methods, including inherited methods |
| getDeclaredMethod(name, types) | Methods declared directly in the class |
| getConstructor(types) | Public constructors |
| getDeclaredConstructor(types) | Directly declared constructors, including non-public ones |

The getDeclared... methods help retrieve metadata, but do not have the authority to automatically bypass Java access checks.

## 4. What does setAccessible(true) do?

Field, Method, and Constructor inherit the accessibility mechanism from AccessibleObject. Calling:

~~~java
field.setAccessible(true);
~~~

requests the runtime to **suppress Java language access checks** for subsequent reflection operations on that AccessibleObject instance, in cases permitted by the JDK and JPMS.

This is not an unconditional permission grant. On a JDK with the module system, the ability to enable accessibility is constrained by the caller's module and the module containing the member.

### 4.1. Example within the same module

Suppose there is a class:

~~~java
package com.example.domain;

public final class Account {
    private final String token;

    public Account(String token) {
        this.token = token;
    }
}
~~~

A utility located in the same module can use reflection:

~~~java
package com.example.inspect;

import com.example.domain.Account;
import java.lang.reflect.Field;

public final class AccountInspector {
    public static String readToken(Account account) throws Exception {
        Field field = Account.class.getDeclaredField("token");
        field.setAccessible(true);
        return (String) field.get(account);
    }
}
~~~

When code runs in the same module and meets the reflection access conditions, the operation can succeed. However, this is still coupling to a private field. If the Account class renames token, the utility will break even though Account's public API may remain unchanged.

A better design, if reading the token is an authorized use case, is to provide a controlled API rather than relying on reflection. For tokens or secrets, security must be considered; do not expose a getter that leaks secrets merely because reflection is currently used.

### 4.2. setAccessible(false)

The call:

~~~java
field.setAccessible(false);
~~~

resets the access-check override flag. It does not make the field public or change the module descriptor; it only controls whether reflection operations attempt to bypass access checks.

### 4.3. trySetAccessible and canAccess

Starting in Java 9, you can query an AccessibleObject:

~~~java
boolean accessible = field.trySetAccessible();
~~~

If enabling the override is not permitted under module rules, trySetAccessible generally returns false instead of throwing InaccessibleObjectException as setAccessible(true) does. Other potential errors documented by the API, such as security-related restrictions in the relevant environment, still need to be handled.

You can use:

~~~java
boolean allowed = field.canAccess(targetObject);
~~~

canAccess checks whether the current calling code can access the member via reflection under its current state. For an instance field, pass the appropriate target object; for a static field, pass null. This is not a method for asking whether a package is open in all situations, and the result depends on the member, caller, and override state.

An approach to avoid cryptic errors:

~~~java
Field field = Account.class.getDeclaredField("token");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "Module owning Account does not permit reflective access");
}

String value = (String) field.get(account);
~~~

This improves diagnostics but does not alter the module contract. If exposing private data is inappropriate, the right solution is to redesign the integration.

## 5. Why can setAccessible fail after migration?

Starting in Java 9, JPMS introduced strong encapsulation at the module level. For named modules, many private reflection operations across module boundaries are only allowed when the target package is opened to the calling module.

Common scenario:

~~~text
Module: com.example.domain
  package: com.example.domain.model
  class: Customer
    private String id

Module: com.example.serializer
  calling code:
    Customer.class.getDeclaredField("id")
    field.setAccessible(true)
~~~

If the domain module only exports model without opening the package to serializer, public API access can work normally while setAccessible(true) on a private field can throw InaccessibleObjectException.

Illustrative error:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module com.example.domain does not "opens
com.example.domain.model" to module com.example.serializer
~~~

The actual message depends on the member, modules, JDK, and framework.

### 5.1. Conditions that generally allow enabling accessible

Under AccessibleObject rules, common cases include:

- Caller and member reside in the same module.
- Caller accesses a public member in a public class belonging to an appropriately exported package.
- Certain protected static cases permitted by Java/module access rules.
- The package containing the member is opened to the caller's module.

Details depend on the member kind, declaring class, caller class, and JDK reflection rules. Do not infer that exports is always sufficient for private reflection.

### 5.2. The case of final fields

setAccessible(true) does not mean every final field can be modified safely. Certain kinds of final fields cannot be written via reflection, such as fields considered non-modifiable final under the reflection specification. Even if a particular final instance field can be written via a compatibility path, the Java Memory Model, JIT, and object invariants can make post-initialization mutation unsafe.

**Do not use reflection to break invariants or mutate final fields of live objects as a default migration mechanism.**

## 6. exports and opens: decision table

| Module configuration | Calling public API from another module | Private deep reflection from another module |
|---|---|---|
| Neither exports nor opens | No, under normal access | No, absent appropriate special permissions |
| exports package | Yes, when readability and Java access are satisfied | Not automatically |
| opens package | Does not automatically grant compile-time access | May be permitted per reflection rules |
| exports + opens | Yes | May be permitted |
| exports package to module X | Public access for X | Does not automatically open private members |
| opens package to module X | Does not automatically grant compile access | Deep reflection for X per rules |
| open module | Packages are opened for deep reflection | Does not automatically turn all packages into exported source API |

In library systems, a package may only need to be accessible to a serializer or ORM framework. Instead of opening the entire module, use **qualified opens** when the framework and deployment allow it.

## 7. Practical JPMS module example

Suppose a module contains the model:

~~~text
domain/
  src/main/java/
    module-info.java
    com/example/domain/api/Customer.java
~~~

Contents of module-info.java:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.api to com.example.inspector;
}
~~~

Class Customer:

~~~java
package com.example.domain.api;

public final class Customer {
    private final String code;

    public Customer(String code) {
        this.code = code;
    }

    public String displayName() {
        return "Customer";
    }
}
~~~

Module using reflection:

~~~text
inspector/
  src/main/java/
    module-info.java
    com/example/inspector/Main.java
~~~

module-info.java:

~~~java
module com.example.inspector {
    requires com.example.domain;
}
~~~

Main.java:

~~~java
package com.example.inspector;

import com.example.domain.api.Customer;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("C-001");

        Field field = Customer.class.getDeclaredField("code");
        field.setAccessible(true);

        System.out.println((String) field.get(customer));
    }
}
~~~

In this example, exports lets inspector compile against the public Customer class. opens lets inspector perform deep reflection on the private field code. If the opens line is removed and the two classes remain in two different named modules, the setAccessible(true) call can fail.

Note: the module name declared in qualified opens must match the actual module name of the code receiving access. If the framework runs as an unnamed module or the module name changes, the configuration must reflect that topology.

## 8. JVM flags --add-opens and --add-exports

When the module descriptor cannot yet be modified or a transitional measure is needed, the runtime can accept additional options.

### 8.1. --add-opens

Example:

~~~bash
java --add-opens=com.example.domain/com.example.domain.api=com.example.inspector \
     --module-path mods \
     --module com.example.inspector/com.example.inspector.Main
~~~

The syntax opens a source module's package to the specified target module. A slash separates the module from the package, and an equals sign separates the set of modules granted access. This is an illustrative example; adjust the module path and entrypoint for your project.

If a framework runs on the classpath as part of the unnamed module, it is common to see:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

ALL-UNNAMED grants access to all corresponding unnamed modules; this is a broad permission that should be carefully evaluated before use in production.

### 8.2. --add-exports

Example:

~~~bash
java --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED -jar app.jar
~~~

--add-exports permits access to public types/members of a package that is not normally exported, subject to Java access limits. It does **not automatically** permit deep reflection into private fields.

### 8.3. Comparison

| Option | Primary purpose | Does not guarantee |
|---|---|---|
| --add-exports | Opens public access of a package to the target module | Access to private members via setAccessible |
| --add-opens | Opens a package for deep reflection by the target module | Stability of internal APIs or safety of mutating private state |
| --add-reads | Adjusts a module readability relationship when needed | Automatically exporting or opening packages |

Not every error can be solved with a single flag type. Check the JVM error message to see whether reads, exports, or opens is missing.

### 8.4. Use flags only as a transitional measure

When adding a runtime flag, record:

- Target package and module.
- Dependency or plugin requiring access.
- JDK and library versions in use.
- Risks and why the library cannot be upgraded immediately.
- Tracking owner and removal milestone.
- Tests proving the app works once the flag is removed after upgrading the dependency.

Do not open internal packages wholesale just to "make the app run". A package may contain sensitive information, and opens grants deep reflection capabilities to targets in the specified module.

## 9. Impact of strong encapsulation across Java versions

For codebases moving from Java 8 to modern JDKs, a major change is stricter control over access to internal JDK packages.

Key milestones:

| Milestone | Impact on reflection |
|---|---|
| Java 8 | No JPMS yet; many legacy libraries relied on access to internals |
| Java 9 | JPMS, exports/opens, and warnings about illegal reflective access in applicable scenarios |
| Java 16 | Strong encapsulation became the default as the JDK evolved |
| Java 17 | JEP 403 reinforced strong encapsulation for JDK internals; do not rely on legacy relaxed encapsulation |
| Java 21 and later | Integration must be designed around public APIs, module boundaries, and supported library versions |

The --illegal-access option was once used during the transition period, but it is no longer a reliable strategy on modern JDKs. For Java 17 and later, consult the target JDK version guide and prioritize upgrading libraries or replacing internal access paths.

Certain critical internal APIs, such as those in jdk.unsupported, have their own policies. The fact that an internal API still exists **does not mean** it carries stability guarantees equivalent to a Java SE API.

## 10. What are MethodHandles?

The java.lang.invoke package provides the method handle mechanism. A MethodHandle represents an invocation to a method, constructor, or corresponding operation that the JVM can execute.

Specifically:

- java.lang.reflect.Method is an object describing a method and has Method.invoke to invoke it via reflection.
- MethodHandle is a callable object with a defined **method type**, which can be composed via adapters in java.lang.invoke.
- MethodHandles.Lookup is **an object carrying an access-checking context** used to look up method handles and certain other handle types.

Common components:

| Component | Role |
|---|---|
| MethodHandle | Callable reference to a method/constructor or combinator |
| MethodType | Return type and JVM parameter types of a handle |
| MethodHandles.Lookup | Lookup context with corresponding access privileges |
| MethodHandles.lookup() | Caller-bound lookup whose privileges are based on the call site |
| MethodHandles.publicLookup() | Lookup for accessible public members |
| MethodHandles.privateLookupIn() | Creates a lookup with private access to a target class when permitted |
| VarHandle | Handle for read/write/atomic operations on variables |
| findVirtual | Finds an instance method |
| findStatic | Finds a static method |
| findConstructor | Finds a constructor |
| findGetter/findSetter | Finds a field accessor subject to access rules |
| unreflect | Converts a Method into a MethodHandle if permissions allow |

**MethodHandle is not "reflection without permissions".** Access permissions are checked when looking up/creating the handle, and a created handle carries the capability to invoke the corresponding member. Therefore, do not accidentally pass a full-privilege lookup or sensitive handle to an untrusted plugin.

## 11. MethodHandle example with a public method

Suppose there is a class:

~~~java
public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Using MethodHandle:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class PublicHandleDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle greet = lookup.findVirtual(
            Greeter.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );

        Greeter receiver = new Greeter();
        String message = (String) greet.invokeExact(receiver, "Lan");
        System.out.println(message);
    }
}
~~~

Explanation:

1. findVirtual looks up the instance method greet on Greeter.
2. MethodType specifies the String return type and a single String parameter of the method.
3. When invoking an instance handle, the Greeter receiver is passed as the first argument of the invocation.
4. invokeExact requires the call-site signature to match the handle's type exactly.
5. In the example, main declares throws Throwable because the invocation can throw a Throwable from the target method or from the invocation mechanism.

In real Java source code, these two public classes must be placed in separate files or have their visibility adjusted according to the project structure.

### 11.1. invokeExact, invoke, and asType

Three easily confused operations:

| Operation | Meaning |
|---|---|
| invokeExact | Requires the call-site method type to match exactly |
| invoke | Allows certain valid type conversions under method handle invocation rules |
| asType | Creates an adapter handle for a convertible method type |

For example, the receiver variable of invokeExact must have a static type matching the handle signature. If Object is used instead of Greeter at the call site while the handle expects Greeter, the JVM can throw WrongMethodTypeException.

Using invoke does not remove all type restrictions; conversions are still governed by MethodHandle API rules.

### 11.2. Method handles are not guaranteed to always be faster than reflection

The JVM can optimize method handles well in certain situations, especially when the handle and call site are stable. However, results depend on workload, JDK, caching strategy, inlining potential, allocation, warm-up, and conversion overhead.

Do not choose MethodHandles solely on the assumption that speed is always higher than Method.invoke. First select the API based on technical requirements, contracts, and access permissions; benchmark afterward under realistic workloads.

## 12. MethodHandles.Lookup and privateLookupIn

### 12.1. Lookup carries the caller's privileges

MethodHandles.lookup() returns a lookup bound to the calling class. Its access capabilities reflect the caller's scope and current module conditions.

MethodHandles.publicLookup() is more restricted, suitable when you only need to look up accessible public members.

A lookup is not an all-powerful token: it does not automatically grant permission to read private members of arbitrary classes in the JVM.

### 12.2. privateLookupIn

privateLookupIn is the API used when a Lookup with private access to a target class is needed, **if JVM access conditions permit it**.

Example within the same module:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class PrivateLookupDemo {
    private static final class Session {
        private String state = "NEW";
    }

    public static void main(String[] args) throws Throwable {
        Session session = new Session();

        MethodHandles.Lookup privateLookup =
            MethodHandles.privateLookupIn(
                Session.class,
                MethodHandles.lookup()
            );

        VarHandle stateHandle = privateLookup.findVarHandle(
            Session.class,
            "state",
            String.class
        );

        String current = (String) stateHandle.get(session);
        System.out.println(current);
    }
}
~~~

The example focuses on the lookup mechanism. For a private nested class in the same code/module, access can already be granted; here, using privateLookupIn primarily serves to demonstrate the API.

### 12.3. Across module boundaries

If the lookup belongs to module A and the target class belongs to module B, privateLookupIn imposes requirements on lookup privileges and on the target package being opened to the calling module, along with other access conditions per the Java Platform documentation. For example, B's package has qualified opens to A:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.api to com.example.inspector;
}
~~~

Then inspector may be permitted to obtain a private lookup into a class in the api package. If opens is removed and there is no other valid permission path, privateLookupIn can throw IllegalAccessException.

Distinguish the errors:

- setAccessible(true) typically reports InaccessibleObjectException when the override cannot be enabled.
- privateLookupIn typically reports IllegalAccessException if lookup privileges or module openness are not satisfied.

Do not try privateLookupIn as a way to circumvent JPMS encapsulation rules; it is designed to **obey** those boundaries.

### 12.4. Do not distribute broadly privileged Lookup instances carelessly

A Lookup with private access is a sensitive capability. If a framework hands this lookup to an external plugin, the plugin could gain access to many unintended members.

Provide purpose-specific method handles or a public facade instead of passing a highly privileged lookup to uncontrolled code. Limiting capabilities helps preserve internal boundaries even when plugins run in the same JVM.

## 13. VarHandle and how it differs from Field

VarHandle is designed to operate on variables through access modes. Example:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1);
    }
}
~~~

The snippet illustrates looking up a VarHandle for an instance field and using getAndAdd. A volatile field together with a VarHandle operation fits a simple concurrent counter case.

VarHandle supports multiple access modes related to:

- get, set.
- volatile access.
- acquire/release semantics.
- compareAndSet and atomic updates when supported by the variable type and access mode.
- Type-specific operations.

VarHandle does not automatically open private access across modules. The findVarHandle step still requires a Lookup with valid permissions.

### 13.1. When to use Field, MethodHandle, or VarHandle?

| Need | Typically appropriate tool |
|---|---|
| Reading annotations, field names, generic metadata | Core reflection |
| Dynamically looking up/invoking a method with a known signature | MethodHandle |
| Creating an object via a runtime-selected constructor | Constructor reflection or MethodHandle |
| Controlled atomic/ordering operations on variables | VarHandle |
| Normal access within the same codebase | Direct Java method/field access |
| Plugin needing a stable extension point | Public API/SPI, without relying on private reflection |

Do not replace every Field with VarHandle or every Method with MethodHandle if code primarily uses metadata. Each abstraction has its own strengths and rules.

## 14. Migrating from Method reflection to MethodHandle

Traditional reflection example:

~~~java
java.lang.reflect.Method method =
    Greeter.class.getMethod("greet", String.class);

String result = (String) method.invoke(new Greeter(), "Lan");
~~~

When using Method.invoke, exceptions thrown by the target method are typically wrapped in InvocationTargetException. Error-handling code must know how to unwrap the cause.

With MethodHandle:

~~~java
MethodHandle handle = MethodHandles.lookup().findVirtual(
    Greeter.class,
    "greet",
    MethodType.methodType(String.class, String.class)
);

String result = (String) handle.invokeExact(new Greeter(), "Lan");
~~~

Method handle invocation has its own Throwable throwing and type rules; it does not automatically wrap target method exceptions the way Method.invoke does.

### 14.1. Differences to consider when migrating

- The signature of invokeExact is checked strictly at the call site.
- MethodHandle must be created using a lookup with appropriate permissions.
- Invocation exceptions may differ from Method.invoke's wrapping behavior.
- Adapters and conversions must be designed intentionally.
- Member lookup can report NoSuchMethodException or IllegalAccessException.
- Caching handles can reduce lookup overhead on hot paths.
- Using MethodHandles does not automatically remove module access restrictions.

A safe refactoring should have contract tests verifying that results, exceptions, side effects, and concurrency behavior match the old reflection path.

## 15. Common errors when upgrading the JDK

### 15.1. InaccessibleObjectException

Example error form:

~~~text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang" to unnamed module
~~~

The cause is typically a library calling setAccessible(true) on a private member in an unopened package.

Remediation steps:

1. Identify the caller library from the stack trace.
2. Identify the encapsulated module/package.
3. Check whether a newer library version supports the target JDK.
4. Replace the deep reflection path with a public API when possible.
5. If forced to use --add-opens temporarily, record the scope and removal milestone.

### 15.2. IllegalAccessException

Can occur with reflection or method handle lookup when access permissions are insufficient. Do not guess that adding opens solves every IllegalAccessException; check member visibility, lookup class, readability, exports, and private lookup conditions.

### 15.3. IllegalAccessError

A linkage/runtime access-level error, often encountered when bytecode references a type or member that the current runtime does not allow accessing. This differs from the checked IllegalAccessException thrown by some reflection/lookup APIs.

### 15.4. NoSuchFieldException or NoSuchMethodException

Possible causes are that the name, signature, or member changed; this can happen when a framework relies on implementation details. If a supported public API changed, migrate following official guidance. Do not open modules to look for a member that no longer exists.

### 15.5. WrongMethodTypeException

Usually related to a MethodHandle call-site signature mismatch. Inspect receiver type, return type, primitive boxing/unboxing, arity, and adapters.

### 15.6. UnsupportedClassVersionError

Occurs if the bytecode of a dependency or plugin requires a newer Java runtime than the one running. The --add-opens flag cannot fix class-file version errors.

### 15.7. ServiceConfigurationError or ClassCastException

In framework/plugin systems, these can relate to service registration, classloaders, module layers, type identity, or dependency versions. They are not necessarily setAccessible errors.

Accurate error classification helps avoid adding unnecessary JVM flags.

## 16. How are frameworks and annotation processors affected?

Many frameworks rely on reflection to:

- Instantiate objects via non-public constructors.
- Set fields when deserializing JSON/XML.
- Map ORM entities.
- Generate proxies or invoke lifecycle callbacks.
- Read annotations and generic metadata.
- Perform dependency injection.
- Run mock/test instrumentation.
- Discover service providers or plugins.

When a framework reflects on classes in an **application module**, it is often necessary to open the application package to the framework module. When a framework reflects on **JDK internals**, the root cause may instead be a framework/agent version not yet compatible with the newer JDK.

The two directions require different handling:

| Access direction | Example | Preferred handling |
|---|---|---|
| Framework → application private member | ORM reading entity fields | Open package to the right framework or change mapping |
| Application → framework internals | Using framework private fields | Use supported framework API/SPI |
| Legacy library → JDK internals | setAccessible on java.base internals | Upgrade/replace library, avoid long-term flags |
| Annotation processor → compiler internals | javac implementation API | Upgrade processor to match compiler |
| Test agent → internals/class loading | Mock/profiler instrumentation | Upgrade agent and test on target JDK |

Do not look only at stack trace lines in application code. An error can originate from a transitive dependency or a Java agent launched before the application.

## 17. Reflection with the JDK compiler, annotation processing, and tooling

Some annotation processors, Lombok-like tooling, or code-generation plugins may depend on javac implementation classes. When upgrading the build JDK, those tools can hit access errors even if the production runtime stays the same.

Separate:

- **Build tool JDK:** the JVM running Maven/Gradle.
- **Compiler JDK:** javac processing the source.
- **Release target:** syntax/API/class-file version targeted by the artifact.
- **Production JDK:** the JVM executing the application.
- **Processor/plugin runtime:** where the processor/plugin executes.

For example, configuring --release 17 does not mean an annotation processor runs in a JDK 17 environment if the compiler toolchain is JDK 21. The processor runs inside the corresponding compiler context, so it can be affected by changes to javac internals.

The preferred solution is upgrading the processor/plugin to a version that supports that compiler. Adding --add-exports for internal javac packages is only a temporary measure once risks are understood and the scope of application is constrained.

## 18. Classpath, module path, and plugin loaders

JPMS further complicates migration when an application has multiple classloaders or ModuleLayers.

### 18.1. Unnamed module

JARs on the traditional classpath generally belong to the unnamed module of their corresponding classloader. When an error says "to unnamed module", the caller may be the application or a library running on the classpath, rather than a named module.

The ALL-UNNAMED flag targets the set of unnamed modules; it does not mean opening the package to a specific named module.

### 18.2. Named module

When using the module path, module-info.java can explicitly specify requires, exports, and opens. Qualified opens for a framework module helps limit the scope of deep reflection.

### 18.3. Automatic module

A JAR without an explicit module descriptor can be placed on the module path as an automatic module, with access characteristics different from an explicit named module. Do not guess the module name from the filename when configuring opens; verify it using tools or runtime resolution.

### 18.4. Plugin isolation

A plugin may use its own classloader, so:

- Same class name in different loaders can be two distinct types.
- A lookup created in one module/loader does not automatically have rights into another module/loader.
- ServiceLoader and the context classloader affect discovery.
- ModuleLayer can establish its own boundaries and resolution paths.
- The module name targeted by qualified opens must match where the reflection code actually runs.

When testing reflection issues, reproduce a classloader/module path topology matching production. A unit test on a flat classpath may not surface failures occurring in the real plugin host.

## 19. Security and limits of opening reflective access

Even though reflection is a legitimate Java tool, opening permissions should not be done indiscriminately. Some principles:

1. Open only the necessary packages; do not open the entire module without reason.
2. Prefer qualified opens when deploying with named modules and knowing the target module.
3. Avoid passing highly privileged MethodHandles.Lookup instances to untrusted plugins.
4. Do not read/write private secrets merely because the tooling allows it.
5. Do not use --add-opens as a substitute for business authorization checks.
6. Evaluate third-party libraries and Java agents before granting runtime permissions.
7. Track runtime flags in deployment configurations and migration documentation.

Module encapsulation **is not a complete security sandbox** for running malicious code in the same process. A truly untrusted plugin may require isolation in a separate process/container and a clear API protocol. Conversely, opening modules does not solve authentication, authorization, or secret handling issues either.

## 20. Reflection in native image or AOT

An application running on the JVM with dynamic reflection may require additional configuration when moving to a native image or Ahead-of-Time compilation environment.

Depending on the AOT/native image tool and framework, accessing a class or method by dynamic name may need metadata or hints to be included in the binary. Opening a package via JPMS does not automatically guarantee the build tool sees every reflection point.

Therefore, when a migration combines upgrading the JDK and changing the packaging model, distinguish:

- Java access/module openness errors.
- Missing native image reflection metadata errors.
- Errors where classes/resources are omitted from the artifact.
- Dynamic proxy, JNI, or service provider registration errors.

Each group has its own remediation; do not attribute everything to setAccessible.

## 21. Diagnostic tools worth knowing

### 21.1. Inspecting a JAR's module

~~~bash
jar --describe-module --file library.jar
~~~

Helps inspect the module declaration or module information associated with an artifact.

### 21.2. Inspecting JDK modules

~~~bash
java --describe-module java.base
~~~

Allows checking which packages are exported/opened according to the running JDK's module declarations.

### 21.3. Inspecting module resolution

~~~bash
java --show-module-resolution --module-path mods \
     --module com.example.app/com.example.Main
~~~

Useful for checking which modules are resolved in a module path layout.

### 21.4. Using jdeps to inspect JDK internals

~~~bash
jdeps --jdk-internals app.jar
~~~

When also analyzing dependencies:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

jdeps can detect static bytecode references to internal APIs. It does not automatically detect all string-based reflection paths or dynamically loaded classes, so inspect both source code and runtime logs.

### 21.5. Checking the actual JVM configuration

Record the startup command and JVM options across:

- Shell scripts.
- Docker entrypoints or container images.
- Kubernetes deployments.
- Service managers.
- Maven/Gradle test JVM arguments.
- IDE run configurations.
- Application servers.
- Java agent initialization.

An application that runs locally thanks to --add-opens can fail in production if the flag is not deployed accordingly. Conversely, a leftover flag left by accident can mask an unresolved internal dependency.

## 22. Migration workflow for reflection errors

### Step 1 — Identify the actual configuration

Record:

- JDK distribution and version.
- Build JDK, compiler/toolchain, and release target.
- Runtime classpath/module path.
- Application module declaration.
- Framework/agent versions.
- JVM arguments.
- Runtime scenario triggering the error.

### Step 2 — Read the full stack trace

Identify:

- What is the exact exception?
- Which class/member is being accessed?
- What are the source module and target module?
- Is the package missing exports or opens?
- Who is calling setAccessible or privateLookupIn?
- Does the code belong to the application, framework, plugin, or a JDK internal dependency?

Do not change JVM flags based on a truncated error snippet missing the caller or module.

### Step 3 — Classify the access path

| Access path | Preferred solution |
|---|---|
| Calling another module's public API | Check requires, exports, and dependencies |
| Framework reflection on application models | Open the appropriate package to the framework, if allowed by the contract |
| Application reflection on framework private members | Find a public API/SPI alternative |
| Dependency calling JDK internals | Upgrade dependency/agent to a JDK-supported version |
| MethodHandle lookup failure | Check lookup class, permissions, method type, and module openness |
| Missing Native/AOT metadata | Add AOT configuration per framework, not just opens |

### Step 4 — Prioritize fixing design or dependencies

If the library already has a release without internal API usage, upgrade the library. If a public facade or SPI exists, move to that contract. If a framework needs reflection on application models, opening the right package is a legitimate configuration.

Use --add-opens/--add-exports only temporarily if needed to keep the service running during transition and with a removal plan.

### Step 5 — Test on the exact JDK/module layout

Tests should cover:

- Startup and dependency injection.
- Deserialization/serialization.
- ORM mapping and database access.
- Proxies, aspects, dynamic invocation.
- Annotation processing, generated code.
- Test/mocking frameworks.
- Java agents and tracing.
- Plugin discovery/loading/callbacks.
- Error branches and cleanup.

### Step 6 — Confirm no unnecessary flags remain

After upgrading libraries and fixing code, try running the application on staging with a minimal list of runtime flags. If a flag is still needed, know specifically why and who is responsible for removing it.

### Step 7 — Document decisions

A migration record can use this template:

~~~text
APPLICATION / MODULE
  App:
  Build JDK:
  Target runtime JDK:
  Classpath or module path:
  Framework/agent version:

ACCESS FAILURE
  Exception:
  Caller class/module:
  Target class/module/package:
  Member and access type:
  Stack trace reference:

ROOT CAUSE
  Public API / internal API / reflection:
  Missing readability / exports / opens:
  Dependency version:
  Temporary JVM option:

RESOLUTION
  Public API replacement:
  Library/agent upgrade:
  Module-info change:
  JVM option removal milestone:
  Owner:

VALIDATION
  Compile:
  Reflection integration test:
  Framework test:
  Plugin/classloader test:
  Runtime smoke test:
  Deployment/rollback:
~~~

## 23. Common misconceptions

### "setAccessible(true) makes every private member accessible"

Incorrect. The JVM enforces permissions and module boundaries; deep reflection across a module boundary generally requires the package to be open.

### "exports is equivalent to opens"

Incorrect. exports primarily serves public access, whereas opens serves deep reflective access. A package can be opened without being exported.

### "MethodHandles bypasses JPMS"

Incorrect. MethodHandles.Lookup carries the caller's permissions, and privateLookupIn is subject to module openness conditions.

### "trySetAccessible returning false means the member does not exist"

Incorrect. The member may exist while the caller is not granted permission to enable the override.

### "Opening a module fixes the dependency"

Incorrect. Runtime flags only alter access permissions; internal APIs can still change or disappear in future JDKs.

### "A public class is a stable public API"

Incorrect. Public is visibility, not a support policy. Check documentation and support contracts.

### "MethodHandle is always faster than reflection"

There is no general guarantee. Performance depends on how handles are created/cached, call-site types, and actual workloads.

### "A successful build means there are no reflection errors left"

Incorrect. Most reflection errors appear when a framework or plugin exercises specific runtime paths.

### "No jdeps warnings means full compatibility"

Incorrect. Dynamic reflection, class loading by name, and configuration-driven paths may not be fully analyzed statically.

## 24. Key takeaways

When migrating code involving reflection, answer five questions:

1. **Who is accessing whom?** Identify the caller, target class, member, and module.
2. **Is it a public invocation or deep reflection?** Choose the right access rules.
3. **What permission is missing?** requires/readability, exports, opens, or specific MethodHandles.Lookup privileges?
4. **Is internal access truly necessary?** Prioritize supported APIs/SPIs or upgrading dependencies.
5. **Has it been verified on the target runtime?** Run integration tests with the actual classloader/module layout and JVM options.

setAccessible, MethodHandles, and JPMS are not three independent mechanisms. They meet at the same boundary: **who is permitted to see and operate on which members of a module**. Understanding this boundary properly helps the team distinguish compile errors from runtime errors, configure opens with the right scope, avoid depending on JDK internals, and maintain a more sustainable Java upgrade path.