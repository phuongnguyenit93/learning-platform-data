# The spring-cloud-function-adapter-aws Dependency

**spring-cloud-function-adapter-aws** is the adapter library that enables a **Spring Cloud Function** application to run on **AWS Lambda** without introducing Lambda APIs into each business function. Once the application declares **Supplier<T>**, **Function<T, R>**, or **Consumer<T>** beans, the adapter provides the **FunctionInvoker** entry point to receive Lambda invocations, initialize the Spring context, look up the function in **FunctionCatalog**, convert data, and return results according to the runtime capabilities.

This lesson belongs to the **AWS Lambda** chapter and focuses on **declaring the right dependency**, managing Spring Boot/Spring Cloud versions, distinguishing the adapter from web libraries and the AWS SDK, understanding the role of the handler, packaging a Lambda-compatible JAR, verifying after the build, and diagnosing errors. The implementation steps are illustrated on Java 17+; you must choose Java and Spring versions compatible with your actual runtime.

## 1. Why Do We Need an AWS Lambda Adapter?

In a standard Java application, a caller can obtain a **Function** bean and call **apply(input)**. In AWS Lambda, the platform does not search for Spring beans. It invokes the **handler** configured in Lambda settings and passes the event to that handler.

Without an adapter, each application would need to handle steps such as initializing the Spring application context, looking up beans, deserializing the event, invoking the function, and serializing the result on its own.

~~~mermaid
flowchart LR
    A["AWS Lambda invocation"] --> B["FunctionInvoker"]
    B --> C["Spring ApplicationContext"]
    C --> D["FunctionCatalog"]
    D --> E["Function<T, R>"]
    E --> F["Result R"]
    F --> B
    B --> G["Lambda response"]
~~~

**spring-cloud-function-adapter-aws** provides the integration mechanism for the flow above. The business logic can remain independent:

~~~java
Function<String, String> normalize =
    text -> text.trim().toUpperCase(java.util.Locale.ROOT);
~~~

Whether using HTTP, Spring Cloud Stream, or AWS Lambda, the function still transforms **String → String**. The difference lies in **how events are received, data conversion, startup configuration, and how results are returned**.

### Separating the Two Layers of Responsibility

| Component | Role |
| --- | --- |
| **Spring Cloud Function Core / Context** | Discovers functional beans, provides **FunctionCatalog**, composition, conversion, and related mechanisms |
| **spring-cloud-function-adapter-aws** | Integrates Spring Cloud Function with the AWS Lambda handler/invocation model |
| **spring-cloud-function-web** | HTTP adapter for Spring Cloud Function applications in web environments |
| **Spring Cloud Stream + binder** | Integrates message streams with Kafka, RabbitMQ, or corresponding systems |
| **AWS SDK / aws-lambda-java-events** | Calls AWS services or uses specific AWS event classes when needed by the application |

**Installing the adapter does not enable an HTTP server**, nor does it automatically add a Kafka/SQS event source mapping. The Lambda handler and triggers are configured at the AWS configuration layer.

## 2. Exact Maven Coordinates of the Adapter

The dependency to add to the project:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

The full coordinate has the form:

~~~text
org.springframework.cloud:spring-cloud-function-adapter-aws:<version>
~~~

This is an **application dependency**, not a Maven build plugin. Do not write:

~~~xml
<!-- Incorrect: the adapter is not a packaging plugin -->
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</plugin>
~~~

The artifact name must be exact. **spring-cloud-starter-function-web** serves the HTTP path, while **spring-cloud-function-adapter-aws** serves the Lambda handler; the two dependencies are not interchangeable.

### Which Dependencies Are Required and Which Are Optional?

For a Spring Boot function running on Lambda under the functional model, you typically need:

- **Spring Boot** to create the application context and manage beans.
- **spring-cloud-function-adapter-aws** to connect the Lambda runtime with Spring Cloud Function.
- **Spring Cloud Function context/core** brought in through the corresponding dependency tree; you may explicitly declare **spring-cloud-function-context** if you want to make the intent clear and your source code imports **FunctionCatalog**.
- **Business-logic libraries** such as JDBC, JSON, an HTTP client, or the AWS SDK only when your code actually uses them.
- **A deployable JAR build tool** such as Maven Shade Plugin or Gradle Shadow Plugin at the **build** layer, not as a runtime dependency.

