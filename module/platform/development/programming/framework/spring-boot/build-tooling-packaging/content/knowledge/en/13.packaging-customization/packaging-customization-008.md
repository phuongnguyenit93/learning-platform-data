# Creating a Fully Executable Archive with a Launch Script on Compatible Operating Systems

## 1. Purpose and key distinctions

A Spring Boot application packaged by Maven or Gradle as an executable JAR can be run with:

~~~bash
java -jar my-app.jar
~~~

However, some Linux servers and SysV `init.d` deployment workflows want to invoke the file directly as an executable program:

~~~bash
./my-app.jar
~~~

Spring Boot provides a **fully executable archive** for this purpose. When enabled in Maven or Gradle, the build plugin **prepends a shell launch script to the start of the JAR/WAR**. On compatible Unix systems, the OS reads the **shebang**, runs the script, and the script starts the JVM with the packaged application. This technique also integrates with `init.d`-style service scripts supporting **start, stop, restart, and status** commands.

**A fully executable JAR is not a Native Image or a standalone `.exe`.** Beneath the script prefix lies a Java archive with **BOOT-INF/classes**, **BOOT-INF/lib**, and the Spring Boot Loader. It still requires a compatible Java runtime. Do not default to this JAR format for Windows, every Unix-like OS, systemd, Docker, or standard ZIP tools.

Lesson objectives:

- Understand what is required for **./app.jar** to run, and how it differs from **java -jar app.jar**.
- Build a fully executable artifact using **spring-boot-maven-plugin** and the **Spring Boot Gradle Plugin**.
- Run a Java 17 example with an HTTP endpoint and inspect the built artifact.
- Distinguish **mode=auto**, **MODE=run**, **MODE=service**, **init.d**, and **systemd**.
- Customize the embedded script at build time and configure Java/process options at runtime.
- Recognize limitations with **Windows**, **macOS**, **FreeBSD**, **ZIP64**, **jar -xf**, and container images.
- Handle execute permissions, JDKs, users, PIDs, logs, and security during deployment.

## 2. Executable JAR vs. fully executable JAR

| Type | Has Spring Boot Loader? | Has shell script prefix? | Primary launch method |
| --- | --- | --- | --- |
| Plain JAR | Not necessarily | No | External classpath, or `java -jar` if manifest fits |
| Spring Boot executable JAR | Yes | No | **java -jar app.jar** |
| Spring Boot fully executable JAR | Yes | **Yes** | **./app.jar** on compatible Unix once executable bit is set |

A standard Boot executable JAR looks like:

~~~text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/app/...
    ├── classes/application.properties
    └── lib/
        ├── spring-boot-....jar
        ├── spring-context-....jar
        └── ...
~~~

In a fully executable archive, **all of the above remains**, positioned after a **shell script** at the beginning of the file:

~~~text
app.jar (fully executable)
+--------------------------------------+
| #!/bin/...                           |
| Spring Boot shell launch script      |
+--------------------------------------+
| JAR/ZIP data                         |
| META-INF/MANIFEST.MF                 |
| BOOT-INF/classes/...                 |
| BOOT-INF/lib/*.jar                   |
| Spring Boot Loader classes           |
+--------------------------------------+
~~~

When a user runs **./app.jar**, the OS runs the shell snippet per its shebang; the script locates Java, applies runtime settings, and starts the app. Only then does the **Spring Boot Loader** handle loading classes from nested JARs inside the archive.

### 2.1. Launch script vs. Boot Loader

The **Launch script** runs at the OS layer, before the JVM. It handles `JAVA_HOME`, `JAVA_OPTS`, process modes, or `init.d` controls.

The **Boot Loader** is Java code inside the archive, running inside the JVM and understanding Spring Boot's nested JAR format. It resolves classes in **BOOT-INF/classes** and libraries in **BOOT-INF/lib**. **Application main()** then calls `SpringApplication.run` to initialize the Spring context.

~~~text
./app.jar
   |
   v
OS + embedded shell script
   |
   v
Java process / JVM
   |
   v
Boot Loader + classloader
   |
   v
Application.main(args)
   |
   v
SpringApplication.run(...) -> server/job
~~~

Never assume the script constructs a Java classpath independently of the Boot Loader, nor that enabling the shell prefix compensates for a missing or outdated JDK.

### 2.2. Why must this feature be opted into explicitly?

The script adds bytes **before the ZIP payload**. Some archive tools reject JARs with such a preamble. Spring Boot warns that **jar -xf** may silently fail to extract a fully executable archive. That is why **executable** defaults to **false** in the Maven Plugin, and Gradle requires calling **launchScript()** explicitly.

**Selection rule:** enable only when you genuinely need **direct execution** of a JAR/WAR via launch script on a supported OS. If your goal is **`java -jar`**, deploying to a servlet container, or building an OCI image, a standard executable Spring Boot JAR carries fewer compatibility risks.

## 3. Which operating systems and deployment models fit?

| Platform | Sensible option | Notes |
| --- | --- | --- |
| Linux direct shell execution | Fully executable JAR + `chmod` + `MODE=run` | Requires shell, Java, and filesystem allowing execute |
| Linux SysV `init.d` | Fully executable JAR + `init.d` symlink | Documented Spring Boot use case; protect user/PID/logs |
| Linux `systemd` | Standard Boot JAR + `systemd` unit calling `java -jar` | Usually no need to embed a launch script |
| Docker/Kubernetes | Standard Boot JAR + JVM entrypoint | Avoid breaking archive readers or image tooling |
| Windows CMD/PowerShell | Standard JAR + `java -jar` or WinSW service | Unix launch script is not an `.exe` |
| macOS, FreeBSD | Standard JAR or tested custom launch script | Default script is not guaranteed on these OSes |
| WAR deployed to servlet container | Standard container-compatible WAR | Do not prepend shell script if container/tooling dislikes it |

Per Spring Boot 3.5 guidance, the **default embedded launch script** supports many Linux distributions and has been tested on Ubuntu and CentOS. Platforms such as macOS and FreeBSD require a **custom script** if using direct execution. This is a limitation of **shell/OS utilities**, not that Spring Boot Java apps fail to run on macOS.

### 3.1. Fully executable does not mean "runs everywhere"

Windows has no native mechanism using a Unix shebang to invoke **./app.jar** directly in CMD or PowerShell. A fully executable JAR built on Windows must still be transferred to a compatible environment to use the script prefix.

A Linux container may mount filesystems as **`noexec`**, use a minimal shell missing expected interpreters, or lack a JRE altogether. In distroless images with no shell, **`java -jar` on a standard JAR** is generally the right choice.

Some services only need **`java -jar`** under `systemd`; adding a launch script there adds no value while complicating ZIP inspection tooling.

## 4. Spring Boot Java 17 hands-on exercise

To prove the launch script actually boots the application, we write a small HTTP service with a **/launch-check** endpoint. The Java code is shared across Maven and Gradle; learners **choose only one** build configuration.

Examples use Spring Boot **3.5.16** and Java **17** for explicit version pinning. In active projects, pick a supported Spring Boot branch and JDK per organizational policy; do not treat these illustrative versions as an upgrade mandate.

### 4.1. File structure

~~~text
launch-demo/
├── pom.xml                       (if choosing Maven)
│   or
├── build.gradle                  (if choosing Gradle)
├── settings.gradle               (if choosing Gradle)
├── mvnw, mvnw.cmd, .mvn/wrapper/...
│   or
├── gradlew, gradlew.bat, gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/launchdemo/
    │   │   ├── LaunchDemoApplication.java
    │   │   └── LaunchController.java
    │   └── resources/application.properties
    └── test/java/com/example/launchdemo/
        └── LaunchControllerTests.java
~~~

Maven Wrapper and Gradle Wrapper must be generated via Spring Initializr or wrapper commands; merely writing a POM or build script does not create **mvnw** or **gradlew**.

### 4.2. Main class

**src/main/java/com/example/launchdemo/LaunchDemoApplication.java**:

~~~java
package com.example.launchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LaunchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LaunchDemoApplication.class, args);
    }
}
~~~

### 4.3. Controller

**src/main/java/com/example/launchdemo/LaunchController.java**:

~~~java
package com.example.launchdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LaunchController {
    @GetMapping("/launch-check")
    public String launchCheck() {
        return "fully-executable-ok";
    }
}
~~~

### 4.4. `application.properties`

**src/main/resources/application.properties**:

~~~properties
spring.application.name=launch-demo
server.port=8080
~~~

If port 8080 is occupied, pass **`--server.port=9090`** at runtime to override the port, and adjust your test URL accordingly.

### 4.5. Unit/integration-style HTTP test

**src/test/java/com/example/launchdemo/LaunchControllerTests.java**:

~~~java
package com.example.launchdemo;

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
class LaunchControllerTests {
    @Autowired
    private MockMvc mvc;

    @Test
    void endpointReturnsExpectedText() throws Exception {
        mvc.perform(get("/launch-check"))
                .andExpect(status().isOk())
                .andExpect(content().string("fully-executable-ok"));
    }
}
~~~

This test verifies the Spring endpoint works on the test classpath. It **does not prove** the shell script runs on Linux, because tests are launched via Maven/Gradle's own classpath. You must execute the artifact via **./file.jar** to test direct execution.

## 5. Maven: enable the launch script prefix with `executable=true`

### 5.1. Complete `pom.xml`

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
    <artifactId>launch-demo</artifactId>
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
                    <executable>true</executable>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The decisive setting is:

~~~xml
<executable>true</executable>
~~~

The **Spring Boot Maven Plugin** runs **repackage** to create the Boot executable archive and prepends the embedded launch script when `executable` is enabled. When inheriting **spring-boot-starter-parent**, the **repackage** execution is preconfigured, so declaring the plugin suffices.

