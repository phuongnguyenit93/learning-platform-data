# Looking Up Managed ConnectionFactory via JNDI in Spring JMS

## 1. Problem Statement and Resource Management Model

In a Spring application using **Jakarta Messaging (JMS)**, `jakarta.jms.ConnectionFactory` is the entry point for creating JMS connections/contexts. On a **Jakarta EE application server**, an administrator can create a `ConnectionFactory`, configure the broker endpoint, authentication, TLS, pooling, and transaction participation, and then **bind** the object under a **JNDI** name. The Spring application only needs to **look up** that name and pass the resulting factory into `JmsTemplate` or a listener container.

```text
         Application server / JMS administrator
     ┌──────────────────────────────────────────┐
     │ Create, configure, and manage ConnectionFactory│
     │ broker / TLS / credentials / pool / JTA  │
     └─────────────────┬────────────────────────┘
                       │ bind
                       ▼
          JNDI: java:comp/env/jms/OrdersCF
                       │ lookup
                       ▼
       Spring bean: jakarta.jms.ConnectionFactory
                  /                    \
                 ▼                      ▼
             JmsTemplate           Listener container
                  \                    /
                   └── JMS provider ──┘
```

Keep these stages distinct:

1. **Provision:** the administrator or server creates the actual factory.
2. **Bind:** the server associates a JNDI name with the factory; for `java:comp/env`, resource reference mapping may be required.
3. **Lookup:** Spring retrieves the object by name and checks its type.
4. **Use:** `JmsTemplate` or a listener uses the factory to create/borrow connections, sessions, producers, and consumers and send/receive messages.

**A successful lookup does not mean the broker is ready.** JNDI returns the configured object; networking, authentication, authorization, pooling, or failover can still fail when JMS begins using it. JNDI is neither a Queue/Topic nor a JMS transport.

### Benefits of a Managed ConnectionFactory

- Infrastructure configuration lives on the server: change endpoints, certificates, pools, or credentials per environment with fewer code edits.
- The container can supply pooling, security, transaction integration (JTA/XA), recovery, and monitoring depending on the provider's capabilities.
- Spring works against the `ConnectionFactory` interface, reducing coupling to a specific vendor's constructors.
- Across multiple environments, the application can use a single logical resource name mapped to different physical resources.

These benefits **depend on the bound factory**: looking it up via JNDI does not automatically turn a plain factory into an XA-aware or pooled one.

## 2. Choosing the Right API Namespaces: `jakarta.jms` and `javax.naming`

With Java 17+, Spring Framework 6, or Spring Boot 3:

```java
import jakarta.jms.ConnectionFactory;
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.naming.NamingException;
```

- `ConnectionFactory` now belongs to **`jakarta.jms`** (Jakarta Messaging 3.x).
- `InitialContext`, `Context`, and `NamingException` remain in **`javax.naming`** from Java SE/JDK. Keeping the `javax` prefix for JNDI is **correct**, not legacy code.
- `javax.jms.ConnectionFactory` from JMS 2.0/Java EE 8 is **not the same type** as `jakarta.jms.ConnectionFactory`. Using the wrong library can cause lookup to return an object that cannot be assigned to the interface Spring 6 expects.

| Component | Role |
| --- | --- |
| `javax.naming.InitialContext` | Accesses the naming context and calls `lookup("...")`. |
| `javax.naming.NamingException` | Represents naming/context/resource errors during lookup. |
| `jakarta.jms.ConnectionFactory` | Factory implemented by the JMS provider, supplying methods to create connections/contexts. |
| `org.springframework.jndi.JndiLocatorDelegate` | Spring helper for typed lookups with ENC name support. |
| `org.springframework.jndi.JndiObjectFactoryBean` | Exposes a JNDI object as a Spring bean, supporting caching/lazy proxies. |
| `org.springframework.jms.core.JmsTemplate` | Sends/receives JMS messages using the configured factory. |

JNDI lookup returns `Object`; validate the type rather than casting blindly. After lookup, the factory is typically **injected and shared** across components; it is not an open JMS `Connection` object, and the `ConnectionFactory` interface has no `close()` method.

## 3. JNDI Names and Access Scope

Jakarta Messaging **does not mandate a single universal name** for user-defined factories. The naming provider, application server, and deployment configuration determine the name.

