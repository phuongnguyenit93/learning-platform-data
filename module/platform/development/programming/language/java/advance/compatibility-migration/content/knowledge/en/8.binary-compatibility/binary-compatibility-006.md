# Narrowing Access and Impact on Compiled Code

When a Java library is released, other applications may have already compiled their source code into `.class` files and packaged these files in JARs. If the vendor changes a method from `public` to `protected`, package-private, or `private`, the application's source code may no longer compile. Even without recompiling, the existing application may fail at runtime.

The reason is that access is not checked only by the compiler. The JVM also performs access checks when resolving class, field, and method references in bytecode. Narrowing access may preserve the method name and descriptor, yet render a compiled binary no longer permitted to invoke that member. A common error is `IllegalAccessError`, which belongs to `LinkageError`.

To evaluate binary compatibility, it is necessary to see who is accessing the member, from which package, whether there is an inheritance relationship, and whether the module exports that package. Then both new source consumers and already-released binary consumers must be checked.

## 1. Access Levels in Java

Java has four commonly used access levels: `public`, `protected`, package-private (no modifier written), and `private`. Each level determines which source code can access the declared member or type.

| Access Level | Same class | Same package | Subclass in another package | Unrelated class in another package |
|---|---:|---:|---:|---:|
| `public` | Yes | Yes | Yes | Yes, if module/package conditions also permit |
| `protected` | Yes | Yes | Yes, according to protected access rules | No |
| package-private | Yes | Yes | No, if the subclass is in another package | No |
| `private` | Yes, including nestmates per Java rules | No | No | No |

With `protected`, the access rules from a subclass in another package have more detailed conditions than merely being a subclass. In an instance code context, the access expression must satisfy Java's protected access rules; a subclass in another package cannot use `protected` access to arbitrarily access any instance of the superclass.

Example:

```java
package library;

public class Account {
    public String id;
    protected void calculateInterest() {}
    void refreshCache() {}
    private void validateInternalState() {}
}
```

A class in the `library` package can access package-private and protected members according to the normal rules. A class in another package can only directly access public members, or protected members in cases where it satisfies the subclass rules.

### 1.1. Which Direction Does Narrowing Access Go?

You can visualize the order of access levels from widest to narrowest as follows:

```text
public
  |
  v
protected
  |
  v
package-private
  |
  v
private
```

Changing in the downward direction can remove access that consumers previously used. Changing in the upward direction usually expands the set of consumers allowed to access it.

This diagram should not be understood to mean that every pair of levels can be changed freely in every context. For example, an overriding method must not reduce access compared to the overridden method; the compiler will reject source code that violates that rule. However, changing the modifier of a member in an already-released library can still affect subclasses or clients that were compiled beforehand.

### 1.2. Access Privileges of Classes, Constructors, and Members

Access privileges can be changed in many places:

- **Top-level class:** a public class can be referenced from another package; a non-public top-level class is only accessible within the package.
- **Nested class:** a nested class can have access modifiers, and narrowing access can prevent clients from creating or referencing that type.
- **Constructor:** a public constructor allows clients to create instances; changing it to protected, package-private, or private can block compiled `new` instructions.
- **Method:** clients may lose the permission to call a method even though its name, parameters, and return type remain the same.
- **Field:** old bytecode may no longer be able to read or write a field after its modifier is narrowed.

When changing an API, its entire public surface must be checked, not just the main business methods.

## 2. Why Can Narrowing Access Break Binaries?

The compiler and the JVM check access at two different times.

At compile time, the compiler reads the source code together with the library's API. If a method is no longer public and the client does not have access under Java rules, the compiler reports an error. This is a source compatibility error.

At runtime, the JVM loads previously compiled class files. Bytecode contains symbolic references to classes, fields, or methods, including names and descriptors. The JVM locates the corresponding member and performs an access check. If the member exists but the binary invokes it from a location that is no longer permitted, the JVM may throw `IllegalAccessError`.

The key point is that access flags reside in the metadata of the class file; they are not part of the method descriptor. Therefore, preserving the method name and descriptor is not enough to guarantee that old binaries can continue calling that method.

### 2.1. Example: Changing a public Method to protected

Suppose version 1 of the library has:

