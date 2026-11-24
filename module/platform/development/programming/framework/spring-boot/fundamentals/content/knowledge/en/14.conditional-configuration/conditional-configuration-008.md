# `@ConditionalOnResource` and Resource Conditions

A Spring Boot application sometimes should only register a configuration part when a required file or resource is present. For example, a reporting module may only work when the template file `templates/report.html` is packaged in the application; a schema-reading adapter should only be created when the schema file exists; or a default configuration is only appropriate when a library-bundled resource is present.

Spring Boot provides the **`@ConditionalOnResource`** annotation to express this condition. When the specified resources exist according to Spring's resource resolution mechanism, the condition matches and the configuration or bean is allowed to be registered. If the resource does not exist, the marked configuration part is not applied.

This annotation configures beans based on resource presence. It does not read and check file contents, validate file formats, or automatically watch for file changes after the application context has started.

This lesson covers how to declare resource conditions on configuration classes and `@Bean` methods, how to use resource locations such as `classpath:` and `file:`, the impact of specifying multiple resources, how to test both branches of the condition, and common pitfalls.

## 1. What Is a Resource Condition?

In Spring, a **resource** is an abstraction for assets an application can read, such as:

- A file packaged on the classpath.
- An external file on the filesystem.
- A resource accessed via a URL or appropriate `ResourceLoader` mechanism.
- A resource provided by another library or module.

For example, a project has the file:

~~~text
src/main/resources/
└── templates/
    └── report.html
~~~

After building, this resource is typically placed on the application's classpath at the path:

~~~text
templates/report.html
~~~

If a configuration should only be enabled when that file is present, we can use:

~~~java
@ConditionalOnResource(resources = "classpath:templates/report.html")
~~~

`@ConditionalOnResource` is a Spring Boot annotation in the package:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
~~~

This annotation is built on Spring's condition mechanism. It checks the existence of the declared resource locations through `ResourceLoader` during configuration evaluation.

### 1.1. When Does the Condition Match?

Suppose the configuration is:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/report.html")
public class ReportTemplateConfiguration {
    // Beans are only registered when the resource exists.
}
~~~

Two scenarios:

| Resource status | Condition outcome |
| --- | --- |
| `templates/report.html` is on the classpath | Condition matches; Spring processes the configuration |
| Resource not found | Condition does not match; marked configuration is not applied |

The condition is evaluated while Spring processes configurations and registers bean definitions. It is not a statement executed each time a business method is called.

If the resource appears after the context has already started, Spring does not automatically re-register beans just because the file was created. Re-evaluating the condition requires an appropriate context lifecycle, typically starting or refreshing a new context.

### 1.2. This Annotation Belongs to Spring Boot

`@ConditionalOnResource` resides in `spring-boot-autoconfigure`, package `org.springframework.boot.autoconfigure.condition`. It is not a core Spring Framework annotation like `@Conditional`.

In a typical Spring Boot application, starters and Boot configurations bring `spring-boot-autoconfigure` into the dependency graph. If you use plain Spring Framework without the Spring Boot Autoconfigure module, you cannot import this annotation from `spring-context` alone.

## 2. Placing `@ConditionalOnResource` on a Configuration Class

The most common usage is placing the annotation on a `@Configuration` class.

Suppose a reporting module works only when a template file exists:

~~~text
src/main/resources/
└── templates/
    └── report.html
~~~

Create the configuration class:

~~~java
package com.example.report;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/report.html")
public class ReportTemplateConfiguration {

    @Bean
    public Resource reportTemplate(ResourceLoader resourceLoader) {
        return resourceLoader.getResource("classpath:templates/report.html");
    }

    @Bean
    public ReportService reportService(Resource reportTemplate) {
        return new ReportService(reportTemplate);
    }
}
~~~

`ReportService` is an application class receiving the resource via constructor:

~~~java
package com.example.report;

import org.springframework.core.io.Resource;

public class ReportService {
    private final Resource reportTemplate;

    public ReportService(Resource reportTemplate) {
        this.reportTemplate = reportTemplate;
    }

    public boolean hasTemplate() {
        return reportTemplate.exists();
    }
}
~~~

When `templates/report.html` is present:

1. Spring evaluates the condition on `ReportTemplateConfiguration`.
2. `ResourceLoader` determines the resource exists.
3. The configuration is processed.
4. Both bean definitions `reportTemplate` and `reportService` are registered.
5. When `ReportService` needs to be created, Spring supplies the `Resource` bean via the constructor.

When the file does not exist, the configuration does not match, and neither bean method in this configuration class is registered from it.

Placing the condition on the whole class is helpful when **a group of beans shares a dependency on a resource**. It avoids situations where one bean is skipped while another bean is still registered and demands the missing dependency.

## 3. Placing `@ConditionalOnResource` on a `@Bean` Method

If only one bean needs the resource, you can place the condition directly on the factory method.

~~~java
package com.example.report;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
public class OptionalReportConfiguration {

    @Bean
    @ConditionalOnResource(resources = "classpath:templates/optional-report.html")
    public Resource optionalReportTemplate(ResourceLoader resourceLoader) {
        return resourceLoader.getResource(
                "classpath:templates/optional-report.html"
        );
    }
}
~~~

In this case:

- The configuration class is still processed.
- The `optionalReportTemplate` bean definition is only registered when the resource exists.
- Other bean methods in the class are not subject to this condition, unless they have their own conditions or their enclosing class is also annotated with a condition.

This works well when a configuration class provides multiple independent beans and only one of them requires an optional file.

### 3.1. Be Careful with Mandatory Dependencies on Conditional Beans

Suppose there is an independently component-scanned service:

~~~java
@Service
public class ReportService {
    public ReportService(Resource optionalReportTemplate) {
        // ...
    }
}
~~~

If `optionalReportTemplate` is not registered because the file does not exist, `ReportService` is still scanned and still demands a `Resource` in its constructor. The context may fail because no matching bean is found.

This is a common design mistake: **a bean is excluded by a condition while its consumer remains unconditionally registered**.

There are several ways to handle this depending on application intent:

- Place the condition on the entire configuration/service that requires the resource.
- Use `ObjectProvider<Resource>` if the dependency is genuinely optional and the consumer handles the missing-bean case.
- Use another default implementation if business logic allows it.
- Use `@ConditionalOnMissingBean` or another condition to configure an appropriate fallback.

Example using `ObjectProvider`:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<Resource> templateProvider;

    public ReportService(ObjectProvider<Resource> templateProvider) {
        this.templateProvider = templateProvider;
    }

    public boolean hasTemplate() {
        Resource resource = templateProvider.getIfAvailable();
        return resource != null && resource.exists();
    }
}
~~~

This snippet illustrates accessing an optional bean; if an application has multiple unrelated `Resource` beans, you need a qualifier or a dedicated abstraction to select the right template.

Do not inject a generic `Resource` in an application with many kinds of resources. Creating a dedicated type like `ReportTemplate` or using an explicit qualifier is usually clearer.

## 4. Resource Locations and Common Prefixes

`@ConditionalOnResource` accepts resource location strings. Resource resolution uses Spring's `ResourceLoader`, so write explicit prefixes to make clear which source the application is checking.

### 4.1. `classpath:`

Used for resources packaged on the classpath:

~~~java
@ConditionalOnResource(resources = "classpath:templates/report.html")
~~~

Example source location:

~~~text
src/main/resources/templates/report.html
~~~

After building, the file typically sits on the classpath at `templates/report.html`, even though it may live inside an executable JAR rather than as a standalone file on the filesystem.

Other examples:

~~~java
@ConditionalOnResource(resources = "classpath:config/defaults.yml")
@ConditionalOnResource(resources = "classpath:schemas/order-v1.json")
@ConditionalOnResource(resources = "classpath:messages/errors.properties")
~~~

`classpath:` is especially useful when the resource is part of the application or a library.

### 4.2. `file:`

Used when checking a file on the filesystem:

~~~java
@ConditionalOnResource(resources = "file:/opt/myapp/config/report-template.html")
~~~

This example assumes the deployment environment has the file at that corresponding path. Actual paths depend on the operating system and deployment setup.

For external files, remember:

- A file may exist on a developer's machine yet not exist in a container or production server.
- Relative paths depend on the process working directory and how `ResourceLoader` interprets locations.
- Paths should be configured per environment rather than hard-coding a path that only exists on a personal machine.
- A resource being present at startup does not guarantee the file remains there throughout the application's lifetime.

