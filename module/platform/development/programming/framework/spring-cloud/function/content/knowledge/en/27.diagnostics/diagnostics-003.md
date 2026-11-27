# Wrong Name Lookup Still Returns a Function When Fallback Is Enabled

## 1. Symptom: Misspelled Name Still Causes FunctionCatalog to Return a Function

In a **Spring Cloud Function** application, you declare only one function:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Then you look up the wrong name:

~~~java
Function<String, String> function =
    functionCatalog.lookup(Function.class, "upprcase");
// Typo: "upprcase" instead of "uppercase".
~~~

Instead of getting `null` as expected, you may receive a valid function, and when invoked:

~~~java
String result = function.apply("hello");
// May return "HELLO"!
~~~

This is not necessarily a bug in Spring, nor is it proof that a bean named `upprcase` was registered. Spring Cloud Function has **single-function fallback**: when only **one eligible functional bean** exists, the catalog can select that lone function if the caller supplies no name, an empty name, or even **a non-matching name**.

This mechanism is convenient when deploying a small app with a single `Supplier`, `Function`, or `Consumer`. However, if you rely on it unknowingly, the application can:

- Mask typos in `spring.cloud.function.definition`.
- Cause "does the function exist" tests to give false positives.
- Invoke the wrong business function when a router or adapter passes an incorrect name.
- Break later when a second function is added or the eligible function list changes.
- Cause confusion between the real bean name and names the catalog **accepts via fallback**.

This lesson belongs to the **Diagnostics** chapter of the **SPRING_CLOUD_FUNCTION** module, where logic is written with `Supplier`, `Function`, and `Consumer` and reused through `FunctionCatalog`, composition, message conversion, HTTP, events, or serverless environments.

**Central diagnostic question:**

> Does `catalog.lookup("someName") != null` prove a function with **that exact name** was found, or merely that the catalog found **a function to substitute**?

### Learning Objectives

After this lesson, you will be able to:

1. Explain single-function fallback and why a non-existent name can still resolve to the sole function.
2. Distinguish **name registration**, **lookup success**, **actual selected function**, and **invocation success**.
3. Identify when fallback applies and when you should not assume it applies.
4. Use `getNames(null)`, `lookup(...)`, and `ApplicationContext` to detect misspelled names.
5. Disable fallback using `spring.cloud.function.single-function-fallback-enabled=false`.
6. Distinguish catalog fallback from Spring Cloud Stream's single-function auto-binding.
7. Recognize the implications for composition, the HTTP adapter, routing, error handlers, and serverless.
8. Write Spring Boot tests to verify valid names, invalid names, and behavior as the number of functions changes.

## 2. Why Does Spring Cloud Function Have a Fallback Mechanism?

Spring Cloud Function decouples **business logic** from **invocation protocols**. In a small application, you might simply write:

~~~java
@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase(java.util.Locale.ROOT);
}
~~~

This bean can be:

- Looked up by Java callers via `FunctionCatalog`.
- Exported by the web adapter as an HTTP endpoint.
- Selected by Spring Cloud Stream as a message handler.
- Used by a serverless adapter as the business function.
- Composed with another function when composition is configured.

If only one candidate exists, the framework can infer "the single function is what the caller wants." Official documentation illustrates `uppercase` as the sole function where all of the following calls can find it:

~~~java
catalog.lookup(null);
catalog.lookup("");
catalog.lookup("foo");
~~~

In this situation, `foo` **does not have to be registered**. It is simply an unmatched name normalized by the fallback mechanism to the lone function.

### 2.1. Convenience and Risk

| Situation | Benefit of fallback | Risk |
| --- | --- | --- |
| Sample app with only `uppercase` | No need to configure names in every caller | Masks misspelled names |
| Serverless deploying one business function | Can auto-select the default function | A misconfigured target still runs a different function |
| Test only checks `lookup != null` | Test looks simple | False positives for unregistered names |
| Spring Cloud Stream with one handler | Convenient when definition is omitted | Easily confused with Stream's own **auto-binding** mechanism |
| Adding a second function | Requires more explicit selection | Previously accepted typos suddenly fail |

**Key takeaway:** fallback is a **function selection** mechanism—it does not automatically create a second Spring bean with the misspelled name, is not a permanently registered alias, and is not a spell-checker.

## 3. Name Selection Mechanics: From ApplicationContext to Lookup

In Spring Cloud Function, functional beans in `ApplicationContext` are lazily discovered and registered into `FunctionCatalog`. The catalog supports named lookup, typed lookup, composition, and wrappers for type conversion.

~~~mermaid
flowchart TD
    CALL["lookup('upprcase')"] --> NAME{"Does catalog have name 'upprcase'?"}
    NAME -->|Yes| EXACT["Look up exact name"]
    NAME -->|No| ENABLED{"Single-function fallback enabled?"}
    ENABLED -->|No| NULL["Target not found"]
    ENABLED -->|Yes| ONE{"Only one eligible function?"}
    ONE -->|Yes| REWRITE["Normalize to sole function name"]
    ONE -->|No| NULL
    REWRITE --> FIND["Fetch real wrapper/function"]
    EXACT --> FIND
    FIND --> END["Caller receives function"]
~~~

This diagram illustrates **the simple named lookup case**. Composition, types, routers, and aliases involve additional rules; do not assume every input string gets rewritten to a lone function.

### 3.1. Different Names and Concepts

| Name/concept | Example | Proves a real catalog bean name? |
| --- | --- | --- |
| Real bean name | `uppercase` | Yes, after verifying via catalog/context |
| Wrong lookup name | `upprcase` | **No**, even if lookup returns a function |
| Function definition | `uppercase` or `uppercase|reverse` | Explicitly identifies selected function/composition |
| HTTP path | `/uppercase` or `/` | Web adapter mapping, not a bean name |
| Stream binding | `uppercase-in-0`, `uppercase-out-0` | Binding name, not function name |
| Broker destination | `orders-in` | Topic/queue name, not catalog name |
| Router target | `headers.targetFunction` resolves name | Must verify the final target is valid |

To find the real name, use `catalog.getNames(null)` or registration metadata; **do not infer it from the argument passed to `lookup`**.

