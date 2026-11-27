# Local Testing and Deployment with Infrastructure Tools

A **Spring Cloud Function** application can run standalone on the JVM, be invoked over HTTP, or be deployed as **AWS Lambda**. When taking the application to Lambda, development teams must verify both business logic and concerns that appear only in serverless environments: handlers, event payloads, environment variables, IAM permissions, timeouts, memory, event source mappings, and infrastructure configuration. **AWS SAM CLI** helps build, locally test Lambdas in Docker containers, emulate API Gateway endpoints, and deploy resources via Infrastructure as Code (IaC).

This lesson belongs to the **AWS Lambda** chapter and walks through a workflow from a Spring Cloud Function project to AWS: creating functional beans, packaging a Lambda-ready JAR, declaring a SAM template, running **sam build**, generating sample events, using **sam local invoke**, **sam local start-api**, and **sam local start-lambda**, verifying configuration, and deploying with **sam deploy**. It also compares testing levels, explains limits of local emulation, covers environment/permission configuration, CI/CD pipelines, and post-deployment troubleshooting.

## 1. Testing and Deployment Levels

No single command replaces every kind of testing. Each level answers a different set of questions:

| Level | Tool | Primary Question |
| --- | --- | --- |
| **Unit test** | JUnit 5, Mockito | Is the Function logic right for the defined inputs/outputs? |
| **Spring integration test** | Spring Boot Test, FunctionCatalog | Are beans registered under the right names, and do DI and composition work? |
| **Packaging** | Maven/Gradle, Shade/Shadow | Does the JAR contain FunctionInvoker, dependencies, and required Spring metadata? |
| **Local Lambda** | AWS SAM CLI + Docker | Do the handler, runtime container, JSON event, and serialization work in a Lambda-like environment? |
| **Local HTTP** | sam local start-api | Do routes, HTTP request/response, and API Gateway event mappings work? |
| **Cloud integration** | AWS SAM deploy, real Lambda/SQS/S3/API Gateway | Do IAM, triggers, event source mappings, retries, concurrency, and AWS services work? |
| **Production rollout** | SAM/CloudFormation, version/alias, CI/CD | Are changes deployed, observed, and rolled back safely? |

~~~mermaid
flowchart TD
    A["Write Supplier / Function / Consumer"] --> B["JUnit + Spring tests"]
    B --> C["Build shaded JAR"]
    C --> D["sam validate"]
    D --> E["sam build"]
    E --> F["sam local invoke / start-api / start-lambda"]
    F --> G["Cloud integration test"]
    G --> H["sam deploy"]
    H --> I["Logs, metrics, alarms"]
    I --> J["Version / alias / rollback"]
~~~

**Fast, inexpensive unit tests** should run frequently. **SAM local** helps validate events/handlers close to the Lambda runtime. **Cloud integration tests** remain necessary because local emulation does not fully reproduce IAM, event source mappings, retries, concurrency, quotas, service policies, and every AWS behavior.

## 2. Toolkit to Prepare

To run the examples in this lesson, prepare:

| Tool | Purpose | Check |
| --- | --- | --- |
| **JDK** | Compile the Spring Boot application | java -version |
| **Maven or Gradle** | Resolve dependencies, test, build JAR | mvn -version or gradle -version |
| **AWS SAM CLI** | Validate, build, local invoke, and deploy IaC | sam --version |
| **Docker Engine/Desktop** | Run Lambda runtime containers for sam local | docker version |
| **AWS CLI v2** | Credentials, profiles, inspecting resources, and invoking | aws --version |
| **IDE** | Debug Java, run JUnit | IntelliJ IDEA/Eclipse/VS Code |
| **Git** | Version control and IaC review | git --version |

### Java Runtime Must Be Compatible

The runtime declared in SAM must match:

- The JDK used to compile.
- The bytecode target in Maven/Gradle.
- The Spring Boot and Spring Cloud Function versions.
- The chosen Lambda CPU architecture, such as **x86_64** or **arm64**.
- An AWS Lambda runtime still supported at deployment time.

A template example using **java21** does not mean any JAR compiled with a newer JDK will run. Set the compiler release to match the target runtime and check the current supported Lambda runtime list before choosing.

### When Must Docker Be Running?

The **sam local invoke**, **sam local start-api**, and **sam local start-lambda** commands use runtime containers to emulate Lambda. Docker must be installed and its daemon must be running. If you are only running JUnit or a Spring Boot app directly on the JVM, Docker is not required.

### AWS Credentials and Profiles

Deployment commands against AWS require credentials with appropriate permissions. You can use AWS IAM Identity Center/SSO or an organization-provisioned profile:

~~~bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
~~~

The commands above are examples; the **dev** profile name is configured by the learner. Never place access keys/secrets in source code, SAM templates, event JSON files, or logs. **sam local** only needs AWS credentials if the function calls real AWS services; running a local invocation by itself does not require deploying a Lambda to the cloud.

## 3. A Sample Spring Cloud Function for Hands-on Practice

We create a small application with an **uppercase** bean taking a String and returning a String. This simple example separates packaging, handler, and infrastructure concerns from complex business logic.

File **src/main/java/example/lambda/FunctionApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(FunctionApplication.class, args);
    }

    @Bean("uppercase")
    Function<String, String> uppercase() {
        return value -> {
            if (value == null) {
                throw new IllegalArgumentException(
                    "Input must not be null");
            }
            return value.toUpperCase(Locale.ROOT);
        };
    }
}
~~~

