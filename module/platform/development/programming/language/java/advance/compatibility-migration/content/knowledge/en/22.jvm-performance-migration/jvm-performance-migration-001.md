# Deprecated, ignored, or removed JVM flags

When upgrading the JDK, a Java application may fail to start because a JVM option accepted in the older release has been removed. Even more dangerously, the application might **start cleanly while a flag that previously controlled GC, locking, or logging has become a no-op**. Operators assume the old tuning configuration is still active, while the JVM actually runs with new defaults or mechanisms. The system throws no exception in this case, yet latency, CPU usage, memory footprint, GC pauses, and diagnostic visibility can shift.

A classic example is `-XX:MaxPermSize`: Permanent Generation was removed from HotSpot in JDK 8; in JDKs that still syntactically accept the legacy option, the JVM may warn that it is **ignoring** it. Another example is `-XX:+UseConcMarkSweepGC`: CMS was removed in JDK 14. A startup script carrying CMS flags from Java 8 is no longer proof that the new JVM uses CMS.

This lesson explains the lifecycle of JVM flags in HotSpot, how to distinguish **deprecated**, **obsolete/ignored**, and **expired/removed**, easily confused compatibility cases, methods for gathering effective options, and a workflow for replacing legacy flags during Java Advance Compatibility Migration.

## 1. What are JVM flags and where are they passed?

JVM flags are arguments used to configure how the Java virtual machine starts and operates. They differ from business arguments passed to the `main(String[] args)` method.

Example:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar orders-service.jar --profile=prod
~~~

In this example:

- `-Xms512m` and `-Xmx2g` control heap sizing per JVM policy.
- `-XX:+UseG1GC` requests the G1 garbage collector on supporting HotSpot builds.
- `-jar orders-service.jar` selects the application.
- `--profile=prod` after the JAR filename is an **application** argument, not a `-XX` JVM flag.

A system can also inject options via scripts, container images, service managers, IDEs, or environment variables, so the command line visible to a developer is not necessarily the complete configuration.

### 1.1. Common option categories

| Category | Examples | Meaning |
|---|---|---|
| Standard options | `-version`, `-cp`, `--module-path` | Parameters documented by the Java launcher specification |
| Extra options `-X` | `-Xms`, `-Xmx`, `-Xlog` | Additional options, typically HotSpot-specific |
| Advanced options `-XX` | `-XX:+UseG1GC`, `-XX:MaxRAMPercentage=75` | Controls GC, JIT, memory, serviceability, etc. |
| System properties `-D` | `-Dfile.encoding=UTF-8` | Sets Java system properties; not every property is a JVM tuning flag |
| Module/runtime options | `--add-opens`, `--add-exports` | Controls module accessibility per JDK rules |
| Agent options | `-javaagent`, `-agentpath` | Loads Java/native agents at startup |
| Application arguments | `--spring.profiles.active=prod` after `-jar app.jar` | Handled by the application/framework itself |

A `-D...` property can alter platform behavior, yet system properties should not all be lumped into the `-XX` category because lifecycles and error messages differ.

### 1.2. Boolean and value syntax

A HotSpot boolean flag typically has the form:

~~~bash
-XX:+SomeFeature   # Request enable
-XX:-SomeFeature   # Request disable
~~~

A flag taking a value:

~~~bash
-XX:MaxMetaspaceSize=256m
-XX:MaxRAMPercentage=70.0
~~~

`+`/`-` prefixes and `=value` syntax cannot be swapped arbitrarily across flags. A malformed option, out-of-range value, or unmet precondition can still cause the JVM to refuse startup even when the flag name is recognized.

## 2. Lifecycle of a HotSpot flag: accepted does not mean active

HotSpot follows a lifecycle process for many tuning flags. Important terms:

| State | What does the JVM typically do? | Practical impact |
|---|---|---|
| **Supported / active** | Accepts and executes option per documented behavior | Flag can affect runtime behavior |
| **Deprecated** | Still accepts and **still applies**, while emitting a warning | Plan replacement; do not assume the flag is already a no-op |
| **Obsolete** | May still accept, warn, and **ignore the value** | Flag likely has no effect even though the JVM runs |
| **Expired / removed** | Rejects the option or reports unrecognized VM option | JVM may exit before running application code |
| **Contextually ignored** | Option may be valid yet inactive in the current setup | May emit no warning; verify effective behavior |
| **Locked / experimental / diagnostic** | Flag exists but requires unlocking or matching conditions | Neither deprecated nor removed |

Under HotSpot's lifecycle model, the typical progression is:

~~~text
ACTIVE
   |
   v
DEPRECATED
  Still applied with warning
   |
   v
OBSOLETE
  Accepted yet ignored, warning
   |
   v
EXPIRED / REMOVED
  Rejected, may fail JVM startup
~~~

This is a **conceptual model**. Not every flag traverses all stages; experimental flags or specific JVM implementations may follow different policies. Status cannot be inferred from flag names alone—always verify against the **JDK feature release, update release, JVM vendor, and build**.

### 2.1. Deprecated: still active, yet prepare migration

When a flag is deprecated, the JVM may print a warning like:

~~~text
Java HotSpot(TM) 64-Bit Server VM warning:
  Option SomeFlag was deprecated in version X
  and will likely be removed in a future release.
~~~

