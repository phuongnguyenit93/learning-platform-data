# Map Keys via Environment Variables and Case-Preservation Limitations in Spring Boot

Spring Boot lets you configure a `Map<String, String>` through operating system environment variables. This is very useful when deploying applications on servers, Docker, or Kubernetes because each environment can supply different key–value pairs without modifying source code. However, the *relaxed binding* mechanism has an important limitation:

> **When Spring Boot binds environment variables into a Map via `@ConfigurationProperties`, the keys in the Map are converted to lowercase. The values of the environment variables preserve their original uppercase and lowercase letters.**

For example, the environment variable `MY_PROPS_VALUES_KEY=VALUE` produces the entry `{"key": "VALUE"}` in the corresponding Map. The key name `KEY` becomes `key`, while the value `VALUE` remains `VALUE`.

This lesson focuses on Spring Boot 3.3.x and Java 21; it distinguishes environment variable names, property paths, and actual keys in the Map, and then explains how to handle cases where external systems require case-sensitive key names.

## 1. Why are Maps used in configuration?

Some configurations have dynamic lists of keys that are not fixed at compile time. For instance, an application might store integration labels, partner names, or routing rules:

~~~yaml
my:
  props:
    values:
      region: vietnam
      team: platform
      mode: production
~~~

We want to bind `my.props.values` into a Java object:

~~~java
Map<String, String> values
~~~

Corresponding result:

~~~text
values["region"] = "vietnam"
values["team"]   = "platform"
values["mode"]   = "production"
~~~

When the application runs across multiple environments, operators may want to declare those values via environment variables instead of creating a separate YAML file. That is when you need to understand the rules for converting environment variable names into configuration paths and how the Binder handles **dynamic Map keys**.

## 2. Recap of relaxed binding from environment variables

Spring Boot supports several ways to write property names, for example:

~~~text
my.service.client-id
my.service.clientId
MY_SERVICE_CLIENTID
~~~

For environment variables, Spring Boot documentation recommends converting canonical property names (*canonical kebab-case*) as follows:

1. Replace dots `.` separating property levels with underscores `_`.
2. Remove hyphens `-` within property names.
3. Convert to uppercase.

Examples:

| Canonical property name | Corresponding environment variable |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `my.props.values` | `MY_PROPS_VALUES` |
| `app.client.connect-timeout` | `APP_CLIENT_CONNECTTIMEOUT` |

This rule allows supplying configuration using variable names compatible with operating systems and deployment tools. For a fixed Java field such as `connectTimeout`, relaxed binding enables receiving the value from `APP_CLIENT_CONNECTTIMEOUT`.

However, with a **Map**, the last segment of the property name is not necessarily the name of a fixed Java field. That segment can be **a data key chosen by an operator**. Therefore, letter-case normalization can lose information that another system requires to remain intact.

### Environment variable and value are two separate parts

~~~text
MY_PROPS_VALUES_CLIENT=SomeValue
|____________________| |_______|
    variable name        value
~~~

In the example, the variable name contains the path prefix `MY_PROPS_VALUES` and the dynamic key `CLIENT`. Only the variable **name** is used to determine the path and Map key during binding. The `SomeValue` part is value data and is not automatically converted to `somevalue`.

## 3. Official example of Map binding

Create the configuration class:

~~~java
package com.example.configdemo;

import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "my.props")
public class MyMapsProperties {

    private final Map<String, String> values = new HashMap<>();

    public Map<String, String> getValues() {
        return values;
    }
}
~~~

This class has prefix `my.props` and field `values`, so sub-properties of `my.props.values` can be bound as entries in the Map.

Register the configuration in the Spring Boot application:

~~~java
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
~~~

`@ConfigurationPropertiesScan` allows Spring Boot to detect classes annotated with `@ConfigurationProperties` within the scanned packages. If the project already registers configuration via `@EnableConfigurationProperties(MyMapsProperties.class)`, that mechanism can be used instead.

On Linux/macOS, set the environment variable:

~~~bash
export MY_PROPS_VALUES_KEY=VALUE
java -jar config-demo.jar
~~~

