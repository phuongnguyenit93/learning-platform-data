# Module Patching and Production Risks

## 1. What Is Module Patching in JPMS?

The Java Platform Module System (JPMS) organizes classes and resources into named modules. When a named module is resolved and loaded, its classes belong to the corresponding module and class loader. In some situations where you need to replace or add classes/resources of a module without modifying the original JAR directly, Java provides the **--patch-module** option.

`--patch-module` allows adding one or more directories/JARs to the contents of an existing module. When a class or resource with the same path appears in both the patch path and the original module, the content on the patch path is found first. Therefore, a patch can override a class/resource with the same name or add new classes/resources into a module.

General syntax:

~~~text
--patch-module module=patch-path
~~~

Where:

- `module` is the name of the named module to patch, e.g., `com.acme.core` or `java.base`.
- `patch-path` is one or more directories/JARs containing classes and resources to add.
- Multiple entries are joined using the OS path separator: `:` on Linux/macOS and `;` on Windows.

Example:

~~~bash
java --patch-module=com.acme.core=patches/com.acme.core ...
~~~

This option can appear in the compile environment or when launching the JVM. The two places serve different roles and must be configured consistently.

## 2. How Does Patching a Module Differ from Replacing a JAR or Editing a Module Descriptor?

Module patching affects the class/resource contents loaded for a module during that JVM run. It does not modify the original JAR on disk, does not create a new release, and does not replace the module descriptor.

Several distinctions to make:

- **Replacing the JAR:** replaces the original artifact with another artifact on the module path. This is usually the official way to release a bugfix version.
- **--patch-module:** keeps the original artifact on the module path while adding patch content that is searched before the module's own content.
- **--add-exports:** adds access to public types of a package for target modules.
- **--add-opens:** opens a package for deep reflection at runtime.
- **Java agent/instrumentation:** has a separate mechanism to transform or redefine classes in a running JVM, within the limits of the Instrumentation API.

`--patch-module` is not a mechanism to hot-patch an already running process. The patch path is applied when the JVM starts up and modules are set up; modifying files on disk after a class has been loaded does not cause the in-memory class to change automatically.

The module descriptor remains the original module's descriptor. Patching does not automatically add `requires`, `exports`, `opens`, `uses`, or `provides` directives. If a patch adds a new package, that package becomes part of the module's contents when loaded, yet it does not automatically become exported to other modules. If module access rights are needed, they must be handled separately via an appropriate descriptor or corresponding access options.

## 3. When Should Module Patching Be Used?

Some scenarios to consider:

1. **Module testing:** adding test classes to the exact module under test so tests can access package-private APIs within the same module boundary.
2. **Testing JDK or frameworks:** replacing a class/resource in a module to reproduce a bug, inspect behavior, or verify a fix before an official artifact is available.
3. **Temporary compatibility:** applying a small fix in a controlled environment when a new dependency cannot be released immediately.
4. **Adding resources:** supplying resources looked up by a module via module/class loader, such as test data or configuration for a specific run.
5. **Incident investigation:** trying an alternative implementation to determine whether a bug lies within a specific class.

For production, patching should only be an exception with a clear owner, deadline, and removal plan. Once a fix is confirmed necessary long-term, update the source and re-release the official module/JAR. Keeping a separate patch outside the artifact increases the number of components to control and can make the runtime environment non-reproducible from normal dependency declarations.

## 4. Patching Classes and Resources

Suppose module `com.acme.core` contains:

~~~text
com.acme.core.jar
  module-info.class
  com/acme/core/Parser.class
  com/acme/core/internal/TokenReader.class
  com/acme/core/messages.properties
~~~

We want to replace `Parser.class` and the `messages.properties` resource. The patch directory has a matching structure:

~~~text
patches/com.acme.core/
  com/acme/core/Parser.class
  com/acme/core/messages.properties
~~~

When launching:

~~~bash
java \
  --patch-module=com.acme.core=patches/com.acme.core \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

The JVM looks up classes/resources on the patch path before the original module's contents. If the patch contains `com/acme/core/Parser.class`, that class is used instead of the class of the same name in the original module. If the patch contains a new resource not present in the original module, the module can access that resource via the appropriate resource lookup mechanism.

Preserve exact package paths and resource names. Java class names are case-sensitive on many filesystems. The patch directory must be the root of the package tree; do not add an arbitrary extra folder level that causes entry paths to no longer match class/resource names.

A patch JAR can also be used:

~~~bash
java \
  --patch-module=com.acme.core=patches/core-fix.jar \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

When there are multiple patch entries, join them with the OS path separator. Keep the entry list short and clearly ordered so operators can determine the exact source of loaded classes.

## 5. Using `--patch-module` When Compiling

The compiler also supports `--patch-module`. This is useful when compiling sources that need to be treated as part of an existing module, such as test code needing access to package-private members or replacement source for a class in the module.

For example, the compiled main module is in `mods`, while patch source is in `src/patches/com.acme.core`:

~~~bash
mkdir -p build/patches/com.acme.core

