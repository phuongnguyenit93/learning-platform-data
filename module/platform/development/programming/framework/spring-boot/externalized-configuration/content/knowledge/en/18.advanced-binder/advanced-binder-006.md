# Binding into Existing Objects with `Bindable.ofInstance` in Spring Boot

## 1. Context and Objectives

Spring Boot supports **Externalized Configuration** so applications receive operational parameters from `application.properties`, `application.yml`, environment variables, Java system properties, command-line arguments, and additional configuration sources. The most common approach is declaring a class with `@ConfigurationProperties`, letting the framework create the object and bind values into it.

In certain advanced scenarios, the application **already has an object** created by code, a factory, a third-party library, or a specialized initialization routine. Instead of asking Binder to create a new object, we want to update the JavaBean properties of **that exact existing instance** based on data in `Environment`.

Spring Boot provides:

~~~java
Bindable.ofInstance(existingObject)
~~~

to describe the target for the binding operation. This method belongs to `org.springframework.boot.context.properties.bind.Bindable` and is used together with `Binder`.

General example:

~~~java
ClientOptions options = new ClientOptions();

Binder binder = Binder.get(environment);
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));
~~~

In the example, `app.client` is the **prefix** of the properties to look up; `options` is the **existing object**. With a JavaBean that has matching setters, Binder can apply the values of `app.client.*` onto that object.

This topic falls under **advanced Binder** because the application explicitly invokes the binding API rather than only letting the `@ConfigurationProperties` mechanism run automatically.

After this lesson, you should clearly distinguish:

1. How does `Bindable.ofInstance(existing)` differ from `Bindable.of(Type.class)`?
2. How is an object with existing default values updated when only a few properties are declared?
3. To what extent can it be used with JavaBeans, records, nested objects, collections, and third-party library objects?
4. When should you bind manually vs. let Spring Boot manage it automatically?
5. How do you control validation, type conversion errors, side effects, and lifecycle?
6. Why should binding into an existing instance not be treated as an automatic dynamic configuration refresh mechanism?

## 2. Three Core Components: `Binder`, `Bindable`, and `BindResult`

The related APIs reside in the package:

~~~java
org.springframework.boot.context.properties.bind
~~~

### 2.1. `Binder`

`Binder` is the object that performs binding from one or more `ConfigurationPropertySource`s into a typed target.

With a Spring Boot application that has created an appropriate `Environment`:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

Binder binder = Binder.get(environment);
~~~

`Binder.get(Environment)` creates a Binder backed by Environment and the configuration property sources attached to it. In a standard Spring Boot application context, this is the convenient path for manual binding.

Some key methods:

~~~java
binder.bind("app.client", Bindable.of(ClientOptions.class));
binder.bind("app.client", Bindable.ofInstance(existing));
binder.bindOrCreate("app.client", ClientOptions.class);
~~~

They **do not share the same contract**. Calling `bind` returns `BindResult<T>`; `bindOrCreate` provides the bound object or a new instance per API capabilities and conditions if there is no binding result.

### 2.2. `Bindable<T>`

`Bindable<T>` describes the target processed by Binder. It holds type information, associated annotations, and optionally an **existing value**.

Two common ways to create it:

~~~java
Bindable.of(ClientOptions.class);
Bindable.ofInstance(existing);
~~~

Differences:

- `Bindable.of(ClientOptions.class)`: describes a target by class, **without providing an existing object**.
- `Bindable.ofInstance(existing)`: describes the target by the runtime type of `existing` and specifies that **the existing value is that exact object**.

According to Spring Boot Javadoc, `ofInstance` creates a `Bindable` whose existing value equals the passed-in instance; **the instance must not be null**.

### 2.3. `BindResult<T>`

`Binder.bind(...)` returns `BindResult<T>`, used to check whether binding produced a result and retrieve the corresponding value:

~~~java
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));

if (result.isBound()) {
    ClientOptions bound = result.get();
    // Use bound object.
}
~~~

`isBound()` checks whether a binding result exists; `get()` should only be called when a result exists, otherwise an exception may be thrown for no value. The API also offers optional handling such as `orElse(...)` and `ifBound(...)` depending on the Spring Boot version.

**Do not confuse:** `BindResult` is the outcome of a binder operation, not an automatic validation report listing every invalid property, and receiving an object does not automatically guarantee business validity.

## 3. Minimal Example with a Mutable JavaBean

Suppose the application has a connection options object initialized with some defaults in Java:

~~~java
package com.example.demo.config;

import java.time.Duration;

public class ClientOptions {

    private String host = "localhost";
    private int port = 8080;
    private Duration timeout = Duration.ofSeconds(2);
    private boolean enabled = true;

