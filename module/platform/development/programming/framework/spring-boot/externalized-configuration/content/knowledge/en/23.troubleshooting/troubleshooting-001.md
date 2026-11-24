# Value Tracing Workflow: Key, Source, Profile, Location, and Read Time

In Spring Boot Externalized Configuration, a value such as `app.client.timeout=2s` can be declared in multiple places: `application.yml`, `application-prod.yml`, a file outside the JAR, imported Config Data, environment variables, JVM system properties, command-line arguments, or a custom `PropertySource`. At runtime, the same key can have **multiple candidate values**, but Spring Boot only uses the value matching the **precedence order and read timing** to bind into a Java object.

A familiar incident: a developer sees `timeout: 5s` in YAML, yet the live service receives `500ms`. Or production runs the wrong profile, a configuration line is placed in the right file that was never loaded, or the file was just edited while an immutable bean still uses the old value. To diagnose systematically, avoid guessing that "Spring caches configuration" or randomly editing a file.

This lesson walks through tracing along **five axes**:

1. **Key:** which exact property is the application requesting, under which canonical name?
2. **Source:** which `PropertySource`s contain candidates, and which source has the highest precedence?
3. **Profile:** are the active/default profiles correct, and have they caused the necessary Config Data documents to be loaded?
4. **Origin/location:** which file, line, environment variable, or argument did the value come from?
5. **Time:** when does the application read/bind/copy the value into an object, and is it refreshed or not?

The examples target Spring Boot 3.x and Java 17+; terms such as `ConfigData`, `Environment`, `PropertySource`, `Binder`, `OriginLookup`, `@ConfigurationProperties`, and `Actuator` serve as the basis for applying this on real projects. Log examples, inspection commands, and reports use **non-sensitive** values only; never print passwords/tokens or the entire environment in production.

## 1. Map from Configuration File to Active Runtime Value

~~~text
Input sources
  ├── application.yml / application.properties
  ├── application-<profile>.yml
  ├── spring.config.import / file:/... / configtree:/...
  ├── OS environment: APP_CLIENT_TIMEOUT
  ├── JVM system property: -Dapp.client.timeout=...
  ├── application arguments: --app.client.timeout=...
  └── PropertySource created by application / library
                      |
                      v
       Spring Environment / Config Data
       - which profiles are active?
       - which sources are loaded?
       - what is the source precedence order?
                      |
                      v
          Property lookup / Binder
       - find exact canonical key
       - pick effective value
       - resolve placeholders
       - convert String -> Duration
                      |
                      v
      @ConfigurationProperties / @Value
       or Environment.getProperty(...)
                      |
                      v
           Bean or service consumer
       - holding startup snapshot?
       - re-reading Environment on each call?
       - refreshed/recreated or not?
~~~

Discrepancies can arise at every step:

- **Wrong key:** YAML has `app.client.time-out`, whereas the model expects `app.client.timeout`.
- **Wrong source:** the file is right, but a higher-precedence environment variable overrides it.
- **Wrong profile:** `application-prod.yml` has not been loaded because the active profile is `dev`.
- **Wrong location:** `src/main/resources/application.yml` was edited in the workspace, while the running JAR is an older build or uses an external file.
- **Wrong time:** the file changed after startup, while the bean still holds the already-bound data.
- **Wrong data type:** the value is found, but cannot be converted to the Java type.
- **Wrong consumer:** configuration is right, while the service stores a copy or applies a different default.

Do not lump every case together as "Spring is not reading config"; identify the first layer that diverges.

## 2. Ask Tracing Questions Before Making Fixes

A short note template for an engineering ticket:

~~~text
Application: order-service
Environment: staging
Key under investigation: app.client.timeout
Expected value: 5s
Observed value: 500ms
Consumer: ClientProperties.timeout()
Running profile: staging
Read type: @ConfigurationProperties (startup bind)
Expected source: application-staging.yml
Symptom: client times out early
~~~

Fields must be confirmed with factual evidence, not filled in by guesswork. For instance, if active profiles are not yet known, record "unconfirmed" rather than taking a Kubernetes environment name or Git branch as the answer.

**One key, one trace at a time:** start with one verifiable property, then expand to related keys. Do not dump the entire config to hunt down a single issue.

## 3. Axis 1 — Identify the Canonical Key

Suppose the Java model is:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

The corresponding canonical keys are:

~~~properties
app.client.timeout=2s
app.client.max-retries=3
~~~

If in YAML:

~~~yaml
app:
  client:
    timeout: 2s
    max-retries: 3
~~~

then the structure is correct. With `@ConfigurationProperties`, Spring Boot supports **relaxed binding**, allowing common spellings of a property name to map to a camelCase Java component.

However, relaxed binding does not auto-correct typos:

~~~properties
app.clinet.timeout=2s
~~~

`clinet` is not `client`. If the application has a default or does not validate the field, a misspelled key can be ignored while the bean still starts up.

### Distinguish Prefix from Field

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

The model above requires `app.client.timeout`, neither `app.timeout` nor `client.timeout`.

If the consumer uses:

~~~java
environment.getProperty("app.client.timeout")
~~~

verify the exact key. If the consumer uses `@Value`, check how the placeholder is written:

~~~java
@Value("\${app.client.timeout:2s}")
private Duration timeout;
~~~

Here `:2s` is the placeholder fallback if the property is not resolved in the applicable way; it is not evidence that the YAML source provided 2 seconds.

**Separate the property name, Java type, and consumer default** before examining precedence.

## 4. Environment Variable Naming Rules for Spring Boot

A deployment might set:

~~~text
APP_CLIENT_TIMEOUT=500ms
APP_CLIENT_MAXRETRIES=4
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8080
~~~

With canonical properties:

~~~text
app.client.timeout        -> APP_CLIENT_TIMEOUT
app.client.max-retries    -> APP_CLIENT_MAXRETRIES
spring.profiles.active    -> SPRING_PROFILES_ACTIVE
server.port               -> SERVER_PORT
~~~

Common rules when converting a canonical name to an environment variable for `@ConfigurationProperties`:

1. Replace dots `.` with underscores `_`.
2. Remove dashes `-` inside segments.
3. Convert to uppercase.
4. For list indexes, use numbers separated by underscores per Binder rules.

For example:

~~~text
app.gateways[0].timeout   -> APP_GATEWAYS_0_TIMEOUT
app.client.base-url       -> APP_CLIENT_BASEURL
~~~

