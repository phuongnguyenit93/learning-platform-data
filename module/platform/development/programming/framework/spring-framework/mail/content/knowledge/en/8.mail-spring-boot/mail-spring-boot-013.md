# Checking auto-configuration conditions when a bean does not appear

## 1. Symptom: Spring Mail was added, yet JavaMailSender cannot be injected

In a **Spring Boot** application using **Spring Framework Mail**, email-sending code usually injects **JavaMailSender**:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Use mailSender to send notifications...
}
~~~

If the application starts up yet Spring cannot create the bean, the logs may contain the error:

~~~text
Parameter 0 of constructor in ...NotificationService required
a bean of type 'org.springframework.mail.javamail.JavaMailSender'
that could not be found.
~~~

This message only describes **the failure point during dependency injection**: Spring needed a bean of the right type and could not find it. It **does not assert** that the cause is "the library is not installed", nor does it mean the SMTP server is refusing connections. To resolve it, you must inspect **auto-configuration conditions**, **classpath**, **configuration properties**, **existing beans**, and **the context being initialized**.

In Spring Boot, **auto-configuration** is the mechanism for automatically registering beans based on conditions that can be checked at runtime. It is not a guarantee that "just adding the starter guarantees you get a JavaMailSender".

### Kinds of situations to distinguish

| Symptom | Initial meaning | Investigation direction |
|---|---|---|
| No JavaMailSender bean, application fails on injection | No bean has been registered with the required type | Bean-creation conditions, configuration, custom beans, test context |
| MailSender bean exists, but no JavaMailSender | There is an implementation of the parent interface, yet it does not satisfy the MIME API | Inspect custom beans blocking auto-config |
| JavaMailSender exists, yet sending mail fails | The bean was created; the error happens when connecting/sending | SMTP host, TLS, AUTH, network, quota, recipient address |
| Application fails right when creating the mail sender | Conditions may have matched, yet configuration/initialization failed | Root cause exception, JNDI, binding, bean factory |
| Error occurs only in tests | Tests create a different context from real runtime | Test slice, mocks, @ActiveProfiles, @Import |
| Bean exists, yet injection is ambiguous | Multiple beans of the same type, Spring cannot pick | @Primary, @Qualifier, bean configuration |

**Having no bean** differs from **having a bean yet being unable to connect to SMTP**. Opening a connection, logging in, and actually delivering mail are steps after the Spring context has finished choosing the bean.

## 2. Under what conditions is Spring Mail auto-configuration activated?

In Spring Boot 3.x, the mechanism usually involves **MailSenderAutoConfiguration** in package **org.springframework.boot.autoconfigure.mail**. When using **spring-boot-starter-mail**, the libraries required for Spring Mail and Jakarta Mail are usually brought onto the classpath via dependencies.

General condition model:

~~~mermaid
flowchart TD
    A[Spring Boot evaluates MailSenderAutoConfiguration] --> B{Are required Mail/Jakarta Mail classes on classpath?}
    B -- No --> X[Do not apply mail configuration]
    B -- Yes --> C{Does a MailSender bean already exist?}
    C -- Yes --> Y[Back off: prefer bean provided by application]
    C -- No --> D{Is spring.mail.host or suitable spring.mail.jndi-name present?}
    D -- No --> Z[Do not create sender due to missing configuration condition]
    D -- Yes --> E[Select host-based or JNDI configuration]
    E --> F[Initialize JavaMailSenderImpl]
    F --> G[JavaMailSender can be injected]
~~~

The diagram illustrates the common processing path of Spring Boot 3.3.x; specific annotations and sub-branches should be cross-checked against the application's **actual Spring Boot version**. Fundamental conditions usually include:

1. **The classpath has the required types**: Spring Mail components, Jakarta Mail, and mail classes referenced by auto-configuration.
2. **No MailSender bean exists yet**: Spring Boot does not create a default sender to override a sender already registered by the application or another library.
3. **A mail-sending configuration source exists**: usually **spring.mail.host**, or a valid **spring.mail.jndi-name** when using a mail session via JNDI.
4. **Auto-configuration is not excluded**: Boot configuration is not excluded by annotation or property.
5. **The context actually loads auto-configuration**: for instance a normal Spring Boot application; a test slice or minimal context may not load that configuration.

