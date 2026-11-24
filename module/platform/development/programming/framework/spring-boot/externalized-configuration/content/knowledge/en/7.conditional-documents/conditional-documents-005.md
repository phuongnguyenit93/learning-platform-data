# Profile Expressions with !, & and | Operators

## 1. Why do we need profile expressions?

In a Spring Boot application, some configurations should only take effect when **multiple environmental conditions are true at the same time**. For example:

- Enable mock connections only when running in `dev` and **not** running in `cloud`.
- Enable extra monitoring configuration when running in `staging` **or** `prod`.
- Load infrastructure parameters only when the application is both in `prod` **and** has the `cloud` profile.
- Load a set of non-production parameters everywhere **except** `prod`.

If you use a single profile name for each combination, the list of names quickly becomes hard to manage: `dev-local`, `dev-cloud`, `staging-cloud`, `prod-cloud`, etc. Spring supports **profile expressions**, allowing you to combine independent profile names with logical operators.

The three important operators:

| Operator | Meaning | Example | When is it true? |
| --- | --- | --- | --- |
| `!` | Negation (NOT) | `!prod` | Profile `prod` is not active |
| `&` | Conjunction (AND) | `prod & cloud` | Both `prod` and `cloud` are active |
| `|` | Disjunction (OR) | `dev | staging` | At least one of `dev` or `staging` is active |

Parentheses `( )` help group conditions:

```text
(prod | staging) & cloud

           AND
          /   \
         OR   cloud
        /  \
      prod staging
```

This expression is true only when `cloud` **and** at least one of `prod` or `staging` are active. In other words, having `cloud` alone is not enough; having `prod` alone is not enough either.

In the "Conditional Documents" knowledge group, profile expressions are especially useful with `spring.config.activate.on-profile`: **Spring Boot uses the expression result to decide which configuration documents are loaded**.

## 2. What is an active profile?

A profile is a conditional name selected by the application or deployment platform. A Spring application can have **multiple active profiles simultaneously**.

For example:

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

In this startup run, the active profile set contains two names: `prod` and `cloud`. With that set:

```text
prod               -> true
cloud              -> true
staging            -> false
!staging           -> true
prod & cloud       -> true
prod | staging     -> true
staging & cloud    -> false
```

Clearly distinguish **profile names** from **profile expressions**:

- `prod` is an independent profile name.
- `prod & cloud` is an expression to be evaluated against the **active profile set**.
- `spring.profiles.active=prod,cloud` is a list of profiles to activate; the comma here separates **names**.
- `spring.config.activate.on-profile: "prod & cloud"` is a condition to activate **a configuration document**; the `&` here is an AND operation.

Do not use the string `prod & cloud` as an environment name expecting Spring to interpret it as two activated profiles. Logical conditions belong where expressions are declared; the active profile set is chosen via the profile activation mechanism.

When no active profile is set, Spring still has the concept of **default profiles** (usually `default`). Therefore, the `!prod` expression can evaluate to true on a run with no active profiles specified. The `!` operator checks for **the absence of the negated profile name**; it does not mean "running in the dev environment".

## 3. The ! operator: negation condition

Simplest syntax:

```text
!prod
```

Meaning: the condition is true when the `prod` profile is not active.

| Active profiles | `!prod` |
| --- | --- |
| No profile declared | True |
| `dev` | True |
| `staging` | True |
| `prod` | False |
| `prod,cloud` | False |
| `dev,cloud` | True |

Example in a conditional YAML document:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"

feature:
  diagnostic-banner: true
```

This document participates only when the `!prod` condition is true. Because `!prod` is also true in `staging` or when no profile is active, it **cannot directly substitute for the `dev` condition** if the goal is to enable something only for development.

A stricter way to express "dev, but not cloud" is:

```yaml
spring:
  config:
    activate:
      on-profile: "dev & !cloud"
