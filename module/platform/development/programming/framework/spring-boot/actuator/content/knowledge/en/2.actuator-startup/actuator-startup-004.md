# Running the Sample Application and Calling the First health Endpoint

## 1. Goal: obtain a verifiable response

After adding Actuator, the first thing to do is run a small application and call the `health` endpoint properly. This hands-on lesson helps you verify the entire chain:

~~~text
Source code and configuration
    -> compile, package
    -> Java process starts
    -> web server accepts requests
    -> health endpoint returns a response
~~~

At the end of a normal run, the check command will output:

~~~text
{"status":"UP"}
HTTP=200
~~~

The two lines have different meanings:

- `{"status":"UP"}` is the JSON body of the health response.
- `HTTP=200` is the HTTP status code additionally displayed by the calling tool.

You will learn how to produce that result, read it within the right scope, and distinguish it from cases with the wrong path, health reporting `DOWN`, or an application no longer accepting connections.

The example uses **Java 21**, **Spring Boot 3.3.13**, and **Maven** in a standalone project. This is a lesson on running the application and testing the first endpoint; no database, Docker, Prometheus, or monitoring account is needed.

## 2. Preparation before creating the project

### 2.1. Check the tools

In the terminal, run:

~~~powershell
java -version
mvn -v
curl.exe --version
~~~

Check the following points instead of requiring the entire output to match another machine:

- `java -version` shows that the `java` command uses JDK 21.
- `mvn -v` shows that Maven is also running on JDK 21.
- `curl.exe --version` confirms the cURL program can be invoked.

Java in `PATH` and the Java used by Maven may differ. If they do not match the expected environment, adjust your JDK configuration before continuing.

The commands in this lesson are written for **PowerShell on Windows**. Calling `curl.exe` avoids colliding with the `curl` alias in some PowerShell versions. On Linux or macOS, use `curl` for the corresponding cURL commands.

### 2.2. Prepare the directory and two terminals

Create a new directory named `first-health`. There is no need to place it inside another application.

You will use:

- **Terminal A** to compile and keep the application running.
- **Terminal B** to send HTTP requests.

The sample application listens at `127.0.0.1:18080`. If this port is already in use, the troubleshooting section below shows how to change the port.

The first build needs to download libraries and plugins from the Maven repository. Maven failing to download dependencies is a build-stage error; at that point there is no health endpoint yet to check.

## 3. Creating the minimal project

Required structure:

~~~text
first-health/
├── pom.xml
└── src/main/
    ├── java/example/firsthealth/FirstHealthApplication.java
    └── resources/application.yml
~~~

### 3.1. Declare dependencies in pom.xml

Complete contents of `pom.xml`:

~~~xml
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

    <groupId>example</groupId>
    <artifactId>first-health</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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

The two starters have different responsibilities:

- `spring-boot-starter-web` provides the web application infrastructure for the example.
- `spring-boot-starter-actuator` provides the corresponding management and observability capabilities.

Adding Actuator does not replace the requirement to have web infrastructure if you want to call endpoints over HTTP. Enabling Actuator via the starter is described in [the official documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

The parent manages library versions and shared build configuration. With this parent, declaring `spring-boot-maven-plugin` makes the package step produce a JAR runnable with `java -jar`. [Spring Boot Maven Plugin: Packaging Applications](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html).

### 3.2. Create the startup class

File `src/main/java/example/firsthealth/FirstHealthApplication.java`:

~~~java
package example.firsthealth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FirstHealthApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirstHealthApplication.class, args);
    }
}
~~~

The file name must match the `FirstHealthApplication` class and the directory path must match the `example.firsthealth` package.

`@SpringBootApplication` enables standard Boot application configuration. `SpringApplication.run(...)` creates the context and starts the required components according to dependencies and configuration.

