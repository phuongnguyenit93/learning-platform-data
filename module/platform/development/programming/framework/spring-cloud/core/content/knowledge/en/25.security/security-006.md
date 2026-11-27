# Restricting Dynamically Modifiable Properties by Version Capabilities

Spring Cloud allows applications to update the Environment at runtime and apply new configurations to certain beans. This capability is useful for operating feature flags, rate limits, or integration settings without restarting the service. However, an endpoint capable of writing to the Environment can also modify sensitive properties if the allowed keys are not restricted.

This issue was documented in **CVE-2026-59284 – Spring Cloud Commons no allow list for writable env actuator endpoint**, published on 2026-08-20 with severity HIGH. Affected versions allow POST requests to the Actuator Environment endpoint without a property key allowlist. The patch introduced a property to restrict updatable keys: **management.endpoint.env.post.valid-keys-regex**.

This lesson belongs to the **Security** chapter of the **SPRING_CLOUD_CORE** module. It focuses on the boundary between updating the Environment and refreshing beans, the capabilities of each Spring Cloud Commons branch, configuring an allowlist using regular expressions, securing the endpoint, and writing tests to confirm properties outside the list cannot be modified.

## 1. Risks of Allowing Environment Writes

Spring Boot Actuator provides management endpoints for observing and controlling an application. Spring Cloud Context adds the ability to write new values into the Environment via POST /actuator/env, then detect changes and update certain beans.

If this write endpoint accepts arbitrary property keys, an authorized caller could attempt to modify configurations beyond the intended operational scope, such as:

- Database URLs or connection details.
- Authentication, authorization, or session settings.
- Management addresses, ports, and paths.
- Spring Security or management endpoint configurations.
- Cloud client, broker, or service discovery configurations.
- Log levels of sensitive packages.
- Feature flags or business limits that the operator should not be permitted to alter.

Changing a property in the Environment does not necessarily change every bean's behavior immediately. The outcome depends on whether a bean is rebound or refreshed. Nevertheless, allowing arbitrary key writes creates a large attack surface because it enables modifying the application's runtime configuration source.

### 1.1. CVE-2026-59284

The official security advisory describes the vulnerability as a missing allowlist for property keys when enabling the writable /actuator/env endpoint in Spring Cloud Commons.

| Field | Details |
| --- | --- |
| CVE | CVE-2026-59284 |
| Published | 2026-08-20 |
| Severity | HIGH |
| Component | Spring Cloud Commons |
| Risk | POST /actuator/env can write keys outside the intended scope |
| Primary Mitigation | Upgrade to a patched version and configure valid-keys-regex |
| Source | Spring Security Advisories |

Do not treat adding a regex property to the configuration file of an older version as having fixed the CVE. The Spring Cloud Commons code itself must support checking the regex before accepting write operations.

Version capability differences appear directly in the documentation: Spring Cloud 2023.0.x docs only instructed enabling POST via management.endpoint.env.post.enabled; current Spring Cloud Commons docs add the valid-keys-regex requirement to restrict writable keys. Always verify the actual Commons implementation rather than merely checking whether the property name is in the configuration file.

## 2. Capabilities by Spring Cloud Commons Version

The Spring Security Advisory lists the affected version ranges and corresponding fixed versions:

| Spring Cloud Commons | Status | Fixed Version | Fix Release Scope |
| --- | --- | --- | --- |
| 5.0.0 to 5.0.2 | Affected | 5.0.3 | OSS |
| 4.3.0 to 4.3.3 | Affected | 4.3.4 | Enterprise Support Only |
| 4.0.0 to 4.2.6 | Affected | 4.2.7 | Enterprise Support Only |
| 3.1.10 and earlier | Affected | 3.1.11 | Enterprise Support Only |

At the time of writing, Spring Cloud Commons 5.0.4 is a newer stable release in the 5.0.x branch. Spring Cloud 2025.1.3 incorporated the CVE fix into the release train; Spring Cloud 2025.1.4 currently uses Commons 5.0.4.

