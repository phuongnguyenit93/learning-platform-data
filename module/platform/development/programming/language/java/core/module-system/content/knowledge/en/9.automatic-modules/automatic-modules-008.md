# Strategy for Eliminating Automatic Modules in Long-Term Projects

Automatic modules act as a bridge helping legacy Java libraries participate on the module path without needing an explicit module descriptor yet. This mechanism supports step-by-step migration, but it does not establish clear API and dependency boundaries like an explicit named module. If a project wants to leverage JPMS long-term, the goal should be for every dependency resolved in the runtime module graph to have an explicit module descriptor, or be replaced by a dependency that already has one.

Migration must follow the actual dependency graph, including transitive dependencies. Upgrading only a few direct libraries or adding the Automatic-Module-Name attribute is not enough to eliminate automatic modules.

## 1. Defining the Target State

Before changing dependencies, agree on completion criteria:

- Every application module owned by the project has an explicit module descriptor.
- Libraries in the resolved runtime module graph are all explicit named modules or JDK system modules.
- No automatic modules remain in the production runtime configuration.
- Legacy dependencies have been upgraded, replaced, or converted into explicit modular artifacts with managed and verified descriptors.
- API packages, reflection access, and service providers are declared intentionally.
- Builds and CI detect automatic modules again whenever a new dependency is added.

Do not equate this goal with simply silencing a warning line. Automatic modules can still appear in transitive dependencies even if the application's build file does not declare that library directly.

You also need to distinguish three states:

| State | Meaning | Meets Goal of Eliminating Automatic Modules? |
|---|---|---|
| Explicit named module | JAR has an explicit module descriptor, typically module-info.class | Yes |
| Automatic module | JAR lacks a descriptor but is placed on the module path; descriptor is derived automatically | No |
| Unnamed module | Code/JAR resides on the classpath and belongs to the class loader's unnamed module | Not an automatic module, yet still not explicitly modularized |

Moving a JAR from the module path back to the classpath only changes how it is loaded to the unnamed module. That is not a conversion into an explicit module and is not the end goal of a complete JPMS application.

## 2. Inventorying the Entire Dependency Graph

Start by listing direct and transitive dependencies for each application module. Analyze both the compile classpath and runtime classpath because a library may appear only at runtime.

With Gradle, you can view the dependency tree of the runtime configuration:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

To understand why a specific artifact is pulled in:

~~~bash
./gradlew :app:dependencyInsight --dependency legacy-codec --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree
~~~

Once you have the artifact list, classify each JAR with:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

The output helps identify whether the JAR has an explicit descriptor, is an automatic module, or is not yet a module on the module path. For automatic JARs, the tool output typically shows the derived module name and automatic status.

You can use jdeps to analyze bytecode dependencies and identify required modules:

~~~bash
jdeps --print-module-deps --module-path libs path/to/application.jar
~~~

When analyzing a multi-release JAR or a specific target JDK, use the appropriate multi-release option so the results reflect the bytecode actually executed. Results from jdeps serve as investigative data; they do not replace reading the library's API, service descriptors, and reflection configuration.

Create an inventory table with at least the following information:

| Field | What to Record |
|---|---|
| Artifact | group/artifact/version or corresponding coordinates |
| Dependency path | Which module pulls in the artifact, directly or transitively |
| Runtime scope | Whether it appears in runtimeClasspath |
| Module status | Explicit, automatic, unnamed/classpath, or system module |
| Module name | Name taken from the module descriptor or automatic module name |
| Upstream status | Whether a newer version already has module-info.class |
| Migration action | Upgrade, replace, contribute descriptor, repackage, or keep as time-boxed exception |
| Owner | Person or team responsible for updating and maintaining |

Do not record only the automatic module name. You need to know which dependency pulls it in so you can address the right source in the build graph.

## 3. Prioritizing Upgrades to Explicit Module Versions from Upstream

This is usually the option with the lowest maintenance cost.

For each automatic module, check release notes and JAR contents of newer versions. A library may already provide a module descriptor in a newer release, or offer a separate release for Java 9 and later.

Workflow:

1. Identify the direct or transitive dependency producing the automatic module.
2. Find a compatible version that already has module-info.class.
3. Read the new version's descriptor using jar --describe-module.
4. Check the module name, requires, exports, opens, uses, and provides.
5. Upgrade the dependency in the build file or constraint/version catalog.
6. Run compile, unit tests, integration tests, and test launching on the module path.
7. Confirm the runtime dependency graph no longer contains that automatic module.

Do not assume the new version's module name will match the old automatic module name. If upstream changed the module name, dependent modules must update their requires directives and may need launcher configuration adjustments.

Prefer the stable module name published by upstream. Do not derive a name yourself from the JAR name if upstream has declared an official descriptor.

## 4. When Upstream Does Not Yet Provide a Module Descriptor

There are three main approaches when a library does not yet have an explicit module.

### 4.1. Contributing a Module Descriptor Upstream

If the project can work with the vendor or library community, propose adding module-info.java upstream and releasing a new version.

The descriptor should be designed based on the real API:

- Declare direct dependencies with requires.
- Export only packages consumers need to use.
- Use qualified exports for internal SPIs with known consumers.
- Declare opens only for packages where frameworks need deep reflection.
- Declare uses and provides for services if the library consumes or provides services.
- Avoid requires transitive unless the dependency is genuinely part of the API consumers must read.

A good descriptor is the library's module contract. Adding a descriptor should not aim merely to stop tools from reporting automatic modules while still exporting every package and declaring inaccurate dependencies.

### 4.2. Creating a Project-Managed Explicit Modular Artifact

If source is available or the license allows modification/repackaging, the project can create a controlled modularized build:

1. Obtain the exact source or binary artifact and pin its source checksum/version.
2. Use jdeps to analyze dependencies and optionally generate a suggested module-info.java.
3. Manually review the module name, requires, exports, opens, uses, and provides.
4. Compile the descriptor with the appropriate module path/dependencies.
5. Package the descriptor together with the library contents into a new modular JAR.
6. Store the build procedure, source, checksums, patches, and tests in your repository or internal artifact repository.
7. Publish the internal artifact under your own coordinates and version, without spoofing the upstream release source.
8. Run compatibility tests and verify module resolution.

You can start the analysis with:

~~~bash
jdeps --generate-module-info generated-module-info path/to/legacy.jar
~~~

A module descriptor generated by jdeps is only a suggested draft. Bytecode analysis tools cannot decide on their own which packages are supported API, which packages need to be opened for reflection, or which dependencies are part of the public contract. Maintainers must review the descriptor before release.

Do not modify vendor JARs sitting in the build cache or downloaded from repositories directly. Produce a new output artifact reproducible from a pinned input source. If the JAR is digitally signed, modifying its contents invalidates the old signature; the release process for the new artifact must handle signing and provenance per project policy.

### 4.3. Replacing the Library When Modularization Cost Is Too High

If the library is unmaintained, has split packages, hard-to-resolve dependency cycles, or overly broad reflection requirements, evaluate a replacement library with a better explicit module.

Compare on these criteria:

- Required features and APIs.
- Compatibility with Java version and other dependencies.
- Performance and runtime behavior.
- Service providers and reflection mechanisms.
- Upstream activity level.
- Long-term maintainability and licensing.
- Ease of adapting data or APIs in an adapter layer.

Sometimes writing a small adapter around an alternative API costs less than maintaining a modularized fork long-term.

## 5. Using Automatic-Module-Name in Its Proper Transitional Role

The **Automatic-Module-Name** manifest attribute lets a library publish a stable automatic module name when the JAR is placed on the module path:

~~~text
Automatic-Module-Name: com.acme.legacy.codec
~~~

This prevents consumers from depending on a module name derived from the JAR file name. When the file is renamed or its version suffix changes, the module name remains stable.

However, this attribute **does not create an explicit module descriptor**. The JAR is still an automatic module: packages are broadly exported, and the descriptor does not fully reflect the author's intended API boundaries and dependencies.

Therefore:

- Use Automatic-Module-Name as a name-stabilizing measure during the transition period.
- Clearly record that the dependency is still an automatic module in the migration list.
- Do not mark migration complete just because the module name is stable.
- Assign an owner and review deadline to upgrade, contribute a descriptor, or replace it.

