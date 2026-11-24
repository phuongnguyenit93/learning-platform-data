# Profile groups and environment group configuration

A Spring Boot application often needs multiple configuration sets to run on a personal machine, integration testing environment, staging, and production. For example, local uses an in-memory database and logs to the console; staging uses a shared database while still disabling real notifications; production uses the production database, sends real notifications, and enables system observability settings.

If each environment corresponded to only a single profile, configuration could be simple. However, once environmental characteristics start combining, you easily run into long lists like `production-db,production-mail,metrics,audit` in launch commands. Such lists are hard to remember, easy to mistype, and hard to keep consistent between developer machines and deployment systems.

Spring Boot provides **profile groups** to bundle multiple member profiles under an easy-to-understand name. Instead of requiring deployers to memorize all component profiles, you declare a group such as `production`, and then only need to activate that group. Spring Boot expands the group into its member profiles to load configuration and evaluate profile-dependent beans.

This lesson belongs to the **Profiles** chapter of **Spring Boot Fundamentals**. We will clarify how to declare `spring.profiles.group`, how it works when the application starts, rules on declaration placement, configuration precedence order, differences from `spring.profiles.active` and `spring.profiles.include`, and a complete environment group design example.

## 1. Problem: an environment often consists of multiple characteristics

Imagine an application with three independent configuration dimensions:

- **Storage:** local database or remote database.
- **Notifications:** print to console or send via the production channel.
- **Observability:** enable audit/monitoring in environments requiring tracking.

If you combine profiles manually via command line, you might have to run:

```bash
java -jar application.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

The problem is that profile names are long and technical. A deployer only needs to say "this is production", without necessarily memorizing every underlying component.

Similarly, staging might need:

```bash
java -jar application.jar \
  --spring.profiles.active=remote-db,console-notify,observability
```

Both environments share some profiles while differing on others. If you duplicate lists manually, adding a new characteristic requires editing multiple places.

Profile groups solve this by mapping:

```text
local
  ├── local-db
  └── console-notify

staging
  ├── remote-db
  ├── console-notify
  └── observability

production
  ├── remote-db
  ├── real-notify
  └── observability
```

Operators only need to activate `local`, `staging`, or `production`. Centralized group configuration describes which components each environment consists of.

## 2. What is a Profile group?

A profile group is a Spring Boot configuration feature declared through the property group:

```text
spring.profiles.group.<group-name>
```

Where:

- `spring.profiles.group` is the prefix recognized by Spring Boot.
- `<group-name>` is the group profile name, for example `production`.
- The value is the list of profiles activated when the group profile is activated.

YAML example:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
        - observability
```

When starting with:

```bash
java -jar application.jar --spring.profiles.active=production
```

Spring Boot activates the `production` profile and the member profiles declared in the group.

You can visualize it as:

```text
Activate profile "production"
                │
                ▼
Read spring.profiles.group.production
                │
                ▼
       ┌────────┼─────────┐
       ▼        ▼         ▼
  remote-db  real-notify  observability
       │        │         │
       └────────┼─────────┘
                ▼
     Load profile-based configuration
     Evaluate @Profile conditions
     Create matching bean definitions
```

**A profile group is not a new ApplicationContext.** It is a rule that expands the set of active profiles within the same application startup process.

### 2.1. A group profile is also a profile

If `production` is activated, the name `production` itself remains an active profile. Therefore, you can have all of:

```text
application-production.yml
application-remote-db.yml
application-real-notify.yml
application-observability.yml
```

and Java components:

```java
@Profile("production")
```

```java
@Profile("remote-db")
```

However, each annotation carries a different scope of meaning:

- `@Profile("production")` describes beans meant only for the entire production environment.
- `@Profile("remote-db")` describes beans used whenever the remote database characteristic is activated, whether in staging or production.

This is the main benefit of groups: separating **overall environment names** from **reusable characteristics**.

### 2.2. Does a profile group contain files or directories?

No. A profile group does not declare paths to files or directories. It only contains **profile names**.

When a member profile is activated, Spring Boot can load `application-<profile>.yml` or matching `spring.config.activate.on-profile` documents depending on available Config Data sources.

If a member profile has no separate configuration file, it can still be meaningful for `@Profile` on classes or methods.

## 3. YAML syntax for spring.profiles.group

The most common syntax is a map from group name to list of members:

```yaml
spring:
  profiles:
    group:
      local:
        - local-db
        - console-notify
      staging:
        - remote-db
        - console-notify
        - observability
      production:
        - remote-db
        - real-notify
        - observability
```

With this configuration:

| Activated profile | Member profiles activated |
|---|---|
| `local` | `local-db`, `console-notify` |
| `staging` | `remote-db`, `console-notify`, `observability` |
| `production` | `remote-db`, `real-notify`, `observability` |

You do not need to activate each member manually in the launch command.

### 3.1. Single-line list syntax can be used

In YAML, the following form is conceptually equivalent:

```yaml
spring:
  profiles:
    group:
      production: [remote-db, real-notify, observability]
```

The multi-line form is easier to review when a group has many members. The inline form is compact when a group is very short.

### 3.2. Do not confuse with spring.profiles.active

Configuration:

```yaml
spring:
  profiles:
    active: production
```

means **select** the `production` profile to activate.

Configuration:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

means **define** which members belong to the `production` group.

Defining a group does not automatically activate it. You still have to select an appropriate active profile via command line, environment variable, startup config, or equivalent mechanism.

### 3.3. Properties configuration instead of YAML

Spring Boot also supports `application.properties`:

```properties
spring.profiles.group.local[0]=local-db
spring.profiles.group.local[1]=console-notify

spring.profiles.group.staging[0]=remote-db
spring.profiles.group.staging[1]=console-notify
spring.profiles.group.staging[2]=observability

spring.profiles.group.production[0]=remote-db
spring.profiles.group.production[1]=real-notify
spring.profiles.group.production[2]=observability
```

