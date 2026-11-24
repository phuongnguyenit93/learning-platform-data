# Keeping New Integrations as Optional Components with Independent Tests

When extending Springdoc, a new customizer, model converter, security scheme, or documentation group can affect the application's entire OpenAPI document. If that integration serves only one subset of systems or a non-default feature, design it as an optional component and test both its enabled and disabled states separately.

An optional integration should satisfy three conditions:

1. **No unintended activation**: when unconfigured, the integration does not alter the existing document.
2. **No mandatory dependency**: if the extension library or corresponding Springdoc feature is absent from the classpath, the application still boots when the feature is not requested.
3. **Independent tests**: verify activation conditions, enabled behavior, disabled behavior, and actual impact on the OpenAPI document.

In this article, we build an illustrative integration: adding an `X-Request-Id` header to operations marked with `@AuditedOperation`. The customizer activates only when `acme.openapi.audit.enabled=true`; when disabled, the OpenAPI document remains unchanged.

## 1. Separating Feature Activation Conditions from Integration Logic

Do not create a customizer unconditionally and check the property in multiple places inside lambdas. Place the condition on bean configuration so Spring registers the bean only when the feature is enabled.

```yaml
acme:
  openapi:
    audit:
      enabled: false
```

The default value is `false`. Only environments or applications that actually need the integration enable it:

```yaml
acme:
  openapi:
    audit:
      enabled: true
```

`acme.openapi.audit.enabled` is an application-defined extension property, not a built-in Springdoc property. Using a dedicated namespace avoids confusion with standard `springdoc.*` settings and clarifies feature ownership.

With `@ConditionalOnProperty`, by default the condition matches only when the property has value `true` as declared in `havingValue="true"`. If the property is omitted, the bean is not created. Do not set `matchIfMissing=true` for a feature intended to be optional/off-by-default.

## 2. Creating a Marker Annotation to Select Operations

The integration should not modify every operation if the requirement applies only to a subset of endpoints. A marker annotation lets controllers opt specific operations into exposing the header.

```java
package com.example.openapi.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditedOperation {
}
```

The annotation uses `RUNTIME` retention because `OperationCustomizer` inspects handler method metadata while Springdoc builds the OpenAPI operation. With `SOURCE` or `CLASS` retention, runtime reflection cannot read the annotation this way.

## 3. Writing an Idempotent `OperationCustomizer`

`OperationCustomizer` allows adjusting an OpenAPI `Operation` based on its `HandlerMethod`. The integration adds `X-Request-Id` only when the method carries `@AuditedOperation`.

```java
package com.example.openapi.audit;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.method.HandlerMethod;
import org.springdoc.core.customizers.OperationCustomizer;

import java.util.ArrayList;
import java.util.List;

public class AuditHeaderOperationCustomizer implements OperationCustomizer {

    private static final String HEADER_NAME = "X-Request-Id";

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        boolean audited = AnnotatedElementUtils.hasAnnotation(
            handlerMethod.getMethod(), AuditedOperation.class
        );

        if (!audited) {
            return operation;
        }

        List<Parameter> parameters = operation.getParameters();
        if (parameters == null) {
            parameters = new ArrayList<>();
            operation.setParameters(parameters);
        }

        boolean alreadyDeclared = parameters.stream().anyMatch(parameter ->
            HEADER_NAME.equalsIgnoreCase(parameter.getName())
                && "header".equalsIgnoreCase(parameter.getIn())
        );

        if (!alreadyDeclared) {
            parameters.add(new Parameter()
                .name(HEADER_NAME)
                .in("header")
                .required(false)
                .description("Optional correlation ID sent by the client to trace requests.")
                .schema(new StringSchema()));
        }

        return operation;
    }
}
```

The customizer is idempotent: if the operation already declares a header with the same name and location, it does not add a duplicate. This helps when a controller already describes the header via annotations or another customizer added it.

`OperationCustomizer` runs during OpenAPI model generation. Never perform I/O, call external services, or query databases inside `customize`; those operations slow down document generation and can couple the docs endpoint to external system availability. All needed metadata should come from the handler method, configuration, or existing beans.

## 4. Registering the Customizer with Conditional Configuration

