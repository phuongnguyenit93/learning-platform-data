# Changing Code, Re-running, and Verifying Observable Results

In your first Spring Boot project, getting the application to start once is only the beginning. A developer's daily workflow is **changing code, getting that change into the running process, and verifying whether the application behaves as expected**.

A seemingly simple change, such as editing an API's greeting message, might not show up when you call the HTTP endpoint. The reason is not necessarily wrong Java code: you might not have recompiled, might not have restarted the server, might be calling the wrong port, or might still be running a JAR built from older code.

This lesson builds a repeatable feedback loop:

~~~text
Observe current behavior
         │
         ▼
Choose one concrete change
         │
         ▼
Edit source code and save file
         │
         ▼
Compile / restart application
         │
         ▼
Send request to the right process
         │
         ▼
Inspect status, response, logs
         │
         ▼
Compare with expected result
         │
    ┌────┴─────┐
    ▼          ▼
  Match     Mismatch
    │          │
    ▼          ▼
 Record     Find cause,
 outcome    fix, and retry
~~~

The core skill is distinguishing **“source edited”**, **“code built”**, **“code running”**, and **“result observed by the client”**. They are closely linked, yet not automatically the same thing.

## 1. What are we trying to verify?

Suppose our first application has the endpoint:

~~~http
GET /api/greeting?name=Lan
~~~

Initially, the server returns:

~~~json
{
  "message": "Hello, Lan!"
}
~~~

You want to change it to:

~~~json
{
  "message": "Hello, Lan! This is the updated version."
}
~~~

A meaningful verification must answer three questions:

1. **Is the new code actually executing?** Recompiling and restarting is the standard way to load updated classes into a JVM process.
2. **Are we calling the right application and endpoint?** Check host, port, HTTP method, and path.
3. **Does the response meet the requirement?** Cross-check status, response body, and when needed, logs or automated tests.

A log line `Started DemoApplication` only proves the process completed a startup stage; it **does not prove** the endpoint returns the new content. Conversely, a response containing the new text from a verified endpoint confirms that the corresponding execution path ran the updated code or an equivalent configuration change.

Before verifying, define the **expected output** upfront so you avoid treating just any response as a pass.

## 2. Preparing the illustrative project

The examples use Java 21, Spring Boot 3.x, and Maven. If you already have a Spring Boot project with `spring-boot-starter-web`, you can start from the controller. If you are using Gradle, the Java code is identical; only build and run commands differ.

To keep the example self-contained, the project layout is:

~~~text
demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── demo/
        │               ├── DemoApplication.java
        │               ├── GreetingController.java
        │               └── GreetingResponse.java
        └── resources/
            └── application.properties
~~~

### 2.1. Minimal Maven declaration

File `pom.xml`:

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
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

Versions in the example are fixed to illustrate a reproducible setup. When creating a real project, pick a supported Spring Boot version compatible with your Java version and libraries.

### 2.2. Entry point

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables component scanning and auto-configuration in the appropriate scope. Place the controller in the same `com.example.demo` package so Spring detects it via default scanning.

### 2.3. Response data type

File `src/main/java/com/example/demo/GreetingResponse.java`:

~~~java
package com.example.demo;

public record GreetingResponse(String message) {
}
~~~

`record` is a concise Java type for modeling data. When the web app has appropriate JSON dependencies, Spring MVC serializes a `GreetingResponse` into JSON in the HTTP response.

### 2.4. Initial controller

