# Handling Duplicate Keys, Misindentation, and Empty vs. Null in Spring Boot

## Goal

**application.properties** and **application.yml** files are two common ways to supply configuration outside Java code in Spring Boot. The exact same application can run normally in one environment yet fail to start or receive wrong values in another simply because a key appears twice, a YAML line sits at the wrong level, or a value is written empty instead of explicitly **null**.

This lesson focuses on three groups of issues:

1. **Duplicate keys:** a property name is declared repeatedly in the same file, or the same property appears across multiple sources with different precedence.
2. **Misindentation:** YAML structure is altered or unparseable because lines are not at the right level.
3. **Empty and null:** notations that look similar yet can produce an empty string, a null value, whitespace, the literal string "null", or a missing property.

After this lesson, you will be able to explain why Spring Boot chooses a given value, write less ambiguous configuration, and verify results using **Environment**, **@ConfigurationProperties**, and startup error messages.

## 1. Distinguish three layers of the problem

When you hear "duplicate configuration", identify where the duplication happens before editing:

| Situation | Example | Underlying nature |
| --- | --- | --- |
| Same key repeated in one .properties file | Two app.mode=... lines | One source redeclares the same key |
| Same mapping key repeated in one YAML document | Two sibling app: entries | Duplicate key in YAML structure; parser may reject it |
| Same property name across multiple sources | application.yml and environment variable | Spring picks the higher-precedence source |
| Two different YAML paths due to indentation | app.cache.ttl and app.ttl | Two distinct keys, even though the leaf name is ttl |
| A value that looks empty | app.name=, app.name: null | Must check syntax, data type, and loading mechanism |

Three layers have different responsibilities:

- **The format parser** reads `.properties` or YAML text and produces structured data.
- **Spring Boot's configuration loader** converts data into PropertySources, flattening YAML trees into property names like app.cache.ttl.
- **Spring Environment and Binder** select values by precedence and convert them to the types requested by beans or Java code.

A syntactically valid YAML file does not guarantee the right structure for the application. Likewise, a file containing a valid key does not guarantee its value is chosen when Spring has a higher-precedence source.

## 2. Duplicate keys in application.properties

Consider the following file:

~~~properties
app.mode=standard
app.worker-count=2
app.mode=fast
~~~

Java properties syntax allows lines with the same key name to be read sequentially; with standard loading, the later declaration can replace the earlier value, so app.mode typically resolves to **fast**. Even so, **never use duplicate declarations to design precedence**: maintainers easily miss the second line, linters may warn, and custom loaders can behave differently.

A clearer version:

~~~properties
app.mode=fast
app.worker-count=2
~~~

If different settings are needed per environment, separate values using profiles or distinct configuration sources rather than declaring the same key twice in one file:

~~~properties
# application.properties
app.mode=standard
~~~

~~~properties
# application-dev.properties
app.mode=fast
~~~

When the **dev** profile is active and configuration is loaded by default rules, the value in the profile file can override the base value. This is **precedence between configuration sources/documents**, unlike repeating a line within the same file.

Another source of confusion is key names with whitespace or separators:

~~~properties
app.mode = fast
app.timeout: 10s
~~~

In `.properties` format, both **=** and **:** can separate key and value; whitespace around the separator is processed according to format rules. Therefore **app.timeout=10s** and **app.timeout: 10s** represent the same key name, not two different namespaces.

Use one consistent convention, such as **app.timeout=10s**, so editors and code reviews can spot duplicates easily.

## 3. Duplicate keys in YAML: same level vs. overriding

YAML expresses data with mappings and nested levels. A repeated key at the **same mapping inside a single YAML document** is very different from having multiple Spring PropertySources:

~~~yaml
# Avoid: key app appears twice in the same document
app:
  mode: standard

app:
  worker-count: 2
~~~

Depending on the parser and library version settings, duplicate keys can fail immediately when reading YAML; never assume the second app block will automatically merge with the first. Spring Boot uses its own YAML loader, and you should inspect errors on your actual version when encountering duplicate-key files. Never apply `.properties`' "last line wins" intuition to YAML.

