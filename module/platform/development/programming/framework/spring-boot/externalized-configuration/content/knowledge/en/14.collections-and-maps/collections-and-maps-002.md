# Indexed Notation and Comma-Separated Lists in Spring Boot

## 1. Lesson Objectives

Spring Boot does not bind only a single string or number from `application.yaml` into Java. When configuration has multiple elements, you can use `List`, `Set`, arrays, `Map`, or a list of structured objects through `@ConfigurationProperties`. Two ways of declaring lists appear very frequently:

- **Indexed notation:** `app.servers[0]`, `app.servers[1]`, or `app.backends[0].base-url`.
- **Comma-separated values:** `app.servers=alpha,beta,gamma`.

For example, the two declarations below both describe three server names:

```properties
# Approach A: indexed elements
app.servers[0]=alpha
app.servers[1]=beta
app.servers[2]=gamma
```

```properties
# Approach B: a single comma-separated value
app.servers=alpha,beta,gamma
```

In a Spring Boot application, both approaches can be converted by the binder into:

```java
List<String> servers
```

However, **they are not equivalent choices in every situation**. Indexed notation fits when an element contains multiple fields, when ordering indices are needed, and when supplying configuration from sources such as environment variables. Comma-separated lists are concise for scalar values, but require caution when an element itself contains a comma. Furthermore, lists across multiple property sources are usually **replaced as a whole list**, not merged element-by-element by index like a patch.

This lesson is part of the **Collections and Maps** group in the **Spring Boot Externalized Configuration** topic. It focuses on how to **describe, bind, observe, and predict** lists, with comparisons to maps to avoid common misunderstandings.

After completing it, you will be able to:

1. Read and write properties with `[0]`, `[1]` indices in `.properties`, YAML, and CLI.
2. Bind a simple CSV string into `List<String>`, `List<Integer>`, or `List<Duration>` when appropriate converters are available.
3. Distinguish `List<String>` from `List<Backend>` containing multiple nested properties.
4. Map keys like `app.backends[0].base-url` into structured Java records.
5. Explain how environment variables represent indices and hierarchy.
6. Predict outcomes when a profile-specific file replaces a base list.
7. Understand why `Map` has different merging rules from `List`, and how to represent map keys containing special characters.
8. Practice with a Spring Boot 3.3, Java 21, Gradle application, including how to run and test it.
9. Detect missing-index errors, unexpected CSV data, type-conversion failures, and validation errors.
10. Choose a maintainable configuration structure when deploying across JARs, containers, and multiple profiles.

**Lab scope:** endpoints, labels, and identifiers in the examples are simulated; the console application makes no real network connections and prints no sensitive data.

## 2. A Single Property vs. a Collection of Elements

For a single property:

```yaml
app:
  region: ap-southeast-1
```

Java can use:

```java
String region
```

For multiple regions:

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
```

Java uses:

```java
List<String> regions
```

For a list of endpoints with an additional name and timeout:

```yaml
app:
  backends:
    - name: inventory
      base-url: https://inventory.example.test
      timeout: 2s
    - name: billing
      base-url: https://billing.example.test
      timeout: 3s
```

Java can use:

```java
List<Backend> backends
```

with:

```java
public record Backend(String name, URI baseUrl, Duration timeout) {}
```

A `List` has **order**. Swapping the positions of the same two elements can change behavior if the application uses order for priority selection or fallback.

Conversely, `Map<String,String>` represents a set of key-value pairs accessed by **key** instead of index:

```yaml
app:
  labels:
    team: platform
    stage: sandbox
```

Accessing `labels.get("team")` differs from `regions.get(0)`. Do not convert a map into a list merely because you see multiple lines of YAML.

## 3. Indexed Syntax `[n]` in `.properties`

Common form:

```properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.regions[2]=us-east-1
```

The numbers inside `[]` are **element indices**. They start at `0` in standard Java and Spring Boot examples.

Mapping when bound:

```text
app.regions[0] --> regions.get(0) --> ap-southeast-1
app.regions[1] --> regions.get(1) --> eu-west-1
app.regions[2] --> regions.get(2) --> us-east-1
```

This pattern matters because it appears in:

- `application.properties` files.
- Command-line arguments like `--app.regions[0]=...`.
- Configurations generated automatically by certain deployment systems.
- `PropertySource` entries that represent lists as indexed keys.
- Observation tables and binding failure messages.

### 3.1. Indexing Nested Objects

A `List<String>` only needs each element to be a string. But `List<Backend>` has multiple components:

```properties
app.backends[0].name=inventory
app.backends[0].base-url=https://inventory.example.test
app.backends[0].timeout=2s

app.backends[1].name=billing
app.backends[1].base-url=https://billing.example.test
app.backends[1].timeout=3s
```

The keys with index `0` together form **one** `Backend`; likewise, the keys with index `1` form another `Backend`.

You can visualize it as:

```text
app.backends
     |
     +-- [0]
     |    +-- name      = inventory
     |    +-- base-url  = https://inventory.example.test
     |    +-- timeout   = 2s
     |
     +-- [1]
          +-- name      = billing
          +-- base-url  = https://billing.example.test
          +-- timeout   = 3s
```

In Java:

```java
List<Backend> backends
```

and:

```java
Backend first = backends.get(0);
URI firstUrl = first.baseUrl();
```

**Do not** assign indices arbitrarily and assume Spring Boot will infer the order you meant. Use a contiguous sequence `0,1,2,...` when writing configuration, and use YAML lists whenever possible. If an element in the middle is missing or only a large index is passed, the binder may fail to build the expected structure or raise an error; treat a contiguous index sequence as the input contract for this lab.

### 3.2. Avoid Using Indices as Long-Term Identifiers

If a backend moves from index `0` to `1`, keys like `app.backends[0].timeout` will affect a different element. This can be hazardous with override files or environment variables trying to alter a single element.

When each object has an independent identifier and order is not needed, consider:

```yaml
app:
  backend-by-name:
    inventory:
      base-url: https://inventory.example.test
      timeout: 2s
    billing:
      base-url: https://billing.example.test
      timeout: 3s