If not inheriting the starter parent, declare the plugin version and bind the `repackage` execution explicitly. Setting **`executable=true`** on a plugin that never runs **does not produce** a fully executable artifact.

### 5.2. Run the build

On Linux/macOS at project root:

~~~bash
./mvnw --version
./mvnw clean verify
~~~

**verify** includes `package` in Maven's default lifecycle; with the POM above and passing tests, the expected output is:

~~~text
target/launch-demo-1.0.0.jar
~~~

This is the repackaged Maven artifact. **`mvnw.cmd`** builds on Windows, though direct shell-prefix execution must still be tested on a compatible Unix OS. A passing Maven build does not imply the Linux target host has Java or execute permissions configured.

### 5.3. Inspect effective Maven config

If the artifact lacks a shell prefix despite editing the POM:

~~~bash
./mvnw help:effective-pom
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

In the effective POM, look for **spring-boot-maven-plugin**, configuration **`executable`**, goal **repackage**, and active profiles. Plugin declarations and executions differ: **`pluginManagement`** only sets defaults and does not guarantee the goal is bound to run.

**Avoid invoking `spring-boot:repackage` standalone** if the source JAR has not been packaged yet; `repackage` operates on an existing archive.

## 6. Gradle: invoke `bootJar.launchScript()`

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'launch-demo'
~~~

### 6.2. Complete Groovy DSL `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    launchScript()
}
~~~

**launchScript()** instructs the Spring Boot Gradle Plugin to prepend the default launch script during **bootJar**. It **does not** create a Windows EXE, does not add scripts to every Gradle JAR task, and does not replace Spring Boot's nested-JAR classloader.

This sample uses **io.spring.dependency-management** to apply Spring Boot's managed dependency versions. When opting for native Gradle BOM support instead, configure **`platform(...)`** and classpaths properly; never drop dependency versions without an active BOM mechanism.

### 6.3. Build with Gradle

With a compatible Gradle Wrapper, e.g., Gradle **8.14** within the range supported by Spring Boot 3.5:

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

The artifact path is normally:

~~~text
build/libs/launch-demo-1.0.0.jar
~~~

If project name, version, or **`bootJar.archiveFileName`** changes, the path changes accordingly. Verify the exact **`bootJar`** output instead of mistaking it for the plain JAR from `jar`.

### 6.4. Kotlin DSL equivalent

In a project already using **`build.gradle.kts`**, the snippet enabling the script is:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    launchScript()
}
~~~

This is only the addition inside `build.gradle.kts`, **not the entire `build.gradle.kts` file**. Convert plugins, dependencies, and toolchain declarations to Kotlin DSL syntax as well. Never paste Groovy `tasks.named('bootJar')` verbatim into a Kotlin DSL file.

## 7. Direct execution on Linux

After transferring the artifact from CI or your build machine to a compatible Linux host, locate the exact file. With the Maven example:

~~~bash
ls -l target/launch-demo-1.0.0.jar
head -n 1 target/launch-demo-1.0.0.jar
chmod +x target/launch-demo-1.0.0.jar
~~~

For Gradle, replace **`target/`** with **`build/libs/`**.

**head -n 1** should display a shebang line starting with **#!** from the embedded script; the exact interpreter depends on Boot version and custom scripts. **`chmod +x`** grants execute permission on the filesystem. If an artifact passed through an artifact repository or Windows filesystem, execute bits may be stripped—always check permissions.

### 7.1. Foreground smoke test

With Maven:

~~~bash
MODE=run ./target/launch-demo-1.0.0.jar
~~~

With Gradle:

~~~bash
MODE=run ./build/libs/launch-demo-1.0.0.jar
~~~

**MODE=run** tells the default embedded script to run the process in the foreground without guessing service mode from symlink location. Once startup completes, open a second terminal:

~~~bash
curl http://localhost:8080/launch-check
~~~

**Exact response body** from source code:

~~~text
fully-executable-ok
~~~

You can pass Spring arguments, for example:

~~~bash
MODE=run ./target/launch-demo-1.0.0.jar --server.port=9090
~~~

and query **`http://localhost:9090/launch-check`**. This command targets the Maven path; for Gradle, adjust the path accordingly.

If the request fails, inspect startup logs, JDK, port bindings, and exceptions. Being able to execute the script **does not guarantee** the Spring `ApplicationContext` started successfully.

### 7.2. `MODE=auto`, `run`, and `service`

Per Spring Boot's default script:

| Mode | Meaning | When to use |
| --- | --- | --- |
| **auto** | Script tries to detect whether invoked via `init.d` or directly | Default when mode is not forced |
| **run** | Runs the application in the foreground | Dev smoke tests and foreground process supervisors |
| **service** | Enables `start`/`stop`/`status` service-script lifecycle behavior | Compatible Linux `init.d` |

