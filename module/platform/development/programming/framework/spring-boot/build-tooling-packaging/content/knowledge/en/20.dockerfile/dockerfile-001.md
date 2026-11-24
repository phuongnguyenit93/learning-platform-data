# Packaging a Verified JAR into an OCI Image with a Dockerfile

## 1. The Problem to Solve

A Spring Boot application can be built into an executable JAR and run fine with `java -jar` on a developer's machine, yet fail at startup inside Docker/Kubernetes. The root cause is often not in the Java source code: the image might use a different JRE, the Dockerfile might copy the wrong plain JAR, the port and bind address might be wrong, file permissions might be insufficient, environment variables might be missing, or the image might be built from a different artifact than the file that passed QA.

This lesson belongs to the **Dockerfile** section of the **Spring Boot Build Tooling Packaging** topic, with a specific goal: **package the exact verified executable JAR into an OCI-compatible image**, then prove that the image contains the exact bytes of that JAR and that the application actually works inside the container.

You will learn how to:

1. Distinguish between an **executable JAR**, **OCI image**, **image tag**, **image digest**, and **running container**.
2. Create a Spring Boot Java 17 web application and a Maven executable JAR with an explicit artifact name.
3. Create a real JAR testing gate before the Docker build, without substituting `spring-boot:run`.
4. Write a Dockerfile that **copies only the tested JAR**, using JRE 17 and a non-root user.
5. Restrict the Docker build context with `.dockerignore` to avoid accidentally sending secrets, source code, or extra JARs.
6. Compare the JAR bytes on the host against the JAR extracted from the image itself using `docker create`, `docker cp`, and `cmp`/SHA-256.
7. Run the image, publish the port in a controlled way, probe HTTP, and clean up the container whether the test passes or fails.
8. Handle image tags, registry digests, architectures, base image updates, and common CI failures.
9. Understand when a layered image or multi-stage build is needed while preserving traceability to the exact artifact.

**Example stack:** Java `17`, Spring Boot `3.5.16`, compatible Maven, Docker Linux containers, and `eclipse-temurin:17-jre-jammy`. These are illustrative versions; base image tags can change with patches, so production should pin a verified digest and have an update process.

## 2. Distinguishing a JAR from an OCI Image

| Object | Example | Contents | Identity |
| --- | --- | --- | --- |
| Executable JAR | `target/oci-demo-1.0.0.jar` | Boot loader, classes/resources, nested dependencies | SHA-256 hash of the **JAR file** |
| OCI/Docker image | `oci-demo:1.0.0` | JRE, OS filesystem layers, copied JAR, image config, and manifest | Local image ID or registry manifest/index digest |
| Running container | `oci-demo-smoke` | Java process and writable layer based on the image | Container ID, status, and logs |

According to the OCI Image Specification, an image typically consists of a manifest, configuration, and filesystem layers. The JAR file is only **one part** of the image filesystem. Therefore, **the JAR SHA-256 is not the image digest**, and two different image digests do not by themselves prove that the JAR bytes inside differ.

An image tag like `oci-demo:1.0.0` is a **reassignable name**, not immutable evidence. Only a registry digest uniquely identifies the pushed manifest/index content. For multi-platform images, the image index digest and each individual platform manifest digest can also differ.

**Dual goal of this lesson:**

~~~text
Git revision + source + pom.xml
          |
          v
      mvn clean verify
          |
          v
  executable JAR on host
          |
          +-- GATE 1: java -jar, HTTP probe, SHA-256
          |
          v
  Dockerfile COPY exact JAR file
          |
          v
  OCI-compatible container image
          |
          +-- GATE 2A: JAR bytes in image == tested JAR
          |
          +-- GATE 2B: JRE in image + HTTP smoke
          |
          v
  Record image identity/digest and publish exact image
~~~

The `docker build` step in this example **does not run Maven again**. If CI verifies file A and then the Dockerfile or multi-stage build produces a separate file B, you must not claim the image contains artifact A without verifying that B's bytes match A.

## 3. Standalone Java 17/Spring Boot Project

### 3.1. Project structure

~~~text
oci-demo/
  pom.xml
  Dockerfile
  .dockerignore
  SmokeJar.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`SmokeJar.java` is a **standalone test runner at the project root**. Because it is not inside `src/main/java`, Maven does not package it into the application JAR. This tests the **released archive**, rather than silently running on the build tool's source/test classpath.

### 3.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>oci-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot starter parent provides dependency management and plugin configuration; when `spring-boot-maven-plugin` is declared, the `repackage` goal participates in the package lifecycle via the parent. With `artifactId=oci-demo`, `version=1.0.0`, no classifier, and no custom `finalName`, the result is `target/oci-demo-1.0.0.jar`.

