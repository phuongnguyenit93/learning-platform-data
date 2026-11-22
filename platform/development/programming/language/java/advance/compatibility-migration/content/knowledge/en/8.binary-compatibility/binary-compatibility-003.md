# Deleting, renaming, or moving classes and packages

In Java, the fully qualified name of a class is part of the binary contract. When the compiler generates bytecode, it records the names of classes, interfaces, fields, and methods referenced by the program into the constant pool and descriptors. The JVM uses those names and descriptors to load classes, link methods, access fields, and execute calls.

Therefore, deleting a class, renaming a class, or moving a class to another package can prevent compiled binaries from finding the types they reference. A change that appears to be merely reorganizing the source tree can lead to `NoClassDefFoundError`, `ClassNotFoundException`, `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, or errors when loading services, configurations, and persisted data.

During a Java compatibility migration, it is necessary to distinguish relocating a `.java` file from changing a class's binary name. Moving a file's location in the repository while preserving the `package` declaration and class name usually does not change its binary identity. Conversely, modifying the package declaration or class name creates a new binary name, even if the internal logic does not change.

## 1. What is a class's binary name?

### 1.1. Package name and class name form the binary name

Suppose the source declares:

```java
package com.acme.payment;

public class PaymentService {
}
```

The simple name is `PaymentService`, the fully qualified name in source is `com.acme.payment.PaymentService`, and the binary name the JVM uses to identify the class is `com.acme.payment.PaymentService`. In a class file, the internal name is typically represented using forward slashes:

```text
com/acme/payment/PaymentService
```

If the class is moved to the `com.acme.billing` package, the binary name changes to `com.acme.billing.PaymentService`. The JVM treats this as a different type, even though the source code retains the same contents and simple class name.

Similarly, renaming the class from `PaymentService` to `BillingService` creates a new binary name. There is no automatic mechanism for the JVM to infer that the new class is the old class just because they have the same contents.

### 1.2. Binary identity differs from source file location

Java build tools usually expect source files to reside in a directory corresponding to the package, for example:

```text
src/main/java/
└── com/acme/payment/PaymentService.java
```

However, what determines the generated class name is the package declaration and type name in source, not merely the file path. The compiler can compile source from a different path, yet the class file still carries the binary name according to the declaration.

Moving the `PaymentService.java` file to a different directory while keeping:

```java
package com.acme.payment;
public class PaymentService { }
```

leaves the binary name as `com.acme.payment.PaymentService`. This is a source layout change, not a package migration. Even so, build scripts, source sets, code generators, or IDEs may depend on the old path; they need to be checked separately.

Conversely, just editing the package line:

```java
package com.acme.billing;
```

already changes the binary name. Already-compiled clients still reference the old name.

### 1.3. Class loaders also participate in runtime identity

In the JVM, a class is identified by its binary name together with its defining class loader. Two classes with the same name defined by two different class loaders can be two incompatible types. Therefore, plugin applications, application servers, OSGi, or systems with custom class loaders must also consider where classes are loaded.

When moving packages, issues can arise with parent-first/child-first delegation, package sealing, class loader constraints, and communication between modules/plugins. Simply confirming that a JAR contains the new class is not enough if the runtime still loads an old copy of the class from another class loader.

## 2. How does the JVM store references to classes and methods?

### 2.1. Constant pool and symbolic references

A class file contains a constant pool, which stores class names, method names, field names, data types, and symbolic references needed for linking. Example source:

```java
PaymentService service = new PaymentService();
service.charge(100L);
```

The bytecode will reference the class `com/acme/payment/PaymentService` and the method named `charge` along with the corresponding descriptor. The JVM uses that information to locate the class and method at runtime.

If the class's package is changed, the binary name in the old client's constant pool is not automatically updated. If a method has a parameter or return type that is a class whose package changed, the descriptor also changes.

### 2.2. Descriptors contain referenced type names

Example method:

```java
public Receipt charge(PaymentRequest request) { ... }
```

If `PaymentRequest` is in `com.acme.payment.model` and `Receipt` is in `com.acme.payment.result`, the binary descriptor of the method contains the internal names of those types, taking the form:

```text
(Lcom/acme/payment/model/PaymentRequest;)Lcom/acme/payment/result/Receipt;
```

When moving `PaymentRequest` to another package, the method descriptor also changes. Keeping the method name `charge` and the logic is not enough to maintain binary compatibility.

Cases requiring attention:

- Parameter types of public/protected methods.
- Return types of methods.
- Field types of public/protected fields.
- Superclasses and implemented interfaces.
- Constructors whose parameters are moved classes.
- Types used in annotations, generic signatures, or exception declarations.
- Types referenced by bridge methods or generated bytecode.

Generic type arguments usually undergo type erasure in descriptors, but generic signature metadata can still contain class names. API analysis tools and consumer compilers can detect this change even though the descriptor has erased part of the generic information.

## 3. What errors does deleting a class cause?

### 3.1. Compiled class is no longer on the runtime classpath

Suppose a client is compiled against library version 1 which has:

```java
package com.acme.payment;

