# Startup Parameters in Scripts, systemd, or Kubernetes Configuration

## 1. Context: Startup Parameters Are Also Part of the Java Compatibility Contract

In **Java Advance Compatibility Migration**, teams often audit source code, dependencies, APIs, and bytecode, yet forget that the JVM in real environments may be started with an entirely different combination of flags than locally. An application that runs with the java -jar command on a developer machine can still fail when deployed via a shell script, Linux systemd, or Kubernetes.

Examples:

- A JVM flag is placed after -jar, so it has no effect on the JVM and instead becomes an application argument.
- A script concatenates a command string and calls eval, breaking quoting or introducing injection risks.
- systemd ExecStart is written like a Bash command, whereas systemd does not automatically invoke a shell to handle arbitrary syntax.
- EnvironmentFile sets JAVA_OPTS, but the startup command never reads that variable.
- A Docker image has an ENTRYPOINT configuring agents and TLS, while Kubernetes command overrides the entrypoint so those preparation steps are skipped.
- A shell runs as PID 1 and fails to forward SIGTERM properly, causing shutdown hooks not to be called as expected.
- A newer JDK rejects removed VM options, or reads cgroups differently and alters the effective heap size or processor count.
- Truststore, heap dump, GC log, and agent paths match on VMs but are missing in the container.
- Secrets appear in -D properties or application arguments and get exposed in process lists, logs, or diagnostic output.

Therefore, **artifact + JDK runtime + startup command + environment + resource limits + lifecycle settings** must be treated as a single combination to verify. This lesson belongs to the *Packaging and Environment* chapter, focusing on how to manage parameters across scripts, systemd, and Kubernetes when upgrading or migrating Java.

After this lesson, the reader can distinguish JVM options from application arguments, organize startup scripts safely, write systemd units/drop-ins with proper semantics, understand Docker ENTRYPOINT/CMD and Kubernetes command/args, manage JVM environment variables, inspect effective flags, and design post-migration tests and rollback.

## 2. Java Launcher Syntax and the Position of Each Parameter

Common launcher forms:

~~~text
java [JVM/launcher options] -jar application.jar [application arguments]
java [JVM/launcher options] -cp classpath com.example.Main [application arguments]
java [JVM/launcher options] --module-path modules -m module.name/com.example.Main [application arguments]
~~~

Example:

~~~bash
java -Xms256m -Xmx768m -Dapp.mode=production \
    -jar /opt/app/app.jar --server.port=8080
~~~

| Component | Group | Meaning |
|---|---|---|
| java | Executable | Java launcher from the selected JDK/JRE. |
| -Xms256m | JVM option | Initial heap size. |
| -Xmx768m | JVM option | Maximum Java heap size. |
| -Dapp.mode=production | JVM system property | Can be read by the application/framework. |
| -jar /opt/app/app.jar | Main selector | Selects the executable JAR to run. |
| --server.port=8080 | Application argument | Passed to main; takes effect only if supported by the application/framework. |

### 2.1. JVM Flags Must Come Before -jar, Main Class, or -m

Wrong example if the intent is to set heap size:

~~~bash
java -jar app.jar -Xmx768m
~~~

In the command above, -Xmx768m is an **application argument** after -jar, not a JVM heap option. The Java launcher does not use it to change Xmx.

Similarly:

~~~bash
java -jar app.jar -Dapp.mode=production
~~~

does not set app.mode as a system property in the way the JVM launcher interprets when -D is used before -jar.

This distinction is important when translating a startup command into an args list in Kubernetes or when using Docker CMD to append arguments after an image ENTRYPOINT.

### 2.2. Application Arguments and JVM System Properties Differ

Java example:

~~~java
import java.util.Arrays;

public final class StartupArguments {
    public static void main(String[] args) {
        System.out.println("args=" + Arrays.toString(args));
        System.out.println("app.mode=" +
                System.getProperty("app.mode"));
    }
}
~~~

If you run:

~~~bash
java -Dapp.mode=production StartupArguments --profile=blue
~~~

then -Dapp.mode is a system property, while --profile=blue appears in args. Some frameworks have their own mechanism to map application arguments into configuration properties; that does not mean every Java application automatically understands --profile or --server.port.

### 2.3. Do Not Mix Main Selection Modes

For an executable JAR, use -jar. For a main class directly, use -cp/--class-path and the class name. For a named module, use --module-path and -m/--module per the module structure.

Switching from classpath to module path during migration requires separate testing because service discovery, reflection, exports/opens, and module resolution can differ. Do not combine -jar, main class, and -m in the same command without an explicit design.

## 3. JVM Option Groups Frequently Involved When Upgrading JDK

| Group | Common Options | Why Check During Migration |
|---|---|---|
| Heap | -Xms, -Xmx | Heap limits and memory footprint. |
| Ergonomic memory | -XX:MaxRAMPercentage, -XX:InitialRAMPercentage | How heap is computed when Xmx/Xms are not explicitly set. |
| CPU | -XX:ActiveProcessorCount | Affects the processor count the JVM uses for certain decisions. |
| Garbage collection | -XX:+UseG1GC and corresponding collector options | Old GC and flags may be removed or change defaults. |
| Diagnostics | -Xlog, -XX:+HeapDumpOnOutOfMemoryError | Logging, dumps, and storage permissions. |
| Agents | -javaagent, -agentpath, -agentlib | Depends on Java/bytecode/JVMTI versions and OS/architecture. |
| Module access | --add-opens, --add-exports, --add-modules | Some legacy libraries need temporary access permissions. |
| Encoding/timezone | -Dfile.encoding, -Duser.timezone | Can affect output and test behavior. |
| TLS | -Djavax.net.ssl.trustStore and related properties | Certificate trust, mTLS, and keystore paths. |
| Application framework | --spring.profiles.active, --server.port, --app.config | Framework-dependent, typically application arguments. |

These are illustrative groups for compatible JVM/Java launchers; not every JVM vendor/release supports the exact same flags. When moving from HotSpot to another JVM implementation, verify that implementation's documentation.

