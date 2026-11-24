# Multiple Active Profiles and Override Order in Spring Boot

## Objectives

Spring Boot lets you activate **multiple profiles in a single run**. An application can simultaneously use the **prod** profile for production settings, **eu** for regional parameters, and **metrics** to enable a group of observability beans. However, when multiple profiles declare the same property, developers must understand **profile order**, **PropertySource order**, and **bean conditional mechanisms** to explain the result accurately.

For example, the following two commands can yield different configurations:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,live
java -jar demo.jar --spring.profiles.active=live,prod
~~~

The reason is that for **profile-specific configuration files at the same precedence level**, Spring Boot applies the rule that **a profile listed later can override values from an earlier profile**. However, this rule is only one part of the configuration precedence system: command-line arguments, JVM system properties, environment variables, file locations, imports, and Config Data documents also play a role.

After this lesson, the reader will be able to:

- Declare, inspect, and distinguish the list of active profiles from default profiles.
- Explain what happens when the same key appears in application.yml, application-prod.yml, and application-live.yml.
- Predict the impact of changing the order of **spring.profiles.active**.
- Distinguish **spring.profiles.active**, **spring.profiles.include**, **spring.profiles.group**, and **spring.config.activate.on-profile**.
- Understand how **@Profile** selects beans, as distinct from property overriding.
- Inspect runtime configuration when another profile or configuration source changes an expected value.

## 1. Profiles have two distinct roles to separate

In Spring Boot, profiles typically participate in two related but separate mechanisms.

**First role: selecting configuration.** When the **prod** profile is active, Spring Boot can load **application-prod.yml** alongside **application.yml**. When **eu** is also active, it can additionally load **application-eu.yml** and matching conditional YAML documents.

**Second role: selecting beans.** The **@Profile("prod")** annotation can ensure a configuration or bean is registered only when the prod profile is in effect. This is a decision about the composition of the ApplicationContext.

A profile **is not an isolated application**. For example, prod and metrics can be active together because one profile specifies the deployment environment while the other specifies an additional capability.

~~~text
A Spring Boot process
  |
  +-- Active profiles: prod, eu, metrics
  |
  +-- Config Data:
  |     application.yml
  |     application-prod.yml
  |     application-eu.yml
  |     application-metrics.yml
  |
  +-- Bean conditions:
        @Profile("prod")
        @Profile("eu")
        @Profile("metrics")
        @Profile("prod & eu")
~~~

The diagram shows the sources that can be considered. A file that does not exist does not appear automatically, and profile-specific documents are also subject to the application's specific search, import, and location rules.

**An important principle:** profile order matters when resolving **overlapping configuration keys** across profile-specific documents at the same precedence tier. That order **does not make** @Profile("prod") take bean-creation priority over @Profile("eu").

## 2. Activating multiple profiles with spring.profiles.active

The value of **spring.profiles.active** can contain a comma-separated list of profile names:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu,metrics
~~~

Common sources:

~~~properties
# application.properties (non-profile-specific document)
spring.profiles.active=prod,eu,metrics
~~~

~~~yaml
# application.yml (base document)
spring:
  profiles:
    active: prod,eu,metrics
~~~

~~~bash
# Linux/macOS: environment variable supplied to the process
SPRING_PROFILES_ACTIVE=prod,eu,metrics java -jar demo.jar
~~~

~~~bash
# JVM system property must precede -jar
java -Dspring.profiles.active=prod,eu,metrics -jar demo.jar
~~~

~~~powershell
# Windows PowerShell
$env:SPRING_PROFILES_ACTIVE = "prod,eu,metrics"
java -jar demo.jar
~~~

The list is a set of effective profile names in activation order, **not a single profile name containing commas**. Commas act as separators.

When passed through Docker or Kubernetes, the same logical property name applies:

~~~bash
docker run --rm -e SPRING_PROFILES_ACTIVE=prod,eu demo-image
~~~

~~~yaml
# Part of a Pod configuration
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod,eu"
~~~

Declaring profiles in a container environment does not alter Spring Boot's precedence rules; the container simply supplies an input source.

### 2.1. When spring.profiles.active appears in multiple places

Suppose:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

Yet the application is launched with:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu
~~~