Key points to note:

- For Commons 5.0.0 to 5.0.2, upgrade to at least 5.0.3 or a newer release in the same branch.
- For Commons 4.3.0 to 4.3.3, the advisory notes that fix 4.3.4 is available under Enterprise Support only.
- For Commons 4.0.0 to 4.2.6, the advisory notes that fix 4.2.7 is available under Enterprise Support only.
- For Commons 3.1.10 and earlier, the advisory notes that fix 3.1.11 is available under Enterprise Support only.
- Older branches without a listed OSS fix must be upgraded to a supported release train or handled through official support channels.

If an application cannot be upgraded yet, disable POST /actuator/env and do not expose this write endpoint. Never rely on a regex that is unimplemented in an affected version to protect it.

### 2.1. Maintain Spring Boot and Spring Cloud Compatibility

Do not upgrade Spring Cloud Commons in isolation to an arbitrary version without checking the release train. Spring Cloud publishes a BOM to manage modules across a compatible line.

| Spring Cloud release train | Spring Boot generation | Notes |
| --- | --- | --- |
| 2025.1.x – Oakwood | 4.0.x; supports 4.1.x since 2025.1.2 | Commons 5.0.x; 2025.1.3 includes the CVE fix |
| 2025.0.x – Northfields | 3.5.x | Commons 4.3.x; advisory lists fix 4.3.4 as Enterprise Support Only |
| 2024.0.x – Moorgate | 3.4.x | Commons 4.2.x; advisory lists fix 4.2.7 as Enterprise Support Only |
| 2023.0.x – Leyton | 3.2.x and 3.3.x since 2023.0.2 | Verify exact Commons version and support status before upgrading |
| 2022.0.x – Kilburn | 3.0.x and 3.1.x since 2022.0.3 | Older branch; check support status and available fixes |

For example, Spring Cloud 2025.1.4 is built on Spring Boot 4.0.9 and supports Spring Boot 4.1.2. If an application is still on Spring Boot 3.x, do not force Spring Cloud 5.0.x onto the classpath merely to obtain the patch. Plan a coordinated Boot and Cloud upgrade, or apply the corresponding Enterprise fix if your organization holds that support entitlement.

### 2.2. Use the BOM Instead of Pinning Individual Modules

Maven example for the 2025.1.4 release train:

~~~xml
<properties>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The BOM ensures Spring Cloud modules use versions tested together for that release train. When remediating a CVE, inspect the dependency tree to confirm the actual Spring Cloud Commons version resolved at runtime, even if the application does not declare that dependency directly.

Do not conclude an upgrade succeeded simply from the version string in one build file. Transitive dependencies, dependency constraints, or another platform BOM can override the expected version.

## 3. What Does POST /actuator/env Do?

Spring Cloud Context extends Spring Boot Actuator's Environment endpoint. When POST operations are enabled and the endpoint is exposed, clients can submit a property name along with a new value.

Example payload:

~~~json
{
  "name": "app.runtime.catalog-enabled",
  "value": "false"
}
~~~

Spring Cloud updates the Environment and detects changed keys. Standard behaviors include:

- Rebinding beans managed with @ConfigurationProperties.
- Updating log levels for keys under logging.level.*.
- Allowing application listeners to receive EnvironmentChangeEvent to perform additional actions.

This change lives in the running process's Environment. It does not modify application.yml files, the Config Server Git repository, or deployment manifests.

### 3.1. Updating the Environment Does Not Update Every Bean

A bean receives new values only if its configuration management mechanism supports updates.

For example, a @ConfigurationProperties bean with setters can be rebound. A bean that captured a value in a regular field without being rebound or refreshed continues using the old value.

Therefore, distinguish:

| Mechanism | Role |
| --- | --- |
| POST /actuator/env | Changes values in the Environment |
| EnvironmentChangeEvent | Notifies which property keys changed |
| @ConfigurationProperties rebinding | Reassigns values on configuration beans |
| @RefreshScope | Invalidates cached target so the bean is recreated on next use |
| Spring Cloud Bus | Distributes change/refresh events across multiple instances |