If the project owns the library, you can release a compatible version with Automatic-Module-Name first, then release an explicit module version with the same name once the descriptor is designed. Check upstream versioning rules and compatibility before transitioning.

## 6. Handling Packages, Dependency Cycles, and Services When Moving to Explicit Modules

When adding a descriptor, several issues previously hidden by the classpath become visible.

### 6.1. Split Packages

Two modules containing classes in the same package can cause module graph resolution failures or leave package ownership unclear. Check for overlapping packages across JARs before modularizing.

Common solutions are:

- Designate a single module as the package owner.
- Upgrade the library so packages are reorganized.
- Replace or separate dependencies.
- Move internal code into its own package if the project controls the source.

Do not try to work around split packages by exporting extra packages or dumping JARs onto the same module path without understanding the conflict.

### 6.2. Dependency Cycles

Named modules cannot form requires cycles. If A requires B and B requires A, re-examine module boundaries.

Approaches to resolve:

- Extract shared interfaces/SPIs into a third module.
- Invert the dependency via an abstraction.
- Move shared code into an independent API module.
- Merge parts that truly cannot be separated if they share the same lifecycle and responsibility.

Do not use requires transitive to hide a dependency cycle.

### 6.3. Reflection and Frameworks

A library may work on the classpath because the classpath does not enforce strong encapsulation like named modules. After migrating to an explicit module, frameworks may need deep reflection access.

Identify the exact package and framework module needing access, then use restricted opens:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to com.acme.orm;
}
~~~

Options like --add-opens can help with diagnostics or temporary compatibility. Do not let broad launcher flags become the final design when specific permissions can be declared in the descriptor.

### 6.4. ServiceLoader

Inspect both legacy service configuration files in META-INF/services and the new descriptor. Explicit named modules should declare consumed services with uses and providers with provides ... with ....

~~~java
module com.acme.application {
    requires com.acme.report.spi;
    uses com.acme.report.spi.ReportExporter;
}
~~~

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;
    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

Ensure the provider module is resolved into the layer where the application looks for it. When switching from an automatic to an explicit module, verify provider behavior with integration tests rather than assuming legacy META-INF/services files will be handled identically across all configurations.

## 7. Avoid Using the Classpath to Hide Automatic Modules

Moving a JAR from the module path to the classpath puts it in the unnamed module. That can be useful during a transitional phase when legacy code still runs on the classpath, but it does not turn the JAR into an explicit named module.

The critical point is that a named module cannot declare requires on the unnamed module. Therefore, if an application module that has moved to an explicit named module needs to call a legacy library's API directly, moving that library back to the classpath will not satisfy the dependency in the standard way.

If you are forced to keep a library on the classpath in the short term:

- Keep the legacy integration at a controlled classpath/unnamed-module boundary.
- Let code at that boundary call named module APIs as needed.
- Do not let named modules depend back on classpath code.
- Record this as a migration exception, with an owner and removal criteria.
- Do not count this state as completing the modularization of the dependency.

For an application aiming for a complete module graph, the sustainable approach remains upgrading, replacing, or creating a managed explicit modular artifact.

## 8. Phased Migration Roadmap

You can break the work into small phases to keep the build green after each change.

| Phase | Actions | Exit Criteria |
|---|---|---|
| 1. Baseline | Record current JDK, build tool, module path, classpath, and dependency graph | Direct and transitive runtime dependency list established |
| 2. Inventory | Classify explicit, automatic, unnamed, and system modules; assign owners | Every automatic module has a dependency source and handling plan |
| 3. Upstream first | Upgrade dependencies that already have explicit module descriptors | Compile/tests pass; module names and APIs verified |
| 4. Internal modules | Add descriptors for project-owned modules; design exports/opens/services | Internal modules resolve cleanly with no cycles/split packages |
| 5. Legacy conversion | Contribute descriptors, create internal modular artifacts, or replace remaining libraries | Each artifact has provenance, version, and tests |
| 6. Runtime verification | Check module resolution on the exact production runtime image/configuration | No automatic modules remain in the resolved runtime graph |
| 7. CI enforcement | Add automated checks and fail when a new automatic module appears | New dependencies cannot silently introduce automatic modules into production |

Address libraries shared by many modules first, because a single upgrade or modularization can eliminate an automatic module from multiple dependency paths. Libraries appearing only on a rarely used branch can be handled later, though they still need an owner and target date.

