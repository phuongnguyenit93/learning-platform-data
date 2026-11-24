# Reading Display Names Separately from Routing Names in JMX ObjectName

## 1. The Problem: One Managed Object Has Multiple Ways of Being Named

In Java Management Extensions (JMX), `ObjectName` determines **which MBean** receives a management call. In a Spring Framework application, an MBean can be registered via `MBeanExporter`, displayed in JConsole or a monitoring tool, and read/written through `MBeanServer` or `MBeanServerConnection`. When building management interfaces, two kinds of names commonly appear:

1. **Routing identity:** the actual `ObjectName` registered in the `MBeanServer`. JMX uses this name to locate the MBean, read attributes, and invoke operations.
2. **Display name:** human-friendly text, such as "Primary Cache", "Payment App – Host A", a UI-formatted `name`, or a label taken from MBean metadata.

The two names may look similar, yet they do not serve the same role. In JMX, a human-readable string does **not automatically** become a valid `ObjectName`, and a label shown by a dashboard does **not guarantee** unique identification of an MBean.

Example:

```text
Display name in dashboard:
  Primary Cache (Hanoi)

ObjectName used for routing:
  com.example.cache:type=CacheMetrics,region=hn,name=primary
```

Only the registered `ObjectName` value works directly for:

```java
connection.getAttribute(objectName, "HitCount");
connection.invoke(objectName, "clear", null, null);
```

If you replace `objectName` with the string "Primary Cache (Hanoi)", the code no longer has a corresponding JMX identifier.

The goal of this lesson is to understand how to read and present `ObjectName`, separate display labels from routing identities, and preserve MBean identity when users switch languages, rename labels, or run multiple instances.

## 2. The Real Structure of an ObjectName

A JMX name typically has the form:

```text
domain:key1=value1,key2=value2,...
```

Example:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
```

Three components to distinguish:

| Component | Example | Role |
| --- | --- | --- |
| Domain | `com.example.cache` | JMX namespace, helps group MBeans |
| Key property | `type`, `name`, `region` | Keys forming the ObjectName |
| Property value | `CacheMetrics`, `primary`, `hn` | Value of each key |

In the example, `name=primary` is an **ObjectName key property**. It is not necessarily a JMX attribute named `Name`, nor is it automatically the label intended for display. The word `name` across multiple layers can cause confusion:

- **Spring bean name**: identifier of the bean in the `ApplicationContext`.
- **JMX ObjectName**: identifier of the MBean in the `MBeanServer`.
- **ObjectName key property `name`**: one data field of the JMX ObjectName.
- **UI display name**: text decided by the UI or management system.
- **`Name` attribute**: exists only if the MBean explicitly exposes an attribute with that name.

They may happen to share the same value in a specific case, but they should never be treated as synonymous.

### 2.1. ObjectName Is a Structure, Not Just a Descriptive String

Java provides `javax.management.ObjectName`:

```java
import javax.management.ObjectName;

ObjectName objectName = new ObjectName(
    "com.example.cache:type=CacheMetrics,name=primary,region=hn");

System.out.println(objectName.getDomain());
System.out.println(objectName.getKeyProperty("type"));
System.out.println(objectName.getKeyProperty("name"));
System.out.println(objectName.getKeyProperty("region"));
```

Expected output:

```text
com.example.cache
CacheMetrics
primary
hn
```

These methods read **identity** components from the ObjectName. They do not ask the MBean what management attributes it has and do not query runtime data.

### 2.2. Key Property Order Carries No Business Meaning

Two strings can express the same JMX identity even when key property order differs:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
com.example.cache:region=hn,name=primary,type=CacheMetrics
```

When comparing identities, use `ObjectName.equals(...)` instead of comparing unnormalized strings manually. When consistent string output is needed, `getCanonicalName()` provides a canonical representation with key properties sorted per JMX rules.

```java
ObjectName a = new ObjectName(
    "com.example.cache:type=CacheMetrics,name=primary,region=hn");

ObjectName b = new ObjectName(
    "com.example.cache:region=hn,name=primary,type=CacheMetrics");

System.out.println(a.equals(b));          // true
System.out.println(a.getCanonicalName());
System.out.println(b.getCanonicalName());
```