The CVE allowlist protects property key writes via the writable Environment endpoint. It is not a general filter for every configuration source or every refresh mechanism.

## 4. Enabling the Allowlist Based on Patched Version Capabilities

On a patched version of Spring Cloud Commons, you can restrict writable property keys with:

**management.endpoint.env.post.valid-keys-regex**

Example allowing only three application-managed properties:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env"
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(catalog-enabled|recommendations-enabled|max-items))$'
~~~

The regex above matches only these keys:

~~~text
app.runtime.catalog-enabled
app.runtime.recommendations-enabled
app.runtime.max-items
~~~

Keys such as spring.datasource.url, spring.security.user.password, management.endpoints.web.exposure.include, or server.port do not match and are excluded from writes.

This example assumes a patched version. On an affected version, never assume valid-keys-regex is enforced.

### 4.1. Reading the Regex

| Component | Meaning |
| --- | --- |
| ^ | Start of string |
| app\.runtime\. | Permitted property prefix |
| (catalog-enabled\|recommendations-enabled\|max-items) | One of the three listed key names |
| $ | End of string |

Dots in property names are escaped as \. to match literal dots only. The ^ and $ anchors bound the entire key, preventing a longer string that merely contains an allowed substring from being accepted.

YAML uses single quotes around the regex to preserve backslashes verbatim. If double quotes are used, account for YAML escaping rules.

### 4.2. Do Not Use Overly Broad Regexes

Do not configure:

~~~yaml
management:
  endpoint:
    env:
      post:
        valid-keys-regex: '.*'
~~~

That regex matches every property key and defeats the allowlist.

Other broad patterns also carry risks:

~~~text
^app\..*$
^spring\..*$
.*password.*
.*url.*
~~~

A broad application prefix may encompass security settings, credentials, or internal endpoints in the future. Enumerate the exact keys that need dynamic updates instead of opening an entire namespace without clear justification.

### 4.3. Key Restriction Alone Does Not Validate Values

The regex validates the property name. It does not validate whether the value makes business sense.

For example, the key app.runtime.max-items may be writable, yet a value of 1000000 could cause overload if the application lacks validation.

Validate values via binding and validation constraints:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.runtime")
public class RuntimeOptions {