public class PaymentService {
    public void charge() { }
}
```

Client:

```java
import com.acme.payment.PaymentService;

public class Checkout {
    public void complete() {
        new PaymentService().charge();
    }
}
```

In version 2, the library removes `PaymentService` without keeping a compatible class. The old client can still exist as compiled bytecode, but when the JVM needs to load `PaymentService`, the runtime cannot find the class. Depending on when and how the class is used, the error is typically:

```text
java.lang.NoClassDefFoundError: com/acme/payment/PaymentService
```

If the application uses reflection:

```java
Class.forName("com.acme.payment.PaymentService");
```

it may receive `ClassNotFoundException`. The two errors have different contexts: `ClassNotFoundException` is typically thrown by explicit class-loading APIs such as `Class.forName`, whereas `NoClassDefFoundError` is a linkage error when the JVM needs a class but cannot find or load it.

### 3.2. Deleting a class used as a parameter type or return type

A client may not directly instantiate a class yet still reference it in a method descriptor:

```java
public interface PaymentGateway {
    Receipt charge(PaymentRequest request);
}
```

If `Receipt` or `PaymentRequest` is removed from the runtime, an error can occur when the JVM loads the interface, checks methods, uses reflection, or executes calls. You should not only search for `new OldClass()` to determine the impact scope; search for every place that type appears in the public/protected API and dependency graph.

### 3.3. Deleting related methods or constructors

If the class still exists, but a method called by an old client is deleted, renamed, or has its descriptor changed, the JVM may throw `NoSuchMethodError`. If a field is deleted or has its descriptor changed, it may throw `NoSuchFieldError`.

Changing a constructor is also a form of binary change. Constructors are represented as a special `<init>` method with its own descriptor. If an old client calls constructor `(String)`, while the new version only has constructor `(Path)`, old bytecode will not automatically substitute the new constructor.

### 3.4. Deleting a class can cause delayed errors

Not every referenced class is loaded immediately at application startup. A class used only in a rare execution branch, optional plugin, scheduled job, or infrequently called endpoint may only cause an error when that feature is executed.

Therefore, startup tests are not enough to prove class removal is safe. All consumers and flows using the class must be tested, including reflection, service loading, and external configuration.

## 4. Renaming or moving a class/package changes the binary name

### 4.1. Renaming a class

From:

```java
package com.acme.payment;
public class PaymentService { }
```

to:

```java
package com.acme.payment;
public class BillingService { }
```

already creates a new binary name. Clients referencing `com.acme.payment.PaymentService` do not automatically switch to `BillingService`.

### 4.2. Moving a class to a new package

From:

```java
package com.acme.payment;
public class PaymentService { }
```

to:

```java
package com.acme.billing;
public class PaymentService { }
```

the new binary name is `com.acme.billing.PaymentService`. This is a type name change from the JVM's perspective. All clients, subclasses, annotations, resources, and configurations specifying the old name must be reviewed.

### 4.3. Moving a package affects more than just imports

A package change can affect:

- Bytecode referencing the old class.
- Method descriptors containing the old type.
- Inheritance, interface implementations, and generic signatures.
- Package-private classes, fields, constructors, and methods.
- Reflection and `Class.forName`.
- `ServiceLoader`, `META-INF/services` files, and `module-info.java`.
- Java serialization and persisted data.
- Framework annotation scanning, component scanning, and entity scanning.
- Resources located under the package path.
- JNI/native methods and symbol names.
- Documentation, XML/YAML/properties configuration, and deployment scripts.

Therefore, package refactoring in an IDE can update source code within a single repository, but it does not automatically update external consumers, old serialized data, or integrated systems using class names as strings.

## 5. Package-private access and runtime packages

### 5.1. Moving packages can cause loss of access rights

Members not declared `public` or `protected` may only be accessible within the same package according to Java rules. For example:

```java
package com.acme.payment;

