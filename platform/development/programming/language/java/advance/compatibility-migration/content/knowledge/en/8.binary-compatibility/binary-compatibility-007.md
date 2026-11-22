# Changing Superclasses, Interfaces, and Inheritance Relationships

In Java, superclasses and interfaces define part of the contract a class publishes to code that uses it. A class can inherit methods and state from a superclass, implement one or more interfaces, or receive default implementations from parent interfaces. When a library changes its inheritance structure, the impact can spread to already-compiled applications, even when the method names called by consumers still exist in the source.

In Java Compatibility Migration, hierarchy changes need to be evaluated at at least three levels:

- **Source compatibility:** Can consumer source code still recompile? Do subclasses and implementations still properly override/implement the contract?
- **Binary compatibility:** Can previously compiled bytecode still be loaded, verified, and linked against the new classes/interfaces?
- **Behavioral compatibility:** Is the dispatched method still the old implementation? Have subtype relationships, `super` calls, default methods, and inherited behavior changed?

A hierarchy change might not break all binaries immediately when classes are loaded, yet still fail when a specific code path is executed. Therefore, checking only compilation or startup is insufficient.

## 1. Inheritance Model in Java and the JVM

### 1.1. Superclasses and Interfaces

A Java class has only one direct superclass (except `Object`, which is the root of the standard class system), but it can implement multiple interfaces:

```java
public class PremiumOrder extends Order implements Billable, Auditable {
    // Inherits from Order and implements two interfaces.
}
```

This relationship establishes multiple contracts:

- `PremiumOrder` is a subtype of `Order`, `Billable`, and `Auditable`.
- Code accepting `Order` can accept `PremiumOrder`.
- Code accepting `Billable` can accept `PremiumOrder` and call methods in the `Billable` contract.
- Inherited or implemented methods are selected according to JVM method lookup and dynamic dispatch rules.

An interface can extend multiple other interfaces:

```java
public interface Billable extends Identifiable, Taxable {
    Receipt createReceipt();
}
```

A change in a parent interface can affect all child interfaces and implementing classes across many different modules.

### 1.2. Inheritance Relationships Recorded in Class Files

A class file contains information about the superclass and the direct interfaces that the class implements. The JVM uses this information to verify type safety, check type assignability, look up methods, and perform dispatch.

When compiling a method call, bytecode typically records a symbolic reference consisting of the owner type, method name, and descriptor. The invocation instruction can be `invokevirtual`, `invokeinterface`, `invokespecial`, or `invokestatic`, depending on the kind of method and how it is called.

Example:

```java
Order order = new PremiumOrder();
order.calculateTotal();
```

The static type `Order` participates in compilation and determines the method reference recorded in bytecode; the actual object `PremiumOrder` participates in dynamic dispatch for overridable instance methods.

Therefore, hierarchy changes can affect both whether the JVM finds the referenced method and which implementation is selected at runtime.

### 1.3. Distinguishing Method Resolution from Method Selection

Two steps are frequently confused:

1. **Resolution:** The JVM locates a method/field matching the symbolic reference in the constant pool, based on the owner, name, descriptor, and search rules in the hierarchy.
2. **Selection/dispatch:** For instance calls with dynamic dispatch, the JVM selects the implementation matching the actual class of the receiver.

A method may exist in a child class yet fail to help resolve a symbolic reference if the bytecode references a superclass owner that no longer declares or inherits that method. Conversely, a method reference may resolve successfully, yet the selected implementation changes because the hierarchy or overrides changed.

## 2. Changing the Superclass

Changing a superclass is a structural change with broad impact. It affects subtype relationships, inherited methods, constructor chains, protected access, `super` calls, and method dispatch.

### 2.1. Changing the Superclass to an Unrelated Class

Old library version:

```java
public class Order extends BaseEntity {
    public String getId() {
        return super.getId();
    }
}
```

Consumers might use:

```java
BaseEntity entity = new Order();
```

If the new version changes it to:

```java
public class Order extends Object {
    public String getId() {
        return "generated";
    }
}
```

then `Order` is no longer a subtype of `BaseEntity`. Consumer source code with the assignment `BaseEntity entity = new Order()` will fail to recompile. Old binaries may encounter verification errors or errors when casting/linking operations based on the old relationship, depending on bytecode and execution paths.

Even if the new class declares a method itself with the same name as a previously inherited method, that does not restore the entire contract of the old superclass. Other methods, fields, constructors, protected members, annotations, and the semantics of `BaseEntity` may still be lost.

### 2.2. Changing to a Subclass of the Old Superclass

Suppose `Order` previously extended `BaseEntity`, and later switches to `AuditedEntity`, where `AuditedEntity extends BaseEntity`:

```java
public class BaseEntity {
    public String getId() { return "id"; }
}

public class AuditedEntity extends BaseEntity {
    public Instant getCreatedAt() { return Instant.now(); }
}

public class Order extends AuditedEntity {
}
```

In terms of subtype relationships, `Order` is still a `BaseEntity` because `AuditedEntity` extends `BaseEntity`. Some consumer sources continue compiling without modification. However, this is still a hierarchy change that needs evaluation:

- The new constructor chain may invoke different constructors and change initialization state.
- `AuditedEntity` may override a method that `Order` previously inherited directly.
- New methods added to the intermediate superclass may alter overloads/overrides in the subclass.
- Fields and methods with the same name in the hierarchy may change access or cause *hiding*.
- Serialization, reflection, and framework introspection may observe a different hierarchy than before.

Preserving the subtype relationship does not equate to preserving full behavioral compatibility.

### 2.3. Changing Superclass Constructors

Constructors are not inherited. A subclass constructor must invoke a valid superclass constructor, explicitly or implicitly.

If the superclass previously had a no-argument constructor:

```java
public class BaseEntity {
    public BaseEntity() { }
}
```

then subclasses could omit declaring a constructor and the compiler automatically inserted a `super()` call.

If the new version removes the no-argument constructor:

```java
public class BaseEntity {
    public BaseEntity(String tenantId) { }
}
```

subclass sources without an explicit constructor will no longer compile because the default `super()` call is no longer valid. Previously compiled subclasses must also be examined: when the new superclass no longer has the constructor descriptor invoked by subclass bytecode, instantiating the subclass can fail with `NoSuchMethodError` during constructor invocation.

When changing superclass constructors, all internal subclasses and external consumers that might extend that class must be checked.

### 2.4. Changing `protected` and Package Access in a Hierarchy

Subclasses can access protected members according to Java rules. Moving a method or field to another superclass, changing packages, or changing visibility can cause source consumers to lose access.

Example:

```java
package com.example.base;

public class BaseEntity {
    protected String tenantId;
}
```

Subclasses in other packages can access protected members according to the rules for subclasses. If the member moves to a class no longer in the hierarchy or has its visibility reduced, subclasses may fail to compile and old bytecode may encounter access errors at runtime.

Package-private changes are even more sensitive: access depends on the package, not just the inheritance relationship. Module/package boundaries must also be examined when moving classes.

### 2.5. Adding a Method to a Superclass Can Change Dispatch

A new superclass may add a method matching the name and signature of a method a subclass previously declared on its own. That method can become a true override after the source is recompiled.

Old version:

```java
public class BaseTask {
}

public class CustomTask extends BaseTask {
    public void execute() {
        System.out.println("custom");
    }
}
```

New version of the superclass:

```java
public class BaseTask {
    public void execute() {
        System.out.println("base");
    }
}
```

When `CustomTask` is recompiled, its `execute()` method overrides the superclass method. If old code calls `super.execute()` after being modified or adds the `@Override` annotation, the behavior will differ from prior code where that method did not exist in the parent class.

