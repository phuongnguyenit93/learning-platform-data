# Organizing by Feature or by Business Domain

When starting a Spring Boot application, many developers place all controllers in a `controller` folder, all services in `service`, and all repositories in `repository`. This approach is easy to get started with because each package indicates the **type of technical component**. However, as the system grows, a requirement such as "change how orders are placed" can force developers to open many different packages just to find the related classes.

Another organizational approach is grouping source code by **feature** or **business domain**. Instead of asking "is this class a controller or a repository?", we start by asking "which business capability does this class serve?". In a retail application, the capabilities might be `catalog`, `orders`, `customers`, or `payments`. Each group contains the components needed to carry out its work.

Organizing by feature or business domain does not automatically turn an application into microservices or impose a complex architecture. It is a way to **establish code boundaries and ownership** so that modifying, understanding, testing, and evolving a Spring Boot application becomes easier.

## 1. Understanding the Different Ways to Organize Source Code

First, let's distinguish three common perspectives.

| Organization Style | Primary Grouping Criterion | Example Top-Level Packages | Question Answered |
|---|---|---|---|
| By technical layer (*package by layer*) | Component type in the architecture | `controller`, `service`, `repository`, `entity` | "What technical job does this class do?" |
| By feature (*package by feature*) | Capability used by users or the system | `catalog`, `orders`, `checkout` | "Which feature does this class serve?" |
| By business domain (*package by domain*) | Business concepts, rules, and ownership boundaries | `inventory`, `ordering`, `billing` | "Which business area owns this rule?" |

**By feature** and **by business domain** overlap significantly, though they are not completely synonymous. A feature typically stems from a capability or user flow, such as "customer places an order." A domain or subdomain is defined through business models and rules, such as "ordering," "inventory management," or "billing." A checkout feature may simultaneously involve both the ordering and billing domains. Conversely, an ordering domain may provide multiple features: creating orders, canceling orders, and tracking status.

In small projects, a package named `orders` may represent both the feature and the corresponding business domain area. As the project grows, look more closely at responsibilities and dependency directions rather than just folder names.

## 2. Comparing By-Layer and By-Feature Structures

Suppose we are building a bookstore system with Spring Boot, featuring APIs for browsing books, placing orders, and managing customers.

### 2.1. Technical Layer Structure

~~~text
src/main/java/com/example/bookstore/
├── BookstoreApplication.java
├── controller/
│   ├── BookController.java
│   ├── OrderController.java
│   └── CustomerController.java
├── service/
│   ├── BookService.java
│   ├── OrderService.java
│   └── CustomerService.java
├── repository/
│   ├── BookRepository.java
│   ├── OrderRepository.java
│   └── CustomerRepository.java
├── entity/
│   ├── Book.java
│   ├── Order.java
│   └── Customer.java
└── dto/
    ├── BookResponse.java
    ├── CreateOrderRequest.java
    └── OrderResponse.java
~~~

**Pros:** easy to spot classes of the same kind; makes sense for introductory lessons or very small applications where execution flows are short, class counts are low, and few business boundaries exist yet.

**Limitations at scale:** any change to the "orders" feature spans `controller`, `service`, `repository`, `entity`, and `dto`. Packages grow very large, ownership becomes hard to discern, and it is easy to accidentally call another feature's repository or service simply because everything sits technically close together.

Important: packaging by layer is **not wrong as far as Spring Boot is concerned**. Spring still runs normally if beans are within scan scope and properly configured. The issue is that this organization can become difficult to maintain as business requirements grow.

### 2.2. Feature-Based Structure

Those exact same classes can be arranged as follows:

~~~text
src/main/java/com/example/bookstore/
├── BookstoreApplication.java
├── catalog/
│   ├── BookController.java
│   ├── BookService.java
│   ├── BookRepository.java
│   ├── Book.java
│   └── BookResponse.java
├── orders/
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   ├── Order.java
│   ├── CreateOrderRequest.java
│   └── OrderResponse.java
└── customers/
    ├── CustomerController.java
    ├── CustomerService.java
    ├── CustomerRepository.java
    └── Customer.java
~~~

Now, a developer needing to change how orders are created typically starts in one place: `orders`. Inside that package, they can find the request handling flow, order creation logic, persisted data, and returned types.

This structure brings three main benefits:

1. **Higher internal cohesion.** Components solving the same business problem sit close together.
2. **Clearer ownership.** The team responsible for orders can focus on working inside `orders` with minimal changes to the catalog area.
3. **Predictable change scope.** When reviewing a requirement or pull request, files belonging to the same feature are typically changed together.

This alone does not guarantee true boundaries. If `OrderService` directly manipulates `CustomerRepository` and `BookRepository` everywhere, the project still has tangled coupling despite grouping folders by feature. **Where files sit is only the first step; how classes depend on one another determines independence.**

## 3. From Feature to Business Domain: Defining Ownership Boundaries

In Domain-Driven Design (DDD), developers strive to understand the language and rules used by domain experts. For example, an e-commerce system might have:

- **Catalog:** book descriptions, authors, listed prices, search information.
- **Inventory:** physical stock counts, reserved items, warehouse intake and dispatch rules.
- **Ordering:** shopping carts and placed orders, order processing states, cancellation conditions.
- **Billing:** invoices, amounts due, reconciliation.
- **Shipping:** packing, delivery, shipment tracking states.

"Catalog" and "inventory" may both talk about a product, yet **do not necessarily own the same data or the same rules**. Catalog manages descriptive content; Inventory manages sellable quantities. Putting everything into a `product` package just because it relates to products easily creates an oversized package.

A good business boundary usually answers:

- Which rules is this area responsible for?
- Which data is allowed to be modified directly here?
- What results do other areas need to know to collaborate, without needing to know internal implementation?
- When a rule changes, which parts must be edited?

In small systems, you may not need full DDD or immediate subdomain splitting. Still, using **business terminology** to name packages is a very helpful foundation.

### How Do a Bounded Context and a Package Differ?

A **bounded context** is a boundary within which a model and business terms have consistent meaning. A Java package is a mechanism for organizing classes and controlling access in source code. They are related but not equivalent: a bounded context may span multiple packages; a package does not automatically enforce bounded-context rules.

Similarly, a **business module** may consist of several internal packages and a public API. It can still live inside **a single Spring Boot application and a single JAR**. You do not need to split into microservices just to practice domain-oriented organization.

## 4. A Practical Structure for Spring Boot

When a feature has many classes, you can combine both approaches: **organized by business area on the outside, and by technical responsibility on the inside**.

~~~text
src/
├── main/
│   ├── java/com/example/bookstore/
│   │   ├── BookstoreApplication.java
│   │   ├── catalog/
│   │   │   ├── api/
│   │   │   │   ├── BookController.java
│   │   │   │   └── BookResponse.java
│   │   │   ├── application/
│   │   │   │   └── SearchBooksService.java
│   │   │   ├── domain/
│   │   │   │   └── Book.java
│   │   │   └── persistence/
│   │   │       └── BookRepository.java
│   │   ├── orders/
│   │   │   ├── api/
│   │   │   │   ├── OrderController.java
│   │   │   │   └── CreateOrderRequest.java
│   │   │   ├── application/
│   │   │   │   └── PlaceOrderService.java
│   │   │   ├── domain/
│   │   │   │   └── Order.java
│   │   │   └── persistence/
│   │   │       └── OrderRepository.java
│   │   ├── customers/
│   │   │   └── ...
│   │   └── configuration/
│   │       └── SecurityConfiguration.java
│   └── resources/
│       └── application.yml
└── test/
    └── java/com/example/bookstore/
        ├── catalog/
        └── orders/
~~~

The meaning of the subpackages (when needed) is:

| Subpackage | Common Responsibilities | What to Avoid |
|---|---|---|
| `api` or `web` | REST controllers, HTTP request/response DTOs, API-related error translation | Writing all business rules directly inside controllers |
| `application` | Use-case orchestration, task-level transactions, calling necessary components | Holding all kinds of logic without separating responsibilities |
| `domain` | Business concepts and rules, objects representing valid state | Depending directly on HTTP requests or user interfaces |
| `persistence` or `infrastructure` | Storage details, adapters calling external systems, feature-specific integration config | Letting other features depend directly on storage details |

Names like `api`, `application`, `domain`, and `persistence` are common conventions, **not Spring Boot requirements**. A feature with just one controller and one service can place both classes directly in `catalog`. Do not create empty packages or pass-through layers that merely forward calls without adding meaning.

### Root Package and Component Scan

Place the startup class in the highest common package that Spring needs to scan:

~~~java
package com.example.bookstore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookstoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookstoreApplication.class, args);
    }
}
~~~