    public ClientOptions() {
    }

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

In `application.properties`:

~~~properties
app.client.host=api.example.test
app.client.timeout=5s
~~~

Explicitly bind:

~~~java
import com.example.demo.config.ClientOptions;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.core.env.Environment;

public ClientOptions createOptions(Environment environment) {
    ClientOptions options = new ClientOptions();

    Binder.get(environment)
            .bind("app.client", Bindable.ofInstance(options));

    return options;
}
~~~

With a suitable bean and configuration source:

| Field | Initial value | Source property | Value after binding |
| --- | --- | --- | --- |
| `host` | `localhost` | `app.client.host=api.example.test` | `api.example.test` |
| `port` | `8080` | Undeclared | `8080` |
| `timeout` | `2s` | `app.client.timeout=5s` | `5s` |
| `enabled` | `true` | Undeclared | `true` |

Main point: **no need to replace the entire object when only some properties are supplied**. Binder can apply the present values onto the instance via appropriate setters; other fields can retain their existing defaults.

However, this **is not an arbitrary merge guarantee for every kind of object or collection**. Nested fields, lists, maps, and immutable types have their own binding rules.

### 3.1. The `ofInstance` method does not execute binding by itself

Common mistake:

~~~java
ClientOptions options = new ClientOptions();
Bindable.ofInstance(options); // Only creates the target descriptor object.
~~~

The second line **does not** read `Environment` and does not call setters. You must pass the `Bindable` into a Binder operation:

~~~java
Binder.get(environment)
        .bind("app.client", Bindable.ofInstance(options));
~~~

### 3.2. `ofInstance` is not an annotation

Do not write:

~~~java
@Bindable.ofInstance
public class ClientOptions {}
~~~

`ofInstance` is a **static factory method**, not an annotation. It returns a `Bindable<T>` used as a parameter to Binder.

## 4. Full Pattern in a Spring Boot Application

A clean approach is creating the object inside a `@Bean` factory method and binding **once** before returning the object to the application context.

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ClientOptionsConfiguration {

    @Bean
    ClientOptions clientOptions(Environment environment) {
        ClientOptions options = new ClientOptions();

        Binder binder = Binder.get(environment);
        binder.bind("app.client", Bindable.ofInstance(options));

        return options;
    }
}
~~~

A service can inject the bean:

~~~java
package com.example.demo.service;

import com.example.demo.config.ClientOptions;
import org.springframework.stereotype.Service;

@Service
public class ClientService {

    private final ClientOptions options;

    public ClientService(ClientOptions options) {
        this.options = options;
    }

    public String endpoint() {
        return options.getHost() + ":" + options.getPort();
    }
}
~~~

When `@Configuration` is scanned or imported into the context, Spring creates the `clientOptions` bean. Inside the factory method, the object is instantiated first, binder binds values into it, and the method returns the instance for the container to use.

### 4.1. Why bind before exposing the object for use?

Binding a mutable JavaBean can invoke multiple setters sequentially. During that window, the object can be in a **partially updated state**. Sharing an object mid-binding with other threads lets them see an inconsistent set of values.

Therefore, always:

1. Create the object locally.
2. Bind onto that object.
3. Verify necessary invariants/validation.
4. Only after success, publish it to the application context or consumers.

Do not use `Bindable.ofInstance` to mutate a configuration object currently accessed by multiple request threads without a proper concurrency design.

### 4.2. Watch out for mid-binding failures

If Binder has already called the setter for `host` and then fails while converting `timeout`, **the passed-in object may be left partially mutated**. Do not assume binding into an existing instance is a transaction capable of rollback.

In the factory method example, the object has not been published yet, so startup can fail and discard it. With an already-shared singleton, partial mutation is a far bigger risk.

## 5. Comparing `ofInstance` and `of(Class)`

### 5.1. Creating target by type

~~~java
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.of(ClientOptions.class));

ClientOptions options = result.orElse(new ClientOptions());
~~~

In this approach, the caller describes **the type to bind**, letting Binder instantiate the target according to the type's capabilities and binding mechanism. If no properties are bound, `BindResult` may be empty; the example uses `orElse` to provide a fallback object.

### 5.2. Binding into an existing instance

~~~java
ClientOptions options = new ClientOptions();

BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));
~~~

Here the object already exists before the `bind` call. JavaBean binding can update this object.

| Criterion | `Bindable.of(ClientOptions.class)` | `Bindable.ofInstance(options)` |
| --- | --- | --- |
| Target specified by | Java type | Already created object |
| Initial existing value | No | Yes |
| Who creates initial instance | Binder or corresponding target instantiation mechanism | Calling code |
| Suitable for records/immutable | Possible with proper value-object/constructor binding | Not suitable for "editing" immutable fields |
| Preserves object's own defaults | Depends on created object and binding logic | Typically keeps unprovided fields in JavaBean |
| Purpose | Bind an object from configuration | Apply configuration onto an existing object |
| Auto-registers Spring bean | No | No |

**Note:** both calls are manual Binder APIs. They do not replace Spring's bean registration mechanisms.

### 5.3. `Bindable.ofInstance` and `withExistingValue`

Javadoc also mentions:

~~~java
Bindable<ClientOptions> target =
        Bindable.of(ClientOptions.class)
                .withExistingValue(options);
~~~

This expresses a very similar intent to `Bindable.ofInstance(options)`: supplying an existing value for Binder to use in JavaBean binding.

The advantage of `withExistingValue` is starting from a `Bindable` that already carries type/annotation metadata and then attaching the existing value. `ofInstance` is concise when only the instance's own class is needed.

Per the API docs, `withExistingValue(...)` **implies JavaBean binding**; do not use it expecting constructor binding on an already constructed immutable object.

### 5.4. `withSuppliedValue` differs from existing value

`Bindable` also has `withSuppliedValue(Supplier<T>)`, allowing you to supply a supplier instead of passing an existing value directly.

This is an advanced capability for scenarios where you want Binder to obtain the target from a supplier. Do not equate a supplier with `ofInstance`:

- `ofInstance` already has the object and supplies that object as the existing value.
- `withSuppliedValue` describes how to obtain a target value when binder needs it.

Without a special need, `ofInstance` is usually easier to understand when the object genuinely already exists.

## 6. `Binder.get(Environment)` and Configuration Sources

In Spring Boot, `Environment` aggregates property sources in precedence order, including Config Data, environment variables, JVM system properties, and command-line arguments.

Example:

~~~properties
app.client.host=localhost
app.client.port=8080
app.client.timeout=2s
~~~

Running from command line:

~~~bash
java -jar app.jar \
  --app.client.host=api.production.example \
  --app.client.timeout=10s
~~~

In a standard Boot app, command-line arguments take precedence over configuration files, so Binder can apply `api.production.example` and `10s` onto `ClientOptions`.

Precedence is governed by `Environment` and how Boot prepares sources; **`ofInstance` does not alter source selection rules**.

### 6.1. Prefix is the starting point of binding

~~~java
binder.bind("app.client", Bindable.ofInstance(options));
~~~