### 3.2. Lookup Returns a Wrapper, Not Simply the Raw Bean

~~~java
Function<String, String> fromCatalog =
    catalog.lookup(Function.class, "uppercase");

Function<String, String> fromContext =
    context.getBean("uppercase", Function.class);
~~~

`fromCatalog` may be a wrapper instrumented by Spring Cloud Function to support conversion and composition. Therefore:

- Do not rely on `==` or `assertSame(...)` to verify a catalog lookup.
- Verify the actual name, type, and input/output behavior.
- A successful lookup does not mean the function has been **invoked**.
- For reactive functions returning `Mono`/`Flux`, `apply` may only construct the pipeline; real execution occurs upon subscription.

## 4. Minimal Example with Exactly One Functional Bean

Create a Java 17+ application using Spring Boot and Spring Cloud Function:

~~~java
package demo.fallback;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OneFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(OneFunctionApplication.class, args);
    }

    @Bean
    public Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

This example assumes compatible Spring Boot / Spring Cloud Function dependencies with no other application functional beans. When fallback is enabled, you may observe:

~~~java
Function<String, String> exact =
    catalog.lookup(Function.class, "uppercase");

Function<String, String> typo =
    catalog.lookup(Function.class, "upprcase");

Function<String, String> randomName =
    catalog.lookup(Function.class, "somethingElse");
~~~

When only one valid candidate exists, `exact`, `typo`, and `randomName` **can behave identically**: all three resolve to the uppercase logic.

### 4.1. Comparison Table of Expected Results

| Lookup | Fallback enabled; one matching function | Fallback disabled; no other default definition |
| --- | --- | --- |
| `lookup("uppercase")` | Uppercase function | Uppercase function |
| `lookup("upprcase")` | May return uppercase | Not found for this name |
| `lookup("somethingElse")` | May return uppercase | Not found for this name |
| `lookup("")` | May return uppercase | Does not automatically fall back to uppercase |
| `lookup(null)` | May return uppercase | Does not automatically fall back to uppercase |

**Scope of the table:** a runtime `spring.cloud.function.definition` value can provide a default definition when the caller passes an empty string or `null`. The table assumes **no extra default definition** so as to isolate the fallback effect.

### 4.2. Why Does This Code Produce a Misleading Test?

~~~java
boolean exists = catalog.lookup("upprcase") != null;
~~~

If `exists` evaluates to `true` via fallback, the test only proves **some function was returned**, not that a function named `upprcase` exists.

If you need to verify the name:

~~~java
boolean nameIsRegistered =
    catalog.getNames(null).contains("upprcase");
~~~

In the sample application, `nameIsRegistered` must be `false`, even though the typo lookup may still return `uppercase`.

## 5. Identify the Applicability Conditions Instead of Relying on Raw Counts

Spring Cloud Function documentation explains the common condition as having **only one functional bean**. In real applications, however, the catalog list may include framework helper functions, routers, or special registrations.

Therefore, do not write a rigid check like:

~~~java
if (catalog.getNames(null).size() == 1) {
    // Wrong to treat this as the sole condition governing all fallbacks.
}
~~~

Points to examine:

1. How many **valid functional candidates** remain after registration and filtering?
2. Are there special framework-provided functions (such as the router)?
3. Is the requested name **a simple name** or a composition expression?
4. Is `single-function-fallback-enabled` configured?
5. Is a default `spring.cloud.function.definition` set at runtime?
6. Does the lookup request the right `Function`, `Supplier`, or `Consumer` type?
7. Which framework version and extensions are active?

### 5.1. Not Every Lookup Falls Back

In modern implementations, name normalization includes safeguards—for example, it does not automatically replace a **definition containing the `|` composition operator** with a single function's name. Framework-provided names like the router are also handled specially.

Therefore:

~~~java
catalog.lookup("upprcase");        // May fall back.
catalog.lookup("uppercase|missing"); // Composition missing a step;
                                    // does not default to uppercase.
~~~

If a composition cannot find one of its links, treat it as a **composition error** rather than assuming fallback will fix every name mistake.

### 5.2. Function Type Also Matters

~~~java
@Bean
Supplier<String> greeting() {
    return () -> "hello";
}
~~~

If only `greeting` exists, an unnamed lookup may pick the default supplier depending on the adapter/caller mechanism. However, do not infer that:

~~~java
Function<String, String> function =
    catalog.lookup(Function.class, "greeting");
~~~

produces a valid function accepting input. `Supplier<T>`, `Function<T,R>`, and `Consumer<T>` have distinct contracts. **Name fallback does not turn a Supplier into a Function or a Consumer into a Supplier.**

When verifying, combine inventory checks, function type checks, and real invocation behavior; do not treat a non-null wrapper alone as proof that the caller's type contract holds.

## 6. How to Verify the Real Name Using FunctionCatalog

When you encounter a situation where a wrong name still returns a function, start with the public API:

~~~java
import java.util.Set;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;

FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

Set<String> names = catalog.getNames(null);
int size = catalog.size();

System.out.println("Catalog names = " + names);
System.out.println("Catalog size = " + size);

System.out.println("exact name registered = " +
    names.contains("uppercase"));

System.out.println("typo registered = " +
    names.contains("upprcase"));

Function<String, String> typo =
    catalog.lookup(Function.class, "upprcase");

System.out.println("typo lookup returned function = " +
    (typo != null));
~~~

A telltale output looks like:

~~~text
exact name registered = true
typo registered = false
typo lookup returned function = true
~~~

This is direct evidence consistent with fallback: **the misspelled name is absent from the inventory, yet lookup still returned a function**.

### 6.1. Cross-Check Spring ApplicationContext

~~~java
boolean realBeanExists =
    applicationContext.containsBean("uppercase");

boolean typoBeanExists =
    applicationContext.containsBean("upprcase");

System.out.println(realBeanExists);
System.out.println(typoBeanExists);
~~~

In the sample application, the real bean is `uppercase`. Fallback does not create a bean named `upprcase` inside `ApplicationContext`.

You can also list candidate beans:

~~~java
String[] functions =
    applicationContext.getBeanNamesForType(
        java.util.function.Function.class
    );
~~~

