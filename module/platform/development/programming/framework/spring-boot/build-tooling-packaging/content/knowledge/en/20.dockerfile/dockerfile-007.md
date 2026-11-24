# Configuring WORKDIR, File Ownership, and a Non-Root User

A Dockerfile for a Spring Boot application needs to do more than `COPY app.jar` followed by `java -jar app.jar`. An image can build cleanly yet fail to start a container because it cannot read the JAR, cannot write temporary files, or runs as `root` even though the application actually needs no privileges. Three directly related instructions/concepts apply:

1. **`WORKDIR`** sets the working directory inside the image/container for subsequent instructions. It **does not automatically grant** write permissions to the process.
2. **Owner, group, and permissions** determine which UID/GID can read, write, or traverse a directory. `COPY --chown` and `COPY --chmod` let you declare these permissions right when building the image.
3. **`USER`** sets the default account/UID/GID for subsequent `RUN` instructions in the same stage and for the container process running `ENTRYPOINT`/`CMD`. For typical web applications, use **non-root** and grant least privilege.

This lesson uses **Java 17, Spring Boot 3.3.13, Maven 3.9.x**, the Eclipse Temurin Ubuntu/JRE runtime image, and Docker Engine with a BuildKit/Dockerfile frontend supporting `COPY --chown` and `--chmod`. Versions are pinned for this learning example; before production, select an organization-approved image tag/digest, patch CVEs, and test compatibility. All `docker` commands illustrate usage on a machine with Docker installed and authorized; they were not executed during writing.

## 1. Permission and Role Diagram in a Spring Boot Container

We use this filesystem layout:

```text
Runtime image
/
├── opt/
│   └── app/                       WORKDIR
│       └── app.jar                mode 0444, owner 10001:10001
├── var/
│   └── app-data/                  mode 0750, owner 10001:10001
├── tmp/                           JVM/Tomcat temp; needs a mount if root FS is read-only
└── usr/lib/jvm/...                Java runtime from base image

Container process:
  UID = 10001
  GID = 10001
  command = java -jar /opt/app/app.jar
  HTTP port = 8080
```

**Intentional design:**

- `/opt/app` holds only the program. This directory is root-owned and non-writable by the app user, yet must allow **directory traversal** (`x`) and reading the JAR file.
- `/opt/app/app.jar` is owned by UID/GID `10001:10001` with mode `0444` (read-only). Even the owner **does not** automatically have write access because the mode omits `w`.
- `/var/app-data` is a **writable area** for tasks needing persistent or temporary data storage (if any). Mode `0750` and owner `10001:10001` restrict access by others.
- `/tmp` suits certain Java/Spring Boot temp files, yet when enabling a **read-only root filesystem** you must provide a suitable tmpfs/volume. Where the application needs to write must be verified in practice.
- `USER 10001:10001` prevents the application process from running as container root by default. This is **privilege reduction**, not a replacement for seccomp, capabilities, network isolation, secret protection, or dependency updates.

**Final goal:** A Spring Boot executable JAR running cleanly as non-root; able to verify UID, GID, file permissions, working directory, endpoint, and writable paths. Never use `chmod -R 777` or switch to `USER root` to paper over permission errors.

## 2. What Does `WORKDIR` Actually Do?

Per the Dockerfile reference, `WORKDIR /path` sets the working directory for **subsequent** `RUN`, `CMD`, `ENTRYPOINT`, `COPY`, and `ADD` instructions. If the directory does not yet exist, Docker creates it; that **does not guarantee** a different user later will have permission to write to it.

Example:

```dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /opt/app
COPY app.jar ./app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
```

With `WORKDIR /opt/app`:

- `COPY app.jar ./app.jar` places the file at `/opt/app/app.jar`.
- When the container starts, the process has current working directory `/opt/app`.
- `java -jar app.jar` uses a relative path from `/opt/app`.
- If an orchestrator or `docker run -w /another/path` changes the working directory, the relative path `app.jar` may break.
- A more resilient entrypoint is `["java", "-jar", "/opt/app/app.jar"]` — an absolute path independent of `pwd`.

**Use absolute paths for `WORKDIR` and runtime artifacts.** Avoid guessing the base image's default working directory; if a Dockerfile omits `WORKDIR`, the default is usually `/`, though a base image may have set a different `WORKDIR`.

### 2.1. Consecutive `WORKDIR` Instructions Chain Relative Paths

```dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /srv
WORKDIR app
WORKDIR logs
RUN pwd
```

In this stage, `pwd` at `RUN` outputs:

```text
/srv/app/logs
```

Because `WORKDIR app` and `WORKDIR logs` are **relative** to the previous `WORKDIR`. This easily causes files to be copied somewhere unexpected; use `WORKDIR /opt/app` consistently to avoid confusion.

### 2.2. `WORKDIR` Does Not Replace `USER` or `chown`

These two Dockerfiles **differ in permissions**:

```dockerfile
# Only selects the directory; does not guarantee user 10001 can write.
WORKDIR /opt/app
USER 10001:10001
```

and:

```dockerfile
# Explicitly sets permissions on the data directory.
RUN mkdir -p /var/app-data \
    && chown 10001:10001 /var/app-data \
    && chmod 0750 /var/app-data
WORKDIR /opt/app
USER 10001:10001
```

The second snippet is a **fragment**: it needs a suitable base image and user/group to be complete. `/var/app-data` is prepared **before** dropping privileges; `WORKDIR` only controls relative execution location, without changing permission bits.

## 3. Understanding UID, GID, Owner, Group, and Three Linux Permissions

On Linux, a file/directory typically has:

- **UID owner:** numeric user ID of the owner.
- **GID group:** numeric group ID of the owning group.
- **Mode bits:** `r` (read), `w` (write), `x` (execute/search) for owner, group, and others.
- **Other mechanisms:** ACLs, SELinux/AppArmor labels, mount flags, capabilities, and user namespaces can make actual access differ from `ls -l` alone.