If the integration lives directly inside the application, a simple configuration can look like:

```java
package com.example.openapi.audit;

import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "acme.openapi.audit",
    name = "enabled",
    havingValue = "true"
)
public class AuditOpenApiConfiguration {

    @Bean
    OperationCustomizer auditHeaderOperationCustomizer() {
        return new AuditHeaderOperationCustomizer();
    }
}
```

When the property is missing or `false`, the configuration does not create the customizer. When the property is `true`, the bean is registered and Springdoc invokes it while building operations.

If the application always has Springdoc on the classpath, the property condition alone suffices. If writing an extension library that may be used in applications without Springdoc installed, add a classpath condition as shown next.

## 5. Keeping Extension Libraries Optional When Springdoc Is Absent from the Classpath

A starter or reusable library may want to offer OpenAPI audit support without forcing every consumer to use Springdoc. In that case, ensure both the dependency graph and auto-configuration are optional.

With Maven, declare the Springdoc dependency as optional in the integration module:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>${springdoc.version}</version>
    <optional>true</optional>
</dependency>
```

`optional=true` prevents Maven from transitively propagating this dependency to consumers of the library. Applications wanting the feature must explicitly add the matching MVC or WebFlux Springdoc starter. It does not implement the classpath condition automatically; auto-configuration must still handle the absence of Springdoc classes.

With Gradle, select the appropriate publication/feature variant configuration so consumers do not pull in Springdoc unintentionally. `compileOnly` can compile the library when Springdoc is not packaged as a default runtime dependency, though you must check publication metadata and how consumers opt into the feature. Do not assume `compileOnly` automatically creates a re-enableable optional feature across all repository types.

## 6. Classpath-Conditional Auto-Configuration

For Spring Boot 3, you can register the library's auto-configuration. Place the Springdoc condition on a nested configuration so classes referencing `OperationCustomizer` are loaded only when Springdoc classes exist.

```java
package com.example.openapi.audit.autoconfigure;

import com.example.openapi.audit.AuditHeaderOperationCustomizer;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AuditOpenApiAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springdoc.core.customizers.OperationCustomizer")
    @ConditionalOnProperty(
        prefix = "acme.openapi.audit",
        name = "enabled",
        havingValue = "true"
    )
    static class SpringdocAuditConfiguration {

        @Bean
        @ConditionalOnMissingBean(name = "auditHeaderOperationCustomizer")
        OperationCustomizer auditHeaderOperationCustomizer() {
            return new AuditHeaderOperationCustomizer();
        }
    }
}
```

The classpath condition is written using the class name string so the outer auto-configuration does not need to resolve Springdoc types when the classpath lacks the dependency. The nested configuration keeps method signatures referencing `OperationCustomizer` inside the guarded scope.

Do not place `@ConditionalOnClass(OperationCustomizer.class)` directly on a `@Bean` method inside the outer configuration and assume every class-loading case is safe. When a dependency is genuinely optional, configuration structure must avoid loading optional types before conditions are evaluated.

`@ConditionalOnMissingBean` in the example specifies a bean name because `OperationCustomizer` is an extension point that allows multiple customizers to coexist. Using `@ConditionalOnMissingBean(OperationCustomizer.class)` could prevent the library's customizer from registering simply because the application already defines another customizer, breaking composability. Use type-based conditions only when the intent is genuinely "at most one bean of this type."

Register auto-configuration in:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File contents:

```text
com.example.openapi.audit.autoconfigure.AuditOpenApiAutoConfiguration
```

`@AutoConfiguration` and `AutoConfiguration.imports` are supported from Spring Boot 2.7 onward and continue in Boot 3. For Spring Boot 2.6 and earlier, auto-configuration registration typically used `spring.factories`; determine the minimum version supported by your starter and provide the matching metadata.

## 7. Using the Annotation in Controllers

Controllers explicitly mark operations requiring the audit header:

```java
package com.example.orders.api;

