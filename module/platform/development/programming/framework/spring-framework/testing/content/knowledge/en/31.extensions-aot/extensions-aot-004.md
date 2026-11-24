# `TestContextBootstrapper` When Changing the Initialization Mechanism

## 1. What Is `TestContextBootstrapper`?

The Spring TestContext Framework manages how a test is connected to an `ApplicationContext`, how the context is loaded, and how test callbacks are executed. `TestContextBootstrapper` is the extension point at the startup layer of this mechanism.

The bootstrapper is responsible for providing the `TestContext` and the list of `TestExecutionListener` instances to `TestContextManager`. It also participates in building `MergedContextConfiguration`, which is the configuration merged from test annotations and inherited configuration on the test class.

The merged information may include:

- Configuration classes or resource locations declared with `@ContextConfiguration`.
- The `ContextLoader` used to create the `ApplicationContext`.
- Active profiles.
- Test-specific property sources.
- Context initializers and context customizers.
- Web application context configuration and parent-child context hierarchy.

In most tests, built-in annotations such as `@SpringJUnitConfig`, `@ContextConfiguration`, `@WebAppConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, or `@DynamicPropertySource` are sufficient to describe the context to create. You should only replace the bootstrapper when you need to change the framework-level initialization policy for a group of tests or the entire test suite.

## 2. Where the Bootstrapper Fits in the Test Lifecycle

When JUnit runs a test with Spring integration, `SpringExtension` or the corresponding runner creates a `TestContextManager`. This manager determines the bootstrapper, obtains the `TestContext` and listeners from the bootstrapper, and invokes the listeners at the appropriate points in the test lifecycle.

Overall flow:

```text
JUnit Jupiter / SpringExtension
             |
             v
      TestContextManager
             |
             v
      Select TestContextBootstrapper
       - @BootstrapWith if declared
       - appropriate default bootstrapper
             |
             v
      Bootstrapper builds TestContext
      and list of TestExecutionListener
             |
             v
      MergedContextConfiguration
      - classes / locations
      - profiles / properties
      - loader / initializers
      - context customizers / parent
             |
             v
      ContextLoader loads ApplicationContext
             |
             v
      TestContextManager invokes listeners
      around test class / instance / method
             |
             v
          Test method
```

`TestContextBootstrapper` decides how the `TestContext` is set up. `ContextLoader` is responsible for loading the `ApplicationContext` from the merged configuration. `TestExecutionListener` receives callbacks during the test lifecycle. These three components have distinct roles, so you should not use a bootstrapper to solve a requirement that only needs a different `ContextLoader` or an added listener.

## 3. Default Bootstrappers and Spring Boot's Bootstrappers

If a test does not declare `@BootstrapWith`, Spring selects a default bootstrapper based on the test context type. Common bootstrappers include:

| Bootstrapper | Usage Scope |
|---|---|
| `DefaultTestContextBootstrapper` | Default bootstrapper for standard test contexts. |
| `WebTestContextBootstrapper` | Used for tests with `@WebAppConfiguration`, requiring a web application context on the Servlet stack. |
| `SpringBootTestContextBootstrapper` | Used by Spring Boot for `@SpringBootTest`, adding Boot-specific initialization behavior. |
| Test slice bootstrappers | Annotations such as `@WebMvcTest` may use their own bootstrapper to apply the corresponding auto-configuration and slice filters. |

Spring Boot provides its own bootstrappers because Boot test initialization includes additional concepts such as `@SpringBootConfiguration`, `@SpringBootTest`, `@AutoConfigure...`, `ContextCustomizerFactory`, and Boot environment configuration. If a test uses `@SpringBootTest` or a test slice, do not arbitrarily replace the Boot bootstrapper with `DefaultTestContextBootstrapper`; doing so can lose behaviors expected by Boot annotations.

Default bootstrapper class names and selection logic can vary by Spring Framework or Spring Boot version. When exact control is needed, check the `@BootstrapWith` annotation on the test annotation in use and the Javadoc for your project's version.

## 4. Specifying a Bootstrapper with `@BootstrapWith`

`@BootstrapWith` lets you specify a `TestContextBootstrapper` implementation for a test class. This annotation can also be used as a meta-annotation to create a shared testing annotation within a project.

For example, creating a custom bootstrapper extending `DefaultTestContextBootstrapper`:

```java
import org.springframework.test.context.support.DefaultTestContextBootstrapper;

public class ProjectTestContextBootstrapper
        extends DefaultTestContextBootstrapper {

    // Place shared bootstrap customizations for the project's test group here.
}
```

Registering the bootstrapper on a test class:

```java
import org.springframework.test.context.BootstrapWith;
import org.springframework.test.context.ContextConfiguration;

