# Phân biệt DI với Service Locator và việc chủ động tìm phụ thuộc

Trong một ứng dụng Java, nhiều lớp cần dùng thành phần khác để làm việc: `CheckoutService` cần cổng thanh toán, `OrderService` cần kho lưu trữ đơn hàng, `ReportService` cần nguồn dữ liệu. Khi triển khai, câu hỏi thiết kế quan trọng không chỉ là **phụ thuộc vào interface nào**, mà còn là **ai chịu trách nhiệm tìm, tạo và lắp phụ thuộc đó**.

Dependency Injection (DI) là cách **đối tượng nhận cộng tác viên từ bên ngoài**, thường qua constructor. Ngược lại, với **Service Locator**, đối tượng **chủ động yêu cầu một bộ tra cứu** trả về cộng tác viên mà nó cần. Tự gọi `new` hoặc truy cập singleton toàn cục cũng là những cách chủ động lấy phụ thuộc, dù không phải trường hợp nào cũng được gọi là Service Locator.

Hiểu sự khác biệt này giúp thực hành Inversion of Control (IoC): tách mã sử dụng phụ thuộc khỏi mã lựa chọn implementation và lắp ghép object graph. Ta sẽ bắt đầu bằng Java thuần, quan sát tác động tới khả năng kiểm thử và vòng đời đối tượng, rồi mới liên hệ với DI container.

## 1. Phụ thuộc được đưa vào hay đối tượng tự đi tìm?

Xét một dịch vụ thanh toán đơn hàng có hợp đồng:

```java
interface PaymentGateway {
    ChargeReceipt charge(String orderId, long amountVnd);
}
```

Hai kiểu mã sau đều có thể sử dụng `PaymentGateway` và trả kết quả giống nhau, nhưng quan hệ giữa các thành phần khác nhau.

**Dependency Injection — bên ngoài đưa cộng tác viên vào:**

```java
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway);
    }

    ChargeReceipt checkout(String orderId, long amountVnd) {
        return gateway.charge(orderId, amountVnd);
    }
}
```

Nhìn vào constructor, caller biết ngay cần cung cấp một `PaymentGateway`. `CheckoutService` không quyết định cổng thanh toán được tạo ra bằng cách nào hay lấy từ đâu.

**Service Locator — chính đối tượng đi tìm cộng tác viên:**

```java
final class CheckoutServiceWithLocator {
    ChargeReceipt checkout(String orderId, long amountVnd) {
        PaymentGateway gateway = ServiceRegistry.require(PaymentGateway.class);
        return gateway.charge(orderId, amountVnd);
    }
}
```

Chữ ký constructor không nói `CheckoutServiceWithLocator` cần `PaymentGateway`. Nhu cầu chỉ bộc lộ khi đọc thân phương thức hoặc khi lời gọi `require` thất bại trong runtime.

Sơ đồ so sánh:

```text
DI: đưa phụ thuộc vào
  Composition root ── tạo/chọn ──► PaymentGateway
          │                               │
          └── new CheckoutService(gateway)┘
                         │
                         └── checkout(orderId, amount)

Service Locator: tự lấy phụ thuộc
  Composition root ── đăng ký ──► ServiceRegistry
                                      ▲
                                      │ require(PaymentGateway.class)
                               CheckoutServiceWithLocator
                                      ▲
                                      │ checkout(orderId, amount)
                                    Caller
```

Điểm khác nhau nằm ở **hướng điều khiển việc cung cấp phụ thuộc**: DI đưa thứ cần thiết tới đối tượng; Service Locator yêu cầu đối tượng biết cách hỏi một nơi cung cấp phụ thuộc.

## 2. Ví dụ hoàn chỉnh bằng Java thuần

Ví dụ dưới đây chạy với Java 17 trở lên, không cần Spring, Guice hay thư viện ngoài. Lưu nguyên vẹn thành `DiVsLocatorDemo.java`:

```java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public final class DiVsLocatorDemo {
    record ChargeReceipt(String transactionId, long amountVnd) {}

    @FunctionalInterface
    interface PaymentGateway {
        ChargeReceipt charge(String orderId, long amountVnd);
    }

    static final class ConsolePaymentGateway implements PaymentGateway {
        @Override
        public ChargeReceipt charge(String orderId, long amountVnd) {
            return new ChargeReceipt("TX-" + orderId, amountVnd);
        }
    }

    // Bộ tra cứu mẫu để minh họa Service Locator, không phải DI container.
    static final class ServiceRegistry {
        private static final Map<Class<?>, Object> services =
                new ConcurrentHashMap<>();

        private ServiceRegistry() {}

        static <T> void register(Class<T> type, T instance) {
            services.put(
                    Objects.requireNonNull(type),
                    Objects.requireNonNull(instance)
            );
        }

        static <T> T require(Class<T> type) {
            Object value = services.get(type);
            if (value == null) {
                throw new IllegalStateException(
                        "Missing service: " + type.getName()
                );
            }
            return type.cast(value);
        }
    }

    static final class CheckoutWithLocator {
        ChargeReceipt checkout(String orderId, long amountVnd) {
            validate(orderId, amountVnd);

            // Phụ thuộc thật chỉ xuất hiện bên trong phương thức.
            PaymentGateway gateway =
                    ServiceRegistry.require(PaymentGateway.class);
            return gateway.charge(orderId, amountVnd);
        }
    }

    static final class CheckoutWithDI {
        private final PaymentGateway gateway;

        CheckoutWithDI(PaymentGateway gateway) {
            this.gateway = Objects.requireNonNull(gateway);
        }

        ChargeReceipt checkout(String orderId, long amountVnd) {
            validate(orderId, amountVnd);
            return gateway.charge(orderId, amountVnd);
        }
    }

    private static void validate(String orderId, long amountVnd) {
        if (orderId == null || orderId.isBlank() || amountVnd <= 0) {
            throw new IllegalArgumentException("Invalid checkout input");
        }
    }

    public static void main(String[] args) {
        PaymentGateway gateway = new ConsolePaymentGateway();

        // Cách 1: khai báo vào registry để service tự tra cứu.
        ServiceRegistry.register(PaymentGateway.class, gateway);
        var locatorBased = new CheckoutWithLocator();
        System.out.println(locatorBased.checkout("ORD-1", 120_000));

        // Cách 2: composition root cấp trực tiếp vào constructor.
        var injected = new CheckoutWithDI(gateway);
        System.out.println(injected.checkout("ORD-2", 250_000));
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac DiVsLocatorDemo.java
java DiVsLocatorDemo
```

Kết quả mong đợi:

```text
ChargeReceipt[transactionId=TX-ORD-1, amountVnd=120000]
ChargeReceipt[transactionId=TX-ORD-2, amountVnd=250000]
```

Cả hai đường đi đều có thể tạo kết quả nghiệp vụ đúng. Sự khác biệt quan trọng xuất hiện khi **thiếu cấu hình**, **thay implementation**, **kiểm thử độc lập** hoặc **quản lý scope**.

- Với `CheckoutWithDI`, nơi gọi phải cung cấp `PaymentGateway` khi tạo đối tượng. Constructor biểu diễn trực tiếp yêu cầu về collaborator. Truyền `null` cũng bị từ chối ngay lúc tạo.
- Với `CheckoutWithLocator`, `new CheckoutWithLocator()` vẫn thành công dù chưa có `PaymentGateway` trong registry. Vấn đề chỉ lộ ra khi chạy `checkout(...)` tới câu lệnh tra cứu.
- `ServiceRegistry` ở đây dùng map toàn cục. `ConcurrentHashMap` tránh một số lỗi truy cập đồng thời vào map, **không** giải quyết việc thay giá trị giữa các kiểm thử, ownership, transaction scope hay vòng đời tài nguyên.

## 3. Dấu hiệu nhận biết Service Locator và việc chủ động tìm phụ thuộc