Example:

```text
-r--r--r--  1 10001 10001  ... /opt/app/app.jar
drwxr-xr-x  2     0     0  ... /opt/app
drwxr-x---  2 10001 10001  ... /var/app-data
```

The lines with numeric UID/GID above are **illustrative output matching the lesson layout**, not output from a live command. Interpretation:

| Path | Mode | UID:GID | What Can User 10001 Do? |
| --- | --- | --- | --- |
| `/opt/app` | `0755` | `0:0` | Can traverse, list/read names; **cannot write/add files** |
| `/opt/app/app.jar` | `0444` | `10001:10001` | Read the JAR, **cannot modify the JAR** |
| `/var/app-data` | `0750` | `10001:10001` | Read/write/create files, traverse directory |
| `/etc/shadow` in base image | Usually tightly restricted | `0:0` | Non-root has no read permission |

### Directory `x` Is Not File `x`

For a directory, `x` is **search/traverse** permission. Even if `app.jar` is readable, if a parent directory lacks traverse permission, the process still cannot open the file.

For instance, setting only:

```bash
chmod 0644 /opt/app
```

on a **directory** removes traverse permission and causes accessing files inside to fail. That is a **broken** configuration, not a recommendation. For a JAR directory, `0755` (root-owned) is a sensible convention when read/traverse access is needed; for a dedicated writable directory, `0750` (app-owned) narrows access.

**Least-privilege principle:** grant write access only where genuinely required. Never grant `w` on code/config that should not change at runtime.

## 4. `USER`: Drops Process Privileges, Does Not Re-Own Existing Files

`USER appuser` or `USER 10001:10001` sets the default identity for subsequent `RUN` instructions in that stage and for the final stage's runtime `ENTRYPOINT`/`CMD`.

Example:

```dockerfile
FROM eclipse-temurin:17-jre-jammy

RUN groupadd --gid 10001 appgroup \
    && useradd --no-log-init --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin appuser

USER 10001:10001
ENTRYPOINT ["java", "-version"]
```

- `groupadd` and `useradd` are Linux user/group tools in the Ubuntu example base image. On Alpine, UBI minimal, distroless, or scratch, syntax/tools may differ or **not exist**.
- `--no-log-init` is a Debian/Ubuntu `useradd` option that avoids updating sparse log files for large UIDs, per Docker best practices.
- `--uid`/`--gid` fix numeric IDs to work cleanly with files, Kubernetes `runAsUser`, and volumes.
- `/usr/sbin/nologin` prevents interactive login shells; the container can still launch `java` via exec-form `ENTRYPOINT`. It **does not by itself strengthen the sandbox** or block other ways of launching a process.
- `USER` does not `chown` existing files. If `app.jar` is root-owned with mode `0600`, `USER 10001` will not make it readable.
- Multi-stage Dockerfiles: `USER` in the **build stage** does not automatically set the user of the **runtime stage**. You must set `USER` in the final image stage.

### Named User or Numeric UID?

`USER appuser` is friendly to human readers, yet requires that account to exist in the image. `USER 10001:10001` is easy for orchestrators to validate and stays consistent across volume mounts. Some hardened base images lack `/etc/passwd` entries; the JVM or third-party libraries occasionally look up a home directory or username. Because our example creates a real account, `10001` still resolves to `appuser` when running `id`.

**Never assume UID 10001 is valid in every organization**: confirm it does not collide with reserved base-image UIDs, OpenShift/Kubernetes random-UID policies, bind mounts, or host user mappings. If the runtime enforces a random non-root UID, design **group/others read permissions** and compatible writable volumes instead of hardcoding ownership everywhere.

## 5. `COPY --chown` and `COPY --chmod`: Ownership Differs from Permissions

Per the Dockerfile reference, on Linux:

```dockerfile
COPY --chown=10001:10001 --chmod=0444 app.jar /opt/app/app.jar
```

Has two independent effects:

- `--chown=10001:10001`: sets the owner UID/GID of the **newly copied file**.
- `--chmod=0444`: sets **read-only mode for owner/group/others**; no `w` bit.
- Without `--chown`, Docker `COPY` normally creates files owned by `0:0` (root), even if you intend to run the app as non-root later.
- `COPY --chown=appuser:appgroup` uses names, requiring the account/group to exist in the stage filesystem at `COPY` time; numeric IDs need no name lookup.
- `COPY --chmod` requires Dockerfile frontend/build tooling support; our examples use `# syntax=docker/dockerfile:1` with modern BuildKit.

Separate examples:

```dockerfile
# Case A: app-readable yet root-owned.
COPY --chmod=0444 app.jar /opt/app/app.jar

# Case B: app UID/GID owns file, mode remains read-only.
COPY --chown=10001:10001 --chmod=0444 app.jar /opt/app/app.jar

# Case C: shown solely as a configuration NOT to use.
# RUN chmod -R 777 /opt/app
```

**Case A is not wrong by default** if the JAR is read-only and the directory allows traversal. Not every app file must be owned by the non-root user. Many setups are safer when **the JAR/config is root-owned yet readable**, because the non-root process cannot modify them itself. Case B illustrates `--chown`, while mode `0444` still prevents the user from writing to the file under standard POSIX permissions.

### Why Is `COPY --chown` Better Than Running `chown -R` After `COPY`?

For large file sets, setting ownership directly in `COPY` is cleaner and avoids adding a separate layer modifying metadata across an entire directory tree. `RUN chown -R /opt/app` can increase build/layer overhead and accidentally broaden write permissions. Only `chown` specific **data directories** that need writes; never blanket-`chown` the entire root filesystem.

### Context Is Linux Containers

