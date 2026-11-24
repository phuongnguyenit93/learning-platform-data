# Exposing Java, Operating System, and Process Information

## 1. Knowing Which Environment the Application Is Running In

The same JAR file can run properly on a developer's machine yet encounter problems after deployment: the server uses a different Java version than expected, a different processor architecture, or the operator is inspecting the wrong process. Before analyzing business-logic errors, you must determine the actual environment running the application.

In Spring Boot Actuator, the `info` endpoint collects pieces of information provided by components implementing `InfoContributor`. This lesson focuses on three built-in sources: `java`, `os`, and `process`. They answer three consecutive questions: **which Java is it running on → which OS does the JVM see → which process is this**.

| Info section | Question to answer | Example use case |
| --- | --- | --- |
| `java` | What is the running Java/JVM version and vendor? | Verify the runtime environment after changing deployment images |
| `os` | What OS name, version, and architecture does the JVM report? | Compare Windows/Linux or `amd64`/`aarch64` environments |
| `process` | What PID, parent process, running account, and available CPUs does the process have? | Correlate application info with operational tools |

This lesson uses **Spring Boot 3.3.x and JDK 21**. `ProcessInfoContributor` was added in Spring Boot 3.3.0; applications on older versions do not gain this feature merely by adding configuration properties. See the [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes).

## 2. Distinguishing Data Sources, Endpoint, and Access Permissions

All three sources `java`, `os`, and `process` are **disabled by default** in Spring Boot 3.3. To receive data over HTTP, three things must be distinguished:

1. Enable each source with `management.info.<id>.enabled`.
2. The `info` endpoint must be enabled and exposed over HTTP.
3. HTTP requests must be permitted by the security mechanism.

Enabling the `java` source does not automatically expose the URL. Conversely, exposing `info` does not automatically enable the three sources. Configuration and defaults are described in the [Spring Boot 3.3 endpoints documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info).

For the data flow, you can visualize:

```text
Java/JVM, operating system, current process
                  ↓
JavaInfoContributor + OsInfoContributor + ProcessInfoContributor
                  ↓
              InfoEndpoint
                  ↓
       GET /actuator/info → JSON
```

There is no need to write a custom Controller for this URL. Nor do you need to create `build-info.properties` or `git.properties` for these three sources to work; those files serve build/Git information.

## 3. Configuration to Observe in a Web Application

### 3.1. Example Prerequisites

Use a Spring Boot 3.3.x application with an existing startup class and web environment. With Gradle, ensure the following dependencies are in the `dependencies` block; versions are managed by the project's Spring Boot configuration:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This is an **additional configuration snippet**, not a complete standalone Gradle project. If the application already uses WebFlux, keep the existing `spring-boot-starter-webflux`; do not add MVC just to read `info`.

The HTTP examples below assume no custom context path, no upstream proxy, and no Spring Security. If the project has security enabled, use an account permitted to read the endpoint according to the project's policy.

### 3.2. Enabling Each Source Explicitly

In `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    java:
      enabled: true
    os:
      enabled: true
    process:
      enabled: true
```

In this local learning example, `server.address` binds the server to loopback. That is a choice for the example, not an Actuator requirement. When integrating into another application, merge the YAML keys with existing configuration; avoid creating two sibling `management` keys.

If using `application.properties`, the equivalent part to enable the three sources is:

```properties
management.info.java.enabled=true
management.info.os.enabled=true
management.info.process.enabled=true
```

These three lines only replace the `management.info` section in YAML; the endpoint and HTTP settings must still be kept. There is no need to enable `management.info.env.enabled` for this lesson.

### 3.3. Running and Calling the Endpoint

From the root directory of the example application with Gradle Wrapper, run on Windows:

```powershell
.\gradlew.bat bootRun
```

For macOS/Linux:

```bash
./gradlew bootRun
```

This is a command for a standalone application with a `bootRun` task; in a multi-module repository, use the task path of the module to run.

