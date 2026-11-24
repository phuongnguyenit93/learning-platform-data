# Practice: Naming ObjectNames with a Naming Strategy in Spring Framework JMX

## 1. Lab Objectives

In Java Management Extensions (JMX), each MBean is registered in an `MBeanServer` under an `ObjectName`, such as `com.example.orders:type=Queue,name=Primary`. The ObjectName is the key that JConsole, VisualVM, JMX clients, monitoring collectors, and Spring's `MBeanProxyFactoryBean` use to locate the right management resource.

Spring Framework supports exporting MBeans from Spring-managed beans via `MBeanExporter`. Instead of hard-coding every ObjectName on each individual bean, you can implement or configure an **`ObjectNamingStrategy`** to generate names according to a consistent rule. This lab creates two management beans, defines the exporter map, applies a naming strategy, and verifies the resulting names in the MBeanServer.

You will learn:

- The `domain:key=value` structure and how ObjectName distinguishes MBeans.
- The difference between a Spring bean name, an exporter map key, and a JMX ObjectName.
- How to use the `org.springframework.jmx.export.naming.ObjectNamingStrategy` interface.
- How to wire the strategy into `MBeanExporter.setNamingStrategy(...)`.
- How to design domains and key properties by application, resource type, and instance.
- How to handle special characters and collisions when multiple MBeans share names.
- How to verify results with `MBeanServer.queryNames`/`getMBeanInfo`.

**Expected outcome:** the application registers two MBeans with stable, readable names:

```text
com.example.ordering:type=Queue,name=Primary
com.example.ordering:type=Cache,name=Primary
```

## 2. Why Do We Need ObjectNamingStrategy?

Without a centralized strategy, an application may end up with inconsistent naming styles:

```text
app:type=Queue
com.example.cache:name=main
myModule:bean=cacheManagement
```

These names may be valid, but they are difficult to manage in large systems. If each team uses a different convention, JMX collectors have to query multiple domains/keys and can break after refactoring bean names.

`ObjectNamingStrategy` answers the question **"Which ObjectName should this management object be registered under?"**. It does not decide which methods are exposed; that belongs to JMX MBean conventions, `MBeanInfoAssembler`, or annotation metadata.

```text
Spring beans
    |
    v
MBeanExporter
    |
    +-- Bean selection: setBeans / autodetection
    +-- ObjectNamingStrategy: ObjectName of each bean
    +-- MBeanInfoAssembler: attributes / operations
    v
MBeanServer
    |
    v
JMX clients
```

## 3. ObjectName and the Uniqueness Rule

A JMX ObjectName has the structure:

```text
domain:key1=value1,key2=value2,...
```

Example:

```text
com.example.ordering:type=Queue,name=Primary
```

- `com.example.ordering`: domain.
- `type=Queue`: MBean category.
- `name=Primary`: instance identifier.

Within **a single MBeanServer**, every ObjectName must be unique. Two MBeans with the same ObjectName cannot be registered simultaneously; doing so triggers `InstanceAlreadyExistsException` or behavior governed by `RegistrationPolicy`.

The order of key properties does not affect identity:

```java
ObjectName a = new ObjectName(
    "com.example.ordering:type=Queue,name=Primary"
);
ObjectName b = new ObjectName(
    "com.example.ordering:name=Primary,type=Queue"
);
System.out.println(a.equals(b)); // true
```

Do not reorder `type`/`name` to avoid collisions. You must change the domain or an actual key property value when two resources are distinct.

## 4. Distinguishing Three Types of Names

| Type | Example | Role |
| --- | --- | --- |
| Spring bean name | `queueManagement` | Identifies the bean inside `ApplicationContext` |
| Exporter map key | `Queue:Primary` | Input provided by the configurator to the exporter |
| JMX ObjectName | `com.example.ordering:type=Queue,name=Primary` | Actual name registered in `MBeanServer` |