With this placement, default component scan can locate annotated components such as `@RestController`, `@Service`, and `@Component` inside subpackages like `com.example.bookstore.catalog`, `com.example.bookstore.orders`, etc.

If you accidentally place `BookstoreApplication` inside `com.example.bookstore.orders`, Spring may fail to auto-scan controllers in `catalog` by default. This is a **scan scope** issue, not proof that feature-based organization is incompatible with Spring.

With Spring Data JPA, default entity and repository scan scopes also tie back to the application configuration package and auto-configuration settings. If you intentionally place entities/repositories outside the package tree, configure scanning accordingly for the version and technology in use.

## 5. Interaction Example Between Two Features: Catalog and Orders

A real system needs features to collaborate. For example, **Orders** needs product pricing information from **Catalog** before creating an order. A clean organization lets Catalog publish a **small contract**, while keeping Catalog's persistence details internal.

To stay focused on package boundaries, the following snippets only illustrate the key classes; supporting types such as entities, repositories, and exceptions must be fully implemented in a real application.

### 5.1. Catalog Publishes a Contract for Reading Products

File `catalog/ProductInfo.java`:

~~~java
package com.example.bookstore.catalog;

import java.math.BigDecimal;

public record ProductInfo(
        Long id,
        String title,
        BigDecimal unitPrice
) {}
~~~

File `catalog/ProductCatalog.java`:

~~~java
package com.example.bookstore.catalog;

public interface ProductCatalog {
    ProductInfo findAvailableProduct(Long productId);
}
~~~

These two types serve as the **Java API between business areas within the same application**. `ProductInfo` carries only the data other features truly need; it does not expose internal JPA entities or repositories.

### 5.2. Catalog Implements Its Contract Using Its Own Data

Example service inside Catalog:

~~~java
package com.example.bookstore.catalog;

import org.springframework.stereotype.Service;

@Service
class DatabaseProductCatalog implements ProductCatalog {
    private final BookRepository repository;

    DatabaseProductCatalog(BookRepository repository) {
        this.repository = repository;
    }

    @Override
    public ProductInfo findAvailableProduct(Long productId) {
        Book book = repository.findById(productId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Book not found"));

        return new ProductInfo(
                book.getId(),
                book.getTitle(),
                book.getCurrentPrice()
        );
    }
}
~~~

In this example, `BookRepository` and `Book` are assumed to be internal types in the same `catalog` package; production code may place them in subpackages and adjust visibility accordingly. Leaving `DatabaseProductCatalog` without the `public` keyword expresses the intent to keep it as a package-internal implementation detail.

Spring can still discover `@Service` classes under the root package and inject the bean via the `ProductCatalog` interface in standard Spring Boot packaging. If using the Java Platform Module System or stricter encapsulation rules, design accessibility and reflection appropriately.

### 5.3. Orders Depends on the Contract, Not on Catalog's Repository

File `orders/PlaceOrderService.java` (abbreviated example):

~~~java
package com.example.bookstore.orders;

import com.example.bookstore.catalog.ProductCatalog;
import com.example.bookstore.catalog.ProductInfo;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final ProductCatalog productCatalog;
    private final OrderRepository orderRepository;

    public PlaceOrderService(
            ProductCatalog productCatalog,
            OrderRepository orderRepository
    ) {
        this.productCatalog = productCatalog;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long place(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than 0"
            );
        }

        ProductInfo product =
                productCatalog.findAvailableProduct(productId);

        Order order = Order.create(
                product.id(),
                product.unitPrice(),
                quantity
        );

        return orderRepository.save(order).getId();
    }
}
~~~

`Order` and `OrderRepository` are owned by Orders, and in this example are assumed to sit in the same `orders` package. `Order.create(...)` indicates where order creation rules live, such as capturing the unit price at the time of ordering; the exact rule details are unnecessary for understanding package organization.

Main dependency direction:

~~~text
    orders/PlaceOrderService
             |
             | calls public API
             v
      catalog/ProductCatalog
             ^
             | implements
             |
 catalog/DatabaseProductCatalog
             |
             v
     catalog/BookRepository
~~~

Orders knows about `ProductCatalog` and `ProductInfo`, yet **does not need to know** whether Catalog uses JPA, JDBC, an external API, or a cache. Changing Catalog's storage strategy therefore has minimal impact on Orders, as long as the contract and business semantics are preserved.

