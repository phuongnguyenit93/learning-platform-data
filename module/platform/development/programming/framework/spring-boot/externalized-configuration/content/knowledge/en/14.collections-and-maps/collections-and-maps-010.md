# Mutable vs. Immutable Collections and Getter or Setter Requirements in Spring Boot `@ConfigurationProperties`

## Goal

When application configuration consists only of an integer or a string, using Spring Boot **@ConfigurationProperties** is straightforward: the property name is resolved, the value is converted, and it is assigned to a Java field. With **List**, **Set**, and **Map**, binding is more involved because the binder must **create or update an entire collection**, sometimes instantiating nested elements too.

One crucial difference is that the following two Java designs are not equivalent:

~~~java
// Getter-only, mutable list
private final List<String> hosts = new ArrayList<>();
public List<String> getHosts() { return hosts; }
~~~

~~~java
// Getter-only, immutable list
private final List<String> hosts = List.of("localhost");
public List<String> getHosts() { return hosts; }
~~~

In the first case, JavaBean-style binding can update the pre-existing collection. In the second case, the object returned by **List.of(...)** does not support mutating operations such as `add`, `clear`, or `set`. You cannot assume "having a getter means Spring can bind it" merely because both return **List<String>**.

This lesson clarifies:

- How **mutable** and **immutable** collections differ, especially for getter-only properties.
- When JavaBean binding requires a setter versus when a getter exposing a pre-initialized collection can suffice.
- Why **record + constructor binding** is the natural choice when immutable configuration state is desired.
- How to represent **List**, **Set**, **Map**, and object elements in YAML, `.properties`, and environment variables.
- The difference between **binding a collection** and **overriding a collection across multiple PropertySources**.
- How to handle defaults, empty collections, validation, and binding errors.
- How to test mutable/immutable designs to prevent unexpected runtime behavior.

The context is **Spring Boot externalized configuration**, with Java examples written in Spring Boot 3.x style. When working on another version, especially with constructor binding, verify the exact APIs of your target version.

## 1. What Are Collections in Configuration?

A collection can describe:

- An ordered list of endpoints to try in sequence.
- A list of allowed CORS domains.
- Notification channels or the set of enabled features.
- A routing Map keyed by region/tenant name.
- A list of workers, each with multiple fields.
- A Map of settings per transaction type.

Example YAML:

~~~yaml
app:
  gateway:
    hosts:
      - api-a.example.test
      - api-b.example.test
    allowed-methods:
      - GET
      - POST
    labels:
      owner: platform
      region: asia
~~~

There are three kinds:

| Configuration path | Expected Java type | Meaning |
| --- | --- | --- |
| app.gateway.hosts | List<String> | Ordered list |
| app.gateway.allowed-methods | Set<String> or List<String> | Set of methods |
| app.gateway.labels | Map<String, String> | Key-based lookup table |

The same YAML can be bound using a JavaBean with getters/setters or a constructor-bound record. However, requirements around pre-initialized collections and mutability differ between those two models.

### 1.1. Mutable Does Not Mean Contents Auto-Update at Runtime

A **mutable collection** allows code to invoke state-changing methods such as `add`, `remove`, or `put`. It does not mean Spring Boot automatically synchronizes the collection when an environment variable changes after startup.

An **immutable collection** forbids modifications through the collection API. It can be constructed from binder data at startup and consumed read-only by services. These are two orthogonal characteristics:

~~~text
Mutable / Immutable
    -> Can the Java object's state be modified?

Startup binding / Dynamic refresh
    -> Does the application have a mechanism to reload config at runtime?
~~~

Do not confuse the two concepts.

## 2. JavaBean Binding and Constructor Binding

In Spring Boot, two common ways to bind **@ConfigurationProperties** are:

**JavaBean binding:** the binder instantiates an object, uses setters for regular properties, and in certain scenarios accesses a pre-created collection via its getter to populate contents.

**Constructor binding:** the binder collects and converts values, then constructs the object via its constructor. For records or classes with `final` fields only, this is typically the right path to immutable configuration.

Diagram:

~~~text
Config Data / Environment
            |
            v
    Configuration Binder
            |
            +-- JavaBean binding
            |      new Properties()
            |      setServers(...), setLabels(...)
            |      or mutate pre-initialized collection
            |
            +-- Constructor binding
                   bind List, Map, nested values
                   new Properties(servers, labels)
                   -> constructed configuration object
~~~

### 2.1. Why Are Getters/Setters a JavaBean-Specific Concern?

A typical JavaBean has a field, a getter, and a setter:

~~~java
private List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return hosts;
}

public void setHosts(List<String> hosts) {
    this.hosts = hosts;
}
~~~

A setter allows replacing the existing collection reference with a newly bound collection. Without a setter, if the getter returns a pre-initialized mutable collection, the binder can work with that collection as supported by JavaBean binding.

By contrast, constructor binding does not need setters: the collection value is passed into the constructor as a parameter. That aligns far better with an immutable model.

## 3. JavaBean Example with Full Getters and Setters

Suppose YAML is:

~~~yaml
app:
  routing:
    hosts:
      - primary.example.test
      - backup.example.test
    labels:
      environment: production
      owner: platform
~~~

A JavaBean:

~~~java
package example.config;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.routing")
public class RoutingProperties {

    private List<String> hosts = new ArrayList<>();
    private Map<String, String> labels = new LinkedHashMap<>();

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        this.hosts = hosts;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }
}
~~~

Paths read by the binder:

~~~text
app.routing.hosts[0]           -> primary.example.test
app.routing.hosts[1]           -> backup.example.test
app.routing.labels.environment -> production
app.routing.labels.owner       -> platform
~~~

With a properly registered bean, `RoutingProperties` receives the two-host list and two-entry map.

**Role of setters:** allow Spring to assign a new reference for `hosts` and `labels`. The declared field types are the **List** and **Map** interfaces; exposing `ArrayList` or `LinkedHashMap` as the public type is unnecessary.

### 3.1. Registering the Configuration Bean

One way to register:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Place `RoutingProperties` inside a scanned package, or use **@EnableConfigurationProperties(RoutingProperties.class)** on a `@Configuration` class.

Without bean registration, even if getters/setters and YAML are valid, Spring will report `RoutingProperties` missing when a service tries to inject it. That is a bean registration error, not a mutability bug.

## 4. Pre-Initialized Collections and Getter-Only Properties

In JavaBean binding, Spring Boot supports a **pre-initialized, still-mutable collection/map exposed via a getter**, so a setter is not always required.

For example:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private final List<String> hosts = new ArrayList<>();
    private final Map<String, String> labels = new LinkedHashMap<>();

    public List<String> getHosts() {
        return hosts;
    }

    public Map<String, String> getLabels() {
        return labels;
    }
}
~~~

Here:

- **hosts** is created with **new ArrayList<>()**, a mutable `List`.
- **labels** is created with **new LinkedHashMap<>()**, a mutable `Map`.
- Both getters return **the exact initialized objects**, not copies.
- There are no setters, so field references cannot be reassigned, yet the binder can populate data inside the collections where supported.

This is especially useful in JavaBeans that want a stable reference for a configuration collection.

### 4.1. A `final` Field Does Not Mean an Immutable Collection

For example:

~~~java
private final List<String> hosts = new ArrayList<>();
~~~

The **final** keyword prevents reassigning a different `List` to **hosts** after object construction. It does **not** forbid operations such as:

~~~java
hosts.add("another.example.test");
hosts.clear();
~~~

