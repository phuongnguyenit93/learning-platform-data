# Cross-Checking Version-Specific Documentation and Recognizing Legacy Bootstrap Guides

## 1. Purpose and Scope

When learning **Spring Boot Externalized Configuration**, many articles online reuse familiar terms like `application.yml`, `bootstrap.yml`, `spring.profiles.active`, `spring.cloud.config.uri`, and `spring.config.import`. However, **a single guide does not apply uniformly across every Spring Boot and Spring Cloud version**.

A tutorial that worked smoothly on Spring Boot 2.2/2.3 with Spring Cloud Hoxton is no longer the default setup when moving to Spring Boot 2.4+ and matching Spring Cloud generations. Likewise, an article discussing **Spring Cloud bootstrap context** is sometimes mistaken by readers as describing **Spring Boot bootstrap** in general.

This lesson helps you:

1. Identify the exact **Spring Boot, Spring Framework, Java, Spring Cloud release train, and Config Client module** your project actually uses.
2. Understand the **Config Data** milestone introduced in Spring Boot **2.4** and the role of `spring.config.import`.
3. Distinguish **Spring Cloud bootstrap context / `bootstrap.yml`** from the standard Config Data mechanism.
4. Recognize **legacy bootstrap** examples, **modern Config Data** examples, and cases deliberately enabling legacy compatibility mode.
5. Read the **reference documentation for your running version**, avoiding copying from the latest docs into an older codebase or vice versa.
6. Establish upgrade workflows, verify profiles, precedence, remote sources, startup failure handling, and testing.
7. Know when to **intentionally retain bootstrap**, when to **migrate to Config Data**, and when to defer changes until dependencies are fully verified.

Primary scope is Spring Boot and Spring Cloud Config Client; Vault, Consul, Kubernetes, AWS, or custom configuration integrations may impose additional library- and version-specific rules.

**Guiding principle: check versions first, select the mechanism second, and verify on the real running artifact.**

---

## 2. Common Scenario: Copying `bootstrap.yml` Yet Configuration Fails to Load

An older tutorial may write:

```yaml
# bootstrap.yml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://localhost:8888
```

A developer copies this into:

```text
src/main/resources/bootstrap.yml
```

upgrades Spring Boot or Spring Cloud, and runs:

```bash
java -jar order-service.jar
```

Possible outcomes:

- The app fails to fetch properties from Config Server.
- Spring Cloud Config Client reports missing `spring.config.import`.
- Some environment variables still work, fooling the developer into thinking `bootstrap.yml` was read.
- A profile-specific setting does not apply the same way as in older releases.
- Or the app still runs because **legacy bootstrap was enabled** via another dependency.

No single conclusion fits all cases. Classify systematically:

| Question | What to Verify |
| --- | --- |
| Which Spring Boot version does the project use? | Exact major/minor/patch in build and artifact |
| Which Spring Cloud release train is used? | Actual Spring Cloud BOM |
| Is Spring Cloud Config Client present? | Runtime dependency `spring-cloud-starter-config` or related module |
| Is legacy bootstrap enabled? | `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled` supplied early |
| Is `spring.config.import` declared? | Location and property value |
| Is a `configserver:` Config Data resolver active? | Dependency, bootstrap mode, and matching config |
| Are higher-precedence profiles/sources overriding? | Active profiles, Config Data, CLI, environment |
| What do the logs show? | Load, binding, conversion, validation, or network errors |

A reliable README must state **version and dependency preconditions**, not just paste a context-free YAML snippet.

## 3. The Word "Bootstrap" Does Not Always Mean the Same Thing

The term *bootstrap* appears in several contexts:

### 3.1. Bootstrap in the General Sense

A Java application starts the JVM, creates `SpringApplication`, prepares `Environment`, initializes `ApplicationContext`, registers beans, and runs lifecycle hooks. People sometimes call this entire startup sequence *application bootstrap*.

### 3.2. Spring Cloud Legacy Bootstrap Context

In older Spring Cloud generations, the **bootstrap context** was a special early phase/context responsible for fetching early config, notably from Spring Cloud Config Server.

`bootstrap.yml` or `bootstrap.properties` files were commonly used in guides for this model.

### 3.3. Spring Boot Bootstrap Registry / Bootstrap Context API

Spring Boot includes APIs such as `BootstrapRegistryInitializer` to register objects early during startup/Config Data in supported versions. **This does not mean a legacy Spring Cloud `bootstrap.yml` file is automatically loaded.**

### 3.4. Spring Boot Config Data

Starting in Spring Boot 2.4, Config Data handles importing configuration via `spring.config.import`, profile activation, and specialized locations/resolvers.

This is the centerpiece of modern Boot reference documentation.

**Remember:** seeing `bootstrap` in an API name, doc, or log **is never enough to conclude** a project uses Spring Cloud's `bootstrap.yml` loader.

## 4. Key Milestone: Spring Boot 2.4

Spring Boot **2.4** substantially changed how `application.properties`, `application.yml`, and related config sources are processed. This change is explained in the **Spring Boot Config Data Migration Guide** and official release notes.

Before that milestone, applications relied on legacy rules for profiles, multi-document ordering, and config locations.

Starting in Spring Boot 2.4, **Config Data** was introduced along with:

```properties
spring.config.import=optional:file:./local.properties
```

The new mechanism also introduced strict rules restricting profile activation inside profile-specific or conditional documents.

Conceptual timeline:

```text
Spring Boot 2.3 and earlier
   |
   | Legacy application.* processing;
   | many Spring Cloud guides use bootstrap.yml
   v
Spring Boot 2.4
   |
   | Config Data processing introduced
   | spring.config.import
   | new profile/document rules
   v
Spring Boot 2.5 / 2.6 / 2.7
   |
   | continues Config Data
   | requires matching Spring Cloud release train
   v
Spring Boot 3.x
   |
   | continues Config Data model;
   | Java/Jakarta platform and framework version changes
   v
Spring Boot 4.x
   |
   | verify 4.x docs and compatibility;
   | do not assume all APIs, starters, versions carry over unchanged from 3.x
```

This diagram highlights **conceptual milestones**, not a lifecycle support table or exhaustive changelog.

### 4.1. Reading Historical Documentation Accurately

Valuable historical references:

- Spring Boot Config Data Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Config-Data-Migration-Guide
- Spring Boot 2.4 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.4-Release-Notes

Whenever reading a guide mentioning `bootstrap.yml` or `spring.config.use-legacy-processing`, verify whether the author is writing before or after the 2.4 shift.

## 5. Version Matrix: Do Not Pair Spring Boot and Spring Cloud Arbitrarily

Spring Cloud uses named **release trains**, such as Hoxton, 2020.0.x, 2021.0.x, 2023.0.x, 2024.0.x, and 2025.x. Never look at a "newer Spring Cloud version" and assume it works with any Boot version.

Relationship examples **per the compatibility table on the Spring Cloud project page**:

| Spring Cloud Release Train | Associated Spring Boot Line |
| --- | --- |
| Hoxton | Boot 2.2.x / 2.3.x in supported service releases |
| 2020.0.x | Boot 2.4.x / 2.5.x, within specific patch bounds |
| 2021.0.x | Boot 2.6.x / 2.7.x, within specific patch bounds |
| 2022.0.x | Boot 3.0.x / 3.1.x, within specific patch bounds |
| 2023.0.x | Boot 3.2.x / 3.3.x, within specific patch bounds |
| 2024.0.x | Boot 3.4.x |
| 2025.0.x | Boot 3.5.x |
| 2025.1.x | Boot 4.0.x; Boot 4.1.x supported from a compatible 2025.1.x release |

**This table gives train-level orientation, not a guarantee that every arbitrary patch pair is compatible.** The official page notes minimum service releases, end-of-life (EOL) status, and later adjustments.

Always double-check:

https://spring.io/projects/spring-cloud/

and the release notes for the **exact** Spring Cloud train before upgrading.

### 5.1. Why Does the Matrix Matter for Bootstrap?

A `bootstrap.yml` example written for Boot 2.3 + Cloud Hoxton omits `spring.config.import` because that Cloud generation relied on traditional bootstrap.

