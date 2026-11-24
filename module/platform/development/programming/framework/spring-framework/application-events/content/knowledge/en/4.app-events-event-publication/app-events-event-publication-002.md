# Injecting ApplicationEventPublisher into a Bean

## 1. Why Inject ApplicationEventPublisher?

`ApplicationEventPublisher` is an interface provided by Spring for a component to publish notifications about an event that has occurred. A service can call `publishEvent(event)` without needing to know which listeners will receive it or how those listeners are implemented.

In a Spring application, `ApplicationContext` implements `ApplicationEventPublisher`. Therefore, Spring can supply the current context's publisher to a bean through dependency injection. You only need to declare `ApplicationEventPublisher` as a bean dependency; there is no need to look up a global `ApplicationContext` manually or call listeners directly.

For example, `RegistrationService` needs to publish `UserRegistered` after creating an account. The service receives the publisher via its constructor and calls `publisher.publishEvent(new UserRegistered(...))`. Registered listeners in the context are then notified by Spring through the Application Events mechanism.

## 2. Constructor Injection

Constructor injection is the preferred approach when a bean needs the publisher throughout its active lifecycle:

```java
public class RegistrationService {
    private final ApplicationEventPublisher publisher;

    public RegistrationService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void register(String userId) {
        publisher.publishEvent(new UserRegistered(userId));
    }
}
```

The dependency is explicitly declared in the constructor and stored in a `final` field. When creating `RegistrationService`, Spring must supply an object compatible with `ApplicationEventPublisher`. If the class has only one constructor, Spring automatically uses that constructor to inject the dependency; adding `@Autowired` is unnecessary in standard cases.

Constructor injection ensures the bean cannot be created in a state missing the publisher. It also makes unit tests straightforward by allowing a fake or test publisher to be passed when needed.

## 3. Declaring Beans and Letting Spring Supply the Publisher

With Java configuration, you can accept `ApplicationEventPublisher` as a parameter of a `@Bean` method and pass it into the service's constructor:

```java
@Configuration
public class AppConfig {

    @Bean
    RegistrationService registrationService(ApplicationEventPublisher publisher) {
        return new RegistrationService(publisher);
    }

    @Bean
    UserRegisteredListener userRegisteredListener() {
        return new UserRegisteredListener();
    }
}
```

Spring resolves the `publisher` parameter by dependency type and supplies the publisher bound to the `ApplicationContext` creating the bean. `RegistrationService` does not need to know the concrete implementation of the context.

In an application using component scanning, the equivalent declaration is annotating the service with `@Service` and declaring the constructor:

```java
@Service
public class RegistrationService {
    private final ApplicationEventPublisher publisher;

    public RegistrationService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
```

The listener must also be a Spring-managed bean, for example using `@Component` and `@EventListener`. Injecting the publisher into the service alone does not automatically create listeners; both sides must be registered in the appropriate `ApplicationContext`.

## 4. Complete Runnable Example with Java 17

The following example uses plain Spring Context to clearly show the publisher being injected into a service by Spring. When the service publishes an event, the listener receives the payload and prints a message.

### Directory Structure

```text
publisher-injection/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>publisher-injection</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.0</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/App.java

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class App {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(RegistrationService.class).register("user-46");
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        RegistrationService registrationService(ApplicationEventPublisher publisher) {
            return new RegistrationService(publisher);
        }

        @Bean
        UserRegisteredListener userRegisteredListener() {
            return new UserRegisteredListener();
        }
    }

    static class RegistrationService {
        private final ApplicationEventPublisher publisher;

        RegistrationService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void register(String userId) {
            publisher.publishEvent(new UserRegistered(userId));
            System.out.println("Registration completed for user=" + userId);
        }
    }

    static class UserRegisteredListener {

        @EventListener
        public void welcome(UserRegistered event) {
            System.out.println("Welcome event received for user=" + event.userId());
        }
    }

    public record UserRegistered(String userId) {
    }
}
```

### Running the Program