Do not equate `mvn package` with a guaranteed runnable JAR: if another project does not inherit the Boot parent or `repackage` execution is disabled, Maven may produce only a plain JAR. You must inspect the **actual file**.

### 3.3. Complete Application.java

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @GetMapping(value = "/probe",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return "oci-jar-ok";
    }
}
~~~

On a successful GET request to `/probe`, the HTTP status is **200** and the body is exactly:

~~~text
oci-jar-ok
~~~

`/probe` is a small check for web server startup and Spring MVC routing; it does not by itself prove that a larger project's database, SSO, or broker is ready. In this example, `server.address=127.0.0.1` is not hardcoded in application configuration, because the server inside the container needs to bind to an interface that can receive traffic from Docker port forwarding.

### 3.4. Build and inspect the archive

At the project root:

~~~bash
mvn -B -ntp clean verify
jar tf target/oci-demo-1.0.0.jar
~~~

`verify` includes compile, tests, package, and `repackage` in an example using the Boot parent. Typical entries in an executable Spring Boot JAR:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

This is an **abbreviated illustrative list**, not verbatim output from `jar tf`. `BOOT-INF/classes` holds application code/resources and `BOOT-INF/lib` holds runtime dependencies.

If using the Maven Wrapper provided by the project, replace `mvn` with `./mvnw` (Linux/macOS) or `.\mvnw.cmd` (Windows PowerShell). Do not invoke the Wrapper if it is not present in the repository.

## 4. GATE 1: Testing the Exact Executable JAR Before Building the Image

### 4.1. Why java -jar is needed

`mvn spring-boot:run` and IDEs run against a development classpath and do not validate the manifest or nested libraries of the released archive. A reliable gate must invoke **the exact output JAR file path**, wait for the endpoint with a timeout, and return a nonzero exit code on failure.

You can run it manually:

~~~bash
java -jar target/oci-demo-1.0.0.jar \
  --server.address=127.0.0.1 \
  --server.port=18080
~~~

Then from another terminal:

~~~bash
curl -fsS http://127.0.0.1:18080/probe
~~~

The expected body is `oci-jar-ok`. When finished, stop the Java server with `Ctrl+C`. However, to ensure CI does not hang or forget cleanup, we use a Java 17 runner.

### 4.2. SmokeJar.java (Java 17 Standard Library)

Create `SmokeJar.java` at the project root:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class SmokeJar {

    private static String javaExecutable() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        return Path.of(System.getProperty("java.home"),
                "bin", os.startsWith("windows")
                        ? "java.exe" : "java").toString();
    }

    private static int choosePort() throws IOException {
        try (ServerSocket socket = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"))) {
            return socket.getLocalPort();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java SmokeJar.java <jar-file>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException(
                    "JAR not found: " + jar);
        }

        int port = choosePort();
        Path log = Files.createTempFile("oci-jar-smoke-", ".log");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable(),
                "-jar", jar.toString(),
                "--server.address=127.0.0.1",
                "--server.port=" + port,
                "--spring.main.banner-mode=off");
        builder.redirectErrorStream(true);
        builder.redirectOutput(log.toFile());

        Process child = builder.start();
        boolean passed = false;

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + port + "/probe"))
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(45);

            while (System.nanoTime() < deadline) {
                if (!child.isAlive()) {
                    throw new IllegalStateException(
                            "JAR exited early; exit="
                                    + child.exitValue()
                                    + "; log=" + log);
                }

                try {
                    HttpResponse<String> response =
                            client.send(request,
                                    HttpResponse.BodyHandlers.ofString(
                                            StandardCharsets.UTF_8));
                    if (response.statusCode() == 200) {
                        if (!"oci-jar-ok".equals(response.body())) {
                            throw new AssertionError(
                                    "Unexpected body: "
                                            + response.body());
                        }
                        passed = true;
                        System.out.println("jar.smoke=PASS");
                        System.out.println(
                                "jar.probe=oci-jar-ok");
                        return;
                    }
                } catch (IOException serverNotReady) {
                    // Retry while Spring Boot starts.
                }
                Thread.sleep(250);
            }

            throw new IllegalStateException(
                    "Timeout waiting for /probe; log=" + log);
        } finally {
            if (child.isAlive()) {
                child.destroy();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                    child.waitFor(5, TimeUnit.SECONDS);
                }
            }

            if (passed) {
                try {
                    Files.deleteIfExists(log);
                } catch (IOException ignored) {
                    // Does not change the HTTP result.
                }
            } else {
                System.err.println("jar.smoke.log=" + log);
            }
        }
    }
}
~~~

`ProcessBuilder` launches **a separate JVM process** with `-jar`, without importing application classes into the runner. `HttpClient` performs a real HTTP 200/body check; a 45-second deadline and 2-second per-request timeout prevent hanging. The `finally` block stops the process on both PASS and FAIL, avoiding holding the port for other jobs.

