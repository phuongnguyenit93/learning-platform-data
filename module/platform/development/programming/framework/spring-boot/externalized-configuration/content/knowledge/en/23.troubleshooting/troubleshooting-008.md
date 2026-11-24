# Troubleshooting Inactive Profiles and Configuration Placed in the Wrong Document

In Spring Boot Externalized Configuration, profiles select configuration by environment or capability: `dev`, `test`, `staging`, `prod`. An application can read a common `application.yml`, `application-prod.yml` for production, YAML documents conditioned with `spring.config.activate.on-profile`, imported Config Data files, and runtime-supplied `PropertySource`s.

When a developer sees a value that does not match a profile file, that **does not prove the profile was turned off**. Many causes exist: the profile is inactive, the file sits outside Config Data search paths, activation lives in the wrong YAML document, profile-control keys are placed in an invalid document, a higher-precedence source overrides it, or `@Profile` and `@ConditionalOnProperty` beans are not registered.

This lesson presents a diagnostic workflow from **actual profiles → loaded documents → PropertySource order → bound values → bean creation conditions**. Examples assume Spring Boot 3.x and Java 17+, though always verify against your project's version when deploying.

## 1. Four Questions to Answer Before Editing YAML

1. **Which application is running?** Check process, JAR/image, pod revision, and startup timestamp.
2. **Which profiles are active?** Read startup logs, launch command, or `Environment#getActiveProfiles()`.
3. **Which documents were loaded?** Check filenames, locations, imports, and each document's `on-profile`.
4. **Which source wins for the specific key?** Check precedence across CLI, environment, Config Data, and binding.

Only after answering these four questions should you inspect `@Profile`, component scanning, validation, or List/Map binding. A "wrong" value can be completely valid behavior under precedence rules.

## 2. Example of application.yml and Profile-Specific Files

Structure:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
~~~

Common config:

~~~yaml
# application.yml
catalog:
  endpoint: "https://catalog.example.invalid"
  timeout: 5s
  diagnostic-mode: false
~~~

Dev:

~~~yaml
# application-dev.yml
catalog:
  endpoint: "http://localhost:9090"
  timeout: 1s
  diagnostic-mode: true
~~~

Prod:

~~~yaml
# application-prod.yml
catalog:
  endpoint: "https://prod-catalog.example.invalid"
  timeout: 3s
  diagnostic-mode: false
~~~

If `dev` is active with no other overriding source, the endpoint is localhost and timeout is 1s. With `prod`, the production endpoint and 3s timeout can be used. With no matching active profile, values from the common file can be used.

| Profiles | Expected timeout | Diagnostic mode |
| --- | --- | --- |
| Neither dev nor prod active | 5s | false |
| dev | 1s | true |
| prod | 3s | false |

These are **expectations for a simple source set**, not guarantees if Config Data imports, environment variables, CLI, or system properties define the same keys.

## 3. Activating Profiles via Command-Line Arguments

When running an executable JAR:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Production:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Multiple profiles:

~~~bash
java -jar app.jar --spring.profiles.active=staging,metrics
~~~

The `--spring.profiles.active=dev` syntax is a Spring Boot application argument, placed **after** the JAR name. A Java system property uses different syntax:

~~~bash
java -Dspring.profiles.active=dev -jar app.jar
~~~

`-Dspring.profiles.active=dev` is a JVM argument, placed **before** `-jar`. Putting it in the wrong IDE field (VM options vs. Program arguments) or wrong order can prevent the process from receiving the profile as expected.

Do not infer profiles from Git branch names, directory names, or container images: Spring knows only the runtime/configuration values it actually receives.

## 4. Activating via Environment Variables

In a POSIX shell:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
~~~

When running via Docker, Kubernetes, CI, or a service manager, verify the variable reaches **the exact Java process**, not merely that it exists in a manifest or pipeline editor.

Common mistakes:

- Misspelling `SPRING_PROFILES_ACTIVE`.
- Value containing unexpected whitespace or quotes.
- Variable passed only to a different container/job.
- Overridden by command line or system property.
- Pod not restarted after updating environment.
- App actually running an old artifact.
- Multiple replicas exist and logs read belong to another replica.

