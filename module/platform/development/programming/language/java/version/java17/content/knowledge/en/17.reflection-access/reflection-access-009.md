# Keep API Contracts, Not JDK Internal Structures

Reflection allows a Java program to inspect information about classes, constructors, fields, methods, and annotations, and invoke members dynamically. This capability is useful for dependency injection, serialization, mapping, plugins, test frameworks, and many foundational libraries. Yet **being able to see a member via reflection does not mean that member is a supported API for applications to depend on long-term**.

Java distinguishes specified public APIs from internal implementation details. Field names, implementation classes, method order, inheritance hierarchy structure, or private members of the JDK can change across versions, vendors, or implementations. The Java Platform Module System (JPMS) also draws an even clearer boundary between packages exported for normal access and packages opened for deep reflection.

With Java 17, the practical rule is: **design against public API contracts; use reflection to discover published contracts; open deep access only for packages your application truly needs; never turn JDK internal structures into a product dependency**.

## 1. Public API and implementation details are two different things

An API is a contract a provider publishes for users to call. That contract specifies the supported types, methods, parameters, results, exceptions, and behavior. Implementation details are how the library carries out that contract internally.

Example with collections:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
~~~

The application depends on the List contract: adding elements, reading elements, and getting the size. It does not need to know that ArrayList stores elements in an internal array named elementData, how capacity grows, or what other fields exist.

Good design:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
~~~

Fragile design:

~~~java
Field field = ArrayList.class.getDeclaredField("elementData");
field.setAccessible(true);
Object[] internalArray = (Object[]) field.get(names);
~~~

The second snippet relies on a private field name and the storage mechanism of a specific implementation. Another JDK could rename the field, change the structure, enforce module boundaries, or alter access rules. The application can also inadvertently depend on capacity, layout, and allocation timing details that the List API never promised.

### What makes up an API contract?

When using a library, distinguish:

| Element | Can it be part of the contract? | How to evaluate |
| --- | --- | --- |
| Public types documented in Java SE | Yes | Rely on Java API specification/Javadoc |
| Public methods in exported packages | Usually yes, if documented and supported | Check module, documentation, and compatibility policy |
| Annotations published by a library | Possibly yes | Follow the annotation's intent and retention/target |
| Published interfaces/SPIs | Yes | Implement according to contract and lifecycle rules |
| Private fields/methods of JDK classes | No | Implementation details, do not rely on them |
| Class names in internal JDK packages | Not a stable Java SE API | Avoid depending on them |
| Return order of getDeclaredFields() | Not guaranteed | Do not use as serialization order or logic |
| Compiler-generated synthetic fields | No | Do not assume existence or fixed names |
| How a collection/stream is internally optimized | No | Measure through published APIs, do not read implementation internals |

A member having the public modifier is not guaranteed to be a public API accessible from another module. If the package is not exported, the module system can block ordinary access. And even when reflection can observe a class name, that creates no compatibility commitment for that class.

## 2. Public Java API vs JDK internals

Java SE publishes foundational APIs such as java.lang, java.util, java.time, java.net, java.nio.file, and many other packages. These APIs are documented in the Java SE specification/Javadoc. The JDK also contains packages for implementation, tooling, or runtime internals.

For example, when you need to:

- Work with files and directories: use java.nio.file.Path, Files, FileSystem.
- Work with processes: use ProcessBuilder and ProcessHandle.
- Work with dates and times: use java.time.
- Send HTTP requests: use java.net.http.HttpClient.
- Inspect threads, memory pools, and GC metrics at a published management level: see java.lang.management and ManagementFactory.
- Work with sockets: use java.net or java.nio.channels.

Do not access private/internal classes merely because they happen to do what the application wants. Public APIs generally provide more stable behavior, documentation, and substitutable implementations.

### Why are internal packages not APIs for applications to depend on?

A JDK may contain packages such as jdk.internal.* or other implementation classes to run the runtime. They can:

- Have their packages renamed or moved.
- Change class and field structures.
- Change algorithms or how state is stored.
- Not be exported by their containing module.
- Have reflective access restricted by the module system.
- Disappear or change across JDK releases and vendors.

