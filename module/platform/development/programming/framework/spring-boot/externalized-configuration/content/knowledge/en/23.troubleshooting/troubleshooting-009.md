# Troubleshooting Replaced Lists, Wrong Map Keys, and Misnamed Environment Variables in Spring Boot

## 1. Objectives

When operating Spring Boot applications, situations occur where configuration files look right and the app still starts, yet the data received in `@ConfigurationProperties` is wrong:

- The base file has three servers; the production file overrides just one server, yet the resulting **List** shrinks to one.
- A route Map uses key `/api/v1`; after binding, the app cannot find the key with slashes.
- A Map key containing a dot `service.alpha` is treated as a nested structure instead of an intact key.
- An operator supplies environment variable `APP_CLIENT_RETRY_MAX_ATTEMPTS`, yet the bean keeps its default; the canonical name requires a different form.
- A Map key set in uppercase via an environment variable turns into lowercase upon binding.
- Indexed properties exist in `Environment`, yet `Environment.getProperty("app.servers")` returns `null`, misleading the investigator into thinking the List is empty.

These belong to **Troubleshooting Spring Boot Externalized Configuration**. Learners need to pinpoint where the issue sits in the chain **configuration source → precedence order → property name → Binder → Java object**, instead of randomly editing multiple files and guessing outcomes.

Three rules to remember:

1. **List:** when multiple property sources declare the same list, the list in the higher-precedence source replaces the entire list. There is no automatic list concatenation or element-by-element field merging.
2. **Map:** keys and nested properties can be aggregated across multiple sources; identical property paths still follow precedence. Literal Map keys with special characters require the right syntax.
3. **Environment variables:** convert from canonical name to env name by replacing dots with underscores, **removing dashes**, then uppercasing; indexed Lists use `_0_`, `_1_`. When binding Maps, key names taken from environment variables can become lowercase.

Examples follow Spring Boot Binder and `@ConfigurationProperties` rules. If an application uses custom converters, custom `PropertySource`s, or parses files itself via another library, verify that specific behavior separately.

## 2. Configuration Flow

~~~text
application.yml / application-prod.yml
        |
  Spring Boot Config Data
        |
        +-------- OS environment variables
        |                |
        +------ JVM system properties
        |                |
        +------ command-line arguments
        |
        v
    Environment
        |
        v
 PropertySource precedence
        |
        v
   Spring Boot Binder
        |
  +-----+---------+--------+
  |               |        |
 List             Map    Scalar
 replacement     key     relaxed naming
                 rules
  |               |        |
  +---------------+--------+
                  |
                  v
       @ConfigurationProperties
                  |
                  v
            Business service
~~~

Do not confuse a value appearing in a file with the **effective value**. A valid `application.yml` can still be overridden by `application-prod.yml`, an external file, an environment variable, or a command-line option. For Lists and Maps, even after knowing the winning source, how Java objects combine differs.

### 2.1. Four Diagnostic Questions

1. **Which property sources are loaded?** Are profiles active, and are locations and imports right?
2. **Which source has the highest precedence for the property?** Is there an override from command line/system property/env?
3. **Is the property name right?** Do prefix, dashes, env name, Map key, and List index match?
4. **What is the target type?** `List<POJO>`, `Map<String,String>`, and `Map<String,Object>` cannot be reasoned about identically.

### 2.2. Do Not Start by Dumping Environment

`Environment` can contain passwords, API keys, connection URLs, and tokens from CI/deployment. Never print all `PropertySource`s and raw values to logs. Diagnose one allowed key at a time using source metadata, error codes, and mock data in tests.

## 3. A Model to Illustrate Lists and Maps

~~~java
package com.example.gateway.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        List<Upstream> upstreams,
        Map<String, Route> routes,
        Duration connectTimeout,
        boolean failFast
) {
    public record Upstream(
            String name,
            String url,
            Duration timeout
    ) {}

    public record Route(
            String target,
            boolean enabled
    ) {}
}
~~~

Registration:

~~~java
package com.example.gateway;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {}
~~~

Configuration:

~~~yaml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://primary.example.test"
        timeout: 2s
      - name: secondary
        url: "https://secondary.example.test"
        timeout: 3s
    routes:
      orders:
        target: primary
        enabled: true
      payments:
        target: secondary
        enabled: true
    connect-timeout: 5s
    fail-fast: true
~~~

Corresponding Java fields:

- `upstreams` is `List<Upstream>`; element order matters.
- `routes` is `Map<String,Route>`; each key identifies a route.
- `connectTimeout` is a scalar `Duration`.
- `failFast` is a scalar boolean.

Binder converts `2s` to `Duration`, `connect-timeout` to `connectTimeout`, and the YAML structure into Java objects. However, when multiple sources supply these fields, combination rules must be understood by target type.

## 4. Mistake Number One: Lists Are Replaced, Not Merged

Base file:

~~~yaml
# application.yml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://primary.example.test"
        timeout: 2s
      - name: secondary
        url: "https://secondary.example.test"
        timeout: 3s
~~~

Production file:

~~~yaml
# application-prod.yml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://prod-primary.example.test"
        timeout: 1s
~~~

When `prod` is active and the production source wins, the List typically contains only:

~~~text
upstreams.size()          = 1
upstreams[0].name         = primary
upstreams[0].url          = https://prod-primary.example.test
upstreams[0].timeout      = 1s
~~~

