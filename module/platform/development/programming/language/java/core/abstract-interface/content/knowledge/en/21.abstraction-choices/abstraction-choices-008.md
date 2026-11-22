# Dependency Inversion via Parameters or Constructors in Java

The Dependency Inversion Principle (DIP) is one of the five SOLID principles. The main idea is that **high-level business code should depend on an abstraction (an interface or abstract class), while low-level details also implement or depend on that abstraction**. As a result, business logic is not locked into a specific way of sending notifications, storing data, or calling a service.

In Java, a dependency can be passed into an object via a constructor or passed into a method via a parameter. These are forms of dependency injection (DI). They help apply DIP, but passing parameters alone is not enough to guarantee that the architecture adheres to DIP: parameter types and dependency directions still need to be designed properly.

## 1. The Problem with Depending Directly on a Concrete Class

Suppose an alert service must send notifications via email:

~~~java
final class AlertService {
    private final EmailChannel email = new EmailChannel();

    void alert(String recipient, String message) {
        email.send(recipient, message);
    }
}
~~~

The `AlertService` class creates `EmailChannel` itself. It decides both when to send an alert and which delivery mechanism to use. If you want to send SMS, use a different provider, or test without sending real emails, you have to modify or replace how the dependency is created inside the service.

The problem is not that `EmailChannel` is a class. The problem is that high-level logic is tightly coupled to an implementation detail. A small abstraction allows the service to know only that it can send notifications, without needing to know the specific way of sending them.

## 2. Separating the Contract with an Interface

Define an interface that describes the capability the business logic needs:

~~~java
interface NotificationChannel {
    void send(String recipient, String message);
}
~~~

Different delivery mechanisms implement the same contract:

~~~java
final class EmailChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("EMAIL to " + recipient + ": " + message);
    }
}

final class SmsChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}
~~~

Now `AlertService` can depend on `NotificationChannel`. `EmailChannel` and `SmsChannel` are concrete details that both implement the abstraction. When adding another channel, such as push notification, you only need to implement the interface if the current contract meets the needs.

## 3. Injecting Dependencies via a Constructor

Constructor injection passes the dependency in at object creation time. This is usually the right choice when the dependency is required and needs to remain stable throughout the object's lifecycle.

~~~java
import java.util.Objects;

final class AlertService {
    private final NotificationChannel channel;

    AlertService(NotificationChannel channel) {
        this.channel = Objects.requireNonNull(channel, "channel must not be null");
    }

    void alert(String recipient, String message) {
        channel.send(recipient, message);
    }
}
~~~

Key points:

- The `channel` field is declared using the interface, not `EmailChannel` or `SmsChannel`.
- The constructor receives the dependency from the outside. `AlertService` does not call `new EmailChannel()` itself.
- The `final` field prevents the dependency from being replaced after the object is initialized.
- `Objects.requireNonNull` exposes configuration errors immediately upon object creation, instead of letting them occur later when sending a notification.

The application's initialization code decides which implementation is used:

~~~java
AlertService emailAlerts = new AlertService(new EmailChannel());
AlertService smsAlerts = new AlertService(new SmsChannel());
~~~

The same business class can be configured with two different implementations. When you want to change the default channel, the initialization configuration changes the way the dependency is passed; the logic inside `AlertService` remains unchanged.

## 4. Injecting Dependencies via a Method Parameter

Sometimes a dependency is only needed for a single operation, or each call needs a different implementation. In that case, you can pass the abstraction via a parameter:

~~~java
final class NotificationWorkflow {
    static void sendOnce(
            NotificationChannel channel,
            String recipient,
            String message) {
        Objects.requireNonNull(channel, "channel must not be null")
               .send(recipient, message);
    }
}
~~~

Usage example:

~~~java
NotificationWorkflow.sendOnce(
        new EmailChannel(), "ops@example.com", "Daily report ready");
NotificationWorkflow.sendOnce(
        new SmsChannel(), "+84901234567", "Deployment started");
~~~

The method only requires a `NotificationChannel`; it does not need to know the concrete implementation. The caller chooses the appropriate dependency for each execution. Because the example uses `Objects.requireNonNull`, the complete file in the next section imports `java.util.Objects`.

Constructor injection and parameter injection address two different needs:

| Injection approach | Suitable when | Characteristics |
|---|---|---|
| Constructor | The dependency is required for most of the object's behavior | Available after initialization; easy to keep immutable and easy to see the required dependencies |
| Method parameter | The dependency is only needed for a single operation or varies per call | Narrow scope of use; the caller chooses the implementation on each call |
| Setter | The dependency is truly optional or can be reconfigured after creation | The object can exist in an unconfigured state; validity must be managed carefully |

You should not choose parameter injection just because it seems more flexible. If every operation of a service needs the same required dependency, a constructor usually expresses the intent more clearly. Conversely, if each call needs its own strategy, passing it via a parameter may be more natural.

## 5. Complete Runnable Example on Java 17

Save the code below to the file `DependencyInversionDemo.java`. The example demonstrates constructor injection and parameter injection in a standalone program.

~~~java
import java.util.Objects;

public class DependencyInversionDemo {
    public static void main(String[] args) {
        AlertService emailAlerts = new AlertService(new EmailChannel());
        emailAlerts.alert("linh@example.com", "Build succeeded");

        AlertService smsAlerts = new AlertService(new SmsChannel());
        smsAlerts.alert("+84901234567", "Deployment started");

        NotificationWorkflow.sendOnce(
                new EmailChannel(), "ops@example.com", "Daily report ready");
    }
}

interface NotificationChannel {
    void send(String recipient, String message);
}

final class EmailChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("EMAIL to " + recipient + ": " + message);
    }
}

final class SmsChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}