When storing an identity for reuse, prefer the canonical name or keep the `ObjectName` type until serialization. `toString()` is a valid name representation, but does not necessarily have canonical property ordering like `getCanonicalName()`.

## 3. Where Should Display Names Come From?

A display name is a decision made by the management application. There are several common sources, and you should distinguish which come from the JMX standard and which are custom conventions.

### 3.1. Deriving a Label from the ObjectName

If the `ObjectName` has readable key properties, the UI can extract them and build a label:

```java
ObjectName name = new ObjectName(
    "com.example.cache:type=CacheMetrics,name=primary,region=hn");

String region = name.getKeyProperty("region");
String instance = name.getKeyProperty("name");

String label = "Cache " + instance + " (" + region + ")";
System.out.println(label); // Cache primary (hn)
```

This is a **presentation rule chosen by the application**. JMX does not dictate that `region` must translate to any geographic name or that `name` must become a UI label.

If localization is needed:

```java
String localizedRegion = switch (region) {
    case "hn" -> "Hà Nội";
    case "hcm" -> "TP. Hồ Chí Minh";
    default -> region;
};

String displayName = "Bộ nhớ đệm " + instance
                   + " (" + localizedRegion + ")";
```

Changing a Vietnamese label to English does not change the `ObjectName` and should not change the target that JMX operations are directed to.

### 3.2. Reading an Attribute Exposed by the MBean

An MBean can proactively expose `DisplayName` or `Description` as a management attribute. In that case, the client actually calls `MBeanServerConnection.getAttribute(...)`:

```java
String label = (String) connection.getAttribute(
    name, "DisplayName");
```

This works only if the MBean metadata exposes a readable `DisplayName` attribute. Not every MBean has such an attribute.

Standard MBean example:

```java
public interface CacheMetricsMBean {
    String getDisplayName();
    long getHitCount();
}
```

```java
public class CacheMetrics implements CacheMetricsMBean {
    private final String displayName;
    private long hitCount;

    public CacheMetrics(String displayName) {
        this.displayName = displayName;
    }

    @Override
    public String getDisplayName() {
        return displayName;
    }

    @Override
    public long getHitCount() {
        return hitCount;
    }
}
```

Under Standard MBean conventions, `getDisplayName()` can be modeled as a read-only `DisplayName` attribute. This attribute name is data exposed by the MBean; it is **distinct** from the ObjectName's `name` key property.

An operational application can allow users to change `DisplayName` while keeping the ObjectName fixed. That way, dashboard links to the MBean do not break.

### 3.3. Reading Descriptions from MBeanInfo

JMX metadata also includes descriptions for management tools:

```java
import javax.management.MBeanInfo;

MBeanInfo info = connection.getMBeanInfo(name);
String description = info.getDescription();
```

`MBeanInfo.getDescription()` describes the MBean according to provider metadata; it does **not mean** "the official display name" of the MBean. The description may be a long explanatory sentence, blank, or merely a technical string depending on how the MBean is implemented.

With Spring Framework, `@ManagedResource(description = "...")` and the corresponding metadata assembler can contribute description text to `MBeanInfo`.

Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.cache:type=CacheMetrics,name=primary,region=hn",
    description = "Runtime metrics for the primary regional cache")
public class SpringCacheMetrics {
    @ManagedAttribute(description = "Cache hit count")
    public long getHitCount() {
        return 0L; // Illustrative value
    }
}
```

Spring annotations must be processed by a metadata-aware exporter/assembler for those descriptions to appear in the JMX interface. Do not expect annotations alone to auto-register MBeans in every Spring context.

### 3.4. Labels Living Entirely in the Display System

A dashboard can store its own configuration:

```json
{
  "jmxObjectName": "com.example.cache:type=CacheMetrics,name=primary,region=hn",
  "displayName": "Primary Cache - Hanoi",
  "group": "Cache"
}
```

Where:

- `jmxObjectName` routes to the JMX MBean.
- `displayName` renders the label on screen.
- `group` groups or sorts UI items.

This is simply an illustrative JSON structure for a dashboard application, not a schema mandated by JMX. It highlights an important principle: human-facing data can change freely without altering the resource address.

## 4. Distinguishing ObjectName APIs from Metadata and Attribute APIs

Three similar-sounding operations read completely different kinds of data:

| Goal | API | Requirement |
| --- | --- | --- |
| Read domain or key property from ObjectName | `getDomain()`, `getKeyProperty(key)` | Requires only `ObjectName` |
| Read MBean description/management interface | `MBeanServerConnection.getMBeanInfo(objectName)` | MBean exists on the server |
| Read a specific MBean attribute | `MBeanServerConnection.getAttribute(objectName, attribute)` | MBean exists and attribute is readable |

Example combining all three sources:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxDisplayReader {
    private JmxDisplayReader() {}

    public static void print(
            MBeanServerConnection connection,
            ObjectName name) throws Exception {

        System.out.println("Routing identity: "
            + name.getCanonicalName());

        System.out.println("Domain: " + name.getDomain());
        System.out.println("Instance key: "
            + name.getKeyProperty("name"));

        MBeanInfo info = connection.getMBeanInfo(name);
        System.out.println("MBean description: "
            + info.getDescription());
    }
}
```

