# Risks of Module Names Depending on File Names

## 1. Where Does an Automatic Module Get Its Name?

A JAR without `module-info.class` when placed on the **module path** can be treated as an automatic module. The JVM needs a module name to place that JAR into the module graph.

The automatic module name is determined in order:

1. If the JAR's manifest has the `Automatic-Module-Name` attribute, that value is used as the module name.
2. If that attribute is absent, the module name is derived from the JAR file name.

For example, a library with the file:

~~~text
payment-client-2.4.1.jar
~~~

may have its module name derived as:

~~~text
payment.client
~~~

The name is derived using filename normalization rules: stripping the `.jar` extension, detecting and stripping the version suffix according to naming rules, replacing invalid separator characters with dots, collapsing consecutive dots, and stripping leading/trailing dots. This is an inference from the file name, not a name committed by the library author as a stable API.

When a JAR already has an explicit module descriptor, the name in the descriptor is the module name used. `Automatic-Module-Name` and filename-derived names only apply to JARs without an explicit descriptor.

## 2. Why Does Depending on File Names Create Risk?

Suppose the application declares:

~~~java
module com.acme.checkout {
    requires payment.client;
}
~~~

The `requires` declaration refers to the **module name**, not directly to the JAR file name, Maven artifact, or path on disk.

If the module name is derived from the file, renaming the artifact or changing how it is packaged can alter the name seen by the compiler and the JVM. Then `requires payment.client;` may no longer match the actual module.

Several changes can have an impact:

- The vendor renames the artifact or the JAR file name.
- The build pipeline adds or removes a classifier in the file name.
- A distribution changes its file naming convention.
- The library is split from one combined JAR into multiple differently named JARs.
- A packaging tool renames the JAR when copying it into the deployment directory.

Not every version change alters the module name. Typical version suffixes are normally stripped when deriving the name. However, the application is still relying on a file naming convention and its derived outcome, so the derived name should not be treated as a vendor-guaranteed stable contract.

## 3. Examples of File Names and Derived Module Names

Some illustrative examples:

| JAR File Name | Possible Derived Automatic Module Name |
|---|---|
| `payment-client-2.4.1.jar` | `payment.client` |
| `json-core-1.8.jar` | `json.core` |
| `acme-logging.jar` | `acme.logging` |
| `legacy_http-3.0.jar` | `legacy.http` |

Note that a module name derived from the file does not necessarily match Maven coordinates:

~~~text
groupId    = com.vendor
artifactId = payment-client
version    = 2.4.1
file       = payment-client-2.4.1.jar
module     = payment.client
~~~

JPMS does not automatically take `groupId` to form a `com.vendor` prefix. If the application writes `requires com.vendor.payment.client;` while the actual JAR has the automatic module name `payment.client`, the compiler will not find the requested module.

The names in the examples illustrate results under the derivation rules; for actual dependencies, always verify the exact artifact resolved in your build.

## 4. Risk When the File Name Changes

Suppose the library is initially distributed as:

~~~text
libs/
└── payment-client-2.4.1.jar
~~~

The derived automatic module name is `payment.client`. The application declares:

~~~java
module com.acme.checkout {
    requires payment.client;
}
~~~

Later, a packaging step renames the file to:

~~~text
libs/
└── acme-payment.jar
~~~

If the JAR lacks `Automatic-Module-Name` and lacks `module-info.class`, the derived name may become `acme.payment`. At this point, the consuming module still requests `payment.client`, while the module path only has `acme.payment`.

The typical result is a module resolution error such as:

~~~text
module not found: payment.client
~~~

The error occurs even though the bytecode inside the JAR may be identical to before the rename. The cause lies in the module name metadata seen by the module system.

Renaming a file can also cause errors in the reverse direction: a new JAR may accidentally derive a module name that existing code never requested. Therefore, when upgrading or changing how dependencies are packaged, check the actual module name.

## 5. Risk of Duplicate Module Names

Two different JARs can derive the same module name if their normalized file names match.

Example:

~~~text
libs/
├── payment-client-2.4.1.jar
└── payment-client-3.0.0.jar
~~~

Both can be derived as `payment.client`. If both are placed into the same module configuration, the module resolver cannot treat them as two independent modules with the same name so the application can pick versions arbitrarily.

JPMS does not provide a mechanism to load two versions of the same module name in a single module configuration like a dependency version resolver. Version selection must be handled by the build tool or packaging process before constructing the module path.

This also shows you cannot use automatic module names to isolate library versions. If two versions must coexist, you must design appropriate deployment boundaries or class loaders/layers; merely renaming JAR files does not create a safe version isolation mechanism.

