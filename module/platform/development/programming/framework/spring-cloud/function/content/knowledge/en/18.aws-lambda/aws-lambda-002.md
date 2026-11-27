# Packaging a JAR for Lambda and Specifying the Application Class

In **SPRING_CLOUD_FUNCTION**, you can write business logic using **Supplier<T>**, **Function<T, R>**, or **Consumer<T>** without depending directly on HTTP, a message broker, or AWS Lambda. However, to run those beans on **AWS Lambda**, the system needs a properly structured Java artifact: Lambda must be able to load the **handler**, the adapter must find the **Spring Boot application class**, and **FunctionCatalog** must look up the right function name.

This lesson belongs to the **AWS Lambda** chapter and focuses on two tasks: **packaging a JAR with all required classes and metadata** and **specifying the main class so Spring Cloud Function can initialize the context**. We use the Java Lambda JAR model with **spring-cloud-function-adapter-aws**; container image or custom runtime deployment paths have different packaging rules.

## 1. Three Identifiers You Must Distinguish

A Spring Cloud Function application running on Lambda can use three completely different names:

| Name | Example | Role |
| --- | --- | --- |
| **AWS Lambda handler** | **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** | Entry point invoked by the Lambda runtime |
| **Spring Boot application class** | **example.lambda.QuoteLambdaApplication** | Class used by the adapter to initialize the Spring ApplicationContext |
| **Function bean name** | **calculateQuote** | Logic name looked up by FunctionCatalog |

~~~mermaid
flowchart LR
    A["AWS Lambda invocation"] --> B["FunctionInvoker"]
    B --> C["QuoteLambdaApplication"]
    C --> D["Spring ApplicationContext"]
    D --> E["FunctionCatalog"]
    E --> F["calculateQuote bean"]
    F --> B
    B --> G["Lambda response"]
~~~

- **Handler** is the class/method provided by the AWS adapter; it must be present on the runtime classpath.
- **Application class** is typically annotated with **@SpringBootApplication**; the adapter uses it to create the context.
- **Function bean** is the Java object implementing **Function**, **Supplier**, or **Consumer**; the bean name can be selected using the **spring.cloud.function.definition** property.

Do not use **calculateQuote** as the Lambda handler name. Also do not point the handler to **QuoteLambdaApplication::main**, because **main(String[] args)** is not the AWS invocation handler signature in this adapter model.

## 2. Why Can a JAR That Runs with java -jar Still Fail on Lambda?

A **Spring Boot executable JAR** typically has the layout:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/example/lambda/QuoteLambdaApplication.class
BOOT-INF/lib/spring-cloud-function-adapter-aws-....jar
BOOT-INF/lib/spring-context-....jar
org/springframework/boot/loader/...
~~~

When running **java -jar**, the Spring Boot launcher understands the **BOOT-INF** layout and loads nested dependency JARs. However, in the **Java JAR on AWS Lambda** deployment model, the runtime tries to load the handler class via the classpath using Lambda's mechanism; it does not operate like the Boot launcher by default.

Therefore, **Spring Cloud Function AWS adapter** samples typically use a **shaded JAR (uber JAR)** for JAR deployments: application classes, the adapter, and dependencies appear in a layout that the Java classloader can load directly.

~~~mermaid
flowchart TB
    A["Java source + Maven/Gradle dependencies"] --> B{"Packaging type"}
    B --> C["Boot executable JAR"]
    B --> D["Shaded JAR"]
    C --> E["BOOT-INF/classes + nested BOOT-INF/lib"]
    D --> F["Classes/resources on Java classpath"]
    E --> G["Typically run with java -jar"]
    F --> H["Used for Lambda Java handler"]
~~~

**Build success is not deployment success.** A JAR may contain all business code yet not place the **FunctionInvoker** class where the Lambda classloader expects it, or contain the classes while losing Spring metadata during shading.

If deploying via a **Lambda container image**, a dedicated image/entrypoint setup can replace the shaded JAR approach here. Do not apply a single packaging approach to every type of Lambda deployment.

## 3. Sample Project Structure

Suppose a Maven project has the structure:

~~~text
quote-lambda/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/example/lambda/
│   │   │   └── QuoteLambdaApplication.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/java/example/lambda/
│       └── QuoteLambdaApplicationTest.java
└── target/
    ├── quote-lambda-1.0.0.jar
    └── quote-lambda-1.0.0-aws.jar
~~~

