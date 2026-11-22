# How Export Changes Affect Binary Compatibility

## 1. exports Is Part of the Module Contract

In JPMS, declaring `requires` alone is not enough for another module to use types belonging to a named module. The providing module must also export the package containing those types.

Example of a library module exposing an API:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

A consuming module can read and use public types in the exported package:

~~~java
module com.acme.application {
    requires com.acme.customer;
}
~~~

`exports` is a package-level access boundary. When a package is exported, types and members must still obey normal Java access rules: a top-level class usually must be `public`, and the member being used must have an appropriate access level. Exporting a package does not make package-private classes or private members public.

Because consuming modules rely on the export directive to compile and run, changing `exports` can directly affect previously compiled programs. Therefore, exposed packages should be treated as part of the compatibility contract that the library commits to maintaining.

## 2. Three Export Changes to Distinguish

Suppose the first version of the library has the descriptor:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Every named module reading `com.acme.customer` can access public types in package `com.acme.customer.api`.

### Removing exports

The new version drops the directive:

~~~java
module com.acme.customer {
    // No longer exports com.acme.customer.api
}
~~~

The package becomes internal to other modules. A previously compiled consumer may still contain bytecode referencing classes in this package, but when the JVM needs to access a type or member hidden from that module, the access check can fail with `IllegalAccessError`.

A consumer recompiled against the new descriptor will also be rejected when importing or accessing the unexported package.

### Narrowing from a Public Export to a Qualified Export

Initial version:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Later version:

~~~java
module com.acme.customer {
    exports com.acme.customer.api to com.acme.application;
}
~~~

The package is now exported only to module `com.acme.application`. Other consumers that previously read the customer module and used the API package lose access.

This is a change that can break compatibility even though the module name, package name, public classes, and method signatures have not changed. Access permissions changed at the module descriptor level.

### Removing a Module from a Qualified Export List

Suppose the descriptor is:

~~~java
module com.acme.customer {
    exports com.acme.customer.spi
        to com.acme.application, com.acme.integration;
}
~~~

If a subsequent release removes `com.acme.integration`:

~~~java
module com.acme.customer {
    exports com.acme.customer.spi
        to com.acme.application;
}
~~~

Consumer `com.acme.integration` is no longer allowed to access that package. Remaining consumers on the list retain access if other conditions remain unchanged.

## 3. Why Can Old Bytecode Encounter IllegalAccessError?

Java compilation and bytecode linking/execution occur at two different times:

1. When compiling the consumer, the compiler reads the library's module descriptor and confirms that the needed package is exported to the consumer.
2. The compiler generates bytecode containing references to types, methods, or fields of the library.
3. At runtime, the JVM resolves references and performs access checks according to the module descriptors currently loaded.
4. If the new library version no longer exports the package to the consuming module, the JVM can throw `IllegalAccessError` when the execution path reaches the forbidden reference.

Example of a consumer already compiled against the API:

~~~java
package com.acme.application;

import com.acme.customer.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = null;
        System.out.println(service);
    }
}
~~~

The consumer was compiled while the customer module still exported `com.acme.customer.api`. Later, the application swaps in a version of the library JAR with the export removed. The consumer bytecode is not automatically recompiled and still contains the reference to `CustomerService`. When the JVM needs to access this type, the module access check can fail with `IllegalAccessError`.

The error may appear when the class or member is linked or used, not necessarily immediately at JVM startup. Therefore, merely running the application through a code path that does not touch the narrowed API is not sufficient to prove compatibility.

## 4. Distinguishing Compile-Time Errors from Runtime Errors

| Scenario | Recompiled Consumer | Old Consumer Bytecode |
|---|---|---|
| Package remains exported to consumer | Can continue compiling if API remains compatible | Can continue running if other linking conditions remain unchanged |
| Unqualified export removed | Compiler reports package is not exported/visible | May encounter `IllegalAccessError` when accessing a type or member |
| Changed to qualified export and consumer is not on the list | Compiler denies package access | May encounter `IllegalAccessError` |
| Consumer removed from qualified export | Compiler denies package access | May encounter `IllegalAccessError` |
| Qualified export added for a new consumer | New consumer can compile | Other existing consumers do not lose access just because a new export is added |

Compiler messages usually state that the package is not visible or that the module does not export the package to the consuming module. Runtime messages usually specify the source module, package, and target module that is not permitted access.

You should not lump every error after changing a descriptor into a binary compatibility error of exports. If a public method is removed, a type is renamed, or a signature changes, consumers may encounter other linking errors such as `NoSuchMethodError` or `NoClassDefFoundError`. If a package is no longer exported, the issue lies in module access permission and can lead to `IllegalAccessError`.

## 5. Adding an Export Is Usually Additive, but Widens the API

Adding an export:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.events;
}
~~~

usually does not revoke permissions from currently working consumers. Other modules can begin using the new package if they read the customer module and the required types/members are accessible.

However, a new export increases the public API surface. Once consumers begin depending on that package, narrowing or removing the export in a later version can become a compatibility-breaking change.

Before exporting a new package, confirm:

- Will the package be supported long term?
- Are the public types in the package stable yet?
- Does the package contain implementation details or internal-only classes?
- Can a qualified export be used to expose it only to a specific integration module?
- Does exposing the package expose additional dependencies in the API?

Do not export a package just to make an access error disappear if that package is not part of the contract the library wants to provide.

## 6. Qualified Exports and Classpath Consumers

A qualified export grants permission only to named modules:

~~~java
module com.acme.customer {
    exports com.acme.customer.spi to com.acme.integration;
}
~~~

This suits an internal SPI meant for a known integration module. Keep in mind, however:

- The consuming module must have a name matching the list.
- Another consumer is not granted permission just because it also declares `requires com.acme.customer`.
- Code on the classpath belongs to the unnamed module, which has no name to list as a named consumer in a qualified export.
- Moving a consumer from the module path to the classpath can change accessibility if the package is only conditionally exported.

If a library needs to support both classpath consumers and multiple named modules, consider whether the package should be an unqualified export or have a different public API. Do not assume a qualified export will automatically apply to every consumer.

## 7. exports and opens Are Two Different Contracts

`exports` controls normal access to public types of a package. `opens` permits deep reflection on a package at runtime.

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.persistence;
}
~~~

If you remove:

~~~java
exports com.acme.customer.api;
~~~

normal Java consumers can lose API access. If you remove:

~~~java
opens com.acme.customer.model to com.acme.persistence;
~~~

the persistence framework can encounter reflection errors such as `InaccessibleObjectException`, even though consumer code still compiles and the model package is not used directly in source code.

Conversely, keeping `opens` does not replace `exports`. A package opened only for reflection does not thereby become an API that can be imported and called directly from another module.

When changing descriptors, check both kinds of permission separately: consumer source/binary compatibility for exports, and framework runtime behavior for opens.

## 8. How to Test the Impact of Export Changes

A successful build of the library itself only proves that the library's own source compiles. To assess the impact on consumers, test against both new consumers and old bytecode.

### Step 1: Retain a consumer compiled against the old descriptor

Compile a consuming module while the package is still exported:

~~~java
module com.acme.application {
    requires com.acme.customer;
}
~~~

The consumer calls an API belonging to the exported package. Save the compiled consumer artifact to test against the new library version.

### Step 2: Build the library with the new descriptor

Produce the release candidate JAR in which the export has been removed or narrowed according to the change being evaluated.

### Step 3: Run old bytecode with the new JAR

Place the new library JAR and the old consumer bytecode on the module path. Execute the exact code path that accesses the changed package. Record any linking or access permission errors, if any.

### Step 4: Recompile the consumer

Use the new module path to recompile the consumer. If the package is no longer exported to that module, the compiler will catch the issue before runtime.

### Step 5: Test all supported qualified consumers and classpath consumers

If the descriptor has `exports ... to A, B`, test A and B individually. If the library commits to supporting classpath code, also test the unnamed module because it cannot be named in a qualified export list.

### Step 6: Test reflection and services independently

Run actual frameworks to test `opens`; test `ServiceLoader` if the module has `uses` or `provides`. A normal API access test does not substitute for these tests.

## 9. Tools to Inspect Artifacts

After building the new JAR:

~~~bash
jar --describe-module --file build/libs/customer-module.jar
jar --list --file build/libs/customer-module.jar
~~~

These two commands confirm the descriptor and packages packaged inside the actual artifact.

You can check the module descriptor against detected dependencies:

~~~bash
jdeps --check com.acme.customer --module-path mods
~~~

And inspect the module configuration at runtime:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.application/com.acme.application.Main
~~~

These tools help confirm module names, descriptors, and dependency relationships. They do not replace running previously compiled consumers against the new JAR; testing both new and old consumers directly uncovers the compatibility impact of exports.

During diagnosis, `--add-exports` can be used to verify hypotheses about access permissions:

~~~bash
java --add-exports com.acme.customer/com.acme.customer.api=com.acme.application \
  --module-path mods \
  -m com.acme.application/com.acme.application.Main
~~~

This option adds runtime export permission for that run. It is useful for identifying root causes or supporting controlled migration, but it does not fix the descriptor in the JAR and should not be treated as a long-term release solution in place of a proper module contract.

## 10. Compatibility Policy at Release Time

If a package is publicly exported and documented as a supported API, treat removing the export or narrowing the consumer list as a compatibility-breaking change.

A release process can apply:

- **Patch release**: preserve public exports and supported consumers; only fix internal bugs or add controlled compatibility permissions.
- **Minor release**: may add new exported packages or qualified exports when the new API is stable and expansion aligns with the compatibility policy.
- **Major release**: perform intentional changes such as removing exports, renaming packages/modules, or narrowing published qualified exports; accompanied by migration notes and replacement guidance.

This is a library-level versioning policy, not a mandatory JPMS rule. The development team must clearly identify which packages are supported APIs, which packages are internal details, and which consumer modules are guaranteed support.

If an API package needs to be retired, a transition period can be released: publish the replacement API, mark the old API deprecated, guide consumers to migrate, measure or check known consumers, and only then narrow the export in a major release.

## 11. Checklist Before Changing exports

- [ ] List all packages currently exported in the existing descriptor.
- [ ] Identify known consuming modules currently using each package.
- [ ] Verify whether each package is a public API, a restricted SPI, or an implementation detail.
- [ ] Evaluate changes to unqualified exports and qualified exports separately.
- [ ] Identify which consumers will lose access if the export is removed or narrowed.
- [ ] Recompile consumers against the new descriptor to detect source errors.
- [ ] Run old consumer bytecode against the new JAR to detect runtime errors such as `IllegalAccessError`.
- [ ] Check `opens` separately for framework reflection.
- [ ] Confirm the final JAR contains the exact `module-info.class` and expected descriptor.
- [ ] Update the version, migration notes, and API documentation according to the impact level.

## Conclusion

Changing `exports` is a module-level access permission change. Removing an export, converting a public export into a qualified export, or removing a consumer from the allowlist can prevent source from recompiling and cause old bytecode to encounter `IllegalAccessError` when the JVM checks access permissions.

Before releasing, treat exported packages as part of the compatibility contract, test both new consumers and old bytecode, and verify the descriptor on the actual final JAR. This testing approach ensures module API changes are intentional, properly versioned, and accompanied by clear migration guidance.