File `src/main/java/com/example/demo/GreetingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/greeting")
    public GreetingResponse greeting(
            @RequestParam(defaultValue = "Friend") String name) {
        return new GreetingResponse("Hello, " + name + "!");
    }
}
~~~

In the code above:

- `@RestController` marks a component that handles HTTP requests and writes return values into the response body.
- `@GetMapping("/api/greeting")` maps `GET` requests at this path to the `greeting` method.
- `@RequestParam` reads the `name` query parameter. If omitted, the application uses `Friend`.
- `GreetingResponse` supplies the data object that the HTTP converter serializes to JSON.

### 2.5. Port and application name configuration

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=demo
server.port=8080
~~~

Port `8080` is set explicitly in the example for easy checking. If another program on your machine already uses that port, choose a free port or stop the program holding it.

## 3. Step 1: Run the initial version and record a baseline

From the `demo` directory, you need a compatible JDK and Maven.

Check basic commands if your environment is not yet verified:

~~~bash
java -version
mvn -version
~~~

`java -version` shows the Java runtime invoked from the terminal. `mvn -version` also reports the Java version Maven uses. Having those two commands point to different JDKs can cause confusing build and runtime behavior.

Start with Maven:

~~~bash
mvn spring-boot:run
~~~

If the project has a **Maven Wrapper**, you can use:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell, use the corresponding wrapper if present:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Not every project includes wrapper files. Wrapper commands only work if those files are present in the project.

When Spring Boot starts successfully, logs typically include lines like:

~~~text
... Tomcat started on port 8080 (http) ...
... Started DemoApplication in ... seconds ...
~~~

Exact log wording and timing vary by version, configuration, and environment. Useful signs are the absence of fatal startup errors and the server listening on the expected port.

**Keep the server terminal running.** A web application running in a terminal continues occupying that terminal until stopped. Open a second terminal to send HTTP requests.

### 3.1. Calling the endpoint before editing

In the second terminal:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Lan"
~~~

If PowerShell aliases `curl` to something else, invoke the executable explicitly:

~~~powershell
curl.exe -i "http://localhost:8080/api/greeting?name=Lan"
~~~

An equivalent response is:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"Hello, Lan!"}
~~~

Exact header formatting, header ordering, and JSON whitespace may differ. What to compare is:

| Observation | Expected in Initial Version |
| --- | --- |
| HTTP method | `GET` |
| URL | `http://localhost:8080/api/greeting?name=Lan` |
| HTTP status | `200 OK` |
| Content type | JSON (`application/json`) |
| JSON field | `message` |
| `message` value | `Hello, Lan!` |

You can also test without passing a name:

~~~bash
curl -i "http://localhost:8080/api/greeting"
~~~

Then `name` defaults to `Friend`, because the controller has `@RequestParam(defaultValue = "Friend")`.

**Record the baseline before editing.** If the endpoint does not work right from the start, resolve the startup or routing issue first before using it to verify a new code change.

## 4. Step 2: Edit the exact code producing the behavior

Our change goal here is: append the sentence `This is the updated version.` to the greeting message. Keep the endpoint, HTTP method, and JSON structure unchanged so the comparison focuses on a single change.

Open `GreetingController.java` and edit **one return line**.

**Before edit:**

~~~java
return new GreetingResponse("Hello, " + name + "!");
~~~

**After edit:**

~~~java
return new GreetingResponse(
        "Hello, " + name + "! This is the updated version.");
~~~

Keep the rest intact:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/greeting")
    public GreetingResponse greeting(
            @RequestParam(defaultValue = "Friend") String name) {
        return new GreetingResponse(
                "Hello, " + name + "! This is the updated version.");
    }
}
~~~

Save the file in your editor. If the IDE has multiple tabs open, make sure you saved the exact path `src/main/java/com/example/demo/GreetingController.java`.

A clearly observable change has these qualities:

- **Small:** easy to tell which exact code is responsible.
- **Externally visible:** observable in HTTP responses, logs, stored data, or effects you can inspect.
- **Predefined expectation:** before restarting, you already know what JSON should be returned.
- **Repeatable:** the same input and conditions produce consistent output.

Saving a file only updates **source on disk**. It does not guarantee the updated class has been loaded into the running JVM.

## 5. Step 3: Get the new code into the running application

### 5.1. Reliable approach for beginners: stop and restart

Return to the terminal running `mvn spring-boot:run` and stop the process with `Ctrl+C`. Wait for the process to exit, then run again:

~~~bash
mvn spring-boot:run
~~~

In this flow, Maven prepares the application from source according to the relevant lifecycle, and Spring Boot starts a fresh process. Once source is saved and compiled cleanly, the updated controller runs in the next startup.

~~~text
Edit GreetingController.java
            │
            ▼
       Save source
            │
            ▼
Stop old Spring Boot process
            │
            ▼
Compile new source and restart
            │
            ▼
New JVM process serves /api/greeting
~~~

If the change introduces a compile error, the application **cannot start from the new classes** until the error is fixed. Read the compiler message and file/line location before retrying.

### 5.2. If running from an IDE

In IntelliJ IDEA, Eclipse, or VS Code, exact shortcuts depend on project and IDE configuration. The most deterministic procedure is:

1. Save `GreetingController.java`.
2. Stop the previous application run.
3. Re-run the Spring Boot/main class run configuration so the IDE compiles changed source.
4. Watch the new logs, then re-call the endpoint.

