# Inventorying JVM options, system properties, and environment variables

Before upgrading the JDK, changing how an application is packaged, or moving a system to new servers/containers, it is necessary to know the exact configurations used to launch Java processes. An application may run stably thanks to JVM options, system properties, or environment variables scattered across scripts, CI/CD pipelines, service configurations, Docker images, Kubernetes manifests, and deployment tools. If you check only `build.gradle`, `pom.xml`, or application config files, you can miss settings actually affecting the JVM.

**Inventorying JVM options, system properties, and environment variables** is the process of finding, recording, identifying the origin of, and reconciling configuration values associated with each Java process. The goal is to answer: which process is running; which JDK it uses; where it receives its configuration; what the actual values at startup are; what purpose each setting serves; and which values must be kept, replaced, or removed during migration.

This is a system assessment step prior to changing the runtime. A configuration list read solely from source code is not enough: declared configurations must be combined with the state of running processes, because the two can differ due to environment variables, launch scripts, command-line arguments, deployment platform settings, or code modifying system properties at runtime.

## 1. Distinguishing the three configuration groups

JVM options, Java system properties, and environment variables often appear side by side in a Java launch command, yet they differ in how they are passed, their scope, and how they are read.

| Group | Common declaration syntax | How read in Java | Primary scope |
|---|---|---|---|
| JVM option | `-Xmx2g`, `-Xss1m`, `-XX:+UseG1GC`, `--add-opens=...` | Processed by the JVM or launcher before the application runs | JVM startup configuration |
| Java system property | `-Dapp.region=ap-southeast-1` | `System.getProperty("app.region")` | Single JVM; can also be changed by code while running |
| Environment variable | `APP_REGION=ap-southeast-1` | `System.getenv("APP_REGION")` | Process environment and child processes spawned from that environment |

### 1.1. JVM options

JVM options are parameters passed to the Java launcher or virtual machine to control how the JVM starts and operates. Some common groups:

| Group | Example | Effect |
|---|---|---|
| Heap memory | `-Xms512m`, `-Xmx2g` | Initial heap and maximum heap limit |
| Stack | `-Xss1m` | Stack size per thread |
| Garbage Collector | `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis=200` | GC selection and tuning |
| Metaspace | `-XX:MaxMetaspaceSize=512m` | Metaspace region limit |
| Module access | `--add-opens=java.base/java.lang=ALL-UNNAMED` | Opens package for reflective access under module rules |
| Assertion | `-ea` or `-enableassertions` | Enables assertions at runtime |
| Agents and instrumentation | `-javaagent:agent.jar`, `-agentlib:jdwp=...` | Loads agents, profiling, or debugger |
| Diagnostics and errors | `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath=/var/dumps` | Produces evidence when the JVM encounters failures |

Some options have standard forms, while some begin with `-X` or `-XX`. Extended `-X` and `-XX` options can depend on the specific JDK, JVM vendor, and version. Do not assume an option that worked on an older JDK will continue to be supported on a newer JDK.

### 1.2. Java system properties

A system property is a string key/value pair belonging to a JVM. The common way to set a property at startup is using `-D`:

```bash
java -Dapp.region=ap-southeast-1 -Dfile.encoding=UTF-8 -jar application.jar
```

The application reads values using:

```java
String region = System.getProperty("app.region");
String encoding = System.getProperty("file.encoding");
```

Code can also change system properties at runtime:

```java
System.setProperty("app.region", "ap-southeast-1");
```

Therefore, a value seen in the application does not necessarily come solely from `-D`. It can come from JDK defaults, startup arguments, libraries, or `System.setProperty()` calls executed afterward. Some libraries read a property once during initialization; changing the property afterward does not mean the library updates its behavior automatically.

System properties are string data. The meaning of each key depends on the JVM, JDK, library, or application. For example, `user.timezone` can affect the default timezone; `javax.net.ssl.trustStore` can specify a truststore; `app.region` is a custom application-defined property.

### 1.3. Environment variables

Environment variables are attached to the process environment by the operating system when the process is created. Java reads them with:

```java
String region = System.getenv("APP_REGION");
```

Or retrieves the map of variables visible to the process:

```java
Map<String, String> environment = System.getenv();
```