If an application depends on such elements, upgrading the JDK can prevent the application from compiling, prevent startup, or throw runtime access errors. This is a sign that the design depends on implementation rather than contract.

### sun.* and jdk.internal.* are not substitutes for public APIs

Package names alone do not tell the whole support story, yet applications should not treat internal packages as Java SE APIs. Some historical internal packages remain for special compatibility purposes; their existence does not mean new applications should depend on them.

Do not choose a class in sun.* or jdk.internal.* just because it has a more convenient method than the published API. If you need functionality not yet in a public API, evaluate a supported library, redesign your abstraction, or explicitly isolate implementation limits; never assume an internal API is a long-term contract.

## 3. Java Platform Module System and access boundaries

Since Java 9, applications can be organized into modules. Each module declares its dependencies and exposed packages in module-info.java.

Three concepts to distinguish:

- **Readability**: whether a module can read another module, typically via requires.
- **Exports**: packages exposed for ordinary access to public types/members.
- **Opens**: packages permitting deep reflection at runtime.

### exports for ordinary access

Library module:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Application module:

~~~java
module com.example.application {
    requires com.example.domain;
}
~~~

The application can import and call public types in com.example.domain.api. Other packages of the domain module are not automatically exposed.

exports does not mean every private field in the package can be accessed via reflection. It publishes the public API under module rules, without opening the entire implementation.

### opens for deep reflection

A framework may need to access non-public constructors or fields of application classes. If the application module controls that package, it can open only that package to the specific framework module:

~~~java
module com.example.application {
    requires com.example.framework;

    opens com.example.application.persistence
            to com.example.framework;
}
~~~

opens permits deep reflection into the package at runtime for the specified target module. It does not replace exports for another module to import public types in that package as an ordinary API.

### Qualified exports and qualified opens

Recipients can be restricted:

~~~java
module com.example.model {
    exports com.example.model.api
            to com.example.application;

    opens com.example.model.persistence
            to com.example.orm;
}
~~~

In this example:

- com.example.application can access the public API in package com.example.model.api.
- com.example.orm is allowed deep reflection into package persistence.
- Other modules do not gain those permissions merely by knowing the package names.

This narrows access instead of opening the entire module.

### Broad scope of open module

Declaration:

~~~java
open module com.example.model {
    requires com.example.framework;
}
~~~

Opens all packages of the module for deep reflection. It does not automatically export all packages for normal Java access. Only use this when a framework truly needs broad scope and the module owner accepts that contract; whenever possible, open specific packages via opens p to m.

## 4. Strong encapsulation in Java 17

Java 17 enforces strong encapsulation for JDK internal components per JEP 403. Mechanisms that relaxed internal access in transitional releases are no longer a reliable foundation for applications.

Before the module system, many libraries used reflection to access private members of the JDK. Starting in Java 9, module boundaries were progressively enforced; Java 16 made strong encapsulation the default, and Java 17 continues closing those boundaries by default.

Practical consequences:

- Reflection on private members of unopened JDK packages can fail.
- setAccessible(true) can throw InaccessibleObjectException.
- trySetAccessible() can return false.
- Older libraries may run on earlier JDKs yet fail when upgrading to Java 17.
- Do not resolve errors by unconditionally opening all internal JDK packages.

### --illegal-access is not a solution for Java 17

In transitional JDKs, the --illegal-access option controlled compatibility modes for reflective access into certain internal packages. From Java 17 onward, this option no longer restores that relaxed mechanism; it is retained only for launch compatibility and emits warnings, without reopening closed JDK packages for arbitrary deep reflection.

Therefore, do not add --illegal-access=permit to scripts expecting old applications to work on Java 17.

### Why upgrading libraries is usually the right direction?

If an ORM framework, serializer, dependency injection container, or mocking library tries to access private JDK members, the issue is usually an older library version that does not yet support strong encapsulation. Preferred steps:

1. Upgrade to a library version that supports Java 17.
2. Use the library's published extension/configuration APIs.
3. Adjust integration so reading JDK implementations is unnecessary.
4. Only use --add-opens on application packages you own when a framework needs deep reflection and there is a clear reason.

Opening JDK packages via JVM options can serve as a transitional measure in an evaluated legacy system, yet it creates an implementation dependency and weakens encapsulation. It does not turn internal APIs into stable contracts.

