# Generics and Type Bounds to Prevent Mixing Semantically Different Data

## Learning Objectives

In Java applications, many values share the **same technical data type** while carrying **different business meanings**: customer IDs and order IDs may both be UUIDs; VND amounts and USD amounts may both be represented as BigDecimal; weight and distance may both be numeric. If every API accepts only String, UUID, or BigDecimal, the compiler lacks enough information to prevent accidental mix-ups.

**Generics** parameterize types, while **type bounds** specify which types are permitted in a shared API. Combining generics with **nominal domain types** (typically value objects) catches mistakes that mix semantically different data at compile time, rather than letting them surface only during database queries or writes.

This lesson belongs to the **Java Models** chapter of the **DATABASE_DATA_MODELING** module. The module's goal is to translate business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while knowing how to compare relational, document, graph, and analytical models to choose suitable, evolvable, and verifiable structures. This lesson focuses on **type boundaries in the Java model and preserving semantics when translating to the data model**.

After this lesson, you will be able to:

1. Explain generic types, type parameters, type arguments, **upper bounds**, and **multiple bounds** in Java.
2. Explain why generics **do not automatically create semantic distinction** when two domains both use String, UUID, or Number.
3. Design strongly typed **CustomerId**, **OrderId**, **Money**, **Quantity**, and **Repository** to prevent accidental data mix-ups.
4. Use the **E extends Identified<ID>** pattern to bind entities to their repository key types.
5. Distinguish **invariance**, **extends/super wildcards**, and the **PECS** principle when reading from or writing to typed collections.
6. Understand the limits of **type erasure**, raw types, unchecked casts, equality comparisons, and the difference between compile-time safety and runtime verification.
7. Know which protections belong in Java and which must still be enforced by **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, and database constraints.

> **Example version:** Code snippets use Java 17+ syntax, including records. They illustrate domain models and in-memory collections; they do not imply records are automatically JPA entities or that an in-memory repository replaces database transactions.

## 1. Same Technical Type Does Not Mean Same Meaning

Suppose an older API is written as follows:

~~~~java
import java.util.UUID;

class OrderServiceBad {
    void loadOrder(UUID orderId) {
        // Load order by id.
    }

    void changeCustomer(UUID orderId, UUID customerId) {
        // Reassign order to the specified customer.
    }
}
~~~~

The call below is **valid in Java**, even though the two arguments have swapped meanings:

~~~~java
UUID orderId = UUID.randomUUID();
UUID customerId = UUID.randomUUID();

OrderServiceBad service = new OrderServiceBad();
service.changeCustomer(customerId, orderId); // Compiles, yet semantically wrong.
~~~~

The compiler sees only two UUIDs. Because both values have valid UUID shapes, the bug may surface only when a query finds no row, updates the wrong row, or violates a foreign key. **Variable names help human readers, not compiler type checking on method calls.**

Similarly:

~~~~java
void transferAmount(java.math.BigDecimal amount);
void moveBy(java.math.BigDecimal distance);
~~~~

Nothing prevents passing a monetary amount into the distance parameter if the model only uses BigDecimal.

### Three Protection Layers for a Value

| Layer | Examples | What It Guarantees |
| --- | --- | --- |
| **Technical type** | UUID, String, BigDecimal | Representation and basic operations |
| **Domain type** | CustomerId, OrderId, Money, Distance | Semantics, invariants, and valid methods per concept |
| **Data constraint** | PK, FK, UNIQUE, CHECK in the DB | Existence, uniqueness, referential integrity, and correctness under concurrent writes |

The three layers **complement one another**. A well-designed CustomerId prevents accidentally passing an OrderId in Java; it **does not prove** that the customer actually exists in the database.

## 2. Generics Are Type Parameterization, Not Semantic Aliasing

### 2.1. An API Without Generics

~~~~java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList();
raw.add("KH01");
raw.add(123);

String customerCode = (String) raw.get(1); // ClassCastException at runtime.
~~~~

The **raw type** List (without a type argument) bypasses generic type protection. The compiler may warn, yet adding 123 to the raw list is still allowed.

### 2.2. Generic Declarations

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> customerCodes = new ArrayList<>();
customerCodes.add("KH01");

// customerCodes.add(123); // Compile error: Integer is not String.
String first = customerCodes.get(0);
~~~~

**List<E>** is a generic type with type parameter E. In **List<String>**, String is the *type argument*. The compiler knows this list accepts only String and returns String without manual casting.

Yet this is **still insufficient for semantic distinction**:

~~~~java
List<String> customerCodes = new ArrayList<>();
List<String> productCodes = new ArrayList<>();

productCodes.add("SP01");
customerCodes.add(productCodes.get(0)); // Still compiles: both are String.
~~~~

Generics guarantee the list holds String; they **do not know which String is a customer code and which is a product code**. To prevent mix-ups, define distinct domain types and pass those into generics.

### 2.3. Type Parameters and Type Arguments

~~~~java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

Box<String> name = new Box<>("Nguyễn An");
Box<Integer> quantity = new Box<>(3);
~~~~

In the declaration, **T** is an unspecified *type parameter*. At call sites, **String** and **Integer** are *type arguments*. The same Box template is reused across many types without duplicating code.

Notice the distinction: **Box<CustomerId> differs from Box<OrderId> during type checking**, whereas **Box<UUID> for a customer and Box<UUID> for an order are the exact same type Box<UUID>**.

## 3. Bounding Types with `extends`

An unbounded type parameter permits only operations Java knows every Object supports. When an API needs to invoke a specific capability, declare an **upper bound**.

### 3.1. A Single Upper Bound

~~~~java
interface Identified<ID> {
    ID id();
}

final class IdPrinter<E extends Identified<?>> {
    void print(E entity) {
        System.out.println(entity.id());
    }
}
~~~~

**E extends Identified<?>** states that E must implement Identified for some ID type. Consequently, code inside IdPrinter may call **entity.id()**.

In generic bounds, Java uses the keyword **extends** even when the bound is an **interface**:

~~~~java
class Example<T extends java.io.Serializable> {
    // T must implement Serializable.
}
~~~~

Never write **T implements Serializable** in a type parameter declaration.

### 3.2. Generic Methods and Multiple Bounds

