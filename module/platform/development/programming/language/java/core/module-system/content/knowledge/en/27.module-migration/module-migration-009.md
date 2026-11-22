# Measuring Packaging and Deployment Impact

When migrating a Java application from the classpath to the Java Platform Module System (JPMS), changes extend beyond `module-info.java`. Compilation, the module path, the module graph, service providers, reflection, distribution layout, runtime images, and launch commands can all change. Therefore, a successful migration must be verified through **before/after packaging and deployment measurements**, rather than relying solely on successful compilation.

The goal is to answer practical questions: how much does total artifact size change; can a custom runtime image be built with `jlink`; do build and startup times change; are any modules or services missing at deploy time; and does rollback still work?

## 1. Defining the Scope to Measure

First, distinguish the following artifacts:

- **Product JAR:** the application's bytecode and resources, potentially containing `module-info.class`.
- **Dependency artifacts:** library JARs shipped with the application, which may be explicit, automatic, or classpath JARs.
- **Java runtime:** a full JDK/JRE or a custom runtime image created by `jlink`.
- **Distribution:** the complete ZIP, TAR, installation directory, installer, or container image released to users.
- **Deployment:** downloading/installing packages, configuring, starting, and bringing the application to readiness.
- **Runtime behavior:** startup, memory, service discovery, reflection, resource loading, and business execution paths.

Never equate the size of a single JAR with the size of a distribution. If before migration you packaged a small JAR while target machines needed a full JDK, and after migration you package the application alongside a custom runtime, the measurement boundary changed. Measure the same scope before and after, or report each deployment mode separately.

## 2. Locking a Pre-Modularization Baseline

Before editing code, record:

~~~text
Baseline:
- Commit/release:
- JDK vendor and version:
- OS / CPU architecture:
- Build tool and version:
- Build command:
- Packaging command:
- Actual launch command:
- JVM options:
- Dependency lock or resolved dependency list:
- Test workload:
- Distribution format:
- Deployment environment:
~~~

The baseline must be reproducible. If the system uses containers, record the base image digest, architecture, and configuration variables. If using Maven or Gradle, lock dependencies so results do not shift merely from library version upgrades.

The post-migration build should use the same JDK version, GC configuration, memory limits, and workload if the goal is isolating JPMS impact. If the JDK or frameworks are upgraded simultaneously, note this explicitly because those factors also affect speed and size.

## 3. Minimal Metrics Set

| Group | Metric | Unit |
|---|---|---|
| Artifact | Main JAR size | bytes, MiB |
| Dependency | Total size of dependency JARs | bytes, MiB |
| Runtime | Total size of bundled Java runtime | MiB |
| Distribution | Total size of ZIP/installer/directory | MiB |
| Container | Compressed size and uncompressed size | MB or MiB, specified |
| Build | Clean build duration | seconds |
| Packaging | Image/installer creation duration | seconds |
| Startup | Launch to readiness | milliseconds |
| Runtime | Peak RSS and heap usage under workload | MiB |
| Resolution | Number of modules in the boot layer | modules |
| Operations | Deploy, ready, and rollback duration | seconds/minutes |
| Compatibility | Number of module, reflection, or service discovery errors | error count |

For each metric, record `Before`, `After`, `Delta`, measurement method, and test conditions. Some metrics such as dependency errors must reach 0; module count or size is not automatically better just for being smaller.

Percentage formula when the baseline value is non-zero:

~~~text
Absolute delta = After - Before
Delta (%)      = (After - Before) / Before * 100
~~~

Hypothetical example:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Total distribution | 320 MiB | 240 MiB | -80 MiB (-25%) |
| Clean build | 40 s | 46 s | +6 s (+15%) |
| Cold startup | 1.50 s | 1.42 s | -0.08 s (-5.3%) |

These numbers illustrate the formula, not measurements from a real application. Size savings can come with increased build cost. Evaluate trade-offs against product requirements.

## 4. Reliable Measurement Methodology

A benchmark should follow a repeatable procedure:

1. Run on the same OS, JDK, CPU architecture, and JVM configuration.
2. Define a fixed workload and input dataset.
3. Perform clean builds when comparing full build times.
4. Measure multiple runs rather than picking a single best run.
5. Record median, p90, or spread for startup and deployment.
6. Distinguish cold startup from warm runs where the filesystem cache is hot.
7. Document whether network, database, DNS, or external service dependencies are included in the measurement.
8. Use the **exact artifact to be deployed**, not just IDE class outputs.

If the pipeline uses build caches or downloads dependencies over the network, separate download/cache time from compilation when analyzing causes. Results are only meaningful if conditions are documented well enough for another team to reproduce.

## 5. Dependency Analysis with jdeps

`jdeps` analyzes static bytecode dependencies to identify JDK modules and other dependencies.