**Distinction:** Spring context is where beans are registered; FunctionCatalog is the lookup/wrapper layer; adapters provide invocation entry points. Each can display different lists of names.

### 6.2. What If getNames Shows Unfamiliar Names?

Check these registration sources:

- `@Bean` methods or `@Component` classes implementing `Function`/`Supplier`/`Consumer`.
- Overly broad component scanning or `@Import` configurations.
- Spring Cloud Function's function-specific component scanning.
- `FunctionalSpringApplication` and `FunctionRegistration`.
- Autoconfiguration from dependencies.
- Which names `spring.cloud.function.ineligible-definitions` filters out.

Do not tweak fallback when the real cause is **the catalog containing unexpected functions**. Audit the list accurately first.

## 7. Disabling Fallback to Require Exact Names

The property documented by Spring Cloud Function is:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

After applying it and restarting the appropriate context, looking up a wrong name **is no longer automatically normalized to the lone function via this fallback**.

~~~java
// With fallback disabled and no registration/alias under that name:
Function<String, String> exact =
    catalog.lookup(Function.class, "uppercase");  // Returns function.

Function<String, String> typo =
    catalog.lookup(Function.class, "upprcase");    // Not found.
~~~

### 7.1. Representation in YAML

~~~yaml
spring:
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Or as an environment variable following Spring Boot's relaxed binding rules:

~~~text
SPRING_CLOUD_FUNCTION_SINGLE_FUNCTION_FALLBACK_ENABLED=false
~~~

After deployment, verify the **effective value at runtime**. A property in source files can be overridden by profiles, environment variables, or startup arguments.

### 7.2. What Does This Property NOT Do?

| Desired outcome | Does `single-function-fallback-enabled=false` do it? |
| --- | --- |
| Stop misspelled names from resolving to a sole function | **Yes**, that is its purpose |
| Remove the `uppercase` bean from Spring context | **No** |
| Remove `uppercase` from FunctionCatalog | **No** |
| Disable HTTP endpoints | **No** |
| Stop Spring Cloud Stream from auto-binding a sole functional bean | **No**, that is a separate mechanism |
| Enable authorization for functions | **No** |
| Disable routing expressions explicitly configured by the app | **No** |
| Fix a non-existent function name in definition | **No**, the misconfiguration must be fixed |
| Automatically fix component scanning | **No** |

**Recommendation:** for systems that depend on exact names—multi-function apps, complex routing, error handlers, production fail-fast requirements—consider disabling fallback and adding regression tests for function names.

### 7.3. Empty/Null Names Still Have an Exception via Definition

If a caller invokes `lookup(null)` or `lookup("")`, Spring Cloud Function also has a mechanism to read a **default function definition** from the environment. Thus, if you set:

~~~properties
spring.cloud.function.definition=uppercase
spring.cloud.function.single-function-fallback-enabled=false
~~~

an unnamed lookup **can still select uppercase** due to the configured definition—this is **not** single-function fallback for a misspelled name.

To accurately test that fallback is disabled, use **a non-empty wrong name** and ensure no alias or real registration exists for it, rather than testing only `lookup(null)`.

## 8. Standard Test: Same Application, Both Fallback Modes

Unit tests with a single function should check both **enabled** and **disabled** modes. The following example sets up two independent Spring test contexts using Java 17+, JUnit 5, AssertJ, and Spring Boot Test.

### 8.1. Minimal Application Configuration for Testing

Use `@SpringBootConfiguration` and `@EnableAutoConfiguration` to construct a context with one application function, preventing broad component scanning from pulling other functions into the test.

~~~java
package demo.fallback;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
class OneFunctionTestConfiguration {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

The test project must include the Spring Cloud Function dependency so `FunctionCatalog` is auto-configured. Do not rely on plain Spring Boot Test without the Spring Cloud Function context.

### 8.2. Fallback Enabled: Wrong Name Still Returns uppercase

~~~java
package demo.fallback;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
    classes = OneFunctionTestConfiguration.class,
    properties = {
        "spring.cloud.function.single-function-fallback-enabled=true",
        "spring.cloud.stream.function.autodetect=false"
    }
)
class FallbackEnabledTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void typoIsNotRegisteredButFallsBackToOnlyFunction() {
        assertThat(catalog.getNames(null))
            .contains("uppercase")
            .doesNotContain("upprcase");

        Function<String, String> byTypo =
            catalog.lookup(Function.class, "upprcase");

        assertThat(byTypo).isNotNull();
        assertThat(byTypo.apply("hello")).isEqualTo("HELLO");
    }

    @Test
    void explicitNameStillWorks() {
        Function<String, String> byExactName =
            catalog.lookup(Function.class, "uppercase");

        assertThat(byExactName).isNotNull();
        assertThat(byExactName.apply("spring"))
            .isEqualTo("SPRING");
    }
}
~~~

This test **demonstrates behavior when fallback is enabled**; it is not an endorsement to rely on misspelled names in production.

### 8.3. Fallback Disabled: Same Wrong Name Must Be Rejected

~~~java
package demo.fallback;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
    classes = OneFunctionTestConfiguration.class,
    properties = {
        "spring.cloud.function.single-function-fallback-enabled=false",
        "spring.cloud.stream.function.autodetect=false"
    }
)
class FallbackDisabledTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void typoMustNotResolve() {
        assertThat(catalog.getNames(null))
            .contains("uppercase")
            .doesNotContain("upprcase");

        assertThat(catalog.lookup("upprcase")).isNull();
    }

    @Test
    void exactNameStillResolves() {
        Function<String, String> exact =
            catalog.lookup(Function.class, "uppercase");

        assertThat(exact).isNotNull();
        assertThat(exact.apply("hello")).isEqualTo("HELLO");
    }
}
~~~

The two test classes use different properties to avoid state leakage between tests. `spring.cloud.stream.function.autodetect=false` here simply isolates Stream if Stream dependencies happen to be on the test classpath; it **does not replace** SCF's fallback property.

### 8.4. Conditions to Keep Stable in Tests

