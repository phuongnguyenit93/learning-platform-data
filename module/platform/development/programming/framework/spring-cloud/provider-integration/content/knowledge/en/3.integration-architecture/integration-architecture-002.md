# Auto-Configuration, Bean Creation Conditions, and Client Customization

When adding a Spring Cloud starter to a Spring Boot application, you often only need to declare a dependency and a few configuration properties to inject a cloud client for S3, Azure Blob Storage, or Google Cloud Storage. That feeling of a “client appearing automatically” comes from **auto-configuration**: Spring Boot and the integration library inspect the classpath, configuration, and existing beans, then register the eligible beans. Understanding this mechanism helps you know when a client is created, why a configuration does not take effect, and how to customize a client without breaking other integrations.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, including identity and permissions, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. In this lesson, the focus is **the process of creating and customizing clients inside the Spring application context**, before a client makes network requests to the cloud.

## 1. Learning Objectives

After this lesson, you can:

- Explain how Spring Boot discovers auto-configuration and evaluates conditions to register beans.
- Distinguish **bean definition**, **bean instance**, **configuration properties**, **client builder**, and **cloud credentials**.
- Read common conditions such as **@ConditionalOnClass**, **@ConditionalOnMissingBean**, **@ConditionalOnProperty**, and **@ConditionalOnBean**.
- Choose the appropriate level of customization: modifying properties, using library-supported hooks/builder customizers, or defining client beans directly.
- Diagnose missing beans, multiple beans, mismatched configuration, and clients using the wrong region/project/identity.
- Build tests for bean creation conditions and verify connectivity to managed services on AWS, Azure, or Google Cloud.

## 2. What Does Auto-Configuration Do?

**Spring Framework** provides the IoC container: managing beans and injecting dependencies. **Spring Boot** provides the auto-configuration mechanism on top of that container. Starters for **Spring Cloud AWS**, **Spring Cloud Azure**, and **Spring Cloud GCP** can bring additional SDK libraries, auto-configuration classes, and specialized integrations into the application.

Auto-configuration operates mainly at **application startup time**:

1. Boot initializes the **ApplicationContext**, reads effective configuration, and scans application beans.
2. Boot discovers auto-configuration classes provided by dependencies. In the Spring Boot 3.x generation, libraries typically declare them via **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
3. Auto-configurations are evaluated against conditions: whether a class is on the classpath, whether a property is enabled, whether a bean of the same type already exists, and starter-specific conditions.
4. If conditions are satisfied, Spring registers the bean definition, instantiates the object when needed, injects dependencies, and places it into the application lifecycle.
5. Controllers, services, adapters, templates, or listeners can receive the client via constructor injection.

The presence of a **starter** does not guarantee every client will be created: only configuration branches whose conditions match become active. Conversely, the fact that a bean is created **does not prove the client is connected, the token is valid, or the identity has sufficient permissions**. Many SDKs defer network calls until the first method is executed.

~~~mermaid
flowchart TD
    D[Dependencies / starters on classpath] --> I[Boot discovers auto-configuration]
    P[application.yml and other property sources] --> E[Evaluate conditions]
    U[User-declared beans in application] --> E
    I --> E
    E -->|Match| B[Register bean definition]
    E -->|No match| S[Back off / skip configuration branch]
    B --> C[Create cloud client or template bean]
    C --> A[Inject into adapter / service]
    A --> R[Runtime: call cloud SDK / API]
~~~

**Back off** is the behavior where an auto-configuration yields to a bean that the application has already defined itself, usually via **@ConditionalOnMissingBean**. This is a common starter convention, though not an absolute guarantee for every bean type or every library: you must check the actual conditions and library version in use.

## 3. Conditions That Determine Which Beans Are Created

