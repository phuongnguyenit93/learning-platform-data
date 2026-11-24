# Initializing a Project with Spring Initializr

To start learning Spring Boot, you do not need to create every directory manually, write build configuration from scratch, or download dozens of libraries by hand. **Spring Initializr** generates a Spring Boot project skeleton with your chosen language, build tool, Java version, and dependencies. Once downloaded, the project is still a standard Java project: you have full control to read, edit, run, test, package, and commit the source code to Git.

This lesson guides you through creating your **first Spring Boot project** from Spring Initializr, understanding the key options in the form, opening the project locally, running the application, and adding a simple HTTP endpoint yourself. The example prioritizes Java 21, JAR packaging, and the **Spring Web** dependency; if you use Maven instead of Gradle, the equivalent steps are also presented.

## 1. What is Spring Initializr and what does it generate?

Spring Initializr is a **project generator** for applications using Spring Boot. The most common interface is [https://start.spring.io/](https://start.spring.io/), where you select project metadata and click **Generate** to download a ZIP file containing the starter codebase.

Spring Initializr is neither a server that runs your application nor a Java compiler. It prepares **structured input** so your IDE, Maven, or Gradle can carry out the next steps.

~~~text
Spring Initializr
      │
      ├── Choose Java, Spring Boot version, build tool
      ├── Declare group, artifact, package, packaging type
      └── Select appropriate dependencies
      │
      ▼
Generate → project.zip
      │
      ▼
Extract → open the project with an IDE or terminal
      │
      ▼
Maven / Gradle downloads dependencies and builds source code
      │
      ▼
Run Spring Boot → add controller/service → test endpoint
~~~

A generated project typically includes:

- Maven or Gradle configuration files, along with a **wrapper** mechanism to use the project-specified build tool version.
- A **src/main/java** directory and a class containing the **main()** method.
- The **@SpringBootApplication** annotation and a **SpringApplication.run(...)** call.
- A **src/main/resources** directory with an application configuration file.
- A **src/test/java** directory with an initial startup test class.
- The dependency list matching your selections on the form.

Key point to remember: **Initializr generates the skeleton; the business code and how the application behaves are written by you.** Selecting Spring Web provides the HTTP-handling foundation, but it does not automatically generate a **/hello** business endpoint for you.

## 2. Preparation before creating the project

You need a browser to open Spring Initializr, a **JDK** compatible with the Spring Boot version you will choose, and a Java IDE or editor. Popular IDE choices include IntelliJ IDEA, Eclipse/STS, and Visual Studio Code with appropriate Java extensions.

This lesson uses **JDK 21** as an example. What matters is that the Java version installed on your machine matches your selection in Initializr and the requirements of the specific Spring Boot version. Do not pick Java 21 on the form and then try to build with JDK 17.

Check Java from the terminal:

~~~bash
java -version
javac -version
~~~

If Java is not recognized, you need to install a JDK and configure your environment so the terminal/IDE uses the right JDK. For Maven and Gradle, **you do not necessarily need to install a global version** because new projects normally already include a Maven Wrapper or Gradle Wrapper.

An Internet connection is required to generate and download the project; the first build may also require Internet access so the build tool can download plugins and libraries from dependency repositories.

## 3. Open Initializr and choose configuration for your first project

Open **https://start.spring.io/**. The interface may evolve over time, but the main option groups usually still include **Project**, **Language**, **Spring Boot**, **Project Metadata**, **Packaging**, **Java**, and **Dependencies**.

To follow along, you can fill in the fields per the table:

| Field | Example Value | Meaning |
|---|---|---|
| **Project** | Gradle - Groovy | Uses Gradle with a Groovy build file; Maven is an equivalent choice if you prefer XML |
| **Language** | Java | Writes application source code in Java |
| **Spring Boot** | Compatible stable version | Pick a supported stable release in the UI; avoid Snapshot/Milestone builds when starting out |
| **Group** | com.example | Conventional namespace of the organization or development team |
| **Artifact** | hello-spring | Artifact identifier, usually also used to name the build output file |
| **Name** | hello-spring | Project name displayed in metadata |
| **Description** | First Spring Boot application | Short description of the project's purpose |
| **Package name** | com.example.hellospring | Root package for the startup class and application components |
| **Packaging** | Jar | Packages into an executable JAR; suitable for Spring Boot apps using an embedded server |
| **Java** | 21 | Java level of the example project; requires a matching JDK when building and running |
| **Dependencies** | Spring Web | Provides the foundation for building REST APIs with Spring MVC |

**Clarifying two easily confused choices:**

**Project** determines the build tool. Both Gradle and Maven download libraries, compile, run tests, and produce artifacts; they differ mainly in configuration syntax and command syntax. You only need to choose **one** tool for an initial project.

**Spring Boot** determines the platform version and the managed set of compatible dependencies. You do not necessarily have to pick the highest number regardless of release label: **Snapshot** or **Milestone/RC** builds are for early testing needs, whereas **Stable** builds are better suited for basic practice. Initializr's UI can change its list of available versions, so rely on release labels and actual compatibility requirements rather than copying a fixed version number from older documentation.

### How are Group, Artifact, and Package name related?

These three fields have distinct roles:

- **Group:** namespace used in build metadata, typically written in reverse-domain style, for example **com.example**.
- **Artifact:** name of the built and published unit, for example **hello-spring**; it may appear in the JAR filename.
- **Package name:** the Java package containing the main class, for example **com.example.hellospring**. Java packages do not use hyphens like artifacts do.

For instance, a class generated by Initializr may reside at:

~~~text
src/main/java/com/example/hellospring/HelloSpringApplication.java
~~~

And begin with the declaration:

~~~java
package com.example.hellospring;
~~~

Do not treat **Group** and **Package name** as two fields that must be identical. Group identifies the artifact; package organizes Java code and affects Spring Boot's default bean scanning area.

### Why choose Jar instead of War?

With **Jar**, Spring Boot can package the application and required components to run via the **java -jar** command. When Spring Web is selected in an appropriate Servlet configuration, an embedded HTTP server is integrated into this execution model. This is a common and convenient starting point.

**War** is usually better suited when the project needs to be deployed to an external servlet container under specific constraints. For a first project without such requirements, **Jar** is simpler.

## 4. Choose dependencies: start minimal but sufficient

Click **Add Dependencies** and search for **Spring Web**. This is the core dependency for the HTTP example in this lesson: it brings Spring MVC components, request/response handling, and an appropriate embedded server into the project.

When you select dependencies in Initializr, you are asking the generator to add the corresponding declarations to the build file. A **Starter** groups libraries commonly used together; Spring Boot's **auto-configuration** leverages the available libraries and configuration to automatically set up sensible default beans.

For a first learning project, **Spring Web** alone is enough to write a REST controller. Some other dependencies you may encounter are not yet required:

| Dependency | Purpose | Should You Choose It Now? |
|---|---|---|
| **Spring Web** | Build HTTP endpoints using Spring MVC | **Yes**, for this lesson's example |
| **Spring Boot DevTools** | Supports development experience, such as restarting on classpath changes | Optional |
| **Validation** | Supports input validation with Bean Validation | Add when validation is required |
| **Spring Data JPA** | Relational data access using the JPA approach | Only when a database/JPA is needed |
| **Spring Security** | Authentication and application protection mechanisms | Add when you have a security goal; default config affects endpoint access |
| **Actuator** | Provides observability, health, and management capabilities | Can be learned after getting the app running |

**Do not select every dependency just because it appears in the list.** Additional libraries can trigger auto-configuration, configuration requirements, or runtime behaviors that this exercise does not need yet. For example, selecting a database-related starter without a corresponding data source can cause startup to fail due to missing configuration.

Note that actual starter artifact names can differ across Spring Boot versions. Let Initializr generate the dependencies appropriate for the selected version; in this lesson we interact via the **Spring Web** selection name in the UI.

## 5. Generate, extract, and open the right project folder

After completing the form, click **Generate**. The browser downloads a ZIP file, for example **hello-spring.zip**. Extract it into your working directory, such as:

~~~text
projects/
└── hello-spring/
    ├── build.gradle
    ├── settings.gradle
    ├── gradlew
    ├── gradlew.bat
    ├── gradle/
    └── src/
~~~

The example above shows a **Gradle - Groovy** structure. If you chose Maven, the main build file will be **pom.xml**, accompanied by **mvnw**, **mvnw.cmd**, and the **.mvn/** directory.

**Open the correct root folder** containing **build.gradle** or **pom.xml**, rather than only opening the **src** folder. The IDE needs the build file to recognize the project, sync dependencies, and set up run configurations.

### Opening with an IDE

**IntelliJ IDEA:** use **Open** and select the extracted project folder. When the IDE asks whether to trust the project, confirm if this is indeed the project you just created; then let the IDE import and sync Gradle/Maven.

**Eclipse / Spring Tools:** import as an existing Gradle or Maven project, depending on the configuration you chose.

**Visual Studio Code:** open the root folder via **Open Folder**, ensuring the Java extension and appropriate Spring/Gradle or Maven support components are installed.

First-time dependency synchronization may take longer than subsequent runs because the build tool has to download missing components. If repository connection errors occur, check your network, proxy, or dependency repository configuration.

## 6. Read the generated project structure

With the **Gradle - Groovy** option, a simple structure looks like:

~~~text
hello-spring/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── build.gradle
├── settings.gradle
├── .gitignore
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/hellospring/
    │   │       └── HelloSpringApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/hellospring/
                └── HelloSpringApplicationTests.java
~~~

Filenames may be adjusted based on the values entered and generator version. Important locations to recognize:

| Path | Role |
|---|---|
| **build.gradle** | Plugins, Java toolchain, dependencies, and build configuration for Gradle - Groovy |
| **settings.gradle** | Gradle project setup and root project name |
| **pom.xml** | Equivalent build configuration file if generated with Maven |
| **gradlew / gradlew.bat** | Scripts to run the Gradle Wrapper on Unix/macOS and Windows |
| **mvnw / mvnw.cmd** | Maven Wrapper scripts if Maven was chosen |
| **src/main/java** | Java source code of the application |
| **src/main/resources** | Non-code resources and configuration |
| **src/test/java** | Test code |
| **application.properties** | Initial Spring Boot configuration; **application.yml** can be used as needed |
| **.gitignore** | List of files/folders that should not be committed to Git |

The **build/** (Gradle) and **target/** (Maven) directories typically appear **after building** and are not where you write source code. They contain generated outputs and can be rebuilt from source and project configuration.

### The startup class: the application entry point

Initializr creates a class with a structure similar to:

~~~java
package com.example.hellospring;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HelloSpringApplication {

    public static void main(String[] args) {
        SpringApplication.run(HelloSpringApplication.class, args);
    }
}
~~~

**main()** is the standard Java entry point. **SpringApplication.run(...)** creates and launches the Spring application context; Spring Boot reads configuration and applies appropriate auto-configurations.

The **@SpringBootApplication** annotation is a concise shorthand grouping important capabilities, including declaring Spring configuration, enabling auto-configuration, and component scanning. By default, component scanning searches for components in the startup class's package and its subpackages. Therefore, placing the main class in the root package **com.example.hellospring** and putting controllers/services underneath it is an intuitive layout for beginners.

You do not yet need to understand every initialized bean to run your first project. First recognize that **main() starts the application**, while additional classes handle business logic.

## 7. Run the application for the first time

You can run the **HelloSpringApplication** class directly from your IDE using the **Run** button, or use the wrapper from a terminal. The commands below are **the recommended learner workflow**, requiring no global Maven/Gradle installation.

### If you chose Gradle - Groovy

In Windows PowerShell, inside the folder containing **gradlew.bat**:

~~~powershell
.\gradlew.bat bootRun
~~~

On Linux or macOS:

~~~bash
./gradlew bootRun
~~~

### If you chose Maven

In Windows PowerShell, inside the folder containing **mvnw.cmd**:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

On Linux or macOS:

~~~bash
./mvnw spring-boot:run
~~~

**Use only the commands belonging to the build tool you selected in Initializr.** There is no reason to run both Maven and Gradle on the same newly generated skeleton.

If the project includes **Spring Web**, upon successful startup you will typically see logs indicating that the application has started and the HTTP server is listening. With default configuration, the port is usually **8080**. If another program is already using this port, Spring Boot may report a port-binding error.

One common point of confusion: visiting **http://localhost:8080/** right after generating the project may return **404 Not Found**. That does not necessarily mean the application is broken. The basic project does not yet have a controller returning data for the **/** path. We will create a dedicated endpoint in the next step.

To stop an application running in the terminal, typically press **Ctrl+C**. If running from an IDE, use the **Stop** button.

## 8. Create your first HTTP endpoint

In the example project, create the file:

~~~text
src/main/java/com/example/hellospring/HelloController.java
~~~

Add the contents:

~~~java
package com.example.hellospring;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "World") String name) {
        return Map.of("message", "Hello, " + name + "!");
    }
}
~~~