In a standard source configuration, command-line arguments take higher precedence than values from application.yml. The active list comes from the higher-precedence argument, namely **prod,eu**. It does not automatically append **dev** to **prod,eu** just because both sources declare **spring.profiles.active**.

Similarly, when also using an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=dev java -jar demo.jar --spring.profiles.active=prod,eu
~~~

Standard command-line arguments beat environment variables for the **spring.profiles.active** property, so the active list from this property is **prod,eu**, unless the application customizes handling or a higher-precedence source exists.

**Distinguish two meanings of commas:**

- Commas **inside a single spring.profiles.active value** create a multi-profile list.
- Two **spring.profiles.active values across two PropertySources** normally follow source precedence rules and are not merged into a combined list by default.

## 3. Baseline example: which profile overrides which?

Create three configuration files.

~~~yaml
# src/main/resources/application.yml
app:
  stage: base
  message: "Hello from base"
  timeout: 10s
  region: global
~~~

~~~yaml
# src/main/resources/application-prod.yml
app:
  stage: production
  message: "Hello from prod"
  timeout: 25s
~~~

~~~yaml
# src/main/resources/application-live.yml
app:
  message: "Hello from live"
  timeout: 40s
  region: primary
~~~

Run:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,live
~~~

When files are loaded via the default Config Data mechanism with no higher-precedence sources, **live** comes after **prod**, so overlapping keys in **application-live.yml** are chosen.

| Property | Base | prod | live | Effective value |
| --- | --- | --- | --- | --- |
| app.stage | base | production | Absent | **production** |
| app.message | Hello from base | Hello from prod | Hello from live | **Hello from live** |
| app.timeout | 10s | 25s | 40s | **40s** |
| app.region | global | Absent | primary | **primary** |

Notice: a later file **does not erase all properties** from an earlier file. It overrides matching keys, while keys not declared in the higher-precedence file continue taking values from the base file or another profile.

### 3.1. Reversing profile order

Run again:

~~~bash
java -jar demo.jar --spring.profiles.active=live,prod
~~~

With those exact same three files, the application can receive:

| Property | prod,live | live,prod |
| --- | --- | --- |
| app.stage | production | production |
| app.message | Hello from live | Hello from prod |
| app.timeout | 40s | 25s |
| app.region | primary | primary |

This is the most direct way to understand **last-wins** across profile-specific config files of equal precedence: changing the list order when keys overlap can change the winning value.

Avoid the extreme conclusion that “the last profile always wins across the entire application.” It only wins overlapping keys within **the scope of profile documents compared under the same precedence rules**; other sources such as CLI arguments or higher-precedence locations can decide the final outcome.

### 3.2. When a profile-specific file does not exist

If only application.yml and application-prod.yml exist while **prod,live** are active, Spring Boot can still start and use the documents it finds. The absence of **application-live.yml** under standard profile lookup does not force the application to fail. It simply means there are no properties from that file.

However, if a document has **spring.config.import** pointing to a required missing location, import failure rules can still halt the application. Do not confuse “an optional profile file does not exist” with “a required import location does not exist.”

## 4. Profile order is one part of PropertySource order

Expand the example with overlapping values in an environment variable, a JVM property, and a command-line argument:

~~~bash
APP_TIMEOUT=50s java -Dapp.timeout=60s -jar demo.jar   --spring.profiles.active=prod,live   --app.timeout=70s
~~~

In Bash syntax, a trailing **\** is used for line continuation. In other shells, enter the command on one line or use the appropriate line-continuation syntax.

With these sources and standard Spring Boot behavior:

| Source | app.timeout value | Relative precedence in example |
| --- | --- | --- |
| application.yml | 10s | Base source |
| application-prod.yml | 25s | prod profile file |
| application-live.yml | 40s | live profile file, beats prod |
| APP_TIMEOUT | 50s | Environment variable, beats Config Data |
| -Dapp.timeout | 60s | JVM system property, beats environment variable |
| --app.timeout | 70s | Command-line property, beats the sources above |

The result of **Environment.getProperty("app.timeout")** in this run is **70s**. Changing **prod,live** to **live,prod** does not alter the outcome because **--app.timeout=70s** still holds higher precedence.

