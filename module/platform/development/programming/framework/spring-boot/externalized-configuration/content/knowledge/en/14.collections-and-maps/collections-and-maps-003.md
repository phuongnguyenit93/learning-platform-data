# Binding Lists of Objects with Nested Structures

Spring Boot Externalized Configuration is not limited to reading single keys like `server.port` or `app.enabled`. In real-world applications, configuration often takes the shape of **a list of objects, where each object contains nested objects, lists, maps, and typed fields**. For example, an event-processing system has multiple pipelines; each pipeline has its own retry policy, a list of endpoints, and each endpoint has different headers or operational options.

Spring Boot provides **`@ConfigurationProperties` and the Binder** to convert YAML structures or indexed keys in `.properties` into `List<Pipeline>`, `List<Destination>`, `Map<String,String>`, and nested records/classes. The focus of this lesson is how to design configuration trees, declare Java types, map indices, apply validation, understand precedence when multiple configuration sources exist, and diagnose common errors.

The examples use Spring Boot 3.x with Java 17+ and Jakarta Bean Validation in the validation section. Principles for lists, maps, and Config Data are also useful when working with any Spring Boot version that supports the Configuration Properties Binder.

## 1. What Does a Nested List of Objects Look Like?

Suppose an application has the following configuration:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
          headers:
            x-channel: retail
            x-region: asia
        - id: backup
          url: https://backup.example.test/orders
          timeout: 5s
          headers:
            x-channel: fallback
      labels:
        owner: team-orders
        tier: critical

    - name: invoices
      enabled: false
      retry:
        max-attempts: 1
        backoff: 1s
      destinations:
        - id: billing
          url: https://billing.example.test/events
          timeout: 3s
          headers:
            x-channel: finance
      labels:
        owner: team-finance
        tier: standard
~~~

Data tree:

~~~text
app
└── pipelines                              List<Pipeline>
    ├── [0]                                Pipeline
    │   ├── name: orders                   String
    │   ├── enabled: true                  boolean
    │   ├── retry                          Retry
    │   │   ├── max-attempts: 3            int
    │   │   └── backoff: 250ms             Duration
    │   ├── destinations                   List<Destination>
    │   │   ├── [0] primary                Destination
    │   │   │   ├── url                    URI
    │   │   │   ├── timeout                Duration
    │   │   │   └── headers                Map<String,String>
    │   │   └── [1] backup                 Destination
    │   └── labels                         Map<String,String>
    └── [1]                                Pipeline
        ├── name: invoices
        ├── enabled: false
        ├── retry
        ├── destinations
        └── labels
~~~

There are **two levels of lists**: `pipelines` and `destinations`. Each element of `pipelines` in turn contains a `retry` object, a `destinations` list, and a `labels` map. This is a classic case for using typed binding rather than manually reading individual keys with `Environment.getProperty(...)`.

An important point: the YAML item after `-` is not a plain string. It is an **object** because inside it are the fields `name`, `enabled`, `retry`, `destinations`, and `labels`.

## 2. From YAML to Java: Designing Root and Nested Records

We want a root object managing the `app.*` group. Use the `PipelineProperties` record:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record PipelineProperties(
    List<Pipeline> pipelines
) {
    public record Pipeline(
        String name,
        boolean enabled,
        Retry retry,
        List<Destination> destinations,
        Map<String, String> labels
    ) {}

    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}

    public record Destination(
        String id,
        URI url,
        Duration timeout,
        Map<String, String> headers
    ) {}
}
~~~

This is an example of a **root record and nested records**. Property mapping structure:

| YAML path | Java path | Type |
| --- | --- | --- |
| `app.pipelines` | `pipelines` | `List<Pipeline>` |
| `app.pipelines[0].name` | `pipelines.get(0).name()` | `String` |
| `app.pipelines[0].enabled` | `pipelines.get(0).enabled()` | `boolean` |
| `app.pipelines[0].retry.max-attempts` | `pipelines.get(0).retry().maxAttempts()` | `int` |
| `app.pipelines[0].retry.backoff` | `pipelines.get(0).retry().backoff()` | `Duration` |
| `app.pipelines[0].destinations` | `pipelines.get(0).destinations()` | `List<Destination>` |
| `app.pipelines[0].destinations[1].id` | `pipelines.get(0).destinations().get(1).id()` | `String` |
| `app.pipelines[0].destinations[0].url` | `pipelines.get(0).destinations().get(0).url()` | `URI` |
| `app.pipelines[0].labels` | `pipelines.get(0).labels()` | `Map<String,String>` |

The Spring Boot Binder inspects the **generic type of the list**, sees that elements must become `Pipeline`, and then inspects the record components of `Pipeline` to instantiate `Retry`, `Destination`, and the corresponding maps. You do not need to call each nested record's constructor in application code.

### Why Use `URI` and `Duration` Instead of `String`?

YAML configuration such as `timeout: 2s` is text, yet the Java model can use `Duration` to express a **wait duration** explicitly. Similarly, an endpoint address binds to `URI`. When input data fails type validation, the Binder can report the error while constructing the bean, avoiding late failures when business code uses the value.

## 3. Registering the `@ConfigurationProperties` Bean

`@ConfigurationProperties` declares the prefix, but a bean registration mechanism is still needed. A common approach is scanning annotated types:

~~~java
package com.example.orders;

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

With structure:

~~~text
src/main/java/
  com/example/orders/
    OrderApplication.java
    config/
      PipelineProperties.java
    service/
      PipelineRunner.java
~~~

`@ConfigurationPropertiesScan` on package `com.example.orders` can find `PipelineProperties` inside the subpackage `com.example.orders.config`.

Or register explicitly if you want to enable only one type:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PipelineProperties.class)
public class PipelineConfiguration {}
~~~

`PipelineConfiguration` must be included in the Spring context, for example within component scan range or imported appropriately. For a constructor-bound root record, do not add `@Component` just for Spring to find the record; use the mechanism dedicated to configuration properties.

**Nested records `Retry` and `Destination` are not standalone Spring beans in this example.** They are value objects inside root `PipelineProperties`, constructed by the Binder while binding the root.