The snippet above is illustrative, not fixed wording across all versions. **Do not delete an important tuning flag merely because it says deprecated** and assume behavior will stay identical. Record baselines, understand its current effect, pick a replacement strategy, and test on the target runtime.

### 2.2. Obsolete: still accepted, yet no longer controls the JVM

An obsolete flag may print a notice like:

~~~text
OpenJDK 64-Bit Server VM warning:
  Ignoring option SomeFlag; support was removed in ...
~~~

The JVM may continue starting up. This is easily misread: the system booting **does not prove the flag is doing anything**. If the flag previously governed GC or locking, performance may shift dramatically.

### 2.3. Removed/expired: explicit startup failure

Illustrative example:

~~~text
Unrecognized VM option 'SomeOldFlag'
Error: Could not create the Java Virtual Machine.
Error: A fatal exception has occurred.
~~~

This is a JVM parsing/configuration failure occurring **before `main()`**. If application logs never appear, it does not mean code failed to deploy—the Java process may have failed option parsing.

Similar errors also arise from misspelled flags or options specific to another JVM vendor. Distinguish “removed in this JDK” from “never existed on the active runtime”.

### 2.4. Contextually ignored differs from obsolete

For example, a flag applies only to a specific GC while the application runs a different collector. Some HotSpot builds accept the option without effect under the active setup. In addition, the JVM may adjust values dynamically at runtime or through ergonomics.

Consequently, **accepted by the parser**, **stored as a flag**, and **having real runtime impact** are three distinct verification tiers.

## 3. Major historical examples when upgrading the JDK

### 3.1. Permanent Generation removed from HotSpot in JDK 8

Prior to JDK 8, HotSpot had Permanent Generation (PermGen) and flags such as:

~~~bash
-XX:PermSize=128m
-XX:MaxPermSize=256m
~~~

JDK 8 replaced PermGen with **Metaspace** (JEP 122). On runtimes retaining syntax compatibility, PermGen flags may be ignored with warnings.

A legacy configuration:

~~~bash
java -XX:MaxPermSize=256m -jar app.jar
~~~

does not bound Metaspace on newer JDKs. Metaspace options to evaluate include:

~~~bash
-XX:MetaspaceSize=128m
-XX:MaxMetaspaceSize=512m
~~~

**Never mechanically replace `MaxPermSize=256m` with `MaxMetaspaceSize=256m`.** PermGen and Metaspace have different management, memory accounting, and effects; setting a Metaspace limit too low can trigger `OutOfMemoryError: Metaspace`. Measure class loading, Metaspace commit/usage, and native memory before choosing caps.

### 3.2. CMS GC removed in JDK 14

The **Concurrent Mark Sweep (CMS)** collector was deprecated in JDK 9 and removed in JDK 14 under **JEP 363**. Historical options such as:

~~~bash
-XX:+UseConcMarkSweepGC
-XX:+CMSClassUnloadingEnabled
-XX:CMSInitiatingOccupancyFraction=70
~~~

are no longer valid CMS tuning once CMS is removed. On some builds, the JVM may warn/ignore old flags; on others, the flags are expired and rejected.

**Migration direction:** select a supported collector, such as G1 for suitable workloads:

~~~bash
java -XX:+UseG1GC -Xmx4g -jar app.jar
~~~

Yet swapping `UseConcMarkSweepGC` for `UseG1GC` does not guarantee identical latency, throughput, and footprint. CMS and G1 use different policies, tuning knobs, region layouts, and pause models. Measure GC logs, p95/p99 latency, CPU usage, allocation rate, and heap occupancy before/after switching.

### 3.3. Biased locking: deprecated in JDK 15, obsolete in JDK 18

**JEP 374** disabled biased locking by default and deprecated related options in **JDK 15**. Per JDK 18 release notes, `UseBiasedLocking` and options like `BiasedLockingStartupDelay` became **obsolete**, emitting warnings and being ignored in JDK 18.

Legacy options example:

~~~bash
-XX:+UseBiasedLocking
-XX:BiasedLockingStartupDelay=0
~~~

Merely copying these two flags from an old optimization guide onto Java 21 does not mean biased locking is enabled. Subsequent releases may alter support further, so verify on your exact target JDK.

If the application performs heavy uncontended synchronized operations, measure actual behavior on the new JVM. Do not try to preserve an altered locking mechanism using no-op flags.

### 3.4. GC logging moved to Unified Logging in JDK 9

Before JDK 9, scripts commonly used flags like:

~~~bash
-verbose:gc
-Xloggc:/var/log/app/gc.log
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-XX:+UseGCLogFileRotation
~~~

JDK 9 introduced **Unified JVM Logging** (JEP 158); many legacy GC/tracing flags were subsequently deprecated, aliased, obsoleted, or removed across later releases. Never assume every flag in the list above holds the same status across all JDKs.

A modern HotSpot equivalent:

~~~bash
java \
  -Xlog:gc*,safepoint=info:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=10M \
  -jar app.jar
~~~

This example uses Unix shell syntax. `gc*` selects relevant GC tags, `safepoint=info` adds safepoint events, and `filecount`/`filesize` configure Unified Logging rotation.

New configurations are not strict 1-to-1 flag translations. Determine the event tags, log levels, decorators, and rotation needed by your GC analysis workflows. For instance, `-Xloggc` might still be deprecated in a newer JDK, yet switching to `-Xlog:gc:file=...` eliminates legacy syntax reliance.

### 3.5. Class-loading tracing flags