On Boot 3.5 + Cloud 2025.0.x, Spring Cloud Config Client docs support Config Data imports; you should not blindly copy Hoxton's startup layout.

On Boot 4.x, check its matching train and 4.x documentation rather than merely bumping version numbers in `pom.xml`.

## 6. Identify Your Project's Actual Versions Before Reading Docs

Never guess versions from folder names, artifact names, or a line in an outdated README.

### 6.1. Maven: Inspect Parent/BOM

Example:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.x</version>
</parent>
```

This is an **illustrative template**; `3.5.x` denotes a version line, not a literal buildable version string.

If the project imports a BOM instead of a parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>...</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Check parent/BOM declarations, overridden dependency versions, and active Maven profiles.

### 6.2. Maven: Inspect Resolved Dependencies

```bash
./mvnw help:effective-pom
./mvnw dependency:tree
```

In a multi-module project, target the specific module:

```bash
./mvnw -pl service-module dependency:tree
```

Look for:

```text
org.springframework.boot:*
org.springframework.cloud:*
spring-cloud-starter-config
spring-cloud-starter-bootstrap
spring-cloud-dependencies
```

If using system Maven without the wrapper, replace `./mvnw` with `mvn`.

### 6.3. Gradle: Inspect Plugin/BOM

```groovy
plugins {
    id 'org.springframework.boot' version '<version>'
}

dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:<train-version>"
    )
}
```

This is an illustrative layout. Projects may alternatively use the Spring dependency-management plugin, version catalogs, or convention plugins.

### 6.4. Gradle: Inspect Resolved Runtime Dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-cloud-config-client \
  --configuration runtimeClasspath
```

If a module uses different tasks/configurations, target the right Gradle subproject.

### 6.5. Distinguish Source Files from the Running Artifact

Even when `build.gradle` declares Spring Boot 3.x, a container might still be running a JAR built under 2.7. Verify the **artifact version, image digest, or commit** of the live process—not just local build files.

## 7. Picking the Right Official Documentation

There are at least four distinct doc categories, each answering a different question:

| Documentation Type | Use When |
| --- | --- |
| Exact-version Spring Boot reference | Checking Externalized Configuration, Config Data, profiles |
| Spring Boot migration guide / release notes | Understanding behavior changes during Boot upgrades |
| Exact-version Spring Cloud Config Client reference | Checking `configserver:`, legacy bootstrap, remote connections |
| Spring Cloud compatibility / release train | Matching a Cloud BOM to Boot |

For example, modern Boot docs:

https://docs.spring.io/spring-boot/reference/features/external-config.html

Spring Cloud Config Client docs:

https://docs.spring.io/spring-cloud-config/reference/client.html

**Caution:** `/reference/...` URLs generally reflect whichever release the site currently treats as latest. A project running an older version must use the **version selector** or versioned archive URL—never assume "current" matches your runtime.

Specifically:

- Spring Boot guides **do not automatically cover all Spring Cloud Config Client features**.
- Spring Cloud guides **do not override the Config Data rules of your Boot version**.
- A blog post may be historically accurate yet obsolete for newer versions.

## 8. Spotting Legacy Bootstrap Guides by Their Signatures

An article likely targets the traditional bootstrap era if it shows several of these traits:

1. Creates `src/main/resources/bootstrap.yml`.
2. Places `spring.cloud.config.uri` and `spring.application.name` inside it.
3. Never mentions `spring.config.import`.
4. Explains that a bootstrap context reads Config Server before the application context.
5. Uses Boot 2.3 or Spring Cloud Hoxton / older release trains.
6. Uses `BootstrapConfiguration` classes or legacy Spring Cloud `spring.factories` entries.
7. Advises putting all remote-config properties into `bootstrap.properties` with no mention of Config Data.

Classic example:

```yaml
# bootstrap.yml — legacy Spring Cloud bootstrap example
spring:
  application:
    name: invoice-service
  cloud:
    config:
      uri: http://localhost:8888
      fail-fast: true
```

This is **not the universal default configuration for modern Spring Boot applications**.

### 8.1. Having `bootstrap.yml` Is Not Always Wrong

Some projects deliberately enable legacy bootstrap for compatibility or specific Spring Cloud integrations. In such setups, `bootstrap.yml` remains valid.

The task is not "delete every bootstrap file blindly", but **verify why it works today and whether it fits your target design**.

## 9. Spring Boot Config Data with `spring.config.import`

In the modern model, an application file imports additional sources via:

```yaml
# application.yml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
```

When the location exists, values from the imported document can take higher precedence than the document declaring the import under Config Data rules.

This mechanism belongs to **Spring Boot**. It handles standard Boot location types as well as custom location schemes added by external resolvers/loaders.

When importing from Spring Cloud Config Server, the location uses a dedicated scheme:

```text
configserver:
```

`configserver:` does not represent a local file; it requires Spring Cloud Config Client on a compatible version to resolve it.

## 10. Spring Cloud Config Client via Config Data

When using Spring Cloud Config Client compatible with Spring Boot 2.4+ and Config Data, a typical setup is:

```yaml
# application.yml
spring:
  application:
    name: invoice-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Preconditions:

- Compatible Spring Cloud Config Client dependency is present.
- Spring Boot and Spring Cloud release trains match.
- Config Server is reachable at the declared endpoint.
- Environment policy permits fetching remote configuration.

### 10.1. `optional:configserver:`

```properties
spring.config.import=optional:configserver:
```

Spring Cloud Config Client docs show this form to connect to Config Server at its default location when no URL is specified.

`optional:` means **do not turn an unreachable source into a mandatory startup failure under import semantics**.

Verify your actual requirements:

- If remote config only supplements feature flags, `optional:` may be fine.
- If remote config holds mandatory policies, booting without it can be dangerous; consider a non-optional import, validation, and fail-fast behavior.

### 10.2. Non-Optional `configserver:`

```properties
spring.config.import=configserver:http://localhost:8888
```

This states that the remote Config Server is a required dependency of configuration loading under Config Data / Config Client semantics.

Do not casually add `optional:` just to "get the app running" without evaluating the fallout. The app might boot with wrong environment defaults.

### 10.3. Specifying the Config Server Address

Spring Cloud Config Client docs allow specifying the address in the import location:

```properties
spring.config.import=optional:configserver:http://localhost:8888
```

Or using `spring.cloud.config.uri` alongside an appropriate import declaration. When both specify locations, check the **exact-version** docs for precedence; in modern reference versions, the address in `spring.config.import` takes precedence over `spring.cloud.config.uri`.

Never embed usernames or passwords inside URLs in public READMEs. Use a secret manager or secure environment delivery for credentials.

## 11. Before-and-After Comparison

### 11.1. Legacy Bootstrap Style

```yaml
# bootstrap.yml
spring:
  application:
    name: billing-service
  cloud:
    config:
      uri: http://localhost:8888
```

This assumes **legacy bootstrap context is enabled** and the required dependency is present.

### 11.2. Config Data Style

```yaml
# application.yml
spring:
  application:
    name: billing-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Add any needed Spring Cloud Config Client properties as required.

### 11.3. Fundamental Differences

| Aspect | Legacy Bootstrap | Config Data Import |
| --- | --- | --- |
| Primary file cited | `bootstrap.yml` | `application.yml` or suitable Config Data source |
| Primary extension point | Spring Cloud bootstrap context | Spring Boot Config Data |
| Remote connection property | Often `spring.cloud.config.uri` | `spring.config.import=configserver:...` |
| Activation | Legacy bootstrap enabled | Compatible import + resolver/loader |
| Profile handling | Legacy bootstrap lifecycle | Config Data follows modern Boot rules |
| Legacy compatibility | Intentional when required | Common target for modern projects |

**Never maintain both configurations unconsciously.** If a project simultaneously enables bootstrap context and imports `configserver:`, multiple connection paths or confusing precedence can result. Inspect your version's docs and startup logs.

## 12. Legacy Bootstrap Can Still Be Enabled Intentionally

Per Spring Cloud Config Client docs, to keep the legacy **Config First Bootstrap** mode, bootstrap can be enabled via:

```text
spring.cloud.bootstrap.enabled=true
```

or the starter:

```text
org.springframework.cloud:spring-cloud-starter-bootstrap
```