Binder searches for properties under the `app.client` group, such as:

~~~text
app.client.host
app.client.port
app.client.timeout
app.client.enabled
~~~

If the actual configuration uses:

~~~properties
external.client.host=api.example.test
~~~

then prefix `app.client` does not match, and the `host` field can retain its default. One binding operation does not scan every property name in Environment.

### 6.2. Relaxed binding

The JavaBean property `connectTimeout` can match the canonical name `connect-timeout`:

~~~properties
app.client.connect-timeout=5s
~~~

With setter:

~~~java
public void setConnectTimeout(Duration timeout) {
    this.connectTimeout = timeout;
}
~~~

Binder can bind the property using Boot's relaxed binding rules. Write keys and prefixes in lowercase kebab-case so different configuration sources remain compatible.

### 6.3. `ofInstance` does not read YAML files directly

`Bindable.ofInstance` does not accept a file path. It accepts a **Java object**. Sources are provided by `Binder`.

If configuration comes from an `application.yml` file, Spring Boot Config Data already placed the file contents into `Environment` before Binder runs in appropriate phases. If you need to bind from an optional source not in Environment, construct a `ConfigurationPropertySource` or configure Binder accordingly; do not treat `ofInstance` as a YAML parser.

## 7. Writing Configuration in Properties and YAML

### 7.1. Properties format

~~~properties
app.client.host=api.example.test
app.client.port=8443
app.client.timeout=3s
app.client.enabled=true
~~~

With `ClientOptions` from earlier, Binder updates the corresponding fields via setters.

### 7.2. YAML format

~~~yaml
app:
  client:
    host: api.example.test
    port: 8443
    timeout: 3s
    enabled: true
~~~

Both representations have the same meaning after Spring Boot loads them as configuration properties.

The YAML parser handles nested indentation; Binder handles binding and conversion. Indentation and YAML syntax must be valid before reaching the binder step.

### 7.3. Environment variable format

The environment variable name matching a canonical key is usually:

~~~text
APP_CLIENT_HOST
APP_CLIENT_PORT
APP_CLIENT_TIMEOUT
APP_CLIENT_ENABLED
~~~

POSIX shell example:

~~~bash
export APP_CLIENT_HOST="api.internal.example"
export APP_CLIENT_PORT=8443
export APP_CLIENT_TIMEOUT=5s

java -jar app.jar
~~~

Depending on higher-precedence sources in Environment, these values can override file configurations. In Windows/PowerShell environments, syntax for setting environment variables differs.

### 7.4. Placeholders and type conversion

~~~properties
app.client.host=${APP_REMOTE_HOST:localhost}
app.client.timeout=${APP_REMOTE_TIMEOUT:2s}
~~~

Spring can resolve placeholders through `Environment` and Binder converts `2s` into `Duration`. If the supplied value is not a valid Duration string, binding can fail; `ofInstance` does not skip conversion.

## 8. Existing Values and Missing Properties

This is the behavior that makes `ofInstance` most useful with JavaBeans.

Example:

~~~java
ClientOptions options = new ClientOptions();
options.setHost("127.0.0.1");
options.setPort(9090);

binder.bind("app.client", Bindable.ofInstance(options));
~~~

Configuration source only contains:

~~~properties
app.client.timeout=8s
~~~

In standard JavaBean binding, you can expect:

~~~text
host    = 127.0.0.1
port    = 9090
timeout = 8s
enabled = true
~~~

Undeclared properties are not necessarily reset to `null` or Java defaults; fields already initialized on the object can retain their prior values.

### 8.1. Do not confuse "undeclared" with "declared empty"

~~~properties
app.client.host=
~~~

This is a property with an empty string value, not a missing key. Binder can invoke the setter with an empty string; the default `127.0.0.1` is replaced by `""`.

If host must have non-empty content, use validation or explicit invariants. Do not rely on object defaults to handle empty input.

### 8.2. Key present with wrong type

~~~properties
app.client.port=not-a-number
~~~

If the target has `int port`, conversion can fail. Do not treat Binder as a function that "tries to assign, and if invalid keeps the old default" by default.

For required configuration, failing fast is usually better than silently ignoring invalid data.

### 8.3. No properties matching the prefix

~~~properties
unrelated.value=hello
~~~

If `Environment` provides no properties matching `app.client.*`, `bind("app.client", ...)` can return an unbound `BindResult`. The `options` object still exists because **the caller created it**, not because Binder bound successfully.

Therefore:

~~~java
ClientOptions options = new ClientOptions();
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));

if (!result.isBound()) {
    // No binding result; choose appropriate handling.
}
~~~

Keeping defaults can be allowed if the configuration section is completely optional. If the configuration group is required, report a clear error when no properties are found.

## 9. `BindResult`: Checking the Result Without Losing the Existing Instance

Key APIs:

~~~java
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));

boolean bound = result.isBound();
~~~

If you need the value inside `BindResult`:

~~~java
if (result.isBound()) {
    ClientOptions effective = result.get();
}
~~~

If you only care about the passed-in instance and accept defaults when no properties exist, you can write concisely:

~~~java
ClientOptions options = new ClientOptions();
binder.bind("app.client", Bindable.ofInstance(options));
return options;
~~~

**Note:** do not unconditionally call `result.get()` if the prefix may be unconfigured. If using `orElse(options)`, understand it as a binding-result-level fallback, not another rebinding pass.

### 9.1. `bindOrCreate` does not mean "apply additional config onto a shared object"

`Binder.bindOrCreate(...)` has the contract to bind or create an object by type if binding yields no result. It is useful when you always want an object, yet **differs from asking to mutate a specific instance and manage that instance's lifecycle**.

When the goal is configuring an object you already created yourself, express that intent with `Bindable.ofInstance(object)` and handle the result appropriately.

## 10. Use Case: Configuring Third-Party Library Objects