## 4. Accessing the Bound List in Business Code

A service can inject the exact typed bean:

~~~java
package com.example.orders.service;

import com.example.orders.config.PipelineProperties;
import org.springframework.stereotype.Service;

@Service
public class PipelineRunner {
    private final PipelineProperties config;

    public PipelineRunner(PipelineProperties config) {
        this.config = config;
    }

    public void printNonSensitiveOverview() {
        for (PipelineProperties.Pipeline pipeline : config.pipelines()) {
            if (!pipeline.enabled()) {
                continue;
            }

            System.out.println("Pipeline: " + pipeline.name());
            System.out.println(
                "Retry count: " + pipeline.retry().maxAttempts());

            for (PipelineProperties.Destination dest
                    : pipeline.destinations()) {
                System.out.println(
                    " -> " + dest.id() + " at " + dest.url());
            }
        }
    }
}
~~~

The example above assumes `pipelines`, `retry`, and `destinations` were validly provided. In real applications, required settings should be validated at startup so consumers do not have to scatter null checks everywhere.

Advantage: the service does not need to know whether YAML uses `-`, index `[0]`, or which folder holds the config file. The service receives the **bound object tree** and works with Java accessors.

A service can consume only the slice it needs. For instance, to build an endpoint client, it only reads `Destination.url()` and `Destination.timeout()`, while retry logic uses `Retry.maxAttempts()` and `Retry.backoff()`.

## 5. YAML Syntax: Hyphens Create List Elements

In YAML, a sequence is normally written using `-`. Each `-` at that indentation level creates an element:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
    - name: invoices
      enabled: false
~~~

Here:

- `pipelines` is a sequence with two elements.
- The first element is a mapping containing `name` and `enabled`.
- The second element is another mapping containing the same two keys.
- The Spring Binder can map the sequence to `List<Pipeline>` based on the record type.

An object list differs from a scalar list:

~~~yaml
app:
  allowed-regions:
    - ap-southeast-1
    - eu-west-1
~~~

This list can bind into `List<String> allowedRegions`. Do not declare `List<Destination>` and supply plain strings if the Binder expects `id`, `url`, and `timeout` fields.

### Indentation Determines Parent-Child Relationships

Correct:

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
~~~

`retry` and `destinations` sit at the same level as `name`, so both are fields of element `pipelines[0]`.

Structurally wrong:

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        backoff: 250ms
        destinations:
          - id: primary
            url: https://orders.example.test/events
~~~

The snippet above places `destinations` **inside `retry`**, no longer a direct field of `Pipeline`. If `Retry` does not declare this field, data can be ignored or trigger an error depending on Binder configuration. Indentation mistakes are one of the most frequent reasons nested configuration binds with missing data.

### One Object Must Stay Under the Same `-`

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
    - name: invoices
      enabled: false
      retry:
        max-attempts: 1
        backoff: 1s
~~~

The two blocks following `-` denote two distinct objects—not one object with two `name`s. Fields belong strictly to the element they are indented under.

## 6. Writing the Same Structure in `application.properties`

When translating a YAML sequence to `.properties`, use **zero-based indices inside square brackets**:

~~~properties
app.pipelines[0].name=orders
app.pipelines[0].enabled=true
app.pipelines[0].retry.max-attempts=3
app.pipelines[0].retry.backoff=250ms

app.pipelines[0].destinations[0].id=primary
app.pipelines[0].destinations[0].url=https://orders.example.test/events
app.pipelines[0].destinations[0].timeout=2s
app.pipelines[0].destinations[0].headers.x-channel=retail
app.pipelines[0].destinations[0].headers.x-region=asia

app.pipelines[0].destinations[1].id=backup
app.pipelines[0].destinations[1].url=https://backup.example.test/orders
app.pipelines[0].destinations[1].timeout=5s
app.pipelines[0].destinations[1].headers.x-channel=fallback

app.pipelines[0].labels.owner=team-orders
app.pipelines[0].labels.tier=critical

app.pipelines[1].name=invoices
app.pipelines[1].enabled=false
app.pipelines[1].retry.max-attempts=1
app.pipelines[1].retry.backoff=1s
app.pipelines[1].destinations[0].id=billing
app.pipelines[1].destinations[0].url=https://billing.example.test/events
app.pipelines[1].destinations[0].timeout=3s
app.pipelines[1].destinations[0].headers.x-channel=finance
app.pipelines[1].labels.owner=team-finance
app.pipelines[1].labels.tier=standard
~~~

Typical keys can be read like paths from the root:

~~~text
app.pipelines[0].name
app.pipelines[0].retry.backoff
app.pipelines[0].destinations[1].url
app.pipelines[1].destinations[0].timeout
~~~

`[0]` in the middle of the key name marks **the first element of a list**. `[1]` is the second element. `.retry` or `.destinations` segments traverse further into objects nested inside the respective element.

### Do Not Confuse List Indices with Map Key Names

`pipelines[0]` is index-addressing syntax because `pipelines` has type `List<Pipeline>`. By contrast, `labels.owner` accesses a map with key `owner` (via map binding). For maps whose keys contain special characters or dots to preserve verbatim, Spring Boot provides dedicated bracket notation rules for maps, covered below.

## 7. Contiguous Indexing Rules and Element Ordering

When expressing a list in properties, declare elements `[0]`, `[1]`, `[2]` ... explicitly in order. In indexed property sources, the Binder must assemble entries by index to build the collection; **do not leave accidental index gaps** expecting the framework to guess how to fill them.

Readable example:

~~~properties
app.pipelines[0].name=orders
app.pipelines[1].name=invoices
app.pipelines[2].name=shipments
~~~

Hard-to-predict and hard-to-maintain example:

~~~properties
app.pipelines[0].name=orders
app.pipelines[5].name=invoices
~~~

Even if the config parses syntactically, you should not rely on sensible elements appearing automatically at `[1]`–`[4]`. Control element counts, required fields, and ordering explicitly.

**List order can carry business meaning.** If pipelines execute strictly in file order, state that clearly in configuration docs. If order is merely for listing without semantic weight, prefer identifier keys and treat them as a map where suitable.

