# Identifying Indicators from Bean Names and Organizing Component Paths

## 1. From a Java Bean to a Health Path

When adding a `HealthIndicator` to a Spring Boot application, you do not need to write a separate controller for that check. Actuator collects health beans, registers them under specific names, and uses those names to build the component tree.

For example:

```text
Bean: inventoryHealthIndicator
    -> root ID: inventory
    -> path: /actuator/health/inventory
```

Understanding this conversion accurately helps answer three questions:

1. Why is the name in JSON shorter than the bean name?
2. Why does a child object inside a composite have a multi-segment path?
3. Why does a name exist in Java code yet the URL you guessed still returns `404`?

This lesson uses **Spring Boot 3.3.0 and JDK 21** to anchor the examples. The rules and API types presented belong to the **3.3.x** line, with Actuator's standard registry configuration.

### 1.1. Four Name Layers to Distinguish

| Name layer | Example | Role |
| --- | --- | --- |
| Spring bean name | `inventoryHealthIndicator` | Identifies the bean inside the container |
| Root contributor ID | `inventory` | Lookup key in the health registry |
| Child name in a composite | `primary` | Lookup key under a parent contributor |
| HTTP path | `/actuator/health/checkout/payment/primary` | Path from the endpoint to a node in the tree |

Java class names, method names, aliases, names inside `details` data, and contributor IDs are related, yet they are not always the same string.

A package structure like `example.health.payment` does not automatically create a `/health/payment` path. The health tree is determined by registered contributors and composite relationships, not by the source directory tree.

## 2. Root IDs Are Derived from Bean Names

### 2.1. Where Does the Bean Name Come From?

For a `@Bean` method without an explicit name, the method name is the bean name:

```java
@Bean
HealthIndicator searchHealthIndicator() {
    return () -> Health.up().build();
}
```

The bean name is `searchHealthIndicator`. By health naming conventions, the root ID is `search`.

If an explicit name is specified, that name is used instead of the method name:

```java
@Bean(name = "inventoryHealthIndicator")
HealthIndicator supplyProbe() {
    return () -> Health.up().build();
}
```

The bean has the name `inventoryHealthIndicator`, so the health ID is `inventory`. The method name `supplyProbe` does not create a health component of that name.

The snippets above reside inside a Spring configuration class and require importing `Bean`, `Health`, and `HealthIndicator`. Default and explicit naming rules for `@Bean` are described in [Spring Framework 6.1.8 API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/annotation/Bean.html).

For a class scanned via `@Component`, the default bean name is typically derived from the class name. For example, an `InventoryHealthIndicator` class normally creates an `inventoryHealthIndicator` bean and is then given the health ID `inventory`. If `@Component` specifies an explicit name, that specified bean name must be considered.

### 2.2. Suffix Stripping Rules

In the standard naming mechanism, `HealthContributorNameFactory` converts a bean name into a contributor name. Verified examples in this lesson:

| Input bean name | Contributor ID |
| --- | --- |
| `searchHealthIndicator` | `search` |
| `inventoryHealthIndicator` | `inventory` |
| `checkoutHealthContributor` | `checkout` |
| `inventory` | `inventory` |
| `inventoryHealthIndicatorV2` | `inventoryHealthIndicatorV2` |
| `searchhealthindicator` | `search` |
| `InventoryHealthIndicator` | `Inventory` |

Points to read carefully:

- The `HealthIndicator` or `HealthContributor` suffix is stripped from the bean name when applicable.
- A substring in the middle of a name is not stripped: `inventoryHealthIndicatorV2` does not end with that suffix, so it is kept intact.
- In the tested version, suffix matching is case-insensitive. This **does not mean the entire ID is converted to lowercase**: `InventoryHealthIndicator` still produces `Inventory`.
- The remaining part of the name is what is used for lookup. Do not arbitrarily change `inventory` to `Inventory` in the URL.

The reference documentation describes the `HealthIndicator` suffix-stripping rule; the table above is additionally verified using Spring Boot 3.3.0's naming API in the program in section 8. [HealthIndicator naming conventions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

### 2.3. Aliases Do Not Automatically Create Additional Health IDs

A bean can have a primary name and an alias:

```java
@Bean(name = {"inventoryHealthIndicator", "stockAlias"})
HealthIndicator supplyProbe() {
    return () -> Health.up().build();
}
```

Inside the container, the same bean can be looked up by the name `stockAlias`. However, with standard bean collection and the standard registry in the experiment:

```text
Primary bean: inventoryHealthIndicator
Spring alias: stockAlias
Health ID: inventory
```

`/actuator/health/inventory` exists, while `/actuator/health/stockAlias` does not appear automatically. An alias serves Spring bean lookup; it is not an additional endpoint declaration.

This is especially important to remember when renaming: adding an alias for an old name does not automatically guarantee that the old health URL continues to exist.

### 2.4. Avoid Two Bean Names Collapsing to the Same ID

Two beans named `inventory` and `inventoryHealthIndicator` can both lead to the ID `inventory`. Different bean names do not guarantee different health IDs.

Design unique IDs after the name conversion step rather than relying on suffix differences. When inspecting a real configuration, cross-check the IDs in the registry to ensure every desired check has a distinct, clear name.

`@Primary` or `@Qualifier` serve bean selection during dependency injection; they are not tools that automatically rename health IDs. Do not treat `@Primary` as a way to pick a single indicator to replace the entire contributor set of the endpoint.

## 3. Single Contributors and Composite Contributors

`HealthContributor` is the common type for components providing health. Two forms must be distinguished:

| Type | Role | Has child nodes to traverse in the tree? |
| --- | --- | --- |
| `HealthIndicator` | Executes a check and returns `Health` | No |
| `CompositeHealthContributor` | Contains named contributors | Yes |

A composite is a structure of checks, not a precomputed `Health`. When building a result, Actuator traverses the contributors and produces the corresponding health data. [HealthContributor 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributor.html)

### 3.1. Child Names Come from Map Keys

A composite can be created using `CompositeHealthContributor.fromMap`:

```java
HealthIndicator database = () -> Health.up().build();
HealthIndicator cache = () -> Health.up().build();

CompositeHealthContributor checkout =
        CompositeHealthContributor.fromMap(
                Map.<String, HealthContributor>of(
                        "database", database,
                        "cache", cache));
```

This is an object construction snippet and requires importing `java.util.Map` and the health types. For it to become a root contributor under the standard collection mechanism, it must be returned from a bean or registered through the registry.

If the root bean is named `checkoutHealthContributor`, the tree is:

```text
checkout
├── database
└── cache
```

The keys `database` and `cache` are **child names supplied directly**, not inferred back from Java variable names.

`fromMap` accepts a map from names to `HealthContributor`; values can be indicators or another composite. [CompositeHealthContributor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html)

### 3.2. Root Naming Rules Do Not Automatically Re-Apply to Child Keys

Suppose the map uses the key:

```java
"cacheHealthIndicator"
```

The child name remains `cacheHealthIndicator`. The suffix is not automatically stripped to turn it into `cache`.

Therefore, these two steps differ:

```text
Root bean name checkoutHealthContributor -> checkout

Child key in map cacheHealthIndicator -> cacheHealthIndicator
```

The complete example below intentionally keeps a child key with the suffix to prove the difference. In practical design, you should usually choose a concise child name such as `cache` directly in the map.

### 3.3. Nesting Composites to Create Multiple Levels

The following tree has a composite nested inside a composite:

```text
checkout
├── database
├── cacheHealthIndicator
└── payment
    ├── primary
    └── backup
```

`checkout` and `payment` are composite nodes. `database`, `cacheHealthIndicator`, `primary`, and `backup` are leaves that execute checks.

The leaves in the example are created via helper methods without `@Bean`. Because of this, they are only placed in the tree through the composite's map, rather than simultaneously being collected as root contributors.

If you deliberately declare a leaf as its own bean and also put it inside a composite, it can appear in both places. Decide clearly whether you want a root node, a child node, or both; do not accidentally create two observation paths for the same check.

## 4. Paths Are Traversals Through the Contributor Tree

With the default base path, the health endpoint is at `/actuator/health`. Subsequent segments are names that the registry and composites can look up:

```text
/actuator/health/{root-id}/{child-name}/{grandchild-name}
```

Example using the tree in section 3:

| Path | Node read |
| --- | --- |
| `/actuator/health` | Aggregate result of the system |
| `/actuator/health/checkout` | The checkout branch |
| `/actuator/health/checkout/payment` | The payment branch inside checkout |
| `/actuator/health/checkout/payment/primary` | The primary leaf |
| `/actuator/health/checkout/payment/backup` | The backup leaf |

The handling mechanism looks up each name sequentially on objects holding named contributors. It does not parse Java packages to find path levels. [Tree traversal code in HealthEndpointSupport 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java)

### 4.1. Do Not Add `components` to the URL

The JSON may display:

```json
{
  "status": "UP",
  "details": {
    "target": "inventory-store"
  }
}
```

This is the response of an `inventory` leaf in the example. The `target` field is detail data, not a child node; `/actuator/health/inventory/target` does not become a health path.

Similarly, `components` in a composite node's JSON is a field name representing data structure. The path to payment remains:

```text
/actuator/health/checkout/payment
```

not:

```text
/actuator/health/components/checkout/components/payment
```

To have a real child segment, you must organize it with a named contributor inside a composite.

### 4.2. Parent Nodes and Leaves Can Have Different Statuses

If `payment/primary` is `UP` while `payment/backup` is `DOWN`, the default aggregator can cause `payment` and `checkout` to report `DOWN`, while the direct path to `primary` still reports `UP`.

For that reason, a leaf URL returning success does not mean the entire tree is healthy. Identify whether you are reading a leaf, a branch, or the entire system.

## 5. Runnable HTTP Application

This application does not call a real database or payment service. Fixed results help observe names and paths without being affected by external infrastructure.

### 5.1. File Structure