Key components:

1. **@RestController** tells Spring this class handles HTTP requests and that handler return values are written to the HTTP response body.
2. **@GetMapping("/hello")** maps HTTP **GET /hello** requests to the **hello(...)** method.
3. **@RequestParam** extracts the **name** parameter from the URL; if omitted, it uses **World**.
4. **Map<String, String>** holds the response data; with the JSON components provided by Spring Web, Spring MVC can serialize this value into JSON.

Because **HelloController** is in the same package as **HelloSpringApplication**, it falls within the default component scanning scope. You do not need to instantiate the controller yourself with **new** or register it manually.

After saving the file, if the application was already running without a suitable automatic restart mechanism, stop and restart it so the new code is compiled and loaded into the application.

### Send a test request

Use a browser or terminal to call:

~~~text
http://localhost:8080/hello
http://localhost:8080/hello?name=Lan
~~~

On Windows, use **curl.exe** to avoid confusion with PowerShell's alias:

~~~powershell
curl.exe "http://localhost:8080/hello?name=Lan"
~~~

Or use a PowerShell cmdlet:

~~~powershell
Invoke-RestMethod "http://localhost:8080/hello?name=Lan"
~~~

On Linux/macOS:

~~~bash
curl "http://localhost:8080/hello?name=Lan"
~~~