~~~~java
final class Comparisons {
    static <T extends Number & Comparable<T>> T larger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }
}

Integer largerCount = Comparisons.larger(5, 8);
java.math.BigDecimal largerPrice = Comparisons.larger(
    new java.math.BigDecimal("10.50"),
    new java.math.BigDecimal("8.25")
);
~~~~

**T extends Number & Comparable<T>** requires T to satisfy both:

- Being a subtype of **Number**.
- Being comparable to **T itself** via Comparable<T>.

In a multiple-bound declaration, if **a class** is present, that class must be listed **first**; interfaces follow separated by **&**. Java does not permit a type parameter to extend two independent classes.

The upper bound guarantees **larger** can safely call **compareTo** on two arguments of the same T. However, Number does not distinguish "item quantity", "unit price", and "road meters". **Technical type bounds alone are not enough to protect domain meaning.**

### 3.3. Bounds Express Capability Contracts, Not Business Validation

For instance, a generic repository needs objects that expose **id()**; the bound E extends Identified<ID> expresses that contract accurately. By contrast, an API intended specifically for VND amounts should not merely accept **T extends Number**: that bound still permits unrelated numbers with completely different meanings.

The distinction:

- **Bound** answers: "What **capabilities** must E have?"
- **Domain type** answers: "What does this value **represent**?"
- **Business validation** answers: "Is this value **valid in the current context**?"

## 4. Creating Distinct Domain Types with `record`

Java uses **nominal typing** for classes and records. Two separate records are two distinct types, even when both wrap a UUID.

~~~~java
import java.util.Objects;
import java.util.UUID;

record CustomerId(UUID value) {
    CustomerId {
        Objects.requireNonNull(value, "customer id must not be null");
    }
}

record OrderId(UUID value) {
    OrderId {
        Objects.requireNonNull(value, "order id must not be null");
    }
}

record ProductId(UUID value) {
    ProductId {
        Objects.requireNonNull(value, "product id must not be null");
    }
}
~~~~

Here:

- **CustomerId** and **OrderId** have identical internal structure, yet **different Java types**.
- **new CustomerId(uuid)** cannot be passed directly to an OrderId parameter.
- Constructors reject null UUIDs, eliminating invalid domain states early.
- Records automatically provide equals/hashCode based on **record type and components**; a CustomerId never equals an OrderId just because both wrap the same UUID.

Example:

~~~~java
final class TypedOrderService {
    void changeCustomer(OrderId orderId, CustomerId customerId) {
        // Find order by OrderId and verify customer by CustomerId.
    }
}

UUID rawId = UUID.randomUUID();
OrderId orderId = new OrderId(rawId);
CustomerId customerId = new CustomerId(rawId);

TypedOrderService service = new TypedOrderService();
service.changeCustomer(orderId, customerId); // Type-safe.

// service.changeCustomer(customerId, orderId);
// Compile error: first parameter must be OrderId.
~~~~

Even when both wrappers hold the exact same UUID, the compiler distinguishes the identifier types. That is a major improvement over **changeCustomer(UUID, UUID)**.

### 4.1. Records Are Not Only a Trick to Prevent Argument Swaps

A value object is also where domain rules belong:

~~~~java
record CustomerCode(String value) {
    CustomerCode {
        Objects.requireNonNull(value);
        if (!value.matches("KH[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid customer code");
        }
    }
}
~~~~

Suppose the domain requires customer codes formatted as **KH0001**; malformed codes are rejected immediately when constructing CustomerCode. This is an **illustrative example rule**, not a universal code standard.

Note: records provide simple immutability and **component-reference** finality, yet if a component is a mutable object (such as an array), a record **does not automatically provide deep immutability**. Choose immutable component types or copy defensively when needed.

## 5. Generic Repositories Bounding Both Entity Type and Key Type

Here is a key example of applying generics **after separating domain identifiers**.

### 5.1. Entity Contract

~~~~java
interface Identified<ID> {
    ID id();
}

record Customer(CustomerId id, String name)
        implements Identified<CustomerId> {
    Customer {
        Objects.requireNonNull(id);
        Objects.requireNonNull(name);
    }
}

record Order(OrderId id, CustomerId customerId,
             java.math.BigDecimal total)
        implements Identified<OrderId> {
    Order {
        Objects.requireNonNull(id);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(total);
        if (total.signum() < 0) {
            throw new IllegalArgumentException("Total must be nonnegative");
        }
    }
}
~~~~

**Customer** has an id of type **CustomerId**. **Order** has an id of type **OrderId** while also holding **customerId** to reference the customer. These two roles never get mixed up just because both hold UUIDs underneath.

### 5.2. Bounded Generic Repository

~~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class Repository<E extends Identified<ID>, ID> {
    private final Map<ID, E> rows = new HashMap<>();

    void save(E entity) {
        rows.put(entity.id(), entity);
    }

    Optional<E> findById(ID id) {
        return Optional.ofNullable(rows.get(id));
    }

    boolean existsById(ID id) {
        return rows.containsKey(id);
    }
}
~~~~

Declaring **E extends Identified<ID>** establishes a strict link between **entity type E** and **key type ID**. Consequently, Repository knows entity.id() returns ID and Map<ID,E> can never mix mismatched entities or keys.

### 5.3. Usage

~~~~java
import java.math.BigDecimal;
import java.util.UUID;

Customer customer = new Customer(
    new CustomerId(UUID.randomUUID()), "Nguyễn An"
);
Order order = new Order(
    new OrderId(UUID.randomUUID()),
    customer.id(),
    new BigDecimal("95000.00")
);

Repository<Customer, CustomerId> customers = new Repository<>();
Repository<Order, OrderId> orders = new Repository<>();

customers.save(customer);
orders.save(order);

Customer foundCustomer = customers.findById(customer.id()).orElseThrow();
Order foundOrder = orders.findById(order.id()).orElseThrow();

// orders.findById(customer.id());
// Compile error: finding an Order requires OrderId, not CustomerId.

// orders.save(customer);
// Compile error: Repository<Order, OrderId> does not accept Customer.

// new Order(order.id(), order.id(), new BigDecimal("10"));
// Compile error: second parameter of Order must be CustomerId.
~~~~

Combining **nominally typed ID records** with **Repository<E, ID>** ensures both the service layer and the in-memory storage layer enforce "which entity type goes with which key type".

