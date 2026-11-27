# Routing Multiple Functions Through One Lambda or Separate Lambdas

A **SPRING_CLOUD_FUNCTION** project can contain multiple **Supplier<T>**, **Function<T, R>**, and **Consumer<T>** beans, yet when deploying to **AWS Lambda**, you must decide how those beans map to actual AWS resources. There are two main approaches: **one Lambda receiving multiple request types and routing to the appropriate function**, or **multiple independent Lambdas, each pinned to a single function or pipeline**. Both can use **FunctionInvoker** and **FunctionCatalog**, but they differ in where routing decisions are made, isolation capabilities, IAM permissions, concurrency, operational overhead, and data contracts.

This lesson belongs to the **AWS Lambda** chapter. After this lesson, you can explain three deployment strategies, configure **spring_cloud_function_definition**, use **RoutingFunction/functionRouter**, Message headers, or **MessageRoutingCallback** when per-invocation routing is needed, write a safe adapter layer for AWS events, build an AWS SAM template, and test each path. The goal is to keep business logic reusable independently of HTTP, events, or serverless environments.

## 1. Three Deployment Models to Distinguish

The phrase "multiple functions" can refer to **Java beans**, **AWS Lambda functions**, or both. Here are three concrete architectures:

| Architecture | Lambda resource | JAR/code package | How function is chosen |
| --- | --- | --- | --- |
| **A. One Lambda, dynamic routing** | One | One JAR with multiple beans | Per invocation, via router or adapter layer |
| **B. Multiple Lambdas, same JAR** | Multiple | Same JAR containing the beans | Each Lambda selects statically via environment |
| **C. Multiple Lambdas, separate JARs** | Multiple | Separate artifact per Lambda | Chosen in each separate app/definition |

~~~mermaid
flowchart TB
    S["One codebase with Function beans"] --> A["A: Single Lambda"]
    S --> B["B: Multiple Lambdas sharing JAR"]
    S --> C["C: Multiple independent Lambdas/JARs"]
    A --> A1["Router picks bean per event"]
    B --> B1["Static env var per Lambda"]
    C --> C1["Each artifact contains only what it needs"]
~~~

Model A fits when operations are **closely related**, sharing permissions and infrastructure configuration. B fits when operations share code yet need **separate IAM, event source mappings, timeouts, or scaling profiles**. C fits when each operation is owned by different teams with separate release cycles and dependency sets.

**A single JAR containing multiple beans does not mean you can only create one Lambda.** Conversely, an AWS Lambda resource does not automatically know which bean inside the JAR to call without an appropriate definition or routing rule.

## 2. The Shared Path with FunctionInvoker

Whether choosing A or B, the standard integration approach is using the handler provided by **spring-cloud-function-adapter-aws**.

~~~text
AWS Lambda handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

Spring Boot main class:
  example.lambda.RoutingLambdaApplication

Bean names in FunctionCatalog:
  uppercase, lowercase, reverse, dispatchText, functionRouter
~~~

**Handler** is the Lambda runtime entry point; **main class** initializes the Spring application context; **bean name** identifies logic inside the context. Do not use **uppercase** as the AWS handler, and do not use **FunctionInvoker** as a business bean name.

~~~mermaid
sequenceDiagram
    participant AWS as AWS runtime
    participant INV as FunctionInvoker
    participant CAT as FunctionCatalog
    participant F as Function bean

    AWS->>INV: handleRequest(event, Context)
    INV->>CAT: lookup(definition / router)
    CAT-->>INV: wrapped Function
    INV->>F: apply(input)
    F-->>INV: output
    INV-->>AWS: serialized result
~~~

When multiple beans exist, explicitly select a definition or a router. Do not rely on the declaration order of **@Bean** methods in source code. Fallback behavior when no definition is provided can vary by framework version and bean count.

## 3. Spring Boot Example: Reusable Transformations

We create three string-processing functions **uppercase**, **lowercase**, and **reverse**, plus a **dispatchText** bean that accepts an envelope containing an **operation** field and selects a function via an allowlist. The example uses Java 17+.

File **src/main/java/example/lambda/RoutingLambdaApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RoutingLambdaApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingLambdaApplication.class, args);
    }

    // Dedicated contract for the Lambda acting as a gateway.
    public record TextCommand(
        String operation,
        String value
    ) {}

    public record TextResult(
        String operation,
        String value
    ) {}

    @Bean("uppercase")
    Function<String, String> uppercase() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    @Bean("lowercase")
    Function<String, String> lowercase() {
        return text -> text.toLowerCase(Locale.ROOT);
    }

    @Bean("reverse")
    Function<String, String> reverse() {
        return text -> new StringBuilder(text).reverse().toString();
    }

    // This is an explicit application router, NOT
    // Spring Cloud Function's default RoutingFunction.
    @Bean("dispatchText")
    Function<TextCommand, TextResult> dispatchText(
            @Qualifier("uppercase") Function<String, String> upper,
            @Qualifier("lowercase") Function<String, String> lower,
            @Qualifier("reverse") Function<String, String> reversing) {

        return request -> {
            if (request == null
                    || request.operation() == null
                    || request.value() == null) {
                throw new IllegalArgumentException(
                    "operation and value are required");
            }

            String operation = request.operation()
                .trim().toLowerCase(Locale.ROOT);

            // Allow only the three public operations.
            String result = switch (operation) {
                case "upper" -> upper.apply(request.value());
                case "lower" -> lower.apply(request.value());
                case "reverse" -> reversing.apply(request.value());
                default -> throw new IllegalArgumentException(
                    "Unsupported operation");
            };

            return new TextResult(operation, result);
        };
    }
}
~~~