```

**Note on quotes in YAML:** A `!` character at the start of an unquoted value can be interpreted by YAML as a tag declaration. For clarity and to avoid parsing errors, write profile expressions as strings inside single or double quotes, especially when `!`, `&`, and `|` are present.

### Negating a group

Compare:

```text
!(prod | staging)
!prod & !staging
```

Both expressions are true when **neither `prod` nor `staging` is active**. The parentheses in the first expression negate the entire OR operation, not just the name `prod`.

By contrast:

```text
!prod | staging
```

means "not prod **or** staging is present". That expression is still true when both `prod` and `staging` are active simultaneously. It does not mean "not both prod and staging". To avoid confusion, state the requirement in plain words first, then write the logic.

## 4. The & operator: requiring multiple conditions simultaneously

Syntax:

```text
prod & cloud
```

The condition is true only when **both profile names** are active.

| Active profiles | `prod & cloud` |
| --- | --- |
| `prod` | False |
| `cloud` | False |
| `prod,cloud` | **True** |
| `prod,staging` | False |
| `prod,staging,cloud` | **True** |

Example loading a document only when production runs on a cloud environment:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"

storage:
  use-managed-service: true
```

Here, `prod` indicates the deployment stage, while `cloud` indicates the infrastructure type. Both conditions must be true together.

The AND operator can combine with negation:

```text
dev & !cloud
```

The condition is true only when `dev` is active and `cloud` is not active. It fits configurations intended for local development on a personal machine that should not be used when running dev on cloud infrastructure.

With three conditions, you can write:

```text
prod & cloud & metrics
```

The condition is true when all three profiles are active. Use profile names that reflect clear contexts; do not turn a profile into a flag for every independent option if a dedicated configuration property expresses the requirement better.

## 5. The | operator: accepting at least one condition

Syntax:

```text
prod | staging
```

The condition is true when **at least one** of the two profiles is active.

| Active profiles | `prod | staging` |
| --- | --- |
| `dev` | False |
| `prod` | **True** |
| `staging` | **True** |
| `prod,staging` | **True** |
| `prod,cloud` | **True** |

The `|` operator is an **inclusive OR**: when both `prod` and `staging` are active, the expression is still true. It does not mean "only one of the two".

Example configuration allowed to load in two production-like environments:

```yaml
spring:
  config:
    activate:
      on-profile: "prod | staging"

observability:
  enhanced-tracing: true
```

This configuration does not require both profiles to be active. Requiring just one of the two is enough for the document to participate.

You can also combine more than two choices:

```text
dev | test | staging
```

When at least one of the three names is active, the whole expression is true.

### Do not confuse OR with a list in @Profile

In Java, `@Profile({"prod", "staging"})` on a bean also allows the bean to be active if **at least one** name matches. For complex conditions, it is more readable to use **a single expression** such as `@Profile("prod | staging")`. For AND, use `@Profile("prod & cloud")`; do not pass a two-string array expecting AND semantics.

## 6. Combining !, & and | with parentheses

Expressions often contain more than one logical operation. Example:

```text
(prod | staging) & cloud
```

Evaluate from inside the parentheses outward:

1. `prod | staging` is true if `prod` or `staging` is active.
2. `cloud` is true if `cloud` is active.
3. Combine both results with `&`: both must be true.

Illustrative truth table:

| Active profiles | `prod | staging` | `cloud` | `(prod | staging) & cloud` |
| --- | --- | --- | --- |
| `prod` | True | False | False |
| `staging` | True | False | False |
| `cloud` | False | True | False |
| `prod,cloud` | True | True | **True** |
| `staging,cloud` | True | True | **True** |
| `dev,cloud` | False | True | False |
| `prod,staging,cloud` | True | True | **True** |

Compare these two expressions:

```text
(prod | staging) & cloud
prod | (staging & cloud)
```

With active profiles containing only `prod`:

- The first expression is **false**: `cloud` is missing.
- The second expression is **true**: `prod` alone is sufficient.

Parentheses determine the business meaning of the condition. This is not merely a formatting detail.

### Important rule: do not mix & and | without parentheses

Spring uses Spring Framework's profile expression syntax. When an expression contains both `&` and `|`, **parentheses must be used to clarify the structure**. Do not write:

```text
prod & cloud | staging
```

Mixing both operators at the same level without explicit grouping is invalid under the profile expression parser's rules. Choose one intended meaning:

```text
(prod & cloud) | staging
```

or:

```text
prod & (cloud | staging)
```

The two forms are not equivalent; your choice must come from actual requirements.

For negating an entire group:

```text
!(prod & cloud)
```