### 3.1. Separate JVM Flags, Application Config, and Secrets

A good startup contract classifies:

~~~text
JVM options: heap, GC, module access, JVM diagnostics
Application arguments: profile, port, config path, feature switches
Environment/config files: endpoint, log level, app-specific settings
Secrets: secret manager or protected credential files
Deployment: CPU/memory, probes, restart, filesystem permissions
~~~

Do not use one giant “JAVA_OPTS” string to hold JVM flags, URLs, passwords, and shell commands together. This matters especially when multiple teams modify startup configuration.

## 4. Configuration Sources and Application Order

A runtime can have multiple sources:

~~~text
Script / systemd unit / container image
                │
                ▼
 Environment and deployment config
                │
                ▼
 Java launcher + JVM options
                │
                ▼
   Main class / executable JAR
                │
                ▼
Application arguments / framework configuration
                │
                ▼
Runtime business behavior
~~~

The diagram illustrates layers of responsibility; it does **not** claim a universal precedence order across all frameworks.

For instance, Spring Boot has its own precedence across command-line arguments, environment variables, system properties, and configuration files. A custom application may read only a small subset. Similarly, duplicate JVM flags have behavior depending on the specific JVM/launcher and option; you should not design around a “whichever flag appears later always wins” rule without verifying on the target JDK.

Every critical setting should have **a single source of truth** or a documented and tested precedence rule.

## 5. Startup Scripts on Linux/Unix

A startup script can help pick the Java executable, validate configuration, and prepare paths. However, it is also a common place to introduce quoting bugs, argument-splitting issues, and signal-handling bugs.

### 5.1. Simple POSIX Shell Script Example

Suppose start.sh is located in /opt/myapp and app.jar is in the same directory:

~~~sh
#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec /usr/bin/java \
    -Xms256m \
    -Xmx768m \
    -XX:+ExitOnOutOfMemoryError \
    "-Dapp.config=$APP_DIR/conf/app.yml" \
    -jar "$APP_DIR/app.jar" \
    "$@"
~~~

This example uses a fixed Java command at /usr/bin/java and assumes the shell/utilities support the syntax used; concrete paths must be adjusted per host/container. In an environment with a wrapper managing JDK versions, you can use the absolute path to the approved JDK instead of relying on PATH.

Points to note:

1. Use the path relative to the script location to locate the artifact rather than relying on the current working directory.
2. Quote paths that may contain spaces.
3. Place JVM flags before -jar.
4. "$@" forwards each argument individually to the application.
5. **exec** replaces the shell process with Java rather than keeping the shell between Java and the supervisor.
6. Startup must not print secrets to stdout/stderr.

Do not use eval or arbitrarily execute environment variable contents as shell commands.

### 5.2. Improper Quoting Changes Argument Meaning

Example path with spaces:

~~~text
/opt/My Application/config/app.yml
~~~

Unsafe for argument splitting:

~~~sh
java -Dapp.config=/opt/My Application/config/app.yml -jar app.jar
~~~

Explicit form:

~~~sh
java "-Dapp.config=/opt/My Application/config/app.yml" -jar app.jar
~~~

Quoting also needs to be applied to Java agent paths, truststore paths, heap dump paths, application JARs, and user-supplied parameters.

### 5.3. "$@" and "$*" Are Not Equivalent

When the script is invoked:

~~~sh
./start.sh "--display-name=Example App" --profile=staging
~~~

a script using "$@" passes two separate application arguments. In many usages, "$*" combines positional arguments into a single string and can lose argument boundaries.

Do not join all arguments into one string and let the shell re-parse it, because data containing spaces, wildcards, or special characters will not be preserved.

### 5.4. Dangerous Pattern: Building a Command String Followed by eval

Avoid:

~~~sh
JAVA_OPTS="-Xmx768m"
CMD="java $JAVA_OPTS -jar app.jar"
eval "$CMD"
~~~

If part of the string is modified from environment/secret/config values, eval can turn data into shell syntax. It also makes it difficult to quote paths, options containing spaces, and arguments that must remain intact.

Prefer passing each flag explicitly or using a managed Java argument file.

## 6. Java Argument Files for Managing Multiple Options

On JDKs that support argument files for the Java launcher, options can be placed in a file:

File /etc/myapp/jvm.args:

~~~text
-Xms256m
-Xmx768m
-Duser.timezone=UTC
-Xlog:gc*:stdout:time,uptime,level,tags
~~~

Command:

~~~sh
java @/etc/myapp/jvm.args -jar /opt/myapp/app.jar
~~~

Advantages:

- Less dependent on shell/systemd/YAML escaping when option lists are long.
- Easier to manage through versioned configuration.
- Convenient separation between JVM options and application arguments.

Limitations:

- The file uses Java launcher argument-file syntax, not shell script syntax; do not assume shell expansion happens inside automatically.
- Ensure the target JDK's Java launcher supports the intended syntax.
- File permissions and source provenance must still be managed.
- Do not store secrets in the file merely because the file does not show completely on the command line.
- Avoid declaring conflicting entries of the same JVM flag in the argfile, direct command, and environment.

If using an argfile in systemd/Kubernetes, mount or copy the file to the exact path before Java starts.

## 7. Java-Related Environment Variables

| Variable | Role | Warning |
|---|---|---|
| JAVA_HOME | Convention for JDK/JRE install path commonly used by scripts/build tools. | The Java launcher does not automatically force using the binary from JAVA_HOME. |
| JAVA_TOOL_OPTIONS | Can be picked up by the JVM during initialization to append certain VM options. | Not synonymous with all Java launcher options. |
| JDK_JAVA_OPTIONS | Read by supporting JDK Java launchers to append launcher options. | Has restrictions on options that alter the main selector/launcher behavior. |
| JAVA_OPTS | Conventional variable name set by scripts/app servers/images. | **The standard Java launcher does not automatically read JAVA_OPTS.** |
| _JAVA_OPTIONS | Handled by certain JVM/HotSpot implementations. | Should not be treated as mandatory portable configuration across all Java runtimes. |