| Example name | Meaning | Notes |
| --- | --- | --- |
| `java:comp/env/jms/OrdersCF` | Name in the component environment naming context (ENC). | A mapping for the application/component must exist. |
| `jms/OrdersCF` | Shortened logical name. | Can be transformed by Spring into `java:comp/env/jms/OrdersCF` when `resourceRef=true`. |
| `java:comp/DefaultJMSConnectionFactory` | Default JMS factory name defined by the Jakarta EE Platform for compatible full-platform servers. | Use only when the server implements and exposes this resource. |
| `java:/JmsXA`, `java:/XAConnectionFactory` | Names seen in servers with integrated JMS/XA, also probed by Spring Boot auto-detection. | Not portable across all servers. |
| `java:app/jms/OrdersCF` | Application-scoped namespace per Jakarta EE resource organization. | Requires provider support and binding in the right scope. |

In this lesson, we assume the administrator has configured **`java:comp/env/jms/OrdersCF`** pointing to a factory supporting Jakarta Messaging with permissions to use destination `orders.in`. This is an **assumption for running the examples**, not a default on every application server.

### `resourceRef` in Spring

Spring's JNDI helpers have a `resourceRef` flag (default **false**):

```text
resourceRef=true, jndiName="jms/OrdersCF"
  -> Spring looks up "java:comp/env/jms/OrdersCF"

resourceRef=false, jndiName="jms/OrdersCF"
  -> Spring looks up "jms/OrdersCF"

resourceRef=true, jndiName="java:comp/DefaultJMSConnectionFactory"
  -> Spring looks up the exact absolute name, without prepending java:comp/env/
```

If the name already has a scheme, such as starting with `java:`, Spring does not prepend the ENC prefix again. **`resourceRef=true` only transforms the lookup name**; it does not create the factory or replace the server-side mapping step.

### Can JNDI Run in a Standalone Application?

Yes, if you actively provide a **JNDI naming provider** and configure `InitialContext` appropriately. However, `java:comp/env/...` names are usually local contexts supplied by a Jakarta EE/servlet container, so **running `java -jar` on a bare machine will not automatically have those bindings**. Plain Tomcat also does not ship with a full JMS provider/pooled factory by default; you must configure external resources or pick a full Jakarta EE server with JMS.

## 4. Preparing Bindings and Resource References

Before writing code, verify:

1. The runtime provides a `jakarta.jms.ConnectionFactory` compatible with Spring 6/Boot 3.
2. The factory is created with the proper broker endpoint, credentials, TLS, and permissions, then bound under the name the application looks up.
3. `jms/OrdersCF` is declared/mapped in ENC if using `java:comp/env/jms/OrdersCF`.
4. The broker has the expected Queue/Topic; policies allow sending/receiving.
5. XA/JTA, pooling, and recovery policies are aligned with the application server.

Example deployment descriptor `WEB-INF/web.xml` declaring a resource reference in a Jakarta EE servlet application (the server may use equivalent configuration via annotations or the admin console):

```xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <resource-ref>
        <res-ref-name>jms/OrdersCF</res-ref-name>
        <res-type>jakarta.jms.ConnectionFactory</res-type>
        <res-auth>Container</res-auth>
    </resource-ref>
</web-app>
```

That file **only declares the logical reference**; the server still must map the reference to a created physical factory. Depending on the server, creating the factory is done via the admin console, vendor-specific deployment descriptors, or resource definitions. Do not store broker credentials in source code just to look up the object.

Another option in the Jakarta EE full platform is the default name:

```java
@Resource(lookup = "java:comp/DefaultJMSConnectionFactory")
private ConnectionFactory connectionFactory;
```

This is an example **inside a class managed by a Jakarta EE container**, requiring imports for `jakarta.annotation.Resource` and `jakarta.jms.ConnectionFactory`. Jakarta EE `@Resource` field injection follows the lifecycle of container-managed components; **it does not automatically work on arbitrary Java objects instantiated with `new`**.

## 5. Direct Lookup Using `InitialContext`

Create `JndiConnectionFactoryLookup.java` (Java 17; the project needs the Jakarta Messaging API on the compile classpath):

```java
import jakarta.jms.ConnectionFactory;
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.naming.NamingException;

public final class JndiConnectionFactoryLookup {

    private JndiConnectionFactoryLookup() {
    }

    public static ConnectionFactory lookup() throws NamingException {
        Context context = new InitialContext();
        try {
            Object resource = context.lookup(
                    "java:comp/env/jms/OrdersCF"
            );

            if (!(resource instanceof ConnectionFactory factory)) {
                throw new NamingException(
                        "JNDI resource is not a jakarta.jms.ConnectionFactory"
                );
            }
            return factory;
        } finally {
            context.close();
        }
    }
}
```