The `secondary` element is not automatically retained. This is **List replacement across configuration sources**, documented by Spring Boot under *Merging Complex Types*.

### 4.1. Why Not Append?

If two sources both provide `upstreams[0]`, there is no unambiguous way to know whether the user wanted to add, modify, or remove elements. Merging by index could also create a "hybrid" object combining fields from different environments. Spring Boot chooses a clearer rule: **the higher-precedence source providing a List determines the entire list**.

### 4.2. Nested Fields Do Not Auto-Merge Either

Base file:

~~~properties
app.gateway.upstreams[0].name=primary
app.gateway.upstreams[0].url=https://primary.example.test
app.gateway.upstreams[0].timeout=2s
~~~

Higher-precedence profile file:

~~~properties
app.gateway.upstreams[0].name=prod-primary
~~~

Do not expect `url` and `timeout` to be preserved from item 0 of the base file. With List object binding, the effective element may have `name=prod-primary` while fields undeclared in the winning source become `null` or target-type defaults.

**Common symptom:** the List still has item 0, yet its endpoint or timeout disappears; the app fails in the service layer rather than at startup.

### 4.3. Fix When Each Environment Needs a Complete List

Declare **all required elements and fields** in the winning source:

~~~yaml
# application-prod.yml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://prod-primary.example.test"
        timeout: 1s
      - name: secondary
        url: "https://prod-secondary.example.test"
        timeout: 3s
~~~

In simple cases, this is the easiest solution to understand because the production list is a complete unit of configuration.

### 4.4. When Appending Is Genuinely Needed, Design an Explicit Merge

Do not treat Binder as a "concatenate two Lists" tool. You can split properties:

~~~yaml
app:
  gateway:
    common-upstreams:
      - "https://shared.example.test"
    extra-upstreams:
      - "https://prod-only.example.test"
~~~

Java:

~~~java
public record UpstreamGroups(
        List<String> commonUpstreams,
        List<String> extraUpstreams
) {}
~~~

When the final list is needed:

~~~java
List<String> combined = new ArrayList<>(
        properties.commonUpstreams()
);
combined.addAll(properties.extraUpstreams());
~~~

The example requires an appropriate model, non-null lists or handling for missing values, and checking duplicates/order. This is application logic, not default Spring Boot behavior.

### 4.5. Do Not "Fix" by Arbitrarily Switching List to Set

`Set` does not guarantee ordering like `List` and may drop duplicates by `equals/hashCode`. If endpoint priority matters, `Set` can break semantics. Design for the actual business domain instead of changing types solely to dodge List replacement.

## 5. Lists When Multiple Profiles or Locations Are Active

Suppose:

~~~yaml
# application-dev.yml
app:
  gateway:
    upstreams:
      - name: dev
        url: "https://dev.example.test"
~~~

~~~yaml
# application-qa.yml
app:
  gateway:
    upstreams:
      - name: qa
        url: "https://qa.example.test"
~~~

If an environment activates multiple profiles, the result is not a concatenated list from `dev` and `qa`. Following Config Data/profile precedence order, the List from the higher-precedence source is chosen.

When external files, imports, or location groups are present, identify which source actually wins. Never conclude solely from filenames or the order seen in the repository.

### 5.1. External Files Can Override the JAR

An application might read:

~~~text
classpath:/application.yml
classpath:/application-prod.yml
file:./config/application.yml
file:./config/application-prod.yml
~~~

External files can take higher precedence under Boot's Config Data order. A list in an external file can replace the entire list in `src/main/resources/application.yml`, even if the developer did not know the external file existed.

### 5.2. Local Tests and Production Differ

Tests without the production profile active may see two endpoints from the base file. Production activates the profile and leaves only one endpoint. To prevent incidents, write integration tests with matching profiles and sources, asserting **the exact element count and order**.

### 5.3. Do Not Infer a List Property from Its Scalar Prefix

If source keys are `app.gateway.upstreams[0].name` and `app.gateway.upstreams[1].name`, calling:

~~~java
environment.getProperty("app.gateway.upstreams")
~~~

can return `null` because there is no scalar property at that prefix. This **does not prove the List is empty**; inspect indexed child keys or the post-binding object.

## 6. When Lists Are Empty, Missing, or Wrong Type

Three distinct states:

1. No List property exists in relevant sources.
2. A List exists in a lower source yet was replaced by a higher source.
3. The winning source declares an empty value, bad index, or conversion failure.

Example:

~~~properties
app.gateway.upstreams[0].timeout=not-a-duration
~~~

can cause a conversion failure when the target is `Duration`.

A default List initialized inside a JavaBean also does not mean a higher source appends into it. Test with an override, with no source, and with an empty list on your exact Spring Boot version.

### 6.1. Non-Contiguous Indexes

Defining only `upstreams[1]` while omitting `[0]` is not a reliable way to represent the first element. Use contiguous indexes starting at 0, and write tests if special cases must be supported.

### 6.2. Combining Lists from JSON/YAML/Properties

A `List<String>` can be expressed as:

~~~properties
app.servers=alpha,beta
~~~

or:

~~~properties
app.servers[0]=alpha
app.servers[1]=beta
~~~

or YAML:

~~~yaml
app:
  servers:
    - alpha
    - beta
~~~

