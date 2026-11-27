# Remote Configuration Source Unexpectedly Overrides Local Values

When a Spring Cloud application retrieves configuration from Config Server, Vault, Consul, or Kubernetes, the same property can appear in multiple places: `application.yml` packaged in the JAR, configuration files placed alongside the JAR, environment variables, JVM system properties, command line, and remote property sources. The value a bean receives depends on the precedence order of these sources and how the application loads them.

A common scenario is a developer setting `catalog.timeout=2s` in local configuration while the application still uses `5s` from Config Server. This can be the intended behavior under Spring Cloud's legacy bootstrap mechanism, or occur because a Config Data import is placed at higher priority than the document declaring the import. The value could also come from a profile, an external file outside the JAR, an environment variable, or a shared setting on the Config Server side.

This lesson belongs to the **Troubleshooting** chapter of the `SPRING_CLOUD_CORE` module. It guides you through pinpointing the exact winning property source, distinguishing Config Data from legacy bootstrap, understanding the `allowOverride`, `overrideNone`, and `overrideSystemProperties` flags, checking server-side overrides, and resolving conflicts among multiple configuration sources.

## 1. Identifying Symptoms and Scope of the Issue

A precedence issue typically exhibits symptoms such as:

- The value in `application.yml` differs from the value injected into a bean.
- Changing an environment variable still leaves the application receiving the remote value.
- The same artifact produces different results locally and in production.
- Only the `prod` or `staging` profile gets overridden.
- Config Server returns the expected file, yet the client picks a value from another property source.
- After a refresh, a bean still holds the old value or receives an unexpected value.
- A property is defined in `application.yml`, `bootstrap.yml`, a ConfigMap, and Config Server with different values.

Before making changes, determine three pieces of information:

1. **Property key:** the exact name read by the bean, e.g., `catalog.timeout`.
2. **Effective value:** the actual value in `Environment` or the bean.
3. **Winning property source:** the highest-priority source and location supplying that key.

Do not start by adding the same key to more files. That increases the number of conflicting sources and makes the next diagnosis harder.

## 2. How Does Spring Boot Decide Which Property Wins?

Spring Boot aggregates configuration into `PropertySource` entries inside `Environment`. When multiple sources contain the same key, the higher-priority source is used to resolve the value.

In modern Spring Boot's default order, common sources are evaluated from lowest to highest as follows:

| Order | Property source | Example |
| --- | --- | --- |
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` | File loaded from a configuration class |
| 3 | Config Data | `application.yml`, profile files, imported files |
| 4 | Random value source | `random.*` |
| 5 | OS environment variables | `CATALOG_TIMEOUT=3s` |
| 6 | Java system properties | `-Dcatalog.timeout=4s` |
| 7 | JNDI | `java:comp/env/...` |
| 8 | ServletContext init parameters | Servlet context configuration parameters |
| 9 | ServletConfig init parameters | Servlet parameters |
| 10 | `SPRING_APPLICATION_JSON` | Inline JSON in environment or system property |
| 11 | Command line arguments | `--catalog.timeout=6s` |
| 12 onward | Test property sources and Devtools | `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource`, Devtools |

This table describes Spring Boot's general order. Spring Cloud may add remote property sources through its own bootstrap mechanism; therefore, determine which configuration loading mechanism the application uses before applying this table.

For example, if the same key appears in a local file, an environment variable, and the command line:

```yaml
# application.yml
catalog:
  timeout: 2s