The **uppercase** bean is the business logic. It does not depend on AWS Lambda, API Gateway, or SQS. The Spring Cloud Function AWS adapter provides a Lambda-compatible entry point and converts payloads according to the function's types.

You can add **application.yml** to choose a default function when running in contexts where it is needed:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
~~~

In AWS Lambda, set the environment variable:

~~~text
spring_cloud_function_definition=uppercase
~~~

When an application has multiple Supplier/Function/Consumer beans, setting definition explicitly prevents the framework from guessing which bean to invoke. **The bean name** is **uppercase**; the AWS handler remains **FunctionInvoker**.

### Testing Logic Before Running SAM

File **src/test/java/example/lambda/FunctionApplicationTest.java**:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class FunctionApplicationTest {

    private final FunctionApplication app =
        new FunctionApplication();

    @Test
    void uppercasesInput() {
        assertEquals(
            "HELLO SAM",
            app.uppercase().apply("hello sam"));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(
            IllegalArgumentException.class,
            () -> app.uppercase().apply(null));
    }
}
~~~

Unit tests call the Function bean directly and therefore require neither Docker nor AWS credentials. They prove the logic works with Strings, not the Spring context, FunctionCatalog, Lambda handler, or deployment package.

### Verifying the Bean in the Spring Context

You can add an integration test to verify FunctionCatalog registered the expected bean name:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = FunctionApplication.class)
class FunctionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void registersUppercaseFunction() {
        assertNotNull(catalog.lookup("uppercase"));
    }
}
~~~

This test checks the Spring context and bean name. It does not test the Lambda handler or AWS event conversion; those require SAM local and cloud integration tests.

## 4. Packaging Spring Cloud Function for AWS Lambda

The application requires the **spring-cloud-function-adapter-aws** dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

The Spring Cloud Function AWS adapter provides the handler:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

This is the generic entry point. The adapter implements Lambda's **RequestStreamHandler** interface, initializes the Spring context, looks up the function via **FunctionCatalog**, converts the input, and serializes the output.

### Why Is a Shaded JAR Needed?

A standard Spring Boot executable JAR places dependencies nested inside **BOOT-INF/lib**. Spring Cloud Function's AWS Lambda packaging approach uses a **shaded JAR** to place classes and dependencies in a layout that the Java Lambda runtime can load directly.

Example artifact filename:

~~~text
target/function-app-1.0.0-aws.jar
~~~

Maven projects can produce an artifact with the **aws** classifier using **Maven Shade Plugin**. Gradle projects can use **Shadow Plugin**. During shading, preserve/merge Spring metadata such as **META-INF/spring.factories**, **AutoConfiguration.imports**, service files, and other resources per your Spring Boot version's guide.

### Maven Shade Plugin and Spring Metadata

The abbreviated configuration below illustrates creating the **aws** classifier and merging Spring resources. The Maven Shade Plugin, Spring Boot Maven Plugin, and transformer versions must be compatible with your project's BOM/versions; consult the official Spring Cloud Function sample when upgrading major versions.

The **spring-boot.version** property in the example must be declared in the POM and match the Spring Boot version the application uses.

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
        </dependency>
    </dependencies>
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
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                        <resource>META-INF/spring.handlers</resource>
                    </transformer>
                    <transformer implementation="org.springframework.boot.maven.PropertiesMergingResourceTransformer">
                        <resource>META-INF/spring.factories</resource>
                    </transformer>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                        <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This is an illustrative configuration snippet, not a complete POM. Some Spring Boot applications also need to merge **META-INF/spring.schemas**, **spring.components**, or other metadata. Check the transformer list against the Spring Cloud Function guide for your version; if metadata is overwritten, the context may fail to initialize properly even though the JAR builds cleanly.

With Gradle, use Shadow Plugin and configure service file / Spring metadata merging accordingly. Do not assume the default **bootJar** task has a layout equivalent to an AWS shaded JAR.

**Do not simply rename a .jar file to -aws.jar.** The artifact must genuinely be built with the right configuration. You can inspect it with:

~~~bash
jar tf target/function-app-1.0.0-aws.jar
~~~

Look for critical classes such as:

~~~text
org/springframework/cloud/function/adapter/aws/FunctionInvoker.class
example/lambda/FunctionApplication.class
~~~

If the JAR lacks the handler or Spring metadata was overwritten during shading, Lambda can throw **ClassNotFoundException**, fail to initialize ApplicationContext, or fail to locate the Function bean.

### Running the Maven Build

With Maven Wrapper on macOS/Linux:

~~~bash
./mvnw clean package
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
~~~

If using a globally installed Maven:

~~~bash
mvn clean package
~~~

The output filename depends on project configuration. Do not assume every project produces **function-app-1.0.0-aws.jar**.

## 5. What Does AWS SAM Do in the Workflow?

**AWS Serverless Application Model (SAM)** is an IaC framework extending CloudFormation. A SAM template describes Lambdas, APIs, queues, buckets, environment variables, IAM policies, and related resources. SAM CLI provides commands to:

- **sam init**: initialize a sample project.
- **sam validate**: validate the template.
- **sam build**: build and prepare artifacts for subsequent steps.
- **sam local**: test the application locally in containers.
- **sam deploy**: deploy templates and artifacts to AWS via CloudFormation.
- **sam logs**: read/tail logs of a deployed Lambda.
- **sam sync**: rapidly sync changes to a cloud environment during development.
- **sam remote invoke**: invoke cloud resources from SAM CLI.