Regardless of source syntax, when multiple property sources re-declare the target List, apply replacement rules. There is no general rule that "comma-separated merges while YAML replaces."

## 7. Maps Differ from Lists: They Can Aggregate Across Sources

Spring Boot allows a Map to receive keys from multiple property sources; for an identical property path, the higher-precedence source decides the value.

JavaBean model:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class RoutesProperties {

    private final Map<String, Route> routes = new LinkedHashMap<>();

    public Map<String, Route> getRoutes() {
        return routes;
    }

    public static class Route {
        private String target;
        private String description;

        public String getTarget() { return target; }
        public void setTarget(String target) {
            this.target = target;
        }

        public String getDescription() { return description; }
        public void setDescription(String description) {
            this.description = description;
        }
    }
}
~~~

Base file:

~~~properties
app.routes.orders.target=primary
app.routes.orders.description=Order service
~~~

Higher-precedence profile file:

~~~properties
app.routes.orders.target=prod-primary
app.routes.payments.target=prod-payments
app.routes.payments.description=Payment service
~~~

The bound Map object result can be:

~~~text
routes.orders.target         = prod-primary
routes.orders.description    = Order service
routes.payments.target       = prod-payments
routes.payments.description  = Payment service
~~~

The Map keeps `orders.description` from the lower source, updates `orders.target`, and adds `payments` from the higher source. **This is a crucial difference from `List<POJO>`.**

### 7.1. Maps Do Not Do Everything Automatically

Identical key/value paths still apply precedence; Maps do not sum numbers, concatenate strings, or merge objects via arbitrary algorithms. They only aggregate keys and nested properties under Binder rules.

### 7.2. If You Want Whole-Map Replacement

An `application-prod.yml` declaring just a few entries does not automatically delete keys from the base file. If you need environment-independent route sets, use distinct prefixes, separate models, or a designed replacement step with tests.

### 7.3. Illustrative `Map<String,String>`

Base source:

~~~yaml
app:
  labels:
    owner: platform
    tier: backend
~~~

Higher source:

~~~yaml
app:
  labels:
    tier: critical
    environment: prod
~~~

The final Map can contain `owner=platform`, `tier=critical`, `environment=prod`. Do not describe it as a List being wholly replaced.

## 8. Wrong Map Keys from Omitting Bracket Notation

Map key names sometimes contain characters such as `/`, `:`, `@`, or `+`. If the key is not wrapped in `[ ]`, Binder can strip unsupported characters under relaxed binding.

For example, wanting literal key `/catalog/v1`.

Avoid:

~~~properties
app.routes./catalog/v1=https://catalog.example.test
~~~

Better:

~~~properties
app.routes[/catalog/v1]=https://catalog.example.test
~~~

With YAML:

~~~yaml
app:
  routes:
    "[/catalog/v1]": "https://catalog.example.test"
~~~

**Two different purposes:** `[ ]` instructs Binder to preserve the Map key; quotes in YAML ensure the YAML parser reads the bracketed key as a scalar string.

### 8.1. Example of Three Map Keys

~~~properties
app.routes[/key1]=value1
app.routes[/key2]=value2
app.routes./key3=value3
~~~

With target `Map<String,String>`, the result can be:

~~~text
"/key1" -> "value1"
"/key2" -> "value2"
"key3"  -> "value3"
~~~

The third key was unprotected, so the slash was stripped. This example comes directly from the Spring Boot documentation.

### 8.2. Never Fix YAML Parse Errors by Deleting Brackets

Snippet:

~~~yaml
app:
  routes:
    [/orders]: "backend"
~~~

can be interpreted by the YAML parser as different syntax. Quote it instead:

~~~yaml
app:
  routes:
    "[/orders]": "backend"
~~~

Deleting the brackets lets YAML parse, yet causes Binder to drop the slash in the key.

### 8.3. Application Paths Are Data, Not Property Structure

Map key `/api/v1` may be a real route. If Binder strips the slash, do not rush to change application code to look up `api/v1`; doing so masks a data bug and can collide with another route.

## 9. Dots in Map Keys Depend on the Value Type

For `Map<String, String>`, Spring Boot has an exception: dots inside keys of a **scalar map value** can be preserved.

~~~properties
app.labels.a.b=enabled
~~~

If target is:

~~~java
Map<String, String> labels;
~~~

the result can be:

~~~text
"a.b" -> "enabled"
~~~

However, if the target is:

~~~java
Map<String, Object> labels;
~~~

the exact same property can be represented as a nested structure:

~~~text
"a" -> {"b" -> "enabled"}
~~~

To get the literal key `a.b`, write:

~~~properties
app.labels[a.b]=enabled
~~~

Or YAML:

~~~yaml
app:
  labels:
    "[a.b]": "enabled"
~~~

### 9.1. Rule for `Map<String, POJO>`

When the value is a nested object, dots normally participate in field hierarchy. For example:

~~~properties
app.routes.orders.target=primary
~~~

is interpreted as Map key `orders` with property `target` on the value object, not literal Map key `orders.target`.

If the route name genuinely contains a dot, protect it with brackets:

~~~properties
app.routes[orders.v2].target=primary
~~~

### 9.2. Do Not Apply Rules Mechanically

Boot docs define scalar types as including enums and types in `java.lang` except `Object`. For custom POJOs or Map values typed as `Object`, verify how Binder interprets dots.

