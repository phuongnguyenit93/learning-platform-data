# Designing Clear Methods with Many Parameters in Java

A method with many parameters can be completely valid syntactically yet very difficult to call correctly. For example:

~~~java
sendMessage("an@example.com", "Lịch họp", "Mời họp lúc 9 giờ", true, false, 3);
~~~

It is hard for readers to tell whether `true` means send immediately or high priority, whether `false` means saving a draft, and whether `3` is the number of retries or the timeout. Another method with multiple `String` parameters even allows **accidentally swapping argument positions while the program still compiles**.

The goal of API design is to make **the intent of a call clear**, restrict invalid values, group data belonging to the same concept, and make methods easier to change and test. The number of parameters is a signal to examine, but **there is no Java rule stating that a method is only allowed to have at most N parameters**. The issue lies in their meaning, relationships, and safe usability.

This lesson focuses on Java 17+ methods: how to name and order parameters, choose types, split responsibilities, use **parameter objects**, `record`, **overloading**, **builders**, validate inputs, handle optional parameters, and avoid confusing signatures.

## 1. Why Do Many Parameters Easily Cause Bugs?

Consider the following call:

~~~java
static void register(
        String firstName,
        String lastName,
        String email,
        String city,
        int age,
        boolean verified) {
    // Process registration
}

// At the call site:
register("Mai", "Nguyen", "mai@example.com", "Ha Noi", 22, false);
~~~

This is **a snippet illustrating an API signature**, not a standalone runnable program. The method has six parameters; the first four are all of type `String`. A caller can accidentally pass `city` into the `email` position or swap `firstName` and `lastName` without the compiler detecting it, because **the argument types still match**. These bugs only surface during business logic testing or with real data.

Some risk signals:

| Signal | Risk | Improvements to Consider |
| --- | --- | --- |
| Multiple parameters of the same primitive/`String` type | Passing in the wrong position still compiles | Clearly named domain types, parameter object |
| Multiple consecutive `boolean` parameters | `true, false` do not clearly convey meaning | `enum` or methods expressing behavior |
| Multiple options with default values | Calls must pass values “just to fill the slots” | Overload, options record, builder |
| Parameters that always appear together | A group of data is missing a model | `record`/class such as `Address`, `DateRange` |
| Multiple parameter groups serving different operations | The method carries multiple responsibilities | Split into separate methods by behavior |
| Validation rules depend on multiple parameters | Hard to preserve invariants | Validate at the boundary and group into a domain type |
| Repeatedly adding parameters to a public API | Callers must modify many places | Request object/options type with an extensibility strategy |
| Signature contains multiple `Object` or `Map<String, Object>` | Loss of type information, runtime casting | Concrete types checked by the compiler |

**Avoid fixing this by grouping unconditionally.** A method `distance(double x1, double y1, double x2, double y2)` may still be easy to understand in a small geometry API. Creating an entire 20-field configuration class for three fixed parameters will make the design more complex. Choose a solution based on the actual relationships of the data.

## 2. Fundamentals: Java Passes Arguments Positionally and by Value

In normal Java calls, **arguments are matched to parameters by position**, not by parameter name. Java does not have a general *named arguments* syntax that allows writing something like `createUser(email = "...", age = 20)` for the compiler to reorder automatically. Although `.class` files can contain parameter name metadata when compiled with the appropriate option, that metadata does not turn Java calls into named arguments.

~~~java
static void move(int horizontal, int vertical) {
    System.out.println(horizontal + ", " + vertical);
}

// Inside a method:
move(10, 20);
move(20, 10);
~~~

Both calls are valid, but their meanings differ because the parameter positions differ. If `horizontal` and `vertical` are two very important domain concepts, a `Point` type can make the intent clearer.

Java **always passes arguments by value**:

- For `int`, `double`, `boolean`, a primitive value is passed to the parameter.
- For `String`, `List<String>`, custom classes, or arrays, a reference value is passed to the parameter. A method can mutate a mutable object through the reference if allowed, but reassigning the parameter variable does not reassign the caller's variable.

Designing a method with many parameters requires clearly stating **whether the method mutates the objects passed into it**. If a mutable request object is shared across multiple places, unexpectedly modifying it can be more dangerous than having a long signature.

## 3. Start with Method Names, Parameter Names, and a Sensible Order

Before adding new classes, improve the simple elements.

### Choose a Verb That Expresses the Effect

The signature:

~~~java
void process(String id, int count, boolean mode);
~~~

is ambiguous because `process` does not say what is being processed, `count` has no unit, and `mode` does not make the choices clear. It can be expressed as:

~~~java
void reserveSeats(String eventId, int seatCount, ReservationMode mode);
~~~

Here `reserveSeats` describes the behavior, `seatCount` clearly states the number of seats, and `ReservationMode` is a type expressing a finite set of choices. If the `ReservationMode` type actually has the values `STANDARD`, `PREMIUM` in your design, the compiler will restrict the values passed in more tightly than an arbitrary `String`.

