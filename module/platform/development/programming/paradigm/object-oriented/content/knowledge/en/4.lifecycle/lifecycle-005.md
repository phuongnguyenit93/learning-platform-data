# Static Factory Methods, Factory, and Builder in Java

In OOP, using `new` is not the only way to **obtain an object**. You can hide a constructor behind a static method, delegate the choice of concrete class to a Factory, or collect parameters in a Builder before constructing the object. All three relate to **object creation and lifecycle**, but address different problems.

> **Key distinctions:** A constructor is Java's object-initialization syntax; a *static factory method* is a `static` method that returns an object; a *Factory* is usually an object/class responsible for choosing and supplying objects; a *Builder* configures an object step by step and then invokes `build()`. Calling a factory does not guarantee creation of a new instance.

## 1. Starting with Constructors and the Object Lifecycle

A basic Java example:

~~~java
public class User {
    private final String email;

    public User(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không được rỗng");
        }
        this.email = email.trim();
    }

    public String getEmail() {
        return email;
    }
}
~~~

~~~java
User user = new User("hello@example.com");
System.out.println(user.getEmail());
~~~

In `new User(...)`, the JVM allocates and initializes an instance under Java's language rules and invokes its constructor after the appropriate initialization steps. A constructor shares its class's name, **has no return type**, can be overloaded, and can validate initial state.

However, constructors become less expressive when multiple creation approaches need descriptive names:

~~~java
// Cùng nhận một double nên không thể khai báo cả hai constructor này:
// Temperature(double celsius)
// Temperature(double fahrenheit)
~~~

The two constructors above have the **same signature** `Temperature(double)`; Java cannot distinguish them by parameter names alone. A static factory method handles that case.

For every object-creation approach in this lesson, distinguish:

- **Creating an instance:** the constructor actually executes for a new object (directly or inside a factory/builder).
- **Obtaining an instance:** a method returns an existing object, a cached object, a shared instance, or a particular implementation.
- **Using and releasing an object:** once no reachable strong reference remains to an object, it may become eligible for garbage collection. Factories and Builders do not change this principle; external resources such as files/sockets still need timely closing when appropriate.

## 2. Static Factory Methods: Naming Creation Paths

A **static factory method** is a `static` method that returns an object. It can invoke a constructor, process or convert data before construction, or return an existing object.

A practical example: a temperature can be specified in °C or °F. Internally, we store only **Celsius** as the canonical representation:

`Temperature.java` (Java 11+):

~~~java
public final class Temperature {
    private final double celsius;

    // Ẩn cách khởi tạo: bên ngoài phải chọn đơn vị rõ ràng.
    private Temperature(double celsius) {
        if (!Double.isFinite(celsius)) {
            throw new IllegalArgumentException("Nhiệt độ phải là số hữu hạn");
        }
        this.celsius = celsius;
    }

    public static Temperature celsius(double value) {
        return new Temperature(value);
    }

    public static Temperature fahrenheit(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Nhiệt độ phải là số hữu hạn");
        }
        return new Temperature((value - 32.0) * 5.0 / 9.0);
    }

    public double inCelsius() {
        return celsius;
    }

    public double inFahrenheit() {
        return celsius * 9.0 / 5.0 + 32.0;
    }
}
~~~

~~~java
public class Main {
    public static void main(String[] args) {
        Temperature a = Temperature.celsius(30);
        Temperature b = Temperature.fahrenheit(86);

        System.out.println(a.inCelsius()); // 30.0
        System.out.println(b.inCelsius()); // 30.0

        // new Temperature(30); // Không biên dịch: constructor private
    }
}
~~~

The names `celsius` and `fahrenheit` reveal the **meaning** of the arguments at call sites. The class exposes only valid creation paths; with no setter, the instance's `celsius` field cannot be updated after creation. Nevertheless, the two calls above create **separate objects**, because each factory calls `new Temperature(...)`.

### When Are Static Factories Useful?

1. **Meaningful names:** `of(...)`, `from(...)`, `parse(...)`, `forGuest(...)`, and `fromCsv(...)` make the data source clear.
2. **Input validation and normalization:** the factory enforces validity rules before returning an object.
3. **Hiding implementations:** the return type may be an interface/superclass while the instance is a specific implementation.
4. **Reuse/caching when appropriate:** a factory may return an old instance, singleton, or cached object instead of allocating a new one.
5. **A compact API:** constructors can be hidden with `private`/package-private access while valid creation paths stay centralized.