class PaymentValidator {
    void validate() { }
}

public class PaymentService {
    void execute() {
        new PaymentValidator().validate();
    }
}
```

If `PaymentValidator` alone is moved to `com.acme.validation`, `PaymentService` can no longer access the package-private class/method as before. The compiler may report a source error immediately upon recompilation.

Even if both classes are moved, other classes in the old package may lose access to package-private members. Package boundaries must be checked to determine whether visibility should be widened, the API changed, or related classes kept together in the same package.

### 5.2. A runtime package is not based solely on package name

In the JVM, a runtime package is tied to the package name and the defining class loader. Two classes with the same package name loaded by different class loaders do not necessarily belong to the same runtime package. This matters for plugins, application servers, and custom module/class loader systems.

When moving classes between JARs, modules, or class loaders, package-private access can change even if the source package name does not change. Packaging and class loading behavior must be checked in the actual environment.

### 5.3. Sealed classes and package relationships

A sealed class/interface has a list of permitted subclasses. For classes in an unnamed module, package and module rules affect where subclasses are allowed to exist. Moving a class or permitted subclass to another package/module can render the sealed type declaration invalid or alter extensibility.

When moving packages, check:

- The `permits` clause and fully qualified names of subclasses.
- Same-package rules when types are in an unnamed module.
- Module relationships when types are in named modules.
- Subclasses generated by plugins or other modules.

## 6. Java Platform Module System (JPMS) when moving packages

### 6.1. `exports` and `opens` need updating

In projects using `module-info.java`, packages are exported or opened by package name. For example:

```java
module com.acme.payment {
    exports com.acme.payment.api;
    opens com.acme.payment.model to com.fasterxml.jackson.databind;
}
```

If `com.acme.payment.api` is moved to `com.acme.billing.api`, the module descriptor needs to update `exports`. If a framework uses reflection on the new model, `opens` also needs to point to the new package.

An unexported package can still be used internally within a module, but consumers in other modules cannot access it. A package that is not opened can cause deep reflection to fail even when code compiles normally.

### 6.2. `uses` and `provides` for ServiceLoader

A module descriptor may declare:

```java
module com.acme.payment {
    uses com.acme.payment.spi.PaymentProvider;
    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.internal.DefaultPaymentProvider;
}
```

If the SPI interface or implementation is moved to a new package, both `uses` and `provides` must be updated. If using the classpath and `META-INF/services` files, the interface name in the file path and the provider name inside the file must also be updated.

Missing configuration can cause `ServiceLoader` not to find the provider or to throw `ServiceConfigurationError` when loading an invalid provider.

### 6.3. Split packages and the module path

Moving part of a package's classes to another JAR/module can create a split package. On the classpath, a split package can lead to unpredictable class loading depending on the class loader. On the module path, named modules must not share duplicate packages under JPMS rules; the application can fail during module layer startup or resolution.

When splitting a package into a new module, determine which module owns the package, which module exports/opens it, and which modules read it via `requires`. Avoid allowing the same package to exist across multiple JARs/modules if the system will run on the module path.

## 7. Reflection, framework scanning, and string-based configuration

### 7.1. Reflection is not updated automatically by the compiler

The following code depends on string class names:

```java
Class<?> type = Class.forName("com.acme.payment.PaymentService");
Object instance = type.getDeclaredConstructor().newInstance();
```

IDE package refactoring can update imports and static type references, but not all tools detect string class names. If a class is renamed or moved to another package, reflection configuration may continue pointing to the old name and only fail at runtime.

Review the following APIs and locations:

- `Class.forName(...)` and `ClassLoader.loadClass(...)`.
- `MethodHandles` and reflection looking up methods/fields by name.
- `ServiceLoader.load(...)` and provider configurations.
- Class names in XML, YAML, JSON, properties, or databases.
- Plugin registries, dependency injection, polymorphic serializer types, and scripting.
- Annotation scanning by package prefix.

### 7.2. Framework component scanning and entity scanning

Frameworks may use package names to restrict the scan scope for components, controllers, repositories, entities, mappers, or configurations. For example, a configuration scanning an old package may fail to detect a bean after it is moved to a new package.

Check:

- Component scan and package scan base packages.
- ORM entity scan, repository scan, and mapping files.
- Jackson polymorphic types or class names in payloads.
- Validation provider, converter, serializer, and mapper registrations.
- Test scans, test configurations, and test fixtures.
- Native image reflection/resource configuration if the application builds a native image.

An application may start up without the moved bean/entity being scanned, and then fail when the first request or query executes. Therefore, test behavior and inspect registries/metadata after moving packages.

### 7.3. Resource paths following packages

Some APIs load resources relative to a class's package:

```java
InputStream stream = PaymentService.class.getResourceAsStream("messages.properties");
```

If a resource is packaged under a path corresponding to the package, moving the class can change the resource lookup path. Similarly, properties files, templates, XML mappings, SQL scripts, or schemas placed alongside the class may not be found after the package changes.

Check both resources copied by the build tool and resources generated during the build. Do not only move `.java` files; verify the resource path contract and how the framework locates resources.

## 8. Java serialization and persisted data

### 8.1. Class name is part of the serialized stream

With Java Object Serialization, the stream contains the class name and class metadata. If an object was serialized when the class was named `com.acme.payment.PaymentRecord`, and later the class's package changes to `com.acme.billing.PaymentRecord`, old data may fail to deserialize if the runtime no longer has the old class.

Even if `serialVersionUID` is preserved, changing the binary name remains a separate problem. `serialVersionUID` helps verify structural serialization compatibility for a class with the same identity; it does not automatically map an old class name to a new one.

### 8.2. Strategies for maintaining old serialized data

If old data must be read, you can keep a compatible class at the old binary name and provide conversion logic to the new model. Another option is using a custom `ObjectInputStream.resolveClass` to map the old descriptor to the new class, though this approach must be carefully designed and thoroughly tested for schema/field compatibility.

Overriding `resolveClass` should not be treated as a simple global package replacement. Mapping can fail if field structure, reference types, hierarchy, or serialization protocols have changed. For critical long-lived data, consider data formats with explicit schemas/versions such as JSON/Avro/Protobuf instead of depending directly on Java class names.

### 8.3. `serialVersionUID`, `readObject`, and `readResolve`

When keeping the old class as a compatibility facade, clearly verify:

- Whether `serialVersionUID` is explicitly declared.
- Whether old fields are retained or need conversion.
- Whether `readObject` can convert data into the new representation.
- Whether `readResolve` can return the new object that consumers expect.
- Whether there are nested serialized objects containing multiple moved classes.

Test using actual serialized data from the old version. Creating a new object and serializing/deserializing it within the same new version does not prove compatibility with historical data.

## 9. JNI, native libraries, and class names

JNI can use class names, packages, and signatures to link native methods. If the class or package changes, the JNI symbol name generated according to JNI mangling rules may change. An old native library may no longer find the corresponding method.

Review:

- Methods declared `native`.
- Native libraries using `RegisterNatives` with specific classes and signatures.
- JNI headers generated by `javac -h`.
- Native agents, profilers, or C/C++ libraries looking up classes via JNI.
- Native image configurations or binding generators.

After moving classes, regenerate JNI headers, build the corresponding native library, and run integration tests on the target OS/architecture. Changing packages in Java without updating native code can cause errors that only appear when calling native methods.

## 10. Preserving compatibility with facades, adapters, and deprecation

When a public class has been released and has external consumers, a safe approach is usually to keep the old binary name during a transition period. The new class becomes the canonical API, while the old class serves as a facade/adapter.

### 10.1. Keeping the old class as a facade extending the new class

If the new class is not `final`, has no inheritance restrictions, and has compatible constructors, the old class can extend the new class:

```java
// New API
package com.acme.billing;

