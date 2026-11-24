# Activating Configuration Documents by Platform with `spring.config.activate.on-cloud-platform`

## 1. Context and goal

A Spring Boot application can run on a laptop, a standard server, Docker, or an orchestration platform such as Kubernetes. The same source code and build artifact still need different configuration: running locally might use a file on disk, whereas Kubernetes might supply configuration from a ConfigMap or Secret mounted as files.

Spring Boot supports **conditional configuration documents** in the **Config Data** mechanism. The property:

~~~properties
spring.config.activate.on-cloud-platform=kubernetes
~~~

specifies: **activate the configuration document containing this property only when Spring Boot determines that the active cloud platform is Kubernetes**.

In YAML, the corresponding property is:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

The goal is to write a shared configuration set while applying certain properties only when the runtime environment matches, instead of duplicating multiple files or forcing deployers to always pass an extra profile.

Distinguish three concepts:

- **Cloud platform**: the type of platform running the application as detected by Spring Boot, such as Kubernetes.
- **Spring profile**: an environment or feature name used by the application, such as `dev`, `test`, `prod`.
- **Config Data document**: a logical document inside `application.yml`, `application.yaml`, or `application.properties` that can be conditionally activated.

`spring.config.activate.on-cloud-platform` checks the cloud platform. It **does not turn on profiles**, does not create Kubernetes beans automatically, and does not connect to the Kubernetes API server on its own.

## 2. How does Spring Boot activate a document?

In Spring Boot's modern Config Data model, one physical configuration file can contain multiple **logical documents**. Documents are processed in order; a later document can override properties from an earlier document within the same loading context.

A document can declare activation metadata:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

Spring Boot evaluates the condition before adding the document's properties to the effective configuration sources.

- **Condition is true:** the document is loaded and its properties can participate in `Environment`.
- **Condition is false:** the document is skipped; properties located solely in that document do not become effective configuration from this source.
- **No activation condition:** the document can be loaded normally according to location, filename, profile, and other Config Data rules.

For example, an application has a shared configuration for all environments and a separate configuration for Kubernetes:

~~~yaml
# application.yml
app:
  storage:
    directory: ./data
  messaging:
    endpoint: localhost:9092
---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  storage:
    directory: /var/app/data
  messaging:
    endpoint: messaging.default.svc.cluster.local:9092
~~~

Interpretation:

1. When running locally and Spring Boot does not detect Kubernetes, the first document supplies `app.storage.directory=./data` and `app.messaging.endpoint=localhost:9092`.
2. When running in an environment detected as Kubernetes, the second document is activated. Within the scope of this file, it overrides the two values with `/var/app/data` and the corresponding internal service address.
3. Another higher-precedence source, such as a command-line argument in common configurations, can still override the values above.

The example only illustrates the configuration mechanism. The `messaging.default.svc.cluster.local` address works only if the corresponding Service and DNS actually exist; Spring Boot does not create them from this YAML.

## 3. Distinguishing cloud platform detection from profile activation

`spring.config.activate.on-cloud-platform` uses the **CloudPlatform** detected by Spring Boot. `spring.config.activate.on-profile` uses a profile expression. Both properties belong to the `spring.config.activate.*` group, yet they test two different conditions.

| Property | Checks | Example |
| --- | --- | --- |
| `spring.config.activate.on-cloud-platform` | Cloud platform detected by Spring Boot | `kubernetes` |
| `spring.config.activate.on-profile` | Active Spring profile expression | `prod | staging` |
| `spring.profiles.active` | Declares list of profiles to activate | `prod,observability` |
| `spring.main.cloud-platform` | Overrides cloud platform auto-detection result | `kubernetes` |

For example, in Kubernetes when the application only has the `dev` profile:

- A document with `on-cloud-platform=kubernetes`: **eligible** on cloud platform.
- A document with `on-profile=prod`: **ineligible** on profile `prod`.
- A document containing both `on-cloud-platform=kubernetes` and `on-profile=prod`: **not activated**, because both are not yet satisfied.

Conversely, running the `prod` profile on a local machine does not cause Boot to treat that environment as Kubernetes.