~~~mermaid
flowchart LR
    A["template.yaml"] --> B["sam validate"]
    B --> C["sam build"]
    C --> D[".aws-sam/build"]
    D --> E["sam local"]
    D --> F["sam deploy"]
    F --> G["CloudFormation stack"]
    G --> H["Lambda / API / IAM / Event sources"]
~~~

SAM does not replace Maven/Gradle or Spring Cloud Function. It orchestrates artifact builds and describes infrastructure. Java code must still be compiled, tested, and packaged to meet Lambda requirements.

## 6. Declaring a SAM Template for Spring Cloud Function

Example **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Spring Cloud Function running on AWS Lambda

Resources:
  UppercaseFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: .
      MemorySize: 512
      Timeout: 15
      Architectures:
        - x86_64
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.FunctionApplication
          spring_cloud_function_definition: uppercase
      Events:
        UppercaseApi:
          Type: HttpApi
          Properties:
            Path: /uppercase
            Method: POST
            PayloadFormatVersion: "2.0"

Outputs:
  UppercaseApiUrl:
    Description: HTTP API endpoint
    Value: !Sub "https://${ServerlessHttpApi}.execute-api.${AWS::Region}.amazonaws.com"
~~~

The template above illustrates a Lambda with an API Gateway HTTP API event. Key fields:

- **Runtime**: Lambda Java environment; must match bytecode.
- **Handler**: FunctionInvoker, not the uppercase bean name.
- **CodeUri**: code/build context directory used by SAM.
- **MemorySize/Timeout**: Lambda resource settings.
- **Architectures**: Lambda CPU architecture.
- **Environment.Variables**: selects the bean via **spring_cloud_function_definition**.
- **Events**: declares the API Gateway route triggering Lambda.

**The logical ID UppercaseFunction differs from the bean name uppercase and from the handler name.** When running **sam local invoke**, pass the resource's logical ID, while Spring Cloud Function uses the environment variable to locate the bean.

## 7. Using a Makefile So SAM Builds the Shaded JAR

Plain Java Lambdas can use SAM's default Java builder. However, Spring Cloud Function applications need Maven Shade/Gradle Shadow configuration and preserved Spring metadata. If SAM builds using its default Maven workflow, custom build steps in the POM might not produce the exact shaded artifact required by the adapter.

An explicit approach is declaring **Metadata: BuildMethod: makefile**. SAM will invoke the matching target in the Makefile to produce the artifact.

Add to the resource:

~~~yaml
  UppercaseFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: .
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.FunctionApplication
          spring_cloud_function_definition: uppercase
    Metadata:
      BuildMethod: makefile
~~~

File **Makefile** inside the CodeUri directory:

~~~makefile
build-UppercaseFunction:
	mvn -B -DskipTests clean package
	mkdir -p "$(ARTIFACTS_DIR)/lib"
	cp target/function-app-1.0.0-aws.jar "$(ARTIFACTS_DIR)/lib/"
~~~

Replace **function-app-1.0.0-aws.jar** with the exact shaded JAR filename produced by Maven. The Makefile must preserve **tab** indentation before each command. The build environment needs Maven and a matching JDK; if using Maven Wrapper, replace **mvn** with the wrapper matching your OS/build container.