> **Scope of this example:** This Repository is an in-memory Map, **with no transactions, FKs, authorization, concurrency control, durability, or customer-existence verification**. It illustrates only the type contract. In real applications, a JDBC/JPA adapter or another storage implementation must fulfill those persistence responsibilities.

## 6. Designing Generic APIs Without Losing Semantic Boundaries

### 6.1. Do Not Replace Domain IDs with a Single Generic Type

A repository interface that looks general yet erases boundaries:

~~~~java
import java.util.UUID;

interface BadRepository<E> {
    E find(UUID id);
}
~~~~

Every repository accepts UUID, so customers and orders can once again be queried with the wrong domain's UUID. Instead:

~~~~java
interface TypedRepository<E, ID> {
    java.util.Optional<E> findById(ID id);
    void save(E entity);
}
~~~~

Declaring **TypedRepository<Order, OrderId>** pins the accepted key type. To also ensure entity.id() returns the same type, add the bound:

~~~~java
interface BoundedRepository<E extends Identified<ID>, ID> {
    java.util.Optional<E> findById(ID id);
    void save(E entity);
}
~~~~

Pairing **distinct domain types** with **generic bounds** matters more than using either one alone.

### 6.2. Generic Bounds Do Not Force Two Type Arguments to Differ

The declarations:

~~~~java
Repository<Customer, CustomerId> customers = new Repository<>();
Repository<Order, OrderId> orders = new Repository<>();
~~~~

only produce two differently constrained repositories **because CustomerId and OrderId are already distinct types**. If both entities declared **Identified<UUID>**, both generic repositories would use ID=UUID, and the compiler could not prevent passing one entity's UUID where the other is expected.

This is a fundamental design rule:

> **To protect business semantics, represent the distinction in the type system itself.** Generics preserve and propagate distinctions; they do not invent meaning for two values of the same type.

### 6.3. A Shared Type Parameter Can Be Inferred Too Broadly

Example:

~~~~java
final class Pairing {
    static <T> boolean equal(T left, T right) {
        return java.util.Objects.equals(left, right);
    }
}

boolean result = Pairing.equal(
    new CustomerId(UUID.randomUUID()),
    new OrderId(UUID.randomUUID())
);
// Still compiles: T can be inferred as a common supertype.
~~~~

Never assume **two parameters sharing symbol T must have the exact same concrete domain type** on every generic method call. Java can infer a **broader common supertype** for T, such as Object.

When an API should genuinely compare only two OrderIds, write a fixed signature:

~~~~java
static boolean sameOrder(OrderId a, OrderId b) {
    return a.equals(b);
}
~~~~

Or pin T on the **receiving object** and its instance methods, rather than letting the compiler infer T from two unrelated arguments.

### 6.4. Return Types Must Also Bind to Input Types

An API taking CustomerId but returning Object forces callers to cast and throws away much of the benefit:

~~~~java
Object findCustomerBad(CustomerId id);
~~~~

The API should reflect its contract:

~~~~java
java.util.Optional<Customer> findCustomer(CustomerId id);
~~~~

Or use a generic repository with fixed **E** and **ID**. **Optional<Customer>** models the possibility of not finding a customer while preserving the return type; Optional **does not prove a customer exists**—it simply handles absence explicitly.

## 7. Invariance: Why `List<Order>` Is Not a `List<Identified<?>>`

Java generics are **invariant** in their type arguments. Suppose Order implements Identified<OrderId>:

~~~~java
import java.util.ArrayList;
import java.util.List;

List<Order> orderList = new ArrayList<>();

// List<Object> objects = orderList;             // Compile error.
// List<Identified<?>> entities = orderList;     // Compile error.
~~~~

Reason: if List<Order> were treated as List<Object>, someone could insert a Customer into that list, breaking the guarantee that every element is an Order.

Distinguish:

- **Order** may be a subtype of Identified<OrderId>.
- **List<Order>** does not thereby become a subtype of **List<Identified<OrderId>>**.
- To accept a list of subtypes of an interface for **reading**, use wildcards.

### 7.1. `extends` Wildcard: Reading from a Family Sharing a Contract

~~~~java
import java.util.List;

final class IdReporting {
    static void printIds(List<? extends Identified<?>> entities) {
        for (Identified<?> entity : entities) {
            System.out.println(entity.id());
        }

        // Cannot add an arbitrary Customer or Order to entities:
        // the concrete element type is hidden by wildcard capture.
    }
}

List<Order> allOrders = new ArrayList<>();
List<Customer> allCustomers = new ArrayList<>();

IdReporting.printIds(allOrders);
IdReporting.printIds(allCustomers);
~~~~

**? extends Identified<?>** accepts lists of any entity type exposing id(), enabling shared reporting logic. Because the wildcard hides the exact element type, the method cannot arbitrarily insert an Order or Customer into the list.

**Distinguish the two question marks:** The outer wildcard stands for any element type implementing Identified; the inner wildcard says the entity's ID type is also unknown. Thus the report may only print id, and **must never assume every id is an OrderId**.

### 7.2. `super` Wildcard: Writing Objects into a Target That Can Accept Them

~~~~java
import java.util.List;

final class Collecting {
    static void addCustomer(List<? super Customer> target, Customer value) {
        target.add(value);
    }
}

List<Customer> customers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

Collecting.addCustomer(customers, customer);
Collecting.addCustomer(objects, customer);
~~~~

**? super Customer** means the list accepts Customer or a supertype of Customer. We can **add Customer**, yet when reading elements out we can generally only treat them as Object because the exact element type of the list is unknown.

### 7.3. The PECS Rule

**PECS** stands for *Producer Extends, Consumer Super*:

- **Source producing values to read:** typically **? extends T**.
- **Target consuming values to write:** typically **? super T**.
- **Both reading exact T and writing T:** typically concrete T without wildcards.

Copying example:

~~~~java
static <T> void copy(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~~

However, **PECS is a collection API rule, not a proof that two domain types share the same meaning**. A generic reporting helper can read across many entity types; a business operation creating an order needs concrete signatures so a customer can never be mistaken for an order.

### 7.4. Wildcards Do Not Fit Every Store Operation

If an API declares:

~~~~java
void saveAny(Identified<?> value);
~~~~

it accepts any entity type and loses the guarantee that an Order store accepts only Orders. Critical write APIs should pin **E** and **ID** via repository type parameters or concrete signatures instead of overusing wildcards.

## 8. Type Erasure: Compile-Time Safety Is Not Runtime Type Identity

In Java, most generic type-argument information is **erased at runtime** (*type erasure*). This preserves compatibility with older Java libraries while introducing important constraints.

### 8.1. Two Lists with Different Type Arguments Share the Same Runtime Class

~~~~java
List<CustomerId> customerIds = new ArrayList<>();
List<OrderId> orderIds = new ArrayList<>();

System.out.println(customerIds.getClass() == orderIds.getClass());
// true: both are ArrayList at runtime.
~~~~

You cannot write:

~~~~java
// if (value instanceof List<CustomerId>) { ... }
// Invalid: concrete type arguments cannot be checked this way.
~~~~

You can check **value instanceof List<?>** because an unbounded wildcard needs no runtime element type; to verify every element has the right type, inspect elements individually using appropriate runtime checks.

### 8.2. Cannot Call `new T()` Directly

~~~~java
class Creator<T> {
    // T make() { return new T(); } // Does not compile.
}
~~~~

At runtime, T's constructor is unknown and Java does not guarantee T has a no-arg constructor. When instantiation is needed, pass a **factory**:

~~~~java
import java.util.function.Supplier;

final class Creator<T> {
    private final Supplier<T> factory;

    Creator(Supplier<T> factory) {
        this.factory = factory;
    }

    T make() {
        return factory.get();
    }
}

Creator<CustomerId> idCreator =
    new Creator<>(() -> new CustomerId(UUID.randomUUID()));
CustomerId newId = idCreator.make();
~~~~

If runtime type checks or conversions are needed, pass **Class<T>** or an explicitly typed codec. Never expect type parameter T to survive intact at runtime.

### 8.3. Danger of Generic Typed IDs Without a Runtime Tag

Suppose a designer tries to reduce ID record boilerplate with a single template:

~~~~java
record NaiveId<T>(UUID value) {}

UUID same = UUID.randomUUID();
NaiveId<Customer> customerId = new NaiveId<>(same);
NaiveId<Order> orderId = new NaiveId<>(same);

// Cannot pass NaiveId<Customer> directly to an API expecting NaiveId<Order>.
// Yet the expression below evaluates to true:
System.out.println(customerId.equals(orderId)); // true
~~~~

Why does **equals** return true? Both values share the **same runtime NaiveId record class** and the same UUID component. The **Customer/Order** type argument is not stored as a record component; it is erased from runtime identity.

This becomes dangerous if IDs are compared generically, used as keys in an untyped Map, or passed through raw/unchecked APIs. It is a classic illustration that **compile-time safety alone does not preserve domain distinction once generic information is erased**.

### 8.4. Two Solutions for Typed IDs

**Option A — Separate records per domain:** CustomerId, OrderId, ProductId as in Section 4. This is usually the clearest, simplest, and safest choice even for equals comparisons.

**Option B — Generic ID carrying a runtime tag:**

~~~~java
import java.util.Objects;
import java.util.UUID;

interface EntityKind {}

final class CustomerKind implements EntityKind {
    private CustomerKind() {}
}

final class OrderKind implements EntityKind {
    private OrderKind() {}
}

record TaggedId<K extends EntityKind>(Class<K> kind, UUID value) {
    TaggedId {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(value, "value");
    }
}

UUID shared = UUID.randomUUID();
TaggedId<CustomerKind> c = new TaggedId<>(CustomerKind.class, shared);
TaggedId<OrderKind> o = new TaggedId<>(OrderKind.class, shared);

System.out.println(c.equals(o)); // false: kind is also a record component.
~~~~

Thanks to **Class<K> kind**, the ID value carries domain-distinguishing information at runtime. When using it, ensure every ID construction path supplies the matching kind; raw types or unchecked casts can still break the contract in unsafe code.

You do not need TaggedId in every project. When there are only a handful of ID types, dedicated records are usually **less complex and cleaner to read in DTOs, APIs, and logs**. When there are dozens of identifier types and broad generic infrastructure, TaggedId can be worth considering.

### 8.5. Raw Types and Unchecked Casts Punch Holes in the Guardrail

~~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(Repository<Order, OrderId> typed, Customer customer) {
    Repository raw = typed;
    raw.save(customer); // Bypasses compiler generic checks.
}
~~~~

This method is **not recommended coding practice**. It demonstrates how raw types and unchecked operations can slip a Customer into an in-memory Order repository. The bug may only surface later when reading, casting, or processing data.

Eliminate raw types, minimize **@SuppressWarnings("unchecked")**, and isolate any unavoidable unsafe conversions inside small, tested adapters rather than letting them leak into domain code.

## 9. Generics Are Not Only for IDs: Currencies and Units of Measure

A sound data model separates values that share numeric types yet differ in meaning. Using BigDecimal or **T extends Number** alone cannot enforce that distinction.

### 9.1. Money Is a Value Pairing Amount and Currency

~~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    Money plus(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException(
                "Cannot add amounts in different currencies"
            );
        }
        return new Money(amount.add(other.amount()), currency);
    }
}

Money vndA = new Money(
    new BigDecimal("120000"), Currency.getInstance("VND")
);
Money vndB = new Money(
    new BigDecimal("30000"), Currency.getInstance("VND")
);
Money usd = new Money(
    new BigDecimal("10.00"), Currency.getInstance("USD")
);

Money sum = vndA.plus(vndB); // 150000 VND.
// vndA.plus(usd); // Compiles; rejected at runtime.
~~~~

With **Money**, the currency is stored as a **runtime value**. The constructor guarantees amount and currency are non-null; plus guarantees matching currencies. Generics are not mandatory in every situation: sometimes a **value object holding a unit and performing runtime checks** is the simplest model.

Never silently add VND and USD using an implicit exchange rate. If the business requires currency conversion, use an explicit conversion function with a **rate, rate source, effective timestamp, and rounding policy**. Those are business data, not something derivable from BigDecimal alone.

### 9.2. Phantom Types: Using Type Parameters as Semantic Tags

To distinguish units of measure at **compile time**, you can use marker types:

~~~~java
import java.math.BigDecimal;
import java.util.Objects;

interface MeasureUnit {}

final class Kilogram implements MeasureUnit {
    private Kilogram() {}
}

final class Meter implements MeasureUnit {
    private Meter() {}
}

record Quantity<U extends MeasureUnit>(BigDecimal value) {
    Quantity {
        Objects.requireNonNull(value);
    }

    Quantity<U> plus(Quantity<U> other) {
        return new Quantity<>(value.add(other.value()));
    }
}

Quantity<Kilogram> weight = new Quantity<>(new BigDecimal("2.5"));
Quantity<Kilogram> extraWeight = new Quantity<>(new BigDecimal("1.2"));
Quantity<Meter> length = new Quantity<>(new BigDecimal("5.0"));

Quantity<Kilogram> totalWeight = weight.plus(extraWeight);

// weight.plus(length);
// Compile error: Quantity<Meter> is not Quantity<Kilogram>.
~~~~

Type parameter **U** is never used in value computations; it serves purely as a **type tag**. This pattern is commonly called a **phantom type**.

Understand its limitations:

- Due to **type erasure**, U is absent as a runtime component of record Quantity.
- Two Quantity instances with different units but identical BigDecimal values can have **equals return true**, just like NaiveId in Section 8.
- Data read from JSON or a DB must be assigned the **correct unit type** by the adapter; the compiler cannot tell on its own whether a raw number was measured in kg or m.
- When units must be stored or checked at runtime, include an explicit **unit token**, enum, or value object rather than relying solely on a phantom type.

Therefore, choosing between **Money with runtime Currency** and **Quantity<U> with a compile-time generic tag** depends on requirements: where unit data is stored, whether unit conversions occur, and how strongly mix-ups must be prevented.

### 9.3. Bounds Do Not Replace Value Constraints

**T extends Number** guarantees T has numeric/conversion methods, yet it never checks:

- Order quantities must be **greater than 0**.
- Discount percentages must lie within **0–100%**.
- Prices must be non-negative.
- Money and quantities must not be added together.

These rules belong in the appropriate **constructors, domain methods, and DB constraints**. For instance:

~~~~java
record OrderQuantity(int value) {
    OrderQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
~~~~

OrderQuantity is a dedicated domain type that prevents confusion with unrelated ints whenever an API requires OrderQuantity, while guaranteeing positivity whenever constructed validly.

## 10. Preserving Semantics When Mapping Java to SQL

A **strongly typed Java model** and a **keyed relational schema** must be designed together. Java type safety verifies **calls and object structure**; the database verifies **persisted state, keys, references, and transaction concurrency**.

### 10.1. Same UUID Type in SQL, Different Meanings

~~~~sql
CREATE TABLE customer (
    id UUID PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE sales_order (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    total NUMERIC(14, 2) NOT NULL CHECK (total >= 0),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
        ON DELETE RESTRICT
);
~~~~

From the physical standpoint:

- customer.id and sales_order.id are both **UUID**.
- sales_order.customer_id is also **UUID** and references customer.id.
- The DB does not create Java's **CustomerId** and **OrderId** classes; the adapter maps those wrappers to and from UUID.

From the Java standpoint:

~~~~text
Customer.id       : CustomerId
Order.id          : OrderId
Order.customerId  : CustomerId

CustomerId.value  : UUID
OrderId.value     : UUID
~~~~

**Java types** prevent passing an **OrderId** to a parameter expecting **CustomerId**. **SQL FKs** prevent inserting a customer_id that does not exist in customer (unless data policies are intentionally designed otherwise). **PRIMARY KEYs** on both tables protect uniqueness within each relation. Both verification layers matter.

### 10.2. A JDBC Write Example with Explicit Unwrapping

~~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

static void insertOrder(Connection connection, Order order)
        throws SQLException {
    String sql = """
        INSERT INTO sales_order (id, customer_id, total)
        VALUES (?, ?, ?)
        """;
    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, order.id().value());
        statement.setObject(2, order.customerId().value());
        statement.setBigDecimal(3, order.total());
        statement.executeUpdate();
    }
}
~~~~

This example uses JDBC with a PostgreSQL driver supporting UUIDs. In production, UUID binding and database type mapping must match your JDBC driver and application error policies.

Crucial point: the adapter passes **order.id().value()** for column id and **order.customerId().value()** for column customer_id. If a mapping bug mistakenly passed **order.id()** into customer_id, Java cannot catch it because by the time setObject runs, both wrappers have been **unwrapped** to UUID. That is why adapters require **mapping tests** and the DB must keep its FK.

### 10.3. DTO/JSON Is an Untrusted Boundary

An HTTP/JSON request typically starts as Strings:

~~~~java
record CreateOrderRequest(String customerId, String total) {}

static CustomerId parseCustomerId(CreateOrderRequest request) {
    return new CustomerId(
        java.util.UUID.fromString(request.customerId())
    );
}
~~~~

A user can send a syntactically valid UUID belonging to a **non-existent entity** or one they lack permission to access. Therefore the pipeline must separate:

1. **Structural parse/validation:** is the UUID properly formatted?
2. **Domain type conversion:** CustomerId rather than raw String or bare UUID.
3. **Business/authorization check:** is the caller allowed to place an order for that customer?
4. **DB enforcement:** FKs, locks, and transactions protect data even under concurrent requests.

Never rely solely on a pre-INSERT existence check in Java: under concurrency, the referenced row can be deleted or updated between check and write. Database constraints and transactions form the final line of defense for referential integrity.

### 10.4. JPA and Frameworks Do Not Automatically Understand Semantic Wrappers

At the domain-model level, records like CustomerId and OrderId express immutable identifiers cleanly. Mapping them to SQL columns may require an **AttributeConverter, custom mapping, or adapter** depending on your JPA provider and version. Never assume every framework natively supports record IDs or generic IDs.

Nor should you infer from the Customer and Order record examples that records can directly serve as **standard JPA entities**: JPA entities impose specific requirements on classes, constructors, mutability/proxies, and lifecycle management. An architecture can keep **records as domain models/DTOs** alongside **separate persistence entity classes** with tested mappings between layers.