Service Locator là một **cơ chế tra cứu các dịch vụ đã được đăng ký hoặc có thể được tạo theo yêu cầu**. Mã dùng locator thường biết một khóa hoặc kiểu (`PaymentGateway.class`, tên dịch vụ, định danh) và gọi `get`, `resolve`, `require` hay API tương tự.

Nhưng không phải mọi cách tự lấy phụ thuộc đều là Service Locator:

| Cách viết trong lớp nghiệp vụ | Điều đang xảy ra | Tác động đến thiết kế |
|---|---|---|
| `new SqlOrderRepository(...)` | Lớp tự chọn và tạo implementation cụ thể | Gắn mã nghiệp vụ với việc khởi tạo và cấu hình phụ thuộc |
| `Services.get(OrderRepository.class)` | Tra cứu qua Service Locator/registry | Phụ thuộc thực tế bị che sau registry |
| `ApplicationContext.getBean(OrderRepository.class)` | Tra cứu từ DI container theo lối Service Locator | Mã nghiệp vụ biết API container và chủ động resolve |
| `GlobalConfig.repository()` hoặc `Repository.getInstance()` | Truy cập một nguồn toàn cục | Có thể giấu phụ thuộc và tạo trạng thái chia sẻ; không nhất thiết là Service Locator tổng quát |
| `new OrderService(repository)` | Constructor injection | Caller công khai chịu trách nhiệm cấp cộng tác viên |
| `process(order, pricingStrategy)` | Method injection nếu `pricingStrategy` là collaborator của lần gọi | Caller lựa chọn hành vi cho đúng thao tác đó |

Ví dụ một constructor **nhận locator** vẫn chưa đưa trực tiếp các cộng tác viên thực sự vào đối tượng:

```java
final class OrderService {
    private final ServiceLocator locator;

    OrderService(ServiceLocator locator) {
        this.locator = locator;
    }

    void place(Order order) {
        var repository = locator.get(OrderRepository.class);
        repository.save(order);
    }
}
```

Ở đây constructor chỉ công khai `ServiceLocator`, còn phụ thuộc vào `OrderRepository` bị ẩn trong phương thức `place`. Đó vẫn là **mẫu tra cứu theo Service Locator**, mặc dù bản thân locator được truyền qua constructor. Điều cần quan sát là *ai quyết định tra cứu collaborator* và *hợp đồng của service có nêu rõ collaborator đó không*.

## 4. Những đánh đổi cần nhìn đúng bản chất

| Tiêu chí | Constructor Injection | Service Locator bên trong service |
|---|---|---|
| Khả năng nhìn thấy collaborator bắt buộc | Rõ qua constructor | Phải đọc mã hoặc tài liệu về các lệnh tra cứu |
| Thiết lập khi tạo đối tượng | Caller/composition root cung cấp phụ thuộc | Có thể tạo service trước, sau đó lỗi khi thiếu registration |
| Thay implementation | Truyền implementation khác khi khởi tạo | Thay cấu hình locator, có thể ảnh hưởng nơi dùng chung |
| Kiểm thử đơn vị | Dễ truyền stub/fake riêng cho test | Thường cần dựng, thay hoặc dọn trạng thái locator |
| Phụ thuộc vào cơ chế hạ tầng | Service có thể chỉ biết interface nghiệp vụ | Service biết locator hoặc API container |
| Vòng đời và scope | Lộ hơn tại nơi lắp graph; vẫn phải quản lý đúng | Có thể linh hoạt resolve theo thời điểm, nhưng việc theo dõi scope và ownership khó hơn nếu tra cứu tùy ý |
| Đường gọi phụ thuộc | Tương đối tường minh | Có thể phát sinh phụ thuộc mới ở các nhánh runtime |

