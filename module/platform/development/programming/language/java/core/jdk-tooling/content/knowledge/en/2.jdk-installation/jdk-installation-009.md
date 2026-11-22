# JDK in Containers

Containers allow you to package a Java application along with its runtime environment and required configuration into a single unit that can be deployed consistently across developer machines, test environments, and production servers. When working with Java in containers, it is important to distinguish between a **container image**, a **running container**, a **JDK used for building**, and a **runtime used for running the application**. These concepts determine image size, diagnosability, resource consumption, and how the application shuts down gracefully.

This article uses Docker as an example because it is a widely used interface for working with OCI container images. The principles regarding images, processes, resource limits, and filesystems also apply to many other container platforms.

## 1. Container Images and Containers

### Container Image

A **container image** is an immutable package from a usage perspective, containing the filesystem, metadata, and default configuration needed to create a container. An image is typically built from multiple layers. Each build instruction can create a layer or modify metadata; layers are cached and can be shared across multiple images.

A Java image typically contains:

- A base operating system or minimal filesystem.
- A JVM and runtime libraries.
- The application's JAR file, class files, or runtime image.
- Metadata such as the working directory, user, entrypoint, and default command.

An image is not a full virtual machine. It uses the host operating system's kernel through the OS container mechanism.

### Container

A **container** is an instance created from an image that is either running or exists in a stopped state. A container has its own process, writable filesystem, network configuration, and resource limits according to the runtime configuration.

Multiple containers can be created from the same image. Containers typically share the read-only layers of the image, while each container has its own writable layer. Data in the writable layer is generally not meant for persistent storage; when a container is removed, its private data is also lost.

### Images, Containers, and Volumes

| Component | Role | Data Lifecycle |
|---|---|---|
| Image | Filesystem and configuration template for creating containers | Stored and reused across multiple runs |
| Container writable layer | Changes generated within a single container | Typically lost when the container is removed |
| Volume or bind mount | Stores data outside the container lifecycle | Can persist after the container is removed |

For Java applications, treat the image as the deployment artifact, the container as the running application process, and the volume as the place to store data that must survive container replacements.

## 2. JDK Images and Runtime Images

### Using a JDK for Compilation

A JDK contains the compiler and development tools such as javac, jar, javadoc, and javap. Therefore, a JDK image is suitable for the build stage:

- Compiling Java source code into class files.
- Packaging JARs.
- Running tests or build tasks that require JDK tools.
- Analyzing dependencies or creating a custom runtime with jlink.

You do not necessarily need to include the entire JDK in a production image if the application only needs to run.

### Using a JRE or Runtime Image for Execution

A runtime image needs the JVM and the libraries the application requires to execute. It can come from a JRE image published by a vendor or from a custom runtime created with jlink.

A smaller runtime image can reduce the amount of data to download and the number of unnecessary components. On the other hand, development and diagnostic tools such as javac or jcmd may not be present.

Keep the distinction in mind:

- **JDK image:** convenient for building and diagnostics, typically larger.
- **JRE/runtime image:** suitable for running applications, typically has fewer tools.
- **Custom runtime image:** a runtime selectively built from only the required modules, usually using jlink.

Choosing an image should be based on actual requirements. If the application needs JNI, agents, native libraries, or diagnostic tools, verify that the chosen runtime image includes all compatible components.

## 3. Choosing a Base Image

A **base image** is the foundation image specified in the FROM instruction of a Dockerfile. Java base images are typically published by JDK vendors, such as Eclipse Temurin or other OpenJDK providers.

Common image name examples:

- eclipse-temurin:21-jdk: JDK 21, suitable for compilation.
- eclipse-temurin:21-jre: Java 21 runtime, suitable for running applications.
- Variants with OS or architecture suffixes: specify a more particular underlying environment.

Tag names are for illustration only. Check whether the tag is still published by the vendor for your target architecture and deployment platform.

When choosing a base image, consider:

1. **Java version:** match the target version against which the application is compiled and tested.
2. **Vendor:** choose a vendor with an appropriate update and support policy.
3. **Base operating system:** some images use Debian/Ubuntu or Alpine; native libraries may depend on libc.
4. **CPU architecture:** the image must be compatible with the deployment host, such as linux/amd64 or linux/arm64.
5. **Size and tools:** minimal images reduce footprint but may lack a shell, package manager, or debugging tools.
6. **Reproducibility:** tags can be updated over time. For builds requiring strict reproducibility, consider pinning a specific patch version or image digest, while maintaining an intentional security update process.

### Alpine, glibc, and musl

Alpine Linux is often chosen because of its small base image and use of musl libc. Many pure-bytecode Java applications run well on Alpine, but native libraries or JNI may be compiled against glibc. When using Alpine, test native components, agents, monitoring tools, and system libraries.

