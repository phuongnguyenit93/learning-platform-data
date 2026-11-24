# Attributes, Operations, Constructors, and Notifications in MBeanInfo

## Objectives

After this lesson, you will be able to read `MBeanInfo` to see which attributes, management methods, constructors, and notifications an MBean exposes; understand how metadata differs from invoking actual operations; and use `MBeanServer` to discover and interact with MBeans according to the JMX contract.

## 1. What Is MBeanInfo?

Java Management Extensions (JMX) enables Java applications to expose monitoring information and management operations through **managed beans** (MBeans). `MBeanInfo`, located in `javax.management`, describes the management interface that an MBean presents to JMX tools.

An `MBeanInfo` object has a class name, description, and four metadata groups:

| Method on MBeanInfo | Element Type | Represents |
| --- | --- | --- |
| `getAttributes()` | `MBeanAttributeInfo[]` | Readable/writable attributes |
| `getOperations()` | `MBeanOperationInfo[]` | Invocable management methods |
| `getConstructors()` | `MBeanConstructorInfo[]` | Described constructor signatures |
| `getNotifications()` | `MBeanNotificationInfo[]` | Notification types that may be emitted |

These arrays may be empty. Metadata is used to **discover capabilities**; it does not hold current attribute values, does not execute operations, and is not a history of notifications.

`MBeanInfo` also provides `getClassName()`, `getDescription()`, and `getDescriptor()`. Descriptors supply extended metadata, especially in Model MBeans, MXBeans, or specialized management tools. Data exposed by an MBean can change in a Dynamic MBean; therefore, discovery tools should re-fetch `MBeanInfo` when updates are needed.

## 2. Attribute: Readable or Writable Management Data

`MBeanAttributeInfo` describes **name**, **Java type**, description, and access permissions:

- `getName()`: attribute name, e.g., `ActiveConnections`.
- `getType()`: type name, e.g., `int` or `java.lang.String`.
- `isReadable()`: whether the value can be retrieved with `MBeanServer.getAttribute`.
- `isWritable()`: whether the value can be set with `MBeanServer.setAttribute`.
- `isIs()`: indicates whether it uses an `isXxx()` style getter for booleans.

Standard MBean interface example:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clear();
}
```

For an MBean named `CacheMonitor`, JMX typically exposes two attributes `EntryCount` (read-only) and `Enabled` (read/write), along with the operation `clear`. Getters/setters matching Standard MBean conventions become attributes; you should not assume every Java method becomes an operation.

**Reading metadata differs from reading values:**

```java
MBeanInfo info = server.getMBeanInfo(objectName);
for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf("%s: %s, read=%s, write=%s%n",
            a.getName(), a.getType(), a.isReadable(), a.isWritable());
}

Object count = server.getAttribute(objectName, "EntryCount");
server.setAttribute(objectName, new Attribute("Enabled", false));
```

`getAttribute` / `setAttribute` call into the actual MBean and may throw `AttributeNotFoundException`, `InvalidAttributeValueException`, `MBeanException`, `ReflectionException`, or other errors depending on the operation. Call `setAttribute` only when the attribute is writable and the value has a compatible type. Do not confuse `isIs()` with `isReadable()`: `isIs()` reflects the boolean getter pattern, not a substitute for the read permission flag.

## 3. Operation: Invocable Management Actions

`MBeanOperationInfo` describes:

- `getName()`: operation name.
- `getReturnType()`: return type.
- `getSignature()`: `MBeanParameterInfo` entries containing the name, type, and description of each parameter.
- `getImpact()`: intended impact, one of `INFO`, `ACTION`, `ACTION_INFO`, `UNKNOWN`.

`impact` is only a descriptive classification, **not an authorization mechanism or a guarantee that an operation has no side effects**. Consult documentation and enforce access controls before invoking state-changing operations.

Example:

```java
for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName() + " -> " + op.getReturnType());
    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.println("  " + p.getName() + ": " + p.getType());
    }
}
server.invoke(objectName, "clear", new Object[0], new String[0]);
```

When an operation takes parameters, pass an array of values and **an array of corresponding type names, in the same order**:

```java
server.invoke(objectName, "resize",
        new Object[] { 256 },
        new String[] { "int" });
