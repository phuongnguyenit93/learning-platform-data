# Spring Framework JMX — Avoiding Overloads That Make Tool Signature Selection Difficult

## 1. The Problem: Java Overloading Is Convenient, but JMX Clients Need Exact Signatures

In Java, overloading allows multiple methods to share the same name with different parameter type lists:

\`\`\`java
public void resize(int newSize) { /* ... */ }
public void resize(long newSize) { /* ... */ }
public void resize(String profile) { /* ... */ }
\`\`\`

The Java compiler can use the expression types at the call site to pick an overload. However, when methods are exported as JMX operations, a management tool such as JConsole, VisualVM, a Jolokia gateway, or a program calling \`MBeanServerConnection.invoke\` must specify **operation name + parameter signature**. Not every tool displays, inputs, and selects overloads easily; some UIs even show multiple nearly identical operations, making it hard for operators to know which one to invoke.

This lesson focuses on Spring Framework's \`@ManagedOperation\` and how to design clear, unambiguous JMX management interfaces, especially when a Java class has overloaded methods.

Objectives:
- Understand why JMX uses operation name, parameter array, and **parameter type signature array**.
- Distinguish method names from signatures like \`int\`, \`long\`, \`java.lang.Integer\`, and \`java.lang.String\`.
- Recognize the risks of overloading when using manual management tools or scripts.
- Design operations with business-meaningful names instead of relying solely on overloading.
- Know how to use \`MBeanInfo\` metadata to retrieve the actual signature before calling \`invoke\`.

## 2. Mental Model: JMX Operations Differ from Normal Java Calls

A Java caller can write:

\`\`\`java
service.resize(12);
service.resize(12L);
service.resize("large");
\`\`\`

The compiler knows the type of each expression, applies Java's overload resolution rules, and generates the matching call.

A JMX caller instead works through the API:

\`\`\`java
Object result = connection.invoke(
    objectName,
    operationName,
    params,
    signature
);
\`\`\`

Where:

| Component | Role | Example |
|---|---|---|
| \`objectName\` | Identifies the registered MBean | \`com.example:type=WorkerPool,name=main\` |
| \`operationName\` | Operation name | \`"resize"\` |
| \`params\` | Java values sent to the operation | \`new Object[]{12}\` |
| \`signature\` | List of **declared type names** of parameters | \`new String[]{"int"}\` |

Tools should not guess overloads solely from the value \`12\` passed in \`Object[]\`: that element is already an \`Integer\` object due to boxing, whereas the JMX method may declare primitive \`int\`.

Diagram:

\`\`\`text
Java source
  resize(int)
  resize(long)
  resize(String)
       |
       | Spring JMX metadata assembler
       v
MBeanInfo.operations[]
  resize(signature = ["int"])
  resize(signature = ["long"])
  resize(signature = ["java.lang.String"])
       |
       | JMX client must select exact signature
       v
MBeanServerConnection.invoke(name, "resize", params, signature)
\`\`\`

**Key point:** \`@ManagedOperation\` publishes operations; it does not give every JMX tool a Java compiler-like overload resolver.

## 3. Example That Causes Friction with @ManagedOperation

Suppose there is a bean controlling a worker pool:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=main",
    description = "Runtime worker pool controls"
)
public class WorkerPoolControl {

    @ManagedOperation(description = "Resize worker count")
    public void resize(int threads) {
        applyWorkerCount(threads);
    }

    @ManagedOperation(description = "Resize using long count")
    public void resize(long threads) {
        if (threads > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Too many threads");
        }
        applyWorkerCount((int) threads);
    }

    @ManagedOperation(description = "Resize using named profile")
    public void resize(String profile) {
        switch (profile) {
            case "small" -> applyWorkerCount(4);
            case "medium" -> applyWorkerCount(8);
            case "large" -> applyWorkerCount(16);
            default -> throw new IllegalArgumentException(
                "Unknown profile: " + profile
            );
        }
    }

    private void applyWorkerCount(int count) {
        if (count < 1 || count > 64) {
            throw new IllegalArgumentException("count must be 1..64");
        }
        // In practice: call the configuration mechanism of the running executor.
    }
}
\`\`\`

If exported by Spring JMX annotation infrastructure, the MBean can publish three entries named \`resize\` with different signatures.

This is **not invalid in Java**, but it creates a burden for management UI users:

- On a tool listing operations, users may see three \`resize\` rows.
- When calling from a script, the caller must explicitly select \`"int"\`, \`"long"\`, or \`"java.lang.String"\`.
- When a JMX bridge receives parameters from JSON or text strings, runtime types may be insufficient to pick an overload automatically.
- When a new overload is added, tools or scripts that guess signatures may change behavior or fail.
- When logs only record \`operation=resize\`, it is not enough to tell which overload was called.

These complications become even clearer when multiple overloads return similar values or have side effects on production state.

## 4. Why Do Primitive and Wrapper Signatures Differ?

The two Java declarations below do not have the same JMX signature:

\`\`\`java
public void setLimit(int value);
public void setLimit(Integer value);
\`\`\`

JMX operation metadata uses **declared type names**, not custom display labels:

| Java Declaration | JMX Signature String |
|---|---|
| \`int\` | \`"int"\` |
| \`long\` | \`"long"\` |
| \`boolean\` | \`"boolean"\` |
| \`double\` | \`"double"\` |
| \`java.lang.Integer\` | \`"java.lang.Integer"\` |
| \`java.lang.Long\` | \`"java.lang.Long"\` |
| \`java.lang.String\` | \`"java.lang.String"\` |
| \`java.time.Duration\` | \`"java.time.Duration"\` |

For Java primitive \`int\`, the value sent in \`Object[]\` is still \`Integer\`:

\`\`\`java
connection.invoke(
    objectName,
    "resize",
    new Object[] { Integer.valueOf(12) },
    new String[] { "int" }
);
\`\`\`

Do not replace \`"int"\` with \`"java.lang.Integer"\` just because the element in the \`params\` array is \`Integer\`.

Similarly, if the method declares \`long\`, use \`"long"\` and a matching \`Long\` value:

\`\`\`java
connection.invoke(
    objectName,
    "resize",
    new Object[] { Long.valueOf(12L) },
    new String[] { "long" }
);
\`\`\`

**Do not assume JMX automatically applies numeric widening like the Java compiler.** A bridge or MBean implementation might handle conversions on its own, but proper client design should rely on concrete metadata and pass the exact type.

## 5. Common Errors When Invoking Overloaded Operations

### 5.1. Wrong Signature Even Though the Value Looks Right

\`\`\`java
// Actual operation is resize(int), but signature selects Integer:
connection.invoke(
    objectName,
    "resize",
    new Object[] { 12 },
    new String[] { "java.lang.Integer" }
);
\`\`\`

If the MBean only has \`resize(int)\`, JMX cannot find an operation with signature \`java.lang.Integer\`. Depending on the MBean type and adapter, the error may surface via \`ReflectionException\` with a cause like \`NoSuchMethodException\`, or another dispatch exception.

### 5.2. Omitting Signature or Passing the Wrong Parameter Count

\`\`\`java
connection.invoke(
    objectName,
    "resize",
    new Object[] { 12 },
    new String[0] // Does not match one parameter
);
\`\`\`

For \`resize(int)\`, one \`"int"\` entry is needed. A mismatched signature count causes operation lookup to fail or be rejected by the implementation.

### 5.3. Calling the Same Name but Choosing the Wrong Semantic Overload

Suppose:
- \`resize(int)\` means absolute worker count;
- \`resize(String)\` means operational profile;
- \`resize(long)\` accepts large numbers but has separate validation.

A script reads text input \`"12"\` and selects \`resize(String)\` because the input data is text, even though the operator wanted an absolute worker count. If the Java method \`resize(String)\` only supports profiles, the error occurs inside the business method rather than at JMX dispatch.

This is an example of an **unclear API**, not merely a type-passing mistake.

### 5.4. Logging Without the Signature

\`\`\`text
event=jmx.invoke.failed
operation=resize
exception=ReflectionException
\`\`\`

This log is hard to investigate because it lacks:
- ObjectName and endpoint,
- parameter types sent,
- signature requested by the client,
- signatures published by MBean metadata,
- cause/target exception.

Log this instead:

\`\`\`text
event=jmx.invoke.failed
objectName=com.example.app:type=WorkerPool,name=main
operation=resize
signature=[java.lang.Integer]
expectedSignatures=[[int],[long],[java.lang.String]]
exception=javax.management.ReflectionException
\`\`\`

Avoid logging sensitive parameter values.

## 6. How to Avoid Overloads: Name by Behavior

The easiest-to-operate design is usually **giving each JMX operation a semantically distinct name**. Instead of:

\`\`\`java
@ManagedOperation
public void resize(int threads) { /* ... */ }

@ManagedOperation
public void resize(String profile) { /* ... */ }
\`\`\`

use:

\`\`\`java
@ManagedOperation(description = "Set absolute worker count")
public void setWorkerCount(int threads) {
    applyWorkerCount(threads);
}

@ManagedOperation(description = "Apply a predefined worker profile")
public void applyWorkerProfile(String profile) {
    // validate profile and configure worker pool
}
\`\`\`

And if a relative adjustment action is needed:

\`\`\`java
@ManagedOperation(description = "Increase workers by delta")
public void increaseWorkerCount(int delta) {
    // ...
}
\`\`\`

Then MBeanInfo is clear:

\`\`\`text
setWorkerCount(int)
applyWorkerProfile(java.lang.String)
increaseWorkerCount(int)
\`\`\`

Advantages:
1. Operators understand the action just by reading the name.
2. Clients rarely need to disambiguate complex overloads.
3. Logs are easier to search.
4. Per-operation authorization configuration is clearer if the system supports fine-grained policies.
5. Adding new operations has less impact on older scripts.
6. Easier to describe side effects and valid ranges for each action.

**Naming rule:** use verbs describing the actual effect; the more specific the name, the better for operations that mutate state, start jobs, or delete data.

## 7. When Should @ManagedAttribute Be Used Instead of an Operation?

Some overloads stem from modeling actions incorrectly. Example:

\`\`\`java
public void configure(int maxThreads);
public void configure(int maxThreads, int queueSize);
\`\`\`

If operators only need to adjust an independent setting, an attribute can be exposed:

\`\`\`java
@ManagedAttribute
public int getMaxThreads() {
    return maxThreads;
}

@ManagedAttribute
public void setMaxThreads(int value) {
    if (value < 1 || value > 64) {
        throw new IllegalArgumentException("Expected 1..64");
    }
    maxThreads = value;
}
\`\`\`

When **multiple settings must be applied atomically**, a clearly named operation such as \`reconfigurePool(int, int)\` may be better than multiple \`configure(...)\` overloads.

Distinction:
- **Attribute:** state or a single configuration value with getter/setter.
- **Operation:** action or multi-step/side-effecting task.
- **No export needed:** purely internal helper methods.

Do not turn a dangerous operation like \`clearCache()\` into a setter \`setClearCache(true)\` just to avoid overloads. What matters is a semantically clear management contract.

## 8. Separating Internal Java API from the JMX Interface

An application may need Java overloads for business-code convenience, without needing to expose all of them over JMX.

Example:

\`\`\`java
public class WorkerPoolControl {
    public void resize(int threads) {
        // Internal API used in many places
    }

    public void resize(String profile) {
        // Another internal API
    }

    @ManagedOperation(description = "Set worker pool size")
    public void setWorkerCount(int threads) {
        resize(threads);
    }

    @ManagedOperation(description = "Apply worker pool profile")
    public void applyWorkerProfile(String profile) {
        resize(profile);
    }
}
\`\`\`

If the Spring metadata assembler only publishes annotated methods, \`resize\` does not become a JMX operation, while the two meaningfully named methods are published.

Benefits of an administrative facade:
- Preserves backward compatibility of the internal Java API.
- Separates lifecycle and authorization for administrative actions.
- Can add specialized validation for remote management.
- Provides a dedicated place for audit logging and metrics.
- Changes internal implementation without changing the JMX contract.

For larger systems, you can create a separate \`WorkerPoolManagementFacade\` bean instead of adding all annotations to business classes.

## 9. Spring Framework: Creating Operation Metadata with Annotations

\`@ManagedOperation\` resides in:

\`\`\`java
org.springframework.jmx.export.annotation.ManagedOperation
\`\`\`

Typical bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=main"
)
public class WorkerPoolManagementFacade {
    @ManagedOperation(description = "Set exact number of workers")
    public void setWorkerCount(int count) {
        // ...
    }

    @ManagedOperation(description = "Pause new work")
    public void pauseIntake() {
        // ...
    }

    @ManagedOperation(description = "Resume new work")
    public void resumeIntake() {
        // ...
    }
}
\`\`\`

To export annotations, Spring JMX infrastructure is required, for example:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {}
\`\`\`

Or \`MBeanExporter\` and \`MetadataMBeanInfoAssembler\` can be configured explicitly. Avoid having two exporters register the same bean and ObjectName.

**Note:** adding \`@ManagedOperation\` does not resolve overloading by itself; if multiple methods with the same name are annotated, metadata can still contain multiple operation entries with the same name and different signatures.

## 10. Adding @ManagedOperationParameter for Tool Readability

Spring has \`@ManagedOperationParameter\` to describe parameters, typically used with \`@ManagedOperationParameters\`.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Set exact worker count")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "threads",
        description = "Number of workers, from 1 to 64"
    )
})
public void setWorkerCount(int threads) {
    // ...
}
\`\`\`

This metadata helps JMX tools display parameter names/descriptions more clearly. However:
- Descriptions **do not change the type signature** used in \`invoke\`.
- They **do not fix** the problem of three overloads sharing one name.
- They do not convert String \`"12"\` into primitive \`int\`.
- They do not replace validation in Java code.

Rather than relying solely on metadata to reduce confusion, prioritize distinct operation names and simple input types.

## 11. Inspecting Actual Signatures via MBeanInfo

Do not guess signatures from source code and hardcode scripts without checking the actually exported MBean. The same bean may be wrapped by Spring in a ModelMBean, and the assembler decides which operations are published.

Using the Java JMX API:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectJmxOperations {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.app:type=WorkerPool,name=main"
        );

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.print(operation.getName() + "(");

            MBeanParameterInfo[] params = operation.getSignature();
            for (int i = 0; i < params.length; i++) {
                if (i > 0) System.out.print(", ");
                System.out.print(params[i].getType());
            }

            System.out.println(")");
        }
    }
}
\`\`\`

If the output shows:

\`\`\`text
setWorkerCount(int)
applyWorkerProfile(java.lang.String)
pauseIntake()
resumeIntake()
\`\`\`

then the client has enough information to invoke. If the output still contains multiple \`resize\` entries, determine whether they really need to be exposed over JMX.

In applications using multiple MBeanServers, the client must target the exact server where \`MBeanExporter\` registered the bean; \`getPlatformMBeanServer()\` is only the common case, not guaranteed for every configuration.

## 12. Calling invoke with Explicit Signatures

Suppose metadata publishes:

\`\`\`text
setWorkerCount(int)
applyWorkerProfile(java.lang.String)
pauseIntake()
\`\`\`

Client invocation:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerPool,name=main"
);

server.invoke(
    name,
    "setWorkerCount",
    new Object[] { Integer.valueOf(12) },
    new String[] { "int" }
);

server.invoke(
    name,
    "applyWorkerProfile",
    new Object[] { "large" },
    new String[] { "java.lang.String" }
);

server.invoke(
    name,
    "pauseIntake",
    new Object[0],
    new String[0]
);
\`\`\`

Each operation has its own name. Scripts do not have to guess between \`resize(int)\` and \`resize(String)\`.

### Do Not Use Overly Complex Parameter Types Unnecessarily

Example:

\`\`\`java
@ManagedOperation
public void configure(java.time.Duration timeout) { /* ... */ }
\`\`\`

A Java client sharing the classpath might be able to send \`Duration\`, but generic JMX tools, remote clients, and JSON-based bridges can struggle with complex types.

Replace with an easy-to-invoke contract:

\`\`\`java
@ManagedOperation(description = "Set timeout in milliseconds")
public void setTimeoutMillis(long timeoutMillis) {
    if (timeoutMillis < 0 || timeoutMillis > 600_000) {
        throw new IllegalArgumentException("Invalid timeoutMillis");
    }
    // Convert to Duration in the implementation.
}
\`\`\`

Similarly, use \`String\` for enums/profiles with a clear allowlist, or expose an integer with documented units and range. Simplicity at the JMX boundary reduces operational errors.

## 13. If Overloads Must Be Kept

Sometimes legacy clients depend on existing overloads or an already-deployed JMX interface. When the contract cannot be changed yet, at minimum:

1. Document **every signature** with concrete invocation examples.
2. Only use overloads when semantics are truly the same action, not changing meaning by type.
3. Avoid closely related pairs like \`int\`/\`Integer\`, \`int\`/\`long\` if they carry no distinct operational value.
4. Do not let JMX clients guess signatures from input strings.
5. Inspect \`MBeanInfo\` at runtime to build the operation list.
6. Use a controlled wrapper/client helper to construct \`params\` and \`signature\` accurately.
7. Treat adding a new overload as a management interface change requiring compatibility checks.
8. For side-effecting operations, verify the right overload is selected before invoking in production.

Example of a signature-explicit helper:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerJmxClient {
    private final MBeanServerConnection connection;
    private final ObjectName name;

    public WorkerJmxClient(
            MBeanServerConnection connection,
            ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public void resizeByCount(int count) throws Exception {
        connection.invoke(
            name,
            "resize",
            new Object[] { count },
            new String[] { "int" }
        );
    }

    public void resizeByProfile(String profile) throws Exception {
        connection.invoke(
            name,
            "resize",
            new Object[] { profile },
            new String[] { "java.lang.String" }
        );
    }
}
\`\`\`

Although the JMX contract still has the overloaded \`resize\` name, the client API \`resizeByCount\` and \`resizeByProfile\` spares Java callers from repeating signatures every time.

## 14. Using Operation Aliases During API Transitions

A migration option is keeping the old overload during a transition period while adding an operation with a clear name:

\`\`\`java
@ManagedOperation(description = "Legacy resize(int)")
public void resize(int threads) {
    setWorkerCount(threads);
}

@ManagedOperation(description = "Preferred: set worker count")
public void setWorkerCount(int threads) {
    // ...
}
\`\`\`

Requirements:
- Publish the new name in operational documentation.
- Update dashboards/scripts incrementally.
- Monitor usage of the old operation if logging is available.
- Do not remove the old operation before confirming clients have migrated.
- When removing it, treat it as a potentially breaking JMX compatibility change.

If you need to keep Java overloads without exporting them over JMX, only annotate the administrative aliases. Exporting the legacy variant in JMX is not always necessary.

## 15. When an Operation Is a Dangerous Action

For operations such as:

\`\`\`java
reloadConfiguration(...)
clearCache(...)
restartWorker(...)
rotateKeys(...)
\`\`\`

overloading can have bigger consequences than misreading a read-only metric. Therefore:
- Choose names that express scope clearly, e.g., \`clearLocalCache\` vs \`clearDistributedCache\`.
- Use simple signatures and validate inputs.
- Apply proper authorization for remote JMX.
- Audit ObjectName, operation, signature, and outcome status.
- Never log secrets/credentials.
- If an operation can partially execute and fail, verify post-state before retrying.
- When confirmation is needed for dangerous actions, add a workflow in the client/tool rather than expecting Java overloads to help users understand risks.

For instance, two \`clearCache\` operations taking \`boolean distributed\` and \`String cacheName\` are confusing when displayed in a JMX console. Names like \`clearLocalCache\`, \`clearNamedCache\`, or \`clearAllCaches\` reflect scope much more clearly.

## 16. Error Table and Investigation Guide

| Symptom | Common Cause | Resolution |
|---|---|---|
| \`ReflectionException\` on invoke | Wrong operation name or signature | Print \`MBeanInfo.getOperations()\` |
| \`NoSuchMethodException\` in cause | No method matching signature | Compare each type name: \`int\` vs \`java.lang.Integer\` |
| Succeeds but applies wrong config type | Selected unintended overload | Rename operations by semantics |
| JConsole displays multiple rows with same name | Multiple overloads exported | Limit annotated methods or use aliases |
| Bridge sends all parameters as String | Lost primitive types in client | Convert explicitly per metadata or change JMX API |
| \`InvalidAttributeValueException\` | Action targets an attribute, not an operation | Distinguish \`setAttribute\` and \`invoke\` |
| \`MBeanException\`/\`RuntimeMBeanException\` | Operation business logic threw an error | Check target exception, validation, state |
| \`InstanceNotFoundException\` | Wrong ObjectName/MBean not registered | Check registration before investigating overloads |

Do not treat every \`ReflectionException\` as an overload error; the method might not exist or the adapter might fail to invoke it. Check the full exception chain and metadata.

## 17. Practice Exercises

### Exercise 1 — Predict the Signatures

Given the methods:

\`\`\`java
@ManagedOperation
public void schedule(int delaySeconds) { }

@ManagedOperation
public void schedule(long epochMillis) { }

@ManagedOperation
public void schedule(String cron) { }
\`\`\`

Question: What are the JMX signatures?

Answer:
- \`schedule(int)\` → \`["int"]\`.
- \`schedule(long)\` → \`["long"]\`.
- \`schedule(java.lang.String)\` → \`["java.lang.String"]\`.

### Exercise 2 — Spot the Wrong Call

\`\`\`java
connection.invoke(
    name,
    "schedule",
    new Object[] { Integer.valueOf(30) },
    new String[] { "java.lang.Integer" }
);
\`\`\`

Question: If only \`schedule(int)\` exists, what must be fixed?

Answer: the signature must be \`"int"\`, because the declared method parameter type is primitive \`int\`.

### Exercise 3 — Refactor Names by Meaning

Initially:

\`\`\`java
void reset();
void reset(boolean includeHistory);
void reset(String module);
\`\`\`

Suggested naming design:

\`\`\`java
resetCurrentCounters();
resetCountersIncludingHistory();
resetModuleCounters(String module);
\`\`\`

The names express scope more clearly. Also consider whether resetting history is a sensitive operation requiring separate permissions.

### Exercise 4 — Choose Attribute or Operation

Given two methods:
- \`setMaxThreads(int)\` changes worker configuration;
- \`clearQueue()\` deletes pending jobs.

Hint:
- \`MaxThreads\` can be a read/write \`@ManagedAttribute\` if it is a genuine property.
- \`clearQueue()\` should be a separate \`@ManagedOperation\`, with explicit permissions and warnings.

### Exercise 5 — When Should Overloads Be Kept?

An old client has used \`resize(int)\` for years; you want to add a profile option. Hint:
- Keep \`resize(int)\` for the legacy client if compatibility is required.
- Add \`applyWorkerProfile(String)\`, avoiding adding \`resize(String)\`.
- Update documentation and track migration.

## 18. @ManagedOperation Design Checklist

Before exposing an operation to JMX, ask:

1. Does the method name clearly express the **action** and scope?
2. Are there overloads with the same name on the JMX interface? If so, are they truly necessary?
3. Is \`signature\` simple and widely supported by clients?
4. Are primitive/wrapper types used consistently?
5. Do parameters describe names, units, and valid ranges?
6. Does the operation mutate state or cause side effects?
7. Does the exported MBean metadata match intent?
8. Do scripts use exact signatures from \`MBeanInfo\`?
9. Are error handling, post-state verification, and safe retries in place?
10. Could new names or overload changes break existing clients?

## 19. Summary

Overloading is not an anti-pattern in Java in general, but it often makes **JMX management APIs harder to operate**. The JMX API selects operations by name and parameter type list; signatures \`"int"\`, \`"long"\`, and \`"java.lang.Integer"\` are distinct. When a tool lacks a friendly overload picker, operators and scripts easily choose the wrong type or misunderstand the action.

For Spring \`@ManagedOperation\`, prefer **unique operation names described by business intent**, use easy-to-enter parameter types, provide helpful metadata, and expose only methods needed for management. If internal Java code needs overloads, keep them in the implementation and export a non-overloaded JMX facade. Inspect \`MBeanInfo\` after the exporter registers the bean to verify the exact contract clients actually receive.