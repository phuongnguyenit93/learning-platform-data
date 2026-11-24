# Preparing the Docker Daemon and Verifying Connectivity from Spring Boot Build Tools

## 1. Problem to Solve

When you want to create a Docker/OCI image for Spring Boot using **Cloud Native Buildpacks (CNB)**, you typically run one of two commands:

~~~bash
mvn spring-boot:build-image
./gradlew bootBuildImage
~~~

These two commands can create an image directly from a Java application **without a Dockerfile**, but they require access to a **Docker-compatible daemon**. A common failure is when `docker --version` succeeds in the terminal, yet the plugin reports “Cannot connect to Docker daemon”. The root cause: **Docker CLI, Docker daemon, Docker context, image registry, and Cloud Native Buildpacks are separate components**.

After this lesson, you will know how to:

1. Understand what the Docker daemon is and why Maven/Gradle build-image must reach the daemon.
2. Check step-by-step with `docker --version`, `docker version`, `docker info`, `docker ps`, and `docker run`.
3. Prepare Docker Desktop on Windows/macOS and Docker Engine on Linux; identify WSL2, Linux containers, and Unix sockets.
4. Check Docker context, `DOCKER_CONTEXT`, `DOCKER_HOST`, `DOCKER_CONFIG`, TLS/certificates, and user permissions.
5. Understand permission differences across terminals, IDEs, the Gradle Daemon, build containers, and CI runners.
6. Create a runnable, unit-testable Spring Boot Java 17 app and build an OCI image with Maven.
7. Create a Gradle Kotlin DSL variant with the `bootBuildImage` task and verify the image in the right daemon.
8. Configure a remote Docker daemon via context or TLS, avoiding insecure TCP connections.
9. Separate Docker API errors from builder/run image pull errors, registry login, CNB lifecycle, volumes, and Java packaging.
10. Build a CI preflight, troubleshooting, and smoke-test workflow for the created image.

**Example versions:** Spring Boot **3.5.16**, Java **17+**. You can use Maven/Gradle versions compatible with Spring Boot 3.5, preferring the Wrapper if the project provides one. These values are concrete practice milestones, not a requirement for every project to stay on these exact versions long-term.

## 2. Connection Diagram: Who Is Talking to Whom?

~~~text
Developer Terminal / IDE / CI runner
           |
           |  mvn spring-boot:build-image
           |  gradle bootBuildImage
           v
  Spring Boot Maven/Gradle Plugin
           |
           |  Docker-compatible Engine API
           |  via Unix socket, Windows npipe, or TCP/TLS
           v
       Docker daemon
           |
           +-- Pull builder image from registry
           +-- Pull run image from registry
           +-- Create container running CNB build lifecycle
           +-- Create/mount cache volumes and workspace
           +-- Export OCI application image into image store
           |
           v
   docker image inspect app:tag
   docker run --rm app:tag
~~~

**Docker CLI** (`docker`) is the program sending requests to the daemon via API. **Docker daemon** (`dockerd` on Docker Engine) is the server managing images, containers, volumes, and networking. **Docker context** is a configuration selecting a daemon endpoint. **Registry** is where images are stored/distributed over the network; a registry **is not a daemon**.

The **CNB builder image** contains buildpacks and the lifecycle. The **run image** is the runtime base of the OCI application image. The Spring Boot plugin uses the Docker API to fetch/run those components; it is not equivalent to running `docker build` on a custom Dockerfile.

### 2.1. Distinguishing Each Check Result

| Command | What is proven | What is not yet proven |
| --- | --- | --- |
| `docker --version` | CLI binary is in PATH | Whether the Docker daemon is running |
| `docker version` showing both **Client** and **Server** | CLI can connect to a Docker daemon | Whether another Maven/Gradle process shares the same connection |
| `docker info` | Daemon responds to API and returns server config | Whether pulling builder/run images and CNB lifecycle will succeed |
| `docker ps` | Permission to call API to list containers | Whether permissions suffice to create, mount, and run the builder container |
| `docker run --rm hello-world` | Ability to pull (when needed) and run a simple container | Whether a specific Paketo builder/JDK/image platform is valid |
| `mvn spring-boot:build-image` succeeds | Plugin built the application OCI image | Whether the production app passed full integration/security tests |

If only the CLI is present while the daemon is stopped, `docker --version` can still print a version. Therefore, **never use this command alone to conclude the environment is ready**.

### 2.2. Does the Spring Boot Plugin Require Docker CLI?

Spring Boot 3.5 Maven/Gradle plugins can read **Docker CLI config files/context**, then communicate with a **Docker-compatible API**. They do not merely shell out to `docker build`. The Docker CLI is very useful for diagnostics, but what is required is an **API daemon accessible by the build process itself**, along with the capabilities CNB needs.

Do not mistake `docker buildx version` for a valid probe for Spring Boot `build-image`. Buildx is separate tooling; having Buildx does not prove the Spring Boot plugin connects to the right daemon.

## 3. Minimum Prerequisites Before Calling build-image

- JDK compatible with Java 17 and Spring Boot 3.5.
- Project `mvn clean verify` or `./gradlew clean test bootJar` succeeds **without depending on Docker**.
- Docker Engine, Docker Desktop, or a compatible engine is running and exposing a valid API.
- The Maven/Gradle process has permission to access the daemon endpoint.
- The daemon has storage, memory, and the ability to create containers/volumes.
- Network/registry or image cache allows fetching builder and run images.
- On Windows Docker Desktop, use **Linux containers** for Paketo Linux builders.
- Image OS/architecture matches: typically Linux `amd64` or `arm64` depending on the builder.
- If remote/CI uses TLS, certificates and firewall/VPN are properly configured.