From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java
```

Output:

```text
Welcome event received for user=user-46
Registration completed for user=user-46
```

The listener prints its message before the `Registration completed` line because the default configuration processes events synchronously. When `publishEvent` returns, the synchronous listener has already completed.

In the example:

- `ApplicationEventPublisher` is passed by Spring into the `registrationService` `@Bean` method.
- The factory method passes the publisher into `RegistrationService`'s constructor.
- The service depends only on the publisher interface and publishes a `UserRegistered` payload.
- `UserRegisteredListener` is a bean in the same context and receives the payload via `@EventListener`.

## 5. Injecting the Publisher in Spring Boot

In a Spring Boot application, the usage is identical. You can use the constructor of a `@Service`:

```java
@Service
public class AccountService {
    private final ApplicationEventPublisher publisher;

    public AccountService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void openAccount(String accountId) {
        // Save the account using a repository first or follow the appropriate business flow.
        publisher.publishEvent(new AccountOpened(accountId));
    }
}
```

Spring Boot creates and manages the `ApplicationContext`, so the publisher is resolved automatically. You do not need to declare a separate `ApplicationEventPublisher` bean in standard configurations.

## 6. Other Injection Approaches and Choosing the Right One

Spring also supports field injection and setter injection, though constructor injection is usually clearer:

```java
// Field injection
@Autowired
private ApplicationEventPublisher publisher;

// Setter injection
@Autowired
public void setPublisher(ApplicationEventPublisher publisher) {
    this.publisher = publisher;
}
```

Field injection hides dependencies inside the class body and makes instantiating the class in plain unit tests harder. Setter injection is better suited when a dependency is genuinely optional or needs to change after bean creation. The publisher is typically a mandatory dependency for an event-publishing service, making constructor injection the easiest option to control.

Do not inject `ApplicationContext` solely to call `publishEvent` if the bean only needs event-publishing functionality. Declaring the `ApplicationEventPublisher` interface accurately expresses the requirement and reduces coupling to the broader context API.

Spring also provides `ApplicationEventPublisherAware` for beans that want to receive the publisher via a container callback. This mechanism is useful in certain infrastructure components that need Aware callbacks, but regular business services should use constructor injection so the dependency is immediately visible at bean instantiation.

## 7. Scope and Processing Timing

The injected publisher is bound to the context managing the bean. Events are dispatched through Spring's Application Events mechanism within the application/context scope and delivered to compatible listeners. When there is a parent/child context relationship, you must understand how events propagate between contexts; do not assume every independent context shares all listeners.

Injecting `ApplicationEventPublisher` does not make events automatically asynchronous, does not create a durable queue, and does not guarantee listeners run after a transaction commits. By default, synchronous listeners run on the thread publishing the event. If you want a listener to run asynchronously, you can use `@Async` with `@EnableAsync` and configure an executor.

If a listener should only run after a transaction commits, look into `@TransactionalEventListener` and phases such as `AFTER_COMMIT`. This requirement relates to the transaction lifecycle; injecting the publisher itself does not alter commit timing.

## 8. Common Errors

| Symptom | Cause and Resolution |
|---|---|
| Spring cannot inject the publisher | The bean was created outside the container or the context was not initialized properly. Let Spring create the bean via component scanning or `@Bean`. |
| Constructor reports a missing dependency | Check the bean creation configuration and parameter types. For Spring-managed beans, `ApplicationEventPublisher` is provided by the context. |
| Manually calling `new RegistrationService(...)` and expecting dependencies | Objects instantiated with `new` outside the container are not injected by Spring. Obtain the bean from the context or let the container manage its full lifecycle. |
| Listener does not receive the event | Verify the listener is a bean, has `@EventListener`, belongs to the appropriate context, and accepts a compatible payload type. |
| Assuming the publisher runs in the background by default | Events are processed synchronously by default. Use `@Async` if executor-based execution is needed and error handling is prepared. |
| Injecting the entire `ApplicationContext` just to publish events | Use `ApplicationEventPublisher` to depend only on the required interface. |

## 9. Key Takeaways

- `ApplicationContext` provides `ApplicationEventPublisher` functionality to beans within the context.
- Declare `ApplicationEventPublisher` in the constructor or as a `@Bean` method parameter for Spring to inject the dependency.
- Services publish events with `publisher.publishEvent(event)` without needing to invoke listeners directly.
- Listeners must be Spring beans and register handling via `@EventListener` or an appropriate listener mechanism.
- Constructor injection keeps dependencies explicit, mandatory, and easy to test.
- Injecting the publisher does not by itself introduce asynchronous processing, a message broker, or transaction-after-commit behavior.