In particular, adding a method to a superclass can change subclass dispatch without changing call sites. If the subclass is recompiled, a method with the same signature can become an override; if old binaries are kept unchanged, resolution and dispatch need to be evaluated on the actual class files together with the new hierarchy.

## 3. Changing Implemented Interfaces

A class can implement multiple interfaces. Changing the list of interfaces changes the set of types the class can be assigned to and the method contracts the class must satisfy.

### 3.1. Adding an Interface

Suppose the initial class is:

```java
public class CsvExporter {
    public byte[] export() { return new byte[0]; }
}
```

The new version declares an additional interface:

```java
public interface Exportable {
    byte[] export();
}

public class CsvExporter implements Exportable {
    @Override
    public byte[] export() { return new byte[0]; }
}
```

Adding an interface can expand a class's usability, but the following cases must be considered:

- The interface only declares an abstract method and the class already has a matching method: the class may satisfy the contract without adding a new implementation.
- The interface has an abstract method that the class has not implemented yet: the source build may fail if the concrete class does not satisfy the interface; if class files are generated or released in an incomplete way, calling the method may throw `AbstractMethodError`.
- The interface has a default method: that method may participate in method selection and change the invoked implementation.
- The interface has a default method conflicting with another default method in the hierarchy: compile-time conflicts or linkage errors may occur when a class/interface does not provide an override resolving the conflict.
- The interface has the same method signature as an existing method but different semantics: the class may be treated as implementing the new contract even though the old implementation does not meet the new expectations.

Adding an interface is not just adding an `implements` clause; it is publishing an additional contract to every consumer.

### 3.2. Removing an Interface

If a class removes an interface from its `implements` list, source consumers assigning that class to the interface type will no longer compile:

```java
Exportable exporter = new CsvExporter();
```

Compiled binaries may still load the class, but when executing casts, passing arguments, or calling `invokeinterface` based on the removed interface, they may encounter `ClassCastException` or `IncompatibleClassChangeError` depending on the operation and the state of the loaded classes.

If the interface is completely deleted from the library, binaries directly referencing the interface may encounter `NoClassDefFoundError` when the JVM needs to resolve that type.

### 3.3. Changing an Interface's Superinterfaces

An interface can extend multiple interfaces:

```java
public interface SecureRepository extends Repository, Auditable {
}
```

If the new version removes `Repository` from the superinterface list, code assigning `SecureRepository` to `Repository` will no longer be valid when recompiled. Binaries relying on the old subtype relationship also need to be checked during casts, method resolution, or calls through the interface.

Adding a superinterface can introduce additional abstract/default methods into the contract. In particular, default methods from multiple parent interfaces can create conflicts and require child interfaces or implementing classes to provide an explicit override.

## 4. Changing Abstract Methods and Default Methods in Interfaces

Java 8 added default methods to interfaces. This helps libraries add behavior without forcing every implementation to be modified immediately, though it does not eliminate all compatibility risks.

### 4.1. Adding an Abstract Method

Old interface:

```java
public interface PaymentGateway {
    PaymentResult pay(PaymentRequest request);
}
```

Consumer has an implementation:

```java
public class LegacyGateway implements PaymentGateway {
    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.success();
    }
}
```

The new interface adds an abstract method:

```java
public interface PaymentGateway {
    PaymentResult pay(PaymentRequest request);
    void refund(RefundRequest request);
}
```

When recompiling `LegacyGateway`, the compiler reports that the class does not implement `refund`. Previously compiled `LegacyGateway` binaries may still load, but if code invokes `refund` on that instance, the JVM finds no implementation and may throw `AbstractMethodError`.

This is a major risk for plugin APIs and SPIs: implementations may reside in third-party repositories or products outside the library development team's control.

### 4.2. Adding a Default Method

A default method can be added to provide default behavior:

```java
public interface PaymentGateway {
    PaymentResult pay(PaymentRequest request);

    default void refund(RefundRequest request) {
        throw new UnsupportedOperationException("Refund is not supported");
    }
}
```

