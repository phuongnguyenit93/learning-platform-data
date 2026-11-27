# Registering Types and Members for Access via RuntimeHints

## 1. Why Must Reflection Be Registered?

Java reflection allows a program to discover and interact with classes, constructors, methods, and fields at runtime. Spring Framework and many libraries use reflection to instantiate objects, bind data, serialize JSON, read annotations, or invoke components selected from configuration.

On the JVM, classes on the classpath can usually be loaded and accessed via reflection whenever access rules allow. GraalVM Native Image, by contrast, performs reachability analysis at build time under a closed-world model. If a reflection target is only determined from a string name, external metadata, or a rarely executed branch, the tool may fail to recognize which classes/members must be retained.

Spring AOT provides **RuntimeHints** to declare runtime capabilities ahead of time. For reflection, the `hints.reflection()` API lets you register the types and members the application will access. These declarations are collected by Spring AOT and converted into metadata suitable for Native Image.

This lesson walks through identifying the exact classes/members, registering them via `RuntimeHints`, attaching the registrar to the `ApplicationContext`, and testing on the native executable. The goal is to provide enough metadata for actual execution paths without opening reflection more broadly than necessary.

## 2. ReflectionHints and RuntimeHintsRegistrar

The primary APIs reside in the `org.springframework.aot.hint` package:

| API | Responsibility |
|---|---|
| `RuntimeHints` | Aggregates declarations for reflection, resources, proxies, serialization, and JNI |
| `ReflectionHints` | Registers classes and members accessed via Java reflection |
| `MemberCategory` | Selects groups of constructors, methods, or fields to support |
| `ExecutableMode` | Describes how an executable member is used, such as invoke or introspect |
| `RuntimeHintsRegistrar` | Extension point for declaring hints in Spring AOT |
| `@ImportRuntimeHints` | Links a registrar to Spring configuration |

A minimal registrar:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class ApplicationReflectionHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        // Register types/members needing reflection here
    }
}
```

For Spring AOT to discover the registrar, attach it to a configuration belonging to the `ApplicationContext`:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApplicationReflectionHints.class)
class NativeConfiguration {
}
```

The registrar runs during AOT preparation. Creating a `RuntimeHints` instance inside business code at runtime does not alter the metadata of an already compiled native executable.

## 3. Identifying the Exact Reflection Contract Before Declaring

Before writing hints, read the code path that uses reflection and list the specific members. For example, a legacy library reads a class name from configuration, then instantiates an object:

```java
String className = settings.getProperty("invoice.handler");
Class<?> type = Class.forName(className);
Object handler = type.getDeclaredConstructor().newInstance();

Method method = type.getDeclaredMethod("handle", Invoice.class);
method.invoke(handler, invoice);
```

The contract to support includes:

- The target class loaded by name.
- The no-argument constructor invoked via reflection.
- The `handle(Invoice)` method invoked via reflection.
- If the library accesses fields directly, those fields must also be considered separately.

Do not register every member in a package just because you do not yet know exactly what the library uses. Identify the classes selectable from configuration, constructor/method signatures, and how the library accesses them. If the class name can take multiple values, register each class in the supported set or design a static registry so the target set is clearly known.

## 4. Registering a Type and Constructor

Suppose the application has the class:

```java
package com.example.invoice;

public final class InvoiceHandler {

    public InvoiceHandler() {
    }

    public void handle(Invoice invoice) {
        // Process invoice
    }
}
```

If the code only needs to invoke public constructors via reflection, register the corresponding category:

```java
hints.reflection().registerType(
        InvoiceHandler.class,
        MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
);
```

If calling a declared but non-public constructor is required, consider `INVOKE_DECLARED_CONSTRUCTORS` along with actual Java access rules. A declared category does not automatically mean all Java module/access restrictions are bypassed.

If only one specific constructor is needed, you can register the executable member instead of an entire group:

```java
hints.reflection().registerConstructor(
        InvoiceHandler.class.getDeclaredConstructor(),
        ExecutableMode.INVOKE
);
```

This specific approach requires handling `NoSuchMethodException`. It clearly documents the constructor used by the library and avoids retaining unnecessary constructors.

## 5. Registering Methods to Invoke

If the library calls `handle(Invoice)` via `Method.invoke`, you can register the specific method:

```java
hints.reflection().registerMethod(
        InvoiceHandler.class.getDeclaredMethod(
                "handle", Invoice.class),
        ExecutableMode.INVOKE
);
```

Method-specific registration requires the exact name and exact parameter types. If a method is overloaded, each signature is a separate member. If code uses an inherited method from a superclass, determine which type declares the member and register accordingly; `getDeclaredMethod` only finds methods declared directly on the class.