Expected JSON response:

~~~json
{
  "message": "Hello, Lan!"
}
~~~

This is the result of **the controller you just wrote**. Spring Initializr helped prepare the project and libraries; the request is handled because the project now has a **/hello** mapping and the application is running.

### Request flow in the example

~~~text
Browser / curl
         │
         │ GET /hello?name=Lan
         ▼
Embedded HTTP server
         │
         ▼
Spring MVC finds @GetMapping("/hello")
         │
         ▼
HelloController.hello("Lan")
         │
         ▼
Map: message = "Hello, Lan!"
         │
         ▼
HTTP response containing JSON
~~~

Later, as business logic grows more complex, controllers should delegate work to services rather than containing all processing. But in a first project, this small method lets you clearly observe the relationship between a request and a Java method.

## 9. Where is the application configured?

Initializr usually creates the file **src/main/resources/application.properties**. This is one of the places from which Spring Boot can read configuration. For example, to change the HTTP port from **8080** to **8081**, add:

~~~properties
server.port=8081
~~~

After restarting with the new configuration, use the URL:

~~~text
http://localhost:8081/hello?name=Lan
~~~

Spring Boot also supports YAML syntax in **application.yml**, with an equivalent example:

~~~yaml
server:
  port: 8081
~~~

Choose one declaration format consistently and avoid configuring the same key across multiple files before understanding configuration precedence. Besides in-project files, Spring Boot supports configuration sources such as environment variables and command-line arguments. That allows a single artifact to run in different environments with different configurations.