```

```text
CATALOG_TIMEOUT=3s
```

```bash
java -jar catalog.jar --catalog.timeout=6s
```

The selected value is `6s` because the command line has higher priority than environment variables and configuration files. Seeing `2s` in the file does not prove the bean will receive `2s`.

### 2.1. Config Data Has Its Own Ordering Within the Configuration Group

Within the Config Data group, files packaged inside the JAR and files outside the JAR have different precedence. Profile-specific files are also evaluated in corresponding order.

For instance, an `application-prod.yml` outside the JAR can override a value in `application.yml` packaged inside the JAR when the `prod` profile is active. Locations declared later in `spring.config.location` or `spring.config.additional-location` can override locations processed earlier.

Spring Boot also specifies that configuration loaded via `spring.config.import` has higher priority than the document that declared the import. If there are multiple imports, imports processed later can override earlier ones.

### 2.2. `spring.config.location` and `spring.config.additional-location`

These two properties serve different purposes:

- `spring.config.location` replaces the default locations to search.
- `spring.config.additional-location` appends locations in addition to the default locations.

Example:

```text
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/catalog/
```

Configuration files in `/etc/catalog/` can override values from default locations. If the same key is unintentionally placed in this file, a developer may think Config Server overrode local config when the value actually comes from the external file outside the JAR.

Both properties are read very early during startup. Supply them via environment variable, system property, or command line rather than inside a file whose discovery they control.

## 3. Distinguishing Config Data Import from Legacy Bootstrap

This is the most important step when diagnosing Spring Cloud Config. The two mechanisms have different loading rules and precedence controls.

| Mechanism | How to Enable | Precedence Characteristics |
| --- | --- | --- |
| Config Data import | `spring.config.import=configserver:...` | Remote data is loaded as Config Data; imports have higher priority than the document declaring the import |
| Legacy bootstrap | `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true` | Bootstrap context loads remote property sources with high priority; by default, local config does not override remote sources |

Do not apply legacy bootstrap control flags to Config Data imports and assume they change import ordering. Read the documentation for the exact mechanism and version in use.

### 3.1. Config Data Import

Example:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "optional:configserver:http://config-server:8888"
```

Values from Config Server are loaded via Config Data. Because imported data has higher priority than the document declaring the import, a matching property in that same document can be overridden by the remote value.

If you want local configuration to have higher priority than remote Config Server, you can use a dedicated local import declared after Config Server:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
      - "optional:file:./config/local-overrides.yml"
```

`local-overrides.yml`:

```yaml
catalog:
  timeout: 2s
```

In this example, the local import is processed after the Config Server import, so values in the local override file take higher priority than the same keys from Config Server. Verify the import order in Config Data logs and test with the exact Spring Boot/Config Client version running.

If you want overrides per deployment environment, you can use environment variables, JVM system properties, or command-line arguments since those sources have higher priority than Config Data.

### 3.2. Legacy Bootstrap

Legacy bootstrap creates a bootstrap context as the parent of the application context. Remote property sources are typically added with higher priority than local application configuration.

Enable bootstrap via starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
</dependency>
```

Or enable via environment/system property:

```text
SPRING_CLOUD_BOOTSTRAP_ENABLED=true
```

When bootstrap is enabled, the application can use `bootstrap.yml` to configure Config Server connection details:

```yaml
spring:
  application:
    name: catalog-service
  cloud:
    config:
      uri: http://config-server:8888
```

In this model, if Config Server returns `catalog.timeout=5s` and local `application.yml` sets `catalog.timeout=2s`, the remote property source wins by default. To change that behavior, the remote property source must grant override permission to the client.

### 3.3. Do Not Arbitrarily Enable Both Mechanisms Together

Do not simultaneously use `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true` alongside `spring.config.import` to load the same Config Server or the same group of property sources. The two mechanisms have different lifecycles and ordering; duplicate loading makes it difficult to determine which source wins.

Choose one consistent mechanism, document it clearly in your runbook, and test the exact property source order. If migrating from legacy bootstrap to Config Data, treat it as a migration step requiring testing—not merely deleting `bootstrap.yml` and changing a single import line.

## 4. Legacy Bootstrap Override Control Flags

Spring Cloud Context provides three properties to control whether local sources can override remote sources:

- `spring.cloud.config.allowOverride`
- `spring.cloud.config.overrideNone`
- `spring.cloud.config.overrideSystemProperties`

**Most common pitfall:** `spring.cloud.config.allowOverride=true` must be placed in the remote configuration supplied by Config Server. Putting it in local `application.yml` does not grant permission to override remote property sources.

### 4.1. `allowOverride=true`

This property allows the remote property source to yield part of its priority so that local property sources can override it.

Example placed in the configuration repository served by Config Server:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
```

Do not put this property only in a local file and expect Config Server to change precedence. Config Client must receive this permission from the remote property source.

### 4.2. `overrideNone=true`

When `allowOverride=true` and `overrideNone=true`, local property sources can override remote property sources.

Example:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
      overrideNone: true

catalog:
  timeout: 5s
```

With legacy bootstrap, local `application.yml`, profile-specific configs, environment variables, system properties, and command-line arguments can supply replacement values in their respective order.

