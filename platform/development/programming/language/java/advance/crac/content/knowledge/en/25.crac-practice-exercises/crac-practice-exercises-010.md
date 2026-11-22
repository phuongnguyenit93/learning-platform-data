# Packaging and Restoring Applications in Linux Containers

Packaging a Java application using CRaC (Coordinated Restore at Checkpoint) in a Linux container requires preparing both the application image and an environment capable of checkpointing and restoring processes. The container image contains the application, a CRaC-enabled JDK, and system libraries. A checkpoint is created while the application is running, saving the process state along with the necessary image files, and is then restored using the exact same JDK and compatible CRaC mechanism.

This practice exercise builds a small Java HTTP server, packages it into a Linux container, creates a checkpoint, and then restores the application from the checkpoint. Along the way, you will check CRIU on the Linux host, configure a volume to store the checkpoint, handle network listeners via CRaC callbacks, verify the application after restore, and recognize the limitations when moving checkpoints between containers or nodes.

There is a distinction to make right from the start: **JDK CRaC checkpoint** coordinates Java Resource callbacks with the process checkpoint/restore mechanism. The **Docker container checkpoint** feature can also use CRIU, but it is a container runtime-level mechanism with a different lifecycle. These two approaches cannot be substituted for each other simply by changing the command name.

## 1. Objectives and Practice Architecture

After completing this exercise, you will be able to:

- Build a JAR that registers a CRaC Resource.
- Run the application using a Linux JDK with CRaC support.
- Prepare the Linux host and CRIU for checkpoint/restore.
- Store the checkpoint in a separate volume, without mixing it into the application image.
- Use pre-checkpoint callbacks to stop listeners and workers.
- Create a checkpoint using the JDK tool.
- Restart the application from the checkpoint using the mechanism provided by the JDK.
- Check the HTTP endpoint and logs to confirm the restore.
- Package metadata to know which image/JDK a checkpoint was created from.

Overview model:

~~~text
Source code + CRaC API
        |
        v
Gradle build
        |
        v
Application JAR
        |
        v
Linux container image
  - CRaC-enabled JDK
  - application JAR
  - native dependencies
        |
        v
Run and warm up application
        |
        v
JDK CRaC checkpoint command
        |
        v
Checkpoint directory on persistent volume
        |
        v
Compatible Linux restore environment
        |
        v
JDK CRaC restore
        |
        v
afterRestore callbacks
        |
        v
HTTP server ready
~~~

A checkpoint is not a cache layer that can be arbitrarily copied to any image. It is the state of a specific process, tied to the JDK, native runtime, kernel, CPU, namespaces, and the resources the process is using. Use the same image digest and a restore environment that has been verified as compatible throughout this exercise.

## 2. Preparing the Linux Environment

This exercise requires a Linux host or Linux VM with a suitable kernel and system permissions. You can use a dedicated Linux machine or a virtualization environment that supports the required CRIU features.

Required components:

| Component | Role |
|---|---|
| Linux kernel | Provides process, memory, namespace, and checkpoint-related features |
| CRIU | Dumps/restores process state at the operating system level |
| Docker Engine or equivalent runtime | Runs containers with the required configuration |
| CRaC-enabled JDK | Provides the CRaC API and checkpoint/restore commands |
| Gradle | Builds the application JAR |
| curl | Sends HTTP test requests |
| Persistent volume/directory | Stores checkpoint files outside the container's writable layer |

### 2.1. Checking Kernel and Architecture

Run on the Linux host:

~~~bash
uname -a
uname -r
uname -m
cat /etc/os-release
lscpu
~~~

Record the kernel release, architecture, and CPU features. A checkpoint created on x86-64 needs to be restored in an environment compatible with the architecture and CPU constraints of the JDK/CRIU. Do not use an x86-64 checkpoint for ARM64 just because both hosts run Linux.

### 2.2. Checking CRIU

Install CRIU via your distribution's package manager or according to the platform's official instructions. Then run:

~~~bash
criu --version
sudo criu check
~~~

The `criu check` command checks several kernel capabilities and current permissions. A successful result is an initial condition, not proof that every Java workload can be restored. You need to test with the exact container, JDK, namespaces, and resources of the application.

If the command reports missing capabilities or kernel features, check the logs and host configuration. Requirements may vary by kernel and CRIU version; do not assume that a newer container image will automatically add missing capabilities to the host kernel.

### 2.3. Docker Desktop, WSL2, and Remote Linux Machines

Containers on Linux share the kernel with the host. Therefore, the fact that the Docker CLI runs on Windows or macOS does not mean that environment has sufficient CRIU features to perform this lab.

If using Windows, run the checkpoint/restore part inside a Linux VM or a supported Linux host. WSL2 or Docker Desktop is only suitable when the kernel, permissions, namespaces, and container runtime integration actually meet CRaC/CRIU requirements. Check `criu check` in the Linux environment where the process will be checkpointed.