- Run the intended test configuration without accidentally scanning extra functional beans.
- Ensure no unintended default `spring.cloud.function.definition` is configured.
- Ensure no real alias or registration named `upprcase` exists.
- Do not use `assertSame(bean, catalogResult)` because wrappers may differ from raw beans.
- When upgrading Spring Cloud Function, verify behavior against the actual version.
- If framework/router functions exist, do not inspect only total name counts; examine **application-eligible candidates**.

## 9. Regression Scenario: Adding a Second Function Exposes a Masked Bug

Initially, the application has only:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

A caller writes a typo:

~~~java
catalog.lookup("upprcase");
~~~

With fallback enabled and one candidate in the catalog, the system appears to work as if the name were valid. After adding:

~~~java
@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

the catalog now has multiple functional candidates. The wrong name `upprcase` is no longer rewritten to a sole function via single-function fallback, and lookup fails to find a target.

### 9.1. Two Interpretations—Wrong vs. Accurate

**Wrong:** "Adding `reverse` broke `uppercase`."

**More accurate:** "A misspelled lookup configuration already existed; fallback masked the bug while the app had only one function. The second function made the pre-existing bug visible."

Do not delete `reverse` just to bring fallback back. Fix the target to `uppercase` and add tests that catch typos.

### 9.2. The Reverse Can Also Happen

If an application has multiple functions, looking up a wrong name fails clearly. After a refactor, one function is excluded from the catalog by a profile or `ineligible-definitions`. Once only one candidate remains, the wrong name can **suddenly start resolving to the remaining candidate** if fallback is enabled.

Thus behavior can change whenever **the number of eligible candidates changes**, not only when someone edits the name string.

### 9.3. Test After Every Configuration Change

Add a regression test:

~~~java
assertThat(catalog.getNames(null))
    .contains("uppercase", "reverse")
    .doesNotContain("upprcase");

// With strict fallback disabled:
assertThat(catalog.lookup("upprcase")).isNull();
~~~

If you want a stronger contract check, also assert the effective `spring.cloud.function.definition` and the selected function's output.

## 10. Distinguishing Fallback from Real Bean Names or Aliases

A bean can be registered under a name different from its method name:

~~~java
@Bean("formatOrder")
Function<String, String> uppercase() {
    return String::trim;
}
~~~

The expected name in the Spring context is `formatOrder`. If a caller requests `uppercase` and still gets a result when only one functional bean exists, **fallback** is likely masking the confusion between method name and bean name.

### 10.1. How to Verify

~~~java
System.out.println(
    applicationContext.containsBean("formatOrder")
);

System.out.println(
    applicationContext.containsBean("uppercase")
);

System.out.println(catalog.getNames(null));
~~~

If a Spring bean is registered with multiple real names/aliases, those follow their own lookup rules. Never infer an alias from a successful lookup. Use Spring's bean alias / bean definition APIs and the catalog inventory to prove which names are genuinely registered.

### 10.2. Being Accepted Does Not Mean an Alias Was Created

Comparison:

| Indicator | Real alias | Fallback |
| --- | --- | --- |
| Configured/registered intentionally | Yes | Not required |
| Recognized by Spring as a bean name/alias | Yes | Not created by fallback |
| Can change when candidate count changes | Not due to fallback | **Yes** |
| Can be disabled by `single-function-fallback-enabled=false` | Not governed by this mechanism | Yes |
| Proven by `lookup("alias") != null` | Insufficient | Insufficient |

Enforce an **exact-name** contract across application configuration, adapters, and tests.

## 11. Distinguishing from spring.cloud.function.definition

In Spring Cloud Function, there are two separate operations:

1. `FunctionCatalog.lookup(name)` performed by code/callers.
2. `spring.cloud.function.definition` configuring which function or composition adapters use.

Example:

~~~properties
spring.cloud.function.definition=uppercase
~~~

This is an explicit and valid selection.

However:

~~~properties
spring.cloud.function.definition=upprcase
~~~

is a **name configuration bug**. If the catalog has only one candidate and fallback is enabled, depending on the adapter's function-selection path, that wrong name might not fail at startup and instead normalize to the lone function.

### 11.1. An Explicit Definition Does Not Automatically Catch Typos

Some assume "because I set `spring.cloud.function.definition`, the framework will reject wrong names." That assumption does not hold while fallback is enabled and only one candidate exists.

For fail-fast behavior:

~~~properties
spring.cloud.function.definition=uppercase
spring.cloud.function.single-function-fallback-enabled=false
~~~

Then integration-test the actual function definition. **Disabling fallback does not autocorrect `upprcase` to `uppercase`**; you still must fix the broken configuration.

### 11.2. Composition Uses the Pipe |

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

This is a two-step **composition**. If one step does not exist, inspect each link individually:

~~~java
catalog.lookup("uppercase");
catalog.lookup("reverse");
catalog.lookup("uppercase|reverse");
~~~

Do not treat `uppercase|missing` as a simple name lookup eligible for fallback. Modern implementations include safeguards for composition strings.

### 11.3. Semicolon ; Differs from Pipe |

In Spring Cloud Stream, `;` in `spring.cloud.function.definition` typically selects **multiple independent functions**:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Whereas `|` chains them into **one pipeline**. Using the wrong separator creates different bindings than intended and is unrelated to single-function fallback.

## 12. Distinguishing from Spring Cloud Stream Single-Function Autodetection

**It is very easy to confuse two similarly named mechanisms.**

Spring Cloud Function has:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Goal: stop auto-selecting the sole function when **looking up a wrong or missing name**.

Spring Cloud Stream has:

~~~properties
spring.cloud.stream.function.autodetect=false
~~~

Goal: disable **auto-detecting and auto-binding a sole functional bean** to handle messages when no explicit function definition is specified.

| Criterion | SCF single-function fallback | Stream function autodetect |
| --- | --- | --- |
| Where does it operate? | `FunctionCatalog.lookup` | Spring Cloud Stream functional binding |
| When does it surface? | Caller passes wrong/null/empty name | App has one functional bean and no definition set |
| Purpose | Choose which function catalog returns | Choose which function binds to the broker |
| Property | `spring.cloud.function.single-function-fallback-enabled` | `spring.cloud.stream.function.autodetect` |
| Disabling one disables the other? | **No** | **No** |
| Directly enables/disables HTTP? | No | No |
| Removes Spring bean? | No | No |

