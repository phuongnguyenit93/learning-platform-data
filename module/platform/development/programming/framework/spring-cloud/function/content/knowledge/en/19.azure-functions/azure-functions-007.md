# Configuring the Main Application Class and Deployment Packaging

## 1. Problem: Running a Spring Cloud Function Properly in Azure Functions

In **SPRING_CLOUD_FUNCTION**, business logic is modeled using `Supplier<T>`, `Function<T,R>`, and `Consumer<T>` beans, looked up via `FunctionCatalog`, optionally chained via *composition*, and reused across HTTP, event streams, or other serverless adapters. When bringing these beans to **Azure Functions**, functionally correct Java code is **not enough** on its own for the Azure Host to invoke them.

A Spring Cloud Function application deployed to Azure needs three relatively independent configuration layers:

1. **Spring application entrypoint:** a `@SpringBootApplication`/`@SpringBootConfiguration` class so the adapter finds the Spring configuration, scans handlers, and creates function beans and `FunctionCatalog`.
2. **Azure function entrypoints:** `public` Java methods annotated with `@FunctionName` and trigger/binding annotations so the Azure Java Worker knows **when** and **which method** to invoke.
3. **Azure deployment package:** the Azure Maven/Gradle plugin analyzes annotations, generates metadata such as `function.json`, places `host.json` in the right spot, and builds a layout containing the application JAR and dependencies for the Azure Host.

If any layer is wrong, you can end up with **Spring tests passing while Azure sees no functions**, or **Azure finding the HTTP endpoint while Spring dependency injection fails**.

### What Will You Be Able to Do After This Lesson?

- Write the main Spring Boot class and define component scanning boundaries.
- Understand how the adapter resolves `Main-Class`/`Start-Class` or the `MAIN_CLASS` variable.
- Distinguish the Spring `main(...)` entrypoint from an Azure `@FunctionName` handler.
- Configure Maven/Gradle so the Azure plugin builds the package; avoid conflicts with Spring Boot *repackaged executable JARs*.
- Read the `target/azure-functions/<appName>/...` layout, `function.json`, and `host.json`.
- Run locally with Azure Functions Core Tools, then choose the deployment method matching your hosting plan.
- Design practical CI/CD, secrets configuration, post-release verification, and rollback workflows.
- Diagnose build, Azure discovery, Spring context, catalog, trigger, and deployment errors in order.

**Scope:** this lesson covers configuring/packaging an **Azure adapter using annotated Java handlers**. Do not use Docker or another Azure Web framework unless there is an explicit reason.

## 2. Initialization and Deployment Architecture

~~~mermaid
flowchart TB
    subgraph Source["Java source and configuration"]
      A["@SpringBootApplication<br/>OrderFunctionApplication"]
      B["@Bean Function / Supplier / Consumer"]
      C["@Component OrderAzureHandler<br/>@FunctionName + @HttpTrigger"]
      D["pom.xml or build.gradle<br/>host.json"]
    end
    subgraph Build["Build and staging"]
      E["Java compile"]
      F["Azure Maven/Gradle plugin"]
      G["function.json per Azure Function<br/>host.json + app jar + lib"]
    end
    subgraph Runtime["Azure Functions Host / Java Worker"]
      H["Reads binding metadata and discovers triggers"]
      I["Azure adapter locates Spring main class"]
      J["Spring ApplicationContext<br/>DI + FunctionCatalog"]
      K["Spring-managed Azure handler"]
    end
    A --> E
    B --> E
    C --> E
    D --> F
    E --> F
    F --> G
    G --> H
    H --> K
    I --> J
    J --> K
    K --> L["HTTP response / Queue output / event"]
~~~

**Two flows inside the same package:**

- **Build-time:** the compiler/plugin finds Azure annotations, generating metadata and the staging layout. `@Bean Function` does **not** automatically generate a `function.json`.
- **Runtime:** the adapter locates the Spring configuration class, builds the `ApplicationContext`, and injects services and `FunctionCatalog` into the Azure handler. `@FunctionName` does **not** automatically make a class a Spring component.

| Concept | Meaning | What Happens If Missing |
| --- | --- | --- |
| `@SpringBootApplication` | Spring configuration root, component scan, and auto-configuration. | The adapter may fail to determine which context to initialize. |
| `@Bean Function<T,R>` | Registers logic in the Spring context/SCF catalog. | Function not found when calling `catalog.lookup(...)`. |
| `@Component` on handler | Lets Spring manage the instance and constructor injection. | The Azure method may be discovered, but DI fails as expected. |
| `@FunctionName` | Unique Azure Function identifier within the Function App. | The Azure Host does not see the corresponding entrypoint. |
| `@HttpTrigger`/`@QueueTrigger` | Specifies the trigger source and binding. | No valid trigger for the host to execute. |
| `Main-Class`/`MAIN_CLASS` | Points the adapter to the exact Spring configuration class. | Spring startup may fail or pick the wrong main class. |
| Azure plugin | Generates Azure metadata and package. | You get a JAR, but not a valid deployment artifact. |

### 2.1. The Spring Main Class Is Not an Azure Entrypoint

`public static void main(String[] args)` is the entrypoint for a **Spring Boot application run in the traditional Java/Boot way**. In Azure Functions, the Java Worker executes `@FunctionName` methods based on binding metadata; the Spring main class serves to **locate configuration and build the application context**, not as an endpoint the Azure Host calls on every HTTP request.

**Never call `SpringApplication.run(...)` inside a `@FunctionName` method on every invocation.** Doing so recreates the application context repeatedly, increases latency/cost, and makes bean lifecycles hard to control.

## 3. Designing the Project Directory Before Coding

Example of a small Maven project:

~~~text
azure-order-functions/
├── pom.xml
├── local.settings.json              # Local only, never commit secrets
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/azure/
    │   │       ├── OrderFunctionApplication.java
    │   │       └── OrderAzureHandler.java
    │   └── resources/
    │       ├── application.properties
    │       └── host.json
    └── test/
        └── java/example/azure/
            └── OrderFunctionApplicationTest.java
~~~

**Package convention:** place the `@SpringBootApplication` class in the **root package** `example.azure`, at or above the location of all Spring components. Default component scanning from this package detects the handler and configurations underneath.

If you move the handler to `com.company.handlers` outside the root package, Spring may not create that bean. Fix this with proper package placement or explicit `scanBasePackages`/`@ComponentScan` configuration. Never use unrestricted full-classpath scanning, as it risks creating unintended beans.

### 3.1. Separating the Handler and Function Beans

The handler depends on the Azure SDK, whereas business function beans should accept/return domain data or simple Java types:

~~~text
HTTP Trigger -> OrderAzureHandler -> FunctionCatalog
                                        |
                                        +-> normalizeOrder
                                        +-> addReferencePrefix
                                              -> "REF-DH-701"