Some older applications use:

~~~bash
-XX:+TraceClassLoading
-XX:+TraceClassUnloading
-XX:+TraceExceptions
~~~

These tracing flags were superseded by Unified Logging and became obsolete after JDK 9 introduced the new framework. Common equivalents:

~~~bash
-Xlog:class+load=info
-Xlog:class+unload=info
-Xlog:exceptions=info
~~~

Example:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Never swap flag names without checking log volume and destinations. Class-loading logs in production can grow huge, so constrain duration, log level, and disk capacity.

### 3.6. `--illegal-access`: obsolete does not mean encapsulation is relaxed

During JPMS migration, `--illegal-access=permit` temporarily relaxed reflective access to internal JDK packages. JDK 17 (JEP 403) rendered this option **obsolete**; it no longer relaxes strong encapsulation as in earlier JDKs.

Example:

~~~bash
java --illegal-access=permit -jar legacy-app.jar
~~~

On a JDK that still accepts yet ignores the option, its presence on the command line **does not permit illegal reflective access**. Proper remediation is upgrading frameworks relying on JDK internals or applying targeted configuration such as:

~~~bash
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

Use `--add-opens` only after identifying exact packages, callers, and deep-reflection requirements; never turn it into an uncontrolled list of broad opens.

### 3.7. Security Manager as a system-property example

`java.security.manager` is primarily a **system property**, not a `-XX` flag, yet still must be inventoried during migration because many scripts bundle it with JVM flags.

In **JDK 24**, under JEP 486, enabling the Java Security Manager was permanently disabled. A command line attempting `-Djava.security.manager=allow` or a similar activation mode can cause the JVM to fail and exit. This differs from an obsolete flag that is accepted and ignored.

If the application relied on Security Manager for sandboxing, merely deleting the property so the JVM boots is insufficient: you must re-evaluate the security model because the former safeguard no longer exists. Process/container isolation, OS permissions, and network policies are measures to evaluate.

### 3.8. Selected RTM locking options removed in JDK 25

Oracle JDK 25 `java` command documentation notes related RTM locking options such as:

~~~bash
-XX:+UseRTMDeopt
-XX:RTMAbortRatio=50
-XX:RTMRetryCount=5
~~~

among options removed in JDK 25. Legacy lock-tuning scripts carrying them can fail with `Unrecognized VM option` on that release.

This demonstrates that GC flags are not the only ones that evolve. JIT, locking, CPU-specific intrinsics, and tracing options also have lifecycles. When spanning multiple major releases, audit all options—not solely `-Xmx` and `-XX:+UseG1GC`.

## 4. Classification table for frequent cases

The table below notes **documented change milestones** without implying flags retain identical status on every subsequent JDK release.

| Option / group | Notable milestone | Required action |
|---|---|---|
| `-XX:PermSize`, `-XX:MaxPermSize` | PermGen removed in JDK 8; legacy flags may be ignored | Remove legacy flags; evaluate Metaspace instead of 1-to-1 mapping |
| `-XX:+UseConcMarkSweepGC` and CMS options | CMS deprecated JDK 9, removed JDK 14 | Select a supported GC, re-benchmark pauses/throughput |
| `-XX:+UseBiasedLocking` | Disabled/deprecated JDK 15, obsolete JDK 18 | Remove legacy flags; measure concurrency/locking |
| `-XX:+TraceClassLoading` | Migrated to Unified Logging after JDK 9 | Use `-Xlog:class+load=info` |
| `-XX:+TraceClassUnloading` | Migrated to Unified Logging | Use `-Xlog:class+unload=info` |
| `-XX:+TraceExceptions` | Migrated to Unified Logging | Use `-Xlog:exceptions=info` |
| `-Xloggc:...` | Recommended replacement via Unified Logging | Use `-Xlog:gc:...` with modern syntax |
| `--illegal-access=permit` | Obsolete since JDK 17 | Do not rely on it to re-open internal APIs |
| `-Djava.security.manager=allow` | Enabling Security Manager blocked in JDK 24 | Redesign protection; do not hunt for bypass flags |
| Selected `-XX:RTM...` options | Removed in JDK 25 | Remove from scripts and measure lock performance |
| `-XX:+IgnoreUnrecognizedVMOptions` | Still supported by some HotSpot builds to skip unrecognized flags | Do not use to mask migration failures |

`-XX` options are **JVM implementation-specific**, so a HotSpot flag is not guaranteed to carry the same meaning on OpenJ9 or GraalVM. Differences can also appear across vendor builds and update releases.

## 5. A flag appearing in `PrintFlagsFinal` is not guaranteed active

HotSpot supports printing flag tables:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Output includes flag names, types, values, and origins. Illustrative structure:

~~~text
size_t MaxHeapSize = ... {product} {ergonomic}
bool UseG1GC = true {product} {command line}
~~~

Never copy sample lines as fixed truths: values and origin markers depend on JDK, host, container, and command line.

### 5.1. Meaning of “effective value”

A JVM flag may be:

- Explicitly set by the user on the command line.
- Chosen by the JVM via ergonomics.
- Computed from CPU/RAM/container limits.
- Dependent on another flag or the active collector.
- Adjustable at runtime if marked manageable.
- Absent from the table altogether because it is obsolete/removed.

Therefore, `PrintFlagsFinal` is valuable evidence, yet **insufficient** to confirm a tuning knob actually improves performance. Correlate logs and metrics tied directly to the subsystem it governs.