**Không nên hiểu “constructor injection bảo đảm ứng dụng không bao giờ lỗi runtime”.** Compiler Java kiểm tra việc caller phải truyền đối số đúng kiểu cho constructor, nhưng không xác nhận được toàn bộ cấu hình production, thông tin môi trường hoặc một DI container sẽ lắp được mọi nhánh object graph. Container thường phát hiện được một số lỗi khi khởi động, tùy cơ chế cấu hình và thời điểm tạo đối tượng.

Service Locator cũng không tự động sai trong mọi lớp. Nó có thể hữu ích tại **ranh giới tích hợp, điểm khởi động, plugin host hoặc mã hạ tầng** cần tìm thành phần theo khóa động. Vấn đề thường gặp là đưa cơ chế tra cứu tổng quát vào nhiều lớp nghiệp vụ khiến các phụ thuộc mất tính tường minh.

## 5. Kiểm thử: thay cộng tác viên mà không đụng trạng thái toàn cục

Với phiên bản DI, có thể dùng một fake riêng cho mỗi phép thử. Lưu file `DiVsLocatorDemoCheck.java` cạnh ví dụ ở trên:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class DiVsLocatorDemoCheck {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        DiVsLocatorDemo.PaymentGateway fake = (orderId, amountVnd) -> {
            if (!"ORD-TEST".equals(orderId) || amountVnd != 90_000) {
                throw new AssertionError("Wrong input");
            }
            calls.incrementAndGet();
            return new DiVsLocatorDemo.ChargeReceipt("FAKE-TX", amountVnd);
        };

        var service = new DiVsLocatorDemo.CheckoutWithDI(fake);
        var result = service.checkout("ORD-TEST", 90_000);

        if (!"FAKE-TX".equals(result.transactionId())
                || result.amountVnd() != 90_000
                || calls.get() != 1) {
            throw new AssertionError("Unexpected result");
        }

        System.out.println("PASS");
    }
}
```

```bash
javac DiVsLocatorDemo.java DiVsLocatorDemoCheck.java
java DiVsLocatorDemoCheck
```

Bài kiểm tra này chứng minh service sử dụng đúng collaborator do test cấp và chuyển đúng `orderId`, `amountVnd` của một lời gọi. Không có bước đăng ký service toàn cục hoặc khôi phục registry sau test.

Nếu dùng `CheckoutWithLocator`, test phải bảo đảm `ServiceRegistry` đang chứa đúng `PaymentGateway`, và các test khác không đổi đăng ký đó. Test nối tiếp có thể vô tình phụ thuộc thứ tự chạy; test đồng thời có thể tranh chấp cấu hình. Một locator quản lý scope và cách dọn dẹp tốt có thể giảm vấn đề này, nhưng lúc đó test phải hiểu thêm cơ chế locator thay vì chỉ nhìn constructor của đối tượng cần kiểm tra.

**Tách hai chiều thay đổi:** implementation/fake của `PaymentGateway` do nơi lắp ghép chọn; `orderId` và `amountVnd` là dữ liệu biến đổi qua từng lần gọi `checkout`. Không nên đăng ký mỗi mã đơn hàng vào DI container chỉ vì chúng xuất hiện trong cùng một use case.

## 6. Liên hệ giữa DI, IoC, DIP và DI container

Các thuật ngữ này liên quan nhưng không đồng nghĩa:

- **Inversion of Control (IoC)** là ý tưởng rộng: chuyển một phần quyền điều phối khỏi thành phần đang được sử dụng. Với lắp ghép đối tượng, lớp nghiệp vụ không tự quyết định cách tạo cộng tác viên.
- **Dependency Injection (DI)** là một kỹ thuật cụ thể: cung cấp collaborator từ bên ngoài qua constructor, phương thức hoặc một cơ chế injection khác. Constructor injection thường phù hợp nhất cho collaborator bắt buộc trong suốt vòng đời service.
- **Dependency Inversion Principle (DIP)** nói về hướng phụ thuộc giữa các chính sách cấp cao và chi tiết triển khai: các thành phần nên dựa vào abstraction phù hợp. DIP và DI hỗ trợ nhau nhưng là hai khái niệm khác nhau. Có thể inject trực tiếp một class cụ thể, hoặc dùng interface nhưng vẫn tự tra cứu qua locator.
- **DI container** là công cụ giúp cấu hình, tạo, lắp ghép và đôi khi quản lý scope của object graph. Container có thể có API `getBean`/`resolve`, nhưng việc **gọi API đó từ mã nghiệp vụ** là phong cách Service Locator. Việc **container tự cấp dependency vào constructor** là DI.

Ví dụ, ở **composition root**, tra cứu vẫn có thể được dùng để lấy một đối tượng đầu vào cho việc lắp ghép:

```java
// Pseudocode tại điểm khởi động ứng dụng.
PaymentGateway gateway = container.resolve(PaymentGateway.class);
CheckoutService checkoutService = new CheckoutService(gateway);
```

Ở đây việc tra cứu nằm trong mã **chịu trách nhiệm composition**; `CheckoutService` chỉ nhận `PaymentGateway`. Kể cả khi bên dưới dùng container có chức năng service lookup, lớp nghiệp vụ vẫn giữ hợp đồng constructor tường minh.

Ngược lại, nếu bên trong `CheckoutService.checkout(...)` liên tục gọi `container.resolve(...)`, thành phần nghiệp vụ đã biết về container và tự điều khiển việc tìm dependency. Hai trường hợp có hệ quả kiến trúc khác nhau.

## 7. Scope và vòng đời: tra cứu theo lúc dùng có giải quyết vấn đề không?

Trong ứng dụng web, một collaborator có thể sống theo cả ứng dụng, một request, hoặc một transaction. Đây là **quyết định về scope và ownership**, độc lập với câu hỏi DI hay Service Locator.

Giả sử một `OrderService` dùng chung giữa nhiều request, nhưng connection tới cơ sở dữ liệu chỉ được phép dùng trong transaction đang mở. Nếu constructor cố giữ một connection request-scoped cho toàn bộ vòng đời service, scope có thể bị sai. **Không nên vì thế chuyển toàn bộ logic nghiệp vụ sang gọi container trực tiếp.** Có các lựa chọn rõ ràng hơn:

1. Cấp `OrderService` theo scope phù hợp nếu kiến trúc hỗ trợ.
2. Inject một abstraction như `TransactionRunner`, `UnitOfWorkFactory` hoặc `ConnectionFactory`; service yêu cầu tạo/điều phối tài nguyên cho từng thao tác, còn cơ chế mở/đóng nằm sau abstraction.
3. Tại ranh giới request/transaction, tạo và truyền dependency tương ứng vào một đối tượng xử lý chỉ sống trong scope đó.

Ví dụ minh họa ý tưởng factory bằng Java thuần:

```java
interface UnitOfWork extends AutoCloseable {
    void saveOrder(String orderId);