@BootstrapWith(ProjectTestContextBootstrapper.class)
@ContextConfiguration(classes = TestApplicationConfiguration.class)
class CatalogRepositoryTests {
}
```

This example illustrates replacing the default bootstrapper with a project implementation. Because the class does not override any behavior yet, it retains the workings of `DefaultTestContextBootstrapper`. A real-world bootstrapper should only override the hooks it needs to change; you should not copy all of Spring's logic into your project.

### Creating a Composed Annotation for a Group of Tests

If multiple tests need the same bootstrapper and configuration conventions, you can wrap `@BootstrapWith` into a custom annotation:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.test.context.BootstrapWith;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@BootstrapWith(ProjectTestContextBootstrapper.class)
public @interface ProjectIntegrationTest {
}
```

Using the annotation:

```java
@ProjectIntegrationTest
@ContextConfiguration(classes = IntegrationTestConfiguration.class)
class InventoryIntegrationTests {
}
```

A composed annotation lets a group of tests share the same bootstrap policy without repeating `@BootstrapWith`. If the annotation is used alongside a higher-level annotation like `@SpringBootTest`, ensure the chosen bootstrapper remains compatible with that annotation's mechanism.

## 5. Customizing the Default `ContextLoader`

One reason a custom bootstrapper may be needed is when a project wants to pick the default `ContextLoader` according to its own convention. `AbstractTestContextBootstrapper` provides the `getDefaultContextLoaderClass(Class<?>)` hook to determine the fallback loader when `@ContextConfiguration` does not specify a loader explicitly.

For example, suppose a project has a group of legacy XML tests and wants to use `GenericXmlContextLoader` as the default loader:

```java
import org.springframework.test.context.ContextLoader;
import org.springframework.test.context.support.DefaultTestContextBootstrapper;
import org.springframework.test.context.support.GenericXmlContextLoader;

public class LegacyXmlTestContextBootstrapper
        extends DefaultTestContextBootstrapper {

    @Override
    protected Class<? extends ContextLoader> getDefaultContextLoaderClass(
            Class<?> testClass) {
        return GenericXmlContextLoader.class;
    }
}
```

Registering the bootstrapper and declaring an XML resource:

```java
import org.springframework.test.context.BootstrapWith;
import org.springframework.test.context.ContextConfiguration;

@BootstrapWith(LegacyXmlTestContextBootstrapper.class)
@ContextConfiguration(locations = "classpath:/legacy-test-context.xml")
class LegacyBillingTests {
}
```

In this example, the test does not declare `loader = ...`, so the bootstrapper supplies the default loader. If `@ContextConfiguration` specifies an explicit `ContextLoader`, that choice takes precedence according to annotation configuration. This hook only replaces the fallback loader; it does not modify the contents of the XML file or automatically add beans to the context.

If only a single test needs the XML loader, declaring `@ContextConfiguration(loader = GenericXmlContextLoader.class)` is usually simpler. A custom bootstrapper makes sense when that rule needs to be applied consistently across an entire family of tests.

## 6. Choosing the Right Extension Point Instead of Replacing the Bootstrapper

`TestContextBootstrapper` is a high-level extension point. Before creating a custom implementation, identify which part the change actually belongs to:

| Need | More Appropriate Extension Point |
|---|---|
| Only changing configuration classes or resource locations | `@ContextConfiguration` |
| Only changing the loader for a single test | The `loader` attribute of `@ContextConfiguration` |
| Needing to add beans or adjust context configuration | `@TestConfiguration`, `@Import`, `ApplicationContextInitializer`, or dedicated test configuration |
| Needing to conditionally alter the context or dynamically register beans | `ContextCustomizer` / `ContextCustomizerFactory` |
| Needing to add listeners for the test lifecycle | `@TestExecutionListeners` with the appropriate merge mode |
| Needing to enable profiles | `@ActiveProfiles` or `ActiveProfilesResolver` |
| Needing to add static properties for tests | `@TestPropertySource` or Boot annotation `properties` attribute |
| Needing properties dependent on ports/containers created at runtime | `@DynamicPropertySource` |
| Needing a parent-child multi-context structure | `@ContextHierarchy` |
| Needing to change the overall bootstrap policy, configuration merging, or default listeners for a family of tests | Custom `TestContextBootstrapper` |

