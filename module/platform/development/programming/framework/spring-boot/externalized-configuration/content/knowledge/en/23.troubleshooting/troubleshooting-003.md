# Inspecting PropertySource and Value Origins Without Printing Secrets in Spring Boot

## Objectives

When a Spring Boot application receives an unexpected configuration value, the fastest way to diagnose it is usually to find out **which configuration source is taking precedence**, whether the property actually exists, and which path Binder/configuration beans used. However, inspecting Environment easily leaks sensitive information: the same Environment can contain database passwords, API keys, access tokens, connection URLs with credentials, Kubernetes secrets, or strings loaded from a secret source.

Therefore, you should not diagnose by printing all keys/values:

~~~java
// DO NOT DO THIS:
System.out.println(environment.getSystemEnvironment());
System.out.println(environment.getSystemProperties());
System.out.println(environment.getProperty("spring.datasource.password"));
~~~

Those statements can send secrets into stdout, container logs, log aggregation systems, CI artifacts, or support tickets. Once logs are copied and retained in multiple places, revoking secrets can be costly and uncertain.

The proper diagnostic approach is **inspecting structure and metadata**, without displaying raw values. This lesson focuses on:

1. Understanding Spring **PropertySource** precedence order and how the final property is resolved.
2. Listing source names/types in a controlled way, without dumping contents.
3. Identifying which sources provide a canonical key and which source has the highest precedence.
4. Distinguishing **PropertySource**, Binder's **ConfigurationPropertySource**, and **Origin**.
5. Inspecting origins such as file, resource, or line location when metadata is available, while not assuming origin always exists.
6. Using **/actuator/env** and **/actuator/configprops** safely; keeping values masked and restricting access.
7. Avoiding leaks via debug logs, exceptions, shell commands, test output, and incident reports.
8. Diagnosing environment variables, JVM system properties, CLI, Config Data imports, profiles, and relaxed binding.
9. Writing diagnostic helpers/tests that return presence/absence status and source type without returning raw values.
10. Building a runbook procedure usable in production without exposing secrets.

Examples favor Spring Boot 3.x APIs and Java 17+; guidance on management endpoints follows the corresponding capabilities in official Spring Boot documentation. Some packages and endpoint management options may change between Boot 3.x and Boot 4.x, so verify against your project version when deploying.

---

## 1. Typical Problem: One Value Set in Multiple Places

Suppose an HTTP client has a timeout:

~~~yaml
# application.yml
app:
  gateway:
    timeout: 5s
~~~

Yet the deployment has a production profile:

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 8s
~~~

An environment variable is also supplied:

~~~text
APP_GATEWAY_TIMEOUT=12s
~~~

And when launching the process there is a CLI argument:

~~~text
--app.gateway.timeout=15s
~~~

When code reads the configuration, the final value can be **15 seconds**, because command-line arguments normally take higher precedence than those other sources.

To diagnose, we need to know:

- Which property is being evaluated?
- Which sources contain that property?
- Which source comes first in lookup order?
- Did any test source, custom PropertySource, or extension step in between?
- Is this value after binding the same type expected by the bean?

**You do not need to print 5s, 8s, 12s, or 15s to answer the first question about which source wins**, if a helper can report that the property was found first in the "command-line" source category.

In real environments, app.gateway.timeout might be app.gateway.api-key. In that case, structure-based diagnostics instead of value printing becomes a security requirement.

## 2. Distinguish PropertySource, Environment, and Binder

Three conceptual layers:

**PropertySource** represents a source of properties such as systemEnvironment, systemProperties, commandLineArgs, or a Config Data document.

**ConfigurableEnvironment** maintains an ordered set of PropertySources, provides the property lookup API, and supports type conversion where applicable.

**Spring Boot Binder** binds properties according to canonical form and relaxed binding rules into JavaBeans, records, Lists, Maps, and nested objects.

Diagram:

~~~text
application.yml     application-prod.yml     env / JVM / CLI
       |                    |                      |
       +--------------------+----------------------+
                            |
                            v
                  MutablePropertySources
                  (ordered list)
                            |
             +--------------+--------------+
             |                             |
             v                             v
       Environment API                Binder API
       getProperty(...)               ConfigurationPropertySource
             |                             |
             v                             v
       value or null                @ConfigurationProperties
                                     Java object
~~~

### 2.1. Two Different Calls

~~~java
environment.getProperty("app.gateway.timeout");
~~~

and:

~~~java
Binder.get(environment)
      .bind("app.gateway.timeout", Duration.class);
~~~

can both read the same timeout concept, yet go through lookup/conversion mechanisms that are not completely identical.

In particular, Binder has rules for canonical naming, relaxed binding, collection indices, and map keys. An exact-key check on a PropertySource is not always equivalent to Binder finding a Java field.

### 2.2. Why Know the Difference?

If you see:

~~~text
APP_GATEWAY_READTIMEOUT
~~~

in the OS environment, yet call:

~~~java
source.containsProperty("app.gateway.read-timeout")
~~~

on a single PropertySource, the result does not necessarily reflect Binder's full aliasing/canonicalization capability. To properly analyze binding, use the ConfigurationPropertySource API or an appropriate Binder test rather than only searching for an exact key string.

---

## 3. What Does PropertySource Order Mean?

In **ConfigurableEnvironment**, the PropertySource list is ordered. When a property is requested, higher-precedence sources are typically checked before lower ones.

Common sources include:

- Command-line arguments.
- JVM system properties.
- OS environment variables.
- Config Data such as application.properties/application.yml.
- Profile-specific files and imported files.
- Sources added by SpringApplication or libraries.
- Configuration sources added in tests.

Note: this is not a table promising an absolute order for every application; test properties, DynamicPropertySource, devtools, JNDI, servlet parameters, custom PropertySources, and extensions can change the actual order.

**To know the real order of a process, inspect the PropertySource list already present in that process's Environment.**

### 3.1. List Position Does Not Equal Creation Time

An EnvironmentPostProcessor can run after Config Data is loaded yet call **addFirst**, placing its source ahead of existing sources.

Therefore "the source created last" does not automatically have the lowest or highest precedence. What matters is the final position in the list.

### 3.2. One Key Can Appear Multiple Times

For example:

~~~text
app.gateway.timeout
  -> commandLineArgs
  -> systemEnvironment
  -> Config resource application-prod.yml
  -> Config resource application.yml
~~~

Lower sources are not deleted; they still exist but are shadowed by earlier sources for overlapping keys.

A setting appearing in YAML does not prove YAML is the winning source. You must consider the full order and relevant name-mapping mechanisms.

---

## 4. Security Principle: Metadata First, Values Later

When production has a configuration error, do not open with "what is the real value?" Ask:

1. Is the key requested under the right name?
2. Which sources contain the key?
3. Which source is winning?
4. Does origin metadata help identify file/line?
5. Was any new source added by runtime, tests, or libraries?
6. Did the bean fail conversion/validation?
7. Is accessing the real value actually required to solve the issue?

In many incidents, steps 1–6 are enough.

### 4.1. Tiered Classification of Observable Data

