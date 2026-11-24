# @ConditionalOnJndi and JNDI Lookup Infrastructure Conditions in Spring Boot

## 1. Lesson Objectives

In Spring Boot Auto-configuration, not every bean should be registered in every deployment environment. An application running on an **application server** may use resources exposed by the server via **JNDI** such as a `DataSource`, integration resources, or environment entries. That same application running on a standalone JVM may **lack the corresponding JNDI naming service**.

`@ConditionalOnJndi` in the `org.springframework.boot.autoconfigure.condition` package is used to **activate a configuration or bean only when JNDI is available**, and optionally verify one or more specific JNDI locations.

After this lesson, the learner should be able to distinguish:
- Having `InitialContext` infrastructure for JNDI lookup;
- Being able to look up **a specific JNDI name**;
- Being able to look up **at least one of several names**;
- A matching condition vs. the resource actually being compatible and working properly when used.

The first three cases are what `@ConditionalOnJndi` supports directly. The last case still requires verification of the data type, configuration, and actual service behavior.

## 2. What Is JNDI and Why Does It Affect Auto-Configuration?

**JNDI (Java Naming and Directory Interface)** is Java's standard API for finding objects/resources by name in a naming system. Two core components:

1. **`javax.naming.InitialContext`**: the starting point for looking up a name.
2. **`lookup(name)`**: the operation asking the JNDI system to return the object bound to that name.

Conceptual example:

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;

class JndiLookupExample {
    static Object findResource() throws NamingException {
        InitialContext context = new InitialContext();
        try {
            return context.lookup("java:comp/env/jdbc/OrdersDS");
        }
        finally {
            context.close();
        }
    }
}
~~~

This is an **illustrative method snippet**, not a program with `main`. It only runs successfully when the environment provides a JNDI system and binds the name `java:comp/env/jdbc/OrdersDS`.

`java:comp/env` is typically the **environment naming context** in a container-backed Java application environment. It is a **JNDI name**, not a file path, HTTP URL, Spring bean name, or `application.properties` key.

Package name note: on **Java 17 / Spring Boot 3.x**, the standard JNDI API remains **`javax.naming.*`** in Java's `java.naming` module. Do not change it to `jakarta.naming.*` merely because the project uses Jakarta Servlet or Jakarta Persistence.

The JNDI system is backed by a **naming service provider / InitialContextFactory**, container, or runtime configuration. Creating `new InitialContext()` does not guarantee `lookup` will work: some implementations only detect a missing provider when an operation is actually invoked.

## 3. Exact Contract of @ConditionalOnJndi

The annotation can be placed on a configuration **class** or a **`@Bean` method**:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;

// Check JNDI infrastructure only.
@ConditionalOnJndi

// Check one specific location.
@ConditionalOnJndi("java:comp/env/jdbc/OrdersDS")

// Check MULTIPLE locations: only ONE location needs to exist.
@ConditionalOnJndi({
    "java:comp/env/jdbc/OrdersDS",
    "java:comp/env/jdbc/ArchiveDS"
})
~~~

**The three declarations above are three independent options**; do not place all three on the same method/class. The annotation definition has the attribute **`String[] value() default {}`**.

According to the Spring Boot Javadoc:
- **Without `value`** (`@ConditionalOnJndi` or `@ConditionalOnJndi()`): the condition relies on the **presence of a usable JNDI `InitialContext`**.
- **One name**: requires JNDI to be available and **that name to be resolvable via lookup**.
- **Multiple names**: requires JNDI to be available and **at least one name to be resolvable**; the names have an **OR** relationship, not AND.

This is a common point of confusion: `@ConditionalOnJndi({"nameA", "nameB"})` **does not require both names to exist**. It differs from `@ConditionalOnProperty(name={"a","b"})`, where multiple properties in the same annotation must all satisfy the condition.