the condition is false only when **both `prod` and `cloud` are active**. In all other cases, it is true. Placing `!` outside parentheses is completely different from `!prod & cloud`.

## 7. spring.config.activate.on-profile: conditional YAML documents

Spring Boot can organize multiple configuration documents inside **one YAML file** using `---`. Each document can contain a condition:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
```

When the expression is true, that document joins the loaded configuration set; when false, properties specific to that document are not included as an effective configuration source.

Example:

```yaml
# application.yml — shared document
service:
  timeout: 5s
  endpoint: https://example.invalid/default

---
# Document for dev not running on cloud
spring:
  config:
    activate:
      on-profile: "dev & !cloud"

service:
  timeout: 15s
  endpoint: http://localhost:9000/mock

---
# Document for staging or production on cloud
spring:
  config:
    activate:
      on-profile: "(staging | prod) & cloud"

service:
  timeout: 2s
  endpoint: https://example.invalid/managed
```

The `example.invalid` addresses are purely illustrative data, not reachable endpoints.

Expected results when no higher-precedence source exists:

| Active profiles | Matching documents | `service.timeout` |
| --- | --- | --- |
| No explicit active profile | Shared document | `5s` |
| `dev` | Shared + `dev & !cloud` | `15s` |
| `dev,cloud` | Shared document only | `5s` |
| `staging` | Shared document only | `5s` |
| `staging,cloud` | Shared + `(staging | prod) & cloud` | `2s` |
| `prod,cloud` | Shared + `(staging | prod) & cloud` | `2s` |

Note: if you pass `--service.timeout=20s` at startup, the command-line source can override even the profile-conditional document. **Document loading conditions** and **precedence order between sources** are two separate mechanisms.

### Conditional configuration only adds the keys it declares

If the shared document has:

```yaml
service:
  timeout: 5s
  retries: 3
```

and the conditional document only overrides:

```yaml
spring:
  config:
    activate:
      on-profile: "prod"

service:
  timeout: 2s
```

then when `prod` is active, `timeout` receives `2s` while `retries` can still take the value `3` from the shared document. There is no default rule that activating a document wipes out all remaining properties under the `service` branch in the previous document.

For structures like lists or complex configurations, binding rules can differ from individual scalar keys; the example above intentionally uses simple values to focus on profile expressions.

## 8. Complete hands-on: four conditions in one application.yml

We will build a very small Spring Boot program to verify `!`, `&`, and `|` operators with Boolean outputs, rather than guessing from logs.

Minimal structure:

```text
src/main/
├── java/com/example/profileexpr/
│   └── ProfileExpressionApplication.java
└── resources/
    └── application.yml
```

In `src/main/resources/application.yml`, write one shared document along with four conditional documents:

```yaml
# Shared document: default values for all conditions
lab:
  flags:
    dev-local: false
    release-like: false
    managed-release: false
    not-prod: false

---
# Only dev without cloud
spring:
  config:
    activate:
      on-profile: "dev & !cloud"

lab:
  flags:
    dev-local: true

---
# Staging or prod
spring:
  config:
    activate:
      on-profile: "staging | prod"

lab:
  flags:
    release-like: true

---
# Cloud and (staging or prod)
spring:
  config:
    activate:
      on-profile: "(staging | prod) & cloud"

lab:
  flags:
    managed-release: true

---
# Any case without prod
spring:
  config:
    activate:
      on-profile: "!prod"

lab:
  flags:
    not-prod: true
```

Each document overrides only one test key; this avoids having to reason about the order of two documents declaring the same key. Each flag's result directly reflects whether its conditional document was activated.

Create `ProfileExpressionApplication.java`:

```java
package com.example.profileexpr;

