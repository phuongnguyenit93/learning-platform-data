# ObjectName in Queries, Listeners, and Proxies

> **Topic:** Spring Framework JMX  
> **Knowledge group:** ObjectName  
> **Lesson:** ObjectName in Queries, Listeners, and Proxies

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain \`ObjectName\` as the MBean identifier in an \`MBeanServer\`, and distinguish between an **exact name** and a **name pattern**.
- Use \`MBeanServerConnection.queryNames()\` to find MBeans by \`ObjectName\` pattern, combining it with \`QueryExp\` when additional filtering is needed.
- Attach and detach a \`NotificationListener\` to/from an MBean via \`ObjectName\`, understanding that listener registration belongs to the MBean/connection and resource lifecycle.
- Create client proxies via the JMX API or Spring's \`MBeanProxyFactoryBean\`, understanding how a proxy translates method calls into JMX operations.
- Evaluate the impact of dynamic names, multiple instances, remote connections, missing MBeans, access permissions, and registration changes.

## 2. Foundational Model: Three Ways to Use an ObjectName

In JMX, \`ObjectName\` identifies an MBean registered in an \`MBeanServer\`. Basic structure:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Examples:

\`\`\`text
learning.jmx:type=WorkerPool,name=main
learning.jmx:type=WorkerPool,name=background
learning.jmx:type=Cache,name=users
\`\`\`

In three common scenarios, the role of \`ObjectName\` differs slightly:

\`\`\`text
             MBeanServer / MBeanServerConnection
                          |
       +------------------+-------------------+
       |                  |                   |
       v                  v                   v
   queryNames()    addNotificationListener()  JMX proxy
   + name pattern      + exact ObjectName    + exact ObjectName
       |                  |                   |
       v                  v                   v
  Find multiple     Monitor one MBean       Call MBean like
  registered MBeans & receive notifications a Java interface
\`\`\`

- **Querying:** an \`ObjectName\` can be a **pattern** to retrieve a list of multiple actual names.
- **Listeners:** when registering a listener, \`ObjectName\` is normally the **exact name** of an MBean emitting notifications.
- **Proxies:** a proxy typically targets **one exact ObjectName**, representing one concrete MBean. A proxy does not automatically query all MBeans matching a pattern.

Importantly, \`ObjectName\` does not hold a direct reference to a Spring bean. It is the JMX name that the MBeanServer uses to route requests to the registered resource.

## 3. Exact ObjectNames and Patterns

### 3.1. Exact Name

\`\`\`java
ObjectName mainPool = new ObjectName(
    "learning.jmx:type=WorkerPool,name=main"
);
\`\`\`

Use this name when you want to:

- Read an attribute: \`connection.getAttribute(mainPool, "ActiveCount")\`.
- Invoke an operation: \`connection.invoke(mainPool, "reset", new Object[0], new String[0])\`.
- Attach a listener: \`connection.addNotificationListener(mainPool, listener, filter, handback)\`.
- Create a proxy: \`newProxyInstance(connection, mainPool, WorkerPoolMBean.class, true)\`.

An exact name contains no wildcards and must match an MBean registered in the right MBeanServer.

### 3.2. Pattern in the Domain

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.*:type=WorkerPool,name=*"
);
\`\`\`

The \`*\` in the domain can match multiple character segments, and \`*\` in the value \`name=*\` matches multiple property values.

### 3.3. Pattern on the Property List

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);
\`\`\`

The trailing \`,*\` allows the MBean to have additional key properties, such as \`name\`, \`node\`, or \`region\`. This is a common pattern when you only care about the resource type.

Compare:

\`\`\`text
learning.jmx:type=WorkerPool
\`\`\`

is an exact name having strictly the \`type\` property, whereas:

\`\`\`text
learning.jmx:type=WorkerPool,*
\`\`\`

is a pattern allowing additional properties. An MBean named \`learning.jmx:type=WorkerPool,name=main\` does not match the first exact name, but matches the second pattern.

### 3.4. \`*\` and \`?\` in Patterns

- \`*\`: matches a character sequence of any length.
- \`?\`: matches a single character.
- An \`ObjectName\` pattern can contain wildcards in the domain or values, and property-list patterns have their own syntax.

\`\`\`java
ObjectName byDomain = new ObjectName("learning.*:*");
ObjectName byName = new ObjectName(
    "learning.jmx:type=WorkerPool,name=worker-?"
);
ObjectName anyPool = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);
\`\`\`

For a key property value containing special characters such as commas, equals signs, colons, quotes, or wildcards meant as literal data characters, use \`ObjectName.quote(value)\` when building the name. Wildcards can become pattern operators if interpreted outside the proper quoted context.

## 4. Querying MBeans with queryNames()

Primary API:

\`\`\`java
Set<ObjectName> queryNames(
    ObjectName name,
    QueryExp query
) throws IOException;
\`\`\`

On a local \`MBeanServer\`, the corresponding call does not declare checked \`IOException\`; on the \`MBeanServerConnection\` interface it declares \`IOException\` because the connection may be remote.

- \`name\`: an exact name or pattern; \`null\` means no name restriction.
- \`query\`: an additional JMX query filter; \`null\` means no extra expression filtering.
- Return value: a \`Set<ObjectName>\` of MBeans registered and matching the query at the time of execution.
- \`queryNames\` returns **names**, whereas \`queryMBeans\` returns \`ObjectInstance\` objects containing both name and class information.

### 4.1. Finding All WorkerPools

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Example output:

\`\`\`text
learning.jmx:name=background,type=WorkerPool
learning.jmx:name=main,type=WorkerPool
\`\`\`

\`getCanonicalName()\` sorts key properties into canonical form. It may differ from the order in which you wrote the \`ObjectName\`, yet it represents the same name. Do not rely on \`Set\` iteration order when rendering UIs or reports; sort if you want deterministic output.

### 4.2. Filtering by Domain and Instance

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,name=worker-*,*"
);

Set<ObjectName> names = server.queryNames(pattern, null);
\`\`\`

This pattern is useful when instances are named with sequential numbers: \`worker-1\`, \`worker-2\`, or environment-qualified names.

### 4.3. Combining QueryExp to Filter Attributes

JMX supports query expressions via \`javax.management.Query\`. For example, finding only WorkerPools whose \`ActiveCount\` attribute is greater than 10:

\`\`\`java
import javax.management.Query;
import javax.management.QueryExp;

ObjectName poolPattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);

QueryExp busyPools = Query.gt(
    Query.attr("ActiveCount"),
    Query.value(10)
);

Set<ObjectName> names = server.queryNames(
    poolPattern,
    busyPools
);
\`\`\`

Here:

1. \`poolPattern\` narrows the candidate set by name.
2. \`QueryExp\` evaluates the condition against each MBean's attribute.
3. Only MBeans satisfying both conditions appear in the result.

For this query to be useful, candidate MBeans must expose an \`ActiveCount\` attribute of a suitable numeric type. Do not treat \`QueryExp\` as general-purpose SQL or a query engine over Spring beans; it operates solely on exposed JMX information.

### 4.4. Checking a Name Before Use

\`\`\`java
ObjectName exact = new ObjectName(
    "learning.jmx:type=WorkerPool,name=main"
);

if (!server.isRegistered(exact)) {
    throw new IllegalStateException("MBean not registered: " + exact);
}

Object activeCount = server.getAttribute(
    exact,
    "ActiveCount"
);
\`\`\`

A concurrency note: \`isRegistered\` followed by \`getAttribute\` are two separate operations. An MBean can be unregistered between them. Clients must still handle \`InstanceNotFoundException\` during actual operations.

## 5. Standard MBean Example to Illustrate Queries and Listeners

An MBean that emits notifications on reset events can extend \`NotificationBroadcasterSupport\` and implement \`WorkerPoolMBean\`.

### 5.1. MBean Contract

\`\`\`java
package example.jmx;

public interface WorkerPoolMBean {
    int getActiveCount();

    void reset();
}
\`\`\`

### 5.2. Implementation with Notifications

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class WorkerPool extends NotificationBroadcasterSupport
        implements WorkerPoolMBean {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int activeCount;

    public WorkerPool(int activeCount) {
        this.activeCount = activeCount;
    }

    @Override
    public int getActiveCount() {
        return activeCount;
    }

    @Override
    public void reset() {
        int oldValue = activeCount;
        activeCount = 0;

        Notification notification = new AttributeChangeNotification(
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker pool active count reset",
            "ActiveCount",
            "int",
            oldValue,
            0
        );
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            AttributeChangeNotification.ATTRIBUTE_CHANGE
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                AttributeChangeNotification.class.getName(),
                "Worker pool active-count changes"
            )
        };
    }
}
\`\`\`

This MBean exposes a read-only attribute \`ActiveCount\`, an operation \`reset()\`, and a notification of type \`jmx.attribute.change\`. Notifications are a mechanism **actively emitted** by the implementation via \`sendNotification\`; merely mutating a Java field does not automatically emit a notification.

### 5.3. Registering Two Instances with Different ObjectNames

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName main = new ObjectName(
    "learning.jmx:type=WorkerPool,name=main"
);
ObjectName background = new ObjectName(
    "learning.jmx:type=WorkerPool,name=background"
);

server.registerMBean(new WorkerPool(12), main);
server.registerMBean(new WorkerPool(4), background);
\`\`\`

After registration, the pattern \`learning.jmx:type=WorkerPool,*\` finds both. However, to attach a listener or create a proxy for \`main\`, you must use \`main\` — an exact name.

## 6. ObjectName When Registering a NotificationListener

An MBean can emit a \`Notification\` to report management events: configuration changes, errors, resource states, task completion, or custom events.

The call:

\`\`\`java
connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

Where:

| Parameter | Purpose |
|---|---|
| \`objectName\` | Name of the MBean emitting notifications; must point to an appropriate MBean. |
| \`listener\` | \`NotificationListener\` object receiving the \`handleNotification\` callback. |
| \`filter\` | Accepts/ignores notifications based on criteria; may be \`null\`. |
| \`handback\` | Context object supplied by the client and returned in the callback; may be \`null\`. |

### 6.1. Attaching a Listener to an MBean

\`\`\`java
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    System.out.println(
        "source=" + notification.getSource()
            + ", type=" + notification.getType()
            + ", message=" + notification.getMessage()
            + ", context=" + handback
    );
};

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("jmx.attribute.change");

server.addNotificationListener(
    main,
    listener,
    filter,
    "main-pool-listener"
);

try {
    // Trigger reset() -> MBean sends notification.
    server.invoke(
        main,
        "reset",
        new Object[0],
        new String[0]
    );
} finally {
    server.removeNotificationListener(
        main,
        listener,
        filter,
        "main-pool-listener"
    );
}
\`\`\`

When \`reset\` runs, the implementation dispatches the notification through the broadcaster. The callback may run according to the broadcaster's dispatch mechanism; **never assume the callback always runs on the caller's thread or finishes before \`invoke\` returns**. With default \`NotificationBroadcasterSupport\`, notification dispatch uses a synchronous executor unless another executor is supplied, while a remote client adds its own transport layer.

### 6.2. Why Using the Right ObjectName Matters

If a listener is attached to \`main\`, it does not automatically receive notifications from \`background\`, even though both MBeans have the same type and domain.

\`\`\`text
main ObjectName ─────── listener A
background ObjectName ─ listener B

queryNames(pattern) -> {main, background}
\`\`\`

To monitor all MBeans matching a pattern, you can:

1. Call \`queryNames(pattern, null)\` to obtain the current list.
2. Iterate through each **exact ObjectName**.
3. Attach the listener to each notification-capable MBean.
4. Keep track of registrations so listeners can be removed when no longer needed.

Querying by pattern does not automatically maintain listeners on MBeans registered **after** the query runs. To track newly added or removed MBeans, you can listen to notifications from \`MBeanServerDelegate\` or implement a refresh mechanism for the MBean set.

### 6.3. MBeanServerDelegate for Registrations and Unregistrations

JMX provides the system MBean \`JMImplementation:type=MBeanServerDelegate\` (constant \`MBeanServerDelegate.DELEGATE_NAME\`) that emits notifications when MBeans are registered or unregistered.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener registryListener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification event) {
            ObjectName changed = event.getMBeanName();

            System.out.println(
                event.getType() + " " + changed
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);

// When stopping monitoring:
// server.removeNotificationListener(
//     MBeanServerDelegate.DELEGATE_NAME,
//     registryListener
// );
\`\`\`

You can combine callbacks from the Delegate with \`pattern.apply(changed)\` to decide whether to attach or detach a listener for a matching MBean. Because a query snapshot and registration notifications are not a single atomic operation, production implementations should guard against races and handle duplicate subscriptions.

### 6.4. Registering with the ObjectName of a Listener MBean

Besides the overload taking a Java \`NotificationListener\`, JMX also has an overload:

\`\`\`java
server.addNotificationListener(
    broadcasterName,
    listenerMBeanName,
    filter,
    handback
);
\`\`\`

This overload can only be used when the **listener is itself a registered MBean implementing \`NotificationListener\`** as required by JMX. Do not confuse \`listenerMBeanName\` with the broadcaster's \`ObjectName\`. In typical client code, the overload accepting a \`NotificationListener\` object directly is simpler.

## 7. Managing Listener and Connection Lifecycles

Attaching a listener creates a stateful callback registration. Forgetting to remove it can retain unwanted references or keep processing events after the consumer component has stopped.

Safe pattern:

\`\`\`java
NotificationListener listener = (n, h) ->
    System.out.println(n.getMessage());

server.addNotificationListener(
    main,
    listener,
    null,
    null
);

try {
    // Work requiring MBean monitoring
} finally {
    server.removeNotificationListener(
        main,
        listener
    );
}
\`\`\`

If using the \`removeNotificationListener(name, listener, filter, handback)\` overload, you must pass the exact matching listener/filter/handback tuple. The overload accepting only \`name, listener\` removes all matching registrations of that listener on the MBean, per the API contract.

Cases to consider:

- **MBean unregistered:** a listener attached to an old MBean does not automatically transfer to a new instance even if the new instance reuses the same ObjectName. Track lifecycle if resubscription is needed.
- **Remote connector disconnected:** callbacks may stop arriving; detect connection loss and re-establish listeners after reconnecting.
- **Slow listener processing:** do not run heavy work directly inside the callback; offload events to an appropriate executor/queue and manage backlog.
- **MBean does not support notifications:** registration may be rejected, e.g., with \`RuntimeOperationsException\` or an appropriate JMX error depending on the implementation. Inspect \`getMBeanInfo(name).getNotifications()\` before attaching when necessary.
- **Duplicate or missed notifications:** design idempotent handling if notifications drive monitoring; do not treat JMX notifications as a durable message broker.

## 8. ObjectName When Creating a JMX Proxy

A JMX proxy lets a client invoke Java methods through an interface. The proxy routes calls to the MBean named by \`ObjectName\`.

### 8.1. JMX API: JMX.newMBeanProxy()

For a Standard MBean:

\`\`\`java
import javax.management.JMX;
import javax.management.MBeanServerConnection;

MBeanServerConnection connection = server;

WorkerPoolMBean proxy = JMX.newMBeanProxy(
    connection,
    main,
    WorkerPoolMBean.class,
    true
);

int active = proxy.getActiveCount();
System.out.println("active=" + active);

proxy.reset();
\`\`\`

The \`true\` argument requests a proxy supporting the \`NotificationEmitter\` interface so notification listeners can be managed through the proxy when the underlying MBean supports notifications.

Key points:

- \`main\` is the **exact** ObjectName of a single MBean.
- \`WorkerPoolMBean.class\` describes the interface expected by the client.
- \`getActiveCount()\` typically maps to the JMX operation of **reading attribute** \`ActiveCount\`.
- \`reset()\` maps to the JMX **invoke operation** \`reset\`.
- The proxy holds no WorkerPool state; state resides in the server-side MBean.
- Method calls can fail if the MBean disappears, signatures mismatch, or the remote connection breaks. Proxies do not guarantee automatic reconnection.

\`\`\`text
Java caller
   |
   v
WorkerPoolMBean proxy.reset()
   |
   v
JMX invocation handler
   |
   v
MBeanServerConnection.invoke(main, "reset", [], [])
   |
   v
WorkerPool MBean server-side
\`\`\`

For MXBeans, use \`JMX.newMXBeanProxy(...)\` and follow MXBean type mappings; do not assume Standard MBean proxies and MXBean proxies convert every value identically.

### 8.2. Spring: MBeanProxyFactoryBean

Spring provides \`org.springframework.jmx.access.MBeanProxyFactoryBean\`, creating a proxy from an \`ObjectName\` and a management interface.

Example client interface:

\`\`\`java
package example.jmx;

public interface WorkerPoolOperations {
    int getActiveCount();
    void reset();
}
\`\`\`

Proxy configuration:

\`\`\`java
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class JmxClientConfiguration {

    @Bean
    public MBeanProxyFactoryBean workerPoolProxy(
            MBeanServerConnection connection
    ) throws Exception {
        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(connection);
        factory.setObjectName(
            "learning.jmx:type=WorkerPool,name=main"
        );
        factory.setProxyInterface(
            WorkerPoolOperations.class
        );

        return factory;
    }
}
\`\`\`

Once Spring initializes the FactoryBean, the bean injected as \`WorkerPoolOperations\` will be a JMX proxy:

\`\`\`java
import org.springframework.stereotype.Component;

@Component
public class PoolDashboard {

    private final WorkerPoolOperations pool;

    public PoolDashboard(WorkerPoolOperations pool) {
        this.pool = pool;
    }

    public void printAndReset() {
        System.out.println(pool.getActiveCount());
        pool.reset();
    }
}
\`\`\`

\`MBeanProxyFactoryBean\` uses \`ObjectName\` to target the MBean and maps interface calls according to appropriate metadata. Only use interfaces whose methods/attributes are actually exposed by the MBean; declaring extra methods on a Java client interface does not give the server-side MBean extra operations.

If the application uses a remote \`MBeanServerConnection\`, configure that connection via a JMX connector or an appropriate \`MBeanServerConnectionFactoryBean\`. Local Spring exporters and remote clients share the same ObjectName model, but the connection must point to the server hosting the target MBean.

### 8.3. Configuring Proxies with Exact Names, Not Patterns

This is suitable for querying:

\`\`\`text
learning.jmx:type=WorkerPool,*
\`\`\`

When creating a proxy, however, choose a concrete name:

\`\`\`text
learning.jmx:type=WorkerPool,name=main
\`\`\`

If you need one proxy per existing WorkerPool, the client can call \`queryNames(pattern, null)\` and then construct a proxy for each returned ObjectName.

\`\`\`java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import javax.management.JMX;
import javax.management.ObjectName;

ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);

Set<ObjectName> discovered =
    connection.queryNames(pattern, null);

Map<ObjectName, WorkerPoolMBean> proxies =
    new LinkedHashMap<>();

for (ObjectName name : discovered) {
    WorkerPoolMBean proxy = JMX.newMBeanProxy(
        connection,
        name,
        WorkerPoolMBean.class,
        false
    );
    proxies.put(name, proxy);
}
\`\`\`

This is a **snapshot** of the MBeans at query time. MBeans registered afterward will not appear automatically in the map. If an MBean is removed, the created proxy may still exist on the client side, but calls through it will fail.

## 9. Pattern Matching: Examples That Match and Do Not Match

Suppose the server has these MBeans:

\`\`\`text
learning.jmx:type=WorkerPool,name=main
learning.jmx:type=WorkerPool,name=background
learning.jmx:type=WorkerPool,name=main,node=n1
learning.jmx:type=Cache,name=users
system.jmx:type=WorkerPool,name=main
\`\`\`

| Pattern | Matching MBeans | Explanation |
|---|---|---|
| \`learning.jmx:type=WorkerPool,name=main\` | Only WorkerPool main without extra properties | Exact name. |
| \`learning.jmx:type=WorkerPool,name=*\` | WorkerPool main and background without extra properties | Value pattern, but fixed property list. |
| \`learning.jmx:type=WorkerPool,name=*,*\` | All three WorkerPools in domain learning.jmx | Allows extra key properties. |
| \`learning.jmx:type=WorkerPool,*\` | All three WorkerPools in domain learning.jmx | Constrains only \`type\`. |
| \`*:type=WorkerPool,*\` | All WorkerPools across both domains | Domain wildcard + property-list pattern. |
| \`learning.jmx:type=Cache,*\` | Cache users | Filters by type Cache. |

An \`ObjectName\` with the same key properties in a different order still represents the same name if the corresponding values match. For example, \`learning.jmx:name=main,type=WorkerPool\` is equivalent to \`learning.jmx:type=WorkerPool,name=main\`.

## 10. Query Then Subscribe: Pattern for Monitoring Multiple MBeans

Problem: monitor notifications for every \`WorkerPool\` in the \`learning.jmx\` domain.

\`\`\`java
import java.util.HashSet;
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class WorkerPoolSubscriptions
        implements AutoCloseable {

    private final MBeanServerConnection connection;
    private final ObjectName pattern;
    private final NotificationListener listener;
    private final Set<ObjectName> subscriptions =
        new HashSet<>();

    public WorkerPoolSubscriptions(
            MBeanServerConnection connection
    ) throws Exception {
        this.connection = connection;
        this.pattern = new ObjectName(
            "learning.jmx:type=WorkerPool,*"
        );
        this.listener = (notification, handback) ->
            System.out.println(
                notification.getType() + ": "
                    + notification.getMessage()
            );
    }

    public void subscribeCurrent() throws Exception {
        for (ObjectName name :
                connection.queryNames(pattern, null)) {
            if (subscriptions.contains(name)) {
                continue;
            }

            connection.addNotificationListener(
                name,
                listener,
                null,
                null
            );
            subscriptions.add(name);
        }
    }

    @Override
    public void close() {
        for (ObjectName name : subscriptions) {
            try {
                connection.removeNotificationListener(
                    name,
                    listener
                );
            } catch (Exception ignored) {
                // MBean already unregistered or remote disconnected.
            }
        }
        subscriptions.clear();
    }
}
\`\`\`

Usage:

\`\`\`java
try (WorkerPoolSubscriptions subscriptions =
         new WorkerPoolSubscriptions(connection)) {
    subscriptions.subscribeCurrent();
    // Perform work or keep process running to receive events.
}
\`\`\`

Note: this example subscribes to **currently existing MBeans** and releases registered listeners upon closing. It does not yet cover dynamic subscriptions when new MBeans appear, reconnection handling, or races between querying and registration. In production systems, use notifications from \`MBeanServerDelegate\` or a refresh strategy, while avoiding duplicate listeners and pruning subscriptions when MBeans disappear.

## 11. Spring NotificationListenerBean and Listener Mapping

Besides registering listeners directly via the JMX API, Spring JMX export supports configuring notification listeners for MBeans managed by an exporter. The structure typically includes:

- \`NotificationListenerBean\`: describes the callback, filter, and list of mapped object names.
- \`MBeanExporter.setNotificationListeners(...)\`: supplies listener configuration to the exporter.
- \`mappedObjectNames\`: specifies the names of the MBeans to which the listener will be registered.

Illustrative example:

\`\`\`java
import java.util.Map;
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
class SpringNotificationConfig {

    @Bean
    MBeanExporter exporter(
            WorkerPool monitoredPool
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "learning.jmx:type=WorkerPool,name=main",
            monitoredPool
        ));

        NotificationListener listener =
            (notification, handback) ->
                System.out.println(notification.getMessage());

        NotificationListenerBean subscription =
            new NotificationListenerBean(listener);

        subscription.setMappedObjectNames(
            "learning.jmx:type=WorkerPool,name=main"
        );

        exporter.setNotificationListeners(subscription);
        return exporter;
    }
}
\`\`\`

This example assumes the \`WorkerPool\` bean is managed by Spring and suitable for export as an MBean. Do not simultaneously configure another exporter attempting to register the same ObjectName. Spring manages registration/listener lifecycles according to exporter configuration, but **do not assume** that \`mappedObjectNames\` is a full query language replacing \`MBeanServerConnection.queryNames\` in every scenario.

On the client side, a Spring application can still use \`MBeanClientInterceptor\` or \`MBeanProxyFactoryBean\` to invoke MBeans by ObjectName. Server-side listener configuration and client-side proxies solve two different needs: receiving notifications versus executing operations and attribute access.

## 12. Impact When an ObjectName Changes

An \`ObjectName\` is meaningful only within the registry of one \`MBeanServer\`. Renaming, unregistering/re-registering, or switching MBeanServers can break active references.

| Change | Query by Pattern | Attached Listener | Created Proxy |
|---|---|---|---|
| New MBean registered with matching name | Subsequent queries will see it | Listener not attached automatically | Proxy not created automatically |
| MBean unregistered | Subsequent queries will not see it | Registration on old instance becomes invalid | Calls may fail with \`InstanceNotFoundException\` (often wrapped by proxy) |
| MBean re-registered with same name | Subsequent queries see it again | May need to re-register listener | Proxy can continue routing by name, but interface/contract compatibility must hold |
| ObjectName changes a property | Depends on whether pattern matches new name | Listener on old name does not follow to new name | Proxy continues targeting old name |
| Client switches MBeanServer | Query results reflect the new server | Old listener remains on old connection/server | Must configure the appropriate connection |

Therefore, choose ObjectName rules that are stable, unique, and structured. Avoid random values that change on every startup if clients rely on fixed names; when multiple instances are needed, put \`instance\`, \`node\`, or \`region\` dimensions in key properties.

## 13. Local and Remote: Same ObjectName, Different Connection

\`\`\`text
Local:
MBeanServer -> ObjectName -> MBean

Remote:
JMXConnector -> MBeanServerConnection -> ObjectName -> MBean
\`\`\`

The name \`learning.jmx:type=WorkerPool,name=main\` **does not contain a hostname or remote endpoint**. Selecting the host/JVM is done through the connection, and then \`ObjectName\` selects the MBean within that server.

Remote client example:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection remote =
        connector.getMBeanServerConnection();

    ObjectName pattern = new ObjectName(
        "learning.jmx:type=WorkerPool,*"
    );

    for (ObjectName name :
            remote.queryNames(pattern, null)) {
        System.out.println(name);
    }
}
\`\`\`

This snippet assumes a JMX connector is already running and reachable. Exporting a Spring bean via JMX does not automatically enable a remote connector. When exposing remote access, configure proper authentication, authorization, and network security, especially for MBeans with state-mutating operations.

Notifications from a remote client carry added risks of disconnection and latency. Monitor connector health, re-establish subscriptions after reconnection, and do not treat notifications as a guaranteed durable data source.

## 14. Common Errors and Root-Cause Diagnosis

### Query Returns No MBeans

Check:

1. Is the connection pointing to the right JVM/MBeanServer where the exporter registered?
2. Was the MBean actually registered with the expected \`ObjectName\`?
3. Did the pattern omit \`,*\` when the MBean has additional key properties?
4. Are domain, keys, and values spelled and cased accurately?
5. Are there special characters in values requiring \`ObjectName.quote()\`?

Example:

\`\`\`java
ObjectName strict = new ObjectName(
    "learning.jmx:type=WorkerPool"
);
ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);
\`\`\`

An MBean that also has \`name=main\` does not match \`strict\`, but can match \`pattern\`.

### Listener Receives No Notifications

- Does the MBean support \`NotificationBroadcaster\`/\`NotificationEmitter\` and expose proper notification metadata?
- Was the listener attached to the exact right **ObjectName**?
- Is a \`NotificationFilter\` accidentally blocking the event type?
- Does the implementation actually invoke \`sendNotification\` or its equivalent notification mechanism?
- Was the MBean unregistered and re-registered?
- For remote clients, is the connection still alive?

### Proxy Call Fails

- Does the proxy point to the right server and ObjectName?
- Does the proxy interface match the exposed methods/attributes?
- Does the operation have matching signature, parameter count, and return type?
- Was the MBean unregistered or replaced with a different version?
- Did the Spring exporter publish attributes per the annotations/assembler expected by the client?

### Query Matches Multiple MBeans, Yet Proxy Accesses Only One

This is by design: a query returns a **set of names**, whereas a proxy represents **one name**. If an application needs a multi-instance dashboard, build a collection of proxies from \`queryNames\` results and refresh it when the registry changes.

## 15. Hands-On Exercises

Suppose the system has:

\`\`\`text
app.monitoring:type=Cache,name=users,node=a
app.monitoring:type=Cache,name=orders,node=a
app.monitoring:type=Cache,name=users,node=b
app.monitoring:type=Queue,name=emails,node=a
\`\`\`

**Question 1.** Write a pattern to get all Caches:

\`\`\`java
ObjectName allCaches = new ObjectName(
    "app.monitoring:type=Cache,*"
);
\`\`\`

**Question 2.** Write a pattern to get the \`users\` Cache across all nodes:

\`\`\`java
ObjectName userCaches = new ObjectName(
    "app.monitoring:type=Cache,name=users,*"
);
\`\`\`

**Question 3.** Can \`userCaches\` be used as the ObjectName for a single \`JMX.newMBeanProxy\` representing all instances?

No. A JMX proxy targets a single MBean. Call \`queryNames(userCaches, null)\`, then create a proxy for each exact \`ObjectName\` in the results.

**Question 4.** If a listener is attached to \`app.monitoring:type=Cache,name=users,node=a\`, will it automatically receive notifications from node \`b\`?

No. You must register a separate listener for node \`b\`'s MBean or use another notification aggregation layer.

**Question 5.** If node \`a\` re-registers the same ObjectName, what must be handled?

Queries will see the new MBean under the same name, but the old listener registration is not guaranteed to remain valid. Clients should monitor lifecycle and re-attach listeners; proxies must verify the new MBean's contract.

## 16. Key Takeaways

\`\`\`text
ObjectName exact:
    Selects exactly one MBean
    -> attribute / operation / listener / proxy

ObjectName pattern:
    Selects a set of MBeans when querying
    -> queryNames(pattern, QueryExp?)
    -> Set<ObjectName> exact
    -> listener or proxy per concrete name
\`\`\`

**Practical rule:** use **patterns to discover**, use **exact ObjectNames to interact**, and manage **MBean registration, listener, and proxy lifecycles** because the registry can change while the application is running.