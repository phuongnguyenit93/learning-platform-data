# Configuring FunctionInvoker::handleRequest as the Entry Point

In **SPRING_CLOUD_FUNCTION**, business logic is declared via **Supplier<T>**, **Function<T, R>**, or **Consumer<T>** beans. When deploying that same logic to **AWS Lambda**, the platform does not automatically know which Spring bean to invoke; it requires a **handler** (entry point) following the Java runtime contract. The **spring-cloud-function-adapter-aws** library provides the **org.springframework.cloud.function.adapter.aws.FunctionInvoker** class and the **handleRequest** method to connect AWS invocations to **FunctionCatalog**.

This lesson belongs to the **AWS Lambda** chapter and focuses on properly configuring **FunctionInvoker::handleRequest** as the handler through the AWS Console or Infrastructure as Code, identifying the Spring Boot class to initialize, selecting the business Function bean, converting events, testing, and diagnosing errors. The goal is to keep application logic unchanged when switching between HTTP, events, and Lambda, while AWS-specific responsibilities remain in the adapter layer.

## 1. Three Different Names in a Spring Cloud Function Lambda

An application can contain the following identifiers:

| Component | Example | Role |
| --- | --- | --- |
| **Lambda handler** | **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** | Entry method invoked by the AWS Lambda runtime |
| **Spring Boot application class** | **example.lambda.GreetingApplication** | Configuration class used to create the Spring ApplicationContext |
| **Function bean name** | **greet** | Logic identifier looked up and executed by FunctionCatalog |
| **Function definition** | **spring.cloud.function.definition=greet** | Rule selecting the bean or composition to run |

These are four related concepts, yet **they cannot be used interchangeably**. AWS does not use the name **greet** to look up a Java handler directly, and **FunctionInvoker** is not the greeting logic itself.

~~~mermaid
flowchart LR
    A["AWS Lambda invocation"] --> B["FunctionInvoker.handleRequest"]
    B --> C["Spring ApplicationContext"]
    C --> D["FunctionCatalog"]
    D --> E["greet Function bean"]
    E --> B
    B --> F["Lambda response"]
~~~

**Common mistake:** setting the handler to **example.lambda.GreetingApplication::main** or **greet**. The **main(String[] args)** method does not accept an AWS event per the handler contract, while **greet** is merely a Spring bean name.

## 2. What Does Handler Mean in AWS Lambda Java?

Every AWS Lambda function configures a **handler**. When receiving an invocation, the runtime loads the corresponding class/method from the artifact and passes the **event** and **Context** information according to the Java runtime contract.

AWS supports several handler models, including:

- **RequestHandler<I, O>**: a Java handler receiving an input object and **Context**, returning an output result.
- **RequestStreamHandler**: a handler reading an **InputStream**, writing an **OutputStream**, and receiving **Context**.
- Standard Java methods matching general handler rules when not implementing the two interfaces above.

Spring Cloud Function's **FunctionInvoker** integrates with **RequestStreamHandler**. Its core signature looks like:

~~~java
@Override
public void handleRequest(
        java.io.InputStream input,
        java.io.OutputStream output,
        com.amazonaws.services.lambda.runtime.Context context)
        throws java.io.IOException {
    // The adapter handles context initialization, conversion,
    // Function lookup in the catalog, and writing the response.
}
~~~

The snippet above illustrates the signature so the reader understands the interface. **You do not need to write this handler body yourself** when using the built-in adapter. In your application, you only need to declare Function beans with concrete data types.

### How Is the Handler Syntax Used?

In the AWS Lambda Console, Spring Cloud Function instructs entering:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

AWS Java documentation also describes using **package.Class** when a class implements **RequestHandler** or **RequestStreamHandler**. Consequently, many Spring Cloud Function SAM examples use:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

Both forms appear in official documentation in different contexts. **For this lesson**, the illustrative configuration prefers **FunctionInvoker::handleRequest** as specified in the topic; when using templates or deployment tools, verify which handler value is supported by **your adapter version and Lambda runtime**.

Do not assume that Java method-reference syntax in source code, such as **service::process**, can be placed directly into the AWS handler field. The AWS handler field belongs to the **runtime**, not a reference to a Spring bean created with **@Bean**.

## 3. What Does FunctionInvoker Do?

The generic handler handles many responsibilities that a business function should not carry:

1. Receives the event **InputStream** and **Context** supplied by Lambda.
2. Initializes or reuses the **Spring ApplicationContext** appropriately for the execution environment lifecycle.
3. Retrieves **FunctionCatalog** from the context.
4. Determines the **function definition** or applies configured routing.
5. Uses the Function's input type to convert the event into an appropriate Java payload when supported by converters.
6. Invokes the selected **Supplier**, **Function**, or **Consumer** via the corresponding wrapper.
7. Writes the result to the output stream or lets errors propagate to the runtime per adapter rules.

~~~mermaid
sequenceDiagram
    participant AWS as AWS Lambda
    participant Invoker as FunctionInvoker
    participant Spring as Spring context
    participant Cat as FunctionCatalog
    participant Fn as Function<T,R>

    AWS->>Invoker: handleRequest(input, output, Context)
    Invoker->>Spring: initialize / get context
    Spring-->>Invoker: beans
    Invoker->>Cat: lookup definition
    Cat-->>Invoker: Function wrapper
    Invoker->>Fn: apply(T)
    Fn-->>Invoker: R
    Invoker-->>AWS: write output stream
~~~

The **Function<T, R>** signature is not an object instantiated directly by AWS. The **Function** bean resides in the Spring context, whereas **FunctionInvoker** is the entry point AWS locates from the deployed JAR or package.

The adapter may use wrappers to support **conversion, Message, and composition**. The object returned by the catalog does not necessarily have the same identity as the original bean; do not cast the wrapper to a specific application implementation class without a guaranteed contract.

## 4. Complete Example: One Spring Boot Application with Two Functions

To clearly show the handler and bean selection, we create two functions: **greet** taking a JSON DTO and returning a JSON result, and **uppercase** taking a string and returning a string. Both live in the same Spring Boot application, while AWS Lambda selects only one definition per invocation according to configuration.

File **src/main/java/example/lambda/GreetingApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }

    public record GreetingRequest(
        String name
    ) {}

    public record GreetingResponse(
        String message
    ) {}

    @Bean("greet")
    Function<GreetingRequest, GreetingResponse> greet() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException(
                    "Name must not be blank");
            }

            return new GreetingResponse(
                "Hello, " + request.name().trim());
        };
    }

    @Bean("uppercase")
    Function<String, String> uppercase() {
        return text -> {
            if (text == null) {
                throw new IllegalArgumentException(
                    "Text must not be null");
            }

            return text.toUpperCase(Locale.ROOT);
        };
    }
}
~~~

The application has two beans with different names:

~~~text
greet      : Function<GreetingRequest, GreetingResponse>
uppercase  : Function<String, String>
~~~

If AWS specifies **greet**, a direct JSON object event can be:

~~~json
{
  "name": "Lan"
}
~~~

Expected business output:

~~~json
{
  "message": "Hello, Lan"
}
~~~

**uppercase** has a different input contract: a JSON string, such as **"hello"**, not the object **{"name":"Lan"}**. When switching function definitions, the test payload must match the new signature; otherwise, errors occur during conversion or inside the logic.

The application does not import AWS **RequestStreamHandler** or create a custom subclass of **FunctionInvoker**. That is the whole purpose of the adapter: keeping business logic as reusable Java Functions.

## 5. Required Dependencies Before Configuring the Handler

The handler only works if the artifact includes the AWS adapter library. Maven dependencies:

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

This is only the dependency declaration, **not a complete pom.xml**. The project must have compatible Spring Boot/Spring Cloud Function versions and a Maven Shade/Gradle Shadow setup if deploying via JAR.

**Do not confuse these dependency types:**

| Component | When to Use |
| --- | --- |
| **spring-cloud-function-adapter-aws** | Lambda handler to invoke FunctionCatalog |
| **spring-cloud-starter-function-web** | Expose functions via an HTTP server; not needed merely to run on Lambda |
| **spring-cloud-stream + binder** | Process messages through a broker using the Spring Cloud Stream model |
| **aws-lambda-java-events** | Use specific AWS event types such as SQSEvent/S3Event in signatures |
| **aws-sdk-java** | Call AWS service APIs from application logic/adapters |

A Lambda receiving events from SQS does not mean the application necessarily needs to run a Spring Cloud Stream binder. **AWS Lambda event source mapping** is already a different invocation path; pick the right architecture model and event type before adding dependencies.