This snippet intentionally does not read `DisplayName` because not every MBean exposes that attribute. If needed, inspect `MBeanInfo.getAttributes()` before reading to avoid `AttributeNotFoundException`.

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;

boolean hasReadableDisplayName = Arrays.stream(info.getAttributes())
    .anyMatch(attribute ->
        attribute.getName().equals("DisplayName")
        && attribute.isReadable());

String displayName = hasReadableDisplayName
    ? (String) connection.getAttribute(name, "DisplayName")
    : name.getKeyProperty("name");
```

In real applications, handle a missing `name` key, null/blank `DisplayName`, and attributes whose type is not `String` before rendering. Using the canonical name as a final fallback label ensures tools can still display MBeans lacking friendly metadata.

## 5. Discovering MBeans Without Confusing Labels and Routing Keys

### 5.1. Listing ObjectNames from MBeanServer

JMX provides `queryNames` to find registered MBeans matching a pattern.

```java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName query = new ObjectName(
    "com.example.cache:type=CacheMetrics,*");

Set<ObjectName> names = connection.queryNames(query, null);

for (ObjectName objectName : names) {
    System.out.println(objectName.getCanonicalName());
}
```

`queryNames` returns actual `ObjectName`s suitable as MBean selection keys. It does not return a list of localized display labels. A pattern `ObjectName` is for **searching**, not a concrete MBean address for automatically reading attributes: if a pattern matches multiple MBeans, the client must choose each concrete ObjectName.

To render a list, keep both identity and label:

```java
public record MBeanOption(ObjectName objectName, String label) {}
```

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

List<MBeanOption> options = new ArrayList<>();

for (ObjectName objectName : names) {
    String instance = objectName.getKeyProperty("name");
    String label = (instance == null || instance.isBlank())
        ? objectName.getCanonicalName()
        : "Cache " + instance;

    options.add(new MBeanOption(objectName, label));
}

options.sort(Comparator.comparing(
    option -> option.objectName().getCanonicalName()));
```

When a user selects "Cache primary", the UI must take the original `MBeanOption.objectName()` to call the server. Never pass `label` into `new ObjectName(label)`.

### 5.2. Display Labels Can Collide

Two MBeans:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
com.example.cache:type=CacheMetrics,name=primary,region=hcm
```

If the dashboard only displays `name=primary`, both have the same label "Cache primary". A label collision does not mean the identities collide.

How the UI can handle it:

```text
Cache primary — Hanoi
Cache primary — Ho Chi Minh City
```

In the underlying data, each row still keeps the full `ObjectName`, including `region`. Do not "fix" a working ObjectName merely to make UI labels look prettier; changing an ObjectName changes the JMX identity and can break dashboards, alert rules, client proxies, automation, and scripts referencing the old name.

### 5.3. Never Use Display Labels as Map Keys

An anti-pattern:

```java
// Unsafe if labels collide or language changes.
Map<String, ObjectName> byDisplayLabel = new HashMap<>();
byDisplayLabel.put("Cache primary", firstMBean);
byDisplayLabel.put("Cache primary", secondMBean);
```

The second entry overwrites the first. A better design stores identity by `ObjectName` or canonical name and uses labels strictly for presentation.

```java
Map<String, String> labelsByCanonicalName = new HashMap<>();

