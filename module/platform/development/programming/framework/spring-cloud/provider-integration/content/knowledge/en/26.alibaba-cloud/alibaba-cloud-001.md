# Distinguishing Between Spring Cloud Alibaba and Alibaba Cloud Service Starters

## 1. Problem Statement and Learning Objectives

A Spring Boot application running on Alibaba Cloud may need to register services with Nacos, limit traffic with Sentinel, store files in Object Storage Service (OSS), send SMS, or access managed Redis. All of these requirements belong to the Alibaba Cloud ecosystem, yet they do not necessarily use the same set of dependencies.

The names **Spring Cloud Alibaba**, **Aliyun Spring Boot Starter**, and **Alibaba Cloud Java SDK** frequently appear side by side in documentation. They are related to one another, but they address different integration layers:

- **Spring Cloud Alibaba (SCA)** provides components following the Spring Cloud model for building distributed microservices: service discovery/configuration with Nacos, flow control with Sentinel, distributed transactions with Seata, and messaging with RocketMQ.
- **Aliyun Spring Boot Starters** provide auto-configuration and starters for individual Alibaba Cloud services such as OSS, SMS, Redis, RDS MySQL, or SchedulerX. This group focuses on consuming services from Spring Boot.
- **Alibaba Cloud Java SDK** is the product-specific client API. The application calls the SDK directly to use a service's features; you can wrap the client in a Spring bean or build a custom adapter if no suitable starter is available.

This lesson belongs to the **Alibaba Cloud** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services from AWS, Azure, Google Cloud, and Alibaba Cloud through their respective libraries; learners need to know how to configure identity/permissions, access storage, messaging, and data, protect secrets, write integration tests, and evaluate differences across providers.

After completing this lesson, you will be able to:

1. Distinguish the purpose and scope of Spring Cloud Alibaba, Aliyun Spring Boot Starters, and product SDKs.
2. Choose the right BOM, starter, and dependencies for a given problem.
3. Understand why the Spring Cloud Alibaba version does not automatically manage the versions of all Alibaba Cloud service SDKs.
4. Configure Nacos discovery and integrate OSS using either the SDK or a starter.
5. Select an appropriate RAM user, RAM role, STS, or OIDC mechanism for the runtime environment.
6. Test each integration layer and diagnose dependency, credentials, endpoint, region, or permission errors.

## 2. Three Integration Layers to Identify

~~~mermaid
flowchart TD
    APP["Spring Boot application"]
    SCA["Spring Cloud Alibaba<br/>Microservice integration"]
    STARTER["Aliyun Spring Boot Starters<br/>Service-specific auto-configuration"]
    SDK["Alibaba Cloud Java SDK<br/>Product API client"]
    NACOS["Nacos / Sentinel / Seata / RocketMQ"]
    SERVICE["OSS / SMS / Redis / RDS / SchedulerX"]
    API["Product REST/OpenAPI or SDK API"]

    APP --> SCA
    APP --> STARTER
    APP --> SDK
    SCA --> NACOS
    STARTER --> SERVICE
    SDK --> API
~~~

| Layer | Question It Answers | Example Components | Typical Dependency/BOM |
| --- | --- | --- | --- |
| **Spring Cloud Alibaba** | How do microservices register, discover each other, manage configuration, throttle traffic, or communicate in a distributed manner? | Nacos Discovery/Config, Sentinel, Seata, RocketMQ integration | BOM **spring-cloud-alibaba-dependencies** and starter **spring-cloud-starter-alibaba-...** |
| **Aliyun Spring Boot Starters** | How does a Spring Boot application configure and consume a specific Alibaba Cloud service? | OSS, SMS, Redis, RDS MySQL, SchedulerX | BOM **aliyun-spring-boot-dependencies** and starter **aliyun-...-spring-boot-starter** |
| **Product Java SDK** | How do you call a specific product's API with full request/response control and SDK features? | OSS Java SDK, OpenAPI SDK for ECS, SLS, or other products | Product-published SDK dependency, e.g., **aliyun-sdk-oss** |