In Spring Boot's auto-configuration structure, **MailSenderAutoConfiguration** uses conditional annotations, enables **MailProperties** binding, and imports configuration branches for host/port or JNDI. You can inspect **MailSenderPropertiesConfiguration** and **MailSenderJndiConfiguration** when you need to understand which branch was selected.

### Distinguishing @ConditionalOnClass and @ConditionalOnMissingBean

**@ConditionalOnClass** checks for the presence of a class on the classpath, such as types in Spring Mail or Jakarta Mail. A missing library directly causes the condition not to match.

**@ConditionalOnMissingBean** checks beans already registered in the context. If a suitable bean already exists, Boot actively **backs off**: it no longer registers the default bean. This is usually intentional behavior, not a Spring bug.

With Spring Mail, backing off on **MailSender** has an important consequence: a custom bean that implements only **MailSender** without implementing **JavaMailSender** can prevent the default JavaMailSender from being created, while services require injecting **JavaMailSender** specifically.

## 3. Check dependencies and classpath first

With Spring Boot and Gradle, the common way to enable mail support is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

The **starter** brings the dependencies that support sending mail. It is not a JavaMailSender bean directly and does not include a preconfigured SMTP host or credentials to send real email.

Some classpath mistakes:

- Having only **spring-context-support** yet missing the required Jakarta Mail implementation.
- Adding the dependency to **testImplementation** instead of runtime **implementation**, causing the real application not to see the classes.
- Transitively excluding a required Jakarta Mail or activation dependency in the build configuration.
- Mixing legacy **javax.mail** with Spring Boot 3.x's **jakarta.mail**, making imports or object types incompatible.
- A multi-module project failing to declare the mail dependency for the module that actually runs; the dependency sits in another module and is not on the application's runtime classpath.

Spring Boot 3.x uses the **jakarta.mail.\*** namespace. For example **jakarta.mail.internet.MimeMessage** is used together with JavaMailSender. Legacy code importing **javax.mail.internet.MimeMessage** cannot simply rename the package arbitrarily if the dependency still belongs to the old generation; you need to align the libraries, Spring version, and API usage.

When checking the classpath, rely on the **dependency graph of the runnable module**, not just seeing a dependency line in another file. Example Gradle commands for reference:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-mail --configuration runtimeClasspath
~~~

Project names, runtime classpath, and command syntax depend on the Gradle layout; in a multi-module project, select the right project. With Maven you can use **mvn dependency:tree**. These are commands for developers to use during diagnosis, not part of automatic bean creation.

If the condition report says **@ConditionalOnClass did not find required class**, identify the missing class and fix the actual dependency. Adding a **spring.mail.host** property will not fix a missing-class error.

## 4. Check spring.mail.host and spring.mail.jndi-name

When sending mail via an SMTP host, a basic configuration:

~~~yaml
# application.yml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

**spring.mail.host** is an important property for activating the ordinary SMTP configuration branch. The **username**, **password**, **port**, and **properties.mail.smtp.\*** properties adjust how connections/sends work; they **do not automatically substitute** for the host condition when using the host-based branch.

An easily confused configuration example:

~~~yaml
spring:
  mail:
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

If **spring.mail.host** is missing from every effective configuration source and JNDI is also not used, Spring Boot may **not register the mail sender** because the starting condition is missing. Then a JavaMailSender injection error can occur even though the starter dependency is completely correct.

### Using a JNDI mail session

In some application servers, a JavaMail Session is supplied via **JNDI**. Configuration may be:

~~~yaml
spring:
  mail:
    jndi-name: mail/Session
~~~

When choosing JNDI, Session lookup depends on the environment providing the JNDI resource. An ordinary standalone Spring Boot application does not automatically have a **mail/Session** resource. If JNDI is configured without a JNDI resource, bean initialization may fail; that case must be distinguished from **auto-configuration not matching at all**.