After binding, the Map contains:

~~~text
key   → VALUE
~~~

That is:

~~~java
properties.getValues().get("key");   // "VALUE"
properties.getValues().get("KEY");   // typically null if there is no separate "KEY" key
~~~

This is the core example described in the Spring Boot 3.3 documentation section *Binding Maps From Environment Variables*.

## 4. Key names are always lowercased, values are preserved

Consider the environment variables:

~~~bash
export MY_PROPS_VALUES_REGION="APAC"
export MY_PROPS_VALUES_TEAM="PlatformOps"
export MY_PROPS_VALUES_TOKENLABEL="xYz123"
~~~

With `MyMapsProperties` above, the Map receives these entries:

~~~text
{
  "region":     "APAC",
  "team":       "PlatformOps",
  "tokenlabel": "xYz123"
}
~~~

Two different transformations take place:

| Part | Input data | Result |
| --- | --- | --- |
| Map key name | `REGION` | `region` |
| Map value | `APAC` | `APAC` |
| Map key name | `TEAM` | `team` |
| Map value | `PlatformOps` | `PlatformOps` |
| Map key name | `TOKENLABEL` | `tokenlabel` |
| Map value | `xYz123` | `xYz123` |

What to avoid is inferring that because environment variable names are typically uppercase, the Map will preserve uppercase key names. **There is no such mechanism in Spring Boot's standard relaxed binding from environment variables into a Map.**

Conversely, do not infer that all data passing through the Binder gets converted to lowercase: **only the variable name is normalized to determine property/Map key names; values are not lowercased**.

This is an important distinction when values contain identifiers, case-sensitive strings, URLs, filenames, or business content.

## 5. Reading the Map in a Java application

Create an `ApplicationRunner` to observe data after the application starts:

~~~java
package com.example.configdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ConfigPrinter {

    @Bean
    ApplicationRunner printMap(MyMapsProperties properties) {
        return args -> {
            properties.getValues()
                    .forEach((key, value) ->
                            System.out.println(key + " = " + value));

            System.out.println(
                    "Get lowercase key: "
                            + properties.getValues().get("region"));

            System.out.println(
                    "Get uppercase key: "
                            + properties.getValues().get("REGION"));
        };
    }
}
~~~

With environment variable `MY_PROPS_VALUES_REGION=APAC`, the lookup output is:

~~~text
region = APAC
Get lowercase key: APAC
Get uppercase key: null
~~~

The line order in `forEach` may not be fixed because the configuration class uses `HashMap`. In exercises requiring consistent output, you can sort entries when printing or check specific keys individually.

For `Map<String, String>`, `get("region")` and `get("REGION")` are two different lookups. `HashMap` compares String keys case-sensitively by default; the Binder created a lowercase key, so querying with uppercase does not find that entry.

**Important point:** this is the behavior of the Map **after binding**. Java's `Map` itself does not arbitrarily convert key names to lowercase; Spring Boot's Binder and environment variable source are what perform the normalization.

## 6. Why does Spring Boot normalize Map keys from environment variables?

Many operating systems and deployment tools restrict which characters can be used in environment variable names. Typically variable names follow the form:

~~~text
LETTERS_DIGITS_AND_UNDERSCORES
~~~

Therefore, Spring Boot introduces relaxed binding to connect names like:

~~~text
MY_PROPS_VALUES_KEY
~~~

to the property structure:

~~~text
my.props.values.key
~~~

When binding from the `systemEnvironment` property source, Spring Boot treats environment variable names in lowercase form. For regular Java fields, this rarely causes issues because `firstName`, `first-name`, or `FIRSTNAME` can all bind to the same field via relaxed binding.

However, if the end of the name represents **key data** rather than a predefined field name, the difference becomes obvious:

~~~text
Input:     MY_PROPS_VALUES_ACCOUNTID=ABC
Map key:   accountid
Map value: ABC
~~~

You cannot recover the original casing of `AccountID`, `ACCOUNTID`, or `accountId` solely from the bound key `accountid`. Multiple spellings normalize to the same form.

