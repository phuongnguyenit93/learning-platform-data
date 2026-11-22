# Module consumers: applications, libraries, and shared platforms

When planning to upgrade or migrate a Java module, it is necessary to identify what type of consumer the module serves. A module can be packaged and used as a standalone application, embedded into another application as a library, or participate in a shared platform for multiple projects. These three usage types create three different compatibility scopes.

For example, a change that prevents an application from starting is usually detected during test runs and test deployments. That same change in a library can cause dozens of applications to fail to compile. If it is in a shared platform, the impact can spread to the build process, dependencies, and runtime of multiple systems. Therefore, a single set of criteria cannot be used to conclude that every module is ready for migration.

## 1. Why is it necessary to identify the consumers?

The consumer indicates how the module is brought into the system, who depends on it, and what is considered the contract to keep stable. This information determines:

- **Scope of impact:** one deployment process, dependent applications, or an entire group of projects sharing the platform.
- **Compatibility checkpoints:** startup capability, public APIs, dependencies, configuration, data, or build rules.
- **Release method:** deploying an application, releasing a library version, or releasing a set of platform components synchronously.
- **Migration approach:** whether it can be upgraded and rolled back independently or requires coordinating multiple consumers.
- **Completion evidence:** testing the actual application, testing library consumers, or a test matrix representing multiple projects.

The directory name or Gradle project name is not enough to classify a module. A project may be named `core`, `common`, or `platform`, yet its actual usage determines its compatibility contract. It is necessary to examine the dependency graph, packaging method, entry point, deployment configuration, and the consumers using the artifact.

## 2. Module used as an application

An application is a unit that can be launched and operated as an independent system or process. It typically has its own entry point, environment configuration, runtime lifecycle, resources to be allocated, and deployment process. An application may use many other libraries and services, but it itself is the unit that the operations team starts, monitors, upgrades, and rolls back.

### 2.1. Application contracts

For an application, the key question is: after migration, can the application be built, started, connected to the required components, and continue to deliver the committed behavior?

Contracts that typically need to be reviewed include:

| Contract | What needs to be ensured |
|---|---|
| Build and packaging | The build produces the correct type of artifact; build tasks, plugins, and build tools are compatible with the target environment. |
| JVM and runtime | The deployment JVM supports the bytecode, Java APIs, and libraries that the application uses. |
| Startup | Entry point, auto-configuration, dependency injection, and initialization order still work. |
| Configuration | Property names, data types, default values, environment variables, and configuration loading behavior are not changed unexpectedly. |
| Communication | HTTP endpoints, messages, events, protocols, and data formats remain compatible with relevant consumers. |
| Data | Queries, schemas, migrations, and data read/write operations work during the transition period. |
| Operations | Logging, metrics, tracing, health checks, timeouts, threads, memory, and shutdown behavior still meet requirements. |

You should not only check whether the application compiles successfully. An application may build successfully yet fail to start due to configuration changes, fail to connect to the database due to an incompatible driver, or run but return different data than before.

### 2.2. How to evaluate when migrating an application

Before making changes, record the current runtime environment: JDK version, startup method, environment variables, configuration, critical dependencies, and external services. Then identify the target environment and check each point that may change.

A practical sequence includes:

1. Build the application with the target configuration and save the logs, artifacts, and verification results.
2. Start the application in an environment close to the real deployment environment.
3. Check health checks, database connections, caches, brokers, and integrated services.
4. Run smoke tests for critical business flows and verify API contracts.
5. Inspect logs, metrics, runtime errors, resource usage, and shutdown behavior.
6. Deploy by environment or by instance group; prepare a way to roll back to the previous version if needed.

If the change involves schemas or data formats, you must consider the ability to run the old and new versions concurrently. For example, the new application may be deployed while some old instances are still processing requests. Data changes are only safe when both versions can operate during the transition period, or when a controlled deployment plan is in place.

## 3. Module used as a library

A library is a component declared as a dependency by an application or another module. Typically, a library does not create an independent deployment process on its own. Consumers place the library's artifact on the compile classpath and/or runtime classpath to use the classes, interfaces, annotations, resources, or services provided by the library.

For example, an application can declare a Gradle dependency as follows:

```kotlin
dependencies {
    implementation("com.example:customer-client:2.4.0")
}
```

The consumer application decides the startup time and operating environment. However, changes in the library can still cause that application to fail to compile, fail to link at runtime, or change its behavior.