If the resource location needs to vary by environment or configuration, consider using a property and an appropriate condition mechanism; `@ConditionalOnResource` takes resource locations declared in the annotation.

### 4.3. URL Resources

Spring's `Resource` abstraction can support URL prefixes depending on the `ResourceLoader` used. For example, a URL might be written as:

~~~java
@ConditionalOnResource(resources = "https://example.invalid/config/report.json")
~~~

However, you should not use a network URL as an application startup condition by default. Checking the existence of a remote resource can depend on the network, DNS, access permissions, timeouts, and the behavior of the resource implementation. A temporarily unreachable external service can alter startup outcomes.

For production configurations, usually package resources on the classpath or check clearly managed local files. If you need to verify that a remote service is healthy, use an appropriate health check/availability mechanism rather than using a resource condition as a general connectivity check.

### 4.4. Unprefixed Locations and Default Resolution

Spring's `ResourceLoader` has its own rules when a location lacks a prefix. With common default implementations, an unprefixed location is treated as a classpath resource. However, for clear and portable configuration, write `classpath:` or `file:` explicitly instead of relying on implicit interpretation.

## 5. How Does the Condition Behave When Multiple Resources Are Declared?

The `resources` attribute accepts a string array:

~~~java
@Configuration
@ConditionalOnResource(resources = {
        "classpath:schemas/order.json",
        "classpath:schemas/customer.json"
})
public class SchemaConfiguration {
    // ...
}
~~~

In this configuration, the listed resources are required assets. The condition matches only when **all specified resources exist**.

| `order.json` | `customer.json` | Outcome |
| --- | --- | --- |
| Present | Present | Matches |
| Present | Missing | Does not match |
| Missing | Present | Does not match |
| Missing | Missing | Does not match |

If the requirement is "only one of several files needs to exist," `@ConditionalOnResource` does not directly express OR logic by listing multiple entries in the same annotation. You can create separate conditional configurations or write a custom condition expressing the desired OR logic.

