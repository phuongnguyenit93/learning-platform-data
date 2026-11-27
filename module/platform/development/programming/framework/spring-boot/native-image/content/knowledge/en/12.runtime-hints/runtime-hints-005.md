# ReflectionHints and MemberCategory Access Levels

## 1. Why Does Native Image Need ReflectionHints?

Java applications on the JVM can routinely use reflection to look up classes, constructors, methods, or fields at runtime. For example, a framework might read annotations, instantiate objects from class names in configuration, or invoke getters from metadata. The JVM can perform these operations as long as the class/member exists and access rules permit it.

GraalVM Native Image performs reachability analysis at build time under a closed-world model. The tool cannot always infer reflection targets selected from runtime strings or dynamic metadata. If a class/member is not described and not recognized automatically, that element may be omitted or disallowed for reflection operations in the executable.

Spring provides **RuntimeHints** to declare required runtime capabilities ahead of time. Within it, **ReflectionHints** describes the classes and members that an application or library will access via reflection. **MemberCategory** lets you select the required access level, such as constructors, methods, or fields.

In the **SPRING_BOOT_NATIVE_IMAGE** module, understanding ReflectionHints properly helps resolve native compatibility without registering overly broad reflection. The goal is to retain only the classes/members actually used, reduce runtime errors, and avoid bloating the executable with unnecessary metadata.

## 2. How Does Reflection Differ from Regular Java Calls?

Direct call:

```java
Invoice invoice = new Invoice();
invoice.setCode("INV-001");
```

The compiler sees the `Invoice` type, constructor, and `setCode` method in the bytecode. Reachability analysis can usually trace these static calls.

Reflection call:

```java
String className = configuration.getProperty("invoice.type");
Class<?> type = Class.forName(className);
Object instance = type.getDeclaredConstructor().newInstance();
Method setter = type.getMethod("setCode", String.class);
setter.invoke(instance, "INV-001");
```

Here, the value of `className` may only be known when the application runs. Native Image cannot always infer which class/member will be chosen. If the reflection target is neither registered nor automatically detected, the operation can fail in the native executable even though the JVM build works.

Not all reflection requires hints. Cases with static targets already supported by Spring AOT or libraries may be analyzed and registered automatically. Add hints based on observed errors or verified reflection requirements.

## 3. Where Do RuntimeHints and ReflectionHints Live?

Spring AOT provides these APIs in the package:

```java
org.springframework.aot.hint
```

Key concepts:

| API | Role |
|---|---|
| `RuntimeHints` | Collection of runtime capability declarations such as reflection, resources, proxies, and serialization |
| `ReflectionHints` | Registers types, constructors, methods, and fields requiring reflection access |
| `MemberCategory` | Reflection access permission groups that can be registered per class |
| `TypeReference` | Represents a reference to a type by name/type metadata |
| `RuntimeHintsRegistrar` | Extension point for libraries/applications to register hints during Spring AOT |

A typical registrar:

```java
public final class InvoiceRuntimeHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        // Register required reflection/resources/proxies
    }
}
```

