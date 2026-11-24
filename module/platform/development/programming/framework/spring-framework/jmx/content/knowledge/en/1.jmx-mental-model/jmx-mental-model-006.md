# Managing state via JMX: reading attributes, writing attributes, and invoking operations

## 1. Mental picture

JMX (Java Management Extensions) provides a **live management interface** for a Java application. Instead of viewing an object as a regular Java class, think of an **MBean** (Managed Bean) as a control panel with three types of interaction:

- **Read attribute:** observe the current state exposed by the MBean. For example: \`Active\`, \`MaxConnections\`, \`ProcessedCount\`.
- **Write attribute:** modify a runtime parameter that the MBean allows editing. For example: change \`MaxConnections\` from \`20\` to \`30\`.
- **Invoke operation:** ask the MBean to execute a named action, optionally taking arguments and returning a result. For example: \`resetCounters()\`, \`refreshCache()\`.

These three interaction types have different meanings even though all are sent through the same \`MBeanServer\`. An attribute describes *observable or configurable state*; an operation represents *deliberate behavior*. A read-only value does not naturally become writable just because the Java code has a corresponding field.

\`\`\`text
JMX client (JConsole / VisualVM / JMX code)
             |
             v
       MBeanServer
             |
             v
 ObjectName: com.example.app:type=WorkerControl,name=main
             |
       +-----+-----------------------+
       |                             |
 Attributes                      Operations
  Active (read)                resetCounters()
  MaxThreads (read/write)      pause()
  ProcessedCount (read)        resume()
       |                             |
       +-------------+---------------+
                     v
            Runtime service state
\`\`\`

In Spring Framework, the JMX export mechanism can wrap a Spring bean into an MBean. Because of that, administrators do not need to know directly how to obtain the bean from \`ApplicationContext\`; they interact via the JMX name (\`ObjectName\`) and the management contract published by the application.

## 2. The contract before interacting

Before reading, writing, or invoking an operation, identify four pieces of information:

1. **ObjectName** identifying the exact MBean, such as \`com.example.app:type=WorkerControl,name=main\`. Do not infer it from the class name; verify the name actually exported.
2. **Attribute or operation name** as defined in JMX metadata; it may differ from how internal fields/methods are written.
3. **Accessibility**: an attribute may be readable, writable, or both; an operation has a defined parameter signature and return type.
4. **Business meaning and bounds**: which values are valid to write, whether an operation is idempotent, and whether the action affects serving traffic.

An MBean exposes metadata via \`MBeanInfo\`. In code, \`MBeanAttributeInfo.isReadable()\` and \`isWritable()\` indicate readability/writability; \`MBeanOperationInfo\` describes operation names and parameters. Metadata is the technical check; operational documentation still needs to explain the real-world effect.

### Attributes are not operations

| Question | Attribute | Operation |
|---|---|---|
| Purpose | View or configure a piece of state | Trigger an action |
| JMX call | \`getAttribute\`, \`setAttribute\` | \`invoke\` |
| Parameters? | Writes one value of declared type | Can take multiple parameters with a signature |
| Can mutate the system? | Yes, when writable | Possible; depends on the operation contract |
| Example | Read \`ProcessedCount\`, write \`MaxThreads\` | \`resetCounters()\`, \`pause()\` |

You should not model an action like \`resetCounters\` as a boolean attribute to "turn on and off" when it is inherently a command. Conversely, a configuration like \`MaxThreads\` fits a writable attribute better when you need to observe the value again after writing it.

## 3. Building a Spring JMX export example

The example below intentionally separates the business class from the JMX-exposed class. It models a simulated worker with in-memory state; it does not connect to real resources. Operations are kept simple and synchronized so runtime changes are easy to observe.

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class WorkerRuntime {
    private volatile int maxThreads = 8;
    private volatile boolean active = true;
    private final AtomicLong processedCount = new AtomicLong();

    public int getMaxThreads() {
        return maxThreads;
    }

    public void setMaxThreads(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("maxThreads must be between 1 and 64");
        }
        maxThreads = value;
    }

    public boolean isActive() {
        return active;
    }

    public long getProcessedCount() {
        return processedCount.get();
    }

    public void recordProcessed() {
        processedCount.incrementAndGet();
    }

    public void resetCounters() {
        processedCount.set(0);
    }

    public void pause() {
        active = false;
    }

    public void resume() {
        active = true;
    }
}
\`\`\`

In a real application, updating \`maxThreads\` must be applied to the corresponding executor/pool; changing a configuration field **does not automatically** resize a thread pool. Here the field represents the example's state.

Use \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` to declare the exact management surface:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=main",
    description = "Runtime control for example worker"
)
public class WorkerControl {
    private final WorkerRuntime runtime;