When multiple public methods on a class need to be invoked reflectively, you can use:

```java
hints.reflection().registerType(
        InvoiceHandler.class,
        MemberCategory.INVOKE_PUBLIC_METHODS
);
```

Choose between categories and specific members according to the contract: categories are convenient when many members of the same group are genuinely needed; specific registration is easier to review when only a few methods are used.

## 6. Registering Fields

Some mapper or serializer libraries access fields directly instead of getters/setters. Example:

```java
Field code = Invoice.class.getDeclaredField("code");
code.setAccessible(true);
code.set(invoice, "INV-2026-01");
```

If declared fields on the class need access, you can use the category:

```java
hints.reflection().registerType(
        Invoice.class,
        MemberCategory.DECLARED_FIELDS
);
```

Or register a specific field:

```java
hints.reflection().registerField(
        Invoice.class.getDeclaredField("code"));
```

Registering fields does not mean constructors and methods are also permitted to be called. You must distinguish:
- Introspection: reading name/type/modifier metadata.
- Field access: reading or writing values.
- Invocation: calling methods or constructors.

If a library only uses getters/setters, there is no need to expose a field simply because the field exists.

## 7. Public Members vs. Declared Members

Java reflection provides different APIs:

| Reflection API | Scope |
|---|---|
| `getMethods()` | Public methods of the class and inherited public methods |
| `getDeclaredMethods()` | Methods declared directly on the class, including non-public |
| `getFields()` | Public fields, potentially including inherited fields |
| `getDeclaredFields()` | Fields declared directly on the class |
| `getConstructor(...)` | Public constructor with matching signature |
| `getDeclaredConstructor(...)` | Constructor declared on the class, including non-public |

Example:

```java
class BaseHandler {
    public void validate() {}
}

class InvoiceHandler extends BaseHandler {
    private String code;

    public void handle(Invoice invoice) {}
}
```

`InvoiceHandler.class.getMethods()` can see the inherited `validate()`, whereas `getDeclaredMethods()` only returns methods declared on `InvoiceHandler`. Therefore, registering `INVOKE_DECLARED_METHODS` for a subclass should not be assumed to automatically register every superclass method.

If code invokes `validate()` via reflection, check the actual type/member being looked up and register on `BaseHandler` when needed.

## 8. Introspection and Invocation Are Two Different Requirements

One framework may only list methods to read annotations, names, and parameter types; another framework may invoke methods via reflection. These two behaviors require different metadata.

| Behavior | Hints to Consider |
|---|---|
| Read method metadata | `INTROSPECT_PUBLIC_METHODS` or `INTROSPECT_DECLARED_METHODS` |
| Invoke method | `INVOKE_PUBLIC_METHODS` or `INVOKE_DECLARED_METHODS` |
| Read constructor metadata | Constructor introspection category |
| Create object via reflection | Constructor invocation category or specific constructor registration |
| Read/write field | Field category or specific field registration |

Registering introspection does not mean a method can be invoked. Conversely, registering invocation should not be assumed to allow every form of introspection. If code both reads metadata and invokes, register both capabilities as needed.

Enum names and semantics must be verified against the Spring Framework version in the project. When using broad categories, consider whether the type hierarchy or inherited members need separate hints.

## 9. Complete Registrar for a Class

The example below registers a specific constructor and method:

```java
package com.example.invoice;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class InvoiceHandlerHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        try {
            hints.reflection().registerConstructor(
                    InvoiceHandler.class.getDeclaredConstructor(),
                    ExecutableMode.INVOKE
            );

            hints.reflection().registerMethod(
                    InvoiceHandler.class.getDeclaredMethod(
                            "handle", Invoice.class),
                    ExecutableMode.INVOKE
            );
        }
        catch (NoSuchMethodException ex) {
            throw new IllegalStateException(
                    "InvoiceHandler reflection contract changed", ex);
        }
    }
}
```