import java.util.Arrays;
import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ProfileExpressionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileExpressionApplication.class, args);
    }

    @Bean
    ApplicationRunner showFlags(Environment environment) {
        return args -> {
            System.out.println("=== PROFILE EXPRESSION LAB ===");
            System.out.println("Active profiles: " +
                Arrays.toString(environment.getActiveProfiles()));

            for (String key : List.of(
                    "dev-local",
                    "release-like",
                    "managed-release",
                    "not-prod")) {
                System.out.println(key + " = " +
                    environment.getProperty("lab.flags." + key));
            }
        };
    }
}
```

`Environment.getActiveProfiles()` displays the explicitly activated profiles. The `lab.flags.*` values indicate which conditional YAML documents contributed configuration.

If using a Gradle project with the Spring Boot plugin, you can package it with `./gradlew bootJar` (Linux/macOS) or `gradlew.bat bootJar` (Windows), then replace `app.jar` in the commands below with the path to the actual JAR.

### Case A: enable only dev

```bash
java -jar app.jar --spring.profiles.active=dev
```

Expected:

```text
dev-local = true
release-like = false
managed-release = false
not-prod = true
```

Explanation: `dev & !cloud` is true because `dev` is present and `cloud` is absent. `staging | prod` is false because both staging and prod are missing. The `!prod` condition is true.

### Case B: enable dev and cloud

```bash
java -jar app.jar --spring.profiles.active=dev,cloud
```

Expected:

```text
dev-local = false
release-like = false
managed-release = false
not-prod = true
```

Simply adding `cloud` flips `dev & !cloud` from true to false. This demonstrates the role of negation in an AND condition.

### Case C: enable only prod

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected:

```text
dev-local = false
release-like = true
managed-release = false
not-prod = false
```

`staging | prod` is true thanks to prod. However, `(staging | prod) & cloud` is false because cloud is missing.

### Case D: enable prod and cloud

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Expected:

```text
dev-local = false
release-like = true
managed-release = true
not-prod = false
```

Because prod and cloud are active together, both the release-group OR expression and the combined AND/OR expression evaluate to true.

### Case E: enable staging and cloud

```bash
java -jar app.jar --spring.profiles.active=staging,cloud
```

Expected:

```text
dev-local = false
release-like = true
managed-release = true
not-prod = true
```

`staging` satisfies the OR branch, `cloud` satisfies the AND condition, and since `prod` is absent, `!prod` remains true. This is an example of multiple independent conditions evaluating to true in a single startup.

### Case F: no active profile selected

```bash
java -jar app.jar
```

Assuming the host environment supplies no extra profiles, the result is:

```text
dev-local = false
release-like = false
managed-release = false
not-prod = true
```

Here `!prod` is true because `prod` is not active. This reinforces an important reminder: **`!prod` does not mean "dev"**, it simply means "the prod profile is not active".

To keep runs independent, clear any leftover `SPRING_PROFILES_ACTIVE` environment variable or `-Dspring.profiles.active` system property from a previous session. Each run should be a fresh process.

## 9. Summary results of the experiment

| Active profiles | `dev & !cloud` | `staging | prod` | `(staging | prod) & cloud` | `!prod` |
| --- | --- | --- | --- | --- |
| No active profile | False | False | False | True |
| `dev` | True | False | False | True |
| `dev,cloud` | False | False | False | True |
| `staging` | False | True | False | True |
| `prod` | False | True | False | False |
| `prod,cloud` | False | True | True | False |
| `staging,cloud` | False | True | True | True |
| `prod,staging,cloud` | False | True | True | False |

You can use the table to check your reasoning before running commands. Understanding an expression properly lets you predict which documents are loaded for **any profile combination**, without testing by repeatedly editing YAML.

Looking at the `staging,cloud` row, we can clearly see the independence of the conditions: `staging | prod` is true, `cloud` is true, and `!prod` is also true. An application is not limited to activating only one conditional document at a time.

## 10. Distinguishing on-profile from @Profile

Their names look similar, yet they apply in different places:

| Mechanism | Conditioned target | Example |
| --- | --- | --- |
| `spring.config.activate.on-profile` | A Config Data document | Load YAML when `"prod & cloud"` is true |
| `@Profile` | A bean definition or bean configuration | Register Java bean when `"prod & cloud"` is true |
| `spring.profiles.active` | Currently selected profile set | `prod,cloud` |
| `Environment.acceptsProfiles(Profiles.of(...))` | Evaluate an expression at runtime | `"(prod | staging) & cloud"` |

### 10.1. Using @Profile with expressions

Suppose the application has a bean dedicated to operating on cloud infrastructure:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class CloudConfiguration {

    @Bean
    @Profile("prod & cloud")
    CloudClient cloudClient() {
        return new CloudClient();
    }
}
```

`CloudClient` here is a hypothetical type declared by the application itself. The goal of the example is the annotation syntax. The `cloudClient` bean is registered only when **both prod and cloud** are active.