| Condition / annotation | Question Spring evaluates | Illustrative consequence |
| --- | --- | --- |
| **@ConditionalOnClass** | Is the specified class on the classpath? | S3 configuration only makes sense when the S3 SDK dependency is present |
| **@ConditionalOnMissingClass** | Is the specified class absent? | Select a branch intended for environments lacking a specific API |
| **@ConditionalOnBean** | Has a matching bean already been registered? | Create a template only when the required client exists |
| **@ConditionalOnMissingBean** | Is there no matching bean yet? | Do not create a default client if the application already defined one |
| **@ConditionalOnSingleCandidate** | Is there exactly one matching candidate (or one primary among multiple candidates)? | Only create a dependent component when a single client can be resolved for injection |
| **@ConditionalOnProperty** | Does the property exist and have a matching value? | Enable an adapter when **app.storage.enabled=true** |
| **@ConditionalOnResource** | Does the specified resource exist? | Enable a configuration only when the corresponding resource is present |
| **@ConditionalOnWebApplication** | Is this a web application of the expected type? | Enable web configuration in the appropriate environment |

Conditions can be placed on a **configuration class** or a **@Bean method**, and combine with AND semantics. When a class-level condition fails, the beans inside that class are generally not evaluated further.

An illustrative example of the principle, **not actual source code from a Spring Cloud starter**:

~~~java
// Pseudocode illustrating an auto-configuration.
@AutoConfiguration
@ConditionalOnClass(S3Client.class)
@ConditionalOnProperty(
    prefix = "example.s3",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
class ExampleS3AutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(S3Client.class)
    S3Client s3Client() {
        return S3Client.create();
    }
}
~~~

With this illustrative condition, if the **S3Client** class is missing, the entire branch is skipped; if the property is set to **false**, the configuration is disabled; if the application already has an **S3Client** bean, the default method is not used. **example.s3.enabled** is only a hypothetical property name to explain how it works, not an actual Spring Cloud AWS property.

Two easily confused details:

- **@ConditionalOnProperty** checks properties according to the annotation's rules; the string value **false** means something different from a missing property, especially when using **havingValue** or **matchIfMissing**. It does not verify whether a bucket exists or whether an identity has permissions.
- **@ConditionalOnMissingBean** depends on the bean definitions known to the container **at the time of evaluation**. This annotation is designed primarily for auto-configurations with well-defined ordering; avoid using it arbitrarily in application configuration code and treating it as a runtime client selection mechanism.

**@Profile** can also restrict beans by environment (such as local or staging), though that selects configuration by profile. **@Primary** and **@Qualifier** solve **choosing which bean to inject when multiple candidates exist**; they do not enable or disable auto-configuration by themselves.

## 4. Distinguishing Property Binding, Beans, and SDK Clients

Consider an application that needs to write data to object storage:

| Concept | Example | Meaning |
| --- | --- | --- |
| **Configuration property** | Region, bucket, endpoint, timeout, enabled | Data used to select and configure objects |
| **@ConfigurationProperties** | StorageSettings containing enabled/bucket | Binds and validates configuration into a strongly typed object |
| **Bean definition** | Method **@Bean S3Client s3Client(...)** | Recipe for Spring to create and manage the object |
| **Bean instance** | An instantiated **S3Client** object | Object injected and used at runtime |
| **SDK client builder** | **S3Client.builder()** | Specific configuration for the SDK object prior to creation |
| **Credential provider** | AWS default chain, Azure credential, Google ADC | Obtains/refreshes identity to sign or attach tokens to calls |
| **Cloud service** | S3, Blob Storage, Cloud Storage | Checks permissions, executes operations, and returns results |

~~~mermaid
flowchart LR
    Y[Config properties] --> A[Spring auto-configuration / @Bean]
    K[Classpath + conditions] --> A
    A --> B[SDK client bean]
    C[Credential provider] --> B
    B --> D[DocumentStorage adapter]
    E[Application service] --> D
    D --> F[Managed cloud service]
~~~

A **client bean** is managed by Spring within an application context. A **client builder** is solely an initialization tool. **Credentials** may be obtained via a provider chain or dedicated token acquisition; they do not necessarily appear as fixed strings in YAML. And a client can be completely valid at startup yet fail on network calls due to DNS, endpoints, IAM/RBAC, or quotas.