Some common names (mostly **conventions**, not special Java syntax):

| Method name | Common meaning | Familiar example |
| --- | --- | --- |
| `of(...)` | Create/obtain an instance from parameters | `List.of("a", "b")` |
| `from(...)` | Convert another kind of data/type to the target type | `Instant.from(temporal)` |
| `valueOf(...)` | Obtain an object for a corresponding value | `Integer.valueOf(42)` |
| `parse(...)` | Parse a string into a target-type value | `LocalDate.parse("2026-10-15")` |
| `getInstance(...)` | Obtain an instance, possibly shared | A library-defined name |
| `newInstance(...)` | Name suggesting a new instance | A library-defined name |

Do not infer caching behavior or guaranteed new allocation **from the name alone**. Read the API contract: for example, `Integer.valueOf` may return cached objects for some values, while `List.of` creates/obtains an unmodifiable list without guaranteeing instance identity.

### A Static Factory Is Not a “Static Constructor”

Java **has no static constructors** in the sense of declaring `static User(...)` or adding `static` to a constructor. A static initialization block, `static { ... }`, runs when JVM rules initialize the class; it initializes static state and **does not** act as a factory returning an object. A static factory method is an ordinary method with the `static` keyword and a return type.

~~~java
public class Config {
    private static final String DEFAULT_REGION;

    static {
        DEFAULT_REGION = "VN"; // Static initializer, không trả về object
    }

    private final String region;

    private Config(String region) {
        this.region = region;
    }

    public static Config defaultConfig() { // Static factory method
        return new Config(DEFAULT_REGION);
    }

    public String region() {
        return region;
    }
}
~~~

## 3. Factory: Centralizing the Choice of Object Type

The `Temperature` static factory lives **inside the returned class**. But some systems must choose an **implementation type** based on configuration, business conditions, or the runtime environment. A separate Factory class/object prevents callers from scattering `new ConcreteType(...)` throughout the codebase.

Example: selecting a notification channel. For OOP illustration, both implementations only print to the console; they **do not send real emails or SMS messages**.

`NotificationDemo.java` (Java 11+):

~~~java
interface Notifier {
    void send(String message);
}

final class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("[EMAIL] " + message);
    }
}

final class SmsNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("[SMS] " + message);
    }
}

enum Channel {
    EMAIL, SMS
}

final class NotifierFactory {
    private NotifierFactory() {
        // Không cho tạo instance của lớp tiện ích này.
    }

    public static Notifier create(Channel channel) {
        if (channel == null) {
            throw new IllegalArgumentException("Channel không được null");
        }

        switch (channel) {
            case EMAIL:
                return new EmailNotifier();
            case SMS:
                return new SmsNotifier();
            default:
                throw new IllegalArgumentException("Channel không hỗ trợ");
        }
    }
}

public class NotificationDemo {
    public static void main(String[] args) {
        Notifier notifier = NotifierFactory.create(Channel.EMAIL);
        notifier.send("Đơn hàng đã được xác nhận");
        // [EMAIL] Đơn hàng đã được xác nhận

        Notifier sms = NotifierFactory.create(Channel.SMS);
        sms.send("Mã OTP thử nghiệm");
        // [SMS] Mã OTP thử nghiệm
    }
}
~~~

Callers only depend on `Notifier` and the selected `Channel`. The Factory constructs the actual class; application code calls `send` through the interface. If creation of `EmailNotifier` changes (for example, to supply dependencies or configuration), those changes can be concentrated where objects are built.

~~~mermaid
flowchart LR
    Client["Client"] --> Factory["NotifierFactory.create(channel)"]
    Factory --> Decision{"Channel"}
    Decision -->|EMAIL| Email["new EmailNotifier()"]
    Decision -->|SMS| SMS["new SmsNotifier()"]
    Email --> Interface["Notifier"]
    SMS --> Interface
    Interface --> Use["Client gọi send(...)"]
~~~

### Are “Factory” and the “Factory Method Pattern” the Same?

Not exactly. These terms are often confused:

| Term | Characteristics | Example |
| --- | --- | --- |
| **Static factory method** | A `static` method returning an object, usually on the product class | `Temperature.fahrenheit(86)` |
| **Simple Factory** | A method/class centralizing implementation selection and creation; not one of the 23 individually named GoF patterns | `NotifierFactory.create(Channel)` above |
| **Factory Method (GoF)** | A superclass defines an extensible creation operation; subclasses override it | `Creator.createProduct()` implemented by a subclass |
| **Abstract Factory (GoF)** | Provides an interface for creating a **family of related objects** without requiring clients to name concrete classes | `UiFactory.createButton()` and `createDialog()` for each UI family |