import com.example.openapi.audit.AuditedOperation;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{id}")
    @AuditedOperation
    @Operation(summary = "Get order details")
    OrderResponse getOrder(@PathVariable Long id) {
        return orderService.getOrder(id);
    }

    @GetMapping("/api/orders/health")
    @Operation(summary = "Check order API health")
    String health(@RequestParam(required = false) String detail) {
        return detail == null ? "ok" : detail;
    }
}
```

When the integration is enabled, `GET /api/orders/{id}` includes the optional `X-Request-Id` header; the `health` operation does not. When the integration is disabled, both operations remain documented by Springdoc according to their original metadata.

Adding a header to the OpenAPI document does not automatically cause controllers to read or validate that header. If runtime code needs `X-Request-Id`, a controller/filter/interceptor must implement that behavior. OpenAPI metadata only describes the contract; it does not alter HTTP handling on its own.

The example uses an annotated controller with `HandlerMethod`. If the application uses WebFlux functional routes (`RouterFunction`), routes do not necessarily pass through the same handler method metadata; describe operations using `@RouterOperation`/`@RouterOperations` or Springdoc's functional DSL and test the route documentation separately.

## 8. Testing Enable/Disable Conditions with `ApplicationContextRunner`

`ApplicationContextRunner` tests auto-configuration in a lightweight context without booting an entire web server. It is the right place to verify properties, classpath conditions, and bean registration.

The tests below use JUnit 5, AssertJ, and Spring Boot Test; you can add the test dependency:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

```java
package com.example.openapi.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;

import static org.assertj.core.api.Assertions.assertThat;

class AuditOpenApiAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(AuditOpenApiAutoConfiguration.class));

    @Test
    void disabledByDefault() {
        contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean("auditHeaderOperationCustomizer");
        });
    }

    @Test
    void registersCustomizerWhenEnabledAndSpringdocIsPresent() {
        contextRunner
            .withPropertyValues("acme.openapi.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasBean("auditHeaderOperationCustomizer");
            });
    }

    @Test
    void backsOffWhenSpringdocCustomizerTypeIsMissing() {
        contextRunner
            .withClassLoader(new FilteredClassLoader("org.springdoc.core.customizers"))
            .withPropertyValues("acme.openapi.audit.enabled=true")
            .run(context -> {
                assertThat(context).doesNotHaveBean("auditHeaderOperationCustomizer");
                assertThat(context).hasNotFailed();
            });
    }

    @Test
    void explicitFalseKeepsIntegrationDisabled() {
        contextRunner
            .withPropertyValues("acme.openapi.audit.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean("auditHeaderOperationCustomizer");
            });
    }
}
```

These tests verify four critical cases: missing property, explicitly enabled, missing Springdoc class, and explicitly disabled. The missing-classpath test is especially valuable for optional starters: it proves an application without Springdoc can still build its context when the feature is inactive.

If the test module always has Springdoc on its test classpath, `FilteredClassLoader` simulates the dependency being absent at runtime. Keep auto-configuration tests small without starting a web server so condition bugs are caught quickly.

## 9. Testing Actual Impact on the OpenAPI Document

Checking that a bean exists is not enough. A customizer might be registered yet never invoked by Springdoc, or might attach parameters to the wrong operation. Write integration tests that read the actual document.

Test when enabled:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "acme.openapi.audit.enabled=true")
@AutoConfigureMockMvc
class AuditOpenApiEnabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsAuditHeaderOnlyToMarkedOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{id}'].get.parameters[*].name"
            ).value(hasItem("X-Request-Id")))
            .andExpect(jsonPath(
                "$.paths['/api/orders/health'].get.parameters[*].name"
            ).value(not(hasItem("X-Request-Id"))));
    }
}
```

The `health` operation in the example has a `detail` query parameter, so the test verifies the operation has parameters without containing `X-Request-Id`. The goal is confirming the marker affects only selected operations.

Test when disabled:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "acme.openapi.audit.enabled=false")
@AutoConfigureMockMvc
class AuditOpenApiDisabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsBaseOpenApiWithoutAuditHeader() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{id}'].get.parameters[*].name"
            ).value(not(hasItem("X-Request-Id"))));
    }
}
```

The test above inspects the `GET` operation's parameter list. In OpenAPI, parameters may also be declared at the Path Item level; if a project's extension supports both locations, parse the document into an object and merge parameter lists per OpenAPI rules before asserting. Quick check example with `jq` after saving the file:

```bash
jq '.paths["/api/orders/{id}"].get.parameters' openapi.json
```

For stable tests, verify the parameter list after merging path-level and operation-level parameters per OpenAPI rules rather than assuming all parameters always sit in one place.

## 10. Isolating Unit Tests for the Customizer

Beyond context and integration tests, test customizer logic with pure unit tests. These tests verify marker annotations, added parameters, and idempotency.

```java
package com.example.openapi.audit;

