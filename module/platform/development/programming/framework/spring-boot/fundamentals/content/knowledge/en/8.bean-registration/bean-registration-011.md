# Checking Registered Beans Using Tools or Context Queries

When working with Spring Boot, a class may carry **@Component**, **@Service**, **@Repository**, or be declared via **@Bean**, yet that alone is not enough to conclude the corresponding object exists in the Spring container. The component might sit outside the scan scope, its configuration might not have been imported, a profile or condition might not match, or a bean factory method might have failed during initialization.

Therefore, after declaring a bean, you need to know how to **check whether the bean is registered**, **what its bean name is**, **what type it has**, and **whether it has been instantiated successfully**.

Spring provides several ways to inspect this:

- Querying **ApplicationContext** and BeanFactory APIs in code or a debugger.
- Inspecting **BeanDefinition** metadata to understand registered bean definitions.
- Using **Spring Boot Actuator** and the **/actuator/beans** endpoint to inspect beans in a running application.
- Using the conditions report to see why auto-configurations applied or were skipped.
- Writing tests with a Spring context to verify a bean exists under a specific configuration.

Each approach answers a slightly different question. Distinguish between **bean definition**, **bean instance**, **bean currently being created**, and **Java object manually created with `new`** to avoid misreading results.

## 1. First, Know What You Want to Check

Suppose you have a service:

~~~java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

And a controller:

~~~java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "friend") String name) {
        return greetingService.greet(name);
    }
}
~~~

If both classes lie within component scan scope and the context starts successfully, Spring registers the corresponding beans. Yet asking "Does `GreetingService` exist yet?" can mean several different checks:

| Question | What to inspect |
|---|---|
| Is a bean definition registered? | Bean name and metadata in BeanFactory. |
| Can the context find the bean by name? | **containsBean("greetingService")**. |
| Are there any beans matching a type? | **getBeanNamesForType(...)** or **getBeansOfType(...)**. |
| Has the bean been instantiated successfully? | Query the instance or observe startup/runtime. |
| Is the bean a singleton? | Scope in BeanDefinition or corresponding scope API. |
| Which configuration did the bean come from? | Resource/metadata of BeanDefinition, conditions report, debugger, or Actuator endpoint. |
| Why did auto-configuration not create the bean? | Condition evaluation report and configuration conditions. |

Do not lump all these questions into a single "does the bean exist?" question, because different APIs can give different answers.

## 2. ApplicationContext Is the Most Common Query Entry Point

**ApplicationContext** is the central interface of the Spring IoC container. It inherits bean lookup capabilities from BeanFactory and adds application services such as events, resources, and message sources.

Inside a Spring-managed component, you can inject `ApplicationContext`:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInspector {
    private final ApplicationContext context;

    public BeanInspector(ApplicationContext context) {
        this.context = context;
    }
}
~~~

Through **context**, you can check beans by name, type, or aliases, or retrieve instances. In ordinary business code, avoid overusing context queries as a substitute for constructor injection; this example illustrates diagnostic tooling and is useful for infrastructure or troubleshooting.

### 2.1. Checking a Bean by Name with `containsBean`

~~~java
boolean exists = context.containsBean("greetingService");
System.out.println("greetingService exists = " + exists);
~~~

If the result is **true**, the context can find a bean by that name. Remember:

- The default bean name for **GreetingService** is typically **greetingService** (first letter lowercased), following standard component naming rules.
- Bean names can be set explicitly via **@Component("...")**, **@Service("...")**, or the **@Bean** method name.
- **containsBean** can also check parent contexts in a context hierarchy.
- **true** does not prove the bean has already been instantiated cleanly or that all its methods work properly.

Example of a custom-named bean:

~~~java
@Service("primaryGreetingService")
public class GreetingService {
    // ...
}
~~~

Then you check:

~~~java
context.containsBean("primaryGreetingService");
~~~

The name **greetingService** is no longer valid when the class is registered as **primaryGreetingService** with no matching alias.

### 2.2. Retrieving a Bean by Name or Type

~~~java
GreetingService service =
        context.getBean("greetingService", GreetingService.class);

GreetingService byType =
        context.getBean(GreetingService.class);
~~~

These two lookups differ in selection criteria:

- **getBean(name, type)** requests a bean by name while verifying type compatibility.
- **getBean(type)** requests a bean matching by type.

