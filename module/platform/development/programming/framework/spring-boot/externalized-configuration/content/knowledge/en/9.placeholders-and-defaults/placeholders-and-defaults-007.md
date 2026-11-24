# Distinguishing Placeholders `${...}` from SpEL Expressions `#{...}` in Spring Boot

## Objective

In Spring Boot, the two syntaxes **${...}** and **#{...}** often appear close to each other in **@Value** annotations, configuration files, and dependency injection examples. They share the goal of supplying values to a component during application initialization, yet they solve **two different problems**:

- **Property placeholder — ${...}:** looks up a configuration key in the Spring Environment, optionally using a default value when the key cannot be resolved.
- **Spring Expression Language (SpEL) — #{...}:** evaluates an expression within a Spring context, such as arithmetic calculations, conditional selection, reading a bean's property, or invoking permitted methods.

Example:

~~~java
@Value("${server.port:8080}")
private int port;

@Value("#{10 * 2}")
private int doubleTen;
~~~

The first line asks **"What server.port configuration value does Spring currently have?"**. The second line asks **"What does the expression 10 * 2 evaluate to?"**. Without distinguishing these two questions, code can easily misuse SpEL to solve configuration problems, or mistakenly assume that SpEL strings in application.yml are always evaluated automatically by Spring Boot.

After this lesson, you will be able to accurately recognize both syntaxes, understand placeholder default values, know the processing order when combining the two mechanisms, and choose the right declaration approach when deploying applications.

## 1. Where Do the Two Syntaxes Differ?

| Criterion | Property placeholder ${...} | SpEL #{...} |
| --- | --- | --- |
| Primary purpose | Look up a configuration property | Evaluate an expression |
| Simple example | ${app.name:demo} | #{3 + 7} |
| Primary input | Spring Environment PropertySources | Spring expression evaluation context |
| How values are obtained | Searches for key **app.name** | Computes **3 + 7** |
| Default value | Typically uses **:**: ${app.name:demo} | Uses expression operators, e.g. **?:** |
| Result type | Property value, usually starting as a string, convertible on injection | Can be a number, boolean, String, object, collection, etc. |
| Accessing other beans | Not its primary purpose | Can use **@beanName** in supported contexts |
| Key characteristic | Follows configuration source precedence order | Can compute values, access data, and invoke methods |
| Recommendation | Use for environment configuration and values changeable at deploy time | Use when a genuine, simple, controlled expression is needed |

**Distinguish Spring syntax from Java syntax:** in Java code, **"${...}"** is the content of a string literal passed to an annotation; Java itself does not process placeholders. Spring performs resolution when creating beans. Likewise, **"#{...}"** is not Java math syntax: it is recognized and processed by Spring as an expression.

Not every location containing a ${...} or #{...} string automatically runs both mechanisms. They only carry special meaning at Spring integration points that support placeholder resolution or SpEL.

## 2. Property Placeholder ${...}: Looking Up Values in Environment

Suppose application.yml contains:

~~~yaml
app:
  display-name: "Inventory Service"
  worker:
    threads: 8
    enabled: true
~~~

In a bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerInfo {

    @Value("${app.display-name}")
    private String name;

    @Value("${app.worker.threads}")
    private int threads;

    @Value("${app.worker.enabled}")
    private boolean enabled;

    public String description() {
        return name + ": " + threads + " threads, enabled=" + enabled;
    }
}
~~~

Spring resolves the three placeholders from properties loaded into Environment. In the baseline example, they yield **Inventory Service**, **8**, and **true**, respectively. For the int and boolean fields, Spring also converts the configuration values to the target types.

**Field names do not determine which property name is looked up.** For instance, the Java field **threads** does not automatically imply key **app.worker.threads** inside `@Value`; the placeholder content itself specifies the key.

### 2.1. Values Can Come from Multiple Sources

Keeping application.yml as above, run:

~~~bash
APP_WORKER_THREADS=12 java -jar inventory.jar
~~~

If no higher-precedence configuration source exists, the environment variable **APP_WORKER_THREADS** can override the value **8** in the file. The placeholder **${app.worker.threads}** then resolves to **12**.

Next, run:

~~~bash
APP_WORKER_THREADS=12 java -Dapp.worker.threads=14 -jar inventory.jar   --app.worker.threads=16
~~~

In the usual PropertySource order among these sources, the command-line argument **--app.worker.threads=16** takes precedence over the JVM system property **14**, the environment variable **12**, and the YAML file **8**.

When writing:

~~~java
@Value("${app.worker.threads}")
private int threads;
~~~

Spring uses the configuration value resolved by precedence, rather than reading only one specific environment variable directly.

### 2.2. Looking Up with Environment

Code with an equivalent configuration-lookup goal:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigReader {
    private final Environment environment;

    ConfigReader(Environment environment) {
        this.environment = environment;
    }

    String name() {
        return environment.getProperty("app.display-name", "Unknown");
    }

    int threads() {
        return environment.getProperty("app.worker.threads", Integer.class, 4);
    }
}
~~~