**Safe practice when a key containing dots is truly an identifier:** use explicit bracket notation and test the final key.

## 10. Collisions When Two Map Keys Normalize to the Same Name

Suppose two distinct routes are needed: `/orders` and `orders`.

If written:

~~~properties
app.routes./orders=serviceA
app.routes.orders=serviceB
~~~

key normalization can cause both entries to collapse onto the same key or yield unpredictable precedence outcomes.

Explicit form:

~~~properties
app.routes[/orders]=serviceA
app.routes.orders=serviceB
~~~

With `Map<String,String>`, tests should assert two independent keys exist. Never arbitrarily strip slashes or lowercase in the service to "fix" collisions when the domain truly distinguishes them.

### 10.1. Map Keys from Untrusted Data

If Map keys originate from requests or externally editable sources, validate character allowlists, length, element counts, and collisions. Binder converts configuration into objects; it does not replace input validation or security policies.

## 11. Environment Variables Are Not Arbitrarily Uppercased Property Names

Spring Boot recommends converting a **canonical property name** to an OS environment variable name in three steps:

1. Replace dots `.` with underscores `_`.
2. **Remove dashes `-`**.
3. Convert to uppercase.

Example:

~~~text
spring.main.log-startup-info
         |
         v
SPRING_MAIN_LOGSTARTUPINFO
~~~

Another key:

~~~text
app.gateway.connect-timeout
         |
         v
APP_GATEWAY_CONNECTTIMEOUT
~~~

Many people are used to turning every dash into an underscore, yet under Spring Boot's relaxed binding, that is not the recommended env name.

### 11.1. Mapping Table

| Canonical property | Environment variable |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `app.gateway.connect-timeout` | `APP_GATEWAY_CONNECTTIMEOUT` |
| `app.gateway.fail-fast` | `APP_GATEWAY_FAILFAST` |
| `app.client.retry-max-attempts` | `APP_CLIENT_RETRYMAXATTEMPTS` |
| `payment.gateway.api-key` | `PAYMENT_GATEWAY_APIKEY` |
| `my.main-project.person.first-name` | `MY_MAINPROJECT_PERSON_FIRSTNAME` |

This is how canonical keys map when the source is OS environment; custom `PropertySource`s may apply different rules.

### 11.2. Dashes Are Removed, Not Replaced with Underscores

Canonical:

~~~properties
app.client.retry-max-attempts=3
~~~

Wrong name per standard conversion:

~~~text
APP_CLIENT_RETRY_MAX_ATTEMPTS=7
~~~

Right name:

~~~text
APP_CLIENT_RETRYMAXATTEMPTS=7
~~~

If an operator uses the wrong name and the bean stays `3`, do not immediately conclude the environment source has low precedence. Verify whether the env name actually maps to the bean field.

### 11.3. Java Field vs. Canonical Key

Java:

~~~java
private int retryMaxAttempts;
~~~

Canonical property:

~~~properties
app.client.retry-max-attempts=3
~~~

Environment variable:

~~~text
APP_CLIENT_RETRYMAXATTEMPTS=7
~~~

Do not insert underscores between camelCase words following some convention outside Spring Boot.

## 12. List Indexes in Env Vars Must Have Underscores

Canonical:

~~~properties
my.service[0].other=alpha
my.service[1].other=beta
~~~

OS environment:

~~~text
MY_SERVICE_0_OTHER=alpha
MY_SERVICE_1_OTHER=beta
~~~

The index number is surrounded by underscores in the variable name, corresponding to `[0]`, `[1]` in the canonical key.

### 12.1. List of POJO Example

~~~properties
app.gateway.upstreams[0].name=primary
app.gateway.upstreams[0].url=https://primary.example.test
app.gateway.upstreams[1].name=secondary
app.gateway.upstreams[1].url=https://secondary.example.test
~~~

Correspondingly:

~~~bash
export APP_GATEWAY_UPSTREAMS_0_NAME="primary"
export APP_GATEWAY_UPSTREAMS_0_URL="https://primary.example.test"
export APP_GATEWAY_UPSTREAMS_1_NAME="secondary"
export APP_GATEWAY_UPSTREAMS_1_URL="https://secondary.example.test"
~~~

Do not use:

~~~text
APP_GATEWAY_UPSTREAMS0NAME
~~~

expecting Binder to understand `upstreams[0].name`. The documented form is `_0_`.

### 12.2. Lists from Env Still Have Replacement Semantics

If the base file has two upstreams while a higher-precedence environment source provides only `APP_GATEWAY_UPSTREAMS_0_NAME` and `APP_GATEWAY_UPSTREAMS_0_URL`, do not assume the second element is kept from the base file.

Supply the full desired List in the winning source, or build an explicit merge in business logic.

### 12.3. Non-Contiguous Indexes

If only element `[2]` is declared without `[0]` and `[1]`, results may be unexpected or binding may fail depending on target. Use contiguous indexes starting at 0, with tests if special cases must be supported.

## 13. Map Keys from Env Vars Can Be Lowercased

Per Boot docs, when binding a Map from system environment, Spring Boot lowercases the environment variable name before binding.

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "my.props")
public class MyMapsProperties {
    private final Map<String, String> values = new java.util.HashMap<>();

    public Map<String, String> getValues() {
        return values;
    }
}
~~~

Variable:

~~~text
MY_PROPS_VALUES_REGION=AP_SOUTHEAST
~~~