```text
health-path-demo/
├── pom.xml
└── src/main/
    ├── java/example/healthpaths/HealthPathApplication.java
    └── resources/application.properties
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>health-path-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

`src/main/java/example/healthpaths/HealthPathApplication.java`:

```java
package example.healthpaths;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthPathApplication.class, args);
    }

    @Bean
    public HealthIndicator searchHealthIndicator() {
        return up("search-service");
    }
    
    @Bean(name = {"inventoryHealthIndicator", "stockAlias"})
    public HealthIndicator supplyProbe() {
        return up("inventory-store");
    }
    
    @Bean("checkoutHealthContributor")
    public CompositeHealthContributor checkoutTree() {
        CompositeHealthContributor payment = CompositeHealthContributor.fromMap(
                Map.<String, HealthContributor>of(
                        "primary", up("payment-primary"),
                        "backup", (HealthIndicator) () -> Health.down()
                                .withDetail("target", "payment-backup").build()));
        return CompositeHealthContributor.fromMap(
                Map.<String, HealthContributor>of(
                        "database", up("checkout-database"),
                        "payment", payment,
                        "cacheHealthIndicator", up("checkout-cache")));
    }
    
    private static HealthIndicator up(String target) {
        return () -> Health.up().withDetail("target", target).build();
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=health-path-demo
management.endpoints.web.exposure.include=health
management.health.defaults.enabled=false
management.endpoint.health.probes.enabled=false
management.health.livenessstate.enabled=false
management.health.readinessstate.enabled=false
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.group.dependencies.include=checkout
```

Purpose of the configuration properties:

- Exclude auto-configured indicators and probes from the experiment so only the tree created by the sample code is observed.
- Allow viewing components and details in a local testing environment.
- Create a `dependencies` group whose member is the `checkout` branch.

The beans in the example are not conditioned on `management.health.defaults.enabled`, so they are still created. Do not interpret that switch as a command that deletes all self-declared health beans.

In a real deployment, choose a visibility policy appropriate for caller permissions. The `always` values here aid observation in the experiment, not a requirement to expose health details publicly.

### 5.2. Resulting Tree

```text
HealthContributorRegistry
├── checkout                    bean: checkoutHealthContributor
│   ├── cacheHealthIndicator    UP
│   ├── database                UP
│   └── payment
│       ├── primary             UP
│       └── backup              DOWN
├── inventory                   bean: inventoryHealthIndicator
└── search                      bean: searchHealthIndicator
```

The display order of JSON keys is not a contract of the example; do not use map order to infer check execution order or status priority.

`stockAlias` exists in the container as an alias of the inventory bean, but does not become a separate root contributor.

### 5.3. Packaging and Running

In the directory containing `pom.xml`, with Maven and JDK 21:

```powershell
mvn -q package
java -jar target/health-path-demo-1.0.0.jar
```

Wait for the application to start successfully. Open another terminal and call a leaf:

```powershell
curl.exe -sS http://localhost:8080/actuator/health/inventory
```

JSON body:

```json
{"status":"UP","details":{"target":"inventory-store"}}
```

PowerShell commands use `curl.exe` to avoid the `curl` alias in some versions. With Bash, use the corresponding `curl` program.

Fetch only the HTTP status code of primary:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health/checkout/payment/primary
```

Stdout:

```text
200
```

Check backup:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health/checkout/payment/backup
```

Stdout:

```text
503
```

`NUL` is the destination that discards the body on Windows; on Linux/macOS replace it with `/dev/null`. Do not use `--fail` when the goal is to observe both error responses and their bodies.

### 5.4. Table of Valid and Invalid Paths

With the sample configuration and direct access to the application:

| Suffix after `/actuator/health` | HTTP result | Health status if present |
| --- | --- | --- |
| No suffix | `503` | `DOWN` |
| `/search` | `200` | `UP` |
| `/inventory` | `200` | `UP` |
| `/Inventory` | `404` | No health result at that path |
| `/inventoryHealthIndicator` | `404` | Using bean name instead of ID |
| `/stockAlias` | `404` | Alias does not automatically create a path |
| `/inventory/target` | `404` | `target` is only a key in details |
| `/checkout` | `503` | `DOWN` |
| `/checkout/payment` | `503` | `DOWN` |
| `/checkout/payment/primary` | `200` | `UP` |
| `/checkout/payment/backup` | `503` | `DOWN` |
| `/checkout/cacheHealthIndicator` | `200` | `UP` |
| `/checkout/cache` | `404` | Actual child key includes the suffix |
| `/components/checkout` | `404` | `components` is not a root node |

These status codes are verified using the real HTTP extension of health in the program in section 8. If the application has Spring Security, a proxy, or a different base path, you must account for those layers before comparing URLs.

## 6. Health Groups Create an Additional Scope, Not a New Component Tree

The configuration in the sample application:

```properties
management.endpoint.health.group.dependencies.include=checkout
```

creates the `dependencies` group. A path belonging to the group has the form:

```text
/actuator/health/dependencies/checkout/payment/primary
                 group        root     child   grandchild
```

`dependencies` is the group name. `checkout` remains the root contributor ID; do not omit this segment just because the group selected checkout.

| Path | Result in the example |
| --- | --- |
| `/actuator/health/dependencies` | Group aggregate, `503 DOWN` |
| `/actuator/health/dependencies/checkout/payment/primary` | Primary leaf in the group, `200 UP` |
| `/actuator/health/dependencies/payment/primary` | `404` because the checkout level is missing |

A group is a way of selecting a set of contributors for observation. It does not turn the checkout bean into a child bean of a new Java object.

Spring Boot supports selecting either a composite or a component by full name such as `checkout/payment` in group configuration. [Spring Boot 3.3 Health groups](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups)

### 6.1. Use IDs/Paths in Group Configuration

When writing `include` or `exclude`, use actual contributor names, not class names or long bean names:

```properties
management.endpoint.health.group.dependencies.include=checkout
```

as opposed to guessing:

```properties
management.endpoint.health.group.dependencies.include=checkoutHealthContributor
```

The latter does not exist as a root ID in the example. The group membership validation mechanism may fail at startup when referencing a non-existent contributor.

You should also keep group names distinct from root contributor names. In standard processing, the first segment is evaluated as a group name before being used as a system traversal path; colliding names can make the URL stop meaning what you intended. Do not use colliding names to simulate a parent–child relationship.

### 6.2. Changing Base Path Does Not Change IDs

If configured with:

```properties
management.endpoints.web.base-path=/manage
```

the sample path becomes:

```text
/manage/health/checkout/payment/primary
```

`checkout/payment/primary` remains the same path in the tree. The base path is where endpoints are published; it does not change bean names or contributor IDs.

If there is a management port, context path, or a proxy in front, determine the address the application actually publishes. Do not add those network prefixes into bean names to try to make URLs match.

## 7. Why Can a Real Contributor Still Return 404?

### 7.1. `show-components` Controls Component Paths

In Spring Boot 3.3, if the caller is not permitted to view components under the accessed group's policy, querying a child path may not return a result even though the contributor is still registered.

Try stopping the application and running:

```powershell
java -jar target/health-path-demo-1.0.0.jar --management.endpoint.health.show-components=never
```

The file's `show-details=always` setting remains intact, yet:

```text
/actuator/health             -> 503 DOWN
/actuator/health/inventory   -> 404
```

The aggregate health check still evaluates statuses. A `404` on a child path is not enough to conclude that the inventory bean was disabled.

In the handler code, the flag allowing component visibility is checked before traversing to a non-root node of the accessed scope. [HealthEndpointSupport 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java)

### 7.2. `show-details` Is a Different Policy

Stop the application first, then run:

```powershell
java -jar target/health-path-demo-1.0.0.jar --management.endpoint.health.show-components=always --management.endpoint.health.show-details=never
```

`/actuator/health/inventory` remains reachable and returns `200`, but does not expose the `details` field:

```json
{"status":"UP"}
```

Separate the two questions:

- Is the caller allowed to see and access the component?
- Once allowed to read that result, is the caller allowed to see detailed data?

With `when-authorized`, identity, roles, and the exact group's policy must also be evaluated. This lesson does not assume every caller has permission simply because a bean exists in the container.

### 7.3. Do Not Blame Every 404 on a Naming Error

When encountering `404`, check in a useful order:

1. Are you calling the right host, port, base path, and health endpoint?
2. Is the first segment selecting a health group?
3. What is the actual root ID after bean-name conversion?
4. Does each child segment match the composite key and letter casing?
5. Is the caller permitted to see components in that scope?
6. Does the contributor belong to the group being accessed?

A security layer or proxy can also make the observed result differ from Actuator's direct response. When diagnosing, distinguish the registry, visibility data, and HTTP response.

## 8. Java Program Verifying Names, Aliases, and Paths

The following program builds a small `ApplicationContext`, uses Spring Boot's health registration and group machinery, and calls `HealthEndpointWebExtension` to inspect responses.

It **does not open an HTTP socket**. The `200`, `503`, and `404` lines are `WebEndpointResponse` status codes returned by health's HTTP extension. Thus it directly verifies Actuator rules, while the application in section 5 is used for additional testing over a real network.

Create `experiments/HealthPathExperiment.java` outside `src/main/java` of the sample project, so as not to add another main class to the Spring Boot JAR:

```java
import java.time.Duration;
import java.util.Map;
import java.util.TreeSet;
import org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration;
import org.springframework.boot.actuate.endpoint.ApiVersion;
import org.springframework.boot.actuate.endpoint.SecurityContext;
import org.springframework.boot.actuate.endpoint.web.WebServerNamespace;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorNameFactory;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthEndpointGroups;
import org.springframework.boot.actuate.health.HealthEndpointWebExtension;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.NamedContributor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class HealthPathExperiment {
    @Configuration(proxyBeanMethods = false)
    static class Indicators {
        @Bean
        public HealthIndicator searchHealthIndicator() {
            return up("search-service");
        }
        
        @Bean(name = {"inventoryHealthIndicator", "stockAlias"})
        public HealthIndicator supplyProbe() {
            return up("inventory-store");
        }
        
        @Bean("checkoutHealthContributor")
        public CompositeHealthContributor checkoutTree() {
            CompositeHealthContributor payment = CompositeHealthContributor.fromMap(
                    Map.<String, HealthContributor>of(
                            "primary", up("payment-primary"),
                            "backup", (HealthIndicator) () -> Health.down()
                                    .withDetail("target", "payment-backup").build()));
            return CompositeHealthContributor.fromMap(
                    Map.<String, HealthContributor>of(
                            "database", up("checkout-database"),
                            "payment", payment,
                            "cacheHealthIndicator", up("checkout-cache")));
        }
        
        private static HealthIndicator up(String target) {
            return () -> Health.up().withDetail("target", target).build();
        }
    }

    static AnnotationConfigApplicationContext context(
            String showComponents, String showDetails) {
        var context = new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("experiment", Map.of(
                        "management.endpoint.health.show-components", showComponents,
                        "management.endpoint.health.show-details", showDetails,
                        "management.endpoint.health.group.dependencies.include", "checkout")));
        context.register(Indicators.class, HealthEndpointAutoConfiguration.class);
        context.refresh();
        return context;
    }

    static HealthEndpointWebExtension extension(
            AnnotationConfigApplicationContext context) {
        return new HealthEndpointWebExtension(
                context.getBean(HealthContributorRegistry.class),
                context.getBean(HealthEndpointGroups.class), Duration.ofSeconds(10));
    }

    static void inspect(HealthEndpointWebExtension extension, String... path) {
        var response = extension.health(ApiVersion.V3, WebServerNamespace.SERVER,
                SecurityContext.NONE, false, path);
        String status = response.getBody() == null ? "-"
                : response.getBody().getStatus().getCode();
        String route = "/actuator/health"
                + (path.length == 0 ? "" : "/" + String.join("/", path));
        System.out.println(route + " -> " + response.getStatus() + " " + status);
    }

    public static void main(String[] args) {
        for (String name : java.util.List.of("searchHealthIndicator",
                "inventoryHealthIndicator", "checkoutHealthContributor",
                "inventory", "inventoryHealthIndicatorV2", "searchhealthindicator",
                "InventoryHealthIndicator")) {
            System.out.println("name " + name + " -> "
                    + HealthContributorNameFactory.INSTANCE.apply(name));
        }
        try (var context = context("always", "always")) {
            var registry = context.getBean(HealthContributorRegistry.class);
            var names = new TreeSet<String>();
            for (NamedContributor<HealthContributor> item : registry) {
                names.add(item.getName());
            }
            System.out.println("roots=" + names);
            System.out.println("aliasBean=" + context.containsBean("stockAlias"));
            System.out.println("aliasContributor="
                    + (registry.getContributor("stockAlias") != null));
            var extension = extension(context);
            inspect(extension);
            inspect(extension, "search");
            inspect(extension, "inventory");
            inspect(extension, "Inventory");
            inspect(extension, "inventory", "target");
            inspect(extension, "inventoryHealthIndicator");
            inspect(extension, "stockAlias");
            inspect(extension, "checkout");
            inspect(extension, "checkout", "payment");
            inspect(extension, "checkout", "payment", "primary");
            inspect(extension, "checkout", "payment", "backup");
            inspect(extension, "checkout", "cacheHealthIndicator");
            inspect(extension, "checkout", "cache");
            inspect(extension, "components", "checkout");
            inspect(extension, "dependencies");
            inspect(extension, "dependencies", "checkout", "payment", "primary");
            inspect(extension, "dependencies", "payment", "primary");
        }
        try (var context = context("never", "always")) {
            System.out.println("hidden-components:");
            inspect(extension(context));
            inspect(extension(context), "inventory");
        }
        try (var context = context("always", "never")) {
            System.out.println("hidden-details:");
            inspect(extension(context), "inventory");
        }
    }
}
```

Compile and run in PowerShell from the directory containing `pom.xml`:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$healthPathClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $healthPathClasspath experiments/HealthPathExperiment.java
java -cp "$healthPathClasspath;experiments" HealthPathExperiment
```