Do not assume `APP_CLIENT_BASE_URL` and `APP_CLIENT_BASEURL` are completely equivalent across all read paths. `@ConfigurationProperties` and `Environment.getProperty(...)` have mapping/lookup mechanisms that are not identical in every situation; prefer the canonical form and verify with an actual test.

**Docker Compose note:** variables that only exist in a `.env` file used for Compose interpolation **are not automatically injected into the container**. Before blaming Spring, verify the variable is actually present in the process environment.

## 5. Axis 2 — Sources and Candidate Values

Spring Boot's `Environment` aggregates `PropertySource`s. One key can appear in multiple sources simultaneously.

For example:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 8s
~~~

Environment variable in the process:

~~~text
APP_CLIENT_TIMEOUT=2s
~~~

Launch command:

~~~bash
java -jar order-service.jar \
  --spring.profiles.active=prod \
  --app.client.timeout=500ms
~~~

In a typical Spring Boot application, command-line properties have higher precedence than environment variables and Config Data. Therefore, the effective property is `500ms`, even though the base file specifies `5s`, the prod file specifies `8s`, and the OS environment specifies `2s`.

Not every file containing the key is the winning source. A reasoning table:

| Source | Candidate key/value | Participates? | Conclusion |
| --- | --- | --- | --- |
| `application.yml` | `5s` | Yes | Does not win |
| `application-prod.yml` | `8s` | Yes if prod active | Does not win |
| OS environment | `APP_CLIENT_TIMEOUT=2s` | Present in process | Does not win |
| Application CLI | `--app.client.timeout=500ms` | Yes | Wins in example |

**Only after confirming a source is actually loaded** should you conclude it was overridden by a higher source. A file that has not been loaded is not a candidate.

## 6. Precedence Order — A General Mental Model

In Spring Boot, PropertySources order is typically constructed so that higher-precedence sources can override lower ones. Important groups in deployments:

- Spring Boot command-line arguments of the form `--key=value` typically have very high precedence.
- `SPRING_APPLICATION_JSON` is a source with its own position in precedence.
- JVM system properties `-Dkey=value` are typically higher than OS environment.
- OS environment is typically higher than Config Data from files.
- Config Data includes packaged, external, profile-specific, and imported files according to detailed rules.
- `@PropertySource` has its own addition order and timing, and is not the right tool to override every early-stage setting.
- Default properties supplied by the application sit at a lower fallback tier in many situations.

This is a **mental framework**, not an absolute list for every project. Test sources, servlet/JNDI, custom `EnvironmentPostProcessor`s, programmatically added `PropertySource`s, or specific starters can alter the exact order.

When a conflict occurs, **do not just memorize precedence and guess**: inspect the actual sources in `ConfigurableEnvironment` or secured Actuator information.

An important fact: a field default in a Java record/JavaBean **is not a PropertySource**. It is a fallback in object creation/binding logic, and does not compete in priority like files or OS environment.

## 7. Check the Value Spring Environment Returns

A simple way to inspect at runtime:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class TimeoutReporter {
    private final Environment environment;

    public TimeoutReporter(Environment environment) {
        this.environment = environment;
    }

    public String currentTimeout() {
        return environment.getProperty(
            "app.client.timeout", "<missing>");
    }
}
~~~

For example, the method may return `"500ms"` if the command-line source is winning. **Use this method only for non-sensitive keys.** For secrets, never log or return them via an HTTP endpoint.

To obtain a typed value:

~~~java
Duration timeout = environment.getProperty(
    "app.client.timeout",
    Duration.class
);
~~~

Spring `Environment` can convert the value to `Duration` if the corresponding conversion support is configured. The `@ConfigurationProperties` Binder has its own conversion and relaxed binding mechanisms; therefore testing via `Environment.getProperty` is useful to see the effective value, but does not replace testing the binding of a complex configuration group.

### When the Key Is Missing

~~~java
String value = environment.getProperty(
    "app.client.timeout");
~~~

If it returns `null`, the key may not exist in the sources visible via that lookup. Yet the service might still receive a timeout through a `@Value` default, `@DefaultValue`, or a field initializer. **A consumer's value does not necessarily come only from property lookup.**

## 8. Iterate Over PropertySources in Actual Order

When you need to know **which sources contain the key**, you can use `ConfigurableEnvironment`:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceInspector {
    private final ConfigurableEnvironment environment;

    public PropertySourceInspector(
        ConfigurableEnvironment environment
    ) {
        this.environment = environment;
    }

    public void inspectNamesForNonSensitiveKey() {
        String key = "app.client.timeout";
        for (PropertySource<?> source
                : environment.getPropertySources()) {
            Object rawValue = source.getProperty(key);
            if (rawValue != null) {
                System.out.println(
                    "candidate source: " + source.getName());
            }
        }
    }
}
~~~

**Important:** the example prints **only the source name**, not the value. Spring `MutablePropertySources` are iterated in the precedence order used by Environment at the time of the call. The first element that provides a value for the corresponding lookup is usually the winning source.

A practical limitation: some `PropertySource`s provide relaxed aliasing, placeholder resolution, or specific origin handling. `source.getProperty(key)` is a direct check against that source, but **is not a perfect tool for reconstructing every spelling/index/value processed by Binder**. For nested lists/maps and environment aliases, always verify the actual typed binding result.

Do not grant public endpoints permission to iterate or display all PropertySources; they can contain passwords, tokens, private keys, and internal details.

## 9. Find the Winning Source Without Exposing the Value

A diagnostic-style helper can stop at the first source providing a non-sensitive key:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertyDiagnostics {
    private PropertyDiagnostics() {}

    public static String firstCandidateSourceName(
        ConfigurableEnvironment env,
        String key
    ) {
        for (PropertySource<?> source : env.getPropertySources()) {
            if (source.getProperty(key) != null) {
                return source.getName();
            }
        }
        return "<no direct candidate>";
    }
}
~~~

Usage:

~~~java
String sourceName =
    PropertyDiagnostics.firstCandidateSourceName(
        environment, "app.client.timeout");
~~~

This is an **orienting** tool: it finds the first source with a value returned by `PropertySource.getProperty` for the queried key. If the project has custom resolvers, dynamic sources, deferred resolution, or specific relaxed binding, verify further with Binder/Actuator/tests.

If the key is a secret, **even the source name alone can reveal infrastructure structure**. Restrict access to the output and do not turn helpers into end-user features.

## 10. Axis 3 — Which Profile Is Active?

Do not infer active profiles from hostnames, branch names, or files existing in the repository. Retrieve the information from Spring Environment:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;

