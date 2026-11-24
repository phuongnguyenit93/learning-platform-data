# Avoiding Sensitive Data Leaks and Cycles When Serializing Objects to JSON in Spring Boot

## 1. Why Is the JSON Response a Security Boundary?

A Spring Boot REST controller can return a Java object and let `HttpMessageConverter` serialize it into JSON. While convenient, objects in the data/business layer often contain **more information than the API is allowed to disclose**. Beyond sensitive data, bidirectional relationships like `Account -> Order -> Account` also form **object graphs with cycles**; the serializer can follow reference loops and fail.

Two separate questions must be answered:

1. **Which data is allowed to appear?** Should a user see `email`, `passwordHash`, `recoveryToken`, admin roles, payment details, or another user's data?
2. **How should the graph be shaped?** Does the API need a summary list of orders, or should it serialize the entire bidirectional JPA relationship? Avoid unbounded recursion, unintended lazy queries, massive payloads, and `StackOverflowError`.

**Safe default solution:** define **allowlist response DTOs**—declare only permitted fields, map from domain/entity to the DTO, and return only DTOs from controllers. Jackson annotations are supporting tools; they are not an authorization mechanism replacing checks at the service/security layer.

This lesson focuses on **Spring Boot 3.5.16 + Jackson 2 + Spring MVC + Java 17+** for consistent Maven/MockMvc examples. In Spring Boot 4.x, Jackson 3 is the default; the final section highlights differences to audit when upgrading.

## 2. Serialization Flow and Common Failure Points

~~~text
HTTP GET /api/accounts/42
         |
         v
Spring MVC selects Controller
         |
         v
Service loads Account domain/JPA entity
         |
         +-- id, displayName, email, passwordHash, recoveryToken
         |
         +-- orders: List<PurchaseOrder>
                           |
                           +-- id, sku, owner: Account
                                             |
                                             +-- orders -> ...
         |
         v
Controller selects return value
         |
         +-- Return domain/entity directly -> leaks fields + reference cycle
         |
         +-- Map to AccountView DTO -> only id, displayName,
                                         orders[id,sku]
         |
         v
MappingJackson2HttpMessageConverter (Boot 3.5, Spring MVC)
         |
         v
JSON per API contract, no secrets leaked and no infinite recursion
~~~

When a controller uses `@RestController` or `@ResponseBody`, Spring MVC typically selects an `HttpMessageConverter` based on return type and content negotiation. For JSON, Spring Boot 3.5 integrates Jackson 2 by default: public properties/getters, record components, and Jackson annotations govern the generated JSON structure.

**Note:** Jackson serializes the *representation of the returned object*; it does not inherently know which fields are business "secrets." A public `getPasswordHash()`, a newly generated Lombok getter, or a newly added entity association can silently alter responses if the controller returns domain objects directly.

In WebFlux, reactive JSON encoders/codecs execute a different pipeline, though property exposure and reference cycle risks when mapping objects with Jackson are similar. Do not conflate MVC's `HttpMessageConverter` name with all WebFlux codec implementations.

## 3. Two Distinct Risks to Separate

### 3.1. Unintended Data Exposure: Excessive Data Exposure

Example entity/domain class:

~~~java
public class Account {
    private long id;
    private String displayName;
    private String email;
    private String passwordHash;
    private String recoveryToken;
    // getters, setters, relationships ...
}
~~~

This snippet **only illustrates the model** and is not a standalone runnable file. Returning an instance with matching getters from a controller can include `passwordHash` or `recoveryToken` in JSON even if the frontend never renders them. Any API caller can inspect the raw response in network tools.

The issue persists even if:

- HTML/frontend does not display the sensitive fields.
- A route requires authentication, yet fails to enforce **property-level** or object-level authorization.
- The backend expects client-side JavaScript to strip fields after receiving JSON.
- The value is a hash rather than plaintext password: hashes aid offline cracking and must never be sent to clients.
- The field is currently empty/`null`: once populated later, a silent change exposes it.

Under OWASP API3:2023 (Broken Object Property Level Authorization), APIs must determine **which properties a requester is authorized to read/write**; avoid returning raw objects simply because serialization works out of the box.

### 3.2. Reference Cycles or Oversized Object Graphs