This is a **compilable class**, but **not a standalone program with fixed output**: the caller must run inside a runtime with a JNDI provider and resource binding, or supply an equivalent naming provider. There is no `main` method because the class is intended for use inside a deployed application.

How it works:

1. `new InitialContext()` obtains the naming environment from the runtime.
2. `lookup(name)` queries the naming provider for the bound object.
3. `instanceof ConnectionFactory` verifies the Jakarta JMS type.
4. `context.close()` releases the naming context. The factory object is a server-managed resource and remains usable by Spring after lookup.

If the name does not exist, `NameNotFoundException` is common. If no JNDI environment is present, `NoInitialContextException` can occur. Both belong to `NamingException`. **Do not catch it and return `null`**, which delays configuration errors until message-sending time.

In Spring, configure a singleton bean instead of repeating manual lookups across services.

## 6. Direct Spring Framework Configuration with JNDI

### 6.1. `JndiLocatorDelegate`: Concise and Type-Checked

Create `src/main/java/example/jms/JndiJmsConfig.java` in an application with Spring Framework 6 and Spring JMS:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import javax.naming.NamingException;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jndi.JndiLocatorDelegate;

@Configuration
public class JndiJmsConfig {

    @Bean
    public ConnectionFactory connectionFactory()
            throws NamingException {
        return JndiLocatorDelegate
                .createDefaultResourceRefLocator()
                .lookup("jms/OrdersCF", ConnectionFactory.class);
    }

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
```

`createDefaultResourceRefLocator()` sets `resourceRef=true`, so `"jms/OrdersCF"` is looked up as `"java:comp/env/jms/OrdersCF"`. `lookup(name, ConnectionFactory.class)` returns an object of the expected type or throws `NamingException`. Spring fails during bean creation if the binding is wrong, catching configuration issues early.

If you want to use the standard factory with an absolute name, **replace** the bean body with:

```java
return new JndiLocatorDelegate().lookup(
        "java:comp/DefaultJMSConnectionFactory",
        ConnectionFactory.class
);
```

Choose only one name confirmed by the administrator. Do not declare two `ConnectionFactory` beans with overlapping roles that make Spring injection ambiguous.

### 6.2. `JndiObjectFactoryBean`: Managing a JNDI Object as a `FactoryBean`

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jndi.JndiObjectFactoryBean;

@Configuration
public class JndiFactoryBeanConfig {

    @Bean("connectionFactory")
    public JndiObjectFactoryBean connectionFactoryFromJndi() {
        var bean = new JndiObjectFactoryBean();
        bean.setJndiName("jms/OrdersCF");
        bean.setResourceRef(true);
        bean.setExpectedType(ConnectionFactory.class);
        return bean;
    }
}
```

`JndiObjectFactoryBean` is a Spring `FactoryBean`, so the bean exposed to clients is the **looked-up `ConnectionFactory` object**, rather than requiring clients to call `getObject()` manually. This configuration is an **alternative option**; do not place it alongside the class in section 6.1 under the same `connectionFactory` name.

Spring defaults:

- `lookupOnStartup=true`: looks up during bean initialization, failing early if the resource is missing.
- `cache=true`: retains the looked-up object instead of looking it up again on each use.
- If lazy lookup (`lookupOnStartup=false`) or reloading the object (`cache=false`) is desired, appropriate proxy interfaces are required; use this only when the runtime truly requires it. Lazy lookup can push configuration errors out to message-sending time instead of startup.

JNDI bean lookup **does not open a JMS `Connection` by itself**, and caching a `ConnectionFactory` does not mean caching all `Session`s or creating a JMS pool.

## 7. Spring Boot: The `spring.jms.jndi-name` Property

Spring Boot 3 can be configured to look up `ConnectionFactory` from JNDI when running inside an application server. Some server-specific names Boot may probe are `java:/JmsXA` and `java:/XAConnectionFactory`. To use a name provisioned by the administrator, declare it explicitly:

```yaml
# src/main/resources/application.yml
spring:
  jms:
    jndi-name: "java:comp/env/jms/OrdersCF"
    pub-sub-domain: false
```

When the application starts in a runtime with the matching resource binding, Boot obtains the `ConnectionFactory` bean and can auto-configure `JmsTemplate`/JMS listener infrastructure based on the classpath. With this approach, **do not also declare a manual `ConnectionFactory` bean** as in section 6 unless you have a specific configuration reason. A standalone application without a JNDI context cannot succeed at lookup from this YAML alone.

### 7.1. Java 17 WAR Application Example Using a Managed Factory

This example uses **Spring Boot 3.3.x / Spring Framework 6**, deployed in a **Jakarta Servlet/Jakarta Messaging-compatible application server**. Before running, the admin must map `jms/OrdersCF` to `java:comp/env/jms/OrdersCF`, ensure the factory connects to the broker, and ensure Queue `orders.in` exists. Observed path: HTTP request → `JmsTemplate` → managed `ConnectionFactory` → Queue → `@JmsListener`.

Create `settings.gradle`:

```groovy
rootProject.name = 'managed-jndi-jms-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework:spring-jms'

    // Runtime Jakarta EE server provides JMS API/provider.
    compileOnly 'jakarta.jms:jakarta.jms-api'

    // Package WAR for deployment to an external Servlet container.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

In `src/main/resources/application.yml`:

```yaml
spring:
  jms:
    jndi-name: "java:comp/env/jms/OrdersCF"
    pub-sub-domain: false
```

Create `src/main/java/example/jms/ManagedJndiJmsApplication.java`:

```java
package example.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ManagedJndiJmsApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ManagedJndiJmsApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ManagedJndiJmsApplication.class, args);
    }
}
```

Create `src/main/java/example/jms/MessageEndpoint.java`:

```java
package example.jms;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class MessageEndpoint {

    private final JmsTemplate jmsTemplate;

    public MessageEndpoint(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @PostMapping(path = "/send",
                 consumes = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> send(@RequestBody String body) {
        if (body == null || body.isBlank()) {
            return ResponseEntity.badRequest().body("blank message");
        }

        jmsTemplate.convertAndSend("orders.in", body);
        return ResponseEntity.accepted().body("accepted");
    }
}
```

Create `src/main/java/example/jms/OrderListener.java`:

```java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.in")
    public void onOrder(String body) {
        System.out.println("JMS received: " + body);
    }
}
```

**Why does this example genuinely use JNDI?** The application **has no code instantiating a vendor factory with `new`**. Boot uses `spring.jms.jndi-name` to retrieve `ConnectionFactory`; `MessageEndpoint` only knows `JmsTemplate`. The factory on the server determines the endpoint/security/pooling. `OrderListener` also uses the Spring-configured JMS infrastructure.

### 7.2. Building and Verifying in the Appropriate Environment

With Gradle 8.5+ and Java 17, build the WAR:

```bash
gradle clean bootWar
```

If using the Gradle Wrapper, run `./gradlew clean bootWar` on Linux/macOS or `gradlew.bat clean bootWar` on Windows. The WAR file is placed in `build/libs/`. Deploy the WAR following the instructions of the application server where resource mapping is configured.

Assuming the server uses HTTP port 8080 and context path `/managed-jndi-jms-demo`, you can send a test message:

```bash
curl -i -X POST \
  -H "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "Hello JMS" \
  http://localhost:8080/managed-jndi-jms-demo/demo/send
```

If JNDI lookup, Queue, broker, permissions, and consumer all work, the endpoint can return `202 Accepted` with body `accepted`. If the listener in this app receives the message, the log can show:

```text
JMS received: Hello JMS
```

**This is conditional output**, not a result executed in a sample environment. Port/context path depend on the server, the Queue name must match, and if another consumer is on the same Queue, this listener is not guaranteed to receive the message. If the JNDI binding is missing, the Spring context may fail to initialize so no endpoint is available. Running `main()` outside an application server without a naming provider also will not automatically provide `java:comp/env`.

The endpoint above is learning demo code; real environments must enforce authentication, authorization limits, input validation, and anti-abuse policies before allowing message sends.

## 8. ConnectionFactory JNDI Differs from Destination JNDI

Both **`ConnectionFactory`** and **`Queue`/`Topic`** can be *JMS administered objects*; however, they are **two distinct resources**.

- Looking up `ConnectionFactory` via `spring.jms.jndi-name` only determines which factory Spring uses to create connections.
- `jmsTemplate.convertAndSend("orders.in", body)` by default resolves the string `orders.in` to a provider destination name via `DynamicDestinationResolver`; it **does not automatically fetch a `Queue` from JNDI**.
- If the server only permits destinations bound under `java:comp/env/jms/OrdersQueue`, inject the `Queue` or configure `JndiDestinationResolver`.

**Separate** example for a Spring Framework application configuring both objects via JNDI:

```java
@Bean
JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    var destinationResolver = new JndiDestinationResolver();
    destinationResolver.setResourceRef(true);

    var template = new JmsTemplate(connectionFactory);
    template.setDestinationResolver(destinationResolver);
    return template;
}
```

The snippet above belongs inside a `@Configuration` class and needs imports for `jakarta.jms.ConnectionFactory`, `org.springframework.jms.core.JmsTemplate`, and `org.springframework.jms.support.destination.JndiDestinationResolver`. When sending to `"jms/OrdersQueue"`, the resolver looks up `java:comp/env/jms/OrdersQueue`; corresponding bindings and ACLs must exist. The **listener container** also needs its own destination resolver if `@JmsListener(destination=...)` is meant to resolve JNDI names. Do not mix this example bean into the Spring Boot demo without determining how it replaces the auto-configured bean.

## 9. Lifecycle, Pooling, and Transactions After Lookup

### Proper Lifecycle

- A server-managed `ConnectionFactory` is usually a shared object; keep it as a Spring singleton and inject it into `JmsTemplate`/containers.
- `InitialContext.close()` closes the naming context; it **does not** reclaim the `ConnectionFactory` resource from the server.
- Do not call destroy/unbind on server resources during application shutdown. Close JMS connections/sessions **created directly by your own code** according to JMS rules; Spring helpers typically manage their own lifecycles.
- `JndiObjectFactoryBean` caching the looked-up object does not mean caching sessions. Likewise, a managed factory may already be pooled; do not blindly wrap it in `CachingConnectionFactory` or another pool without verifying compatibility with the container and transactions.

### Transactions Are a Separate Responsibility

A factory returned from JNDI may support JTA/XA, **but JNDI lookup does not automatically guarantee** DB and JMS participate in a single atomic transaction. You must verify the transaction manager, how Spring uses connections/sessions, server enlistment, and listener ack/commit behavior.

For example, a handler receives a message and writes to a database, then the application crashes before JMS acknowledges: the message may be **redelivered** even though the DB write persisted. Use a stable business event ID and idempotency/inbox handling where needed. Do not infer *exactly-once* guarantees for HTTP/DB side effects merely from using a JNDI factory.

### Two Distinct Failure Layers

```text
A. JNDI layer:
  NoInitialContext / NameNotFound / wrong Java type