**Note:** The **server.port** setting only takes effect when the application actually uses a web server. Spring Boot can also build CLIs or workers that do not open an HTTP port.

## 10. Build and package as a JAR

During development, **bootRun** or **spring-boot:run** is convenient for running the project. When you want to produce a standalone runnable Java file, you **build** the project to obtain an executable JAR.

With Gradle on Windows:

~~~powershell
.\gradlew.bat bootJar
~~~

With Gradle on Linux/macOS:

~~~bash
./gradlew bootJar
~~~

The executable JAR file is located in **build/libs/**. With the example metadata, the name might look like:

~~~text
build/libs/hello-spring-0.0.1-SNAPSHOT.jar
~~~

Run that file from the project root directory:

~~~bash
java -jar build/libs/hello-spring-0.0.1-SNAPSHOT.jar
~~~

If you chose Maven, run:

~~~powershell
.\mvnw.cmd package
~~~

Or on Linux/macOS:

~~~bash
./mvnw package
~~~

The artifact is typically generated under **target/**, for example:

~~~bash
java -jar target/hello-spring-0.0.1-SNAPSHOT.jar
~~~

**The actual JAR filename and version may differ** depending on metadata and build configuration; check the generated file in the output directory rather than assuming the example above always matches.

Typical build operations also involve compiling and running tests according to the tool's lifecycle. If tests fail, read the errors and fix the cause; the build output file is only meaningful when packaging completes in accordance with project requirements.

### What does the build tool do when running?

Maven/Gradle uses the metadata generated by Initializr to:

- Identify compatible plugins and the Spring Boot version.
- Download declared dependencies along with required transitive dependencies.
- Compile Java code and process resources.
- Execute configured test and build steps.
- Package the artifact for execution or distribution.

Spring Initializr does not perform all of that work at Generate time. The ZIP contains the necessary source code and configuration; **building happens after you extract and run the build tool**.

## 11. Understand the relationship between Initializr, starters, and auto-configuration

These are three related concepts with distinct responsibilities:

| Component | When It Participates | Responsibility |
|---|---|---|
| **Spring Initializr** | At project creation | Generates directories, startup code, wrapper, and dependency declarations |
| **Spring Boot Starter** | When Gradle/Maven resolves libraries | Brings in a group of dependencies suited to a development need |
| **Spring Boot Auto-configuration** | When the application starts up | Inspects the classpath, beans, and configuration to set up appropriate components |

For example, choosing **Spring Web** makes Initializr add the appropriate starter to the build file. After building, the web libraries are on the classpath. When **SpringApplication.run(...)** runs, Spring Boot can auto-configure MVC, JSON conversion, and an appropriate HTTP server. Then, the **@GetMapping** method you wrote determines what data the endpoint returns.

Viewed sequentially:

~~~text
Generate        Build                  Runtime
────────        ─────                  ───────
Initializr  →   Starter dependencies → Auto-configuration
                                        │
                                        ▼
                                  Controller runs
~~~

Spring Boot saves effort with sensible defaults while still allowing you to change configuration, beans, and dependencies to match actual application requirements.

## 12. Common first-time errors

| Symptom | Common Cause | How to Handle |
|---|---|---|
| **java** is not recognized | JDK is not installed or environment configuration is incorrect | Check JDK installation, PATH, and IDE JDK configuration |
| Reports incompatible Java version | JDK used for building does not match Java level and Spring Boot version | Choose a compatible JDK and verify with **java -version** |
| IDE cannot download dependencies | Network, proxy, repository, or build configuration error | Check Gradle/Maven messages and repository connectivity |
| Cannot find **gradlew.bat** or **mvnw.cmd** | In the wrong directory or a different build tool was chosen | Open the root directory containing the right wrapper and build file |
| Cannot run **bootRun** | Project was created with Maven, or Gradle did not import properly | Use **spring-boot:run** if Maven; inspect the build file |
| Visiting **/** returns 404 | No mapping defined for the root path | Call the declared **/hello** endpoint instead |
| **/hello** returns 404 | Controller not compiled, outside scan scope, or application not restarted | Check package, file, mapping, and restart the app |
| **Port 8080 already in use** error | Another program is listening on port 8080 | Stop the process occupying the port or change **server.port** |
| Not seeing expected JSON | Spring Web was not selected or mapping/response is incorrect | Verify Initializr-generated dependencies and controller |
| Running JAR does nothing or fails | Wrong file selected, build failed, or incompatible JDK | Verify the actual artifact, startup logs, and **java -jar** command |

