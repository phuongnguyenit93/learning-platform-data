# @ConditionalOnWarDeployment and @ConditionalOnNotWarDeployment in Spring Boot

## Learning Objectives

When building **auto-configuration**, the same Spring Boot application can be run in two very different ways: deployed as a WAR into an **external servlet container** (such as a Tomcat managed by ops), or **starting an embedded server itself** via `java -jar`. The two annotations `@ConditionalOnWarDeployment` and `@ConditionalOnNotWarDeployment` let you select the configuration suited to how the application **is actually starting**.

After this lesson, you will be able to:

- Explain which condition matches in traditional WAR deployment, embedded-server deployment, and non-web applications.
- Distinguish **JAR/WAR file format** from **deployment model**; especially understand the case of an executable WAR run via `java -jar`.
- Place the annotations properly on a configuration class or on a `@Bean` method, while avoiding confusion with `@ConditionalOnWebApplication`.
- Write a small test for both branches and read the Condition Evaluation Report when actual results differ from expectations.

## 1. Context: Both Are Web Apps, but Who Owns the Servlet Container Differs

### Traditional WAR deployment

The application is packaged as a WAR to be **deployed into a standalone servlet container**, such as `webapps/myapp.war` on an external Tomcat. The container creates and provides the `ServletContext`; the startup mechanism for WARs usually goes through a class extending `SpringBootServletInitializer`.

In this model, the application **does not own creating and starting** an embedded servlet server. Settings belonging to container startup must coordinate with the external system rather than assuming Spring Boot will create a new server.

### Embedded-server deployment

The application starts its own server via the `SpringApplication.run(...)` flow. The most common way to run is an executable JAR containing embedded Tomcat/Jetty/Undertow; additionally, an **executable WAR** can also run with `java -jar app.war`, using its internal embedded server.

Therefore, the critical question for these two annotations is **not** “does the artifact end in `.war` or `.jar`?”, but “is Spring Boot being started via **traditional WAR deployment**, or in another way?”.

## 2. Exact Meaning of the Two Annotations

Both annotations belong to the package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

Usage syntax:

~~~java
@ConditionalOnWarDeployment
@ConditionalOnNotWarDeployment
~~~

Each annotation is a Spring Boot condition based on `@Conditional` and can be placed on a **configuration class** or a **`@Bean` method**. Neither has required parameters.

- **`@ConditionalOnWarDeployment`**: matches when the application runs via traditional WAR deployment and is initialized by an external servlet container. For applications running with an embedded server, this condition **does not match**.
- **`@ConditionalOnNotWarDeployment`**: matches when **not** in the traditional WAR deployment model. For applications running an embedded server, this condition **matches**. It can also match non-web applications, because the condition only says “not a traditional WAR”.

The two annotations carry **opposite** meanings under the same deployment check. Using them on two `@Bean`s or two configuration groups lets the application pick exactly one branch depending on the environment.

### Outcome table to remember

| Startup scenario | `@ConditionalOnWarDeployment` | `@ConditionalOnNotWarDeployment` |
| --- | --- | --- |
| WAR deployed into an **external** Tomcat/Jetty servlet container | **Matches** | Does not match |
| Executable JAR running `java -jar app.jar` with embedded Tomcat | Does not match | **Matches** |
| Executable WAR running `java -jar app.war` with embedded server | Does not match | **Matches** |
| Servlet application using embedded Undertow/Jetty | Does not match | **Matches** |
| CLI or non-web application without a servlet container | Does not match | **Matches** |
| Reactive application not using traditional WAR deployment | Does not match | **Matches** |

**Common pitfall:** `@ConditionalOnNotWarDeployment` is **not synonymous** with “only runs on executable JAR” or “only runs on web apps with embedded Tomcat”. It only excludes traditional WAR deployment. If a bean only makes sense in a servlet application, add a separate condition for a **servlet web application**.

## 3. How Does Spring Boot Detect Traditional WAR?