The map key can hold a full ObjectName or a logical identifier. When using a custom strategy, the key becomes the input to `getObjectName(managedBean, beanKey)`. Therefore, document the key format and validate formatting errors at startup.

**Note:** if a bean is exported via an annotation-based naming strategy instead of the strategy you created, the ObjectName may be read from `@ManagedResource`. The chosen strategy must match the exporter type and configuration path; do not assume every annotation overrides a custom naming strategy.

## 5. Create Two Illustrative Management Beans

First, create a queue management MBean following the Standard MBean convention:

```java
package com.example.management;

public interface QueueMonitorMBean {
    int getPendingCount();
    void requestRefresh();
}
```

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger pending = new AtomicInteger(5);

    @Override
    public int getPendingCount() {
        return pending.get();
    }

    @Override
    public void requestRefresh() {
        // Illustration only; real apps should use a bounded task.
        pending.set(0);
    }
}
```

Next, create a cache management bean:

```java
package com.example.management;

public interface CacheMonitorMBean {
    long getEntryCount();
}
```

```java
package com.example.management;

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public long getEntryCount() {
        return 42L;
    }
}
```

These are two valid Standard MBeans following the convention where class `QueueMonitor` implements `QueueMonitorMBean` and class `CacheMonitor` implements `CacheMonitorMBean`. When `MBeanExporter` receives these objects, it can register them under the standard JMX contract. The example does not require a reflection assembler to expose all public methods.

In real applications, management beans should delegate to services and return safe operational data rather than containing business logic or secrets.

## 6. Create a Custom ObjectNamingStrategy

We choose a map key of the form `type:name`, such as `Queue:Primary` and `Cache:Primary`. The strategy parses the key and constructs an ObjectName.

```java
package com.example.management;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class ApplicationObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String domain;

    public ApplicationObjectNamingStrategy(String domain) {
        if (domain == null || !domain.matches("[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("Invalid JMX domain");
        }
        this.domain = domain;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        if (beanKey == null) {
            throw new IllegalArgumentException("beanKey is required");
        }
        int delimiter = beanKey.indexOf(':');
        if (delimiter <= 0 || delimiter == beanKey.length() - 1) {
            throw new IllegalArgumentException(
                "Expected bean key type:name, got " + beanKey
            );
        }

        String type = beanKey.substring(0, delimiter);
        String name = beanKey.substring(delimiter + 1);
        if (!type.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid type: " + type);
        }

        return new ObjectName(
            domain + ":type=" + type + ",name=" + ObjectName.quote(name)
        );
    }
}
```

Explanation:

1. The constructor accepts the configured domain and validates syntax according to application rules.
2. `getObjectName(Object managedBean, String beanKey)` is the contract method of Spring's naming strategy.
3. The part before `:` is the MBean type; the part after is the instance name.
4. `ObjectName.quote(name)` protects characters such as commas or colons inside the property value.
5. `ObjectName` validates JMX syntax, and `MBeanExporter` uses the result for registration.

The regex in the example is an **internal convention**, not the entirety of valid JMX syntax. The `type` value is constrained so it cannot become a wildcard or a string that alters the key structure. In production, identifiers passed into the strategy must be controlled and must not contain sensitive information.

## 7. Wire the Strategy into MBeanExporter

```java
package com.example.config;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import com.example.management.ApplicationObjectNamingStrategy;
import com.example.management.CacheMonitor;
import com.example.management.QueueMonitor;

