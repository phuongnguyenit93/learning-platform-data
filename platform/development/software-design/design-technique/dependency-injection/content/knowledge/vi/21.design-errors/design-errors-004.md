# Service Locator, container toàn cục và phụ thuộc ẩn

**Dependency Injection (DI)** tách việc **sử dụng một phụ thuộc** khỏi việc **chọn, tạo và lắp ghép phụ thuộc đó**. Với constructor injection, một lớp nghiệp vụ khai báo những collaborator bắt buộc ngay trong chữ ký constructor; composition root tạo và truyền các đối tượng cụ thể từ bên ngoài.

**Service Locator** dễ gây nhầm lẫn vì nó cũng có thể trả về đối tượng qua interface. Thay vì nhận phụ thuộc, lớp nghiệp vụ chủ động gọi một registry hoặc container để **tìm** phụ thuộc khi cần. Nếu registry ấy nằm trong biến `static` toàn cục, vấn đề còn lan sang vòng đời ứng dụng, khả năng kiểm thử và việc xử lý nhiều request cùng lúc.

Bài học thuộc chương **Lỗi thiết kế** của module **DEPENDENCY_INJECTION**. Ta sẽ phân tích vì sao *một chương trình dùng interface và có container* chưa chắc đang áp dụng DI đúng ranh giới, cách nhận diện **phụ thuộc ẩn**, cùng cách chuyển dần từ service locator sang **constructor injection + composition root**. Toàn bộ ví dụ thực hành dùng **Java thuần** trước khi cân nhắc DI container của framework.

Sau bài này, bạn có thể:

- Phân biệt **Service Locator** với **Dependency Injection**, kể cả khi cùng sử dụng một API container.
- Nhận diện container toàn cục, mutable static registry và các cách giấu phụ thuộc khỏi chữ ký constructor.
- Giải thích tác động đến tính đúng khi khởi tạo, khả năng thay thế adapter, vòng đời/scope, đồng thời và kiểm thử.
- Xác định **đâu là chỗ hợp lệ để gọi container** và đâu là việc tra cứu dependency đang rò vào nghiệp vụ.
- Refactor từng bước để khai báo các hợp đồng cần dùng và tập trung việc lắp ghép ở composition root.
- Kiểm thử service trực tiếp bằng fake mà không phải thiết lập hoặc reset trạng thái toàn cục.

## 1. Service Locator là gì?

**Service Locator** là mẫu mà một đối tượng **chủ động truy vấn một nguồn dịch vụ** để lấy các dependency của mình, thường bằng khóa kiểu, tên hoặc chuỗi:

~~~java
// Minh họa API lookup; tên lớp chỉ dùng để giải thích.
OrderRepository orders =
        ServiceRegistry.get(OrderRepository.class);
~~~

Một registry có thể cung cấp đúng một `OrderRepository` cụ thể. Tuy nhiên, **từ góc nhìn người sử dụng lớp nghiệp vụ**, dependency có thể không hề xuất hiện ở nơi tạo lớp ấy.

~~~java
final class CheckoutService {
    // Không có tham số constructor.
    void checkout(Order order) {
        OrderRepository orders =
                GlobalServices.get(OrderRepository.class);
        orders.save(order);
    }
}

// Nhìn vào đây không biết CheckoutService cần OrderRepository.
CheckoutService checkout = new CheckoutService();
~~~

Nếu registry chưa đăng ký `OrderRepository`, việc tạo `CheckoutService` vẫn có thể thành công; lỗi chỉ xảy ra khi `checkout()` được gọi. Đó là một biểu hiện điển hình của **phụ thuộc ẩn** (*hidden dependency*).

So sánh với constructor injection:

~~~java
final class CheckoutService {
    private final OrderRepository orders;

    CheckoutService(OrderRepository orders) {
        this.orders = java.util.Objects.requireNonNull(orders);
    }

    void checkout(Order order) {
        orders.save(order);
    }
}
~~~

Trong phiên bản sau, muốn có `CheckoutService` hợp lệ phải cấp một `OrderRepository`. Điểm khác biệt không nằm ở chuyện có dùng interface hay không; nó nằm ở **ai quyết định và ai chủ động lấy dependency**.

### Sơ đồ luồng phụ thuộc

~~~mermaid
flowchart LR
    subgraph Locator["Service Locator"]
        CallerA["Caller"] --> ServiceA["CheckoutService"]
        ServiceA -->|"get(OrderRepository)"| Registry["Global registry"]
        Registry --> AdapterA["Repository adapter"]
    end
    subgraph DI["Constructor injection"]
        Root["Composition root"] -->|"tạo"| AdapterB["Repository adapter"]
        Root -->|"new CheckoutService(adapter)"| ServiceB["CheckoutService"]
        ServiceB -->|"gọi qua interface"| AdapterB
    end
~~~

Ở mô hình Service Locator, mã nghiệp vụ có **cạnh phụ thuộc đến cơ chế tra cứu**. Ở mô hình constructor DI, mã lắp ghép nằm ở ranh giới ngoài; mã nghiệp vụ dùng dependency đã được cung cấp.

## 2. So sánh theo những điều lập trình viên thực sự cần