### 2.4. Checking Docker Engine

~~~bash
docker version
docker info
~~~

You need to determine the Docker Engine version and how the daemon is configured. If using rootless containers, user namespaces, or a Kubernetes runtime, permission requirements and restore methods can differ significantly from rootful Docker Engine on Linux.

## 3. Creating the Project Structure

Create a small project:

~~~text
crac-container-lab/
├── build.gradle
├── settings.gradle
├── Dockerfile
├── .dockerignore
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── CracHttpApp.java
~~~

The checkpoint directory will be created separately when running the container. Do not include the checkpoint in the JAR or package it as a fixed part of the image if the goal is to manage the image and checkpoint as two artifacts with different lifecycles.

### 3.1. settings.gradle

~~~groovy
rootProject.name = 'crac-container-lab'
~~~

### 3.2. build.gradle

This example uses Java 21 and the CRaC API. The API version must be compatible with the CRaC JDK distribution you choose; verify the artifact version in the repository and distribution documentation before locking the version for production.

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.crac:crac:1.4.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.CracHttpApp'
        )
    }
}
~~~

If your CRaC JDK provides the API under a different dependency version, update the dependency accordingly. Do not choose a JDK solely by major version; use the exact distribution/build that has been tested with CRaC.

### 3.3. .dockerignore

~~~text
.gradle
build/tmp
.git
.idea
.vscode
*.iml
checkpoint
~~~

Do not include the checkpoint directory in the Docker build context. This avoids accidentally copying memory images into the application image, bloating the image and mixing two artifacts with different lifecycles.

## 4. Writing a Java Application with a CRaC Resource

The application will open an HTTP server on port 8080. Before checkpointing, it stops the listener and executor so it does not hold active sockets or workers in the state to be restored. After restore, the callback creates a new listener and executor.

In production, you need to drain in-flight requests and close other clients such as JDBC, Redis, HTTP, or message brokers according to each library's contract. This lab uses an HTTP server to illustrate the resource lifecycle.

Create the file **src/main/java/com/example/CracHttpApp.java**:

~~~java
package com.example;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class CracHttpApp implements Resource {

    private final int port;

    private volatile HttpServer server;
    private volatile ExecutorService requestExecutor;

    private static CracHttpApp application;

    public CracHttpApp(int port) throws Exception {
        this.port = port;

        Core.getGlobalContext().register(this);
        startListener();
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        System.out.println("CRAC beforeCheckpoint: stopping HTTP listener");
        stopListener();
        System.out.println("CRAC beforeCheckpoint: resources are ready");
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        System.out.println("CRAC afterRestore: recreating HTTP listener");
        startListener();
        System.out.println("CRAC afterRestore: HTTP listener started");
    }

    private synchronized void startListener() throws IOException {
        if (server != null) {
            return;
        }

        ExecutorService executor = Executors.newFixedThreadPool(4);
        HttpServer newServer = null;

        try {
            newServer = HttpServer.create(
                    new InetSocketAddress("0.0.0.0", port),
                    0
            );

            newServer.setExecutor(executor);
            newServer.createContext("/", this::handleRequest);
            newServer.start();

            requestExecutor = executor;
            server = newServer;

        } catch (IOException | RuntimeException e) {
            if (newServer != null) {
                newServer.stop(0);
            }

            executor.shutdownNow();
            throw e;
        }
    }

    private synchronized void stopListener() throws InterruptedException {
        HttpServer currentServer = server;
        ExecutorService currentExecutor = requestExecutor;

        server = null;
        requestExecutor = null;

        if (currentServer != null) {
            currentServer.stop(0);
        }

        if (currentExecutor != null) {
            currentExecutor.shutdown();

            if (!currentExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                currentExecutor.shutdownNow();

                if (!currentExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "HTTP request executor did not terminate"
                    );
                }
            }
        }
    }

    private void handleRequest(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();

        String body;
        if ("/health/ready".equals(path)) {
            body = "READY\n";
        } else {
            body = "Hello from a CRaC-enabled Java container\n"
                    + "path=" + path + "\n"
                    + "java.version=" + System.getProperty("java.version") + "\n"
                    + "java.vendor=" + System.getProperty("java.vendor") + "\n";
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type",
                "text/plain; charset=utf-8"
        );

        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.getInteger("server.port", 8080);
        application = new CracHttpApp(port);

        System.out.println("Application started on port " + port);
    }
}
~~~

### 4.1. Role of Callbacks

`beforeCheckpoint()` is called before the process state is saved. The application should stop accepting new work, drain in-flight operations, and close or re-prepare resources that are unsafe to keep across a checkpoint.

`afterRestore()` is called when the process is restored. The application can recreate listeners, connection pools, schedulers, or necessary clients. Only transition readiness to READY after all required resources are ready.