Profile selection should be managed by the deployment when a single artifact serves multiple environments.

## 5. Active and Default Profiles Differ

Spring Environment exposes:

~~~java
environment.getActiveProfiles();
environment.getDefaultProfiles();
~~~

`getActiveProfiles()` returns active profiles, possibly an empty array. `getDefaultProfiles()` returns default profiles used when no active profiles exist; by default it typically contains `default`.

Therefore, a message similar to:

~~~text
No active profile set, falling back to default profile...
~~~

is not necessarily an error. It does not mean `application.yml` was not loaded.

You can set a default profile in a non-profile-specific document:

~~~yaml
# application.yml, common document
spring:
  profiles:
    default: "local"
~~~

When `prod` is explicitly activated, the default profile does not replace it. Do not confuse "no active profile" with "no configuration."

## 6. Profile Filenames Must Match Exactly

Spring Boot normally searches for documents by convention:

~~~text
application-{profile}.properties
application-{profile}.yml
application-{profile}.yaml
~~~

If `prod` is active, `application-production.yml` does not automatically become `application-prod.yml`. Other variants like `application_prod.yml`, `Application-prod.yml`, or `application-prod.yml.txt` also cannot be assumed equivalent.

Check:

- Is the basename `application`?
- Does the profile suffix match the active name?
- File extension and letter casing.
- Is the file on the classpath, filesystem, or another Config Data location?
- Does the artifact actually contain the file?
- Do both `.properties` and `.yml` exist with the same basename?

Just because your IDE displays a file does not mean the running JAR/container finds it.

## 7. Multi-Document YAML and the --- Separator

One `application.yml` can hold multiple documents:

~~~yaml
app:
  greeting: "base"
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "dev"

app:
  greeting: "development"
  timeout: 1s

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  greeting: "production"
  timeout: 3s
~~~

Each section separated by `---` is a distinct YAML document. The common document is unconditional, the dev document takes effect only when the profile expression matches, and prod similarly.

Common mistakes:

- Missing `---`, leaving keys in the wrong document.
- Putting the common document after profile documents, altering expected precedence.
- Confusing one document's activation with a condition for the entire file.
- Nesting activation under a business prefix instead of the root.
- Misspelling `spring.config.activate.on-profile`.

Adopt a readable convention: common document first, conditional documents after, then test effective values.

## 8. on-profile Does Not Self-Activate a Profile

Example:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod"
~~~

Meaning: **this document is used only if the matching profile has already been selected**. It does not turn `prod` active by itself.

Distinguish three mechanisms:

| Mechanism | Responsibility |
| --- | --- |
| `spring.profiles.active` | Selects active profiles |
| `spring.config.activate.on-profile` | Decides which YAML document takes effect |
| `@Profile("prod")` | Decides which bean/configuration class is registered |

To make `prod` active, pass the profile from a valid bootstrap source:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Do not put `on-profile: prod` inside a document expecting it to load `application-prod.yml` automatically.

## 9. spring.profiles.active Must Not Be Placed in a Profile-Specific File

**Invalid** configuration:

~~~yaml
# application-prod.yml
spring:
  profiles:
    active: "prod"

app:
  mode: "production"
~~~

In modern Spring Boot Config Data, `spring.profiles.active` must reside in a valid **non-profile-specific** source/document. A file already carrying the `prod` suffix is not the place to self-enable `prod`.

Better configuration:

~~~yaml
# application-prod.yml
app:
  mode: "production"
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

A similar error occurs when `spring.profiles.active` sits inside a document containing `spring.config.activate.on-profile`:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod"
  profiles:
    active: "staging"
~~~

Boot can reject this during Config Data processing because a profile-activating property appeared in an invalid document. Do not try to fix this by disabling Bean Validation or altering `ignoreUnknownFields`.

## 10. Include, Default, and Group Also Have Placement Restrictions

Profile-set control keys such as:

- `spring.profiles.active`
- `spring.profiles.include`
- `spring.profiles.default`
- `spring.profiles.group`

must be declared in permitted documents, not profile-specific documents or documents conditioned by `spring.config.activate.on-profile`.

Example to avoid:

~~~yaml
# application-dev.yml
spring:
  profiles:
    include: "metrics"
~~~

If intentionally including profiles, place them in an appropriate common document:

~~~yaml
# application.yml
spring:
  profiles:
    include:
      - "metrics"
~~~

However, `include` changes the application-wide profile set. If the goal is merely enabling a monitoring bean, consider a dedicated property condition instead of pulling in an extra profile that might affect datasource or security configuration.

## 11. Profile Groups

Profile groups can be declared:

~~~yaml
# application.yml, common document
spring:
  profiles:
    group:
      production:
        - "database-prod"
        - "observability-prod"
~~~

When launched with:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Spring Boot can expand the `production` group so its member profiles become active together.

Keep in mind:

- Group definitions must be placed in valid locations.
- Groups do not automatically discover arbitrary files in the repository.
- If two member profiles define the same key, precedence still needs checking.
- Files like `application-database-prod.yml` must still live in supported Config Data locations.
- Test the final profile set and critical values, especially after changing group membership.

Do not place a group inside a document that is only loaded when that very group is already active.

## 12. on-profile Expressions

Spring supports profile expressions:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod & eu"

app:
  region-policy: "eu-production"
~~~

Or:

~~~yaml
spring:
  config:
    activate:
      on-profile: "dev | staging"

app:
  diagnostics: true
~~~

Operators and parentheses must follow the profile expression syntax of your Spring version. When conditions are simple, prefer `on-profile: "prod"` to avoid confusion.

If a document does not activate, verify the entire active profile set, not just the first name in `spring.profiles.active`. Never assume `production` matches `prod` by prefix.

## 13. Do Not Confuse Files in resources with Loaded Files

Suppose:

~~~text
src/main/resources/
  application.yml
  integrations/
    billing-prod.yml
~~~

Spring Boot does not load `billing-prod.yml` by default just because `prod` is active. An arbitrarily named file must be brought into Config Data properly, such as via `spring.config.import`:

~~~yaml
# application.yml
app:
  mode: "base"

---
spring:
  config:
    activate:
      on-profile: "prod"
    import: "classpath:integrations/billing-prod.yml"
~~~

If the prod document is inactive, the import inside it does not apply to other environments. Imports also have their own precedence: an imported document can take higher precedence than the document declaring the import on overlapping keys.

Do not add imports without understanding who owns the final value.

## 14. spring.config.name Can Change the Basename

Spring Boot looks for `application` by default. However, a process might run:

~~~bash
java -jar app.jar --spring.config.name=catalog
~~~

Then config files searched follow basename `catalog` instead of the `application-*.yml` files the developer is editing.

When a profile seems ineffective:

1. Check whether `spring.config.name` was supplied.
2. Check actual basenames in Config Data locations.
3. Check the profile suffix.
4. Check files inside the artifact and external directories.
5. Check whether higher sources override the key.

Do not conclude Binder is broken just because `application-prod.yml` goes unused in an app whose config name was changed.

## 15. location and additional-location Differ

`spring.config.location` specifies Config Data search locations, which can replace the default location set under Boot's mechanism. `spring.config.additional-location` adds locations alongside the defaults.

Example:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deployment-config/
~~~

If a system sets `spring.config.location` pointing solely to an external directory, default classpath files may no longer be searched as you expect.

Notes:

- Properties controlling search locations must be supplied early when Spring Boot bootstraps.
- `file:./...` depends on working directory.
- `classpath:` refers to classpath resources.
- `optional:` allows missing locations in supported cases; it does not make mandatory business values optional.
- Another location can pull in profile-specific variants with their own precedence.

When switching loading mechanisms, test overlapping-key cases too, not merely whether files exist.

## 16. @PropertySource Is Unreliable for Selecting Profiles

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:profiles.properties")
class ProfileSelectorConfiguration {}
~~~