**There is no default rule that "a profile named `kubernetes` is enabled when running on Kubernetes".** If the application has an `application-kubernetes.yml` file, that file is **profile-specific** and is selected by the `kubernetes` profile, rather than being automatically loaded just because the runtime is on Kubernetes.

## 4. How Spring Boot determines CloudPlatform

Spring Boot has the `org.springframework.boot.cloud.CloudPlatform` enum representing several recognized cloud platforms. Depending on the version, the list may include Kubernetes, Cloud Foundry, Heroku, SAP, Nomad, Azure App Service, and others. The `NONE` value represents the case where no cloud platform is selected.

For Kubernetes, Spring Boot uses characteristic environmental cues, such as environment variables related to Kubernetes Services, to determine whether the application is running on this platform.

For example, in a typical Kubernetes environment, variables like these may exist:

~~~text
KUBERNETES_SERVICE_HOST
KUBERNETES_SERVICE_PORT
~~~

The exact detection checks can change across Spring Boot versions. Therefore, do not design an application assuming that the mere presence of any arbitrary variable is enough to always detect Kubernetes.

### 4.1. Auto-detection is not infrastructure authentication

CloudPlatform detection relies on environment information. It is useful for selecting configuration or auto-configuration, but it is **not** a mechanism verifying that the process genuinely belongs to a trusted Kubernetes cluster.

Do not use `on-cloud-platform` as a security boundary, such as "if on Kubernetes, automatically allow access to sensitive resources". Access control must be enforced by real security mechanisms, such as network policies, service accounts, authorization, and secret management.

### 4.2. CloudPlatform can be overridden

When the real environment does not provide sufficient detection signals, or when simulating behavior in a test environment, you can use:

~~~bash
java -jar app.jar --spring.main.cloud-platform=kubernetes
~~~

`spring.main.cloud-platform` instructs Spring Boot to use the specified platform instead of auto-detection. Similarly, the configuration:

~~~bash
java -jar app.jar --spring.main.cloud-platform=none
~~~

can be used to disable cloud platform detection in appropriate cases.

This is a **startup option affecting cloud detection**, not a way to enable Spring profiles. Adding `--spring.profiles.active=prod` is a different property:

~~~bash
java -jar app.jar \
  --spring.main.cloud-platform=kubernetes \
  --spring.profiles.active=prod
~~~

The command above can be used to simulate **Kubernetes + prod profile** to observe conditional documents. It does not create a Kubernetes cluster, mount ConfigMaps, connect Secrets, or provide real Kubernetes networking services.

### 4.3. Check the enum for your Boot version

Valid names in `on-cloud-platform` are based on `CloudPlatform` in the Spring Boot version you are using. For instance, Kubernetes uses `kubernetes`; for other platforms, consult the API documentation of that exact version to choose the right name.

Do not assume any arbitrary cloud provider name is valid, such as setting `on-cloud-platform=my-private-cloud` and expecting Boot to detect it. This mechanism relies on Spring Boot's defined set of values; to support custom-named environments, a Spring profile or a dedicated application property is usually more appropriate.

## 5. Standard example with multi-document YAML

In `application.yml`, use `---` to separate logical documents:

~~~yaml
# Document 1: can always be used as base configuration
spring:
  application:
    name: order-service

app:
  storage:
    root: ./data
  endpoints:
    inventory: http://localhost:8081

---
# Document 2: considered only when the cloud platform is Kubernetes
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  storage:
    root: /mnt/order-data
  endpoints:
    inventory: http://inventory.default.svc.cluster.local:8080
~~~

Spring Boot processes documents in order from top to bottom. If the second document is activated, it can override same-named keys in the first document. If skipped, the base configuration can still function.

### 5.1. Meaning of the three dashes

In YAML, `---` separates documents. It must be placed in a valid YAML position; it is not a key name and not a profile.

Incorrect example treating `---` as a property:

~~~yaml
app:
  name: catalog
  ---: kubernetes
~~~

This does not create a conditional document. You need a separate document after the separator and must declare `spring.config.activate.on-cloud-platform` inside that document.

### 5.2. You can have multiple documents for multiple platforms