In the example, the listener is closed before checkpointing and reopened after restore. This avoids assuming that the old socket remains valid in the target environment's network namespace.

### 4.2. Why Keep the Resource in a Static Field?

The **application** variable holds a reference to the object that registers the callbacks in the example. The CRaC context also manages registered resources, but keeping an explicit reference makes the object's lifecycle easier to understand as the application grows.

### 4.3. Why Not Keep the Old Executor?

An executor has threads and internal state. Stopping it before checkpointing and creating a new executor after restore clarifies ownership of the thread pool. For other libraries, follow their specific documentation: some clients have CRaC integration and manage resources themselves; do not double-close resources owned by a library.

### 4.4. Limitations of the Example

`stop(0)` stops the server immediately and is not a suitable drain strategy for every production workload. In a real system, you need to stop admission, wait for in-flight requests to complete within a timeout, close connections, and handle errors if draining fails.

## 5. Building the JAR

From the project directory, run:

~~~bash
./gradlew clean test jar
~~~

If the project does not have a Gradle Wrapper yet, generate the wrapper using an installed Gradle:

~~~bash
gradle wrapper
./gradlew clean test jar
~~~

Verify the artifact:

~~~bash
ls -lh build/libs/
jar tf build/libs/crac-container-lab-1.0.0.jar
sha256sum build/libs/crac-container-lab-1.0.0.jar
~~~

The actual JAR filename depends on `rootProject.name` and `version`. If the filename differs, update the path in the Dockerfile in the next step.

Build the JAR with a suitable JDK toolchain. The runtime container must still use a JDK with CRaC support; a standard Java 21 JDK does not automatically gain CRaC capabilities just because the JAR imports `org.crac.Resource`.

## 6. Creating a Container Image with a CRaC-enabled JDK

Choose a verified Linux base image containing a CRaC JDK. Use a specific digest instead of a floating tag. Replace the placeholder in the Dockerfile with the actual image from the distribution you use.

Example **Dockerfile**:

~~~dockerfile
FROM registry.example.com/java-crac:21@sha256:<verified-image-digest>

WORKDIR /opt/app

RUN mkdir -p /checkpoint

COPY build/libs/crac-container-lab-1.0.0.jar /opt/app/app.jar

EXPOSE 8080

VOLUME ["/checkpoint"]

CMD ["java", "-XX:CRaCCheckpointTo=/checkpoint", "-jar", "/opt/app/app.jar"]
~~~

This is a sample Dockerfile. The image name, digest, checkpoint flag path, and restore method need to be confirmed with the CRaC JDK distribution. Some vendors provide dedicated images or wrappers for checkpoint/restore.

### 6.1. Why Is the Checkpoint Directory a Volume?

A checkpoint can consist of many files and be large in size. Storing it in the container's writable layer makes the artifact easy to lose when the container is deleted or replaced.

Mounting a host directory or persistent volume at `/checkpoint` helps:

- Keep the checkpoint independent of the container lifecycle.
- Enable computing checksums and storing manifests.
- Reuse the artifact in a verified restore process.
- Apply separate retention and access control.

Do not commit checkpoints to the source repository or include them in the Docker build context.

### 6.2. Building the Image

~~~bash
docker build -t crac-container-lab:1.0.0 .
~~~

After building, inspect the image:

~~~bash
docker image inspect crac-container-lab:1.0.0
docker image ls crac-container-lab
~~~

For an actual release, push the image to a registry and retrieve the digest returned by the registry. Use that digest for deployment and record it in the checkpoint manifest.

### 6.3. Checking the JDK in the Image

~~~bash
docker run --rm crac-container-lab:1.0.0 java -version
docker run --rm crac-container-lab:1.0.0 java -XX:+PrintFlagsFinal -version
~~~

The second command helps inspect the JVM flags recognized by the runtime, but it does not replace the vendor's CRaC documentation. If the JDK does not recognize the `-XX:CRaCCheckpointTo` flag, the image is not a suitable runtime or the syntax differs for the chosen distribution.

## 7. Preparing the Checkpoint Volume

On the Linux host:

~~~bash
mkdir -p "$PWD/checkpoint"
chmod 700 "$PWD/checkpoint"
~~~

The directory must be accessible by the user running the container and CRIU. If the container runs as a non-root UID, adjust ownership or mount options accordingly.

Do not reuse a checkpoint directory that contains old artifacts without checking its contents. Each checkpoint creation should use a separate directory or clear old artifacts following a controlled procedure.

Example structure after checkpointing:

~~~text
crac-container-lab/
├── build/
├── checkpoint/
│   ├── checkpoint.img
│   ├── pages-1.img
│   ├── core-*.img
│   └── metadata...
├── Dockerfile
└── src/
~~~

The filenames and number of files depend on the CRaC/CRIU version. Do not assume every version produces these exact illustrative names.

## 8. Running the Container with Checkpoint/Restore Permissions

