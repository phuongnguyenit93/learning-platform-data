# Preview Features and Version-Matching Requirements at Compile and Runtime

Within the **Cross-Version Compilation** chapter of **Java Advance Compatibility Migration**, preview features are part of the process for evaluating new Java features before they become stable standards. When using a preview feature, a team must simultaneously manage the JDK version used for compilation, the compiler preview flag, the JVM version running the application, and the runtime preview flag.

A key detail to remember is that a preview feature is tied to a specific Java feature release. Bytecode depending on a release's preview feature is accepted only by a matching-release JVM when preview is enabled. Consequently, adding the flag only to the compile command is insufficient; every participating execution process must also be configured properly.

This lesson explains the preview feature lifecycle, how the compiler and JVM enforce them, version-matching requirements, Gradle/Maven/CI configuration, common pitfalls, and how to plan when a feature changes or becomes finalized.

## 1. What Is a Preview Feature?

A preview feature is a Java feature implemented for community and developer experimentation before being finalized into standard status. Depending on the release, previews can apply to:

- The Java language, such as new syntax or language rules.
- The JVM or class-file format, when execution mechanisms must change.
- Java SE APIs, when a new API is shipped in preview status.

A preview feature has a complete enough specification and implementation to test, yet may still be adjusted or removed in the next release. Teams adopting it must accept the possibility of revising source code, configuration, and deployment practices when upgrading the JDK.

Preview features do not carry the same stability guarantee as standardized Java features. A program compiling and running cleanly with preview should not be taken as proof that the exact source code will keep working unmodified in every subsequent Java release.

### 1.1. Typical Lifecycle

~~~text
Proposal and design
        |
        v
First preview in a JDK release
        |
        v
Collect feedback and refine
        |
        +--------------------+
        |                    |
        v                    v
   Next preview     Major change or removal
        |
        v
Promoted to final status
        |
        v
API/language stabilized under Java compatibility policy
~~~

Not every feature completes this entire chain. A feature may appear in a single preview, go through multiple previews with substantial revisions, become finalized, or be withdrawn.

When preparing a migration, look up the status of the exact feature in the exact JDK release. Never infer its status solely from its name or from a tutorial written for a different release.

### 1.2. Preview Features Differ from Finalized Features

| Characteristic | Preview feature | Finalized feature |
|---|---|---|
| Status | Under evaluation | Standardized in a release |
| How enabled | Typically requires the corresponding preview flag | Used under standard Java configuration |
| Likelihood of change | May change or be removed | Covered by Java compatibility guarantees |
| Bytecode | May be marked as a preview-using class file | Standard class file |
| Runtime | Preview must be enabled and match the release that produced the bytecode | Can run on JVMs compatible with the class file/API |
| Suitability for public libraries | Needs strict consideration due to runtime constraints | Better suited for stable contracts |

A preview feature can be useful for evaluating a design, yet introducing it into a shared library imposes constraints on every consumer. If consumers cannot control their JDK version and JVM startup flags, exposing preview features in a public API can restrict library distribution.

## 2. Preview Flags at Compile Time

Compilers do not permit source code to use preview features by default. With **javac**, pass the option:

~~~bash
--enable-preview
~~~

This option lets the current JDK's compiler accept preview features belonging to that exact release.

It should be combined with **--release** to declare the Java release that source and bytecode target.

Example with JDK 21:

~~~bash
javac --enable-preview --release 21 -d out src/com/example/Main.java
~~~

In this example:

- **--enable-preview** enables preview features of the JDK executing the compiler.
- **--release 21** sets the language level, class-file version, and permitted Java SE APIs to release 21.
- **-d out** specifies the output directory for generated class files.

**Critical condition:** the compiler must be JDK 21 when enabling Java 21 previews. You cannot invoke JDK 22 with **--enable-preview --release 21** to compile a Java 21 preview feature. Preview is enabled for the compiler's own current release, not for an arbitrary older release.

### 2.1. Why Use --release?

You may encounter the source and target options:

~~~bash
javac -source 21 -target 21 ...
~~~

They govern syntax level and bytecode version, yet do not fully constrain the target JDK's API set. When compiling on a newer JDK, source code can inadvertently invoke APIs existing only on that newer JDK even though bytecode targets an older release.