```

Type names in the signature must match the signature exposed by JMX (for example, `int` differs from `java.lang.Integer`). With overloads, the signature helps select the right operation. `invoke` may throw `ReflectionException`, `MBeanException`, `InstanceNotFoundException`, and other errors. Operations are not automatically invoked just because they appear in metadata.

## 4. Constructor: Metadata About Instantiation

`MBeanConstructorInfo` contains `getName()`, `getDescription()`, `getSignature()`, and `getDescriptor()`. `MBeanParameterInfo[]` in the signature indicates the names/types of constructor parameters.

```java
for (MBeanConstructorInfo ctor : info.getConstructors()) {
    System.out.println("Constructor: " + ctor.getName());
    for (MBeanParameterInfo p : ctor.getSignature()) {
        System.out.println("  " + p.getType() + " " + p.getName());
    }
}
```

Constructors **differ from operations**: constructors describe how instances are created, not management methods called via `invoke`. Some `MBeanServer` implementations support creating and registering MBeans via `createMBean` if the class and access permissions allow; many Spring applications register pre-created beans instead of letting clients instantiate them.

Do not infer that the constructor list is as complete as Java Reflection: metadata describes the exposed management contract; having a constructor in `MBeanInfo` does not guarantee a remote client can instantiate it successfully. Instantiation also depends on classloaders, available classes, the environment, and access policies.

## 5. Notification: Asynchronous Events Emitted by MBeans

`MBeanNotificationInfo` describes the notification types an MBean can emit:

- `getNotifTypes()`: list of notification type strings, e.g., `com.example.cache.cleared`.
- `getName()`: notification class name (typically `javax.management.Notification` or a subclass).
- `getDescription()`: description of the notifications.

```java
for (MBeanNotificationInfo n : info.getNotifications()) {
    System.out.println(n.getName() + ": "
            + java.util.Arrays.toString(n.getNotifTypes()));
}
```

An MBean can emit notifications if it supports `NotificationBroadcaster` / `NotificationEmitter`. To actually receive events, a client registers a `NotificationListener` via `MBeanServer.addNotificationListener` or an appropriate JMX connection:

```java
NotificationListener listener = (notification, handback) ->
        System.out.println(notification.getType() + ": "
                + notification.getMessage());