Regular JAR example:

~~~bash
jdeps --print-module-deps app.jar
~~~

For a modular JAR on the module path:

~~~bash
jdeps --module-path mods \
      --print-module-deps \
      mods/com.acme.app.jar
~~~

For more detailed dependencies:

~~~bash
jdeps --module-path mods \
      --list-deps \
      mods/com.acme.app.jar
~~~

Record required modules, missing dependencies, and JDK internal packages still referenced by code. Do not automatically treat the `jdeps` list as the complete set of all runtime modules.

**Important limitation:** `jdeps` primarily inspects bytecode dependencies. Classes loaded via `Class.forName`, provider names read from configuration, reflection, service loading, JNI, or dynamic resources may not be fully detected. Always confirm with integration tests and real runtime checks.

## 6. Inspecting Modular JARs and Module Descriptors

An explicit modular JAR contains a `module-info.class` descriptor. Inspect the artifact after building:

~~~bash
jar --describe-module --file mods/com.acme.app.jar
jar --list --file mods/com.acme.app.jar
~~~

Sample descriptor:

~~~java
module com.acme.app {
    requires java.logging;
    requires java.sql;
    requires java.net.http;
}
~~~

During migration, record the changes:

- Whether the main JAR already has `module-info.class`.
- Whether the actual module name is stable.
- Which packages are `exports` or `opens`.
- Dependencies via `requires`, `requires transitive`, or `requires static`.
- Whether `uses` and `provides` service directives are accurate.
- Whether any dependency JARs cannot yet move onto the module path.

A modular JAR may be slightly larger than an older JAR due to the descriptor, but that does not mean the overall distribution is larger. JPMS focuses on the module graph, encapsulation, and enabling custom runtimes.

## 7. Observing the Runtime Module Graph

`--show-module-resolution` lets you observe resolved modules:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

In Java code, you can list modules in the boot layer:

~~~java
ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
~~~

This list shows modules directly defined in the boot layer, not every JAR sitting on disk. Save before/after lists to spot added modules, missing modules, or unexpected automatic modules.

If the application needs providers brought into the graph via service binding, test the bound configuration explicitly:

~~~bash
java --bind-services \
     --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

A larger graph is not necessarily bad: a required JDBC driver, logging provider, or crypto module must still be present. The goal is **complete dependencies without pulling in unintended modules**.

## 8. Building Custom Runtime Images with jlink

One way to reduce distribution size is using `jlink` to link the required application/JDK modules into a runtime image.

Example with explicit modular JARs packaged in `mods`:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --output runtime-image
~~~

On Windows PowerShell, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --output runtime-image
~~~

Verify the image:

~~~bash
./runtime-image/bin/java --list-modules
./runtime-image/bin/java -m com.acme.app/com.acme.app.Main
~~~

`--add-modules com.acme.app` selects the root; the resolver pulls in the dependency closure from descriptors. When measuring, take the size of the **entire `runtime-image` directory**, not just a single binary in `bin` or `lib`.

A smaller custom runtime image does not automatically prove the JVM uses less RAM or starts faster. Filesystem size, RSS, heap, and startup duration are distinct metrics and must be measured independently.

## 9. Automatic Modules Can Block Linking

During transition, a legacy library without `module-info.class` placed on the module path can become an automatic module. It gets its name from `Automatic-Module-Name` or derived from the JAR name.

Automatic modules help named-module applications reference legacy libraries, yet **`jlink` does not accept automatic modules as standard linking inputs**. Therefore, an application that still has automatic module dependencies can run with the Java launcher, but cannot yet be linked directly into a runtime image as expected.

Document in the report:

| Library kind | Status | Packaging impact |
|---|---|---|
| JDK/Java SE module | Named module with descriptor | Can be selected as root/dependency during linking |
| Explicit modular JAR | Has `module-info.class` | Participates in resolution and usable for linking if valid |
| Automatic module | Lacks explicit descriptor | Aids migration; has restrictions with `jlink` |
| Classpath library | Belongs to unnamed module | Needs separate compatibility/packaging strategy |

If linking is blocked, do not assume adding a manifest name alone is enough. You may need to upgrade the library to a modular release, swap dependencies, or pick another distribution model during the transition.

## 10. Service Providers and Runtime Image Impact

Applications using `ServiceLoader` have dynamic dependencies that cannot be inferred solely from `requires` clauses.

Consumer:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
~~~

Provider:

~~~java
module com.acme.formatter.json {
    requires com.acme.spi;
    provides com.acme.spi.Formatter
        with com.acme.formatter.json.JsonFormatter;
}
~~~

`jlink` has an option to bind available service providers:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --bind-services \
      --output runtime-with-providers
~~~