`@ConditionalOnJndi` does not have `name`, `prefix`, `havingValue`, or `matchIfMissing` like property-based conditional annotations. Its value is a **JNDI name**, not a configuration value for string comparison.

## 4. Decision Table: When Does It Match?

Suppose the code checks `java:comp/env/app/cache` and `java:comp/env/app/queue`.

| `InitialContext` infrastructure available | Lookup `cache` | Lookup `queue` | `@ConditionalOnJndi` (unnamed) | `@ConditionalOnJndi(".../cache")` | `@ConditionalOnJndi({".../cache",".../queue"})` |
| --- | --- | --- | --- | --- | --- |
| No | No | No | **No match** | **No match** | **No match** |
| Yes | No | No | **Match** | No match | No match |
| Yes | Yes | No | **Match** | **Match** | **Match** |
| Yes | No | Yes | **Match** | No match | **Match** |
| Yes | Yes | Yes | **Match** | **Match** | **Match** |

The "Yes/No" columns in the table refer to the **JNDI lookup result at the time the condition is evaluated**, not merely a name declared on paper. If a system denies a lookup due to configuration or access permissions, that name cannot simply be assumed usable.

**Examples:**
- An application has a working `InitialContext` but does not bind `jdbc/OrdersDS`: `@ConditionalOnJndi` may match, while `@ConditionalOnJndi("java:comp/env/jdbc/OrdersDS")` does not match.
- The server binds `jdbc/ArchiveDS` but not `jdbc/OrdersDS`: the condition with the two-name array will **match** because ArchiveDS is present.
- A standalone JAR with no JNDI provider or corresponding environment naming context: the condition typically **does not match**.

Do not assume that a "web application" definitely has JNDI, or that a "CLI application" can never have JNDI. The condition depends on the **actual naming infrastructure at runtime**, not directly on Servlet/WebFlux or the application's packaging type.

## 5. Runnable Spring Boot Example: Creating a Bean Only When a JNDI Resource Exists

Suppose the project already has **Java 17+**, `spring-boot-starter`, and the Spring Boot Maven plugin (supporting `spring-boot:run`). Create **`src/main/java/example/JndiFeatureApplication.java`**:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringBootApplication(proxyBeanMethods = false)
@Import(JndiFeatureApplication.JndiFeatureConfiguration.class)
public class JndiFeatureApplication {

    public static void main(String[] args) {
        SpringApplication.run(JndiFeatureApplication.class, args);
    }

    @Bean
    CommandLineRunner showDecision(ApplicationContext context) {
        return args -> System.out.println(
                "JNDI_FEATURE_REGISTERED="
                        + context.containsBean("jndiFeature"));
    }

    @Configuration(proxyBeanMethods = false)
    static class JndiFeatureConfiguration {

        @Bean
        @ConditionalOnJndi("java:comp/env/app/feature")
        FeatureMarker jndiFeature() {
            return new FeatureMarker("JNDI resource detected");
        }
    }

    record FeatureMarker(String description) {
    }
}
~~~

**Explanation:**
1. `@Import` ensures the `JndiFeatureConfiguration` class is processed.
2. The `jndiFeature()` method only creates the bean when `java:comp/env/app/feature` can be looked up.
3. `CommandLineRunner` prints whether the application registered the bean.

Run command in the project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

**Environment-dependent observed output:** if the naming context/name above is absent, the printed line is:

~~~text
JNDI_FEATURE_REGISTERED=false
~~~

If the environment provides an `InitialContext` and `java:comp/env/app/feature` resolves successfully, the result is:

~~~text
JNDI_FEATURE_REGISTERED=true
~~~

These are **two conditional outcomes**, not a claim that every machine will always print `false` or `true`. The startup command may also print Spring Boot/Maven logs.

**Limitation of the example:** `FeatureMarker` is a symbolic bean. The code only demonstrates **conditional bean registration**; in a real system, if the bean must use the JNDI object itself, you must perform the lookup and check the object's type, as shown in the next section.

### Why place the condition directly on @Bean?

