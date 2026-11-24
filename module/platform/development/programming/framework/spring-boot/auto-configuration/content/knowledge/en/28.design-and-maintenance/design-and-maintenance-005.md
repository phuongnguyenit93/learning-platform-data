# Do not create external resources just to evaluate activation conditions

> **Spring Boot Auto Configuration → Design and Maintenance.** This lesson explains why an auto-configuration condition should only decide whether a configuration applies based on configuration information and existing local state. A condition should not call a remote service or create a database table, bucket, queue, or topic merely to check whether a feature can be enabled. The hands-on example uses Spring Boot 3.3.13 and Java 17: an archive feature is enabled via a property, the client is constructed without network connections, and a fake transport confirms zero requests during ApplicationContext refresh.

## 1. Principle: conditions decide configuration, not infrastructure provisioning

Auto-configuration answers the question: **given the current classpath, Environment, and bean definitions, which beans should be registered?**

Examples:
- Did the user enable the feature with a property?
- Is the required library on the classpath?
- Has a foundation bean needed by the integration already been registered?
- Does a configuration file exist on the classpath or at a Spring-supported resource location?
- Is the application a servlet, reactive, or non-web context?

These questions concern configuration and state that Spring can evaluate while building the ApplicationContext.

A condition should not create external resources itself to answer an on/off question. For instance, do not create an S3 bucket, database schema, table, Kafka topic, message queue, remote tenant, or cloud project solely to decide whether a bean should be registered.

Doing so mixes three distinct responsibilities:

1. **Activation:** deciding whether a bean/configuration is registered based on properties, classpath, bean definitions, and existing configuration.
2. **Provisioning:** creating or updating infrastructure such as databases, buckets, topics, queues, schemas, or service accounts.
3. **Availability:** checking whether an external service is up, reachable, and meeting operational requirements.

These three concerns may relate to the same integration, but they have different lifecycles, permissions, and testing strategies. Conditions should handle the first. Provisioning belongs to infrastructure management workflows or an explicitly designed initialization step. Availability belongs to health/readiness probes or an intentional connection verification step.

## 2. Why is creating resources inside a condition dangerous?

Suppose a library wants to enable an archiving feature when a bucket exists. A custom condition is written like this:

~~~java
// ANTI-PATTERN: pseudocode, not an implementation for use.
public boolean matches(ConditionContext context,
                       AnnotatedTypeMetadata metadata) {
    return cloudAdmin.createBucketIfMissing("notice-archive");
}
~~~

This condition both checks state and mutates infrastructure. Bucket creation becomes a side effect of configuration parsing. That causes multiple problems.

### 2.1. Application startup unexpectedly alters infrastructure

An operator only intended to start the application, yet context refresh creates a bucket or topic. A seemingly harmless configuration change can provision billable resources, alter permissions, or affect other applications.

This is especially dangerous if resource names are shared across environments or instances. A staging instance might accidentally create resources in a production project if credentials or endpoints are misconfigured.

### 2.2. Conditions can be evaluated across multiple contexts and multiple times

Do not rely on the assumption that a condition runs exactly once across the system's entire lifecycle. There can be multiple ApplicationContexts, test contexts, parent/child contexts, restarts, or repeated evaluations at different configuration-processing stages.

If every evaluation triggers resource creation:
- Concurrent creation requests can occur.
- Multiple resources can be created if names are unstable.
- Race conditions can occur when multiple instances start simultaneously.
- Orphaned resources can remain if context startup fails later.
- Tests can mutate shared cloud accounts or databases.

Even an idempotent resource-creation API does not make a condition an appropriate place for provisioning. Idempotency reduces some repetition risks; it does not solve resource ownership, cost, race conditions, rollback, or deletion responsibility.

### 2.3. Conditions become slow and network-dependent

A condition calling HTTP, a database, or a cloud control plane depends on:
- DNS and TLS.
- Network latency.
- Credentials and token refresh.
- Rate limits.
- Timeouts.
- External service outages.
- Proxies, firewalls, and environment settings.

When the external service is slow, ApplicationContext refresh slows down too. When the external service is temporarily unreachable, the condition may return no-match even though the feature is properly configured.

This makes startup flaky and hard to reproduce. What should be a fast configuration check turns into an I/O operation.

### 2.4. Condition results can mask configuration errors

If a condition calls a service and returns false when unable to connect, Spring may skip the bean. The application keeps starting without the feature the operator believed was enabled.

