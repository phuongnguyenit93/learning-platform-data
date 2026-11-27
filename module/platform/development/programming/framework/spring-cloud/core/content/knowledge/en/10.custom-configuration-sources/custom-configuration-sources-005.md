# Using Input Environment Selectors for Application and Profile

Spring Cloud Config Server can retrieve configuration from Git, the filesystem, JDBC, Vault, or a custom source built by the development team. For a custom source, the server needs to know **which application, which profiles, and which configuration version** are being requested before querying the data store. The `EnvironmentRepository` contract provides these exact three pieces of information to the `findOne` method.

This lesson belongs to the **Custom Configuration Sources** chapter of the **SPRING_CLOUD_CORE** module. We will trace a request from Config Client to Config Server, use `application`, `profile`, and `label` to select data, construct the returned `Environment` object, and examine how multiple profiles combine.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of `EnvironmentRepository` in Spring Cloud Config Server.
- Distinguish `org.springframework.core.env.Environment` from `org.springframework.cloud.config.environment.Environment`.
- Identify where `application`, `profile`, and `label` come from in a configuration request.
- Write a custom repository implementing `findOne(application, profile, label)`.
- Select the right configuration by application and multiple profiles while keeping profile precedence consistent.
- Return an `Environment` with the appropriate name, profiles, label, and `PropertySource` entries.
- Register the repository as a Spring bean, control order in a composite setup, and verify results over HTTP.
- Protect configuration lookup against invalid application/profile/label values and prevent arbitrary data queries.

## 2. Environment Has Two Meanings in Spring Cloud Config

The name `Environment` appears in two different packages. Distinguish them clearly so you do not confuse the request/runtime environment with the response model.

| Type | Package | Role |
| --- | --- | --- |
| Spring Framework `Environment` | `org.springframework.core.env.Environment` | Abstraction of the running Spring application, providing active/default profiles and reading properties from `PropertySource` instances. |
| Spring Cloud Config `Environment` | `org.springframework.cloud.config.environment.Environment` | Data model returned by Config Server, containing application name, profile list, label, and property sources. |

In the `EnvironmentRepository` contract, **the direct input is not an `Environment` object**. The inputs are three strings:

~~~java
Environment findOne(String application, String profile, String label);
~~~

The repository uses those parameters to select data, then creates and returns `org.springframework.cloud.config.environment.Environment`. Config Server's own `org.springframework.core.env.Environment` is a separate concept, typically injected to read the server's runtime configuration.

## 3. Three Input Parameters Selecting Configuration

Config Server serves configuration via an endpoint of the form:

~~~text
/{application}/{profile}/{label}
~~~

Each of the three components has a distinct meaning:

| Parameter | Meaning | Typical client-side value |
| --- | --- | --- |
| `application` | Name of the application requesting configuration | `spring.application.name` |
| `profile` | One or more activated profiles | `spring.profiles.active`, typically a comma-separated list |
| `label` | Version label of the configuration set on the server | Git branch, tag, commit, or backend-specific version |

Client example:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: dev,mysql
  cloud:
    config:
      label: release-2026.11
~~~

Config Client defaults to `spring.application.name` as application, the active profiles as profile, and a default label determined by client/server configuration. These values can be overridden via `spring.cloud.config.name`, `spring.cloud.config.profile`, and `spring.cloud.config.label`.

With the example above, the repository receives a request equivalent to:

~~~text
application = order-service
profile     = dev,mysql
label       = release-2026.11
~~~

### 3.1. Application Selects Configuration Scope

`application` usually corresponds to the service name. The repository uses it to select the namespace, tenant, folder, table, or data store dedicated to that application.

Examples:

| Application | Configuration space |
| --- | --- |
| `order-service` | Order processing timeout, order database connection, checkout feature flags |
| `catalog-service` | Catalog cache, search limits, search index connection |
| `payment-service` | Payment gateway timeout, retry policy, and reconciliation settings |

Do not treat the `application` sent in the request as an already-authenticated identity. Config Server must verify whether the caller is authorized to read that application's configuration. Otherwise, a caller could change the application name and accidentally or maliciously read another service's configuration.