Meanwhile:

~~~java
private final List<String> hosts = List.of("localhost");
~~~

has both a `final` reference and an unmodifiable collection. Those two designs must be distinguished.

**Conclusion:** to let the binder populate via getter-only, check the **mutability of the collection instance**, not just the `final` keyword or getter presence.

### 4.2. The Getter Must Return a Workable Object

A getter like:

~~~java
public List<String> getHosts() {
    return new ArrayList<>(hosts);
}
~~~

returns a copy. If the binder only modifies that copy, the real field will not receive the updates. This is not a reliable getter-only binding pattern.

Similarly:

~~~java
public List<String> getHosts() {
    return List.copyOf(hosts);
}
~~~

returns an unmodifiable list. When there is no setter and the binder needs to mutate the collection, this design blocks updates.

To support getter-only JavaBean binding, the getter should expose the pre-initialized mutable collection directly rather than returning a copy or an immutable wrapper.

**Note on encapsulation:** exposing a mutable collection means other code could modify it too. If your architectural goal is read-only access, consider constructor binding with immutable collections instead of a getter-only mutable field disguised behind a defensive-copy getter.

## 5. Immutable Collections and Cases That Typically Fail to Bind

Java provides factory methods and wrappers creating collections that cannot be mutated through their API:

~~~java
List.of("a", "b")
Set.of("READ", "WRITE")
Map.of("region", "asia")
List.copyOf(source)
Map.copyOf(source)
Collections.unmodifiableList(source)
~~~

If a JavaBean is written as:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private final List<String> hosts = List.of("fallback.example.test");

    public List<String> getHosts() {
        return hosts;
    }
}
~~~

then the binder has no setter to swap the reference and the collection returned by **List.of** rejects mutation. When configuration specifies `hosts`, getter-only mutable binding cannot be assumed to succeed; the app may fail to bind or fail to update depending on the binding path taken.

### 5.1. `Arrays.asList` Is Not Like `ArrayList`

An easily confused example:

~~~java
private final List<String> hosts =
        Arrays.asList("primary.example.test", "backup.example.test");
~~~

The list returned by **Arrays.asList** is fixed-size: it permits **set(index, value)**, but forbids adding or removing elements. If the binder needs to clear, add, or resize the list, this `List` cannot satisfy all requirements.

Do not use a collection that merely **looks mutable** yet lacks full structural mutation as a getter-only binding target.

**Clearer pattern:**

~~~java
private final List<String> hosts =
        new ArrayList<>(List.of("primary.example.test"));
~~~

This provides a default element while using a genuinely mutable `ArrayList`.

### 5.2. `Collections.unmodifiableList` Only Creates a View

~~~java
List<String> backing = new ArrayList<>();
List<String> view = Collections.unmodifiableList(backing);
~~~

`view` forbids calling `add` or `clear`. However, if other code retains **backing**, underlying data can still change and `view` reflects those changes.

Hence an **unmodifiable view** is not the same as an **immutable snapshot** where data cannot change via any reference. If you want an immutable snapshot after binding, use **List.copyOf(...)** once data is received, provided elements and nulls match its rules.

## 6. When Is a Setter the Right Choice?

A JavaBean with setters fits when:

- The collection can be replaced wholesale by a binder-constructed instance.
- You do not want to depend on mutating an existing collection instance.
- The class must satisfy JavaBean conventions expected by other frameworks or libraries.
- The field starts uninitialized and the binder needs a way to assign the new value.
- Certain collection types or nested structures require the binder to instantiate a replacement object.

For example:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private List<String> hosts;

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        this.hosts = hosts;
    }
}
~~~

If the `hosts` property appears in the `Environment` and the binder creates a matching `List`, the setter receives the new reference.

However, if **hosts** is unconfigured, the field can remain `null`. Having a setter does not mean a collection is automatically non-empty or non-null. Define defaults and validation explicitly in your design.

### 6.1. Setters Can Normalize Input

For example:

~~~java
public void setHosts(List<String> hosts) {
    this.hosts = hosts == null
            ? new ArrayList<>()
            : new ArrayList<>(hosts);
}
~~~

This keeps a mutable defensive copy. It helps decouple internal references from the `List` passed by the binder. Yet if the ultimate goal is immutability, the class should provide a read-only getter and avoid exposing setters to business code, or use constructor binding instead.

Avoid packing unrelated side effects into setters: parsing files, calling external services, writing disk files, or making network requests during binding makes startup unpredictable.

### 6.2. Getters/Setters on Nested Objects

For example:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private final Routing routing = new Routing();

    public Routing getRouting() {
        return routing;
    }

    public static class Routing {
        private final Map<String, String> labels = new LinkedHashMap<>();

        public Map<String, String> getLabels() {
            return labels;
        }
    }
}
~~~

Because the nested `Routing` instance is already created, the binder can traverse into the child object via its getter and update the mutable `Map` inside as supported by JavaBean binding. If **routing** is `null` with no instantiation path or setter, do not assume the binder will construct arbitrary nested levels automatically.

## 7. Constructor Binding: Choosing an Immutable Model Without Setters

When your architectural rule is **configuration must not mutate after initialization**, record/constructor binding is the natural choice.

~~~java
package example.config;

import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        List<String> hosts,
        Map<String, String> labels
) {}
~~~

YAML:

~~~yaml
app:
  gateway:
    hosts:
      - primary.example.test
      - backup.example.test
    labels:
      owner: platform
      region: asia
~~~

The binder reads the `List` and `Map` from configuration sources, then invokes the record constructor. You do not need:

~~~java
setHosts(...)
setLabels(...)
~~~

and you do not need a JavaBean getter **getHosts()**: the record generates **hosts()** and **labels()** accessors.

**Crucial point:** a record has `final` component fields, yet a field of type **List** or **Map** can still point to a mutable collection instance. **A record does not automatically make collection contents immutable.**

### 7.1. A Record Does Not Turn a List Immutable on Its Own

For example:

~~~java
List<String> mutable = new ArrayList<>();
mutable.add("a");
GatewayProperties p = new GatewayProperties(mutable, Map.of());
mutable.add("b");
~~~

With only the default canonical constructor, **p.hosts()** will reflect element **b** because it still references the same mutable `List`.

Therefore, if the record must hold a true snapshot, add defensive copying.

## 8. Defensive Copying in a Record's Compact Constructor

A stronger immutable design:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        List<String> hosts,
        Map<String, String> labels
) {
    public GatewayProperties {
        hosts = hosts == null
                ? List.of()
                : List.copyOf(hosts);

        labels = labels == null
                ? Map.of()
                : Map.copyOf(labels);
    }
}
~~~

This is a record **compact constructor**. Parameters are normalized before the record assigns them to its components.

Benefits:

- The binder can freely build whatever temporary collection it needs during binding.
- The record takes an immutable copy and exposes a read-only view.
- Services injecting the record cannot succeed in calling **hosts().add(...)** or **labels().put(...)**.
- If other code still holds the source mutable `List`, subsequent edits to it do not alter the copied snapshot.

### 8.1. Constraints of `copyOf`

**List.copyOf**, **Set.copyOf**, and **Map.copyOf** reject `null` elements, keys, or values by contract. If configuration contains nulls, the constructor will throw an exception.

For `List`:

~~~java
List.copyOf(List.of("a", "b"));
~~~

works cleanly, whereas a `List` containing `null` must be handled according to your config contract prior to copying.