```

and Java:

```java
Map<String, BackendSettings> backendByName
```

There, `inventory` and `billing` are stable keys, not ordinal numbers. If order carries business meaning, `List` remains the right choice, but manage the entire list as a unified set.

## 4. YAML Lists and Indexed Syntax Represent the Same Structure

YAML typically writes lists using leading dashes:

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
```

This structure can be viewed as:

```properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.regions[2]=us-east-1
```

Similarly, a YAML list of objects:

```yaml
app:
  backends:
    - name: inventory
      base-url: https://inventory.example.test
      timeout: 2s
    - name: billing
      base-url: https://billing.example.test
      timeout: 3s
```

corresponds to the indexed keys in the example from section 3.1.

YAML also supports an inline list syntax:

```yaml
app:
  regions: [ap-southeast-1, eu-west-1, us-east-1]
```

This is a **YAML sequence**, not a single string containing commas. When communicating with readers, distinguish between:

```yaml
# YAML sequence
app:
  regions: [alpha, beta, gamma]
```

and:

```yaml
# YAML scalar string; the binder can split it to create List<String>
app:
  regions: "alpha,beta,gamma"
```

Commas in a YAML flow sequence are part of YAML syntax; commas inside a quoted string are scalar content that the binder can convert into a collection.

## 5. Comma-Separated Lists (CSV-Style)

When a list contains simple scalar values, it can be declared as a single string:

```properties
app.regions=ap-southeast-1,eu-west-1,us-east-1
```

and bound to:

```java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<String> regions) {}
```

Inside the binding mechanism, Spring Boot uses an appropriate conversion service to convert the string value into `List<String>`.

Equivalent YAML scalar:

```yaml
app:
  regions: "ap-southeast-1,eu-west-1,us-east-1"
```

Do not assume `@Value("${app.regions}")` always yields the same type as `@ConfigurationProperties`. `@Value` first resolves placeholders and only then, depending on the injection point and converters, may perform type conversion; for structured configuration groups, `@ConfigurationProperties` is easier to control.

### 5.1. CSV Is Concise for Scalars, Not Object Structures

A string:

```properties
app.backends=inventory,billing
```

can produce a `List<String>` with two names, but it does **not** carry enough information to construct each `Backend(name, URI baseUrl, Duration timeout)` in this lab. To obtain a list of objects, declare the elements using a YAML list or indexed keys:

```properties
app.backends[0].name=inventory
app.backends[0].base-url=https://inventory.example.test
app.backends[0].timeout=2s
```

Do not try to pack multiple properties of an object into a string like:

```properties
app.backends=inventory|https://inventory.example.test|2s,billing|https://billing.example.test|3s
```

unless the project intentionally defines a custom converter/parser and has tests for that format. Spring Boot does not automatically interpret `|` as your custom object structure.

### 5.2. Types Other Than `String`

If the target is:

```java
List<Integer> retryCodes
```

and the data is:

```properties
app.retry-codes=408,429,503
```

The Binder can convert each element into `Integer` when conversion rules apply.

Similarly:

```java
List<Duration> retryIntervals
```

with:

```properties
app.retry-intervals=100ms,250ms,1s
```

Each element is converted to `Duration`. If an element such as `not-a-duration` is invalid, binding can fail; Spring Boot does not silently skip a broken element and use the rest.

### 5.3. Whitespace in CSV Strings

You may encounter:

```properties
app.regions=alpha, beta, gamma
```

With standard conversion, elements may be trimmed to match the target type, but do not treat whitespace and special-character handling rules across every converter as an immutable contract. If whitespace is genuinely meaningful data inside an element, use an explicit YAML sequence or a format capable of exact representation.

As a project convention, when using CSV for simple names or codes, standardize on:

```properties
app.regions=alpha,beta,gamma
```

rather than relying on spacing variants that are hard to distinguish in logs.

### 5.4. What If a Value Contains a Comma?

Suppose an element must be preserved verbatim:

```text
Ho Chi Minh City, Viet Nam
```

If you write:

```properties
app.locations=Ho Chi Minh City, Viet Nam,Hanoi
```

then which comma is **content** and which comma is a **separator**? There is not enough information in a plain CSV string to distinguish them safely.

The clear solution is to use a YAML sequence:

```yaml
app:
  locations:
    - "Ho Chi Minh City, Viet Nam"
    - "Hanoi"
```

If `.properties` is required, use indexed notation:

```properties
app.locations[0]=Ho Chi Minh City, Viet Nam
app.locations[1]=Hanoi
```

Because each element has its own key, the comma in the value belongs to that element's content. Do not assume that putting double quotes inside a CSV scalar will automatically turn the Spring Boot Binder into a full RFC 4180 CSV parser.

### 5.5. Empty Values and Empty Elements

Consider:

```properties
app.regions=
```

and:

```properties
app.regions=alpha,,gamma
```

These are two different scenarios. Conversion behavior depends on the target type and converter; an empty string may result in an empty collection or a different interpretation depending on context, whereas an empty element between two commas can cause problems if the target is a number or `Duration`.

If a collection must contain at least one meaningful element, use Bean Validation:

```java
@NotEmpty List<@NotBlank String> regions
```

For types that do not accept empty strings, rely on converters and validation to fail early rather than silently discarding empty values.

## 6. Lists in Environment Variables

When running in Docker, CI, or Kubernetes, values are often supplied via process environment variables.

For a scalar list, a manageable approach is:

```text
APP_REGIONS=ap-southeast-1,eu-west-1
```

Spring Boot can bind that value into `List<String> regions` in CSV style.

For an indexed element, the environment variable naming rule for lists uses **the index wrapped in underscores**:

```text
app.regions[0] -> APP_REGIONS_0_
app.regions[1] -> APP_REGIONS_1_
```

For nested objects, the idea is the same:

```text
app.backends[0].name     -> APP_BACKENDS_0_NAME
app.backends[0].base-url -> APP_BACKENDS_0_BASEURL
```

Note that `BASEURL` comes from canonical `base-url`: dashes are removed rather than replaced with `_` between the two words.

**Common mapping convention from canonical property to environment variable:**

1. Dots `.` are replaced with underscores `_`.
2. Dashes `-` are removed.
3. Names are converted to uppercase.
4. For list indices, the index number is enclosed in underscores according to list binding rules.

This is the **corresponding form for the environment source**, not a universal rule converting every character in every key format into a unique string. Escaping, special map keys, and custom binders may have different requirements.

### 6.1. Environment Variables for Scalar Lists

Bash:

```bash
APP_REGIONS=alpha,beta,gamma ./gradlew bootRun
```

PowerShell:

```powershell
$env:APP_REGIONS = 'alpha,beta,gamma'
.\gradlew.bat bootRun
Remove-Item Env:APP_REGIONS
```

If no higher-precedence source defines the same key, the application binds the new list from the environment variable.

### 6.2. Environment Variables for Indexed Lists

Bash:

```bash
APP_REGIONS_0_=alpha APP_REGIONS_1_=beta ./gradlew bootRun
```

PowerShell:

```powershell
${env:APP_REGIONS_0_} = 'alpha'
${env:APP_REGIONS_1_} = 'beta'
.\gradlew.bat bootRun
Remove-Item 'Env:APP_REGIONS_0_'
Remove-Item 'Env:APP_REGIONS_1_'
```

Some deployment systems have restrictions on characters in environment variable names and how they pass the environment through entrypoints. Check your platform's capabilities; for complex object lists, a YAML file mounted outside the JAR is usually easier to read and maintain than a set of environment variables full of index numbers.

### 6.3. A List from a Higher-Precedence Source Is Not a Per-Element Patch

Suppose the base YAML has:

```yaml
app:
  regions:
    - alpha
    - beta
```

If a higher-precedence source provides a list with only `gamma`, the result is usually:

```text
[gamma]
```

not:

```text
[gamma, beta]
```

This is the core difference from thinking "I modified index 0 so index 1 still comes from the old file". When a collection is provided by a higher-precedence source, the Spring Boot Binder generally binds **the entire list from that source**, rather than merging individual indices across sources.

To change one element while keeping the rest, declare **the entire required list** in the overriding source.

## 7. Differences Between List and Map When Combining Multiple Sources

Spring Boot has specific rules when binding collections from multiple `PropertySource` instances.

For `List`, the safe rule of thumb in scenarios such as profile files and property sources of different precedence is:

> A list from the appropriate higher-precedence source can **replace the entire list** from a lower-precedence source. Do not assume index-by-index merging.

For `Map`, **different keys** can be combined across multiple sources; for the **same key**, the higher-precedence source determines the value for that key.

Base configuration example:

```yaml
app:
  regions:
    - alpha
    - beta
  labels:
    team: platform
    stage: base
```

File `application-dev.yaml`:

```yaml
app:
  regions:
    - local
  labels:
    stage: development
```

When the `dev` profile is active, expected result:

```text
app.regions = [local]
app.labels.team = platform
app.labels.stage = development
```

Explanation: the list was replaced by the `dev` profile's list, while the map kept the `team` key from the base source and took the `stage` key from the dev source.

Do not generalize from this example that a **map of nested objects** always merges every field in a simple way. Binding behavior also depends on target type, source type, representation, and precedence. For a backend with many important fields, test it with an integration test using the exact runtime structure.

### 7.1. Map Keys with Special Characters

A map key containing slashes:

```text
/api/v1
```

must be preserved when the binder processes property names.

In `.properties`, you can use bracket notation:

```properties
app.labels.[/api/v1]=public-route
```

In YAML, the brackets must be wrapped in quotes when used as a map key:

```yaml
app:
  labels:
    "[/api/v1]": public-route
```

Then Java can access:

```java
properties.labels().get("/api/v1")
```

Note that `[0]` in a list denotes an **index**, whereas `[/api/v1]` in a map denotes a **literal key whose special characters must be preserved**. Using bracket notation in the right context prevents the binder from stripping or reinterpreting characters in the map key.

### 7.2. Dots in Map Keys

With a `Map<String, String>`, binding rules may preserve `.` in scalar-valued keys in common cases; however, with `Map<String, Object>` or nested maps, a dot is easily treated as a hierarchy separator.

To be certain a key is `a.b` rather than two levels `a` -> `b`, use bracket notation when declaring it:

```properties
app.labels.[a.b]=value
```

YAML:

```yaml
app:
  labels:
    "[a.b]": "value"
```

Do not rely on a simple string-map structure happening to interpret a key as intended and assume the same applies to every map type.

## 8. Choosing a Declaration Style by Data Type

| Target Data Type | Readable Declaration Style | Example |
| --- | --- | --- |
| Short `List<String>` | Comma-separated | `app.regions=alpha,beta` |
| Short `List<Integer>` | Comma-separated | `app.retry-codes=408,429,503` |
| Short `List<Duration>` | Comma-separated | `app.intervals=100ms,1s` |
| `List<String>` with comma in elements | YAML list or indexed | `app.locations[0]=City, Country` |
| Multi-field `List<Backend>` | YAML list or multiple indexed keys | `app.backends[0].name=...` |
| `Map<String,String>` | Direct key names | `app.labels.team=platform` |
| Identifier-keyed `Map<String,Backend>` | YAML map | `app.backend-by-name.inventory.base-url=...` |
| Map key with special characters | Bracket notation | `app.labels.[/api/v1]=...` |