The indices `[0]`, `[1]`, `[2]` represent list elements.

Indexed syntax makes lists explicit in properties files and avoids confusion about how Spring Boot binds collections.

## 4. Which Spring Boot versions support profile groups?

Profile groups were introduced alongside the new Config Data mechanism in **Spring Boot 2.4**.

Therefore, note the distinction:

- For Spring Boot 2.3 and earlier, do not assume `spring.profiles.group` is supported.
- For Spring Boot 2.4 and newer releases, profile groups can be used under the corresponding configuration mechanism.
- When upgrading a very old application, also review changes related to `spring.config.activate.on-profile` and rules for reading profile-specific documents.

For instance, a Boot 2.3 application that used profile rules inside multi-document YAML may need adjustments when moving to Boot 2.4+. Do not merely add `spring.profiles.group` and expect all legacy configuration to behave identically.

When working on a project, check the **actual Spring Boot version running** instead of blindly applying syntax from an unversioned article.

## 5. Designing configuration by environment groups

A simple, easy-to-understand structure:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
├── application-production.yml
├── application-local-db.yml
├── application-remote-db.yml
├── application-console-notify.yml
├── application-real-notify.yml
└── application-observability.yml
```

Role of each file:

| File | Responsibility |
|---|---|
| `application.yml` | Shared configuration and profile group definitions |
| `application-local.yml` | Values specific to the local environment |
| `application-staging.yml` | Values specific to the staging environment |
| `application-production.yml` | Values specific to the production environment |
| `application-local-db.yml` | Values applied for local database mode |
| `application-remote-db.yml` | Shared values for environments using remote DB |
| `application-console-notify.yml` | Console notification configuration |
| `application-real-notify.yml` | Real notification channel configuration |
| `application-observability.yml` | Shared observability configuration |

This is an illustrative organization. Not every project needs to split into this many files. If configuration has only a few keys, a single `application.yml` with multiple documents can be easier to maintain.

### 5.1. application.yml: defining groups

```yaml
spring:
  application:
    name: profile-group-demo
  profiles:
    group:
      local:
        - local-db
        - console-notify
      staging:
        - remote-db
        - console-notify
        - observability
      production:
        - remote-db
        - real-notify
        - observability

app:
  greeting: "Hello from shared configuration"
  http-client:
    timeout: 5s
```

This file **does not yet require** the application to run local, staging, or production. It only describes the groups.

A deployer can choose:

```bash
java -jar application.jar --spring.profiles.active=staging
```

Boot then loads Config Data applicable to `staging` and the related group members.

### 5.2. application-local.yml: local-specific values

```yaml
app:
  environment-name: local
  http-client:
    timeout: 2s
  demo-data:
    enabled: true
```

### 5.3. application-staging.yml: staging-specific values

```yaml
app:
  environment-name: staging
  http-client:
    timeout: 4s
  demo-data:
    enabled: false
```

### 5.4. application-production.yml: production-specific values

```yaml
app:
  environment-name: production
  http-client:
    timeout: 10s
  demo-data:
    enabled: false
```

### 5.5. application-local-db.yml: component configuration

```yaml
app:
  storage:
    mode: in-memory
```

### 5.6. application-remote-db.yml: reused between staging and production

```yaml
app:
  storage:
    mode: remote
    endpoint: "https://storage.example.test"
```

In a real project, remote endpoints should come from a proper configuration/secret system, not hard-coded production hosts or credentials in the repository.

### 5.7. application-console-notify.yml

```yaml
app:
  notification:
    channel: console
```

### 5.8. application-real-notify.yml

```yaml
app:
  notification:
    channel: external
```

### 5.9. application-observability.yml

```yaml
app:
  observability:
    audit-enabled: true
```

If the `observability` profile is activated in staging or production, the values in this file can be loaded.

Thus, the `staging` and `production` groups share the `remote-db` and `observability` components, while selecting different notification channels.

## 6. Activating a group with a command-line argument

Suppose the JAR packages the configuration files above.

Running local:

```bash
java -jar profile-group-demo.jar --spring.profiles.active=local
```

Running staging:

```bash
java -jar profile-group-demo.jar --spring.profiles.active=staging
```

Running production:

```bash
java -jar profile-group-demo.jar --spring.profiles.active=production
```

From an operational standpoint, these commands are far simpler than manually listing `remote-db,real-notify,observability`.

### 6.1. Advantages of activating a single group name

- Operators remember **environment** names, not every implementation detail.
- Member profile lists live in configuration and can be reviewed and version-controlled.
- When adding a new component, edit the group definition instead of updating every script/deployment.
- The same member profile can be reused across groups.
- `@Profile` and profile-specific files remain the standard mechanisms for enabling beans or configuration.

### 6.2. Groups do not disable configuration overrides

For example, production uses a default timeout of `10s`, yet one deployment wants `15s`:

```bash
java -jar profile-group-demo.jar \
  --spring.profiles.active=production \
  --app.http-client.timeout=15s
```

The command-line property can override values coming from Config Data under normal precedence.

A profile group decides **which profiles are active**. It does not lock down every property's value or forbid higher-precedence sources from overriding configuration.

## 7. Activating a group with environment variables

In containers or CI/CD systems, this variable is commonly used:

```text
SPRING_PROFILES_ACTIVE=production
```

Example in a shell supporting inline variable assignment:

```bash
SPRING_PROFILES_ACTIVE=production java -jar profile-group-demo.jar
```

Or in Docker Compose:

```yaml
services:
  app:
    image: example/profile-group-demo:latest
    environment:
      SPRING_PROFILES_ACTIVE: production
      APP_STORAGE_ENDPOINT: "https://storage.example.test"