Result:

~~~text
values.get("region") = "AP_SOUTHEAST"
~~~

The **key** is typically lowercase `region`, while the **value** stays `AP_SOUTHEAST`.

### 13.1. When Business Logic Needs Case-Sensitive Keys

If Map key `US_EAST` differs from `us_east` in business semantics, OS environment variables are not a good source for preserving key casing. Use YAML/properties with literal keys or an appropriate structured config source, and test it.

### 13.2. Map Keys with Slashes, Colons, or Characters Hard to Express in Env

POSIX variable names normally cannot contain `/` or `[ ]`. You cannot turn `/orders` into `_ORDERS` and expect Binder to restore the slash in the key.

For Maps using URL paths, hostnames with special characters, or exact identifiers, prefer Config Data files with bracket notation or a structured config source supporting exact keys.

### 13.3. Do Not Lowercase Map Values

If values appear lowercased in business objects, check custom converters, setters, or other logic. The rule talks about **environment/key names**, not env var values.

## 14. Env-Style Rules Apply Only to Corresponding Sources

A subtle point: Spring Boot's handling for system environment names applies to `systemEnvironment` and sources whose names end with `-systemEnvironment`, per the docs.

If a test manually puts:

~~~java
Map<String, Object> values = Map.of(
    "APP_GATEWAY_CONNECTTIMEOUT", "2s");
~~~

into an arbitrary `MapPropertySource`, that test does not necessarily reproduce production OS environment behavior faithfully.

To verify naming, build a test harness with a source having system-environment semantics, or test with actual process/container environments in controlled integration tests.

### 14.1. Do Not Confuse @Value with @ConfigurationProperties

`@ConfigurationProperties` uses broader relaxed binding. `@Value` does not share the exact same level of relaxed binding support. When using `@Value` with placeholders, docs recommend canonical kebab-case names to take best advantage of property lookup.

~~~java
@Value("${app.gateway.connect-timeout}")
private Duration connectTimeout;
~~~

Here the placeholder uses the canonical name. Even so, when building a configuration group with multiple fields and collections, `@ConfigurationProperties` remains clearer and easier to test.

## 15. A Properly Named Variable Can Still Be Overridden by Another Source

Suppose the shell has:

~~~bash
export APP_GATEWAY_CONNECTTIMEOUT=2s
~~~

Yet the launch command is:

~~~bash
java -Dapp.gateway.connect-timeout=1s \
     -jar gateway.jar \
     --app.gateway.connect-timeout=500ms
~~~

In standard Spring Boot, command-line options take precedence over Java system properties and OS environment variables. The final value can be `500ms`, not `2s`.

### 15.1. Which Source Wins?

In many Boot applications, participating source types include:

~~~text
Config Data files
OS environment variables
Java system properties
SPRING_APPLICATION_JSON
command-line arguments
test-specific properties
~~~

Sources higher in the final precedence override overlapping keys from lower sources. Determine exact order according to your Boot version, profiles/imports, and test context rather than relying on one fixed guess for every app.

### 15.2. One Process Does Not Inherit Changes from Another Shell

Exporting a variable in terminal A does not update an already-running Java process or another container process. To reproduce cleanly:

~~~bash
APP_GATEWAY_CONNECTTIMEOUT=2s java -jar gateway.jar
~~~

This passes the env var strictly to the command's child process. With Docker/Kubernetes, configure the exact container running the JVM. After changing a deployment's environment, a restart/redeploy is normally needed for a new process to pick it up.

### 15.3. CLI Can Be Disabled by the Application

`SpringApplication.setAddCommandLineProperties(false)` omits CLI options from Environment. During diagnostics, verify how the application actually bootstraps before asserting every `--key=value` takes effect.

## 16. Profiles, Config Data Imports, and External Files

Suppose a developer edits:

~~~text
src/main/resources/application.yml
~~~

yet production runs with:

~~~text
file:./config/application-prod.yml
~~~

then the external source can contain List/Map overrides not visible in source code.

### 16.1. Config Data Order

Spring Boot defines rules for JAR-packaged files, JAR-packaged profile-specific files, external files, and external profile-specific files. Location groups and imports can create subtler orderings.

When values differ from expectations, identify which files loaded, active profiles, `spring.config.import`, and the winning source.

### 16.2. application.properties and application.yml in the Same Location

If both exist in the same location, Boot documentation states `.properties` takes precedence. Someone editing YAML without seeing effects might be shadowed by a same-named properties file.

### 16.3. Placeholders Inside Values

~~~properties
app.gateway.connect-timeout=${APP_TIMEOUT:5s}
~~~

Placeholders can be resolved via Environment. However, placeholders only determine scalar values; they do not change **List replacement** or **Map key binding** semantics.

## 17. Decision-Tree Diagnostic Workflow

~~~text
Start: Java configuration is wrong
           |
           v
Does @ConfigurationProperties bean exist?
   | no -> check scanning / registration
   |
   yes
   |
   v
Is the right property source loaded?
   | no -> check profile / import / location / process env
   |
   yes
   |
   v
Are canonical name and prefix right?
   | no -> fix kebab-case / env naming
   |
   right
   |
   v
Is there a higher-precedence source?
   | yes -> identify winning source
   |
   v