### 3.2. Profile Selects Environment Variants

A profile is an environment name or configuration group such as `dev`, `test`, `staging`, `prod`, `mysql`, or `redis`. A single request can contain multiple profiles:

~~~text
/order-service/dev,mysql/release-2026.11
~~~

Spring Cloud Config applies profile rules similar to Spring Boot: active profiles take precedence over default configuration; when multiple profiles are present, **a later profile can override values from an earlier profile**. For example, if both `dev` and `mysql` declare `spring.datasource.url`, the value from `mysql` wins under the corresponding merge rules.

A custom repository must preserve the exact profile order supplied by the request when merging data. Sorting profiles alphabetically or using an unordered structure can yield results different from what Config Client expects.

### 3.3. Label Selects the Configuration Version

`label` is a server-side version label. With a Git backend, the label is usually a branch, tag, or commit ID. With another data source, the label can be a version code, revision, or published snapshot.

Do not confuse `label` with `profile`:

- `prod` answers **which environment the configuration is for**.
- `release-2026.11` answers **which version of the configuration set to use**.

If no label is passed, the repository must apply a well-defined default label. Do not silently use different defaults across Config Server instances.

## 4. Request Flow from Config Client to EnvironmentRepository

~~~mermaid
sequenceDiagram
    participant C as Config Client
    participant H as Config Server HTTP endpoint
    participant R as EnvironmentRepository
    participant S as Custom configuration store
    C->>H: GET /order-service/dev,mysql/release-2026.11
    H->>R: findOne(application, profile, label)
    R->>R: Validate application/profile/label
    R->>S: Load data for app + label + profiles
    S-->>R: Default and profile-specific properties
    R->>R: Merge profiles in requested order
    R-->>H: Config Environment + PropertySources
    H-->>C: JSON Environment response
~~~

These steps can be extended with authentication, authorization, caching, secret decryption, auditing, or composite repositories. Still, the core contract remains: **accept the configuration selectors, read the data store, and return an Environment containing PropertySources**.

Config Server does not dictate a specific database for repositories. A repository can read from SQL tables, an internal REST API, object storage, a secret manager, or a custom-built configuration store.

## 5. Structure of the Returned Environment

`org.springframework.cloud.config.environment.Environment` is the response model. It contains:

- `name`: the requested application.
- `profiles`: the list of processed profiles.
- `label`: the configuration version label.
- `propertySources`: list of property sources, each with a name and key/value map.
- `version` and `state`: optional metadata provided by the repository/backend.

Abbreviated JSON example:

~~~json
{
  "name": "order-service",
  "profiles": ["dev", "mysql"],
  "label": "release-2026.11",
  "propertySources": [
    {
      "name": "custom:order-service:dev,mysql:release-2026.11",
      "source": {
        "order.timeout": "5s",
        "order.checkout.enabled": "true",
        "spring.datasource.url": "jdbc:postgresql://db-dev/orders"
      }
    }
  ]
}
~~~

In this example, the repository merged values into a single `PropertySource`. Another implementation may return multiple separate `PropertySource` entries to preserve provenance and precedence. When returning multiple sources, place higher-priority sources in the proper position per Spring Cloud Config's contract.

## 6. Writing a Custom EnvironmentRepository

Suppose an organization stores configuration in an internal catalog with the logical layout:

~~~text
application
  └── label
      ├── default
      ├── dev
      ├── mysql
      └── prod
~~~

Each profile holds a property map. The repository will:

1. Validate `application` and `label`.
2. Split the profile string into a list preserving request order.
3. Load the `default` configuration first.
4. Load each active profile from left to right; later profiles overwrite overlapping keys from earlier profiles.
5. Create a Config `Environment` and add the `PropertySource`.

### 6.1. Catalog Access Interface

To separate application/profile selection from storage technology, define a small abstraction:

~~~java
package com.example.configserver.repository;

import java.util.Map;

public interface ConfigurationCatalog {

