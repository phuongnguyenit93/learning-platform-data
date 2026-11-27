# Native Image Tracing Agent Observes Dynamic Access While Running on the JVM

When compiling Spring Boot into a **GraalVM Native Image**, certain operations performed dynamically at runtime may not be fully recognized by static analysis. Examples include reflection looking up constructors or methods by name, reading files from the classpath, creating dynamic proxies, or invoking JNI. If metadata is missing, the application may build successfully yet fail when a specific request or business branch runs on the native executable.

The **Native Image Tracing Agent** helps investigate this issue by attaching an agent to a process running on the JVM. The agent observes the dynamic accesses that actually occur, then generates metadata for Native Image to use during the build. Within the **`SPRING_BOOT_NATIVE_IMAGE`** module (compiling Spring Boot with Spring AOT, evaluating startup/memory, compatibility testing, and container packaging), this lesson guides you through running the agent, generating workload coverage, reading/filtering metadata, integrating with Maven/Gradle, and verifying results on a native executable.

> **Key point:** the tracing agent records what happened during the observed run. It does not automatically discover every code path, does not prove the application is fully compatible, and does not replace hints already provided by Spring AOT or libraries.

## 1. Learning Objectives

After this lesson, you can:

- Explain why Native Image needs metadata for reflection, resources, proxies, and JNI.
- Attach the tracing agent to a Spring Boot application running on the JVM.
- Choose between running the application directly and running a test suite with the agent.
- Design workloads to exercise business branches that involve dynamic access.
- Understand `config-output-dir`, `config-merge-dir`, `trace-output`, and how to save results.
- Distinguish between a caller filter and an access filter.
- Review, merge, and place metadata into the proper location in source.
- Use the agent with Maven Native Build Tools or Gradle Native Build Tools.
- Verify metadata through a native build and native integration tests.

## 2. Why Do You Need the Tracing Agent?

Native Image performs reachability analysis at build time. The builder can see many ordinary Java calls through bytecode, but it does not always know the exact target of a dynamic operation.

~~~java
String implementationName = settings.getImplementationClass();
Class<?> type = Class.forName(implementationName);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

The class name and constructor are selected from configuration at runtime. Static analysis cannot necessarily infer every value that might appear in `implementationName`.

| Category | Examples | Metadata Possibly Needed |
|---|---|---|
| Reflection | `Class.forName`, `getDeclaredMethod`, constructor invocation | Class, constructor, field, method, and access permissions |
| Resource | `Class.getResource`, `ClassLoader.getResource`, reading files by name | Resource pattern or resource bundle |
| Dynamic proxy | `Proxy.newProxyInstance` | List of proxy interfaces |
| JNI | Java calling a native method or native code calling back into Java | JNI classes/methods/fields |
| Serialization | Framework reading/writing objects via reflection | Appropriate reflection/serialization metadata |

Spring AOT and Native Image-compatible libraries can contribute many hints themselves. The Tracing Agent is useful when a library or pattern is not recognized by Spring, or when you need to find a specific missing member.

## 3. What Does the Agent Observe and What Does It Not?

The agent attaches to a **JVM process**. While the application runs, it observes the dynamic accesses performed by the process. When the JVM exits, the agent writes metadata to the configuration directory.

~~~mermaid
flowchart TD
    A["Spring Boot application + dependencies"] --> B["Run on GraalVM JDK/JVM"]
    B --> C["Tracing Agent observes dynamic access"]
    C --> D["Reflection / resources / proxies / JNI"]
    D --> E["Metadata JSON"]
    E --> F["Review and filter metadata"]
    F --> G["META-INF/native-image"]
    G --> H["Native Image build"]
    H --> I["Native executable"]
    I --> J["Native integration tests"]
~~~

The agent can observe operations that occur during the run with the agent attached, but it has limitations:

- If a code branch is not executed, the agent cannot record accesses that exist only in that branch.
- Tests may perform accesses for JUnit, Mockito, logging, or the test framework that production does not need.
- A single test dataset does not represent all inputs, configurations, tenants, or system states.
- The agent records runtime behavior; it does not prove that the operation is business-correct or safe.
- Generated metadata may be broader than necessary, duplicated, or contain test-only entries.