Conversely, if the condition creates a resource successfully and returns true, users may not realize the application just mutated infrastructure. When resource creation fails, the error surfaces as a Spring startup failure even though the real cause is provisioning permissions or the cloud control plane.

It is much better to represent clearly:
- Whether the feature is enabled.
- Whether endpoint/credential configuration is valid.
- Whether the resource has been provisioned.
- Whether the service is available.

### 2.5. Application permissions are unnecessarily broadened

An application's runtime identity typically only needs permission to use resources, such as writing objects to a bucket or sending messages to a queue. If a condition creates resources, the application needs administrative permissions such as create bucket, create topic, create schema, or create IAM policies.

Infrastructure admin permissions are far broader than application runtime permissions. Separating provisioning from runtime enforces least privilege: pipelines/infrastructure hold creation permissions, while workloads hold usage permissions only.

## 3. What should conditions check?

Spring Boot provides standard conditions to decide whether to apply a configuration or bean.

| Condition | What is checked | What it does not prove |
| --- | --- | --- |
| `@ConditionalOnProperty` | Value in Spring Environment | Remote service is healthy |
| `@ConditionalOnClass` | Class is on the runtime classpath | Credentials or external service are valid |
| `@ConditionalOnMissingClass` | Class is absent from the classpath | Cloud resource does not exist |
| `@ConditionalOnBean` | Matching bean exists in BeanFactory | That bean can connect to a database or broker |
| `@ConditionalOnMissingBean` | No matching bean exists at evaluation time | It is safe to create external resources |
| `@ConditionalOnResource` | Resource at a Spring-resolvable location exists | A bucket, queue, or database table can be created |
| `@ConditionalOnWebApplication` | Application context type | HTTP server or external endpoint is healthy |

These conditions answer questions about configuration, classpath, bean registry, or resource locations. They are not infrastructure provisioning tools.

### 3.1. Use properties to enable features

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.archive",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
static class ArchiveEnabledConfiguration {
}
~~~

The feature applies only when the property equals true. When the property is missing or false, the configuration is skipped.

This property expresses the operator's intent. It does not by itself verify that the endpoint is reachable or that the bucket already exists.

### 3.2. Use classpath conditions for optional integrations

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.archive.ArchiveSdk")
static class ArchiveSdkConfiguration {
}
~~~

This condition checks whether the SDK is on the runtime classpath. It does not download the SDK over the network and does not create cloud resources.

When the optional library is absent, the nested configuration is skipped. Core beans that do not depend on the SDK continue to operate.

### 3.3. Use bean conditions for registered dependencies

~~~java
@Bean
@ConditionalOnBean(DataSource.class)
@ConditionalOnMissingBean(ArchiveRepository.class)
ArchiveRepository archiveRepository(DataSource dataSource) {
    return new JdbcArchiveRepository(dataSource);
}
~~~

Here Spring checks that a DataSource bean exists in the BeanFactory and no replacement ArchiveRepository exists yet. The condition does not execute SQL to inspect schemas, nor does it create databases or tables.

If schemas require migration, use a migration tool or an explicit provisioning step. The presence of a DataSource bean does not guarantee the schema is ready.

### 3.4. Use resource conditions for actual configuration files

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:/acme/archive-defaults.json"
)
static class ArchiveDefaultsConfiguration {
}
~~~

This condition checks a resource location that Spring can resolve, such as a file on the classpath or a location following Spring's Resource conventions. It does not create files, buckets, database tables, or topics.

Do not use a resource condition as a substitute for a cloud resource provisioning workflow. If remote availability must be checked, use health/readiness probes or a dedicated connectivity check.

### 3.5. Custom Conditions read only local configuration state

When standard annotations are insufficient, a custom condition can inspect the Environment or classloader:

~~~java
public final class OnArchiveModeCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        return context.getEnvironment().getProperty(
                "acme.archive.mode",
                "disabled"
        ).equalsIgnoreCase("enabled");
    }
}
~~~

This condition only reads a property; it creates no beans, calls no external services, and makes no infrastructure changes.

If a custom condition merely checks a boolean property, ConditionalOnProperty is usually simpler and clearer. Write a custom condition only when genuinely needed rules demand it.

## 4. Separate activation, provisioning, and availability

A clean design puts each responsibility in its proper place.

| Responsibility | Question | Appropriate mechanism |
| --- | --- | --- |
| Activation | Should ArchiveClient be registered? | Property/classpath/bean conditions |
| Provisioning | Has the bucket or schema been created, and if not, who creates it? | IaC, migrations, pipelines, or an explicitly enabled provisioner |
| Availability | Does the endpoint respond and is the resource usable? | Health indicator, readiness probe, or startup validator |
| Runtime operation | Did writing an object or sending a message succeed? | Client call with appropriate timeout/retry |