    boolean supportsApplication(String application);

    boolean supportsLabel(String label);

    boolean supportsProfile(String application, String label, String profile);

    Map<String, Object> find(
            String application,
            String label,
            String profile);
}
~~~

In production, `ConfigurationCatalog` can be implemented via JDBC, JPA, Redis, or a REST client. Queries must use parameter binding and enforce caller access permissions.

In the example, `find` follows the convention of always returning a non-null map; if a profile has no properties, it returns an empty map. This prevents `NullPointerException` when the repository calls `putAll`.

### 6.2. Repository Implementing the Contract

~~~java
package com.example.configserver.repository;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.environment.PropertySource;
import org.springframework.cloud.config.server.environment.EnvironmentRepository;
import org.springframework.core.Ordered;
import org.springframework.util.StringUtils;

public class CatalogEnvironmentRepository
        implements EnvironmentRepository, Ordered {

    private static final String DEFAULT_LABEL = "main";
    private static final String DEFAULT_PROFILE = "default";

    private final ConfigurationCatalog catalog;

    public CatalogEnvironmentRepository(ConfigurationCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public Environment findOne(
            String application,
            String profile,
            String label) {

        String selectedLabel =
                StringUtils.hasText(label) ? label : DEFAULT_LABEL;

        String[] profiles = parseProfiles(profile);
        Environment result = new Environment(application, profiles);
        result.setLabel(selectedLabel);

        if (!StringUtils.hasText(application)
                || !catalog.supportsApplication(application)
                || !catalog.supportsLabel(selectedLabel)) {
            return result;
        }

        Map<String, Object> merged = new LinkedHashMap<>();
        merged.putAll(catalog.find(
                application, selectedLabel, DEFAULT_PROFILE));

        for (String activeProfile : profiles) {
            if (DEFAULT_PROFILE.equals(activeProfile)) {
                continue;
            }

            if (!catalog.supportsProfile(
                    application, selectedLabel, activeProfile)) {
                return result;
            }

            merged.putAll(catalog.find(
                    application, selectedLabel, activeProfile));
        }

        if (!merged.isEmpty()) {
            String sourceName = "custom:"
                    + application + ":"
                    + String.join(",", profiles) + ":"
                    + selectedLabel;

            result.add(new PropertySource(sourceName, merged));
        }

        return result;
    }

    private String[] parseProfiles(String profile) {
        if (!StringUtils.hasText(profile)) {
            return new String[] { DEFAULT_PROFILE };
        }

        String[] parsed = Arrays.stream(
                    StringUtils.commaDelimitedListToStringArray(profile))
                .map(String::trim)
                .filter(StringUtils::hasText)
                .distinct()
                .toArray(String[]::new);

        return parsed.length == 0
                ? new String[] { DEFAULT_PROFILE }
                : parsed;
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
~~~

This example illustrates the orchestration logic. `ConfigurationCatalog` must have a real implementation and bean for the repository to start. The example uses `main` as the default label for this catalog; if the backend uses Git, read the default label from Config Server's Git configuration instead of assuming every repository has a `main` branch.

Config Client may send a default label such as `master` depending on version and configuration. When deploying, align the default label across client, Config Server, and catalog. The most predictable approach is setting `spring.cloud.config.label` explicitly in the deployment environment or reading the default label from backend configuration rather than letting each layer pick its own value.

Key details in the code:

- `new Environment(application, profiles)` constructs the response model with the application name and parsed profile list.
- `setLabel` records the selected label in the response.
- `LinkedHashMap` preserves insertion order; `putAll` for a later profile replaces overlapping keys from an earlier profile.
- `PropertySource` holds the resulting map for Config Client to read.
- `getOrder()` controls precedence when the repository is included in a composite; the concrete value must fit the ordering of the remaining repositories.
- An invalid profile returns an empty Environment in the example. When `accept-empty=false` is configured, Config Server can return HTTP 404 if the application has no property sources. A production system may use a custom exception/response policy to distinguish a non-existent app from an invalid profile.

## 7. Registering the Repository in Config Server

Config Server requires the `spring-cloud-config-server` dependency, managed by a Spring Cloud BOM compatible with Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
~~~

The server application enables `@EnableConfigServer`:

~~~java
package com.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Register the repository as a bean. You can scope the bean to the **Config Server**'s runtime `custom` profile:

~~~java
package com.example.configserver;

import com.example.configserver.repository.CatalogEnvironmentRepository;
import com.example.configserver.repository.ConfigurationCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class CustomRepositoryConfiguration {

    @Bean
    CatalogEnvironmentRepository catalogEnvironmentRepository(
            ConfigurationCatalog catalog) {
        return new CatalogEnvironmentRepository(catalog);
    }
}
~~~

Activate the `custom` profile on Config Server:

~~~yaml
spring:
  application:
    name: config-server
  profiles:
    active: custom
  cloud:
    config:
      server:
        accept-empty: false
server:
  port: 8888
~~~

`custom` here is the profile activating the repository bean inside the Config Server process. It is **not** the `dev`, `prod`, or `mysql` profile that Config Client sends in requests. The two sets of profiles have different scopes and purposes.

In the example, `accept-empty: false` makes the server return 404 if the repository cannot find the application or returns an Environment without property sources. If you want to combine a custom repository with Git/Vault or other sources, configure a composite explicitly instead of accidentally activating multiple backends without a defined order.

## 8. Calling the Endpoint to Verify Application/Profile Selection

After running Config Server at `localhost:8888`, try calling:

~~~bash
curl -i "http://localhost:8888/order-service/dev/release-2026.11"
~~~

Multi-profile request:

~~~bash
curl -i "http://localhost:8888/order-service/dev,mysql/release-2026.11"
~~~

Same profile, different application:

~~~bash
curl -i "http://localhost:8888/catalog-service/dev/release-2026.11"
~~~

If the catalog contains data for these three selector sets, each response will contain `name`, `profiles`, `label`, and the corresponding property sources. If `order-service` has `order.timeout=5s` in `dev` and `mysql` sets `order.timeout=8s`, the resulting response must use `8s` according to the last-profile-wins rule implemented by the repository.

### 8.1. Example Response

~~~json
{
  "name": "order-service",
  "profiles": ["dev", "mysql"],
  "label": "release-2026.11",
  "propertySources": [
    {
      "name": "custom:order-service:dev,mysql:release-2026.11",
      "source": {
        "order.timeout": "8s",
        "order.checkout.enabled": "true",
        "spring.datasource.url": "jdbc:mysql://db-dev/orders"
      }
    }
  ]
}
~~~

When querying `catalog-service`, the repository must return data belonging to the `catalog-service` namespace; it must never reuse `order-service` configuration merely because the profile matches.

## 9. Combining Multiple Profiles in the Right Order

Suppose the catalog contains:

| Profile | `order.timeout` | `order.checkout.enabled` | `spring.datasource.url` |
| --- | --- | --- | --- |
| `default` | `3s` | `false` | `jdbc:postgresql://db/orders` |
| `dev` | `5s` | `true` | `jdbc:postgresql://db-dev/orders` |
| `mysql` | `8s` | — | `jdbc:mysql://db-dev/orders` |
| `prod` | `2s` | `false` | `jdbc:postgresql://db-prod/orders` |

For the request `dev,mysql`, the merge process is:

1. Load `default`: timeout `3s`, checkout `false`, default PostgreSQL URL.
2. Load `dev`: timeout `5s`, checkout `true`, dev PostgreSQL URL.
3. Load `mysql`: timeout `8s`, dev MySQL URL; checkout is not declared so it retains `true` from `dev`.

Result:

~~~yaml
order:
  timeout: 8s
  checkout:
    enabled: true
spring:
  datasource:
    url: jdbc:mysql://db-dev/orders
~~~

If the request is reversed to `mysql,dev`, the `dev` profile is processed last and overrides `order.timeout` back to `5s`, while the datasource URL reverts to dev PostgreSQL. Therefore, do not reorder input profiles if their order is meaningful to the client.

If you want to keep each source separate for auditing, you can return multiple `PropertySource` entries instead of merging into one map. When doing so, ensure higher-priority property sources appear earlier in the `Environment` list, per Config Server conventions.

## 10. How Clients Choose Application, Profile, and Label

Modern Config Clients use Config Data import. Example `application.yml` for `order-service`:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: dev,mysql
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: release-2026.11
~~~

Client dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Spring Cloud Config Client uses:

- `spring.application.name` to choose the default application.
- `Environment.getActiveProfiles()` to obtain the active profiles.
- `spring.cloud.config.label` to choose the label.

You can override application name, profiles, or label specifically with:

~~~yaml
spring:
  cloud:
    config:
      name: order-service,shared-database
      profile: dev,mysql
      label: release-2026.11
~~~

When `spring.cloud.config.name` has multiple comma-separated names, Config Server can return shared configuration from `application`, service-specific configuration, and the additional shared names listed. Names appearing later in the list can override overlapping keys from earlier names.

### 10.1. Why Might Config Server Receive Multiple Requests at Startup?

With `spring.config.import`, Spring Boot loads configuration in two steps:

1. Request configuration with the `default` profile to find properties that may activate other profiles.
2. Once active profiles are determined, request additional configuration for those profiles.

Therefore, a Config Client can call `EnvironmentRepository.findOne` multiple times during the same startup process. This is normal behavior. The repository should be **idempotent**, returning consistent results for the same `application/profile/label` tuple, performing no state-mutating writes on reads, and never assuming only one call occurs per startup.

If legacy bootstrap is needed, you must explicitly enable the bootstrap mechanism per the Spring Cloud Config documentation. `bootstrap.yml` is not required when using modern Config Data import.

## 11. Selecting Repositories in a Composite Setup

A Config Server can combine Git with a custom repository, Vault, or other sources. When multiple repositories provide the same key, their order determines which value wins.

Composite example:

~~~yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: file:./config-repository
          - type: vault
            host: 127.0.0.1
            port: 8200
~~~

With composite repositories, the declaration order affects precedence. Spring Cloud Config documentation also supports configuring `order` when activating backends via their respective profiles; smaller numbers have higher priority.

The example above only illustrates ordering. When using real Vault, configure tokens/credentials per Vault backend instructions and ensure the token has read permission for the exact secret path.

If a custom repository is included in a composite, implement `Ordered` and `getOrder()` to clearly define its position. Without `Ordered`, a custom repository is treated as having the lowest priority per the custom repository guide.

An important operational detail: by default, an error reading one repository can fail the entire composite request. Only set `spring.cloud.config.server.fail-on-composite-error=false` when you explicitly accept continuing to serve from the remaining sources and understand the impact on configuration completeness.

## 12. Testing the Repository

You can unit test `findOne` directly without starting an HTTP server. Using a mock catalog, verify at least these cases:

~~~java
@Test
void selectsApplicationAndMergesProfilesInRequestOrder() {
    Environment environment = repository.findOne(
            "order-service",
            "dev,mysql",
            "release-2026.11");

    assertThat(environment.getName()).isEqualTo("order-service");
    assertThat(environment.getProfiles())
            .containsExactly("dev", "mysql");
    assertThat(environment.getLabel())
            .isEqualTo("release-2026.11");

    Map<?, ?> source = (Map<?, ?>) environment
            .getPropertySources().get(0).getSource();

    assertThat(source).containsEntry("order.timeout", "8s");
}
~~~

The test snippet assumes the catalog has the earlier sample data and uses AssertJ. Add tests for other applications to verify namespaces do not leak across services.

### 12.1. Recommended Test Matrix

| Case | Input | Expected result |
| --- | --- | --- |
| Single application, single profile | `order-service`, `dev`, `release-2026.11` | Selects config for the right service/profile/label |
| Multiple profiles | `dev,mysql` | Later profile overrides overlapping keys |
| Reversed profile order | `mysql,dev` | Values change according to the new order |
| Different application | `catalog-service`, `dev` | Contains no properties from `order-service` |
| Different label | `release-2026.10` | Returns the older snapshot or empty data |
| Non-existent application | `unknown-service` | Never returns another service's config; 404 handled per policy |
| Invalid profile | `dev,unknown` | Errors or returns empty per policy; never silently falls back to wrong profile |
| Empty/default profile | `default` or no profile | Uses default data per chosen rules |

Beyond unit tests, add integration tests calling the real endpoint to check `Environment` serialization, HTTP status when data is not found, and that Config Server selects the right repository bean for the runtime profile.

## 13. Protecting Inputs and Configuration Data

`application`, `profile`, and `label` are passed through the URL. They are request-supplied selectors, so they must be authenticated and validated before use.

- **Application allowlist:** only allow callers to read applications their identity is authorized for.
- **Validate profile:** restrict valid profiles per application; disallow empty strings, control characters, or unsupported profiles.
- **Validate label:** only accept branches/tags/commits or versions allowed by policy; never concatenate the label directly into shell commands or SQL.
- **Safe queries:** use parameterized SQL/ORM binding; never concatenate `application` or `profile` into SQL statements.
- **File paths:** if building a file-based backend, canonicalize paths and verify the resolved path stays within the permitted configuration root to prevent path traversal.
- **Prevent secret leaks:** protect Config Server endpoints with authentication/authorization and TLS; return secrets only to authorized clients.
- **Audit:** record application, profile, label, caller, outcome, and configuration version; avoid logging secret values.

The `(_)` notation can be used by Spring Cloud Config to represent `/` in certain application/label paths because `/` is a URL separator. This mechanism only solves path encoding, **it does not replace access control checks**.

## 14. Common Mistakes

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Request returns another application's config | Repository ignores `application` parameter or catalog uses incomplete keys | Use `application` as a namespace key in every query and add cross-application tests |
| Second profile does not override | Repository sorts profiles or merges in reverse order | Preserve input profile order and apply later profiles last |
| `default` profile is missing | Only reads active profiles without loading shared defaults | Load `default` first, then apply active profiles |
| Label does not change data | Backend always uses a default branch/version | Include `label` in catalog queries or Git references |
| Client calls Config Server multiple times | Config Data loads `default` first, then active profiles | Make `findOne` idempotent and inspect request logs per profile |
| Custom repository is not called | Bean not created due to profile/conditional config or another backend is active | Check Config Server runtime profile and composite configuration |
| Composite returns unexpected values | Repository order/`Ordered` is unclear | Declare explicit ordering and test overlapping keys |
| Application receives an empty Environment | Wrong application/profile/label or catalog has no data | Check request parameters and enable `accept-empty=false` if 404 is desired |

## 15. Summary

In Spring Cloud Config Server, `EnvironmentRepository.findOne(application, profile, label)` is the extension point for selecting and reading configuration by application, profile, and version. Input parameters define the data scope; `org.springframework.cloud.config.environment.Environment` is then built to return metadata along with `PropertySource` objects to the client.

A well-designed repository preserves `application` and `label`, processes the profile list in exact order, loads default configuration first, handles missing data cleanly, and returns consistent results. When integrating into Config Server, register the bean under the proper runtime profile, define precedence if using a composite, secure the endpoint, and test both valid and invalid requests.

## References

- [Spring Cloud Config — Custom Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/custom-enviroment-repository.html): implementing `EnvironmentRepository`, registering custom beans, and `Ordered`.
- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html): meaning of application/profile/label and profile precedence.
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): how clients select application/profile/label, Config Data import, and requests when active profiles change.
- [Spring Cloud Config — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html): repository order, `order`, and composite error handling.
- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): Git labels, application/profile repository patterns, and search paths.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): Spring Framework's `Environment`, profiles, and `PropertySource`.

Always verify against the documentation for the exact Spring Cloud release train in use. The `EnvironmentRepository` contract may include additional overloads depending on the version; the three-parameter method in this lesson is the foundational starting point for a custom repository.
