# Key and Value Syntax in application.properties

`application.properties` is a **key–value** plain-text format that Spring Boot commonly uses to configure applications outside of Java code. Understanding the file syntax accurately helps prevent subtle bugs: an accidental space that renames a key, a `#` character intended as a comment that actually becomes part of a value, or a backslash that gets processed as an escape character.

This lesson focuses on how to **write and read each line of `application.properties`**. The examples use Spring Boot, but it is important to distinguish two layers: **`.properties` syntax** determines how key/value pairs are parsed into strings; **Spring Boot** determines which keys have meaning and converts those strings into the appropriate Java types.

## 1. What does a simple properties file look like?

~~~properties
# src/main/resources/application.properties

spring.application.name=order-service
server.port=8080
server.shutdown=graceful

app.client.base-url=https://api.example.test
app.client.connect-timeout=750ms
app.client.max-retries=3
app.feature.audit-enabled=true
~~~

Every non-comment, non-blank line declares a key/value pair. For example, `server.port` is the key and `8080` is the text of the value. Spring Boot recognizes `server.port` as the HTTP port configuration property; when binding it to a numeric property, it converts the string `8080` to the appropriate number.

The keys starting with `app.` in the example are **custom properties**. Spring Boot does not automatically know which API to call using `app.client.base-url`: the application needs a bean that consumes this configuration, via `@ConfigurationProperties`, `@Value`, or `Environment`.

The standard location for this file in a Java project is `src/main/resources/application.properties`. When packaged, the file goes onto the classpath and is treated by Spring Boot as a Config Data source by default. An application can also receive configuration from external files outside the JAR, environment variables, command-line arguments, and other sources.

## 2. Core syntax: key, separator, and value

The most readable and recommended style is:

~~~properties
key=value
~~~

The Java properties format also allows `:` or whitespace as a separator:

~~~properties
app.mode=fast
app.mode:fast
app.mode fast
~~~

**The three lines above are three ways of writing the same key/value**, not examples that should be placed together in a single file. Choose `=` to stay consistent with other team members and reduce the chance of misreading.

A line is parsed according to these basic rules:

1. Skip leading whitespace at the beginning of the line to locate the start of the key.
2. Read the key up to the first **unescaped** `=`, `:`, or whitespace character.
3. Skip the separator and any associated whitespace immediately before the value begins.
4. The remainder of the logical line becomes the value after valid escape sequences are processed.

Example:

~~~properties
app.title = Order Service
app.description: Handles purchase orders
app.region asia-southeast
app.empty=
~~~

Logical result:

| Key | Value |
| --- | --- |
| `app.title` | `Order Service` |
| `app.description` | `Handles purchase orders` |
| `app.region` | `asia-southeast` |
| `app.empty` | Empty string |

`app.empty=` declares **a key with an empty value**. This is different from **the absence of a key** in a configuration source. When an application has fallbacks, validation, or special target types, the two situations can produce different results.

### What if `=` or `:` appears inside the value?

Normally, after the first separator, subsequent `=` and `:` characters belong to the value:

~~~properties
app.query=page=1&size=20
app.endpoint=https://example.test:8443/api
app.label=alpha:beta=gamma
~~~

The values are `page=1&size=20`, `https://example.test:8443/api`, and `alpha:beta=gamma`, respectively. There is no need to escape `:` in a URL just because it appears on the value side.

On the **key** side, if you want to use `:`, `=`, or whitespace as literal characters in the name, you must escape them; however, in Spring Boot configuration, you should generally avoid special key names and use clear hierarchical names instead.

## 3. Key naming conventions in Spring Boot

Spring Boot typically uses dot-separated hierarchical keys with hyphens between multiple words within a segment:

~~~properties
server.port=8080
spring.application.name=order-service

app.mail.sender-address=noreply@example.test
app.mail.retry-policy.max-attempts=3
app.mail.retry-policy.backoff=2s
~~~

You can read `app.mail.retry-policy.max-attempts` structurally: group `app` → component `mail` → group `retry-policy` → property `max-attempts`. With `@ConfigurationProperties(prefix = "app.mail")`, the Spring Boot Binder can map the corresponding parts to Java properties such as `senderAddress` and `maxAttempts`.