### 4.1. Activation does not require connecting to the service

If the user sets:

~~~properties
acme.archive.enabled=true
acme.archive.endpoint=https://archive.example.test/objects
~~~

Spring can register ArchiveClient based on the property and endpoint configuration. Creating a client object does not require sending an HTTP request.

The constructor may:
- Store the endpoint.
- Build a local HTTP client.
- Configure timeouts.
- Validate configuration syntax.
- Receive an injected transport.

The constructor should not:
- Send requests to create a bucket.
- Create database tables.
- Create queues or topics.
- Upload a dummy object to check whether the endpoint works.
- Call a remote API just to decide whether the bean should exist.

### 4.2. Provisioning is a separate workflow

External resources are typically managed by:
- Terraform, CloudFormation, or another Infrastructure as Code tool.
- Kubernetes operators or manifests.
- Database migrations such as Flyway/Liquibase.
- Deployment pipelines.
- A dedicated administrative command or provisioning job.
- An in-application provisioner if the product genuinely owns that resource lifecycle.

If the application is responsible for creating resources, model this action as an explicit workflow. The workflow must define resource ownership, naming and namespaces, create/delete permissions, idempotency, rollback, cleanup, and behavior when the resource already exists.

Do not hide provisioning inside Condition.matches(...), ConditionalOnProperty, or factory methods meant solely to decide whether to register a bean.

### 4.3. Availability belongs to health and readiness

A service can be properly configured yet temporarily unreachable. That does not mean the client bean should not exist.

Options:
- Health indicators check service status when Actuator health is queried.
- Readiness probes report the application unready for traffic when a required dependency is unavailable.
- Startup validators run a timeout-bounded check if the contract requires fail-fast behavior.
- Runtime clients handle connection errors, retries, and circuit breakers per business policy.

Health checks should inspect status via read-only checks or health endpoints. They must not create new resources just to make health report UP.

If a resource must exist before the application runs, the provisioning pipeline should create it prior to deployment. The application can fail fast if required configuration is invalid or report readiness DOWN if the resource is unavailable, per the published contract.

### 4.4. Do not turn availability failures into no-match

Suppose a property enables the feature while the cloud service is timing out. If a custom condition returns false, the bean disappears and the application may start missing the feature.

Those are two distinct outcomes:
- Property false: the user explicitly disabled the feature.
- Property true yet service timeout: the feature is enabled, and the dependency is currently unavailable.

Keep these two states separate. Conditions decide whether the bean is configured; health/readiness indicates whether the dependency is available.

## 5. Anti-pattern example: creating a bucket in a Condition

A flawed implementation might look like this:

~~~java
// ANTI-PATTERN: pseudocode to recognize the design flaw.
public final class OnArchiveBucketCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        CloudAdminClient admin = createAdminClient(context);

        if (!admin.bucketExists("notice-archive")) {
            admin.createBucket("notice-archive");
        }

        return admin.bucketExists("notice-archive");
    }
}
~~~

Issues:
1. matches requires network I/O and can block context refresh.
2. The condition requires administrative credentials.
3. Creating a bucket is an unintended side effect of activation.
4. Two instances starting simultaneously may race to create the resource.
5. If context startup fails on another bean, the bucket remains behind.
6. Unit tests require a cloud client or real cloud resources.
7. A remote service outage can make the condition return no-match.
8. There is no clear place to manage ownership, cleanup, and cost.

Fix the design by:
- Having the condition check only properties or classpath.
- Creating the client bean without connecting.
- Running provisioning before deployment or via a separate command/job.
- Checking usability via health/readiness after the resource is provisioned.

## 6. Complete example: ArchiveClient creates no resources on context refresh

This lab builds an HTTP client to send content to an archive endpoint. Goals:
- The feature activates only when acme.archive.enabled=true.
- The bean is created without calling the endpoint.
- HTTP requests are sent only when business code calls ArchiveClient.put(...).
- Tests use a fake transport to prove zero requests occur during ApplicationContext refresh.

The example uses Java 17, as java.net.http.HttpClient is built into JDK 11 and later.

### 6.1. Directory structure