`COPY --chown` and `--chmod` per Dockerfile reference target Linux containers and do not apply identically to Windows containers. Permissions like `0750`, `uid/gid`, and `useradd` also follow Linux semantics. Do not copy them verbatim onto a Windows Server Core container and expect them to work.

## 6. Complete Java 17 Spring Boot Example

A simple REST endpoint returning `Hello non-root`. The application **never needs to write any file into `/opt/app`**, keeping permissions clear. Subsequent Docker commands verify JAR readability, the writable data path, and the executing user.

Maven project structure:

```text
ownership-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
└── src/
    ├── main/java/dev/example/ownership/
    │   ├── OwnershipDemoApplication.java
    │   └── HelloController.java
    └── test/java/dev/example/ownership/
        └── HelloControllerTest.java
```

### 6.1. Complete `pom.xml`

```xml
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

    <groupId>dev.example</groupId>
    <artifactId>ownership-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
```

The starter parent manages dependency/plugin versions and `repackage` execution when `spring-boot-maven-plugin` is declared. After `mvn clean verify`, `target/ownership-demo-1.0.0.jar` is the **Spring Boot executable JAR**, containing the loader, `BOOT-INF/classes`, and `BOOT-INF/lib`. The Dockerfile copies **this exact file**, not `.jar.original` or a plain JAR missing runtime libraries.

### 6.2. Main class

`src/main/java/dev/example/ownership/OwnershipDemoApplication.java`:

```java
package dev.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipDemoApplication.class, args);
    }
}
```

### 6.3. REST controller

`src/main/java/dev/example/ownership/HelloController.java`:

```java
package dev.example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello non-root";
    }
}
```

### 6.4. Unit/web test

`src/test/java/dev/example/ownership/HelloControllerTest.java`:

```java
package dev.example.ownership;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void helloWorks() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello non-root"));
    }
}
```

This test verifies the Spring context and endpoint when Maven runs tests; **it does not verify that the image has the right `USER`**. You must build the Dockerfile, inspect `id`/permissions, and smoke-test the container separately.

## 7. Standard Multi-Stage Dockerfile: Maven Build with JDK, Run with Non-Root JRE

Below is the complete Dockerfile for the source from Section 6.

`Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: build + test; do not carry Maven/JDK build tools into runtime image.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src

COPY pom.xml ./
COPY src ./src
RUN mvn -B -ntp clean verify

# Stage 2: minimal runtime with JRE 17, without inheriting build stage user.
FROM eclipse-temurin:17-jre-jammy

# Perform setup as root at build time.
RUN groupadd --gid 10001 appgroup \
    && useradd --no-log-init --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin appuser \
    && mkdir -p /opt/app /var/app-data \
    && chmod 0755 /opt/app \
    && chown 10001:10001 /var/app-data \
    && chmod 0750 /var/app-data

WORKDIR /opt/app

# JAR readable yet non-modifiable at runtime.
COPY --from=build --chown=10001:10001 --chmod=0444 \
    /src/target/ownership-demo-1.0.0.jar /opt/app/app.jar

# Main process runs with regular UID/GID, not root.
USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

**Step-by-step analysis:**

1. `FROM maven:3.9-eclipse-temurin-17 AS build` provides Maven/JDK for building. The tag is illustrative; production can pin a digest and record a BOM/SBOM.
2. `WORKDIR /src` ensures `pom.xml` and `src/` are copied to the right location for Maven.
3. `RUN mvn -B -ntp clean verify` compiles, tests, and packages inside the **builder**. Do not add `-DskipTests` when this is a required QA build.
4. `FROM eclipse-temurin:17-jre-jammy` opens a **new stage** with only the Java 17 runtime on Ubuntu; build tools and source do not appear in the final image.
5. `groupadd`/`useradd` create a Linux group/account with UID/GID `10001`. Setup commands require root at **build time**, which does not mean the app must run as root at runtime.
6. `mkdir -p /opt/app /var/app-data` creates directories. `/opt/app` stays root-owned with mode `0755` so the app can **read/traverse without writing**.
7. `chown 10001:10001 /var/app-data && chmod 0750 /var/app-data` grants write access only to the data folder that needs it.
8. `WORKDIR /opt/app` sets the process's working directory. `ENTRYPOINT` still uses an absolute path to avoid failing if orchestration overrides the working directory.
9. `COPY --from=build ... --chown=10001:10001 --chmod=0444` transfers **only the executable JAR** from builder to runtime, omitting source and the rest of `target`. The app user can read the file, with no write bit.
10. `USER 10001:10001` sets the default runtime identity. Both numbers should be verified against the owners of writable volumes/directories.
11. `EXPOSE 8080` is merely **metadata declaring the expected listening port**. It does not publish the port to the host; host access requires `docker run -p ...` or appropriate container networking/orchestration.
12. Exec-form `ENTRYPOINT ["java", "-jar", ...]` avoids wrapping the app in `sh -c`, making the JVM the main process with more direct signal and exit-code handling.

**Helpful tip:** Placing `USER` near the end of the runtime stage is a clear convention. Putting `USER 10001` before `RUN groupadd/useradd/chown` will fail setup commands with `Operation not permitted`. If using `COPY --chown=appuser:appgroup` by name, the user/group must already exist before `COPY` in that stage. This lesson uses numeric IDs to avoid lookup ambiguity.

## 8. `.dockerignore` and Build Context

File `.dockerignore` in the sample project:

```dockerignore
.git
target/
build/
.gradle/
.idea/
*.log
*.iml
.env
```

Section 7's multi-stage Dockerfile needs only `pom.xml` and `src/` from the build context, so ignoring host `target/` is **sensible**: the image does not depend on stale artifacts left on a developer's machine. `.env` exemplifies environment data that must stay out of the image build context.

From the directory containing `pom.xml`, `Dockerfile`, and `src`, run:

```bash
docker build --pull -t ownership-demo:local .
```

- The trailing `.` is the **build context root**, not a flag pointing at the current Dockerfile.
- `--pull` requests checking for a newer base image on the chosen tag, yet **does not guarantee provenance/immutability**. In production CI, pin digests and run image scanning per policy.
- Docker build executes Maven tests in the builder stage. If tests fail, the image build fails rather than producing a false "green" release image.
- If a repository depends on code generators or files outside `src` and `pom.xml`, the Dockerfile must copy those inputs too. The example is intentionally minimal.

**Never run `COPY . .` unconditionally** in a runtime stage: it can sweep in `.git`, build outputs, env files, credentials, or unneeded source. Copy only the exact executable JAR and approved runtime resources.

## 9. Verifying the Image and User/Permissions with Docker

After building cleanly, you can inspect the image **without starting the web server** by overriding the entrypoint to `sh` (the illustrative Ubuntu image includes a shell).

### 9.1. Inspecting Image Config

```bash
docker image inspect --format '{{.Config.User}}' ownership-demo:local
docker image inspect --format '{{.Config.WorkingDir}}' ownership-demo:local
```

With the sample Dockerfile, the two expected lines are:

```text
10001:10001
/opt/app
```

This is a **metadata check**; it does not prove every directory was `chmod`-ed properly. Pair it with real runtime checks.

### 9.2. Checking the Real Identity When the Container Runs

```bash
docker run --rm --entrypoint sh ownership-demo:local -c 'id; pwd'
```

Typical output (`id` formatting varies by implementation):

```text
uid=10001(appuser) gid=10001(appgroup) groups=10001(appgroup)
/opt/app
```

- `--entrypoint sh` is strictly for **image testing**, replacing `ENTRYPOINT java` for this single run.
- The image's `USER` still applies because we did **not** pass `--user 0`.
- `pwd` confirms `WORKDIR` is `/opt/app`.
- You do not need `sudo` installed in the image to check permissions.

### 9.3. Checking Owner/Mode with Numeric `stat`

```bash
docker run --rm --entrypoint sh ownership-demo:local \
  -c 'stat -c "%u:%g %a %n" /opt/app /opt/app/app.jar /var/app-data'