The filenames in **target** are only illustrative post-build examples. The **-aws.jar** suffix comes from the classifier configured in Maven Shade Plugin, not a mandatory name enforced by Spring Cloud Function.

Keep these concerns separate:

1. **Source code** defines the Spring Boot application and functional beans.
2. **Build configuration** determines dependencies and JAR layout.
3. **Runtime configuration** on AWS determines the handler, main class, function definition, Java runtime, and event source.

## 4. Example Spring Boot Application Class

File **src/main/java/example/lambda/QuoteLambdaApplication.java**:

~~~java
package example.lambda;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteLambdaApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteLambdaApplication.class, args);
    }

    public record QuoteRequest(
        String orderId,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record QuoteResponse(
        String orderId,
        BigDecimal subtotal
    ) {}

    @Bean("calculateQuote")
    Function<QuoteRequest, QuoteResponse> calculateQuote() {
        return request -> {
            if (request == null
                    || request.orderId() == null
                    || request.orderId().isBlank()
                    || request.quantity() <= 0
                    || request.unitPrice() == null
                    || request.unitPrice().signum() < 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            BigDecimal subtotal = request.unitPrice().multiply(
                BigDecimal.valueOf(request.quantity()));

            return new QuoteResponse(request.orderId(), subtotal);
        };
    }
}
~~~

The **calculateQuote** function does not import Lambda APIs, the AWS SDK, or Spring HTTP requests. It keeps the **QuoteRequest → QuoteResponse** contract, so it can be called directly in unit tests or through FunctionCatalog.

Example input for **direct Lambda invocation**:

~~~json
{
  "orderId": "ORD-101",
  "quantity": 2,
  "unitPrice": 85000
}
~~~

Example output:

~~~json
{
  "orderId": "ORD-101",
  "subtotal": 170000
}
~~~

**Business note:** unit price is passed in to illustrate data types. A real sales system should verify prices from a trusted source and define currency and rounding rules.

## 5. How Does the Adapter Find the Spring Application Class?

To run the code above, **FunctionInvoker** must locate the class that initializes the Spring context. There are two key mechanisms to understand:

- **Start-Class** in **META-INF/MANIFEST.MF** provided by the packaging/Boot tool in certain build setups.
- **MAIN_CLASS** explicitly configured in the execution environment, pointing to the fully qualified class name of the application.

Example manifest of a Spring Boot executable JAR:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: example.lambda.QuoteLambdaApplication
~~~

**Main-Class** in an executable JAR may be the Boot launcher class. That is not synonymous with the **application class**. **Start-Class** is what describes the class to run inside Boot; launcher class names vary across Boot generations.

Example AWS Lambda environment configuration:

~~~text
MAIN_CLASS=example.lambda.QuoteLambdaApplication
~~~

This value is the **actual class** in Java code, not the **@Bean** name, the Lambda function name, a Java filename without its package, or the handler name.

~~~text
CORRECT: MAIN_CLASS=example.lambda.QuoteLambdaApplication

WRONG:   MAIN_CLASS=calculateQuote
WRONG:   MAIN_CLASS=FunctionInvoker
WRONG:   MAIN_CLASS=QuoteLambdaApplication::main
~~~

If both the manifest and environment specify the application class, keep their values consistent. How the adapter prioritizes or discovers metadata sources must be checked against the **spring-cloud-function-adapter-aws version** you are using, rather than assuming a single absolute rule for all releases.

### How to Check Whether the Class Is in the JAR

The class above corresponds to the path:

~~~text
example/lambda/QuoteLambdaApplication.class
~~~

Therefore, an artifact inspection command is:

~~~bash
jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'example/lambda/QuoteLambdaApplication.class'
~~~

If this class is missing from the actual artifact, setting **MAIN_CLASS** correctly will still not resolve a **ClassNotFoundException**.

## 6. Package Location and Component Scanning

When Spring initializes **QuoteLambdaApplication**, **@SpringBootApplication** normally scans components under the package containing the application class.

For example:

~~~text
example.lambda.QuoteLambdaApplication
example.lambda.config.QuoteConfiguration
example.lambda.service.PriceService
~~~

In the layout above, configuration/service classes in subpackages can be discovered by Spring via normal scanning.

Conversely, if a functional bean lives in **com.other.functions** while the application is in **example.lambda**, Spring will not automatically scan every package on the classpath. You need **@Import**, explicit scan configuration, or to register the bean in the right place.

Example of an additional configuration class:

~~~java
package example.lambda.config;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TextFunctions {

    @Bean("normalizeText")
    Function<String, String> normalizeText() {
        return value -> value.trim()
            .toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

If **QuoteLambdaApplication** is in **example.lambda**, the **TextFunctions** class in the subpackage can be discovered. Do not change **MAIN_CLASS** to **TextFunctions** because that is a configuration class, not the application entry point.

## 7. Which Dependencies Are Needed for a Lambda JAR?

Maven needs **spring-cloud-function-adapter-aws**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-aws</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Boot and Spring Cloud Function versions must be managed together using **parent/BOM or dependencyManagement**. Example Spring Cloud BOM section:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The **spring-cloud.version** property must be declared with a real release train compatible with your project's Boot version. This is a **POM snippet**, not a complete runnable pom.xml file.

Distinguish two categories:

| Category | Example | Purpose |
| --- | --- | --- |
| **Runtime dependency** | **spring-cloud-function-adapter-aws** | Provides the handler and integrates FunctionCatalog on Lambda |
| **Build plugin** | **maven-shade-plugin** | Builds a shaded JAR containing classes and dependencies |
| **Core/application dependency** | **spring-boot-starter** | Creates the application context |
| **Optional dependency** | JDBC, AWS SDK, Stream binder | Included only when business logic actually uses them |

Do not place **spring-cloud-function-adapter-aws** under Maven **plugins**. Likewise, do not add Spring MVC or a Kafka binder just because Lambda is a serverless environment.

## 8. Maven Shade Plugin: Creating the Deployment Artifact

The goal of **Maven Shade Plugin** is to package application classes, dependencies, and resources into an artifact that the AWS Lambda Java runtime can load.

An illustrative configuration snippet:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-shade-plugin</artifactId>
            <version>3.6.0</version>
            <executions>
                <execution>
                    <id>lambda-jar</id>
                    <phase>package</phase>
                    <goals>
                        <goal>shade</goal>
                    </goals>
                    <configuration>
                        <createDependencyReducedPom>false</createDependencyReducedPom>
                        <shadedArtifactAttached>true</shadedArtifactAttached>
                        <shadedClassifierName>aws</shadedClassifierName>
                        <transformers>
                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
                            </transformer>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                <resource>META-INF/spring.handlers</resource>
                            </transformer>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                <resource>META-INF/spring.schemas</resource>
                            </transformer>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                <manifestEntries>
                                    <Start-Class>example.lambda.QuoteLambdaApplication</Start-Class>
                                </manifestEntries>
                            </transformer>
                        </transformers>
                        <filters>
                            <filter>
                                <artifact>*:*</artifact>
                                <excludes>
                                    <exclude>META-INF/*.SF</exclude>
                                    <exclude>META-INF/*.DSA</exclude>
                                    <exclude>META-INF/*.RSA</exclude>
                                </excludes>
                            </filter>
                        </filters>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

**This is not a complete deployment POM for all Spring versions.** You must add proper merging for **META-INF/spring.factories** (properties format, potentially with multiple values under the same key) and other Spring resources used by the dependency tree. In the Spring Cloud Function documentation, specialized transformers are used to avoid losing metadata during shading. Do not simply use AppendingTransformer for every properties-style resource.

You also need to control **spring-boot-maven-plugin repackage** if the project declares that plugin: Shade must receive the right input artifact and not accidentally wrap an unsuitable Boot nested JAR. It is best to use the official Lambda packaging sample from the **same Spring Cloud Function release** and test the final artifact.

### Why Set the aws Classifier?

With artifactId **quote-lambda** and version **1.0.0**, the configuration above can generate:

~~~text
target/quote-lambda-1.0.0.jar
target/quote-lambda-1.0.0-aws.jar
~~~

**-aws.jar** helps distinguish the shaded artifact from other JARs. However, the actual name depends on your project build; always verify the real file path before uploading.

## 9. How Important Is Spring Metadata?

Common resources in the Spring ecosystem:

~~~text
META-INF/MANIFEST.MF
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring.handlers
META-INF/spring.schemas
META-INF/services/...
~~~

Not every project needs all of them. Which resources actually appear depends on Spring Boot, Spring Cloud, and accompanying libraries.

| Resource | Content | What to Preserve |
| --- | --- | --- |
| **META-INF/services/** | Service provider lists | Merge lists |
| **AutoConfiguration.imports** | Auto-configuration class names | Keep all required entries |
| **spring.factories** | Properties format declared by multiple modules | Merge keys and values properly |
| **spring.handlers/schemas** | XML configuration metadata | Keep mappings from required dependencies |
| **MANIFEST.MF** | Artifact metadata such as **Start-Class** | Write consistent main class info |

A very misleading failure mode: the JAR has **FunctionInvoker.class** and **QuoteLambdaApplication.class**, yet **the Spring context still fails to start** because shading kept only one **spring.factories** file instead of merging entries from multiple libraries.

Therefore, **checking .class files is only a necessary condition**. You must preserve resource metadata, test context startup, and if possible perform a Lambda invocation with the exact deployed artifact.

## 10. Inspecting JAR Contents After Building

The following commands are for a fully configured Maven project:

~~~bash
mvn clean package
ls -lh target/*.jar

jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'org/springframework/cloud/function/adapter/aws/FunctionInvoker.class'

jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'example/lambda/QuoteLambdaApplication.class'

jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'META-INF/spring/'
~~~

The path **target/quote-lambda-1.0.0-aws.jar** is illustrative. In PowerShell, replace grep with:

~~~powershell
jar tf target/quote-lambda-1.0.0-aws.jar |
  Select-String 'FunctionInvoker.class|QuoteLambdaApplication.class'
~~~

To view the manifest on a system with unzip:

~~~bash
unzip -p target/quote-lambda-1.0.0-aws.jar META-INF/MANIFEST.MF
~~~

Look for:

~~~text
Start-Class: example.lambda.QuoteLambdaApplication
~~~

If the shaded JAR lacks **Start-Class**, you can explicitly set **MAIN_CLASS** per the adapter's supported mechanism. However, if the JAR is completely missing the main class, setting the environment variable alone is not enough.

### Checking Dependency Versions

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

If you see unexpected multiple versions, cross-check the BOM and plugins against the dependency tree. Do not randomly delete dependencies just to silence a runtime exception.

## 11. Gradle: Building a Lambda JAR with Shadow

If the project uses Gradle, the equivalent approach is using the **Shadow Plugin** to build an uber JAR. **Groovy DSL** example showing the main operations:

~~~groovy
// Assumes the Shadow plugin is declared appropriately for the Gradle project.
tasks.named("shadowJar") {
    archiveClassifier.set("aws")

    mergeServiceFiles()
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
    append("META-INF/spring.handlers")
    append("META-INF/spring.schemas")

    manifest {
        attributes(
            "Start-Class": "example.lambda.QuoteLambdaApplication"
        )
    }
}
~~~

**Do not treat the snippet above as a complete build.gradle**. You must include plugins, dependencies, Java toolchain, task wiring, and especially a transformer that merges **spring.factories** in valid properties format. Plugin API syntax can also change across versions.

To avoid conflicts between Spring Boot **bootJar** and Shadow **shadowJar**, explicitly determine **which artifact is handed to AWS**. For example, two different files can be generated:

~~~text
build/libs/quote-lambda-1.0.0.jar
build/libs/quote-lambda-1.0.0-aws.jar
~~~

Inspect the handler class and metadata inside the final file rather than relying solely on the filename suffix.

## 12. Configuring the Lambda Handler and Main Class

Once you have the shaded JAR, configure Lambda accordingly:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

Environment:
  MAIN_CLASS=example.lambda.QuoteLambdaApplication
  spring_cloud_function_definition=calculateQuote
~~~

Depending on the adapter version or deployment tool, some handler configurations may use **org.springframework.cloud.function.adapter.aws.FunctionInvoker** (the class name) instead of the **::handleRequest** syntax. Check the exact handler format supported by your adapter/runtime version; do not put the business bean name in this field.

The **spring_cloud_function_definition** variable selects the bean in **FunctionCatalog**. When there are multiple Function beans, this is the explicit way to prevent the application from picking the wrong function.

### AWS SAM Example

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  QuoteFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java17
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/quote-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.QuoteLambdaApplication
          spring_cloud_function_definition: calculateQuote
~~~

**CodeUri must point to the actual built JAR**. Java 17 Runtime is only an illustrative choice; verify AWS-supported Java versions and configure your compiler/release accordingly. Memory and timeout are also demo parameters, not fixed optimal settings.

With the AWS Console, AWS CLI, Terraform, or CloudFormation, the three roles remain the same: the adapter's handler, Spring's main class, and the selected bean in FunctionCatalog.

## 13. Testing Each Layer of Responsibility

### 13.1. Business Logic Unit Tests Without AWS

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class QuoteLambdaApplicationTest {

    private final QuoteLambdaApplication app =
        new QuoteLambdaApplication();

    @Test
    void calculatesSubtotal() {
        var result = app.calculateQuote().apply(
            new QuoteLambdaApplication.QuoteRequest(
                "ORD-101", 2, new BigDecimal("85000")
            )
        );

        assertEquals(
            new BigDecimal("170000"), result.subtotal());
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> app.calculateQuote().apply(
                new QuoteLambdaApplication.QuoteRequest(
                    "ORD-101", 0, new BigDecimal("85000")
                )
            ));
    }
}
~~~

This unit test does not verify FunctionInvoker, JAR layout, or main-class discovery.

### 13.2. FunctionCatalog Integration Test

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = QuoteLambdaApplication.class)
class QuoteCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsBeanByName() {
        Function<QuoteLambdaApplication.QuoteRequest,
                QuoteLambdaApplication.QuoteResponse> fn =
            catalog.lookup("calculateQuote");

        assertNotNull(fn);

        var quote = fn.apply(
            new QuoteLambdaApplication.QuoteRequest(
                "ORD-101", 2, new BigDecimal("85000")
            )
        );

        assertEquals(
            new BigDecimal("170000"), quote.subtotal());
    }
}
~~~

This test proves the Spring context can start and the catalog can look up the bean. However, you still need to inspect **the final shaded JAR** and invoke Lambda to catch handler/classpath or runtime conversion issues.

### 13.3. Direct Invocation After Deployment

Example direct event:

~~~json
{
  "orderId": "ORD-101",
  "quantity": 2,
  "unitPrice": 85000
}
~~~

AWS CLI command in a shell supporting single-quote syntax:

~~~bash
aws lambda invoke \
  --function-name quote-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '{"orderId":"ORD-101","quantity":2,"unitPrice":85000}' \
  response.json

cat response.json
~~~

**quote-lambda** is an example AWS function name, not the **calculateQuote** bean name. Inspect returned metadata, response contents, and CloudWatch logs to detect function errors even when the CLI command sends the request successfully.

**Direct invocation is not equivalent to API Gateway/SQS/S3 triggers**: each source has its own event envelope, batch semantics, or error mapping. If Lambda receives an event with a **body** or **Records** field, you must choose the appropriate input type/converter; changing **MAIN_CLASS** will not solve a schema issue.

## 14. Diagnostic Table for Packaging and Application Class Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Adapter not included or wrong JAR uploaded | **jar tf**, dependency tree, CodeUri |
| **ClassNotFoundException: QuoteLambdaApplication** | Wrong class path, renamed package, or class missing from JAR | **jar tf** with the fully qualified class name |
| Cannot find main class | Missing **Start-Class** and **MAIN_CLASS** | Manifest, env var, adapter version |
| Spring context cannot find bean | Wrong package scan/definition | **@Bean**, FunctionCatalog test, config |
| Build passes but Lambda fails auto-configuration | Incomplete Spring metadata merging | **spring.factories**, **AutoConfiguration.imports**, service resources |
| **java -jar** runs but Lambda fails to load handler | Boot executable JAR has wrong layout | Check **BOOT-INF** and shaded JAR |
| **NoSuchMethodError** or linkage error | Boot/Cloud/adapter version mismatch | BOM and dependency tree |
| **UnsupportedClassVersionError** | Bytecode compiled higher than AWS Java runtime | Compiler release, Runtime |
| Cannot deserialize QuoteRequest | JSON/schema/generic type mismatch | Function signature, real input event |
| Output differs from direct invoke | Different API Gateway/SQS event envelope | Adapt according to trigger |
| **MAIN_CLASS** set correctly but still fails | Main class missing from JAR or metadata conflict | Compare package/class, artifact, manifest |
| Cold start too slow | Large context, too many dependencies, or startup I/O | Measure duration, audit dependencies, startup logs |

An effective diagnostic sequence is checking in order: **(1) can the handler be loaded**, **(2) can the main class/context initialize**, **(3) can the catalog find the bean**, **(4) does the event convert properly**. Avoid changing multiple settings at random simultaneously.

## 15. Java Runtime, Cold Starts, and State

The build must target a Java version compatible with the Lambda runtime. Maven example:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Gradle toolchain example:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Verify that Spring Boot, Spring Cloud Function, and transitive dependencies are all compatible with the Java runtime.

When Lambda initializes a new execution environment, loading the JAR, creating the application context, and initializing dependencies can increase **cold-start latency**. A warm instance can reuse singleton Function beans; however, instances do not share memory, and Lambda may create a new environment at any time.

Therefore:

- Do not use singleton fields to store durable business state.
- Do not rely on the same Lambda instance always processing every event.
- Measure real cold starts before optimizing dependencies and auto-configuration.
- Do not strip Spring metadata or required libraries merely to reduce JAR size.
- For Consumers with side effects, handle retries and idempotency at the data/infrastructure level rather than relying on the classloader or singletons.

## 16. Pre-Deployment Checklist

| Check | Passing Sign |
| --- | --- |
| **Source** | Has **@SpringBootApplication** with clear package/class |
| **Bean** | Has **Function/Consumer/Supplier** with exact type and name |
| **Adapter** | **spring-cloud-function-adapter-aws** dependency resolves |
| **Compatibility** | Boot/Cloud/Java are compatible and versions are pinned |
| **Artifact** | Real **shaded JAR** exists; Boot JAR not uploaded by mistake |
| **Handler class** | **FunctionInvoker.class** is inside the deployment JAR |
| **Application class** | **QuoteLambdaApplication.class** is inside the deployment JAR |
| **Metadata** | Spring resources are merged properly and context initializes |
| **Discovery** | **Start-Class** or **MAIN_CLASS** is valid |
| **Function selection** | **spring_cloud_function_definition=calculateQuote** |
| **AWS configuration** | Handler, CodeUri, Runtime, memory, timeout, and IAM are correct |
| **Invocation** | JSON converts to DTO, output is right, logs show no errors |

If an item has not been verified, do not conclude the artifact is ready simply because Maven/Gradle returned exit code 0.

## 17. Applied Exercises

**Exercise 1 — Three names.** An application has **@SpringBootApplication com.shop.QuoteApplication** and bean **@Bean("quoteOrder")**. Write the values for the Lambda handler, **MAIN_CLASS**, and **spring_cloud_function_definition**. Describe the error if the bean name is used as the handler.

**Exercise 2 — Different JARs.** A build generates **service.jar** containing **BOOT-INF/lib** and **service-aws.jar** with classes on the classpath. Explain which artifact fits the Java Lambda JAR deployment path and which manifest entries should be checked.

**Exercise 3 — Missing Start-Class.** A shaded JAR contains **com.shop.QuoteApplication.class** but lacks **Start-Class**. Propose the corresponding environment variable and how to verify that Lambda initializes the Spring context.

**Exercise 4 — Metadata.** A shade task keeps only one **spring.factories** from multiple dependencies. Describe the likely symptoms and the difference between merging a properties file versus appending a class-list file.

**Exercise 5 — Package refactoring.** Refactor **example.lambda.QuoteLambdaApplication** to **example.serverless.QuoteLambdaApplication**. List every place that must be updated: manifest, **MAIN_CLASS**, source package, scan, SAM, and tests.

**Exercise 6 — Multiple Functions.** Register **normalizeSku** alongside **calculateQuote**. Describe how to use the same shaded JAR to deploy two Lambdas with different definition configurations.

**Exercise 7 — ClassNotFound error.** Unit tests and **@SpringBootTest** pass, yet Lambda reports **FunctionInvoker** cannot be found. Outline an investigation sequence covering dependencies, artifact, handler, and CodeUri in order.

**Exercise 8 — Event envelope.** Direct invocation with **QuoteRequest** succeeds, but an API Gateway trigger sends an object containing **body**. Propose a solution that maps the event to the DTO rather than modifying the main class or handler.

### Key Takeaways

- **AWS Lambda handler**, **Spring Boot main class**, and **Function bean** are three distinct identifiers.
- With **Java JAR + spring-cloud-function-adapter-aws**, you need a **shaded JAR** containing the handler, application classes, dependencies, and proper Spring metadata; an executable Boot JAR cannot be used directly by default.
- **Start-Class** in the manifest or **MAIN_CLASS** per the adapter mechanism identifies the application class; **spring_cloud_function_definition** selects the business bean.
- Maven Shade/Gradle Shadow must merge **META-INF** properly. Checking `.class` files alone is insufficient.
- Unit tests verify logic and Spring integration tests verify context/catalog; **artifact inspection and Lambda invocation** confirm the actual deployment path.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): handler, main class, shaded JAR, and integration.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): FunctionCatalog, model, and composition.
- [AWS Lambda — Java deployment packages](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): artifacts and how to deploy Java.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): how the runtime invokes the handler.