For `Map`, **Map.copyOf** also makes no guarantee about preserving iteration order. If deterministic ordering matters, choose a data model and copying strategy that preserves order instead of relying on incidental `Map` iteration order.

### 8.2. Top-Level Immutability Does Not Guarantee Deep Immutability

If a `List` holds mutable elements:

~~~java
List<MutableServer> servers;
~~~

then **List.copyOf(servers)** stops adding or removing elements, yet each individual **MutableServer** can still be mutated through its reference.

To achieve deeper immutability, use immutable element types such as records:

~~~java
public record Server(String name, String host, int port) {}
~~~

and ensure components inside `Server` do not hold uncopied mutable references.

## 9. Nested Records with Lists and Maps

A more realistic example:

~~~java
package example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cluster")
public record ClusterProperties(
        List<Node> nodes,
        Map<String, Region> regions
) {
    public ClusterProperties {
        nodes = nodes == null ? List.of() : List.copyOf(nodes);
        regions = regions == null ? Map.of() : Map.copyOf(regions);
    }

    public record Node(
            String name,
            String host,
            int port
    ) {}

    public record Region(
            String endpoint,
            Duration timeout
    ) {}
}
~~~

YAML:

~~~yaml
app:
  cluster:
    nodes:
      - name: edge-a
        host: edge-a.example.test
        port: 8080
      - name: edge-b
        host: edge-b.example.test
        port: 8081
    regions:
      asia:
        endpoint: "https://asia.example.test"
        timeout: 3s
      europe:
        endpoint: "https://eu.example.test"
        timeout: 5s
~~~

Property paths:

~~~text
app.cluster.nodes[0].name
app.cluster.nodes[0].host
app.cluster.nodes[0].port
app.cluster.nodes[1].name
app.cluster.nodes[1].host
app.cluster.nodes[1].port

app.cluster.regions.asia.endpoint
app.cluster.regions.asia.timeout
app.cluster.regions.europe.endpoint
app.cluster.regions.europe.timeout
~~~

**Node** and **Region** are standalone records, so child elements stay clean and immutable too. The `ClusterProperties` bean can safely be injected across many services without worrying about one service accidentally mutating list items or the regions Map.

### 9.1. Why Doesn't Each `Node` Need Setters?

The binder constructs each `Node` from properties like **nodes[0].host**, then passes the list of `Node` instances to `ClusterProperties`'s constructor. No setter is required on `Node` when using constructor binding supported by your Boot version.

In a mutable nested JavaBean, by contrast, the binder might need getters/setters to construct and populate `Node`. Do not mix the two styles up merely because both bind from the same YAML.

## 10. Immutable Java Classes Without Using `record`

If a project needs traditional classes, use constructor binding with `final` fields and getters:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.queue")
public class QueueProperties {

    private final List<String> names;

    public QueueProperties(List<String> names) {
        this.names = names == null ? List.of() : List.copyOf(names);
    }

    public List<String> getNames() {
        return names;
    }
}
~~~

With a single constructor, Spring Boot 3 can infer constructor binding where supported. If a class has multiple constructors or you need to designate the binding constructor explicitly, use the annotation/registration appropriate for your Spring Boot version.

Do not annotate the class with **@Component** and assume it follows the same constructor-binding lifecycle as a `@ConfigurationProperties` bean registered via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**.

### 10.1. Constructor Binding vs. Constructor Injection

Constructor binding passes **configuration values** resolved by the binder from prefixes, parameter names, and target types.

Constructor injection passes **Spring bean dependencies** resolved by the IoC container.

Both use Java constructors, yet serve completely different purposes. An immutable configuration class receiving values such as `List<String>` or `Duration` typically uses constructor binding; a service that uses `ClusterProperties` receives the `ClusterProperties` bean via constructor injection.

## 11. Getter-Only Rules for `List`, `Set`, and `Map`

Practical comparison table:

| JavaBean design | Has setter? | Initial state | Binding behavior to rely on |
| --- | --- | --- | --- |
| Null `List` field | Yes | null | Setter lets binder assign the `List` |
| Pre-created `ArrayList` | No | Mutable | Binder can populate via getter where supported |
| Pre-created `LinkedHashMap` | No | Mutable | Binder can populate/update via getter |
| Pre-created `LinkedHashSet` | No | Mutable | Verify binding support for the `Set` type and update operations |
| `List.of(...)` | No | Unmodifiable | Not a suitable getter-only binding pattern |
| `Map.of(...)` | No | Unmodifiable | Cannot mutate `Map` through getter |
| `List.copyOf(...)` | Yes | Immutable | Binder may need to swap reference via setter |
| Record with `List`/`Map` | No setter | Constructor-bound | Values are passed into constructor |
| Record with defensive copy | No setter | Immutable snapshot | Constructor receives data then copies |

This table distinguishes **which binding approach to choose**, rather than guaranteeing every binder version invokes a specific method. For multi-level collections, unusual collection factories, or complex value types, test on your actual Spring Boot version.

### 11.1. Do Not Confuse Getter-Only with a Read-Only Business API

A getter-only mutable bean supports the binder, yet another service can still invoke:

~~~java
gatewayProperties.getHosts().clear();
~~~

and alter configuration state. Omitting **setHosts** only blocks replacing the reference via a setter; it does not protect `List` elements.

If the requirement is "services may only read", a better approach is returning immutable configuration after binding, using record/constructor binding, or introducing a separate read-only facade backed by a defensive snapshot.

## 12. `List` in YAML and `.properties`

YAML:

~~~yaml
app:
  queue:
    names:
      - urgent
      - standard
      - deferred
~~~

Equivalent in `.properties`:

~~~properties
app.queue.names[0]=urgent
app.queue.names[1]=standard
app.queue.names[2]=deferred
~~~

When the `List` is inside a JavaBean:

~~~java
@ConfigurationProperties(prefix = "app.queue")
public class QueueProperties {

    private List<String> names = new ArrayList<>();

    public List<String> getNames() {
        return names;
    }

    public void setNames(List<String> names) {
        this.names = names;
    }
}
~~~

Spring Boot binds elements by index. If declared inside a record:

~~~java
@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(List<String> names) {}
~~~

the binder collects elements and passes the `List` to the constructor.

### 12.1. CSV Format in Certain Sources

Some List binding paths accept comma-separated strings:

~~~properties
app.queue.names=urgent,standard,deferred
~~~

However, this representation is unsuitable for complex Lists. For Lists of objects with host, port, and timeout fields, indexed properties in YAML/`.properties` are far clearer.

Do not assume a **@Value** placeholder reads a YAML list the exact same way `@ConfigurationProperties` does: the placeholder resolver and the Binder follow different contracts.

### 12.2. List of Objects

YAML:

~~~yaml
app:
  workers:
    - name: indexing
      concurrency: 2
    - name: exporting
      concurrency: 4
~~~

Record:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record WorkerProperties(List<Worker> workers) {
    public record Worker(String name, int concurrency) {}
}
~~~

Paths:

~~~text
app.workers[0].name
app.workers[0].concurrency
app.workers[1].name
app.workers[1].concurrency
~~~

This is not a Map with keys `"0"` and `"1"`. The binder recognizes List indices from the property path structure.

## 13. `Set`: Collections of Unique Values

`Set` fits when users do not require meaningful positional ordering and want unique values determined by equality rules.

For example:

~~~yaml
app:
  security:
    allowed-methods:
      - GET
      - POST
      - DELETE
~~~

Record:

~~~java
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(Set<String> allowedMethods) {}
~~~

If deterministic ordering is needed for display or processing precedence, consider **List** instead of `Set`.

### 13.1. Limits of "Unique"

`Set` relies on element **equals/hashCode** to determine duplicates. For `String`, **"GET"** and **"get"** are two distinct strings unless normalized. Spring Boot does not automatically treat them as the same HTTP method just because your application wants case-insensitive comparison.

A constructor can normalize:

~~~java
public SecurityProperties {
    if (allowedMethods == null) {
        allowedMethods = Set.of();
    } else {
        allowedMethods = Set.copyOf(allowedMethods);
    }
}
~~~

This builds an unmodifiable snapshot, though it does not uppercase strings automatically. When normalization is required, design an explicit normalization step and validate allowed values.

### 13.2. Be Cautious with Getter-Only `Set`

A mutable **HashSet** or **LinkedHashSet** may support update operations, but do not assume from getter-only `Map`/`List` examples that every custom `Set` type binds identically through a getter.

For important `Set` properties, a **setter** on a JavaBean or **constructor binding** is far more predictable. Verify against your Spring Boot version before relying on a getter-only `Set`.

## 14. `Map`: Dynamic Keys and Mutable Collections

YAML:

~~~yaml
app:
  catalog:
    regions:
      asia: "https://asia.example.test"
      europe: "https://eu.example.test"
~~~

Getter-only mutable `Map` JavaBean:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public class CatalogProperties {

    private final Map<String, String> regions = new LinkedHashMap<>();

    public Map<String, String> getRegions() {
        return regions;
    }
}
~~~

With mutable map support in the binder, entries **asia** and **europe** are inserted into the pre-initialized `Map`. You do not need Java fields named **asia** and **europe**, because they are dynamic data keys.

### 14.1. Getter-Only `Map.of` Is Unsuitable

~~~java
private final Map<String, String> regions = Map.of(
        "default", "https://default.example.test"
);

public Map<String, String> getRegions() {
    return regions;
}
~~~

A Map created by **Map.of** forbids `put`/`remove`. If the binder needs to add or replace entries, getter-only `Map.of` fails.

To keep defaults while still using a mutable JavaBean:

~~~java
private final Map<String, String> regions =
        new LinkedHashMap<>(Map.of(
                "default", "https://default.example.test"
        ));
~~~

Note that across multiple PropertySources, Map merging behavior can affect default entries. Do not assume defaults and overrides always combine the way you expect when multiple sources supply overlapping keys.

### 14.2. Map of Objects

~~~yaml
app:
  policies:
    fast:
      retries: 2
      backoff: 100ms
    reliable:
      retries: 5
      backoff: 1s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record PolicyProperties(Map<String, Policy> policies) {
    public record Policy(int retries, Duration backoff) {}
}
~~~

Paths:

~~~text
app.policies.fast.retries
app.policies.fast.backoff
app.policies.reliable.retries
app.policies.reliable.backoff
~~~

This structure works well when **fast** and **reliable** keys come from config data. When the set of objects is fixed, a nested record with named fields is easier to troubleshoot.

## 15. Special Map Keys and Bracket Notation

When Map keys contain dots, slashes, or characters significant in property paths, you cannot always write them like ordinary keys.

For example, key **tenant.eu** must preserve its dot as part of the tenant name:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

In `.properties`:

~~~properties
app.tenants.[tenant.eu].endpoint=https://eu.example.test
~~~

Bracket notation instructs the binder that **tenant.eu** is a single Map key, not two nested levels **tenant** and **eu**.

For key **/internal/path**:

~~~yaml
app:
  headers:
    "[/internal/path]": enabled
~~~

This is a **Map key recognition rule**, not an effect of mutable vs. immutable collections. An immutable Map still relies on receiving the exact key before the record copies it.

### 15.1. `Map<String, String>` vs. `Map<String, Object>`

The Map's value type affects how the binder resolves nested paths and dots. Never assume dots inside every type of Map automatically stay literal keys.

When dynamic keys contain special characters, use bracket notation or a key-preserving configuration source, and verify actual keys with a unit test.

### 15.2. Avoid Holding Externally Provided Mutable References

If configuration is a constructor-bound Map:

~~~java
public PolicyProperties {
    policies = policies == null
            ? Map.of()
            : Map.copyOf(policies);
}
~~~

calling code cannot easily mutate entries through the accessor. Still, if the **Policy** value is a mutable JavaBean instead of a record, `Map.copyOf` only freezes the Map structure, not the value objects themselves.

## 16. Overriding a `List` Across Multiple Configuration Sources

Java collection mutability **does not control precedence rules** when Spring Boot reads multiple sources.

Example `application.yml`:

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
    - name: beta
      host: beta.example.test
~~~

`application-prod.yml`:

~~~yaml
app:
  servers:
    - name: production
      host: prod.example.test
~~~

When the **prod** profile is active, Spring Boot typically binds the **List** from the higher-priority source. The expected result is a list containing only **production**, not a three-element list of `alpha`, `beta`, and `production`.

This is the **List replacement** rule across PropertySources—unrelated to whether a JavaBean has setters or a record is immutable.

### 16.1. Why Shouldn't You Override One Index and Expect a Merge?

Suppose the base file has:

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
    - name: beta
      host: beta.example.test
~~~

A higher-priority source provides only:

~~~properties
app.servers[0].name=production
~~~

Do not predict the result will be:

~~~text
[0] name=production, host=alpha.example.test
[1] name=beta, host=beta.example.test
~~~

Spring Boot selects the List from the higher-priority source rather than arbitrarily merging individual elements. Omitting `host` in the winning source can produce an incomplete element or validation failure, and items from the lower source are not kept.

**Safe practice:** when overriding a List, declare the entire desired list in the higher-priority source.

### 16.2. Choosing Immutable Records Does Not Change Precedence

Even when a record calls **List.copyOf**, which list the binder passes to the constructor still obeys configuration source precedence. Defensive copying only prevents mutation **after construction**; it does not turn List replacement into List merging.

## 17. Overriding a `Map` Across Multiple Configuration Sources

Maps typically combine differently from Lists.

`application.yml`:

~~~yaml
app:
  labels:
    owner: platform
    region: global
~~~

`application-prod.yml`:

~~~yaml
app:
  labels:
    region: asia
    tier: critical
~~~

Under standard Map binding, distinct keys can combine across sources:

~~~text
owner = platform
region = asia
tier = critical
~~~

For overlapping key **region**, the higher-priority source supplies **asia**. Key **owner** is absent in the prod file so it continues to come from the base file.

This is **Map merging across PropertySources**, and it does not require the resulting Map to stay mutable. A record can accept the combined Map from the binder and call **Map.copyOf** for read-only consumption.

### 17.1. Nested Object Values in Maps Still Need Field-Level Attention

With **Map<String, Region>**, a `Region` can contain `endpoint`, `timeout`, and `retries`. Those fields bind by property name across sources too. When keys overlap and multiple sources specify different child fields, combination behavior is richer than `Map<String, String>`.

If a region entry must always be complete, add validation and explicit deployment examples. Do not extrapolate from a simple scalar Map example to guarantee nested object merging under every circumstance.

## 18. Environment Variables for `List` and `Map`

For **List**:

~~~text
app.servers[0].name -> APP_SERVERS_0_NAME
app.servers[0].host -> APP_SERVERS_0_HOST
app.servers[1].name -> APP_SERVERS_1_NAME
app.servers[1].host -> APP_SERVERS_1_HOST
~~~