### 7.1. JAVA_TOOL_OPTIONS

Example:

~~~sh
export JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -Dapp.mode=production"
java -jar app.jar
~~~

In supporting JVMs, VM options can be injected into JVM initialization. This is useful when you cannot modify the launcher command directly, yet it cannot serve as a general replacement for every command-line option such as -jar or a main class name.

Some JVMs print a “Picked up JAVA_TOOL_OPTIONS” message; that can be useful diagnostic info, though it does not prove every option passed took effect as intended.

### 7.2. JDK_JAVA_OPTIONS

Example:

~~~sh
export JDK_JAVA_OPTIONS="-Xmx768m -Dapp.mode=production"
java -jar app.jar
~~~

The variable is supported by the Java launcher on compatible JDKs and has specific restrictions on the options it is allowed to contain. Consult the Java launcher documentation for the target runtime; do not put -jar, a main selector, or disallowed options into the variable expecting it to work.

If both JDK_JAVA_OPTIONS and an image ENTRYPOINT set -Xmx or GC, verify effective behavior and fix the configuration to avoid conflicts.

### 7.3. JAVA_OPTS Does Not Work Automatically

Example:

~~~sh
export JAVA_OPTS="-Xmx512m"
java -jar app.jar
~~~

The standard java command above **does not automatically read JAVA_OPTS**. Some application servers, build scripts, or Docker images provide wrappers that process JAVA_OPTS, yet that is a wrapper contract, not a standard launcher feature.

When seeing JAVA_OPTS in a systemd unit or Kubernetes ConfigMap, check whether the actual startup script reads it.

### 7.4. Use a Single Configuration Source Whenever Possible

Clearly specify:

- Which flags are encoded in the image or unit.
- Which flags change per environment.
- Which variables are strictly for application configuration.
- Which secrets must be read from a protected file/secret manager.
- How to inspect the running Java process.

Avoid having the same -Xmx set in Dockerfile, JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS, and Kubernetes command with nobody owning precedence.

## 8. systemd Service: Not an Arbitrary Shell Script

On Linux, systemd commonly manages Java services with restart policy, process supervision, signals, logging, and cgroup limits.

Unit file example:

~~~ini
[Unit]
Description=Example Java Application
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=javaapp
Group=javaapp
WorkingDirectory=/opt/javaapp
Environment=APP_ENV=production
ExecStart=/usr/bin/java -Xms256m -Xmx768m -XX:+ExitOnOutOfMemoryError -jar /opt/javaapp/app.jar --app.env=production
Restart=on-failure
RestartSec=5s
TimeoutStopSec=60s
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
~~~

The example assumes user/group javaapp, app.jar, and /usr/bin/java exist, and the service has required permissions.

### 8.1. ExecStart Does Not Automatically Use Bash Syntax

Do not treat characters like pipe, redirect, &&, or command substitution in ExecStart as shell syntax processed by default. systemd has its own rules for parsing the executable and arguments.

If simply running Java with explicit flags, a direct ExecStart is usually less risky than adding a shell wrapper. If the application genuinely needs a preflight script, the unit can invoke a script with a shebang and the script should exec Java at the final step.

### 8.2. WorkingDirectory and Filesystem Permissions

WorkingDirectory helps the application handle relative paths consistently, yet for JARs, agents, truststores, and critical configs it is usually better to use absolute paths.

Run the service under a dedicated least-privilege user/group. If using systemd sandboxing (ProtectSystem, ReadWritePaths, PrivateTmp...), test paths for writing logs, temporary files, heap dumps, and application data. Missing permissions might only appear during an incident, not necessarily right at startup.

### 8.3. Type=simple and Readiness

Type=simple is useful for a foreground Java process. However, systemd considering the process started is not synonymous with the application having finished initializing the database, cache, or HTTP endpoints. If the application needs stricter readiness semantics, health/readiness must be designed according to the appropriate stack.

Do not treat systemctl status returning active as proof that all business endpoints are ready.

## 9. systemd EnvironmentFile

Example:

~~~ini
[Service]
EnvironmentFile=-/etc/javaapp/javaapp.env
ExecStart=/usr/bin/java -Xmx768m -jar /opt/javaapp/app.jar
~~~

File javaapp.env:

~~~text
APP_ENV=production
LOG_LEVEL=INFO
~~~

EnvironmentFile has systemd syntax, **not automatically sourced by a shell**. A minus sign before the path indicates that a missing file can be ignored per the relevant syntax; for mandatory files, declare without a minus sign so a missing file is an operational error.

If the file contains:

~~~text
JAVA_OPTS=-Xmx1024m
~~~

the JAVA_OPTS variable still does not automatically become a Java command-line argument unless ExecStart or a wrapper has logic to use that variable.

### 9.1. Environment Expansion in systemd

systemd supports forms of variable substitution on the command line, yet splitting behavior between $VAR and braced forms is specific to systemd, not completely identical to a shell. If a variable contains multiple JVM arguments, check semantics for your exact systemd version.

In most simple services, place fixed flags directly in ExecStart or use a Java argument file, rather than relying on a variable string holding multiple flags that are brittle to parse.

### 9.2. Do Not Use systemd Environment as an Uncontrolled Secret Store

Environment variables may be exposed through diagnostic configuration or process environment if permissions allow. Do not put database passwords, private keys, or bearer tokens directly in ExecStart with -Dsecret=... .

On supporting systemd releases, consider credential mechanisms like LoadCredential or protected credential files that the application reads from an appropriate path. File read permissions and rotation lifecycles must be clearly defined.

## 10. systemd Drop-ins and Overriding ExecStart

If the unit is managed by a package or platform, use drop-ins instead of editing the vendor unit directly.

Example:

~~~sh
sudo systemctl edit javaapp.service
~~~

Override content:

~~~ini
[Service]
ExecStart=
ExecStart=/usr/bin/java -Xms384m -Xmx1024m -jar /opt/javaapp/app.jar --app.env=production
~~~