If no matching bean exists, Spring throws an exception such as **NoSuchBeanDefinitionException**. If multiple beans match the type and no single candidate can be resolved, you may hit **NoUniqueBeanDefinitionException**.

**`getBean()` can trigger bean instantiation.** Therefore, if your goal is solely checking bean definitions or registered names, avoid calling an instance-fetching lookup and concluding the bean had already been created beforehand.

### 2.3. Retrieving All Beans of a Given Type

~~~java
import java.util.Map;

Map<String, GreetingService> services =
        context.getBeansOfType(GreetingService.class);

services.forEach((name, service) ->
        System.out.println(name + " -> " + service.getClass().getName())
);
~~~

The result is a map from **bean name** to compatible instance. This is helpful when an interface has multiple implementations or you want to inspect every bean in a family.

Example:

~~~java
public interface NotificationSender {
    void send(String message);
}
~~~

~~~java
@Component("emailSender")
class EmailSender implements NotificationSender {
    public void send(String message) {
        // Send email.
    }
}
~~~

~~~java
@Component("smsSender")
class SmsSender implements NotificationSender {
    public void send(String message) {
        // Send SMS.
    }
}
~~~

Query:

~~~java
Map<String, NotificationSender> senders =
        context.getBeansOfType(NotificationSender.class);
~~~

can return both **emailSender** and **smsSender** if both are registered and obtainable.

Note that fetching the instance map can initialize eligible lazy beans. If you only need the list of names, use the type-based name query API instead of requesting all objects.

### 2.4. Listing Bean Names by Type

`ApplicationContext` also exposes queries via **ListableBeanFactory**:

~~~java
String[] names =
        context.getBeanNamesForType(GreetingService.class);

for (String name : names) {
    System.out.println(name);
}
~~~

This is a concise way to see which bean names the context lists for a type. Depending on the API and query flags, type determination can involve `FactoryBean`s or early factory initialization; when avoiding eager initialization matters, use the appropriate `BeanFactory`/`ListableBeanFactory` overload and understand its parameters.

Not every listing method behaves identically regarding **parent contexts**, lazy beans, and `FactoryBean`s. When diagnosing accurately, know which exact API you are calling instead of assuming all of them just read one static list.

## 3. Distinguishing `BeanDefinition` from Bean Instance

This is a crucial distinction when inspecting beans.

**BeanDefinition** is metadata describing how Spring manages a bean: bean class or factory method, scope, lazy flag, dependencies, and other configuration attributes. **Bean instance** is the concrete object created from that definition or registered through an equivalent mechanism.

Example:

~~~java
@Configuration
public class AppConfiguration {
    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

When the configuration is processed, Spring registers the bean definition. If the bean is a default eager singleton, its instance is normally created during context refresh. If the bean is lazy, the definition can exist while no instance has been created yet.

### 3.1. Listing Bean Definition Names

Given a context implementing **ConfigurableApplicationContext**, you can obtain its BeanFactory:

~~~java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public void printDefinitions(ConfigurableApplicationContext context) {
    ConfigurableListableBeanFactory beanFactory =
            context.getBeanFactory();

    for (String name : beanFactory.getBeanDefinitionNames()) {
        System.out.println(name);
    }
}
~~~

**getBeanDefinitionNames()** lists **bean definitions registered in the current BeanFactory**. It is not a list of every Java object alive in the JVM.

An object created with:

~~~java
GreetingService manual = new GreetingService();
~~~

does not appear in this list automatically, because **`new`** does not register a `BeanDefinition` into the context.

### 3.2. Inspecting a Definition by Name

~~~java
boolean hasDefinition =
        beanFactory.containsBeanDefinition("greetingService");

if (hasDefinition) {
    var definition =
            beanFactory.getBeanDefinition("greetingService");

    System.out.println("Scope: " + definition.getScope());
    System.out.println("Lazy: " + definition.isLazyInit());
    System.out.println("Bean class: " + definition.getBeanClassName());
    System.out.println("Resource: " + definition.getResourceDescription());
}
~~~

This information helps clarify:

- Is the bean definition registered in the current factory?
- What scope is declared?
- Is the bean marked for lazy initialization?
- Is there a class name or resource description tracing back to the configuration source?

**getBeanClassName() can return null**, for example when a bean is defined by a factory method or when the class is not stored directly in the definition. Do not treat null as proof the bean does not exist.

### 3.3. `containsBean` and `containsBeanDefinition` Differ

| API | Meaning |
|---|---|
| **ApplicationContext.containsBean(name)** | Checks whether the context has a bean by name; may check parent contexts. |
| **BeanFactory.containsBean(name)** | Checks for a bean by name in the factory and may include ancestors per BeanFactory contract. |
| **BeanDefinitionRegistry.containsBeanDefinition(name)** | Checks whether a definition is registered directly in that registry/factory. |
| **ConfigurableListableBeanFactory.getBeanDefinitionNames()** | Lists definitions belonging to the current factory. |

A bean may be provided by a **parent context**, causing `containsBean` to return `true` while the child factory's definition list lacks that name. Conversely, a singleton can be registered directly without a standard `BeanDefinition`; in that case, definition checks and instance checks can differ.

## 4. Checking Whether a Singleton Instance Has Been Created

With a **DefaultListableBeanFactory** or factory implementing **ConfigurableListableBeanFactory**, you can inspect the singleton registry via suitable APIs. For example:

~~~java
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public void inspectSingleton(
        ConfigurableListableBeanFactory beanFactory,
        String beanName) {

    System.out.println(
            "Has definition: "
                    + beanFactory.containsBeanDefinition(beanName)
    );
    System.out.println(
            "Has singleton instance: "
                    + beanFactory.containsSingleton(beanName)
    );
}
~~~

Meaning:

- **containsBeanDefinition** indicates whether a bean definition exists in the current factory.
- **containsSingleton** indicates whether a singleton instance is already registered in the singleton registry under that name.

Do not use **containsSingleton=false** to conclude a bean does not exist. The bean might:

- Have a definition yet remain uninstantiated due to lazy initialization.
- Have prototype scope, which is not stored in the singleton registry.
- Come from a parent context.
- Be provided by another mechanism.

A single bean lookup can trigger creation of a lazy singleton, flipping `containsSingleton` from `false` to `true`. Thus, inspecting can alter state if you call an API that instantiates the bean.

### 4.1. Listing Singleton Names

A concrete factory can expose the list of registered singletons:

~~~java
String[] singletonNames = beanFactory.getSingletonNames();

for (String name : singletonNames) {
    System.out.println(name);
}
~~~

This lists singleton instances recorded by the registry—not all definitions, and not beans across all scopes. For prototype beans, each retrieval can create a new instance without appearing in the singleton list.

## 5. Checking Aliases, Scope, and Bean Type

### 5.1. Bean Name and Aliases

A bean can be accessed under multiple names via aliases. Example:

~~~java
@Configuration
public class GreetingConfiguration {
    @Bean({"greetingService", "primaryGreeting"})
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

**greetingService** is the method-derived bean name; **primaryGreeting** is an additional alias. When inspecting, distinguish aliases from two independent bean instances.

You can query:

~~~java
String[] aliases = context.getAliases("greetingService");
for (String alias : aliases) {
    System.out.println(alias);
}
~~~

If you look up by alias, you still receive the same bean. Do not count aliases as separate instances.

### 5.2. Checking Scope

With `BeanFactory`:

~~~java
String scope = beanFactory.getMergedBeanDefinition("greetingService")
        .getScope();

System.out.println(scope);
~~~

When scope is empty in a standard `BeanDefinition`, Spring uses **singleton** as the default scope. For special bean/factory types, check actual metadata and behavior instead of assuming every definition has a non-empty scope string.

Scope answers **under what rule the container supplies instances**. It does not confirm whether the bean has been instantiated yet.

### 5.3. Checking Bean Type

~~~java
Class<?> type = context.getType("greetingService");
System.out.println(type);
~~~

**getType** returns the type the container predicts for the bean. With factory methods, **FactoryBean**s, proxies, or lazy configuration, the predicted type may not always match the final runtime class of the target object.

If you have already retrieved the instance:

~~~java
Object bean = context.getBean("greetingService");
System.out.println(bean.getClass().getName());
~~~

then you observe the runtime class of the returned reference. If the bean is wrapped in an AOP proxy, the class may be a proxy class rather than the implementation class.

## 6. Using Spring Boot Actuator to View Running Beans

When you need to inspect a running application, **Spring Boot Actuator** provides the **beans** endpoint to inspect beans in the `ApplicationContext`.

Add the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

In Spring Boot 3.x, web endpoints typically need to be exposed explicitly. Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans
~~~

Once the application runs, the default endpoint path is typically:

~~~http
GET /actuator/beans
~~~

The actual path may differ if the application changes **management.endpoints.web.base-path**, the management port, or context path settings. Access must also be permitted by current security configuration.

### 6.1. What Information Does `/actuator/beans` Provide?

This endpoint presents contexts and beans observable by Actuator, typically including details such as:

- Bean name.
- Aliases.
- Scope.
- Bean type.
- Resource or definition source when available.
- Dependencies of the bean or beans depending on it, when provided.

Exact JSON structure varies by version and configuration; inspect the actual response from your running application instead of hardcoding a schema from a different version's guide.

Illustrative JSON snippet:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "greetingService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.demo.service.GreetingService",
          "resource": "..."
        }
      }
    }
  }
}
~~~