    @Override
    void close();
}

interface UnitOfWorkFactory {
    UnitOfWork open();
}

final class OrderWriter {
    private final UnitOfWorkFactory unitOfWorkFactory;

    OrderWriter(UnitOfWorkFactory unitOfWorkFactory) {
        this.unitOfWorkFactory = unitOfWorkFactory;
    }

    void save(String orderId) {
        try (UnitOfWork work = unitOfWorkFactory.open()) {
            work.saveOrder(orderId);
        }
    }
}
```

`UnitOfWorkFactory` là collaborator được inject; `orderId` là dữ liệu của lần gọi. Mỗi lần gọi `save` mở một `UnitOfWork` và đóng trong `try-with-resources`. Đây là ví dụ về **cung cấp có kiểm soát theo vòng đời**, không cần trao cho `OrderWriter` một locator tổng quát cho mọi loại dịch vụ. Ví dụ giả định `close()` giải phóng tài nguyên; việc commit/rollback giao dịch cần hợp đồng bổ sung phù hợp với hệ thống thực tế.

Nếu chọn implementation theo loại thanh toán của từng request, có thể inject `PaymentGatewaySelector` hoặc `PaymentGatewayFactory` với API chuyên biệt như `forMethod(PaymentMethod method)`. Việc lựa chọn runtime vẫn diễn ra, nhưng contract chỉ công khai năng lực thực sự cần thay vì cấp quyền truy cập cả registry ứng dụng.

## 8. Khi nào tra cứu dịch vụ vẫn hợp lý?

Đôi khi chương trình *thật sự* cần tìm dịch vụ dựa trên danh sách plugin hoặc module chỉ biết tại runtime. Ví dụ host nạp bộ xử lý theo định danh trong cấu hình, kiểm tra plugin nào đang được cài hoặc chuẩn bị object graph khi startup. Một registry chuyên biệt có thể thích hợp ở **ranh giới động** đó.

Hãy phân biệt hai ý định thiết kế:

**Tra cứu để lắp ghép ứng dụng**:

```text
Startup/plugin host
      │
      ├── discover implementation theo plugin key
      ├── tạo hoặc lấy collaborator đúng scope
      └── new BusinessService(collaborator)
                         │
                         └── xử lý nghiệp vụ
