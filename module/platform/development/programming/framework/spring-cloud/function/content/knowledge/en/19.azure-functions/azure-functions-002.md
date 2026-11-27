# Registering a Handler Class with @Component and @FunctionName Methods

## 1. Context and Objectives

**Spring Cloud Function (SCF)** encapsulates business logic using `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`; beans are looked up through `FunctionCatalog` and can be composed (*composition*) for reuse across HTTP, event streams, or serverless environments. Business logic does not need to know directly which protocol is invoking it.

In **Azure Functions**, the Java entrypoint is a **public method** annotated with `@FunctionName`, alongside an annotation specifying the trigger/binding such as `@HttpTrigger`, `@QueueTrigger`, or `@TimerTrigger`. The Azure Java Worker invokes that method whenever the corresponding source fires.

The **`spring-cloud-function-adapter-azure`** module bridges the two models: the handler class annotated with **`@Component`** is managed by Spring and receives injected beans and `FunctionCatalog`, while methods annotated with **`@FunctionName`** are discovered and invoked by Azure Functions on triggers. This model was introduced in Spring Cloud Function documentation starting in **4.0.0+** and is the modern approach replacing the deprecated `FunctionInvoker`.

This lesson belongs to the **Azure Functions** chapter of the **SPRING_CLOUD_FUNCTION** module and focuses on registering and operating the **handler class** rather than merely writing a single standalone Azure HTTP Function.

### After This Lesson, You Will Be Able To

1. Distinguish the roles of `@Component`, `@FunctionName`, and trigger/binding annotations.
2. Write a Spring handler class with **two Azure Functions methods** sharing common business beans.
3. Inject `Function<T,R>` with `@Qualifier` and use `FunctionCatalog.lookup("f1|f2")`.
4. Understand that the Azure plugin generates `function.json`, whereas Spring component scan creates runtime beans.
5. Run locally with Azure Functions Core Tools and inspect function names, routes, Spring DI, and composition errors.
6. Design stateless handlers, keep `ExecutionContext` scoped per invocation, and protect HTTP endpoints.

## 2. Two Separate Registration Systems

~~~mermaid
flowchart LR
    T["HTTP / Queue / Timer / Event"] --> H["Azure Functions Host"]
    H --> W["Azure Java Worker"]
    W --> F["Method @FunctionName"]
    P["Azure Maven / Gradle plugin"] -. "Scans annotations, generates metadata" .-> F
    S["Spring ApplicationContext"] -. "@Component, inject" .-> C["Handler bean"]
    C --> F
    S --> K["FunctionCatalog"]
    B["Bean Supplier / Function / Consumer"] --> K
    F -->|"lookup(name|composition)"| K
    K --> R["Business logic"]
    R --> F
    F --> O["Response / output binding"]
~~~

There are **two mechanisms** that do not replace one another:

- **Azure discovery at build/deploy time:** The Azure Maven/Gradle plugin inspects `@FunctionName` and binding annotations, generating metadata like `function.json` and packaging the app so the Azure Java Worker can locate the right handler.
- **Spring bean registration at runtime:** `@SpringBootApplication` scans classes with `@Component`/`@Service`, creates instances, and injects Spring-owned beans. The Azure adapter connects the worker to the Spring-managed instance.

| Annotation | Where Placed? | System Using It | Meaning |
| --- | --- | --- | --- |
| `@SpringBootApplication` | Main application class | Spring Boot | Initializes configuration, component scanning, and auto-configuration. |
| `@Bean` | Method in Spring configuration | Spring | Registers a service/function object. |
| **`@Component`** | **Azure handler class** | **Spring** | Spring instantiates and injects the handler bean. |
| **`@FunctionName("name")`** | **Public method** | **Azure** | Defines the Azure Function name invoked by the host. |
| `@HttpTrigger` | Method parameter | Azure | Defines HTTP trigger, route, method, and auth level. |
| `@QueueTrigger` | Method parameter | Azure | Defines an Azure Storage Queue trigger. |
| `@BindingName` | Method parameter | Azure | Extracts route/trigger metadata values. |
| `@Qualifier` | Constructor/field/parameter | Spring | Disambiguates a bean when multiple candidates share the same type. |

**Three names that are not synonymous:** `@FunctionName("normalizeByCatalog")` is the Azure Function name; `@Bean upperCode()` registers a bean named `upperCode`; `"trimCode|upperCode"` is a function composition resolved by `FunctionCatalog`.