Some IDEs support **HotSwap**, auto-build, or auto-restart. Do not assume those features are enabled. In particular, standard HotSwap only supports a limited set of edits; class structure changes face different limits than method body edits.

### 5.3. If running an executable JAR

With packaging, distinguish **building the JAR** from **running the JAR**:

~~~bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

`mvn clean package` deletes previous build output and runs steps through packaging, including compiling and running tests configured in Maven's lifecycle. `java -jar` launches a packaged artifact.

If you edit `.java` files and keep running the **old JAR** without rebuilding, you will keep receiving the old response even though source on disk changed properly.

**Sequence to remember with JARs:**

~~~text
Edit source → Build new JAR → Stop old process → Run new JAR → Send HTTP request
~~~

Writing a new JAR to disk also does not replace classes already loaded inside an older JVM process. You need an actual restart/redeploy step so the process uses the new artifact.

### 5.4. If the project uses Gradle

For a Spring Boot project using Gradle and the Spring Boot plugin, the equivalent commands are typically:

~~~bash
./gradlew bootRun
~~~

To package:

~~~bash
./gradlew clean bootJar
~~~

In PowerShell, if the repository includes the Gradle Wrapper:

~~~powershell
.\gradlew.bat bootRun
.\gradlew.bat clean bootJar
~~~

Executable JARs are normally created in `build/libs/`; the exact name depends on project configuration. Always run `java -jar` against the exact newly built artifact. These commands describe **alternatives** to Maven when a project is set up with Gradle; you do not run both build tools on one project.

## 6. Step 4: Re-call the endpoint and observe the result

Once the new server starts, in the second terminal run:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Lan"
~~~

Expected result:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"Hello, Lan! This is the updated version."}
~~~

Compare against the initial version:

| Attribute | Before Edit | After Edit |
| --- | --- | --- |
| URL | `GET /api/greeting?name=Lan` | Unchanged |
| Status | `200` | `200` |
| Data format | JSON | JSON |
| `message` | `Hello, Lan!` | `Hello, Lan! This is the updated version.` |

Thus, the new response is observable as intended: **same request, same structure, expected new value**.

Avoid over-concluding. This response does not prove every other feature in the application works, nor does it prove the system has production-grade security or performance. It verifies a specific behavior of one specific path at the time of testing.

### 6.1. Checking a second input

Send a request without `name`:

~~~bash
curl -i "http://localhost:8080/api/greeting"
~~~

Expected response:

~~~json
{"message":"Hello, Friend! This is the updated version."}
~~~

This check confirms the default parameter rule still works after updating the greeting sentence.

### 6.2. Testing a nonexistent path

~~~bash
curl -i "http://localhost:8080/api/not-found"
~~~

A Spring MVC app without a matching mapping normally returns HTTP `404 Not Found`. Exact error body contents may vary by version and configuration, so focus on the status. This case helps distinguish “server is running, yet hit the wrong route” from “server did not start.”

### 6.3. Observing HTTP status and body are two separate checks

An endpoint can return `200` with the wrong body, or return expected JSON in a mocked scenario while having the wrong HTTP status per contract. For your first API, verify at minimum:

- **Status:** did the server handle the request successfully or report an error?
- **Content type:** is the response JSON as expected by the contract?
- **Body:** are the fields and values correct?
- **Request target:** are host, port, path, method, and parameters right?

When you need to verify JSON structure accurately, parse the JSON and assert on fields rather than comparing the entire raw string. Property ordering and whitespace in JSON are not always significant.

## 7. Distinguishing build logs, startup logs, and request logs

Beginners often see many lines in the terminal and assume all of them prove the same thing. In fact, they reflect distinct stages.

| Information Source | What It Proves or Helps Verify | What It Does Not Prove Yet |
|---|---|---|
| Maven/Gradle compile logs | Build tasks processed source and dependencies per lifecycle | That endpoints return expected data |
| `Started DemoApplication` log | Application context finished corresponding startup | That specific requests run the right logic |
| Server port-listening log | Server started serving on a port | That the client is calling the right port or process |
| HTTP status and body | Actual result received by the client from a request | That all other business flows are correct |
| Application-written logs | Trace helping confirm execution path | That every behavior succeeded end to end |

To observe directly when a method is invoked, you can add logging intentionally.

Example in `GreetingController`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

Declare the logger in the class:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(GreetingController.class);
~~~

And inside the method:

~~~java
log.info("Greeting endpoint invoked");
return new GreetingResponse(
        "Hello, " + name + "! This is the updated version.");
~~~

These are **additions** to the example controller, not a standalone Java file. After saving and restarting, a valid request to the endpoint emits that log line when logging configuration displays `INFO` level.

Do not log tokens, passwords, private details, or sensitive data just to verify an endpoint. In this lesson, HTTP status and JSON body already suffice to confirm the greeting; logging is a supporting tool when tracing execution flow.

## 8. When do you need to build, restart, or just refresh the browser?

“Re-run” means different things. The kind of change determines which update step you must perform.

| What Did You Change? | Reliable Update Flow for a First Project |
|---|---|
| Java source (`.java`) | Save → recompile → restart application |
| `application.properties` or `application.yml` | Save → restart application to load new configuration |
| Dependency in `pom.xml` or `build.gradle` | Resolve/build dependencies → restart application |
| Packaged executable JAR | Build new JAR → stop old process → run new JAR |
| Frontend page output built by another tool | Run that tool's build/reload step, then reload the page |
| Only the URL or query parameter in the client | Send a new request; usually no server restart needed |

This table describes a reliable workflow for beginners. Some environments provide tools that watch file changes and auto-restart/reload, yet you should rely on them only after understanding the underlying mechanism.

**Refreshing a browser does not compile Java.** If the server is still running older classes, pressing F5 repeatedly will never load your new Java source.

## 9. Does Spring Boot DevTools help auto-restart?

Spring Boot DevTools is an optional development-loop utility. When properly configured, it watches classpath changes and triggers an **application restart** so you see new code faster. It does not replace Java compilation.

With Maven, you can add to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Then restart the project in development mode. Several nuances to distinguish:

1. Editing a `.java` file changes **source**, whereas DevTools watches for appropriate changes on the **classpath**. Your IDE or build tool must place newly compiled classes onto the classpath for the restart trigger to detect them.
2. Depending on launch mode or IDE configuration, you may need to trigger a build, recompile classes, or enable IDE auto-build.
3. DevTools is not guaranteed to hot-reload every kind of configuration or runtime change; manual restarts are still needed in some cases.
4. DevTools is for **development**, not a mechanism for updating production code.

If you want a solid grasp of the basic lifecycle, stop and restart manually the first few times. Once you have observed it working, DevTools shortens the feedback loop without changing the principle: **new code must reach the process serving requests**.

## 10. Situations where “I edited the code, yet the result is still old”

The following scenarios are very common in a first project. Start from observable signals instead of randomly editing multiple files.

### 10.1. Forgot to save the file

**Symptom:** The editor shows the new greeting, yet the response still shows the old text.

**Likely cause:** Edits still live only in the editor's memory buffer. The build tool reading files on disk still sees old content.

**How to handle:** Save the file, verify the editor tab shows no unsaved indicator, build/restart, and re-call the endpoint.

### 10.2. Forgot to compile or restart

**Symptom:** Source on disk is correct with no errors, yet calling the API still returns the old body.

**Likely cause:** The JVM is running classes compiled before the edit. Very common when not using DevTools or when IDE auto-build is off.

**How to handle:** Stop the server, restart via Maven/Gradle/IDE, wait for startup to finish, and send the request again.

### 10.3. Running the wrong JAR or wrong project directory

**Symptom:** Build succeeded and started up, yet the API output did not change.

**Likely cause:** The terminal launched an older JAR or a different directory. A workspace may contain multiple artifacts or modules.

**How to handle:** Check your working directory, inspect the JAR path passed in the command, rebuild the right module, and launch the right artifact. With Maven, `mvn clean package` in the example project generates a fresh artifact in `target/` if the build passes.

Do not guess which JAR is new just from similar filenames; use the exact path of the freshly built artifact.

### 10.4. Calling the wrong port

**Symptom:** HTTP fails to connect, or returns stale data even though the new app's logs say it is listening on another port.

**Likely cause:** The new app runs on `8081`, yet the client still calls `8080`. An older instance may still be running on `8080`.

**How to handle:** Read the port reported in startup logs and `server.port` settings. Then verify the exact URL in the client.

For example, if the app runs on `8081`:

~~~bash
curl -i "http://localhost:8081/api/greeting?name=Lan"
~~~

If you intentionally switch ports to compare versions, record which **host and port** are tested in each pass.

### 10.5. Port already in use