```java
package com.example.api;

public class ReportService {
    public void exportReport() {
        System.out.println("Exporting report");
    }
}
```

An application in another package calls the method:

```java
package com.example.client;

import com.example.api.ReportService;

public class Client {
    public static void main(String[] args) {
        new ReportService().exportReport();
    }
}
```

`Client` compiles successfully against version 1. Its bytecode contains a reference to `ReportService.exportReport:()V`.

In version 2, the vendor narrows the access:

```java
package com.example.api;

public class ReportService {
    protected void exportReport() {
        System.out.println("Exporting report");
    }
}
```

If `Client` is recompiled against version 2, the compiler reports an error because the client is in another package and is not a subclass permitted to access the protected method under Java rules.

If the `Client.class` file compiled against version 1 is kept unchanged and run with the version 2 JAR, the JVM may throw an error at the time the call is resolved/executed:

```text
java.lang.IllegalAccessError:
  class com.example.client.Client tried to access
  method com.example.api.ReportService.exportReport()
```

The method name, parameters, and return type are unchanged. The binary still finds the method, but no longer has permission to access it. This is an example of a change that can break binary compatibility even though the method signature remains intact.

### 2.2. Narrowing Field Access

Suppose a library has a public field:

```java
package com.example.api;

public class Settings {
    public String region = "ap-southeast-1";
}
```

A client can read it directly:

```java
String region = new Settings().region;
```

If a later version changes the field to private:

```java
public class Settings {
    private String region = "ap-southeast-1";

    public String getRegion() {
        return region;
    }
}
```

Old client source code no longer compiles because the field is inaccessible. The old binary still references the field with the old name and descriptor, but when the JVM checks access permissions, the field read instruction may fail with `IllegalAccessError`.

Adding a new getter does not automatically fix already-released binaries. The old binary was compiled to read the field directly; it does not automatically redirect calls to `getRegion()`. Consumers need to be recompiled or the vendor needs to keep a compatible surface during the transition period.

### 2.3. Narrowing Constructor or Class Access

Constructors are also members with access privileges. If a class previously provided a public constructor and later changes it to protected or private, an old client with a compiled `new` instruction may encounter `IllegalAccessError` when the JVM checks permission to invoke the constructor.

Similarly, changing a top-level class from public to package-private can prevent binaries outside the package from having permission to use that class. Keeping the class name and class file does not mean all old consumers can still access it.

For nested classes, the permissions of both the enclosing class and the nested class must be checked. A client may lose access even though the nested class still exists in the JAR.

## 3. Errors That Can Occur When Access Is Narrowed

The specific message depends on the member kind, when the JVM resolves the reference, and the application's execution path. Common cases include:

| Narrowed component | Old binary situation | Potential error |
|---|---|---|
| Public method | Client outside package continues calling method changed to protected/private/package-private | `IllegalAccessError` |
| Public field | Client outside permitted scope continues reading/writing field | `IllegalAccessError` |
| Public constructor | Client continues instantiating using constructor whose access was narrowed | `IllegalAccessError` |
| Public class or nested type | External binary continues referencing type that is no longer public | `IllegalAccessError` during type resolution/access |
| Package export in module | Client module references package no longer exported to it | Linkage access error, usually `IllegalAccessError` |
| Reflection access | Framework uses reflection to look up or invoke member no longer accessible the old way | `NoSuchMethodException`, `IllegalAccessException`, or module-related error such as `InaccessibleObjectException`, depending on the operation |

`IllegalAccessError` is a `LinkageError`, different from compile-time errors like `cannot access` or `has protected access`. It is also different from `NoSuchMethodError`: that error usually means the JVM could not find a method with the name and descriptor requested by the binary. When narrowing access while keeping the member, the issue is usually that the member is found but access is no longer valid.

Not all errors appear immediately at application startup. The JVM may resolve a reference only when the corresponding execution path is run. Therefore, an application that starts up successfully can still fail when calling a rarely used API.

## 4. Distinguishing Java Access from Module Access

Since Java 9, the module system adds a layer controlling module readability and access to exported/open packages. A class or method with the `public` modifier can still be inaccessible from another module if the package containing it is not appropriately exported.

Example in `module-info.java`:

```java
module com.example.library {
    exports com.example.api;
}
```