**--release** combines source level, bytecode target, and Java SE API constraints for the chosen release. When preview is needed, use the exact matching JDK release and combine:

~~~bash
javac --enable-preview --release 21 ...
~~~

Do not use **--release** expecting to generate preview bytecode for an older JDK from a newer compiler. A compiler enables preview only for its own release.

### 2.2. Distinguishing Compiler JDK from Target Runtime

A project can involve multiple Java versions across its build lifecycle:

| Component | Role |
|---|---|
| JDK running Gradle/Maven | Launches the build tool |
| Compiler/toolchain JDK | Runs javac to compile sources |
| Release target | Defines API and class-file level |
| Test-execution JDK | Launches test workers or test processes |
| Application-execution JDK | Loads classes and runs the application |

When using a Java 21 preview feature, the compiler must be JDK 21 and the JVM executing preview-dependent classes must also be Java 21 with preview enabled. Gradle running on a different JDK does not automatically ensure compilers and test workers use the right version.

## 3. Preview Flags at Runtime

After compiling cleanly, the JVM must also be permitted to run preview features.

Example:

~~~bash
java --enable-preview -cp out com.example.Main
~~~

The runtime flag serves a separate role from the compiler flag:

| Phase | Flag | Purpose |
|---|---|---|
| Compile | javac with **--enable-preview** | Permits source code to use preview features of the compiler release |
| Run | java with **--enable-preview** | Permits the JVM to execute preview-dependent class files of the current release |

If preview is enabled only at compile time while omitted at runtime, the JVM rejects loading the preview-using class file. A common error is **UnsupportedClassVersionError** accompanied by a message indicating preview features are not enabled.

The runtime flag must be present on the exact JVM process executing the code. Passing the flag to the Gradle daemon or Maven process does not mean child JVMs spawned by test runners, application plugins, or launcher scripts inherit it.

### 3.1. Release-Matching Requirement

Suppose a class uses a Java 21 preview feature:

~~~text
Compiler: JDK 21 + --enable-preview
                 |
                 v
         Java 21 preview class file
                 |
                 v
Runtime: JDK 21 + --enable-preview
                 |
                 v
             Can execute
~~~

Common invalid combinations:

| Compiler creating preview class | Runtime | Outcome |
|---|---|---|
| JDK 21, preview enabled | JDK 21, preview enabled | Matching release; can run if dependencies and environment also align |
| JDK 21, preview enabled | JDK 21, preview disabled | JVM rejects preview-dependent class file |
| JDK 21, preview enabled | JDK 22, preview enabled | Incompatible; release 21 preview class is rejected by JVM 22 |
| JDK 21, preview enabled | JDK 20 | Incompatible class-file/runtime version |
| JDK 22, preview enabled | JDK 22, preview enabled | Matching release if compiled by JDK 22 |
| JDK 22, preview enabled | JDK 21 | Older runtime does not understand release 22 class file |

Having **--enable-preview** on both processes does not make different releases compatible. The flag enables preview only for the currently running JDK; it does not turn a newer JVM into a runtime for an older release's preview class files.

### 3.2. Class-File Version and Special Minor Version

Java class files carry a major version and a minor version. When a class file uses a preview feature, the JVM recognizes it via the special minor version **65535**, paired with the major version of the corresponding release.

For example, a regular Java 21 class file uses major version 65. A Java 21 preview class file carries the matching major version along with the special preview minor version.

This mechanism lets the JVM know the class file depends on preview features. The JVM checks that the release matches and preview is enabled before allowing execution. That is why a preview class file is not an artifact you can freely carry forward to the next JDK feature release.

Do not inspect only the major version when concluding compatibility. When troubleshooting, inspect both the minor version and the JVM error message.

## 4. Hands-On Example with Java 21

The steps below illustrate compiling and running a program using a Java 21 preview feature. The program body is assumed to use syntax or an API belonging to that release's preview; substitute the specific example your team is evaluating.

### Step 1: Confirm the Active JDK

~~~bash
java -version
javac -version
~~~

Both the compiler and runtime chosen for the experiment must be JDK 21. If the build tool uses its own toolchain, confirm the toolchain also points to JDK 21.

### Step 2: Compile with Preview

~~~bash
javac --enable-preview --release 21 -d out src/com/example/Main.java
~~~