After each dependency change, run tests on the exact target JDK. A library may compile cleanly yet fail at runtime due to reflection, service discovery, or class loading.

## 9. Setting Up a Verification Gate in CI

Once migration reaches a steady state, CI must prevent automatic modules from creeping back in.

An appropriate verification workflow:

1. Resolve the runtime dependency graph using the build tool.
2. Collect all JARs/modules actually present on the module path.
3. Use jar --describe-module or the ModuleFinder API to inspect each artifact's descriptor.
4. Classify automatic modules and explicit modules.
5. Compare against a migration exception allowlist with owner, reason, and expiration date.
6. Fail the build if a new automatic module appears or an exception has expired.
7. Run the application with --show-module-resolution in integration tests to verify runtime configuration.

Example command to observe launch configuration:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.application/com.acme.application.Main
~~~

Do not merely scan JAR files in a libs directory if the build tool resolves dependencies from multiple locations or constructs the module path dynamically. The CI gate must inspect the exact artifact set of the actual runtime configuration.

You can save a machine-readable migration report containing artifact, module name, descriptor status, dependency path, and approved exceptions. The report should be regenerated from the build's dependency graph, not maintained by hand after every upgrade.

## 10. Acceptance Criteria for Each Dependency

A dependency is marked as having eliminated its automatic module only when:

- The output artifact has an explicit module-info.class.
- The module name is stable and recorded.
- The descriptor has requires matching actual dependencies.
- Exports expose only necessary API packages.
- Opens grant deep reflection only to needed packages/consumers.
- uses/provides are declared and service discovery works if the library uses services.
- No split packages or requires cycles are introduced in the module graph.
- Compile, unit tests, integration tests, and runtime verification all pass.
- Source artifact, checksum, version, and build process are reproducible.
- The runtime dependency graph no longer contains that automatic module.

If a dependency does not meet these criteria, keep it in the migration list with a clear status and reason. Do not relabel it as an explicit module solely because it has Automatic-Module-Name.

## 11. Example Migration Report

Suppose the initial runtime graph has three automatic modules:

| Dependency | Initial State | Handling Approach | Target State |
|---|---|---|---|
| legacy-json | Automatic | Upgrade to upstream version with module-info.class | Explicit |
| old-logging-adapter | Automatic, transitive dependency | Replace with a maintained adapter | Explicit |
| vendor-codec | Automatic, no modular release yet | Create internal artifact with reviewed descriptor or replace | Explicit |

After making changes, re-run dependencyInsight/dependency:tree to confirm the old artifact is no longer pulled in via another branch. Next, verify the new artifact's module name and descriptor, then check runtime resolution.

An example final migration report can record:

- Total number of automatic modules in the runtime graph before migration.
- Number of modules upgraded from upstream.
- Number of modules replaced.
- Number of internal modular artifacts created.
- Number of remaining exceptions, owners, and due dates.
- Results of the CI gate and integration tests on the target JDK.

This report lets the team know how many dependencies genuinely remain to be addressed, instead of relying on the impression that the application has moved to JPMS because the main modules have module-info.java.

## 12. Principles for Long-Term Maintenance

- Treat Automatic-Module-Name as a name-stabilization measure during migration, not as an explicit module descriptor.
- Track transitive dependencies, not only direct dependencies.
- Prefer upstream-maintained descriptors; create internal modular artifacts only when there is a reproducible process and clear owner.
- Do not use the classpath to hide an automatic module and claim modularization is complete.
- Do not export all packages or open an entire module just to make a framework run; identify the needed APIs and reflection access.
- Do not use requires transitive casually; expose a dependency only when consumers genuinely need to read it through the API.
- Check service providers, split packages, dependency cycles, and reflection after every conversion.
- Put automatic module checks into CI so new dependencies do not regress the state.
- Periodically review exceptions and remove them once upstream or an alternative is ready.

The sustainable strategy is to manage each library's module descriptor as part of its contract, while managing the dependency graph as part of the build. When every runtime dependency has an explicit descriptor, API packages are clearly bounded, and CI protects that state, the project can leverage JPMS without relying long-term on the broad rules of automatic modules.