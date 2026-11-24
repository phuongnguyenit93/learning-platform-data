# Grouping Profiles by Functionality with `spring.profiles.group`

## 1. The problem: many small profiles, hard to activate reliably

A Spring Boot application may need several configuration groups depending on the environment and enabled capabilities:

- **proddb**: database connection configuration used in production.
- **prodmq**: messaging or queue configuration in production.
- **observability**: observability settings such as appropriate log levels and metrics.
- **localdb**: data configuration for developer machines.
- **devtools**: settings intended for the development workflow.

Without a grouping mechanism, every production deployment must remember the entire list:

~~~bash
java -jar app.jar --spring.profiles.active=proddb,prodmq,observability
~~~

Omitting a single profile can leave the application missing required settings or fail to enable an expected set of beans. The list also gets duplicated across multiple places: scripts, CI/CD configs, deployment manifests, and operational runbooks.

**spring.profiles.group** solves this by assigning **a single composite profile name** to multiple related profiles. When that composite name is activated, Spring Boot automatically activates the member profiles.

~~~text
spring.profiles.active=production
               |
               v
      Profile group production
               |
       +-------+--------+
       |       |        |
       v       v        v
     proddb  prodmq  observability
~~~

As a result, operators only need to select **production**, while the application keeps the list of required components in common configuration.

## 2. How does `spring.profiles.group` work?

In Spring Boot 3.3, each group is declared in the form:

~~~text
spring.profiles.group.<group-name> = [profile-1, profile-2, ...]
~~~

Example in **application.yml**:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability
~~~

At startup:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Spring Boot activates the following profiles:

~~~text
production
proddb
prodmq
observability
~~~

**The group name `production` itself is also an active profile.** It is not replaced or removed after group expansion. Consequently, both **application-production.yml** and files like **application-proddb.yml** can be considered.

This is an important difference between a profile group and simple text aliasing. Profile groups activate multiple profiles inside Spring Boot's profile management mechanism; places checking profiles with **@Profile** or **Environment.acceptsProfiles(...)** also observe the activated member profiles.

No custom annotation is needed to define a group. Groups are configured in a valid Spring Boot configuration source, while selection happens via **spring.profiles.active** or the corresponding profile-activation mechanism.

## 3. Declaring groups in `application.yml` and `application.properties`

### 3.1. YAML: readable when there are many members

~~~yaml
spring:
  profiles:
    group:
      production:
        - "proddb"
        - "prodmq"
        - "observability"
      development:
        - "localdb"
        - "console-logs"
~~~

There are two independent groups:

| Group | Member profiles | Purpose |
| --- | --- | --- |
| **production** | **proddb**, **prodmq**, **observability** | Combines configuration groups needed for production deployment |
| **development** | **localdb**, **console-logs** | Combines configuration groups needed during development |

Activating **production** does not automatically activate **development**. When selecting **development**, the application activates **development**, **localdb**, and **console-logs**.

### 3.2. Properties: using list indices

Equivalent example in **application.properties**:

~~~properties
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
spring.profiles.group.production[2]=observability

spring.profiles.group.development[0]=localdb
spring.profiles.group.development[1]=console-logs
~~~

In **.properties**, the **[0]**, **[1]**, **[2]** syntax expresses the order of member list elements. Do not write multiple lines with the same plain key assuming Spring Boot will automatically concatenate them into a list.

Usually you only need to pick one format—YAML or properties—that fits the project. If multiple configuration sources define the same group, the final result also depends on precedence order and list-binding behavior for the applied source; keep group definitions in one consistent place.

## 4. Complete example: one command activates three functional groups

Suppose a Java 21 application uses Spring Boot 3.3 and **spring-boot-starter-web**. We want to demonstrate how a profile group activates different configuration files without depending on a real database or message broker.

Project structure:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/profiles/
    │       ├── ProfileGroupApplication.java
    │       └── ProfileController.java
    └── resources/
        ├── application.yml
        ├── application-production.yml
        ├── application-proddb.yml
        ├── application-prodmq.yml
        └── application-observability.yml
~~~

### 4.1. `application.yml`: declaring the group and defaults

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability

demo:
  environment: general
  database-mode: none
  messaging-mode: none
  metrics-enabled: false
~~~

Here **demo.*** are illustrative properties without connecting a real database or message broker. Default values make changes clearly visible when profiles are activated.

### 4.2. `application-production.yml`: shared configuration for the whole group

~~~yaml
demo:
  environment: production
~~~

Because **production** remains an active profile, **application-production.yml** can be loaded. This file suits values shared across the entire production environment.

### 4.3. `application-proddb.yml`: database slice