To clearly observe the effect of profile order, remove external overrides or pick a key declared only inside profile files. Looking only at a property currently overridden by the CLI can mislead learners into thinking Spring Boot ignores profile order.

Spring Boot has additional PropertySource types such as **SPRING_APPLICATION_JSON**, test sources, and DevTools sources. The table above shows only the sources present in the illustrative scenario.

## 5. Active profiles vs. default profiles

When no active profile is enabled, Spring uses **default profiles** for matching conditions. Normally the default profile name is **default**.

You can change the default profile list with:

~~~yaml
# application.yml
spring:
  profiles:
    default: local
~~~

When **there is no explicit active profile**, configuration and conditions for the default profile **local** can apply. If you run:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

then **prod** is active, so the default profiles set is not applied as it would be when no active profile exists.

Notably, the name **default** is not a mandatory alias for **dev**, nor is it a “no configuration at all” state. The base **application.yml** file can still be loaded whether active profiles are present or not.

You can configure:

~~~properties
spring.profiles.default=none
~~~

This disables the usual default profile selection behavior by using the special name **none** instead of defaulting to activating a profile named **default**.

**When teaching or operating**, distinguish:

- **No explicit active profile**: the application can use default profiles.
- **Active profiles present**: the application evaluates the supplied active profiles rather than relying on default profiles.
- **No application-default.yml file**: does not prevent Spring from loading the base application.yml.

## 6. How does spring.profiles.include add profiles?

The **spring.profiles.include** property is used when a configuration needs to **add auxiliary profiles** alongside profiles activated via **spring.profiles.active**.

Example:

~~~yaml
# application.yml
spring:
  profiles:
    include:
      - observability
      - audit
~~~

Run:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

By intent, the application's effective profile set contains **prod** along with **observability** and **audit**. This avoids repeating observability,audit on every launch command.

**Include is an additive operation**, different from declaring overlapping **spring.profiles.active** across two sources. Moreover, Spring Boot processes **spring.profiles.include** per PropertySource; do not infer from one active value beating another source that include follows identical override rules.

Example profile-specific files:

~~~yaml
# application-observability.yml
management:
  metrics:
    tags:
      service: orders
~~~

~~~yaml
# application-audit.yml
app:
  audit:
    enabled: true
~~~

Together with prod, these two additional profiles can bring their configuration into the environment.

### 6.1. Do not place include inside a profile-activated document

An error-prone pattern:

~~~yaml
# application-prod.yml: example to avoid
spring:
  profiles:
    include: audit
~~~

Properties controlling profile activation such as **spring.profiles.active**, **spring.profiles.default**, and **spring.profiles.include** have placement restrictions in Config Data. Spring Boot requires them in **non-profile-specific documents**; they may not be used as a chained profile-activation mechanism inside a file dedicated to prod or activated by **spring.config.activate.on-profile**.

If you want “selecting prod automatically brings in audit,” see **profile groups** in the next section. That mechanism lets a business-level profile expand into concrete profiles.

### 6.2. Order when using include

When using include, included profiles are added before active profiles under Spring Boot's processing rules. However, final configuration order can also be affected by **location groups**, multiple Config Data documents, imports, and expanded profiles.

Therefore, in complex systems, do not take a declaration string in one file and calculate full precedence by hand. Inspect the effective profile set and PropertySources in the running environment. This is especially important when multiple profiles define a critical property like a database URL, port, or timeout.

## 7. spring.profiles.group: grouping profiles under a meaningful name

If you want to activate several profiles that normally go together using one short name, you can use **spring.profiles.group**.

~~~yaml
# application.yml, non-profile-specific document
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - metrics
~~~

When running:

~~~bash
java -jar demo.jar --spring.profiles.active=production
~~~

Spring Boot expands the group so member profiles **proddb**, **prodmq**, and **metrics** are activated as well. That lets operators know one stable name at the deployment tier while the application manages detailed configuration components.

An example division of roles:

| Profile | Typical purpose |
| --- | --- |
| production | Group name used in deployment commands |
| proddb | Production datasource configuration |
| prodmq | Message broker configuration |
| metrics | Observability configuration |

Corresponding files can exist:

~~~text
src/main/resources/
  application.yml
  application-production.yml
  application-proddb.yml
  application-prodmq.yml
  application-metrics.yml
~~~

In practice, **profile groups are expanded according to Spring Boot's profile processing rules**. When a key appears in multiple documents activated by a group, property source ordering still decides the winning value. Groups do not automatically “merge YAML” with any special rule for databases or metrics.

### 7.1. How group differs from include and activate.on-profile

- **group**: activating the group name triggers activation of its member profiles.
- **include**: unconditionally adds profiles to the effective set from a configuration property.
- **activate.on-profile**: sets a condition for **a configuration document** to take effect when a profile expression matches. It does not itself activate profiles in the expression.

For example, writing only:

~~~yaml
spring:
  config:
    activate:
      on-profile: production
~~~

does **not** make **production** an active profile. This document is only activated when the condition already matches the application's effective profiles.

Do not place **spring.profiles.group** inside a profile-specific document; group definitions must belong to non-profile-specific configuration documents.

## 8. Multi-document YAML and spring.config.activate.on-profile

A single application.yml file can hold multiple documents separated by **---**. Later documents can specify profile activation conditions.

~~~yaml
# application.yml: base document
app:
  client:
    timeout: 5s
    mode: local

---
spring:
  config:
    activate:
      on-profile: prod
app:
  client:
    timeout: 20s
    mode: secure

---
spring:
  config:
    activate:
      on-profile: eu
app:
  client:
    timeout: 25s
~~~

In this example:

- The first document has no condition, so it serves as base configuration.
- The second document takes effect when profile **prod** matches.
- The third document takes effect when profile **eu** matches.

If both prod and eu are active, both conditional documents can participate in loading. With documents in the same file processed in normal order, **a later document can override overlapping properties**; here app.client.timeout can be **25s**, while app.client.mode remains **secure**.

Subtle point: **YAML document order** also affects precedence; you cannot mechanically apply “last profile name wins” to every scenario if two profiles appear in multi-part YAML documents or across different locations.

### 8.1. Profile expressions

The **spring.config.activate.on-profile** condition can be a profile expression:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod & eu"
app:
  tax:
    regime: eu-production
~~~

This document takes effect only when **both prod and eu** are active simultaneously. With **prod** alone and no **eu**, the condition does not match.

OR example:

~~~yaml
spring:
  config:
    activate:
      on-profile: "dev | test"
app:
  remote:
    mock: true
~~~

The document applies if dev **or** test is active. The **!** operator expresses negation in profile expressions, such as **!prod**. For complex expressions, use quotes in YAML and appropriate parentheses to express the logic clearly.

**Distinction:** a document with **on-profile: "prod & eu"** does not create those two profiles; it only reads the already-determined profile state.

## 9. @Profile selects beans, not which configuration source wins

Suppose there are two service implementations:

~~~java
public interface PaymentGateway {
    String provider();
}
~~~

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
class FakePaymentGateway implements PaymentGateway {
    @Override
    public String provider() {
        return "fake";
    }
}
~~~

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
class RealPaymentGateway implements PaymentGateway {
    @Override
    public String provider() {
        return "real";
    }
}
~~~

When only **dev** is active, FakePaymentGateway can be registered. When only **prod** is active, RealPaymentGateway can be registered.

However, if **dev,prod** are both active, **both @Profile conditions match**. If the application injects a single PaymentGateway with no disambiguation, Spring can fail with **NoUniqueBeanDefinitionException** (or an equivalent dependency error) because two matching beans exist.

**The order dev,prod does not automatically pick RealPaymentGateway over FakePaymentGateway.** Bean selection depends on registration conditions and dependency resolution mechanisms such as **@Primary**, **@Qualifier**, bean names, or designing conditions so the two beans never appear together.

### 9.1. OR, AND, and NOT in @Profile

~~~java
@Profile({"dev", "test"})
class DevelopmentToolsConfiguration {
}
~~~

An annotation with the array **{"dev", "test"}** means **dev or test**, not requiring both.

To require both:

~~~java
@Profile("prod & eu")
class EuProductionConfiguration {
}
~~~

To apply only when prod is absent:

~~~java
@Profile("!prod")
class NonProductionConfiguration {
}
~~~

Note: only annotations on appropriate classes/configurations or methods control bean registration. Loading an application-eu.yml file **does not automatically decide** which bean has @Primary.

### 9.2. Profiles are startup conditions, not hot-swap switches

Standard @Profile conditions are evaluated while building the ApplicationContext. Changing system values after the application is already running does not cause Spring to automatically remove old beans, create new beans, or reload all Config Data for a new profile list.

To reliably change the active profile set, update startup configuration and restart the application via your deployment workflow. If an application has a dedicated refresh mechanism, evaluate that mechanism's contract rather than extrapolating from default @Profile behavior.

## 10. Override order also depends on configuration locations

In Spring Boot, profile-specific files live within the **Config Data** system. Beyond profile order, Spring Boot also applies precedence rules based on where files are found.

Suppose an application has:

~~~text
Inside JAR:
  classpath:/application.yml
  classpath:/application-prod.yml

Outside JAR:
  ./config/application.yml
  ./config/application-prod.yml
~~~

Documents from higher-precedence locations can override documents at lower-precedence locations. Therefore, if a key exists in both classpath and external configuration files, looking at profile names alone is insufficient to determine the final value.

You can specify:

~~~bash
java -jar demo.jar   --spring.profiles.active=prod,eu   --spring.config.additional-location=optional:file:./site-config/
~~~

Then files in site-config can participate after default locations according to additional-location precedence order. If those files share keys with packaged files, results can differ from running the JAR alone.

### 10.1. Locations and location groups

**spring.config.location** replaces the default search locations; **spring.config.additional-location** adds search locations. In particular, **,** and **;** in a location list define ordering and location groups.

In scenarios with multiple active profiles, where profile-specific files sit inside **location groups** affects processing order. Two launches with the same **prod,eu** yet different location groups can still produce PropertySources in different orders.

Examples of location declarations with different meanings:

~~~text
classpath:/cfg/,file:./external/
classpath:/cfg/;file:./external/
~~~

Do not deduce a winning value solely from profile names when multiple locations or imports are involved. To diagnose, identify **all loaded documents and their precedence order**, then locate where the key in question appears.

### 10.2. spring.config.import also creates precedence

A configuration file can use:

~~~yaml
spring:
  config:
    import: "optional:file:./config/overrides.yml"
app:
  timeout: 15s
~~~

Under standard Config Data rules, an imported file has higher precedence than the document declaring the import. If another profile-specific file or imported file also defines app.timeout, you must inspect the import, profile, location, and source order relationships; reading the **spring.profiles.active** string alone is not enough.

## 11. Lists and Maps when multiple profiles declare configuration

For a scalar such as app.timeout, “higher-precedence source wins” is usually intuitive. For **List** and **Map** structures, binding behavior needs separate attention.

### 11.1. Lists are usually replaced, not appended element by element

Example:

~~~yaml
# application.yml
app:
  servers:
    - host: alpha.example.test
      port: 9001
    - host: beta.example.test
      port: 9002
~~~

~~~yaml
# application-prod.yml
app:
  servers:
    - host: production.example.test
      port: 9443
~~~

When binding a list across PropertySources of different precedence, Spring Boot typically uses **the list from the higher-precedence source**, rather than concatenating into three elements. With the prod profile, you may receive a list containing only production.example.test.

Do not assume index 1 elements from the base file will always remain when the profile only declares index 0. If you need a list with all elements, supply the full list in the winning source or define explicit merging logic in code.

### 11.2. Maps can combine keys

Example:

~~~yaml
# application.yml
app:
  labels:
    owner: platform
    region: global
~~~

~~~yaml
# application-prod.yml
app:
  labels:
    region: asia
    tier: critical
~~~

When bound to **Map<String, String>**, Spring Boot can combine distinct keys across configuration sources: owner from the base file, region from the higher-precedence source, and tier from the prod profile. These rules are also affected by map/nested value types and specific key names.

| Map key | Base | prod | Illustrative result |
| --- | --- | --- | --- |
| owner | platform | Absent | platform |
| region | global | asia | asia |
| tier | Absent | critical | critical |