If sources use a release 21 preview feature without **--enable-preview**, the compiler reports an error. If the compiler is not JDK 21, the flag-and-release combination may be rejected.

### Step 3: Run with Preview

~~~bash
java --enable-preview -cp out com.example.Main
~~~

The runtime must be JDK 21. When the program starts, the JVM may print a warning noting that the program uses preview features of Java SE 21.

### Step 4: Try Removing the Runtime Flag

~~~bash
java -cp out com.example.Main
~~~

If the class file genuinely depends on a preview feature, the JVM refuses to load or execute the class. This failure demonstrates that the compile flag and runtime flag are two independent requirements.

### Step 5: Try Running on the Next JDK Release

If running the Java 21 preview class with JDK 22, even with **--enable-preview**, the JVM will not support preview class files built for release 21. Recompile the source with JDK 22 after checking whether the feature still exists and how its syntax/API changed.

Do not simply swap the runtime in production to troubleshoot errors. Produce a fresh build matching the target release and run tests on the new artifact.

## 5. Configuration in Gradle

In Gradle, configure both the compiler and every JVM executing the code. Groovy DSL example for Java 21:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.compilerArgs += ['--enable-preview']
}

tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview'
}

tasks.withType(JavaExec).configureEach {
    jvmArgs '--enable-preview'
}
~~~

Meaning:

- The Java toolchain selects JDK 21 for corresponding Java tasks.
- **options.release = 21** sets the target API and class-file level.
- **options.compilerArgs** enables preview during compilation.
- Test tasks pass the flag to the JVM running test workers.
- JavaExec passes the flag to the JVM running the application or main class.

Confirm that your Gradle version supports JDK 21 and verify your active toolchain configuration. If the project defines custom tasks, forked compilers, or separate forked JVMs, configure those tasks as well.

### 5.1. Watch Out for Tests and Custom Tasks

A project may have many kinds of tasks:

- Main source compilation.
- Test source compilation.
- Unit tests.
- Integration tests.
- JavaExec running the application.
- Tasks running migration tools or code generators.
- Tasks spawning child processes.
- Tasks generating smoke tests or compatibility fixtures.

Do not assume configuring one task automatically covers every process. Inspect actual task command lines when needed, especially for test workers and forked processes.

Adding **--enable-preview** only to JavaCompile lets sources compile, yet the test JVM still rejects the class files. Adding it only to Test tasks prevents the compiler from accepting preview syntax.

### 5.2. Toolchains and Executing JVMs

Toolchains select the JDK for tasks, yet verify whether each task type actually uses that launcher. Test tasks and JavaExec generally honor Java toolchain launchers; custom tasks or shell-spawned processes may fall back to environment `JAVA_HOME` or `PATH`.

Verify with:

~~~bash
./gradlew -version
./gradlew compileJava --info
./gradlew test --info
~~~

On Windows, run **gradlew.bat** accordingly. Read logs to identify the actual compiler JDK and executing JVM rather than relying solely on the terminal's `java` version.

## 6. Configuration in Maven

In Maven, configure the compiler plugin and test runners separately. The snippets below show illustrative `pom.xml` fragments; pick plugin versions compatible with your active JDK and Maven.

### 6.1. Compiler

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--enable-preview</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

The compiler process must run on JDK 21 to enable Java 21 previews. **maven.compiler.release** constrains the target API and class-file level.

### 6.2. Unit Tests with Surefire

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--enable-preview</argLine>
    </configuration>
</plugin>
~~~

If running integration tests with Maven Failsafe, configure equivalent JVM arguments for Failsafe. If combining JaCoCo or other agents, merge **argLine** carefully so existing agent arguments are not overwritten.

When tests run in a forked JVM, **argLine** configures that process. If forking is disabled and tests run inside the Maven JVM itself, the flag must be passed to the JVM starting Maven; child-process settings have no effect on the current process.

### 6.3. Checking Maven's JDK

~~~bash
mvn -version
mvn clean test
~~~

**mvn -version** shows the Java runtime running Maven. If the compiler is forked or a separate toolchain is configured, also check the actual compiler JDK. CI must use the exact feature release chosen by the project for preview.

## 7. IDE and CI/CD Configuration