```

**Tra cứu tùy ý trong nghiệp vụ**:

```text
BusinessService
      └── Registry.get(...), Context.getBean(...),
          GlobalServices.require(...), ...
            ├── cần cấu hình ngoài constructor
            └── khó thấy mọi collaborator thực sự
```

Để quyết định có cần locator hay không, hãy hỏi: việc tìm thành phần theo khóa động có phải **trách nhiệm chính đáng của lớp này** không, hay đơn giản lớp đang muốn sử dụng một cộng tác viên đã biết trước? Nếu collaborator đã biết và bắt buộc, constructor injection thường mang lại hợp đồng rõ hơn. Nếu việc tìm kiếm bản thân là một năng lực cần thiết, hãy cân nhắc interface chuyên biệt có phạm vi hẹp, chính sách lỗi rõ ràng và ownership minh bạch.

## 9. Cách refactor từ chủ động tìm phụ thuộc sang DI

Giả sử mã hiện tại:

```java
final class InvoiceService {
    Invoice load(String invoiceId) {
        InvoiceRepository repository =
                GlobalServices.require(InvoiceRepository.class);
        return repository.findById(invoiceId);
    }
}
```

Có thể chuyển theo các bước:

1. **Xác định các collaborator thực tế.** Ở đây là `InvoiceRepository`; `invoiceId` là input từng lần gọi.
2. **Khai báo phụ thuộc trực tiếp qua constructor.** Thay câu lệnh `GlobalServices.require` bằng field `final`, kiểm tra `null` nếu dependency bắt buộc.
3. **Chuyển việc lắp ghép ra composition root.** Nơi khởi động tạo/cấp `InvoiceRepository` và xây `InvoiceService`.
4. **Dùng fake trong kiểm thử.** Truyền implementation thử nghiệm riêng mà không động tới cấu hình toàn cục.
5. **Kiểm tra scope.** Nếu repository giữ session ngắn hạn, cân nhắc scope phù hợp hoặc inject factory; không kéo dài vòng đời tài nguyên ngoài thiết kế.

Kết quả trong service:

```java
final class InvoiceService {
    private final InvoiceRepository repository;