If the annotation uses:

```java
@Profile("prod | staging")
```

then only one of the two profiles needs to be active.

If it uses:

```java
@Profile("!prod")
```

then the bean is registered in every run satisfying the absence of `prod`, including unintended runs if the project mistakenly assumes "not prod = dev".

### 10.2. Do not use @Profile to replace every configuration condition

If only a URL, timeout, retry count, or log level changes, it is usually easier to maintain using configuration properties and `@ConfigurationProperties`. There is no need to create nearly identical business beans just because profiles differ.

Use `@Profile` when the difference truly lies in **whether a component is registered or selected**. Use `spring.config.activate.on-profile` when you need to **conditionally load a group of configuration values**. In both cases, operator logic remains AND/OR/NOT over the profile set.

### 10.3. Evaluating expressions in code with Profiles.of

Spring Framework provides the `Profiles.of(...)` API to represent a profile condition and `Environment.acceptsProfiles(...)` to evaluate it:

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

public final class ProfileChecks {

    private final Environment environment;

    public ProfileChecks(Environment environment) {
        this.environment = environment;
    }

    public boolean isManagedRelease() {
        return environment.acceptsProfiles(
            Profiles.of("(staging | prod) & cloud")
        );
    }
}
```

This check can be useful in diagnostic code or well-structured initialization conditions. However, if this pertains to a bean registered conditionally, using `@Profile` or built-in conditional configuration mechanisms usually communicates intent more clearly than scattering `acceptsProfiles` calls into business logic.

## 11. Do not confuse expressions with the active profiles list

Two configuration lines are frequently confused:

```properties
spring.profiles.active=prod,cloud
spring.config.activate.on-profile=prod & cloud
```

The first line is a **profile activation** list. The second line is a **document condition** and should only be placed in an appropriate configuration document context.

When using YAML:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
```

Do not write:

```yaml
spring:
  profiles:
    active: "prod & cloud"
```

intending to activate both `prod` and `cloud` at once. The value of `spring.profiles.active` is a list of names, not a logical expression for Spring to infer a set of profiles.

Similarly, `spring.profiles.active=prod|cloud` is not syntax to select "prod or cloud". Expressions like `prod | cloud` are evaluated where a condition is needed, and **do not decide which profiles get turned on**.

## 12. Placement constraints in Config Data

In Spring Boot, distinguish **selecting active profiles** from **loading documents based on active profiles**.

A document activated by:

```yaml
spring:
  config:
    activate:
      on-profile: "prod"
```

already depends on the active profile set. Therefore, it is not the right place to redefine that very profile set.

Properties such as `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group` have constraints requiring profile-independent documents. Do not declare them inside a document activated by `spring.config.activate.on-profile` or inside a profile-specific file like `application-prod.yml` expecting Spring Boot to allow resetting active profiles there.

Example to avoid:

```yaml
spring:
  config:
    activate:
      on-profile: "dev"

  profiles:
    active: prod
```

This snippet attempts to switch to `prod` from a document that only takes effect once `dev` has already been chosen. Spring Boot handles profile selection at the appropriate phase of configuration loading and restricts such circular declarations.

The proper approach is to **select profiles from outside** (for example, the `--spring.profiles.active=dev` argument), then let documents with `on-profile` decide for themselves whether they are loaded.

## 13. Another pitfall: YAML with multiple documents and multiple matching conditions

Suppose `application.yml` is:

```yaml
service:
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: "prod | staging"

service:
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

service:
  timeout: 2s
```

With `prod,cloud`, **both conditional documents evaluate to true**. In a multi-document YAML file like this example and with no higher-precedence external source, a document appearing later can override the earlier document's value for the same key, so `service.timeout` becomes `2s`.

However, that does not mean the `&` operator has "higher override precedence" than the `|` operator. The operator only decides **whether a document matches its condition**. **Document order and configuration source order** decide which value is chosen if multiple documents provide the same property.

If you swap the positions of the two documents, the result for the same profile set can change. Therefore, you should:

- Order documents from general rules to specific rules when overriding is intended.
- Avoid having multiple documents write the same key unless the override is clearly designed and documented.
- Keep profile differences easy to read instead of building an overlapping chain of conditions that is hard to trace.
- When results differ from expectations, check both the activation condition **and** the source's position in the precedence order.