The client module needs to read the library module and the API package needs to be exported. If the vendor removes the `exports` directive or moves the package to a module not read by the client, old binaries may encounter access errors when linking or using that public type.

### 4.1. `exports` and `opens` Serve Different Purposes

- `exports` allows other modules to access public types in the exported package according to module rules.
- `opens` allows deep access via reflection into the package, including non-public members within the permitted scope.

These two mechanisms do not replace each other. A framework calling normal public APIs needs the package to be exported. A framework using reflection to access private fields may need the package to be opened. Merely adding `opens` does not automatically make all normal bytecode calls valid.

JVM options such as `--add-exports` and `--add-opens` can be used as controlled transitional measures in their respective situations. `--add-exports` supports access to public types in the specified package; `--add-opens` supports deep reflection. They should not be used to hide an internal API or narrowed access without a migration plan.

### 4.2. Reflection Access Can Change Independently

Frameworks can look up members using reflection. For example:

```java
Method method = ReportService.class.getMethod("exportReport");
```

`getMethod` searches for public methods, including inherited public methods. If the method changes to protected, this lookup call may no longer find the method and throw `NoSuchMethodException`.

`getDeclaredMethod` searches for a method declared directly in the class without restricting to public:

```java
Method method = ReportService.class.getDeclaredMethod("exportReport");
```

However, finding the method does not mean it can be invoked. `Method.invoke` must still satisfy access rules; `setAccessible(true)` or `trySetAccessible()` is also affected by the module system and deep access restrictions. Therefore, changing a modifier can break ORM frameworks, serializers, dependency injection, or mappers even when application code does not call the method directly.

## 5. Which Consumers Are Affected by Narrowing Access?

Not all binaries are affected equally. It is necessary to identify the access site and the relationship between the consumer and the API.

### 5.1. Consumers in the Same Package

If a public member changes to package-private, consumers in the same package can still access it under Java rules, provided they actually belong to the same runtime package. A runtime package is determined not only by the package name but also by the class loader. Two classes with the same package name but loaded by different class loaders may not belong to the same runtime package.

Therefore, inspecting source code and only seeing the `package` declaration is sometimes insufficient in applications with plugins or custom class loaders.

### 5.2. Subclasses in Other Packages

If a public method changes to protected, a subclass in another package may still have access in valid contexts. However, non-subclass clients lose access. Even within a subclass, protected access has rules regarding the receiver's type; protected cannot be treated as equivalent to public.

Example:

```java
package com.example.extension;

import com.example.api.ReportService;

public class CustomReportService extends ReportService {
    public void runExport() {
        exportReport(); // Can access protected via inheritance.
    }
}
```

A subclass client still running does not prove that all consumers are compatible. Direct calls from non-inheriting classes must also be checked.

### 5.3. Consumers Using Reflection or Frameworks

Frameworks may rely on public constructors, public getters/setters, or deep access via reflection. When a modifier changes, errors may only appear when the framework instantiates beans, maps entities, serializes data, or loads plugins.

Do not look only for static method calls in source code. Search class/method name configurations, annotations, XML mappings, reflection, and libraries that automatically scan the classpath.

## 6. Why Do Vendors Want to Narrow Access?

Reducing access levels is usually aimed at controlling the API surface and reducing the number of contracts the vendor must maintain long term. A public method can become depended upon by many applications, making it difficult for the vendor to change internal structure.

Common reasons:

- **Hide implementation details:** turn helper methods or fields into private/package-private so consumers do not depend on internals.
- **Protect data invariants:** prevent clients from directly modifying fields and putting objects into invalid states.
- **Control extension points:** keep certain hooks as protected instead of public to limit how subclasses interact.
- **Module encapsulation:** export only packages considered officially supported APIs.
- **Remove unsupported APIs:** shrink the compatibility surface after a deprecation or transition period.
- **Reduce security risk:** restrict access to sensitive internal data or operations.

These can be reasonable design improvements, but if the API has already been released and has external consumers, the change still must be managed as an impactful compatibility change.

## 7. How to Narrow Access While Reducing Migration Risk

If the vendor controls the library and consumers, this can be done in phases.

### 7.1. Identify the API Surface Currently in Use