| Information | Risk level | Handling approach |
| --- | --- | --- |
| Allowed config group name | Lower | Display only via allowlist |
| PropertySource category | Lower | Can be logged in a controlled manner |
| Source precedence position | Lower | Useful for diagnostics |
| Presence/absence of origin metadata | Lower | Can log boolean status |
| Full resource file path | Potentially sensitive | View only in controlled tooling; consider redacting |
| Env var name containing tenant/customer ID | Potentially sensitive | Do not scan and export in bulk |
| Raw property value | May be a secret | Do not log / view only via authorized workflow |
| Credential, password, token, private key | Very high | Never display in routine diagnostics |

Even **metadata** can reveal infrastructure layout, tenant names, internal addresses, or paths containing usernames. Therefore "not printing values" is necessary but not always sufficient.

---

## 5. Listing PropertySources Without Printing Values

A Java code example:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceInspector {

    public static void printSourceTypes(
            ConfigurableEnvironment environment) {

        int order = 0;
        for (PropertySource<?> source
                : environment.getPropertySources()) {

            order++;

            System.out.printf(
                "position=%d type=%s%n",
                order,
                source.getClass().getSimpleName()
            );
        }
    }
}
~~~

This snippet prints only **position** and **class simple name**. It does not call:

~~~java
source.getProperty(key)
source.getSource()
source.toString()
~~~

thereby avoiding several ways of accidentally printing the entire source content.

### 5.1. Should You Print source.getName()?

**PropertySource.getName()** is often useful because it can report names such as commandLineArgs, systemEnvironment, or a configuration document name.

However, for file sources, the name can include paths, resource URIs, or sensitive organizational data. Therefore in production, you can log only the source category, or map known names to safe labels.

Example:

~~~java
private static String safeSourceLabel(String name) {
    return switch (name) {
        case "commandLineArgs" -> "CLI";
        case "systemEnvironment" -> "OS_ENV";
        case "systemProperties" -> "JVM_SYSTEM";
        default -> "OTHER_SOURCE";
    };
}
~~~

This is an illustrative label set; in real applications, source names may vary, so test against the target Environment.

**Do not put raw source.getName() into default labels** if the source name might contain a file path or URI.

### 5.2. Never Dump source.getSource()

Some PropertySources hold a Map or object representing the underlying source. Calling:

~~~java
System.out.println(source.getSource());
~~~

can print all keys/values, including secrets. This is an antipattern to avoid even at DEBUG log level.

---

## 6. Identifying the Winning Source Without Printing Values

If you only want to see which source contains a key, you can write a helper returning the **precedence position** without returning the raw value.

However, the **PropertySource.containsProperty(...)** API uses the key name in that specific PropertySource's manner and may not reproduce full relaxed binding.

Basic example:

~~~java
public static int firstExactSourceIndex(
        ConfigurableEnvironment environment,
        String exactName) {

    int index = 0;
    for (PropertySource<?> source :
            environment.getPropertySources()) {

        index++;
        if (source.containsProperty(exactName)) {
            return index;
        }
    }

    return -1;
}
~~~

A result of **1** means the exact key exists in the first source inspected; **-1** means not found under this exact check.

### 6.1. Limitation of the Exact-Key Approach

Do not use a **-1** result to assert that an @ConfigurationProperties field definitely cannot bind. An upper-underscore env var can be mapped from a canonical key by Spring Boot Binder via its own mechanism.

If the goal is **which source binds the canonical property**, use ConfigurationPropertySources as shown in the next section.

### 6.2. Do Not Scan Every Property Name

To inspect an allowed key, **check only that key**. Do not iterate all keys of systemEnvironment, systemProperties, or enumerable sources and print them to logs.

Even without printing values, a list of variable names can reveal providers, customers, secret names, internal services, or deployment topology.

---

## 7. ConfigurationPropertySource: A Closer View to Binder

Spring Boot provides:

~~~java
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.boot.context.properties.source.ConfigurationProperty;
~~~

**ConfigurationPropertySources.from(...)** can create adapters from existing Spring PropertySources, letting you check keys in ConfigurationPropertyName form.

Example observing presence only:

~~~java
import org.springframework.boot.context.properties.source.ConfigurationProperty;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.ConfigurableEnvironment;

public final class CanonicalPropertyProbe {

    public static int firstMatchingSource(
            ConfigurableEnvironment environment,
            String canonicalProperty) {

        ConfigurationPropertyName name =
                ConfigurationPropertyName.of(canonicalProperty);

        int position = 0;

        for (ConfigurationPropertySource source :
                ConfigurationPropertySources.from(
                    environment.getPropertySources())) {

            position++;

            ConfigurationProperty property = source.get(name);

            if (property != null) {
                // Return only source position; never print property.
                return position;
            }
        }

        return -1;
    }
}
~~~

Example call:

~~~java
int position = CanonicalPropertyProbe.firstMatchingSource(
        environment,
        "app.gateway.read-timeout"
);

System.out.println("source-position=" + position);
~~~

What gets printed is **an integer**, not the property value.

### 7.1. Why Use from(...) Instead of get(environment)?

**ConfigurationPropertySources.get(environment)** returns sources already **attached** to Environment. It can throw an error if the environment does not have the corresponding support attached yet.

**ConfigurationPropertySources.from(environment.getPropertySources())** creates an adapter over the current list, suitable for a read-only helper given a ConfigurableEnvironment. In a standard Spring Boot app, Binder also has other integration paths matching context lifecycle.

### 7.2. Canonical Name Must Be Formed Properly

Canonical examples:

~~~text
app.gateway.read-timeout
spring.datasource.hikari.maximum-pool-size
app.clients[0].name
~~~

Do not pass an arbitrary upper-underscore env name into ConfigurationPropertyName.of(...) expecting it to be treated like a canonical path. Choose the bean's exact **logical property path**.

### 7.3. Reading ConfigurationProperty Still Reads the Value Object in Memory

Calling **source.get(name)** returns a ConfigurationProperty, which can hold the value. The example above **does not print or store** the value, only checking non-null.

If organizational policy forbids even accessing secrets in an unauthorized module, enforce an allowlist and helper permissions. Do not expose an open endpoint letting users pass arbitrary keys for lookup.

---

## 8. Inspecting Configuration Origin

**Origin** is metadata describing where a property came from: it can be a resource, file line/column, environment source, or specific information provided by a PropertySource.

In Spring Boot, relevant APIs include:

~~~java
org.springframework.boot.origin.Origin
org.springframework.boot.origin.OriginLookup
org.springframework.boot.context.properties.source.ConfigurationProperty
~~~

Given a ConfigurationProperty:

~~~java
Origin origin = property.getOrigin();
~~~

Origin can be null when the source does not support origin tracking.

### 8.1. Do Not Confuse Origin with Value

Descriptive example:

~~~text
logical property: app.gateway.timeout
source category:  CONFIG_DATA
origin available: true
value:            [HIDDEN]
~~~

Origin can tell you the file and line of the value, yet file/line info is not the value itself.

### 8.2. Origin Metadata Is Not Always Present

A YAML/properties file loaded by Spring Boot's Config Data loader usually has origin tracking.

A MapPropertySource constructed manually from Map.of may not supply detailed origin.

A library's custom source may have only a source name, without file or line number.

**If property.getOrigin() is null, report "origin unavailable"; do not fabricate a fake path.**

### 8.3. Warning About origin.toString()

A line like:

~~~java
System.out.println(property.getOrigin());
~~~

can print resource paths or deployment layout information. It does not necessarily print secret values, yet can still leak folder/usernames or URIs containing sensitive segments.