```

Expected output matching the Dockerfile:

```text
0:0 755 /opt/app
10001:10001 444 /opt/app/app.jar
10001:10001 750 /var/app-data
```

Numeric modes printed by `stat` typically omit the leading zero. The Dockerfile uses `0444`/`0750`, whereas `stat -c %a` prints `444`/`750`.

### 9.4. Testing Real Process Permissions

```bash
docker run --rm --entrypoint sh ownership-demo:local \
  -c 'test -r /opt/app/app.jar && \
      test ! -w /opt/app/app.jar && \
      test ! -w /opt/app && \
      test -w /var/app-data && \
      echo "PASS: least-privilege file permissions"'
```

When matching Section 7's layout, output:

```text
PASS: least-privilege file permissions
```

Why does `test -w` matter? Because rather than just reading mode/owner metadata, you ask the actual container user to perform real access checks. On filesystems with ACLs, user namespaces, or special mount policies, observed runtime behavior is what counts.

**Never run permission checks with `docker run --user 0`**, because root bypasses many DAC checks, rendering non-root verification meaningless.

## 10. Running Spring Boot and Smoke-Testing the Endpoint

Start the container (Linux/macOS/Windows PowerShell, Docker CLI is the same):

```bash
docker run --rm --name ownership-demo \
  -p 127.0.0.1:8080:8080 \
  ownership-demo:local
```

**OS note:** Multi-line commands with `\` use Bash syntax. In PowerShell, use a **single line**:

```powershell
docker run --rm --name ownership-demo -p 127.0.0.1:8080:8080 ownership-demo:local
```

- `-p 127.0.0.1:8080:8080` publishes port 8080 only on the **Docker host loopback** for local testing. It avoids exposing it on all interfaces as `-p 8080:8080` typically does.
- Spring Boot's embedded server defaults to `server.port=8080` when unconfigured; the sample app exposes `/hello`.
- Container startup launches Java under the default `USER 10001:10001`. Port 8080 is an unprivileged port on standard Linux, so root is not needed to bind it.

In a **second terminal**, after logs report the app has started:

```bash
curl -fsS http://127.0.0.1:8080/hello
```

Expected HTTP body:

```text
Hello non-root
```

If the process fails to start, inspect logs; do not switch to `USER root` before checking permissions. If a container named `ownership-demo` is already running, Docker reports a name conflict; stop the old container or pick another name. `--rm` deletes the container when it exits, without deleting the image.

## 11. Image File Permissions Differ from Bind Mount and Volume Permissions

This is the single most common snag when adopting non-root. Suppose the image already has:

```text
/var/app-data -> owner 10001:10001, mode 0750
```

Then an operator bind-mounts a host directory onto that exact path:

```bash
docker run --rm \
  --mount type=bind,src=/srv/ownership-demo-data,dst=/var/app-data \
  ownership-demo:local