public class BillingService {
    public BillingService(String tenant) { }

    public void charge(long amount) { }
}
```

```java
// Compatibility facade at the old binary name
package com.acme.payment;

/** @deprecated Use com.acme.billing.BillingService. */
@Deprecated(since = "2.0", forRemoval = false)
public class PaymentService extends com.acme.billing.BillingService {
    public PaymentService(String tenant) {
        super(tenant);
    }
}
```

Old clients still find `com.acme.payment.PaymentService` and the old constructor. New clients can gradually migrate to `BillingService`.

All constructors that old consumers might call must be preserved. Constructors are not inherited automatically, so the facade must redeclare the public/protected constructors that need to be retained. Old methods and old descriptors must also be kept if they are part of the published API.

### 10.2. Using composition when inheritance is not possible

If the new class is `final`, its constructors are incompatible, or inheritance exposes undesirable semantics, use composition:

```java
package com.acme.payment;

/** @deprecated Use com.acme.billing.BillingService. */
@Deprecated(since = "2.0", forRemoval = false)
public final class PaymentService {
    private final com.acme.billing.BillingService delegate;

    public PaymentService(String tenant) {
        this.delegate = new com.acme.billing.BillingService(tenant);
    }

    public void charge(long amount) {
        delegate.charge(amount);
    }
}
```

Composition preserves the old API, but it must completely forward methods, exceptions, null contracts, lifecycle, and semantics. If the old class has many public methods, the entire surface used by consumers must be maintained.

### 10.3. Keeping the old interface as a forwarding interface

If an interface is moved to a different package, the old interface can be kept extending the new interface:

```java
package com.acme.billing.spi;