| Tiêu chí | Service Locator trong mã nghiệp vụ | Constructor injection |
| --- | --- | --- |
| Phụ thuộc bắt buộc thể hiện ở đâu? | Trong thân phương thức hoặc lời gọi locator | Trong tham số constructor |
| Tạo đối tượng thiếu dependency | Có thể thành công, lỗi xuất hiện khi lookup | Có thể từ chối ngay tại constructor nếu dependency thiếu |
| Muốn thay adapter trong unit test | Cần cài đặt/giả lập registry hoặc container | Truyền fake trực tiếp |
| Mức độ gắn với cơ chế DI | Class phải biết lookup API hoặc global holder | Class chỉ cần biết interface nghiệp vụ |
| Đọc object graph từ composition root | Không thấy đủ các cạnh bị lookup ở runtime | Thấy rõ các constructor và cách lắp ghép |
| Scope và vòng đời | Dễ tra cứu ngoài scope hoặc giữ instance nhầm | Vẫn cần thiết kế scope, nhưng dependency được cấp ở ranh giới rõ |
| Refactor khi thêm dependency | Có thể chỉ thêm lookup trong thân code | Constructor thay đổi; các nơi tạo class buộc phải xem lại |
| Nguy cơ phụ thuộc ẩn | Cao nếu lookup nằm trong logic nghiệp vụ | Thấp hơn với các collaborator bắt buộc |

Constructor injection **không tự bảo đảm toàn bộ kiến trúc đúng**. Vẫn có thể truyền một abstraction quá rộng, dùng singleton mutable sai hoặc tạo một vòng phụ thuộc. Nhưng nó làm **các nhu cầu của class hiển thị ở ranh giới khởi tạo**, hỗ trợ phát hiện vấn đề sớm hơn.

### Dấu hiệu quan trọng: dependency chưa được khai báo ở API

Hãy thử đưa constructor của service cho một đồng nghiệp chưa đọc thân class. Họ có biết những hệ thống nào cần có để sử dụng service không?

Với:

~~~java
new PaymentService();
~~~

không thể biết bên trong service có tự lấy `PaymentGateway`, `AuditTrail` và `Clock` hay không.

Với:

~~~java
new PaymentService(gateway, audit, clock);
~~~

điều kiện tạo hợp lệ hiện rõ. Composition root hoặc DI container cũng có một **danh sách dependency có kiểu** để lắp ghép thay vì phải biết mỗi phương thức nghiệp vụ sẽ lookup gì.

## 3. Container toàn cục là phiên bản đặc biệt rủi ro

Một biến `static` có thể khiến một registry truy cập được từ mọi nơi:

~~~java
// Minh họa kiểu thiết kế dễ gây rủi ro.
public final class GlobalContainer {
    public static Object get(String name) {
        // Trả về đối tượng đã đăng ký trước đó.
        throw new UnsupportedOperationException();
    }
}
~~~

Vấn đề không chỉ là sử dụng `static`. Những hệ quả đáng lưu ý khi registry **mutable, toàn cục và được gọi từ nhiều service** là:

- **Thứ tự khởi tạo ngầm:** class hoạt động hay không tùy có ai đã đăng ký đúng dịch vụ trước đó.
- **Trạng thái giữa các bài test:** test A thay binding, test B quên reset và dùng nhầm fake.
- **Nhiều ứng dụng/context trong một JVM:** một registry có thể trộn các graph lắp ghép lẽ ra độc lập.
- **Lỗi đa luồng:** đăng ký hoặc thay binding khi các thread đang lookup có thể gây race; thêm `ConcurrentHashMap` chưa sửa được lỗi về ý nghĩa scope.
- **Quyền sở hữu không rõ:** đối tượng trả về thuộc container, request hay caller? Ai được đóng nó?
- **Khó tìm nơi sử dụng:** API `get(String)` hoặc `get(Class<?>)` có thể xuất hiện ở nhiều nơi, làm object graph khó truy vết.

Không phải mọi dữ liệu `static` đều là Service Locator. **Hằng số bất biến** hoặc hàm tiện ích không tra cứu collaborator không có vấn đề này. Mẫu đáng cảnh giác là một **điểm truy cập toàn cục chứa hoặc giải quyết những dịch vụ đang thay đổi theo cấu hình và vòng đời**.

### Hai cấu hình test có thể ảnh hưởng nhau

~~~text
Test A:
  GlobalContainer.register(PaymentGateway, FakeGatewayA)
  new PaymentService().pay(...)  -> FakeGatewayA

Test B:
  GlobalContainer.register(PaymentGateway, FakeGatewayB)
  new PaymentService().pay(...)  -> FakeGatewayB

Nếu hai test chạy song song hoặc reset không đúng:
  A có thể sử dụng FakeGatewayB, hoặc B dùng binding của A.
~~~

Đây là ví dụ về *test contamination*. Khi service được inject trực tiếp, mỗi bài test có thể tạo **đồ thị riêng**:

~~~java
PaymentService serviceA = new PaymentService(fakeGatewayA);
PaymentService serviceB = new PaymentService(fakeGatewayB);
~~~

Hai service không phải tranh giành một registry toàn cục. Tuy nhiên, các fake dùng chung một nguồn dữ liệu static hoặc tài nguyên hạ tầng vẫn có thể làm test nhiễu; DI làm ranh giới rõ hơn, chứ không tự cô lập mọi trạng thái.

## 4. Service Locator không đồng nghĩa DI container

Một **DI container** có thể có API `getBean(...)`, `resolve(...)` hoặc tương tự. **API ấy được gọi ở đâu** quyết định nó đang phục vụ composition root hay đang bị sử dụng như service locator trong nghiệp vụ.

~~~java
// HỢP LÝ: entry point / composition root lấy service đã lắp ghép.
CheckoutService checkout = container.resolve(CheckoutService.class);
checkout.checkout(order);
~~~

Ở đây, việc lấy một **entry service** tại bootstrap hoặc ranh giới tích hợp là một cách giao phần wiring cho container. `CheckoutService` không biết container tồn tại và nhận dependency qua constructor.

~~~java
// KHÔNG KHUYẾN KHÍCH: service nghiệp vụ chủ động tìm dependency.
final class CheckoutService {
    private final Container container;

    CheckoutService(Container container) {
        this.container = container;
    }