On Linux/macOS, use `:` as the classpath separator and the file-reading syntax appropriate for your shell.

Stdout lines produced by the program:

```text
name searchHealthIndicator -> search
name inventoryHealthIndicator -> inventory
name checkoutHealthContributor -> checkout
name inventory -> inventory
name inventoryHealthIndicatorV2 -> inventoryHealthIndicatorV2
name searchhealthindicator -> search
name InventoryHealthIndicator -> Inventory
roots=[checkout, inventory, search]
aliasBean=true
aliasContributor=false
/actuator/health -> 503 DOWN
/actuator/health/search -> 200 UP
/actuator/health/inventory -> 200 UP
/actuator/health/Inventory -> 404 -
/actuator/health/inventory/target -> 404 -
/actuator/health/inventoryHealthIndicator -> 404 -
/actuator/health/stockAlias -> 404 -
/actuator/health/checkout -> 503 DOWN
/actuator/health/checkout/payment -> 503 DOWN
/actuator/health/checkout/payment/primary -> 200 UP
/actuator/health/checkout/payment/backup -> 503 DOWN
/actuator/health/checkout/cacheHealthIndicator -> 200 UP
/actuator/health/checkout/cache -> 404 -
/actuator/health/components/checkout -> 404 -
/actuator/health/dependencies -> 503 DOWN
/actuator/health/dependencies/checkout/payment/primary -> 200 UP
/actuator/health/dependencies/payment/primary -> 404 -
hidden-components:
/actuator/health -> 503 DOWN
/actuator/health/inventory -> 404 -
hidden-details:
/actuator/health/inventory -> 200 UP
```