An archive invoked through a symlink inside **`init.d`** is normally auto-detected in `auto` mode. Running **`./app.jar start`** in `run` mode **is not** necessarily interpreted like **`service app start`**. Spring Boot application arguments and script control commands are distinct contexts.

To stop the foreground test, press `Ctrl+C` in the running terminal. Avoid defaulting to **`kill -9`** when the app can perform a graceful shutdown.

### 7.3. Why isn't `java -jar` the primary pattern here?

Some Java launchers accept ZIP/JAR files with a shell prefix, yet Spring Boot advises enabling fully executable only when targeting **direct execution**, not for **`java -jar`** or servlet container deployment. A script prefix introduces discrepancies across ZIP and JDK utilities. When `java -jar` is your primary launch method, build a **standard Boot executable JAR without a script prefix**.

## 8. Customizing the embedded script at build time

Spring Boot's default script expands several variables at packaging time. Maven uses **`embeddedLaunchScriptProperties`**; Gradle uses **`launchScript { properties ... }`**.

### 8.1. Illustrative Maven XML

In a POM with `spring-boot-maven-plugin`, **replace** the plugin block from section 5 with:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <executable>true</executable>
        <embeddedLaunchScriptProperties>
            <initInfoShortDescription>Launch Demo Service</initInfoShortDescription>
            <logFilename>launch-demo.log</logFilename>
            <stopWaitTime>45</stopWaitTime>
        </embeddedLaunchScriptProperties>
    </configuration>
</plugin>
~~~

This snippet is **not a standalone POM**; it belongs inside **`build/plugins`**. Never add two duplicate plugin definitions expecting two separate artifacts. When inheriting the starter parent, `repackage` execution still runs via parent defaults.

**initInfoShortDescription** sets the `init.d` description; **logFilename** and **stopWaitTime** configure default script properties. **logFilename** controls the script's log file in `init.d` mode, **not** Spring Boot's runtime **`logging.file.name`** property.

### 8.2. Illustrative Gradle Groovy DSL

In **`build.gradle`**, replace the existing `bootJar` block with:

~~~groovy
tasks.named('bootJar') {
    launchScript {
        properties 'initInfoShortDescription': 'Launch Demo Service',
                   'logFilename': 'launch-demo.log',
                   'stopWaitTime': '45'
    }
}
~~~

This is a **variant** of **`launchScript()`**, so do not call `launchScript()` a second time. Properties are baked in when the task builds the shell prefix.

### 8.3. Illustrative Gradle Kotlin DSL

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    launchScript {
        properties(
            mapOf(
                "initInfoShortDescription" to "Launch Demo Service",
                "logFilename" to "launch-demo.log",
                "stopWaitTime" to "45"
            )
        )
    }
}
~~~

This task configuration replaces **`tasks.named('bootJar') { launchScript() }`** in the corresponding Kotlin DSL file.

### 8.4. Build-time vs. runtime

Properties substituted by the plugin modify the script **when creating the artifact**. Changing **initInfoShortDescription** requires rebuilding so the updated script enters the JAR. Runtime environment variables such as Java home, heap size, Spring profiles, or `RUN_ARGS` are supplied **when the process starts** and do not require rebuilding the artifact.

## 9. Configuring the launch script at runtime

The default script reads several environment variables or a **`.conf`** file.

| Variable | Effect |
| --- | --- |
| **MODE** | Selects `auto`/`run`/`service` |
| **JAVA_HOME** | Points to the Java directory instead of relying on `PATH` |
| **JAVA_OPTS** | JVM options such as `-Xmx512m` |
| **RUN_ARGS** | Arguments passed to the Spring Boot application |
| **RUN_AS_USER** | Selects the OS user in `service` mode |
| **PID_FOLDER** | Directory for the PID file in `init.d` mode |
| **LOG_FOLDER** | Directory for logs in `init.d` mode |
| **LOG_FILENAME** | Log filename in `init.d` mode |
| **STOP_WAIT_TIME** | Wait timeout when stopping the service, default 60 seconds |
| **APP_NAME** | Application name used by the script |
| **CONF_FOLDER** | Directory where the script looks for `.conf` files |
| **USE_START_STOP_DAEMON** | Option to use `start-stop-daemon` when available |

Per Spring Boot guidance, **PID_FOLDER, LOG_FOLDER, and LOG_FILENAME** apply only to **`init.d` services**; under `systemd`, configure PIDs and logging via the **`systemd` unit and service manager**.

Foreground run example with JVM options and Spring profile:

~~~bash
JAVA_OPTS='-Xms128m -Xmx512m' MODE=run RUN_ARGS='--spring.profiles.active=dev' ./target/launch-demo-1.0.0.jar
~~~

- **JAVA_OPTS** configures the JVM and does not set a Spring profile by itself.
- **RUN_ARGS** passes through to the Spring Boot application.
- **MODE** controls script process behavior.
- None of these variables supplies a JVM if Java is missing; a compatible JDK/JRE must be installed.