For example: when `primary` and `backup` are tried in failover order, the `destinations` list expresses explicit priority order. When you only need lookup by `id` and order does not matter, `Map<String,Destination>` expresses intent better.

## 8. Multi-Level Lists: List Inside List

The pipeline structure above has:

~~~text
List<Pipeline>
  └── List<Destination>
~~~

The Spring Boot Binder handles even deeper nesting as long as the Java model and data align. For example, a rule-grouping configuration:

~~~yaml
app:
  rule-groups:
    - id: checkout
      rules:
        - code: require-address
          conditions:
            - field: shippingAddress
              operator: present
            - field: country
              operator: allowed
        - code: require-email
          conditions:
            - field: email
              operator: present

    - id: invoices
      rules:
        - code: valid-currency
          conditions:
            - field: currency
              operator: supported
~~~

Model:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RuleGroupProperties(
    List<RuleGroup> ruleGroups
) {
    public record RuleGroup(
        String id,
        List<Rule> rules
    ) {}

    public record Rule(
        String code,
        List<Condition> conditions
    ) {}

    public record Condition(
        String field,
        String operator
    ) {}
}
~~~

A specific path:

~~~text
app.rule-groups[0].rules[1].conditions[0].field
~~~

This path references:

1. First rule group: `rule-groups[0]`.
2. Second rule in that group: `rules[1]`.
3. First condition of that rule: `conditions[0]`.
4. The `field` property of that condition.

Same data in properties:

~~~properties
app.rule-groups[0].id=checkout
app.rule-groups[0].rules[0].code=require-address
app.rule-groups[0].rules[0].conditions[0].field=shippingAddress
app.rule-groups[0].rules[0].conditions[0].operator=present
app.rule-groups[0].rules[0].conditions[1].field=country
app.rule-groups[0].rules[0].conditions[1].operator=allowed
app.rule-groups[0].rules[1].code=require-email
app.rule-groups[0].rules[1].conditions[0].field=email
app.rule-groups[0].rules[1].conditions[0].operator=present

app.rule-groups[1].id=invoices
app.rule-groups[1].rules[0].code=valid-currency
app.rule-groups[1].rules[0].conditions[0].field=currency
app.rule-groups[1].rules[0].conditions[0].operator=supported
~~~

It is **the `List<RuleGroup>`, `List<Rule>`, `List<Condition>` types themselves** that tell the Binder how to build objects, sparing you from writing recursive parsers manually.

## 9. Maps Inside List Elements

A `Destination` element can carry a map of headers:

~~~yaml
app:
  pipelines:
    - name: orders
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
          headers:
            x-channel: retail
            x-region: asia
~~~

With record:

~~~java
public record Destination(
    String id,
    URI url,
    Duration timeout,
    Map<String, String> headers
) {}
~~~

The Binder creates the corresponding map containing `x-channel` and `x-region`. This is a **map inside an object, inside a list**.

### Maps with Keys Containing Dots or Special Characters

With `@ConfigurationProperties`, map keys can be normalized under binding rules unless explicit syntax is used. When you must preserve a map key containing dots or special characters, use bracket notation.

Example properties:

~~~properties
app.pipelines[0].labels.[deployment.zone]=asia
app.pipelines[0].labels.[/team]=orders
~~~

With `Map<String,String> labels`, bracket notation tells the Binder the bracketed segment is a map key to preserve under the matching rules. In YAML, quote bracketed keys:

~~~yaml
app:
  pipelines:
    - name: orders
      labels:
        "[deployment.zone]": asia
        "[/team]": orders
~~~

Normal keys like `owner` or `tier` do not require bracket notation.

**Note:** do not conclude from the dotted map key example above that list index syntax changes. `pipelines[0]` remains a list index, whereas `labels.[deployment.zone]` is a map key containing a dot.

## 10. Binding Objects with Diverse Data Types

A nested record can contain `String`, `URI`, `Duration`, `DataSize`, enums, numbers, and booleans, provided the Binder supports the conversions.

For example:

~~~yaml
app:
  workers:
    - name: thumbnail
      enabled: true
      max-payload: 8MB
      retry-delay: 200ms
      mode: ASYNC
    - name: cleanup
      enabled: false
      max-payload: 1MB
      retry-delay: 2s
      mode: SYNC
~~~

Java:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app")
public record WorkerCatalogProperties(
    List<Worker> workers
) {
    public enum Mode {
        SYNC, ASYNC
    }

    public record Worker(
        String name,
        boolean enabled,
        DataSize maxPayload,
        Duration retryDelay,
        Mode mode
    ) {}
}
~~~

| YAML value | Java type | Meaning |
| --- | --- | --- |
| `true` | `boolean` | Enable a worker |
| `8MB` | `DataSize` | Capacity size |
| `200ms` | `Duration` | Duration |
| `ASYNC` | `Mode` enum | Mode from defined set |
| `thumbnail` | `String` | Identifier name |

Do not declare every field as `String` just because data is read from a file. Strong types make intent clear to consumers, and invalid conversions are caught at startup.

If an enum is invalid, a URI is malformed, or a duration cannot be parsed, the Binder reports a type conversion error. That is a binding error, not a missing-file or `@ConfigurationPropertiesScan` error.

## 11. Constructor Binding with Nested Records

In Spring Boot 3.x, a record with an appropriate canonical constructor is naturally eligible for constructor binding. When the root record is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the Binder builds the record tree via constructors.

For example:

~~~java
@ConfigurationProperties(prefix = "app")
public record PipelineProperties(
    List<Pipeline> pipelines
) {
    public record Pipeline(
        String name,
        Retry retry
    ) {}

    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

Configuration:

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        backoff: 250ms
~~~

The Binder constructs `Retry(3, Duration.ofMillis(250))`, then `Pipeline("orders", retry)`, and finally `PipelineProperties(List.of(pipeline))` according to its binding rules.

**Do not** annotate nested records with `@Component`. They are not standalone components. Even putting `@Component` on the constructor-bound root record shifts bean creation toward Spring's dependency injection mechanism instead of the Binder's constructor binding.

### Is a Record Truly Deeply Immutable?

A record makes **field references** final, yet a `List` or `Map` inside can still be a mutable collection implementation. Never assume `record List<...>` is deeply immutable.

If consumers might mutate lists, design defensively: avoid mutating configuration collections directly, convert to immutable snapshots when required, or expose read-only operations only. Those are Java application design choices distinct from binding out of YAML.

## 12. Mutable JavaBeans for Nested List Configuration

Records are not mandatory. Legacy codebases or certain libraries expect JavaBeans with no-arg constructors and getters/setters.

Simple example:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class PipelineSettings {
    private List<Pipeline> pipelines = new ArrayList<>();

    public List<Pipeline> getPipelines() {
        return pipelines;
    }

    public void setPipelines(List<Pipeline> pipelines) {
        this.pipelines = pipelines;
    }

    public static class Pipeline {
        private String name;
        private boolean enabled;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
~~~

With:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
    - name: invoices
      enabled: false
~~~

The Binder constructs `Pipeline` JavaBeans and populates data via setters. Mutable beans used in setter binding follow constructor, getter, setter, and collection-initialization rules that must fit the actual model.

### Record vs. JavaBean?

| Requirement | Record / constructor binding | JavaBean / setter binding |
| --- | --- | --- |
| Want configuration with a clear immutability contract | Usually advantageous | Must restrict mutation manually |
| Want zero getter/setter boilerplate | Concise | More verbose |
| Compatibility with a library requiring setters | Not directly suitable | Typically suitable |
| Want defaults via field initializers | Not JavaBean-style | Possible |
| Multiple nested objects/lists | Supported | Supported |
| Bean created via `@Bean` then bound onto instance | Does not use constructor binding | Can bind via appropriate setters |

Both use `@ConfigurationProperties` to declare the prefix; they differ primarily in **how objects are constructed and populated**.

## 13. Validation for Elements and Nested Objects

With multi-level configuration, validation matters even more. If `destinations` or `url` is missing, business code can crash far past startup time. Spring Boot combines configuration properties binding with Jakarta Bean Validation.

For example:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record PipelineProperties(
    @NotEmpty List<@Valid Pipeline> pipelines
) {
    public record Pipeline(
        @NotBlank String name,
        boolean enabled,
        @NotNull @Valid Retry retry,
        @NotEmpty List<@Valid Destination> destinations,
        Map<String, String> labels
    ) {}

    public record Retry(
        @Min(0) int maxAttempts,
        @NotNull Duration backoff
    ) {}

    public record Destination(
        @NotBlank String id,
        @NotNull URI url,
        @NotNull Duration timeout,
        Map<String, String> headers
    ) {}
}
~~~

For validation to run in Spring Boot 3.x, projects need a proper validation provider and dependency, typically:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Role of each annotation:

- `@Validated`: triggers validation on the configuration properties bean using the configured validation mechanism.
- `@NotEmpty` on a list: requires the list to contain at least one element (if required by business rules).
- `@Valid`: cascades validation into child objects or collection elements when supported by the provider.
- `@NotBlank` on a string: rejects missing, empty, or whitespace-only strings.
- `@NotNull`: marks an object/value as required.
- `@Min(0)`: `max-attempts` must be non-negative.

When `app.pipelines[0].destinations[1].url` is missing, validation catches a deeply nested path error instead of letting the component fail only when sending real requests.

### Validating Values Inside a Map

To validate complex map values, use `Map<String, @Valid SomeConfig>` with matching constraints. For `Map<String,String>` headers, distinguish "the map is present" from "every key/value inside the map is valid". `@NotEmpty` on a map does not guarantee each header name satisfies HTTP standards.

Cross-field constraints, such as "an enabled pipeline must have destinations" or "backup timeout exceeds primary timeout", may require custom object-level validation. Place constraints where they accurately reflect domain rules.

### Adding `@Valid` Alone Is Not Enough

If the project lacks a Bean Validation provider, or the root bean is not registered via the proper mechanism, annotating fields alone does not guarantee all validation will execute. Verify dependencies, `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, and root annotations.

## 14. Empty Lists, Missing Keys, and Defaults

For collection binding, distinguish carefully among:

1. **List key not declared:** `app.pipelines` does not exist in any configuration source.
2. **Empty list declared:** YAML has `pipelines: []`.
3. **Element declared with missing fields:** `pipelines[0].name` exists, but `pipelines[0].destinations` is absent.
4. **Field declared with an empty value:** `name: ""` or `url: ""`.

These cases are not equivalent:

~~~yaml
# Case A: pipelines absent
app:
  service-name: order-service
~~~

~~~yaml
# Case B: empty pipelines
app:
  pipelines: []
~~~

~~~yaml
# Case C: element present but destinations missing
app:
  pipelines:
    - name: orders
      enabled: true
~~~

If a component requires at least one pipeline and each pipeline requires at least one destination, use `@NotEmpty` with `@Valid` as shown to fail appropriately.

With constructor-bound records, do not assume a list will automatically become `List.of()` when the key is missing. The model needs an explicit default if an absent key is meant to represent an empty collection. With mutable JavaBeans, you can initialize the list field and use setter binding according to supported rules.

### Defaults for a Nested Object

Spring Boot Binder supports `@DefaultValue` for constructor binding. For example, to provide default retry values:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record SimplePipelineProperties(
    @DefaultValue List<Pipeline> pipelines
) {
    public record Pipeline(
        String name,
        @DefaultValue Retry retry
    ) {}

    public record Retry(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("250ms") Duration backoff
    ) {}
}
~~~

Here, an empty `@DefaultValue` on a nested object tells the Binder to instantiate the nested object using its default values when conditions in the Boot version allow. For lists, verify the Binder's default semantics in your Spring Boot version before relying on a missing list being instantiated as a specific collection type; using validation or explicitly writing `pipelines: []` may be simpler.

**Do not use defaults to hide missing critical data.** If an enabled pipeline lacks a URL, a vague fallback can be riskier than failing fast at startup.

## 15. Critical Rule: Lists Are Replaced, Not Merged by Index

When the same list is declared across **multiple PropertySources or Config Data documents** with different precedence, the Spring Boot Configuration Properties Binder typically applies a **whole-list replacement rule from the higher-precedence source**, rather than automatically merging individual objects by index.

Example base file:

~~~yaml
# application.yml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
    - name: invoices
      enabled: true
      retry:
        max-attempts: 2
        backoff: 1s
      destinations:
        - id: billing
          url: https://billing.example.test/events
          timeout: 4s
~~~

Profile-specific `dev` file:

~~~yaml
# application-dev.yml
app:
  pipelines:
    - name: orders
      enabled: false
~~~

When `dev` is active and `application-dev.yml` is the winning source for the list, do not expect the final configuration to become:

~~~text
pipelines[0] = orders (enabled=false, retry inherited, destinations inherited)
pipelines[1] = invoices (fully inherited)
~~~

That would be **deep merge** reasoning; standard list binding **does not behave that way**. In this example, the higher-precedence profile source supplies a list with one `orders` element, so its nested values must be declared completely according to the contract (or have appropriate defaults). The `invoices` element from the lower-precedence list is not automatically re-added.

### Why Does This Matter So Much for Lists of Objects?

If production requires every endpoint to be well-defined, a profile override writing only:

~~~properties
app.pipelines[0].retry.max-attempts=5
~~~

should not be assumed to change only `max-attempts` on the first pipeline in a long list from the base file while **preserving all remaining fields and elements**. List precedence causes a different outcome: only the indices/fields present in the winning source may remain, triggering validation failures.

**Safe implementation patterns:**

- Define the complete list per profile or overriding source when using list configuration.
- Or, if you want to override individual items by identifier key, switch the model to a **map of objects**.
- Or reduce override scope by extracting values that vary per environment into separate scalar keys instead of patching deeply inside a list.

### Comparing List and Map Across Overlapping Sources

| Aspect | `List<Pipeline>` | `Map<String,Pipeline>` |
| --- | --- | --- |
| How elements are identified | Index 0, 1, 2... | Keys like `orders`, `invoices` |
| Element order | Can carry meaning | Should not rely on order as a default contract |
| Override from higher source | List is replaced per binder rules | Map supports key-level combination across sources |
| Adding/removing elements | Replace the corresponding list | Add/remove or update keys more clearly in config |
| Ideal use cases | Failover order, sequential steps | Registry of objects looked up by name |

For maps, merge and overwrite rules still depend on value types and source structure; do not treat maps as unconditional deep merge either. However, maps are usually more semantically accurate when identifiers matter and indices do not.

## 16. Switching from a List to a Map When Identifier-Based Overrides Are Needed

Alternative design example:

~~~yaml
app:
  pipeline-by-name:
    orders:
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
    invoices:
      enabled: false
      retry:
        max-attempts: 1
        backoff: 1s
~~~

Model:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record PipelineRegistryProperties(
    Map<String, PipelineEntry> pipelineByName
) {
    public record PipelineEntry(
        boolean enabled,
        Retry retry
    ) {}

    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

Access:

~~~java
PipelineRegistryProperties.PipelineEntry orders =
    registry.pipelineByName().get("orders");
~~~

The map model gives elements stable keys. If pipelines also need to be sorted in a specific order, add an explicit `order` field or a separate list of names rather than relying on map iteration order.

**Choose a list when order itself is core data; choose a map when identifiers and key lookup matter.** That is a domain modeling decision, not merely a Spring Boot syntax detail.

## 17. Profile-Specific Files and List Replacement

In Spring Boot, files such as `application-dev.yml` and `application-prod.yml` participate in Config Data when their profile is active. With scalar keys, developers are used to overriding one value and keeping all others from the base file. With **lists**, the example below illustrates an important distinction.

Base file:

~~~yaml
app:
  gateways:
    - id: north
      url: https://north.example.test
    - id: south
      url: https://south.example.test
~~~

`application-dev.yml`:

~~~yaml
app:
  gateways:
    - id: local
      url: http://localhost:8090
~~~

When running:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

The winning list value in normal setups contains only `local`. Do not expect three elements (`north`, `south`, `local`) or expect the first two items to remain with index `[0]` patched.

For lists of complex objects, this is a frequent cause of "works locally, missing nested fields in prod" if one profile overrides only a couple of keys without declaring the full list.

## 18. Command-Line Arguments and Environment Variables for Nested Lists

Indexed key names can supply data from sources outside configuration files.

Spring Boot command-line arguments:

~~~bash
java -jar order-service.jar \
  '--app.pipelines[0].name=orders' \
  '--app.pipelines[0].enabled=true' \
  '--app.pipelines[0].retry.max-attempts=3' \
  '--app.pipelines[0].retry.backoff=250ms'
~~~

In this example, single quotes protect the arguments from a Unix-like shell. When running in PowerShell or CMD, use appropriate quoting. On the command line with nested objects, ensure all required keys of the entire list are supplied due to list replacement rules.

Environment variables follow Spring Boot's naming rules:

~~~text
app.pipelines[0].name               -> APP_PIPELINES_0_NAME
app.pipelines[0].retry.max-attempts -> APP_PIPELINES_0_RETRY_MAXATTEMPTS
app.pipelines[1].enabled            -> APP_PIPELINES_1_ENABLED
~~~

For environment variables, Spring Boot typically converts dots to `_`, removes dashes from canonical names, converts to uppercase, and wraps list indices in underscores.

Example in a shell supporting inline environment variable assignments such as Bash:

~~~bash
APP_PIPELINES_0_NAME=orders \
APP_PIPELINES_0_ENABLED=true \
APP_PIPELINES_0_RETRY_MAXATTEMPTS=3 \
APP_PIPELINES_0_RETRY_BACKOFF=250ms \
java -jar order-service.jar
~~~

In Kubernetes or CI/CD, these variables can be declared in the runtime environment configuration. Avoid turning an entire multi-layered system into hundreds of environment variables with unclear contracts; for large lists, a mounted or imported YAML file is often much easier to maintain.

**Watch out for precedence:** if these environment variables define a list in a source with higher precedence than the config file, providing only a few indices or fields can drop the remaining items from the base file. Never override deep into a list unless you manage the complete structure in the winning source.

## 19. Should You Use `@Value` to Read `List<...>`?

`@Value` is handy for one or a few scalar values, such as:

~~~java
@Value("\${app.client.timeout:2s}")
private Duration timeout;
~~~

However, for `List<Pipeline>` where each element also has `Retry` and `List<Destination>`, trying to split strings with `@Value` is no longer suitable. That annotation is not a replacement for the Binder's support for nested collections, type conversion, and validation.

`Environment.getProperty("app.pipelines[0].name")` can return a single value, but manually assembling hundreds of key names and indices forces your code to track list lengths, handle nulls, convert types, and verify parent-child relationships on its own.

Example of an individual lookup:

~~~java
String first = environment.getProperty(
    "app.pipelines[0].name");
~~~

This can be useful for diagnostics, but you should not reconstruct an entire `PipelineProperties` tree by calling individual keys manually when the Binder already does the job.

**Prefer `@ConfigurationProperties` for nested object lists.** Use `Environment` or `@Value` only when you genuinely need a single key or simple scalar value.

## 20. Nested Configuration Across Multiple Imported Files

An application can place lists in files imported via `spring.config.import`:

~~~properties
# application.properties
spring.config.import=classpath:config/pipelines.yml
~~~

`src/main/resources/config/pipelines.yml`:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
~~~

Spring Boot brings Config Data imports into the `Environment` according to import mechanics, and the Binder can then bind `app.pipelines`. `@ConfigurationProperties` does not need to know whether the file is the base file, a profile-specific file, or an imported file.

If two sources both declare `app.pipelines`, you still need to consider **property source precedence and list replacement rules**. Importing an extra file does not automatically concatenate lists from two files.

### Note on External Files Outside the JAR

~~~properties
spring.config.import=optional:file:./config/pipelines-local.yml
~~~

This syntax ignores the location if the file does not exist. However, if the file does exist and contains a list with only one pipeline, it can replace the list from a lower-precedence source. This is precedence behavior, not an append feature.

If a configuration file is mandatory for production, do not use `optional:` where it could silently swallow a deployment mistake; configure explicit paths and validation.

## 21. Identifiers, Ordering, Duplicates, and the List Contract

The Binder understands **positional lists**. It does not automatically know that two objects sharing `name: orders` are invalid in your domain.

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
    - name: orders
      enabled: false
~~~

In YAML syntax, this simply has two elements. If `name` must be unique, add business validation or switch to a key-indexed map. `@NotBlank` only ensures each `name` has text, not that names are unique across elements.

Important design questions:

- Does the order of the list change runtime behavior?
- Are two objects allowed to share the same `name` or `id`?
- If `destinations` is empty, is the pipeline still valid?
- If `enabled=false` on a pipeline, is full configuration still required or may some sections be omitted?
- When one destination fails, does the system try the next destination in list order or follow a custom policy?
- Should profile-specific configurations repeat the entire list or only specific items?

`@ConfigurationProperties` is a data-mapping mechanism; it does not enforce these business rules on its own. For domain-specific constraints, writing an explicit validator catches errors early.

## 22. Testing Nested List Binding in Spring Boot

An integration test can prove that the Spring context registers the root properties bean and binds all nested lists properly.

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import com.example.orders.config.PipelineProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.pipelines[0].name=orders",
    "app.pipelines[0].enabled=true",
    "app.pipelines[0].retry.max-attempts=3",
    "app.pipelines[0].retry.backoff=250ms",
    "app.pipelines[0].destinations[0].id=primary",
    "app.pipelines[0].destinations[0].url=https://orders.example.test/events",
    "app.pipelines[0].destinations[0].timeout=2s",
    "app.pipelines[0].destinations[0].headers.x-channel=retail",
    "app.pipelines[0].labels.owner=team-orders"
})
class PipelinePropertiesTest {
    @Autowired
    PipelineProperties properties;

    @Test
    void nestedListAndObjectsAreBound() {
        assertThat(properties.pipelines()).hasSize(1);

        var pipeline = properties.pipelines().get(0);
        assertThat(pipeline.name()).isEqualTo("orders");
        assertThat(pipeline.retry().maxAttempts()).isEqualTo(3);
        assertThat(pipeline.retry().backoff())
            .isEqualTo(Duration.ofMillis(250));

        assertThat(pipeline.destinations()).hasSize(1);
        assertThat(pipeline.destinations().get(0).url().getHost())
            .isEqualTo("orders.example.test");
    }
}
~~~

This test assumes the application uses `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` to register `PipelineProperties` and includes `spring-boot-starter-test` in test dependencies. With Bean Validation enabled as in earlier examples, all required fields must be supplied according to their constraints.

### Pure Java Tests for Consumers

If you only want to test the logic of a service consuming typed configuration, instantiate the record tree directly in the test:

~~~java
var retry = new PipelineProperties.Retry(
    3, Duration.ofMillis(250));

var destination = new PipelineProperties.Destination(
    "primary",
    URI.create("https://orders.example.test/events"),
    Duration.ofSeconds(2),
    Map.of("x-channel", "retail")
);

var pipeline = new PipelineProperties.Pipeline(
    "orders",
    true,
    retry,
    List.of(destination),
    Map.of("owner", "team-orders")
);

var properties = new PipelineProperties(List.of(pipeline));
~~~

Unit tests like this verify consumer behavior without starting a Spring context, **but do not prove that the Binder parses YAML/indexed syntax correctly**. To verify actual binding, use a Spring context test.

## 23. Using `ApplicationContextRunner` for Focused Configuration Property Tests

When you do not want to boot the entire web application, use Spring Boot Test's `ApplicationContextRunner` to create a lightweight context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.orders.config.PipelineProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PipelineBindingRunnerTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class)
            .withPropertyValues(
                "app.pipelines[0].name=orders",
                "app.pipelines[0].enabled=true",
                "app.pipelines[0].retry.max-attempts=3",
                "app.pipelines[0].retry.backoff=250ms",
                "app.pipelines[0].destinations[0].id=primary",
                "app.pipelines[0].destinations[0].url=https://orders.example.test/events",
                "app.pipelines[0].destinations[0].timeout=2s"
            );

    @Test
    void bindsNestedList() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(PipelineProperties.class);
            var config = context.getBean(PipelineProperties.class);
            assertThat(config.pipelines()).hasSize(1);
            assertThat(config.pipelines().get(0).destinations())
                .hasSize(1);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PipelineProperties.class)
    static class TestConfig {}
}
~~~

If the minimal context does not enable the same auto-configurations or conversion services as the main application, select an appropriate test setup when testing specialized types. A full `@SpringBootTest` is often simpler for verifying complete Spring Boot binding, while `ApplicationContextRunner` isolates registration and property inputs.

## 24. Troubleshooting Errors in Nested Paths

### Error A: Root `@ConfigurationProperties` Bean Not Registered

~~~java
@ConfigurationProperties(prefix = "app")
public record PipelineProperties(List<Pipeline> pipelines) {}
~~~

If `PipelineProperties` falls outside `@ConfigurationPropertiesScan` and is not registered via `@EnableConfigurationProperties`, consumers fail with a missing bean error even though the YAML is valid.

**Fix:** verify package scanning, annotations, configuration classes, and bean registration. Do not add `@Component` to a constructor-bound record to "fix" a missing bean error.

### Error B: Wrong Prefix

~~~java
@ConfigurationProperties(prefix = "application")
~~~

While the file starts with `app:`. The Binder does not treat `application` and `app` as the same prefix. **Fix:** align the annotation prefix with the actual key name in the configuration source.

### Error C: Incorrect YAML Indentation

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        destinations:
          - id: primary
~~~

`destinations` is nested under `retry`. **Fix:** move it back to the same level as `retry` if the Java model defines `destinations` as a field on `Pipeline`.

### Error D: Confusing a Single Object with a List of Objects

~~~yaml
app:
  pipelines:
    name: orders
    enabled: true
~~~

Here `pipelines` is a single mapping, not a sequence. Yet Java expects `List<Pipeline>`. **Fix:** use `-` for list elements:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
~~~

### Error E: Missing Indices in Properties

~~~properties
app.pipelines.name=orders
app.pipelines.retry.max-attempts=3
~~~

This syntax fails to specify the list element. **Fix:** use `app.pipelines[0].name` and `app.pipelines[0].retry.max-attempts`.

### Error F: Type Mismatch in Data

~~~properties
app.pipelines[0].retry.max-attempts=many
app.pipelines[0].retry.backoff=tomorrow
~~~

Since Java expects `int` and `Duration`, the Binder throws a conversion failure. **Fix:** supply valid integers and duration units, such as `3` and `250ms`.

### Error G: Profile List Does Not Retain Base Configuration

`application.yml` has two pipelines, while `application-dev.yml` defines only part of `pipelines[0]`. When `dev` is active, the second pipeline disappears and nested fields may be missing.

**Fix:** recognize list replacement; declare the complete list in the winning source or switch to an identifier-keyed map.

### Error H: Missing Validation on Nested Elements

A `Destination.url` might be null if omitted, yet a consumer still calls `dest.url().getHost()`. **Fix:** add `@Valid` on the nested list and `@NotNull` on required fields, and ensure a validation provider is enabled.

### Error I: Expecting File Edits to Refresh the Object Automatically

A developer edits `application.yml` while the application is running, but the `PipelineProperties` record does not change. Config Data is normally loaded at startup and beans are bound during initialization.

**Fix:** distinguish startup configuration from dynamic configuration. If dynamic reload is required, design an explicit refresh/rebind mechanism; `@ConfigurationProperties` by itself is not a file watcher.

## 25. Layered Debugging Workflow

When nested list data differs from expectations, inspect in order:

1. **Which sources were actually loaded:** base file, profile-specific files, imports, environment variables, or command-line arguments?
2. **Prefix name:** does `app` on the annotation match the configuration?
3. **Structural shape:** do YAML sequences use `-`? Are `retry` and `destinations` at the right levels?
4. **Indices:** do properties have clear, contiguous `[0]`, `[1]`?
5. **Java types:** do `List<Pipeline>`, `List<Destination>`, and `Map<String,String>` match the intended structure?
6. **Root bean registration:** is `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` covering the right package?
7. **Constructors/setters:** are you using constructor-bound records or mutable JavaBeans consistently?
8. **Data conversion:** do `URI`, `Duration`, `enum`, and `int` convert cleanly?
9. **Validation:** are nested objects and lists validated as required?
10. **Precedence:** is a higher-precedence source replacing **the entire list**?
11. **Lifecycle timing:** is this startup config, or is someone expecting live file reloads?
12. **Evidence:** write an integration test binding a minimal list and expand it step by step.

If the application exposes appropriately secured Spring Boot Actuator endpoints, `configprops` and `env` can help inspect bound properties and source details. Never leave configuration endpoints open to the public or log full header/credential maps, as configuration maps can hold tokens, keys, or sensitive data.

## 26. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "An object list in YAML is just a comma-separated string." | A YAML sequence contains mappings; the Binder converts each into an element matching the Java type. |
| "`List<Pipeline>` only binds scalar fields, not nested objects." | The Binder can bind nested objects, lists, and maps when the model matches. |
| "Every nested record needs its own `@Component`." | Nested records are value objects of the root model, not standalone Spring beans. |
| "Just put `@Component` on the root record so Spring finds it." | For constructor-bound records, use dedicated configuration properties scanning/enabling rather than standard component construction. |
| "YAML lists must declare `[0]`, `[1]`." | YAML normally uses `-`; indices appear explicitly in flat properties. |
| "In properties, you can omit `[0]` when there is only one element." | Indexed list binding requires explicit index paths in this property representation. |
| "A profile setting one field in a list merges the rest from the base file." | Lists in Configuration Properties are normally replaced by the winning source, not deep-merged by index. |
| "Adding `@Valid` once makes every constraint run automatically." | You need a validation provider, root registration, and propagation into nested objects/lists. |
| "A record containing a `List` means the `List` is completely immutable." | The record keeps a final reference, but the underlying collection instance may still be mutable. |
| "Editing YAML while the program runs updates the bean automatically." | Config Data and binding normally happen at startup; dynamic refresh is a separate mechanism. |
| "`Map` behaves just like `List` and gets replaced wholesale." | `Map` has key-based binding semantics different from `List`; pick the structure matching your needs. |
| "`@Value` is the best way to parse all nested collections." | The `@ConfigurationProperties` Binder is much better suited for typed nested structures. |

## 27. Practice Exercises

### Exercise 1 — A List of Objects with a Nested Record

Given:

~~~yaml
app:
  connectors:
    - name: payment
      retry:
        attempts: 4
        delay: 200ms
    - name: search
      retry:
        attempts: 2
        delay: 1s
~~~

Create the model:

~~~java
@ConfigurationProperties(prefix = "app")
public record ConnectorProperties(List<Connector> connectors) {
    public record Connector(String name, Retry retry) {}
    public record Retry(int attempts, Duration delay) {}
}
~~~

**Question:** What is `connectors.get(1).retry().delay()`?

**Answer:** A `Duration` equal to `1s`, assuming the configuration loads and binds successfully.

### Exercise 2 — Converting YAML to Properties

Given:

~~~yaml
app:
  jobs:
    - name: daily
      triggers:
        - kind: cron
          expression: "0 0 2 * * *"
~~~

**Sample answer:**

~~~properties
app.jobs[0].name=daily
app.jobs[0].triggers[0].kind=cron
app.jobs[0].triggers[0].expression=0 0 2 * * *
~~~

Note that the cron expression here is merely an illustrative config string, not a guarantee that a scheduler has been registered.

### Exercise 3 — Finding the Indentation Bug

~~~yaml
app:
  jobs:
    - name: daily
      retry:
        attempts: 3
        triggers:
          - kind: cron
~~~

Java defines `Job(String name, Retry retry, List<Trigger> triggers)`.

**Answer:** `triggers` is currently nested inside `retry`; align it with `name` and `retry` under the `jobs[0]` element.

### Exercise 4 — Lists and Profile Overrides

`application.yml` has three `app.jobs` elements. `application-prod.yml` declares `app.jobs` with only one job.

**Question:** Will the Spring Boot Binder append the production job to the three base jobs?

**Answer:** No. The list from the winning source is used under replacement rules; you must declare the full desired list or change the data model.

### Exercise 5 — Map with a Key Containing a Dot

A `labels` map needs the exact key `deployment.zone`.

**Answer:** In flat properties, use:

~~~properties
app.pipelines[0].labels.[deployment.zone]=asia
~~~

In YAML:

~~~yaml
labels:
  "[deployment.zone]": asia
~~~

Bracket notation expresses the literal map key to preserve.

### Exercise 6 — Validating Lists of Objects

A pipeline must have at least one destination, and every destination must have a URL.

**Suggested answer:** place `@NotEmpty List<@Valid Destination> destinations` on the model and `@NotNull URI url` inside `Destination`, using `@Validated` on the root along with a validation provider.

### Exercise 7 — Environment Variable for an Index

Flat property:

~~~properties
app.pipelines[0].retry.max-attempts=3
~~~

**Answer for environment variable name per Spring Boot rules:**

~~~text
APP_PIPELINES_0_RETRY_MAXATTEMPTS
~~~

Do not keep dashes in the canonical converted environment variable name.

### Exercise 8 — Missing Bean Error

The root record has `@ConfigurationProperties(prefix="app")`, yet a service fails to inject `PipelineProperties`.

**Answer:** check `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` and package scope. Having data in YAML does not by itself register the bean.

### Exercise 9 — Empty List

Configuration has:

~~~yaml
app:
  pipelines: []
~~~

The root record has `@NotEmpty List<@Valid Pipeline> pipelines`.

**Answer:** when validation is properly active, `@NotEmpty` rejects an empty list. This is an intended business validation check, not a YAML syntax error.

### Exercise 10 — When to Choose a Map?

There are 500 connectors, each identified by a unique name, order does not matter, and different environments need to tweak settings by name.

**Suggested answer:** using `Map<String, Connector>` expresses the contract better than `List<Connector>` because keys are meaningful and key-based binding/overriding works much more naturally. If order is still required, represent ordering explicitly.

## 28. Quick Reference Summary

| Goal | Representation |
| --- | --- |
| List of objects in YAML | `- name: orders` under the list key |
| List of objects in properties | `app.pipelines[0].name=orders` |
| Nested list inside a list in properties | `app.pipelines[0].destinations[1].url=...` |
| Root model | `@ConfigurationProperties(prefix="app")` |
| List model | `List<Pipeline> pipelines` |
| Nested object model | `Retry retry` or `List<Destination> destinations` |
| Nested map model | `Map<String,String> headers` |
| Map key containing a dot | `labels.[deployment.zone]` |
| Binding duration types | `Duration timeout` with YAML `2s` |
| Registering the root bean | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Validating a mandatory non-empty list | `@NotEmpty` |
| Validating elements inside a list | `@Valid` on element/nested object |
| Validating required fields | `@NotBlank`, `@NotNull`, `@Min` as appropriate |
| Binding from indexed env vars | `APP_PIPELINES_0_NAME` |
| Overriding an entire list per profile | Redeclare the desired list in the winning source |
| Overriding by identifier name | Consider `Map<String,Pipeline>` |
| Testing binding | `@SpringBootTest` or a suitable Spring context test |

**Conclusion:** to bind nested lists of structured objects in Spring Boot, start from the **shape of the data**, use YAML sequences or `[index]` keys in properties, design matching `List<record>`/`List<class>` models, register the root `@ConfigurationProperties` bean properly, and validate at every critical layer. When multiple configuration sources declare the same list, remember that **lists are typically replaced rather than deep-merged element by element**. Choose `List` when order is essential, `Map` when entries are managed by identifier, and let the Binder construct your typed object tree instead of stitching individual keys together by hand.
