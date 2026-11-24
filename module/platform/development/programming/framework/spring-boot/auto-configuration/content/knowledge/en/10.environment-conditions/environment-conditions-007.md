# `@ConditionalOnCloudPlatform` and Platform Detection Scope in Spring Boot

**Topic:** Spring Boot Auto Configuration  
**Context:** Environment conditions  
**Goal:** Understand when Spring Boot considers a cloud platform active, what `@ConditionalOnCloudPlatform` checks, its detection scope, how to test it, and limits to keep in mind in real-world deployments.

## 1. What Is This Condition's Job?

`@ConditionalOnCloudPlatform` is a Spring Boot annotation used to **register a configuration or bean only when the specified cloud platform is active** according to the framework's detection mechanism. It lives at:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnCloudPlatform;
import org.springframework.boot.cloud.CloudPlatform;
```

Example illustrating a configuration active only when Spring Boot detects Kubernetes:

```java
@AutoConfiguration
@ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)
public class KubernetesSupportAutoConfiguration {

    @Bean
    KubernetesDeploymentHints kubernetesDeploymentHints() {
        return new KubernetesDeploymentHints();
    }
}
```

This is an API illustration snippet, not a standalone compilable class, since `KubernetesDeploymentHints` is an application-defined type. If the condition does not match, the beans in that configuration are not registered. If the condition matches, they can be registered provided any other conditions also permit it.

The annotation can be used on both:

- **`@Configuration` / `@AutoConfiguration` classes:** the condition determines participation of the entire configuration.
- **`@Bean` methods:** the condition only decides bean registration for a specific method.

Example on a method:

```java
@Bean
@ConditionalOnCloudPlatform(CloudPlatform.CLOUD_FOUNDRY)
CloudFoundryAdapter cloudFoundryAdapter() {
    return new CloudFoundryAdapter();
}
```

This snippet also only illustrates configuration; `CloudFoundryAdapter` is a type the application must implement itself. Both cases use a **`CloudPlatform`** enum as the required value of the annotation.

## 2. How Does Spring Boot Determine the Cloud Platform?

Spring Boot has the `org.springframework.boot.cloud.CloudPlatform` enum with key methods:

```java
CloudPlatform.KUBERNETES.isDetected(environment);
CloudPlatform.KUBERNETES.isEnforced(environment);
CloudPlatform.KUBERNETES.isActive(environment);
CloudPlatform.getActive(environment);
```

Here `environment` is of type `org.springframework.core.env.Environment`:

- **`isDetected`**: detects characteristic signals of the platform in `Environment`, such as environment variables.
- **`isEnforced`**: checks whether that platform is forced via the `spring.main.cloud-platform` key.
- **`isActive`**: decides whether the platform is active according to Spring Boot's detection/enforcement mechanism.
- **`getActive`**: retrieves the active platform per the respective version's API, or `null` if no platform is active.

Conceptual logic:

```text
Application Environment
      |
      |-- Is spring.main.cloud-platform explicitly forced?
      |       |-- Yes: use the forced choice (KUBERNETES, NONE, ...)
      |       `-- No: rely on characteristic platform signals
      |
      `-- Is the corresponding CloudPlatform active?
              |-- Yes: condition matches
              `-- No: condition does not match
```

**This is a configuration/environment detection heuristic, not a connectivity test or cloud authentication.** Spring Boot does not call the Kubernetes API just to verify a Pod exists, nor does it prove access permissions, services, or cloud resources are ready. Forcing a value can make the condition match on a laptop even without a cluster.

## 3. Platform Scope That Spring Boot Understands

In the **Spring Boot 3.3.x** line, the `CloudPlatform` enum has these constants:

| Enum constant | Meaning |
| --- | --- |
| `NONE` | Select no cloud platform; useful when avoiding false detection |
| `CLOUD_FOUNDRY` | Cloud Foundry |
| `HEROKU` | Heroku |
| `SAP` | SAP Cloud platform |
| `NOMAD` | HashiCorp Nomad (available since Spring Boot 3.1) |
| `KUBERNETES` | Kubernetes platform |
| `AZURE_APP_SERVICE` | Azure App Service |

`CloudPlatform.NONE` is a special value expressing the state of not using a specific cloud platform, not an individual cloud provider. The corresponding configuration value is typically set as `spring.main.cloud-platform=NONE`.

**Scope limitation:** Not every cloud provider or infrastructure type has its own enum. In Spring Boot 3.3, `CloudPlatform.KUBERNETES` refers to Kubernetes in general, not identifying whether a cluster is managed by **GKE**, **EKS**, or **AKS**. Running on an EC2 VM, local Docker, or a regular cloud server also does not automatically equate to Kubernetes.

The constant list and detection algorithm are version-dependent APIs. When switching Spring Boot major/minor versions, you must check the Javadoc for the exact running version; do not assume every enum in newer Spring Boot exists in 3.3.

## 4. What Signals Identify Kubernetes?

Spring Boot 3.3's cloud deployment documentation describes Kubernetes auto-detection based on service-related environment variables matching the `"*_SERVICE_HOST"` and `"*_SERVICE_PORT"` patterns.

Examples of signals commonly seen in a Pod:

```text
KUBERNETES_SERVICE_HOST=10.96.0.1
KUBERNETES_SERVICE_PORT=443
```

Points to distinguish:

1. In a Pod with the corresponding signals present, Spring Boot can detect the Kubernetes environment.
2. A customized deployment may omit injecting those service variables; the system **can miss** Kubernetes even when truly running inside a cluster.
3. A local or CI machine configured with similar signals can lead to **false positive detection**.
4. Running an application inside a Docker container is **not enough to conclude** that Kubernetes is active.

Do not use an environment signal as security proof. It does not authenticate users, does not prove Kubernetes API server connectivity, does not replace tokens or RBAC permissions, and does not verify cloud resources exist.

### 4.1. Forcing detection with `spring.main.cloud-platform`

Spring Boot lets you force the detection result via a property:

```yaml
# application.yml
spring:
  main:
    cloud-platform: KUBERNETES
```

An equivalent way when running a packaged JAR:

```bash
java -jar app.jar --spring.main.cloud-platform=KUBERNETES
```

The command is only an operational example; `app.jar` must already exist from your application.

With the value above, conditions requiring `KUBERNETES` can match even outside a cluster. This is useful for unit/integration tests checking bean registration, yet **does not create a Kubernetes API, node, ConfigMap, ServiceAccount, or cloud connection**.

If Spring Boot misdetects a platform in a test environment, you can force no cloud selection:

```properties
spring.main.cloud-platform=NONE
```

You can force Cloud Foundry to test another branch:

```properties
spring.main.cloud-platform=CLOUD_FOUNDRY
```

If this override configuration appears in profile-specific files, environment variables, or JVM/CLI arguments, check the actual configuration precedence sources. When auto-detection is desired, ensure no override is active.

## 5. Standalone Lab with Java 17 and Spring Boot 3.3.5

The example uses `ApplicationContextRunner` to test three decision types: class-level condition, method-level condition, and platform override. No web server, Docker, or real Kubernetes is required.

### 5.1. Project structure

