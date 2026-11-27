# Adapter Dependencies and Integrating Spring with Azure Functions

## 1. Lesson Objectives

**Azure Functions** provides a serverless environment that runs code in response to a *trigger* such as an HTTP request, timer, Queue Storage, Blob Storage, or events from Azure services. In the Java model, Azure Functions looks for `public` methods annotated with `@FunctionName`, reads the trigger/binding annotations, and executes the method when an event occurs.

**Spring Cloud Function (SCF)** has a different goal: encapsulating business logic into `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`, registering them via `FunctionCatalog`, and supporting *composition* and message conversion so the same function can be reused across HTTP, event streams, or serverless platforms.

To make the two systems work together, **`spring-cloud-function-adapter-azure`** bridges the **Azure Java Worker** and the Spring application context: a handler with `@FunctionName` can be managed by Spring as a `@Component`, inject Spring beans or `FunctionCatalog`, and invoke the business logic.

This lesson explains the **exact dependencies to add**, the role and limitations of the adapter, how to configure Spring with Azure Functions, an HTTP trigger example using composition, the packaging workflow with the Azure plugin, as well as how to test locally and diagnose errors.

After this lesson, you will be able to:

1. Distinguish between an Azure trigger/binding, an Azure Java handler, a Spring bean, and a Spring Cloud Function.
2. Choose the right dependency between `spring-cloud-function-adapter-azure` and `spring-cloud-function-adapter-azure-web`.
3. Configure Maven/Gradle and avoid the wrong Spring Boot executable JAR format.
4. Write an Azure `@FunctionName` handler as a Spring `@Component` and inject `FunctionCatalog`.
5. Test business logic independently of Azure, run with Functions Core Tools, and package for deployment.
6. Understand why `FunctionInvoker` is an older deprecated model and avoid using it as the default approach.

## 2. Architecture: The Adapter Bridges Two Models

~~~mermaid
flowchart LR
    A["HTTP / Timer / Queue / Blob Event"] --> B["Azure Functions Host"]
    B --> C["Azure Java Worker"]
    C --> D["Handler @FunctionName<br/>+ trigger annotation"]
    E["spring-cloud-function-adapter-azure"] -. "wires Spring DI" .-> D
    F["Spring ApplicationContext"] --> E
    F --> G["FunctionCatalog"]
    H["Bean Supplier / Function / Consumer"] --> G
    D -->|"lookup(name) / composition"| G
    G --> I["Business Function"]
    I --> D
    D --> J["HTTP response / output binding"]
~~~

**A request crosses these boundaries:**

1. **Azure Functions Host** receives the trigger; it does not directly invoke an arbitrary `@Bean Function`.
2. **Azure Java Worker** uses metadata generated from annotations and the Azure build plugin to invoke the handler method.
3. **Spring Cloud Function Azure adapter** connects the Azure Java Worker with the Spring context, allowing the handler to be managed by Spring and use dependency injection.
4. **The handler** performs the translation between the trigger and the business contract: reading the body, headers, and metadata; calling `FunctionCatalog`; and building the response or output binding.
5. **The business function** only processes input/output values and does not need to import the Azure Functions SDK unless it directly depends on the protocol.

This is a **serverless adapter**, not a message broker, and not a web server application listening on a Spring Boot HTTP port. The Azure Host and worker manage the invocation lifecycle; the Spring context is initialized by the adapter to provide beans to the handler.

### 2.1. Three Interfaces Do Not Equal Three Azure Triggers

| SCF Interface | Meaning | How It Combines with Azure Functions |
| --- | --- | --- |
| `Supplier<T>` | Produces/retrieves a value with no input. | Can be called by a handler when a Timer Trigger or appropriate source event fires; the trigger is still declared via Azure. |
| `Function<T,R>` | Transforms `T` into `R`. | Suitable for HTTP request/reply, or processing a Queue/Event Hub message and returning a result to a binding. |
| `Consumer<T>` | Consumes `T`, typically with side effects. | Suitable for event/queue processing without a return value, but requires handling errors, ack, and idempotency. |

**Do not assume automatically:** simply declaring `@Bean Supplier<T>` will not make Azure create a Timer Trigger; nor will having `@Bean Consumer<T>` make Azure listen to a Storage Queue automatically. **Triggers and bindings must still be declared** using Azure Functions annotations/configuration or an adapter that provides the corresponding capability.

## 3. Dependency Matrix and When Each Component Is Needed

### 3.1. Core Dependencies

