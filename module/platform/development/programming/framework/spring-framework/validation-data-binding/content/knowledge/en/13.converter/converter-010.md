# Distinguishing Data Conversion from Authorization Checks or Business Lookups

In Spring Framework, `Converter<S, T>` has one clear responsibility: transforming a value from source type `S` to target type `T`. For example, it can turn the string `"ab-012"` into a `ProductCode("AB-012")` value object. It should not decide whether the current user has permission to use that code, whether the code exists in the database, or whether the product has enough stock for an order.

Three groups of work must be kept separate:

1. **Conversion:** turning a representation into a typed value according to defined syntax and normalization rules.
2. **Authorization:** determining whether the current principal is allowed to perform an action on a specific resource.
3. **Business lookup and rules:** fetching authoritative data and deciding whether an action is valid under business state.

Putting all three inside `Converter.convert(...)` couples conversion to the database, security context, and transactions; makes testing and reuse harder; can trigger hidden repeated queries during binding; and distorts error types. This article explains that boundary with Java 17+ and Spring Framework 6.2.x examples.

## 1. Three Distinct Questions

Suppose a request sends:

```text
productCode = "ab-012"
quantity    = "2"
```

The application must answer three questions:

| Question | Example | Appropriate component |
| --- | --- | --- |
| Can the value be converted to the target type? | Does `"ab-012"` match product code syntax? | `Converter<String, ProductCode>` |
| Is the caller permitted to place an order? | Does the current user have permission to create orders in this tenant/warehouse? | Spring Security / authorization service |
| Do data and state satisfy business rules? | Does the code exist? Still on sale? Does the warehouse have 2 units? | Application service / repository / domain rule |

Common flow:

```text
HTTP request
  productCode = "ab-012"
  quantity    = "2"
        |
        v
Binding + Conversion
  String -> ProductCode
  String -> Integer
        |
        v
Typed, syntactically valid DTO
        |
        v
Authentication / Authorization
  Who is calling? Authorized on the resource?
        |
        v
Business lookup + rules
  Look up product, check status, stock
        |
        v
Execute business logic / return appropriate error
```

Steps can be organized differently depending on architecture, yet conversion never replaces authorization or lookup. A converter may be invoked from MVC form binding, `BeanWrapper`, other code using `ConversionService`, batch jobs, or tests. It should not need to know the full request or the current user.

## 2. Conversion: Type Transformation and Representation Normalization

Conversion turns an existing value into a value of another type, for example:

- `String -> Integer`: `"42"` into the number 42.
- `String -> UUID`: UUID string into a `UUID` object.
- `String -> ProductCode`: normalizing and validating product code syntax.
- `Long -> CustomerId`: creating a value object from a numeric ID.
- `String -> LocalDate`: parsing according to a defined format.

The primary interface in Spring Core has the form:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

This is a shortened form of the interface. The `convert` method accepts one source value and returns the target value; if conversion is impossible, the implementation can throw an appropriate exception. The core API does not take a principal, request, repository, or transaction as parameters.

A converter should answer: “can this value be represented by the target type under the published contract?”. For example, product codes must match pattern `AA-999`. If the string fails the pattern, reject it as a conversion failure because a valid value object cannot be built.

**Valid syntax does not mean existence.** `AB-012` can become `ProductCode("AB-012")` even if the database holds no such product. A converter does not need to know the catalog to do its job.

### 2.1. Characteristics of a Good Converter

- Output depends only on the source and defined conversion rules.
- No database or network access.
- No calls to services with side effects.
- Does not read the principal or security context.
- Holds no per-request state across calls.
- Deterministic and easy to unit test.
- Bad input is never silently turned into another valid value.

“Pure” here denotes an architectural boundary: the converter needs no external state varying by user, tenant, or database. It can rely on immutable configuration, yet if it must query the latest data at request time, that is typically a lookup rather than simple conversion.

## 3. Authorization: Is the Caller Permitted?

Authorization checks an authenticated principal's rights for an action/resource. It typically needs to know:

- Who is the caller?
- Which action is being requested?
- Which specific resource is affected?
- Which tenant/owner/scope does the resource belong to?
- Which authority, scope, or policy applies?
- Does permission depend on resource state or relationships between objects?

For instance, `ProductCode("AB-012")` is syntactically valid and the product exists, yet user A is not allowed to place orders for tenant B. The decision to deny belongs to authorization.

Spring Security supports authorization at the request level and method level. Services can be protected with `@PreAuthorize` (when method security is enabled), or enforce policies inside the application service when permissions depend on domain data. Checks must run on the server at the action execution point; hiding a button in the UI does not protect an endpoint.

```java
@Service
public class OrderApplicationService {
    @PreAuthorize("hasAuthority('order:create')")
    public OrderResult createOrder(CreateOrderCommand command) {
        // Additional checks on the specific resource/tenant may be needed.
        ...
    }
}
```

This is an architectural illustration snippet, not a complete class. Authority `order:create` is an example policy; a method-level annotation alone does not prove the caller can access every product or tenant in the command.

**Do not put `SecurityContextHolder` inside a converter to check permissions.** The exact same string would yield different conversion outcomes per user, even though syntax never changed. Converters can also run in batch jobs, background tasks, tests, or bean configuration with no HTTP security context.

## 4. Business Lookup: Does Data Exist and Satisfy State Rules?

Business lookup queries an authoritative data source, usually via a repository or service. Examples:

- Does the product code have a corresponding record?
- Is the product still active or discontinued?
- Which contract/price list applies to the buyer?
- Which price is effective at order time?
- Does the warehouse have enough stock?
- Does quantity exceed the customer's limit?

A typical service:

```java
@Service
public class OrderApplicationService {
    private final ProductRepository products;
    private final AuthorizationService authorization;

    public OrderApplicationService(
            ProductRepository products,
            AuthorizationService authorization) {
        this.products = products;
        this.authorization = authorization;
    }

    public OrderResult create(
            CurrentUser user, CreateOrderCommand command) {
        Product product = products.findByCode(command.productCode())
                .orElseThrow(ProductNotFoundException::new);

        authorization.requireCanOrder(user, product);
        product.requireActive();
        product.requireAvailable(command.quantity());

        return placeOrder(user, product, command.quantity());
    }
}
```

This is pseudocode requiring domain classes/interfaces. Lookup and authorization order depends on policy—for instance, some applications filter queries by tenant up front to avoid disclosing out-of-scope resources. The core point is that the application service coordinates lookups, policies, and domain rules; the converter only constructs `ProductCode`.

### 4.1. Lookup Is Not Syntax Validation

`findByCode("AB-012")` is a query. It can fail to find a record even when the string is valid. Conversely, if a string has invalid syntax, there is no need to query the database to recognize it is not a valid code.

Separating these stages helps:

- Avoid hitting the DB for obviously malformed input.
- Avoid merging “cannot convert type” with “not found”.
- Return more accurate HTTP status codes and error codes.
- Control caching and lookup performance easily.
- Keep `ConversionService` decoupled from persistence.

## 5. Decision Tree: Which Layer Owns the Logic?

```text
What are you trying to determine?
        |
        +-- Convert representation/type?
        |       -> Converter / Formatter / value object
        |
        +-- Is the caller permitted?
        |       +-- General role/scope -> Spring Security
        |       +-- Resource/tenant permission -> authorization policy
        |
        +-- Do data/state satisfy rules?
                +-- Needs persistent data -> repository via service
                +-- Aggregate rule -> domain model/service
```

A useful review question: **If the source value is identical yet the user or database changes, should the result change?**

- Conversion result should stay the same: sign that the logic belongs in a converter.
- Outcome depends on principal/permission: belongs in authorization.
- Outcome depends on records, price, stock, or state: belongs in lookup/business rules.

Sometimes a code catalog is static configuration loaded immutably at startup. That can serve as conversion configuration if it is merely a static alias table. However, if the question is “does this value currently exist or is it permitted for use?”, handle it in lookup/policy.

## 6. Runnable Java 17+ Example: Pure Converter, Service Performs Lookup

A standalone Maven example with Spring Core. It demonstrates:

1. Value object `ProductCode` enforces its own syntactic invariant.
2. Converter normalizes the source without needing a database.
3. `ConversionService` invokes the converter.
4. Repository and authorization are represented as separate interfaces.
5. Application service coordinates lookup, permissions, and business rules.

So the program runs standalone without a database or Spring Security server, repository and authorization use in-memory fakes. Real applications replace them with proper persistence/security adapters.

### 6.1. Project Structure

```text
conversion-boundary-demo/
├── pom.xml
└── src/main/java/ConversionBoundaryDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>conversion-boundary-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/ConversionBoundaryDemo.java`:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;

public class ConversionBoundaryDemo {

    public record ProductCode(String value) {
        public ProductCode {
            if (value == null || !value.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid product code");
            }
        }
    }

    // Only parses and normalizes; does not access repository/security.
    public static final class ProductCodeConverter
            implements Converter<String, ProductCode> {
        @Override
        public ProductCode convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Product code is required");
            }
            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new ProductCode(normalized);
        }
    }

    public record User(String username, Set<String> permissions) {}
    public record Product(ProductCode code, boolean active) {}
    public record CreateOrderCommand(ProductCode productCode, int quantity) {}
    public record OrderResult(String message) {}

    public interface ProductRepository {
        Optional<Product> findByCode(ProductCode code);
    }

    public interface ProductAuthorization {
        void requireCanOrder(User user, Product product);
    }

    public static final class InMemoryProductRepository
            implements ProductRepository {
        private final Map<ProductCode, Product> data;

        public InMemoryProductRepository(Map<ProductCode, Product> data) {
            this.data = Map.copyOf(data);
        }

        @Override
        public Optional<Product> findByCode(ProductCode code) {
            return Optional.ofNullable(data.get(code));
        }
    }

    public static final class PermissionCheck
            implements ProductAuthorization {
        @Override
        public void requireCanOrder(User user, Product product) {
            if (!user.permissions().contains("order:create")) {
                throw new SecurityException("Order permission required");
            }
        }
    }

    public static final class OrderApplicationService {
        private final ProductRepository repository;
        private final ProductAuthorization authorization;

        public OrderApplicationService(
                ProductRepository repository,
                ProductAuthorization authorization) {
            this.repository = repository;
            this.authorization = authorization;
        }

        public OrderResult create(User user, CreateOrderCommand command) {
            if (command.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Quantity must be positive");
            }

            Product product = repository.findByCode(command.productCode())
                    .orElseThrow(() ->
                            new IllegalStateException("Product not found"));

            authorization.requireCanOrder(user, product);

            if (!product.active()) {
                throw new IllegalStateException("Product is inactive");
            }

            return new OrderResult(
                    "Order accepted for " + product.code().value());
        }
    }

    public static void main(String[] args) {
        DefaultConversionService conversions =
                new DefaultConversionService();
        conversions.addConverter(new ProductCodeConverter());

        ProductCode existingCode = new ProductCode("AB-012");
        ProductRepository repository = new InMemoryProductRepository(
                Map.of(existingCode, new Product(existingCode, true))
        );

        ProductAuthorization authorization = new PermissionCheck();
        OrderApplicationService orders =
                new OrderApplicationService(repository, authorization);

        User buyer = new User("linh", Set.of("order:create"));
        User viewer = new User("minh", Set.of("catalog:read"));

        ProductCode validCode =
                conversions.convert(" ab-012 ", ProductCode.class);
        OrderResult accepted = orders.create(
                buyer, new CreateOrderCommand(validCode, 2));
        System.out.println("valid=" + accepted.message());

        // Valid syntax, yet the repository does not contain this code.
        ProductCode unknownCode =
                conversions.convert("ZZ-999", ProductCode.class);
        try {
            orders.create(buyer, new CreateOrderCommand(unknownCode, 1));
        } catch (IllegalStateException ex) {
            System.out.println("lookup=" + ex.getMessage());
        }

        // Same product/same code; different principal lacking permission.
        try {
            orders.create(viewer, new CreateOrderCommand(validCode, 1));
        } catch (SecurityException ex) {
            System.out.println("authorization=" + ex.getMessage());
        }

        // Invalid syntax: fails before lookup.
        try {
            conversions.convert("not-a-code", ProductCode.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("conversion=Invalid product code");
        }
    }
}
```

Run in the `conversion-boundary-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=ConversionBoundaryDemo
```

Expected output from the `System.out.println` statements:

```text
valid=Order accepted for AB-012
lookup=Product not found
authorization=Order permission required
conversion=Invalid product code
```

### 6.2. Analyzing Each Case

**Conversion:** `conversions.convert(" ab-012 ", ProductCode.class)` normalizes the input and creates `ProductCode`. The converter has no dependency on `ProductRepository` or `ProductAuthorization`.

**Lookup:** `ZZ-999` is syntactically valid so it converts cleanly. The repository has no matching record, so the service reports “Product not found”.

**Authorization:** given the same `ProductCode("AB-012")` and the same record, user `linh` has authority `order:create` and is allowed; user `minh` lacks permission and is denied. Authorization outcomes differ by principal, while conversion output remains unchanged.

**Business rule:** the service also checks positive quantity and active product status. Those rules do not belong in the converter.

**Demo limitations:** the in-memory repository does not simulate transactions, concurrency, real data, or a Spring Security context. The example only illustrates where each responsibility lives. With a real database, the repository is an injected adapter and state mutations require appropriate transactions.

## 7. Why Should a Converter Not Query the Database?

An implementation like the following is an anti-pattern:

```java
public class ProductConverter
        implements Converter<String, Product> {

    private final ProductRepository repository;

    @Override
    public Product convert(String source) {
        return repository.findByCode(new ProductCode(source))
                .orElseThrow(ProductNotFoundException::new);
    }
}
```

This is not recommended. Problems:

1. **Conversion depends on the database:** given the same source string, output changes depending on when records are inserted or deleted.
2. **Hidden queries inside binding:** binders can call converters multiple times; each call can trigger an opaque query.
3. **Wrong error category:** “failed to parse” and “record not found” get collapsed into conversion/type mismatch errors.
4. **Hard to reuse:** batch jobs, loggers, message handlers, or tests that just want to parse a code would also need persistence.
5. **Hard to optimize:** callers cannot easily batch lookups, control fetch plans, or paginate.
6. **Unclear transactions:** conversion can happen in many contexts; hidden I/O obscures transaction lifecycles.
7. **Layer coupling:** conversion infrastructure becomes aware of persistence and domain exceptions.

The right approach is for the converter to build `ProductCode`; the application service receives `ProductCode` to look up the product. If a form needs product details for suggestions, build an endpoint/query service with a clear contract instead of turning a parser into a lookup service.

### 7.1. Can Configuration Data Participate in Conversion?

A small, stable alias table loaded immutably at startup may exist. If it only describes representation rules, does not depend on principal/request, and does not change with business state, using that configuration inside a converter can be reasonable.

However, if data changes and must be queried at the current point in time, or if the question is “does this value exist or is it permitted right now?”, use lookup/policy. Caching does not turn a business lookup into conversion.

## 8. Why Should a Converter Not Check Permissions?

A converter can be called during form binding, via `BeanWrapper`, in tests, in batch jobs, or when other code calls `ConversionService`. Not every context has an authenticated HTTP user.

If a converter reads `SecurityContextHolder.getContext()`:

- The same string can convert differently depending on the user, even though syntax never changed.
- Background jobs or async threads may have no security context.
- Conversion tests would have to mock a principal just to test parsing.
- Reviewers struggle to spot authorization hidden behind property assignment.
- A conversion call meant simply to inspect or format data could accidentally trigger policy checks.

Authorization must run at **the point of action**. For example, an order-creation endpoint must call a protected service; if permission depends on the resource, the service proceeds to check the exact product/tenant.

### 8.1. Request Authorization and Method Authorization

Spring Security can protect endpoints by authority:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/orders")
        .hasAuthority("order:create")
        .anyRequest().authenticated());
```