Avoid adding all of Spring Cloud Stream, WebFlux, Spring MVC, or the AWS SDK to a Lambda just because a library name contains the word "cloud". Unnecessary dependencies can enlarge the JAR, increase the number of classes to load, and create an unneeded maintenance surface.

## 3. Managing Versions with a BOM Instead of Guessing Version Numbers

Spring Cloud Function, Spring Boot, and Spring Cloud modules must belong to **compatible** versions. A common mistake is using the latest version of the adapter with a Spring Boot version that is too old, or letting Maven pull in multiple different versions of **spring-cloud-function-context**.

A **BOM (Bill of Materials)** helps manage versions consistently. In a Maven project that already uses the **Spring Boot parent** or an equivalent Boot management mechanism, you can declare the Spring Cloud BOM:

~~~xml
<properties>
    <!-- Specify a release train value compatible with the project's Spring Boot version. -->
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

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

**This is an illustrative configuration snippet**, not a complete **pom.xml**: you must replace **YOUR_COMPATIBLE_RELEASE_TRAIN** with a real version confirmed to be compatible with your Spring Boot version and project parent/plugin setup. Do not copy the placeholder as-is and expect Maven to resolve it successfully.

Points to check:

1. **Spring Boot** provides Boot dependency versions and the startup mechanism.
2. **Spring Cloud BOM** manages compatible modules within the release train.
3. If your project's BOM does not yet manage the desired adapter version, use Spring Cloud Function's dedicated dependency management according to the guide for the chosen version, rather than setting arbitrary versions on individual artifacts.
4. The **Java language level** at compile time must match the selected Lambda runtime.
5. A transitive dependency pulling in a different version may need to be handled with **dependencyManagement** or a well-reasoned exclusion; do not blindly exclude dependencies just to make the build pass.

**There is no single Spring Boot/Spring Cloud version pair that is right for every point in time.** Lock versions in your build and verify them against the corresponding release train documentation instead of mixing the latest independent releases.

## 4. Equivalent Declaration in Gradle

Example **build.gradle** using Gradle Groovy DSL with a BOM:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation "org.springframework.boot:spring-boot-starter"
    implementation "org.springframework.cloud:spring-cloud-function-adapter-aws"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
}

tasks.named("test") {
    useJUnitPlatform()
}
~~~

The **springCloudVersion** variable must be declared in the Gradle project or **gradle.properties**, and the project must configure the Java/Spring Boot plugins along with repositories such as Maven Central. This snippet describes **dependencies and the test task**; it does not yet configure a **Shadow JAR** for deployment.

Use **implementation** instead of the deprecated **compile** configuration in modern Gradle. If the project uses Kotlin DSL, the syntax is slightly different:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    ))
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-function-adapter-aws")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

**Do not run both Maven and Gradle on the same module just to add two declarations.** Choose the build tool your project already uses.

## 5. Application Example: A Function Bean Without Importing AWS APIs

After declaring the dependency, a Spring Boot application can continue using the Spring Cloud Function programming model.

File **GreetingLambdaApplication.java**:

~~~java
package example.lambda;

import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GreetingLambdaApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingLambdaApplication.class, args);
    }

    public record GreetingRequest(String name) {}

    public record GreetingResponse(String message) {}

    @Bean("greet")
    Function<GreetingRequest, GreetingResponse> greet() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException(
                    "name must not be blank");
            }

            String name = request.name().trim();

            return new GreetingResponse("Hello, " + name);
        };
    }
}
~~~

The class above **does not implement RequestHandler**, has no **handleRequest(...)** method, and does not need to read the AWS **Context** object directly. **@Bean("greet")** declares a strongly typed Function; **FunctionInvoker** assumes the role of the Lambda handler.

When the event body maps directly to the **GreetingRequest** type, an illustrative JSON payload is:

~~~json
{
  "name": "Lan"
}
~~~

Expected business result:

~~~json
{
  "message": "Hello, Lan"
}
~~~

The final output returned by AWS also depends on the invocation type and how the adapter serializes it. This example assumes **a direct Lambda invocation with a JSON object** of matching structure; it does **not** assume that every API Gateway or SQS event only has a **name** field.

### What Happens Internally?

~~~mermaid
sequenceDiagram
    participant AWS as AWS Lambda
    participant Invoker as FunctionInvoker
    participant Spring as Spring Context
    participant Cat as FunctionCatalog
    participant Fn as greet Function

    AWS->>Invoker: invoke JSON event
    Invoker->>Spring: initialize / get context
    Spring-->>Invoker: application context
    Invoker->>Cat: lookup("greet")
    Cat-->>Invoker: selected Function
    Invoker->>Fn: apply(GreetingRequest)
    Fn-->>Invoker: GreetingResponse
    Invoker-->>AWS: serialized response
