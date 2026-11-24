# Choosing `@ConditionalOnSingleCandidate` when a configuration only supports one foundation component

## 1. Problem: having a bean is not enough; you need to know whether there is a single unique candidate

In a Spring application, multiple beans of the same type can exist. For example, an application registers two `PaymentGateway` beans for two providers, two `ObjectMapper` beans for two formats, or multiple `DataSource` beans for different databases.

An auto-configuration may require strictly **one foundation component that can be selected when injecting by type**. If there are no beans, the feature cannot operate. If there are multiple beans and Spring does not know which one to pick, creating the consumer is also unsafe.

Spring Boot provides:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
```

`@ConditionalOnSingleCandidate` ensures a configuration or bean is only registered when Spring **can determine a single candidate** for the specified bean type.

Key point: "a single candidate" does not necessarily mean "strictly one bean definition". The condition can match in two cases:

- There is only **one bean matching** the checked type.
- There are multiple matching beans, but Spring identifies **a single `@Primary` bean** as the default candidate when injecting by type.

Conversely, if there are multiple beans of the same type with no single primary bean, the condition does not match. If there are no matching beans, the condition also does not match.

This condition is useful when a component only supports **one default backend**, one foundation client, one serializer, or one type-selected implementation. It helps avoid registering a consumer in a state where type-based dependency injection cannot resolve a candidate.

## 2. Matching rules of `@ConditionalOnSingleCandidate`

### 2.1. Case table

Suppose the foundation type to check is `FoundationClient`.

| Registered `FoundationClient` beans | Single candidate exists? | Condition | Reason |
| --- | --- | --- | --- |
| No bean | No | **No match** | No foundation component to use |
| One bean, no `@Primary` | Yes | **Match** | Only one candidate |
| Two beans, no `@Primary` | No | **No match** | Cannot select a default candidate |
| Two beans, exactly one `@Primary` bean | Yes | **Match** | The primary bean is the default candidate |
| Multiple beans, multiple `@Primary` causing ambiguity | Not uniquely resolvable | **No match** | No single primary bean to select |

`@ConditionalOnSingleCandidate` inspects **registered bean definitions/candidates** when the condition is evaluated. It does not need to instantiate every object just to count instances. It is a condition evaluated during Spring Boot's configuration processing phase.

### 2.2. "Single candidate" is not "single bean"

For example, suppose an application has:

```java
@Bean
@Primary
FoundationClient mainClient() {
    return new HttpFoundationClient("main");
}

