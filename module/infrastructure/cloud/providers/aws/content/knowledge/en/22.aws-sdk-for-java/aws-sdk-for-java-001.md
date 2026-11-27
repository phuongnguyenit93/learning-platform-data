# AWS SDK for Java v2 Architecture and Dependency Management with BOM

A Java application can call Amazon S3, DynamoDB, SQS, SNS, Step Functions, or STS using the AWS SDK for Java. However, the SDK is not a single JAR containing every service. **AWS SDK for Java 2.x is split into multiple modules**, each providing a client and models for an AWS service or a shared capability. A project only needs to depend on the components it requires, but it must manage versions consistently to avoid classpath errors at compile time or runtime.

**Bill of Materials (BOM)** is a Maven/Gradle mechanism for centralized version management. When importing `software.amazon.awssdk:bom`, individual SDK v2 dependencies can omit their own versions; the build tool resolves the version managed by the BOM. This reduces the risk of `s3`, `dynamodb`, `sts`, and underlying SDK libraries being pulled in at incompatible versions.

This lesson belongs to the **AWS SDK for Java** chapter of the **CLOUD_PROVIDERS_AWS** module. The content ties into Regions/AZs, IAM, VPC, compute and storage services, databases, messaging, serverless, monitoring, and operating AWS applications that are secure, resilient, and cost-controlled. Examples use **AWS SDK for Java 2.x**, Maven, Gradle, and Java 17/21; the SDK version in configurations is a pinned example for reproducible builds and should be updated according to your project's dependency management process.

> **Principle:** Import the BOM once in dependency management, declare the exact SDK modules the application uses, and maintain **a single unified SDK v2 version across the entire dependency graph**. The BOM manages versions; it **does not automatically add service modules, configure IAM/Region, lock all third-party libraries, or automatically connect the application to AWS**.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the modular architecture of AWS SDK for Java 2.x.
2. Distinguish between service client, model/request/response, shared core, authentication, HTTP transport, and AWS service endpoint.
3. Identify artifact coordinates: `groupId`, `artifactId`, `version`, Maven scope, and Gradle configuration.
4. Understand BOM, dependency management, version alignment, and transitive dependencies.
5. Import the AWS SDK v2 BOM in Maven `pom.xml` and Gradle Kotlin/Groovy DSL.
6. Explain why individual service dependencies do not need a version declared once the BOM is imported.
7. Know the scope of the BOM: SDK v2 modules under `software.amazon.awssdk`; it does not automatically manage SDK v1, Lambda Java runtime, Spring, logging, or JUnit.
8. Use Maven Enforcer and Gradle dependency insight to detect version divergence.
9. Choose the right HTTP client for synchronous/asynchronous clients.
10. Manage thread-safe service clients, connection pools, lifecycle, and configuration.
11. Understand the credentials provider chain, Region provider chain, IAM roles, and SigV4 signing.
12. Distinguish between synchronous, asynchronous, and high-level clients.
13. Configure controlled timeouts/retries and understand the default retry changes since v2.58.0.
14. Integrate the SDK with Spring Boot, Lambda, ECS/EC2, and local environments.
15. Diagnose compile/runtime errors caused by BOM, classpath, transport, credentials, and Region.

## 2. Where Does SDK v2 Sit in a Java Application?

The application calls services through a **service client**. The client encapsulates most of the communication with AWS: constructing the request, serializing data, signing the request, sending it over HTTP, receiving the response, deserializing it, and applying retries as configured.

~~~mermaid
flowchart TD
    APP["Java application / Spring service"] --> CLIENT["Service client<br/>S3Client / DynamoDbClient / SqsClient"]
    CLIENT --> MODEL["Generated request/response models"]
    CLIENT --> CORE["SDK core<br/>configuration, protocol, auth, retry"]
    CORE --> SIGN["AWS Signature Version 4 signing"]
    CORE --> HTTP["HTTP transport<br/>Apache5 / Netty / URLConnection / CRT"]
    HTTP --> ENDPOINT["Regional AWS service endpoint"]
    ENDPOINT --> SVC["Amazon S3 / DynamoDB / SQS / STS ..."]
    BOM["Maven/Gradle BOM<br/>aligns SDK module versions"] -. "Build-time dependency management" .-> CLIENT
~~~

The BOM is only involved **at build/dependency-resolution time**. It is not a runtime component sitting between the application and AWS.

### 2.1. Core Component Layers

| Component | Example | Responsibility |
|---|---|---|
| Service module | `software.amazon.awssdk:s3` | `S3Client`, `S3AsyncClient`, request/response models |
| Service module | `software.amazon.awssdk:dynamodb` | `DynamoDbClient` and API models |
| Shared SDK core | `sdk-core`, `aws-core` | Client runtime, execution pipeline, configuration |
| Auth | `auth`, `sts` | Credentials providers, request signing, STS operations |
| Region/config | `regions`, shared config providers | Region and profile resolution |
| HTTP transport | `apache5-client`, `netty-nio-client` | Synchronous/asynchronous HTTP connectivity |
| High-level library | `dynamodb-enhanced`, `s3-transfer-manager` | Higher-level APIs over basic service APIs |
| BOM | `software.amazon.awssdk:bom` | Version management for SDK modules |

A service dependency typically pulls in required shared modules via transitive dependencies. You do not need to manually declare every core JAR if the service module already manages them.

### 2.2. What Does a Service Client Handle?

When code calls:

~~~java
HeadObjectResponse response = s3.headObject(
    HeadObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build()
);
~~~

The client performs a sequence of steps:

1. Validates and prepares the request model.
2. Serializes the request into the protocol required by the AWS service.
3. Resolves the Region/endpoint and credentials.
4. Signs the request using AWS Signature Version 4 (SigV4) when required.
5. Sends the request via the HTTP client and processes the response.
6. Applies retry/timeout policies as configured.
7. Converts the response/error into corresponding Java types.

The SDK reduces boilerplate, but **it does not replace IAM least privilege, input validation, business idempotency, or business error handling**.

## 3. Modular Artifacts: Add Only the Modules the Application Needs

AWS SDK v2 distributes each service as a separate artifact:

| Need | Artifact | Commonly Used Classes |
|---|---|---|
| Object storage | `software.amazon.awssdk:s3` | `S3Client`, `S3AsyncClient` |
| NoSQL database | `software.amazon.awssdk:dynamodb` | `DynamoDbClient` |
| Queue | `software.amazon.awssdk:sqs` | `SqsClient` |
| Notification | `software.amazon.awssdk:sns` | `SnsClient` |
| Identity/token service | `software.amazon.awssdk:sts` | `StsClient` |
| Step Functions | `software.amazon.awssdk:sfn` | `SfnClient` |
| Key management | `software.amazon.awssdk:kms` | `KmsClient` |
| Secrets Manager | `software.amazon.awssdk:secretsmanager` | `SecretsManagerClient` |
| SSO login/profile | `software.amazon.awssdk:sso`, `ssooidc` | SSO credential providers |
| DynamoDB Enhanced Client | `software.amazon.awssdk:dynamodb-enhanced` | `DynamoDbEnhancedClient` |
| S3 high-level transfers | `software.amazon.awssdk:s3-transfer-manager` | `S3TransferManager` |