~~~

Spring can reuse the application context within an already-initialized Lambda execution environment. However, a **cold start** may create a new context, and different Lambda instances do not directly share singleton beans in memory.

## 6. FunctionInvoker Is the Handler, Not the Business Bean Name

With the AWS adapter, the entry point recommended by Spring Cloud Function is the class:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

In the **Java Lambda handler** configuration UI, the notation illustrated in the documentation is:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

This is the **handler class/method name of the adapter**. It differs from **greet**, which is the name of the Function bean registered in Spring.

Do not configure the handler as:

~~~text
example.lambda.GreetingLambdaApplication::greet
~~~

The **greet()** method in the application class is a factory method annotated with **@Bean**, not an AWS handler designed to receive an event and runtime context.

| Value | Meaning | Location |
| --- | --- | --- |
| **FunctionInvoker::handleRequest** | Adapter's Lambda entry point | Handler configuration in AWS |
| **greet** | Business Function bean | Spring ApplicationContext / FunctionCatalog |
| **spring.cloud.function.definition** | Name or composition to invoke | Spring configuration |
| **spring_cloud_function_definition** | Corresponding environment variable used in Lambda | Lambda Environment variables |
| **MAIN_CLASS** | Hint for the Spring Boot main class when the adapter cannot find it | Manifest or Lambda configuration |

**You do not need to write a custom AWS handler** in this example. A custom handler is only needed if you have specialized integration requirements not covered by the generic adapter, in which case you are responsible for conforming to Lambda's event contract.

## 7. Selecting a Bean via spring.cloud.function.definition

An application can have multiple functional beans. If no function is specified, the adapter may rely on default routing mechanisms; do not assume "Spring will pick the right one" when there are multiple choices.

For example, declaring an additional bean in the application class:

~~~java
@Bean("uppercase")
Function<String, String> uppercase() {
    return value -> value.toUpperCase(java.util.Locale.ROOT);
}
~~~

Now the application has at least **greet** and **uppercase**. To make each Lambda function select the right bean, set the configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: greet
~~~

When declared via **AWS Lambda environment variables**, the corresponding variable name can be written as:

~~~text
spring_cloud_function_definition=greet
~~~

AWS does not allow dots in environment variable names. Spring Boot supports mapping underscore-delimited variables to the corresponding properties; the Spring Cloud Function AWS Lambda documentation uses **spring_cloud_function_definition** as an example.

A single JAR can be deployed to **two separate Lambda functions**, both pointing to **FunctionInvoker** while using two different environment variables:

~~~text
Lambda "greeting-lambda"
  Handler = FunctionInvoker
  spring_cloud_function_definition = greet

Lambda "uppercase-lambda"
  Handler = FunctionInvoker
  spring_cloud_function_definition = uppercase
~~~

For functions with different resource access permissions, concurrency levels, timeouts, or event sources, deploying them as separate Lambda functions often makes IAM configuration and operations clearer.

**Composition** can also be selected by definition, for example **normalize|validate|persist**, provided each step has compatible types and the integration mechanism supports that invocation path. However, this lesson focuses on the AWS adapter dependency; dynamic routing within the same Lambda function requires considering **RoutingFunction**, message headers, or callbacks according to separate documentation.

## 8. Proper Packaging Is Just as Important as Declaring the Dependency

**Having the adapter in pom.xml does not mean the generated JAR will automatically run on Lambda.** A Spring Boot application is normally packaged as an executable JAR with application classes in **BOOT-INF/classes** and dependencies in **BOOT-INF/lib**. This layout works well for **java -jar**, but it is not necessarily compatible with how the Lambda Java runtime loads handler classes from an uploaded JAR.

According to the Spring Cloud Function AWS guide, for a **Lambda Java JAR** deployment you typically need a **shaded JAR**: an artifact with a suitable classpath containing application classes and required libraries.

~~~text
Maven/Gradle source
  ├── Java classes and resources
  ├── spring-cloud-function-adapter-aws
  ├── Spring context/Boot and business dependencies
  │
  ├── JAR for local execution (depending on configuration)
  └── Shaded JAR for AWS Lambda deployment
~~~

### Differences Between Artifacts