In a bidirectional relationship:

~~~text
Account(id=42)
  orders[0] -> PurchaseOrder(id=501)
                     owner -> Account(id=42)
                                 orders[0] -> ...
~~~

If Jackson traverses both directions, it repeatedly expands the same objects. Depending on annotations/mapper/converter settings, the outcome can be a `JsonMappingException` for infinite recursion or a `StackOverflowError`, typically causing HTTP 500 or an incomplete response.

An **acyclic** graph can still over-serialize if it spans thousands of entities, large collections, and lazy ORM relationships. Additional problems include:

- Related entity data outside the API scope.
- **N+1 queries** as Jackson invokes lazy relationship getters.
- `LazyInitializationException` or proxy errors after the session closes.
- Huge responses inflating heap/CPU/bandwidth and leaking unneeded metadata.
- Serialization accidentally triggering expensive computation or side effects inside getters.

**Breaking cycles does not stop secret leaks.** `@JsonIdentityInfo` replaces recursion with ID references, yet if the root object holds a password hash, the JSON still leaks that password hash.

## 4. Preferred Solution: Allowlist Response DTOs

Instead of returning `Account`, define a public schema:

~~~java
public record AccountView(
        long id,
        String displayName,
        List<OrderView> orders) {

    public record OrderView(long id, String sku) {
    }
}
~~~

This is a **DTO excerpt** without imports or mapping code. It includes only fields needed for the feature, omitting `email`, `passwordHash`, `recoveryToken`, and `Order.owner`. When the domain evolves, the public API **does not automatically sprout new fields**.

Advantages:

1. **Explicit allowlist:** API owners can review the exact contract directly on the DTO.
2. **Separation of concerns:** domains/entities model business logic and relations; DTOs represent client contracts.
3. **Cycle-free by design:** `OrderView` contains neither `AccountView` nor an `Account` domain object.
4. **Greater stability:** JPA relation edits, column renames, getters, or credential storage refactors do not silently mutate JSON.
5. **Easier testing:** assert the exact JSON field set per role/endpoint.
6. **Clear policy enforcement point:** before mapping the DTO, the service checks which account and fields the requester may read, then constructs the matching DTO.

Avoid doing this:

~~~java
// Anti-pattern example only: returning an object that may contain internal data.
@GetMapping("/api/accounts/{id}")
public Account getAccount(@PathVariable long id) {
    return accountService.load(id);
}
~~~

Even if some fields carry `@JsonIgnore`, the endpoint remains fragile against annotations and future domain additions. **A boundary DTO is a stronger structural barrier** than scattered annotations.

In multi-role systems, define explicit DTOs such as `PublicAccountView`, `OwnAccountView`, and `AdminAccountView`, constructing the right one only after authorization. Never allow clients to pass `?includeSecrets=true` or pick arbitrary sensitive properties.

## 5. Common Jackson Annotations and Their Limits

The annotations below belong to Jackson 2 package `com.fasterxml.jackson.annotation.*`. In Jackson 3 (default in Spring Boot 4.x), **the Jackson annotations module preserves this package** for compatibility; other Jackson databind/core libraries move to `tools.jackson.*`.

| Technique | Purpose | What It Does Not Solve |
|---|---|---|
| `@JsonIgnore` | Excludes logical property from JSON and normally ignores it on deserialization | Does not decide whether the user is authorized to read the record |
| `@JsonProperty(access = WRITE_ONLY)` | Allows reading from JSON during deserialization but omits when serializing | Does not hash passwords or scrub sensitive data from logs |
| `@JsonProperty(access = READ_ONLY)` | Allows serialization but ignores values from JSON input | Does not replace update permission checks in services |
| `@JsonIgnoreProperties({"x","y"})` | Ignores named properties on a class | Denylists easily miss newly added domain fields |
| `@JsonManagedReference`/`@JsonBackReference` | Marks forward/back links to skip serializing back-links | Does not filter sensitive data along the forward direction |
| `@JsonIdentityInfo` | Emits ID-based identity/references, reducing duplicate instances and recursion | Does not restrict object access; may expose internal IDs |
| `@JsonView` | Filters fields for designated JSON views | Does not enforce user/role authorization |
| `@JsonInclude(NON_NULL)` | Omits null values from JSON | Does not hide non-null secrets |
| `@JsonFilter` | Filters properties via configured serializer/filter provider | Error-prone if filters are not applied consistently |