Once the application has started, open another terminal. On Windows, use `curl.exe` to avoid confusion with the PowerShell alias:

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/info
```

On macOS/Linux:

```bash
curl -i http://127.0.0.1:8080/actuator/info
```

A successful response has HTTP status `200`. The content below is **illustrative JSON**, not fixed values that must appear on your machine; key ordering is also not a test condition:

```json
{
  "java": {
    "version": "21.0.9",
    "vendor": {
      "name": "Microsoft"
    },
    "runtime": {
      "name": "OpenJDK Runtime Environment",
      "version": "21.0.9+10-LTS"
    },
    "jvm": {
      "name": "OpenJDK 64-Bit Server VM",
      "vendor": "Microsoft",
      "version": "21.0.9+10-LTS"
    }
  },
  "os": {
    "name": "Linux",
    "version": "6.8.0",
    "arch": "amd64"
  },
  "process": {
    "pid": 24580,
    "parentPid": 24410,
    "owner": "appuser",
    "cpus": 4
  }
}
```

If the project also has build/Git sources or custom contributors, the JSON may contain additional sections. Do not compare the entire response against the illustrative sample to conclude whether these three sources are right or wrong.

## 4. Reading the `java` Section Correctly

`java` describes the **environment currently running the application**. Spring Boot represents it via `JavaInfo`, including Java version, vendor, runtime environment, and virtual machine. This structure is described in [Spring Boot 3.3 JavaInfo](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/JavaInfo.html).

| Common path | Meaning |
| --- | --- |
| `java.version` | Java version reported by the running JVM |
| `java.vendor.name` | Java vendor |
| `java.vendor.version` | Vendor-specific version information, when available |
| `java.runtime.name`, `java.runtime.version` | Name and version of the runtime environment |
| `java.jvm.name`, `java.jvm.vendor`, `java.jvm.version` | Name, vendor, and version of the virtual machine |

Fields depend on JDK data; do not assume every vendor provides `vendor.version` or formats version strings the same way.

For instance, a project configured with Java toolchain 21 for compilation does not prove the HTTP-serving process runs on that same JDK. An IDE, OS service, or container image might launch the application with a different Java. When investigating, take the `java` section from the exact instance experiencing the issue.

Similarly, `java -version` in a terminal only describes the `java` command found by that terminal. Compare it against the application's runtime info before concluding both sides use the same JDK.

This information helps verify the environment; it does not prove the application has no compatibility bugs or needs no security updates.

## 5. Reading the `os` Section Correctly

`os` has three main fields in the Spring Boot 3.3 API:

| Field | Published information source |
| --- | --- |
| `os.name` | System property `os.name` |
| `os.version` | System property `os.version` |
| `os.arch` | System property `os.arch` |

This is how the JVM describes the operating system environment. The field structure is confirmed in the [Spring Boot 3.3 `info` API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html#actuator-api.info.response-structure).

When comparing deployment environments, use actual values instead of guessing from hostnames. For example, if two instances return `amd64` and `aarch64`, re-check the deployment image and native libraries used by the application.

In containers, also distinguish user-space OS image, kernel, and JVM view. From `os.name`/`os.version` alone you cannot infer the full distribution, container image version, or physical host specs. To know the image tag/digest, cross-check deployment records.

Do not use `os.arch` as a performance measure: two machines with the same architecture can still differ in allocated CPUs, memory limits, and current load.

## 6. Reading the `process` Section Correctly

### 6.1. Fields Present in Spring Boot 3.3

| Field | Meaning | How to use |
| --- | --- | --- |
| `process.pid` | Application process identifier | Correlate with the Java process being inspected |
| `process.parentPid` | Parent process PID; may be `-1` when undetermined | Identify which launcher started the application |
| `process.owner` | Reported account owning/running the process | Verify against the expected operational account |
| `process.cpus` | Number of processors available to the process according to the JVM | Check the process's view of resources |

This is the **Spring Boot 3.3** schema, not a list of every field in newer Spring Boot versions. Do not take `process.memory` or virtual-thread samples from another version's documentation and treat them as required 3.3 output.

### 6.2. PID Only Makes Sense in the Right Environment

An application may be started from an IDE, Gradle, a script, or a service manager. Therefore, the parent process is not necessarily your open shell. After a restart, the PID is not guaranteed to stay the same either.

Java provides `ProcessHandle` to identify the current process and query the parent process. A PID can be reused by the OS after a process terminates; hence do not use PID as a long-term business identifier. See [ProcessHandle in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html).

In a container or environment with PID namespace isolation, compare from the process's own perspective. Not seeing the container's PID `1` in the host process list the way you expected is not enough to conclude Actuator returned wrong data.

With multiple replicas behind a load balancer, two calls to the same URL can land on two different processes. To compare PIDs before/after, target the specific instance or use internal routing tools of the deployment environment.

### 6.3. Available CPUs Is Not CPU Utilization Percentage

`Runtime.availableProcessors()` returns the number of processors available to the JVM; the minimum value is `1` and it may change during the JVM's lifecycle. This is the visible resource count, not the busy CPU percentage. See [Runtime.availableProcessors() in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html#availableProcessors()).

For example, `process.cpus = 4` does not mean the application is using 4% CPU, nor does it prove the physical host has only four cores. If the number differs from expectations, inspect container limits, JVM options, and the execution environment; do not rush to change algorithms based solely on this value.

To monitor load, memory, or uptime over time, use an appropriate metrics system. Spring Boot integrates Micrometer for that set of needs; see the [Spring Boot 3.3 metrics documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 7. A Java Program to Observe Information Sources

The following program runs standalone without Spring. It helps reveal the data Java can query from the runtime environment. Save the exact content as `RuntimeProbe.java`:

```java
public class RuntimeProbe {
    public static void main(String[] args) {
        ProcessHandle current = ProcessHandle.current();

        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.version=" + System.getProperty("os.version"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("pid=" + current.pid());
        System.out.println("parentPid="
                + current.parent().map(ProcessHandle::pid).orElse(-1L));
        System.out.println("owner=" + current.info().user().orElse("unknown"));
        System.out.println("cpus=" + Runtime.getRuntime().availableProcessors());
    }
}
```

Compile and run with JDK 21:

```text
javac --release 21 RuntimeProbe.java
java RuntimeProbe
```

The output always follows the order of the nine lines written in the program; **the values vary by machine and run**. An illustrative example is:

```text
java.version=21.0.9
java.vendor=Microsoft
os.name=Linux
os.version=6.8.0
os.arch=amd64
pid=24620
parentPid=24410
owner=appuser
cpus=4
```

This is a new Java process, so this program's PID is not the PID of the Spring Boot application serving `/actuator/info`. To inspect the same process, observe from inside the application or match OS tools against the PID returned by the endpoint itself.

`parent()` and `user()` represent data that may be unavailable. The example intentionally uses `-1` and the string `unknown` as fallback values in the custom program; do not treat the string `unknown` as an output guarantee of every Actuator version. OS permissions can restrict process information that can be queried, as described in [ProcessHandle.Info in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html).

## 8. Proper Exposure Scope and Understanding Common Errors

Java vendor, OS version, PID, and running account details have operational value. When deploying to an environment, identify the intended readers and apply appropriate access permissions; do not expose all endpoints automatically just to see the `java` section.

For a need meant only for tools on the application host, you can separate the management port and restrict the listening address:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

This snippet is **merged** into the configuration in section 3; you then call `http://127.0.0.1:8081/actuator/info`. Spring Boot allows configuring a separate management server address when the management port differs from the application port. See [Spring Boot 3.3 management HTTP configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Restricting the address does not replace authentication/authorization policies. Conversely, merely moving to another port while still listening on a public network still does not define who is allowed to read.