**Do not configure both host and JNDI together arbitrarily.** Choose a clear Session management method; when using JNDI, the corresponding settings on the Session provided by the application server may govern behavior instead of Spring Boot's SMTP properties.

### Common mistakes in writing properties

| Configuration | Problem |
|---|---|
| **spring.mail.hostname** | Not the standard Spring Boot key for host; needs **spring.mail.host** |
| **mail.host** at root level | Not bound by MailProperties into **spring.mail.host** |
| **spring.mail.smtp.host** | Not the same as Spring Boot's **spring.mail.host** property |
| Setting only **spring.mail.port** | Not enough to activate the host-based branch |
| Setting only **spring.mail.username** | Not enough to activate the host-based branch |
| Putting **spring.mail.host** in an inactive profile | Property is not present in the starting context |
| Setting env var in a different terminal/container | Java process may not receive the value |

You can write SMTP properties directly under **spring.mail.properties** for Jakarta Mail, yet you must distinguish **properties Boot uses to decide whether to create the bean** from **properties passed to JavaMail once the bean exists**. Setting **spring.mail.properties.mail.smtp.host** does not reliably substitute for **spring.mail.host** in auto-configuration conditions.

## 5. Active profiles and effective property sources

Suppose the file:

~~~yaml
# application-dev.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
~~~

If the application does not activate the **dev** profile, those values are not necessarily loaded. Run the application:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

or set the environment variable **SPRING_PROFILES_ACTIVE=dev** in the process's environment.

In production, the host configuration may be injected via **SPRING_MAIL_HOST** or a placeholder bound to a secret/config source. What must be verified is **the final value seen by Spring Environment**, not "the file already has a host line".

Some sources of mismatch:

- The active profile is not what was intended.
- The configuration file lies outside the classpath or was not packaged.
- The file or environment variable on the container host was not passed into the application container.
- A property source with higher priority overrides the value from YAML.
- A test has **@TestPropertySource**, **@ActiveProfiles**, **@DynamicPropertySource**, or separate config differing from runtime.
- Another profile introduces **spring.mail.jndi-name**, causing a different configuration branch to be selected than expected.

You can log information about **active profiles** at startup; if using **Actuator env/configprops**, restrict access permissions and avoid exposing secrets. Spring Boot has mechanisms to mask or restrict displaying sensitive values, yet security configuration remains the operator's responsibility.

## 6. Custom beans that make auto-configuration actively back off

This is the most confusing case: dependencies and **spring.mail.host** are both right, yet Spring Boot still does not create **JavaMailSenderImpl**.

Example of an application declaring its own:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

@Configuration
public class CustomMailConfig {
    @Bean
    MailSender customMailSender() {
        return new MailSender() {
            @Override
            public void send(SimpleMailMessage message) {
                // Illustrative fake/no-op.
            }

            @Override
            public void send(SimpleMailMessage... messages) {
                // Illustrative fake/no-op.
            }
        };
    }
}
~~~

Because the **customMailSender** bean has type **MailSender**, the **@ConditionalOnMissingBean(MailSender.class)** condition may no longer be satisfied. Then Spring Boot **does not create the default JavaMailSender**. Yet the service requires the subtype **JavaMailSender**, so injection fails.

~~~text
CustomMailConfig
  |
  v
MailSender bean exists
  |
  v
MailSenderAutoConfiguration back off
  |
  v
No JavaMailSender bean
  |
  v
JavaMailSender injection fails
~~~

A complete custom **JavaMailSender** can also make auto-configuration back off. In that case, if services inject JavaMailSender successfully, there is no problem: Boot is respecting the application's configuration.

### How to fix according to actual need

If you only want the default SMTP sender, **remove or limit the scope of the custom bean** blocking it. If you want a custom mail sender, register a bean of exact type **JavaMailSender** and provide full behavior needed for MIME and transport, instead of implementing only MailSender when services need JavaMailSender.

In tests, custom fakes should only be registered in the **test context** via **@TestConfiguration**, mock beans, or an explicit test profile. Avoid letting a fake/no-op MailSender get scanned into production accidentally and make Boot back off.

### When there are multiple beans of the same type

