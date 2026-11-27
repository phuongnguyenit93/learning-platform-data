# Required Build Arguments to Enable Selected Observability Capabilities

## 1. Why Must You Choose Build Arguments for Observability?

A native executable is produced at build time from the classes, metadata, and features that GraalVM Native Image is instructed to support. Several observability capabilities—such as debug symbols, build reports, Java Flight Recorder (JFR), heap dumps, or JMX—may need to be enabled explicitly during the build. Without enabling the right capabilities, operations teams may lack critical data during incident investigations even while the application logs normally and exposes health endpoints.

In the **SPRING_BOOT_NATIVE_IMAGE** module, observability spans multiple layers: Spring Boot application logs and metrics, distributed traces, native process diagnostics, and data for analyzing the Native Image build itself. Each layer has its own mechanism. Build arguments only enable the required executable or compiler features; they do not automatically configure all of Micrometer, OpenTelemetry, or your monitoring backend.

This lesson helps you choose build arguments based on operational needs, distinguish build-time diagnostics from runtime monitoring, configure Maven/Gradle, and verify that features are actually present in the released binary.

## 2. Classifying Observability Capabilities

| Need | Example | When |
|---|---|---|
| Build diagnostics | Build report, analysis diagnostics | When the Native Image compiler runs |
| Debug native executable | Debug symbols, source/line information | Build and process investigation |
| Clearer stack traces | Reporting exception stack traces | Runtime |
| Application monitoring | Actuator, Micrometer metrics | Runtime |
| Distributed tracing | OpenTelemetry/Micrometer Tracing | Runtime |
| Profiling/flight recording | JFR if supported by runtime and build | Runtime |
| Memory investigation | Heap dump if feature is enabled and supported | Runtime |
| Remote admin/monitoring | JMX server/client if enabled | Runtime |

Do not enable every feature by default. Choose based on the operational questions you need to answer, data sensitivity, and overhead cost.

## 3. Build Arguments and Runtime Configuration Are Different

Build arguments are passed to the Native Image compiler and affect the generated executable. Runtime options/environment variables are passed when executing the binary. Spring application configuration is yet another layer.

For example:

- `-g` requests generating debug information in the executable.
- `--enable-monitoring=...` requests enabling monitoring capabilities supported by the Native Image version.
- `--emit=...` requests the compiler to emit supported report/diagnostic artifacts.
- `--logging.level...` is application logging configuration, not a Native Image build argument.
- `management.endpoints.web.exposure.include` controls Actuator endpoints at runtime, not a compiler option.

An already-built executable missing a required capability may need to be rebuilt to enable that capability. Changing environment variables at runtime cannot add debug symbols or monitoring code that was excluded from the binary.

## 4. Generating Debug Information with -g

Native Image supports the option:

```bash
native-image -g -o orders-service ...
```

`-g` requests generating debug information for the executable. Debug information helps debuggers and native binary analysis tools map machine addresses back to symbols/source locations when the corresponding build information is available.

Debug symbols are useful when:

- Investigating crashes or native stack traces.
- Using native-level debuggers/profilers.
- Analyzing core dumps.
- Mapping native frames back to functions/source lines when supported by the toolchain.

Debug information can enlarge the artifact or produce separate symbol files depending on the platform/toolchain. You can strip symbols from the executable and store them in a secure artifact store following OS/build pipeline practices.

Do not push symbol files or debug packages to public registries if they expose unnecessary source/path details. Keep symbols tied to the exact commit and binary digest for accurate analysis.

## 5. Exception Stack Traces

Native Image provides the option:

```bash
native-image -H:+ReportExceptionStackTraces ...
```

This option instructs Native Image to report more detailed stack traces for exceptions in supported scenarios. Option names and support levels may depend on the GraalVM version; check `native-image --help` or the documentation for your exact release before adding it to the build.