Illustrative example:

~~~yaml
app:
  transport:
    mode: local

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  transport:
    mode: kubernetes

---
spring:
  config:
    activate:
      on-cloud-platform: cloud-foundry
app:
  transport:
    mode: cloud-foundry
~~~

The Kubernetes and Cloud Foundry documents have independent conditions. Platform names must be supported and detected by Spring Boot. Using multiple documents groups conditions in the same file, though if the file grows too long, you can organize them into separate Config Data files and import them conditionally.

### 5.3. Avoid placing keys without defaults solely in a conditional document

If a required key appears only in the Kubernetes document:

~~~yaml
---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  payment:
    endpoint: http://payment.default.svc.cluster.local
~~~

then running locally might lack `app.payment.endpoint`. If the application calls `Environment.getRequiredProperty("app.payment.endpoint")` or binds to a required field, startup may fail.

There are two ways to handle this:

1. Provide a sensible default value in the base document.
2. Design the component using that value so it is also only created when the appropriate condition is satisfied, such as with a profile or separate condition.

Do not confuse a skipped document with keys automatically receiving empty or fallback values.

## 6. Equivalent example with `application.properties`

The `.properties` format does not use YAML's `---`. Spring Boot supports separating documents using **`#---` or `!---`**:

~~~properties
# application.properties
spring.application.name=order-service
app.storage.root=./data
app.endpoints.inventory=http://localhost:8081
#---
spring.config.activate.on-cloud-platform=kubernetes
app.storage.root=/mnt/order-data
app.endpoints.inventory=http://inventory.default.svc.cluster.local:8080
~~~

When Kubernetes is detected, the document after `#---` is activated; otherwise, it is skipped.

### 6.1. Separator placement rules in properties

When using multi-document properties:

- The separator must be on its own line with exact `#---` or `!---` syntax per Boot rules.
- There must be no leading whitespace on the separator line.
- There must be **exactly three `-` characters**.
- Do not place comment lines with the same prefix immediately before or after the separator in a way that violates Boot's splitting rules.

For example, place explanatory comments inside documents where they create no ambiguity:

~~~properties
app.mode=local
#---
spring.config.activate.on-cloud-platform=kubernetes
app.mode=cluster
~~~

In plain Spring Framework systems, `#---` is normally just a comment line. Document splitting is handled by Spring Boot when loading Config Data; `@PropertySource` and `@TestPropertySource` do not process multi-document properties this way.

### 6.2. Do not confuse with ordinary `#` comments

A line:

~~~properties
# Kubernetes configuration
~~~

is a normal comment. However, `#---` has special semantics when Spring Boot loads multi-document properties. If you only want a visual divider, use another line such as:

~~~properties
# ===== Kubernetes-specific settings =====
~~~

## 7. Combining cloud platform and profile conditions

Spring Boot supports both together:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
      on-profile: "prod | staging"
~~~

This means the document is activated only when:

1. The cloud platform is identified as **Kubernetes**.
2. The profile expression `prod | staging` is true, meaning **at least one** of `prod` or `staging` is active.

**Two conditions of different types are combined with AND**. Inside the `on-profile` expression, the `|` operator represents OR between profile choices.

Complete example:

~~~yaml
app:
  feature:
    audit-enabled: false
  integration:
    endpoint: http://localhost:8080

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
      on-profile: "prod | staging"

app:
  feature:
    audit-enabled: true
  integration:
    endpoint: http://integration.default.svc.cluster.local:8080
~~~

Interpretation table assuming no other overriding source:

| Cloud platform | Active profiles | Second document | `app.feature.audit-enabled` |
| --- | --- | --- | --- |
| Kubernetes | `prod` | Activated | `true` |
| Kubernetes | `staging` | Activated | `true` |
| Kubernetes | `dev` | Skipped | `false` |
| Not Kubernetes | `prod` | Skipped | `false` |
| Not Kubernetes | `dev` | Skipped | `false` |

If you want to activate only in Kubernetes **and** the `prod` profile, use:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
      on-profile: prod
~~~