## 5. Distinguishing exports, opens, --add-exports, and --add-opens

Module declarations and launcher options serve different purposes:

| Mechanism | Time/scope | What does it allow? |
| --- | --- | --- |
| exports p; | module-info.java | Ordinary access to public types/members in package p from modules reading this module |
| exports p to m; | module-info.java | Only module m receives ordinary access |
| opens p; | module-info.java | Deep reflection into package p at runtime from other modules |
| opens p to m; | module-info.java | Deep reflection into package p for module m |
| open module x {} | module-info.java | Opens all packages of module x for deep reflection |
| --add-exports source/package=target | JVM/compiler launcher | Adds export for public types/members of the package to the target module |
| --add-opens source/package=target | JVM runtime launcher | Opens the package for deep reflection to the target module |

--add-exports does not automatically allow accessing private fields. --add-opens permits deep reflection, but is not a way to import public types from unexported packages in normal source code.

Syntax examples:

~~~bash
java --add-exports source.module/internal.package=target.module ...
java --add-opens source.module/internal.package=target.module ...
~~~

If the application runs on the classpath, target can typically be ALL-UNNAMED:

~~~bash
java --add-opens source.module/internal.package=ALL-UNNAMED -jar app.jar
~~~

This syntax illustrates module configuration. Do not use hypothetical module/package names in production; only configure specific packages after identifying which library needs permission and why.

### Why shouldn't everything be opened broadly?

An option like:

~~~bash
java --add-opens java.base/java.util=ALL-UNNAMED -jar app.jar
~~~

may let libraries on the classpath deep-reflect into package java.util within that opened runtime scope. However, the application has introduced a dependency on that package's internal structure. The JDK can change its implementation, making the application harder to upgrade.

If a framework needs this permission, identify the exact class/field being accessed, check the framework version, look for supported configuration, and narrow the opened scope. Do not add numerous --add-opens flags by trial and error until errors disappear without recording an owner and reason.

## 6. What can reflection access?

Reflection provides APIs such as:

- Class.getMethods() and getMethod(...): inspect public methods, including inherited methods.
- Class.getDeclaredMethods() and getDeclaredMethod(...): inspect methods declared directly in the class, including non-public ones if metadata observation is allowed.
- Class.getFields() and getField(...): inspect public fields, including inherited fields.
- Class.getDeclaredFields() and getDeclaredField(...): inspect directly declared fields.
- Class.getConstructors() and getDeclaredConstructors(): inspect public constructors or declared constructors.
- Class.getAnnotations() and getDeclaredAnnotations(): read annotations per inheritance/declaration rules.
- Method.invoke(...), Constructor.newInstance(...), Field.get(...), and Field.set(...): perform reflective operations when access checks allow.

Being able to obtain metadata about private members does not mean being permitted to read or modify them. **Listing metadata and permission to access members are two separate issues**.

### Public reflection does not need to break encapsulation

Example:

~~~java
import java.lang.reflect.Method;

public class PublicReflectionDemo {
    public static void main(String[] args) {
        for (Method method : String.class.getMethods()) {
            if (method.getName().equals("isBlank")) {
                System.out.println(method);
            }
        }
    }
}
~~~

String.isBlank() is a published public API. Reflection merely discovers and displays information about the public method; setAccessible(true) is unnecessary.

### getDeclaredMethods() does not guarantee order

Do not write:

~~~java
Method first = SomeType.class.getDeclaredMethods()[0];
~~~

and assume the first element is always the expected method. Java does not guarantee the order of methods/fields returned by these reflection APIs. Search by name, parameters, and return type, or better yet, use published annotations/interfaces to identify roles.

Additionally, reflection can expose bridge methods or compiler-generated synthetic members. Frameworks should check isBridge() and isSynthetic() if their contract requires processing only user-declared members.

### Fields and methods are not a public data model

If a framework serializes every field returned by getDeclaredFields(), it turns internal structure into a wire format. Renaming a field, adding a cache, or changing storage types can unintentionally alter the JSON/schema.

Define DTOs, record components, getters, or published serialization annotations as the data contract. Never infer a public schema from all implementation fields.

## 7. Using canAccess, trySetAccessible, and setAccessible properly