    @Min(1)
    @Max(100)
    private int maxItems = 20;

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
~~~

Register RuntimeOptions with @ConfigurationPropertiesScan or @EnableConfigurationProperties. Validation must be active with the appropriate validation dependency on the classpath.

The allowlist answers "which keys may be written?". Validation answers "which values are valid?". Authorization answers "who may perform the operation?". All three layers must be designed together.

## 5. Protecting the Endpoint with Access Control and Network Boundaries

A regex does not authenticate callers. Someone without authorization still must not be able to call the endpoint even if they know a key on the allowlist.

A production setup should include these protective layers:

- Expose the env endpoint only when an approved operational need exists.
- Place the management interface on an internal network or separate management port.
- Use Spring Security to require identities and dedicated roles for configuration changes.
- Scope operator permissions by environment and service.
- Use TLS or mTLS on management paths.
- Audit caller, key, timestamp, outcome, and change request.
- Monitor POST requests to /actuator/env.
- Never place shared administrative credentials in source code or application.yml.
- Never expose all of Actuator with include="*".

If the application declares a custom SecurityFilterChain, Spring Boot's automatic Actuator security configuration backs off. The application must then define rules for both management endpoints and all remaining routes.

### 5.1. Expose Only Necessary Endpoints

Example exposing only health and env on the management interface:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
~~~

Exposure only makes endpoints reachable over HTTP. It does not replace authentication, authorization, or firewalls.

If the application does not need runtime Environment updates over HTTP, leave env POST disabled and do not expose the env endpoint. Never enable an endpoint for quick testing and forget to disable it before production deployment.

### 5.2. Separate Write Permissions from Read Permissions

A simple permission model:

| Group | Permissions |
| --- | --- |
| Health probe | Read health status only |
| Monitoring | Read required metrics and operational data |
| Configuration operator | Write keys on the allowlist |
| Application administrator | Manage endpoints per dedicated policy |
| Service identity | Receive configuration from Config Server or Bus per granted permissions |

Do not grant Actuator admin roles to all application users. Accounts permitted to write Environment properties are operational identities capable of altering process behavior.

### 5.3. Avoid Exposing Configuration Values

GET /actuator/env and /actuator/configprops reveal details about running configuration. Even though Spring Boot provides sanitization, these endpoints should not be publicly accessible.

- Keep sensitive values masked.
- Never log passwords, tokens, or private keys.
- Never return the entire Environment to frontends or business APIs.
- Restrict configuration read access by role.
- Protect logs and audit trails because they may reference property keys or change details.

## 6. Testing the Allowlist

Do not test only a single valid request. Include permitted, rejected, and unauthorized cases.

### 6.1. Valid Request

Example:

~~~bash
curl -X POST http://localhost:8080/actuator/env \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CONFIG_OPERATOR_TOKEN" \
  -d '{"name":"app.runtime.catalog-enabled","value":"false"}'
~~~

After the operation succeeds, verify that the Environment and configuration beans received the new value via the corresponding rebinding mechanism.

Do not treat a successful response as proof that every bean in the ApplicationContext was recreated. If a bean requires @RefreshScope, run the refresh workflow appropriate for that bean.

### 6.2. Invalid Request

Attempt to write a sensitive property outside the allowlist:

~~~bash
curl -X POST http://localhost:8080/actuator/env \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CONFIG_OPERATOR_TOKEN" \
  -d '{"name":"spring.datasource.url","value":"jdbc:example"}'
~~~

On a patched release with a properly scoped regex, the operation must be rejected. Also verify that the Environment retains its previous value and no configuration bean changed.

Never test writing sensitive keys in production. Use a test context or staging environment with dummy data.

### 6.3. Minimum Test Matrix

| Test | Expected Outcome |
| --- | --- |
| Valid key, caller has role | Write succeeds |
| Key outside regex, caller has role | Rejected |
| Valid key, caller lacks role | 401 or 403 depending on security configuration |
| POST env disabled | No write succeeds |
| env not exposed over HTTP | Endpoint unreachable over web |
| Missing or misconfigured regex | Dynamic write disallowed; verify exact patch behavior |
| Value fails validation | Binding/validation fails or app preserves safe state per config |
| Valid key updated | Environment and rebinding-capable beans reflect new value |

### 6.4. Example Test with MockMvc

Example test structure:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,env",
        "management.endpoint.env.post.enabled=true",
        "management.endpoint.env.post.valid-keys-regex=^(app\\.runtime\\.(catalog-enabled|recommendations-enabled|max-items))$"
})
@AutoConfigureMockMvc
class WritableEnvironmentAllowlistTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsAnAllowlistedProperty() throws Exception {
        mockMvc.perform(post("/actuator/env")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "name": "app.runtime.catalog-enabled",
                          "value": "false"
                        }
                        """))
                .andExpect(status().is2xxSuccessful());
    }

    @Test
    void rejectsAPropertyOutsideTheAllowlist() throws Exception {
        mockMvc.perform(post("/actuator/env")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "name": "spring.datasource.url",
                          "value": "jdbc:example"
                        }
                        """))
                .andExpect(status().is4xxClientError());
    }
}
~~~

This test must run against a patched Spring Cloud Commons version with the Actuator endpoint enabled. The snippet focuses on the regex; if Spring Security is active in the context, supply mock users/roles for valid requests and test missing permissions separately. You can add assertions on the Environment or RuntimeOptions bean to prove rejected keys leave values unchanged.

If the endpoint is protected by Spring Security, the allowed test must authenticate with the proper user/role; the unauthorized test must verify 401/403 before drawing conclusions about the regex.

## 7. Distinguishing POST env from POST refresh