Variables that commonly affect JDK selection or runtime configuration include:

| Variable | Common role |
|---|---|
| `JAVA_HOME` | Points to the JDK/JRE installation directory used by scripts or tools as Java home |
| `PATH` | Determines which `java` executable is found when invoked by name |
| `JDK_JAVA_OPTIONS` | Appends options for the Java launcher on JDKs supporting this variable |
| `JAVA_TOOL_OPTIONS` | Appends options when a JVM is created via the VM initialization mechanism, often useful for tools embedding the JVM |
| `_JAVA_OPTIONS` | Private mechanism in certain HotSpot builds; should not be treated as a portable, standardized interface |
| `CLASSPATH` | Default classpath when the launcher receives no other classpath |
| `MAVEN_OPTS` | Typically used by the Maven launcher to pass options to the JVM running Maven |
| `GRADLE_OPTS` | Typically passes options to the JVM running the Gradle client; the Gradle daemon's JVM may have its own config via `org.gradle.jvmargs` |
| `APP_*`, `SPRING_*` | Configuration conventions used by applications or frameworks |
| `TZ`, `LANG`, `LC_ALL` | Can affect process timezone, locale, or formatting environment |

Variable names and usage may differ by operating system, scripts, and deployment platforms. The Java launcher does not automatically interpret every variable whose name contains `JAVA` or `OPTS`; you must know which component reads that variable.

## 2. Understanding how configuration enters a Java process

A configuration setting may be declared across multiple layers. For example, the same property `app.region` may appear in a `-D` flag, an `APP_REGION` environment variable, an application config file, and a `System.setProperty()` call. There is no universal precedence rule across all applications: precedence among environment, system properties, YAML files, command-line arguments, and remote config depends on the framework or code in use.

### 2.1. Boundary between JVM options and application arguments

The Java launcher separates launcher/JVM options from arguments passed to the application. For example:

```bash
java -Xmx2g -Dapp.mode=production -jar application.jar --server.port=8080
```

In this example:

- `-Xmx2g` is a JVM option.
- `-Dapp.mode=production` sets a system property for the JVM.
- `-jar application.jar` tells the launcher to run the JAR.
- `--server.port=8080` is an application argument, typically processed by the framework.

With a class launch command:

```bash
java -Dapp.mode=production com.example.Main --verbose
```

Options must precede the class name. Everything after the class name is passed to `main(String[] args)`. Similarly, with `-jar`, everything after the JAR name is an application argument. Placing `-Dapp.mode=production` after `-jar application.jar` no longer sets a JVM system property; the application receives that string as an argument.

This point is often missed when moving parameters across Docker `ENTRYPOINT`, `CMD`, shell scripts, or service manager configurations.

### 2.2. Sources injecting JVM options via the environment

Besides the command line shown in scripts, certain environment variables can inject options:

- `JDK_JAVA_OPTIONS` is prepended to the launcher command line by the Java launcher on supporting JDKs. This variable was introduced in JDK 9.
- `JAVA_TOOL_OPTIONS` is read during JVM creation and can affect programs embedding the JVM or tools initializing a JVM without calling the launcher normally.
- `_JAVA_OPTIONS` exists in some HotSpot environments yet is an implementation-dependent mechanism; do not rely on it as a portable contract.

Because these sources can combine with command-line and script options, reading a single `java ...` line does not guarantee seeing the full configuration. Record relevant environment variables as well and verify actual options from the running JVM.

`JAVA_OPTS` is a variable name commonly adopted by scripts by convention. The Java launcher does not read this variable automatically. For example, a script might write:

```bash
java $JAVA_OPTS -jar application.jar
```

If the script does not reference `$JAVA_OPTS`, setting that variable in the environment has no automatic effect. Similarly, `MAVEN_OPTS` and `GRADLE_OPTS` are read by build tools through their own mechanisms; do not assume they are also options of the final application JVM.

### 2.3. Declared values vs effective values

When inventorying, distinguish at least three states:

1. **Declared value:** appears in config files, scripts, pipelines, or manifests.
2. **Value passed into the process:** actually present on the command line or in the environment when the process is created.
3. **Effective value:** what the JVM or application uses after applying defaults, options, framework configs, and runtime modifications.