In environment variable names, element indices sit between underscores.

Example command:

~~~bash
APP_SERVERS_0_NAME=production APP_SERVERS_0_HOST=prod.example.test java -jar demo.jar
~~~

For a simple **Map**:

~~~text
app.labels.region -> APP_LABELS_REGION
app.labels.owner  -> APP_LABELS_OWNER
~~~

Be careful if Map keys require significant uppercase letters or special characters. OS environment variable constraints and relaxed binding rules can normalize keys away from what you expect.

Even a properly named environment variable may not beat an even higher-priority source such as a JVM system property or command-line argument. Keep **naming translation**, **precedence**, and **Java object mutability** separate.

## 19. Default Values: `null`, Empty, and Pre-Initialized

There are three distinct cases:

**Collection property omitted:**

~~~yaml
app:
  name: demo
~~~

**Empty list declared:**

~~~yaml
app:
  servers: []
~~~

**One-element list declared:**

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
~~~

If the record is:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Server> servers) {
    public record Server(String name, String host) {}
}
~~~

an omitted property can leave **servers** as `null` depending on binding strategy and defaults, whereas an empty list recognized by the binder has a different meaning. Do not assume omitted, YAML `null`, and `[]` always yield the exact same outcome.

### 19.1. Defaults in a JavaBean

~~~java
private List<String> hosts = new ArrayList<>();
~~~

This creates an empty `List` as soon as the object is instantiated. You can also seed default elements:

~~~java
private List<String> hosts =
        new ArrayList<>(List.of("localhost"));
~~~

If runtime configuration declares `hosts`, the binder can replace or update the `List` per JavaBean mechanics; do not assume `localhost` is guaranteed to remain as the first element.

### 19.2. Defaults in a Record

~~~java
public record GatewayProperties(List<String> hosts) {
    public GatewayProperties {
        hosts = hosts == null ? List.of() : List.copyOf(hosts);
    }
}
~~~

This normalizes **null** at the constructor boundary to an empty `List`. It does not dictate how YAML **servers: []** behaves across every PropertySource, yet it protects consuming code from `null` components.

Another option is placing defaults in a base configuration file:

~~~yaml
app:
  gateway:
    hosts:
      - localhost
~~~

Decide cleanly whether defaults come from base config files, annotations/constructors, or Java logic. Avoid conflicting layers of defaults.

### 19.3. `@DefaultValue` in Constructor Binding

Spring Boot provides **@DefaultValue** for supported constructor-binding scenarios. It lets you declare parameter defaults, even for constructing nested objects depending on Boot version and types.

Conceptual example:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(
        @DefaultValue("standard") List<String> names
) {}
~~~

Using `@DefaultValue` with collections depends on available converters and annotation syntax in your actual Spring Boot version. For complex default lists, base YAML or compact constructors are often easier to read.

## 20. Validation of Collections and Individual Elements

A `List` can bind successfully yet still be invalid: empty, duplicate names, missing element host, or invalid port.

Example with Jakarta Validation:

~~~java
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record ValidatedProperties(
        @Valid @NotEmpty List<Server> servers,
        @Valid @NotNull Map<String, Region> regions
) {
    public record Server(
            @NotBlank String name,
            @NotBlank String host,
            @Min(1) int port
    ) {}

    public record Region(
            @NotBlank String endpoint
    ) {}
}
~~~

**@Validated** enables validation on the configuration bean when an appropriate validation provider is present. **@Valid** triggers cascading validation into nested elements/values per Jakarta Validation rules.

**@NotEmpty** fits when a collection must contain at least one element. **@NotNull** only requires the collection itself to be non-null, allowing empty entries.

### 20.1. `null` vs. Empty Can Differ in Contract Semantics

If business rules allow zero regions, an empty Map is valid. However, if having zero configured regions is a deployment mistake, `@NotNull` alone will not catch an empty Map. Use `@NotEmpty` when appropriate.

For a `List`, **@NotEmpty** catches both `null` and an empty list. It does not validate child elements, so combine it with **@Valid** and constraints inside `Server`.

### 20.2. Validating After Creating Immutable Copies

A compact constructor can normalize `null` to `List.of()`. When validation runs, `servers` is an empty `List` rather than `null`. With `@NotEmpty`, that still reports a clear constraint violation.

However, if the record constructor calls `Map.copyOf` on data containing `null`, an exception can be thrown directly inside the constructor before Bean Validation messages are produced. Therefore, when detailed validation messages matter, pay attention to the order of normalization, null checks, and copying.

### 20.3. Avoid Logging Collections Containing Secrets

A configuration Map may hold credentials or tokens. Never log:

~~~java
System.out.println(properties);
~~~

when a record's default `toString` can expose secrets. During binding diagnostics, log only key names or sanitized non-sensitive placeholders.

## 21. Mutable Collections and Thread Safety

Collections such as `ArrayList` and `HashMap` are mutable and **not inherently thread-safe**. If one service mutates a config `List` after Spring starts, other services can observe inconsistent state.

Example never to write in business code:

~~~java
properties.getHosts().add(requestHost);
~~~

This mutates global configuration data and introduces race conditions in multi-threaded web applications.

If configuration is only read after startup, prefer:

- Constructor-bound records with defensive copying.
- An immutable class post-binding.
- Services accepting only read-only interfaces/views when architecturally warranted.

If values must change **genuinely dynamically**, build a dedicated runtime state component with proper synchronization, validation, and lifecycle management. Never turn mutable `@ConfigurationProperties` into request-scoped mutable state.

## 22. `@Value` with Collections vs. the `@ConfigurationProperties` Binder

Some developers try:

~~~java
@Value("${app.queue.names}")
private List<String> names;
~~~

This can work for certain property string formats, such as a comma-separated list string. Do not assume it handles **every nested YAML List/Map structure** the same way `@ConfigurationProperties` Binder does.

**@Value** mainly resolves placeholders and converts types at an injection point. **@ConfigurationProperties** provides a dedicated binder for nested structures, canonical names, collection indices, map keys, and nested objects.

For `List<Server>` or `Map<String, Region>`, model configuration with `@ConfigurationProperties`. That also keeps element validation clean and explicit.

### 22.1. When There Is Just One Simple List

If an app only needs a few unstructured tags, `@Value` may suffice in a small example. Once switching from comma-separated strings to YAML lists, verify the actual behavior rather than assuming identical binder rules.

For long-lived operational configuration, prefer an API giving a clear contract for names, types, defaults, and precedence.

## 23. Nested Objects Have Similar Getter/Setter Requirements

A JavaBean with a nested object:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private Http http = new Http();

    public Http getHttp() {
        return http;
    }

    public static class Http {

        private List<String> proxies = new ArrayList<>();

        public List<String> getProxies() {
            return proxies;
        }

        public void setProxies(List<String> proxies) {
            this.proxies = proxies;
        }
    }
}
~~~

If **http** is pre-instantiated, the binder can update child properties on `Http` via its getter without strictly needing a setter for `http`. Yet this structure only works if the nested object's instantiation and accessors match the binder's expectations.

If a nested object is an immutable record while the outer class is a JavaBean, or vice versa, check whether each level binds via setters or constructors. Never mix patterns blindly assuming the binder infers arbitrary combinations of constructors and getters.

### 23.1. Null Nested Objects

If:

~~~java
private Http http;
public Http getHttp() { return http; }
~~~

