# Defining lifecycle ownership and resource cleanup for auto-configured beans

> **Spring Boot Auto-Configuration → Extension points.** This lesson defines who is responsible for creating, using, stopping, and releasing resources held by beans provided by auto-configuration. It focuses on Spring container management authority, how auto-configuration yields to application-supplied beans, destruction callbacks, differences between singleton/prototype scopes, and cleanup testing. Examples use Java 17+ and Spring Boot 3.3.x.

## 1. Why being able to create a bean does not mean resources are managed properly

An auto-configuration may provide beans that hold external resources:

- Connection pools, database clients, or HTTP clients.
- File handles, sockets, channels, and native handles.
- Executors, schedulers, and worker threads.
- Message consumers or listener containers.
- Caches, SDKs, or libraries exposing a `close()` / `shutdown()` method.

If a bean is created without a release policy, the application can leak file descriptors, keep threads alive preventing the JVM from exiting, fail to return connections to the pool, hold open ports, or keep processing work after the context has closed.

For Spring-managed beans, the contract should be:

1. Auto-configuration decides whether the bean is registered and how it is created.
2. The Spring container creates the instance, injects dependencies, and manages its lifecycle within the bean's scope.
3. Consuming beans only use the injected dependency; they do not arbitrarily close a resource they do not own.
4. When the scope ends, the container invokes the registered destruction callback.
5. If the application provides a replacement bean, the application's configuration is responsible for declaring the appropriate lifecycle for that bean.

**Auto-configuration provides the bean definition; the Spring container manages instance lifecycle.** A library must clearly document how resources owned by its beans are closed, rather than forcing users to guess when to call `close()`.

## 2. Distinguishing creation rights, usage rights, and cleanup rights

| Role | Responsibility | Example |
| --- | --- | --- |
| Bean definition owner | Decides whether the bean is registered, factory method, scope, and destroy callback | Auto-configuration or application-authored configuration |
| Spring container | Creates instances, injects dependencies, invokes lifecycle callbacks, and destroys beans by scope | `ApplicationContext` / `BeanFactory` |
| Bean consumer | Uses the dependency while the bean remains valid | Service calling `HttpClient` or `WorkerResource` |

Example:

~~~text
WorkerAutoConfiguration
       |
       +-- registers ManagedClient bean definition
       |          |
       |          +-- destroyMethod = close
       |
       v
Spring IoC Container
       |
       +-- creates ManagedClient
       +-- injects ManagedClient into FeatureService
       +-- manages dependencies and scope
       |
       +-- when the context closes:
                 destroys consuming beans first
                 calls ManagedClient.close()
~~~

A consuming service may hold a reference to `ManagedClient`, yet that **does not make the service the resource owner**. If both the service and the container call `close()` on a singleton client, cleanup can run twice or close a connection while another bean is still using it.

A solid ownership contract must answer:
- Which bean actually owns the resource?
- Who creates the bean and registers it with the container?
- What is the bean's scope?
- Which callback stops or releases the resource?
- When the user provides a replacement bean, who declares the destroy callback?
- Which beans must stop before the underlying resource?

## 3. Bean lifecycle and cleanup timing

For a typical singleton, the lifecycle can be illustrated as:

~~~text
1. Read configuration / auto-configuration
                  |
                  v
2. Register BeanDefinition
                  |
                  v
3. Instantiate bean
                  |
                  v
4. Inject dependencies / process Aware
                  |
                  v
5. BeanPostProcessor and initialization callbacks
                  |
                  v
6. Bean ready for application use
                  |
                  v
7. ApplicationContext begins closing
                  |
                  v
8. Stop lifecycle-managed beans
                  |
                  v
9. Destroy singletons in dependency order
                  |
                  v
10. Invoke destroy callbacks / close resources
~~~

Key points:

- Auto-configuration is processed and bean definitions are registered before bean instances are created.
- Dependency injection tells Spring which bean depends on which. Consuming beans are normally created after their dependencies and destroyed before their dependencies.
- Beans can declare initialization callbacks and destruction callbacks.
- When `ApplicationContext` closes, Spring invokes registered destroy callbacks for beans within managed scopes.
- Injecting one bean into another does not transfer lifecycle ownership to the consuming bean.