~~~yaml
demo:
  database-mode: postgresql
~~~

### 4.4. `application-prodmq.yml`: messaging slice

~~~yaml
demo:
  messaging-mode: rabbitmq
~~~

### 4.5. `application-observability.yml`: observability slice

~~~yaml
demo:
  metrics-enabled: true
~~~

The three files are separated by **functional concern**. They do not need to know the group's name; each file's own profile name is the condition for Spring Boot to load its configuration.

In a real system, the database file might contain **spring.datasource.url** or pool parameters, while the messaging file might contain broker endpoints. Do not put real passwords, tokens, or secret keys into the repository; those values should be supplied by the runtime environment's secrets management mechanism.

### 4.6. An API to view active profiles

**ProfileGroupApplication.java**:

~~~java
package com.example.profiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileGroupApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProfileGroupApplication.class, args);
    }
}
~~~

**ProfileController.java**:

~~~java
package com.example.profiles;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    private final Environment environment;

    public ProfileController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/profiles")
    public Map<String, Object> profiles() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("active", Arrays.asList(environment.getActiveProfiles()));
        result.put("environment",
                environment.getProperty("demo.environment", "unknown"));
        result.put("database",
                environment.getProperty("demo.database-mode", "unknown"));
        result.put("messaging",
                environment.getProperty("demo.messaging-mode", "unknown"));
        result.put("metricsEnabled",
                environment.getProperty("demo.metrics-enabled", Boolean.class, false));
        return result;
    }
}
~~~

The controller reads from **Environment** rather than deciding profiles itself. In real deployments, an API exposing configuration should not be left public; this endpoint is purely a learning example with non-sensitive values.

### 4.7. Build and run

From a project with the Spring Boot Gradle plugin and web starter:

~~~bash
./gradlew bootJar
~~~

Assuming the artifact is named **app.jar**, run:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Then call:

~~~bash
curl http://localhost:8080/profiles
~~~

Illustrative output (JSON field order may vary):

~~~json
{
  "active": [
    "production",
    "proddb",
    "prodmq",
    "observability"
  ],
  "environment": "production",
  "database": "postgresql",
  "messaging": "rabbitmq",
  "metricsEnabled": true
}
~~~

Key observations:

1. The run command specified only one profile: **production**.
2. The group brought in **proddb**, **prodmq**, and **observability**.
3. Spring Boot considered the configuration file matching each active profile.
4. No Java code changes or separate JAR builds were needed for each member group.

If run without active profiles and no other overrides, values can keep their defaults: **general**, **none**, **none**, **false**.

## 5. Groups also activate `@Profile` conditions

Spring Profiles are not only for selecting **application-{profile}.yml**. A **@Component**, **@Configuration**, or **@Bean** can also be bound to a profile condition.

Example of a bean that exists only when **observability** is active:

~~~java
package com.example.profiles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    @Profile("observability")
    public MonitoringMarker monitoringMarker() {
        return new MonitoringMarker("monitoring-enabled");
    }

    public record MonitoringMarker(String value) {
    }
}
~~~

When running **--spring.profiles.active=production**, the group activates **observability**, so the **MonitoringMarker** bean is eligible for registration. When running with an unrelated profile and nothing else activates **observability**, that bean will not be registered.

You can check this using **ApplicationContext.containsBean("monitoringMarker")** in a test or local experiment.

**A helpful distinction:** an **application-observability.yml** file only loads configuration. It does not install dependencies or create beans the project has not declared. To actually enable metrics, messaging, or databases, the application still needs the appropriate dependencies, beans, auto-configuration, and conditions.

## 6. `spring.profiles.group` is not an alias that replaces the profile name

There are two ways people look at this:

~~~text
Misconception:
production is replaced by proddb, prodmq, observability

Actual behavior:
production is active and additionally activates
proddb, prodmq, observability
~~~

For example, if you have:

~~~text
application-production.yml
application-proddb.yml
application-prodmq.yml
application-observability.yml
~~~

then all of them can be evaluated according to the active profiles, following the corresponding Config Data precedence order.

Therefore, you can put production-wide settings in **application-production.yml**, and each concern's settings in its own file.

Do not duplicate the exact same group of settings in **application-production.yml** and copy them again into **application-proddb.yml**. A cleaner model is **each file owns one slice** with very few overlapping keys.

## 7. Comparing `group` with `active`, `include`, and `default`

Spring Boot has several profile-related properties serving different purposes.

