# Selecting a Function with the spring_cloud_function_definition Environment Variable

In **SPRING_CLOUD_FUNCTION**, an application can contain multiple **Supplier<T>**, **Function<T, R>**, and **Consumer<T>** beans. When deploying to **AWS Lambda**, the **FunctionInvoker** adapter needs to know which bean to trigger for each invocation. The **spring_cloud_function_definition** environment variable lets you select a bean name or composition chain without modifying business code, changing the handler class, or building a separate JAR for each function.

This lesson belongs to the **AWS Lambda** chapter and focuses on setting the exact key/value, the relationship between the AWS handler, main class, and **FunctionCatalog**, sharing a single JAR across multiple Lambdas, configuring via Console/SAM/AWS CLI, troubleshooting wrong function selection, and end-to-end testing. The goal is to keep functions **protocol-independent** while deploying flexibly across HTTP, events, and serverless.

## 1. Which Function Does the Environment Variable Select?

The core Spring Cloud Function property is:

~~~properties
spring.cloud.function.definition=greet
~~~

In AWS Lambda, the Spring Cloud Function documentation uses the environment variable:

~~~text
spring_cloud_function_definition=greet
~~~

Here **greet** is the **functional bean name registered by Spring**. When Lambda receives an invocation, **FunctionInvoker** uses the definition configuration, looks up the function via **FunctionCatalog**, and applies the appropriate data conversion mechanism.

~~~mermaid
flowchart LR
    A["AWS Lambda event"] --> B["FunctionInvoker"]
    C["spring_cloud_function_definition"] --> B
    B --> D["FunctionCatalog"]
    D --> E["Selected bean or composition"]
    E --> F["Output / side effect"]
~~~

This variable answers **which logic should run?**, but it does **not** automatically determine:

- Whether AWS Lambda can load the **FunctionInvoker** class from the JAR.
- Which **@SpringBootApplication** class is used to create the context.
- Whether the API Gateway, SQS, or direct invocation payload matches the schema.
- How exceptions from the Function are retried or sent to a dead-letter queue.
- Whether the Lambda has IAM permissions to read/write AWS services.

Setting the right definition is **one step in the deployment path**, not a replacement for adapters and infrastructure.

## 2. Distinguishing Handler, Main Class, Bean, and Lambda Name

Suppose we have Spring application **example.lambda.MultiFunctionApplication**, bean **greet**, and AWS Lambda **greeting-lambda**.

| Concept | Example | Meaning |
| --- | --- | --- |
| AWS Lambda resource name | **greeting-lambda** | Function identifier in AWS |
| Java handler | **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** | Entry point of the AWS runtime |
| Spring application class | **example.lambda.MultiFunctionApplication** | Configuration class used to create the Spring ApplicationContext |
| Spring function bean | **greet** | Business function in FunctionCatalog |
| Spring function definition | **greet** | Bean name selected for the invocation |

Configuration example:

~~~text
Handler = org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
MAIN_CLASS = example.lambda.MultiFunctionApplication
spring_cloud_function_definition = greet
~~~

**Do not use greet as the AWS handler.** The AWS handler must point to a class/method following the Java Lambda contract. **Do not use FunctionInvoker as MAIN_CLASS.** MAIN_CLASS specifies the Spring Boot application class. **Do not use MultiFunctionApplication as the definition**, unless the application actually registers a functional bean with that name.

The AWS adapter's generic handler can stay the same across many Lambdas; bean selection happens in **spring_cloud_function_definition**.

## 3. Example with Multiple Functional Beans