AccessibleObject provides APIs to control access checks:

- canAccess(object): checks whether the member can be accessed in the current context.
- trySetAccessible(): attempts to bypass Java language access checks if module boundaries permit; returns true if successful, false otherwise.
- setAccessible(true): requests bypassing access checks; can throw InaccessibleObjectException when access cannot be opened.
- setAccessible(false): restores ordinary access checking.

Example checking first:

~~~java
Field field = SomeType.class.getDeclaredField("value");

if (field.trySetAccessible()) {
    Object value = field.get(target);
} else {
    // Deep reflection is not permitted for this member.
}
~~~

The snippet above only illustrates the mechanism. In application design, if value is a private implementation field of the JDK or a third-party library, do not treat trySetAccessible() succeeding in one environment as a guarantee it will always succeed in another.

### setAccessible(true) is not a fix for every reflection error

If a package belongs to a module not opened to the caller's module, deep reflection requests can be denied. For JDK members, the application does not control that module's module-info.java. Do not try to force access through various tricks or internal APIs to bypass boundaries.

If the class belongs to the application's own module, selectively open only the necessary package:

~~~java
module com.example.app {
    opens com.example.app.model to com.example.mapper;
}
~~~

This is an intentional module declaration, easier to review and maintain than a sprawling set of launcher flags.

## 8. Using MethodHandles when more strongly typed dynamic invocation is needed

java.lang.invoke.MethodHandles provides a mechanism to look up and invoke methods/constructors/fields via MethodHandle. It is a public API for dynamic invocation scenarios, often with a clearer typing model than Method.invoke.

Example invoking a public method:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandle length = MethodHandles.publicLookup()
        .findVirtual(
                String.class,
                "length",
                MethodType.methodType(int.class));

int result = (int) length.invokeExact("Java 17");
System.out.println(result);
~~~

findVirtual looks up the public method by name and MethodType. invokeExact requires the call-site types to match the method handle type exactly. This is a public API; the example does not require accessing private JDK members.

### Lookup and access permissions

Common lookups:

- MethodHandles.lookup() creates a Lookup with permissions tied to the calling class.
- MethodHandles.publicLookup() only has public permissions within its scope.
- MethodHandles.privateLookupIn(targetClass, lookup) requires appropriate module access conditions to create a private-access lookup on the target class.

privateLookupIn is not a shortcut around JPMS. The caller module must read the target module and the target package must be opened to the caller module under module system rules. If the package is not open, the operation can throw IllegalAccessException.

### VarHandle for typed variable access

VarHandle is a public API since Java 9 for accessing variables with defined memory-ordering modes and atomic operations. When operating on fields of application-owned classes, consider VarHandle instead of plain field reflection.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleDemo {
    static final class Counter {
        private volatile int value;
        private static final VarHandle VALUE;

        static {
            try {
                VALUE = MethodHandles.lookup()
                        .findVarHandle(Counter.class, "value", int.class);
            } catch (NoSuchFieldException | IllegalAccessException ex) {
                throw new ExceptionInInitializerError(ex);
            }
        }

        void set(int newValue) {
            VALUE.set(this, newValue);
        }

        int get() {
            return (int) VALUE.get(this);
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.set(10);
        int current = counter.get();
        System.out.println(current);
    }
}
~~~

The Lookup is created inside Counter, so it has permission to access private fields of that class itself. When crossing modules or packages, corresponding access permissions and opens/exports must be satisfied. VarHandle is not a license to read arbitrary private fields of the JDK.

## 9. Designing extension points with interfaces and ServiceLoader

A common reason developers use reflection is wanting to look up implementations by class name or build plugins. Java already has a public way for many such cases: interfaces/SPI and ServiceLoader.

Define the contract:

~~~java
package com.example.spi;

public interface GreetingProvider {
    String language();
    String greet(String name);
}
~~~

Implementation:

~~~java
package com.example.english;

import com.example.spi.GreetingProvider;

public final class EnglishGreetingProvider
        implements GreetingProvider {

    public String language() {
        return "en";
    }

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

For classpath applications, the provider can be registered via file:

~~~text
META-INF/services/com.example.spi.GreetingProvider
~~~

The file content is the fully qualified provider class name:

~~~text
com.example.english.EnglishGreetingProvider
~~~

The application discovers implementations:

~~~java
ServiceLoader<GreetingProvider> providers =
        ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.greet("Lan"));
}
~~~