| Artifact | Usage | What to Verify |
| --- | --- | --- |
| **Standard JAR** | Library or input for a later build step | Has classes, but may not include dependencies |
| **Spring Boot executable JAR** | Run **java -jar** | Has nested JAR layout; do not upload directly as a Lambda handler JAR by default |
| **Shaded JAR** | A single JAR structured for Java Lambda | Contains handler, classes, resources, merged metadata, and dependencies |
| **Container image** | Deploy Lambda using an image | Uses a Dockerfile/base image and appropriate handler; differs from JAR deployment |
| **Native image/custom runtime** | Native execution or custom runtime | Has completely different bootstrap/packaging and rules |

Choose **one packaging path that matches your deployment type**. Do not treat a standard Spring Boot JAR as a Lambda artifact simply because both end in **.jar**.

## 9. Maven Shade Plugin: Merging Dependencies and Spring Metadata

Maven Shade Plugin can produce an artifact with the **aws** classifier. A real configuration must stay aligned with your Spring Boot/Spring Cloud version and build lifecycle.

Example **plugin configuration snippet** illustrating the idea:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <!-- Pin an appropriate plugin version in your project's build. -->
    <executions>
        <execution>
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
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**This is an illustrative configuration snippet, not a complete deployment POM.** An application using Spring Boot auto-configuration also needs proper handling for **META-INF/spring.factories** and other metadata resources such as **META-INF/spring.components** or Actuator auto-configuration metadata. The official documentation describes **PropertiesMergingResourceTransformer** alongside **AppendingTransformer**s; transformers provided by Spring Boot also require configuring the corresponding plugin dependency. An incomplete configuration can produce a JAR that builds successfully yet causes Spring Boot to miss auto-configuration when running on Lambda.

Essential notes:

1. **Preserve Spring metadata:** resources under **META-INF/** can appear with the same name across multiple dependencies; do not let Shade arbitrarily overwrite lists that must be merged.
2. **Preserve main class discovery:** Spring Cloud Function can use **Start-Class** in the manifest; if missing, supply **MAIN_CLASS** per the adapter documentation.
3. **Coordinate plugins:** if using both Spring Boot repackage and Maven Shade, the order and input artifact must be right; do not arbitrarily shade a BOOT-INF nested JAR and treat it as a deployable JAR.
4. **Attach a classifier:** configuring **shadedClassifierName=aws** helps distinguish it from artifacts meant for other purposes.
5. **Pin the plugin version:** verify compatibility and pick a specific version so the build does not depend on unexpected tool changes.
6. **Verify the final artifact:** filename, manifest, classes, and metadata must be checked on the exact JAR you plan to upload.

If you do not yet have a standard build pipeline, start from the **official Spring Cloud Function AWS Lambda sample** for your chosen version, then adjust the source/dependencies and inspect the artifact. Avoid piecing together fragmented Maven Shade configurations from different Spring versions.

### Maven Verification Commands

In a properly configured Maven project:

~~~bash
mvn clean package

# Find the generated JARs.
ls -lh target/*.jar

# Inspect an artifact intended for deployment.
jar tf target/your-app-aws.jar | grep 'FunctionInvoker.class'
jar tf target/your-app-aws.jar | grep 'GreetingLambdaApplication.class'
jar tf target/your-app-aws.jar | grep 'AutoConfiguration.imports'
~~~

**your-app-aws.jar** is a sample name; replace it with the **actual file** produced by the build. The grep command fits Unix shells; on Windows, use an equivalent string search tool. Finding the class does not guarantee the application will initialize successfully, but missing the handler class is definitely a sign of broken packaging.

Check **META-INF/MANIFEST.MF**, especially the **Start-Class** attribute or **MAIN_CLASS** configuration if the adapter does not auto-detect the entry point.

## 10. Gradle Shadow JAR and Resources

With Gradle, the equivalent approach is using the **Shadow Plugin** to build a JAR containing dependencies and required resources. The snippet below shows **the core task settings**; DSL names and plugin versions depend on the Shadow version you use:

~~~groovy
tasks.named("shadowJar") {
    archiveClassifier = "aws"

    // Merge service registration files for libraries that support ServiceLoader.
    mergeServiceFiles()

    // Some Spring metadata files must be appended rather than overwritten.
    append("META-INF/spring.handlers")
    append("META-INF/spring.schemas")
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
~~~

You must declare a compatible Shadow plugin in the **plugins** block, and if **spring.factories** is present, its properties must be merged properly; a simple text file append is not always right when files share **the same property key**. The Spring Cloud Function guide includes a **PropertiesFileTransformer** example for this case.

**Do not treat the Shadow task snippet above as a standalone Gradle file ready for deployment.** Use the official reference configuration for your matching plugin version and verify that the **assemble/package** task actually produces the JAR with the expected classifier.

### Why Must We Be Careful with Metadata?

Spring Boot uses resource files to discover auto-configuration, service providers, or other component declarations. When dependencies contain metadata files with identical names, improper shading or merging can drop part of the list of classes to load. As a result:

- The build succeeds, but the application context fails to create beans.
- FunctionCatalog cannot find **greet**.
- A converter or serializer is missing a service provider.
- Errors occur only on Lambda and not when running **java -jar** locally.

Therefore, **packaging is part of the deployment contract**, not just a file-compression step.

## 11. MAIN_CLASS, Manifest, and Starting the Spring Application

When Lambda invokes **FunctionInvoker**, the adapter needs to know the Spring Boot application class to create the context. The Spring Cloud Function documentation notes that the adapter tries to find **Start-Class** in the JAR manifest. If absent, you can specify **MAIN_CLASS** as an environment variable or system property.

Example:

~~~text
MAIN_CLASS=example.lambda.GreetingLambdaApplication
~~~

**MAIN_CLASS** must be the fully qualified class name of the application class, not the Function bean name **greet**.

Identification diagram:

~~~text
Lambda handler
    org.springframework.cloud.function.adapter.aws.FunctionInvoker

Spring Boot main class
    example.lambda.GreetingLambdaApplication

Spring Function bean
    greet
~~~

A configuration may run locally yet fail on Lambda if main-class discovery relied on an executable JAR layout that changed during shading. In particular, when creating the JAR manually rather than using a tested sample, set **MAIN_CLASS** explicitly and inspect startup logs.

## 12. AWS SAM Example: Coordinating Dependencies, JAR, and Handler

Once the right artifact is built, you can use **AWS SAM** to describe the Lambda function. Illustrative **template.yaml** example:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GreetingFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/your-app-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          spring_cloud_function_definition: greet
          MAIN_CLASS: example.lambda.GreetingLambdaApplication
~~~

Explanation:

- **Runtime: java21** is only an illustrative choice. You must compile with a matching Java version and verify the Java runtimes supported by AWS at deployment time.
- **Handler** points to the adapter, not directly to the **@Bean greet()** method.
- **CodeUri** must point to the **actual built and properly packaged JAR**. **your-app-aws.jar** is not a fixed name generated by the framework.
- **spring_cloud_function_definition** selects the **greet** bean.
- **MAIN_CLASS** serves as a hint to locate the Spring Boot main class; if the manifest is complete, it may not be needed.
- **MemorySize** and **Timeout** are illustrative operational settings, not fixed optimal values.

If you use the AWS Console instead of SAM, the handler field per the Spring Cloud Function guide can be entered as:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Do not mix a runtime configured for a Java JAR with **container image** or **GraalVM native custom runtime** deployments: those deployment paths have their own startup and packaging mechanisms.

### Testing Events in AWS Lambda

If Lambda directly receives a JSON object meant for **GreetingRequest**, you can create a test event:

~~~json
{
  "name": "Lan"
}
~~~

The business result is the greeting message **Hello, Lan**.

**Warning about triggers:** events generated by **API Gateway**, **SQS**, **S3**, or **EventBridge** have an outer structure (event envelope) different from a direct test event. Do not assume the adapter automatically unwraps a **body** field from every event type into **GreetingRequest**. Choose a Java input type or a conversion step that matches the event contract and test with a real payload from the chosen trigger.

## 13. Invoking Lambda and Distinguishing Output from Logs

AWS CLI example for an environment with configured AWS credentials and Lambda invocation permissions, in a shell supporting single-quote syntax:

~~~bash
aws lambda invoke \
  --function-name greeting-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '{"name":"Lan"}' \
  response.json

cat response.json
~~~

**greeting-lambda** is an illustrative deployment name; **response.json** is the output file of the CLI command. This is not a file you need to create within the scope of this lesson.

What to verify during hands-on practice:

1. The invocation does not fail with a handler initialization error.
2. The Spring context finds the **greet** bean.
3. The input JSON is properly converted into **GreetingRequest**.
4. The output matches the structure of **GreetingResponse**.
5. CloudWatch logs contain no exceptions or sensitive data.

**The CLI command can complete the Lambda invocation even when the Lambda returns an application error.** Check the response metadata (such as function error indicators), the response payload, and the logs; do not rely solely on the CLI exit code.

## 14. The AWS Adapter Dependency Does Not Replace Event-Type Libraries

For specialized input events, application code may need classes such as **SQSEvent**, **S3Event**, **SQSBatchResponse**, or **Context**. In that case, you may need to explicitly declare **aws-lambda-java-events** or **aws-lambda-java-core** with the right version and scope for the imported APIs.

Example signature for SQS:

~~~java
// Illustrates the signature, not complete batch processing.
Function<com.amazonaws.services.lambda.runtime.events.SQSEvent,
         com.amazonaws.services.lambda.runtime.events.SQSBatchResponse>
    processSqsBatch = event -> {
        // Inspect each record and build the result according to the AWS contract.
        throw new UnsupportedOperationException(
            "Implement batch processing and partial failure response");
    };
~~~

The snippet above only shows why an **SQSEvent** type differs from **GreetingRequest**. It intentionally leaves SQS handling unimplemented and **must not be used directly in production**. If you want to return a partial batch response, you must follow the exact event source mapping and AWS configuration for reporting batch item failures; returning a constructed **SQSBatchResponse** alone is not enough if the trigger is not configured accordingly.

**spring-cloud-function-adapter-aws** solves the generic integration path. It does not automatically provision IAM roles, create SQS queues, guarantee idempotency, or decide retry/dead-letter policies for each event source.

Similarly, if business logic calls DynamoDB or S3 using the AWS SDK, the SDK dependencies, client configuration, and IAM permissions must be declared separately. Do not assume the adapter pulls in a full AWS SDK ready for every service.

## 15. Data Conversion and Generic Types

**FunctionInvoker** can attempt to convert the input payload into the type declared on the Function.

For example:

~~~java
Function<GreetingRequest, GreetingResponse>
~~~

gives the adapter a clearer conversion target than:

~~~java
@SuppressWarnings("rawtypes")
Function genericFunction
~~~

When using raw types or unclear generic arguments, the converter may choose a generic representation such as **Map**, making business logic prone to cast errors or schema mismatches.

Notes table:

| Signature | Use Case | Risks to Check |
| --- | --- | --- |
| **Function<String, String>** | Simple text events | JSON string events and plain text can differ |
| **Function<DTO, Result>** | Events with a clear schema | Missing fields, numeric types, nullability, serializing records |
| **Function<Map<String,Object>, R>** | Flexible or unknown-schema events | Prone to manual casting, hard to version |
| **Function<InputStream, R>** | Raw input handling needed | Logic is responsible for parsing and data errors |
| **Function<SQSEvent, SQSBatchResponse>** | Processing batch events from SQS | Batch semantics, retries, and partial failures |

JSON support libraries may already be in the adapter's dependency tree, but **your chosen data types must still be supported by serialization**. Test with real events rather than only calling the Java Function directly.

## 16. Local Testing: Verifying Business Logic Before Deployment

An advantage of Spring Cloud Function is that logic can be tested without AWS credentials, the Lambda service, or an HTTP server.

Example JUnit 5 unit test for the **greet** bean:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingFunctionUnitTest {

    private final GreetingLambdaApplication application =
        new GreetingLambdaApplication();

    @Test
    void greetsValidName() {
        var result = application.greet().apply(
            new GreetingLambdaApplication.GreetingRequest("Lan")
        );

        assertEquals("Hello, Lan", result.message());
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> application.greet().apply(
                new GreetingLambdaApplication.GreetingRequest("  ")
            ));
    }
}
~~~

The test above verifies **Java logic** only. It does not test the handler class, AWS runtime, JSON conversion, or JAR layout.

### Testing FunctionCatalog in a Spring Context

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class GreetingFunctionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsGreetByName() {
        Function<GreetingLambdaApplication.GreetingRequest,
                GreetingLambdaApplication.GreetingResponse> fn =
            catalog.lookup("greet");

        assertNotNull(fn);

        var output = fn.apply(
            new GreetingLambdaApplication.GreetingRequest("Lan")
        );

        assertEquals("Hello, Lan", output.message());
    }
}
~~~

When running tests, the project needs **spring-boot-starter-test** and the appropriate Spring Cloud Function dependencies. If a test uses **@SpringBootTest**, the Spring context must be able to start without depending on real AWS services (unless you are intentionally writing an integration test against external services).

### Testing Levels to Distinguish

| Testing Level | What Does It Verify? |
| --- | --- |
| **Unit test** | Rules inside **Function.apply(...)**, validation, and output |
| **Spring integration test** | Bean discovery, DI, and **FunctionCatalog.lookup(...)** |
| **Artifact verification** | Shaded JAR contains the handler, classes, manifest, and required metadata |
| **Lambda invocation test** | Handler, runtime, event conversion, serialization, logs |
| **Trigger integration test** | SQS/S3/API Gateway event envelope, retries, batching, IAM, and timeout |

**Passing tests at an earlier level does not guarantee passing at the next.** For example, unit tests can pass normally while Lambda throws **ClassNotFoundException** if the shaded JAR is missing **FunctionInvoker.class**.

## 17. Diagnosing Dependency and Packaging Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Adapter not added or shaded JAR missing dependencies | Check dependency tree and uploaded artifact |
| **ClassNotFoundException** for application class | Wrong JAR layout or missing main class | Check **jar tf**, **Start-Class**, **MAIN_CLASS** |
| **FunctionCatalog cannot find greet** | Wrong bean/definition name, Spring context did not scan class | Check **@Bean**, package scan, and env var |
| Lambda starts but auto-configuration fails | Spring metadata overwritten during shading | Check resource transformers and Spring Boot version |
| **NoSuchMethodError** or Spring class conflict | Incompatible Boot/Cloud/Function versions | Check BOM, dependency tree, duplicate versions |
| Input received unexpectedly as a Map | Unclear generic or converter does not know DTO | Declare **Function<DTO, R>**, test real JSON events |
| Output differs when called via API Gateway | Event has a different envelope than direct invoke | Map **body**, status, headers according to the trigger |
| Wrong AWS handler | Set Java bean name as Lambda handler | Use **FunctionInvoker**, select bean via definition |
| Runtime reports unsupported class version | Compiled with higher Java version than Lambda runtime | Align compiler release and Java runtime |
| Cold start too slow | Large application context, too many dependencies/init work | Reduce auto-configuration and dependencies, measure cold starts |
| Cannot call S3/DynamoDB | Missing SDK, endpoint/region, or IAM permissions | Check service dependencies, client config, and IAM |
| Build runs locally but Lambda fails | Uploaded Boot executable JAR instead of shaded JAR | Verify classifier/artifact name and internal JAR layout |

### Inspecting the Dependency Tree

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands reveal the adapter, Spring Cloud Function context, and resolved versions. If there are multiple module versions or unexpected dependencies, adjust the BOM and exclusions for identified reasons; do not randomly remove dependencies just to get a temporary build to pass.

## 18. Operations: Cold/Warm Starts, IAM, and Configuration Security

Even a complete JAR can be difficult to operate if application startup is too heavy or has external dependencies.

**Cold start:** when Lambda creates a new execution environment, the platform must download the artifact, start the Java runtime, initialize the Spring context, and load dependencies. Adding Spring Web, excessive auto-configuration, or creating heavy clients at startup can impact latency and cost.

**Warm invocation:** an environment can be reused. Singleton beans may persist across multiple invocations in the same environment, but **you cannot rely on this reuse to hold business state**. Different environments do not automatically share memory.

**IAM:** grant least-privilege permissions to the Lambda execution role, such as allowing reads only from a specific bucket or writes only to the table required by the business logic. The AWS adapter does not grant permissions automatically. Do not treat event payloads or headers from callers as authenticated without proper validation controls.

**Secrets:** avoid hard-coding access keys or secrets in source code or unmanaged environment variables. Use a managed configuration/secrets mechanism suitable for the project; do not log credentials or entire sensitive payloads.

**Observability:** use logs with standardized request IDs/correlation IDs, and monitor errors, duration, cold starts, and timeouts. Exceptions from a Function should be categorized to avoid unnecessary retries on invalid data.

**Advanced optimizations:** Lambda SnapStart, memory/CPU sizing, and functional bean registration can help reduce cold starts in appropriate cases; measure in practice, verify runtime compatibility, and assess effects on client/state initialization. Do not enable an optimization simply because you saw it in an example from a different version.

## 19. Pre-Deployment Checklist

| Question | Expected Status |
| --- | --- |
| Is **spring-cloud-function-adapter-aws** declared? | Yes |
| Are Spring Boot/Cloud/Function release versions compatible? | Yes, managed via BOM/pinned versions |
| Does the application have appropriate Function/Supplier/Consumer beans? | Yes, clearly named |
| Does **spring_cloud_function_definition** point to the right bean when needed? | Yes |
| Has a runtime-appropriate **shaded JAR** artifact been built? | Yes |
| Does the JAR contain **FunctionInvoker**, main class, and Spring metadata? | Yes, verified |
| Does the AWS handler point to **FunctionInvoker**? | Yes |
| Has **Start-Class** or **MAIN_CLASS** for main discovery been verified? | Yes |
| Is the Java bytecode compatible with the Lambda runtime? | Yes |
| Has direct invocation been tested with realistic JSON input? | Yes |
| If using API Gateway/SQS/S3, has the event envelope been tested? | Yes |
| Are IAM, timeout, memory, and retries configured appropriately? | Yes |
| Have logs, sensitive data, and side effects/idempotency been checked? | Yes |

This checklist emphasizes that **the dependency is a necessary condition, not a sufficient one**. A successful deployment depends on bean registration, versions, packaging, handler configuration, event mapping, and operational settings.

## 20. Hands-on Exercises

**Exercise 1 — Distinguishing dependencies.** An existing application has **spring-cloud-starter-function-web** and needs to run on Lambda. State which artifact must be added, why the Web starter cannot replace the AWS adapter, and when Web/Stream adapters can be excluded from the deployed artifact.

**Exercise 2 — Maven/Gradle.** Write a BOM and dependency configuration for **spring-cloud-function-adapter-aws**. Explain why you should not enter a Spring Cloud Function version incompatible with Spring Boot, and which command inspects the dependency tree.

**Exercise 3 — Bean and handler.** Create **@Bean("normalizeSku") Function<String,String>**, configure the **FunctionInvoker** handler, and set the environment variable so Lambda selects **normalizeSku**. Explain the difference between the Lambda handler and the bean name.

**Exercise 4 — Shaded JAR.** Given a project producing both an executable Boot JAR and an AWS shaded JAR, identify which artifact to upload. Inspect **FunctionInvoker.class**, the **@SpringBootApplication** class, the manifest, and **AutoConfiguration.imports**. Describe what happens when shading drops Spring metadata.

**Exercise 5 — DTO conversion.** Change a function from **Function<String, String>** to **Function<GreetingRequest, GreetingResponse>**. Test a direct Lambda JSON object containing a **name** field, then explain why an API Gateway event does not necessarily have that direct structure.

**Exercise 6 — Multiple Lambdas from one JAR.** Register two beans **uppercase** and **lowercase**; deploy them as two Lambdas sharing the same artifact but with different **spring_cloud_function_definition** values. State the benefits of separate IAM, timeout, and trigger configurations.

**Exercise 7 — Operations.** A Lambda has slow cold starts after unnecessary Spring Web and AWS SDK dependencies were added. Create a plan to audit dependencies, auto-configuration, startup time, memory/CPU, and test before/after optimization.

**Exercise 8 — Error analysis.** Lambda throws **ClassNotFoundException: FunctionInvoker** even though **Function.apply(...)** unit tests pass. Identify which layers to inspect—dependencies, build artifact, handler, and runtime—and explain why unit tests did not catch this error.

### Key Takeaways

- The core dependency is **org.springframework.cloud:spring-cloud-function-adapter-aws**; it is a **runtime adapter**, not a build plugin.
- **FunctionInvoker** is the AWS Lambda handler, while **FunctionCatalog** looks up beans such as **greet**, **normalizeSku**, or a composition chain by definition.
- **Spring Cloud BOM and compatible Boot versions** prevent conflicts between the adapter, context, and other Spring libraries.
- When deploying a Java JAR to Lambda, you must **build a proper shaded JAR**, preserve Spring metadata, and verify **Start-Class/MAIN_CLASS** along with the handler.
- **AWS Lambda event envelopes** differ across direct invocation, API Gateway, SQS, and S3; the adapter does not eliminate the need for schema design and conversion.
- Unit tests verify logic, integration tests verify Spring, and artifact/Lambda tests confirm the dependency truly works in the deployment environment.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): dependency, FunctionInvoker, handler, routing, shaded JAR, and deployment notes.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): function model, FunctionCatalog, composition, and adapters.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): handler contract and Java runtime.
- [AWS Lambda — Deployment packages for Java](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): how to package and deploy Java code.