Key points:

1. All three **uppercase/lowercase/reverse** beans have the **Function<String, String>** contract and can be tested independently.
2. **dispatchText** is a separate **Function<TextCommand, TextResult>**; it decides the path based on the converted business input.
3. **@Qualifier** helps Spring inject the right three beans that share the same generic type.
4. The **switch** acts as an **allowlist**: callers can only select the three public operations rather than passing arbitrary bean names straight into the catalog.
5. The gateway input/output DTOs do not depend on Lambda or HTTP APIs.
6. In production systems, permission to execute an operation must be checked separately; an allowlist only restricts routes and does not replace authentication/authorization.

**Distinction:** the **dispatchText** example is a **hand-written Java router**. Spring Cloud Function also provides **RoutingFunction** named **functionRouter** to route based on Message headers, application properties, or callbacks; that second mechanism is explained next.

## 4. Approach A — One Lambda with an Explicit Business Router

If all operations are string transformations sharing configuration, timeout, and permissions, you can deploy **a single AWS Lambda** accepting **TextCommand**.

~~~text
AWS Lambda: text-gateway
  Handler: FunctionInvoker
  MAIN_CLASS: example.lambda.RoutingLambdaApplication
  spring_cloud_function_definition: dispatchText
~~~

A direct invocation sends:

~~~json
{
  "operation": "upper",
  "value": "Hello Lambda"
}
~~~

Business result:

~~~json
{
  "operation": "upper",
  "value": "HELLO LAMBDA"
}
~~~

Same Lambda, next request:

~~~json
{
  "operation": "reverse",
  "value": "abc-123"
}
~~~

produces:

~~~json
{
  "operation": "reverse",
  "value": "321-cba"
}
~~~

~~~mermaid
flowchart LR
    A["Lambda text-gateway"] --> B["dispatchText"]
    B --> C{"operation"}
    C -- "upper" --> D["uppercase"]
    C -- "lower" --> E["lowercase"]
    C -- "reverse" --> F["reverse"]
    D --> G["TextResult"]
    E --> G
    F --> G
~~~

The **spring_cloud_function_definition** value here is **dispatchText** and does not change between invocations. **TextCommand.operation itself handles internal function selection**. This is a simple, testable approach for a unified JSON contract.

### Why Not Use an Environment Variable to Switch Routes per Request?

A Lambda environment variable is a **function/version-level** configuration, not a per-invocation parameter. If you set:

~~~text
spring_cloud_function_definition=uppercase
~~~

then that function is selected statically at the adapter level per the active configuration. Do not update the AWS environment variable before each request to switch between uppercase and lowercase; that modifies deployment configuration, adds latency, causes concurrency conflicts, and is unsuitable for per-request routing.

A Lambda serving multiple actions needs **dynamic routing based on the event or metadata**, either through an adapter like **dispatchText** or the framework's **functionRouter** mechanism.

## 5. Advanced Approach A — Spring Cloud Function's RoutingFunction

Spring Cloud Function registers a default router named:

~~~text
functionRouter
~~~

The corresponding class is **RoutingFunction**, with the generic contract **Function<Object, Object>**. The router takes an input accompanied by routing metadata and selects the function definition to invoke from **FunctionCatalog**.

Ways to provide routing instructions include:

- A **Message header** with key **spring.cloud.function.definition** and value equal to a bean name or composition.
- A **Message header** **spring.cloud.function.routing-expression** using a Spring Expression Language (SpEL) expression.
- An **application/system property**, suited for static routing logic selection.
- A **MessageRoutingCallback**, a custom strategy registered as a Spring bean.

~~~mermaid
flowchart TD
    A["Incoming Message"] --> B["functionRouter"]
    C["Header / callback / property"] --> B
    B --> D{"Definition"}
    D --> E["uppercase"]
    D --> F["lowercase"]
    D --> G["reverse"]
~~~

An important point: **FunctionInvoker** may default to **functionRouter** when there is no way to select a single function, but you should not treat this as a substitute for explicit routing design. In projects with multiple beans, configure intentionally and test how your adapter version resolves the router.

### Testing the Router Directly with a Message Header

You can use **FunctionCatalog** to test the router independently of AWS:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(classes = RoutingLambdaApplication.class)
class FrameworkRoutingTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void routePerMessageUsingHeader() {
        Function<Object, Object> router =
            catalog.lookup("functionRouter");

        assertNotNull(router);