Preview flags must stay synchronized between development environments and pipelines. If an IDE compiles with JDK 21 while a test runner uses another JDK, results can diverge from CI.

### 7.1. IDE

Verify these settings:

- Workspace Project SDK or JDK.
- Module language level.
- Compiler options include **--enable-preview**.
- Run configurations include **--enable-preview**.
- Test run configurations include **--enable-preview**.
- Gradle/Maven JVM and Java toolchain.
- JDK used by application servers or plugins launched from the IDE.

IDEs may offer per-module preview toggles. However, IDE settings apply only locally; encode the requirement in build files and project docs so CI and other machines share the exact setup.

### 7.2. CI Pipeline

Pipelines must pin the JDK feature release and enable preview at both compile and runtime.

~~~text
Select JDK feature release
          |
          v
Confirm compiler and runtime
          |
          v
Compile with --enable-preview
          |
          v
Run unit/integration tests with --enable-preview
          |
          v
Inspect artifact and class files
          |
          v
Run smoke tests on target runtime
          |
          v
Record JDK version, command line, and test report
~~~

Steps should produce evidence:

- Runner JDK version and vendor.
- Gradle/Maven version.
- Actual compiler arguments.
- JVM arguments of test workers and application processes.
- Test results.
- Artifact checksums and build metadata.
- Required JDK feature release for deployment.

If the pipeline splits into multiple jobs or stages, each job may execute on a different runner. Explicitly configure the JDK and flags for every job; never assume compile-job settings carry over to test or deploy jobs automatically.

## 8. Preview Features in Multi-Module Builds and Shared Libraries

One module may use a preview feature while other modules do not. Determine whether the preview dependency crosses module boundaries.

~~~text
application
    |
    +---- core-library
    |         |
    |         +---- uses Java 21 preview API
    |
    +---- adapter
              |
              +---- does not use preview
~~~

If **core-library** contains class files depending on a Java 21 preview, any application loading those classes must run on JDK 21 with preview enabled. The fact that the application module itself writes no preview syntax does not remove the dependency's runtime requirement.

Check:

- Which modules actually use preview features.
- Which modules depend on preview classes at compile or test time.
- Which tasks emit preview class files.
- Which applications load that module.
- Whether any external plugins or consumers receive the artifact.
- Whether the runtime flag is passed to every consuming process.

### 8.1. Propagation Limits of Configuration

Compiler flags belong to compile tasks. Runtime flags belong to JVM processes. They do not automatically turn into transitive metadata propagating across the dependency graph.

A JAR can package cleanly while consumers remain unaware that they need to:

- Use the exact JDK feature release.
- Enable preview at runtime.
- Align versions of related dependencies.

Therefore, when publishing an artifact with a preview dependency, explicitly document the JDK requirement and runtime flag. If consumers cannot meet those requirements, consider isolating the experimental part into an optional module or keeping preview code out of public APIs.

### 8.2. Limiting Previews in Public Libraries

A public library typically supports many applications on varying upgrade schedules. When public APIs or implementation classes depend on a preview feature, consumers must satisfy both the exact release and runtime flag.

Risks include:

- Consumers running other JDKs cannot load preview classes.
- Consumers cannot control JVM startup arguments.
- Feature changes in the next release break source or API compatibility.
- Old artifacts must be recompiled to run on the newer release.
- One preview module raises the runtime requirements for the entire application.

If the goal is experimentation, isolate preview code in a dedicated module, limit it to test environments, or publish experimental artifacts with explicit support boundaries. If production use is mandatory, document the release lock, runtime flag, support horizon, and plan for replacing or promoting to final.

## 9. Preview Features and Incubator Modules Are Not the Same

Java provides distinct experimentation mechanisms. Do not confuse preview features with incubator modules.

| Characteristic | Preview feature | Incubator module |
|---|---|---|
| Purpose | Evaluate language, JVM, or API features per release | Evaluate APIs/modules prior to stabilization |
| Common activation mechanism | **--enable-preview** | **--add-modules** plus potentially related module options |
| Release coupling | Preview class files depend on the release that built them | Depends on specific JDK module state |
| Scope | Can affect syntax, class files, or APIs | Typically APIs delivered via an incubator module |
| How verified | Matching preview flags and releases for compiler/runtime | Check module existence, resolution, and module path config |