Quick selection rule: **scalars with few elements** can use CSV; **structured objects** use YAML sequences or indexed keys; **items with stable identifiers** use maps. If a configuration spans multiple profiles and needs clear overrides, prefer explicit data descriptions rather than over-shortening to the point where it is hard to observe.

## 9. Sample Application: Collection Binding Observer

We will build a Spring Boot console application containing:

- `tags`: a list of strings supplied as a **comma-separated value**.
- `retryIntervals`: a list of `Duration` also supplied as a comma-separated value.
- `backends`: a list of objects, each having `name`, `baseUrl`, `timeout`.
- `labels`: a string map, including regular keys and keys with slashes.
- The Spring Boot Binder converts everything into a typed record.
- An `ApplicationRunner` prints the results in order and by position for easy observation.

The application only prints simulated data; it sends no requests to the URLs and requires no database or web server.

### 9.1. Directory Structure

```text
collection-binding-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/collections/
    │   │   ├── CollectionBindingApplication.java
    │   │   └── DemoProperties.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/collections/
            └── CollectionBindingTest.java
```

Create the skeleton with Spring Initializr, choosing Java 21, Gradle, and a Spring Boot version in the 3.3.x branch. Keep the Gradle Wrapper generated by the project.

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'collection-binding-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` supports Bean Validation via Jakarta Validation, helping detect missing lists or configuration objects missing mandatory fields.

In a repository that already manages shared plugins/dependencies, follow the repository's conventions rather than copying an entire new build setup.

### 9.3. Base `application.yaml` File

```yaml
spring:
  main:
    web-application-type: none

demo:
  tags: "alpha,beta,gamma"
  retry-intervals: "100ms,250ms,1s"

  backends:
    - name: inventory
      base-url: "https://inventory.example.test"
      timeout: 2s
    - name: billing
      base-url: "https://billing.example.test"
      timeout: 3s

  labels:
    team: education
    stage: base
    "[/api/v1]": example-route
```

The first two fields are YAML scalars containing commas. `backends` is a YAML sequence. `labels` is a YAML map.

Although the prefix in this lesson is `demo`, the same rules apply to any other application prefix such as `app`, `client`, or `service`.

### 9.4. Equivalent `.properties` Version for Comparison

If you want to use `.properties` **instead of** the YAML file in the same location, you can put:

```properties
spring.main.web-application-type=none

demo.tags=alpha,beta,gamma
demo.retry-intervals=100ms,250ms,1s

demo.backends[0].name=inventory
demo.backends[0].base-url=https://inventory.example.test
demo.backends[0].timeout=2s

demo.backends[1].name=billing
demo.backends[1].base-url=https://billing.example.test
demo.backends[1].timeout=3s

demo.labels.team=education
demo.labels.stage=base
demo.labels.[/api/v1]=example-route
```

This is a semantically equivalent example. Do not create both `application.properties` and `application.yaml` in the same location and assume both will merge as intended; Spring Boot has format precedence rules when both files coexist. In this lab, choose **one of the two** so the results are not confounded.

### 9.5. Configuration Record with Lists and Maps

`src/main/java/dev/example/collections/DemoProperties.java`:

```java
package dev.example.collections;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotEmpty List<@NotBlank String> tags,
        @NotEmpty List<@NotNull Duration> retryIntervals,
        @Valid @NotEmpty List<Backend> backends,
        Map<String, String> labels
) {
    public DemoProperties {
        tags = tags == null ? List.of() : List.copyOf(tags);
        retryIntervals = retryIntervals == null
                ? List.of() : List.copyOf(retryIntervals);
        backends = backends == null
                ? List.of() : List.copyOf(backends);
        labels = labels == null ? Map.of() : Map.copyOf(labels);
    }

    public record Backend(
            @NotBlank String name,
            @NotNull URI baseUrl,
            @NotNull Duration timeout
    ) {}
}
```

Explanation:

1. `@ConfigurationProperties(prefix = "demo")` tells the Binder to read the `demo.*` group.
2. `List<String> tags` receives data from a comma-separated scalar or from indexed elements.
3. `List<Duration> retryIntervals` demonstrates converting each element to a duration type.
4. `@Valid List<Backend>` propagates validation into child objects; `Backend` is a nested record.
5. `Map<String,String> labels` stores data by key, including `"/api/v1"` thanks to bracket notation in YAML.
6. `List.copyOf` and `Map.copyOf` avoid storing mutable collections directly in the record after binding.
7. `@NotEmpty` requires critical collections to have elements.
8. `@NotBlank` on string elements and `@NotNull` on object components express input constraints. To further validate the domain/range of timeout, custom validation or another suitable mechanism can be used.

Records are immutable at the reference level, but if the elements inside are mutable objects, the collection is only shallowly immutable. The example uses a `Backend` record, `URI`, and `Duration` to minimize mutable state.

### 9.6. Main Class and Console Report

`src/main/java/dev/example/collections/CollectionBindingApplication.java`:

```java
package dev.example.collections;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CollectionBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(CollectionBindingApplication.class, args);
    }

    @Bean
    ApplicationRunner report(
            DemoProperties properties,
            Environment environment) {
        return args -> {
            System.out.println("=== COLLECTION BINDING LAB ===");
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));

            System.out.println("tags size = "
                    + properties.tags().size());
            for (int i = 0; i < properties.tags().size(); i++) {
                System.out.println("tags[" + i + "] = "
                        + properties.tags().get(i));
            }

            System.out.println("retryIntervals = "
                    + properties.retryIntervals());

            System.out.println("backends size = "
                    + properties.backends().size());
            for (int i = 0; i < properties.backends().size(); i++) {
                DemoProperties.Backend backend =
                        properties.backends().get(i);
                System.out.println(
                        "backends[" + i + "] name="
                        + backend.name()
                        + ", url=" + backend.baseUrl()
                        + ", timeout=" + backend.timeout());
            }

            System.out.println("labels.team = "
                    + properties.labels().get("team"));
            System.out.println("labels.stage = "
                    + properties.labels().get("stage"));
            System.out.println("labels./api/v1 = "
                    + properties.labels().get("/api/v1"));
        };
    }
}
```