### 3.1. Library contracts

The primary contract of a library is the API and behavior that consumers rely on. Several concepts need to be distinguished:

- **Source compatibility:** old consumer source code still compiles when using the new library version.
- **Binary compatibility:** compiled consumer bytecode still links and runs with the new library version within the committed scope.
- **Behavioral compatibility:** the same call still produces results, exceptions, and side effects consistent with the published contract.
- **Runtime compatibility:** the library and its dependencies can be loaded and run on the JVM and environment supported by the consumer.

These concepts are related but do not substitute for one another. A change may still compile yet produce a different calculation result. Conversely, consumer source code may need modifications even though some compiled bytecode still runs.

Changes likely to affect consumers include:

- Removing, renaming, or reducing the visibility of public classes, methods, constructors, or fields.
- Changing parameter types or the return type of a method.
- Modifying an interface that consumers implement themselves; for example, adding a new abstract method.
- Changing exception-throwing behavior, default values, processing order, or `null`-handling rules.
- Changing annotations, generic contracts, serialization formats, resource paths, or configuration names used by consumers.
- Upgrading the Java version or dependencies such that the consumer's environment can no longer meet the minimum requirements.

In particular, a library compiling successfully on a new JDK does not prove that every consumer can run it. If the artifact is compiled into bytecode of a higher Java version than the consumer's JVM, the consumer may encounter a class-loading error such as `UnsupportedClassVersionError`. The library may also call APIs that only exist in the new JDK even though part of the source code still looks compatible.

### 3.2. Dependencies and public API scope

A library typically has direct dependencies and transitive dependencies. Consumers can be affected by both types, even when the consumer does not directly declare that dependency.

With a Gradle Java Library, it is necessary to distinguish between dependencies exported as part of the public API and dependencies used only for internal implementation. For example:

```kotlin
dependencies {
    api("com.example:public-model:1.2.0")
    implementation("com.example:internal-helper:3.1.0")
}
```

`api` is appropriate when types from the dependency appear in the public API and consumers need that dependency on the compile classpath. `implementation` is appropriate for dependencies used only inside the library. Choosing the wrong scope can expose unnecessary dependencies, force consumers to resolve version conflicts, or make the API difficult to use.

When migrating a library, check the dependency tree, minimum versions, excluded dependencies, version conflicts, and the classes that consumers actually see. An internal dependency change can still cause runtime errors if the library requires a new version with different behavior or APIs.

### 3.3. How to evaluate when migrating a library

You should not only run tests inside the library's repository. That test suite usually only verifies how the author uses the library and does not necessarily represent how external consumers are using it.

You should check:

1. The public API before and after the change, including supported classes, methods, constructors, interfaces, annotations, and resources.
2. The ability to compile sample consumers on JDK versions within the supported range.
3. The ability to run previously compiled consumer bytecode if the library commits to binary compatibility.
4. The behavior of critical APIs, including boundary values, exceptions, concurrency, and serialization.
5. Transitive dependencies and dependency resolution in a real consumer application.
6. Upgrade guides, deprecations, and release versions.

If an API must be changed, you can keep the old API during a transition period, add the new API, mark the old API as deprecated, and provide replacement instructions. Only remove the old API when the versioning policy and compatibility scope allow. This decision needs to be based on actual consumers and the library's support commitments.

## 4. Module used as a shared platform

A shared platform provides conventions, dependencies, plugins, foundational libraries, or infrastructure components for multiple applications and libraries to use consistently. A platform may consist of a single artifact or a version-managed set of components.

Examples of platform components include:

- BOMs or Gradle platforms to manage dependency versions.
- Gradle convention plugins to standardize build configuration.
- Shared foundational library sets, starters, or adapters.
- Default configurations for logging, observability, security, and service connectivity.
- Common APIs or clients for applications to communicate with internal systems.
- Rules for JDK, Spring, build plugins, and allowed dependencies.

A platform is usually not a business application with a single entry point. It can have an impact at build time, compile time, application startup, or throughout runtime. Therefore, testing a single platform artifact in isolation is not enough to evaluate the impact.

### 4.1. Platform contracts

A platform's contract consists of two layers:

1. **Contract of each component:** the APIs, dependencies, plugins, configurations, and behavior that each artifact provides.
2. **Coordination contract:** the components are expected to work together under a unified set of versions and conventions.