These three states can differ. A deployment file declares `-Xmx2g`, yet the container has a lower memory limit and the JVM applies a different memory calculation; an environment variable may be set in a manifest yet ignored by the launch script; a system property may be overwritten by code during startup.

Therefore, the inventory should store both declaration sources and runtime evidence. Do not record a single value and assume it is the final effective value.

## 3. Identifying all Java processes to inventory

Before searching for options, list the processes. A system can contain multiple JVMs with different configurations:

- JVM running the main application.
- JVM running Gradle or Maven.
- Gradle daemon and separately forked test JVMs.
- JVM running compilers, annotation processors, or code generation tools.
- JVMs of application servers, workers, schedulers, or sidecars.
- JVMs running migration tools, batch jobs, and administrative scripts.
- JVMs across development, staging, production, and CI environments.

Do not merge configurations across these processes into one shared set. For example, `GRADLE_OPTS` may affect the JVM running Gradle; `test.jvmArgs` or test fork configs affect test JVMs; `bootRun` or deploy scripts may have separate application settings. Upgrading the JDK for the Gradle daemon does not itself prove the application JVM was upgraded.

For each process, record:

| Attribute | Content to determine |
|---|---|
| Identity | Service name, PID, container/pod, hostname, or job id |
| Role | Application, build, test, batch, worker, or admin tool |
| Runtime | JVM vendor, JDK version, and executable path if identifiable |
| Launch | Command, entrypoint, script, service unit, or pipeline spawning the process |
| Environment | OS, container image, namespace, deployment environment |
| Timestamp | Time inventory was captured and running release version |
| Owner | Team responsible for the process and configuration |

A process can be restarted by an orchestrator or autoscaling. A PID only identifies one specific execution, not a stable service identity. Associate the PID with service name, container/pod, and observation timestamp.

## 4. Finding declared configurations in repositories and deployment environments

Static inventorying helps locate where configurations are written before observing running processes. Search across multiple keyword groups while expanding scope beyond source code.

### 4.1. Searching in source code and build configurations

Locations typically needing inspection:

- `build.gradle`, `build.gradle.kts`, `gradle.properties`, `settings.gradle`, and convention plugins.
- `pom.xml`, `.mvn/jvm.config`, `.mvn/maven.config`, and Maven wrapper scripts.
- `Dockerfile`, `docker-compose.yml`, shell scripts, batch files, and PowerShell scripts.
- Test configs, `JavaExec` tasks, `bootRun`, forked test JVMs, and application plugin settings.
- `.env` files, profile-specific config files, deployment templates, and entrypoint scripts.
- GitHub Actions, Jenkinsfile, GitLab CI, Azure pipelines, or equivalent CI/CD workflows.

You can search common keywords using `rg`:

```bash
rg -n --hidden -g '!**/.git/**' \
  'JAVA_HOME|JAVA_OPTS|JDK_JAVA_OPTIONS|JAVA_TOOL_OPTIONS|_JAVA_OPTIONS|MAVEN_OPTS|GRADLE_OPTS|CLASSPATH' .

rg -n --hidden -g '!**/.git/**' \
  -- '-Xms|-Xmx|-Xss|-XX:|-D[a-zA-Z0-9_.-]+=|--add-opens|--add-exports|-javaagent|-agentlib' .
```

Search expressions are only starting points. An option may be built dynamically via variables, string concatenation, read from external files, or passed via script parameters. Trace where variables are assigned, where they are expanded, and which final process receives them.

Inspect per-environment configs closely. A shared `application.yml` file may lack production values because deployment injects environment variables or separate system properties. Helm templates, ConfigMaps, service units, secret references, and cloud platform configs can be key sources.

### 4.2. Searching in OS and service manager configs

On Linux, check systemd unit files, referenced environment files, startup scripts, and supervisor configs. On Windows, check Windows Service configurations, wrapper scripts, registry entries, or service wrapper configs if any. For application servers, check startup scripts and server-specific JVM configs.

Do not search only for the string `java`. A service may invoke a wrapper such as `startup.sh`, `catalina.sh`, `gradlew`, an internal script, or another executable; the wrapper is where actual options are assembled.