## 6. How to Stabilize Names with Automatic-Module-Name

To avoid relying on file names, library vendors can set the `Automatic-Module-Name` attribute in the manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.payment.client
~~~

When the JAR lacks `module-info.class`, JPMS uses the name in the manifest instead of deriving one from the file name. Thus, the file can be renamed or given new versions while the module name stays stable, provided the vendor preserves that attribute.

Consumers then declare:

~~~java
module com.acme.checkout {
    requires com.acme.payment.client;
}
~~~

Example Gradle Groovy configuration for a library owned by your team:

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.acme.payment.client'
        )
    }
}
~~~

When the library moves to an explicit named module, keep the same name in `module-info.java`:

~~~java
module com.acme.payment.client {
    exports com.acme.payment.api;
}
~~~

Keeping the name consistent ensures consumers do not have to change `requires` merely because the library moved from an automatic module to an explicit named module.

For third-party libraries, prefer releases that already publish `Automatic-Module-Name` or have a module descriptor. Manually renaming files just to make `requires` match can cause errors on the next upgrade and make the build process unpredictable.

## 7. Inspecting the Actual Module Name with JDK Tools

Do not guess the module name solely from Maven coordinates. Use the exact JAR file used by the build:

~~~bash
jar --describe-module --file libs/payment-client-2.4.1.jar
~~~

For a JAR without an explicit descriptor, the output indicates that it is an automatic module and shows the name used. If the manifest has `Automatic-Module-Name`, check that name in the output.

You can also inspect the manifest:

~~~bash
unzip -p libs/payment-client-2.4.1.jar META-INF/MANIFEST.MF
~~~

Look for the line:

~~~text
Automatic-Module-Name: com.acme.payment.client
~~~

If the environment lacks `unzip`, you can extract the manifest with an available ZIP tool or view the manifest content in your artifact repository. The key point is to inspect the exact JAR resolved by the build, not only look at the dependency name in configuration files.

After confirming the name, verify three places:

1. The module name in the consumer's `requires`.
2. The module name displayed by `jar --describe-module`.
3. The JAR file actually present on the module path at compile time and runtime.

## 8. Automatic Modules Also Have Broad Access Characteristics

File naming is not the only risk when using automatic modules. Automatic modules were designed as a transitional mechanism so legacy libraries can join the module path:

- An automatic module exports all of its packages.
- An automatic module reads other modules in the module configuration.
- It does not express strict API boundaries like a named module with a well-designed descriptor.

Therefore, having a module name and being usable in `requires` does not mean the library has been completely modularized. Consumers can still see more internal packages than the library wants to support long-term.

When clear encapsulation is needed, prefer libraries with `module-info.class` that export only the necessary API packages. Automatic modules are suited to step-by-step migration, but should not be assumed as the final design state.

## 9. Workflow When Upgrading Dependencies

When upgrading a JAR currently used as an automatic module, follow these steps:

1. Resolve dependencies with Maven/Gradle and locate the actual JAR file path.
2. Run `jar --describe-module --file <jar>` to obtain the module name.
3. Inspect the manifest to see whether `Automatic-Module-Name` is present.
4. Compare the module name with the consumer's `requires` directives.
5. Verify that the module path does not contain two JARs with the same module name.
6. Rebuild the consumer to catch module resolution and readability errors.
7. Run the application on the module path to confirm runtime uses the right artifact.

If the module name changed, first determine whether the change came from the manifest, the file name, or the library switching to an explicit module descriptor. Only then decide whether to update `requires` or pick a different artifact version.

Do not adjust module names based on guesswork or manually rename files without recording the convention in the build. The module name is part of the contract that consumers depend on.

## 10. Key Takeaways

An automatic module needs a name to join the module graph. If the JAR has `Automatic-Module-Name`, JPMS uses the stable name declared by the vendor. Otherwise, the name is derived from the JAR file name and can be affected by artifact naming or packaging.

- `requires` references the module name, not Maven coordinates or the file name.
- Typical version suffixes are normally stripped during name derivation; do not assume every file naming convention yields stable results.
- Two JARs can derive the same module name and conflict in the same module configuration.
- `Automatic-Module-Name` helps keep the name stable across file name changes.
- An explicit module descriptor is the way to express clearer API boundaries than an automatic module.
- Always inspect the actual artifact with `jar --describe-module` before concluding the module name.

When an automatic module dependency causes a `module not found` error, first check the module name the JAR actually publishes. That is the direct evidence for determining whether `requires` references the wrong name or the build puts the wrong artifact on the module path.