This is the right choice when remote configuration acts as shared defaults and each deployment is allowed to set its own values.

### 4.3. `overrideSystemProperties=false`

When `allowOverride=true` and `overrideSystemProperties=false`, only system properties, command-line arguments, and environment variables are allowed to override remote settings; local config files cannot be used to override remote values.

Example:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
      overrideSystemProperties: false
      overrideNone: false
```

Expected result:

- Local `application.yml` does not replace the remote value.
- Environment variables can replace the remote value.
- JVM system properties can replace the remote value.
- Command-line arguments can replace the remote value.

This approach is helpful when the platform team wants Config Server to manage application settings while still allowing deployments to inject certain runtime values via environment or JVM flags.

### 4.4. Quick Selection Table

| Goal with legacy bootstrap | Configuration in remote repository |
| --- | --- |
| Remote config beats local sources by default | Omit `allowOverride` or set to `false` |
| Allow all local sources to override remote | `allowOverride=true`, `overrideNone=true` |
| Allow only env/system/command line to override; disallow local files | `allowOverride=true`, `overrideSystemProperties=false` |
| Try to change behavior by placing flags only in local `application.yml` | Has no effect granting remote override permission |

These flags do not replace Spring Boot's precedence rules. Once the remote source allows overrides, local sources are still ordered according to their own precedence.

## 5. Distinguishing Server-Side Overrides from Regular Properties

Spring Cloud Config Server provides `spring.cloud.config.server.overrides` so operators can supply a shared set of properties to all Config Clients.

Example configuration on the Config Server side:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          company:
            support-url: https://support.example.com
          platform:
            request-timeout: 3s
```

These properties are included in the configuration response sent to clients. They are useful for shared values, but are not a strict security boundary: the client is still an application running in an operator-managed environment and may have other ways to load or use properties.

### 5.1. `overrideNone` with Server-Side Overrides

Config Server documentation describes setting `spring.cloud.config.overrideNone=true` in the remote repository as a way to make server overrides behave more like defaults, allowing applications to supply their own values via environment or system properties.

If you want to change how server-side overrides behave, verify clearly:
- Whether the property lives under `spring.cloud.config.server.overrides` or inside an application config file in the repository.
- Whether the client uses Config Data or legacy bootstrap.
- Which versions Config Server and Config Client are running.
- Which property source the overriding value actually comes from.

Do not confuse `spring.cloud.config.server.overrides` (operator setting on Config Server) with `spring.cloud.config.allowOverride` (client-side override permission of the remote property source).

### 5.2. Using Placeholders When Local Values Are Needed as Input

Another approach is having remote config define a placeholder expression so the client resolves a local value.

Example in server-side override configuration:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          catalog:
            display-name: \${local.catalog.display-name:Default Catalog}
```

If you want the placeholder resolved on the client side, escape it according to the syntax specified by Spring Cloud Config. Then `local.catalog.display-name` can come from a local property source.

This approach is useful when remote config needs to define a shared structure while each deployment supplies part of the value. Test the final result after Config Server serializes the property source and Config Client resolves the placeholder; do not assume seeing the placeholder string in the response is sufficient.

## 6. Order of Property Sources Returned by Config Server

Config Server typically combines shared configuration, profile-specific configuration, application-specific configuration, and shared sources.

With default file-based configuration, a request takes the form:

```text
GET /{application}/{profile}/{label}
```

The three parameters are usually determined from the client:

| Parameter | Default Value / Source | Example |
| --- | --- | --- |
| `application` | `spring.application.name` | `catalog-service` |
| `profile` | Client's active profiles | `prod` |
| `label` | Repository default label | `main`, branch, or commit ID |

Config Server serves `application.yml` as baseline configuration for applications. Application-specific and profile-specific configurations are added in repository order.

For example, when a client uses `spring.application.name=catalog-service` and profile `prod`, sources may be returned in this order:

1. `application.yml`
2. `application-prod.yml`
3. `catalog-service.yml`
4. `catalog-service-prod.yml`

Property sources appearing later can win over earlier sources in the response. If `spring.cloud.config.name` is used with a comma-separated list of names, name order also affects precedence: later names can override earlier ones.

### 6.1. Checking for Wrong Application Name

A common mistake is Config Client sending the wrong application name. For example, the service sets:

```yaml
spring:
  application:
    name: catalog