Registering the registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceHandlerHints.class)
class InvoiceNativeConfiguration {
}
```

If the constructor/method is renamed or has its signature changed during refactoring, the registrar will fail right at the AOT step rather than waiting for a rare request in production. This is an important benefit of declaring reflection contracts centrally.

## 10. Registering Multiple Selectable Implementations

If runtime configuration allows choosing one of several handlers, the set of classes must be known at build time:

```java
final class HandlerHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        registerHandler(hints, StandardInvoiceHandler.class);
        registerHandler(hints, PriorityInvoiceHandler.class);
    }

    private void registerHandler(
            RuntimeHints hints, Class<?> type) {
        hints.reflection().registerType(
                type,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

The example assumes both handlers have constructors and public methods that need to be used. In a real application, register the exact members on each class. If an implementation is loaded from a new Java plugin after the native image is released, adding a JAR to the classpath does not cause the binary to compile new classes; you must rebuild the image or change the plugin architecture.

## 11. RuntimeHintsPredicates: Testing Declared Metadata

You can write unit tests confirming that the registrar adds the expected hints:

```java
@Test
void registersInvoiceHandlerConstructor() throws Exception {
    RuntimeHints hints = new RuntimeHints();

    new InvoiceHandlerHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.reflection()
            .onConstructor(
                    InvoiceHandler.class.getDeclaredConstructor())
            .test(hints))
            .isTrue();
}
```

The test requires JUnit, AssertJ, and Spring AOT hint test support. The predicate API may differ between versions; check the project's packages/Javadoc. Additional predicates can be written for specific methods or fields.

Unit tests prove the registrar creates the expected metadata in the `RuntimeHints` object. They do not yet prove the registrar is discovered by Spring AOT or that the native executable actually runs. Therefore, both layers must be verified:

1. Unit test the registrar.
2. AOT build confirms the registrar is collected.
3. Native integration test or run the actual executable through the reflection path.

## 12. When to Use RuntimeHintsRegistrar vs. Library Metadata?

Some dependencies already ship their own reachability metadata or Spring `RuntimeHints`. Before writing duplicate hints, check whether the library in use already supports GraalVM Native Image.

Prioritize in order:

- Use hints provided by Spring Framework/Spring Boot or the dependency library.
- Use `RuntimeHintsRegistrar` for the application's own reflection contracts.
- Use GraalVM metadata directly when declarations cannot be adequately expressed by Spring abstractions, following the format supported by your Native Image version.

Do not edit generated metadata directly after AOT. Fix the registrar or metadata source, then rebuild so changes are applied reproducibly.

## 13. Diagnosing Reflection Errors in a Native Executable

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ClassNotFoundException` | Dynamically selected class is not in the image | Register type/metadata, check class name |
| `NoSuchMethodException` | Wrong signature or method/constructor not described | Match name, parameter types, and registrar |
| `IllegalAccessException` | Member lacks appropriate access permission | Check public/declared and access hints |
| Method can be found but cannot be invoked | Only introspection was registered | Add invocation hint |
| Field mapper fails | Library accesses fields directly but only methods were registered | Register appropriate field access |
| Fails only for secondary implementation | Secondary class was not registered | Add type/members for every valid option |
| Works on JVM, fails on native | Reflection target was not recognized by reachability analysis | Check runtime hints and test executable |

Not every reflection error is caused by missing hints. Wrong class names, different classloaders, module access, library bugs, or signature changes can also cause errors. Read the exception and identify the actual member being accessed before expanding metadata.

## 14. Hands-On Workflow: Registering Reflection for a Dynamic Handler

**Context:** a Spring Boot application has configuration selecting a handler by implementation name. A legacy library instantiates the handler and invokes a method via reflection.

**Step 1 — Identify the handler set.** List all valid classes and the constructors/methods used by the library.

**Step 2 — Write `RuntimeHintsRegistrar`.** Register required constructors and methods for each class; use categories when multiple members in the same group are genuinely needed.

**Step 3 — Import the registrar.** Attach `@ImportRuntimeHints` to a configuration belonging to the `ApplicationContext`.

**Step 4 — Write unit tests.** Use `RuntimeHintsPredicates` to verify constructors/methods exist in `RuntimeHints`.

**Step 5 — Run Spring AOT and native build.** Observe logs, verify hints are collected, and produce the executable.

**Step 6 — Test all handlers.** Run the executable with each configuration option, verifying results and error branches.

**Step 7 — Document scope.** Record the list of classes/members, why reflection is needed, and corresponding tests so future refactors can update metadata.

Completion criteria: all valid implementations run on native, members are registered for the right operations, registrar tests pass, and whole-package reflection does not need to be opened.

## 15. Conclusion

`RuntimeHints` lets Spring AOT declare classes and members accessed via reflection before GraalVM Native Image compiles the executable. Choose the exact types, constructors, methods, and fields; distinguish public from declared, inherited members, and introspection from invocation; then attach the registrar to the `ApplicationContext` and test the metadata.

With Spring Boot Native Image, treat reflection contracts as a controllable part of build configuration. Register the smallest scope that satisfies actual paths, leverage existing library metadata, and verify with the native executable. This practice reduces runtime-only failures and keeps AOT configuration maintainable.