The two endpoints serve different purposes:

| Endpoint | Role | Uses the CVE Key Allowlist? |
| --- | --- | --- |
| POST /actuator/env | Writes properties into Environment and triggers related rebinding | Yes, on patched Commons |
| POST /actuator/refresh | Refreshes property sources via Spring Cloud and refreshes @RefreshScope beans | Not the key-writing endpoint covered by that allowlist |
| Config Server refresh | Fetches external configuration from Config Server | Access controlled at Config Server/repository and refresh mechanism |
| Spring Cloud Bus refresh | Broadcasts refresh events across multiple instances | Access controlled at Bus, broker, and receiving endpoint |

The valid-keys-regex is not a global filter across all configuration changes. It protects property key writes through the writable Environment endpoint added by Spring Cloud Commons.

If configuration is altered via Config Server, Spring Cloud Bus, a custom EnvironmentPostProcessor, or code calling the Environment API, control the sources and permissions of those specific mechanisms.

## 8. Rebinding @ConfigurationProperties

When EnvironmentChangeEvent is processed, Spring Cloud can rebind @ConfigurationProperties beans.

The example below illustrates a separate mutable class to explain rebinding. In real applications, do not register multiple configuration beans with the same prefix just to mimic examples; maintain a single configuration class with a clear contract.

Example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.runtime")
public class RuntimeOptionsRebindingExample {

    private boolean catalogEnabled = true;
    private int maxItems = 20;

    public boolean isCatalogEnabled() {
        return catalogEnabled;
    }