In particular, `ContextCustomizerFactory` is often the right choice if the goal is to add a customizer to the context while keeping the rest of the bootstrap process intact. A custom bootstrapper should only be chosen when you need to change overall policy that lower-level extension points cannot satisfy.

## 7. When Should You Extend Spring Boot's Bootstrapper?

For Spring Boot tests, the selected bootstrapper can provide essential logic for discovering Boot configuration, handling `@SpringBootTest`, applying test slices, and adding Boot's context customizers.

If you need to customize a Boot test, consider in order:

1. Use `@TestConfiguration`, `@Import`, `@DynamicPropertySource`, or `@ActiveProfiles` if you only need to change beans, properties, or profiles.
2. Use `ContextCustomizerFactory` if you need to intervene in the context according to an encapsulatable rule.
3. Only when you truly need to change bootstrap policy, extend the Boot bootstrapper corresponding to the annotation in use and preserve its behavior.

Example of the inheritance principle:

```java
import org.springframework.boot.test.context.SpringBootTestContextBootstrapper;

public class ProjectBootTestContextBootstrapper
        extends SpringBootTestContextBootstrapper {

    // Override only the hooks the project actually needs to change.
}
```

The class above preserves the bootstrap foundation of `@SpringBootTest`. When applying it, register the custom bootstrapper via the appropriate annotation and verify compatibility with your Boot version. With test slices such as `@WebMvcTest`, the bootstrapper may be a slice-specific implementation; extending `SpringBootTestContextBootstrapper` does not necessarily preserve that slice behavior.

Do not replace Boot's bootstrapper with `DefaultTestContextBootstrapper` just to solve a property or bean problem. Doing so can cause the test to initialize a different context than what Spring Boot expects.

## 8. `MergedContextConfiguration` and the Context Cache

`MergedContextConfiguration` is the data model describing the merged configuration for loading an `ApplicationContext`. It holds information such as the test class, locations, classes, context initializers, active profiles, property source descriptors, context customizers, parent configuration, and loader.

The Spring TestContext Framework uses this merged configuration to manage the context cache. Tests with equivalent configurations can reuse a context to reduce runtime.

When customizing a bootstrapper, ensure that the merged configuration data fully reflects all factors affecting the context. If a bootstrapper produces different contexts without reflecting that difference in the configuration or an appropriate customizer, the cache may reuse an incorrect context for the current test.

Do not modify `MergedContextConfiguration` in a way that omits information about profiles, properties, loader, or context customizers. If you need to change configuration, use the hooks provided by Spring and ensure all components participate properly in equality comparison/cache key generation.

## 9. How Bootstrapper, `ContextLoader`, and `ContextCustomizer` Work Together

These three extension points are often confused because all three affect how the `ApplicationContext` is created:

| Component | Responsibility | Example |
|---|---|---|
| `TestContextBootstrapper` | Determines how the `TestContext` and merged configuration are built; supplies default listeners. | `DefaultTestContextBootstrapper`, Boot bootstrappers, or a project bootstrapper. |
| `ContextLoader` | Creates and loads the `ApplicationContext` from `MergedContextConfiguration`. | `AnnotationConfigContextLoader`, `GenericXmlContextLoader`, `DelegatingSmartContextLoader`. |
| `ContextCustomizer` | Applies a specific change to the context during preparation before the context is refreshed. | Registering beans or adjusting configuration based on test metadata. |

For example, if you only need to register a mock bean for integration tests, `@TestConfiguration` or `ContextCustomizer` is more appropriate than replacing the bootstrapper. If you need a custom loader to read a configuration format, consider `ContextLoader`. If an entire group of tests needs different configuration-merging rules or default listeners, the bootstrapper is the layer to consider.

## 10. Impact on AOT and Bootstrap Determinism

Spring Framework supports AOT processing for test contexts in modern versions. During the AOT phase, test context configurations are analyzed and initializers or supporting code are generated for running tests in AOT mode.

A custom bootstrapper must behave deterministically between the AOT generation phase and the test execution phase. If a bootstrapper picks configuration based on changing environment variables, external system state, or random values, the context analyzed at build time may differ from the context at runtime.

When a project uses AOT for tests:

- Keep bootstrap configuration stable and determinable from declared annotations/configuration.
- Do not depend on production services or the Internet to decide which context to create.
- Verify that custom `ContextLoader`, initializers, and context customizers are compatible with the AOT pipeline in use.
- If a custom bootstrapper changes how the context is created, run tests in both normal mode and the AOT pipeline to detect discrepancies.
- Provide runtime hints or AOT contributions when custom extensions use reflection, resources, or proxies that must be recognized ahead of time.