A minimal **Factory Method pattern** example:

~~~java
interface Report {
    String render();
}

final class CsvReport implements Report {
    public String render() {
        return "name,quantity\nBook,2";
    }
}

final class JsonReport implements Report {
    public String render() {
        return "{\"name\":\"Book\",\"quantity\":2}";
    }
}

abstract class ReportService {
    // Thuật toán chung gọi điểm mở rộng do subclass cung cấp.
    public final void printReport() {
        Report report = createReport();
        System.out.println(report.render());
    }

    protected abstract Report createReport(); // Factory Method
}

final class CsvReportService extends ReportService {
    @Override
    protected Report createReport() {
        return new CsvReport();
    }
}

final class JsonReportService extends ReportService {
    @Override
    protected Report createReport() {
        return new JsonReport();
    }
}

// Cách dùng:
ReportService service = new CsvReportService();
service.printReport();
~~~

Here, `createReport()` is an overridden **instance method**; it need not be `static`. Thus, a “static factory method” and the “Factory Method design pattern” are different concepts.

**Trade-off:** A factory using `switch` centralizes selection, but adding a new channel still requires modifying the `switch`; it does not automatically satisfy the Open/Closed Principle in every case. Larger projects may register implementations through `Map<Channel, Supplier<Notifier>>`, dependency injection, or a suitable configuration strategy. Avoid excessive Factory layers for a single simple object type.

## 4. Builder: Configure Step by Step Before Creating an Object

Constructors with many parameters are easy to misuse and hard to extend:

~~~java
// Người đọc khó biết 0, 20 và true tương ứng tham số nào:
SearchRequest request = new SearchRequest("java", 0, 20, true);
~~~

Adding more optional parameters creates an increasingly difficult “forest of constructors” (telescoping constructors). The **Builder pattern** solves this with an intermediate object whose clearly named methods configure the result; the final object is created only when `build()` is called.

For example, `SearchRequest` has a required query and optional `page`, `pageSize`, and filter tags.