This is a configuration snippet inside a Spring Security application; it requires a filter chain, imports, and matching dependencies. It enforces general permissions at the endpoint.

For resource-dependent permissions, a service can use:

```java
@PreAuthorize("hasAuthority('order:create')")
public OrderResult createOrder(CreateOrderCommand command) {
    Product product = repository.findByCode(command.productCode())
            .orElseThrow(ProductNotFoundException::new);
    authorization.requireCanOrder(currentUser(), product);
    return createFor(product, command.quantity());
}
```

This illustration requires method security enabled and an appropriate way to obtain the principal. Annotations do not replace checking tenant/owner when policies require that information.

### 8.2. Avoid Inadvertently Disclosing Resource Existence

Some APIs want to return `404` for both cases: product does not exist, or the caller is not permitted to know it exists. Other APIs return `403` when the resource exists yet the user lacks permission. That is a decision about **information disclosure**, not a converter concern.

Lookup/authorization ordering depends on policy. For example, a repository query can filter by tenant taken from the principal up front, never loading resources outside the tenant. What matters is having a clear, consistent policy enforced on the server.

## 9. Converter, Formatter, Validator, and Authorization Do Not Replace Each Other

| Component | Role | Example |
| --- | --- | --- |
| `Converter<S,T>` | Converts source type to target type | `String -> ProductCode` |
| `Formatter<T>` | Parses/prints according to `Locale` | `String <-> BigDecimal` |
| `Validator` / Bean Validation | Checks constraints on input/objects | `quantity >= 1` |
| Authorization service | Checks principal rights on actions/resources | Has `order:create` authority? |
| Repository | Accesses persistent data | Finds product by code/tenant |
| Application service | Coordinates lookup, policy, domain rules, transactions | Creates order |