### 4.3. Inspecting Docker and Kubernetes

With Docker, inspect `ENTRYPOINT`, `CMD`, `ENV`, build arguments converted into environment variables, compose overrides, and variables injected at `docker run`. `docker inspect` can reveal container settings, yet environment or command-line data may hold sensitive info; extract only needed keys and redact secret values.

With Kubernetes, inspect `command`, `args`, `env`, `envFrom`, ConfigMap references, Secret references, init containers, and Helm/Kustomize templates. A manifest referencing a Secret does not show the actual value; there is no need to dump Secret contents to complete a JVM inventory. Record the reference name, key, and owner per organizational secret-management policy.

Distinguish configuration in the Pod template from the actual configuration of a running Pod. A Pod may be running an older revision, a different image digest, or have been created before the latest manifest update.

## 5. Observing running JVMs

Inspecting runtime processes confirms the JDK and options actually received by the JVM. The commands below apply primarily to HotSpot/OpenJDK; commands and diagnostic command sets may differ on other JVM providers.

### 5.1. Listing processes and command lines

```bash
jps -lv
```

`jps` lists JVMs observable by the tool on the machine and typically prints the main class along with JVM arguments. It helps locate PIDs, yet does not always see every process, especially across different users, container namespaces, or when attach is restricted.

After identifying the PID, use `jcmd`:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
jcmd <pid> VM.system_properties
```

Meaning:

- `VM.command_line` shows the command line information recorded by the JVM.
- `VM.flags -all` displays VM flags and their current values exposed via the diagnostic command.
- `VM.system_properties` displays the process's system properties at query time.

This is stronger runtime evidence than merely reading scripts. However, `VM.system_properties` output can contain internal paths, tokens, or sensitive info if the application stores them in system properties. Do not paste raw output into tickets, shared logs, or repositories.

Attach permissions, process owning user, container PID namespaces, and security policies can prevent `jcmd` from connecting. When commands fail, record the observation limitation and use approved administrative channels; do not arbitrarily run processes with elevated privileges just to retrieve data.

### 5.2. Observing flags of a fresh JVM

To inspect flags and defaults of a selected JDK:

```bash
java -XX:+PrintFlagsFinal -version
```

This command launches a new JVM and prints the final flag list for that run. It helps inspect a specific JDK binary, yet does not replace reading flags of running production processes. Values can vary depending on passed options, JVM type, hardware, container limits, and JDK version.

To inspect system properties of a fresh launch:

```bash
java -XshowSettings:properties -version
```

This is also only a snapshot of the new process spawned by the command above. It does not prove a running application process holds the same values.

### 5.3. Reading information from the Java Management API

An application can observe certain JVM details itself through the Management API:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

public class RuntimeInventory {
    public static void printRuntimeIdentity() {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        System.out.println("VM name: " + runtime.getVmName());
        System.out.println("VM vendor: " + runtime.getVmVendor());
        System.out.println("VM version: " + runtime.getVmVersion());
        System.out.println("Input arguments:");
        runtime.getInputArguments().forEach(System.out::println);
    }
}
```

`getInputArguments()` provides arguments passed to the JVM from the runtime's perspective. It is useful for diagnostics, yet is not a complete copy of every configuration source: it does not replace inventorying environments, scripts, framework configs, or runtime property changes. The argument list may also contain sensitive data if deployers placed secrets directly inside parameters.

Reading specific system properties via `System.getProperty()` and specific environment variables via `System.getenv()` helps verify values seen by the application. Prefer choosing keys via an allowlist rather than dumping all data.

### 5.4. Inspecting process environment variables

Environment variables are process attributes managed by the operating system. `System.getenv()` in Java reflects the environment received by the current process. JVM tools like `jcmd` are not tools for listing all environment variables.

On Linux, a process's initial environment can often be observed via `/proc/<pid>/environ` if OS permissions allow. Technical example:

```bash
tr '\0' '\n' < /proc/<pid>/environ
```

This command can print secrets, credentials, or tokens. Use only when authorized, filter strictly for the keys needing inventory, and never save raw output to unprotected locations. `ps` may display command lines yet is not a complete source for retrieving environment variables.