```text
cloud-platform-condition-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── CloudPlatformConditionTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>cloud-platform-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Create `src/test/java/demo/CloudPlatformConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnCloudPlatform;
import org.springframework.boot.cloud.CloudPlatform;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class CloudPlatformConditionTest {

    static final class KubernetesMarker {
    }

    static final class KubernetesProbe {
    }

    static final class CloudFoundryMarker {
    }

    // Class-level condition: every @Bean inside is governed by the condition.
    @AutoConfiguration
    @ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)
    static class KubernetesAutoConfiguration {

        @Bean
        KubernetesMarker kubernetesMarker() {
            return new KubernetesMarker();
        }

        @Bean
        KubernetesProbe kubernetesProbe() {
            return new KubernetesProbe();
        }
    }

    // Method-level condition: only one bean is governed by the condition.
    @AutoConfiguration
    static class CloudFoundryAutoConfiguration {

        @Bean
        @ConditionalOnCloudPlatform(CloudPlatform.CLOUD_FOUNDRY)
        CloudFoundryMarker cloudFoundryMarker() {
            return new CloudFoundryMarker();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            KubernetesAutoConfiguration.class,
                            CloudFoundryAutoConfiguration.class
                    )
            );

    @Test
    void kubernetesOverrideRegistersOnlyKubernetesBeans() {
        runner.withPropertyValues("spring.main.cloud-platform=KUBERNETES")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(KubernetesMarker.class);
                    assertThat(context).hasSingleBean(KubernetesProbe.class);
                    assertThat(context).doesNotHaveBean(CloudFoundryMarker.class);
                    assertThat(CloudPlatform.KUBERNETES.isActive(
                            context.getEnvironment())).isTrue();
                });
    }

    @Test
    void cloudFoundryOverrideRegistersOnlyCloudFoundryBean() {
        runner.withPropertyValues("spring.main.cloud-platform=CLOUD_FOUNDRY")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(KubernetesMarker.class);
                    assertThat(context).doesNotHaveBean(KubernetesProbe.class);
                    assertThat(context).hasSingleBean(CloudFoundryMarker.class);
                });
    }

    @Test
    void noneOverrideDisablesCloudSpecificBeanConditions() {
        runner.withPropertyValues("spring.main.cloud-platform=NONE")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(KubernetesMarker.class);
                    assertThat(context).doesNotHaveBean(KubernetesProbe.class);
                    assertThat(context).doesNotHaveBean(CloudFoundryMarker.class);
                });
    }

    @Test
    void otherCloudDoesNotMatchEitherAnnotation() {
        runner.withPropertyValues("spring.main.cloud-platform=HEROKU")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(KubernetesMarker.class);
                    assertThat(context).doesNotHaveBean(CloudFoundryMarker.class);
                });
    }
}
```

Run:

```bash
mvn test
```

**Expected result:** four tests pass. In a standard Maven Surefire report there will be:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

The test code prints no dedicated stdout. What each test checks:

- When forcing `KUBERNETES`, the Kubernetes auto-configuration class is activated and creates two beans. The Cloud Foundry branch does not match.
- When forcing `CLOUD_FOUNDRY`, only the Cloud Foundry branch creates a bean among the declared branches.
- When forcing `NONE`, the specific cloud conditions do not match.
- When forcing `HEROKU`, no bean is created in the example because no branch is configured for Heroku.

**Note on test reliability:** We deliberately avoid writing an assertion like “on a local machine it must detect no cloud” without controlling the environment. CI may run inside Kubernetes and make that test environment-dependent. Property overrides isolate the Spring Boot behavior under test.

### 5.2. Testing real auto-detection

If you need to test raw detection, create an `Environment` whose property sources and characteristic platform signals are controlled, while **not** setting `spring.main.cloud-platform`. Compare the results of `CloudPlatform.getActive(environment)` and `CloudPlatform.KUBERNETES.isActive(environment)` with and without the matching signals.

When a test must assert real connectivity to Kubernetes/Cloud Foundry, write a separate integration test with proper infrastructure, credentials, service account, and API permissions. `ApplicationContextRunner` in this example only proves bean registration results, not that infrastructure works.

## 6. Distinguishing Cloud Conditions from Other Conditions

| Mechanism | Question it answers |
| --- | --- |
| `@ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)` | Does Spring Boot consider Kubernetes active? |
| `@ConditionalOnProperty(name = "app.feature.enabled")` | Does the configuration property satisfy the condition? |
| `@Profile("k8s")` | Is the `k8s` profile enabled? |
| `@ConditionalOnClass(KubernetesClient.class)` | Is the optional library/class on the classpath? |
| `@ConditionalOnBean(SomeBean.class)` | Has the container registered the dependent bean yet? |
| `@ConditionalOnWebApplication` | Is the application context of the corresponding web type? |

These mechanisms are independent and can be combined:

- `@Profile("k8s")` **does not automatically match** just because it runs on Kubernetes. Profiles are determined by Spring active profiles.
- `@ConditionalOnProperty(name="spring.main.cloud-platform", havingValue="KUBERNETES")` is **not equivalent** to `@ConditionalOnCloudPlatform(KUBERNETES)`: the property condition only checks the declared override value; the cloud condition can also rely on auto-detection even when that property is absent.
- Having a Kubernetes client on the classpath does not mean running on Kubernetes. You can use a client locally to connect to a remote cluster, while `@ConditionalOnCloudPlatform` does not match.
- Having an active cloud platform also does not guarantee other beans are ready. Classpath or bean dependency conditions may still be needed to avoid initialization errors.

If a feature should only turn on when **both on Kubernetes and permitted by operators**, combine the two conditions:

```java
@Bean
@ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)
@ConditionalOnProperty(
        prefix = "app.discovery",
        name = "enabled",
        havingValue = "true"
)
ClusterDiscovery clusterDiscovery() {
    return new ClusterDiscovery();
}
```

This is illustrative code inside an existing configuration; `ClusterDiscovery` is a class that must be defined by the application. Both conditions must match. If the goal is simply a cloud-independent feature flag, prefer `@ConditionalOnProperty` alone.

## 7. Understanding the Boundaries of Platform Detection

### 7.1. Kubernetes detection is not provider detection

`CloudPlatform.KUBERNETES` does not tell whether the cluster runs on EKS, GKE, AKS, or self-managed Kubernetes. To choose provider-specific integrations, you need dedicated provider metadata/configuration and to verify connectivity accordingly.

### 7.2. Running in a container does not automatically trigger a cloud condition

Local Docker, a Kubernetes Pod, a Heroku dyno, and a cloud VM are different environments. A container is merely a packaging/execution mechanism; it does not supply the characteristic signals of all supported platforms. Do not enable cloud-specific beans just because you see a container image or the `HOSTNAME` variable.

### 7.3. `spring.main.cloud-platform` is a forced choice, not an infrastructure guarantee

Configuration can be set deliberately in local/test to reproduce behavior. That does not prove DNS, API endpoints, RBAC, ServiceAccount, or resources are ready. Conversely, `NONE` is not a mechanism to block the application from accessing the cloud; it only changes Spring Boot's detection behavior.

### 7.4. Conditions do not change automatically after startup

Auto-configuration conditions are evaluated when building the application context. Changing environment variables or configuration files after the application has started does not automatically re-register previously excluded beans. When changing platform mode, you must recreate the context or redeploy via the appropriate operational workflow.

### 7.5. Do not use as a security check

Env signals and forced configuration choices are not security attestations. To call cloud APIs, you must still authenticate, enforce authorization, and validate resources. A bean with a matching condition does not guarantee the application's cloud permissions are valid.

## 8. Diagnosing When a Bean Does Not Appear

Follow these steps in order:

1. **Check annotation scope:** Is `@ConditionalOnCloudPlatform` placed on the class or on the method? Are other conditions also applied?
2. **Check `spring.main.cloud-platform`:** Is it forcing `NONE`, `HEROKU`, `CLOUD_FOUNDRY`, or `KUBERNETES`? Is a higher-precedence configuration source overriding it?
3. **Check detection signals:** For Kubernetes, inspect whether the service variables used by your Spring Boot version are provided by the container.
4. **Check version and enum:** Rely only on `CloudPlatform` from the Spring Boot version actually running; do not extrapolate from documentation of other versions.
5. **Read the Condition Evaluation Report:** Run the application with `--debug` and look up the reason from `OnCloudPlatformCondition`. With Actuator and the conditions endpoint properly configured/exposed, you can inspect `/actuator/conditions`.
6. **Reproduce minimally:** Use `ApplicationContextRunner` with `spring.main.cloud-platform=KUBERNETES`, then switch to `NONE`, and compare the registered beans.
7. **Separate runtime issues:** If the bean appears yet calling the Kubernetes API fails, that is a connectivity/credentials/permissions issue, not necessarily a condition evaluation bug.

Example of viewing the condition report of an existing JAR application:

```bash
java -jar app.jar --debug --spring.main.cloud-platform=KUBERNETES
```

The report helps distinguish *condition did not match* from *bean was registered but failed initialization*. Avoid exposing internal diagnostic endpoints to the public Internet unprotected.

## 9. Real-World Design Scenarios

**Scenario A — Configuration dedicated to Kubernetes:** There is a group of beans serving Kubernetes-specific paths or deployment info. Place the annotation on the auto-configuration class; add a classpath condition if the Kubernetes library is optional. Afterward, still test permissions and API connectivity.

**Scenario B — Using the same JAR locally and on Kubernetes:** To test wiring without deploying a cluster, use the `KUBERNETES` property override. When production uses real detection, verify deployment env signals; if you must force a value, set it intentionally in operational configuration.

**Scenario C — Just separating dev and prod:** Use Spring profiles or application properties. `CloudPlatform` does not represent lifecycle stage; production may run on Kubernetes, a VM, or other infrastructure.

**Scenario D — Wanting to distinguish cloud vendors:** Do not rely solely on `KUBERNETES` to conclude AWS/Azure/Google. Create a dedicated configuration/provider detector with a clear contract.

## 10. Self-Assessment Questions

**1.** Is `@ConditionalOnCloudPlatform(KUBERNETES)` guaranteed to match when running on local Docker on a laptop?  
**Answer:** No. Docker does not mean Kubernetes; the outcome depends on actual detection or an override.

**2.** If `spring.main.cloud-platform=KUBERNETES` is forced in a test with no cluster, can it match?  
**Answer:** Yes. The condition checks the active state determined by Spring Boot; it does not attempt to connect to an API server.

**3.** Do GKE/EKS/AKS need three different enums?  
**Answer:** For `CloudPlatform.KUBERNETES`, no; they can all be detected as the Kubernetes platform, without reflecting the vendor provider.

**4.** If the `k8s` profile is enabled, does the cloud condition automatically match?  
**Answer:** No. Profiles and cloud platforms operate independently.

**5.** If CI misdetects the cloud, what configuration can disable detection?  
**Answer:** `spring.main.cloud-platform=NONE`, understanding that this is only an override within Spring Boot.

**6.** When the condition matches, is the Kubernetes client guaranteed to connect successfully?  
**Answer:** No. Connectivity, DNS, API server, credentials, and RBAC belong to the runtime layer.

## 11. Key Takeaway

`@ConditionalOnCloudPlatform` is a tool for selecting **a configuration branch according to the platform Spring Boot detects**, via `CloudPlatform` and `Environment`. It has version-bounded support scope, an override mechanism via `spring.main.cloud-platform`, and **does not certify infrastructure or access permissions**. Proper design tests bean registration separately from cloud integration tests, and uses profiles/properties when the true goal is feature configuration or deployment stage.

### Official Documentation

- [Spring Boot 3.3 API — `@ConditionalOnCloudPlatform`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnCloudPlatform.html)
- [Spring Boot 3.3 API — `CloudPlatform`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/cloud/CloudPlatform.html)
- [Spring Boot 3.3 Reference — Deploying to the Cloud](https://docs.spring.io/spring-boot/3.3/how-to/deployment/cloud.html)
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