In this case, **Environment.getProperty(...)** reads from PropertySources. It is not the same as evaluating an arbitrary SpEL expression. If a string looking like **#{1 + 2}** sits in a configuration source, the standard getProperty API does not automatically execute it as arithmetic.

## 3. Placeholder Default Values: The Colon

Common syntax:

~~~text
${property.name:default-value}
~~~

Example:

~~~java
@Value("${app.worker.threads:4}")
private int threads;

@Value("${app.display-name:Demo Service}")
private String displayName;

@Value("${app.feature.enabled:false}")
private boolean enabled;
~~~

If the application **cannot resolve** app.worker.threads from configuration sources, the placeholder uses the default string **4**, which Spring then converts to int for injection. Similarly, displayName defaults to **Demo Service**, and enabled defaults to **false**.

The colon belongs to property placeholder syntax; it does not mean Java's ternary operator.

### 3.1. Defaults Are Only a Fallback When No Value Is Found

Consider three scenarios:

~~~properties
# Case A: key does not exist

# Case B: key is present but empty
app.display-name=

# Case C: key has a concrete value
app.display-name=Order Service
~~~

Annotation:

~~~java
@Value("${app.display-name:Unnamed}")
private String displayName;
~~~

In typical scenarios:

| Scenario | Result |
| --- | --- |
| No app.display-name in sources | **Unnamed** |
| app.display-name present with empty string | **""** (empty string) |
| app.display-name=Order Service | **Order Service** |

This explains a common misconception: the default after **:** does not mean "replace any falsy value." An empty string **that was found** can still count as a valid value, depending on how the PropertySource provides data.

If business logic does not accept empty strings, express that requirement explicitly via validation or business logic rather than assuming the placeholder will replace it.

### 3.2. Empty Defaults

Example:

~~~java
@Value("${app.optional-label:}")
private String label;
~~~

Here the part after **:** is an empty string. If app.optional-label is absent, label can be **""**.

This is a reasonable choice for a genuinely optional string field. However, if the field is int:

~~~java
@Value("${app.worker.threads:}")
private int threads;
~~~

an empty default may fail conversion to primitive int. Use a valid number, a nullable/absent-capable type, or a configuration mechanism with proper validation.

### 3.3. Nested Placeholders

Spring supports placeholders referencing each other at supported resolution points:

~~~properties
app.base-url=https://api.example.test
app.health-url=${app.base-url}/health
~~~

After resolution, app.health-url can become **https://api.example.test/health**.

Another fallback pattern:

~~~java
@Value("${app.display-name:${spring.application.name:Demo}}")
private String displayName;
~~~

Idea:

1. Look up app.display-name.
2. If absent, look up spring.application.name.
3. If both are absent, use Demo.

Placeholders can become hard to read if nested too deeply. For complex configuration, put sensible defaults in files or `@ConfigurationProperties` classes and keep lookups simple.

### 3.4. Colons Inside Default Values

Example:

~~~java
@Value("${app.callback-url:https://example.test/callback}")
private String callbackUrl;
~~~

The default portion can be a URL containing **:**. The resolver identifies the default delimiter according to placeholder syntax rather than blindly splitting on every colon in the URL.

Still, for complex values with many special characters, pay attention to how Java, YAML, .properties, and the deployment shell handle quotes and escaping. Do not assume every context parses identically.

## 4. SpEL #{...}: Evaluating Expressions

**Spring Expression Language**, abbreviated **SpEL**, is an expression language provided by Spring to describe calculations, logic, property access, bean access, and other operations within a supported evaluation context.

Basic examples:

~~~java
@Value("#{4 + 6}")
private int ten;

@Value("#{'hello'.toUpperCase()}")
private String upperGreeting;

@Value("#{10 > 3}")
private boolean bigger;

@Value("#{T(java.lang.Math).max(7, 12)}")
private int maximum;
~~~

SpEL understands arithmetic syntax, String literals, comparisons, method calls, and **T(...)** type references. These expressions evaluate to **10**, **HELLO**, **true**, and **12**, respectively, when evaluated in a supported context.

Difference from placeholders: in **#{4 + 6}**, **4 + 6 is an expression to compute**, not a configuration property name. If you write **${4 + 6}**, Spring will try to treat the content as a placeholder name rather than switching to SpEL addition.

### 4.1. SpEL Arithmetic and Comparisons

~~~java
@Value("#{3 * (4 + 2)}")
private int capacity;

@Value("#{15 >= 10}")
private boolean acceptable;

@Value("#{('A' + 'B') == 'AB'}")
private boolean sameText;
~~~