`ApplicationRunner` runs after the configuration bean has been created and bound in the application context. Because Spring Boot is configured with `web-application-type: none`, the program prints the results and exits without needing an HTTP server.

**Do not print the entire `Environment` in a real application.** In this lesson, `tags`, `backends`, and `labels` contain only simulated data; in real configurations, maps/lists may hold tokens, URLs with credentials, or other information that must not be logged.

## 10. Experiment 1: CSV Scalars and YAML Object List

From the project root directory:

macOS/Linux:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Expected key lines:

```text
=== COLLECTION BINDING LAB ===
activeProfiles = []
tags size = 3
tags[0] = alpha
tags[1] = beta
tags[2] = gamma
retryIntervals = [PT0.1S, PT0.25S, PT1S]
backends size = 2
backends[0] name=inventory, url=https://inventory.example.test, timeout=PT2S
backends[1] name=billing, url=https://billing.example.test, timeout=PT3S
labels.team = education
labels.stage = base
labels./api/v1 = example-route
```

Output for `Duration` uses Java's default formatting, so `100ms` becomes `PT0.1S` and `250ms` becomes `PT0.25S`.

Observation table:

| Property | Form in YAML | Java Target | Expected |
| --- | --- | --- | --- |
| `demo.tags` | CSV scalar | `List<String>` | 3 elements |
| `demo.retry-intervals` | CSV scalar | `List<Duration>` | 3 durations |
| `demo.backends` | YAML object sequence | `List<Backend>` | 2 records |
| `demo.labels` | YAML map | `Map<String,String>` | 3 keys |

The important point is not which file syntax is shorter, but that the Binder infers the structure **from the source representation and the target Java type**.

## 11. Experiment 2: Changing CSV to a YAML Sequence

Edit `application.yaml`:

```yaml
demo:
  tags:
    - alpha
    - beta
    - gamma
```

Keep the other entries as they were. Start the application again. Expected:

```text
tags size = 3
tags[0] = alpha
tags[1] = beta
tags[2] = gamma
```

Even though the source representation changed from a CSV string to a sequence, `DemoProperties` **needs no changes** because the target type is still `List<String>`.

Now try:

```yaml
demo:
  tags:
    - "north, central"
    - "south"
```

Expected:

```text
tags size = 2
tags[0] = north, central
tags[1] = south
```

A comma inside a YAML list element does not automatically act as a collection separator. This illustrates why a YAML sequence or indexed notation should be chosen when element contents contain commas or meaningful whitespace.

After the experiment, you can restore `tags: "alpha,beta,gamma"` to continue with the steps based on the base configuration.

## 12. Experiment 3: Overriding CSV via CLI Arguments

Using the base configuration from section 9, run:

macOS/Linux:

```bash
./gradlew bootRun --args='--demo.tags=red,green,blue'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.tags=red,green,blue"
```

Expected:

```text
tags size = 3
tags[0] = red
tags[1] = green
tags[2] = blue
```

CLI arguments are processed by Spring Boot as a configuration source with higher precedence than `application.yaml` in standard setups. Therefore, the list from the CLI is used instead of the base list.

There is no need to pass:

```text
--demo.tags[0]=red
--demo.tags[1]=green
--demo.tags[2]=blue
```

when the elements are simple scalars without commas. If you want to supply `List<Backend>` with multiple fields, indexed syntax becomes more useful.

### 12.1. A String Containing a Comma in One Element via CLI

If you try:

```bash
./gradlew bootRun --args='--demo.tags=red,green\,blue'
```

there are multiple layers of string handling and escaping: shell, Gradle, CLI, property placeholders, and converters. Do not design a production contract around an untested escaping style.

When an element contains a meaningful comma, switch to a YAML file with a sequence or separate indexed properties. That approach is easier to understand, easier to review, and less dependent on the parsers of argument-passing layers.

## 13. Experiment 4: Overriding an Object List Using CLI Indices

Suppose during a test run you want **only one backend** named `sandbox` instead of the two backends in YAML.

Use:

macOS/Linux:

```bash
./gradlew bootRun --args='--demo.backends[0].name=sandbox --demo.backends[0].base-url=https://sandbox.example.test --demo.backends[0].timeout=1s'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.backends[0].name=sandbox --demo.backends[0].base-url=https://sandbox.example.test --demo.backends[0].timeout=1s"
```

Expected:

```text
backends size = 1
backends[0] name=sandbox, url=https://sandbox.example.test, timeout=PT1S
```

The CLI supplied the backend list from a higher-precedence source. **The list in the base YAML is not used to supply a second backend** into the resulting list.

A common mistake is passing only:

```text
--demo.backends[0].timeout=1s
```

expecting the binder to pull `name` and `base-url` for index 0 from the base YAML and only change timeout. Do not rely on that assumption. When a list from another source is selected, the element's fields must be sufficiently specified to bind a valid object; if any are missing, validation may fail.

This guide treats a list override as **a complete replacement configuration**. If you want to change a few properties by a fixed identifier name, consider switching to a map or supplying the full list in the overriding source.

### 13.1. Shell Quoting for Square Brackets

In Bash or Zsh, `[` and `]` can participate in pattern matching if not properly quoted. In PowerShell, quoting rules also differ between direct commands and arguments passed to Gradle.

In the examples above, the entire `--args='...'` or `--args="..."` content is passed as one string to Gradle. When running the JAR directly, you can quote each argument containing `[n]`:

```bash
java -jar app.jar \
  '--demo.backends[0].name=sandbox' \
  '--demo.backends[0].base-url=https://sandbox.example.test' \
  '--demo.backends[0].timeout=1s'
```

This ensures the shell preserves the square brackets so Spring Boot receives the exact property names.