## 5. Basic Example: Spring Cloud AWS Auto-Configuring S3Client

In a Spring Boot 3 application with **Spring Cloud AWS 3.x**, the S3 starter typically provides the integration needed for Spring to create **S3Client** and related beans when conditions are met. Artifact versions and actual properties must align with the **Spring Cloud AWS BOM** compatible with your project's Spring Boot version.

Illustrative Maven dependency declaration (version managed by BOM):

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Example **application.yml**:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    enabled: true
    bucket: ${APP_STORAGE_BUCKET}
~~~

In this configuration, **spring.cloud.aws.region.static** is a property serving the AWS client through Spring Cloud AWS; **app.storage.enabled** and **app.storage.bucket** are properties **defined by the application itself** for its adapter and are not automatically understood by the starter. The **APP_STORAGE_BUCKET** environment variable holds a bucket name, not a secret. The SDK can use the appropriate credential chain for the environment; production should prefer a role or workload identity with least-privilege permissions.

The application can receive the managed client via constructor injection:

~~~java
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.core.sync.RequestBody;

@Component
public class S3DocumentWriter {
    private final S3Client s3;

    public S3DocumentWriter(S3Client s3) {
        this.s3 = s3;
    }

    public void write(String bucket, String key, byte[] data) {
        s3.putObject(
            PutObjectRequest.builder().bucket(bucket).key(key).build(),
            RequestBody.fromBytes(data)
        );
    }
}
~~~

Startup sequence: the starter puts auto-configuration on the classpath → conditions match → the client bean is registered → Spring injects it into **S3DocumentWriter**. Write sequence: business code calls **write** → the adapter calls **S3Client.putObject** → the SDK uses credentials/HTTP to reach S3. Auto-configuration is not a proxy layer sitting on top of every SDK call.

If you only need to select a region via supported configuration, **prefer the starter's official property**. Do not manually define an extra client bean when your actual goal is simply changing a built-in property.

## 6. Three Levels of Client Customization

There is no single customization API common to every cloud provider. A sensible order of consideration:

### 6.1. Level 1 — Use Starter Properties

Suitable for options already supported by the library: region, project ID, account/endpoint, credential mode, feature toggles, and sometimes timeouts/retries. Example with Spring Cloud AWS:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Advantages: minimal code, convenient across environments, and preserves the library's bean creation, lifecycle, and template/listener integrations. Limitation: not every SDK parameter has a corresponding Spring property.

### 6.2. Level 2 — Use Library-Published Customizers or Builder Hooks

Some starters publish a **customizer**, **builder hook**, or SDK-specific options. When available, this is the right place to add client configuration while keeping auto-configuration for everything else. You must check the exact **interface name, application order, and affected client types** for your library version; do not assume AWS, Azure, and Google Cloud share the same customizer interface.

Examples of needs that commonly require checking supported hooks: proxies, custom endpoints, interceptors, tracing, retries, connect/read timeouts, or HTTP transport. Adding an interceptor to client A's builder does not automatically mean listener/template B uses that same client.

### 6.3. Level 3 — Declare the SDK Client Bean Yourself

When direct control over SDK configuration is required, you can register a bean with **@Configuration** and **@Bean**. The example below illustrates owning the **S3Client** configuration directly:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class AwsS3ClientConfiguration {

    @Bean
    S3Client s3Client(
            @Value("${app.aws.s3.region}") String region) {
        return S3Client.builder()
            .region(Region.of(region))
            .credentialsProvider(DefaultCredentialsProvider.create())
            .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(Duration.ofSeconds(5))
                .apiCallTimeout(Duration.ofSeconds(20)))
            .build();
    }
}
~~~

~~~yaml
app:
  aws:
    s3:
      region: ap-southeast-1
~~~

With an auto-configuration using **@ConditionalOnMissingBean(S3Client.class)**, this user-declared bean causes the **default S3Client** branch to back off; other templates/components may still use the new bean. **Do not assume this for every starter version**: verify the condition report and bean graph. The example uses **DefaultCredentialsProvider** and does not place access keys/secret keys in source code or configuration. Timeouts shown are illustrative only and must be tuned to your actual SLA and retries.