In production, prefer **originAvailable=true/false** or a normalized label. Only view detailed origins in authenticated, audited diagnostic tooling with redaction rules for paths/URIs.

---

## 9. Safe Helper: Report Only Source Category and Origin Availability

A helper that returns no property value:

~~~java
package example.diagnostics;

import org.springframework.boot.context.properties.source.ConfigurationProperty;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.ConfigurableEnvironment;

public final class SafeConfigProbe {

    public record SourceFinding(
            boolean found,
            int sourcePosition,
            String sourceType,
            boolean originAvailable
    ) {}

    public static SourceFinding inspect(
            ConfigurableEnvironment environment,
            String canonicalName) {

        ConfigurationPropertyName name =
                ConfigurationPropertyName.of(canonicalName);

        int position = 0;

        for (ConfigurationPropertySource source :
                ConfigurationPropertySources.from(
                    environment.getPropertySources())) {

            position++;

            ConfigurationProperty property = source.get(name);

            if (property != null) {
                // Do not call property.getValue(), property.toString(),
                // or property.getOrigin().toString().
                return new SourceFinding(
                    true,
                    position,
                    source.getClass().getSimpleName(),
                    property.getOrigin() != null
                );
            }
        }

        return new SourceFinding(
            false,
            -1,
            "NONE",
            false
        );
    }

    private SafeConfigProbe() {}
}
~~~

Usage with a **key allowlist**:

~~~java
var finding = SafeConfigProbe.inspect(
        environment,
        "app.gateway.timeout"
);

logger.info(
        "gateway timeout config: found={}, sourcePosition={}, " +
        "originAvailable={}",
        finding.found(),
        finding.sourcePosition(),
        finding.originAvailable()
);
~~~

**Do not pass canonicalName from an untrusted request into loggers or allow querying arbitrary keys.** For production APIs, build a registry of **non-sensitive** properties permitted for inspection.

### 9.1. Why Not Log the Whole SourceFinding?

The record in the example contains only booleans, a number, and a class simple name, so it is safer than a record holding values. Even so, good practice is logging **only the fields truly needed**, rather than calling toString on every diagnostic object out of habit.

### 9.2. Source Position Is Not a Stable Identifier

Source position = 3 today can become 4 after a library adds a PropertySource. It is useful for a single observation, not a business identifier to store permanently.

If a stable category is needed, translate source names into safe internal labels through a controlled mapping.

### 9.3. Do Not Promise a Complete "Binder Trace"

A Binder binding Lists, Maps, placeholders, aliases, or nested objects can look up multiple properties and perform conversions. This helper checks only **one canonical property** across the adapted sources in order.

It is an orienting tool, not a log of every internal Binder step or every property forming the final object.

---

## 10. OriginLookup with Underlying PropertySources

Besides ConfigurationProperty.getOrigin(), Spring Boot provides **OriginLookup**. Some PropertySources can report origin from a key.

Concept:

~~~java
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;
import org.springframework.core.env.PropertySource;

Origin origin =
        OriginLookup.getOrigin(source, "app.gateway.timeout");
~~~

For a source supporting OriginLookup, the result can be an Origin. If unsupported, it can return null.

### 10.1. Caveat About Keys and Relaxed Binding

**OriginLookup on a raw PropertySource** may require the key in the exact form stored by that source. It is not guaranteed to locate origin from every Binder alias automatically.

If analyzing @ConfigurationProperties, using **ConfigurationPropertySources.from(...)** and **ConfigurationProperty.getOrigin()** is usually closer to canonical binding.

### 10.2. Origin Is Not Necessarily file:line

Sources can be:

- Config Data from a classpath resource.
- File outside the JAR.
- Environment variable.
- Configuration tree.
- Library-supplied source.
- A source with unknown origin.

Therefore do not design a diagnostic API requiring mandatory **path** and **line** fields. Use **originAvailable** and an optional metadata type.

### 10.3. Do Not Copy Origin Metadata Blindly to Logs

Even if it is just a file path, an origin can contain usernames, tenants, directory structure, URLs, or data accidentally placed in a source name.

If storing origin for investigation is needed, restrict retention scope and apply a sanitizer based on a **safe resource allowlist**, not a regex masking words like password/token.

---

## 11. Actuator: What Are env and configprops Used For?

When appropriate Spring Boot Actuator is present, two helpful endpoints are:

- **/actuator/env**: inspect information about PropertySources and properties in ConfigurableEnvironment.
- **/actuator/configprops**: inspect @ConfigurationProperties beans and bound configuration info within the scope provided by the endpoint.

Spring Boot documentation treats these as tools to understand why a property has a particular value.

### 11.1. Values Are Masked by Default

In current Spring Boot lines, **env**, **configprops**, and certain other endpoints have a **sanitization** mechanism. By default, values can be replaced with a masked representation such as:

~~~text
******
~~~

This is an important feature, yet it should not be taken to mean the endpoint can be exposed publicly to everyone: property names, source lists, and metadata can still leak infrastructure details.

### 11.2. Do Not Set show-values=always Just to Debug

Dangerous configuration in many contexts:

~~~properties
management.endpoint.env.show-values=always
management.endpoint.configprops.show-values=always
~~~

Depending on version and SanitizingFunction, this can expose many unmasked values to anyone able to reach the endpoint.

**Do not use in production** merely to solve a timeout or profile issue. The risk of exposing passwords and tokens outweighs the convenience.

### 11.3. How to Keep Values Masked

Explicit safety-oriented configuration:

~~~properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

This configuration leans toward safety: inspect metadata without revealing raw values via these two endpoints.

**Note:** access/endpoint availability syntax changes across Boot versions; verify your application's settings. Even with show-values=never, continue restricting access/exposure of env and configprops.

### 11.4. when-authorized Still Requires Careful Assessment

Spring Boot supports **when-authorized** mode for certain endpoints. That mode can display real values to users considered authorized under security/roles configuration.

Illustrative example for env:

~~~properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=admin
~~~

**This is not a recommended default for secret-free diagnostics.** Once authorized, many values can become visible; evaluate data policy and the trust level of that role.

If the goal is merely determining "which source is winning," keeping **never** is a safer fit.

---

## 12. Do Not Expose /actuator/env or /actuator/configprops Publicly

In many Spring Boot setups, only health is exposed over HTTP by default; sensitive endpoints must be explicitly enabled per governance policy.

Do not deploy:

~~~properties
management.endpoints.web.exposure.include=*
~~~

assuming value masking makes everything harmless. Other endpoints can expose bean details, mappings, logs, or environment information.

If env/configprops are truly needed in a diagnostic environment:

- Prefer a separate management port, private network, and firewall.
- Configure appropriate Spring Security/authorization.
- Expose only required endpoints for the required time window.
- Keep show-values=never.
- Maintain access logs and auditing for diagnostic queries.
- Do not put management tokens in shared scripts or tickets.
- Remove exposure afterward if it was enabled temporarily.
- Review metadata risks, not only values.

### 12.1. Narrow Scope Pattern

If the environment already has real administrative protection layers and policy permits:

~~~properties
management.endpoints.web.exposure.include=health,info,env,configprops
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

This example only **lists exposed endpoints**; it omits firewall/authentication setup. **Do not copy verbatim into public production** without access controls.

### 12.2. JMX Is Also an Access Surface

Do not focus only on HTTP. Management endpoints can also exist via JMX depending on configuration, and show-values/authorization policies differ from HTTP.