A matching expression is only a necessary condition for a document to be loaded; it is not sufficient to guarantee that a property inside that document becomes the final value received by a bean.

## 14. Practicing negation with parentheses

Examine three expressions:

```text
A. !(prod | staging)
B. !prod & !staging
C. !prod | !staging
```

A and B are equivalent: both are true only when **neither prod nor staging is present**.

C is different: missing **at least one** of the two profiles makes it true. Thus, with active profiles containing only `prod`, C is true due to `!staging`; whereas A and B are false.

Another example:

```text
D. !(prod & cloud)
E. !prod | !cloud
F. !prod & !cloud
```

D and E are equivalent: the condition is false only when **both prod and cloud** are active. F is stricter: both prod and cloud must be absent.

Remember De Morgan's logical laws:

```text
!(A | B) == !A & !B
!(A & B) == !A | !B
```

These are rules of logic, not Spring-specific behavior. Yet when putting them into profile expressions, **parentheses become even more important** because they both help readers understand the intent and avoid errors when mixing AND with OR.

## 15. Operational scenario: which conditions should be expressed with profiles?

Suppose a deployment team has independent contexts:

- `dev`, `staging`, `prod`: environment stages.
- `cloud`: application runs on cloud infrastructure.
- `local`: application runs on a personal machine.
- `metrics`: enables an experimental measurement mode.

Some needs can be expressed as:

| Requirement | Appropriate expression |
| --- | --- |
| Only dev and not cloud | `dev & !cloud` |
| Staging or prod | `staging | prod` |
| Cloud in staging or prod | `(staging | prod) & cloud` |
| Not prod | `!prod` |
| Neither staging nor prod | `!(staging | prod)` |
| Prod with metrics but not local | `prod & metrics & !local` |

However, **not every option should be modeled as a profile**. If `metrics` is just a small toggle that can change independently, a property like `observability.metrics-enabled=true` may be simpler than creating another profile. If a value changes per user or per request, it is also usually business data, not a Spring profile.

Use expressions when profile names already have clear meanings and combined conditions are genuinely needed. Each expression should express a rule short enough that operators can predict it from the active profile set.

## 16. Distinguishing a profile name from an expression with operators

A profile name like `prod-cloud` is just **a single name**. It has no logical meaning of "prod and cloud" unless the application explicitly activates the name `prod-cloud` or designs a specific profile group.

By contrast:

```text
prod & cloud
```

is an expression that is true when **two separate names** are active at the same time.

A profile group in Spring Boot can allow a high-level name to activate multiple member profiles. For example, a `production` group can activate both `prod` and `cloud` if the application declares it in a valid location. Once the member profiles are active, the `prod & cloud` expression will match.

However, a **profile group** differs from a **conditional expression**:

- A profile group defines *which names are activated together*.
- An `on-profile` or `@Profile` expression defines *when a document or bean is applied*.

Do not mix the two responsibilities by placing activation logic inside a document that is only loaded once the expression already matches.

## 17. Common implementation mistakes

### 17.1. Forgetting quotes around ! in YAML

Error-prone example:

```yaml
spring:
  config:
    activate:
      on-profile: !prod
```

YAML may interpret `!prod` as tag syntax, causing a document parsing error. Write:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

Quoting the whole expression also helps readers recognize it as a condition string, especially with `&` and `|`.

### 17.2. Mixing AND and OR without parentheses

Do not write `prod & cloud | staging`. Replace it with `(prod & cloud) | staging` or `prod & (cloud | staging)` depending on the actual intent. Do not guess operator precedence from other programming languages.

### 17.3. Using !prod to mean dev

`!prod` is true in `staging`, `test`, and many other states. If you only want dev, use `dev`; if you want dev without cloud, use `dev & !cloud`.

### 17.4. Expecting an expression to activate profiles automatically

`on-profile: "prod & cloud"` only evaluates already-active profiles. It does not turn on `prod` and `cloud` by itself. Pass `--spring.profiles.active=prod,cloud` or supply profiles through an appropriate startup mechanism.

### 17.5. Confusing on-profile and Java @Profile