| Mechanism | Meaning | Example |
| --- | --- | --- |
| **spring.profiles.active** | Selects profiles to activate explicitly | **production** |
| **spring.profiles.group** | Declares member profiles that accompany a profile group | **production → proddb, prodmq** |
| **spring.profiles.include** | Adds included profiles alongside explicitly active ones | **common, local** |
| **spring.profiles.default** | Selects the default profile when no active profile is set | **dev** or **none** |

### 7.1. `spring.profiles.active` chooses the starting point

Example:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

This command activates the **production** group and its declared members. You can also activate multiple profiles directly:

~~~bash
java -jar app.jar --spring.profiles.active=proddb,prodmq
~~~

However, direct activation forces operators to remember the list themselves. If **observability** is a required member of the production group, the second command leaves it out.

For the **spring.profiles.active** property, higher-precedence configuration sources can replace values from lower-precedence sources. For instance, command-line arguments typically override a default active profile in **application.yml**.

### 7.2. `spring.profiles.include` adds shared profiles

~~~yaml
spring:
  profiles:
    include:
      - common
      - audit
~~~

**include** adds the listed profiles even when the caller chooses a different active profile. Included profiles are added before profiles selected via **spring.profiles.active**.

By contrast, **group** is a set of members **conditionally activated** when the corresponding group name becomes active. Selecting only **development** does not expand the **production** group.

Use **include** when a profile should be added consistently across the scope where it is declared. Use **group** when you want to **name a functional combination** that can be chosen at runtime.

### 7.3. `spring.profiles.default` applies only when no active profile exists

~~~properties
spring.profiles.default=dev
~~~

If there is no active profile, Spring Boot can use **dev** as the default profile. When running **--spring.profiles.active=production**, the default profile is not used to automatically append members to production.

A group can also be declared for a profile name activated through an appropriate mechanism, though you should not confuse **default** with an **include** list.

## 8. Where is declaring a group valid?

This is an important rule in Spring Boot 3.3:

**spring.profiles.group may only be declared in non-profile-specific configuration documents**.

Similarly, **spring.profiles.active**, **spring.profiles.default**, and **spring.profiles.include** are restricted in where they may be declared.

### 8.1. Valid: declaring in common `application.yml`

~~~yaml
# src/main/resources/application.yml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

In this example, **application.yml** has no profile activation condition and is therefore a valid place to declare groups.

### 8.2. Invalid: putting a group in `application-production.yml`

The following example has **invalid placement**:

~~~yaml
# src/main/resources/application-production.yml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Reason: **application-production.yml** is a document used only when the **production** profile is already active. Allowing group declarations here would make determining which profiles to activate circularly dependent on profile-specific document loading.

### 8.3. Invalid: putting a group in a document with `on-profile`

A YAML file can contain multiple documents separated by **---**. Declaring a group inside a document constrained by **spring.config.activate.on-profile** is invalid:

~~~yaml
# application.yml - valid common section
demo:
  name: sample
---
# This document must not declare spring.profiles.group
spring:
  config:
    activate:
      on-profile: production
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

To fix this, move **spring.profiles.group.production** into the first common document, keeping only business or operational properties that genuinely depend on the profile inside the profile-specific document.

### 8.4. A common external file can also contain groups

If you manage configuration outside the JAR, you can declare groups in a configuration source loaded **independently of profiles**. What matters is that the source is present early enough and does not reside in a file or document activated only by the very profile being declared.

For example, provide an external config file via **spring.config.additional-location**; inside the external common config file, place the **spring.profiles.group** section. Groups do not have to live inside Java source packages.

## 9. Using groups across multiple environments and multiple concerns

An organizational layout might look like this:

~~~yaml
spring:
  profiles:
    group:
      development:
        - dev-db
        - console-logs
      staging:
        - stage-db
        - stage-messaging
        - observability
      production:
        - prod-db
        - prod-messaging
        - observability
~~~

Diagram:

~~~text
development
  |-- dev-db
  +-- console-logs

staging
  |-- stage-db
  |-- stage-messaging
  +-- observability

production
  |-- prod-db
  |-- prod-messaging
  +-- observability
~~~

The **observability** member can be shared between staging and production if its configuration contents are truly shared.

In real projects, splitting profiles by **configuration concern** promotes reuse, though avoid turning every single key into its own profile. Profile names should describe a meaningful feature set, integration, or deployment mode.

Do not create a group just to rename a single profile without needing to bundle multiple pieces. Keep the number of groups small enough that readers immediately understand which profiles are chosen when looking at a launch command.

## 10. When multiple members declare the same key

Groups activate multiple profiles, yet **do not bypass configuration precedence rules**.

Suppose:

**application-proddb.yml**:

~~~yaml
demo:
  shared-name: from-database-profile
~~~

**application-prodmq.yml**:

~~~yaml
demo:
  shared-name: from-messaging-profile
~~~

When the **production** group activates both, **demo.shared-name** appears in multiple configuration documents. Spring Boot still applies Config Data loading order and source precedence; within the same location group, profiles processed in order can cause a value loaded later to override one loaded earlier.

**A more controllable design:** avoid defining overlapping keys across functional files unless intentionally overriding. Use separate namespaces such as:

~~~yaml
demo:
  database:
    mode: postgresql
~~~

and:

~~~yaml
demo:
  messaging:
    mode: rabbitmq
~~~

If overriding a shared value is necessary, document the precedence convention explicitly and inspect the actual value from **Environment** at startup. Do not rely on intuition like “this profile seems more important,” because Spring Boot does not rank **db**, **mq**, or **production** by semantic meaning.

Similarly, a property in **application-production.yml** can interact with a same-named property in a member file. Groups do not create a “smart merge” across arbitrary values; final configuration still depends on sources, loading order, and data types.

## 11. Inspecting which profiles are actually active

**Environment.getActiveProfiles()** returns the active profiles in the application's environment. This is the direct way to observe a group's effect.

Example inspection using a runner:

~~~java
package com.example.profiles;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ProfileDiagnosticsConfiguration {

    @Bean
    CommandLineRunner printActiveProfiles(Environment environment) {
        return args -> System.out.println(
                "Active profiles = "
                        + Arrays.toString(environment.getActiveProfiles()));
    }
}
~~~

When selecting **production**, the log can contain **production** and all its members.

However, do not treat the printed order in a log as a stable API contract for other services to depend on. The goal of inspection is knowing **which profiles are active**, while the final value of each property should be verified via:

~~~java
String databaseMode =
        environment.getProperty("demo.database-mode");
~~~

In JUnit tests, you can write assertions on the set of profile names or property values. Never expose an endpoint dumping the entire Environment to the public Internet for debugging; many properties can contain sensitive information.

## 12. Example testing `@Profile` conditions

Suppose a project has two beans implementing an interface:

~~~java
package com.example.profiles;

public interface MessageSender {
    String destination();
}
~~~

The first bean is only for production messaging mode:

~~~java
package com.example.profiles;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prodmq")
public class ProductionMessageSender implements MessageSender {
    @Override
    public String destination() {
        return "production-broker";
    }
}
~~~

The second bean is for local sending mode:

~~~java
package com.example.profiles;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("localmq")
public class LocalMessageSender implements MessageSender {
    @Override
    public String destination() {
        return "in-memory";
    }
}
~~~

For example, declare groups:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability
      local:
        - localdb
        - localmq
~~~

When choosing **--spring.profiles.active=production**, the **@Profile("prodmq")** condition is satisfied. When choosing **local**, **@Profile("localmq")** is satisfied.

The two beans above are illustrative. If in practice multiple active profiles cause both beans to exist simultaneously, injecting a single **MessageSender** can become ambiguous. Therefore, design groups and **@Profile** rules so each deployment configuration creates the exact expected bean set.

## 13. Configuration from CI/CD, Docker, and Kubernetes

Groups do not require a special deployment mechanism. The deployment platform simply supplies **spring.profiles.active** as usual.

### 13.1. Java command

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

### 13.2. Environment variables

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar app.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "production"
java -jar app.jar
~~~

### 13.3. Docker

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=production \
  my-application:1.0.0
~~~

If the **production** group is declared in a configuration document loaded by the application, member profiles will be activated when the container starts.

### 13.4. Kubernetes

Example snippet declaring an environment variable inside a Pod template:

~~~yaml
containers:
  - name: app
    image: my-application:1.0.0
    env:
      - name: SPRING_PROFILES_ACTIVE
        value: "production"
~~~

This is only a snippet illustrating the **env** field in container config, not a complete Deployment manifest.

**Important:** groups help select valid configuration sets; they are not a secrets management tool. Values such as passwords, tokens, and private keys must be supplied via a solution suited to the deployment environment, never hardcoded in profile files in a repository.

## 14. Common mistakes

### Mistake 1: placing a group in `application-production.yml`

If the file containing the group definition only loads once the production profile is already active, Spring Boot rejects that declaration style. The fix is moving **spring.profiles.group** into a common configuration file or document.

### Mistake 2: placing a group in a YAML document with `on-profile`

**spring.config.activate.on-profile** makes the document profile-dependent. Do not declare **spring.profiles.group** in that document. Separate the group definition and profile-specific settings into distinct documents, putting the group in a non-profile-specific document.

### Mistake 3: specifying a group name and forgetting the group itself is active