```

**This is an illustrative fragment for a Linux host that actually has `/srv/ownership-demo-data`.** It is not portable verbatim across all machines. On a bind mount, the mount's contents and permissions **shadow** the corresponding image directory. Running `chown` on the image directory at build time **does not change the host directory's ownership**.

Consequences:

- If the host directory is writable only by root, process UID 10001 hits `Permission denied`.
- If the Docker daemon uses user-namespace remapping or a rootless engine, numeric host UID/GID seen from inside the container may be mapped; do not mechanically equate all host and container UIDs.
- If Docker Desktop shares a filesystem from Windows/macOS, permission semantics can differ from native Linux; test inside the actual container.
- If a mount overlays `/opt/app`, it can **hide `app.jar`** copied into the image; `java -jar /opt/app/app.jar` will then report file not found.

### Handling Writable Mounts Properly

1. Check the container process UID/GID using `id`.
2. Inspect file/directory permissions at the exact **mount path** using `stat`/`ls -ldn` and test `test -w` or a safe write.
3. For native Linux bind mounts, prepare host directory ownership/ACLs **via proper host administration** matching UID/GID/namespace mapping. Do not default to `chmod 777`.
4. With Docker named volumes, note that Docker volumes have their own lifecycle and initialization rules; inspect actual ownership after mounting rather than assuming image `chown` always wins.
5. With Kubernetes PVCs, check the StorageClass/CSI driver, `fsGroup` support, and pod security policies; avoid running `chown -R` over huge volumes on every app startup.
6. If the app does not genuinely need persistent writes, **do not attach a writable volume just for convenience**.

### Do Not Have the App `chown` Itself at Startup

A non-root process normally **lacks privileges to change ownership** of arbitrary files. Writing a root init script that runs `chown -R` and drops privileges can expand attack surface and slow startup, especially on volumes with many files. If a privileged init container or provisioning step is required, it must be an audited, tightly scoped operational design with explicit ownership rules.

## 12. `readOnlyRootFilesystem` and `/tmp` with Spring Boot

Alongside `USER`, the runtime can enforce a read-only root filesystem:

```bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 \
  -p 127.0.0.1:8080:8080 \
  ownership-demo:local
```

Conditions:

- The sample image does not write to `/opt/app` and application code has no persistent write requirements.
- `--read-only` makes the container's root filesystem layer read-only; it **does not prohibit** separate writable mounts or tmpfs.
- `--tmpfs /tmp:...` provides scratch write space at `/tmp`. Spring Boot, Tomcat, the JVM, or libraries may need temp files at startup; 64 MiB is a **learning value** and should be tuned/measured for real workloads.
- `mode=1777` lets users share the temp directory with the sticky bit set, matching standard `/tmp`.
- In this mode, `/var/app-data` on the root filesystem **is no longer writable**, even if the image ran `chown` for UID 10001. If the app needs to write data, mount a dedicated writable volume/tmpfs **and** verify ownership after mounting.
- If the runtime must write heap dumps, GC log files, uploaded files, or an embedded DB elsewhere, route those paths to authorized volumes or revise the workload design.

An additional verification command:

```bash
docker run --rm --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 \
  --entrypoint sh ownership-demo:local \
  -c 'test -w /tmp && test ! -w /opt/app && echo "PASS: read-only root with writable tmp"'
```

If mounts and permissions are right, output:

```text
PASS: read-only root with writable tmp
```

**Caution:** never treat `--read-only` as a "permission fix trick" to make an app work. It is a stricter constraint that often exposes unmodeled write paths. Apps needing database files or persistent uploads must use proper volumes with managed lifecycles.

## 13. Kubernetes: `runAsNonRoot`, `runAsUser`, `runAsGroup`, and `fsGroup`

In Kubernetes, the Dockerfile image is not the sole source of permissions. A Pod `securityContext` can override runtime identity, and volume permissions depend on the CSI/storage backend. Example fragment for a container already pushed/loaded into a cluster:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ownership-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ownership-demo
  template:
    metadata:
      labels:
        app: ownership-demo
    spec:
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: ownership-demo:local
          imagePullPolicy: Never
          ports:
            - containerPort: 8080
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
```

**This is a local-cluster example**: `imagePullPolicy: Never` requires `ownership-demo:local` to already be loaded on **the exact node** scheduling the Pod (e.g., kind/minikube image load workflows). If the image is absent from the node, the Pod will fail to start; that is not a `USER` error. In production, pull images from a controlled registry, pin digests, and set an appropriate pull policy.

Explanation:

- `runAsUser: 10001`: sets the process UID.
- `runAsGroup: 10001`: sets the primary GID. Never omit this and silently assume the process is not in the root group.
- `runAsNonRoot: true`: kubelet refuses to run containers as UID 0; it is a guardrail, not something that grants permissions on mounted files.
- `allowPrivilegeEscalation: false`: restricts privilege escalation via kernel/runtime mechanisms; does not replace `runAsNonRoot`.
- `capabilities.drop: ["ALL"]`: drops default Linux capabilities, fitting a service that only needs HTTP 8080. Workloads needing specific capabilities must be narrowly analyzed rather than blindly adding `SYS_ADMIN`.
- `readOnlyRootFilesystem: true`: makes the root layer read-only; `emptyDir` at `/tmp` supplies scratch space. **Actual owner/mode of `emptyDir` should still be verified**, especially under random UIDs or custom security policies.
- `seccompProfile.type: RuntimeDefault`: enables the container runtime's default seccomp profile when supported.
- `fsGroup` (omitted here since no PVC is mounted) can help manage permissions on certain volumes, though behavior depends on volume type, CSI driver, and `fsGroupChangePolicy`. **Never** treat it as a universal `chown` for every mount.

### `fsGroup` and Writable PVCs

When a persistent volume is needed, Pod-level security context may include:

```yaml
securityContext:
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  fsGroupChangePolicy: OnRootMismatch
```

This is a **fragment**, placed under `spec.template.spec.securityContext` of a Deployment/Pod, requiring a compatible volume/storage class. `fsGroupChangePolicy` applies only to volume types supporting it; it does not guarantee every PVC or bind mount instantaneously gets owner 10001. On some CSI drivers, ownership adjustments are delegated to the driver.

### OpenShift / Random UIDs

Some clusters assign an arbitrary UID differing from the image's `USER`. In that environment:

- Know the Pod's actual UID/GID and allowed security context constraints.
- JAR/config files should usually be **readable** even by other UIDs.
- Writable areas should rely on group permissions, ACLs, or `fsGroup` rather than assuming every Pod runs strictly as UID 10001.
- Never "fix" it by setting `privileged: true` or running as root if policy forbids it.

## 14. Dockerfile Variant When the JAR Is Built Outside Docker

Sometimes CI runs Maven first and Docker only packages the **QA-passed artifact**. You do not need a Maven build stage then; the Dockerfile can contain only the runtime stage. Example **`Dockerfile.runtime`**:

```dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:17-jre-jammy

RUN groupadd --gid 10001 appgroup \
    && useradd --no-log-init --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin appuser \
    && mkdir -p /opt/app /var/app-data \
    && chmod 0755 /opt/app \
    && chown 10001:10001 /var/app-data \
    && chmod 0750 /var/app-data

WORKDIR /opt/app
COPY --chown=10001:10001 --chmod=0444 \
    target/ownership-demo-1.0.0.jar /opt/app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

In this case, you must **intentionally update Section 8's `.dockerignore`**, because it currently ignores `target/`. Leaving `target/` ignored causes `COPY target/...jar` to fail even when Maven produced the JAR on the host.

Corresponding workflow:

```bash
mvn -B -ntp clean verify
docker build -f Dockerfile.runtime -t ownership-demo:prebuilt .
```

Preconditions: `Dockerfile.runtime` and `target/ownership-demo-1.0.0.jar` are included in the build context, and the file is an **executable Boot JAR**, not `.jar.original` or a plain archive. This two-step CI model makes it easy to trace the verified JAR's SHA-256 to the image, provided Docker copies only the exact tested artifact.

**Pick one clear strategy per workflow:**

- **Multi-stage** (Section 7): Maven builds and tests inside the Docker build stage; runtime image holds only JRE/JAR.
- **Prebuilt artifact** (Section 14): Maven builds and tests in CI; Dockerfile copies only the verified JAR.

Never accidentally rebuild a different JAR with altered dependencies/versions inside Docker when CI intended to ship the exact signed/QA-passed artifact from the prior step.

## 15. `ENTRYPOINT`, `CMD`, Signals, and Why to Avoid `sh -c`

`USER` defines privileges, while `ENTRYPOINT`/`CMD` define the running process. Good example:

```dockerfile
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

This is **exec form**. The Java process becomes the container's main process, receiving signals from Docker/Kubernetes directly and reporting its exit code cleanly to the container lifecycle. This aligns with Spring Boot graceful shutdown when configured with an adequate shutdown window.

Avoid unnecessary shell form:

```dockerfile
ENTRYPOINT java -jar /opt/app/app.jar
```

Shell form wraps execution in a shell, which can interfere with signal forwarding, shell expansion, and PID 1 behavior. If a shell script is genuinely needed to prepare the environment, document why, end with `exec java ...`, and stay non-root at runtime.

### Passing JVM Options Safely

When memory or runtime flags are needed:

```dockerfile
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/opt/app/app.jar"]
```

This is a **replacement fragment for the `ENTRYPOINT` line**; do not keep two `ENTRYPOINT` instructions. JVM options go before `-jar`, whereas Spring Boot application args like `--server.port=8081` go **after** the JAR or via suitable environment variables.

If using `JAVA_TOOL_OPTIONS`, keep in mind environment values can appear in logs/diagnostics. Never store secrets in Dockerfile `ENV` or `ARG` because image metadata/build history can expose them; use secret managers or runtime injection.

## 16. Non-Root Containers vs Rootless Docker

Two concepts are frequently conflated:

- **Non-root container process:** the application **inside the container** runs as a non-zero UID (e.g., `USER 10001:10001`).
- **Rootless Docker Engine / user namespaces:** the Docker daemon / host-side container mapping is configured not to depend on host root in certain workflows or remaps UIDs/GIDs.

They operate at different layers. A container with `USER 10001` on a rootful Docker daemon is **non-root inside the container**, yet the Docker daemon holds host-level privileges. Conversely, a rootless engine does not automatically fix bad permissions inside your image/application. Do not treat `USER` as sufficient protection if you mount the Docker socket or use `--privileged`.

For defense in depth alongside non-root `USER`, apply:

- Never run with `--privileged`.
- Drop unnecessary capabilities and restrict privilege escalation.
- Use a read-only root filesystem with properly prepared writable tmpfs/volumes.
- Never mount `/var/run/docker.sock` or sensitive host paths into app containers.
- Constrain network egress, resources, and syscalls per environment.
- Pin base image digests, scan for vulnerabilities, and update images regularly.
- Inject secrets via controlled runtime mechanisms; never bake them into JARs or image layers.

## 17. When Should the Owner Be Root vs `appuser`?

A common misconception is "every file in the image must be `chown appuser`." Instead, design by **access intent**:

| Component | Suggested Owner | Suggested Mode | Rationale |
| --- | --- | --- | --- |
| `/opt/app` directory | `root:root` | `0755` | App only traverses/reads; cannot modify its own code |
| `/opt/app/app.jar` | `root:root` **or** `10001:10001` | `0444`/`0644` | App only reads; mode matters as much as owner |
| `/etc/app/config.yml` (no secrets) | `root:root` | `0644` or stricter | App only reads config |
| `/etc/app/secret-file` | Per secret manager/mount | Minimal read access for app | Do not bake secrets into image build |
| `/var/app-data` | `10001:10001` or group ACL | `0750`/`0770` if shared | App intentionally writes data here |
| `/tmp` | Per runtime mount | Sticky mode `1777` common | Processes/Java may create temp files |
| Application logs | stdout/stderr | No writable app log dir needed | Container logging collects streams |
| JVM heap dumps / GC log files | Scoped writable volume | Matching app UID/GID | Only when flags requiring file writes are enabled |

