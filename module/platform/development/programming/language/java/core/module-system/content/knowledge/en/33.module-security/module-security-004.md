# Controlling Untrusted Module Paths and Module Sources

## Objectives

After this lesson, you can:

- Distinguish between the risks of the module path at runtime and the module source path at compile time.
- Explain why JPMS encapsulation and module descriptors are not a sandbox mechanism.
- Control the provenance, identity, and integrity of modular JARs, exploded modules, and source trees.
- Identify automatic modules, duplicate module names, module overrides, and service providers as control points.
- Reduce risks when compiling untrusted sources, especially annotation processors and build plugins.
- Design verification, staging, and isolation workflows before placing modules into a JVM with access to real data.

## 1. Trust Boundaries of the Java Module System

The Java Platform Module System (JPMS) organizes an application into modules with names, dependencies, and package boundaries. A module descriptor states which modules a module requires, which packages it exports, which packages it opens, and which services it provides or uses.

Those rules help control visibility and access between modules. However, **JPMS is not a sandbox for running untrusted code**.

When a class is loaded and executed in the application's JVM, that code generally runs with the privileges of the current process: reading files the process is allowed to read, opening network connections, using environment credentials, spawning threads, or calling native code through permitted mechanisms. Being inside a named module does not automatically restrict those operating system privileges.

Therefore, three layers must be distinguished:

1. **Module boundary**: controls readability, `exports`, `opens`, packages, and dependencies within Java.
2. **Supply-chain trust**: determines where an artifact/source came from, whether it is the right version, and whether it has been tampered with.
3. **Execution isolation**: restricts process resources and privileges via OS accounts, containers, VMs, filesystem/network policies, and operational mechanisms.

A module with a valid descriptor can still contain malicious code. A signed JAR can still contain dangerous code if the signer is untrusted. A module that exports no packages can still perform I/O or send data over the network from the public code it provides.

## 2. The Runtime Module Path Is an Execution Input

### 2.1. Where Does the JVM Look for Modules?

When running a modular application, the launcher receives the module path via:

~~~bash
java --module-path mods -m com.acme.app/com.acme.Main
~~~

The module path can contain:

- Modular JARs with a module descriptor.
- Exploded modules, i.e., directories containing `module-info.class` and a package tree.
- JARs that become automatic modules when placed on the module path.
- Multiple directories or archives separated according to the OS path rules.

Discovered modules participate in configuration resolution. Once a module is defined in a layer and its classes are loaded, code in the module can be executed.

Consequently, every directory and archive on the module path is part of the code supply chain. Never add directories writable by untrusted users to the module path of a production process.

### 2.2. The Module Path Is Not a Harmless List of Libraries

A modular JAR is not merely metadata. It can contain classes with static initializers, constructors, service providers, or methods invoked by the application. These pieces of code can execute side effects when initialized or executed.

For example, a class with a static initializer:

~~~java
package com.acme.plugin;

public final class PluginEntry {
    static {
        // Side effects can occur when the class is initialized.
        System.out.println("Plugin initialized");
    }

    public static void start() {
        System.out.println("Plugin started");
    }
}
~~~

Merely resolving a module does not mean every class in the module is initialized immediately. However, when the application loads and initializes a class, invokes a service provider, or calls a plugin API, code can run.

Do not rely on "not having called the main class yet" to conclude that a module has no side effects. Class loaders, frameworks, and service discovery can trigger loading or initialization of code at different stages.

## 3. Controlling Module Identity and Artifact Provenance

### 3.1. A Module Name Does Not Prove Provenance

A module named `com.acme.payment` does not prove by itself that it was published by the organization owning that namespace. A module name is an identifier for the resolver and code references; it is not a digital signature or proof of origin.

Before placing an artifact on the module path, determine:

- Which repository or build pipeline did the artifact come from?
- Do the group, artifact, version, and module name match the approved release manifest?
- Does the file have the recorded hash?
- Who has permission to publish or replace the artifact?
- Are any unexpected transitive dependencies or new modules introduced?

Do not use file names, directory names, or module names as sole evidence of trustworthiness.

### 3.2. Verifying Descriptors and Module Names