    InvoiceService(InvoiceRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    Invoice load(String invoiceId) {
        return repository.findById(invoiceId);
    }
}
```

Mã minh họa giả định các interface `InvoiceRepository` và kiểu `Invoice` đã tồn tại trong hệ thống. Điểm quan trọng là collaborator trở thành một phần rõ ràng của hợp đồng, còn dữ liệu của lần tra cứu tiếp tục đi qua phương thức `load`.

Trong ứng dụng nhiều lớp, nên lần theo **caller** để đặt composition đúng nơi. Đổi mỗi constructor mà không cập nhật đường lắp ghép sẽ chỉ chuyển lỗi từ lúc lookup sang lúc tạo đối tượng. Đừng thay một Service Locator toàn cục bằng một `ServiceLocator` instance được inject vào mọi lớp; cách này chỉ đổi vị trí cất locator.

## 10. Tự kiểm tra hiểu biết

**Tình huống A:** Một lớp `PdfExporter` luôn cần `FontRenderer` và `FileStore`; mỗi lần xuất nhận `documentId` và `outputPath`. Nếu renderer và store được cấp lúc khởi tạo, còn ID và path đi qua `export(...)`, đó là DI cho hai collaborator và per-call input cho hai giá trị.

**Tình huống B:** Lớp `ReportService` nhận `ApplicationContext` trong constructor rồi gọi `context.getBean(ReportRepository.class)` mỗi lần tạo báo cáo. Mặc dù context được inject, việc lấy `ReportRepository` vẫn theo Service Locator.

**Tình huống C:** Ở điểm khởi động, `main` dùng một registry để tìm `MetricsClient` rồi gọi `new AnalyticsService(metricsClient)`. `AnalyticsService` đang nhận dependency theo constructor injection; lookup chỉ xảy ra tại composition root.

**Tình huống D:** Cùng service xử lý nhiều cách thanh toán, mỗi request chọn `paymentMethod` khác nhau. Nếu một đối tượng `PaymentGatewayFactory` được inject và chọn gateway dựa trên `paymentMethod`, ta vẫn có DI cho factory và dữ liệu per-call cho lựa chọn. Cần thêm quy tắc tạo/đóng gateway nếu nó sở hữu tài nguyên.

### Câu hỏi thực hành

Cho đoạn mã:

```java
final class StockChecker {
    boolean available(String sku, int quantity) {
        var store = AppServices.get(InventoryStore.class);
        return store.inStock(sku, quantity);
    }
}
```

Hãy trả lời trước khi nhìn gợi ý: thành phần nào là collaborator, thành phần nào là dữ liệu lời gọi, và cần đổi gì để loại bỏ việc chủ động tìm phụ thuộc?

<details>
<summary>Gợi ý đáp án</summary>

`InventoryStore` là collaborator; `sku` và `quantity` là dữ liệu của lần kiểm tra. Chuyển `InventoryStore` vào constructor, giữ `available(sku, quantity)` và để composition root cung cấp implementation:

```java
final class StockChecker {
    private final InventoryStore store;

    StockChecker(InventoryStore store) {
        this.store = Objects.requireNonNull(store);
    }

    boolean available(String sku, int quantity) {
        return store.inStock(sku, quantity);
    }
}
```

Ví dụ chỉ minh họa cấu trúc khi `InventoryStore` đã được định nghĩa và chính sách kiểm tra input được thực hiện ở nơi thích hợp.

</details>

## Ghi nhớ

- **DI là đưa cộng tác viên từ ngoài vào; Service Locator là đối tượng tự tra cứu cộng tác viên từ một nơi cung cấp.** Cùng một interface sử dụng được trong cả hai, nhưng mức độ tường minh của hợp đồng khác nhau.
- **Việc chủ động tìm phụ thuộc rộng hơn Service Locator**: tự gọi `new`, dùng singleton toàn cục hoặc gọi container trong service đều có thể gắn lớp nghiệp vụ với cách lấy dependency.
- **Có API tra cứu trong DI container không biến mọi cách dùng container thành DI.** Quan trọng là lớp nào thực hiện việc lookup; tra cứu tại composition root có thể vẫn dẫn tới constructor injection cho service.
- **Scope, ownership và lựa chọn implementation lúc runtime cần thiết kế riêng.** Khi cần tạo tài nguyên ngắn hạn hoặc chọn plugin động, factory/selector chuyên biệt thường biểu diễn nhu cầu rõ hơn một locator tổng quát trong business logic.
- **Java thuần đã đủ để thực hành DI:** truyền collaborator vào constructor, thay nó bằng fake trong test, để dữ liệu của từng request vào tham số phương thức, rồi mới cân nhắc DI container khi object graph phức tạp hơn.