## 14. Experiment 5: The `dev` Profile Replaces the Entire List

Create `src/main/resources/application-dev.yaml`:

```yaml
demo:
  tags:
    - local
    - debug

  retry-intervals: "50ms,100ms"

  backends:
    - name: local
      base-url: "http://localhost:9090"
      timeout: 500ms

  labels:
    stage: development
```

Run:

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Expected:

```text
activeProfiles = [dev]
tags size = 2
tags[0] = local
tags[1] = debug
retryIntervals = [PT0.05S, PT0.1S]
backends size = 1
backends[0] name=local, url=http://localhost:9090, timeout=PT0.5S
labels.team = education
labels.stage = development
labels./api/v1 = example-route
```

Analysis:

- `demo.tags` from the `dev` profile replaces the three-element base list.
- `demo.retry-intervals` also replaces the base list.
- `demo.backends` from `dev` has exactly one object `local`, without automatically keeping `billing`.
- `demo.labels.stage` in `dev` overrides `base`.
- `demo.labels.team` and `[/api/v1]` were not overridden and continue to come from the base map.

Therefore, **List and Map should not be assumed to follow the same merge rules**. When writing a profile override for a List, include the entire list needed for that profile.

### 14.1. Is Writing Only `backends[0].timeout` in the Dev File Safe?

For example:

```properties
demo.backends[0].timeout=100ms
```

in a higher-precedence config source is not a safe way to tweak only the timeout of the `inventory` element while keeping all fields from the base list. It can cause the binder to try constructing a new list missing required components.

If you need to override individual backends by name, a structure like `Map<String, BackendConfig>` is usually more appropriate. Even with maps, test nested object merging rules across real sources.

## 15. Experiment 6: Using Environment Variables to Replace a List

Return to the base configuration, without enabling the `dev` profile:

Bash:

```bash
DEMO_TAGS=from-env-1,from-env-2 ./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_TAGS = 'from-env-1,from-env-2'
.\gradlew.bat bootRun
Remove-Item Env:DEMO_TAGS
```

Expect the `tags` list to have two elements from the environment variable, rather than the three base elements. This is convenient for container environments, provided each element is a simple scalar with no ambiguous delimiters.

To override the backend list via environment variables, supply all required fields and indices according to the variable naming rules:

```text
DEMO_BACKENDS_0_NAME=sandbox
DEMO_BACKENDS_0_BASEURL=https://sandbox.example.test
DEMO_BACKENDS_0_TIMEOUT=1s
```

In some deployment systems, indexed variables are harder to maintain than YAML files. Consider mounting a configuration file outside the JAR when object lists are long or change frequently.

## 16. Testing Binding with JUnit

`src/test/java/dev/example/collections/CollectionBindingTest.java`:

```java
package dev.example.collections;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.tags=from-test-a,from-test-b",
        "demo.backends[0].name=from-test",
        "demo.backends[0].base-url=https://test.example.test",
        "demo.backends[0].timeout=800ms"
})
class CollectionBindingTest {

    @Autowired
    DemoProperties properties;

    @Test
    void csvValuesAreConvertedToList() {
        assertEquals(
                List.of("from-test-a", "from-test-b"),
                properties.tags());
    }

    @Test
    void indexedPropertiesCreateOneNestedObject() {
        assertEquals(1, properties.backends().size());
        DemoProperties.Backend only =
                properties.backends().get(0);
        assertEquals("from-test", only.name());
        assertEquals(URI.create("https://test.example.test"),
                only.baseUrl());
        assertEquals(Duration.ofMillis(800),
                only.timeout());
    }

    @Test
    void otherMapKeysFromBaseSourceRemainAvailable() {
        assertEquals("education",
                properties.labels().get("team"));
        assertTrue(properties.labels().containsKey("/api/v1"));
    }
}
```

Run:

macOS/Linux:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

These tests verify two different things:

1. A CSV string in the test source is converted into `List<String>`.
2. Indexed keys in the test source construct one `Backend` from three fields.

The `Map` test confirms that base keys are not lost merely because a higher-precedence source overrides other collections. If you change config sources or profiles, keep tests aligned with the sources actually in use.

### 16.1. Testing Failure Scenarios

To practice, try running with an invalid duration element:

```bash
./gradlew bootRun --args='--demo.retry-intervals=100ms,not-a-duration'
```

The Binder will fail to convert the invalid element into `Duration` under normal conversion. An application with critical configuration should fail at startup rather than silently dropping a malformed element.

Try using a CSV containing only whitespace or an empty list when the record has `@NotEmpty`. Validation helps catch cases that violate the data contract. Conversion errors and validation errors are two distinct categories: one **cannot convert the type**, while the other **converts successfully but violates constraints**.

If you want to write tests verifying startup failures, use `ApplicationContextRunner` to create a controlled context and assert failure, rather than using `@SpringBootTest` and breaking context startup for the whole test suite.

## 17. Comparing List Reading via `Environment`, `@Value`, and `@ConfigurationProperties`

### 17.1. `Environment.getProperty()`

With a property:

```properties
demo.tags=alpha,beta,gamma
```

you can call:

```java
String raw = environment.getProperty("demo.tags");
```

The result is typically the raw string stored in the source, for example:

```text
alpha,beta,gamma
```

However, if the list is declared using a YAML sequence or keys `demo.tags[0]`, `demo.tags[1]`, **not every source provides a scalar property named `demo.tags`**. Calling `getProperty("demo.tags")` cannot replace reliable collection binding across all source types.

### 17.2. `@Value`

An injection point:

```java
@Value("${demo.tags}")
private String rawTags;
```

depends on whether the `demo.tags` placeholder resolves to a suitable value. With a CSV scalar, this can be simple. With an indexed structure, a root placeholder does not guarantee you will receive an aggregated CSV string.