**Key takeaway:** Spring Cloud Alibaba is not a catch-all name for every Alibaba Cloud service starter. It is a microservice integration project built on the Spring Cloud model. Service starters are developed in the **aliyun-spring-boot** project with their own BOM. Product SDKs, in turn, have their own release lifecycles and configuration approaches.

### 2.1. Examples to Recognize the Difference

- A service needs to **register its service name, instance address, and discover other services**: use Nacos Discovery via Spring Cloud Alibaba.
- A service needs **request rate limiting, circuit breaking, and degradation**: use Sentinel integration via Spring Cloud Alibaba.
- A service needs to **upload/download files from OSS**: use Aliyun OSS Spring Boot Starter if the version and features match, or the OSS Java SDK directly.
- A service needs to **send SMS**: check Aliyun SMS Spring Boot Starter; if you need a new API or parameters not wrapped by the starter, use the SMS SDK.
- A service needs **a specialized product API** without an existing starter: use the product's SDK/OpenAPI client and configure the bean yourself.

Nacos, Sentinel, Seata, and RocketMQ are middleware components/microservice solutions. They can be self-hosted or consumed through compatible managed services, such as the MSE/EDAS platforms depending on the product. OSS, SMS, and RDS are specific cloud services with their own APIs and access permissions.

## 3. What Does Spring Cloud Alibaba Do?

### 3.1. Functional Scope

Spring Cloud Alibaba connects Spring Cloud applications with Alibaba's microservice solutions following the Spring programming model. Typical functional groups include:

| Capability | Component | Role |
| --- | --- | --- |
| Service registration/discovery | **Nacos Discovery** | Registers instances and resolves addresses of other services |
| Externalized configuration | **Nacos Config** | Retrieves centralized configuration and supports configuration updates |
| Flow control/circuit breaking | **Sentinel** | Rate limiting, circuit breaking, degradation, and system protection |
| Distributed transaction | **Seata** | Supports distributed transaction management using the Seata model |
| Distributed messaging | **RocketMQ integration** | Connects Spring applications with RocketMQ |
| Job scheduling | **SchedulerX integration** in supported branches | Integrates distributed job scheduling |

SCA enables applications to use Spring-style abstractions, annotations, and auto-configuration. It does not turn Nacos, Sentinel, or RocketMQ into a generic API for accessing OSS or SMS.

### 3.2. Nacos Discovery Example