A context can close via `context.close()`, try-with-resources on an appropriate context, or a shutdown hook when the JVM exits. Spring Boot registers a shutdown hook by default for standard applications. While the process is still running, the context remains open and singleton destroy callbacks have not yet been called.

### 3.1. Singleton

Singleton is the default scope: one instance per container. When the context closes, the container invokes the destruction callback registered in the bean definition.

This is the common choice for connection pools, shared HTTP clients, schedulers, or background services supplied by auto-configuration.

If singleton A is injected into singleton B, Spring knows the dependency relationship and can destroy B before A. This gives B a chance to stop its work before A is closed.

### 3.2. Prototype

With `prototype` scope, Spring creates a new instance each time the bean is requested, but after handing the instance to the caller, the container **does not automatically invoke destruction callbacks when the caller stops using it**.

Therefore, you should not create a resource-bearing prototype bean and expect Spring to close it once no references remain. The caller or a dedicated management mechanism must handle cleanup.

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
ManagedResource newManagedResource() {
    return new ManagedResource();
}
~~~

This is an illustrative configuration snippet. If `ManagedResource` holds a file/socket/client, the caller receiving the instance must know about and perform cleanup. For application-wide shared resources, singleton scope is usually easier to manage.

### 3.3. Custom scopes

Request, session, or custom scopes can invoke destroy callbacks when the scope ends. Behavior depends on the scope's implementation. Do not assume every scope closes beans at the exact same timing as singleton.

When designing auto-configuration, pick the scope based on **the resource's lifetime**. Shared connection pools should generally not be prototypes; objects holding no external resources may fit shorter scopes.

## 4. Destruction callbacks supported by Spring

| Mechanism | Where declared | When appropriate |
| --- | --- | --- |
| `@Bean(destroyMethod = "close")` | Factory method creating the bean | Library wants to explicitly advertise how the resource is closed |
| Inferred destroy method | `@Bean` returning an object with a matching public `close()` / `shutdown()` | Follows Spring's default convention |
| `@PreDestroy` | Method inside the bean class | Bean declares its own cleanup using a Jakarta annotation |
| `DisposableBean.destroy()` | Bean implements Spring interface | Integration requiring Spring's lifecycle API |
| `DestructionAwareBeanPostProcessor` | Extension infrastructure | Special cleanup policy applied across multiple beans |
| `SmartLifecycle.stop(...)` | Bean with start/stop lifecycle | Workers, listeners, or background components needing coordinated shutdown |

### 4.1. @Bean(destroyMethod = "close")

~~~java
@Bean(destroyMethod = "close")
ManagedClient managedClient() {
    return new ManagedClient();
}
~~~

When the singleton bean is destroyed, Spring invokes the declared `close()` method. The method must exist on the returned object and be callable.

Spring also supports inferring certain public destruction methods like `close` or `shutdown` by `@Bean` default convention. For critical resources, explicit declaration makes the contract easier to read and prevents maintainers from overlooking inference.

If you deliberately do not want Spring to infer a destruction method, `@Bean(destroyMethod = "")` disables default inference. Only use that when another cleanup mechanism is established; never disable the callback and leave resources leaking.

### 4.2. AutoCloseable and Closeable

Java provides `AutoCloseable`:

~~~java
public final class ManagedClient implements AutoCloseable {

    @Override
    public void close() {
        // release resources
    }
}
~~~

`Closeable` extends `AutoCloseable` and is commonly used for I/O. Implementing the interface clearly signals that the object can be closed.

For a Spring-managed singleton bean, you can combine:

~~~java
@Bean(destroyMethod = "close")
ManagedClient managedClient() {
    return new ManagedClient();
}
~~~

Do not confuse `AutoCloseable` with using try-with-resources inside a consuming bean. If the container owns the bean, the container invokes the callback when the lifecycle ends; the consumer should not close the injected reference after each use.

### 4.3. @PreDestroy

In Spring Boot 3 / Spring Framework 6, the annotation comes from Jakarta:

~~~java
import jakarta.annotation.PreDestroy;

public class ManagedClient {

    @PreDestroy
    public void release() {
        // release resources
    }
}
~~~

`@PreDestroy` fits when the class itself declares its cleanup action without implementing a Spring interface. The bean must be Spring-managed and annotation lifecycle infrastructure must be active.