In the resource:

~~~properties
spring.profiles.active=prod
~~~

`@PropertySource` is processed during ApplicationContext refresh, usually **too late** to reliably influence Boot's earlier decisions when finding Config Data and profile-specific documents.

To choose profiles, supply them from a proper bootstrap source such as CLI, environment, Java system property, or a valid common document.

Environment eventually holding a `spring.profiles.active` key does not prove profile-specific files were loaded by Boot from the start. Check lifecycle order rather than looking at a single property.

## 17. Profile Active Yet Value Still Wrong Due to Precedence

Prod file example:

~~~yaml
# application-prod.yml
app:
  timeout: 3s
~~~

Yet launched with:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.timeout=1s
~~~

Command-line argument `--app.timeout=1s` normally takes precedence over Config Data, so the final value can be 1s. The `prod` profile was activated and the prod file may have loaded fine.

Sources that can affect this:

- Command line.
- Java system properties.
- OS environment variables.
- `SPRING_APPLICATION_JSON`.
- Config Data imports.
- Another profile-specific file that is simultaneously active.
- Files in higher-precedence search locations.
- Test property sources.

When a value mismatches, trace **one specific key** instead of claiming the whole profile is not running.

## 18. Multiple Profiles and Last-Wins

Run:

~~~bash
java -jar app.jar --spring.profiles.active=dev,metrics
~~~

Can load both `application-dev.yml` and `application-metrics.yml`.

Example:

~~~yaml
# application-dev.yml
app:
  mode: "development"
~~~

~~~yaml
# application-metrics.yml
app:
  mode: "metrics"
~~~

For profile-specific Config Data within the same location group, profiles listed later can have higher precedence under last-wins rules. However, imports, location groups, and CLI/env sources can change the final value.

Do not rely on IDE file order, timestamps, or alphabetical order. Check the actual `PropertySources` order and typed bean.

## 19. List Replacement Can Be Mistaken for "Profile Not Loaded"

Common file:

~~~yaml
# application.yml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
    - name: "backup"
      url: "https://backup.example.invalid"
      timeout: 5s
~~~

Dev file:

~~~yaml
# application-dev.yml
routing:
  endpoints:
    - name: "local"
      url: "http://localhost:9090"
~~~

With `List<Endpoint>`, when the dev list wins, the new List typically replaces the entire common List. It can end up with just one element; `local`'s `timeout` **is not inherited** from `primary`.

This can be a sign **the profile worked properly**, yet the new configuration is incomplete. With `@NotNull Duration timeout` and nested validation, startup can fail.

If you want to override by name/ID while keeping fields from lower sources, consider `Map<String, Endpoint>` instead of List. For order-sensitive business Lists, declare the full effective sequence in the new profile.

## 20. Maps Can Combine Keys from Multiple Sources

Example:

~~~yaml
# application.yml
clients:
  endpoints:
    billing:
      url: "https://billing.example.invalid"
      timeout: 3s
    inventory:
      url: "https://inventory.example.invalid"
      timeout: 5s
~~~

Dev:

~~~yaml
# application-dev.yml
clients:
  endpoints:
    billing:
      url: "http://localhost:9090"
~~~

If Java binds a Map of nested objects, the `billing` entry can receive dev's URL and common's timeout, while `inventory` remains from common.

A key missing from dev YAML **does not prove the field will be null**; account for Java types, map merging, defaults, and property sources. This rule differs from List replacement. Thus reading a single file is insufficient to predict bound configuration.

## 21. @Profile Controls Beans, Not YAML Loading

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
class ProductionClientConfiguration {
}
~~~

If `prod` is inactive, this configuration class is not registered under the condition. Yet if `prod` is active and the bean is still missing, check:

- Is the class component-scanned/imported?
- Is the module/JAR on the classpath?
- Are there `@ConditionalOnProperty` or other conditions?
- Are auto-configuration or `@ConditionalOnMissingBean` involved?
- Did an earlier bean creation fail?
- Is the bean defined in a parent config class excluded by a condition?