When diagnosing, distinguish **three phases**: generate/download errors, Gradle/Maven build-time errors, and Spring Boot startup or request-handling errors. Knowing which phase failed helps pinpoint the real cause.

A frequent case is that after generating the project, learners open the root URL, see **404**, and assume Spring Boot “is not running.” If the logs show the server started and **/hello** responds properly, a 404 on **/** simply means **there is no handler for that path**.

## 13. What if you do not want to build a web application?

Spring Initializr can generate a Spring Boot project **without Spring Web**. For example, if you want to write a file-processing tool run from the terminal:

1. Select Java, Maven or Gradle, and metadata as usual.
2. Do not select Spring Web if an HTTP server is not needed.
3. Write an **ApplicationRunner** or **CommandLineRunner** bean to perform the work after Spring initializes.
4. Manage application termination and exit codes according to CLI behavior.

A scheduled background-processing application can also be generated from Initializr and then have scheduling or message listeners added as needed. That clarifies a fundamental characteristic: **Initializr is not only for creating REST APIs**; the final application type depends on the dependencies and code you build.

## 14. Practice extending the project after initialization

Once **GET /hello** is running, you can develop the project further through a few small changes:

**Experiment A — Request parameter:** call **/hello?name=Minh**, then call **/hello** without a query string. Observe the role of **@RequestParam(defaultValue = "World")**.