The Java 17+ code below defines five beans to compare input/output types. File **src/main/java/example/lambda/MultiFunctionApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MultiFunctionApplication {

    private static final Logger log =
        LoggerFactory.getLogger(MultiFunctionApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(MultiFunctionApplication.class, args);
    }

    public record GreetingRequest(String name) {}
    public record GreetingResponse(String message) {}

    @Bean("greet")
    Function<GreetingRequest, GreetingResponse> greet() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException("Name is required");
            }
            return new GreetingResponse(
                "Hello, " + request.name().trim());
        };
    }

    @Bean("trimText")
    Function<String, String> trimText() {
        return input -> {
            if (input == null) {
                throw new IllegalArgumentException("Input is required");
            }
            return input.trim();
        };
    }

    @Bean("uppercaseText")
    Function<String, String> uppercaseText() {
        return input -> {
            if (input == null) {
                throw new IllegalArgumentException("Input is required");
            }
            return input.toUpperCase(Locale.ROOT);
        };
    }

    @Bean("heartbeat")
    Supplier<String> heartbeat() {
        return () -> "ready";
    }

    @Bean("auditGreeting")
    Consumer<GreetingRequest> auditGreeting() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException("Name is required");
            }
            log.info("Received a valid greeting event");
        };
    }
}
~~~

All beans are registered in the Spring context, yet have different contracts:

| Bean | Type | Result / Effect |
| --- | --- | --- |
| **greet** | Function<GreetingRequest, GreetingResponse> | Produces a greeting message |
| **trimText** | Function<String, String> | Removes leading and trailing whitespace |
| **uppercaseText** | Function<String, String> | Converts to uppercase |
| **heartbeat** | Supplier<String> | Returns a status string without business input |
| **auditGreeting** | Consumer<GreetingRequest> | Writes a log, produces no business output |

**auditGreeting** only illustrates a side effect. In production systems, do not write personal data or sensitive payloads directly into logs. If a Consumer writes to a database, design appropriate idempotency, transactions, and retries.

### Is the Bean Name the Same as the Java Method Name?

In the example, **@Bean("greet")** determines the bean name. When a **@Bean** method does not state a name explicitly, Spring normally uses the method name as the bean name. If you change the annotation to **@Bean("sendGreeting")** while keeping the method named **greet()**, the definition must use **sendGreeting**, not **greet**.

Bean names referenced in deployment configurations should remain stable. Refactoring and renaming a bean can break all Lambdas still referencing the old definition.

## 4. Selecting a Function by Name

When Lambda sets:

~~~text
spring_cloud_function_definition=greet
~~~

a **direct invocation** can send a JSON object:

~~~json
{
  "name": "Lan"
}
~~~

Business result:

~~~json
{
  "message": "Hello, Lan"
}
~~~

If you change the definition to:

~~~text
spring_cloud_function_definition=uppercaseText
~~~

then a valid input for the **Function<String,String>** bean can be a **JSON string**:

~~~json
"hello"
~~~

The corresponding output has the content **HELLO**. Verify the exact serialization format in your adapter/runtime.

**The right definition does not guarantee the right payload.** If a caller still sends the object **{"name":"Lan"}** while the Function expects a String, the adapter may encounter a conversion error or unexpected data. Changing the definition changes the **input/output contract**, so corresponding callers and triggers must be tested.

## 5. Supplier and Consumer Are Also Selected by Definition

Spring Cloud Function has three primary models:

- **Supplier<T>**: **get()**, no business arguments, generates data.
- **Function<T,R>**: **apply(T)**, takes T, returns R.
- **Consumer<T>**: **accept(T)**, takes T, returns void.

With the example:

~~~text
spring_cloud_function_definition=heartbeat
~~~

Lambda selects the **Supplier<String>** bean. The runtime still delivers an invocation event, but **Supplier** does not consume business input the way a Function does.

With:

~~~text
spring_cloud_function_definition=auditGreeting
~~~

Lambda selects the **Consumer<GreetingRequest>** bean, processes the payload, and does not return a **GreetingResponse**.

**Do not expect a Consumer to produce a response DTO automatically.** If an acknowledgment result is required, consider **Function<T,ProcessingResult>**, durable state, or a response event per your contract. How the adapter represents a Consumer's empty output should be verified for each trigger.

## 6. Selecting a Composition with |