import io.swagger.v3.oas.models.Operation;
import org.junit.jupiter.api.Test;
import org.springframework.web.method.HandlerMethod;

import static org.assertj.core.api.Assertions.assertThat;

class AuditHeaderOperationCustomizerTests {

    private final AuditHeaderOperationCustomizer customizer =
        new AuditHeaderOperationCustomizer();

    @Test
    void addsHeaderForAuditedMethodOnly() throws Exception {
        HandlerMethod auditedMethod = new HandlerMethod(
            new SampleController(),
            SampleController.class.getMethod("audited")
        );
        Operation operation = new Operation();

        customizer.customize(operation, auditedMethod);

        assertThat(operation.getParameters())
            .extracting(parameter -> parameter.getName())
            .containsExactly("X-Request-Id");
    }

    @Test
    void doesNotAddDuplicateHeader() throws Exception {
        HandlerMethod auditedMethod = new HandlerMethod(
            new SampleController(),
            SampleController.class.getMethod("audited")
        );
        Operation operation = new Operation();

        customizer.customize(operation, auditedMethod);
        customizer.customize(operation, auditedMethod);

        assertThat(operation.getParameters())
            .extracting(parameter -> parameter.getName())
            .containsExactly("X-Request-Id");
    }

    static class SampleController {
        @AuditedOperation
        public void audited() {
        }
    }
}
```

Unit tests do not replace integration tests because they do not prove Springdoc called the customizer or serialized parameters into the document. They test only the operation transformation logic in a small scope.

## 11. Testing Compatibility Across Multiple Springdoc Versions

If an extension library is used across multiple applications, clearly define the supported Spring Boot and Springdoc versions. Never assume every major version shares the same packages, method signatures, or model behavior.

A test matrix may include:

| Variant | Goal |
|---|---|
| Spring Boot 3 + Springdoc v2 | Baseline versions supported by the extension |
| Lowest supported Springdoc version | Catch customizer API or model differences |
| Latest Springdoc version in supported major | Catch compatibility changes in minor/patch releases |
| Springdoc absent from classpath | Confirm optional auto-configuration does not break the context |
| Property undeclared | Confirm off-by-default behavior |
| Property enabled | Confirm customizer takes effect |
| Property disabled | Confirm document is not modified |

Pin dependencies in each test matrix job. When the build uses Spring Boot's Maven/Gradle dependency management, do not force `swagger-core` or `swagger-models` to an independent version without checking compatibility with Springdoc.

## 12. Testing Zero Side Effects When the Integration Is Disabled

An optional feature must include tests for the negative path. When `enabled=false` or the property is absent:

- Do not register customizer beans.
- Do not add unintended parameters, schemas, or security metadata.
- Do not call external services or create scheduled tasks.
- Do not alter the default `OpenAPI` bean or groups.
- Do not trigger startup failures due to missing optional dependencies.
- Do not alter controller runtime responses.

In particular, do not assert only that the bean is absent. Inspect the output document to confirm the extension's metadata is missing. If the extension has side effects outside OpenAPI, verify those side effects with fakes/mocks or spies as well.

## 13. Separating Optional Dependency from Optional Behavior

These two concepts must be designed independently:

| Concept | Question | Mechanism |
|---|---|---|
| Optional dependency | Can the application run when the extension library or Springdoc is absent from the classpath? | Maven optional/Gradle feature metadata, `@ConditionalOnClass` |
| Optional behavior | Can the application keep the integration disabled even when the dependency is present? | `@ConditionalOnProperty`, off by default |

An application may already include Springdoc while not wanting the audit header added; in that case the dependency is present yet the property is off. Conversely, an application not using Springdoc may still use other parts of the library; in that case the classpath condition must prevent Springdoc configuration from loading.

Never use `@ConditionalOnProperty` as a substitute for a classpath condition in an optional library. If a class does not exist yet the configuration still references it, the application can fail with `NoClassDefFoundError` when reading configuration.

## 14. Organizing Packages and Modules for Maintainability

For a small integration living inside an application:

```text
src/main/java/
  com/example/openapi/audit/
    AuditedOperation.java
    AuditHeaderOperationCustomizer.java
    AuditOpenApiConfiguration.java