First, list public/protected classes, constructors, methods, and fields. Combine API analysis with actual usage data, consumer sources, plugins, and integration documentation. Distinguish between published supported APIs and accidentally exposed internal details.

Tools like Revapi or japicmp can compare two library versions and point out modifier changes likely to break compatibility. Results should be interpreted with consumer context because tools do not know all the ways applications use reflection or class loaders.

### 7.2. Mark as Deprecated Before Narrowing or Removing

If a public method needs to be replaced, it can be kept for a period and marked deprecated:

```java
public class ReportService {
    /**
     * @deprecated Use {@link #export()} instead.
     */
    @Deprecated(since = "2.4", forRemoval = true)
    public void exportReport() {
        export();
    }

    public void export() {
        // New implementation
    }
}
```

Keeping the old method and delegating to the new method allows old binaries to continue calling it during the transition period. Afterward, clearly announce the planned removal version and provide replacement instructions.

Note: marking as deprecated does not narrow access by itself. It is a notification step giving consumers time to transition before the vendor makes a compatibility-breaking change in an appropriate major version.

### 7.3. Keep a Public Facade and Move Logic to an Internal Implementation

One way to shrink the API surface is to keep the public method stable while moving logic into an internal component:

```java
public class ReportService {
    private final ReportExporter exporter = new ReportExporter();

    public void export() {
        exporter.export();
    }
}

final class ReportExporter {
    void export() {
        // Internal implementation details
    }
}
```

Clients continue calling the public facade, while the implementation can be changed without exposing helper methods. This approach is often more appropriate than turning many already-released public methods into private ones in a minor update.

### 7.4. Release Breaking Changes in a Planned Major Version

If a public API must be narrowed or removed, clearly publish the change in release notes and migration guides, stating the old API, replacement API, removal timeline, and potential errors. For libraries used by many applications, a transition period and migration examples are necessary.

A major version does not automatically make a change safe. It is merely a versioning signal helping consumers know the contract may have changed. Binary compatibility still needs to be checked, along with a rollout plan for dependent consumers.

### 7.5. Consider Adapters or Bridges When Old Binaries Must Be Supported

In some cases, the old public method can be retained as a bridge method, delegating to the new implementation. This allows old consumers to continue working during the transition period.

Keeping a bridge is not always possible: there may be security reasons, invariants, or data model changes that make the old API unsafe. When it cannot be kept, clearly announce the breaking change and require consumers to recompile.

## 8. Checking Impact on Source Code and Compiled Binaries

A migration requires two separate types of verification. Recompiling consumer source verifies source compatibility; running old artifacts with the new library helps uncover binary linkage issues.

### 8.1. Compile Consumer Source Against the New Library

Maintain a representative consumer or an API compatibility test suite. Compile it against the new library version. Errors such as `has protected access`, `is not public`, or `cannot access` indicate that the source is using access privileges that were narrowed.

Check these cases:

- Clients outside the package calling a public member.
- Subclasses in another package overriding or calling a protected member.
- Clients instantiating a class via a constructor whose modifier changed.
- Code accessing fields directly.
- Reflection or frameworks looking up public members.
- Client modules reading and accessing a package whose exports changed.

### 8.2. Run Old Binaries Against the New Library

To check binary compatibility, the process needs to keep the consumer artifact compiled against the old library unchanged:

```text
Library version 1
        |
        v
Compile Client.java
        |
        v
Keep Client.class unchanged
        |
        v
Replace library with version 2
        |
        v
Run old Client.class with new library
        |
        v
Observe linkage/access error
```

General example commands:

```bash
# Compile consumer with old API
javac -cp library-v1.jar -d consumer-classes Client.java

# Run old bytecode with new API
java -cp library-v2.jar:consumer-classes com.example.client.Client
```

On Windows, the classpath separator character is a semicolon (`;`) instead of a colon (`:`). It is important not to recompile `Client.class` between the two steps; if recompiled against the new library, source errors will appear before the old binary can be tested.

### 8.3. Check Rarely Used Execution Paths as Well

A binary may start up successfully because the JVM has not resolved every reference yet. It is necessary to invoke methods and business branches that use the changed API, instantiate related classes, and exercise plugin/reflection paths.