Definition does not only take a single bean name. Spring Cloud Function allows chaining compatible functions with **|**.

~~~text
spring_cloud_function_definition=trimText|uppercaseText
~~~

Pipeline:

~~~mermaid
flowchart LR
    A["Input String"] --> B["trimText"]
    B --> C["Trimmed String"]
    C --> D["uppercaseText"]
    D --> E["Uppercase String"]
~~~

With input:

~~~json
"  item-a  "
~~~

the expected output has the value **ITEM-A**.

**Requirement:** the output type of the earlier function must be compatible with the input type of the next function. **greet** returns **GreetingResponse**, whereas **uppercaseText** expects String; do not chain **greet|uppercaseText** without an intentional conversion step.

### Quoting Composition Strings in YAML and Shell

~~~yaml
Environment:
  Variables:
    spring_cloud_function_definition: "trimText|uppercaseText"
~~~

In a shell, the **|** character normally represents a pipe between two commands. Therefore, when passing a definition directly on the command line, quote it properly or use a JSON/YAML file so the shell does not misparse it. **Quoting does not alter the composition order**; it only preserves the string intact.

## 7. Sharing One JAR Across Multiple Lambdas

When **greet** and **trimText/uppercaseText** live in the same application, they can share the same shaded JAR:

~~~text
Artifact: multi-function-aws.jar
  + MultiFunctionApplication
  + FunctionInvoker
  + greet
  + trimText
  + uppercaseText
  + heartbeat
  + auditGreeting
~~~

Two separate AWS Lambdas:

~~~text
AWS Lambda "greeting-lambda"
  Handler: FunctionInvoker
  MAIN_CLASS: example.lambda.MultiFunctionApplication
  spring_cloud_function_definition: greet

AWS Lambda "normalization-lambda"
  Handler: FunctionInvoker
  MAIN_CLASS: example.lambda.MultiFunctionApplication
  spring_cloud_function_definition: trimText|uppercaseText
~~~

The two functions can use different **memory, timeout, IAM policies, triggers, and concurrency limits**. The **greet** bean and composition remain Java logic reusable over HTTP or event binders with suitable adapters.

**Sharing a JAR does not mean sharing singleton memory.** Each Lambda execution environment may create its own Spring context; static variables or in-memory caches are not synchronized between the two Lambdas or across replicas.

## 8. AWS Lambda Console: Entering Key and Value

In the Lambda Console, after uploading the right Java JAR and setting the adapter handler:

1. Open the Lambda to configure, for example **greeting-lambda**.
2. Go to the **Environment variables** configuration section.
3. Add key **spring_cloud_function_definition**, value **greet**.
4. Verify **Handler** is still **FunctionInvoker**, and **MAIN_CLASS** or **Start-Class** resolves the right Spring application.
5. Save the configuration, invoke with a payload matching the selected bean, and inspect logs.

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

Environment variables:
  MAIN_CLASS = example.lambda.MultiFunctionApplication
  spring_cloud_function_definition = greet
~~~

Menu labels may vary across AWS Console versions, yet the fields keep their roles: **Handler** is the runtime entry point, **MAIN_CLASS** helps initialize the Spring context, and **definition** specifies the bean or pipeline.

Environment variables belong to **each individual Lambda function**, not to the entire account or the JAR artifact.

## 9. AWS SAM: Same JAR, Two Definitions

Example **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GreetingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/multi-function-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.MultiFunctionApplication
          spring_cloud_function_definition: greet

  NormalizeLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/multi-function-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.MultiFunctionApplication
          spring_cloud_function_definition: "trimText|uppercaseText"
~~~

**This is an illustrative configuration**, not a complete deployment artifact:

- **CodeUri** must point to an actual shaded JAR produced by the build.
- Runtime **java21** is only appropriate if the Java bytecode and Spring dependencies are compatible.
- Handler must be verified against the adapter, Lambda runtime, and deployment tool.
- MemorySize/Timeout are examples only; IAM and triggers must be designed separately.
- When using IaC, update the definition in the YAML/Terraform source and redeploy to avoid manual configuration drift.