```

while the repository contains `catalog-service-prod.yml`. The client may receive shared configuration or configuration for a different name than expected.

Check `spring.application.name`, `spring.cloud.config.name`, profile, and label. Do not add local files to compensate for the client requesting the wrong configuration from the server.

### 6.2. Checking Active Profiles

If `prod` is not activated, Config Server may return default configuration instead of `prod`. If multiple profiles are activated, profile order also affects how configurations merge.

Check sources supplying `spring.profiles.active`:
- Environment variable `SPRING_PROFILES_ACTIVE`.
- JVM argument `-Dspring.profiles.active=...`.
- Command line `--spring.profiles.active=...`.
- Local and remote configs capable of activating additional profiles.
- Profile groups or profile includes if used by the application.

With Config Data, the client may call Config Server multiple times while resolving profiles: first with the `default` profile, then with activated profiles. Multiple requests during startup are not necessarily an error or retry.

### 6.3. Checking Label and Repository Version

`spring.cloud.config.label` can point to a branch, tag, or commit ID. An old label can cause the client to receive values that were already changed on the current branch.

Record the exact label requested by the client. In environments requiring rollback, use reproducible, auditable labels rather than implicitly depending on a continuously moving branch.

## 7. Multiple Remote Sources Coexisting

An application may receive properties from Config Server, Kubernetes ConfigMap/Secret, Vault, Consul, or a custom `PropertySourceLocator`.

Do not assume every remote source shares the same order. The loading mechanism and provider determine precedence.

### 7.1. Multiple `spring.config.import` Entries

Example:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
      - "optional:kubernetes:"
```

According to Config Data ordering, imports processed later have higher priority than earlier imports. In this example, the Kubernetes property source can override Config Server for the same key.

If you reverse the order, Config Server can override the Kubernetes source.

This is useful when intentional: Config Server holds shared settings while the ConfigMap holds deployment-specific values. However, if conventions are undocumented, an operator may edit a ConfigMap without realizing it overrides Config Server.

### 7.2. Legacy Bootstrap with Multiple PropertySourceLocators

When using legacy bootstrap, `PropertySourceLocator` instances can run inside the bootstrap context. Providers may use the same order value; if so, do not rely on incidental ordering between locators.

For example, Spring Cloud Kubernetes notes that the ConfigMap locator and Config Server locator share the same order in certain legacy setups. If deterministic ordering between Kubernetes and Config Server is needed, Spring Cloud Kubernetes documentation recommends using `spring.config.import` instead of legacy bootstrap.

Do not mix bootstrap property loading and Config Data import in the same application when that combination is unsupported.

### 7.3. Custom PropertySourceLocator

If your organization has a custom locator, inspect:
- The `PropertySource` name returned by the locator.
- `@Order` or order metadata.
- The context where the locator is created.
- When the locator runs.
- Conditions based on application name/profile.
- Whether the property source collides in name with another source.

A custom locator can insert keys ahead of remote Config Server or behind local config without developers seeing them in YAML files.

## 8. Step-by-Step Diagnostic Procedure

When you discover a local value is overridden by a remote source, follow these steps in order.

### Step 1 — Lock Down the Key and Effective Value

Record the property key, expected value, actual value, and the bean using the property. If using `@ConfigurationProperties`, inspect the bound object; if using `@Value`, verify the exact placeholder.

Do not treat a value shown in a single isolated file as proof.

### Step 2 — Identify the Configuration Loading Mechanism

Check build and startup configuration to see whether the application uses:
- `spring.config.import=configserver:...`.
- `spring-cloud-starter-bootstrap`.
- `spring.cloud.bootstrap.enabled=true`.
- A custom `PropertySourceLocator`.
- Multiple remote sources such as Config Server and Kubernetes.

Also inspect environment variables and JVM arguments because they can enable legacy bootstrap or change import locations.

### Step 3 — Check application/profile/label

Record:
- `spring.application.name`.
- `spring.cloud.config.name`.
- Active profiles.
- `spring.cloud.config.profile` if present.
- `spring.cloud.config.label`.
- Config Server URI or discovery service ID.

Confirm the request the client sends to Config Server points to the right configuration.

### Step 4 — List All Sources Containing the Duplicate Key