**Do not add the entire SDK just for convenience.** The aggregate artifact `aws-sdk-java` can pull in many unnecessary service modules, increasing the dependency graph, artifact size, classpath scanning, and build/startup times. Select only the modules actually used.

### 3.1. Artifact Coordinates

A basic Maven coordinate:

~~~text
groupId    = software.amazon.awssdk
artifactId = dynamodb
version    = 2.59.1
~~~

- `groupId` identifies the publishing organization/namespace.
- `artifactId` identifies the module.
- `version` identifies the release.
- Maven `scope`/Gradle configuration determines whether the module participates in compile, runtime, test, or packaging.

In SDK v2, service modules use the `software.amazon.awssdk` namespace. SDK v1 uses the `com.amazonaws` namespace and artifact names like `aws-java-sdk-s3`. **Do not confuse the two coordinate systems** when declaring a BOM or reading a dependency tree.

### 3.2. Low-Level Service Clients and High-Level Libraries

`DynamoDbClient` provides an API close to DynamoDB service operations. `DynamoDbEnhancedClient` is an add-on library that helps map Java objects, schemas, and table operations; it **does not replace** the low-level client and is declared via a separate `dynamodb-enhanced` module.

Similarly, `S3TransferManager` provides a high-level transfer API using appropriate transports/clients. When using a high-level library, check the modules and HTTP client dependencies required by that library's documentation.

## 4. What Is a BOM?

A **Bill of Materials** is a POM/Gradle platform containing a list of compatible dependency versions. AWS SDK v2 publishes a BOM with coordinates:

~~~text
software.amazon.awssdk:bom:<sdk-version>
~~~

The BOM tells the build tool that SDK v2 artifacts such as `s3`, `dynamodb`, `sdk-core`, `aws-core`, and related modules should be resolved to the same release/version.

Without a BOM, an application might declare:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
        <version>2.59.1</version>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>dynamodb</artifactId>
        <version>2.51.0</version>
    </dependency>
</dependencies>
~~~

The two modules can pull in different versions of shared dependencies. The result may compile but throw `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, or obscure linkage errors at runtime.

### 4.1. What Does the BOM Solve?

| Without BOM | With BOM |
|---|---|
| Declare a version for every module | Declare one centralized SDK version |
| Easy version drift across service modules | Build tool aligns versions via the BOM |
| Upgrade multiple dependency statements | Upgrade the BOM version in one place |
| Shared modules can be pulled in at mismatched versions | Reduces risk of version mismatch |
| Hard to review version policy | Clearer dependency policy |

### 4.2. What Does the BOM Not Do?

The BOM:

- **Does not automatically add** S3/DynamoDB/SQS to the classpath; you must declare the module dependencies.
- Does not automatically create IAM roles, credentials, Regions, or VPC endpoints.
- Does not force all dependencies outside `software.amazon.awssdk` to the same version.
- Does not replace Maven/Gradle dependency locking or convergence checks.
- Does not guarantee that all third-party transitive dependencies are compatible with your Java runtime.
- Is not a runtime client and does not open network connections.

A BOM is a **version catalog**, not a list of the modules the application actually needs.


## 5. Maven: Importing the BOM in `pom.xml`

Place the BOM inside `dependencyManagement`, using `type=pom` and `scope=import`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>2.59.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is the **version management section**; it has not added S3/DynamoDB service dependencies to the project yet.

### 5.1. Declaring Modules Without Individual Versions

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>dynamodb</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>apache5-client</artifactId>
    </dependency>
</dependencies>
~~~

Maven looks up the version from the BOM for artifacts managed by the BOM. **Do not declare a different version** on individual service modules unless there is a reviewed compatibility reason.

`apache5-client` in the example is declared in compile scope so the code can **configure `Apache5HttpClient` directly**. When only a service module is declared, the SDK already pulls Apache5 and Netty HTTP artifacts into runtime; if you do not need to configure the transport, declaring `apache5-client` explicitly in compile scope is not required. If choosing another transport, replace with the corresponding module and configure the appropriate client; you do not need to declare all HTTP clients at once.

### 5.2. A Minimal Complete POM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>aws-order-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <aws.sdk.version>2.59.1</aws.sdk.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>software.amazon.awssdk</groupId>
                <artifactId>bom</artifactId>
                <version>${aws.sdk.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>s3</artifactId>
        </dependency>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>dynamodb</artifactId>
        </dependency>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>sts</artifactId>
        </dependency>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>apache5-client</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version `2.59.1` is a **pinned version example** to illustrate the BOM, not a requirement that every project must use this exact release. In a real project, pick an SDK version approved by the team, security-reviewed, and compatible with your Java/runtime; upgrade versions via a tested pull request.

### 5.3. BOM Scope and Dependencies with Different groupIds

The BOM `software.amazon.awssdk:bom` manages SDK v2 artifacts within the SDK namespace. For example, `aws-lambda-java-core` has coordinates `com.amazonaws:aws-lambda-java-core`, so it **is not managed by the SDK v2 BOM** and must declare its own version or appropriate managed BOM.

Similarly, the SDK v2 BOM does not automatically manage:

- AWS SDK v1 modules `com.amazonaws:aws-java-sdk-*`.
- Spring Boot, Spring Cloud AWS, Micrometer, Logback/Log4j.
- JUnit, Mockito, Testcontainers, LocalStack test dependencies.
- AWS Lambda Java runtime/API libraries under other groups.
- AWS CRT platform artifacts if they use an independent version scheme.

Never assume "importing the AWS BOM means all AWS dependencies can omit versions". Always verify the exact groupId/artifactId.

## 6. Gradle: BOM with Kotlin DSL and Groovy DSL

Gradle uses `platform(...)` to import a Maven BOM as a **platform**.

### 6.1. Kotlin DSL — `build.gradle.kts`

~~~kotlin
plugins {
    java
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("software.amazon.awssdk:bom:2.59.1"))

    implementation("software.amazon.awssdk:s3")
    implementation("software.amazon.awssdk:dynamodb")
    implementation("software.amazon.awssdk:sts")
    implementation("software.amazon.awssdk:apache5-client")

    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

### 6.2. Groovy DSL — `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('software.amazon.awssdk:bom:2.59.1')

    implementation 'software.amazon.awssdk:s3'
    implementation 'software.amazon.awssdk:dynamodb'
    implementation 'software.amazon.awssdk:sts'
    implementation 'software.amazon.awssdk:apache5-client'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}