Follow the order: **Java project OK → daemon reachable → container capability OK → builder/run image pull OK → build-image OK → run application image OK**. Do not reverse the order and lump every failure into “Docker failed”.

## 4. Checking the Docker Daemon from the Terminal

### 4.1. Step 1: Is the CLI Present?

~~~bash
docker --version
~~~

For example, the terminal might print:

~~~text
Docker version <server-or-cli-version>, build <build-id>
~~~

The line above is an **output outline**, not a guaranteed exact result across machines. Even if exit code is 0, you **have not proven the daemon is reachable**.

### 4.2. Crucial Step: Is the Docker Server Responding?

~~~bash
docker version
docker info
~~~

`docker version` must show both **Client** and **Server** information. If only Client appears followed by `Cannot connect to the Docker daemon`, check the daemon process, endpoint, context, socket permissions, or TLS.

`docker info` normally displays operating system, architecture, container runtime, storage driver, server version, and image/cache information. To shorten output for CI scripts:

~~~bash
docker version --format '{{.Server.Version}}'
docker info --format '{{.OSType}}/{{.Architecture}}'
~~~

These are Docker CLI Go templates; no need to guess versions. If the CLI is connecting to the wrong daemon, the check may “succeed” against a **different daemon**, so checking the context is still necessary.

### 4.3. Confirming the Docker Engine API Actually Works

~~~bash
docker ps
docker image ls
~~~

These two commands are relatively lightweight and read container/image state on the selected daemon. When policy permits pulling public images and creating containers, use an additional probe:

~~~bash
docker run --rm hello-world
~~~

`docker run` has side effects: it creates a container and may pull an image from a registry. Do not call it a “read-only check”; run it only when allowed. If it succeeds, the daemon can run a simple container, but **it still does not prove the CNB builder image will pull/run successfully**.

### 4.4. Recommended Probe Flow

~~~text
docker --version
    |
    +-- fail --> Missing Docker CLI / wrong PATH
    |
    v
docker version: Server present?
    |
    +-- no --> daemon service / context / socket / TLS / permission
    |
    v
docker info / docker ps
    |
    +-- fail --> authorization / API compatibility
    |
    v
docker run --rm hello-world (optional, if policy permits)
    |
    +-- fail --> container runtime / image pull / network / storage
    |
    v
Maven spring-boot:build-image or Gradle bootBuildImage
    |
    +-- fail --> check builder/run image, buildpack, cache, process env
    |
    v
docker image inspect <exact-image>:<exact-tag>
    |
    v
docker run --rm <exact-image>:<exact-tag>
~~~

Angle brackets `<...>` in the diagram are placeholder markers, not literal commands to copy verbatim. Specific names and tags are provided in the hands-on sections below.

## 5. Preparing Docker Engine on Linux

### 5.1. Docker Service on a systemd Host

After installing Docker Engine per official documentation:

~~~bash
sudo systemctl status docker
docker version
docker info
~~~

If the service exists but is stopped, an administrator can run:

~~~bash
sudo systemctl start docker
docker version
~~~

**Do not blindly apply `systemctl`** on WSL2 without systemd, container runners, rootless daemons, or machines using another init system. In those environments, the daemon has its own lifecycle.

The default Docker Engine Unix socket is typically:

~~~text
unix:///var/run/docker.sock
~~~

If using a rootless engine or alternate context, the endpoint may differ. **Do not guess the socket path from the OS and skip `docker context inspect`.**

### 5.2. Permission Denied Errors

Suppose `docker info` reports it cannot access `/var/run/docker.sock`. Test with administrative privileges:

~~~bash
sudo docker info
~~~

If it succeeds with `sudo` while a normal user fails, the daemon is likely running fine and the fault lies in the **current process's permissions**.

An administrator can grant group membership according to policy:

~~~bash
sudo usermod -aG docker "$USER"
~~~

Afterward, you usually need to log out/in or start a new session and then check:

~~~bash
id -nG
docker info
~~~

**Security warning:** a user in the `docker` group has very high privileges on the host, often nearly equivalent to root. Do not add every developer or CI job to that group without control. **Do not run `chmod 666 /var/run/docker.sock`** as a “quick fix”, because it grants daemon access to all processes.

Consider rootless Docker or isolated runners where appropriate; also understand trade-offs around socket paths, volumes, container privileges, and CNB compatibility.

### 5.3. Rootless Docker Socket

A rootless daemon typically uses a path keyed by UID, for example:

~~~text
unix:///run/user/1000/docker.sock
~~~

This is only an **example** for UID 1000; do not hardcode it for every machine. Check your UID and Docker context:

~~~bash
id -u
docker context ls
docker context show
docker context inspect "$(docker context show)"
docker info
~~~

If Maven runs under a different user from the one owning the rootless socket, it may fail to connect. Configure the context/socket for the **exact service account**, rather than loosely changing permissions.

## 6. Docker Desktop on Windows and macOS

### 6.1. Windows + Docker Desktop + WSL2

Standard procedure:

1. Install Docker Desktop per vendor instructions, verifying virtualization/WSL2 requirements.
2. Start Docker Desktop and confirm the backend is **running**.
3. Select **Linux containers** to use Paketo Linux builders.
4. Open PowerShell under the user running the build tool.
5. Run:

~~~powershell
docker --version
docker context ls
docker context show
docker version
docker info
~~~

Docker Desktop may create a context named `desktop-linux`, but **do not assume** it exists on every machine. If the daemon is running Windows containers, Linux builder/run images may fail due to OS/platform incompatibility.

The Windows Docker API may use a named pipe:

~~~text
npipe:////./pipe/docker_engine
~~~