Example using an incubator module:

~~~bash
java --add-modules jdk.incubator.vector -cp out com.example.Main
~~~

This illustrates adding a module to the module graph. It does not replace **--enable-preview**, nor does every incubator module use identical flags.

A project may need both mechanisms if simultaneously using a preview feature and an incubator API. Read the documentation for your exact JDK release and each module to determine required flags.

## 10. Common Errors and How to Investigate Them

### 10.1. Compiler Reports Preview Features Are Not Enabled

Common causes:

- Missing **--enable-preview** in compiler arguments.
- One module or source set missing the configuration.
- Actual compiler differs from the expected JDK.
- Code generation or test compilation tasks use different compiler options.

How to verify:

1. Inspect the `javac` command line.
2. Confirm the `javac` version.
3. Inspect compiler tasks for each module.
4. Inspect test source sets and custom tasks.

### 10.2. JVM Reports Preview Features Are Not Enabled

Common causes:

- Enabled preview at compile time, omitted at runtime.
- Test worker or child process did not receive the JVM argument.
- IDE run configuration lacks the flag.
- Container entrypoint or service script omits the flag.

The fix is adding **--enable-preview** to the exact JVM process executing the class, then re-running the exact same artifact to confirm.

### 10.3. JVM Reports Incompatible Class-File Version

Common causes:

- Runtime is older than the release used for compilation.
- Preview class compiled on one release is executed on another release.
- A transitive dependency contains class files newer than the runtime supports.
- CI and production use different JDKs.

Inspect **java -version**, **javap -verbose**, and the dependencies actually loaded. Do not check only the JDK in the build container; verify both the runtime image and production processes.

### 10.4. Using a New Compiler with an Old Release

For example, running JDK 22 while requesting:

~~~bash
javac --enable-preview --release 21 ...
~~~

The compiler does not enable Java 21 preview features this way. **--enable-preview** applies to the compiler's current release. Select the JDK 21 toolchain if Java 21 previews are needed.

### 10.5. Only Some Tests Fail

If unit tests pass while integration tests fail, integration tests may run on a different JVM. Places to check:

- Surefire and Failsafe have differing configurations.
- Test workers fork separately.
- Gradle defines multiple Test-type tasks.
- Tests launch the app via JavaExec or shell scripts.
- Docker Compose or Testcontainers uses a different JRE image.
- Tests run on a CI runner different from the compile stage.

Identify which process actually loads preview classes and pass the flag to that process.

### 10.6. Source Runs on This Release Yet Fails to Compile on the Next Release

Preview features may change syntax, types, APIs, or language rules. When switching JDKs, consult the feature's JEP and migration notes, update sources, and recompile/retest.

Do not carry old preview class files forward to deploy on a new release. Build a fresh artifact from updated sources using the target release's compiler.

## 11. Tracking Feature Status Across Releases

For each preview feature in use, maintain an inventory entry:

| Field | Content |
|---|---|
| Feature name | Name of the feature |
| JEP / reference | JEP number or official documentation |
| First preview release | Initial preview release |
| Current status | Preview, second preview, final, or withdrawn |
| Source usage | Modules, packages, and files using it |
| Runtime dependency | Which classes require preview upon loading |
| Build flag | Compiler flag and release |
| Runtime flag | Required JVM argument |
| Consumer | Dependent applications, plugins, or modules |
| Owner | Responsible team |
| Next action | Re-evaluate, update source, remove, or finalize |

On each JDK upgrade:

1. Look up the feature's status in the target release.
2. Determine whether it remains in preview, is finalized, or was withdrawn.
3. Read changes to syntax, APIs, class files, and runtime behavior.
4. Update compiler and runtime configuration.
5. Recompile all dependent modules.
6. Execute tests on the target JDK.
7. Verify converted consumers and artifacts.
8. Update the inventory and documentation.

If the feature becomes finalized, code usually needs to be recompiled for the new release. Once no preview dependencies remain, remove preview flags and confirm builds and runs succeed without them.

If the feature is withdrawn, the team must redesign the code using it. Never assume a withdrawn feature will always have a one-to-one replacement API.

## 12. Migration Strategy When Previews Finalize or Change

### 12.1. When a Feature Becomes Finalized