CRIU needs to interact with the kernel and processes. Required permissions depend on the kernel, CRIU, container runtime, user namespaces, and security profile.

An illustrative command on Linux Docker Engine:

~~~bash
docker run -d \
  --name crac-demo \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  --cap-add=CHECKPOINT_RESTORE \
  --cap-add=SYS_PTRACE \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  crac-container-lab:1.0.0
~~~

The capabilities and security options above are examples for testing in a Linux lab environment. Do not apply them as-is to production. Use the minimal configuration supported by your JDK/CRIU and container runtime. Some older kernels do not have `CAP_CHECKPOINT_RESTORE`; some configurations require different permissions or policies.

If the container fails to start or `criu check` fails, check:

- Kernel release and CRIU version.
- Container capabilities.
- Seccomp profile.
- AppArmor/SELinux policy.
- User namespace and UID mapping.
- Access permissions to `/proc`, mounts, and the checkpoint directory.
- How the Docker daemon is configured.

Do not simply grant unlimited privileges to mask an unsuitable host configuration. Identify which system operation is being blocked and apply an appropriate policy for the lab or production.

### 8.1. Checking the Container and Application

~~~bash
docker ps --filter name=crac-demo
docker logs crac-demo
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health/ready
~~~

The expected result is HTTP 200 and a body containing application information. If the container exits immediately, check the logs before continuing.

### 8.2. Identifying the Java PID

~~~bash
docker exec crac-demo jcmd -l
~~~

With the CMD in the Dockerfile, Java is usually PID 1 inside the container because Docker runs the command directly. However, obtain the PID from `jcmd -l` rather than always assuming it is 1.

## 9. Creating a Checkpoint with JDK CRaC

Before checkpointing:

1. Send a test request and confirm the application is serving.
2. Confirm the checkpoint directory is mounted and writable.
3. Verify there are no in-flight requests or unfinished jobs.
4. Record the image digest, JDK build, and runtime profile.
5. Ensure CRIU and the host meet the requirements.

With a CRaC JDK supporting the `JDK.checkpoint` command, you can trigger a checkpoint using `jcmd`:

~~~bash
docker exec crac-demo jcmd 1 JDK.checkpoint
~~~

Replace PID `1` with the actual Java PID obtained from `jcmd -l`. Some distributions have wrappers or different control syntax; follow the exact instructions of the running JDK.

When the command executes, CRaC invokes the registered Resource callbacks before saving the process state. In the example, `beforeCheckpoint()` stops the HTTP listener and executor. Then, the runtime's checkpoint mechanism writes the necessary files to `/checkpoint`.

### 9.1. Checking the Result

~~~bash
find checkpoint -maxdepth 2 -type f -printf '%p %s bytes\n'
du -sh checkpoint
~~~

If the checkpoint directory remains empty, check the `jcmd` output, JVM logs, and CRIU logs. Do not proceed to restore with an empty directory or a partial set of checkpoint files.

### 9.2. Original Process After Checkpoint

The behavior of the original process after creating a checkpoint depends on the CRaC JDK distribution and how the checkpoint tool is integrated. Some runtimes let the process continue running after the image is created; other workflows manage the process differently.

Read the output and check the status:

~~~bash
docker ps --filter name=crac-demo
docker logs crac-demo
~~~

If the original process is still running, do not let it and the restored process bind to the same port/network endpoint. Stop or isolate the original instance according to the runtime's instructions before restoring.

## 10. Restoring the Application from Checkpoint

Restoring requires the right JDK/CRaC runtime, complete checkpoint files, and a compatible Linux environment. Simply running `docker start` does not automatically restore the application from a JDK CRaC checkpoint. A normal `docker start` just restarts the container using the image's command.

For CRaC JDKs using the `-XX:CRaCRestoreFrom` flag, the common command form is:

~~~bash
java -XX:CRaCRestoreFrom=/checkpoint
~~~

The checkpoint already contains the process state and launch information of the saved process; therefore, the restore command typically only specifies the checkpoint path and does not re-run the main class like a cold start. The exact command must follow your distribution's documentation. Some runtimes require a wrapper or container restore integration to set up namespaces, mounts, process tree, and CRIU options. Do not bypass that requirement by simply copying the checkpoint directory into an arbitrary container.

### 10.1. Restoring with the Same Image and Volume

In principle, restore must use:

- The same application image digest that created the checkpoint.
- The same JDK/CRaC build.
- The same native libraries and runtime files.
- The same architecture and compatible CPU baseline.
- Required mount paths.
- Verified kernel/CRIU and security configuration.
- Suitable network and namespace configuration.

If the JDK provides direct command-line restore, you can use a command similar to the following in a runtime-supported environment:

~~~bash
docker run --rm \
  --name crac-demo-restored \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  --cap-add=CHECKPOINT_RESTORE \
  --cap-add=SYS_PTRACE \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  crac-container-lab:1.0.0 \
  java -XX:CRaCRestoreFrom=/checkpoint