Images based on Debian or Ubuntu typically use glibc and may be more compatible with common native libraries. Image size is only one factor; compatibility and operational stability are equally important.

### Distroless and Minimal Images

Minimal or distroless images usually keep only the runtime and essential files. Some images have no shell or package manager. This reduces the attack surface and footprint, but changes how you debug directly inside a container. You should have an observability workflow via logs, metrics, JFR, or a separate debug image.

## 4. Dockerfile and Multi-Stage Builds

A **Dockerfile** describes how to build an image. A Dockerfile can have multiple stages. A **multi-stage build** uses one stage with a JDK to compile, then copies only the artifacts needed to run into the runtime stage.

This keeps the final image from carrying source code, compilers, build caches, or tools needed only during development.

### Small Java Application Example

Directory structure:

~~~text
jdk-container-demo/
├── Dockerfile
├── .dockerignore
└── src/
    └── com/
        └── example/
            └── Main.java
~~~

Main.java file:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from Java in a container!");
    }
}
~~~

Dockerfile:

~~~dockerfile
# Stage 1: compile with a full JDK
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY src ./src
RUN mkdir -p /out && javac --release 21 -d /out src/com/example/Main.java

# Stage 2: run with a smaller runtime image
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build --chown=10001:10001 /out/ /app/
USER 10001:10001
ENTRYPOINT ["java", "-cp", "/app", "com.example.Main"]
~~~

.dockerignore file:

~~~text
.git
.idea
*.iml
target
build
.gradle
.env
~~~

Build the image from the project root directory:

~~~bash
docker build -t jdk-container-demo:local .
~~~

Run the container:

~~~bash
docker run --rm --name jdk-container-demo jdk-container-demo:local
~~~

Output:

~~~text
Hello from Java in a container!
~~~

Explanation:

- The build stage uses JDK 21 to compile source code with javac.
- The --release 21 option sets the target Java API level and class file version to Java 21.
- The -d /out option places compiled class files into the output directory.
- The runtime stage uses a JRE 21 image.
- COPY --from=build copies only the compiled class files from the previous stage.
- --chown sets ownership of the copied files to UID/GID 10001.
- USER runs the process under a non-root UID/GID.
- The JSON (exec form) ENTRYPOINT launches Java directly without going through a shell.

This example assumes Docker is installed, the daemon is running, and the base image tag is supported on the current platform. For real-world projects, replace the single javac command with the appropriate Maven or Gradle build process, then copy only the required JAR or runtime artifact into the final stage.

## 5. Layers, Build Context, and Cache

Docker sends the **build context** to the builder. The dot in `docker build -t ten-image .` means the current directory is the build context. Files in the context can be used by COPY or ADD instructions.

The .dockerignore file excludes items that do not need to be sent into the build context, such as:

- The .git directory, IDE metadata, and temporary files.
- Old build output directories such as target or build.
- Unnecessary dependency caches.
- Local configuration files or secrets.

**Layer cache** allows the builder to reuse results from unchanged build steps. For Maven or Gradle projects, structure the Dockerfile so that dependency descriptor files are copied before source code, followed by downloading dependencies and compiling. When only source code changes, the dependency download steps can be cached.

Avoid including the entire working directory, the .git folder, or secrets in the image. A secret once copied into a layer can still exist in the image history even if a later layer deletes that file.

## 6. Application Configuration and Data

### Environment Variables

Non-sensitive configuration can be passed via environment variables:

~~~bash
docker run --rm -e APP_MODE=production jdk-container-demo:local
~~~

The Java application can read it using `System.getenv("APP_MODE")`. Keep environment-specific configuration outside the image so that the same artifact can run in development, test, and production.

### Secrets

Do not hardcode passwords, tokens, or private keys in a Dockerfile, source code, image layers, or standard build arguments. Environment variables can also be exposed through inspect tools, process configurations, or logging systems. Use secret mounts or your deployment platform's secret management mechanism, restrict access permissions, and rotate secrets according to policy.

### Volumes and Bind Mounts

A container filesystem can be replaced when deploying a new version. If the application needs to persist data long-term, use a volume or an external storage service. Example of mounting a data directory:

~~~bash
docker run --rm -v app-data:/app/data jdk-container-demo:local
~~~

In this example, `app-data` is a Docker-managed named volume. For production applications, clearly define which data is ephemeral, which data must persist long-term, and who is responsible for backups.

### Logging

Containerized applications typically write logs to stdout and stderr for the runtime to collect. Avoid writing logs only to files inside the container's writable layer, as logs can be lost when the container is replaced. If log files are required, configure a proper storage location and clear rotation policy.

## 7. The JVM and Container Resource Limits

Containers can be constrained by CPU and memory limits. The JVM needs to see these limits to choose appropriate heap sizes, thread counts, and runtime settings.