If the system does not need JMX management, check the corresponding exposure. Never open remote JMX without authentication, network isolation, and proper logging.

---

## 13. Inspect One Property Instead of Exporting the Whole Environment

When tracing a specific key, a narrow query is usually better than listing every property.

Default endpoint URL example:

~~~text
/actuator/env/app.gateway.timeout
~~~

The endpoint can provide information about the property and related sources, in the format specific to the Boot version, with values subject to sanitization.

Before using, confirm:

- The endpoint is exposed and secured.
- show-values stays at **never**.
- The chosen property name is safe to appear in URLs/access logs.
- The query contains no secret value or token.
- Viewers are permitted to see metadata such as source names and origins.

### 13.1. Query URLs Can Also Be Logged

If someone puts a secret into a path/query parameter, web servers/proxies can log the URL. Never use an endpoint query as a way to pass passwords/tokens directly.

Only pass key names from an allowlist; never pass values.

### 13.2. Be Careful When Copying JSON into Tickets

Even when values are masked, responses can contain key names, resource names, profiles, or file paths. Before pasting into a ticketing system, filter down to just the needed fields and remove metadata outside the investigation scope.

Do not paste an entire /actuator/env JSON into a public chat or repository issue merely because values appear as ******.

---

## 14. /actuator/configprops and Its Limitations

/actuator/configprops helps inspect configuration bound to @ConfigurationProperties beans.

Example record:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        Duration timeout,
        String apiKey
) {}
~~~

The endpoint can assist diagnosing beans and related inputs, though sanitization and version-specific formatting must be accounted for.

### 14.1. Do Not Equate Environment with Bound Objects

A property can exist in Environment yet:

- The @ConfigurationProperties bean was not registered.
- The bean's prefix does not match.
- The data type could not be converted.
- A nested object was not created.
- Validation rejected the object.
- The bean was created before a new source was added.
- A @ConditionalOnProperty prevented the bean from existing.

Thus /actuator/env answers questions about Environment; /actuator/configprops helps inspect **binding for configuration beans**.

### 14.2. Do Not Print record.toString()

Records auto-generate toString containing component values. A record with apiKey or password can print that information verbatim:

~~~java
// AVOID:
log.info("GatewayProperties={}", gatewayProperties);
~~~

If you only need to confirm the bean exists:

~~~java
log.info("GatewayProperties loaded");
~~~

If you want to know whether a property is present, compute a boolean status that reveals no content, and log it only when allowed for observation.

### 14.3. Actuator Masking Does Not Protect Everywhere

Even with Actuator show-values=never, debug code printing gatewayProperties, custom exceptions, or tracing interceptors can still leak secrets.

Treat log protection and management API protection as **two independent control layers**.

---

## 15. Origin Metadata from YAML/Properties

With file:

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 12s
~~~

Spring Boot can retain source origin metadata, such as resource and text position.

Conceptual info example:

~~~text
property: app.gateway.timeout
source: config data resource
origin: resource location / line information
value: hidden
~~~

**Not every PropertySource has equivalent origin.** Files read by Spring Boot's Config Data loader have different tracking capabilities than a manually created MapPropertySource.

### 15.1. When an Imported File Overrides the Base File

application.yml:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway-extra.yml"
~~~

If the import provides an overlapping key, the winning source can come from the imported file. Origin helps pinpoint the actual resource, yet you must simultaneously check **precedence**.

A file having a valid origin does not mean it is the winning source if a higher CLI/system property exists.

### 15.2. File Names Can Be Sensitive Data

A path like:

~~~text
/home/<user>/secrets/customer-alpha/application.yml
~~~

reveals filesystem structure or tenants. In production logs, normalize to a label such as **CONFIG_DATA_EXTERNAL** instead of printing the raw path.

---

## 16. Environment Variables: Name May Look Right While Exact Key Is Missing

Canonical property:

~~~text
app.gateway.read-timeout
~~~

Standard env name:

~~~text
APP_GATEWAY_READTIMEOUT
~~~

Rules Spring Boot applies when mapping canonical keys to env names:

1. Replace dots with underscores.
2. Remove dashes.
3. Convert to uppercase.

A common mistake is setting:

~~~text
APP_GATEWAY_READ_TIMEOUT
~~~

and expecting Binder to treat it identically to **app.gateway.read-timeout** in every scenario. That naming is not the standard conversion of the canonical key above.

### 16.1. Never Dump System.getenv()

Statement:

~~~java
System.getenv().forEach(
        (key, value) -> log.info("{}={}", key, value)
);
~~~

can expose all secrets injected into the container.

Even:

~~~bash
printenv
~~~

or:

~~~bash
env
~~~

when run in a debug session whose output is saved to a transcript carries secret-leak risk.

Instead, verify whether **a known variable name** exists at a controlled point without printing its value:

~~~java
boolean present =
        System.getenv().containsKey("APP_GATEWAY_READTIMEOUT");
~~~

### 16.2. Do Not Infer Environment State Just Because System.getenv Has a Variable

Binder might read a higher-precedence source, or the environment source may be adapted under specific rules. An env var being present does not prove it is the final value.

Check PropertySource order and the canonical key in Environment.

### 16.3. Manage Secret Variable Names

Even a variable name like **TENANT_X_SECRET_KEY** can reveal tenant names or credential types. Therefore do not export a list of all env keys.

---

## 17. JVM Properties and Command-Line Arguments

An application can be launched with:

~~~bash
java -Dapp.gateway.timeout=9s -jar demo.jar \
  --app.gateway.timeout=11s
~~~

JVM properties typically reside in systemProperties, CLI in commandLineArgs.

If diagnostics show the command-line source winning, there is no need to print all arguments.

### 17.1. Why Not Print argv?

Command-line arguments can contain:

~~~text
--app.external.api-key=...
--spring.datasource.password=...
~~~

Printing raw **ApplicationArguments** or the argument list can leak tokens.

Even command lines can be observed by OS process-management tools depending on the platform. Best practice is **not passing raw secrets via CLI** when the platform provides safer mechanisms.

### 17.2. Log Only the Source of Allowed Keys

For example:

~~~text
app.gateway.timeout: winner=CLI
~~~

helps when diagnosing timeout. There is no need for:

~~~text
app.gateway.timeout: value=11s
~~~

For secrets, even the key name may need to be hidden or mapped to a non-disclosing identifier.

---

## 18. PropertySource Priority and Binder Precedence

Some issues occur when operators see two values in two files without understanding why one is selected.

For example:

~~~yaml
# application.yml
app:
  gateway:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 10s
~~~

When the prod profile is active, profile-specific config data can override the base file.

If an env var, system property, or CLI argument is also present, that source can override further depending on order.

### 18.1. No Need to Log Raw Values

A safe report:

~~~text
propertyGroup=GATEWAY_TIMEOUT
profileActivated=true
winningSourceCategory=CLI
originAvailable=false
valuePrinted=false
~~~

This report narrows the investigation from the profile file to startup arguments without containing any value.

### 18.2. Origin in the Base File Does Not Prove the Base File Is Used

A key can exist in application.yml yet be overridden by application-prod.yml. If you only read the origin of the base file you already know about, you do not yet know the final value.

Identify **the winning source first**, then inspect the origin of that exact source.

---

## 19. Lists and Maps: Diagnose Structure, Not Just One Key