Spring Boot uses `OnWarDeploymentCondition` to evaluate both annotations. Under Spring Boot 3.x's mechanism, the condition inspects the **context being built**: whether a `WebApplicationContext` is provided during condition evaluation, and whether its `ServletContext` is already present. A `ServletContext` supplied by an external container when a traditional WAR starts is the signal that matches the WAR branch.

With an embedded server, bean definitions and auto-configurations are processed **before** the embedded server finishes starting and creates the servlet context for serving requests. Thus the traditional WAR branch does not match, even though after the server starts, the application still has a `ServletContext`.

Condensed sequence:

1. Spring Boot creates the application context and reads configuration/auto-configuration classes.
2. When encountering `@ConditionalOnWarDeployment` or `@ConditionalOnNotWarDeployment`, the framework checks the current deployment state.
3. The matching branch is allowed to register bean definitions; the other branch is skipped.
4. The context proceeds to instantiate beans, and the application finishes its startup lifecycle.

**Note on timing:** the annotations are **bean-registration conditions during context construction**. They do not change results per request; they do not wait until a bean is first used; and they do not re-observe server state after the application has started.

Do not try to mimic this rule by inferring from `server.port`, an `APP_MODE` environment variable, or the JAR/WAR filename. Those values do not prove who owns the servlet container.

## 4. Usage Example in Auto-Configuration

Suppose a library needs to provide a `DeploymentPolicy` corresponding to where the application runs. In real configuration, we can register two different implementations:

~~~java
package example.deployment.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWarDeployment;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWarDeployment;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class DeploymentPolicyAutoConfiguration {

    @Bean
    @ConditionalOnWarDeployment
    DeploymentPolicy externalContainerPolicy() {
        return new DeploymentPolicy("external-container");
    }

    @Bean
    @ConditionalOnNotWarDeployment
    DeploymentPolicy selfManagedPolicy() {
        return new DeploymentPolicy("self-managed");
    }

    public record DeploymentPolicy(String mode) {
    }
}
~~~

The snippet above is a **standalone production class** if saved at `src/main/java/example/deployment/autoconfigure/DeploymentPolicyAutoConfiguration.java` and the project has the Spring Boot auto-configuration dependency. When running in each model, one of the two bean methods is selected by the condition. Here `DeploymentPolicy` only illustrates a configuration decision; it does **not** create a servlet container or change Tomcat configuration itself.

If this is an auto-configuration provided by a library, register the class name in:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
example.deployment.autoconfigure.DeploymentPolicyAutoConfiguration
~~~

In Spring Boot 3.x, this is the standard mechanism for Boot to discover a library's auto-configuration. When testing both branches, also ensure the configuration class is actually loaded; if the imports file is missing, neither bean appears even when the condition is right.

### Placing the annotation on the class or on the bean?

You can select an entire group of beans dedicated to WAR:

~~~java
@AutoConfiguration
@ConditionalOnWarDeployment
public class ExternalContainerAutoConfiguration {
    // Related @Beans are only processed in traditional WAR.
}
~~~

Conversely, if the same class contains multiple independent beans, place the annotation on the **specific method**. A class-level condition can accidentally exclude beans that still need to run in both models.

### Distinguishing from checking the web application type

`@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)` only states that the application is a **servlet web application**; both traditional WAR and embedded servlet can satisfy it.

If a bean is intended only for **embedded servlet** (not to be created in CLI or WebFlux), we can combine two conditions:

~~~java
@Bean
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnNotWarDeployment
ServletOnlyCustomizer servletOnlyCustomizer() {
    return new ServletOnlyCustomizer();
}
~~~

This is an **illustrative snippet**, assuming `ServletOnlyCustomizer` is a custom application-defined class and `ConditionalOnWebApplication` is imported from the same condition package. Each annotation checks a different aspect: **application type** and **deployment model**.

## 5. Verification Example for Java 17+ / Spring Boot 3.3 / JUnit 5

The following example can be saved as **a complete test file**. The first test creates an `ApplicationContext` without a servlet context, so the **NotWar** branch matches. The second test supplies a `MockServletContext` **before refreshing the context**, simulating the condition of a servlet context already provided by a container, so the **War** branch matches.