**Recommended convention:** use lowercase `kebab-case` keys for each name segment, separating levels with `.`. For example, `app.client.connect-timeout` is the canonical name to prefer when defining and referencing configuration.

~~~properties
# Recommended names
app.client.connect-timeout=750ms
app.feature.audit-enabled=true
~~~

Spring Boot supports *relaxed binding*, meaning several name variants can map to the corresponding Java property. Even so, relaxed binding is not a reason to arbitrarily mix `connectTimeout`, `connect_timeout`, and `connect-timeout` in the same file. Canonical names keep searching, overriding, and lookup consistent.

There is no "automatic registration" for every key starting with `app.`. If a key name is not consumed by any bean, that configuration line may simply sit as data in `Environment`. Certain well-known keys such as `server.port` or `spring.application.name` are recognized by Spring Boot and its corresponding auto-configurations.

## 4. Values are text before Spring Boot type conversion

In a `.properties` file, the right-hand side is first read according to string syntax. Spring Boot can convert it into numbers, booleans, durations, data sizes, URIs, enums, or other types depending on the consumer.

~~~properties
app.worker.threads=8
app.feature.enabled=true
app.client.connect-timeout=1500ms
app.client.read-timeout=5s
app.cache.maximum-size=64MB
app.client.base-url=https://api.example.test/v1
app.banner=Welcome to Order Service
~~~

| Value in file | Bindable Java type | Interpretation |
| --- | --- | --- |
| `8` | `int` / `Integer` | Integer |
| `true` | `boolean` / `Boolean` | Boolean value |
| `1500ms` | `Duration` | 1.5 seconds |
| `5s` | `Duration` | 5 seconds |
| `64MB` | `DataSize` | Data size using Spring units |
| `https://api.example.test/v1` | `URI` | Structured address |
| `Welcome to Order Service` | `String` | Plain text |

`.properties` syntax does not declare the type of a line by itself; **the target type is determined by how the application reads and binds it**. For example, `server.port=eight-thousand` is still syntactically valid as a key/value line, but Spring Boot cannot use that text as a valid port number and may report a configuration error on startup.

Not every custom key is automatically validated by Spring Boot. If a custom value must be present or fall within a specific range, define constraints on the configuration class that receives it.

## 5. Comments and blank lines

A comment line begins with `#` or `!` at the **first non-whitespace character** of a natural line:

~~~properties
# HTTP configuration
! This line is also a comment

server.port=8080

    # Comment with leading whitespace
app.feature.audit-enabled=true
~~~

Blank lines help group related properties without creating key/value entries.

### No YAML-style end-of-line comments

This is a very common pitfall:

~~~properties
app.greeting=Hello # this is a comment
app.version=1.0 ! latest release
~~~

According to Java properties syntax, `# this is a comment` and `! latest release` at the **end of a value** are part of the value itself, not ignored as comments. If you want to add a note, move the comment onto its own line:

~~~properties
# Greeting displayed on the home page
app.greeting=Hello

# Version displayed on the About screen
app.version=1.0
~~~

For data containing `#`, such as a URL fragment, it can appear directly inside the value:

~~~properties
app.docs-url=https://docs.example.test/guide#configuration
~~~

Do not assume that the comment rules of YAML or JSONC also apply in `.properties`.

## 6. Quotes do not act as string delimiters

In YAML, strings are often wrapped in quotes. In `application.properties`, adding quotes usually makes the quote characters themselves part of the value as parsed by Java properties:

~~~properties
app.message=Hello world
app.message-quoted="Hello world"
app.choice='blue'
~~~

The values according to file syntax are:

- `Hello world`
- `"Hello world"`, including the double quotes
- `'blue'`, including the single quotes

Therefore, **do not add quotes just to include spaces**:

~~~properties
# Sufficient to represent a string with spaces
app.display-name=Order Management Service
~~~

Whether a higher-level consumer performs its own quote handling depends on that consumer, but do not treat quotes as a core rule of the properties format. If you need to pass a string containing literal quotes, verify the exact value received by the bean.

## 7. Whitespace before, around, and after the separator

Several lines may look different yet represent the same pair:

~~~properties
app.locale=vi_VN
app.locale = vi_VN
app.locale: vi_VN
~~~

Leading whitespace on a line and whitespace used around the key/value separator are handled by the parser according to the format rules. Whitespace **inside the value** remains significant:

~~~properties
app.display-name=Order Service
app.pattern=first  second
~~~

`app.pattern` contains two spaces between `first` and `second`. **Trailing** whitespace at the end of a value can also be preserved, causing subtle bugs if the string is used in comparisons, signing, or building paths.

If a value needs to **start with a literal space**, you can escape the first space:

~~~properties
app.indented-label=\ Leading space
~~~

The value of `app.indented-label` starts with a single space. In practice, avoid making important data depend on invisible whitespace; if you must use it, document the intent clearly and write a test checking the bound value.

A key name with an unescaped space can also be cut off early:

~~~properties
# Should not be used to represent the key "feature flag"
feature flag=true

# Example of escaping a space in a Java properties key
feature\ flag=true
~~~

The first line can be interpreted as key `feature` and value `flag=true` under the key/value splitting rules, rather than key `feature flag`. The second line represents a key containing a space, but this is not an appropriate naming style for most Spring Boot configuration. Use `app.feature.enabled=true` or `app.feature-flag=true` for clear meaning.

## 8. Escaping with backslashes

The backslash `\` has special meaning in Java properties. Common escape sequences include:

| Notation in file | Character after parsing |
| --- | --- |
| `\\` | A single backslash `\` |
| `\n` | Newline (line feed) |
| `\r` | Carriage return |
| `\t` | Tab |
| `\f` | Form feed |
| `\u0041` | Unicode character `A` |
| `\ ` | Escaped space |
| `\=`, `\:` | Literal `=`, `:`, useful when inside a key |

Example:

~~~properties
app.message=First line\nSecond line
app.column-label=Name\tStatus
app.literal-backslash=\\
app.windows-export-dir=C:\\data\\exports
app.key\=with-equals=some-value
~~~

According to properties syntax:

- `app.message` contains a newline character between the two text parts, not the two characters `\` and `n`.
- `app.column-label` contains a tab.
- `app.literal-backslash` is a single `\` character.
- `app.windows-export-dir` contains the Windows path `C:\data\exports` with literal backslashes.
- The last line has the key `app.key=with-equals`, escaped so that `=` is part of the key name.

**Windows path pitfall:**

~~~properties
# Unsafe when expecting backslashes to be preserved
app.export-dir=C:\temp\reports

# Escaped backslashes
app.export-dir=C:\\temp\\reports
~~~

In the first example, `\t` can become a tab and `\r` a carriage return. Backslashes before characters not recognized as escapes may also not remain intact. Do not copy Windows paths into properties without checking the backslashes.

For Unicode content, `\uXXXX` syntax represents a Unicode code unit according to properties rules. When representing characters outside the Basic Multilingual Plane with traditional escapes, two escapes corresponding to a UTF-16 surrogate pair may be needed. In real projects, standardize file encoding across your files and build pipeline; avoid relying on how a particular editor or custom loader handles encoding.

## 9. Writing multiline values with `\`

A backslash at the **end of a natural line** can join the next line into the same logical value:

~~~properties
app.long-message=Welcome to \
  the order service \
  configuration guide
~~~

The lines above create a single key `app.long-message`. Leading whitespace on continuation lines is typically stripped according to continuation rules; physical line breaks do not automatically become spaces in the value. The logical result of the example is `Welcome to the order service configuration guide` because each segment before `\` already includes the required space.

Look at an example without a space before the backslash:

~~~properties
app.code=ABC\
  DEF
~~~

The value is `ABCDEF`, not `ABC DEF`. To include a space, write the space intentionally or use a simpler representation.

If you need an **actual newline character** in the value, use the `\n` escape rather than assuming line continuation preserves newlines:

~~~properties
app.notice=Line one\nLine two
~~~

Multiline continuation saves horizontal width, but for long or richly structured text, consider whether YAML or a separate text resource would be easier to read and maintain.

## 10. Duplicate keys and what overriding means

Consider a single file:

~~~properties
app.client.max-retries=2
app.client.max-retries=5
~~~

When two declarations of the same key are loaded sequentially into the same property set in the usual way, **the later declaration replaces the value of the earlier one**. Therefore, do not rely on duplicate declarations to represent environments or change history. Keep only one clear declaration per key within a configuration document.

Unlike duplicate keys *within the same document*, Spring Boot also supports **multiple property sources**. For example, `app.client.max-retries=2` in `application.properties` can be overridden by an environment variable or startup argument with higher precedence. In that case, the result depends on precedence rules between sources, not just line order within a file.

~~~bash
java -jar order-service.jar --app.client.max-retries=7
~~~

If no higher-precedence source is active, this command-line example can make the effective value of `app.client.max-retries` equal `7` even though the file sets `2`. Distinguish **single-document parsing syntax** from **how Spring Boot merges multiple sources**.

## 11. Lists, elements, and maps in properties

`.properties` syntax itself does not have arrays like YAML does. However, the Spring Boot Binder understands indexed keys when binding configuration to collections:

~~~properties
app.contacts[0].name=Operations
app.contacts[0].email=ops@example.test
app.contacts[1].name=Support
app.contacts[1].email=support@example.test
~~~

A Java object containing `List<Contact>` can receive data based on the `[0]`, `[1]` indices if the bean and element type are properly declared.

For simple values, comma-separated configuration can also bind to a collection depending on the target type:

~~~properties
app.allowed-regions=ap-southeast-1,ap-northeast-1,eu-west-1
~~~

This is not a native Java properties array syntax. The raw data is a comma-containing string; conversion into a list belongs to the Spring Boot Binder or the corresponding consumer. If an element value itself contains commas or has a complex structure, indexed syntax is clearer.

Maps can also be represented using sub-keys:

~~~properties
app.labels.team=payments
app.labels.owner=backend
~~~

For map keys containing special characters such as slashes, the Spring Boot Binder supports bracket notation to preserve the key in the appropriate context:

~~~properties
app.labels.[/public-api]=enabled
~~~

Do not assume dots, slashes, or brackets will always be preserved across all map types; choose appropriate keys and verify how binding behaves for the specific target type.

## 12. Placeholders: referencing other values with `${...}`

Spring Boot allows configuration values to contain placeholders resolved through `Environment`. Example:

~~~properties
app.http.scheme=https
app.http.host=api.example.test
app.http.port=8443
app.http.base-url=${app.http.scheme}://${app.http.host}:${app.http.port}
~~~

When resolved by Spring, `app.http.base-url` evaluates to `https://api.example.test:8443`.