B. JMS layer after lookup:
  broker unreachable / wrong credential / SSL / pool exhaustion
  destination missing / denied / transaction rollback / redelivery
```

A successful factory lookup **does not verify** connect/send/receive; to know the system is ready, run a smoke test against an authorized destination.

## 10. Diagnosing Common Errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoInitialContextException` | Application runs outside a naming provider/container or lacks a JNDI environment. | Verify runtime; do not assume `java:comp/env` exists under `java -jar`. |
| `NameNotFoundException` | Wrong name, unmapped resource-ref, wrong application scope, wrong `resourceRef`. | Check the bound name and scope in the admin console / deployment config. |
| `NamingException` or Spring `BeanCreationException` | Lookup failed due to naming config/permissions/lifecycle. | Inspect the **root cause** in the stack trace and server naming logs. |
| `ClassCastException`/type mismatch | Wrong bound type or mixing `javax.jms` with `jakarta.jms`. | Check interfaces, classloader, and API/provider versions. |
| `NoClassDefFoundError` (JMS API) | Missing JMS API at runtime or dependency/server module conflict. | Check Spring Boot WAR packaging, server Jakarta Messaging, and dependency tree. |
| Lookup OK but send fails | Broker down, wrong credentials/TLS, pool exhausted, invalid Queue/Topic. | Check broker health, ACLs, endpoint, pool, and vendor JMS logs. |
| App A succeeds, App B fails | Different ENC, principal, or resource mapping. | Compare deployment/roles/bindings for each application. |
| Changed JNDI binding but app uses old resource | Looked-up object is cached; requires redeploy or vendor-specific refresh config. | Check `cache`, `lookupOnStartup`, and lifecycle; do not disable caching lightly. |