Allocating a temporary port with `ServerSocket(0)` has a small race window between closing the socket and Spring Boot binding, so on busy CI runners with many jobs you can improve it with bound-port discovery or instance identity. This is an illustrative version suited for practicing Java 17.

### 4.3. Running Gate 1

~~~bash
java SmokeJar.java target/oci-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
java SmokeJar.java .\target\oci-demo-1.0.0.jar
~~~

On PASS, the stdout **printed by the runner** is exactly:

~~~text
jar.smoke=PASS
jar.probe=oci-jar-ok
~~~

If the JAR is missing, the process crashes, the route is wrong, a timeout occurs, or the body mismatches, the runner throws an exception, returns a non-zero exit code, and preserves the startup log. Do not run the Docker build if this gate fails.

Record the SHA-256 **of the JAR that passed**:

~~~bash
sha256sum target/oci-demo-1.0.0.jar
~~~

PowerShell:

~~~powershell
Get-FileHash .\target\oci-demo-1.0.0.jar -Algorithm SHA256
~~~

Do not write a fake SHA in documentation. After this gate, **do not silently rebuild the JAR** before the image build; if you rebuild, you must verify the exact new file.

## 5. Complete Dockerfile: JRE 17, exact COPY, non-root, exec ENTRYPOINT

Create `Dockerfile` at the project root:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

COPY --chown=10001:10001 target/oci-demo-1.0.0.jar /app/application.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

This Dockerfile has no Maven, `RUN mvn`, compiler, or Git. It places **an existing artifact** into a runtime image containing JRE 17.

| Instruction | Role | Key Point |
| --- | --- | --- |
| `FROM eclipse-temurin:17-jre-jammy` | Selects a Linux base image with a Java 17 runtime | Tags are mutable; releases must pin a verified digest |
| `WORKDIR /app` | Sets the working directory of the process | Does not automatically grant the user write permissions to everything here |
| `COPY --chown=10001:10001` | Copies **one built JAR** into the image; changes owner numerically | Does not invoke Maven or extract the JAR |
| `USER 10001:10001` | Runs Java as non-root | Directories/volumes need sufficient permissions for the user |
| `EXPOSE 8080` | Documents the TCP port inside the container | **Does not** publish a host port |
| JSON-form `ENTRYPOINT` | Runs the JVM directly in exec form | Good for signal forwarding, lifecycle, and application args |

`COPY --chown` uses numeric UID/GID so creating a named account in the Linux image is not required. Some applications require a user home directory or account lookup, in which case you should create an explicit user/group and test it; the minimal HTTP service here only needs to read the JAR and serve requests.

`USER 10001:10001` does not automatically make `/app` writable: if the application must write uploads or cache, configure a separate writable directory/mount. This Dockerfile also contains no secrets; credentials for databases, brokers, and TLS should be provided at runtime according to deployment policy.

**Why exact COPY?** Using `COPY target/*.jar /app/app.jar` easily picks the wrong file when `target` contains plain, executable, and classifier JARs. The known right file for this example is `target/oci-demo-1.0.0.jar`; if you change the Maven version, classifier, or `finalName`, update both the Dockerfile **and** the gate with the same artifact identity.

### 5.1. Default preconditions

- The build context must be the **project root** containing `target/oci-demo-1.0.0.jar`.
- Docker runs in Linux containers mode; numeric `USER` and Linux base images do not apply directly to Windows container mode.
- The Spring Boot app must bind to an interface receiving container traffic, not only `127.0.0.1` inside the container.
- The runtime port in the example is 8080. If you change the service's `server.port`, you must adjust `EXPOSE`, `docker run -p`, and the probe.
- A JAR compiled for Java 17 requires a sufficiently new JRE; if a dependency was compiled for Java 21, JRE 17 can still fail.
- Apps with JNI/native libraries must match the base image's CPU architecture, libc, and system libraries.

## 6. Build Context and .dockerignore

The command:

~~~bash
docker build -t oci-demo:1.0.0 .
~~~

uses `.` as the build context. A Dockerfile can only `COPY` files present in the context that **are not excluded by `.dockerignore`**. A file existing on the host that is ignored will still cause `COPY` to report file not found.

Because this Dockerfile only needs a single executable JAR, create `.dockerignore` at the root:

~~~dockerignore
**
!target/
!target/oci-demo-1.0.0.jar
~~~

Meaning: exclude most files from the build context, then allow the `target` directory and the exact JAR file to be sent to the builder. The Dockerfile and `.dockerignore` are still read by the builder under special rules even if matched by an ignore rule. When the Maven artifact is renamed or located under `service/target`, update the allowlist and `COPY` together.