When activating **production**, **application-production.yml** and beans annotated with **@Profile("production")** can activate alongside the members. That is the intended behavior of groups, not a “virtual” profile used purely as a pointer.

### Mistake 4: misusing `spring.profiles.include`

If the goal is building a **production** combination only when operators choose it, do not use global **include** to add production members across every environment. Use **group** to control adding members under the group name.

### Mistake 5: declaring a group without actually activating it

**spring.profiles.group.production** defines relationships between profiles, but does not enable production by default. You must select **spring.profiles.active=production** or activate the profile via an appropriate mechanism.

### Mistake 6: thinking a group automatically provisions a database or message broker

Activated profiles cause matching configuration documents and conditional beans to be evaluated. They do not replace dependencies, infrastructure, DNS, accounts, or permissions. For example, **prodmq** does not make RabbitMQ appear if no broker has been deployed.

### Mistake 7: multiple groups causing bean conflicts

If one run activates groups containing alternative implementations (such as **localmq** and **prodmq**), multiple beans of the same type may exist. Design member profiles and bean conditions cleanly; avoid selecting incompatible combinations simultaneously.

### Mistake 8: assuming member order replaces all PropertySource rules

Groups make multiple profiles active. When a key is defined in multiple places, Spring Boot still resolves it according to Config Data order, file locations, and external configuration sources. Inspect actual properties whenever overrides occur.

### Mistake 9: putting sensitive settings into grouped configs committed to Git

Do not put real secrets into **application-proddb.yml** or **application-production.yml**. Having **prod** in a filename does not make its contents secure.

## 15. Practice exercises

### Exercise A: activate a group of three profiles

1. Create **application.yml** with **spring.profiles.group.production** containing **proddb**, **prodmq**, and **observability**.
2. Create **application-proddb.yml**, **application-prodmq.yml**, and **application-observability.yml**, each changing a distinct key.
3. Run **--spring.profiles.active=production**.
4. Use **Environment.getActiveProfiles()** and **Environment.getProperty(...)** to observe both the profile list and configuration values.

**Takeaway to verify:** selecting a single profile can activate member profiles simultaneously.

### Exercise B: activate a single member directly

1. Stop the previous run.
2. Start with **--spring.profiles.active=proddb**.
3. Read the profile list and illustrative properties.

**Takeaway to verify:** activating **proddb** directly does not cause the **production** group to activate in reverse. Groups define the direction **production → members**.

### Exercise C: add a `development` group

1. Declare **spring.profiles.group.development** containing **localdb** and **console-logs**.
2. Create **application-localdb.yml** and **application-console-logs.yml** with distinct illustrative keys.
3. Run **--spring.profiles.active=development**.
4. Verify neither **proddb** nor **prodmq** is present when no other source activates them.

**Takeaway to verify:** each group expresses a combination chosen by the operator.

### Exercise D: observe the difference between `group` and `include`

1. In an isolated test build, add **spring.profiles.include: [common]** in the common configuration file.
2. Run profile **production**, then run profile **development**.
3. Observe that **common** is still added when different groups are selected.
4. Remove **include** and test again to see groups activate independently.

**Takeaway to verify:** `include` adds profiles unconditionally within its declaration scope, while `group` adds members only when the group name is activated.

### Exercise E: rule for placing groups in common configuration documents

1. Try placing a group inside **application-production.yml** in your test build.
2. Observe the configuration error when Spring Boot processes the invalid definition.
3. Move the definition back into non-profile-specific **application.yml**.
4. Restart with **--spring.profiles.active=production**.

**Takeaway to verify:** profile relationship definitions must reside where they can be processed beforehand and independently of selecting a specific profile.

## 16. Core points

- **spring.profiles.group** names a related combination of profiles, such as **production → proddb + prodmq + observability**.
- Selecting **--spring.profiles.active=production** activates **production** and its member profiles.
- Declare groups using YAML lists or indexed elements in **application.properties**.
- Groups affect loading of **application-{profile}** files and conditions such as **@Profile**.
- **spring.profiles.group** definitions are valid only in **non-profile-specific** configuration documents; do not place them in **application-production.yml** or documents with **spring.config.activate.on-profile**.
- **spring.profiles.active** selects the names to activate; **include** adds profiles differently; **default** applies only when there are no active profiles.
- Splitting profiles by functional group improves configuration reuse, yet still requires managing overlapping keys, bean conditions, and secrets properly.

**Official references:**

- Spring Boot 3.3 — Profiles, *Profile Groups*: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 — Externalized Configuration, *Profile Specific Files*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework — Profiles and Environment: https://docs.spring.io/spring-framework/reference/core/beans/environment.html