public void reportProfiles(Environment env) {
    System.out.println(
        "active profiles = "
            + Arrays.toString(env.getActiveProfiles()));
    System.out.println(
        "default profiles = "
            + Arrays.toString(env.getDefaultProfiles()));
}
~~~

`getActiveProfiles()` returns the profiles currently active in Environment. `getDefaultProfiles()` returns the default profiles used when no profile is active under Spring's mechanism. These are two different concepts.

For example:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

or an environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

activates `prod` under standard Spring configuration. However, if a higher-precedence source sets a different `spring.profiles.active`, the result must be confirmed on the actual Environment.

### A Common Mistake

A developer reads `application-prod.yml` and says "production is already using 8s." Yet `getActiveProfiles()` returns `[staging]`. The production file exists in the artifact, but **is not automatically loaded just for existing**. Check active profiles and the source supplying them before debugging individual keys.

## 11. Active and Default Profiles Are Not the Same

Suppose:

~~~properties
spring.profiles.default=local
~~~

If there is no explicit active profile, conditions based on the default profile can participate. If `spring.profiles.active=prod` is already provided, the default profile does not act like an additional active profile.

Distinguish between:

- **Active profiles:** activated explicitly or via a valid mechanism, affecting Config Data selection and `@Profile` beans.
- **Default profiles:** used when there are no active profiles.
- **Profile groups:** multiple profiles can be grouped with `spring.profiles.group.*` in valid configuration; one active group can lead to multiple active profiles.
- **Profile-specific documents:** loaded/selected when the corresponding profile is active, not merely because the file exists.

Do not compute the list of profile files manually by concatenating environment names. Inspect the actual profile list and Boot's Config Data mechanism.

## 12. Where spring.profiles.active May Be Placed

In Spring Boot Config Data, you should not place `spring.profiles.active` or properties controlling profile activation inside a profile-activated document in ways that violate the Boot version's rules.

For example, base configuration:

~~~yaml
# application.yml - base document
spring:
  profiles:
    active: dev
~~~

can be a way to set the active profile in an appropriate context, though production should generally control profiles via the deployment environment or CLI, avoiding hardcoding `dev` into a shared artifact.

A file like `application-prod.yml` is not a reliable place to "self-enable the prod profile," because that file is selected **after** the system has determined profiles from valid sources.

Similarly, a YAML document with `spring.config.activate.on-profile` is not a place to arbitrarily redefine `spring.profiles.active` to create an activation loop.

**Debugging rule:** inspect where active/default/include/group are declared; do not move these keys into profile-specific files without considering Config Data restrictions.

## 13. Reading Multiple YAML Documents by Profile

An `application.yml` file can contain multiple documents:

~~~yaml
app:
  client:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  client:
    timeout: 8s
~~~

When the `prod` profile is active and no higher source overrides it, the second document can provide `app.client.timeout=8s`. When `prod` is not active, that conditional document is not applied.

Distinguish carefully:

- Was the file found and loaded?
- Which YAML documents inside the file were activated?
- Does another profile-specific file declare the same key?
- Is there a higher-precedence Config Data import or environment property?
- How is the final value converted/bound?

**"Read application.yml" does not mean every document in the file is active.**

## 14. Axis 4 — Declaration Location (Origin)

In Spring Boot, certain property sources can store **origin** information, such as configuration file, resource name, and line/column number. From that, the failure analyzer sometimes prints:

~~~text
Property: app.client.timeout
Value: "soon"
Origin: class path resource [application.yml] - 7:14
Reason: Failed to convert from String to Duration
~~~

This is an illustrative sample, not a log string guaranteed to look identical across all versions. `Origin` is very useful because it indicates **where the value came from**, rather than the file the developer happens to have in mind.

### What Kinds of Origin Exist?

- Classpath resource inside an executable JAR.
- External file from a file location.
- Profile-specific YAML/properties.
- Imported resource, config tree, or PropertySource with origin support.
- Environment variables or system properties with corresponding source metadata when available.
- Custom PropertySources may not provide detailed information.

**Not every source has a line number.** A container-supplied environment variable usually has no "line in YAML" in a sense the Java application can know. If origin is absent, never fabricate a file location.

## 15. Querying OriginLookup for a Key

Spring Boot has an origin API supporting metadata retrieval from sources with origin tracking. Illustrative code:

~~~java
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class OriginInspector {
    private OriginInspector() {}

    public static void inspectNonSensitiveKey(
        ConfigurableEnvironment env,
        String key
    ) {
        for (PropertySource<?> source : env.getPropertySources()) {
            Object candidate = source.getProperty(key);
            if (candidate == null) {
                continue;
            }

            Origin origin = OriginLookup.getOrigin(source, key);
            System.out.println("source = " + source.getName());
            System.out.println(
                "origin available = " + (origin != null));
        }
    }
}
~~~

This example avoids printing `candidate` or `origin` verbatim. Once it is confirmed that **the key is non-sensitive** and the test environment permits it, selective origin information can be displayed to identify which file/line to inspect. Resource paths can reveal deployment details, so do not expose them publicly.

`OriginLookup.getOrigin(...)` can return `null` when the source does not provide origin, or when the lookup does not map to a specific origin. Source name and origin together are helpful, but do not replace understanding PropertySource precedence.

### A Source Name Is Not Always a Filepath

For example, `systemEnvironment`, `systemProperties`, or `commandLineArgs` are Spring mechanism source names. They do not mean a physical file exists by that name. If you need to know which Compose file supplied a container variable, inspect the **deployment infrastructure**; Spring Environment does not automatically retain the full Compose interpolation history.

## 16. Classpath File, External File, and the Running Artifact

A common cause is editing `src/main/resources/application.yml` in the repo while the application actually runs from a **previously built JAR**.

For example:

~~~text
Workspace:
  src/main/resources/application.yml  -> timeout 8s

Running:
  order-service.jar                   -> timeout 3s
~~~

Without rebuilding/redeploying, editing a workspace file does not automatically change the packaged resource already inside the JAR.

Diagnostic path:

1. Identify the actual running version/image digest/JAR.
2. Identify the classpath files the artifact contained at build time.
3. Check whether external Config Data is overriding it.
4. Check active profiles and higher-precedence sources.
5. Check when the process started relative to when the file was modified.

Do not say "edited the file, Spring isn't picking it up" before distinguishing **source files** from **files inside the artifact**.

## 17. External Configuration Outside the JAR

Spring Boot can load Config Data from locations outside the JAR according to default search rules or configured locations.

Run example:

~~~bash
java -jar order-service.jar \
  --spring.config.additional-location=optional:file:./config/
~~~

