# Cross-Checking Beans and Condition Evaluation Report in a Web Application Without Creating Dummy Business APIs

## 1. Goal: Observing Built-In Spring MVC Infrastructure

When learning Spring Boot auto-configuration, we often want to know:

- Which web beans did Spring Boot create?
- Which beans come from Servlet infrastructure, and which come from Spring MVC?
- When changing one property, which beans appear or disappear?
- Which condition in the report explains that change?
- Do other foundational beans stay intact?

You do not need to write a `@RestController` just to have an endpoint for observation. Spring Boot itself already provides a real system of beans to inspect: `DispatcherServlet`, `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, `HttpMessageConverters`, filters, and the embedded web server.

This lesson uses an application **without declaring any business controller**. The application simply starts Spring MVC, prints the infrastructure bean list, and exposes Actuator `/actuator/conditions` to read the Condition Evaluation Report. We change a single built-in Spring MVC property to compare two runs.

Key point: `/actuator/conditions` is an operational endpoint provided by Actuator. It is not a custom-built business API for the example.

## 2. Distinguishing the Bean Registry from the Condition Evaluation Report

These two observation sources answer two different questions:

| Source | Shows | Does not prove by itself |
| --- | --- | --- |
| Bean registry / `ApplicationContext` | Which beans are actually present, bean names, counts by type | Why conditions were evaluated that way |
| Condition Evaluation Report | Which auto-configuration/`@Bean` matched or did not match, related conditions and messages | Whether the bean is actually used properly in business flows |
| Test / assertion | Whether the outcome satisfies the expected contract | All runtime behavior across every environment |

For example, the report may show `WebMvcAutoConfiguration#hiddenHttpMethodFilter` did not match because the property was not enabled. The bean registry confirms there is no `HiddenHttpMethodFilter`. When the property is enabled, the report switches to a positive match and the bean appears.

We need to **cross-check both**. Looking only at the report can miss custom beans created by the application; looking only at the bean registry misses why defaults were created or backed off.

## 3. Real Web Beans to Observe

### 3.1. Servlet Container and DispatcherServlet

`ServletWebServerFactory` represents the factory creating the embedded server (e.g., Tomcat). `DispatcherServlet` is Spring MVC's Front Controller: it receives requests from the Servlet container and coordinates with MVC components to process them.

A standard application using `spring-boot-starter-web` will have the corresponding beans when started in Servlet web mode.

### 3.2. Handler Mapping and Handler Adapter

- `RequestMappingHandlerMapping` finds mappings for controller methods declared with annotations such as `@RequestMapping`, `@GetMapping`, `@PostMapping`.
- `RequestMappingHandlerAdapter` executes the mapped handler methods, handling argument resolution, return values, and related mechanisms.

These two beans are framework infrastructure. They can still exist even when the application **has not declared any business controller**.

### 3.3. HTTP Message Converters

`HttpMessageConverters` is an abstraction provided by Spring Boot to manage the `HttpMessageConverter` instances used for reading request bodies and writing response bodies. The actual converter list depends on the classpath and configuration.

For example, if Jackson is present on the classpath, the corresponding JSON converter is normally configured. Do not conclude a converter always exists just because starter-web is present; inspect the actual types and conditions.

### 3.4. Spring MVC Filters

This example compares two real filters:

- `FormContentFilter`: supports reading form bodies for HTTP methods such as PUT/PATCH/DELETE. In Boot 3.3 configuration, auto-configuration enables this filter by default unless a replacement bean exists.
- `HiddenHttpMethodFilter`: allows HTML forms to use a `_method` field to represent methods such as PUT/DELETE over a POST request. This bean is auto-configured only when `spring.mvc.hiddenmethod.filter.enabled` is enabled; the default is false.

These two filters are a good example to distinguish **foundational beans that remain unchanged** from **an optional bean that changes with a property**.

## 4. Real Conditions in Spring Boot 3.3

In `WebMvcAutoConfiguration`, the `hiddenHttpMethodFilter()` method has two conditions:

```java
@Bean
@ConditionalOnMissingBean(HiddenHttpMethodFilter.class)
@ConditionalOnProperty(
        prefix = "spring.mvc.hiddenmethod.filter",
        name = "enabled")
public OrderedHiddenHttpMethodFilter hiddenHttpMethodFilter() {
    return new OrderedHiddenHttpMethodFilter();
}
```

This is a structural excerpt from Spring Boot 3.3 auto-configuration; you do not need to copy this method into your application.

The two conditions are combined with AND logic:

1. `@ConditionalOnMissingBean(HiddenHttpMethodFilter.class)`: no `HiddenHttpMethodFilter` bean provided by the user or another configuration exists yet.
2. `@ConditionalOnProperty(prefix = "spring.mvc.hiddenmethod.filter", name = "enabled")`: the property `spring.mvc.hiddenmethod.filter.enabled` has a matching value. With an annotation that does not specify `havingValue`, a value that exists and is not the string `false` matches.

Therefore:

| Property | Custom bean of same type | Result |
| --- | --- | --- |
| Undeclared / false | No | Default filter is not created |
| true | No | Default `OrderedHiddenHttpMethodFilter` is created |
| true | Yes | Default backs off in favor of custom bean |
| false | Yes | Custom bean still exists; property only blocks default auto-config |

`OrderedHiddenHttpMethodFilter` is an implementation of `HiddenHttpMethodFilter`. Therefore, when checking for the bean, you can use the parent type `HiddenHttpMethodFilter.class` to see both the default implementation and custom beans.

In the Condition Evaluation Report, the source is typically identified as `WebMvcAutoConfiguration#hiddenHttpMethodFilter`. When the property is false, the source appears under `negativeMatches` with `OnPropertyCondition` unmatched; `OnBeanCondition` may still match because there is no filter bean yet. When the property is true and there is no custom bean, the source moves to `positiveMatches` with both conditions matching.

## 5. Spring Boot 3.3.5 / Java 17+ Example Application Without Business Controllers

We create a real application with Spring MVC and Actuator. The program prints bean names from the context after startup. No `@RestController`, business DTOs, business services, or dummy endpoints are created.

### 5.1. Directory Structure