final class AlertService {
    private final NotificationChannel channel;

    AlertService(NotificationChannel channel) {
        this.channel = Objects.requireNonNull(
                channel, "channel must not be null");
    }

    void alert(String recipient, String message) {
        channel.send(recipient, message);
    }
}

final class NotificationWorkflow {
    static void sendOnce(
            NotificationChannel channel,
            String recipient,
            String message) {
        Objects.requireNonNull(channel, "channel must not be null")
               .send(recipient, message);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 DependencyInversionDemo.java
java DependencyInversionDemo
~~~

Exact stdout:

~~~text
EMAIL to linh@example.com: Build succeeded
SMS to +84901234567: Deployment started
EMAIL to ops@example.com: Daily report ready
~~~

None of the auxiliary types are declared `public`, so they can reside in the same file as the `public` class `DependencyInversionDemo`. The compilation command above targets Java 17 and does not require a DI framework.

## 6. Why Is This Dependency Inversion?

There are two dependency directions to observe:

- **Before separating the abstraction:** `AlertService` knows about and creates `EmailChannel` itself. Changing email-sending details may force changes to the business class.
- **After separating the abstraction:** `AlertService` only references `NotificationChannel`. `EmailChannel` and `SmsChannel` implement the interface; the external initialization code connects an implementation to the service.

Relationship diagram after the redesign (arrows represent source-code dependencies or operations at the initialization site):

~~~text
AlertService --------- uses -----------> NotificationChannel
                                            ^              ^
                                            | implements   | implements
                                       EmailChannel     SmsChannel

CompositionRoot --- creates ----> EmailChannel or SmsChannel
CompositionRoot --- passes -----> new AlertService(channel)
~~~

`AlertService` only knows the `NotificationChannel` type. The two concrete channels implement that contract, while `CompositionRoot` is the code in `main` that decides which channel to create and passes it into the constructor. The source-code dependency direction is not inverted incorrectly: `AlertService` itself depends on the interface, and the implementations also depend on the same interface.

DIP is an architectural principle about dependency direction. DI is a technique for supplying an object that a class needs to use. Constructor or parameter injection can support DIP when the dependency is declared through an abstraction. If a constructor accepts `EmailChannel` directly, even though the dependency is passed in from the outside, the class is still coupled to the email detail.

## 7. Easier Testing When Dependencies Are Injected

You can pass in a fake implementation or a mock to test the logic without making network calls, sending real emails, or depending on an external provider. A simple fake example:

~~~java
final class RecordingChannel implements NotificationChannel {
    String lastRecipient;
    String lastMessage;

    @Override
    public void send(String recipient, String message) {
        lastRecipient = recipient;
        lastMessage = message;
    }
}
~~~

In a test, you create a `RecordingChannel`, pass it into `AlertService`, call `alert`, and then verify `lastRecipient` and `lastMessage`. Because the fake implements the same interface, the business class needs no special branch dedicated to the test environment.

This is a major benefit of depending on an abstraction: external behavior can be substituted in tests, while business logic is tested in a controlled way.

## 8. Common Design Mistakes

**Creating concrete classes directly inside the service.** If `AlertService` still calls `new EmailChannel()`, adding a constructor that accepts an interface does not completely resolve the coupling if the dependency is ignored or overwritten by an internally created object.

**Passing a concrete class instead of an abstraction.** A parameter `EmailChannel channel` restricts callers to a single implementation. If the business logic needs multiple channel types, it should accept `NotificationChannel`.

**Confusing DI with DIP.** Receiving a dependency through a constructor is not enough. If the dependency's type is a concrete implementation class, or the high-level module still depends on low-level details, the dependency inversion principle is not yet fully realized.

**Using a setter for a required dependency.** An object can be created and called before the setter configures the dependency. For a dependency needed for the object to operate validly, a constructor is usually safer.

**Allowing a null dependency.** If null is not a valid state, check for it immediately where the dependency is received. A consistent nullability contract should be established instead of letting errors happen deep inside the processing.

**Creating abstractions with no value.** You do not need to add an interface for every class just to follow a pattern. An abstraction is useful when it expresses a stable contract, separates business policy from implementation details, or enables meaningful substitution/testing.

**Scattering implementation selection everywhere.** If multiple business classes decide on their own using `new EmailChannel()` or `new SmsChannel()`, coupling still spreads. Centralize object creation and wiring where the application is configured, often called the composition root.

## 9. Do You Need a Dependency Injection Framework?

No. Java supports passing objects directly via constructors and method parameters; the example above uses no external libraries.

In large applications, a DI framework can automatically create dependencies, manage lifecycles, and wire components together based on configuration. A framework changes how objects are created and assembled, but it does not replace designing the right abstractions. A class that directly accepts a concrete implementation class still has that coupling even if it is instantiated by a framework.

## 10. Adoption Checklist

- Identify what capability the high-level business logic needs, then represent that capability with an appropriate interface or abstraction.
- Let concrete classes implement the contract and hold the execution details.
- Use a constructor for dependencies that are required and stable over the object's lifecycle.
- Use a method parameter when the dependency is only needed for a single operation or the choice varies per call.
- Create and wire implementations where the application is initialized, rather than scattering `new ConcreteClass()` throughout business logic.
- Check nullability, ownership, and the lifecycle of the dependency according to the application's contract.
- Write tests using fakes or mocks to verify behavior without calling external systems.
- Check whether swapping an implementation forces you to modify the business class; if so, re-examine the dependency direction.

Abstraction-oriented design keeps business code stable in the face of changes to technical details. Constructor injection makes required dependencies explicit; parameter injection lets an operation use an implementation chosen by the caller. Both are useful when used within the right scope and combined with a well-designed abstraction contract.