If you need `List<String>` via `@Value`, the framework can convert from a string to a collection depending on configured converters; however, for **structured property groups**, `@ConfigurationProperties` is clearer and safer.

### 17.3. `@ConfigurationProperties`

With:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(List<String> tags) {}
```

The Binder is designed to accept various representations and produce a typed list. This is the preferred choice when:

- The list has many elements or nested objects.
- Type conversions such as `Duration` or `URI` are involved.
- Profile overrides are used.
- Validation is required.
- Multiple beans consume the same configuration.
- Consistent testing across YAML files, environment, and CLI is needed.

Do not confuse **looking up a single key** (`Environment.getProperty`) with **binding a multi-key structure** (`@ConfigurationProperties`).

## 18. Common Pitfalls with Indexed Notation

### 18.1. Starting Indices at 1

```properties
demo.tags[1]=alpha
demo.tags[2]=beta
```

If you want a two-element list, use `0` and `1`. A sequence starting at `1` leaves an index gap at `0`, causing unexpected binding results. Keep indices contiguous starting from `0` to avoid structural errors.

### 18.2. Leaving a Gap in the Middle

```properties
demo.tags[0]=alpha
demo.tags[2]=gamma
```

Do not assume the Binder will fill in a `null` or pull index `1` from a base file. Renumber the indices or declare the full list.

### 18.3. Misnaming Nested Properties

```properties
demo.backends[0].baseurl=https://inventory.example.test
```

In some cases relaxed binding may accept variants, but the readable canonical name is:

```properties
demo.backends[0].base-url=https://inventory.example.test
```

Keep kebab-case in files and placeholders to reduce ambiguity when mapping to environment variables.

### 18.4. Missing Required Fields on an Object

```properties
demo.backends[0].name=inventory
```

If the `Backend` record requires both `baseUrl` and `timeout`, a higher-precedence list source can create an object missing fields. `@NotNull` validation reports the error early instead of throwing a `NullPointerException` later when a service calls `backend.baseUrl()`.

### 18.5. Using Square Brackets in the Shell Without Quoting

A command containing `[0]` may be interpreted by the shell as a pattern wildcard. Quote argument names when running directly, or use proper `--args` syntax with Gradle so Spring receives the exact property name.

## 19. Common Pitfalls with Comma-Separated Lists

### 19.1. Elements Containing Commas

Address or label data containing commas should use a YAML list or indexed properties. Avoid inventing ad-hoc CSV parsers by adding quotes inside strings without an agreed escaping rule.

### 19.2. An Element Cannot Be Converted to the Target Type

```properties
demo.retry-intervals=100ms,error,1s
```

The Binder must convert elements to `Duration`; the element `error` is invalid. Do not handle this by falling back to defaults without notifying operators.

### 19.3. Using a CSV String to Describe Complex Objects

Do not assume a format like `name,url,timeout` is automatically understood as a three-field record. Use YAML sequences or indexed keys so each field is clearly named, or build a custom converter if that format is a legitimate product requirement.

### 19.4. Unexpected Whitespace

When users copy a CSV string from a spreadsheet or secret manager, leading or trailing spaces may slip in. For critical configurations, validators should verify meaningful content, and input conventions should avoid ambiguous whitespace.

### 19.5. An Overriding Source Has an Empty String

If a higher-precedence source supplies `demo.tags=` while the base file has three elements, do not assume the Binder will automatically fall back to the base list. The higher-precedence source can alter how the value is resolved. For mandatory lists, use `@NotEmpty` and inspect the actual data.

## 20. Troubleshooting When Profiles or Environments Yield Different Results

A concise workflow:

**Step 1 — Identify the Java target.** Is it `List<String>`, `List<Backend>`, `List<Duration>`, or `Map<String,String>`? A source expression only makes sense once you know what type the Binder needs to build.

**Step 2 — List all property sources that may contain the same prefix.** Base files, profile-specific files, files outside the JAR, environment variables, CLI, test sources, or imported sources.

**Step 3 — Identify the highest-precedence source.** If two sources declare the list, do not merge lists by index like a patch unless a custom mechanism is explicitly designed for it.

**Step 4 — Check the source representation.** CSV scalar, YAML sequence, or `[n]` indexed keys? Different structures affect what `Environment.getProperty` displays.

**Step 5 — Verify canonical names.** `demo.backends[0].base-url` should map to `baseUrl` on `Backend`, and the indexed environment variable corresponds to `DEMO_BACKENDS_0_BASEURL`.

**Step 6 — Verify indices.** Do they start at 0 and run contiguously? Does each object have all required fields?

**Step 7 — Check conversion and validation.** Can the values convert to `Duration`, `URI`, or `int`? Is a required list or component empty?

**Step 8 — Restart the application after editing files.** Config Data is normally loaded at startup. A bound record bean does not automatically change when you edit YAML externally.

**Step 9 — Record the output and change one factor at a time.** Use a runner to print list size, indices, simulated values, and allowed map keys. There is no need to dump the entire `Environment`.

If dealing with sensitive data or lists of tokens, do not print every element for debugging. Use presence/absence flags, counts, or checks against a safe allowlisted set of keys instead.

## 21. Advanced Practice Exercises

### Exercise A — Three Ways to Declare the Same List

Create a `List<String> colors` from:

1. YAML sequence: `[red, green, blue]`.
2. `.properties` indexed: `demo.colors[0]=red`, ...
3. `.properties` CSV: `demo.colors=red,green,blue`.

Write a small record and an `ApplicationRunner` that prints each element. Note when these structures yield identical results, and observe the difference when an element string contains a comma.

### Exercise B — A List of Objects with Three Fields

Design:

```java
public record Worker(
        String name,
        int concurrency,
        Duration timeout
) {}
```

Write indexed properties for two workers named `email` and `billing`. Ensure indices are contiguous and all three fields are present on each object. Convert to a YAML sequence and prove the Java bean needs no changes.

### Exercise C — Profile Override

The base file has three backends. `application-dev.yaml` has only one backend `local`. Predict and verify the list size. Then try writing only one property for index `0` in the profile and record the application's behavior/error with validation enabled.

Explain why the profile configuration here should describe **the complete list to use**, rather than editing a single element from the base file.

### Exercise D — Map with Special Keys

Add:

```properties
demo.labels.[/internal/v2]=internal-route
demo.labels.[a.b]=with-dot
```

In Java, read:

```java
labels.get("/internal/v2")
labels.get("a.b")
```

Then convert to YAML with quoted bracketed map keys. This exercise contrasts **map key** brackets with **list index** brackets.

### Exercise E — List of Durations

Declare:

```properties
demo.retry-intervals=50ms,250ms,2s
```

Bind into `List<Duration>` and compute the total milliseconds in a pure Java service. If an `invalid` value is present, predict which error occurs. No network calls or actual sleeping are needed in this lab.

### Exercise F — Converting a List to an Identifier-Keyed Map

Suppose the application wants to override just the `billing` backend without caring about its position in a list. Refactor the design from:

```java
List<Backend> backends
```

to:

```java
Map<String, BackendSettings> backendByName
```

and use keys `inventory`, `billing`. Write YAML for each backend. Explain the benefits of stable keys and the responsibility of validating nested map value objects.

### Exercise G — Writing an Integration Test for the Configuration Contract

Write tests covering three cases:

- CSV `alpha,beta` becomes two elements.
- Indexed objects construct `Backend` with `URI` and `Duration`.
- The `dev` profile replaces the base list while the map retains non-overlapping keys.

Use `@SpringBootTest` or `ApplicationContextRunner` and control profiles/source properties so tests are repeatable.

## 22. Self-Check Questions

**1.** How do `demo.tags[0]` and `demo.tags[1]` differ from `demo.tags=one,two`? When do they produce the same `List<String>`?

**2.** Why is writing `demo.locations=City, Country,Hanoi` unsafe if `City, Country` is meant to be a single element?

**3.** With `List<Backend>`, why does a string `inventory,billing` fail to fully describe `baseUrl` and `timeout`?

**4.** Which environment variable corresponds to `demo.backends[0].base-url` according to the Spring Boot rules covered in this lesson?

**5.** The base file has `regions=[a,b]`, and the dev file has `regions=[local]`. When dev is active, what can the list be? Why is `[local,b]` not the default?

**6.** The base map has `team=platform`, `stage=base`, and the dev map has only `stage=development`. What typical outcome differs from a list override?

**7.** Why must a YAML map key `[/api/v1]` be quoted?

**8.** Should you read `Environment.getProperty("demo.backends")` and assume it always returns a string containing all indexed objects?

**9.** An indexed list declares elements 0 and 2 while omitting 1. How should you fix it?

**10.** If a CSV config contains `100ms,not-a-duration`, should the system ignore the broken element or raise a conversion error?

**11.** Why must you start a new process in this lab after editing `application-dev.yaml`?

**12.** When should you switch from an indexed list to a map with stable keys?

**Answer Key:**

1. One uses indexed keys, the other supplies a CSV scalar; for target `List<String>` and simple data, both can produce a list with the same order.
2. The comma acts as both data and separator; use a YAML sequence or indexed properties to preserve the element.
3. Because the object has multiple fields; a YAML object list or indexed property keys are required.
4. `DEMO_BACKENDS_0_BASEURL`.
5. `[local]`, because a list from a higher-precedence source can replace the list rather than merging by index with the base file.
6. The map can combine the `team` key from base and override the `stage` key from dev.
7. Because `[]` must be represented as a valid YAML key name and the binder needs to preserve the special string.
8. No; indexed properties do not by default create a root scalar `demo.backends` suitable for `getProperty()`.
9. Renumber indices contiguously starting from 0 or declare all elements.
10. Report a conversion error; do not hide broken configuration by dropping elements.
11. Config Data is normally loaded at startup; bound beans do not automatically refresh.
12. When each element has a stable identifier and needs to be accessed/overridden by name rather than by order.

## 23. Applying to Real Projects

An easy-to-follow convention:

```text
Simple scalars, few elements:
  YAML sequence or comma-separated.