If there are multiple application-defined JavaMailSenders, Spring may report **NoUniqueBeanDefinitionException** when injecting one bean without a qualifier. This error is completely different from "bean could not be found". Select one sender explicitly using **@Qualifier**, **@Primary**, or a routing gateway, rather than trying to enable auto-configuration to create a third bean.
## 7. Reading the Condition Evaluation Report to see why the bean does not appear

The **Condition Evaluation Report** is the most important source for understanding whether auto-configuration was applied. Spring Boot evaluates conditions such as **@ConditionalOnClass**, **@ConditionalOnBean**, **@ConditionalOnMissingBean**, **@ConditionalOnProperty**, or custom conditions; the report describes which configurations **matched** and **did not match**, along with reasons.

During diagnosis, you can start the application with the debug flag:

~~~bash
java -jar app.jar --debug
~~~

Or configuration:

~~~yaml
debug: true
~~~

When debug is enabled, Spring Boot can write an auto-configuration conditions report to the logs, even when startup hits an error preventing the application from initializing completely. Specific section names and wording may vary across Spring Boot versions, so look for **MailSenderAutoConfiguration**, **MailSenderPropertiesConfiguration**, and **MailSenderJndiConfiguration** rather than expecting fixed wording.

An **illustrative** report snippet, not standard output to match character-for-character:

~~~text
Negative matches:

MailSenderAutoConfiguration:
   Did not match:
      - No spring.mail.host or spring.mail.jndi-name property found
~~~

In this situation, missing host/JNDI is the primary cause. Adding a password or enabling **mail.smtp.auth** does not satisfy the condition stated in the report.

Another situation:

~~~text
Negative matches:

MailSenderAutoConfiguration:
   Did not match:
      - @ConditionalOnMissingBean found bean of type MailSender:
        customMailSender
~~~

Meaning: Boot sees a registered MailSender bean and **actively refrains from creating a default sender**. Hunting for missing libraries will not resolve this situation.

Another example:

~~~text
Negative matches:

MailSenderAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class
        ...
~~~

Then check the **runtime classpath**, starter, dependency exclusions, or library versions.

### When the report shows a positive match yet injection still fails

**Positive match** does not mean the bean was successfully created and ready. For instance:

- The auto-configuration class matched, yet the bean-creating **sub-branch** did not match.
- Configuration selected the JNDI branch, yet no mail Session was found in JNDI.
- The bean factory method threw an exception during initialization.
- The bean was created in a **different context** from the context containing the service needing injection.
- The actual bean has type **MailSender**, yet the service asks for **JavaMailSender**.
- A **BeanDefinition** exists, yet fails during the instantiation phase.

Therefore when viewing the report, combine it with the **root stack trace**, bean names in the context, and dependency error messages. Do not stop at a single "MailSenderAutoConfiguration matched" line.

## 8. Using Spring Boot Actuator to observe beans and conditions

Once the application has started and has Spring Boot Actuator, several endpoints can help observe configuration:

| Endpoint | Information provided | Question to answer |
|---|---|---|
| **/actuator/conditions** | Auto-configuration condition evaluation results | Was MailSenderAutoConfiguration applied or excluded? |
| **/actuator/beans** | Beans present in the application context | Is there a JavaMailSender bean? Which context is it in? |
| **/actuator/configprops** | Bound configuration properties | Does MailProperties have suitable values? |
| **/actuator/env** | Properties and configuration sources | Where is spring.mail.host coming from? |

Not every endpoint is exposed over HTTP by default. You can configure appropriate exposure in **development or administrative** environments:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions,beans,configprops,env
~~~

**Do not open configuration endpoints publicly in production.** They can reveal bean structure, property names, internal endpoints, or sensitive metadata even when secret values are sanitized. Use authentication/authorization, network restriction, and proper display configuration; do not copy secret data into logs/tickets when investigating.

If the application context **fails to start**, Actuator HTTP is not ready yet. In that case prioritize the **--debug** flag, stack trace, or checking beans with a test/context that can start partially.

### Condition report in a test