```

Here, the application receives the group name `production` via an environment variable. Group members are expanded by Boot while preparing Config Data.

Note: `APP_STORAGE_ENDPOINT` only overrides the `app.storage.endpoint` property if the project uses matching naming and binding. It does not modify the profile group itself.

### 7.1. Setting the variable in PowerShell

In PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar profile-group-demo.jar
```

In Bash or a similar shell:

```bash
export SPRING_PROFILES_ACTIVE=staging
java -jar profile-group-demo.jar
```

Shell syntax differs, while the property Spring Boot reads remains `spring.profiles.active`.

## 8. How do member profiles affect @Profile?

Profile groups do not only affect YAML files. Member profiles are also used when Spring evaluates the `@Profile` annotation.

Example interface:

```java
package com.example.demo.notification;

public interface MessageSink {
    void send(String message);
}
```

Console implementation:

```java
package com.example.demo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("console-notify")
public class ConsoleMessageSink implements MessageSink {

    @Override
    public void send(String message) {
        System.out.println("[CONSOLE] " + message);
    }
}
```

External implementation:

```java
package com.example.demo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("real-notify")
public class ExternalMessageSink implements MessageSink {

    @Override
    public void send(String message) {
        System.out.println("[EXTERNAL-DEMO] " + message);
    }
}
```

The `ExternalMessageSink` class in this example **only simulates an external channel via logs**, without actually sending emails/SMS.

Consuming service:

```java
package com.example.demo.notification;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final MessageSink sink;

    public NotificationService(MessageSink sink) {
        this.sink = sink;
    }

    public void notifyStarted() {
        sink.send("Application has started");
    }
}
```

When activating:

- `local` → `console-notify` → registers `ConsoleMessageSink`.
- `staging` → `console-notify` → registers `ConsoleMessageSink`.
- `production` → `real-notify` → registers `ExternalMessageSink`.

Even though the operator only chooses `staging` or `production`, beans are still determined based on the member profiles.

### 8.1. If two opposing profiles are active together

Suppose you run:

```bash
java -jar app.jar \
  --spring.profiles.active=staging,production
```

These two groups can activate both `console-notify` and `real-notify` simultaneously. Both `MessageSink` beans can then be registered, leading to an error when injecting a single bean unless `@Primary`, `@Qualifier`, or proper handling is present.

**Profile groups do not create mutual exclusion**. They only activate additional profiles. If two groups must not run concurrently, establish a configuration check policy to detect invalid combinations.

### 8.2. @Profile on the group vs. on a member?

Use:

```java
@Profile("production")
```

when the bean only makes sense in the production environment.

Use:

```java
@Profile("remote-db")
```

when the bean is shared by every environment that activates `remote-db`.

Not every class needs `@Profile("production")`. If a piece of infrastructure is genuinely shared between staging and production, annotating by capability profile improves reusability.

## 9. Runnable example: local and production groups

A minimal example only needs `spring-boot-starter`, with no web server required. Assume the project uses modern Spring Boot and a compatible Java version.

### 9.1. File structure

```text
src/main/
├── java/com/example/profilegroup/
│   ├── ProfileGroupApplication.java
│   ├── NotificationService.java
│   ├── MessageSink.java
│   ├── ConsoleMessageSink.java
│   ├── ProductionMessageSink.java
│   └── ProfilePrinter.java
└── resources/
    ├── application.yml
    ├── application-local.yml
    ├── application-production.yml
    ├── application-console-notify.yml
    └── application-real-notify.yml
```

### 9.2. application.yml

```yaml
spring:
  application:
    name: profile-group-demo
  profiles:
    group:
      local:
        - console-notify
      production:
        - real-notify

app:
  notification:
    greeting: "Hello"
```

### 9.3. application-local.yml

```yaml
app:
  notification:
    greeting: "Hello from local"
```

### 9.4. application-production.yml

```yaml
app:
  notification:
    greeting: "Hello from production"
```

### 9.5. Interface and two implementations

```java
package com.example.profilegroup;

public interface MessageSink {
    void send(String text);
}
```

```java
package com.example.profilegroup;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("console-notify")
public class ConsoleMessageSink implements MessageSink {

    @Override
    public void send(String text) {
        System.out.println("[CONSOLE] " + text);
    }
}
```

```java
package com.example.profilegroup;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("real-notify")
public class ProductionMessageSink implements MessageSink {

    @Override
    public void send(String text) {
        System.out.println("[PRODUCTION-DEMO] " + text);
    }
}
```

### 9.6. Service using bound configuration

```java
package com.example.profilegroup;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final MessageSink sink;
    private final String greeting;

    public NotificationService(
            MessageSink sink,
            @Value("${app.notification.greeting}") String greeting
    ) {
        this.sink = sink;
        this.greeting = greeting;
    }

    public void notifyStarted() {
        sink.send(greeting);
    }
}
```

### 9.7. Runner printing active profiles

```java
package com.example.profilegroup;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfilePrinter implements CommandLineRunner {

    private final Environment environment;
    private final NotificationService notificationService;

    public ProfilePrinter(
            Environment environment,
            NotificationService notificationService
    ) {
        this.environment = environment;
        this.notificationService = notificationService;
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "Active profiles: "
                        + Arrays.toString(
                                environment.getActiveProfiles()
                        )
        );

        notificationService.notifyStarted();
    }
}
```

### 9.8. Main application

```java
package com.example.profilegroup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileGroupApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileGroupApplication.class, args);
    }
}
```

### 9.9. Running local

```bash
java -jar profile-group-demo.jar --spring.profiles.active=local
```

Logs from the runner may resemble:

```text
Active profiles: [local, console-notify]
[CONSOLE] Hello from local
```

### 9.10. Running production

```bash
java -jar profile-group-demo.jar --spring.profiles.active=production
```

Illustrative logs:

```text
Active profiles: [production, real-notify]
[PRODUCTION-DEMO] Hello from production
```

The list and display order of active profiles depend on whether additional profiles come from other sources. This is the expected output for an example with a single activated group.

### 9.11. What happens when running without a profile?

If `spring.profiles.active` is not declared, the `local` or `production` groups **are not automatically activated just because they exist**.

In the example above, neither member profile `console-notify` nor `real-notify` is active, so there is no `MessageSink` bean. `NotificationService` has a required constructor parameter `MessageSink`, so the context may fail to start.

This example is intentional to show that **a group is a mapping declaration, not a default activation command**.

If the application needs to run locally without external configuration, you must design an explicit default: for instance activating a profile when launching from the IDE, or configuring an appropriate group/default at bootstrap. Avoid implicitly assuming that the name `local` automatically becomes the default profile.

## 10. Very important rule: declare groups only in non-profile-specific documents

Spring Boot has a restriction to remember:

**`spring.profiles.group` may only be used in non-profile-specific configuration documents.**

In other words, placing a group in a root configuration document such as `application.yml` is valid; placing a group in `application-production.yml` or a document activated by `spring.config.activate.on-profile` is invalid under Config Data rules.

### 10.1. Valid: defining groups in application.yml

```yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

### 10.2. Invalid: defining groups in application-production.yml

```yaml
# application-production.yml — INVALID
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

Reason: `application-production.yml` is a profile-specific file. Using it to define additional active profile relationships can create a circular dependency during document selection: Boot first needs to know which profiles are active to load the file, yet needs to load the file to know which profiles are active.

Spring Boot prevents this ambiguous configuration by restricting where properties affecting profile activation can be declared.

### 10.3. Invalid: placing a group in a document with on-profile

```yaml
# application.yml
app:
  name: demo
---
spring:
  config:
    activate:
      on-profile: production
  profiles:
    group:
      production:
        - real-notify
```

The second document is profile-activated, so it must not be used to declare `spring.profiles.group`.

### 10.4. Valid: group in root document, profile-specific values in activated documents

```yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify

app:
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: production

app:
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: real-notify

app:
  notification:
    mode: external
```

Here only the first document defines the group. The subsequent documents contribute application values according to the active profiles.

### 10.5. What happens if violated?

Spring Boot may report a configuration error while processing Config Data, such as an `InvalidConfigDataPropertyException` stating that the property is not allowed in a profile-specific resource/document.

When you see an error involving `spring.profiles.group` in profile-specific configuration, move the group definition up to a non-profile-specific document. Do not try to work around it by disabling validation or renaming properties.

## 11. spring.profiles.active, spring.profiles.include, and spring.profiles.group

These three mechanisms serve different purposes.

| Mechanism | Question it answers |
|---|---|
| `spring.profiles.active` | Which profiles are selected to be active? |
| `spring.profiles.include` | Which profiles need to be added on top of the selected profile set? |
| `spring.profiles.group` | If a profile name is activated, which additional profiles does it represent? |

### 11.1. active: direct selection

```yaml
spring:
  profiles:
    active: production
```

This configuration selects `production` as an active profile. If a group is defined for that name, its members are expanded.

In real deployments, the runtime environment usually selects active profiles via environment variables or command line rather than hard-coding `production` inside a shared JAR.

### 11.2. include: adding profiles to the active set

Example:

```yaml
spring:
  profiles:
    include:
      - observability
```

The purpose is adding `observability`, not defining a newly named group.

When you simply want to create one name representing the full production configuration, `group` expresses the intent more clearly. When you want to add a profile to the active set regardless of which environment profile is selected, `include` can fit.

### 11.3. group: defining membership relationships

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
        - observability
```

Only when the `production` profile is active are the member profiles activated by the group relationship.

### 11.4. active/include/group must not be placed in profile-specific documents

Like `spring.profiles.group`, `spring.profiles.active` and `spring.profiles.include` also have placement restrictions under modern Spring Boot's Config Data mechanism.

Do not declare them in:

- `application-production.yml`.
- YAML documents with `spring.config.activate.on-profile`.
- Other profile-specific documents.

This is an important rule when migrating from legacy YAML configuration to Spring Boot 2.4+.

### 11.5. When to prefer group over include?

If the intent is:

> "Whenever production is enabled, automatically enable remote-db, real-notify, and observability."

then use `spring.profiles.group.production`.

If the intent is:

> "Regardless of whether running local or production, this application always needs the observability profile added."

then `spring.profiles.include` can express that well, provided it is declared in a valid location.

Do not use one giant `include` list to simulate multiple different environment groups.

## 12. When are groups and profile-specific configuration processed?

Profile groups are resolved during the phase when Spring Boot prepares Config Data and determines active profiles, **before most application beans are created**.

Conceptual flow:

```text
SpringApplication.run(...)
             │
             ▼
Prepare Environment and Config Data sources
             │
             ▼
Read spring.profiles.group definitions in
non-profile-specific documents
             │
             ▼
Determine spring.profiles.active
             │
             ▼
Expand groups into member profiles
             │
             ▼
Load matching profile-specific Config Data
             │
             ▼
Evaluate @Profile and configuration conditions
             │
             ▼
Register bean definitions
             │
             ▼
Instantiate and inject beans
             │
             ▼