`SearchRequest.java` (Java 11+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class SearchRequest {
    private final String keyword;
    private final int page;
    private final int pageSize;
    private final List<String> tags;

    private SearchRequest(Builder builder) {
        this.keyword = builder.keyword;
        this.page = builder.page;
        this.pageSize = builder.pageSize;
        this.tags = List.copyOf(builder.tags); // Snapshot, không lộ List mutable
    }

    public static Builder builder(String keyword) {
        return new Builder(keyword);
    }

    public String getKeyword() { return keyword; }
    public int getPage() { return page; }
    public int getPageSize() { return pageSize; }
    public List<String> getTags() { return tags; }

    public static final class Builder {
        private final String keyword;
        private int page = 0;          // Giá trị mặc định
        private int pageSize = 20;     // Giá trị mặc định
        private final List<String> tags = new ArrayList<>();

        private Builder(String keyword) {
            String clean = Objects.requireNonNull(keyword, "keyword").trim();
            if (clean.isEmpty()) {
                throw new IllegalArgumentException("Keyword không được rỗng");
            }
            this.keyword = clean;
        }

        public Builder page(int page) {
            if (page < 0) {
                throw new IllegalArgumentException("Page phải >= 0");
            }
            this.page = page;
            return this;
        }

        public Builder pageSize(int pageSize) {
            if (pageSize < 1 || pageSize > 100) {
                throw new IllegalArgumentException("Page size phải trong [1, 100]");
            }
            this.pageSize = pageSize;
            return this;
        }

        public Builder addTag(String tag) {
            String clean = Objects.requireNonNull(tag, "tag").trim();
            if (clean.isEmpty()) {
                throw new IllegalArgumentException("Tag không được rỗng");
            }
            this.tags.add(clean);
            return this;
        }

        public SearchRequest build() {
            return new SearchRequest(this);
        }
    }
}
~~~

`SearchDemo.java`:

~~~java
public class SearchDemo {
    public static void main(String[] args) {
        SearchRequest request = SearchRequest.builder("  java oop  ")
                .page(2)
                .pageSize(25)
                .addTag("core")
                .addTag("interview")
                .build();

        System.out.println(request.getKeyword()); // java oop
        System.out.println(request.getPage());    // 2
        System.out.println(request.getPageSize()); // 25
        System.out.println(request.getTags());    // [core, interview]

        // Khi chỉ có tham số bắt buộc, dùng được giá trị mặc định:
        SearchRequest defaults = SearchRequest.builder("spring").build();
        System.out.println(defaults.getPageSize()); // 20
    }
}
~~~

Analyzing the flow:

~~~mermaid
flowchart TD
    A["SearchRequest.builder(keyword)"] --> B["Tạo Builder, kiểm tra keyword"]
    B --> C["page(), pageSize(), addTag()"]
    C --> D["Builder lưu cấu hình và trả this"]
    D --> E["build()"]
    E --> F["new SearchRequest(builder)"]
    F --> G["Sao chép List; đối tượng kết quả bất biến"]
~~~

- `builder(...)` is a **static factory for a Builder**; it does not yet create `SearchRequest`.
- `page(...), pageSize(...), addTag(...)` update the Builder's **mutable** state and return `this` for fluent chaining.
- `build()` invokes the `private SearchRequest(Builder)` constructor and returns the configured object.
- `List.copyOf(builder.tags)` protects the `SearchRequest` list from later changes to the Builder. Since `String` is immutable, its elements cannot be changed in place either.

Checking what happens when a Builder is reused:

~~~java
SearchRequest.Builder builder = SearchRequest.builder("oop");
builder.addTag("basic");

SearchRequest first = builder.build();

builder.addTag("advanced");
SearchRequest second = builder.build();

System.out.println(first.getTags());  // [basic]
System.out.println(second.getTags()); // [basic, advanced]
System.out.println(first == second);  // false
~~~

**Note:** The Builder in this example is mutable and **not designed to be thread-safe**; do not share it among threads that modify it concurrently. `build()` is also **not required to create a new instance** under every Builder API, but in our sample implementation, each call executes `new SearchRequest(...)`.

## 5. Choosing the Right Creation Approach

| Criterion | Constructor | Static Factory Method | Separate Factory | Builder |
| --- | --- | --- | --- | --- |
| Typical syntax | `new Order(...)` | `Order.from(...)` | `factory.create(...)` | `Order.builder().build()` |
| Main purpose | Direct initialization | Naming a creation path or choosing return behavior | Centralizing implementation selection and dependency creation | Configuring many parameters clearly |
| Must each call create a new instance? | Yes, when using `new` | Not necessarily | Not necessarily | Depends on the contract of `build()` |
| Optional parameters | Use overloads, which may become confusing | Overloads are possible | API-dependent | Convenient for many options |
| Hide concrete implementation class | No, when invoked directly | Possible | Common | Possible |
| Design cost | Low | Low to moderate | Moderate | Moderate to high |

Some quick selection examples:

- **`Point(int x, int y)`**: simple data with few parameters and straightforward creation → a constructor is usually enough.
- **`Temperature.celsius(30)` / `fahrenheit(86)`**: the same parameter type has different meanings → use static factories.
- **Select an encoder/notification sender from configuration** → use a Factory to supply the appropriate interface.
- **Configure many required/optional fields, including defaults and validation** → use a Builder.
- **Create complex objects with both implementation selection and stepwise configuration** → a Factory may supply a Builder, followed by `build()`.

These techniques **are not mutually exclusive**: a class can have a `private` constructor, a static factory returning a `Builder`, another Factory selecting implementations, and the Builder invoking the constructor to create the result.

## 6. Relationship to Dependency Injection and Spring

In Spring applications, the container is often responsible for creating and managing beans and injecting dependencies. Therefore, a real project Factory may need **injected dependencies** instead of constructing every service with `new`.

A minimal illustration:

~~~java
import org.springframework.stereotype.Component;

@Component
public class NotifierSelector {
    private final EmailService emailService;
    private final SmsService smsService;

    public NotifierSelector(EmailService emailService, SmsService smsService) {
        this.emailService = emailService;
        this.smsService = smsService;
    }

    public MessageSender select(Channel channel) {
        return switch (channel) {
            case EMAIL -> emailService;
            case SMS -> smsService;
        };
    }
}
~~~

This assumes `EmailService` and `SmsService` are existing beans implementing `MessageSender`, and `Channel` is an enum with `EMAIL` and `SMS`. The code illustrates **Spring integration**; it is not a standalone Java program like the previous examples. Here, `select` **returns an existing managed bean**, rather than creating a service. Avoid `new EmailService()` in application logic if the service relies on Spring injection, interceptors, transaction proxies, or lifecycle callbacks.

In Spring, an `@Bean` annotation on a configuration method can return an object for container management, but that does not mean every `@Bean` method is a static factory method. Distinguish the **framework's bean management mechanism** from **object-creation patterns in plain Java**.

## 7. Common Errors and Misconceptions

**1. Assuming Static Factories Always Create New Instances**

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);