Old implementations do not need to add the method for source to recompile. However, default methods only maintain compatibility at the structural level; the default behavior may not suit every implementation. If callers start calling `refund`, old implementations may throw an exception.

A new default method can also conflict with a method of the same signature from another interface or with a method in a superclass. Priority rules among class methods, interface default methods, and parent interfaces must be evaluated at compile time and runtime.

### 4.3. Default Method Conflicts

Two unrelated interfaces both declare a default method with the same signature:

```java
interface JsonExport {
    default String format() { return "json"; }
}

interface XmlExport {
    default String format() { return "xml"; }
}
```

A class implementing both must resolve the conflict:

```java
class ReportExporter implements JsonExport, XmlExport {
    @Override
    public String format() {
        return JsonExport.super.format();
    }
}
```

If a new interface is added to the hierarchy and brings a default method with a colliding signature, child classes or child interfaces may need to add an override. Changing parent interfaces can also render a previously selected default method no longer unique.

### 4.4. Class Method Precedence

In a conflict between a concrete method in a class hierarchy and a default method from an interface, the class method takes precedence. This can change behavior when a new method is added to a superclass, or when a new interface brings a default method into the hierarchy.

For foundational libraries, do not rely on assumptions from method names. Compile representative consumers and verify dispatch on actual class files.

## 5. Changing a Class to an Interface or an Interface to a Class

Changing the nature of a type from a class to an interface or vice versa is a drastic change. Bytecode stores the kind of symbolic reference and the corresponding invocation instructions; when the type kind changes, the JVM can detect a mismatch.

For example, consumers compiled against a `Repository` class may use `new Repository()` or `extends Repository`. If the library changes `Repository` into an interface, consumer source is no longer valid. Old binaries may encounter `IncompatibleClassChangeError` when the JVM detects a class/interface kind mismatch with the bytecode.

The reverse is also true: if an interface becomes a class, code using `implements`, interface method invocations, or multiple inheritance contracts may no longer be valid.

Typically, this kind of type change should be treated as a breaking change and performed in a major version, accompanied by a new API or adapter types to support the transition period.

## 6. Changing final, abstract, and Inheritance Capabilities

### 6.1. Adding `final` to a Class

If a class could previously be subclassed but a new version adds `final`, subclass sources no longer compile. Old subclass binaries may encounter `VerifyError` when the JVM verifies that they inherit from a final class.

This is a change with direct impact on frameworks and libraries relying on subclasses/proxies such as ORM, mocking, AOP, or dependency injection.

### 6.2. Adding `abstract` or an Abstract Method

Changing a concrete class to abstract prevents source consumers from instantiating that class directly. Old binaries executing `new` on a now-abstract class may encounter `InstantiationError`.

Adding an abstract method to a superclass can leave old concrete subclasses without an implementation. When the method is invoked on an instance of that subclass, `AbstractMethodError` may occur. When subclass source is recompiled, the compiler will require implementing the method or making the subclass abstract.

### 6.3. Changing Visibility and Sealed Hierarchies

Reducing visibility of a class or member can cause source consumers to lose access and binaries to encounter `IllegalAccessError`. Increasing visibility is usually less restrictive, though it can still alter the visible API and overload resolution.

Java 17 supports sealed classes/interfaces as a standard feature. If a type is converted to `sealed` with a `permits` list, external subclasses/implementations not in the permitted list will be unable to compile or verify against the new hierarchy. This change must be evaluated like a change in API extensibility policy.

## 7. Method Resolution, `super`, and Common Linkage Errors

### 7.1. `NoSuchMethodError`

This error occurs when bytecode references a method by owner/name/descriptor, but the JVM cannot find a matching method during resolution. Several causes relate to hierarchies:

- The method was removed from the class and is no longer inherited from a superclass/interface.
- The method was moved to a subclass while the symbolic reference still points to the superclass.
- The descriptor changed because parameters or the return type changed.
- The new superclass or interface no longer provides the method the consumer compiled against.

For example, an old binary calls `BaseTask.execute()`. If the new version removes the method from `BaseTask` and declares it only in `CustomTask`, a symbolic reference with owner `BaseTask` is not resolved by searching down into subclasses. The JVM does not search for methods in all child classes of the owner.

### 7.2. `AbstractMethodError`

This error can occur when a method is resolved, but the actual object has no concrete implementation to execute. A typical scenario is adding an abstract method to an interface or superclass that an old implementation/subclass does not yet provide.

### 7.3. `IncompatibleClassChangeError`

This is a category of linkage errors when the class/interface structure or member kind expected by bytecode no longer matches runtime. Examples can include changing a class to an interface, an interface to a class, or method/default method conflicts in certain resolution scenarios.

### 7.4. `VerifyError`

The JVM verifier checks whether bytecode adheres to type safety and class hierarchy rules. Changing superclasses, final/abstract modifiers, or assignability relationships can make old consumer bytecode invalid under the new hierarchy and lead to `VerifyError`.

### 7.5. `ClassCastException`

If a class no longer implements an interface or inherits from a superclass expected by the consumer, a `checkcast` operation may fail at runtime. Old code may have compiled and the class may still load, yet the runtime object is no longer an instance of the cast target type.

### 7.6. `NoClassDefFoundError`

If a superclass or interface is removed from the runtime artifact, dependent classes may fail to load when the JVM needs to resolve the hierarchy. This is a missing-class error at runtime, distinct from a class still existing without the same inheritance relationship as before.

## 8. Impact on Frameworks and Dynamic Class Generation

Hierarchy changes can heavily impact frameworks because many frameworks inspect or generate classes based on inheritance relationships.

### 8.1. Proxies and AOP

Some proxies are created by subclassing the target class. If the class becomes `final`, its constructor becomes inaccessible, or methods can no longer be overridden, proxy generation may fail. Frameworks using interface-based proxies may depend less on a specific class hierarchy, though the interface contract must still remain stable.

### 8.2. ORM and Entity Inheritance

ORMs may use superclasses for mapped fields, identifiers, lifecycle callbacks, or inheritance mapping. Changing superclasses, constructor visibility, or entity relationships can alter mapping and schema behavior.

### 8.3. Mocking and Bytecode Instrumentation

Mocking libraries may subclass target classes or instrument bytecode. Adding `final`, sealed hierarchies, or changing method visibility can prevent mocks from being created or cause test behavior to diverge from production.

### 8.4. Serialization

With Java serialization, changing superclasses and inherited state can affect serialized data. Default `serialVersionUID` is computed from certain characteristics of the class; changing the class declaration or hierarchy can change the default value. When a `Serializable` class changes, explicit `serialVersionUID`, `serialPersistentFields`, custom `readObject`/`writeObject`, and data stored from previous versions must be reviewed.

Do not assume that keeping fields in the child class is sufficient to preserve serialization compatibility if the superclass or serializable hierarchy has changed.

## 9. Designing Safer Hierarchy Changes

### 9.1. Keep the Old Superclass as an Adapter

If an implementation needs to move to a new hierarchy, the old type can be kept and delegated to the new component:

```java
public class LegacyOrder extends BaseEntity {
    private final OrderModel delegate;

    public LegacyOrder(OrderModel delegate) {
        this.delegate = delegate;
    }

    @Override
    public String getId() {
        return delegate.id();
    }
}
```

An adapter is only suitable when the semantics and invariants of the old type can be maintained. If the old superclass provided substantial state or protected extension points, clearly determine which parts the adapter supports.

### 9.2. Add Interfaces First, Migrate Consumers Later

A common roadmap is:

1. Define a new interface representing the contract to be published.
2. Have the existing class implement the interface and release a compatible version.
3. Migrate consumers to depend on the interface rather than the concrete class.
4. Create new implementations against the interface.
5. Retain the old implementation/type during the transition period.
6. Remove the old type in a major release after consumers have migrated.

This approach reduces coupling to a concrete superclass and supports more independent implementation replacement.

### 9.3. Use Composition When Inheritance Is Not Needed

Inheritance creates a subtype relationship and shares contracts. When only code reuse is needed, composition is usually less constraining:

```java
public class OrderService {
    private final TaxCalculator taxCalculator;

    public OrderService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public Money total(Order order) {
        return taxCalculator.calculate(order);
    }
}
```

Replacing the `TaxCalculator` implementation does not necessarily alter `OrderService`'s hierarchy. However, composition also has its own contract; interfaces/dependency injection must be managed like any other API.

### 9.4. Manage Default Methods Carefully

When adding a default method to a public interface:

- Check parent interfaces and other interfaces for matching signatures.
- Check whether superclasses of implementations have a corresponding method.
- Determine whether the default behavior is safe for all old implementations.
- If no valid default behavior exists, consider a new interface or adapter instead of adding a method that unexpectedly throws `UnsupportedOperationException`.
- Test consumers/plugins compiled against the old interface version.

## 10. Binary Compatibility Verification Workflow for Hierarchies

### Step 1: Save Baseline APIs and Artifacts

Retain old JARs, class files, public API reports, dependency graphs, and representative consumers. Record which classes are extensible, which interfaces are SPIs, and which subclasses/implementations reside outside the repository.

### Step 2: Map the Hierarchy

Collect:

- Direct superclass and superinterfaces of each type.
- Subclasses and interface implementations in internal sources.
- Classes proxied or generated by frameworks.
- Protected/public APIs overridden or invoked via `super` by consumers.
- Default methods, bridge methods, and covariant returns.

For compiled artifacts, `javap -v` can display superclasses, interfaces, method descriptors, and bridge flags.

### Step 3: Compare Before/After Hierarchies

Record classes/interfaces that were added, removed, changed kind, moved packages, changed superclass, or changed interface lists. Compare declared and inherited methods/constructors.

### Step 4: Rebuild Consumer Sources

Compile all internal modules and representative implementations. Specifically check subclasses, SPI providers, plugins, and tests using mocks/proxies.

### Step 5: Run Old Binaries Against the New Library

If the product requires binary compatibility, keep consumers compiled with the old library unchanged and run them with the new library artifact. Check startup, class loading, and actual call paths; do not recompile consumers in this test because doing so hides binary errors.

### Step 6: Check Linkage and Dispatch

Watch for errors:

- `NoSuchMethodError`, `AbstractMethodError`.
- `IncompatibleClassChangeError`, `VerifyError`.
- `IllegalAccessError`, `NoClassDefFoundError`.
- `ClassCastException` at casts or framework proxies.

Add tests to verify which method implementation is invoked, especially with default methods, `super` calls, subclasses, and interface references.

### Step 7: Check Serialization and Framework Integration

If the hierarchy participates in serialization, ORM, proxies, AOP, or instrumentation, test data and behavior created with the old version. Run tests on the same runtime and dependency versions as the deployment environment.

### Step 8: Publish the Migration Path

If compatibility cannot be preserved by the change, clearly publish the breaking change, replacement types, migration examples, removal version, and instructions for external implementors/consumers.

## 11. Supporting Tools

### 11.1. `javap`

Inspect class file structure:

```bash
javap -classpath old-library.jar -v com.example.Order
javap -classpath new-library.jar -v com.example.Order
```

Observe:

- `super_class` and `interfaces`.
- Method descriptors and generic signatures.
- Access flags such as `ACC_FINAL`, `ACC_ABSTRACT`, `ACC_BRIDGE`.
- Declared constructors and methods.

### 11.2. japicmp and Revapi