lacks a setter, the binder has fewer options for populating the nested object. Pre-initializing a mutable `Http` or adding a setter expresses JavaBean binding clearly.

### 23.2. `@NestedConfigurationProperty` Does Not Make Getters Work

The **@NestedConfigurationProperty** annotation primarily supplies configuration metadata for IDE/tooling support. It does not convert `List.of` into `ArrayList`, synthesize setters, fix copy-returning getters, or turn an immutable object into a mutable one.

Never use metadata annotations trying to fix getter/setter or constructor binding issues.

## 24. Registering Constructor-Bound Beans Properly

Example record:

~~~java
@ConfigurationProperties(prefix = "app.cluster")
public record ClusterProperties(List<String> nodes) {
    public ClusterProperties {
        nodes = nodes == null ? List.of() : List.copyOf(nodes);
    }
}
~~~

In standard Spring Boot, register via:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

or:

~~~java
@Configuration
@EnableConfigurationProperties(ClusterProperties.class)
class ClusterConfiguration {
}
~~~

Do not write:

~~~java
@Component
@ConfigurationProperties(prefix = "app.cluster")
public record ClusterProperties(List<String> nodes) {}
~~~

and assume a single constructor automatically uses constructor binding the same way. Constructor binding must be managed by the appropriate configuration-properties infrastructure; regular `@Component` follows normal bean instantiation lifecycles.

For JavaBeans with a no-arg constructor and setters, registering as a component can follow different paths, though consistently using scan/enable keeps project organization simpler.

## 25. `UnsupportedOperationException` During Binding

If an application uses getter-only:

~~~java
private final List<String> hosts = List.of();

public List<String> getHosts() {
    return hosts;
}
~~~

and the Binder attempts to update the `List`, operations such as `add`/`clear` can throw **UnsupportedOperationException**, or binding fails to finish the intended update.

Fixes depend on your goal:

**If you want a mutable getter-only JavaBean:**

~~~java
private final List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return hosts;
}
~~~

**If you want a JavaBean that swaps the `List`:**

~~~java
private List<String> hosts = List.of();

public List<String> getHosts() {
    return hosts;
}

public void setHosts(List<String> hosts) {
    this.hosts = List.copyOf(hosts);
}
~~~

Verify setter behavior with your actual binder version: if the binder tries mutating the pre-existing collection before calling the setter, keeping an immutable initial collection while adding a setter might still fail expectations. In such cases, initialize with a mutable collection for JavaBean binding or switch cleanly to constructor binding.

**If you want immutability after startup:**

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(List<String> hosts) {
    public GatewayProperties {
        hosts = hosts == null ? List.of() : List.copyOf(hosts);
    }
}
~~~

This last pattern produces an immutable target model without requiring the binder to mutate a pre-initialized `List.of` in a getter-only JavaBean.

## 26. Bug: Getter Returning an Unmodifiable Wrapper

A pattern that commonly shows up when trying to protect encapsulation:

~~~java
private final List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return Collections.unmodifiableList(hosts);
}
~~~

The public getter prevents callers from mutating `hosts`, yet a getter-only JavaBean binder sees only that same unmodifiable view. Without a setter or alternative path, binding directly into this collection cannot reliably succeed.

**Architectural fix:** separate the binding phase from read-only exposure, or use constructor binding with defensive copying. Do not try to give the binder one kind of getter behavior and services another, hoping JavaBean introspection reads your mind.

## 27. Bug: Getter Creating a New Collection Every Call

For example:

~~~java
private final List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return new ArrayList<>(hosts);
}
~~~

If the Binder mutates the `List` returned by the getter, changes never reach the underlying **hosts** field. Even though the method is named `getHosts`, it fails to expose mutable state for updates.

Fix this by providing a real setter or moving to constructor binding. A copy-returning getter should only sit inside a well-defined setter-backed or immutable design, never as a target for getter-only mutation.

## 28. Bug: Using Collections Without Full Public Mutators

Besides `List.of` and `Map.of`, there are:

~~~java
Arrays.asList(...)
Collections.singletonList(...)
Collections.emptyMap()
Collections.unmodifiableMap(...)
~~~

These factories and wrappers have differing mutability semantics. Some forbid resizing, some forbid `put`/`remove`, and some are views over backing objects.

Never rely solely on the **List** or **Map** interface assuming every implementation supports full mutation. For getter-only JavaBean binding, initialize concrete mutable implementations such as `ArrayList` and `LinkedHashMap` when you expect the binder to populate them.

## 29. Bug: Omitted Collection Still Lets Bean Start

JavaBean:

~~~java
private List<String> hosts;
~~~

Record:

~~~java
public record GatewayProperties(List<String> hosts) {}
~~~

If config omits `hosts`, the property can be `null` depending on binding strategy and defaults. Downstream code calling:

~~~java
properties.getHosts().size();
~~~

or:

~~~java
properties.hosts().size();
~~~

risks throwing **NullPointerException**.

Options:

- Default to empty and handle empty meaningfully in business logic.
- Require at least one element using **@NotEmpty**.
- Provide default hosts in `application.yml`.
- Normalize `null` inside a record's compact constructor.
- For a JavaBean, initialize the field with a mutable empty collection.

Do not silently default to empty if missing `hosts` is genuinely a fatal deployment misconfiguration that should stop startup.

## 30. Bug: List Loses Elements When Switching Profiles

If `application.yml` defines three workers while `application-prod.yml` defines one worker, Spring Boot can bind the `List` from the higher-priority profile source. After enabling `prod`, the worker count drops from three to one.

This is not **List.copyOf** dropping elements or a setter clearing things accidentally. The cause is the **List replacement rule across sources**.

How to verify:

1. List all relevant PropertySources.
2. Check active profiles.
3. Identify which files declare the same collection path.
4. Identify the highest-priority source providing the `List`.
5. Inspect the final bound `List` in the bean rather than counting lines in base YAML.

## 31. Bug: Map Receives Wrong Keys Due to Special Characters

Example business key **us.east**:

~~~yaml
app:
  regions:
    us.east:
      endpoint: "https://east.example.test"
~~~

When the Map value has a nested structure, dots can be parsed as property path separators. To preserve the dotted key, write:

~~~yaml
app:
  regions:
    "[us.east]":
      endpoint: "https://east.example.test"
~~~

This issue is independent of Map mutability. Even if the final Map is copied into an immutable `Map`, a key that was mis-parsed earlier remains wrong.

## 32. Decision Table: Which Pattern to Choose?

| Requirement | Pattern to consider | Notes |
| --- | --- | --- |
| JavaBean needing traditional setters | Mutable `List`/`Map` + getters/setters | Setter allows reference replacement |
| Getter-only JavaBean | Pre-initialized `ArrayList`/`LinkedHashMap`, getter returns field directly | Collection must be mutable |
| Want immutable configuration | Record constructor binding | No setters needed |
| Want `List`/`Map` protected from service mutation | Record + `List.copyOf`/`Map.copyOf` | Watch out for nulls and deep immutability |
| List of multi-field child objects | `List<record>` or `List<JavaBean>` | Indexed, validate elements |
| Collection of unique values | `Set<T>` | Do not rely on it when business ordering matters |
| Data keyed dynamically | `Map<String, Value>` | Use brackets for special keys |
| Optional collection with defaults | Pre-initialize mutable in JavaBean or normalize in constructor | Choose empty vs. explicit default clearly |
| Collection required to be non-empty | `@NotEmpty` + `@Validated` | Add `@Valid` for elements |
| Overriding a `List` per profile | Declare the complete `List` in higher-priority source | Do not expect automatic merging |
| Combining `Map` keys | `Map` binding across PropertySources | Colliding keys obey precedence |
| Changing config while app runs | Dedicated runtime config/refresh mechanism | Mutable `List` does not auto-refresh |

