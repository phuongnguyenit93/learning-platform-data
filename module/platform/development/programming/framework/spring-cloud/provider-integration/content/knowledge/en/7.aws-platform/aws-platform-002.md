# Choosing the Right BOM, Starters, and AWS SDK Generation

## 1. The Problem to Solve

In a Spring Boot project integrating Amazon S3, Amazon SQS, or AWS Secrets Manager, adding a dependency and compiling successfully is **not enough** to guarantee the application runs correctly. Spring Boot, AWSpring's Spring Cloud AWS, and the AWS SDK for Java each have their own release schedules, API sets, and compatibility requirements. An inconsistent choice easily leads to startup failures, missing beans, class conflicts, or runtime breakage.

This lesson belongs to the **AWS Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The goal of the module is to practice integrating Spring Boot with managed services across AWS, Azure, and Google Cloud—covering permissions, storage, messaging, data, secrets, testing, and provider comparison. This lesson focuses on the first decision in the AWS track: **choosing the right version set and dependency set before writing cloud access code**.

After this lesson, you will be able to:

- Distinguish the roles of a **BOM**, a **starter**, the **AWS SDK**, and direct dependencies.
- Identify the two generations of AWS SDK for Java through Maven coordinates, packages, and APIs.
- Select a compatible version set based on Spring Boot, Java, AWSpring, and the AWS services needed.
- Declare Maven/Gradle configurations so AWS modules use controlled versions.
- Detect dependency conflicts, prepare a migration plan, and verify the application across test layers.

> **Version note:** The configuration snippets in this lesson illustrate the **Spring Boot 3.x / Spring Cloud AWS 3.x / AWS SDK for Java 2.x** line. They do not imply that every version sharing the same major number is compatible. You must replace placeholders with **specific release versions** and consult the compatibility documentation for the chosen AWSpring version before running; if the project is on a newer Spring Boot generation, use that generation's compatibility table.

## 2. Four Layers of Dependency Decisions

A project may have Spring Boot, AWSpring, and the AWS SDK on the classpath together, but each component has a distinct responsibility.

| Component | Role | Examples | What it does not do automatically |
| --- | --- | --- | --- |
| Spring Boot | Runtime foundation for Spring applications, auto-configuration, and core starters | `spring-boot-starter-web`, `spring-boot-starter-actuator` | Does not automatically provide all AWS integrations |
| AWSpring / Spring Cloud AWS | Integrates AWS services into Spring via configuration, templates, and listeners | `spring-cloud-aws-starter-s3`, `spring-cloud-aws-starter-sqs` | Does not replace the entire SDK or pre-create IAM permissions |
| AWS SDK for Java | Clients calling AWS APIs, signing requests, handling responses, retries/networking | `software.amazon.awssdk:s3`, `software.amazon.awssdk:sqs` | Does not automatically turn AWS APIs into Spring listeners/templates |
| BOM (Bill of Materials) | Manages the **versions** of a related set of dependencies | `spring-cloud-aws-dependencies`, `software.amazon.awssdk:bom` | Does not automatically add S3/SQS modules to the application |

There are two separate questions:

1. **Which features are needed?** Choose the right starter or SDK module and add it to the dependencies section.
2. **Which versions should be used?** Choose a version set managed by Spring Boot dependency management and the relevant BOMs.

**A BOM is not a starter.** Importing a BOM lets you omit `<version>` on dependencies managed by that BOM; it does not make `S3Template` or `@SqsListener` appear if you have not added the required starter. Conversely, adding a starter does not prove that versions across the entire classpath are consistent if overrides or older dependencies exist.

### 2.1. BOM in Maven and Platform in Gradle

In Maven, a BOM is typically imported into `<dependencyManagement>` with `type=pom` and `scope=import`. It specifies the version used when a corresponding dependency is declared without its own version.

In Gradle, you can use `platform("group:artifact:version")` or an equivalent dependency management mechanism to apply version constraints. Version constraints can interact with other constraints; always inspect the **resolved dependency graph** rather than inferring solely from the build file.