Spring Cloud Function AWS can use a class-only **FunctionInvoker** handler in some runtime examples. This lesson uses **FunctionInvoker::handleRequest** to illustrate the entry point clearly; do not replace it with a bean name.

### Why Should IAM Be Separated?

If **normalization-lambda** only processes strings while **greeting-lambda** is extended to access a database, do not grant database-read IAM permissions to both functions just because they share a JAR. **spring_cloud_function_definition** selects logic, but it does not change the execution role or enforce per-bean authorization.

## 10. AWS CLI: Inspecting and Updating Properly

Read the deployed Lambda configuration:

~~~bash
aws lambda get-function-configuration \
  --function-name greeting-lambda
~~~

In the output, verify:

~~~text
Handler
Runtime
Environment.Variables.MAIN_CLASS
Environment.Variables.spring_cloud_function_definition
~~~

You can update environment variables with the AWS CLI, but **update-function-configuration with Environment.Variables can replace the entire declared map**, rather than adding just one key. If you only send definition and omit MAIN_CLASS or existing variables, the configuration can break.

Example **lambda-env.json** file for hands-on practice:

~~~json
{
  "Variables": {
    "MAIN_CLASS": "example.lambda.MultiFunctionApplication",
    "spring_cloud_function_definition": "greet"
  }
}
~~~

Illustrative command:

~~~bash
aws lambda update-function-configuration \
  --function-name greeting-lambda \
  --environment file://lambda-env.json
~~~

**The lambda-env.json file is only an example for learners to create in their own project, not a file written as part of authoring this lesson.** In a real system, read the current configuration and preserve all required variables before updating; wait for the update state to complete and verify the new values.

If your organization manages Lambdas with SAM/CloudFormation/Terraform, **prefer updating the IaC source** rather than making manual CLI edits that cause configuration drift.

## 11. application.yml and Environment Variables: Which Source Takes Precedence?

In a Spring application, a default can be written in YAML:

~~~yaml
spring:
  cloud:
    function:
      definition: greet
~~~

In Lambda, you can set:

~~~text
spring_cloud_function_definition=trimText|uppercaseText
~~~

Under Spring Boot's standard externalized configuration rules, environment variables can override values in the packaged **application.yml**. However, actual precedence also depends on other configuration sources such as system properties, command-line arguments, profiles, or custom property sources.

Therefore, for an important Lambda:

- Define the beans in source code.
- Use environment variables in the deployment environment to select the bean/pipeline.
- Keep a default in application.yml only if there is a clear local/test purpose.
- Inspect the **effective definition** rather than guessing from a single file.
- Avoid putting conflicting definition values in multiple places without a controlled process.

The name **spring_cloud_function_definition** is documented for the AWS adapter; do not assume every uppercase/lowercase variant is handled identically across all integration layers. If your system uses a different naming convention, test actual binding.

## 12. Lambda Versions and Aliases Can Hold Different Configurations

Environment configuration belongs to a **Lambda function version**. A published version stores a snapshot of code/configuration and is immutable compared to unpublished configuration. Therefore, when changing the definition serving production through an alias, you should:

1. Update the environment on the mutable configuration following the deployment pipeline.
2. Run tests with the corresponding payload.
3. Publish/deploy a new version as needed.
4. Verify the alias points to the intended version.
5. Shift traffic in a controlled manner and prepare a rollback.

A Lambda alias pointing to an older version can keep using **greet** while the current unpublished configuration has already been updated to **uppercaseText**. This explains why the Console may show the new definition while invocations via an alias still execute the old function.

Do not accidentally invoke **$LATEST** when you intend to test traffic on a production alias. Explicitly specify the function name and qualifier/version/alias in your test plan.

## 13. Why Is Explicit Configuration Better Than Default Selection?