With named modules, declare the service in module-info.java:

~~~java
module com.example.english {
    requires com.example.spi;
    provides com.example.spi.GreetingProvider
            with com.example.english.EnglishGreetingProvider;
}
~~~

The consuming module declares:

~~~java
module com.example.application {
    requires com.example.spi;
    uses com.example.spi.GreetingProvider;
}
~~~

ServiceLoader lets the application depend on interfaces and service contracts rather than implementation class names or provider internals.

## 10. Reflection following application class contracts

Reflection remains useful when working with classes controlled by the application or framework. The key is discovering what is explicitly published: interfaces, annotations, supported constructors, record components, or methods following stable conventions.

### Use annotations instead of inferring from field names

Example annotation marking a method to invoke:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface OnStart {}
~~~

The framework can find marked methods:

~~~java
for (Method method : component.getClass().getMethods()) {
    if (method.isAnnotationPresent(OnStart.class)) {
        if (method.getParameterCount() != 0
                || method.getReturnType() != void.class) {
            throw new IllegalArgumentException(
                    "@OnStart method must have no arguments and return void");
        }
        method.invoke(component);
    }
}
~~~

The contract here is the OnStart annotation plus the method signature rule. The framework does not have to guess which method is a callback from names like startInternal, declaration order, or private fields.

If a framework needs to invoke non-public methods, explicitly decide whether that is a supported contract. You can require public methods, or require the application module to open the package containing the component to the framework. Do not silently invoke private methods merely because reflection happens to allow it in one specific setup.

### Use record components when the data type is a record

Java 17 provides the Class.getRecordComponents() API:

~~~java
record UserView(long id, String name) {}

for (RecordComponent component
        : UserView.class.getRecordComponents()) {
    System.out.println(component.getName());
    System.out.println(component.getType().getName());
}
~~~

Record components are part of a record's published contract. If a framework supports records, use record components/accessors to map data instead of arbitrarily reading internal fields.

### Do not assume every class has a no-arg constructor

Older frameworks often assumed every class had a no-argument constructor and setters for every field. Modern designs may use constructor injection, factories, builders, or record canonical constructors. Frameworks should support published object-creation contracts instead of forcing classes to mimic an internal layout.

## 11. Why is relying on field names, order, and implementation classes fragile?

Common forms of fragile dependencies:

### Depending on field names

~~~java
Field field = SomeJdkClass.class.getDeclaredField("internalState");
~~~

Field names can change without breaking any public API. Reflection finding a field today creates no guarantee for the next JDK.

### Depending on field/method order

~~~java
Field[] fields = SomeType.class.getDeclaredFields();
serialize(fields[0]);
~~~

Return order is not guaranteed. If serialization order matters, use explicit schemas, annotations, or ordering metadata.

### Depending on implementation class names

~~~java
if (value.getClass().getName().contains("ImmutableCollections")) {
    // ...
}
~~~

The JDK can change implementation classes while preserving List, Set, or Map behavior. Check contracts using APIs such as instanceof, published methods, or interface operations.

### Depending on private state for optimization

Reading capacities, locks, caches, or internal node structures can make optimizations valid only for a single JDK release. For performance, benchmark through public APIs, profile, and pick suitable data structures. Never treat a private field as an operational metric.

## 12. Public APIs replacing common needs

| Need | Public APIs to consider | Avoid depending on |
| --- | --- | --- |
| Reading/writing files, file metadata | Path, Files, BasicFileAttributes | Internal fields of file providers |
| Monitoring processes | ProcessHandle, ProcessHandle.Info | Internal JDK process classes |
| Getting time | Instant, Clock, ZonedDateTime | Clock/private runtime state |
| Sending HTTP | HttpClient, HttpRequest, HttpResponse | Internal HTTP client implementations |
| JVM management, memory pools, threads | ManagementFactory, java.lang.management | Private fields of VM implementations |
| Creating plugins | Interfaces/SPI, ServiceLoader | Scanning classpath and guessing implementations |
| Handling configuration | Published configuration APIs, records/DTOs | Reflection into private framework fields |
| Dynamic member access in code you control | Reflection/MethodHandles per contract and module access | Using internal JDK classes to bypass access checks |
| Reading record info | getRecordComponents() and accessors | Assuming compiler field layout |
| Network info | NetworkInterface, InetAddress | Private network implementation classes |

