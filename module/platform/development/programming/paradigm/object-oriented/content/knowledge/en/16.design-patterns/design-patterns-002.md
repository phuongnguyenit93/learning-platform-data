# Factory Method and Abstract Factory in Java

> **Category:** Design Patterns → *Creational patterns* (patterns for object creation).  
> **Goal:** Understand why object creation should be separated from consuming code, implement the correct **Factory Method** and **Abstract Factory** structures, recognize their differences, choose based on the problem, and avoid confusing them with ordinary object-creation functions.

## 1. The Shared Problem: Business Code Is Coupled to Object Creation

Consider an application that sends notifications by email or SMS. If the business class chooses the implementation itself:

~~~java
void notifyCustomer(String channel, String customerId, String message) {
    if ("email".equals(channel)) {
        new EmailSender().send(customerId, message);
    } else if ("sms".equals(channel)) {
        new SmsSender().send(customerId, message);
    } else {
        throw new IllegalArgumentException("Unsupported channel");
    }
}
~~~

Adding a new channel requires modifying an `if/else` branch at the call site. Object-creation code is mixed with notification orchestration. If multiple places choose channels, the conditionals are easily duplicated.

Both patterns below use **abstraction** to reduce coupling, but they focus on different concerns:

- **Factory Method** lets a **base class define an extension point for product creation**, while subclasses decide which product type to instantiate.
- **Abstract Factory** lets clients use **a factory object** to create **a family of related products** without knowing the family's concrete classes.

Do not rush to introduce a factory when you only have one simple `new` with little chance of change. A factory becomes useful when object creation is an **intentional variation point**.

## 2. Factory Method — Deferring Product Creation to Subclasses

**GoF definition:** Define an interface for creating an object, but let subclasses decide which class to instantiate. Factory Method lets a class defer instantiation of concrete products to subclasses.

Typical roles:

| Role | Responsibility | Example |
|---|---|---|
| **Product** | Contract of the created object | `Sender` |
| **Concrete Product** | Implementations of Product | `EmailSender`, `SmsSender` |
| **Creator** | Contains the common processing flow and declares the factory method | `NotificationCampaign` |
| **Concrete Creator** | Overrides the factory method to return a concrete product | `EmailCampaign`, `SmsCampaign` |

Key point: **a Creator is not necessarily just a “factory class”**. It often implements real processing logic and calls the factory method to obtain an appropriate collaborator. In the example below, `notifyCustomer` is the shared flow; `createSender` is the factory method.

### 2.1. Standalone Java Example: Creating a Notification Channel

Create `FactoryMethodDemo.java`. The code runs on Java 17+ without contacting real email or SMS services.

~~~java
import java.util.List;
import java.util.Objects;

// Product: client chỉ cần thao tác trên hợp đồng này.
interface Sender {
    void send(String customerId, String message);
}

// Concrete products: các adapter mô phỏng để dễ chạy demo.
final class EmailSender implements Sender {
    @Override
    public void send(String customerId, String message) {
        System.out.printf("[EMAIL] %s: %s%n", customerId, message);
    }
}

final class SmsSender implements Sender {
    @Override
    public void send(String customerId, String message) {
        System.out.printf("[SMS] %s: %s%n", customerId, message);
    }
}

// Creator: thuật toán chung, đồng thời công bố factory method.
abstract class NotificationCampaign {
    public final void notifyCustomer(String customerId, String message) {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(message, "message");

        if (customerId.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException("Blank customer/message");
        }

        // Không cần biết Sender cụ thể là email hay SMS.
        Sender sender = Objects.requireNonNull(
                createSender(), "createSender returned null");
        sender.send(customerId, message);
    }

    protected abstract Sender createSender(); // Factory Method
}

// Concrete creators: lựa chọn sản phẩm bằng polymorphism.
final class EmailCampaign extends NotificationCampaign {
    @Override
    protected Sender createSender() {
        return new EmailSender();
    }
}

final class SmsCampaign extends NotificationCampaign {
    @Override
    protected Sender createSender() {
        return new SmsSender();
    }
}