### 12.1. Example of a Supplier Auto-Bound to a Broker

~~~java
@Bean
Supplier<String> heartbeat() {
    return () -> "alive";
}
~~~

If the application has a Spring Cloud Stream binder and only one functional bean, the framework may auto-bind this supplier per configuration. Its being polled and emitting messages is **not** the result of `catalog.lookup("upprcase")`.

To avoid unintended auto-binding, explicitly declare which function to bind or disable Stream autodetection when appropriate:

~~~properties
spring.cloud.stream.function.autodetect=false
~~~

To prevent wrong-name lookups, configure **separately**:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Depending on the application, you may need both, but do not copy properties blindly without understanding operational requirements.

## 13. HTTP Web Adapter: Route Names Do Not Match Lookup Conclusions

When using Spring Cloud Function's web module, functions can be exported as endpoints. The web adapter documentation explains that if the catalog contains only one function, requests can hit:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data "hello" \
  http://localhost:8080/uppercase
~~~

and the root path:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data "hello" \
  http://localhost:8080/
~~~

both reaching the same function under the right web adapter version/configuration.

### 13.1. Do Not Assume Arbitrary URLs Always Work

An HTTP request to `/upprcase` may be handled according to web adapter mappings, definition fallbacks, and path-specific rules. **You cannot treat `catalog.lookup("upprcase")` falling back as proof that any arbitrary URL will auto-route to `uppercase`.**

The web adapter documentation also describes cases where `spring.cloud.function.definition` maps a function or composition to the root path or handles non-directly-resolved URLs. Therefore, test **the HTTP adapter itself**, not only catalog calls in unit tests.

### 13.2. Security Implications

If only one sensitive function exists and a route/adapter allows selecting it when names are ambiguous, risk increases that a caller reaches it unexpectedly. However:

- Fallback does **not** bypass Spring Security, IAM, or proxy authentication.
- Fallback does **not** turn a function into a public endpoint if no adapter is present.
- A route may still be exported by web rules even after disabling fallback.
- Protection must rely on **authorization per actual target/capability**, not merely URL names.

For administrative functions, avoid exposing them in an uncontrolled web context; enforce security allowlists, deny-by-default rules, and negative tests.

### 13.3. Test Both Layers

| Layer | What to test |
| --- | --- |
| Catalog | Misspelled lookup is rejected under strict fallback |
| HTTP | Unfamiliar/root/composition URLs do not accidentally invoke sensitive targets |
| Security | Unauthorized callers cannot trigger side effects |
| Operations | Logs/audits reflect the actual function invoked |

Asserting HTTP 404 alone is insufficient if the goal is zero side effects: verify with a fake/spy service that the sensitive operation **was not executed**.

## 14. Serverless and FunctionInvoker: Misconfigured Names Can Be Hard to Spot

A serverless adapter can pull the business function from `FunctionCatalog` while the platform invokes a handler. With the AWS Lambda adapter, the handler/entry point is distinct from the functional bean name.

Example:

~~~text
Lambda handler: FunctionInvoker
Business function: uppercase
Configured definition: upprcase  (typo)
~~~

If the catalog has only one candidate, fallback can mask the typo across certain function-selection paths. Once a second function is added or the artifact changes, invocations can fail because a sole candidate no longer exists.

### 14.1. Remediation Steps

1. Treat **handler** and **business function** as two separate names.
2. Inspect the catalog inside the real serverless artifact.
3. Read the effective runtime `spring.cloud.function.definition` value.
4. Consider disabling fallback to require exact names.
5. Test invocations with representative payloads, including wrong-target cases.
6. Never let untrusted caller routing instructions steer execution to sensitive targets.
7. When functions have side effects, verify idempotency because invocations may be retried.

**Do not assume all serverless adapters handle errors identically.** Handler, startup, serialization, and error responses depend on the platform and version; fallback is just one factor in target selection.

## 15. FunctionRouter: Do Not Rely on Fallback Instead of Routing Rules

Spring Cloud Function provides `functionRouter` to route to another function based on configuration or, for imperative message routing, supported headers/callbacks.

Suppose:

~~~text
Client/Message → functionRouter → targetName → FunctionCatalog
~~~

If `targetName` is misspelled and only one candidate function exists, fallback can cause the router or an intermediate lookup step to pick an unintended function. Do not build logic on top of that coincidence.

### 15.1. Path to Verify

~~~mermaid
flowchart LR
    INPUT["Message/Invocation"] --> ROUTER["RoutingFunction"]
    ROUTER --> NAME["Target name from config/header"]
    NAME --> LOOKUP["FunctionCatalog.lookup"]
    LOOKUP --> TARGET["Actual selected function"]
~~~

For wrong-route issues:

- Log the **resolved target name**, not just "router invoked".
- Compare the target against `catalog.getNames(null)`.
- Disable single-function fallback when strict routing is required.
- Maintain an allowed-target list per caller/capability.
- Ensure untrusted input cannot freely select arbitrary internal functions.
- Test that invalid targets are rejected instead of falling back to the lone function.

### 15.2. Reactive Routing Is Not Arbitrary Per-Message Routing

For `Function<Flux<T>, Flux<R>>`, the unit of invocation can be the entire publisher rather than each individual element. Spring Cloud Function documentation distinguishes reactive stream routing instructions from imperative message routing. Do not assume an event header can re-select a different function per item just because the router is enabled.

## 16. Real-World Case: Missing Error Handler Yet Lookup Still "Succeeds"

A system may look up a dedicated function to handle errors:

~~~java
Function<?, ?> errorHandler =
    catalog.lookup("handleProcessingError");
~~~

The developer forgot to register the `handleProcessingError` bean. If the catalog actually contains only one other function—say, `processOrders`—fallback can return **`processOrders`** instead of `null`.

### 16.1. Why Is This More Dangerous Than an Ordinary Typo?

- The code believes it selected an error handler.
- When an error occurs, the framework or caller may **re-invoke the primary business function**.
- Side effects may execute unintentionally.
- Tests checking only `handler != null` still pass.
- The missing handler goes undetected at startup.

This is **a risk scenario**, not a claim that every framework's error-handler API calls `FunctionCatalog.lookup` this way. Check your specific integration.