If there is only one functional bean, Spring Cloud Function may use a default discovery/selection mechanism. However, adding new beans, changing configuration, or refactoring can make function selection unpredictable.

For a Lambda deployed to serve a specific business capability, setting **spring_cloud_function_definition** explicitly helps make it:

1. **Auditable**: reading the config immediately shows which logic runs.
2. **Code-independent**: multiple Lambdas share one JAR while picking different functions.
3. **Less surprising** when the application gains additional Suppliers/Functions/Consumers.
4. **Testable** by bean name via FunctionCatalog before deployment.
5. **Easy to roll back** to a known version/configuration.

Do not rely on **@Bean** declaration order in code, Java filenames, or the Lambda resource name to infer which bean is selected.

## 14. FunctionCatalog: Testing Names Before Deployment

A Spring class can receive **FunctionCatalog** via constructor injection:

~~~java
package example.lambda;

import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class GreetingInvoker {

    private final FunctionCatalog catalog;

    public GreetingInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public MultiFunctionApplication.GreetingResponse greet(
            MultiFunctionApplication.GreetingRequest request) {

        Function<
            MultiFunctionApplication.GreetingRequest,
            MultiFunctionApplication.GreetingResponse> fn =
                catalog.lookup("greet");

        if (fn == null) {
            throw new IllegalStateException(
                "Function 'greet' not registered");
        }

        return fn.apply(request);
    }
}
~~~

FunctionCatalog can return wrappers for conversion, composition, and message handling. Therefore, do not assume the looked-up object is always the exact same instance/class as the bean implementation.

You can look up a composition of two String Functions:

~~~java
Function<String, String> pipeline =
    catalog.lookup("trimText|uppercaseText");

if (pipeline == null) {
    throw new IllegalStateException("Pipeline not found");
}

String output = pipeline.apply("  item-a  ");
// "ITEM-A"
~~~

The second snippet illustrates a context where **FunctionCatalog catalog** has already been injected by Spring; it is not a standalone Java file.

If the catalog cannot find **greet**, the problem may be a wrong bean name, the configuration class being outside component scan, or misconfigured Spring Cloud Function dependencies.

## 15. Direct Java Tests Do Not Prove Lambda Picks the Right Definition

### 15.1. Logic Unit Tests

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MultiFunctionApplicationTest {

    private final MultiFunctionApplication app =
        new MultiFunctionApplication();

    @Test
    void greetReturnsExpectedMessage() {
        var response = app.greet().apply(
            new MultiFunctionApplication.GreetingRequest(" Lan ")
        );
        assertEquals("Hello, Lan", response.message());
    }

    @Test
    void greetRejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
            () -> app.greet().apply(
                new MultiFunctionApplication.GreetingRequest(" ")
            ));
    }

    @Test
    void twoFunctionsCanBeComposed() {
        String trimmed = app.trimText().apply("  item-a  ");
        String upper = app.uppercaseText().apply(trimmed);
        assertEquals("ITEM-A", upper);
    }
}
~~~

The tests above verify business logic, not bean registration or Lambda environment variables.

### 15.2. Spring FunctionCatalog Integration Test

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = MultiFunctionApplication.class)
class FunctionCatalogSelectionTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void namedFunctionsExist() {
        assertNotNull(catalog.lookup("greet"));
        assertNotNull(catalog.lookup("trimText"));
        assertNotNull(catalog.lookup("uppercaseText"));
    }

    @Test
    void compositionRunsInOrder() {
        Function<String, String> chain =
            catalog.lookup("trimText|uppercaseText");

        assertNotNull(chain);
        assertEquals("ITEM-A", chain.apply("  item-a  "));
    }
}
~~~

Integration tests prove the context contains the beans and the catalog can look them up. To verify the environment variables of **a deployed Lambda**, check its actual configuration/version and run a corresponding invocation.

### 15.3. Inspecting the Artifact