    public WorkerControl(WorkerRuntime runtime) {
        this.runtime = runtime;
    }

    @ManagedAttribute(description = "Maximum configured worker threads")
    public int getMaxThreads() {
        return runtime.getMaxThreads();
    }

    @ManagedAttribute(description = "Change the worker thread limit")
    public void setMaxThreads(int maxThreads) {
        runtime.setMaxThreads(maxThreads);
    }

    @ManagedAttribute(description = "Whether the worker accepts work")
    public boolean isActive() {
        return runtime.isActive();
    }

    @ManagedAttribute(description = "Number of processed items")
    public long getProcessedCount() {
        return runtime.getProcessedCount();
    }

    @ManagedOperation(description = "Reset the processed counter to zero")
    public void resetCounters() {
        runtime.resetCounters();
    }

    @ManagedOperation(description = "Pause accepting new work")
    public void pause() {
        runtime.pause();
    }

    @ManagedOperation(description = "Resume accepting work")
    public void resume() {
        runtime.resume();
    }
}
\`\`\`

At the example's JMX contract level: \`MaxThreads\` is readable/writable because both getter and setter are exported; \`Active\` and \`ProcessedCount\` are read-only because only getters are exposed; \`resetCounters\`, \`pause\`, and \`resume\` are operations.

Configure a Spring context using annotation-based export:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
    @Bean
    public WorkerRuntime workerRuntime() {
        return new WorkerRuntime();
    }

    @Bean
    public WorkerControl workerControl(WorkerRuntime workerRuntime) {
        return new WorkerControl(workerRuntime);
    }
}
\`\`\`

In Spring Framework, \`@EnableMBeanExport\` registers the export mechanism along with discovery of management annotations; a Spring Boot environment may provide its own JMX configuration, so verify the actual runtime before enabling an additional exporter to avoid duplicate registration. JMX objects only appear once the context is initialized and successfully exported to the \`MBeanServer\`.

## 4. Reading state with a JMX client

A Java client can access \`MBeanServerConnection\`. When running in the same JVM, use \`ManagementFactory.getPlatformMBeanServer()\`; when running from another process, the connection is obtained from \`JMXConnector\` with appropriate access configuration.

Same-JVM example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

boolean registered = server.isRegistered(name);
if (!registered) {
    throw new IllegalStateException("MBean is not registered yet: " + name);
}

int threads = (Integer) server.getAttribute(name, "MaxThreads");
boolean active = (Boolean) server.getAttribute(name, "Active");
long count = (Long) server.getAttribute(name, "ProcessedCount");

System.out.printf(
    "maxThreads=%d, active=%s, processed=%d%n",
    threads, active, count
);
\`\`\`

The read value is a snapshot at the time of the call; if the worker continues processing tasks, \`ProcessedCount\` may change immediately afterward. Do not treat a sequence of multiple \`getAttribute\` calls as a consistent transaction across attributes.

Before relying on names or write permissions, you can inspect metadata:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

A graphical client like JConsole can also list MBeans by domain/type/name and display attributes and operations. Before clicking \`set\` or \`invoke\`, verify the ObjectName and data types displayed by the client.

## 5. Writing attributes: configuration must be confirmed

\`setAttribute\` carries a name-and-value pair. For \`MaxThreads\` in the example:

\`\`\`java
import javax.management.Attribute;

server.setAttribute(name, new Attribute("MaxThreads", 16));

int observed = (Integer) server.getAttribute(name, "MaxThreads");
if (observed != 16) {
    throw new IllegalStateException(
        "Value after write does not match: " + observed
    );
}
\`\`\`

Mindset when writing:

1. **Read first** to know the current state and assess whether a change is necessary.
2. **Check bounds**: in this example \`1 <= MaxThreads <= 64\`; a real application may have its own resource limits.
3. **Write the right type**: JMX distinguishes \`Integer\`, \`Long\`, \`Boolean\`, \`String\`, etc. Passing \`"16"\` (String) instead of \`16\` (Integer) is not equivalent.
4. **Read back** to confirm the state the MBean is publishing.
5. **Monitor the impact**: lowering/raising runtime limits can affect throughput or latency; a successful readback does not prove that actual underlying infrastructure behavior changed.

If the setter throws \`IllegalArgumentException\` upon receiving \`1000\`, JMX may wrap the application error in an \`MBeanException\` or an appropriate exception depending on the export/adapter method. The client should record cause details; do not assume every write failure is a permission issue.

**Distinguish persistent configuration:** changes via JMX typically affect running state. Upon restart, the bean may be recreated with values from static configuration. If you need changes to survive restarts, implement and document an explicit persistence mechanism; JMX does not automatically write back to \`application.properties\` or configuration sources.

## 6. Invoking operations: deliberate actions

To reset the counter to zero:

\`\`\`java
server.invoke(
    name,
    "resetCounters",
    new Object[0],
    new String[0]
);

long afterReset = (Long) server.getAttribute(
    name, "ProcessedCount"
);
System.out.println("processedCount=" + afterReset);
\`\`\`

\`invoke\` has four parts: target ObjectName; operation name; argument value array; corresponding type signature array. When there are no parameters, both arrays are empty.

Example of an operation accepting a parameter:

\`\`\`java
@ManagedOperation(description = "Set desired worker limit")
public void resize(int targetThreads) {
    runtime.setMaxThreads(targetThreads);
}
\`\`\`

Client call:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { 12 },
    new String[] { "int" }
);
\`\`\`

The JMX signature for a primitive \`int\` parameter is \`"int"\`. If the operation accepts \`java.lang.String\`, you must use \`"java.lang.String"\`. The client must match the exact overload and declared types; matching only the operation name is not enough.

### Do not infer safety from HTTP-like semantics

JMX does not have built-in \`GET\`/ \`POST\` rules or database-like transactions. An operation like \`refreshCache\` can be time-consuming, \`resetCounters\` discards accumulated measurements, and \`pause\` alters serving capability. Repeated invocations may produce side effects or different results depending on current state. Document preconditions, postconditions, and re-invocability for each management operation.

For \`pause()\` and \`resume()\`, check state after the command:

\`\`\`java
server.invoke(name, "pause", new Object[0], new String[0]);
boolean paused = !(Boolean) server.getAttribute(name, "Active");

server.invoke(name, "resume", new Object[0], new String[0]);
boolean resumed = (Boolean) server.getAttribute(name, "Active");
\`\`\`

In the example, \`Active\` is a simulated flag; with a real worker, pause/resume actions must integrate with scheduler/queue mechanisms and have a clear contract for previously accepted tasks.

## 7. Common errors and operational situations

| Situation | Common symptom | How to handle |
|---|---|---|
| Wrong ObjectName | \`InstanceNotFoundException\` | List registered MBeans and use the exact ObjectName |
| Attribute does not exist | \`AttributeNotFoundException\` | Inspect \`MBeanInfo\`, check exported getter and JMX name |
| Attempt to write read-only attribute | \`AttributeNotFoundException\` or corresponding write error | Check \`isWritable()\`, redesign contract if needed |
| Wrong value type | \`InvalidAttributeValueException\` or setter error | Use the right Java type and valid bounds |
| Wrong operation name/signature | \`ReflectionException\` or invocation error | Read operation metadata and parameter signatures |
| Error inside business method | \`MBeanException\` or adapter exception | Inspect cause and application logs |
| Cannot connect remotely | Connection timeout, auth error, or port issue | Check endpoint, network, transport, and credentials |
| Readback differs from written value | Normalization logic or concurrent updates | Check setter contract and concurrent activity |

Some exception types depend on the MBean type (Standard/Dynamic/Model MBean) and the Spring adapter in use; this table is a diagnostic guide, not a guarantee of a single exception class across every runtime.

### Concurrency and consistency

- A JMX request is a call into a running component; multiple clients can read, write, or invoke nearly simultaneously.
- A setter that modifies multiple fields needs proper synchronization if intermediate state must not be exposed. \`volatile\` only provides visibility for a single field, not multi-field transactions.
- If an operation runs for a long time, consider a pattern that returns a \`jobId\` and exposes a progress attribute instead of making the client wait too long or lose track of status.
- When attributes return multiple related metrics, design a consistent snapshot in the implementation if they must correspond to the same point in time; multiple separate \`getAttribute\` calls do not guarantee this.

## 8. Security and governance boundaries

JMX often grants access to very powerful capabilities of the Java process. When opening remote management connections, design authentication, authorization, and transport protection; do not expose sensitive JMX ports to public networks. In addition:

- Export only necessary attributes/operations, avoiding leaking passwords, access tokens, or personal data.
- Separate read-only privileges from write or invoke privileges when the management system supports it.
- Validate and bound inputs inside the service itself, not relying solely on JConsole's UI.
- Log contextual audit records for mutating actions: target MBean, action type, timestamp, value or command (without leaking secrets), and outcome.
- Place dangerous operations under environment-appropriate policies; \`shutdown()\` and \`resetAll()\` require special scrutiny.

Remote JMX authorization depends on connector configuration, authentication/authorization mechanisms, and deployment platform; the \`@ManagedOperation\` annotation by itself does not define access permissions.

## 9. Step-by-step practice workflow

Suppose the application is running with MBean \`com.example.app:type=WorkerControl,name=main\`:

1. **Discover:** open JConsole, connect to the JVM, go to the MBeans tab, and locate this ObjectName.
2. **Observe:** read \`MaxThreads\`, \`Active\`, \`ProcessedCount\`; record a snapshot before making changes.
3. **Verify metadata:** \`MaxThreads\` is writable; \`Active\` and \`ProcessedCount\` are read-only; operations include \`resetCounters\`, \`pause\`, \`resume\`.
4. **Runtime configuration:** write \`MaxThreads = 16\`, then read it back and confirm \`16\`.
5. **Execute actions:** invoke \`pause()\`, read \`Active = false\`; then invoke \`resume()\`, read \`Active = true\`.
6. **Manage metrics:** invoke \`resetCounters()\` and read \`ProcessedCount\` again; note that a real worker may increment the counter right after reset.
7. **Cross-check impact:** in a real system, check logs/metrics/throughput to verify that the pool, scheduler, or service responded as expected.

Minimal technical check commands in Java can be expressed sequentially as follows (run after the MBean has been exported):

\`\`\`java
ObjectName target = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);
System.out.println(server.getAttribute(target, "MaxThreads"));

server.setAttribute(target, new Attribute("MaxThreads", 16));
System.out.println(server.getAttribute(target, "MaxThreads"));

server.invoke(target, "pause", new Object[0], new String[0]);
System.out.println(server.getAttribute(target, "Active"));

server.invoke(target, "resume", new Object[0], new String[0]);
System.out.println(server.getAttribute(target, "Active"));
\`\`\`

## 10. Self-check for comprehension

**Scenario A.** An MBean has \`getProcessedCount()\` with no exported setter. A client attempts \`setAttribute("ProcessedCount", 0)\`. Why shouldn't this approach be used to reset?  
*Hint:* \`ProcessedCount\` is read-only; resetting has side effects and therefore needs a clearly named operation and contract, such as \`resetCounters()\`.

**Scenario B.** \`setAttribute("MaxThreads", 16)\` succeeds, yet the actual thread pool still has eight workers. What does this prove?  
*Hint:* The bean is storing a configuration value, not necessarily applying the change to runtime resources. You must wire the setter to the pool and verify real system state.

**Scenario C.** Two \`getAttribute("ProcessedCount")\` calls return 105 and 109. Is that a JMX bug?  
*Hint:* No. This is live data; the system may process additional work between two reads.

**Scenario D.** Why might \`invoke(name, "resize", new Object[]{12}, new String[]{"java.lang.Integer"})\` fail to match the operation \`resize(int)\`?  
*Hint:* The signatures \`int\` and \`java.lang.Integer\` differ; JMX requires the exact signature of the exported operation.

**Scenario E.** A remote script has permission to invoke \`pause()\` in production. What needs to be considered?  
*Hint:* Authentication, authorization, network isolation, auditing, controlling traffic impact, and recovery procedures.

## 11. Key takeaways

**Read attribute = observe**, **write attribute = change an allowed configuration/state**, **invoke operation = ask the system to execute an action**. All three require the right ObjectName, a clear JMX contract, and awareness that the target is live state that can change concurrently. Reading back after a write/invoke confirms the published state; to verify real impact, check the business components behind the MBean as well.