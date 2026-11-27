# Distinguishing Direct Dependencies, Transitive Dependencies, and Build Tools

## Learning Objectives

After this lesson, learners can:

- Distinguish between a direct dependency, a transitive dependency, and a build tool.
- Read a dependency graph to tell which libraries are declared directly, which are pulled in indirectly, and why a given version is selected.
- Understand that a build tool can have its own dependencies, which do not automatically become runtime libraries of the application.
- Choose the right scope or configuration for a dependency based on where it is used.
- Use commands and reports from Maven, Gradle, or other ecosystems to investigate dependencies.
- Manage versions, lockfiles, repositories, caches, and supply chain evidence in CI/CD.

## 1. Why Distinguish These Three Concepts?

A software project rarely consists solely of source code written by the team. To compile, test, package, and run an application, the project relies on libraries, plugins, compilers, test runners, packaging tools, and many other components. These components form a dependency graph that can grow quite large.

Without clearly distinguishing component types, teams easily run into several problems:

- Declaring a library in the wrong scope causes it to appear in the runtime package even though it is only used for testing.
- A transitive library has a vulnerability, yet nobody knows the application is using it.
- Upgrading a direct library alters many indirect libraries and causes compatibility errors.
- Confusing Maven or Gradle with an application library leads to mismanaging scope and misjudging the attack surface.
- Treating a build cache as the source of truth causes the pipeline to depend on stale state or fail to reproduce results.

These three concepts answer three different questions:

| Concept | Question to Answer |
|---|---|
| Direct dependency | Which components does the project explicitly declare and depend on directly? |
| Transitive dependency | Which components are brought in because another dependency needs them? |
| Build tool | Which tool orchestrates compiling, testing, packaging, and producing artifacts? |

They are related, but they are not three levels of the same kind of object. Direct and transitive describe relationships in a dependency graph. Build tool describes the tool's role in the software creation process. A build tool or plugin may also have its own dependencies, but that does not turn it into an application runtime library.

## 2. Direct Dependency: Dependencies Declared Directly by the Project

A direct dependency is a library or module explicitly declared by the project in its dependency management configuration because the project's source code or workflow needs to use it.

For example, a Java service might declare:

- Spring Web to provide HTTP endpoints.
- Jackson for JSON serialization if the source code calls Jackson APIs directly.
- PostgreSQL JDBC driver to connect to the database.
- JUnit to write and run tests.
- A logging library to emit logs from application code.

Declaring a dependency directly expresses the project's intent. When a dependency is upgraded, replaced, or removed, the team can review that change as part of the technical contract the application relies on.

A dependency should be declared directly if the project's own source code or configuration depends on its API or behavior. For example, if the code imports a class from library A, the project should declare A directly even if library B currently pulls A in indirectly.

You should not rely on a library happening to appear in the transitive graph in order to use its API. If dependency B changes and no longer pulls A in, the project may fail to compile. This is an undeclared dependency, which is hard to maintain and fragile during upgrades.

### 2.1. Direct Dependency Does Not Mean Runtime Dependency

A direct dependency may only be used during testing or building. For example, JUnit is typically a direct dependency of a project, yet does not need to be packaged into the production application.

Therefore, two axes must be distinguished:

- **Relationship:** direct or transitive.
- **Usage scope:** compile, runtime, test, build, or a specific configuration.

A dependency can be direct and used only for tests; a transitive dependency can be required at runtime. You should not infer scope from whether a dependency is direct or transitive.

## 3. Transitive Dependency: Dependencies Pulled In Indirectly

A transitive dependency is a component brought into the dependency graph because another dependency declares that it needs that component.

Suppose the project declares library A. A needs library B, and B needs library C. The graph looks like this:

~~~mermaid
flowchart TD
    APP["Project application"] --> A["A: direct dependency"]
    A --> B["B: transitive dependency"]
    B --> C["C: transitive dependency"]
~~~

The project only declares A, but dependency resolution can put both B and C onto the classpath or into the final package depending on scope and packaging rules.

Real-world example:

- The application declares a web framework.
- The web framework pulls in HTTP, JSON, or logging libraries.
- Those libraries in turn require other utility modules.

The team may not call APIs of B or C directly, yet the application is still affected by their versions, compatibility, and vulnerabilities.

### 3.1. Why Do Transitive Dependencies Still Need Management?

There are four main reasons:

1. **Compatibility:** the selected version of B or C might be incompatible with version A or with the JDK used by the application.
2. **Security:** a vulnerability in a transitive library can still affect the application.
3. **Size and performance:** a large dependency branch can increase artifact size, startup time, or the number of components that must be downloaded.
4. **Stability:** changing a dependency at level A can alter the entire B and C branch even if application code was not modified directly.

Transitive libraries should not be treated as "not our responsibility." The team still needs to know they exist, which versions are selected, and whether any issues require action.

### 3.2. Real-World Graphs Can Have Multiple Branches

In a large project, multiple direct dependencies may pull in the same transitive library. For example, A and D both need C, but require different versions.

~~~mermaid
flowchart TD
    APP["Application"] --> A["A: direct"]
    APP --> D["D: direct"]
    A --> B["B: transitive"]
    B --> C1["C: requested version 1"]
    D --> C2["C: requested version 2"]
~~~

The build tool or dependency resolver must apply resolution rules to pick a version, or report a conflict if no valid graph can be formed. The exact rules depend on the ecosystem and configuration.

Importantly, you should not guess the final version merely by reading a single declaration line in a configuration file. Inspect the dependency report after the resolver actually runs.

## 4. What Is a Build Tool and How Does It Differ from a Dependency?

A build tool orchestrates the steps that turn source code and input resources into testable or deployable outputs. Common tasks include:

- Parsing project structure and configuration.
- Downloading and resolving dependencies.
- Compiling source code.
- Running unit tests and configured test tasks.
- Processing resources, generating code, or running annotation processors.
- Packaging JAR, WAR, packages, or other artifacts.
- Generating reports, running quality checks, and publishing artifacts.

In the Java ecosystem, common build tools include:

- **Maven:** describes the project, dependencies, and lifecycle in a POM; executes phases through plugins.
- **Gradle:** defines builds using a DSL, tasks, and configurations; supports plugins and dependency resolution.
- **Ant:** a task-based build tool commonly seen in legacy projects or custom workflows.

A build tool usually runs on a developer's workstation or a CI runner. It may download plugins, compilers, libraries, and helper tools to execute the build. Those components belong to the build environment or the build process dependency graph.

Distinguish the following layers:

| Component | Role | Included in Runtime Artifact by Default? |
|---|---|---|
| Maven or Gradle | Build orchestration | No |
| Maven/Gradle plugin | Adds tasks or behavior to the build | No |
| JDK compiler | Compiles source code | No |
| Annotation processor | Generates or processes code during build | No, unless the application also needs a corresponding library at runtime |
| JUnit or test framework | Runs tests | Usually no |
| Application library | Provides functionality when the application runs | Potentially, depending on packaging and scope |
| Runtime framework | Provides the execution platform for the application | Usually yes |

A build tool can have its own dependencies. For example, a Maven plugin needs internal libraries to run. Those dependencies belong to the plugin's classloader or environment and do not automatically become application dependencies.

However, the boundary can become more complex when a plugin generates code, packages libraries, or adds components to an artifact. Therefore, inspect both plugin configuration and output contents instead of assuming everything downloaded during the build is excluded from runtime.

## 5. Three Axes to Separate When Reading Configuration

When reading `pom.xml` or `build.gradle`, identify three independent axes:

| Axis | Questions |
|---|---|
| Dependency relationship | Is the component declared directly or pulled in indirectly? |
| Scope / configuration | Is the component needed at compile, runtime, test, annotation processing, or as a build plugin? |
| Execution location | Does the component run inside the application, inside the test runner, inside the build process, or on the CI runner? |

Examples:

- JUnit: direct dependency, test scope, runs inside the test process.
- Jackson: can be a direct dependency, compile/runtime depending on the application, used inside the application.
- A logging module pulled in by a framework: transitive dependency, runtime scope, runs alongside the application.
- Maven Surefire Plugin: build plugin, runs to orchestrate tests; the plugin's own dependencies do not belong to the runtime graph by default.
- JDK: toolchain of the build environment and runtime depending on deployment architecture; the JDK compiler should not be treated as a regular application library.

This classification prevents mistakes such as packaging JUnit into production, missing a driver at runtime, or upgrading a build plugin while mistakenly thinking an application dependency was upgraded too.

## 6. How Dependencies Are Declared in Maven

Maven uses the `dependencies` section in the POM to declare project dependencies. For example:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.4.0</version>
  </dependency>

  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.0</version>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

In this example:

- Starter web is a dependency declared directly by the project.
- JUnit is a direct dependency, but used only for tests.
- Libraries pulled in by starter web are transitive dependencies if the project does not declare them directly.