### 5.1. @JsonIgnore for Never-Serialized Properties

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Account {
    private String passwordHash;

    @JsonIgnore
    public String getPasswordHash() {
        return passwordHash;
    }
}
~~~

This snippet **illustrates annotations**, separate from the runnable project in section 8. Under default Jackson property introspection, `getPasswordHash` is omitted from serialization. By default semantics, `@JsonIgnore` applies to the logical property, so it also affects deserialization; if your goal is **accepting a password on signup without returning it**, use a dedicated input DTO or `@JsonProperty(access = WRITE_ONLY)`.

Do not slap `@JsonIgnore` on a getter and assume every leak vector is closed: objects can still be logged via `toString()`, serialized by another library, or sent over systems ignoring Jackson annotations.

### 5.2. @JsonProperty(access = WRITE_ONLY) for Input-Only Fields

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record SignupRequest(
        String displayName,
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String password) {
}
~~~

From Jackson's perspective:

- `WRITE_ONLY`: Jackson can **write the value into the Java object during input deserialization**, but will not **read it from the object to write JSON**.
- `READ_ONLY`: the reverse—the property can be serialized, but is not populated from JSON input.

The terms read/write here are **from the Java property's perspective**, which often confuses people thinking from HTTP's perspective.

In production designs, `SignupRequest` is an input DTO and **should never be returned from an endpoint** even with `WRITE_ONLY`. Passwords must be processed with an appropriate password encoder and never logged in signup payloads. A `passwordHash` stored in the database/domain must never be returned.

Do not combine `@JsonIgnore` and `@JsonProperty(access=WRITE_ONLY)` on the same logical property without understanding Jackson annotation merging: `@JsonIgnore` can win and block input binding as well.

### 5.3. @JsonIgnoreProperties Is a Denylist, Not an Allowlist

~~~java
@JsonIgnoreProperties({"passwordHash", "recoveryToken"})
class InternalAccount {
    public String displayName;
    public String email;
    public String passwordHash;
    public String recoveryToken;
}
~~~

This is an **illustrative** snippet. Two properties are omitted, while `email` is still emitted. If next month adds `privateKey`, `apiToken`, or `isAdmin`, the denylist will not automatically hide them. Therefore, a DTO declaring only allowed fields provides more durable output control.

`@JsonIgnoreProperties(ignoreUnknown = true)` applies to **unknown input fields**; it does not hide sensitive fields during serialization. These are distinct settings and must not be conflated.

## 6. Approaches for Handling Object Cycles

### 6.1. Breaking Cycles with DTOs — Recommended Approach

If the domain has `Account.orders -> Order.owner -> Account`, the API only needs:

~~~json
{
  "id": 42,
  "displayName": "Mai",
  "orders": [
    {"id": 501, "sku": "BOOK-1"}
  ]
}
~~~

This JSON omits `owner` inside each order and omits sensitive fields. The DTO explicitly **defines the stopping point** for graph traversal. When another endpoint genuinely needs owner info, include an explicit summary containing allowed fields such as `ownerId` or `ownerDisplayName`, rather than embedding the full `Account`.

### 6.2. @JsonManagedReference / @JsonBackReference

For simple parent-child relationships, you can use:

~~~java
class Account {
    @JsonManagedReference("account-orders")
    private List<PurchaseOrder> orders;
}

class PurchaseOrder {
    @JsonBackReference("account-orders")
    private Account owner;
}
~~~

This is an **excerpt**, not a standalone compilable Java file; it requires imports/getters/constructors. `@JsonManagedReference` marks the forward link for normal serialization; `@JsonBackReference` marks the back-link to omit. During deserialization, Jackson can restore the back-reference on compatible properties.

**Important limitations:**

- Back-references belong on **bean-typed** properties, not collections/maps/arrays; e.g., `Order.owner` fits, whereas placing `@JsonBackReference` on `Account.orders` is the wrong direction.
- Multi-way relationships may require distinct **reference pair names**; one annotation pair per loop does not cleanly solve complex graphs.
- Sensitive fields on `Account` are still serialized along the forward direction.
- With JPA entities, the serializer can still trigger lazy loading.
- The serialized JSON omits the back-link, which may not fit every endpoint's contract.