An SDK may provide a mutable configuration class, for example:

~~~java
package com.vendor.sdk;

import java.time.Duration;

public class VendorClientOptions {

    private String endpoint = "http://localhost:9000";
    private Duration timeout = Duration.ofSeconds(3);
    private int maxRetries = 1;

    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public Duration getTimeout() { return timeout; }
    public void setTimeout(Duration timeout) { this.timeout = timeout; }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Suppose you do not own the library source code and cannot add annotations to this class. The application wants to apply configuration:

~~~yaml
vendor:
  client:
    endpoint: "https://vendor.example.test/v1"
    timeout: 4s
    max-retries: 3
~~~

You can write a factory:

~~~java
import com.vendor.sdk.VendorClientOptions;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class VendorClientConfiguration {

    @Bean
    VendorClientOptions vendorClientOptions(Environment environment) {
        VendorClientOptions options = new VendorClientOptions();

        Binder.get(environment)
                .bind("vendor.client", Bindable.ofInstance(options));

        return options;
    }
}
~~~

The benefit is avoiding an intermediate wrapper class just to copy each property and call setters manually.

### 10.1. A simpler option: `@Bean` + `@ConfigurationProperties`

If manual Binder control is not needed, Spring Boot also supports placing `@ConfigurationProperties` on a `@Bean` method returning a JavaBean:

~~~java
import com.vendor.sdk.VendorClientOptions;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class VendorClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.client")
    VendorClientOptions vendorClientOptions() {
        return new VendorClientOptions();
    }
}
~~~

In this model, Boot manages the binding step. This is usually the **cleaner** choice when the only need is configuring a factory-created bean.

Only use `Binder + Bindable.ofInstance` if you need special control such as dynamic prefix selection, binding in a dedicated processing phase, custom sources, or explicit binding result handling.

### 10.2. Do not use both on the same bean simultaneously

**Avoid** placing `@ConfigurationProperties` on `@Bean` while also calling `binder.bind(..., Bindable.ofInstance(bean))` just to "be sure."

That can cause double binding, setters with side effects running twice, or configuration applied in a confusing order. Pick one party responsible for binding each object.

## 11. JavaBean Binding and Setters Are Central

Per the Spring Boot API, supplying an existing value via `ofInstance` or `withExistingValue` directs Binder toward **JavaBean binding**. This requires the target to expose properties that Binder can update.

Suitable example:

~~~java
public class CacheOptions {
    private String region = "local";

    public String getRegion() { return region; }
    public void setRegion(String region) { this.region = region; }
}
~~~

For scalar fields like `String`/`int`/`Duration`, appropriate public setters are the simplest and clearest path.

### 11.1. A parameterized constructor does not automatically become constructor binding

Example:

~~~java
public class ImmutableOptions {
    private final String endpoint;

    public ImmutableOptions(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getEndpoint() {
        return endpoint;
    }
}
~~~

This snippet:

~~~java
ImmutableOptions existing =
        new ImmutableOptions("https://default.example.test");

binder.bind("app.client", Bindable.ofInstance(existing));
~~~

will not change `existing.endpoint`. The field is `final` with no setter; `ofInstance` is not a mechanism that re-invokes the constructor of an already instantiated object.

If you want immutable binding, ask Binder to create the object via appropriate value-object/constructor binding, such as `Bindable.of(ImmutableOptions.class)` when supported by the model and Spring Boot version, or use `@ConfigurationProperties` with a properly registered record.

### 11.2. Records are unsuitable as existing mutable targets

~~~java
public record ClientRecord(String host, int port) {}
~~~

Records are designed to be immutable. `Bindable.ofInstance(new ClientRecord(...))` is not a way to "change host while keeping port" in an already created record.

If a record is needed:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientRecord(String host, int port) {}
~~~

and register it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, so Boot performs constructor binding appropriately.

**Selection rule:** need to keep and update an existing mutable JavaBean → `ofInstance`. Need an immutable object built from configuration → constructor binding, do not try to mutate a record.

## 12. Nested JavaBeans: Pre-Existing Child Objects

A useful scenario is a parent object holding an already initialized mutable nested object:

~~~java
import java.time.Duration;

public class GatewayOptions {

    private final RetryOptions retry = new RetryOptions();
    private String host = "localhost";

