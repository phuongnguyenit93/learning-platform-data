# Prototype Resource Cleanup Responsibility

In Spring, a bean with `prototype` scope is newly created each time the container is asked to provide that bean. Spring is responsible for instantiation, dependency injection, and running initialization callbacks. After handing the instance to the caller, the container does not automatically manage the prototype's destruction step.

This point is critical when a prototype opens files, holds sockets, creates sessions, or owns resources that must be closed. **The code receiving the instance must take responsibility for releasing the resources the instance owns.**

## 1. Where Does the Prototype Lifecycle End?

When Spring creates a prototype bean, the main steps are similar to other scopes:

1. Spring instantiates the object.
2. The container injects dependencies and applies bean processing steps.
3. Spring runs initialization callbacks, such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or a declared `initMethod`.
4. Spring returns the instance to the component requesting the bean.

After step four, Spring does not track the full usage lifecycle of the prototype instance to automatically invoke destruction callbacks when the instance is no longer used. Consequently, when the `ApplicationContext` closes, Spring does not automatically invoke destruction callbacks for previously issued prototypes either.

This differs from singleton. For singletons, the container manages the instance throughout the `ApplicationContext` lifecycle and can call destruction callbacks when the context closes. For prototypes, the container only manages creation and initialization before handing the instance to the caller.

## 2. Destruction Callbacks That Do Not Run Automatically for Prototypes

The following mechanisms are not automatically invoked by Spring for a prototype bean merely because it was created by the container:

- Methods annotated with `@PreDestroy`.
- `DisposableBean.destroy()`.
- Destruction methods declared via `@Bean(destroyMethod = "...")`.
- `close()` or `shutdown()` methods inferred by Spring for resource-closing beans.

For example, the following declaration does not make Spring automatically call `close()` when a prototype finishes being used:

~~~java
@Configuration
public class ExportConfiguration {

    @Bean(destroyMethod = "close")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    ExportSession exportSession() {
        return new ExportSession();
    }
}
~~~

The `destroyMethod` attribute still applies to beans whose destruction lifecycle is managed by the container, yet it creates no automatic reclamation mechanism for prototypes. If `ExportSession` opens files or holds connections, the code using it must invoke the appropriate release method.

Similarly, adding `@PreDestroy` to a prototype method does not remove that responsibility:

~~~java
@PreDestroy
public void cleanup() {
    // Not automatically called by Spring for prototypes.
}
~~~

Do not rely on `ApplicationContext` shutdown to release prototype resources.

## 3. The Instance Owner Must Release Resources

A clear approach is having the prototype implement `AutoCloseable` or `Closeable`, then using try-with-resources where the instance is retrieved.

For example, each `ExportSession` opens a file to write data:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ExportSession implements AutoCloseable {

    private final BufferedWriter writer;

    public ExportSession(
            @Value("${app.export.directory}") String directory)
            throws IOException {

        Path output = Path.of(
                directory,
                UUID.randomUUID() + ".txt"
        );

        this.writer = Files.newBufferedWriter(
                output,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
        );
    }

    public void write(String content) throws IOException {
        writer.write(content);
        writer.newLine();
    }

    @Override
    public void close() throws IOException {
        writer.close();
    }
}
~~~

Each time the container provides `ExportSession`, a new instance is created and opens its own file. The `close()` method closes the writer, thereby releasing the held file handle.

The component using the prototype can receive `ObjectProvider` to obtain a fresh instance for each export:

~~~java
import java.io.IOException;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    private final ObjectProvider<ExportSession> sessions;

    public ExportService(ObjectProvider<ExportSession> sessions) {
        this.sessions = sessions;
    }

    public void export(String content) throws IOException {
        try (ExportSession session = sessions.getObject()) {
            session.write(content);
        }
    }
}
~~~

The sequence in `export()` is:

1. `sessions.getObject()` asks Spring to create and return a prototype instance.
2. `try` uses the instance to write content.
3. Upon leaving the `try` block, Java automatically calls `session.close()`, even if writing throws an exception.
4. Resources owned by the session are released.

Resource closing here is handled by Java's try-with-resources via the `AutoCloseable` contract; Spring does not have to invoke destruction callbacks for the prototype.

If the class does not implement `AutoCloseable`, call the release method inside `finally`:

~~~java
ExportSession session = sessions.getObject();
try {
    session.write(content);
} finally {
    session.close();
}
~~~

Try-with-resources is usually easier to read and less prone to missed cleanup. If `close()` might be called multiple times, the class should clearly define idempotent close behavior; many resource APIs already support safe repeated closing.

## 4. Using ObjectProvider to Retrieve Prototypes at the Right Time

There is a common point of confusion: injecting a prototype directly into a singleton does not make Spring create a new prototype whenever the singleton calls a method.

Example:

~~~java
@Service
public class ExportService {

    private final ExportSession session;

    public ExportService(ExportSession session) {
        this.session = session;
    }

    public void export(String content) throws IOException {
        session.write(content);
    }
}
~~~