### 9.1. `.conf` configuration

For a JAR deployed at:

~~~text
/opt/launch-demo/launch-demo.jar
~~~

the default script checks for a config file in the same directory:

~~~text
/opt/launch-demo/launch-demo.conf
~~~

Shell-style example contents:

~~~bash
JAVA_OPTS=-Xmx512m
STOP_WAIT_TIME=45
~~~

**`.conf`** is not **`application.properties`**, and Spring `Environment` does not read it automatically. It configures the launch script. **JARFILE** and **APP_NAME** are two exceptions Spring Boot notes cannot be configured the same way inside `.conf`; set them through appropriate external mechanisms if truly needed.

**Critical security warning:** in a root-managed `init.d` context, `.conf` may be **sourced/evaluated by a shell running as root**. Never allow the application user or untrusted accounts write access to `.conf`. Spring Boot illustrates **`root:root`** ownership and **`400`** permissions for this setup.

### 9.2. Why never store secrets in the script?

Never hardcode DB passwords or API keys inside the **embedded script** or build-time properties: the JAR file can be extracted/read and persists in artifact repositories and build logs. Likewise, avoid blindly placing secrets in `JAVA_OPTS`/`RUN_ARGS`, where they can leak through process listings or logs.

Use your organization's secret distribution mechanism, strict file permissions, and runtime config injection. When storing settings in `.conf`, weigh shell-evaluation risks and `init.d` privilege boundaries.

## 10. Integrating an `init.d`/SysV service on Linux

**init.d** is Spring Boot's primary documented use case for fully executable archives. The commands below are **privileged administrative deployment examples**: use only on machines genuinely running SysV init or compatible mechanisms where you are authorized to manage services. Never run directly in production without a change and rollback plan.

### 10.1. Place the JAR in the service directory

Assuming a sysadmin already created user/group **launchdemo** and directory **`/opt/launch-demo`**, and the artifact is built and tested:

~~~bash
sudo cp target/launch-demo-1.0.0.jar /opt/launch-demo/launch-demo.jar
sudo chown launchdemo:launchdemo /opt/launch-demo/launch-demo.jar
sudo chmod 500 /opt/launch-demo/launch-demo.jar
~~~

For Gradle builds, copy from **`build/libs/`** instead of **`target/`**. This snippet **assumes the directory and user already exist**; it is not a full provisioning script.

**chmod 500** grants read and execute—without write—to the owner; Spring Boot docs show this to protect the artifact. Audit actual ownership, verify the runtime account cannot tamper with the file, and never run the application process as `root`.

### 10.2. Create the `init.d` symlink

~~~bash
sudo ln -s /opt/launch-demo/launch-demo.jar /etc/init.d/launch-demo
sudo service launch-demo start
sudo service launch-demo status
~~~

The default embedded script detects when it is invoked via a symlink inside **`init.d`** and supports **start/stop/restart/status**. When finished testing or needing to stop:

~~~bash
sudo service launch-demo stop
~~~

Before creating the symlink, verify the service name is unused and the distro supports this behavior. On `systemd`-based Linux, **`service`** may only be a compatibility shim and is not the preferred modern service interface.

`init.d` scripts normally write PIDs and console logs to configured paths defaulting under **`/var/run`** and **`/var/log`**. Ensure directory permissions allow it. If service startup fails, inspect those log paths and PID/LOG variables instead of assuming startup succeeded just because the shell command returned quietly.

### 10.3. Which user does it run under?

When invoked by root in service mode, Spring Boot's default script runs the application under **`RUN_AS_USER`**, or falls back to the user owning the JAR if unset. Never set **`RUN_AS_USER=root`**, and never configure the artifact so the Spring Boot app runs with root privileges.

Spring Boot documentation also recommends creating an account without a login shell and locking down both the JAR and `.conf` files. A compromised Java process must not be able to modify its own binary or startup configuration to escalate privileges on the next service restart.

### 10.4. Do not enable boot autostart unconditionally

Some Debian/SysV systems use **`update-rc.d`** to enable startup on boot. That is a separate administrative step to perform only after verifying start/stop, security, log rotation, and rollback. Do not assume a freshly built fully executable archive is automatically registered as a system service on the target host.

## 11. `systemd`: in most cases a fully executable archive is unnecessary

On Linux systems using **`systemd`**, Spring Boot advises creating a unit file invoking a **standard Boot executable JAR** via **`java -jar`**. `systemd` handles process lifecycle, restarts, and stdout/stderr logging, eliminating the need for `init.d` launch-script PID/log handling.

Sample unit at **`/etc/systemd/system/launch-demo.service`**:

~~~ini
[Unit]
Description=Launch Demo Spring Boot
After=network.target