When using `spring.cloud.bootstrap.enabled=true`, the docs require supplying it early—such as via a **Java system property or environment variable**.

Example:

```bash
java -Dspring.cloud.bootstrap.enabled=true \
     -jar app.jar
```

Or:

```bash
SPRING_CLOUD_BOOTSTRAP_ENABLED=true java -jar app.jar
```

With that mode active, `bootstrap.yml` and `spring.cloud.config.uri` operate along Spring Cloud's legacy path.

**Note:** whether this works depends on the Cloud module, compatible release train, and startup mechanism of that version. Never assume creating `bootstrap.yml` makes plain Boot start a Spring Cloud bootstrap context automatically.

## 13. `spring-cloud-starter-config` vs `spring-cloud-starter-bootstrap`

The two artifacts serve different roles:

```text
spring-cloud-starter-config
spring-cloud-starter-bootstrap
```

- `spring-cloud-starter-config` provides the components for Spring Cloud Config Client.
- `spring-cloud-starter-bootstrap` activates the legacy bootstrap mechanism in release trains supporting it.

For Config Data imports from Config Server, start with the **Config Client starter** and `spring.config.import`.

If intentionally running legacy bootstrap, verify the bootstrap starter/flag explicitly.

Never "fix" a configuration error by reflexively adding `spring-cloud-starter-bootstrap` without knowing which mode the project uses. It can mask symptoms initially while complicating future upgrades.

## 14. The "No spring.config.import property has been defined" Error

In Spring Cloud Config Client setups operating in Config Data mode, missing import configuration triggers a startup message such as:

```text
No spring.config.import property has been defined
```

This is a strong sign you are running a **Config Client generation expecting Config Data import**, yet neither declared `spring.config.import` nor enabled legacy bootstrap.

### 14.1. Proper Resolution Steps

1. Confirm Spring Cloud Config Client is genuinely needed.
2. Confirm Boot–Cloud release train compatibility.
3. Choose **Config Data mode** or **legacy bootstrap mode**.
4. For Config Data, declare `spring.config.import=...` in an appropriate source.
5. For legacy mode, enable bootstrap only if justified and supported by your version's docs.
6. Verify network reachability, URI, and the application/profile/label served by Config Server.
7. Restart and inspect logs.

Some posts suggest disabling the check via:

```properties
spring.cloud.config.import-check.enabled=false
```

Where supported, this **disables the startup check**, yet **does not configure remote loading**. Never use it as a substitute for understanding `spring.config.import`.

## 15. What Is `spring.config.use-legacy-processing`?

The Spring Boot 2.4 migration guide documents:

```properties
spring.config.use-legacy-processing=true
```

to temporarily restore Boot 2.3-style config processing within transitional releases supporting that option.

This is a **historical transitional compatibility flag**, not an option guaranteed to exist or recommended long-term in newer releases.

Do not assume an app on Boot 3.x or 4.x can simply flip `spring.config.use-legacy-processing=true` and regain Boot 2.3 behavior.

Specifically:

- This option belongs to **Spring Boot Config Data migration**.
- It is not a synonym for `spring.cloud.bootstrap.enabled`.
- Enabling one does not automatically reproduce all behavior of the other.
- When upgrading, target the official configuration contract of the destination version rather than leaning on compatibility flags indefinitely.

If a blog advises keeping `spring.config.use-legacy-processing=true` "to keep things simple", check **its publication date, source version, and target version**.

## 16. Distinguishing the Two Legacy Mechanisms

| Need | Mechanism | Meaning |
| --- | --- | --- |
| Pre-Boot 2.4 `application.yml` processing | `spring.config.use-legacy-processing` in supported transitional versions | Spring Boot Config Data compatibility |
| Legacy Spring Cloud bootstrap context | `spring.cloud.bootstrap.enabled` / bootstrap starter where supported | Spring Cloud legacy bootstrap |
| Modern import from Config Server | `spring.config.import=configserver:...` | Spring Boot Config Data + Cloud Config Client |
| Import local files | `spring.config.import=file:...` | Pure Spring Boot Config Data |
| Register resources/objects in Boot's bootstrap phase | `BootstrapRegistryInitializer` | Boot startup API; does not load `bootstrap.yml` |

This is the most important table whenever a guide mentions "bootstrap" or "legacy".

## 17. Profile Document Changes Since Boot 2.4

A major friction point upgrading from Boot 2.3 involves multi-document YAML and profile conditions.

Legacy style:

```yaml
spring:
  profiles: dev

app:
  message: "development"
```

With Config Data, document activation conditions commonly use:

```yaml
spring:
  config:
    activate:
      on-profile: dev

app:
  message: "development"
```

Here `spring.config.activate.on-profile` is a **condition controlling when the document applies**, not a request to activate that profile.

To activate the profile:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Check the migration guide whenever encountering older YAML using `spring.profiles` as a document selector.

## 18. Do Not Place `spring.profiles.active` Inside Profile-Activated Documents

A common mistake when migrating from bootstrap:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: prod

app:
  message: "production"
```

This violates Config Data structure. Modern Spring Boot restricts profile-activating properties inside profile-specific files or documents conditioned with `spring.config.activate.on-profile`.

Proper separation of responsibilities:

**In a startup source allowed to set active profiles:**

```bash
java -jar app.jar --spring.profiles.active=prod
```

**Inside the prod-only document:**

```yaml
spring:
  config:
    activate:
      on-profile: prod

app:
  message: "production"
```

If startup fails complaining about an invalid `spring.profiles.active` declaration, inspect which document contains the property rather than rushing to re-enable legacy bootstrap.

## 19. `spring.profiles.include` and Groups When Upgrading

Older tutorials often show:

```yaml
spring:
  profiles:
    include: metrics
```

Modern Spring Boot still supports includes and profile groups, yet enforces **rules on where they may be declared**.

Profile group example in an unconditional document:

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmetrics
```

Activating `production` brings in the member profiles accordingly.

Do not place `spring.profiles.include` or group definitions arbitrarily inside an `on-profile` document or profile-specific file.

When reading older guides placing `include` inside each profile file, consult your running version's migration guide. Never assume Boot 2.3 YAML stays valid under Config Data.

## 20. `spring.config.import` Is Not `@PropertySource`

Spring Framework supports:

```java
@Configuration
@PropertySource("classpath:company.properties")
public class CompanyConfiguration {
}
```

This is processed while building the Spring context.

Meanwhile:

```yaml
spring:
  config:
    import: "classpath:company.properties"
```

belongs to Boot's **Config Data phase**.

The two differ in:

- load timing;
- profile handling;
- precedence position;
- import syntax;
- missing-resource behavior;
- effect on early startup properties.

An older guide may suggest `@PropertySource` to load an external file. That can still work for classic `.properties` files, yet does not replace Config Data—especially when early profile or import decisions are needed.

Never treat `@PropertySource`, `bootstrap.yml`, and `spring.config.import` as interchangeable.

## 21. `spring.config.location` and `additional-location`

The properties:

```text
spring.config.location
spring.config.additional-location
```

govern Config Data search locations.

In brief:

- `spring.config.location` overrides Boot's default search locations.
- `spring.config.additional-location` appends extra locations alongside defaults.

Example:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/app/config/
```

The trailing `/` denotes a directory; `optional:` permits an absent location where appropriate.

An older guide might put external file paths in `bootstrap.yml` to "load really early." If your goal today is simply **reading config files outside the JAR**, check standard Config Data locations before reviving Spring Cloud bootstrap context.

Introduce legacy bootstrap only when you genuinely require its Spring Cloud-specific characteristics.

## 22. Do Not Equate `file:` Imports with `configserver:` Imports

Two examples:

```properties
spring.config.import=optional:file:./local.yml
```

and:

```properties
spring.config.import=optional:configserver:http://localhost:8888
```

both use `spring.config.import`, yet target **different location types**:

| Scheme | Typical Handler |
| --- | --- |
| `file:`, `classpath:` | Spring Boot's Config Data loader for supported resources |
| `configserver:` | Spring Cloud Config Client extension when the dependency is present |
| Custom scheme | `ConfigDataLocationResolver` and `ConfigDataLoader` from a library/app |

If the app reports an unrecognized `configserver:` location, check your Config Client module and version before renaming YAML files.

A plain Boot app does not need Spring Cloud to load local `application.yml` or supported `file:` imports.

## 23. When Is an Import Loaded?

In Config Data, a document declaring:

```yaml
spring:
  config:
    import: "optional:file:./extra.yml"