Usually there is no need to manually set `DOCKER_HOST` to the named pipe if Docker Desktop/current context is already recognized by the plugin. Check `docker context inspect` before overriding.

### 6.2. Distinguishing the Windows Host and WSL2 Shell

Suppose:

~~~text
Windows PowerShell:
    docker version        --> Server OK
    Maven/Gradle?         --> Not running here

WSL2 Ubuntu:
    ./mvnw build-image    --> Actually runs here
    docker info           --> Not guaranteed OK
~~~

A WSL2 distro has its **own filesystem, home directory, environment, and socket view**. Enable Docker Desktop WSL integration if required by your workflow, then check `docker info` **directly inside the WSL2 shell**. A passing check on the Windows host does not automatically grant access to a WSL2 process.

Similarly, an IDE running on the Windows host and a Gradle daemon running inside WSL/a container may see different Docker configs; probe in the exact environment where the build tool process actually executes.

### 6.3. macOS + Docker Desktop or Colima

On macOS, Docker Desktop provides a Linux VM with a Docker Engine-compatible API. After starting Desktop:

~~~bash
docker context ls
docker context show
docker version
docker info
~~~

If using Colima, check the daemon/context created by Colima:

~~~bash
docker context ls
docker context inspect colima
~~~

The second command **only applies when the `colima` context actually exists**. Do not copy socket paths from old blog posts because they can vary by user and Colima version. The Spring Boot plugin can read the CLI's Docker context or be configured with an explicit endpoint when needed.

## 7. Docker Context as the Source of Truth for Connectivity

### 7.1. Viewing the Selected Daemon Endpoint

Linux/macOS:

~~~bash
docker context ls
docker context show
docker context inspect "$(docker context show)"
~~~

PowerShell:

~~~powershell
docker context ls
docker context show
docker context inspect (docker context show)
~~~

In the `inspect` output, look at `Endpoints.docker.Host`. It may be a Unix socket, Windows npipe, or TCP/TLS endpoint. If multiple daemons exist (Desktop, Colima, minikube, remote), **each daemon's image store is separate**. Building an image into daemon A does not mean `docker image ls` on daemon B will see it.

Do not print Docker registry credentials or private certificate keys to public CI logs. Only log the endpoint/context and connection errors.

### 7.2. Selecting a Context for One Command Instead of Machine-Wide

When the machine **has** a `desktop-linux` context:

~~~bash
docker --context desktop-linux info
~~~

This uses the context **for a single Docker CLI invocation only**. By contrast:

~~~bash
docker context use desktop-linux
~~~

changes the **default context saved in the Docker CLI config**, which can affect other terminals/IDEs sharing that config. Be careful before using it in a shared environment.

### 7.3. Five Environment Variables Supported by Spring Boot 3.5

| Variable | Role |
| --- | --- |
| `DOCKER_CONFIG` | Directory for Docker CLI config and context definitions; defaults typically to `$HOME/.docker` |
| `DOCKER_CONTEXT` | Context name to look up Docker daemon info; **takes precedence over `DOCKER_HOST`** |
| `DOCKER_HOST` | Docker API endpoint: Unix socket, named pipe, or TCP host/port |
| `DOCKER_TLS_VERIFY` | Value `1` requires TLS verification when using remote TLS |
| `DOCKER_CERT_PATH` | Path containing CA/certificate/key suitable for Docker API TLS |

Both Spring Boot Maven `build-image` and Gradle `bootBuildImage` can read Docker CLI config, current context, and these variables. **`DOCKER_CONTEXT` overrides `DOCKER_HOST`** according to the Spring Boot 3.5 Docker daemon documentation.

### 7.4. Inspecting Environment Without Exposing Secrets

Bash on Linux/macOS:

~~~bash
printenv DOCKER_CONFIG
printenv DOCKER_CONTEXT
printenv DOCKER_HOST
printenv DOCKER_TLS_VERIFY
docker context show
docker version
~~~

`printenv` can exit non-zero when a variable is unset; in `set -e` shells/CI, handle that case if those variables are allowed to be absent. Do not run `env` to dump the entire secret-bearing environment to public logs.

Windows PowerShell:

~~~powershell
Write-Output "DOCKER_CONFIG=$env:DOCKER_CONFIG"
Write-Output "DOCKER_CONTEXT=$env:DOCKER_CONTEXT"
Write-Output "DOCKER_HOST=$env:DOCKER_HOST"
Write-Output "DOCKER_TLS_VERIFY=$env:DOCKER_TLS_VERIFY"
docker context show
docker version
~~~

Do not print registry passwords/tokens to logs. Keep checks restricted to “printing only Docker endpoint variables and TLS flags” instead of dumping the whole environment.

### 7.5. Removing Erroneous Overrides in the Current Shell Only

Bash:

~~~bash
unset DOCKER_CONTEXT
unset DOCKER_HOST
docker context show
docker info
~~~

PowerShell:

~~~powershell
Remove-Item Env:DOCKER_CONTEXT -ErrorAction SilentlyContinue
Remove-Item Env:DOCKER_HOST -ErrorAction SilentlyContinue
docker context show
docker info
~~~

**Only do this once you have confirmed the current overrides are wrong.** In CI, a remote daemon may be the intended design; clearing variables would cause the job to connect to the wrong daemon. Do not modify global Windows system environment variables or someone else's persistent Docker context without understanding the impact.

## 8. Why Does Terminal Docker Work While Maven/Gradle Still FAILS?

### 8.1. Different User or Process

A process **inherits environment from its parent process**. Maven launched from a new terminal may differ from a previously started Gradle daemon or an IDE opened before Docker environment settings were changed.

~~~text
Terminal A: docker info -> OK
     |
     +--> Maven runs directly in Terminal A -> inherits A's env