~~~text
archive-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/archive/
    │   │   ├── ArchiveClient.java
    │   │   ├── ArchiveProperties.java
    │   │   ├── ArchiveTransport.java
    │   │   └── JdkArchiveTransport.java
    │   ├── java/com/acme/archive/autoconfigure/
    │   │   └── ArchiveAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/archive/autoconfigure/
            └── ArchiveAutoConfigurationTest.java
~~~

### 6.2. pom.xml

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme.archive</groupId>
    <artifactId>archive-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

spring-boot-autoconfigure provides auto-configuration annotations and mechanisms. spring-boot-starter-test provides JUnit 5, AssertJ, and ApplicationContextRunner for testing.

No cloud SDK or database driver is required because the lab only models an HTTP client. If a real integration requires an optional SDK, declare the dependency in the appropriate module and guard references to the SDK with a nested configuration class-level condition.

### 6.3. ArchiveProperties.java

File src/main/java/com/acme/archive/ArchiveProperties.java:

~~~java
package com.acme.archive;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.archive")
public class ArchiveProperties {

    private URI endpoint;

    private Duration connectTimeout = Duration.ofSeconds(2);

    private Duration requestTimeout = Duration.ofSeconds(5);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

Properties hold configuration, not remote-service calling logic. Endpoint is required when the feature is enabled; timeouts have defaults.

### 6.4. ArchiveTransport.java

File src/main/java/com/acme/archive/ArchiveTransport.java:

~~~java
package com.acme.archive;

import java.io.IOException;
import java.net.URI;

public interface ArchiveTransport {

    int put(URI endpoint, String content)
            throws IOException, InterruptedException;
}
~~~

This interface decouples request sending from the business client. Tests can replace the real transport with a fake implementation to record requests.

### 6.5. JdkArchiveTransport.java

File src/main/java/com/acme/archive/JdkArchiveTransport.java:

~~~java
package com.acme.archive;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class JdkArchiveTransport implements ArchiveTransport {

    private final HttpClient httpClient;
    private final Duration requestTimeout;

    public JdkArchiveTransport(
            Duration connectTimeout,
            Duration requestTimeout) {

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();

        this.requestTimeout = requestTimeout;
    }

    @Override
    public int put(URI endpoint, String content)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(requestTimeout)
                .header("Content-Type", "text/plain; charset=utf-8")
                .PUT(HttpRequest.BodyPublishers.ofString(content))
                .build();

        HttpResponse<Void> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.discarding()
        );

        return response.statusCode();
    }
}
~~~

The constructor only creates a local HttpClient and stores the timeout. It sends no requests, checks no endpoints, and creates no remote resources.

Network I/O happens only in put(...), when an actual business operation requests writing an archive entry. Requests have a dedicated timeout to avoid waiting indefinitely.

### 6.6. ArchiveClient.java

File src/main/java/com/acme/archive/ArchiveClient.java:

~~~java
package com.acme.archive;

import java.io.IOException;
import java.net.URI;

public class ArchiveClient {

    private final ArchiveTransport transport;
    private final URI endpoint;

    public ArchiveClient(ArchiveTransport transport, URI endpoint) {
        this.transport = transport;
        this.endpoint = endpoint;
    }

    public int put(String content)
            throws IOException, InterruptedException {

        return transport.put(endpoint, content);
    }
}
~~~

The client holds the transport and endpoint. There is no availability check or provisioning in the constructor. Only when the user invokes put does the client perform a remote operation.

### 6.7. ArchiveAutoConfiguration.java

File src/main/java/com/acme/archive/autoconfigure/ArchiveAutoConfiguration.java:

~~~java
package com.acme.archive.autoconfigure;

import com.acme.archive.ArchiveClient;
import com.acme.archive.ArchiveProperties;
import com.acme.archive.ArchiveTransport;
import com.acme.archive.JdkArchiveTransport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ArchiveAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "acme.archive",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @EnableConfigurationProperties(ArchiveProperties.class)
    static class EnabledArchiveConfiguration {

        @Bean
        @ConditionalOnMissingBean(ArchiveTransport.class)
        ArchiveTransport archiveTransport(ArchiveProperties properties) {
            return new JdkArchiveTransport(
                    properties.getConnectTimeout(),
                    properties.getRequestTimeout()
            );
        }

        @Bean
        @ConditionalOnMissingBean(ArchiveClient.class)
        ArchiveClient archiveClient(
                ArchiveTransport transport,
                ArchiveProperties properties) {

            if (properties.getEndpoint() == null) {
                throw new IllegalStateException(
                        "Set acme.archive.endpoint when "
                                + "acme.archive.enabled=true"
                );
            }

            return new ArchiveClient(
                    transport,
                    properties.getEndpoint()
            );
        }
    }
}
~~~