```text
web-infrastructure-observer/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   └── WebInfrastructureApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/demo/
            ├── WebInfrastructureTests.java
            └── HiddenMethodFilterEnabledTests.java
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
    <artifactId>web-infrastructure-observer</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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

`spring-boot-starter-web` puts Spring MVC and the embedded Servlet container onto the runtime classpath. `spring-boot-starter-actuator` provides the condition report endpoint. No dependencies for business controllers or APIs are needed.

### 5.3. `src/main/resources/application.properties`

```properties
server.port=8080
management.endpoints.web.exposure.include=health,conditions
```

We expose only `health` and `conditions` for observation. Actuator endpoints still require appropriate access restrictions when deploying the application to shared environments or production.

### 5.4. `src/main/java/demo/WebInfrastructureApplication.java`

```java
package demo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.web.filter.FormContentFilter;
import org.springframework.web.filter.HiddenHttpMethodFilter;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@SpringBootApplication
public class WebInfrastructureApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebInfrastructureApplication.class, args);
    }

    @Bean
    ApplicationRunner printWebInfrastructure(ApplicationContext context) {
        return args -> {
            printBeanNames(context, ServletWebServerFactory.class);
            printBeanNames(context, DispatcherServlet.class);
            printBeanNames(context, RequestMappingHandlerMapping.class);
            printBeanNames(context, RequestMappingHandlerAdapter.class);
            printBeanNames(context, HttpMessageConverters.class);
            printBeanNames(context, FormContentFilter.class);
            printBeanNames(context, HiddenHttpMethodFilter.class);
        };
    }

    private static void printBeanNames(
            ApplicationContext context, Class<?> beanType) {

        String[] names = context.getBeanNamesForType(beanType);

        System.out.printf("%s=%s%n",
                beanType.getSimpleName(),
                names.length == 0 ? "[]" : Arrays.toString(names));
    }
}
```

`ApplicationRunner` simply reads bean names from `ApplicationContext` after the context starts. The queried types are all Spring Boot/Spring MVC infrastructure components:

- `ServletWebServerFactory`: factory for the embedded server.
- `DispatcherServlet`: front controller.
- `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter`: mapping and execution of handler methods.
- `HttpMessageConverters`: manages HTTP converters.
- `FormContentFilter` and `HiddenHttpMethodFilter`: Spring MVC filters.

There are no business controllers. Having handler mapping/adapter beans does not mean the application has defined a business endpoint.

### 5.5. Testing Default Infrastructure Beans: `WebInfrastructureTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.web.filter.FormContentFilter;
import org.springframework.web.filter.HiddenHttpMethodFilter;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebInfrastructureTests {

    @Autowired
    ApplicationContext context;

    @Test
    void servletAndMvcInfrastructureIsPresentWithoutBusinessController() {
        assertThat(context.getBeansOfType(DispatcherServlet.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(RequestMappingHandlerMapping.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(RequestMappingHandlerAdapter.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(HttpMessageConverters.class))
                .isNotEmpty();

        assertThat(context.getBeansOfType(FormContentFilter.class))
                .isNotEmpty();
    }

    @Test
    void hiddenMethodFilterIsAbsentByDefault() {
        assertThat(context.getBeansOfType(HiddenHttpMethodFilter.class))
                .isEmpty();
    }
}
```

### 5.6. Test When Property Is Enabled: `HiddenMethodFilterEnabledTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.web.filter.HiddenHttpMethodFilter;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.mvc.hiddenmethod.filter.enabled=true"
)
class HiddenMethodFilterEnabledTests {

    @Autowired
    ApplicationContext context;

    @Test
    void hiddenMethodFilterIsCreatedWhenPropertyIsEnabled() {
        assertThat(context.getBeansOfType(HiddenHttpMethodFilter.class))
                .hasSize(1);
    }
}
```

The tests start a real Servlet web context on a random port. They do not need to call a business API: the goal is to verify that framework beans are present and the optional bean appears accurately when the property is enabled.

## 6. Running Twice with the Same Artifact

Requires JDK 17+ and Maven. From the `web-infrastructure-observer` directory:

```bash
mvn -q test
mvn -q -DskipTests package
```

### Run A — HiddenHttpMethodFilter Disabled

Start:

```bash
java -jar target/web-infrastructure-observer-0.0.1-SNAPSHOT.jar --spring.mvc.hiddenmethod.filter.enabled=false
```

ApplicationRunner prints the bean list. With Spring Boot 3.3.5 and the dependencies above, the core beans are expected to look like:

```text
ServletWebServerFactory=[tomcatServletWebServerFactory]
DispatcherServlet=[dispatcherServlet]
RequestMappingHandlerMapping=[requestMappingHandlerMapping]
RequestMappingHandlerAdapter=[requestMappingHandlerAdapter]
HttpMessageConverters=[messageConverters]
FormContentFilter=[formContentFilter]
HiddenHttpMethodFilter=[]
```

Bean names are the names registered by framework configuration; if the application adds configurations or swaps the embedded server, names/counts of some beans may differ. Match by type first, then compare names.

Save the Condition Evaluation Report in another PowerShell terminal:

```powershell
$off = Invoke-RestMethod 'http://localhost:8080/actuator/conditions'
$off | ConvertTo-Json -Depth 100 |
    Set-Content -Encoding utf8 .\conditions-off.json
```

### Run B — HiddenHttpMethodFilter Enabled

Stop process A with Ctrl+C. Start the same JAR with exactly one property changed:

```bash
java -jar target/web-infrastructure-observer-0.0.1-SNAPSHOT.jar --spring.mvc.hiddenmethod.filter.enabled=true
```

Key difference in output:

```text
FormContentFilter=[formContentFilter]
HiddenHttpMethodFilter=[hiddenHttpMethodFilter]
```

Core infrastructure beans such as `DispatcherServlet`, `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, and `HttpMessageConverters` are preserved. The `HiddenHttpMethodFilter` bean appears because the property was enabled.

Save the second report:

```powershell
$on = Invoke-RestMethod 'http://localhost:8080/actuator/conditions'
$on | ConvertTo-Json -Depth 100 |
    Set-Content -Encoding utf8 .\conditions-on.json
```

### 6.1. What Changed in the Report?

Find the source:

```text
WebMvcAutoConfiguration#hiddenHttpMethodFilter
```

When the property is false:

- The source typically appears under `negativeMatches`.
- `OnPropertyCondition` does not match because the property is not enabled.
- `OnBeanCondition` can still match because there is no custom `HiddenHttpMethodFilter` bean yet.
- The `hiddenHttpMethodFilter()` method does not register the default bean.

When the property is true:

- The source moves to `positiveMatches`.
- `OnPropertyCondition` matches.
- `OnBeanCondition` still matches if there is no custom bean.
- The default `hiddenHttpMethodFilter` bean is registered.

Other sources of `WebMvcAutoConfiguration` may still appear in positive/negative matches depending on dependencies, properties, and classpath. Do not expect the entire report to be identical; focus on comparing the exact relevant source.

## 7. Filtering and Comparing Reports with PowerShell

The condition report is JSON with dynamic keys by class or bean method name. We can extract just the target source for comparison instead of diffing the entire file.

Create the following function in PowerShell:

```powershell
function Get-ConditionRows {
    param(
        [string]$Path,
        [string]$Source
    )

    $report = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $context = $report.contexts.application
    $rows = @()

    $positive = $context.positiveMatches.PSObject.Properties[$Source]
    if ($null -ne $positive) {
        foreach ($item in $positive.Value) {
            $rows += [pscustomobject]@{
                State = "positive"
                Condition = $item.condition
                Message = $item.message
            }
        }
    }

    $negative = $context.negativeMatches.PSObject.Properties[$Source]
    if ($null -ne $negative) {
        foreach ($item in $negative.Value.notMatched) {
            $rows += [pscustomobject]@{
                State = "notMatched"
                Condition = $item.condition
                Message = $item.message
            }
        }

        foreach ($item in $negative.Value.matched) {
            $rows += [pscustomobject]@{
                State = "matched"
                Condition = $item.condition
                Message = $item.message
            }
        }
    }

    return $rows
}

$source = 'WebMvcAutoConfiguration#hiddenHttpMethodFilter'

$before = Get-ConditionRows -Path '.\conditions-off.json' -Source $source
$after = Get-ConditionRows -Path '.\conditions-on.json' -Source $source

'--- OFF ---'
$before | Format-Table -Wrap

'--- ON ---'
$after | Format-Table -Wrap

'--- DIFF ---'
Compare-Object $before $after -Property State, Condition, Message
```

`Compare-Object` displays entries that exist on only one side or have a different state/message. This is a diff of **a selected source**, not an overall diff of every auto-configuration.

If the source does not appear on either side, check:

- Was the auto-configuration loaded?
- Is the application running a Servlet web context?
- Is it using Spring MVC or WebFlux?
- Is the Boot version right?
- Does the source name in JSON match the class/method being observed?

Do not hard-code entire report messages into tests because messages and source sets can change between Boot versions.

## 8. Reading the Report and Bean Inventory in the Right Order

An effective investigation workflow:

1. **Confirm the context type:** is this a Servlet web application? `WebMvcAutoConfiguration` applies only when web/classpath conditions match and no replacement `WebMvcConfigurationSupport` exists.
2. **Check class-level conditions:** did `WebMvcAutoConfiguration` match? If the class was excluded, do not look up inner bean method conditions as though the method were still evaluated independently.
3. **Locate the method source:** e.g., `WebMvcAutoConfiguration#hiddenHttpMethodFilter`.
4. **Read each condition:** `OnPropertyCondition`, `OnBeanCondition`, etc. Which condition did not match? Which conditions still matched?
5. **Cross-check beans by type:** call `getBeanNamesForType` or `getBeansOfType` to confirm the bean is actually present.
6. **Cross-check bean names:** names help find the exact factory method or configuration creating the bean, while type tells you the contract the bean provides.
7. **Check consumers:** if an infrastructure bean disappears, is there any filter/handler/consumer that needs it? Can the application start and does the related feature still work?
8. **Compare against baseline:** change only one property, dependency, or bean at a time. Keep the same Boot version, JDK, profile, and classpath to pinpoint the exact cause.

### Cross-Check Table for This Example

| Observation | Property false | Property true | Interpretation |
| --- | --- | --- | --- |
| `DispatcherServlet` | Present | Present | Servlet infrastructure unchanged |
| `RequestMappingHandlerMapping` | Present | Present | MVC mapping infrastructure unchanged |
| `RequestMappingHandlerAdapter` | Present | Present | MVC adapter unchanged |
| `HttpMessageConverters` | Present | Present | HTTP converter registry unchanged |
| `FormContentFilter` | Present (default) | Present | Other filter not governed by this property |
| `HiddenHttpMethodFilter` | Absent | Present | Optional bean enabled by property |
| Condition source | Negative match | Positive match | `OnPropertyCondition` changed state |

This table describes the sample scenario with default dependencies. If the application supplies its own `HiddenHttpMethodFilter` bean, the custom bean can still exist when the property is false, while the auto-configured default is still not created.

## 9. Edge Cases to Verify

### 9.1. Application Supplies the Filter Itself

If the application has:

```java
@Bean
HiddenHttpMethodFilter customHiddenMethodFilter() {
    return new HiddenHttpMethodFilter();
}
```

then `@ConditionalOnMissingBean` causes Boot's default to back off, even when the property is true. In that case, the report may show `OnPropertyCondition` matching while `OnBeanCondition` does not match. The bean registry will contain the custom bean named `customHiddenMethodFilter`.

This is an important example: **one matching property condition does not mean the default bean is guaranteed to be registered**. All conditions on the method must match.

### 9.2. User Replaces the Entire MVC Configuration

`WebMvcAutoConfiguration` has a condition checking for missing `WebMvcConfigurationSupport`. When an application uses `@EnableWebMvc` or provides an equivalent foundational MVC configuration itself, default auto-configuration may back off.

This has a broader scope than a filter property: many default MVC beans may change. Do not add `@EnableWebMvc` just to fix one formatter, converter, or interceptor if you want to keep all of Boot's MVC auto-configuration; normally implement `WebMvcConfigurer` without enabling `@EnableWebMvc`.

### 9.3. Classes on Classpath Without a Servlet Context

`spring-boot-starter-web` may be present on the runtime classpath while the application is started with `spring.main.web-application-type=none`. In that case, Servlet web conditions do not match; MVC-specific beans are not registered merely because the classes are present.

This is why `OnClassCondition` and `OnWebApplicationCondition` must be distinguished in the report.

### 9.4. Confusing Mapping Beans with Business Endpoints

`RequestMappingHandlerMapping` is an infrastructure bean. It can exist without any application-written controller. In addition, Actuator and error handling can register their own handler mappings. Therefore, counting a mapping bean does not mean the application has a corresponding business API.

If you need to know the actual registered endpoints, inspect `/actuator/mappings` when the endpoint is exposed and appropriately secured. Do not infer a URL list from the presence of a `RequestMappingHandlerMapping` bean.

### 9.5. Confusing Bean Type with Bean Name

If the application creates a custom implementation or renames a bean, conditions by type and by name may yield different results. Use:

- `getBeanNamesForType(HiddenHttpMethodFilter.class)` to find every bean matching the contract.
- `getBeansOfType(HiddenHttpMethodFilter.class)` to inspect the corresponding instances.
- `/actuator/beans` if exposed and you need to inspect the full registry in an authorized environment.

Do not merely search for the string `hiddenHttpMethodFilter` in logs and conclude no other bean of that type exists.

## 10. When to Use --debug, Actuator, or Tests?

| Tool | Use when | Pros | Limitations |
| --- | --- | --- | --- |
| `--debug` | Local, CI, or apps without a management HTTP endpoint | Prints Condition Evaluation Report at startup | Long log; requires filtering the target source |
| `/actuator/conditions` | Running app with safely exposed endpoint | Structured JSON, easy to save and diff | Requires enabling Actuator/exposure and securing access |
| `ApplicationContext` | Need actual bean types/names | Confirms final result in the registry | Does not directly explain which condition led to the result |
| `@SpringBootTest` | Need to test a web context close to the real app | Verifies infrastructure beans and startup | Context initialization takes more time |
| `ApplicationContextRunner` / `WebApplicationContextRunner` | Need to isolate one auto-configuration or condition | Fast tests for each input branch | Must choose the right context type and load the right auto-configurations |

For this problem, combining **bean inventory in ApplicationRunner**, **Actuator conditions snapshot**, and **SpringBootTest** is enough to compare properties without building dummy business endpoints.

## 11. Common Mistakes

1. **Creating a controller just to have a test URL.** Unnecessary when the goal is observing auto-configuration. A bean runner and Actuator endpoint are enough.
2. **Looking only at positive matches.** An excluded bean usually has its reason in negative matches, including both unmatched conditions and other conditions that still matched.
3. **Reading the report without checking the bean registry.** The report explains the decision; the bean registry confirms the actual result.
4. **Checking only the bean name.** An application may supply a bean of the same type with a different name. Check by type first, then inspect names.
5. **Enabling the property while forgetting custom beans.** `@ConditionalOnMissingBean` can still make the default back off.
6. **Comparing two runs with different dependencies or profiles.** When multiple factors change, the diff no longer points to a single cause.
7. **Assuming every MVC bean requires a controller.** DispatcherServlet, mappings, adapters, and converters are infrastructure; they can exist before the application registers any business controller.
8. **Using `@EnableWebMvc` to fix a small component.** This can make `WebMvcAutoConfiguration` back off and change many foundational beans.
9. **Exposing Actuator conditions publicly.** The report reveals auto-configuration names, beans, and environment details; restrict access.
10. **Treating report messages as a fixed contract.** Messages and source lists can change between Spring Boot versions; compare by source/condition and verify the version.

## 12. Practice Checklist

- [ ] Application uses the right Servlet web context and pinned Spring Boot version.
- [ ] No custom-created business controllers/APIs exist in the infrastructure observation example.
- [ ] Confirmed `DispatcherServlet`, handler mapping, handler adapter, and message converters.
- [ ] Recorded bean names by type, not relying only on guessed names.
- [ ] Saved the baseline Condition Evaluation Report.
- [ ] Changed only one property in the second run.
- [ ] Cross-checked the `WebMvcAutoConfiguration#hiddenHttpMethodFilter` source.
- [ ] Checked `OnPropertyCondition` and `OnBeanCondition` separately.
- [ ] Confirmed `HiddenHttpMethodFilter` bean presence/absence matched expectations.
- [ ] Verified other foundational MVC beans remained unchanged.
- [ ] Ran tests with a web context and verified both property branches.
- [ ] Restricted access to Actuator endpoints.

## Official Documentation

- [Spring Boot 3.3 — Servlet Web Applications / Spring MVC](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Spring MVC infrastructure and property configuration.
- [Spring Boot 3.3 — `WebMvcAutoConfiguration` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html): conditions of Web MVC auto-configuration and the `hiddenHttpMethodFilter` method.
- [Spring Boot 3.3 — Conditions Evaluation Report API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): structure of `positiveMatches`, `negativeMatches`, and each condition's message.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): enabling, exposing, and securing endpoints.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test contexts and auto-configured tests.
- [Spring Framework — Special Bean Types in DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html): role of handler mappings, handler adapters, and special beans.