Spring dependencies should be managed using a compatible **Spring Boot BOM/parent** and **Spring Cloud BOM**. Do not choose an arbitrary adapter version merely because that artifact is the latest.

## 6. Selecting a Bean with spring.cloud.function.definition

When the application has two beans **greet** and **uppercase**, you must specify which function Lambda should call. Configuration in Spring:

~~~yaml
spring:
  cloud:
    function:
      definition: greet
~~~

In the AWS Lambda environment, the property can be passed via an environment variable:

~~~text
spring_cloud_function_definition=greet
~~~

This variable name is documented by Spring Cloud Function for AWS Lambda, replacing dots in the Spring property name with underscores in the manner supported by Spring Boot binding.

**The handler remains FunctionInvoker** and does not change per bean:

~~~text
Handler = org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
spring_cloud_function_definition = greet
~~~

If **uppercase** is needed:

~~~text
Handler = org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
spring_cloud_function_definition = uppercase
~~~

What differs is the **function definition** and the **input/output contract**. You do not need to create a new Java handler class for each bean in these cases.

### What If No Definition Is Specified?

Spring Cloud Function has default function lookup and routing mechanisms when none is specified. However, in an application with multiple Functions/Suppliers/Consumers, the choice can be ambiguous or depend on framework-defined precedence rules.

**Do not rely on bean declaration order in source code.** When deploying a Lambda for a specific business capability, set **spring_cloud_function_definition** explicitly, then test that the right bean is invoked.

### What If the Definition Is a Composition?

For example, two beans with compatible types:

~~~java
@Bean("trimText")
Function<String, String> trimText() {
    return String::trim;
}

@Bean("uppercaseText")
Function<String, String> uppercaseText() {
    return text -> text.toUpperCase(Locale.ROOT);
}
~~~

You can select a pipeline:

~~~text
spring_cloud_function_definition=trimText|uppercaseText
~~~

The handler stays the same. **Composition** runs left-to-right and must ensure the output of the preceding step is compatible with the input of the next step. Test in practice with real data types, converters, and runtime environment; do not chain two arbitrary beans just because both implement Function.

## 7. Packaging the Application So Lambda Can Load the Handler

Setting the right handler while uploading a **wrongly structured JAR** will still result in **ClassNotFoundException**. For the Spring Cloud Function AWS Java JAR deployment path, the documentation recommends a **shaded JAR** containing the handler class, application classes, dependencies, and required Spring resources.

Note the difference:

~~~text
Spring Boot executable JAR:
  BOOT-INF/classes/
  BOOT-INF/lib/...
  org/springframework/boot/loader/...

Lambda shaded JAR:
  example/lambda/GreetingApplication.class
  org/springframework/cloud/function/adapter/aws/FunctionInvoker.class
  org/springframework/... (dependency classes)
  META-INF/... (Spring metadata)
~~~

With a Spring Boot executable JAR, the Boot launcher knows how to load nested dependencies when running **java -jar**. The Lambda Java runtime loads the handler from the classpath and does not run through the Boot launcher by default. Therefore, do not upload an arbitrary Spring Boot executable JAR assuming the runtime will read classes inside **BOOT-INF/lib**.

### Dependencies and Build Plugins Are Separate Concerns

- **spring-cloud-function-adapter-aws** is a **runtime dependency**.
- **maven-shade-plugin** or **Gradle Shadow** is a **packaging tool**.
- **aws-lambda-java-core** and event SDKs are used when application/adapter code needs their APIs; they do not replace the handler adapter.

A Shade/Shadow configuration must merge **META-INF/spring.factories**, **AutoConfiguration.imports**, and related resources according to each file's format. If only one file is kept when multiple dependencies share metadata with the same name, the Spring context may fail even while **FunctionInvoker** remains intact.

### Verifying the Artifact

Illustrative commands on a system with **jar** and **grep**:

~~~bash
mvn clean package
ls -lh target/*.jar

jar tf target/greeting-aws.jar |
  grep 'org/springframework/cloud/function/adapter/aws/FunctionInvoker.class'

jar tf target/greeting-aws.jar |
  grep 'example/lambda/GreetingApplication.class'

jar tf target/greeting-aws.jar |
  grep 'META-INF/spring/'
~~~

**target/greeting-aws.jar** is a sample name; replace it with the actual file produced after the build, usually including a version and the **aws** classifier. Make sure the inspection commands run on the **actual artifact you intend to upload**, not another JAR generated alongside it.

If the JAR is missing **FunctionInvoker.class**, the issue is in dependencies or packaging, not the bean name or JSON input. If **GreetingApplication.class** is missing, **MAIN_CLASS** cannot rescue the artifact.

## 8. Identifying the Application Class via Start-Class or MAIN_CLASS

FunctionInvoker needs to know the **Spring application class** to initialize the context. Spring Cloud Function can read **Start-Class** from the JAR manifest; if absent or to specify it explicitly, you can provide the **MAIN_CLASS** environment variable:

~~~text
MAIN_CLASS=example.lambda.GreetingApplication
~~~

Example manifest:

~~~text
Manifest-Version: 1.0
Start-Class: example.lambda.GreetingApplication
~~~

**MAIN_CLASS is a fully qualified class name**, not:

~~~text
MAIN_CLASS=greet                                  # Wrong: bean name
MAIN_CLASS=FunctionInvoker                        # Wrong: handler name
MAIN_CLASS=GreetingApplication::main              # Wrong: method name
~~~

Environment variables in AWS can be set as:

~~~text
MAIN_CLASS = example.lambda.GreetingApplication
spring_cloud_function_definition = greet
~~~

If the manifest already identifies the application class properly, **MAIN_CLASS may not be needed**. When setting both, keep them consistent and verify the behavior of the adapter version you are using.

**Note:** a normal main method can still exist in the source:

~~~java
public static void main(String[] args) {
    SpringApplication.run(GreetingApplication.class, args);
}
~~~

However, Lambda **does not call main() as the handler**. The adapter initializes the application context via Spring Cloud Function's mechanism; discovering the main class does not mean AWS executes the main method the same way **java -jar** does.

## 9. Configuring the AWS Lambda Console

A manual deployment workflow may proceed as follows:

1. Create a Lambda function with a **Java managed runtime** compatible with the application bytecode.
2. Upload the built **AWS JAR**, taking care not to confuse it with the Boot executable JAR artifact.
3. Open **Runtime settings** and set **Handler** to:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

4. Under **Configuration → Environment variables**, declare **spring_cloud_function_definition=greet**; add **MAIN_CLASS** if needed.
5. Configure memory, timeout, execution role, and appropriate IAM permissions.
6. Create a test event containing a JSON object matching the **greet** contract.
7. Invoke and inspect the output, function error, and CloudWatch logs.

Menu names may vary across AWS Console UI updates, yet the concepts of **runtime**, **handler**, **artifact**, and **environment variables** remain the fields to confirm.

**Do not set the handler to a bean factory method name** such as **GreetingApplication::greet**: that method returns a Function and does not accept Lambda's **InputStream, OutputStream, Context**.

## 10. Configuring AWS SAM / Infrastructure as Code

You can describe the function using **AWS Serverless Application Model (SAM)**. Example of a Lambda using the **greet** bean:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GreetingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/greeting-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.GreetingApplication
          spring_cloud_function_definition: greet
~~~

Explanation:

- **Runtime: java21** is an example compatible with source/bytecode built for Java 21 or lower per runtime requirements; verify the actual AWS runtime list and Spring version.
- **Handler** is the AWS entry point, not the function bean name.
- **CodeUri** must point to the **actual built JAR file**; the filename is illustrative.
- **MAIN_CLASS** is the Spring application class; **spring_cloud_function_definition** is the business bean name.
- **MemorySize** and **Timeout** are illustrative and must be measured and tuned for the application.
- **Role/IAM** must be configured according to which AWS services are called. SAM can generate a default role for some configurations, but never assume that role has enough permissions for every task.

Spring Cloud Function documentation also has SAM examples where **Handler** is just the class name:

~~~yaml
Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

The reason: FunctionInvoker implements a Java handler interface that the runtime can recognize by class name. Within a project, standardize on **one syntax verified with your runtime and deployment tool**; this lesson uses the **::handleRequest** form to make the entry method explicit.

### Two Lambdas Sharing One JAR

If two business operations have different access permissions or scaling profiles, one JAR can be deployed as two separate Lambdas:

~~~yaml
Resources:
  GreetingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/greeting-aws.jar
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.GreetingApplication
          spring_cloud_function_definition: greet

  UppercaseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/greeting-aws.jar
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.GreetingApplication
          spring_cloud_function_definition: uppercase
~~~

This illustrative example focuses only on handler and definition; in a real SAM template, check memory, timeout, IAM, triggers, and packaging thoroughly. Do not assume **greet** and **uppercase** take the same test payload: they accept two different types.

## 11. Checking Configuration via AWS CLI

Once you have a real Lambda name and appropriate AWS permissions, you can inspect the current runtime/handler:

~~~bash
aws lambda get-function-configuration --function-name greeting-lambda
~~~

In the output, inspect **Handler**, **Runtime**, **Environment.Variables**, configuration state, and any related errors. **greeting-lambda** here is an example AWS function name, not a Spring bean name.

You can update the handler via CLI:

~~~bash
aws lambda update-function-configuration --function-name greeting-lambda --handler 'org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest'
~~~

Or update the configuration via SAM/CloudFormation/Terraform rather than editing directly in the Console/CLI. **If the project is managed with Infrastructure as Code, edit the IaC source and redeploy** to avoid infrastructure state drift.

When updating environment variables via CLI, note that the API may **replace the entire Environment.Variables map** rather than inserting a single key. Read the current configuration and send all keys you want to keep; do not include real secrets in examples, shell history, or output logs.

## 12. Testing Direct Invocation with Matching JSON

After deploying the **greet** bean, test event:

~~~json
{
  "name": "Lan"
}
~~~

AWS CLI example, in a shell supporting single quotes:

~~~bash
aws lambda invoke --function-name greeting-lambda --cli-binary-format raw-in-base64-out --payload '{"name":"Lan"}' response.json

cat response.json
~~~

Expected business output:

~~~json
{
  "message": "Hello, Lan"
}
~~~

Actual output is serialized according to the adapter and invocation event. **The aws lambda invoke command can return success metadata at the API level while the Function had an execution error**. Check the **FunctionError** field if present, the contents of **response.json**, and CloudWatch logs.

When switching **spring_cloud_function_definition** to **uppercase**, a compatible event for **Function<String,String>** can be a **JSON string**:

~~~json
"hello"
~~~

Do not pass the object **{"name":"Lan"}** into **uppercase** and conclude the handler is broken when the payload does not match the generic signature.

### Layer-by-Layer Self-Check

~~~text
1. Did Lambda load the handler?
2. Did FunctionInvoker initialize the Spring context?
3. Did FunctionCatalog find the right bean by definition?
4. Was the input converted to the right type?
5. Did the Function execute and return a result?
6. Was the output serialized properly for the caller?
~~~

Testing layer by layer helps separate **handler errors** from **data conversion errors** or **business logic errors**.

## 13. Direct Invoke Differs from API Gateway, SQS, S3, and EventBridge

A direct invoke JSON like **{"name":"Lan"}** is not the same as a full event emitted by another AWS service.

| Invocation Source | Points to Note |
| --- | --- |
| **Direct invoke** | Caller supplies payload directly; can be a direct JSON DTO |
| **API Gateway** | Event typically contains **body**, headers, request context, and route metadata |
| **SQS** | Event contains **Records** and possibly multiple messages in a batch |
| **S3** | Event contains bucket info, object key, and event type |
| **EventBridge** | Event envelope contains **detail**, **source**, **detail-type**, and metadata |

FunctionInvoker can convert data based on the bean's generic types. However, **do not assume every event envelope is automatically unwrapped into a business DTO across every version and trigger**. Write integration tests with realistic events or use the corresponding AWS event types when needed.

Example SQS handler using a dedicated signature:

~~~java
@Bean("processSqs")
Function<
    com.amazonaws.services.lambda.runtime.events.SQSEvent,
    com.amazonaws.services.lambda.runtime.events.SQSBatchResponse>
        processSqs() {
    return event -> {
        // Inspect each record and return partial batch failure
        // per the AWS contract if the application uses that feature.
        throw new UnsupportedOperationException(
            "Implement batch processing before deployment");
    };
}
~~~

This snippet **only illustrates the signature** and intentionally omits batch logic; do not use it as-is in production. Partial batch response support requires matching event source mapping configuration and the proper output type. When using **SQSEvent/SQSBatchResponse** classes, the project may need **aws-lambda-java-events**.

In the SQS model, a failed record can be redelivered. A properly configured handler **does not automatically guarantee idempotency**, ordering, partial failure handling, or DLQ behavior.

## 14. Context Metadata and AWS-Independent Function Design

AWS passes a **Context** to the handler. Context can hold invocation details such as the AWS request ID, remaining timeout, or runtime logger. **FunctionInvoker** receives this object at the adapter layer.

If business logic only transforms a payload, keep the function simple:

~~~java
Function<GreetingRequest, GreetingResponse>
~~~

If you need a correlation ID or metadata from the context for business logic, define an explicit path to pass that metadata into your code. Do not assume every **Context** field always appears in the payload DTO or Spring Message headers.

You can place a dedicated adapter at the boundary if technical metadata must be mapped into a Java input with an explicit contract. When preserving headers across composition, use **Message<T>** and **MessageBuilder** deliberately; do not copy all sensitive metadata unnecessarily.

Do not add **aws-lambda-java-core.Context** to the signature of every Function just to log. The more business logic is coupled directly to AWS APIs, the less reusable it becomes across HTTP or Stream transports.

### Avoid Confusing Authentication with Correlation

A header or event field such as **correlationId** only supports tracing. If sent by the client, it is **not proof of identity or authorization**. Authentication checks should be performed at API Gateway/authorizer or the appropriate trust boundary.

## 15. Business Errors, Conversion Errors, and Retries Are Not the Same

When Lambda reports an error, you must distinguish:

1. **Runtime/handler error:** Lambda cannot load FunctionInvoker.
2. **Initialization error:** handler loads, but the Spring context fails to start.
3. **Function lookup error:** catalog cannot find the bean/definition.
4. **Conversion error:** JSON event does not match the input type.
5. **Validation/business error:** Function is called but rejects the input.
6. **Infrastructure error:** database/API/broker times out or lacks permissions.

~~~mermaid
flowchart TD
    A["Lambda invocation"] --> B{"Handler load?"}
    B -- "No" --> C["ClassNotFound / config error"]
    B -- "Yes" --> D{"Spring context?"}
    D -- "No" --> E["Main class / dependency error"]
    D -- "Yes" --> F{"FunctionCatalog lookup?"}
    F -- "No" --> G["Definition / bean error"]
    F -- "Yes" --> H{"Input conversion?"}
    H -- "No" --> I["Schema / type error"]
    H -- "Yes" --> J["Business Function"]
    J --> K["Output or exception"]
~~~

**Do not assume every exception should be retried**. A malformed payload is usually a permanent error; an API timeout may be transient. For asynchronous invocations or event sources like SQS, retry and failure mechanics are governed by AWS triggers/event source mappings.

A **Consumer** writing to a database must design idempotency using a stable event key, unique constraint/transaction, or outbox as required. AWS may redeliver the same event after side effects completed if the response or acknowledgment failed.

## 16. Spring Context Lifecycle and Cold Starts

With Java Lambda, one execution environment can serve multiple invocations. FunctionInvoker can retain and reuse the context after initialization, reducing startup cost on subsequent calls.

~~~text
Cold start:
  Lambda downloads artifact
  -> JVM / handler class
  -> Spring context and beans initialize
  -> FunctionCatalog lookup
  -> Function invocation

Warm invocation:
  Handler/context may be reused
  -> Function invocation
~~~

Not every invocation is guaranteed to be warm: Lambda can create new execution environments, scale out across instances, or recycle instances. **A Spring singleton bean is only a singleton within one instance's context**, not a shared object across all Lambdas.

To reduce cold starts:

- Include only adapter and infrastructure dependencies that are truly needed.
- Avoid configuring a web server if the function only runs on Lambda.
- Avoid heavy unnecessary startup I/O.
- Measure **Init Duration**, **Duration**, memory, and startup logs on realistic workloads.
- Consider mechanisms such as AWS SnapStart or provisioned concurrency when appropriate, after checking limits/runtime support and snapshotted state.

The right handler **does not reduce latency by itself**. It is a prerequisite for running the Function; performance must be analyzed separately.

## 17. Testing Java Functions Independently of Lambda

An advantage of Spring Cloud Function is that business functions can be tested without AWS. JUnit 5 example for the **greet** bean:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingApplicationUnitTest {

    private final GreetingApplication application =
        new GreetingApplication();

    @Test
    void greetReturnsExpectedMessage() {
        var result = application.greet().apply(
            new GreetingApplication.GreetingRequest("Lan")
        );

        assertEquals("Hello, Lan", result.message());
    }

    @Test
    void greetRejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> application.greet().apply(
                new GreetingApplication.GreetingRequest("  ")
            ));
    }
}
~~~

Unit tests only verify logic and validation. They **do not prove** FunctionInvoker is in the JAR or that AWS can load the handler.

### Integration Test for FunctionCatalog

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = GreetingApplication.class)
class GreetingCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogResolvesGreetBean() {
        Function<GreetingApplication.GreetingRequest,
                GreetingApplication.GreetingResponse> function =
            catalog.lookup("greet");

        assertNotNull(function);

        var response = function.apply(
            new GreetingApplication.GreetingRequest("Lan")
        );

        assertEquals("Hello, Lan", response.message());
    }
}
~~~

Integration tests verify the context and catalog, yet **do not replace** inspecting the shaded JAR or invoking a real Lambda. The project needs appropriate Spring Boot Test, JUnit, and Spring Cloud Function dependencies.

## 18. Testing Handler Configuration and the Artifact

A deployment test suite should cover these steps:

| Verification Level | Content |
| --- | --- |
| **Unit** | Function handles valid input properly and rejects invalid input |
| **ApplicationContext** | Spring initializes; catalog finds the **greet** bean |
| **Artifact inspection** | JAR contains **FunctionInvoker.class**, application classes, resources |
| **Lambda configuration** | Handler, MAIN_CLASS, definition, Runtime, and CodeUri are correct |
| **Direct invocation** | JSON event maps to DTO, output and logs are correct |
| **Trigger integration** | API Gateway/SQS/S3 envelope, retries, batching, IAM per event source |

You do not need to run Gradle/Maven/AWS deployments just to test Java logic. Conversely, you cannot rely solely on unit tests to claim the handler works on Lambda.

### Inspecting a Specific JAR

~~~bash
jar tf target/greeting-aws.jar |
  grep 'FunctionInvoker.class'

jar tf target/greeting-aws.jar |
  grep 'GreetingApplication.class'
~~~

You can check the manifest if the adapter needs **Start-Class**:

~~~bash
unzip -p target/greeting-aws.jar META-INF/MANIFEST.MF
~~~

If the adapter cannot determine the main class from the manifest, provide **MAIN_CLASS** with the exact class name. Do not replace **Handler** with the main class name to work around Spring initialization errors.

## 19. Common Configuration Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Missing adapter or wrong JAR uploaded | Check dependencies and shaded JAR |
| **ClassNotFoundException** for application class | Wrong package/MAIN_CLASS or JAR missing class | Check **jar tf** and manifest |
| Lambda invokes wrong Function | Multiple beans, missing/wrong definition | Set **spring_cloud_function_definition** accurately |
| **lookup("greet")** fails | Bean not registered or outside component scan | Check Spring context, @Bean name |
| Handler set to **GreetingApplication::main** | Confused Boot main with AWS handler | Use **FunctionInvoker::handleRequest** |
| Handler is right, but Spring fails to initialize | Missing auto-configuration or resource metadata | Check Shade transformers and Spring version |
| **NoSuchMethodError** at startup | Incompatible Spring dependencies | Align Boot/Cloud/Function BOM |
| JSON input turns into unexpected Map | Unclear generic type or unsuitable converter | Use **Function<DTO,R>**, test event |
| Direct invoke succeeds, but API Gateway fails | Event envelope differs from DTO | Map request body/headers explicitly |
| Entire SQS batch redelivered | Missing proper batch failure/retry handling | Configure event source mapping and idempotency |
| **UnsupportedClassVersionError** | Java compile release higher than runtime | Align toolchain and runtime |
| Timeout before logic runs | Cold start, slow dependency initialization | Check Init Duration, memory, startup |
| Updating environment drops other variables | CLI update replaces variable map | Read current config and pass all keys |
| Lambda returns function error, yet CLI request succeeds | Confused API invoke status with handler result | Check FunctionError, body, and logs |

An error must be traced at the **layer where it occurs**. Changing the handler string does not fix a wrong schema; changing the DTO does not solve ClassNotFoundException; increasing timeout does not replace merging Spring metadata.

## 20. Pre-Deployment Checklist

- [ ] Compatible **org.springframework.cloud:spring-cloud-function-adapter-aws** dependency is present.
- [ ] A **shaded JAR** suited for the Java Lambda runtime has been built with the handler and application classes.
- [ ] Handler is configured as **FunctionInvoker::handleRequest** or a verified class-only form.
- [ ] **MAIN_CLASS** or **Start-Class** accurately identifies the Spring Boot application.
- [ ] The **greet** bean has the exact name and is inside the Spring context.
- [ ] **spring_cloud_function_definition** selects the right bean or pipeline.
- [ ] Java compile release is compatible with the Lambda Runtime.
- [ ] JSON test event matches the input type and trigger event envelope.
- [ ] JAR filename in CodeUri/upload points to the latest build artifact.
- [ ] Lambda execution role has least-privilege permissions for the business task.
- [ ] CloudWatch logs, errors, timeouts, and cold starts have been checked.
- [ ] For events with side effects, idempotency, retries, and DLQ are designed where needed.

## 21. Hands-on Exercises

**Exercise 1 — Distinguishing three names.** An application has class **com.shop.QuoteApplication** and bean **@Bean("quoteOrder")**. Write the exact values for the AWS handler, MAIN_CLASS, and spring_cloud_function_definition. Explain why the bean name must not be configured as the handler.

**Exercise 2 — Console.** Create a Lambda using a JAR containing **FunctionInvoker** and the **uppercase** bean. Specify Runtime settings, Handler, and environment variable. Predict what happens if a JSON object is sent instead of a JSON string.

**Exercise 3 — SAM.** Create two Lambdas **UppercaseLambda** and **GreetingLambda** from the same JAR. Use FunctionInvoker as the handler, but give each Lambda a different definition. Analyze the ability to assign separate IAM roles and memory.

**Exercise 4 — Class-only vs. method form.** Compare **org.springframework.cloud.function.adapter.aws.FunctionInvoker** with **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** based on Java RequestStreamHandler and runtime documentation. Verify a syntax accepted by your deployment tool.

**Exercise 5 — Fixing a wrong handler.** A Lambda is configured with **com.example.GreetingApplication::main** and logs report a handler initialization failure. State the correct handler value, then explain why the Spring main class is still needed at another layer.

**Exercise 6 — FunctionCatalog.** An app has three beans **greet**, **uppercase**, **trim**. Write a test looking up **greet**; then configure **trim|uppercase** and predict the output for a string with whitespace.

**Exercise 7 — Event envelope.** Direct invocation with JSON **{"name":"Lan"}** succeeds, but API Gateway sends an event with a **body** containing JSON. Design an adapter step to read the body properly; do not change the handler name to fix a mapping error.

**Exercise 8 — Deployment diagnosis.** Unit tests pass, yet Lambda hits **ClassNotFoundException: FunctionInvoker**. Outline the inspection order across dependencies, shaded JAR, CodeUri, handler, and manifest.

**Exercise 9 — Transient vs. permanent errors.** A database-writing Consumer receives an SQS event with the same eventId twice. Propose an idempotency key, unique constraint, retry handling approach, and how to check appropriate partial batch responses.

### Key Takeaways

- **FunctionInvoker::handleRequest is the AWS Lambda entry point**, not the business function name. It bridges the AWS runtime with the Spring ApplicationContext and FunctionCatalog.
- **MAIN_CLASS/Start-Class identifies the Spring Boot application**, while **spring_cloud_function_definition** selects a bean or composition.
- Official documentation includes both **class-only** and **::handleRequest** handler examples; verify the syntax supported by your Java runtime and deployment tool.
- **A shaded JAR, compatible dependencies, and Spring metadata** are prerequisites for the runtime to load the handler and start the context.
- **Direct invoke, API Gateway, SQS, and S3** have different event contracts; the adapter does not automatically remove the need for conversion, retries, and trigger testing.
- Keep **Supplier/Function/Consumer** logic AWS-independent for reuse across HTTP, events, or serverless; test the runtime/handler layer separately when deploying.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, handler, routing, packaging, main class, and conversion.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): FunctionCatalog, functional model, and composition.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): RequestHandler, RequestStreamHandler, and handler naming syntax.
- [AWS Lambda — Java deployment packages](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): deploying Java JAR/ZIP and runtime.