If the directory is loaded and contains a matching configuration file, properties in it can affect the final value. For directory locations, the trailing `/` in the path matters syntactically.

Checklist:

- Which process's working directory is `./config/` resolved against?
- Does the file there have the exact `application.yml`/profile-specific name?
- Is `spring.config.name` or another location set?
- Does the import/optional location exist and is it readable?
- Is the path inside the container actually mounted?
- Is a higher-precedence source overriding the value?

### spring.config.location and additional-location Differ

`spring.config.location` changes how configuration locations are specified with its own semantics; `spring.config.additional-location` adds locations to the search chain. Do not treat them as equivalent spellings.

Properties controlling Config Data locations must be available **very early** so Boot can locate config files. Placing them inside a file that is only read after locations are determined may not work as expected. Prefer supplying them via CLI, system properties, or appropriate environment variables.

## 18. spring.config.import and Source Location

A file can import other data:

~~~properties
# application.properties
spring.config.import=optional:file:./config/client.properties
~~~

Imported file:

~~~properties
# ./config/client.properties
app.client.timeout=7s
~~~

Boot brings imports into Config Data according to framework rules. When two documents both declare a key, the order and precedence of the imported document must be examined; do not assume it has arbitrary high or low priority purely based on filename.

In Spring Boot's Config Data model, **imports have precedence rules relative to the document declaring the import**, while also being influenced by other sources such as environment, CLI, and profiles. When tracing, record explicitly:

1. Which document contains `spring.config.import`?
2. Which path did the imported resource resolve to?
3. Does the imported file exist and was it loaded?
4. Is the key in the imported file overridden by another PropertySource?
5. Is `optional:` causing a missing file to be skipped?

Do not edit a classpath YAML while overlooking an imported file that is actually providing the winning key.

## 19. configtree and Mounted Files

A container can mount secrets/config as files under a directory:

~~~text
/run/secrets/
  app.client.timeout
  spring.datasource.password
~~~

With:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

each file can become a property named after the filename. For example, a file `app.client.timeout` containing `4s` will yield the corresponding key.

**The origin of a configtree property relates to the imported resource**, and does not necessarily have a "YAML line" like `application.yml`.

During diagnosis:

- Check the exact filename.
- Check the mount path **inside the container**, not just on the host machine.
- Check the process's read permissions.
- Check whether the container was restarted/refreshed after the mount changed.
- Never print the contents of secret files.

`configtree:/run/secrets/` is a mechanism for supplying Config Data; it does not automatically guarantee Spring Boot updates every bean the moment a file is updated.

## 20. Axis 5 — When the Value Is Read

This part is often overlooked. Even with the same `Environment`, different consumers can read values at different times.

~~~text
Process startup
     |
     +-- Environment prepared
     |     - system properties
     |     - environment variables
     |     - Config Data load, profile resolution
     |
     +-- Bean definitions / configuration parsing
     |
     +-- @ConfigurationProperties bean bound
     |     -> ClientProperties(timeout=2s)
     |
     +-- Service created
     |     -> may copy timeout into a client object
     |
     +-- Application handles requests
           -> uses retained timeout
           -> or reads Environment each time
~~~

A record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

is typically bound when the bean is created during context startup. A service injects the record and holds that reference:

~~~java
@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration configuredTimeout() {
        return properties.timeout();
    }
}
~~~

When an external YAML file is edited after startup, you cannot assume `properties.timeout()` changes immediately. Standard Config Data **is not a file watcher** that automatically rebinds beans.

## 21. Call-Time Environment Lookup vs. Bean Snapshot

Compare the two approaches:

**Approach A — reading Environment each time:**

~~~java
@Service
public class DynamicLookupService {
    private final Environment env;

    public DynamicLookupService(Environment env) {
        this.env = env;
    }

    public String timeoutText() {
        return env.getProperty("app.client.timeout");
    }
}
~~~

**Approach B — using an already-bound typed bean:**

~~~java
@Service
public class BoundConfigService {
    private final ClientProperties config;

    public BoundConfigService(ClientProperties config) {
        this.config = config;
    }

    public Duration timeout() {
        return config.timeout();
    }
}
~~~

With A, the method queries Environment on each call. However, if the underlying PropertySources **have not changed**, A still receives the old value even if a file on the host was edited.

With B, the method reads the value of the already-created object. Even if the underlying Environment changes via a custom mechanism, B can still retain the old snapshot until the bean is refreshed/rebound/recreated according to the architecture.

**Do not equate "reads on every call" with "reloads file on every call."** The two belong to different mechanisms.

## 22. When a Service Has Copied the Value into Another Dependency

A service might use configuration when building an HTTP client:

~~~java
@Bean
WebClient remoteWebClient(
    WebClient.Builder builder,
    ClientProperties properties
) {
    return builder
        .baseUrl("https://api.example.test")
        .build();
}
~~~

The example illustrates lifecycle only, without applying timeout yet. A real client might configure timeout when constructing the underlying HTTP transport. In that case:

- `ClientProperties` might change if a rebind mechanism exists.
- Yet the already-created client object can still keep the timeout configured during initial creation.
- The client must be recreated/reconfigured to apply the new value.

The diagnostic point is **when the consumer captures/copies the value**, not only when Binder receives the value. Even if `Environment.getProperty("app.client.timeout")` yields the new value, an existing connection pool, scheduler, or HTTP client may still be using the old configuration.

## 23. Early-Created Beans and Late-Added PropertySources

Some properties are read by Spring Boot very early during startup. For example, settings controlling logging and `spring.main.*` are often evaluated before later application configuration steps complete.

If you add a source late via `@PropertySource` on a `@Configuration`, that source can enter the context **too late** for certain settings read in early phases.

An example to consider carefully:

~~~java
@Configuration
@PropertySource("classpath:custom.properties")
public class CustomConfiguration {}
~~~

Do not treat `custom.properties` as an appropriate source for controlling all early-startup properties as though it were loaded beforehand by the Config Data loader. If a key is read early, choose a source that Spring Boot loads in time during Environment preparation.

**When debugging, ask "who reads this property first?"**. If the logging system has already initialized before a source appears, changing that source later will not automatically reapply the logging policy.

## 24. Spring Profiles Are Also Determined Early

`spring.profiles.active` matters for deciding which Config Data is loaded. Therefore, attempting to change active profiles too late inside a bean after startup is not equivalent to starting the application with that profile from the beginning.

For example:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

differs in timing from a service executing dynamic code after the context is ready:

~~~java
System.setProperty("spring.profiles.active", "prod");
~~~