A converter can reject syntactically invalid strings. That remains a conversion failure. Yet the rule “product is active” depends on the database/state at processing time, not on formatting rules.

Validators are not authorization either. `@NotNull` ensures a property has a value; it does not ensure the caller has permission to assign that value. `@Min(1)` checks for a positive quantity; it does not prove stock is available.

Example DTO:

```java
public record CreateOrderRequest(
        @jakarta.validation.constraints.NotNull ProductCode productCode,
        @jakarta.validation.constraints.Min(1) int quantity
) {}
```

This is an illustrative model requiring a Bean Validation provider and validation trigger mechanism. Constraints check form values. Once validation passes, the application service still must look up the product, check permissions, and verify stock.

## 10. Using Converters with ConversionService and DataBinder

Registering a converter in `ConversionService`:

```java
DefaultConversionService conversions =
        new DefaultConversionService();
conversions.addConverter(new ProductCodeConverter());

ProductCode code =
        conversions.convert("ab-012", ProductCode.class);
```

This snippet uses `ProductCodeConverter` from the example. Conversion is invoked explicitly with no security context required.

With `DataBinder`:

```java
PurchaseForm target = new PurchaseForm();
DataBinder binder = new DataBinder(target, "purchaseForm");

DefaultConversionService conversions =
        new DefaultConversionService();
conversions.addConverter(new ProductCodeConverter());
binder.setConversionService(conversions);

MutablePropertyValues values = new MutablePropertyValues();
values.add("productCode", "ab-012");
binder.bind(values);

BindingResult result = binder.getBindingResult();
```

This integration snippet requires a `PurchaseForm` class with a setter accepting `ProductCode`. `DataBinder` converts types to assign properties and records binding errors if conversion fails. If validation is needed, register a validator and call `binder.validate()` or trigger validation in MVC; conversion does not automatically run all business rules.

With Spring MVC, converters for form/web binding can be registered via `WebMvcConfigurer.addFormatters(FormatterRegistry)`:

```java
@Configuration
class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
    }
}
```

This MVC configuration snippet requires imports and the converter class; place it within component scan scope. It only adds type conversion capability for the binder—it does not turn the converter into a business service.

**`@RequestBody` JSON is a separate flow:** JSON is usually deserialized by an HTTP message converter (such as Jackson). Registering a Spring Core `Converter` does not mean every JSON serializer/deserializer automatically uses it. Configure JSON mapping separately if the API requires it.