~~~

This is an illustrative command shape, not a guarantee that every Docker Engine or JDK can restore a checkpoint from a new container with new namespaces. CRIU needs to restore the process into a compatible environment; the runtime may need to preserve or recreate PID, mount, and network namespaces following a specific procedure.

If your distribution provides a CRaC-aware container runtime, wrapper script, or Kubernetes integration, use that mechanism instead of this illustrative command.

### 10.2. Do Not Confuse with Docker Container Checkpoint

Docker may provide commands such as:

~~~bash
docker checkpoint create <container> <checkpoint-name>
docker start --checkpoint <checkpoint-name> <container>
~~~

This is checkpoint/restore at the container runtime level, not an equivalent JDK CRaC operation. This mechanism does not replace Java Resource `beforeCheckpoint()`/`afterRestore()` callbacks under the same contract. If the application needs to prepare connections, caches, or listeners, you still need to design a proper CRaC lifecycle.

### 10.3. Handling Ports and Network Namespaces

The application in this lab closes the HTTP listener before checkpointing and re-binds after restore. However, the container runtime can still create a different network namespace or port mapping when creating a new container.

If restoring in a different namespace, you must verify how the runtime restores sockets and how host ports are mapped. Do not assume a checkpoint containing an old socket will automatically work in a new network namespace.

## 11. Verifying After Restore

After the runtime reports a successful restore, check the logs:

~~~bash
docker logs crac-demo-restored
~~~

Expect to see the messages:

~~~text
CRAC afterRestore: recreating HTTP listener
CRAC afterRestore: HTTP listener started
~~~

Then send requests:

~~~bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health/ready
~~~

Expect HTTP 200 and body `READY` at the readiness endpoint. If restore succeeds but the listener does not reopen, check the `afterRestore` callback, port binding, and exception logs.

### 11.1. Checking Process and Runtime Identity

~~~bash
docker exec crac-demo-restored jcmd -l
docker exec crac-demo-restored java -version
~~~

The container name and how `jcmd` is invoked may vary depending on how the runtime restores. What matters is confirming that the process is running the intended image/JDK and the application serves requests after the callbacks.

### 11.2. Confirming Callbacks Are Called in Order

The logs should show:

- At checkpoint time, `beforeCheckpoint()` stopped the listener.
- After restore, `afterRestore()` created a new listener.
- Readiness only succeeds after required resources are ready.
- No port binding or thread pool errors.
- Requests after restore return successful responses.

Do not rely on the container being in the Running state to conclude that the application is Ready.

## 12. Packaging the Checkpoint as a Separate Artifact

After creating the checkpoint, record information to know which release the image belongs to and in which environment it can be restored.

A minimal manifest:

~~~yaml
schemaVersion: 1

application:
  name: crac-container-lab
  version: 1.0.0
  sourceCommit: "<git-commit-sha>"
  jarSha256: "<jar-sha256>"

container:
  image: "registry.example.com/crac-container-lab@sha256:<image-digest>"
  architecture: "amd64"

runtime:
  jdkVendor: "<vendor>"
  javaVersion: "<full-java-version>"
  jdkBuild: "<exact-build>"
  cracSupport: "<crac-build>"
  jvmFlags:
    - "-XX:CRaCCheckpointTo=/checkpoint"

platform:
  os: Linux
  kernel: "<kernel-release>"
  criu: "<criu-version>"
  containerRuntime: "<runtime-version>"
  cpuBaseline: "<validated-cpu-baseline>"

checkpoint:
  id: "crac-container-lab-1.0.0-linux-x86-001"
  path: "checkpoint/"
  totalBytes: 0
  files:
    - path: "checkpoint.img"
      sha256: "<sha256>"
    - path: "pages-1.img"
      sha256: "<sha256>"

validation:
  restoreTest: "<test-run-id>"
  status: "<passed-or-failed>"
  testedNodePool: "<node-pool-profile>"
~~~

The values are placeholders. Generate the manifest after the checkpoint completes and compute actual digests for all files. Do not leave `totalBytes: 0` or placeholders in a release manifest.

### 12.1. Computing Checksums for the Checkpoint

Example:

~~~bash
find checkpoint -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum > checkpoint.SHA256SUMS
~~~

If storing the checksum file inside the checkpoint directory itself, avoid including the checksum file in its own checksum list. You can store `SHA256SUMS` outside the directory or generate the list before adding the checksum file.

When restoring:

~~~bash
sha256sum -c checkpoint.SHA256SUMS
~~~

Use the signed file list or one stored in a trusted catalog. A checksum is only meaningful if the expected values are protected; if an attacker replaces both the checkpoint and the checksum, the comparison does not prove artifact provenance.

### 12.2. Signing the Manifest and Protecting Artifacts