Do not apply list-replacement rules verbatim to maps; nor extrapolate from a simple Map to all nested structures.

### 11.3. Empty values and null do not automatically delete lower sources

A profile might declare **app.name: ""**, **app.name:**, or **app.name: null**. They behave differently during YAML parsing and PropertySource conversion; do not assume null automatically “deletes” all prior configuration values.

If the goal is to disable a feature per profile, an explicit flag is much clearer:

~~~yaml
# application-prod.yml
app:
  notifications:
    enabled: false
~~~

When handling required values, pair **@ConfigurationProperties** with appropriate validation to catch missing or blank values early.

## 12. Rules for placing spring.profiles.active in Config Data

You can place **spring.profiles.active** in a non-profile-specific base document:

~~~yaml
# application.yml: base document
spring:
  profiles:
    active: dev
~~~

However, do not write:

~~~yaml
# application-prod.yml: invalid placement configuration
spring:
  profiles:
    active: metrics
~~~

Similarly, inside a YAML document activated by **spring.config.activate.on-profile**, you may not use **spring.profiles.active** or **spring.profiles.default** to alter the profile list. Spring Boot enforces this constraint to prevent profile activation from forming cycles or depending on a document that has not yet been activated.

An example to avoid:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: eu
~~~

The snippet above is not a valid way to say “when prod, enable eu.” If you want to expand one profile into multiple fixed related profiles, define **spring.profiles.group** in a non-profile-specific base document.

## 13. Organizing profiles as a project grows

A project may have three independent configuration dimensions:

- **Environment:** dev, staging, prod.
- **Region:** eu, apac, us.
- **Operational features:** metrics, tracing, audit.

If you create a combined profile for every combination, file count and duplication explode quickly. You can declare files by role, for example:

~~~text
application.yml
application-dev.yml
application-staging.yml
application-prod.yml
application-eu.yml
application-apac.yml
application-metrics.yml
application-audit.yml
~~~

Then activate:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu,metrics
~~~

This works well when each profile holds properties that **do not overlap unintentionally**. If profiles frequently define the same sensitive key, establish ownership conventions:

| Key category | Where to manage clearly |
| --- | --- |
| Database or broker addresses | Environment profile / designated deployment source |
| Regional endpoints, locale, data region | Regional profile |
| Toggling system observability | Feature profile or operational configuration |
| Safe, environment-independent defaults | application.yml |
| Secrets, credentials | Dedicated secret source and proper access controls |

This is an organizational practice to reduce accidental overrides, not a rule automatically enforced by Spring Boot. Even with clean separation, an environment variable or startup argument can still override file values by source precedence.

### 13.1. Do not use profiles for every feature

Profiles fit a group of configurations or beans selected at startup. However, if a feature flag must change while the application is running without restarting, relying on @Profile may not meet the requirement. In that case, consider a dedicated feature-flag mechanism with well-defined update behavior.

Nor are profiles a secret-protection mechanism. Putting a password in application-prod.yml and enabling only the prod profile does not prevent that information from leaking in source code or build artifacts.

## 14. How to inspect active profiles at runtime

Do not guess solely from filenames. Spring Environment provides an API reporting active profiles:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ProfileInspector implements ApplicationRunner {

    private final Environment environment;

    ProfileInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Active profiles: "
            + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("Default profiles: "
            + Arrays.toString(environment.getDefaultProfiles()));
        System.out.println("app.message: "
            + environment.getProperty("app.message"));
        System.out.println("app.timeout: "
            + environment.getProperty("app.timeout"));
    }
}
~~~

This example answers two independent questions:

1. **Which profiles are currently effective?** Read from getActiveProfiles().
2. **What is the final configuration value?** Read from getProperty(...).

Do not treat the value of a single property as sufficient proof of the profile list. If a CLI source overrides a property, that value may reveal nothing about which profile was listed last.

### 14.1. Displaying PropertySource names