public interface BillingProvider {
    Receipt charge(Request request);
}
```

```java
package com.acme.payment.spi;

/** @deprecated Use com.acme.billing.spi.BillingProvider. */
@Deprecated(since = "2.0", forRemoval = false)
public interface PaymentProvider extends com.acme.billing.spi.BillingProvider {
}
```

An old class that already `implements PaymentProvider` will simultaneously be an instance of the new interface through the inheritance relationship. However, if the new interface adds an abstract method, old implementation classes may not provide an implementation. When that method is called, the runtime may throw `AbstractMethodError`. You must preserve the old method contract or provide a default method/adapter with appropriate semantics.

### 10.4. Keeping old types in old API signatures

A common mistake is keeping the old facade class while immediately changing the old method to accept/return new types:

```java
// Old API
public OldReceipt charge(OldRequest request);

// Binary incompatible if the descriptor changes
public NewReceipt charge(NewRequest request);
```

Keeping the same method name does not preserve the binary descriptor. Keep the old method with the old types and add a new API with a different name or signature:

```java
public OldReceipt charge(OldRequest request) {
    NewReceipt result = billingService.charge(convert(request));
    return convertBack(result);
}

public NewReceipt chargeNew(NewRequest request) {
    return billingService.charge(request);
}
```

If type conversion is needed, clearly define the adapter and behavior for null, errors, fields that no longer map, and default data.

## 11. Moving packages in phases

A large package migration should be broken down into independently releasable steps.

### Phase 1: Prepare the new API

- Create classes/interfaces in the new package.
- Define the canonical API and ownership of each type.
- Add necessary adapters/facades.
- Update module descriptors, service providers, and resource paths.
- Do not delete the old binary name yet.

### Phase 2: Maintain the compatibility facade

- Keep old classes/interfaces in the old package.
- Forward methods/constructors to the new API.
- Mark as deprecated and provide migration notes.
- Retain old descriptors for key methods/fields/constructors.
- Add tests for both old consumers and new consumers.

### Phase 3: Migrate consumers

- Update imports and type references in source code.
- Update reflection strings, XML/YAML/properties, and package scanning.
- Update service loaders, module descriptors, serialization mappings, and JNI if applicable.
- Check generated sources, test fixtures, and documentation.
- Monitor deprecation warnings to identify consumers still using the old API.

### Phase 4: Retire the old API

- Announce the end-of-support timeline.
- Confirm internal consumers and partners have migrated.
- Measure usage if the system has appropriate telemetry.
- Prepare a major release if removing the old API is a breaking change.
- Provide a migration guide and the final release still containing the facade.

### Phase 5: Remove the facade in a major release

Only remove the old class/package when the versioning policy permits a breaking change and consumers have an upgrade plan. If there is serialized data, external plugins, SDKs, or integration contracts depending on the old name, there must be a separate migration plan. A major version does not make historical data disappear automatically.

## 12. Checking impact scope before deleting or moving a class

### 12.1. Checking public/protected APIs

Create a list of:

- Public and protected classes/interfaces/enums/records.
- Public/protected constructors.
- Methods and fields whose parameter/return types are the class being moved.
- Superclasses/interfaces, annotations, and nested classes.
- Generic signatures, exception declarations, and bridge methods.
- SPIs, plugin extension points, and classes subclassed by consumers.

A non-public class can still be used by other modules in the same package, reflection, frameworks, or code generation. Do not conclude a class is safe to delete just because it does not appear in API documentation.

### 12.2. Searching for static and dynamic references

Search for the old fully qualified names in source code, build files, and configurations:

```text
com.acme.payment.PaymentService
com.acme.payment.spi.PaymentProvider
```

Also search for the slash form in bytecode/tooling configurations:

```text
com/acme/payment/PaymentService
```

Review `Class.forName`, `loadClass`, reflection, ServiceLoader, module descriptors, framework scanning, serializer type IDs, JNI, and resource lookups. Class names can be constructed from properties or databases, so plain code search alone cannot detect everything.

### 12.3. Inspecting JARs and bytecode

Use `jar tf` to view archive contents:

```bash
jar tf payment-library.jar
```

Use `javap` to view binary APIs and descriptors:

```bash
javap -classpath payment-library.jar -public com.acme.payment.PaymentService
javap -classpath payment-library.jar -s com.acme.payment.PaymentService
javap -classpath payment-library.jar -verbose com.acme.payment.PaymentService
```

`-public` shows public members; `-s` displays descriptors; `-verbose` adds the constant pool and metadata. Compare old and new JARs to determine whether the old class still exists, whether methods/constructors retain their descriptors, and whether the new package is packaged properly.

### 12.4. Using API compatibility tools

Tools like japicmp and Revapi can compare the APIs of two artifacts and detect deleted/renamed classes, changed methods/fields, modifier changes, or hierarchy changes. Configure the API scope and baseline version properly.

These tools are useful, but they do not replace runtime tests for reflection, service loading, serialization, JNI, or string-based configuration. A class may not belong to the public API yet still be an actual contract with a framework or plugin.

### 12.5. Using jdeps and dependency graphs

`jdeps` helps analyze dependencies across classes/packages/modules:

```bash
jdeps -summary payment-library.jar
jdeps -verbose:class payment-library.jar
```

For multi-module applications, combine this with Gradle/Maven dependency graphs to see which modules depend on the old artifact. Check compile, runtime, test, annotation processor, and plugin classpaths as well. Transitive dependencies can pull in an old version of a library containing the moved class.

## 13. Testing binary compatibility and consumer compatibility

### 13.1. Binary compatibility testing

Keep a consumer fixture compiled against the old library version. Then run that same binary with the new library version on the runtime classpath. This is a direct way to detect linkage errors caused by deleted classes/methods/fields or changed descriptors.

Illustrative process:

1. Compile the consumer with library v1.
2. Preserve the consumer's class files and necessary dependencies intact.
3. Replace library v1 with library v2 on the runtime classpath.
4. Run the flows that use the relevant classes, methods, fields, and constructors.
5. Record linkage errors and features that stop working.

Do not recompile the consumer at step 3, because recompiling tests source compatibility rather than binary compatibility.

### 13.2. Source compatibility testing

Take the old consumer source and recompile it with library v2. This test detects nonexistent imports/packages, visibility changes, overload or type inference changes, and other source errors.

Source compatibility and binary compatibility require two separate pipelines or two separate fixtures. A change can pass one type of test and fail the other.

### 13.3. Runtime integration testing

Run the final artifact in a production-like environment and verify:

- Startup, component scanning, and dependency injection.
- Invoking endpoints, jobs, message handlers, and plugin extensions.
- `ServiceLoader` finds the right provider.
- Reflection and serialization can read old data.
- Resources/templates/configurations are loaded properly.
- JNI/native methods work on the target OS/architecture.
- Module resolution and access rules work properly on the module path.

Test both success paths and error paths. An old class might only be used when handling a specific payload type or when a specific profile is enabled.

## 14. End-to-end example: moving packages while preserving binary compatibility

Suppose the `payment-core` v1 library publishes:

```java
package com.acme.payment;

