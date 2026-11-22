# Encapsulation as an Attack Surface Reduction Layer

## 1. Encapsulation and Attack Surface

In Java, **encapsulation** is the practice of organizing state and behavior so that users of a component can only access the operations that the component intentionally exposes. A class can keep data in private fields, provide controlled methods, and hide implementation classes behind a stable interface or API.

In the Java Platform Module System (JPMS), encapsulation is extended from the class and package scope to the module scope. The module descriptor specifies which packages are exported, which packages are for internal use only, and which packages are opened for deep reflection.

A small attack surface reduces the number of points that external code can call, configure, or directly affect. In a security context, this means reducing the number of APIs, states, and implementation details that an application must protect against untrusted input or misuse.

For example, a payment module might only expose its API:

    module com.example.payment {
        exports com.example.payment.api;
    }

Implementation packages such as:

    com.example.payment.internal
    com.example.payment.persistence
    com.example.payment.crypto

are kept hidden if not exported or opened. Consumers only see the types designed for use. The module can change how it authenticates, stores, or encrypts internally without turning those classes into a public contract.

Encapsulation is an attack surface reduction layer, not a complete sandbox. It helps control the accessibility of Java code within the module system; it does not by itself protect an application from all logic bugs, malicious input data, native code vulnerabilities, or code already granted execution privileges within the process.

## 2. From Access Modifiers to Module Boundaries

Java has multiple layers of access control. Each layer addresses a different scope:

| Mechanism | Scope | Meaning |
|---|---|---|
| private | Members of the class | Only code within the declaring class can access directly |
| package-private | Classes in the same package | Supports internal collaboration between classes in the same package |
| protected | Package and subclasses per Java rules | Supports controlled extension |
| public | Anywhere the type/package is accessible | Public at the language level, but still subject to module rules |
| exports | Package of a named module | Allows other modules to read and access public types in the package |
| opens | Package of a named module | Allows deep reflection into the package per JPMS rules |

The `public` modifier does not mean every module can use the class. A public class located in a non-exported package is still kept outside the module's normal access surface.

For example:

    module com.example.payment {
        exports com.example.payment.api;
    }

    package com.example.payment.internal;

    public final class PaymentTokenVerifier {
        public boolean verify(String token) {
            // Implementation details
            return true;
        }
    }

Even though `PaymentTokenVerifier` is `public`, other modules cannot use it via normal access because the `com.example.payment.internal` package is not exported.

This helps the module retain control over where the implementation is used. If the verifier class is later replaced by a service or a different implementation, consumers do not directly depend on that detail.

## 3. Designing a Small API to Reduce Access Points

A module should expose the operations that consumers need, not all the classes that make up the implementation.

Example of a payment API:

    package com.example.payment.api;

    public interface PaymentService {
        PaymentResult charge(PaymentRequest request);
    }

    public record PaymentRequest(
            String accountId,
            long amountInCents) {
    }

    public record PaymentResult(
            String transactionId,
            boolean accepted) {
    }

Consumers only need to call `PaymentService`:

    PaymentResult result = paymentService.charge(request);

Validation, limit checking, database access, key handling, and audit logging classes can reside in internal packages. There is no need to export those classes just for consumers to coordinate directly.

Designing a small API provides several security benefits:

- Reduces the number of methods that can be invoked from outside.
- Reduces the amount of internal state that consumers can observe or attempt to modify.
- Centralizes input validation at a few well-defined entry points.
- Reduces the likelihood of consumers calling internal steps in the wrong order.
- Limits the exposure of sensitive information through unnecessary data types or exceptions.
- Allows changing the implementation without expanding the compatibility contract.

A small API does not replace validation. A public method must still validate input data, authenticate identity, and authorize the operation. Encapsulation helps locate the points where checks are needed and prevents consumers from bypassing them by calling internal classes directly.

## 4. Do Not Export Internal Packages

A package should be exported only when it is part of the supported API. For example:

    module com.example.identity {
        exports com.example.identity.api;
    }

Whereas the following packages are kept internal:

    com.example.identity.internal
    com.example.identity.crypto
    com.example.identity.persistence
    com.example.identity.audit

If all packages are exported merely for the convenience of another application, the module may inadvertently turn implementation details into API. Consumers may then depend on internal classes, constructors, exceptions, or processing order that the module never committed to maintaining.