~~~

`implementation(platform(...))` lets Gradle inject BOM constraints into dependency resolution. If another library requests a higher SDK module version, Gradle may select the higher version over the BOM. Therefore **a platform does not automatically guarantee all modules end up at the exact same version** in every dependency graph.

### 6.3. When to Use `enforcedPlatform`?

~~~kotlin
dependencies {
    implementation(enforcedPlatform("software.amazon.awssdk:bom:2.59.1"))
    implementation("software.amazon.awssdk:s3")
    implementation("software.amazon.awssdk:dynamodb")
}
~~~

`enforcedPlatform` turns BOM constraints into **forced versions**, which can override or downgrade a higher version requested by another library. This helps a final application keep its chosen version, but can cause runtime linkage errors if a dependency truly requires a newer API.

- **Deployable end applications:** may choose `enforcedPlatform` if the dependency graph is controlled and runtime compatibility is tested.
- **Libraries published for others:** avoid forcing versions onto consumers; use `platform`/constraints so you do not impose your library's version on consuming applications.
- Either way, still inspect the dependency graph and run runtime tests.

## 7. BOM in Multi-Module Projects and Spring Boot

### 7.1. Maven Parent POM

A multi-module project can import the AWS BOM in the **parent POM** under `dependencyManagement`. Child modules declare service artifacts without their own versions.

~~~text
aws-platform-parent
├── order-api       → dynamodb, sqs
├── file-service    → s3
├── identity-api    → sts
└── notification    → sns
~~~

Not every child module needs to depend on all service clients. The BOM manages versions centrally; each module still declares only its actual dependencies.

### 7.2. Gradle Root Project

In a multi-project Gradle build, place the platform in a convention plugin or root dependency constraints so subprojects share one version. Avoid copying different BOM versions across multiple subprojects; they can resolve differently if configurations diverge.

### 7.3. Combining with the Spring Boot BOM

The Spring Boot BOM and AWS SDK BOM are **two independent platforms**:

- The Spring Boot BOM manages the Spring Boot ecosystem.
- The AWS SDK BOM manages `software.amazon.awssdk` modules.
- Spring Cloud AWS has its own BOM/starter versions and is not automatically aligned just by importing the AWS SDK BOM.

If multiple BOMs manage the same artifact, check precedence in the effective POM/Gradle resolution. Do not upgrade Spring Boot solely to upgrade the SDK, or manually override transitive versions without verifying compatibility.

## 8. A BOM Is Not a Version Lock or Convergence Enforcement

A BOM is one source of version management, but another dependency may request a different version, a POM may declare an explicit override, or Gradle conflict resolution may select a higher version. **A build can still succeed even when SDK modules have mismatched versions.**

~~~text
Application
├── software.amazon.awssdk:s3:2.59.1
│   └── software.amazon.awssdk:aws-core:2.59.1
└── library-x
    └── software.amazon.awssdk:dynamodb:2.51.0
        └── software.amazon.awssdk:aws-core:2.51.0
~~~

This is a **non-convergent** dependency graph, not the graph the BOM intends. Depending on the build tool and version selection, the classpath may resolve shared modules to a different version; never rely on compile success to conclude safety.

### 8.1. Maven Enforcer — Failing the Build on Divergent Versions

AWS recommends using the Maven Enforcer Plugin with `dependencyConvergence` scoped to `software.amazon.awssdk`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.6.3</version>
            <executions>
                <execution>
                    <id>enforce-aws-sdk-version-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence>
                                <includes>
                                    <include>software.amazon.awssdk</include>
                                </includes>
                            </dependencyConvergence>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

If the transitive graph contains multiple versions of SDK modules, the build fails during the `validate` phase and lists the divergent artifacts. This catches mismatches early rather than waiting for production failures.

### 8.2. Gradle Dependency Insight

~~~bash
# List the dependency graph.
./gradlew dependencies --configuration runtimeClasspath

# Inspect why the DynamoDB module resolved to its current version.
./gradlew dependencyInsight \
  --dependency software.amazon.awssdk:dynamodb \
  --configuration runtimeClasspath

# On Windows, use gradlew.bat instead of ./gradlew.
~~~

`dependencyInsight` explains which versions were requested, which version was selected, and why (constraint, conflict resolution, enforced platform).

### 8.3. Maven Dependency Tree and Effective POM

~~~bash
# View only AWS SDK v2 dependencies.
mvn dependency:tree -Dincludes=software.amazon.awssdk

# Display the POM after merging parent/dependencyManagement.
mvn help:effective-pom

# Run validate to execute Maven Enforcer if configured.
mvn validate
~~~

Read `dependency:tree` to find which module is pulling a mismatched version; read the effective POM to verify whether the BOM import actually applies or is being overridden.

## 9. Choosing the Right HTTP Client and Dependency

A service client needs an HTTP transport to send requests to AWS endpoints. SDK v2 decouples HTTP implementations from service APIs, allowing selection based on sync/async needs, latency, startup, TLS, proxy, and concurrency.

| HTTP Artifact | Client Type | When Appropriate |
|---|---|---|
| `apache5-client` | Synchronous | HTTP connection pooling, fine-grained configuration, traditional clients |
| `url-connection-client` | Synchronous | Lightweight, reduces startup/dependencies in simple use cases |
| `netty-nio-client` | Asynchronous | Non-blocking network I/O, async service clients |
| `aws-crt-client` | Sync/async depending on client support | Native AWS Common Runtime, workloads/networking needing specialized optimization |

**Since AWS SDK for Java 2.x version 2.46.0**, `Apache5HttpClient` is the default synchronous HTTP client, replacing `ApacheHttpClient` based on Apache HttpClient 4.x. The artifact for direct configuration is `apache5-client`; many older guides still list `apache-client`. When copying dependencies from older blogs, check the exact version and artifact documentation.

By default, service modules place **Apache5 synchronous** and **Netty asynchronous** HTTP artifacts on the runtime classpath. If no transport is specified, the SDK selects the default implementation for the client type; when multiple HTTP implementations are on the classpath, Apache5 has higher priority for sync. To force a specific transport, use `httpClientBuilder(...)` on each service client.

### 9.1. Synchronous HTTP Clients

`UrlConnectionHttpClient` is not automatically added to the project in configurations that require an explicit dependency. If you choose it, add:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>url-connection-client</artifactId>
</dependency>
~~~

For service dependencies with unused transitive HTTP clients, exclusions may be needed according to current documentation. For example, excluding `apache5-client` and `netty-nio-client` from the S3 module and using URLConnection; **do not apply this blindly** if asynchronous clients are still used.