**File:** `src/test/java/example/deployment/WarDeploymentConditionsTest.java`

~~~java
package example.deployment;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWarDeployment;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWarDeployment;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.web.MockServletContext;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class WarDeploymentConditionsTest {

    @Test
    void ordinaryContextMatchesNotWar() {
        try (var context =
                     new AnnotationConfigApplicationContext(DeploymentConfiguration.class)) {

            assertThat(context.containsBean("externalWarPolicy")).isFalse();
            assertThat(context.containsBean("otherDeploymentPolicy")).isTrue();
            assertThat(context.getBean(DeploymentPolicy.class).mode())
                    .isEqualTo("not-war");
        }
    }

    @Test
    void contextWithServletContextAtEvaluationMatchesWar() {
        try (var context = new AnnotationConfigWebApplicationContext()) {
            context.setServletContext(new MockServletContext());
            context.register(DeploymentConfiguration.class);
            context.refresh();

            assertThat(context.containsBean("externalWarPolicy")).isTrue();
            assertThat(context.containsBean("otherDeploymentPolicy")).isFalse();
            assertThat(context.getBean(DeploymentPolicy.class).mode())
                    .isEqualTo("war");
        }
    }

    interface DeploymentPolicy {
        String mode();
    }

    @Configuration(proxyBeanMethods = false)
    static class DeploymentConfiguration {

        @Bean
        @ConditionalOnWarDeployment
        DeploymentPolicy externalWarPolicy() {
            return () -> "war";
        }

        @Bean
        @ConditionalOnNotWarDeployment
        DeploymentPolicy otherDeploymentPolicy() {
            return () -> "not-war";
        }
    }
}
~~~