When tracking down why a value won, you can iterate over the PropertySource list in **ConfigurableEnvironment**:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
class PropertySourceNames implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    PropertySourceNames(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Source names usually identify loaded files or locations. The PropertySource order inside Environment reflects runtime lookup order. When tracing a specific key, account for relaxed binding and how each PropertySource represents key names, so calling getProperty directly on an individual source is not always equivalent to Environment.getProperty(...).

**Do not print all values of every PropertySource to logs**, because configuration files can contain passwords, API tokens, or sensitive connection details.

### 14.2. Using Actuator when appropriately configured

In systems with Spring Boot Actuator, the env endpoint can show property names and configuration sources, while the conditions endpoint helps inspect bean creation conditions. These endpoints must have appropriate access restrictions; sensitive data can be masked.

Do not expose environment details publicly just to verify profile order. When diagnostics are needed, inspect results in a secured environment or use code that prints only non-sensitive keys.

## 15. Common real-world mistakes

### 15.1. Changing profile order without seeing the value change

**Common cause:** the key is being overridden by a command-line property, JVM system property, environment variable, or Config Data from a higher-precedence location.

**How to check:** test a key present only in profile files; log Environment.getProperty(...); inspect the property's source at runtime.

### 15.2. Thinking the last profile “turns off” beans from earlier profiles

**Cause:** confusing config-file precedence with @Profile precedence.

**How to check:** inspect each bean's @Profile condition. With **dev,prod**, both the @Profile("dev") bean and the @Profile("prod") bean can be created simultaneously. Design mutually exclusive conditions or explicit bean resolution if exactly one implementation is required.

### 15.3. Writing active profiles in application-prod.yml

**Cause:** placing **spring.profiles.active** in a profile-specific document. That placement is not supported.

**How to fix:** move activation to a startup source or base document; use profile groups if prod should automatically expand into auxiliary profiles.

### 15.4. Assuming two spring.profiles.active values automatically add together

**Cause:** confusing PropertySource precedence with the include mechanism.

**How to check:** inspect spring.profiles.active at the highest-precedence source, then inspect include/group and the actual getActiveProfiles() list.

### 15.5. Defining a profile group without seeing the expected profiles

**Cause:** the group was declared in a document at an invalid location, the group name does not match the activated profile, or member profile files do not exist.

**How to check:** place the group in the base document, verify the group name and getActiveProfiles(); then verify configuration documents actually loaded.

### 15.6. Valid YAML file yet keys disappear with multiple profiles

**Cause:** YAML structure changed, indentation error, or a list was replaced instead of merged.

**How to check:** compare full key names and binding types in @ConfigurationProperties; distinguish scalars, Lists, and Maps.

### 15.7. Production environment running with the default profile

**Cause:** SPRING_PROFILES_ACTIVE was not actually supplied to the process, the launcher omitted the argument, or the variable name was misspelled.

**How to check:** observe getActiveProfiles() right at startup and compare with the deployment command. Never infer solely from namespace name, container name, or environment label.

### 15.8. Analyzing order in multi-document YAML solely by profile order

**Cause:** assuming every on-profile document in a file is re-ordered according to the active profiles string.

**How to check:** examine **YAML document order**, location groups, and imports as well. The on-profile condition decides whether a document participates; precedence also depends on document position in Config Data.

## 16. Practice: predict and verify

### Exercise 1 — Reordering two profiles

Files:

~~~properties
# application.properties
demo.value=base
demo.owner=core
~~~

~~~properties
# application-dev.properties
demo.value=dev
demo.log-level=verbose
~~~

~~~properties
# application-qa.properties
demo.value=qa
demo.owner=quality
~~~

Run A:

~~~bash
java -jar demo.jar --spring.profiles.active=dev,qa
~~~

Run B:

~~~bash
java -jar demo.jar --spring.profiles.active=qa,dev
~~~

Predict **demo.value**, **demo.owner**, and **demo.log-level**.

| Key | dev,qa | qa,dev |
| --- | --- | --- |
| demo.value | qa | dev |
| demo.owner | quality | quality |
| demo.log-level | verbose | verbose |

**Explanation:** demo.value appears in both profile files so it changes with whichever profile comes later; demo.owner is overridden only by QA; demo.log-level is declared only by dev. A later profile does not erase keys it did not declare.

### Exercise 2 — Profiles vs. CLI override

Config files:

~~~yaml
# application-prod.yml
app:
  timeout: 20s
~~~

~~~yaml
# application-eu.yml
app:
  timeout: 30s
~~~

Launch command:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu --app.timeout=90s
~~~

Question: what is the effective timeout assuming no higher-precedence source? **90s**, because of the CLI override. Remove **--app.timeout=90s** and run again: **30s**, because eu comes after prod in this simple Config Data example.

### Exercise 3 — OR and AND in @Profile

~~~java
@Profile({"dev", "test"})
class ToolsConfiguration {
}

@Profile("prod & eu")
class EuProductionConfiguration {
}
~~~

- Active profiles **dev,test**: ToolsConfiguration matches, EuProductionConfiguration does not.
- Active profiles **prod,eu**: EuProductionConfiguration matches, ToolsConfiguration does not.
- Active profiles **dev,prod,eu**: both configurations can match.

Do not confuse **@Profile({"dev", "test"})** with an AND condition.

### Exercise 4 — Group and include

~~~yaml
spring:
  profiles:
    include:
      - audit
    group:
      production:
        - proddb
        - prodmq
~~~

Run:

~~~bash
java -jar demo.jar --spring.profiles.active=production
~~~

Use Environment.getActiveProfiles() to inspect the effective list, confirming **production**, member profiles **proddb** and **prodmq**, and included profile **audit**. Then create application-proddb.yml and application-audit.yml with the same test key to observe the actual PropertySource order effect.

The goal is to distinguish **group names**, **the include mechanism**, and **source precedence**, rather than guessing order from filenames.

### Exercise 5 — YAML document order

~~~yaml
demo:
  mode: base
---
spring:
  config:
    activate:
      on-profile: prod
demo:
  mode: production
---
spring:
  config:
    activate:
      on-profile: eu
demo:
  mode: european
~~~

With **prod,eu** and no other overrides, both conditional documents match, and the final document can decide **demo.mode=european** in this example's standard Config Data processing.

Swapping the positions of the two profile documents without changing the active profile string is a separate test to observe the effect of **document order**.

## 17. Troubleshooting workflow when configuration does not match expectations

Follow this order to avoid guessing:

1. **Identify the exact property name that is wrong**, such as app.timeout, and record the expected value.
2. **Read the actual active profiles** via Environment.getActiveProfiles() and default profiles if needed.
3. **Inspect launch commands and environment variables**, identifying which source sets spring.profiles.active and whether include/group applies.
4. **List all relevant Config Data documents**, including application.yml, profile files, multi-document YAML, locations, and imports.
5. **Mark every place the key is declared**, and apply source precedence instead of looking solely at filenames.
6. **Check binding data types**, especially List, Map, Duration, boolean, or empty/null values.
7. **For bean errors**, inspect each bean's @Profile condition and Spring's bean selection rules; do not apply “last profile wins” to bean creation.
8. **Verify runtime values** through Environment, configuration beans, or secured observability tools.

If a profile change prevents the application from starting, distinguish **Config Data loading errors**, **type conversion/validation errors**, and **bean registration/injection errors**. These categories have different root causes and fixes even though all appear after changing active profiles.

## 18. Key takeaways

- **spring.profiles.active** can activate multiple profiles with a comma-separated list, such as **prod,eu,metrics**.
- When **profile-specific configuration files at the same precedence level** define the same key, **a profile listed later can override values from an earlier profile**.
- Last-wins across profiles **does not bypass Spring Environment precedence**. CLI arguments, JVM properties, environment variables, locations, and imports can change the effective value.
- **spring.profiles.include** adds profiles; **spring.profiles.group** expands one profile name into multiple members; **spring.config.activate.on-profile** only decides whether a Config Data document is activated.
- **Default profiles** apply when there are no active profiles; they differ from an explicitly specified active list.
- **@Profile** determines which beans are eligible for registration. Two beans with different profile conditions can still coexist when both profiles are active.
- **Lists** and **Maps** follow different binding rules when multiple configuration sources participate.
- To know what happened in an actual run, compare **getActiveProfiles()**, **Environment.getProperty(...)**, and **PropertySource order**.

When an application uses multiple profiles, the reliable mental model is **determine which profiles are active → determine which documents are loaded → apply source precedence per key → check bean conditions separately**. This approach explains both overridden configuration and cases where multiple beans are created together.