### 2.1. What Happens with Only @Component?

A `@Component` class can be instantiated as a Spring bean and injected normally. However, without a `@FunctionName` method and an appropriate trigger/binding, the Azure Host **will not automatically publish an HTTP/Queue/Timer Function** for that class.

### 2.2. What Happens with Only @FunctionName?

A class with `@FunctionName` that is not a Spring component can still work as a regular Azure Java Function. However, there is **no guarantee** that the Spring Cloud Function adapter will inject `FunctionCatalog` or Spring beans into an object not managed by Spring. For modern SCF integration, annotate the class with `@Component` or `@Service` and ensure it falls within component scan scope.

### 2.3. One Class Can Contain Multiple Azure Functions

You can place multiple `public` methods annotated with `@FunctionName` inside a single Spring component class, each with its own trigger/route. Azure Function names must be **unique within the Function App**. The Java method name does not have to match the function name:

~~~java
@FunctionName("orderStatus")
public String calculateStatus(/* Azure trigger argument */) {
    return "DONE";
}
~~~

This is an annotation illustration fragment, not a complete handler because the trigger parameter still needs to be defined. A complete example is in Section 4.

## 3. Adapter Dependencies and Build Tools

### 3.1. Maven

The application needs dependencies compatible with the chosen **Spring Boot** and **Spring Cloud BOM**:

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

Version `1.3.1` of the Azure Java library is an **illustrative API baseline per Microsoft Learn**, not a claim that it is the latest version. When initializing a new project, use the template and versions approved by your project. The Spring Cloud Function adapter version must be managed **on the same release line** as `spring-cloud-function-context` to avoid mixing major versions.

| Component | Purpose |
| --- | --- |
| `spring-cloud-function-adapter-azure` | Connects the Spring context, beans, and `FunctionCatalog` with the Azure Worker. |
| `azure-functions-java-library` | Provides `@FunctionName`, `@HttpTrigger`, `HttpRequestMessage`, `ExecutionContext`, etc. |
| `spring-cloud-function-context` | `FunctionCatalog`, function registration, and composition; usually a transitive dependency of the adapter. |
| `azure-functions-maven-plugin` | Scans Azure annotations, generates `function.json`, sets up staging layout, and runs/deploys. |
| `spring-boot-starter-test` | Unit/integration tests for Spring/SCF. |

**Build plugins are not runtime libraries.** Simply adding the adapter to `dependencies` does not produce a package that the Azure Host can discover. Conversely, the Azure Maven plugin can package a regular Java Function, but it does not automatically make a class a Spring component.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Gradle projects use the `com.microsoft.azure.azurefunctions` plugin to package/run/deploy. Do not mix both Maven and Gradle build lifecycles simply because documentation covers both. SCF 4.0.0+ is required by the documentation for the modern `@Component` + Azure handler model.

### 3.3. Do Not Use FunctionInvoker for New Projects

SCF 3.x guides showed examples extending `FunctionInvoker`. Current documentation marks `FunctionInvoker` **deprecated**; the examples in this lesson use Spring-managed `@Component` classes and Azure annotations as the recommended model. When upgrading legacy projects, verify code and release trains before replacing APIs.

## 4. Complete Example: One @Component, Two @FunctionName Methods

### 4.1. Requirements

An endpoint receives a `POST` body containing a text order code:

~~~text
Input:  "  dh-207  "
Output: "DH-207"
~~~

We split the business logic into two beans:

- `trimCode: Function<String,String>` strips leading/trailing whitespace.
- `upperCode: Function<String,String>` converts to uppercase using `Locale.ROOT`.

Inside the same Spring component handler, there are **two Azure Functions**:

1. `normalizeByBean`: uses direct bean injection.
2. `normalizeByCatalog`: uses the composition `trimCode|upperCode` looked up via `FunctionCatalog`.

~~~mermaid
flowchart LR
    A["POST /api/orders/bean"] --> B["normalizeByBean"]
    C["POST /api/orders/catalog"] --> D["normalizeByCatalog"]
    E["@Component OrderAzureHandler"] -. "Spring managed" .-> B
    E -. "Spring managed" .-> D
    B --> F["Injected trimCode and upperCode"]
    D --> G["FunctionCatalog: trimCode|upperCode"]
    F --> H["Result DH-207"]
    G --> H