[Service]
Type=exec
User=launchdemo
Group=launchdemo
WorkingDirectory=/opt/launch-demo
ExecStart=/usr/bin/java -jar /opt/launch-demo/launch-demo.jar
SuccessExitStatus=143
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

This is a **sample unit** for a **standard executable Spring Boot JAR**. Ensure **`/usr/bin/java`** exists on the host, the JDK meets requirements, user/group exist, and the artifact is readable. Do not configure **`RUN_AS_USER/PID_FOLDER/LOG_FOLDER`** when `systemd` already owns those responsibilities.

Administrative commands (with privileges):

~~~bash
sudo systemctl daemon-reload
sudo systemctl start launch-demo.service
sudo systemctl status launch-demo.service
sudo journalctl -u launch-demo.service --no-pager -n 50
~~~

Enabling **`systemctl enable`** to auto-start on reboot is a separate operational decision.

### 11.1. Can `systemd` invoke a fully executable JAR?

It can, if justified and tested on the exact distro and script. For instance, a unit snippet using **`MODE=run`** so the script stays in the foreground for `systemd` process tracking:

~~~ini
[Service]
Type=exec
User=launchdemo
Group=launchdemo
WorkingDirectory=/opt/launch-demo
Environment=MODE=run
ExecStart=/opt/launch-demo/launch-demo.jar
Restart=on-failure
~~~

This is an **alternative snippet**, not a complete unit; it assumes a fully executable JAR with a valid shebang and execute bit. For a new `systemd` service, a standard JAR + **`ExecStart=java -jar`** is simpler and plays better with ZIP/JAR tooling.

## 12. Windows, macOS, FreeBSD, and containers

### 12.1. Windows

A Unix shell shebang does not convert a JAR into an **`.exe`** binary. Windows CMD and PowerShell do not use Unix shebangs to execute **./app.jar** directly. Use a standard Boot JAR with:

~~~powershell
java -jar .\launch-demo.jar
~~~

For a Windows service, Spring Boot docs recommend **WinSW** (Windows Service Wrapper) or an appropriate service wrapper. Never enable **`executable=true`** expecting Windows Service Manager to recognize a JAR natively as a service.

### 12.2. macOS and FreeBSD

These OSes provide shells, yet differ from the Linux conventions and utilities the default Spring Boot launch script is tested against. Per Spring Boot, direct execution on macOS/FreeBSD needs an appropriate **custom launch script**, or simply a standard JAR run with **`java -jar`**. Working in a Linux terminal does not prove compatibility across all Unix-like OSes.

### 12.3. Docker/OCI and Kubernetes

Containers normally run a foreground process so orchestrators can track health, restart, collect logs, and deliver signals. Example Dockerfile for a **standard Boot JAR**:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is illustrative; pin images and JDKs per production policy. In many pipelines, Spring Boot layered archives and OCI image builders parse ZIP/JAR structures, where a script prefix can break readers. Enable fully executable only when specifically needed and tested on your image/toolchain; otherwise default to a standard Boot JAR.

## 13. ZIP tools and ZIP64 limitations

### 13.1. Why can `jar -xf` fail to extract?

A fully executable archive starts with shell script bytes instead of a standard ZIP/JAR signature. Some ZIP tools still locate the ZIP directory, yet **not all tools support this**. Spring Boot explicitly warns that **`jar -xf`** may silently fail.

Therefore:

~~~bash
jar xf target/launch-demo-1.0.0.jar
~~~

**should not be relied on as the sole test** of a fully executable archive. It can also scatter extracted files into the current working directory. When inspecting entries, use a format-aware reader or build an additional **standard Boot JAR** to verify `BOOT-INF`/manifest structure.

### 13.2. At which level does ZIP64 matter?

Per the Spring Boot 3.5 specification, **an outer JAR in ZIP64 format cannot be made fully executable**; prepending a script can cause it to be reported as corrupt at runtime. However, a **standard-format outer JAR** can still contain a ZIP64 nested JAR inside.

Never generalize that "Spring Boot does not support ZIP64"—the restriction applies specifically to **fully executable outer archives**. For applications large enough to require ZIP64 at the outer JAR level, pick another packaging strategy rather than prepending a shell script.

## 14. Replacing the default script with a custom launch script when genuinely needed

Spring Boot accepts a user-supplied script file when the default script does not fit. Maven Plugin provides **`embeddedLaunchScript`**, and Gradle Plugin provides **`launchScript { script = file(...) }`**.

Maven excerpt:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <executable>true</executable>
        <embeddedLaunchScript>src/launch/launch.sh</embeddedLaunchScript>
    </configuration>
</plugin>
~~~

Gradle excerpt:

~~~groovy
tasks.named('bootJar') {
    launchScript {
        script = file('src/launch/launch.sh')
    }
}
~~~

**This configures a pointer to a script file**, not a self-contained runnable setup. **`src/launch/launch.sh`** must exist, start with a valid shebang, and contain startup logic tested on the target OS. If the custom script needs **start/stop/restart/status**, user switching, signals, PID files, logging, and exit codes, you must implement and verify all of that yourself.