labelsByCanonicalName.put(
    firstMBean.getCanonicalName(),
    "Cache primary — Hanoi");

labelsByCanonicalName.put(
    secondMBean.getCanonicalName(),
    "Cache primary — Ho Chi Minh City");
```

In multi-connection applications, an ObjectName identifies an MBean **within one MBeanServer**. Two different JVMs can completely legitimately have the same ObjectName. If a dashboard connects to multiple servers, the full routing key usually must include both the connection/server identifier and the ObjectName, such as `(connectionId, objectNameCanonical)`.

## 6. Interacting Properly with an MBean via ObjectName

### 6.1. Reading Attributes

After selecting an MBean, use the stored `ObjectName` object:

```java
ObjectName selected = option.objectName();

long hits = (Long) connection.getAttribute(
    selected, "HitCount");

System.out.println(option.label() + ": " + hits);
```

Console output uses the label, while the server call uses `selected` to target the exact MBean. The `Long` cast in the example assumes the MBean exposes `HitCount` as a `long`.

### 6.2. Invoking Operations

```java
connection.invoke(
    selected,
    "clear",
    new Object[0],
    new String[0]);
```

This call succeeds only if the MBean exposes a no-arg `clear()` operation and the client has permission to invoke it. Having an ObjectName and a display label in the UI does not grant the operation. In practice, verify MBean metadata, authorization, and operation side effects before allowing invocation.

### 6.3. Do Not Derive ObjectNames from Label Text

Wrong example:

```java
String displayName = "Cache primary — Hanoi";
ObjectName target = new ObjectName(displayName);
```

The string above does not conform to ObjectName syntax and will fail. Even if a label happened to contain `:` and `=` making it syntactically valid by coincidence, there is no guarantee that name exists in the MBeanServer or points to the MBean the user intended to select.

## 7. Standardizing How ObjectNames Are Displayed

### 7.1. getCanonicalName and getKeyProperty

For technical labels, prefer a format that makes the structure clear:

```java
ObjectName name = new ObjectName(
    "com.example.cache:region=hn,name=primary,type=CacheMetrics");

String stableIdentity = name.getCanonicalName();
String shortLabel = name.getKeyProperty("name");
```

`stableIdentity` is suitable for logging, storing mappings, or passing identifying data; `shortLabel` works as part of a label but does not guarantee uniqueness.

To show the exact ObjectName for diagnostic purposes, keep the canonical name as well, such as in a tooltip or detail pane:

```text
Label: Primary Cache — Hanoi
ObjectName: com.example.cache:name=primary,region=hn,type=CacheMetrics
```

### 7.2. Using Quoting When Values Are Complex

A key property value may need JMX quoting syntax when it contains special characters such as commas, equals signs, colons, or double quotes. Do not concatenate arbitrary values without respecting ObjectName rules.

```java
import javax.management.ObjectName;

String input = "Primary, Region A";

ObjectName name = new ObjectName(
    "com.example.cache:type=CacheMetrics,name="
    + ObjectName.quote(input));
```

`ObjectName.quote(...)` produces a validly quoted value representation. When reading `getKeyProperty("name")`, note that quotes may remain in the key property representation; use `ObjectName.unquote(...)` if the value is in quoted form and you need the original text.

Keep display data separate from data used to build identities: a user-entered label should not be concatenated directly into a server identifier without validation and identity governance rules.

### 7.3. Do Not Force Canonical Names as User-Facing Labels

Canonical names are great for technical matching, but can be verbose in a user interface. A common model:

```json
{
  "connectionId": "production-hn-01",
  "objectName": "com.example.cache:name=primary,region=hn,type=CacheMetrics",
  "displayName": "Primary Cache — Hanoi",
  "subtitle": "CacheMetrics · production-hn-01"
}
```

Here `connectionId` and `objectName` determine the target; `displayName` and `subtitle` determine presentation. If you rename the server's display name, switch languages, or adjust labels, keep the routing identity unchanged unless performing an actual migration.

## 8. Spring Framework JMX and Naming Issues

### 8.1. Spring Bean Names Differ from JMX ObjectNames

Configuration example:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class CacheJmxConfig {

    @Bean("primaryCacheMetrics")
    public CacheMetrics cacheMetrics() {
        return new CacheMetrics("Primary Cache — Hanoi");
    }

    @Bean
    public MBeanExporter cacheMBeanExporter(CacheMetrics cacheMetrics) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheMetrics,name=primary,region=hn",
            cacheMetrics));
        return exporter;
    }
}
```