On Windows, `Get-ChildItem Env:` shows only the current PowerShell environment, not another process's environment. You can inspect command lines via CIM:

```powershell
Get-CimInstance Win32_Process |
    Select-Object ProcessId, Name, CommandLine
```

To learn the environment of a Windows Service or specific process, check service configuration, wrappers, appropriate process admin tools, and granted permissions. Do not use the current terminal's environment to infer that a service received the same values.

## 6. Reading system properties and environments safely

A good inventory needs enough evidence for migration without copying secrets. JVM options, system properties, and environments sometimes hold passwords, tokens, URLs with credentials, or internal paths. Even key names can leak operational information.

### 6.1. Prefer allowlists

For example, instead of printing all system properties, read only keys identified as needed for migration:

```java
import java.util.List;

public class SelectedProperties {
    private static final List<String> PROPERTY_KEYS = List.of(
            "java.version",
            "java.vendor",
            "java.home",
            "file.encoding",
            "user.timezone",
            "app.region"
    );

    public static void printSelectedProperties() {
        for (String key : PROPERTY_KEYS) {
            System.out.printf("%s=%s%n", key, System.getProperty(key));
        }
    }
}
```

Similarly, with environments, read only approved keys such as `JAVA_HOME`, `APP_REGION`, or `TZ`. Do not print all of `System.getenv()` into production logs.

If you need to inspect config keys that may contain secrets, record status such as `present`, reference source, and owner; do not store values. For example, an inventory might record `DB_PASSWORD: configured via SecretRef/database-credentials`, rather than copying the password.

### 6.2. Do not place secrets directly in JVM arguments

Command-line arguments can appear in process listings, diagnostic outputs, orchestrator logs, or monitoring tools. Passing `-Dapi.token=...` or `--password=...` can expose secrets to anyone with permission to view process metadata. Use a secret manager, appropriately permissioned mounted files, or platform-supported credential mechanisms; applications should read secrets at runtime according to security policy.

If the inventory uncovers secrets passed via command line or system properties, record the risk and configuration location, and redact values in reports. Changing how secrets are delivered should be handled as a separate migration task and verified to ensure the application still reads credentials properly.

## 7. Building an inventory table usable for migration

Do not simply produce a list of `-Xmx`, `-D`, and `APP_*` lines. Record origin, scope, purpose, and runtime evidence so implementers know what to check on the new JDK.

### 7.1. Recommended fields

| Field | Content |
|---|---|
| Process/service | Service, job, test worker, or build daemon receiving the configuration |
| Environment | Local, CI, dev, staging, production, or cluster name |
| Configuration type | JVM option, system property, environment variable, or application argument |
| Key/option | Exact name, e.g. `-Xmx`, `app.region`, `APP_REGION` |
| Value | Value permitted for storage; if sensitive, record status and reference |
| Source | Script, Gradle, Maven, service unit, container, manifest, CI variable, or secret reference |
| Effective evidence | `jcmd` output, runtime API, process metadata, or owner confirmation |
| Scope | Single process, single host, single container, single namespace, or whole environment |
| Purpose | Technical or business purpose of the setting |
| Owner | Responsible team or component |
| Lifecycle | Startup-only, read at init, mutable at runtime, or refreshed by framework |
| JDK dependency | Relevant JDK/vendor/version; portable or implementation-specific |
| Migration action | Keep, replace, validate, remove, or investigate |
| Evidence/time | Evidence source, release, and inventory timestamp |

### 7.2. Abbreviated inventory example

The following rows are illustrative data, not default settings for every application:

| Process | Type | Configuration | Source | Evidence to confirm | Handling direction |
|---|---|---|---|---|---|
| `orders-api` | JVM option | `-Xmx2g` | Deployment `args` | `jcmd ... VM.flags -all` and memory limit | Validate on new JDK and container limit |
| `orders-api` | JVM option | `--add-opens=java.base/java.lang=ALL-UNNAMED` | `JAVA_TOOL_OPTIONS` | `VM.command_line`, environment, and libraries needing reflective access | Find consumer; upgrade/replace library or keep temporarily if needed |
| `orders-api` | System property | `app.region=...` | `-D` in entrypoint | `VM.system_properties` and value read by app | Preserve semantics, confirm standard config source |
| `orders-api` | Environment | `APP_REGION` | Kubernetes ConfigMap | Actual Pod environment and `System.getenv` | Check mapping into framework |
| `batch-worker` | Environment | `JAVA_HOME` | Service unit | Process executable and `java.version` | Confirm JDK actually selected |
| `gradle-test` | JVM option | `-Xmx1g` | Test task config | JVM fork running tests | Evaluate separately from application JVM |