In a test using Spring Boot, you can collect condition results directly from the test context. Example reading the report from BeanFactory provided the context initialized:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootTest
class MailConditionsInspectionTest {

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void inspectConditions() {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        report.getConditionAndOutcomesBySource()
                .forEach((source, outcomes) -> {
                    if (source.contains("MailSender")) {
                        System.out.println(source + " -> " + outcomes);
                    }
                });
    }
}
~~~

This snippet is for **observation during diagnosis**, not a stable assertion for CI: printing the **ConditionAndOutcomes** object may not be the optimal presentation, and internal source names may change across Spring Boot versions. When wanting to verify constraints durably, assert **bean presence/absence** with an explicitly configured context instead of comparing entire log strings.

## 9. Do not confuse an unregistered bean with a failed SMTP connection

**JavaMailSenderImpl** can usually be created from host, port, username, password, and JavaMail properties **without performing any send or network connection yet**. Therefore:

~~~text
Spring context creates JavaMailSenderImpl
        |
        v
Bean appears in ApplicationContext
        |
        v
Service injects JavaMailSender successfully
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP connection / STARTTLS / AUTH / send mail
~~~

If the SMTP password is wrong or the server does not respond, the bean normally still exists; **send()** is what throws connection, authentication, or mail-sending exceptions.

Spring Boot also has the **spring.mail.test-connection** option. When enabled, Boot may proactively check the mail connection during startup. If the SMTP server cannot be reached, the application may **fail to start** even though bean-creation conditions matched.

Example:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    test-connection: true
~~~

This property helps check the communication path at startup, yet carries a trade-off: a temporary SMTP outage can make the application unavailable even though other business functions do not depend on mail. **test-connection** is not a mandatory condition to create JavaMailSender, nor does it guarantee future emails will be delivered successfully.

| Observed error | Likely area |
|---|---|
| **No qualifying bean of type JavaMailSender** | Bean not created/not present in context |
| **MailAuthenticationException** on send | Credentials, token, or SMTP AUTH policy |
| **MailSendException** on send | Connection, SMTP transaction, or one/more messages failed |
| **ConnectException / timeout** during test-connection | Host/port/network/server/TLS at startup time |
| **NamingException** when using JNDI | Cannot find JNDI Session/resource |
| **BeanCreationException** | Bean factory initialization error; inspect nested cause |

If the console prints both **"No bean found"** and a complex stack trace, identify the **first root exception** and corresponding context conditions. Subsequent dependency errors may only be consequences.

## 10. Auto-configuration is excluded or not loaded

Even when classpath and properties are valid, an application may intentionally turn off MailSenderAutoConfiguration.

Example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration;

@SpringBootApplication(exclude = MailSenderAutoConfiguration.class)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Or via a configuration property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration
~~~

When auto-configuration is excluded, Boot does not create the sender through that configuration, regardless of declaring **spring.mail.host**. If the application still needs to send mail, it must register a suitable sender through another configuration, or remove the exclusion once requirements are properly confirmed.

Besides direct exclusion, there are other situations:

- The application does not run through normal **Spring Boot auto-configuration**, for instance manually creating a plain Spring context without enabling required auto-configs.
- Tests use **@ContextConfiguration** with a restricted set of @Configurations that do not include auto-config.
- A test slice such as **@WebMvcTest** creates only beans serving the MVC slice, not equivalent to the full application context.
- A module or library has its own Spring configuration yet is not a Boot application context that loaded auto-config.
- Custom bootstrap configuration or multiple parent/child contexts place the sender where services cannot see it.

For tests, **do not enable all auto-configuration just to fix a missing mock error** if the test only needs to verify a controller/service. When a mail gateway is needed for unit tests, supply an appropriate mock or fake. When verifying that Boot actually creates the sender, use a test context with the required auto-configuration and an explicit property set.

## 11. Bean missing only in tests: identify the right test context type

The application running normally while tests report a missing JavaMailSender is a common case. The cause usually does not lie in SMTP, but because **the test builds a different ApplicationContext**.

### @SpringBootTest

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = "spring.mail.host=127.0.0.1")
@ActiveProfiles("test")
class MailSenderContextTest {

    @Autowired
    JavaMailSender mailSender;