## 33. Testing a Getter-Only Mutable JavaBean

You can use **ApplicationContextRunner** from `spring-boot-test` to verify binding. Conceptual example:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsMutableGetterOnlyCollection() {
        runner.withPropertyValues(
                "app.gateway.hosts[0]=alpha.example.test",
                "app.gateway.hosts[1]=beta.example.test",
                "app.gateway.labels.owner=platform"
        ).run(context -> {
            GatewayProperties properties =
                    context.getBean(GatewayProperties.class);

            assertThat(properties.getHosts())
                    .containsExactly("alpha.example.test", "beta.example.test");
            assertThat(properties.getLabels())
                    .containsEntry("owner", "platform");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestConfiguration {}
}
~~~

In this test, **GatewayProperties** is the getter-only mutable class from section 4 with prefix **app.gateway**. The test supplies properties via the test runner rather than creating YAML files or OS environment variables.

**What the test actually proves:** on the running Spring Boot version and class definition, whether the binder populates the pre-initialized collections cleanly. This gives solid verification whenever a project uses a custom collection implementation or omits setters.

## 34. Testing Immutable Records and Defensive Copies

For records, add a plain Java unit test checking immutability without needing an `ApplicationContext`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.*;

class ImmutableGatewayPropertiesTest {

    @Test
    void defensiveCopiesPreventExternalMutation() {
        List<String> inputHosts = new ArrayList<>();
        inputHosts.add("alpha.example.test");

        Map<String, String> inputLabels = new LinkedHashMap<>();
        inputLabels.put("owner", "platform");

        GatewayProperties properties =
                new GatewayProperties(inputHosts, inputLabels);

        inputHosts.add("beta.example.test");
        inputLabels.put("region", "asia");

        assertThat(properties.hosts())
                .containsExactly("alpha.example.test");
        assertThat(properties.labels())
                .containsOnlyKeys("owner");

        assertThatThrownBy(() -> properties.hosts().add("other"))
                .isInstanceOf(UnsupportedOperationException.class);

        assertThatThrownBy(() -> properties.labels().put("x", "y"))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

This test assumes the `GatewayProperties` record has a compact constructor executing **List.copyOf** and **Map.copyOf** as in section 8.

This tests **Java object behavior**, not whether the binder parsed YAML accurately. To test end-to-end binding, add a separate `ApplicationContextRunner` test.

## 35. Testing List Replacement Across Multiple PropertySources

A valuable test for profile-based projects:

Base file:

~~~yaml
app:
  gateway:
    hosts:
      - alpha.example.test
      - beta.example.test
~~~

Prod profile file:

~~~yaml
app:
  gateway:
    hosts:
      - production.example.test
~~~

Activate the `prod` profile and assert the final host list:

~~~java
assertThat(properties.hosts())
        .containsExactly("production.example.test");
~~~

If this test fails because another source overrode it, log the active PropertySources. Do not change collection code to mutable trying to "fix" an issue that actually stems from source precedence.

## 36. Recognizing Binding Errors from Exceptions

Common indicators:

| Symptom | Where to check | How to fix |
| --- | --- | --- |
| `UnsupportedOperationException` | Is an immutable `List`/`Map` being mutated? | Use a mutable JavaBean or constructor binding |
| Bean lacks a property inside the `List` | Wrong path/index? | Verify `app.items[0].field` |
| Getter-only `List` is empty despite YAML values | Getter returning copy/unmodifiable view? | Expose real mutable collection or add setter |
| `Cannot bind properties` | Wrong item type or constructor? | Read nested root cause inside exception |
| `List` drops elements across profiles | List replacement | Check high-priority source; declare complete `List` |
| Map key split unexpectedly | Special characters in key | Use bracket notation |
| `NullPointerException` accessing collection | Field has no default | Normalize or add validation |
| Duplicate configuration properties bean | Class registered multiple ways | Pick scan or enable consistently |
| Bean value differs from environment variable | Source precedence | Check CLI, `-D`, env, config data |
| Setter not called as expected | Binder using constructor path or getter-only path? | Identify active binding strategy |
| Validation skipped on elements | Missing `@Valid` or validation provider | Add proper validation dependency/annotations |

A `"Failed to bind properties under ..."` message usually names the property path, target Java type, and conversion cause. Read the root cause instead of concluding "Spring Boot doesn't support immutable config".

## 37. Distinguishing Binding, Conversion, and Validation

Consider the example:

~~~yaml
app:
  workers:
    - name: indexing
      concurrency: many
~~~

If `Worker` is:

~~~java
public record Worker(String name, int concurrency) {}
~~~

the binder reads path **app.workers[0].concurrency**, yet **many** cannot convert to `int`. That is a **conversion failure**, not a setter or mutability issue.

If `concurrency` is **0** with **@Min(1)**, the failure belongs to **validation**. If YAML places **concurrency** under **app.queue.workers[0]** while the bean expects **app.workers[0]**, that is a **property path** issue.

A solid debugging trail follows:

~~~text
PropertySource
   -> full key name
   -> raw value
   -> conversion to element type
   -> collection creation/update
   -> validation
   -> final Java object
~~~

Adding a setter cannot fix bad input types or wrong YAML indentation.

## 38. Diagnostics via `Environment`

An example reading non-sensitive keys:

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
        System.out.println("first host = "
                + environment.getProperty("app.gateway.hosts[0]"));
        System.out.println("owner = "
                + environment.getProperty("app.gateway.labels.owner"));
    }
}
~~~

This merely reads specific keys from Spring `Environment`. It is no substitute for inspecting the bound collection inside the bean via its getter or record accessor.

If `Environment` holds the right values yet the bean does not, check binding strategy, mutability, constructors, conversion, and validation.

### 38.1. Listing `PropertySource` Names

During environment debugging, you can use `ConfigurableEnvironment`:

~~~java
for (org.springframework.core.env.PropertySource<?> source
        : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

This assumes **environment** is a **ConfigurableEnvironment**. Print source names only—never dump all keys/values, since config collections may contain tokens or secrets.

Spring Boot Actuator, properly secured, can trace property origins. Never expose diagnostic endpoints publicly just to check a host list.

## 39. A Complete Deployment-Ready Configuration Example

Base file example:

~~~yaml
app:
  notifications:
    channels:
      - email
      - webhook
    templates:
      welcome: "welcome-v1"
      alert: "alert-v2"
    targets:
      - name: primary
        endpoint: "https://notify.example.test"
        timeout: 3s
~~~

An immutable record:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        List<String> channels,
        Map<String, String> templates,
        List<Target> targets
) {
    public NotificationProperties {
        channels = channels == null
                ? List.of()
                : List.copyOf(channels);
        templates = templates == null
                ? Map.of()
                : Map.copyOf(templates);
        targets = targets == null
                ? List.of()
                : List.copyOf(targets);
    }

    public record Target(
            String name,
            String endpoint,
            Duration timeout
    ) {}
}
~~~

Key paths:

~~~text
app.notifications.channels[0]
app.notifications.channels[1]
app.notifications.templates.welcome
app.notifications.templates.alert
app.notifications.targets[0].name
app.notifications.targets[0].endpoint
app.notifications.targets[0].timeout
~~~

Example environment variables for a target:

~~~text
APP_NOTIFICATIONS_TARGETS_0_NAME
APP_NOTIFICATIONS_TARGETS_0_ENDPOINT
APP_NOTIFICATIONS_TARGETS_0_TIMEOUT
~~~

Note: if a deployment overrides `target[0]` via high-priority env vars, inspect the entire final `targets` `List`. Do not assume fields omitted in env vars will merge in from the base file.

### 39.1. When Choosing a JavaBean Instead of a Record

If legacy constraints demand setters, keep the JavaBean solely for binding and build a separate immutable object for consuming services. Make clear who (if anyone) may modify the JavaBean after startup.

Example conversion step:

~~~java
public record NotificationSnapshot(List<String> channels) {
    public NotificationSnapshot {
        channels = channels == null
                ? List.of()
                : List.copyOf(channels);
    }
}
~~~

A config service can build the snapshot from the bound JavaBean and pass only `NotificationSnapshot` to downstream modules. That preserves JavaBean binding compatibility without exposing mutable Lists widely.

## 40. Practice Exercise 1: Getter-Only Mutable

Given YAML:

~~~yaml
app:
  tags:
    names:
      - green
      - blue
~~~

Build a JavaBean with prefix **app.tags**, with no setter for `names`, yet capable of binding via a pre-initialized collection.

Sample solution:

~~~java
@ConfigurationProperties(prefix = "app.tags")
public class TagProperties {

    private final List<String> names = new ArrayList<>();

    public List<String> getNames() {
        return names;
    }
}
~~~

Explanation: the getter returns the mutable `ArrayList` itself. Changing it to **List.of()** breaks the mutation-based binding assumption.

## 41. Practice Exercise 2: Immutable Record

Given YAML:

~~~yaml
app:
  tags:
    names:
      - green
      - blue
~~~

Write a record with no setters, protected against external code calling `add`:

~~~java
@ConfigurationProperties(prefix = "app.tags")
public record TagProperties(List<String> names) {

    public TagProperties {
        names = names == null ? List.of() : List.copyOf(names);
    }
}
~~~

When other code calls:

~~~java
properties.names().add("red");
~~~

the `List` produced by `copyOf` rejects `add`. That enforces the bean's immutability contract.

## 42. Practice Exercise 3: Copy-Returning Getter

Someone writes:

~~~java
private final Map<String, String> labels = new LinkedHashMap<>();

public Map<String, String> getLabels() {
    return new LinkedHashMap<>(labels);
}
~~~

They wrote no setter. Why is this not a reliable getter-only binding pattern?

Because every getter call returns a different `Map`. Even if the binder writes into that `Map`, the original **labels** field is not necessarily updated. Fix it by returning `labels` directly for mutable getter-only binding, or switching to setter/constructor binding with defensive copying for read-only guarantees.

## 43. Practice Exercise 4: `List` vs. `Map` Precedence

Base file:

~~~yaml
app:
  servers:
    - alpha
    - beta
  labels:
    owner: platform
    region: global
~~~

Prod profile file:

~~~yaml
app:
  servers:
    - production
  labels:
    region: asia
    tier: critical
~~~

Predict the outcome:

~~~text
servers = [production]

labels.owner  = platform
labels.region = asia
labels.tier   = critical
~~~

Under standard binding, Lists tend to be **replaced** by the higher-priority source's List, while Maps can **combine** keys. This explanation applies regardless of whether the target Java object is a mutable JavaBean or an immutable record.

## 44. Practice Exercise 5: Map with a Dotted Key

Ambiguous YAML:

~~~yaml
app:
  tenant-configs:
    tenant.eu:
      enabled: true
~~~

If **tenant.eu** must be a single `Map<String, TenantConfig>` key, use:

~~~yaml
app:
  tenant-configs:
    "[tenant.eu]":
      enabled: true
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Map<String, TenantConfig> tenantConfigs
) {
    public record TenantConfig(boolean enabled) {}
}
~~~

After binding, the expected key is **tenant.eu**. Map mutability does not alter key recognition rules.

## 45. Practice Exercise 6: Choosing Setter vs. Constructor

Requirements:

- Config has `List<Region>`.
- Services may only read after startup.
- No setters in the public API.
- Each `Region` has `endpoint` and `timeout`.
- No runtime refresh needed.

Suitable design:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Region> regions) {

    public AppProperties {
        regions = regions == null
                ? List.of()
                : List.copyOf(regions);
    }

    public record Region(
            String endpoint,
            java.time.Duration timeout
    ) {}
}
~~~

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. This uses constructor binding without JavaBean getters/setters. Add validation if the list must be non-empty or endpoints must be valid.