The AWS Lambda Java runtime must be able to load **FunctionInvoker** and the main class from the deployable JAR:

~~~bash
jar tf target/multi-function-1.0.0-aws.jar |
  grep 'FunctionInvoker.class'

jar tf target/multi-function-1.0.0-aws.jar |
  grep 'MultiFunctionApplication.class'
~~~

These are example commands, not to be run as part of STEP 4 while authoring this lesson. If the artifact is missing the handler, fix dependencies/packaging rather than changing the definition.

## 16. Testing AWS Lambda After Deployment

Example invocation to the Lambda selecting **greet**:

~~~bash
aws lambda invoke \
  --function-name greeting-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '{"name":"Lan"}' \
  response.json

cat response.json
~~~

For the Lambda selecting **trimText|uppercaseText**:

~~~bash
aws lambda invoke \
  --function-name normalization-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '"  item-a  "' \
  response.txt

cat response.txt
~~~

These commands only show how to test in an AWS environment with credentials and invoke permissions. **A successful Lambda API call does not mean the Function had no errors**: check metadata such as **FunctionError**, response contents, and CloudWatch logs.

A checklist for verifying results:

- Are you invoking the right Lambda, version, or alias?
- Does the environment have the exact **spring_cloud_function_definition**?
- Does Handler point to **FunctionInvoker** and is the main class right?
- Does the input event match the contract of the selected bean?
- Are there any conversion, validation, exception, or timeout errors?
- Does the actual output match the selected logic?

## 17. Event Envelopes Cannot Be Changed by Definition Alone

A direct invocation receiving a JSON object like **{"name":"Lan"}** differs from events emitted by API Gateway, SQS, S3, or EventBridge.

| Source | Typical Contents | What to Handle |
| --- | --- | --- |
| Direct invoke | Caller-supplied payload | Deserialize into DTO |
| API Gateway | **body**, headers, requestContext | Read body and map HTTP response |
| SQS | **Records** and potentially multiple messages | Batching, retries, partial failure |
| S3 | Bucket, key, event metadata | Object retrieval, access rights, idempotency |
| EventBridge | **source**, **detail-type**, **detail** | Map event detail to contract |

**spring_cloud_function_definition** only selects the function; it does **not** unwrap every event envelope into a business DTO. If a Function expects **GreetingRequest** while the actual trigger sends **SQSEvent**, you need an appropriate input type or conversion adapter rather than merely changing the bean name in the environment.

For Consumers with side effects, design retries and idempotency because Lambda/brokers may redeliver the same event. An environment variable cannot guarantee exactly-once processing.

## 18. Error Scenarios and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Lambda cannot find **FunctionInvoker** | Wrong JAR or missing AWS adapter | Check shaded JAR/handler |
| Lambda cannot find main class | Wrong **MAIN_CLASS** or Start-Class | Check fully qualified class name, manifest |
| Catalog cannot find bean | Wrong definition or bean not registered | Cross-check @Bean and lookup |
| Lambda runs a different bean than expected | Env on a different version/alias | Run get-function-configuration with exact qualifier |
| Composition fails | Typo in one name or incompatible data types | Test lookup("a|b") and T/R |
| **\|** treated as a pipe by the shell | Value not quoted | Quote the value or use JSON/YAML file |
| CLI update wipes other variables | Variables map replaced | Read current config first, send full map |
| IaC deploy overwrites Console changes | Drift between Console and IaC | Edit IaC source configuration |
| JSON parse fails | Payload does not match generic input | Check schema and adapter |
| Function is invoked but throws exception | Invalid data or business error | Classify validation/business errors |
| Supplier does not take input like Function | Supplier has no business parameter | Design invocation accordingly |
| Consumer has no DTO output | Consumer returns void | Use Function if a result is needed |
| SQS trigger redelivers events | Retry/redelivery | Use eventId, unique constraint, DLQ per policy |
| IAM AccessDenied | Role lacks permissions | Grant appropriate least-privilege permissions |
| Incompatible Java version | Bytecode/runtime mismatch | Align compiler release and Runtime |