    @Test
    void contextProvidesMailSender() {
        org.assertj.core.api.Assertions.assertThat(mailSender)
                .isNotNull();
    }
}
~~~

This test observes the **context creating the sender**, without actively sending mail. Since JavaMailSenderImpl normally does not open a connection until sending, a dummy host can be used to check the bean if **spring.mail.test-connection** is not enabled in an effective config source. If the test profile has another custom **MailSender**, the default bean may still back off.

### @WebMvcTest and slice tests

For example a controller injects a service, and the service injects JavaMailSender:

~~~text
@WebMvcTest
   |
   +-- MVC controller
          |
          v
       Mail service
          |
          v
       JavaMailSender (may not be created in the slice)
~~~

**@WebMvcTest** does not automatically create every dependency of the application. When testing a controller that does not require real mail sending, you usually mock the **service** or **mail gateway** used by the controller. Example per Spring Boot 3.3:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(NotificationController.class)
class NotificationControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    NotificationService notificationService;

    @Test
    void example() {
        // Use mvc to test the controller's HTTP behavior.
    }
}
~~~

The example assumes **NotificationController** and **NotificationService** belong to the application. It illustrates placing the mock at the **boundary matching the test's goal**; controller tests do not need SMTP.

**@MockBean** is the annotation used in Spring Boot 3.3. Across other Spring/Boot generations, context mocking mechanisms may change; use the API matching the project's version.

### When wanting to mock JavaMailSender directly

In a SpringBootTest used to verify a service that builds email content, you can register:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class NotificationServiceTest {
    @MockBean
    private JavaMailSender mailSender;

    @Autowired
    private NotificationService service;

    // Verify the service calls mailSender with the expected message.
}
~~~

When **@MockBean JavaMailSender** is registered, auto-configuration may back off because the context **already has a sender bean**. This is normal: the mock is used for the test, and no real JavaMailSenderImpl needs to be added. If you inspect the condition report, you will see the missing-bean condition differs from runtime **without the mock**.

### Another situation: mocking the wrong parent interface

If the test mocks only **MailSender** while the service injects **JavaMailSender**, auto-configuration may not create the default JavaMailSender because a MailSender already exists. Then the test still lacks a JavaMailSender bean. Mock **the exact interface the service requires** or refactor the service to use the appropriate interface.
## 12. Checking each condition with ApplicationContextRunner

When you need to understand whether auto-configuration works under a specific set of properties, **ApplicationContextRunner** from Spring Boot Test is a useful tool. It creates a **small, controlled ApplicationContext**, letting you enable the auto-configuration to observe and check the resulting beans.

Simple example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.mail.javamail.JavaMailSender;

class MailSenderAutoConfigurationConditionsTest {
    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MailSenderAutoConfiguration.class));

    @Test
    void createsJavaMailSenderWhenHostIsConfigured() {
        contextRunner
                .withPropertyValues("spring.mail.host=localhost")
                .run(context ->
                        assertThat(context).hasSingleBean(
                                JavaMailSender.class));
    }

    @Test
    void doesNotCreateSenderWithoutHostOrJndi() {
        contextRunner
                .run(context ->
                        assertThat(context).doesNotHaveBean(
                                JavaMailSender.class));
    }
}
~~~

The example assumes **spring-boot-starter-mail** and **spring-boot-test** are on the test runtime classpath, with no additional config source pre-creating a sender. That is why the two cases can yield different results. When the application customizes **MailSender** or uses JNDI, add the corresponding configuration to the context.

If you want to view condition details when using the runner, you can attach **ConditionEvaluationReportLoggingListener** or read the report from BeanFactory inside the callback. This helps find the cause at the exact moment Spring makes its decision, without running real SMTP.

### Example of registering a custom bean and observing back off

Suppose a test configuration has a **MailSender** bean yet no **JavaMailSender**. Using the same runner and adding the custom bean configuration, you can verify that BeanFactory contains the application-provided MailSender yet does not create the default JavaMailSenderImpl. It is important to check the **exact bean type**, because:

~~~text
MailSender is the parent interface
          ^
          |
JavaMailSender extends MailSender
          ^
          |