Use DTOs for stable REST contracts; use the annotation pair only when serializing bidirectional models within tight, well-tested boundaries.

### 6.3. @JsonIdentityInfo and ID References

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id")
class Account {
    public long id;
    public List<PurchaseOrder> orders;
}
~~~

This **illustrates** identity handling and requires Jackson imports and `PurchaseOrder`. When related objects have valid identities and matching configuration, the serializer emits the full object once and uses its identifier on subsequent encounters rather than expanding infinitely.

However, `@JsonIdentityInfo` does not constrain the schema, does not hide `passwordHash`, and can leak internal IDs. If clients need an owner ID, **a transparent `OrderView(ownerId)` DTO is clearer** than relying on Jackson's reference ID semantics.

### 6.4. Do Not Use Global Serializer Tweaks to "Rescue" Unsafe Domains

Replacing `ObjectMapper`, enabling broad default typing/polymorphic deserialization, relaxing visibility, or stripping properties across entire packages can break unrelated endpoints. If a custom serializer is necessary:

- Restrict it to a **specific DTO type** rather than altering mapping for all objects.
- Avoid side effects and network/database I/O inside serializers.
- Test emitted fields, nested structures, error behavior, and performance.
- Never enable insecure default typing on untrusted JSON input. Polymorphic input should only allow an explicit subtype allowlist with secure configuration.

## 7. JPA/Hibernate: Why Returning Entities Directly Is Even Riskier

Spring Data JPA entities often have bidirectional associations:

~~~text
@OneToMany: User -> List<Order>
@ManyToOne: Order -> User
~~~

Returning entities from controllers can cause:

1. **Recursion** when getters traverse child collections and back-references.
2. **LazyInitializationException** if the serializer accesses a lazy relation outside a persistence context.
3. **N+1 queries** when serializing collections causes Hibernate to fetch each relation one by one.
4. **Data exposure** if the serializer walks into related entities carrying non-public fields.
5. **Proxies / Hibernate type metadata** causing unexpected JSON or serialization failures.
6. **Contract instability** when adding database columns or relations inadvertently alters API responses.

A cleaner flow:

~~~text
Controller
   -> Service checks object access permissions
      -> Repository queries needed data (projection/DTO/entity with fetch plan)
         -> Service maps to response DTO within appropriate transaction
            -> Controller returns DTO
               -> Jackson serializes only a finite DTO graph
~~~

When lazy relations are involved, the service should decide **when and how much to fetch**, via projections, `JOIN FETCH`, `@EntityGraph`, or dedicated queries. Never let the JSON serializer dictate database fetch plans.

In JPA projects, consider:

~~~properties
spring.jpa.open-in-view=false
~~~

This prevents the persistence context from remaining open throughout response rendering in many MVC architectures, though **it does not fix cycles, create DTOs, or eliminate N+1 queries by itself**. Map DTOs or resolve needed relations before the transaction/session closes.

`@JsonIgnore` on entities can act as defense-in-depth, but JPA mappings (`@OneToMany`, `@ManyToOne`, `FetchType.LAZY`) are neither authorization policies nor JSON contracts.

**Lombok `@Data` and other loops:** Lombok-generated `toString()`, `equals()`, and `hashCode()` on entities with bidirectional relations can also recurse infinitely even when JSON uses DTOs. Avoid `@Data` on complex JPA entity graphs, choose `equals`/`hashCode` fields deliberately, and use `@ToString.Exclude` where needed. `@ToString.Exclude` only affects `toString()` and **does not** prevent Jackson from serializing properties.

## 8. Complete Spring Boot 3.5.16, Java 17+ Example: Cyclic Domain, Safe DTO API

This example intentionally constructs a bidirectional domain `Account -> PurchaseOrder -> Account` and populates **dummy sentinel values** in private fields to verify responses do not leak them. It is not a real password store or production authentication/authorization system; it solely demonstrates the **JSON serialization boundary**.

### 8.1. File Structure