### 5.2. `PrintCommandLineFlags` and `VM.flags`

Some HotSpot versions support:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

This prints notable command-line/ergonomic flags, though not always every option in complex deployments.

For a running process:

~~~bash
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
~~~

`12345` is an illustrative PID. `VM.command_line` displays the startup command, while `VM.flags` and `VM.flags -all` inspect flags reported by the JVM. These diagnostic commands depend on JVM support and attach/process permissions; run `jcmd 12345 help` if unsure.

### 5.3. `-Xlog:arguments` is not a universal source across all JDKs

When logging command-line arguments or startup info, choose log tags/options **documented as supported by your target JDK** rather than inventing tags. Run `java -Xlog:help` to list available unified logging tags and options.

~~~bash
java -Xlog:help
~~~

Nonexistent tags or invalid syntax can also cause JVM startup failures.

## 6. Tracing JVM flag sources: beyond `JAVA_HOME`

In modern systems, startup flags flow from multiple layers:

~~~text
Dockerfile / base image
       |
       +--> Entrypoint shell script
       |       |
       |       +--> JAVA_OPTS (script/framework-specific convention)
       |       +--> JAVA_TOOL_OPTIONS
       |       +--> JDK_JAVA_OPTIONS
       |       +--> _JAVA_OPTIONS (implementation-specific)
       |       +--> java @args-file
       |
       +--> Kubernetes Deployment / Helm values
       |
       +--> Service manager (systemd, Windows Service)
       |
       +--> CI/CD deployment variables
       |
       v
    Actual JVM command line
~~~

### 6.1. `JAVA_TOOL_OPTIONS` and `JDK_JAVA_OPTIONS`

These environment variables inject options into Java startup within the scope supported by the launcher/JVM. They are handy in containers or builds/tests, yet can accidentally pass obsolete/incompatible flags into unintended Java processes.

Example:

~~~bash
export JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65.0"
java -jar app.jar
~~~

Or:

~~~bash
export JDK_JAVA_OPTIONS="-Xlog:gc"
java -jar app.jar
~~~

Each variable has its own processing scope and restrictions. Never assume they behave identically for every option or order. On multi-JDK hosts, a variable intended for a newer JDK can break processes still running an older JDK.

### 6.2. `JAVA_OPTS` is not a standard Java launcher parameter

Many Docker entrypoints, application servers, and startup scripts read `JAVA_OPTS`, yet the Java launcher itself does not automatically consume it. Editing `JAVA_OPTS` takes effect only if your script explicitly expands that variable onto the command line.

Inspect the actual entrypoint or live process arguments rather than assuming based solely on environment variables.

### 6.3. Argument files

The Java launcher can read flags from files:

~~~text
# jvm.args
-Xms512m
-Xmx2g
-XX:+UseG1GC
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

Launched via:

~~~bash
java @jvm.args -jar app.jar
~~~

During audits, inspect `@...` files as well. A file holding an obsolete flag might live inside a container image or mounted volume outside the application repository.

### 6.4. Protecting sensitive information

Command-line logs or environment dumps may expose tokens, passwords, and internal endpoints. Collect only relevant flags and scrub secrets before sharing—especially if `-Dsome.password=...` is used. Never paste full raw process command lines into public tickets.

## 7. Workflow for auditing JVM flags before upgrading the JDK

### Step 1: Identify source and target runtimes

Record:

~~~bash
java -version
java -XshowSettings:vm -version
~~~

If multiple JDKs exist on the machine, run commands using the exact executable inside the deployment image or host. Relying on a laptop's JDK is insufficient for validating production behavior.

Document:

- JDK feature/update/build versions.
- Vendor and JVM implementation.
- OS/architecture.
- Container image and CPU/RAM limits.
- Effective command line/JVM options.

### Step 2: Gather all startup options

Inspect application manifests/scripts, Dockerfiles, service managers, Kubernetes values, CI deployments, and environment variables. Include options injected automatically by APMs, platforms, or sidecars.

Build an inventory:

| Flag | Source | Historical purpose | Status on target JDK | Action |
|---|---|---|---|---|
| `-XX:MaxPermSize=256m` | Startup script | PermGen cap | Legacy/ignored | Remove; measure Metaspace |
| `-XX:+UseConcMarkSweepGC` | Helm values | CMS GC | CMS removed | Choose supported GC, benchmark |
| `-Xloggc:gc.log` | Wrapper script | GC log file | Legacy/deprecated syntax on newer JDK | Migrate to Unified Logging |
| `-XX:+UseBiasedLocking` | Shared JAVA_OPTS | Lock tuning | Obsolete as of JDK 18 | Remove; measure lock contention |
| `-Xmx2g` | Dockerfile | Heap cap | Supported option | Verify against container limit |
| `--add-opens=...` | Runtime config | Reflection integration | Package/module dependent | Verify necessity and scope |

Do not edit every line immediately. First determine **which flags are actually active and what they influence**.

### Step 3: Classify by lifecycle

For each flag:

1. Is it HotSpot or another JVM vendor's flag?
2. Does the target JDK accept the option?
3. Does it emit a deprecated/obsolete warning?
4. If accepted, does it still take effect?
5. Does an official replacement option exist?
6. Does removing it alter defaults/ergonomics?
7. Do tests/metrics confirm the original tuning goal?