Calling `System.setProperty` at runtime changes the JVM system property, but does not automatically tell Spring Boot to **reload all profile-specific Config Data and rebuild the bean graph**. Do not use this technique as a dynamic profile-switching mechanism.

The safe approach: configure the profile **before the application starts**, then perform a controlled restart/rollout when a deployment needs to switch profiles.

## 25. Why Editing a File Does Not Auto-Refresh

Suppose the process starts at 09:00:

~~~text
09:00 - Spring Boot reads application.yml, timeout=2s
09:01 - ClientProperties is created with timeout=2s
09:05 - Developer edits application.yml to timeout=8s
09:06 - Service still has ClientProperties(timeout=2s)
~~~

The situation above is normal when no reload mechanism is present. Mental model:

~~~text
File change on disk
   != PropertySource updated
   != ConfigurationProperties bean rebound
   != HTTP client/pool recreated
~~~

If Spring Boot DevTools is present in a development environment, certain changes can trigger an application restart under DevTools' mechanism; that is a **context restart**, not evidence that Binder supports live reload of arbitrary files.

If the system uses Spring Cloud Config, a refresh endpoint, Kubernetes reload integration, or a custom source watcher, you must describe precisely which mechanism updates Environment, refreshes scope, rebinds beans, and recreates dependent objects. Do not assume these capabilities exist in core Spring Boot.

## 26. Record the Timestamp of Evidence

A diagnostic report should record measurement timestamps:

~~~text
Process started: 09:00
Config file modified: 09:05
Environment lookup observed: 09:07
Bound properties observed: 09:07
Container recreated: No
Config refresh mechanism: None
~~~

If two people collect results from **two different containers** (rolling deployment), each container has its own startup time, image version, and Environment. Do not conclude "Spring returns inconsistent values" when comparing an old instance against a new one.

With Kubernetes or Compose, record the container ID/Pod name/revision per operational procedure without printing the entire environment.

## 27. A Combined Case: Wrong Timeout in Production

Suppose the sources are as follows:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 8s
~~~

Container runtime:

~~~text
APP_CLIENT_TIMEOUT=2s
SPRING_PROFILES_ACTIVE=prod
~~~

Java command:

~~~bash
java -jar app.jar --app.client.timeout=500ms
~~~

Consumer:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

**Tracing workflow:**

1. **Key:** Java component `timeout` with prefix `app.client` requires `app.client.timeout`.
2. **Profile:** `prod` is active, so the profile-specific file can participate.
3. **Sources:** base file 5s, prod file 8s, env 2s, CLI 500ms.
4. **Precedence:** CLI beats the other standard sources in this scenario.
5. **Origin:** the winning source is application CLI; there is no YAML line number for the 500ms value.
6. **Time:** the `ClientProperties` bean was bound at startup with `Duration.ofMillis(500)`.
7. **Conclusion:** editing prod YAML will not change the value while CLI still supplies 500ms. Fix or remove the higher-precedence override, then redeploy/restart accordingly.

Do not "fix" this by modifying code to force a minimum timeout if the timeout policy was simply deployed incorrectly. Of course, business validation such as a minimum timeout bound can be added separately.

## 28. Wrong Profile Case, Not Wrong Precedence

Another scenario:

~~~yaml
# application-staging.yml
app:
  client:
    timeout: 7s
~~~

At runtime, `environment.getActiveProfiles()` only returns `[dev]`. The developer expects staging timeout `7s`, yet the app receives `3s` from the base file.

This is primarily a **profile selection** error, not a staging source being overridden by a dev source in every respect. The staging file may simply not be loaded.

Check:

- Is `SPRING_PROFILES_ACTIVE=staging` actually set inside the container?
- Does the Compose `.env` file only contain `APP_PROFILE=staging` without passing it through to `SPRING_PROFILES_ACTIVE`?
- Does the command line pass `--spring.profiles.active=dev` with higher precedence than env?
- Is a profile group or other startup logic affecting it?
- Is the running process the newly deployed instance or an old container?

Even though the filename says `staging`, it is only a candidate when Spring selects that document under Config Data rules.

## 29. Origin Points to a File Outside the JAR

Suppose the repo has:

~~~text
src/main/resources/application.yml
  app.client.timeout: 3s
~~~

Yet the container mounts:

~~~text
/etc/order-config/application.yml
  app.client.timeout: 9s
~~~

and Spring Boot is configured to load the corresponding external location. If the external source outside the JAR wins, origin can point to the resource `file:/etc/order-config/application.yml`.

Do not edit the packaged file in the repository expecting the timeout to change if runtime is picking up another source. Identify:

1. Host-to-container mount path.
2. Config location in command/env.
3. Actual source order.
4. Permissions and **non-sensitive** file content.
5. Whether the process was restarted after the file changed.

If the source only has a filename without line-level origin metadata, you can still use that URL/path as a starting point, then inspect the specific file with authorized operational tools.

## 30. Placeholders Make Raw Values Hard to Read

File:

~~~yaml
app:
  client:
    timeout: "\${CLIENT_TIMEOUT:2s}"
~~~

A source may contain the raw text `\${CLIENT_TIMEOUT:2s}`, yet when Spring resolves the placeholder it can become `5s` if `CLIENT_TIMEOUT=5s` is present in Environment.

Therefore differences can appear across layers:

- `PropertySource.getProperty("app.client.timeout")`: raw value or value provided by the source.
- `Environment.getProperty("app.client.timeout")`: value after the applicable resolver/placeholder mechanism.
- `Binder.bind(...)`: typed value after binding/conversion.
- Bean `ClientProperties.timeout()`: value bound when the bean was created.

A proper debugging approach is to separate **where the placeholder is written** from **the source of the variable the placeholder references**. If `CLIENT_TIMEOUT` is missing, the fallback `2s` is not a value "beating the staging file"; it is the default in the placeholder expression.

If a placeholder cannot be resolved and has no fallback, the failure can occur in resolution/binding depending on context, not solely conversion.

## 31. Lists and Maps Have Different Semantics from Scalars

A scalar key can be overridden individually. However, with `@ConfigurationProperties`, **a list is typically replaced by the list from the higher-precedence PropertySource**, rather than deep-merged element by index as one might expect.

Base file:

~~~yaml
app:
  gateways:
    - name: primary
      timeout: 2s
    - name: secondary
      timeout: 5s
~~~

A higher source declares only:

~~~properties
app.gateways[0].timeout=1s
~~~

Do not assume the result will be primary timeout 1s while preserving all fields of both primary and secondary from the original file. List replacement, missing fields, or missing elements can occur.