**Symptom:** Startup logs contain a message like `Port 8080 was already in use`; the new instance fails to start.

**Likely cause:** A process is already holding that port, quite possibly your older unstopped run.

**How to handle:** Stop the older run or pick another port for the new run, such as:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=8081
~~~

This is Maven Spring Boot plugin syntax for passing application arguments. Another option after packaging is:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=8081
~~~

Only use a port you have verified is free. If running two versions side by side for comparison, clearly note which port holds the old version and which holds the new one.

### 10.6. Receiving HTTP 404

**Symptom:** Connection to the server succeeds, yet status is `404 Not Found`.

**Likely cause:** Request hit the wrong path, called the wrong app, controller was not detected by Spring, or the mapping is incorrect.

**How to handle:** Check every piece: `GET` vs `POST`, exact `/api/greeting` spelling, whether the controller is in a component-scanned package, and which port the server uses. Do not conclude the greeting string logic is broken simply because a different path returned 404.

### 10.7. Receiving HTTP 405 or 400

- `405 Method Not Allowed` can appear when using an HTTP method unsupported by the route, such as sending `POST` to an endpoint annotated only with `@GetMapping`.
- `400 Bad Request` can appear when Spring cannot convert or validate input parameters per the handler contract.

In the `/api/greeting` example, use `GET` and a string `name` parameter. If using Postman, check the method dropdown next to the URL rather than looking only at the endpoint path.

### 10.8. Receiving HTTP 500

**Symptom:** The server received the request, yet encountered an internal error during handling and returned `500 Internal Server Error`.

**Likely cause:** The controller method or a dependency threw an unhandled exception, or response serialization failed.

**How to handle:** Inspect the stack trace and application logs at request time, find the first meaningful exception and call chain. After fixing, build/restart and re-test with the exact same input.

Do not read only the error response body and edit the controller blindly; the stack trace normally points to the exact source of the failure.

### 10.9. Build failed, yet another server still responds

**Symptom:** Maven/Gradle reported a compile error, yet `curl` still received JSON.

**Likely cause:** An older application process started in a previous run is still alive. An HTTP response from that older process **does not prove the new build succeeded**.

**How to handle:** Locate and stop the older run, fix the compile error, and start a fresh run with clear logs. Never use a response from a preexisting process as evidence about newly edited code.

### 10.10. Response appears unchanged due to caching

In simple HTTP examples, the cause is usually process or port mix-ups, yet in larger apps, browsers, proxies, or cache layers can cause observed responses not to reflect the latest request.

When suspecting caching, call the backend development address directly with `curl` and check incoming request logs. Do not disable caching everywhere as a default fix for everything; first identify which component served the response.

## 11. Using actual results to isolate errors

Follow observable signals in order:

~~~mermaid
flowchart TD
    A["Send GET /api/greeting"] --> B{"Able to connect?"}
    B -->|No| C["Check process, host, port, startup logs"]
    B -->|Yes| D{"HTTP status?"}
    D -->|404/405| E["Check route and HTTP method"]
    D -->|500| F["Read exception and request logs"]
    D -->|200| G{"Body matches new version?"}
    G -->|Yes| H["Record observed change"]
    G -->|No| I["Check save, build, restart, JAR, and port"]
~~~

This sequence cuts down the number of variables investigated at once:

- If **unable to connect**, fix connection or startup first; you cannot verify response contents yet.
- If **connected yet wrong status**, check route, method, and request logs.
- If **status right yet old body**, focus on build, running process, port, and saved source file.
- If **both status and body match**, you have concrete evidence for that specific change.

Do not edit five places at once just to see if the error goes away. Whenever you change multiple variables at once, you lose the ability to know which change actually caused the result.

## 12. Verifying not just by eye: asserting results

For small projects, `curl -i` is enough to learn observation. When repeating a check over and over, you can write a script or automated test to verify success conditions automatically.

### 12.1. Checking with PowerShell

In PowerShell you can parse JSON into an object:

~~~powershell
$response = Invoke-RestMethod -Uri "http://localhost:8080/api/greeting?name=Lan"
$response.message
~~~

Output:

~~~text
Hello, Lan! This is the updated version.
~~~

You can write an explicit assertion:

~~~powershell
$expected = "Hello, Lan! This is the updated version."
if ($response.message -ne $expected) {
    throw "Response does not match the expected value."
}
Write-Output "Verified new response."
~~~