In APIs that need units of measurement, use names like `timeoutMillis`, `priceInCents`, or dedicated value types instead of `timeout` or `price` whose meaning is unclear. This is especially important for monetary amounts, durations, distances, ratios, and capacities.

### Order Related Parameters

A predictable order is typically:

1. The primary target or identifier of the operation.
2. Required data describing the operation.
3. Dependent or contextual values.
4. Configuration options if the design still uses a parameter list.

For example, `sendEmail(String recipient, String subject, String body)` has a conventional order that is easier to read than `sendEmail(String body, String recipient, String subject)`. However, **do not reorder a widely used API signature just to achieve an ideal order**: changing the order between parameters of the same type may not produce a compile error, yet will cause incorrect behavior at existing callers.

Good parameter names help when reading **the declaration** and are displayed by the IDE at the call site, yet a reader viewing a source file with an ordinary call still might not see the parameter names. When the risk of swapping positions is high, consider dedicated types or a parameter object.

## 4. When Values Belong to the Same Concept, Create a Dedicated Type

If a method receives `street`, `city`, `postalCode`, that is usually **an address**. These values can be grouped into an `Address` type to make the semantic boundary clearer.

~~~java
record Address(String street, String city, String postalCode) {
    Address {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city is required");
        }
        if (postalCode == null || postalCode.isBlank()) {
            throw new IllegalArgumentException("postalCode is required");
        }
    }
}
~~~

This is an **illustrative type declaration**; to run standalone, it must be placed in a source file with an appropriate `main` provided. `record`, available since Java 16 and usable on Java 17, is a convenient choice for data with a defined set of components:

- The compiler generates accessors named after the components: `address.street()`, `address.city()`, `address.postalCode()`.
- The compiler provides `equals`, `hashCode`, and `toString` based on the record components.
- Record components have corresponding `private final` fields; they cannot be reassigned through accessors.
- A **compact constructor** such as `Address { ... }` can validate data before the object finishes initializing.

**Records are not deeply immutable automatically.** If a record contains a `List`, an array, or a mutable object, they can still be modified through aliases unless you handle them defensively when creating and returning data.

### Use Domain Types to Distinguish Values of the Same Type

The values `customerId`, `orderId`, `productId` may all be `String`, but they carry different meanings. In complex APIs, small types can prevent passing the wrong one:

~~~java
record ProductId(String value) {
    ProductId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }
    }
}

record CustomerId(String value) {
    CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Customer ID is required");
        }
    }
}
~~~

A method `findProduct(ProductId id)` will not accept a `CustomerId` just because both types wrap a `String`. The compiler protects **the identifier kind**, while the constructor protects **the valid value**. In return, the application must create/read these small types; this should only be applied when the gains in safety and expressiveness justify the cost.

## 5. Parameter Object: Replacing a Group of Parameters with a Named Request

A **Parameter Object** is a class/record that holds values serving the same operation together, instead of forcing callers to remember a long positional list. It fits well when a group of parameters has a shared meaning, is used repeatedly, has invariants, or tends to grow over time.

Example of a hard-to-read API:

~~~java
void placeOrder(
        String productId,
        int quantity,
        String street,
        String city,
        String postalCode,
        boolean express,
        String note);
~~~

A call containing seven separate values makes it hard to follow and easy to mix up the address and shipping option. We can turn it into:

~~~java
void placeOrder(OrderRequest request);
~~~

Here, `OrderRequest` describes an order-placement operation, `Address` describes the address, and `DeliverySpeed` describes the delivery option using an `enum`.

### Complete Java 17+ Program

Save as **`OrderRequestDemo.java`**:

~~~java
import java.util.Objects;

public class OrderRequestDemo {
    enum DeliverySpeed {
        STANDARD, EXPRESS
    }

    record Address(String street, String city, String postalCode) {
        Address {
            if (street == null || street.isBlank()) {
                throw new IllegalArgumentException("street is required");
            }
            if (city == null || city.isBlank()) {
                throw new IllegalArgumentException("city is required");
            }
            if (postalCode == null || postalCode.isBlank()) {
                throw new IllegalArgumentException("postalCode is required");
            }
        }

        String label() {
            return street + ", " + city + " " + postalCode;
        }
    }