In production, sign the manifest or create an attestation linking the checkpoint digest with the image digest, source commit, and JDK build. Restrict read permissions on the checkpoint because the memory image may contain tokens, credentials, sessions, or sensitive data in the heap.

Do not store plaintext secrets in the manifest. Only record secret references or version IDs.

## 13. Dockerfile and Dual-Mode Restore Workflow

An image can provide two startup modes: creating a checkpoint and restoring a checkpoint. An entrypoint script can be used to select the mode, but the corresponding JDK flags must be verified.

Example **entrypoint.sh**:

~~~sh
#!/bin/sh
set -eu

MODE=$(printenv START_MODE 2>/dev/null || true)
if [ -z "$MODE" ]; then
  MODE=normal
fi

case "$MODE" in
  normal)
    exec java \
      -XX:CRaCCheckpointTo=/checkpoint \
      -jar /opt/app/app.jar
    ;;
  restore)
    exec java \
      -XX:CRaCRestoreFrom=/checkpoint
    ;;
  *)
    echo "Unsupported START_MODE: $MODE" >&2
    exit 2
    ;;
esac
~~~

If using the script, update the Dockerfile:

~~~dockerfile
FROM registry.example.com/java-crac:21@sha256:<verified-image-digest>

WORKDIR /opt/app

RUN mkdir -p /checkpoint

COPY build/libs/crac-container-lab-1.0.0.jar /opt/app/app.jar
COPY entrypoint.sh /opt/app/entrypoint.sh

RUN chmod 755 /opt/app/entrypoint.sh

EXPOSE 8080
VOLUME ["/checkpoint"]

ENTRYPOINT ["/opt/app/entrypoint.sh"]
~~~

Normal startup:

~~~bash
docker run -d \
  --name crac-demo \
  -e START_MODE=normal \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  crac-container-lab:1.0.0
~~~

Startup in restore mode in a supported runtime:

~~~bash
docker run --rm \
  --name crac-demo-restored \
  -e START_MODE=restore \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  crac-container-lab:1.0.0
~~~

This script only selects JVM options. It does not grant capabilities, set up namespaces, invoke CRIU, or configure the container runtime. Those parts still must be supported by the restore environment.

## 14. Using Checkpoints in Kubernetes

In Kubernetes, the application image and checkpoint artifact are usually distributed separately. The image contains the CRaC JDK and application; the checkpoint is loaded into a volume or provided by a restore-aware runtime.

A Pod should only be marked Ready after:

- The checkpoint is verified and restored successfully.
- The `afterRestore()` callback completes.
- Essential connections and resources are recreated.
- The listener or request handler is ready.
- The readiness state is updated.

Illustrative configuration showing a checkpoint volume and readiness probe:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crac-container-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: crac-container-lab
  template:
    metadata:
      labels:
        app: crac-container-lab
    spec:
      containers:
        - name: app
          image: registry.example.com/crac-container-lab@sha256:<image-digest>
          ports:
            - name: http
              containerPort: 8080
          volumeMounts:
            - name: checkpoint
              mountPath: /checkpoint
              readOnly: true
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
      volumes:
        - name: checkpoint
          persistentVolumeClaim:
            claimName: crac-checkpoint-pvc
~~~

This is an example of mounting a checkpoint and declaring readiness. It is not a complete CRaC Kubernetes configuration: Kubernetes does not automatically know how to invoke JDK restore or CRIU just from a volume mount. A dedicated runtime, operator, init process, or integration is needed to perform the restore as required by the distribution.

### 14.1. Readiness and Liveness

Readiness reflects the ability to receive traffic. If restore or dependency initialization is not yet complete, the `/health/ready` endpoint should return a not-ready state.

Liveness should focus on the internal health of the process. Do not restart a Pod just because the database or Redis is temporarily slow; restarting can create an additional restore/reconnect storm.

### 14.2. Checkpoint Volume and Access Control

The checkpoint volume needs:

- The exact checkpoint ID for the release.
- Read-only access for the process after the artifact has been created and verified, if the runtime does not need to write.
- Sufficient capacity and read speed.
- Appropriate ownership/permissions.
- Access control restricting which workloads are allowed to read.
- Retention protecting checkpoints still referenced by Pods or rollbacks.

A PVC can be mounted into multiple Pods, but that does not mean every Pod can restore the same checkpoint in every configuration. You need to verify how CRIU and the runtime handle namespaces, PIDs, and file locks when restoring multiple replicas.

## 15. Conditions That Must Remain Compatible

When creating and restoring checkpoints in Linux containers, record and cross-check at least the following groups:

| Group | Must Record |
|---|---|
| Application | Release ID, source commit, JAR digest |
| Image | OCI image digest, base image digest |
| JDK | Vendor, full version, build, CRaC support |
| JVM | JVM flags, GC/compiler configuration |
| Native runtime | libc, dynamic linker, JNI/native libraries |
| CPU | Architecture and CPU feature baseline |
| Kernel | Kernel release/build and required features |
| CRIU | Version and capability check |
| Container runtime | Docker/containerd/CRI-O version and restore integration |
| Namespace | PID, mount, network, user namespace |
| Security | Capabilities, seccomp, AppArmor/SELinux |
| Filesystem | Checkpoint path, mount, ownership, storage behavior |

The same container image does not guarantee restore on every host because the container still uses the host's kernel. The same kernel version is also insufficient if capabilities, namespaces, CPU features, or security policies differ.

## 16. Common Troubleshooting

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| JVM does not recognize `-XX:CRaCCheckpointTo` | JDK lacks CRaC or flag differs by distribution | Check `java -version` and JDK documentation |
| `JDK.checkpoint` not found | Runtime does not support the command or jcmd is from the wrong JDK | Check `jcmd -l`, JDK build, and command reference |
| `criu check` fails | Insufficient kernel features or permissions | Check CRIU logs, capabilities, and security policy |
| Permission denied when writing checkpoint | Incorrect volume ownership/mode | Check UID/GID and mount |
| Checkpoint directory is empty | Checkpoint has not finished or output path is wrong | Inspect jcmd/JVM/CRIU logs |
| Restore reports missing files | Incomplete artifact copy | Cross-check manifest and checksums |
| Restore fails on another node | Different kernel, CPU, CRIU, or namespaces | Compare platform manifests |
| Port 8080 already in use | Old listener or another process is still running | Check processes, sockets, and port mapping |
| Restore succeeds but HTTP does not respond | `afterRestore()` failed or listener did not bind | Check callback logs and readiness |
| Container exits after restore | Incorrect runtime/entrypoint procedure | Inspect exit code, JVM logs, and restore wrapper |
| Native library load error | Different ABI or dependencies | Check image digest, `ldd`, `readelf` |
| Abnormally slow restore | Large checkpoint or slow storage I/O | Measure image size and read time |

### 16.1. Collecting Information on Failure

~~~bash
java -version
jcmd -l
criu --version
sudo criu check
docker version
docker info
docker logs crac-demo
~~~

Collect additional kernel logs or CRIU logs as provided by the runtime. Do not only record a single line of Java exception because the root error may lie in the kernel or container runtime.

### 16.2. Do Not Delete the Checkpoint Immediately After a Failed Restore

Keep the artifacts and logs for investigation. If you need to retry, copy the checkpoint to a separate test directory and preserve the original. Do not overwrite artifacts that have been signed or are referenced by a release catalog.

## 17. End-to-End Practice Workflow

Follow this sequence on a compatible Linux host.

### Phase A: Build

1. Create the Gradle project.
2. Add a compatible CRaC API dependency.
3. Write `CracHttpApp` and register the Resource.
4. Run `./gradlew clean test jar`.
5. Compute the SHA-256 of the JAR.
6. Select a CRaC-enabled JDK image by digest.

### Phase B: Package

1. Write a Dockerfile using the right JDK image.
2. Copy the JAR into the image.
3. Declare the checkpoint directory.
4. Build the container image.
5. Save the image digest and runtime identity.

### Phase C: Prepare Host

1. Check the kernel and CPU architecture.
2. Install CRIU.
3. Run `criu check`.
4. Determine required capabilities and security profile.
5. Prepare the checkpoint volume.
6. Verify read/write permissions.

### Phase D: Run and Checkpoint

1. Start the container.
2. Send requests to `/` and `/health/ready`.
3. Get the Java PID using `jcmd -l`.
4. Trigger `JDK.checkpoint` per the JDK documentation.
5. Observe `beforeCheckpoint()` in the logs.
6. Confirm checkpoint files are completely written.
7. Compute checksums and generate the manifest.

### Phase E: Restore and Verify

1. Stop or isolate the original process per runtime procedure.
2. Select the exact image digest and JDK build.
3. Mount the checkpoint directory.
4. Invoke restore using the JDK or a supported wrapper.
5. Observe `afterRestore()` in the logs.
6. Send a request to `/health/ready`.
7. Confirm HTTP 200.
8. Record the restore attempt, node profile, and readiness time.

### Phase F: Package Release

1. Store the JAR/image digest and checkpoint manifest.
2. Sign the manifest or attestation.
3. Store the checkpoint in storage with access control.
4. Link the checkpoint ID to the release ID.
5. Only promote after restore validation succeeds.

## 18. Pre-Production Checklist

### Build and Image

- [ ] JDK image has CRaC support and is pinned by digest.
- [ ] JAR is built with a recorded toolchain.
- [ ] CRaC API dependency is compatible with the runtime.
- [ ] Native dependencies have been inventoried.
- [ ] Image does not unintentionally contain old checkpoints.

### Linux Host and Container Runtime