Library logs, if any, do not belong to these output lines. The `-` after `404` means the test response does not contain a health result object, not a new health status.

The program cross-checks three sides of the same design:

- How bean names convert into IDs.
- Whether an alias exists in Spring yet becomes a separate contributor or not.
- Whether path segments, groups, and visibility policies allow accessing the desired node.

## 9. Naming to Keep the Health Tree Operable

### 9.1. Pin Public Names When Contracts Must Be Preserved

If the URL `/actuator/health/inventory` is already used by monitoring systems, renaming a `@Bean` method without an explicit name can change the ID.

To rename the method while keeping the public name:

```java
@Bean(name = "inventoryHealthIndicator")
HealthIndicator checkWarehouseAvailability() {
    return () -> Health.up().build();
}
```

The ID remains `inventory` because the explicit bean name did not change. Similarly, keep map keys stable when you want to preserve child paths.

When intentionally changing an ID, review:

- URLs that monitoring tools are calling.
- Group `include`/`exclude` configurations.
- Operational runbooks and path checks.
- Other components looking up the registry directly.

Do not rely on bean aliases as an automatic mechanism for maintaining two health URLs.

### 9.2. Choose Names Based on Observation Role

Good names explain what the node is checking, such as `checkout/database` or `checkout/payment/primary`. Avoid putting long implementation class names, values that change per startup, or user data into IDs.