If you want a document to apply across multiple different cloud platforms, do not assume `on-cloud-platform` accepts an OR expression string like `on-profile` does. You can create separate documents per platform or organize configuration using another mechanism supported by your Boot version.

## 8. Combining with `spring.config.import` and Config Tree

This is a common scenario when running applications on Kubernetes: configuration is attached as a **volume**, where each file holds one configuration value.

Suppose the container has this layout:

~~~text
/etc/app-config/
├── api.endpoint
└── api.timeout
~~~

Contents:

~~~text
/etc/app-config/api.endpoint  ->  https://api.internal.example
/etc/app-config/api.timeout   ->  5s
~~~

Spring Boot supports `configtree:`, allowing each file in a directory to be loaded as a property with the corresponding name. You can import this configuration tree only when running on Kubernetes:

~~~yaml
app:
  api:
    endpoint: http://localhost:8081
    timeout: 2s

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
    import: "optional:configtree:/etc/app-config/"
~~~

When the cloud platform is detected as Kubernetes, the conditional document is evaluated and the Config Tree import can bring `api.endpoint` and `api.timeout` into `Environment`. When running locally, that document is not activated and the associated import does not participate in configuration loading.

**Note on the example:** the two keys in the Config Tree here are `api.endpoint` and `api.timeout`, which differ from `app.api.endpoint` and `app.api.timeout` in the base document. If you want to override the `app.api.*` keys directly, name the files in the tree accordingly (for example `app.api.endpoint`, `app.api.timeout`), or rename the base configuration keys to match.

To load required files from a directory, you can omit `optional:`:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
    import: "configtree:/etc/app-config/"
~~~

In that case, a missing required location can prevent the application from starting. This is often helpful if a missing ConfigMap/Secret is a deployment error that should be caught early. `optional:` only allows the location to be absent; it does not guarantee ignoring formatting, permission, or binding errors.

### 8.1. Config Tree vs. `file:`

The following two locations are not equivalent:

~~~text
configtree:/etc/app-config/
file:/etc/app-config/
~~~

`configtree:` treats filenames in the tree as property names; `file:` is normally used to look up configuration files by names such as `application.properties` or `application.yml`.

Choose the right import prefix so the application interprets mounted data properly. You do not need to install Spring Cloud Kubernetes just to use the basic Config Data and `configtree:` mechanisms supported by Spring Boot.

### 8.2. Do not treat Config Tree as a complete security solution

Config Tree is convenient when infrastructure supplies files from a Secret volume, yet security also depends on RBAC, file read permissions, mount configuration, service account permissions, and avoiding leaking contents via logs or diagnostic endpoints. `on-cloud-platform` only decides whether a document is applied, not who has permission to read secrets.

## 9. How does the cloud platform condition differ from locations, precedence, and imports?

`spring.config.activate.on-cloud-platform` is **the condition for a document to participate in loading**. It does not alter the general precedence rules across all property sources.

Distinguish three layers:

1. **Discovering sources:** Spring Boot checks default locations, `spring.config.location`, `spring.config.additional-location`, `spring.config.import`, and related locations.
2. **Activating documents:** Boot evaluates `on-cloud-platform` and, if present, `on-profile` for each document.
3. **Computing effective values:** Accepted property sources enter the precedence and override mechanism.

Example:

~~~yaml
server:
  port: 8080
---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
server:
  port: 8085
~~~

Within the same file and without higher-precedence sources, when Kubernetes is detected `server.port` can be `8085`. However, if started with:

~~~bash
java -jar app.jar --server.port=9090
~~~

then in standard Spring Boot setups, command-line arguments have higher priority and `server.port` becomes `9090` even though the Kubernetes document is activated.

Similarly, an external file loaded from a higher-precedence location can override properties declared in a Kubernetes document packaged inside the JAR.

**Do not conclude that a document containing `on-cloud-platform=kubernetes` always beats other documents.** The condition only allows the document to participate, while the final outcome depends on locations, document order, and other sources.

## 10. Organizing configuration by environment

### 10.1. When to use cloud conditions?

Appropriate when the main difference is **the runtime platform**:

- Local runs use the `./data` directory; Kubernetes runs use the `/var/app/data` mount.
- Kubernetes runs import a config tree from a volume, while local runs use project configuration.
- An internal endpoint only makes sense inside Kubernetes and should be declared separately in the Kubernetes document.
- The same artifact runs both on Kubernetes and on standard servers, and you do not want to maintain an extra profile solely to distinguish the two infrastructures.

### 10.2. When to use Spring profiles?

Profiles are appropriate when the main difference is **environment purpose or operating mode**:

- `dev`: mock services and development log levels.
- `test`: test data and test configuration.
- `prod`: production configuration.
- `debug`: controlled diagnostic tools enabled.

When both platform and environment matter, you can combine `on-cloud-platform` with `on-profile` instead of creating many complex profile names like `prod-kubernetes` or `staging-kubernetes`.

### 10.3. Do not turn cloud conditions into business branching

Platform conditions should describe genuine technical differences. For example, whether a user's tax rate differs by country should not depend on whether the service runs on Kubernetes or Cloud Foundry. Business logic should be managed with business configuration, data, or appropriate feature flags.

Similarly, deciding to use a production database should not be based solely on cloud platform. Kubernetes can run production, staging, and development workloads alike.

## 11. Testing behavior locally without a Kubernetes cluster

You can use `spring.main.cloud-platform` to test configuration branches. Create `application.yml`:

~~~yaml
app:
  runtime:
    description: local
    path: ./data

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  runtime:
    description: kubernetes
    path: /mnt/data
~~~

Run normally on your local machine:

~~~bash
java -jar app.jar
~~~

When no cloud platform is detected and no forced platform configuration is set, the `app.runtime.*` properties from the base document take effect.

Run with an explicit cloud platform selection:

~~~bash
java -jar app.jar --spring.main.cloud-platform=kubernetes
~~~

Assuming no other source overrides these properties, the Kubernetes document is activated and `app.runtime.description` receives `kubernetes`.

You can verify with a small application component:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationDisplay implements ApplicationRunner {
    private final Environment environment;

    public ConfigurationDisplay(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String description = environment.getProperty("app.runtime.description");
        String path = environment.getProperty("app.runtime.path");
        System.out.println("Runtime description: " + description);
        System.out.println("Runtime path: " + path);
    }
}
~~~

This is an example of inspecting non-sensitive values. Do not log passwords, tokens, secret keys, or the entire `Environment` just to see which document was activated.

**Important limitation:** forcing `spring.main.cloud-platform=kubernetes` only simulates Spring Boot's platform selection. Calls to the Kubernetes API, actual mounts, internal service DNS, or Kubernetes ServiceAccounts still do not exist on a local machine unless separately provided. Therefore, use this mode to verify configuration, not as a full infrastructure integration test.

## 12. Common mistakes

### 12.1. Using the wrong property name

**Wrong:**

~~~yaml
spring:
  profiles:
    activate:
      on-cloud-platform: kubernetes
~~~

**Correct:**

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

The required prefix is `spring.config.activate`, not `spring.profiles.activate`.

### 12.2. Placing the condition outside the document to be activated

A property only governs **the logical document containing it**; it does not automatically apply the condition to other documents in the file.

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  mode: cluster
---
app:
  timeout: 3s
~~~

In this example, the first document has the Kubernetes condition. The second document is a separate document and does not automatically inherit that condition. If you want the later document to apply only on Kubernetes as well, declare the condition on the later document itself or reorganize the properties into the same document.

### 12.3. Thinking `on-cloud-platform=kubernetes` enables the `kubernetes` profile

No. If `application-kubernetes.properties` exists, that file remains a profile-specific file. The cloud condition does not automatically make the `kubernetes` profile appear in `Environment.getActiveProfiles()`.

### 12.4. Using a platform name not supported by Spring Boot

This mechanism relies on the `CloudPlatform` enum of the Boot version in use. Do not treat any arbitrary string name as a valid value. For an unrecognized platform, consider a Spring profile or a specific application property.

### 12.5. Expecting external config files to exist automatically

A Kubernetes document can declare:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
    import: "configtree:/etc/config/"
~~~

