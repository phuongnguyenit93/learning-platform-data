# Changing Signatures, Return Types, and `throws`: Impact on Java API Consumers

When a Java API changes, the library source code may compile successfully, yet applications using the library may still fail to compile, fail to link against the new bytecode, or run with different behavior. Three aspects need to be evaluated: **source compatibility**, **binary compatibility**, and **behavioral compatibility**.

This article focuses on changing parameters, return types, and `throws` clauses, especially for public/protected methods and interfaces used across modules.

## 1. Checking Compatibility at Three Stages

Changing an API requires three separate checks: **source compatibility** when recompiling the client, **binary compatibility** when running old client bytecode with the new library, and **behavioral compatibility** when comparing results/exceptions against the published contract. In this article, the differences between Java signatures, JVM descriptors, and `throws` clauses are why these three checks can yield different conclusions.

## 2. What Does a Method Signature Include?

In Java, the signature used to distinguish methods is based on the **method name, type parameters (if any), and formal parameter types**. Parameter variable names are not part of the signature; the return type and `throws` clause are not used to distinguish overloads.

```java
String find(long id)
String find(String id) // valid overload: different parameter type
```

Two declarations with the same name and the same parameters but different return types cannot coexist:

```java
String find(long id)
Product find(long id) // Cannot overload by return type alone
```

In bytecode, a JVM method descriptor includes the parameter types and the return type, but not the `throws` clause. This explains why changing the return type can prevent old bytecode from finding the method, whereas changing `throws` usually does not alter binary linkage.

## 3. Changing Parameter Types

Suppose API v1 declares:

```java
public User findUser(long id)
```

If v2 only has `findUser(String id)`, a client calling `findUser(42L)` will not compile against the new API. Old bytecode also requires a descriptor with a `long` parameter; if that descriptor disappears, the call may encounter `NoSuchMethodError` at runtime.

A less disruptive path is to keep the old method as a bridge and add an overload:

```java
public User findUser(long id) {
    return findUser(Long.toString(id));
}

public User findUser(String id) {
    return lookupByTextId(id);
}
```

This is a structural example; `User` and `lookupByTextId` need to be defined according to the application. Keeping the old method gives existing clients time to migrate, after which it can be marked with `@Deprecated` and removed only in a deliberate release.

Adding overloads can also make existing source code ambiguous. For example, adding an overload accepting `Integer` alongside an overload accepting `String` can cause a `findUser(null)` call to no longer resolve to a single method. When changing overloads, check calls involving `null`, lambdas, method references, and boxing/unboxing.

## 4. Changing Return Types

Suppose v1 provides:

```java
public String findName(String id)
```

If changed directly to `public Product findName(String id)`, clients assigning the result to a `String` may fail to compile. Java does not allow keeping two methods with the same name and parameters that differ only in return type.

This change can also break binary compatibility: the return type belongs to the JVM descriptor. Old bytecode invokes the descriptor returning `String`; the new descriptor returning `Product` does not automatically replace the old descriptor. If the old method no longer exists, clients may encounter `NoSuchMethodError`.

A safer migration approach is to add a new method with a clear name, keep the old method as a bridge, and mark it deprecated:

```java
@Deprecated(since = "2.0", forRemoval = false)
public String findName(String id) {
    Product product = findProduct(id);
    return product == null ? null : product.name();
}

public Product findProduct(String id) {
    return lookupProduct(id);
}
```

This is an illustrative example; `Product` is assumed to have a `name()` accessor (for example, a record), while `lookupProduct` must actually be implemented. Clearly define the behavior when data is not found: `null`, `Optional`, or an exception. Do not silently change that rule in an upgrade.

Java allows covariant return types when overriding (the new return type is a compatible subtype of the old type); the compiler can generate a bridge method to support linkage. This is a special case and does not mean every return type change is safe. With generics, changing type parameters while keeping the same erasure may still link at the bytecode level, yet cause compilation errors or cast errors at runtime.

## 5. Changing the `throws` Clause

The `throws` clause declares the checked exceptions that a method can throw. It is not part of the signature used for overloading and is not included in the JVM descriptor, yet it affects source code compilation.

### Adding a Checked Exception

If an API changes from:

```java
public String load(String id)
```

to:

```java
public String load(String id) throws IOException
```

recompiled callers may have to catch `IOException` or declare it with `throws`. Implementing classes and overriding methods must also be reviewed; an override cannot declare checked exceptions broader than what the parent method's contract allows.

Because the descriptor does not change, merely adding `throws IOException` usually does not break binary linkage. However, if the new version actually throws `IOException`, old client bytecode that does not handle the exception can let it escape at runtime. The JVM does not enforce checked exception rules on behalf of the compiler.

### Removing a Checked Exception or Adding an Unchecked Exception

Removing a checked exception usually does not change the descriptor, but when recompiling the client, a `catch` block catching only that exception may no longer be valid if no operations remain in the `try` block that can throw it. Check both callers and overriding classes.