This is illustrative data, not a verbatim response guaranteed across every Spring Boot version. The endpoint can display multiple contexts if the application uses a context hierarchy.

### 6.2. Why Is Actuator Useful?

Actuator is especially convenient when:

- The application runs in an environment where attaching a debugger is difficult.
- You need to see which beans actually appeared in the context after startup.
- You need to check bean names, types, scopes, or definition sources.
- You want to compare differences across local, staging, and production.
- You are investigating a bean added by a starter or library integration.

It answers **which beans the context exposes**, without replacing reading source code or checking bean creation conditions.

### 6.3. The `beans` Endpoint Is Not the `conditions` Endpoint

These two endpoints serve different goals:

| Endpoint | Purpose |
|---|---|
| **/actuator/beans** | View beans and related details across contexts. |
| **/actuator/conditions** | View the condition evaluation report for auto-configurations. |

If `GreetingService` does not appear:

- **beans** confirms whether the bean is present in the context.
- **conditions** can explain whether a related auto-configuration matched or was skipped and why.

A bean registered by **@ComponentScan** may not have an entry in the conditions report like an auto-configuration does. Conversely, the conditions report might show an auto-configuration matched while a `@Bean` method inside had its own condition or failed during instantiation.

### 6.4. Securing Management Endpoints

Bean metadata can expose:

- Internal package and class names.
- Integration, client, or data store names.
- Component structure and dependency relationships.
- Partial details about application configuration.

Therefore, never leave **/actuator/beans** publicly open purely for convenience. In real environments, restrict endpoints via authentication/authorization, an internal management network, or tight exposure settings. Expose only the endpoints you actually need.

For instance, exposing **health** and **beans** only controls which endpoints are published over the web; it **does not set up a complete security policy**. Configure Spring Security or your deployment environment's access controls accordingly.

## 7. Using the Condition Evaluation Report When Beans Come from Auto-Configuration

If a bean is expected from Spring Boot auto-configuration yet is missing from the context, inspect **configuration selection conditions**.

Launch the application with:

~~~bash
java -jar app.jar --debug
~~~

Boot can print the **Condition Evaluation Report** in startup logs. The report typically groups entries into:

- **Positive matches**: conditions that matched.
- **Negative matches**: conditions that did not match and why.
- **Exclusions**: excluded auto-configurations.

Illustrative example:

~~~text
Negative matches:
-----------------
GreetingAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty did not find property 'demo.greeting.enabled'
~~~

Class names and exact phrasing are illustrative. Actual output depends on the auto-configurations, Boot version, and declared conditions.

### 7.1. Reading Condition Results Properly

If the report says **did not match**, read the specific condition:

- **@ConditionalOnClass**: the required class is absent from the inspected classpath.
- **@ConditionalOnProperty**: the property is missing or its value does not match.
- **@ConditionalOnBean**: a required bean did not exist yet at evaluation time.
- **@ConditionalOnMissingBean**: a matching bean already existed, so the default backed off.
- **@ConditionalOnWebApplication**: the current context type does not qualify.

Not every negative match is an error. If your application does not use an optional integration, seeing that auto-configuration skipped is completely normal.

### 7.2. A Positive Match Does Not Prove Bean Creation Succeeded

An auto-configuration class can pass its class-level condition while a **@Bean** method inside has its own condition. Furthermore, a bean factory method can throw an exception during instantiation.

Thus, combine:

1. **Conditions report** to understand conditional matching.
2. **Beans endpoint or ApplicationContext** to confirm the bean was registered/provided.
3. **Startup log / stack trace** to check whether bean creation failed.

## 8. Checking Beans via Tests with a Spring Context