| Artifact / plugin | Role | When Required? |
| --- | --- | --- |
| `org.springframework.cloud:spring-cloud-function-adapter-azure` | Integrates the Azure Java Worker with Spring dependency injection and SCF. | **Yes** when implementing Azure handlers using the `@Component`/`@FunctionName` model with Spring beans. |
| `org.springframework.cloud:spring-cloud-function-adapter-azure-web` | Specialized adapter for running a Spring Web application via an Azure HTTP Trigger, hiding annotation details at the web application layer. | **Replaces** the generic adapter when the use case is primarily a Spring MVC/Web application. |
| `org.springframework.cloud:spring-cloud-function-context` | Provides `FunctionCatalog`, bean registration, and composition for `Function` beans. | Functionally required; typically pulled in transitively by the corresponding SCF adapter. |
| `org.springframework.boot:spring-boot-starter` | Spring Boot configuration, application context, and foundational components. | Suitable for structuring the Spring Boot application that serves as configuration for the adapter. |
| `com.microsoft.azure.functions:azure-functions-java-library` | `@FunctionName`, `@HttpTrigger`, `HttpRequestMessage`, `ExecutionContext`, and Java binding APIs. | Needed on the compile classpath for handlers using Azure annotations/APIs; may be transitive, but should be declared explicitly if used directly in code. |
| **`com.microsoft.azure:azure-functions-maven-plugin`** | Reads annotations, generates `function.json`, sets up the staging/package layout, and supports run/deploy. | Required for the Maven build/deploy workflow. |
| **`com.microsoft.azure.azurefunctions`** (Gradle plugin) | Tasks for building/packaging/running/deploying Azure Functions in Gradle. | Correspondingly required when the project uses Gradle. |
| `org.springframework.boot:spring-boot-starter-test` | Unit/integration tests on the Spring context. | Test scope. |
| Azure extensions / SDKs for specific triggers | Queue/Blob/Event Hubs, output bindings, or client APIs. | Only add when using the corresponding trigger/binding or Azure operations. |

**Distinguish dependency from plugin:** `spring-cloud-function-adapter-azure` is a **runtime library**. `azure-functions-maven-plugin` is a **build/package/deploy tool**, not a business library to inject. Having only the adapter on the classpath is not enough to generate the proper function app structure for the Azure Host to discover functions.

### 3.2. Choosing the Generic Adapter vs. Azure Web Adapter

| Question | Generic Adapter | Azure Web Adapter |
| --- | --- | --- |
| Do you want to write `@FunctionName` handlers with `@HttpTrigger`/`@TimerTrigger`/`@QueueTrigger`? | Suitable. | Not the primary use case. |
| Do you want to use `HttpRequestMessage`, `ExecutionContext`, and output bindings directly? | Suitable. | Hidden behind the Spring Web layer by the adapter. |
| Does the application already have Spring Web controllers/routers? | You can write a handler to forward requests, but it adds boilerplate. | Better suited for pure web applications. |
| Does it turn every Spring `@Bean Function` into an Azure trigger automatically? | **No**; a handler/binding is still required. | **Does not** auto-generate every trigger type. |
| Do you need to handle non-HTTP events as well? | Choose the generic adapter with appropriate annotations/bindings. | Do not use Web Adapter as a general solution for all triggers. |

Normally, **choose one strategy as the primary entry point** rather than adding both adapters to the project just because their names look similar. If the app only needs an SCF `Function<String,String>` over HTTP, a thin Azure handler with the generic adapter is sufficient; if the app needs Spring MVC routes/filters/controllers, consider the Web Adapter.

## 4. Versions and Compatibility: Avoid Conflating Four Layers

Current Spring Cloud Function documentation explicitly states that the DI-based Azure adapter requires **SCF 4.0.0+**. **`FunctionInvoker`** is the legacy model and has been marked **deprecated** by Spring. Writing handlers with `@Component`/`@FunctionName` is the recommended approach for new projects.

Four version layers must be evaluated independently:

| Layer | Example | What Must Match |
| --- | --- | --- |
| Spring Boot / Spring Cloud release train | Boot 3.x or 4.x and the corresponding Cloud BOM | Must choose a compatible release train; it manages the SCF version. |
| Spring Cloud Function Azure Adapter | SCF 4.x or 5.x compatible with the BOM | The adapter must be on the same release line as `spring-cloud-function-context`. |
| Azure Functions Host runtime | `FUNCTIONS_EXTENSION_VERSION=~4` | Choose a Host version that supports your Java runtime and trigger extensions. |
| Java runtime / build JDK | Java 17 or 21 for Functions v4 | Java compile target, worker runtime, and hosting OS/plan must be compatible. |
| Azure Maven/Gradle plugin | Plugin published by Microsoft | Generates metadata/packages matching the selected host and Java runtime. |

For example, **Azure Functions runtime 4.x** supports Java 17 and 21 per Microsoft documentation, but you must verify the combination of **OS, hosting plan, and support lifecycle** before selecting a deployment version. Do not assume Azure Functions runtime `4.x` means Spring Cloud Function `4.x`; they are two separate pieces of software.

### 4.1. Why Not Hard-Code "latest" for Everything?

A new `pom.xml` using Spring Boot 4.x mixed with `spring-cloud-function-adapter-azure` 4.x or an older Spring Cloud BOM can cause classpath/Jackson/auto-configuration errors. Conversely, an older Azure build plugin might not recognize newer runtime/Java targets. The safe approach is:

1. Choose a JDK and Azure Functions Host supported by Microsoft.
2. Choose a Spring Boot and Spring Cloud BOM **published as compatible**.
3. Use the Azure adapter from the same SCF line managed by the BOM.
4. Use an Azure Maven/Gradle plugin that supports your Java version, OS, and plan.
5. Inspect the dependency tree and test with Azure Functions Core Tools.

This lesson uses **Java 17** in its examples because it is supported by Azure Functions runtime 4.x and works well with modern Spring Boot releases. Do not assume every account/plan runs the exact same runtime patch.

## 5. Maven: Declaring Libraries and Plugins

### 5.1. Dependencies to Add

For a project that already has a **Spring Boot parent**, **Spring Cloud BOM**, and appropriate dependency management, the `dependencies` section can start like this:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-azure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.microsoft.azure.functions</groupId>
        <artifactId>azure-functions-java-library</artifactId>
        <version>1.3.1</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`1.3.1` for the Azure Java library here is an **example baseline mentioned in Microsoft API documentation**, not a claim that it is the latest version. Check the Azure Java library and Azure Maven plugin used in current templates before locking dependencies. Some adapters already pull in the Azure Java library transitively; if you add it directly, ensure there are no version conflicts.

`spring-cloud-function-adapter-azure` already integrates with SCF context, so you do not necessarily need to add `spring-cloud-function-context` separately if the transitive dependency is already aligned. You can verify with:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud,com.microsoft.azure.functions
~~~

If the project does not yet manage the adapter version via a BOM, **do not let Maven guess**. Add dependency management matching the Spring Cloud release train before running.

### 5.2. Azure Functions Maven Plugin

The following snippet illustrates the `build/plugins` section; you will need to choose the app name, resource group, region, and plan for your prepared Azure environment:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <skip>true</skip>
            </configuration>
        </plugin>

        <plugin>
            <groupId>com.microsoft.azure</groupId>
            <artifactId>azure-functions-maven-plugin</artifactId>
            <version>1.22.0</version>
            <configuration>
                <appName>demo-orders-functions-unique</appName>
                <resourceGroup>demo-functions-rg</resourceGroup>
                <region>eastasia</region>
                <hostJson>src/main/resources/host.json</hostJson>
                <runtime>
                    <os>linux</os>
                    <javaVersion>17</javaVersion>
                </runtime>
                <appSettings>
                    <property>
                        <name>FUNCTIONS_EXTENSION_VERSION</name>
                        <value>~4</value>
                    </property>
                </appSettings>
            </configuration>
            <executions>
                <execution>
                    <id>package-functions</id>
                    <goals>
                        <goal>package</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

**This is an illustrative configuration to merge into a complete project**, not a full `pom.xml`. Values like `appName`/`resourceGroup`/`region` are examples and must be changed when deploying. Maven plugin version `1.22.0` is the baseline mentioned in Spring Cloud Function documentation; verify the current plugin version approved by your team that supports your hosting plan.

The Spring Boot Maven plugin is configured with `skip=true` because **Azure Functions packaging is incompatible with the default Spring Boot repackaged executable JAR**. Older projects may use an appropriate thin layout configuration, but with the new DI handler model, a standard JAR alongside dependencies inside the Azure package layout is usually easier to manage. The Azure Maven plugin is responsible for building the staging layout.

### 5.3. Specifying the Spring Application Main Class

The adapter needs to identify the Spring Boot application to initialize the context. In `pom.xml`, you can declare:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

Depending on the build tool, you can also use `Main-Class` in the manifest or the `MAIN_CLASS` environment variable. If multiple JARs contain Spring configurations, explicitly specifying the main class prevents the adapter from picking the wrong Spring Boot application.

Do not confuse `main()` with the Azure entrypoint:

- `AzureOrderApplication.main(...)` is used by Spring Boot and identifies the application configuration class.
- `@FunctionName("normalizeOrderCode")` is the **Azure Function entrypoint**, invoked by the Azure Java Worker upon a trigger.
- Azure Functions does not require running a Spring Boot embedded HTTP server to execute Azure handlers.

## 6. Java Example: Reusing a Business Function via an Azure HTTP Trigger

### 6.1. Business Rule

The application receives an order code as text:

~~~text
Request body: " dh-102 "
Result:       "DH-102"
~~~

There are two independent processing steps:

- `trimCode: Function<String,String>` removes leading/trailing whitespace.
- `upperCode: Function<String,String>` converts to uppercase using `Locale.ROOT`.

In `FunctionCatalog`, the composed definition is **`trimCode|upperCode`**. If we later deploy through a different HTTP adapter, a Queue event, or another serverless platform, we reuse these exact same functions.

~~~mermaid
sequenceDiagram
    participant Client
    participant Host as Azure Functions Host
    participant Worker as Azure Java Worker
    participant Handler as @Component @FunctionName
    participant Catalog as FunctionCatalog
    Client->>Host: POST /api/orders/normalize
    Host->>Worker: HTTP trigger invocation
    Worker->>Handler: HttpRequestMessage + ExecutionContext
    Handler->>Catalog: lookup("trimCode|upperCode")
    Catalog-->>Handler: Function<String,String>
    Handler->>Catalog: apply(" dh-102 ")
    Catalog-->>Handler: "DH-102"
    Handler-->>Worker: HttpResponseMessage(200)
    Worker-->>Client: HTTP response