Some consequences:

- Refactoring or replacing the implementation becomes difficult.
- Consumers can bypass validation on the main API and call internal classes directly.
- Classes with access to sensitive data or resources are exposed more broadly.
- It becomes harder to restrict access by the role of each module.
- The surface area requiring compatibility and security review increases.

Not exporting internal packages does not mean internal code is automatically secure. Classes within the module must still adhere to access modifiers, input validation, resource management, and the principle of least privilege.

## 5. Qualified Exports and Intentional Access

JPMS supports **qualified exports**, which export a package only to a specified group of modules.

    module com.example.payment {
        exports com.example.payment.api;

        exports com.example.payment.spi
            to com.example.payment.adapter;
    }

In this example, the API package is broadly exposed to modules that read the payment module. The SPI package is only exported to the specifically named adapter module.

Qualified exports are useful when a module has an extension point intended for other known modules. It helps narrow the scope of consumers that can access the package.

However, qualified exports are still part of the module descriptor and architectural contract. If the target module could be replaced by untrusted or unmanaged code, granting package access needs careful consideration.

Do not use qualified exports as a way to grant access to every test module or every plugin without a clear design reason. If access is only needed in tests, test launcher or build tool configuration is usually more appropriate.

## 6. `opens` and Risks from Deep Reflection

The **opens** directive allows frameworks or libraries to use deep reflection into a package, including accessing non-public members under conditions permitted by JPMS.

For example:

    module com.example.payment {
        exports com.example.payment.api;
        opens com.example.payment.persistence
            to com.example.orm;
    }

The ORM module may need reflection to map entities or read metadata. Opening the package is restricted to the `com.example.orm` module instead of opening the entire module.

A broader declaration:

    open module com.example.payment {
        exports com.example.payment.api;
    }

opens all packages of the module for deep reflection. This approach can be convenient for legacy frameworks, but it weakens encapsulation because many internal components become accessible via reflection.

Prefer opening specific packages to the exact target modules. Only use `open module` when the framework genuinely requires broad access and that scope has been accepted in the design.

Reflection is not a way to bypass all access rules. Operations like `setAccessible(true)` can be restricted by JPMS; deep access into an unopened package can result in `InaccessibleObjectException`. Opening a package also does not turn private fields into a stable API; it only grants reflection access within the permitted scope.

## 7. Runtime Options Can Weaken Encapsulation

The Java launcher has options that allow adjusting module boundaries at runtime:

| Option | Effect | Impact on encapsulation |
|---|---|---|
| `--add-exports` | Exports an additional package to target modules | Opens normal access to public types in the package |
| `--add-opens` | Opens a package for deep reflection | Allows frameworks to access non-public members |
| `--add-reads` | Adds a readability relationship | Allows a module to read another module |
| `--patch-module` | Adds classes or resources to a target module | Modifies module contents in the runtime configuration |

For example:

    java --add-exports com.example.payment/com.example.payment.internal=ALL-UNNAMED \
         --module-path mods \
         --module com.example.application/com.example.application.Main

This command exports the `internal` package to unnamed modules. It can provide temporary compatibility with legacy libraries, but it also increases the amount of code that can access that package.

Example of opening a package for reflection:

    java --add-opens com.example.payment/com.example.payment.persistence=ALL-UNNAMED \
         --module-path mods \
         --module com.example.application/com.example.application.Main

Do not add these options to production by default. Identify which framework needs access, which package needs to be opened, and which module is the target. Then document the reason, limit the scope, and plan to remove them when dependencies are updated.

## 8. Encapsulation and the Principle of Least Privilege

The principle of **least privilege** requires each component to receive only the permissions necessary to perform its task.

In JPMS, this can be applied by:

- Only exporting API packages that consumers truly need.
- Using qualified exports when only a few modules need an SPI package.
- Only opening packages for reflection when a framework has a specific requirement.
- Avoiding `open module` if only a single package needs to be opened.
- Avoiding `ALL-UNNAMED` when a specific target module can be specified.
- Keeping `requires` dependencies to what is necessary.
- Not exposing internal classes or sensitive capabilities through public APIs.
- Separating modules by responsibility so access rights are easy to understand and manage.

For example:

    module com.example.secrets {
        exports com.example.secrets.api;
        opens com.example.secrets.persistence
            to com.example.orm;
    }