    void checkout(Order order) {
        OrderRepository orders =
                container.resolve(OrderRepository.class);
        orders.save(order);
    }
}
~~~

Dù `Container` đã được **inject qua constructor**, phần nghiệp vụ vẫn chứa **hành vi Service Locator**: nó phụ thuộc vào **cơ chế truy vấn động**, còn `OrderRepository` cần dùng vẫn không hiện trong chữ ký. “Inject container” không tương đương “inject các dependency thực sự cần thiết”.

### Ranh giới sử dụng container phù hợp

| Nơi sử dụng | Đánh giá | Lý do |
| --- | --- | --- |
| `main`, bootstrap hoặc composition root | Thường phù hợp | Đây là nơi xây/lấy object graph để chạy ứng dụng |
| Framework adapter ở ranh giới request/job | Có thể phù hợp | Adapter nhận entry service từ container và chuyển dữ liệu vào nghiệp vụ |
| Module cấu hình/registration | Phù hợp khi có chủ đích | Nơi khai báo binding, scope, lifecycle |
| Service nghiệp vụ, domain object | Nên tránh | Dependency ẩn, ghép nối với cơ chế tra cứu |
| Factory có kiểu, được inject rõ ràng | Có thể phù hợp | Hợp đồng tạo đối tượng cần thiết hiện ở constructor |
| Static global holder cho mọi class gọi `get(...)` | Nên tránh | Trộn scope và che các cạnh trong object graph |

**Service Locator là vấn đề ở *mẫu sử dụng*, không nhất thiết ở bản thân một lớp có tên Registry hoặc Container.** Một registry có thể là chi tiết bên trong composition root; nó trở thành nguồn phụ thuộc ẩn khi consumer tự dùng nó để tìm collaborator.

## 5. Các dạng phụ thuộc ẩn ngoài `GlobalContainer.get()`

Không phải mọi phụ thuộc ẩn đều được viết thành một lời gọi `get` dễ nhìn:

| Dạng | Biểu hiện | Tác động |
| --- | --- | --- |
| **Static holder** | `Services.repository()` | Mã nghiệp vụ dựa vào object được thiết lập toàn cục |
| **Thread-local locator** | `CurrentContext.repository()` | Phụ thuộc vào thread/scope ngầm; async có thể mất hoặc rò context |
| **Service locator qua interface** | Inject `ServiceResolver` rồi gọi `resolver.get(OrderRepository.class)` | Constructor cho thấy resolver, không cho thấy repository thật |
| **Container injection** | Inject `ApplicationContext` hoặc `BeanFactory` để gọi `getBean` mọi nơi | Domain logic bị ràng buộc với framework |
| **Tên chuỗi/khóa động** | `registry.get("payment")` rồi ép kiểu | Sai tên/kiểu thường lộ lúc chạy |
| **Constructor tự đọc environment** | `new PaymentService()` rồi gọi `System.getenv()` và tự dựng adapter | Ẩn chính sách cấu hình và lắp ghép |
| **Factory vạn năng** | `factory.create(Class<T>)` dùng từ mọi service | Có thể chỉ là locator đổi tên |
| **Field injection không tường minh** | Một field được framework gán sau constructor | Phụ thuộc bắt buộc khó thấy tại điểm tạo bằng Java thuần |

Không phải mọi hình thức lấy giá trị từ ambient context đều sai theo cùng cách. Chẳng hạn, thư viện logging/tracing có thể có cơ chế ambient context riêng với ràng buộc rõ; nhưng nếu **quy tắc nghiệp vụ cần một collaborator quan trọng**, hãy ưu tiên **hợp đồng và tham số tường minh**. Đặc biệt, request/tenant data không nên được lấy ngầm từ một singleton mutable khi chuyển qua thread khác.

## 6. Rủi ro về thiết kế, thời điểm lỗi và khả năng thay thế

Một service lookup dependency trong phương thức có thể biên dịch thành công dù không có binding nào:

~~~java
final class InvoiceService {
    void issue(Invoice invoice) {
        InvoiceRepository repository =
                GlobalServices.get(InvoiceRepository.class);
        repository.save(invoice);
    }
}
~~~

Ở đây, lời gọi `new InvoiceService()` không có cơ hội xác nhận rằng `InvoiceRepository` tồn tại. Lỗi có thể xuất hiện ở một nhánh hiếm khi `issue()` chạy.

Constructor injection thể hiện điều kiện ngay lúc lắp ghép:

~~~java
final class InvoiceService {
    private final InvoiceRepository repository;

    InvoiceService(InvoiceRepository repository) {
        this.repository = java.util.Objects.requireNonNull(
                repository, "repository");
    }

    void issue(Invoice invoice) {
        repository.save(invoice);
    }
}
~~~

Nếu code gọi `new InvoiceService()` mà không truyền tham số, **trình biên dịch phát hiện không có constructor tương ứng**. Nếu truyền `null`, constructor có thể từ chối sớm. Tuy nhiên, Java không tự kiểm tra rằng một adapter thực thi hợp đồng nghiệp vụ đúng; điều đó vẫn cần tài liệu và contract/integration tests.

### Hướng phụ thuộc bị đảo sai

Về mặt Dependency Inversion Principle (DIP), nghiệp vụ nên phụ thuộc vào **abstraction ổn định do nhu cầu nghiệp vụ quyết định**. Khi service import API container, nó đang phụ thuộc vào **hạ tầng lắp ghép** để lấy một abstraction khác.

~~~mermaid
flowchart LR
    subgraph Hidden["Locator trong nghiệp vụ"]
        BusinessA["Business service"] --> Resolver["Global container / resolver"]
        Resolver --> ConcreteA["Concrete adapter"]
    end
    subgraph Explicit["Constructor DI"]
        App["Composition root"] --> Port["Business port"]
        App --> Adapter["Concrete adapter"]
        BusinessB["Business service"] --> Port
        Adapter -.->|"implements"| Port
    end