A reliable verification technique is writing tests that start the exact Spring configuration your application uses.

### 8.1. Testing the Full Spring Boot Application Context

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.service.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class GreetingBeanRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void greetingServiceIsRegistered() {
        assertThat(context.containsBean("greetingService")).isTrue();
        assertThat(context.getBeansOfType(GreetingService.class))
                .hasSize(1);
    }
}
~~~

This test verifies that the context started by **@SpringBootTest** contains the bean by name and has exactly one bean matching `GreetingService` in that query.

**@SpringBootTest** usually builds a context using convention-discovered or specified application configuration. It can be heavier than a pure unit test because it initializes many beans and integrations. Use it when your goal is genuinely verifying wiring or context behavior.

### 8.2. Testing a Small Configuration with `ApplicationContextRunner`

When testing auto-configuration without booting the entire application, Spring Boot test supports **ApplicationContextRunner**.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(GreetingAutoConfiguration.class);

    @Test
    void registersGreetingServiceWhenEnabled() {
        contextRunner
                .withPropertyValues("demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                });
    }
}
~~~

This is an example test setup; **spring-boot-starter-test** or appropriate test dependencies are required, and the auto-configuration class and related types must exist in the project.

You can add a test for the disabled case:

~~~java
@Test
void doesNotRegisterGreetingServiceWhenDisabled() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(GreetingService.class);
            });
}
~~~

The strength of `ApplicationContextRunner` is testing a small configuration slice, supplying properties or extra beans, and asserting the outcome without spinning up a full web server.

### 8.3. Testing Component Scan and Bean Registration

To test whether a component is discovered from a package, create a context with **@ComponentScan** configuration or run a test with the application configuration. Tests should reflect the scan packages and profiles the application actually needs.

A unit test calling only:

~~~java
GreetingService service = new GreetingService();
~~~

does not prove **@Service** was scanned or that the bean was registered. It only proves Java can instantiate the object.

## 9. Using the IDE Debugger

When running from IntelliJ IDEA, Eclipse, or VS Code with Java extensions, you can set breakpoints to observe:

- Which `ApplicationContext` is being created.
- Which bean definitions are registered.
- Which constructor or factory method is invoked.
- Which `BeanPostProcessor`s are acting.
- Which bean is injected into a consumer's constructor.
- Whether a reference is the target object or an AOP proxy.

### 9.1. Useful Breakpoints

For a missing-bean error, set breakpoints at:

1. The constructor of the class expecting injection.
2. The configuration class or factory method declaring the bean.
3. Application context startup code if needed.
4. Relevant bean creation/registration code inside the framework once you have narrowed down the investigation.

Do not start by step-debugging the entire Spring Framework. Verify bean name, type, and package scan first; dive deeper into bean creation only if logs and context queries have not explained it yet.

### 9.2. Inspecting the Injected Instance

In a constructor:

~~~java
public GreetingController(GreetingService greetingService) {
    this.greetingService = greetingService;
}
~~~

set a breakpoint to inspect the parameter value. You can examine its runtime class, instance identity, and internal dependencies. If Spring AOP is active, the reference's class may be a proxy; use your debugger's tools to inspect the target class when needed.

## 10. Querying the Context Is Not Searching Every Object in the JVM

The Spring context only knows about beans registered or supplied through container mechanisms. It is not global memory tracking every Java object.

Example:

~~~java
GreetingService managed = context.getBean(GreetingService.class);
GreetingService manual = new GreetingService();
~~~

The **manual** object does not automatically show up in:

~~~java
context.getBeanNamesForType(GreetingService.class);
~~~

unless you take an explicit step to register it as a bean. The context is not responsible for tracking every `new` call in the program.

Conversely, a bean can be created by a factory method where consumer code never sees a `new` call. What matters is the **bean registration path**, not whether a class has an annotation or which constructor created the object.

## 11. Situations That Make Inspection Results Differ

### 11.1. Lazy Bean Not Yet Instantiated

With:

~~~java
@Bean
@org.springframework.context.annotation.Lazy
GreetingService greetingService() {
    return new GreetingService();
}
~~~

a bean definition can exist even before a singleton instance has been created. A query checking only definitions returns yes, while a check for an existing singleton instance returns no. Calling **getBean** can trigger Spring to instantiate it.

### 11.2. Prototype Beans Do Not Sit in the Singleton Registry