The configuration is split into two layers:
- Outer auto-configuration performs no provisioning or network I/O.
- Nested configuration applies only when the property is enabled.

When the feature is disabled or the property is missing:
- The nested configuration is not registered.
- Default ArchiveProperties, ArchiveTransport, and ArchiveClient do not appear.
- No client is constructed to call the remote service.

When the feature is enabled:
- Properties are bound.
- Transport and client are created.
- A missing endpoint causes startup to fail with a clear configuration message.
- A present endpoint whose remote service is not yet responding does not cause the context to make network calls. Availability checking belongs to a separate step.

ConditionalOnMissingBean lets the application replace the default transport or client with its own implementation.

### 6.8. AutoConfiguration.imports

Create file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.acme.archive.autoconfigure.ArchiveAutoConfiguration
~~~

This is the resource Spring Boot uses to discover auto-configuration inside the JAR. Tests using AutoConfigurations.of(...) load the class directly; verifying metadata inside the JAR requires a separate consumer test if the module is published for other applications.

## 7. Test proving context refresh does not call external services

File src/test/java/com/acme/archive/autoconfigure/ArchiveAutoConfigurationTest.java:

~~~java
package com.acme.archive.autoconfigure;

import java.io.IOException;
import java.net.URI;

import com.acme.archive.ArchiveClient;
import com.acme.archive.ArchiveProperties;
import com.acme.archive.ArchiveTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ArchiveAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ArchiveAutoConfiguration.class
                    ));

    static class RecordingArchiveTransport implements ArchiveTransport {

        private int calls;
        private URI lastEndpoint;
        private String lastContent;

        @Override
        public int put(URI endpoint, String content) throws IOException {
            calls++;
            lastEndpoint = endpoint;
            lastContent = content;
            return 201;
        }
    }

    @Test
    void featureIsDisabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(ArchiveClient.class);
            assertThat(context).doesNotHaveBean(ArchiveTransport.class);
            assertThat(context).doesNotHaveBean(ArchiveProperties.class);
        });
    }

    @Test
    void falsePropertyDoesNotRegisterArchiveBeans() {
        runner.withPropertyValues("acme.archive.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(ArchiveClient.class);
                    assertThat(context).doesNotHaveBean(ArchiveTransport.class);
                });
    }

    @Test
    void contextRefreshDoesNotCallRemoteTransport() {
        RecordingArchiveTransport transport =
                new RecordingArchiveTransport();

        runner.withPropertyValues(
                "acme.archive.enabled=true",
                "acme.archive.endpoint=https://archive.example.test/objects",
                "acme.archive.connect-timeout=1s",
                "acme.archive.request-timeout=3s"
        ).withBean(ArchiveTransport.class, () -> transport)
         .run(context -> {
             assertThat(context).hasNotFailed();
             assertThat(context).hasSingleBean(ArchiveClient.class);

             ArchiveClient client = context.getBean(ArchiveClient.class);

             // Context has refreshed, yet no HTTP operation has occurred.
             assertThat(transport.calls).isZero();

             int status;
             try {
                 status = client.put("invoice-42");
             }
             catch (InterruptedException ex) {
                 Thread.currentThread().interrupt();
                 throw new AssertionError(ex);
             }
             catch (IOException ex) {
                 throw new AssertionError(ex);
             }

             // Request happens only after an explicit business call.
             assertThat(status).isEqualTo(201);
             assertThat(transport.calls).isEqualTo(1);
             assertThat(transport.lastEndpoint)
                     .isEqualTo(URI.create(
                             "https://archive.example.test/objects"
                     ));
             assertThat(transport.lastContent).isEqualTo("invoice-42");
         });
    }

    @Test
    void enabledFeatureRequiresEndpointConfiguration() {
        runner.withPropertyValues("acme.archive.enabled=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(rootCause(context.getStartupFailure())
                            .getMessage())
                            .contains("acme.archive.endpoint");
                });
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;

        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }

        return current;
    }
}
~~~

The test uses RecordingArchiveTransport instead of real HTTP. After context refresh:
- ArchiveClient already exists.
- The transport has received zero requests.
- Only after the test invokes client.put(...) does the counter increment to one.

This is direct proof that activation does not need to call external services. The test also confirms that missing or false properties register no beans, and a missing endpoint configuration is reported clearly when the feature is enabled.

### 7.1. Run tests

From the directory containing pom.xml:

~~~bash
mvn clean test
~~~

Expected four tests to PASS. The tests require no cloud account, real bucket, database, or HTTP server.

If a test fails:
- Check that ArchiveAutoConfiguration has the right condition prefix/property.
- Check that EnableConfigurationProperties sits inside the guarded nested configuration.
- Check that ArchiveClient's constructor does not call transport.
- Check that JdkArchiveTransport's constructor does not send requests or call provisioning APIs.
- Check that the test registers the fake transport before the default factory method is applied.

## 8. Checking existing resources differs from creating resources

There are cases where an application needs to know a resource already exists before receiving traffic. For instance, a bucket, table, or queue must be provisioned beforehand.

That does not mean a condition should create the resource. Choose an approach matching the goal:

| Goal | Appropriate action |
| --- | --- |
| Decide only whether the feature is enabled | Read properties or check classpath/beans |
| Confirm a local configuration file is present | Use ConditionalOnResource or check the resource in configuration |
| Check whether a bucket was created | Use a read-only health/startup validator without creating the bucket |
| Create a bucket if missing per deployment workflow | IaC or an explicitly enabled provisioner |
| Verify database schema was migrated | Run a separate migration/version check |
| Create a Kafka topic | Provisioning pipeline or topic-management workflow |
| Check whether a broker responds | Health/readiness or timeout-bounded client operation |
| Create a remote tenant/project | Dedicated admin workflow with clear permissions and audit |

### 8.1. If the resource must exist before startup

You can define a fail-fast contract:
1. The feature is enabled by property.
2. The client bean is registered.
3. A startup validator performs a read-only check with a bounded timeout.
4. If the resource does not exist, the application stops with a specific message.

This is intentional validation, not a condition. It still generates network I/O and affects startup, so use it only if operational requirements genuinely demand it.

If the resource may be temporarily unavailable while the application should still run, use readiness probes to report an unready state. Do not silently return condition no-match and make the bean disappear.

### 8.2. If the application owns provisioning

If the product intentionally creates resources, place that logic in a component with a clear contract, such as:
- ArchiveProvisioner.ensureContainerExists().
- An ApplicationRunner enabled only by a dedicated property.
- A CLI command run before deploying the workload.
- A migration job running under an identity with DDL permissions.

You must define:
- Who owns the resource and who is allowed to delete it?
- Are resource names namespaced by environment/application?
- Is the creation API idempotent?
- How is concurrency handled if two instances run simultaneously?
- If provisioning succeeds yet context startup fails, how is cleanup handled?
- Are there audit logs and metrics for the operation?
- Can the runtime workload drop create permissions after provisioning?

The key point: operators must know a provisioning action is taking place. Never let it happen as a side effect of condition evaluation.

## 9. Testing activation without real resources

An auto-configuration test suite should verify bean registration logic using lightweight contexts, fake data, and controlled classloaders.

### 9.1. ApplicationContextRunner for property and bean conditions

ApplicationContextRunner lets you create contexts with specific property sets and bean definitions. Each run(...) creates an isolated test context.

Examples:
- Property missing: feature disabled.
- Property false: feature disabled.
- Property true: client bean appears.
- User bean already exists: auto-configuration backs off.
- Dependency bean missing: integration bean does not appear.

These tests require no cloud account or real database because they verify the activation contract, not the network protocol.

### 9.2. Use fake transports or mocks

A fake transport records:
- How many calls were made.
- Which endpoint was targeted.
- Which payload was sent.
- Which result or exception was returned.

In the sample test, the counter is 0 immediately after context refresh and increments only after ArchiveClient.put(...).

This is a good way to catch someone accidentally adding an HTTP call to a constructor or factory method in a future refactor.

### 9.3. Use FilteredClassLoader for optional libraries

If an integration depends on an optional SDK, you can simulate missing classes:

~~~java
runner.withClassLoader(
        new FilteredClassLoader("com.vendor.archive")
).run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).doesNotHaveBean(ArchiveClient.class);
});
~~~

This test verifies the classpath condition and optional boundary. It does not need to download the SDK, connect to the cloud, or create resources.

### 9.4. When to use Testcontainers?

Testcontainers fits integration tests that need to verify real behavior against a database, broker, or compatible service running in a test environment.

In that case:
- The container/resource is a fixture explicitly created by the test.
- Use test-specific data and names.
- Run migrations or setup in a test setup step.
- Destroy the container/resource after the test.
- Never let unit/condition tests share production cloud resources.