For a List:

~~~yaml
app:
  clients:
    - name: primary
      timeout: 3s
    - name: backup
      timeout: 5s
~~~

Logical properties:

~~~text
app.clients[0].name
app.clients[0].timeout
app.clients[1].name
app.clients[1].timeout
~~~

If another profile defines a List with only index 0, Spring Boot typically uses the List from the higher-precedence source instead of merging elements from both sources.

### 19.1. Do Not Inspect Only app.clients[0].name

A List can have elements missing fields or a changed element count. To diagnose, find out:

- How many elements does the final List have?
- Which source provides the indexes?
- Did a List from a higher profile replace the base List?
- Do element constraints report validation errors?

You do not need to print real server names or endpoints to logs to learn the element count or validation status.

### 19.2. Maps Combine Keys Differently from Lists

For a Map:

~~~yaml
app:
  labels:
    owner: platform
    region: global
~~~

when a higher-precedence source declares a different region, a Map can combine keys while overlapping keys follow precedence.

To diagnose a Map, check the structure and sources of **permitted keys**, avoiding enumerating all keys since keys can hold customer IDs or secret names.

### 19.3. Each Element Can Have a Different Origin

Do not report:

~~~text
app.clients -> origin=application-prod.yml
~~~

and assert the entire object came from a single file in all cases. With nested Maps, placeholders, or multiple sources, fields can be resolved from different sources.

---

## 20. Placeholders and Final Values

A property can be defined with a placeholder:

~~~properties
app.gateway.timeout=5s
app.gateway.endpoint=https://example.test
~~~

Or an application config can reference another property via Spring's placeholder mechanism.

In that case:

- The origin of the declared key may point to the line containing the placeholder.
- The resolved value may pull data from another key subject to its own precedence.
- A final Binder object may hold the already-converted value.

**Do not treat one line's origin as a complete list of all sources affecting the final value.**

### 20.1. Secrets Can Live Inside Placeholders

If an endpoint is built from username/password or a token, printing the final URL can leak credentials even when the key name `endpoint` does not contain the word `password`.

Therefore the rule "only mask keys containing password/token" is insufficient. Never print any raw value in default diagnostics.

### 20.2. Do Not Invoke Resolver Just to Log Values

A diagnostic helper can accidentally call getProperty and pass the result into String.format. Avoid:

~~~java
log.debug(
    "resolved property={}",
    environment.getProperty(key)
);
~~~

Replace with status:

~~~java
boolean configured =
        environment.containsProperty(allowedKey);
log.debug("configured={}", configured);
~~~

And explicitly note that containsProperty only answers presence under the Environment API, not proof that all constraints or binding succeeded.

---

## 21. Reading Binding Errors Without Copying Rejected Values

Spring Boot can report conversion or Bean Validation errors when data is invalid.

Example:

~~~properties
app.gateway.pool.max-connections=abc
~~~

while Java requires int. Conversion failure can occur before validation.

If the value were a secret instead of **abc**, a carelessly configured error or custom exception could emit the rejected value into output.

### 21.1. Never Throw Custom Exceptions Containing Raw Config

Avoid:

~~~java
throw new IllegalArgumentException(
        "Invalid property " + key + "=" + value
);
~~~

A safer approach:

~~~java
throw new IllegalArgumentException(
        "Invalid configuration for gateway pool size"
);
~~~

If technical details are needed, record an error code, an allowlisted property path, and the error category. Never put passwords/tokens into messages.

### 21.2. Root Cause Is More Useful Than Dumping Data

When seeing a failure, classify it under:

- Source lacks key.
- Wrong property name.
- Profile/import not loaded.
- Unexpected source precedence.
- Conversion failure.
- Constructor binding failure.
- Validation failure.
- Bean registration/condition failure.

You can identify the failure category without logging raw values.

### 21.3. Validation Does Not Replace Sanitization

A @NotBlank on password checks whether a password exists, yet does not guarantee exception logs mask the password. Sanitization is an independent responsibility.

---

## 22. Why Logging at TRACE/DEBUG Can Be Dangerous

When hitting a tough bug, operators are tempted to enable extremely verbose logging for Spring Boot Binder, Environment, Config Data, or HTTP clients.

Some loggers can emit more information than expected, especially if application code or custom libraries log Maps/values themselves.

Do not set:

~~~properties
logging.level.root=TRACE
~~~

across all of production just to locate a single property.

### 22.1. Replace with Narrow Diagnostics

A lower-risk path:

1. Identify the canonical key.
2. Use an allowlist helper reporting the first source.
3. Check active profiles and source-type list.
4. Test conversion/validation in an isolated test.
5. Enable targeted logging in a controlled environment only when the steps above are insufficient.
6. Set a time limit to disable debug and a log deletion policy if sensitive data is emitted.

### 22.2. Debug Mode Does Not Automatically Mean Safe

Enabling Spring Boot debug can help inspect condition evaluation and certain startup details. However, do not assume every library and custom logger redacts secrets.

Inspect the exact loggers enabled, message patterns, and appenders before applying.

---

## 23. Log Configuration Data Using an Allowlist, Not a Blacklist

A blacklist like:

~~~text
If key contains password, token, secret -> mask.
Otherwise print normally.
~~~

has many flaws:

- Secrets can be named **credential**, **auth**, **access**, **private**, **client-key**, or an arbitrary name.
- A URL can contain username/password even if the key is named **endpoint**.
- A JSON structure can embed tokens inside.
- Maps can have dynamic keys.
- Secrets can live in Strings with non-suggestive names.

**Safer:** diagnostics have a small set of logical properties permitted for inspection, and print no values by default.

### 23.1. Allowlist Example

~~~java
public enum DiagnosticKey {
    GATEWAY_TIMEOUT("app.gateway.timeout"),
    GATEWAY_POOL_SIZE("app.gateway.pool.max-connections"),
    FEATURE_AUDIT("app.audit.enabled");

    private final String canonicalName;

    DiagnosticKey(String canonicalName) {
        this.canonicalName = canonicalName;
    }

    public String canonicalName() {
        return canonicalName;
    }
}
~~~

An API using the enum:

~~~java
SourceFinding inspect(
        ConfigurableEnvironment environment,
        DiagnosticKey key) {

    return SafeConfigProbe.inspect(
        environment,
        key.canonicalName()
    );
}
~~~

This prevents callers from passing an arbitrary String like **spring.datasource.password** when the public method accepts only the reviewed enum.

### 23.2. Do Not Expose an Endpoint Returning the Entire Enum Unnecessarily

Even the list of keys permitted for inspection can reveal module structure. Apply authorization and provide only the information groups needed by authorized roles.

---

## 24. Observing Sources Intentionally During Application Startup

A diagnostic can run at application startup, yet does not need to emit details about every property on every production run.

A good pattern:

~~~text
On startup:
  - Log active profile category if permitted.
  - Log number of configuration sources.
  - Log load status of a few non-sensitive config groups.
  - Never print raw config values.
  - Never list all env variable names.
~~~

If an incident-support command is needed, provide a secured, audited internal query mechanism instead of dumping all metadata into permanent logs.

### 24.1. Do Not Auto-Log Origin Paths on Every Run

Paths and source URIs can differ across developer machines, CI, and production; logging them continuously can expose infrastructure layout.

You can log a high-level label such as:

~~~text
winnerCategory=CONFIG_DATA
~~~