If you combine `@PreDestroy` with `@Bean(destroyMethod = "close")`, `DisposableBean`, or another callback that all perform the same action, avoid duplicate cleanup. Pick one primary mechanism or make cleanup idempotent.

### 4.4. DisposableBean

~~~java
import org.springframework.beans.factory.DisposableBean;

public class ManagedClient implements DisposableBean {

    @Override
    public void destroy() {
        // release resources
    }
}
~~~

This API couples directly to Spring. It is useful in certain integrations but ties the class to Spring. For libraries wanting to keep resource classes framework-independent, `AutoCloseable` plus `@Bean(destroyMethod = "close")` usually creates a cleaner boundary.

### 4.5. Making cleanup safe

Do not simultaneously:
- Call `close()` in `@PreDestroy`;
- Implement `DisposableBean.destroy()` also calling `close()`;
- Declare `@Bean(destroyMethod = "close")`;
- Require consumers to call `close()` manually.

Multiple callbacks can all participate in the lifecycle, causing a double-close. If `close` is not idempotent, the second call may throw an exception or operate on an already-released resource.

A good `close()` method should:
- Be safe to call repeatedly if the contract calls for idempotency;
- Mark closed state and reject new operations;
- Stop or wait for in-flight work within a time limit;
- Close resources in a sensible order;
- Not swallow critical cleanup exceptions;
- Clean up remaining resources even if one closing step fails, typically using `try/finally` or suppressed exceptions.

## 5. Designing an auto-configuration with lifecycle responsibility

An auto-configuration providing a resource-bearing bean must define:

1. **Activation conditions:** which properties, classpath types, or beans must exist?
2. **Bean owner:** does auto-configuration create a default bean or yield to the application?
3. **Scope:** singleton, prototype, or another scope?
4. **Resource owner:** which bean actually holds and releases the resource?
5. **Destroy callback:** `close`, `shutdown`, `@PreDestroy`, or lifecycle protocol?
6. **Dependency order:** which workers/listeners must stop before the client/pool?
7. **Override contract:** if the user supplies their own bean, how must the user handle cleanup?

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.worker",
    name = "enabled",
    havingValue = "true"
)
public class WorkerAutoConfiguration {

    @Bean(destroyMethod = "close")
    @ConditionalOnMissingBean(ManagedWorkerResource.class)
    ManagedWorkerResource managedWorkerResource() throws IOException {
        return new ManagedWorkerResource();
    }
}
~~~

Three annotations carry three responsibilities:
- `@ConditionalOnProperty` enables auto-configuration only when the property permits it.
- `@ConditionalOnMissingBean` lets the application provide a replacement bean.
- `@Bean(destroyMethod = "close")` registers the resource-release callback for the bean created by the factory method.

### 5.1. When the user overrides the bean, who is responsible for cleanup?

~~~java
@Configuration(proxyBeanMethods = false)
class UserWorkerConfiguration {

    @Bean(destroyMethod = "close")
    ManagedWorkerResource managedWorkerResource() throws IOException {
        return new ManagedWorkerResource();
    }
}
~~~

If this bean is registered before auto-configuration evaluates `@ConditionalOnMissingBean`, the default configuration backs off. **The replacement bean is still managed by the Spring container** because it is also registered via Spring; however, the configuration owned by the application must declare the appropriate lifecycle contract.

Auto-configuration should not look up and close a user-supplied bean on its own. The library only owns resources inside the default bean it creates. When users override it, users are responsible for ensuring their bean has proper cleanup.

### 5.2. Do not close an injected dependency as if you own it

~~~java
@Bean
FeatureService featureService(ManagedWorkerResource resource) {
    return new FeatureService(resource);
}
~~~

`FeatureService` uses `resource`; Spring knows this dependency. If `FeatureService` has a destruction callback, that callback should stop the service's own work, not arbitrarily call `resource.close()` when the resource belongs to another singleton bean.

The container tracks dependency relationships and destroys dependent beans before their dependencies. The service can stop accepting work and finish or cancel active tasks before the underlying resource is closed.

### 5.3. Do not use @DependsOn instead of dependency injection

`@DependsOn` can force one bean to initialize before another and ensure a dependent singleton is destroyed before the bean it depends on. However, if bean A is directly injected into bean B, Spring already knows the dependency relationship.