    public RetryOptions getRetry() {
        return retry;
    }

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public static class RetryOptions {
        private int maxAttempts = 2;
        private Duration delay = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getDelay() {
            return delay;
        }

        public void setDelay(Duration delay) {
            this.delay = delay;
        }
    }
}
~~~

Configuration:

~~~properties
gateway.host=api.example.test
gateway.retry.max-attempts=5
gateway.retry.delay=500ms
~~~

Bind:

~~~java
GatewayOptions options = new GatewayOptions();

binder.bind("gateway", Bindable.ofInstance(options));
~~~

In a compatible JavaBean binding model, Binder can navigate into the pre-initialized `retry` object and call the nested bean's setters. Replacing `retry` is unnecessary if the child object can be bound via its getter.

### 12.1. Distinguish nested mutable from nested immutable

If the nested object is a record or a class where all fields are `final`, binder cannot mutate fields like a mutable JavaBean. You may need a setter on the parent to replace the nested object, or switch the whole structure to constructor binding.

Do not claim that a `final` field on a parent always prevents nested properties from binding: the parent can hold a **final reference to a mutable nested object** and Binder can update that child object.

### 12.2. Risk of sharing nested instances

If multiple services already hold references to `options.getRetry()`, calling binder on the parent after services start using it can mutate the nested object without synchronization. Therefore, still bind before publishing the object.

## 13. List, Set, and Map: Do Not Reason Like Scalars

For scalars such as `host` and `timeout`, the idea of "keep old default when key is missing" is intuitive. For collections, greater care is needed.

Example:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PoolOptions {
    private List<String> endpoints = new ArrayList<>(
            List.of("http://localhost:8080")
    );

    public List<String> getEndpoints() {
        return endpoints;
    }

    public void setEndpoints(List<String> endpoints) {
        this.endpoints = endpoints;
    }
}
~~~

Configuration:

~~~properties
pool.endpoints[0]=https://primary.example.test
pool.endpoints[1]=https://backup.example.test
~~~

Bind:

~~~java
PoolOptions options = new PoolOptions();
binder.bind("pool", Bindable.ofInstance(options));
~~~

The expected result is a list containing the two new configured endpoints. However, **do not promise that Binder will append onto the pre-initialized list**. Depending on the target, collection implementation, and binding mode, the collection may be recreated/replaced or updated according to Binder rules.

### 13.1. Lists from multiple property sources are usually replaced

Spring Boot has an important rule: when a `List` is declared in multiple configuration sources of different precedence, Binder normally selects **the list from the higher-precedence source**, rather than merging elements from all sources.

Base file example:

~~~yaml
pool:
  endpoints:
    - https://a.example.test
    - https://b.example.test
~~~

`prod` profile file:

~~~yaml
pool:
  endpoints:
    - https://prod.example.test
~~~

When the `prod` profile is active and this file wins, the effective list is typically **one element** `https://prod.example.test`, not three elements.

`ofInstance` does not turn that mechanism into a special list merge. Do not use it to vaguely "patch" individual indices.

### 13.2. Map behaves differently from List

For `Map<String, ClientOptions>`, Binder can combine keys from multiple sources and apply precedence per shared key according to Map rules. Yet when binding a Map into an existing instance, clearly define merge/replace expectations and test with real data.

If the system needs **intentional merging**, especially with complex mutable objects, write an explicit tested merge algorithm rather than relying on assumptions about an `ofInstance` operation.

### 13.3. Set does not guarantee order

If a target has `Set<String>`, do not write logic depending on Set iteration order. If endpoint order matters, use `List`.

Set also collapses duplicate entries according to `equals`/`hashCode`. If duplicate entries represent an operational error to catch, bind into a List and validate duplicates before converting to a Set.

### 13.4. Default collection values

If an object has a default list and the source provides no list keys, the list can remain intact in the JavaBean. If the source provides a new list, never assume it always appends onto the default list.

Choose the policy explicitly: **default list when absent**, **replacement when present**, or **custom merge**. Only the last policy requires explicit merge code.

## 14. `Bindable.ofInstance` Does Not Mean Hot Reload

A frequent question: "If the object already exists, can I call `ofInstance` periodically to auto-update configuration?"

At the API level, you can perform additional binder calls on the same object. However, **Spring Boot does not do that automatically just because you used `ofInstance`**.

Risks of runtime rebinding:

- Setters are called again on an already-published object.
- New fields may be updated before other fields.
- A binding error can leave the object half-updated.
- Clients constructed from old settings will not necessarily reinitialize themselves.
- Other threads can observe inconsistent data.
- A property deleted from a source does not necessarily clear or reset the old field the way you expect.

If runtime reconfiguration is required, design a dedicated flow: bind into a **temporary object**, validate it completely, then publish the new snapshot via a thread-safe mechanism. For mostly static configuration, restarting/redeploying is usually simpler.

### 14.1. Whole-snapshot replacement model

Conceptual example:

~~~java
public final class SettingsHolder {
    private volatile ClientOptions current;

    public SettingsHolder(ClientOptions initial) {
        this.current = initial;
    }

    public ClientOptions get() {
        return current;
    }