When the same value is declared in multiple places, create multiple source rows or a group with clear provenance relationships. Do not delete duplicate sources before knowing which source actually takes effect.

## 8. Classifying configurations by risk when upgrading JDK

After collecting, classify items to know which must be verified before switching runtimes.

### 8.1. Version- or vendor-dependent JVM options

`-XX` and `-X` options typically must be checked against the target JDK. An option may:

- Still be supported and keep its semantics.
- Be supported yet change its default value.
- Be deprecated and emit a warning.
- Be obsolete or no longer take effect as before.
- Be removed and cause the JVM to refuse to start.
- Exist only on a specific implementation or JDK release line.

Pay close attention to GC, memory sizing, compiler, JIT, container awareness, diagnostic, module access, and internal options. Do not copy the entire old JDK flag set onto the new JDK without verification.

### 8.2. System properties defined by the JDK or libraries

Some properties have meanings defined by the JDK or libraries; default values and handling can change across versions. Examples may relate to encoding, timezone, TLS, proxies, truststores, logging, or reflective access. Determine whether a property belongs to the JDK, a third-party library, or the application itself.

Application-defined properties are generally not validated automatically by the JVM. That does not mean they are safe: code may rename keys, change defaults, or change parsing. Locate where the property is read, not only where it is declared.

### 8.3. Platform-dependent environment variables