### Scope of the conclusion

The conclusion "Map keys are lowercased" applies to **binding from environment variables via Spring Boot's Binder**, especially when using `@ConfigurationProperties`. It does not mean every key name in every Java `Map` or every configuration source gets lowercased.

For example, `Map.of("ClientID", "ABC")` created directly by a developer still has key `ClientID`. A YAML file written with key-preserving syntax can provide different keys; those cases must be evaluated according to their respective source and binding syntax.

## 7. Do not confuse with `Environment.getProperty` and `System.getenv`

There are three distinct operations:

1. Reading a raw operating system environment variable.
2. Reading a single property's value from Spring `Environment`.
3. Binding a group of properties into a `Map` using `@ConfigurationProperties`.

### 7.1. `System.getenv(...)` reads the raw variable

~~~java
String raw = System.getenv("MY_PROPS_VALUES_KEY");
~~~

This call reads the value of the variable with the given name according to OS/JVM rules. If the variable holds `VALUE`, the result is `VALUE`. It **does not create a Map with key `KEY`**; the string `"MY_PROPS_VALUES_KEY"` is simply the argument the developer passed to look up the variable.

You can list the environment variable map seen by the JVM via `System.getenv()`, though how operating systems handle uppercase/lowercase in **variable names** can differ. For instance, Windows usually treats environment variable names case-insensitively, whereas on Unix systems they are typically case-sensitive.

### 7.2. `Environment.getProperty(...)` reads a single property

~~~java
String value = environment.getProperty("my.props.values.key");
~~~

This API asks Spring `Environment` for the resolved value of a property path. It does not require creating the `MyMapsProperties` bean and does not mean the full Map binding rules apply to that call.

### 7.3. `@ConfigurationProperties` binds a group of keys

~~~java
MyMapsProperties props = ...;
Map<String, String> values = props.getValues();
~~~

This Map object reflects the result after the Binder parsed and converted each property name into its corresponding key.

| Operation | Input | Primary result |
| --- | --- | --- |
| `System.getenv("MY_PROPS_VALUES_KEY")` | Raw variable name | Environment variable string value |
| `Environment.getProperty("my.props.values.key")` | Property name | Final resolved string value if found |
| `MyMapsProperties.getValues()` | Configuration processed by Binder | Map with keys created by Binder |

Thus, seeing `System.getenv(...)` return `"VALUE"` does not prove the Map will contain an uppercase `"KEY"` key. These are two different processing layers.

## 8. Limitations when case-sensitive key names are needed

Suppose an external system requires exact identifier names:

~~~text
ClientID
clientId
CLIENTID
~~~

In certain protocols or APIs, these could be three distinct data keys. If you try to encode them as segments of environment variable names and rely on relaxed binding to build a Map, Spring Boot lacks sufficient information to reconstruct each original spelling.

Expected example:

~~~java
Map<String, String> externalNames = Map.of(
        "ClientID", "A",
        "clientId", "B",
        "CLIENTID", "C"
);
~~~

Such a Java Map is valid because the three key strings are distinct. But if you use environment variable names to represent them, name normalization prevents guaranteeing that all three exact names are preserved and distinguished after binding.

**Do not rely on environment variable casing to encode Map key casing.** Changing variable names to `MY_PROPS_VALUES_ClientID`, `MY_PROPS_VALUES_CLIENTID`, or mixed-case forms does not produce a case-preservation mechanism guaranteed by Spring Boot.

### 8.1. Example of an API integration failure

Suppose the program needs to construct a payload:

~~~json
{
  "ClientID": "partner-123",
  "Mode": "Fast"
}
~~~

If keys are taken from a Map bound via environment variables, the result may be:

~~~json
{
  "clientid": "partner-123",
  "mode": "Fast"
}
~~~

For an API that checks field names case-sensitively, the second payload may be rejected. The string value `Fast` is still correct; the **field name** is what changed.

This example shows the limitation affects not only `map.get("ClientID")` lookups, but also JSON generation, external system parameters, or business mapping tables requiring exact spelling.