When using generic repository-generation libraries, check whether **ID types in the effective API** get collapsed to Object, Serializable, UUID, or String. If so, ensure the domain layer still prevents mismatched calls.

## 11. Scoped IDs: Tenants and Composite Keys

Another real-world concern is uniqueness scoped to a **business boundary**. For example, department code **KT** can exist across multiple tenants.

~~~~java
import java.util.Objects;
import java.util.UUID;

record TenantId(UUID value) {
    TenantId {
        Objects.requireNonNull(value);
    }
}

record DepartmentCode(String value) {
    DepartmentCode {
        Objects.requireNonNull(value);
        if (value.isBlank()) {
            throw new IllegalArgumentException("Department code required");
        }
    }
}

record DepartmentKey(TenantId tenantId, DepartmentCode departmentCode) {
    DepartmentKey {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(departmentCode);
    }
}
~~~~

**DepartmentKey** represents a composite identifier **(tenantId, departmentCode)**. It prevents dropping tenantId when looking up a department.

Corresponding relational schema:

~~~~sql
CREATE TABLE department (
    tenant_id UUID NOT NULL,
    department_code VARCHAR(30) NOT NULL,
    department_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (tenant_id, department_code)
);

CREATE TABLE employee (
    tenant_id UUID NOT NULL,
    employee_code VARCHAR(30) NOT NULL,
    department_code VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, employee_code),
    FOREIGN KEY (tenant_id, department_code)
        REFERENCES department(tenant_id, department_code)
);
~~~~

**A generic tag on DepartmentId only distinguishes entity kinds**, whereas **DepartmentKey** captures the **tenant value** itself. Java has no static way to mint a distinct type argument for **every tenant UUID discovered at runtime**. Therefore, to protect tenant isolation, embed tenantId in the key, enforce composite FKs, and perform tenant/authorization checks in services and related safeguards.

Mistake to avoid: passing **DepartmentCode** (or TaggedId<DepartmentKind>) alone and assuming it proves an employee belongs to the right tenant. The "department" type and **membership in a specific tenant's department** are two separate pieces of information.

## 12. Common Pitfalls in Generics and Java Modeling

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| All IDs are UUIDs, distinguished only by variable names | Variable names are not type barriers on method calls | Create CustomerId, OrderId, and domain-typed signatures |
| Using Repository<E> with ID always fixed to UUID | Fails to separate UUIDs across domains | Use Repository<E, ID> with distinct ID types |
| Thinking T extends Number separates money from distance | Bounds only guarantee technical numeric capabilities | Use Money, Distance, Quantity, or appropriate value objects |
| Using the same T for two method parameters assuming identical concrete classes | Type inference may pick a common supertype | Pin concrete domain types on APIs or generic receivers |
| Using List<Object> to collect everything | Loses element type information, requires casts | Use shared interfaces and read-only wildcards |
| Using `extends` wildcards to insert elements into a list | Exact element type is unknown | Use concrete types or `super` wildcards for consumers |
| Using a generic ID wrapping only UUID expecting `equals` to separate kinds | Type arguments are erased at runtime | Separate ID records or include a runtime kind tag |
| Using raw types and arbitrary unchecked casts | Bypasses type checking, causes delayed failures | Remove raw types and isolate unavoidable conversions |
| Assuming records are deeply immutable | Mutable array/object components can still change | Use immutable components or defensive copying |
| Assuming Java type safety proves customerId exists | Right type does not prove the referenced row exists | DB FKs and business/transactional validation |
| Using one DepartmentCode across all tenants | Missing tenant scope | Use DepartmentKey pairing tenantId and departmentCode |
| Storing all IDs in Map<Object,Object> | Mixes entities, loses type constraints | Stores with concrete E and ID, plus tested mappings |
| Using auto-converters without mapping tests | Wrappers can unwrap into the wrong UUID column | Test JDBC/JPA adapters and enforce DB constraints |
| Implicitly converting currencies by adding BigDecimals | Ignores currency units, rates, and rounding | Use Money and explicit semantic conversion |

### 12.1. Type Erasure Affects Overloading

These **two signatures cannot coexist** in the same Java class:

~~~~java
// void handle(List<CustomerId> ids) { ... }
// void handle(List<OrderId> ids) { ... }
// Compile error due to identical parameter erasure: List.
~~~~

Because type arguments are erased in runtime method signatures, the two overloads cause a **name clash**. Instead:

~~~~java
void handleCustomers(List<CustomerId> ids) { /* ... */ }
void handleOrders(List<OrderId> ids) { /* ... */ }
~~~~

Or use a generic handler interface whose type parameter is fixed per implementation with a **single method name**, when the business workflow is genuinely shared across domains.

Unlike generic List overloads, overloads on **direct wrappers** are valid:

~~~~java
void load(CustomerId id) { /* ... */ }
void load(OrderId id) { /* ... */ }
~~~~

Here CustomerId and OrderId are **two distinct runtime classes**, not erased to UUID.

### 12.2. Never Use `instanceof` with Concrete Type Arguments

~~~~java
Object value = new ArrayList<CustomerId>();

if (value instanceof List<?>) {
    // Only proves it is a List, not that elements are CustomerId.
}
~~~~

When receiving data from generic frameworks, inspect elements individually or use a decoder given **explicit type metadata**. An unchecked cast from Object to List<CustomerId> never turns wrong contents into right contents.

### 12.3. A Domain Model Is Not a 1:1 Copy of Tables

Every SQL column does not need its own Java class, nor does every value object need its own table. For example:

~~~~text
Java:
  OrderId(UUID)
  CustomerId(UUID)
  Order(id: OrderId, customerId: CustomerId, total: BigDecimal)

SQL:
  sales_order(id UUID PK, customer_id UUID FK, total NUMERIC)
~~~~

Two ID value objects can map to **two UUID columns**. Conversely, one **DepartmentKey** containing TenantId and DepartmentCode can map to a **two-column composite PK**.

What matters is preserving **meaning** and **constraints**, not forcing class count to equal table count or Java types to match SQL types one-for-one.

## 13. Choosing the Right Level of Type Protection

Not every project requires the same level of abstraction. Decision matrix:

| Scenario | Usually Appropriate Choice | Rationale |
| --- | --- | --- |
| Only a few distinct ID types | Separate CustomerId, OrderId records | Readable; compiler and equals both distinguish them |
| Many entities sharing CRUD workflows | Repository<E extends Identified<ID>, ID> | Reuses logic while binding entity–ID pairs |
| Dozens of ID types needing shared mechanics | TaggedId<K> with runtime kind or dedicated wrappers | Controls type erasure and equality |
| Numbers with runtime units or unit conversion | Money/Currency or value object carrying unit | Unit is runtime data that must be validated |
| Fixed units per API needing compile-time mix-up prevention | Quantity<U> with unit tag | Type parameter guards operations within the same unit |
| Collection of multiple subtypes for reading only | List<? extends SharedInterface> | Reads shared capability without permitting arbitrary inserts |
| Collection accepting new instances of a subtype | List<? super Subtype> | Safely adds Subtype |
| Tenant-scoped IDs | Composite value object holding TenantId + code | Scope is data value, not just static type |
| External APIs sending Strings/UUIDs | Parse/validate at boundary into value objects | Prevents raw data from entering the domain |
| Relationships between entities in DB | FK/UNIQUE/NOT NULL and transactions | Java types cannot block invalid data from other transactions |

**Prioritize clarity:** If building dozens of phantom types, converters, and factories makes code harder to understand than the domain itself, prefer **dedicated ID records** or straightforward value objects. The goal is not maximum genericization, but **encoding expressible business invariants in types so the compiler helps verify them**.

## 14. Process for Adding Type Safety to a Java Data Model

1. **List values that share technical types yet differ in meaning.** For example, CustomerId, OrderId, and ProductId are all UUIDs; prices and weights are both numbers.
2. **Identify business boundaries.** Where must an OrderId never substitute for a CustomerId? Where must currency or tenant be tracked?
3. **Create domain-named value objects** for identifiers or values prone to mix-ups; place basic invariants in constructors.
4. **Write API signatures using domain types** instead of raw Strings/UUIDs; convert from raw values strictly at boundaries.
5. **Extract reusable logic** into generic classes/methods; use bounds to express required capabilities, e.g., E extends Identified<ID>.
6. **Lock type arguments in write APIs.** Repository<Order, OrderId> never accepts Customer; minimize wildcards, raw types, and Object in core domain logic.
7. **Use wildcards intentionally** for read-only, write-only, or cross-entity algorithms; apply PECS.
8. **Check runtime behavior:** type erasure, equals/hashCode, serialization, reflection, and generic IDs missing runtime tags.
9. **Design matching SQL schemas:** PKs, FKs, UNIQUE, NOT NULL, and composite keys aligned with domain types.
10. **Verify adapters** across HTTP/JSON, JDBC/JPA, queues/events, and caches; these are the boundaries where type arguments can be lost or wrappers unwrapped to primitives.
11. **Write tests for type errors and invalid data.** Wrong calls should fail to compile; bad DB references should fail FKs; converters must target the right columns.
12. **Evaluate model evolution.** When changing ID keys, adding tenants, or adding currencies, type safety should surface impacted call sites as clear compile errors rather than silent bugs.

### Defense-in-Depth Diagram

~~~~mermaid
flowchart TD
    A["HTTP / JSON / external messages"] --> B["Parse + validate input data"]
    B --> C["Value objects: CustomerId / OrderId / Money"]
    C --> D["Domain APIs and Repository with generics + bounds"]
    D --> E["JDBC / JPA adapters converting types"]
    E --> F["SQL PK / FK / UNIQUE / CHECK + transactions"]
    F --> G["Persisted data state"]
    F -- "Constraint error" --> H["Handle business error"]
~~~~

In this diagram, **every layer has its own verification role**:

- Boundaries parse data types and input formats.
- Value objects and generic APIs prevent mixing data kinds in Java code.
- Adapters preserve accurate column/field mappings.
- Databases enforce cross-row constraints and concurrent transactions.

Never skip one layer just because another exists. A Java API using CustomerId properly can still receive a non-existent customer ID; conversely, SQL FKs do not make swapped-UUID calls readable or safe.

## 15. Practice Exercises with Answers

### Exercise 1 — Will the Compiler Catch Swapped UUIDs?

Given:

~~~~java
void updateCustomer(UUID orderId, UUID customerId) {}
~~~~

Someone calls updateCustomer(customerId, orderId).

**Question:** Will the compiler report an error? How should the model be fixed?

**Answer:** No; both arguments are UUIDs. Change the signature to **updateCustomer(OrderId orderId, CustomerId customerId)** using separate ID records. Swapped arguments will then fail at compile time.

### Exercise 2 — Does `List<String>` Separate Customer Codes from Product Codes?

Given List<String> customerCodes and List<String> productCodes.

**Question:** Does customerCodes.add(productCodes.get(0)) compile?

**Answer:** Yes. Generics only know both hold String. To protect semantics, use **List<CustomerCode>** and **List<ProductCode>** with two distinct types. Then a ProductCode cannot be inserted directly into a CustomerCode list.

### Exercise 3 — Repository Bounds

Given the interface:

~~~~java
interface Identified<ID> {
    ID id();
}
~~~~

**Question:** Declare a repository with two parameters E and ID such that entity.id() returns ID; include findById.

**Reference answer:**

~~~~java
interface RepositoryContract<E extends Identified<ID>, ID> {
    java.util.Optional<E> findById(ID id);
    void save(E entity);
}
~~~~

The bound **E extends Identified<ID>** links the entity type and key type. However, if all IDs are bare UUIDs, you still need separate domain types to preserve semantic separation.

### Exercise 4 — Purpose of Multiple Bounds

Given the method:

~~~~java
static <T extends Number & Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~~

**Question:** What do the two bounds guarantee? Do they prevent passing a price in place of a quantity?

**Answer:** Number guarantees T is a numeric type; Comparable<T> lets two values of type T be compared. They **do not** separate prices from quantities if both domains share the same technical type, such as BigDecimal. Dedicated Money, Quantity, or similar value objects are needed.

### Exercise 5 — Why Does a Generic Method with One `T` Still Accept Two ID Types?

~~~~java
static <T> void pair(T a, T b) {}

pair(new CustomerId(UUID.randomUUID()),
     new OrderId(UUID.randomUUID()));
~~~~

**Question:** Must this trigger a compile error because CustomerId differs from OrderId?