once the category is safely determined.

---

## 25. Spring Profiles: Inspectable Metadata

When an environment behaves incorrectly, active profiles are usually the first thing to check.

In ConfigurableEnvironment:

~~~java
String[] profiles =
        environment.getActiveProfiles();
~~~

If logging policy allows, you can record the count of active profiles or standardized names like local/test/prod.

### 25.1. Profile Names Can Be Sensitive

Some organizations embed environment, customer, or project names in profile names. Therefore do not print all of getActiveProfiles() to production logs by default.

If you only need to confirm prod:

~~~java
boolean prod =
        environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("prod")
        );
~~~

Then log:

~~~text
productionProfileActive=true
~~~

A boolean state is often enough for the question at hand.

### 25.2. Default Profiles

When no profile is active, Spring Boot can apply default profiles and their corresponding documents.

Do not assume an empty getActiveProfiles() means no Config Data was loaded. Understand default profiles and actual sources.

---

## 26. Difference Between "Present in File" and "Bound"

A file having:

~~~yaml
app:
  gateway:
    timeout: 5s
~~~

does not guarantee:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

will receive timeout, because the prefix differs.

Likewise, an unregistered bean has no configuration object to read.

### 26.1. Layer-by-Layer Diagnosis

~~~text
Layer 1: Was file/location/profile loaded?
Layer 2: Does PropertySource have the canonical key?
Layer 3: Which source has highest precedence?
Layer 4: Can Binder convert type / nested object?
Layer 5: Is @ConfigurationProperties bean registered?
Layer 6: Does validation allow the bean to exist?
Layer 7: Does the service use the right bean and component?
~~~

Never use an Environment dump in place of distinguishing these seven layers.

### 26.2. If Actuator env Sees the Key but configprops Does Not

The root cause can lie in prefix, bean registration, conditional creation, conversion, or validation. Not necessarily a skipped source.

---

## 27. Safe Conversion Diagnostics

Suppose:

~~~text
app.gateway.timeout = not-a-duration
~~~

If this value came from a real environment and might contain a secret, do not print the raw value when conversion fails.

A Binder test can reproduce it with **mock data**:

~~~java
Map<String, Object> testValues = Map.of(
        "app.gateway.timeout", "not-a-duration"
);

Binder testBinder = new Binder(
        new MapConfigurationPropertySource(testValues)
);
~~~

Then assert the appropriate conversion error.

### 27.1. No Need to Copy Production Data into Unit Tests

If the failure is caused by a string that cannot convert to Duration, use a dummy input of the same error category. Never put real URLs/tokens/passwords into test fixtures just to reproduce.

### 27.2. Tests with Dummy Data Are Easier to Share

Test suites and code reviews are visible to many team members. Replacing real values with mock data prevents leaking secrets through repositories, CI logs, or artifacts.

---

## 28. Testing Helpers Without Leaking Secrets

A unit test for SafeConfigProbe can use a test source containing a dummy secret:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class SafeConfigProbeTest {

    @Test
    void reportsSourcePositionWithoutReturningValue() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
            new MapPropertySource(
                "unitTestSource",
                Map.of(
                    "app.gateway.timeout", "5s",
                    "app.gateway.api-key", "dummy-secret-do-not-log"
                )
            )
        );

        var finding = SafeConfigProbe.inspect(
            env,
            "app.gateway.timeout"
        );

        assertThat(finding.found()).isTrue();
        assertThat(finding.sourcePosition()).isPositive();
        assertThat(finding.originAvailable()).isFalse();
    }
}
~~~

This test verifies only the returned metadata. It does not try to assert the timeout value, because the helper's purpose is not exposing values.

### 28.1. Test Output Redaction

You can add a test capturing logs while running a full diagnostic path, then assert the log **does not contain** the mock string:

~~~text
dummy-secret-do-not-log
~~~

Never use a real secret as the sentinel. The test must verify the relevant loggers/appenders are properly captured, because "absent from one log" does not prove all other logging systems are safe.

### 28.2. Test Keys Outside the Allowlist

If the diagnostic API accepts an enum or registry, verify callers cannot request an unapproved secret key. That tests access/API design, distinct from testing source position.

### 28.3. Do Not Enable Uncontrolled Debug in Tests

A test framework can print Environment or context automatically when startup fails. If fixtures contain raw dummy secrets, verify test reports do not dump full exceptions or source Maps.

---

## 29. Not Exposing Secrets via Actuator in Tests

A security test can boot the context with Actuator and verify:

- env and configprops are not exposed unexpectedly.
- When exposed in a dedicated test environment, access policies work.
- show-values=never actually masks values.
- Unauthorized callers cannot view sensitive metadata.
- Endpoints do not emit a mock secret in HTTP responses.

### 29.1. Test Both Response and Access Control

A test only looking for `******` is insufficient to declare an endpoint safe. If the endpoint still exposes all key names/source names publicly, metadata risks remain.

A test only asserting HTTP 401 is also insufficient if another security rule in production unintentionally permits access. Verify the actual security configuration and real build/deploy sources.

### 29.2. Do Not Infer JMX Is Safe from HTTP Tests

An application can expose Actuator over multiple technologies. If the organization uses remote JMX, test security on that channel separately.

---

## 30. Risks in Log Aggregation and Observability Pipelines

Even if console logs look temporary, a production app may ship logs to:

- Container runtime.
- Kubernetes logging agents.
- Central logging systems.
- SIEM or audit stores.
- APM/tracing collectors.
- Operations support tools and chatops.
- Ticketing systems or screenshots.

Once a raw secret is logged, it can persist longer than intended and be replicated across many channels.

### 30.1. Layered Prevention

**Layer 1:** Never put secrets into logs from source code.

**Layer 2:** Use allowlisted diagnostics; never dump Maps/Environment.

**Layer 3:** Apply redaction in the logging pipeline if available.

**Layer 4:** Restrict log viewing permissions and retention.

**Layer 5:** When exposure is detected, follow credential revocation/rotation and incident-response procedures.

**Never treat Layer 3 as a substitute for Layer 1.** Pattern-based redaction can miss data lacking secret-like labels.

### 30.2. Terminal Commands Carry Risks Too

Do not run and copy raw output of:

~~~bash
printenv
env
java -XX:+PrintFlagsFinal ...
~~~

just to check a timeout. For commands that display configuration or process arguments, verify scope and sharing policies.

---

## 31. "Safe to Print" Information Must Be Context-Defined

One API may treat timeout as non-sensitive, yet the timeout's source name contains a file path with a customer ID. Another system may treat even feature flag names as non-public internal info.

Therefore do not build a "safe" helper merely because it avoids calling getValue(). You must:

1. Identify who views diagnostics.
2. Define which properties may be queried.
3. Define which metadata may be returned.
4. Normalize source names/paths.
5. Secure endpoints/access.
6. Enforce auditing and retention limits.
7. Test for leaks with mock data.

**Security is a property of the entire data flow, not just a single Java method.**

---

## 32. A Runbook for "Wrong Value"

Suppose a service uses an unexpected timeout.

### Step 1. Narrow down the canonical key

For example:

~~~text
app.gateway.read-timeout
~~~

Ensure the @ConfigurationProperties prefix and Java component name match.

### Step 2. Verify the bean exists

Check registration: @ConfigurationPropertiesScan, @EnableConfigurationProperties, or another valid method. Do not print the whole bean/toString.