IDE started from OS before env change
     |
     +--> Gradle build -> may retain stale env

CI job container
     |
     +--> Host Docker socket may not be mounted
~~~

Therefore, the Docker CLI probe must occur **in the exact same environment/runner/user** executing build-image. A passing `docker version` on a laptop host does not prove a job container has API access.

### 8.2. Plugin Has Its Own Docker Configuration

The Spring Boot plugin supports `docker.context`, `docker.host`, `docker.tlsVerify`, `docker.certPath`, and `docker.bindHostToBuilder`. If the build script sets a specific endpoint, inspect the exact plugin configuration and build logs rather than looking solely at the CLI default context.

### 8.3. A Full Check from the Same Shell

Maven:

~~~bash
docker context show
docker version
docker info
mvn spring-boot:build-image
docker image ls
~~~

Gradle:

~~~bash
docker context show
docker version
docker info
./gradlew --no-daemon bootBuildImage
docker image ls
~~~

Only run the Gradle Wrapper when the project actually has `gradlew`; otherwise use an installed Gradle of a compatible version. `--no-daemon` removes one environmental variable during diagnostics, and is not a substitute for proper context configuration.

## 9. Complete Spring Boot 3.5.16 Maven Project

### 9.1. Project Structure

This is a Java 17 Spring Boot application **without a web server**: it prints one line and exits. This design lets you test the image build path without port 8080 conflicts.

~~~text
cnb-connect-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cnb/
    │   └── CnbApplication.java
    └── test/java/com/example/cnb/
        └── CnbApplicationTest.java
~~~

### 9.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cnb-connect-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <configuration>
                    <image>
                        <name>cnb-connect-demo:1.0.0</name>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-parent` manages Boot 3.5.16 plugin/dependency versions. `spring-boot-maven-plugin` provides the `build-image` goal, which uses Cloud Native Buildpacks. `<image><name>...` only sets the **output image name in the daemon**; it does not automatically publish to a registry.

**No Dockerfile is needed**, and there is no need to add `docker-java` to app dependencies. The plugin builds the image from the executable JAR, using its configured CNB builder/run image automatically.

### 9.3. Complete Java Class

Create `src/main/java/com/example/cnb/CnbApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CnbApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbApplication.class, args);
    }

    public static String message() {
        return "CNB_DAEMON_OK";
    }

    @Bean
    ApplicationRunner output() {
        return args -> System.out.println(message());
    }
}
~~~

This class compiles with Java 17 and Spring Boot Starter. When the context initializes, `ApplicationRunner` prints:

~~~text
CNB_DAEMON_OK
~~~

This is the **line printed by our Java code**, not a claim that the entire stdout consists of only one line; Spring Boot may emit startup logs.

### 9.4. Complete JUnit Test

Create `src/test/java/com/example/cnb/CnbApplicationTest.java`:

~~~java
package com.example.cnb;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CnbApplicationTest {

    @Test
    void messageIsStable() {
        assertEquals("CNB_DAEMON_OK", CnbApplication.message());
    }
}
~~~

This is a unit test requiring no HTTP server, database, or Docker. Thus **`mvn clean verify` passing does not mean the daemon is accessible** — an important lesson when separating Java build failures from CNB infrastructure failures.

### 9.5. Verifying the Java Build Before Building the Image

From the project root (assuming Maven is installed):

~~~bash
java -version
mvn -version
mvn clean verify
java -jar target/cnb-connect-demo-1.0.0.jar
~~~

On success, the line `CNB_DAEMON_OK` appears. If the project was generated by Spring Initializr and **actually includes a Wrapper**, use `./mvnw clean verify` on POSIX or `.\mvnw.cmd clean verify` on Windows.

### 9.6. Running Maven build-image from the Same Environment

~~~bash
docker context show
docker version
docker info
mvn spring-boot:build-image
~~~

When invoked from the CLI, the `build-image` goal ensures the package lifecycle runs as needed. It communicates with the Docker API, pulls builder/run images if necessary, runs the CNB lifecycle, and exports the image.

Read the logs to distinguish the stages:

~~~text
Checking / pulling builder image
Checking / pulling run image
Detecting buildpacks
Analyzing / restoring / building
Exporting image
Build success
~~~

The lines above represent **conceptual order only**, not fixed raw logs. If the build fails during the pull step, do not modify Java classes. If it fails before contacting the daemon, check context/socket/permissions first.

### 9.7. Checking the Image in the Right Daemon

~~~bash
docker image ls cnb-connect-demo
docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

When the container runs properly, the Java app prints `CNB_DAEMON_OK`. If the image does not appear, check the Maven image name/tag and whether the Docker context **after the build** still points to the same daemon. If Maven built on a remote Docker daemon while the CLI is reading local Docker Desktop, the two image stores are different.

### 9.8. Windows PowerShell Equivalent

~~~powershell
docker context show
docker version
docker info
mvn clean verify
mvn spring-boot:build-image
docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

If Maven is not installed on Windows but the project has `mvnw.cmd`, use `.\mvnw.cmd` accordingly. Importantly: **Docker Desktop must be running Linux containers**, not just have a Docker icon in the taskbar.

## 10. Equivalent Gradle Kotlin DSL Project

### 10.1. Project and Source

Reuse the **same** `CnbApplication.java` and `CnbApplicationTest.java` from section 9 in a separate Gradle project:

~~~text
cnb-connect-gradle/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/com/example/cnb/CnbApplication.java
└── src/test/java/com/example/cnb/CnbApplicationTest.java
~~~

### 10.2. Complete settings.gradle.kts

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "cnb-connect-gradle"
~~~