javac \
  --module-path mods \
  --patch-module com.acme.core=src/patches/com.acme.core \
  -d build/patches/com.acme.core \
  src/patches/com.acme.core/com/acme/core/Parser.java
~~~

The resulting compiled class resides in the patch output. When running the application, pass that exact output to the JVM:

~~~bash
java \
  --patch-module=com.acme.core=build/patches/com.acme.core \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

If you only use a patch at compile time without the corresponding patch at runtime, the compiler and JVM may see two different implementations. Conversely, patching only at runtime without compiling/testing against the corresponding source and API can cause linkage errors or unexpected behavior.

When patching a JDK module or running tests needing access to internal packages, additional access options may be required depending on the compilation target. `--patch-module` does not automatically export packages or open packages for reflection.

## 6. Module Patching in Unit Tests

A modular application often wants test classes to reside in the same module as the code under test. This allows tests to call package-private methods or access package-private types without turning implementations into public APIs solely for testing.

Example source tree:

~~~text
src/main/java/
  module-info.java
  com/acme/core/Parser.java

src/test/java/
  com/acme/core/ParserTest.java
~~~

If tests are compiled as a patch of module `com.acme.core`, they can participate in the same module boundary as the main code. Illustrative command:

~~~bash
javac \
  --module-path mods:test-libs \
  --patch-module com.acme.core=src/test/java \
  -d build/test-patches/com.acme.core \
  src/test/java/com/acme/core/ParserTest.java
~~~

Actual test configuration also depends on the test framework, the module containing JUnit, and how the build tool constructs the test runtime. Additional readability or access options may be needed so the patched module can read the test framework module. Do not add broad `opens` or `--add-opens` if tests only need to call package-private APIs within the same module.

When running tests, pass the patch output to the JVM:

~~~bash
java \
  --patch-module=com.acme.core=build/test-patches/com.acme.core \
  --module-path mods:test-libs \
  ...
~~~

With Gradle or Maven, inspect the compiler command line and test JVM that the build tool actually generates. Do not assume a compiler argument configuration is automatically forwarded to the test runtime.

## 7. Patching JDK Modules

You may encounter examples of patching platform modules, such as `java.base`, during JDK testing or when investigating a bug dependent on runtime implementation details.

Formal example:

~~~bash
java \
  --patch-module=java.base=patches/java.base \
  -jar diagnostic-tool.jar
~~~

This carries higher risk than patching an application module:

- Platform modules are shared by many JVM components and libraries.
- A replacement class can affect multiple subsystems not directly related to the application being investigated.
- Implementation details can change across JDK vendors, patch updates, and Java versions.
- An incompatible patched class can cause the JVM or platform tools to fail before the application starts.
- Patching can alter behavior expected by monitoring tools or security checks.

Test only against a specific JDK, in an isolated and reproducible environment. Do not take a patch built for one JDK release and deploy it onto another update or vendor without rebuilding and retesting.

## 8. Production Risks When Patching Modules

### 8.1. Overriding Implementations Outside the Release Process

Patching a class with the same name can replace the implementation in the original module. Operators see the original JAR/version looking correct, while the code actually running comes from the patch path.

If patches are not managed like release artifacts, incident investigations may struggle to determine why two instances on the same version behave differently.

### 8.2. Binary Compatibility Errors

A patched class may be compiled against a different API than the runtime API. Differences in methods, fields, constructors, modifiers, or hierarchy can cause:

- `NoSuchMethodError`
- `NoSuchFieldError`
- `AbstractMethodError`
- `IncompatibleClassChangeError`
- `VerifyError`
- `ClassCastException`
- `NoClassDefFoundError`

Not every error surfaces immediately at startup. A rarely executed code branch might only fail when production receives a specific request or loads a particular plugin.

### 8.3. Altering Security Behavior

A class in a module may perform authentication, permission checks, input parsing, certificate validation, or resource management. An incorrect or unreviewed patch can bypass validation, alter trust boundaries, or expand accessibility.

Therefore, patch artifacts require the same review, source control, and security checks as main code. Do not obtain patches from unverified sources and do not allow untrusted users to write to the patch directory.

### 8.4. Module Boundary Mismatches

A patch does not replace the module descriptor. It does not automatically create necessary dependencies, `exports`, or `opens`. A patch can add a class to a package, yet callers in other modules still cannot access it if the package is not exported; reflection remains blocked if the package is not opened.

Trying to add many `--add-exports` or `--add-opens` flags just to make a patch run can mask a broader architectural change. Identify the exact module/package/target needing access and limit permissions to the minimum.

### 8.5. Difficulty Reproducing and Rolling Back

If a patch is mounted from a volume or manually copied into a container, two instances can run different patches despite having the same image tag. If the patch path is stored in an external environment variable or script, that configuration can be missed in the release process.

Rollback must also simultaneously restore:
- The original JAR/module.
- The patch directory/JAR and patch path order.
- JVM flags.
- Container or service configuration.
- Patch version/hash records.

Rolling back only the original JAR while forgetting the patch path may fail to restore original behavior.

## 9. Controlling Patches Before Deployment