URLConnection has lightweight startup, but **does not support HTTP PATCH** (some service operations require PATCH) and lacks a per-client configurable idle connection timeout. Check the operation API before choosing a transport; for workloads requiring richer features and connection controls, Apache5 is a better fit.

URLConnection only supports synchronous service clients; if the application uses `S3AsyncClient`/`DynamoDbAsyncClient`, it needs an appropriate asynchronous HTTP transport such as Netty or CRT.

### 9.2. HTTP Transport and Client Lifecycle

Each service client can hold a connection pool and HTTP resources. Do not create a new `S3Client` per request. Create one long-lived client per Region/credentials/endpoint configuration, reuse it across the application, and close it on shutdown.

If you inject a pre-built HTTP client yourself, be clear on who owns the lifecycle and who must close it. If the builder creates the HTTP client via `httpClientBuilder`, the SDK generally manages its lifecycle together with the service client; check the API docs for your specific version.


## 10. Service Clients: Thread-Safe and Should Be Reused

AWS SDK v2 service clients are **thread-safe** and immutable once built. Each client can hold a connection pool, credentials provider, and configuration. Therefore:

- Create one shared client per service/configuration for the application lifecycle.
- Do not create/close a client on every HTTP request or every database call.
- Use dependency injection (Spring singleton bean) or an application-scoped holder.
- Close clients during application shutdown.
- If a different Region/endpoint/credentials set is needed, create a separate client for that configuration; do not mutate an already-built client.

### 10.1. Shared Client

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class AwsClients {
    private static final DynamoDbClient DYNAMODB =
            DynamoDbClient.builder()
                    .region(Region.AP_SOUTHEAST_1)
                    .build();

    private AwsClients() {
    }

    public static DynamoDbClient dynamodb() {
        return DYNAMODB;
    }

    public static void shutdown() {
        DYNAMODB.close();
    }
}
~~~

This is a plain Java example. Spring applications should let the container manage lifecycle via beans; Lambda functions should create clients during static initialization outside the handler to take advantage of reuse across invocations in the same execution environment.

### 10.2. Why Not Create a Client Per Request?

Each client instantiation can initialize an HTTP connection pool, credential provider, endpoint/config resolution, and other resources. Creating them repeatedly wastes CPU/memory, increases handshakes, and easily exhausts sockets/threads. Reusing clients improves connection pooling and startup efficiency.

## 11. Credentials Provider Chain and IAM

The SDK must obtain credentials to sign AWS API requests. The **default credentials provider chain** searches credential sources in provider order. If the builder does not specify a provider, the service client uses the default chain.

Common sources include:

1. Java system properties.
2. Environment variables.
3. Web identity token / IAM role for service account.
4. Shared AWS config/credentials profiles, including appropriate IAM Identity Center/SSO configurations.
5. Container credential provider (ECS).
6. EC2 instance profile credentials via Instance Metadata Service (IMDS).

Provider order and details depend on configuration and SDK version; consult the credential chain documentation instead of hardcoding assumptions.

### 11.1. Local Development with IAM Identity Center

~~~bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
~~~

Java can use `ProfileCredentialsProvider` for an explicit profile:

~~~java
import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(
                ProfileCredentialsProvider.builder()
                        .profileName("dev")
                        .build())
        .build();
~~~

If no provider is specified, the SDK uses `DefaultCredentialsProvider` and checks the appropriate sources automatically. Explicit profiles are useful for local tools/tests, but production apps should not be forced to depend on a profile file on the host.

### 11.2. Production Workloads

| Runtime | Recommended Credentials Source |
|---|---|
| AWS Lambda | Function execution role |
| Amazon ECS/Fargate | Task role |
| Amazon EC2 | Instance profile role |
| Amazon EKS | EKS Pod Identity or IAM Roles for Service Accounts (IRSA), depending on cluster setup |
| On-premises | IAM Identity Center/STS assume role or controlled federation |

**Never hardcode access keys/secret keys in source code, YAML, Docker images, build logs, or application properties.** Use temporary credentials, IAM least privilege, and providers capable of refreshing credentials. Avoid copying access keys from the console into production environment variables.

### 11.3. STS and AssumeRole

If the application needs access to another account or resource, use STS AssumeRole and a credentials provider that supports refreshing. Do not write your own loop calling STS on every request. Design the trust policy, external ID when needed, and appropriate session duration; grant the target-account role only the necessary actions and resources.

## 12. Region Provider Chain and Endpoints

Credentials identify **who is calling**; Region determines **where the service endpoint is called**. These two configurations are independent.

The SDK can resolve the Region via:

1. Region set directly on the client builder.
2. JVM system property `aws.region`.
3. Environment variable `AWS_REGION`.
4. Region in the shared AWS config profile.
5. EC2 Instance Metadata Service in applicable environments.

### 12.1. Specifying the Region Explicitly

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();
~~~

Or use external Region configuration when the same artifact runs across multiple environments. Explicit Region configuration simplifies review and prevents the application from accidentally calling the wrong Region, table, or bucket. Region is not inferred from an IAM role alone.

### 12.2. Endpoint Override

`endpointOverride(URI.create(...))` is useful for local test services, LocalStack, or specialized AWS-supported endpoints. When overriding an endpoint, requests may still require a valid Region and signing credentials. **Do not hardcode LocalStack endpoints or private dev endpoints into production configurations.**

For private connectivity, service clients usually still use the regional endpoint; VPC endpoint DNS/routing directs traffic along the private path. Do not manually switch endpoints to static IPs unless AWS documentation explicitly requires it.


## 13. Synchronous and Asynchronous Service Clients

### 13.1. Synchronous Clients

`S3Client`, `DynamoDbClient`, and `SqsClient` execute API calls synchronously: the calling thread blocks until a response or error arrives. This is readable and fits Spring MVC, batch jobs, and workloads with moderate concurrency.

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

HeadBucketResponse response = s3.headBucket(
        HeadBucketRequest.builder()
                .bucket("example-bucket")
                .build());
~~~

In server applications, do not close the client after every call; reuse it and close on shutdown. Short-lived CLI tools or scripts may use try-with-resources.

### 13.2. Asynchronous Clients

`S3AsyncClient` and `DynamoDbAsyncClient` return `CompletableFuture`. Async clients support non-blocking network I/O and high concurrency with fewer request threads:

~~~java
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.dynamodb.DynamoDbAsyncClient;
import software.amazon.awssdk.services.dynamodb.model.DescribeTableRequest;
import software.amazon.awssdk.services.dynamodb.model.DescribeTableResponse;

DynamoDbAsyncClient db = DynamoDbAsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

CompletableFuture<DescribeTableResponse> future =
        db.describeTable(DescribeTableRequest.builder()
                .tableName("Orders")
                .build());