This table lists **design options**, not a mandatory `chmod` for every organization. If multiple processes share a group or random UIDs are enforced, re-evaluate modes, ACLs, and group permissions. Never grant world-write just to skip configuration.

### Logging: stdout/stderr Usually Beats Files in WORKDIR

Containerized Spring Boot apps should log to stdout/stderr by default so the runtime collects them. Setting `logging.file.name=/opt/app/app.log` when `/opt/app` is non-writable causes errors. Instead of making the whole code directory writable, prefer stdout or direct log files to a volume with matching owner/group if policy requires files.

## 18. Real-World Failures and How to Diagnose Them

| Symptom | Common Cause | Check / Fix |
| --- | --- | --- |
| `java -jar app.jar`: unable to access jarfile | `WORKDIR` differs from JAR path or missing read permission | Check `docker image inspect` WorkingDir, `pwd`, `stat` on JAR; use absolute path |
| `Permission denied` reading JAR | Root-owned `0600` file, or parent dir lacks traverse bit | Run `id`, `stat -c '%u:%g %a %n'` on file and parent dirs; grant minimal read/traverse |
| `Permission denied` writing `/opt/app` | Directory designed as code-only, root-owned `0755` | Do not `chown` code; move output to `/var/app-data` or a volume |
| `Permission denied` writing `/var/app-data` | Host bind mount/PVC shadowed image owner/mode | Inspect mounted path, fix volume ownership/ACL or `fsGroup` policy |
| `USER appuser` fails with unknown user | Account not created in final stage or base lacks `/etc/passwd` | Create account in runtime stage; or use numeric UID |
| `RUN apt-get`/`useradd` fails after `USER 10001` | Dropped privileges before setup | Move setup commands before `USER`; runtime stays non-root |
| `COPY --chown=appuser:appgroup` fails | Named user/group didn't exist yet at `COPY` time | Create group/user earlier or use numeric `--chown` |
| `COPY --chown` has no expected effect | Using Windows containers or wrong stage/context | Check Dockerfile syntax, platform, Dockerfile frontend, and `stat` |
| Container runs as `uid=0(root)` despite `USER` | `docker run --user 0`, K8s securityContext override, wrong image | Inspect final image config and live process UID; check deployment spec |
| Docker image builds yet app fails to start | Copied plain JAR or missing dependencies | `jar tf` for `BOOT-INF/lib`, test `java -jar` on artifact, inspect build stage |
| Spring Boot fails creating temp directory | Read-only root filesystem or non-writable `/tmp` | Mount tmpfs/volume at `/tmp` with right permissions/mode/size |
| Works in local Docker, fails in Kubernetes | Different UID/GID, `readOnlyRootFilesystem`, PVC/CSI policy | Check Pod securityContext and mounted paths, `kubectl logs` |
| Mounting over `/opt/app` hides `app.jar` | Bind mount shadows image contents | Never mount over the code directory; mount dedicated data/config paths |
| App cannot bind port 80 as non-root | Privileged port/capabilities/sysctl and runtime policy | Use an unprivileged port like 8080; map externally via host port/reverse proxy |
| `EXPOSE 8080` yet host cannot connect | `EXPOSE` is metadata only | Use `docker run -p`/service/network; check bind interface and firewall |
| `chmod -R 777` "fixes" error unsafely | Granted overly broad world-write | Narrow write paths and owner/group/ACL; revert broad `chmod` |
| Built with Gradle yet Dockerfile looks for `target/*.jar` | Maven and Gradle output paths differ | For Gradle use `build/libs/` and pick exact `bootJar`, never `-plain.jar` |
| Runtime reports `sh: not found` when debugging | Distroless/minimal base has no shell | Use a debug image or external inspection; don't add a shell to prod just to debug |
| Same image tag builds produce different binaries | Base tag drifted, JAR rebuilt, inputs changed | Pin base digest, record source commit and image/JAR digests; deploy QA artifact |

### Layer-by-Layer Investigation Workflow

1. **Identify the actually running image**: tag, digest, runtime spec. Never debug an image you built locally that was not actually deployed.
2. **Identify process identity**: `docker image inspect ...Config.User` or `docker run --entrypoint sh ... -c id`, Kubernetes `runAsUser`, and live Pod identity.
3. **Identify current working directory**: `WORKDIR`/`docker run -w`/Kubernetes `workingDir`, and the JAR path in `ENTRYPOINT`.
4. **Inspect permissions along the whole path**: UID/GID/mode of the file, parent directories, mount options, ACL/SELinux.
5. **Check all runtime write paths**: `/tmp`, uploads, logs, cache, heap dumps, embedded databases, certificate stores.
6. **Verify the archive**: executable Boot JAR vs plain JAR; Java version and dependencies.
7. **Inspect volumes**: verify mounts do not shadow files, runtime owner vs image owner, and `fsGroup`/CSI support.
8. **Fix Dockerfile/securityContext/volume provisioning deliberately**, rebuild, test permissions, and smoke-test — never bypass with root unless genuinely justified.

## 19. Self-Check Scenarios

**Scenario A:** `WORKDIR /opt/app` and `USER 10001:10001` are set, yet `app.jar` is root-owned `0600`. Will the app start?

*Answer:* Not under standard POSIX permissions. `WORKDIR` does not grant read access; the app user cannot read a root-owned `0600` file. Keep root ownership with readable mode (`0644`/`0444`) or set ownership/mode per policy.

**Scenario B:** `app.jar` is owned by `10001` with mode `0444`. Can the app modify the JAR itself?

*Answer:* No, because the `w` bit is omitted for the owner. Ownership does not automatically equal full permissions.

**Scenario C:** The Dockerfile sets `COPY --chown=10001:10001 ... /var/app-data`, yet with a bind mount the app still cannot write. Why?