Do not paste a one-liner **`exec java -jar "$0"`** assuming it works across every prefixed JAR and JDK. Compatibility of Java/ZIP readers with prefixed archives is not guaranteed like a standard JAR. Whenever the default script fits your needs, customizing **`embeddedLaunchScriptProperties`** or **`launchScript.properties`** is much safer than rewriting the whole launch logic.

## 15. Inspecting the artifact post-build without corrupting the archive

### 15.1. Verify shell prefix and file permissions

With Maven:

~~~bash
test -s target/launch-demo-1.0.0.jar
head -n 1 target/launch-demo-1.0.0.jar
ls -l target/launch-demo-1.0.0.jar
~~~

For Gradle replace with **`build/libs/launch-demo-1.0.0.jar`**. Indicators:

- **`test -s`**: file exists and is non-empty.
- **`head -n 1`**: first line begins with **`#!`** if the launch script is embedded properly.
- **`ls -l`**: file permissions on the current filesystem. If lacking execute permission, run **`chmod +x`** where permitted.

You can use **`file`** to inspect file type, though its output varies by magic database version; never treat a specific `file` string as a strict standard.

### 15.2. Functional runtime verification

~~~bash
MODE=run ./target/launch-demo-1.0.0.jar --server.port=9090
~~~

In another terminal:

~~~bash
curl --fail http://localhost:9090/launch-check
~~~

Exact response body:

~~~text
fully-executable-ok
~~~

This uses the Maven path; for Gradle adjust the JAR path. **`curl --fail`** fails on HTTP response codes >=400, yet you should still inspect the body, logs, and environment conditions.

### 15.3. Verify the deployed file's checksum

~~~bash
sha256sum target/launch-demo-1.0.0.jar
~~~

Checksums prove the file **did not change bytes** between CI and the target server. They do not prove script/JDK/OS compatibility or endpoint correctness. On Windows use **`Get-FileHash`**, and on macOS **`shasum -a 256`**.

## 16. Diagnostic table for common errors

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| **Permission denied** on `./app.jar` | Missing execute bit, `noexec` mount, or wrong owner | `ls -l`, valid `chmod +x`, check mount options |
| **Exec format error** | File lacks a shebang or script header is corrupt | `head -n 1`, verify Maven/Gradle packaging |
| **bad interpreter** | Shebang points to missing shell or has CRLF line endings | Check interpreter on target OS |
| First bytes of JAR are **PK** | Launch script not prepended, or checking wrong JAR | Verify `executable=true` / `bootJar.launchScript` |
| **java: command not found** | `JAVA_HOME`/`PATH` wrong for runtime user | Check `java -version`, user/service environment |
| **UnsupportedClassVersionError** | Java runtime too old | Select a JVM matching compiled bytecode and Spring Boot |
| **Port already in use** | Spring server cannot bind port | Change `server.port` or stop conflicting process |
| **`./app.jar start`** behaves unexpectedly | `MODE` is `run`/`auto`, not `service` | Check `MODE` and `init.d` symlink |
| Cannot write PID/log | Wrong default folder permissions | Check `PID_FOLDER`, `LOG_FOLDER`, user/group |
| **`service app start`** fails | Distro uses `systemd`, or `init.d` script misconfigured | Use an appropriate `systemd` unit, read logs |
| **`jar -xf`** shows no extracted contents | ZIP tool rejects shell prefix | Use a compatible reader or standard JAR |
| Scanner/OCI builder rejects JAR | Does not accept script-prefixed archive | Publish a standard Boot JAR |
| ZIP64 outer JAR corrupt | Fully executable outer ZIP64 is unsupported | Change packaging strategy |
| Windows refuses **`./app.jar`** | Unix shebang unsupported natively | Use `java -jar` and a Windows service wrapper |
| macOS/FreeBSD fails running script | Default script is tested only on specific Linux distros | Use a custom script or standard JAR |
| App boots then fails on bean/DB | Script and JVM worked; failure is inside Spring runtime | Read exception/stack trace/config |

**Layer your debugging:** Can OS execute the script → does script find Java → does Java open the archive → does Spring context boot → does the endpoint/job work? Isolate the layer before changing build scripts or OS settings.

## 17. Exercise comparing both packaging modes

Build two variants from the same Java source:

**Variant A — standard Boot executable JAR:**
- Maven removes **`executable=true`** to return to default `false`.
- Gradle omits **`launchScript()`**.
- Run with **`java -jar`** where compatible Java exists.
- Use for standard `systemd`, Windows, or OCI images.

**Variant B — fully executable Boot JAR:**
- Maven sets **`<executable>true</executable>`**.
- Gradle sets **`tasks.named('bootJar') { launchScript() }`**.
- On Linux, verify shebang, `chmod +x`, and run **`MODE=run ./app.jar`**.
- Where `init.d` is available, test service commands under appropriate user/permissions.