Save release notes or specific JEPs documenting major changes rather than guessing from an old flag list.

### Step 4: Smoke-test flag parsing

On the target runtime, test launching the JVM with the candidate flags before running the full app:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -version
~~~

Unrecognized options surface immediately here. However, **`-version` succeeding proves only part of the startup path**. Some options trigger failures or effects only once class loading, native agents, GC, modules, or application workloads engage.

Use a test environment and inspect **both exit code and stderr**. Warnings do not always produce a non-zero exit code.

### Step 5: Compare flags before and after

Capture outputs of `PrintFlagsFinal`, `VM.flags`, and the JVM command line on both source and target JDKs. Do not compare outputs with the mindset “identical values mean better compatibility”: newer JDKs intentionally change defaults and retire obsolete knobs.

Look specifically for shifts in **performance and operational assumptions**: collectors, heap sizing, logging, tiered compilation, code cache, container awareness, and user-specified flags.

### Step 6: Run monitored workload tests

Execute identical artifacts, workloads, and representative data conditions. Track:

- Startup time.
- Heap usage, GC allocation rates, pause times.
- p50/p95/p99 latencies.
- Throughput and CPU utilization.
- Container memory limits/OOM kills.
- Native memory/Metaspace.
- JIT warmup and compilation activity if relevant.
- Log volume and post-incident diagnostic utility.

Never declare “equivalence verified” simply because the JVM printed no warnings and healthchecks passed.

## 8. Migrating legacy GC logging to `-Xlog`

GC logging is among the easiest flag groups to convert yet hides several traps.

### 8.1. General Unified Logging syntax

Typical form:

~~~text
-Xlog:<what>:<output>:<decorators>:<output-options>
~~~

Where:

- `what` selects tags and levels, such as `gc*` or `gc+heap=debug`.
- `output` may be `stdout`, `stderr`, or a file.
- `decorators` add timestamps, uptime, log level, tags, etc.
- `output-options` configure file rotation in applicable setups.

Example:

~~~bash
-Xlog:gc*:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

If the output directory does not exist or lacks write permissions, the JVM may fail startup or skip log creation. Prepare filesystems, disk quotas, and rotation rules inside containers prior to rollout.

### 8.2. Do not translate 1-to-1 by name

An old script carrying `PrintGCDetails` and `PrintGCDateStamps` does not automatically need identical-looking `-Xlog` tags. Ask:

- Is the goal measuring pause times or analyzing heap occupancy?
- Is safepoint data required?
- Are rotation and retention limits defined?
- Which collector emits the logs?
- Must outputs stay compatible with existing log parsers/dashboards?

Verify your GC log analyzer parses the new format cleanly. The JVM writing logs cleanly does not guarantee existing dashboards still ingest them.

### 8.3. Log level affects overhead

`info` usually suits ongoing operations; `debug` or `trace` can substantially inflate log volume and overhead. Never turn on every tag at `trace` in production merely trying to “preserve the detail level” of a historical flag.

## 9. Choosing a new GC: there is no 1-to-1 mapping for CMS flags

When upgrading from JDK 8 running CMS to a newer JDK, legacy tuning knobs have no direct equivalent.

### 9.1. Legacy CMS configuration example

~~~bash
java \
  -Xms4g -Xmx4g \
  -XX:+UseConcMarkSweepGC \
  -XX:CMSInitiatingOccupancyFraction=70 \
  -XX:+UseCMSInitiatingOccupancyOnly \
  -jar service.jar
~~~

Do not convert this into:

~~~text
Swap CMS name for G1
Keep every % threshold unchanged
Assume equivalent pause times
~~~

G1 has its own region selection, pause prediction, and concurrent marking mechanics. CMS parameters are not direct G1 tuning knobs.

### 9.2. Starting fresh cleanly

A simpler baseline configuration:

~~~bash
java \
  -Xms4g -Xmx4g \
  -XX:+UseG1GC \
  -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \
  -jar service.jar
~~~

Then measure actual runs, define SLO goals, and tune G1 appropriately (for example `-XX:MaxGCPauseMillis` with rationale). Target goals are not hard pause guarantees and should never be copied blindly from CMS guides.

Modern JDKs also offer collectors like ZGC or Shenandoah on supporting runtimes. Choose collectors based on workload traits and vendor support matrices, not legacy flag names.

## 10. Memory and container flags: valid options can still misfit

Not every post-upgrade issue comes from deprecated flags. Valid flags can interact differently with **new ergonomics** or container setups.

### 10.1. `-Xmx` and RAM percentages

Example:

~~~bash
-Xmx2g
-XX:MaxRAMPercentage=70.0
~~~

When setting an explicit heap cap via `-Xmx`, do not assume `MaxRAMPercentage` applies as expected. Verify actual `MaxHeapSize` via JVM flags or `-XshowSettings:vm`.

Inside memory-limited containers, measure total RSS rather than heap alone: the JVM also allocates Metaspace, code cache, direct buffers, thread stacks, and native memory.

### 10.2. `UseContainerSupport` and CPU detection

Modern Linux HotSpot JDKs detect container resource limits. However, handling of cgroups, CPU quotas, and memory limits evolves across JDK releases and environments.

When upgrading the JDK alongside base images, kernels, or cgroup versions, differences in GC thread counts or `Runtime.availableProcessors()` do not necessarily come from ignored old flags. Inspect with:

~~~bash
java -Xlog:os+container=info -version
java -XX:+PrintFlagsFinal -version
~~~

Log format and detail depend on the JDK version. Some runtimes require `debug` level to show fuller diagnostics.

### 10.3. Do not preserve legacy “tuning magic” indefinitely

A `JAVA_OPTS` string stuffed with dozens of unmeasured `-XX` flags makes migration harder. Flags added to work around JDK 8 bugs often become unnecessary or counterproductive on newer JDKs.

A sound strategy starts from minimal custom flags, captures a fresh baseline, and adds flags only with **supporting hypotheses and benchmark data**. Never blindly delete essential safety caps like heap limits, OOM diagnostics, or proxy/network config.

## 11. `IgnoreUnrecognizedVMOptions`: why not to use it for migration

HotSpot supports the option:

~~~bash
-XX:+IgnoreUnrecognizedVMOptions
~~~

This can instruct the JVM to **skip unrecognized VM options** rather than failing immediately. It is occasionally used in shared multi-JDK scripts to keep one JDK from aborting on flags meant for another.

In migrations, however, it carries serious risks:

- A flag typo gets silently ignored instead of caught.
- A vital tuning flag loses effect while the app keeps booting.
- Differences across JVM vendors are masked.
- Other invalid argument values or policies remain unhandled by this option.
- Operations loses clear evidence that a configuration is no longer supported.

Example:

~~~bash
java -XX:+IgnoreUnrecognizedVMOptions \
     -XX:+SomeNonexistentTuningFlag \
     -version
~~~

This command merely demonstrates the hazard; **it is strongly discouraged** in production to ignore unknown flags. A JVM starting cleanly does not prove settings took effect.

If supporting shared scripts across multiple JDKs, prefer **branching configs cleanly per supported JDK**, with separate startup tests per JDK verifying effective flags. Avoid a global “ignore” flag acting as an error mask.

### 11.1. Startup gates should be strict

In CI or canary stages, an “obsolete flag ignored” warning should be treated as migration debt to resolve even with exit code 0. On `Unrecognized VM option`, fail the build/deploy with clear diagnostics.

Capturing startup stderr in non-sensitive environments is helpful, though never dump raw logs containing secrets into public pipeline artifacts.

## 12. Deprecated differs from experimental and diagnostic

HotSpot exposes diagnostic and experimental option groups requiring explicit unlocking:

~~~bash
-XX:+UnlockDiagnosticVMOptions
-XX:+UnlockExperimentalVMOptions
~~~

These **are not** ways to restore removed flags. An experimental flag gated behind an unlock switch is not deprecated; an expired flag will not revive simply by enabling `UnlockExperimentalVMOptions`.

### 12.1. Locked-flag errors

The JVM may report that a flag requires its matching unlock option first. Evaluate whether the team genuinely needs that flag and understands production risks before unlocking it.

### 12.2. Experimental flags carry weaker stability guarantees

Experimental options evolve faster and carry fewer compatibility promises. Never treat an experimental flag tested during benchmarking as a durable tuning contract across multiple JDKs.

### 12.3. Diagnostic flags do not replace long-term observability

Diagnostic flags can generate heavy log volume or alter performance profiles. Using them in runbooks should specify purpose, activation window, size caps, and deactivation steps.

## 13. Checking flags across JVM vendors and architectures

Java SE standardizes APIs and core behavior, whereas `-XX` flags are implementation-defined. HotSpot, OpenJ9, and custom distributions may use different tuning flags/syntaxes.

For example:

- HotSpot uses `-XX:+UseG1GC` in G1-supporting JDKs.
- OpenJ9 uses distinct memory/GC options under its own architecture.
- Certain intrinsics or RTM options depend on CPU/platform.
- Container flags can behave differently by OS.
- Diagnostic serviceability commands vary across JVMs.

Thus, a script written for “Java 21” is not guaranteed to run identically across every Java 21 JVM. Explicitly specify **vendor/implementation**, or scope configs to your support matrix.

### 13.1. Do not turn integer version checks into the entire rule

For example:

~~~text
if java.version >= 17:
    use new option
~~~

is overly simplistic when flags vary by JDK vendor, update build, or platform. When dynamic configuration is necessary, back it with a tested matrix for actually supported combinations.

### 13.2. Verify inside real artifacts and containers

`java -version` on a host machine does not ensure `java` inside containers matches. During investigations, test inside production-equivalent environments and verify image digests, JDK homes, startup scripts, and live process command lines.

## 14. Separating JVM option failures from application errors

A startup failure after upgrading the JDK is not necessarily caused by Java application code. Follow this decision tree:

~~~text
JVM process fails to start
       |
       v
"Unrecognized VM option" message present?
       |
  +----+----+
  |         |
 Yes        No
  |         |
  v         v
Check    Error opening log file, heap, agent,
flag,    module, class file, JNI, or GC init?
JDK/vdr     |
  |         v
  |      Read stderr and hs_err logs
  v
Cross-check flag with target JDK docs
  |
  +--> Deprecated: still takes effect, test before removing
  |
  +--> Obsolete: ignored, remove/replace properly
  |
  +--> Removed: must remove/change option
  |
  +--> Typo/locked/invalid: fix syntax or config
  |
  v
Re-run startup smoke test then run workload
~~~

If the JVM starts yet suffers performance regressions, check GC logs, heap usage, JIT activity, container limits, and effective flags. Never cite an application error like `NoSuchMethodError` to declare a tuning flag ineffective without evidence.