@Bean
FoundationClient backupClient() {
    return new HttpFoundationClient("backup");
}
```

Assuming `HttpFoundationClient` implements `FoundationClient`, the context has **two beans** of the same type, but `mainClient` is marked `@Primary`. When a consumer injects a single `FoundationClient` parameter, Spring can select `mainClient`. Therefore, `@ConditionalOnSingleCandidate(FoundationClient.class)` can match.

`@Primary` does not delete `backupClient`, does not shrink a collection to one element, and does not merge two beans into one. It only designates the preferred candidate for eligible single-value injection points.

If a consumer needs all clients, inject `List<FoundationClient>` or `Map<String, FoundationClient>`. In that case, a single-candidate condition is usually not the right tool, because the business requirement is to **support multiple candidates**.

### 2.3. The condition does not pass the bean in by itself

`@ConditionalOnSingleCandidate` only answers: **"Can a single candidate be determined for this type?"** It does not pass objects into the method by itself, does not create beans, and does not mark any bean as primary.

Actual injection is still performed by Spring:

```java
@Bean
@ConditionalOnSingleCandidate(FoundationClient.class)
FeatureService featureService(FoundationClient foundationClient) {
    return new FeatureService(foundationClient.id());
}
```

When two beans exist and one is `@Primary`, the condition can match and the `foundationClient` parameter is injected with the primary bean. When two non-primary beans exist, the condition does not match, so `featureService()` is not used to register a bean.

If a method uses a specific qualifier, consider the qualifier contract of the injection point as well. Do not rely on `@ConditionalOnSingleCandidate` to replace a name-based or tenant-based bean selection policy. The condition checks whether a candidate can be determined by type; if business logic needs to explicitly pick `mainClient` or `backupClient`, use `@Qualifier` or explicit configuration.

## 3. Distinguishing from related conditions and annotations

### 3.1. `@ConditionalOnBean` — at least one matching bean exists

`@ConditionalOnBean` checks for the presence of a matching bean. It does not assert that only a single candidate exists for injection by type.

```java
@Bean
@ConditionalOnBean(FoundationClient.class)
ClientRegistry clientRegistry() {
    return new ClientRegistry();
}
```

If one or more `FoundationClient` beans exist, the bean-presence condition can match. However, if another bean takes a single `FoundationClient` parameter and the context has two non-primary candidates, that method can still fail when Spring creates the bean.

Choose `@ConditionalOnBean` when the feature only needs **at least one bean to exist**, or when the consumer manages multiple candidates itself. Choose `@ConditionalOnSingleCandidate` when the consumer needs **a single candidate injectable by type**.

### 3.2. `@ConditionalOnMissingBean` — default backs off when a bean already exists

`@ConditionalOnMissingBean` answers a different question: **"Is there already a matching bean to replace the default?"**

```java
@Bean
@ConditionalOnMissingBean(FoundationClient.class)
FoundationClient defaultFoundationClient() {
    return new HttpFoundationClient("default");
}
```

If the application already declares one or more `FoundationClient` beans, the default can back off. This condition is very common in starters so users can replace implementations.

However, when the user declares **two** non-primary `FoundationClient` beans, the default can still back off while a consumer requiring a single candidate is not registered. Thus, "the default backed off" does not mean "every consumer can operate".

### 3.3. `@Primary` — prioritize one bean for single injection

`@Primary` is metadata for candidate selection during dependency injection. It does not check bean creation conditions itself and does not eliminate other beans.

For example:

```java
@Bean
@Primary
FoundationClient primaryClient() {
    return new HttpFoundationClient("primary");
}
```

When multiple `FoundationClient` beans exist, a primary bean allows `@ConditionalOnSingleCandidate` to match. When only one bean exists, `@Primary` is not needed.

### 3.4. `@Qualifier` — select by specific label/semantics

`@Qualifier` lets an injection point select a bean from a group by qualifier:

```java
@Bean
FeatureService featureService(
        @Qualifier("backupClient") FoundationClient client) {
    return new FeatureService(client.id());
}
```

The snippet above is an example of qualified dependency injection, not a replacement for the single-candidate condition. If a feature always uses `backupClient`, it does not need a "single default candidate" by type; it needs a bean with a specific qualifier. Design conditions and dependencies according to that contract.

### 3.5. Summary comparison table

| Mechanism | Question | Two beans of the same type, no primary |
| --- | --- | --- |
| `@ConditionalOnBean` | Does a matching bean exist? | Usually **match** |
| `@ConditionalOnSingleCandidate` | Can a single candidate be determined? | **No match** |
| `@ConditionalOnMissingBean` | Is a matching bean absent so the default should be registered? | **No match** for the default |
| `@Primary` | Which bean is preferred for single injection? | Does not resolve without a single primary |
| `@Qualifier` | Which qualifier does the injection point require? | Can explicitly select the designated bean |

## 4. Placing the condition at class level or per `@Bean`?

### 4.1. Class level: the whole configuration group requires a single candidate

```java
@AutoConfiguration
@ConditionalOnSingleCandidate(FoundationClient.class)
public class FoundationFeatureAutoConfiguration {

    @Bean
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }

    @Bean
    public FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

This is an illustrative snippet; the types `FoundationClient`, `FeatureService`, and `FeatureMetrics` must be defined. If a single candidate cannot be determined, the **entire** `FoundationFeatureAutoConfiguration` is not applied. Neither `FeatureService` nor `FeatureMetrics` is provided by this class.

Use class level when **every bean in the group only makes sense if a single foundation exists**. If `FeatureMetrics` can operate independently, putting the condition at the class level accidentally drops metrics as well.

### 4.2. Method level: only the bean depending on a single candidate is conditional