~~~text
safe-json-demo/
  pom.xml
  src/
    main/
      java/com/example/safejson/
        SafeJsonApplication.java
        Account.java
        PurchaseOrder.java
        AccountService.java
        AccountView.java
        AccountController.java
    test/
      java/com/example/safejson/
        AccountControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-json-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

The 3.5.16 line has been released; this example pins it to fix package names and Jackson 2, without claiming it is the latest release or within OSS support life. For new projects, pick an actively supported Spring Boot line and apply security patches.

### 8.3. Main Class

File `src/main/java/com/example/safejson/SafeJsonApplication.java`:

~~~java
package com.example.safejson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeJsonApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeJsonApplication.class, args);
    }
}
~~~

### 8.4. Domain Account with Non-Client Fields

File `src/main/java/com/example/safejson/Account.java`:

~~~java
package com.example.safejson;

import java.util.ArrayList;
import java.util.List;

public final class Account {
    private final long id;
    private final String displayName;
    private final String email;
    private final String passwordHash;
    private final String recoveryToken;
    private final List<PurchaseOrder> orders = new ArrayList<>();

    public Account(long id, String displayName, String email,
                   String passwordHash, String recoveryToken) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
        this.passwordHash = passwordHash;
        this.recoveryToken = recoveryToken;
    }

    public long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public String getPasswordHash() { return passwordHash; }
    public String getRecoveryToken() { return recoveryToken; }

    public List<PurchaseOrder> getOrders() {
        return List.copyOf(orders);
    }

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
    }
}
~~~

The getters for `email`, `passwordHash`, and `recoveryToken` exist for **illustrative domain logic**. They do **not imply permission to return them in the API**. This sample intentionally **omits** `@JsonIgnore` to demonstrate why DTOs form the critical security barrier rather than relying solely on domain annotations.

### 8.5. Domain PurchaseOrder Pointing Back to Account

File `src/main/java/com/example/safejson/PurchaseOrder.java`:

~~~java
package com.example.safejson;

public final class PurchaseOrder {
    private final long id;
    private final String sku;
    private final Account owner;

    public PurchaseOrder(long id, String sku, Account owner) {
        this.id = id;
        this.sku = sku;
        this.owner = owner;
    }

    public long getId() { return id; }
    public String getSku() { return sku; }
    public Account getOwner() { return owner; }
}
~~~

If an `Account` were serialized directly, Jackson would follow `getOrders()`, then `getOwner()`, looping back to the initial `Account`. `List.copyOf` only creates an unmodifiable snapshot list; it does **not** break cycles between objects.

### 8.6. Service Creating Demo Data and Handling Not Found

File `src/main/java/com/example/safejson/AccountService.java`:

~~~java
package com.example.safejson;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AccountService {
    public Account load(long id) {
        if (id != 42L) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Account not found");
        }

        Account account = new Account(
                42L, "Mai", "private@example.test",
                "DEMO_HASH_ONLY_NOT_REAL",
                "DEMO_TOKEN_ONLY_NOT_REAL");

        account.addOrder(
                new PurchaseOrder(501L, "BOOK-1", account));
        return account;
    }
}
~~~

The `DEMO_...` strings are test sentinel values, not real hashes or tokens. `AccountService` uses no database and **does not implement access checks yet**; in production, the service must verify whether the requester is authorized to view account ID 42 before returning data.

### 8.7. Response DTO and Mapper Selecting Only Public Fields

File `src/main/java/com/example/safejson/AccountView.java`:

~~~java
package com.example.safejson;

import java.util.List;

public record AccountView(
        long id,
        String displayName,
        List<OrderView> orders) {

    public record OrderView(long id, String sku) {
    }

    public static AccountView from(Account account) {
        List<OrderView> items = account.getOrders().stream()
                .map(order -> new OrderView(
                        order.getId(), order.getSku()))
                .toList();

        return new AccountView(
                account.getId(), account.getDisplayName(), items);
    }
}
~~~

**Decision point:** mapping from `PurchaseOrder` extracts only `id` and `sku`, **never passing `order.getOwner()`** into the response. The DTO holds no domain references, exposes no secret getters, and has no back-link, so serialization is bounded.

### 8.8. Controller Returns DTO, Not Account