If no public API meets the requirement, clearly distinguish whether the feature is an application requirement or merely a secondary optimization. For critical requirements, consider a library with a supported contract or design a replaceable abstraction. Never build a product around a private detail just because it happens to be accessible in one JDK release.

## 13. Tools for detecting dependencies on JDK internals

The JDK provides the jdeps tool to analyze dependencies at the class/package/module level. The --jdk-internals option helps detect dependencies on internal JDK APIs in classes or JARs.

Example:

~~~bash
jdeps --jdk-internals application.jar
~~~

You can also analyze dependent libraries or the classpath as appropriate for your build structure:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

The output helps pinpoint which classes depend on internal packages and suggests replacement APIs in some cases. This is static analysis; it does not catch every reflective access built dynamically from configuration or runtime strings.

### Searching for string-based reflection in code

In addition to jdeps, you can search source code for patterns worth reviewing:

- Class.forName("...")
- getDeclaredField(...)
- getDeclaredMethod(...)
- setAccessible(true)
- trySetAccessible()
- MethodHandles.privateLookupIn(...)
- sun.* or jdk.internal.*

Not every use of reflection is a bug. The goal is to classify them:

1. Reflection on published public APIs/annotations/interfaces.
2. Reflection on application-owned classes with explicit module opens.
3. Reflection on private implementations of external libraries.
4. Reflection on internal JDK packages/members.

The first two groups can be valid designs. The latter two require evaluating library upgrades, API replacements, or dependency removal.

### Checking during JDK upgrades

In CI, include a job running on JDK 17 matching the target environment, and a step running jdeps --jdk-internals on key artifacts. Integration tests should verify that serialization, ORM, DI, and instrumentation frameworks do not rely on unexpected internal access.

jdeps does not prove an application has zero runtime internal dependencies. It is a supporting tool; combine it with source reviews, testing, and dependency governance.

## 14. Migrating older libraries to Java 17

When upgrading from an older JDK to Java 17, you may encounter:

- InaccessibleObjectException when a library calls setAccessible(true).
- IllegalAccessException when MethodHandles lack access permissions.
- NoSuchFieldException or NoSuchMethodException because a library depended on internal member names that changed.
- ClassNotFoundException or NoClassDefFoundError when an internal class no longer exists or a module is not read.
- Warnings about internal APIs during compilation or execution.

Resolution workflow:

1. Read the stack trace to identify the library and accessed package.
2. Determine whether it is a JDK internal package or an application/library package.
3. Look up a Java 17-compatible version of the library and upgrade.
4. Look for official configuration/extension points to replace deep reflection.
5. If the package belongs to an application module, open only that package to the specific framework module when genuinely needed.
6. If launcher options are unavoidable during migration, scope the package and target module tightly, and document the reason, owner, and removal deadline.
7. Run tests on Java 17 and analyze dependencies with jdeps.

Do not add --add-opens in bulk just to silence startup errors. Doing so may get the system running temporarily while leaving fragile dependencies in place and creating burden for the next JDK upgrade.

## 15. Security and trust boundaries when using reflection

Reflection can invoke methods, instantiate objects, and read data according to the permissions granted to the program. Therefore, never take class names, method names, or constructors from untrusted input and execute them directly.

Dangerous design example:

~~~java
Class<?> type = Class.forName(userSuppliedClassName);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Without an allowlist and type validation, input can select unintended implementations or trigger class initializers/constructors with side effects. Reflection is not a sandbox.

Safer design:

- Define an interface that plugins must implement.
- Register providers via ServiceLoader or a controlled registry.
- Permit only implementations on an allowlist or in trusted configuration.
- Validate types and permissions before creating objects.
- Do not open packages more broadly than required.
- Do not let external input arbitrarily choose which private methods get called.

Do not treat setAccessible(true) bypassing module or trust boundaries as an authorization mechanism. Java access control and business authorization are two distinct layers.