Treat agent-generated metadata as **evidence to review**, not configuration files to accept automatically.

## 4. Preparing the Environment

Before running the agent:

1. Install a GraalVM JDK compatible with the Native Image version you will use to build.
2. Check `JAVA_HOME`, `java -version`, and `native-image --version`.
3. Build the JVM application successfully first.
4. If using Spring AOT, generate AOT output according to the project configuration.
5. Prepare data/test accounts to invoke the business flows you want to observe.
6. Choose a new, dedicated output directory for the agent run.

The agent is typically bundled with the GraalVM JDK. You can attach it using `-agentlib:native-image-agent=...`. If using another JVM that supports JVMTI, the GraalVM documentation describes loading the agent library by absolute path via `-agentpath`; in Spring Boot practice, using the GraalVM JDK avoids mismatches in agent binaries and versions.

## 5. Running the Application Directly with the Agent

This is the right approach when you want to investigate a specific library or request flow not yet covered by the current test suite.

For a Spring Boot application processed with AOT and packaged as a JAR:

~~~bash
java -Dspring.aot.enabled=true -agentlib:native-image-agent=config-output-dir=build/native/agent-output -jar build/libs/orders-service.jar
~~~

With Maven, the JAR is usually under `target/`; with Gradle, it is usually under `build/libs/`. Replace this with your project's actual artifact name.

Notes:

- `-agentlib` must appear before `-jar`, the main class name, or application arguments.
- `-Dspring.aot.enabled=true` enables AOT optimizations when running a JAR that already has AOT assets; use this only when the application was built with AOT.
- `config-output-dir` is the directory where the agent writes metadata. Use a fresh directory, and do not accidentally point to a source directory containing already-reviewed metadata.
- The agent writes metadata when the JVM exits. Stop the application using a controlled shutdown so the agent finishes writing files.

After the application starts, send requests or perform actions to walk through the code paths you want to investigate:

- Sign in and refresh tokens.
- Create, read, update, and delete data.
- Upload/download files.
- Call partner APIs via WebClient/RestClient.
- Run background tasks or message listeners.
- Serialize/deserialize DTOs, records, enums, and subtypes.
- Read templates, schemas, certificates, or resources by name.

Once you have exercised enough workload, stop the application (for example, `Ctrl+C`), then inspect the `build/native/agent-output` directory.

### Periodic Agent Output

For long-running processes, you can use:

~~~bash
java -agentlib:native-image-agent=config-output-dir=build/native/agent-output,config-write-period-secs=300,config-write-initial-delay-secs=5 -jar build/libs/orders-service.jar
~~~

In this example, the agent writes metadata periodically every 300 seconds, starting after 5 seconds. For a short test run, writing output when the JVM exits is usually simpler.

## 6. Running the Test Suite with the Agent

Running tests with the agent creates a repeatable workflow: whenever dependencies or hints change, you can rerun the same group of tests and compare metadata.

However, the agent also observes test infrastructure activity. The output may include reflection/resource/proxy entries solely for JUnit, Mockito, assertion libraries, or the test framework. Do not put raw test output straight into production without filtering.

A useful test suite should cover:

- Happy paths and expected errors.
- Configuration toggle branches (enabled/disabled).
- Various DTO types and subtypes.
- Rarely called endpoints or message handlers.
- Different file formats and resources.
- External integration flows that use reflection/proxies.

If tests only run a smoke test that starts the context, the collected metadata may be minimal even if the application has many other dynamic code paths.

## 7. Choosing the Output Mode

The agent provides the following main output options:

| Option | Behavior | When to Use |
|---|---|---|
| `config-output-dir=DIR` | Writes a new metadata set to the output directory | Starting a new collection run, separating outputs by scenario |
| `config-merge-dir=DIR` | Merges new accesses into an existing metadata set | Collecting additional coverage from another scenario |
| `trace-output=FILE` | Writes a detailed trace of observed accesses | Deeply investigating individual dynamic accesses |

Example of running two independent scenarios:

~~~bash
java -agentlib:native-image-agent=config-output-dir=build/native/agent-rest -jar app.jar
java -agentlib:native-image-agent=config-output-dir=build/native/agent-messaging -jar app.jar
~~~

You can merge the two directories after review:

~~~bash
native-image-utils generate --input-dir=build/native/agent-rest --input-dir=build/native/agent-messaging --output-dir=build/native/agent-merged
~~~

Or run the next execution with `config-merge-dir` to add onto existing output:

~~~bash
java -agentlib:native-image-agent=config-merge-dir=build/native/agent-merged -jar app.jar
~~~

Do not let multiple concurrent processes write to the same `config-output-dir`. If multiple processes must run simultaneously, give each process its own output directory, then merge using `native-image-utils`.

### Recording a Detailed Trace

~~~bash
java -agentlib:native-image-agent=trace-output=build/native/trace.json -jar build/libs/orders-service.jar
~~~

After the process exits, convert the trace into metadata:

~~~bash
native-image-utils generate --trace-input=build/native/trace.json --output-dir=build/native/trace-config
~~~

A trace can be very large and contain much more detail than the final configuration set. Use it only when deep investigation is needed.

## 8. Understanding the Generated Metadata Files

Depending on the GraalVM version, Native Build Tools, and metadata format, the agent may generate `reachability-metadata.json` or separate legacy JSON files per configuration type.

| File/Group | Contents |
|---|---|
| `reachability-metadata.json` | Modern unified format for multiple kinds of reachability metadata |
| `reflect-config.json` | Classes, constructors, methods, and fields requiring reflection |
| `resource-config.json` | Resources and resource bundles |
| `proxy-config.json` | Interface lists used to create dynamic proxies |
| `jni-config.json` | Classes/members accessed via JNI |
| `serialization-config.json` | Data types requiring serialization support per Native Image metadata |

Not every version generates all of these files. Inspect the actual output produced by the agent you are using, and do not create empty files just to complete the list.

Example of legacy reflection metadata:

~~~json
[
  {
    "name": "com.example.plugins.CsvExportPlugin",
    "allDeclaredConstructors": true,
    "methods": [
      {
        "name": "export",
        "parameterTypes": ["com.example.ExportRequest"]
      }
    ]
  }
]
~~~

The snippet above only illustrates the structure; files generated by the agent may include additional member flags, conditions, or another format. Do not copy this example into your project without verifying actual classes/members.

Newer metadata may contain conditions such as `typeReached`, meaning an entry only takes effect when a specific type is reached. Conditions help reduce globally applied metadata. Do not remove or rewrite tool-generated conditions merely to make the file shorter.

## 9. Increasing Workload Coverage

The agent only knows about behavior that ran. Therefore, metadata quality depends directly on workload quality.

1. List all endpoints, message handlers, scheduled tasks, and integration flows.
2. List the data types or resources accessed dynamically in each flow.
3. Run the agent with representative data for each group.
4. Re-run with important configuration branches.
5. Compare metadata across runs.
6. Cross-check new entries against source code or the library performing the access.
7. Run native tests after adding the metadata to the build.

| Flow | Data to Exercise | Dynamic Access to Observe |
|---|---|---|
| REST order | DTOs, nested records, enums | Jackson reflection/binding |
| CSV upload | Sample files, parser | Resources and reflection if used by the parser |
| OAuth callback | Provider, keys/certificates | Resources, proxies, or reflection |
| Message consumer | Multiple event subtypes | Serialization/deserialization |
| Packaged internal plugin | Provider classes | Service discovery, reflection if needed |
| Scheduled report | Templates and locales | Resource bundles, template access |

Coverage is not just test count. Make sure tests actually invoke the branches that contain dynamic access.

## 10. Filtering Output: Caller Filter and Access Filter

The agent has two main filter types:

- **Caller filter:** which class initiated the access? Filters based on the class making the dynamic call.
- **Access filter:** which class or member is the access targeting? Filters based on the target of the access and can exclude the class along with its members from metadata.

### Caller Filter

A caller filter is useful for excluding accesses originating from test infrastructure or packages not belonging to the application being collected.

Example `caller-filter.json`:

~~~json
{
  "rules": [
    {"includeClasses": "com.example.orders.**"},
    {"excludeClasses": "com.example.orders.test.**"}
  ]
}
~~~

~~~bash
java -agentlib:native-image-agent=caller-filter-file=caller-filter.json,config-output-dir=build/native/agent-filtered -jar build/libs/orders-service.jar
~~~

Rules are evaluated in order; later rules can override earlier decisions. The `.*` pattern matches classes directly in a package; `.**` includes subpackages at all levels.

### Access Filter

An access filter is used to exclude targets you do not want in metadata. For example, excluding an internal test-framework package:

~~~json
{
  "rules": [
    {"excludeClasses": "org.example.testinfra.**"}
  ]
}
~~~

~~~bash
java -agentlib:native-image-agent=access-filter-file=access-filter.json,config-output-dir=build/native/agent-filtered -jar build/libs/orders-service.jar
~~~

You can combine caller filters and access filters:

~~~bash
java -agentlib:native-image-agent=caller-filter-file=caller-filter.json,access-filter-file=access-filter.json,config-output-dir=build/native/agent-filtered -jar build/libs/orders-service.jar
~~~

### Keep Built-in Filters

The agent has built-in filters to skip many accesses performed by the JVM and parts of the JDK that Native Image already supports. Disabling them with `no-builtin-caller-filter` or `no-builtin-heuristic-filter` can produce huge, less useful output. Only use those in experimental investigations when there is a clear reason; do not use that output as default production metadata.

Overly broad filters can also accidentally drop application accesses. After adding filters, compare the before/after output and run native tests covering the relevant flows.

## 11. Integrating with Spring Boot

Spring Boot AOT typically generates most of the required hints automatically. Therefore, the agent should be used to **find missing pieces** or confirm a specific library/pattern, not to replace Spring AOT.

Run a JAR that already has AOT assets with the agent:

~~~bash
java -Dspring.aot.enabled=true -agentlib:native-image-agent=config-output-dir=build/native/agent-output -jar target/orders-service.jar
~~~

After the app starts, invoke the flows you want to check and then shut down the process normally. Review the metadata and keep only the entries that are still needed.

If you run a test suite, the output may contain metadata for the test engine, mocking, assertions, or test server. You can:

- Run the application directly to focus on production behavior.
- Use caller/access filters to exclude unwanted targets/callers.
- Use Native Build Tools conditional mode if the plugin is configured for it.
- Copy test output into `src/test/resources/META-INF/native-image` when metadata is only needed for native tests.
- Only place metadata into `src/main/resources/META-INF/native-image` after verifying it is required for production.

## 12. Maven Native Build Tools

The Native Build Tools Maven plugin supports attaching the tracing agent to tests or application runs. The agent is disabled by default; you can enable it via the command line with `-Dagent=true` if the project already configures the native profile/plugin.

### Collecting from the Test Suite

~~~bash
./mvnw -Pnative -Dagent=true test
~~~

The agent is attached to Maven Surefire test execution; default output is typically at:

~~~text
target/native/agent-output/test/
~~~

If `metadataCopy` is configured in the plugin, you can copy output after tests run:

~~~bash
./mvnw -Pnative -Dagent=true test native:metadata-copy
~~~

Abbreviated configuration example to copy test metadata into test resources:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <agent>
            <enabled>true</enabled>
            <metadataCopy>
                <disabledStages>
                    <stage>main</stage>
                </disabledStages>
                <merge>true</merge>
                <outputDirectory>src/test/resources/META-INF/native-image</outputDirectory>
            </metadataCopy>
        </agent>
    </configuration>
</plugin>
~~~

`disabledStages` in this example skips metadata from the `main` stage and copies only test output. If metadata is confirmed to be needed for the production application, choose an output directory under `src/main/resources/META-INF/native-image` and do not unintentionally exclude the `main` stage.

### Collecting While Running the Application

Collecting from the main application requires a separately forked Java process. The Native Build Tools Maven plugin can coordinate with `exec-maven-plugin`; the configured execution ID must match `agentExecutionId`.

Example when the project declares execution `java-agent`:

~~~bash
./mvnw -Pnative -Dagent=true -DskipTests -DskipNativeBuild=true package exec:exec@java-agent
~~~

Main output is typically located under:

~~~text
target/native/agent-output/main/
~~~

Fork configuration details depend on the project's main class and classpath. Use the example from the Native Build Tools documentation as a template and adjust the execution ID, main class, and working directory.

Once production metadata is ready, rebuild the native executable and run integration tests:

~~~bash
./mvnw -Pnative -DskipTests package
~~~

## 13. Gradle Native Build Tools

With Gradle, the tracing agent is configured inside the `graalvmNative.agent` block once the `org.graalvm.buildtools.native` plugin is applied.

Minimal configuration example:

~~~groovy
graalvmNative {
    agent {
        enabled = true
        defaultMode = "standard"
        metadataCopy {
            inputTaskNames.add("test")
            outputDirectories.add("src/test/resources/META-INF/native-image")
            mergeWithExisting = true
        }
    }
}
~~~

Collecting metadata during tests:

~~~bash
./gradlew -Pagent=standard nativeTest
~~~

Copying metadata from the test task:

~~~bash
./gradlew metadataCopy --task test
~~~

If using `nativeRun` or `run` to collect metadata from the application:

~~~bash
./gradlew metadataCopy --task run
~~~

The output directory in `metadataCopy` should be chosen according to its purpose:

- `src/test/resources/META-INF/native-image`: metadata solely for native tests.
- `src/main/resources/META-INF/native-image`: reviewed metadata required for the production native build.

Task names and DSL options may vary by Native Build Tools version. Check the resolved plugin version and matching documentation; do not copy configuration from another plugin version without confirming.

## 14. Including Metadata in the Native Build

For reviewed metadata, the standard resource location in an application is usually:

~~~text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── orders-service/
                └── reachability-metadata.json
~~~

The `META-INF/native-image` directory (or subdirectories underneath it) is discovered by Native Image on the classpath/module path. Legacy per-type metadata files can also be recognized according to the rules of the corresponding GraalVM version.

If metadata is outside the classpath, you can pass the directory directly to Native Image with:

~~~bash
native-image -H:ConfigurationFileDirectories=build/native/agent-output -jar target/orders-service.jar
~~~

When using the Maven/Gradle plugin, metadata on the classpath is usually detected automatically; metadata outside the classpath requires configuring the corresponding build argument. Avoid adding the same metadata set through multiple different sources unnecessarily, as that can make tracing harder.

## 15. Reviewing Metadata Before Committing

Before committing metadata into source:

1. **Identify the source:** which application code, framework, test, or library produced this entry?
2. **Verify the target:** does the class/member/resource exist in the current dependency version?
3. **Check scope:** can you register one specific constructor/method instead of all members?
4. **Check conditions:** is there a `typeReached` condition or other condition that must be preserved?
5. **Deduplicate:** merge duplicate entries according to proper semantics, rather than just deleting duplicate text lines.
6. **Check environment assumptions:** do resource paths or class names depend on OS or profile?
7. **Check test-only entries:** metadata used only by tests belongs in test resources.
8. **Check dependency versions:** upgrading a library version can make old metadata outdated.

The narrower and more clearly sourced your metadata is, the easier it is to maintain. Avoid enabling full reflection on every class just to make one test pass.

## 16. The Agent Does Not Replace the Reachability Metadata Repository

Many third-party libraries already provide reachability metadata in the GraalVM Reachability Metadata Repository. Native Build Tools can automatically download metadata matching your dependency versions at build time.

Check in this order:

1. Does Spring AOT or framework integration already provide the hints?
2. Does the library have official metadata or metadata in the repository?
3. Can the dependency be upgraded to a version that already supports Native Image?
4. If gaps remain, use the tracing agent to observe behavior.
5. If the agent does not cover enough or conditional metadata is needed, write a tested `RuntimeHintsRegistrar` or manual metadata.