Versions in the example are only for illustrating structure. Real projects should choose versions matching their BOM, framework, JDK, and team update policies.

### 6.1. Scopes in Maven

Scope determines which phases a dependency is used in and whether it is propagated to dependent projects.

| Scope | Compile | Runtime | Test | Notes |
|---|---:|---:|---:|---|
| compile | Yes | Yes | Yes | Default; usually propagated along the dependency graph |
| provided | Yes | Not on standard runtime classpath | Yes | Expected to be supplied by the runtime environment |
| runtime | Not required for compiling main sources | Yes | Yes | E.g. drivers only needed at runtime |
| test | No | No | Yes | Used solely for testing |
| system | Yes | Not on standard runtime classpath | Yes | Similar to provided, but takes a JAR from a local path; not transitive, hard to reproduce, and should be avoided |

Scope does not replace the direct/transitive relationship. A dependency declared directly with `test` scope is still a direct dependency. A `compile` dependency pulled in by a starter can still be a transitive dependency.

### 6.2. Plugins in Maven Are Declared Separately

Plugins typically reside in the `build/plugins` section:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>21</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Maven Compiler Plugin controls compilation. It is not a library that application code imports to handle requests. A plugin can have its own dependencies and runs within the Maven process.

Do not place a plugin in the `dependencies` section just because it is needed to build. Likewise, do not declare a runtime library in the plugin section simply because the build tool can download it.

## 7. How Dependencies Are Declared in Gradle

Gradle uses configurations to determine at which stage a dependency is needed. With the Java plugin, common configurations include:

| Configuration | Meaning |
|---|---|
| implementation | Dependency used to compile and internally implement the module |
| api | Dependency that is part of the public API exposed to consumers |
| compileOnly | Needed at compile time but excluded from the standard runtime classpath |
| runtimeOnly | Needed only at runtime |
| testImplementation | Used to compile and run tests |
| testRuntimeOnly | Needed only when running tests |
| annotationProcessor | Used during annotation processing and code generation |

Example:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.4.0")
    runtimeOnly("org.postgresql:postgresql:42.7.4")

    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}

tasks.test {
    useJUnitPlatform()
}
~~~

In this example:

- Starter web is a direct dependency of the application.
- PostgreSQL driver is declared directly, but is only needed at runtime.
- JUnit is declared directly for tests.
- Lombok annotation processor is used during the build to process annotations.

Lombok may also need a corresponding `compileOnly` dependency so the IDE and compiler understand annotations in source code. This is an example showing how one library can participate in multiple configurations depending on its role.

### 7.1. Gradle Plugins Are a Different Configuration Layer

Gradle plugins can be declared in the `plugins` block:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.4.0"
    id("io.spring.dependency-management") version "1.1.7"
}
~~~

Plugins extend build capabilities, add tasks, or apply configuration. A plugin may download its own dependencies to operate. Those dependencies belong to build logic and are not automatically runtime dependencies of the application.

For complex build logic, Gradle can also use `buildSrc` or included builds to separate shared logic. These parts must be versioned and security-checked just like the project's build code.

## 8. Why Inspect the Actual Dependency Graph?

Configuration files only show directly declared dependencies and part of the version management rules. They do not always show the complete final set of dependencies the application uses.

A resolver may:

- Select a version via mediation or conflict resolution rules.
- Remove a dependency via an exclusion.
- Apply dependency constraints or a BOM.
- Choose a variant matching attributes or a platform.
- Apply scope/configuration and dependency substitution.
- Receive dependencies from plugins or custom build logic.

Therefore, when investigating, inspect the result after the build tool finishes resolution.

### 8.1. Maven

Useful commands:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=org.example:library-name
mvn help:effective-pom
~~~

- `dependency:tree` displays the project's dependency tree.
- `verbose` shows extra information about omitted or conflicting dependencies depending on the plugin version.
- `includes` helps focus on a specific `groupId`/`artifactId`.
- `effective-pom` displays the POM after parent inheritance, profiles, and configuration have been applied.

Maven uses dependency mediation to decide versions in the graph. When multiple paths reach the same artifact, dependency depth and declaration order can affect which version is chosen. DependencyManagement and BOMs help manage versions consistently, though they do not mean every managed dependency is added to the classpath.

### 8.2. Gradle

Commonly used commands:

~~~bash
./gradlew dependencies
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