~~~

Điểm quan trọng không phải “cấm service biết một kiểu nào đó từ thư viện”, mà là giữ **quyết định tạo, chọn và tìm collaborator** ở ranh giới phù hợp. Một cổng `OrderRepository` do use case cần thường có ý nghĩa hơn một `GlobalServiceRegistry` chỉ cung cấp khả năng tìm bất kỳ thứ gì.

## 7. Ví dụ Java 17: so sánh service locator với constructor injection

Chương trình dưới đây dùng **Java 17+**, không cần thư viện ngoài. Nó chứa một registry toàn cục **cố ý sai về mặt thiết kế** để quan sát phụ thuộc ẩn, và phiên bản service đúng hơn nhận repository cùng sender qua constructor.

Registry này chỉ là công cụ minh họa; nó không có cơ chế scope, shutdown hay đồng bộ, **không được sử dụng làm DI container production**.

Lưu vào `Main.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

record Order(String id, long amountCents) {
    Order {
        if (id == null || id.isBlank() || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

interface OrderRepository {
    void save(Order order);
}

interface ReceiptSender {
    void send(Order order);
}

// Adapter cụ thể; logic chi tiết không thuộc service.
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        Objects.requireNonNull(order, "order");
        if (orders.putIfAbsent(order.id(), order) != null) {
            throw new IllegalArgumentException(
                    "Duplicate order: " + order.id());
        }
        System.out.println("STORE: " + order.id());
    }
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void send(Order order) {
        System.out.println("RECEIPT: " + order.id());
    }
}

// CHỈ ĐỂ MINH HỌA ANTI-PATTERN.
// Mutable global registry, không được thiết kế cho nhiều thread.
final class GlobalServices {
    private static final Map<Class<?>, Object> VALUES = new HashMap<>();

    private GlobalServices() {}

    static <T> void install(Class<T> type, T service) {
        VALUES.put(
                Objects.requireNonNull(type, "type"),
                type.cast(Objects.requireNonNull(service, "service")));
    }

    static <T> T get(Class<T> type) {
        Object value = VALUES.get(Objects.requireNonNull(type, "type"));
        if (value == null) {
            throw new IllegalStateException(
                    "Missing binding: " + type.getSimpleName());
        }
        return type.cast(value);
    }

    static void clear() {
        VALUES.clear();
    }
}

// Có phụ thuộc ẩn: không nhận repository/sender tại constructor.
final class HiddenCheckout {
    void checkout(Order order) {
        Objects.requireNonNull(order, "order");

        OrderRepository orders = GlobalServices.get(OrderRepository.class);
        ReceiptSender sender = GlobalServices.get(ReceiptSender.class);

        orders.save(order);
        sender.send(order);
    }
}

// Constructor DI: hợp đồng bắt buộc nhìn thấy tại nơi tạo class.
final class CheckoutService {
    private final OrderRepository orders;
    private final ReceiptSender sender;

    CheckoutService(OrderRepository orders, ReceiptSender sender) {
        this.orders = Objects.requireNonNull(orders, "orders");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void checkout(Order order) {
        Objects.requireNonNull(order, "order");
        orders.save(order);
        sender.send(order);
    }
}

// Composition root: lựa chọn và lắp ghép object graph.
public class Main {
    public static void main(String[] args) {
        GlobalServices.clear();
        HiddenCheckout hidden = new HiddenCheckout();

        // Lỗi chỉ xuất hiện khi phương thức dùng dependency được gọi.
        try {
            hidden.checkout(new Order("MISSING", 1_000));
        } catch (IllegalStateException expected) {
            System.out.println("Hidden failure: " + expected.getMessage());
        }

        // Cần thiết lập state toàn cục trước khi service ẩn hoạt động.
        GlobalServices.install(
                OrderRepository.class, new InMemoryOrderRepository());
        GlobalServices.install(
                ReceiptSender.class, new ConsoleReceiptSender());

        hidden.checkout(new Order("BAD-01", 10_000));

        // Cách rõ hơn: tạo các collaborator tại composition root.
        OrderRepository repository = new InMemoryOrderRepository();
        ReceiptSender sender = new ConsoleReceiptSender();

        CheckoutService explicit =
                new CheckoutService(repository, sender);
        explicit.checkout(new Order("GOOD-01", 20_000));

        GlobalServices.clear(); // chỉ dọn dữ liệu minh họa
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Đầu ra dự kiến:

~~~text
Hidden failure: Missing binding: OrderRepository
STORE: BAD-01
RECEIPT: BAD-01
STORE: GOOD-01
RECEIPT: GOOD-01
~~~

### Điều gì được quan sát?

1. **`HiddenCheckout` tạo được dù thiếu dependency.** Lỗi “Missing binding” xuất hiện khi `checkout()` mới thực hiện lookup.
2. **Registry toàn cục là điều kiện tiên quyết ngầm.** Không thể chỉ nhìn constructor của `HiddenCheckout` để biết phải cài `OrderRepository` và `ReceiptSender`.
3. **`CheckoutService` nhận dependency bằng constructor.** Không cần truy cập `GlobalServices` để xây hoặc chạy service.
4. **Cùng một hợp đồng nghiệp vụ vẫn được sử dụng.** Sự khác biệt là cách cấp dependency, không phải `OrderRepository` có còn là interface hay không.
5. **Composition root là điểm lựa chọn adapter.** Nó có thể chuyển từ repository trong RAM sang JDBC mà không cần thay logic `CheckoutService` nếu adapter giữ đúng hợp đồng.

**Giới hạn ví dụ:** `HashMap` trong cả registry và repository chỉ dành cho chương trình console đơn luồng. Đối với server nhiều thread, phải thiết kế tính đồng thời riêng. Ngoài ra, `save()` thành công rồi `send()` thất bại có thể để lại trạng thái đã lưu mà chưa gửi biên nhận; DI không tự thêm transaction hoặc bảo đảm gửi đúng một lần.

## 8. Kiểm thử service không cần khởi tạo registry

Với constructor DI, test có thể thay adapter bằng fake chỉ dùng Java thuần. Mỗi lần kiểm thử dựng một service và danh sách lời gọi riêng; không cần `GlobalServices.clear()` hay thứ tự khởi chạy đặc biệt.

Lưu `CheckoutServiceTest.java` cùng thư mục với `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CheckoutServiceTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> calls = new ArrayList<>();

        // Cả hai interface chỉ có một phương thức.
        OrderRepository repository =
                order -> calls.add("save:" + order.id());
        ReceiptSender sender =
                order -> calls.add("send:" + order.id());

        CheckoutService service =
                new CheckoutService(repository, sender);

        service.checkout(new Order("TEST-01", 15_000));

        check(calls.equals(List.of(
                "save:TEST-01",
                "send:TEST-01")),
                "Checkout must save before sending receipt");

        // Nếu lưu thất bại, không được gửi biên nhận.
        OrderRepository failingRepository = order -> {
            throw new IllegalStateException("Store unavailable");
        };
        ReceiptSender mustNotSend = order -> {
            throw new AssertionError("Should not send after save failure");
        };

        CheckoutService failed =
                new CheckoutService(failingRepository, mustNotSend);

        boolean expectedFailure = false;
        try {
            failed.checkout(new Order("TEST-FAIL", 20_000));
        } catch (IllegalStateException expected) {
            expectedFailure = true;
        }
        check(expectedFailure, "Storage failure must be visible");

        // Phụ thuộc bắt buộc được kiểm tra ngay khi tạo.
        boolean missingRepositoryRejected = false;
        try {
            new CheckoutService(null, sender);
        } catch (NullPointerException expected) {
            missingRepositoryRejected = true;
        }
        check(missingRepositoryRejected,
                "Null repository must be rejected at construction");

        boolean missingSenderRejected = false;
        try {
            new CheckoutService(repository, null);
        } catch (NullPointerException expected) {
            missingSenderRejected = true;
        }
        check(missingSenderRejected,
                "Null sender must be rejected at construction");

        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java CheckoutServiceTest.java