## 9. Using YAML with bracket notation when keys must be preserved

For file-based configuration sources, Spring Boot supports **bracket notation** to preserve Map key names containing special characters. You can use it when key names must be represented accurately.

Example:

~~~yaml
my:
  props:
    values:
      "[ClientID]": "partner-123"
      "[Mode]": "Fast"
      "[X-API-Key]": "demo-value"
      "[/external/key]": "enabled"
~~~

In YAML, key names containing square brackets `[ ... ]` should be wrapped in quotes so the parser reads them as proper YAML key strings.

When binding properties from this document into a Map, bracket notation tells Spring Boot to treat the bracketed part as an **intact key** to preserve, rather than parsing or stripping characters according to property naming rules.

Expected lookup examples:

~~~java
values.get("ClientID");       // "partner-123"
values.get("Mode");           // "Fast"
values.get("X-API-Key");      // "demo-value"
values.get("/external/key");  // "enabled"
~~~

### Why doesn't bracket notation solve the environment variable limitation on its own?

Standard operating system environment variables use letters, digits, and underscores in names; names containing `[` or `]` are not a universal deployment practice. More importantly, Spring Boot specifies that **environment variable names are lowercased before Map binding**.

Therefore, do not assume you can set a variable name like `MY_PROPS_VALUES_[ClientID]` and the Binder will preserve `ClientID`. Bracket notation is documented for **keys in configuration files**; the environment variable mechanism has its own rules and still carries the uppercase limitation.

### 9.1. `application.properties` files

You can also write bracketed keys:

~~~properties
my.props.values.[ClientID]=partner-123
my.props.values.[Mode]=Fast
my.props.values.[X-API-Key]=demo-value
~~~

Here `[ ... ]` shows how the Binder distinguishes an intact key segment. File syntax is much better suited for keys needing uppercase letters or special characters.

### 9.2. Keys containing dots or slashes

With `Map<String, String>`, according to Spring Boot documentation, keys containing dots may be preserved in some cases even without brackets. However, with `Map<String, Object>` or nested Map structures, dots may be treated as level separators.

Example:

~~~yaml
my:
  props:
    values:
      "[api.v1]": "v1"
      "[/health]": "healthy"
~~~

Brackets make the intent explicit: `api.v1` and `/health` are two **data keys** of the Map, not property paths to split further.

When key names must be kept exact, choosing bracketed notation in a configuration file is clearer and easier to verify.

## 10. What to do if you still want to supply data via environment variables?

When preserving case matters, **separate technical configuration** from **business key names** instead of trying to derive business key names from environment variable names.

### 10.1. Approach A: hardcode keys in code, take values from environment variables

Suppose an external API requires the exact field names `ClientID` and `Mode`. You can configure values via regular properties:

~~~bash
export APP_PARTNER_CLIENTID="partner-123"
export APP_PARTNER_MODE="Fast"
~~~

Bind into Java fields:

~~~java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(String clientId, String mode) {
}
~~~

When building the Map for the external API:

~~~java
Map<String, String> payload = Map.of(
        "ClientID", partnerProperties.clientId(),
        "Mode", partnerProperties.mode()
);
~~~

In this way:

- `clientId` and `mode` are fixed configuration fields, suitable for relaxed binding.
- `ClientID` and `Mode` are fixed key strings in code to satisfy the external API contract.
- Operators change **values** through environment variables, not **key spelling**.

This is usually the simplest approach when the set of business keys is known beforehand.

### 10.2. Approach B: place case-sensitive mappings in a configuration file

Example deployment file `/etc/my-service/external-keys.yml`:

~~~yaml
my:
  props:
    values:
      "[ClientID]": "partner-123"
      "[Mode]": "Fast"
~~~