System.out.println(a.equals(b)); // true
// a == b không nên dùng để kiểm tra bằng nhau về giá trị.
~~~

`valueOf` may use caching; applications should follow the **value contract** (using `equals` to compare values), not depend on which instance a factory allocates. Sharing a mutable object can cause unintended state changes, so cache or share such instances only deliberately.

**2. Putting Heavy Business Logic or I/O into Every Constructor/Factory**

Constructors and factories should ensure valid state. I/O may be necessary by design, but failures, resources, latency, and side effects must be explicit. Do not turn every `new` or `of` into an unexpected network call.

**3. Assuming Builders Automatically Guarantee Immutability**

A Builder is often mutable, and the constructed object may also be mutable if fields, setters, or collections are exposed. For immutable results, use `private final` fields, validate inputs, defensively copy mutable state, avoid public setters, and take care with nested elements.

**4. Validating Individual Setters but Ignoring Cross-Field Constraints**

If `startDate` must precede `endDate`, validating `startDate(...)` and `endDate(...)` separately may not be sufficient. Check the combined constraint in `build()` or the final constructor:

~~~java
public TimeRange build() {
    if (start == null || end == null || !start.isBefore(end)) {
        throw new IllegalStateException("Khoảng thời gian không hợp lệ");
    }
    return new TimeRange(start, end);
}
~~~

The code above sketches `build()` for a Builder with `start` and `end` fields of type `LocalDateTime` (or another comparable time type); it emphasizes **when to validate whole-object invariants**.

**5. Overengineering**

A class with two clear parameters does not need a hundreds-of-lines Builder. There is no need to create a `FactoryFactory` solely to wrap a single `new` statement. Choose abstractions when they improve call-site meaning, implementation extensibility, or control over creation.

**6. Misunderstanding Inheritance and Factories**

Constructors cannot be overridden. Java static methods can be subject to **method hiding**, which is different from instance-polymorphic overriding; they do not offer the same extension point as a `protected createProduct()` method in the GoF Factory Method pattern. For polymorphic creation, consider Factory Method, Abstract Factory, or dependency injection.

## 8. Practice Questions

**Question 1:** Why can't the constructors `Temperature(double celsius)` and `Temperature(double fahrenheit)` coexist?

**Answer:** They have the same parameter-type signature. Parameter names do not distinguish overloads; named static factories `celsius` and `fahrenheit` solve the problem.

**Question 2:** Must `Temperature.fahrenheit(86)` create a new object?

**Answer:** Yes in the sample implementation, because it calls `new Temperature(...)`. But static factory methods in general need not; a factory may return an existing object.

**Question 3:** How do `NotifierFactory.create(Channel.EMAIL)` and `ReportService.createReport()` differ?

**Answer:** The former is a **Simple Factory** using a static method with `switch` to select an implementation; the latter uses the **Factory Method pattern**, allowing subclasses to override creation of `Report`.

**Question 4:** Why do Builders commonly use `return this`?

**Answer:** To enable fluent chaining such as `builder.page(1).pageSize(30).build()`. This is a fluent API; steps before `build()` modify the **Builder**, without necessarily creating the result object.

**Question 5:** Why is `List.copyOf(builder.tags)` used in the `SearchRequest` constructor?

**Answer:** To snapshot the list at construction. If the Builder later adds tags, an existing `SearchRequest` stays unchanged; callers also cannot modify the getter's list through `add/remove`.

**Question 6:** What would you choose for an immutable class with only required `id` and `name` fields?

**Answer:** A simple validating constructor is usually sufficient; add a static factory if a special creation path needs a meaningful name. There is no default requirement to use a Builder.

**Remember:** Constructors create instances directly; static factories **name and control how objects are obtained**; Factories **select and supply implementations**; Builders **collect configuration and then complete objects**. Choose techniques based on creation needs and class invariants instead of applying a design pattern everywhere.