    public void replace(ClientOptions next) {
        this.current = next;
    }
}
~~~

This only illustrates swapping the **reference**. `ClientOptions` in the earlier example is still mutable; to ensure snapshots are not modified after publication, design proper immutable views/copies, manage resource lifecycles, and synchronize dependencies created from old settings.

**Do not adopt this pattern merely because you want to use Bindable.ofInstance.** It is its own architectural problem.

## 15. Choosing an API When Only Manual Binding Is Needed

| Goal | Typical suitable choice |
| --- | --- |
| Spring manages a `@ConfigurationProperties` class | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Spring instantiates a JavaBean via `@Component` and binds | `@Component` + `@ConfigurationProperties` |
| Spring creates a JavaBean from `@Bean` and binds automatically | `@Bean` + `@ConfigurationProperties` |
| Code already holds a mutable object and needs config applied | `Binder.bind(prefix, Bindable.ofInstance(object))` |
| Only need target by type | `Binder.bind(prefix, Bindable.of(Type.class))` |
| Want to bind or create a new object if needed | `Binder.bindOrCreate(...)` |
| Target is an immutable record | Constructor/value-object binding, do not mutate with `ofInstance` |
| Want to bind a plain list with element type | `Bindable.listOf(Element.class)` when appropriate |
| Want to bind a map with explicit key/value types | `Bindable.mapOf(Key.class, Value.class)` when appropriate |
| Want flexible configuration from custom sources | Create `Binder` with appropriate `ConfigurationPropertySource` |

**Principle:** if Spring Boot's automatic mechanism already satisfies the requirement, do not call Binder manually just to redo the exact same work.

## 16. Manual Binder and Bean Validation

With Boot-managed `@ConfigurationProperties`, you can use `@Validated` and Jakarta Bean Validation to check fields. Yet when manually calling:

~~~java
binder.bind("app.client", Bindable.ofInstance(options));
~~~

do not assume **all application validations have been automatically activated identically to a framework-managed `@ConfigurationProperties` bean**.

Manual binding lets you pass an appropriate `BindHandler`, and the application can also explicitly validate the object with a Bean Validation provider after binding. If data is mandatory, design a clear verification step.

### 16.1. Post-bind configuration check example

~~~java
import java.time.Duration;

public static void validateOptions(ClientOptions options) {
    if (options.getHost() == null || options.getHost().isBlank()) {
        throw new IllegalStateException(
                "app.client.host must be configured");
    }

    if (options.getPort() < 1 || options.getPort() > 65535) {
        throw new IllegalStateException(
                "app.client.port must be between 1 and 65535");
    }

    Duration timeout = options.getTimeout();
    if (timeout == null || timeout.isZero() || timeout.isNegative()) {
        throw new IllegalStateException(
                "app.client.timeout must be a positive duration");
    }
}
~~~

Usage:

~~~java
ClientOptions options = new ClientOptions();
binder.bind("app.client", Bindable.ofInstance(options));
validateOptions(options);
~~~

The example uses fixed messages about the **configuration contract**, avoiding printing raw hostnames, passwords, or rejected values.

### 16.2. Bean Validation for complex configurations

For classes annotated with `@NotBlank`, `@Min`, and `@Max`, you can explicitly use `jakarta.validation.Validator` to validate the instance after Binder finishes. A Bean Validation provider is needed on the classpath, typically via `spring-boot-starter-validation`.

When using custom `BindHandler`s to check or alter behavior, inspect the API of your actual Spring Boot version. Do not add arbitrary handlers without understanding when they are called.

### 16.3. Do not treat binding as security validation

A syntactically valid URI may still point to a disallowed internal network, a password string may be expired, a `Resource` may point to a sensitive file, and a timeout may exceed operational budgets even though it parses as a `Duration`.

Domain/security checks are an additional responsibility and do not arise automatically from type conversion.

## 17. Handling Binding Errors and Avoiding Half-Updated State

A configuration error can occur when:

- `app.client.port` is not an integer.
- `app.client.timeout` cannot be parsed as `Duration`.
- The JavaBean lacks a matching setter.
- The prefix does not match sources.
- A nested object cannot bind due to an immutable type.
- A custom converter throws an exception.
- A custom `BindHandler` rejects a value.

Example:

~~~properties
app.client.port=oops
~~~

Binder may report `BindException` or conversion-related exceptions. Do not swallow the error and continue using an object that has already been partially mutated.

### 17.1. Safe pattern inside a factory

~~~java
@Bean
ClientOptions clientOptions(Environment environment) {
    ClientOptions candidate = new ClientOptions();

    Binder.get(environment).bind(
            "app.client",
            Bindable.ofInstance(candidate)
    );

    validateOptions(candidate);
    return candidate;
}
~~~

If binding or validation fails, the factory does not return the object to the container. The application context may fail to start; this is usually the right choice for mandatory configuration.

### 17.2. Do not enable ignoreErrors to mask bad data

Some configuration properties mechanisms have options to ignore binding errors. For mandatory configuration, hiding errors can leave objects retaining defaults in places you do not expect.

Only allow fallbacks when a clear policy exists and missing, wrong-type, and conflicting configurations have been tested. Never let `ofInstance` silently turn data errors into quiet misbehavior.

### 17.3. Information safety in error messages

Configuration may contain API keys, passwords, or URIs with credentials. Do not print `options.toString()`, the entire `Environment`, or rejected raw values for debugging.

Good messages state safe keys/requirements, for example:

~~~text
[CFG-201] app.client.timeout must be a valid positive duration.
Action: correct the deployment setting and restart.
~~~

Avoid printing raw input strings if they might contain secrets. This is especially important when exceptions originate from converters or third-party libraries.

## 18. `BindHandler` in Advanced Scenarios

`Binder.bind` has an overload accepting `BindHandler`:

~~~java
binder.bind("app.client",
            Bindable.ofInstance(options),
            bindHandler);
~~~

`BindHandler` is an extension point for stages of binding, such as on start, on success, on failure, or on finish. Spring Boot provides several handlers for specific cases; custom handlers can also be written for special requirements.

Important points:

- `BindHandler` is not needed to use `ofInstance` in basic examples.
- A handler does not automatically make an immutable JavaBean updatable.
- If a handler customizes errors or results, test carefully because it can alter general binding behavior.
- Do not log full `ConfigurationProperty` entries or input values in handlers when they contain sensitive data.
- A validation handler does not give existing-instance mutation transactional rollback.

### 18.1. When should you use a handler?

Some genuine needs:

- Checking unused properties within a critical configuration scope.
- Enforcing special validation rules during binding.
- Attaching allowed origin info to diagnostics.
- Rejecting a forbidden property group per policy.

If you only want to ensure host is non-blank or port is valid, post-bind validation is usually easier to read than writing a complex handler.

## 19. Creating a Custom `Binder` from Specific Sources

`Binder.get(Environment)` is convenient inside a Spring Boot context. Yet the `Binder` API also has constructors taking one or more `ConfigurationPropertySource` instances.

This is useful when the application wants to bind an object from **a restricted set of chosen sources** instead of the entire Environment.

Conceptual flow:

~~~text
Map / custom PropertySource / ConfigurationPropertySource
                     |
                     v
                   Binder
                     |
                     v
           Bindable.ofInstance(existing)
                     |
                     v
               Existing JavaBean
~~~

In Java, utilities under `org.springframework.boot.context.properties.source` can convert a `PropertySource` into a compatible `ConfigurationPropertySource` and pass it to Binder.

### 19.1. Why must you pay attention to source precedence?

If Binder receives multiple sources, their order determines which value wins when the same key appears multiple times. A custom source list does not automatically share the application context's precedence policy.

With a standard Spring Boot Environment, using `Binder.get(environment)` avoids manually assembling sources in the wrong order. Only build a separate Binder when there is a clear requirement and corresponding tests.

### 19.2. Do not confuse Binder with the Config Data loader

`Binder` focuses on **mapping properties → Java objects**. Loading multi-document YAML, selecting profiles, and importing Config Trees are handled by Config Data in other phases.

If you read a YAML file manually outside Boot's mechanism, you need an appropriate parser/loader before feeding data into Binder. `Bindable.ofInstance` does not read file paths, detect profiles, or import configs.

## 20. Generic Types and Runtime Type Issues

`Bindable.ofInstance(existing)` infers the type from the existing object. This is convenient for a concrete JavaBean:

~~~java
ClientOptions options = new ClientOptions();
Bindable<ClientOptions> target = Bindable.ofInstance(options);
~~~

For collections and complex generic types, Java type erasure means an `ArrayList<String>` instance does not carry enough element-type information the way an explicit `ResolvableType` does.

If the goal is binding a standalone collection, use the collection static factories:

~~~java
Bindable<List<String>> target = Bindable.listOf(String.class);
~~~

Or declare the target using a `ResolvableType` with full generic metadata when needed. Do not assume `ofInstance(new ArrayList<>())` always knows elements must be `String` when no generic declaration context exists.

### 20.1. Why does generic metadata matter?

Suppose the configuration is:

~~~properties
app.retry.delays[0]=100ms
app.retry.delays[1]=2s
~~~

If the target is `List<Duration>`, Binder needs to know the element type is `Duration` to convert the string `100ms` properly. If it only knows the runtime class `ArrayList`, the element type is not fully represented.

When `List<Duration> delays` is a property field on a JavaBean, metadata from the field/setter usually supplies the generic type information. Hence, binding into **a JavaBean containing typed collection fields** is generally safer than binding directly into a raw collection instance.

## 21. Testing with `@SpringBootTest`

Suppose the project has a Spring Boot application class and appropriate test dependencies.

~~~java
import com.example.demo.config.ClientOptions;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "app.client.host=test.example.test",
        "app.client.timeout=750ms"
})
class ExistingInstanceBindingTest {