### 10.3. Complete build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.testing.Test
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )

    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("cnb-connect-gradle:1.0.0")
}
~~~

The Spring Boot Gradle Plugin creates the `bootBuildImage` task when the appropriate Java/War plugin is applied. `platform(...)` imports the Spring Boot BOM so Spring library/test library versions are managed; **simply applying the Boot plugin does not automatically provide versions for versionless dependencies**.

### 10.4. Testing and Building the Image

If the project has the Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -jar build/libs/cnb-connect-gradle-1.0.0.jar

docker version
docker info
./gradlew --no-daemon bootBuildImage

docker image inspect cnb-connect-gradle:1.0.0
docker run --rm cnb-connect-gradle:1.0.0
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
docker version
docker info
.\gradlew.bat --no-daemon bootBuildImage
docker image inspect cnb-connect-gradle:1.0.0
docker run --rm cnb-connect-gradle:1.0.0
~~~

Wrapper commands only work if the repository already has `gradlew`/`gradlew.bat` scripts and `gradle/wrapper/*`. If not, use a compatible installed Gradle version to generate the Wrapper first and then run. The line printed by the Java app after startup is `CNB_DAEMON_OK`.

### 10.5. Gradle Daemon and Environment Variables

The Gradle Daemon can outlive a terminal/IDE, making it harder to diagnose inherited environment variables. When suspecting the Daemon is using a stale context/env, try `--no-daemon` in the exact shell:

~~~bash
docker context show
docker info
./gradlew --no-daemon bootBuildImage
~~~

When you need to manage daemons for **your own user/project**, you can run `./gradlew --stop`. Do not stop shared CI daemons arbitrarily or assume `--no-daemon` replaces a valid Docker API endpoint.

## 11. Configuring Docker Context/Endpoint Directly in the Maven Plugin

### 11.1. Default Needs No Host Configuration

On Docker Desktop or a local Docker Engine with a valid current context, the Spring Boot Maven Plugin **automatically reads the Docker CLI config**. Set `<docker><host>...` explicitly only when required: remote daemon, rootless socket, Colima/Podman, or special CI setups.

### 11.2. Selecting a Named Context

Snippet inside `spring-boot-maven-plugin` (not a standalone POM):

~~~xml
<configuration>
    <docker>
        <context>desktop-linux</context>
    </docker>
</configuration>
~~~

**Use only when `desktop-linux` actually exists** for the user running Maven (`docker context ls`). A shared team POM should generally not hardcode one member's laptop context.

### 11.3. Remote Docker Daemon with TLS

**Model** configuration example, not a live endpoint:

~~~xml
<configuration>
    <docker>
        <host>tcp://192.0.2.10:2376</host>
        <tlsVerify>true</tlsVerify>
        <certPath>/home/developer/.docker/certs</certPath>
    </docker>
</configuration>
~~~

`192.0.2.10` is a **TEST-NET address used for documentation examples**, not a server to connect to. In real deployments, there must be a daemon running TLS, issued certificates, firewall/VPN, and a valid path in the runner. **Do not commit private keys** or credentials into the POM.

Do not use unencrypted `tcp://0.0.0.0:2375` as a general troubleshooting workaround: the Docker API holds very high privileges on the host.

### 11.4. bindHostToBuilder

The Maven Plugin also provides `bindHostToBuilder`: when enabled, the host configuration is passed into the CNB builder container. This option is useful for **some alternative engine environments such as Podman**, and does not need to be enabled by default for every Docker Desktop setup.

If host API probes pass but the builder lifecycle fails due to socket/endpoint access inside the builder, consult the documentation for that engine before enabling it. Do not use it to mask Docker socket permission errors of the Maven process itself.

## 12. Configuring the Docker Endpoint in Gradle

### 12.1. Selecting a Named Context

Additional snippet in `build.gradle.kts`:

~~~kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    docker {
        context.set("desktop-linux")
    }
}
~~~

It requires importing `BootBuildImage` as in the complete file in section 10. If that context name does not exist on the machine/runner, choose an actual context; do not commit a laptop-specific context name into a shared project.

### 12.2. Remote TLS Endpoint

Kotlin DSL snippet:

~~~kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    docker {
        host.set("tcp://192.0.2.10:2376")
        tlsVerify.set(true)
        certPath.set("/home/developer/.docker/certs")
    }
}
~~~

Equivalent Groovy DSL:

~~~groovy
tasks.named("bootBuildImage") {
    docker {
        host = "tcp://192.0.2.10:2376"
        tlsVerify = true
        certPath = "/home/developer/.docker/certs"
    }
}
~~~

These are **separate configuration examples**, not blocks to be copied simultaneously. The TEST-NET address and illustrative path must be replaced with values managed by the real environment. Do not set both `context` and a conflicting `host` without understanding precedence; when debugging, choose **one primary configuration source**.

### 12.3. Environment Variables May Be Better Than Hardcoding

In CI, Docker context/TLS is usually provisioned by the runner. Use per-job environment variables or runner-specific plugin properties to avoid hardcoding personal endpoints in build scripts. Most importantly: that environment must be read by the **Maven/Gradle process**, not merely tested in an unrelated terminal.

## 13. Daemon Connection Differs from Registry Connection

### 13.1. `docker info` Succeeds Yet Builder Pull FAILS

Even when `docker info` succeeds, the plugin can still fail at:

~~~text
Pulling builder image ...
Pulling run image ...
~~~

Common causes:

- Daemon DNS/network/firewall/proxy cannot reach the registry.
- Registry rate limiting.
- Private registry requires token/password/credential helper.
- Daemon's certificates/CA do not trust an internal registry.
- Builder/run image tag does not exist, or registry timed out.
- Image platform does not match the daemon's Linux/architecture.