@Configuration
public class JmxManagementConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            QueueMonitor queueMonitor, CacheMonitor cacheMonitor) {
        Map<String, Object> beans = new LinkedHashMap<>();
        beans.put("Queue:Primary", queueMonitor);
        beans.put("Cache:Primary", cacheMonitor);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(beans);
        exporter.setNamingStrategy(
            new ApplicationObjectNamingStrategy("com.example.ordering")
        );
        return exporter;
    }
}
```

With this design, the exporter asks the strategy for each bean's ObjectName during registration. Expected output:

```text
Queue:Primary -> com.example.ordering:type=Queue,name="Primary"
Cache:Primary -> com.example.ordering:type=Cache,name="Primary"
```

**Important detail:** `ObjectName.quote("Primary")` produces a quoted representation for the key value, meaning the actual name in the example is `name="Primary"`. In JMX, quoted values and unquoted values can differ in representation/semantics, so when writing a client with an exact ObjectName, use the exact canonical name returned by the strategy instead of hand-typing an unquoted version.

If you want the name to appear strictly unquoted as `name=Primary` with always-safe inputs, you can construct the ObjectName using a `Hashtable<String,String>` from values validated against JMX rules. This lab uses quoting consistently to illustrate handling arbitrary values and verifies the exact generated ObjectName.

## 8. Use the Same Name on the Client Side

To avoid hard-coding mismatched names between server and client, you can extract the name-generation rule into a shared function:

```java
ObjectNamingStrategy naming =
    new ApplicationObjectNamingStrategy("com.example.ordering");

ObjectName queueName = naming.getObjectName(
    queueMonitor,
    "Queue:Primary"
);

ObjectName cacheName = naming.getObjectName(
    cacheMonitor,
    "Cache:Primary"
);
```

The client can call `MBeanServer.getAttribute(queueName, "PendingCount")`. If the client is remote, establish a stable contract for domains and keys, or discover via a pattern and select the exact MBean. Do not require the client to instantiate all application beans just to generate names; the example illustrates reusing the strategy internally, whereas an independent client module should use a small naming contract class with no dependencies on business objects.

## 9. Verify Registered MBeans

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.ordering:*"
);

Set<ObjectName> registered = server.queryNames(pattern, null);
registered.stream()
    .map(ObjectName::getCanonicalName)
    .sorted()
    .forEach(System.out::println);
```

If the exporter registered into the platform MBeanServer, you will see the ObjectNames generated by the strategy. If you configured a dedicated MBeanServer, query that server instead of calling the default platform server.

Checking an exact name:

```java
ObjectName queueName = new ApplicationObjectNamingStrategy(
    "com.example.ordering"
).getObjectName(queueMonitor, "Queue:Primary");

System.out.println(server.isRegistered(queueName));
System.out.println(server.getMBeanInfo(queueName).getClassName());
System.out.println(server.getAttribute(queueName, "PendingCount"));
```

This snippet assumes `queueMonitor` is the instance used in configuration. When debugging naming issues, print `getCanonicalName()` of the actual ObjectName rather than guessing from the Spring bean name.

## 10. Test with JUnit 5

You can unit test the naming strategy directly without starting a Spring context:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ApplicationObjectNamingStrategyTest {
    private final ApplicationObjectNamingStrategy naming =
        new ApplicationObjectNamingStrategy("com.example.ordering");

    @Test
    void namesQueueAndCacheDifferently() throws Exception {
        ObjectName queue = naming.getObjectName(null, "Queue:Primary");
        ObjectName cache = naming.getObjectName(null, "Cache:Primary");

        assertNotEquals(queue, cache);
        assertEquals("com.example.ordering", queue.getDomain());
        assertEquals("Queue", queue.getKeyProperty("type"));
    }

    @Test
    void handlesSpecialCharactersInName() throws Exception {
        ObjectName name = naming.getObjectName(
            null, "Queue:payments,west"
        );
        assertFalse(name.isPattern());
        assertEquals("com.example.ordering", name.getDomain());
        assertNotNull(name.getKeyProperty("name"));
    }

    @Test
    void rejectsMalformedKey() {
        assertThrows(IllegalArgumentException.class,
            () -> naming.getObjectName(null, "QueueOnly"));
    }
}
```

Here the implementation does not use `managedBean`, so passing `null` in the unit test is valid for this illustrative strategy alone. For other strategies that inspect the target class or annotations, you must pass a real object.

Testing the MBean structure after Spring startup is also important, because unit tests on the strategy do not prove the exporter actually registered the bean or chose the right MBeanServer.

## 11. Configure Domain per Environment

Instead of hard-coding the domain in `@Bean`, read it from a property:

```properties
jmx.management.domain=com.example.ordering.dev
```

In production:

```properties
jmx.management.domain=com.example.ordering
```

Configuration:

```java
import org.springframework.beans.factory.annotation.Value;