future.thenAccept(response ->
        System.out.println(response.table().tableStatus()));
~~~

In server applications, handle errors with `exceptionally`/`handle` or compose futures; do not call `join()` immediately on the event-loop/request thread if your goal is non-blocking execution. Close the client at lifecycle shutdown.

### 13.3. Async Does Not Mean Every Operation Is Non-Blocking

Async HTTP I/O does not guarantee the entire SDK pipeline is non-blocking. Steps such as credential retrieval, SigV4 signing, endpoint discovery, or user callbacks may perform blocking or CPU-bound work. Design thread pools, callback execution, and backpressure carefully; avoid heavy blocking work directly on the Netty event-loop.

### 13.4. Choosing a Client by Application Architecture

| Application Type | Common Choice |
|---|---|
| Spring MVC / traditional servlet | Sync clients |
| Spring WebFlux / reactive integration | Async clients, appropriate adapters |
| Single-threaded batch job | Sync clients |
| Fan-out across many service calls | Async clients if futures can be composed |
| Simple Lambda handler | Sync client is usually sufficient; reuse client |
| High-throughput S3 transfers | Evaluate S3 Transfer Manager/CRT |

Do not choose async simply because it is "newer". Compare throughput, tail latency, memory, thread utilization, and code complexity on real workloads.

## 14. Request/Response Models and Error Handling

SDK v2 uses immutable models and the **builder pattern**. For example:

~~~java
GetItemRequest request = GetItemRequest.builder()
        .tableName("Orders")
        .key(key)
        .consistentRead(true)
        .build();

GetItemResponse response = dynamoDb.getItem(request);
~~~

Once built, a request should not be treated as a mutable bean. Create a new request or a new builder for each call, and avoid sharing mutable builders across threads.

### 14.1. Exception Hierarchy

| Exception Type | Meaning | Example Handling |
|---|---|---|
| `SdkException` | Base SDK exception | Catch at boundary if needed |
| `AwsServiceException` | AWS service returned an error response | Read status, error code, request ID |
| `DynamoDbException`, `S3Exception` | Service-specific exceptions | Branch on business/service errors |
| `SdkClientException` | Client/network/credentials/config error | Check DNS, TLS, credentials, timeout |
| `ConditionalCheckFailedException` | Conditional write failed | Handle conflict/business rule |
| `ProvisionedThroughputExceededException` | DynamoDB throttling/capacity | Retry with backoff, inspect hot keys/capacity |

### 14.2. Service Errors Differ from Client Errors

- A service error includes an HTTP status/error code and a request ID from AWS—for example, `AccessDeniedException`, `ResourceNotFoundException`, or `ThrottlingException`.
- A client error can come from network timeouts, TLS handshakes, credentials providers, Region config, or serialization before the request is sent.
- Do not retry all exceptions uniformly. Validation/authorization errors usually require fixing the request or policy; transient throttling/network errors can be retried according to policy.
- Log the request ID, service, operation, Region, and error code; **never log credentials, authorization headers, raw PII payloads, or secrets**.

## 15. Retry Strategy and Timeouts: Version Changes

SDK v2 includes a built-in retry mechanism. The retry strategy classifies transient/throttling errors, backoff, and circuit-breaking behavior. Configuration must be set when building the client.

### 15.1. Default Retry Starting in v2.58.0

Starting with **AWS SDK for Java 2.x version 2.58.0**, the **Standard retry strategy** became the default. According to current documentation:

- Many service clients perform up to **3 attempts total** (including the initial call).
- DynamoDB clients default to up to **4 attempts total** under the Standard/Adaptive strategy.
- Throttling retries use dedicated backoff; a circuit breaker can halt retries when downstream continually fails.
- The Legacy strategy retains older behavior if a workload requires compatibility, but should not be selected just for a higher retry count without measurement.

Defaults may change in future SDK releases. Check the release notes and retry strategy docs for the exact SDK version your project pins.

### 15.2. Configuring Timeouts and Retry Mode

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.retry.RetryMode;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient db = DynamoDbClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .overrideConfiguration(o -> o
                .apiCallTimeout(Duration.ofSeconds(30))
                .apiCallAttemptTimeout(Duration.ofSeconds(8))
                .retryStrategy(RetryMode.STANDARD))
        .build();
~~~

`apiCallAttemptTimeout` bounds a single attempt; `apiCallTimeout` bounds the entire logical API call, including attempts and retry delays. Set the attempt timeout smaller than the overall timeout so there is room for retries. These values are examples; choose budgets based on SLAs, service latency, and business deadlines.

### 15.3. Retries Do Not Automatically Make Every Operation Idempotent

A retry can happen when the service received the request but the client lost the response. For certain write APIs, repeating the same request can cause duplicate side effects if the service or application does not support idempotency. Use:

- API idempotency tokens when available.
- Stable business request/operation IDs.
- Conditional writes and unique constraints.
- Transactional outbox/inbox for event processing.
- Reconciliation when write outcomes are uncertain.

SDK retry is a **transport/service-call mechanism**, not a substitute for business idempotency.

### 15.4. Avoiding Retry Storms

Never set unlimited max attempts, never retry validation or access denied errors, and never stack a custom application retry loop on top of SDK retries without accounting for total attempts. If the SDK retries 4 times and the application retries 5 times, a single business request can generate up to 20 network attempts (or more with nested calls). Monitor retries/throttles and apply bounded exponential backoff with jitter at the right layer.


## 16. Configuring Service Clients and HTTP Transport

A service client is configured through its builder. A typical configuration includes:

- **Region** and credentials provider.
- HTTP client/connection pool, proxy, TLS, and socket settings.
- API call timeout, attempt timeout, and retry strategy.
- Endpoint override (only when the use case genuinely requires it).
- Metrics/interceptors/logging per observability policy.

### 16.1. Configuring a Synchronous HTTP Client

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.apache5.Apache5HttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(Apache5HttpClient.builder()
                .maxConnections(100)
                .connectionTimeout(Duration.ofSeconds(5))
                .socketTimeout(Duration.ofSeconds(20)))
        .overrideConfiguration(o -> o
                .apiCallTimeout(Duration.ofSeconds(30))
                .apiCallAttemptTimeout(Duration.ofSeconds(10)))
        .build();
~~~

This is an illustrative configuration, not optimal values for every application. `maxConnections`, connect/socket timeouts, and API timeouts must match traffic, latency SLOs, server request timeouts, and retry budgets.

### 16.2. Configuring an Asynchronous Netty HTTP Client

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3 = S3AsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(200)
                .connectionTimeout(Duration.ofSeconds(5))
                .readTimeout(Duration.ofSeconds(30)))
        .build();
~~~

Excessively high concurrency can increase memory usage, open sockets, downstream throttling, and connection contention. Apply proper backpressure and limits; raising `maxConcurrency` does not give an AWS service infinite capacity.