| Observation | A | B |
| --- | --- | --- |
| Shebang at start of file | No | Yes |
| `BOOT-INF/classes` and `BOOT-INF/lib` | Yes | Yes |
| Designed launch method | `java -jar` | Direct execution on compatible Unix |
| `jar -xf` compatibility like standard ZIP | Typical | Not guaranteed |
| Requires Java runtime | Yes | Yes |

Both variants serve **`fully-executable-ok`** from the same endpoint, differing only in how they launch. **Never let both variants overwrite each other under the same filename** in an artifact repository; assign distinct names/classifiers and test each.

## 18. Knowledge self-check

**Q1.** Is a fully executable JAR a native binary?

**Answer:** No. It is a Spring Boot executable archive with a prepended shell script prefix. A JVM still executes the bytecode inside.

**Q2.** Which options are used in Maven and Gradle?

**Answer:** Maven uses **`spring-boot-maven-plugin`** with **`<executable>true</executable>`**; Gradle uses **`bootJar.launchScript()`**.

**Q3.** Why might `chmod +x` be needed after building?

**Answer:** The file needs an execute bit on a Unix filesystem; execute permissions can be lost when stored or transferred through artifact stores or non-Unix filesystems.

**Q4.** Why can a fully executable JAR cause `jar -xf` to fail?

**Answer:** Because the archive starts with a shell script before the ZIP payload, and some JAR/ZIP tools do not handle such a preamble.

**Q5.** Is a fully executable JAR needed for `systemd`?

**Answer:** No. A standard Boot JAR with a unit running `ExecStart=java -jar` is supported by Spring Boot and usually simpler.

**Q6.** On Windows, can `./app.jar` replace `java -jar`?

**Answer:** Not via the default Unix launch script; use a standard JAR with `java -jar` or a service wrapper like WinSW.

**Q7.** Do `mode=run`, `service`, and `auto` differ?

**Answer:** Yes. `run` runs in the foreground, `service` handles `start`/`stop`/`status` service management, and `auto` tries to infer context. Never pass service commands like `start` expecting `run` mode to interpret them identically.

**Q8.** Is it safe to embed passwords in `embeddedLaunchScriptProperties`?

**Answer:** No. Build artifacts can be read and copied. In `init.d`, `.conf` files may also be sourced by a privileged shell; protect secrets using proper runtime policies.

**Q9.** Are ZIP64 outer JARs suitable as fully executable archives?

**Answer:** Per Spring Boot 3.5, no. A standard-format outer JAR containing a ZIP64 nested JAR is a different case that can still be supported.

## 19. Pre-deployment checklist

- [ ] Identified target OS and process manager: Linux direct, `init.d`, `systemd`, Windows, or container.
- [ ] Enabled fully executable only when **`./artifact.jar`** is genuinely required on a supported platform.
- [ ] Maven uses the proper **`repackage`** plugin/goal and **`executable=true`**; Gradle uses **`bootJar`** with **`launchScript()`**.
- [ ] Java runtime meets Spring Boot and compiler target requirements.
- [ ] Artifact has a shebang, exists, is non-empty, and has appropriate execute permissions.
- [ ] Direct smoke test **`MODE=run ./app.jar`** ran, not only Maven/Gradle unit tests.
- [ ] For `init.d`: checked user, symlink, PID/log paths, start/stop/status, and `.conf` security.
- [ ] For `systemd`: evaluated standard Boot JAR + **`ExecStart=java -jar`**.
- [ ] For Windows/macOS/FreeBSD: did not assume Linux scripts work out of the box.
- [ ] For OCI images/ZIP tools: avoided script prefix if tooling expects a standard archive.
- [ ] Avoided fully executable outer ZIP64 JARs.
- [ ] Verified checksum and artifact identity after transfer.
- [ ] Ensured runtime users cannot tamper with startup files against policy.
- [ ] Release gate still executes app tests and QA; shell startup never replaces verification.

**Conclusion:** A Spring Boot fully executable archive uses an **embedded launch script at the start of the JAR** to support direct invocation on compatible Unix hosts and **`init.d`** workflows. It fits specific targets well, yet is not ideal for every platform. For Windows, typical `systemd`, containers, or toolchains expecting standard JAR/ZIP files, prefer a **standard Spring Boot JAR launched via `java -jar`**. Above all, verify the script, permissions, Java runtime, and application behavior on the actual deployment OS.

## 20. Official documentation

- Spring Boot 3.5 — Installing Spring Boot Applications, systemd/init.d/launch scripts: https://docs.spring.io/spring-boot/3.5/how-to/deployment/installing.html
- Spring Boot 3.5 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Spring Boot 3.5 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — Maven Plugin Using: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- systemd.service — Configuration reference: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- Linux chmod manual: https://man7.org/linux/man-pages/man1/chmod.1.html