Tools like japicmp or Revapi can compare the public API between two artifact versions, detecting removed types/members, visibility changes, and many forms of binary/source compatibility issues. Configure artifacts, filters, and policies properly. Tools cannot replace tests for reflection, framework-generated classes, or runtime behavior.

### 11.3. Dependency and Runtime Tests

When testing consumers, use the exact dependency graph the application will resolve in production. Two versions of the same library on the classpath can alter test results; separate classloaders of application servers/plugin containers also need to be accounted for if the system uses them.

## 12. Summary Table of Hierarchy Changes and Risks

| Change | Source consumer | Common binary/runtime risks |
|---|---|---|
| Change superclass to unrelated type | Loss of subtype, inherited members, or protected access | `VerifyError`, `NoSuchMethodError`, `ClassCastException`, or dispatch change |
| Change superclass to subclass of old superclass | May still compile, but constructors/overrides change | Constructor chain, method selection, serialization, and behavior change |
| Remove old superclass constructor | Subclasses without valid `super()` fail compilation | `NoSuchMethodError` when invoking constructor descriptor that no longer exists |
| Add method to superclass | May create override or name conflict | Dispatch/behavior changes; source recompilation may pick the new method |
| Add interface abstract method | Implementations may have to add the method | `AbstractMethodError` when calling the method on old implementations |
| Add default method | Usually does not force implementation edits, but can conflict | Dispatch changes or conflict during resolution |
| Remove interface from class | Loss of ability to assign/cast to interface | `ClassCastException`, `IncompatibleClassChangeError` on invokeinterface |
| Remove interface type from runtime | Source cannot resolve type | `NoClassDefFoundError` when the JVM needs to load the type |
| Class changed to interface or vice versa | `extends`/`implements` and instantiation become invalid | `IncompatibleClassChangeError` |
| Add `final` to class | Subclasses fail to compile | `VerifyError` with old subclass binaries |
| Add `abstract` or abstract method | Cannot instantiate or must implement | `InstantiationError` or `AbstractMethodError` |
| Change sealed permits list | Subclasses outside list are disallowed | Compile/verification failure with an invalid hierarchy |

The errors in the table are typical risks, not guaranteed outcomes in every case. Actual outcomes depend on class files, symbolic references, runtime classpath/module path, and executed code paths.

## 13. Checklist Before Releasing a Hierarchy Change

- [ ] Recorded superclasses and superinterfaces before/after the change.
- [ ] Checked subtype relationships that consumers depend on.
- [ ] Found subclasses, implementations, plugins, and SPI providers.
- [ ] Checked constructor chains and superclass constructor descriptors.
- [ ] Reviewed inherited methods, overrides, `super` calls, and protected access.
- [ ] Evaluated new abstract methods and default methods, including interface conflicts.
- [ ] Checked class/interface kind, `final`, `abstract`, and sealed permits.
- [ ] Compared descriptors, bridge methods, and class files using `javap` or API compatibility tools.
- [ ] Recompiled consumer source code.
- [ ] Ran old consumer binaries against the new library if binary compatibility is required.
- [ ] Tested dispatch, casts, reflection, proxies, ORM, and serialization where relevant.
- [ ] Published adapters, deprecations, or migration guides for breaking changes.

## 14. Conclusion

Superclasses, interfaces, and inheritance relationships are part of the runtime contract in Java. Changing them can alter subtype relationships, constructor chains, method resolution, dynamic dispatch, default method selection, and the ability to generate proxies/implementations. Some changes prevent source from compiling; others still allow classes to load but fail only when a specific method, cast, or code path is used.

When migrating libraries or JDKs, compare before/after artifact hierarchies and descriptors, recompile consumers, run old binaries if binary compatibility must be supported, and test behavior of frameworks that depend on inheritance. If the contract must change, use interfaces/adapters or a clear major release roadmap so consumers can transition in a controlled manner.