Do not keep large amounts of agent-generated metadata if the dependency already provides official metadata and those entries are not needed by application code.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Empty output directory | Dynamic path was not executed, agent was not attached, or JVM has not exited | Check command line, workload, and shutdown |
| Only startup metadata recorded | Required endpoints/jobs were not invoked | Increase workload coverage |
| Metadata contains many JUnit/Mockito classes | Ran test suite and captured test infrastructure | Run app directly, filter, or separate test metadata |
| Native still fails despite metadata | Error branch was not executed, metadata target is wrong, or hint type is unsuitable | Read native error, reproduce path, add the right hint |
| Metadata not used by build | Placed in wrong directory or not on classpath | Place under `META-INF/native-image` or configure directory argument |
| Multiple processes overwrite output | Shared `config-output-dir` | Give each process its own directory, then merge |
| Output is too large | Broad filters or built-in filters disabled | Restore built-in filters, review caller/access filters |
| Build passes but production fails | Tests did not cover real config/input/branches | Add integration scenarios and run the native executable |

## 18. Complete Workflow from JVM to Native Image

~~~mermaid
flowchart TD
    A["Build JAR with Spring AOT"] --> B["Run JVM with tracing agent"]
    B --> C["Invoke APIs/jobs/messages per workload"]
    C --> D["Agent writes metadata"]
    D --> E["Review, filter, merge"]
    E --> F["Commit required metadata"]
    F --> G["Build Native Image"]
    G --> H["Run native integration tests"]
    H --> I{"All tested flows pass?"}
    I -->|No| B
    I -->|Yes| J["Package and test container"]
~~~

Checklist:

- [ ] Build the JVM application and Spring AOT successfully.
- [ ] Run the agent on the right GraalVM JDK/version.
- [ ] Choose a fresh, dedicated output directory for collection.
- [ ] Cover REST, messaging, scheduled jobs, serialization, and resource access.
- [ ] Run varied inputs/configurations to traverse dynamic branches.
- [ ] Stop the JVM cleanly so the agent writes output.
- [ ] Review each metadata entry and its origin.
- [ ] Remove test-only metadata if not needed for production.
- [ ] Place approved metadata under `META-INF/native-image`.
- [ ] Rebuild the native executable.
- [ ] Run native integration tests across the observed flows.
- [ ] Test the final container with production-equivalent config and resources.

## 19. Self-Check Exercises

**Question 1.** At which stage does the Tracing Agent run?

**Hint:** the agent attaches to a JVM process to observe dynamic access while the application runs; it does not directly observe a native executable.

**Question 2.** Why does agent-generated metadata not guarantee full application compatibility?

**Hint:** the agent only records executed code paths. Branches that did not run will not appear in the output.

**Question 3.** How do `config-output-dir` and `config-merge-dir` differ?

**Hint:** one option creates a fresh output set; the other appends/merges accesses into an existing metadata set.

**Question 4.** Why can running a test suite produce unnecessary metadata?

**Hint:** the agent also observes the test framework, mocks, assertions, and test-only dependencies.

**Question 5.** How does a caller filter differ from an access filter?

**Hint:** a caller filter filters where the access originates; an access filter filters the target of the access.

**Question 6.** Why must you run native integration tests after copying metadata?

**Hint:** you need to confirm Native Image actually loads the metadata and the final code paths work on the executable, not just on the JVM.

**Question 7.** When multiple JVM processes run the agent concurrently, should they share an output directory?

**Hint:** no. Each process should write to its own directory, then merge the outputs.

## 20. References

- [GraalVM — Collect Metadata with the Tracing Agent](https://www.graalvm.org/reference-manual/native-image/Agent/): how to attach the agent, output/merge, filters, trace files, and native-image-utils.
- [GraalVM — Configure Native Image with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/guides/configure-with-tracing-agent/): workflow for generating metadata and building the executable.
- [Spring Boot Reference — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): using the tracing agent with Spring AOT, running the app or tests, reviewing, and access filters.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin): agent configuration, test/application runs, and metadata copy.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): agent modes, filter files, and the metadataCopy task.

**Remember:** The Tracing Agent is a tool for observing dynamic access during a JVM run to help produce reachability metadata for Native Image. Output quality depends on workload, filters, and review. Use Spring AOT and official dependency metadata first, run the agent to find missing pieces, store approved metadata under `META-INF/native-image`, and then verify with native integration tests and a real container.