        Message<String> message =
            MessageBuilder.withPayload("Hello")
                .setHeader(
                    "spring.cloud.function.definition",
                    "uppercase")
                .build();

        Object result = router.apply(message);

        // The result may be a raw payload or a Message
        // depending on the wrapper and integration path.
        Object value = result instanceof Message<?> output
            ? output.getPayload()
            : result;

        assertEquals("HELLO", value);
    }
}
~~~

This test illustrates an **imperative Function** and a **Message** with an **explicitly** added routing header. The input of **functionRouter** differs from a business Function with a fixed DTO signature; you may need to verify conversion and output wrappers for your specific Spring Cloud Function version.

**Special warning when using AWS:** sending JSON containing a field named **headers** does not mean the AWS adapter automatically converts that field into **Spring MessageHeaders**. Converting API Gateway headers, SQS message attributes, or event fields into Spring headers must be **verified or implemented in an adapter layer**. Without a reliable mapping step, the **dispatchText** approach in Section 4 offers a clearer contract for direct invocations.

## 6. RoutingFunction with a Route-Controlling Callback

**MessageRoutingCallback** allows application code to determine the function name from a **Message<?>** rather than trusting a bean name supplied directly by the caller.

Example configuration snippet for current-generation Spring Cloud Function, where the callback returns **String**:

~~~java
import org.springframework.cloud.function.context.MessageRoutingCallback;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration(proxyBeanMethods = false)
class TrustedRoutingConfiguration {

    @Bean
    MessageRoutingCallback trustedRouter() {
        return new MessageRoutingCallback() {
            @Override
            public String routingResult(Message<?> message) {
                Object action = message.getHeaders()
                    .get("trustedAction");

                if ("upper".equals(action)) {
                    return "uppercase";
                }
                if ("lower".equals(action)) {
                    return "lowercase";
                }
                if ("reverse".equals(action)) {
                    return "reverse";
                }
                throw new IllegalArgumentException(
                    "Unsupported trusted action");
            }
        };
    }
}
~~~

**Use this example only when the trustedAction header is generated/controlled by an adapter or trusted authentication layer.** This is an **optional configuration snippet** illustrating an alternative routing mechanism. Do not add it to the Section 3 application and expect **spring.cloud.function.definition** Message header tests to keep taking precedence as before: the callback has higher priority and can override routing outcomes.

**API version note:** older Spring Cloud Function versions may use a callback signature returning **FunctionRoutingResult** instead of String. Check the JavaDoc/source and examples for the exact dependency version pinned in your build before copying callback code.

### Why Control Routes?

If callers are allowed to pass directly:

~~~text
spring.cloud.function.definition=deleteAllRecords
~~~

and **functionRouter** obeys without an authorization layer, a sensitive internal bean can be invoked unintentionally. This is an **authorization** risk, not a syntax error.

Solution: define an allowlist of operations allowed to be exposed; authenticate callers at API Gateway or a trusted boundary; map public routes/actions to internal bean names via code or managed configuration; never allow untrusted callers to specify arbitrary beans.

## 7. Routing via SpEL: Flexible but Needs Guardrails

Spring Cloud Function also supports the **spring.cloud.function.routing-expression** property. When used on AWS Lambda, documentation shows the environment variable form:

~~~text
spring_cloud_function_routingExpression
~~~

This is an **environment variable key**, not a bean name. Example of an admin-configured expression selecting a function from a header attached by an adapter:

~~~properties
spring.cloud.function.routing-expression=headers['trustedAction']=='upper' ? 'uppercase' : 'lowercase'
~~~

The expression above assumes a context that already has **Spring Message headers**. With raw JSON Lambda invocations, a header-mapping step is needed before assuming **headers['trustedAction']** exists.

According to Spring Cloud Function documentation:

1. SpEL from a **Message header** is evaluated in a **SimpleEvaluationContext** with restricted capabilities.
2. SpEL from an **application/system property** may use a more powerful **StandardEvaluationContext**, so the expression source must be protected.
3. Routing versions/mechanisms may have different precedence rules; when a callback is present, the callback takes precedence over headers/properties for imperative functions.

**Never feed arbitrary client-supplied SpEL expressions into a privileged configuration context.** Use only vetted expressions and thoroughly test error branches. When there are only a few operations, a **switch allowlist** or **MessageRoutingCallback** is usually easier to audit.

## 8. Precedence Order of Routing Mechanisms

For **imperative functions** and the **RoutingFunction** mechanism per Spring Cloud Function documentation, the precedence order when multiple instructions are present is:

| Priority | Mechanism | Meaning |
| --- | --- | --- |
| **1 — highest** | **MessageRoutingCallback** | Policy in the callback bean decides the route |
| **2** | **Message headers** | Function name or SpEL carried with the Message |
| **3** | **Application properties** | Instructions from application/environment configuration |

For example, if a callback always returns **uppercase**, a Message header requesting **lowercase** will not necessarily be honored. Therefore, when testing **functionRouter** via headers, do not simultaneously register a callback with different logic and conclude the framework "ignored" the header due to a bug.