If the library is used by multiple application versions, test important consumer artifacts or maintain an automated binary compatibility test suite.

### 8.4. Check Modules and Reflection

If the application uses the module path, run tests with the actual `module-info.java` and exports configuration. If frameworks use reflection, create integration tests to verify method/field lookup, constructor access, and calling `setAccessible`/`trySetAccessible` in the target module environment.

Do not run tests only on the classpath if production deploys on the module path, because module rules can change access outcomes.

## 9. How to Read Errors and Isolate the Root Cause

When an old application fails after replacing a library, distinguish access errors from missing-member errors or class structure errors.

| Message | Interpretation | Verification direction |
|---|---|---|
| `IllegalAccessError` | Member/class was found, but the binary does not have permission to access it | Compare modifiers, packages, subclass relationships, and module exports. |
| `NoSuchMethodError` | No method found with the name and descriptor requested by the bytecode | Compare old/new APIs, overloads, parameter/return types, and loaded dependencies. |
| `NoSuchFieldError` | No field found with the name and descriptor requested by the bytecode | Check whether the field was renamed, deleted, or changed type. |
| `ClassNotFoundException` | Code actively loaded a class by name, but the class loader could not find it | Check classpath/module path, class name, and class loader. |
| `NoClassDefFoundError` | The JVM could not supply a required class during linking or usage | Check missing JARs, transitive dependencies, or an earlier class initialization error. |
| `IllegalAccessException` | Reflection is not permitted to perform the operation | Check modifiers, caller, and reflection permissions. |
| `InaccessibleObjectException` | Deep reflection is blocked by encapsulation/module rules | Check whether the package is opened and module policies. |

A stack trace may point to a framework rather than an application code line. Find the class and method actually being accessed, then determine who is calling it and which class loader/module is involved.

## 10. Common Misconceptions

**“The method name and descriptor didn't change, so the binary is still compatible.”** The descriptor only identifies the method at the linkage level. Access flags are still checked by the JVM; old binaries can encounter `IllegalAccessError`.

**“Changing public to protected only affects recompiled code.”** Source consumers may report errors immediately at compile time, but old binaries can also fail when the JVM checks access privileges.

**“Adding a new getter will preserve compatibility for clients reading the old field.”** Old binaries still reference the field directly. They do not automatically switch to the new getter.

**“Protected is equivalent to public for all subclasses.”** Protected has specific access rules, especially for subclasses in other packages and the receiver's type.

**“If a method is public, any module can call it.”** JPMS also controls readability and exports. A public type in an unexported package may be inaccessible from another module.

**“The application starting up successfully is enough.”** References may only be resolved when a business flow, plugin, or reflection path is executed.

## 11. Checklist When Narrowing Access in a Library

- [ ] Identified which members/classes/constructors will have access reduced.
- [ ] Found consumers outside the package and subclasses using the API.
- [ ] Checked released binaries, plugins, and applications that cannot be rebuilt simultaneously.
- [ ] Checked reflection, framework mappings, and dynamic class loading configurations.
- [ ] Reviewed module `exports`/`opens` and the production module path.
- [ ] Evaluated potential errors, especially `IllegalAccessError`.
- [ ] Considered keeping a facade/bridge or a deprecation period before narrowing.
- [ ] Announced breaking changes and migration guidance if the old API cannot be kept.
- [ ] Compiled consumer source against the new library.
- [ ] Ran old consumer binaries against the new library without recompiling artifacts.
- [ ] Tested rarely used runtime, plugin, and reflection branches.
- [ ] Recorded test results and the library/JDK versions used for verification.

## 12. Conclusion

Narrowing access from `public` down to `protected`, package-private, or `private` can break binary compatibility. Even though the class, field, or method name and descriptor remain unchanged, the JVM still checks access flags when resolving and using references from bytecode. If an old binary calls a member it no longer has permission to access, `IllegalAccessError` may occur at runtime.

Impact also depends on packages, inheritance relationships, class loaders, module exports, and whether the application uses reflection or automated frameworks. Therefore, vendors should inventory consumers, announce deprecations, keep facades or bridges when appropriate, and publish planned breaking changes. Verification must include both recompiling consumer source and running old artifacts against the new library. Only when the relevant access cases have been verified can the team accurately assess the safety of an access change.