Read the **actual image name from the build log** and test pulling it in the same daemon. With a Boot 3.5 project using Paketo, for example:

~~~bash
docker pull paketobuildpacks/builder-noble-java-tiny:latest
~~~

This is an image name plugin 3.5 can use. Do not assume `latest` is immutable or right for every release; get the **exact name from the build log**.

### 13.2. Builder Registry and Publish Registry Are Two Separate Concerns

| Spring Boot Plugin Property | Function |
| --- | --- |
| `docker.builderRegistry` | Credentials to pull builder/run images from a protected registry |
| `docker.publishRegistry` | Credentials to push the application image when publishing |
| `docker.host` | Docker daemon API endpoint; not a registry endpoint |
| `image.name` or Gradle `imageName` | Name/tag of the application image |
| `image.publish` or Gradle `publish` | Requests publishing the image (if enabled) |

You can use a Docker CLI credential store or appropriate helper instead of inserting passwords into the POM/Gradle file. **Do not confuse `docker login` with starting the daemon**: login only authenticates to a registry; the daemon still must be running and reachable.

### 13.3. An Image on Daemon A Is Not on Daemon B

If Maven builds against a remote Docker host while the current shell switches back to the local Desktop daemon, `docker image ls cnb-connect-demo` may not find the image. This **does not mean the Maven build failed**. Keep the same context/host when running:

~~~bash
docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

To transfer images between daemons, use registry push/pull or image save/load according to organizational workflow; **do not assume Docker contexts share a local image store**.

## 14. Builder Container, Volumes, Cache, and Network

### 14.1. The Plugin Does More Than `docker ps`

Cloud Native Buildpacks may:

1. Pull the builder image and run image.
2. Check builder metadata and image OS/architecture.
3. Create a container to run the lifecycle.
4. Mount application source/archive, launch/build caches, and workspace.
5. Run the detect/build/export phases of buildpacks.
6. Export the OCI image into the daemon image store, and optionally push to a registry.

Therefore, `docker ps` passing can still be followed by build-image failing due to **disk full**, volume mount denied, or builder network blocked. Separate errors by the **stage shown in the logs**.

### 14.2. Daemon Storage and Named Volumes

Use read-only inspection commands:

~~~bash
docker volume ls
docker system df
~~~

Named build cache/launch cache volumes belong to the **specific daemon**. Switching to a remote Docker host also switches where caches are stored, without carrying local caches over. If CI uses an ephemeral daemon per job, builder/run images and caches may have to be re-downloaded.

**Do not blindly run `docker system prune -a --volumes`** on a shared machine to fix an error. That command can delete data/images/volumes belonging to other projects. When cleanup is needed, identify the exact job-owned resources, backups, and retention policy.

### 14.3. Proxy, DNS, and Certificates Inside the Builder

The Maven host having network access does not guarantee the **CNB builder container** has network access to JDK/buildpack downloads. Proxy/CA settings may need to be configured on both the Docker daemon and the builder environment. Do not print proxy passwords in logs or store private certificates in a public repository.

Remote Docker daemons also introduce **bind mount path** issues: a host path on a laptop does not automatically exist on the remote server. When using custom builder bindings/cache paths, understand that paths resolve **on the daemon host** and verify permissions on that host.

## 15. Other Docker-Compatible Engines

### 15.1. Podman

Spring Boot 3.5 supports communicating with Podman when a Docker-compatible API is properly configured. A rootless Podman socket usually has a user-scoped path, for example:

~~~text
unix:///run/user/1000/podman/podman.sock
~~~

The number 1000 is only an example UID; the actual path must be checked on the host. The Podman CLI can help:

~~~bash
podman info --format '{{.Host.RemoteSocket.Path}}'
~~~

If the socket/service is not started or the user lacks permissions, the Spring Boot plugin will fail. Some Podman setups require `bindHostToBuilder=true` to expose the daemon endpoint to the CNB builder. Check the docs and builder logs instead of applying that option to every engine.

### 15.2. Colima

On macOS, Colima provides a Docker-compatible context/socket. When `docker context ls` lists a `colima` context and Colima is running:

~~~bash
docker context inspect colima
docker --context colima info
~~~

Then set the corresponding Docker context/env for Maven/Gradle. Do not copy a fixed Unix socket path between two developers' machines.

### 15.3. Minikube and Remote Docker

Minikube can provide a Docker daemon inside a VM. When using `minikube docker-env` or a remote context, the application image is built **inside Minikube's daemon**, and will not automatically appear in local Docker Desktop. TLS certs, endpoint, image platform, and network must be compatible.

With a remote Docker daemon over TCP/TLS, verify connectivity from Maven/Gradle **and** related buildpack operations, not just SSH reachability to the server. API permissions and image registry traffic must also be managed.

## 16. Checking in CI: Probe the Exact Process That Builds

### 16.1. Maven Preflight Script (Linux Shell)

Assumes the runner **already has JDK, Docker CLI, daemon API, and a project-provided Maven Wrapper**, so the script does not install tools itself:

~~~bash
set -eu

java -version
./mvnw -version
docker context show
docker version
docker info --format '{{.OSType}}/{{.Architecture}}'

./mvnw -B -ntp clean verify
./mvnw -B -ntp spring-boot:build-image

docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

The earlier hand-created Maven example **did not include a Wrapper by default**, so this script is a CI template for repositories that already generated/committed `mvnw`. If there is no Wrapper yet, use an installed Maven of a controlled version.

### 16.2. Gradle Preflight Script

~~~bash
set -eu

java -version
./gradlew --version
docker version
docker info --format '{{.OSType}}/{{.Architecture}}'