Beans are singletons by default, so the client can be reused instead of created per request. Spring manages the bean's lifecycle and typically infers the **close** method on SDK clients when the context closes; verify transport resource cleanup when configuring an external custom HTTP client. If you drop the starter completely and use only the SDK, the application must configure any integrations previously provided by the starter on its own.

### 6.4. Selection Rules

| Need | First Appropriate Approach | Notes |
| --- | --- | --- |
| Select region or project/account per environment | Starter property | Avoid setting two conflicting region sources |
| Add interceptor or HTTP timeout lacking a property | Official hook/customizer, if available | Check which sync/async clients the customizer applies to |
| Use a client for a special endpoint/identity | Declare the appropriate bean yourself | Check impact on auto-config, templates, and listeners |
| Two cloud accounts or two regions in the same context | Define multiple beans with clear names/qualifiers | Avoid relying on injection by type when ambiguous |
| Enable or disable a business adapter | Condition on the application's adapter/port | Does not mean disabling the entire starter |
| Need to run locally without real cloud | Mock port or emulator/test configuration | Context tests and real IAM must be verified separately |

## 7. Customizing Bean Creation Conditions for Your Own Adapter

Suppose you only want to create the document storage adapter when **app.storage.enabled=true**, independent of whether the starter creates the SDK client. You can declare a port and a conditional configuration class:

~~~java
// DocumentStorage.java
public interface DocumentStorage {
    void put(String key, byte[] bytes);
}
~~~

~~~java
// S3DocumentStorage.java
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

public final class S3DocumentStorage implements DocumentStorage {
    private final S3Client client;
    private final String bucket;

    public S3DocumentStorage(S3Client client, String bucket) {
        this.client = client;
        this.bucket = bucket;
    }

    @Override
    public void put(String key, byte[] bytes) {
        client.putObject(
            PutObjectRequest.builder().bucket(bucket).key(key).build(),
            RequestBody.fromBytes(bytes)
        );
    }
}
~~~

~~~java
// StorageSettings.java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageSettings(boolean enabled, String bucket) {}
~~~

~~~java
// DocumentStorageConfiguration.java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StorageSettings.class)
public class DocumentStorageConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.storage",
        name = "enabled",
        havingValue = "true"
    )
    DocumentStorage documentStorage(
            S3Client s3Client, StorageSettings settings) {
        return new S3DocumentStorage(s3Client, settings.bucket());
    }
}
~~~

With the configuration above:

| **app.storage.enabled** | **DocumentStorage** Bean | What Happens? |
| --- | --- | --- |
| **true** | Registered, if **S3Client** dependency exists | Adapter is ready to be injected |
| **false** | Skipped | A service requiring **DocumentStorage** may fail to start if no alternative exists |
| Omitted | Skipped by default | Because **matchIfMissing** defaults to **false** |

This condition only controls **DocumentStorage**; it does not automatically disable Spring Cloud AWS's **S3Client** bean. If the application needs to support multiple providers, you can add an **app.storage.provider** property to select the corresponding adapter; ensure exactly one adapter satisfies the condition, or use an explicit **@Qualifier** when multiple adapters are valid.

**@ConfigurationProperties** groups data under a namespace and supports strongly typed binding. For production configuration, you can combine it with validation (**@Validated**, Jakarta Validation constraints when the appropriate dependency is present) to catch an empty bucket or invalid values at startup rather than only failing at runtime.

## 8. Multiple Client Beans: @Primary, @Qualifier, and Auto-Config Boundaries

Two S3 accounts, two regions, or two API endpoints may require two beans of the same **S3Client** type. In that case:

~~~java
// Idea inside an application-owned @Configuration.
@Bean("invoiceS3Client")
S3Client invoiceS3Client() {
    return S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();
}