In this example only `jndiFeature` requires the JNDI resource. If `@ConditionalOnJndi` were placed on the entire `JndiFeatureConfiguration`, **every bean in the class** would be governed by that condition. Placing it on the method limits the scope of impact.

For a custom **starter/library**, you can use `@AutoConfiguration` instead of `@Configuration`, and register the configuration class name in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. That file serves library auto-configuration discovery; the application example above uses `@Import` directly and does not need an imports file.

## 6. Real-World Application Example: Container-Managed JNDI DataSource

A Java EE/Jakarta EE environment or servlet container may register a `javax.sql.DataSource` at:

~~~text
java:comp/env/jdbc/OrdersDS
~~~

When the application runs in that infrastructure, the configuration can create the integration bean only when that location exists:

~~~java
// Illustrative snippet inside a Spring Boot configuration class.
import javax.sql.DataSource;

import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;
import org.springframework.context.annotation.Bean;
import org.springframework.jndi.JndiDataSourceLookup;

@Bean
@ConditionalOnJndi("java:comp/env/jdbc/OrdersDS")
DataSource ordersDataSource() {
    return new JndiDataSourceLookup()
            .getDataSource("java:comp/env/jdbc/OrdersDS");
}
~~~

**Key points to understand:**
- First, the condition verifies that the JNDI location can be looked up.
- When `ordersDataSource()` executes, `JndiDataSourceLookup` retrieves the object from the naming service and expects it to be a **DataSource**.
- A successful lookup at condition evaluation time **does not guarantee** database queries will succeed: the resource could change, connections could expire, credentials could be wrong, or the database could be unavailable.
- If the JNDI object is not of type `DataSource`, an error may occur during bean instantiation; the annotation is not a complete type-validation check.

For applications that only need a standard JNDI DataSource configuration, Spring Boot provides `spring.datasource.jndi-name` in supported versions/integration setups. Before writing your own `DataSource` `@Bean`, inspect your project version's existing DataSource auto-configuration to avoid bean conflicts or unintentionally replacing defaults.

**Server-side resource setup** depends on the server (Tomcat, WildFly, WebLogic, etc.), naming context scope, and deployment descriptors. Adding the string `java:comp/env/jdbc/OrdersDS` to `application.properties` **does not create** a JNDI binding on the server. Bind the resource in the naming service/container first, then point the application to it.

## 7. Multiple JNDI Locations: OR and Handling Candidates

The annotation:

~~~java
@ConditionalOnJndi({
    "java:comp/env/jdbc/PrimaryDS",
    "java:comp/env/jdbc/LegacyDS"
})
~~~

matches if **at least one** of the two names can be looked up. However, **the annotation does not return which name matched** and has no "auto-pick DataSource" capability. Example of a flawed assumption:

~~~java
// ILLUSTRATIVE SNIPPET WITH A DESIGN FLAW:
@Bean
@ConditionalOnJndi({
    "java:comp/env/jdbc/PrimaryDS",
    "java:comp/env/jdbc/LegacyDS"
})
DataSource badDataSource() {
    // Wrong: only LegacyDS might exist, in which case looking up PrimaryDS still fails.
    return new JndiDataSourceLookup()
            .getDataSource("java:comp/env/jdbc/PrimaryDS");
}
~~~

**Better design:** if the application must support two JNDI names, try the names in priority order inside the bean creation logic, or define separate configurations for each naming contract. Do not rely on the annotation's name list as an automatic fallback mechanism.

If business logic requires **both** resources to exist simultaneously, a single annotation with a `value` array **does not perform an AND operation**. You can split into multiple beans/configurations governed by appropriate conditions, or build a custom `Condition` that looks up both names; check annotation combination rules for your version before applying.

## 8. Proactive Testing with ApplicationContextRunner and a Mock Naming Service