public class FactoryMethodDemo {
    public static void main(String[] args) {
        List<NotificationCampaign> campaigns = List.of(
                new EmailCampaign(),
                new SmsCampaign()
        );

        for (NotificationCampaign campaign : campaigns) {
            campaign.notifyCustomer("CUST-42", "Don hang da xac nhan");
        }
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac FactoryMethodDemo.java
java FactoryMethodDemo
~~~

Output:

~~~text
[EMAIL] CUST-42: Don hang da xac nhan
[SMS] CUST-42: Don hang da xac nhan
~~~

**What happens:**

1. The client chooses `EmailCampaign` or `SmsCampaign` at the assembly point (for example, in `main`).
2. The client calls the **same API**, `notifyCustomer(customerId, message)`.
3. The Creator validates the input and calls `createSender()`.
4. The method is dynamically dispatched to the subclass; the subclass creates an `EmailSender` or `SmsSender`.
5. The common processing flow does not require `if (sender instanceof EmailSender)` or modification when another Concrete Creator is added.

In a real system, `EmailSender` might call an email provider while `SmsSender` calls an SMS gateway. Here `customerId` is a general identifier, not an email address or phone number; real adapters would need contact-information lookup and appropriate error-handling rules.

### 2.2. Relationship Diagram

~~~mermaid
classDiagram
    class Sender {
        <<interface>>
        +send(customerId, message) void
    }
    class EmailSender {
        +send(customerId, message) void
    }
    class SmsSender {
        +send(customerId, message) void
    }
    class NotificationCampaign {
        <<abstract>>
        +notifyCustomer(customerId, message) void
        #createSender() Sender
    }
    class EmailCampaign {
        #createSender() Sender
    }
    class SmsCampaign {
        #createSender() Sender
    }

    Sender <|.. EmailSender
    Sender <|.. SmsSender
    NotificationCampaign <|-- EmailCampaign
    NotificationCampaign <|-- SmsCampaign
    NotificationCampaign ..> Sender : sử dụng
    EmailCampaign ..> EmailSender : tạo
    SmsCampaign ..> SmsSender : tạo
~~~

This is the **GoF Factory Method structure**, because **a subclass overrides a product-creation method declared by the Creator**. It is not simply a function with “factory” in its name.

### 2.3. When Should You Use It?

Factory Method is useful when the **Creator has a stable workflow** but the component created within that workflow varies by Creator type: rendering reports with suitable renderers, creating message senders for campaigns, creating specialized parsers in a pipeline, or creating documents in an editor.

Trade-off: each variant may require a Concrete Creator, increasing the number of classes and the use of inheritance. If objects differ only by runtime configuration or the Creator has no genuine shared behavior, passing a factory or strategy through composition may be more concise.

## 3. Abstract Factory — Creating a Consistent Product Family

**GoF definition:** Provide an interface for creating **families of related or dependent objects** without specifying their concrete classes.

Example: a desktop application supports **Light** and **Dark** interfaces. Each theme has multiple components: `Button` and `Checkbox`. Clients expect those components to be created **consistently within one theme**.

| Product family | Button | Checkbox |
|---|---|---|
| **Light** | `LightButton` | `LightCheckbox` |
| **Dark** | `DarkButton` | `DarkCheckbox` |

If clients instantiate each class separately throughout the code, they may accidentally mix `LightButton` with `DarkCheckbox`. Abstract Factory centralizes the choice of the entire family.

### 3.1. Standalone Java Example: Light/Dark UI

Create a **separate** file, `AbstractFactoryDemo.java`, and compile and run it independently of the Factory Method example.

~~~java
import java.util.Objects;

// Abstract products: hợp đồng của từng loại thành phần UI.
interface Button {
    String render();
}

interface Checkbox {
    String render();
}

// Abstract factory: danh sách sản phẩm mà MỌI họ cần cung cấp.
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// Họ Light: hai sản phẩm có cùng phong cách.
final class LightButton implements Button {
    @Override
    public String render() {
        return "Button[LIGHT]";
    }
}

final class LightCheckbox implements Checkbox {
    @Override
    public String render() {
        return "Checkbox[LIGHT]";
    }
}

final class LightUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox();
    }
}

// Họ Dark: cùng interface sản phẩm, implementation khác.
final class DarkButton implements Button {
    @Override
    public String render() {
        return "Button[DARK]";
    }
}

final class DarkCheckbox implements Checkbox {
    @Override
    public String render() {
        return "Checkbox[DARK]";
    }
}

final class DarkUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new DarkCheckbox();
    }
}

// Client chỉ biết các abstraction Button, Checkbox và UiFactory.
final class SettingsScreen {
    private final Button button;
    private final Checkbox checkbox;

    SettingsScreen(UiFactory factory) {
        Objects.requireNonNull(factory, "factory");

        // Tất cả thành phần được tạo qua CÙNG MỘT factory.
        this.button = Objects.requireNonNull(
                factory.createButton(), "button");
        this.checkbox = Objects.requireNonNull(
                factory.createCheckbox(), "checkbox");
    }