app:
  timeout: 3s
```

imports data from `extra.yml` if present.

Official docs explain that imports are processed as encountered and have specific precedence: values from the import can override values in the document declaring the import.

Example:

```yaml
# extra.yml
app:
  timeout: 5s
```

Here, `app.timeout` from the import becomes effective within that Config Data scope.

**However:** that does not yet account for CLI, environment variables, system properties, profile-specific documents, or other sources. A higher-precedence source can still win.

Never copy "legacy bootstrap config" precedence rules to guess Config Data import ordering. Consult exact-version docs and test.

## 24. Config Server May Be Called Multiple Times at Startup

Spring Cloud Config Client docs explain that Config Data can operate in multiple passes—for instance, fetching default-profile data first to discover active profiles, then fetching data for those active profiles.

Thus in Config Data mode, you may observe **multiple requests to Config Server** during a single startup. That can be normal profile/import lifecycle behavior, not necessarily a duplicate-call bug or infinite retry loop.

When reviewing logs or metrics:

- Distinguish the default-phase request from active-profile requests.
- Check app name, profile, label, and URI.
- Distinguish normal multi-pass fetches from network-failure retries.
- Compare behavior against your exact version's Config Client docs.

If moving from legacy bootstrap to Config Data increases request counts, do not blindly disable profile processing just to force a single request.

## 25. Fail-Fast and `optional:` Are Design Decisions

An example may show:

```properties
spring.config.import=optional:configserver:
```

so developers can run locally when Config Server is down. Yet production may require the opposite.

Classify needs:

| Requirement | Design to Consider |
| --- | --- |
| Config Server optional; safe local defaults exist | `optional:` may be used |
| Config Server mandatory to enforce policies | Non-optional import |
| Retry connection on transient server outages | Retry mechanism supported by Config Client version |
| Prevent startup with incomplete configuration | Appropriate validation and fail-fast |
| Let offline developers run | Meaningful local fallback and clear profile separation |

In legacy bootstrap, tutorials used:

```properties
spring.cloud.config.fail-fast=true
```

In Config Data imports, omitting `optional:` relates to failing startup when a required source is unreachable.

Do not treat those two switches as identical in every detail. Check interactions with retries, import locations, and Config Client versions.

## 26. Retries in Config Data Imports Have Specific Rules

Config Client docs cover `spring.cloud.config.retry.*` and require the appropriate retry dependency.

Conceptual example:

```properties
spring.cloud.config.retry.max-attempts=10
spring.cloud.config.retry.initial-interval=1000
```

In some cases—such as Config Server imports declared inside profile-specific files—retry parameters may need to be passed as URL query parameters on the import location per that version's docs.

Structural example:

```properties
spring.config.import=configserver:http://config.example.invalid:8888?fail-fast=true&max-attempts=10
```

This illustrates **parameter syntax** described in versions supporting it, not a complete production setup.

In real apps, check:

- Are network failures retried?
- Should auth failures or 4xx responses be retried?
- Is total startup time bounded?
- Does retry apply during Config Data loading or legacy bootstrap?
- Are retry/AOP dependencies configured properly?

Do not copy retry settings from legacy bootstrap blogs into Config Data mode without verifying how your version handles them.

## 27. `spring.application.name`, Profile, and Label on Config Server

A Spring Cloud Config Client typically identifies remote config via:

```text
application
profile
label
```

These correspond to:

```text
spring.application.name
spring.profiles.active
spring.cloud.config.label
```

Example:

```yaml
spring:
  application:
    name: billing-service
  profiles:
    active: dev
  config:
    import: "optional:configserver:http://localhost:8888"
```

In real deployments, supply the active profile via launch command or environment policy rather than hardcoding it in a shared file.

A bug might have nothing to do with bootstrap mode—it may simply be **the app querying Config Server with a different app name, profile, or label than you thought**.

When logs show remote fetch succeeded yet properties are missing, verify that identifier tuple and the Config Server repository.

## 28. Do Not Confuse `bootstrap.yml` with `application.yml`

Placing a file at:

```text
src/main/resources/bootstrap.yml
```

does not behave like `application.yml` in every Spring Boot application.

In standard Boot, base config names center around `application`, unless customized via `spring.config.name` or another mechanism.

`bootstrap.yml` is associated with **Spring Cloud legacy bootstrap**.

If your project lacks Spring Cloud bootstrap machinery or does not explicitly import the file, never assume plain Boot reads `bootstrap.yml` automatically.

**Simple verification steps:**

1. Confirm exact versions and dependencies.
2. Check whether legacy bootstrap is enabled.
3. Enable Config Data trace logs.
4. List `PropertySource` names and inspect a non-sensitive key.
5. Verify which source the app actually uses.

Never conclude a file is active just because it exists in the repository.

## 29. Separate File Presence, Load Order, and Final Precedence

Three separate questions:

**Does the file exist?**

```text
src/main/resources/application.yml
```

**Was the file packaged and loaded?**

In a standard executable JAR, application module resources sit under:

```text
BOOT-INF/classes/
```

**Did the file's value win?**

Maybe not, because:

- Another file/profile holds higher priority.
- An import contributed a newer value.
- A Java system property overrode it.
- An environment variable overrode it.
- CLI arguments overrode it.
- A custom `PropertySource` was prepended.

When an old bootstrap guide says "bootstrap config loads first, so it always has highest priority," re-evaluate against current precedence rules, Spring Cloud property source ordering, and override policies.

**Loading early does not automatically mean winning over all other sources.**

## 30. Legacy Bootstrap Can Tune Remote Source Ordering

In traditional Spring Cloud bootstrap setups, the `PropertySource` from Config Server entered Spring's `Environment` with priority and override flags controlled by Cloud properties.

Old guides mention:

```text
spring.cloud.config.allow-override
spring.cloud.config.override-none
spring.cloud.config.override-system-properties
```

Do not copy those switches into arbitrary Config Data apps expecting identical behavior.

When encountering them in docs:

1. Verify which Spring Cloud Config / legacy bootstrap version they target.
2. Check whether the property is still supported in your current version.
3. Verify whether server or client controls override policy.
4. Test effective values across remote sources, local Config Data, environment, and CLI.
5. Never infer precedence from property names alone.

Configuration precedence is part of the operational contract and can shift behavior on upgrade even when the app still starts.

## 31. Recognizing Guides with Legacy Packages/APIs

Older technical articles may use:

```java
import javax.validation.constraints.NotBlank;
```

In Spring Boot 3.x, Jakarta Validation examples use:

```java
import jakarta.validation.constraints.NotBlank;
```

This reflects a **platform shift** across major Boot releases rather than a Config Data change directly.

It reminds us to view bootstrap guides in full context:

- Supported Java version.
- Spring Framework major version.
- Boot starters and APIs.
- Jakarta/Javax namespaces.
- Spring Cloud release train.
- Build plugins and dependency versions.

If an article shows both legacy `bootstrap.yml` and pre-Boot 3 `javax.*` imports, cross-check versions carefully.

Do not merely swap `javax` for `jakarta` and assume the entire setup is Boot 3.x-compatible.

## 32. Spring Boot 4.x Requires Another Verification Pass

At the time of writing, Spring Boot 4.x and Spring Cloud 2025.x exist. A Boot 4.x project must not blindly copy every dependency, starter, or constructor API from Boot 2.x/3.x examples.

Verify:

- Release notes for your exact Boot 4.x patch.
- The Spring Cloud train supporting that minor version.
- Corresponding Spring Cloud Config Client docs.
- Dependency, auto-configuration, or starter reorganizations in the major release.
- Config Data/Environment APIs and extension registration mechanisms used by libraries.
- Supported Java, Gradle, and Maven plugin versions.

On Spring Cloud's compatibility table, the `2025.1.x` train pairs with Boot 4.0.x and supports 4.1.x starting from an appropriate service release. **Do not assume train names alone guarantee every patch pair matches**; check official support tables and release notes.

## 33. Why You Should Not Copy BOM Versions from Old Answers

Maven might declare:

```xml
<properties>
    <spring-cloud.version>...</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Here `...` is a **placeholder for an exact version chosen from the compatibility table**, not runnable build text.