- [ ] Kernel/architecture has been verified.
- [ ] CRIU version and capability check have been recorded.
- [ ] Container runtime supports the chosen restore workflow.
- [ ] Capabilities and security profile are at the minimum required level.
- [ ] PID/mount/network namespaces are appropriate.
- [ ] Checkpoint storage has sufficient capacity and access permissions.

### Application Lifecycle

- [ ] Resources have registered CRaC callbacks.
- [ ] `beforeCheckpoint()` stops admission and drains work.
- [ ] Connections and listeners are properly closed or prepared.
- [ ] `afterRestore()` recreates required resources.
- [ ] Callbacks have timeouts and error handling.
- [ ] Readiness only opens when essential dependencies are ready.
- [ ] Scheduled tasks, locks, and consumer states are checked after restore.

### Artifact and Restore

- [ ] Checkpoint has a unique ID.
- [ ] Manifest records source, image, JDK, platform, and warm-up profile.
- [ ] All checkpoint files have checksums.
- [ ] Manifest/attestation is signed.
- [ ] Checkpoint is stored immutably with access control.
- [ ] Test restore has been run on the exact target node pool.
- [ ] A tested rollback or cold-start fallback exists.

## 19. Frequently Asked Questions

### Can any JDK 21 image be used?

No. The JDK must have CRaC support compatible with the application and checkpoint. The same Java major version does not guarantee the same CRaC patches, native runtime, or build. Pin the distribution/build and image digest.

### Is just adding the `org.crac` library to the JAR enough?

No. The dependency provides the API for the application to register resources and handle callbacks. Checkpoint/restore capability also requires a CRaC-supporting JDK, CRIU, and a suitable Linux environment.

### Can a checkpoint be created on Windows or macOS and then restored in a Linux container?

You should not assume so. A checkpoint is tied to the process, kernel, and native runtime. This exercise creates and restores on a compatible Linux environment. If using a Windows/macOS host, run inside a Linux VM or an environment supported by JDK/CRIU.

### Can a checkpoint be copied into a new image and then restored?

Only if the new image preserves a compatible runtime and native dependencies, and kernel, CPU, and namespace conditions are met. Changing the JDK, libc, or native libraries can invalidate the checkpoint. Use manifests and restore validation to confirm.

### Is Docker `checkpoint create` the same as `jcmd JDK.checkpoint`?

No. Docker checkpoint is a container runtime-level operation. `JDK.checkpoint` is a JDK CRaC operation and coordinates with Resource callbacks in the application. Choose the mechanism based on your architecture and integration in use.

### Can `docker start` be used to restore a JDK CRaC checkpoint?

Not by default. `docker start` restarts the container using its normal command. CRaC restore requires the JDK restore option or a corresponding wrapper/integration. Docker has its own container restore command, but that is a different mechanism.

### Why must the HTTP listener be closed before checkpointing?

Sockets and network namespaces may no longer be valid in the restore environment. This example closes the listener and reopens it in `afterRestore()`. Production needs to drain requests before closing and check port mapping at runtime.

### Can the checkpoint be stored in a separate volume?

Yes, and that is usually a convenient organization. A volume allows the checkpoint to exist independently of the container's writable layer. Ensure mount paths, permissions, storage behavior, and access control are appropriate.

### Can the same checkpoint be restored across multiple containers at the same time?

You should not assume so. Restoring multiple replicas depends on CRIU, namespaces, PIDs, networking, storage, and how the runtime supports it. Beyond technical compatibility, you must check duplicated heap state such as schedulers, locks, consumers, and running jobs.

### What should be checked when restore succeeds but readiness fails?

Check `afterRestore()` logs, resource initialization, connection pools, listener binding, secrets, DNS, and dependency health. A Running container only indicates the process exists; it does not prove the application can serve requests.

### Does the checkpoint need to be included in the container image?

Usually, it is better to manage the image and checkpoint as separate artifacts. The image contains the application and runtime; the checkpoint is stored in an appropriate registry or storage and linked to the image digest via a manifest. This makes managing retention, validation, and rollback clearer.

## Conclusion

Packaging and restoring Java applications in Linux containers with CRaC requires coordinating three layers: application lifecycle, JDK CRaC runtime, and the Linux/container environment. The application must register Resources to properly stop or re-establish resources; the image must contain the right JDK and native dependencies; and the host must meet kernel, CRIU, namespace, and security policy requirements.

In this exercise, the HTTP server is closed before checkpointing and recreated in `afterRestore()`. The JAR is packaged in the image, while the checkpoint is stored on a separate volume and linked to a manifest containing the image digest, JDK build, platform profile, and checksums. After restore, check callbacks, readiness, and HTTP requests to confirm the application is working.

In real deployments, use the proper restore integration of the JDK/container runtime, keep the environment compatible, verify artifacts before restoring, and only open traffic once essential resources are ready.