```

For a reusable library/starter:

```text
openapi-audit-spring-boot-autoconfigure/
  src/main/java/.../AuditOpenApiAutoConfiguration.java
  src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

openapi-audit-spring-boot-starter/
  pom.xml
```

The autoconfigure module holds logic and conditions; the starter aggregates dependencies and publication configuration. Splitting modules pays off only when multiple applications actually reuse it or need optional dependency management. For a single feature inside one service, conditional configuration inside the application itself can be simpler and easier to control.

## 15. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Integration is always enabled | `matchIfMissing=true` or property defaults to true | Use `havingValue="true"` and default false |
| App without Springdoc still fails startup | Auto-configuration loads Springdoc types before condition evaluation | Move optional types into a nested configuration guarded by `@ConditionalOnClass(name=...)` |
| Consumers pull in Springdoc even when unused | Dependency declared as required | Mark optional or configure feature publication properly |
| Customizer is never called | Bean not registered or package/config not scanned/imported | Check condition evaluation and bean registration |
| Header appears on every operation | Customizer does not check the marker annotation | Transform only marked handler methods |
| Duplicate headers | Customizer does not check whether the parameter already exists | Make logic idempotent before adding |
| Bean exists yet document is unchanged | Tests check only the context without checking OpenAPI output | Add integration tests calling `/v3/api-docs` |
| Property disabled yet document still changes | Another customizer or direct annotation also adds metadata | Inspect all extension points and the baseline document |
| `@ConditionalOnMissingBean(OperationCustomizer.class)` blocks other customizers | Extension point allows multiple beans of the same type | Condition on bean name/marker bean or remove the condition if unneeded |
| Integration slows document generation | Customizer performs I/O or scans runtime data | Use only existing metadata; profile the customizer with a profiler |
| Upgrading Springdoc causes compile errors | Model API/package changes across versions | Use a version matrix and check dependency alignment |

## 16. Checklist for Adding an Optional Springdoc Integration

- [ ] Dedicated property exists for the feature and defaults to `false`.
- [ ] Integration is not activated merely because the dependency is on the classpath.
- [ ] Extension library does not force Springdoc as a mandatory dependency if consumers do not need it.
- [ ] Auto-configuration uses `@ConditionalOnClass` when Springdoc is an optional dependency.
- [ ] Springdoc types appear only inside guarded nested configurations when needed.
- [ ] Beans are registered under explicit property conditions.
- [ ] Customizer affects only selected operations.
- [ ] Customizer is idempotent and creates no duplicate parameters/schemas.
- [ ] No network/database calls or side effects occur while building the OpenAPI model.
- [ ] Unit tests cover customizer logic.
- [ ] `ApplicationContextRunner` tests cover default off, explicit on, explicit off, and missing classpath.
- [ ] Integration tests verify the real document when enabled and disabled.
- [ ] Tests confirm controller/API runtime behavior is not unintentionally altered.
- [ ] Supported Spring Boot/Springdoc matrix is defined.
- [ ] Dependency tree and publication metadata have been inspected.

Keep new integrations as optional components by separating two conditions: dependency presence on the classpath and feature activation via property. Springdoc customizers should be registered conditionally, modify only selected operations, and avoid side effects during document generation. For reusable libraries, classpath conditions paired with optional dependency publication allow consumers without Springdoc to still boot cleanly. Finally, test customizer logic, auto-configuration, and the OpenAPI document separately in both enabled and disabled states to prove the new integration does not alter existing contracts outside the requested scope.

## References

- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot – `@ConditionalOnClass` and `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations)
- [Spring Boot – Testing Auto-configuration with `ApplicationContextRunner`](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing)
- [Springdoc OpenAPI – Customization](https://springdoc.org/#how-can-i-customise-the-openapi-description)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