Only use `@DependsOn` when an initialization/destruction constraint cannot be expressed through direct dependency injection. It does not replace `@Bean(destroyMethod=...)`, does not register missing beans, and does not turn a consumer into the resource owner.

## 6. Runnable example: auto-configuration creates a resource and Spring closes it

This lab creates a temporary file as a representative resource. The `ManagedWorkerResource` bean opens the file, writes data, and then closes the stream and deletes the file when the Spring context ends.

We want to observe:
- When `demo.worker.enabled=true`, the bean is created by auto-configuration.
- When the feature is disabled or omitted, auto-configuration does not create the bean.
- When the context closes, the `close()` callback runs and the temporary file is deleted.
- `ApplicationRunner` only uses the bean and does not call `close()`.

Requirements: JDK 17+, Maven, and dependency download access. Example version: Spring Boot 3.3.13.

### 6.1. Project structure

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/
    │   │       ├── app/
    │   │       │   └── LifecycleDemoApplication.java
    │   │       └── worker/
    │   │           ├── ManagedWorkerResource.java
    │   │           └── autoconfigure/
    │   │               └── WorkerAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── demo/
                └── worker/
                    └── WorkerAutoConfigurationTest.java
~~~

The application resides in `demo.app`, and auto-configuration in `demo.worker.autoconfigure`. The application's component scan does not automatically scan the auto-configuration class; Boot discovers it via `AutoConfiguration.imports`.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. ManagedWorkerResource.java

File `src/main/java/demo/worker/ManagedWorkerResource.java`:

~~~java
package demo.worker;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class ManagedWorkerResource implements AutoCloseable {

    private final Path file;
    private final OutputStream output;
    private boolean closed;

    public ManagedWorkerResource() throws IOException {
        Path created = Files.createTempFile("managed-worker-", ".txt");
        OutputStream opened;

        try {
            opened = Files.newOutputStream(
                    created,
                    StandardOpenOption.WRITE
            );
        } catch (IOException openFailure) {
            try {
                Files.deleteIfExists(created);
            } catch (IOException cleanupFailure) {
                openFailure.addSuppressed(cleanupFailure);
            }
            throw openFailure;
        }

        this.file = created;
        this.output = opened;
        System.out.println("resource opened");
    }

    public synchronized void write(String message) throws IOException {
        if (closed) {
            throw new IllegalStateException("Resource is already closed");
        }
        output.write(message.getBytes(StandardCharsets.UTF_8));
        output.flush();
    }

    @Override
    public synchronized void close() throws IOException {
        if (closed) {
            return;
        }

        IOException failure = null;

        try {
            output.close();
        } catch (IOException closeFailure) {
            failure = closeFailure;
        }

        try {
            Files.deleteIfExists(file);
        } catch (IOException deleteFailure) {
            if (failure == null) {
                failure = deleteFailure;
            } else {
                failure.addSuppressed(deleteFailure);
            }
        }

        if (failure != null) {
            throw failure;
        }

        closed = true;
        System.out.println("resource closed");
    }

    Path filePath() {
        return file;
    }
}
~~~

Explanation:
- The constructor creates a temporary file and opens an `OutputStream`. If opening the stream fails, it attempts to delete the created file; cleanup errors are preserved as suppressed exceptions.
- `write()` checks state and then writes UTF-8 bytes.
- `close()` closes the stream and then deletes the file even if closing the stream failed.
- If a cleanup step fails, the method throws an exception instead of silently treating it as success.
- The `closed` flag makes a successful close idempotent; subsequent calls do not repeat operations on an already-released resource.

This is a real resource for the lab, though not representative of a complete database/network client. The goal is to observe the file being created and deleted according to the bean's lifecycle.

### 6.4. WorkerAutoConfiguration.java

File `src/main/java/demo/worker/autoconfigure/WorkerAutoConfiguration.java`:

~~~java
package demo.worker.autoconfigure;

import java.io.IOException;

import demo.worker.ManagedWorkerResource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.worker",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class WorkerAutoConfiguration {

    @Bean(destroyMethod = "close")
    @ConditionalOnMissingBean(ManagedWorkerResource.class)
    ManagedWorkerResource managedWorkerResource() throws IOException {
        return new ManagedWorkerResource();
    }
}
~~~