Pasting a train from an old blog into Boot 4.x risks startup crashes, API mismatches, or compatibility check failures.

Proper workflow:

1. Read the project's Boot version.
2. Check Spring Cloud's compatibility table.
3. Pick the compatible release train.
4. Pick a suitable supported service release.
5. Import the Cloud BOM.
6. Let dependency management align all Cloud modules in that train.
7. Inspect the dependency tree and test startup.

Never pin individual Cloud module versions arbitrarily alongside a BOM unless verified necessary.

## 34. Gradle Also Needs Aligned Version Management

A general template:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version>'
}

dependencies {
    implementation platform(
            'org.springframework.cloud:spring-cloud-dependencies:<cloud-train-version>')

    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Depending on build conventions, projects may use the dependency-management plugin or version catalogs.

The point is not placeholder syntax, but **selecting the Boot plugin and Cloud train as a compatible pair**.

During upgrades, run:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

and inspect which versions modules resolve, especially if subprojects still pin older individual versions.

## 35. Do Not Confuse Extension Registration Mechanisms

Across the Spring ecosystem you will encounter:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

along with distinct interfaces/classes:

```text
EnvironmentPostProcessor
BootstrapRegistryInitializer
PropertySourceLocator
ConfigDataLocationResolver
ConfigDataLoader
AutoConfiguration
```

Each serves a different lifecycle stage.

For example:

- `EnvironmentPostProcessor` customizes `Environment` preparation.
- `ConfigDataLocationResolver` and `ConfigDataLoader` add Config Data location types.
- `BootstrapRegistryInitializer` participates in Boot's bootstrap registry.
- `PropertySourceLocator` belongs to traditional Spring Cloud bootstrap.
- `AutoConfiguration.imports` registers auto-configuration classes.

**Never assume anything named `Bootstrap` reads `bootstrap.yml`.**

When following an extension tutorial, check the exact API and release notes for your Boot/Cloud version; older posts often show outdated registration files.

## 36. Diagnose Before Editing Bootstrap Files

An effective investigation workflow:

### Step 1: Confirm Versions

Inspect the build files and dependency tree. Identify Boot major/minor, Cloud train, and Config Client.

### Step 2: Confirm Mode

Look for:

```text
spring.config.import
spring.cloud.bootstrap.enabled
spring-cloud-starter-bootstrap
spring.config.use-legacy-processing
```

Note: finding a string in a repo does not prove it is active at runtime. Verify loaded sources and version support.

### Step 3: Inspect Startup Logs

Enable detailed logging when needed:

```bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
```

For Spring Cloud Config Client, enable relevant Cloud Config loggers per your version to see remote requests and HTTP errors.

### Step 4: Inspect Profiles and Config Data

Verify active profiles, default profile, import locations, and loaded resources.

### Step 5: Inspect `PropertySources`

List source names; never dump all values, especially secrets.

### Step 6: Verify Bound Values

Read a non-sensitive key from `Environment` or a `@ConfigurationProperties` bean. Distinguish:

- File not found.
- File loaded yet profile did not apply.
- Value overridden.
- Binder conversion failure.
- Validation rejection.

### Step 7: Fix at the Right Layer

You may need to fix imports, the BOM, profiles, working directory, server URL, or permissions—not necessarily create a new bootstrap file.

## 37. Classifying Spring Cloud Config Errors

| Symptom | Likely Cause Category | Investigation Path |
| --- | --- | --- |
| Missing `spring.config.import` error | Config Client in Config Data mode lacks import | Add proper import or verify intentional legacy mode |
| `bootstrap.yml` has no effect | Legacy bootstrap is not enabled | Check starter/flag and version |
| `configserver:` scheme unrecognized | Config Client module absent or incompatible | Inspect dependency tree and BOM |
| Cannot connect to Config Server | URI, network, auth, TLS, server down | Check client logs, connectivity, and secrets |
| Connected yet property missing | App name/profile/label, repo contents, precedence | Inspect endpoint and effective sources |
| Remote loaded yet bean fails | Conversion/validation or missing value | Inspect `@ConfigurationProperties` and logs |
| Multiple config requests at startup | Config Data profile processing or retry | Separate phases from retry loops |
| Profile behavior changed after upgrade | Config Data rules differ from legacy | Read migration guide and test profiles |
| Boot–Cloud mismatch | Incompatible release train chosen | Check compatibility table |
| Prod runs using local defaults | Optional remote import or missing remote config | Review fail-fast and validation rules |

Do not blame every symptom on "Spring Boot isn't reading bootstrap." An app may be running Config Data properly while hitting a remote server or validation issue.

## 38. Do Not Let `optional:` Hide Missing Required Configuration

A common "quick fix":

```yaml
spring:
  config:
    import: "optional:configserver:"
```

The app starts past a Config Server connection error, yet may run with unsafe defaults if remote keys were actually mandatory.

For example:

```yaml
payment:
  endpoint: "https://fallback.example.invalid"
```

If production Config Server is supposed to provide the real endpoint and transaction policy, falling back can be a severe operational incident.

To mitigate risk:

1. Classify required properties.
2. Never add fake defaults for safety-critical values.
3. Validate when creating beans.
4. Use `optional:` only for truly optional sources.
5. Add integration tests with the remote server offline.
6. Add telemetry/readiness checks detecting missing config.

**Booting cleanly does not guarantee valid configuration.**

## 39. Verify Precedence After Switching Modes

A practical test uses the same key across multiple sources:

```yaml
# application.yml
client:
  timeout: 3s
```

Remote Config Server (example):

```properties
client.timeout=5s
```

Environment variable:

```text
CLIENT_TIMEOUT=7s
```

Command line:

```bash
java -jar app.jar --client.timeout=9s
```

With all present, verify **which value the binder resolves in your exact version and mode**.

Do not write tests assuming "remote always beats local" or "env always beats remote" without accounting for Cloud mechanics and override flags.

You can check:

```java
Environment environment = ...;
String timeout = environment.getProperty("client.timeout");
```

and a bean:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {
}
```

Inspect both the resolved value and the `PropertySource` list rather than trusting a single YAML file's order.

## 40. Confirming Which Sources Config Data Loaded

In dev/test, enable TRACE:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Logs reveal location resolution, profile handling, and imports. Exact output varies by version.

To list `PropertySource` names:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceNamePrinter implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public PropertySourceNamePrinter(
            ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (var source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
```

This prints source names only, never all values. Internal names may change across versions, so do not couple business logic to them.

A log line saying "Config Server returned data" does not prove server values beat higher-precedence sources. Verify the effective value.

## 41. Inspect Active Profiles at Runtime Instead of Reading One File

Example:

```java
import java.util.Arrays;

System.out.println(
        Arrays.toString(environment.getActiveProfiles()));
```

When no profiles are explicitly active, this array can be empty even though Spring Boot loads base documents and considers the default profile.

If `prod` is passed via CLI:

```bash
java -jar app.jar --spring.profiles.active=prod
```

yet logs show additional profiles, check profile groups/includes, bootstrap code, or overriding sources.

Specifically, a document containing:

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

**does not activate `prod`**. It only conditions when that document applies.

## 42. Testing Configuration per Mode in Your Project

Your suite should combine fast unit tests and realistic integration tests.

### 42.1. Unit Tests for Binding

Use `Binder` with `MapConfigurationPropertySource` to verify key names and Java types.

### 42.2. Context Tests for Bean Registration

Use `ApplicationContextRunner` with `@EnableConfigurationProperties` to test binding and bean validation.

### 42.3. Integration Tests for Config Data

Boot the context with realistic profiles and config sources in tests.

### 42.4. Integration Tests with Config Server

Use a test server or controlled integration environment to test both server-available and server-unavailable cases.

### 42.5. Smoke Tests on the Executable JAR

Run the packaged artifact with deployment-like CLI/env and check startup, profiles, remote imports, validation, and readiness.

You cannot prove a migration from legacy bootstrap to Config Data succeeded solely by unit-testing a `MapPropertySource`. That never exercises remote fetching or the Config Data lifecycle.

## 43. Illustrative Configuration Contract for Testing

Record:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts) {
}
```

This example uses `jakarta.validation.*` imports for Spring Boot 3.x. For Boot 2.x, namespaces and dependencies differ; for Boot 4.x, check exact version docs.

A context test verifying valid effective values:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsValidValues() {
        runner.withPropertyValues(
                "client.endpoint=https://api.example.invalid",
                "client.timeout=3s",
                "client.max-attempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            ClientProperties properties =
                    context.getBean(ClientProperties.class);
            assertThat(properties.maxAttempts()).isEqualTo(4);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfiguration {
    }
}
```

