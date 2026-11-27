# Running Locally with Azure Functions Core Tools

## 1. Objective: Running Azure Functions on a Development Machine

In the **SPRING_CLOUD_FUNCTION** module, we build reusable business logic using `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. `FunctionCatalog` registers and looks up functions, composition chains multiple steps, and adapters allow the same logic to be invoked via HTTP, event streams, or serverless environments.

When deploying to **Azure Functions**, a Java handler is invoked by the Azure Functions Host upon a trigger. Before releasing to the cloud, we need to run the actual Azure runtime on a development machine to verify:

- Does the Azure Host start up and discover `@FunctionName` methods?
- Does the Spring Cloud Function adapter build the Spring context and inject handlers/services properly?
- Does `FunctionCatalog.lookup(...)` resolve the function or composition?
- Do the HTTP route, body, response, and validation follow the contract?
- Do Queue/Blob/Timer triggers connect to their sources and run as expected?
- Are logs, exceptions, retries, and invocation metadata observable while debugging?

**Azure Functions Core Tools** is the CLI suite providing a local Functions Host for developing, running, and testing function apps. For Java Maven projects, the Azure Maven plugin integrates Core Tools through the `azure-functions:run` goal. This is the execution workflow used throughout this lesson.

### After This Lesson, You Will Be Able To

1. Prepare a JDK, Maven, Azure Functions Core Tools v4, and Azurite when needed.
2. Check tool versions and resolve `func` installation conflicts on Windows.
3. Configure `host.json` and `local.settings.json` according to their roles.
4. Build and run the Spring Cloud Function Azure adapter with Maven or Gradle.
5. Call a local HTTP Trigger using cURL/PowerShell, inspecting status codes and responses.
6. Run Queue/Blob/Timer Triggers in an appropriate local environment.
7. Debug the Java worker from IntelliJ IDEA or VS Code.
8. Diagnose errors across Core Tools, the Java worker, Spring dependency injection, `FunctionCatalog`, and binding extensions.
9. Distinguish what can be verified locally from what still must be verified on Azure staging.

**Scope:** this lesson guides local development and execution for Java Azure Functions using the Spring Cloud Function Azure adapter. It does not replace dedicated lessons on production deployment configuration or cloud resource management.

## 2. Local Runtime Architecture

~~~mermaid
flowchart TB
    subgraph Dev["Developer machine"]
        A["Terminal / IDE"]
        B["Maven or Gradle"]
        C["Spring Cloud Function Azure adapter"]
        D["Java classes: @Component / @FunctionName"]
        E["local.settings.json + host.json"]
        F["Azurite (when Storage is needed)"]
    end
    subgraph LocalHost["Azure Functions Core Tools v4"]
        G["Azure Functions Host"]
        H["Java language worker"]
        I["Azure trigger / binding runtime"]
    end
    A --> B
    B --> C
    B --> G
    D --> H
    E --> G
    G --> I
    I --> H
    F <--> I
    H --> J["Spring ApplicationContext"]
    J --> K["FunctionCatalog"]
    K --> L["Supplier / Function / Consumer"]
    L --> H
    H --> M["HTTP response / output binding"]
~~~

Typical execution flow:

1. Maven compiles and packages the Java application.
2. `azure-functions:run` starts the local Azure Functions Host.
3. The Host reads `host.json`, local settings, and Azure Functions metadata.
4. The Host starts the Java language worker and dispatches invocations when triggers fire.
5. The Spring Cloud Function Azure adapter initializes the Spring context, creates `@Component` handlers, and injects dependencies.
6. The handler invokes function beans directly or via `FunctionCatalog`.
7. The handler returns an HTTP response or writes an output binding; the Host manages the trigger/binding lifecycle.

**Three components that do not replace one another:**

| Component | Responsibility | What It Does Not Replace |
| --- | --- | --- |
| **Core Tools / Functions Host** | Runs the local Azure runtime, loads functions, triggers, and bindings. | Does not write Spring business logic. |
| **Maven/Gradle Azure plugin** | Builds/packages, configures local execution, and integrates Core Tools. | Does not replace the Java compiler or Spring context. |
| **Spring Cloud Function Azure adapter** | Connects the Java Worker with Spring DI, `FunctionCatalog`, and the function model. | Does not auto-generate Azure triggers without Azure annotations/metadata. |

### 2.1. Local Execution Differs from Running Plain Spring Boot

A Spring Boot application can run via `java -jar` or `spring-boot:run`, yet those **do not start the Azure Functions Host**. For handlers with `@FunctionName`, you must run the local Functions Host to verify:

- Function discovery and binding metadata.
- Java worker startup.
- Trigger routing and authorization behavior.
- Real `ExecutionContext` supplied by the Azure runtime.
- HTTP response mapping and output bindings.

**Never use `java -jar` as sole proof that an Azure Function works.**

## 3. Tools to Prepare

| Tool | Role | Required in All Cases? |
| --- | --- | --- |
| **JDK** | Compiles and runs the Java worker/application. | Yes. |
| **Apache Maven or Gradle** | Builds and invokes the Azure Functions plugin. | One of the two, matching the project. |
| **Azure Functions Core Tools v4** | Local Functions Host and the `func` CLI. | Yes for this local workflow. |
| **Node.js/npm** | Installs Core Tools via npm or runs Azurite via npm. | Only if using that installation method. |
| **Azurite** | Emulates Azure Storage Blob/Queue/Table. | Only when Host/triggers/bindings use Storage. |
| **Azure CLI** | Signs in and manages cloud resources; used by some deploy flows. | Not needed for HTTP-only local tests. |
| **Java IDE** | Breakpoints, stack traces, and debugging. | Optional. |

### 3.1. Checking JDK and Maven

On Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
mvn -version
~~~

If the project uses Maven Wrapper:

~~~powershell
.\mvnw.cmd -version
~~~

Output should confirm:

- The Java version required by the project, e.g., Java 17.
- `JAVA_HOME` points to the JDK directory, not its `bin` folder.
- Maven runs on the intended JDK.
- Compiler release settings in `pom.xml` match the Java runtime used.

Example Maven configuration:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

This is an example for a Java 17 project; if your project uses a compiler plugin or parent-managed properties, follow the actual project config. Never set a Java target newer than the Azure/local worker runtime.

### 3.2. Checking Azure Functions Core Tools

~~~powershell
func --version
where.exe func
~~~

For a stable workflow, use **Azure Functions Core Tools v4**, compatible with Azure Functions runtime 4.x. Microsoft documentation also lists Azure Functions CLI v5 in preview; this lesson focuses on Core Tools v4 GA and the Azure Maven plugin for Java.

If `func --version` fails:

- Verify Core Tools is installed.
- Open a new terminal after installing so `PATH` refreshes.
- On Windows, run `where.exe func` to see which executable resolves.
- If multiple `func.exe` paths exist, resolve duplicate installations before continuing.

### 3.3. Checking Optional Tools

~~~powershell
node --version
npm --version
az version
~~~

`node`/`npm` are only needed if installing Core Tools or Azurite via npm. Azure CLI is only needed for signing in, syncing settings, or deploying to the cloud; it is unnecessary for simple local HTTP testing.

## 4. Installing Azure Functions Core Tools on Windows

Windows offers two common methods:

1. **MSI installer:** suited for users wanting CLI tools without Node.js.
2. **npm package:** suited for VS Code/Node.js environments and the Azure Functions extension.

Choose **one** method and use that same method for upgrades.

### 4.1. Installing via Windows MSI

1. Open the Microsoft Learn page on [installing Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local).
2. Select Windows and download the matching **64-bit MSI**.
3. Complete the installer wizard.
4. Open a new PowerShell window and run:

~~~powershell
func --version
where.exe func
~~~

Node.js is not needed when using the MSI installer.

### 4.2. Installing via npm

If Node.js and npm are already installed:

~~~powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
~~~

After installation:

~~~powershell
func --version
where.exe func
~~~

If `func` is not recognized, verify npm's global bin directory is in `PATH` and open a new terminal. Do not install both MSI and npm versions on the same machine hoping Windows picks the right one; Microsoft warns that mixed installations cause `PATH` conflicts.

### 4.3. Updating Core Tools

Update using **the same method used to install**:

- MSI: uninstall the old version per Windows instructions, then install the new MSI.
- npm: re-run npm install for major version 4.
- Chocolatey: use Chocolatey's upgrade flow if installed via Chocolatey.

After updating, re-check `func --version` and `where.exe func`. Ensure your IDE does not invoke a different Core Tools binary than your terminal.

### 4.4. macOS and Linux

macOS can install via Homebrew:

~~~bash
brew tap azure/functions
brew install azure-functions-core-tools@4
~~~

Ubuntu/Debian has official Microsoft packages for Core Tools v4; follow the official guide for your distribution and architecture. You can also use npm where a Node.js environment is appropriate.

Never copy APT commands blindly across Ubuntu/Debian versions without checking the corresponding package repository.

## 5. Creating a Java Project or Preparing an Existing Spring Cloud Function Project

### 5.1. Starting a New Azure Java Functions Project

Microsoft recommends the **Azure Functions Maven archetype** for Java. In an empty directory:

~~~powershell
mvn archetype:generate "-DarchetypeGroupId=com.microsoft.azure" "-DarchetypeArtifactId=azure-functions-archetype" "-DjavaVersion=17"
~~~

Maven prompts for `groupId`, `artifactId`, `version`, and the Java package. Once confirmed, the archetype generates a sample Java Azure Functions project containing:

- A Maven build file.
- A sample HTTP-triggered Java function.
- `host.json`.
- `local.settings.json` for local development.
- Azure Functions Maven plugin configuration.

This is for initializing **new projects**. Do not run the archetype inside an existing Spring Cloud Function project directory, as it can overwrite or conflict with files and structure.

### 5.2. If the Project Already Has the Spring Cloud Function Azure Adapter

In an existing project, verify:

- `pom.xml` or `build.gradle` exists.
- `spring-cloud-function-adapter-azure` is present.
- Compatible Azure Java Functions library is present.
- Azure Maven/Gradle plugin is configured.
- `@Component` handler has `public` `@FunctionName` methods.
- Spring Boot main class is identified by the adapter.
- `host.json` and appropriate local settings exist.

**You do not need to run `func init` or `func new` to scaffold Java functions as in other language templates.** Java uses the Maven archetype/plugin as its primary workflow; if you already have Spring Cloud Function sources, add the adapter/handler/package configuration directly to the project.

### 5.3. Example Directory Structure

~~~text
spring-cloud-function-azure/
├── pom.xml
├── local.settings.json
└── src/
    ├── main/
    │   ├── java/example/azure/
    │   │   ├── OrderFunctionApplication.java
    │   │   └── OrderAzureHandler.java
    │   └── resources/
    │       ├── host.json
    │       └── application.properties
    └── test/
        └── java/example/azure/
            └── OrderFunctionApplicationTest.java
~~~

`local.settings.json` normally lives at the **project root**, not inside `src/main/resources` where it would be packaged into the JAR like a normal application config file.

## 6. Configuring host.json and local.settings.json

### 6.1. host.json

`host.json` configures the **Azure Functions Host**, shared across all functions in a Function App. Minimal template:

~~~json
{
  "version": "2.0"
}
~~~

A configuration explicitly setting the HTTP route prefix (host default is `api`):

~~~json
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": "api"
    }
  }
}
~~~

With this configuration, route `orders/normalize` becomes `/api/orders/normalize`. Setting `routePrefix` to an empty string removes the `/api` prefix.

Some triggers require binding extensions and extension-specific settings. Do not add extension bundles or binding-specific settings just because another function used them; consult documentation for the triggers/extensions you actually use.

### 6.2. local.settings.json

This file provides **environment/app settings for local runs**, primarily inside the `Values` collection. Example for the Spring Cloud Function Azure adapter:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

Explanation:

| Setting | Meaning |
| --- | --- |
| `IsEncrypted` | Indicates whether local settings have been encrypted by Core Tools. |
| `FUNCTIONS_WORKER_RUNTIME=java` | Selects the Java worker runtime. |
| `FUNCTIONS_EXTENSION_VERSION=~4` | Selects the Azure Functions 4.x runtime. |
| `MAIN_CLASS` | Explicitly points the adapter to the Spring Boot application class when needed. |
| `AzureWebJobsStorage` | Storage connection for the host/bindings; `UseDevelopmentStorage=true` targets Azurite. |

`MAIN_CLASS` must be the **fully qualified name** of the Spring application class, e.g., `example.azure.OrderFunctionApplication`; do not point it to `OrderAzureHandler`. If the adapter resolves the main class from the manifest, this setting may be optional, yet specifying it explicitly prevents confusion in multi-entrypoint projects.

`AzureWebJobsStorage` depends on hosting/triggers and host operations. For Queue/Blob/Timer triggers or features requiring host storage, configure a valid connection. For pure HTTP functions that do not need storage, check actual runtime/adapter requirements rather than blindly adding a cloud connection string.

### 6.3. Distinguishing the Three Configuration Files

| File | Read By | Used For |
| --- | --- | --- |
| `host.json` | Azure Functions Host | Triggers, bindings, logging, and host behavior. |
| `local.settings.json` | Core Tools local runtime | App settings and connections during local development. |
| `application.properties` | Spring Boot | Business configuration, Spring logging, bean configuration. |

Example `application.properties`:

~~~properties
logging.level.example.azure=INFO
spring.cloud.function.definition=normalizeOrder
~~~

The property `spring.cloud.function.definition` applies to adapters/flows using SCF's default definition; when a handler explicitly calls `catalog.lookup("normalizeOrder")`, this property does not auto-create an Azure route or replace the handler. Only declare it when the app actually relies on it.

### 6.4. Protecting Local Settings

`local.settings.json` may contain connection strings, keys, or secrets:

- Add this file to `.gitignore` per project policy; never commit secrets.
- Use **development** resource connections, never accidentally pointing to production.
- Core Tools supports encrypting local settings via `func settings encrypt`; local encryption does not replace production secret management.
- When publishing, local settings are **not automatically synced to Azure by default**. Manage cloud App Settings separately through approved processes.
- If pulling settings from Azure to local, note that it can overwrite existing local values.

### 6.5. Do Not Use the Storage Emulator for Every Service

`UseDevelopmentStorage=true` works only with the **Azurite Azure Storage emulator**. Azurite supports Blob, Queue, and Table; it does not emulate Service Bus, Event Hubs, Cosmos DB, or other Azure services. For those bindings, use dedicated dev resources, proper connections, or appropriate test doubles.

## 7. Running Azurite When Azure Storage Is Needed

### 7.1. When Is Azurite Needed?

| Function / Host Behavior | Is Azurite Needed? |
| --- | --- |
| Pure HTTP Trigger, no Storage used | Typically no separate Azurite instance needed. |
| Azure Storage Queue Trigger/Output | Yes, if testing locally with the Storage emulator. |
| Blob Trigger/Input/Output | Yes, if testing locally with the Blob emulator. |
| Timer Trigger | Depends on host/storage config; Timer may use host storage for coordination. |
| Service Bus Trigger | No; requires a Service Bus dev resource or emulator. |
| Event Hubs Trigger | No; requires an Event Hubs dev resource/connection. |

### 7.2. Installing Azurite via npm

If Node.js/npm is installed:

~~~powershell
npm install -g azurite
~~~

Create a data workspace:

~~~powershell
New-Item -ItemType Directory -Force -Path C:\azurite
~~~

Run Azurite in a **separate terminal**:

~~~powershell
azurite --silent --location C:\azurite
~~~

Keep that terminal open while running the Azure Functions Host. By default, Azurite uses:

| Storage Service | Port |
| --- | ---: |
| Blob | 10000 |
| Queue | 10001 |
| Table | 10002 |

You can enable debug logging:

~~~powershell
azurite --location C:\azurite --debug C:\azurite\debug.log
~~~

### 7.3. Using Docker Instead of a Global npm Install

If Docker is installed:

~~~powershell
docker run -p 10000:10000 -p 10001:10001 -p 10002:10002 -v C:\azurite:/data mcr.microsoft.com/azure-storage/azurite
~~~

This is an example command on Windows PowerShell. The host directory must exist and Docker Desktop must be running. Expose only the ports your project needs if you want to restrict scope.

### 7.4. Checking Azurite Before Starting the Function

- The Azurite terminal does not report port-in-use errors.
- Storage Explorer can connect to the emulator if you need to inspect Queues/Blobs.
- `AzureWebJobsStorage` in `local.settings.json` uses `UseDevelopmentStorage=true`.
- Queues/containers are created with the exact expected names before sending messages, or created via appropriate tooling.
- Never allow the local host to accidentally point to a production Storage account.

## 8. Building and Running Java Azure Functions with Maven

### 8.1. Build First

From the root directory containing `pom.xml`:

~~~powershell
.\mvnw.cmd clean package
~~~

If the project does not have a Maven Wrapper:

~~~powershell
mvn clean package
~~~

The build must complete cleanly before starting the local Host. In the logs, verify:

- The Java compiler uses the intended JDK.
- The Spring Cloud Function Azure adapter resolves cleanly.
- The Azure Functions Maven plugin is configured.
- The plugin processes `@FunctionName` methods and trigger annotations.
- The build produces staging metadata/packages per project config.

### 8.2. Running Locally with the Azure Maven Plugin

~~~powershell
.\mvnw.cmd azure-functions:run
~~~

Or:

~~~powershell
mvn azure-functions:run
~~~

This is the primary Java Maven workflow recommended by Microsoft and Spring Cloud Function. The Azure Maven plugin launches the local Functions Host via Core Tools and prepares the Java application from project configuration.

**Never run `func init` once the project already has an Azure Java Maven layout.** Also never run `SpringApplication.run` in a second terminal as a substitute for the Functions Host.

### 8.3. Expected Host Startup Output

Logs typically show output similar to:

~~~text
Azure Functions Core Tools
Core Tools Version: 4.x
Function Runtime Version: 4.x

Worker process started and initialized.

Functions:

    normalizeAzureOrder: [POST] http://localhost:7071/api/orders/normalize
~~~

Exact log lines and formatting vary by Core Tools/plugin version. Verify that:

- The Host started cleanly.
- The Java worker initialized.
- The Azure Function name appears.
- The HTTP URL, method, and route match annotations/metadata.
- No Spring context, dependency injection, or `FunctionCatalog` lookup errors occurred.

### 8.4. Stopping the Host

Press `Ctrl+C` in the terminal running `azure-functions:run`. Wait for both the Host and Java worker to shut down completely before restarting or launching another host.

Only **one Functions Host for the same local project/port** should run during testing at a time.

## 9. Running with Gradle

If the project uses Gradle and configures the Azure Functions plugin:

~~~powershell
.\gradlew.bat clean jar --info
~~~

Then:

~~~powershell
.\gradlew.bat azureFunctionsRun
~~~

On macOS/Linux:

~~~bash
./gradlew clean jar --info
./gradlew azureFunctionsRun
~~~

The Azure Gradle plugin handles building/packaging and invoking the local runtime. Exact task names/configs depend on the plugin version pinned in `build.gradle`; check the project's task list if names differ.

**Never mix Maven and Gradle for the same release** without an explicitly defined build process. Pick one build tool as the single package source to avoid inconsistent staging artifacts.

## 10. Calling a Local HTTP Trigger

### 10.1. Default URL

The local Azure Functions Host defaults to:

~~~text
http://localhost:7071
~~~

With the default `routePrefix` of `api`, a trigger:

~~~java
@FunctionName("normalizeAzureOrder")
public HttpResponseMessage normalize(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/normalize")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    // ...
}
~~~

has the URL:

~~~text
POST http://localhost:7071/api/orders/normalize
~~~

Always take the exact URL from the **host startup output**; route prefixes and ports can be customized.

### 10.2. Sending Requests with cURL

Open a second terminal while the Azure Functions Host is still running:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/normalize" \
  -H "Content-Type: text/plain" \
  --data " dh-701 "
~~~

Assuming the function uppercases and adds a prefix, the expected body is:

~~~text
REF-DH-701
~~~

Depending on your code and response builder, content-type headers and status codes may vary. Do not treat another lesson's sample response as your contract; use the output defined by your own project's function.

### 10.3. Sending Requests from Windows PowerShell

Windows PowerShell 5.1 aliases `curl`, so invoke `curl.exe` explicitly:

~~~powershell
curl.exe -i -X POST "http://localhost:7071/api/orders/normalize" -H "Content-Type: text/plain" --data " dh-701 "
~~~

Or use PowerShell cmdlets:

~~~powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:7071/api/orders/normalize" -ContentType "text/plain" -Body " dh-701 "
~~~

`Invoke-RestMethod` is convenient when you only need the body. To inspect detailed status codes and headers, use `Invoke-WebRequest` or `curl.exe -i`.

### 10.4. Testing Valid and Invalid Inputs

| Request Body | Expected Result per Example | Purpose |
| --- | --- | --- |
| `" dh-701 "` | `REF-DH-701`, HTTP 200 | Tests trimming/uppercasing/composition. |
| `"   "` | HTTP 400 | Blank-input validation. |
| Empty body | HTTP 400 | Confirms handler rejects invalid input before calling function. |
| `"dh-702"` | Depends on function contract; e.g., requires valid order fields | Checks schema/input format. |

If the function expects JSON, set `Content-Type: application/json` and send valid JSON; if it expects text, use `text/plain`. HTTP body and content type must match the adapter's converters/contract.

### 10.5. Authorization During Local Runs

With `AuthorizationLevel.FUNCTION`, cloud Azure enforces function keys per host policy. However, **the local Functions Host does not enforce access keys like the cloud environment** in standard Core Tools workflows. Therefore:

- Local requests may succeed without a key.
- Never conclude a production endpoint is secured just because local requests work.
- Test function keys, authentication, and network restrictions on Azure staging.
- Never commit or log keys during testing.


## 11. Running Non-HTTP Triggers Locally

HTTP is the easiest trigger to test because it only requires calling a URL. Event-driven triggers need an event source or another trigger mechanism.

### 11.1. Queue Trigger with Azurite

If a method uses `@QueueTrigger`:

~~~java
@FunctionName("processOrder")
public void processOrder(
        @QueueTrigger(
                name = "order",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String payload,
        ExecutionContext context) {
    // Invoke Spring function/service.
}
~~~

Requirements:

1. Azurite is running and its Queue service is reachable.
2. `AzureWebJobsStorage` points to Azurite.
3. The `orders-input` queue exists or is created by tooling.
4. The local Host is running and has discovered `processOrder`.
5. A valid message is sent to the queue.

You can use Azure Storage Explorer to create the queue and enqueue messages, or use an Azure Storage SDK/CLI tool. Azurite does not automatically pre-create application queues upon startup.

### 11.2. Blob Trigger

With `@BlobTrigger`, you need Azurite's Blob service or a dev Azure Storage account with the target container/path. Uploading a file to the container triggers the function per extension behavior. Watch host logs to observe trigger processing.

Blob triggers can exhibit detection latency depending on trigger source/extension; do not expect uploads and invocations to occur synchronously and instantaneously.

### 11.3. Timer Trigger

`@TimerTrigger` uses the Azure Functions Host's NCRONTAB schedule. When running locally, that schedule applies; for example:

~~~java
@TimerTrigger(
        name = "timer",
        schedule = "0 */1 * * * *")
String timerInfo
~~~

This expression illustrates firing every minute at second 0. Timers need no HTTP request to fire. For quick testing, choose a reasonable schedule and inspect host logs; avoid overly tight schedules that create load or noisy logs.

### 11.4. Service Bus, Event Hubs, and Other Services

Azurite does **not** emulate Service Bus or Event Hubs. When functions use those triggers, choose one of these options:

- Connect to a dedicated development resource in Azure.
- Use an emulator/test infrastructure supported by that service.
- Unit test the business function with simulated messages while verifying bindings in integration/staging tests.

Never put production connection strings into local settings. When local runs connect to cloud resources, messages can actually be consumed, written, or emitted to that service.

## 12. Debugging the Java Worker from an IDE

### 12.1. Starting the Maven Plugin in Debug Mode

Stop any normally running host, then run:

~~~powershell
.\mvnw.cmd azure-functions:run -DenableDebug
~~~

Or:

~~~powershell
mvn azure-functions:run -DenableDebug
~~~

The Java worker typically opens a debug socket on port `5005`. Check startup logs to confirm a line like `Listening for transport dt_socket at address: 5005`.

### 12.2. Attaching the Debugger in IntelliJ IDEA

1. Open the Maven project in IntelliJ.
2. Select **Run -> Edit Configurations**.
3. Add a **Remote JVM Debug** configuration.
4. Host `127.0.0.1`, port `5005`, transport `Socket`.
5. Start `azure-functions:run -DenableDebug`.
6. Attach the debugger.
7. Place breakpoints inside the Azure handler or Spring functional bean.
8. Send an HTTP request from a second terminal to hit the breakpoint.

### 12.3. Attaching the Debugger in Visual Studio Code

Illustrative `.vscode/launch.json` configuration:

~~~json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "java",
      "name": "Attach to Azure Functions Java Worker",
      "request": "attach",
      "hostName": "127.0.0.1",
      "port": 5005
    }
  ]
}
~~~

Run the Maven debug goal, then select the attach configuration. Send an HTTP request so the debugger pauses at your breakpoint.

**Security:** the debug port should only listen on loopback/local developer machines. Never expose a remote debugger port publicly in Azure environments or untrusted networks.

### 12.4. Debugging the Host vs. Debugging the Java Worker

- **Functions Host logs:** discovery, triggers, bindings, routes, and host lifecycle.
- **Java worker debugger:** Java code, Spring handlers, function beans, and stack traces.
- **Spring logs:** context startup, bean creation, catalog registration, and dependency injection.

If a breakpoint never hits, the failure may occur **before the Java method is called**, such as the Host failing to discover the function or a binding not firing.

## 13. Reading Logs and Observing Invocations

### 13.1. Three Log Sources

| Source | Contents | Where to View |
| --- | --- | --- |
| Azure Functions Host | Worker startup, function discovery, triggers/bindings, HTTP routes. | Terminal running `azure-functions:run`. |
| Java/Spring application | Bean startup, services, `FunctionCatalog`, business errors. | Same terminal or IDE console per logging config. |
| Storage emulator | Queue/Blob requests, connections, and storage errors. | Azurite terminal or log file. |

### 13.2. Logging from ExecutionContext

The Azure handler receives `ExecutionContext` on each invocation:

~~~java
context.getLogger().info(
        "Function=" + context.getFunctionName()
        + ", invocation=" + context.getInvocationId());
~~~

`getInvocationId()` is the ID of **one execution attempt**, not a business event ID. A retried Queue message can get a new invocation ID. When idempotency is needed, use a stable business event ID.

### 13.3. Never Log Sensitive Data

Do not log:

- Function keys, connection strings, access tokens.
- `Authorization` headers or cookies.
- Full request bodies containing personal data.
- `local.settings.json` verbatim.
- Runtime objects or all headers indiscriminately.

Prefer logging the function name, invocation ID, allowed correlation IDs, processing status, and error codes.

### 13.4. Tuning Spring Logging

You can configure `src/main/resources/application.properties`:

~~~properties
logging.level.root=INFO
logging.level.example.azure=DEBUG
~~~

Avoid broad `DEBUG` logging in production if logs capture sensitive payloads or metadata. Local and cloud log levels can differ due to environment-specific app settings.

## 14. Troubleshooting Local Runs

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `func` is not recognized | Core Tools not installed or `PATH` not refreshed. | `func --version`, `where.exe func`, open a new terminal. |
| Wrong Core Tools version | Overlapping MSI/npm/Chocolatey installs. | Check all `func.exe` paths and keep only one install method. |
| Maven cannot find `azure-functions:run` | Missing Azure Functions Maven plugin or wrong plugin version. | Inspect `pom.xml` and effective Maven configuration. |
| Host fails to start | Invalid `host.json`, port busy, or missing runtime dependency. | Read the earliest startup error, check port 7071 and config. |
| Port 7071 already in use | Another Functions Host is already running. | Stop the old process/terminal before restarting. |
| Function missing from list | Plugin did not generate annotations/metadata. | `@FunctionName`, `public` method, trigger annotation, staging package. |
| Host sees function, but call fails in Spring | Handler not Spring-managed or wrong main class. | `@Component`, component scan, `MAIN_CLASS`, adapter. |
| `NoSuchBeanDefinitionException` | Missing service/function bean or component scan issue. | Spring Boot main class and package layout. |
| `FunctionCatalog.lookup(...)` returns null | Wrong function bean name/definition or bean not registered. | Check `@Bean` name, catalog tests, and dependency versions. |
| `UnsupportedClassVersionError` | JDK compile target is newer than the Java runtime. | `java -version`, `mvn -version`, compiler release, and runtime. |
| Worker process fails to initialize | Wrong `JAVA_HOME`/`PATH` or missing dependencies/classpath. | Verify JDK, main class, Azure adapter, and package layout. |
| HTTP 404 | Wrong route or `/api` prefix. | Use the URL printed by the host; check `host.json` `routePrefix` and `@HttpTrigger`. |
| HTTP 405 | Wrong HTTP method sent. | Compare against `methods` in the trigger annotation. |
| HTTP 400 | Request body violates business contract. | Check body, content type, and validation. |
| HTTP 500 | Business, conversion, DI, or dependency error. | Read Java stack trace, root cause, and function logs. |
| Local HTTP key not required | Local Core Tools does not enforce keys like cloud. | Expected local difference; test auth separately on Azure. |
| Queue Trigger does not run | Azurite not running, wrong queue/connection. | Port 10001, queue name, `AzureWebJobsStorage`, and host logs. |
| Blob Trigger misses files | Wrong container/path, Blob service not running. | Port 10000, binding expression, extension, and upload target. |
| `UseDevelopmentStorage=true` fails | Azurite not running or wrong emulator endpoint. | Start Azurite, verify ports and settings. |
| Debugger fails to attach | Debug mode not enabled or port 5005 busy. | `-DenableDebug`, worker logs, host/port, and IDE config. |
| Two local hosts conflict | Old terminal/IDE run still active. | Stop old host; run only one instance per project/port. |

### 14.1. Ordered Investigation Workflow

~~~text
1. Tools: are java, mvn, func at the right version/PATH?
2. Project: are Azure adapter, Java library, and plugin in dependencies/build?
3. Settings: are host.json, local.settings.json, MAIN_CLASS correct?
4. Build: did Maven/Gradle package succeed and generate metadata?
5. Host: did Core Tools start and Java worker initialize?
6. Discovery: does Host list the expected @FunctionName and trigger?
7. Spring: did ApplicationContext/DI/FunctionCatalog initialize?
8. Request/event: are route, payload, connection, and binding right?
9. Business: are function output and error mapping right?
10. Security: secrets, keys, cloud settings, and permissions?
~~~

Do not bulk-change plugin or Java versions before knowing which layer is failing. Note the **first error** in the startup log; later errors are often just downstream consequences.

## 15. How Local Tests Differ from Cloud Tests

| Item | Local Core Tools | Azure Staging / Cloud |
| --- | --- | --- |
| Functions Host | Local host via Core Tools. | Azure-managed host. |
| Java worker | Java process on dev machine. | Function App / hosting plan Java runtime. |
| Spring DI | Fully testable via the adapter. | Must be confirmed on the real deployment package. |
| `FunctionCatalog` | Test local lookups/compositions. | Verify matching dependency/runtime versions in the cloud. |
| HTTP route | Calls `localhost:7071`. | Function App domain, real auth and networking. |
| Function key | Not enforced like cloud in typical local flows. | Enforced per `authLevel`/host policy. |
| Storage | Azurite or dev account. | Real Azure Storage and IAM/managed identities. |
| Service Bus / Event Hubs | Dev resource or matching emulator. | Real cloud resources, networking, and permissions. |
| Cold start / scale | Does not fully simulate hosting plan behavior. | Depends on hosting plan and actual load. |
| Observability | Terminal/IDE/emulator logs. | Azure Monitor / Application Insights per config. |
| Secrets | Local settings / dev secrets. | App Settings / Key Vault / managed identities. |

**Passing locally does not mean production-ready.** Factors such as the Azure Java runtime, identities, networking, scaling, binding extensions, and deployment configuration require staging smoke tests.

### 15.1. Do Not Use local.settings.json as Production Config

Azure Function Apps use **Application Settings** in the cloud. Settings in `local.settings.json` are not automatically synced to the cloud by default. When syncing is needed, use appropriate tooling and review every setting before writing; fetching settings can overwrite local files.

### 15.2. When to Use Real Azure Dev Resources

Some services lack equivalent local emulators. If you must test against real Azure dev resources:

- Use a separate, authorized dev subscription/resource group.
- Isolate dev queues/containers/topics from production.
- Use least-privilege identities/credentials.
- Monitor costs and data created/consumed.
- Never send test messages to production systems.
- Clean up test data per project procedures.

## 16. Recommended Local Workflow

A repeatable loop:

1. **Check environment:** `java -version`, `mvn -version`, `func --version`.
2. **Prepare settings:** `host.json`, `local.settings.json`, Spring properties.
3. **Start Azurite** if the project uses Blob/Queue/Table Storage.
4. **Build:** `mvn clean package` or the equivalent Gradle task.
5. **Run Host:** `mvn azure-functions:run` or `gradle azureFunctionsRun`.
6. **Verify discovery:** check the function list and URLs in startup logs.
7. **Call HTTP:** send both valid requests and invalid inputs.
8. **Send events:** enqueue Queue messages or upload Blobs when testing non-HTTP triggers.
9. **Debug/logs:** attach the debugger, read host/Java logs, locate invocation IDs.
10. **Stop host/emulator:** avoid leftover processes/ports when switching projects.
11. **Run automated tests:** unit, Spring context, and integration tests.
12. **Staging smoke test:** only after local behavior stabilizes and cloud resources are ready.

### 16.1. Version-Check Script on Windows

Run these commands before starting:

~~~powershell
java -version
mvn -version
func --version
where.exe func
node --version
az version
~~~

If you do not use npm/Azurite/Azure CLI, the corresponding commands are optional. Record outputs when reporting issues to your team; it quickly exposes environment differences.

### 16.2. One Host, One Project, One Clear Configuration

Do not run multiple hosts on the same port, do not reuse Project A's local settings while running Project B, and do not let two different plugin versions generate inconsistent packages. If multiple configurations are needed, use separate profiles/environments and test explicitly.

## 17. Practice Exercises

1. **Install Core Tools:** install Core Tools v4 using one method on Windows, run `func --version` and `where.exe func`, and record the resolved path.
2. **Check JDK/Maven:** verify `JAVA_HOME`, `java -version`, and `mvn -version` all point to the same JDK.
3. **Build Java project:** run `mvn clean package` or Maven Wrapper and confirm the Azure plugin completes.
4. **Run local HTTP:** use `azure-functions:run`, send a POST to the printed host URL, and confirm the response.
5. **Test validation:** send a blank body, malformed body, and valid body; compare HTTP 400 vs. 200.
6. **Test Spring DI:** intentionally mistype a function name in `catalog.lookup(...)`, observe fail-fast startup, then fix it.
7. **Use Azurite:** start Azurite, create a queue, send a message, and verify the Queue Trigger fires.
8. **Timer Trigger:** configure a short local schedule, observe invocation logs, and stop the host cleanly.
9. **Debug Java:** run with `-DenableDebug`, attach the IDE on port 5005, and hit breakpoints in the handler/function bean.
10. **Port conflict:** start one host, attempt to start a second host, observe the error, then stop the old instance.
11. **Distinguish local vs. cloud:** list five settings that must be re-verified on Azure staging (runtime, auth, identity, storage, app settings).
12. **Never commit secrets:** verify `local.settings.json` is ignored by Git and contains no production data.

## 18. Self-Assessment Questions

- Which component does Azure Functions Core Tools provide when running locally?
- Why don't `java -jar` or `spring-boot:run` replace the Azure Functions Host?
- For Java, why is the Maven archetype/Azure Maven plugin usually preferred over `func init`/`func new`?
- How do `host.json` and `local.settings.json` differ?
- When is Azurite needed, and which Storage services does it support?
- What does `UseDevelopmentStorage=true` point to?
- Should `MAIN_CLASS` point to the Spring Boot application class or the Azure handler?
- Why must you check the function list in startup output before sending HTTP requests?
- Which port and route prefix does the default local URL use?
- Why can a local HTTP function succeed without a function key?
- When is `-DenableDebug` needed, and what is the default debug port?
- What message source and connection does a local Queue Trigger require?
- Why isn't a Spring context test alone enough to prove an Azure binding works?
- When should local runs connect to real Azure dev resources instead of an emulator?
- Which differences must be re-verified on Azure staging before production?

## 19. Official References

- [Microsoft Learn — Develop Azure Functions locally by using Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): installing Core Tools, running the Functions Host, HTTP/non-HTTP triggers, local settings, and the Java Maven workflow.
- [Microsoft Learn — Code and test Azure Functions locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-develop-local): local runtime, syncing settings, testing HTTP, triggers, and storage emulators.
- [Microsoft Learn — Quickstart: Create a Java Function from the command line](https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-first-java-maven): Java JDK, Maven archetype, Core Tools, running Maven locally, and HTTP testing.
- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, Spring DI, `@Component` handlers, `FunctionCatalog`, and Maven/Gradle local execution.
- [Microsoft Learn — Install and run the Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite): installing Azurite via npm/Docker/VS Code and configuring local endpoints.
- [Microsoft Learn — Use the Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite): limitations and differences between Azurite and real Azure Storage.
- [Microsoft Learn — Azure Functions Java ExecutionContext](https://learn.microsoft.com/en-us/java/api/com.microsoft.azure.functions.executioncontext): invocation ID, function name, and logger.
- [Microsoft Learn — Debug Java Azure Functions](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/getting-started-with-spring-cloud-function-in-azure): `azure-functions:run -DenableDebug`, Java worker port 5005, and remote attach.
- [Microsoft Learn — Azure Functions Core Tools reference](https://learn.microsoft.com/en-us/azure/azure-functions/functions-core-tools-reference): `func` commands, host startup, and options.

**Conclusion:** Running locally with **Azure Functions Core Tools** lets you test your application in a Functions Host closely matching the Azure runtime before deploying. For Spring Cloud Function Java projects, prepare the right JDK/Maven/Core Tools, configure `host.json` and `local.settings.json`, start the host with `azure-functions:run`, and verify function discovery, HTTP/event triggers, Spring DI, and `FunctionCatalog`. Use Azurite for Azure Storage when appropriate, debug the Java worker when needed, and always re-verify authentication, identities, runtime, settings, and trigger behavior on Azure staging before going to production.