    void render() {
        System.out.println(button.render() + " | " + checkbox.render());
    }
}

public class AbstractFactoryDemo {
    public static void main(String[] args) {
        UiFactory light = new LightUiFactory();
        UiFactory dark = new DarkUiFactory();

        new SettingsScreen(light).render();
        new SettingsScreen(dark).render();
    }
}
~~~

Run:

~~~bash
javac AbstractFactoryDemo.java
java AbstractFactoryDemo
~~~

Output:

~~~text
Button[LIGHT] | Checkbox[LIGHT]
Button[DARK] | Checkbox[DARK]
~~~

`SettingsScreen` knows only the **Abstract Products** (`Button`, `Checkbox`) and the **Abstract Factory** (`UiFactory`). It neither instantiates nor imports `DarkButton` / `LightCheckbox`.

A concrete factory creates products from **the same family**; replacing `UiFactory` at the **composition root** switches the entire UI suite. If a concrete factory mixes products from different themes, that is an implementation/product-family contract error; the Java interface alone cannot enforce this consistency.

### 3.2. Abstract Factory Diagram

~~~mermaid
flowchart TD
    Client["SettingsScreen (client)"] --> Abstract["UiFactory"]
    Client --> BP["Button"]
    Client --> CP["Checkbox"]
    Light["LightUiFactory"] -.->|"implements"| Abstract
    Dark["DarkUiFactory"] -.->|"implements"| Abstract
    Light --> LB["LightButton"]
    Light --> LC["LightCheckbox"]
    Dark --> DB["DarkButton"]
    Dark --> DC["DarkCheckbox"]
    LB -.->|"implements"| BP
    DB -.->|"implements"| BP
    LC -.->|"implements"| CP
    DC -.->|"implements"| CP
~~~

The defining feature is **a factory with multiple methods that create different Product types**, such as `createButton()` and `createCheckbox()`. Each Concrete Factory implements all those methods to produce **one consistent variant**.

### 3.3. When Should You Use It?

- There are **multiple related product types** that must be selected together as a family: Light/Dark UI, AWS/Azure cloud connector suites (storage, queues, notifications), document-export components by format, or adapters for multiple providers in the same ecosystem.
- You need to switch product families at startup or when constructing a session, without making clients depend on concrete classes.
- You need to isolate the rules for constructing product suites and test compatibility among products in the same family.

**Important trade-off:** Adding a **new family** usually requires only a new Concrete Factory and its Concrete Products. But adding a **new product type** to the interface (such as `createSlider()`) may require changing every Concrete Factory. Abstract Factory fits when the set of product types is relatively stable but the number of families changes.

## 4. Side-by-Side Comparison

| Criterion | Factory Method | Abstract Factory |
|---|---|---|
| Core problem | Vary how **one Product type** is created within a Creator's algorithm | Create **a family of related Products** |
| Characteristic variation mechanism | **Inheritance + overriding** a factory method | **Composition**: pass a factory object to the client |
| Creation interface | `protected Sender createSender()` in the Creator | `UiFactory` exposes `createButton()` and `createCheckbox()` |
| Adding a variant | Add a Concrete Creator and corresponding Product | Add a Concrete Factory and the Products of the new family |
| Adding an entirely new product type | May require a new Creator abstraction/workflow | Usually requires extending the API and updating every concrete factory |
| Primary client | Uses the Creator (or invokes its shared operation) | Uses the Abstract Factory and Abstract Products |
| Example above | `EmailCampaign` selects `EmailSender` | `DarkUiFactory` creates both `DarkButton` + `DarkCheckbox` |
| Main concern | Many subclasses may exist just to choose a single product | Hard to extend by adding product types |

**The two patterns are not mutually exclusive.** A concrete Abstract Factory may internally use factory methods to create each product type. The distinction lies in **design intent and the client's usage structure**, not in method names.

## 5. Distinguishing Simple Factory and Static Factory Methods

Many resources call every function that returns an object a “Factory Method,” which creates confusion.

A **Simple Factory** is usually a class or function that selects an implementation centrally based on a parameter:

~~~java
enum Channel { EMAIL, SMS }

final class SenderFactory {
    static Sender create(Channel channel) {
        return switch (channel) {
            case EMAIL -> new EmailSender();
            case SMS -> new SmsSender();
        };
    }
}

// Client:
Sender sender = SenderFactory.create(Channel.EMAIL);
~~~