Here:

- The Spring bean name is `primaryCacheMetrics`.
- The JMX ObjectName is `com.example.cache:type=CacheMetrics,name=primary,region=hn`.
- `DisplayName` is an attribute exposed by the `CacheMetrics` object: "Primary Cache — Hanoi".

All three can coexist and serve distinct purposes. When a user clicks a row in a management UI, the backend must use the ObjectName rather than the bean name or `DisplayName`.

### 8.2. Annotation Metadata Does Not Change Identity's Role

Spring also supports `@ManagedResource(objectName = "...")`, `@ManagedAttribute`, and assemblers to define both the name and the exported management interface. If the name comes from an annotation, **the final registered ObjectName value** remains the routing key used by JMX.

An MBean can also supply metadata such as:

```java
@ManagedResource(
    objectName = "com.example.cache:type=CacheMetrics,name=primary,region=hn",
    description = "Regional primary cache metrics")
```

`description` is descriptive metadata and may be chosen by a tool for display. It does not replace the ObjectName.

### 8.3. Connecting to Multiple MBeanServers

In a Spring application with multiple connection sources, there may be separate `MBeanServerConnection` instances for local servers or remote connectors. The same ObjectName on two connections does not necessarily refer to the same physical object.

```text
Connection A → ObjectName com.example.cache:type=CacheMetrics,name=primary
Connection B → ObjectName com.example.cache:type=CacheMetrics,name=primary
```

If the UI displays both, store the server/connection identity to route accurately. Showing the label "Cache primary" for both is valid for presentation, but creates ambiguity if the selection layer fails to retain the underlying identity.

## 9. Example Implementation of an MBean Selection Table

The following example builds a list of management targets with identity and label kept separate. It only derives labels from ObjectNames; MBean registration and connection setup are assumed complete.

```java
package com.example.monitoring;

import java.util.Comparator;
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class MBeanCatalog {

    public record Item(
        String objectNameCanonical,
        String displayName) {}

    public static List<Item> listCaches(
            MBeanServerConnection connection) throws Exception {

        ObjectName pattern = new ObjectName(
            "com.example.cache:type=CacheMetrics,*");

        return connection.queryNames(pattern, null).stream()
            .map(MBeanCatalog::toItem)
            .sorted(Comparator.comparing(Item::objectNameCanonical))
            .toList();
    }

    private static Item toItem(ObjectName name) {
        String instance = name.getKeyProperty("name");
        String region = name.getKeyProperty("region");

        if (instance == null || instance.isBlank()) {
            instance = "unknown";
        }

        String label = "Cache " + instance;
        if (region != null && !region.isBlank()) {
            label += " (" + region + ")";
        }

        return new Item(name.getCanonicalName(), label);
    }

    public static ObjectName resolve(Item selected)
            throws Exception {
        return new ObjectName(selected.objectNameCanonical());
    }
}
```

Usage flow:

```java
List<MBeanCatalog.Item> items = MBeanCatalog.listCaches(connection);

for (MBeanCatalog.Item item : items) {
    System.out.printf(
        "%s -> %s%n",
        item.displayName(),
        item.objectNameCanonical());
}

MBeanCatalog.Item selected = items.get(0);
ObjectName target = MBeanCatalog.resolve(selected);

Object hitCount = connection.getAttribute(target, "HitCount");
System.out.println(selected.displayName() + ": " + hitCount);
```

This is a simple example for a single connection. Production systems must handle an empty list before accessing `items.get(0)`, account for MBeans unregistered after listing, and include connection identity when multiple servers exist. Most importantly, `displayName()` is strictly for presentation, while `objectNameCanonical()` identifies the call target.

## 10. Common Misconceptions

**"The `name` key property is the MBean's standard display name."** False. `name` is just an arbitrary key in the ObjectName. It may be unreadable, unlocalized, or absent altogether.

**"`MBeanInfo.getDescription()` is always the UI title."** False. It is the MBean's description and may be used by an application for display, but JMX does not designate it as a display name.