## 11. Classifying Errors by Stage

Applications should distinguish failures cleanly:

| Stage | Example | Common response |
| --- | --- | --- |
| Conversion | `"not-a-code"` fails pattern | 400 / `INVALID_PRODUCT_CODE` |
| Input validation | `quantity=0` | 400 / `QUANTITY_MUST_BE_POSITIVE` |
| Authentication | Unauthenticated | 401 or login flow |
| Authorization | Authenticated yet lacking permission | 403 or 404 per policy |
| Lookup | Valid code yet does not exist | 404 or domain error per contract |
| Business rule | Product inactive/out of stock | 409 or business error per contract |

Exact HTTP codes depend on the API and information disclosure policy. The key point is never turning “product not found” into `typeMismatch`: that is not a type conversion error.

### 11.1. Form Binding

When a converter throws an exception for a syntactically invalid string, Spring's binder can record a `FieldError`, often with generic code `typeMismatch`. The UI can display “Product code must match AB-123”.

If the converter succeeds yet the repository finds no record, the controller/service handles the lookup failure separately. Do not pretend it is a `ConversionFailedException` merely to reuse the same message.

### 11.2. Do Not Return Raw Rejected Values or Exceptions

`BindingResult` may retain the original `rejectedValue`. For sensitive fields, do not log or serialize the entire `FieldError`/`BindingResult` unfiltered. Create an error DTO containing only the necessary field/code/message and mask sensitive data.

## 12. Anti-Patterns and Fixes

### A. Converter Calling a Repository

```java
@Override
public Product convert(String source) {
    return productRepository.findByCode(source)
            .orElseThrow(ProductNotFoundException::new);
}
```

**Problem:** syntax and existence are conflated; conversion depends on the DB; binders trigger hidden queries.  
**Fix:** convert to `ProductCode`, then call the repository inside the application service.

### B. Converter Reading Security Context

```java
@Override
public ProductCode convert(String source) {
    User current = securityContextService.currentUser();
    authorizationService.checkCanUse(current, source);
    return new ProductCode(source);
}
```

**Problem:** conversion output depends on user and struggles to run outside HTTP.  
**Fix:** keep conversion independent; enforce authorization in the use case/service.

### C. Converter Mutating Data

```java
@Override
public OrderId convert(String source) {
    Order order = repository.findByCode(source).orElseThrow();
    order.setViewedAt(Instant.now());
    repository.save(order);
    return order.getId();
}
```

**Problem:** an unexpected binding/conversion step has side effects; rendering or retries can repeat mutations.  
**Fix:** converters only construct IDs/value objects; service commands perform write actions.

### D. Converter Doing All Validation

If `convert` parses, queries the DB, checks stock, checks permissions, and writes audit logs, errors lose clear boundaries and tests become hard to isolate. Separate parsing, Bean Validation, authorization policy, and domain/service rules.

### E. Treating “Convertible” as “Authorized/Usable”

```java
ProductCode code = conversionService.convert(input, ProductCode.class);
// Not enough conditions met to create an order.
orderRepository.create(code);
```

**Problem:** bypasses existence, permissions, and business state.  
**Fix:** the use case/service must verify all required conditions before mutating state.

## 13. Lookup, Caching, and Reference Data

Some applications have a small, stable code catalog. An immutable dictionary can be loaded into a dedicated service/cache. Distinguish carefully:

- **Conversion mapping:** static aliases, normalization rules, fixed code tables. This can be conversion configuration if it does not depend on user/request and carries no business state.
- **Reference data lookup:** codes checked against an authoritative catalog. This remains a lookup even when cached.
- **Authorization cache:** cached by principal/resource/permission with proper expiry and invalidation; not a conversion cache.
- **Business availability:** stock/price/status changes; caches require freshness/consistency policies.

Caching is purely a performance strategy. It does not change the category of responsibility. If a cached lookup expires or depends on tenant/user, it still must be handled at the service/persistence boundary.

## 14. Testing Each Layer Independently

A good test suite does more than assert end-to-end “order placed successfully”.