What is the target?
   |
   +-- List   -> replacement / index / nested fields
   |
   +-- Map    -> bracket key / dot / slash / lowercase
   |
   +-- Scalar -> conversion / validation
   |
   v
Write reproducing test -> fix right source -> verify bean
~~~

The decision tree helps avoid a common bad habit: adding yet another override to "force" an outcome without understanding the original cause.

## 18. Checking Environment and Beans in Tests

A test can verify the scalar source:

~~~java
import org.springframework.core.env.Environment;

@Autowired Environment environment;

@Test
void timeoutPropertyIsVisible() {
    assertThat(environment.getProperty(
        "app.gateway.connect-timeout"))
        .isEqualTo("2s");
}
~~~

Then verify type conversion:

~~~java
@Autowired GatewayProperties properties;

@Test
void timeoutHasBeenBound() {
    assertThat(properties.connectTimeout())
        .isEqualTo(Duration.ofSeconds(2));
}
~~~

If the first check fails, look into sources, prefix, or precedence. If the first check passes yet the bean is wrong, look into bean registration, conversion, setters/constructors, validation, and custom binding.

### 18.1. Do Not Expect Environment to Return an Entire List as One String

When sources provide indexed keys, `environment.getProperty("app.gateway.upstreams")` returning null does not prove the List is empty. Test the `properties.upstreams()` bean or individual loaded keys instead.

### 18.2. Avoid Printing Entire ConfigProps

A `@ConfigurationProperties` record can hold secrets, and Java records auto-generate `toString()` containing all fields. Never print the entire object via logger during investigation.

## 19. Actuator Helps Trace Sources — Provided Security Is Enforced

When properly configured, Spring Boot Actuator offers endpoints:

- `/actuator/env`: helps inspect Environment/property sources per allowed visibility level.
- `/actuator/configprops`: helps inspect `@ConfigurationProperties` beans and bound values per configured visibility level.

Never expose these two endpoints publicly. Require authentication, authorization, sanitization, and tests proving credentials never leak. `show-values` options or masking behavior can vary by Boot version.

Good operational practice: log **error codes, allowlisted key names, source types, and expected requirements**, never raw passwords, tokens, or the entire Environment.

### 19.1. TRACE/DEBUG Is Not the Default Answer

Enabling system-wide verbose logging can reveal profiles/sources yet simultaneously leak sensitive details or flood logs. If needed, use a mock environment with fake secrets and restrict loggers, retention, and viewer permissions.

## 20. Testing List Replacement with SpringBootTest

With `application.yml` containing two upstreams and `application-prod.yml` containing one upstream:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionGatewayConfigTest {

    @Autowired GatewayProperties properties;

    @Test
    void productionListReplacesBaseList() {
        assertThat(properties.upstreams())
            .extracting(GatewayProperties.Upstream::name)
            .containsExactly("primary");
    }
}
~~~

This test requires real application/test configuration containing both files as in the example. It demonstrates verifying **whole List replacement**, rather than asserting only that `primary` exists.

### 20.1. Testing Missing Nested List Fields

If production specifies only `upstreams[0].name`, add assertions on `url` and `timeout` to catch missing fields. For mandatory fields, use validation to fail fast at startup instead of passing null to services.

### 20.2. Testing with Real Config Data

If the goal is testing profile-specific precedence, use `@ActiveProfiles` and real Config Data files rather than constructing a pre-built list in Java code.

## 21. Testing Map Special Keys

Target:

~~~java
@ConfigurationProperties(prefix = "app")
public record RouteStrings(
    Map<String, String> routes
) {}
~~~

YAML:

~~~yaml
app:
  routes:
    "[/api/v1]": service-a
    orders: service-b
~~~

Test:

~~~java
assertThat(properties.routes())
    .containsEntry("/api/v1", "service-a")
    .containsEntry("orders", "service-b");
~~~

Such a test verifies both **keys** and **values**, not merely that the Map has two entries.

### 21.1. Testing Keys with Dots

With `Map<String, Object>` and key `team.alpha`, assert that `keySet()` contains `"team.alpha"` rather than only `"team"`. Wrap the key in brackets in YAML to preserve the literal key.

### 21.2. Testing Collisions

Declare `[/orders]` and `orders` as two independent keys and assert both. If one key disappears, revisit syntax/sources before changing business lookup code.

## 22. Testing Env Var Naming

When simulating env vars, pay attention to **property source type**. Spring Boot applies env-style rules to `systemEnvironment` or sources ending in `-systemEnvironment`. An arbitrary `MapPropertySource` with uppercase keys does not necessarily match real OS environment behavior.

A test can verify:

~~~text
Canonical: app.client.retry-max-attempts
Expected OS env: APP_CLIENT_RETRYMAXATTEMPTS
~~~

When running integration tests with containers or mock process environments, assert the `retryMaxAttempts` bean has the right value. Also test a List index such as `MY_SERVICE_0_OTHER`.

### 22.1. Do Not Mutate System.getenv Arbitrarily

`System.getenv()` is not a mutable map meant for simple set/unset via standard Java APIs. Test libraries mutating process environments have varying JVM/module restrictions. Prefer a test harness with explicit OS env/source semantics, or separate naming tests from source-precedence tests.

### 22.2. Testing Map Lowercasing

Supply `MY_PROPS_VALUES_REGION=AP_SOUTHEAST` in an appropriate test environment, asserting key `region` and value `AP_SOUTHEAST`. If business logic requires uppercase keys, move to a source supporting literal keys.