`on-profile` only conditions a Config Data document. It does not directly enable or disable a Java bean unless that bean has its own condition. Conversely, `@Profile` on a bean does not automatically create or delete a YAML file. Both evaluate profiles, but they act on different targets.

### 17.6. Confusing being active with winning precedence

A document can be loaded properly according to `on-profile` yet still have its values overridden by environment variables, command-line arguments, or higher-precedence Config Data. When diagnosing, check in order: active profiles -> which conditions match -> which sources provide the key -> which source supplies the final value.

### 17.7. Expecting profiles to change while a process is running

Profile-conditional configuration documents are normally loaded at application startup. Changing environment variables or YAML files after beans are constructed does not make Spring Boot re-evaluate every expression and rebind every value automatically. A new test run should start a new process, or the project must have a specifically designed configuration refresh mechanism.

## 18. Self-assessment exercises

### Exercise 1: Choose the expression

For each requirement, write a valid expression:

1. Load only when `prod` or `staging` is active.
2. Load only when `dev` is active and `cloud` is not active.
3. Load only when `cloud` is present along with at least one of `prod` or `staging`.
4. Load only when neither `prod` nor `staging` is present.
5. Load when `prod` is active, or when both `staging` and `cloud` are active.

Reference answers:

```text
1. prod | staging
2. dev & !cloud
3. cloud & (prod | staging)
4. !(prod | staging)
5. prod | (staging & cloud)
```

### Exercise 2: Evaluate profile combinations

Given the expression:

```text
(dev | staging) & !cloud
```

Evaluate the result for the following profile sets:

| Active profiles | Result |
| --- | --- |
| `dev` | True |
| `staging` | True |
| `dev,cloud` | False |
| `staging,cloud` | False |
| `prod` | False |
| `dev,staging` | True |

Explanation: at least one of `dev/staging` must be present, and `cloud` must not be present.

### Exercise 3: Distinguish two groupings

Two expressions:

```text
A: (prod | staging) & cloud
B: prod | (staging & cloud)
```

With only `prod` active, A is false while B is true. With only `staging,cloud` active, both A and B are true. Build the table yourself for `cloud`, `prod,cloud`, `prod,staging`, and `dev,cloud`.

### Exercise 4: YAML file with multiple conditional documents

Given the file:

```yaml
feature:
  mode: base

---
spring:
  config:
    activate:
      on-profile: "dev | test"
feature:
  mode: development

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"
feature:
  mode: managed
```

Predict `feature.mode` when running sequentially with:

- No active profile: `base`.
- `dev`: `development`.
- `test`: `development`.
- `prod`: `base`.
- `prod,cloud`: `managed`.

In these scenarios, no two conditional documents both declare the key and both match. Therefore, the result depends directly on each document's condition, assuming no higher-precedence source exists.

### Exercise 5: Spot the configuration bug

A document contains:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud | metrics"
```

Requirement: the document is loaded if (`prod` and `cloud`) or `metrics` is present. Fix it to:

```yaml
spring:
  config:
    activate:
      on-profile: "(prod & cloud) | metrics"
```

If the requirement changes to "prod is present and (cloud or metrics)", you must write `prod & (cloud | metrics)`. Changing only the position of parentheses alters the behavior.

## 19. An easy way to remember

A profile expression is a **logical question about the active profile set**.

- `!A`: is A absent?
- `A & B`: are both A and B active?
- `A | B`: is at least one of A or B active?
- `(A | B) & C`: is C active, and is at least one of A/B also active?

When writing a condition for a YAML document, put the expression in `spring.config.activate.on-profile`, **quote the string**, and use **explicit parentheses** when combining AND with OR. When writing a condition for a Java bean, use `@Profile("...")` with the same logical meaning.

The processing flow can be visualized as:

```text
Select active profiles at startup
                |
                v
Evaluate on-profile expression
                |
        +-------+-------+
        |               |
      true            false
        |               |
  Load document     Do not load
        |
        v
Enter PropertySource precedence order
        |
        v
Effective value bound to beans
```

Most importantly: **a matching expression decides whether a document participates, while configuration source order decides the final value**. Distinguishing these two steps accurately explains why a profile-conditional configuration can "match the condition" yet the bean still receives a different value.

Further reading: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html), and Spring Framework documentation on `@Profile` expressions and `Profiles.of(...)`.
