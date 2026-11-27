# Reading Build Reports to Find Components That Increase Size or Compilation Time

## Lesson Objectives

When compiling Spring Boot into a **GraalVM Native Image**, build time and executable size can increase significantly as an application pulls in more dependencies, reachable methods, objects retained in the image heap, or packaged resources. Looking only at total build time and file size makes it hard to tell which parts are driving the cost.

Native Image provides build output and, in supported distributions, an HTML **Build Report** to analyze the binary's components and the phases of the compilation process. The report helps answer questions such as: which packages contribute the most code, which object types occupy the image heap, which resources are embedded, whether the build spends more time in analysis or compilation, and which dependencies need closer inspection.

This lesson helps you:

- Enable the Build Report and structured build output.
- Read Summary, Code Area, Image Heap, Resources, and SBOM.
- Distinguish components that increase binary size from phases that increase build time.
- Trace back the packages, classes, objects, and dependencies causing the cost.
- Choose targeted optimization changes and compare against a baseline.
- Track binary size and build time trends in CI.

## 1. Why Read the Build Report?

### 1.1. Total Size Is Not Just Application Code

A native executable can consist of several parts:

- **Code area:** machine code generated for reachable methods.
- **Image heap:** objects and data retained in the binary, including static state, metadata, and resource data.
- **Debug information:** information for debugging/profiling if generated or embedded.
- **Other data:** remaining data and structures needed for the executable.

One dependency may increase the code area because many methods become reachable. Another dependency may increase the image heap by retaining many objects or resources. Therefore, you cannot draw conclusions solely from the number of JARs or total class count.

### 1.2. Build Time Also Has Multiple Sources

Native Image performs reachability analysis, processes metadata, optimizes and compiles methods, lays out code, and creates the binary. Build time can increase because:

- Dependencies enlarge the set of reachable classes, fields, and methods.
- Reflection, proxies, or metadata expand the set of components that must be retained.
- Static initialization creates a large object graph during the build.
- The compiler has to optimize and compile many methods.
- The build machine lacks CPU or memory, increasing GC and paging.
- Debug information or the packaging/linking step adds time to artifact creation.

**Binary size and build time are related but distinct issues.** A change may reduce the code area without reducing analysis time; a slow build may be caused by insufficient CPU/RAM even when the final binary is not large.

### 1.3. Two Types of Data to Distinguish

| Source | Questions Answered | How to Use |
|---|---|---|
| Terminal build output | Which phases is the build going through, and what are the overall metrics and resources? | Find slow phases and compare across builds |
| HTML Build Report | Which components contribute to the code area, image heap, resources, and dependency inventory? | Drill down to packages, classes, object types, and resources |
| Machine-readable JSON build output | What are the structured build metrics to store and check automatically? | Track trends and set thresholds in CI |

The Build Report does not replace error logs or an application profiler. It describes the process of creating the native executable and the contents of the binary.

## 2. Enabling the Build Report and Build Output

### 2.1. Generating the Build Report with native-image

On a GraalVM distribution that supports the Build Report, add the option:

```bash
native-image --emit build-report -jar target/payment-service.jar
```

You can specify a custom report path:

```bash
native-image \
  --emit=build-report=reports/payment-service-build-report.html \
  -jar target/payment-service.jar
```

After a successful build, the HTML report path is listed in the Build artifacts section of the output. The default name typically follows `<binary-name>-build-report.html` and sits next to the binary.

**Edition note:** according to current GraalVM documentation, the HTML Build Report is not available in GraalVM Community Edition. If `--emit build-report` is unsupported, check your edition and version before concluding the build configuration is wrong. You can use terminal build output and JSON output to track the metrics provided by the toolchain.

### 2.2. Enabling via Gradle Native Build Tools