For example, a feature previewed in release N is standardized in release N+1.

Workflow:

1. Read release N+1 official documentation.
2. Check whether final syntax and APIs changed relative to preview N.
3. Switch the compiler toolchain to JDK N+1.
4. Update sources to match the final specification.
5. Remove **--enable-preview** if no other preview features remain.
6. Rebuild all modules and artifacts.
7. Run tests on JDK N+1.
8. Run consumer tests and verify runtime behavior.
9. Release new artifacts, documenting the upgrade requirement clearly.

Do not keep preview N artifacts and merely swap the JVM to N+1. Artifacts must be recompiled with the new release's compiler.

### 12.2. When a Feature Remains in Preview

If a feature is previewed again in release N+1, do not assume syntax and APIs remained unchanged. Compare preview iterations, update code for the new release, enable preview flags at compile and runtime, and test all consumers.

Preview N class files are not deployable artifacts for N+1. Each preview release requires its own build and matching-release runtime.

### 12.3. When a Feature Is Withdrawn

If a feature is withdrawn or no longer present:

- Identify dependent modules and APIs.
- Read the published rationale and alternatives.
- Identify replacement APIs or designs.
- Evaluate impact on public APIs and consumers.
- Refactor on a migration branch.
- Add regression tests for the replacement behavior.
- Release new artifacts after verification.

If no replacement exists yet, explicitly document the decision to defer the upgrade or remove preview usage. Never delete code without confirming which business behaviors must be preserved.

## 13. Preview Features in Production: Considerations and Controls

Preview features primarily serve feedback and evaluation prior to standardization. Organizations may occasionally choose to test one in a production-like environment or controlled workload, provided they accept strict version lock-in and change risk.

Before adopting, determine:

- Does the feature deliver genuinely essential value?
- Can the JDK feature release stay pinned throughout the support period?
- Can every runtime instance receive **--enable-preview**?
- Are there external consumers or independent plugins?
- Is there a path to roll back to an artifact without previews?
- Does the feature leak preview APIs through public contracts?
- Are tests, logging, monitoring, and owners ready when the feature changes?

If deployed to production, document the release lock, time limit, scope, owner, rollback plan, and roadmap to transition to the finalized feature or a stable alternative. For public libraries, avoid forcing consumers into preview features when you cannot control their runtimes.

## 14. Checklist Before Enabling Preview Features

### Feature Identification

- [ ] Feature name and JEP/documentation for the exact release identified.
- [ ] Preview status confirmed in the target JDK.
- [ ] Understood whether the feature applies to language, JVM, or API.
- [ ] Changes across preview iterations checked.

### Compiler

- [ ] Compiler runs on the exact JDK feature release.
- [ ] **--enable-preview** passed to compiler.
- [ ] **--release** set to the matching release where applicable.
- [ ] All source sets and modules using the feature receive configuration.
- [ ] Build logs record the actual compiler/toolchain.

### Runtime

- [ ] Runtime matches the preview class's JDK feature release.
- [ ] JVM processes receive **--enable-preview**.
- [ ] Test workers, integration tests, and child processes receive the flag.
- [ ] Containers, service scripts, and production launchers pass the flag.
- [ ] No old preview class files run on a different release.

### Consumers and Release

- [ ] Dependent modules, plugins, and consumers inventoried.
- [ ] Impact on public APIs evaluated.
- [ ] Artifacts and checksums saved per preview release.
- [ ] JDK/runtime requirements documented for consumers.
- [ ] Plan in place for when the feature finalizes, changes, or is withdrawn.
- [ ] Verified fallback and rollback artifacts exist.

### CI/CD

- [ ] CI uses the exact JDK for compiling and testing.
- [ ] Compiler and test JVMs receive the exact flags.
- [ ] Smoke tests execute on the target runtime.
- [ ] Reports store JDK, command lines, and artifact checksums.
- [ ] Pipeline checks detect JDK mismatches across stages.

Preview features let teams try upcoming Java capabilities before standardization. In return, preview class files are tightly bound to the release that created them and must execute on a JVM of that exact release with preview enabled. Therefore, treat compiler version, runtime version, build tasks, and consumers as one unified contract. When features change or finalize, recompile sources for the new release, verify behavior, and publish fresh artifacts rather than reusing old preview bytecode.
