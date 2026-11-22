# Factory Method: Separating the Concrete Class Selection Decision

## 1. Problem and Idea

Factory Method is a creational design pattern belonging to the Creational group in GoF. This pattern defines an object-creation method in a base class and then lets subclasses decide which concrete product class will be instantiated. The stable business logic works only with the abstract type of the product.

Imagine a notification-sending service. The sending workflow may be the same for email and SMS, but the way the sender object is created differs. If the business class directly calls `new EmailNotification()` or scatters `if/else` statements to select among multiple concrete classes, every time a new channel is added, existing classes may have to be modified.

Factory Method places the point of variation into a method that can be overridden:

1. The base class declares the product creation method and uses it in the common workflow.
2. Each concrete subclass overrides the creation method to return an appropriate product.
3. The calling code selects a concrete service class, but the sending workflow only knows the `Notification` interface.

## 2. Roles in the GoF Pattern

| Role | Responsibility | In the Example |
| --- | --- | --- |
| Product | Common contract for the created product | `Notification` |
| Concrete Product | Implements a product type | `EmailNotification`, `SmsNotification` |
| Creator | Declares the Factory Method and contains the workflow that uses the product | `NotificationService` |
| Concrete Creator | Overrides the Factory Method to choose the product type | `EmailNotificationService`, `SmsNotificationService` |
| Client | Chooses the appropriate creator and invokes the business logic through the abstract type | `Main` |

The key relationship is that `NotificationService` does not need to know the concrete class name of the product. It calls `createNotification()` and works with the returned value through the `Notification` type.

## 3. Complete Java 17 Example

The example below creates two services that share the same sending workflow but create two different types of notifications. All classes are in a single file so it can be compiled directly.

Save as `Main.java`:

```java
import java.util.Objects;

public class Main {
    public static void main(String[] args) {
        NotificationService email = new EmailNotificationService();
        email.notifyUser("alice@example.com", "Your report is ready.");

        NotificationService sms = new SmsNotificationService();
        sms.notifyUser("+84901234567", "Your report is ready.");
    }
}

interface Notification {
    void send(String recipient, String message);
}

final class EmailNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.println("EMAIL -> " + recipient + ": " + message);
    }
}

final class SmsNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS -> " + recipient + ": " + message);
    }
}

abstract class NotificationService {
    public final void notifyUser(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");

        Notification notification = createNotification();
        notification.send(recipient, message);
    }

    protected abstract Notification createNotification();
}

final class EmailNotificationService extends NotificationService {
    @Override
    protected Notification createNotification() {
        return new EmailNotification();
    }
}

final class SmsNotificationService extends NotificationService {
    @Override
    protected Notification createNotification() {
        return new SmsNotification();
    }
}
```

Compile and run with JDK 17 or higher:

```text
javac --release 17 Main.java
java Main
```

Exact stdout:

```text
EMAIL -> alice@example.com: Your report is ready.
SMS -> +84901234567: Your report is ready.
```

## 4. How the Program Works

When `email.notifyUser(...)` is called, Java executes the `notifyUser` method defined in `NotificationService`. This method calls `createNotification()`. Because the actual object is an `EmailNotificationService`, dynamic dispatch runs that class's override and creates an `EmailNotification`. The product is then used through the `Notification` interface.

When `sms.notifyUser(...)` is called, the same workflow in the base class is preserved, but the override in `SmsNotificationService` creates an `SmsNotification`. The base class does not need an `if/else` branch to distinguish between email and SMS.

`notifyUser` represents the common workflow; `createNotification` is the extension point. If you want to add a push notification channel, you can create `PushNotification` and `PushNotificationService` without modifying the sending workflow in `NotificationService`.

In real-world applications, the creator class is usually chosen at the application startup point or through dependency injection configuration. Factory Method handles how the product is created inside the creator; deciding which creator to use still belongs where the application is configured.

## 5. How Does Factory Method Differ from Other Ways of Creating Objects?

### Calling the Constructor Directly

```java
Notification notification = new EmailNotification();
```

This approach is clear and completely reasonable if the product type is fixed. However, the calling class depends directly on `EmailNotification`; if multiple product types need to be selected based on the environment or business logic, object-creation sites can become scattered.

### Simple Factory or Static Factory Method

A Simple Factory typically takes a parameter such as `"email"` or `"sms"` and uses a conditional to return a product. This centralizes class-selection logic in one place, but the factory usually has to be modified whenever a new product type is added. It is not the GoF Factory Method pattern in the strict sense, because it does not rely on subclasses overriding a creation method.