~~~

### 6.2. Spring Boot Application and Function Beans

Create `src/main/java/example/azure/AzureOrderApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AzureOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AzureOrderApplication.class, args);
    }

    @Bean
    Function<String, String> trimCode() {
        return value -> value.strip();
    }

    @Bean
    Function<String, String> upperCode() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

This is pure **Spring Cloud Function** logic, with no `com.microsoft.azure.functions.*` imports. Both functions can be tested in plain Java. They are also discovered and registered by Spring so the catalog can look them up by name.

### 6.3. Azure Handler as a Spring Component

Create `src/main/java/example/azure/OrderAzureHandler.java`:

~~~java
package example.azure;

import java.util.Optional;
import java.util.function.Function;

import com.microsoft.azure.functions.AuthorizationLevel;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final FunctionCatalog catalog;

    public OrderAzureHandler(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @FunctionName("normalizeOrderCode")
    public HttpResponseMessage normalize(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/normalize")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");
        if (input.isBlank()) {
            return request.createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Order code must not be blank")
                    .build();
        }

        Function<String, String> normalize =
                this.catalog.lookup("trimCode|upperCode");

        if (normalize == null) {
            context.getLogger().severe(
                    "Composition trimCode|upperCode not found");
            return request.createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Function is not configured")
                    .build();
        }

        try {
            String result = normalize.apply(input);
            return request.createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .body(result)
                    .build();
        }
        catch (RuntimeException ex) {
            context.getLogger().severe(
                    "Order processing error: " + ex.getClass().getSimpleName());
            return request.createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Processing failed")
                    .build();
        }
    }
}
~~~

**Key technical points:**

1. `@Component` lets Spring manage the handler class. The Azure adapter connects the Azure Java Worker model with Spring dependency injection.
2. `@FunctionName` declares the **Azure Function name**. It does not need to match the bean names `trimCode` or `upperCode`.
3. `@HttpTrigger` defines the HTTP method, route, authorization level, and input binding.
4. `FunctionCatalog.lookup("trimCode|upperCode")` looks up the SCF composition. Injecting a `Function` bean directly with `@Autowired` also works, but does not leverage catalog/composition and wrappers.
5. `HttpRequestMessage<Optional<String>>` represents an HTTP string body that may be absent. Using `Optional` avoids assuming every request has a body.
6. `ExecutionContext` is the Azure context per invocation. In the example it is only used for logging; do not store this object in a long-lived singleton.
7. The handler maps invalid input to HTTP 400 and unexpected errors to HTTP 500; production applications should use a consistent error schema and avoid returning stack traces to callers.

`AuthorizationLevel.FUNCTION` requires an appropriate function key policy on Azure. In the example, **ANONYMOUS is not used** so the endpoint is not accidentally exposed publicly; proper authentication/authorization for your environment is still required, and function keys should not be treated as a complete replacement for IAM/API gateways.

### 6.4. Why Should the Business Function Not Know About HttpRequestMessage?

If you write:

~~~java
Function<HttpRequestMessage<String>, HttpResponseMessage> process() {
    // Logic directly depends on Azure Java SDK.
}
~~~

the function becomes hard to reuse when invoked from a Kafka event, another HTTP adapter, or a different serverless environment. Keep `Function<String,String>` or `Function<OrderRequest,OrderDecision>`, and let the Azure handler deal with protocol translation.

**Not every handler has to use String.** For JSON bodies, you can use Azure POJO binding or deserialize/validate at the boundary to invoke `Function<OrderRequest,OrderDecision>`. Verify the JSON contract, content type, nullability, serializer, and converters rather than casting arbitrarily.

## 7. Azure Functions Packaging Differs from a Spring Boot JAR

A common cause of deployment failure is running `spring-boot:repackage` and handing the **executable fat JAR** directly to the Azure Java Worker. According to SCF Azure documentation, Azure Functions requires the structure generated by the **Azure Maven/Gradle plugin**: classes/handlers must be discoverable by the worker, dependencies placed in the right location, and `function.json` and `host.json` files present.

### 7.1. Typical Structure After Packaging

~~~text
target/
  azure-functions/
    demo-orders-functions-unique/
      host.json
      demo-orders-functions-unique.jar
      normalizeOrderCode/
        function.json
      lib/
        [dependency JARs packaged by the plugin]
~~~

Exact JAR names, directories, and layout may vary by plugin, but **what must be verified** is that the Azure Java Worker can locate the method `example.azure.OrderAzureHandler.normalize` and the Spring/SCF libraries when the function executes.

`function.json` is binding metadata **generated by the Azure plugin from annotations**; do not use annotations and then manually edit that metadata in the staging output to "patch" bugs. Fix the annotations or build configuration and re-package.

### 7.2. What Is host.json Used For?

Minimal `src/main/resources/host.json` example:

~~~json
{
  "version": "2.0"
}
~~~

`host.json` controls configuration for the **entire function app**, not Spring business functions. Specific extensions/bindings may require an appropriate extension bundle or extra settings per Azure documentation. Do not copy a full set of extension configurations if you are not using the corresponding triggers.

### 7.3. MAIN_CLASS and Package Scanning

If the adapter cannot find the Spring Boot main configuration:

- Check `<start-class>` or the `Main-Class` manifest entry.
- Or set `MAIN_CLASS=example.azure.AzureOrderApplication` in local settings or Azure Function App settings.
- Place `OrderAzureHandler` in the same package or a subpackage so `@SpringBootApplication` scans the `@Component`.
- Do not include multiple main classes without explicitly specifying which class the adapter should use.

**The Spring context must be created in alignment with the Azure Worker lifecycle.** Do not call `SpringApplication.run(...)` on every HTTP request inside the handler: doing so wastes time and resources and can create unnecessary contexts.

## 8. Running Locally with Azure Functions Core Tools

Prerequisites:

- A JDK matching the compile target, e.g., 17.
- Maven or Gradle depending on the project.
- **Azure Functions Core Tools v4**.
- **Azure CLI** if deploying/managing Azure resources.
- **Azurite** or a storage account if triggers/bindings require Azure Storage (Queue, Blob, Table, and certain host scenarios).

### 8.1. local.settings.json

Example for local development:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "MAIN_CLASS": "example.azure.AzureOrderApplication"
  }
}
~~~

This is **local configuration**, not production configuration. `UseDevelopmentStorage=true` requires Azurite or a compatible storage emulator if the host/triggers use storage. Never commit `local.settings.json` containing real connection strings, tokens, or keys to the repository. When deploying, use Azure Function App settings/Key Vault or an appropriate secrets management mechanism.

### 8.2. Building and Running with Maven

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

The Azure Maven plugin creates the package and binding metadata from annotations. After the host starts, check the logs to confirm that the `normalizeOrderCode` function is discovered and the `orders/normalize` route is displayed.

With the default Functions Host route, the local endpoint typically looks like:

~~~text
POST http://localhost:7071/api/orders/normalize
Body:  dh-102
Expected 200: DH-102
~~~

The host, port, and URL prefix can change depending on `host.json` and plugin configuration. Local auth behavior may differ from production, so test authorization separately when deployed.

Example request using curl (assuming the local endpoint uses the `/api` prefix):

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/normalize" \
  -H "Content-Type: text/plain" \
  --data " dh-102 "
~~~

Expect HTTP 200 with body `DH-102`. Try a whitespace-only body to confirm HTTP 400.

### 8.3. With Gradle

Corresponding runtime dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The Gradle plugin provided by Microsoft has the ID `com.microsoft.azure.azurefunctions`. Once the plugin and `azurefunctions { ... }` are configured properly for the project:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

Do not run both Maven and Gradle plugin toolchains in the same build if the project uses only one build tool. In Gradle, ensure the JAR task includes a `Main-Class` manifest entry, uses a compatible Java runtime, lets the Azure plugin package dependencies, and that Spring Boot's executable `bootJar` does not accidentally replace the artifact Azure expects.

## 9. Deploying to Azure

Once Azure resources (subscription, resource group, Function App, hosting plan, storage) are provisioned and the build plugin is configured properly:

~~~bash
az login
./mvnw azure-functions:deploy
~~~

Or with Gradle:

~~~bash
./gradlew azureFunctionsDeploy
~~~

**These are instructional commands, not commands to run in this exercise.** Deploying can modify cloud resources, configurations, costs, and access permissions; use an approved subscription/resource group and verify the plan, region, and runtime before executing.

Post-deployment verification steps:

1. The Function App runs the expected **Java version** and `FUNCTIONS_EXTENSION_VERSION`.
2. Azure Portal/CLI discovers `normalizeOrderCode` with the HTTP trigger on the expected route/method.
3. The Spring context initializes successfully inside the Azure Worker; logs show no `NoSuchBeanDefinitionException`.
4. `FunctionCatalog` resolves `trimCode|upperCode`.
5. App settings contain the required configuration, with no hard-coded secrets in code or the JAR.
6. Function keys/identity/network access match security requirements.
7. Input errors map properly to 4xx; unexpected errors produce safe responses and necessary telemetry.

## 10. Comparing the Azure Adapter with the Azure Web Adapter

### 10.1. Generic Adapter

When using `spring-cloud-function-adapter-azure`:

~~~text
@FunctionName + @HttpTrigger/@TimerTrigger/@QueueTrigger...
               ↓
Azure Java Worker + Spring DI
               ↓
@Component handler
               ↓
FunctionCatalog.lookup("name|composition")
               ↓
Business Function
~~~

You choose the Azure triggers yourself, access `ExecutionContext`, use SDK-specific binding annotations, and control the response with `HttpResponseMessage`. This model fits this lesson well because it clearly separates the Azure platform from business logic.

### 10.2. Azure Web Adapter

When the application genuinely uses Spring Web with controllers:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-azure-web</artifactId>
</dependency>
~~~

Along with the Spring Web dependency matching your Boot version and Azure packaging plugins. The Web Adapter lets you use the Spring Web model, hiding most Azure HTTP annotation details and hosting the web application on an HTTP Trigger.

**Do not mistake this for a "library for calling Azure REST APIs."** It is an adapter for **hosting a Spring Web application on Azure Functions**. Nor does it turn Queue/Timer/Blob triggers into Spring MVC requests. For simple `Function<T,R>` logic or non-HTTP events, the generic adapter is usually clearer.

### 10.3. When Is the Spring Cloud Function Web Adapter Used?

`spring-cloud-function-web` is an SCF adapter that can expose HTTP invocation for functions in supported Spring Web setups, but it is **not an Azure runtime adapter**. To deploy to Azure Functions, you still must choose a mechanism that integrates with the Azure Host and corresponding packaging. Adding multiple overlapping HTTP adapters can cause route ambiguity or false expectations about behavior.

## 11. Passing ExecutionContext and Metadata

Azure provides an `ExecutionContext` per invocation, containing a logger and contextual information such as the invocation ID. Inside a handler, you can use it directly:

~~~java
context.getLogger().info(
        "Processing Azure invocation " + context.getInvocationId());
~~~

It is not mandatory to pass `ExecutionContext` into the domain function. Keeping it in the adapter/handler keeps business logic decoupled from Azure.

When a function **genuinely needs** contextual data from Azure, SCF provides the utility `AzureFunctionUtil.enhanceInputIfNecessary(...)` to attach the execution context under the `AzureFunctionUtil.EXECUTION_CONTEXT` header. However, using `Message<T>` instead of a plain payload should be explicitly designed and tested for type/header propagation; do not let domain functions accidentally depend on the runtime.

### 11.1. Metadata at Trigger Boundaries

| Source | Available Metadata | What to Do |
| --- | --- | --- |
| HTTP Trigger | Method, headers, route/query, authentication context. | Validate input, filter sensitive headers, map 4xx/5xx appropriately. |
| Queue Trigger | Message ID, dequeue count, correlation data. | Define retry/poison queue/idempotency behavior per extension and host. |
| Blob Trigger | Blob path/name, properties, metadata. | Account for size, streaming, and storage permissions. |
| Timer Trigger | Scheduled/past-due timestamp. | Do not treat a Timer Trigger as generating business input or guaranteeing strict exactly-once execution. |
| Event Hub/Kafka | Partition, offset, event key. | Manage ordering, checkpointing, and redelivery according to the adapter. |

A common mistake is passing **all** Azure metadata into domain objects or storing `ExecutionContext` in a singleton for subsequent invocations. Extract only the fields that truly belong to the application contract; handle tracing/correlation with a dedicated strategy.

## 12. Lifecycle, Concurrency, and Resources

### 12.1. The Spring Context Is Not Request-Scoped by Default

The adapter can retain and reuse the Spring application context across the lifetime of a Java Worker/process. Therefore, Spring singleton beans and function objects can be reused by multiple concurrent invocations. Write **stateless** functions or protect shared state for concurrency safety.

Example to avoid:

~~~java
@Bean
Function<String, String> unsafe() {
    StringBuilder shared = new StringBuilder();

    return value -> {
        shared.setLength(0);
        shared.append(value);
        return shared.toString();
    };
}
~~~

`StringBuilder shared` holds mutable state shared across invocations. Replace it with:

~~~java
@Bean
Function<String, String> safe() {
    return value -> new StringBuilder(value)
            .reverse()
            .toString();
}
~~~

### 12.2. Cold Start

Initializing the Spring context can increase **cold start latency**, especially when there are many dependencies, complex eager bean initialization, or the function runs on a plan that scales to zero. To reduce overhead:

- Only include the starters/auto-configurations you actually need on the classpath.
- Avoid loading the entire web stack if you are only handling an HTTP Trigger via Azure annotations.
- Never initialize the Spring context per invocation.
- Measure actual startup time, memory, CPU, and scaling behavior.
- Choose an appropriate hosting plan/always-ready setting or equivalent options when first-request latency matters.

### 12.3. Do Not Collapse Every Error into HTTP 500

For an HTTP Trigger, you can map validation errors to 400, auth errors per security policy, transient failures to responses matching the retry contract, and unexpected failures to 500. For Queue/Event Hub triggers, there is no HTTP response; retries, poison messages, retry intervals, and checkpointing depend on the host/extension. A `Function.apply(...)` throwing an exception is only the starting point for the adapter's error policy.

## 13. FunctionCatalog, Composition, and Data Conversion

### 13.1. Direct Bean Injection vs. Catalog Lookup

Both approaches work inside a Spring handler:

~~~java
@Autowired
private Function<String, String> upperCode;
~~~

and:

~~~java
@Autowired
private FunctionCatalog catalog;

// In handler:
Function<String, String> pipeline =
        catalog.lookup("trimCode|upperCode");
~~~

**Direct bean injection** works well when you only need a single plain Spring `Function`. **Use `FunctionCatalog`** when you need definition names, composition, wrappers/type conversion, or want the invocation pattern to remain compatible with other SCF adapters.

### 13.2. Do Not Confuse the Azure Function Name with the Catalog Definition

`@FunctionName("normalizeOrderCode")` is the **Azure handler** name. `trimCode|upperCode` is the definition in the **SCF catalog**. The property `spring.cloud.function.definition` (when read by an adapter) also selects a function, but it does not automatically create an Azure `@FunctionName` or binding.

Never accept a query parameter directly like `?functionName=...` and pass it to `catalog.lookup(input)` without an allowlist. Doing so can let clients invoke sensitive functions or trigger unwanted load. In the example, the definition is fixed in code.

### 13.3. JSON, POJOs, and Message<T>

This lesson uses `String` to avoid serialization details. For a real request:

~~~json
{
  "orderId": "dh-102",
  "totalVnd": 1500000
}
~~~

you can use Java records:

~~~java
record OrderRequest(String orderId, long totalVnd) {}
record OrderDecision(String orderId, String lane) {}
~~~

and a function:

~~~java
@Bean
Function<OrderRequest, OrderDecision> classifyOrder() {
    return request -> new OrderDecision(
            request.orderId().strip().toUpperCase(),
            request.totalVnd() >= 1_000_000 ? "PRIORITY" : "STANDARD");
}
~~~

However, **the adapter must be able to construct `OrderRequest`** before calling the function, and the response must be serialized in a consistent format. SCF has converters/wrappers, and Azure Functions Java Worker also has POJO binding, and they do not necessarily share the exact same serialization contract in every case. Test the actual boundary.

If headers like `traceId` or the Azure execution context are needed, you can use `Function<Message<T>,Message<R>>`, but you must understand how the adapter maps headers; do not assume a Spring `Message<T>` survives intact across every transport.

## 14. Layered Testing

### 14.1. Unit Testing Business Logic Without Azure

~~~java
AzureOrderApplication config = new AzureOrderApplication();

String normalized = config.upperCode()
        .apply(config.trimCode().apply(" dh-102 "));

assertEquals("DH-102", normalized);
~~~

Plain Java tests verify business rules. You can use JUnit 5; the example uses `assertEquals` from `org.junit.jupiter.api.Assertions`. Neither Core Tools nor an Azure subscription is required.

### 14.2. Spring Context + FunctionCatalog Test

~~~java
@SpringBootTest(classes = AzureOrderApplication.class)
class CatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void compositionNormalizesOrderCode() {
        Function<String, String> pipeline =
                catalog.lookup("trimCode|upperCode");

        assertNotNull(pipeline);
        assertEquals("DH-102", pipeline.apply(" dh-102 "));
    }
}
~~~

Imports include Spring Boot Test, `@Autowired`, `FunctionCatalog`, `Function`, and JUnit `@Test` along with `assertNotNull`/`assertEquals`. This test catches bean scanning issues, definition naming errors, or composition issues before running the Azure Host.

### 14.3. Testing the HTTP Trigger in the Local Azure Functions Runtime

Once `azure-functions:run` is running:

| Case | Request | Expected |
| --- | --- | --- |
| Valid | `POST /api/orders/normalize` with body `" dh-102 "` | HTTP 200, body `"DH-102"`. |
| Blank | Body `"   "` | HTTP 400, validation message. |
| Missing body | No body | HTTP 400, does not throw `NoSuchElementException`. |
| Wrong method | GET when only POST is declared | Not processed as a valid POST; check host response. |
| Authentication | Missing/wrong function key on Azure | Rejected according to the configured authLevel/host policy. |
| Startup | Wrong Spring application main class | Host logs startup failure and does not handle invocations. |

Local Core Tools may handle function keys differently from the cloud; therefore, security requirements must be verified **after deploying to an environment with the target policies**.

### 14.4. Deployment Integration Tests

Beyond the response body, verify:

- The Azure plugin generates `function.json` with the right route/entrypoint.
- The Java runtime is compatible with the target bytecode.
- `FunctionCatalog` is injected into the handler.
- Spring/SCF dependencies are not missing from the package.
- Logs contain invocation ID/correlation ID and do not log secrets.
- Cold start, concurrency, and memory under load.
- For non-HTTP triggers: retry, poison queue, checkpointing, and idempotency.

## 15. Common Errors and Diagnostics

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `NoClassDefFoundError` for Azure SDK annotations | Missing `azure-functions-java-library` on compile/runtime classpath or version conflict. | Dependency tree and package layout. |
| `FunctionCatalog` fails to inject | Missing SCF/context adapter or broken Spring configuration. | Adapter version, BOM, main class, auto-configuration. |
| `OrderAzureHandler` is not managed by Spring | Forgot `@Component` or class is outside package scan. | Annotations, Spring component scan, main class. |
| Azure Host does not list `normalizeOrderCode` | `function.json` not generated/invalid, plugin missed annotations, or packaging failed. | Azure staging directory, `function.json`, and plugin logs. |
| Cannot find Spring main class | `start-class`/`Main-Class`/`MAIN_CLASS` missing or incorrect. | Manifest, environment variables, `@SpringBootApplication` class. |
| Boot fat JAR exists but host fails to run handler | Spring Boot repackage breaks the package layout Azure expects. | Disable `spring-boot:repackage` and use the Azure plugin package goal. |
| `catalog.lookup("trimCode|upperCode")` returns null | Wrong bean name, missing component scan, or incompatible definitions. | Catalog unit test, bean list, and generic types. |
| HTTP 500 with `ClassCastException` | Request body/POJO/converter generic mismatch. | Test serialization, content type, and Azure/SCF adapter. |
| Works locally but deployment fails with Java class version error | Build JDK is newer than the Function App Java runtime. | Compiler target, runtime OS/Java, Azure settings. |
| Local run fails due to missing Azure Storage | Storage-backed trigger lacks `AzureWebJobsStorage`/Azurite or valid credentials. | Local settings, Azurite, permissions. |
| `FunctionInvoker` errors or outdated sample no longer applies | Following legacy/older adapter guides. | Migrate to `@Component` + Azure annotations with SCF 4.0+. |
| Handler with side effects runs duplicate processing | Client retry, trigger redelivery, or concurrent invocation. | Idempotency by business key; retry/ack per trigger. |
| Slow function cold start | Context too large, excessive auto-configs/dependencies. | Profile startup, memory, hosting plan, and context initialization. |

### 15.1. Pre-Deployment Checklist

- [ ] Chosen **one** appropriate adapter: generic Azure or Azure Web.
- [ ] Azure handler has `@FunctionName` and required trigger/binding annotations.
- [ ] Handler is a Spring `@Component` within the package scan path.
- [ ] Spring main class is declared/resolved accurately.
- [ ] `FunctionCatalog` looks up the exact bean/composition name.
- [ ] JDK, Azure Functions runtime, and Spring Boot/SCF/BOM are compatible.
- [ ] Azure Maven/Gradle plugin generates `function.json` and the standard package.
- [ ] Spring Boot executable JAR repackaging does not break the layout Azure requires.
- [ ] App settings/secrets/identities are configured securely with no committed credentials.
- [ ] Business function, Spring catalog, and local Azure runtime tests have passed.
- [ ] Retry, idempotency, logging, and security are verified for the trigger type.

## 16. Further Exercises

1. Add `Function<String,Integer> lengthCode` and invoke `catalog.lookup("trimCode|upperCode|lengthCode")` from another Azure handler. Verify input/output composition.
2. Replace `String` with `OrderRequest`/`OrderDecision`, and test JSON bodies, null fields, validation, and HTTP responses.
3. Try a `@TimerTrigger` invoking a `Supplier<String>`, compare Azure's schedule with calling `Supplier.get()`, and explain why a `Supplier` is not automatically a timer.
4. Create a Queue Trigger calling `Consumer<OrderEvent>`; describe retries, poison messages, and idempotency by event ID when the handler throws an error.
5. Compare injecting a `Function` bean directly versus injecting `FunctionCatalog` for composition: abstraction benefits and risks of misconfigured names.
6. Try packaging with the Azure Maven plugin after disabling Boot repackage; inspect `function.json` and the staging directory structure to distinguish an Azure Function App from an executable Boot JAR.

## 17. Official References

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): generic adapter, Web Adapter, `@Component` handlers, `FunctionCatalog`, Azure packaging, local run/deploy, and `FunctionInvoker` deprecation notice.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`/`Function`/`Consumer`, composition, `FunctionCatalog`, and type conversion.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, triggers/bindings, packaging, Java versions, metadata, and execution context.
- [Microsoft Learn — Spring Cloud Function in Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/getting-started-with-spring-cloud-function-in-azure): workflow for creating, running, debugging, and deploying Spring Cloud Function to Azure.
- [Azure Functions Maven Plugin](https://github.com/microsoft/azure-maven-plugins/tree/develop/azure-functions-maven-plugin): plugin for packaging, running, deploying, and configuring a Function App.
- [Spring Cloud Function — Azure samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): handler examples for HTTP, Blob, Timer, Kafka, and Web Adapter.
- [Microsoft Learn — Java functions reference / supported Java versions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java#java-versions): mapping Azure Functions Host to Java runtimes.

**Conclusion:** To use Spring Cloud Function on Azure, keep business logic in `Supplier`/`Function`/`Consumer` and `FunctionCatalog`, use **`spring-cloud-function-adapter-azure`** to integrate Spring dependency injection into Azure `@FunctionName` handlers, and use the **Azure Maven/Gradle plugin** to build a compliant Azure Functions package. If the application is primarily Spring Web, consider **`spring-cloud-function-adapter-azure-web`** instead. Do not use the legacy `FunctionInvoker` as your default approach; verify the release train, main class, Java runtime, triggers/bindings, security, and error lifecycle so the same business function can be reused across HTTP, events, or other serverless environments.