~~~java
@Component
@org.springframework.context.annotation.Scope("prototype")
class ReportDraft {
}
~~~

A prototype definition can exist and lookups can create a new object every time. Not seeing the name in the singleton registry does not mean the prototype bean is unregistered.

### 11.3. Parent and Child `ApplicationContext`s

An application can have multiple contexts in a parent/child relationship, such as in certain web setups or multi-context configurations. Beans in the parent can be visible to the child under lookup rules, yet the child's `BeanDefinition` list does not necessarily include the parent's definitions.

When inspecting:

- Identify which context is being queried.
- Check parent relationships if present.
- Distinguish beans declared in the current context from beans inherited from an ancestor.

Actuator can display multiple contexts in the `beans` endpoint response; do not assume the entire application has just one flat bean map.

### 11.4. `FactoryBean`

Spring provides the **FactoryBean<T>** interface allowing a bean factory to produce another object. When looking up a bean by its regular name, the context normally returns the **object produced by the FactoryBean**; the **&** prefix retrieves the `FactoryBean` itself.

Lookup example:

~~~java
Object product = context.getBean("clientFactory");
Object factory = context.getBean("&clientFactory");
~~~

In this example, **clientFactory** is an assumed name of a `FactoryBean`. The two lookups can return two different object types: the product and the factory. Comparing bean names, runtime types, and definitions therefore requires understanding `FactoryBean` mechanics.

### 11.5. Proxied Beans

A proxy-wrapped bean can have a runtime class different from its implementation class. For example, a service with transactions or aspects may be delivered via a JDK dynamic proxy or a class-based proxy depending on configuration.

Therefore:

- **getBeanNamesForType** finds beans based on the type Spring predicts.
- **getBean(name).getClass()** shows the class of the returned reference, which may be a proxy.
- **BeanDefinition** traces back to the declaration.

Do not conclude a bean is wrong or missing just because `getClass()` is not the exact source class you expected.

## 12. Diagnostic Workflow When a Bean Is Not Found

Suppose startup reports:

~~~text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.demo.GreetingService' available
~~~

You can follow this investigation workflow:

### Step 1: Check Expected Bean Type and Name

Verify whether the constructor requests **GreetingService** or another interface. If multiple implementations exist, inspect candidates and qualifiers.

### Step 2: Identify How the Bean Should Be Registered

Does the bean come from:

- **@Component**, **@Service**, **@Repository**, and component scanning?
- **@Bean** in a **@Configuration**?
- **@Import** or a registrar?
- Auto-configuration from a starter?
- A test configuration or specific profile?

Do not search every mechanism blindly at once; identify the intended declaration source first.

### Step 3: Check Component Scan Scope or Imports

If it is a component, check whether the main class's package covers the component's package. If it is a **@Bean**, verify the configuration class is imported or scanned and its conditions match.

### Step 4: Check Profiles and Conditions

Verify active profiles and actual property values. If the bean comes from auto-configuration, read the conditions report to see which configuration did not match or was excluded.

### Step 5: Inspect the Actual Context

Using a debugger, test, or Actuator, check:

- Does the bean name appear?
- Does a definition exist?
- Is there a bean of the same type under another name?
- Does the bean live in a parent context or child context?
- Does bean scope or lazy initialization alter how it shows up?

### Step 6: Read Bean Creation Errors When Definitions Exist Yet Startup Fails

A bean definition may be registered while its constructor or factory method throws an exception during instantiation. Look for **BeanCreationException** and the **Caused by** chain. That is not a case of component scan failing to find the class.

### Step 7: Fix the Registration Source and Re-verify

Fix the scan package, import, property, profile, dependency, or factory method according to the proven root cause. Then re-run the test/context and confirm the bean appears with the expected name, type, and scope.

## 13. Complete Example: Checking a Bean at Multiple Levels

Suppose:

~~~java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

We want to verify whether the service is registered and retrievable.

A diagnostic component:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class StartupBeanReport {
    private final ApplicationContext context;

    public StartupBeanReport(ApplicationContext context) {
        this.context = context;
    }

    public void printGreetingService() {
        String name = "greetingService";

        System.out.println(
                "containsBean = " + context.containsBean(name)
        );

        String[] names =
                context.getBeanNamesForType(GreetingService.class);

        System.out.println(
                "matching type count = " + names.length
        );

        for (String beanName : names) {
            System.out.println("bean name = " + beanName);
        }
    }
}
~~~