@Bean("archiveS3Client")
S3Client archiveS3Client() {
    return S3Client.builder()
        .region(Region.AP_NORTHEAST_1)
        .build();
}
~~~

~~~java
// Example selecting a client by bean name.
public InvoiceWriter(
        @Qualifier("invoiceS3Client") S3Client s3Client) {
    this.s3Client = s3Client;
}
~~~

The snippets above are **illustrative excerpts** and must be placed in an appropriate class with project imports added. Each client uses its corresponding credential chain and access permissions; differing regions do **not** automatically produce differing identities. If using two accounts, you must intentionally configure the identity for each client.

**@Primary** only designates a default candidate when injecting by type. **@Qualifier** explicitly expresses which client serves which business purpose and is usually better when two clients have distinct responsibilities. Having multiple **S3Client** beans can also cause **@ConditionalOnSingleCandidate** to fail or leave templates unsure which bean to pick. In an application that owns multiple clients, also inspect dependent Spring Cloud beans and reconfigure templates/listeners by explicit bean name if necessary.

Do not enable **spring.main.allow-bean-definition-overriding=true** just to “fix” duplicate bean errors: overriding definitions by name can mask configuration conflicts, whereas **NoUniqueBeanDefinitionException** is a type-resolution conflict. Fix it properly using conditions, bean names, qualifiers, or clear ownership of configuration.

## 9. Comparing How Spring Cloud Integrates AWS, Azure, and Google Cloud

All three ecosystems share the idea of auto-configuration and injected clients, but **starters, SDK classes, credentials, and properties are not uniform**.

| Criterion | Spring Cloud AWS | Spring Cloud Azure | Spring Cloud GCP |
| --- | --- | --- | --- |
| Typical managed storage | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| Corresponding starter (common example) | **spring-cloud-aws-starter-s3** | **spring-cloud-azure-starter-storage-blob** | **spring-cloud-gcp-starter-storage** (coordinates depend on library generation) |
| Common Java client | **S3Client**, sometimes **S3AsyncClient** | **BlobServiceClient** or async variant | **Storage** from Google Cloud Java client |
| Common identity source | AWS default credentials chain, IAM role | DefaultAzureCredential, Managed Identity | Application Default Credentials, workload identity |
| Resource scope | Region + bucket | Storage account/endpoint + container | Project + bucket and bucket location |
| Key customization points | Region, credential provider, endpoint, retry/timeout | Endpoint, credential, retry/transport | Project, credentials, transport/retry |

The path of the adapters can be described by the same diagram:

~~~text
Business service
  -> Application-defined StoragePort
  -> Provider adapter
  -> Spring-managed client or template
  -> AWS / Azure / Google Cloud SDK
  -> Corresponding managed service
~~~

In many cases, Spring Cloud creates a higher-level **template** over the SDK client and the adapter calls that template. In other cases, the adapter calls the Spring-injected SDK client directly. Both still use beans and dependency injection; they differ in the abstraction exposed to the developer.

**Distinguish configuration sources carefully:**

- **AWS:** Region, credential chain, and endpoint must be consistent with S3 or the target service. A workload IAM role can be used, but a valid role still needs permissions granted on the bucket.
- **Azure:** Endpoints are tied to a storage account; Managed Identity/DefaultAzureCredential handles authentication, while Azure RBAC and storage policies determine authorization.
- **Google Cloud:** Project ID selects the working project; ADC determines credentials; bucket/project permissions must be granted separately. A bucket location is not directly equivalent to an S3 region endpoint.

You cannot assume renaming an AWS property to an Azure or GCP equivalent is enough to switch clouds. Beans, builders, retry mechanisms, lifecycles, and service characteristics must be verified per library. Before applying examples to a project, use a compatible **BOM** for each family and read documentation for the exact version.

## 10. A Cloud Client Can Be Configured Correctly and Still Fail at Runtime