*Answer:* A bind mount shadows the image's filesystem path; permissions are governed by the mounted path and host mapping. Inspect the mount's permissions and prepare the host/volume, not just the image layer.

**Scenario D:** Placing `USER 10001` before `RUN groupadd ...` in the Dockerfile fails. How do you fix it?

*Answer:* Group/user creation requires build-time root privileges on the base image; place those commands before `USER`. Runtime still drops privileges afterward.

**Scenario E:** A Dockerfile omits `WORKDIR` and uses `ENTRYPOINT ["java","-jar","app.jar"]`. Is that safe?

*Answer:* You should not rely on an unspecified base image default working directory. Set `WORKDIR /opt/app` and use the absolute `/opt/app/app.jar` in the entrypoint.

**Scenario F:** `docker run --read-only` makes Tomcat error creating temp files even though the JAR is readable. Why?

*Answer:* A read-only root layer blocks temp file writes; provide a tmpfs or volume for the actual path used by the JVM/Tomcat, such as `/tmp`, with proper permissions.

**Scenario G:** Kubernetes sets `runAsNonRoot: true`, yet the PV is root-owned with mode `0700`. Is the Pod guaranteed to write?

*Answer:* No. `runAsNonRoot` only constrains process UID; volume writes require matching filesystem permissions/ACLs or storage driver `fsGroup` support. Never run as root to hide the error.

**Scenario H:** Does `EXPOSE 8080` make the port reachable from a browser on the host?

*Answer:* No. You must publish the port with `-p` or configure container networking/orchestration; `EXPOSE` is purely informational.

**Scenario I:** An operator runs `docker run --user 0` on an image with `USER 10001:10001`. Is runtime still non-root?

*Answer:* No. `--user` overrides the image's default identity. Therefore CI/production must inspect the runtime spec, not only the Dockerfile.

**Scenario J:** The platform assigns an arbitrary dynamic UID. Should we try changing ownership of the entire filesystem to `10001`?

*Answer:* No. Design code files to be readable by the allowed UIDs, use group/ACL/`fsGroup` for writable volumes, and test against actual platform constraints.

## 20. Pre-Release Dockerfile Verification Checklist

**Paths and image contents:**

- `WORKDIR` is a stable absolute path; `ENTRYPOINT` uses an absolute JAR path.
- Only the Spring Boot **executable JAR** is copied into the runtime stage; no source, Maven cache, or secrets.
- Runtime image includes only the required JRE/JDK, not full build tools by default.
- `.dockerignore` matches the multi-stage or prebuilt-JAR strategy without accidentally excluding artifacts needed by `COPY`.

**Owner, mode, and user:**

- Final stage sets a non-root `USER` with a managed UID/GID.
- `id` / image inspect proves runtime UID/GID, with no `--user 0` or orchestrator override.
- Code/config files are readable yet not arbitrarily writable by the app.
- Data directories genuinely needing writes have exact UID/GID/mode configured; no `chmod 777`.
- Parent directories have traverse permissions; both files and directories checked.
- `COPY --chown` and `COPY --chmod` match the target stage and Dockerfile frontend.

**Runtime and storage:**

- Spring Boot listens on an unprivileged port such as 8080; `EXPOSE` is not confused with `-p`.
- `/tmp` and actual write paths have writable mounts when enabling a read-only root filesystem.
- Bind mounts/PVCs/volumes are inspected for ownership **after mounting**, not assumed from base image permissions.
- K8s `runAsUser`/`runAsGroup`/`runAsNonRoot`/`fsGroup` align with runtime storage.
- No privileged mode, broad capabilities, Docker socket mounts, or baked-in secrets.

**QA and artifact delivery:**

- Maven `verify`/Gradle `build` and required tests actually run in the build workflow.
- Image config `User` and `WorkingDir`, process `id`, `stat`, and access checks verified.
- Container smoke-tested at the exact URL; verified on both Docker and Kubernetes when deploying to a cluster.
- Base image digest pinned per release, scanned for CVEs, with checksums retained for QA-passed images/artifacts.
- Read-only mode and volumes verified in a production-like environment before enforcing them.

**Conclusion:** `WORKDIR` chooses where work happens; **owner/GID/mode** govern access rights; `USER` sets the process identity. The right setup for a Spring Boot container is: **readable but non-writable JAR, traversable runtime directory, separate writable data path, non-root runtime UID/GID, and compatible mount permissions**. Use `COPY --chown`/`--chmod` to encode image permissions, `USER` at the end of the runtime stage to drop privileges, and confirm with **`id` + `stat` + permission tests + an HTTP smoke test**. Never treat build success or `WORKDIR` alone as proof that permissions are right.

### Official Documentation

- Dockerfile reference (`WORKDIR`, `USER`, `COPY --chown`, `COPY --chmod`): https://docs.docker.com/reference/dockerfile/
- Docker — Building Best Practices (`USER` and fixed UID/GID): https://docs.docker.com/build/building/best-practices/
- Docker — Dockerfile Overview: https://docs.docker.com/build/concepts/dockerfile/
- Docker — Bind Mounts (mounts shadow image contents and permissions): https://docs.docker.com/engine/storage/bind-mounts/
- Docker — tmpfs mounts and `--tmpfs`: https://docs.docker.com/engine/storage/tmpfs/
- Docker — `docker container run`: https://docs.docker.com/reference/cli/docker/container/run/
- Spring Boot — Container Images/Dockerfiles: https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html
- Spring Boot — Efficient Images/Layering: https://docs.spring.io/spring-boot/reference/packaging/container-images/efficient-images.html
- Kubernetes — Security Context (`runAsUser`, `runAsGroup`, `fsGroup`, `readOnlyRootFilesystem`): https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Eclipse Temurin — Official Container Image Sources: https://github.com/adoptium/containers