In standard service types like Type=simple, replacing the old ExecStart with a new line requires resetting the list first with an **empty ExecStart=**. Simply adding a second ExecStart can make the unit invalid.

### 10.1. Reloading and Applying Changes

~~~sh
sudo systemctl daemon-reload
sudo systemctl restart javaapp.service
sudo systemctl status javaapp.service
sudo journalctl -u javaapp.service -n 100 --no-pager
~~~

These are illustrative operational commands. Production restarts require change windows, replication/rolling strategies, and appropriate rollback plans.

Editing a unit file or EnvironmentFile **does not automatically alter flags on a running JVM**. For JVM options that only take effect at startup, a process restart is required.

### 10.2. Checking the Effective Unit

~~~sh
systemctl cat javaapp.service
systemctl show javaapp.service -p ExecStart -p Environment -p FragmentPath -p DropInPaths
~~~

Exercise caution when saving output because if the system is misconfigured and contains secrets in commands/environment, results can expose sensitive information. To verify which JVM flags truly took effect, additional observation from the Java process after restart is required.

## 11. systemd Resource Limits and JVM Ergonomics

systemd can manage resources via cgroups:

~~~ini
[Service]
MemoryMax=2G
CPUQuota=150%
TasksMax=1024
LimitNOFILE=65536
~~~

Meaning:

- MemoryMax is the memory limit of the service cgroup, not just Java heap.
- CPUQuota=150% grants a CPU time budget of roughly 1.5 CPUs when quota enforcement operates.
- TasksMax limits the number of tasks/threads per the relevant controller/policy.
- LimitNOFILE adjusts the OS file descriptor limit.

Do not set -Xmx equal to MemoryMax without accounting for Metaspace, code cache, thread stacks, direct buffers, native libraries, page cache, and other memory accounting items.

Do not set -XX:ActiveProcessorCount=8 assuming the container/service gets more CPU when the kernel only grants a quota equivalent to 1.5 CPUs.

When upgrading the JDK, record cgroups version, effective CPU count, heap max, GC threads, and memory usage; a newer JDK may detect container limits differently from an older JDK.

## 12. Logging and Diagnostic Paths in systemd

For a Java application running in the foreground, writing logs to stdout/stderr for journald collection can be simpler than leaving many unmanaged log files.

Example HotSpot unified GC logging on a supporting JDK:

~~~sh
java -Xlog:gc*:stdout:time,uptime,level,tags -jar app.jar
~~~

If a GC log file is needed:

~~~text
-Xlog:gc*:file=/var/log/javaapp/gc.log:time,uptime,level,tags:filecount=5,filesize=10m
~~~

When using file paths:

- Create the directory and set write permission for the right user.
- Ensure sandbox policy allows writing.
- Set disk quota/retention to avoid filling the disk.
- Distinguish GC logs from application logs.
- Consider sensitive data inside heap dumps/crash dumps.

Some older GC logging flags may have been replaced by unified logging or are no longer supported; verify on the target JDK.

## 13. Docker ENTRYPOINT and CMD

Docker/container images commonly provide ENTRYPOINT (default program) and CMD (default command/arguments), with two main declaration forms.

Exec form:

~~~dockerfile
ENTRYPOINT ["java", "-Xmx768m", "-jar", "/app/app.jar"]
~~~

Shell form:

~~~dockerfile
ENTRYPOINT java -Xmx768m -jar /app/app.jar
~~~

In Linux containers, exec form usually lets Java act directly as the main process. Shell form typically runs through a shell, which can alter signal forwarding and process supervision unless designed carefully.

### 13.1. Dockerfile Example

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
~~~

This is an example, not a prebuilt image. For real systems, pin image version/digest per policy, verify Linux OS/architecture, file permissions, and choose memory percentage from measurement results.

### 13.2. CMD to Pass Application Arguments

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

By default, CMD is appended as arguments after ENTRYPOINT. Because -jar is already in ENTRYPOINT, --server.port=8080 is an application argument.

**Do not put -Xmx in CMD in this example expecting it to change heap**: that parameter will end up after the JAR. To change JVM flags, change the ENTRYPOINT design, use a startup script/argument file, or use an appropriate launcher environment mechanism.

### 13.3. PID 1 and exec

A startup script used as ENTRYPOINT should end with:

~~~sh
exec java -jar /app/app.jar
~~~

when no separate supervisor needs to be kept. exec replaces the shell process with Java, letting signals and exit status go directly to Java. If using a dedicated init process to reap child processes, ensure proper SIGTERM forwarding.

A shell wrapper without exec can keep Java from receiving SIGTERM as intended and force the container to be killed after the termination grace period.

### 13.4. Do Not Package Production Secrets in the Dockerfile

Do not put private keys, passwords, or tokens into Dockerfile ENV/ARG or image layers. Secrets must be provisioned at runtime via a secret store/volume with access control. Do not log the entire environment in the entrypoint just to “make it easy to inspect”.

## 14. Kubernetes command and args

In a Pod spec:

- command generally overrides the image ENTRYPOINT.
- args generally overrides the image CMD.

These are **container command** concepts, not automatic Kotlin/Java main arguments. Kubernetes does not automatically verify whether -Xmx is placed properly before -jar.

### 14.1. Example Running Java Directly

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-example
spec:
  replicas: 2
  selector:
    matchLabels:
      app: java-example
  template:
    metadata:
      labels:
        app: java-example
    spec:
      containers:
        - name: app
          image: example/java-app:1.0
          command: ["java"]
          args:
            - "-XX:MaxRAMPercentage=60.0"
            - "-XX:+ExitOnOutOfMemoryError"
            - "-jar"
            - "/app/app.jar"
            - "--server.port=8080"
          ports:
            - containerPort: 8080
~~~

The image example/java-app:1.0 is a placeholder. Argument order is correct: JVM flags before -jar, application arguments after the JAR.

**Important:** Pod command in the example replaces the image ENTRYPOINT. If the old ENTRYPOINT was a wrapper setting up truststore, Java agent, or native library config, overriding it can skip those steps.