The snippet above assumes the `Sender`, `EmailSender`, and `SmsSender` classes from `FactoryMethodDemo.java` are reused (when placed in the same package). This is commonly called a **simple factory**: one function makes a selection based on an enum, with **no Creator subclass overriding a factory method**. Adding an enum value requires changing the `switch`; a simple factory may still be entirely appropriate for a small system.

A **Static factory method** is a `static` method that creates or returns an object, such as `List.of(...)` and `LocalDate.of(...)` in Java. It is an API-design technique and **does not imply** the GoF **Factory Method** pattern. Depending on its API contract, a static factory may return a new object, a cached object, or a hidden implementation.

The name does not determine the pattern. Ask **whether the variation point is in a subclass, in a factory object, or simply in an argument passed to the method**.

## 6. How Do Factories Differ from DI and Strategy?

**Dependency Injection (DI)** is the technique of **supplying an object's dependencies from outside**. With `new SettingsScreen(new DarkUiFactory())`, constructor injection supplies `UiFactory`; Abstract Factory is the kind of dependency being injected. DI itself is not automatically Factory Method or Abstract Factory.

**Strategy** encapsulates an **interchangeable algorithm/behavior**. A factory creates **objects**. They can work together: a factory creates or selects a `PricingStrategy`, while a service uses Strategy to calculate a price.

A practical rule:

- If the variation concerns **how an existing operation behaves**, consider Strategy first.
- If the variation concerns **which class is created within a shared process, as chosen by a subclass**, consider Factory Method.
- If you must create a **set of products in the same variant** (several related interfaces), consider Abstract Factory.
- If only one implementation needs to be selected at startup with few variants, constructor DI at the composition root may already suffice.

In Spring, `@Bean` and the DI container handle bean creation, wiring, and lifecycle, but **do not automatically** turn every `@Bean` into a GoF Factory Method/Abstract Factory. If the only requirement is configuring a `Sender`, direct injection may suffice; a separate factory class is not always needed.

## 7. Clean Factory Design in Real Applications

### 7.1. Separate Variant Selection from Client Code

Both examples have a **composition root**:

~~~java
// Factory Method:
NotificationCampaign campaign = new EmailCampaign();

// Abstract Factory:
UiFactory uiFactory = new DarkUiFactory();
SettingsScreen screen = new SettingsScreen(uiFactory);
~~~

With runtime configuration, variant selection may occur in `main`, a bootstrap module, or DI configuration. The main client should not scatter `new DarkButton()` or `if (factory instanceof DarkUiFactory)` throughout its logic.

Distinguish **changing configuration between startups** from **selecting variants per request**. If each HTTP request requires a different provider, a fixed singleton factory chosen at startup is insufficient; you may need a registry/selector that governs selection permissions, or to pass the appropriate factory with each request. This choice depends on the operating context; the pattern itself does not provide it.

### 7.2. Avoid Exposing Concrete Classes in the API Without Good Reason

If `UiFactory.createButton()` returns `DarkButton` and clients must cast to access special behavior, the goal of decoupling concrete products is weakened. A product interface should provide operations **that clients actually need**, without adding methods relevant to only one family.

Avoid an interface with dozens of methods where most implementations merely throw `UnsupportedOperationException`. Reconsider how interfaces are split, which capabilities are supported, or how capabilities are represented.

### 7.3. Specify Creation Time, Ownership, and Lifecycle

Both demos use `new`, so each factory-method call can create a new object. In production, expensive dependencies such as HTTP clients, connection pools, or SDKs may need reuse. A factory **may** return an existing, pooled, or new object, provided its contract permits that.

Specify clearly:
- Does the factory-produced object contain request-specific state?
- Is it safe to share across threads?
- Who is responsible for closing `AutoCloseable` instances and managing resource lifecycles?
- May the client mutate product state after creation?

Do not default to caching/singletons merely because a factory is called repeatedly, especially if the product contains user data or transaction context.

### 7.4. Handle Object-Creation Failures

Initialization may fail because of invalid configuration, missing credentials, unavailable providers, or exhausted resources. Distinguish **startup configuration errors** from **operational errors while invoking a method**. The contract should specify whether a factory may return `null` or must throw an exception; returning a valid object or throwing a meaningful exception by default simplifies client code.

## 8. Test Each Pattern Against Its Purpose

### Factory Method: Verify That the Shared Algorithm Uses the Created Product