Do not only edit `application-prod.yml` when the bug is an unscanned class.

## 22. @ConditionalOnProperty Is Not @Profile

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "billing",
    name = "enabled",
    havingValue = "true"
)
BillingClient billingClient() {
    return new BillingClient();
}
~~~

The bean depends on the effective value of `billing.enabled`. Even if `prod` is active, if CLI passes:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --billing.enabled=false
~~~

the bean will not appear. Verify the winning source for `billing.enabled` instead of asserting `prod` is inactive.

## 23. Wrong Prefix or Indentation

YAML:

~~~yaml
billing:
  client:
    endpoint: "https://billing.example.invalid"
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(URI endpoint) {}
~~~

Java looks for `billing.endpoint`, while YAML provides `billing.client.endpoint`. The profile may be active yet Binder lacks a value at the right key.

Fix to:

~~~java
@ConfigurationProperties(prefix = "billing.client")
public record BillingProperties(URI endpoint) {}
~~~

or change the YAML structure to match the real schema.

Adding `@Validated` and required constraints like `@NotNull` helps detect missing properties at startup. Register typed configuration beans via `@EnableConfigurationProperties` or proper scanning.

## 24. When Both .properties and .yml Exist with the Same Basename

If the same location has:

~~~text
application-prod.properties
application-prod.yml
~~~

Spring Boot defines precedence between these formats; in the same location, `.properties` typically takes precedence over YAML. A key in properties can shadow the key a developer just edited in YAML.

Avoid keeping two formats for the same purpose without good reason. If you must keep both, define key ownership, test final values, and inspect contents inside the JAR.

File modification timestamps do not determine source order in Spring Boot.

## 25. Inspecting Actual Resources Inside the JAR

Use:

~~~bash
jar tf build/libs/application.jar
~~~

or:

~~~bash
jar tf target/application.jar
~~~

In a Spring Boot executable JAR, resources typically appear as:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-prod.yml
~~~

If a file is missing:

- It might reside only in `src/test/resources`.
- The build has excludes/resource filtering.
- The app is running a different module/JAR.
- The container image was not rebuilt.
- Path/classpath differs from the IDE.
- Filename or casing differs.

If the file is mounted by deployment outside the JAR, check the volume and runtime filesystem instead of searching inside the artifact.

## 26. Observing Active/Default Profiles in the Application

A simple diagnostic:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ProfileDiagnostics {

    @Bean
    ApplicationRunner printProfiles(Environment environment) {
        return args -> {
            System.out.println(
                "Active profiles: " +
                Arrays.toString(environment.getActiveProfiles())
            );
            System.out.println(
                "Default profiles: " +
                Arrays.toString(environment.getDefaultProfiles())
            );
        };
    }
}
~~~

Never put secrets into logs. This code runs after the context is created, so it cannot directly help when the app fails during Config Data bootstrap. For early startup failures, read exceptions, location diagnostics, or write bootstrap tests.

## 27. Finding Which Sources Contain a Key Without Printing Values

With `ConfigurableEnvironment`:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

String key = "catalog.timeout";

for (PropertySource<?> source :
        environment.getPropertySources()) {
    if (source.containsProperty(key)) {
        System.out.println(source.getName());
    }
}
~~~

This snippet assumes the injected `environment` is a `ConfigurableEnvironment`. Source order in Environment helps analyze which key can win. For OS environment and relaxed property binding, direct canonical key lookup can differ from Binder; use appropriate tools if the key does not show up as expected.

Never print raw values or the whole Environment, as they can contain passwords, tokens, or sensitive paths. PropertySource names can also disclose system info; enable diagnostics only in controlled places.

## 28. Actuator and Diagnostic Logs

With secured Actuator, `/actuator/env` helps inspect property sources and `/actuator/configprops` helps inspect bound typed configuration beans. Never expose them publicly or enable broad `show-values` in production to debug.

To observe Config Data loading in local/test environments, use:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

This logger can record Config Data activity depending on Boot version. The `--debug` flag is useful for the condition evaluation report, yet **is not equivalent** to enabling TRACE across Config Data.