## 23. ApplicationContextRunner for Small Binding Cases

Spring Boot provides `ApplicationContextRunner` to build a context with property values and inspect outcomes without full `@SpringBootTest`.

Model:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sample")
public record SampleProperties(
    List<String> servers,
    Map<String, String> labels
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class SampleBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(SampleTestConfig.class);

    @Test
    void bindsCollections() {
        runner.withPropertyValues(
            "sample.servers[0]=https://prod.example.test",
            "sample.labels[region]=ap-southeast"
        ).run(context -> {
            SampleProperties p = context.getBean(SampleProperties.class);

            assertThat(p.servers())
                .containsExactly("https://prod.example.test");
            assertThat(p.labels())
                .containsEntry("region", "ap-southeast");
        });
    }
}
~~~

`SampleTestConfig` must register `SampleProperties` via `@EnableConfigurationProperties(SampleProperties.class)` or an equivalent mechanism. The example above tests only one set of values. When testing merge/replacement **across multiple sources**, construct separate `PropertySource`s with properly simulated precedence, or use Config Data integration tests.

## 24. A Complete Production Scenario

Suppose a Kubernetes service hits three symptoms:

1. Upstream list has one element even though the base file has two.
2. Route `/payments` is unreachable.
3. Timeout stayed unchanged after an operator added an env var.

Base config:

~~~yaml
app:
  gateway:
    upstreams:
      - name: primary
        url: "https://primary.example.test"
      - name: backup
        url: "https://backup.example.test"
    routes:
      /payments: "payment-service"
    connect-timeout: 5s
~~~

Production file:

~~~yaml
app:
  gateway:
    upstreams:
      - name: production
        url: "https://prod.example.test"
~~~

Deployment:

~~~yaml
env:
  - name: APP_GATEWAY_CONNECT_TIMEOUT
    value: "2s"
~~~

### 24.1. List Symptom

The production file declares its own List and therefore replaces the entire base List. To retain backup, declare backup directly inside the production list, or design an explicit merge source.

### 24.2. Map Symptom

Key `/payments` requires bracket notation:

~~~yaml
app:
  gateway:
    routes:
      "[/payments]": "payment-service"
~~~

Do not edit business code to look up `payments` if the path genuinely needs the slash.

### 24.3. Env Symptom

Canonical name `app.gateway.connect-timeout` converts to:

~~~text
APP_GATEWAY_CONNECTTIMEOUT
~~~

not `APP_GATEWAY_CONNECT_TIMEOUT` per canonical rules. Fix the variable name in the container spec, redeploy, and verify the bean receives `2s`.

### 24.4. Safe Resolution Order

1. Confirm the production profile and loaded external files.
2. Inspect the winning List source; never assume merging.
3. Inspect Map keys post-binding; fix brackets.
4. Inspect the env name injected into the exact container.
5. Verify no CLI/system property overrides the timeout.
6. Write a reproducing integration test.
7. Redeploy/restart per procedure.
8. Verify live behavior of routes and upstreams, not just context startup.

## 25. Common Design Pitfalls

### 25.1. Using Profiles to "Patch" a List Element

When a higher profile sets only `items[0].name`, do not expect other fields from lower sources to remain populated. Declare the complete item.

### 25.2. Assuming Maps Replace Wholly Like Lists

Maps can keep un-overridden keys from lower sources. If replacement is intended, build a dedicated policy.

### 25.3. Removing Brackets to Avoid YAML Syntax Errors

Quote the bracketed key; do not remove brackets. Removing brackets causes Binder to mangle literal Map keys.

### 25.4. Looking Only at Map Key Names Without Checking Generic Value Types

`Map<String,String>` and `Map<String,Object>` handle dots differently. Verify the target type.

### 25.5. Lowercasing All Map Values

Env/key names can be lowercased; Map values are not automatically lowercased because of that. If case distinction matters, inspect target value handling.

### 25.6. Inserting Underscores Between All Java camelCase Words

Canonical `retry-max-attempts` must become `RETRYMAXATTEMPTS` when converting to env names under Boot rules, not `RETRY_MAX_ATTEMPTS`.

### 25.7. Exporting Env Vars in a Shell That Does Not Run Java

Process/container scope matters. Set env vars in the exact command or deployment container.

### 25.8. Seeing a Property in Environment and Assuming the Bean Is Right

There could be wrong prefixes, wrong generic types, missing bean registration, conversion failures, or collection replacement. Inspect the bean.

### 25.9. Dumping the Entire Environment to Debug

Can leak secrets and create unsafe logs. Inspect only needed key/source metadata.

### 25.10. Editing Multiple Config Data Sources at Once

Without knowing which source is winning, changing YAML, external properties, and env together masks the root cause. Isolate, fix one place, write a test, and verify.

## 26. Symptom and Fix Table