### 16.3. One Shared HTTP Client or One Client Per Service?

A service client can own its own HTTP client, or an HTTP client object can be shared across multiple service clients if configurations and lifecycles are compatible. When sharing, the developer is responsible for closing it at the right time and not closing it while another client is still using it. The simplest approach is letting each service client manage its own transport unless measured optimization warrants sharing.

### 16.4. Choosing URLConnection for Lightweight Applications

`UrlConnectionHttpClient` fits simple synchronous use cases, but does not support async clients. When selecting it:

- Add the `url-connection-client` dependency.
- Exclude other HTTP implementations only after confirming they are unused.
- If an async service client is also present, add a separate async HTTP provider.
- Measure actual cold start, TLS, connection behavior, and throughput.

Do not blindly copy exclusions from old examples. The `apache-client` artifact is the legacy name; for SDK v2.46.0 and later, the current Apache HTTP client is `apache5-client`.

## 17. Spring Boot Integration: Creating Client Singleton Beans

Spring applications typically declare each AWS service client as a **singleton bean**. Spring manages dependency injection and closes the client when the ApplicationContext shuts down.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class AwsSdkConfiguration {

    @Bean(destroyMethod = "close")
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

Services use constructor injection:

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Service
public class OrderRepository {
    private final DynamoDbClient dynamoDb;

    public OrderRepository(DynamoDbClient dynamoDb) {
        this.dynamoDb = dynamoDb;
    }

    // Business methods calling DynamoDB through the shared client.
}
~~~

In production, read the Region from external configuration/profiles per environment (dev/staging/prod) rather than duplicating strings across classes. For multiple Regions, create named/qualified beans with a clear routing policy.

### 17.1. Spring Boot BOM and AWS SDK BOM

If the project uses Spring Boot dependency management:

- Keep the Spring Boot BOM for Spring modules.
- Import the AWS SDK BOM for `software.amazon.awssdk`.
- If using Spring Cloud AWS, import the BOM compatible with your Spring Boot version; this is a separate project dependency.
- Inspect the effective POM or Gradle `dependencyInsight` if an artifact is managed by multiple BOMs.

Do not upgrade `spring-cloud-aws` or the AWS SDK independently without checking the integration version's compatibility matrix and release notes.

## 18. Lambda, ECS, and EC2: Runtime Credentials and Lifecycle

### 18.1. AWS Lambda

In Lambda, the execution role grants permissions to the function. The SDK uses the provider chain to obtain temporary role credentials; do not close the client after every invocation. Create the service client during static initialization to reuse it within the execution environment:

~~~java
public final class Handler {
    private static final S3Client S3 = S3Client.builder()
            .region(Region.of(System.getenv("AWS_REGION")))
            .build();

    public Response handleRequest(Request request, Context context) {
        // Use the S3 client initialized outside the handler.
        return process(request, S3);
    }
}
~~~

Lambda environments can be recycled at any time; do not rely on static memory as durable business state storage. Choose the HTTP transport and dependencies to balance cold start, connection reuse, and request duration. For functions calling only sync APIs, URLConnection can trim some dependencies; measure before changing.

### 18.2. ECS/Fargate

Assign a **task role** to the task definition. The SDK credential chain reads container credentials provided by the runtime. Never put IAM user access keys in task environment variables. In private subnets, networking requires a path to regional service endpoints via NAT or the corresponding VPC endpoints; the SDK does not create network routes automatically.

### 18.3. EC2

Assign an instance profile role to the EC2 instance. The SDK can fetch temporary credentials via IMDS; protect IMDS and restrict IMDSv1 according to your security baseline. Never log credential responses or pass role credentials through environment variables.

### 18.4. EKS

Prefer EKS Pod Identity or IRSA depending on cluster/namespace/service account configuration. The SDK needs the modules/providers matching the chosen identity mechanism and a valid trust policy. Do not confuse the node IAM role with the application pod's dedicated role.

## 19. SDK v1 and v2: Identification and Migration Path

AWS SDK for Java **1.x reached end-of-support on December 31, 2025**. Existing applications can still run on already-released versions, but v1 no longer receives updates or releases. New projects should use v2; systems still running v1 need a controlled upgrade plan.

| Aspect | SDK v1 | SDK v2 |
|---|---|---|
| Maven groupId | `com.amazonaws` | `software.amazon.awssdk` |
| Service artifact | `aws-java-sdk-s3` | `s3` |
| BOM | `aws-java-sdk-bom` | `bom` |
| Client example | `AmazonS3` | `S3Client` |
| Request construction | Mutable models / `with` methods common | Immutable models + builders |
| Async APIs | Varies by client/API | Async clients return `CompletableFuture` |
| HTTP client | Fewer built-in options | Pluggable HTTP implementations |
| Dependency modules | Typically service artifacts in v1 namespace | Modular artifacts + shared core |
| Support lifecycle | End-of-support 2025-12-31 | Actively maintained |

### 19.1. Coexistence During Transition

An application can temporarily use v1 and v2 side by side if dependencies do not conflict and code is isolated. The two SDKs use separate namespaces and separate BOMs:

- V1 BOM: `com.amazonaws:aws-java-sdk-bom`.
- V2 BOM: `software.amazon.awssdk:bom`.

However, avoid building new architecture that permanently depends on both. Break migration down by service or module—migrate individual service clients first, keep internal application APIs stable, and verify behavior before removing v1.

### 19.2. Common Code Changes

- `AmazonS3` → `S3Client`.
- Mutable request/`withBucketName` → immutable request builder.
- Credentials/Region classes change packages and APIs.
- Exception types, paginators/waiters, and async APIs change.
- S3 transfer utilities and DynamoDBMapper/high-level APIs have separate migration paths.

AWS provides an **OpenRewrite-based migration tool** to transform many service client patterns, though it does not transform every high-level API. For example, DynamoDBMapper and some specialized APIs require manual migration. Always run a dry-run, review diffs, add tests, and scan for remaining v1 imports.

### 19.3. Finding Remaining v1 Usage

- Search source imports for `com.amazonaws.services.`.
- Check the Maven/Gradle dependency tree for `com.amazonaws:aws-java-sdk-*`.
- Check logs for v1 deprecation warnings in releases that emit warnings.
- For fat JARs or container images, inspect nested libraries; a single module's dependency tree may not reveal shaded or nested artifacts.

## 20. Upgrading the SDK BOM Safely

Upgrading the BOM version is a **dependency upgrade** that requires reviewing release notes and testing both compilation and runtime.

Recommended process:

1. Select an approved version; pin an explicit version and avoid dynamic versions.
2. Bump the BOM version in one place (parent POM/platform plugin).
3. Verify that all SDK modules in the dependency graph align to the same SDK version.
4. Read release notes, deprecations, Java runtime compatibility, and default behavior changes (especially retry/HTTP).
5. Run compile, unit, and integration tests, and verify against an appropriate AWS sandbox or LocalStack.
6. Check startup/cold start, TLS/HTTP pools, P95/P99 latency, retries, and throttling.
7. Deploy via canary/staged rollout and monitor CloudWatch/application telemetry.
8. Keep a rollback version and build artifact for reproducibility.

**Never just bump the BOM and assume there are no behavioral changes.** The SDK can change default retry strategies, HTTP implementation artifacts, service models, or API behavior between releases.



## 21. Troubleshooting Dependencies and Runtime

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `NoSuchMethodError` | SDK shared modules have mismatched versions | Dependency tree, BOM, convergence rule |
| `NoClassDefFoundError` | Missing service/HTTP module at runtime | Compile/runtime scopes and packaging |
| `ClassNotFoundException` for HTTP provider | Missing `apache5-client`/`netty-nio-client` or excluded dependency | HTTP transport artifacts |
| Maven reports missing version for `s3` | BOM not imported with right scope/type or wrong groupId | Effective POM, `dependencyManagement` |
| Gradle selects SDK version higher than BOM | `platform` constraint is a recommendation and graph has higher request | `dependencyInsight`; consider `enforcedPlatform` |
| Runtime downgrade after `enforcedPlatform` | Forced version is lower than API needed by another dependency | Update BOM, verify compatibility |
| Client cannot find Region | No explicit/env/profile/IMDS Region | Region chain and deployment config |
| `Unable to load credentials` | Chain finds no provider or SSO token expired | Profile/SSO login/IAM role/metadata |
| `AccessDeniedException` | Role lacks action/resource or resource policy denies | Caller identity, IAM policy, SCP, endpoint policy |
| TLS/connection timeout | DNS, proxy, SG/NACL, VPC endpoint, HTTP pool | Network path and HTTP configuration |
| Too many retries/throttling | Hot key, request burst, stacked retry budgets | CloudWatch, SDK retry config, backpressure |
| Client connection pool exhausted | Too many clients created or mismatched pool sizing | Client reuse, resource lifecycle |
| Async requests do not scale | Callbacks blocking event loop, mismatched thread pool/buffers | Profiling, backpressure, completion executor |
| Cold start increases after adding SDK | Too many modules/HTTP providers added, classpath scanning | Keep only needed modules, measure startup |
| AWS SDK v1 warning | v1 artifact still present in graph/runtime | Search `com.amazonaws:aws-java-sdk-*`, migration plan |
| LocalStack signature error | Region/credentials/signing/endpoint mismatch | Configure appropriate test endpoint and credentials |

### 21.1. Distinguishing Build Errors from Runtime Errors

- **Build-time:** Maven fails to resolve the BOM, artifact not found, version conflict, compiler rejects API. Inspect effective POM, repositories, compiler JDK, and dependency tree.
- **Classpath/runtime:** missing class, `NoSuchMethodError`, or HTTP provider fails to load. Inspect packaged JAR/container libs, dependency convergence, and shading.
- **Authentication:** credentials chain finds nothing or IAM denies access. Check `GetCallerIdentity`, role trust, and resource policies.
- **Network:** timeout/TLS/DNS. Check endpoints, VPC routes, SG/NACL, proxy, and HTTP transport.
- **Service behavior:** throttling, validation, resource not found. Inspect service error code/request ID and CloudWatch.

Do not fix `NoSuchMethodError` by randomly adding a new version of a core dependency. Find which module is pulling in the mismatched version and fix the **root cause in the dependency graph**.


## 22. Lab: Setting Up a Project Using the AWS SDK v2 BOM

### 22.1. Lab A — Maven

Create a new Java project or use a sandbox project:

1. Import `software.amazon.awssdk:bom` in `dependencyManagement`.
2. Add `s3` and `dynamodb` without individual versions.
3. Add the HTTP transport matching the sync/async client chosen in the lab.
4. Add Maven Enforcer `dependencyConvergence` scoped only to group `software.amazon.awssdk`.
5. Run:

~~~bash
mvn validate
mvn dependency:tree -Dincludes=software.amazon.awssdk
mvn help:effective-pom
mvn test
~~~

Expected verification: SDK v2 modules resolve from the BOM, the HTTP provider is present on the runtime classpath, and no module has an unintended version override.

### 22.2. Lab B — Gradle

1. Import the BOM using `platform("software.amazon.awssdk:bom:2.59.1")`.
2. Add `s3` and `dynamodb`.
3. Inspect the graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency software.amazon.awssdk:s3 --configuration runtimeClasspath
./gradlew dependencyInsight --dependency software.amazon.awssdk:dynamodb --configuration runtimeClasspath
~~~

4. Add a test dependency in the sandbox that requests a different SDK version and observe which version Gradle selects.
5. Compare `platform` with `enforcedPlatform` and explain why an enforced platform can downgrade a transitive dependency.

### 22.3. Lab C — Client and Credentials

1. Use an AWS CLI SSO sandbox profile and verify `aws sts get-caller-identity`.
2. Create a `DynamoDbClient` or `S3Client` with an explicit Region and the default credentials chain.
3. Call a read operation on an authorized resource.
4. Log operation name, request ID, latency, and consumed capacity if supported by the service; do not log item PII/secrets.
5. Re-run with a role lacking permissions to observe the service authorization error.
6. Close the client on application shutdown.

**You do not need to create buckets/tables or write real data to complete the dependency-management section.** If running write operations, only use a sandbox with confirmed budget and cleanup.

### 22.4. Lab D — Analyzing a Version Conflict

Suppose the runtime graph contains:

~~~text
software.amazon.awssdk:s3:2.59.1
software.amazon.awssdk:dynamodb:2.59.1
software.amazon.awssdk:aws-core:2.51.0
software.amazon.awssdk:sdk-core:2.59.1
~~~

Answer:

- Can the build succeed? Possibly, depending on resolution.
- Is the graph convergent? No.
- Does the BOM automatically block all overrides? No.
- How should it be resolved? Find the dependency pulling `aws-core:2.51.0`, remove the override or upgrade the relevant dependency, enforce convergence, and run runtime tests.

## 23. Pre-Merge Review Checklist

### Dependency Management

- [ ] Is there exactly one AWS SDK v2 BOM version for the application?
- [ ] Do service dependencies avoid declaring versions different from the BOM?
- [ ] Is the BOM placed properly in Maven `dependencyManagement` or Gradle `platform`?
- [ ] Is the SDK v1 BOM not confused with the SDK v2 BOM?
- [ ] Do dependencies under other groupIds (Lambda runtime, Spring, JUnit, CRT platform) have their own version management?
- [ ] Are dependency convergence checks or `dependencyInsight` inspections in place?
- [ ] Are dynamic versions/SNAPSHOTs avoided for production releases unless governed by policy?

### Runtime Architecture

- [ ] Are only the needed service modules declared?
- [ ] Does the HTTP transport match sync/async usage?
- [ ] Are clients reused and closed properly at lifecycle shutdown?
- [ ] Are Region/endpoints sourced from explicit configuration?
- [ ] Do credentials use IAM roles/SSO/temporary credentials rather than hardcoded keys?
- [ ] Are IAM least privilege and VPC/network policies properly applied?
- [ ] Do timeout/retry budgets match SLAs and idempotency guarantees?
- [ ] Are logs free of credentials, tokens, secrets, or raw PII?
- [ ] Do metrics/tracing capture request IDs, operation, latency, retries, and throttles?
- [ ] Have SDK v1 migration/support lifecycle plans been checked if any v1 dependency remains?

### Upgrade/Release

- [ ] Have release notes and breaking/default changes been reviewed?
- [ ] Do compile, unit, and integration tests pass?
- [ ] Does the packaged runtime artifact include the required HTTP provider?
- [ ] Are staging/canary latency, error rate, retry rate, and cold start monitored?
- [ ] Are a rollback version and reproducible build artifact available?

## 24. Self-Assessment Questions

1. Is AWS SDK for Java v2 one monolithic JAR or a collection of modules?
2. What responsibilities does a service client handle in the request pipeline?
3. How do `groupId` and `artifactId` differ?
4. What is a BOM and where is it imported in Maven?
5. Why can service dependencies omit versions after importing the BOM?
6. Does the BOM automatically add S3/DynamoDB modules to a project?
7. Does the AWS SDK v2 BOM manage `com.amazonaws:aws-lambda-java-core`?
8. How does `platform` in Gradle differ from `enforcedPlatform`?
9. Why can `enforcedPlatform` cause a runtime downgrade?
10. How does Maven Enforcer detect version divergence?
11. Which Gradle command shows why a specific SDK version was selected?
12. Why should you declare only the service modules the application actually uses?
13. How do `S3Client` and `S3AsyncClient` differ in execution model?
14. Does an async client guarantee every part of the pipeline is non-blocking?
15. Why should service clients be singletons/long-lived?
16. Which sources does the credentials provider chain check?
17. Do the Region provider chain and credentials chain have the same responsibility?
18. Why should production use task roles/instance profiles instead of access keys?
19. When should you use `apache5-client`, `url-connection-client`, or `netty-nio-client`?
20. Why is `url-connection-client` insufficient for async clients?
21. How does API attempt timeout differ from API call timeout?
22. Do SDK retries make all write operations idempotent?
23. What changed with default retries starting in SDK v2.58.0?
24. Why is `NoSuchMethodError` often a sign of a misaligned dependency graph?
25. When did AWS SDK for Java v1 reach end-of-support?
26. Does the v1-to-v2 migration tool automatically convert every high-level API?
27. Why should LocalStack endpoints never be placed in production config?
28. What information should be logged to debug the SDK without exposing secrets?

### Answer Key Outline

- **Architecture:** Service module + generated models + shared core/auth/protocol + HTTP transport + regional endpoint.
- **BOM:** Import `software.amazon.awssdk:bom`; omit versions on individual SDK modules; BOM does not auto-add modules or manage every groupId.
- **Convergence:** Maven Enforcer/Gradle `dependencyInsight` inspect the graph; `enforcedPlatform` can force/downgrade versions.
- **Client runtime:** Thread-safe, immutable, reused; credentials/Region chains are independent; match sync/async HTTP transport to workload.
- **Reliability:** Retry/timeouts have budgets; idempotency is a business responsibility; observe request IDs, latency, errors, and retries.
- **Migration:** SDK v1 end-of-support 2025-12-31; v2 brings modular architecture, builders, and async APIs, requiring review and testing during migration.


## 25. Official AWS and Build Tool Documentation

1. [AWS SDK for Java documentation](https://docs.aws.amazon.com/sdk-for-java/) — Developer Guide, API Reference, and Migration Guide.
2. [Set up a Maven project for AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup-project-maven.html) — Import BOM, add modules, Maven Enforcer.
3. [Set up a Gradle project for AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup-project-gradle.html) — Kotlin/Groovy DSL, platform, and enforcedPlatform.
4. [Configuring service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/configuring-service-clients.html) — Client builders, singleton, Region, credentials, retry, timeout, HTTP.
5. [Making service requests](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/work-witih-clients.html) — Service client behavior.
6. [Use singleton service client instances](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/singleton-service-clients.html) — Thread safety, connection pools, reuse.
7. [Credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — Default credential sources.
8. [Using credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html) — SSO, profiles, role providers, temporary credentials.
9. [Setting the AWS Region](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html) — Region provider chain.
10. [Configure service clients in code](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/configuring-service-clients-code.html) — HTTP/configuration builders.
11. [Configure HTTP clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html) — Sync/async HTTP transports.
12. [URLConnection-based HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-url.html) — Lightweight synchronous transport.
13. [Apache 5 HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-apache5.html) — Apache5 transport configuration and lifecycle.
14. [Programming asynchronously](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html) — CompletableFuture and non-blocking I/O.
15. [Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html) — Standard/Legacy/Adaptive and default behavior.
16. [Troubleshooting the AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html) — Classpath/version conflicts and runtime issues.
17. [SDK v1-to-v2 migration guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration.html) — API and architecture differences.
18. [Migration tool](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration-tool.html) — OpenRewrite automation and limitations.
19. [AWS SDK for Java v1 end-of-support announcement](https://aws.amazon.com/blogs/developer/announcing-end-of-support-for-aws-sdk-for-java-v1-x-on-december-31-2025/) — Lifecycle through 2025-12-31.
20. [AWS SDK for Java v2 GitHub repository](https://github.com/aws/aws-sdk-java-v2) — Source, releases, BOM, and versioning information.
21. [Maven dependency management](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — `dependencyManagement` and imported BOM.
22. [Maven Enforcer dependency convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html) — Detect conflicting transitive versions.
23. [Gradle platforms](https://docs.gradle.org/current/userguide/platforms.html) — Platform constraints and enforced platforms.

> **Final Takeaway:** AWS SDK for Java 2.x is a collection of modules with a shared core and service clients. **The BOM aligns versions**, while Maven Enforcer/Gradle dependency insight detect divergent graphs. At runtime, reuse thread-safe clients, choose the appropriate HTTP transport, use IAM temporary credentials, configure Region/timeouts/retries explicitly, and never assume SDK retries replace idempotency. Upgrading the BOM must go hand in hand with dependency review, testing, and runtime observability.