### Step 3. Identify profiles and configuration sources

Inspect active profiles at safe metadata granularity and which source types are present.

### Step 4. Find the winning source for the canonical key

Use a helper based on ConfigurationPropertySources, returning only source position/category and originAvailable.

### Step 5. If the winning source is CLI

Check the startup pipeline that supplied an unexpected override, without printing all of argv or arguments containing secrets.

### Step 6. If the winning source is OS_ENV

Check canonical env naming, injection policy, and deployment version. Do not dump env.

### Step 7. If the winning source is CONFIG_DATA

Inspect profile/import/location and origin metadata through a secured channel. Do not paste file paths containing tenant/user info into tickets unless permitted.

### Step 8. If Binder/bean still differs

Check conversion, nested property path, List/Map, validation, or custom converters. Use tests with dummy data to reproduce.

### Step 9. Confirm the result after changes

Re-check source position and bean status, verifying values only via an appropriately authorized test rather than dumping to logs.

### Step 10. Close temporary diagnostic access

Turn off elevated logging, remove temporary exposure if any, store sanitized reports, and verify no raw secrets remain in artifacts.

---

## 33. Runbook: "Property Not Picked Up from Env"

Symptom: operator sets an environment variable, yet the bean still uses its default.

Common causes:

- Env name violates canonical conversion rules.
- Variable was not passed into the running process/container.
- Container is running an old deployment version.
- A higher CLI or system property overrides it.
- Wrong @ConfigurationProperties prefix.
- Bean not registered or conversion failure.
- Config was read before the source changed.
- Test overrides mask the env value.

### 33.1. Investigating Without Leaking Secrets

Instead of printing env values, confirm:

~~~text
expectedNamePresent=true/false
canonicalKeyFound=true/false
winningSourceCategory=...
activeProfileCategory=...
beanBound=true/false
~~~

If the key is secret, do not log the specific key name; use an approved group code.

### 33.2. Once the Winning Source Is Known

If the winning source is not env, focus on precedence. If the winning source is env yet the bean is still wrong, focus on conversion, property name adaptation, bean registration, and lifecycle.

---

## 34. Runbook: "Actuator Reports One Source, Bean Gets Another Value"

Several possibilities:

1. Bean was created before a dynamic source was added.
2. Bean bound a snapshot, and Environment was later modified.
3. A bean property came from a different key or alias.
4. Placeholder/conversion caused the value to differ from raw text.
5. Configprops returns bean-level metadata not equivalent to querying one raw key.
6. Bean is an immutable record and is not automatically rebound.
7. Custom binder/handler/default logic exists.
8. A collection merged/replaced differently than expected.

### 34.1. Do Not Assume Automatic Refresh

Environment currently holding a new value does not mean already-created beans were updated.

If the application requires refresh, there must be a proper rebind/reconstruction mechanism and tests confirming it, not merely mutating a PropertySource.

### 34.2. Diagnose with Tests Instead of Live Logs

If the cause is List replacement or conversion, a Binder/ApplicationContextRunner test with mock data usually suffices to reproduce. No need to turn on show-values=always in production.

---

## 35. Diagnosing Config Tree and Mounted Secrets

In containers/Kubernetes, configuration can be mounted onto the filesystem and loaded via configtree:

~~~properties
spring.config.import=optional:configtree:/etc/config/
~~~

Values can come from files where the filename is the property name.

### 35.1. Do Not Print File Contents

Never read and log directory contents just to check whether a source loaded. Files in configtree can contain secrets.

You can check source presence/origin via metadata, though mount paths can also be sensitive. Use labels like **CONFIG_TREE_SOURCE** instead of printing raw paths.

### 35.2. Filesystem Permissions Still Matter

Spring Boot being able to bind a secret does not mean every diagnostic endpoint may display metadata about it. Do not allow arbitrary APIs to list configtree filenames/paths beyond the viewer's authorization.

### 35.3. Source Presence Does Not Guarantee Final Value Comes from It

A system property or CLI argument can override a key loaded by configtree. Diagnose by precedence, not solely file presence.

---

## 36. Diagnosing via Classification Results, Not String Values

An ideal diagnostic output can be a small record:

~~~java
public record ConfigDiagnosticResult(
        String diagnosticId,
        boolean configured,
        String sourceCategory,
        boolean originAvailable,
        String failureCategory
) {}
~~~

Report example:

~~~text
diagnosticId=GW_TIMEOUT
configured=true
sourceCategory=CONFIG_DATA
originAvailable=true
failureCategory=NONE
~~~

This payload contains no verbatim key, raw value, or file path. It lets operations teams share an engineering conclusion without accessing secrets.

### 36.1. Identifiers Must Not Accept Arbitrary Input

Place diagnosticId in a team-controlled enum or registry. Never use request-supplied arbitrary property names.

### 36.2. SourceCategory Should Have Only a Few Safe Values

For example:

~~~text
CLI
JVM
OS_ENV
CONFIG_DATA
DEFAULT
CUSTOM
UNKNOWN
~~~

Classification from source names/classes must be tested against your Boot version and custom sources. When uncertain, report **UNKNOWN** instead of printing the raw name.

### 36.3. Never Trust Any External Exception String as Safe

If failureCategory is pulled from exception.getMessage(), it might contain raw input. Instead, map exception/failure types to a fixed enum.

---

## 37. Example of Safe Error Classification

An enum:

~~~java
public enum ConfigFailureCategory {
    NONE,
    SOURCE_NOT_FOUND,
    VALUE_NOT_CONVERTIBLE,
    VALIDATION_FAILED,
    BEAN_NOT_REGISTERED,
    CONFIG_DATA_NOT_LOADED,
    UNKNOWN
}
~~~

Reporting:

~~~java
log.warn(
    "config diagnosticId={} failureCategory={}",
    "GW_TIMEOUT",
    ConfigFailureCategory.VALUE_NOT_CONVERTIBLE
);
~~~

Do not write:

~~~java
log.warn("Bad config: {}", exception.getMessage());
~~~

in systems where exception messages can contain secret input data.

In internal logs with protective policies and special investigative needs, stack traces may be stored after risk assessment; never assume exceptions are non-sensitive by default.

---

## 38. Diagnostic Tool Comparison Table

| Tool | Primary information | Watch out for secrets? | When appropriate |
| --- | --- | --- | --- |
| Environment.getProperty | Resolved property value | Very high | Authorized business logic, do not log |
| Environment.getPropertySources | Source list | Yes, even source names | Identify source order and types |
| PropertySource.containsProperty | Exact key presence | Limited for relaxed binding | Local probe for a single key |
| ConfigurationPropertySources.from | Sources from binder view | Do not print returned value | Controlled canonical key tracing |
| ConfigurationProperty.getOrigin | Origin metadata | File/path may be sensitive | Origin tracing in secured tooling |
| OriginLookup.getOrigin | Origin from supporting source | Depends on key/source | Tracing specific source |
| /actuator/env | PropertySources/environment | Sensitive endpoint/metadata | Authorized, sanitized inspection |
| /actuator/configprops | Configuration properties beans | Bound values may be sensitive | Inspect bound beans |
| Binder unit test | Conversion/nested binding | Use dummy data | Reproduce technical failures |
| ApplicationContextRunner | Beans/validation/conditionals | Non-real test data | Reproduce startup config behavior |
| @SpringBootTest | Config Data/profiles/integration | Never use prod secrets | Verify bootstrap/wiring |