Consumer modules can use the public API. The ORM can reflect into the `persistence` package for its designated purpose. The `crypto` and `internal` packages remain hidden.

However, JPMS is not a user authorization system or a sandbox for malicious code. Another module can gain access via granted directives or runtime options; code in the same process can also use other APIs such as JNI or native code. Encapsulation must be combined with authentication, authorization, input validation, secret management, dependency updates, and secure deployment configuration.

## 9. Service Providers Do Not Necessarily Have to Export Implementations

`ServiceLoader` allows a module to provide an implementation without needing to export the package containing the provider class.

For example:

    module com.example.payment.api {
        exports com.example.payment.api;
        exports com.example.payment.spi;
    }

    module com.example.payment.provider {
        requires com.example.payment.api;

        provides com.example.payment.spi.PaymentProvider
            with com.example.payment.internal.DefaultPaymentProvider;
    }

The `com.example.payment.internal` package can remain hidden. Consumers discover the provider through the public service type without needing to import the implementation class.

This approach preserves the boundary between contract and implementation. Consumers only depend on the supported interface, while the provider module can change the implementation class without forcing consumers to know internal class names.

There is no need to export the implementation package just for `ServiceLoader` to discover a provider declared with `provides` in the module descriptor. If a provider is packaged using the legacy classpath mechanism, `META-INF/services` configuration has its own rules; even so, exposing the API should still be separated from implementation details.

## 10. Testing Without Expanding the Production API

Tests may need to inspect internals, but you should not export packages in the released module descriptor for that reason.

Prefer testing through the public API:

    PaymentResult result = paymentService.charge(request);
    assertTrue(result.accepted());

If tests need to access public classes in internal packages, `--add-exports` can be used in the test configuration. If a framework needs deep reflection, `--add-opens` can be used in the test runtime. If tests need package-private access, the build tool can configure `--patch-module` to place test classes into the module under test.

Test runtime example:

    java --add-opens com.example.payment/com.example.payment.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar

The exact configuration depends on how the test framework and build tool organize the module path, classpath, and test classes. Test-only options should stay in test tasks and should not be placed into production startup scripts.

If tests run in a separate named module, specify that module name instead of `ALL-UNNAMED` when possible. Granting narrower access helps tests accurately reflect the intended boundaries.

## 11. How to Evaluate a Module's Access Surface

You can start by reading the module descriptor:

    jar --describe-module --file payment.jar

Check:

1. Which packages does the module export?
2. Are there qualified exports, and do the target modules really need them?
3. Does the module have `opens` directives or is it declared as an `open module`?
4. Do the `requires` directives reflect actual dependencies?
5. Are any internal packages being exported just for a framework or tests?
6. Are any `--add-exports` or `--add-opens` runtime options added in deployment scripts?
7. Can service providers be declared with `provides` to keep implementation packages hidden?

You can use:

    java --show-module-resolution \
         --module-path mods \
         --module com.example.application/com.example.application.Main

to view the module graph resolved at runtime. Also inspect the actual launcher command because command-line options can alter access boundaries compared to the module descriptor.

Reading the descriptor does not prove a module is secure. It only helps understand part of the access surface exposed by JPMS and the runtime exceptions being applied.

## 12. Takeaways

- Encapsulation narrows the types, states, and operations that external code can access.
- A module should export its supported API and keep implementation packages internal.
- The `public` modifier does not bypass JPMS package export boundaries on its own.
- Qualified exports restrict a package to specific target modules, but remain part of the module contract.
- `opens` serves deep reflection; `open module` expands reflection scope to all packages.
- `--add-exports` and `--add-opens` can weaken encapsulation at runtime; grant them only for the exact packages and modules needed.
- `ServiceLoader` allows registering providers without exporting implementation packages.
- Test-only access should be configured in the build/test runtime, not added to the production API for convenience.
- Encapsulation is not a complete sandbox; it must be combined with authentication, authorization, validation, secret management, and dependency updates.
- Inspect the module descriptor and launcher options to understand the actual access surface.

**Encapsulation is a layer of defense by limiting the points external code can reach.** Keeping APIs small, internal packages hidden, and reflection rights scoped helps reduce the surface that needs protection, while keeping the module easier to change and govern.

## References

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html