If Orders directly injected Catalog's `BookRepository` and manipulated `Book` as its own entity, data access rules would scatter. Whenever Catalog changed its storage model, Orders would easily break along with it.

### 5.4. Controllers Should Target Feature Use Cases

The Orders controller typically just translates HTTP requests into business calls and converts results into HTTP responses:

~~~java
package com.example.bookstore.orders;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderService placeOrderService;

    public OrderController(PlaceOrderService placeOrderService) {
        this.placeOrderService = placeOrderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderCreatedResponse create(
            @RequestBody CreateOrderRequest request
    ) {
        Long orderId = placeOrderService.place(
                request.productId(), request.quantity()
        );
        return new OrderCreatedResponse(orderId);
    }

    public record CreateOrderRequest(Long productId, int quantity) {}
    public record OrderCreatedResponse(Long id) {}
}
~~~

An example request:

~~~http
POST /orders
Content-Type: application/json

{
  "productId": 101,
  "quantity": 2
}
~~~

Processing flow:

1. `OrderController` in Orders receives the request and translates it into use-case parameters.
2. `PlaceOrderService` checks ordering conditions and queries Catalog via `ProductCatalog`.
3. Catalog reads book information using its own internal mechanism.
4. Orders creates the order object and saves it with Orders' repository.
5. The controller returns the order ID in the HTTP response.

This is an **illustration of boundaries and call direction**, not a complete ordering workflow. A real retail system also has to handle input validation, currency, price changes, inventory reservation, concurrency errors, authorization, exception mapping, and consistency across concurrent transactions. Those responsibilities should be placed in the business area that owns each rule.

## 6. Establishing Package Boundaries to Reduce Coupling

Moving files into feature folders only solves the visual layout. For packages to remain meaningful long term, several dependency rules should be established.

### Expose Only What Needs to Be Used Outside the Feature

A feature can have a **public interface** and **internal details**:

~~~text
catalog/
├── ProductCatalog.java        <- contract used by other features
├── ProductInfo.java           <- data required for exchange
├── DatabaseProductCatalog.java <- implementation detail
├── Book.java                  <- internal Catalog model
└── BookRepository.java        <- internal storage mechanism
~~~

In Java, package-private visibility (omitting `public` on top-level classes) can restrict direct access from other packages. However, **a subpackage is a different package**: `catalog.persistence` is not in the same Java package as `catalog`. When organizing with multiple subpackages, controlling visibility also relies on modules, explicit APIs, code reviews, or architecture-checking tools when truly needed. Do not assume everything under `catalog.*` is automatically hidden from `orders`.

Not every `public` class should be treated as a stable usage contract. Package names, grouping conventions, and documented responsibilities also matter greatly.

### Limit Circular Dependencies

Problematic example:

~~~text
orders/OrderService -> catalog/BookService
catalog/BookService -> orders/OrderService
~~~

Circular dependencies obscure business flows; in Spring, they can also trigger bean circular dependency errors at startup. You should not solve this by enabling circular references by default. Identify which side truly owns the work: move orchestration to the right feature, define a one-way contract, or use events if the business workflow fits.

For example, after an order is created, Orders could publish an "OrderPlaced" event for other parts to handle follow-up work. Yet events are not a default silver bullet: you must account for transactions, error handling, retries, idempotency, and event ordering. For a simple synchronous call, a public interface between features is usually clearer.

### Avoid Turning a "Shared" Package into a Dumping Ground

A `shared` or `common` package often starts small and accumulates utilities, DTOs, entities, and business rules from every feature. Eventually every feature depends on it, erasing ownership boundaries.

Only move code that is genuinely cross-cutting into a shared area, such as application-level infrastructure configuration or a stable abstraction used across multiple areas. If two features have DTOs with similar names yet different semantics, keeping two independent DTOs is usually better than creating a "shared" type prone to ripple-effect changes.

## 7. Combining Feature Organization with Layered Architecture

"Organizing by feature" and "layered design" are not mutually exclusive. They answer two different questions:

- **By feature/domain:** who owns the code and the rules?
- **By layer:** within that feature, at what level of responsibility does the code operate?

For instance, the following structure is a sensible option for a feature with complex logic:

~~~text
orders/
├── api/
│   ├── OrderController.java
│   └── dto/
├── application/
│   ├── PlaceOrderUseCase.java
│   └── CancelOrderUseCase.java
├── domain/
│   ├── Order.java
│   └── OrderStatus.java
└── infrastructure/
    ├── JpaOrderRepository.java
    └── OrderJpaEntity.java
