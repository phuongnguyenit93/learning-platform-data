# Operation Parameters and @ManagedOperationParameter

## Learning Objectives

After this lesson, you will be able to:

- Declare a JMX operation using \`@ManagedOperation\` in Spring Framework.
- Use \`@ManagedOperationParameter\` and \`@ManagedOperationParameters\` to describe the name and meaning of each parameter.
- Distinguish **parameter descriptive metadata** from the **actual Java parameter types and signature** used when invoking an operation.
- Read \`MBeanOperationInfo\` and \`MBeanParameterInfo\` from \`MBeanServer\` to inspect metadata.
- Invoke parameterized operations using JConsole or \`MBeanServer.invoke\` with the correct order, values, and signature.
- Recognize issues involving data types, overloading, operation side effects, and JMX invocation errors in a Spring application.

## 1. What Is an Operation in Spring JMX?

JMX (Java Management Extensions) allows management tools like JConsole to interact with a running Java application. An MBean can provide attributes to read/write state and operations to execute actions.

In Spring Framework, \`@ManagedOperation\` marks a method to be exposed as a **JMX operation**. With annotation-based exporting, the class is typically annotated with \`@ManagedResource\`, and \`AnnotationMBeanExporter\` or \`@EnableMBeanExport\` is responsible for reading metadata and registering the bean with \`MBeanServer\`.

Example of an operation that limits cache size:

\`\`\`java
@ManagedOperation(description = "Set the maximum cache size")
public void resizeCache(int newMaxSize) {
    // Modify cache state
}
\`\`\`

When a method has parameters, JMX tools need to know: the operation name, parameter order, **Java type** of each parameter, and the values passed on invocation. The variable name \`newMaxSize\` in Java source does not necessarily appear automatically as a meaningful display name on the client. Spring provides \`@ManagedOperationParameter\` to add parameter descriptive metadata.

## 2. What Is @ManagedOperationParameter Used For?

\`@ManagedOperationParameter\` belongs to the package:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
\`\`\`

It defines descriptive information for a JMX operation parameter, primarily:

| Annotation Attribute | Meaning | Example |
| --- | --- | --- |
| \`name\` | Parameter name displayed to management tools | \`"newMaxSize"\` |
| \`description\` | Explanation of the parameter's meaning | \`"Maximum number of cached entries"\` |

When a method has multiple parameters, \`@ManagedOperationParameters\` is used to group multiple metadata declarations in the **exact Java parameter order**.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Adjust cache configuration")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "newMaxSize",
        description = "Maximum number of entries; must be positive"),
    @ManagedOperationParameter(
        name = "evictImmediately",
        description = "Whether to evict entries above the new limit now")
})
public void configureCache(int newMaxSize, boolean evictImmediately) {
    // implementation
}
\`\`\`

In this example, the first annotation describes \`int newMaxSize\`; the second annotation describes \`boolean evictImmediately\`.

**Important point:** \`@ManagedOperationParameter\` does not change the method's Java types, does not convert values automatically, does not validate numeric ranges, and does not grant permission to invoke the operation. Parameter types are still determined by the method signature: \`int\`, \`boolean\`, \`java.lang.String\`, etc. Business validation must reside in the implementation or an appropriate control layer.

## 3. Complete Example with @ManagedResource and Two Parameters

Create a \`CacheAdmin\` class as the management object in a Spring application. This class can be registered as a Spring bean and exported via the JMX annotation exporter.

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.jmx:type=CacheAdmin,name=primary",
        description = "Cache administration through Spring JMX")
public class CacheAdmin {

    private volatile int maxSize = 100;
    private volatile boolean evictionEnabled = true;

    @ManagedAttribute(description = "Maximum cache size")
    public int getMaxSize() {
        return maxSize;
    }

    @ManagedAttribute(description = "Whether eviction is enabled")
    public boolean isEvictionEnabled() {
        return evictionEnabled;
    }

    @ManagedOperation(description = "Configure cache size and eviction")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
                name = "newMaxSize",
                description = "New positive capacity limit"),
        @ManagedOperationParameter(
                name = "enableEviction",
                description = "Enable or disable automatic eviction")
    })
    public String configure(int newMaxSize, boolean enableEviction) {
        if (newMaxSize <= 0) {
            throw new IllegalArgumentException(
                    "newMaxSize must be greater than zero");
        }

        this.maxSize = newMaxSize;
        this.evictionEnabled = enableEviction;
        return "Updated maxSize=" + newMaxSize
                + ", evictionEnabled=" + enableEviction;
    }
}
\`\`\`

Here:

- \`@ManagedResource\` marks the class as a managed resource and specifies the JMX \`ObjectName\`.
- \`@ManagedAttribute\` exposes current information via \`MaxSize\` and \`EvictionEnabled\`.
- \`@ManagedOperation\` exposes the \`configure\` method as an operation.
- \`@ManagedOperationParameters\` describes the two parameters in order.
- The \`int\` and \`boolean\` types belong to the Java method signature; clients must pass them accurately when invoking.
- The method body is responsible for validation and changing state.

Both properties in the example only have getters annotated with \`@ManagedAttribute\`, so operators read current state via JMX without directly writing these attributes. Changes are made through a validated operation, which is suitable when ensuring multiple values are updated in a single action.

The example uses \`volatile\` to ensure visibility of each field. When atomic consistency across multiple fields is required, the implementation must use an appropriate synchronization or snapshot strategy; two separate \`volatile\` assignments do not form a transaction.

## 4. Registering the Bean in ApplicationContext

Use \`@EnableMBeanExport\` to enable Spring Framework's annotation export mechanism.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class JmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheAdmin cacheAdmin() {
        return new CacheAdmin();
    }
}
\`\`\`

\`CacheAdmin\` is a Spring bean registered via \`@Bean\`, so \`@Component\` on the class is not required. The \`@EnableMBeanExport\` configuration enables annotation-based export support and uses the \`platformMBeanServer\` bean to register eligible managed resources.

The example uses the platform \`MBeanServer\` so JConsole can connect to the right JVM. If the application already has an MBean server or an exporter configured by Spring Boot, inspect and reuse the existing mechanism to avoid duplicate \`ObjectName\` registration.

To run with plain Java and a Spring context:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {
            System.out.println("PID: " + ProcessHandle.current().pid());
            System.out.println("JMX ready");
            System.in.read(); // Keep context alive while testing JConsole.
        }
    }
}
\`\`\`

When the context closes, the Spring-managed exporter performs lifecycle cleanup for the MBeans it is responsible for registering.

## 5. Inspecting Parameter Metadata with MBeanInfo

The JMX API lets you query the operations and parameters that the server actually exposes. This is more reliable than relying only on source annotations or a single client's UI.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectOperations {

    public static void inspect() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=CacheAdmin,name=primary");

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.printf(
                    "Operation: %s, returns %s%n",
                    operation.getName(),
                    operation.getReturnType());

            for (MBeanParameterInfo parameter : operation.getSignature()) {
                System.out.printf(
                        "  %s : %s — %s%n",
                        parameter.getName(),
                        parameter.getType(),
                        parameter.getDescription());
            }
        }
    }
}
\`\`\`

For \`configure(int, boolean)\`, the expected metadata has two parameters in order:

\`\`\`text
Operation: configure, returns java.lang.String
  newMaxSize : int — New positive capacity limit
  enableEviction : boolean — Enable or disable automatic eviction
\`\`\`

\`name\` and \`description\` information comes from the annotations. \`type\` comes from the Java signature, not from \`description\`.

If the operation has not been registered by the exporter, \`getMBeanInfo\` will not find the \`ObjectName\`. If parameter metadata lacks descriptions, check whether \`@ManagedOperationParameters\` is on the same method as \`@ManagedOperation\`, check element ordering, and check whether the configured assembler actually reads Spring annotations.

## 6. Invoking a Parameterized Operation via MBeanServer.invoke

The JMX API has the form:

\`\`\`java
Object invoke(
        ObjectName name,
        String operationName,
        Object[] params,
        String[] signature
);
\`\`\`

In our example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.jmx:type=CacheAdmin,name=primary");

Object result = server.invoke(
        name,
        "configure",
        new Object[]{250, false},
        new String[]{"int", "boolean"}
);

System.out.println(result);
System.out.println(server.getAttribute(name, "MaxSize"));
System.out.println(server.getAttribute(name, "EvictionEnabled"));
\`\`\`

Note four conditions:

1. \`ObjectName\` must match the exact registered MBean name.
2. \`"configure"\` must match the operation name.
3. \`params\` must match the exact count, order, and value types accepted by the implementation. In Java, \`250\` and \`false\` are autoboxed to \`Integer\` and \`Boolean\` in \`Object[]\`.
4. \`signature\` contains the **declared Java parameter type names**, e.g. \`"int"\` and \`"boolean"\`, not \`"java.lang.Integer"\` and \`"java.lang.Boolean"\` when the method uses primitives.

\`@ManagedOperationParameter(name="newMaxSize")\` does not allow a client to invoke using a map like \`{"newMaxSize": 250}\`. JMX \`invoke\` still uses positional arrays. Parameter names serve metadata and UI display; they do not change the protocol to named arguments.

If the signature is wrong or missing, the client typically receives an error indicating no matching operation/signature was found (which may be surfaced via \`ReflectionException\` and an accompanying cause), even though a method with the same name exists in Java source.

## 7. Invoking via JConsole

While the Spring context is running and the MBean is exported:

1. Open \`jconsole\` from a matching JDK.
2. Select the JVM by the PID printed by the application.
3. Go to the **MBeans** tab and find \`com.example.jmx:type=CacheAdmin,name=primary\`.
4. Open the **Operations** section and locate \`configure\`.
5. Observe the two parameters in the order \`newMaxSize\` and \`enableEviction\`; the tool may also display descriptions.
6. Enter \`250\` for the \`int\` parameter and \`false\` for the \`boolean\` parameter.
7. Invoke the operation and view the return value if displayed.
8. Read \`MaxSize\` and \`EvictionEnabled\` in the **Attributes** section to verify that the state changed.

JConsole or other JMX tools may display parameter names differently depending on how they read metadata, their version, and the MBean type. Some tools require string input and convert it to Java types according to the signature; users should check error messages if conversion fails.

Do not test directly against production data when an operation has side effects. In particular, operations like clearing caches, resetting statistics, triggering jobs, or changing configuration can affect in-flight requests.

## 8. Single Parameter and Multiple Parameters

For a method with only one parameter, you can declare \`@ManagedOperationParameter\` directly:

\`\`\`java
@ManagedOperation(description = "Pause processing")
@ManagedOperationParameter(
        name = "reason",
        description = "Reason recorded for the pause")
public void pause(String reason) {
    // ...
}
\`\`\`

When using multiple parameters, declare the container annotation explicitly:

\`\`\`java
@ManagedOperation(description = "Schedule an administrative task")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "taskName",
        description = "Name of the task to schedule"),
    @ManagedOperationParameter(
        name = "delaySeconds",
        description = "Delay before execution, in seconds"),
    @ManagedOperationParameter(
        name = "force",
        description = "Whether to override a pending task")
})
public void scheduleTask(
        String taskName,
        long delaySeconds,
        boolean force) {
    // ...
}
\`\`\`

Metadata order must match the order of \`String taskName\`, \`long delaySeconds\`, \`boolean force\`. If you reorder parameters in the method, update the metadata accordingly. The Java compiler does not verify whether \`description\` matches the parameter's meaning; that is the responsibility of the management API author.

The corresponding invoke signature:

\`\`\`java
server.invoke(
        name,
        "scheduleTask",
        new Object[]{"refresh-index", 10L, false},
        new String[]{
            "java.lang.String",
            "long",
            "boolean"
        }
);
\`\`\`

The illustrative \`scheduleTask\` method must actually be declared and exposed on the registered MBean; an operation cannot be invoked just because its name appears in an invoke snippet.

## 9. Complex Parameters: DTOs, Enums, Collections, and Data Limitations

Not every Java type is convenient for JMX clients. JMX operations need data types that both the MBean server and client can handle.

Cases:

| Java Parameter | What to Watch Out For |
| --- | --- |
| Primitives \`int\`, \`long\`, \`boolean\` | Easy to display and pass over JMX |
| \`String\` | Common, needs content validation |
| \`ObjectName\` | Standard JMX type, requires a valid name |
| \`enum\` | Standard MBeans may require the class on the client; MXBeans have rules mapping to strings |
| Custom DTO | Standard MBean remote clients may need the corresponding class and compatible serialization |
| \`Map\`, collection | Requires understanding exact types and JMX/MXBean mapping; do not assume every client can input them |
| Generic parameter with unclear type | Easily causes ambiguity in mapping and metadata |

\`@ManagedOperationParameter\` only describes the parameter's name/meaning; it does not automatically convert a DTO into \`CompositeData\`. If you need to pass data structures compatible with general-purpose JMX clients, consider MXBeans or a management contract using simple types.

For operations requiring multiple parameters, prefer a small, easy-to-understand management API with value validation. For example, \`setThreshold(int percent)\` with a description noting the 0–100 range is easier to operate than a complex configuration DTO when the management requirement is simply adjusting a threshold.

## 10. Operation Overloading and Exact Signatures

Java allows method overloading:

\`\`\`java
@ManagedOperation
@ManagedOperationParameter(name = "key", description = "Cache key")
public void evict(String key) {
    // ...
}

@ManagedOperation
@ManagedOperationParameter(name = "groupId", description = "Numeric group ID")
public void evict(int groupId) {
    // ...
}
\`\`\`

JMX can distinguish operations with the same name by their parameter type lists, but support and rendering of overloads can vary across JMX clients and MBean types. When invoking via \`MBeanServer.invoke\`, the signature is decisive:

\`\`\`java
server.invoke(
        name, "evict",
        new Object[]{"product:42"},
        new String[]{"java.lang.String"});
\`\`\`

or:

\`\`\`java
server.invoke(
        name, "evict",
        new Object[]{42},
        new String[]{"int"});
\`\`\`

In an administrative API where users operate via JConsole, giving operations distinct names such as \`evictByKey\` and \`evictByGroupId\` is sometimes easier to use than multiple overloads with the same name. This is a design choice to reduce confusion, not a hard Java limitation.

## 11. Do Parameter Names and Descriptions Affect Invocation?

No. You should distinguish three layers of information:

- **Java method signature**: method name and parameter types/order, which determine how JMX \`invoke\` locates the operation.
- **Spring annotation metadata**: \`name\` and \`description\` on \`@ManagedOperationParameter\`, which help clients/operators understand each parameter.
- **Runtime values**: the actual data passed in, validated and used by the implementation.

For example, the same Java method:

\`\`\`java
public void setLimit(int value)
\`\`\`

can be described with \`@ManagedOperationParameter(name="maximumItems", description="...")\`. The JMX signature remains \`setLimit(int)\`. Changing metadata \`maximumItems\` to \`limit\` does not require clients to change \`new String[]{"int"}\`.

Conversely, changing the type \`int\` to \`long\` changes the JMX signature even if the annotation keeps the same parameter name.

## 12. Testing Annotation Metadata in ApplicationContext

To verify that the exporter actually reads and publishes metadata:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ManagedOperationParameterTest {

    @Test
    void operationContainsParameterMetadata() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jmx:type=CacheAdmin,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            MBeanOperationInfo configure = null;
            for (MBeanOperationInfo operation : info.getOperations()) {
                if ("configure".equals(operation.getName())) {
                    configure = operation;
                    break;
                }
            }

            assertNotNull(configure);
            MBeanParameterInfo[] params = configure.getSignature();

            assertEquals(2, params.length);
            assertEquals("newMaxSize", params[0].getName());
            assertEquals("int", params[0].getType());
            assertEquals("enableEviction", params[1].getName());
            assertEquals("boolean", params[1].getType());

            server.invoke(name, "configure",
                    new Object[]{250, false},
                    new String[]{"int", "boolean"});

            assertEquals(250, server.getAttribute(name, "MaxSize"));
            assertEquals(
                    false,
                    server.getAttribute(name, "EvictionEnabled"));
        }
    }
}
\`\`\`

The test requires appropriate Spring Framework JMX and JUnit Jupiter dependencies. It demonstrates three things: the Spring context registered the MBean, the operation metadata has the right order/names/types, and \`invoke\` affects the managed instance.

In a test suite running in parallel, use a dedicated \`MBeanServer\` instead of the shared platform server, or assign distinct \`ObjectName\` values per fixture. Tests using the same \`ObjectName\` on the platform MBean server easily conflict with \`InstanceAlreadyExistsException\` if lifecycles overlap.

## 13. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Operation does not appear | Missing \`@ManagedOperation\`, bean not exported, or assembler does not use annotations | Check \`@ManagedResource\`, exporter, and \`MBeanInfo\` |
| Parameters show default names like \`p1\`, \`p2\` | Annotation metadata not declared/read properly | Check \`@ManagedOperationParameters\` and order |
| \`invoke\` reports non-matching operation | Wrong name, count, or \`signature\` type | Read \`MBeanOperationInfo.getSignature()\` |
| \`int\` passed as \`"java.lang.Integer"\` in signature | Confusing primitive with wrapper | Use \`"int"\` if the method declares \`int\` |
| JConsole fails to enter \`boolean\` | Input string not converted to valid boolean by client | Use \`true\`/\`false\`, check client error |
| Operation executes but value does not change as expected | Implementation rejected it, async execution, or updated a different instance | Check logs, same instance, and attributes after invoke |
| \`MBeanException\` or \`RuntimeMBeanException\` | Method threw an exception | Read cause/target exception and business conditions |
| \`InstanceNotFoundException\` | Wrong \`ObjectName\` or MBean not registered | Check \`isRegistered\` and \`queryNames\` |
| Invoked right operation on wrong JVM | JMX client connected to a different server | Verify PID, domain, and full \`ObjectName\` |

The \`description\` metadata is documentation for management tools, not a data constraint. If a parameter requires a positive number, the code must still check and throw a meaningful error when 0 or a negative value is entered.

## 14. Notes on Operations with Side Effects

A JMX operation can change application state directly inside the JVM. \`configureCache\`, \`clearCache\`, \`reloadRules\`, or \`resetStatistics\` can all affect requests currently being processed.

Administrative contract design needs to:

1. Clearly describe parameters, units, valid values, preconditions before calling, and expected effects.
2. Validate and reject invalid values inside the method.
3. Ensure thread safety and consistency if multiple fields are modified.
4. Consider idempotency: a client that loses connection after invoke may not know whether the operation completed, so blind retries can cause duplicate execution.
5. Control JMX access permissions, especially when using remote connections.
6. Have sufficient logs/metrics to confirm operation execution when diagnosing issues.
7. Never put secrets or sensitive data in parameter descriptions or returned attributes.

For long-running tasks, consider designing a \`startJob(...)\` operation that returns a job ID and provides attributes/operations to track status; avoid forcing JConsole to wait on a prolonged operation without a way to check the result.

## 15. Practice Exercises

**Exercise 1 — Single parameter.** Create \`QueueAdmin\` with \`pauseForSeconds(int seconds)\`, add \`@ManagedOperation\` and \`@ManagedOperationParameter(name="seconds", description="Pause duration in seconds; 1..300")\`. Inspect metadata and enter values via JConsole. The implementation must validate the 1–300 range itself.

**Exercise 2 — Multiple parameters.** Create \`MaintenanceAdmin\` with \`schedule(String taskName, long delaySeconds, boolean force)\`. Declare three \`@ManagedOperationParameter\` annotations in the right order. Invoke via \`MBeanServer.invoke\` using signatures \`java.lang.String\`, \`long\`, \`boolean\`; verify metadata is accurate.

**Exercise 3 — Wrong signature.** Invoke a method declared with \`int\` using signature \`java.lang.Integer\` and read the error. Fix it to \`int\`; explain the difference between the declared primitive type and the wrapper of the boxed value passed in \`Object[]\`.

**Exercise 4 — Metadata and validation.** Change the description of \`newMaxSize\` to \`"Positive size between 1 and 10000"\`, without changing the validation code. Try entering 10001 to prove the description does not enforce value limits on its own. Then add the range check in the implementation and test again.

**Exercise 5 — ApplicationContext test.** Create a Spring test context with \`@EnableMBeanExport\`, read \`MBeanInfo\`, and assert the count, name, type, and description of each parameter. Verify the operation is registered and can be invoked on the exact bean used in the application.

## Conclusion

\`@ManagedOperation\` exposes a Java method as a JMX operation; \`@ManagedOperationParameter\` and \`@ManagedOperationParameters\` add **names and descriptions** for parameters so management tools can display and understand them. They do not alter the Java signature, do not turn positional arguments into named arguments, and do not validate values automatically. To invoke an operation accurately, you must use the exact \`ObjectName\`, method name, argument order, and \`signature\` published by \`MBeanOperationInfo\`. In Spring Framework, the annotation exporter connects that metadata to \`MBeanServer\` so JConsole and JMX clients can observe or control the application.