File `src/main/java/com/example/safejson/AccountController.java`:

~~~java
package com.example.safejson;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {
    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/api/accounts/{id}")
    public AccountView getAccount(@PathVariable("id") long id) {
        Account account = accountService.load(id);
        return AccountView.from(account);
    }
}
~~~

The controller publishes its **response contract** via the `AccountView` return type. Adding new fields or relations to an entity will not automatically expand the response. When adding legitimate fields, deliberately update the DTO, mapper, and tests.

### 8.9. Run and Inspect Response

Requires JDK 17+ and Maven, in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If the project has a Maven Wrapper, use `./mvnw spring-boot:run` or `mvnw.cmd spring-boot:run` on Windows. With the server listening on default port 8080:

~~~bash
curl -sS http://localhost:8080/api/accounts/42
~~~

Expected logical JSON:

~~~json
{
  "id": 42,
  "displayName": "Mai",
  "orders": [
    {
      "id": 501,
      "sku": "BOOK-1"
    }
  ]
}
~~~

Jackson may emit compact single-line JSON; whitespace and field ordering are irrelevant to the test. What matters is that the JSON has **exactly three top-level keys** (`id`, `displayName`, `orders`) and **two keys per order item** (`id`, `sku`).

`email`, `passwordHash`, `recoveryToken`, and `owner` are absent; `DEMO_HASH_ONLY_NOT_REAL` and `DEMO_TOKEN_ONLY_NOT_REAL` never appear in the response. Because the DTO contains no back-reference, no recursion occurs even though the underlying domain graph has a cycle.

Try another ID:

~~~bash
curl -i http://localhost:8080/api/accounts/99
~~~

Expect HTTP 404 because the service throws `ResponseStatusException`. The exact error body depends on Spring Boot configuration rather than a fixed JSON shape defined by this demo.

## 9. MockMvc Verifies JSON Contract Safety

File `src/test/java/com/example/safejson/AccountControllerTest.java`:

~~~java
package com.example.safejson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AccountControllerTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void responseContainsOnlyApprovedFields() throws Exception {
        String body = mvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);
        assertEquals(3, root.size());
        assertEquals(42L, root.get("id").asLong());
        assertEquals("Mai", root.get("displayName").asText());

        JsonNode orders = root.get("orders");
        assertEquals(1, orders.size());
        JsonNode order = orders.get(0);
        assertEquals(2, order.size());
        assertEquals(501L, order.get("id").asLong());
        assertEquals("BOOK-1", order.get("sku").asText());

        assertFalse(root.has("email"));
        assertFalse(root.has("passwordHash"));
        assertFalse(root.has("recoveryToken"));
        assertFalse(order.has("owner"));
        assertFalse(body.contains("DEMO_HASH_ONLY_NOT_REAL"));
        assertFalse(body.contains("DEMO_TOKEN_ONLY_NOT_REAL"));
        assertFalse(body.contains("private@example.test"));
    }

    @Test
    void unknownAccountDoesNotReturnAnObject() throws Exception {
        mvc.perform(get("/api/accounts/99"))
                .andExpect(status().isNotFound());
    }
}
~~~

Run with Maven:

~~~bash
mvn test
~~~

These assertions serve three purposes:

- **Positive assertions:** clients receive the required data.
- **Schema allowlist:** exact key counts at each level ensure any newly leaked field is caught immediately.
- **Negative assertions:** neither sensitive field names, secret sentinels, nor `owner` references appear in JSON.

The test completes only if valid JSON is produced, practically proving **the cyclic domain graph does not trap the serializer in a loop** when mapped through DTOs. This test does not prove authentication/authorization correctness; production requires testing that user A cannot read objects or fields restricted to user B/admin.

**Do not only write `assertFalse(json.contains("password"))`:** the field name could be absent while the secret value leaks under another property name. Test **both JSON shape and dummy sensitive values**, and audit contracts by caller permissions.

## 10. Handling JSON Views, Dynamic Fields, and Varying Permissions

### 10.1. When Different Roles Need Different Responses

An API may have variants:

| Caller | Example DTO | Permitted Fields |
|---|---|---|
| Guest | `PublicAccountView` | Public ID, display name |
| Account owner | `OwnAccountView` | ID, display name, permitted email, minimal order list |
| Support agent | `SupportAccountView` | Only fields approved for support |
| Admin | `AdminAccountView` | Operational fields post-authorization, still excluding password hashes or secret tokens |

This mapping must sit behind **object-level authorization** and **property-level authorization**. Never send an admin DTO containing admin-only fields to regular users relying on the frontend to hide them.

`@JsonView` can serve different APIs, but easily grows tangled with view inheritance, default view inclusion, or `@ResponseBody` methods missing views. Sensitive fields should be isolated with separate DTOs/policies rather than treating `@JsonView` as an authorization system.

### 10.2. Dynamic Maps and JsonNode Also Need Allowlists

With:

~~~java
Map<String, Object> response = new HashMap<>();
response.putAll(domainProperties);
return response;
~~~

dynamically populated properties can leak unintended fields. Switching from an entity to `Map<String,Object>` **is not automatically safer** if all attributes are blindly copied.

When dynamic responses are needed, enforce an allowlist of keys and inspect every value including nested objects; never place an entity or secret-bearing object as a map value, because Jackson will serialize that nested object's contents.

### 10.3. Prevent Log/Trace Leaks Even When JSON Is Safe

Safe DTOs only protect the **response body at the API boundary**. Sensitive data can still leak via:

- `logger.info("account={}", account)` if `toString()` includes email/hash/token.
- Access logs, tracing, APM, or request/response logging filters that do not redact headers/bodies.
- Exception messages containing raw tokens or request payloads.
- JSON published to event queues, caches, or export jobs using domain objects instead of dedicated DTOs.
- Debug error endpoints accidentally returning stack traces, internal properties, or `cause`.
- Spring Actuator endpoints exposing config/data without access controls.

Apply **redaction**, restrict captured fields, use proper secret management, control log access, and test all outbound data paths. Never enable `logging.level.org.springframework.web=TRACE` or full HTTP body logging in production without evaluating PII/credential leaks.

## 11. Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning JPA `@Entity` directly | Can expose new fields, recursion, lazy-loading | Use allowlist response DTOs |
| Hiding fields only via CSS/frontend | Network response still leaks secrets | Omit fields on the backend before serialization |
| Assuming `@JsonIgnore` replaces authorization | Users can still access unauthorized objects or fields | Enforce service/security permissions + role-specific DTOs |
| Putting `@JsonBackReference` on a collection | Wrong parent/back-reference direction | Put back-reference on child -> parent bean |
| Using `@JsonIdentityInfo` to hide data | Limits recursion but can still leak fields/IDs | Use DTOs and policy-based field filtering |
| Relying on `@JsonInclude(NON_NULL)` | Non-null secrets are still serialized | Exclude secrets from response DTOs entirely |
| Assuming JPA `@Transient` always hides JSON | JPA persistence mapping differs from Jackson introspection | Use DTOs / proper JSON annotations |
| Using `@ToString.Exclude` to block JSON | Only affects `toString()`, not serialization | Use DTOs / Jackson annotations |
| Serializing lazy entities in controllers | N+1, `LazyInitializationException`, huge payloads | Fetch and map DTOs inside services |
| Using global mixins/serializers without tests | Breaks unrelated endpoints unexpectedly | Narrow scope and add contract tests |
| Custom `ObjectMapper` ignoring Boot auto-config | Drops modules, Java Time support, codecs, security settings | Use Boot's auto-configured mapper or builder customizer |
| Disabling Jackson `FAIL_ON_SELF_REFERENCES` to silence errors | Not a safe way to represent graphs | Break graphs via DTOs or tested identity/references |
| Building response DTOs from unauthorized entities | DTOs alone do not stop returning another account's data | Check object/field access before mapping |
| Testing only expected fields are present | Misses newly leaked secret fields | Assert both key allowlists and negative assertions |
| Using `@JsonProperty(WRITE_ONLY)` while logging passwords | JSON response may be safe while logs still leak | Never log credentials; redact and use separate input DTOs |

## 12. Jackson 2 on Spring Boot 3.5 vs. Jackson 3 on Boot 4.x