public class PaymentService {
    public PaymentService(String tenant) { }

    public Receipt charge(PaymentRequest request) { ... }
}
```

In v2, the team wants to move the API to `com.acme.billing`. If they only change the packages of the three classes, old clients will no longer find `PaymentService`, `Receipt`, and `PaymentRequest` under their old binary names. The method descriptor also changes because two data types moved packages.

A more compatible roadmap:

1. Create `com.acme.billing.BillingService`, `BillingRequest`, and `BillingReceipt`.
2. Keep `com.acme.payment.PaymentService`, `PaymentRequest`, and `Receipt` in the v2 artifact.
3. Keep the old constructor and `charge(PaymentRequest)` method with the old descriptor.
4. Inside the old method, convert the request to the new model, call the new service, and convert the result back to the old type.
5. Add a new API using `BillingRequest`/`BillingReceipt` with clear method names.
6. Update module descriptors, service providers, framework scanning, and resource paths.
7. Compile the old consumer source against v2 and run the v1 consumer binary against v2.
8. Test serialization of `PaymentRequest`/`Receipt` persisted from v1.
9. Mark the old API as deprecated, publish a migration guide, and track consumer migration.
10. Only remove the old facade in a major release after dependent data and consumers have been addressed.

In this example, the facade must also keep the old types used in the method descriptor. Keeping only the old `PaymentService` class while deleting `PaymentRequest` or changing the return type to `BillingReceipt` can still break binary compatibility.

## 15. Common mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Thinking moving source files changes the package | May confuse file layout changes with binary names | Check the package declaration and actual binary name |
| Only updating imports within the repository | External consumers, reflection, and configs still use the old name | Review all static and dynamic contracts |
| Keeping the old class but changing types in method signatures | Descriptor changes; old binaries may fail with linkage errors | Keep the old method with the old descriptor; add a separate new API |
| Only testing compilation | Does not detect old binaries or runtime configurations | Run binary compatibility fixtures and integration tests |
| Only testing startup | Old classes may only be loaded in late-executed branches | Invoke endpoints/jobs/plugins and rarely used branches |
| Keeping `serialVersionUID` and then changing the package | Class name in the stream still mismatches | Keep compatibility classes or tested migration mappings |
| Forgetting `META-INF/services`/module descriptors | Service providers are not found | Update `uses`, `provides`, and provider files |
| Forgetting package-private access | Compilation errors or runtime access changes | Check package boundaries and class loaders |
| Moving packages on the module path without checking split packages | Module resolution may fail | Define package ownership and `exports`/`opens` |
| Removing the facade immediately in a minor release | Old consumers may fail to run | Follow versioning policy; use deprecation and major releases |

## 16. Handover record for a class/package change

Before approving deleting, renaming, or moving a class/package, record:

1. **API inventory:** old/new binary names, visibility, constructors, methods, fields, superclasses, and interfaces.
2. **Descriptor diff:** parameters, return types, field descriptors, generic signatures, and related exceptions.
3. **Consumer inventory:** modules, artifacts, plugins, frameworks, configurations, and external systems referencing old names.
4. **Runtime contract inventory:** reflection, ServiceLoader, JPMS, serialization, JNI, resources, and package scanning.
5. **Compatibility strategy:** facade, adapter, interface bridge, migration mapping, or major breaking release.
6. **Binary test report:** v1 consumer binary running against v2 library.
7. **Source test report:** v1 consumer source compiling against v2 library.
8. **Integration report:** modules, services, plugins, old data, and target environment runtime.
9. **Migration guide:** new names, how to replace imports/APIs, configuration changes, and removal timeline for old names.
10. **Release decision:** owner, remaining risks, release version, and rollback plan.

### Pre-release checklist

- [ ] Identified old and new binary names of every moved class.
- [ ] Checked method/field/constructor descriptors containing types with changed packages.
- [ ] Distinguished source compatibility from binary compatibility.
- [ ] Reviewed subclasses, interface implementations, and package-private access.
- [ ] Updated `exports`, `opens`, `uses`, `provides`, and service provider files.
- [ ] Reviewed reflection, framework scanning, string-based configurations, and resource paths.
- [ ] Evaluated Java serialization and historical data.
- [ ] Checked JNI/native bindings if present.
- [ ] Checked split packages and class loaders in the target environment.
- [ ] Kept facades/adapters if old consumers need support.
- [ ] Ran old consumer binaries against the new artifact.
- [ ] Compiled old consumer source against the new API.
- [ ] Ran integration tests on the final artifact and rarely invoked flows.
- [ ] Prepared a migration guide and a facade removal plan aligned with the versioning policy.

Deleting, renaming, or moving a class/package is a binary contract change because binary names and descriptors are recorded directly in class files. Preserving compatibility requires retaining old names and signatures where consumers still depend on them, typically via facades or adapters, while updating dynamic contracts such as reflection, serialization, service loading, and JNI. With separate binary tests, source tests, and integration tests, teams can clearly identify the scope of breaking changes and roll out package migrations in phases.