**Reasonable troubleshooting order:** read the actual JNDI name → verify the resource is bound → verify the returned type is `jakarta.jms.ConnectionFactory` → test creating a connection / sending to an authorized Queue → check transactions, concurrent consumers, failover, and pool resources.

**Security:** Never accept arbitrary JNDI names from HTTP input or untrusted data to perform lookups; never dump the full JNDI environment, passwords, or sensitive message bodies into logs. Use allowlisted configuration names and apply least privilege to the application.

## 11. Testing, Deployment, and Responsibility Boundaries

**Unit tests:** only test service logic that uses `JmsTemplate` or an application-defined publisher interface via mocks/test doubles. Do not force unit tests to stand up an application server/JNDI provider to test business methods.

**Integration tests:** deploy on a real server or sufficiently equivalent environment to verify JNDI bindings, `jakarta.jms` compatibility, permissions, pooling, transactions, and destinations. If using a mock JNDI context, tests only verify name/type lookup and cannot prove XA/JTA or real server behavior.

**In production**, binding names should be externalized from source code and managed per deployment; admins supply certificates/credentials; monitor pool exhaustion, broker health, latency, and message retries. With a remote JNDI provider outside the server, setting `Context.INITIAL_CONTEXT_FACTORY`/`Context.PROVIDER_URL` must follow vendor docs and be properly secured. Do not assume remote JNDI behaves identically to Jakarta EE ENC.