~~~

### 4.2. Spring Boot Configuration and Business Functions

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
    public Function<String, String> trimCode() {
        return String::strip;
    }

    @Bean
    public Function<String, String> upperCode() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

This is pure **Spring Cloud Function** code: it does not import the Azure Java SDK. Both functions can be reused across HTTP, event streams, an `IntegrationFlow`, or another serverless adapter if that adapter provides appropriate data conversion.

Placing `@SpringBootApplication` in the `example.azure` package ensures component scanning detects the handler class in the same package. The Azure Worker invokes the handler, rather than calling `main(...)` on every request.

### 4.3. Handler with Constructor Injection

Create `src/main/java/example/azure/OrderAzureHandler.java`:

~~~java
package example.azure;

import java.util.Objects;
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

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final Function<String, String> trimCode;
    private final Function<String, String> upperCode;
    private final Function<String, String> composed;

    public OrderAzureHandler(
            @Qualifier("trimCode") Function<String, String> trimCode,
            @Qualifier("upperCode") Function<String, String> upperCode,
            FunctionCatalog catalog) {

        this.trimCode = trimCode;
        this.upperCode = upperCode;
        this.composed = Objects.requireNonNull(
                catalog.lookup("trimCode|upperCode"),
                "Composition trimCode|upperCode not found");
    }

    @FunctionName("normalizeByBean")
    public HttpResponseMessage normalizeByBean(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/bean")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");
        if (input.isBlank()) {
            return badRequest(request);
        }

        String normalized = upperCode.apply(trimCode.apply(input));
        context.getLogger().info("normalizeByBean processed");
        return ok(request, normalized);
    }

    @FunctionName("normalizeByCatalog")
    public HttpResponseMessage normalizeByCatalog(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/catalog")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");
        if (input.isBlank()) {
            return badRequest(request);
        }

        String normalized = composed.apply(input);
        context.getLogger().info("normalizeByCatalog processed");
        return ok(request, normalized);
    }

    private HttpResponseMessage badRequest(
            HttpRequestMessage<Optional<String>> request) {
        return request
                .createResponseBuilder(HttpStatus.BAD_REQUEST)
                .header("Content-Type", "text/plain; charset=utf-8")
                .body("Order code must not be blank")
                .build();
    }

    private HttpResponseMessage ok(
            HttpRequestMessage<Optional<String>> request,
            String value) {
        return request
                .createResponseBuilder(HttpStatus.OK)
                .header("Content-Type", "text/plain; charset=utf-8")
                .body(value)
                .build();
    }
}
~~~

**Expected behavior:** Both `POST /api/orders/bean` and `POST /api/orders/catalog` with body `"  dh-207  "` return `"DH-207"`. Empty or whitespace-only bodies return HTTP 400. The two methods are separate Azure Functions sharing the same logic inside the Spring context.

### 4.4. Significance of Constructor Injection

Because there are two `Function<String,String>` beans, injecting by type without qualifying the bean would leave Spring unable to decide which one to pick. `@Qualifier("trimCode")` and `@Qualifier("upperCode")` resolve that ambiguity.

With `FunctionCatalog`, the constructor looks up `"trimCode|upperCode"` **once** when the bean is created. `Objects.requireNonNull` makes the application fail fast if a name is misconfigured, rather than waiting until the first HTTP request arrives. When handling requests, the method simply invokes the already-resolved function.

Constructor injection also allows fields to be `final` and prevents accidentally instantiating the handler outside Spring. **Do not manually call `new OrderAzureHandler(...)` in Azure handling code**, because doing so bypasses Spring adapter instance management.

## 5. Azure Handler Signature

Example:

~~~java
@FunctionName("normalizeByCatalog")
public HttpResponseMessage normalizeByCatalog(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/catalog")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    // ...
}
~~~

| Element | Explanation |
| --- | --- |
| `@FunctionName("normalizeByCatalog")` | Identifies the Azure Function during packaging, discovery, and invocation. |
| `public` | Azure Java Functions require entrypoint methods to be `public`. |
| `@HttpTrigger` | Marks the input parameter as triggered by an Azure HTTP trigger. |
| `name = "request"` | Binding name, independent of the Java method name. |
| `methods = {POST}` | Accepts only POST per trigger design. |
| `authLevel = FUNCTION` | The host enforces a function/host key policy for the HTTP trigger in cloud environments. |
| `route = "orders/catalog"` | Relative route; defaults to the `/api` prefix unless changed in host config. |
| `HttpRequestMessage<Optional<String>>` | Optional String body along with headers and query parameters. |
| `ExecutionContext` | Context of the current invocation: logger, invocation ID, etc. |