Example splitting into two configurations:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/pdf-report.html")
class PdfReportConfiguration {
    // PDF report beans.
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/csv-report.html")
class CsvReportConfiguration {
    // CSV report beans.
}
~~~

Each configuration is evaluated independently. If one file is present, the corresponding configuration can be applied.

## 6. When Is the Condition Evaluated?

`@ConditionalOnResource` is a condition evaluated during Spring's configuration processing. It is evaluated when the container is parsing configurations and deciding which bean definitions to register.

General lifecycle:

~~~text
SpringApplication starts
          │
          ▼
Prepare ApplicationContext
          │
          ▼
Read configuration and metadata
          │
          ▼
Encounter @ConditionalOnResource
          │
          ▼
ResourceLoader checks resource location
          │
      ┌───┴────┐
      ▼        ▼
   Exists   Does not exist
      │        │
      ▼        ▼
 Condition  Condition
  matches  does not match
      │        │
      ▼        ▼
Register    Skip the marked
bean        configuration/bean
definition
~~~

The condition does not re-run on each HTTP request, nor does it automatically register beans when a file appears after startup.

If a resource is created or deleted while the application is running, registered beans do not automatically change accordingly. To have configuration reflect the new state, you need a context refresh/restart strategy or a design that reads resources dynamically at runtime.

### 6.1. Distinguishing Startup Conditions from Runtime Checks

The following two requirements differ:

**Requirement A:** "Only register `ReportService` if the template file is already present when the application starts."

`@ConditionalOnResource` is appropriate.

**Requirement B:** "Each time a report is generated, check whether the file still exists; if deleted, handle the error."

This is runtime logic. The service needs to check `Resource.exists()` or handle errors when reading the file at usage time. `@ConditionalOnResource` does not guarantee the file remains present after startup.

Do not use startup conditions to replace error handling when accessing actual resources.

## 7. `@ConditionalOnResource` Only Checks Existence, Not Content Validation

Suppose `classpath:schemas/order.json` exists, yet contains invalid JSON syntax:

~~~json
{
  "orderId":
~~~

The resource condition can still match because the resource exists. `@ConditionalOnResource` does not parse JSON to validate its contents.

Similarly, the annotation does not guarantee:

- That the file can be successfully read by the user running the application.
- That the file content matches a schema or version.
- That the file has non-empty data.
- That sufficient access permissions exist.
- That the resource will not be deleted or modified after the condition is evaluated.
- That an external system related to the file is healthy.

If content validation is needed, perform it at the appropriate step:

- Use a parser to read and validate format.
- Use Bean Validation or schema validation.
- Check permissions and handle `IOException`.
- Put mandatory checks into startup logic if the application cannot run with invalid configuration.
- Use health indicators for runtime status that needs monitoring.

`@ConditionalOnResource` answers only one narrow question: **is the specified resource location present according to `ResourceLoader`?**

## 8. Comparison with Other Spring Boot Conditions

Spring Boot has many condition annotations. Choosing the right one lets configuration express the exact condition needed.

| Annotation | Main condition | Example |
| --- | --- | --- |
| `@ConditionalOnResource` | Resource location exists | `classpath:templates/report.html` |
| `@ConditionalOnClass` | A class is on the classpath | `com.fasterxml.jackson.databind.ObjectMapper` |
| `@ConditionalOnMissingClass` | A class is not on the classpath | Optional library not installed |
| `@ConditionalOnProperty` | Property has matching value or state | `report.enabled=true` |
| `@ConditionalOnBean` | Matching bean is already registered | `DataSource` |
| `@ConditionalOnMissingBean` | No matching bean exists yet | Providing default implementation |
| `@ConditionalOnWebApplication` | Application has matching web type | Web server configuration |

Examples:

### 8.1. Resource Exists

~~~java
@Configuration
@ConditionalOnResource(resources = "classpath:reports/template.html")
class ReportConfiguration {
}
~~~

Question: is the template file present?

### 8.2. Property Enables Feature

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "reports",
        name = "enabled",
        havingValue = "true"
)
class ReportFeatureConfiguration {
}
~~~

Question: does `reports.enabled` enable the feature?

### 8.3. Class on Classpath

~~~java
@Configuration
@ConditionalOnClass(name = "com.example.pdf.PdfRenderer")
class PdfIntegrationConfiguration {
}
~~~

Question: does the library provide the required class?

### 8.4. Bean Registered

~~~java
@Configuration
@ConditionalOnBean(DataSource.class)
class DatabaseReportConfiguration {
}
~~~

Question: does the container have a matching `DataSource` bean?

Conditions can be combined if a configuration requires multiple conditions:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.pdf.PdfRenderer")
@ConditionalOnResource(resources = "classpath:reports/pdf-template.html")
@ConditionalOnProperty(
        prefix = "reports.pdf",
        name = "enabled",
        havingValue = "true"
)
class PdfReportConfiguration {
    // Applied only when all declared conditions match.
}
~~~

When combining multiple conditions on the same configuration, they form an AND requirement: every condition must match for the configuration to be applied.

## 9. Practical Example: Enabling a Feature Based on a Template File

Suppose an application only provides an invitation generation feature if an HTML template file is packaged.

Structure:

~~~text
src/main/
├── java/com/example/invitation/
│   ├── InvitationApplication.java
│   ├── InvitationService.java
│   └── InvitationTemplateConfiguration.java
└── resources/
    └── templates/
        └── invitation.html
~~~

File `invitation.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Invitation</title>
</head>
<body>
    <h1>Hello!</h1>
    <p>You are invited to attend the event.</p>
</body>
</html>
~~~

Configuration:

~~~java
package com.example.invitation;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/invitation.html")
public class InvitationTemplateConfiguration {

    @Bean
    public Resource invitationTemplate(ResourceLoader resourceLoader) {
        return resourceLoader.getResource(
                "classpath:templates/invitation.html"
        );
    }

    @Bean
    public InvitationService invitationService(Resource invitationTemplate) {
        return new InvitationService(invitationTemplate);
    }
}
~~~

Service:

~~~java
package com.example.invitation;

import org.springframework.core.io.Resource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class InvitationService {
    private final Resource template;

    public InvitationService(Resource template) {
        this.template = template;
    }

    public String loadTemplate() throws IOException {
        try (var inputStream = template.getInputStream()) {
            return new String(
                    inputStream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

If the file is present in `src/main/resources`, the configuration can be applied and the service is created. If the file is not packaged, the condition does not match; neither the `Resource` bean nor `InvitationService` in that configuration class is registered.

This example reads the file content when `loadTemplate()` is called. The condition only checks presence at startup; if the resource disappears later, reading can still throw an `IOException`.

## 10. Configuring External Application Files

Not every resource should be packaged inside the JAR. Some applications allow deploying external template or schema files so they can be updated without rebuilding the artifact.

Example file:

~~~text
/opt/invitation/config/invitation.html
~~~

Condition:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "file:/opt/invitation/config/invitation.html"
)
public class ExternalInvitationConfiguration {
    // ...
}
~~~

If the file exists at the time the condition is evaluated, the configuration can be registered.

However, hard-coding a path like this ties the configuration to a specific environment. If the path varies across deployments, you may need a custom condition or another configuration mechanism to bring a property value into the decision.

An important note: `@ConditionalOnResource` accepts fixed resource locations in annotation metadata. It does not support arbitrary placeholder attributes for runtime configuration substitution in every situation. If the requirement is "read the path from `app.template-location`," you can use a custom `Condition` reading `Environment`, or use `@ConditionalOnProperty` to control the configuration and have the bean read the property and check the resource.

Example combining properties:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "invitation",
        name = "template-enabled",
        havingValue = "true"
)
public class InvitationFeatureConfiguration {

    @Bean
    public InvitationService invitationService(
            Environment environment,
            ResourceLoader resourceLoader) {

        String location = environment.getRequiredProperty(
                "invitation.template-location"
        );

        Resource resource = resourceLoader.getResource(location);
        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Invitation template does not exist: " + location
            );
        }

        return new InvitationService(resource);
    }
}
~~~

Configuration:

~~~properties
invitation.template-enabled=true
invitation.template-location=file:/opt/invitation/config/invitation.html
~~~

In this example, `@ConditionalOnProperty` decides whether to enable the feature; the factory method reads the configured path, checks the resource, and creates the service. If a mandatory resource is missing, the application fails clearly during bean creation.

If you only need a condition on a fixed path, `@ConditionalOnResource` is more concise. If the path is a dynamic property, design an appropriate way to read the property.

## 11. Testing Both Resource-Present and Resource-Missing Cases

Because the condition is evaluated during context creation, you can write integration tests using dedicated test resources.

Example test resource:

~~~text
src/test/resources/
└── conditional/
    └── feature-present.txt
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:conditional/feature-present.txt")
class ConditionalFeatureConfiguration {

    @Bean
    FeatureService featureService() {
        return new FeatureService();
    }
}
~~~

Context test when resource is present:

~~~java
class ConditionalFeatureConfigurationTest {

    @Test
    void registersBeanWhenResourceExists() {
        try (var context = new AnnotationConfigApplicationContext(
                ConditionalFeatureConfiguration.class)) {

            assertTrue(context.containsBean("featureService"));
        }
    }
}
~~~

To test the missing-resource branch, use a nonexistent location:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:conditional/missing.txt")
class MissingResourceConfiguration {

    @Bean
    FeatureService featureService() {
        return new FeatureService();
    }
}
~~~

Test:

~~~java
@Test
void skipsBeanWhenResourceIsMissing() {
    try (var context = new AnnotationConfigApplicationContext(
            MissingResourceConfiguration.class)) {

        assertFalse(context.containsBean("featureService"));
    }
}
~~~

The test snippets require JUnit 5 and Spring Context imports; `FeatureService` is a simple class defined in the test or corresponding source.

### 11.1. Why Use `src/test/resources`?

Resources in `src/test/resources` are normally placed on the test classpath, so tests can verify conditions with sample files without putting those resources into production artifacts.

However, this also creates a point to watch out for: a test passing because a file is on the test classpath does not prove the file is packaged in the production executable JAR. If the resource is required in real execution, ensure it resides in `src/main/resources` or is properly supplied in the deployment environment.

### 11.2. Check Bean Definitions Instead of Merely Calling the Method

The goal of `@ConditionalOnResource` is controlling configuration/bean registration. Therefore tests should assert whether the bean is present or absent in the context, rather than calling the factory method directly in plain Java.

A direct call:

~~~java
new ConditionalFeatureConfiguration().featureService();
~~~

bypasses Spring's condition evaluation process. It does not test `@ConditionalOnResource` behavior.

## 12. Observing Condition Evaluation in Spring Boot

When a configuration is not applied, you can enable debug mode to inspect the auto-configuration conditions report:

~~~bash
java -jar application.jar --debug
~~~

Or in development, enable debug for the application via the appropriate launch configuration.

The condition evaluation report helps identify which configurations matched and which did not. For resource conditions, the report usually provides reasons related to the required or missing resources.

Things to keep in mind:

- Replace the JAR name `application.jar` in the example with the actual artifact.
- The condition report assists diagnostics; it does not replace checking paths and packaged contents.
- If the configuration is regular component-scanned or custom configuration, displayed details may differ from typical auto-configuration reports.
- Read startup logs and root exceptions if errors occur during bean creation after a condition matches.

## 13. Common Pitfalls

### 13.1. Wrong Classpath Path

**Symptom:** File exists in source, yet condition does not match.

Possible causes:

- File placed in a different directory.
- Case mismatch in filename on case-sensitive filesystems.
- Missing the `classpath:` prefix.
- Resource is in `src/test/resources`, while testing production runtime.
- File not packaged into the JAR due to build configuration.

How to check: compare the path under `src/main/resources` with the classpath path, then inspect the built artifact contents.

Example:

~~~text
src/main/resources/templates/report.html
              ↓
classpath:templates/report.html
~~~

Do not include `src/main/resources/` in the classpath location; that is a source directory path, not a resource path on the classpath.

### 13.2. Confusing Filesystem Files with Classpath Resources

If the file lives outside the JAR:

~~~text
/opt/myapp/report.html
~~~

then:

~~~java
@ConditionalOnResource(resources = "classpath:report.html")
~~~

does not check that external file. Use the matching location:

~~~java
@ConditionalOnResource(resources = "file:/opt/myapp/report.html")
~~~

`classpath:` and `file:` point to two different sources.

### 13.3. Condition Does Not Match, Yet a Service Is Still Created

If a condition is only placed on a `@Bean` method while another service is independently component-scanned and requires that bean, the context may report a missing dependency.

How to fix: place the condition on the entire configuration group needing the resource, or make the dependency optional and handle the missing case.

### 13.4. File Is Present, Yet Application Fails When Reading It

`@ConditionalOnResource` only checks existence. The file may be unreadable, have the wrong encoding, contain malformed contents, or be modified after startup.

How to fix: handle exceptions when opening resources and validate contents in the appropriate place. If the file is mandatory for the application to function, you can validate its contents during initialization to fail fast with a clear message.

### 13.5. Conditions Are Evaluated Only at Startup

Creating a file after the application is running does not automatically make the bean appear. Deleting a file after startup does not automatically remove the bean from the context.

How to fix: if file state needs to change dynamically, use a service that checks resources at runtime or design an appropriate refresh/reload mechanism. Do not expect `@ConditionalOnResource` to act like a file watcher.

### 13.6. Listing Multiple Resources When Only One File Is Created

If you declare:

~~~java
@ConditionalOnResource(resources = {
        "classpath:a.properties",
        "classpath:b.properties"
})
~~~

and only `a.properties` exists, the condition does not match because `b.properties` is missing.

If the logic requires either one of the two files, split the conditions or write a custom condition expressing OR logic.

### 13.7. Using a Remote Resource URL as a Startup Dependency

A URL may be unreachable at startup due to network or external service issues. Using it as a condition can make startup depend on external availability.

How to fix: package required resources locally or use an appropriate readiness/health check mechanism. `@ConditionalOnResource` is not a general health check.

## 14. When Should You Use `@ConditionalOnResource`?

Appropriate when **the presence or absence of a resource** decides whether a group of beans or a feature should be registered.

Examples:

- A report-rendering module enabled only when a packaged template exists.
- An integration active only when a library-bundled schema or mapping file is present.
- A starter providing a bean that reads a default resource if the resource is on the classpath.
- A configuration supporting a data format registered only when its metadata file is present.
- An optional feature with resources installed alongside the module.

Not appropriate when:

- Simply toggling via a property.
- Confirming a class or library is on the classpath.
- Confirming another bean has been registered.
- Validating whether a file's content is valid.
- Watching for continuous file changes after startup.
- Checking whether a remote service is healthy.

Choosing the condition matching the exact question you need to answer keeps configuration readable and free of hidden assumptions.

## 15. Practice Exercises

### Exercise A: Enabling Configuration When a Template Exists

Create the file:

~~~text
src/main/resources/templates/welcome.html
~~~

Register a `WelcomeTemplate` bean using `@Bean` and annotate the method with:

~~~java
@ConditionalOnResource(resources = "classpath:templates/welcome.html")
~~~

Run the application and confirm the bean is in the context.

Then rename or move the file, restart, and confirm the bean is no longer registered.

### Exercise B: Conditions on Class vs. Method

Create a configuration class with two bean methods:

- Bean A only needs resource `classpath:feature/a.txt`.
- Bean B only needs resource `classpath:feature/b.txt`.

Place separate conditions on each method. Create the two files in different combinations and observe which bean definitions appear.

Then try moving the condition up to the class and explain why the entire configuration is skipped if the class condition does not match.

### Exercise C: Checking Multiple Resources

Declare:

~~~java
@ConditionalOnResource(resources = {
        "classpath:config/one.yml",
        "classpath:config/two.yml"
})
~~~

Test all four combinations of presence/absence for the two files. Record which cases match the condition.

### Exercise D: Distinguishing Existence from Valid Content

Create a JSON file that exists yet has invalid syntax. Confirm the condition still matches. Then add JSON parsing logic during bean initialization or in a service and observe the parsing error.

Explain why these two checks belong to two separate responsibilities.

### Exercise E: Avoiding Missing Dependencies

Create a `TemplateService` bean registered only when a template is present, then create another component that unconditionally injects `TemplateService`.

Delete the template and observe the startup error. Fix it by placing the condition on the whole configuration group or using an optional dependency with explicit handling.

### Exercise F: Checking Classpath in Tests and Production

Place a resource in `src/test/resources` and verify tests see the file. Then verify the file is not automatically included in the production executable JAR. Move the required file to `src/main/resources` and re-verify the artifact.

## 16. Self-Check Questions

**1. Which package does `@ConditionalOnResource` belong to?**

`org.springframework.boot.autoconfigure.condition`. It is an annotation from Spring Boot Autoconfigure.

**2. What does the annotation check?**

It checks the existence of declared resource locations via Spring's `ResourceLoader`.

**3. If two resources are listed, is having just one resource exist sufficient?**

No. All listed resources must exist for the condition to match.

**4. Where can the annotation be placed?**

It can be placed on a configuration class or a `@Bean` method to control applying that configuration or registering the corresponding bean.

**5. The resource exists, yet contains invalid JSON; does the condition match?**

It can match because the annotation checks existence, not parsing or validating JSON contents.

**6. Does creating the file after the application has started automatically make the bean appear?**

No. Conditions are evaluated during configuration processing; subsequent resource changes do not trigger bean registration.

**7. How does `classpath:` differ from `file:`?**

`classpath:` looks up resources on the application classpath; `file:` points to resources on the filesystem.

**8. When a conditional bean is not registered, what issue can a consumer injecting it unconditionally face?**

If the consumer is still registered and its constructor requires that bean, Spring cannot resolve the dependency. You need to make the whole group of beans conditional or design an optional dependency.

**9. Is `@ConditionalOnResource` a health check?**

No. It does not confirm external services are healthy and does not monitor resources at runtime.

## 17. Conclusion

`@ConditionalOnResource` allows Spring Boot to **apply a configuration or register a bean only when specified resources exist**. The annotation can be placed on a `@Configuration` class to condition a group of beans or on a `@Bean` method to condition that individual bean.

Use explicit resource locations such as `classpath:templates/report.html` or `file:/opt/myapp/report.html`, keep in mind that all listed resources must be present, and remember that conditions are evaluated during context startup. The annotation only checks existence; reading, parsing, validating, and handling content errors remain the application's responsibility.

When a conditional bean is injected into other services, make sure consumers can also exist when that bean is absent. Combining `@ConditionalOnResource` properly with `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, and dependency injection mechanisms keeps conditional configuration clear, testable, and aligned with the application's actual resources.