Enable logging only as long as needed, avoid dumping secrets, and restore normal levels once the issue is identified.

## 29. InvalidConfigDataPropertyException

Placing `spring.profiles.active` inside `application-prod.yml` or `spring.profiles.include` inside a document with `on-profile` can be rejected by Spring Boot with an error of the form:

~~~text
InvalidConfigDataPropertyException
~~~

When seeing this error, inspect the document and source location reported by the framework. Fix **the placement of profile-control keys**, rather than disabling Bean Validation.

If a project upgraded from an older Boot version, documents using legacy profile activation such as `spring.profiles: dev` should be reviewed and migrated to `spring.config.activate.on-profile` under modern Config Data rules.

## 30. Testing Profiles with @ActiveProfiles

Example:

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class CatalogDevTest {

    @Autowired
    CatalogProperties properties;

    @Test
    void loadsDevConfiguration() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofSeconds(1));
        assertThat(properties.diagnosticMode())
            .isTrue();
    }
}
~~~

Typed properties:

~~~java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        URI endpoint,
        Duration timeout,
        boolean diagnosticMode
) {}
~~~

For the test to work, `CatalogProperties` must be registered and test/application resources must match the example. JUnit/AssertJ/Spring Test imports may be needed per your project.

Remember that `@ActiveProfiles("dev")` in a test does not prove a production pod has `dev` active. Tests also have sources like `@TestPropertySource`, `@SpringBootTest(properties=...)`, and `@DynamicPropertySource` that can override Config Data. Assert bean values to verify results, not only active profile names.

## 31. Testing Invalid Document Placement Requires Real Config Data Bootstrap

If you want to prove Spring Boot rejects:

~~~yaml
# application-prod.yml — intentionally invalid fixture
spring:
  profiles:
    active: "prod"
~~~

the test must **load this file through the Config Data bootstrap mechanism** with `prod` active from a valid source.

`ApplicationContextRunner.withPropertyValues(...)` supplies raw properties directly and does not automatically test how Boot parses/activates YAML documents. Use an integration/bootstrap test with an isolated fixture verifying startup failure in the Config Data error category. A proper JUnit test should pass when confirming the expected failure.

Do not place intentionally broken files into main resources where other tests would fail unintentionally.

## 32. @SpringBootTest and ApplicationContextRunner Serve Different Goals

`@SpringBootTest` is suited for running an integration context with real profiles and files, then asserting bound values.

`ApplicationContextRunner` is suited for testing Binder, validation, and conditions in a minimal context. Writing only:

~~~java
new ApplicationContextRunner()
    .withPropertyValues(
        "catalog.timeout=2s"
    )
    .run(context -> {
        // assert
    });
~~~

does not prove `application-dev.yml` was located and loaded properly.

For bootstrap errors such as missing Config Data imports or invalid profile property placement, create a real bootstrap fixture rather than relying on a runner injecting property values directly.

## 33. Docker/Kubernetes: Changing Files Does Not Change an Old Process's Profile

Partial Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: registry.example.invalid/catalog:release
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
~~~

This is a structural example only, not a complete production manifest.

If you edit the manifest while the old pod keeps running, the Java process will not pick up the new variable automatically. Check apply/rollout, Deployment revision, pod template, image digest, runtime environment, and startup logs.

Likewise, updating a mounted ConfigMap or Secret file does not guarantee Spring Boot re-evaluates profiles or rebinds all beans. For bootstrap decisions, a controlled restart/rollout is usually much easier to verify.

## 34. Symptom and Cause Table