**Experiment B — Extract a service:** create a **GreetingService** with a method returning a greeting; use constructor injection to pass the service into **HelloController**, then have the controller call the service.

**Experiment C — Change the port:** set **server.port=8081** in configuration, restart, and access the endpoint on the new port.

**Experiment D — Produce an artifact:** use the wrapper to build a JAR, run it with **java -jar**, and send the same HTTP request as when running in the IDE. Notice that application code does not need to change merely because the launch method changed.

**Experiment E — Inspect the source:** open the build file, the class with **@SpringBootApplication**, the controller, and the configuration file. Identify which parts were generated by Initializr and which parts are code you added.

These experiments help separate **project skeleton**, **dependencies**, **configuration**, **request-handling code**, and **how the application is run**.

## 15. When you finish this lesson, what do you have?

A basic Spring Boot project created via Spring Initializr that can run from an IDE or terminal; a **main()** class using **@SpringBootApplication**; a web dependency to serve HTTP; a controller you wrote at **GET /hello**; a configuration file allowing port changes; and the ability to package the application using the wrapper.

The focus of initialization is not memorizing every option on the form. Grasp the **causal chain**:

**Spring Initializr creates the project → Maven/Gradle downloads and builds dependencies → Spring Boot starts the ApplicationContext → your controller handles HTTP requests you define.**

From this skeleton, you can continue learning dependency injection, controller-service-repository structure, data handling, environment configuration, and testing in upcoming lessons without recreating the project from scratch.