This tests binding in a minimal context and **does not exercise Config Server loading**. Remote config requires dedicated integration tests.

## 44. Upgrade Scenario 1: Boot 2.3 + Cloud Hoxton to Boot 2.7

Suppose a legacy project has:

```text
Spring Boot 2.3.x
Spring Cloud Hoxton
src/main/resources/bootstrap.yml
```

Target:

```text
Spring Boot 2.7.x
Compatible Spring Cloud 2021.0.x
```

Plan:

1. Identify which code actually relies on the bootstrap context.
2. Read the Boot 2.4 migration guide before changing Boot versions.
3. Update the Boot version and pick the compatible Cloud train.
4. Migrate configuration documents from legacy rules to Config Data where appropriate.
5. Decide whether to adopt `spring.config.import=configserver:` or intentionally keep legacy bootstrap.
6. Fix multi-document YAML relying on legacy profile syntax.
7. Verify CLI/system/env precedence.
8. Test dev/prod profiles against a test Config Server.
9. Verify remote fetch, retries, and fail-fast behavior.
10. Package, smoke-test, and document changes in the README.

Never jump from Hoxton to a newer Cloud train incompatible with Boot 2.7.

## 45. Upgrade Scenario 2: Boot 2.7 to Boot 3.x

Here, beyond Config Data (already introduced in 2.4), projects face Java/Jakarta/Spring Framework platform shifts.

Checklist:

- Select the Java version required by Boot 3.x.
- Update the Spring Cloud train per the compatibility table.
- Migrate relevant `javax.*` APIs to `jakarta.*`.
- Audit replaced or removed dependencies.
- Verify Cloud Config Client stays in the intended mode.
- Verify `@ConfigurationProperties` and validation.
- Review Actuator/management security.
- Test profile/import/config precedence.
- Confirm the new JAR is built and no stale artifact is run.

If startup throws `ClassNotFoundException` or `NoSuchMethodError`, suspect a **dependency/API mismatch** rather than blaming `bootstrap.yml`.

## 46. Upgrade Scenario 3: Boot 3.x to Boot 4.x

Do not apply a "Boot 2.7 to 3.x" recipe mechanically to the next major jump.

Workflow:

1. Select a supported target Boot 4.x minor/patch release.
2. Look up the matching Spring Cloud train.
3. Read Boot 4.x and Cloud Config Client release notes.
4. Check Java, build tool, and starter changes.
5. Verify Config Data import mechanics still match expectations.
6. Inspect custom extensions using `EnvironmentPostProcessor`, `ConfigDataLocationResolver`, or `BootstrapRegistryInitializer`.
7. Audit renamed or removed APIs and annotations.
8. Test startup, binding, validation, and remote fetch on the new artifact.
9. Check logs, metrics, and Actuator security.
10. Record the proven version pair backed by build/test runs.

In particular, if an internal library uses legacy Spring Cloud bootstrap extensions, upgrade that library rather than only the consuming Boot app.

## 47. A Team Migration Checklist

Before changing anything:

- Record current Boot version, Cloud train, and Config Client version.
- Capture the application module's dependency tree.
- Inventory `application.*`, `bootstrap.*`, and external-to-JAR sources.
- List imports, active profiles, includes, and groups.
- Record effective values of selected **non-sensitive** keys.
- Determine whether remote config is mandatory or optional.
- Identify how legacy bootstrap is currently enabled (if at all).

During changes:

- Choose target mode: Config Data or intentional legacy bootstrap.
- Update to a compatible BOM.
- Move configuration into the appropriate sources.
- Update profile/document syntax to match target rules.
- Avoid using transitional compatibility flags permanently without justification.
- Keep secrets out of source code and logs.
- Explicitly document working directory and file locations in deployments.

After changes:

- Run binder/validation tests.
- Run Config Data/profile integration tests.
- Test Config Server online and offline.
- Verify fail-fast/optional semantics.
- Verify precedence across overlapping keys.
- Smoke-test the actual executable JAR/container.
- Update the README with exact versions and doc links.

## 48. Build a Project-Specific Before–After Comparison Table

Include a table like this in your upgrade notes:

| Item | Before | After | Verification Method |
| --- | --- | --- | --- |
| Boot version | 2.3.x | 2.7.x | Effective build |
| Cloud train | Hoxton | Matching 2021.0.x | Dependency tree |
| Remote config | `bootstrap.yml` | `spring.config.import=configserver:` | Startup log + Config Server |
| Profile declaration | Legacy file rules | Config Data profile activation | Profile integration test |
| Missing remote | Legacy fail-fast | Intentional optional/required import | Offline server test |
| Client timeout | Multi-source value | Verified target precedence | Bean config assertion |
| Artifact | Old build JAR | New build JAR | Artifact ID/version |
| Rollback | Legacy startup mode | Tested rollback plan | Smoke test |

This is a **process template**. In real docs, use exact versions (no `x`) and real module names.

A solid migration is not merely swapping files; it provides **before-and-after behavioral evidence**.

## 49. Common Mistake: Copying "Current" Examples into an EOL Project

Suppose a project runs Boot 2.2 and Cloud Hoxton, yet someone reads modern Spring Cloud docs and adds:

```properties
spring.config.import=configserver:http://localhost:8888
```

Boot 2.2 predates Boot 2.4's `spring.config.import` Config Data mechanism.

Never expect an older Boot runtime to recognize new properties and call Config Server in the modern way.

Fix:

- If not upgrading yet, read version-matched historical docs.
- To adopt Config Data, plan a compatible Boot and Cloud upgrade.
- Do not patch new properties onto old runtimes and ignore them when they have no effect.

**Modern docs cannot teach an old runtime features that did not exist yet.**

## 50. Common Mistake: Using `bootstrap.yml` in Plain Boot

An app with only:

```groovy
implementation 'org.springframework.boot:spring-boot-starter'
```

has neither Spring Cloud Config Client nor a legacy bootstrap module.

A developer creates:

```yaml
# bootstrap.yml
demo:
  message: "Hello"
```

and wonders why `demo.message` is missing.

Normally, plain Boot uses `application.yml` as its default Config Data name and does not treat `bootstrap.yml` as a standard config file just because "bootstrap" is in the name.

For local configuration, use:

```yaml
# application.yml
demo:
  message: "Hello"
```

or explicitly import a supported resource.

Do not add the Spring Cloud bootstrap starter just to load a local file that ordinary Config Data can name and import cleanly.

## 51. Common Mistake: Missing Config Client Dependency

A file has:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

yet the project lacks the Config Client module supporting that location.

Spring Boot has no resolver for the `configserver:` scheme and fails on the unrecognized location.

Proper fix:

- Confirm Spring Cloud Config Server is genuinely needed.
- Add `spring-cloud-starter-config` from the right train.
- Do not pick an arbitrary Cloud version.
- Re-verify the import config and startup.

If remote Config Server is unneeded, drop the `configserver:` scheme and use an appropriate local source instead of adding extra dependencies.

## 52. Common Mistake: Adding the Bootstrap Starter and Losing Precedence Control

A team hits a Config Client import error and adds:

```text
spring-cloud-starter-bootstrap
```

to make the app boot. Now configuration loads through the bootstrap context path, altering timing and precedence expectations.

Consequences:

- Unclear which path loads remote config.
- Different developers document conflicting approaches.
- Keys get overridden unexpectedly.
- Future upgrades fail again.

Required steps:

1. Pick one intentional mode.
2. Document the loading path.
3. Inspect the dependency tree.
4. Test effective values.
5. Keep the bootstrap starter only when backed by a clear technical rationale.

## 53. Common Mistake: Removing `optional:` Without Testing Offline Server

Changing:

```properties
spring.config.import=optional:configserver:
```

to:

```properties
spring.config.import=configserver:
```

changes the startup contract: the remote source is now mandatory under import semantics.

That may be right for production, yet requires testing:

- Server available.
- Server temporarily unreachable.
- DNS/network timeout.
- Rejected credentials.
- Profile returning no data.
- Remote returns data that fails bean validation.

Never evaluate only the happy path.

## 54. Common Mistake: Writing an `EnvironmentPostProcessor` to "Fix Bootstrap"

Older guides use:

```java
EnvironmentPostProcessor
```

to inject custom `PropertySources` very early.

While valid for targeted needs, do not reinvent Spring Cloud Config Client or Config Data just because legacy bootstrap stopped working.

To support a new Config Data location type, inspect:

```text
ConfigDataLocationResolver
ConfigDataLoader
```

and the corresponding API version.

If you only need an external `application.yml`, use standard Config Data locations. If you need Config Server, use the matching Config Client train.

**Pick extension points for the problem**, not outdated compatibility workarounds.

## 55. When Old and New Docs Conflict, Which Wins?

A documentation evaluation rubric:

1. **Identify your project's versions.**
2. **Prioritize exact-version reference docs.**
3. **Read release notes and migration guides across your upgrade span.**
4. **Consult the compatibility matrix for Spring Cloud.**
5. **Treat issues and blogs as supporting clues, not authoritative replacements for official docs.**
6. **Reproduce in a minimal project or test context running your exact versions.**
7. **Document the findings alongside your project's versions.**

Example:

- A 2019 blog states `bootstrap.yml` is standard for Config Server.
- Current docs state `spring.config.import=configserver:`.
- Your project runs Boot 2.7 + Cloud 2021.0.x.

That does not make the 2019 post "wrong" historically—it matched the author's stack. Applying it to Boot 2.7 requires aligning with Config Data and matching Cloud rules.

## 56. Signs a Guide Is Under-Specified

Be skeptical when an article:

- Omits the Spring Boot version.
- Omits the Spring Cloud train.
- Conflates Spring Cloud Config Client with plain Boot.
- Tells you to create `bootstrap.yml` without stating whether legacy bootstrap is enabled.
- Recommends `spring.config.use-legacy-processing=true` for "every modern Boot version."
- Lists mismatched dependency versions without a BOM.
- Ignores missing remote source handling.
- Gives no guidance on testing profiles or precedence.
- Relies on an old IDE screenshot or dated console snippet.
- Omits launch commands or environment setup.
- Blames a `BindException` on "Config Server failed to connect" without checking the cause.
- Advises printing the entire `Environment`/`PropertySources` including secrets.

Do not discard blogs entirely—fill in the missing pieces using exact-version official docs and tests.

## 57. Minimal Sandbox Steps Before Migrating Bootstrap

Spin up a small sandbox on your target versions:

1. Create a minimal app with a compatible BOM.
2. Add the Config Client dependency if testing remote config.
3. Add `application.yml` with `spring.application.name` and import.
4. Put a non-sensitive property in Config Server, e.g., `demo.source=remote`.
5. Run the app with the `dev` profile.
6. Verify `Environment#getProperty("demo.source")` and the visible source.
7. Stop Config Server and observe startup behavior.
8. Test optional and non-optional imports separately.
9. Test overriding a property via CLI.
10. Record logs and observed behavior.
11. Once the new path is understood, migrate the real project.

Never test against production secrets or a sensitive Config Server just to verify a demo property.

## 58. Minimal Runnable Local Config Data Example (No Cloud Needed)

A pure Spring Boot example ideal for isolating Config Data mechanics.

```text
src/main/resources/
├── application.yml
└── extra.yml
```

```yaml
# application.yml
spring:
  config:
    import: "classpath:extra.yml"

demo:
  message: "local"
```

```yaml
# extra.yml
demo:
  message: "from-import"
```

Record:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String message) {
}
```

Application:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Notice `extra.yml` sets the same `demo.message` key so you can observe precedence between the importing file and imported file.

This example **does not use Spring Cloud** and runs in any Boot project supporting Config Data. It helps separate general Config Data issues from `configserver:` issues.

## 59. Config Client Configuration Example on Compatible Versions

With Spring Cloud Config Client managed by a matching BOM:

```yaml
# application.yml
spring:
  application:
    name: config-client-demo
  config:
    import: "optional:configserver:http://localhost:8888"

demo:
  message: "local-fallback"
```

When Config Server is up, remote config can supply:

```properties
demo.message=remote
```

When the server is down, an optional import can allow startup depending on version details and retry/fail-fast settings, falling back locally where appropriate.

Tests should actually verify:

- Application/profile names requested from the server.
- Whether remote properties loaded.
- Whether the final value is remote or overridden by a higher source.
- Behavior when the server is offline.
- Exceptions raised when remote config supplies an unconvertible value.

Never assume declaring an import guarantees every value comes from the server.

## 60. Distinguishing File, Network, and Bean Errors

Three failure paths:

**A. Required local file missing**

```properties
spring.config.import=file:./required.yml
```

Fails during Config Data resolution/loading.

**B. Config Server unreachable**

```properties
spring.config.import=configserver:http://localhost:8888
```

Fails when the resolver/loader calls the remote server, depending on import and client settings.

**C. File or server loaded, yet bean binding fails**

```properties
client.timeout=not-a-duration
```

Fails during conversion/binding.

They happen at distinct stages:

```text
Config Data location
       |
       v
Resolution / Loading ----> file/network error
       |
       v
Spring Environment
       |
       v
Binder / Conversion -----> type error
       |
       v
Bean Validation ----------> constraint error
```

Do not fix a conversion error by enabling legacy bootstrap, and do not fix a network error by removing `@Validated`.

## 61. Documenting Project Setup to Prevent Repeated Mistakes

Include a summary block in your internal README:

```text
Spring Boot version:       <exact-version>
Spring Cloud train:        <exact-train>
Config Client:             Yes/No
Remote config mechanism:   Config Data import / Legacy bootstrap
Config Server location:    where it is supplied from
Active profile:            where it is supplied
Fail-fast/optional:        policy
Retry:                     policy
Fallback:                  which defaults are permitted
How to test:               command + expected outcome
Reference docs:            exact-version URL
```

Replace placeholders with actual values before sharing with the team.

Documentation can also include a decision log table:

| Decision | Rationale |
| --- | --- |
| Use Config Data import | Matches current Boot/Cloud generation |
| Omit bootstrap starter | No legacy use case |
| Require remote config in prod | Prevents booting with unsuitable defaults |
| Allow local fallback in dev | Enables offline development |
| Enable bean validation | Catches bad configuration early |

Documenting decisions matters more than pasting an isolated YAML snippet.

## 62. FAQ: Is `bootstrap.yml` Still "Supported"?

The complete answer is: **it depends on your modules, versions, and bootstrap mode**.

- In plain Boot using default Config Data, `bootstrap.yml` is not a standard app file automatically loaded like `application.yml`.
- In a Spring Cloud setup intentionally enabling **legacy bootstrap context**, `bootstrap.yml` can still function per that version's documentation.
- In modern Config Client mode, `spring.config.import=configserver:` is used without needing a `bootstrap.yml` to import Config Server.

Avoid blanket answers like "`bootstrap.yml` is always dead" or "`bootstrap.yml` is always required."

## 63. FAQ: Should I Delete `bootstrap.yml` Immediately When Upgrading Boot?

Never delete it purely because a dependency version changed.

Check first:

1. Which properties are inside the file?
2. Do they govern Spring Cloud Config, service discovery, security, profiles, or startup logging?
3. Which mode is currently active?
4. Do any internal extensions read the bootstrap context?
5. Where will each setting move?
6. Are there tests verifying remote config and precedence?
7. Is there a rollback plan if startup fails?

Once loading paths are migrated and verified by tests, remove the old bootstrap file if no longer needed. Never keep two duplicate files without explicit precedence rules.

## 64. FAQ: Can I Put `spring.config.import` Only Inside `bootstrap.yml`?

In Config Data mode, documentation recommends placing imports in `application.yml` or another configuration source loaded at the proper phase.

If legacy machinery reading `bootstrap.yml` is disabled, a `spring.config.import` sitting **inside an unloaded `bootstrap.yml`** cannot trigger loading of that very file.

This is a classic circular pitfall when copying guides:

```text
bootstrap.yml is not loaded
       |
       v