### 14.1. Converter Unit Tests

| Input | Expectation |
| --- | --- |
| `"ab-012"` | `ProductCode("AB-012")` |
| `" AB-012 "` | `ProductCode("AB-012")` |
| `"ZZ-999"` | Conversion succeeds even when the repository has no such code |
| `"ABC-12"` | Syntax error |
| `""` | Required error per example |
| `null` | Required error per example |

Key test: `ZZ-999` must parse successfully even though the repository does not contain that code. This proves the converter does not hit the database.

### 14.2. Authorization Unit Tests

Use the same product and swap principals/permissions. A user with the permission is allowed; a user lacking the permission is denied. There is no need to create different converters per user.

### 14.3. Repository/Service Tests

- Valid code yet product not found.
- Product exists yet is inactive.
- Product active yet quantity exceeds stock.
- Product belongs to another tenant.
- Caller lacks permission.
- Stock changes between lookup and order write (requires appropriate transactions/locking).

### 14.4. Endpoint Tests

Verify status codes and error bodies for conversion failure, validation failure, authentication, authorization, not found, and business conflicts. Never assert that all of them return `typeMismatch`.

## 15. Code Review Checklist

When reviewing a class implementing `Converter<S,T>`, ask:

1. Does `convert` depend only on the source and immutable configuration?
2. Are there any repositories, DAOs, HTTP clients, or network calls?
3. Does it read `SecurityContextHolder` or a principal?
4. Does it write to a DB, update audit logs, emit events, or cause side effects?
5. Does converting the same source multiple times produce consistent results?
6. Will it still work when run in a batch/job without a web request?
7. Are exceptions representation/type errors, or are they masking lookup/permission errors?
8. Is there a test proving a syntactically valid yet nonexistent code still converts successfully?
9. Is authorization invoked at the use case/action execution point?
10. Does data access enforce tenant/owner bounds and appropriate transactions?

A converter having persistence/security dependencies may not be a compile or framework error. The issue is responsibility: if `convert` needs that information to decide whether an action is permitted, the logic is likely in the wrong layer.

## 16. Self-Check

**1. `"AB-012"` is syntactically valid yet has no record. Should the converter throw “not found”?**  
No. It should create `ProductCode`; the repository/application service detects that no record exists.

**2. User A has permission, User B does not. Should the same input string convert differently?**  
No. Conversion does not depend on the principal. Authorization produces the differing outcome.

**3. Can a converter throw `IllegalArgumentException` when a string fails format rules?**  
Yes. That is a conversion failure because a valid target value cannot be built under the contract.

**4. Does `@Min(1)` guarantee the product has sufficient stock?**  
No. It checks the input quantity; availability requires inventory data and stock rules.

**5. What problems arise when a converter queries the database to verify an ID exists?**  
Conversion depends on persistent state, hidden queries run during binding, not-found errors get mixed with type mismatches, and reuse becomes difficult.

**6. Where should Spring Security method authorization be applied?**  
At the application service/entry point executing the use case; additional policies can also be checked on the resolved resource.

**7. Does caching a lookup turn lookup into conversion?**  
No. It remains a lookup/reference-data concern; caching is only a performance strategy.

**8. When should `Formatter<T>` be used instead of `Converter<S,T>`?**  
When `Locale`-aware parsing/printing is needed for the UI. A formatter still does not check permissions or query business data.

**9. Should a nonexistent product return `typeMismatch`?**  
No. `typeMismatch` is a binding/conversion error; not-found requires its own error code/domain exception.

**10. Can permissions be checked only in the frontend?**  
No. Frontend checks assist UX; the server must enforce authorization based on the actual principal and resource.

**Remember:** a converter answers **“can this value be converted into the target type?”**; authorization answers **“is this person allowed to perform that action?”**; repository/service answers **“does the data exist and does state satisfy business rules?”**. Keeping these three questions separate keeps conversion easy to test, errors accurate, and permissions enforced at the action point.

## Official References

- [Spring Framework 6.2 — Core Conversion Service](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Converter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/Converter.html)
- [Spring Framework 6.2 — ConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
