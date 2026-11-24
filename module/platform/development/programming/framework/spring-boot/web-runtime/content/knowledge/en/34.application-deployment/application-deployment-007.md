# Read-Only Directories, Process Accounts, and Temporary File Write Permissions

## 1. Lesson Objectives and Spring Boot Deployment Problems

Under the **Application Deployment** topic of the **Spring Boot - web-runtime** module, a Java application is typically built into an executable JAR, packaged into a container, and run behind a Kubernetes Service/Ingress. When moving from a developer machine to a hardened container, the app can unexpectedly fail right at startup or during file uploads:

~~~text
java.nio.file.AccessDeniedException: /app/...
java.nio.file.FileSystemException: /tmp/...: Read-only file system
java.io.IOException: Permission denied
java.nio.file.FileSystemException: ...: No space left on device
java.lang.IllegalStateException: Unable to create tempDir
~~~

These messages are **symptom examples**, not a fixed stack trace: exact exception names depend on the code layer, Servlet container, filesystem, storage driver, and OS.

This task requires resolving three distinct design decisions:

1. **Read-only root filesystem:** the container must not write into `/app`, `/etc`, or paths baked into the running image.
2. **Process account:** the JVM runs under a non-root UID/GID with minimal Linux privileges.
3. **Temporary write area:** components needing scratch space (Tomcat, Servlet multipart uploads, `java.io.tmpdir`, file-processing libraries) still have an **explicitly writable, quota-bounded mount with the right lifecycle**.

These three goals **do not conflict**: a container can have a read-only root filesystem and still write to an **intentionally mounted `emptyDir`/tmpfs/PVC** when UID/GID and access modes permit.

After this lesson, you can:
- Distinguish image layers, root filesystem, mounted volumes, OS file permissions, and the Java temp directory.
- Configure a Dockerfile to run with a non-root UID/GID.
- Enable Kubernetes `readOnlyRootFilesystem`, `runAsNonRoot`, `runAsUser`, `runAsGroup`, `fsGroup`, and mount `emptyDir` properly.
- Configure `java.io.tmpdir`, `spring.servlet.multipart.location`, and understand `server.tomcat.basedir`.
- Run a **Java 17 + Spring Boot 3.3.13** lab with endpoints testing temp file write/delete and multipart uploads.
- Diagnose `AccessDeniedException`, read-only filesystem, `ENOSPC`, startup/readiness failures, quotas, and uncleaned temp files.
- Know when a PVC/object storage is needed instead of `emptyDir`.

## 2. File Model Inside a Container

A container filesystem typically consists of **image layers** built from the Dockerfile plus a writable layer while the container runs, though that writable layer is not where durable data belongs. With Docker **`--read-only`** or Kubernetes **`readOnlyRootFilesystem: true`**, the root filesystem is mounted read-only.

~~~text
Image:
  /app/app.jar             fixed JAR in the image
  /etc/...                 OS configuration
  /usr/lib/jvm/...         Java runtime
          |
          v
Running container with read-only root filesystem
  /app/app.jar             readable, NOT writable
  /etc                    readable, NOT writable
  /tmp                    may not be writable unless mounted separately
  /scratch --------------> writable emptyDir or tmpfs
  /config  --------------> read-only ConfigMap/Secret
  /data    --------------> PVC if the application truly needs persistence
~~~

**`readOnlyRootFilesystem` applies only to the container's root filesystem**, and does not automatically make all volumes read-only. A writable volume mount stays writable according to its mount flags, permissions, security contexts, and runtime policies.

This differs from:
- **Immutable image:** the image digest does not change, yet the container can still have a writable overlay unless read-only root is enabled.
- **`volumeMounts.readOnly: true`:** a specific mount is read-only, independent of the root filesystem.
- **ConfigMap/Secret volumes:** normally provide config/secrets as read-only, not scratch disk.
- **Non-root UID:** prevents the process from using normal root privileges, yet does not make the filesystem read-only if a directory permits writes.
- **Linux file mode `0444`/`0555`:** permissions per file/owner/group; still distinct from a read-only mount.
- **Kubernetes PersistentVolumeClaim:** stores data with its own lifecycle, neither read-only nor temporary by default.

Never “fix” file write errors by running the container as root or mounting the entire host root filesystem into the Pod. Identify **which exact paths actually need writes** and grant minimal permissions to that specific mount.

## 3. Why Does a Web App Still Write Files When Its Source Code Only Reads?

A Spring Boot API may never call `FileOutputStream` in business code yet still create files:

| Component | When it may write | Where to check |
| --- | --- | --- |
| JDK NIO / `Files.createTempFile` | Temporary files in application code | `java.io.tmpdir` system property or explicit `Path` |
| Spring MVC `MultipartFile` | HTTP `multipart/form-data` upload buffering/spooling | `spring.servlet.multipart.location` |
| Embedded Tomcat | Tomcat base/work/temp directory, servlet context tempdir | `server.tomcat.basedir` and `java.io.tmpdir` |
| Third-party PDF/image/video tools | Intermediate output, unzip, caches | Tool-specific `TMPDIR`/config, subprocess environment |
| Logging | File append/rotation | `logging.file.name`/`path` or Logback `FileAppender` |
| H2/SQLite/file-backed databases | Local persistent data/log files | Datasource URL, file permissions; avoid scratch for critical data |
| TLS/library/native components | Temp files, extracted native libraries, caches | `java.io.tmpdir`, JNI/native library requirements |
| Report/export | Generating intermediate ZIP/CSV/PDF | Configured workspace or streaming strategy |
| Actuator heapdump/diagnostics | Large output when diagnostic actions run | Explicit path and disk quota |
| JVM attach tooling | Sockets or auxiliary files depending on runtime | `/tmp` and runtime tool behavior |

**Do not assume “the app only reads the JAR so it will definitely run with a read-only root”.** The Servlet container and dependencies can create temp directories at startup; uploads can hit disk even when the controller only reads an `InputStream` and discards it.

### 3.1. Spring Boot 3.3 Multipart Can Spool to Disk

Spring Boot 3.3 provides:
- **`spring.servlet.multipart.enabled`**, default `true`.
- **`spring.servlet.multipart.file-size-threshold`**, default **`0B`**: above this threshold, multipart content can be spooled to disk instead of kept solely in RAM.
- **`spring.servlet.multipart.location`**: intermediate directory for uploaded files.
- **`spring.servlet.multipart.max-file-size`**, default **`1MB`**.
- **`spring.servlet.multipart.max-request-size`**, default **`10MB`**.

These defaults are verified against **Spring Boot 3.3 application properties**. If root is read-only and `location` does not point to a writable mount, multipart requests can fail during Servlet parsing **before the controller ever receives `MultipartFile`**.

Raising `file-size-threshold` to a huge number to “avoid disk” is not a universal fix: uploaded payloads consume RAM, increasing GC/OOM pressure, and other libraries still need temp space. Use a **bounded scratch mount**, enforce `max-file-size`/`max-request-size`, and stream data where appropriate.

### 3.2. Tomcat Has Its Own Work Directory

**`server.tomcat.basedir`** sets Tomcat's base directory; when unspecified, Spring Boot may use a temporary directory. Tomcat's servlet context also uses **`jakarta.servlet.context.tempdir`** for apps needing scratch space. See Tomcat Host/Context **`workDir`** in the Tomcat docs.