JavaMailSenderImpl implements JavaMailSender
~~~

A JavaMailSender bean can always be used as a MailSender, yet a custom MailSender implementation does not necessarily support MimeMessage. Spring Boot cannot guess that the application wants to automatically turn a custom MailSender into a JavaMailSender.

There is no need to write tests just to count conditions if the report already explains the cause clearly. ApplicationContextRunner is most useful when you are **developing library configurations**, need to check many property/bean combinations, or want to ensure custom auto-configuration does not accidentally override user beans.

## 13. Diagnostic workflow from error message to cause

For a **No qualifying bean of type JavaMailSender** error, you can go from symptom to cause using a decision tree:

~~~mermaid
flowchart TD
    A[Cannot inject JavaMailSender] --> B{Which Spring Boot context is running?}
    B -->|Test slice / restricted context| C[Check loaded auto-config and mock right type]
    B -->|Full Boot application| D[Enable condition report]
    D --> E{Was MailSenderAutoConfiguration applied?}
    E -->|No due to classpath| F[Check starter / runtime dependencies]
    E -->|No due to property| G[Check effective spring.mail.host or jndi-name]
    E -->|No due to existing bean| H[Check custom MailSender bean]
    E -->|Excluded| I[Remove exclude if default is desired]
    E -->|Matched| J{Is JavaMailSender bean in context?}
    J -->|Yes| K[Check qualifier / injection point / context]
    J -->|No| L[Check config branch, bean factory exception, JNDI]
~~~

A short practical sequence:

1. **Read the full stack trace.** Determine whether the real error is no bean, non-unique bean, bean creation failure, or an SMTP connection error.
2. **Identify the ApplicationContext**: a full Boot application, @SpringBootTest, @WebMvcTest, or a manually constructed Spring context.
3. **Enable the Condition Evaluation Report** and find **MailSenderAutoConfiguration** along with its sub-branches.
4. **If classpath is missing**, inspect dependencies of the runnable module and use the right Jakarta Mail namespace for the Spring Boot version.
5. **If a property is missing**, check host or JNDI in the **effective Environment**, active profiles, and high-precedence config sources.
6. **If an existing MailSender exists**, locate the custom bean, its actual type, and the service's needs.
7. **If auto-config is excluded**, verify whether it was intentional.
8. **If auto-config matched**, inspect bean definitions, initialization errors, and different contexts before concluding.
9. **Only after having the bean**, move on to diagnosing STARTTLS, SMTP AUTH, host/port, and test sends if sending does not yet work.

### Situation A: adding starter yet forgetting host

~~~yaml
spring:
  mail:
    port: 587
    username: mailer
    password: some-example-value
~~~

If there is no host or JNDI in another config source, MailSenderAutoConfiguration may not be activated. Fix by supplying **spring.mail.host** in the right profile/config source and protecting credentials with secrets; do not create a custom JavaMailSenderImpl just to bypass this condition.

### Situation B: host declared only in the prod profile

~~~yaml
# application-prod.yml
spring:
  mail:
    host: smtp.example.com
~~~

Tests running the **test** profile will not automatically pick up host from the **prod** profile. Choose the objective clearly: if only testing business logic, use a mock/fake; if testing auto-configuration, supply a test **spring.mail.host** for the context. Do not activate prod in unit tests just to get a bean.

### Situation C: mocking MailSender while service needs JavaMailSender

~~~java
@MockBean
private org.springframework.mail.MailSender mailSender;
~~~

The service injects **JavaMailSender**, so there is still no matching bean. Create a mock of exact type **JavaMailSender** or change the service's interface if only basic MailSender functionality is needed. The report will help spot back off due to an existing MailSender.

### Situation D: bean created yet server refuses login

~~~text
org.springframework.mail.MailAuthenticationException:
Authentication failed
~~~

This is not a missing JavaMailSender error. Check SMTP AUTH, credentials, TLS, port, sending permissions, locked account, or expired token. Changing auto-configuration does not resolve the essence of an authentication error.

### Situation E: bean is right yet controller test still fails