A bootstrapper does not automatically make a test context AOT-compatible. AOT compatibility depends on how the entire context and its extension points are constructed. If you only need to add deterministic properties or beans, using standard annotations or customizers usually helps Spring analyze the configuration more easily.

## 11. Testing a Custom Bootstrapper

Once you have a custom bootstrapper, test it with a small test context and verify the behavior the bootstrapper is responsible for. There is no need to re-test the entire Spring TestContext Framework.

The example below illustrates verifying the loaded profile and bean in the test context:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.BootstrapWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestApplicationConfiguration.class)
@BootstrapWith(ProjectTestContextBootstrapper.class)
@ActiveProfiles("bootstrap-test")
class ProjectBootstrapperTests {

    @Autowired
    ApplicationContext context;

    @Test
    void loadsTheExpectedTestContext() {
        assertThat(context.getEnvironment().getActiveProfiles())
                .contains("bootstrap-test");
        assertThat(context.containsBean("testMarker")).isTrue();
    }
}
```

`TestApplicationConfiguration` needs to declare a bean named `testMarker`. This example verifies that the test context loads and the profile is applied; if the bootstrapper has specific behavior such as choosing a loader, write assertions directly for that outcome, such as checking a specific bean or context type. To avoid writing a test that merely verifies Spring defaults, pick a concrete behavior that the bootstrapper actually changes.

## 12. Common Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Boot test loses auto-configuration after adding `@BootstrapWith` | Boot's bootstrapper was replaced with a generic Framework bootstrapper. | Extend the corresponding Boot bootstrapper or use a lower-level extension point. |
| `@ContextConfiguration` does not use the expected loader | Loader was specified explicitly or the default hook was not invoked. | Check the `loader` attribute and `getDefaultContextLoaderClass(...)`. |
| Test class does not receive expected listeners | Custom bootstrapper altered the default listener list. | Keep required listeners or use an appropriate merge mechanism; inspect listeners supplied by the bootstrapper. |
| Context cache returns an inappropriate context | Dynamic configuration or customizers do not fully reflect differences between tests. | Include differences in merged configuration/customizers and manage cache keys properly. |
| Custom bootstrapper is not selected | `@BootstrapWith` is not placed on the test or meta-annotation is not applied as expected. | Check direct annotations, composed annotations, and annotation inheritance. |
| Test works normally but fails under AOT | Bootstrapper or extension depends on information available only at runtime. | Keep configuration deterministic and verify AOT support for loaders/customizers/initializers. |
| Bootstrapper is overly complex | Using a high-level SPI to handle minor property or bean changes. | Switch to `@TestPropertySource`, `@DynamicPropertySource`, `@TestConfiguration`, or `ContextCustomizerFactory`. |

## 13. Decision Process for Whether a Custom Bootstrapper Is Needed

Before creating a new bootstrapper, answer each question in turn:

1. Can the problem be solved with existing test configuration annotations?
2. If you need to change how the context is loaded, is `ContextLoader` sufficient?
3. If you need to add changes before context refresh, do `ApplicationContextInitializer` or `ContextCustomizer` meet the need?
4. If you only need to add lifecycle callbacks, is `@TestExecutionListeners` appropriate?
5. If you need to change configuration-merging rules, default loader selection, or listener policy for a whole group of tests, is `TestContextBootstrapper` the right layer?
6. If using Spring Boot, does the new bootstrapper preserve the behavior of Boot's bootstrapper or test slice?
7. If using AOT, do the bootstrapper and related extensions behave deterministically in both build and runtime phases?

When the answers to earlier steps show that a simpler extension point is sufficient, use that extension point. A custom bootstrapper should be reserved for a bootstrap policy with a clear scope that is genuinely shared by multiple tests.

## 14. Conclusion

`TestContextBootstrapper` is the SPI that controls how the Spring TestContext Framework builds `TestContext`, merges configuration, and supplies listeners for the test lifecycle. `@BootstrapWith` selects the bootstrapper for a test class or group of tests. When you need to change the default loader or overall bootstrap policy, you can extend `DefaultTestContextBootstrapper` or the corresponding Spring Boot bootstrapper and override the appropriate hooks. For minor changes to beans, profiles, properties, individual loaders, or listeners, prefer dedicated annotations and specialized extension points. Choosing the right layer helps preserve Spring's default behavior, reduces risks with the context cache, and makes test contexts easier to keep compatible with AOT.

## References

- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Javadoc — `TestContextBootstrapper`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestContextBootstrapper.html)
- [Spring Framework Javadoc — `@BootstrapWith`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/BootstrapWith.html)
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