spring.config.import sits inside bootstrap.yml
       |
       v
import is never seen
```

Place `spring.config.import` in a source Spring Boot actually reads during Config Data processing.

## 65. FAQ: Does the New Config Client Always Require Config Server to Be Running?

Not all configurations behave identically.

- With a mandatory import, an unreachable server fails startup.
- With an optional import, the app can proceed using local data under suitable conditions.
- Retries and fail-fast settings alter timing and error behavior.
- If the app also enforces required bean validation, missing remote properties can still fail context startup even with an optional import.

Saying "Config Server isn't needed thanks to `optional:`" is incomplete. Check the impact on the application's **final configuration contract**.

## 66. FAQ: Does `spring.config.use-legacy-processing` Fix All Upgrade Issues?

No. It was a historical transition mechanism for moving from Boot 2.3 to 2.4 in releases that supported it.

It does not replace:

- selecting a compatible Spring Cloud train;
- configuring Config Client properly;
- fixing invalid profile YAML;
- migrating Java/Jakarta APIs;
- auditing dependencies;
- testing network/remote config;
- verifying precedence;
- writing migration tests.

Aim for the mechanism supported long-term by your target version's docs.

## 67. Exercise A: Identifying a Guide's Era

You read an example:

```yaml
# bootstrap.yml
spring:
  cloud:
    config:
      uri: http://localhost:8888
```

The post omits `spring.config.import` and states the project runs Boot 2.3.

**Question:** Which style does this guide describe?

**Answer:** Spring Cloud **legacy bootstrap**. It may be accurate for that historical stack, yet moving to Boot 2.4+ and matching Cloud trains requires re-evaluating against Config Data.

## 68. Exercise B: A Plain Boot App

A project includes only the Boot starter. File:

```yaml
# bootstrap.yml
demo:
  mode: "safe"
```

No Cloud bootstrap or extra import is configured.

**Question:** Can you rely on Spring Boot automatically loading `demo.mode`?

**Answer:** no. `bootstrap.yml` is not a standard default Config Data file in plain Boot applications. Use `application.yml` or an explicit import.

## 69. Exercise C: Migrating Config Client

A project uses Spring Cloud Config Client compatible with Boot 3.x and has no need to keep legacy bootstrap.

**Task:** propose an import configuration connecting to Config Server on `localhost:8888` while allowing local development when the server is offline.

**Sample Answer:**

```yaml
spring:
  application:
    name: sample-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Test both server-online and server-offline cases; `optional:` does not replace validation for required properties.

## 70. Exercise D: Distinguishing Legacy Flags

Explain:

```text
spring.config.use-legacy-processing=true
spring.cloud.bootstrap.enabled=true
```

**Answer:**

- The first reverts to pre-Boot 2.4 config-processing rules in transitional versions supporting it.
- The second enables **Spring Cloud legacy bootstrap** per the corresponding Cloud mechanism and version.

They are not two spellings for the same feature.

## 71. Exercise E: Profile Migration

Old example:

```yaml
spring:
  profiles: prod

app:
  mode: live
```

**Task:** rewrite the document condition using Config Data syntax.

**Answer:**

```yaml
spring:
  config:
    activate:
      on-profile: prod

app:
  mode: live
```

And activate the profile from a proper source such as CLI:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Never put `spring.profiles.active` inside the conditioned document itself.

## 72. Exercise F: Compatibility Matrix

A project uses Boot 3.5 yet pulls in Spring Cloud 2020.0.x copied from an old blog.

**Question:** What should be checked first?

**Answer:** the Spring Cloud train does not match Boot 3.5. Consult Spring Cloud's current compatibility table and select the train officially paired with Boot 3.5 instead of mixing mismatched Cloud modules.

## 73. Exercise G: Multiple Config Server Requests

After switching to Config Data imports, logs show two config requests during a single startup. A developer insists this must be a bug.

**Answer:** not necessarily. Spring Cloud Config Client notes Config Data may resolve profiles in multiple passes, triggering additional requests. Inspect profiles and logs to separate normal lifecycle passes, network-error retries, and unintended duplicate fetches.

## 74. Exercise H: File Loaded Yet Value Wrong

Config Data TRACE shows `application-prod.yml` loaded. Yet the bean gets `client.timeout=9s` instead of `5s` from the file.

**Question:** Should we conclude the loader is broken?

**Answer:** no. Check higher-precedence sources such as CLI, environment variables, remote Config Server, or custom `PropertySources`; the file loaded properly and was simply overridden.

## 75. Exercise I: An Undated Internet Guide

You find a Spring Cloud Config article that:

- Omits the Boot version.
- Omits the Spring Cloud train.
- Uses `bootstrap.yml`.
- Pins unaligned Maven dependency versions without a BOM.
- Has no fail-fast or profile tests.

**Question:** Should you copy it straight into production?

**Answer:** no. Verify your project versions, consult official docs and compatibility matrices, verify how bootstrap is enabled, pick your mode intentionally, and write startup tests with realistic remote sources and paths.

## 76. Official References

Links for checking and cross-referencing by version:

1. **Spring Boot — Externalized Configuration**  
   https://docs.spring.io/spring-boot/reference/features/external-config.html

2. **Spring Boot — Config Data Migration Guide**  
   https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Config-Data-Migration-Guide

3. **Spring Boot — 2.4 Release Notes**  
   https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.4-Release-Notes

4. **Spring Cloud Config — Config Client**  
   https://docs.spring.io/spring-cloud-config/reference/client.html

5. **Spring Cloud — Release Train / Spring Boot Compatibility**  
   https://spring.io/projects/spring-cloud/

6. **Spring Cloud — Release Train Reference**  
   https://docs.spring.io/spring-cloud-release/reference/index.html

**Usage note:** current URLs evolve as new releases ship. When maintaining Boot 2.7 or a specific Cloud train, pick the archived docs or version selector and record the **exact-version URL** in your project README.

This lesson does not demand always running the latest release; it demands **never mixing documentation from one generation with a runtime from another**.

## 77. Key Takeaways

- **Spring Boot 2.4 was a major turning point**, introducing Config Data and `spring.config.import`.
- **Spring Cloud legacy bootstrap context**, **Spring Boot bootstrap registry**, and **Config Data** are distinct concepts; seeing the word "bootstrap" never tells you how files load.
- `bootstrap.yml` belongs to legacy Spring Cloud tutorials; it **does not automatically act as the default configuration file in every Spring Boot app**.
- With Config Data-compatible Spring Cloud Config Client, use `spring.config.import=configserver:...` or `optional:configserver:...` per policy rather than assuming `bootstrap.yml` is required.
- Legacy bootstrap can still be enabled intentionally via mechanisms supported by your Cloud version, such as `spring.cloud.bootstrap.enabled` or `spring-cloud-starter-bootstrap`.
- `spring.config.use-legacy-processing` belongs to Spring Boot 2.4 migration compatibility, **not** Spring Cloud bootstrap, and is not a permanent upgrade solution.
- Spring Boot and Spring Cloud **must be paired via the compatibility matrix**. Picking versions from random blogs is risky.
- When migrating to Config Data, re-verify **profile activation**, multi-document YAML, `spring.config.import`, `optional:`, precedence, and remote fetches.
- A file loading cleanly **does not guarantee its values win**; effective runtime values depend on all active `PropertySources`.
- Startup failures can stem from **location loading**, **networking**, **binding/conversion**, **validation**, or **dependency mismatches**; do not blame every failure on bootstrap.
- Always cross-reference **exact-version reference docs**, migration guides, release notes, and tests against the real artifact.
- The goal of upgrading is a **configuration contract that is explainable, testable, and repeatable to deploy**, not merely renaming `bootstrap.yml` to `application.yml`.