Scalars with special delimiter characters:
  YAML sequence or indexed keys.

List of objects with multiple fields:
  YAML sequence or contiguous indexed keys.

Collection overrides across profiles/CLI/environment:
  Write the complete list in the higher-precedence source.

Elements with stable IDs needing per-ID overrides:
  Consider Map instead of List.

Map keys containing meaningful slashes/dots:
  Use bracket notation and quote properly in YAML.

Java code:
  @ConfigurationProperties + type conversion + validation.
```

When designing configuration in an organization, document canonical property names, target types, allowed override sources, update strategies, and empty-value semantics. Treating lists as **ordered snapshots** and maps as **keyed datasets** helps operators predict results across local, profiles, CI, and containers.

Summary diagram:

```text
application.yaml / properties / environment / CLI
                         |
                         v
                 Property Sources
                         |
                 Source precedence
                         |
                         v
              @ConfigurationProperties
                         |
        +----------------+----------------+
        |                |                |
   CSV / index       YAML sequence     YAML / key-value
        |                |                |
        v                v                v
  List<String>      List<Backend>    Map<String,String>
                         |
                         v
             Validation + application usage
```

Key takeaways to remember: **`[0]`, `[1]` describe positions in a collection; commas describe converting a scalar string into multiple elements; and Map describes stable keys.** When a higher-precedence configuration source changes a List, do not attempt to merge individual indices from a lower-precedence source. Bind to clear Java types, test both profile overrides and validation, and observe the output using a small application like this lab.

### References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), sections *Type-safe Configuration Properties*, *Relaxed Binding*, *Merging Complex Types*, *Binding Maps*.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html), using `application-dev.yaml` and profile-specific Config Data.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html), conversion service and collection types.