```java
@AutoConfiguration
public class SharedFeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }

    @Bean
    public FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

In this example, `featureService` only appears when a single candidate exists. `featureMetrics` is still registered both when there is no client and when there are multiple ambiguous clients, unless another condition prevents it.

**Placement rule:** place the condition at the smallest scope covering exactly the beans that share that requirement. Do not put it on the class just to reduce annotation count if the class contains beans with different dependency requirements.

### 4.3. Combining with back-off in a starter

A starter often needs two things:

1. Provide a default foundation if the application does not have a client yet.
2. Only enable the feature if Spring can determine a single client.

These can be split into two auto-configurations:

```java
@AutoConfiguration
public class FoundationClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationClient.class)
    public FoundationClient foundationClient() {
        return new HttpFoundationClient("default");
    }
}
```

```java
@AutoConfiguration(after = FoundationClientAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }
}
```

The provider configuration is processed before the consumer so the default bean definition has a chance to be registered before the single-candidate condition is evaluated. If the application has one custom client, the default backs off and the feature uses that client. If the application has multiple custom clients without a primary, the default backs off and the feature also does not match.

`@AutoConfiguration(after = ...)` controls **auto-configuration processing order**, while `@ConditionalOnSingleCandidate` checks existing candidates. The two mechanisms complement rather than replace each other.

## 5. Runnable example with Spring Boot 3.3.5 and Java 17+

This example builds a simulated starter with `FoundationClient` and `FeatureService`. The application can start in four states:

- **Default:** only one default client exists.
- **Primary:** two custom clients exist, with one marked `@Primary`.
- **Ambiguous:** two custom clients exist, with no primary.
- **No provider:** exclude the auto-configuration creating the default client and declare no custom clients.

We observe the client bean count and whether `FeatureService` is registered.

### 5.1. Directory structure

```text
single-candidate-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── api/
    │   │   │   ├── FoundationClient.java
    │   │   │   └── FeatureService.java
    │   │   ├── app/
    │   │   │   └── DemoApplication.java
    │   │   └── autoconfigure/
    │   │       ├── FoundationClientAutoConfiguration.java
    │   │       └── FeatureAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/app/
        └── SingleCandidateConditionTests.java
```

### 5.2. `pom.xml`

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
    <artifactId>single-candidate-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. `src/main/java/demo/api/FoundationClient.java`

```java
package demo.api;

public interface FoundationClient {
    String id();
}
```

### 5.4. `src/main/java/demo/api/FeatureService.java`

```java
package demo.api;

public record FeatureService(String description) {
}
```

### 5.5. `src/main/java/demo/autoconfigure/FoundationClientAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationClient.class)
    public FoundationClient foundationClient() {
        return () -> "default";
    }
}
```

When no `FoundationClient` is supplied by the application, this default is registered. When the application declares one or more custom clients, the default backs off so an unwanted extra candidate is not created.

### 5.6. `src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationClientAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService("uses:" + client.id());
    }
}
```

The `FeatureService` bean is only created if a single candidate exists. The `FoundationClient client` parameter uses Spring's own candidate selection rules; when two beans exist and one is primary, the primary client is passed in.

### 5.7. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.FoundationClientAutoConfiguration
```

Both classes are registered as auto-configuration candidates. The file intentionally places the consumer before the provider to illustrate that Spring Boot honors `after` metadata rather than treating line order in the file as a dependency contract. Class names must be exact fully qualified class names.

### 5.8. `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@SpringBootApplication
public class DemoApplication {

    @Bean
    @Primary
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "primary")
    public FoundationClient primaryClient() {
        return () -> "primary";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "primary")
    public FoundationClient secondaryClient() {
        return () -> "secondary";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "ambiguous")
    public FoundationClient clientA() {
        return () -> "A";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "ambiguous")
    public FoundationClient clientB() {
        return () -> "B";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            int clientCount =
                    context.getBeansOfType(FoundationClient.class).size();

            FeatureService feature =
                    context.getBeanProvider(FeatureService.class)
                            .getIfAvailable();

            System.out.println("clients=" + clientCount);
            System.out.println("feature=" +
                    (feature == null ? "none" : feature.description()));
        }
    }
}
```

Custom beans are created by application configuration. In `primary` mode, `primaryClient` and `secondaryClient` coexist, but only `primaryClient` has `@Primary`. In `ambiguous` mode, `clientA` and `clientB` have no primary.

### 5.9. Building and running the four scenarios

Requires JDK 17+, Maven, and connectivity to download dependencies on the first build. From the `single-candidate-demo` directory:

```bash
mvn -q -DskipTests package
```

**Scenario A — default client only**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

Output lines printed by the application:

```text
clients=1
feature=uses:default
```

There is only one default `FoundationClient`, so the condition matches and `FeatureService` uses that client.

**Scenario B — two custom clients, one primary**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --demo.clients=primary --spring.main.banner-mode=off --logging.level.root=OFF
```

Output:

```text
clients=2
feature=uses:primary
```

The default backs off because the application already supplied clients. Two beans exist, one of which is primary, so Spring identifies a single candidate; the feature is registered and injects `primaryClient`.

**Scenario C — two custom clients, no primary**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --demo.clients=ambiguous --spring.main.banner-mode=off --logging.level.root=OFF
```

Output:

```text
clients=2
feature=none
```

The default still backs off because clients already exist. However, there is no single primary and there are two candidates, so `@ConditionalOnSingleCandidate` does not match; `FeatureService` is not registered. The application still starts successfully because the feature bean is conditional.

**Scenario D — exclude the default provider, no replacement client**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationClientAutoConfiguration --spring.main.banner-mode=off --logging.level.root=OFF
```

Output:

```text
clients=0
feature=none
```

There is no foundation client and no dependent consumer is created either. This is safe behavior if the feature is optional. If another bean still injects `FoundationClient` as required without a guarding condition, the context can fail at startup.

## 6. Testing with `ApplicationContextRunner`

A starter should test the cases: no client, one client, multiple clients without primary, and multiple clients with primary. `ApplicationContextRunner` helps verify conditions and resulting beans in small contexts without booting the full application.

Create **`src/test/java/demo/app/SingleCandidateConditionTests.java`**:

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import demo.autoconfigure.FeatureAutoConfiguration;
import demo.autoconfigure.FoundationClientAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class SingleCandidateConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FoundationClientAutoConfiguration.class,
                            FeatureAutoConfiguration.class));

    @Test
    void oneDefaultClientIsSingleCandidate() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FoundationClient.class);
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context.getBean(FeatureService.class).description())
                    .isEqualTo("uses:default");
        });
    }

    @Test
    void multipleClientsWithPrimaryHaveSingleCandidate() {
        runner.withUserConfiguration(PrimaryClients.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(FoundationClient.class))
                            .hasSize(2);
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class).description())
                            .isEqualTo("uses:primary");
                });
    }

    @Test
    void multipleClientsWithoutPrimaryHaveNoSingleCandidate() {
        runner.withUserConfiguration(AmbiguousClients.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(FoundationClient.class))
                            .hasSize(2);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                });
    }

    @Test
    void noClientMeansFeatureIsNotRegistered() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FeatureAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FoundationClient.class);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryClients {

        @Bean
        @Primary
        FoundationClient primaryClient() {
            return () -> "primary";
        }

        @Bean
        FoundationClient secondaryClient() {
            return () -> "secondary";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousClients {

        @Bean
        FoundationClient clientA() {
            return () -> "A";
        }

        @Bean
        FoundationClient clientB() {
            return () -> "B";
        }
    }
}
```

Run all tests:

```bash
mvn -q test
```

Four tests protect the key contracts:

- One unique bean: condition matches.
- Two beans with one primary: condition matches, injects primary.
- Two beans without primary: condition does not match, context still starts.
- No bean: condition does not match, feature does not appear.

These tests directly check **condition logic in the context**. The JAR runs in section 5.9 additionally test the real startup path with `spring.autoconfigure.exclude` and application custom beans.

## 7. Usage in real-world auto-configuration

### 7.1. When to choose `@ConditionalOnSingleCandidate`

Consider it when a feature:

- Only supports one default `DataSource` and does not know how to route across multiple data sources.
- Creates an adapter needing a single selected `CacheManager`.
- Provides a service depending on one default `ObjectMapper`.
- Needs one shared client and allows the application to mark the preferred client with `@Primary`.
- Only supports one backend at a time; multiple non-primary backends represent an ambiguous configuration.

### 7.2. When not to use it

Do not use this condition if:

- The consumer is designed to work with **multiple backends** and can accept `List<T>`/`Map<String,T>`.
- The feature always uses a specific bean by `@Qualifier` or by property.
- You only need to know at least one bean exists; `@ConditionalOnBean` is more suitable.
- You are creating a default and want to back off when the application already declares a bean; `@ConditionalOnMissingBean` is the right target.
- Multiple candidates are a valid state without a primary because the design uses per-tenant/per-request routing. In that case you need an explicit routing mechanism; do not force a fake primary just to make the condition match.

### 7.3. Distinguishing class-level and method-level conditions in a starter

A configuration can create two beans:

- `FeatureService` needs a single `FoundationClient`.
- `FeatureHealthIndicator` only needs to know the system has at least one `FoundationClient` to display overall status.

If you put `@ConditionalOnSingleCandidate` at the class level, `FeatureHealthIndicator` is also dropped when two non-primary clients exist. That can be wrong if the health indicator can inspect both.

A better design:

```java
@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }

    @Bean
    @ConditionalOnBean(FoundationClient.class)
    public FeatureHealthIndicator featureHealthIndicator(
            ObjectProvider<FoundationClient> clients) {
        return new FeatureHealthIndicator(clients.stream().count());
    }
}
```

This is a design example, assuming `FeatureService` and `FeatureHealthIndicator` types exist. The first bean requires a single candidate; the second can handle a set of clients. Conditions and injection styles must stay consistent with each component's requirements.

## 8. Common mistakes and diagnostics

1. **Confusing "single candidate" with "single bean".** Two beans with one marked primary can still match. Check bean count and primary metadata.
2. **Assuming `@Primary` eliminates secondary beans.** No. Secondary beans still exist; collection injection can still receive both. `@Primary` only selects the preferred candidate at eligible single-value injection points.
3. **Using `@ConditionalOnBean` and then injecting a single parameter when multiple candidates exist.** The condition can match even though dependency injection later becomes ambiguous. If the consumer requires one candidate, use `@ConditionalOnSingleCandidate`.
4. **Using `@ConditionalOnSingleCandidate` to create a default.** This is not a back-off condition. Default beans normally use `@ConditionalOnMissingBean`; the consumer is where a single candidate should be checked.
5. **Placing the condition too broadly at the class level.** One bean needing a single candidate can make other independent beans disappear. Move the condition down to the exact method.
6. **Assuming qualifiers automatically make the condition match.** Qualifiers select a bean at a specific injection point. The single-candidate condition checks whether a candidate can be determined by type and primary metadata; do not use it instead of a name/tenant selection policy.
7. **Forgetting auto-configuration processing order.** If the provider is another auto-configuration, use `@AutoConfiguration(after = ProviderAutoConfiguration.class)` when the consumer's condition must see the provider's bean definition. `after` does not create beans if the provider is excluded.
8. **Expecting the condition to run after beans are instantiated.** Conditions evaluate bean metadata during configuration processing, not an object count checked on each request.
9. **Testing only the default application.** A test with one bean will not catch failures when two beans exist. Test zero, one, multiple-with-primary, and multiple-without-primary.
10. **Adding `@Primary` to hide undesigned ambiguity.** Only mark a bean primary if it is truly the business default candidate. If the application needs explicit routing across multiple backends, build a router/selector instead of forcing one bean to win.

When a condition does not match as expected, enable `--debug` to inspect the Condition Evaluation Report. Check whether the auto-configuration class was imported, whether the bean definition was registered before the condition ran, whether the bean type matches, and whether a single primary exists. If the application started yet the feature is absent, that may be an **intentional negative match**, not a bean creation error.

## 9. Quick rules of thumb

- **No bean:** `@ConditionalOnSingleCandidate` does not match.
- **One bean:** matches, no `@Primary` needed.
- **Multiple beans, one primary:** matches; single injection can select the primary.
- **Multiple beans, no unique primary:** does not match.
- **Only need at least one bean:** consider `@ConditionalOnBean`.
- **Provide a default if none exists:** use `@ConditionalOnMissingBean`.
- **Select a specific bean by name/label:** use `@Qualifier` and matching configuration.
- **Condition applies to only one bean:** place it on the `@Bean` method; only place on the class when every bean in the class needs the same condition.

Final self-check question: **"Does this feature need any bean, strictly one candidate injectable by type, or a specific bean by qualifier?"** Answering that question correctly helps choose the right condition and prevents losing functionality when the application adds more backends.

## Official documentation

- [Spring Boot 3.3 — `@ConditionalOnSingleCandidate` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html): matching rules when a single candidate can be determined.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, auto-configuration ordering, `AutoConfiguration.imports`, and testing.
- [Spring Boot 3.3 — `@ConditionalOnBean` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): checking bean existence.
- [Spring Boot 3.3 — `@ConditionalOnMissingBean` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): back-off mechanism for default beans.
- [Spring Framework 6.1 — `@Primary` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Primary.html): prioritizing a bean when multiple candidates exist for a single injection point.
- [Spring Framework — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): collection injection, qualifiers, and bean selection rules.