Then attach the registrar to Spring configuration:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceRuntimeHints.class)
class InvoiceConfiguration {
}
```

Spring AOT collects hints while processing the application. Appropriate information is forwarded to Native Image for reachability analysis and executable generation.

## 4. Which Permissions Does MemberCategory Represent?

`MemberCategory` is an enum describing member groups that reflection needs to use. Common categories include:

| Category | General meaning |
|---|---|
| `INVOKE_PUBLIC_CONSTRUCTORS` | Invoke public constructors via reflection |
| `INVOKE_DECLARED_CONSTRUCTORS` | Invoke constructors declared on the type, including non-public constructors where supported |
| `INVOKE_PUBLIC_METHODS` | Invoke public methods via reflection |
| `INVOKE_DECLARED_METHODS` | Invoke methods declared on the type |
| `PUBLIC_FIELDS` | Access public fields via reflection |
| `DECLARED_FIELDS` | Access fields declared on the type |
| `INTROSPECT_PUBLIC_CONSTRUCTORS` | Inspect metadata of public constructors |
| `INTROSPECT_DECLARED_CONSTRUCTORS` | Inspect metadata of declared constructors |
| `INTROSPECT_PUBLIC_METHODS` | Inspect metadata of public methods |
| `INTROSPECT_DECLARED_METHODS` | Inspect metadata of declared methods |
| `INTROSPECT_PUBLIC_FIELDS` | Inspect metadata of public fields |
| `INTROSPECT_DECLARED_FIELDS` | Inspect metadata of declared fields |
| `UNSAFE_ALLOCATED` | Support instance allocation via unsafe mechanisms supported by Native Image |

Check the exact enum names and detailed semantics against the Spring Framework version in use. In particular, `INTROSPECT_*` categories primarily allow querying metadata; `INVOKE_*` or field access categories support acting on members. **You can introspect a method without permission to invoke it**, and vice versa; if code needs both, register both capabilities explicitly.

Declared-level categories generally cover members declared directly on the type; do not assume they automatically cover all inherited members from superclasses or interfaces in every situation. When specific members are needed, register those exact members or the corresponding type hierarchy.

## 5. Registering by MemberCategory

Example of a class with a public constructor, public methods, and a declared field:

```java
public class Invoice {
    private String code;

    public Invoice() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
```

If a library uses reflection to invoke the constructor and getters/setters, you can register:

```java
final class InvoiceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                Invoice.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

This snippet registers the public constructors and public methods of `Invoice`. It does not need field registration because the example accesses fields via getters/setters. If the library uses `Field.setAccessible(true)` to access `code` directly, appropriate field access must be declared.

This approach is convenient when a class has multiple members in the same category that need to be accessed. When only one specific constructor or method is needed, registering that exact member is easier to review and grants fewer permissions.

## 6. Registering a Specific Constructor or Method

ReflectionHints also allows registering a specific executable rather than opening up an entire member category.

Constructor example:

```java
hints.reflection().registerConstructor(
        Invoice.class.getDeclaredConstructor(),
        ExecutableMode.INVOKE
);
```

Method example:

```java
hints.reflection().registerMethod(
        Invoice.class.getDeclaredMethod("setCode", String.class),
        ExecutableMode.INVOKE
);
```

Import `java.lang.reflect.Executable` or use the `org.springframework.aot.hint.ExecutableMode` enum according to the corresponding API version. `getDeclaredConstructor` and `getDeclaredMethod` can throw `NoSuchMethodException`, so registrar code must handle the exception—such as via a helper method or a `try/catch` converting it into a clear build failure.

A more complete example:

```java
final class InvoiceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        try {
            hints.reflection().registerConstructor(
                    Invoice.class.getDeclaredConstructor(),
                    ExecutableMode.INVOKE);

            hints.reflection().registerMethod(
                    Invoice.class.getDeclaredMethod(
                            "setCode", String.class),
                    ExecutableMode.INVOKE);
        }
        catch (NoSuchMethodException ex) {
            throw new IllegalStateException(
                    "Invoice reflection contract changed", ex);
        }
    }
}
```

Register methods by exact signature: method name, parameter count, and parameter types. If a method is overloaded, registering the wrong signature will not guarantee that the method called at runtime is supported.

## 7. Field Access: Introspection and Read/Write

Some serializers or mappers access fields directly instead of through getters/setters. For example:

```java
Field codeField = Invoice.class.getDeclaredField("code");
codeField.setAccessible(true);
codeField.set(invoice, "INV-002");
```

In this case, appropriate field access must be registered. Using a category:

```java
hints.reflection().registerType(
        Invoice.class,
        MemberCategory.DECLARED_FIELDS
);
```

If only a specific field is needed, use the field registration API for your Spring Framework version, for example:

```java
hints.reflection().registerField(
        Invoice.class.getDeclaredField("code"));
```

Handle `NoSuchFieldException` inside the registrar. Registering a field does not automatically allow all method reflection on the class; constructors/methods must be declared separately when used.

**Distinction:**

- Introspection: querying a field's name, type, modifiers, or metadata.
- Read/write: getting or setting field values via reflection.
- Invocation: calling methods/constructors.

Register only the permissions matching the behavior the library actually needs. Do not open all declared fields and methods if only a single field is used.

## 8. How Do Public and Declared Members Differ?

In Java reflection:

- Public members can be inherited from superclasses or interfaces.
- Declared members are those declared directly in a class/interface, including private/protected/package-private members per reflection rules.
- `getMethods()` and `getFields()` differ from `getDeclaredMethods()` and `getDeclaredFields()`.

Example:

```java
class BaseEntity {
    public void validate() {}
    protected String id;
}

class Invoice extends BaseEntity {
    private String code;
    public void submit() {}
}
```

With `Invoice.class.getMethods()`, reflection sees both `submit()` and the inherited `validate()`. With `getDeclaredMethods()`, only methods declared directly on `Invoice` are returned. Similarly, `getDeclaredFields()` on `Invoice` sees `code`, not the superclass field `id`.

Therefore, when registering `INVOKE_DECLARED_METHODS` for `Invoice`, do not assume that `validate()` from `BaseEntity` is also registered. If code accesses inherited members, consider registering the type/members on the corresponding superclass.

## 9. Introspect Does Not Mean Invoke

A framework might only read metadata to build a schema or binding without invoking methods/constructors via reflection. For example, it may need to list annotations and parameter types of public methods:

```java
for (Method method : Invoice.class.getMethods()) {
    System.out.println(method.getName());
}
```

In this case, an introspection category is more appropriate than an invocation category if there is no reflective method invocation. Conversely, if the framework calls `method.invoke(...)`, the corresponding invoke permission must be registered.

| Behavior in code | Hint group to consider |
|---|---|
| Listing methods and reading metadata | Appropriate `INTROSPECT_*` |
| Invoking a method via `Method.invoke` | `INVOKE_*` or registering the specific method with `INVOKE` |
| Listing constructors | Constructor introspection |
| Instantiating via `Constructor.newInstance` | Constructor invocation |
| Listing field metadata | Field introspection |
| Reading/writing fields via reflection | Field access category or registering the specific field |

Specific APIs and support levels depend on the Spring/GraalVM version. Use Native Image tracing/diagnostic output and tests to confirm; do not rely solely on guessing from enum names.

## 10. Combining MemberCategory with @ImportRuntimeHints

A registrar must be discovered by Spring AOT. Common wiring approach:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceHints.class)
class InvoiceConfiguration {