@Bean
public MBeanExporter exporter(
        QueueMonitor queue, CacheMonitor cache,
        @Value("${jmx.management.domain}") String domain) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "Queue:Primary", queue,
        "Cache:Primary", cache
    ));
    exporter.setNamingStrategy(
        new ApplicationObjectNamingStrategy(domain)
    );
    return exporter;
}
```

The `jmx.management.domain` property is a **custom property of this example**, not a special property that Spring Framework automatically applies to every exporter. Passing the value into the naming strategy is what makes it take effect.

Do not change the domain across environments merely to avoid collisions if the environments run in separate JVMs. Stable names help reuse dashboards. When modules share the same server, app/module identity is what needs to be distinguished most.

## 12. Built-In Naming Strategies in Spring

You do not always need to write your own class. Spring JMX includes naming strategies such as:

- `KeyNamingStrategy`: uses keys or a configuration mapping to look up ObjectNames.
- `MetadataNamingStrategy`: uses JMX annotation metadata, specifically `@ManagedResource` combined with `JmxAttributeSource`.
- `IdentityNamingStrategy`: generates an identifier based on the class and instance identity.

Depending on your Spring Framework version and needs, choose a built-in strategy when it satisfies your naming rules. A custom strategy is useful when your organization's domain/module/instance naming requirements cannot be expressed directly via mappings/annotations.

**Warning:** identity-based strategies can produce names that change per instance and restart, making fixed-name dashboards/proxies difficult to use. For long-lived monitored MBeans, stable naming is usually better.

## 13. How Does Annotation-Based Naming Differ from a Custom Strategy?

With an annotation-based exporter:

```java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ordering:type=Queue,name=Main"
)
public class QueueManagement {
    // @ManagedAttribute, @ManagedOperation...
}
```

`MetadataNamingStrategy` can read the ObjectName from the annotation. Conversely, the custom strategy in this lab generates names from the map key `Queue:Primary`. Do not supply multiple conflicting name sources and expect the exporter to guess your preferred "right name" without knowing the precedence rules.

If an organization uses annotation-based export broadly, enforce conventions in annotations and write tests verifying ObjectNames. If a small group of endpoints needs centrally configured names, explicit maps and a custom strategy are easier to control.

## 14. Handling Duplicate ObjectNames

If a strategy returns the same ObjectName for two different beans, the exporter can encounter a registration error:

```text
javax.management.InstanceAlreadyExistsException:
  com.example.ordering:type=Queue,name="Primary"