./gradlew --no-daemon clean test bootJar
./gradlew --no-daemon bootBuildImage

docker image inspect cnb-connect-gradle:1.0.0
docker run --rm cnb-connect-gradle:1.0.0
~~~

CI must use the **same daemon** throughout the build and inspect steps. Do not call `docker context use` in one step and implicitly expect another job/container to pick up the change; configure context/host in the runner configuration.

### 16.3. Runner Models

| Runner | Where does the Docker daemon usually live? | Risks to check |
| --- | --- | --- |
| Linux VM self-hosted | Local `dockerd` system service | Permissions, disk, lifecycle |
| Docker Desktop self-hosted | Desktop VM/WSL backend | User session, Linux containers mode |
| Job container + host Docker socket | Host daemon outside the container | Mounting socket grants high host privileges |
| Docker-in-Docker (DinD) | Service container with its own daemon | TLS, privileged mode, network, cache |
| Remote API daemon | Dedicated VM/host | TLS, firewall, certificates, host path semantics |
| Rootless Docker/Podman | Per-user daemon/separate socket | UID, socket lifetime, CNB compatibility |

**Unencrypted TCP port 2375 is not recommended** for any CI simply for convenience. If an organization uses DinD or a remote daemon, runner isolation and TLS/auth per security standards are required to avoid giving untrusted PR code broad Docker host API privileges.

### 16.4. Separating Failures by Layer

~~~text
Layer 1: Java/compiler/test -> mvn clean verify / gradle clean test
Layer 2: Docker API         -> docker version / docker info
Layer 3: Container runtime  -> docker ps / docker run smoke
Layer 4: Registry           -> pull builder/run images
Layer 5: Buildpacks         -> detect / build / export logs
Layer 6: Image store        -> docker image inspect
Layer 7: App runtime        -> docker run + readiness/business tests
Layer 8: Publishing         -> registry auth/push/digest
~~~

One layer passing does not prove subsequent layers will pass; that is why CI should fail at the earliest step that clearly identifies the issue rather than wrapping everything in a single opaque build-image command.

## 17. Troubleshooting by Symptom

| Observed Error | Possible Cause | How to Confirm / Fix |
| --- | --- | --- |
| `docker: command not found` | CLI not installed / wrong PATH | Install valid Docker CLI/Engine, check PATH |
| `docker --version` OK, `docker version` missing Server | Daemon stopped, wrong context, endpoint unreachable | Start daemon, check context/socket |
| `Cannot connect to Docker daemon at unix:///var/run/docker.sock` | Socket missing or process cannot access it | Check daemon service, current context, rootless path |
| `permission denied while trying to connect to docker.sock` | User/group lacks API permissions | Grant approved permissions, do not chmod 666 |
| `sudo docker info` OK, normal fails | Daemon OK but ordinary user lacks socket permission | Review group/session/rootless options |
| Docker Desktop Windows running Windows containers | Paketo builder is a Linux image | Switch to Linux containers, check Docker Server OS |
| Host Docker OK but WSL/IDE Maven fails | Different process/home/socket/env | Test directly inside WSL/IDE runner process |
| `DOCKER_CONTEXT` and `DOCKER_HOST` differ | Env precedence points to wrong daemon | Keep one primary config source, check context inspect |
| Docker TLS handshake failure | CA/cert path, TLS endpoint, firewall | Check certificate/host/TLS, do not disable security |
| Docker TCP connection refused | Daemon not listening on endpoint or network blocked | Check server listeners/firewall/VPN |
| CLI `docker info` OK but Boot plugin fails | POM/Gradle docker context/host override or process env differs | Check plugin config, user, and runner environment |
| Pull builder image unauthorized | Registry requires credentials | Check image name, credential helper/`builderRegistry` |
| Pull builder image timeout | DNS/proxy/firewall/registry rate limit | Test `docker pull` on exact image, check daemon network |
| `no matching manifest for linux/...` | Image architecture/OS incompatible | Choose compatible builder/platform and daemon mode |
| Builder runs but Java download fails | CNB builder network/CA/proxy | Check lifecycle logs and builder env |
| Build fails on volume/cache mount | Disk, user rights, remote path mismatch | Check `docker system df`, named volumes/bind mounts |
| Maven Java tests fail before image build | Source/compiler/dependency error | Fix `mvn clean verify` before Docker |
| Gradle `bootBuildImage` task missing | Java/War or Boot plugin not applied properly | Check Gradle plugins and `tasks` |
| Image build succeeds but `docker image ls` doesn't show it | Docker CLI looking at different daemon | Compare plugin and CLI context/`DOCKER_HOST` |
| Image exists but `docker run` reports ClassNotFound | App packaging/classpath issue | Run `java -jar`, check dependencies/Boot JAR |
| Publish fails `denied` after local build OK | Registry push credentials/permissions | Check `publishRegistry`/login/tag, do not change daemon |
| Docker socket mounted into untrusted PR job | Weak security isolation | Use trusted isolated runner/remote managed build service |
| CI build slow on every job | Ephemeral daemon loses image/cache volumes | Consider image/volume caching per policy |
| `docker buildx` works but CNB fails | Buildx does not validate plugin API | Diagnose `bootBuildImage` Docker context and Engine API |

### 17.1. Five-Step Debugging Workflow

**Step 1:** Identify which **terminal, IDE, WSL distro, container, or CI job** is actually running Maven/Gradle.

**Step 2:** Check which daemon **Docker context/env/plugin config** points to; do not change multiple endpoints at once.

**Step 3:** Run `docker version` (checking Server), `docker info`, and `docker ps` in the corresponding environment; if they fail, fix the daemon API first.