    @Bean
    Invoice invoice() {
        return new Invoice();
    }
}
```

`@ImportRuntimeHints` links the registrar to the configuration class. Spring AOT invokes the registrar while collecting runtime hints. If the registrar is not imported/registered or the configuration class is outside the AOT context, the hints may not be generated.

Another option is registering the registrar through Spring's extension mechanism for libraries. For regular applications, the annotation makes it clear which configuration is responsible for supplying hints.

Do not call `registerHints` arbitrarily at runtime expecting Native Image to update the executable. Hints must be present during the AOT/build phase before the compiler produces the binary.

## 11. Testing Hints with RuntimeHintsPredicates

Spring provides utilities to test whether a `RuntimeHints` instance registers the expected reflection entry. For example:

```java
@Test
void invoiceConstructorIsRegistered() throws Exception {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceHints().registerHints(hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.reflection()
            .onConstructor(Invoice.class.getDeclaredConstructor())
            .test(hints)).isTrue();
}
```

This example requires Spring test support/AssertJ and imports for `RuntimeHints`, `RuntimeHintsPredicates`, and JUnit. Specific predicates may vary by Spring version. The idea is to verify registered metadata in unit tests before running a full native build.

Methods or types can be checked similarly. Unit tests verify that the registrar declares the right hints, but **do not prove** that the entire executable contains the metadata and runs properly. Native integration tests or running the actual binary are still required to cover the code path.

## 12. ReflectionHints and GraalVM Metadata

Spring `RuntimeHints` is an application/framework-level API, whereas GraalVM Native Image uses reachability metadata to perform its analysis. Spring AOT converts the collected hints into the format Native Image understands.

Some libraries ship built-in metadata (reachability metadata) so users do not have to declare every member manually. When upgrading dependency versions, metadata may be updated alongside the library. Do not add duplicate hints blindly; first check whether the library already supports native and whether its metadata is recognized.

If you need to declare GraalVM metadata directly, the supported format/mechanism depends on the GraalVM version and Native Build Tools. In Spring Boot projects, prefer `RuntimeHints` when possible so configuration ties into the Spring AOT lifecycle and remains easy to test.

## 13. Common Errors

| Symptom | Possible cause | How to resolve |
|---|---|---|
| `ClassNotFoundException` during reflection | Class is unreachable or runtime class name is incorrect | Identify the target and register the type/metadata |
| `NoSuchMethodException` | Constructor/method signature does not exist or differs from the hint | Match the exact parameter types and member |
| `IllegalAccessException` | Member is not opened for the required operation | Register the appropriate category/member and check Java access rules |
| Reflection metadata exists, yet method still cannot be called | Only introspection was registered, not invocation | Add the corresponding `INVOKE` hint |
| Field serializer error | Only methods/constructors were registered, but library accesses fields directly | Add the appropriate field hint |
| Inherited member not supported | Only declared members of subclass were registered | Register members on the required superclass/interface |
| Hints missing from native output | Registrar was not discovered by Spring AOT | Check `@ImportRuntimeHints` and the AOT context |
| JVM works, native fails | JVM reflection is more permissive than closed-world analysis | Run native integration tests and inspect hints/metadata |

## 14. Hands-on Exercise: Minimal Registration for a DTO

**Context:** an application uses a legacy library that relies on reflection to instantiate `Invoice`, call `setCode`, and read `getCode`.

**Step 1 — Create the DTO.** Declare a public constructor and getters/setters.

**Step 2 — Identify reflection behavior.** Read the library code or stack trace to determine the exact constructor, methods, or fields accessed.

**Step 3 — Write the registrar.** If only the constructor is called, register the constructor; if setters/getters are called, register the exact methods or the public methods category.

**Step 4 — Import hints.** Attach the registrar via `@ImportRuntimeHints` on a configuration belonging to the `ApplicationContext`.

**Step 5 — Write unit tests.** Use `RuntimeHintsPredicates` to verify the required entry is present.

**Step 6 — Build natively.** Run Spring AOT and GraalVM Native Image, watching the logs if the compiler warns about reflection metadata.

**Step 7 — Run the binary.** Call the endpoint that goes through the legacy library and verify both success and failure cases.

Completion criteria: register only members that are genuinely used; hint tests pass; the native executable runs the reflection path cleanly; do not rely on passing JVM tests to conclude native compatibility.

## 15. Principles for Choosing MemberCategory

When deciding on a category, answer in order:

1. Does the application need to **read metadata** or perform an action?
2. If performing an action, is it instantiating, invoking a method, or reading/writing a field?
3. Is the member public or declared/non-public?
4. Which class owns the member, and is it inherited from a superclass?
5. Can you register a specific member instead of an entire category?
6. Does the library already supply reachability metadata or Spring hints?

A broad hint can cause many members to be retained and increase required metadata. An overly narrow hint can cause errors to surface only on rare code paths. Choose the smallest scope that satisfies the actual contract, then verify with native tests.

## 16. Conclusion

**ReflectionHints** lets Spring AOT describe classes/members accessed via reflection in a Native Image executable. **MemberCategory** distinguishes operation groups such as introspection, constructor/method invocation, and field access. Understanding the difference between public and declared members, inherited members, and introspect versus invoke helps you register the exact permissions needed.

In Spring Boot Native Image applications, prefer `RuntimeHints`/`RuntimeHintsRegistrar`, wire registrars into Spring AOT, test metadata with unit tests, and verify with the native executable. This approach reduces runtime reflection failures, keeps configuration intentional, and avoids expanding metadata beyond actual needs.