- `dependencies` shows the graph by project or configuration.
- `dependencyInsight` explains why a dependency appears and which rules led to the chosen version.
- Selecting the right configuration avoids confusion between compile, runtime, and test.

Gradle has its own conflict resolution rules and supports constraints, platforms, version catalogs, dependency locking, and verification. Do not infer Gradle results using Maven rules.

### 8.3. Other Ecosystems

Other ecosystems also have tools to inspect dependency graphs:

~~~bash
npm ls --all
go mod graph
pipdeptree
~~~

Each ecosystem has its own way of declaring direct dependencies, resolving transitive ones, locking versions, and handling scopes. Read the documentation for the tool you use instead of blindly applying Maven or Gradle rules to npm, Go, or Python.

## 9. Version Conflicts and How to Handle Them

A common conflict occurs when two direct dependencies require different versions of the same transitive library.

For example:

~~~text
Application
├── A 2.x
│   └── C 1.x
└── B 4.x
    └── C 2.x
~~~

The resolver must choose a version of C or fail with an error depending on the ecosystem and policy. Even if a version is selected and the build succeeds, the application may still encounter runtime errors due to incompatible APIs or behavior.

For example, Maven typically uses the nearest definition rule: the path closer in depth to the project takes precedence; if depths are equal, declaration order can decide. Gradle by default tends to pick the higher version when resolving version conflicts, though constraints, platforms, rich version constraints, or resolution rules can change the outcome. Always check the report of the actual resolver rather than applying a single universal rule to every build tool.

When resolving conflicts, follow this sequence:

1. Identify which dependencies bring each version into the graph.
2. Identify which version is actually selected in the failing configuration.
3. Read the compatibility matrix or release notes of A, B, and C.
4. Prefer upgrading direct dependencies so branches become compatible with one another.
5. Use a BOM, platform, or dependency constraint to manage versions consistently when appropriate.
6. Only override a transitive dependency after verifying compatibility and adding tests.
7. Run tests on the exact runtime classpath and verify the final artifact.

Do not override a transitive library just to make a scan report warning disappear. A security patch may be necessary, but you must verify API compatibility, test behavior, and document the reason for choosing the version.

### 9.1. Exclusion Is Not the Default Fix

Maven and Gradle allow excluding a transitive dependency. Exclusions are useful when:

- The dependency is unused in the application.
- A directly managed replacement exists.
- An incompatible component needs to be removed intentionally.

However, removing a dependency can cause missing classes or services expected by other libraries. Only use an exclusion after understanding the dependency path and testing the affected flows.

## 10. Dependency Management, BOM, Constraints, and Lockfiles

Several mechanisms help keep versions consistent, but they solve different problems.

**Dependency management or BOM:** centrally specifies versions for a group of compatible libraries. Maven has `dependencyManagement` and BOM imports; Gradle has platforms or version catalogs combined with constraints. BOMs reduce scattered version declarations, though they do not necessarily lock the entire graph identically for every build.

**Dependency constraints:** express desired versions, bounds, or version selection rules. They are useful when multiple modules need to share a common library.

**Lockfile / dependency locking:** records resolved versions so subsequent builds can reproduce the same result. Gradle supports dependency locking. Ecosystems like npm and Go have their own lock/sum files. Maven typically uses BOMs, `dependencyManagement`, and supplementary mechanisms; do not assume every Maven project has a standard lockfile generated automatically.

**Checksum and verification metadata:** help verify that downloaded artifact contents match trusted values. Gradle dependency verification can check checksums or signatures per configuration. Other ecosystems have corresponding checksum mechanisms or checksum databases.

Understand accurately:

- BOMs help manage versions across a set of libraries.
- Locking helps pin resolution results.
- Checksums/signatures help verify downloaded contents.
- SBOMs describe the components contained in an artifact.
- Provenance records which source and process produced an artifact.

No single mechanism completely replaces the others.

## 11. Security of Direct and Transitive Dependencies

A vulnerability in a transitive dependency can affect an application just like a vulnerability in a direct dependency. Therefore, security checks must examine the resolved graph and the final artifact.

Common risks:

- Dependencies with publicly disclosed vulnerabilities.
- Packages impersonating real package names (typosquatting).
- Dependency confusion due to ambiguous repository configuration.
- Artifacts being replaced or downloaded from untrusted sources.
- Malicious build plugins executing code during CI.
- Outdated versions that are no longer maintained.
- Build scripts or plugins having overly broad access to secrets.

A baseline management process should include:

1. Specify trusted repositories with clear precedence order.
2. Restrict arbitrary repository declarations per module if the organization has a centralized policy.
3. Monitor direct and transitive dependencies with appropriate tools.
4. Evaluate plugins, build logic, and toolchains as well.
5. Use checksums or signatures where the ecosystem supports them.
6. Record SBOM and provenance according to product requirements.
7. Schedule dependency updates and run tests after upgrading.
8. Limit secrets and permissions granted to CI jobs responsible for resolving or executing builds.

Do not scan only runtime libraries while ignoring build plugins. Plugins running in CI can execute code with the runner's permissions, read the workspace, or access credentials granted to the job.

## 12. Build Tools and Toolchains Also Need Version Management

Build results do not depend solely on application libraries. They also depend on:

- Maven or Gradle version.
- JDK and compiler version.
- Plugin versions.
- Runner OS and architecture.
- Environment variables and build configuration.
- Repositories and dependency resolvers.
- External code generation or packaging tools.

If a developer's machine uses JDK 21 while CI uses JDK 17, the build may yield different results or fail. If a plugin version changes unexpectedly, tasks or artifacts may also change.

Practical measures:

- Use Maven Wrapper or Gradle Wrapper to pin the build tool version.
- Declare a Java toolchain to specify the required JDK.
- Pin versions of critical plugins.
- Lock dependencies according to the ecosystem's capabilities.
- Record runner versions, toolchains, and build parameters.
- Use container build images with explicit versions when appropriate.
- Avoid downloading and executing unverified build scripts from arbitrary sources.

Wrappers standardize the build tool, but do not automatically guarantee that every dependency, plugin, or JDK is immutable. Manage each layer individually.

## 13. Dependency Caching Does Not Replace Dependency Management

Caching in CI/CD typically stores downloaded files or build outputs to reduce execution time. For example, a Maven local repository, Gradle dependency cache, or package manager cache can be reused across runs.

Caching is a performance optimization, not a source of truth for dependency versions.

A good cache key typically ties to:

- Runner OS or architecture when cached contents depend on them.
- JDK and build tool versions.
- Dependency declaration files or lockfiles.
- Repository configuration and parameters affecting resolution.
- Cache schema version if storage layout changes.

If a cache key is too broad, the pipeline may reuse inappropriate data. If too narrow, the cache provides almost no benefit.

Keep in mind:

- Do not use caches to replace lockfiles or version pinning.
- Do not treat a cache as a release artifact repository.
- Do not share writable caches between jobs or branches at different trust levels if cache poisoning is a risk.
- Maintain a strategy to refresh or evict caches when dependencies, toolchains, or configurations change.
- Builds must still verify dependencies according to policy even when data comes from cache.

Caches can contain files downloaded from repositories and scripts executed during builds. Hence, cache read and write permissions are also part of the software supply chain.

## 14. Dependency Management Workflow in CI/CD

A reference workflow for a Java project:

~~~mermaid
flowchart TD
    A["Change POM / Gradle build"] --> B["Review direct dependency declarations"]
    B --> C["Resolve dependency graph"]
    C --> D["Check versions and locks/constraints"]
    D --> E["Dependency vulnerability scan"]
    E --> F{"Policy passed?"}
    F -- "No" --> X["Block build or require waiver"]
    F -- "Yes" --> G["Compile and test"]
    G --> H["Package artifact"]
    H --> I["Generate SBOM / provenance if needed"]
    I --> J["Publish immutable artifact"]
~~~

A pipeline can divide work into the following steps:

| Step | Action | Evidence |
|---|---|---|
| Review | Check new direct dependencies, scope changes, and sources | Pull request review |
| Resolve | Resolve the full graph under deterministic configuration | Dependency tree/report |
| Verify | Verify checksums, lock state, or repository policy | Verification result |
| Scan | Scan direct and transitive dependencies | Vulnerability report |
| Build | Compile, test, and package using the specified toolchain | Test/build result |
| Inventory | Generate an SBOM or component list when needed | SBOM attached to artifact |
| Publish | Store artifact with digest and metadata | Artifact ID, digest, provenance |

Not every project must generate an SBOM or sign artifacts to the same degree. Choose based on supply chain requirements, sensitivity level, and release policy. Yet every project must know which dependencies were resolved and which build tool produced the artifact.

## 15. Signs That Dependencies Are Poorly Managed