**Step 4:** If API checks pass, read the build-image log to see whether failure occurs at registry pull, builder lifecycle, cache, export, or publishing.

**Step 5:** Once the image builds, use the **same context** with the exact name/tag to run `docker image inspect` and `docker run`, verifying Java app output and real runtime behavior.

## 18. Exercises with Answers

**Exercise 1 — CLI installed but daemon unconfirmed.** `docker --version` prints a version, `docker version` shows only Client.  
**Answer:** Not connected to daemon; check service, context, socket, TLS/permissions. Do not edit Java source yet.

**Exercise 2 — Docker context precedence.** `DOCKER_CONTEXT` points to a remote daemon, `DOCKER_HOST` points to the local Unix socket.  
**Answer:** Spring Boot 3.5 docs specify `DOCKER_CONTEXT` takes precedence. Keep a single consistent endpoint source.

**Exercise 3 — Maven tests pass but build-image fails.**  
**Answer:** Tests exercise the Java build/test path; CNB image build adds daemon, builder, registry, and container lifecycle. Probe `docker version`/`info` first.

**Exercise 4 — Linux user permission.** `sudo docker info` works while `docker info` fails.  
**Answer:** Ordinary user lacks socket permission; handle account/runner permissions per security policy, do not chmod 666.

**Exercise 5 — Windows Linux containers.** Docker Desktop runs Windows containers, Paketo builder pull reports OS mismatch.  
**Answer:** Switch to Linux containers mode and check Server OSType/architecture.

**Exercise 6 — Remote image store.** Maven builds the image successfully on a remote daemon, but local Docker Desktop does not show it.  
**Answer:** Daemons have separate stores. Inspect/run with the remote context or publish/pull via registry.

**Exercise 7 — Registry auth differs from daemon auth.** `docker info` passes, pulling builder fails `unauthorized`.  
**Answer:** Docker API is reachable; check builder registry credentials/permissions and `docker.builderRegistry`, do not change `DOCKER_HOST`.

**Exercise 8 — Maven vs Gradle command.** Which standard commands does Spring Boot use?  
**Answer:** Maven `spring-boot:build-image`; Gradle `bootBuildImage`. Both use CNB and require no Dockerfile.

**Exercise 9 — Demo project output.** When running the sample Maven or Gradle image successfully, what does the Java code print?  
**Answer:** `CNB_DAEMON_OK`, in addition to other startup logs.

**Exercise 10 — Docker socket on untrusted CI.** Should `/var/run/docker.sock` be mounted for every PR job?  
**Answer:** No. The Docker API carries very high privileges; use isolated/trusted runners or managed container build infrastructure.

## 19. Environment Acceptance Checklist

- [ ] Java/toolchain is appropriate; Maven/Gradle project compiles and tests pass first.
- [ ] Docker Engine/Desktop/container engine daemon is actually running.
- [ ] `docker version` shows **Server**, not just `docker --version`.
- [ ] `docker info` and `docker ps` pass under the **user/job running the build**.
- [ ] Docker context and `DOCKER_CONTEXT`/`DOCKER_HOST`/`DOCKER_CONFIG` are consistent.
- [ ] No POM/Gradle `docker.context` or `docker.host` override points to the wrong daemon.
- [ ] Docker Desktop on Windows uses Linux containers with Linux builders.
- [ ] Engine has sufficient resources and permissions to create containers, images, and cache volumes.
- [ ] Pull path to builder/run images or a proper registry proxy/cache is available.
- [ ] Registry credentials/proxy/TLS trust are managed separately from Docker daemon access.
- [ ] Remote Docker API uses TLS and firewall; TCP 2375 is not exposed publicly.
- [ ] Docker socket is not exposed to untrusted users/jobs.
- [ ] `spring-boot:build-image` or `bootBuildImage` runs from the right project/build tool.
- [ ] Final image is verified via `docker image inspect` on the same daemon.
- [ ] `docker run --rm` starts the app; demo prints `CNB_DAEMON_OK`.
- [ ] CI logs sufficient version/context/error-phase info for diagnostics.
- [ ] `docker system prune -a --volumes` is not used as a generic troubleshooting step.
- [ ] Policy exists to pin builder/runtime images, scan, and record image digests on release.

## 20. Official Sources

- Spring Boot 3.5 Maven — Packaging OCI Images and Docker Daemon: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Spring Boot 3.5 Gradle — Packaging OCI Images, bootBuildImage: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html
- Spring Boot Wiki — Building OCI Images, Docker-compatible engines: https://github.com/spring-projects/spring-boot/wiki/Building-OCI-Images-with-Spring-Boot
- Docker CLI Reference — context/host/environment options: https://docs.docker.com/reference/cli/docker/
- Docker Contexts: https://docs.docker.com/engine/manage-resources/contexts/
- Docker Context Use: https://docs.docker.com/reference/cli/docker/context/use/
- Docker Engine Linux post-install and permissions: https://docs.docker.com/engine/install/linux-postinstall/
- Docker Desktop Windows installation: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker Engine daemon socket: https://docs.docker.com/reference/cli/dockerd/#daemon-socket-option
- Cloud Native Buildpacks documentation: https://buildpacks.io/docs/
- Paketo Buildpacks: https://paketo.io/docs/

**Conclusion:** For Spring Boot to build an OCI image with Buildpacks, the **Maven/Gradle process must be able to access a Docker-compatible daemon**, not merely have the Docker CLI on PATH. A reliable verification chain is `docker version` showing Server → `docker info` under the right user/context → plugin `build-image`/`bootBuildImage` → `docker image inspect` → `docker run`. On failure, categorize errors across API, permissions, registry, builder lifecycle, and app runtime instead of randomly changing Java configuration or Docker endpoints.