~~~

When moving business logic to a Queue Trigger or another HTTP adapter, you call the same beans and only swap the boundary handler and serialization/ack policy.

## 4. Spring Boot Main Class and Functional Beans

Create `src/main/java/example/azure/OrderFunctionApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionApplication.class, args);
    }

    @Bean
    public Function<String, String> normalizeOrder() {
        return text -> {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                        "Order code must not be blank");
            }
            return text.strip().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, String> addReferencePrefix() {
        return code -> "REF-" + code;
    }
}
~~~

Here:

- `@SpringBootApplication` is the **root Spring configuration**, enabling component scanning.
- The two `@Bean` methods register functional beans named **`normalizeOrder`** and **`addReferencePrefix`**.
- `FunctionCatalog` can return the composition `normalizeOrder|addReferencePrefix` once both beans are discovered.
- The `Function<String,String>` signature is easy to test and independent of Azure.
- `main(...)` is useful when running Spring Boot in other environments; the Azure adapter still selects this class as the application entrypoint from config/manifest.

### 4.1. Names to Distinguish

| Name | System | Responsibility |
| --- | --- | --- |
| `example.azure.OrderFunctionApplication` | Spring application | Main configuration class. |
| `normalizeOrder` | Spring bean / SCF catalog | Normalizes order codes. |
| `addReferencePrefix` | Spring bean / SCF catalog | Prepends the reference prefix. |
| `normalizeOrder|addReferencePrefix` | SCF composition | Chains both transformations. |
| `normalizeAzureOrder` | Azure Function | Name displayed and invoked by the Azure Host. |
| `orders/normalize` | Azure HTTP trigger | URL route, nested under `/api` by default. |
| `order-functions-demo-unique` | Azure Function App resource | Resource container managing and deploying the Azure functions. |

One Spring application can contain **many function beans**, yet the Azure Host only sees Azure handler methods that are properly annotated and packaged. Similarly, one Azure Function App can contain multiple `@FunctionName` methods, sharing host settings and deployment boundaries.

## 5. Azure Handler Using FunctionCatalog

Create `src/main/java/example/azure/OrderAzureHandler.java`:

~~~java
package example.azure;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import java.util.logging.Level;

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

    private final Function<String, String> pipeline;

    public OrderAzureHandler(FunctionCatalog catalog) {
        this.pipeline = Objects.requireNonNull(
                catalog.lookup("normalizeOrder|addReferencePrefix"),
                "Function composition not found");
    }

    @FunctionName("normalizeAzureOrder")
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
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Order code must not be blank")
                    .build();
        }

        try {
            String result = pipeline.apply(input);

            context.getLogger().info("Order normalized");

            return request
                    .createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(result)
                    .build();
        }
        catch (RuntimeException failure) {
            context.getLogger().log(
                    Level.SEVERE, "Order processing failed", failure);

            return request
                    .createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Unable to process order code")
                    .build();
        }
    }
}
~~~

If the body is `" dh-701 "`, the expected output is **`REF-DH-701`**. In real applications, use a clear error taxonomy: validation errors -> HTTP 400, system errors -> 5xx, and never log sensitive payloads. The example proactively rejects blank bodies before invoking the pipeline.

### 5.1. Only One Azure Function Despite Two @Bean Definitions

The class has **one** `@FunctionName("normalizeAzureOrder")` method, so the Azure plugin generates metadata for **one Azure Function**—it does not auto-generate two Azure Functions from `normalizeOrder` and `addReferencePrefix`.

### 5.2. Why Constructor Injection?

`OrderAzureHandler` is managed by Spring via `@Component`. When instantiating the bean, Spring injects `FunctionCatalog` and looks up the composition once; `Objects.requireNonNull` ensures misspelled function names are caught early (*fail fast*). Never instantiate the handler via `new OrderAzureHandler(...)` outside the Spring adapter if you expect DI to work.

### 5.3. Where Do @FunctionName and @HttpTrigger Go?

- `@FunctionName` goes on the **`public` method**.
- `@HttpTrigger` goes on that method's **input parameter**.
- `@Component` goes on the **handler class**.
- `@SpringBootApplication` goes on the **Spring configuration class**.

The Azure Maven/Gradle plugin generates binding metadata from Azure annotations; Spring component scanning does not replace this step.

## 6. Dependencies and Version Alignment

### 6.1. Maven Dependencies

In a project that already has a compatible **Spring Boot parent** and **Spring Cloud BOM**:

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

**This is a POM snippet, not a full `pom.xml`.** Use a Spring Boot parent/Cloud BOM from a release train published as compatible; `spring-cloud-function-adapter-azure` requires the modern SCF **4.0.0+** model. `1.3.1` for the Azure Java library is merely an **API illustration version**, not always the latest release; in real projects, use the version from your Azure Java template/version policy.

| Component | Why Needed? |
| --- | --- |
| `spring-cloud-function-adapter-azure` | Spring DI and `FunctionCatalog` inside the Azure Java Worker. |
| `spring-cloud-function-context` | Catalog and function wrapping/composition; typically pulled transitively by the adapter. |
| `azure-functions-java-library` | `@FunctionName`, `@HttpTrigger`, `HttpRequestMessage`, `ExecutionContext`. |
| `spring-boot-starter-test` | JUnit 5 / Spring context tests. |
| `azure-functions-maven-plugin` | **Build plugin** generating metadata and packages, not a runtime dependency. |

Do not add `spring-boot-starter-web` just to handle an Azure `@HttpTrigger`. If you want to run Spring MVC controllers over Azure HTTP, that is a different adapter strategy (`spring-cloud-function-adapter-azure-web`).

### 6.2. Gradle Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Gradle still requires Spring Boot/Spring Cloud dependency management and the Azure Functions Gradle plugin. **Pick one** primary build tool per project; do not maintain Maven and Gradle with diverging configs and deploy inconsistently.

### 6.3. Choosing Java and the Azure Functions Runtime

Azure Functions runtime **4.x** supports Java versions depending on OS/hosting plan; common releases are Java 11, 17, and 21. A project using Java records or Java 17 features should compile and deploy on compatible Java 17+. **Check Microsoft's current support matrix** because support depends on container images, hosting plans, and lifecycle schedules.

Three values must align:

- The JDK used to compile and test locally.
- The Java target/release bytecode emitted by the Maven/Gradle compiler.
- The Java runtime configured on the Azure Function App.

An `UnsupportedClassVersionError` indicates bytecode compiled for a newer Java version than the target runtime.

## 7. Specifying the Main Class: Three Mechanisms

This is the **core part** of this topic.

The Spring Cloud Function Azure adapter needs to know the **`@SpringBootApplication`/`@SpringBootConfiguration` class** to initialize the context. Per Spring documentation, you can use:

1. **Maven `start-class`** or `Main-Class` inside the JAR manifest.
2. **Gradle `jar.manifest`** setting `Main-Class`.
3. **The `MAIN_CLASS` environment variable** locally or in Azure App Settings.

If `MAIN_CLASS` is unset, the adapter searches JARs on the classpath for `Main-Class` entries and identifies the class bearing appropriate Spring Boot application/configuration annotations. Because the classpath can hold multiple JARs/entrypoints, projects should choose **one explicit, tested configuration**.

### 7.1. Maven start-class

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.OrderFunctionApplication</start-class>
</properties>
~~~

`start-class` is a Spring Boot build convention. However, once **Spring Boot repackaging is disabled**, do not assume every build setup automatically writes the desired manifest. The reliable approach is to **inspect the JAR manifest** after building, or configure `maven-jar-plugin` to write `Main-Class` explicitly.

### 7.2. Explicit Maven JAR Manifest

One way to configure the manifest when building a **standard JAR** instead of a Boot executable fat JAR:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifest>
                <mainClass>example.azure.OrderFunctionApplication</mainClass>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

When packaged, the standard JAR contains `META-INF/MANIFEST.MF` with:

~~~text
Manifest-Version: 1.0
Main-Class: example.azure.OrderFunctionApplication
~~~

**Important:** `Main-Class` must point to the **Spring application class**, not `OrderAzureHandler`. The Azure worker uses `function.json`'s `entryPoint` to find the annotated handler method; the Spring adapter uses `Main-Class`/`MAIN_CLASS` to find the context configuration.

### 7.3. Gradle JAR Manifest

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'example.azure.OrderFunctionApplication'
        )
    }
}
~~~

When using the Spring Boot Gradle plugin, prevent `bootJar` from replacing the artifact needed by the Azure plugin. Depending on versions/builds, disable `bootJar` or configure the Azure Gradle plugin to consume the standard JAR with the right layout.

### 7.4. MAIN_CLASS in the Environment

Local `local.settings.json`:

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

In the Azure Function App, configure the **application setting**:

~~~text
MAIN_CLASS=example.azure.OrderFunctionApplication
~~~

Azure App Settings are injected into the runtime environment by the Function App. **Never set `MAIN_CLASS` in local settings and assume it appears on Azure automatically**: `local.settings.json` is not synced to the cloud by default.

### 7.5. Recommended Order

1. Place `@SpringBootApplication` in the root package.
2. Pin `MAIN_CLASS` in the runtime environment when needed, especially in projects with multiple configurations.
3. Ensure the JAR manifest or Maven `start-class` is declared accurately.
4. Verify runtime Spring logs and `@SpringBootTest`.
5. Avoid creating multiple competing `@SpringBootApplication` classes in the same deployment without a clear selection strategy.

## 8. Azure Maven Plugin: Packaging Beyond Compilation

`spring-cloud-function-adapter-azure` is a runtime library; the **Azure Functions Maven plugin** is responsible for generating the Azure package from Java annotations.

### 8.1. Illustrative Plugin Configuration

Add inside `<build><plugins>` in a `pom.xml` that already has Spring Boot/Cloud dependency management:

~~~xml
<plugin>
    <groupId>com.microsoft.azure</groupId>
    <artifactId>azure-functions-maven-plugin</artifactId>
    <version>1.22.0</version>
    <configuration>
        <appName>order-functions-demo-unique</appName>
        <resourceGroup>order-demo-rg</resourceGroup>
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
~~~

Spring Cloud Function documentation cites **`1.22.0` or newer** as the Azure Maven plugin baseline for the modern adapter. This is **not a claim that `1.22.0` is the latest release**. On real projects, pin a recent compatible plugin version, Java runtime, hosting plan, and resource settings.

**`appName`, `resourceGroup`, and `region` in the snippet are illustrative placeholders**. When the plugin provisions Azure resources, the resource group, Azure subscription, service plan, pricing tier, and Function App name must follow governance policies. `appName` must follow naming rules and be unique within the relevant Azure namespace.

### 8.2. Why Is the Plugin `package` Goal Needed?

The Java compiler only emits classes/JARs. The Azure plugin reads `@FunctionName` and `@HttpTrigger` and generates function metadata, the staging layout, and dependencies so the Azure Host discovers the methods.

An **illustrative** snippet of metadata for the handler in Section 5:

~~~json
{
  "scriptFile": "../order-functions-demo.jar",
  "entryPoint": "example.azure.OrderAzureHandler.normalize",
  "bindings": [
    {
      "type": "httpTrigger",
      "direction": "in",
      "name": "request",
      "methods": ["post"],
      "authLevel": "function",
      "route": "orders/normalize"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ]
}
~~~

This is not a strict byte-for-byte required output; `scriptFile` depends on the artifact name and plugin layout. Key checks:

- `entryPoint` points to the **Azure handler**.
- `httpTrigger` declares method, route, and auth.
- The HTTP output binding declares how the response is returned.
- `function.json` is generated by the plugin from annotations, not a source file to hand-edit.

### 8.3. One Function App with Multiple Functions

If source code adds another method `@FunctionName("receiveOrderQueue")` with `@QueueTrigger`, the plugin creates **another function metadata folder** inside the same Function App package. This is **different** from adding another `@Bean Function`—that bean does not automatically appear as an Azure endpoint.

## 9. The Spring Boot Repackaged JAR Problem and Solutions

### 9.1. Why Does a Spring Boot Fat JAR Conflict?

By default, `spring-boot-maven-plugin` can **repackage** the application JAR into an executable Boot archive containing `BOOT-INF/classes`, `BOOT-INF/lib`, and a launcher. The Azure Java Worker instead expects the Azure package layout produced by the Azure Maven/Gradle plugin, with a standard JAR/classpath and corresponding Azure metadata.

Therefore, **never just copy `target/*.jar` to Azure and expect it to run**. An executable Boot fat JAR can run via `java -jar`, yet the Azure Host still cannot locate `@FunctionName` handlers or the Spring adapter.

### 9.2. Simple Option: Disable Boot Repackaging

Inside `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <skip>true</skip>
    </configuration>
</plugin>
~~~

This works well when the project relies on the Azure plugin to create the package. **After disabling it**, make sure Maven still builds a standard JAR with `Main-Class`/`MAIN_CLASS` so the adapter can find the Spring application. Some projects need `maven-jar-plugin` configured as in Section 7.

### 9.3. Other Options

Spring docs also mention **Spring Boot Thin Launcher/layout** as an alternative to skipping the plugin, though compatibility depends on the Boot/SCF versions and build ecosystem. **Do not add `spring-boot-thin-layout` to a modern project** without verifying the artifact is still supported in your target version.

With Gradle, depending on the project:

~~~groovy
tasks.named('bootJar') {
    enabled = false
}
tasks.named('jar') {
    enabled = true
    manifest {
        attributes('Main-Class':
                'example.azure.OrderFunctionApplication')
    }
}
~~~

This is a directional template: task/plugin names and packaging order can vary across Gradle/Spring Boot/Azure plugin versions. Confirm the Azure plugin uses the **standard JAR** and generates a properly structured staging package.

### 9.4. Pre-Packaging Decision Checklist

| Question | If the Answer Is "No" |
| --- | --- |
| Does Maven/Gradle produce an Azure-compatible standard application JAR? | Check Boot repackage/`bootJar`. |
| Does `Main-Class` or `MAIN_CLASS` point to the right Spring configuration? | Fix manifest/app setting. |
| Can the Azure plugin scan the annotated handler? | Check `@FunctionName`, trigger, and `public` method. |
| Does the package include `host.json` and function metadata? | Check the Azure plugin goal and source `hostJson` path. |
| Are runtime dependencies present in the Azure layout? | Check plugin staging/`lib` and dependency resolution. |
| Is the Java target compatible with the Function App? | Check compiler release and Azure runtime. |

**Never edit `function.json` in staging and treat it as a source fix.** Change Java annotations/plugin config and rebuild so the artifact remains reproducible.


## 10. Inspecting the Built Azure Package

### 10.1. Distinguishing Source Folders, Build Output, and Deployment Artifacts

A typical Maven staging layout per Microsoft Learn:

~~~text
azure-order-functions/
├── pom.xml
├── src/main/java/example/azure/...
├── src/main/resources/host.json
└── target/
    ├── classes/
    │   └── example/azure/...
    ├── order-functions-demo.jar
    └── azure-functions/
        └── order-functions-demo-unique/
            ├── host.json
            ├── order-functions-demo.jar
            ├── normalizeAzureOrder/
            │   └── function.json
            ├── bin/
            └── lib/
                └── [dependencies]
~~~

**This is an illustrative diagram**, not an exact file listing for every version. JAR names, `appName`, and some helper directories depend on plugin configuration; do not assume two independent JARs need separate deployment. The core point is **packaging and publishing the Function App staging contents**, not picking a lone JAR from `target/`.

Per Microsoft's Java Functions documentation, a single Function App can hold multiple Java `@FunctionName` methods; all belong to the **same deployment context/package**. Do not bundle multiple independent application JARs as separate Function Apps inside one Function App.

### 10.2. Role of Files After Packaging

| File / Directory | Meaning | What to Check |
| --- | --- | --- |
| Root `host.json` | Shared configuration for the entire Function App. | Correct version/extension bundle/host settings. |
| `normalizeAzureOrder/function.json` | Metadata for one Azure Function. | `entryPoint`, trigger/bindings, method, route, auth level. |
| Application `.jar` | Project Java bytecode and resources. | Package classes and manifest are accurate. |
| `lib/` | Runtime dependencies bundled with the artifact. | Contains Spring, SCF Azure adapter, and required Azure Java SDKs. |
| `bin/` or helper directories | Build/runtime artifacts managed by the plugin. | Generated by the plugin; do not guess or hand-edit. |
| `local.settings.json` | Local development settings file. | Excluded from production packages unless under a specially controlled workflow. |

### 10.3. Verifying the Artifact Instead of Trusting "Build Success"

After running Maven packaging in a hands-on environment:

~~~bash
./mvnw clean package
~~~

Inspect the staging contents using OS-appropriate tools:

~~~bash
# Bash/macOS/Linux: inspect actual package
find target/azure-functions -maxdepth 4 -type f

# Java JDK: inspect JAR contents or manifest
jar tf target/order-functions-demo.jar
unzip -p target/order-functions-demo.jar META-INF/MANIFEST.MF
~~~

These shell examples **depend on your project's JAR name**, not commands executed during authoring. With PowerShell:

~~~powershell
Get-ChildItem -Path target/azure-functions -Recurse -File
jar tf target/order-functions-demo.jar
~~~

If build output paths differ from the example, inspect the artifact name printed by the plugin rather than creating manual copies to match docs.

**Tip:** confirm `function.json`'s `entryPoint` points to `example.azure.OrderAzureHandler.normalize`, while `Main-Class` or `MAIN_CLASS` points to `example.azure.OrderFunctionApplication`. These are **two classes with distinct roles**.

### 10.4. When Creating a ZIP Manually: Capture the Exact Root Contents

When using a ZIP/package deployment method suited to your hosting plan, the archive must contain `host.json` **directly at the extracted root**:

~~~text
CORRECT:
  host.json
  normalizeAzureOrder/function.json
  application.jar
  lib/...

INCORRECT:
  target/azure-functions/order-functions-demo-unique/
    host.json
    normalizeAzureOrder/function.json
    application.jar
~~~

If you zip the parent folder itself, the Azure Host will not find `host.json` at the expected root. Prefer using the Azure build/deployment plugin to reduce packaging errors. Across different hosting plans and deployment technologies, **never assume a single manual ZIP command works for every Function App**.

## 11. host.json, application.properties, and local.settings.json

These three files coexist in the project yet belong to **three distinct configuration layers**.

### 11.1. host.json: Azure Functions Host Configuration

Minimal `src/main/resources/host.json`:

~~~json
{
  "version": "2.0"
}
~~~

If bindings require an extension bundle and the project distributes extensions that way, an example from the Spring reference is:

~~~json
{
  "version": "2.0",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
~~~

Choose an extension bundle **matching your host, trigger types, and Microsoft-supported extension versions**. Never copy a bundle version blindly just because an HTTP sample used it. `host.json` can hold concurrency, logging, and binding-specific settings affecting **all functions** in the Function App.

If `host.json` sits at `src/main/resources/host.json`, point the Azure Maven plugin to it via `<hostJson>src/main/resources/host.json</hostJson>` as shown. Edit `host.json` in source control, re-package, and publish a new artifact; never edit the copy in staging after a build and expect CI to reproduce it.

### 11.2. application.properties: Spring Configuration

Example `src/main/resources/application.properties`:

~~~properties
orders.reference-prefix=REF-
logging.level.example.azure=INFO
~~~

These are optional properties. **The Java snippet in Section 4 hard-codes the `REF-` prefix**, so for the property above to take effect, update the `addReferencePrefix` bean to inject it via `@Value` or a tested `@ConfigurationProperties` class.

Do not confuse Spring properties with Azure app settings. Spring Boot can bind some Spring settings from environment variables and Azure Application Settings, but naming conventions and property source precedence must be verified on your actual release train.

### 11.3. local.settings.json: Local Azure Functions Developer Config

Template at the project root:

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

| Setting | Role |
| --- | --- |
| `FUNCTIONS_WORKER_RUNTIME=java` | Selects the Java worker runtime. |
| `FUNCTIONS_EXTENSION_VERSION=~4` | Selects the Azure Functions 4.x runtime line. |
| `MAIN_CLASS=...` | Selects the Spring Boot application configuration class. |
| `AzureWebJobsStorage` | Host storage/trigger connection per environment. |
| Other business settings | URLs/thresholds/feature flags, matching Spring bindings. |

`UseDevelopmentStorage=true` requires **Azurite** or a compatible emulator when the Host or bindings require storage. When using real Azure Storage, switch to connection/identity settings per policy—never embed real connection strings in guides or commits.

**Critical security notes:**

- `local.settings.json` can hold secrets, so never commit it to a remote repository.
- Core Tools offers local settings encryption, yet encryption does not replace production secret management.
- When publishing a project, **local settings are not automatically pushed to the cloud by default**. Configure Azure Function App settings separately using approved tooling.
- In CI, never print secrets to logs or store them in build artifacts.
- With managed identities, connection settings can use identity-based configurations, provided the binding extension and IAM roles support them.

### 11.4. Distinguishing Settings from Code Artifacts

~~~mermaid
flowchart LR
    H["host.json"] --> A["Azure Host configuration"]
    L["local.settings.json"] --> B["Local environment"]
    P["Application properties"] --> C["Spring ApplicationContext"]
    S["Azure App Settings"] --> D["Cloud environment"]
    B --> A
    D --> A
    D --> C
~~~

When changing `MAIN_CLASS` on Azure, you change **runtime configuration**. When changing handler Java annotations, you must **rebuild/redeploy** to update binding metadata. When changing `host.json`, release the config change as part of a controlled artifact.

## 12. Gradle: Same Goal as Maven, Different Configuration

If a project uses Gradle, do not create an equivalent POM just to deploy to Azure. The Azure Functions Gradle plugin likewise scans annotations and produces the staging package.

### 12.1. Plugins and Dependencies

Directional example for a project with Spring Boot/Spring Cloud dependency management:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '...'
    id 'com.microsoft.azure.azurefunctions' version '1.11.0'
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`'...'` is a **placeholder to replace with the actual Spring Boot version chosen by your project**. Azure plugin `1.11.0` is only an **example from Spring documentation**, not the latest version or a prescription to pin it. Projects require a Spring Cloud BOM and dependency version alignment per release train.

### 12.2. Avoiding Broken bootJar Packaging

With the Spring Boot Gradle plugin, control the `bootJar` task if the Azure plugin expects a standard JAR:

~~~groovy
tasks.named('bootJar') {
    enabled = false
}

tasks.named('jar') {
    enabled = true
    manifest {
        attributes('Main-Class':
                'example.azure.OrderFunctionApplication')
    }
}
~~~

Do not apply this verbatim to every build without checking dependencies and plugin tasks. Task configuration and artifact selection can vary across Gradle versions. Verify that the generated staging package is valid.

### 12.3. Azure Gradle Configuration

Example following plugin structure:

~~~groovy
azurefunctions {
    appName = 'order-functions-demo-unique'
    resourceGroup = 'order-demo-rg'
    region = 'eastasia'

    runtime {
        os = 'linux'
        javaVersion = '17'
    }

    auth {
        type = 'azure_cli'
    }

    appSettings {
        FUNCTIONS_EXTENSION_VERSION = '~4'
    }
}
~~~

Depending on the Azure Functions Gradle plugin version, property syntax/values and hosting plan fields may differ. Check your pinned version and plugin docs. Never assume the plugin automatically chooses your desired enterprise hosting plan/pricing tier if omitted.

### 12.4. Gradle Commands

~~~bash
./gradlew clean azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

These are commands **for learners to run in an appropriate Gradle project**, not commands executed while authoring this lesson. After packaging, verify Azure metadata, Java runtime, and main class just as with Maven.

## 13. Running Locally with Azure Functions Core Tools

### 13.1. Prerequisites

Prepare:

- A JDK matching the Java target, e.g., Java 17.
- Maven or Gradle with the project's wrapper.
- Azure Functions Core Tools **v4**.
- Azurite if the host/bindings need local Azure Storage.
- Azure CLI when planning to deploy/inspect cloud resources (not required for unit tests).

**Never use `java -jar` as a substitute for an Azure Host integration test.** The actual execution target is the Azure Java Worker orchestrated by the Azure Functions Host; `java -jar` does not verify `@FunctionName` metadata or HTTP triggers.

### 13.2. Maven Local Workflow

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

For projects without a Maven wrapper, use an installed `mvn` pinned per organization standards. Watch startup logs to verify the host discovers `normalizeAzureOrder`.

Default route:

~~~text
POST http://localhost:7071/api/orders/normalize
~~~

Port and `routePrefix` can be customized in host configuration. Send a request:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/normalize" \
  -H "Content-Type: text/plain" \
  --data " dh-701 "
~~~

Expected output:

~~~text
HTTP/1.1 200 OK

REF-DH-701
~~~

Test blank/whitespace-only bodies -> HTTP 400. If the host does not list `normalizeAzureOrder`, check Azure annotations/metadata first; if the host lists it but invocations fail in Spring, check the main class and dependency injection.

### 13.3. Checking Function Keys

`AuthorizationLevel.FUNCTION` is an Azure Host policy for HTTP triggers. Local Core Tools may not enforce keys like the cloud does. In real deployments, configure function/host keys per policy, yet **function keys do not fully replace authentication/authorization** for sensitive APIs or multi-tenant applications.

Never place keys in public examples, logs, or unmanaged query strings. Prefer API gateway/authentication mechanisms and appropriate network policies.

### 13.4. Why Not Test via Spring MVC?

A handler using `@HttpTrigger` is an **Azure Functions Java method**. Neither `@RestController`, `spring-boot-starter-web`, nor embedded Tomcat is needed for this example. If you want Spring MVC/WebFlux controllers in Azure, evaluate the specialized `spring-cloud-function-adapter-azure-web` adapter; do not mix both models without an architectural reason.

## 14. Pre-Deployment Testing

Testing can be organized into four layers, each catching a distinct class of defects.

### 14.1. Unit Testing Both Function Beans

No Azure Host required:

~~~java
OrderFunctionApplication application =
        new OrderFunctionApplication();

String value = application.addReferencePrefix()
        .apply(application.normalizeOrder().apply(" dh-701 "));

assertEquals("REF-DH-701", value);
~~~

Add tests for whitespace-only inputs and Unicode casing; import JUnit 5 `assertEquals`/`assertThrows`. This tests **business logic**, not DI or the catalog.

### 14.2. Spring Context + FunctionCatalog

Create `src/test/java/example/azure/OrderFunctionApplicationTest.java`:

~~~java
package example.azure;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderFunctionApplication.class)
class OrderFunctionApplicationTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler handler;

    @Test
    void springCreatesHandlerAndCatalog() {
        assertNotNull(handler);
        assertNotNull(catalog);
    }

    @Test
    void compositionReturnsExpectedOutput() {
        Function<String, String> function =
                catalog.lookup("normalizeOrder|addReferencePrefix");

        assertNotNull(function);
        assertEquals("REF-DH-701",
                function.apply(" dh-701 "));
    }
}
~~~

If the context test fails due to missing `OrderAzureHandler`, check `@Component` and component scanning. If `catalog.lookup(...)` returns null, check `@Bean` names and the definition. If this test PASSES yet the Azure Host fails to discover the function, the issue most likely lies in **Azure annotations/build metadata/packaging**, not Spring DI.

### 14.3. Checking Azure Handler Annotations via Reflection

Additional JUnit example:

~~~java
@Test
void azureHandlerHasExpectedName()
        throws NoSuchMethodException {

    var method = OrderAzureHandler.class.getMethod(
            "normalize",
            HttpRequestMessage.class,
            ExecutionContext.class);

    assertEquals("normalizeAzureOrder",
            method.getAnnotation(FunctionName.class).value());
}
~~~

Import Azure `HttpRequestMessage`, `ExecutionContext`, and `FunctionName`. Reflection tests only inspect source annotations; they do **not** replace Azure plugin packaging.

### 14.4. Host-Level Smoke Tests

| Test | What It Must Prove |
| --- | --- |
| Maven/Gradle package | Azure plugin produces metadata and staging layout. |
| Function discovery | Host lists `normalizeAzureOrder` accurately. |
| Valid HTTP POST | Body `REF-DH-701`, HTTP 200. |
| Blank body | HTTP 400, no unhandled exceptions thrown. |
| Wrong HTTP method | Not processed as a valid POST; exact status determined by host. |
| Wrong main class | Spring context startup logs clearly explain the failure. |
| Wrong Java target | Runtime catches `UnsupportedClassVersionError` or class load failure. |
| Cloud staging key/auth | Requests missing or with wrong keys are rejected per actual policy. |

Run these tests in a production-like environment before wide release.

### 14.5. What Spring Tests Do Not Prove

`@SpringBootTest` does not start the Azure Functions Host, so it does not prove `function.json` was generated, Azure extensions loaded, routes/auth work, cloud app settings are valid, or the Azure runtime classpath contains all dependencies. Never declare "Azure-ready" simply because Java unit tests are green.


## 15. Deploying to Azure: Runtime, Plans, and Deployment Methods

### 15.1. What Must Be Ready Before Deploying?

Cloud deployment is **distinct from local packaging**. Before running it, confirm:

- Authorized Azure subscription and tenant.
- Resource group, Function App name, and region.
- Hosting plan: Flex Consumption, Consumption (legacy), Elastic Premium, Dedicated (App Service), or Container Apps per requirements.
- OS and **Java runtime version** matching your build bytecode.
- Azure Functions runtime 4.x and required app settings.
- Host storage, trigger-specific connections, and identity/RBAC.
- Network restrictions, authentication, observability, retention, and rollback procedures.

Do not treat `resourceGroup`/`region` in the Maven plugin snippet as production-complete configuration. Real projects also need an app service plan, pricing tier, storage account, App Insights, identities, and secret configs—ideally managed with **Infrastructure as Code (IaC)**.

### 15.2. Package Deployment Differs by Hosting Plan

Microsoft provides multiple deployment technologies; no single manual ZIP command fits every Function App type:

| Hosting Plan / Scenario | Deployment Behavior to Know | What to Avoid |
| --- | --- | --- |
| **Flex Consumption** | Code package deployment is platform-managed; supports rolling updates when configured. | **Do not set `WEBSITE_RUN_FROM_PACKAGE=1`** as in traditional ZIP deployment; Flex **has no deployment slots**. |
| **Elastic Premium** | ZIP deployment/run-from-package is supported; deployment slots can be used per docs. | Do not deploy a ZIP with the wrong root or forget slot-specific settings. |
| **Dedicated (App Service)** | ZIP deployment/run-from-package or plan-supported methods. | Do not use the production slot to test unverified changes. |
| **Consumption Windows (legacy)** | ZIP deployment/run-from-package per plan rules. | Do not assume Linux Consumption configurations apply verbatim. |
| **Consumption Linux (legacy)** | Remote build or external package URL mechanisms with specific constraints. | Do not assume `WEBSITE_RUN_FROM_PACKAGE=1` behaves identically to Windows. |
| **Azure Container Apps** | Deploys container images and revisions. | Do not treat a Java Azure Functions ZIP artifact as a container image. |

**Always re-check Microsoft documentation for your exact plan/OS at release time.** Support status and lifecycle policies evolve; plugin commands often choose a deployment flow from configured resources, yet you must understand the target resource and verify the outcome.

### 15.3. Deploying with the Azure Maven Plugin

Once packaged and authenticated with Azure CLI:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

./mvnw clean package
./mvnw azure-functions:deploy
~~~

These are **illustrative commands**, not executed while authoring this lesson, and they can **create/modify resources, replace running code versions, and incur charges**. `<SUBSCRIPTION_ID>` must be replaced with an approved organization subscription.

For Gradle:

~~~bash
az login
./gradlew azureFunctionsPackage
./gradlew azureFunctionsDeploy
~~~

`az login` does not guarantee your session points to the intended subscription or resource group. Verify identity and target configuration before releasing to avoid deploying to the wrong environment.

### 15.4. Using ZIP Deployment

Some hosting plans support deploying a ZIP of the **Azure staging package**. Microsoft documents the corresponding Azure CLI command:

~~~bash
az functionapp deployment source config-zip \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<FUNCTION_APP_NAME>" \
  --src "<AZURE_PACKAGE_ZIP>"
~~~

**Use only on plans supporting ZIP deployment with a properly structured artifact.** Never upload a lone JAR or a ZIP containing a misaligned parent directory. For Flex Consumption, use **Flex package deployment** via plan-supported tooling—do not apply `config-zip` defaults from other plans blindly.

When deploying from an external package URL, URL access, storage credentials/managed identity, and trigger syncing have specific requirements. Never embed long-lived SAS token blob URLs in docs or logs.

### 15.5. Cloud App Settings Differ from Local Settings

Example settings to ensure on Azure:

~~~text
FUNCTIONS_WORKER_RUNTIME=java
FUNCTIONS_EXTENSION_VERSION=~4
MAIN_CLASS=example.azure.OrderFunctionApplication
AzureWebJobsStorage=[connection or identity settings per plan]
~~~

`AzureWebJobsStorage` in the cloud must never remain `UseDevelopmentStorage=true`, as that targets the local emulator. With identity-based connections, setting names and values differ from traditional connection strings and depend on extensions/permissions.

**Never put production secrets into `pom.xml`, `host.json`, or Git repositories.** Use Azure App Settings, Key Vault references/managed identities, and least-privilege access where appropriate. Changing app settings may restart the app; account for this in release workflows.

### 15.6. Immediate Post-Deployment Verification

Do not stop at seeing "deployment succeeded" in logs. In an authorized staging/production environment, verify:

1. The Function App selects the expected Azure runtime and **Java version**.
2. Host startup logs show no class-loading, Spring context, or adapter errors.
3. The Azure Host lists `normalizeAzureOrder` (and any other functions).
4. HTTP POST returns `REF-DH-701` for valid input and 400 for blank bodies.
5. Authorization/authentication/network policies behave as required in the cloud.
6. App Settings and trigger connections work; no secrets appear in logs.
7. Queue/Timer/Event triggers fire and retry/ack per policy.
8. Telemetry, health/alerts, and business metrics appear properly.
9. The deployed artifact retains a version/commit ID sufficient for rollback.

A function visible in the Azure Portal yet unreachable at runtime can still fail due to routes, keys, dependency initialization, storage, or network policies; inspect logs and diagnostics.

## 16. CI/CD, Staging, Rollback, and Production Operations

### 16.1. Recommended Release Pipeline

A pipeline may look like:

~~~mermaid
flowchart LR
    A["Reviewed commit"] --> B["Build / dependency resolution"]
    B --> C["Unit + Spring context tests"]
    C --> D["Azure plugin package"]
    D --> E["Inspect host.json, function.json, Main-Class"]
    E --> F["Store immutable versioned artifact"]
    F --> G["Deploy to staging or release environment"]
    G --> H["Smoke test: discovery / HTTP / trigger"]
    H --> I{"Passes release gate?"}
    I -->|Yes| J["Promote / deploy production"]
    I -->|No| K["Halt release, rollback"]
    J --> L["Monitor / alert / audit"]
~~~

**Build once — deploy to many environments:** whenever possible, build one version-locked artifact and promote that exact artifact from staging -> production, varying environments via App Settings/identities. Avoid rebuilding the same commit with unpinned dependencies and producing different JARs per environment.

### 16.2. Artifact Governance

- Pin Spring Boot/Cloud BOMs, Azure Maven/Gradle plugins, and Java toolchains; review upgrades.
- Retain artifact hashes, commit SHAs, build metadata, and dependency SBOMs per organizational policy.
- Never cache and accidentally deploy a stale `target/azure-functions` directory from another branch.
- Never hand-edit `function.json` after building.
- Scan dependencies and secrets per security standards.
- Verify Java target/OS/runtime compatibility before releasing.

### 16.3. Staging and Deployment Slots

On hosting plans **supporting deployment slots**, deploy to a staging slot, run smoke tests, and **swap** to production to minimize downtime. Settings marked as *slot settings* must be verified so staging never accidentally uses production connections.

**Flex Consumption does not support deployment slots.** On Flex, use the corresponding package deployment/rolling update strategy or separate staging into its own Function App as needed. Never assume every hosting plan has a "swap slot" button.

### 16.4. Deployments Can Interrupt Running Invocations

A deployment may restart or replace the Function App process. When in-flight invocations are interrupted, event-driven triggers can **retry/redeliver** depending on the trigger.

Therefore:

- Design stateless and **idempotent** handlers for event/Queue workloads.
- Distinguish **Azure invocation IDs** from **business event IDs**; retries can issue a new invocation ID.
- For HTTP, define timeout/client retry contracts and correlation IDs.
- For brokers, configure poison queues/dead-letter queues and recovery behavior for interrupted runs.
- Monitor error rates, queue backlogs, latency/cold starts, and resource usage after deploying.

### 16.5. Rollback by Deployment Type

If a release fails:

1. **Halt promotion** if staging smoke tests fail.
2. On slot-enabled plans, use documented swap/revert procedures to restore the previous stable slot.
3. On package/ZIP deployments, **redeploy the prior stable artifact** using the matching tool/plan.
4. Check app settings and schema changes: rolling back code does not automatically roll back databases or event schemas.
5. Re-run smoke tests and confirm Host discovery and business behavior.
6. Reconcile Queue/Event messages, retries, and idempotency so interrupted work is not lost.

**Never use "edit files directly in the portal" as a standard rollback procedure** when deploying read-only packages. Rollback must rely on traceable, versioned artifacts.

### 16.6. Why Is Monitoring Essential?

A single HTTP 200 only proves that specific request/reply succeeded; for ongoing reliability, monitor:

- Startup failures (Spring/Java/adapter).
- Trigger discovery/binding extension errors.
- HTTP 4xx/5xx rates, latency, and cold starts.
- Queue/event backlogs, retries, and dead-letter/poison queues.
- JVM memory, threads/concurrency, and downstream dependency latencies.
- Deployment and rollback timestamps and outcomes.

Never log function keys, HTTP `Authorization` headers, tokens, or full sensitive payloads.

## 17. Troubleshooting: Which Error Belongs to Which Layer?

| Symptom | Layer | Cause / Remediation |
| --- | --- | --- |
| `@SpringBootTest` cannot find handler | **Spring DI** | Missing `@Component`, handler outside package scan, wrong main class. |
| `FunctionCatalog` lookup returns null | **SCF registration** | Wrong `@Bean` name/definition, missing context dependency, or composition mismatch. |
| Azure Host does not list function | **Azure discovery/build** | Missing `@FunctionName`/trigger, non-public method, plugin failed to generate `function.json`. |
| Azure Host lists function but returns 404/405 | **HTTP route** | Wrong `routePrefix`, path, HTTP method, or hostname. |
| Azure HTTP 401/403 in the cloud | **Auth/network** | Function key, auth provider, or access restrictions. |
| `MAIN_CLASS` does not point to Spring class | **Spring startup** | Wrong fully qualified name or wrong configuration class selected. |
| Manifest `Main-Class` points to handler | **Packaging/config** | Change to `OrderFunctionApplication`, rebuild/redeploy. |
| `ClassNotFoundException` for handler/SCF | **Classpath** | Missing dependencies in JAR/staging `lib`, fat JAR layout mismatch. |
| `UnsupportedClassVersionError` | **Java runtime** | Build bytecode is newer than the Azure runtime; align Java target. |
| Plugin package missing `host.json` | **Azure plugin config** | Wrong `hostJson` path or resource copy failure. |
| `function.json` has wrong `entryPoint` | **Build metadata** | Re-package from corrected Java method annotations. |
| Boot fat JAR runs via `java -jar` but fails on Azure | **Artifact format** | Disable/adjust Boot repackage; use Azure plugin staging. |
| Maven build fails on version conflicts | **Dependency management** | Align Boot/Cloud release train and Azure Java library versions. |
| Runs locally, fails to inject beans in cloud | **Environment/runtime** | Differing `MAIN_CLASS`, settings, classpath, or Spring profiles. |
| Local storage works, cloud storage fails | **Connections/identity** | `AzureWebJobsStorage`/permissions; never use emulator setting in the cloud. |
| Missing logs/telemetry | **Observability** | Log levels, monitoring integration, retention, or sampling. |
| Scaled app mixes state across requests | **Concurrency** | Remove invocation state from singletons; use immutable/local values. |
| Queue event processed twice after deploy | **Delivery/retry** | Idempotency, retry/poison policies, and resume logic. |
| ZIP deploy succeeds but app sees no functions | **ZIP root/layout** | `host.json` must sit at package root, not inside a parent directory. |
| Flex deployment fails with legacy ZIP settings | **Hosting plan** | Use Flex package deployment per plan; do not set `WEBSITE_RUN_FROM_PACKAGE=1`. |

### 17.1. Effective Investigation Sequence

~~~text
1. Source: are @SpringBootApplication and @FunctionName correct?
2. Compile: are Java target, imports, and dependencies valid?
3. Azure package: are host.json, function.json, JAR, and lib complete?
4. Main class: does MAIN_CLASS/manifest point to the right Spring config?
5. Runtime: does the Azure Host discover the right function/trigger?
6. Spring: do DI and FunctionCatalog initialize properly?
7. Business: do handler responses and errors follow the schema?
8. Cloud: auth, storage, identity, Java runtime, hosting plan?
9. Operation: metrics, retries, scaling, CI/CD, and rollback?
~~~

**Never fix a Spring DI issue by editing an HTTP route; never fix an Azure discovery failure by renaming a function bean.** Identify the exact layer before acting.

## 18. Practice Exercises and Self-Assessment

### 18.1. Progressive Exercises

1. **Root package configuration:** move `OrderAzureHandler` outside the scanned package; run the Spring context test, then fix either the package structure or `@ComponentScan`.
2. **Change main class:** set an incorrect `MAIN_CLASS`, observe the Spring startup failure, then fix it.
3. **Manifest:** inspect `META-INF/MANIFEST.MF` inside the JAR; distinguish `Main-Class` from `function.json`'s `entryPoint`.
4. **Fat JAR:** toggle Boot repackaging on/off in a test branch; compare the resulting artifact and Azure staging layout.
5. **Function metadata:** rename `@FunctionName("normalizeAzureOrder")`, re-package, and inspect the new directory/`function.json`. Confirm bean names and catalog definitions stay unchanged.
6. **Add another Azure Function:** add a separate Queue Trigger calling `FunctionCatalog.lookup("normalizeOrder")`; note the package gains new function metadata while reusing the Spring functional bean.
7. **Host settings:** add a documented extension bundle and verify the binding loads properly instead of blindly copying config.
8. **Runtime mismatch:** compile classes for a higher Java target than a test runtime (in an isolated test environment) to analyze the class version error; never do this in production.
9. **Smoke tests:** send valid and blank POSTs and verify HTTP 200/400 and function keys on cloud staging.
10. **Artifact release:** design a pipeline storing artifact version/hash, deploying to staging, verifying function discovery, promoting, and rolling back.
11. **Hosting plans:** compare Flex Consumption vs. Premium on ZIP/package deployment and deployment slots; explain why the same `WEBSITE_RUN_FROM_PACKAGE` setting does not apply.
12. **Secrets:** migrate a storage connection from the local emulator to a managed identity in an authorized test environment; verify extension permissions and avoid committing sensitive settings.

### 18.2. Self-Assessment Questions

- How do the roles of `@SpringBootApplication` and `@FunctionName` differ?
- Why do two `@Bean Function` beans with one `@FunctionName` produce only one Azure function metadata folder?
- When does the adapter use `MAIN_CLASS`, and why specify it explicitly in multi-entrypoint apps?
- What is the difference between `Main-Class` in the JAR and `entryPoint` in `function.json`?
- Why can `spring-boot:repackage` prevent the Azure Java Worker from loading your code?
- What does the Azure Maven/Gradle plugin do beyond compiling Java?
- Why must a deployment ZIP place `host.json` at the root after extraction?
- Why should `local.settings.json` never be committed and why doesn't it automatically become Azure App Settings?
- Why must the Java compile target and Azure Java runtime be compatible?
- What does a passing `@SpringBootTest` prove, and what does it **not** prove?
- Why can't Flex Consumption directly reuse Premium's deployment slots / ZIP run-from-package process?
- Which artifacts and metadata must be retained to perform a reproducible rollback?

## 19. Official References

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, `@Component`, `FunctionCatalog`, Maven/Gradle plugins, Spring Boot packaging, main class, `host.json`, and build/run/deploy.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, composition, wrappers, and type conversion.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): Java project layout, `@FunctionName`, `function.json`, runtime/JDK support, and deployment.
- [Microsoft Learn — Java Azure Functions Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): Maven archetype, packaging, local run, and deployment.
- [Microsoft Learn — Run Azure Functions Locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): Core Tools, `local.settings.json`, storage, and deploying settings.
- [Microsoft Learn — Deployment Technologies](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies): publishing methods per hosting plan, deployment slots, and Flex package deployment.
- [Microsoft Learn — Package-based Deployment](https://learn.microsoft.com/en-us/azure/azure-functions/deployment-zip-push): ZIP root layout, run-from-package settings, Flex, and hosting plans.
- [Microsoft Learn — Azure Functions Hosting Options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale): hosting plans, scaling, and associated limits.
- [Microsoft Learn — Azure Functions Deployment Slots](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-slots): managing staging/production slots on supported plans.
- [Spring Cloud Function Samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): sample HTTP Trigger Maven/Gradle, Blob, Timer, and Azure Web Adapter projects.

**Conclusion:** To deploy Spring Cloud Function to Azure, configure the **Spring main class** properly (via `@SpringBootApplication`, `Main-Class`/`Start-Class`, or `MAIN_CLASS`), declare **Azure handler methods** with `@FunctionName` and trigger annotations, and use the **Azure Maven/Gradle plugin** to generate `function.json` and a compliant package rather than uploading a Boot fat JAR directly to the host. Once Java runtime, `host.json`, secrets/app settings, and hosting plan are aligned, inspect the artifact, run the Azure Host locally, deploy through staging/CI, and prepare rollbacks. Clearly separating Spring DI/`FunctionCatalog` from Azure discovery and deployment enables the same `Supplier`, `Function`, and `Consumer` logic to be reused safely across HTTP, event streams, or other serverless platforms.