### Memory Limits and the Java Heap

Example of setting memory and CPU limits for a container:

~~~bash
docker run --rm --memory=512m --cpus=1.5 jdk-container-demo:local
~~~

With modern HotSpot builds on Linux, the JVM is aware of container resource limits via cgroups. Exact behavior depends on the JDK version, vendor, kernel, and container configuration.

Do not assume the entire container memory limit is available for the Java heap. The process's total memory usage can include:

- Java heap: allocated Java objects.
- Metaspace: class metadata.
- Thread stacks: stack memory for threads.
- Direct buffers and native memory regions.
- JIT code cache, native libraries, GC structures, and other runtime components.

If Xmx is set equal to the entire memory limit, the process can still exceed the container limit due to native and non-heap memory, and be terminated by the OS with an OOM kill.

You can adjust the maximum heap percentage relative to the RAM detected by the JVM:

~~~bash
docker run --rm --memory=512m --cpus=1.5 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0" \
  jdk-container-demo:local
~~~

`MaxRAMPercentage` sets the maximum percentage of memory the JVM is allowed to use for the heap. The value `60.0` is only an example; measure actual usage and leave enough headroom for native memory, metaspace, thread stacks, buffers, GC, and agents. No single percentage fits every application.

To inspect the system information detected by the JVM on JDKs that support this option:

~~~bash
java -XshowSettings:system -version
~~~

This command prints system and resource information as seen by the JVM. Compare it against the container's actual memory limit and CPU quota.

### CPU Limits

CPU limits affect the number of processors seen by the JVM and the application. Mechanisms such as garbage collection, the common ForkJoinPool, and thread pools may rely on the available processor count. If the detected CPU count does not match the actual quota, you can consider the `-XX:ActiveProcessorCount=N` flag on supported JDKs. Only set this flag after measuring and understanding its impact on the application.

### OOM and Memory Diagnostics

If a container is terminated for exceeding its memory limit, there may be no Java `OutOfMemoryError` in the logs because the kernel or runtime killed the process. Check the container status, OOM events, memory usage, heap configuration, and native memory. Distinguishing Java heap exhaustion from a container-level OOM is a key step when investigating incidents.

## 8. Processes, Signals, and Graceful Shutdown

Containers are typically designed to run one main process. When running Java, the JVM should be the main process of the container.

The JSON ENTRYPOINT format in the earlier example:

~~~dockerfile
ENTRYPOINT ["java", "-cp", "/app", "com.example.Main"]
~~~

is the **exec form**. It invokes Java directly. The shell form can insert a shell as an intermediate process, making signal forwarding and process management more complicated.

When stopping a container, Docker typically sends SIGTERM to the main process and waits for a grace period before sending SIGKILL. The JVM can run **shutdown hooks** when it receives an appropriate termination signal. The application should use hooks or framework lifecycle mechanisms to:

- Stop accepting new work.
- Complete or cancel in-flight work within a deadline.
- Flush logs and necessary data.
- Close connection pools, executors, and resources.
- Exit before the grace period expires.

You can specify a custom stop timeout:

~~~bash
docker stop --time 30 ten-container
~~~

This duration should align with the application's shutdown time and deployment policy. If the application needs more time, configure the grace period on the corresponding orchestration platform.

## 9. Diagnosing Java Applications in Containers

Combine information from the application, the JVM, and the container runtime:

| Tool or Command | Purpose |
|---|---|
| docker logs | Read container stdout and stderr |
| docker stats | Monitor CPU, memory, network, and block I/O |
| docker inspect | View container configuration, state, mounts, and limits |
| docker exec | Run a command inside a running container |
| jcmd | Send diagnostic commands to the JVM |
| jstack | Capture thread dumps |
| jmap | Collect heap information or heap dumps depending on version capabilities |
| jfr | Record and analyze Java Flight Recorder events |

Example of retrieving the JVM version in a running container that has JDK tools:

~~~bash
docker exec ten-container jcmd 1 VM.version
~~~

This command assumes the Java application is PID 1 in the container and the image includes jcmd. If the runtime image does not contain these tools, you can use a separate debug image or an observability approach suited to the platform. Attach tools can also be restricted by user, namespace, process permissions, and JVM configuration.

Avoid adding the full JDK and a shell to a production image solely for debugging convenience if doing so conflicts with security requirements. Define a diagnostic workflow in advance: logs, metrics, JFR, heap dumps, thread dumps, and where diagnostic artifacts are stored.

## 10. Security and Operations for Java Images

Several principles to apply when building images:

1. **Run as non-root:** use USER with an appropriate UID/GID, and grant write permissions only to directories that truly need them.
2. **Use multi-stage builds:** remove compilers, build caches, and source code from the runtime image when not needed.
3. **Keep base images updated:** track security patches for both the JDK and the base operating system.
4. **Pin versions intentionally:** specific tags or digests aid reproducibility; pair this with an upgrade process to receive new patches.
5. **Do not bake in secrets:** pass secrets through a secret management system and restrict access scope.
6. **Limit container privileges:** avoid granting privileged mode or unnecessary system capabilities.
7. **Keep the filesystem minimal:** include only required packages, files, and libraries.
8. **Monitor resources:** configure appropriate memory/CPU limits, and track OOM events and shutdown times.
9. **Test images on target architectures:** especially when using JNI or native libraries.
10. **Separate configuration from artifacts:** the same image should be deployable across multiple environments via external configuration.

If a read-only filesystem is enabled, determine in advance whether the application writes to `/tmp`, log directories, or data directories. Paths that require writes must be backed by a writable mount or a suitably sized tmpfs.

## 11. Common Issues

### Container Killed by OOM Even Though Heap Is Not Full

The memory limit applies to the entire process and its related memory regions, not just the Java heap. Check the heap, metaspace, direct buffers, thread stacks, native memory, and actual usage. Adjust Xmx or MaxRAMPercentage to leave headroom.

### Works Locally but Fails in the Container

Causes can include a different JDK version, missing native libraries, different CPU architecture, missing configuration files, different relative paths, or unset environment variables. Inspect the actual image, JDK version, filesystem, and runtime configuration.

### Production Image Lacks javac or jcmd

This may be intentional for a minimal runtime image. Use a JDK in the build stage and design a separate debugging workflow. Do not assume every Java image contains full JDK tools.

### Application Does Not Stop on Time

Check whether ENTRYPOINT uses the exec form, whether the JVM receives SIGTERM, whether shutdown hooks complete within the grace period, and whether the application blocks shutdown threads with non-terminating tasks.

### Native Library Fails to Load on Alpine

Check whether the library was compiled for musl or glibc, CPU architecture, system dependencies, and ABI version. Test a base image compatible with the library before changing application code.

### Every Build Re-downloads Dependencies

Order the Dockerfile so dependency steps are cached before the source code COPY step. Ensure the build context does not change unnecessarily and `.dockerignore` excludes locally generated directories.

### Data Disappears After Deployment

A container's writable layer has a lifecycle tied to the container. Move data that needs long-term persistence to a volume, database, or object storage; define backups and migrations separately.

## 12. Checklist for Running Java in Containers

- Choose the right JDK version and vendor for the project.
- Use a JDK image for building; consider a JRE or custom runtime image for production.
- Create a multi-stage build so the final image contains only the artifacts needed to run.
- Configure `.dockerignore` to exclude build outputs, caches, IDE files, and secrets from the build context.
- Use the exec form for ENTRYPOINT so the JVM receives signals directly.
- Run the application with a non-root UID/GID.
- Externalize configuration from the image and use a secret manager for sensitive data.
- Store data requiring long-term persistence in volumes or external storage services.
- Set memory/CPU limits and verify that the JVM detects container limits.
- Leave headroom for native and non-heap memory when choosing Xmx or MaxRAMPercentage.
- Ensure the application handles SIGTERM and shuts down within the grace period.
- Write logs to stdout/stderr and prepare a workflow for capturing JFR, thread dumps, or heap dumps.
- Test the image on the target CPU architecture and deployment environment.
- Track security updates for the JDK and base image.

## 13. Key Terms to Remember

| Term | Meaning |
|---|---|
| Container image | Filesystem and metadata package used to create containers |
| Container | Running or stopped process instance created from an image with its own configuration |
| Base image | Foundation image used in a Dockerfile |
| Build stage | Stage that produces artifacts, typically using a JDK |
| Runtime image | Image containing the environment needed to run the application |
| Multi-stage build | Build process with multiple stages that copies only necessary artifacts to the final stage |
| Build context | Set of files sent to the builder when running docker build |
| Layer cache | Mechanism for reusing results of build steps |
| Volume | Storage area decoupled from the container lifecycle |
| cgroup | Kernel mechanism for grouping and limiting process resources |
| Container awareness | Ability of the JVM to detect container CPU and memory limits |
| MaxRAMPercentage | Flag setting the maximum percentage of RAM the JVM uses for the heap |
| Exec form | JSON-array way of declaring a command to run a process directly |
| SIGTERM | Signal requesting a process to terminate gracefully |
| Shutdown hook | Hook the JVM can execute during the shutdown process |
| JNI | Mechanism for Java to invoke native code |
| jlink | Tool for creating a runtime image from selected modules |
| Distroless | Image style keeping only the runtime and necessary application files |

When packaging a Java application, determine in turn **which JDK is used to build, which runtime is used to run, how container resources are limited, and how the JVM will receive termination signals**. These four questions help design images that are lean, stable to operate, and easier to diagnose.