This makes comparison explicit rather than eyeballing a long body and guessing by feel. This script checks **only the `message` field value**; it is not a complete test suite for all statuses or error cases.

### 12.2. Testing HTTP with Spring Boot

Once comfortable with manual verification, you can add `spring-boot-starter-test` to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `src/test/java/com/example/demo/GreetingControllerTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsUpdatedGreeting() throws Exception {
        mockMvc.perform(get("/api/greeting").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan! This is the updated version."));
    }
}
~~~

Then run:

~~~bash
mvn test
~~~

`MockMvc` exercises Spring MVC's request-handling infrastructure without opening a real HTTP port. This test catches regressions if response-producing code is accidentally altered in the future.

Distinguish clearly:

- **Manual HTTP check:** sends a real request to the running process; verifies which deployed instance you are reaching.
- **MockMvc test:** checks how Spring MVC handles requests in a test environment; great for regression protection, yet does not by itself prove the artifact currently running on port `8080` is the latest build.
- **Successful build:** confirms corresponding build steps completed; does not replace client-facing functional checks.

A serious project combines verification levels appropriate to risk and cost, whereas in a first lesson you simply need to understand why each check exists.

## 13. Leaving a trail so subsequent changes are easy to compare

At the end of an edit cycle, briefly note four facts:

| Information | Example |
| --- | --- |
| Source change | Edited returned string in `GreetingController.greeting` |
| How code entered runtime | Stopped old server, ran `mvn spring-boot:run` |
| Request sent | `GET http://localhost:8080/api/greeting?name=Lan` |
| Observed result | `200`, JSON `message` contains “This is the updated version.” |

This is explainable, reproducible evidence. When working with Git, you can also run `git diff` to inspect the exact lines changed before committing. That inspects repository changes, not runtime behavior directly.

In a development team, stating clearly “what changed and what was observed” is far more helpful than vague claims like “code runs fine” or “it seems updated.”

## 14. Practice: create three verifiable change cycles yourself

### Practice 1: Change the response message

Keep the current controller. Change the message to:

~~~java
return new GreetingResponse(
        "Wishing you effective Spring Boot learning, " + name + "!");
~~~

Before running, write down the expected response for `name=Minh`. Then stop the app, restart, and send:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Minh"
~~~

Compare status and `message` value against your prediction.

### Practice 2: Change the query parameter's default value

Change:

~~~java
@RequestParam(defaultValue = "Friend") String name
~~~

to:

~~~java
@RequestParam(defaultValue = "Learner") String name
~~~

Restart and compare two requests:

~~~bash
curl -i "http://localhost:8080/api/greeting"
curl -i "http://localhost:8080/api/greeting?name=Minh"
~~~

Explain why the first request's response changed while the second still uses `Minh`. What you observe connects directly to default parameter rules, not anything random in Spring Boot.

### Practice 3: Change the port via configuration

Set:

~~~properties
server.port=8081
~~~

Restart. Try calling sequentially:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Lan"
curl -i "http://localhost:8081/api/greeting?name=Lan"
~~~

Observe the difference, keeping in mind: port `8080` might still be used by another program. Therefore, whether the old port fails to connect or returns another response depends on what processes are running on your machine. A more reliable signal is the new app's startup log showing it listening on `8081`, followed by the endpoint on that port returning the expected output.

### Self-assessment after each round

Ask yourself:

1. Which exact file and line did I edit?
2. Has that file been saved to disk?
3. Which mechanism is responsible for compiling Java?
4. Was the old process stopped and the new code started?
5. Did the request use the right host, port, method, and path?
6. Do the status and response body match my prediction?
7. If they do not match, which signal helps me narrow down the cause first?

## 15. Connecting this lesson to future Spring Boot work

At the first-project level, the change is just a returned string. In later projects, the same feedback loop applies when:

- Editing a validation rule and sending valid and invalid requests.
- Adding a service or repository and observing application startup and business processing.
- Updating datasource settings and verifying the app connects to the intended database.
- Changing error-handling rules and checking HTTP status, error body, and logs.
- Optimizing a handler and measuring performance with an appropriate method.

Every time, the question is not merely **“does the code compile?”** but also **“is the right code actually running, and what concrete evidence proves the requirement is met?”**.

A reliable workflow is: **define expected result → edit and save code → build/restart the right process → re-send the same request → inspect status, body, and supporting evidence**. Once you master this cycle, you will resolve most “I edited the code, yet the app still acts the same” situations without relying on guesswork.