| Symptom | Branch to inspect | Appropriate action |
| --- | --- | --- |
| HTTP `404` | Wrong port/path; endpoint not enabled or not exposed | Check endpoint config, exposure, context path, and management port |
| HTTP `401` or `403` | Authentication/authorization policy or intermediary layer denied access | Use valid credentials and check actual access rules |
| HTTP `200` without `java`/`os`/`process` | Corresponding sources not enabled or running config differs from expected | Check active profiles and the three `management.info.*.enabled` properties |
| Only `{}` | No contributor is currently contributing data | Check each source; do not equate an empty response with an HTTP error |
| Missing `process` on older Spring Boot | Version lacks the built-in contributor | Check version; do not keep changing exposure looking for a non-existent feature |
| No `process.memory` on 3.3 | Comparing against a different version's schema | Use documentation for the right version and appropriate metrics source |
| PID or CPU count differs from expected | Different instance, PID namespace, or resource limits | Verify exact process and environment before concluding |

The table above is an investigation guide, not the sole conclusion for every system. Proxies or custom security configurations may return different error codes.

Do not use `management.endpoint.health.show-details` to control the content of `info`: that property belongs to the `health` endpoint. Also do not assume `/env`'s data-masking rules automatically apply to all information in `/info`.

## 9. Hands-on Layer-by-Layer Verification

Perform with the sample application on your local machine:

1. Enable all three sources and call `info`. Confirm the three keys `java`, `os`, and `process` appear; note the actual Java version and PID.
2. Set `management.info.os.enabled=false` specifically, restart, and call again. The `os` section must be absent, while `java` and `process` remain if the rest of the config stays unchanged.
3. Re-enable `os`; remove `info` from the HTTP exposure list and restart. With the sample application having no extra security/proxy layer, that path is no longer exposed and returns `404`. Enabling contributors does not make the URL appear by itself.
4. Restore exposure and call again. Compare `java.version` against the Java actually used to launch the application, not just Java in another terminal.
5. Run `RuntimeProbe` with the same JDK. Compare the Java/OS information groups; explain why the PIDs of the two programs differ.

In automated tests, prefer checking the presence of each section, data types, and conditions such as a positive PID or a minimum CPU count of `1`; avoid hardcoding a PID, kernel version string, or JSON key order.

After practicing, learners should be able to explain: why enabling sources and exposing the endpoint are two separate steps; which section confirms the runtime; why PIDs must be tied to a specific instance; and why available CPU count is not CPU load.