java CheckoutServiceTest
~~~

Kết quả dự kiến: `PASS`.

Bài test chỉ chứng minh **điều phối của `CheckoutService` với các fake**, không chứng minh repository/JDBC thật bền vững hoặc sender thật gửi thành công. Test adapter và tích hợp cần được viết riêng theo hợp đồng tương ứng.

### Nếu phải test `HiddenCheckout` thì sao?

Test buộc phải làm thêm các bước không xuất hiện trong constructor:

~~~java
// Minh họa tác động của hidden dependency.
GlobalServices.clear();
GlobalServices.install(OrderRepository.class, fakeRepository);
GlobalServices.install(ReceiptSender.class, fakeSender);

new HiddenCheckout().checkout(order);

GlobalServices.clear(); // dễ quên nếu test thất bại giữa chừng
~~~

Nếu vẫn tạm duy trì code cũ, nên dùng `try/finally` để reset trạng thái test hoặc chạy test trong môi trường cách ly. Nhưng cleanup chỉ là **biện pháp giảm thiểu trong giai đoạn chuyển đổi**, không làm dependency trở nên tường minh. Test chạy song song trên cùng mutable global registry vẫn có nguy cơ can thiệp nhau.

## 9. Container và tính nhất quán scope: “lookup lúc nào” không phải chuyện nhỏ

Một locator động có thể trả:

- **Singleton:** nhiều lần lookup nhận cùng một instance trong phạm vi container.
- **Transient/prototype:** nhiều lần lookup có thể tạo những instance khác nhau.
- **Request-scoped:** kết quả phụ thuộc request context hiện tại.
- **Unit-of-work context:** kết quả được tái sử dụng theo công việc hiện hành.

Nếu service tự gọi `locator.get(Session.class)` nhiều lần, nó đang ngầm quyết định **thời điểm resolve** và có thể vô tình đổi session giữa các bước thuộc cùng một đơn vị công việc.

~~~java
// Minh họa lỗi ngữ nghĩa khi provider tạo mới mỗi lần.
void processOrder(String id) {
    WorkUnit first = globalLocator.get(WorkUnit.class);
    first.modify(id);

    WorkUnit second = globalLocator.get(WorkUnit.class);
    second.commit(); // có thể không quản lý thay đổi của first
}
~~~

Trong đoạn trên, nếu locator trả cùng một unit thì hành vi khác; nếu trả unit mới thì sai. **Hợp đồng phải cho biết các bước có cần một instance chung hay không**. Tự lookup nhiều lần che quyết định ấy khỏi ranh giới use case và khiến lỗi khó phát hiện.

Cách rõ hơn: **composition root hoặc application coordinator** tạo một unit rồi truyền đúng instance vào toàn bộ bước xử lý:

~~~java
// Mã khái niệm; WorkUnit và các service được giả định đã khai báo.
try (WorkUnit unit = factory.open()) {
    DiscountService discount = new DiscountService(unit);
    ApprovalService approval = new ApprovalService(unit);

    discount.apply(orderId);
    approval.approve(orderId);
    unit.commit();
}
~~~

Đoạn này chưa phải chương trình Java độc lập. Nó minh họa **quyền sở hữu unit of work** và sự nhất quán danh tính đối tượng trong một thao tác.