Three annotations carry three responsibilities:
1. `@ConditionalOnProperty` enables auto-configuration only when the property permits it.
2. `@ConditionalOnMissingBean` lets the application provide a replacement bean.
3. `@Bean(destroyMethod = "close")` registers the resource-release callback for the bean created by the factory method.

### 6.5. AutoConfiguration.imports file

Create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Exactly one line of content:

~~~text
demo.worker.autoconfigure.WorkerAutoConfiguration
~~~

The class name must match the package and class name. If the file is missing or wrong, Boot will not find the auto-configuration through the starter registration mechanism; setting `demo.worker.enabled=true` alone will not make the bean appear.

### 6.6. LifecycleDemoApplication.java

File `src/main/java/demo/app/LifecycleDemoApplication.java`:

~~~java
package demo.app;

import demo.worker.ManagedWorkerResource;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner useWorkerResource(
            ObjectProvider<ManagedWorkerResource> resources) {

        return args -> {
            ManagedWorkerResource resource = resources.getIfAvailable();

            System.out.println(
                    "worker resource present: " + (resource != null)
            );

            if (resource != null) {
                resource.write("sample payload");
                System.out.println("resource used");
            }
        };
    }
}
~~~

`ObjectProvider` allows the application to use the bean optionally. If the feature is disabled, the runner still executes without failing due to a missing dependency. When the bean exists, the runner uses it but **does not call `close()`**.

### 6.7. Packaging and running

From the `lifecycle-demo` directory:

~~~bash
mvn -q -DskipTests package
~~~

**Case A — feature enabled:**

~~~bash
java -jar target/lifecycle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.worker.enabled=true
~~~

Stdout lines printed by the program:

~~~text
resource opened
worker resource present: true
resource used
resource closed
~~~

Explanation:
1. Runner requests the bean; Spring creates `ManagedWorkerResource`, and its constructor opens the file.
2. Runner writes data and finishes using the reference.
3. When the Java process exits, Spring Boot's shutdown hook closes `ApplicationContext`.
4. The container invokes `destroyMethod="close"` and the resource is released.

**Case B — feature disabled:**

~~~bash
java -jar target/lifecycle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.worker.enabled=false
~~~

Stdout:

~~~text
worker resource present: false
~~~

No file is created because the default bean does not appear.

**Case C — property omitted:**

~~~bash
java -jar target/lifecycle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout is also:

~~~text
worker resource present: false
~~~

This is expected because `matchIfMissing=false` is configured. The results above describe the lines printed by the program's `System.out.println`; internal logs may vary by environment and configuration.

In PowerShell/CMD you can run each single-line Java command as shown above. When running in an IDE where the JVM stays alive, the context only closes when the application stops or code explicitly closes the context.

## 7. Testing that closing the context actually releases the resource

Verifying only that the bean exists is not enough. For a resource-bearing bean, you must confirm that **after the context terminates, the resource has been closed**.

File `src/test/java/demo/worker/WorkerAutoConfigurationTest.java`:

~~~java
package demo.worker;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            WorkerAutoConfiguration.class
                    ));

    @Test
    void missingPropertyDoesNotCreateResource() {
        runner.run(context ->
                assertThat(context)
                        .doesNotHaveBean(ManagedWorkerResource.class)
        );
    }

    @Test
    void falsePropertyDoesNotCreateResource() {
        runner.withPropertyValues("demo.worker.enabled=false")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(ManagedWorkerResource.class)
                );
    }

    @Test
    void closingContextReleasesAutoConfiguredResource() {
        AtomicReference<Path> resourcePath = new AtomicReference<>();

        runner.withPropertyValues("demo.worker.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(ManagedWorkerResource.class);

                    ManagedWorkerResource resource =
                            context.getBean(ManagedWorkerResource.class);

                    Path path = resource.filePath();
                    resourcePath.set(path);

                    assertThat(Files.exists(path)).isTrue();
                });

        // ApplicationContextRunner closes the context after the callback.
        assertThat(resourcePath.get()).isNotNull();
        assertThat(Files.exists(resourcePath.get())).isFalse();
    }
}
~~~

The test resides in the same `demo.worker` package to call the package-private `filePath()` method; that method exists for observation in the lab, not as a public library API.

Run:

~~~bash
mvn test
~~~