If you also want to inspect the `BeanDefinition`:

~~~java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public void printDefinition(ConfigurableApplicationContext context) {
    ConfigurableListableBeanFactory factory = context.getBeanFactory();

    if (factory.containsBeanDefinition("greetingService")) {
        var definition = factory.getBeanDefinition("greetingService");
        System.out.println(definition.getScope());
        System.out.println(definition.isLazyInit());
        System.out.println(definition.getResourceDescription());
    }
}
~~~

These two snippets illustrate two perspectives:

- `ApplicationContext` lookup by name and type.
- `BeanFactory` inspection of bean definitions.

In production apps, avoid logging the entire bean registry on every startup if the list is huge or contains sensitive internal component names. Restrict logging to the specific beans being diagnosed.

## 14. Which Tool Fits Which Goal?

| Goal | Suitable approach | Things to keep in mind |
|---|---|---|
| Check a bean by name in code | **ApplicationContext.containsBean(name)** | May check parent contexts; does not prove instantiation succeeded. |
| Retrieve a bean by type | **getBean(type)** | Throws if missing or if multiple unresolved candidates exist. |
| List bean names by type | **getBeanNamesForType(type)** | Watch out for `FactoryBean`s, lazy beans, and context scope. |
| View bean definitions | **getBeanDefinitionNames()**, **getBeanDefinition(name)** | Current factory only; definition differs from instance. |
| Check already-created singletons | **containsSingleton(name)**, **getSingletonNames()** | Excludes other scopes and ancestor contexts. |
| View running beans in another environment | Actuator **/actuator/beans** | Must be exposed and properly secured. |
| Find why auto-configuration did not match | **--debug**, conditions report, or **/actuator/conditions** | Does not replace verifying bean instances. |
| Test wiring in tests | **@SpringBootTest** | Starts a relatively full context. |
| Test a small auto-configuration | **ApplicationContextRunner** | Requires test dependencies and relevant configuration. |
| Observe constructors/proxies/lifecycle | IDE debugger | Needs matching runtime setup and targeted breakpoints. |

No single tool answers every question. **Picking the tool matching what you want to verify** prevents accidentally instantiating beans or misreading a listing.

## 15. Common Misconceptions

**"Having `@Service` means the bean is definitely registered."**  
No. The class must be scanned or registered via an appropriate mechanism; profiles, conditions, and scan scope can keep it out.

**"`containsBean` returning `true` means the bean has been instantiated cleanly."**  
No. It checks whether a bean can be found by name; lazy beans or on-demand beans may not have been instantiated yet.

**"`getBeanDefinitionNames` lists every object in the JVM."**  
No. It lists bean definitions in the current factory; objects created elsewhere with `new` do not appear.

**"Missing from `getSingletonNames` means the bean does not exist."**  
No. The bean may be lazy, prototype-scoped, in a parent context, or provided differently.

**"An alias is a new bean."**  
No. An alias is an extra name for the same bean identity, not a separate instance.

**"A bean having a runtime class different from its source class means registration is broken."**  
No. The reference may be an AOP proxy or a product returned by a `FactoryBean`.

**"Seeing a bean in the conditions report means it was instantiated successfully."**  
No. The conditions report describes conditional matching; the bean can still fail during creation or have method-level conditions.

**"The Actuator `beans` endpoint is always accessible by default."**  
No. Actuator must be on the classpath, the endpoint must be exposed, and security permissions must allow access. The path can also be customized.

**"Calling `getBean` just to inspect has no side effects."**  
No. Lookups can trigger lazy or factory bean instantiation. If you only want metadata, query the definition instead.

**"A test calling `new Service()` proves component scan works."**  
No. Only a test creating a Spring context verifies container registration and wiring.

## Core Takeaways

To verify whether a bean is registered, first decide **whether you need to know about its definition, name, type, or instance**. **ApplicationContext** supports name/type lookups; **BeanFactory/BeanDefinitionRegistry** inspects metadata; **Actuator `/beans`** observes running applications; the **conditions report** explains auto-configuration decisions; and **Spring context tests** verify wiring under a specific configuration.

A bean definition can exist before an instance is created; a lazy or prototype bean may not appear in the singleton registry; a bean from a parent context may be absent from a child's definition list; and a reference may be a proxy. Understanding these distinctions helps you inspect accurately, diagnose missing-bean errors, and avoid confusing objects created via `new` with Spring-managed beans.