If `/etc/config/` is not properly mounted, the application may fail. The cloud condition only determines whether to evaluate that import; it does not create volumes or files.

### 12.6. Ignoring precedence order

When a property in a Kubernetes document does not take effect as expected, inspect environment variables, startup arguments, external files, profile-specific documents, and location groups. The document may have been activated properly while its value was overridden by a higher-precedence source.

### 12.7. Expecting values to change automatically when a process moves environments

Config Data documents are processed during startup. Moving a container to another cluster, changing environment variables, or editing mounted files after the context is ready does not mean documents are automatically re-activated. If dynamic configuration is desired, a dedicated refresh/reload mechanism must be designed; a typical Spring Boot application requires a restart to apply such major changes.

### 12.8. Trying to enable profiles inside a conditional document

Avoid writing:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
  profiles:
    active: prod
~~~

inside a document that is only loaded when a cloud condition is true. In modern Config Data, declaring `spring.profiles.active`, `spring.profiles.default`, or include/group options in conditionally activated documents is restricted and can cause configuration errors.

A clearer approach: place `spring.profiles.active` in a non-profile-specific configuration source (or supply it via environment variable/command line), then use `on-cloud-platform` and `on-profile` on documents requiring both conditions.

### 12.9. Using `@PropertySource` to read multi-document properties

Spring Framework's `@PropertySource` does not handle `#---` document splitting the way Boot's Config Data does. If you rely on activation features, place configuration in sources loaded by Spring Boot Config Data, such as `application.properties`, `application.yml`, or appropriate locations/imports.

## 13. Diagnostic workflow

When a property in a document with `on-cloud-platform=kubernetes` does not appear:

1. **Check the Spring Boot version.** Confirm the application uses the Config Data mechanism supporting `spring.config.activate.*` (introduced in Spring Boot 2.4).
2. **Check whether the document is loaded from a valid source.** For example, is `application.yml` in a Config Data location Boot searches? Are the filename and extension correct?
3. **Check separator syntax.** YAML requires `---`; properties require `#---` or `!---` following their syntax rules.
4. **Check the exact condition name.** Use `spring.config.activate.on-cloud-platform`, not an arbitrary name.
5. **Check the actual platform.** Is Spring Boot detecting the app as Kubernetes? Is there a `spring.main.cloud-platform` override from another configuration source?
6. **Check remaining conditions.** If the same document has `on-profile`, the profile expression must also evaluate to true.
7. **Check property conflicts.** If the document is activated but the value mismatches, inspect higher-precedence sources and document order.
8. **Check imports and volumes.** When the document contains `spring.config.import`, verify the path exists and has read permissions; consider whether `optional:` should be used.
9. **Check whether the context was restarted.** Spring Boot does not re-activate Config Data simply because external environment variables changed.
10. **Read startup error messages.** Do not mask `ConfigDataLocationNotFoundException` or parse errors by blindly ignoring errors across all locations.

You can enable detailed Config Data logging during a diagnostic run:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

The exact log messages depend on the Boot version. Do not enable overly verbose logging in environments with sensitive data unless log storage and viewing permissions are properly controlled.

If Spring Boot Actuator is enabled with proper security configuration, the `/actuator/env` endpoint can help inspect property sources and values masked by policy. This endpoint also does not replace verifying which platform was detected during startup.

## 14. Two-environment deployment example

### 14.1. Local development

Base configuration:

~~~yaml
# application.yml
app:
  cache:
    provider: in-memory
  config:
    location: ./config

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  cache:
    provider: redis
  config:
    location: /etc/myapp
~~~

Start on a developer machine:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

If no Kubernetes platform is detected, the Kubernetes document is skipped. `app.cache.provider` stays `in-memory` and `app.config.location` is `./config`.

### 14.2. Kubernetes production

The same JAR/container image can be used with the configuration file above:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: example/catalog:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
~~~

In a Kubernetes environment detected by Boot, the Kubernetes document is activated. `app.cache.provider` becomes `redis` and `app.config.location` becomes `/etc/myapp`, unless overridden by a higher-precedence source.

The manifest above only illustrates how to set the profile. The value `redis` does not create a Redis Service, and `/etc/myapp` is not automatically mounted; those resources must be provisioned separately.