Stack traces help identify whether an exception originated in application code, framework code, or a dependency. However, they do not replace debug symbols for native debuggers, nor do they guarantee every frame has a source line.

For production, consider what information stack traces may reveal about packages, classes, and internal structure. Logs must be governed by access controls, retention, and masking per system policy.

## 6. Native Image Build Reports and Diagnostics

Build reports help clarify how the compiler analyzed and produced the executable. Depending on the GraalVM release, you can request a report with an option like:

```bash
native-image --emit=build-report ...
```

Some releases/plugins use different flags or output formats for reports. Check the documentation for your exact GraalVM version and confirm the report file is created in the expected location. Do not assume every Native Image version supports the same report types or formats.

A build report can help investigate:

- Which parts contribute most to image size.
- Reachability analysis and which code groups were included.
- Time/cost spent across build phases.
- Runtime components or metadata affecting the artifact.

A build report is compiler data, not a runtime dashboard. It does not directly tell you request latency, error rates, or the RSS of a running production process.

## 7. Enabling Monitoring Features Supported by Native Image

Some GraalVM Native Image versions provide an option such as:

```bash
native-image --enable-monitoring=jfr,heapdump,jmxserver ...
```

The example illustrates requested capabilities; valid names, edition support, and platform limits vary across GraalVM releases. Some versions may support choices such as JFR, heap dump, JMX server/client, or other capability groups. Always verify the list against the documentation and `native-image --help` of your actual toolchain.

Enable only the capabilities you need. JFR serves event recording/profiling; heap dumps aid object memory analysis; JMX lets admin tools access MBeans if the runtime feature and network policy allow it.

Do not treat adding the `--enable-monitoring` flag as sufficient on its own. Verify that the compiler accepts the option, the runtime actually provides the feature, and the container has the required tools/access paths.

## 8. JFR: Event Recording and Profiling

Java Flight Recorder (JFR) can provide data on JVM/runtime activity such as allocations, GC, threads, locks, and application events depending on configuration. Native Image supports JFR in certain GraalVM versions and configurations, though the event set and semantics are not necessarily identical to HotSpot JVM.

If choosing JFR:

1. Verify that your GraalVM distribution/version supports JFR for Native Image.
2. Enable the corresponding monitoring feature at build time per documentation.
3. Check how to start recordings when running the executable.
4. Determine the recording storage location and capacity limits.
5. Protect recording files because they may contain sensitive data.
6. Test reading recordings with a tool compatible with the version that created them.

Do not assume JFR is enabled simply because the application uses Micrometer or has a JFR configuration file. Run a test recording and verify the file contains the expected events.

## 9. Heap Dumps and Memory Investigation

Heap dumps can be useful when analyzing object graphs, retention, and memory distribution. Native Image provides a heap dump mechanism in supported versions/features; capabilities and trigger commands depend on the release.

Before enabling:

- Verify the `heapdump` option is supported.
- Identify an output path with write permissions and sufficient capacity.
- Set filesystem/ephemeral storage limits.
- Control who can retrieve and read dumps.
- Test generating a dump in staging rather than waiting for the first production incident.

Heap dumps can contain payloads, tokens, user information, or business data. Treat them as sensitive data: encrypt at rest/in transit, restrict access, and delete according to retention policy.

Nor should Native Image heap dumps be assumed to have the exact same format, analysis tools, or level of detail as HotSpot heap dumps. Use tools supported by your GraalVM version.

## 10. JMX and the Management Surface

If JMX server/client is enabled in a native executable, the application can expose or connect to MBeans depending on supported capabilities. JMX is a management interface, so network exposure must be controlled.

Do not expose JMX ports directly to the internet. Prefer internal networks, proper authentication/authorization, TLS where appropriate, and restricted connection sources. If the platform does not need JMX, do not enable it merely because the option exists.

JMX monitoring also does not replace metrics endpoints with stable schemas for Prometheus/Kubernetes systems. Choose the mechanism suited to the operational tooling you use.