You can declare a fallback value when a reference does not exist:

~~~properties
app.client.timeout=${APP_TIMEOUT:3s}
app.client.base-url=${APP_BASE_URL:https://api.example.test}
~~~

Here `${APP_TIMEOUT:3s}` means reference `APP_TIMEOUT`; if no corresponding value exists, use `3s` as the default in the placeholder resolution context. A colon **inside a placeholder expression** serves a different role from the file's key/value separator.

Distinguish the layers:

- The `.properties` file determines the raw value as text containing `${...}`.
- Spring Boot and the placeholder resolution infrastructure handle references and fallbacks when a consumer retrieves the value.
- Not every plain `java.util.Properties` reader resolves `${...}` syntax on its own.

Reference internal keys using their canonical names, such as `${app.client.timeout}`, to avoid relying on inconsistent naming conventions. If a placeholder has neither a source nor a fallback, the consumer may fail when resolving the value, depending on how it is used.

## 13. When the application reads values: Environment, @Value, and @ConfigurationProperties

Example file:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=750ms
app.client.max-retries=3
~~~

A bean can read values using `Environment`:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientConfigReader {
    private final Environment environment;

    public ClientConfigReader(Environment environment) {
        this.environment = environment;
    }

    public Duration connectTimeout() {
        return environment.getProperty(
            "app.client.connect-timeout", Duration.class);
    }
}
~~~

For a single property, `@Value` can also be suitable:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class SingleTimeoutHolder {
    public SingleTimeoutHolder(
        @Value("${app.client.connect-timeout:1s}") Duration timeout
    ) {
        System.out.println(timeout);
    }
}
~~~

But with multiple related keys, a strongly typed configuration object is clearer:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Enable scanning for properties beans in the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

The Spring Boot Binder can then map `base-url` → `baseUrl`, `connect-timeout` → `connectTimeout`, and `max-retries` → `maxRetries`. The value `750ms` is converted to `Duration`, and `3` to an integer.

Note that if you only declare a record with `@ConfigurationProperties` without registering the bean via `@ConfigurationPropertiesScan` or the corresponding `@EnableConfigurationProperties`, the application does not automatically have a `ClientProperties` bean to inject.

## 14. Running the same configuration with profiles

A base file can declare:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=3
~~~

A file for development:

~~~properties
# application-dev.properties
app.client.base-url=http://localhost:8081
app.client.connect-timeout=500ms
~~~

When the `dev` profile is activated through a valid source, for example:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Spring Boot can load profile-specific configuration. In this situation, `base-url` and `connect-timeout` take their values from `application-dev.properties`, while `max-retries` continues to receive `3` from the base file if no higher-precedence source overrides it.

Do not assume that `application-dev.properties` takes effect simply because it exists. Additionally, the same key can be overridden by environment variables, system properties, or command-line arguments according to property source precedence.

### Multiple documents in a single Spring Boot properties file

Spring Boot Config Data supports separating documents within a single `application.properties` file using `#---`:

~~~properties
app.client.connect-timeout=3s
app.logging.detail=normal

#---
spring.config.activate.on-profile=dev
app.client.connect-timeout=500ms
app.logging.detail=verbose
~~~

When the second section is activated by the `dev` profile, the matching values from that document are applied. Here `#---` is a **special document separator supported by Spring Boot**, not merely a human comment. Because this is a Spring Boot Config Data feature, do not infer that every plain Java properties parser behaves the same way.

Do not place `spring.profiles.active` inside a document already constrained by `spring.config.activate.on-profile`. Profile activation rules should be placed in a source capable of determining the active profiles validly.

## 15. How do properties files differ from YAML?

The following two declarations can represent the exact same keys:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=3
~~~

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 3
~~~

| Aspect | Properties | YAML |
| --- | --- | --- |
| Hierarchical structure | Flat key names with `.` | Indentation and nested mappings |
| Separator | `=`, `:`, or whitespace per properties syntax | `:` with YAML indentation |
| Comments | `#` or `!` at start of logical line | `#` per YAML rules |
| Quotes | Not standard string delimiters in properties | Has single/double-quoted string syntax |
| Lists | Indexed keys or strings parsed by binder | Native sequences with `- item` |
| Escaping | `\` per properties syntax | Depends on YAML string style |

Even though they describe the same keys, you should not maintain both `application.properties` and `application.yml` with competing values in the same configuration location. Spring Boot has precedence rules when both exist in the same location; by default, `.properties` takes precedence over YAML. Choosing one primary format helps avoid confusion.

## 16. Common mistakes and how to recognize them

### Mistake 1 — Treating the end of a line as a comment

~~~properties
# Wrong if you only want to store the value "3"
app.retry-count=3 # retries
~~~

The value can become `3 # retries`, causing binding to `int` to fail. Better:

~~~properties
# Number of retries
app.retry-count=3
~~~

### Mistake 2 — Using double quotes out of YAML habit

~~~properties
app.mode="production"
~~~

If the consumer expects `production` without quotes, the value at the properties layer may not match. Write:

~~~properties
app.mode=production
~~~

### Mistake 3 — Writing Windows paths with single backslashes

~~~properties
app.download-path=C:\new\temp
~~~

`\n` and `\t` are escapes, so the string can get corrupted. Write explicitly:

~~~properties
app.download-path=C:\\new\\temp
~~~

### Mistake 4 — Confusing key names with Java field style

~~~properties
app.client.connectTimeout=500ms
~~~

Relaxed binding can handle name variants in the appropriate context, but the canonical key, especially when using placeholders, should be:

~~~properties
app.client.connect-timeout=500ms
~~~

If the prefix name is completely different, such as `client.connect-timeout` instead of `app.client.connect-timeout`, the Binder will not guess your intent and search under another prefix.

### Mistake 5 — Believing an empty value means undeclared

~~~properties
app.smtp.username=
~~~

The key exists with an empty value. An application that requires a non-empty username needs an explicit check, such as via Bean Validation on the properties bean.

### Mistake 6 — Using duplicate keys to keep history

~~~properties
app.feature.enabled=false
app.feature.enabled=true
~~~

Remove the old line or use an intentional override mechanism. Duplicate declarations within a single document make files harder to read and maintain.

### Mistake 7 — Assuming a custom property line activates a feature on its own

~~~properties
app.feature.new-checkout=true
~~~

This line only supplies configuration data. Whether the feature actually runs depends on code that reads `app.feature.new-checkout` or related configuration conditions.

## 17. Practical steps to verify a key is read correctly

Suppose you want to set the HTTP client timeout to `750ms`.

**Step 1 — Write the canonical key in the file:**

~~~properties
app.client.connect-timeout=750ms
~~~

**Step 2 — Look up the value through `Environment`:**

~~~java
Duration timeout = environment.getProperty(
    "app.client.connect-timeout", Duration.class);
~~~

If an appropriate converter is available, the result is a `Duration` of 750 milliseconds.

**Step 3 — Compare inputs across different runs:**

~~~bash
java -jar order-service.jar --app.client.connect-timeout=2s
~~~

Now the result can become 2 seconds because the command-line argument overrides the file. That is a change in the **effective configuration source**, not a `.properties` parser bug.

**Step 4 — When the result differs from expectations, check in order:**

1. Is the line actually commented out, missing `=`, or containing an unintended escape?
2. Is the key spelled accurately, especially the prefix and hyphens?
3. Does the value contain unwanted characters such as `# note`, quotes, tabs, or trailing spaces?
4. Are there duplicate keys in the same file?
5. Is a higher-precedence source overriding the same key?
6. What type does the consumer expect, and is the type conversion valid?

If the application uses Spring Boot Actuator, configuration diagnostic endpoints such as `env` or `configprops` can help inspect sources and binding when enabled and properly secured. Do not print tokens, passwords, or sensitive data to logs just to prove the parser works.

## 18. Syntax reading exercises

### Exercise 1

Given the file:

~~~properties
app.count=4
app.title=Hello World
app.endpoint=https://example.test:9443/a?x=1
~~~

Identify the three key/value pairs. Answer: `app.count` → `4`, `app.title` → `Hello World`, `app.endpoint` → `https://example.test:9443/a?x=1`. The `:` and `=` characters appearing in the URL on the value side do not create extra keys.

### Exercise 2

~~~properties
app.stage=prod # current
~~~

Is the value equal to `prod`? **No.** In properties syntax, the trailing `# current` does not automatically become a comment. If a number, enum, or exact string is needed, the extra text can cause an error. Move the note to a separate `# ...` line.

### Exercise 3

~~~properties
app.path=C:\\logs\\archive
app.text=One\nTwo
~~~

The value of `app.path` has single backslashes like `C:\logs\archive`. The value of `app.text` contains a newline character between `One` and `Two`.

### Exercise 4

~~~properties
app.word=Hello,\
  World
~~~

The logical value is `Hello,World`: no space is automatically inserted at the join point. To get `Hello, World`, place a space intentionally in the source text.

### Exercise 5

~~~properties
app.client.timeout=5s
app.client.timeout=8s
~~~

If the two lines are read sequentially within the same properties document, the later declaration replaces the earlier one, so `app.client.timeout` carries the value `8s` from that document. However, the application-wide effective value still depends on any higher-precedence property sources.

## 19. Syntax cheat sheet

| What you want to write | Pattern in `application.properties` | Note |
| --- | --- | --- |
| Simple key/value | `server.port=8080` | Prefer `=` |
| Multi-level name | `app.mail.retry-count=3` | `.` for hierarchy, `kebab-case` per segment |
| String with spaces | `app.name=Order Service` | No quotes needed |
| Comment | `# Connection configuration` | Put on its own line |
| Empty value | `app.optional-value=` | Distinct from missing key |
| Newline character | `app.text=One\nTwo` | `\n` is an escape |
| Windows path | `app.path=C:\\data\\logs` | Double the backslashes |
| Placeholder link | `app.timeout=${app.default-timeout:5s}` | Spring resolves placeholders |
| List item | `app.items[0]=first` | Structure for Binder |
| Profile-specific document | `#---` then `spring.config.activate.on-profile=dev` | Spring Boot Config Data feature |

Look at an `application.properties` line in two consecutive steps: **which key and raw string value the parser reads**, and then **which Spring Boot/bean mechanism consumes that key and converts it to which type**. Separating these two steps helps pinpoint the true cause when a configuration line looks valid yet the application still behaves differently than expected.