Auto-configuration only determines which objects are registered and initialized; it does not replace security or connectivity steps:

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant A as Auto-config
    participant C as Cloud SDK client
    participant I as Identity provider
    participant S as Managed service
    B->>A: Evaluate conditions and properties
    A-->>B: Register client bean
    B->>C: Create / inject client
    Note over B,C: Context may start successfully
    C->>I: Fetch credential / token when needed
    I-->>C: Identity or authentication error
    C->>S: Request to endpoint
    S-->>C: Success / 403 / 429 / 5xx
~~~

For example, the Spring container has an **S3Client** and the service injects it successfully, yet calling **putObject** throws **AccessDenied**. This usually points to IAM/policy/bucket settings or the active identity, and does not directly indicate wrong auto-configuration conditions. Conversely, if Spring reports **NoSuchBeanDefinitionException** for **S3Client** at startup, check the starter, conditions, dependencies, bean scanning, and configuration before checking IAM.

## 11. Diagnosing Unexpected Auto-Configuration Behavior

### 11.1. Investigation Procedure

1. **Read the initial error**: missing bean, multiple beans, bean initialization failure, or runtime network error?
2. **Check dependencies/BOM**: are the starter and SDK present with compatible versions? Are there classpath conflicts?
3. **Inspect effective properties**: are profiles, environment variables, property sources, precedence order, and property namespaces right?
4. **Inspect the Condition Evaluation Report**: which auto-config branch matched, which backed off, and why?
5. **Inspect the bean graph**: how many beans of the same type exist, what are their names/qualifiers, and which bean is injected into templates/listeners/adapters?
6. **Run a controlled cloud check**: if the context is healthy, verify identity, permissions, endpoint, network, and service policies.

In development, you can enable the condition report with the **--debug** flag when running Spring Boot. If Actuator is configured with appropriate authorization, the **/actuator/conditions** endpoint can help inspect condition evaluation results; do not expose internal diagnostic endpoints to public users.

### 11.2. Symptoms and Potential Causes

| Symptom | What to Check First | Fix by Root Cause |
| --- | --- | --- |
| **NoSuchBeanDefinitionException** | Is the starter on the classpath? Do conditions/properties match? | Add the right dependency, fix conditions, or declare the needed bean |
| **UnsatisfiedDependencyException** on adapter | Which bean dependency is missing or failed to initialize? | Follow the root cause, bean definitions, and bound configuration |
| **NoUniqueBeanDefinitionException** | Are there multiple clients of the same type? | Use qualifiers/bean names, or reduce bean count to match design |
| **BeanDefinitionOverrideException** | Are two beans being registered under the same name? | Rename or adjust conditions, remove duplicate definition |
| Newly added property ignored; client still uses defaults | Does the property belong to the starter and right namespace? Is a custom bean overriding? | Verify property binding and which bean is actually in use |
| Client injected successfully but **403/PermissionDenied** | Identity, IAM/RBAC/policy, resource scope | Grant least-privilege permissions on the right resource, check deny rules and workload identity |
| Client calls wrong project/region/account | Two configuration sources, env vars, hard-coded builder | Pick one intentional value source and verify the runtime bean |
| Timeouts or excessive retries | HTTP client, endpoint, proxy, quotas, multi-layer retry policies | Check network and total call duration, avoid stacked retries |

**Be careful with sensitive information:** during diagnostics you may log bean names, classes, non-sensitive display endpoints, regions/projects, and sanitized error causes. Do not log access keys, SAS tokens, connection strings, secrets, OAuth tokens, or sensitive data payloads. Turning on full SDK debug logging in production can leak sensitive information and generate excessive logs.

## 12. Testing Bean Creation Conditions and Clients

There are two groups of tests with different goals:

**Context tests** verify Spring configuration: when properties are enabled/disabled, beans appear as expected, and when a user-defined client is present, the adapter picks the right bean. No cloud connection is needed.

**Cloud integration tests** verify that the SDK calls real APIs: the bucket/container exists, the identity has permissions, and endpoints and networking are valid. You can use LocalStack (for a subset of AWS services), Azurite (Azure Blob), or an appropriate test environment for Google Cloud; emulators do not fully simulate IAM/Managed Identity/workload identity and all service policies.