| Symptom | Common cause | Fix |
| --- | --- | --- |
| List loses base elements | Higher source replaces whole List | Declare full List in winning source |
| List item loses url/timeout | List nested fields do not merge | Supply all fields and validate |
| Need to append Lists yet cannot | Binder does not auto-concat Lists | Merge explicitly in application |
| Map retains an old key | Maps can aggregate across sources | Design replacement if needed |
| Key `/foo` becomes `foo` | Missing literal key brackets | Use `[/foo]` |
| YAML bracket misparsed | Key unquoted | Use `"[/foo]"` |
| `a.b` becomes nested Map | Map value is object, unbracketed | Use `[a.b]` |
| Env Map key lowercased | Env names are lowercased | Use another source if keys are case-sensitive |
| Env var fails to override | Non-standard variable name | Remove `-` when converting canonical |
| Env List index ignored | Missing `_0_` | Use `MY_LIST_0_NAME` |
| File edited yet bean unchanged | Another source wins or stale process | Check precedence/restart |
| Prefix scalar lookup null | List uses indexed children | Inspect child keys and bean |
| Binder throws error | Type conversion/validation | Check target type and constraints |
| Actuator shows sensitive data | Inappropriate endpoint/auth/masking | Secure, sanitize, and test |

## 27. Production Fix Checklist

- [ ] Identified bean, prefix, and target field.
- [ ] Actual files/profiles/imports are being loaded.
- [ ] Listed sources sharing the key via safe metadata.
- [ ] Treated Lists as whole replacement, not auto-merging.
- [ ] Production list declares all required elements completely.
- [ ] Nested fields in List items are identified and validated.
- [ ] If appending is needed, implemented and tested explicit merge logic.
- [ ] Treated Maps under cross-source key aggregation rules.
- [ ] Literal Map keys with `/` or special characters use `[ ]`.
- [ ] YAML bracketed keys are quoted.
- [ ] Map keys with dots analyzed according to generic value type.
- [ ] Case-sensitive Map keys do not rely on lowercasing env naming.
- [ ] Canonical property names use kebab-case.
- [ ] Env names replace dots with underscores and remove dashes.
- [ ] List indexes via env use `_0_`, `_1_`.
- [ ] Env vars actually exist inside the right process/container.
- [ ] No higher-precedence source overrides unintentionally.
- [ ] Bean is registered and type conversion succeeds.
- [ ] Integration tests assert exact List/Map entries and scalar values.
- [ ] Never print secrets or dump the entire Environment.
- [ ] Restarted/redeployed when changing runtime configuration.
- [ ] Observed actual runtime behavior after fixing, not only startup.

## 28. Applied Exercises

### Exercise A — List Replacement

~~~properties
# base
app.nodes[0].name=a
app.nodes[1].name=b
~~~

~~~properties
# prod
app.nodes[0].name=prod
~~~

When the production profile wins, will the List keep node `b`?

**Guidance:** no. The winning source's List replaces the entire list.

### Exercise B — Nested List Fields

The base file has `app.nodes[0].url` and `app.nodes[0].timeout`. The prod file has only `app.nodes[0].name`.

Will url/timeout be merged from the base item?

**Guidance:** do not rely on merging nested properties of Lists. Declare needed fields in the winning source.

### Exercise C — Map Merging

~~~properties
# base
app.routes.orders.target=primary
app.routes.orders.description=Orders
~~~

~~~properties
# prod
app.routes.orders.target=prod
app.routes.payments.target=prod-payment
~~~

Can `orders.description` still remain?

**Guidance:** Map nested fields can be aggregated across multiple sources, unlike Lists.

### Exercise D — Map Path Key

Target `Map<String,String>` wants key `/v1/orders`. Write the proper property.

**Guidance:**

~~~properties
app.routes[/v1/orders]=order-service
~~~

### Exercise E — Map Dot Key

Target `Map<String,Object>` needs literal key `team.alpha`.

**Guidance:**

~~~yaml
app:
  labels:
    "[team.alpha]": enabled
~~~

### Exercise F — Environment Variable

Canonical property is `app.client.retry-max-attempts`.

**Guidance:** appropriate env name is `APP_CLIENT_RETRYMAXATTEMPTS`.

### Exercise G — Indexed List Env

Canonical `my.service[0].other`.

**Guidance:** `MY_SERVICE_0_OTHER`.

### Exercise H — Map Case from Environment

Env `MY_PROPS_VALUES_REGION=AP_SOUTHEAST`.

**Guidance:** Map key `region`, value `AP_SOUTHEAST`.

## 29. Summary

Three symptoms — **replaced Lists**, **wrong Map keys**, and **misnamed env vars** — are rarely random bugs. They are explainable consequences of Spring Boot's externalized configuration rules:

- **List:** a higher-precedence source re-declaring a List normally replaces the whole thing; it does not auto-append or merge nested item fields.
- **Map:** can receive keys and nested fields from multiple sources; on identical paths precedence decides. Use bracket notation to keep literal keys with special characters.
- **Dots in Map keys:** interpretation depends on scalar vs. object value; when a literal key is needed, use brackets.
- **Environment variables:** from canonical name, `.` → `_`, strip `-`, uppercase; List indexes use `_0_`. Map keys from system environment can be lowercased.
- **Diagnostics:** identify the winning source and actual key, inspect both `Environment` and `@ConfigurationProperties` beans, write reproducing tests, then fix the right source.

Mastering these steps helps developers and operators fix the exact root cause, maintain consistent behavior across local/test/staging/production, and avoid putting secrets into logs while debugging.

### References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding)
- [Spring Boot Reference — Binding Maps](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps)
- [Spring Boot Reference — Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables)
- [Spring Boot Reference — Merging Complex Types](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types)
- [Spring Boot API — Binder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html)