For **reactive functions** accepting a **Publisher** such as **Flux<T>**, the unit of work is the publisher, not individual messages. Documentation only supports reactive routing via **application properties**, and does not guarantee per-message routing by header. If you need per-event routing, consider an **imperative** path or splitting into appropriate pipelines.

## 9. Approach B — Multiple Independent Lambdas Sharing One JAR

If three actions have different permissions, triggers, or operational parameters, instead of one dynamically dispatching Lambda, you can deploy **three Lambda resources** sharing the JAR that contains all three beans:

~~~text
JAR: routing-lambda-1.0.0-aws.jar
  RoutingLambdaApplication
  uppercase bean
  lowercase bean
  reverse bean
  dispatchText bean
  Spring Cloud Function adapter

Lambda uppercase-lambda:
  spring_cloud_function_definition = uppercase

Lambda lowercase-lambda:
  spring_cloud_function_definition = lowercase

Lambda reverse-lambda:
  spring_cloud_function_definition = reverse
~~~

~~~mermaid
flowchart TB
    A["One shaded JAR"] --> B["uppercase-lambda"]
    A --> C["lowercase-lambda"]
    A --> D["reverse-lambda"]
    B --> E["definition = uppercase"]
    C --> F["definition = lowercase"]
    D --> G["definition = reverse"]
~~~

In this approach, **definition is fixed at each Lambda resource level**. With the same JAR and the same **FunctionInvoker** handler, each Lambda exposes only the invocation path chosen by its environment configuration.

### Advantages of Splitting into Multiple Lambdas

- You can grant **separate IAM execution roles** per capability, avoiding broad permissions on a single gateway.
- You have independent **memory/timeout/concurrency** so heavy workloads do not affect the function-level quotas of lightweight workloads in the same way.
- You can attach separate **SQS/Kinesis/EventBridge/S3** event source mappings per business flow.
- You get separate CloudWatch logs, metrics, alarms, versions, and aliases at the Lambda resource level.
- It is easy to roll back or disable one capability without altering dynamic routing for others.

**Limitation:** even though AWS resources are independent, sharing an artifact means a JAR update affects the codebase of every Lambda redeployed with the new artifact. Moreover, a JAR containing all beans may cause Spring to initialize dependencies unnecessary for a specific Lambda, depending on the application's lazy/conditional configuration.

## 10. AWS SAM Example for Multiple Lambdas Sharing a JAR

Illustrative **template.yaml** file:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  UppercaseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/routing-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.RoutingLambdaApplication
          spring_cloud_function_definition: uppercase

  LowercaseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/routing-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.RoutingLambdaApplication
          spring_cloud_function_definition: lowercase

  ReverseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/routing-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.RoutingLambdaApplication
          spring_cloud_function_definition: reverse
~~~

Explanation:

- **Handler** is the shared adapter class, matching SAM examples in the official documentation. When configuring in the AWS Console, documentation also illustrates **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest**.
- **CodeUri** points to the same **shaded JAR**. The filename is a sample; replace it with the actual built artifact.
- **MAIN_CLASS** identifies the Spring Boot application. If the JAR has a compatible **Start-Class** manifest entry, this env var may be unnecessary.
- **spring_cloud_function_definition** pins the bean invoked for each Lambda.
- **Runtime** and MemorySize/Timeout values are illustrative only; they must fit your Java bytecode, Spring version, and workload.

Each Lambda has its own permissions, triggers, and logs. The example does not yet declare IAM or event sources; add them as needed rather than assuming SAM automatically grants all business permissions.

### When to Use a Static Composition?

A Lambda can also select:

~~~yaml
Environment:
  Variables:
    spring_cloud_function_definition: "trimText|uppercase"
~~~

but only when both **trimText** and **uppercase** are valid beans and the output type of the previous step matches the input type of the next step. The **|** chain is a **static composition** for that Lambda, not dynamic per-request branching.

## 11. Approach C — Multiple Lambdas and Separate Artifacts

As a system grows, you can split the codebase or modules into distinct application/function artifacts:

~~~text
order-query-lambda.jar      -> queryOrder
payment-command-lambda.jar -> processPayment
audit-event-lambda.jar     -> recordAudit
~~~

Benefits can include:

- Each deployment carries only the dependencies and beans required for its business logic.
- Teams can version and release independently.
- Infrastructure permissions, test suites, and startup configuration are cleanly separated.
- A dependency change for payment processing does not necessarily affect the order-query Lambda.

In return, the project must manage more modules/build pipelines, inter-service contracts, shared libraries, versioning, and distributed observability. **Splitting JARs does not mean Java logic cannot be reused**: you can place shared DTOs, services, and business policies in a versioned Java library while each Lambda registers only the Functions it needs.

Do not split every tiny operation into its own repository merely to have multiple Lambdas. Weigh ownership, business cohesion, and operational needs.

## 12. When to Choose One Lambda vs. Multiple Lambdas?