Because `Sender` only prints to the console in the demo, a test can create a Creator that returns a fake Sender and records the invocation. The following uses `NotificationCampaign`/`Sender` from the Factory Method example and runs with JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class FactoryMethodContractTest {
    @Test
    void creatorDelegatesToProduct() {
        AtomicInteger sent = new AtomicInteger();
        NotificationCampaign campaign = new NotificationCampaign() {
            @Override
            protected Sender createSender() {
                return (id, message) -> {
                    assertEquals("CUST-1", id);
                    assertEquals("Hello", message);
                    sent.incrementAndGet();
                };
            }
        };

        campaign.notifyCustomer("CUST-1", "Hello");
        assertEquals(1, sent.get());
    }

    @Test
    void invalidInputIsRejectedBeforeCreation() {
        AtomicInteger creations = new AtomicInteger();
        NotificationCampaign campaign = new NotificationCampaign() {
            @Override
            protected Sender createSender() {
                creations.incrementAndGet();
                return (id, msg) -> {};
            }
        };

        assertThrows(IllegalArgumentException.class,
                () -> campaign.notifyCustomer("", "Hello"));
        assertEquals(0, creations.get());
    }
}
~~~

### Abstract Factory: Verify a Consistent Product Family

A test can instantiate each concrete factory, verify that it creates all required non-`null` products, exercise their interface operations, and verify theme conventions. This JUnit Jupiter example uses classes from `AbstractFactoryDemo.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class AbstractFactoryContractTest {
    @Test
    void darkFactoryCreatesMatchingProducts() {
        UiFactory factory = new DarkUiFactory();

        Button button = assertDoesNotThrow(factory::createButton);
        Checkbox checkbox = assertDoesNotThrow(factory::createCheckbox);

        assertNotNull(button);
        assertNotNull(checkbox);
        assertEquals("Button[DARK]", button.render());
        assertEquals("Checkbox[DARK]", checkbox.render());
    }
}
~~~

The test above uses demo output as a signal of theme consistency. In a real UI application, you could inspect exposed theme/token properties on the abstraction or perform screenshot/visual tests at the integration level. This test alone does not prove that the interface renders correctly in every environment.

**Execution note:** Each main example is a separate `.java` file; place tests in the appropriate package/source set and add the `org.junit.jupiter:junit-jupiter` dependency and a JUnit test runner. The corresponding example classes must be on the classpath.

## 9. Decision Questions and Exercises

### Scenario Table

| Scenario | Option to consider | Rationale |
|---|---|---|
| One shared import tool where XML/JSON subclasses create suitable parsers | **Factory Method** | The Creator retains the import workflow; subclasses choose parsers |
| An app creates Button, Checkbox, and Dialog in Light/Dark themes | **Abstract Factory** | Selects one consistent **product family** |
| One function returns a Sender based on an EMAIL/SMS enum | **Simple Factory** | Centralizes parameter-based creation without Creator subclasses |
| A service only needs one `EmailSender` configured at startup | **Constructor DI** | May be sufficiently simple without an extra factory |
| Changing the discount algorithm on the same order object | **Strategy** | The variable aspect is behavior/algorithm |
| Creating Storage + Queue + Email adapters for AWS/Azure | **Abstract Factory** (if a consistent family is required) | Multiple products belong to one provider; avoid mixed configurations |

### Exercise 1 — Factory Method

Design a fixed `DocumentExporter.export(Document)` process that validates input, creates a `Renderer`, and calls `render(Document)`. Implement two subclasses, `PdfExporter` and `HtmlExporter`, that override `createRenderer()`. Verify that the Creator does not import `PdfRenderer`/`HtmlRenderer`; adding `MarkdownExporter` must not change the shared algorithm. You can implement demo renderers returning `String` values without a real PDF library.

### Exercise 2 — Abstract Factory

Design `CloudFactory` with `createObjectStorage()` and `createMessageQueue()`. Implement `AwsFactory` and `AzureFactory`, each supplying its matching adapters. A `BackupWorkflow` accepts only `CloudFactory`. Write a unit test using a fake factory to test the workflow; then investigate the design error when an implementation accidentally creates AWS Storage and an Azure Queue in the same factory.

### Self-Check

1. In Factory Method, which object **owns the shared algorithm**, and which object **decides the product class**?
2. If clients need three product types from the same theme, which pattern avoids choosing each type separately?
3. Why is `static Sender create(Channel)` not automatically a GoF Factory Method?
4. In Abstract Factory, how do adding a **new family** and adding a **new product type** affect source code differently?
5. When is passing a dependency through a constructor sufficient, without introducing another factory layer?

**Remember:** **Factory Method** extends *how a Product is created inside a Creator's workflow through subclasses*. **Abstract Factory** encapsulates *creating several related Products as one consistent family through a factory object*. Choose based on **the variation point in the problem**, rather than whether the code contains the word “Factory”.