Exceptions such as `IllegalArgumentException` and `IllegalStateException` do not need to be declared in `throws`. Starting to throw them usually does not force callers to modify code to compile, yet it can still break behavioral compatibility if clients rely on normal results or a different error type.

## 6. Java 17+ Example: Adding a New API and Keeping the Old One

The following example keeps the old method returning a `String` name while adding a default method that returns `Product` and declares `IOException`. Because the new method is `default`, existing implementing classes do not immediately have to implement a new abstract method.

Save to `ApiEvolutionDemo.java`:

```java
import java.io.IOException;

public class ApiEvolutionDemo {
    @SuppressWarnings("deprecation")
    public static void main(String[] args) throws IOException {
        CatalogApi api = new InMemoryCatalogApi();

        System.out.println(api.findName("42"));
        System.out.println(api.findProduct("42"));

        try {
            api.findProduct("missing");
        } catch (IOException ex) {
            System.out.println("Lookup failed: " + ex.getMessage());
        }
    }
}

interface CatalogApi {
    @Deprecated(since = "2.0", forRemoval = false)
    String findName(String id);

    @SuppressWarnings("deprecation")
    default Product findProduct(String id) throws IOException {
        String name = findName(id);
        if (name == null) {
            throw new IOException("No product for id " + id);
        }
        return new Product(id, name);
    }
}

record Product(String id, String name) {}

final class InMemoryCatalogApi implements CatalogApi {
    @Override
    public String findName(String id) {
        return "42".equals(id) ? "Keyboard" : null;
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ApiEvolutionDemo.java
java ApiEvolutionDemo
```

Program output:

```text
Keyboard
Product[id=42, name=Keyboard]
Lookup failed: No product for id missing
```

Old clients can still call `findName`; new clients can switch to `findProduct` and handle `IOException`. This is an illustrative transition strategy. In a real system, if the old data is insufficient to construct a `Product`, a default method is not appropriate; implement a migration strategy based on the actual semantics of the API.

## 7. Distinguishing Modifying Signatures from Adding New Methods

Changing the parameter types or return type of a published method can remove the descriptor referenced by old bytecode. In contrast, adding an abstract or default method preserves the descriptors of existing methods, but carries its own risks: implementing classes may lack an implementation, or the inheritance hierarchy may develop conflicts. Therefore, when new functionality is needed, evaluate adding an additional method or a sub-interface before modifying the old signature directly.

## 8. Impact Summary Table

| Change | Source Code | Old Bytecode | Risk Mitigation |
|---|---|---|---|
| Change parameter types | Existing calls may fail to compile | Old descriptor may disappear; may encounter `NoSuchMethodError` | Keep the old method and add a forwarding overload |
| Change return type | Clients using the old type may fail to compile | Descriptor includes the return type; may encounter `NoSuchMethodError` | Add a new method with a clear name; deprecate the old method |
| Add a checked exception to `throws` | Callers may have to catch or declare the exception | Descriptor is unchanged; usually still links | Consider a new API, update documentation, and test at runtime |
| Remove a checked exception | Some `catch` blocks may become invalid on recompilation | Descriptor is unchanged | Review and update callers |
| Start throwing an unchecked exception | Usually still compiles | Usually still links | Treat as a behavioral change and update the contract |
| Add an abstract method to an interface | Implementations may require changes | Calling the new method on an old implementation may fail | Use a default method when semantically appropriate, or create an extension interface |
| Add an overload | Some calls may become ambiguous | Usually preserves old descriptors | Check `null`, lambdas, method references, and overload resolution |

These are general guidelines. Specific outcomes also depend on the before/after descriptors, generic erasure, inheritance relationships, and bridge methods generated by the compiler.

## 9. Pre-Release Verification Process

1. **List the changed contracts:** public/protected methods, interfaces, parameters, return types, checked exceptions, and generics.
2. **Recompile sample clients:** include callers that handle exceptions, overloaded calls, and custom classes implementing the interface.
3. **Check binary compatibility:** if applications are not recompiled together with the library, run smoke tests with bytecode from the previous version and check the descriptors that are still needed.
4. **Check behavior:** verify results, not-found cases, exception types, and edge cases.
5. **Provide a transition period:** keep old methods when possible, add overloads or new methods, mark them with `@Deprecated`, and publish a removal plan and migration guide.
6. **Remove intentionally:** before deleting an old API, search for usages in the repository, review published dependencies, and document the change clearly in the release notes.

## 10. Checklist

- [ ] Do parameter changes remove any old descriptors?
- [ ] Is the return type changed directly, or are generics/erasure changed?
- [ ] Does a new checked exception require modifying callers or overrides?
- [ ] Do new overloads make `null`, lambda, or method reference calls ambiguous?
- [ ] Does the interface add an abstract method that many implementations must support?
- [ ] Have both compiling new clients and running old bytecode been tested?
- [ ] Are transition methods, `@Deprecated`, and migration guides provided when needed?

## References

- [Java Language Specification 17 — Method Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2)
- [Java Language Specification 17 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [Java Virtual Machine Specification 17 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3)