~~~

In an architecture aimed at decoupling the domain from technology, domain objects do not need to know about `@RestController` or how JPA persists data; repository interfaces can sit near domain/application, while implementations sit in infrastructure. However, that is an **optional architectural choice**, not a requirement of feature-based packaging.

For small CRUD applications, using JPA entities directly inside a feature's service can be a simple and acceptable solution. As business rules grow and evolve independently from persistence, separating the domain model from persistence becomes more valuable. The degree of layering should follow actual complexity.

## 8. Common Organizational Decisions

### Should Features Be Broad or Narrow?

An overly broad feature, such as `commerce` containing all of catalog, ordering, billing, and shipping, produces a gigantic package. An overly narrow feature, such as putting every operation `createOrder`, `cancelOrder`, and `getOrder` into completely separate top-level packages, easily fragments the shared order concept.

You can usually start from a **semantically stable business capability**, then subdivide when distinct rules or independently changing sub-teams emerge. Use cases within the same domain can live under `orders.application` if helpful.

### Where Should Request/Response DTOs Live?

DTOs belong to the contract they serve. `CreateOrderRequest` belongs to the Orders API, so it should sit near `OrderController` or in `orders.api.dto`. A Catalog DTO should not be reused as an Orders request simply because they share a few fields.

Inter-feature exchange DTOs differ from HTTP DTOs: `ProductInfo` in the example is a contract between Orders and Catalog, not necessarily the JSON Catalog returns to end users. Separating these two contract types makes it easier to evolve HTTP APIs with minimal impact on internal features.

### Which Layer Owns Validation?

Syntactic constraints on HTTP requests (such as required fields and formats) can be handled at the API layer, commonly with Bean Validation. However, rules like "a shipped order cannot be canceled" must be enforced where order business logic is owned. If placed only in the controller, another service call flow could bypass the rule.

### Where Do Transactions Belong?

`@Transactional` is usually placed at an appropriate use-case/service boundary, where the application must ensure data modifications happen as an atomic unit. There is no rule requiring all transactions to sit inside a global `transaction` package. Package organization does not alter the nature of Spring transactions, proxy mechanics, or database transaction scopes.

### Where Do Configuration and Security Live?

Application-wide configuration, such as general Spring Security configuration, can live under `configuration` in the root package. Configuration serving only Orders can sit in `orders`. Business-specific authorization rules still need to be enforced at the appropriate layer within the feature; having a central security configuration does not mean every business check belongs there.

## 9. Testing and Team Collaboration Around Feature Boundaries

A test structure typically mirrors the source structure:

~~~text
src/test/java/com/example/bookstore/
├── catalog/
│   ├── ProductCatalogTest.java
│   └── CatalogControllerTest.java
└── orders/
    ├── PlaceOrderServiceTest.java
    └── OrderControllerTest.java
~~~

When verifying ordering rules, developers know to look for tests in `orders`. When testing the contract between Orders and Catalog, a test can mock `ProductCatalog` to focus on Orders' decisions, or use an integration test when verifying how both parts actually interact.

In Spring Boot, you can use the appropriate test types: plain Java tests for domain rules, web slices with `@WebMvcTest` for controllers, data slices with `@DataJpaTest` for persistence, or `@SpringBootTest` for integration flows. Each has its own purpose; organizing by feature does not mean creating a separate ApplicationContext for every package.

For development teams, feature boundaries also help assign ownership and reduce merge conflicts on the same files. However, if multiple teams constantly need to modify the same internal API, that is a signal to revisit the contract or boundary division, not just rename packages.

## 10. When Should You Use Which Approach?

| Context | Suggested Organization | Reason |
|---|---|---|
| First Spring Boot lesson, very few classes | By layer or simple feature groups | Learners easily see the controller–service–repository relationship |
| Project with a few relatively independent features | **By feature**, each with its own controller/service/repository | Easy to locate code and edit an entire feature |
| Diverse business rules and multiple owning teams | **By business domain**, defining responsibilities and contracts | Prevents rule leakage and cross-coupling |
| A feature starts accumulating many components | Features on the outside, `api`/`application`/`domain`/`infrastructure` inside when useful | Preserves business boundaries while clarifying technical roles |
| Project currently organized by layer but still easy to maintain | Migrate only parts with active change needs gradually | Avoids massive structural churn without clear value |