Service binding can pull many provider modules and their dependencies into the image; size may **increase** compared to an unbound configuration. If only one specific provider is needed, consider controlled root selection or deployment modes.

After creating the image, exercise the actual functional path to verify `ServiceLoader` locates and instantiates the provider. Note that a resolved provider is not yet instantiated; service loading typically happens when the application iterates the loader.

## 11. Reflection, opens, and Runtime Resources

JPMS enforces strong encapsulation on packages of named modules. A program may compile yet fail when frameworks require deep reflection:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

A module can open the exact package to the framework:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.serializer;
}
~~~

Wait—let's keep `com.acme.domain.api` exact as in the original! Let's double check line 281 of `module-migration-009.md`: `exports com.acme.domain.api;`! Good catch!

When a temporary workaround is needed, you can use `--add-opens` with the exact module/package/target. Be sure to include those JVM flags in the actual launch configuration of the image, container, or installer.

Commonly overlooked areas:

- ORM and entity construction.
- JSON/XML serializers accessing fields/constructors.
- Dependency injection and component scanning.
- Resources resolved by module path.
- JDBC drivers and service providers.
- TLS, certificates, security providers, locales, and charsets.

Test these on the **release artifact**. A smoke test calling only main or a health endpoint may miss dynamic loading code paths.

## 12. jpackage: Measuring App Images and Installers

`jpackage` can generate OS-specific app images or installers for application distribution.

Illustrative example with a modular application:

~~~bash
jpackage --type app-image \
         --name AcmeApp \
         --module-path mods \
         --module com.acme.app/com.acme.app.Main \
         --dest dist
~~~

When supplying a matching custom runtime:

~~~bash
jpackage --type app-image \
         --name AcmeApp \
         --runtime-image runtime-image \
         --module-path mods \
         --module com.acme.app/com.acme.app.Main \
         --dest dist
~~~

Depending on the JDK version, OS, and installed packaging tools, installer syntax/capabilities may vary. Test on your real build environment.

Beyond installer size, measure package creation, install, upgrade, and uninstall times; verify execution on a clean machine without a system JDK. A package may be smaller yet make updates or rollbacks more complex, so evaluate the entire distribution lifecycle.

## 13. Measuring Startup and Memory

To measure startup, define clear milestones:

~~~text
Start: timestamp when the Java process is created
Ready: timestamp when the application returns a successful readiness/health response
Startup duration = Ready - Start
~~~

Run multiple iterations and separate cold vs. warm startup. If readiness waits on a database or network, that duration is part of the end-to-end measurement; document it clearly.

Other runtime metrics:

- RSS and peak RSS.
- Heap used/committed.
- Metaspace.
- Class count and class loader count.
- CPU during startup and steady state.

Example JDK diagnostic commands:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

The `<pid>` placeholders must be replaced with the process ID. RSS must be measured using appropriate OS/container monitoring; heap used does not equal total RSS.

Keep `-Xms`, `-Xmx`, GC, workload, and container limits constant when comparing. Never assume a smaller runtime image automatically improves startup or memory.

## 14. Measuring Build, Pipeline, and Deployment

Migration may add pipeline stages:

~~~text
Before:
compile (classpath)
  -> package application
  -> copy dependencies
  -> deploy

After:
compile (module-path)
  -> package modular JAR
  -> inspect module descriptor
  -> dependency analysis
  -> optional jlink / jpackage
  -> test actual distribution
  -> deploy
~~~

Measure separately:

1. Clean compile and incremental compile.
2. Unit/integration tests.
3. JAR packaging.
4. Runtime image/installer creation.
5. Artifact upload/push.
6. Artifact download/pull on target environment.
7. Startup to readiness.
8. Total commit-to-ready pipeline duration.
9. Rollback duration to the previous release.

If custom runtimes must be built separately for Linux x86_64, Linux arm64, Windows, and macOS, CI and operational overhead can increase. A report that cites a smaller package while ignoring the build matrix fails to reflect the full impact.

## 15. Container Images and Target Operating Systems

For containers, measure both **compressed registry size** and **uncompressed filesystem size**, as the two values are not identical. Compare across the same architecture and base image whenever possible.

A deployment with a custom runtime still needs all underlying components:

- Native libraries used by Java and dependencies.
- Certificates/trust stores for TLS connections.
- Required time zones, locales, and charsets.
- Low-privilege user, filesystem permissions, and temp directories.
- Health checks, signal handling, and logging.

A custom image does not automatically include every OS dependency. A smaller image missing CA certificates or system libraries is still a broken package.

Record image digests to restore exact releases rather than relying solely on mutable tags.

## 16. Deployment Compatibility Test Matrix