    public void setCatalogEnabled(boolean catalogEnabled) {
        this.catalogEnabled = catalogEnabled;
    }

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
~~~

When app.runtime.catalog-enabled or app.runtime.max-items changes and the bean is rebound, the bean receives the new values according to binding rules.

### 8.1. Rebinding Mutates the Existing Instance

Rebinding updates fields of the existing bean. It does not create a new instance and swap it atomically in all cases.

Spring Cloud serializes concurrent rebinds of the same bean. However, another thread may still read the bean while fields are being updated and observe an intermediate state.

If the application requires a consistent snapshot during refresh, consider using @RefreshScope on an appropriate bean. Never treat a mutable configuration bean as shared data without a synchronization plan.

### 8.2. Constructor Binding and Java Records

@ConfigurationProperties objects using constructor binding, including Java Records, cannot be refreshed under the current mechanism described in Spring Cloud Context.

If a configuration group needs runtime changes, pick a compatible binding style and test it against your version. Never assume every @ConfigurationProperties class updates automatically just because the Environment changed.

### 8.3. Values Removed from the Environment

Spring Cloud documentation notes that removing a configuration value and refreshing does not necessarily make the presence of that value disappear as expected. If application logic relies on a property being absent, test key-removal semantics explicitly; consider modeling an explicit state value instead of relying on absence.

## 9. @RefreshScope and Refreshable Bean Boundaries

@RefreshScope creates a lazy proxy for a bean. When the refresh scope is invalidated, the cached target is discarded and a new target is initialized on the next call.

Example:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class RemoteCatalogClient {

    private final String endpoint;

    public RemoteCatalogClient(CatalogClientProperties properties) {
        this.endpoint = properties.getEndpoint();
    }

    public String endpoint() {
        return endpoint;
    }
}
~~~

When configuration changes and the scope is refreshed, the next call can create a new target with the updated endpoint value.

### 9.1. @RefreshScope Does Not Automatically Apply to All Beans in a Configuration Class

Annotating a @Configuration class with @RefreshScope does not mean every bean declared in that class automatically becomes refresh-scoped.

Beans depending on beans created by a configuration class also do not automatically receive new targets. If a dependency needs recreation, place the appropriate scope on that bean itself or design the dependency graph so re-injection works properly.

### 9.2. Non-Refreshable Beans and HikariDataSource

Spring Cloud Context maintains a default list of beans that are never refreshed. HikariDataSource is a prominent example documented under spring.cloud.refresh.never-refreshable.

If an application uses HikariDataSource, do not assume refresh will recreate the connection pool simply because the database URL in the Environment changed. Choose a configuration and pool replacement strategy suited to the datasource's lifecycle.

Related properties:

| Property | Purpose |
| --- | --- |
| spring.cloud.refresh.extra-refreshable | Adds bean names or class names to treat as refreshable |
| spring.cloud.refresh.never-refreshable | Lists bean names or class names excluded from refresh/rebind |
| spring.cloud.refresh.never-reset-nested-types | Excludes nested library types from recursive reset during rebind |
| spring.cloud.refresh.enabled | Enables/disables refresh scope auto-configuration and related features |

These properties control bean lifecycles or rebinding mechanics. They are **not a property key allowlist** for POST /actuator/env and do not remediate CVE-2026-59284.

### 9.3. AOT and Native Images

Context refresh is not supported for Spring AOT transformations and native images according to current Spring Cloud Context documentation. For AOT/native applications, set spring.cloud.refresh.enabled=false and manage configuration in line with the build/deploy lifecycle.

Do not enable refresh scope simply because you want an API to alter settings. Identify which beans genuinely support that lifecycle.

## 10. Config Server and Property Source Precedence

Spring Cloud Config can inject remote property sources into the Environment. By default, remote property sources may disallow overrides by local properties.

Relevant properties:

| Property | Meaning |
| --- | --- |
| spring.cloud.config.allow-override | Allows remote property sources to honor override rules |
| spring.cloud.config.override-none | When allow-override is true, lets local property sources override from any source |
| spring.cloud.config.override-system-properties | Controls whether system properties, command line args, and environment variables override remote properties |

These properties control **property source precedence**, not caller authentication and not a property key allowlist.

Having a local property take higher precedence than a remote property does not mean every user is allowed to modify that property. Config Server write access must be controlled at the repository, branch, credentials, API, and deployment pipeline.

### 10.1. Spring Cloud Config Client Does Not Poll by Default

Spring Cloud Config Client does not continuously poll Config Server for changes by default. In multi-replica deployments, Spring Cloud Bus can broadcast refresh events to instances.

When using Bus:
- Protect the broker with credentials and network policies.
- Restrict which publishers can emit events.
- Protect the busrefresh endpoint or equivalent mechanism.
- Track which instances received and processed the refresh.
- Do not treat the /actuator/env regex as protection for Bus events.

A configuration source capable of changing many properties requires its own review, audit, and rollback workflow.

## 11. Upgrade and Remediation Procedure for Affected Systems

When an application is found to use Spring Cloud Commons in an affected range:

1. Determine the actual Commons version in the runtime dependency tree.
2. Check whether POST /actuator/env is enabled.
3. Check whether the env endpoint is exposed over HTTP/JMX or any management interface.
4. If runtime Environment writes are unnecessary, disable POST and revoke exposure.
5. Restrict the management network and access permissions while preparing the upgrade.
6. Select a patch compatible with your Spring Cloud release train and Spring Boot version.
7. If using OSS, consider upgrading to Spring Cloud 2025.1.3 or newer with a compatible Spring Boot 4.0.x release; at the time of writing, 2025.1.4 uses Commons 5.0.4.
8. If a major version upgrade is not yet feasible, check the corresponding Enterprise Support patch or keep env POST disabled.
9. After upgrading, configure valid-keys-regex with a minimal list of keys.
10. Run tests for the allowlist, authentication, authorization, and rebinding.
11. Audit access logs and configuration changes during the window when the vulnerable version was running.
12. Record the BOM version, operator roles, permitted key list, and rollback procedure.

Do not merely edit an application.yml file and consider the issue resolved. Verify that the upgraded code actually enforces the allowlist.

### 11.1. If Unauthorized Operations Are Suspected

If access logs show unapproved POST /actuator/env requests:

- Identify the timestamp, source IP, identity, and submitted property keys.
- Compare the running Environment/runtime configuration against trusted configuration sources.
- Check for changes to log levels, database endpoints, security settings, and management exposure.
- Verify whether configuration beans were rebound or refreshed afterward.
- Restore configuration from a trusted source and restart instances if needed to clear uncertain runtime state.
- Revoke or rotate credentials if there is evidence sensitive values were altered or exposed.
- Preserve logs and audit records for investigation.

Do not automatically assume every application in an affected range was exploited. Distinguish running an affected version from evidence that an unauthorized request actually occurred.

## 12. Common Misconceptions

| Claim | Reality |
| --- | --- |
| Enabling env.post.enabled alone is safe enough | Requires a patched Commons release, regex allowlist, and access controls |
| Adding valid-keys-regex to an old version fixes the CVE | Older versions may not enforce that property |
| The regex also validates values | The regex only restricts property keys |
| The regex replaces Spring Security | The regex does not authenticate or authorize callers |
| /actuator/refresh uses the same allowlist | Refresh is not the key-writing operation of the writable env endpoint |
| @RefreshScope updates every bean automatically | Only appropriately scoped beans and designed dependencies are recreated |
| never-refreshable is a list of properties forbidden from editing | It is a list of beans excluded from refresh/rebind |
| allow-override grants permission to write configuration | It is a property source precedence rule |
| Config Server/Bus are protected by valid-keys-regex | Repositories, APIs, brokers, and publishers require separate controls |
| HTTP 200 from env POST proves every bean changed | It only confirms the endpoint succeeded; verify beans and consumers |

## 13. Security Review Checklist

- [ ] Identified the exact Spring Cloud Commons version running.
- [ ] Version is outside the affected range of CVE-2026-59284.
- [ ] If writable /actuator/env is required, Commons version supports valid-keys-regex.
- [ ] Regex includes start/end anchors and lists only necessary property keys.
- [ ] No wildcard .* or unjustified broad prefixes are used.
- [ ] Values are checked with business validation.
- [ ] POST env is enabled only when operationally needed.
- [ ] Endpoint is exposed only on the management network.
- [ ] Spring Security restricts callers with a dedicated role.
- [ ] Auditing is enabled for configuration-changing requests.
- [ ] GET env/configprops do not expose sensitive values.
- [ ] Config Server, Git repositories, and Bus have separate access controls.
- [ ] Rebinding is distinguished from @RefreshScope.
- [ ] Constructor-bound properties and never-refreshable beans have been reviewed.
- [ ] Tests prove valid keys are written and keys outside the allowlist are rejected.
- [ ] Tests prove unauthorized callers cannot invoke the endpoint.
- [ ] Rollback and investigation procedures exist for unintended runtime config changes.

## Remember

Restricting dynamic configuration updates must happen at the right layer and version. CVE-2026-59284 demonstrates that writable POST /actuator/env is unsafe without property key restrictions. Upgrade Spring Cloud Commons to a patched release, configure management.endpoint.env.post.valid-keys-regex with a narrow key list, protect the endpoint with authentication/authorization and a management network, and validate values separately. Do not confuse the env POST allowlist with @RefreshScope, never-refreshable, Config Server precedence, or Spring Cloud Bus: each mechanism has distinct scope and permissions.

## References

- Spring Security Advisory – CVE-2026-59284: https://spring.io/security/cve-2026-59284/
- Spring Cloud Commons – Application Context Services: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Cloud 2025.1.3 Release Notes – CVE-2026-59284 fix: https://spring.io/blog/2026/08/20/spring-cloud-2025-1-3-has-been-released/
- Spring Cloud 2025.1.4 Release Notes: https://spring.io/blog/2026/10/23/spring-cloud-2025-1-4-has-been-released/
- Spring Cloud – Spring Boot Compatibility Matrix: https://spring.io/projects/spring-cloud/
- Spring Boot Actuator – Endpoints and Security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Cloud Bus – Bus Refresh and Bus Env: https://docs.spring.io/spring-cloud/docs/current/reference/htmlsingle/spring-cloud.html