Search for the key in:
- `application.yml` packaged in the JAR.
- `application-{profile}.yml`.
- Configuration files outside the JAR.
- `bootstrap.yml` if legacy bootstrap is enabled.
- Config Server repository.
- `spring.cloud.config.server.overrides`.
- Kubernetes ConfigMap/Secret.
- Environment variables.
- JVM system properties.
- Command line.
- Custom property sources.

Record the value and source of each occurrence.

### Step 5 — Inspect PropertySource Order at Runtime

Use Actuator `env` and `configprops` in a secured environment to identify the property source and bound value.

Example endpoints:

```text
/actuator/env/catalog.timeout
/actuator/configprops
```

The `env` endpoint shows the property source supplying the property and origin details when supported. The `configprops` endpoint inspects values bound into `@ConfigurationProperties`.

Expose these endpoints only in appropriate environments and protect them with authentication/authorization. Do not share outputs containing passwords, tokens, connection strings, or secrets.

### Step 6 — Enable Config Data Loading Logs When Needed

If using Config Data, you can increase logging:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

This log helps observe which locations and config documents are processed. Use in test/staging or a time-boxed investigation session; lower the log level after investigating.

For legacy bootstrap, check logs from Spring Cloud bootstrap/Config Client and property source locators according to the running version.

### Step 7 — Decide the Desired Override Policy

Choose a clear policy:

- Remote config is authoritative.
- Remote config provides defaults; local files can override.
- Remote config provides defaults; only deployment environment/system properties can override.
- Certain keys are locally overridden; remaining keys remain remotely managed.

Do not apply a global flag if only a few keys need different behavior. Separate property namespaces or design profile-based configuration to reduce conflict scope.

### Step 8 — Fix in the Right Place and Test

- For legacy bootstrap, adjust `allowOverride`/`overrideNone`/`overrideSystemProperties` in the remote repository.
- For Config Data, adjust import order or use a higher-precedence source.
- For server-side overrides, fix `spring.cloud.config.server.overrides` if the shared value is misconfigured.
- For wrong profile/name/label, fix the identifier requested by the client.
- For a custom locator, fix its order or loading condition.

Restart the test context or process according to the mechanism in use, then verify the winning source and bean value.

## 9. Practical Example: `catalog.timeout` Stays at 5 Seconds

Suppose the local file has:

```yaml
catalog:
  timeout: 2s
```

Config Server returns:

```yaml
catalog:
  timeout: 5s
```

### Case A — Client Uses Legacy Bootstrap

If the remote property source has high priority and does not grant override permission, the application receives `5s`.

If you want all local property sources to be able to override, set in the remote repository:

```yaml
spring:
  cloud:
    config:
      allowOverride: true
      overrideNone: true

catalog:
  timeout: 5s
```

After restarting the client, local `application.yml` can supply `2s`. Check `/actuator/env/catalog.timeout` again to confirm the winning source.

### Case B — Client Uses Config Data Import

Configuration:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"

catalog:
  timeout: 2s
```

Imported Config Server data has higher priority than the document declaring the import, so `5s` can win.

If you want a dedicated override file to win, declare it after Config Server:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
      - "optional:file:./config/local-overrides.yml"
```

And put `catalog.timeout: 2s` in `local-overrides.yml`. Check Config Data logs and runtime Environment to confirm.

### Case C — Environment Variable Is Winning

If the deployment defines:

```text
CATALOG_TIMEOUT=7s
```

then with Config Data import, the environment variable can beat both the remote `5s` value and local `2s` file value.

If operators expect Config Server to be the sole source, inspect manifests/Helm values or the deployment environment to locate this variable. Do not fix only the Config Server repository because the environment variable can still override it.

## 10. Refresh Does Not Automatically Fix Precedence Errors

Spring Cloud Context provides `EnvironmentChangeEvent`, `@RefreshScope`, and bean refresh mechanisms. They help an application pick up configuration changes after a property source is updated.

However, refresh does not magically give a local property source higher priority than a remote source. If the remote source still wins under precedence rules, refresh will keep feeding the remote value into the bean.

Distinguish three operations:

1. **Fetch/update:** did the property source receive the updated value from the remote repository?
2. **Precedence:** when the same key exists in multiple sources, which source wins?
3. **Rebinding/refresh:** was the bean rebound or recreated from the effective value?

Check each layer separately. If the property source is right yet the bean is stale, investigate binding or refresh scope. If the effective value is wrong, fix precedence first.