**Answer:** No. The compiler can infer **T as a common supertype** of both arguments. If two parameters must share one concrete ID type, pin the type in the business API (e.g., OrderId and OrderId) rather than inferring T from both arguments.

### Exercise 6 — Invariance of Java Generics

~~~~java
List<Order> orders = new ArrayList<>();
// List<Object> objects = orders;
~~~~

**Question:** Why is the assignment forbidden even though Order is an Object?

**Answer:** List<Order> is **not** a subtype of List<Object> because generics are invariant. If the assignment were allowed, code could insert a Customer into List<Object> (actually a List<Order>), corrupting the list's type safety.

### Exercise 7 — Choosing `extends` vs. `super`

One function needs to read the id of any entity implementing Identified. Another needs to append a Customer into a destination list.

**Question:** Which wildcards fit?

**Answer:** For reading, use **List<? extends Identified<?>>**. For adding Customer, use **List<? super Customer>**. This follows PECS. If both reading and writing the exact same concrete type, List<Customer> is clearer.

### Exercise 8 — Type Erasure and `equals`

~~~~java
record NaiveId<T>(UUID value) {}

UUID shared = UUID.randomUUID();
NaiveId<Customer> a = new NaiveId<>(shared);
NaiveId<Order> b = new NaiveId<>(shared);
~~~~

**Question:** Can a.equals(b) be true? Explain.

**Answer:** **Yes; with the record above, the result is true.** At runtime, both are the same NaiveId record class holding the same UUID value. The type argument is erased and is not part of the record's runtime structure. Use separate ID records or include a runtime kind in the generic ID.

### Exercise 9 — Can Java Replace SQL Foreign Keys?

A method receives properly typed OrderId and CustomerId, yet CustomerId holds a UUID for a customer absent from the database.

**Question:** Will an INSERT into sales_order succeed if customer_id is NOT NULL with an FK?

**Answer:** If no matching customer exists, **the INSERT is rejected by the FK**. A properly typed CustomerId only ensures the value has the **customer-ID type**, not that the customer **exists**. Java type safety and FKs are complementary checks.

### Exercise 10 — Tenant-Scoped IDs

A department has code KT in tenant A and also code KT in tenant B.

**Question:** Does DepartmentCode("KT") alone uniquely identify the department? What key design fits?

**Answer:** No; the code is only unique within a tenant. Use **DepartmentKey(TenantId, DepartmentCode)** in Java and **PRIMARY KEY(tenant_id, department_code)** with composite FKs in SQL so referencing tables preserve tenant isolation.

### Exercise 11 — Currency Conversion in APIs

~~~~java
Money vnd = new Money(new BigDecimal("100000"), Currency.getInstance("VND"));
Money usd = new Money(new BigDecimal("10"), Currency.getInstance("USD"));
~~~~

**Question:** Does the compiler reject vnd.plus(usd)? Should they be added directly?

**Answer:** **The compiler does not reject it**, because both have type Money; however, the example's plus method **rejects it at runtime** due to differing Currencies. Never add different currencies directly; perform an explicit conversion step with a rate, timestamp, and rounding rule.

### Exercise 12 — Testing the JDBC Boundary

In the domain, Order.id() is OrderId and Order.customerId() is CustomerId. When persisting, the adapter unwraps both to UUID.

**Question:** Why are mapping tests and FKs still necessary?

**Answer:** Because at the JDBC boundary, both become plain UUIDs; a mapping bug could pass the wrong value() into customer_id without any compiler warning. Mapping tests verify the right columns are bound; **FKs** verify the referenced row exists.

### Exercise 13 — Overloading by Type Argument

A class defines two methods: handle(List<CustomerId>) and handle(List<OrderId>).

**Question:** Does Java permit this overload?

**Answer:** No. Both methods share the same name and **erased** parameter type List, causing a name clash. Use distinct method names, structure a generic API parameterized per concrete implementation, or overload directly on the CustomerId and OrderId records (without wrapping in generic List).

### Exercise 14 — When Are Generics Unnecessary?

An application has only three ID types, each wrapping a UUID. A team proposes building a multi-layer generic ID framework with factories, reflection, and heavy annotations.

**Question:** Is a generic ID framework necessary here?

**Answer:** No. **Three records—CustomerId, OrderId, ProductId**—are usually clearer, simpler, and distinct at both compile time and runtime comparison. Invest in a generic framework only when reuse, ID count, and integration needs genuinely justify the complexity.

## 16. Summary

| Concept | Key Takeaway |
| --- | --- |
| **Generic type** | Parameterizes types, e.g., Repository<E, ID>, List<CustomerId> |
| **Upper bound** | Restricts type arguments to types with a contract, e.g., E extends Identified<ID> |
| **Multiple bounds** | Combines a class and interfaces, e.g., T extends Number & Comparable<T> |
| **Distinct domain types** | CustomerId differs from OrderId even when both wrap UUID |
| **Generics do not invent semantics** | Repository<E, UUID> still allows wrong-domain UUIDs if two domains share UUID |
| **Generic method type inference** | Shared T across two parameters can infer a common supertype |
| **Invariance** | List<Order> is not List<Object> |
| **PECS** | Read: ? extends; write: ? super |
| **Type erasure** | Type arguments are largely absent at runtime |
| **Tagged ID** | Can carry a runtime kind to separate generic IDs in equals |
| **Value object** | Captures domain meaning and invariants, such as Money or DepartmentKey |
| **Java type safety** | Prevents type-mismatched calls in type-checked code |
| **DB PK/FK/UNIQUE** | Protects persisted uniqueness and references across concurrent transactions |
| **Boundary mapping** | JSON/JDBC/ORM must convert raw values cleanly into and out of domain types |

**Conclusion:** Generics and type bounds let us reuse algorithms while keeping type contracts intact, yet **they deliver full value only once meaningful business distinctions are modeled as separate Java types**. For customer IDs, order IDs, units of measure, or tenant-scoped keys, pick clear value objects, connect compatible types with generic bounds, and apply wildcards according to read/write intent. Finally, always protect invariants the compiler cannot prove—row existence, uniqueness, referential integrity, and write contention—using database constraints and transactions. Doing so keeps both the Java model and the relational schema readable, verifiable, and easy to evolve.