You can inspect a modular JAR's descriptor using:

~~~bash
jar --describe-module --file libs/acme-plugin.jar
~~~

For JARs without an explicit module descriptor, the tool can display the automatic module name and derived packages.

This check helps identify the declared module name, `requires`, `exports`, `opens`, `uses`, and `provides`. It does not prove the bytecode is safe or that the artifact came from a trusted publisher.

For a running module set, you can inspect the list of observable modules:

~~~bash
java --list-modules
~~~

To view the resolution process during a launch:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.Main
~~~

Resolution details help investigate which modules were selected and how dependencies were wired. Save these logs in testing or incident investigation environments when reproducing runtime configurations.

### 3.3. Avoiding Module Name Collisions

If multiple sources provide a module with the same name, the module path configuration can become ambiguous or resolve from a different source than intended. Do not rely on incidental directory ordering to pick a version.

Operational rules should be:

- Only one approved artifact/version per module name in the runtime image.
- Do not mix old and new build output directories.
- Do not allow directories writable by untrusted users to precede verified artifact directories.
- Verify module names and hashes before assembling the final module path.

Place artifacts into a dedicated staging directory after verification, then run the JVM using that exact directory.

## 4. Automatic Modules and the Unnamed Module Must Be Managed Separately

### 4.1. Automatic Modules

A JAR without `module-info.class` placed on the module path can become an automatic module. Its module name is typically derived from the `Automatic-Module-Name` manifest attribute if present, or otherwise derived from the JAR filename.

Automatic modules can read other modules and export their own packages according to automatic module rules. This is a transitional mechanism allowing legacy libraries to participate on the module path.

Because their readability and export scope are broader than typical explicit modules, automatic modules should not be the default choice for untrusted plugins. Verify the JAR, check the module name, and evaluate dependencies before allowing it into runtime.

### 4.2. The Unnamed Module and the Classpath

Code on the classpath belongs to the unnamed module. Placing a library on the classpath does not make it safer code. It only changes how code is organized and encapsulated.

If an application mixes the module path and classpath, maintain an explicit inventory:

- Which JARs are named/automatic modules?
- Which JARs are on the classpath?
- Which modules have readability to the unnamed module?
- Are any `--add-reads`, `--add-exports`, or `--add-opens` flags granting extra access?

Do not treat the classpath as an "uncontrolled plugin zone." Code on the classpath still executes with process privileges.

## 5. Options That Alter Module Sources Must Be Protected

Beyond `--module-path`, several launcher options can alter the set of modules or contents loaded:

| Option | Effect | Risk to Manage |
|---|---|---|
| `--upgrade-module-path` | Allows modules on the upgrade path to replace corresponding system modules | Can alter the implementation of JDK modules |
| `--patch-module` | Adds/replaces classes or resources belonging to a module | Runtime differs from released artifacts |
| `--add-modules` | Adds modules to the graph to resolve | Increases the set of code that can be used |
| `--add-reads` | Adds a readability edge | Creates dependencies outside the descriptor |
| `--add-exports` | Opens a public package to targets | Expands the accessible API surface |
| `--add-opens` | Allows deep reflection | Exposes implementation details to targets |

Do not allow untrusted users or plugins to supply JVM arguments to a privileged process. Flags such as `--patch-module` or `--upgrade-module-path` can alter the code loaded by the JVM; flags opening packages can break encapsulation boundaries the application relies on.

Store launcher arguments in managed, reviewed, and version-controlled configurations.

## 6. Compile-Time Module Source Path Has Different Risks

### 6.1. `--module-source-path` Specifies the Source Tree

When compiling multiple modules, `javac` can use:

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
~~~

Where:

- `--module-source-path` specifies the location and structure of module sources.
- `-m` selects the modules to compile.
- `-d` selects where to write output.

The source tree is an input to the compiler. Normally compiling Java source alone does not mean methods in the source are executed. However, the build pipeline can execute other components during compilation.

### 6.2. Annotation Processors Are Code Running in the Build Process

Annotation processors are Java code loaded by `javac` to process annotations. Processors can read files, write files, access the environment, generate sources, or perform other operations with the privileges of the compilation process.