Setting **`-Djava.io.tmpdir=/scratch`** at JVM startup helps components relying on Java's default temporary directory find the writable mount. However, **not every library honors `java.io.tmpdir`**; some read `TMPDIR`, hardcode `/tmp`, or use app home, current working directory, or custom config. Inventory and test them.

### 3.3. Logging Should Use stdout/stderr

In containers:
- Prefer **console logging** via stdout/stderr so the container runtime collects logs.
- Do not default to writing log files into **`/app/logs`**, **`/var/log`**, or the writable layer.
- If file logging is mandatory (legacy product or integration), mount a dedicated directory with defined rotation, quotas, and retention.
- Never “fix” it with `chmod 777` across the image or running as root to write anywhere.

## 4. Process Account: UID, GID, and Linux Permissions

Linux checks file access using process credentials:
- **UID**: effective user ID.
- **GID**: primary group ID.
- **Supplementary groups**: additional groups.
- **Owner/group/other mode bits**, ACLs, and security modules like SELinux/AppArmor.
- **Mount flags**, read-only mounts, storage backend/CSI permissions.

Example:

~~~text
drwxr-xr-x  root root   /app
-rw-r--r--  root root   /app/app.jar
drwxrwx---  app  app    /scratch
~~~

A Java process running as UID 10001, GID 10001:
- Can read `/app/app.jar` if permissions allow.
- Cannot modify `/app/app.jar` when the root filesystem is read-only.
- Can create files in `/scratch` if the mount is writable and directory mode/group allow.
- Does not need root privileges to bind port **8080** (ports above 1023).

Running non-root shrinks the blast radius if the app is exploited, though it **is not a complete sandbox**. You still need network policies, Secret management, seccomp, capabilities, image scanning, RBAC, and input validation.

### 4.1. Dockerfile USER Differs from Kubernetes runAsUser

- **Dockerfile `USER 10001:10001`** sets the default process identity when running the image.
- **`docker run --user 10001:10001`** can override the identity at container creation.
- **Kubernetes `runAsUser: 10001` / `runAsGroup: 10001`** sets the process UID/GID in the Pod `securityContext`, overriding image defaults.
- **Kubernetes `runAsNonRoot: true`** prevents the runtime from launching the process with UID 0.
- **`fsGroup: 10001`** adds a supplementary group for supported volume access; it does not change ownership of files baked into the image.
- **`supplementalGroups`** can grant additional volume access; do not add overly broad groups unnecessarily.

Do not assume a username exists for every UID. Many production images use numeric UIDs with no `/etc/passwd` entry; some libraries require `user.home` or `getpwuid` to work. Test your base runtime image and avoid apps depending on a writable `HOME` inside the root filesystem.

### 4.2. fsGroup Is Not a Universal Fix for All Permission Issues

Kubernetes can apply **`fsGroup`** to volumes supporting ownership management; the process receives the group and directories become group-writable. However:
- PVC behavior depends on the storage/CSI driver, NFS `root_squash`, mount options, and SELinux.
- **`fsGroupChangePolicy`** does not apply to certain ephemeral volume types such as `emptyDir`/ConfigMap/Secret per Kubernetes docs.
- A directory mounted read-only remains unwritable regardless of `fsGroup`.
- Running an `initContainer` as root just to `chmod`/`chown` broadly may violate Pod Security policies or introduce security risks.
- If too many Pods share one broad GID, they may access each other's volume data if mounts/policies are misconfigured.

In the lab, **`emptyDir` + `runAsGroup`/`fsGroup=10001`** is used and verified via a startup write probe. Real applications must verify their specific storage driver and cluster behavior.

## 5. Read-Only Root Filesystem: Protection Scope and Exceptions

Kubernetes container config:

~~~yaml
securityContext:
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
~~~

This YAML is only a **container `securityContext` fragment**, not a complete Pod. With `readOnlyRootFilesystem`:
- Writes to `/app` on the root filesystem fail, even if the image created that directory.
- File creation in `/tmp` fails if `/tmp` sits on the root filesystem with **no writable mount**.
- Writes to `/scratch` succeed if a writable volume is mounted there.
- Separate ConfigMap/Secret mounts remain readable if permissions and mounts allow.
- Writable bind mounts or PVCs remain writable, so evaluate the security policy of the whole Pod.

**Running as root (UID 0) does not “bypass” a read-only mount**, and running non-root does not make the root filesystem read-only. They are two independent hardening layers.

### 5.1. A Mount at /scratch Shadows Image Contents

If the Dockerfile creates `/scratch/some-default-file` and Kubernetes mounts **`emptyDir`** onto `/scratch`, files from the image under that path **are hidden by the mount** at runtime. Keep default configuration data under `/app` or `/config`, leaving `/scratch` solely as a fresh temporary mount point.

### 5.2. Do Not Use Image Directories as Data Stores

A JAR at `/app/app.jar` should never write updates into `/app`. For runtime config, prefer ConfigMaps/Secrets or environment variables. For durable output, use object storage, a database, or a PVC. For temporary artifacts, use `emptyDir`/tmpfs with quotas and cleanup.

## 6. Which Volume Should You Choose for Temporary Files?

| Type | Writable? | Lifetime | Use when |
| --- | --- | --- | --- |
| Container writable root layer | Yes if root is not read-only | Container lifecycle | Do not rely on it for retaining data |
| `emptyDir` disk-backed | Yes when mount/permissions allow | Pod lifetime; survives container restarts in the same Pod | Tomcat scratch, multipart spool, temporary cache |
| `emptyDir` `medium: Memory` | Yes | Pod lifetime, stored in RAM/tmpfs | Small high-speed scratch; must budget memory |
| Docker `--tmpfs` | Yes when mount options allow | Container lifetime, non-persistent | Local Docker testing with `--read-only` |
| ConfigMap/Secret volume | Read-only for config/secret purposes | Per Pod/project config | Reading configuration and credentials, never scratch |
| PersistentVolumeClaim | Per access mode/permissions | PVC/PV lifecycle | Output that must survive Pod deletion |
| Object storage | Not a direct local filesystem | Bucket lifecycle | Uploaded files, reports, blobs requiring durability |

### 6.1. emptyDir Is Not Persistent Storage

Kubernetes creates an `emptyDir` when a Pod is scheduled to a node. A container crash/restart **does not delete `emptyDir`** within the same Pod. However, when the Pod is deleted or evicted from the node, `emptyDir` data is erased. Never store customer images, orders, records, or documents that must survive deployments in it.

Temp files can be deleted when a request finishes, yet if the process receives `SIGKILL`, `finally` cleanup is not guaranteed to run. With `emptyDir`, while the Pod survives, orphaned files can persist across container restarts; implement stale-file cleanup via TTL/ownership policies.

### 6.2. Disk-Backed emptyDir vs Memory tmpfs

- **`emptyDir: {}`** uses node local ephemeral storage; it is subject to disk pressure, kubelet eviction, and `ephemeral-storage` limits.
- **`emptyDir.medium: Memory`** uses tmpfs; contents count toward container/Pod memory usage in Kubernetes accounting and can push the process to OOM.
- **`sizeLimit`** is helpful, though not all storage drivers/node setups enforce identical hard limits at every instant. Observe actual runtime behavior.
- Never back an unbounded tmpfs with unlimited upload payloads; large memory-backed uploads compete directly with Java heap, direct buffers, thread stacks, and native memory.

### 6.3. Do Not Use a PVC Just to Avoid Configuring Temp