When Spring creates the `ExportService` singleton, it also obtains one `ExportSession` instance to pass to the constructor. That instance is retained in the singleton and reused in subsequent calls to `export()`. It does not automatically swap to a fresh prototype on every call.

If the business requirement is a separate session per execution, use `ObjectProvider<ExportSession>` and call `getObject()` when a session needs to be created, as in the previous section. Each retrieved instance must be closed by the component that took ownership of it.

`ObjectProvider` defers bean retrieval and makes instantiation points explicit. It does not automatically release prototypes after use; closing responsibility remains with the calling code.

## 5. Distinguishing Owned Resources from Shared Dependencies

Not every dependency referenced by a prototype is owned by that prototype. Distinguish:

- **Instance-owned resources:** a file writer opened by the session itself, a dedicated socket, or a privately allocated native handle. The prototype is responsible for closing or releasing these.
- **Shared Spring-managed dependencies:** such as a singleton `DataSource`, shared client, or another injected service. The prototype must never arbitrarily close shared dependencies when finishing its work.
- **Resources borrowed from shared dependencies:** for example, a JDBC `Connection`, `Statement`, and `ResultSet`. Code that opens or receives resources per API contract must close them properly; closing a pooled JDBC `Connection` typically returns it to the pool rather than closing the `DataSource`.

Example:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("select id from orders")) {

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getLong("id"));
        }
    }
}
~~~

This snippet closes `ResultSet`, `PreparedStatement`, and `Connection` after use. It does not call `dataSource.close()`, because `DataSource` is an injected dependency that may be used by many components across the application.

The rule to follow is: whichever component takes ownership of a resource must execute or explicitly transfer the responsibility to release it. Never arbitrarily close shared objects just because a prototype finished its task.

## 6. Organizing Cleanup When Multiple Places Use a Prototype

If multiple services use a resource-holding prototype, every call site should follow the same closing contract. You can place instance acquisition and release behind a factory method or a session runner component to avoid repeating the boilerplate.

For example, a method that allocates and uses a session can keep both operations within one scope:

~~~java
@Component
public class ExportSessionRunner {

    private final ObjectProvider<ExportSession> sessions;

    public ExportSessionRunner(ObjectProvider<ExportSession> sessions) {
        this.sessions = sessions;
    }

    public void run(ExportWork work) throws IOException {
        try (ExportSession session = sessions.getObject()) {
            work.execute(session);
        }
    }
}
~~~

Where `ExportWork` is an application-defined processing contract:

~~~java
@FunctionalInterface
public interface ExportWork {
    void execute(ExportSession session) throws IOException;
}
~~~

Components calling `ExportSessionRunner` supply only the work to execute. The runner handles creating, executing, and closing the session whether the work succeeds or fails.

If a prototype is returned out of a call scope for longer-term use, the returning API must clearly specify whether the receiver is responsible for calling `close()` or whether another component retains ownership. Avoid creating resource-holding instances and discarding references without a defined cleanup point.

## 7. Common Resource Management Mistakes

### Only Declaring @PreDestroy and Waiting for Spring to Call It

For prototypes, Spring does not automatically invoke destruction callbacks. Resources can remain open after the task finishes. Put release logic into an explicit method such as `close()` and call it at the owner's site.

### Assuming Closing ApplicationContext Closes Every Prototype

Closing the context triggers destruction of beans whose destruction lifecycle is container-managed, such as singletons. Prototypes already handed off to calling code are not automatically reclaimed that way.

### Retrieving Prototypes Without Keeping a Cleanup Point

Each call to `getBean()` or `ObjectProvider.getObject()` can create a new instance. If instances open files or connections, repeatedly obtaining them without closing increases held resources. Pair acquisition and closing within the same scope via try-with-resources whenever possible.

### Closing Shared Dependencies

A prototype can receive singleton dependencies via its constructor. Closing those dependencies inside the prototype's `close()` can break other components using the same objects. Release only resources owned by the instance; follow API contracts for borrowed resources.

### Assuming the Garbage Collector Replaces Resource Closing

The garbage collector reclaims memory once an object is unreferenced and eligible for collection. That does not guarantee files, sockets, connections, or OS locks are released promptly. Do not treat dropping object references as a cleanup strategy.

## 8. How to Determine Cleanup Responsibility

When designing a prototype bean, answer these questions:

1. Does the instance open or own resources outside heap memory?
2. Which API releases those resources: `close()`, `release()`, `disconnect()`, or a specialized operation?
3. Which component fetches the instance from the container and is responsible for using it?
4. Can usage of the instance be bounded inside a try-with-resources block?
5. If the instance is passed to another component, where is the ownership and cleanup handoff contract specified?
6. Which dependencies are private resources, and which are shared container-managed objects?

Prototype fits objects that need a fresh instance on demand, yet this scope does not mean Spring manages the entire resource lifecycle. The container creates and initializes the prototype; the code receiving the instance manages its usage duration and releases the resources it owns. When ownership boundaries are expressed with `AutoCloseable`, try-with-resources, and well-timed instance retrieval, the application avoids holding files, sockets, or connections longer than necessary.