**A tool being capable of viewing raw values does not mean the investigator should use that capability.**

---

## 39. Practice 1: List Only Source Types

Given the application's ConfigurableEnvironment.

Task: display the index and class name of PropertySources without printing getSource(), getProperty(), toString(), or raw source names.

Reference solution:

~~~java
int position = 0;

for (PropertySource<?> source :
        environment.getPropertySources()) {

    position++;

    System.out.printf(
        "%d: %s%n",
        position,
        source.getClass().getSimpleName()
    );
}
~~~

Extension: replace the class name with a safe allowlisted source category enum.

## 40. Practice 2: Canonical Property and Env Var

Given canonical key:

~~~text
app.client.read-timeout
~~~

Write the standard Spring Boot environment variable name.

Answer:

~~~text
APP_CLIENT_READTIMEOUT
~~~

Dots become underscores, dashes are removed, then uppercase. Do not insert an underscore between read and timeout.

Extension: explain why **System.getenv().containsKey("APP_CLIENT_READTIMEOUT")** confirms the variable's presence without proving it is the winning source.

## 41. Practice 3: Retrieve Only Origin Status

Given a ConfigurationProperty retrieved from an appropriate ConfigurationPropertySource.

Task: report whether origin metadata is present without printing origin.toString().

Answer:

~~~java
boolean available =
        property != null && property.getOrigin() != null;

log.debug("originAvailable={}", available);
~~~

If origin is null, never assign a guessed file path based on the source name.

## 42. Practice 4: Actuator Keeps Secrets Masked

A team wants to enable /actuator/env on an internal network to check source precedence, while passwords exist in Environment.

Question: should they set show-values=always for easier diagnostics?

**No.** Keep show-values=never, restrict exposure/access, and inspect only permitted source/key metadata. If an authorized person exceptionally needs to view a real value, follow a separate security procedure rather than changing the global policy for everyone.

## 43. Practice 5: Avoid Logging toString

Code:

~~~java
@ConfigurationProperties(prefix = "app.external")
public record ExternalProperties(
        String endpoint,
        String apiKey
) {}
~~~

Statement to avoid:

~~~java
log.info("{}", properties);
~~~

Because record.toString can contain apiKey. Replace with:

~~~java
log.info("ExternalProperties bean loaded");
~~~

If you need to know whether endpoint is configured, use a boolean presence check per contract; do not print apiKey and do not print endpoint if the URI could contain credentials.

## 44. Practice 6: Winning Source Is Not the Expected Origin

application.yml has app.gateway.timeout=5s; prod profile has 8s; CLI has --app.gateway.timeout=15s.

If a helper only finds the origin of the line in application.yml and concludes the final timeout is 5s, what is wrong?

**Precedence error.** Origin tells you where a declaration lives; it does not guarantee that declaration was chosen as the final value. Identify the highest-precedence source supplying the key before inspecting the origin of that exact declaration.

## 45. Practice 7: Reproduce an Incident Without Using Real Secrets

A deployment fails because a value meant to be a Duration was supplied in the wrong format. An operator is about to copy the entire env var set into a repository issue.

Better approach:

1. Identify the canonical key and conversion error category.
2. Create a mock input with the same error type, e.g. **not-a-duration**.
3. Write a Binder test using MapConfigurationPropertySource.
4. Confirm the conversion root cause.
5. Report the winning source category and error status without putting raw config into the issue.

## 46. Practice 8: Choose Diagnostic Scope

An internal API accepts a **key** query parameter, then calls:

~~~java
environment.getProperty(key)
~~~

and returns the raw value to the caller.

Problem: the API becomes a tool to read every property the process can access, including secrets.

Safer design:

- The API accepts a **diagnosticId** from an allowlist registry.
- Only a small set of non-sensitive keys are permitted to be checked.
- The response returns source category and status, not raw values.
- The API enforces authentication, authorization, rate limiting, and auditing.
- Source names/paths are normalized.
- If a key is not in the registry, reject it.

---

## 47. Checklist Before Inspecting Config Sources in Production

- [ ] Know the canonical property and prefix under investigation.
- [ ] Confirmed the operator is authorized to diagnose that config group.
- [ ] Never print Environment, System.getenv, or System.getProperties.
- [ ] Never dump PropertySource.getSource or PropertySource.toString.
- [ ] Never call getProperty and log raw values.
- [ ] Never log @ConfigurationProperties records containing secrets via toString.
- [ ] Inspect only allowlisted keys.
- [ ] Distinguished exact-key lookup from relaxed binding.
- [ ] Checked source precedence before inferring origin.
- [ ] Origin metadata can be null; never fabricate fake data.
- [ ] Masked or omitted sensitive resource paths.
- [ ] /actuator/env and /actuator/configprops are not publicly exposed.
- [ ] show-values kept at never when the goal is secret-free diagnostics.
- [ ] JMX management, if enabled, is also access-restricted.
- [ ] Do not enable global TRACE/DEBUG in production just to check one key.
- [ ] Never copy raw env, CLI arguments, or JSON responses into tickets.
- [ ] Tests use dummy secrets, never real credentials.
- [ ] Incident reports contain only group codes, winning source, and failure category.
- [ ] Temporary elevated permissions/logging are removed after investigation.
- [ ] If a secret leaked, trigger the appropriate incident/rotation process.

## 48. Reference Resources

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Actuator Endpoints and Sanitization: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot API — ConfigurationPropertySources: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertySources.html
- Spring Boot API — ConfigurationPropertySource: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertySource.html
- Spring Boot API — ConfigurationProperty: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/source/ConfigurationProperty.html
- Spring Boot API — OriginLookup: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/OriginLookup.html

When upgrading Spring Boot major versions, re-verify API locations, Actuator access/exposure settings, and endpoint behavior; do not rely on an old snippet to guarantee every case remains identical.

---

## 49. Summary

When a Spring Boot property has an unexpected value, what usually matters is **why it was chosen**, not printing its value.

Remember:

- **PropertySource**s are ordered; a higher source can shadow a lower source for the same property.
- **ConfigurableEnvironment** and **Binder** have related yet non-identical views, especially with relaxed binding and env names.
- **ConfigurationPropertySources.from(...)** lets you inspect canonical properties closer to how Binder handles them than simple exact-key lookup.
- **ConfigurationProperty.getOrigin()** and **OriginLookup** can provide origin metadata, though origin may be null.
- **Origin is not value**; even so, paths/URIs in origin can still be sensitive.
- **/actuator/env** and **/actuator/configprops** aid diagnostics yet must be secured; keep show-values=never when raw values are unnecessary.
- Never print **System.getenv**, **System.getProperties**, **PropertySource.getSource**, bean **toString**, or raw configuration objects.
- Never let a diagnostic endpoint query arbitrary keys; use allowlists and strict access controls.
- Separate source/precedence issues from conversion, validation, bean registration, and runtime refresh.
- When reproducing bugs, use tests with dummy values instead of copying production secrets.
- The safest diagnostics usually need only: **allowed property code, winning source, originAvailable, failure category, and bean status**.

Final principle: **"Diagnose configuration sources, do not disclose configuration data."** Good observability tells you where a property came from and why it took effect, without turning logging and operational environments into a secret store.