An integration test may create a test database to verify migrations. That is completely different from creating a database solely to decide whether an auto-configuration is registered.

### 9.5. Test provisioning separately

If provisioning is part of the product:
- Test idempotency of the provisioner.
- Test missing permissions or API error responses.
- Test two concurrent creation requests.
- Test cleanup and rollback.
- Test pre-existing resources.
- Test audits/metrics and error messages.

Do not lump these tests into ApplicationContextRunner tests intended solely to check conditions.

## 10. Reading failures when conditions and resources are mixed

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Context refresh takes several seconds | Condition calls HTTP/database/cloud API | Remove I/O from conditions; measure with logs/profiler |
| Feature disappears when cloud is temporarily down | Condition turns availability into no-match | Keep activation property-driven; use health/readiness |
| Every test run creates another bucket/topic | Condition has side effects | Use fakes for condition tests; separate provisioning |
| App needs create-bucket permission to start | Runtime identity is performing admin tasks | Separate provisioning identity and runtime identity |
| Unit tests require cloud credentials | Condition depends on cloud admin client | Conditions read local configuration only |
| Context fails after resource was already created | Provisioning runs during config refresh | Move provisioning to a workflow with rollback/cleanup |
| Resource created yet bean is not registered | Subsequent condition no-match or bean creation fails | Separate provisioning step from activation step |
| Startup is sometimes fast, sometimes slow | Condition depends on network/remote service | Make no network calls inside conditions |
| Bucket exists yet service is unreachable | Existence and availability were conflated | Check permissions, endpoint, and health separately |
| Client created even though feature is disabled | Bean sits outside guarded nested configuration | Place bean inside guarded configuration |

When reading the Condition Evaluation Report, note:
- Condition no-match because a property is false is configuration behavior.
- Condition no-match because a class is missing is classpath behavior.
- ConditionalOnBean no-match because a bean is not registered is BeanFactory behavior.
- Remote timeouts should never appear as an activation condition reason if responsibilities are properly separated.

If the condition report shows a custom condition queried a remote service, treat that as a signal to separate responsibilities.

## 11. Common design mistakes

1. **Creating a bucket in Condition.matches.** Context refresh alters cloud infrastructure.
2. **Running CREATE TABLE IF NOT EXISTS in a condition.** The condition both decides configuration and executes migrations.
3. **Creating a Kafka topic to check if the broker works.** Creating a topic is not a health check.
4. **Sending a probe message to a queue to decide bean registration.** Can pollute data or trigger consumers.
5. **Uploading a dummy object to verify a bucket.** This is a business operation with side effects.
6. **Calling a remote health endpoint from a condition.** Startup depends on network and transient state.
7. **Returning no-match on remote timeout.** Feature was enabled yet the bean vanishes due to availability.
8. **Creating resources inside a client constructor.** Simply instantiating the bean mutates infrastructure.
9. **Putting provisioning inside a @Bean factory method.** Factory methods can re-run across contexts and are hard to roll back.
10. **Using @ConditionalOnBean as a connectivity check.** The annotation inspects bean definitions, not remote services.
11. **Using @ConditionalOnResource for buckets or topics.** Resource conditions are not cloud resource management tools.
12. **Granting overly broad admin rights to runtime identity.** Applications do not need create/delete rights just to activate a feature.
13. **Not distinguishing property false from remote service down.** The two states need different messages and handling.
14. **Having no timeout on health/startup validation.** Even read-only checks can hang startup.
15. **Using production resources in activation tests.** Tests can modify or delete real data.
16. **Testing only the feature-enabled branch.** Must verify disabled feature creates no client or transport.
17. **Not checking request count after context refresh.** Can miss network calls inside constructors.
18. **Assuming idempotency means side effects are safe.** Cost, permissions, races, and ownership still apply.
19. **Creating resources with no cleanup policy.** Orphaned resources linger after tests or failed deployments.
20. **Writing a custom condition for a simple property.** ConditionalOnProperty is clearer and easier to test.
21. **Collapsing provisioning and readiness into one boolean.** A resource may already be provisioned while the service is unavailable.
22. **Swallowing provisioning errors and proceeding as if enabled.** Application state no longer reflects real infrastructure.

## 12. Safe design workflow