### 14.2. Override Only args When the Image Supports It

If the image ENTRYPOINT is already java -jar /app/app.jar and designed to receive application args:

~~~yaml
containers:
  - name: app
    image: example/java-app:1.0
    args:
      - "--app.env=staging"
      - "--server.port=8080"
~~~

These args are passed to the application. If the image uses a startup script with a different contract, inspect the script logic and Dockerfile before using it.

### 14.3. Kubernetes Does Not Automatically Launch a Shell with List Command

Not equivalent:

~~~yaml
command: ["java -Xmx768m -jar /app/app.jar"]
~~~

and:

~~~yaml
command: ["java", "-Xmx768m", "-jar", "/app/app.jar"]
~~~

In array form, the first element must designate the executable. If you intentionally need a shell:

~~~yaml
command: ["/bin/sh", "-c"]
args:
  - "exec java -Xmx768m -jar /app/app.jar"
~~~

then the image must contain the shell and quoting/exec must be managed properly. With distroless images, /bin/sh is usually absent; use an exec-form command or the built-in image entrypoint.

## 15. Environment in Kubernetes

Example passing application environment and launcher options:

~~~yaml
containers:
  - name: app
    image: example/java-app:1.0
    env:
      - name: APP_ENV
        value: "production"
      - name: JDK_JAVA_OPTIONS
        value: "-XX:MaxRAMPercentage=60.0 -Dapp.mode=production"
~~~

JDK_JAVA_OPTIONS can be helpful when wanting to keep the image ENTRYPOINT intact while adding options supported by the Java launcher. However, verify:

- The actual launcher uses the right JDK/version.
- Options are permitted via JDK_JAVA_OPTIONS.
- No flag conflicts with ENTRYPOINT or JAVA_TOOL_OPTIONS.
- Effective policy is verified on the real JVM.

Do not use environment as a channel for every launcher option, and do not attempt to insert -jar via JDK_JAVA_OPTIONS.

### 15.1. ConfigMap for Non-Sensitive Configuration

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: java-example-config
data:
  APP_ENV: "production"
  LOG_LEVEL: "INFO"
~~~

Can be referenced:

~~~yaml
envFrom:
  - configMapRef:
      name: java-example-config
~~~

Changing a ConfigMap **does not automatically update environment variables of an already started Java process**. Typically the Pod needs to be recreated/rolled out to pick up the new env. If mounting a ConfigMap as files, update propagation and application reload follow different semantics; JVM startup flags still do not update automatically.

### 15.2. Secret Volumes and Credential Files

For real secrets, prefer the platform's secret management mechanism per organizational policy. Example mounting a Kubernetes Secret:

~~~yaml
volumes:
  - name: credentials
    secret:
      secretName: java-example-credentials
containers:
  - name: app
    image: example/java-app:1.0
    volumeMounts:
      - name: credentials
        mountPath: /run/secrets/javaapp
        readOnly: true
~~~

The application must be designed to read the file at the proper path without logging its contents. Secrets are not automatically secure by default in every cluster; RBAC, auditing, encryption at rest, and rotation management are required.

Do not pass production passwords via -Ddb.password=... or --password=... because command lines and VM diagnostics can expose them.

## 16. Cgroup Resource Limits Differ from JVM Heap Settings

Example:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1500m"
    memory: "1Gi"
~~~

- requests.cpu relates to Kubernetes scheduling and resource allocation; it is **not a hard CPU cap**.
- limits.cpu is usually enforced via Linux CPU quota per runtime policy.
- requests.memory is used for scheduling and related policies.
- limits.memory is the container memory limit, not just heap.

If limit.memory=1Gi, setting -Xmx1g is usually risky because the JVM also has native/non-heap memory.

### 16.1. MaxRAMPercentage

With a container-aware JVM on a compatible runtime:

~~~text
-XX:MaxRAMPercentage=60.0
~~~

suggests to the JVM to compute ergonomic maximum heap based on a percentage of the underlying RAM it detects. If the baseline is a 1 GiB container, the rough calculation is around 614 MiB; the actual value depends on JDK ergonomics, other flags, and runtime conditions.

Do not use one fixed percentage for every workload. Systems using Netty/direct buffers, JNI, many platform threads, or agents may need larger native headroom.

### 16.2. CPU Count and Throttling

With a 1500m CPU limit, the JVM can observe an integer number of active processors depending on how the implementation computes from quota/cpuset. Runtime.availableProcessors() does not return 1.5.

~~~text
-XX:ActiveProcessorCount=2
~~~

can adjust JVM ergonomics, yet it does **not** grant additional CPU time. If kernel quota is low, extra GC/executor threads can cause CPU throttling and increased latency.

### 16.3. Changing JDK Can Change Behavior Even When YAML Is Unchanged

A target JDK may support cgroups v2 or read limits more effectively than an older JDK; consequently, default Xmx, active processor count, and GC thread count change. When comparing, record JDK vendor/update, kernel, cgroup mode, and actual effective flags.

## 17. Probes and Startup Time

Kubernetes has probes:

- startupProbe: supports configurable startup duration.
- readinessProbe: determines whether the Pod is ready to receive traffic.
- livenessProbe: detects states requiring restart per policy.

Example:

~~~yaml
ports:
  - containerPort: 8080
startupProbe:
  httpGet:
    path: /health/startup
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

The endpoints are examples; the application must actually expose them.

Upgrading the JDK can change startup time due to classloading, GC, agents, TLS, or frameworks. If probe thresholds are too low, a Pod can be restarted before finishing boot. If the readiness endpoint does not check necessary dependencies, the Pod can receive traffic too early.

Do not mechanically make the liveness probe depend on every external service and trigger restart loops when a dependency experiences a temporary disruption. Design health semantics according to system requirements.

### 17.1. Synchronizing Port and Host

If the application receives --server.port=9090 while Pod containerPort/probe/Service still point to 8080, the JVM may start fine while the Pod is not ready.

Check:

- Application bind port and network interface.
- Probe port/path.
- Service targetPort and ingress/backend configuration.
- Management port if different from application port.

Increasing probe timeouts will not fix a static error in port/path.

## 18. SIGTERM, Graceful Shutdown, and Termination Grace

When Kubernetes stops a Pod, the process usually receives SIGTERM per lifecycle rules and has a grace period before being force-killed if it has not stopped.

Example:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

If Java is PID 1 or signals are forwarded properly, the JVM can run shutdown hooks and the framework performs graceful shutdown as designed.

Java example:

~~~java
public final class ShutdownHookExample {
    public static void main(String[] args) throws Exception {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("Shutdown requested")));
        Thread.sleep(Long.MAX_VALUE);
    }
}
~~~

This is only a hook example; production shutdown logic must manage transactions, request draining, message consumption, timeouts, and resource cleanup.

### 18.1. Questions to Verify

1. Does Java receive SIGTERM directly?
2. How does readiness change state before stopping incoming traffic?
3. Do in-flight requests have reasonable time to complete?
4. Do background consumers, schedulers, and transactions stop safely?
5. Are systemd stop timeout and Kubernetes termination grace aligned?
6. When grace expires and SIGKILL occurs, what state could data be in?

Shutdown hooks are not guaranteed to run in all cases, such as SIGKILL or a native crash. Do not use a simple sleep in preStop to substitute for verified drain logic.

### 18.2. preStop

A Kubernetes preStop hook can support certain drain workflows, yet it consumes part of the termination grace period. If a hook exists, understand its timing, failure behavior, and signal ordering.

Do not add unconditional preStop sleeps merely to hide readiness propagation bugs or load balancer configuration issues.

## 19. VM Flags Changed or Removed When Upgrading Java

When migrating from an older JDK, startup may stop immediately:

~~~text
Unrecognized VM option
Error: Could not create the Java Virtual Machine
~~~

Possible causes:

- Option/collector no longer exists.
- Flag syntax changed.
- Flag belongs to a different JVM implementation.
- A legacy option now only prints a warning or has no effect.
- Option was split incorrectly by shell/systemd/YAML.

For example, configuration for a collector removed from a newer HotSpot JDK cannot be “fixed” by keeping it intact and adding a flag to ignore errors. You must select a newly supported collector and policy, then benchmark/compare behavior.

### 19.1. Checking on the Target JDK

~~~sh
java -version
java -XshowSettings:vm -version
java -XX:+PrintFlagsFinal -version
java -Xlog:help
~~~

These commands apply to HotSpot/JDK supporting the corresponding features; output can be very long or differ between vendors. Do not put raw VM flags/command lines containing secrets into public logs.

### 19.2. Do Not Hide Invalid Flags

Some JVMs offer ways to ignore unrecognized VM options. Using this mechanism indiscriminately can make service startup green while silently ignoring important settings for memory, GC, or security.

During migration, classify each flag: keep, replace with a new mechanism, or remove with explanation. Only use workarounds with explicit scope, expiration, and owner.

### 19.3. Module Flags and Reflective Access

Some legacy libraries may need:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

during the transition period. This is an example allowing controlled opening of a JDK package in the module system environment, not a flag to enable for every application.

If a dependency uses reflection to access internal JDK APIs, prioritize a compatible update. With workarounds, clearly document the opened package, requiring dependency, related tests, and removal plan.

**--add-opens does not restore classes/modules removed from the JDK.**

## 20. Java Agents and Native Agents

Java agents are typically loaded:

~~~sh
java -javaagent:/opt/agents/observability.jar -jar /opt/app/app.jar
~~~

Native JVMTI agents may use:

~~~sh
java -agentpath:/opt/agents/libobserver.so -jar /opt/app/app.jar
~~~

Check:

- Agent version supports the target JDK/class-file version.
- Native agent matches OS/CPU/ABI of the container/VM.
- File paths and permissions.
- Is an agent already added by image ENTRYPOINT and being added a second time by Kubernetes env?
- Does agent startup or dynamic attach have a new policy per JDK?
- Agent credentials are managed via a secret store, not exposed on the command line.

Do not load the same agent twice from both the command and JAVA_TOOL_OPTIONS/JDK_JAVA_OPTIONS. It can cause duplicate instrumentation, startup errors, or uncontrolled overhead.

## 21. Encoding, Timezone, and Truststore

Some system properties that commonly appear:

~~~text
-Dfile.encoding=UTF-8
-Duser.timezone=UTC
-Djavax.net.ssl.trustStore=/etc/myapp/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

These are examples of settings that may be needed, not a default flag set for every service.

### 21.1. Charset

Default charset has historically changed across JDK/OS/locale. For communication data and critical file formats, use an explicit Charset such as StandardCharsets.UTF_8 at APIs rather than only hoping -Dfile.encoding solves everything.

Overriding file.encoding can also have different limitations depending on the JDK release. Check the target runtime and regression tests on serialization/file I/O.

### 21.2. Timezone

-Duser.timezone can affect the default JVM timezone; it does not replace the database timezone, remote service timezone, Java libraries using explicit ZoneId, or OS clock policy.

Use Instant/ZoneId appropriately, and test date/time across timezones and DST boundaries if relevant to business logic.

### 21.3. Truststore

When moving from a VM to a container, previous truststore paths may not exist. Mount files/certificates at the right path with read permissions, format, and CA chain.

Do not disable certificate/hostname verification merely because TLS handshake fails after migration. Instead, investigate truststore, certificate chain, SAN, and Java security policy.

Especially avoid passing truststore passwords/private keys on the command line or printing them to JVM diagnostic logs.

## 22. Security of Startup Configuration

Startup parameters can be observed via process lists, systemd units, Pod specs, image metadata, JVM management tools, logs, or crash dumps depending on permissions.

Principles:

- Do not put passwords/API tokens/private keys directly into -D or --password arguments.
- Do not print entire commands/environments without redaction.
- Restrict who can edit systemd units, Kubernetes Deployments, and ConfigMaps.
- Use Secrets/credential files and secret managers where appropriate.
- Ensure the runtime user only has read permissions for the secrets it needs.
- Do not place log/agent/truststore directories in locations writable by untrusted actors.
- Manage checksums and provenance of Java agents/native libraries.
- Protect permissions on heap dumps/core dumps because they can contain sensitive information.

If using Java Security properties or custom crypto providers, govern them under reviewed policy; do not relax restricted TLS algorithms just to get past startup errors without security approval.

### 22.1. Configuration Drift Is Also a Security Risk

Two replicas with the same image yet receiving different flags may apply different security providers/truststores/agents. This creates inconsistent behavior, even to the point where one replica accepts a certificate or API that another replica rejects.

Version startup profiles, use GitOps or appropriate configuration management mechanisms, and verify rollouts across all instances.

## 23. Verifying Effective Flags from the Real JVM

After deployment, answer:

1. Which Java executable and runtime version are running?
2. Which flags/heap/GC/module options did the JVM receive?
3. Which arguments and profile did the application receive?
4. Have Environment/ConfigMap/Secret references been applied?
5. Were agent/truststore/classpath/module path loaded properly?
6. Does the process receive signals and operate within resource limits?

### 23.1. Safe Information from Java APIs

~~~java
public final class RuntimeSnapshot {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("availableProcessors=" +
                runtime.availableProcessors());
        System.out.println("maxHeapBytes=" +
                runtime.maxMemory());
    }
}
~~~

This program does not print all arguments/system properties because production startup may contain sensitive information. Runtime.maxMemory reflects the JVM heap limit, **not the total container memory limit**.

### 23.2. jcmd

On JDKs/JVMs allowing attach and having jcmd:

~~~sh
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.info
~~~

These commands assist diagnostics, yet may not exist in minimal runtime images or may be restricted by permissions/namespaces. VM.command_line can expose startup arguments; run in authorized environments and handle output safely.

### 23.3. systemd Diagnostics

~~~sh
systemctl status javaapp.service
systemctl cat javaapp.service
journalctl -u javaapp.service -n 100 --no-pager
~~~

Output helps view the unit, drop-ins, and startup failures. However, systemd config may have changed while the old JVM process has not restarted; verification from the running process remains necessary.

### 23.4. Kubernetes Diagnostics

~~~sh
kubectl describe pod <pod-name> -n <namespace>
kubectl get pod <pod-name> -n <namespace> -o yaml
kubectl logs <pod-name> -n <namespace>
~~~

Inspect image digest, command/args, environment references, probes, restarts, and Pod events. Do not print raw Secret values or all system properties to debug.

### 23.5. Host Java Version Is Not Sufficient

java -version outside on the host does not prove that a process inside a container or systemd uses the same Java executable. Only information from the exact process/image and inspection of the runtime task is enough to conclude.

## 24. Testing Before and After Migration

Organize tests across three deployment layers:

| Layer | Required Tests |
|---|---|
| Script | Shebang, executable path, quoting, forwarding "$@", JVM flags before -jar, exec, signal forwarding, exit status. |
| systemd | Unit parsing, EnvironmentFile, drop-in replacement, service user, cgroup limits, journald, stop/restart. |
| Docker/Kubernetes | ENTRYPOINT/CMD, command/args, env/ConfigMap/Secret, memory/CPU, probes, PID1, graceful shutdown. |

### 24.1. Positive Path Tests

1. Start the artifact on the target JDK.
2. Verify runtime Java vendor/version.
3. Verify effective heap, processors, modules, and agents.
4. Invoke health endpoints / CLI functionality.
5. Check database, TLS, and messaging connectivity per application needs.
6. Send SIGTERM in a test environment and verify graceful shutdown.
7. Verify logs/diagnostics are collected safely.

### 24.2. Negative Tests

| Scenario | Expectation |
|---|---|
| JVM flag removed from the JDK | Startup/CI detects visibly, does not silently ignore. |
| Wrong Java executable path | Clear error message, does not automatically use another JDK against policy. |
| Argfile does not exist | Startup fails diagnosably. |
| Agent JAR or native agent for wrong platform | Smoke test detects prior to rollout. |
| Mandatory secret missing | Fails closed without printing sensitive values. |
| Truststore missing CA/unreadable | TLS test fails safely without disabling verification. |
| Wrong Kubernetes port/probe | Staging detects Pod not ready. |
| Container receives SIGTERM | Stops per policy and termination grace. |
| Memory/CPU limit too tight | Capacity test detects throttling/OOM risk. |

Negative tests must be carried out in recoverable test environments, never by deliberately breaking production services.

## 25. Startup Comparison Table Between Old and New Environments

| Component | Baseline | Target JDK/Deployment | Evidence |
|---|---|---|---|
| Java executable/version | Currently running JDK | Target JDK/vendor/update | Process metadata, java -version in the exact runtime. |
| JVM flags | Current GC/heap/module/agent flags | Still-supported flags | VM.flags, startup test. |
| Main selector | -jar/-cp/-m | Target packaging | Runtime start. |
| Application arguments | Profile/port/config | Unchanged or versioned contract | Integration tests. |
| System properties | -D settings | Controlled settings | Redacted app diagnostics. |
| Environment | Script/systemd/Kubernetes env | New sources and precedence | Deployment inspection. |
| Heap/CPU limits | Host/cgroup baseline | New runtime constraints | JVM metrics, cgroups. |
| Security | User, truststore, secrets | Matching policy and mounts | Security integration tests. |
| Logging | GC/application paths | Stdout/journald/collector | Log collection checks. |
| Agents | Java/native agents | Versions supporting target JDK/OS | Agent load smoke tests. |
| Lifecycle | Stop/restart behavior | Graceful shutdown + probes | SIGTERM/staging test. |

Do not equate “the JVM starts” with “the application is production-ready”. Requests/transactions/connections and lifecycle must be tested in a realistic environment.

## 26. Investigating Common Failures

### 26.1. Flag Placed After -jar

Symptom: Pod has smaller Xmx than expected even though YAML contains -Xmx1g.