Commonly used SpEL operators include: **+**, **-**, *****, **/**, **%**, **>**, **<**, **>=**, **<=**, **==**, **!=**, along with logical operators and compatible comparisons.

Operations must match value types. For example, a String containing the word **"five"** does not automatically become integer 5 just because it is placed in a multiplication.

### 4.2. Conditional SpEL

Ternary operator example:

~~~java
@Value("#{8 > 5 ? 'large' : 'small'}")
private String category;
~~~

Because 8 > 5, the result is **large**.

Elvis operator example in SpEL:

~~~java
@Value("#{'dev' ?: 'default'}")
private String profileLabel;
~~~

The **?:** operator selects the right-hand value when the left-hand side is null or empty as handled by SpEL's Elvis rules. This is an expression-level check, distinct from the colon in **${app.name:default}**.

Distinguish three syntaxes:

~~~text
${app.name:Guest}            // property placeholder default
#{flag ? 'yes' : 'no'}       // SpEL conditional operator
#{name ?: 'Guest'}           // SpEL Elvis operator
~~~

In the SpEL examples, **flag** and **name** must be objects/variables resolvable in the actual evaluation context. You cannot drop those two names into any `@Value` and assume they are already declared. These snippets illustrate operator syntax.

### 4.3. SpEL Accessing Java Properties and Beans

Suppose there is a bean:

~~~java
import org.springframework.stereotype.Component;

@Component("quotaSettings")
public class QuotaSettings {

    public int getDailyLimit() {
        return 100;
    }
}
~~~

Another bean can use:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class QuotaInfo {

    @Value("#{@quotaSettings.dailyLimit}")
    private int dailyLimit;
}
~~~

In SpEL, **@quotaSettings** represents a reference to the registered bean named quotaSettings; **dailyLimit** is read via the corresponding JavaBean property/getter in this case.

This is a SpEL feature that property placeholders are not designed to provide: **${quotaSettings.dailyLimit}** means look up a **configuration key**, not automatically invoke a getter on the quotaSettings bean.

Although SpEL bean access is flexible, arbitrary cross-references can make bean dependencies hard to manage, affect initialization order, and cause circular dependencies. If a class needs data from another bean, constructor injection expresses the relationship much more clearly.

### 4.4. SpEL Accessing System Properties

Example:

~~~java
@Value("#{systemProperties['java.version']}")
private String javaVersion;
~~~

In Spring's `@Value` evaluation context, **systemProperties** allows referencing Java system properties via Spring's built-in integration.

Do not confuse this with:

~~~java
@Value("${java.version}")
private String javaVersionFromEnvironment;
~~~

The second form looks up **java.version** as a property placeholder in the Spring Environment. Both examples may receive the same value in certain cases, yet their paths and semantics differ.

## 5. Direct Side-by-Side Comparison Example

Place three annotations side by side:

~~~java
@Value("${app.max-items:10}")
private int configuredLimit;

@Value("#{10 * 2}")
private int constantCalculation;

@Value("#{T(java.lang.Math).max(10, 20)}")
private int maximum;
~~~

Results:

| Annotation | What does Spring do? | Illustrative result |
| --- | --- | --- |
| ${app.max-items:10} | Look up app.max-items; use 10 if absent | Depends on config; 10 or overridden value |
| #{10 * 2} | Compute 10 times 2 | 20 |
| #{T(java.lang.Math).max(10, 20)} | Invoke Math.max in SpEL context | 20 |

Changing an environment variable like **APP_MAXITEMS=40** can change **configuredLimit**, but it does not alter the constant arithmetic **10 * 2** or the two arguments to Math.max in the other expressions.

Here are the criteria for choosing syntax:

- If operators need to change values across dev/test/prod without modifying code: **placeholder** or **@ConfigurationProperties**.
- If you need a small calculation, branch, or deliberate access to an object in the Spring context: **SpEL**.
- If logic is complex enough to need multiple steps, conditional checks, logging, or unit tests: put it in regular Java code instead of stuffing it into `@Value`.

## 6. Combining Placeholders and SpEL in the Same @Value

An important case is **resolving placeholders first, then evaluating the expression** at a Spring-managed `@Value` injection point.

Suppose:

~~~properties
app.batch-size=16
~~~

We want to compute double the capacity:

~~~java
@Value("#{${app.batch-size:8} * 2}")
private int bufferCapacity;
~~~

In this illustrative configuration:

1. The placeholder resolver looks up **app.batch-size**.
2. If **16** is found, the expression string after resolution corresponds to **#{16 * 2}**.
3. SpEL computes the multiplication.
4. The result **32** is injected into the int field.

If app.batch-size does not exist, the default **8** is used; the expression evaluates with 8, yielding **16**.

Key point: **${...}** resolves **configuration input**; **#{...}** resolves **the computational expression**. The two mechanisms do not become one simply because they sit in the same annotation string.

### 6.1. Conditional Combination Example

Suppose:

~~~properties
app.worker-count=6
~~~

Annotation:

~~~java
@Value("#{${app.worker-count:2} > 4 ? 'large' : 'small'}")
private String sizeLabel;
~~~

The configuration value **6** is substituted into the expression and compared with 4, yielding **large**. If the property is missing, the expression uses default 2 and receives **small**.

This is a good example for understanding processing order, though in long-lived business code it can be clearer to bind workerCount to an int field and write:

~~~java
String sizeLabel = workerCount > 4 ? "large" : "small";
~~~

This avoids turning an annotation into a container for business logic.

### 6.2. When the Value Read from a Property Is a String

With pure integers like 16, the pattern **#{${app.batch-size:8} * 2}** is fairly straightforward. With Strings, you cannot always substitute raw text directly into an expression without considering quotes and special characters.

For example, a configuration value containing spaces, single quotes, or characters meaningful in SpEL can cause syntax errors, alter meaning, or introduce risks if the data source is untrusted. Never construct SpEL by interpolating arbitrary user-supplied data directly into expression code.

When computations depend on customizable Strings, prefer reading the String via `@ConfigurationProperties` and handling it in Java. If an expression is genuinely necessary, control its data type and evaluation context.

### 6.3. When Combining Too Many Default Layers

An annotation can quickly become unreadable if it mixes nested placeholders, SpEL, and type conversions. Example of a hard-to-read form:

~~~text
#{ ... ${first:${second:10}} ... ? ... : ... }
~~~

In long-lived applications, it is better to separate:

1. Deciding configuration values and defaults in a configuration class.
2. Validating at startup.
3. Computing or branching per business rules in a Java method.

This keeps error messages clear about which configuration key is wrong and reduces reliance on expression syntax.

## 7. @Value vs. @ConfigurationProperties: Differences in Expression Handling

In Spring Boot, **@Value** fits injecting a few values, whereas **@ConfigurationProperties** is designed to bind structured groups of properties and supports relaxed binding, type conversion, and validation.

Example configuration group:

~~~yaml
app:
  worker:
    threads: 8
    queue-capacity: 120
    enabled: true
~~~

A configuration record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threads,
        int queueCapacity,
        boolean enabled
) {
}
~~~

Once registered, Spring Boot binds the keys into WorkerProperties without needing three `@Value` annotations.

**Crucial distinction:** **@ConfigurationProperties** binding does not use SpEL to automatically evaluate configuration strings like **#{1 + 2}**. Example:

~~~yaml
app:
  worker:
    threads: "#{4 + 4}"
~~~

This is a configuration string formatted like SpEL, yet the binder does not automatically evaluate it to 8 for assignment to int. The result may be a conversion error because the string is not a valid integer. Do not design `@ConfigurationProperties` configuration this way.

Conversely, `@Value` supports SpEL evaluation at the injection point:

~~~java
@Value("#{4 + 4}")
private int threads;
~~~

The result in this case is 8.

### 7.1. Defining Clear Defaults with ConfigurationProperties

One design approach is supplying defaults via the baseline file:

~~~yaml
app:
  worker:
    threads: 4
    queue-capacity: 100
    enabled: true
~~~

Environments can override via profile files or environment variables. If properties are required, apply validation during binding:

~~~java
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threads,
        @Min(1) int queueCapacity,
        boolean enabled
) {
}
~~~

Validation requires appropriate Jakarta Bean Validation dependencies and configuration. The idea here is to **separate configuration values from computational logic**, while catching invalid configuration early.

### 7.2. Canonical Names in @Value

When using `@Value` placeholders, write property names in canonical **lowercase kebab-case**, for example:

~~~java
@Value("${app.worker.queue-capacity:100}")
private int queueCapacity;
~~~

This helps Spring Boot's lookup mechanism match naming variants in sources such as the environment variable **APP_WORKER_QUEUECAPACITY**.

Writing:

~~~java
@Value("${app.worker.queueCapacity:100}")
private int queueCapacity;
~~~

can produce different lookup behavior across certain sources. Do not assume camelCase names in placeholders are completely equivalent to canonical kebab-case. In classes with many properties, `@ConfigurationProperties` reduces these naming risks.

## 8. In application.yml and application.properties: Which Syntax Is Processed?

A YAML file is a data source. Having strings with **${...}** or **#{...}** in YAML does not make the entire file immediately executable expression code.

Example:

~~~yaml
app:
  name: "Payment Service"
  banner: "Service: ${app.name}"
  arithmetic-text: "#{10 * 2}"
~~~

Layer-by-layer explanation:

- **app.name** is a normal string.
- **app.banner** contains a placeholder referencing another property; at points where Spring resolves placeholders, it can produce **Service: Payment Service**.
- **app.arithmetic-text** contains SpEL-shaped text. Spring Boot does not automatically evaluate every YAML scalar as an expression. If `@ConfigurationProperties` binds it to a String, this value can remain the literal string **#{10 * 2}**.

Meanwhile, if using `@Value`:

~~~java
@Value("${app.arithmetic-text}")
private int result;
~~~

the path can differ because `@Value` supports both placeholder resolution and expression evaluation; the string fetched from the property may be interpreted by the expression processor at the injection point. That does not turn **application.yml** into a global SpEL language, nor guarantee identical behavior across every configuration-reading API.

**Clean organization:** store **configuration data** in YAML/properties; write SpEL only at locations that support expressions and genuinely require evaluation.

### 8.1. The # Character in YAML

In YAML, **#** can start a comment when placed in an unquoted position. Therefore, a value containing **#{...}** should be explicitly quoted:

~~~yaml
app:
  expression-example: "#{10 * 2}"
~~~

Similarly, for scalars containing **:**, brackets, or special characters, use appropriate quotes so the YAML parser preserves the string accurately. However, YAML quotes only govern **YAML syntax**; they do not decide whether Spring evaluates SpEL.

### 8.2. Quotes in properties Differ from YAML

In YAML:

~~~yaml
app:
  label: "Hello"
~~~

the string-delimiting quotes are not part of the value.

In .properties:

~~~properties
app.label="Hello"
~~~

quotes are usually literal characters inside the value under Java properties syntax; they do not automatically mean the same as in YAML. Therefore, when writing placeholders or SpEL inside `.properties` values, be aware that quotes can become actual data and alter the expression.

A simpler, more common example:

~~~properties
app.label=Hello
app.banner=Service: ${app.label}
~~~

These values can undergo placeholder resolution when processed by Spring Environment in a supported context.

## 9. Differences Between Placeholders and SpEL When a Value Is Not Found

Suppose the configuration file **does not contain** app.retry-count.

With a placeholder without a default:

~~~java
@Value("${app.retry-count}")
private int retries;
~~~

In standard Spring Boot-managed `@Value` configuration, a missing property can cause bean initialization to fail with an error like **Could not resolve placeholder** or a nested error inside a bean creation exception. Do not assume Spring always injects null.

With a default:

~~~java
@Value("${app.retry-count:3}")
private int retries;
~~~

the value **3** can be used. If the property exists with value **abc**, conversion to int can fail; a default does not replace a value that was found but invalid.

SpEL handles things differently. Example:

~~~java
@Value("#{null}")
private String name;
~~~

SpEL evaluates the null literal and Spring handles the target value accordingly. This is **not** a "placeholder does not exist" case.

With a conditional operator:

~~~java
@Value("#{null ?: 'Guest'}")
private String name;
~~~

SpEL evaluates null, and then the Elvis operator selects **Guest**. No configuration key lookup occurs in this expression.

Comparison table:

| Case | Placeholder | SpEL |
| --- | --- | --- |
| Missing property | May error if no default exists | Not directly applicable unless the expression reads a property |
| Has default | ${app.name:Guest} | #{null ?: 'Guest'} |
| Wrong type on injection | May fail type conversion after lookup | May fail evaluation or result type conversion |
| Needs another bean | Not designed to access beans by property name | Can use `@name` bean references |
| References configuration key | Primary purpose | Must access Environment or combine with placeholder |

## 10. Cases Requiring Distinction Between Null, Empty, and Absent

Across configuration sources, **non-existent**, **empty string**, and **null** are not synonymous.

YAML example:

~~~yaml
app:
  label-empty: ""
  label-null: null
  label-literal: "null"
~~~

In YAML, **""** is an empty string; **null** is a null scalar; **"null"** is a four-character text string. When placed into Spring Environment, null handling depends on the data loader and `PropertySource` resolution mechanism.

With annotation:

~~~java
@Value("${app.label-empty:Fallback}")
private String label;
~~~

if the source contains an empty string, the **Fallback** default usually is not chosen merely because the string has length 0.

With SpEL Elvis:

~~~java
@Value("#{' ' ?: 'Fallback'}")
private String labelWithSpace;
~~~

A string containing only a space is not necessarily treated as an empty string; check SpEL Elvis rules and the specific value.

**Do not use YAML null as a reliable way to erase a value from a lower-precedence configuration source.** If you want to disable a feature, use an explicit meaningful property:

~~~yaml
app:
  notifications:
    enabled: false
~~~

For required values, use proper validation instead of misusing SpEL to patch undefined inputs.

## 11. SpEL Can Access Beans and Cause Side Effects

Unlike placeholders that only look up property names, SpEL can traverse objects and call methods if the evaluation context allows it.

Example:

~~~java
@Value("#{@quotaSettings.dailyLimit}")
private int limit;
~~~

If quotaSettings has a pure getter, reading the property is fairly predictable. However, if an expression calls a method that mutates state, queries a database, or invokes an external service, bean creation can cause hard-to-trace side effects.

In particular, never feed free-form strings from HTTP requests, user input, or untrusted configuration sources into SpEL and evaluate them as code. **SpEL is an executable expression language**, not a harmless string reader.

Some usage guidelines:

1. Keep expressions short and use trusted data sources.
2. Do not turn user-supplied configuration values into a new SpEL expression for evaluation.
3. If you need a bean reference, consider constructor injection instead of implicit dependencies via expression strings.
4. Avoid methods with side effects inside expressions used during configuration initialization.
5. For complex data, bind via `@ConfigurationProperties` and process in Java.

This is a difference in **capabilities and scope**, not a requirement to use SpEL whenever a dynamic value is needed.

## 12. When to Use SpEL vs. Computing in Java?

Suppose an application has the configuration:

~~~yaml
app:
  concurrency:
    workers: 6
    tasks-per-worker: 10
~~~

One annotation-based solution:

~~~java
@Value("#{${app.concurrency.workers:4} * ${app.concurrency.tasks-per-worker:8}}")
private int totalTaskCapacity;
~~~

Spring resolves both placeholders before SpEL computes the multiplication. With 6 and 10, the result is 60.

However, if totalTaskCapacity is important application logic, a more testable and debuggable solution is:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.concurrency")
public record ConcurrencyProperties(int workers, int tasksPerWorker) {

    public int totalTaskCapacity() {
        return workers * tasksPerWorker;
    }
}
~~~

Place defaults in application.yml or the corresponding configuration mechanism; add validation if both numbers must be positive.

The difference:

- With `@Value` SpEL, the formula lives inside an annotation string and runs during injection.
- With a record and a Java method, data is bound with clear types, and the formula can be unit tested like ordinary code.
- When calculations need conditions, bounds, rounding, error handling, or logging, Java is usually easier to maintain.

SpEL is useful for small expressions supported by a framework integration point. It does not replace writing clear application logic.

## 13. While the Application Is Running: Do Values Change Automatically?

Another misconception is that SpEL or placeholders make values **update continuously on their own**. For `@Value` fields injected at bean initialization, values are typically resolved when the bean is created.

Example:

~~~java
@Component
class RateLimitConfig {
    @Value("${app.max-per-minute:100}")
    private int maximum;
}
~~~

Once the application has started, if someone edits **APP_MAXPERMINUTE** in another shell, the running JVM does not automatically pick up the new variable. Even when a PropertySource updates, already-injected `@Value` fields are not automatically re-injected.

Similarly:

~~~java
@Value("#{10 * 2}")
private int fixedNumber;
~~~

Nothing here recalculates the expression every second. If hot-reloading configuration is required, the application must use a dedicated, controlled refresh/configuration mechanism and clearly define bean lifecycles.

**Distinguish two concepts:** "dynamic" in the sense of *determined at startup from the environment* does not mean "reactive" in the sense of *updated whenever the environment changes*.

## 14. Notes on Placeholders in Other Annotations

Spring has many integration points that use placeholders or SpEL. However, which syntax an annotation supports must be determined from the contract of that annotation and the framework using it.

Example:

~~~java
@Value("${app.name:Demo}")
private String name;
~~~

Spring's `@Value` mechanism supports both property placeholders and SpEL. You cannot extrapolate from that to assume an arbitrary annotation from another library will resolve **#{...}** or **${...}** the same way.

An annotation might:

- Read only literal Strings.
- Accept property placeholders but not support SpEL.
- Accept SpEL without full support for certain objects or bean references.
- Use a different expression context and evaluation timing.

Therefore, when encountering syntax in an unfamiliar annotation, check the documentation and implementation of that integration point. Do not use `@Value` as proof for every annotation across the Spring ecosystem.

## 15. Using SpEL in Contexts Other Than @Value

SpEL is a Spring technology reused across many components: certain conditions, filters, message processors, or data queries in extension modules may accept expressions in their own syntax.

For example, a system might support SpEL when defining rules, yet require the expression to be entered **without #{...}**, because that code calls the parser directly on the expression body. By contrast, **#{...}** in `@Value` is template syntax Spring uses to recognize an expression inside an annotation String.

Example using the SpEL parser in Java code:

~~~java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();
int result = parser.parseExpression("2 + 3").getValue(Integer.class);
~~~

`parseExpression` directly accepts **2 + 3**, not **#{2 + 3}**, because this is direct expression parsing mode. The **#{...}** template syntax is how expressions are embedded into a String in contexts supporting template resolution.

This is why you cannot take `@Value` syntax verbatim and assume all SpEL-enabled APIs require the same prefix.

## 16. Comparing Common Mistakes

### 16.1. Using ${...} to Compute Arithmetic

~~~java
@Value("${10 * 2}")
private int result;
~~~

**Problem:** Spring searches for a configuration key matching the placeholder contents; it is not instructed to evaluate SpEL multiplication.

**Correct way when arithmetic is needed:**

~~~java
@Value("#{10 * 2}")
private int result;
~~~

### 16.2. Using #{...} to Read a Property Without Context

~~~java
@Value("#{app.timeout}")
private String timeout;
~~~

**Problem:** app.timeout in SpEL does not automatically mean "look up property app.timeout in Environment." Unless the evaluation context has a matching variable/object, the expression may fail to resolve.

**Way to read configuration:**

~~~java
@Value("${app.timeout:5s}")
private String timeout;
~~~

### 16.3. Writing SpEL in YAML Expecting @ConfigurationProperties to Compute It

~~~yaml
app:
  worker:
    threads: "#{2 * 4}"
~~~

**Problem:** YAML does not automatically turn this String into the number 8; the `@ConfigurationProperties` binder does not evaluate every String as SpEL.

**Resolution:** write a concrete number or compute in Java from bound numeric properties.

### 16.4. Using Defaults to Fix Invalid Data

~~~java
@Value("${app.worker.threads:4}")
private int threads;
~~~

If a source has **app.worker.threads=invalid**, the placeholder found the value invalid. It does not automatically choose default 4 just because int conversion fails. **Resolution:** fix the data or use validation with clear configuration error messages.

### 16.5. Confusing the Meaning of `:`

~~~text
${app.name:Guest}
#{condition ? 'A' : 'B'}
#{name ?: 'Guest'}
~~~

These colons have different meanings: placeholder default; else branch of the ternary operator; SpEL Elvis operator. Do not read them as a single grammar.

### 16.6. Unquoted String Interpolation When Mixing with SpEL

A fragile example:

~~~java
@Value("#{'${app.name:Demo}' == 'Demo'}")
private boolean isDemo;
~~~

With simple values, this illustrative snippet may work. But if app.name contains a single quote or special characters, the resulting SpEL structure after placeholder substitution can break. **Do not inject arbitrary data into SpEL code**; read properties via typed configuration and compare in Java.

### 16.7. Using SpEL Instead of Constructor Injection

~~~java
@Value("#{@someService.someValue}")
private String value;
~~~

If the class genuinely depends on someService, injecting a bean directly via constructor makes dependencies and lifecycle clearer. `@Value` with bean references fits very simple cases, while broader logic belongs in classes/methods.

### 16.8. Forgetting Escaping in Enclosing String Languages

In Java source code, **$**, **#**, **{**, and **}** sit inside annotation String literals as shown above. However, in shells, template engines, build scripts, or CI systems using variable interpolation, **${...}** strings may be processed by another layer before reaching Spring.

When configuration flows through multiple layers such as CI → Docker Compose → container → Spring, check **which layer interpolates first**. For instance, Docker Compose has its own variable mechanism using dollar signs; its syntax does not automatically share the same meaning as Spring Boot placeholders.

Do not apply one universal escaping style to every context; each parser layer has its own rules.

## 17. Diagnosing Final Values and Bean Creation Errors

When a `@Value` annotation does not receive the expected result, inspect layer by layer.

**Layer 1 — configuration source:** does the key exist in files, environment variables, JVM system properties, or CLI?

**Layer 2 — naming and precedence:** is the placeholder name canonical? Did a higher-precedence source override it?

**Layer 3 — placeholder resolution:** is the property missing without a default? Does the default use a proper colon?

**Layer 4 — SpEL evaluation:** if using #{...}, is the expression valid, do the variables/beans exist, and are value types compatible?

**Layer 5 — conversion and injection:** can the final value convert to the field/constructor parameter type?

Diagnostic table:

| Symptom | Cause to check | Investigation step |
| --- | --- | --- |
| “Could not resolve placeholder” | Key not found, misspelled, or missing default | Check property key and configuration sources |
| SpEL parse exception | Invalid expression syntax or interpolated string broke expression | Inspect post-resolution expression; avoid arbitrary data |
| SpEL evaluation exception | Bean, property, or method missing or inaccessible | Check evaluation context and actual beans |
| Type conversion failed | String/SpEL result incompatible with target type | Compare Java type against data |
| BeanCreationException | Underlying error during bean creation | Read root cause, related property, and expression |
| Unexpected value though bean starts | PropertySource precedence or default value | Read Environment.getProperty(...) and active sources |

### 17.1. A SpEL-Independent Verification Snippet

You can inspect final configuration values via Environment:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class ConfigurationProbe {

    @Bean
    ApplicationRunner showConfig(Environment environment) {
        return args -> {
            System.out.println("app.worker.threads = "
                    + environment.getProperty("app.worker.threads"));
            System.out.println("app.display-name = "
                    + environment.getProperty("app.display-name"));
        };
    }
}
~~~

Environment output shows whether properties are present and what values resolve under precedence. It does not reveal the full SpEL evaluation process inside `@Value`, yet it is a good first step to separate configuration errors from expression errors.

### 17.2. Inspect Only Non-Sensitive Keys

If values are passwords, API tokens, or connection credentials, do not print values to stdout or logs. You can log key names, source presence, and the selected PropertySource name in appropriate environments. Debugging SpEL calls for extra care because expressions can access beans or system properties.

Spring Boot Actuator, when deployed and secured, can provide environment details. Endpoints and value visibility levels must be configured per security policy; never open public endpoints just to inspect a placeholder.

## 18. Practice Exercises on Distinguishing Syntax

### Exercise 1 — Lookup or Computation?

Classify the annotations:

~~~java
@Value("${spring.application.name:Demo}")
private String a;

@Value("#{2 + 3}")
private int b;

@Value("${app.retry-count:5}")
private int c;

@Value("#{T(java.lang.Math).max(3, 9)}")
private int d;
~~~

Answers:

- a and c use **property placeholders**; their values can change based on Environment.
- b and d use **SpEL**; the constant expressions evaluate to 5 and 9.

### Exercise 2 — Placeholder Default Value

The file lacks app.greeting. Annotation:

~~~java
@Value("${app.greeting:Hello}")
private String greeting;
~~~

The expected result is **Hello**. If the file declares:

~~~properties
app.greeting=
~~~

then distinguish **a declared empty string** from **a non-existent key**. Do not conclude you will always receive Hello.

### Exercise 3 — Numeric Configuration and Expressions

File:

~~~properties
app.factor=7
~~~

Annotation:

~~~java
@Value("#{${app.factor:3} * 4}")
private int score;
~~~

Expected result is **28** in a `@Value` context supporting placeholders and SpEL with no other overrides. Removing app.factor uses default 3, yielding **12**.

Add environment variable **APP_FACTOR=9** and observe the value. In standard PropertySource order, if no higher override exists, the result can become **36**.

### Exercise 4 — SpEL Accessing a Bean

Given bean:

~~~java
@Component("priceRules")
class PriceRules {
    public int getDefaultDiscount() {
        return 5;
    }
}
~~~

Usage:

~~~java
@Value("#{@priceRules.defaultDiscount}")
private int discount;
~~~

SpEL accesses bean priceRules and property defaultDiscount. Explain why changing to **${priceRules.defaultDiscount}** does not have the same meaning: a placeholder searches for a key in Environment rather than invoking a bean getter.

### Exercise 5 — Wrong Syntax When Reading a Property

Someone writes:

~~~java
@Value("#{app.worker.threads:4}")
private int threads;
~~~

They want to look up property app.worker.threads with default 4. The intended correct syntax is:

~~~java
@Value("${app.worker.threads:4}")
private int threads;
~~~

**#{...}** is not a substitute for property placeholders. If SpEL logic is desired, clearly identify the context and the variables/beans the expression is permitted to access.

### Exercise 6 — Binding Properties to a Record

Configuration:

~~~yaml
app:
  worker:
    threads: 8
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int threads) {}
~~~

Predict what happens if YAML is edited to:

~~~yaml
app:
  worker:
    threads: "#{4 * 2}"
~~~

Do not predict that the binder will compute 8. This is a String with SpEL syntax, not a valid integer for standard binding. The right approach is keeping **threads: 8** or computing from strongly typed numeric properties in Java.

## 19. Rules for Choosing a Solution

For practical needs, use this decision table:

| Need | Suitable approach | Example |
| --- | --- | --- |
| Read URL, port, timeout from config | Property placeholder or `@ConfigurationProperties` | ${app.api-url} |
| Provide default when key is absent | Placeholder with `:` | ${app.enabled:false} |
| Compute small arithmetic at `@Value` | SpEL | #{2 * 5} |
| Read a bean property by name in expression | SpEL when genuinely needed | #{ @beanName.property } |
| Configure nested groups across environments | `@ConfigurationProperties` | app.worker.threads |
| Enforce configuration constraints | `@ConfigurationProperties` + validation | @Min, @NotBlank |
| Long decision logic needing unit tests | Java method/service | capacity = threads * tasks |
| Update configuration while running | Dedicated refresh mechanism | Do not rely on fixed `@Value` |

Placeholder syntax is easy to read because it directly expresses a configuration key. SpEL can do more, yet greater power requires tighter control over complexity and data sources.

## 20. Key Takeaways

- **${...}** is a **property placeholder**: looks up a property name in Spring Environment; can specify a default with **:**, e.g., **${app.name:Demo}**.
- **#{...}** is **SpEL**: evaluates an expression in a Spring context, e.g., **#{10 * 2}**, **#{T(java.lang.Math).max(2, 5)}**, or accessing a compatible bean.
- **${app.timeout:5s}** computes nothing; it selects a configuration value. **#{10 * 2}** looks up no configuration key; it performs arithmetic.
- At **@Value** integration points, both mechanisms can combine: resolve placeholders first, then evaluate SpEL, e.g., **#{${app.factor:2} * 3}**. Avoid interpolating untrusted strings into SpEL code.
- The placeholder **:**, SpEL Elvis **?:**, and SpEL ternary **? ... : ...** have distinct meanings.
- **@ConfigurationProperties** is designed to bind and validate structured configuration values; it **does not automatically evaluate SpEL** in arbitrary YAML or properties strings.
- **Environment.getProperty** helps verify configuration lookups; SpEL evaluation depends on Spring-supported evaluation contexts.
- Values injected via `@Value` are usually fixed at bean initialization; subsequent environment variable changes do not automatically refresh injected fields.

When reading an annotation or configuration file, ask the first question: **"Is this snippet looking up a property, or asking Spring to evaluate an expression?"**. From there, choose placeholders, SpEL, or regular Java according to their proper responsibilities, keeping configuration testable and applications maintainable.