Sample dependencies in `build.gradle` **of a Spring Boot project already configured with the version-managing plugin/BOM**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring Web and the Servlet API; `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and `MockServletContext` via Spring Test. With Spring Boot 3.3, use Java 17+.

Run in the project directory containing the test:

~~~bash
# Linux / macOS
./gradlew test --tests "example.deployment.WarDeploymentConditionsTest"

# Windows
gradlew.bat test --tests "example.deployment.WarDeploymentConditionsTest"
~~~

**Expected result:** both tests PASS. The first test finds the `otherDeploymentPolicy` bean and value `not-war`; the second test finds the `externalWarPolicy` bean and value `war`. There are no `System.out.println` calls, so there is no fixed stdout to compare against; Gradle logs depend on the test runner configuration.

**Limitation of the test:** `MockServletContext` only reproduces **the condition observed by the annotation in a simulated context**. It does not launch an external Tomcat and does not prove that a WAR file has been deployed properly in a real environment. Therefore, before releasing, you should still test traditional WAR deployment on the intended servlet container.

## 6. Understanding “WAR Running Embedded” Correctly

A Spring Boot **executable WAR** can be used in two ways:

~~~text
A. External Tomcat receives app.war
   -> external container creates ServletContext and starts the application
   -> @ConditionalOnWarDeployment: matches
   -> @ConditionalOnNotWarDeployment: does not match

B. java -jar app.war
   -> application runs its own embedded servlet server
   -> @ConditionalOnWarDeployment: does not match
   -> @ConditionalOnNotWarDeployment: matches
~~~

The same artifact has different **startup paths**, so the condition results differ. Merely seeing `bootWar` in Gradle or a `.war` extension in the deployment path is not enough to draw a conclusion.

For traditional WAR deployment, the startup class can extend `SpringBootServletInitializer` (the example below only illustrates the startup pattern; running it requires appropriate dependencies and WAR packaging configuration):

~~~java
@SpringBootApplication
public class MyApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(MyApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

This snippet needs imports for `SpringApplication`, `SpringBootApplication`, `SpringApplicationBuilder`, and `SpringBootServletInitializer` from the corresponding Spring Boot packages. `configure(...)` serves the external servlet container branch; `main(...)` serves the direct-run branch. For Gradle, WAR packaging typically uses the `war` plugin and puts container dependencies under `providedRuntime` per Spring Boot's guide, avoiding owning the container when it is provided externally.

**Do not** attach the annotation based solely on a requirement to “use WAR” if it is actually still launched with an embedded server. Describe the intended deployment path accurately.

## 7. Common Mistakes

1. **Equating `@ConditionalOnWarDeployment` with the `*.war` filename.** Wrong because an executable WAR run via `java -jar` is not a traditional WAR. Check how the application is actually launched.
2. **Thinking `@ConditionalOnNotWarDeployment` only runs on JARs.** Wrong because an executable WAR running embedded also matches; non-web contexts also match.
3. **Using `@ConditionalOnWebApplication` instead of the WAR condition.** The web annotation only detects a web context; it does not distinguish an external container from an embedded servlet server.
4. **Putting `@ConditionalOnNotWarDeployment` on a servlet-dependent bean without considering CLI/WebFlux.** Combine `@ConditionalOnWebApplication(type = SERVLET)` and classpath conditions when needed.
5. **Evaluating the condition after the server has started and reasoning backward.** Conditions are evaluated during bean registration, not during request handling. `ServletContext` may be created after that point in an embedded deployment.
6. **Forgetting to register the library's auto-configuration.** A missing bean may be because the class was not imported rather than the annotation making the wrong decision.
7. **Trying to simulate WAR by changing `server.port` or `spring.main.web-application-type`.** These properties do not create a traditional external-container deployment.
8. **Testing the WAR branch with a plain context that has no servlet context.** To simulate the WAR branch, supply a `ServletContext` to a `WebApplicationContext` **before** conditions are processed, or run an integration test inside an external servlet container.

To find the root cause at runtime, enable `--debug` when starting Spring Boot and read the **Condition Evaluation Report**. Look for `OnWarDeploymentCondition`, the matched/unmatched sections, and excluded configurations. For libraries, also verify that the auto-configuration name is listed in `AutoConfiguration.imports`.

## 8. Practice Questions

**Q1.** An executable WAR runs via `java -jar demo.war` with embedded Tomcat. Does `@ConditionalOnWarDeployment` match?

**Answer:** No. This is an embedded deployment, even though the artifact is a WAR.

**Q2.** A servlet application is started by an external Tomcat after deploying `demo.war`. Which annotation matches?

**Answer:** `@ConditionalOnWarDeployment`. The `@ConditionalOnNotWarDeployment` branch does not match.

**Q3.** A program uses only a Spring ApplicationContext with no servlet web server. Does `@ConditionalOnNotWarDeployment` match?

**Answer:** Yes. “Not a traditional WAR” includes non-web contexts too; this annotation does not restrict itself to servlet scope.

**Q4.** Can `@ConditionalOnWarDeployment` be replaced with `@ConditionalOnWebApplication(type = SERVLET)` to detect an external Tomcat?

**Answer:** No. A servlet web application can run with either an embedded server or a traditional WAR. The two conditions answer different questions.

**Q5.** Why can you not determine the WAR branch by looking at the artifact name `app.war`?

**Answer:** Because the same executable WAR can be deployed into an external servlet container or run directly with an embedded server; the startup method determines which branch applies.

## 9. Takeaways to Apply

- **`@ConditionalOnWarDeployment`** is for configurations valid only when the application is a **traditional WAR deployed into an external servlet container**.
- **`@ConditionalOnNotWarDeployment`** is for configurations valid only when the application is **not** in traditional WAR mode; this includes embedded deployments, directly executed executable WARs, and non-web contexts.
- The condition is decided while building the `ApplicationContext`, not based on file extension and not changing per request.
- Choose the appropriate annotation scope on a class or bean; combine with `@ConditionalOnWebApplication` if the logic specifically requires a servlet web application.
- Verify both branches with tests, then verify on a real servlet container if the application is intended for traditional WAR deployment.

### References

- [Spring Boot 3.3 Javadoc — ConditionalOnWarDeployment](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWarDeployment.html).
- [Spring Boot 3.3 Javadoc — ConditionalOnNotWarDeployment](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnNotWarDeployment.html).
- [Spring Boot 3.3 Reference — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html).
- [Spring Boot Reference — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html).