| Sign | Risk | How to Investigate |
|---|---|---|
| Code imports an undeclared library | Implicit reliance on a transitive dependency | Find used APIs and declare directly |
| Test-only dependency appears at runtime | Bloated artifact, larger attack surface | Inspect scope/configuration and package |
| Unknown origin of a transitive library | Difficult to assess vulnerabilities and compatibility | Inspect dependency tree or insight |
| Multiple versions appear in the graph | Can cause conflicts or bloat | Check paths and resolution rules |
| Local build passes while CI fails | Mismatched toolchain, cache, or repository | Compare wrapper, JDK, config, and dependency graph |
| Intermittent build failures | Dynamic versions or mutable repositories | Check dynamic versions, locks, and metadata |
| Build plugins use unpinned versions | Build outputs can drift | Declare and control plugin versions |
| Scanning only direct dependencies | Misses vulnerabilities in the actual graph | Scan resolved graph and artifact |
| Cache shared across untrusted branches | Risk of cache poisoning or leakage | Partition cache by trust level and write permissions |
| Upgrading dependencies without testing | Compile or runtime compatibility errors | Run scoped tests and inspect the artifact |

## 16. Practical Example: Investigating a Transitive Dependency

Suppose a Java application declares a web framework and builds successfully. A security report indicates a vulnerable version of a JSON library. In the POM, that library is not declared directly.

How to investigate:

1. Run dependency tree to trace the path from the application to the JSON library.
2. Identify which direct dependency pulls that library in.
3. Check the scope to see whether it appears in compile, runtime, or test.
4. Check which version the resolver selected and why.
5. Check whether the framework or BOM has a compatible update.
6. If an override is needed, intentionally declare the version in `dependencyManagement` or the equivalent mechanism.
7. Run unit tests, integration tests, and inspect the runtime package.
8. Re-run the scan and save evidence for the new artifact.

Do not add the JSON dependency directly just to force the resolver's version choice without understanding the framework's compatibility requirements. If a temporary override is required to mitigate a vulnerability, document the reason, impact scope, tests run, and condition for removing the override once upstream updates.

## 17. Checklist Before Adding or Upgrading a Dependency

- [ ] Source code or build logic genuinely needs this dependency.
- [ ] Confirmed whether it is a direct dependency or only appears transitively.
- [ ] Selected the appropriate scope/configuration.
- [ ] Checked license and repository source against policy.
- [ ] Version is compatible with the framework, JDK, and related dependencies.
- [ ] Inspected the dependency graph and version conflicts.
- [ ] Appropriate lock, constraint, or version management mechanism is in place.
- [ ] Checked vulnerabilities for both direct and transitive dependencies.
- [ ] Related plugins and build logic have also been evaluated.
- [ ] Ran tests on the corresponding classpath/configuration.
- [ ] Final artifact contains no unexpected test/build components.
- [ ] Cache is not used as the source of truth for dependencies.
- [ ] Artifact can be traced back to commit, toolchain, and dependency graph.

## 18. Self-Assessment Exercise

A Java service has the following setup:

~~~text
application
├── framework-web
│   ├── json-core
│   └── logging-api
├── database-driver
└── test-framework (test scope)
~~~

The team discovers:

- Application code calls `json-core` APIs directly, but only declares `framework-web`.
- A scan report flags `logging-api` as vulnerable.
- A developer added the compiler plugin to `dependencies` instead of `build` plugins.
- Local machines use JDK 21 while CI runners use JDK 17.
- CI builds sometimes use an old cache and produce different results from a clean build.

Analyze:

1. Which components are direct dependencies, and which are transitive dependencies?
2. Why should `json-core` be declared directly if the code uses its API?
3. How should `logging-api` be investigated if it is a transitive dependency?
4. Why does the compiler plugin belong in the build configuration?
5. How should the scope/configuration of the test framework be separated from runtime dependencies?
6. By what mechanisms should the JDK and build tool be standardized?
7. What factors should the cache key reflect?
8. What evidence should be saved to trace the artifact and dependency graph?

A solid answer should classify correctly across all three axes: direct/transitive relationship, usage scope, and execution location. Only then should it propose appropriate configuration changes and tests.

## Conclusion

Direct dependencies represent the components a project actively chooses to use; transitive dependencies are those pulled in through other dependencies; build tools orchestrate turning source code into artifacts. These three concepts are related, but cannot substitute for one another.

Good CI/CD management requires controlling the resolved dependency graph, scopes/configurations, plugin versions, and toolchains. When teams understand which components run inside the application, which only serve the build, and which are pulled in indirectly, they can reduce implicit dependencies, detect security risks, and produce stable, traceable artifacts.