### 14.1. Errors occurring before `main()`

Removed or malformed flags fail prior to entering Java's `main`. Inside container orchestrators, this manifests as CrashLoopBackOff, failed startup probes, or services producing zero application logs.

Patterns to look for in stderr/container logs:

~~~text
Unrecognized VM option ...
Improperly specified VM option ...
Could not create the Java Virtual Machine
Ignoring option ...
Option ... was deprecated ...
~~~

An `Ignoring option` warning may explain a **behavioral divergence** without causing a crash. Distinguish severity from operational impact.

### 14.2. Failures triggered only when agents are attached

If a startup script combines `-javaagent`, `-agentpath`, and `-XX` tuning flags, crashes may stem from an agent lacking new-JDK support. Rather than deleting random flags, isolate layers in test environments: no agent, single agent, combined agents—then inspect logs and JNI/native crash reports.

## 15. Multi-phase migration plan

### Phase A – Discovery

1. Gather JDK versions/vendors/builds and flag lists from all processes.
2. Locate startup scripts, environment injections, Dockerfiles, Helm/Kubernetes configs, and argument files.
3. Identify owners and original tuning intent for each flag.
4. Tag flags affecting GC, memory, locking, logging, JIT, diagnostics, modules, and agents.

Expected deliverable: an inventory table mapping source, target release, and planned action.

### Phase B – Classification

1. Consult JDK release notes, migration guides, and `java` command documentation for the target version.
2. Label flags active/deprecated/obsolete/removed/unknown.
3. Separate JVM flags from system properties and application arguments.
4. Decide whether each flag still needs to exist.
5. Define metrics to evaluate the impact of removing or changing each flag.

Never treat JDK 17 documentation as authoritative for every flag on JDK 27.

### Phase C – Cleanup and replacement

Examples:

~~~text
-XX:MaxPermSize -> remove; evaluate Metaspace if required
CMS options -> remove; design GC policy for the new JDK
TraceClassLoading -> Unified Logging class+load
PrintGC* legacy options -> Unified Logging gc*
--illegal-access -> remove; fix module access or open precisely if needed
Removed option -> delete/replace before deploying
~~~

For deprecated flags still taking effect, benchmark removal or replacement; avoid altering too many knobs simultaneously when isolating regressions.

### Phase D – Smoke testing on the target JDK

- Verify flag parsing via `java -version` in the target environment.
- Start the application with its full startup command.
- Inspect warnings, stderr, and exit codes.
- Run `jcmd VM.command_line`/`VM.flags` when permitted.
- Confirm logging paths, heap caps, and active GC selection.

### Phase E – Performance comparison

Use identical workloads and resource budgets. Compare legacy JDK baselines against cleaned-up configs on the new JDK. For GC changes, monitor pauses/throughput/heap together; for JIT/locking shifts, inspect CPU, p99 latency, and warmup behavior.

### Phase F – Canary and rollback

Deploy to a small canary cohort with full observability. Before rolling back, confirm legacy binaries still run on the infrastructure and safely read/write data written by the newer version. **Rolling back a JDK does not reverse data or protocols already written by the new version.**

If an option was removed in the new JDK, do not re-introduce it via `IgnoreUnrecognizedVMOptions` and call that remediation. Retire obsolete tuning assumptions and verify results.

## 16. Practical example: a Java 8 script running on a modern JDK

Suppose an old startup script specifies:

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:MaxPermSize=256m \
  -XX:+UseConcMarkSweepGC \
  -XX:CMSInitiatingOccupancyFraction=70 \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:/var/log/orders/gc.log \
  -jar orders.jar
~~~

### 16.1. What can happen?

- `MaxPermSize` no longer bounds PermGen because PermGen was removed.
- CMS was removed, so CMS options no longer configure the active collector.
- Legacy GC logging flags may be deprecated, obsolete, or rejected depending on JDK version.
- If a flag reached expiration, the JVM may abort startup.
- If the JVM ignores selected flags and boots anyway, actual GC and log formats can diverge from prior goals.

### 16.2. Initial converted baseline

For a workload suited to G1, purely illustrating migration:

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -Xlog:gc*,safepoint=info:file=/var/log/orders/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders.jar
~~~

This is not yet a final tuned configuration. Measure memory footprint, GC pauses, CPU, and log volume; on tight cgroup limits, keeping a 2g heap can trigger OOM kills once native overhead is included.

### 16.3. Verification checklist

| Check | Purpose |
|---|---|
| `java -version` and image digest | Matches intended deployed runtime |
| `-XX:+PrintFlagsFinal` | Heap/GC flags reported accurately |
| `jcmd VM.flags` while running | Inspects effective runtime flags |
| New GC logs | Expected events and rotation work |
| Throughput/latency | Zero unacceptable regressions |
| Heap/Metaspace/RSS | Stays within container budget |
| Startup warnings | Free of obsolete/unknown flags |
| Canary rollback plan | Safe recovery if incidents strike |

Updating flags is only configuration work; operational verification delivers the migration result.

## 17. Common misconceptions

**“Java still accepts the flag, so it definitely works.”** False. Obsolete flags are accepted yet ignored with a warning.

**“Deprecated means the JVM already ignores it.”** False. In HotSpot lifecycles, deprecated flags normally still apply while warning.