You do not need to write a `HealthController` or a `@GetMapping("/actuator/health")` method yourself. `HealthEndpoint` is a capability provided by Actuator. [HealthEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

The example also does not create a dummy business API just to run health. The purpose of the application is to demonstrate that the management endpoint works.

### 3.3. Create the configuration

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: first-health

server:
  address: 127.0.0.1
  port: 18080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Meaning of the configuration:

| Property | Role in the lesson |
| --- | --- |
| `spring.application.name` | Sets the application name |
| `server.address` | Listens only on loopback address `127.0.0.1` |
| `server.port` | Selects port `18080` |
| `management.endpoints.web.exposure.include` | Selects only `health` for web exposure |
| `management.endpoint.health.show-details` | Excludes health details from the response |

In the Boot 3.3 line, health is already in the default HTTP exposure list. The lesson explicitly writes `include: health` so the reader sees the practice scope. It is not a list of every endpoint enabled across the entire application. [Configuring endpoints and exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

YAML uses spaces for indentation. Place the file properly in `src/main/resources` so it is packaged into the JAR.

The example serves only from the same machine at the chosen address and does not add Spring Security. When exposing management endpoints in a deployed application, apply that environment's management access design; reducing JSON details does not replace authorization.

## 4. Compiling and running the application

### 4.1. Package in Terminal A

Open Terminal A in the `first-health` directory, where `pom.xml` resides, and run:

~~~powershell
mvn clean package
~~~

`clean` removes old build artifacts; `package` executes the phases needed to create the new artifact.

Wait for Maven to finish. When the build succeeds, the log ends with:

~~~text
BUILD SUCCESS
~~~

This is a sign of the **build step**, not evidence that the application is currently accepting HTTP requests.

You can confirm the file was created with:

~~~powershell
Test-Path target/first-health-1.0.0.jar
~~~

Result:

~~~text
True
~~~

Do not mistakenly pick the file with the `.jar.original` suffix. The plugin may keep the original JAR under that name; the JAR you need to run in this lesson is `first-health-1.0.0.jar`.

### 4.2. Launch the JAR

Continue in Terminal A:

~~~powershell
java -jar target/first-health-1.0.0.jar
~~~

This command keeps the application running in the foreground of the terminal. Leave that terminal open while testing HTTP.

In the normal startup log of the example, look for messages containing these fragments:

~~~text
Tomcat started on port 18080
Started FirstHealthApplication
~~~

These are identifying fragments within log lines, not the entire fixed stdout. Timestamps, PID, startup duration, and formatting will vary by run.

If the application reports an error and exits, fix the error before moving on to calling the endpoint. A log line appearing early during startup does not guarantee the entire application started successfully.

### 4.3. Why does the lesson use Maven instead of a javac command?

The Java file requires Spring Boot, Spring Framework, and Actuator libraries. Compiling with `javac` requires the full classpath, and you still need to package dependencies to run.

In this lesson, Maven handles those steps using the given configuration; `java -jar` runs the complete artifact. Do not copy the Java file alone and expect `java FirstHealthApplication` to find all libraries on its own.

## 5. Calling the first health endpoint

### 5.1. Send a GET request from Terminal B

Open Terminal B and run:

~~~powershell
curl.exe --silent --show-error --max-time 5 http://127.0.0.1:18080/actuator/health
~~~

If the application is running with the right configuration and existing checks pass, the response body is:

~~~json
{"status":"UP"}
~~~

This is the HTTP response printed by cURL in Terminal B, not a log line from the Java process in Terminal A.

The options make verification easier to read:

- `--silent` hides the progress bar.
- `--show-error` still displays a message on transport errors.
- `--max-time 5` limits the call duration to 5 seconds.

With no option sending data or choosing another method, the request here uses GET. [cURL Documentation](https://curl.se/docs/manpage.html).

### 5.2. Breaking down the URL to avoid wrong calls

~~~text
http://127.0.0.1:18080/actuator/health
|       |         |       |       |
protocol        port    prefix  endpoint identifier
        host address
~~~

In this project:

- The protocol is `http` because HTTPS is not configured yet.
- The address is `127.0.0.1` of the machine running the command.
- The port is `18080` per configuration.
- The default prefix is `/actuator`.
- The endpoint identifier is `health`.

If sent from another container or machine, `127.0.0.1` refers to that sending environment itself. It does not automatically point back to the Java process on the development machine.

The Actuator path can change when the application configures a different prefix or context path. The sample lesson keeps the default path so the first call is easy to verify. [Configuring management HTTP paths](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 5.3. Viewing both JSON and HTTP status code

Use a command with `--write-out` added:

~~~powershell
curl.exe --silent --show-error --max-time 5 --write-out '\nHTTP=%{http_code}\n' http://127.0.0.1:18080/actuator/health
~~~

Output when health is `UP`:

~~~text
{"status":"UP"}
HTTP=200
~~~

In the string passed to cURL, `\n` tells the tool to insert a newline. That keeps the JSON body and HTTP code clearly separated.

Code `200` indicates this request was processed successfully according to the HTTP response. The `status` field is the application's health assessment in that response. When checking status, inspect both.

### 5.4. Reading JSON with PowerShell

You can use PowerShell to extract a data field instead of only viewing the raw JSON string:

~~~powershell
$health = Invoke-RestMethod -Uri "http://127.0.0.1:18080/actuator/health"
$health.status
~~~

Result during a passing run:

~~~text
UP
~~~

`Invoke-RestMethod` converts JSON into an object to read properties. When the server returns an error code such as `503`, the command's error-reporting behavior differs from the cURL command used above. When first testing failure cases, use the cURL command with HTTP code to keep observations consistent.

You can also open the health address in a browser on the same machine. The browser may display or format the JSON; that does not change the meaning of `status`.

## 6. Interpreting UP accurately

Health represents status based on the participating check components. Each `Health` result has a status and may contain details about the evaluated component. [Health API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

With this small application, you have not configured a database or a payment service. Therefore:

~~~text
UP in this sample
    -> existing checks do not report an unhealthy state

UP in this sample
    -> is not evidence about a payment system that has not been integrated
~~~

The first call gives you evidence that at the moment of testing:

1. Terminal B can reach the HTTP address in use.
2. The application receives and processes the request to the health endpoint.
3. Health returns the status shown in the response body.

It has not yet evaluated high load, business API latency, or any dependencies that may be added later.

Do not hardcode JSON to `UP` via a custom controller just to pass a check. When the result differs from expectations, investigate the actual check and conditions.

## 7. Two tests to avoid wrong conclusions

### 7.1. The root path can return 404 while health still works

This application has no controller or home page for `/`. Check the HTTP code of the root path:

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:18080/
~~~

With the exact sample project, the result is:

~~~text
404
~~~

Calling `/actuator/health` right afterward can still return `UP` and `200`.

Having no home page does not mean the web server failed to start. Check the exact path you intend to evaluate.

`NUL` discards the response body on Windows. On Linux or macOS, use `/dev/null` instead of `NUL`.

### 7.2. Metrics is not automatically exposed just because health works

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:18080/actuator/metrics
~~~

With the exposure list containing only `health` in this lesson, the result is:

~~~text
404
~~~

This test confirms the HTTP scope of the sample. There is no need to expose every endpoint to make the hands-on lesson "more complete"; the current goal is to run and understand health first.

## 8. Controlled test: server still running while health reports DOWN

This section is a short optional test to distinguish **receiving no connection** from **receiving an unhealthy status response**.

### 8.1. Create a failing check condition via configuration

Stop the application in Terminal A with `Ctrl+C`. Run the same JAR again with an intentionally very high disk space threshold:

~~~powershell
java -jar target/first-health-1.0.0.jar --management.health.diskspace.threshold=9223372036854775807B
~~~

This threshold is higher than the free space on a typical lab machine. The test changes the disk space evaluation condition; it does not write data to fill up the disk.

The application can still start. Wait for it to finish starting, then call again in Terminal B:

~~~powershell
curl.exe --silent --show-error --max-time 5 --write-out '\nHTTP=%{http_code}\n' http://127.0.0.1:18080/actuator/health
~~~

With the failing disk check and the sample's default mapping configuration:

~~~text
{"status":"DOWN"}
HTTP=503
~~~

You received an HTTP response, meaning the server is still accepting and handling this request. The `DOWN` status describes the check result; it does not mean the process disappeared.

Mapping health status to HTTP status codes has its own dedicated mechanism. The result above belongs to the sample's Boot 3.3 configuration, not a rule for every field containing the word `DOWN` in every API. [Health HTTP code mapping mechanism](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

The lesson's cURL command does not use `--fail`. Hence, receiving code `503` does not automatically turn cURL's exit code into a transport error. HTTP status codes and program exit codes are two distinct kinds of results.

### 8.2. Restore initial conditions

Stop the test run with `Ctrl+C` and restart without the threshold argument:

~~~powershell
java -jar target/first-health-1.0.0.jar
~~~

Call health again. When the default checks pass, you receive `UP` and `200`.

The threshold argument applied only to the run it was passed to. Since you did not edit `application.yml`, no file edit is needed to undo this test.

### 8.3. Compare with when the application is stopped

Stop the application and call health again. If no other process is listening on that address/port, cURL reports a connection error instead of returning health JSON.

If `--write-out` prints `HTTP=000` during a transport error, `000` is not an HTTP code sent by the health endpoint. What needs to be investigated first is connectivity to the server.

Do not expect a stopped application to return `{"status":"DOWN"}` on its own. A JSON response is generated only when a component is still accepting requests and producing responses.

## 9. Troubleshooting by stage

| Symptom | Stage to check first | What to inspect |
| --- | --- | --- |
| `mvn` is not recognized | Build tools | Install/configure Maven and reopen an appropriate terminal |
| Maven uses an unexpected JDK | Build tools | Compare `mvn -v` with `java -version` |
| Cannot download dependencies | Build | Check network connectivity, proxy, and Maven repo configuration |
| JAR not found | Running program | Ensure right directory, successful build, and file name |
| JAR has no main manifest | Packaging/artifact selection | Check plugin and avoid running `.jar.original` |
| Port already in use | Web server startup | Identify the process using the port or choose another port |
| Connection refused or timed out | Connection | Check process, address, port, and startup log |
| HTTP `404` | Routing/exposure | Check URL and the configuration actually running |
| HTTP `401` or `403` | Access | Check security mechanism and target application |
| JSON `DOWN` with HTTP `503` | Health checks | Check health conditions, including passed arguments |

The table provides investigation pointers for the sample lesson, not an absolute reverse mapping for every system with proxies or custom rules.

### 9.1. Changing the port when needed

For example, if `18080` is occupied:

~~~powershell
java -jar target/first-health-1.0.0.jar --server.port=18081
~~~

The verification URL must change accordingly:

~~~powershell
curl.exe --silent --show-error --max-time 5 http://127.0.0.1:18081/actuator/health
~~~

If you keep calling `18080`, you may be calling a different application. Receiving valid JSON alone is not enough to prove you are checking the exact process you just started.

### 9.2. Rerunning after editing files

When you change Java code or `application.yml` and continue running a previously packaged JAR, the JAR does not automatically pick up edits from the source directory.

To test the new version:

1. Stop the running process.
2. Run `mvn clean package`.
3. Run the JAR again and wait for startup to complete.
4. Call the exact URL matching the new configuration.

By contrast, command-line arguments like `--server.port=18081` are passed directly into that run; no rebuild is required just to pass that value.

### 9.3. A minimal project unexpectedly prompts for login

The exact `pom.xml` in this lesson does not add Spring Security. If you see a login screen or `401/403`, check whether you are running the right JAR, right port, and right set of dependencies.

If practicing on an application that already has security, read that application's own rules. Exposing health by removing all security is not a required step of this hands-on lesson.

## 10. Confirming completion on your own

You have completed the practice loop when you can repeat and explain:

- A successful build produces the right JAR; the application actually runs from that JAR.
- Calling `GET /actuator/health` at the right address/port.
- Reading the `status` content and HTTP code separately.
- Explaining why `UP` reflects only existing checks.
- Distinguishing `404` on another path, `503` from health, and a no-connection error.
- Stopping the application and recognizing the endpoint no longer returns JSON on its own.

**Short exercise:** Run the application on port `18081`, call health using both cURL and PowerShell, then stop it. For each check, record whether you received an HTTP response or encountered a transport error.

The question to answer for yourself is: **"What evidence do I have that my own application is receiving the request and what is health evaluating?"** Answering that clearly lets you use the first endpoint as a practical verification tool rather than merely looking for an `UP` string.