## 16. Module example: exporting APIs and opening packages for frameworks

Suppose there are two modules:

~~~text
com.example.app
    com.example.app.api
    com.example.app.persistence

com.example.mapper
~~~

Application module:

~~~java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.persistence to com.example.mapper;
}
~~~

Mapper module:

~~~java
module com.example.mapper {
    requires com.example.app;
}
~~~

The public API is exported to calling modules. The persistence package is opened specifically to the mapper so the framework can deep-reflect at runtime. Other packages remain closed.

This example fits when persistence objects are internal to the application and the mapper genuinely needs access to non-public constructors/fields. If the mapper supports constructor mapping or record components via public APIs, opens may not be needed.

## 17. Design checklist before using deep reflection

Before calling setAccessible, trySetAccessible, or privateLookupIn, determine:

1. Does this member belong to a documented, supported public API?
2. Is there an alternative interface, annotation, accessor, factory, or SPI?
3. Does the class/package belong to a module controlled by your team?
4. Does the target module actually need deep reflection, or only public APIs?
5. Can qualified opens be used instead of opening the entire module?
6. If the target is a JDK internal, is there a documented Java SE or JDK API that meets the need?
7. If it is an external library, is there a version supporting Java 17?
8. Is behavior tested on the target JDK/vendor?
9. Are CI checks in place to detect dependencies on JDK internals?
10. Are the reason, scope, and plan to remove any workaround documented?

Not every framework can operate without deep reflection. What matters is keeping access intentional, scoped to the right package and module, and within contracts the application can control.

## 18. Common mistakes

| Mistake | Why it is fragile | Proper approach |
| --- | --- | --- |
| Reading private JDK fields for state | Fields are implementation details | Find a public API providing the needed info |
| Relying on collection implementation class names | The JDK can change internal classes | Use interfaces and published behavior |
| Relying on getDeclaredFields() order | Order is not guaranteed | Use explicit names, annotations, or schemas |
| Calling setAccessible(true) on all fields | JPMS can block deep reflection | Open only required application packages or use public APIs |
| Using --illegal-access=permit on Java 17 | Option no longer restores legacy access | Upgrade libraries and remove internal dependencies |
| Adding numerous --add-opens for java.base | Broadly exposes JDK internals and hinders upgrades | Identify libraries, narrow permissions, or replace APIs |
| Thinking exports grants private access | Export and open have different purposes | Use scoped opens when deep reflection is needed |
| Thinking opens allows importing public types | Opens only serves runtime deep reflection | Use exports for ordinary access |
| Using reflection to load plugins from arbitrary class names | Input can select unexpected implementations | Interfaces, ServiceLoader, and allowlists |
| Using private implementations for optimization | Depends on a specific JDK's internal structure | Benchmark through public APIs |
| Assuming jdeps catches all dynamic reflection | Names can be constructed from runtime data | Combine static analysis, source review, and testing |
| Opening an entire module to a framework when only one package is needed | Grants broader deep access than necessary | Qualified opens package to module |

## 19. Practical principles

When writing reflection and access code on Java 17:

1. Rely on documented public APIs, interfaces, annotations, and SPIs.
2. Do not depend on internal JDK field names, method names, implementation classes, or member order.
3. Distinguish module readability, exports, and opens.
4. Use public reflection to discover contracts; only deep-reflect into application packages when justified and explicitly authorized by module permissions.
5. Use MethodHandles/VarHandle when dynamic invocation or variable access needs stronger typing and semantics.
6. Use ServiceLoader or registries instead of scanning for implementation classes to build plugins.
7. For Java 17 strong-encapsulation errors, prioritize upgrading libraries and removing internal dependencies.
8. Only use --add-exports/--add-opens as tightly scoped measures, never treating them as API contracts.
9. Use jdeps --jdk-internals and test on the target JDK to detect unsupported dependencies.

Reflection is a powerful tool, yet API boundaries are what decide whether an application can upgrade safely. When code depends on published behavior rather than internal structures, an application can swap JDKs, change implementations, and upgrade libraries with minimal disruption from internal runtime changes.

## Java 17 references

- [Java Language Specification, Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html)
- [AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Class reflection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