| Criterion | One Dynamically Routed Lambda | Multiple Independent Lambdas |
| --- | --- | --- |
| **IAM permissions** | Execution role shared across branches | Can grant separate permissions |
| **Memory/timeout** | Same configuration at Lambda level | Tuned per function |
| **Reserved concurrency** | Same limit at Lambda level | Can be set separately |
| **Event triggers** | Must distinguish and map multiple event types | Dedicated event source mapping per Lambda |
| **API entrypoint** | One convenient unified endpoint | Multiple integrations or API routes |
| **Route selection** | Per invocation | Typically static via definition |
| **Code complexity** | Includes router, allowlist, error mapping | More infrastructure, less dynamic routing |
| **Security** | Must enforce permissions per branch | Better isolation at IAM/function boundaries |
| **Deploy/rollback** | One Lambda version contains all branches | Can version/roll back each Lambda individually |
| **Cold start** | Consecutive branches can benefit from warm environment | Each Lambda has its own cold starts |
| **Blast radius** | Router or shared dependency bug affects all branches | Better separated, though shared JAR still couples |

**There is no universally right choice.** If branches share permissions, data stores, and load profiles and need a single simple endpoint, **one Lambda** can make sense. If one branch needs S3 read access while another writes to DynamoDB, or workloads have very different execution durations, **multiple Lambdas** usually provide better isolation.

Spring Cloud Function AWS documentation also highlights using multiple Lambdas with **separate event source mappings** for messaging-driven applications, because message consumption and processing settings typically depend on the event source.

## 13. One Lambda Receiving Multiple Event Types: Do Not Confuse Payload with Metadata

A common pitfall in Approach A is assuming every AWS event automatically contains a **Spring Message header** readable by functionRouter.

### Direct Invoke with an Application-Designed Envelope

For the **dispatchText** bean, a direct event has the structure:

~~~json
{
  "operation": "lower",
  "value": "MiXeD"
}
~~~

The Lambda adapter can deserialize it into **TextCommand**, after which the application router reads **operation** and invokes **lowercase**.

### API Gateway Events Have Their Own Envelope

An API Gateway proxy event typically includes metadata such as **headers**, **requestContext**, and **body**. The body may be a JSON string:

~~~json
{
  "rawPath": "/text/upper",
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"value\":\"Hello\"}",
  "isBase64Encoded": false
}
~~~

This is only a simplified illustration of the envelope; verify the exact API Gateway REST/HTTP API payload version and real event contract.

**You cannot assume a direct Function<TextCommand, TextResult> always unwraps an API Gateway body automatically**. You need an adapter or a function accepting the matching AWS event type to read route/path, parse the body, validate, convert to TextCommand, and map the result into a response matching the API Gateway contract.

### SQS/S3 Are Different Too

- **SQS:** events have **Records** and can batch multiple messages; partial failures and per-record retries are critical concerns.
- **S3:** events contain bucket/key and typically require calling an API to read the object; IAM permissions and duplicate-processing prevention are required.
- **EventBridge:** events have **detail**, **source**, **detail-type**, and related metadata.

**Routing for business requests does not solve event-source integration by itself.** When one Lambda handles multiple event sources, design an explicit adapter layer to identify verified event types and translate them into respective business payloads.

## 14. Securing Routing: Never Accept Bean Names Directly from Clients

A codebase may contain beans for public APIs, batch jobs, auditing, admin tasks, or data deletion. If callers are allowed to pass arbitrary bean names that the router looks up and executes, an internal capability can be exposed unintentionally.

### Pattern to Avoid

~~~text
Client sends:
  {"function":"deleteAllOrders", "payload": {...}}

Adapter:
  catalog.lookup(userInput.function).apply(userInput.payload)
~~~

This is unsafe whenever the client is untrusted. **Never pass untrusted input directly as a function definition**.

### Safer Pattern

~~~text
Public operation "upper"   -> internal bean uppercase
Public operation "lower"   -> internal bean lowercase
Public operation "reverse" -> internal bean reverse

Any other operation -> reject
~~~

Beyond an allowlist, you still need:

1. **Authentication** at API Gateway/authorizer or an appropriate trust mechanism.
2. **Authorization** per operation, resource, and tenant; an allowlist alone is insufficient.
3. **Input validation** and payload size limits.
4. **Least-privilege IAM** for the Lambda execution role.
5. **Observability** logging the selected route without exposing sensitive data.
6. **Never evaluate arbitrary client-supplied SpEL expressions** in a privileged context.

This is even more critical with **a single Lambda**: all branches typically share one execution role, so a flaw in the router or one branch can affect any resource accessible to that role.

## 15. Missing Route Errors: Reject or Fallback?

If the target route does not exist in FunctionCatalog, **functionRouter** typically raises an error. Spring Cloud Function also has **DefaultMessageRoutingHandler** to handle unroutable messages; one default behavior may be logging and ignoring them.

For business systems, **silently ignoring** can be very dangerous, especially when messages carry payment commands or state updates. Choose an explicit policy:

| Scenario | Behavior to Consider |
| --- | --- |
| Unknown operation sent by caller | Return a validation/authorization error with a clear code |
| Misconfigured missing bean | Fail the deployment rather than pretending to succeed |
| SQS message with no valid route | Reject/quarantine/DLQ per source policy |
| Downstream transient error | Bounded retry with backoff |
| Business rejection | Return contract decision/result or report error appropriately |

**Fallback must not automatically mean "processed successfully"**. With brokers, that can cause a message to be acknowledged without executing business logic. Test actual adapter and event source mapping semantics.

## 16. Retries, Idempotency, and Transactions Across Branches

A pure string-processing Function like **uppercase** can be invoked repeatedly without side effects. However, if a router branches to **recordAudit**, **chargePayment**, or **updateInventory**, system characteristics change completely.

~~~mermaid
flowchart TD
    A["Event received from source"] --> B["Router"]
    B --> C{"Operation"}
    C --> D["Read-only Function"]
    C --> E["Write Consumer/Function"]
    E --> F["Database/external API"]
    F --> G["Response / Ack"]
~~~

If the source redelivers an event after a timeout or failed acknowledgment, a data-writing operation can execute repeatedly. **Idempotency must be guaranteed where side effects occur**, not only in the router:

- Every event/command should carry a stable **idempotency key**.
- The database can enforce a **unique constraint**/transaction on the event ID or business key.
- For workflows that write data and then emit messages, consider an **outbox** or appropriate transactional mechanism.
- Configure retries/backoff/DLQ per AWS source and distinguish permanent errors from transient ones.
- Do not use an in-JVM singleton HashMap as a durable idempotency store across restarts or multiple replicas.

When using multiple independent Lambdas, each function can have its own retry policy, timeout, and event source mapping. When using a single Lambda for multiple operations, **Lambda/trigger-level policies may be shared**, so evaluate whether that offers enough flexibility.

## 17. Cold Starts, Scaling, and Operational Cost

### Single Lambda

A single Lambda can reuse the initialized application context and dependencies across consecutive invocations in the same execution environment. If related functional branches are called back-to-back, they **may** benefit from an existing warm environment.

However:

- There is no guarantee two invocations run on the same environment.
- As traffic rises, AWS can still spin up additional environments and incur cold starts.
- One heavy branch can impact the latency/cost of lightweight branches because they share the same code/package and function-level settings.
- Reserved concurrency, memory, and timeout are typically configured at the resource level, not per Java bean.

### Multiple Lambdas

Multiple Lambdas can choose separate memory/timeout/concurrency settings, and each function has its own metrics and alarms. However, each Lambda has its own initialization environment and warm pool; under low traffic, one Lambda cannot reuse another Lambda's warm JVM.

### What Are the Downsides of Sharing a JAR?

An artifact holding many dependencies/beans can be larger and have more complex startup than a minimal, capability-specific JAR. Still, do not guess cold-start differences from bean counts alone: measure **Init Duration**, **Duration**, memory usage, and dependency initialization on realistic workloads.

**Do not use singleton caches/fields to share state between Lambdas**. Each execution environment is a separate memory space; use a database, distributed cache, or messaging when business logic requires shared state.

## 18. Unit Testing an Explicit Router

Because **dispatchText** is a Java Function accepting DTOs, it can be tested without starting Spring or AWS.

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DispatchTextUnitTest {

    private final RoutingLambdaApplication app =
        new RoutingLambdaApplication();

    @Test
    void dispatchesUpperAndReverse() {
        var router = app.dispatchText(
            app.uppercase(), app.lowercase(), app.reverse());

        var upper = router.apply(
            new RoutingLambdaApplication.TextCommand(
                "upper", "Hello"));
        var reverse = router.apply(
            new RoutingLambdaApplication.TextCommand(
                "reverse", "abc"));

        assertEquals("HELLO", upper.value());
        assertEquals("cba", reverse.value());
    }

    @Test
    void rejectsUnknownOperation() {
        var router = app.dispatchText(
            app.uppercase(), app.lowercase(), app.reverse());

        assertThrows(IllegalArgumentException.class,
            () -> router.apply(
                new RoutingLambdaApplication.TextCommand(
                    "delete", "value")));
    }

    @Test
    void rejectsNullInput() {
        var router = app.dispatchText(
            app.uppercase(), app.lowercase(), app.reverse());

        assertThrows(IllegalArgumentException.class,
            () -> router.apply(null));
    }
}
~~~

This test proves the correctness of the **switch allowlist** and Function logic. It does not verify that Spring injected the right beans or that FunctionCatalog registered **dispatchText**.

## 19. Testing Spring FunctionCatalog and the Default Router

Use **@SpringBootTest** to verify bean discovery and actual composition/routing:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = RoutingLambdaApplication.class)
class FunctionSelectionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void individualBeansAreDiscoverable() {
        assertNotNull(catalog.lookup("uppercase"));
        assertNotNull(catalog.lookup("lowercase"));
        assertNotNull(catalog.lookup("reverse"));
        assertNotNull(catalog.lookup("dispatchText"));
        assertNotNull(catalog.lookup("functionRouter"));
    }

    @Test
    void dispatchBeanUsesExpectedContract() {
        Function<
            RoutingLambdaApplication.TextCommand,
            RoutingLambdaApplication.TextResult> dispatch =
                catalog.lookup("dispatchText");

        assertNotNull(dispatch);

        var output = dispatch.apply(
            new RoutingLambdaApplication.TextCommand(
                "lower", "MiXeD"));

        assertEquals("mixed", output.value());
    }
}
~~~