Application ready
```

This is a conceptual learning model. Spring Boot may perform multiple passes over Config Data to accurately resolve sources and effective profiles; do not treat the diagram as a literal description of internal methods.

Practical takeaway: **group definitions must exist at the stage when Boot determines the active profile set**, not after the context has initialized.

### 12.1. Groups cannot be used as runtime feature flags

If the application has started with `local`, and a service later calls:

```java
environment.setActiveProfiles("production");
```

on an existing `ConfigurableEnvironment`, Spring Boot does not re-run the entire Config Data bootstrap to reload every `application-production.yml`, re-evaluate `@Profile`, and swap all local beans for production beans.

This is not a way to switch environments while the application is serving requests. To change environments, you usually need to restart with a new active profile set or use a dedicated refresh/reconfiguration system.

### 12.2. Do not set group names with an arbitrary runtime property

`spring.profiles.group` is part of bootstrap configuration. Do not use a business service or scheduler running after startup to construct a group dynamically and expect Spring to reload profile-specific documents.

## 13. Profile order and configuration precedence

A group can activate multiple profiles; sometimes the corresponding files declare the same key.

For example:

```yaml
# application.yml
spring:
  profiles:
    group:
      staging:
        - remote-db
        - observability

app:
  greeting: "base"
```

```yaml
# application-staging.yml
app:
  greeting: "staging"
```

```yaml
# application-remote-db.yml
app:
  greeting: "remote-db"
```

```yaml
# application-observability.yml
app:
  greeting: "observability"
```

This is a **confusing** organization because `app.greeting` is repeated across multiple different profiles. The final value depends on the Config Data application order and the precedence of loaded sources.

Spring Boot has precedence rules for profile-specific configuration, where when multiple profiles are active, a profile processed later can override values from an earlier profile at the corresponding configuration tier. However, the overall outcome is also affected by locations, imports, external configuration, command line, and environment variables.

Therefore, **do not design profile groups around an implicit override order among members** if it can be avoided.

### 13.1. Good design: each member owns a distinct area

For example:

```yaml
# application-remote-db.yml
app:
  storage:
    mode: remote
```

```yaml
# application-observability.yml
app:
  observability:
    enabled: true
```

```yaml
# application-staging.yml
app:
  environment-name: staging
```

Each file owns distinct keys according to its responsibility. Override order then has little impact on the outcome, making it easier to understand and test.

### 13.2. Intentional overrides at the environment level

If a key truly needs to differ between staging and production, put it in the corresponding environment profile:

```yaml
# application-staging.yml
app:
  http-client:
    timeout: 3s
```

```yaml
# application-production.yml
app:
  http-client:
    timeout: 10s
```

Avoid letting both `remote-db` and `observability` also define `app.http-client.timeout` without a clear reason.

### 13.3. Higher-precedence sources can still win

Even when profile files load properly, an environment variable or command-line argument can override a property:

```bash
java -jar app.jar \
  --spring.profiles.active=production \
  --app.http-client.timeout=20s
```

This is normal externalized configuration behavior, not a profile group bug.

## 14. Group names, member profile names, and naming conventions

A good convention separates two layers:

- **Environment names:** `local`, `test`, `staging`, `production`.
- **Characteristic names:** `local-db`, `remote-db`, `console-notify`, `real-notify`, `observability`.

Environment names answer "where is the application running?". Characteristic names answer "which capabilities are enabled in this environment?".

### 14.1. Avoid vague names

A group like:

```yaml
spring:
  profiles:
    group:
      prod:
        - a
        - b
        - x
```

is hard to understand because readers do not know what `a`, `b`, and `x` stand for.

Use:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
        - audit
```

Clear names help deployers and reviewers understand intent without consulting multiple documents.

### 14.2. Avoid overly deep groups or circular references

To keep configuration manageable, avoid building a complex network of nested groups, especially relationships that could form cycles such as `a -> b -> a`.

A simple, direct definition is usually easier to predict:

```text
production
  ├── remote-db
  ├── real-notify
  └── observability
```

If an organization wants to reuse a group inside a group, verify the specific behavior of your Boot version and keep relationships acyclic, rather than turning profile groups into a complex dependency graph by default.

### 14.3. Member names should describe configuration concerns

Names like `development` and `production` make sense for environments. Names like `postgres`, `mock-payment`, and `audit` make sense for capabilities.

However, avoid putting sensitive information such as internal hostnames, usernames, or sensitive environment codes into profile names. Profile names often appear in startup logs.

## 15. Organizing with orthogonal profiles

**Orthogonal profiles** is a way of splitting configuration along relatively independent dimensions. For example:

```text
Storage dimension
  local-db / remote-db

Notification dimension
  console-notify / real-notify

Observability dimension
  observability / no-observability
```

Each environment group picks an appropriate option from each dimension:

| Environment | Storage | Notifications | Observability |
|---|---|---|---|
| local | local-db | console-notify | Minimal default |
| staging | remote-db | console-notify | observability |
| production | remote-db | real-notify | observability |

Benefits:

- Capability profiles can be reused.
- Configuration is split by responsibility.
- Changing a shared component does not require duplicating edits across multiple files.
- Tests can activate a single member profile when targeted testing is needed.

### 15.1. Do not over-fragment

If a small application has only two environments differing by a few properties, creating twelve capability profiles can make the project unnecessarily complex.

Use profile groups when they genuinely reduce duplication and make environment combinations clearer. There is no need to turn every boolean property into a dedicated profile.

### 15.2. When to use @ConditionalOnProperty instead of @Profile?

`@Profile` makes sense when a bean/configuration is tied to an **environment or environment-level characteristic**.

`@ConditionalOnProperty` makes sense when toggling a feature with an explicit property:

```java
@Bean
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
AuditPublisher auditPublisher() {
    return new AuditPublisher();
}
```

You can use a profile group to load `application-observability.yml` containing `app.audit.enabled=true`, and then use `@ConditionalOnProperty` based on that value.

Thus, the group selects the configuration combination; the property condition decides a feature based on effective configuration. Not every feature flag needs an extra profile.

## 16. Combining profile groups with multi-document YAML

If you do not want many files, Spring Boot supports multiple documents in one YAML file separated by `---`.

Example:

```yaml
# Document 1: shared, non-profile-specific configuration
spring:
  profiles:
    group:
      local:
        - console-notify
      production:
        - real-notify
        - observability

app:
  greeting: "Hello"

---
# Document 2: only when local is active
spring:
  config:
    activate:
      on-profile: local

app:
  greeting: "Hello local"

---
# Document 3: only when production is active
spring:
  config:
    activate:
      on-profile: production

app:
  greeting: "Hello production"

---
# Document 4: when observability is active
spring:
  config:
    activate:
      on-profile: observability

app:
  audit:
    enabled: true
```

This is valid because `spring.profiles.group` sits in the first document with no `on-profile`. The remaining documents hold only profile-activated configuration.

### 16.1. on-profile does not define additional active profiles

`spring.config.activate.on-profile` is a condition for **applying the current document**:

```yaml
spring:
  config:
    activate:
      on-profile: production
```

It does not mean "activate production". The `production` profile must already be active through another mechanism.

### 16.2. Contrast with legacy syntax

In very old Spring Boot examples, you might see profile tagging on a YAML document written as:

```yaml
spring:
  profiles: production
```

This syntax should not be copied into modern Spring Boot Config Data setups. For profile-dependent documents, use `spring.config.activate.on-profile`.

Important: never use `spring.profiles.group` inside a document that has `on-profile`.

## 17. Profile groups and the default profile

When there is no explicit active profile, Spring Framework has the concept of default profiles, usually defaulting to `default`.

You can check:

```java
String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
```

These are two separate concepts:

- `getActiveProfiles()`: currently active profiles.
- `getDefaultProfiles()`: default profiles used when no active profiles apply.

### 17.1. A group is not chosen as default just because it is declared

For example:

```yaml
spring:
  profiles:
    group:
      local:
        - local-db
        - console-notify
```

Nothing here tells Boot to choose `local` at startup. The group name is only used for expansion when it is activated.

If you want a default mode, choose an explicit policy:

- Configure `spring.profiles.active` in a non-profile-specific document if appropriate for requirements.
- Pass `SPRING_PROFILES_ACTIVE` via a launcher or IDE.
- Provide a documented local run command.
- Design default beans that require no profile, with specific conditions if needed.

Do not conflate `spring.profiles.default`, `spring.profiles.active`, and `spring.profiles.group`.

### 17.2. Why not hard-code production in a shared JAR?

If you put:

```yaml
spring:
  profiles:
    active: production
```

in packaged configuration, the application could accidentally boot in production mode on a laptop if someone forgets to override it.

For an artifact used across multiple environments, letting the deployment system supply the environment name is usually safer and clearer. You can also design a local default, but must evaluate the risk since a local default must never run unexpectedly in production.

## 18. Inspecting active profiles at runtime

After the application starts, you can inject `Environment` to see which profiles are actually active:

```java
package com.example.demo.diagnostics;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfileLogger implements ApplicationRunner {

    private final Environment environment;

    public ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: "
                        + Arrays.toString(
                                environment.getActiveProfiles()
                        )
        );
    }
}
```

If you run `--spring.profiles.active=production` with a suitable group definition, you can observe `production` along with members such as `remote-db`, `real-notify`, and `observability`.

### 18.1. Do not use logs to leak secrets

Lists of profile names are usually not secrets, though profile names can reveal infrastructure details. Avoid using names containing passwords, tokens, or sensitive hostnames.

When debugging, never print the entire `Environment` or all PropertySources to the console; many properties may hold confidential data.

### 18.2. Checking whether a profile is active

`Environment` supports `acceptsProfiles`:

```java
import org.springframework.core.env.Profiles;

boolean remoteDbActive =
        environment.acceptsProfiles(
                Profiles.of("remote-db")
        );

boolean productionOrStaging =
        environment.acceptsProfiles(
                Profiles.of("production | staging")
        );
```

The `Profiles.of(...)` API allows profile expressions with operators such as `!`, `&`, and `|`. Use it when you need to check a profile condition in diagnostic or infrastructure code.

Normally, business services do not need to call `acceptsProfiles` repeatedly. If the difference is an implementation, let Spring select the bean via `@Profile` or an explicit configuration mechanism.

## 19. Writing @Profile with expressions

`@Profile` accepts logical expressions, not just a single profile name.

For example:

```java
@Profile("production & observability")
```

means both `production` and `observability` must be active.

Another example:

```java
@Profile("!production")
```

means the bean matches when `production` is not active.

### 19.1. @Profile with multiple values is OR, not AND

Example:

```java
@Profile({"staging", "production"})
```

means the bean can be active if **either** profile matches, not requiring both.

If you want AND, use an expression:

```java
@Profile("staging & observability")
```

### 19.2. Use the group name or an expression?

If the `production` group already includes `observability`, a bean meant exclusively for production may only need:

```java
@Profile("production")
```

If a bean requires observability regardless of environment:

```java
@Profile("observability")
```

If you want to require both staging and observability regardless of future edits to group definitions, using an AND expression can explicitly capture that policy.

## 20. Testing profile groups with Spring Boot Test

Tests help verify whether a group activates the right set of beans/configurations.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("staging")
class StagingProfileTest {

    @Autowired
    Environment environment;

    @Test
    void expandsStagingGroup() {
        assertThat(environment.getActiveProfiles())
                .contains("staging", "remote-db",
                          "console-notify", "observability");
    }
}
```

In a Spring Boot test context using the application's Config Data, `@ActiveProfiles("staging")` can select the group profile, and then you assert that the member profiles have been activated.

### 20.1. Testing bean selection

Example:

```java
@SpringBootTest
@ActiveProfiles("local")
class LocalNotificationTest {

    @Autowired
    private MessageSink sink;

    @Test
    void usesConsoleSink() {
        assertThat(sink).isInstanceOf(ConsoleMessageSink.class);
    }
}
```

And production:

```java
@SpringBootTest
@ActiveProfiles("production")
class ProductionNotificationTest {