A PVC provides persistence, which is usually unnecessary for per-request scratch. It adds data-sharing, cleanup, and storage-cost overhead. When the goal is just multipart spooling and `File.createTempFile`, a quota-bounded `emptyDir` is the standard choice. When files must be durable, copy/stream them to object storage or a database under a business transaction.

## 7. Configuring Java and Spring Boot to Point to the Right Temp Directory

In this lab, **`/scratch`** is standardized as the single writable mount for intermediate files:

~~~text
/scratch/
  multipart/           Spring Servlet multipart spooling area
  tomcat.*/            directories created by embedded Tomcat when needed
  probe-*.tmp          file created to check write permission, deleted immediately
~~~

Three layers must be aligned consistently:

**Java runtime, before the process starts:**

~~~bash
java -Djava.io.tmpdir=/scratch -jar /app/app.jar
~~~

In Docker you can use:

~~~dockerfile
ENV JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/scratch"
~~~

**Spring Boot multipart:**

~~~yaml
spring:
  servlet:
    multipart:
      location: /scratch/multipart
      file-size-threshold: 0B
      max-file-size: 1MB
      max-request-size: 2MB
~~~

**Optional Tomcat base directory:**

~~~yaml
server:
  tomcat:
    basedir: /scratch/tomcat
~~~

The **`server.tomcat.basedir`** snippet is an **optional fragment**, not part of the default lab. If declared, ensure Tomcat can create/use that path with the right permissions **from startup**; do not wait for an `ApplicationRunner` to create the directory after the web server starts.

When `basedir` is unconfigured, Spring Boot 3.3 notes that Tomcat uses a **temporary directory**; setting `java.io.tmpdir` prior to JVM startup gives the default temp a writable location. Verify by running the real container, as Tomcat and other libraries may have separate work directories.

### 7.1. Why Not Just Set the TMPDIR Environment Variable?

Java uses the **`java.io.tmpdir`** system property, and Java temp APIs rely on it. The **`TMPDIR`** environment variable may affect certain native tools or JVM startup on some platforms, but should not be treated as the sole control for Java's temp path. Passing `-Djava.io.tmpdir` at JVM launch is explicit, alongside configuring libraries with their own paths.

Do not call **`System.setProperty("java.io.tmpdir", "/scratch")`** inside a running controller expecting every JDK class that already cached the default temp path to update. Configure it before the JVM starts and test.

### 7.2. Verify Write Permissions with Real I/O

**`Files.isWritable(path)`** is useful, but insufficient to prove free space, quotas, ACLs, mount flags, or namespace permissions at actual write time. A safe startup check can:
1. Ensure the directory exists.
2. Create a randomized file with **`Files.createTempFile`** inside the target directory.
3. Write a small string.
4. Read back to verify if needed.
5. Delete in `finally`.
6. Never log sensitive file contents or secret paths.

If startup cannot write to scratch, fail startup or keep readiness false when core functionality depends on it, rather than reporting healthy and failing on the first upload.

## 8. Spring Boot 3.3.13 + Java 17 Lab: Temp Files and Multipart Upload

This lab intentionally uses:
- Embedded Tomcat and **`spring-boot-starter-web`**.
- **`spring-boot-starter-actuator`** for readiness/liveness probes.
- An **`ApplicationRunner`** checking scratch writability at startup.
- **`POST /api/temp/probe`** creating/writing/reading/deleting a temp file.
- **`POST /api/upload`** receiving a multipart file and computing its SHA-256 and byte length without persisting the file.
- Multipart location configured to **`/scratch/multipart`**.
- Docker image running as **UID/GID 10001**, with read-only root filesystem when mounted in Docker/Kubernetes.
- Kubernetes writable `emptyDir` at `/scratch`, `readOnlyRootFilesystem=true`, and `fsGroup`.

**The lab uses dummy data only and runs in authorized localhost/staging environments.** The POST endpoints lack authentication for easy testing; **never expose this lab to the public Internet**. Production requires authentication, authorization, rate limiting, content validation, scanning where needed, quotas, and never treating temporary upload files as durable assets.

### 8.1. Directory Tree

~~~text
readonly-runtime-demo/
├── pom.xml
├── Dockerfile
├── k8s.yaml
└── src/
    ├── main/
    │   ├── java/com/example/readonly/
    │   │   └── ReadonlyRuntimeApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/readonly/
            └── FilesystemHttpTest.java
~~~

### 8.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>readonly-runtime-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`starter-validation` is not needed for the lab's two simple endpoints. In production applications with DTO validation, include **`spring-boot-starter-validation`** appropriately.

### 8.3. application.yml

**`src/main/resources/application.yml`:**

~~~yaml
server:
  port: 8080

spring:
  servlet:
    multipart:
      location: /scratch/multipart
      file-size-threshold: 0B
      max-file-size: 1MB
      max-request-size: 2MB

app:
  temp-dir: /scratch

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

**Key details:**
- **`app.temp-dir`** is a custom lab property read via Java `Environment`; it is not a built-in Spring Boot property.
- **`spring.servlet.multipart.location`** is standard Boot configuration for Servlet multipart.
- **`file-size-threshold: 0B`** lets you verify actual write permissions whenever multipart needs to spool.
- **`max-file-size`/`max-request-size`** provide basic input bounds, not a replacement for disk quotas or concurrency limits.
- **`probes.enabled`** creates **`/actuator/health/liveness`** and **`/actuator/health/readiness`** even outside Kubernetes.
- Expose only **`health`** from Actuator; production also needs network/authentication policies for management endpoints.

If running the JAR directly on a machine without `/scratch`, override both **`app.temp-dir`** and **`spring.servlet.multipart.location`**; section 8.7 shows the local commands.

### 8.4. Complete Java Source

**`src/main/java/com/example/readonly/ReadonlyRuntimeApplication.java`:**

~~~java
package com.example.readonly;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class ReadonlyRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReadonlyRuntimeApplication.class, args);
    }
}

@Configuration
class TempBootstrap {

    @Bean
    ApplicationRunner ensureScratchWritable(Environment env) {
        return args -> {
            Path root = Path.of(
                env.getProperty("app.temp-dir", "/scratch")
            ).toAbsolutePath().normalize();

            // Create required directories after the volume has been mounted.
            Files.createDirectories(root.resolve("multipart"));

            Path probe = Files.createTempFile(
                root, "startup-probe-", ".tmp"
            );
            try {
                Files.writeString(
                    probe, "ready", StandardCharsets.UTF_8
                );
                String actual = Files.readString(
                    probe, StandardCharsets.UTF_8
                );
                if (!"ready".equals(actual)) {
                    throw new IOException("Scratch readback mismatch");
                }
            } finally {
                Files.deleteIfExists(probe);
            }
        };
    }
}

record UploadSummary(long bytes, String sha256) {}

@RestController
class TempController {

    private final Path scratch;

    TempController(Environment env) {
        this.scratch = Path.of(
            env.getProperty("app.temp-dir", "/scratch")
        ).toAbsolutePath().normalize();
    }