For the framework **functionRouter**, also use the **MessageBuilder** test in Section 5 or dedicated tests for **MessageRoutingCallback** if a callback is enabled. Avoid mixing routing configurations with different precedence levels in a single test, which makes results harder to interpret.

### Why Test at Two Levels?

| Test | What Is Verified |
| --- | --- |
| **Unit** | Java logic, validation boundaries, and allowlist |
| **Spring integration** | Exact bean names, DI, and FunctionCatalog lookup |
| **Artifact inspection** | Shaded JAR contains FunctionInvoker and Spring classes |
| **AWS invocation** | Handler, env vars, conversion, and actual output |
| **Trigger integration** | Envelope, IAM, batching, retries, DLQ, and idempotency |

Passing unit tests does not prove **CodeUri** is right; passing catalog tests does not prove API Gateway will send the data structure the bean expects.

## 20. Inspecting the Shaded JAR and AWS Configuration

To use **FunctionInvoker** with a Java Lambda JAR, the project needs the **spring-cloud-function-adapter-aws** dependency and proper packaging, usually a **shaded JAR**.

Illustrative Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

The project must manage versions with a compatible Spring Boot/Spring Cloud BOM, and configure Maven Shade or Gradle Shadow to preserve **META-INF/spring.factories**, **AutoConfiguration.imports**, and required service metadata.

Illustrative inspection commands:

~~~bash
mvn clean package

jar tf target/routing-lambda-1.0.0-aws.jar |
  grep 'FunctionInvoker.class'

jar tf target/routing-lambda-1.0.0-aws.jar |
  grep 'RoutingLambdaApplication.class'
~~~

Do not use a Spring Boot executable JAR with nested **BOOT-INF/lib** as the deployable JAR simply because it runs with **java -jar**. Replace the sample artifact name with the actual built file.

**This lesson only authors instructional content**: the Maven/AWS commands are guidance for learners, not operations executed while writing this document.

## 21. Testing AWS Lambda for Both Approaches

### A. Single Lambda with dispatchText

Direct invocation uses an envelope containing operation:

~~~bash
aws lambda invoke \
  --function-name text-gateway \
  --cli-binary-format raw-in-base64-out \
  --payload '{"operation":"upper","value":"Hello Lambda"}' \
  response.json

cat response.json
~~~

Expect business output with **operation=upper** and **value=HELLO LAMBDA**.

### B. Two Separate Lambda Resources

Lambda selecting **uppercase**:

~~~bash
aws lambda invoke \
  --function-name uppercase-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '"Hello Lambda"' \
  response.txt
~~~

Lambda selecting **lowercase**:

~~~bash
aws lambda invoke \
  --function-name lowercase-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '"HeLLo Lambda"' \
  lower.txt
~~~

These commands are examples for an environment configured with AWS credentials, IAM, and deployed artifacts. **A Lambda resource name** such as uppercase-lambda differs from the **Function bean** uppercase.

After invoking, do not check only the output file. Check **FunctionError** in AWS CLI metadata if present, logs, timeout, Java runtime, env vars, function version/alias, and serialized payload. An AWS invoke API call can succeed at the transport layer while the Function logic failed.

## 22. Operations and Versioning with Multiple Lambdas

### Same JAR, Multiple Configurations

In Approach B, Lambdas can share artifact version **1.0.0** while each Lambda stores different environment variables. When releasing a new JAR, track **which Lambdas are running which version**; you can update and test each Lambda individually.

### Each Lambda Has Versions/Aliases

An AWS Lambda version normally stores a snapshot of code and configuration. If a production alias points to an older version, updating an environment variable on unpublished configuration does not mean the alias has switched. When testing, record both function name and qualifier.

### One Dynamically Routed Lambda

In Approach A, changing the router or one bean in the JAR can affect every branch on the same Lambda. Run full regression tests across all routes before publishing a version or shifting an alias. When an incident occurs on one route, rolling back the whole Lambda can affect other routes.

### Observability

Log the authenticated route/operation in structured logs, and break down latency and error counts by route. With multiple Lambdas, you have resource-level metrics/alarms; with one Lambda, you need per-branch metrics so errors on one route are not masked by the overall success rate.

Do not log sensitive raw payloads, secrets, or unnecessary personal data. A correlation ID is for tracing only, not proof of authorization.