Combine parts of the same mapping into a single structure:

~~~yaml
app:
  mode: standard
  worker-count: 2
~~~

Duplicate keys can also appear deeper down, even when there is only one root entry:

~~~yaml
app:
  cache:
    ttl: 10s
    enabled: true
    ttl: 30s
~~~

Here **ttl** appears twice inside the **cache** mapping. Fix it by deciding on one value:

~~~yaml
app:
  cache:
    ttl: 30s
    enabled: true
~~~

### 3.1. Do not confuse with multi-document YAML

In YAML, **---** marks the start of a new document. Spring Boot supports multi-document configuration files and profile-based activation conditions:

~~~yaml
app:
  mode: standard
---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: fast
~~~

The two **app.mode** entries here sit in **two different YAML documents**, not as duplicate keys in the same mapping. When the **dev** profile is active, the second document can override the base configuration per Spring Boot Config Data rules. When dev is inactive, the conditional document is not applied.

Activation conditions and document order are part of configuration precedence; do not collapse a valid multi-document setup into one mapping if doing so breaks profile behavior.

### 3.2. Differently cased names can still target the same property

Observe these two names:

~~~yaml
app:
  report-timeout: 10s
  reportTimeout: 20s
~~~

At the YAML structure level, these are two distinct key strings. However, Spring Boot uses **relaxed binding** when binding to @ConfigurationProperties; both kebab-case and camelCase variants can map to the same Java property. Do not use multiple spellings for the same concept and expect clear winner/loser behavior.

Readable convention: name configuration keys in files using canonical **lowercase, kebab-case**, such as **app.report-timeout**, and declare each in only one place within a source.

## 4. YAML indentation determines property names

YAML uses leading spaces to represent parent–child relationships. Given:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 30s
  name: demo
~~~

Spring Boot can flatten this into property names:

~~~properties
app.cache.enabled=true
app.cache.ttl=30s
app.name=demo
~~~

Tree view:

~~~text
app
├── cache
│   ├── enabled
│   └── ttl
└── name
~~~

Now shift one line's indentation:

~~~yaml
app:
  cache:
    enabled: true
  ttl: 30s
  name: demo
~~~

This file can still be **valid YAML**, yet ttl's name has changed to **app.ttl**. A bean expecting **app.cache.ttl** will not find the value under the expected key. This is one of the hardest bugs to spot because the application may not report any parser error.

Distinguish two kinds of misindentation:

- **Wrong level but valid:** YAML parses cleanly, the property structure shifts, and binding misses the expected data.
- **Invalid indentation:** parser rejects the file, and the application may stop during configuration loading.

Example of invalid structural syntax:

~~~yaml
app:
  database:
    host: localhost
   port: 5432
~~~

The **port** line has leading spaces that do not align with the open mapping. The parser usually reports an error pointing to line/column numbers rather than producing a clear property tree.

Fix:

~~~yaml
app:
  database:
    host: localhost
    port: 5432
~~~

### 4.1. There is no strict rule requiring "always two spaces"

YAML does not require every level to use exactly two spaces. What matters is that sibling elements share consistent indentation and parent–child relationships are unambiguous. In real projects, **two spaces per level** is a helpful convention because it is easy to scan visually.

~~~yaml
# Two spaces/level: clear
app:
  database:
    host: localhost
    port: 5432
~~~

Never mix **tabs** with spaces for YAML structural indentation; tabs are not valid indentation characters in YAML syntax. Turn on visible whitespace in your IDE if errors only happen after copying configuration from docs or chat messages.

### 4.2. Sequence hyphens also depend on indentation

Correct example:

~~~yaml
app:
  servers:
    - host: alpha.local
      port: 8080
    - host: beta.local
      port: 8081
~~~

**servers** is a list of two elements, each a mapping with host and port. When bound, elements typically map to **app.servers[0].host**, **app.servers[0].port**, and similarly for the second element.

Common mistake:

~~~yaml
app:
  servers:
    - host: alpha.local
    port: 8080
~~~

**port** is not at the right level for a property inside the list element. Depending on the exact column, the parser may error or build the wrong structure. For lists of objects, properties of the same element must align with the content column after the **-**.

## 5. Empty, null, whitespace, and literal "null" have four different meanings

Below are easily confused representations in YAML:

~~~yaml
demo:
  missing-value:
  explicit-null: null
  tilde-null: ~
  empty-string: ""
  empty-single-quoted: ''
  blank-string: " "
  literal-null: "null"
  empty-list: []
  empty-map: {}
~~~

Regarding **YAML semantics before Spring Boot loads and binds**:

| Notation | Meaning in YAML data |
| --- | --- |
| missing-value: | Scalar value omitted, typically parsed as null |
| explicit-null: null | Null value |
| tilde-null: ~ | Null value |
| empty-string: "" | Empty string, length 0 |
| empty-single-quoted: '' | Empty string, length 0 |
| blank-string: " " | String containing one space |
| literal-null: "null" | String of four characters n-u-l-l |
| empty-list: [] | Empty list |
| empty-map: {} | Empty mapping |

The key name **missing-value** in the example is illustrative; in YAML syntax, it is still a **key with an empty scalar**, which differs from the key being completely absent from the file.

Do not use **null** as shorthand for an empty string. Do not use **"null"** to represent a null value: quotes make it literal text.

Another distinction: in YAML files, unquoted values like **true**, **42**, or **null** are recognized by the parser according to YAML scalar rules. Use quotes when you need to guarantee a value stays a string, especially for business-meaningful data.

### 5.1. Comparison with application.properties

~~~properties
demo.empty=
demo.empty-also
demo.literal-null=null
demo.literal-tilde=~
demo.with-space= 
~~~

In `.properties` format:

- **demo.empty=** is an empty string.
- **demo.empty-also** is a key without a value portion; standard Java properties readers treat its value as an empty string.
- **demo.literal-null=null** is the literal text **null**, with no special YAML null type.
- **demo.literal-tilde=~** is the string **~**.
- **demo.with-space= ** must be evaluated according to how the `.properties` parser handles whitespace after the separator; never use an invisible space to convey business state.

In particular, quotes in `.properties` **do not serve the same role as quotes in YAML**. For example:

~~~properties
demo.name=""
~~~

In standard `.properties` syntax, double quotes are characters of the value; do not assume they produce an empty string like **demo.name: ""** in YAML. To write an empty string in `.properties`, write **demo.name=**.

### 5.2. Null in YAML is not a "delete" command for another source

Suppose the same property is declared in two sources:

~~~yaml
# Base configuration
app:
  greeting: hello
~~~

~~~yaml
# Additional configuration with higher precedence
app:
  greeting: null
~~~

One might expect **null** to erase **hello**. That assumption is unsafe. Spring Environment uses PropertySources, and how a null scalar is transferred into a PropertySource as well as how PropertyResolver handles null must be verified for the actual loader/version. Typically, null does not act as a "tombstone" guaranteed to shadow every value from lower-precedence sources.

Design principle: **do not treat null as a mechanism to delete or disable settings across precedence layers**. When business logic needs to disable a feature, declare an explicit property with clear meaning, such as:

~~~yaml
app:
  notifications:
    enabled: false
~~~

When you need to remove an element or replace a list/map across configuration sources, check the binding rules for that data type; you cannot generalize String scalar behavior to collections.

## 6. Absent keys, empty keys, and default values

Suppose an application configures **app.display-name**. Three forms express different intents:

~~~yaml
# Case A: key app.display-name is absent
app:
  enabled: true
~~~

~~~yaml
# Case B: key is present with an empty string
app:
  display-name: ""
  enabled: true
~~~

~~~yaml
# Case C: key is present with a specific string
app:
  display-name: "Demo"
  enabled: true
~~~