When tracing collections:

1. Locate the **root property of the list**, not only leaf fields.
2. Identify which source provides the higher-precedence list.
3. Inspect the entire shape and indexes of the list in that source.
4. Check nested conversion and validation.
5. If merging by identifier is desired, consider `Map<String,Gateway>`.

**A leaf property appearing "properly overridden" does not prove the final list structure is right.**

## 32. Distinguish Bad Bind, Bad Conversion, and Bad Validation

Even after knowing key/source/profile/origin/time, failure can still happen at the bind step:

| Issue type | Example | Fix direction |
| --- | --- | --- |
| Wrong key or shape | `app.gateway.timeout` when Java needs `app.gateways[0].timeout` | Fix property structure/name |
| Conversion | `app.client.timeout=soon` when Java needs `Duration` | Fix value format |
| Validation | `timeout=0s` when policy requires positive duration | Fix value or constraint |
| Bean registration | Record has `@ConfigurationProperties` but not scanned/enabled | Register typed bean properly |
| Consumer cache | New Environment while client is old | Recreate/rebind/restart appropriately |

Conversion or validation failures can be **wrapped inside `BindException`/`ConfigurationPropertiesBindException`**. Therefore, look for `Reason` and the exception root cause rather than concluding every "Failed to bind properties" line means invalid YAML.

If a key is misspelled while `ignoreUnknownFields` allows skipping it, the app might not fail startup; validation and tests are needed to catch missing required fields.

## 33. Actuator env to Inspect Sources and Properties

Spring Boot Actuator provides the `env` endpoint, useful for investigating environment and configuration sources when enabled **with proper protection**.

To inspect a non-sensitive property in a test environment, the endpoint can support querying by name:

~~~text
GET /actuator/env/app.client.timeout
~~~

Depending on Spring Boot version and configuration, the response can show the source, sanitized value, or related origin information. The endpoint does not replace checking whether the consumer has bound and retained a snapshot.

**Security is mandatory in operational thinking:**

- Do not expose `env` to the public Internet.
- Expose only to authorized operators.
- Protect with authentication, authorization, and network restrictions.
- Be cautious with endpoint names, property sources, and origin metadata.
- Do not set `show-values=always` indiscriminately in production.

A configuration option to suppress displaying values:

~~~properties
management.endpoint.env.show-values=never
~~~

If values need to be visible in a test environment, verify access permissions, data classification, and options supported by the running Spring Boot version. **Masking does not mean an endpoint is safe to make public.**

## 34. Actuator configprops to Inspect Typed Configuration

Actuator's `configprops` endpoint helps inspect bound `@ConfigurationProperties` beans, potentially accompanied by input metadata depending on version and configuration.

~~~text
GET /actuator/configprops
~~~

Use it to answer a different question from `env`:

- `env`: which property candidates/sources exist in Environment?
- `configprops`: in what structure are configuration properties beans bound, in the observed context?

In many applications, typed beans contain secrets. Do not enable displaying all values just to debug a timeout. You can set:

~~~properties
management.endpoint.configprops.show-values=never
~~~

and secure the endpoint. `never` is the conservative choice for an environment whose safety has not been evaluated.

**Comparing `env` with `configprops` can hint at bind-timing differences**, though interpretation must account for caching, refresh, bean lifecycle, and how Actuator gathers data in the specific version.

## 35. When Actuator Cannot Be Enabled

Not every system has Spring Boot Actuator, and production may prohibit exposing diagnostic endpoints. Alternatives:

1. Create an isolated test context with an environment's exact property inputs.
2. Log only an **allowlist of non-sensitive keys** during experimental startup.
3. Iterate source names for a key via `ConfigurableEnvironment`.
4. Use the failure analyzer when startup fails.
5. Inspect deployment specs to confirm actual env/CLI/mounts.
6. Compare artifact version and process start time.

Example logging non-sensitive info:

~~~java
log.info(
    "springProfiles={}, clientTimeoutPresent={}",
    Arrays.toString(env.getActiveProfiles()),
    env.containsProperty("app.client.timeout")
);
~~~

Never log `System.getenv()`, `getSystemProperties()`, all `PropertySources`, or `@ConfigurationProperties` records containing passwords/tokens.

## 36. Testing Precedence with ApplicationContextRunner

A small test context can illustrate a property input overriding a default file in tests or verify the bound value.