If you must use a patch in production, treat the patch as an independent artifact with versioning and provenance.

A governance process should include:

1. **Clear justification:** document the bug or compatibility requirement the patch resolves.
2. **Controlled source:** store patch source in a controlled repository or artifact system.
3. **Reproducible build:** compile with the exact JDK, module graph, and compiler options.
4. **Artifact hash:** record the SHA-256 of the patch JAR or a manifest of the patch directory.
5. **Compatibility check:** confirm the patch was compiled against the exact original module version and runs on the exact JDK vendor/update.
6. **Automated tests:** run unit, integration, and regression tests on the exact runtime image containing the patch.
7. **Security review:** review changes to authentication, authorization, parsing, serialization, cryptography, and sensitive APIs.
8. **Deployment traceability:** record patch version/hash and JVM flags in deployment metadata.
9. **Rollback plan:** prepare the pre-patch image/configuration and a verifiable restoration procedure.
10. **Expiry/removal:** set conditions or a deadline to replace the patch with an official fix.

The patch path should reside inside an immutable image or versioned artifact. Avoid mounting a directory that can be silently modified after a container has been deployed.

## 10. Inspecting Applied Patches

When a process exhibits unusual results, inspect the launch command line and environment configuration of that exact JVM process. Look for options:

~~~text
--patch-module
--add-exports
--add-opens
--add-reads
~~~

Inspect the patch directory/JAR:

~~~bash
jar --list --file patches/core-fix.jar
sha256sum patches/core-fix.jar
~~~

On Windows, you can use:

~~~powershell
jar --list --file patches/core-fix.jar
Get-FileHash patches/core-fix.jar -Algorithm SHA256
~~~

Compare the list of classes/resources in the patch with the original module. If the patch replaces a class, verify the fully qualified class name and package. If the patch adds a resource, verify the exact path and how code looks up the resource.

You can inspect the original module's descriptor:

~~~bash
jar --describe-module --file mods/com.acme.core.jar
~~~

The descriptor shows the original module's structure; it is not a complete list of patched contents applied at runtime. Therefore, inspect the module artifact, patch artifact, and JVM command line together.

If you need to verify where a class is actually loaded from, you can enable class loading logs:

~~~bash
java -Xlog:class+load=info \
  --patch-module=com.acme.core=patches/com.acme.core \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Class loading logs help identify which classes were loaded during that run and the source location reported by the JVM. Use logging in a controlled test or investigation environment; output can be large and may contain internal filesystem paths.

## 11. Mechanisms Not to Confuse with Module Patching

| Mechanism | Effect | When Appropriate |
| --- | --- | --- |
| `--patch-module` | Adds/overrides classes and resources of a named module when JVM/compiler sets up the module | Testing or controlled module patching. |
| `--upgrade-module-path` | Prioritizes a replacement module to upgrade a same-named module via module resolution | Distributing a complete replacement module per upgrade design. |
| `--add-exports` | Adds public package access | Callers need to reference public types in an unexported package. |
| `--add-opens` | Adds deep reflection access | Frameworks need reflection into an unopened package. |
| Java agent | Instruments/redefines classes via the Instrumentation API | Monitoring or transforming classes in a running JVM, within API limits. |
| Replace JAR and re-release | Replaces the official module artifact | Long-term fix with clear version and provenance. |

If the goal is to replace an entire module with a new version, consider `--upgrade-module-path` or updating dependencies/artifacts. `--patch-module` is typically better suited for narrowly scoped additions/overrides, especially in testing.

## 12. Diagnostic and Production Decision Workflow

When a patch is proposed for a production environment, proceed in order:

1. Identify the module and class/resource needing change; record the fully qualified name.
2. Confirm the issue cannot be resolved by upgrading a dependency or fixing official source.
3. Check whether the patch replaces an existing class or only adds classes/resources.
4. Compile the patch with the exact JDK and exact module version; verify compiler/module options.
5. Run tests with the patch at both compile time and runtime so both environments see identical contents.
6. Run integration tests on the exact runtime image/container planned for deployment.
7. Verify module resolution, service providers, reflection, and relevant code paths.
8. Evaluate security risks, binary compatibility, startup, and performance.
9. Package the patch with an immutable image, recording hashes and JVM flags.
10. Test rollback using the exact operational procedure before broad rollout.
11. Monitor linkage errors, startup, request failures, and class loading logs after deployment.
12. Remove the patch once the official fix has been released and tested.

Do not use module patching to mask split package errors, missing dependencies, or broken module descriptors. Patching is not a tool to fix every JPMS error; it only alters the classes/resources a module receives. When the issue lies in package ownership, readability, `exports`, or `opens`, fix the corresponding structure/access directly.

## 13. Principles for Safe Usage

Module patching is very useful in testing and investigation, yet it introduces a layer of content running outside the main module artifact. In production, this impacts traceability, security, and environment reproducibility.

Use it only with a specific reason, limit the patch to necessary classes/resources, manage patch hashes and provenance, test on the exact JDK/runtime image, and keep a tested rollback. For long-term fixes, fold the change back into the module source and release a new clearly versioned artifact.