For direct lookup via **Environment.getProperty("app.display-name")**, Case A normally indicates the property was not found, while B intentionally supplies an empty string if the source preserves that value. Case C supplies **Demo**.

Separate four questions when troubleshooting:

1. Is the key present in the text?
2. What type did the format parser infer for the value?
3. What value did the loader publish into the Spring PropertySource?
4. How does the bean or Java code convert and use that value?

The four outcomes can differ. For instance, a bean expecting **Duration**, **Integer**, or an enum may fail conversion on values that a **String** bean still accepts.

### 6.1. Placeholders with defaults and empty strings

Spring supports placeholders with default values, for example:

~~~yaml
app:
  display-name: "${APP_DISPLAY_NAME:Demo}"
  callback-url: "${APP_CALLBACK_URL:}"
~~~

In this configuration:

- If **APP_DISPLAY_NAME** cannot be resolved from any source, the placeholder uses the default **Demo**.
- If **APP_CALLBACK_URL** cannot be resolved, the placeholder uses the empty string after **:**.
- If the property resolves to an **intentional empty string**, do not assume the placeholder's default will be chosen. Defaults apply when resolution fails to find a value, not as a rule replacing every empty string.

For deployment environments, define business requirements explicitly: should a missing value fall back to a default, is empty allowed, or should the application refuse to start?

### 6.2. Using validation to avoid running with ambiguous configuration

Example of a display name that must have content:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String displayName
) {
}
~~~

When the application has Jakarta Bean Validation support and registers this class via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**, @NotBlank catches null, empty, or whitespace-only values for required properties.

If business logic **allows** empty strings, do not put @NotBlank on that property. If business logic must distinguish "undeclared" from "explicitly empty string", build explicit rules in the configuration class and test against real sources rather than relying on visual impressions of YAML.

## 7. Values bind by structure, not just by text lines

Consider a Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(boolean enabled, Duration ttl) {
}
~~~

Corresponding configuration:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 20s
~~~

If replaced with:

~~~yaml
app:
  cache:
  enabled: true
  ttl: 20s
~~~

The two lines **enabled** and **ttl** now belong to **app.enabled** and **app.ttl**. For CacheProperties, **app.cache.enabled** and **app.cache.ttl** are no longer declared as before; binding outcomes depend on defaults, other sources, and required field constraints.

With primitive **boolean**, Java's default value can make missing configuration harder to detect than a required object field. Use appropriate validation/startup checks for mandatory flags or values.

### 7.1. Wrong structure can cause type conversion errors

Another case:

~~~yaml
app:
  cache: fast
~~~

If the application expects **app.cache.ttl**, the scalar **fast** at app.cache cannot turn itself into an object with a ttl property. Depending on the configuration class and binding setup, this can cause a bind failure, an unset property, or fallback to defaults. Reading the error message with the full property name reveals whether it is a type error or a nesting error.

### 7.2. Same key across multiple valid sources is a precedence question

Example:

~~~yaml
# application.yml
app:
  cache:
    ttl: 20s
~~~

And setting an environment variable:

~~~bash
APP_CACHE_TTL=40s java -jar demo.jar
~~~

Spring Boot can select **40s** because environment variables typically have higher precedence than file-based Config Data. This is **not a YAML duplicate-key error**; the same property name exists in two different PropertySources.

If you also pass:

~~~bash
APP_CACHE_TTL=40s java -Dapp.cache.ttl=50s -jar demo.jar --app.cache.ttl=60s
~~~

Under the default precedence of the sources shown, Spring Boot argument **--app.cache.ttl=60s** wins over system property **50s**, environment variable **40s**, and YAML file **20s**.

Separate **"a key appearing multiple times in one YAML mapping"** from **"a property having multiple candidates across valid sources"**. The fixes differ: the first edits the document; the second verifies precedence order and deployment intent.

## 8. Reading errors when Spring Boot loads configuration

When the application fails to start or receives unexpected values, read errors by stage:

| Symptom | Issue category to check | Resolution direction |
| --- | --- | --- |
| YAML parse error pointing to line/column | Invalid syntax or indentation; possibly duplicate key | Open exact file/line; inspect nearby mappings |
| Application runs but bean receives null/default | Wrong level, misspelled property name, or shadowed by another source | Compare full key name against @ConfigurationProperties |
| Bind/conversion error | Empty value, string "null", or type mismatch | Check Java type and actual property value |
| @NotBlank validation error | Required property missing, empty, or whitespace-only | Supply valid value or adjust configuration contract |
| Fails only under one profile | Profile-specific YAML document or file has a different value | Check active profiles and Config Data ordering |
| Deployment run overrides file value | Environment variable, -D, or -- with same key | List active sources by precedence |

Do not guess the entire problem from a generic "failed to bind" message. Read the property name, configuration origin if reported, target type, and nested cause inside the exception.

### 8.1. Checking values from Spring Environment

You can write a temporary or dev-only diagnostic snippet:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigProbe implements ApplicationRunner {
    private final Environment environment;

    ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String value = environment.getProperty("app.cache.ttl");
        System.out.println("app.cache.ttl = " + value);
    }
}
~~~

Results from Environment reflect Spring's configuration resolution mechanism. This is more reliable than inspecting `application.yml` alone, because it accounts for environment variables, JVM system properties, or application arguments sharing the same key.

However, **null** from Environment.getProperty(...) does not prove a YAML line wrote null: it could also mean the key does not exist, was misspelled, sat at the wrong indentation level, or was not published by an active source. To know the root cause, compare loaded sources and actual binding types.

### 8.2. Checking source presence without exposing sensitive values

When locating configuration sources in development, you can use ConfigurableEnvironment to list PropertySource names:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