The Java term `static factory method` also has a broader meaning: a static method such as `List.of(...)` that creates or provides objects. It is not automatically the GoF Factory Method pattern.

### Factory Method

Factory Method uses polymorphism: subclasses decide the product type by overriding a creation method. This pattern fits when there is a common workflow but multiple product variants need to be selected through different creators.

### Abstract Factory

Abstract Factory provides an interface for creating a family of related products, often consisting of multiple product types that must be compatible with each other. Factory Method usually focuses on a single product-creation point within a creator; Abstract Factory is useful when multiple creation methods within the same family need to be coordinated.

### Builder

Builder separates the construction of a complex object into multiple steps, typically to configure many optional fields or to represent different ways of constructing it. Factory Method primarily decouples the concrete product class selection decision.

## 6. When to Use It?

Factory Method is appropriate when:

- A class has a stable workflow but requires multiple product variants.
- Calling code should depend on the product's interface or abstract class rather than a concrete class.
- A framework needs to provide a default workflow and allow subclasses to extend how objects are created.
- Products need to be swapped in tests, for example with a test creator returning a fake or stub that implements the same interface.
- Subclasses have clear responsibilities: each creator represents a meaningful product choice.

Real-world examples may include format-specific file readers, report exporters, parsers, storage providers, or notification services. It should only be applied when there is a genuine point of variation; there is no need to create a creator hierarchy for every simple `new` call.

## 7. Benefits and Costs

**Benefits**

- Decouples business logic from concrete product class names.
- Keeps the common workflow in one place, avoiding duplicating the workflow for each product type.
- Extends by adding new creators and products when the design allows, rather than modifying product-creation logic in the base class.
- Supports testing because business code uses a common contract.
- Creates an intentional extension point for libraries or frameworks.

**Costs**

- Increases the number of classes and level of indirection; with a single product, the design can become heavy.
- Users still need to know or configure the concrete creator at the initialization point.
- If all variants are put into a single creator class with many conditionals, the benefits of polymorphism can disappear.
- The pattern does not by itself provide lifecycle management, caching, thread safety, connection pooling, or dependency injection; those requirements must be designed separately.

## 8. Common Design Mistakes

1. **Returning a concrete class from the common workflow.** If `notifyUser` depends on `EmailNotification`, adding a new product still forces modifications to the base class. You should return and use the `Notification` type.
2. **Putting all product-selection conditionals inside the base creator.** A large `switch` in `createNotification` may just be a Simple Factory. If the goal is the GoF Factory Method, let child creators override the creation method.
3. **Confusing Factory Method with any method named `create...`.** The method name does not determine the design pattern; its role in the creator, product, and override relationship is what matters.
4. **Creating subclasses with no real variation.** If the creators all create the same product and there is no reason to extend, you can use a direct constructor or a simple factory.
5. **Letting the client check the product type after creation.** If calling code repeatedly has to use `instanceof` to decide how to use it, the Product contract may not yet express enough of the required behavior.
6. **Forgetting to handle dependencies when creating products.** If a product needs a gateway, configuration, or logger, pass those dependencies through a constructor or an appropriate injection mechanism. Shared resources should not be hidden in global variables.
7. **Assuming the pattern always eliminates all changes.** When adding a product type, you usually still need to add a Concrete Product, a Concrete Creator, and configure the creator at the application startup site. The pattern reduces the scope of change and coupling rather than making new changes disappear.

## 9. Step-by-Step Implementation

1. Identify the stable business logic that needs to use the product, such as `notifyUser`.
2. Define the Product interface with the behaviors that the workflow needs to invoke.
3. Create the Concrete Products that implement that interface.
4. Create the Creator containing the common workflow and declare the Factory Method returning Product.
5. Create Concrete Creators that override the Factory Method to return the desired product type.
6. Select the creator at the composition root or through application configuration.
7. Test each creator and the common workflow; verify that adding a new product does not require modifying code that uses the Product abstraction.

## 10. Design Review Checklist

- Are there multiple product types that genuinely need to be created in different ways?
- Can the workflow that uses the product stay the same across types?
- Does the Product interface express enough of the behavior required by the common workflow?
- Is the Factory Method overridden by Concrete Creators, and does it return an abstract type?
- Is the creator selection point clear in the application configuration?
- Is the cost of the additional classes worth the extensibility and testability benefits?
- Is Abstract Factory needed because an entire family of products must be created, or Builder because the construction process has many steps?

Factory Method is most useful when it isolates a changing product-creation decision while keeping the business workflow stable and dependent on a shared contract.