Variables such as `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `MAVEN_OPTS`, and `GRADLE_OPTS` have distinct semantics. Migration can change images, shells, service managers, or build agents, causing variables to no longer be passed as before.

Application variables such as `APP_REGION`, `SPRING_PROFILES_ACTIVE`, or service connection variables depend on the framework and application. Inspect how the framework maps variables to properties, including naming rules, data types, precedence order, and active profiles. Do not infer one universal precedence rule across all frameworks.

### 8.4. Configurations mutable at runtime

Some system properties can be modified via `System.setProperty`, some application configs can refresh from a config server, whereas JVM flags typically can only be set at startup or only certain flags may be altered via diagnostic commands. The inventory should record read timing and update mechanisms.

If a setting takes effect only at startup, changing an environment variable or file after the process is running does not cause the process to pick up the new value automatically. A restart or an application-supported refresh mechanism is required. Conversely, if config refresh can change behavior without restarting, test both pre-refresh and post-refresh states.

## 9. Reconciling the inventory when moving to a new JDK

Once a baseline exists, perform reconciliation per process and per environment. Do not simply run `java -version` on the build machine and conclude the whole system uses the target JDK.

### Step 1: Lock the target JDK for each process

Specify the Java version, vendor, distribution, and runtime path each process must use. A system may intentionally use different JDKs for build tools, tests, applications, and migration tools; record that decision rather than assuming one shared JDK.

### Step 2: Reconcile each JVM option

For each option, consult vendor documentation and the target JDK version, then test on the exact binary. Confirm the JVM starts, the flag exists, and the effective value is appropriate. You can use `java -XX:+PrintFlagsFinal -version` to inspect target binary flags and `jcmd` on a test process to inspect runtime state.

Do not use `-XX:+IgnoreUnrecognizedVMOptions` as a default migration fix. An unrecognized option may have been protecting a critical requirement; ignoring the warning can silently alter GC, memory, module access, or diagnostics without anyone noticing. If an option must be removed, prove it is no longer needed or already replaced.

### Step 3: Reconcile system properties

For each property, identify its owner and read sites. Distinguish JDK properties, library properties, and application properties. Compare defaults between the two JDKs; if the application relies on a default, decide whether to set an explicit value to keep behavior stable.

Specifically inspect properties that were renamed, unsupported, or gained new semantics. Do not merely confirm the property still appears in `System.getProperties()`; confirm the consuming component still reads and understands that value.

### Step 4: Reconcile environments and launch methods

Confirm `JAVA_HOME`, the executable resolved via `PATH`, option-injecting variables, and application variables are all passed to the right process. Check new scripts, new container images, new service units, and orchestrator configurations. Ensure `-D` still sits in the JVM option position rather than shifting into application arguments.

### Step 5: Trial run in matching environments

Launch each process on the target JDK with the migrated configuration. Capture `java.version`, `VM.command_line`, flags, selected system properties, and permitted environment keys. Compare against the baseline by semantics, not purely by string equality.

### Step 6: Verify behavior and operations

Run functional, integration, load, and failure scenarios related to configurations. For memory options, check heap limits, native memory, and container memory. For GC, check pause and throughput logs/metrics. For module access, exercise code paths using reflection. For TLS/proxy/truststore, test actual connections to required endpoints.

### Step 7: Monitor after rollout

Roll out per environment or instance group, retain rollback capability, and monitor appropriate metrics. When discrepancies arise, trace back from the specific process to the configuration source rather than editing a global variable with unclear blast radius.

## 10. Common misconceptions when inventorying

- **Checking only `JAVA_HOME`:** this variable does not prove which executable a process actually uses. `PATH`, wrappers, container images, or absolute paths may select another JDK.
- **Equating `JAVA_OPTS` with Java launcher options:** this is usually a script-defined convention; find where scripts read it.
- **Treating `MAVEN_OPTS` or `GRADLE_OPTS` as application JVM config:** they typically configure JVMs running build tools; test or application forks may have separate option sets.
- **Reading only config files:** actual values may be injected from environment variables, secret references, service managers, or deployment platforms.
- **Inspecting only command lines:** `JAVA_TOOL_OPTIONS` and other sources can inject options; code can also modify system properties after JVM startup.
- **Treating system properties and environment variables as identical:** `System.getProperty()` and `System.getenv()` read two distinct sources. Frameworks may map them under specific rules.
- **Checking the build JVM instead of the runtime JVM:** Gradle daemon, test forks, compilers, and the application may be separate processes.
- **Saving raw diagnostic outputs verbatim:** command lines, system properties, and environments can contain secrets or internal info.
- **Keeping all old flags out of habit:** old options may no longer have effect, may be removed, or may change defaults on the new JDK.
- **Deleting an option simply because the new JDK starts:** an option can affect performance, memory limits, module accessibility, or diagnostics when errors happen.
- **Omitting source and owner:** when wrong values appear in production, operations teams struggle to know whether to fix manifests, scripts, pipelines, or code.

## 11. Inventory completion checklist

- [ ] Listed Java processes across build, test, runtime, batch, and operations.
- [ ] Recorded JDK vendor, version, executable/image, and environment for each process.
- [ ] Searched for JVM options in source, build configs, scripts, service managers, containers, orchestrators, and CI/CD.
- [ ] Searched for `-D` system properties and identified where code/frameworks read or modify properties.
- [ ] Checked environment variables that can select JDKs or inject JVM options.
- [ ] Distinguished `JAVA_OPTS`, `MAVEN_OPTS`, `GRADLE_OPTS`, `JAVA_TOOL_OPTIONS`, and `JDK_JAVA_OPTIONS` by actual usage site.
- [ ] Collected runtime evidence for command lines, VM flags, and system properties on representative processes.
- [ ] Inspected process environments in a manner compliant with OS/containers and access permissions.
- [ ] Recorded source, owner, purpose, scope, read timing, and sensitivity of each configuration.
- [ ] Classified options/properties by JDK dependency and migration action.
- [ ] Redacted secrets and restricted shared diagnostic data.
- [ ] Established a sufficiently clear baseline to compare against processes running on the target JDK.

## 12. Conclusion

Inventorying JVM options, system properties, and environment variables identifies the configurations actually governing each Java process. To obtain a reliable inventory, combine static search across repositories and deployment platforms with observation of running processes; distinguish declared configurations, passed configurations, and effective values; and record origin, owner, purpose, and JDK dependency. That dataset forms a baseline allowing migration to reconcile each process on the new runtime, spot obsolete options or lost settings, and preserve stable operational behavior.