Illustrative Maven BOM and starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>${springCloudAlibabaVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    </dependency>
</dependencies>
~~~

Example configuration:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    nacos:
      discovery:
        server-addr: ${NACOS_SERVER_ADDR}
        namespace: ${NACOS_NAMESPACE}
~~~

In real environments, the Nacos server address, namespace, group, credentials, and TLS must be configured according to the cluster/tenant in use. Never place Nacos passwords or tokens into YAML committed to Git.

When the application starts, the Nacos Discovery integration registers the instance according to the configuration. Another service can then look up the service by name through Spring Cloud's corresponding discovery mechanism. This is **service governance/discovery**, not a file upload or SMS sending operation.

### 3.3. Sentinel Example

Sentinel hooks into the request flow to apply protection rules. The application needs the corresponding starter and dashboard/transport/rule configuration for its version.

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
</dependency>
~~~

Conceptual example: cap an order-creation endpoint at 100 requests/second and return a degraded response when the rule is exceeded. Sentinel controls application traffic; it is neither a message queue replacing SQS/RocketMQ nor an SDK for calling cloud services.

### 3.4. When Do You Not Need Spring Cloud Alibaba?

If an application is simply a standalone Spring Boot service that needs to upload files to OSS, with no need for service discovery, centralized config, traffic governance, or distributed transactions, there is no reason to add all of Spring Cloud Alibaba just because the application runs on Alibaba Cloud.

Choosing the appropriate service starter or OSS SDK reduces unnecessary dependencies, configuration, and operational components. You can add SCA later when the microservice architecture genuinely requires those capabilities.

## 4. What Do Aliyun Spring Boot Starters Do?

### 4.1. Product-Specific Integration

The **aliyun-spring-boot** project provides Spring Boot starters for Alibaba Cloud services. The published list includes modules such as:

| Service | Published Starter Artifact | Purpose |
| --- | --- | --- |
| Object Storage Service | **aliyun-oss-spring-boot-starter** | Upload/download objects and perform bucket operations |
| Short Message Service | **aliyun-sms-spring-boot-starter** | Send SMS and integrate SMS service parameters |
| Redis | **aliyun-redis-spring-boot-starter** | Connect to managed Redis |
| RDS MySQL | **aliyun-rds-spring-boot-starter** | Support integration with RDS MySQL |
| SchedulerX | **aliyun-schedulerx-spring-boot-starter** | Integrate job scheduling |
| Function Compute | **aliyun-fc-spring-boot-starter** | Integrate selected Function Compute capabilities |

The starter name is an artifactId, not a Java package name or product name. Check the README and documentation for the exact version before copying configuration. Do not infer OSS property names from SMS or Redis property names.

### 4.2. Separate BOM for Service Starters

The Aliyun Spring Boot Starters BOM has its own coordinates:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>aliyun-spring-boot-dependencies</artifactId>
            <version>${aliyunSpringBootVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then add the starter you need, for example OSS:

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>aliyun-oss-spring-boot-starter</artifactId>
</dependency>
~~~

**Do not replace this BOM with spring-cloud-alibaba-dependencies.** The two BOMs manage two different sets of artifacts. Spring Cloud Alibaba's documentation also explicitly states that to use Spring Boot starters for Alibaba Cloud services, you must add the Aliyun Spring Boot BOM.

The starter project and SCA have separate release schedules, support scopes, and compatibility matrices. Do not take SCA's Spring Boot/Spring Cloud compatibility table and assume it applies to all Aliyun service starters. Before adopting one, verify the version published on Maven Central, Java/Spring Boot requirements, and transitive SDK dependencies.

### 4.3. What Does a Starter Typically Provide?

A well-designed starter typically combines several parts:

- A dependency on the product SDK.
- Auto-configuration that creates client or template beans.
- Property binding for endpoint, region, bucket, or connection parameters.
- Conditional configuration so the application can override default beans.
- Integration with the Spring lifecycle, such as shutting down the client when the context closes.
- Possibly abstractions or helpers to reduce boilerplate configuration code.

The level of support varies across starters. Read the documentation and source/samples of the module you are using to see which beans it creates, what it configures, and which APIs it wraps. Using a starter does not eliminate the need to understand RAM permissions, endpoints, regions, networking, and service quotas.

## 5. What Does Using the Product SDK Directly Do?

### 5.1. When Should You Use the SDK?

Use the SDK directly when:

- No suitable starter exists for the product.
- The existing starter does not support a required API or feature.
- You need fine-grained control over requests/responses, retries, timeouts, multipart uploads, or metadata.
- You want explicit control over the SDK version and upgrade schedule.
- You want to write an internal adapter to decouple domain services from provider APIs.

An SDK typically provides a product-specific client. The application is responsible for deciding how to instantiate the client, obtain credentials, choose the region/endpoint, manage connection pools, shut down the client, and map errors to domain exceptions.

### 5.2. OSS Java SDK Dependency Example

The OSS Java SDK V1 documentation publishes these Maven coordinates:

~~~xml
<dependency>
    <groupId>com.aliyun.oss</groupId>
    <artifactId>aliyun-sdk-oss</artifactId>
    <version>${aliyunOssSdkVersion}</version>
</dependency>
~~~

Current documentation gives an example dependency version of **3.18.4**; in a real project, pick a version verified on Maven Repository and manage it via a version catalog or property. OSS Java SDK V2 has a separate artifact—do not attempt to switch from V1 to V2 merely by changing the version number.

### 5.3. Wrapping the SDK as a Spring Bean

The example below uses OSS Java SDK V1 and credentials from environment variables per the SDK guide:

~~~java
package demo.storage;

import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.auth.CredentialsProviderFactory;
import com.aliyun.oss.common.comm.SignVersion;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OssClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    public OSS ossClient(
            @Value("${aliyun.oss.endpoint}") String endpoint,
            @Value("${aliyun.oss.region}") String region) {

        CredentialsProvider credentialsProvider =
                CredentialsProviderFactory
                        .newEnvironmentVariableCredentialsProvider();

        ClientBuilderConfiguration clientConfig =
                new ClientBuilderConfiguration();
        clientConfig.setSignatureVersion(SignVersion.V4);

        return OSSClientBuilder.create()
                .credentialsProvider(credentialsProvider)
                .clientConfiguration(clientConfig)
                .region(region)
                .endpoint(endpoint)
                .build();
    }
}
~~~

This example uses the **OSS_ACCESS_KEY_ID** and **OSS_ACCESS_KEY_SECRET** environment variables via the corresponding SDK V1 provider. Do not hardcode real values into source code or YAML. For workloads running on Alibaba Cloud, prefer short-lived credentials/RAM roles appropriate to the environment over static AccessKeys.

The OSS client can be reused as a singleton Spring bean; do not create a new client for every upload. The client manages a connection pool and must be shut down when the application stops.

### 5.4. Using the Client in a Service

~~~java
package demo.storage;

import com.aliyun.oss.OSS;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Service
public class ObjectStorageService {
    private final OSS ossClient;
    private final String bucketName;

    public ObjectStorageService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public void upload(String objectKey, InputStream content) {
        ossClient.putObject(bucketName, objectKey, content);
    }
}
~~~

This snippet only illustrates the adapter boundary. In production, you need to validate file size/type, enforce write permissions on the intended bucket/prefix, handle streams and metadata properly, define overwrite policies, use multipart upload for large files, configure timeouts and retries, and log request IDs. Do not return public URLs for private objects without an appropriate access-control mechanism.

### 5.5. Comparing a Starter and Direct SDK Usage

| Criterion | Service Spring Boot Starter | Direct SDK |
| --- | --- | --- |
| Client creation | Usually auto-configured | Application creates the bean itself |
| Property binding | May be provided by the starter | Define ConfigurationProperties or Value manually |
| Lifecycle integration | Usually managed by auto-configuration | Configure destroy/close manually |
| Product API coverage | Depends on how much the starter wraps | Usually full access to the SDK API |
| Customization | Limited to extension points exposed by the starter | Direct control over client and requests |
| Upgrades | Must check starter and transitive SDK compatibility together | Independently choose SDK versions |
| Configuration code cost | Lower if the starter fits | Higher, but transparent |
| When to choose | Common needs, starter is maintained and compatible | New/specialized features or deep control required |

## 6. BOM and Version Compatibility: Choose Correctly Before Adding Dependencies

### 6.1. Spring Cloud Alibaba BOM

SCA has the **spring-cloud-alibaba-dependencies** BOM. It manages Spring Cloud Alibaba artifacts and the versions of the components the project integrates. It must be aligned with the Spring Cloud BOM and Spring Boot version.

In the 2025.x documentation branch, the published compatibility pairs include:

| Spring Cloud Alibaba | Spring Cloud | Spring Boot |
| --- | --- | --- |
| **2025.1.0.0** | **2025.1.x** | **4.0.x** |
| **2025.0.0.0** | **2025.0.x** | **3.5.x** |

This is the matrix from the referenced documentation branch; always check the latest release notes when starting a project. Do not pick an SCA version merely because it has a higher number. Do not arbitrarily upgrade Nacos/Sentinel/RocketMQ on your own when the BOM already manages compatible versions.

Maven example for the Spring Boot 3.5 / Spring Cloud 2025.0 branch:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${springCloudVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>${springCloudAlibabaVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The Spring Boot parent/BOM must be selected to match the pair above. Do not import a different Spring Cloud release train from what SCA specifies just because the build still resolves dependencies.

### 6.2. Aliyun Spring Boot Starters BOM

The **aliyun-spring-boot-dependencies** BOM manages the starters from the Aliyun Spring Boot project. It is not the SCA BOM. Read that project's own release notes/README to confirm Spring Boot and product SDK compatibility.

If an application needs both Nacos Discovery and the OSS Starter, it may have to use both dependency sets, but you must verify version convergence, transitive libraries, and conflicts between SDKs. Do not import both BOMs out of habit when the application only uses one group.

### 6.3. Product SDK Versions

Product SDKs have independent versions:

- OSS Java SDK V1/V2 have separate release schedules.
- Alibaba Cloud OpenAPI SDK V2 generates clients per product/API version.
- The credentials tool, Tea/OpenAPI runtime, and product SDKs share common dependencies that must stay compatible.

Alibaba Cloud SDK V2 documentation lists common packages such as **credentials-java**, **tea**, **tea-openapi**, and **tea-util**. These packages are usually pulled in transitively by product SDKs; only add them manually when missing or when resolving conflicts according to the documentation.

Do not use **spring-cloud-alibaba-dependencies** to guess the OSS SDK version. Likewise, do not assume the Aliyun starter BOM manages every SDK your application adds manually.

## 7. Identity, Credentials, and Access Permissions on Alibaba Cloud

### 7.1. RAM and AccessKey

Alibaba Cloud uses **Resource Access Management (RAM)** to manage users, roles, and permissions. An application that only needs to access an OSS bucket should only have permissions scoped to that bucket/prefix; do not grant **AdministratorAccess** or **AliyunOSSFullAccess** unless necessary.

| Environment | Recommended Authentication Approach |
| --- | --- |
| Developer workstation | Alibaba Cloud CLI/profile or environment variables for a test RAM user with least privilege |
| ECS/ECI | RAM role attached to the instance; obtain temporary credentials via instance metadata |
| ACK | OIDC/RRSA and RAM role for workload/pod if the cluster is configured |
| Systems outside Alibaba Cloud | STS/AssumeRole or an appropriate credentials URI/secret broker |
| Legacy integration | RAM user AccessKey stored in a secret manager and rotated per policy |

Never use the root account's AccessKey. If a static AccessKey is required, create a dedicated RAM user, attach a least-privilege policy, store it in a secret manager or secure runtime environment, and maintain a rotation plan.

### 7.2. Alibaba Cloud SDK V2 and Credentials Tool

SDK V2 has its own credentials management tool. The default credential chain can look up credentials from system properties, environment variables, a shared credentials file, an OIDC RAM role, and an instance RAM role depending on the environment and version.

Example environment configuration for a RAM user in local testing:

~~~text
ALIBABA_CLOUD_ACCESS_KEY_ID=<ram-user-access-key-id>
ALIBABA_CLOUD_ACCESS_KEY_SECRET=<ram-user-access-key-secret>
~~~

These are only environment variable names; never write real values into documentation, configuration files, or logs. For ACK with RRSA/OIDC, you can configure the RAM role ARN, OIDC provider ARN, and token file to obtain short-lived STS credentials. For ECS/ECI, the credentials tool can retrieve the RAM role from instance metadata and refresh it automatically.

**The credentials tool should be reused** as a singleton or tied to the client lifecycle to leverage caching and avoid fetching credentials too frequently. If an SDK V2 client uses a credential provider, pass the provider into the client config following that SDK version's API.

### 7.3. Region and Endpoint

Not all services use the same endpoint format. Distinguish carefully between:

- **Region ID**: the region where the resource is created.
- **Endpoint**: the service's API address in that region, which may be public, VPC/internal, or product-specific.
- **Bucket/resource location**: the actual region where the resource resides; do not infer it from the application's region.

With Alibaba Cloud OpenAPI SDK V2, client configuration can accept **regionId** to resolve the endpoint, or the endpoint can be specified explicitly. When an endpoint is set explicitly, verify that it matches the region and network path. For OSS, choose the endpoint and region matching the bucket; SDK V1 Signature V4 requires declaring the corresponding region.

## 8. How to Choose Dependencies in a Spring Boot Application

~~~mermaid
flowchart TD
    A{"What is the primary need?"}
    A -->|"Discovery / config / traffic governance / distributed transaction"| B["Spring Cloud Alibaba"]
    A -->|"Consume a managed service via Spring Boot auto-config"| C["Aliyun Spring Boot Starter"]
    A -->|"Need a specialized API or starter falls short"| D["Product Java SDK"]
    B --> E["Import spring-cloud-alibaba-dependencies"]
    C --> F["Import aliyun-spring-boot-dependencies"]
    D --> G["Manage SDK + credentials + endpoint + client bean"]
    E --> H["Check Spring Boot / Spring Cloud compatibility"]
    F --> I["Check starter release and transitive SDK"]
    G --> J["Check product API version and lifecycle"]
~~~

### 8.1. Decision Examples by Requirement

| Application Requirement | Choice | Reason |
| --- | --- | --- |
| Services auto-register and discover each other via Nacos | Spring Cloud Alibaba Nacos Discovery | This is a service discovery capability |
| Manage centralized configuration with Nacos | Spring Cloud Alibaba Nacos Config | This is externalized configuration |
| Protect endpoints from traffic bursts | Spring Cloud Alibaba Sentinel | This is flow control/circuit breaking |
| Send SMS from Spring Boot | Aliyun SMS starter if compatible; otherwise SMS SDK | The SMS API is a specific cloud service |
| Upload files to OSS | Aliyun OSS starter or OSS Java SDK | This is an object storage API |
| Need a new OSS operation not exposed by the starter | OSS Java SDK directly | Full product API access is required |
| Use RDS MySQL | Standard JDBC driver/DataSource and RDS connection details; starter if it adds value | RDS is managed MySQL, not a replacement for JDBC |
| Use managed Redis | Spring Data Redis/Lettuce or an appropriate starter | Choose based on the Redis service's protocol/compatibility |
| Schedule distributed jobs | SchedulerX integration/starter | Distributed job scheduling and execution are needed |

A managed service does not strictly require a dedicated starter to be used from Spring Boot. If the product is compatible with a standard protocol (such as MySQL/JDBC or the Redis protocol), the corresponding Spring ecosystem library may suffice; a starter only adds value when it simplifies configuration or provides specialized integration.

## 9. Recommended Code Structure in Spring Boot

### 9.1. Decoupling Domain from the SDK

Do not let controllers or domain services depend directly on Alibaba Cloud SDK classes. Create an internal interface:

~~~java
package demo.storage;

import java.io.InputStream;

public interface ObjectStorage {
    void upload(String objectKey, InputStream content);
}
~~~

An adapter implements the interface using the OSS SDK:

~~~java
package demo.storage;

import com.aliyun.oss.OSS;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.InputStream;

@Component
public class AlibabaOssStorage implements ObjectStorage {
    private final OSS ossClient;
    private final String bucket;

    public AlibabaOssStorage(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucket) {
        this.ossClient = ossClient;
        this.bucket = bucket;
    }

    @Override
    public void upload(String objectKey, InputStream content) {
        ossClient.putObject(bucket, objectKey, content);
    }
}
~~~

The domain service only needs **ObjectStorage**. When replacing OSS with another object storage provider, swap the adapter and configuration without rewriting upload business logic everywhere. This structure also makes it easy for unit tests to mock the interface without calling the real cloud.

### 9.2. Profile-Based Configuration

~~~yaml
aliyun:
  oss:
    endpoint: ${ALIYUN_OSS_ENDPOINT}
    region: ${ALIYUN_OSS_REGION}
    bucket: ${ALIYUN_OSS_BUCKET}
~~~

Do not put AccessKey secrets in this file. Separate non-sensitive endpoint/bucket settings from credentials; use environment variables, RAM roles, STS, or a secret manager for authentication details. You can use local/staging/prod profiles to select different endpoints, namespaces, and buckets.

## 10. Testing and Diagnostics

### 10.1. Layered Testing

| Test Type | Scope | How to Execute |
| --- | --- | --- |
| Domain unit test | Upload/SMS sending logic independent of cloud | Mock internal interfaces like ObjectStorage |
| Adapter unit test | Request mapping, object keys, metadata | Mock SDK client or verify the adapter through a wrapper |
| Spring context test | Auto-configuration and bean injection | Use test context, property tests, and conditions |
| Integration test | Real or sandbox Nacos/OSS/SMS connectivity | Use a test account, isolated bucket/namespace, and restricted permissions |
| Permission test | RAM role and policy | Test allowed and denied actions in a test account |
| Failure test | Timeouts, wrong endpoint, quotas, network issues | Verify exception mapping, retries, and request ID logging |

Do not use unit tests to prove that cloud IAM policies are correct. Do not run integration tests that send real SMS messages to users or upload sensitive data to production buckets.

### 10.2. Common Symptoms

| Symptom | Layer to Inspect |
| --- | --- |
| Dependencies fail to resolve | Maven coordinates, repositories, BOM imports, and published versions |
| **NoSuchMethodError / ClassNotFoundException** | Conflicts between Spring Boot, Spring Cloud, SCA, starters, and transitive SDKs |
| Nacos fails to register service | Server address, namespace, group, credentials, network, and client/server versions |
| OSS **AccessDenied** | RAM policy, bucket policy, object prefix, endpoint/region, and runtime credentials |
| OSS **SignatureDoesNotMatch** | AccessKey/STS token, region, endpoint, clock skew, and signing version |
| OSS **NoSuchBucket / NoSuchKey** | Bucket/object key name, region, and resource path |
| SMS rejected | RAM permissions, sender/template approval, phone format, quota, and service status |
| SDK timeout | Public/VPC endpoint, DNS, firewall, proxy, connect/read timeouts |
| Credentials expired | STS refresh, role trust policy, OIDC token, and cache/provider lifecycle |

Distinguish **client-side** errors (DNS, timeout, TLS, credentials provider) from **server-side** errors (AccessDenied, InvalidParameter, NoSuchBucket). When a request ID is present, record it in logs for lookup with Alibaba Cloud support. Never log AccessKeys, secrets, STS tokens, or full payloads containing personal data.

### 10.3. Inspecting the Dependency Tree

When using both SCA and service starters, inspect the Maven/Gradle dependency tree to detect:

- Two different versions of the Nacos client or Sentinel.
- A product SDK pulling in a different version than the starter.
- A Spring Boot/Cloud version outside the SCA compatibility matrix.
- Duplicate or overridden logging/HTTP client libraries.
- An older starter pulling in APIs incompatible with the current Java/Jakarta version.

Only override a dependency after identifying the conflicting artifact and testing the affected functionality. Avoid using a single BOM to force every dependency to the same version number.

## 11. Common Misconceptions to Avoid

| Misconception | Correct Understanding |
| --- | --- |
| Spring Cloud Alibaba is the starter for all Alibaba Cloud services | SCA focuses on microservice integrations such as Nacos, Sentinel, Seata, and RocketMQ |
| **spring-cloud-alibaba-dependencies** manages OSS/SMS SDKs | Aliyun service starters have their own BOM; product SDKs have their own versions |
| Having a starter means you don't need to know RAM permissions | Every request still requires an appropriate principal, permissions, endpoint, and resource policy |
| Running on Alibaba Cloud automatically grants access to all services | Specific RAM roles/credentials and policies are required |
| Nacos replaces OSS or RDS | Nacos is a registry/configuration center; OSS/RDS are storage/database services |
| Every Alibaba Cloud SDK uses the same endpoint | Endpoint/region depends on the specific product and network path |
| The root account's AccessKey is most convenient for applications | Use a RAM user/role with least privilege and short-lived credentials whenever possible |
| An application can only pick one of the three layers | You can combine SCA, service starters, and SDKs when each layer solves a clear need; manage versions and bean lifecycles deliberately |

## 12. Hands-on Exercise

**Exercise:** Build a Spring Boot application that manages orders and invoice files on Alibaba Cloud.

1. Choose a Spring Boot/Spring Cloud version compatible with a current SCA branch.
2. Import **spring-cloud-alibaba-dependencies** and add Nacos Discovery to register the service.
3. Create a dedicated Nacos namespace for the dev environment.
4. Add the OSS service starter if a compatible version meets your needs; otherwise, add the OSS Java SDK and configure a client bean.
5. Create a RAM role/user with permission to upload only to a test bucket/prefix.
6. Implement an **ObjectStorage** adapter to upload invoice files.
7. Unit test the domain service using a mocked ObjectStorage.
8. Integration test uploading files to the dev bucket, verifying metadata and access permissions.
9. Simulate AccessDenied, an invalid endpoint, and expired credentials; document how each error is categorized.
10. Compare the two OSS integration approaches—service starter versus direct SDK—in terms of configuration volume, control, upgradability, and testability.

**Review Questions:**

1. How do Spring Cloud Alibaba and Aliyun Spring Boot Starters differ in purpose?
2. When should you import **spring-cloud-alibaba-dependencies**?
3. When should you import **aliyun-spring-boot-dependencies**?
4. Why doesn't the SCA version automatically manage the OSS Java SDK version?
5. If you need an OSS API not wrapped by the starter, how should you handle it?
6. Why should you create a singleton OSS client instead of creating a client per request?
7. When an application runs on ECS/ACK, how should RAM roles/STS/OIDC be considered?
8. How does **AccessDenied** differ from **SignatureDoesNotMatch**?
9. Can Nacos be used to replace RDS or OSS? Why or why not?
10. If an application needs both Nacos Discovery and OSS, which BOMs/dependencies need to be checked?

## 13. References

- [Spring Cloud Alibaba — What is Spring Cloud Alibaba](https://sca.aliyun.com/en/docs/2025.x/overview/what-is-sca/): SCA positioning and microservice scope.
- [Spring Cloud Alibaba — Release Notes 2025.x](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/): Spring Boot, Spring Cloud, and SCA compatibility matrix.
- [Spring — Spring Cloud Alibaba project](https://spring.io/projects/spring-cloud-alibaba/): distinguishes SCA from Spring Boot starters for Alibaba Cloud services and their respective BOMs.
- [Alibaba — aliyun-spring-boot](https://github.com/alibaba/aliyun-spring-boot): Aliyun Spring Boot Starters project, BOM, and starter list.
- [Alibaba Cloud SDK — V2 Java SDK](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-java-sdk/): common dependencies and endpoint/region configuration for SDK V2.
- [Alibaba Cloud SDK — Manage credentials](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-manage-access-credentials): default credential chain, RAM roles, STS, OIDC, and credentials caching.
- [OSS Java SDK V1 — Installation and quickstart](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-java-sdk/): dependencies, credentials, region, endpoint, Signature V4, and client lifecycle.
- [OSS Java SDK V2](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-sdk-for-java-2-0/): SDK V2 guide for Java applications.
- [Alibaba Cloud RAM](https://www.alibabacloud.com/help/en/ram/): managing users, roles, and permissions.

**Expected Outcome:** Learners accurately identify the three integration layers—**Spring Cloud Alibaba for microservices**, **Aliyun Spring Boot Starters for managed services**, and **direct Java SDKs for product APIs**—and know how to select BOMs/dependencies, configure RAM credentials and regions/endpoints, and test each layer in a Spring Boot application.