**A helpful diagnostic order:** can the handler load → does the Spring context initialize → does FunctionCatalog find the right bean → does the converter understand the event → does the logic succeed.

## 19. Security and Operations When Changing Definitions

Changing the definition can change what a Lambda does even without changing the JAR. Therefore, treat it as a **deployment behavior change**:

- Manage through review and Infrastructure as Code.
- Test in staging with contract-compliant inputs/outputs.
- Use versions and aliases for controlled rollouts/rollbacks.
- Monitor logs, errors, cold starts, duration, and business metrics.
- Do not use definition as an authorization mechanism in place of IAM/authorization.
- Do not allow untrusted callers to pick sensitive beans arbitrarily via uncontrolled routing.
- Do not place credentials or raw secrets in environment variables or logs.

A Lambda execution environment may reuse Spring singletons, yet multiple instances do not share memory. Do not store durable state or idempotency keys solely in fields of a Function bean if the workload must remain safe across scaling/restarts.

## 20. Applied Exercises

**Exercise 1 — Distinguishing three names.** An application has class **com.shop.PricingApplication**, bean **@Bean("calculatePrice")**, and Lambda name **price-prod**. Specify the exact Handler, MAIN_CLASS, and spring_cloud_function_definition, then explain why they must not be swapped.

**Exercise 2 — Two Lambdas sharing a JAR.** Create two beans **reverseText** and **uppercaseText**. Write a SAM template defining two Lambdas with the same Handler/CodeUri/MAIN_CLASS but different definitions. What test event does each Lambda need?

**Exercise 3 — Composition.** With **trimText** and **uppercaseText**, configure a definition using **|**, send a JSON string containing whitespace, and verify the final output with both a unit test and a FunctionCatalog test.

**Exercise 4 — Contract mismatch.** A Lambda selects **greet** expecting **GreetingRequest**, but API Gateway sends an event containing **body**. Distinguish a definition error from an envelope conversion error and design the proper mapping.

**Exercise 5 — AWS CLI.** A Lambda has three environment variables, including MAIN_CLASS and definition. Plan how to update definition without losing the remaining variables, then use get-function-configuration to verify.

**Exercise 6 — Version/alias.** New configuration selects **uppercaseText**, yet the production alias still points to a version selecting **greet**. Describe how to check the active version, roll out, and roll back.

**Exercise 7 — Supplier and Consumer.** Create **Supplier<String> heartbeat** and **Consumer<Event> auditEvent**, and deploy them as two Lambdas selecting the respective definitions. Explain why one has no business input and the other has no business output.

**Exercise 8 — Event retries.** A Lambda selecting a database-writing Consumer receives the same eventId again from SQS. Propose an idempotency key, unique constraint, retry/dead-letter handling, and explain why selecting the right bean alone is not enough.

### Key Takeaways

- **spring_cloud_function_definition** selects the **functional bean or composition** in Spring Cloud Function; it is neither the AWS handler nor the Spring main class.
- **FunctionInvoker** remains the Lambda entry point; **MAIN_CLASS/Start-Class** identifies the Spring application; **FunctionCatalog** locates logic by definition.
- One **shaded JAR** can serve multiple Lambdas with separate definitions, IAM roles, triggers, timeouts, and versions.
- Composition uses **|** in order; quote it in shell/YAML and ensure data types between steps are compatible.
- Changing the definition can change the input/output contract. Verify the event envelope, effective environment, Lambda version/alias, and post-deployment tests.
- Manage configuration via IaC and prepare rollbacks for controlled changes to Lambda logic.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, environment variables, definition, routing.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): FunctionCatalog, programming model, composition.
- [AWS Lambda — Environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html): environment and versions.
- [AWS CLI — update-function-configuration](https://docs.aws.amazon.com/cli/latest/reference/lambda/update-function-configuration.html): updating environment variables.