server.addNotificationListener(objectName, listener, null, null);
try {
    // Perform operations and handle events within the listener's lifecycle.
} finally {
    server.removeNotificationListener(objectName, listener);
}
```

A notification has `type`, `source`, `sequenceNumber`, `timeStamp`, `message`, and may have `userData`. Notification metadata is a list of **event-emission capabilities**, not a queue or log of past events. If an MBean does not emit notifications while a client has a listener registered, there will be no events to receive. Monitoring tools need to handle listener lifecycles, connection loss scenarios, and limit sensitive information in `userData`.

## 6. Complete Java Example: Registering an MBean and Inspecting MBeanInfo

The following example can be saved as `JmxInfoDemo.java` and run with JDK 17+ (JMX is part of the JDK, requiring no external libraries). The `CacheMonitorMBean` interface and `CacheMonitor` class are declared as public nested types so Standard MBean recognizes the contract.

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.*;

public class JmxInfoDemo {
    public interface CacheMonitorMBean {
        int getEntryCount();
        boolean isEnabled();
        void setEnabled(boolean value);
        void clear();
    }

    public static class CacheMonitor
            extends NotificationBroadcasterSupport
            implements CacheMonitorMBean {
        private boolean enabled = true;
        private int entryCount = 3;
        private long sequence;

        @Override public int getEntryCount() { return entryCount; }
        @Override public boolean isEnabled() { return enabled; }
        @Override public void setEnabled(boolean value) { enabled = value; }

        @Override public void clear() {
            entryCount = 0;
            sendNotification(new Notification(
                "com.example.cache.cleared", this, ++sequence,
                System.currentTimeMillis(), "Cache cleared"));
        }

        @Override public MBeanNotificationInfo[] getNotificationInfo() {
            return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                    new String[] { "com.example.cache.cleared" },
                    Notification.class.getName(),
                    "Fired when cache is cleared")
            };
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName("com.example:type=CacheMonitor");
        server.registerMBean(new CacheMonitor(), name);

        try {
            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("MBean class: " + info.getClassName());

            for (MBeanAttributeInfo a : info.getAttributes()) {
                System.out.printf("Attribute %s [%s] R=%s W=%s%n",
                    a.getName(), a.getType(),
                    a.isReadable(), a.isWritable());
            }
            for (MBeanOperationInfo op : info.getOperations()) {
                System.out.printf("Operation %s -> %s%n",
                    op.getName(), op.getReturnType());
            }
            for (MBeanConstructorInfo c : info.getConstructors()) {
                System.out.println("Constructor " + c.getName());
            }
            for (MBeanNotificationInfo n : info.getNotifications()) {
                System.out.println("Notifications "
                    + Arrays.toString(n.getNotifTypes()));
            }

            NotificationListener listener = (n, handback) ->
                System.out.println("Received: " + n.getType());
            server.addNotificationListener(name, listener, null, null);
            try {
                System.out.println("Count before: "
                    + server.getAttribute(name, "EntryCount"));
                server.setAttribute(name, new Attribute("Enabled", false));
                server.invoke(name, "clear", new Object[0], new String[0]);
                System.out.println("Count after: "
                    + server.getAttribute(name, "EntryCount"));
            } finally {
                server.removeNotificationListener(name, listener);
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Run:

```bash
javac JmxInfoDemo.java
java JmxInfoDemo
```

The output illustrates two attributes, the `clear` operation, one notification type, and the log `Received: com.example.cache.cleared`. Constructors listed depend on how the MBean provides metadata; they do not depend on the number of constructors visible via Reflection.

In Spring applications, MBeans exported through Spring's JMX mechanism or registered manually with `MBeanServer` can still be observed using the same APIs above. Annotations such as `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` help Spring determine the metadata to export when using a Spring JMX exporter; that is a separate configuration layer from the pure JMX `MBeanInfo` discovery API.

## 7. Distinction and Application

| Management Tool Question | Metadata Component | Related Runtime Call |
| --- | --- | --- |
| Which configuration/state can be viewed/edited? | `MBeanAttributeInfo` | `getAttribute`, `setAttribute` |
| What actions can the MBean be asked to perform? | `MBeanOperationInfo` | `invoke` |
| Which instantiation methods does the MBean expose? | `MBeanConstructorInfo` | `createMBean` when supported |
| Which events can be subscribed to? | `MBeanNotificationInfo` | `addNotificationListener` |

Practical notes:

1. Always retrieve metadata for the exact registered `ObjectName`; do not use the class name in place of the object name.
2. The interface exposed by `MBeanInfo` may differ from the Java class's public API, especially with Standard MBeans, MXBeans, and Dynamic MBeans.
3. `MBeanInfo` does not replace authorization, authentication, TLS, or access restrictions for remote JMX. Only enable remote JMX in environments configured with security.
4. With dynamic metadata, management tools should handle cases where information changes between reading metadata and executing an action.

## 8. Self-Check

1. Why does `MBeanInfo.getAttributes()` not return current attribute values?
2. What three aspects do `isReadable()`, `isWritable()`, and `isIs()` describe?
3. When invoking an overloaded operation via `MBeanServer.invoke`, why is passing a signature required?
4. Does `MBeanConstructorInfo` mean a client can always create an MBean remotely?
5. Why might `MBeanNotificationInfo` list a notification type yet a listener still receives no events?

**Takeaway:** `MBeanInfo` is the description of the JMX management contract; attributes represent state, operations represent actions, constructors describe instantiation, and notifications represent event-emission capabilities.