This approach reduces the risk of accidentally sending source code, `.git`, test outputs, IDE files, or secrets to a remote builder. Do not use `COPY . /app` when runtime only needs the JAR, because it can put source code, internal files, credentials, or stale outputs into the final image.

**Do not place secrets in Dockerfile `ENV` or `ARG` just for "build convenience."** Those values can appear in image config, layers, history, or provenance. Provide secrets at runtime or use BuildKit secret mounts appropriately for build-time needs, and do not copy them into the final image.

## 7. Building the Image After the JAR Gate Passes

On a POSIX shell, the manual command sequence:

~~~bash
mvn -B -ntp clean verify
java SmokeJar.java target/oci-demo-1.0.0.jar
sha256sum target/oci-demo-1.0.0.jar
docker build -t oci-demo:1.0.0 .
~~~

If automated, the pipeline must **stop immediately when a command fails**; in standard POSIX shell scripts you can use `set -e` and explicitly check critical steps, while CI providers have their own fail-on-nonzero mechanisms. In PowerShell 5.1, check `LASTEXITCODE` after native commands rather than assuming nonzero always halts execution.

Inspect the local image:

~~~bash
docker image inspect --format '{{.Id}}' oci-demo:1.0.0
docker image inspect --format '{{.Config.User}}' oci-demo:1.0.0
docker image inspect --format '{{json .Config.Entrypoint}}' oci-demo:1.0.0
~~~

`Config.User` is expected to be `10001:10001` and the entrypoint is the array `java`, `-jar`, `/app/application.jar`. `.Id` is the local image identifier, **not the JAR SHA**, and does not always equal the registry manifest digest.

The Docker tag `oci-demo:1.0.0` can be reassigned to another build. If CI requires immutable deploys/releases, record the digest after push or enforce a registry tag immutability policy; do not use the `latest` tag as the sole identifier.

## 8. GATE 2A: Comparing JAR Bytes in the Image Against the Verified JAR

A successful Docker build **does not** by itself prove that the copied file is the artifact just tested. Verify directly by extracting the JAR from the image filesystem.

### 8.1. Extracting the JAR from a non-running container

`docker create` only creates a container instance without invoking the entrypoint. `docker cp` reads files even from a stopped container:

~~~bash
cid=$(docker create oci-demo:1.0.0)
docker cp "$cid:/app/application.jar" ./jar-from-image.jar
docker rm "$cid"

cmp target/oci-demo-1.0.0.jar ./jar-from-image.jar
sha256sum target/oci-demo-1.0.0.jar ./jar-from-image.jar
~~~

`cmp` returns exit code `0` when **all bytes are identical**. `sha256sum` produces two identical digests even though the paths differ. If the checksums differ, do not "fix" it by re-running Maven inside the Docker build; investigate why the image contains a different file.

### 8.2. Verification script with safe cleanup

For CI, use a POSIX script that cleans up even if `docker cp` or `cmp` fails:

~~~bash
#!/bin/sh
set -eu

jar=target/oci-demo-1.0.0.jar
image=oci-demo:1.0.0
tmp=$(mktemp -d)
cid=