Spring Boot 3.5 uses **Jackson 2** with `com.fasterxml.jackson.databind.ObjectMapper`. The sample project above targets this environment using `spring-boot-starter-web`.

Spring Boot 4.x switches to **Jackson 3** as the default JSON mapper, using `tools.jackson.databind.json.JsonMapper` and reorganized starters/modules. Specifically:

- `com.fasterxml.jackson.annotation.JsonIgnore`, `JsonProperty`, `JsonManagedReference`, and `JsonBackReference` stay in package `com.fasterxml.jackson.annotation` via the compatibility annotations module.
- Databind/core imports and mapper creation/customization must be audited: many classes move from `com.fasterxml.jackson.*` to `tools.jackson.*`.
- Where Boot 3.5 uses `Jackson2ObjectMapperBuilderCustomizer`, Boot 4 introduces `JsonMapperBuilderCustomizer` and updated extension points.
- Jackson 2 compatibility support exists in Boot 4, but is deprecated; do not treat it as a long-term plan.
- Boot 4.x's Spring MVC starter adopts the clearer name `spring-boot-starter-webmvc`, and test imports/modules must be verified for the target version.
- Jackson 3 defaults can differ from Jackson 2; re-test exact schemas, null handling, polymorphism, Java Time, and nested references after upgrading.

**The security essence stays unchanged:** whether Jackson 2 or 3, only approved fields should appear in responses; DTOs and authorization are design decisions, while annotations are merely expression tools. Upgrading the mapper will not fix an endpoint returning entities that leak secrets.

## 13. Testing and Pull Request Review Checklist

Apply this checklist to any endpoint adding or modifying a JSON response:

1. **Inventory sensitive data:** passwords, `passwordHash`, recovery tokens, API keys, refresh tokens, PII, financial data, secret configs, operational internals.
2. **Define permissions:** who may view which objects and which properties? Enforce object-level and property-level authorization before mapping.
3. **Define the exact JSON schema contract:** return concrete DTOs; never expose entities or unbounded object graphs.
4. **Break bidirectional links:** nested objects use summary DTOs, approved IDs, or URIs; bound collections/depth/pagination.
5. **Audit ORM fetch plans:** avoid N+1, lazy serialization, side effects, and overly long open transactions.
6. **Review annotations:** understand exact semantics of `@JsonIgnore`, `WRITE_ONLY`, ref/identity/view—none are security policies.
7. **Positive & negative JSON tests:** assert expected keys, absence of extra keys, and absence of dummy secret sentinels.
8. **Test every role:** regular user, account owner, support, admin, unauthenticated user, unauthorized requester.
9. **Check errors and observability:** exception handlers leak no stack traces, logs/traces record no secrets, and health/management endpoints are secured.
10. **Test deep and large payloads:** pagination, max response sizes, no unbounded or infinitely looping graphs.
11. **Test migrations:** especially Jackson 2 → 3 and changes to getters/ORM relations.
12. **Preserve evidence:** API contracts, sample bodies, and CI test suites; update tests whenever adding fields or domain relations.

**Conclusion:** Preventing data leaks and preventing reference cycles are two independent requirements that converge at the **serialization boundary**. Always **authorize → choose a response DTO containing only allowed fields → map a finite object graph → serialize → run positive/negative tests**. `@JsonIgnore`, `@JsonBackReference`, and `@JsonIdentityInfo` help in specific cases, but never replace allowlist DTOs and authorization.

## References

- Spring Boot 3.5 — JSON mapping: https://docs.spring.io/spring-boot/3.5/reference/features/json.html
- Spring Boot 4.x — JSON, Jackson 3 as default: https://docs.spring.io/spring-boot/reference/features/json.html
- Spring Boot 4.0 Migration Guide — Jackson 3 and compatibility: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Framework — MVC Response Body / Message Converters: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Jackson 2 Javadoc — JsonIgnore: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html
- Jackson 2 Javadoc — JsonProperty.Access: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html
- Jackson 2 Javadoc — JsonManagedReference: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonManagedReference.html
- Jackson 2 Javadoc — JsonBackReference: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonBackReference.html
- Jackson 2 Javadoc — JsonIdentityInfo: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityInfo.html
- OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
- Spring Boot 3.5.16 Maven artifact: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent/3.5.16