| Environment | Reasonable choice |
| --- | --- |
| Spring Boot inside a Jakarta EE app server with a bound factory | `spring.jms.jndi-name` and auto-configured `JmsTemplate`. |
| Plain Spring Framework | `ConnectionFactory` bean via `JndiLocatorDelegate` or `JndiObjectFactoryBean`. |
| Container-managed Jakarta EE component | `@Resource(lookup="...")` or `InitialContext`. |
| Standalone app without a JNDI naming provider | Configure the client/provider `ConnectionFactory` directly; only use JNDI when a real provider/binding exists. |
| Multiple factories | Give beans clear names, inject with `@Qualifier`; avoid mixing transaction domains. |

## 12. Knowledge Self-Check

**Question 1:** Why can `java:comp/env/jms/OrdersCF` be looked up inside a server yet fail in a standalone Java SE JVM?

**Answer:** ENC is typically provided by the container and bound in application scope; Java SE does not automatically have that provider/binding.

**Question 2:** With Spring `resourceRef=true` and `jndiName="jms/OrdersCF"`, what final name is used?

**Answer:** `java:comp/env/jms/OrdersCF`; this does not create the factory itself.

**Question 3:** Why must we import `jakarta.jms.ConnectionFactory` while still using `javax.naming.InitialContext`?

**Answer:** Jakarta Messaging changed namespace; JNDI remains the `javax.naming` API in the JDK.

**Question 4:** Does a successful lookup prove the broker is ready, XA transactions work, and the destination exists?

**Answer:** No. Each condition must be verified against the JMS/server runtime.

**Question 5:** Does configuring only a JNDI `ConnectionFactory` cause `@JmsListener(destination="jms/OrdersQueue")` to automatically look up the `Queue` from JNDI?

**Answer:** No. Destination resolution requires configuring a `JndiDestinationResolver` on the listener container or injecting the corresponding destination.

**Question 6:** When a managed factory is already pooled/XA-enabled, should you automatically wrap it in another pool?

**Answer:** Not by default. Evaluate lifecycle, session/connection caching, transaction enlistment, and vendor policies first.

## 13. References

- [Jakarta Messaging: ConnectionFactory API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/connectionfactory)
- [Jakarta EE Tutorial: JMS administered objects and JNDI](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
- [Spring Framework: Using JMS / Connections](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework 6.2: JndiLocatorDelegate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jndi/JndiLocatorDelegate.html)
- [Spring Framework 6.2: JndiObjectFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jndi/JndiObjectFactoryBean.html)
- [Spring Boot: JMS and `spring.jms.jndi-name`](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html)
- [Java SE 17: InitialContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/InitialContext.html)

**Takeaway:** The application server **creates and binds** the JMS factory; Spring **looks up the right JNDI name** to obtain **`jakarta.jms.ConnectionFactory`**; then `JmsTemplate` and listeners **use the factory to talk to the provider**. Each step has its own failures and responsibilities.