A platform can cause failures even when each individual library builds successfully. For example, a BOM may introduce an incompatible combination of versions; a convention plugin may alter tasks or compiler options; default configuration may change the startup behavior of consumer applications.

Questions to answer when migrating a platform:

- Which groups of applications, libraries, and modules are using the platform directly or indirectly?
- Which versions of JDK, Gradle, plugins, and frameworks does the platform support?
- Do artifacts in the same release set require synchronized usage?
- Which build rules or default configurations might change consumers?
- Are there any consumers that need to be supported during the transition period?
- Can the old and new versions coexist in the same system?

### 4.2. How to evaluate when migrating a platform

The test scope should represent different types of consumers, rather than just picking one convenient application. A simple matrix might include a web application, a background processing application, an independently released library, and a project using convention plugins. Depending on the platform, it may be necessary to add consumers using different frameworks or JDKs.

The evaluation process typically includes:

1. List the artifacts, plugins, conventions, and configurations provided by the platform.
2. Build a dependency graph to find direct and indirect consumers.
3. Define the supported version matrix: JDK, Gradle, frameworks, and key dependencies.
4. Build and test representative consumers using the new platform version set.
5. Check dependency resolution, build tasks, default configurations, and runtime behavior.
6. Test upgrading by consumer group, record exceptions, and prepare a roadmap for groups that cannot upgrade yet.
7. Publish release notes clearly stating changes, compatible versions, migration steps, and when support for the old version ends.

The more consumers a platform has, the higher the cost of an incompatible change. Therefore, there should be clear versioning rules, representative consumer testing, and a sufficient transition period for project teams to upgrade in a controlled manner.

## 5. Comparing the three usage types

| Aspect | Application | Library | Shared platform |
|---|---|---|---|
| How it is used | Launched and operated as an independent unit | Declared as a dependency of a consumer | Multiple projects use a shared set of dependencies, plugins, conventions, or components |
| Primary contract | Runtime behavior, service APIs, configuration, and data | Public API, source, binary, and behavioral compatibility | Component contracts and the coordination among them |
| Release unit | Application artifact and deployment | Library artifact version | Platform version set or release train |
| Typical risks | Fails to build, fails to start, integration errors, or data changes | Consumer fails to compile, linking errors, or behavioral changes | Multiple consumers fail at build/runtime due to changes in dependencies or shared conventions |
| Key checks | Smoke tests, integration tests, deployment and operations checks | API checks, consumer tests, binary/runtime compatibility | Version matrix, dependency convergence, and testing multiple representative consumers |
| Migration approach | Deploy by environment or instance group | Release a version and guide consumers to upgrade | Migrate by consumer group, with a roadmap and synchronized version management |

These three types can appear together in a single system. An application typically consumes multiple libraries; those libraries may in turn be managed by a shared platform. Therefore, it is necessary to distinguish between **the role of the module being migrated** and **the types of consumers downstream of it**.

## 6. A module can serve multiple types of consumers

Not every module has only one usage type. An internal library may be used by an application in the same repository while also being packaged for multiple other projects to use. A platform component may also contain a runtime library that applications place directly on the classpath.

When multiple consumer types coexist, record each contract separately:

- Consumers running applications need checks for startup, configuration, integration, and operations.
- Consumers using libraries need checks for APIs, dependencies, bytecode, and behavior.
- Consumers using platforms need checks for version combinations, build conventions, and impact across multiple projects.

Results should not be merged into a single generic conclusion such as “module is compatible” without clearly stating which consumer type, which environment version, and under which conditions it is compatible. If the three roles have different release requirements, consider splitting artifacts or clearly defining usage profiles to avoid a change serving one consumer breaking another consumer.

## 7. How to identify actual consumers

Classification must be based on evidence. You can start from the following sources:

| Inspection source | Signs to look for |
|---|---|
| Gradle settings and project dependencies | Which modules directly depend on the module under review; whether any transitive dependency continues propagating it to other consumers. |
| Dependency declarations in build files | Whether the artifact is used as a library, platform/BOM, or plugin. |
| Source code | Whether there is an entry point, startup configuration, public API, or extension point for consumers. |
| Deployment configuration and workflows | Whether an artifact is executed, an image is released, a service is deployed, or there is a separate operations process. |
| Dependency publication | Whether an artifact is published for other projects to use; which versions are being declared by consumers. |
| Testing and CI | Which projects build with, run integration tests with, or verify compatibility with this module. |
| Usage documentation | Whether users are instructed to run an application, add a dependency, or apply a platform convention set. |