For the **DocumentStorageConfiguration** class in section 7, you can use Spring Boot Test's **ApplicationContextRunner** to test enable/disable branches without starting an entire server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import software.amazon.awssdk.services.s3.S3Client;

class DocumentStorageConfigurationTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(DocumentStorageConfiguration.class)
            .withBean(S3Client.class, () -> mock(S3Client.class));

    @Test
    void createsStorageWhenEnabled() {
        runner.withPropertyValues(
                "app.storage.enabled=true",
                "app.storage.bucket=demo-bucket")
            .run(context ->
                assertThat(context).hasSingleBean(DocumentStorage.class));
    }

    @Test
    void skipsStorageWhenDisabled() {
        runner.withPropertyValues("app.storage.enabled=false")
            .run(context ->
                assertThat(context).doesNotHaveBean(DocumentStorage.class));
    }
}
~~~

This test **does not call S3**; the client is a mock used to prove Spring wiring and conditions. To test a starter's own back-off branch, import the specific auto-configuration under test and compare contexts **with** and **without** a user-provided bean. When choosing test containers or real cloud environments, also verify timeouts/retries, permissions, isolated test data, and post-test cleanup.

A reliable test suite should cover:

- Property true/false/absent; including cases where properties are overridden by profiles or environment variables.
- Single default client, customized client, and multiple clients with explicit qualifiers.
- Missing credentials or missing permissions on real cloud (verifying adapter error classification), without conflating them with missing beans.
- Network timeouts, retries, and client reuse; ensuring no new client is created per call.
- Compatibility between starters and SDKs/BOMs when upgrading versions.

## 13. Hands-On Exercises

**Exercise 1 — Explain conditions.** Given an auto-config branch containing **@ConditionalOnClass(S3Client.class)**, **@ConditionalOnProperty(havingValue="true")**, and **@ConditionalOnMissingBean(S3Client.class)**, build a table of four scenarios: missing SDK, property false, custom S3Client present, and all conditions met. Indicate which branch creates the default bean.

**Exercise 2 — Safe customization.** Start with a region configured via Spring Cloud AWS properties. Design two approaches to add timeouts: using an official hook if supported by the library, or registering an **S3Client** bean yourself. Describe how to verify the client is actually injected and how to avoid duplicate retries across the SDK and service.

**Exercise 3 — Select provider.** Propose the property **app.storage.provider=aws|azure|gcp** and conditions to create three adapters implementing **DocumentStorage**. Point out the scenarios where two adapters are present simultaneously, where none is present, and how to report clear configuration errors at startup.

**Exercise 4 — Debug.** An application runs locally and receives **S3Client** normally, but on Kubernetes throws **NoUniqueBeanDefinitionException** after adding an archive client configuration. Use the condition report and bean list to identify the conflict; propose using **@Qualifier** and check related templates.

**Exercise 5 — Cloud comparison.** Draw a diagram covering service → storage port → adapter → SDK client → managed service for Azure Blob and Google Cloud Storage. Explicitly mark where Spring binds properties, where credentials/tokens are acquired, and where the cloud service decides access permissions.

## 14. Key Takeaways

- **Auto-configuration is a startup bean registration and creation mechanism** driven by classpath, properties, and context state; it is not a network call to the cloud.
- **@ConditionalOnMissingBean** typically lets a starter yield to an application-declared bean, though you must verify the library's exact conditions and scope.
- **Properties → supported customizer → custom client bean** represent three levels of customization with increasing control and maintenance responsibility.
- **@Primary/@Qualifier** handle bean selection when multiple candidates exist; bean creation conditions and bean selection are two distinct concerns.
- A context that starts successfully does not guarantee the workload has **valid credentials, proper IAM/RBAC, network connectivity, or permission to use resources**.
- The same mindset applies to Spring Cloud AWS, Azure, and GCP, but you must verify the **BOM, starter, SDK classes, properties, and lifecycle** of the exact provider and version.