**"A unique display name on screen is enough for routing."** Not necessarily. Labels can collide, be localized, or change with product requirements. Identity must be stored separately.

**"`ObjectName.getCanonicalName()` changes the target MBean."** No. It provides a canonical string representation for the exact same ObjectName.

**"ObjectName alone is enough to uniquely specify an MBean across an entire distributed system."** No. ObjectName provides identity within a single MBeanServer; multiple servers can contain identical ObjectNames.

**"You can use a Spring bean name directly to call `MBeanServer.getAttribute`."** Not directly. JMX uses the registered ObjectName, unless the application performs an explicit mapping from bean name to ObjectName.

**"Changing a Vietnamese label to an English one requires re-registering the MBean."** No. If only the presentation label changes, there is no need to alter the ObjectName.

## 11. Hands-On Exercise

A system exports three MBeans:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
com.example.cache:type=CacheMetrics,name=primary,region=hcm
com.example.cache:type=CacheMetrics,name=backup,region=hn
```

Requirements:

1. Use `queryNames("com.example.cache:type=CacheMetrics,*")` to retrieve the ObjectNames.
2. Read `getKeyProperty("name")` and `getKeyProperty("region")` for each ObjectName.
3. Build UI labels "Cache chính — Hà Nội", "Cache chính — TP. Hồ Chí Minh", and "Cache dự phòng — Hà Nội", while keeping the ObjectName as the identity.
4. Let the user pick an item, then use the original ObjectName to read the `HitCount` attribute if the MBean exposes it.
5. Change the labels to English without changing the ObjectName; verify that the previous selection still points to the right MBean.
6. Add a second connection/server with the same ObjectNames and explain why `connectionId` must be added to the routing key.

Expected mapping:

| UI Label | ObjectName Used for JMX Calls |
| --- | --- |
| Cache chính — Hà Nội | `com.example.cache:type=CacheMetrics,name=primary,region=hn` |
| Cache chính — TP. Hồ Chí Minh | `com.example.cache:type=CacheMetrics,name=primary,region=hcm` |
| Cache dự phòng — Hà Nội | `com.example.cache:type=CacheMetrics,name=backup,region=hn` |

If the key property order returned by `getCanonicalName()` differs from the example above, that is not an error: as long as the key/value pairs form the same ObjectName.

## 12. Check Your Understanding

1. **In JMX, what determines which MBean receives a `getAttribute` call?** The `ObjectName` passed to the call on the right `MBeanServerConnection`.
2. **Does `getKeyProperty("name")` read the `Name` attribute?** No; it reads a key property inside the ObjectName identifier.
3. **What do you call to read an MBean's description?** `connection.getMBeanInfo(objectName).getDescription()`.
4. **What is needed to read a display name exposed by an MBean?** An attribute such as `DisplayName` present in metadata and readable, then calling `getAttribute` with that exact name.
5. **Why should display names not be used as routing keys?** They can collide, change, and lack JMX identity semantics.
6. **How is `getCanonicalName()` useful?** It produces a canonical string representation with stable key property ordering for logging, storage, or technical comparison.
7. **Can two MBeanServers contain the same ObjectName?** Yes; therefore, multi-server UIs must retain connection identity alongside the ObjectName.
8. **When a user changes the label "Cache chính" to "Primary cache", does `MBeanExporter` need updating?** No, if only the presentation label changed.
9. **Is a pattern ObjectName from `queryNames` a concrete MBean?** No; it is a search expression, while the returned results are the list of concrete ObjectNames.

## 13. Key Takeaways

- **ObjectName is the routing identity**, consisting of a domain and key properties.
- **Display name is presentation data**; it can be derived from key properties, read from an MBean attribute/metadata, or configured in a dashboard.
- **Spring bean name, key property `name`, attribute `Name`, and display name** belong to different contexts.
- **`getCanonicalName()`** provides consistent ObjectName representation; **`getKeyProperty(...)`** reads identity components.
- When calling `MBeanServer` or `MBeanServerConnection`, **always use the real ObjectName** and keep connection identity when multiple servers exist.
- Switching languages, renaming labels, or changing UI layouts should never change routing keys.

Separating display names from routing names makes Spring JMX management tools both intuitive for operators and accurate in targeting the right MBean even when labels change or when the system spans multiple instances and JMX connections.