Example command with a processor path:

~~~bash
javac --processor-path tools/processor.jar ^
    -d out ^
    --module-source-path src ^
    -m com.acme.app
~~~

If `processor.jar` is untrusted, processor code can execute on the build machine. This is a different risk from classes produced after compilation.

Control points:

- Do not load annotation processors from unapproved dependencies.
- Use `--processor-path` or `--processor-module-path` explicitly instead of letting processors be discovered from uncontrolled sources.
- Specify required processors with `-processor` when appropriate.
- If annotation processing is not needed, consider `-proc:none` to disable running processors.
- Control Gradle/Maven plugins and build scripts because they can also execute code during the build process.

Example disabling annotation processing when compiling sources that do not need processors:

~~~bash
javac -proc:none -d out --module-source-path src -m com.acme.app
~~~

`-proc:none` is not a sandbox for the compiler and does not disable all code that can run during a build. Build plugins, compiler wrappers, scripts, code generators, or dependency tasks still require governance.

### 6.3. Untrusted Sources Can Cause Resource Exhaustion

Even without processors, source code can be crafted to make the compiler consume excessive CPU, memory, or disk: huge files, complex generic structures, deeply nested annotations, or an abnormal number of source files.

For untrusted sources, limit:

- CPU time and memory of the build worker.
- Execution duration and output size.
- File count and source/archive sizes.
- Write permissions outside the workspace.
- Network access during the build if unnecessary.
- Access to pipeline credentials and secrets.

## 7. Inspecting Dependencies and Contents Before Use

JDK tools can be used to gather information before bringing a module into runtime.

### 7.1. Inspecting the Module Descriptor

~~~bash
jar --describe-module --file libs/acme-plugin.jar
~~~

Examine the module name, packages, `requires`, `exports`, `opens`, and service declarations. If the descriptor does not match the release manifest or dependency policy, stop moving the artifact into staging.

### 7.2. Inspecting Static Dependencies

~~~bash
jdeps --print-module-deps --module-path libs libs/acme-plugin.jar
~~~

`jdeps` analyzes dependencies expressed in bytecode. It does not fully detect dynamic reflection, loading classes by name, file/network access, or all runtime dependencies.

To detect references to JDK internal APIs:

~~~bash
jdeps --jdk-internals libs/acme-plugin.jar
~~~

Results serve as clues for compatibility and migration evaluation. This is not a tool for proving code is secure.

### 7.3. Verifying Artifact Integrity

Hashes of approved artifacts can be recorded:

~~~bash
sha256sum libs/acme-plugin.jar
~~~

On PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\libs\acme-plugin.jar
~~~

If using JAR signing, signatures can be verified:

~~~bash
jarsigner -verify -strict -certs libs/acme-plugin.jar
~~~

Signatures are only useful when the signer identity and certificate chain are trusted under organizational policy. A signed JAR does not automatically become safe; signing verifies the signer and integrity under the signing mechanism, not that the code lacks dangerous behavior.

Combine hashes/signatures with repository allowlists, build provenance, version locking, and dependency approval processes.

## 8. Service Providers Are a Code Activation Point

A module descriptor can declare:

~~~java
module com.acme.plugin {
    provides com.acme.spi.PaymentProvider
        with com.acme.plugin.internal.DefaultPaymentProvider;
}
~~~

An application can use `ServiceLoader` to discover providers:

~~~java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.process();
}
~~~

Resolving service bindings and instantiating/invoking providers occur at different times. When the application iterates over or uses a provider, the provider's constructor and methods can run. Do not treat `provides` declarations as harmless metadata if the module path contains untrusted modules.

Principles:

- Only allow providers from approved modules/artifacts.
- Do not automatically load every provider found on the module path if the application does not need it.
- Verify the module providing the service and its version before invoking it.
- Run providers in a process or sandbox matching the trust level.

## 9. JPMS Does Not Replace Process Isolation

If the requirement is to run plugins or sources from outside the organization, design security boundaries outside the module system.

Common options:

- **Separate process** under an OS account with least privilege.
- **Container** with a read-only filesystem, network policy, CPU/memory limits, and no mounted secrets.
- **Dedicated VM or sandbox** when a stronger boundary than a container is required.
- **IPC with explicit schemas and authorization** so the host provides only selected capabilities.
- **Timeouts, quotas, and cancellation** per plugin request.

Do not pass production credentials, CI tokens, or sensitive config files into a process running untrusted modules. If a plugin needs a capability, the host should expose a narrow API or IPC rather than sharing the entire environment and filesystem.

The Security Manager was once a Java mechanism for restricting permissions, but it has been deprecated for removal. Do not design new systems around the assumption that JPMS or the Security Manager will sandbox an untrusted module. Use OS/runtime deployment isolation as the execution boundary.

## 10. Safe Staging Workflow for Modular Artifacts

A practical workflow can be broken down into steps:

1. **Receive artifacts/sources** into a staging area without production privileges.
2. **Verify provenance**: repository, publisher, version, provenance, hash, and signature if applicable.
3. **Inspect structure**: module name, descriptor, packages, dependencies, and service providers.
4. **Inspect dependencies** using tools like `jar` and `jdeps`, then compare against allowlists.
5. **Compile in an isolated build worker**; control processors, plugins, network, and resource quotas.
6. **Run integration tests in a separate process/container** with mock data and least privileges.
7. **Package an immutable staging image** containing exact approved modules.
8. **Promote verified artifacts** to the next environment using the same hash; do not silently rebuild from different sources.
9. **Observe runtime**: log module resolution, versions, startup arguments, and activated service providers.

A production module path should be built from an immutable, approved set of artifacts. Do not directly use upload directories, mutable workspace directories, or directories shared across multiple tenants.

## 11. Example: Checking Before Running a Plugin

Suppose a plugin is located at `incoming/payment-plugin.jar`. Manual checks in staging can be organized as:

~~~bash
jar --describe-module --file incoming/payment-plugin.jar
jdeps --print-module-deps --module-path approved-libs incoming/payment-plugin.jar
sha256sum incoming/payment-plugin.jar
~~~

After verifying the hash, publisher, module name, and dependencies against policy, copy the artifact into an immutable runtime directory:

~~~text
runtime/
├── app/
│   └── com.acme.host/
└── approved-modules/
    ├── com.acme.spi.jar
    └── payment-plugin.jar
~~~

Run the application with the approved module path:

~~~bash
java --show-module-resolution ^
    --module-path runtime/approved-modules ^
    -m com.acme.host/com.acme.host.Main
~~~

These commands illustrate the verification and staging steps. In a real system, automate comparing hashes/provenance against approved metadata and ensure the running process has no excessive privileges.

If plugins come from external users or tenants, verifying hashes alone is insufficient to allow running inside the host process. Run plugins in a separate process/container and restrict the data, network, and filesystem they can access.

## 12. Review Checklist

Before allowing a module or source into build/runtime, confirm:

- [ ] Artifact/source origin and publisher are verified.
- [ ] Module name and descriptor match the release manifest.
- [ ] No unintended module name collisions or module overrides exist.
- [ ] Automatic modules and classpath dependencies are identified.
- [ ] The module path contains only approved directories/archives and is not writable by untrusted users.
- [ ] `--patch-module` and `--upgrade-module-path` are controlled like code changes.
- [ ] Annotation processors and build plugins are approved; processing is disabled when unnecessary.
- [ ] Dependencies, service providers, and internal JDK APIs are inspected at an appropriate level.
- [ ] Hash/signature/provenance are verified per policy.
- [ ] Build and runtime do not receive credentials or OS permissions beyond their needs.
- [ ] Untrusted plugins run in an isolated process/container with quotas.
- [ ] Runtime images are immutable and reproducible by hash/version.

## Conclusion

The module path determines which modules can participate at runtime; the module source path determines which sources the compiler processes. Both are inputs requiring control. At runtime, a modular JAR is still executable code running with the process's privileges. At compile time, annotation processors and build plugins can execute code directly on the build machine.

**JPMS protects access boundaries between modules; it does not authenticate provenance and does not sandbox malicious code.** Combine provenance/integrity verification, dependency and launcher argument controls, isolated build workers, immutable module paths, and process/container isolation to protect applications.