## 11. Actuator and Micrometer Are Not Enabled by Native Image Monitoring Flags

Spring Boot Actuator provides endpoints such as health, info, metrics, and prometheus depending on dependencies and configuration. Micrometer collects application metrics and exports them through the appropriate registry.

Example configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
```

You must add the corresponding Actuator and registry dependencies, such as the Prometheus registry if you want to expose the Prometheus endpoint. Do not merely add YAML and expect the endpoint to appear automatically.

The Native Image build must ensure Actuator/Micrometer dependencies and metadata are handled by Spring Boot AOT/native support. Build flags such as `--enable-monitoring=jfr` do not replace `micrometer-registry-prometheus`, and the Prometheus registry does not automatically enable JFR.

## 12. Distributed Tracing and OpenTelemetry

Distributed tracing helps track requests across multiple services. Spring Boot can integrate Micrometer Tracing and appropriate exporters/bridges; OpenTelemetry agents/SDKs also have their own integration paths.

Distinguish between:

- Build-time native metadata for tracing libraries.
- Runtime exporter/endpoint, service name, and sampling configuration.
- Propagation headers between services.
- Trace-receiving backends such as an OTLP collector.

Runtime configuration can specify exporter endpoints and sampling ratios, but property names depend on the specific stack/version. Do not hardcode endpoints/credentials into the binary.

Native Image compiler flags do not automatically generate trace spans in application code. Verify instrumentation, context propagation, and exporters with integration tests on the native executable.

## 13. Configuring Arguments in Gradle

With the GraalVM Native Build Tools Gradle plugin, build arguments are typically declared on the binary:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("-g")
            buildArgs.add("-H:+ReportExceptionStackTraces")
            buildArgs.add("--enable-monitoring=jfr")
            buildArgs.add("--emit=build-report")
        }
    }
}
```

This is an illustrative example. Not every GraalVM version supports all options above; some options may change, require a specific edition, or be incompatible with a target. Keep only arguments verified with your actual toolchain.

You can separate argument groups by purpose and build profile, while avoiding accidentally applying experimental debug/monitoring configurations to all production builds. Use explicit Gradle tasks/configurations and log build arguments for reproducibility.

## 14. Configuring Arguments in Maven

With the Native Maven Plugin, build arguments are typically placed in the plugin configuration:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-g</buildArg>
            <buildArg>-H:+ReportExceptionStackTraces</buildArg>
            <buildArg>--enable-monitoring=jfr</buildArg>
            <buildArg>--emit=build-report</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

This is an illustrative configuration showing the plugin structure; schema, version, and argument passing may vary. Confirm the plugin version in your POM and inspect compiler logs to verify arguments were passed.

Do not copy a configuration verbatim into your project without checking the options. An invalid argument can fail the native build; an accepted option whose capability is unused will not produce the desired observability either.

## 15. Separating Build Profiles for Diagnostics and Production

You can organize configurations into two groups:

| Group | Goal | Example |
|---|---|---|
| Diagnostic build | Error investigation, profiling, build reports | Debug symbols, stack traces, reports, JFR |
| Production build | Enable only features needed for regular operations | Policy-compliant exception details, actively used monitoring features |

Not every diagnostic option must be turned off in production. For instance, debug symbols can be stored separately in an artifact store to aid crash analysis without broad distribution. JFR can be enabled if operations require it and overhead has been evaluated.

Decisions should be grounded in operations: who collects the data, where it is stored, how long it is retained, and who has access.

## 16. Verifying Options Before Adding Them to the Pipeline

Each GraalVM version can change options, capabilities, and limits. Before committing build arguments:

```bash
native-image --version
native-image --help
native-image --expert-options
```

Use `--expert-options` to inspect advanced options if provided by your version; do not treat every expert option as a stable production API. Read the documentation for the same version, checking the edition and target OS/architecture.

After building:

- Confirm the command line/logs contain the arguments.
- Confirm reports or debug artifacts were generated.
- Test the monitoring feature from the executable.
- Check output paths and file permissions.
- Measure binary size and RSS.
- Record the toolchain version alongside the artifact digest.

If an option is deprecated or renamed, update according to current documentation instead of forcing legacy syntax.

## 17. Security and Operational Cost of Observability

Observability increases diagnostic capability but also carries costs:

- Debug symbols increase artifact size or create additional symbol files.
- JFR/profiling can add CPU, memory, and I/O overhead.
- Heap dumps require significant disk space and may contain sensitive data.
- JMX opens an additional administrative/network surface.
- Detailed stack traces can expose internal structure.
- Build reports can expose class names, dependencies, and build paths.

Define retention, access control, encryption, and deletion procedures. Do not broadly enable management endpoints or JMX just for debugging convenience. Use sampling and bounded recording durations where appropriate.

## 18. Diagnosing When a Feature Does Not Work

| Symptom | Possible cause | Check |
|---|---|---|
| No debug symbols | Missing `-g` or toolchain did not emit expected output | Check build command and binary/symbol files |
| Stack traces lack detail | Appropriate option not enabled or info optimized/stripped | Check version, build flags, and runtime traces |
| No build report | `--emit` unsupported or different output path | Check help/logs and report artifacts |
| JFR fails to start | Monitoring feature not enabled or different runtime syntax | Check version docs and recording command |
| Heap dump fails | Capability not enabled, missing permissions, or disk space | Check build options, path, permissions, and quota |
| JMX fails to connect | Server/client not enabled, wrong port/network/auth | Check listeners and network policies |
| Actuator has no metrics | Missing dependency/registry or endpoint not exposed | Check Spring configuration |
| Traces do not reach backend | Wrong exporter/endpoint/propagation | Check runtime config and collector connectivity |

Do not treat a "build successful" log as proof that every monitoring feature works. Each capability requires its own verification.

## 19. Lab: Choosing Observability for a Native Order API

**Scenario:** Order API needs crash diagnostics, build reports when investigating image size, continuous Prometheus metrics, and JFR only when profiling is requested.

**Step 1 — Identify requirements.** Categorize build reports, debug symbols, stack traces, Actuator/Micrometer, and JFR by when they are used.

**Step 2 — Pin the toolchain.** Record the GraalVM distribution/version, JDK, Native Build Tools, and Spring Boot version.

**Step 3 — Configure the diagnostic build.** Test `-g`, stack trace options, and build report options supported by your version; store outputs separately.

**Step 4 — Configure runtime metrics.** Add Actuator and the appropriate Prometheus registry; expose the endpoint over an internal network.

**Step 5 — Enable JFR when needed.** Verify the monitoring option, run a short recording on the native executable, and open the file with a compatible tool.

**Step 6 — Check security.** Confirm JMX/Actuator are not exposed unintentionally; restrict read access to recordings, dumps, and build reports.

**Step 7 — Measure overhead.** Compare startup, RSS, binary size, and CPU with capabilities enabled/disabled under the same workload.

**Step 8 — Standardize the pipeline.** Separate diagnostic builds and release builds as needed, storing build arguments/toolchain versions alongside artifacts.

Completion criteria: each build argument has a documented purpose and proof of operation; application metrics are configured separately; diagnostic artifacts are stored securely; and costs and limitations are recorded.

## 20. Conclusion

Build arguments can enable important GraalVM Native Image observability capabilities such as debug information, exception stack traces, build reports, and version-supported monitoring features. These features serve distinct goals and must be verified on the actual executable.

With Spring Boot Native Image, keep compiler diagnostics separate from Actuator/Micrometer and distributed tracing, pin GraalVM/Native Build Tools versions, enable only needed capabilities, verify outputs, and evaluate overhead/security. A good observability setup makes clear what data is produced, how it is collected, where it is stored, and who is authorized to access it.