Example record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientBindingTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class);

    @Test
    void bindsExplicitValue() {
        runner
            .withPropertyValues("app.client.timeout=500ms")
            .run(context -> {
                assertThat(context).hasNotFailed();
                ClientProperties props =
                    context.getBean(ClientProperties.class);
                assertThat(props.timeout())
                    .isEqualTo(Duration.ofMillis(500));
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class Config {}
}
~~~

This test proves **a value is bound and converted properly** in the test context. It does not prove that the production profile or an actual external file was loaded. To test Config Data and active profiles, use corresponding integration tests/setup.

## 37. Testing Active Profile with an Integration Test

A test using `@ActiveProfiles`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.core.env.Environment;

@SpringBootTest
@ActiveProfiles("prod")
class ProdProfileTest {
    @Autowired
    Environment environment;

    @Test
    void expectedProfileIsActive() {
        assertThat(environment.getActiveProfiles())
            .contains("prod");
    }
}
~~~

This test confirms the Spring Test context activates `prod` per test configuration; it does not prove that **a deployment outside tests** activates the same profile.

You can inject `ClientProperties` and assert the expected timeout in the test when sources are set up consistently. If the test has `@SpringBootTest(properties=...)`, those test properties themselves can override other files, so document any overrides used in the test clearly.

## 38. Building a Five-Axis Test Matrix

| Case | Key | Source | Profile | Origin | Time |
| --- | --- | --- | --- | --- | --- |
| A | `app.client.timeout` | application.yml | default | classpath resource | startup |
| B | `app.client.timeout` | application-prod.yml | prod | profile resource | startup |
| C | `app.client.timeout` | OS env | prod | environment source | startup |
| D | `app.client.timeout` | CLI | prod | commandLineArgs | startup |
| E | `app.client.timeout` | mounted file | prod | external file | startup |
| F | `app.client.timeout` | Config Data import | prod | imported resource | startup |
| G | `app.client.timeout` | same source, file edited | prod | new file | after startup, not refreshed |
| H | `app.client.timeout` | Environment changed | prod | dynamic source | consumer re-reads or holds snapshot |

The goal of the table is not to assume every case creates a difference, but to **isolate one condition variable at a time**. When the winning source in case D is identified, try removing the CLI override in a safe test environment to see what the next winning source is; do not change production immediately by trial and error.

## 39. When a Value Comes from Docker Compose

A deployment case:

~~~dotenv
# .env - Compose interpolation
CLIENT_TIMEOUT=5s
~~~

~~~yaml
services:
  api:
    environment:
      APP_CLIENT_TIMEOUT: "\${CLIENT_TIMEOUT:-3s}"
~~~

Compose takes `CLIENT_TIMEOUT` from the CLI/dotenv environment and passes it as container env `APP_CLIENT_TIMEOUT`. Spring Boot can bind `app.client.timeout` from that container key.

If the Compose YAML does not declare the corresponding `environment` or `env_file`, a `.env` file alone **does not inject variables into the container**.

Diagnostic clues:

- Host variable is right but missing in container: check Compose interpolation vs. service runtime environment.
- Container has variable but Spring gets something else: check Spring precedence, CLI, and profiles.
- Spring has the new variable but the bean stays old: check startup time/refresh.
- Bean is new but the HTTP client stays old: check when the consumer copied settings.

This is a classic illustration of why you must trace **all the way to the consumer**, not stop at a single file.

## 40. When JVM -D and Spring --arg Both Exist

Command:

~~~bash
java -Dapp.client.timeout=3s \
  -jar order-service.jar \
  --app.client.timeout=500ms
~~~

`-Dapp.client.timeout=3s` before `-jar` is a Java system property. `--app.client.timeout=500ms` after the JAR is a Spring Boot application argument, when command-line properties are enabled.

In typical default Spring Boot configuration, CLI properties take precedence over JVM system properties, so the final value is `500ms`.

A syntax mistake:

~~~bash
java -jar order-service.jar -Dapp.client.timeout=3s
~~~

`-D...` **after** `-jar` is an application argument, no longer processed by the Java launcher as a JVM system property. Do not think of it as equivalent to the correct command. Unless the application manually parses that argument format, the property may not be applied as intended.

Record **the actual command executed** in the container/service manager, not just the JVM options the developer thinks were configured.

## 41. When @Value and @ConfigurationProperties Yield Different Results

One component uses:

~~~java
@Value("\${app.client.timeout:2s}")
private Duration timeout;
~~~

Another bean uses:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

They can differ because:

- `@Value` has a `2s` placeholder fallback, while the record model may have no default.
- The two consumers were created at different times while Environment changed.
- Spring Core `@Value` conversion path is not identical to the specialized Binder in every situation.
- One consumer holds a snapshot; the other re-reads Environment.
- One field is configured via a Java default, not a PropertySource.

Do not deduce that Spring Boot "chose two different sources" merely because two values differ. Inspect **how each consumer receives its configuration** first.

## 42. Custom PropertySource Cases

A library might add an external source via `EnvironmentPostProcessor` or programmatically modify `MutablePropertySources` via an appropriate lifecycle hook. In that case, the source's name and position in the list affect the result.

Conceptual example:

~~~java
ConfigurableEnvironment env = ...;
PropertySource<?> custom = ...;

env.getPropertySources().addFirst(custom);
~~~

This is pseudo-code illustrating the idea, not a recommended configuration to copy verbatim into production. `addFirst` places the source at high precedence in the current `MutablePropertySources`. Another module could also insert a source in another order.

Ask:

- When was the source added?
- Is it before or after system environment/config data?
- Does the source use canonical spelling for keys?
- Does it have origin metadata?
- Was Binder invoked before or after the source was added?
- Are there caches or snapshots in consumers?

Some properties are read very early by Spring Boot; adding a source during context refresh will not necessarily alter those early decisions.

## 43. How to Read a "Failed to bind" Message with Origin

Hypothetical startup failure:

~~~text
Failed to bind properties under 'app.client.timeout'
to java.time.Duration:

    Property: app.client.timeout
    Value: "someday"
    Origin: file [./config/application-prod.yml] - 12:16
    Reason: failed to convert String to Duration
~~~

Workflow:

1. Property shows the **key** to fix.
2. Target type shows **Duration** is needed.
3. Value `someday` is not a valid Duration format.
4. Origin points to the **external production file**, not `src/main/resources/application.yml`.
5. Profile and Config Data explain why that external file was loaded.
6. Startup failure proves the error occurred during binding; no need to hunt for a post-startup "refresh bug."
7. Fix the value in the winning source to a valid duration such as `2s` or `500ms` as actually needed.

Do not print the value if the property might contain a secret; focus on key, target type, and sanitized reason.

## 44. A 15-Step Tracing Workflow Ready for Immediate Use

1. **Identify the observed error** and consumer: controller, datasource, HTTP client, scheduler, config record?
2. **Determine the canonical key**, prefix, and Java target type.
3. **List possible defaults** from `@Value` placeholder, `@DefaultValue`, field initializer, or caller fallback.
4. **Confirm the actual running process/Pod/container**, image/JAR version, and start time.
5. **Read active/default profiles** from the real `Environment`, not from environment names.
6. **List candidate sources** for a non-sensitive key via `PropertySources` or a secured diagnostic tool.
7. **Determine the winning source** in runtime order, without inferring from files alone.
8. **Retrieve origin** if the source supports it; if not, record "no origin."
9. **Check Config Data locations**: packaged, external, import, configtree, profile-specific.
10. **Check host/container/CI variables**: actually passed into the process, or only used for Compose interpolation?
11. **Check command-line and JVM `-D` overrides**; pay attention to `-D` placement.
12. **Check placeholder resolution**, type conversion, and constraint validation.
13. **Check read timing**: startup snapshot, method reading Environment, refreshed bean, dependency that copied config.
14. **Reproduce with a small test** or safe staging environment, changing only one condition at a time.
15. **Fix the right source and lifecycle**, redeploy/restart/recreate components when needed; verify on the exact instance.

Record evidence-backed findings at each step. There is no need to open/dump the entire environment to logs. When a step cannot be verified yet, clearly mark it "unknown" rather than filling in a conclusion.

## 45. Quick Symptom Checklist

| Symptom | Check first |
| --- | --- |
| App does not see key | Prefix, spelling, PropertySources, missing source |
| Prod file has value but app gets dev file | Actual active profiles |
| YAML is right but runtime value differs | CLI, `-D`, OS env, imports, and external config |
| Actuator env shows new value, bean stays old | Bind/refresh timing |
| Bean is new but HTTP client stays old | Dependency copied config at creation time |
| Source name is systemEnvironment | Which container/OS supplied the variable |
| Config source is an unfamiliar external file | `spring.config.location`, `additional-location`, import |
| Origin has no line number | Source does not support file/line origin |
| CLI turns value into 500ms | Check actual startup arguments |
| `@Value` has 2s while Binder has nothing | Placeholder default differs from model default |
| Editing file after startup has no effect | Config Data startup load; no refresh |
| Adding `@PropertySource` does not change logging | Property read too early |
| List loses elements | List replacement / PropertySource precedence |
| Value present but BindException | Conversion, shape, or validation root cause |
| Container does not get variable from `.env` | Compose interpolation is not runtime env |
| Two Pods return different timeouts | Compare start time, image revision, env, and rollout |

## 46. Exercise 1 — Trace the Winning Value

Given:

~~~text
application.yml: app.client.timeout=5s
application-prod.yml: app.client.timeout=8s
APP_CLIENT_TIMEOUT=2s
CLI: --app.client.timeout=500ms
Active profile: prod
~~~

**Question:** what is the `Duration timeout` value under standard precedence?

**Answer:** `Duration.ofMillis(500)`. CLI beats the remaining sources in this illustrative scenario. Whether the prod file was loaded does not change the final result while CLI still has higher precedence.

## 47. Exercise 2 — File Exists but Profile Is Not Active

~~~text
application-staging.yml has timeout 7s
Environment.getActiveProfiles() -> [dev]
~~~

**Question:** why didn't Spring pick 7s?

**Answer:** there is no evidence the staging file was selected under Config Data. You need to activate the appropriate profile or configure an intentional file-loading mechanism, not merely create the file.

## 48. Exercise 3 — Source Exists but Bean Does Not Change

~~~text
09:00: bean binds timeout=2s
09:05: external file edited to 8s
09:06: bean still returns 2s
~~~

**Answer:** this can be a normal startup snapshot. Editing a file does not automatically update PropertySources, rebind beans, or recreate consumers. Verify whether an actual reload mechanism exists before diagnosing a bug.

## 49. Exercise 4 — Key in .env but Missing in Container

~~~dotenv
# .env
APP_CLIENT_TIMEOUT=5s
~~~

~~~yaml
services:
  api:
    image: example/app:local
~~~

**Answer:** the `.env` file serves Compose interpolation by default; it does not automatically inject all keys. You need `environment` or `env_file` on the service according to deployment intent.

## 50. Exercise 5 — JVM Option in the Wrong Position

~~~bash
java -jar app.jar -Dapp.client.timeout=1s
~~~

**Answer:** the JVM launcher does not treat `-D` in this position as a system property; after `-jar` it is an application argument. Put `-Dapp.client.timeout=1s` before `-jar`, or use the Spring CLI property `--app.client.timeout=1s` after the JAR.

## 51. Exercise 6 — Origin Points to an Imported File

~~~properties
spring.config.import=file:./config/client.properties
~~~

The imported file declares `app.client.timeout=7s`. The original file declares `2s`.

**Answer:** check Config Data import precedence; under Spring Boot's import rules, the imported file can override the document declaring the import. Still check whether any higher-precedence CLI/env/system property exists, and whether the file actually exists/was loaded.

## 52. Exercise 7 — Raw Value vs. Resolved Value

~~~yaml
app:
  client:
    timeout: "\${CLIENT_TIMEOUT:2s}"
~~~

Environment has `CLIENT_TIMEOUT=9s`.

**Answer:** the file holds a raw placeholder, Spring can resolve it to `9s`, and Binder converts it to Duration. Do not confuse raw text in a resource with the final value in the bean.

## 53. Exercise 8 — Error Due to List Replacement

The base file has two gateways. A higher source declares only `app.gateways[0].timeout=1s`.

**Answer:** do not assume both gateways and nested fields from the lower source are preserved. With Binder lists, inspect the entire winning source and list replacement semantics.

## 54. Exercise 9 — Custom Source Added Late

The app needs to change `logging.level.root`. A `@PropertySource` is added during later configuration parsing.

**Answer:** the source may arrive too late to affect initial logging setup. Use an appropriately early-loaded config source instead of assuming every PropertySource takes effect at the same time.

## 55. Exercise 10 — Secrets and Debugging

A developer wants to print `System.getenv()` and all `PropertySources` to see the database password.

**Answer:** do not do this. Those outputs can expose tokens/passwords and sensitive data. Trace **key name, source name, existence, and authorized origin**, and use a secret manager/auditing per procedure instead of dumping values.

## 56. Final Reference Table

| Question | Place/concept to check |
| --- | --- |
| What is the canonical key? | `@ConfigurationProperties` prefix + Java component + canonical naming |
| Corresponding environment variable? | Relaxed binding / `APP_CLIENT_TIMEOUT` |
| Which source is winning? | `ConfigurableEnvironment.getPropertySources()`, precedence |
| Value Environment returns right now? | `Environment.getProperty(key)` |
| Which profile is active? | `Environment.getActiveProfiles()` |
| Default profile? | `Environment.getDefaultProfiles()` |
| Which YAML file was selected? | Config Data, profile-specific resources, imports |
| File/line origin? | Failure analysis, `OriginLookup` when source supports it |
| Where are external locations? | `spring.config.location`, `spring.config.additional-location` |
| Was an import loaded? | `spring.config.import` and resource location |
| File-mounted config? | `configtree:` or Config Data file |
| Converted to Java value? | Binder / `@ConfigurationProperties` |
| When does the bean hold the value? | Bean creation/bind time |
| Consumer still using old snapshot? | Dependency lifecycle and caching |
| Auto-reload when file is edited? | Usually not; requires refresh/restart mechanism |
| Debug via Actuator? | Secured/sanitized `env` and `configprops` |
| CLI overriding? | `--key=value` after JAR |
| JVM system property in right place? | `-Dkey=value` before `-jar` |
| Compose .env enters container? | Not automatically; needs `environment`/`env_file` |
| Key is a secret? | Never print raw value; restrict origin/metadata |

## 57. Conclusion

To diagnose a Spring Boot value that "differs from the file," always follow this order:

**Exact key → candidate sources and winning source → profile deciding loaded documents → origin of the value → timing of Environment, Binder, and consumer reads.**

These five axes prevent misguided fixes: changing YAML while CLI overrides, activating the wrong profile, editing a file outside the artifact, overlooking Config Data imports, or expecting an immutable bean to self-update when a mounted file changes. Once a single key, winning source, and value-capture time are pinned down, the fix usually becomes a provable, testable, and safely deployable configuration change — rather than a series of unfounded guesses.