```

Possible causes:

- Two different map keys where the strategy loses the distinguishing information.
- Two instances having the same `type`/`name` in the same MBeanServer.
- Another exporter already registered the same ObjectName.
- An old MBean was not unregistered after redeploy.
- Spring profiles/config created duplicate beans.

The preferred fix is **fixing naming so each resource has a unique name**, such as adding an `instance` or `application` key where appropriate.

Spring provides `RegistrationPolicy`:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

`FAIL_ON_EXISTING` surfaces collisions; `IGNORE_EXISTING` skips the new MBean if one exists; `REPLACE_EXISTING` can replace another module's MBean. Do not use `REPLACE_EXISTING` by default to mask naming errors.

## 15. Avoid Putting Sensitive Information in Key Values

ObjectNames are frequently displayed in JConsole and `queryNames`, so never include:

- Passwords, access tokens, session tokens, or API keys.
- Emails, phone numbers, or sensitive account/customer identifiers.
- Database connection strings with credentials.
- Long business payloads or object-specific secrets.

Example anti-pattern:

```text
com.example.auth:type=Session,token=eyJhbGciOiJI...
```

Instead, use opaque non-sensitive IDs or an aggregate MBean:

```text
com.example.auth:type=SessionMetrics,name=Global
```

`ObjectName.quote` only escapes syntax characters; it does not encrypt or mask data. Managing JMX connector permissions and limiting metadata content remain essential.

## 16. Stable Naming for Multiple Instances

If two `QueueMonitor` beans share the same server:

```text
com.example.ordering:type=Queue,name=Primary,instance=worker-a
com.example.ordering:type=Queue,name=Primary,instance=worker-b
```

The strategy can be extended to generate `instance` from deployment configuration. Use stable identifiers if clients depend on names; avoid PIDs or random timestamps unless you genuinely need to track ephemeral MBeans.

If two replicas run in **two different JVMs** with separate MBeanServers, identical ObjectNames do not collide directly. In that case, clients distinguish them via connection/instance metadata outside JMX.

## 17. Common Pitfalls and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| MBean does not appear under expected name | Exporter not using intended strategy | Check `setNamingStrategy` and export path |
| JConsole shows quoted key | Strategy uses `ObjectName.quote` | Use exact canonical name; align client/server |
| `MalformedObjectNameException` | Invalid key/domain | Validate and quote values properly |
| `InstanceAlreadyExistsException` | Strategy produces duplicate name | Add explicit identity; fix owner/exporter |
| MBean has a different name after restart | Identity/bean name/instance ID varies | Use stable domain/keys |
| Client proxy cannot find MBean | Proxy ObjectName differs from exported name | Share naming contract and check `queryNames` |
| Only class name appears instead of desired type | Using default/Identity naming strategy | Configure custom/Metadata/KeyNamingStrategy properly |
| Enabling autodetection causes duplicate names | Newly detected bean lacks distinguishing name | Narrow scope or add key properties |
| Changing domain breaks monitoring | ObjectName is a management API | Update dashboards/proxies via a migration plan |

## 18. Practice Checklist

1. Define a clear domain namespace by app/module.
2. Decide on key properties such as `type`, `name`, `application`, and `instance`.
3. Avoid secrets/PII in ObjectNames.
4. Choose a map key format with a stable schema or use annotation mapping.
5. Write `ObjectNamingStrategy` and validate inputs.
6. Quote dynamic values containing special JMX characters; stay consistent with clients.
7. Configure `MBeanExporter.setBeans` and `setNamingStrategy` in one place.
8. Confirm target beans are JMX-compliant or have a suitable assembler.
9. Check `MBeanServer.queryNames` after startup.
10. Add naming unit tests and `MBeanInfo` integration tests.
11. Choose `RegistrationPolicy` to surface collisions rather than hiding errors.
12. Document ObjectNames as a stable API for monitoring and JMX proxies.

## 19. Summary Mental Model

```text
Spring ApplicationContext
       |
       +-- QueueMonitor bean
       +-- CacheMonitor bean
       |
       v
MBeanExporter.setBeans
       |
       +-- Queue:Primary
       +-- Cache:Primary
       |
       v
ApplicationObjectNamingStrategy
       |
       +-- domain: com.example.ordering
       +-- type/name properties
       |
       v
ObjectName
       |
       v
MBeanServer register
       |
       v
JConsole / collector / JMX proxy
```

**Conclusion:** using `ObjectNamingStrategy` is the way to design JMX names that are **consistent, verifiable, and stable**. Clearly define input keys, domain, key properties, and quoting/validation policies, then wire the strategy into `MBeanExporter`. Afterward, verify the actual ObjectNames in the MBeanServer, test collisions/lifecycle, and keep the naming contract stable for clients. A naming strategy decides **what name an MBean is known by**, not which operations it exposes or who has JMX access permissions.