**ARTIFACTS_DIR** is an environment variable supplied by SAM for custom Makefile builds. For Java ZIP deployments, dependency JARs are placed inside **lib/** so the Java Lambda runtime can load them from the classpath.

On Windows, a custom Makefile requires GNU Make and a compatible shell. You can use WSL/Git Bash or standardize builds in a Linux CI container; if building manually via PowerShell, use the Windows Maven Wrapper and ensure the SAM template points to the properly laid-out artifact.

### Things to Verify

- The Makefile resides in the **CodeUri** directory.
- The target is named **build-UppercaseFunction**, matching the resource logical ID.
- The build produces the shaded JAR with the **aws** classifier.
- The JAR is copied into **$(ARTIFACTS_DIR)/lib/**.
- The JAR contains **FunctionInvoker.class**, application classes, and Spring metadata.
- Templates and artifacts inside **.aws-sam/build** are regenerated after source edits.

Never edit files directly inside **.aws-sam/build**. That is SAM's build output; edit the source/Makefile and rerun **sam build**.

## 8. Validating the Template Before Building

Run from the directory containing **template.yaml**:

~~~bash
sam validate
~~~

If the corresponding lint tool is installed, you can run:

~~~bash
sam validate --lint
~~~

SAM validation checks template structure and rules. It does not replace full verification of IAM permissions, Java logic, or actual Lambda execution.

When a template references missing files, Makefiles, or artifacts, check relative paths from the project root directory. Avoid absolute paths that exist only on a personal workstation in templates shared with CI/CD.

## 9. Building the Application with SAM

Run:

~~~bash
sam build
~~~

SAM creates the directory:

~~~text
.aws-sam/
  build/
    UppercaseFunction/
      lib/
        function-app-1.0.0-aws.jar
    template.yaml
  build.toml
~~~

This is an illustrative structure; actual files depend on the template and build method.

To build inside a container closer to the Lambda environment:

~~~bash
sam build --use-container
~~~

**sam build** prepares artifacts for local testing or deployment, typically generating **.aws-sam/build**. With a custom Makefile, SAM executes the commands inside your target. Therefore, only build trusted projects and review Makefiles, POMs, and Gradle scripts before execution.

### When Should You Use --use-container?

- You want to reduce differences between the local build environment and the Linux runtime.
- You have native dependencies or need to build against a Lambda-compatible environment.
- You want consistent builds across different developer machines.

**--use-container** requires Docker and the corresponding build image. It does not automatically guarantee the application has been tested across every CPU architecture or AWS service.

## 10. Generating Sample Events for Testing

AWS SAM CLI can generate event payloads formatted like AWS services. Examples:

~~~bash
sam local generate-event apigateway http-api-proxy > events/http-api-v2.json
~~~

~~~bash
sam local generate-event s3 put --bucket sample-input --key incoming/demo.csv > events/s3-put.json
~~~

~~~bash
sam local generate-event sqs receive-message --body '{"orderId":"ORD-101"}' > events/sqs.json
~~~

These commands generate sample events with metadata/shapes close to AWS source structures. Adjust the bucket, ARN, body, headers, region, or business fields to match your application. Generated values are usually placeholders; sample events do not create real S3 buckets or SQS queues.

You can list supported sources/events:

~~~bash
sam local generate-event --help
~~~

Or inspect options for a specific event type:

~~~bash
sam local generate-event s3 put --help
~~~

### Simple Direct Invoke Event

For the **Function<String,String> uppercase** bean, **events/uppercase.json** can contain:

~~~json
"hello sam"
~~~

This is a business payload sent directly to Lambda. It is not an API Gateway event envelope. If Lambda is called via API Gateway, the payload may sit inside the event's **body** field; in that case, verify conversion/adapters and the corresponding function signature.

## 11. Running Once with sam local invoke

After **sam build** succeeds:

~~~bash
sam local invoke UppercaseFunction --event events/uppercase.json
~~~

SAM CLI:

1. Finds logical ID **UppercaseFunction** in the template.
2. Uses the built artifact in **.aws-sam/build** if available.
3. Starts a Lambda runtime container using Docker.
4. Sends the JSON event to the handler.
5. Prints the invocation logs and output.

This lets you test a single invocation without deploying the Lambda to AWS.

### Overriding Environment Variables Locally

Create **env.local.json**:

~~~json
{
  "UppercaseFunction": {
    "spring_cloud_function_definition": "uppercase"
  }
}
~~~

Run:

~~~bash
sam local invoke UppercaseFunction --event events/uppercase.json --env-vars env.local.json
~~~

This env file can hold local-only configuration values. Never commit real secrets to the repository. If the Function calls the AWS SDK, local machine credentials may be used per SAM/CLI settings; enforce least privilege and avoid letting tests write into production.

### Reading Output and Logs

**sam local invoke** runs code locally; runtime logs usually go to stderr and the function result goes to stdout. When troubleshooting:

- Inspect the Lambda runtime **START/END/REPORT** lines.
- Check for Spring ApplicationContext or FunctionCatalog errors.
- Verify the input JSON matches the type declared by the bean.
- Verify the intended function definition was selected.
- Check whether response serialization succeeded.

If the invocation fails before the bean runs, inspect the handler, JAR, and main class before editing business logic.

## 12. Running API Gateway Locally with sam local start-api

When the template includes **Events: Api** or **Events: HttpApi**, you can start a local HTTP server:

~~~bash
sam local start-api
~~~

SAM prints the local routes. Example:

~~~text
Mounting UppercaseFunction at http://127.0.0.1:3000/uppercase [POST]
~~~

Send a request:

~~~bash
curl -X POST http://127.0.0.1:3000/uppercase \
  -H "Content-Type: application/json" \
  -d '"hello sam"'
~~~

This is an example JSON string payload for a **String → String** function. If your function accepts a DTO or uses a specific API Gateway proxy envelope, the body and mapping must match the function/adapter contract. Do not assume every route converts HTTP bodies into the same Java type.

### Testing the HTTP Response

Check:

- Status code.
- Response body.
- Content-Type.
- Headers returned by the adapter.
- Handling of invalid JSON or empty bodies.
- Nonexistent routes and unsupported HTTP methods.

**sam local start-api** is helpful for HTTP development, yet it is not the real API Gateway service. Authorization, custom domains, throttling, WAF, usage plans, mappings, authorizers, and many cloud settings still require testing on AWS.

## 13. Exposing a Local Lambda Endpoint with sam local start-lambda

To invoke the local function via AWS CLI or SDK, use:

~~~bash
sam local start-lambda --port 3001
~~~

This opens a local Lambda endpoint, for example:

~~~text
http://127.0.0.1:3001
~~~

In another terminal, invoke with AWS CLI:

~~~bash
aws lambda invoke \
  --function-name UppercaseFunction \
  --endpoint-url http://127.0.0.1:3001 \
  --cli-binary-format raw-in-base64-out \
  --payload fileb://events/uppercase.json \
  response.json
~~~

Inspect the output:

~~~bash
cat response.json
~~~

**UppercaseFunction** is the logical ID in the template; the endpoint is local, not an AWS Lambda ARN. Here the AWS CLI sends requests to the SAM local endpoint. You do not need to deploy a real resource just to test the SDK/CLI call path.

### Distinguishing the Three Local Commands

| Command | How It Is Called | When to Use |
| --- | --- | --- |
| **sam local invoke** | One event file, one invocation | Quickly test a single Lambda event |
| **sam local start-api** | HTTP client calls route | Test API Gateway HTTP routes |
| **sam local start-lambda** | AWS CLI/SDK calls local Lambda endpoint | Test integration code using the Lambda API |

All three still run function code on your machine inside a local/container environment; none is a Lambda execution environment running inside an AWS account.

## 14. Spring Cloud Function and Events When Running Locally

**FunctionInvoker** is the AWS adapter entry point. It receives the invocation stream, constructs a Message, looks up the function via **FunctionCatalog**, executes it, and serializes output. When running locally with SAM, the adapter still needs the same settings as deployment:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

spring_cloud_function_definition:
  uppercase
~~~

If the application has multiple beans, the definition must identify the intended bean or composition. Do not confuse:

- **SAM logical ID**: resource name in the template, e.g., UppercaseFunction.
- **AWS Lambda function name**: resource name after deployment.
- **Spring bean name**: Function name in FunctionCatalog, e.g., uppercase.
- **Handler**: FunctionInvoker::handleRequest.

### Testing Different Event Types

| Event | Sample File | What to Verify |
| --- | --- | --- |
| Direct invoke | uppercase.json | Payload matches type T |
| API Gateway | http-api-v2.json | Event envelope, body, HTTP response |
| S3 | s3-put.json | Records, bucket/key, and metadata handling |
| SQS | sqs.json | Records, body, and batch response |
| EventBridge | eventbridge.json | source, detail-type, detail, and schema |

For **S3/SQS**, sample events only mimic JSON structure. If code calls real S3/SQS APIs, the function may need AWS credentials, IAM permissions, and real resources. SAM local does not automatically spin up every AWS service.

### Context and Invocation Metadata Locally

Lambda metadata such as request ID, function name, log stream, and remaining time are created by the runtime. SAM local simulates part of this metadata; do not treat local values as proof of production Lambda ARNs, versions, or permissions.

If a function depends on AWS Context, unit tests can mock Context, while adapter tests should invoke through SAM local and then confirm on real staging Lambda.

## 15. Limitations of SAM Local

Local emulation is very useful, yet it is not a complete replica of AWS.

| Component | What SAM Local Supports | What Still Needs Cloud Testing |
| --- | --- | --- |
| Lambda handler/runtime | Runs inside matching runtime container | Cold starts, scaling, quotas, and production runtime behavior |
| Input/output | Sends JSON events and inspects responses | Actual serialization across each AWS trigger/adapter |
| API Gateway | Local HTTP endpoint | Authorizers, WAF, custom domains, throttling, full mappings |
| S3/SQS | Accepts sample JSON events | Real notification delivery, pollers, visibility timeouts, retries, DLQs |
| IAM | Uses local credentials for API calls | Execution roles, resource policies, trust policies, least privilege |
| AWS SDK | Function can call real AWS services | KMS, VPC, endpoint policies, throttling, and service behavior |
| CloudWatch | Shows container logs locally | Log groups, retention, subscriptions, alarms, and real metrics |
| Concurrency | Simple invocation emulation | Scale-out, reserved concurrency, bursts, and race conditions |

**Specifically:** when a function calls AWS services via the SDK, requests can hit **real AWS resources** using local credentials. Local testing does not mean all services are mocked or that requests are free.

Local commands execute project code on your machine inside containers and may grant access to local files/environment. Run only trusted source code; never treat the SAM local container as a security sandbox for untrusted code.

If you want emulated AWS services, you can explore tools like LocalStack. That is a complementary option; emulator behavior must still be verified against real AWS before release.

## 16. Declaring Local and AWS Environments

Never hard-code endpoints, database passwords, tokens, or bucket names in Java source. Use environment-based configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase

app:
  quote:
    currency: VND
~~~

In the SAM template:

~~~yaml
Environment:
  Variables:
    spring_cloud_function_definition: uppercase
    APP_QUOTE_CURRENCY: VND
~~~

In **env.local.json**, override variables needed locally:

~~~json
{
  "UppercaseFunction": {
    "spring_cloud_function_definition": "uppercase",
    "APP_QUOTE_CURRENCY": "VND"
  }
}
~~~

Sensitive values should be fetched from AWS Secrets Manager, Systems Manager Parameter Store, or an organization-approved secrets mechanism with appropriate IAM permissions. Never commit secrets into env.local.json.

### Separating Configuration by Environment

You can maintain environment profiles:

~~~text
samconfig.toml
  [default.deploy.parameters]
  stack_name = "function-dev"
  region = "ap-southeast-1"

  [staging.deploy.parameters]
  stack_name = "function-staging"
  region = "ap-southeast-1"

  [production.deploy.parameters]
  stack_name = "function-production"
  region = "ap-southeast-1"
~~~

This is an illustrative layout; exact samconfig syntax depends on the SAM CLI version and parameters chosen during **sam deploy --guided**. Never store credentials in samconfig. Use named profiles/SSO and separate permissions per environment.

## 17. IAM and Infrastructure Resources in SAM

A SAM template can declare permissions and triggers alongside the Lambda. For example, if a function only logs and calls no other AWS services, it needs basic logging permissions. If it reads S3, add read permissions for the specific bucket/prefix. If it processes SQS, add queue-polling permissions.

~~~yaml
Policies:
  - S3ReadPolicy:
      BucketName: !Ref InputBucket
~~~

This example is a SAM policy template illustrating S3 read permissions. Verify the generated policy matches your exact requirements; never use **AdministratorAccess** to silence AccessDenied errors.

In the example, **InputBucket** must be the logical resource of a bucket declared in the same template, or replaced by a bucket name/ARN matching how your project manages resources.

Settings commonly declared:

- **Execution role**: permissions the function is allowed to use.
- **Resource-based policy**: which services may invoke the Lambda.
- **Timeout/MemorySize**: runtime limits.
- **ReservedConcurrency**: concurrency cap if the workload requires one.
- **Dead-letter queue / destinations**: where failed asynchronous invocations go.
- **Event source mapping**: batching, retries, filtering, and partial batch responses for queues/streams.
- **Log retention**: CloudWatch log retention period.
- **Tracing**: X-Ray/OpenTelemetry per observability strategy.

### Do Not Confuse the Deployer's IAM with the Lambda's IAM

There are two separate identities:

1. **Developer/CI deploy identity**: permitted to create/update CloudFormation stacks, upload artifacts, and pass roles per policy.
2. **Lambda execution role**: assumed by Lambda at runtime; should hold only minimal business permissions.

A successful **sam deploy** does not mean the execution role has permissions to call S3/SQS/DynamoDB. Conversely, Lambda's runtime role does not grant CloudFormation deployment permissions to developers.

## 18. First-Time Deployment with sam deploy --guided

After building and local testing:

~~~bash
sam deploy --guided
~~~

SAM CLI prompts for details such as:

| Prompt | Meaning |
| --- | --- |
| **Stack Name** | CloudFormation stack name |
| **AWS Region** | Target deployment region |
| **Confirm changes before deploy** | Review the changeset before applying |
| **Allow SAM CLI IAM role creation** | Allow SAM to create IAM roles if needed by the template |
| **Disable rollback** | Rollback handling option if deployment fails |
| **Save arguments to configuration file** | Save choices to samconfig.toml |

On first deployment, SAM may ask about an S3 artifact bucket or artifact management. Artifacts are uploaded to S3, and CloudFormation creates/updates the Lambda and other resources.

After the first guided run, parameters are usually saved in **samconfig.toml**. Subsequent deploys can run:

~~~bash
sam deploy
~~~

To target a specific environment in samconfig:

~~~bash
sam deploy --config-env staging
~~~

The **staging** environment name must exist in the project configuration. Before deploying, review the template and config because they can create IAM roles, APIs, queues, buckets, or modify live resources.

### Reviewing the Changeset Before Confirming

When SAM asks to confirm changes, verify:

- Which new resources are created.
- Which resources are modified or replaced.
- Which IAM policies are broadened.
- Which API routes, event source mappings, and environment variables change.
- Whether stateful resources such as S3 buckets, DynamoDB tables, or SQS queues risk replacement or deletion.

Do not approve a changeset merely because code compiled cleanly. Infrastructure changes can affect data lifecycles and access permissions.

## 19. CI/CD Deployment and Managing Multiple Environments

In team projects, do not rely on manual deploys from a developer laptop. A typical pipeline includes:

~~~mermaid
flowchart TD
    A["Commit / Pull Request"] --> B["Compile + Unit tests"]
    B --> C["Build shaded JAR"]
    C --> D["SAM validate + SAM build"]
    D --> E["Local / contract tests"]
    E --> F["Deploy development"]
    F --> G["Cloud integration tests"]
    G --> H["Approval / promotion"]
    H --> I["Deploy staging / production"]
    I --> J["Canary / alias / alarms"]
    J --> K["Rollback on threshold breach"]
~~~

### Recommended Pipeline

1. **Checkout** source code from a reviewed commit.
2. Run **Maven/Gradle tests**.
3. Build the shaded JAR and inspect the artifact.
4. Run **sam validate** and **sam build**.
5. Optionally run **sam local invoke** contract tests.
6. Deploy to development/staging using a scoped CI role.
7. Run integration tests against real API Gateway/SQS/S3.
8. Verify logs, metrics, alarms, permissions, and output contracts.
9. Promote the verified artifact to production; avoid rebuilding a different artifact between staging and production unless necessary.
10. Monitor versions/aliases and roll back when health checks fail.

You can use CodePipeline/CodeBuild, GitHub Actions, or your organization's CI/CD system. The critical point is **promoting the same verified artifact across environments** while managing infrastructure/environment configuration through IaC.

### sam sync During Development

**sam sync --watch** can rapidly sync changes to the cloud for dev/testing. It is useful when testing behavior against real AWS services without running the full pipeline each time. However, it still modifies cloud resources; use an isolated dev stack, scoped profile/role, and never run it against production without an approval process.

## 20. Post-Deployment Testing

After a successful deploy, inspect stack outputs:

~~~bash
aws cloudformation describe-stacks \
  --stack-name function-dev \
  --query "Stacks[0].Outputs"
~~~

If there is an API endpoint, send a test request:

~~~bash
curl -X POST https://example.execute-api.ap-southeast-1.amazonaws.com/uppercase \
  -H "Content-Type: application/json" \
  -d '"hello aws"'
~~~

The **example** endpoint is only a placeholder; obtain the real URL from CloudFormation Outputs or SAM CLI. Check the status code, body, headers, and logs.

You can invoke Lambda directly via SAM:

~~~bash
sam remote invoke UppercaseFunction --stack-name function-dev --event '"hello aws"'
~~~

**sam remote invoke** calls the real cloud resource. Do not confuse it with **sam local invoke**; requests execute on AWS, consume quota, and call real services.

### Viewing Logs After Deployment

~~~bash
sam logs -n UppercaseFunction --stack-name function-dev --tail
~~~

You can also view them via the CloudWatch Logs console or AWS CLI. When investigating, check:

- AWS request ID.
- Lambda function/version/alias.
- Function definition.
- Event source and payload schema.
- Duration, memory, timeout, cold start.
- Error stack trace and downstream requests.
- IAM AccessDenied, throttling, or network timeouts.

## 21. Versions, Aliases, and Rollback

In production, separate **$LATEST** from published versions and point an alias to the verified version. A deployment flow can be:

1. Deploy new code/config.
2. Test $LATEST or the new version.
3. Publish a version.
4. Shift the alias in a controlled manner.
5. Monitor errors, duration, business metrics, and alarms.
6. Point the alias back to the previous version if errors exceed thresholds.

SAM/CloudFormation supports deployment preferences/aliases for suitable rollout strategies. Canary/linear deployments require alarms and associated permissions. Do not assume simply running **sam deploy** automatically produces a safe rollout; declare version/alias and policy settings explicitly.

### During Rollback

Rolling back code does not always roll back persisted data or database schema changes. For migrations, event schemas, or message contracts, design backward compatibility and data handling procedures. Retain prior artifacts/versions, record deployed commits/configs, and verify the alias after rolling back.

## 22. Common Errors When Running Locally

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Docker is not running | Docker daemon not started | Start Docker Desktop/Engine and check docker version |
| Template file not found | Running SAM in wrong folder or wrong template path | Run from project root or pass --template-file |
| Function not found | Used bean name instead of logical ID | sam local invoke expects the template logical ID |
| ClassNotFoundException: FunctionInvoker | Artifact missing adapter or wrong JAR layout | Check shaded JAR, handler, and CodeUri |
| Failed to determine main class | Missing valid Start-Class/MAIN_CLASS | Set MAIN_CLASS or inspect manifest |
| FunctionCatalog cannot find bean | Wrong function definition or component scan | Check @Bean name, spring_cloud_function_definition |
| Local output differs from cloud | Different JSON event, runtime, env, or architecture | Compare event, runtime, env, and cloud integration |
| AWS SDK calls wrong account | Wrong local credentials/profile | Check aws sts get-caller-identity and profile |
| AccessDenied | Execution role or local credentials lack permissions | Identify actual principal and grant least privilege |
| Port already in use | start-api/start-lambda already running on port | Pick another port or stop old process |
| Edited code yet local still runs old build | Forgot to rerun sam build or stale build artifact | Run sam build and restart local server |
| JSON conversion error | Event shape mismatches Function input | Check direct payload vs. event envelope |
| sam deploy fails to upload artifact | Missing bucket, upload permissions, or region | Check artifact bucket, profile, and region |
| CloudFormation rollback | Template, IAM, quota, or resource conflict | Inspect stack events and fix root cause |
| Function timeout | Slow downstream or timeout too low | Check remaining time, timeout, and dependency latency |

## 23. Common Errors During Infrastructure Deployment

| Symptom | Cause | Investigation Path |
| --- | --- | --- |
| SAM reports missing CAPABILITY | Template creates IAM resources | Check capability prompt/flag and review IAM |
| Lambda updates yet API does not change | API route/deployment stage or alias not updated | Inspect CloudFormation resources and endpoint |
| Incompatible function runtime | Runtime and bytecode mismatch | Align Java compiler release and Lambda Runtime |
| Bloated artifact or missing classes | Misconfigured shading, duplicate/dropped dependencies | Inspect JAR contents and transformers |
| Lambda cannot read S3 | Execution role lacks s3:GetObject or bucket policy | Inspect role, bucket, prefix, and KMS |
| SQS mapping does not run | Missing poll permission, queue ARN, or bad mapping | Check event source mapping state and LastProcessingResult |
| Logs do not appear | Role lacks logging permissions or log group missing | Check AWSLambdaBasicExecutionRole/log group |
| Cannot read secret | Missing secretsmanager/ssm/KMS permissions | Check policy and resource ARN |
| Deploy replaces stateful resource | Logical ID/properties changed triggering replacement | Review changeset, retention policy, and migration plan |
| Production alias still runs old version | Alias not shifted to new version | Inspect alias routing configuration |
| Passes locally yet fails in cloud | Differences in IAM, networking, triggers, concurrency, or services | Run cloud integration tests with real roles/resources |

## 24. Pre-Deployment Checklist

- [ ] Unit tests and Spring integration tests pass.
- [ ] Beans are registered under the right names and function definition is explicit.
- [ ] AWS artifact is a properly structured shaded JAR/ZIP.
- [ ] FunctionInvoker is present in the deployment package.
- [ ] Spring metadata is merged during shading.
- [ ] Java runtime, compiler release, and architecture are compatible.
- [ ] sam validate passes.
- [ ] sam build produces fresh artifacts in .aws-sam/build.
- [ ] Sample JSON events accurately reflect direct invoke or trigger envelopes.
- [ ] sam local invoke/start-api/start-lambda ran with matching payloads.
- [ ] Local credentials do not point to a production account by mistake.
- [ ] IAM execution role follows least privilege.
- [ ] Timeout, memory, concurrency, retries, and DLQ are properly configured.
- [ ] Environment variables and secrets are managed securely.
- [ ] CloudFormation changeset has been reviewed.
- [ ] Cloud integration tests completed.
- [ ] Logs, metrics, alarms, and rollback/version/alias are prepared.

## 25. Hands-on Exercises

**Exercise 1 — Unit test and local invoke.** Create an **uppercase** bean of type Function<String,String>. Write JUnit tests for normal strings, empty strings, and null. Create an event JSON and run **sam local invoke**; explain what each step verifies.

**Exercise 2 — Packaging a shaded JAR.** Add **spring-cloud-function-adapter-aws** to Maven. Configure Shade plugin to produce an **aws** classifier artifact while preserving Spring metadata. Use **jar tf** to verify FunctionInvoker and the application class.

**Exercise 3 — SAM Makefile.** Create an **UppercaseFunction** resource, set **Metadata BuildMethod: makefile**, and write target build-UppercaseFunction copying the JAR to **ARTIFACTS_DIR/lib**. Run sam build and describe the generated artifact.

**Exercise 4 — Generating sample events.** Use **sam local generate-event** to create API Gateway HTTP API, S3 put, and SQS receive-message events. Compare the event envelopes, then adjust payloads to match each Function signature.

**Exercise 5 — Local HTTP.** Add an HttpApi event to the template, run **sam local start-api**, and call the route with curl. Check status, body, content type, and malformed JSON body cases.

**Exercise 6 — Local Lambda endpoint.** Run **sam local start-lambda** and invoke it using AWS CLI with **--endpoint-url**. Explain why this command does not require deploying the function to AWS.

**Exercise 7 — Local environment.** Create **env.local.json** overriding the function definition and a business configuration variable. Explain why credentials must never be committed to this file.

**Exercise 8 — Deploying with SAM.** Use **sam deploy --guided** to create a dev stack. Record the stack name, region, artifact bucket, and IAM capabilities; read CloudFormation Outputs after deployment.

**Exercise 9 — Least-privilege IAM.** Extend a Function to read objects from an S3 prefix. Declare a policy allowing only s3:GetObject on that prefix, deploy to staging, and verify AccessDenied when permissions are missing.

**Exercise 10 — Cloud integration.** Configure an SQS trigger, send messages to a real queue, and observe Lambda logs, receive counts, retries, and DLQ. Compare the results against sam local invoke with event JSON.

**Exercise 11 — Versions and rollback.** Deploy a new version, shift a staging alias, monitor metrics, and roll back the alias when responses violate the contract. Explain why rolling back code does not automatically undo persisted data.

**Exercise 12 — CI/CD.** Design a pipeline covering compile, tests, shaded package, sam validate, sam build, local contract tests, dev deploy, integration tests, and production approval. Identify which artifact is promoted across environments.

### Key Takeaways

- **JUnit/Spring tests** verify logic and FunctionCatalog; **SAM local** verifies handlers/events in containers; **cloud integration tests** verify IAM, triggers, and real AWS behavior.
- **sam build** prepares artifacts in **.aws-sam/build**; with Spring Cloud Function, ensure custom Shade/Shadow settings produce the right shaded JAR.
- **sam local invoke** runs a single event; **sam local start-api** serves HTTP routes; **sam local start-lambda** exposes a local AWS CLI/SDK-compatible endpoint; **sam local generate-event** creates sample payloads.
- Local testing requires Docker and may call real AWS services using local credentials. Never treat SAM local as a complete AWS emulator.
- **sam deploy --guided** configures the initial deployment, saves parameters in **samconfig.toml**, and deploys the stack via CloudFormation.
- **FunctionInvoker** is the Lambda handler; **spring_cloud_function_definition** selects the bean; the SAM logical ID is the resource name inside the template.
- IaC requires reviewing IAM, event source mappings, timeouts, memory, environment variables, stateful resources, and CloudFormation changesets.
- Production requires observing logs/metrics, versions/aliases, integration testing, and controlled rollbacks.

### References

- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, handler, Maven/Gradle builds, shaded JARs, FunctionCatalog, and routing.
- [AWS SAM CLI — Core commands](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-corecommands.html): sam init, build, local, deploy, sync, and remote invoke.
- [AWS SAM — Building applications](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-build.html): sam build, build containers, artifacts, and Makefiles.
- [AWS SAM — Local testing](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local.html): local generate-event, invoke, start-api, and start-lambda.
- [AWS SAM — Local invoke](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-invoke.html): single invocation inside a Docker container.
- [AWS SAM — Local start-api](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-start-api.html): testing API Gateway routes locally.
- [AWS SAM — Local start-lambda](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-start-lambda.html): local Lambda endpoint for AWS CLI/SDK.
- [AWS SAM — Deploy applications](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-deploy.html): deploy --guided, samconfig.toml, and CloudFormation.
- [AWS Lambda — Java deployment packages](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): JAR/ZIP, dependencies, Maven, and Gradle.
- [AWS Lambda — Testing guide](https://docs.aws.amazon.com/lambda/latest/dg/testing-guide.html): local container testing and differences versus cloud.