Expected **3 tests PASS**:
- No configuration → no resource created.
- `enabled=false` → no resource created.
- `enabled=true` → resource exists in the context; after the test callback finishes and the context closes, the file no longer exists.

This is a lifecycle test with direct evidence: the file is created while the bean is alive and deleted after the container destroys the bean.

## 8. When a bean runs background work: stop first, close later

A bean holding only a simple file or client may only need `close()`. However, a worker, message listener, or scheduler also has active running work. When the application stops, it needs to stop accepting new work, wait for or cancel running work, and only then release shared resources.

`Lifecycle` / `SmartLifecycle` is intended for components needing a coordinated start/stop procedure:

- `Lifecycle.start()` begins activity.
- `Lifecycle.stop()` stops activity.
- `SmartLifecycle` adds `isAutoStartup()`, `getPhase()`, and the `stop(Runnable callback)` callback.
- `phase` determines start/stop ordering among lifecycle beans; during shutdown, components with higher phase values are stopped before those with lower phase values.
- The callback in `stop(Runnable)` must be invoked once the component has finished stopping.

Illustrative component snippet:

~~~java
public final class BackgroundWorker implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // start accepting work
    }

    @Override
    public void stop() {
        running = false;
        // stop accepting work and release running tasks
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

This example illustrates the contract; a real implementation must be thread-safe, stop running tasks, and enforce appropriate timeouts. If the bean also holds sockets/files/clients, it can provide a destruction callback to **close resources after stopping**.

Do not treat `stop()` and `close()` as synonyms:
- `stop()` halts lifecycle-managed activity.
- `close()` / destroy callbacks release resources owned by the bean.

### 8.1. Graceful shutdown of web applications

For Spring Boot web applications, graceful shutdown for the server is a separate mechanism to stop accepting new requests and allow active requests time to complete. It can be configured with:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

The timeout must match your SLA and actual shutdown duration. Graceful shutdown does not replace destroy callbacks closing database pools or bean-owned clients; the two parts must coordinate so in-flight requests do not lose resources prematurely.

## 9. Destruction order and dependency relationships

Suppose:

~~~text
FeatureService
     |
     v
WorkerClient
     |
     v
ConnectionPool
~~~

`FeatureService` uses `WorkerClient`; `WorkerClient` uses `ConnectionPool`. When Spring knows the dependencies through injection, the container can destroy them in reverse dependency order:
1. Stop/destroy `FeatureService`.
2. Destroy `WorkerClient` once consumers no longer use it.
3. Finally close `ConnectionPool`.

Do not close the pool inside `FeatureService.destroy()` if the pool belongs to `WorkerClient` or another auto-configuration. When multiple beans hold references to a singleton pool, the pool must stay alive until all consumers have stopped.

If a shutdown relationship cannot be expressed via injection, consider `@DependsOn`, `SmartLifecycle` phases, or a dedicated coordinator. Avoid forcing ordering through constructor side effects or relying on line order in source code.

## 10. Common mistakes when managing resources of auto-configured beans

1. **Creating a resource without declaring a destruction callback.** The bean can live for the entire application lifetime; file handles, threads, or connections are not closed on time.
2. **Consumer manually calling `close()` on an injected bean.** Can break other consumers sharing the same singleton.
3. **Closing the same resource in multiple callbacks.** `@PreDestroy`, `DisposableBean`, `destroyMethod`, and manual calls can cause cleanup to run repeatedly.
4. **Thinking prototypes are automatically closed by Spring.** The container does not automatically invoke destruction callbacks for prototypes after handing the instance to the caller.
5. **Using `@DependsOn` instead of injecting dependencies.** Makes initialization order look right while hiding real dependencies and failing to replace release callbacks.
6. **Closing the pool before stopping workers.** Running tasks may use closed resources; stop consumers first.
7. **Swallowing exceptions in `close()`.** The application reports a clean shutdown while files or connections remain unreleased.
8. **Waiting forever during shutdown.** A stuck worker can stall JVM exit; enforce timeouts and interrupt/force-stop policies.
9. **Auto-config closing user-provided beans.** Violates ownership boundaries; let the user's bean definition manage callbacks for the user's bean.
10. **Assuming `@ConditionalOnMissingBean` releases the old bean.** The annotation only decides whether to register a default bean; it is not a mechanism to replace/destroy existing objects.
11. **Using `@Bean(destroyMethod = "")` without another owner.** Disables inferred callbacks without establishing a new cleanup mechanism.
12. **Spawning threads or executors in constructors without managing shutdown.** Threads can keep the JVM alive or keep accessing closed dependencies.
13. **Putting all cleanup into one coordinator bean.** Dependency order and ownership become hard to trace; each bean should release the resources it owns.
14. **Not testing after context closure.** Tests checking only bean presence will not catch leaked resources.
15. **Confusing shutdown hooks with immediate cleanup.** Callbacks only run when the context closes; changing properties or finishing a request does not close a singleton.

## 11. Design checklist before releasing a starter

- [ ] Identify which bean truly owns each resource.
- [ ] Let the Spring container manage long-lived beans; avoid creating objects outside the container without a clear owner.
- [ ] Choose a scope matching the resource's lifetime.
- [ ] Declare `destroyMethod="close"` / `"shutdown"` or an appropriate destruction callback.
- [ ] Make cleanup idempotent when possible; avoid unintended double release.
- [ ] Ensure consuming beans stop before underlying resources.
- [ ] Use `SmartLifecycle` for workers/listeners needing coordinated start–stop.
- [ ] When using `@ConditionalOnMissingBean`, document the contract for user replacement beans and let users manage their bean's lifecycle.
- [ ] Do not let consumers close singleton dependencies they merely use.
- [ ] Set timeouts for shutdown tasks that wait.
- [ ] Test both bean presence/absence conditions and resource state after the context closes.
- [ ] Verify application shutdown via JVM shutdown hook, `context.close()`, or the corresponding managed lifecycle.
- [ ] Document clearly which beans are auto-created, when they are closed, and what user overrides must declare.

## 12. Self-check questions

**Question 1.** Auto-configuration creates a singleton `HttpClient` via `@Bean`. Who invokes cleanup when the Spring context closes?  
**Answer:** The Spring container invokes the destruction callback registered in the bean definition; auto-configuration must declare an appropriate callback.

**Question 2.** A service is injected with a singleton `HttpClient`. Should the service call `httpClient.close()` in `@PreDestroy`?  
**Answer:** No, if the service is only a consumer. The client belongs to the lifecycle of the bean definition that owns it; the container coordinates dependency destruction.

**Question 3.** The user supplies their own bean instead of the default via `@ConditionalOnMissingBean`. Must auto-configuration close the user's bean?  
**Answer:** No. The user configuration owns creation and must declare an appropriate lifecycle callback; the Spring container still manages that bean.

**Question 4.** A prototype bean implements `AutoCloseable`. Does Spring automatically call `close()` when the caller drops the reference?  
**Answer:** No. The caller or a dedicated management mechanism is responsible for prototype cleanup.

**Question 5.** Does `@DependsOn` replace `@Bean(destroyMethod="close")`?  
**Answer:** No. `@DependsOn` specifies initialization/destruction ordering relationships between beans; it does not specify how resources are released.

**Question 6.** Does `SmartLifecycle.stop()` mean all files/sockets/clients have already been closed?  
**Answer:** No. `stop()` halts lifecycle-managed activity; destruction callbacks are still needed to close resources owned by the bean.

**Question 7.** How can you prove that a resource was actually released?  
**Answer:** Create the resource in a context, observe it exists while the context is open, close the context, and then verify the file/connection/handle no longer exists or is no longer active.

## 13. Conclusion and references

Lifecycle ownership must be clear from the moment an auto-configuration is designed. Library-created beans need a destruction contract executed by the Spring container; consuming beans only use dependencies; user-supplied beans have their lifecycle determined by user configuration. For resources with background work, coordinate **stop first, destroy/close second**. For prototype scope, the caller must manage cleanup.

Three principles:
1. Whenever you create a bean holding a resource, define who closes the resource and which callback the container invokes.
2. Being injected with a dependency does not grant ownership; do not close another bean's resource just because you hold a reference.
3. Test after context closure to prove the resource is genuinely released.

Official documentation:
- [Spring Framework — Bean Lifecycle and Initialization/Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle).
- [Spring Framework — Bean Scopes, including Prototype](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html).
- [Spring Framework Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html).
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)