A @WebMvcTest loading only the web slice and missing service dependencies will report its own error. If the controller needs **NotificationService**, the test can mock **NotificationService**. Adding an SMTP host to @WebMvcTest does not necessarily solve the slice test's missing service bean issue.

## 14. When do you need to create a JavaMailSender bean yourself?

Default auto-configuration suffices for many applications: just the mail starter, **spring.mail.host**, and related properties. However, an application may need **multiple SMTP accounts**, specialized senders, or dynamic transport selection, in which case manual bean configuration can be suitable.

Example creating an explicit JavaMailSenderImpl:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class ExplicitMailSenderConfig {
    @Bean
    JavaMailSender applicationMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername("example-user");
        sender.setPassword("example-only-placeholder");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        return sender;
    }
}
~~~

The example above uses dummy values to focus on the API. In a real application, host and credentials must be taken from **externalized configuration/secret store**, not hardcoded. Once this **JavaMailSender** bean is registered, Boot usually backs off and services can inject the application-supplied sender.

Manual configuration carries greater responsibility:

- Set appropriate host, port, timeouts, TLS, authentication, and charset.
- Protect secrets and support rotating credentials per operational processes.
- If there are multiple senders, use qualifiers or an explicit routing gateway.
- Ensure the self-created bean is not registered in the wrong profile, e.g. a fake sender from tests ending up in production.
- Preserve mail-sending semantics and transport error handling.

**There is no need to create a custom sender merely because spring.mail.host is missing.** In many cases, fixing the effective configuration conditions and checking the report is the cleaner fix with less code.

## 15. Logging and observing bean state safely

When investigating a production system, useful data includes:

~~~text
activeProfiles=prod
mailSenderBeanPresent=true
mailSenderImplementation=JavaMailSenderImpl
mailConfigurationSource=runtime-environment
smtpHostCategory=production-provider
mailConnectionCheck=not-run
~~~

This is an illustrative format, not a built-in Spring log. Some fields may be unnecessary or sensitive depending on organizational policy. Do not log **passwords**, **access tokens**, entire **JavaMailProperties**, or **MimeMessages** containing private data to diagnose a bean.

If you need to know the final configuration, read **/actuator/configprops** or **/actuator/env** in a protected admin channel and check masked values. When discussing with colleagues, you can share **match/negative match conditions, class names, active profiles, and property names**, omitting secrets and recipient addresses.

SMTP metrics such as send error rate, send duration, timeout counts, or delivered/bounced events should be tracked **after** the bean exists. They reflect transport health, not conditional auto-configuration evaluation.

## 16. Principles to remember when JavaMailSender does not appear

| Question | Evidence to find | Right fix direction |
|---|---|---|
| Is the mail library on the runtime classpath? | Dependency graph, ConditionalOnClass error | Add starter/dependency to the right module |
| Is there a host or JNDI? | Environment, MailProperties, condition report | Declare spring.mail.host or jndi-name properly |
| Is there a prior custom MailSender bean? | Bean list, ConditionalOnMissingBean report | Remove/limit custom bean or provide suitable JavaMailSender |
| Is MailSenderAutoConfiguration excluded? | Annotations and spring.autoconfigure.exclude | Remove exclude if Boot should create the bean |
| Is a test slice or narrow context used? | @WebMvcTest, @ContextConfiguration, test configuration | Mock right dependency or load needed context |
| Auto-config matched yet bean still missing? | Nested exception, JNDI/host branch, bean factory | Fix bean creation and context errors |
| Bean exists yet SMTP errors? | Send/test-connection stack trace, SMTP response | Check TLS, AUTH, network, host, provider policy |

**Core workflow:** verify the running context → read the **Condition Evaluation Report** → cross-check **classpath**, **spring.mail.host/JNDI**, **existing MailSender bean**, **exclusions and test context** → verify the **JavaMailSender** bean type in ApplicationContext. Only after having the bean should you move on to checking SMTP connectivity and protocol.

Non-matching conditions usually have a **specific reason** recorded by Spring Boot. Relying on that reason to fix the **root configuration or dependency**, instead of reflexively adding a manual JavaMailSenderImpl, will keep a Spring Framework Mail application easy to control, easy to test, and consistent across environments.