Configuration example:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("--emit=build-report")
            buildArgs.add(
                "-H:BuildOutputJSONFile=build/native/native-build-output.json"
            )
        }
    }
}
```

Task names and configuration syntax may vary by Gradle plugin version. Place build arguments in the binary configuration that the project actually uses to produce the executable.

### 2.3. Enabling via Maven Native Build Tools

Example:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--emit=build-report</buildArg>
            <buildArg>-H:BuildOutputJSONFile=target/native-build-output.json</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

If using the Spring Boot Maven plugin or a buildpack to create the native image, pass the arguments through the actual plugin/builder performing the Native Image compilation. Do not assume `native-maven-plugin` configuration automatically applies to buildpacks.

### 2.4. Checking Toolchain Options

Before putting arguments into a pipeline, confirm the version and edition:

```bash
native-image --version
native-image --help
native-image --help-extra
```

Option names, reporting capabilities, and JSON schemas can change between GraalVM versions. Use the documentation matching your project's toolchain; do not copy options verbatim from another version.

## 3. Reading the Summary Section

### 3.1. Environment

Summary typically displays build environment details, such as:

- Java and GraalVM version.
- Graal compiler configuration and optimization level.
- Target machine type/architecture.
- C compiler and version.
- Garbage collector selected for the executable.
- Features enabled by the user or framework.

This is the first section to check when comparing two reports. If the GraalVM version, target architecture, optimization level, or enabled features differ, differences in size/time may come from the environment rather than source changes.

### 3.2. Analysis Results

This section shows the points-to/reachability analysis results, typically grouped into:

- Types.
- Fields.
- Methods.
- Reachable, reflection, JNI, or loaded components depending on how the report presents them.

Large numbers may suggest the application is retaining a broad codebase, using extensive reflection metadata, or loading many libraries. However, **method count does not equal machine code size**, nor does it directly indicate the compilation time of any individual dependency.

Use these metrics to spot unusual changes between a baseline and a new build, then drill down in Code Area or inspect the relevant dependencies/metadata.

### 3.3. Image Details

The Image Details chart shows the breakdown of sections such as:

- Code area.
- Image heap.
- Debug information.
- Other data.

Pick the section taking the largest share to investigate next. If the code area is large, inspect Code Area. If the image heap is large, inspect Image Heap and Resources. If debug information is large, confirm whether the build is intentionally generating/embedding debug info.

### 3.4. Resource Usage

Summary can provide resource metrics for the build process itself:

- Time spent creating the binary.
- Peak RSS of the build process.
- CPU load.
- Garbage collection and related memory statistics.

High peak RSS combined with heavy GC can indicate the build process is under memory pressure. Low CPU load paired with a long total duration may suggest the build is constrained by memory, I/O, or waiting on other resources; cross-check with the CI environment before adding more cores.

These are metrics of the **Native Image build process**, not the RSS or GC behavior of the native application while serving requests.

Depending on the version, Summary may also include a Security Report; reports for builds using Profile-Guided Optimization (PGO) may also include a PGO Sampling Profile section. These provide supplementary information for security review or optimization profiles and do not replace drilling down into Code Area, Image Heap, and Resources when investigating size growth.

## 4. Drilling Down into Code Area to Find Code Bloating the Binary

### 4.1. What Does Code Area Contain?

Code Area describes the code compiled from reachable methods after static analysis. Build output may group origins by JAR, package, or class depending on available metadata; the Build Report lets you drill down deeper by package/class and method.

In the report, you can view a method-level breakdown, method counts, and whatever size/percentage details the report version provides. Select a package to drill into subpackages and classes; the list below stays synchronized with the chart.

### 4.2. Finding Dependencies Contributing Substantial Code

Workflow:

1. Open Code Area and inspect the origins/packages with the largest share.
2. Select a notable package to drill down.
3. Identify the classes and methods contributing the most.
4. Match the package/class against dependencies in the SBOM or the build tool's dependency tree.
5. Verify whether the application actually uses that component.

For example, a reporting library might pull in many formatters, parsers, and font support even though the service only uses one format. If most of the library's code remains reachable, check whether you can exclude unused modules, switch to a lighter dependency, or choose a minimal configuration supported by the vendor.

### 4.3. Do Not Remove a Dependency Just Because Its Share Is Large

A package with a high percentage is not necessarily bloat. It may provide core functionality or be used across many business flows.

Before removing it:

- Check callers/use cases and integration tests.
- See if the dependency is registered by framework auto-configuration.
- Determine whether an optional module or starter is pulling in unnecessary dependencies.
- Check whether reachability metadata is forcing unnecessary components to be retained.
- Rebuild and run all related native tests.

The goal is to remove what is unnecessary while preserving full production behavior.

### 4.4. Distinguishing Method Count from Code Size

A package with many small methods does not necessarily take more code area than a package with fewer, more complex methods. Reachable method count is an indicator of code scope; code area size is the result after the compiler and optimizations run.

Compare multiple builds on the same toolchain rather than applying a single method-count threshold across all applications.

## 5. Reading Image Heap to Find Objects Retained in the Binary

### 5.1. What Does Image Heap Contain?

The image heap stores objects created and retained during the Native Image build, for example:

- Static data and reachable object graphs.
- Metadata needed at runtime.
- Objects created by class initialization at build time.
- Certain `byte[]` arrays containing data, resources, or metadata.

A large object graph can inflate the binary even if the code area barely changes.

### 5.2. Finding Object Types Taking Up the Most Space

Image Heap is typically grouped by object type and provides:

- Instance count.
- Total size.
- Percentage of the image heap.

Sort by size or search to inspect notable classes. For example, if a catalog class holds hundreds of thousands of entries, or a collection stores many configuration strings, find where that object graph is created and whether it needs to live in the image heap.

### 5.3. Distinguishing Data Objects from Resources

Some resources are embedded into the image as `byte[]`. The report may display resources separately in the Resources tab while also showing the contribution of resource data in the image heap/build output.

If the image heap is large, do not look only at static collections in code. Check large resources, reflection metadata, code metadata, and the byte array categories broken down by the build output.

### 5.4. Checking Class Initialization

If a class is initialized at build time, its static initializer can build an object graph stored in the image heap. Classes holding caches, registries, locale data, or large configurations should be inspected:

- Is the data truly immutable and fixed across environments?
- Does it contain information valid only on the build machine?
- Can the data be loaded at runtime instead of storing a snapshot in the binary?
- Is the class being initialized at build time merely because another dependency references it?

Do not switch classes wholesale to runtime initialization just to shrink the heap. Changing class initialization can affect startup and compatibility; test the specific classes and usage paths carefully.

## 6. Reading Resources to Find Unintentionally Packaged Files

### 6.1. What Does the Resources Tab Show?

The Resources tab lists Java resources included in the native image, along with details such as name, module/origin, and size. The report may distinguish:

- Resources explicitly requested via metadata/configuration.
- Resources registered by the framework using API hints.
- Resources requested but not found.
- Directory resources.

The exact categories shown depend on the report version.

### 6.2. Finding Large Resources or Overly Broad Patterns

For example, an application might need only three email templates, yet metadata registers the entire `templates/**` directory. If that directory holds old templates, images, or documents, all of them can be packaged into the binary.

Check by:

1. Sorting resources by size.
2. Looking for large files or groups of resources from the same origin.
3. Seeing which metadata file or Runtime Hints registered the resource.
4. Narrowing the pattern to only the files actually needed.
5. Running native tests to verify templates/schemas can still be read.

### 6.3. Missing Resources Do Not Mean a Large Binary

A resource that is requested but does not exist is a configuration or build-input issue. It may not enlarge the binary, but it can cause the application to fail at runtime when accessing that resource.

Fix missing resources by confirming the file is generated/copied properly during the build, its name matches the case sensitivity of the target filesystem, and the pattern matches the path inside the JAR.

## 7. Using SBOM to Map Components to Dependencies

### 7.1. SBOM Shows Which Artifacts Participated in the Build

The Software Bill of Materials (SBOM) in the Build Report lists the artifacts along with identifiers and versions used to create the binary. This data is useful for:

- Finding unexpected dependencies or unanticipated versions.
- Matching origins in Code Area with the corresponding JAR/module.
- Checking transitive dependencies pulled in indirectly.
- Tying benchmark results to the exact set of dependencies built.

The SBOM does not by itself tell you how many seconds of compilation a dependency caused. Use it to trace components, then combine it with phase timings and build comparisons.

### 7.2. From Package to Dependency

When a large package appears in Code Area:

1. Note the package/class and origin shown in the report.
2. Locate the corresponding artifact in the SBOM.
3. Inspect the Maven or Gradle dependency tree to find direct/transitive dependencies.
4. See which starter or module brought that artifact in.
5. Create a test build with a single dependency/configuration change.
6. Compare the reports and rerun tests.

Do not exclude a dependency based solely on its artifact name; some packages may be shaded/relocated or contain shared classes.

## 8. Finding Phases That Increase Compilation Time

### 8.1. Reading Phases in the Build Output

Phase names and presentation can differ across GraalVM versions, but output typically shows phases such as:

| Phase | Work Performed | Signs to Watch |
|---|---|---|
| Initializing | Initializes the Native Image builder and features | Features/plugins or build environment |
| Analysis | Analyzes reachability and the object graph | Unusual jump in types, fields, or methods |
| Inlining methods | Performs build-time method inlining | Time and number of rounds reported in output |
| Compiling methods | Graal compiler compiles reachable methods to machine code | Method count and compile time |
| Laying out methods | Organizes/lays out compiled methods | Layout time |
| Creating image | Creates and writes the binary, handles linking/debug artifacts | Image creation time and artifact size |

Do not look only at total duration. Identify which phase grew compared to the baseline and which source/dependency changes landed at the same time.

### 8.2. When Analysis Is the Slow Part

Check:

- Whether a new dependency or starter increased the number of reachable types/methods.
- Whether reflection/proxy metadata is registered too broadly.
- Which feature or auto-configuration is introducing extra graphs into the build.
- Whether class initialization creates a large object graph.
- Whether a dependency/plugin needed only in one profile is being included in all variants.

Slow analysis does not necessarily mean the compiler is slow at generating machine code; this is the phase that determines the set of components eligible to enter the image.

### 8.3. When Compiling Methods Is the Slow Part

Check:

- Did the number of reachable methods increase?
- Did a dependency significantly increase the code area?
- Did the optimization level change?
- Are target machine type/architecture identical to the baseline?
- Does the build machine have sufficient CPU and memory?

Modern build output can provide additional method/code area metrics. Use Code Area to pinpoint packages contributing substantial code, but do not interpret code area share as the exact compile time of that package.

### 8.4. When Creating Image or Late Phases Are Slow

Check image heap, resources, debug information, artifact linking, and build workspace I/O. If the report shows large resources or a growing image heap, investigate Resources/Image Heap. If size is unchanged yet late phases are slow, inspect CPU, disk, linker, and build environment configuration.

### 8.5. Distinguishing CPU Limits from Memory Limits

Resource Usage helps inspect peak RSS, CPU load, and GC of the build process:

- Peak RSS near the memory limit with heavy GC can signal insufficient memory.
- High CPU load with many methods to compile can indicate a CPU-bound build.
- Low CPU load paired with long duration may require investigating I/O, memory pressure, or CI resource limits.

Increase CPU/RAM only after gathering evidence. Adding memory will not fix an overly broad dependency graph; adding CPU will not fix a build waiting on I/O.

## 9. Using JSON to Track Builds in CI

### 9.1. Exporting Machine-Readable Build Output

You can instruct the builder to produce JSON:

```bash
native-image \
  -H:BuildOutputJSONFile=build/native/native-build-output.json \
  -jar target/payment-service.jar
```

JSON is intended for automated tracking tools. Terminal output is designed for human readers and can change across versions; avoid writing scripts that parse text logs by line position or fragile regexes.

JSON is produced only when the build succeeds according to builder behavior. Save the schema matching your GraalVM version and inspect its structure before writing CI rules.

### 9.2. Tracking Meaningful Thresholds

You can track:

- Total build time.
- Peak RSS of the build process.
- CPU load and GC statistics.
- Number of reachable methods/types.
- Total binary size.
- Code area and image heap.
- Resource count/size.

For example, GraalVM documentation illustrates accessing the reachable method count in JSON via `analysis_results.methods.reachable`. Schema and field names can change; verify the actual JSON before using that path in a pipeline.

### 9.3. Setting Baseline-Relative Thresholds

Do not apply one rigid threshold across all services. Store the results of a reference build, then set maximum acceptable growth thresholds for that service.

Policy examples:

- Warn when total build time exceeds the allowed margin over baseline.
- Warn when binary size or image heap grows sharply.
- Require review when reachable method count spikes unexpectedly.
- Monitor peak RSS to prevent CI runners from hitting OOM.

Thresholds should account for variance across runners and toolchains. Use multiple builds to establish a baseline before gating the pipeline.

## 10. Report-Driven Optimization Workflow

### Step 1 — Save a Baseline

Build the same source revision with the target toolchain. Record binary size, build output, Build Report if available, JSON output, GraalVM version, build args, and runner details.

### Step 2 — Identify the Largest Contributor

Read Summary to see the breakdown across code area/image heap/debug/other. Drill down into Code Area, Image Heap, Resources, and SBOM to find notable packages, object types, resources, or dependencies.

### Step 3 — Identify the Slow Phase

Read build output and Resource Usage. Determine whether Analysis, Compiling Methods, Creating Image, or environment CPU/memory/I/O accounts for the extra time.

### Step 4 — Form a Concrete Hypothesis

For example:

- An unnecessary starter pulls in many reachable methods.
- An overly broad resource pattern packages many files.
- A class build-time initializer retains a large object graph.
- A new dependency increases analysis and compile time.
- The CI runner lacks memory, causing builder GC to spike.

### Step 5 — Change One Factor

Remove genuinely unused modules, narrow resource patterns, adjust class initialization configuration, or tune build runner resources. Change only one group of causes at a time so you know its impact.

### Step 6 — Rebuild and Compare

Use the same GraalVM version, target, optimization level, CPU/memory, and corresponding source baseline. Compare before/after reports, run full tests, and verify native behavior.

### Step 7 — Record the Decision

Document what was reduced, which metrics changed, which features were tested, and what trade-offs emerged. If size shrank while startup or runtime latency regressed, evaluate against the original goal.

## 11. Optimization Options to Use Deliberately

### 11.1. Fast Build Mode and Size Optimization

Current GraalVM versions may provide optimization levels such as:

| Option | Purpose | When to Use |
|---|---|---|
| `-Ob` | Quick build mode, reducing compilation time | During development/debugging when fast build iteration is needed |
| `-O2` | Default optimization level in current documentation | Baseline using the toolchain's default configuration |
| `-Os` | Optimizes the executable for size | Try when binary size is the primary objective |

Options and defaults depend on the GraalVM version/distribution. `-Ob` can produce a binary with different runtime characteristics from an optimized build; do not use quick build results to draw production performance conclusions. Re-measure startup, throughput, and latency whenever changing optimization levels.

### 11.2. Narrowing Reachable Code Scope

Directions to consider:

- Remove unused dependencies or modules.
- Choose smaller starters/modules if application functionality allows.
- Avoid registering reflection/proxies/resources more broadly than needed.
- Keep only necessary resources in the native image.
- Avoid build-time initialization of classes that construct large or environment-dependent object graphs.

Do not delete metadata merely to reduce method count. Removing required metadata can break the native executable on less-tested code paths.

### 11.3. Re-verifying Functionality After Optimization

After each change, run:

- Unit and integration tests.
- Spring AOT processing.
- Native compilation.
- Tests covering relevant reflection, resource, proxy, and serialization paths.
- Smoke tests on the exact target OS/CPU/container.
- Benchmarks aligned with the original objective.

A smaller binary missing a resource or runtime implementation is not a successful optimization.

## 12. Example of Reading a Report

Suppose a new build exhibits these symptoms:

| Symptom | Hypothesis to Test | Next Step |
|---|---|---|
| Code Area grows sharply after adding a reporting starter | Starter pulls in unused formatters/parsers | Drill down packages and inspect dependency tree |
| Image Heap grows, with many `byte[]` instances | Resources or static object graph grew | Open Resources and Image Heap, inspect class initialization |
| Resources tab contains many old templates | Resource registration pattern is too broad | Narrow Runtime Hints/resource configuration |
| Analysis phase slows down, reachable methods increase | Reachability graph broadened | Compare SBOM, metadata, and auto-configuration |
| Compiling Methods slows down, code area also grows | Compiler must compile more methods | Drill down Code Area and check new dependencies |
| Build process peak RSS hits runner limit | Build is under memory pressure | Review GC statistics and provision an adequate runner |
| Total build time increases while size stays nearly flat | May be due to CPU/I/O or phases not emitting extra code | Compare phase timings, CPU load, and CI environment |

These symptoms are leads for investigation, not automatic conclusions. Change one factor and rebuild to confirm the root cause.

## 13. Build Report Review Checklist

- Do GraalVM version, edition, JDK, and target architecture match the baseline?
- Are the optimization level and build arguments the same as the previous comparison?
- Does code area or image heap account for the largest share?
- Which packages/classes contribute the most methods or code?
- Which object types occupy the most image heap?
- Are there large resources, stale resources, or overly broad patterns?
- Are there missing resources that need fixing?
- Does the SBOM contain new dependencies or unexpected versions?
- Is Analysis or Compiling Methods the phase taking longer?
- Do peak RSS, CPU load, and GC indicate an under-resourced runner?
- Do optimization changes preserve required reflection, resources, proxies, and serialization?
- Have native tests and benchmarks been re-run after optimization?

### Self-Check Questions

1. How do Code Area and Image Heap differ?
2. Why does an increase in reachable method count not mean the code area grows in the same proportion?
3. What kinds of issues does the Resources tab help uncover?
4. How does the SBOM support dependency tracing, and why does it not directly tell you how many seconds each library took to compile?
5. If Analysis is slow while Compiling Methods does not increase, what should you check?
6. What do the build process's peak RSS and CPU load reflect?
7. Why shouldn't you parse text build output to enforce CI rules?
8. When should you try `-Ob` or `-Os`, and which metrics must you re-measure?

## References

- [GraalVM Native Image Build Report](https://www.graalvm.org/latest/reference-manual/native-image/overview/build-report/)
- [GraalVM Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [GraalVM Native Image Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/)

**Key takeaway:** use Summary to identify the largest sections and build environment; Code Area to trace methods/packages; Image Heap and Resources to find objects/resources inflating the binary; SBOM to match dependencies; and build output plus JSON to find slow phases and track CI trends. Optimize around a specific hypothesis, keep a consistent baseline, and re-verify native functionality after every change.