### 16.2. Fail-Fast Design

If a callback requires a declared function name:

~~~java
String expectedName = "handleProcessingError";

if (!catalog.getNames(null).contains(expectedName)) {
    throw new IllegalStateException(
        "Required error handler is not registered: " +
        expectedName
    );
}

Function<?, ?> handler =
    catalog.lookup(Function.class, expectedName);

if (handler == null) {
    throw new IllegalStateException(
        "Required error handler cannot be resolved: " +
        expectedName
    );
}
~~~

Here, checking the inventory before lookup **verifies the exact name**, rather than accepting whichever function the catalog hands back.

If the handler must be `Consumer<ErrorEvent>`, check that type instead of defaulting to `Function.class` out of habit. Add a test firing a simulated error and verifying the proper handler runs; avoid tests with real side effects.

## 17. FunctionCatalog Does Not Mean ApplicationContext Has That Alias

Sometimes bugs are misdiagnosed as "Spring automatically creates an alias for the lookup name."

Check the difference:

~~~java
boolean existsAsBean =
    context.containsBean("upprcase");

boolean appearsInCatalog =
    catalog.getNames(null).contains("upprcase");

boolean resolvesByFallback =
    catalog.lookup("upprcase") != null;
~~~

You might observe:

~~~text
existsAsBean        = false
appearsInCatalog    = false
resolvesByFallback  = true
~~~

That is clear evidence of fallback. If `containsBean` is true, another alias or bean genuinely exists; investigate registration rather than only disabling fallback.

### 17.1. Beans Can Come from Unexpected Places

Catalog candidates can originate from:

- `@Bean` methods in `@Configuration`.
- `@Component` classes implementing a functional interface.
- SCF function-specific scanning.
- `FunctionRegistration` via a functional initializer.
- Library autoconfiguration.
- Accidental test/demo beans picked up by overly broad component scanning.

If candidate counts differ across environments, fallback behavior can shift too. Compare runtime artifacts and name lists across local, staging, and prod.

## 18. ineligible-definitions Indirectly Affects Fallback

Spring Cloud Function lets you exclude functional beans that should not enter the catalog:

~~~properties
spring.cloud.function.ineligible-definitions=internalMaintenance
~~~

This property is **not** a fallback toggle. However, it can change how many candidates the catalog sees.

Example:

~~~text
Before filtering:
  uppercase
  internalMaintenance
=> Multiple candidates; wrong names normally do not fall back.

After filtering:
  uppercase
=> One candidate; if fallback is enabled, wrong names may resolve to uppercase.
~~~

Thus a filtering change made to shrink exposed surface area can inadvertently **hide** typo bugs unless strict lookup is enabled.

### 18.1. Prevention

When using `ineligible-definitions`, consider adding:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

and regression-testing all three conditions:

1. The internal function **is absent from the catalog inventory**.
2. The internal name **does not mistakenly resolve** to another function.
3. Public functions **still** look up and execute properly.

Do not verify "internal function is hidden" solely via `lookup("internalMaintenance") == null` while fallback is enabled; the result may reflect fallback to `uppercase` rather than true registration state.

## 19. Logs and Actuator: Observing the Right Evidence

To diagnose inside a running application, you can add an `ApplicationRunner` enabled only under a debug profile.

~~~java
package demo.fallback;

import java.util.function.Function;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.core.env.Environment;

public final class CatalogFallbackInspector
        implements ApplicationRunner {

    private static final Logger log =
        LoggerFactory.getLogger(CatalogFallbackInspector.class);

    private final FunctionCatalog catalog;
    private final Environment environment;

    public CatalogFallbackInspector(
            FunctionCatalog catalog,
            Environment environment) {
        this.catalog = catalog;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String strict = environment.getProperty(
            "spring.cloud.function.single-function-fallback-enabled",
            "<unset>"
        );

        log.info("single-function-fallback-enabled={}", strict);
        log.info("function.definition={}",
            environment.getProperty(
                "spring.cloud.function.definition",
                "<unset>"
            )
        );
        log.info("catalog names={}", catalog.getNames(null));

        String requested = "upprcase";
        log.info("requested name registered={}",
            catalog.getNames(null).contains(requested));

        Function<?, ?> resolved =
            catalog.lookup(Function.class, requested);

        log.info("lookup returned function={}",
            resolved != null);
    }
}
~~~

The inspector bean must be registered via `@Bean` or `@Component` in a debug profile; creating the class alone will not run it. Note: **this diagnostic code intentionally looks up a misspelled name** to verify behavior, without calling `apply` or `subscribe`, so it does not trigger business side effects.

### 19.1. Beware of "function found" Log Messages

If a logger merely writes:

~~~text
Requested function 'upprcase' found
~~~

the log is misleading. Prefer logging:

~~~text
requestedName=upprcase
registeredName=false
lookupReturnedNonNull=true
fallbackEnabled=true
catalogNames=[uppercase, ...]
~~~

Do not label a function as "actually named upprcase" solely because lookup returned non-null. With complex routers or registrations, inspect the final target via framework metadata and invocation traces.

### 19.2. Actuator Can Help Confirm the Inventory

When Actuator and web dependencies are present, Spring Cloud Function can expose the `functions` endpoint, for example:

~~~properties
management.endpoints.web.exposure.include=health,info,functions
~~~

Then in an authorized environment:

~~~bash
curl http://localhost:8080/actuator/functions
~~~

The endpoint can list function metadata. It **is not automatically present** just because you use the catalog; its URL depends on management base path/port and security, and it should never be exposed publicly just for debugging.

### 19.3. Value of catalog.size()

`catalog.size()` helps inspect registration count at the API level, but in environments with wrappers, framework functions, and lazy registration, it does not necessarily equal "the number of business functions eligible for fallback." Combine `getNames(null)`, bean inventory checks, and strict lookup experiments.

## 20. Reading Runtime Configuration to Spot Environment Differences

A bug where "staging resolves the wrong name to a function while production does not" is commonly caused by:

| Differing factor | Consequence |
| --- | --- |
| Number of functional beans | Fallback applies in one environment but not the other |
| Profile/conditional bean | A second bean appears only in prod |
| `ineligible-definitions` | Candidate list changes |
| `spring.cloud.function.definition` | Default selection differs |
| `single-function-fallback-enabled` | One environment is strict, the other permissive |
| Spring Cloud Function version | Processing rules and extensions may differ |
| Functional bean from a dependency | A library contributes another candidate |
| Web/Stream/serverless adapter | Same catalog, different target selection path |

### 20.1. Comparison Scenario

~~~text
LOCAL:
  names = [uppercase]
  fallback = true
  lookup("upprcase") = uppercase

STAGING:
  names = [uppercase, reverse]
  fallback = true
  lookup("upprcase") = not found

PROD:
  names = [uppercase]
  fallback = false
  lookup("upprcase") = not found
~~~

This is an **illustrative scenario**, not fixed output across every version. It shows why you must gather **the name set**, **fallback setting**, and **definition value** when comparing environments.

### 20.2. Do Not Fix It by Adding a Dummy Function

A flawed workaround is adding a second `Function.identity()` bean just to force multiple candidates into the catalog and "suppress fallback." That alters web adapter, Stream binding, and router behavior, potentially confusing selection or accidentally exposing another endpoint.

Use **the property designed to disable fallback** rather than turning catalog structure into an error-control hack.

## 21. Assessing Risk When Fallback Selects a Side-Effecting Target

In the `uppercase` example, fallback merely uppercases a string so the mistake seems harmless. Now suppose the lone function is:

~~~java
@Bean
Function<RebuildCommand, RebuildResult> rebuildIndex(
        IndexMaintenanceService service) {
    return service::rebuild;
}
~~~

If a caller requests the wrong name `validateOrder` and the catalog returns `rebuildIndex` via fallback, risks depend on data and invocation paths:

- Callers may accidentally trigger an administrative operation.
- Wrapper conversion may fail if the input type mismatches.
- If the input is compatible, side effects may execute.
- Logs or metrics might record the caller-requested name rather than the target actually executed.
- If an adapter permits routing from untrusted input, separate authorization/allowlisting is mandatory.

### 21.1. This Is Not a Default Security Bypass

Fallback does **not** grant HTTP, broker, or IAM permissions. Assess risk under concrete conditions:

1. Does any adapter or caller actually query the catalog with a wrong name?
2. Is the caller authorized to reach that entry point?
3. Is the input compatible enough for the target to execute?
4. Does the target cause sensitive side effects?
5. Is authorization enforced inside the business service/adapter?
6. Do logging and auditing capture the actual invocation?

For sensitive business functions, beyond disabling fallback, enforce boundary policies and separate internal operations from public catalogs/adapters where appropriate.

### 21.2. Defense in Depth at the Call Site

A caller requiring a specific target can verify the inventory prior to lookup:

~~~java
static <T> T requireFunction(
        FunctionCatalog catalog,
        String name,
        Class<?> type) {

    if (!catalog.getNames(null).contains(name)) {
        throw new IllegalArgumentException(
            "Function is not registered: " + name
        );
    }

    T function = catalog.lookup(type, name);

    if (function == null) {
        throw new IllegalStateException(
            "Function registration cannot be resolved: " + name
        );
    }

    return function;
}
~~~

This is an illustrative helper usable at startup to validate configuration. The generic method does not verify type `T` at runtime; callers must supply the right `Function`/`Supplier`/`Consumer` interface and signature. In apps using dynamic registration, inventory checking and lookup timing must also align with the lifecycle.

If you simply need a specific Java bean without SCF wrappers or composition, you can inject the bean directly by type/name; that avoids name fallback while keeping application dependency design clean.

## 22. Step-by-Step Diagnostic Workflow

~~~mermaid
flowchart TD
    START["Wrong-name lookup still returns function"] --> INVENTORY["Record requestedName\nand catalog.getNames(null)"]
    INVENTORY --> REGISTERED{"Is wrong name in inventory?"}
    REGISTERED -->|Yes| ALIAS["Check real bean/alias/registration"]
    REGISTERED -->|No| FALLBACK{"single-function-fallback-enabled?"}
    FALLBACK -->|Enabled / unset| COUNT["Check eligible candidates\nafter filters/router"]
    FALLBACK -->|Disabled| OTHER["Check default definition,\nrouter, or extensions"]
    COUNT --> ONE{"Only one eligible candidate?"}
    ONE -->|Yes| CONFIRM["Most likely single-function fallback"]
    ONE -->|No| OTHER
    CONFIRM --> FIX["Fix name + disable fallback\n+ add negative tests"]
    ALIAS --> FIX
    OTHER --> FIX
    FIX --> VERIFY["Test catalog, HTTP,\nStream, and serverless"]
~~~

### 22.1. Incident Checklist

1. **Record the exact looked-up string:** `upprcase`, a composition string, or a routing target?
2. **Check whether the name is real:** `catalog.getNames(null)` and Spring bean aliases.
3. **Determine functional candidates:** count application functions, types, filters, and routers.
4. **Read effective properties:** `single-function-fallback-enabled` and `function.definition`.
5. **Check SCF version:** behavior can vary across branches and framework extensions.
6. **Reproduce via catalog lookup:** do not invoke side effects while investigating production.
7. **Fix the source name:** bean name, definition, routing target, or handler mapping.
8. **Disable fallback if strict naming is desired:** configure, restart, and verify.
9. **Test the typo:** assert `getNames(null)` lacks the typo and `lookup(typo)` returns null.
10. **Test the right target:** verify the intended function still processes input/output properly.
11. **Test adapters:** confirm HTTP, Stream, and serverless do not accidentally hit another target.
12. **Monitor post-deploy:** catalog inventory, errors, invoked functions, and side-effect audits.

### 22.2. When Handling Production

Never test-invoke a sensitive function with real payloads just to verify fallback; execution can cause side effects. Rely on inventory APIs, staging, or fake services. If there is evidence an unintended target already executed, perform business impact assessment and follow your organization's incident response process.

## 23. Remediation Selection Table