### Container toàn cục không giải quyết scope request

Một singleton global registry không tự chuyển thành request scope khi có nhiều HTTP request. Nó có thể cung cấp một scoped proxy do framework tạo, nhưng khi đó ứng dụng **phụ thuộc vào cơ chế scope và proxy cụ thể**. Nếu service giữ **target request A** trong field dùng chung rồi dùng lại ở request B, data có thể rò dù locator đã resolve thành công ban đầu.

Cần tách **thời điểm resolve**, **lifetime của object** và **quyền sở hữu tài nguyên**. Container không tự làm một dependency mutable trở nên thread-safe hoặc hợp lệ sau khi scope kết thúc.

## 10. Factory và Provider: trường hợp lookup gián tiếp vẫn có lý do đúng

Không nên hiểu bài này thành “mọi provider đều là Service Locator sai”. Một **typed factory/provider được inject tường minh** có thể là abstraction phù hợp khi mỗi lời gọi cần tạo một collaborator mới hoặc lấy một object theo scope.

Ví dụ, mỗi lần xuất tệp phải mở một session mới thuộc quyền sở hữu của lần xuất:

~~~java
interface ExportSession extends AutoCloseable {
    void write(byte[] bytes);

    @Override
    void close();
}

interface ExportSessionFactory {
    // Mỗi lần gọi trả một session mới do caller sở hữu.
    ExportSession open();
}

final class ExportService {
    private final ExportSessionFactory sessions;

    ExportService(ExportSessionFactory sessions) {
        this.sessions = java.util.Objects.requireNonNull(sessions);
    }

    void export(byte[] bytes) {
        try (ExportSession session = sessions.open()) {
            session.write(bytes);
        }
    }
}
~~~

Điều gì khác với Service Locator?

- Constructor của `ExportService` **khai báo cụ thể khả năng cần dùng** là tạo `ExportSession`.
- `ExportSessionFactory` có **hợp đồng chuyên biệt**, không phải API lấy bất kỳ dịch vụ nào theo tên/kiểu.
- Composition root chọn cách tạo session, timeout, client và scope.
- Unit test có thể truyền một fake factory, kiểm tra số session được tạo và đóng.
- Nghĩa vụ ownership “caller đóng session” được mô tả rõ, không phụ thuộc vào đoán scope của container.

Nếu thay `ExportSessionFactory` bằng một `ServiceResolver` có phương thức `<T> T get(Class<T> type)` rồi dùng từ mọi service, đó vẫn có thể là **Service Locator được inject**, chỉ đổi nơi chứa registry.

### Khi nào `Supplier<T>` hợp lý?

Một `Supplier<ExportSession>` có thể thay cho factory chuyên biệt nếu không cần tham số và **hợp đồng tạo mới/ownership đã rõ**. Nhưng kiểu `Supplier<T>` tự thân **không bảo đảm** `get()` luôn tạo mới: có thể trả singleton, lazy-memoized instance hoặc đối tượng theo scope.

Do đó, factory/provider chỉ nên xuất hiện khi consumer thật sự cần **quyết định thời điểm lấy hoặc tạo collaborator**. Nếu luôn dùng cùng một repository trong suốt vòng đời service, truyền `OrderRepository` trực tiếp thường đơn giản và tường minh hơn.

## 11. Nhận diện và refactor trong codebase thật

Đổi toàn bộ service locator sang constructor injection trong một lần có thể gây rủi ro nếu nhiều entry point và scope phụ thuộc vào registry hiện tại. Có thể refactor **theo từng lát dọc của nghiệp vụ**, không cần đập bỏ mọi thứ cùng lúc.

### Bước 1: lập bản đồ lookup và chủ sở hữu

Tìm những API như:

~~~text
GlobalServices.get(...)
ServiceLocator.resolve(...)
ApplicationContext.getBean(...)
StaticRegistry.instance(...)
CurrentContext.service(...)
System.getenv(...) + new Adapter(...)
~~~

Với mỗi nơi, ghi lại:

| Câu hỏi | Mục đích |
| --- | --- |
| Consumer đang cần **khả năng** nào? | Tìm interface/hợp đồng nghiệp vụ thực sự |
| Dependency có bắt buộc không? | Quyết định constructor, optional policy hay factory |
| Nó được tạo mới hay dùng chung? | Xác định scope và identity |
| Ai đóng tài nguyên? | Xác định lifecycle owner |
| Lookup có xảy ra trong request/job/async callback không? | Kiểm tra thread context và phạm vi hợp lệ |
| Có bao nhiêu entry point tạo consumer? | Dự đoán nơi cần cập nhật wiring và test |

### Bước 2: khai báo dependency cụ thể ở constructor

Trước:

~~~java
final class ReportService {
    void publish(Report report) {
        NotificationSender sender =
                GlobalServices.get(NotificationSender.class);
        sender.send(report.toOrder());
    }
}
~~~

Sau (minh họa kiểu và hợp đồng phù hợp):

~~~java
final class ReportService {
    private final NotificationSender sender;

    ReportService(NotificationSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }

    void publish(Report report) {
        sender.send(report.toOrder());
    }
}
~~~

Các đoạn này mô tả trước/sau, **không phải file chạy độc lập** vì `Report` và `toOrder()` được giả định tồn tại. Vấn đề cần sửa là **hướng cung cấp collaborator**, không phải làm thay đổi ngữ nghĩa gửi thông báo.

### Bước 3: chuyển việc chọn và tạo sang composition root

~~~java
NotificationSender sender = new SmtpNotificationSender(config);
ReportService reports = new ReportService(sender);
~~~