| Test | Goal |
|---|---|
| Startup smoke test | Launcher runs with the new module graph |
| Module resolution | No missing roots/dependencies, no graph conflicts |
| ServiceLoader | Required providers appear and initialize properly |
| Database/JDBC | Drivers and connection pools work |
| Reflection/serialization | Needed packages are opened with exact scope |
| HTTP/TLS | Network connections, certificates, and providers work |
| Resource loading | Templates, configs, classpath/module resources exist |
| Background tasks | Schedulers, batch jobs, plugins initialize |
| Health/readiness | Deploy marks ready only when the app is functional |
| Rollback | Previous release can be restored with matching data and config |

Tests must use the exact JARs, runtime image, environment variables, and JVM options of production. An IDE running with a different classpath or flags is not sufficient proof that a deployment package succeeds.

## 17. Common Errors and Causes

| Symptom | Possible cause | What to check |
|---|---|---|
| `FindException: Module ... not found` | Root/dependency missing from image/module path | `--show-module-resolution`, `--list-modules` |
| `LayerInstantiationException` | Module graph/package conflict when defining layer | Descriptors, split packages, loader strategy |
| `IllegalAccessError` | Unsatisfied readability or exports | `requires`, `exports`, runtime flags |
| `InaccessibleObjectException` | Framework needs deep reflection | `opens`, `--add-opens` |
| `ServiceConfigurationError` | Missing/invalid provider or instantiation failure | `uses`, `provides`, service binding |
| `No suitable driver` | JDBC driver omitted from runtime | Driver JAR/provider, module graph |
| Small runtime but TLS fails | Missing crypto/certificates/providers/OS capability | Image contents, security, network |
| Passes locally, fails in container | Differing environment and JVM arguments | Reproduce exact container startup |
| jlink rejects dependency | Contains automatic/non-modular module that cannot be linked | Check dependencies, upgrade to modular versions |

Diagnose in layers: does the artifact contain all files, are modules resolved, do callers have read/access permissions, are providers discovered, and do runtime features operate?

## 18. A/B Impact Measurement Process

A workable process:

1. **Lock the baseline** including commit, JDK, OS, dependencies, commands, artifacts, and workload.
2. **Modularize cleanly** with `module-info.java` and real dependency resolution.
3. **Inspect descriptors** using `jar --describe-module`.
4. **Analyze static dependencies** with `jdeps`.
5. **Build equivalent distributions** and measure total artifact/runtime/package bytes.
6. **Run integration tests on the real package**; especially service providers, reflection, JDBC, and TLS.
7. **Measure performance repeatedly**: cold startup, median/p90, peak RSS, readiness.
8. **Measure the pipeline**: clean build, packaging, upload, deploy, rollback.
9. **Report trade-offs** using before/after/delta tables, along with test environments.
10. **Make a decision** with acceptance criteria or specific blockers.

Do not change frameworks, database drivers, and the JDK simultaneously if you want to isolate JPMS impact accurately. If changes cannot be isolated, document the limitations of the data.

## 19. Migration Impact Report Template

~~~text
JPMS Migration Impact

Scope:
- Application/release:
- Baseline revision:
- Modular revision:
- JDK, OS, architecture:
- Packaging modes:

Artifact & Distribution:
- App JAR bytes: before / after / delta
- Dependency bytes: before / after / delta
- Runtime bytes: before / after / delta
- Full distribution bytes: before / after / delta
- Container compressed/uncompressed size:

Build & Runtime:
- Clean build median:
- Linking/installer time:
- Cold startup median/p90:
- Peak RSS:
- Boot module count:

Compatibility:
- Module resolution:
- Service providers:
- Reflection/serialization:
- JDBC/HTTP/TLS:
- Smoke/integration tests:
- Remaining runtime workarounds:

Operations:
- Deploy duration:
- Rollback duration:
- Readiness:
- Artifact/image digest:

Decision:
- Accept / Block / Further investigation
- Risks and owner:
- Evidence:
~~~

If an item has not been measured, record "not measured"; do not substitute guessed or illustrative numbers. Tie results to the build artifact/digest so the exact tested build can be traced.

## 20. Takeaways

**Measure JPMS migration impact across the entire distribution lifecycle.** A modular JAR may not be smaller than an old JAR, yet `jlink` can help create a runtime image containing only needed modules when inputs meet requirements. `jdeps` aids static dependency analysis; `jar --describe-module` confirms descriptors; `--show-module-resolution` observes the graph; `jpackage` can generate app images or installers.

Compare size, build time, startup, and memory only under equivalent measurement conditions. Verify dynamic dependencies like `ServiceLoader`, JDBC, reflection, TLS, and resource loading on the exact artifact to be deployed. A solid report includes a clear baseline, repeatable measurements, deltas, limitations, rollback readiness, and an evidence-backed deployment decision—not just a context-free "size reduction" headline number.