cleanup() {
  if [ -n "$cid" ]; then
    docker rm -f "$cid" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT HUP INT TERM

cid=$(docker create "$image")
docker cp "$cid:/app/application.jar" "$tmp/from-image.jar"
cmp "$jar" "$tmp/from-image.jar"

printf '%s\n' 'image.jar.bytes=PASS'
~~~

On PASS, the line **printed by the script** is:

~~~text
image.jar.bytes=PASS
~~~

On mismatch, `cmp` returns nonzero and the script fails, blocking publication. `rm -rf "$tmp"` is used only on the directory freshly created by `mktemp -d` inside the script; do not change `tmp` to an arbitrary unverified path.

On Windows, you can similarly use `docker create`/`docker cp`, then compare `Get-FileHash` of `target/oci-demo-1.0.0.jar` and the extracted file, or use a Java 17 `Files.mismatch` utility. In PowerShell, when joining the container ID with a `:`, use a separate string concatenation expression so PowerShell does not misparse the variable name:

~~~powershell
$cid = docker create oci-demo:1.0.0
$source = $cid + ":/app/application.jar"
docker cp $source .\jar-from-image.jar
docker rm $cid
$one = (Get-FileHash .\target\oci-demo-1.0.0.jar -Algorithm SHA256).Hash
$two = (Get-FileHash .\jar-from-image.jar -Algorithm SHA256).Hash
if ($one -ne $two) {
    throw "Image JAR differs from verified JAR"
}
Write-Output "image.jar.bytes=PASS"
~~~

This PowerShell snippet illustrates hash comparison; CI should add `try/finally` and check `LASTEXITCODE` for `docker create/cp` so intermediate failures are not missed. The POSIX script above already includes full cleanup.

**Remember:** an image carries multiple layers and bytes besides the JAR; the right comparison is **the host JAR against `/app/application.jar` extracted from the image**, not the JAR SHA against the image ID.

## 9. GATE 2B: Starting the Container and Probing HTTP

### 9.1. Running and checking manually

~~~bash
docker run -d --name oci-demo-smoke \
  -p 127.0.0.1:18081:8080 \
  oci-demo:1.0.0
~~~

`docker run -d` creates the container and runs the Java entrypoint. The `-p` flag publishes host loopback port `18081` to port `8080` inside the container. **`EXPOSE 8080` only declares the port; it does not automatically publish a host port**.

Check status:

~~~bash
docker ps --filter name=oci-demo-smoke
docker logs oci-demo-smoke
curl -fsS http://127.0.0.1:18081/probe
~~~

Expected HTTP body:

~~~text
oci-jar-ok
~~~

The line above is the endpoint's body, not the Docker startup log. When finished:

~~~bash
docker stop oci-demo-smoke
docker rm oci-demo-smoke
~~~

In CI, use a script with a timeout and cleanup instead of running in the background and forgetting to stop the process.

### 9.2. CI smoke script with retry/timeout

POSIX shell example, from the project root after the image is built:

~~~bash
#!/bin/sh
set -eu

image=oci-demo:1.0.0
name=oci-demo-smoke-$$
port=18081

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

docker run -d --name "$name" \
  -p "127.0.0.1:$port:8080" "$image" >/dev/null

ready=0
i=0
while [ "$i" -lt 45 ]; do
  running=$(docker inspect \
    --format '{{.State.Running}}' "$name")

  if [ "$running" != "true" ]; then
    docker logs "$name" || true
    echo "Container exited before HTTP probe" >&2
    exit 1
  fi

  if body=$(curl -fsS --max-time 2 \
      "http://127.0.0.1:$port/probe" 2>/dev/null); then
    if [ "$body" = "oci-jar-ok" ]; then
      ready=1
      break
    fi
  fi

  i=$((i + 1))
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  docker logs "$name" || true
  echo "Container HTTP probe failed" >&2
  exit 1
fi

printf '%s\n' 'image.smoke=PASS'
printf '%s\n' 'image.probe=oci-jar-ok'
~~~

On PASS, the **two lines intentionally printed by the script** are:

~~~text
image.smoke=PASS
image.probe=oci-jar-ok
~~~

The script redirects the container ID from `docker run` to `/dev/null`, preserves startup logs to print on FAIL, and uses `trap` to clean up the container. Host port `18081` is an example; when running multiple concurrent jobs, each job needs its own port or isolated container network to avoid conflicts.

This step verifies **the real image's JRE and networking**, unlike the host JAR gate: the host might run Java 21 while the image uses Java 17; a dependency compiled too new will expose an `UnsupportedClassVersionError` inside the image.

### 9.3. Checking Java inside the image

~~~bash
docker run --rm --entrypoint java oci-demo:1.0.0 -version
~~~

This command runs the JRE **inside the image** to inspect the runtime version. The Java launcher may write version info to stderr; do not hardcode full vendor/patch output because it changes when the base image updates. In Kubernetes, you also need to test the actual deployment with volumes, securityContext, probes, config, and network policies.

## 10. Multiple Identifier Types: Source Commit, JAR SHA, Image Digest

A release record may contain:

~~~text
Git revision          : commit that was built
Executable JAR        : target/oci-demo-1.0.0.jar
JAR SHA-256           : checksum of file that passed Gate 1
Local image tag       : oci-demo:1.0.0
Local image ID        : docker image inspect value
Target platform       : linux/amd64 or linux/arm64
Registry image digest : manifest/index digest after push
Gate 1 result         : PASS/FAIL
Gate 2A + 2B result   : PASS/FAIL
~~~

**Do not conflate** commit SHA, JAR SHA, and image SHA. The commit SHA identifies the source revision; the JAR SHA identifies the artifact bytes; the registry digest identifies the container manifest/index. One Git commit can produce different JARs if timestamps or generated dependencies are non-deterministic. One byte-identical JAR can also be copied into two different images with different base JREs, OSes, or labels.

`docker image inspect --format '{{.Id}}'` returns a local ID that does not necessarily equal the registry digest used by Kubernetes. Tags can be overwritten; for production, prefer deploying by the **registry digest** of the verified image, or enforce a tag immutability and audit policy.

## 11. Base Image, Digest, and Platform

### 11.1. Mutable FROM tags

Example Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
~~~

This tag is a human-readable reference, but the underlying image contents can change when the JRE or Ubuntu base receives updates. If built at two different times, even with an identical JAR SHA, the image ID/digest can differ.

For strict release/reproducibility requirements, **pin the base image using a full verified digest from a trusted registry** and record the target platform. Do not insert an abbreviated or fabricated digest just to look pinned; obtain the value from the registry or a trusted dependency management system.

`docker build --pull` can check and download an updated tag, but it **does not replace digest pinning**. Digest pinning also requires a periodic update process to receive security patches.

### 11.2. CPU architecture

If deployment uses `linux/amd64`:

~~~bash
docker build --platform linux/amd64 \
  -t oci-demo:1.0.0 .
~~~

Another build might use `linux/arm64`. Pure Java bytecode JARs are relatively portable, but the base JRE and native/JNI libraries are platform-dependent. Running an AMD64 image on an ARM machine may require emulation; do not assume every Docker installation provides it.

If publishing a multi-platform image with Buildx, understand the image index and **per-platform manifest digests**. A tag can point to a manifest list rather than a single image. In CI, smoke-test the target deployment platform or use appropriate runners/emulation.

### 11.3. An OCI tar archive is a different output

A normal `docker build` loads the image into the local store. When you need to deliver an **OCI image layout tarball** instead of a local tag, Buildx provides an exporter:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  --output type=oci,dest=oci-demo.oci.tar \
  .
~~~

This command requires a Buildx builder supporting the `type=oci` exporter. It produces an OCI archive file and **does not automatically load the image into the local Docker daemon** for `docker run`. You must verify the exported/pushed image using the appropriate workflow, rather than assuming test results from another local tag apply automatically to the new OCI archive.

## 12. Using JRE, Non-Root, and Exec ENTRYPOINT Properly

### 12.1. JRE instead of Maven/JDK in the final image

The final image only needs the runtime to launch the JAR previously built by Maven. Keeping Maven, the compiler/JDK, the Git repository, and local `~/.m2` outside the image reduces size and attack surface. However, the base JRE still contains OS packages, CA certificates, and libraries that must be scanned and updated per policy.

Do not pick JRE 17 for a JAR containing Java 21 classes. The host gate might pass on JDK 21, but the image will fail when JVM 17 reads newer bytecode. The image smoke step catches this risk.

### 12.2. Non-root does not make every filesystem path writable

`USER 10001:10001` runs the process with a numeric non-root UID/GID. `COPY --chown` gives the user ownership of the JAR, but `WORKDIR /app` does not automatically grant write access to the whole directory. When the app needs to export files, write cache, or create temp files, configure the directory/mount and securityContext accordingly. Do not switch back to root just because you see `permission denied` without checking the exact path and permissions.

### 12.3. EXPOSE differs from publishing

`EXPOSE 8080` is only metadata about the intended port. `docker run -p 127.0.0.1:18081:8080` actually creates host port forwarding. If the app inside the container binds only to `127.0.0.1`, external traffic from Docker networking cannot reach it; in the example, Spring Boot is left to bind to an appropriate default interface.

### 12.4. Exec form and signals

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

With exec form, the Java process receives stop signals more directly than with shell form. Docker/Kubernetes typically sends SIGTERM first and then SIGKILL after a timeout; you should test graceful shutdown and your real application's shutdown hooks. Spring application arguments can be appended after the image name; JVM options like `-Xmx` and `-D...` must be placed **before `-jar`** or supplied via a suitable JVM configuration mechanism.

### 12.5. Do not rely on a healthcheck using missing tools

A minimal JRE image might not include `curl`, `wget`, or a shell. If a Dockerfile has `HEALTHCHECK CMD curl ...` without `curl` installed, the container will become unhealthy even if the app is fine. In Kubernetes, probes can be executed by the kubelet against an HTTP endpoint; when using Spring Boot Actuator, distinguish liveness/readiness and endpoint security policies.

## 13. Layered Images, Multi-Stage Builds, and Other Cases

### 13.1. Why copying the whole JAR is easy to audit

A Dockerfile that executes `COPY` on the exact JAR creates a direct verification path:

~~~text
verified host JAR
      |
    COPY
      |
      v
/app/application.jar inside image
      |
    docker cp + cmp
      |
      v
exact byte equality
~~~

The downside of this approach is that all dependency JARs sit in one uber JAR; changing a single application class can change the layer holding the entire JAR, making push/pull caching less efficient.

### 13.2. Spring Boot layered JAR

Spring Boot supports a layers index and layer extraction tools to separate dependencies, snapshot dependencies, the Boot loader, and application classes into distinct Docker layers. This allows Docker caching to preserve infrequently changing dependency layers when source code updates.

However, when the Dockerfile **extracts** instead of copying the whole JAR, the final image may no longer contain `/app/application.jar` as the original source file from the example. In that case, QA criteria must change:

1. Verify that the **input JAR to the extract step** is the artifact that passed the gate.
2. Use the `jarmode`/loader command matching your Spring Boot version.
3. Inspect the extracted files/layers and the actual runtime entrypoint.
4. Smoke-test the final image; do not just compare directory names.
5. Maintain provenance from the JAR checksum to the image digest.

Recent Spring Boot docs show `-Djarmode=tools` and `extract --layers`; do not assume every older Boot archive understands that exact command. A layered image can be more optimized, but it requires a clear QA process rather than blindly swapping out the simple Dockerfile in this lesson.

### 13.3. Multi-stage Docker builds differ from this workflow

A multi-stage Dockerfile can use a Maven/JDK stage to build from source and a JRE stage to copy the output. That workflow makes sense when you want to build inside a container, but **the file produced in the builder stage** must be verified. If a CI job tested host JAR A and then the Dockerfile built a separate JAR B, you cannot claim to have packaged A without comparing bytes.

Spring Boot `spring-boot:build-image` / Cloud Native Buildpacks can also create OCI-compatible images without a manual Dockerfile. That is a different option, not the approach practiced in this lesson.

## 14. Fail-Fast CI Pipeline

The pipeline should run in order:

~~~text
1. Checkout exact Git revision
2. Select controlled Maven, Java, and dependencies
3. mvn clean verify
4. Java SmokeJar.java runs exact target/oci-demo-1.0.0.jar
5. Record SHA-256 of the JAR that passed
6. docker build with exact Dockerfile and context
7. docker create/cp then cmp host/image JAR
8. docker run + HTTP probe with deadline
9. Scan dependencies/base image and verify platform
10. Push exact verified image, record registry digest
11. Deploy exact digest + smoke test target environment
~~~

| Gate | Pass Criteria | On Failure |
| --- | --- | --- |
| Maven package/test | Exit code 0, executable JAR at expected path | Stop Docker build |
| Packaged-JAR smoke | `java -jar` runs, HTTP 200 and expected body | Stop Docker build |
| JAR integrity | SHA recorded for the exact tested file | Do not transfer to another builder without verifying |
| Docker build | Exact `COPY`, right JRE, image built successfully | Stop image tests |
| Image/JAR byte check | File extracted from image matches tested JAR byte-for-byte | Stop publish |
| Container smoke | Process runs, HTTP 200 and expected body, cleanup | Stop publish |
| Registry publish | Push exact verified image, record digest/platform | Do not deploy unverified tag |

If jobs run on different runners, upload/download the **exact same JAR file** via artifact storage, verify its SHA immediately after download, and only then build the image. Do not re-run Maven inside the Docker job just to get another file and bypass the first gate.

Do not label builds `REPRODUCIBLE` merely because two image tags match. A byte-for-byte reproducible JAR and a reproducible OCI image are separate goals; base images, layer timestamps, compression, config, and arch can change even if the app JAR is untouched.

A useful release record captures commit SHA, JAR SHA, artifact path, base image digest, target platform, image registry digest, gate results, and links to build/test logs. Do not embed passwords or tokens in logs or `LABEL` instructions just for traceability.

## 15. Troubleshooting Common Failures

| Failure | Likely Cause | Check |
| --- | --- | --- |
| `COPY failed: file not found` | JAR not built yet, wrong build context, `.dockerignore` excludes file | Verify `target/...jar` and context root |
| `no main manifest attribute` | Plain JAR, `repackage` did not run | Inspect manifest, Boot loader, and classifier |
| `ClassNotFoundException` | Wrong archive or missing runtime dependencies | `jar tf`, `BOOT-INF/lib`, startup logs |
| `UnsupportedClassVersionError` | JRE image too old for bytecode | Java image version, Maven compiler target |
| Docker build passes, container exits immediately | JAR/config/JRE/runtime error | `docker logs`, process exit code |
| HTTP connection refused | Server not ready, wrong port, bound to loopback inside container | `-p`, `server.address`, logs |
| `EXPOSE 8080` yet host cannot connect | `EXPOSE` does not publish port | `docker run -p` or orchestrator networking |
| Host JAR hash differs from image JAR hash | Wrong file copied, JAR rebuilt after gate | Artifact path, sha256, and `docker cp` |
| `permission denied` writing files | Non-root UID lacks volume/temp directory permissions | User, mount ownership, writable path |
| Image works on AMD64, fails on ARM | Different base platform/JNI/native libs | Buildx `--platform`, target CPU |
| Container unhealthy | Healthcheck calls missing `curl` or wrong endpoint | Healthcheck implementation/probe |
| Shell ENTRYPOINT ignores SIGTERM | Shell wrapper does not forward signal | Exec-form entrypoint, shutdown logs |
| Same JAR bytes yet different image digest | Different base image/config/layers/compression | Inspect base/digest/layers separately |
| Same image tag deploys wrong version | Mutable tag, rebuilt/pushed after smoke | Registry digest and CI artifact ID |
| K8s fails even though `docker run` passes | Different network/secret/probe/securityContext/volumes | Deployment manifest, pod events/logs |
| Docker build context contains secrets | `COPY .` or loose ignore rules | Exact COPY, strict `.dockerignore`, image inspect |
| Remote builder missing JAR | Artifact not transferred to build context | Download artifact with matching hash before building |

**Do not assume `docker build --no-cache` cures every issue.** If you picked the wrong JAR, wrong JVM version, or wrong port binding, disabling cache does not solve the root cause. Track **which JAR was built, which JAR was copied, which image was run, and which image was published**.

## 16. Checklist and Self-Check Questions

### Pre-publish checklist

- [ ] Executable JAR built with the right version and artifact path.
- [ ] `java -jar` and HTTP smoke test from the packaged JAR pass before Docker build.
- [ ] SHA-256 of the passing JAR recorded and verified across job transfers.
- [ ] Dockerfile copies only the exact JAR, without silently rebuilding.
- [ ] JRE base image and CPU architecture match Java target and native libs.
- [ ] Uses non-root user, exec-form entrypoint, and appropriate permissions.
- [ ] `.dockerignore` excludes `.git`/secrets/unneeded source while still allowing the JAR.
- [ ] Build context is the project root as assumed by the Dockerfile.
- [ ] JAR inside the image extracted and byte-compared against the passing file.
- [ ] Container runs, HTTP probe passes, with timeout, logs, and cleanup.
- [ ] Image JRE, port, and bind address verified appropriately.
- [ ] Git revision, JAR SHA, image digest, and target platform recorded separately.
- [ ] Security scan, secret policy, and runtime configurations reviewed.
- [ ] Publish/deploy the **exact tested image**, without silently rebuilding or re-tagging.

### Question A

**Maven builds a JAR successfully, but `java -jar` reports `no main manifest attribute`. Should we copy the JAR into the image anyway?**

No. Fix or select the proper Spring Boot executable JAR and pass the JAR gate first. A Dockerfile does not turn a plain JAR into an executable archive.

### Question B

**Is it contradictory if two images have the same `/app/application.jar` yet different image digests?**

No. Images also contain the JRE/OS, manifest, config, and layers; those can differ while the JAR file bytes are identical.

### Question C

**Why is `EXPOSE 8080` insufficient to call `http://127.0.0.1:18081/probe` from the host?**

`EXPOSE` only documents the container port. You need `docker run -p 127.0.0.1:18081:8080` or orchestrator networking.

### Question D

**The host smoke-tested JAR A. The Docker build ran Maven again and produced JAR B. Can the image be considered to contain verified artifact A?**

No, unless you proved B is byte-identical to A and verified B under the proper procedure. Ideally, transfer A unchanged via artifact storage with SHA verification.

### Question E

**Does setting `USER 10001:10001` mean every directory inside the image is writable?**

No. A numeric non-root user reduces privileges; writable directories, `/tmp`, mounts, and volumes must be granted proper permissions.

### Question F

**Is an image tag `oci-demo:1.0.0` sufficient as an immutable deployment pin?**

No. Tags can be reassigned. Use the registry digest of the published and verified image, alongside source SHA, JAR SHA, and platform.

## 17. Official Documentation

- Spring Boot 3.5 — Container Images: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/index.html
- Spring Boot — Dockerfiles and Layered JARs: https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Efficient Container Images: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/efficient-images.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Docker — Dockerfile Reference: https://docs.docker.com/reference/dockerfile/
- Docker — Build Context and .dockerignore: https://docs.docker.com/build/concepts/context/
- Docker — Building Best Practices: https://docs.docker.com/build/building/best-practices/
- Docker — Docker Buildx Exporters/OCI Tar: https://docs.docker.com/build/exporters/
- Docker — docker cp: https://docs.docker.com/reference/cli/docker/container/cp/
- Docker — docker image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Eclipse Temurin Docker Official Image: https://hub.docker.com/_/eclipse-temurin
- Open Container Initiative — OCI Image Specification: https://github.com/opencontainers/image-spec
- Java 17 — ProcessBuilder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Java 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html

**Conclusion:** Verify a Spring Boot JAR first, then **package those exact JAR bytes** into an image with a suitable JRE. After the Docker build, verify **the JAR file inside the image** and **the container runtime** with two separate checks, then publish the exact QA-passed image digest. `BUILD SUCCESS`, a readable tag, or the mere presence of a JAR file alone **does not** prove the deployed image is the verified build.