To represent hierarchy, use real composites. Do not put multiple `/` characters in a single bean name expecting Actuator to create levels automatically, and do not use a map inside `details` in place of a composite.

If multiple branches share a child named `primary`, they do not necessarily conflict, because their full paths differ, such as `checkout/payment/primary` and `reporting/database/primary`. What must remain unique is the name within the same parent scope.

### 9.3. Do Not Extend the Tree Unless It Aids Diagnostics

Composites are useful when a domain has multiple related checks and you need to view both the aggregate and individual parts. A single check does not need extra parent layers just to make the URL look structured.

Choose a depth that helps operators find the cause: which branch failed, which leaf failed, and what scope that result affects.

## 10. Self-Check Practice

1. Rename the `supplyProbe` method in the sample project while keeping `@Bean(name=...)`. Predict whether the inventory URL changes, then verify.
2. Remove the explicit name on the inventory bean. Determine the new bean name, new ID, and new URL before restarting.
3. Change the child key `cacheHealthIndicator` to `cache`. Test both old and new paths; explain why this change differs from the bean-name suffix-stripping rule.
4. Add a `secondary` leaf under `payment`, without declaring it as a root bean. Verify that the tree has the new child path but does not automatically get `/actuator/health/secondary`.
5. Keep the inventory contributor in the registry, then hide details and hide components in turn. Compare the differences in JSON and child-path response codes.
6. Write a table for the application's health tree: primary bean name, root ID, child names, full paths, groups using them, and callers permitted to observe them.

When predicting a URL, follow the chain **primary bean name → root ID → each composite key → group scope → visibility policy**. That chain explains why a path exists and why a given caller can or cannot read it.