**“An obsolete flag stays accepted in all future JDKs.”** False. It can progress to expired/removed and block JVM startup.

**“`-XX:+IgnoreUnrecognizedVMOptions` makes migration safe.”** False. It hides typos and destroys visibility into defunct tuning configurations.

**“`MaxPermSize` and `MaxMetaspaceSize` are just two names for the same setting.”** False. PermGen and Metaspace obey different memory management mechanics.

**“CMS flags can stay intact when switching to G1.”** False. G1 has distinct tuning mechanics; re-benchmark workloads.

**“Modern GC logging just changes `-Xloggc` to `-Xlog`.”** Insufficient. Evaluate tags, levels, decorators, rotation, and log-analysis tooling.

**“`--illegal-access=permit` still opens JDK internals on Java 17+.”** In JDK 17 it is obsolete and no longer relaxes strong encapsulation.

**“`mvn test` passes means all Java processes share one JDK.”** False. Maven launchers, forked test JVMs, app/container JVMs, and scripts can differ and receive distinct flags.

**“PrintFlagsFinal proves performance is optimized.”** False. It reports active flags, not benchmark outcomes.

**“Zero warnings means configuration is completely accurate.”** False. Valid flags may have no effect in the chosen collector/mode, or changed JDK defaults may still regress performance.

**“Newer JDKs always run better with old tuning sets.”** False. Tuning tailored for a previous workload/JDK/GC can hurt performance post-upgrade.

**“Checking the Dockerfile alone is enough.”** False. Helm values, `JAVA_TOOL_OPTIONS`, service managers, `@args-file`, and agent injectors can add runtime flags.

## 18. Checklist for JVM flags migration

- [ ] Identified source/target JDK feature/update/build releases, vendor, and JVM implementation.
- [ ] Collected startup flags from command lines, environment variables, scripts, containers, and `@args-file`s.
- [ ] Distinguished `-X`, `-XX`, `-D`, module options, agents, and application arguments.
- [ ] Classified flags as active/deprecated/obsolete/removed/unknown for the target JDK.
- [ ] Identified flags ignored at startup despite the JVM booting cleanly.
- [ ] Removed defunct PermGen options.
- [ ] Replaced or removed unsupported CMS/biased-locking flags.
- [ ] Migrated necessary GC/class tracing to Unified Logging.
- [ ] Audited JPMS `--illegal-access` flags and Security Manager policies if present.
- [ ] Audited `IgnoreUnrecognizedVMOptions` and removed unnecessary error masking.
- [ ] Verified `java -version` and `jcmd VM.command_line` on live processes.
- [ ] Checked `PrintFlagsFinal`/`VM.flags` while accounting for their limitations.
- [ ] Verified heap sizing, Metaspace, and container memory/CPU limits.
- [ ] Confirmed GC logs capture needed fields and log parsers/dashboards ingest them.
- [ ] Executed startup smoke tests capturing stderr, warnings, and exit codes.
- [ ] Measured throughput, CPU, allocations, GC, native memory, and p95/p99 on representative workloads.
- [ ] Tested canary rollouts with production-identical startup commands and container images.
- [ ] Assigned owners, rationale, and retirement plans for custom tuning flags.
- [ ] Prepared rollback plans that do not assume unverified backward data/protocol compatibility.

## 19. Recommended references

These resources document option lifecycles and changes cited as examples:

- [Oracle JDK 27 – The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): standard/extra/advanced option groups, Deprecated/Obsolete/Removed sections, and Unified Logging.
- [Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): upgrading from JDK 8 and changes across PermGen/CMS/GC flags.
- [Oracle JDK 25 – The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): example removed RTM options and current options in JDK 25.
- [JEP 122 – Remove the Permanent Generation](https://openjdk.org/jeps/122): replacing PermGen with Metaspace.
- [JEP 158 – Unified JVM Logging](https://openjdk.org/jeps/158): the `-Xlog` logging framework.
- [JEP 363 – Remove the Concurrent Mark Sweep Garbage Collector](https://openjdk.org/jeps/363): CMS removal in JDK 14.
- [JEP 374 – Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): biased locking changes in JDK 15.
- [JDK 18 Release Notes](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): obsolete status of biased-locking flags.
- [JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): `--illegal-access` behavior in JDK 17.
- [JEP 486 – Permanently Disable the Security Manager](https://openjdk.org/jeps/486): Security Manager policy in JDK 24.
- [Oracle `jcmd` command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): diagnosing processes, VM flags, and command lines.

For every flag in a project configuration, consult documentation for the **exact deployed JDK release**, vendor-specific release notes, and live runtime tests. Example lists in this lesson are not an immutable catalog across every Java release.

## 20. Conclusion

JVM flags do not share a uniform stability contract. A **deprecated** flag still applies while warning; an **obsolete** flag may be accepted yet **ignored**; an **expired/removed** flag can stop the JVM from booting. Moreover, valid flags may have no effect under the current mode/collector or sit atop shifted default values.

To upgrade the JDK safely, inventory all sources of JVM arguments, determine each flag's lifecycle on the target runtime, eliminate outdated tuning workarounds, and migrate mechanisms like CMS/PermGen/GC logging to supported alternatives. Above all, **verify what configuration the running JVM actually uses** and **measure real application impact** across GC logs, CPU, memory, throughput, and latency on representative workloads. A warning-free startup is a good sign; verified performance and operational compatibility are the true goal.