## 15. Comparing options

| Goal | Suitable tool | Notes |
| --- | --- | --- |
| Separate config for Kubernetes vs. local | `spring.config.activate.on-cloud-platform=kubernetes` | Based on platform detected by Boot |
| Separate dev/test/prod | `spring.config.activate.on-profile` or `application-{profile}.*` files | Based on active profiles |
| Select profile from runtime environment | `spring.profiles.active`, `SPRING_PROFILES_ACTIVE` | Does not auto-detect cloud platform |
| Force Boot to detect platform during testing | `spring.main.cloud-platform` | Simulates detection only; creates no infrastructure |
| Load individual files from mounted volume | `spring.config.import=configtree:...` | Requires valid path and read permissions |
| Load Config Tree only on Kubernetes | `on-cloud-platform` with `spring.config.import` | Place import inside conditional document |
| Select Java bean by platform | `@ConditionalOnCloudPlatform` when appropriate | Bean-creation condition, distinct from document loading condition |
| Select Java bean by profile | `@Profile` | Based on profile, not directly on cloud platform |

## 16. Frequently asked questions

**Do I need Spring Cloud Kubernetes to use `on-cloud-platform=kubernetes`?**

No, Config Data activation by `CloudPlatform` is part of Spring Boot. Spring Cloud Kubernetes is an additional set of integrations for interacting with Kubernetes, not a prerequisite just to use this property.

**Can `spring.config.activate.on-cloud-platform` be used inside `application-prod.yml`?**

`application-prod.yml` is only considered when the `prod` profile matches. When `on-cloud-platform=kubernetes` is also declared inside it, the corresponding document is loaded only when the cloud platform condition also holds. However, placing dual conditions inside a profile-specific file can be harder to read than an explicit document in the base file; choose the structure that best reflects intent.

**Can a document have multiple conditions?**

You can combine `on-cloud-platform` with `on-profile`. The document will need to satisfy both conditions. `on-profile` supports expression syntax such as `prod | staging`.

**When running Docker locally, is it automatically treated as Kubernetes?**

No. A Docker container does not equal Kubernetes. Detection depends on the platform signals Spring Boot actually receives, or an explicit `spring.main.cloud-platform` override.

**What if Kubernetes is misdetected?**

Check environment variables and override settings. Where appropriate, you can specify `spring.main.cloud-platform=none` or a valid platform supported by your Spring Boot version. Forcing a platform must be managed explicitly in the deployment setup because it can affect multiple conditions and auto-configurations.

**Can `on-cloud-platform` be used to control business features?**

It can condition infrastructure-related properties, but should not be used as a general business feature flag mechanism. Runtime platform and feature-rollout policy are two separate decisions.

## 17. Takeaways to apply

1. `spring.config.activate.on-cloud-platform` **activates a Config Data document** when Spring Boot determines `CloudPlatform` matches.
2. Use `---` in YAML, and `#---` or `!---` in properties to organize multiple documents.
3. The base document supplies defaults; conditional documents can override relevant keys when activated.
4. You can combine `on-cloud-platform` and `on-profile`; both conditions must be true together.
5. `spring.profiles.active` does not mean cloud platform; `application-kubernetes.yml` is not automatically activated simply by running on Kubernetes.
6. `spring.main.cloud-platform` lets you override auto-detection, useful for diagnostics or testing configuration.
7. `spring.config.import` inside a conditional document can import `configtree:` only when that document is activated.
8. Activation does not establish absolute precedence; Config Data locations, document order, profiles, and other property sources must still be evaluated.
9. Cloud detection is for selecting configuration, not an authentication or secret-management measure.
10. Config Data condition changes are normally applied at startup; restart when the runtime environment changes.

### References

- [Spring Boot Reference — Externalized Configuration, Multi-Document Files and Activation Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot API — `CloudPlatform`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/cloud/CloudPlatform.html)
- [Spring Boot Reference — Deploying to Kubernetes](https://docs.spring.io/spring-boot/how-to/deployment/cloud.html)
- [Spring Boot Reference — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