    @Autowired
    private MessageSink sink;

    @Test
    void usesExternalSink() {
        assertThat(sink).isInstanceOf(ExternalMessageSink.class);
    }
}
```

The examples assume the application package contains these components and the test has Spring Boot Test/AssertJ dependencies.

### 20.2. Testing an invalid profile combination

If two groups must not be active simultaneously, you can write a test or startup validation to detect:

```text
spring.profiles.active=staging,production
```

Running with that combination can cause both `MessageSink` beans to become active. Tests help the development team catch invalid configuration before deployment.

### 20.3. Tests do not replace deployment checks

Even when profile group tests pass, a production deployment could still supply:

```text
SPRING_PROFILES_ACTIVE=staging
```

due to an environment variable mistake. Therefore, observe actual active profiles when starting the process and check CI/CD configuration.

## 21. Common issues

| Symptom | Possible cause | How to address |
|---|---|---|
| Running `production` yet missing `real-notify` bean | Group not declared properly or not loaded | Check `spring.profiles.group.production` in the root document |
| Boot reports invalid `spring.profiles.group` property | Placed group inside a profile-specific document | Move group to a non-profile-specific document |
| Running without passing a profile causes missing bean | Group is defined but not activated | Select an active profile or design a default bean |
| Two beans of the same interface cause `NoUniqueBeanDefinitionException` | Two conflicting groups/profiles active together | Only activate valid combinations; verify configuration |
| Only environment name appears, no members | Group definition not loaded by Boot or version unsupported | Check version, Config Data paths, and actual active profiles |
| application-production.yml not applied | `production` not active, wrong filename, or Config Data not found | Check launch command, filename, and locations |
| Value from a group member overrides unexpectedly | Multiple sources with the same key and precedence rules | Inspect Environment/Config Data and reduce duplicate keys |
| YAML file changed yet beans did not change | Profiles/Config Data are processed at startup | Restart or design explicit refresh |
| Placed group inside `application-production.yml` to "auto-expand" | Restricted placement | Move definition to `application.yml` |
| Works in IDE tests yet fails in JAR | IDE and JAR have different profile/config locations | Compare runtime classpath, Environment, and deployment variables |
| Used `@Profile({"production","staging"})` thinking it is AND | Profile array is evaluated as OR | Use `"production & staging"` expression if AND is truly intended |
| One group has too many unmanageable members | Poor profile granularity and naming | Simplify, split by responsibility, and remove redundant members |

### 21.1. Missing bean error when group is not active

Suppose a service requires `MessageSink`:

```java
public NotificationService(MessageSink sink) {
    this.sink = sink;
}
```

If neither `console-notify` nor `real-notify` is active, Spring has no `MessageSink` candidate. Startup can fail with `UnsatisfiedDependencyException` wrapping `NoSuchBeanDefinitionException`.

To fix, check active profiles and group definitions before modifying injection code.

### 21.2. Confusing feature groups with loading libraries

If `production` activates `real-notify` yet the project lacks the class/bean for real notifications, activating the profile alone does not add dependencies.

A profile group does not add Maven/Gradle dependencies, create non-existent bean classes, or establish network connections. It only makes **already-provided** configurations and bean definitions with matching profile conditions eligible for consideration.

### 21.3. Difference between conditions and groups

`@Profile("real-notify")` checks the active profile set. `@ConditionalOnProperty` checks a property in Environment.

If a single bean uses both conditions, both must match according to condition combination rules. Do not assume an active group bypasses other conditions on a bean.

## 22. Checking effective values and configuration origins

If a profile group works yet a property receives an unexpected value, inspect not just the profile set but also **PropertySources**.

A simple diagnostic runner:

```java
package com.example.demo.diagnostics;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentDiagnostics implements ApplicationRunner {

    private final Environment environment;

    public EnvironmentDiagnostics(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Profiles: "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("Storage mode: "
                + environment.getProperty(
                        "app.storage.mode", "<missing>"
                ));

        System.out.println("Notification channel: "
                + environment.getProperty(
                        "app.notification.channel", "<missing>"
                ));
    }
}
```

The example reads only non-secret keys.

### 22.1. Actuator can assist diagnostics

With Spring Boot Actuator, endpoints such as:

- `/actuator/env`.
- `/actuator/configprops`.
- `/actuator/conditions`.

can help inspect effective configuration values, binding status, and why conditions were applied or skipped, depending on exposure and security settings.

Do not enable exposing all property values in production if secrets could be revealed. Prefer inspecting non-sensitive keys and securing endpoints.

### 22.2. Do not read only application-production.yml

A value can come from:

- `application.yml`.
- `application-production.yml`.
- A member profile's file such as `application-remote-db.yml`.
- An imported Config Data file.
- A configuration file outside the JAR.
- A Java system property.
- An OS environment variable.
- A command-line argument.

Therefore, to know why `app.storage.mode` is `remote`, inspect both group members and source precedence, not just the file named after the environment.

## 23. Profile groups in CI/CD and container deployments

In a deployment system, the goal is for each environment to have a controlled name.

For example:

```text
Local developer:
  SPRING_PROFILES_ACTIVE=local

Staging deployment:
  SPRING_PROFILES_ACTIVE=staging

Production deployment:
  SPRING_PROFILES_ACTIVE=production
```

Group configuration packaged with the artifact:

```yaml
spring:
  profiles:
    group:
      local: [local-db, console-notify]
      staging: [remote-db, console-notify, observability]
      production: [remote-db, real-notify, observability]