## 11. Common Pitfalls During Investigation

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| `allowOverride=true` yet local file still does not win | Flag was set only locally, not in remote repository | Check whether remote property source grants permission |
| Set `overrideNone=true` yet no effect | Client does not use legacy bootstrap or remote source did not return the flag | Determine Config Data vs bootstrap |
| Only env overrides, local YAML does not | `overrideSystemProperties=false` | Check legacy bootstrap policy |
| Config Server returns unexpected values | Wrong application name/profile/label or server override | Check request URL and response |
| `application.yml` in JAR is right yet runtime differs | External file, profile, or import has higher precedence | Check Config Data trace and env endpoint |
| Local override file does not win | Import placed before Config Server or file not loaded | Check order of `spring.config.import` |
| Some properties win, others do not | Duplicate key in another source or different binding namespace | Inspect each key in `env`/`configprops` |
| Value remains stale after refresh | Remote source not updated or bean not refreshed/rebound | Separate fetch, precedence, and refresh |
| Fails only in production | Environment variable, command line, profile, ConfigMap, or secret differs from local | Inspect deployment manifest |
| ConfigMap and Config Server alternate winning | Indeterminate legacy locator order or overlapping source order | Use Config Data import with explicit order |
| Tests produce different results from runtime | Test property sources have higher precedence than production sources | Check `@SpringBootTest`, `@DynamicPropertySource`, and `@TestPropertySource` |

## 12. Designing Configuration Policy to Prevent Recurrence

A multi-service system should have clear conventions for ownership and precedence.

Example division:

| Configuration Type | Recommended Source | Rationale |
| --- | --- | --- |
| Application-wide defaults | Config Server shared/application config | Shared and versioned |
| Service-specific settings | Config Server application config | Clear per-service ownership |
| Environment-specific settings | Profile-specific remote config or deployment config per policy | Distinguishes dev/staging/prod |
| Secrets and credentials | Secret manager/Kubernetes Secret | Separate lifecycle and access control |
| Values changed at deploy time | Environment variables or system properties if policy permits | Avoids rebuilding artifacts |
| Temporary debug parameters | Command line or test properties | Clear scope and lifetime |

Do not store secrets in `application.yml` or plain-text config repositories if your organization has a secret manager. Do not reuse the same property key for different purposes merely for convenience.

### 12.1. Assign One Owner per Key

For each critical property, document:
- Owning team.
- Authoritative source.
- Whether deployment-level overrides are allowed.
- Who has permission to change it.
- Whether refresh or restart is required.
- How to roll back the value.

For example, `spring.datasource.url` might be managed per environment by the platform team; `catalog.page-size` might be managed in Config Server by the service team; `logging.level.*` might allow temporary operator overrides.

### 12.2. Use Namespaces to Reduce Conflicts

Separate properties by function:

```yaml
catalog:
  business:
    default-page-size: 25
  client:
    timeout: 2s
  feature:
    new-search-enabled: false
```

Avoid overly generic keys such as `timeout`, `enabled`, or `url` across modules because they easily collide and cause confusion when viewing `/env`.

### 12.3. Record Winning Sources and Effective Values

Dashboards or startup diagnostics can log:
- Application name.
- Active profiles.
- Config Server label/version.
- Build version.
- Critical property keys.
- Winning property source name.
- Masked value if sensitive data is involved.

Do not log the entire `Environment`. Log an allowlist of necessary properties and mask secrets.

## 13. Deterministic Precedence Testing

Write tests for override policies rather than merely checking that the application starts.

Example test with Spring Boot Config Data:

```java
@SpringBootTest(properties = {
    "catalog.timeout=9s"
})
class CatalogConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void testPropertySourceOverridesConfigData() {
        assertThat(environment.getProperty("catalog.timeout"))
            .isEqualTo("9s");
    }
}
```

This example checks that a test property source can override Config Data. It does not replace an integration test with a real Config Server.

Tests to include:

1. Local file and remote Config Server both define the same key.
2. Environment variable overrides remote Config Data.
3. Command line/system properties override in the expected order.
4. Legacy bootstrap without `allowOverride` granted.
5. Legacy bootstrap with `allowOverride=true`, `overrideNone=true`.
6. Legacy bootstrap with `overrideSystemProperties=false`.
7. Server-side overrides hold expected values.
8. Different profiles and labels return the expected property sources.
9. Two or more `spring.config.import` entries follow deterministic ordering.
10. Refresh updates beans from the effective value, not from a lower-priority source.