    @PostMapping("/api/temp/probe")
    Map<String, Object> tempProbe() throws IOException {
        Path file = Files.createTempFile(
            scratch, "request-probe-", ".txt"
        );
        try {
            Files.writeString(
                file, "temporary-data", StandardCharsets.UTF_8
            );
            String read = Files.readString(
                file, StandardCharsets.UTF_8
            );
            return Map.of(
                "writable", "temporary-data".equals(read),
                "deletedAfterResponse", true
            );
        } finally {
            Files.deleteIfExists(file);
        }
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<UploadSummary> upload(
            @RequestParam("file") MultipartFile file
    ) throws IOException, NoSuchAlgorithmException {

        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        long totalBytes = 0;
        byte[] buffer = new byte[8192];

        // Only read stream, do not trust client filename
        // and do not turn it directly into a server path.
        try (InputStream in = file.getInputStream()) {
            int count;
            while ((count = in.read(buffer)) != -1) {
                sha.update(buffer, 0, count);
                totalBytes += count;
            }
        }

        UploadSummary result = new UploadSummary(
            totalBytes,
            HexFormat.of().formatHex(sha.digest())
        );
        return ResponseEntity.ok(result);
    }
}
~~~

### 8.5. Layer-by-Layer Code Explanation

**ApplicationRunner:**
- Executes after Spring Boot builds the application context and embedded server, before the app is marked ready under the normal lifecycle.
- Creates **`/scratch/multipart`** on the writable volume and verifies create/write/read/delete of a temp file.
- If `IOException`/`AccessDeniedException` occurs, startup fails instead of marking the instance ready only to break on the first upload.
- If the mount is not writable or `fsGroup` did not grant permissions as expected, the error surfaces immediately at startup.

**Important note:** Tomcat may need to create its base/temp directory **before `ApplicationRunner` runs**, since the server starts before runners. Therefore Java's **`java.io.tmpdir`** system property must be set **before JVM start**, not deferred to `ApplicationRunner`. The Docker/Kubernetes sections configure `JAVA_TOOL_OPTIONS` upfront.

**Temp probe endpoint:**
- **`Files.createTempFile(scratch, prefix, suffix)`** uses unpredictable filenames instead of client-controlled paths, reducing collision/symlink race risks.
- **`Files.writeString` / `readString`** tests real write access, not just `Files.isWritable()`.
- **`finally Files.deleteIfExists`** cleans up on both normal completion and exceptions.
- The **`deletedAfterResponse`** field in the demo simply indicates execution reached cleanup upon normal method return—not proof that the file is guaranteed cleaned in all failure cases (`SIGKILL` bypasses `finally`). Clients must not treat that field as a security guarantee.
- Never return absolute scratch paths, UIDs, temp filenames, or host internals in public responses.

**Upload endpoint:**
- Servlet multipart resolver may use **`/scratch/multipart`** before the Controller runs, depending on thresholds.
- The Controller reads the `InputStream` in 8 KiB chunks and computes **SHA-256** and byte count.
- Never pass **`MultipartFile.getOriginalFilename()`** into `Path`. Client filenames are **untrusted input** that can contain path traversal or malicious characters.
- Uploaded files are not persisted; once the request completes, the Servlet/container cleans up temporary multipart parts per its lifecycle.
- SHA-256 is a data fingerprint, not antivirus scanning or MIME validation.
- If real persistence is needed, stream to object storage or an authorized storage service rather than using `emptyDir` as primary storage.

**Code and errors:** the lab lets `IOException` propagate as 5xx if scratch loses writability. Production should return clean error responses, redacted logs, metrics, and readiness/admission handling when disk fills up. Never swallow every `IOException` and return HTTP 200.

### 8.6. Do Not Fake Read-Only Tests with an App That Never Writes

The lab actively exercises write paths; a hello-world JSON app might appear to work with a read-only root even without scratch, leaving a blind spot. Multipart uploads, reporting, exports, and Tomcat startup must all be exercised. Production CI/container tests should run a regression test with **read-only rootfs + writable temp mount**, rather than testing Java only outside containers.

## 9. JUnit Integration Test on a Real HTTP Server

**`src/test/java/com/example/readonly/FilesystemHttpTest.java`:**

~~~java
package com.example.readonly;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class FilesystemHttpTest {

    @DynamicPropertySource
    static void configureTemp(DynamicPropertyRegistry registry) {
        // Tests run on local machine:
        // use OS temp path instead of /scratch which only exists in the container.
        registry.add(
            "app.temp-dir",
            () -> System.getProperty("java.io.tmpdir")
        );
        registry.add(
            "spring.servlet.multipart.location",
            () -> System.getProperty("java.io.tmpdir")
        );
    }

    @Autowired
    TestRestTemplate http;

    @Test
    void tempProbeCanWriteAndDelete() {
        ResponseEntity<Map> response =
            http.postForEntity("/api/temp/probe", null, Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(Boolean.TRUE, body.get("writable"));
        assertEquals(Boolean.TRUE, body.get("deletedAfterResponse"));
    }

    @Test
    void multipartUploadCanBeParsedOnRealTomcat() {
        byte[] bytes = "abc\n".getBytes(StandardCharsets.UTF_8);

        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return "sample.txt";
            }
        };

        MultiValueMap<String, Object> form =
            new LinkedMultiValueMap<>();
        form.add("file", resource);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        HttpEntity<MultiValueMap<String, Object>> request =
            new HttpEntity<>(form, headers);

        ResponseEntity<Map> response =
            http.postForEntity("/api/upload", request, Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(4L, ((Number) body.get("bytes")).longValue());

        String sha = String.valueOf(body.get("sha256"));
        assertTrue(sha.matches("[0-9a-f]{64}"));
    }
}
~~~

### 9.1. Why `@SpringBootTest(RANDOM_PORT)`?

**`@SpringBootTest(webEnvironment=RANDOM_PORT)`** starts a real embedded Tomcat on a random port. Multipart requests go through Servlet multipart parsing and temporary storage, matching web-runtime behavior far closer than a unit test calling `controller.upload()` directly.

**`@DynamicPropertySource`** overrides `app.temp-dir` and `spring.servlet.multipart.location` with the test host OS's temp directory so developer machines do not need `/scratch`. Still, this test **does not verify `readOnlyRootFilesystem`**, since local hosts do not mount rootfs read-only. You must verify that separately in Docker/Kubernetes.

### 9.2. Do Not Hardcode Fixed SHA-256 Unless Needed

The test asserts a 64-char hex digest and exact byte count rather than tying stdout to Spring Boot logs. If an API contract specifies exact SHA-256 outputs, compute the expected fixture digest and compare, though this lesson focuses on filesystem/temporary upload paths.

### 9.3. Note When Testing JVM Temp Path

Some Java APIs/libraries cache the default temp location at JVM startup. `DynamicPropertySource` updates **Spring environment properties** like `app.temp-dir`/`multipart.location`; it does not dynamically alter **`java.io.tmpdir`** after the JVM starts. In containers, set the JVM property at launch or via `JAVA_TOOL_OPTIONS`.

## 10. Running the JAR Locally

Requires JDK 17+, Maven, and port 8080 free. From the project directory:

~~~bash
mvn test
mvn package
~~~

Run directly on Linux/macOS with writable `/tmp`:

~~~bash
java -Djava.io.tmpdir=/tmp \
  -jar target/readonly-runtime-demo-1.0.0.jar \
  --app.temp-dir=/tmp \
  --spring.servlet.multipart.location=/tmp
~~~

**Note:** this is a local machine lab without a read-only root filesystem. If `/tmp` does not exist or is unwritable, substitute a temp directory you created with appropriate permissions, and verify CLI arguments are not dropped by tools/IDEs.

In another terminal, create a sample file:

~~~bash
printf 'abc\n' > sample.txt

curl -i -X POST http://localhost:8080/api/temp/probe
curl -i -F "file=@sample.txt" http://localhost:8080/api/upload
curl -i http://localhost:8080/actuator/health/readiness
~~~

Successful response from **`POST /api/temp/probe`** has a JSON body matching:

~~~json
{"writable":true,"deletedAfterResponse":true}
~~~

Response from **`POST /api/upload`** has **`bytes=4`** and **`sha256`** as a 64-character hex string. JSON property ordering and HTTP headers are not guaranteed byte-for-byte. Startup logs contain timestamps, thread names, and runtime details that vary by environment.

**Do not test with sensitive real data:** the sample file holds `"abc"` and a newline. Never upload secrets, personal photos, or production documents to an unauthenticated demo.

## 11. Non-Root Dockerfile and Read-Only Root Filesystem

The **`Dockerfile`** uses Ubuntu-based Eclipse Temurin JRE 17 and sets UID/GID 10001:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 \
       --home-dir /nonexistent \
       --shell /usr/sbin/nologin app \
    && mkdir -p /app /scratch \
    && chown 10001:10001 /app /scratch

WORKDIR /app
COPY --chown=10001:10001 \
    target/readonly-runtime-demo-1.0.0.jar /app/app.jar

ENV JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/scratch"

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Explanation:**
- **`FROM ...:17-jre-jammy`** provides Java 17 plus Linux tools to create the account during image build. Pin digests and scan CVEs for production.
- **`groupadd`/`useradd`** run only in the build layer and do not give runtime Java root privileges.
- **`COPY --chown`** sets JAR ownership, while read-only rootfs further prevents writes.
- **`USER 10001:10001`** sets the non-root default. K8s still enforces `securityContext`.
- **`JAVA_TOOL_OPTIONS`** sets `java.io.tmpdir` **from JVM launch**. The JDK prints `"Picked up JAVA_TOOL_OPTIONS"`, which is normal.
- **`EXPOSE 8080`** is container metadata only; publishing requires `docker run -p` or a Kubernetes Service.
- **JSON exec-form `ENTRYPOINT`** ensures the JVM receives signals per container runtime semantics instead of a shell wrapper failing to forward `TERM`.

**Never mount the host Docker socket** into the app and never use a privileged container just to write temp files. Never run `chmod -R 777` on `/app` or `/scratch`; assign explicit owner/group permissions.

### 11.1. Build the Image

~~~bash
mvn package
docker build -t readonly-runtime-demo:1.0.0 .
~~~

**Running the image normally** works because the default container root overlay is writable. That **is not a read-only test**. To test the security boundary, run Docker with **`--read-only`** and provide a separate tmpfs mount:

~~~bash
docker run --rm --name readonly-runtime-demo \
  -p 127.0.0.1:8080:8080 \
  --read-only \
  --tmpfs /scratch:rw,nosuid,nodev,noexec,size=64m,uid=10001,gid=10001,mode=0770 \
  readonly-runtime-demo:1.0.0
~~~

Docker's `--tmpfs` mount creates a writable memory scratch filesystem at `/scratch`, while `/app` and the image root stay read-only. Mount UID/GID match the process. Depending on Docker version and platform (Linux/Docker Desktop), `uid`/`gid`/`mode` behavior can vary; verify with **`docker exec ... id`**, **`ls -ld /scratch`**, and real writes.

**`noexec`** prevents executing binaries from scratch. However, some native libraries/JNI tools genuinely need an executable temp area; adjust based on your threat model rather than removing `noexec` blindly.

### 11.2. Docker Smoke Test

While the container runs in another terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/temp/probe

printf 'abc\n' > sample.txt
curl -i -F "file=@sample.txt" http://localhost:8080/api/upload

docker exec readonly-runtime-demo id
docker exec readonly-runtime-demo sh -c 'touch /app/should-fail'
~~~

The first three commands should succeed against the localhost demo. **`touch /app/should-fail`** is expected to **fail** because the root filesystem is read-only; the CLI may report **`Read-only file system`** or **`Permission denied`** depending on the layer. This is an **intentional negative check**, not an app bug.

In this lab, the Ubuntu-based Docker image includes `sh`/`id`/`touch`. Distroless images lack a shell and coreutils; in that case test via Java probes, authorized ephemeral debug containers, or integration tests instead of treating missing `sh` as a filesystem defect.

### 11.3. Testing the Missing-Scratch Failure

Not for production! Running the image with **`--read-only` and without `--tmpfs /scratch`** can prevent Spring Boot from starting because `java.io.tmpdir=/scratch` is unwritable when embedded Tomcat needs temp. Failure may occur **before `ApplicationRunner`**, so startup probe messages might not appear. This demonstrates why scratch must be mounted before the JVM starts.

To test this cleanly without impacting other containers, use a dedicated container with a short timeout, inspect logs, and remove it. Never switch the image to root to “help the lab pass”.

## 12. Complete Kubernetes Deployment + Service

After building the image, with a local **kind cluster** you can load it:

~~~bash
docker build -t readonly-runtime-demo:1.0.0 .
kind load docker-image readonly-runtime-demo:1.0.0
~~~

On other clusters, push to an approved private registry; **do not assume local Docker images automatically exist in every cluster**.

File **`k8s.yaml`**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: readonly-runtime-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: readonly-runtime-demo
  template:
    metadata:
      labels:
        app: readonly-runtime-demo
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: readonly-runtime-demo:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-Djava.io.tmpdir=/scratch"
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: scratch
              mountPath: /scratch
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
              ephemeral-storage: 64Mi
            limits:
              memory: 512Mi
              ephemeral-storage: 256Mi
      volumes:
        - name: scratch
          emptyDir:
            sizeLimit: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: readonly-runtime-demo
spec:
  type: ClusterIP
  selector:
    app: readonly-runtime-demo
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

### 12.1. Why Does the Manifest Set securityContext in Two Places?

**Pod `securityContext`:**
- **`runAsUser`/`runAsGroup`**: UID/GID of the Java process.
- **`runAsNonRoot: true`**: forbids running as UID 0.
- **`fsGroup: 10001`**: group applied to supported volumes.
- **`seccompProfile: RuntimeDefault`**: uses the runtime's default seccomp profile where supported.

**Container `securityContext`:**
- **`readOnlyRootFilesystem: true`**: read-only root filesystem.
- **`allowPrivilegeEscalation: false`**: prevents privilege escalation via available mechanisms.
- **`capabilities.drop: ALL`**: drops extra Linux capabilities, appropriate for an HTTP Java service binding port 8080.

These settings align partially with **Pod Security Restricted**, though they do not guarantee acceptance under every cluster admission policy. Check your cluster's security policies and Kubernetes version.

### 12.2. Mounting emptyDir Keeps Root Read-Only While Temp Is Writable

The only declared writable mount is **`/scratch`**. Spring:
- `java.io.tmpdir=/scratch`;
- `spring.servlet.multipart.location=/scratch/multipart`;
- `ApplicationRunner` creates `/scratch/multipart` and probes write access;
- Tomcat can create its temporary base directory under `java.io.tmpdir`.

If cluster volume ownership does not match, the non-root process can hit `AccessDeniedException`. **The real startup probe catches this.** Verify `fsGroup`, SELinux, security admission, and real storage behavior; never resort to `runAsUser=0` or `chmod 777`.

### 12.3. Resource Limits and Eviction

- **`emptyDir.sizeLimit=64Mi`** bounds scratch data on the volume per Kubernetes semantics.
- **`ephemeral-storage` request/limit** accounts for local ephemeral storage under Kubernetes accounting; workloads also consume logs and other storage, so measure the sum.
- When local storage runs low, kubelet can evict the Pod or the app receives **`No space left on device`**.
- Spring Boot readiness/liveness **do not automatically test disk writability on every request**. `ApplicationRunner` only checks at startup; if the disk fills at runtime, add custom health/admission/metrics if required.

**Do not push arbitrary uploads into `emptyDir` assuming `sizeLimit` prevents every OOM/eviction path.** Under concurrent multipart uploads, a 64Mi quota can be exhausted by many simultaneous requests individually under the per-file limit.

### 12.4. Do Not Mount /tmp Out of Habit

In this lab, **`java.io.tmpdir=/scratch`**, so Tomcat and multipart both use the defined scratch mount. Other libraries may hardcode `/tmp`. If testing shows `/tmp` is genuinely needed, either add a dedicated quota-bounded writable mount with tight permissions, or configure the library to use `/scratch`. Never mount host `/tmp` into a Pod, and never make the root filesystem writable just to satisfy an uninvestigated dependency.

## 13. Testing on Kubernetes and Reading Success Signals

Once the cluster and image are ready:

~~~bash
kubectl apply -f k8s.yaml
kubectl rollout status deployment/readonly-runtime-demo
kubectl get pods -l app=readonly-runtime-demo
kubectl get deployment readonly-runtime-demo
~~~

When Pods are READY, port-forward the service in a separate terminal:

~~~bash
kubectl port-forward service/readonly-runtime-demo 8080:80
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i -X POST http://localhost:8080/api/temp/probe

printf 'abc\n' > sample.txt
curl -i -F "file=@sample.txt" http://localhost:8080/api/upload
~~~

**Conditional expectation:** if Kubernetes applies permissions/`fsGroup` and the volume mount properly, readiness returns HTTP 200 and both POSTs succeed. Otherwise, the Pod may hit `CrashLoopBackOff` or fail readiness; check logs/events rather than relaxing permissions.

To inspect UID/GID/volumes inside the Pod:

~~~bash
kubectl exec deployment/readonly-runtime-demo -- id
kubectl exec deployment/readonly-runtime-demo -- ls -ld /app /scratch
kubectl exec deployment/readonly-runtime-demo -- sh -c 'touch /app/blocked'
kubectl exec deployment/readonly-runtime-demo -- sh -c 'touch /scratch/allowed && rm /scratch/allowed'
~~~

**`touch /app/blocked`** must fail on the read-only root filesystem; **`touch /scratch/allowed`** must succeed. A non-zero exit code on the first command is the expected check result. Never use `rm` with wildcards or delete user files; `/scratch/allowed` is a lab-specific test filename.

If the cluster uses a distroless image without `sh`, verify via Java endpoints or an authorized debug workflow. Never weaken production security contexts just to get a shell.

### 13.1. When a Test Pod Hits CrashLoopBackOff

~~~bash
kubectl describe pod -l app=readonly-runtime-demo
kubectl logs deployment/readonly-runtime-demo --previous
kubectl get events --sort-by=.lastTimestamp
~~~

**`kubectl describe pod -l`** depends on kubectl version and matched Pod count; if unsupported, run **`kubectl get pods -l app=readonly-runtime-demo`** to get a Pod name and describe that exact name. **`--previous`** only has logs if the container restarted; otherwise read current logs.

Look for signs:
- `Unable to create tempDir` / `No space left on device`.
- `Permission denied` / `Read-only file system`.
- `ImagePullBackOff` because the image was not loaded/published.
- `runAsNonRoot` admission rejection due to image/runtime user mismatch.
- Mismatch between the `/scratch` mount and `java.io.tmpdir`.
- Startup failure due to other config/port/library issues.

## 14. When Do You Need Write Access to /tmp, /var/tmp, or user.home?

### 14.1. java.io.tmpdir

Java **`Files.createTempFile(prefix, suffix)`** without a parent uses the runtime's default temp directory. In read-only containers, ensure that path is a writable mount. Setting **`-Djava.io.tmpdir`** at launch is explicit.

### 14.2. TMPDIR and Native Subprocesses

A native executable or external tool may read **`TMPDIR`**, **`TMP`**, or its own variable while ignoring `java.io.tmpdir`. When invoking ImageMagick, ffmpeg, headless LibreOffice, or custom tools, check the tool's contract and sandbox its output. Never accept a client-supplied path as a temp directory.

### 14.3. user.home and Caches

Some SDKs write caches into **`user.home/.cache`**, **`~/.config`**, or the current working directory. If `USER 10001` lacks a writable home, either:
- Configure the specific cache directory onto writable scratch.
- Disable disk caching if unneeded.
- Provide a dedicated quota-bounded writable home mount.
- Never grant blanket write access across `/home` or `/app`.

### 14.4. Access Logs, GC Logs, and Heap Dumps

If enabled:
- **`logging.file.name=/app/logs/service.log`** fails when `/app` is read-only. Prefer console logging.
- **`server.tomcat.accesslog.enabled=true`** with default directory may write to Tomcat base/logs; configure a writable path with rotation.
- **`-Xlog:gc:file=/app/gc.log`** needs a writable path; with a read-only root, log GC to stdout or a dedicated mount.
- **`-XX:HeapDumpPath=/app`** fails when generating dumps. Heap dumps can contain secrets/PII; do not enable casually and restrict access strictly.
- External libraries extracting native `.so`/`.dll` files into temp can hit **`noexec`**; verify requirements rather than blindly stripping mount flags.

**A release should not pass QA if it only runs with a writable root filesystem.** Include container integration tests with production-like flags and policies.

## 15. Interpreting Permission Denied, Read-Only Filesystem, and ENOSPC Errors

| Error/symptom | Suspect layer | How to verify |
| --- | --- | --- |
| `Read-only file system` writing `/app` | `readOnlyRootFilesystem` or `ro` mount | Inspect mount flags, `volumeMounts`, and path |
| `AccessDeniedException` `/scratch` | UID/GID/ACL/SELinux or mount flags | `id`, `ls -ld`, `securityContext`, storage driver |
| `No such file or directory` | Parent dir uncreated or volume mount shadowed path | Verify directory exists before request |
| `Unable to create tempDir` at startup | Tomcat/JVM using unwritable temp path | `JAVA_TOOL_OPTIONS`, `java.io.tmpdir`, `basedir` |
| Multipart request returns 500 before Controller | Servlet multipart location lacks permission | `spring.servlet.multipart.location`, temp dir, logs |
| Small uploads succeed, large fail | Disk threshold, size limit, quota | `max-file-size`, `max-request-size`, `sizeLimit` |
| `No space left on device` | `emptyDir`/node disk/PVC/quotas full | `df`/`du`, `ephemeral-storage` metrics/events |
| `OOMKilled` when using tmpfs | Memory-backed `emptyDir` competing with heap/native | Pod memory limit, tmpfs usage |
| `permission denied` after changing image UID | Mount owner/group mismatches new UID | `runAsUser`, `runAsGroup`, `fsGroup` |
| File written to PVC unreadable after restart | Mount path/StorageClass/lifecycle/permissions | PVC binding, access modes, Pod replacement |
| Actuator readiness UP yet upload fails | Startup probe checks only startup or lacks disk health | Test multipart and runtime disk monitoring |
| Container starts as root, rejected by SecurityPolicy | Image `USER`/root mismatch | `runAsNonRoot`, image metadata, admission |
| `chmod 777` still cannot write | Root mount is read-only or SELinux/ACL | Check `ro` mounts before permission mode bits |
| Log file cannot be created | `FileAppender` points into image path | Console logging or writable log volume |
| Native library extraction fails | Temp `noexec` or insufficient permissions | Native tool requirements, explicit path |
| Too many leftover temp files after crash | Cleanup only in `finally`, Pod stayed alive | TTL reaper, startup cleanup, quotas |

### 15.1. Practical Debugging Order

1. Find the **exact path** the process tried to write to; avoid relying solely on generic exception names.
2. Determine whether the path lives on **rootfs** or a **mounted volume**.
3. Inspect process UID/GID and file owner/group/mode; check ACLs/SELinux if applicable.
4. Check `ro`/`rw` mount options, size limits, and free capacity.
5. Verify **`java.io.tmpdir`** was set at launch, not during Spring bean initialization.
6. Verify **`spring.servlet.multipart.location`** and when the directory is created.
7. Check Tomcat base/temp, access log paths, and third-party libraries.
8. Test create/write/delete using the exact same UID inside the container—never use a root debug shell to prove non-root permissions.
9. Add regression tests in Docker/Kubernetes instead of editing manifests by guesswork.

**Never set `chmod -R 777`, `privileged=true`, or `runAsUser=0`** as a default “quick fix”. They hide root causes and break hardening.

## 16. Security Considerations for Temporary File Areas

Temporary files can also hold sensitive data. Apply:
- **Randomized names** via `Files.createTempFile` or exclusive-create mechanisms; avoid paths built from client-supplied filenames.
- **Dedicated directory** with proper owner/group, not world-writable unless needed.
- **Never log paths alongside tokens or file contents**.
- **Quotas** per request/user and per Pod; upload limits prevent disk-exhaustion DoS.
- **Cleanup** after requests plus TTL cleanup for orphans after crashes/restarts.
- **Never follow symlinks** from untrusted input; use NIO APIs/flags appropriate to your threat model when opening security-sensitive files.
- **Never execute** uploaded files; mount scratch **`noexec`** if dependencies allow.
- **Avoid storing plaintext credentials** in temp; keep secrets in Secret managers/protected volumes.
- **Never share scratch across tenants** if the app cannot enforce isolation.
- **Never map broad `hostPath`s** just to get writable space.

**A read-only root filesystem is defense-in-depth**, not a replacement for vulnerability patching, content validation, authorization, network controls, or process capability restrictions.

### 16.1. Symlinks and Path Traversal from Multipart Original Filenames

A client can send a filename like **`../../etc/passwd`** or an absolute path. The lab controller **does not use `originalFilename` to construct a `Path`**, reading only the `InputStream`; that is the safer pattern for the demo.

If an app must keep display names, treat them as **sanitized metadata**, never as raw filesystem paths. Only accept paths inside a dedicated directory, validate canonical paths, and defend against symlink races—or stream directly to object storage under a server-generated key.

### 16.2. When Containers Restart

If a container crashes while the Pod stays alive, `emptyDir` may retain temporary files left by prior requests. Never assume `/scratch` is empty on every process start. Clean up by TTL/known prefixes with restricted permissions, without deleting files belonging to other sidecars. When the Pod is removed from the node, `emptyDir` data disappears, so never rely on it for business persistence.

## 17. Balancing Security, Performance, and Capacity

A small scratch area improves security and limits disk exhaustion, yet too small a mount can break valid uploads. A large scratch area adds headroom but can hide leaks and consume node resources.

Factors to budget:
- **Max multipart file size** and total request size.
- **Concurrent upload count** and how long each file stays on disk.
- **Tomcat/framework overhead** and third-party conversion temp sizes.
- **Replication:** each Pod has its own scratch and limits.
- **Node ephemeral storage** and eviction thresholds.
- **JVM heap/direct memory** if using `medium: Memory`.
- **Cleanup duration** when clients disconnect mid-upload.
- **Upload cancellation, backpressure, and HTTP body size limits** at Ingress.

For example, **10 concurrent uploads × 1 MiB** before counting multipart overhead, Tomcat scratch, and intermediate files can easily exceed 10 MiB. Setting `emptyDir` `sizeLimit: 64Mi` does not allow unlimited concurrent uploads if conversion workloads also share the volume.

### 17.1. Readiness and Disk Health

A startup write probe catches a volume locked from the beginning, yet hours later the volume can fill up. Production can:
- Monitor ephemeral storage usage percentage and free space.
- Implement custom `HealthIndicator`/Readiness logic if essential storage is lost.
- Apply load shedding on upload endpoints when capacity runs low.
- Reap orphan files and rotate logs.
- Never use liveness failure to address shared node disk pressure: mass restarts can worsen the problem.

Readiness reflects ability to accept traffic; liveness reflects whether the process needs a restart. Design around failure domains so one shared storage issue does not restart every replica simultaneously.

## 18. Comparing Docker --read-only and Kubernetes readOnlyRootFilesystem

| Aspect | Local Docker | Kubernetes |
| --- | --- | --- |
| Read-only root FS | `docker run --read-only` | `container.securityContext.readOnlyRootFilesystem=true` |
| Runtime UID/GID | Dockerfile `USER` or `docker run --user` | `runAsUser`/`runAsGroup`/`runAsNonRoot` |
| Writable temp | `--tmpfs /scratch` or named volume | `emptyDir`/PVC `volumeMount` |
| Volume group permissions | `--tmpfs` `uid`/`gid`/`mode`, bind mount owner | `fsGroup`, storage/CSI ownership rules |
| Storage limit | `tmpfs` `size` option / Docker volume driver | `emptyDir.sizeLimit` and `ephemeral-storage` limits |
| Process hardening | `cap-drop`, `security-opt`, `no-new-privileges` | `allowPrivilegeEscalation=false`, `capabilities.drop`, `seccompProfile` |
| Signal/shutdown | `docker stop` | kubelet termination/`SIGTERM` |
| Pod-level readiness | Docker `HEALTHCHECK` if configured | Kubernetes readiness/liveness probes |
| Data after container restart | `tmpfs`/ephemeral per container lifecycle | `emptyDir` persists within Pod, lost when Pod is removed |

Test **the exact same JAR/image artifact** under production-like security settings. Host Java tests do not prove non-root + read-only mounts. Docker tests alone do not prove `fsGroup`/CSI/Kubernetes security policies. Each layer must be tested individually and together.

## 19. Self-Check Exercises

**1.** Can a container with `readOnlyRootFilesystem=true` write to an `emptyDir` mounted at `/scratch`?  
**Answer:** Yes, provided the volume mount is writable and UID/GID/permissions/storage policies allow it.

**2.** Does `runAsNonRoot=true` make the root filesystem read-only?  
**Answer:** No. That controls process UID; read-only rootfs requires a separate setting.

**3.** Why can an app that writes no business files still fail when `/tmp` is read-only?  
**Answer:** Tomcat base/temp and Servlet multipart/file-upload libraries may require scratch disk.

**4.** When should `java.io.tmpdir` be set?  
**Answer:** At JVM startup via `-Djava.io.tmpdir` or `JAVA_TOOL_OPTIONS`, not mid-request expecting all libraries to re-read it.

**5.** What is the default for Spring Boot 3.3 `spring.servlet.multipart.file-size-threshold`?  
**Answer:** `0B`, allowing uploaded content to spool to disk per the Servlet implementation.

**6.** Which property configures Spring's intermediate multipart directory?  
**Answer:** `spring.servlet.multipart.location`.

**7.** If you set `app.temp-dir=/scratch` but omit `multipart.location`, are uploads guaranteed to use `/scratch`?  
**Answer:** No. `app.temp-dir` is a custom lab property while the Multipart resolver has its own config; `java.io.tmpdir` can influence defaults, so be explicit.

**8.** Why is `Files.isWritable` insufficient to prove a temp mount works?  
**Answer:** It does not verify quotas, free space, mounts, or ACLs at actual write time; creating/writing/deleting a real file is more reliable.

**9.** Does `emptyDir` survive a container crash/restart in the same Pod?  
**Answer:** Yes, `emptyDir` data persists for the Pod's lifetime; it is lost when the Pod is removed from the node.

**10.** Does `emptyDir` `medium: Memory` count against memory usage?  
**Answer:** Yes, tmpfs data competes against the memory limit and can trigger OOM.

**11.** Does `fsGroup=10001` guarantee every PVC across every CSI driver is writable?  
**Answer:** No; it depends on the storage driver, ownership behavior, mount flags, ACLs, and SELinux.

**12.** Why use UID 10001 instead of root in the Dockerfile?  
**Answer:** Reduces default privileges if the process is exploited; volume permissions and additional security layers are still needed.

**13.** Can running as root bypass a read-only mount?  
**Answer:** No; a read-only mount does not become writable for UID 0.

**14.** Should you run `chmod 777` across `/app` to solve upload errors?  
**Answer:** No; identify the exact scratch path and attach a minimal writable mount.

**15.** Why never use `MultipartFile.getOriginalFilename` as a `Path` without validation?  
**Answer:** The filename is client-controlled and can lead to path traversal or file overwrites.

**16.** Why might an upload succeed in Docker yet fail in Kubernetes?  
**Answer:** `fsGroup`/`runAsUser` mismatch, PVC/`emptyDir` mount permissions, SELinux, image policies, or different temp paths.

**17.** What happens if `/scratch` fills up after the app is already ready?  
**Answer:** Uploads/temp writes fail; the startup probe does not keep checking continuously, requiring metrics/quotas/runtime health checks.

**18.** When should you use a PVC or object storage instead of `emptyDir`?  
**Answer:** When files are business data that must survive Pod deletion/redeployment or be shared under a durability contract.

**19.** Is `noexec` on tmpfs always compatible with every Java app?  
**Answer:** No. Some native libraries extract/execute into temp; verify real dependencies before keeping or removing `noexec`.

**20.** Why shouldn't host JUnit tests count as proof that `readOnlyRootFilesystem` works?  
**Answer:** Host tests do not mount the container root read-only or enforce Linux UID/`fsGroup` like the real runtime; Docker/Kubernetes tests are required.

## 20. Production Deployment Checklist

- [ ] Image contains readable JAR/config without needing writes to `/app`.
- [ ] Runtime process runs under a defined non-root UID/GID or supported random-UID policy.
- [ ] Enabled **`readOnlyRootFilesystem`** in Kubernetes and Docker equivalent in tests.
- [ ] Dropped unneeded Linux capabilities; disabled privilege escalation; applied appropriate seccomp profile.
- [ ] No `privileged`, broad `hostPath`, or `chmod 777` permission workarounds.
- [ ] Dedicated writable scratch mount with quotas configured.
- [ ] **`java.io.tmpdir` set at JVM start**, not mid-lifecycle.
- [ ] **`spring.servlet.multipart.location`** configured with request/file size limits.
- [ ] Checked Tomcat base/temp/workdir, access logs, native libs, heap dumps, and caches.
- [ ] Startup performs a write/delete probe on essential temp directories.
- [ ] Runtime temp storage failures have metrics, graceful errors, and appropriate readiness/admission policies.
- [ ] Clearly separated **ephemeral `emptyDir`** from **durable PVC/object storage**.
- [ ] For memory `emptyDir`, implemented memory accounting/quotas and OOM testing.
- [ ] For disk `emptyDir`, set `ephemeral-storage` requests/limits and monitored eviction/`ENOSPC`.
- [ ] Verified `runAsUser`/`runAsGroup`/`fsGroup` and volume permissions under the real process UID.
- [ ] Never echo sensitive filenames/paths/temp contents in public APIs or logs.
- [ ] Used `Files.createTempFile` with `finally` cleanup plus TTL cleanup for crashes.
- [ ] Tested multipart over real HTTP container stacks, not direct controller calls alone.
- [ ] Included Docker integration tests with **`--read-only` + `--tmpfs`**.
- [ ] Included staging Kubernetes tests with **`readOnlyRootFilesystem` + `emptyDir` + `fsGroup`**.
- [ ] Tested failure modes for missing/RO/full mounts alongside readiness and logs.
- [ ] Enforced upload protections: authentication, rate limiting, validation, and content scanning where needed.
- [ ] Lab debug/probe endpoints and sensitive Actuator endpoints are not exposed publicly.

## 21. Conclusion

**A read-only root filesystem, non-root process, and writable temporary volume are not mutually exclusive.** They are three complementary layers of responsibility:
- **Read-only rootfs** protects image contents and restricts where the process can modify state.
- **Non-root UID/GID** limits the JVM's privileges.
- **Quota-bounded writable scratch mount** supplies the intermediate space genuinely needed by Tomcat, multipart, the JDK, and libraries.

A solid design aligns **`java.io.tmpdir`**, **`spring.servlet.multipart.location`**, mount paths, `fsGroup`, and quotas, then **verifies them with real write/delete operations under the deployed UID**. Business data requiring durability must go to PVCs, object storage, or databases; `emptyDir` is strictly scratch. Never treat `Permission denied` as an excuse to drop read-only filesystems, run as root, or open system-wide permissions.

## Official References

- Spring Boot 3.3 — Common Application Properties, `spring.servlet.multipart.*`, and `server.tomcat.basedir`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring MVC Multipart support and uploads: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Apache Tomcat 10.1 — Context `workDir` and `jakarta.servlet.context.tempdir`: https://tomcat.apache.org/tomcat-10.1-doc/config/context.html
- Oracle Java 17 — `Files.createTempFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Kubernetes — Configure a Security Context for a Pod or Container: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes — Volumes, `emptyDir` lifecycle, and `medium: Memory`: https://kubernetes.io/docs/concepts/storage/volumes/
- Kubernetes — Resource Management, ephemeral storage, and tmpfs accounting: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- Kubernetes — Configure a Pod to Use a Volume: https://kubernetes.io/docs/tasks/configure-pod-container/configure-volume-storage/
- Docker — Run containers, `USER`, and `--read-only` rootfs: https://docs.docker.com/reference/cli/docker/container/run/
- Docker — tmpfs mounts, `uid`/`gid`/`mode`/`size`: https://docs.docker.com/engine/storage/tmpfs/
- Docker — Dockerfile `USER`, `COPY --chown`, and `ENTRYPOINT`: https://docs.docker.com/reference/dockerfile/