## 46. Pre-Coding Design Decision Flow

Before building a Collection/Map configuration group, decide:

1. **Does the collection need to change after startup?** If not, prefer an immutable model.
2. **Must you use JavaBean/setter binding for legacy reasons?** If yes, use getter-only strictly with genuinely mutable, pre-initialized collections.
3. **Should you use `List`, `Set`, or `Map`?** Decide based on ordering semantics, uniqueness, and dynamic keys.
4. **Are elements scalars or objects?** For objects, design element types with clear instantiation paths.
5. **What is the intended default?** Omitted, empty, and pre-seeded lists are not interchangeable.
6. **Is at least one element mandatory?** Apply appropriate validation.
7. **Can multiple sources declare the same collection?** Account for List replacement vs. Map merging.
8. **Are there special Map keys?** Use bracket notation where required.
9. **Is sensitive data involved?** Avoid logging `toString()` on records containing secrets.
10. **Are both binding and immutability tested?** Test both `PropertySource` inputs and Java object behavior.

If a design demands both getter-only JavaBean binding and an unmodifiable pre-initialized collection before the binder even runs, reconsider your strategy: **constructor binding into an immutable record** usually expresses the goal far better.

## 47. Key Takeaways

- **Mutable collections** allow mutating elements; **immutable/unmodifiable collections** forbid those operations. A **final List** field can still point to a mutable `ArrayList`.
- In **JavaBean binding**, setters provide the explicit path for assigning a new collection. A **pre-initialized, mutable List/Map returned directly by its getter** can bind without a setter where supported.
- **Getters returning `List.of`, `Map.of`, unmodifiable wrappers, or copies** are not reliable targets for getter-only mutable binding.
- With **constructor binding/records**, the binder passes `List`/`Map` via constructor arguments—no setters needed. Protect post-construction state with controlled defensive copying.
- **A record with a `List`/`Map` component does not guarantee deep immutability**; inspect element types as well.
- **Lists** use index addressing and follow replacement rules across PropertySources; **Maps** can combine keys across multiple sources. Java object mutability never overrides source precedence.
- **Omitted**, **null**, and **empty collection** represent three distinct cases. Design defaults and validation to match business rules.
- If a collection must be non-empty, use **@NotEmpty**; for child objects, apply **@Valid** and per-element constraints.
- When runtime behavior fails, trace **property name → PropertySource → data type → binding strategy → collection instance → validation**.
- When config is read-only after startup, records with constructor binding and defensive copies minimize the risk of services accidentally mutating shared state.

The most important point is that **getters/setters belong to object creation and update strategy, whereas mutable/immutable is a property of the collection instance inside the object**. Keeping those two concepts separate lets you choose the right JavaBean binding or constructor binding pattern and avoid subtle bugs when configuring `List`, `Set`, and `Map` in Spring Boot.