You do not have to choose between "100% package by layer" and "100% package by feature." Start simple, observe which groups of files change together, and shape boundaries accordingly. Organizing around **how the system changes** is usually more sustainable than forcing one rigid layout onto every project.

## 11. Migrating Gradually from By-Layer to By-Feature

If a project already has many files under `controller`, `service`, and `repository`, you do not have to move everything at once. You can migrate one business capability at a time:

1. **Pick one clear scope**, such as ordering. Identify the controllers, services, entities, repositories, DTOs, and tests that truly belong to that scope.
2. **List outbound dependencies**: which classes in Catalog, Customers, or shared infrastructure does Orders call? Identify which calls are contracts to keep.
3. **Create the `orders` package** and move the related classes and tests; update `package` and `import` declarations using your IDE's refactoring tools.
4. **Define a small internal API** for parts other features need to call; avoid forcing other areas to reach directly into internal repositories or entities.
5. **Tighten access modifiers** and dependency injection boundaries to make the separation explicit, if the project permits.
6. **Review anything tied to class/package names** such as scan configurations, framework mappings, security rules, or type references. Changing packages alone usually does not require changing HTTP endpoints or database schemas, unless the project has configurations bound to class/package names.
7. **Continue with the next feature** once the new structure stabilizes and makes changes clearer.

In Spring Boot, moving packages requires special attention to `@SpringBootApplication` placement, component scan scope, entities, and Spring Data repositories. These are mechanisms affected by package names even when business logic has not changed.

## 12. Signs of Suboptimal Organization

Watch for a few symptoms to decide whether adjustments are needed:

| Symptom | Possible Cause | Improvement Direction |
|---|---|---|
| A small change requires editing across many technical packages | Layered structure scatters files for the same feature | Group by feature or related use case |
| One service handles order creation, stock deduction, billing, and shipping | Business responsibility is too broad | Identify owning domains; coordinate via clear contracts |
| Features inject each other's repositories | Data boundaries are bypassed | Expose a public API/use case on the data owner |
| `shared` holds most business logic | Code ownership is unclear | Move logic back to appropriate domains; share only stable abstractions |
| Circular dependencies frequently occur between features | Call paths lack clear direction | Identify the orchestrator and enforce one-way dependency rules |
| Every simple controller and service has multiple interfaces and intermediate layers | Ceremonial layering exceeds actual needs | Reduce pass-through classes; keep structure proportionate |
| Packages are named after UI screens while one business flow spans multiple screens | Boundaries follow UI rather than real business rules | Group code by business capability or owning domain |

A practical rule of thumb: **classes that frequently change for the same reason should sit close together; parts that change for different reasons should have clear boundaries.** If a change in Catalog forces edits to many internal classes in Orders, re-examine the contract between the two features.

## 13. Self-Practice Exercise

Suppose you are building a Spring Boot application for a school library. Initial requirements:

- Students search for books by title or author.
- Librarians manage the number of book copies available.
- Students borrow and return books.
- The system calculates overdue days and late fees.

Try designing the top-level packages before writing any controllers. A possible starting point:

~~~text
com.example.library/
├── LibraryApplication.java
├── catalog/
│   └── ... book search and descriptions
├── inventory/
│   └── ... copy counts and availability
├── loans/
│   └── ... borrowing, returning, and due date rules
└── fines/
    └── ... calculating, recording, and paying fines
~~~

Ask yourself: does "book title" data belong to Catalog or Loans? Where does the rule "disallow borrowing when zero copies remain" belong? If Loans needs to know whether copies are available, should it call `InventoryRepository` directly or call a contract provided by Inventory? When the library introduces a new fine policy, which packages have a legitimate reason to change?

There is no single package tree that is right for every problem. What you need to be able to explain is **each package's responsibility**, **the dependency flow between packages**, **how business changes impact source code**, and **how Spring Boot will discover the components**.

## Conclusion

Organizing Spring Boot source code by feature or business domain puts the focus on what the application does and which rules the system must protect. Layered technical structures remain useful for dividing responsibilities inside a feature; the key is avoiding scattering a business capability across distant packages and coupling it to too many internal details of other areas.

Start with package names that express the business, keep related components together, publish only the contracts truly needed, and control dependency direction. With Spring Boot, remember to place the startup class in an appropriate root package so component scan and related discovery mechanisms find the application's components. As requirements grow, feature/domain boundaries serve as a foundation for adding use cases, tests, and evolving the architecture without rewriting the entire system.