Then integrate the file into Config Data loading using `spring.config.import` or an appropriate location, for example inside a loaded `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/my-service/external-keys.yml"
~~~

Use a mandatory location instead of `optional:` if a missing file should halt application startup. This approach works well when the set of keys varies per environment while exact key spelling must be preserved.

The bound key set can still be affected by **multiple PropertySources**. If the same key is also declared via environment variables, verify the effective value and final key form rather than assuming the file always wins.

### 10.3. Approach C: carry the whole map as a single environment variable containing JSON

If the deployment system only conveniently provides environment variables and the mapping has dynamic case-sensitive keys, you can place the **entire JSON into the value of a single variable**:

~~~bash
export APP_EXTERNAL_MAP_JSON='{"ClientID":"partner-123","Mode":"Fast"}'
~~~

In this case, `APP_EXTERNAL_MAP_JSON` is just the name of one fixed property; the strings `ClientID` and `Mode` live **inside the JSON value**, so they are not keys extracted from an environment variable name.

Example parsing JSON with Jackson, if the project includes Jackson Databind:

~~~java
package com.example.configdemo;

import java.util.Map;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ExternalMapParser {

    public static Map<String, String> fromJson(String json) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        return mapper.readValue(
                json,
                new TypeReference<Map<String, String>>() {});
    }
}
~~~

Retrieve the value using `Environment`:

~~~java
String json = environment.getRequiredProperty("app.external.map-json");
Map<String, String> externalMap = ExternalMapParser.fromJson(json);

System.out.println(externalMap.get("ClientID")); // partner-123
System.out.println(externalMap.get("Mode"));     // Fast
~~~

Here, key preservation is determined by the **JSON parser and JSON data**. The example explicitly parses the JSON value; do not assume Spring Boot's Binder automatically converts arbitrary JSON strings into `Map<String,String>`.

If the JSON is invalid, the parser will throw an error. For critical deployment configurations, validate schema, required fields, and data types before using them.

## 11. Other limitations when specifying Map keys via environment variables

Beyond lowercasing, representing a Map with environment variables has several other caveats to remember.

### 11.1. Underscores act as path separators

Example:

~~~text
MY_PROPS_VALUES_REGION=APAC
~~~

The `_` character separates parts of the property path. Do not assume an underscore in a variable name remains an intact `_` character of the Map key. If a business name strictly requires underscores, consider YAML bracket notation or passing a structured data value.

### 11.2. Hyphens in property names are stripped when converted to env vars

Canonical property name:

~~~text
app.client.retry-count
~~~

becomes:

~~~text
APP_CLIENT_RETRYCOUNT
~~~

Thus, an environment variable name cannot by itself express every original separator of a business key name. For fixed keys defined via Java fields, relaxed binding handles this normalization well. For dynamic keys requiring character-by-character preservation, that mechanism may be unsuitable.

### 11.3. Names containing dots, slashes, or special characters

Map keys like `a.b`, `/health`, or `X-API-Key` can contain characters that env var names cannot represent directly or that may be parsed into multiple property levels. Configuration files with bracket notation clearly specify that this is **a single key**.

### 11.4. Potential name collisions after normalization

Suppose external key names distinguish:

~~~text
ClientID
clientId
clientid
~~~

After the normalization step in the environment variable binding flow, different spellings may become indistinguishable. Do not design configurations assuming variables differing only by case will produce independent Map entries.

If you need two distinct business keys differing by case, use a data transport format that preserves original key names.

## 12. Distinguishing `Map<String, String>` from `Map<String, Object>`

Map binding also depends on the **value type**. Example:

~~~properties
my.map.a.b=c
~~~

With `Map<String, String>`, Spring Boot documentation notes cases where dots can be kept inside a scalar key, corresponding to key `a.b`.

However, with `Map<String, Object>`, dots can produce a nested Map structure:

~~~text
a
└── b = c
~~~

Deliberate bracket notation:

~~~properties
my.map.[a.b]=c
~~~

shows that key `a.b` is a single entry rather than two levels.

Distinguish two questions:

1. **Will the key be split or lose characters?** This depends on bracket notation, the Map type, and property path parsing.
2. **Will the key preserve uppercase letters when coming from an environment variable?** In Map binding from environment variables according to Spring Boot 3.3 documentation, keys are still lowercased.

Brackets help preserve keys in sources that support that syntax; they **do not reverse** lowercasing of environment variable names.

## 13. Practicing on Linux/macOS and Windows

### 13.1. Linux/macOS

In the directory containing the application JAR:

~~~bash
export MY_PROPS_VALUES_KEY="VALUE"
export MY_PROPS_VALUES_REGION="APAC"
java -jar config-demo.jar
~~~

Check the Map using the `MyMapsProperties` bean. Expected keys are `key` and `region`.

When running multiple times in the same shell, exported variables may remain. You can clean up variables when finished:

~~~bash
unset MY_PROPS_VALUES_KEY MY_PROPS_VALUES_REGION
~~~

### 13.2. Windows PowerShell

~~~powershell
$env:MY_PROPS_VALUES_KEY = "VALUE"
$env:MY_PROPS_VALUES_REGION = "APAC"
java -jar config-demo.jar
~~~

Remove the PowerShell session variables after practicing:

~~~powershell
Remove-Item Env:MY_PROPS_VALUES_KEY
Remove-Item Env:MY_PROPS_VALUES_REGION
~~~

The example is presented from the perspective of Spring Boot consuming environment variables already received by the Java process. OS-specific variable naming and case-handling rules may differ; the exercise focuses on the Binder output.

### 13.3. Docker Compose

Example environment variable configuration for the application:

~~~yaml
services:
  app:
    image: example/config-demo:latest
    environment:
      MY_PROPS_VALUES_KEY: "VALUE"
      MY_PROPS_VALUES_REGION: "APAC"
~~~

Both variables are passed into the container as name–value pairs. When Spring Boot binds to `MyMapsProperties`, entries still have lowercase keys. Even though the Compose file uses uppercase in variable names, Map key names are not preserved in uppercase because of that.

If you want to pass JSON in a variable:

~~~yaml
services:
  app:
    image: example/config-demo:latest
    environment:
      APP_EXTERNAL_MAP_JSON: '{"ClientID":"partner-123","Mode":"Fast"}'
~~~

The keys inside the JSON belong to the variable's value content; they can be parsed with Jackson as guided above.

## 14. Observing and diagnosing when a Map lacks an expected key

A common bug:

~~~java
String clientId = properties.getValues().get("ClientID");
~~~

returns `null`, even though you declared:

~~~bash
export MY_PROPS_VALUES_CLIENTID="partner-123"
~~~

In this case, check:

1. Was the environment variable actually passed to the **Java process**?
2. Does prefix `my.props.values` match `@ConfigurationProperties(prefix="my.props")` and field `values`?
3. Is the program looking up uppercase key `ClientID` while the Binder produced key `clientid`?
4. Is another configuration source providing the same property, same key, or overriding the value?
5. Are there `_`, `-`, `.`, or `/` characters in the key name that environment variable representation cannot preserve?

To inspect the set of keys after binding without leaking sensitive values:

~~~java
@Bean
ApplicationRunner showBoundKeys(MyMapsProperties properties) {
    return args -> {
        System.out.println("Bound keys:");
        properties.getValues().keySet().stream()
                .sorted()
                .forEach(System.out::println);
    };
}
~~~

Place the bean in a `@Configuration` or `@SpringBootApplication` class, with the necessary `ApplicationRunner` and `Bean` imports.

When diagnosing, **printing key names** may suffice to spot casing issues. Avoid printing entire Map values if the Map holds tokens, passwords, or sensitive data.

### Querying with lowercase keys

If the application expects Map keys normalized from environment variables, you can intentionally query the lowercase name:

~~~java
String value = properties.getValues().get("clientid");
~~~

This solves lookup within the existing Map. However, if the key must be sent to an external system under the name `ClientID`, you still need to map back to the exact name required by the external system's contract; do not convert the entire payload to lowercase.

## 15. Common misconceptions

### "Environment variable names are uppercase, so Map keys are uppercase too"

False for Map binding from environment variables via Spring Boot Binder. In the `MY_PROPS_VALUES_KEY=VALUE` example, the key is `key`.

### "Spring Boot lowercases the value as well"

Incorrect. The value `VALUE` stays `VALUE`; a string `Prod-US-West` retains its letter casing when bound as a String, unless the application performs its own data transformation.

### "Using bracket notation in environment variable names preserves uppercase keys"

Do not rely on that assumption. Bracket notation is supported to preserve keys in configuration sources like YAML/properties; environment variable binding has its own limitations and variable names are lowercased before creating Map keys.

### "Reading `System.getenv` is the same as `@ConfigurationProperties`"

These two approaches differ. `System.getenv` returns the value of a single named variable; the Binder parses multiple properties and constructs a Map with normalized keys.

### "Changing the Map to `TreeMap` automatically keeps uppercase keys"

The Map implementation type does not recover casing information lost during binding. `TreeMap` has its own sorting/comparator behavior, but it cannot deduce the original key from a normalized env var.

### "Just force all keys to uppercase when reading"

Converting `clientid` to `CLIENTID` can help if your application contract only uses standard uppercase names. But it **cannot recover** original exact spellings like `ClientID` or `clientId`. If a system requires multiple case-sensitive names, preserve metadata or declare exact name mappings from another source.

## 16. Practice questions

### Exercise 1: Predict the Map contents

Given `MyMapsProperties`:

~~~bash
export MY_PROPS_VALUES_ENV="PROD"
export MY_PROPS_VALUES_REGION="AsiaPacific"
~~~

Determine the results of:

~~~java
values.get("env");
values.get("ENV");
values.get("region");
values.get("REGION");
~~~

**Answer:** `"PROD"`, `null`, `"AsiaPacific"`, `null`, assuming no other configuration source adds corresponding keys.

### Exercise 2: Preserving values, not key names

Given:

~~~bash
export MY_PROPS_VALUES_CLIENTID="AbC-987"
~~~

When bound via `@ConfigurationProperties`, identify the key and value.

**Answer:** key `clientid`, value `AbC-987`.

### Exercise 3: Using bracket notation

Write YAML so that `Map<String, String>` contains the exact two keys:

~~~text
ClientID
X-API-Key
~~~

**Suggested solution:**

~~~yaml
my:
  props:
    values:
      "[ClientID]": "partner-123"
      "[X-API-Key]": "demo-value"
~~~

### Exercise 4: Building an external payload

A REST API requires JSON field `ClientID`. Configuration from the environment variable is `APP_PARTNER_CLIENTID=partner-123`. Bind the value into `PartnerProperties.clientId` and build the payload using the literal key `"ClientID"`. Explain why this preserves the API field name.

### Exercise 5: Multiple keys differing only in letter case

A system requires both `ClientID` and `clientId` simultaneously. Should you create two environment variables differing only in casing to bind into one Map automatically?

**Answer:** No. Use YAML/properties with explicitly described keys, a structured JSON value parsed separately, or map fixed fields to external names.

## 17. Key takeaways

- In Spring Boot 3.3, when binding a **Map from environment variables** via `@ConfigurationProperties`, **Map key names are lowercased**.
- Environment variable **values** retain their uppercase/lowercase letters; `KEY=VALUE` creates key `key` with value `VALUE` in the corresponding example.
- Relaxed binding is suitable for mapping Spring Boot property names to environment variables, but does not guarantee preserving dynamic case-sensitive business key names.
- `System.getenv`, `Environment.getProperty`, and `@ConfigurationProperties` are three distinct API layers; reading a value from the raw variable does not imply the Map key after binding.
- When exact keys like `ClientID`, `X-API-Key`, or `/health` are needed, consider YAML/properties with bracket notation or storing key names inside a data format like JSON.
- If an external interface needs a fixed set of field names, bind **values** via configuration and use **exact key names** when constructing payloads.
- When diagnosing, inspect both **bound keys** and **effective values**, while accounting for the impact of other configuration sources.

## References

- [Spring Boot 3.3 — Externalized Configuration, Binding Maps From Environment Variables](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables)
- [Spring Boot 3.3 — Externalized Configuration, Binding Maps](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