| Symptom | Likely cause | Where to check |
| --- | --- | --- |
| No active profile | No active profile supplied | CLI, env, JVM args |
| Prod file has no effect | Prod inactive or file not found | Filename, JAR, locations |
| Invalid Config Data property | active/include placed in wrong document | Move to common/runtime |
| on-profile does not fire | Wrong expression/document/indent | Check root key, `---` |
| Profile active yet value differs | Overridden by another source | PropertySources |
| List loses elements | List replacement | Check type and bound list |
| `@Profile` bean absent | Wrong condition or registration | Scanning, auto-config conditions |
| `@ConfigurationProperties` field null | Wrong prefix / missing field | Binding and validation |
| Fails only in IDE | Different VM/program args or cwd | Run configuration |
| Cluster uses old profile | Old process/revision | Rollout/pod inspection |
| Imported file does not exist | Wrong path/cwd or optional | Config Data locations |
| Editing YAML does not change value | `.properties` in same location or import wins | Per-key precedence |

## 35. Suggested Diagnostic Workflow

1. Identify the exact process/JAR/pod/revision.
2. Read runtime active/default profiles if the context can start.
3. Inspect command line, environment, and JVM system properties.
4. Check `spring.config.name/location/additional-location`.
5. Check exact file/profile suffix and artifact contents.
6. Check `---` and `spring.config.activate.on-profile` in each document.
7. Move profile-control keys out of profile-specific documents.
8. Check `spring.config.import`, `optional:`, and file paths.
9. Identify the PropertySource winning the problematic key.
10. Verify the bound typed bean, especially Lists/Maps and defaults.
11. Check `@Profile`/`@ConditionalOnProperty`/component scanning.
12. Add an integration or bootstrap regression test.
13. Redeploy and verify the new process receives the right value.
14. Never log secrets or open Actuator to unauthorized users.

## 36. Comprehensive Exercise

Given three files:

~~~yaml
# application.yml
app:
  mode: "base"
  retry-count: 2
~~~

~~~yaml
# application-dev.yml
app:
  mode: "development"
  retry-count: 1
~~~

~~~yaml
# application-prod.yml — intentionally invalid
spring:
  profiles:
    active: "prod"

app:
  mode: "production"
  retry-count: 3
~~~

**Question 1:** Running `--spring.profiles.active=dev`, does it automatically load prod?

**Answer:** No. The prod file is not selected merely for existing.

**Question 2:** Why is the prod file invalid?

**Answer:** `spring.profiles.active` sits inside a profile-specific file; it must be moved to a valid common source or supplied at runtime.

**Question 3:** After fixing, activating prod and adding `--app.retry-count=9`, what can retryCount be?

**Answer:** 9 from the command-line override under standard precedence.

**Question 4:** What if the prod file is renamed to `application-production.yml` while activating only `prod`?

**Answer:** Boot does not automatically treat the two suffixes as identical.

**Question 5:** A `@Profile("prod")` bean does not appear even with `prod` active—what should you check?

**Answer:** Component scanning, registration, other conditions, classpath, and startup errors.

**Question 6:** Dev List defines one element replacing a two-element common List. Does that prove the profile is broken?

**Answer:** No. This can be Binder's List replacement behavior when the profile works properly.

**Hands-on task:** fix the prod file, write an `AppProperties` typed bean, test dev/prod, test CLI override, and build a bootstrap fixture with an activation key in the wrong document to verify startup failure is handled cleanly.

## 37. Summary

Diagnosing "profile not activated" in Spring Boot goes beyond checking the `spring.profiles.active` line. Distinguish:

- **Profile activation:** `spring.profiles.active/default/include/group` from valid sources.
- **YAML document selection:** `spring.config.activate.on-profile`, with `---` separators and valid expressions.
- **Finding Config Data:** basename, profile suffix, locations, imports, and real artifacts.
- **Precedence order:** CLI/env/system properties and documents can shadow each other.
- **Binding:** prefix, data types, List replacement, Map merging, and validation.
- **Bean creation:** `@Profile`, `@ConditionalOnProperty`, classpath, and scanning.

Never place profile-control properties in profile-specific documents or conditionally activated documents. Never conclude a file was not loaded simply because one key received a different value. Verify the real profile, real file, winning source, and effective bean; finally lock behavior down with regression tests.

**Remember:** profiles are a **bootstrap** decision, documents are selected by **Config Data**, and final values depend on **PropertySource precedence**. Diagnosing layer by layer prevents blind config edits and reduces the risk of deploying into the wrong environment.