For tests requiring Config Server, use a test repository or a mock server returning fixed responses. Never let tests depend on a production Config Server.

## 14. Troubleshooting Checklist

- [ ] Identified property key and effective value.
- [ ] Identified whether the bean reads the property via `@Value` or `@ConfigurationProperties`.
- [ ] Identified whether the client uses Config Data import or legacy bootstrap.
- [ ] Checked `spring.application.name`, profile, and label.
- [ ] Located every place defining the same key.
- [ ] Checked external config locations and profile-specific files.
- [ ] Checked `spring.config.import` ordering if using Config Data.
- [ ] Checked `allowOverride` in the remote repository if using legacy bootstrap.
- [ ] Checked `overrideNone` and `overrideSystemProperties` against policy.
- [ ] Checked Config Server `server.overrides`.
- [ ] Checked ConfigMap, Secret, Vault, Consul, and custom property sources if present.
- [ ] Inspected `/actuator/env` and `/actuator/configprops` in a secured environment.
- [ ] Verified winning property source and bean value after startup/refresh.
- [ ] Added tests to prevent precedence regressions.
- [ ] Documented owner and authoritative source of the property.

### Self-Check Questions

1. Why might local `application.yml` fail to beat remote Config Server?
2. How does Spring Boot determine the effective value?
3. How does Config Data import differ from legacy bootstrap in precedence?
4. Why must `spring.cloud.config.allowOverride=true` reside in the remote repository?
5. What does `overrideNone=true` change?
6. Which sources does `overrideSystemProperties=false` permit to override remote values?
7. How does `spring.cloud.config.server.overrides` differ from `allowOverride`?
8. Why can multiple entries in `spring.config.import` produce different precedence?
9. How do you verify the application name/profile/label the client is requesting?
10. Why does refresh not automatically fix a property source precedence error?
11. When should Actuator `env` and `configprops` be used?
12. Why should you not enable both legacy bootstrap and Config Data import for the same source?

**Suggested answers:** (1) Because remote property sources or imported Config Data can have higher priority; (2) By the order of PropertySources in Environment; (3) Config Data follows Spring Boot's import rules, whereas legacy bootstrap adds a high-priority remote source and disallows local overrides by default; (4) The client must receive permission from the remote property source—a local flag does not grant permission; (5) Allows all local property sources to override remote sources in legacy bootstrap; (6) Environment variables, JVM system properties, and command line, excluding local config files; (7) One is an operator-supplied map of properties pushed to clients, while the other is override permission on the remote property source; (8) Later imports have higher priority than earlier imports; (9) Check `spring.application.name`, `spring.cloud.config.name/profile/label`, active profiles, and Config Server requests; (10) Refresh only updates/rebinds according to the effective value without changing source ordering; (11) When needing to pinpoint the winning source and effective value in a secured environment; (12) Because their lifecycles and ordering differ, which can cause duplicate loading and unpredictable results.

## 15. Key Principles to Remember

- Always identify the configuration loading mechanism before changing precedence.
- Config Data import and legacy bootstrap follow different rules; do not mix up their control flags.
- In legacy bootstrap, remote property sources have high priority by default and are not overridden by local config.
- `spring.cloud.config.allowOverride=true` must be supplied by the remote repository.
- `overrideNone=true` allows local property sources to override remote ones in legacy bootstrap.
- `overrideSystemProperties=false` restricts overrides to environment variables, system properties, and command line.
- In Config Data, imports have higher priority than the document declaring the import; later imports can beat earlier ones.
- Check application name, profile, label, and server-side overrides before modifying local files.
- Multiple remote sources may have provider-dependent ordering; use Config Data imports when deterministic order is needed.
- Use Actuator `env`/`configprops` and Config Data logs to find the winning source.
- Refresh is no substitute for fixing precedence; inspect fetching, ordering, and bean binding separately.
- Document an owner and authoritative source for every critical property.

Once the winning property source and desired override policy are identified, the fix becomes clear: update the right source, maintain consistent ordering, and add tests to protect the behavior. This keeps remote configuration effective for centralized governance while allowing local or environment-specific values to operate within their intended permissions.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Context — Overriding Remote Properties](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
- [Spring Cloud Kubernetes — PropertySource Precedence](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html)