Đoạn wiring thuộc bootstrap; nó có thể được chia thành các hàm assembly nếu graph lớn. Nếu ứng dụng dùng container, có thể đăng ký `NotificationSender` và để container gọi constructor `ReportService`.

**Tránh thêm constructor không tham số để vẫn lookup ngầm**:

~~~java
// Dễ kéo dài anti-pattern trong lúc migration.
ReportService() {
    this(GlobalServices.get(NotificationSender.class));
}
~~~

Cách đó giữ lại một đường khởi tạo có phụ thuộc ẩn. Nếu cần tương thích ngược, chỉ nên dùng adapter/facade ở **ranh giới legacy được kiểm soát**, có kế hoạch loại bỏ và kiểm thử riêng; đừng nhân bản đường tắt sang các service mới.

### Bước 4: test bằng fake trước khi thay hết wiring

Tạo service với fake repository/sender để khóa hành vi mong muốn. Sau đó sửa composition root của mỗi entry point để truyền đúng dependency.

Nếu service đang có **hành vi fallback** sang global registry khi null, hãy loại bỏ fallback và xác định rõ optional dependency bằng một hợp đồng phù hợp. “Không tìm thấy trong container” không nên tự động được xem là “không cần collaborator”.

### Bước 5: bỏ đường global và xác minh scope/lifecycle

Khi không còn consumer nghiệp vụ gọi global locator, xóa hoặc thu hẹp registry về vùng bootstrap được phép dùng. Kiểm tra:

- Các test không cần `GlobalServices.clear()`.
- Không còn đường code âm thầm lấy dependency khác với instance đã inject.
- Mỗi request/job dùng đúng scope, không giữ đối tượng đã hết hạn.
- Resource được đóng bởi owner đúng, không bị consumer đóng sớm.
- Có test khởi động/wiring cho những entry point quan trọng.
- Nếu container được sử dụng, các bean được đăng ký không mơ hồ và không có vòng phụ thuộc bị che bằng dynamic lookup.

### Lưu ý về việc “tiêm cả container để khỏi sửa nhiều constructor”

Việc inject container vào mọi service có vẻ giảm số dòng wiring, nhưng biến **một dependency lớn và không giới hạn** thành lối thoát chung. Mỗi lần thêm collaborator mới, người viết chỉ cần thêm `container.get(...)` trong thân phương thức, bỏ qua hợp đồng của constructor. Đây là dấu hiệu cần ưu tiên refactor, không phải mục tiêu cuối cùng.

## 12. Trường hợp ngoại lệ: discovery và extensibility cần thiết kế riêng

Có hệ thống thực sự cần phát hiện plugin, adapter hoặc handler theo tên tại runtime. Khi đó một registry **có thể là chi tiết hợp lệ**, nhưng cần ranh giới và hợp đồng rõ:

- Tại bootstrap, plugin registry có thể được dùng để **chọn và lắp một tập handler** theo cấu hình đã được kiểm tra.
- Một **typed factory** có thể cung cấp handler theo khóa nghiệp vụ, ví dụ `Handler create(HandlerType type)`, thay vì cho consumer nhận toàn bộ container.
- Các lựa chọn phụ thuộc dữ liệu runtime có thể thuộc về **Strategy** hoặc một dispatcher có hợp đồng rõ, được inject qua constructor.
- Nếu plugin có vòng đời riêng, registry/factory cần mô tả **ai tạo, cache, đóng và cách xử lý plugin lỗi**.
- Không cho domain object tự resolve hàng loạt service chỉ vì kiến trúc có plugin.

Chẳng hạn:

~~~java
interface PaymentProcessor {
    Receipt process(PaymentRequest request);
}

interface PaymentProcessorFactory {
    PaymentProcessor forChannel(PaymentChannel channel);
}
~~~

Đây là **mã thiết kế**, chưa phải chương trình độc lập vì các kiểu `Receipt`, `PaymentRequest` và `PaymentChannel` được giả định. Hợp đồng `forChannel` có phạm vi rõ ràng; nó không cung cấp mọi loại object trong ứng dụng.

**Điều quan trọng là mức độ quyền truy cập mà abstraction trao cho consumer.** Một factory chuyên biệt nêu rõ nhu cầu; một generic service locator có khả năng trả bất kỳ service nào có thể khiến ranh giới trách nhiệm mất ý nghĩa.

## 13. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `new Service()` thành công, nhưng một phương thức hiếm gặp lỗi “No bean” | Phụ thuộc bị lookup muộn | Chuyển collaborator bắt buộc sang constructor |
| Unit test chỉ chạy nếu một test khác đã đăng ký fake | Mutable global container và thứ tự test | Tạo graph/fake riêng trong từng test |
| Hai test song song nhận sai adapter | Ghi đè binding toàn cục | Tránh shared mutable registry giữa test; inject instance riêng |
| Service import thẳng API container | Service Locator lẫn vào nghiệp vụ | Truyền interface/factory có kiểu qua constructor |
| Container trả object sai scope | Quyết định lifetime bị ẩn trong lookup | Tạo scope rõ tại ranh giới request/job |
| Registry dùng `String` key và cast `Object` | Không được kiểm tra kiểu tại biên dịch | Dùng typed registration/factory hoặc constructor injection |
| Mỗi method tự resolve một session khác nhau | Không chia sẻ đúng unit of work | Lấy/tạo context một lần cho công việc |
| Service tự đóng client lấy từ container | Ownership không rõ | Để owner của client quản lý lifecycle |
| Circular dependency được “chữa” bằng lookup sau | Vòng bị trì hoãn, không được loại bỏ | Tách trách nhiệm hoặc chuyển dữ liệu qua phương thức |
| Thay cấu hình nhưng service dùng object cũ | Snapshot và lifecycle không rõ | Định nghĩa cơ chế reload/rebuild graph |
| Constructor nhận `ObjectProvider<Object>` rồi cast tùy ý | Generic locator được bọc trong provider | Chuyển sang provider/factory chuyên biệt |
| Quá nhiều constructor parameters | Lớp có thể đang ôm nhiều trách nhiệm | Đánh giá cohesion; không tự động chuyển sang locator |