| Actual issue | Appropriate action | What to re-verify |
| --- | --- | --- |
| Misspelled bean name | Fix caller/definition | Exact lookup and output are right |
| Lone function masked a typo | `single-function-fallback-enabled=false` | Typo lookup no longer resolves |
| Missing required function | Fail fast via inventory + strict lookup | Startup/tests fail clearly |
| Unexpected second bean | Fix scan/profile/filter | `getNames(null)` matches expectations |
| Internal function in catalog | `ineligible-definitions` or refactor to service | Context/catalog and direct call paths |
| Stream auto-binds lone function | `spring.cloud.stream.function.autodetect=false` or explicit definition | Runtime bindings |
| Unexpected HTTP path | Check web mapping/definition and security | HTTP positive + negative tests |
| Serverless picks wrong function | Handler, definition/routing, and strict lookup | Invocation integration tests |
| Router accepts untrusted names | Allowlist/authorization, strip headers | Sensitive targets cannot be invoked |
| Test only asserts lookup non-null | Assert inventory and real behavior | Fake names are rejected |
| Second function exposes old bug after refactor | Fix the pre-existing typo | Regression test for changing function count |

Do not mix properties that solve unrelated problems just because they all contain the word "function". They operate at different layers.

## 24. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`lookup("foo") != null` proves a bean named `foo` exists." | It may simply be single-function fallback. |
| "Spring created a `foo` alias when lookup succeeded." | Fallback does not create Spring bean aliases. |
| "Wrong names only fall back if `null` is passed." | Non-existent names can also fall back when conditions match. |
| "Having size 1 in `getNames` is the absolute condition." | The framework includes routers/special registrations; check eligible candidates. |
| "Setting `function.definition` always rejects typos." | Fallback can mask typos in some function-selection paths. |
| "Disabling fallback deletes the function from the catalog." | It only changes lookup behavior; it does not remove beans. |
| "Disabling Stream autodetect disables catalog fallback." | Those are two independent properties. |
| "Disabling catalog fallback disables the HTTP web adapter." | No, web mapping is a separate layer. |
| "Disabling fallback is enough to protect sensitive functions." | Authorization/IAM and call-path restrictions are required. |
| "Typos disappear on their own once a second function is added." | They usually surface instead of staying masked; fix the source. |
| "`lookup(null)` always fails when fallback is off." | A default `definition` may still select a function. |
| "`uppercase|missing` falls back to `uppercase`." | Compositions follow separate rules; they are not treated as single fallback names. |
| "Functions returned by the catalog are the exact Spring bean instances." | The catalog may return wrappers; do not assert object identity. |
| "A lone `Supplier` can be invoked like a `Function`." | Functional interfaces have different contracts. |
| "A catalog unit test proves no HTTP route is exposed." | Adapter and security integration tests are required. |
| "If `Flux` logs nothing, the catalog returned the wrong function." | A cold publisher might simply not be subscribed to yet. |

## 25. Self-Assessment Questions

1. What scenario was single-function fallback designed to simplify?
2. Why can `lookup("upprcase")` return a function when the catalog only has `uppercase`?
3. What is the difference between a **real bean name** and a **lookup name accepted via fallback**?
4. Why is checking `lookup(name) != null` not a valid existence test for a name?
5. Which API lists the actual registered names in `FunctionCatalog`?
6. Which property disables single-function fallback?
7. Why can `lookup(null)` still select a function even when fallback is disabled?
8. Why can adding a second function expose a pre-existing typo?
9. If `ineligible-definitions` excludes the second function, how might fallback behavior change?
10. Why should you not create a dummy second function solely to block fallback?
11. Does the composition `uppercase|reverse` follow the same fallback rule as `lookup("upprcase")`?
12. What does `spring.cloud.function.definition` mean, and does it replace typo checking?
13. How does `spring.cloud.stream.function.autodetect=false` differ from `single-function-fallback-enabled=false`?
14. If a typed lookup requests `Function.class` while the lone function is a `Supplier`, should it be treated as a function taking input?
15. Why does a working unfamiliar web URL not prove the catalog has a bean matching that URL name?
16. When a routing target comes from user input, what controls are needed beyond disabling fallback?
17. In serverless, how do the handler and business function name differ?
18. Why can a wrong error-handler lookup be more severe than mistakenly calling an `uppercase` function?
19. How do you write two Spring Boot tests comparing fallback enabled versus disabled?
20. What data should be logged to confirm fallback without triggering side effects?
21. Why are catalog unit tests insufficient to prove Stream bindings or HTTP authorization are correct?
22. If fallback occurs locally but not in production, which properties and function lists would you compare?

## 26. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — explains `FunctionCatalog`, `spring.cloud.function.definition`, the single-function lookup-by-any-name case, and `single-function-fallback-enabled`.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — `FunctionRegistration`, `getNames(null)`, `size()`, and working with the catalog.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — root path with a single function, HTTP mappings, function selection, and filtering.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — function definition, auto-binding, and message transport boundaries.
- [Spring Cloud Function — AWS Lambda Adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html) — handlers, function selection, and routing in serverless.
- [Spring Cloud Function — SimpleFunctionRegistry source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/SimpleFunctionRegistry.java) — reference for name normalization checks in the implementation; prefer matching the source tag to your project dependency.
- [Spring Cloud Function — BeanFactoryAwareFunctionRegistry source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/BeanFactoryAwareFunctionRegistry.java) — lookup via Spring bean factory and function registrations.

Core behavior is described according to modern Spring Cloud Function documentation. When an application uses different versions/BOMs, custom adapters, or extensions, verify against source tags and integration tests matching your deployed version. Java examples are educational samples and do not replace end-to-end tests with HTTP, binders, IAM, or side-effecting services.

**Takeaway:** When `FunctionCatalog.lookup("wrongName")` still returns a function, **do not assume the wrong name is registered**. In an application with only one eligible functional candidate, Spring Cloud Function can use **single-function fallback** to return that lone function. Verify real names with `catalog.getNames(null)` and `ApplicationContext`, disable fallback with `spring.cloud.function.single-function-fallback-enabled=false` when exact selection is required, and test both **valid names** and **invalid names**. Keep this mechanism distinct from Spring Cloud Stream auto-binding, HTTP route mapping, and serverless routing: each layer requires its own configuration, testing, and protection to prevent invoking the wrong business logic.
