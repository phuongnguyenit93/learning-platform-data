# Verifying a Descriptor Before Releasing a Module

## 1. Why Verify the Module Descriptor?

In JPMS (Java Platform Module System), `module-info.java` is the contract describing a module: the module name, dependencies the module reads, published packages, packages opened for reflection, and services that the module uses or provides.

A descriptor can compile successfully yet still be unsuitable for release. For example:

- `requires` declarations are missing needed dependencies or retain unused dependencies.
- A public API returns types from another module, yet that dependency has not been declared `requires transitive`.
- An internal package is accidentally exported broadly.
- A framework needs deep reflection, yet the corresponding package has not been opened with `opens`.
- The module name in the descriptor does not match the name expected by consuming applications.
- The released JAR does not contain the right `module-info.class`, or the built content does not match the tested configuration.

Verifying before release helps catch these issues at build and test time, rather than letting users encounter errors when integrating the library.

## 2. Checking Module Structure and Naming

An explicit named module has a `module-info.java` file at the root of the module source. After compilation, the corresponding `module-info.class` file sits at the root of the module output or the root of the modular JAR.

Example structure:

~~~text
customer-module/
  src/
    module-info.java
    com/
      acme/
        customer/
          api/
            Customer.java
          internal/
            CustomerRepositoryImpl.java
  build/
    classes/
      module-info.class
      com/
        acme/
          customer/
            api/
            internal/
~~~

Minimal descriptor:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

When verifying the module name:

- Use a stable, recognizable name following reverse-domain convention, such as `com.acme.customer`.
- Do not use namespaces reserved for the Java platform such as `java.*` for application modules.
- Verify that every `requires`, `exports ... to`, `opens ... to`, `uses`, and `provides` directive references the right module or service name.
- If the library must support both classpath and module path, consider keeping the module name stable across releases; renaming a module directly breaks consumers declaring `requires`.

The module name is part of the integration contract. Do not let the module name inadvertently change with the JAR filename if users need to depend on that name long-term.

## 3. Checking Dependencies and Readability

Each `requires` should correspond to an actual dependency of the module. Review source code and public APIs to determine which modules need to be read:

~~~java
module com.acme.customer {
    requires java.sql;
    requires com.acme.logging;

    exports com.acme.customer.api;
}
~~~

Points to review:

- Dependencies used directly in source code must be present in the compile configuration.
- Dependencies needed at runtime must be present in the runtime image or runtime module path.
- Do not keep unnecessary `requires` if they increase release constraints.
- `java.base` is implicitly read by every named module; there is no need to declare `requires java.base`.
- A module can read a dependency indirectly via `requires transitive`, yet you should directly declare dependencies that the module's source code actually uses so the contract stays easy to understand and durable.

### When to Use requires transitive?

If the module's public API exposes types from another dependency, API consumers may need to read that dependency in order to compile. In that case, consider:

~~~java
module com.acme.customer {
    requires transitive com.acme.domain;
    exports com.acme.customer.api;
}
~~~

Example API:

~~~java
package com.acme.customer.api;

import com.acme.domain.CustomerId;

public interface CustomerService {
    CustomerId findCustomer(String value);
}
~~~

A consuming module declaring only `requires com.acme.customer` still gains readability to `com.acme.domain` thanks to `requires transitive`. Use this modifier only when the dependency genuinely appears in the public API contract; internal-only dependencies should normally use regular `requires`.

### When to Use requires static?

~~~java
module com.acme.customer {
    requires static com.acme.annotations;
}
~~~

`requires static` requires the dependency at compile time while allowing it to be absent at runtime. Confirm that runtime code does not genuinely need classes from that dependency when the module is absent. If a runtime code path uses that class, the dependency must be supplied at runtime; declaring `requires static` alone does not generate a substitute implementation.

## 4. Checking exports and API Boundaries

In an explicit named module, packages are not exposed by default. Export only packages belonging to the API that module users need to access.

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Before releasing, check:

- Do exported packages genuinely contain supported APIs?
- Are `internal`, `impl`, `spi`, or implementation-only packages being exported unintentionally?
- Does the public API use types belonging to other packages or modules that consumers cannot access?
- Can qualified exports be used to restrict permissions to specific consuming modules?

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.spi to com.acme.integration;
}
~~~

`exports com.acme.customer.api` allows any module reading the customer module to access public types in the API package. A qualified export exposes the package only to the listed modules.

Exporting a package does not make every member public. Standard Java access rules remain in effect. Conversely, unexported packages can still contain classes used internally within the module.

## 5. Checking opens and Reflection Requirements

Persistence, dependency injection, serialization, or binding frameworks may need deep reflection to access non-public constructors or fields. In that case, open the right packages to the right modules.

~~~java
module com.acme.customer {
    requires com.acme.persistence;

    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.persistence;
}
~~~

Distinguish:

- `exports` allows Java code in other modules to access public types in the package.
- `opens` allows deep reflection on the package at runtime.
- `opens package to module` restricts reflection permissions to the specified module.
- `open module` opens all packages of the module for deep reflection.

There is no need to open the entire module if the framework accesses only one package. In addition, a module declared with `open module` must not simultaneously contain individual `opens` directives in the descriptor. If package-level control is needed, use a regular `module` declaration with selective `opens` directives.

Test with the exact framework and runtime configuration intended for release. A successful compilation does not prove that reflection will work at runtime.

## 6. Checking uses and provides When the Module Uses ServiceLoader

JPMS supports declaring service relationships in the module descriptor.

A service-consuming module declares `uses`:

~~~java
module com.acme.application {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

A module supplying an implementation declares `provides ... with ...`:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

Before releasing, check:

- Is the service type the exact type used by the consuming module?
- Does the provider implementation exist in the supplying module?
- Does the provider satisfy `ServiceLoader` instantiation rules (a public no-argument constructor or a public static method named `provider` with a matching signature)?
- Are both the provider module and consumer module present in the runtime configuration/layer used by the application?
- Has calling `ServiceLoader.load(...)` been tested in an actual integration run?

The package containing the provider implementation does not necessarily need to be exported solely for `ServiceLoader` to locate the provider. Export the service API in the module owning the API, and export the implementation package only if there is another need for direct access.

## 7. Compiling and Inspecting the Descriptor

You can compile a module using `javac` with the module source path:

~~~bash
javac -d mods --module-source-path src -m com.acme.customer
~~~

If the module is compiled separately from an identified source directory:

~~~bash
javac -d out/customer-module \
  src/customer-module/module-info.java \
  src/customer-module/com/acme/customer/api/Customer.java
~~~

In Gradle or Maven projects, prefer the project's official build task because that task also applies the proper dependencies, compiler options, toolchain, and packaging workflow. Verify that the build uses the JDK and target release the project claims to support.

After compiling, inspect the descriptor of the output module:

~~~bash
jar --describe-module --file build/libs/customer-module.jar
~~~

This command shows the module name, packages, dependencies, and module directives provided by the JAR. Cross-check the output against `module-info.java` and the intended contract.

You can list JAR contents to confirm the descriptor is in the right place:

~~~bash
jar --list --file build/libs/customer-module.jar
~~~

For a modular JAR, `module-info.class` should appear at the root of the archive. If the JAR does not contain a descriptor, Java may recognize it differently when placed on the module path.

## 8. Using jdeps and Module Resolution to Detect Issues

`jdeps` helps analyze dependencies actually used by bytecode. For a compiled module, you can inspect the descriptor and dependencies as follows:

~~~bash
jdeps --check com.acme.customer --module-path mods
~~~

This command helps verify the module descriptor against detected dependencies, while offering suggestions when module relationships are not declared appropriately. Read the warnings and evaluate them against the API the module intends to expose; do not automatically turn every detected dependency into `requires transitive`.

To see modules resolved at runtime:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.application/com.acme.application.Main
~~~

To ask the runtime to validate modules on the module path:

~~~bash
java --module-path mods --validate-modules
~~~

When running these commands, use the same module path and module artifacts as the release configuration. Testing only against a temporary build directory may yield different results from the uploaded JAR or deployed image.

## 9. Verifying the Exact Artifact to Be Released

A valid descriptor in source does not guarantee the final JAR contains the right descriptor. Verify the artifact after packaging:

1. Confirm the build completed and the JAR was generated at the expected path.
2. Use `jar --describe-module` to read the name and descriptor from that exact JAR.
3. Use `jar --list` to check `module-info.class` and the packaged packages/classes.
4. Verify no internal packages are exported unintentionally.
5. Run a consuming application or a small test module on the module path using only the release dependencies.
6. If the module uses reflection, run the actual framework to confirm `opens` is right.
7. If the module uses `ServiceLoader`, verify both discovery and provider instantiation.
8. Repeat verification after changing build scripts, compiler version, or JAR shading/relocation workflows.

Pay particular attention to workflows that create fat JARs or use shading. If a packaging tool merges multiple modules into one classpath JAR, the result may no longer preserve JPMS boundaries. Release a modular JAR only when the final artifact genuinely preserves the designed module structure.

## 10. Checking Compatibility Before Changing a Descriptor

The descriptor is part of the module API. A seemingly small change can affect consumers:

- Renaming a module breaks `requires` declarations using the old name.
- Removing a package from `exports` can prevent consumer code from compiling or accessing the API.
- Removing a dependency from `requires transitive` can cause consumers to lose readability to types appearing in the API.
- Narrowing qualified exports can block a supported integration module.
- Removing `opens` can cause frameworks to fail at runtime even though application code still compiles.
- Removing `uses` or `provides` can prevent service discovery from locating implementations.

Therefore, verify the descriptor alongside consumer tests: compile another module that depends only on the published API, run the application on the module path, and test the reflection/service paths the library commits to supporting.

## 11. Release Checklist

Before tagging or uploading an artifact, you can use the following short checklist:

- [ ] The module name is stable and matches the name in integration documentation.
- [ ] `module-info.class` is present in the final JAR in the right location.
- [ ] All needed `requires` are present; unused dependencies have been reviewed for removal.
- [ ] `requires transitive` is applied only to dependencies genuinely appearing in the public API.
- [ ] `requires static` does not mask a mandatory runtime dependency.
- [ ] `exports` exposes only packages belonging to the supported API.
- [ ] `opens` opens only packages needing reflection and to the right consuming modules.
- [ ] `uses` and `provides` match actual services/providers if ServiceLoader is used.
- [ ] `jar --describe-module`, `jdeps --check`, and module resolution checks have been run on the release artifact.
- [ ] An independent consumer compiles and runs on the actual module path.

## Conclusion

Verifying a descriptor before release requires looking at three layers: module structure, access contract, and packaged artifact. `module-info.java` must accurately describe dependencies, API packages, reflection needs, and services; the final JAR must preserve that descriptor; and a consuming application must compile and run in an actual module configuration.

When verified with `jar --describe-module`, `jdeps --check`, `java --validate-modules`, and an independent consumer, the development team has concrete evidence that the module is ready for integration.