### “Constructor có quá nhiều tham số” không phải lý do đủ để giấu chúng

Nếu một service cần 12 collaborator, việc chuyển tất cả sang `GlobalContainer.get(...)` làm constructor ngắn hơn nhưng **không giảm số dependency thật**. Đây có thể là dấu hiệu service đang đảm nhiệm nhiều use case hoặc thiếu một abstraction có ý nghĩa. Hãy xem lại trách nhiệm và hướng phụ thuộc, rồi mới chọn tổ chức lắp ghép phù hợp.

## 14. Checklist review thiết kế DI

Trước khi merge một service mới hoặc chuyển sang framework, hãy tự hỏi:

1. **Constructor có khai báo tất cả collaborator bắt buộc không?** Có lookup trong thân service không?
2. **Có chỗ nào service trực tiếp gọi `container.resolve`, `getBean` hoặc static registry không?**
3. **Code nghiệp vụ có import một kiểu registry/framework chỉ để lấy adapter không?**
4. **Việc chọn implementation nằm ở composition root/assembly hay bị rải trong các use case?**
5. **Có phụ thuộc ngầm vào thứ tự bootstrapping, unit test hoặc biến môi trường không?**
6. **Có thể tạo service với fake trong Java thuần mà không khởi động container không?**
7. **Provider/factory được inject có hợp đồng chuyên biệt không, hay chỉ là locator vạn năng?**
8. **Scope của mỗi dependency có phù hợp với vòng đời consumer không?** Có giữ request state trong singleton không?
9. **Ai sở hữu và đóng tài nguyên?** Nếu resolve muộn, trách nhiệm đóng có được nêu rõ không?
10. **Container startup/wiring test đã kiểm tra thiếu binding và lỗi cấu hình chưa?**
11. **Các tình huống đồng thời có dùng chung registry mutable không?** Có thể tạo hai object graph độc lập không?
12. **Nếu có plugin/runtime selection, ranh giới discovery có được giới hạn và kiểm thử không?**

### Tự kiểm tra

**Tình huống A:** `OrderService` nhận `ApplicationContext` qua constructor, sau đó gọi `context.getBean(OrderRepository.class)` trong từng phương thức. Đây có phải constructor injection đầy đủ cho `OrderRepository` không?

**Không.** Container được inject, nhưng `OrderRepository` vẫn bị lookup ẩn trong thân phương thức. Đây là hành vi Service Locator. Hãy inject `OrderRepository` trực tiếp nếu đó là dependency bắt buộc.

**Tình huống B:** `Main` gọi `container.resolve(CheckoutService.class)` rồi chuyển service cho HTTP server. Có phải cứ gọi `resolve` là anti-pattern không?

**Không.** Composition root và integration boundary cần lấy entry service để khởi chạy ứng dụng. Đánh giá dựa vào **vị trí và trách nhiệm của lời gọi**, không chỉ tên API.

**Tình huống C:** Một registry toàn cục dùng `ConcurrentHashMap`. Như vậy đã xử lý mọi vấn đề Service Locator chưa?

**Chưa.** Map có thể hỗ trợ truy cập đồng thời theo quy tắc của nó, nhưng dependency vẫn ẩn; scope/ownership vẫn có thể sai; test và application graph vẫn có nguy cơ phụ thuộc vào trạng thái toàn cục.

**Tình huống D:** `ExportService` nhận `ExportSessionFactory`, mỗi lần xuất gọi `open()` để tạo session mới và đóng bằng `try-with-resources`. Đây có phải Service Locator không?

**Không nhất thiết.** Đây là **typed factory** có trách nhiệm cụ thể, được khai báo ở constructor; nếu contract tạo mới và ownership đúng, nó là lựa chọn DI hợp lý.

**Tình huống E:** Một service có nhiều tham số constructor. Nhóm đổi sang `GlobalServices.get(...)` để constructor rỗng. Thiết kế đã đơn giản hơn chưa?

**Chưa về mặt phụ thuộc thật.** Nhu cầu collaborator vẫn tồn tại, chỉ bị giấu đi. Nên đánh giá cohesion, tách trách nhiệm và tổ chức composition root trước.

**Tình huống F:** Hai test thay binding trong một static container khi chạy song song, thi thoảng nhận sai fake. Có phải do Java generic không kiểm tra được `Class<T>`?

**Không phải nguyên nhân chính.** Đây là **trạng thái lắp ghép toàn cục dùng chung**. Cách tốt hơn là mỗi test tự tạo service với fake của mình hoặc có graph/container tách biệt; chỉ thêm type check không tạo isolation.

## Ghi nhớ

**Service Locator khiến đối tượng chủ động tìm dependency; Dependency Injection khiến dependency được cung cấp từ bên ngoài.** Một container hoặc registry có thể hợp lệ ở **composition root**, nhưng khi service nghiệp vụ gọi container toàn cục để tìm collaborator, nó tạo **phụ thuộc ẩn**, làm mờ object graph, scope và ownership. Để sửa, hãy nêu rõ những hợp đồng cần dùng trong constructor, chọn adapter ở bootstrap, giữ factory/provider có trách nhiệm chuyên biệt khi cần tạo theo từng công việc, và kiểm thử service với fake bằng Java thuần. DI container giúp tự động hóa wiring; nó không biến Service Locator nằm trong nghiệp vụ thành một thiết kế tường minh.