Testing `@ConditionalOnJndi` is usually harder than testing `@ConditionalOnProperty`, because the condition **depends on the runtime naming service state**, not just Spring `PropertySource`s. Setting `app.jndi.enabled=true` in `application.yml` **will not make the condition match**.

One way to build a fixture in **JUnit 5 + Spring Boot 3.x / Java 17+** is installing a simple `InitialContextFactory` for the test scope. The sample below uses a **mock JNDI `Context` via dynamic proxy**: only `java:comp/env/app/present` and its parent contexts are returned; other names throw `NameNotFoundException`.

Create **`src/test/java/example/JndiConditionTests.java`**. The project requires `spring-boot-starter-test`.

~~~java
package example;

import java.lang.reflect.Proxy;
import java.util.Hashtable;

import javax.naming.Context;
import javax.naming.NameNotFoundException;
import javax.naming.OperationNotSupportedException;
import javax.naming.spi.InitialContextFactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJndi;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

public class JndiConditionTests {

    public static class InMemoryContextFactory
            implements InitialContextFactory {

        @Override
        public Context getInitialContext(Hashtable<?, ?> environment) {
            return (Context) Proxy.newProxyInstance(
                    JndiConditionTests.class.getClassLoader(),
                    new Class<?>[] {Context.class},
                    (proxy, method, args) -> {
                        if (method.getName().equals("lookup")) {
                            String name = String.valueOf(args[0]);

                            if (name.equals("java:comp")
                                    || name.equals("java:comp/env")) {
                                return proxy;
                            }
                            if (name.equals(
                                    "java:comp/env/app/present")) {
                                return "bound-value";
                            }
                            throw new NameNotFoundException(name);
                        }
                        if (method.getName().equals("close")) {
                            return null;
                        }
                        if (method.getName().equals("getEnvironment")) {
                            return new Hashtable<>();
                        }
                        throw new OperationNotSupportedException(
                                method.getName());
                    });
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class JndiConditions {

        @Bean
        @ConditionalOnJndi
        String anyContext() {
            return "context-available";
        }

        @Bean
        @ConditionalOnJndi("java:comp/env/app/present")
        String presentName() {
            return "present";
        }

        @Bean
        @ConditionalOnJndi("java:comp/env/app/missing")
        String missingName() {
            return "missing";
        }

        @Bean
        @ConditionalOnJndi({
                "java:comp/env/app/missing",
                "java:comp/env/app/present"
        })
        String oneOfTwo() {
            return "one-of-two";
        }
    }

    @Test
    void namedAndUnnamedJndiConditions() {
        // Mutates a JVM-global property:
        // do not run in parallel with other tests using JNDI.
        String key = Context.INITIAL_CONTEXT_FACTORY;
        String oldValue = System.getProperty(key);

        try {
            System.setProperty(
                    key, InMemoryContextFactory.class.getName());

            new ApplicationContextRunner()
                    .withUserConfiguration(JndiConditions.class)
                    .run(context -> {
                        assertThat(context).hasBean("anyContext");
                        assertThat(context).hasBean("presentName");
                        assertThat(context).doesNotHaveBean("missingName");
                        assertThat(context).hasBean("oneOfTwo");
                    });
        }
        finally {
            if (oldValue == null) {
                System.clearProperty(key);
            }
            else {
                System.setProperty(key, oldValue);
            }
        }
    }
}
~~~

Run:

~~~bash
./mvnw test -Dtest=JndiConditionTests
~~~

PowerShell:

~~~powershell
.\mvnw.cmd test -Dtest=JndiConditionTests
~~~

**Expected result:** one test passes when the mock JNDI provider is used and no other test interferes with global JNDI state. The assertions verify: infrastructure is available; the present name matches; the missing name does not match; the two-name array matches when one name is present.

**Fixture limitations:** it serves to demonstrate lookup conditions and **does not implement the full JNDI API**. The dynamic context only supports a few methods; do not use it as a real server. Because `Context.INITIAL_CONTEXT_FACTORY` is a **JVM-wide system property**, restore it in `finally` and avoid running in parallel with other tests that modify the provider. Some servers/test frameworks configure the naming service differently; in those cases use a dedicated container fixture or integration tests in a production-like environment.

If you only want to observe real application behavior, you can add an **integration** test running in a real JNDI runtime and compare bean presence/absence. Separate that test from standalone unit tests to avoid depending on the developer's local machine.

## 9. What @ConditionalOnJndi Does Not Guarantee

1. **Does not check the type of the returned object.** A name could return a `String`, a custom object, or a `DataSource`. Validate the type when retrieving the actual object.
2. **Does not create or configure the naming service.** If the container has not bound the name, declaring the annotation does not make the resource appear.
3. **Does not wait for external resources to become fully ready.** A JNDI lookup may succeed while the subsequent database/JMS connection still fails.
4. **Does not turn the condition into a dynamic runtime switch.** The condition is evaluated when Spring processes configurations and registers beans; a JNDI name appearing after context initialization typically will not cause a skipped bean to be created automatically.
5. **Has no AND operator across multiple names in `value`.** The list only needs one name, fitting scenarios that accept alternative names.
6. **Is not identical to having `javax.naming` on the classpath.** Having the JNDI API in the JDK does not imply a provider or resolvable naming environment exists.
7. **Is not equivalent to whether the application has a web server.** `@ConditionalOnWebApplication` checks the web application type; `@ConditionalOnJndi` checks naming infrastructure/lookup.
8. **Does not guarantee startup succeeds.** A bean can still throw errors in its constructor or other dependencies even when the condition matches.

### When should conditions be combined?

You may need to add `@ConditionalOnClass` if the used library is an optional dependency, `@ConditionalOnMissingBean` to let users define a replacement bean, or `@ConditionalOnProperty` if you want an additional feature toggle switch.

Example:

~~~java
// Illustrative snippet: MyJndiAdapter is an application-defined type.
@Bean
@ConditionalOnJndi("java:comp/env/app/feature")
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "enabled",
        havingValue = "true")
MyJndiAdapter myJndiAdapter() {
    return new MyJndiAdapter();
}
~~~

When combining `@Conditional...` annotations on the same method, **all conditions there must match**. Both the JNDI location and the `app.integration.enabled=true` property are required. This snippet is not a standalone Java program: `MyJndiAdapter` and the `@Bean` method location must be defined in the project.

## 10. Diagnosing When Expected Beans Are Missing

**Step 1 — Check the effective JNDI name.** Record the exact full name (e.g. `java:comp/env/jdbc/OrdersDS`) in the container/runtime, including dots, letter casing, and namespace. Do not assume `jdbc/OrdersDS` and `java:comp/env/jdbc/OrdersDS` are always equivalent across all naming providers.

**Step 2 — Test direct lookup in the same runtime.** Use `InitialContext.lookup(...)` or container-provided tools. Check JNDI exceptions such as `NoInitialContextException` and `NameNotFoundException`. Test directly in the deployment JVM/environment to avoid confusing your local machine's provider with the server's provider.

**Step 3 — Inspect Spring Boot's condition report.** Enable the `--debug` flag on startup:

~~~bash
java -jar target/my-application.jar --debug
~~~

Replace the JAR name with your project artifact. Spring Boot can print the **Condition Evaluation Report**, including the result of `OnJndiCondition`. If using Actuator with the corresponding endpoint enabled/exposed, `/actuator/conditions` can help inspect why configurations matched or did not match. Avoid exposing diagnostic endpoints publicly if the environment does not need them.

**Step 4 — Evaluate annotation scope accurately.** Placing on a configuration class controls the entire contents of the class, whereas placing on an individual `@Bean` method controls only that method.

**Step 5 — Check causes after a match.** If logs show the condition matched yet the bean still fails, inspect the stack trace during bean instantiation and check the resource type, connectivity, or injection; do not assume the annotation itself malfunctioned.

## 11. Comparison with Other Environment Conditions

| Annotation | What is checked | Example |
| --- | --- | --- |
| `@ConditionalOnJndi` | `InitialContext` infrastructure, optional resolvable JNDI name(s) | Container binds `java:comp/env/jdbc/OrdersDS` |
| `@ConditionalOnProperty` | Configuration value in Spring `Environment` | `app.feature.enabled=true` |
| `@ConditionalOnResource` | Presence of a resource at a Spring-understood location | `classpath:feature.properties` |
| `@ConditionalOnClass` | Specific class is on the classpath | Optional JDBC/JMS library |
| `@ConditionalOnBean` | Spring BeanFactory already has a matching bean | `DataSource` registered as a bean |
| `@ConditionalOnWebApplication` | Application is detected as a web application | Servlet or reactive context |

A `DataSource` existing **in JNDI** does not mean a Spring `DataSource` bean already exists. They belong to two different lookup systems. Spring can create a bean from a JNDI resource, but only after appropriate configuration/auto-configuration.

## 12. Common Mistakes and How to Avoid Them

| Misunderstanding or misconfiguration | Consequence | Fix |
| --- | --- | --- |
| Thinking `@ConditionalOnJndi({"A","B"})` is an AND operation | Bean is created when only one name exists | Remember OR semantics; write a custom condition if both A and B are mandatory |
| Using the unnamed annotation to check a specific resource | Condition matches when naming context exists even without the resource | Specify one or more names in `value` |
| Assuming having `javax.naming.InitialContext` means a naming server exists | Wrong environment and failed lookups | Test a real lookup using the same provider/runtime |
| Declaring `application.properties` and assuming JNDI gets bound | Lookup fails | Bind the resource in the container/naming provider |
| Using OR across multiple names while method always looks up the first name | Condition matches but bean creation fails if only the second name exists | Implement proper fallback lookup logic |
| Confusing `javax.naming` with `jakarta.naming` | Java code fails to compile | Use the standard `javax.naming` JNDI package |
| Writing unit tests relying on the test machine's JNDI | Tests are flaky between CI and laptops | Use an isolated naming fixture and manage JVM state |
| Thinking a matching condition means database connections work | Startup/query errors after the condition has already matched | Check object type, connectivity, and health checks separately |

## 13. Self-Assessment Questions

**1.** When does `@ConditionalOnJndi` without any passed names match?

**Answer:** When available `InitialContext` JNDI infrastructure exists per Spring Boot's check; no specific name specified by the annotation author is required.

**2.** A naming context exists, `java:comp/env/A` does not exist, but `java:comp/env/B` exists. Does `@ConditionalOnJndi({"java:comp/env/A","java:comp/env/B"})` match?

**Answer:** Yes. The name list uses **OR** semantics: only one location needs to be resolvable.

**3.** If the condition matches on JNDI name `jdbc/OrdersDS`, is the database connection guaranteed to work?

**Answer:** No. The condition does not verify connection opening, permissions, or database health; test those separately.

**4.** Why might a Boot app inside Tomcat match, while the same JAR run standalone does not match?

**Answer:** JNDI infrastructure and bindings can be provided by the external container to apps deployed inside it, whereas a standalone JVM lacks that configuration.

**5.** If you need both a JNDI name and `app.integration.enabled=true`, what should you do?

**Answer:** Combine `@ConditionalOnJndi("...")` and `@ConditionalOnProperty(..., havingValue="true")` on the same configuration or bean; both conditions must match.

## 14. Official References

- Spring Boot Javadoc — `ConditionalOnJndi` (describes `InitialContext` and the "one of which must exist" rule): https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnJndi.html
- Spring Boot Reference — Creating Your Own Auto-configuration / Testing Your Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Java SE API — `javax.naming.InitialContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/InitialContext.html
- Java SE API — `javax.naming.spi.InitialContextFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/InitialContextFactory.html