    @Autowired
    Environment environment;

    @Test
    void bindsExistingJavaBean() {
        ClientOptions options = new ClientOptions();

        BindResult<ClientOptions> result =
                Binder.get(environment).bind(
                        "app.client",
                        Bindable.ofInstance(options)
                );

        assertTrue(result.isBound());
        assertEquals("test.example.test", options.getHost());
        assertEquals(Duration.ofMillis(750), options.getTimeout());
        assertEquals(8080, options.getPort()); // Retains default.
    }
}
~~~

This test verifies the core behavior: Binder sees the properties in the test Environment and applies them onto the pre-constructed instance.

If you need to assert object identity on the JavaBean binding path, you can verify the returned result with `assertSame(options, result.get())` in cases where the API/target is confirmed to support that behavior.

### 21.1. Testing when no properties exist under the prefix

To test `BindResult.isBound()` with no source, create a test Environment without `app.client.*` keys or use a dedicated unconfigured prefix.

Do not assume that omitting `app.client.host` in the test annotation guarantees all other sources lack that key; application files and system properties may still be loaded.

### 21.2. Testing mistyped data

Configuration:

~~~properties
app.client.timeout=invalid-duration
~~~

Expect binding/conversion to report an error instead of retaining the `2s` default. If the application intentionally allows fallbacks, define and verify that policy explicitly.

### 21.3. Testing empty values

~~~properties
app.client.host=
~~~

The expectation is not "keep localhost," because the key exists. Write validation to verify blank hosts are rejected.

### 21.4. Testing nested objects and collections

For nested mutable JavaBeans, test the child object's getters/setters. For Lists/Maps, test replacement/merge behavior across property sources of varying precedence; do not test only a single simple source.

### 21.5. Do not use real credentials in tests

If the target contains passwords or API keys, use fake canary values and verify logs/errors do not expose them. Never paste production secrets into test sources or stdout.

## 22. Common Misconceptions

### 22.1. "`ofInstance` creates a new object by itself"

No. It takes an **already created** object and builds a `Bindable` holding the existing value. Whether a new instance exists depends on the API and how you invoke binder; `ofInstance` itself does not instantiate a new target.

### 22.2. "Just calling `ofInstance(options)` is enough"

No. You must pass the target into `Binder.bind` or a corresponding API. The static factory only describes the target.

### 22.3. "`ofInstance` can be used to modify a record"

Do not do this. It implies existing-value/JavaBean binding; records have no mutable setters. If you want a new record from configuration, choose constructor binding.

### 22.4. "Undeclared properties always wipe default fields"

With an existing JavaBean object, fields without new properties can generally keep their assigned defaults. However, for collections/nested objects test separately; do not claim every field kind shares the exact same behavior.

### 22.5. "A new List appends onto the old List"

Do not assume this. Binder follows List replacement rules when higher-precedence sources exist. If you want append/merge, define that mechanism explicitly in code.

### 22.6. "Binding into an existing object is always concurrency-safe"

No. Setters may be called multiple times with no atomic update across fields. Bind before publishing or use a dedicated snapshot replacement design.

### 22.7. "Having a `BindResult` means all values are validated"

No. Binding and validation are two separate responsibilities. Especially with manual APIs, design validation explicitly.

### 22.8. "`ofInstance` gives environment variables the highest priority"

No. Prefixes, `PropertySource` ordering, Config Data, and the environment determine source values; `ofInstance` only describes the target.

### 22.9. "Any arbitrary object can be bound without setters"

No. With existing values, JavaBean binding requires updatable members or nested objects. Immutable objects do not become mutable automatically.

### 22.10. "Successful type conversion means configuration is ready to use"

No. A valid `URI` might lack a host, a timeout might be negative, a Resource might be unreadable. Validation and resource checks remain necessary.

## 23. Troubleshooting Steps When Binding Does Not Update the Object

If you call Binder and see no changes:

1. **Check whether `binder.bind` was actually called.** `ofInstance` alone does nothing.
2. **Check the prefix.** Does `"app.client"` match the source keys `app.client.*`?
3. **Check Environment.** Was it prepared by Spring Boot with the right profile and Config Data?
4. **Check the winning source.** Did external files, env vars, system properties, or CLI args override the expected value?
5. **Check `BindResult.isBound()`.** If false, do not call `get()` and do not claim it bound.
6. **Check the JavaBean target.** Does it have necessary getters/setters, convertible types, and proper nested object structure?
7. **Check whether the target is a record or immutable.** `ofInstance` does not modify final fields.
8. **Check empty vs. missing source values.** Two different states can yield different outcomes.
9. **Check conversion.** `Duration`, `URI`, numbers, and enums need valid input.
10. **Check collections.** Was the list replaced by a higher-precedence source? Was the generic type preserved?
11. **Check for a second automatic binding.** `@Bean` with `@ConfigurationProperties` or `@Component` can cause the object to be bound twice.
12. **Check usage timing.** Was the object published before binding finished?
13. **Check whether setters have side effects.** Binding is not meant to make network calls or mutate external systems inside setters.
14. **Check validation.** An object that looks updated may still violate invariants.
15. **Diagnose safely.** Do not log the full object if it holds credentials; only log allowed key names/error categories.

With Spring Boot Actuator, `/actuator/env` and `/actuator/configprops` can help inspect property sources and registered beans, though they must be secured and sensitive data masked. An object manually bound via API **will not necessarily appear as a framework-managed configuration properties bean** unless registered through that mechanism.

## 24. Checklist Before Using `Bindable.ofInstance`

- [ ] Object is already instantiated and **non-null**.
- [ ] Object is a mutable JavaBean or has a suitable bindable structure.
- [ ] Binder was created from the right `Environment`/`ConfigurationPropertySource`.
- [ ] Prefix is chosen accurately and uses canonical configuration naming where appropriate.
- [ ] Precedence rules of configuration sources are understood.
- [ ] Not using `ofInstance` to mutate records or immutable value objects.
- [ ] Existing values/defaults are clearly designed when keys are missing.
- [ ] Missing properties, empty strings, and mistyped values are distinguished.
- [ ] Nested JavaBeans have getters/setters or suitable update mechanisms.
- [ ] Collections are not assumed to append/merge outside contract.
- [ ] Not binding raw generic collections directly without element metadata.
- [ ] Calling Binder **before publishing** the object across threads.
- [ ] Rules exist for handling an unbound `BindResult`.
- [ ] Binding errors are not swallowed, and half-updated objects are never used.
- [ ] Post-manual-bind validation or invariants exist for critical configurations.
- [ ] Manual binding does not duplicate automatic `@ConfigurationProperties` binding.
- [ ] Tests cover configured values, absent values, and mistyped values.
- [ ] No secrets leaked in logs, exceptions, or test data.
- [ ] Not treating `ofInstance` as an automatic configuration refresh mechanism.
- [ ] When only binding a single `@Bean`, considered the simpler `@Bean` + `@ConfigurationProperties`.

## 25. Practice Exercises

### Exercise 1: Preserving defaults when overriding only timeout

A JavaBean has:

~~~java
private String host = "localhost";
private Duration timeout = Duration.ofSeconds(2);
~~~

Configuration:

~~~properties
app.client.timeout=5s
~~~

Explain why the object can retain `host=localhost` while timeout changes to `5s` after `binder.bind("app.client", Bindable.ofInstance(options))`. If the source also includes `app.client.host=`, what differs?

**Hint:** "no key" differs from "key with empty string."

### Exercise 2: Distinguishing records and JavaBeans

Two classes:

~~~java
public record ImmutableClient(String host, int port) {}
~~~

and:

~~~java
public class MutableClient {
    private String host;
    private int port;
    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }
    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

If the requirement is updating an **existing object**, which class do you choose and why? If the requirement is creating a **fresh immutable snapshot** from configuration, which mechanism should you use?

### Exercise 3: Avoiding double binding

A `@Bean` method has `@ConfigurationProperties(prefix="vendor.client")`. A developer also calls `Binder.get(environment).bind("vendor.client", Bindable.ofInstance(options))` inside the method.

Explain why this is usually redundant and can cause side effects; choose one unified registration/binding approach.

### Exercise 4: Handling no binding result

Suppose all `app.client.*` keys are undeclared. Decide whether to:

- use the object with initialized defaults;
- fail with a missing configuration error;
- or switch to `Binder.bindOrCreate` as needed.

**There is no single answer valid for every application**; the decision must follow the configuration contract.

## 26. Conclusion

`Bindable.ofInstance(existing)` is a small but important tool in **advanced Spring Boot Binder**: it lets code **specify an existing object** as the target when calling `Binder.bind`. With mutable JavaBeans, Binder can apply properties from compatible configuration sources onto that object, leveraging defaults, setters, nested binding, conversion, and relaxed binding.

However:

- `ofInstance` **does not bind by itself** and **does not create objects by itself**.
- It targets **existing value/JavaBean binding**, not mutating immutable records.
- Without matching properties, `BindResult` can be unbound.
- Lists/Maps and nested objects follow specific rules; do not assume arbitrary merging.
- Binding into a mutable instance **is not atomic**, does not guarantee rollback, and does not auto-refresh at runtime.
- Validation, safe logging, and lifecycle remain the application's responsibility.

When you only need a normal configuration bean, automatic `@ConfigurationProperties` or an annotated `@Bean` is the simpler choice. Use `Bindable.ofInstance` when **direct control over an existing target** adds real value, and bind before the object enters service.

### References

- [Spring Boot API — Bindable, ofInstance, withExistingValue](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Bindable.html)
- [Spring Boot API — Binder, bind, bindOrCreate, and get(Environment)](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot API — BindResult](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/BindResult.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Team — Property Binding in Spring Boot 2.0](https://spring.io/blog/2018/03/28/property-binding-in-spring-boot-2-0/)