**Note:** `AuthorizationLevel.FUNCTION` does not constitute a complete auth solution for every public/multi-tenant scenario. Local Core Tools may not enforce keys the same way the cloud does; always test authorization in the target environment. Avoid `ANONYMOUS` unless intentionally exposing a public endpoint.

### 5.1. Java Method Name and Azure Function Name Can Differ

A method can be named `execute(...)` while carrying `@FunctionName("normalizeByCatalog")`. The Azure Java Worker identifies functions from annotations/metadata rather than the method name when `@FunctionName` specifies it.

### 5.2. Route Parameters with @BindingName

A variant reading the order ID from the URL:

~~~java
@FunctionName("orderLookup")
public HttpResponseMessage lookup(
        @HttpTrigger(
                name = "req",
                methods = {HttpMethod.GET},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/{id}")
        HttpRequestMessage<Optional<String>> request,
        @BindingName("id") String id,
        ExecutionContext context) {
    return request.createResponseBuilder(HttpStatus.OK)
            .body(id)
            .build();
}
~~~

Requires importing `com.microsoft.azure.functions.annotation.BindingName`. This is an independent function illustrating route parameters, not something required in the main demo. Authorization, ID validation, and response serialization should be designed separately in real deployments.

### 5.3. One Function Has One Trigger

An Azure Function is invoked by **one trigger**: HTTP, Queue, Timer, or another type. You can add extra input/output bindings, but you cannot attach two triggers simultaneously to the same method and let Azure "pick one." If the same business logic has two event sources, write two handler methods and invoke the shared `Function`/`Consumer` bean.

## 6. Who Generates function.json?

The Azure Maven/Gradle plugin scans `@FunctionName`, `@HttpTrigger`, `@QueueTrigger`, etc. during the build to generate binding metadata and package the Azure Functions app.

**Illustrative** metadata for the catalog method:

~~~json
{
  "bindings": [
    {
      "type": "httpTrigger",
      "direction": "in",
      "name": "request",
      "methods": ["post"],
      "authLevel": "function",
      "route": "orders/catalog"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ],
  "scriptFile": "../<artifact-name>.jar",
  "entryPoint": "example.azure.OrderAzureHandler.normalizeByCatalog"
}
~~~

This is **not** guaranteed to be byte-for-byte identical across all plugin versions. Exact JAR names and layouts depend on build configuration. Do not edit staging metadata as a source of truth; update annotations or plugin config and re-package.

Two `@FunctionName` methods normally produce two separate function metadata directories:

~~~text
Azure Function App package
  host.json
  normalizeByBean/
    function.json
  normalizeByCatalog/
    function.json
  lib/
    ...
  [application artifact]
~~~

If the Azure Host only shows one function, inspect **Azure discovery**, not just whether Spring created the bean.

## 7. Main Class, Azure Package, and Runtime

### 7.1. Declaring the Spring Main Class

The Spring adapter needs to know the `@SpringBootApplication` class:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

You can also set the environment variable `MAIN_CLASS=example.azure.AzureOrderApplication` in local settings or Azure Function App settings. If multiple Spring Boot entrypoints exist on the classpath, specify it explicitly.

### 7.2. Maven Plugin and Boot Repackaging

`spring-cloud-function-adapter-azure` is a runtime library; the Azure Functions Maven/Gradle plugin must build the proper Azure function package. **A standard Spring Boot executable fat JAR is not directly compatible with the package layout expected by the Azure Java Worker.** Therefore, SCF documentation instructs disabling/adjusting Boot repackaging or using an appropriate thin layout.

`build/plugins` skeleton:

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
                <appName>orders-functions-unique-name</appName>
                <resourceGroup>example-functions-rg</resourceGroup>
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

**Note:** `1.22.0` is the plugin version illustrated/cited as a minimum baseline in Spring documentation, not a claim that it is the latest release. This is a configuration fragment to merge into a POM with a suitable Boot parent/Spring Cloud BOM, dependency management, Java target, and Azure plan; `appName`, resource group, and region must be customized for your project.

### 7.3. host.json and local.settings.json

Example `src/main/resources/host.json`:

~~~json
{
  "version": "2.0"
}
~~~

Example `local.settings.json` during development:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.AzureOrderApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

Local settings are not production settings; do not commit real secrets to the repository. `UseDevelopmentStorage=true` requires Azurite or a compatible emulator when the runtime or triggers use Azure Storage. The compiler Java target, Azure Host/runtime, and deployment environment must match.


## 8. Running Locally and Verifying Discovery

### 8.1. Tools and Steps

To test Azure Functions Java on a development machine, prepare an appropriate JDK, Maven or Gradle, **Azure Functions Core Tools v4**, and Azurite/storage emulator if bindings require Azure Storage.

With the Maven example:

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

The `package` command must generate metadata for both **`normalizeByBean`** and **`normalizeByCatalog`**. When the Functions Host starts up, inspect the logs to confirm both function names and routes are recognized.

With the default host configuration, the URLs typically look like:

~~~text
POST http://localhost:7071/api/orders/bean
POST http://localhost:7071/api/orders/catalog
~~~

The `/api` prefix and port can be changed in the host configuration. Local Core Tools may apply function keys differently from the cloud environment, so local smoke tests do not replace testing authentication/authorization upon deployment.

### 8.2. Sending a Request

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/catalog" \
  -H "Content-Type: text/plain" \
  --data "  dh-207  "
~~~

Expected result:

~~~text
HTTP/1.1 200 OK

DH-207
~~~

The `/orders/bean` endpoint returns the same body. Whitespace-only requests are checked by the handler and return 400. This is deliberate handler validation, not the Azure Host knowing business rules.

### 8.3. Distinguishing Errors from Logs

- **Host does not see the function:** check `@FunctionName`, trigger annotation, build plugin, `function.json`, and package layout.
- **Host sees the function, but injection fails:** check `@Component`, `@SpringBootApplication` main class, component scan scope, and the adapter.
- **Spring injects successfully, but lookup fails:** check the `"trimCode|upperCode"` name, generic signatures, and bean registration.
- **Executes, but returns wrong output:** check the HTTP body, validation, converters, and business logic.

An application can have all Spring beans intact yet still fail Azure Host discovery if build metadata is wrong. Conversely, a function with valid metadata can still fail during Spring bean creation.

## 9. Bean Lifecycle and ExecutionContext

### 9.1. Spring Singletons and Multiple Invocations

`@Component` defaults to singleton scope. The Azure Worker can reuse the Spring context/handler across multiple invocations; a Function App can run concurrently and scale out across multiple instances. Therefore:

- Do not store request bodies, function keys, trace IDs, or `ExecutionContext` in mutable fields for use in subsequent invocations.
- Avoid unsynchronized caches if concurrent invocations can write the same data.
- Do not treat in-memory state inside a Spring singleton as durable state across Azure Functions instances.
- Resource clients such as DB/HTTP clients should have explicitly managed lifecycles and thread safety.

Incorrect example:

~~~java
@Component
class UnsafeState {
    private String lastOrderCode;

    String process(String input) {
        lastOrderCode = input;
        return lastOrderCode;
    }
}
~~~

When two invocations run concurrently, values can be overwritten. This snippet **illustrates a design flaw** and must not be placed into the demo configuration.

### 9.2. Constructor Injection and Azure Instances

The handler:

~~~java
public OrderAzureHandler(
        @Qualifier("trimCode") Function<String, String> trim,
        @Qualifier("upperCode") Function<String, String> upper,
        FunctionCatalog catalog) {
    // ...
}
~~~

requires Spring to resolve three dependencies. Do not manually instantiate `new OrderAzureHandler(...)` outside Spring if you expect the adapter to manage the handler. Also avoid calling `SpringApplication.run(...)` inside each `@FunctionName` method: the Spring context is typically initialized once for the worker lifecycle, and creating a context per request wastes resources and can cause conflicting configurations.

### 9.3. ExecutionContext Belongs to the Invocation

`ExecutionContext` is the Azure invocation context, commonly used for logging and reading the invocation ID:

~~~java
context.getLogger().info(
        "Invocation: " + context.getInvocationId());
~~~

It is **supplied by the Azure Java Worker as a method parameter**, not a singleton dependency to inject via a Spring constructor. SCF provides the `AzureFunctionUtil.enhanceInputIfNecessary(...)` utility to attach the execution context to a `Message<?>` when a function has a message-aware contract. However, to keep business logic independent of Azure, pass only genuinely needed domain metadata or keep logging inside the handler.

## 10. Direct Bean Injection vs. FunctionCatalog

### 10.1. Two Ways to Invoke the Same Logic

**Direct Spring beans:**

~~~java
String result = upperCode.apply(trimCode.apply(input));
~~~

**FunctionCatalog composition:**

~~~java
Function<String, String> pipeline =
        catalog.lookup("trimCode|upperCode");

String result = pipeline.apply(input);
~~~

| Aspect | Direct Bean | FunctionCatalog |
| --- | --- | --- |
| Instance source | Spring dependency injection. | Looks up functions by definition in the catalog. |
| Composition | Chained manually or via Java `andThen`. | String `"f1|f2"`. |
| Wrapper/type conversion | No catalog wrapper by default. | Uses the SCF model and configured type converters. |
| Best fit | Handler knows a few fixed beans. | Want composition, abstraction, and multi-adapter reuse. |
| Common pitfalls | Missing `@Qualifier` when multiple beans share a type. | Wrong function name or incompatible generic types. |

The composition `trimCode|upperCode` means the output of `trimCode` feeds into `upperCode`. If one function outputs `Integer` and the next expects `OrderRequest`, you cannot assume the two are compatible just by joining them with `|`. Conversions must be explicit and tested.

### 10.2. Do Not Take Arbitrary Bean Names from HTTP Input

Code to avoid with untrusted requests:

~~~java
String definition =
        request.getQueryParameters().get("functionName");

Function<?, ?> selected = catalog.lookup(definition);
~~~

Such an endpoint could let callers invoke functions not intended for public APIs. If dynamic routing is needed, use an allowlist of function names, authorization, and controlled logging. In the main example, the function definition is a fixed string in the constructor.

## 11. Multiple @FunctionName Methods for Different Triggers

### 11.1. Queue Trigger Reusing Business Logic

The same Spring `Function<String,String>` bean can be called from an event-driven handler:

~~~java
@FunctionName("normalizeQueueOrder")
public void normalizeQueueOrder(
        @QueueTrigger(
                name = "orderMessage",
                queueName = "order-events",
                connection = "AzureWebJobsStorage")
        String orderId,
        ExecutionContext context) {

    String normalized = composed.apply(orderId);
    context.getLogger().info("Queue item processed");
}
~~~

This is an **illustrative additional method** for `OrderAzureHandler` and requires importing `com.microsoft.azure.functions.annotation.QueueTrigger`. Running it requires Queue Storage, a valid connection, and the appropriate extension. Merely calling the function and logging does not automatically produce an output message; to emit events to another broker/queue, declare an output binding or use the corresponding client API.

With a Queue Trigger, Azure manages acknowledgement, retries, and poison queues according to host/extension settings. Redelivery can occur, so consumers performing side effects must be idempotent by business key or event ID.

### 11.2. Timer Trigger Calling a Supplier or Service

~~~java
@FunctionName("scheduledAudit")
public void scheduledAudit(
        @TimerTrigger(
                name = "timer",
                schedule = "0 0 */5 * * *")
        String scheduleInfo,
        ExecutionContext context) {

    context.getLogger().info("Timer triggered");
    // Call the injected Supplier or Spring service.
}
~~~

This is a **separate method example** requiring `com.microsoft.azure.functions.annotation.TimerTrigger`. Azure uses a six-field NCRONTAB schedule; the expression above illustrates running every five hours. Do not assume declaring `@Bean Supplier<T>` creates a Timer Trigger automatically: the schedule and entrypoint still require an Azure binding.

**Do not create a single method with both HTTP and Queue triggers.** Each Azure Function has only one trigger; if two sources should execute the same logic, write two handler methods sharing the same business service/function.

## 12. Three-Layer Testing

### 12.1. Business Unit Tests

No Azure Host required:

~~~java
AzureOrderApplication config = new AzureOrderApplication();

String result = config.upperCode()
        .apply(config.trimCode().apply("  dh-207  "));

assertEquals("DH-207", result);
~~~

Uses JUnit 5 with `assertEquals`. Testing the beans directly verifies business results, without claiming that Spring DI or Azure annotation discovery is wired properly.

### 12.2. Spring Context and Catalog

~~~java
@SpringBootTest(classes = AzureOrderApplication.class)
class OrderCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler handler;

    @Test
    void handlerIsSpringManagedAndCompositionWorks() {
        assertNotNull(handler);

        Function<String, String> normalize =
                catalog.lookup("trimCode|upperCode");

        assertNotNull(normalize);
        assertEquals("DH-207",
                normalize.apply("  dh-207  "));
    }
}
~~~

Requires imports for Spring Boot Test, `@Autowired`, `FunctionCatalog`, `Function`, JUnit 5, and Assertions. Spring context tests detect component scanning issues, bean ambiguity, catalog definitions, and missing adapter dependencies.

### 12.3. Annotation Tests with Reflection

~~~java
@Test
void functionNamesAreDistinct() throws NoSuchMethodException {
    Method direct = OrderAzureHandler.class.getMethod(
            "normalizeByBean",
            HttpRequestMessage.class,
            ExecutionContext.class);

    Method viaCatalog = OrderAzureHandler.class.getMethod(
            "normalizeByCatalog",
            HttpRequestMessage.class,
            ExecutionContext.class);

    assertEquals("normalizeByBean",
            direct.getAnnotation(FunctionName.class).value());
    assertEquals("normalizeByCatalog",
            viaCatalog.getAnnotation(FunctionName.class).value());
}
~~~

Add imports for `java.lang.reflect.Method`, Azure `FunctionName`, `HttpRequestMessage`, and `ExecutionContext`. Annotation reflection tests do not replace verifying that the Azure build plugin generates valid metadata.

### 12.4. Host-Level Integration Tests

| Case | Expected |
| --- | --- |
| `POST /api/orders/bean` with `" dh-207 "` | 200, body `DH-207`. |
| `POST /api/orders/catalog` with the same body | 200, same output as the bean endpoint. |
| POST with blank/whitespace-only body | 400 per handler validation. |
| GET to a POST-only route | Not handled as a valid POST; exact status is defined by the host. |
| Missing function key in the cloud with `authLevel=FUNCTION` | Rejected according to host policy. |
| Duplicate function name / method missing annotation | Build or discovery must catch the issue. |
| Wrong main class / adapter | Spring context or injection fails; inspect host logs. |

When using Queue/Timer triggers, also test extensions, schedules, connections, retry/redelivery, and idempotency.

## 13. Layered Troubleshooting

| Symptom | Potential Cause | Remediation |
| --- | --- | --- |
| Azure Host does not see handler | Wrong annotation/build metadata. | Check `public` method, `@FunctionName`, trigger, and `function.json`. |
| Host sees function, but method does not run | Wrong route/auth/binding. | Check HTTP method, prefix, keys, and connection settings. |
| Cannot inject Spring beans | Handler is not managed by Spring. | Check `@Component`, component scan, main class, and Azure adapter. |
| `NoSuchBeanDefinitionException` for `FunctionCatalog` | Wrong SCF context/version/auto-configuration. | Check dependency management and adapter. |
| Multiple `Function<String,String>` beans | Spring cannot pick one. | Use `@Qualifier`. |
| Composition lookup returns null | Wrong function name or bean not registered. | Check catalog, type/signature, and name. |
| HTTP 500/`ClassCastException` | Wrong serialization/conversion. | Check body and generic types at the boundary. |
| Boot fat JAR cannot be loaded by Azure Worker | Wrong package layout. | Disable/adjust Boot repackage, use the Azure plugin. |
| Azure Host loads function but Spring startup fails | Wrong main class, missing library, or version conflict. | Check `MAIN_CLASS`, package, and dependency tree. |
| Works locally, fails in the cloud | Different Java runtime, auth, or app settings. | Verify Function App plan, Java version, and secrets. |
| Data from one request leaks into another | Mutable state inside singleton handler. | Use local variables and stateless design. |
| Queue event processed multiple times | Retry/redelivery. | Idempotency by event ID; error policy per trigger. |

### Short Diagnostic Workflow

1. Did the Azure plugin generate metadata for the expected number of function names?
2. Did the Azure Host discover the right names, triggers, and routes?
3. Is the Spring adapter on the runtime classpath and compatible with Boot/SCF?
4. Is the main class accurate and does component scan find the handler?
5. Does constructor injection resolve all beans?
6. Are the catalog composition order and data types valid?
7. Do the HTTP body/response or Queue events match the contract?
8. Are security, retries, idempotency, and observability configured for the environment?

## 14. Production Design Rules

1. **Thin handlers:** accept trigger input, validate the contract at the boundary, invoke the function/service, and return output.
2. **Pure business functions:** do not mix `HttpRequestMessage`, `ExecutionContext`, or Azure SDK types into logic that does not need them.
3. **Separate Azure and catalog names:** do not let a misconfigured function definition name mislead callers into thinking it is an HTTP route error.
4. **Fail fast:** resolve fixed compositions at bean creation time, with clear definition names in error messages.
5. **Do not store invocation state in singletons:** prefer immutable dependencies and local variables.
6. **Trigger-specific error policies:** HTTP 4xx/5xx differ from Queue retries/poison queues.
7. **Prevent duplicate processing:** Azure can scale out and redeliver events, requiring durable idempotency keys.
8. **Security:** never log secrets/function keys or allow callers to arbitrarily control `FunctionCatalog`.
9. **Observability:** log function name, invocation/correlation ID, and metrics while redacting sensitive data.
10. **Lock versions:** verify Boot, Spring Cloud BOM, SCF Azure adapter, Azure Java library/plugin, and Java runtime together.

## 15. Practice Exercises

- Move `trimCode` and `upperCode` into a separate `@Configuration` class; verify the handler still injects them.
- Rename the Java method `normalizeByCatalog` to `execute` while keeping `@FunctionName("normalizeByCatalog")`; build and verify the Azure function name stays unchanged.
- Replace `@Component` with `@Service`; verify Spring bean registration and Azure discovery.
- Change the catalog definition to `trimCode|missingBean` to observe the fail-fast startup error.
- Add `Function<String,Integer> codeLength` and the composition `trimCode|upperCode|codeLength` for a new Azure function.
- Add a Queue Trigger calling the same business function, then design idempotency when events are redelivered.
- Move the handler to a package outside the main scan; use a Spring test to catch the error and then add `@ComponentScan`.
- Open the staging package and compare the `function.json` files of the two Azure Functions against their corresponding annotations.

## 16. Self-Assessment Questions

- Which two frameworks do `@Component` and `@FunctionName` belong to?
- Why doesn't `@Component` alone create an Azure HTTP function?
- Why can a `@FunctionName` handler run as a Java Function yet fail to inject Spring beans?
- When one class has two `@FunctionName` methods, can both share a single `FunctionCatalog`?
- Why is `@Qualifier` needed when two function beans have the same type?
- Does the composition `trimCode|upperCode` differ from Java `upperCode(trimCode(input))` in core logic? Does it differ in wrappers/catalog handling?
- Why should `ExecutionContext` be a method parameter rather than a singleton dependency?
- If the Host does not see the function but the Spring context test PASSES, what should you check next?
- Can an HTTP Trigger and a Queue Trigger be placed on the same method?
- Why is idempotency required when a consumer is invoked by an Azure Queue Trigger?

## 17. Official Sources

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): adapter 4.0+, `@Component`, `@FunctionName`, `FunctionCatalog`, main class, packaging, Core Tools, and `FunctionInvoker` deprecation.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, catalog, and composition.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): public handler methods, `@FunctionName`, triggers, and binding metadata.
- [Microsoft Learn — Azure Java HttpTrigger API](https://learn.microsoft.com/en-us/java/api/com.microsoft.azure.functions.annotation.httptrigger): route, HTTP methods, auth levels, and request types.
- [Microsoft Learn — HTTP Trigger and Binding](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): HTTP requests/responses.
- [Microsoft Learn — Core Tools Local Run](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): local runtime and HTTP/Queue bindings.
- [Microsoft Learn — Java CLI Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): build/package/run/deploy with Maven.
- [Spring Cloud Function Examples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): sample Azure, Timer, Blob, and Web Adapter handlers.

**Conclusion:** `@Component` marks a **handler class managed and injected by Spring**, while `@FunctionName` marks an **Azure Functions method discovered and invoked by the Host** according to its trigger/binding. With `spring-cloud-function-adapter-azure`, a handler can directly use `Function<T,R>` or compositions via `FunctionCatalog` while keeping business logic decoupled from Azure. You must manage the Spring main class, Azure metadata/packaging, bean scopes, security, and per-trigger error handling so the same functions can be reused across HTTP, events, or serverless platforms.