```

This keeps pipelines from having to maintain lists of capability profiles across many deployment variables.

### 23.1. Do not use groups to store secrets

Groups should contain only **profile names**, not passwords or tokens:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

Secrets such as database passwords, API keys, and access tokens should be supplied via secret management, environment variables, or appropriate secure configuration mechanisms.

### 23.2. Verify environment variables at deploy time

If a production system accidentally uses:

```text
SPRING_PROFILES_ACTIVE=staging
```

then Spring Boot will apply the staging group as configured. That is a deployment error, not a profile group bug.

Include a check on the profile name passed by the pipeline and log active profiles safely to aid diagnostics.

### 23.3. Be cautious with combining multiple groups

A command such as:

```bash
java -jar app.jar --spring.profiles.active=production,staging
```

can activate members of both groups.

If `production` and `staging` are mutually exclusive environments, design validation or pipeline policy to reject this combination. Spring Boot does not automatically know your organization's operational rules.

## 24. Migrating from a long profile list to a group

Suppose previously the team ran production with:

```bash
java -jar app.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

To migrate:

### Step 1 — Inventory existing combinations

Record the combinations used across local, test, staging, and production. Especially look for profiles shared across environments.

### Step 2 — Separate capability profiles from environment profiles

For example:

- Environments: `local`, `staging`, `production`.
- Capabilities: `local-db`, `remote-db`, `console-notify`, `real-notify`, `observability`.

### Step 3 — Declare groups in a non-profile-specific file

```yaml
spring:
  profiles:
    group:
      production: [remote-db, real-notify, observability]
```

Place it in the root document of `application.yml` or a non-profile-specific Config Data source.

### Step 4 — Update the launch command

From:

```bash
java -jar app.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

to:

```bash
java -jar app.jar --spring.profiles.active=production
```

### Step 5 — Verify files and beans per member

Verify that files such as `application-remote-db.yml` are loaded and `@Profile("real-notify")` beans are registered when `production` is active.

### Step 6 — Review overridden keys

If multiple profiles set the same key, document configuration ownership or adjust structure to reduce dependence on profile order.

### Step 7 — Test multiple environments

Run separate contexts for local, staging, and production, checking that required beans are registered, inappropriate beans do not appear, and critical properties receive the right values.

### Step 8 — Update deployment documentation

Ensure runbooks, Docker Compose, Kubernetes manifests, scripts, and IDE run configurations use the agreed group names. Avoid leaving some places on groups while others keep outdated lists that drift out of sync.

## 25. Practice exercises

### Exercise 1 — Create your first profile group

Create a Spring Boot 2.4+ project with `application.yml`:

```yaml
spring:
  profiles:
    group:
      local:
        - local-db
        - console-notify
```

Run with `--spring.profiles.active=local` and print the active profiles list via `Environment`.

### Exercise 2 — Create two member profiles with separate files

Create `application-local-db.yml` and `application-console-notify.yml`. Have each file declare a different key. Verify that both values take effect when enabling the `local` group.

### Exercise 3 — Add staging and production

Create `staging` and `production` groups sharing `remote-db` but differing in notification profile. Run with each group name and check which member profiles are activated.

### Exercise 4 — Use @Profile to select beans

Create `MessageSink` with two implementations: one `@Profile("console-notify")`, one `@Profile("real-notify")`. Inject `MessageSink` into a service and verify the implementation per environment.

### Exercise 5 — Check invalid placement

Intentionally place `spring.profiles.group` inside `application-production.yml`. Observe the error Spring Boot reports. Then move the group definition to the root `application.yml` document and run again.

### Exercise 6 — Multi-document YAML

Replace member files with documents inside `application.yml` using `spring.config.activate.on-profile`. Keep group definitions in a document without `on-profile` and check the results.

### Exercise 7 — Distinguish active, include, and group

Create an example using `spring.profiles.active` to select a profile, `spring.profiles.include` to add an always-needed profile, and `spring.profiles.group` to expand an environment name. Explain what problem each mechanism solves.

### Exercise 8 — Configure the same key in multiple sources

Set `app.http-client.timeout` in `application.yml`, `application-production.yml`, and a command-line argument. Predict and then observe the effective value from `Environment#getProperty`.

### Exercise 9 — Invalid environment combination

Try running `--spring.profiles.active=staging,production` when both groups choose different notification implementations. Observe the error or set of beans produced. Propose validation to prevent this combination.

### Exercise 10 — Verify with @SpringBootTest

Write a test using `@ActiveProfiles("staging")`. Assert that required member profiles are active and the service receives the right implementation for staging.

### Exercise 11 — Migrate a legacy launch command

Suppose a runbook has:

```bash
java -jar app.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

Write the corresponding `production` group definition, update the launch command, and explain the maintenance benefits.

### Exercise 12 — Changing profiles after startup

Start the application with `local`. Then try changing an environment variable in another shell or editing a YAML file. Observe that already-registered `@Profile` beans do not swap automatically. Explain why groups are a bootstrap decision rather than a runtime feature flag.

## 26. Official references

- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): activating profiles, `spring.profiles.group`, `spring.profiles.include`, default profiles, and placement restrictions.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data, profile-specific files, document activation, precedence order, and external configuration sources.
- [Spring Framework Reference — Bean Definition Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles): how `@Profile` and `Environment` participate in bean conditions.
- [Spring Framework Javadoc — Profile](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Profile.html): syntax and usage of the `@Profile` annotation.
- [Spring Framework Javadoc — Environment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html): active/default profiles API and querying profile conditions.
- [Spring Boot 2.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.4-Release-Notes): Config Data changes and introduction of profile groups.

In Spring Boot, **a profile group is a declaration mapping an environment name to member profiles**, allowing applications to reuse configuration by capability while operators still only pick one clear environment name. Declare `spring.profiles.group` in a non-profile-specific document, activate the group via `spring.profiles.active` or environment variables, design member profiles with clear responsibilities, and verify actual active profiles and configuration values at startup. This structure keeps local, staging, and production more consistent without equating profile groups with dynamic configuration updates while the application is running.