## 23. Common Troubleshooting Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Handler cannot be loaded | Missing adapter or wrong shaded JAR | Check FunctionInvoker.class, CodeUri |
| Main class not found | Wrong MAIN_CLASS/Start-Class | Check package and manifest |
| Multiple beans, wrong one selected | Missing/wrong function definition | Set explicit definition, test catalog |
| One Lambda runs only one bean | Static definition configured | Use per-invocation router if needed |
| functionRouter does not see route header | AWS event not mapped to Spring MessageHeaders | Build trusted adapter or dispatchText |
| Callback ignores definition header | Callback takes precedence over header | Use one intentional strategy only |
| Route does not exist | Wrong bean name or outside context scan | Check @Bean, FunctionCatalog |
| JSON parsing fails after changing definition | New bean has a different input contract | Update caller/conversion/schema |
| API Gateway body does not become DTO | Envelope differs from direct invoke | Use event adapter matching trigger |
| Unknown route reaches sensitive bean | Missing allowlist/authorization | Explicit operation mapping, least-privilege IAM |
| SQS event written twice | Redelivery and missing idempotency | Event ID + transaction/unique key |
| One operation times out whole Lambda | Shared timeout/memory, heavy branch | Consider splitting into a separate Lambda |
| Multiple Lambdas share a broken dependency | All use the same broken JAR | Version artifacts and test before rollout |
| Alias Lambda does not pick up new config | Alias still points to old published version | Check qualifier/version, controlled deploy |
| SpEL errors or routing risk | Accepting untrusted expressions | Block untrusted expressions, use allowlist |
| Per-message reactive routing does not work | Reactive routing operates per publisher, not per message | Use property routing or redesign |

## 24. Hands-on Exercises

**Exercise 1 — Architecture comparison.** A system has **readOrder**, **payOrder**, and **notifyOrder**. Choose A, B, or C for each operation if payOrder requires separate IAM and timeout settings. State the trade-offs in deployment, observability, and permissions.

**Exercise 2 — Explicit router.** Add a **titleCase** operation to the sample application. Add the new bean, update the allowlist in **dispatchText**, and write unit tests for valid/invalid inputs. Do not allow callers to pass arbitrary bean names directly.

**Exercise 3 — RoutingFunction.** Use **catalog.lookup("functionRouter")** with **MessageBuilder** setting header **spring.cloud.function.definition=uppercase**. Check the output, then switch the header to **lowercase** and determine what conditions govern router selection.

**Exercise 4 — MessageRoutingCallback.** Build a callback allowing only **uppercase** and **reverse** based on a **trustedAction** header set by an adapter. Write a test rejecting disallowed actions, and explain why the callback can override routing headers.

**Exercise 5 — Two Lambdas sharing a JAR.** Write a SAM template creating uppercase and lowercase Lambdas with the same CodeUri/Handler/MAIN_CLASS, but different definition, memory, and timeout. Describe how to deploy/stage them separately.

**Exercise 6 — Splitting artifacts.** When uppercase needs only Java Core while payment needs JDBC, AWS SDK, and Secrets Manager, propose an appropriate module structure, dependencies, and build pipeline. List pros/cons versus sharing a JAR.

**Exercise 7 — Event envelope.** The text-gateway Lambda receives an API Gateway event whose body field is a JSON string. Design an adapter converting body into TextCommand and mapping TextResult to a response, testing invalid JSON/operation errors.

**Exercise 8 — SQS idempotency.** A Lambda processing **Consumer<OrderPaid>** receives the same event ID again after a timeout. Propose a unique key, transaction, and DLQ; explain why a correct router does not guarantee exactly-once processing.

**Exercise 9 — Observability and rollback.** A single Lambda serves three routes; after deployment, reverse shows elevated errors while upper/lower still succeed. Propose per-route metrics, risk mitigation strategies, and criteria for splitting reverse into its own Lambda.

### Key Takeaways

- **One Lambda with multiple functions** requires **per-invocation routing**, via FunctionRouter/MessageRoutingCallback/properly mapped headers or an allowlist gateway bean; a static environment definition does not change per event.
- **Multiple Lambdas sharing a JAR** typically use different **spring_cloud_function_definition** values while keeping the shared **FunctionInvoker** handler and Spring main class.
- **Multiple Lambdas with separate JARs** allow cleaner separation of dependencies, permissions, ownership, and deployment lifecycles, at the cost of extra management overhead.
- **functionRouter** is the router provided by Spring Cloud Function; callbacks, Message headers, and application properties follow a clear precedence order.
- **AWS event envelopes do not automatically become Spring Message headers**. Verify your adapter or write a reliable adapter layer.
- **IAM, authentication, authorization, idempotency, and retries** are not solved merely by choosing a function bean.
- Test Java logic, FunctionCatalog, shaded JAR, Lambda configuration, and real event sources before releasing a service.

### References

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): AWS Function Routing section, choosing one/multiple Lambdas, and FunctionInvoker.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): FunctionCatalog, functionRouter, MessageRoutingCallback, Message headers, SpEL, and routing priority.
- [AWS Lambda — Environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html): static configuration per Lambda and version.
- [AWS Lambda — Event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/invocation-eventsourcemapping.html): stream/queue integration, batching, and retries.
- [AWS SAM — AWS::Serverless::Function](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html): Lambda resources and IaC configuration.