For example, importing a BOM that manages S3/SQS versions without declaring the S3 starter gives no reason to expect an `S3Template` bean to appear automatically.

## 3. Identifying AWS SDK for Java Generations

AWS provides two Java SDK families with similar names but different classes and designs.

| Criterion | AWS SDK for Java **1.x** | AWS SDK for Java **2.x** |
| --- | --- | --- |
| Maven group | `com.amazonaws` | `software.amazon.awssdk` |
| Typical S3 module | `aws-java-sdk-s3` | `s3` |
| S3 client | `com.amazonaws.services.s3.AmazonS3` | `software.amazon.awssdk.services.s3.S3Client` or `S3AsyncClient` |
| SQS client | `AmazonSQS` / `AmazonSQSAsync` | `SqsClient` / `SqsAsyncClient` |
| Request | Usually mutable objects with setters or constructors | Usually immutable objects built via `builder()` |
| Credentials | `AWSCredentialsProvider` | `AwsCredentialsProvider` |
| Async mechanism | SDK 1.x async API/architecture | Dedicated SDK 2.x asynchronous clients |
| Selection guidance for new code | Legacy generation, requires migration evaluation | Preferred generation for new integrations aligned with the modern ecosystem |

An S3 metadata read operation using SDK 2.x:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public final class ObjectMetadataService {
    private final S3Client s3Client;

    public ObjectMetadataService(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    public long sizeOf(String bucket, String key) {
        var request = HeadObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();
        return s3Client.headObject(request).contentLength();
    }
}
~~~

This example uses SDK 2.x's `S3Client`; you cannot simply swap the `S3Client` import for `AmazonS3` and keep the same builder and method chain. **Migrating SDK generations is an API change**, not merely changing a version number.

### 3.1. Relationship with Spring Cloud AWS

Among the commonly encountered lines:

- **Spring Cloud AWS 2.x** integrations tie to earlier Spring Boot/Spring Framework ecosystems and AWS SDK for Java **1.x**.
- **Spring Cloud AWS 3.x** integrations belong to modern AWSpring, use AWS SDK for Java **2.x**, and fit the Spring Boot **3.x** ecosystem when compatible versions are selected.
- When a project uses newer lines, do not apply a "same major version works" rule of thumb: check the compatibility matrix, release notes, Java baseline, and module support of the **exact release**.

Older Spring Cloud AWS library families may also appear under a different group/artifact than `io.awspring.cloud`. Check dependency metadata and code imports rather than relying only on the names "AWS" or "Spring Cloud".

**A common pitfall:** `com.amazonaws` and `software.amazon.awssdk` can appear together in the dependency graph because a legacy library still pulls in SDK 1.x. Maven/Gradle do not automatically treat these two groups as different versions of the same artifact for "newest wins" resolution. Both generations can coexist on the classpath, but that does **not** make their classes, credential providers, or listeners interchangeable. Do not mix both unintentionally; if both must exist during a migration period, clearly define which component owns which client and thoroughly test both runtime paths.

## 4. Process for Selecting a Version Set

Do not start from a random dependency snippet on a forum. Select in order:

~~~mermaid
flowchart TD
    A[Project Java and Spring Boot version] --> B[Check AWSpring compatibility documentation]
    B --> C[Choose a specific Spring Cloud AWS release]
    C --> D[Choose BOM and starters by service]
    D --> E[Verify AWS SDK generation and managed versions]
    E --> F[Analyze resolved dependency graph]
    F --> G{Conflicts or legacy APIs?}
    G -->|Yes| H[Adjust dependencies / plan migration]
    H --> F
    G -->|No| I[Test startup, integration, and AWS permissions]
~~~

### Step 1: Lock Down the Project Baseline

Identify:

- The **Java/JDK** version used for compiling and running.
- The accompanying **Spring Boot** and **Spring Framework** versions.
- Whether the application uses a **Spring Cloud release train** for other features.
- Which AWS dependencies already exist; whether any legacy library keeps SDK 1.x or an older Spring Cloud AWS version.
- Business targets: S3, SQS, SNS, Secrets Manager, Parameter Store, or AWS APIs without a suitable starter.

Spring Boot 3.x uses Spring Framework 6 and a Java 17 baseline, bringing `jakarta.*` differences compared to many older libraries based on `javax.*`. When upgrading from Boot 2.x, errors can originate from **Spring/Jakarta** rather than only from the AWS SDK.

### Step 2: Select a Compatible AWSpring Release

Check **AWSpring** release documentation, dependency management, and support matrix. Answer:

- Which Spring Boot/Spring Framework versions does this release support?
- What is the minimum Java requirement?
- Are the starters for S3, SQS, Secrets Manager, Parameter Store, etc. available, and what namespace do their APIs use?
- Which AWS SDK 2.x version is managed? Are there any critical security or compatibility notes?

This step is necessary even when the project only upgrades a minor or patch version. Do not rely solely on the similarity of the `3.x` number.

### Step 3: Choose Starters Based on **Features Actually Used**

| Need in the Spring Boot application | AWSpring dependency to consider | Typical Spring APIs used |
| --- | --- | --- |
| Read/write objects in S3 | `io.awspring.cloud:spring-cloud-aws-starter-s3` | `S3Template`, SDK client bean |
| Send/receive SQS messages | `io.awspring.cloud:spring-cloud-aws-starter-sqs` | `SqsTemplate`, `@SqsListener` |
| Publish SNS events | `io.awspring.cloud:spring-cloud-aws-starter-sns` | SNS integration if supported by the release |
| Read secrets as configuration | `io.awspring.cloud:spring-cloud-aws-starter-secrets-manager` | Spring Config Data / application configuration |
| Read parameters from Systems Manager | `io.awspring.cloud:spring-cloud-aws-starter-parameter-store` | Spring Config Data / application configuration |
| Call AWS operations without a suitable template | AWS SDK v2 module, e.g. `software.amazon.awssdk:sts` | SDK clients and request/response types |

Exact starter names, capabilities, and configurations must be verified against the chosen release. Do not add every starter "just in case", because each starter can enable additional auto-configurations, beans, properties, and dependencies.

**When is AWSpring unnecessary?** A non-Spring Java CLI querying DynamoDB or a Spring Boot service calling only a single specialized SDK operation can use AWS SDK 2.x directly. Add AWSpring only when you genuinely need the benefits of Spring integration.

### Step 4: Keep One Version Management Source, Limit Overrides

For applications using AWSpring, use the **AWSpring BOM** as the version management source for Spring Cloud AWS modules. For SDK modules, inspect the version resolved by the BOM/graph before deciding whether to additionally import the AWS SDK BOM or override a module.

If a project has the Spring Boot BOM, Spring Cloud BOM, and AWSpring BOM, check the final versions actually selected by Maven/Gradle. Importing multiple BOMs does not guarantee every artifact is managed as intended; precedence and override rules differ by tool and declaration style.

### Step 5: Pin Specific Versions and Test

Do not use dynamic versions like `latest.release` or `3.+` for reproducible builds. Record the resolved Spring Boot, AWSpring, and SDK module releases in project documentation or dependency locks; update in a controlled manner with CI. After changing a BOM, re-run integration tests across critical AWS flows.

## 5. Maven Configuration When Using AWSpring

Suppose a Spring Boot 3.x service needs S3 and SQS operations. The Maven configuration below assumes the project **already has** `spring-boot-starter-parent` or an appropriate Spring Boot dependency management setup.

### 5.1. Import the AWSpring BOM

~~~xml
<properties>
    <!-- Replace with a specific AWSpring release confirmed compatible with Boot/JDK -->
    <spring-cloud-aws.version>CHOOSE_COMPATIBLE_RELEASE</spring-cloud-aws.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`CHOOSE_COMPATIBLE_RELEASE` is a **placeholder**, not a valid version to use as-is. Replace it with an actual release number after checking the compatibility matrix. In Maven, adding only the `dependencyManagement` block without adding dependencies will **not** pull in the S3/SQS starters for use.

### 5.2. Add the Right Starters and Direct SDK Modules When Needed

~~~xml
<dependencies>
    <!-- Spring integration for S3 -->
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>

    <!-- Send and receive messages via SQS using Spring -->
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>

    <!-- If application source code directly imports SDK S3Client -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

Most starters pull in the required SDK modules **transitively**, but if the application's own source code uses the `S3Client` type, declaring a direct dependency on the SDK S3 module expresses the design explicitly and avoids implicit reliance on the starter's transitive structure. The condition is that the version of `software.amazon.awssdk:s3` must actually be managed by dependency management. If the build reports a missing version, inspect the BOM and dependency management setup before pinning an arbitrary version yourself.

An application using the SDK directly will import types under `software.amazon.awssdk.*`:

~~~java
import io.awspring.cloud.s3.S3Template;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import software.amazon.awssdk.services.s3.S3Client;
~~~

`S3Template` and `SqsTemplate` are provided by AWSpring; `S3Client` is provided by SDK 2.x. They can coexist in a Spring Boot service with compatible starters and versions.

### 5.3. Adding an SDK Module for a Service Without a Starter

For example, a service that only needs to call AWS STS to inspect the active identity can add the `sts` SDK module:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sts</artifactId>
</dependency>
~~~

SDK v2 lets you pick modules per service without "importing the entire AWS SDK". If the application has other Spring integration needs, it can still use AWSpring starters at the same time.

## 6. If Using Only AWS SDK 2.x: Choosing the SDK BOM

For a project **not using Spring Cloud AWS**, such as a standalone Java job uploading to S3 or a Spring application with pure SDK adapters, you can directly import the AWS SDK v2 BOM:

~~~xml
<properties>
    <!-- Replace with a specific approved SDK v2 version -->
    <aws.sdk.version>CHOOSE_SDK_V2_RELEASE</aws.sdk.version>
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
        <artifactId>sqs</artifactId>
    </dependency>
</dependencies>
~~~

The properties above remain placeholders to be replaced with **real releases**. The SDK BOM keeps SDK modules (`s3`, `sqs`, `auth`, `regions`, `sdk-core`, etc.) aligned, reducing inconsistent versions.

**If you are already using AWSpring**, do not routinely import an additional SDK BOM with a newer version without evaluating it. Overriding into a misaligned SDK version group can cause linkage errors when AWSpring calls internal SDK APIs/contracts. When you need to upgrade the SDK for a specific security fix or bug, check release notes, compatibility, the effective dependency graph, and test S3/SQS/credentials paths.

## 7. Gradle Kotlin DSL Configuration

With Gradle, you can place the selected AWSpring release in `gradle.properties`:

~~~properties
springCloudAwsVersion=CHOOSE_COMPATIBLE_RELEASE
~~~

In `build.gradle.kts`, once the project has configured the Spring Boot plugin, Java plugin, and Maven Central repository:

~~~kotlin
val springCloudAwsVersion: String by project

dependencies {
    implementation(platform(
        "io.awspring.cloud:spring-cloud-aws-dependencies:$springCloudAwsVersion"
    ))

    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sqs")

    // Declare directly when source code imports the SDK client.
    implementation("software.amazon.awssdk:s3")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`platform(...)` applies version constraints to the relevant configuration. If using the `io.spring.dependency-management` plugin instead of (or alongside) Gradle native platforms, understand the precedence order of the chosen mechanism and check resolved versions. Do not copy multiple BOM import styles at once without a clear reason.

If **using only AWS SDK v2**, swap in the corresponding platform:

~~~kotlin
val awsSdkVersion: String by project

dependencies {
    implementation(platform("software.amazon.awssdk:bom:$awsSdkVersion"))
    implementation("software.amazon.awssdk:s3")
    implementation("software.amazon.awssdk:sqs")
}
~~~

`gradle.properties` needs `awsSdkVersion` set to an actual SDK version. Do not leave literals like `CHOOSE_COMPATIBLE_RELEASE` in committed builds.

## 8. Reading the Dependency Graph: How to Know the BOM Actually Works

Dependency errors do not happen only at compile time. Sometimes a build succeeds, but startup hits `NoSuchMethodError`, `NoClassDefFoundError`, or listeners fail to be created because the classpath mixes multiple generations.

### 8.1. Verification Commands for Maven

The commands below are for checking **inside your own project**, not commands already executed for this lesson:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

On Windows you can use `mvnw.cmd` instead of `./mvnw`. From the output, look for these groups:

- `io.awspring.cloud`: Spring Cloud AWS starters and modules must belong to the chosen release set.
- `software.amazon.awssdk`: AWS SDK v2 modules must have consistent managed versions.
- `com.amazonaws`: identify which library is pulling in SDK v1; do not delete blindly without knowing where it is used.
- `org.springframework`, `org.springframework.boot`: verify Spring libraries match the baseline.

`dependency:tree` shows which dependency paths pull in each module; `effective-pom` helps determine the versions resolved by dependency management after parent inheritance and BOM imports.

### 8.2. Verification Commands for Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency software.amazon.awssdk --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-aws --configuration runtimeClasspath
~~~

On Windows you can use `gradlew.bat`. `dependencyInsight` helps identify which dependency requested a version and why Gradle chose that version after applying constraints. Compare both compile and runtime classpaths if there are signs of divergence.

### 8.3. Result Reading Checklist

| Symptom | What to check | How to handle |
| --- | --- | --- |
| Multiple SDK v2 versions in declarations or complex graphs | Which module overrides the BOM? Which dependency requests another version? | Align modules to verified managed versions |
| Both `com.amazonaws` and `software.amazon.awssdk` present | Is an older library still using SDK v1? | Migrate or maintain an intentional temporary boundary |
| `NoSuchMethodError` when calling the SDK | Are the compiled API and runtime-loaded classes compatible? | Inspect resolved `runtimeClasspath` and actual SDK versions |
| `ClassNotFoundException` for `S3Template` | Missing AWSpring starter/module or the version lacks that API? | Add the proper starter and check imports/packages |
| `SqsTemplate` bean not created | Are the SQS starter, auto-configuration conditions, and config present? | Check the condition report, starter, and configuration |
| `javax.*` / `jakarta.*` errors on Boot upgrade | Incompatible legacy Spring dependency? | Align both the Spring stack and code using the namespace |
| 403 `AccessDenied` when calling AWS | Are role, policy, ARN, region, and KMS correct? | Check IAM/resource policies; a BOM does not grant permissions |

In particular, **a 403 is not automatically a dependency error**, and **a missing class is not automatically an IAM error**. Layer-by-layer diagnosis saves time.

## 9. Easy-to-Make Mistakes and How to Avoid Them

### 9.1. Declaring Individual Versions on Each SDK Module

For example, you **should not** pin SDK modules to arbitrary separate versions like this:

~~~xml
<!-- Anti-pattern example: do not follow -->
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
    <version>VERSION_A</version>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sqs</artifactId>
    <version>VERSION_B</version>
</dependency>
~~~

Some modules might still compile, but shared classes like `sdk-core`, `auth`, and HTTP transport can resolve unpredictably. Prefer using a BOM, overriding only for a specific reason and verifying at runtime.

### 9.2. Copying Examples from Older Spring Cloud AWS Versions

Old code may contain:

~~~java
// Example identifying legacy API:
import com.amazonaws.services.s3.AmazonS3;
// Some older Spring Cloud AWS libraries use different listener/template styles.
~~~

Whereas 3.x-generation integration code typically uses:

~~~java
import io.awspring.cloud.s3.S3Template;
import io.awspring.cloud.sqs.annotation.SqsListener;
import software.amazon.awssdk.services.s3.S3Client;
~~~

These imports are markers for migration checks. Do not change only package names and expect every property and lifecycle behavior to remain unchanged; on a major upgrade, also review configuration, listeners, conversion, acknowledgement, and runtime errors.

### 9.3. Mixing Spring Cloud BOM and AWSpring BOM Without Checking

The **Spring Cloud release train BOM** serves a set of Spring Cloud projects; the **AWSpring BOM** serves the Spring Cloud AWS suite. They are not the same artifact, and neither arbitrarily implies managing all desired AWSpring libraries. Explicitly verify which BOM manages which module and which version wins if rules overlap.

### 9.4. Adding Unnecessary Starters

Adding all S3/SQS/SNS/Secrets Manager starters can pull in extra HTTP clients, JSON converters, auto-configurations, and unused configuration requirements. Choose the smallest set of modules that satisfy requirements to keep classpath, footprint, and startup errors manageable.

### 9.5. Assuming a Newer SDK Solves AWS Permissions

Switching from SDK 1.x to 2.x does not create roles, policies, buckets, queues, secrets, or VPC endpoints. Both generations require proper identity and region. With SDK 2.x, you should normally let the credential chain discover temporary credentials from the workload's IAM role; avoid committing static access keys into configuration.

## 10. Upgrade Strategy from SDK 1.x and Legacy Spring Cloud AWS

A legacy project using Spring Boot 2.x, AWSpring 2.x, and `AmazonS3` usually cannot simply bump `aws-java-sdk-s3` to the `software.amazon.awssdk:s3` artifact. Simultaneous changes may involve the Java baseline, Spring Framework, Spring Boot, `javax`/`jakarta` namespaces, auto-configuration, and AWSpring APIs.

Controlled upgrade process:

1. **Inventory:** list legacy AWS dependencies, `com.amazonaws.*` imports, custom client beans, templates/listeners, properties, and tests.
2. **Choose target:** determine the Spring Boot and AWSpring release pair supported by the project maintainers; identify the JDK and managed AWS SDK 2.x version.
3. **Update build:** update the BOM/starters according to the version set, remove legacy dependencies **once callers have been migrated**; inspect the graph.
4. **Update code:** migrate SDK clients, request builders, exceptions, sync/async code; update listeners/templates and config per release documentation.
5. **Update tests:** verify serialization, SQS acknowledgement, S3 metadata, credentials provider, timeouts, retries, and exception mapping.
6. **Trial deployment:** run smoke tests on a dedicated testing account and role; monitor auth errors, latency, retries, and duplicate message indicators.

If a third-party library still uses SDK 1.x, consider upgrading or replacing that library. Both SDKs can coexist during a transition phase, but that coexistence must have an owner, a boundary, and a clear removal plan.

### Common Regression Areas

| Area | What to verify when upgrading |
| --- | --- |
| Client | `AmazonS3` → `S3Client`, `AmazonSQSAsync` → `SqsAsyncClient`, and async APIs |
| Request/response | Builders, field names, exception mapping, and pagination |
| Retry/timeout | SDK defaults and HTTP/client settings may differ |
| Serialization | SQS payload converters and types, JSON schema, headers |
| Listener | Concurrency, acknowledgement, failure behavior, visibility timeout |
| Credential/region | Default provider chain, profiles, assume-role, workload identity |
| Spring Boot | Java baseline, Spring Framework, `jakarta`, auto-configuration |

## 11. Connecting Dependency Choices to Security and Testing

The right library set is a necessary condition for calling the cloud, but it **does not replace verification in a real environment**.

### 11.1. Identity and Permissions

For a service that sends SQS messages and saves S3 files, permissions must be granted according to the actual operations used—for example, `s3:PutObject` on the target object prefix and `sqs:SendMessage` on the queue ARN. A consumer may need `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, and other permissions if the flow calls those operations. Bucket policies, queue policies, and KMS policies can also affect the outcome.

Choosing `spring-cloud-aws-starter-sqs` or `software.amazon.awssdk:sqs` **does not alter IAM evaluation rules**. On ECS, EKS, or EC2, choose credentials obtained from the workload's role; during local development, an appropriate profile can be used. Never store static access keys in the repository.

### 11.2. Layered Testing

| Layer | What it verifies | What it does not guarantee |
| --- | --- | --- |
| Build + dependency graph | Versions, classpath, and class availability at build time | AWS IAM/networking and service behavior |
| Unit tests | Business logic, adapters, and mappings with mocked SDK/templates | Real requests to S3/SQS |
| Emulated integration tests (e.g., LocalStack) | Spring wiring, endpoint calls, sending/receiving data within emulation scope | All IAM/KMS characteristics, quotas, timing, and AWS behavior |
| Smoke tests on dedicated AWS | Real credentials, roles, region, resource permissions, and end-to-end path | Every high-load failure or every edge case |

Especially after upgrading `@SqsListener`, test throwing an exception in the consumer, message redelivery, duplicate handling, and the DLQ mechanism. A test that only checks that the Spring context starts up does not prove the message flow operates safely.

## 12. Three Practical Selection Scenarios

### Scenario A: Spring Boot 3.x Needing S3 and SQS

- **Choose:** an AWSpring 3.x release **confirmed compatible with the specific Boot version**, import the AWSpring BOM, and add the S3 and SQS starters.
- **Add SDK directly:** only the modules where application code directly uses `S3Client`, `SqsAsyncClient`, or another client; use the verified managed version.
- **Verify:** resolved dependencies, created beans, credentials/region, S3 upload test, and SQS message retry handling.

### Scenario B: Java CLI Using Only S3

- **Choose:** AWS SDK for Java 2.x with `software.amazon.awssdk:bom` and the `s3` module.
- **Not needed:** Spring Boot or AWSpring if the program does not use Spring.
- **Verify:** credential provider, region, permissions, and closing client/network resources.

### Scenario C: Spring Boot 2.x Using Legacy Spring Cloud AWS and SDK 1.x

- **Do not upgrade haphazardly:** upgrading only one starter or SDK module to 3.x/2.x while the rest remains old.
- **Choose:** a synchronized upgrade path for Spring Boot/JDK and AWSpring according to compatibility; migrate imports and configuration per the release.
- **Verify:** whether legacy dependencies remain in the graph, re-test S3/SQS, Spring context, and simulated production operation.

## 13. Hands-On Exercise

A team has a Spring Boot project implementing a document-processing service:

- Users upload documents to **S3**.
- The service sends a notification message to **SQS**.
- A consumer uses `@SqsListener` to retrieve the message and save processing state.
- Some AWS metadata APIs must be accessed via direct SDK clients.
- Secrets are stored in **Secrets Manager**, and the workload role has a least-privilege IAM policy.

**Requirements:**

1. Record the target Java, Spring Boot, and AWSpring versions; specify the **compatibility source** to consult before locking the release.
2. Write the Maven or Gradle dependencies with the AWSpring BOM and required starters. If code directly imports SDK clients, declare the appropriate SDK module; explain why individual arbitrary versions should not be pinned.
3. Indicate which groups and packages distinguish Java SDK v1 and v2 in the dependency tree.
4. Explain the impact if a legacy library pulls in `com.amazonaws:aws-java-sdk-s3` while new code uses `software.amazon.awssdk:s3`. Propose a controlled migration approach.
5. Design checks for `NoSuchMethodError`, missing `SqsTemplate`, and `AccessDenied`; classify each failure as dependency, Spring auto-configuration, or IAM.
6. Write three test levels: adapter unit tests, integration tests with simulated S3/SQS, and a smoke test using a dedicated AWS role and resources; state the limitations of each level.

**Self-assessment hint:** A strong solution has **specific compatibility-checked versions**, uses the BOM for version management, adds starters only as needed, maintains a consistent SDK generation, and includes a plan to verify both the classpath and IAM. Simply listing a few lines of dependencies without explaining the selection rationale or verification steps is incomplete.

## 14. Summary

When integrating Spring Boot with AWS, choose libraries in the sequence **Java/Spring Boot baseline → compatible AWSpring release → BOM → use-case starters → required AWS SDK modules → dependency graph and runtime checks**. Spring Cloud AWS 3.x uses AWS SDK for Java 2.x; legacy code using `com.amazonaws` and `AmazonS3` requires a clear migration path. A BOM keeps modules on one version set, starters bring integration capabilities into Spring, while IAM, networking, S3/SQS behavior, and real-world testing remain system design and operational responsibilities.