    record OrderRequest(
            String productId,
            int quantity,
            Address shippingAddress,
            DeliverySpeed speed,
            String note) {

        OrderRequest {
            if (productId == null || productId.isBlank()) {
                throw new IllegalArgumentException("productId is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            Objects.requireNonNull(shippingAddress, "shippingAddress");
            Objects.requireNonNull(speed, "speed");
            note = note == null ? "" : note.trim();
        }
    }

    static final class OrderService {
        String describe(OrderRequest request) {
            Objects.requireNonNull(request, "request");
            return request.productId()
                    + " x" + request.quantity()
                    + " -> " + request.shippingAddress().label()
                    + " [" + request.speed() + "]"
                    + " note=" + request.note();
        }

        long totalCents(OrderRequest request, long unitPriceCents) {
            Objects.requireNonNull(request, "request");
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("unitPriceCents must be >= 0");
            }
            return Math.multiplyExact(unitPriceCents, request.quantity());
        }
    }

    public static void main(String[] args) {
        Address address = new Address(
                "12 Nguyen Trai", "Ha Noi", "100000");
        OrderRequest request = new OrderRequest(
                "BOOK-01", 2, address,
                DeliverySpeed.EXPRESS, " Giao gio hanh chinh ");

        OrderService service = new OrderService();
        System.out.println(service.describe(request));
        System.out.println("Total cents: " + service.totalCents(request, 150_000));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OrderRequestDemo.java
java OrderRequestDemo
~~~

Stdout:

~~~text
BOOK-01 x2 -> 12 Nguyen Trai, Ha Noi 100000 [EXPRESS] note=Giao gio hanh chinh
Total cents: 300000
~~~

**Explanation:**

1. `Address` groups the three parts of an address; the constructor prevents empty or `null` data.
2. `DeliverySpeed` is an `enum`, so only the `STANDARD` or `EXPRESS` options can be used (except for a `null` reference, which is already checked).
3. `OrderRequest` represents all data for an order. Callers only pass one object into `OrderService.describe`, avoiding a chain of seven separate parameters.
4. The compact constructor normalizes `note`: null becomes an empty string, and a string has leading/trailing whitespace trimmed. In a compact constructor, the record component parameter is validly reassigned so that the normalized value is stored in the corresponding field.
5. `OrderService` is an object providing processing behavior that receives an already validated `OrderRequest`. Checking that `request` is non-null at the method boundary is still necessary.
6. `Math.multiplyExact` checks for overflow when computing a `long` total. Monetary amounts in the example are represented as **the smallest currency unit** using `long` to avoid floating-point precision errors; real-world applications also need currency, tax, exchange rate, and transaction rules.
7. `String` and `enum` inside the record are immutable in terms of observable value. `Address` contains only `String` values, so this data model does not expose a mutable list or array through accessors.

Note that **the parameter object's constructor still takes multiple parameters**, so at the site where `OrderRequest` is created, users still have to understand them. A parameter object primarily solves passing data across multiple APIs and validation rules; if object construction is also complex, a builder or clearly named factory can be used.

### When Is a Parameter Object Worth Using?

Consider it when a group of values has a clear domain name, appears across multiple methods, requires shared validation, or is frequently passed across multiple layers. There is no need to create a new record just to replace every method with three easy-to-understand parameters with a one-off type that carries no distinct meaning of its own.

If the fields inside a parameter object are unrelated, that may be a sign you have bundled a **“parameter bag”** merely to hide a long signature. Re-examine the method's responsibilities before creating a new type.

## 6. Boolean Flags: Why Do `true, false` Make Calls Hard to Read?

For example:

~~~java
sendReport(report, true, false);
~~~

If the parameters are `includeDetails` and `urgent` respectively, looking solely at the call site makes it very difficult to tell which behavior `true` applies to.

Ways to improve:

### Approach A — Methods Named After Behavior

When a boolean switches the method between **two completely different behaviors**, the API can be split:

~~~java
void publishReport(Report report);
void saveReportDraft(Report report);
~~~

These are illustrative signatures requiring a `Report` type and appropriate implementations. The two method names help the caller express the goal directly, instead of `publish(report, true)` versus `publish(report, false)`.

### Approach B — `enum` When There Is a Finite Set of Choices

~~~java
enum DeliveryMode {
    STANDARD, EXPRESS
}

void ship(OrderRequest request, DeliveryMode mode);
~~~

A call `ship(request, DeliveryMode.EXPRESS)` is clearer than `ship(request, true)`. However, if `OrderRequest` already contains an equivalent `speed`, do not force the caller to provide two duplicate data sources without a precedence rule.

### Approach C — Options Object for Multiple Combined Options

When there are independent choices such as format, column headers, maximum row count, and language, group them into `ExportOptions`. An `enum` represents **a single choice**, whereas an options object represents **a set of configuration settings**.

**Not every boolean is bad.** `setEnabled(boolean enabled)` can be appropriate if the on/off property itself is a direct domain concept. Signs that refactoring is needed are when callers typically pass non-self-explanatory `true`/`false` literals, or when a flag changes many unrelated behavioral branches.

## 7. Builder: Clear Meaning When There Are Many Optional Parameters

A Builder fits well when an object has many options with default values, users only set a subset of them, and reading the call becomes easier with named methods. For example, instead of:

~~~java
export(data, "CSV", false, 50, "vi-VN");
~~~

you can write:

~~~java
ExportOptions options = ExportOptions.builder()
        .format(Format.CSV)
        .includeHeader(false)
        .maxRows(50)
        .locale(Locale.forLanguageTag("vi-VN"))
        .build();
~~~

A Builder **is not special Java syntax**: it is a design pattern implemented with classes and methods. Proper builder code is required to support a fluent API.

### Complete Java 17+ Example with Defaults and Validation

Save the file **`BuilderOptionsDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class BuilderOptionsDemo {
    enum Format {
        CSV, JSON
    }

    static final class ExportOptions {
        private final Format format;
        private final boolean includeHeader;
        private final int maxRows;
        private final Locale locale;

        private ExportOptions(Builder builder) {
            this.format = builder.format;
            this.includeHeader = builder.includeHeader;
            this.maxRows = builder.maxRows;
            this.locale = builder.locale;
        }

        static Builder builder() {
            return new Builder();
        }

        String describe() {
            return format
                    + " / header=" + includeHeader
                    + " / maxRows=" + maxRows
                    + " / locale=" + locale.toLanguageTag();
        }

        static final class Builder {
            private Format format = Format.JSON;
            private boolean includeHeader = true;
            private int maxRows = 100;
            private Locale locale = Locale.ROOT;

            Builder format(Format value) {
                format = Objects.requireNonNull(value, "format");
                return this;
            }

            Builder includeHeader(boolean value) {
                includeHeader = value;
                return this;
            }

            Builder maxRows(int value) {
                if (value <= 0) {
                    throw new IllegalArgumentException("maxRows must be positive");
                }
                maxRows = value;
                return this;
            }

            Builder locale(Locale value) {
                locale = Objects.requireNonNull(value, "locale");
                return this;
            }

            ExportOptions build() {
                return new ExportOptions(this);
            }
        }
    }

    public static void main(String[] args) {
        ExportOptions options = ExportOptions.builder()
                .format(Format.CSV)
                .includeHeader(false)
                .maxRows(50)
                .locale(Locale.forLanguageTag("vi-VN"))
                .build();

        ExportOptions defaults = ExportOptions.builder().build();

        System.out.println(options.describe());
        System.out.println(defaults.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BuilderOptionsDemo.java
java BuilderOptionsDemo
~~~

Stdout:

~~~text
CSV / header=false / maxRows=50 / locale=vi-VN
JSON / header=true / maxRows=100 / locale=und
~~~

Here `Locale.ROOT.toLanguageTag()` returns `und`, representing an undetermined language; that is the default choice intentionally set by the example. In a real application, an explicit default locale can be chosen as needed, but do not silently use the system locale if results must remain consistent across machines.

**Strengths of a builder:**

- Each call `.maxRows(50)`, `.locale(...)` pairs a name with the value's meaning.
- Callers can provide only the options they need to change; other items use defaults.
- Input validation in setter methods or `build()` helps create the object in a valid state.
- The resulting `ExportOptions` object has `final` fields and does not expose direct setters after creation.

**Limitations:** A builder requires extra classes/methods and can potentially be misused if defaults are inappropriate. If there are **required parameters**, consider placing them in the constructor/builder factory or validating them in `build()`. Do not allow callers to create an object that is “type-valid” yet missing essential properties merely because every field defaults to null.

## 8. When to Use Overloading Instead of a Builder?

**Method overloading** allows multiple methods with the same name but different parameter signatures. It suits **a small, stable number of variants**, especially when there are clear defaults.

~~~java
static String greet(String name) {
    return greet(name, "Xin chào");
}

static String greet(String name, String prefix) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name is required");
    }
    if (prefix == null) {
        throw new IllegalArgumentException("prefix is required");
    }
    return prefix + ", " + name;
}
~~~

These are two illustrative methods that can be placed in the same class. `greet("Mai")` calls the one-parameter overload and delegates to the primary overload. `greet("Mai", "Chào buổi sáng")` allows supplying a different greeting.

However, if there are five independent options and each option has two states, the number of combinations can reach `2^5 = 32`. You should not create dozens of overloads just to simulate default/named arguments. With many independent options, an **options object or builder** is easier to maintain.

### Runnable Code Demonstrating Overloading

Save the file **`OverloadDemo.java`**:

~~~java
public class OverloadDemo {
    static String greet(String name) {
        return greet(name, "Xin chào");
    }

    static String greet(String name, String prefix) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (prefix == null) {
            throw new IllegalArgumentException("prefix is required");
        }
        return prefix + ", " + name;
    }

    public static void main(String[] args) {
        System.out.println(greet("Mai"));
        System.out.println(greet("Mai", "Chào buổi sáng"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverloadDemo.java
java OverloadDemo
~~~

Stdout:

~~~text
Xin chào, Mai
Chào buổi sáng, Mai
~~~

Overloads **cannot be distinguished solely by return type**. Two methods with the same name and the same parameter list where one returns `int` and the other returns `String` will cause a duplicate declaration error. The compiler selects an overload based on rules regarding parameter lists, argument types, and allowed conversions; it cannot rely on the type of the variable receiving the result to choose between two methods that differ only in return type.

## 9. Avoid Ambiguous Overloads with `null`, Boxing, and Varargs

Having many overloads can sometimes make an API harder to use. Consider two methods:

~~~java
static void search(String query) { /* ... */ }
static void search(Integer limit) { /* ... */ }
~~~

The call `search(null)` is **ambiguous at compile time** because null can be converted to both `String` and `Integer`; neither type is more specific than the other in the subtype hierarchy to break the tie. An explicit cast would be required, or better yet, name the API/input types so callers do not fall into confusing situations.

This is **illustrative code**; the `/* ... */` denotes a valid empty method body without specific business logic. Do not use this example as a standalone runnable program.

### Primitives, Wrappers, and Overload Resolution

~~~java
static void accept(long value) {
    System.out.println("long");
}

static void accept(Integer value) {
    System.out.println("Integer");
}
~~~

For the call `accept(5)` (an `int` literal), Java prefers primitive widening `int → long` over boxing `int → Integer` under these overload rules, so it selects `accept(long)`. If an API has multiple overloads differing in primitives/wrappers and callers pass `null`, complexity can grow rapidly.

**Principle:** Overloads should represent genuinely useful, predictable ways of calling. Do not create overloads merely because it is technically allowed.

### Varargs Do Not Replace a Parameter Object

~~~java
static int sum(int... numbers) {
    int result = 0;
    for (int number : numbers) {
        result = Math.addExact(result, number);
    }
    return result;
}
~~~

`int...` is varargs: inside the method body, `numbers` has type `int[]`. Varargs are suitable for **multiple values with a uniform role** (numbers to sum, items to log). They are not suitable for positions with different meanings such as an amount, a retry count, and a timeout in seconds, even though all three share the `int` type.

A varargs parameter must be **the last parameter** in the declaration. Varargs typically create a corresponding array when called with multiple separate values; if the caller directly passes an array of the matching type, the method may use that exact array. The method should clearly state whether it modifies elements of the input array. For reference-type and generic varargs, there are also warnings/limitations regarding heap pollution that need to be addressed in an advanced lesson.

## 10. Distinguishing Required Data from Optional Data

A method with many parameters easily becomes hard to use because it mixes things that **must be present** with choices that **can be omitted**. For example, consider classifying them:

| Category | Example | Design Direction |
| --- | --- | --- |
| Required to identify the operation | `productId`, `customerId` | Require explicitly at the constructor/factory |
| Required to enforce business rules | `quantity > 0`, `shippingAddress` | Validate when creating the request |
| Optional with clear defaults | `format = JSON`, `maxRows = 100` | Options object, builder, or overload |
| Optional where “not provided” has meaning | `note`, `filter` | Define a clear rule for absence |
| Contextual data that callers should not choose | Internal logger, application configuration | Consider service state/dependencies instead of adding to every method |

**Do not use `null` as an implicit default signal** if doing so leaves callers unaware of the contract. For example, `export(data, null, -1, false)` is hard to understand and hard to validate. Decide on one policy: reject null, convert null into a documented default, or represent absence with a clearer type.

In many APIs, `Optional<T>` is useful as a **return type** to express the presence or absence of a result. Using `Optional` as a parameter is not automatically better than null: it forces callers to create `Optional.of(...)` or `Optional.empty()` and still does not solve the problem of a signature with too many positional slots. For multi-option configuration, an optional field in a request/options object or a builder is usually clearer.

If using overloaded factories, make sure default values live in **one place**, for example having the overload with fewer parameters call the primary overload. Avoid having each overload duplicate a processing branch and accidentally diverge in logic over time.

## 11. Per-Field and Cross-Field Validation

Multiple parameters often have **interrelated** constraints. For example, a date range requires `start` before `end`; quantity must be positive; if express delivery is chosen, the shipping method must support it.

With a `record`, invariants can be enforced in the constructor:

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {
    DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end must be >= start");
        }
    }
}
~~~

This is an **illustrative type declaration**; to run standalone, a class with `main` must be added. The two parameters should not exist as two arbitrary dates if the logic always requires a valid **DateRange**. Once a domain type exists, other methods can accept `DateRange` without rewriting the check on both dates.

**Choose the rule that matches the business logic.** The condition `end.isBefore(start)` is an example rule **allowing a range with the same start and end**. If the system requires a non-empty range or treats the end point as exclusive, the condition needs to be explicitly adjusted rather than silently applying the example's rule.

### Where to Validate?

1. For **reusable value types**, validate upon creation to prevent invalid state from propagating across multiple methods.
2. For **operation-specific rules**, validate in the processing method. For example, a quantity limit based on current inventory cannot be guaranteed solely by the request constructor.
3. For **external inputs**, validate missing data, format, and logic errors before mutating state or performing irreversible actions.
4. For multiple interrelated parameters, avoid validating only each individual field while missing the overall invariant.

For example, `Objects.requireNonNull(address)` helps fail fast when an input is absent; an exception message can be helpful when debugging. However, distinguish carefully: a `null` error is not automatically synonymous with a business-rule error. If `null` is a permitted value, the design and documentation must state so clearly.

## 12. A Long Signature Is Sometimes a Sign That a Method Does Too Much

The solution is not always `record Request(a, b, c, d, e, f)`. Consider:

~~~java
void processOrder(
        String productId,
        int quantity,
        String paymentToken,
        String email,
        boolean notifyCustomer,
        String auditFilePath);
~~~

The method places an order, processes payment, sends a notification, and writes an audit file all at once. Many parameters can reflect **too many responsibilities**.

Distinguish between:

- **Data that defines a single cohesive operation:** can be grouped into `OrderRequest`.
- **Services or dependencies needed to perform the operation:** can be provided through the service's constructor, dependency injection, or collaborating components, depending on the application design.
- **Independent behaviors with their own conditions:** can be extracted into separate methods/functional layers and coordinated through a workflow.

A conceptual organization example:

~~~java
Order order = orderService.create(request);
PaymentReceipt receipt = paymentService.charge(order, payment);
notificationService.sendConfirmation(order, receipt);
~~~

This is **Java pseudocode illustrating responsibility splitting**; the types and methods are not defined, so this is not a standalone compilable example. The purpose is to illustrate behavioral separation, not to recommend that every application start with three services from day one.

Do not put all dependencies into an options object just so a method takes a single parameter. A request meant to represent **the data of an operation** differs from a service holding **collaborators that carry out behavior**.

## 13. Designing Methods That Receive Multiple Mutable Objects

A parameter object may contain an array, list, or map. In Java, passing a parameter object into a method is still **pass-by-value of the reference**; if the object holds mutable references, the caller may observe unintended modifications.

### Example: A Record with a List Needs a Defensive Copy

Create the file **`SafeBatchRequestDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeBatchRequestDemo {
    record BatchRequest(List<String> itemIds, int retryCount) {
        BatchRequest {
            Objects.requireNonNull(itemIds, "itemIds");
            if (itemIds.isEmpty()) {
                throw new IllegalArgumentException("itemIds must not be empty");
            }
            if (retryCount < 0) {
                throw new IllegalArgumentException("retryCount must be >= 0");
            }
            itemIds = List.copyOf(itemIds);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");
        source.add("B");

        BatchRequest request = new BatchRequest(source, 2);
        source.add("C");

        System.out.println("Source: " + source);
        System.out.println("Request: " + request.itemIds());

        try {
            request.itemIds().add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Request list cannot be changed");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeBatchRequestDemo.java
java SafeBatchRequestDemo
~~~

Stdout:

~~~text
Source: [A, B, C]
Request: [A, B]
Request list cannot be changed
~~~

`List.copyOf` creates a list that cannot be modified through ordinary mutation APIs and does not share mutable structural state with `ArrayList source`. Adding `C` to `source` does not add it to `request.itemIds()`.

Points to consider:

- `List.copyOf` does not accept null elements; if the data allows nulls, a different strategy must be chosen.
- When the elements are **mutable objects**, this is a **shallow copy** of each element reference: an element object can still be modified through another alias.
- A `final` field does not protect the immutability of elements inside a collection.
- If a method only needs to **read** the list and does not retain the reference, copying is sometimes unnecessary; decide based on the contract and cost.

Clearly state whether the method modifies the input, whether it takes ownership of the object or merely borrows the reference for reading, and whether the caller can reuse the request. Avoid unexpectedly mutating an input list/map just because the language allows it.

## 14. Public APIs and Compatibility When Adding Parameters

Suppose the initial API is:

~~~java
void send(String recipient, String subject, String body);
~~~

Later, `priority` needs to be added. Completely changing the signature to four parameters breaks compilation for older caller code against the new API. For a published Java library, changing a method descriptor can also affect **binary compatibility**: already-compiled code looking for the old signature may encounter linkage errors such as `NoSuchMethodError` if the new library version removes the old method.

A possible evolution path is:

~~~java
void send(String recipient, String subject, String body) {
    send(recipient, subject, body, Priority.NORMAL);
}

void send(
        String recipient,
        String subject,
        String body,
        Priority priority) {
    // Actual implementation.
}
~~~

This is an **API illustration pattern**, requiring `Priority` and an appropriate implementation body to compile into a runnable program. The three-parameter overload is kept and delegates to the new method. For a new API designed from scratch, a request object such as `SendMessageRequest` can reduce the need to change every signature when adding options with sensible defaults.

However, **adding a component to a public record does not automatically guarantee compatibility**: the synthesized constructor, record structure, accessors, and user code can all be affected. If long-term stability of a library API is needed, consider a builder/class with dedicated constructors, versioning, and compatibility policies instead of assuming a record is always easy to extend.

### Optimize for the Call Site or the Declaration Site?

A method is defined once yet called in hundreds of places. Adding a request object may shorten the declaration, but you must weigh the cost of reading and creating that object at the call sites. Evaluate at least:

- Does the call site clearly convey intent?
- Can callers accidentally pass parameters of the same type in the wrong order?
- Does the request type have standalone meaning and can it be validated?
- Does the API need to remain stable across multiple versions?
- Does it generate too many temporary classes merely to reduce the number of commas?

Clear design lies in **the ability to understand and use the API correctly**, not merely in signature length.

## 15. Rules for Choosing a Solution for Each Parameter Pattern

| Situation | Typical Appropriate Solution | Notes |
| --- | --- | --- |
| 2–3 required parameters with clearly distinct meanings | Keep the parameters directly | Choose predictable names and order |
| Multiple components forming a single concept | Value object / `record` | Validate invariants; consider immutability |
| Multiple parameters describing a single request | Parameter object | Do not create a meaningless “data bag” |
| Multiple independent options with defaults | Builder or options class | Check required values in `build()` |
| A few simple variants | Overloads delegating to the main implementation | Avoid overload explosion |
| Two clearly distinct behavioral modes | Two clearly named methods | Limit ambiguous boolean flags |
| One choice from a fixed set | `enum` | Still must specify whether null is allowed |
| Multiple values with the same meaning, variable count | Varargs or collection | Do not use for different parameter roles |
| Multiple identical primitives with different units | Unit-suffixed names or domain types | Avoid “primitive obsession” when the risk is significant |
| Method containing multiple independent responsibilities | Split the method/service | Do not merely wrap all parameters into one object |

This table is an evaluation guide, not a mandatory formula. Some mathematical APIs have many parameters yet are always clear; likewise, some APIs have just two booleans that should be fixed immediately.

## 16. Testing Multi-Parameter Methods

Test **correct behavior**, **argument order**, **boundary values**, and **shared invariants**. A good test tries to catch the bugs that the compiler cannot see.

### Test Case Categories to Include

1. **Happy path:** valid parameters produce the expected result.
2. **Swapped positions:** for parameters of the same type, use clearly distinguishable test data to detect permutations; consider changing types so the compiler eliminates the error.
3. **Missing required data:** null, empty string, or empty array or collection depending on the contract.
4. **Boundaries:** `quantity = 0`, negative numbers, maximum values, overflow, or end date before start date.
5. **Omitted options:** builder/defaults work properly; no undefined state is produced.
6. **Parameter interactions:** two incompatible choices must be rejected or intentionally normalized.
7. **Mutable inputs:** the method does not accidentally modify the caller's array/list if the contract is read-only.
8. **Overloads:** the right method is selected with primitives, wrappers, subtypes, and null when applicable.

### Verification Check Without a Test Library

Create the file **`ParameterDesignCheck.java`**:

~~~java
import java.util.Objects;

public class ParameterDesignCheck {
    record Range(int startInclusive, int endExclusive) {
        Range {
            if (endExclusive < startInclusive) {
                throw new IllegalArgumentException("invalid range");
            }
        }
    }

    static int length(Range range) {
        Objects.requireNonNull(range, "range");
        return Math.subtractExact(
                range.endExclusive(), range.startInclusive());
    }

    static void assertEquals(int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        assertEquals(5, length(new Range(3, 8)));
        assertEquals(0, length(new Range(4, 4)));

        try {
            new Range(8, 3);
            throw new AssertionError("invalid range was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("Rejected invalid range");
        }

        System.out.println("All checks passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterDesignCheck.java
java ParameterDesignCheck
~~~

Stdout:

~~~text
Rejected invalid range
All checks passed
~~~

`Range` groups two numbers to form **a range with an exclusive end point**, and its constructor prevents `endExclusive < startInclusive`. `length` accepts a single meaningful concept instead of two unnamed integers at the call site.

Test cases in the example:
- The range `[3, 8)` has length 5.
- The range `[4, 4)` has length 0 and is permitted.
- The range `[8, 3)` is rejected in the constructor.

This verification approach using `AssertionError` runs without any additional library; real applications can use JUnit to organize tests. In the example, `Math.subtractExact` protects integer subtraction from overflow. If the input range includes extreme `int` values and the true length exceeds the `int` range, the API must choose an appropriate result type, such as `long`.

## 17. Common Mistakes When Refactoring Many Parameters

| Design Mistake | Consequence | Fix |
| --- | --- | --- |
| Bundling all parameters into `Map<String, Object>` | Compiler loses type-checking ability; key typos only surface at runtime | Use a class/record with concrete fields |
| Using multiple `boolean` values and “magic” numbers | Call site is hard to understand | `enum`, method names, domain types |
| Adding overloads for every combination of options | Signature count balloons, hard to maintain | Options object/builder with defaults |
| Builder does not validate required fields | `build()` produces an invalid object | Validate before returning the object |
| Parameter object holds unrelated data | Merely moves complexity elsewhere | Re-examine the method's responsibilities |
| Record contains a mutable collection without copying | Caller can modify data after creation | Defensive copy and document immutability |
| Null options without a contract | The same call is interpreted differently | Choose a clear null/default policy |
| Converting String to enum but parsing invalid input | Confusing runtime errors at the system boundary | Validate and map external input to enum at the boundary |
| Reordering multiple Strings in an existing API | Still compiles yet passes data incorrectly | Maintain overloads or migrate with a plan and tests |
| Changing a public constructor/record without checking callers | Breaks source/binary compatibility | Review API compatibility and versioning direction |
| Reassigning a parameter expecting to mutate the caller's variable | Caller does not receive the new value | Use a return value or mutate the object via an intentional API |
| Replacing every short method with a builder | Excessive boilerplate and hard to read | Only use a builder when there are enough options and default values |

## 18. Practice Exercises

### Exercise 1 — Upgrade a Notification-Sending API

Given the signature:

~~~java
void notifyUser(
        String userId,
        String title,
        String content,
        boolean urgent,
        boolean saveCopy,
        int retryCount);
~~~

Redesign it so that the call site does not contain two unclear booleans. Hints:

- Create `NotificationRequest` to group `userId`, `title`, `content`, and the options belonging to the same notification.
- Use `enum Priority { NORMAL, URGENT }` if this is indeed the domain set of values.
- Provide a sensible default for `retryCount` via a builder/options, with a non-negative constraint and an appropriate upper limit.
- Explain for yourself when `saveCopy` should be an option and when it should be split into a separate behavior.
- Write tests for cases where `title` is missing or `retryCount < 0`.

### Exercise 2 — Spot the Swapped-Parameter Bug

~~~java
void transfer(String fromAccountId, String toAccountId, long amountCents);
~~~

Set two different IDs and an easily recognizable amount. During review, calls using `transfer(destination, source, amount)` can be **type-valid yet reverse the transfer direction**. Propose an `AccountId` or `TransferRequest` type, write a validation check for a positive amount, and consider forbidding identical source and destination accounts if business rules require it.

### Exercise 3 — When Should You Not Create a Builder?

Consider `calculateArea(double width, double height)` and `drawPixel(int x, int y)`. For simple problems, two required parameters can already be clear enough; explain why a builder might be over-engineering. Then imagine needing to add measurement units, coordinate systems, transformations, and drawing modes; evaluate when dedicated types or options are needed.

### Exercise 4 — A Record Containing Mutable Data

Create the record `TeamRequest(List<String> members, String teamName)`, determine which method validates the name, forbids null members, and copies the list so the caller cannot modify the request's contents after creation. Write tests:
- Initial `members` contains two elements.
- After creating the request, add an element to the original list.
- `request.members()` does not change along with the original list.
- Attempt to modify the returned list, expecting an exception if the design uses `List.copyOf`.

### Exercise 5 — Safe Overload Design

Given the two signatures `search(String query)` and `search(Integer limit)`, explain why `search(null)` does not compile. Propose clear names `searchByText(String query)` and `searchWithLimit(int limit)`, or a `SearchRequest` type, depending on the business domain. Be sure to point out that overload resolution is based on **argument types**, not variable names.

## 19. Review Checklist Before Making a Method Public

- [ ] **Method name:** readers know what the method does, whether it has side effects or only computes a result.
- [ ] **Parameter names and units:** counts, monetary amounts, milliseconds, points in time, and statuses are clearly represented.
- [ ] **Ordering:** do parameters of the same type carry a risk of being swapped accidentally?
- [ ] **Conceptual grouping:** should an address, time range, or request be a separate type?
- [ ] **Booleans/primitives:** are literals `true`, `false`, `0`, `1` at the call site hard to explain?
- [ ] **Required/optional:** are there sensible default values applied consistently?
- [ ] **Validation:** are null checks, bounds, cross-field constraints, and valid states verified?
- [ ] **Aliasing:** does the method modify the input object/array/list, and is that clear in the contract?
- [ ] **Builder/overloads:** which option is simpler for the majority of callers?
- [ ] **Ability to change:** if an option is added, how are existing caller code and binary compatibility affected?
- [ ] **Responsibility level:** are many parameters hiding a method that is doing too much?
- [ ] **Testing:** are there normal cases, boundary cases, invalid cases, and swapped-parameter cases?

**Closing principle:** A good API does not necessarily have the fewest parameters. A good API helps users **understand the exact data to supply, avoid passing values in the wrong positions, know the validity conditions, and predict the effects of the call**. When multiple parameters together describe one concept, model them into a named type with clear constraints. When there are multiple independent options, use compact overloads or a builder. When a signature is long because the method is doing too many things, revisit its responsibilities instead of merely wrapping every value into one object.