Direct and indirect consumers should be distinguished. For example, application A depends on library B, and B depends on module C. C might not appear in A's build file yet still be on A's runtime classpath. When changing C, the impact scope may include A and other applications that have the same dependency chain.

A useful consumer list should clearly state the project name, usage type, version in use, JDK environment, how the dependency is obtained, criticality level, and testing status. If consumers have not been found yet or a transitive dependency cannot be verified, record that as an information gap instead of assuming the module has no users.

## 8. Process for selecting compatibility criteria for a migration

The following process can be applied for each module:

### Step 1: Describe the current role

Clearly state whether the module is an application, library, shared platform, or a combination of multiple roles. Describe how the module is built, packaged, released, and introduced into the system.

### Step 2: Map consumers

List direct and indirect consumers. For each consumer, identify the version currently in use, JDK/runtime, relevant dependencies, and criticality to the system.

### Step 3: Finalize the support scope

Identify the current environment, target environment, and versions that need continued support. Distinguish between the JDK used to run Gradle, the JDK toolchain used for compiling, and the JDK used when running the application; these three environments can differ.

### Step 4: Identify affected contracts

Select the contracts corresponding to the role: startup and operations for applications; APIs and dependencies for libraries; version alignment and build conventions for platforms. Add data or protocol contracts if the module participates in those flows.

### Step 5: Select test evidence

Each risk needs a way to be verified. For example, API changes need consumer compile tests; bytecode changes need target runtime checks; configuration changes need startup/integration tests; BOM changes need dependency resolution checks across representative consumers.

### Step 6: Plan the release and migration roadmap

Decide on the versioning approach, compatibility window, consumer groups to upgrade first, how to handle consumers that are not ready yet, and rollback conditions. For incompatible changes, release notes must clearly specify what changed and what consumers need to do.

### Step 7: Post-migration verification

Record which consumers have upgraded, test results in each environment, and remaining exceptions. Only conclude that a scope is complete when there is evidence appropriate for each consumer type within the committed scope.

## 9. Illustrative example: raising the Java baseline

Suppose a project team wants to raise a module's Java baseline from Java 17 to Java 21. This is a hypothetical example to illustrate classification; the actual decision still depends on each project's support scope.

**If the module is an application:** you need to ensure the deployment environment has a suitable JVM, images or servers have been updated, dependencies are compatible, and the startup process works. A successful build on a development machine does not prove the production environment is ready.

**If the module is a library:** you need to identify which consumers still run Java 17. If the library releases bytecode that only runs on Java 21, consumers running Java 17 cannot load that library. It may be necessary to maintain a branch or older compatible version, or delay raising the baseline until consumers have migrated.

**If the module is a shared platform:** you need to check all consumer groups that the platform supports. Beyond bytecode, you must examine the Gradle wrapper, Gradle plugins, compiler toolchain, frameworks, and managed dependencies. A consumer group may already be running Java 21 yet still be unable to upgrade because a build plugin or another component is not yet compatible.

This example shows that the same Java baseline change creates different action items. The migration scope must be derived from actual consumers and contracts, not only from the module's compiler configuration.

## 10. Checklist before starting a migration

- [ ] Identified whether the module is used as an application, library, platform, or a combination of multiple roles.
- [ ] Found direct and indirect consumers using a dependency graph or equivalent evidence.
- [ ] Recorded the JDK used to build, compile, and run each consumer.
- [ ] Identified APIs, configurations, dependencies, protocols, and data that may be affected.
- [ ] Distinguished between source, binary, behavioral, and runtime compatibility.
- [ ] Selected representative consumers and testing methods appropriate for each role.
- [ ] Determined the release method, upgrade roadmap, and rollback conditions.
- [ ] Recorded consumers or environments that could not be verified yet.

## Conclusion

Applications, libraries, and shared platforms have different ways of consuming modules and different compatibility contracts. Applications focus on build, startup, integration, and operational capabilities; libraries focus on APIs, dependencies, and compatibility with consumers; platforms focus on the consistency of multiple components and cross-project impact. Correctly identifying the consumers helps isolate impact, choose the right tests, and build a verifiable migration roadmap.