1. Clearly document which property enables the feature and what the default is.
2. List required classpath dependencies for the integration.
3. List bean definitions needed by the integration.
4. Use standard conditions to decide whether configurations/beans are registered.
5. Ensure Condition.matches makes no network calls, creates no external files or resources, and mutates no state.
6. Keep client constructors/factory methods free of provisioning.
7. Put endpoints, timeouts, and credentials into configuration properties.
8. Check missing configuration via validation/fail-fast with clear messages.
9. Put resource provisioning in IaC, migrations, or an explicitly triggered workflow.
10. Use health/readiness probes or a separate startup validator if availability verification is needed.
11. Restrict runtime permissions to resource usage; separate provisioning permissions.
12. Write ApplicationContextRunner tests for property/classpath/bean combinations.
13. Use a fake transport to confirm context refresh sends zero requests.
14. Use FilteredClassLoader when testing optional dependencies.
15. Use Testcontainers or dedicated integration environments when verifying real protocols/resources.
16. Measure startup and inspect logs to catch unintended I/O during refresh.

## 13. Acceptance checklist

- [ ] Conditions read only required properties, classpath, bean definitions, or resource locations.
- [ ] No resource create/update/delete happens inside Condition.matches.
- [ ] No HTTP/database/cloud control-plane calls happen inside conditions.
- [ ] Feature activation is separated from provisioning and availability.
- [ ] ConditionalOnProperty has clear prefix, name, havingValue, and matchIfMissing.
- [ ] Optional classes are guarded by classpath conditions at the proper scope.
- [ ] ConditionalOnBean is used only to check registered beans.
- [ ] ConditionalOnResource is used only for Spring-resolvable resource locations.
- [ ] Constructors and factory methods do not create buckets, tables, topics, or queues.
- [ ] Clients perform I/O only when business operations are invoked.
- [ ] Timeouts are configured for connections and requests.
- [ ] Missing endpoints/credentials produce clear errors when the feature is enabled.
- [ ] Provisioning has defined ownership, permissions, idempotency, auditing, and cleanup policies.
- [ ] Runtime identity does not hold admin permissions just for conditions to run.
- [ ] Health/readiness reflects availability separately.
- [ ] Tests cover missing property and property false.
- [ ] Tests cover property true with fake transport.
- [ ] Tests confirm zero requests during context refresh.
- [ ] Tests confirm requests occur only when calling the client.
- [ ] Tests cover missing optional classes if the integration uses optional dependencies.
- [ ] Tests cover provisioning separately if the application owns the resource lifecycle.
- [ ] Production resources are never used in unit tests.

## 14. Self-check questions

**Question 1.** What should an auto-configuration condition decide?  
**Answer:** Whether to apply a configuration or register beans based on properties, classpath, bean definitions, and appropriate configuration state.

**Question 2.** Why should you not create a bucket inside Condition.matches?  
**Answer:** Because the condition turns into a provisioning action with side effects, requires admin permissions, depends on the network, may run across multiple contexts, and leaves orphaned resources if startup fails.

**Question 3.** Does ConditionalOnProperty prove a remote endpoint is working?  
**Answer:** No. It only checks a value in the Spring Environment.

**Question 4.** Does ConditionalOnBean(DataSource.class) prove the database schema already exists?  
**Answer:** No. It checks for a DataSource bean in the BeanFactory; it does not run migrations or verify schemas.

**Question 5.** What is ConditionalOnResource used for?  
**Answer:** Checking for a resource at a location Spring can resolve. It does not create cloud buckets, database tables, or message topics.

**Question 6.** If a feature is enabled yet the external service is down, how should it be handled?  
**Answer:** Keep activation driven by configuration; expose availability via health/readiness or a timeout-bounded startup validator if the contract requires fail-fast.

**Question 7.** Where should provisioning live?  
**Answer:** IaC, migrations, pipelines, admin jobs, or an explicitly enabled provisioner with its own lifecycle and permissions.

**Question 8.** How can you prove context refresh does not call external services?  
**Answer:** Inject a fake/recording transport, start the context, and assert the request count is 0; then call the client and confirm the counter increments.

**Question 9.** Is it acceptable to use Testcontainers to create a test database?  
**Answer:** Yes, when the database is an integration test fixture with its own setup/teardown. Never use it inside a condition just to decide bean activation.

**Question 10.** Why shouldn't the runtime identity have create-bucket permission just to start up?  
**Answer:** Provisioning is an infrastructure admin privilege. Runtime workloads normally only need permission to use already provisioned resources; separating permissions limits blast radius if credentials leak.

## 15. Official references

- [Spring Boot 3.3.13 Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnResource](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).
- [Spring Framework 6.1 Javadoc — Condition](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html).
- [Spring Boot 3.3.13 Javadoc — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).