for (PropertySource<?> source : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

The snippet above requires the **environment** variable to have type **ConfigurableEnvironment** in scope. Do not print all values from every source because they may contain passwords, tokens, database connection strings, or other sensitive data.

When Spring Boot Actuator is deployed and properly secured, its environment endpoint can trace property origins while masking sensitive values. Never expose endpoints publicly just to debug YAML.

## 9. Combined scenario: a file broken in three ways

Suppose you have the following configuration snippet:

~~~yaml
app:
  mail:
    host: smtp.example.test
    port: 2525
  retries: 3
  retries: 5
  sender-name:
  mail:
    tls-enabled: true
~~~

The author intended:

- Mail server has host, port, and tls-enabled.
- retries equals 5.
- sender-name is an empty string, meaning no display name yet.

Yet the text has three problems:

1. Mapping **mail** appears twice at the same **app** level. Do not expect the parser to merge host/port with tls-enabled.
2. **retries** appears twice inside the same mapping. Do not use repeated keys to override.
3. **sender-name:** is an omitted scalar meaning YAML null; it does not clearly express an empty string.

Rewritten version expressing the intent directly:

~~~yaml
app:
  mail:
    host: smtp.example.test
    port: 2525
    tls-enabled: true
  retries: 5
  sender-name: ""
~~~

If sender-name is actually **required**, pick a meaningful string or declare validation rules; an empty string is only appropriate when the application defines it as valid input.

### 9.1. Same configuration in .properties format

~~~properties
app.mail.host=smtp.example.test
app.mail.port=2525
app.mail.tls-enabled=true
app.retries=5
app.sender-name=
~~~

In both formats, the target is a consistent logical property structure. The difference is that **YAML represents hierarchy through indentation**, whereas **properties represents hierarchy directly in key names**.

If a project has both application.properties and application.yml in the same location, check Spring Boot's Config Data precedence rules instead of assuming Spring merges both files in line order.

## 10. A repeatable troubleshooting workflow

Follow this workflow whenever configuration behaves unexpectedly:

**Step 1 — Write down the full key name.** From the bean or @ConfigurationProperties, identify the exact expected key, such as **app.mail.tls-enabled**. Do not just search the whole file for **enabled**.

**Step 2 — Check source syntax.** For YAML, verify parent mappings, leading spaces, list `-` markers, and any duplicate keys inside the same mapping. For `.properties`, find every line with the same key name.

**Step 3 — Distinguish values.** Clarify whether the application expects null, omitted, empty string, whitespace string, or literal "null". If business logic needs an on/off flag, prefer a clearly named boolean property.

**Step 4 — Verify active documents/profiles.** Determine whether the application loads profile-specific files or documents. The same key across multiple valid documents has specific precedence rules.

**Step 5 — Look for higher-precedence sources.** Check environment variables, JVM **-D** options, and application **--** arguments. The value in the file is not necessarily the effective value.

**Step 6 — Inspect what Spring actually receives.** Use Environment or bind to the configuration class; on failure, read the full property name, source, and conversion/validation message.

**Step 7 — Fix one clear configuration intent.** Merge duplicate mappings, fix indentation, use explicit empty/null notation, or move overrides to profiles; never mask the problem by adding more duplicate keys.

This workflow separates root causes even when the final symptom looks identical, such as a bean receiving a default value.

## 11. Practice exercises

### Exercise 1: Spotting duplicate keys in the same mapping

Given the configuration:

~~~yaml
server:
  port: 8080
server:
  shutdown: graceful
~~~

Rewrite it as a single server mapping containing both **port** and **shutdown**.

Reference answer:

~~~yaml
server:
  port: 8080
  shutdown: graceful
~~~

### Exercise 2: Reading wrong indentation levels

Given the YAML:

~~~yaml
app:
  http:
    connect-timeout: 2s
  read-timeout: 5s
~~~

What two keys result after flattening? If both timeouts are meant to be under **app.http**, fix the YAML.

Answer: the current structure produces **app.http.connect-timeout** and **app.read-timeout**. To put read-timeout under http as well:

~~~yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 5s
~~~

### Exercise 3: Distinguishing empty and null values

Examine the following snippet:

~~~yaml
app:
  a:
  b: null
  c: ""
  d: " "
  e: "null"
  f: []
~~~

At the YAML data level, **a** and **b** are null scalars; **c** is an empty string; **d** is a string with one space; **e** is the string "null"; **f** is an empty list. Predict what a String bean, a Collection bean, and Environment might receive, then verify on your project's exact Spring Boot version. Your prediction must account for both PropertySource loading and binding, rather than concluding from YAML text alone.

### Exercise 4: Comparing source precedence

`application.yml` declares:

~~~yaml
app:
  retries: 2
~~~

Launch command:

~~~bash
APP_RETRIES=4 java -Dapp.retries=6 -jar demo.jar --app.retries=8
~~~

Assuming default PropertySource order with no higher-precedence source, **Environment.getProperty("app.retries")** resolves to **8**. Removing **--app.retries=8** leaves **6**; removing the JVM system property as well lets environment variable **4** beat YAML file **2**.

This exercise demonstrates that a key appearing across multiple valid sources is a precedence question, whereas duplicate keys in YAML are a document structure issue.

## 12. Key principles to remember

- Within a **.properties** file, avoid declaring the same key twice; define each value once or separate by profile.
- Within **a single YAML document**, avoid duplicate keys in the same mapping. Never assume two mappings with the same name will merge automatically.
- **Misindentation** can make YAML unparseable, or worse, parse cleanly while producing completely different property names.
- **Omitted**, **null**, **""**, **" "**, and **"null"** have different meanings; Spring Boot also adds source loading and binding steps that should be verified against actual values.
- **application.properties** and **application.yml** have different syntax for empty strings; quotes in `.properties` do not behave like YAML quotes.
- A property can validly appear in multiple **PropertySources**; precedence determines the value Spring receives.
- For required settings, use **@ConfigurationProperties** with appropriate validation to catch errors early instead of running with ambiguous values.
- When debugging, inspect full property names and the values **Spring Environment** receives. Looking at a line in a file alone is not enough to determine runtime behavior.

Understanding the three layers **text syntax → PropertySource → binding** helps resolve duplicate keys, indentation, and null/empty bugs accurately without guesswork edits.