Inspect command/args and the Java process: if -Xmx1g is after /app/app.jar, it is an application argument. Move it before -jar or use the proper JVM option source.

### 26.2. JAVA_OPTS Does Not Work

Symptom: ConfigMap has JAVA_OPTS, yet heap does not change.

A common cause is that the image ENTRYPOINT does not read JAVA_OPTS. Check the startup script/image contract and effective VM flags; switch to a supported mechanism such as direct launcher options or JDK_JAVA_OPTIONS when appropriate.

### 26.3. systemd Service Does Not Read Shell Syntax

Symptom: ExecStart contains pipes, redirection, or shell-style variables and the service fails to start or arguments are wrong.

Fix to systemd ExecStart semantics, use a dedicated script if a shell is truly needed, and end the script with exec Java.

### 26.4. Kubernetes command Overrides ENTRYPOINT

Symptom: after migration, a Java agent disappears or certificate setup is missing even though the image did not change.

Inspect the Dockerfile and Pod command: if the Pod overrides the entire ENTRYPOINT, logic in the image script does not run. Restore the contract or bring necessary steps into a tested new startup configuration.

### 26.5. Old/New JVMs Detect Heap Differently

Symptom: same memory limit, different Runtime.maxMemory.

Compare JDK vendor/update, cgroups v1/v2, Xmx/MaxRAMPercentage, UseContainerSupport, and ancestor cgroup limits. This may be an ergonomic change rather than a heap leak.

### 26.6. JVM Is OOMKilled Even Though Heap Is Not Full

Investigate non-heap/native memory, direct buffers, thread stacks, page cache, container memory events, and image limits. Java OutOfMemoryError differs from a kernel/container OOM kill; exit code 137 alone does not prove the root cause.

### 26.7. Rollout Reports Running but Not Ready

Check startup/readiness probes, port, bind address, truststore, dependency initialization, and startup duration. A live process does not prove it is eligible to receive traffic.

### 26.8. SIGTERM Does Not Reach the JVM

Check PID 1 and the startup script. If a shell does not exec/forward signals properly, Kubernetes may resort to SIGKILL after the grace period; fix process lifecycle instead of merely increasing timeout.

## 27. Workflow for Changing Startup When Upgrading JDK

**Step 1 — Inventory:** identify who starts Java (script, systemd, Docker ENTRYPOINT, Kubernetes command, application server), which JDK, and which options already exist.

**Step 2 — Lock Runtime Contract:** record minimum/runtime JDK, application profile, heap/CPU policy, module access, agent, logging, security, and lifecycle.

**Step 3 — Classify Flags:** still-supported flags, removed flags, flags needing replacement, legacy workarounds, and debug-only flags.

**Step 4 — Pick One Configuration Source:** decide which settings reside in script/image, systemd unit/drop-in, argfile, env, or application configuration; avoid implicit conflicts.

**Step 5 — Standardize Syntax:** VM options before main selector, quote paths, forward arguments, systemd parse rules, Docker ENTRYPOINT/CMD, Kubernetes command/args.

**Step 6 — Security:** keep secrets out of command lines, protect truststore/log/heap dump, manage agent provenance and filesystem permissions.

**Step 7 — Start on Target JDK:** use the exact artifact/container/unit, verify Java runtime and effective JVM flags.

**Step 8 — Test Functionality and Lifecycle:** run integrations, probes, GC/resource metrics, SIGTERM, shutdown hooks, and restart/rollout.

**Step 9 — Store Evidence:** artifact/image digest, unit/manifest revision, Java version, flags, resource limits, test results, and what has not been tested.

**Step 10 — Rollout and Rollback:** canary/staging first, monitor crash loops, OOMKilled, readiness, latency/GC, and TLS errors; prepare rollback for artifact, startup config, and secret references.

## 28. Startup Configuration Report Template

~~~text
Service/module:
Artifact version + checksum:
JDK vendor/version/update:
Runtime: script / systemd / Docker / Kubernetes
OS/architecture + image digest:

Launcher:
  Java executable:
  Main selector: -jar / -cp + main / -m
  JVM options source:
  Application arguments source:
  Environment/config references:
  Agent paths + versions:

Effective JVM:
  Heap initial/max:
  GC collector/logging:
  Active processors:
  Module flags:
  Encoding/timezone:
  Certificate/truststore policy:

Deployment and lifecycle:
  Service user:
  CPU/memory requests/limits:
  PID1/signal forwarding:
  Graceful shutdown duration:
  Startup/readiness/liveness probes:
  Log/dump permissions:

Security:
  Secrets absent from plain-text command arguments:
  Credentials/protected files:
  Agent/native artifact provenance:

Validation:
  Startup:
  Runtime flags:
  Application integration:
  SIGTERM/shutdown:
  Resource/GC:
  Deployment rollout:
  Known gaps and blockers:
~~~

The table above is a data-collection framework when verifying a migration, not completed test results. Store only metadata sufficient for reproduction and diagnosis, avoiding attaching secrets to documents.

## 29. Conclusion

**Startup parameters are a direct component of Java compatibility.** The same JAR can behave differently when JVM flags are misplaced, JAVA_OPTS is not handled by scripts, systemd parses commands differently from Bash, a container loses ENTRYPOINT logic, or Kubernetes changes command/args and resource limits. Newer JDKs can also change VM flag support, container-awareness, GC ergonomics, and module access.

A sustainable approach needs to clearly separate **JVM options, application arguments, environment settings, secrets, and deployment lifecycle/resource configuration**. Startup scripts must manage quoting and exec; systemd needs explicit units/drop-ins; Kubernetes must be compatible with image entrypoints, probes, and graceful shutdown. Every change must be verified from the **actual running JVM**, alongside integration tests, resource metrics, and a rollback plan.

The destination of Java Advance Compatibility Migration is not merely a java command that starts successfully, but **a runtime configuration that can be reproduced, version-controlled, and verified across deployment environments**, helping maintain business behavior, stability, and security after upgrading the JDK.