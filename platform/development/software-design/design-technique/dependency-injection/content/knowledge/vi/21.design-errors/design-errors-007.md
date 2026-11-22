# Truyền một túi phụ thuộc tổng quát để che giấu nhu cầu thực sự

Một lớp có thể trông như đã áp dụng **Dependency Injection (DI)** vì nó nhận một đối tượng qua constructor, nhưng vẫn che giấu phần lớn nhu cầu thực sự. Ví dụ, thay vì nhận `OrderStore`, `NoticeSender` và `Clock`, lớp chỉ nhận một `Dependencies` hoặc `ApplicationContext` có phương thức `get(Class<T>)`. Sau đó, nó tự tìm mọi cộng tác viên bên trong chiếc “túi” này.

Cách làm ấy thường được gọi là **dependency bag** (*túi phụ thuộc tổng quát*) hoặc một biến thể của **Service Locator**. Nó di chuyển thao tác tra cứu từ biến toàn cục sang một object được truyền vào, nhưng **chưa thực hiện đầy đủ mục tiêu thiết kế của constructor injection**: người đọc constructor vẫn không biết lớp cần những gì để hoạt động.

Bài thuộc chương **Lỗi thiết kế** của module **Dependency Injection**. Mục tiêu là nhận diện dependency bag, hiểu vì sao nó làm suy yếu Inversion of Control (IoC), phân biệt một “túi mọi dịch vụ” với đối tượng cấu hình có ý nghĩa, rồi refactor sang constructor injection bằng Java 17 thuần. Ta cũng xem xét cách giữ composition root, scope, vòng đời và kiểm thử ở ranh giới phù hợp trước khi cân nhắc DI container.

## 1. Dấu hiệu của dependency bag

Một API đáng nghi thường có hình dạng:

~~~java
// Minh họa chống mẫu: lớp nghiệp vụ nhận một túi không giới hạn.
final class CheckoutService {
    private final Dependencies dependencies;

    CheckoutService(Dependencies dependencies) {
        this.dependencies = dependencies;
    }

    Receipt checkout(Order order) {
        OrderStore store = dependencies.get(OrderStore.class);
        PaymentGateway payment = dependencies.get(PaymentGateway.class);
        AuditSink audit = dependencies.get(AuditSink.class);

        // Xử lý đơn hàng...
        return null; // Chỉ là mã minh họa ý tưởng.
    }
}
~~~

Constructor chỉ tiết lộ rằng `CheckoutService` cần một `Dependencies`; nó không nói rõ service phụ thuộc vào repository, cổng thanh toán và audit. Muốn biết, người đọc phải đi sâu vào thân phương thức, các nhánh điều kiện, helper và đôi khi cả code kế thừa.

Một số dấu hiệu tương tự:

- Constructor nhận `Map<String, Object>`, `Map<Class<?>, Object>`, `ServiceRegistry`, `BeanProvider` hoặc một `ApplicationContext` đa năng rồi tra cứu dependency tùy ý.
- Một object tên `Services` có hàng chục getter cho repository, HTTP client, clock, message broker, feature flag và mọi component khác; mọi service đều được tiêm nguyên object.
- Trong method nghiệp vụ xuất hiện `context.getBean(...)`, `registry.resolve(...)` hoặc `dependencies.require(...)`.
- Dependency được bổ sung trong code mà **không cần thay chữ ký constructor** hoặc cập nhật composition root một cách rõ ràng.
- Test chỉ tạo một bag với nhiều mục và đến khi chạy một nhánh ít gặp mới báo thiếu dependency.

Không phải mọi object có nhiều trường đều là dependency bag. Điểm cần xác định là **object đó biểu diễn một khái niệm có ý nghĩa và hợp đồng giới hạn**, hay chỉ là cách cho consumer tự tra cứu những thành phần bất kỳ của cả ứng dụng.

## 2. Vì sao truyền bag qua constructor vẫn che giấu phụ thuộc?

So sánh hai constructor:

~~~java
// Các interface ở đây là hợp đồng minh họa.
CheckoutService(Dependencies dependencies);

CheckoutService(
        OrderStore store,
        PaymentGateway payment,
        AuditSink audit);
~~~

Ở thiết kế thứ hai, chữ ký constructor cho thấy **ba cộng tác viên bắt buộc**. Compiler và IDE hỗ trợ caller biết mình phải cung cấp gì. Khi thêm nhu cầu về `Clock`, tác động thể hiện rõ ở constructor và nơi lắp ghép.

Ở thiết kế thứ nhất, bag chỉ là **một cửa tra cứu rộng**. `CheckoutService` vẫn **chủ động yêu cầu** implementation theo khóa tại thời điểm chạy; một dependency thiếu có thể chỉ gây lỗi khi code đi vào nhánh sử dụng nó.

~~~mermaid
flowchart TD
    subgraph Bag["Dependency bag"]
        RootA["Composition root"] --> ContainerA["Dependencies / Map / Registry"]
        ContainerA --> ServiceA["CheckoutService"]
        ServiceA -->|"get(OrderStore.class)"| ContainerA
        ServiceA -->|"get(PaymentGateway.class)"| ContainerA
        ServiceA -->|"get(AuditSink.class)"| ContainerA
    end
    subgraph Explicit["Constructor injection tường minh"]
        RootB["Composition root"] --> Store["OrderStore"]
        RootB --> Pay["PaymentGateway"]
        RootB --> Audit["AuditSink"]
        Store --> ServiceB["CheckoutService"]
        Pay --> ServiceB
        Audit --> ServiceB
    end
~~~

Sơ đồ nhấn mạnh sự khác biệt về **quyền quyết định**:

- Với **bag**, business service tự tra cứu các dependency từ một kho chung. Cách làm này rất gần Service Locator, dù registry đã được truyền vào constructor thay vì đặt trong static field.
- Với **constructor injection tường minh**, composition root quyết định các implementation và đưa đúng cộng tác viên vào service; service chỉ biết sử dụng hợp đồng đã nhận.

Điều đó không có nghĩa mọi thao tác tìm dependency đều xấu. **Composition root và DI container** đương nhiên phải có cơ chế tra cứu/giải quyết binding. Vấn đề xuất hiện khi **logic nghiệp vụ** giữ API tra cứu tổng quát rồi tự điều phối sự phụ thuộc của mình.

## 3. Những hệ quả thiết kế thường bị bỏ qua

### 3.1. Dependency bắt buộc chỉ lộ ra khi chạy

Một service chỉ cần `Dependencies` là có thể được tạo thành công dù trong bag chưa có `PaymentGateway`. Lỗi xuất hiện khi chạy `checkout()`, thậm chí chỉ xảy ra với một loại đơn hiếm gặp.

Ngược lại, constructor nhận `PaymentGateway` bắt buộc có thể dùng `Objects.requireNonNull(payment, "payment")` để **fail fast ngay lúc lắp ghép**. DI container cũng có thể kiểm tra binding khi tạo object graph.

### 3.2. Bag cho phép nhu cầu của class tăng âm thầm

Ban đầu service lấy `OrderStore`; sau đó lập trình viên thêm một lệnh `get(EmailSender.class)`. Constructor không đổi và các caller có thể tiếp tục biên dịch, nhưng **hợp đồng runtime đã thay đổi**.

Khi dependency tường minh, thay đổi này buộc người sửa đánh giá: thông báo có thuộc trách nhiệm của service không, nên dùng abstraction nào, ai tạo instance và scope của nó là gì?

### 3.3. Test có thể chỉ mô phỏng một môi trường lắp ghép mơ hồ

Test tạo một bag chứa đủ loại service không liên quan, rồi để class tự lấy bất cứ thứ gì. Một nhánh dùng tới `AuditSink` ít được kiểm thử sẽ vỡ muộn. Việc fake được đưa vào container **không bảo đảm** những dependency bắt buộc đã được khai báo đúng.

Với constructor injection, unit test chỉ cần truyền những cộng tác viên mà class thực sự sử dụng; việc tạo object graph cho test trở nên đơn giản và đáng tin hơn.

### 3.4. Tính khả biến gây thay đổi wiring bất ngờ

Nếu bag có phương thức `register`/`put`, một component khác có thể thay adapter sau khi service đã được tạo. Nếu service tra cứu trong **mỗi lần gọi**, cùng một service có thể sử dụng hai repository hoặc hai sender khác nhau ở hai thời điểm mà không có bước reconfiguration công khai.

Một số registry/container cũng có thể được đóng băng sau khi cấu hình; điều đó giảm rủi ro bị sửa lúc chạy nhưng **không sửa được vấn đề dependency ẩn**.

### 3.5. Scope và vòng đời bị che đi

Một bag chung có thể chứa instance mang trạng thái request, session/transaction hoặc client cần đóng. Consumer không biết nó đang **mượn** hay **sở hữu** object đó; bag có thể trả một instance đã hết scope. Đặc biệt nguy hiểm khi singleton-scoped service giữ bag chung rồi tự lấy dữ liệu của “request hiện tại” không có ranh giới rõ ràng.

### 3.6. Lớp trở thành điểm tích lũy trách nhiệm

Khi mọi dịch vụ đều sẵn trong bag, thêm một tính năng chỉ cần thêm lệnh tra cứu. Không còn áp lực tự nhiên từ constructor dài để thảo luận việc **tách trách nhiệm**. Một “túi thuận tiện” có thể che giấu một **God Object** đang dần hình thành.

## 4. So sánh dependency bag với đối tượng cấu hình và facade thực sự

Không phải cứ gom nhiều giá trị trong một object là sai. Cần phân biệt **tập hợp dữ liệu có ý nghĩa**, **abstraction nghiệp vụ** và **registry đa năng**.

| Kiểu object | Ví dụ | Có nên truyền cho business service? | Lý do |
| --- | --- | --- | --- |
| **Dependency bag tổng quát** | `Dependencies.get(Class<T>)` có thể lấy bất cứ service nào | Thường không | Che giấu nhu cầu và cho phép tự tra cứu rộng |
| **Typed configuration object** | `HttpClientSettings(URI baseUrl, Duration timeout)` | Có thể, nếu service cần những giá trị đó | Nhóm các **giá trị liên quan** thành một khái niệm |
| **Facade có trách nhiệm rõ** | `PaymentProcessor.authorize(...)` | Có, nếu đó là một cộng tác viên đúng miền nghiệp vụ | Cung cấp hành vi gắn kết, không phơi mọi dịch vụ |
| **Typed factory/provider** | `SessionFactory.open()` | Có, khi cần instance mới hoặc theo scope | Hợp đồng tạo một loại object và ownership cụ thể |
| **DI container/registry ở composition root** | `container.resolve(OrderService.class)` tại bootstrap | Có thể dùng **ở root**, tránh đưa tiếp vào business layer | Nơi lắp ghép chịu trách nhiệm resolve |
| **Request data/context có ý nghĩa** | `RequestIdentity(userId, traceId)` | Có thể truyền theo **lời gọi/request** | Biểu diễn dữ liệu của một request, không phải kho service toàn hệ thống |

Ví dụ một đối tượng giá trị có ý nghĩa:

~~~java
record HttpClientSettings(
        java.net.URI baseUrl,
        java.time.Duration timeout) {

    HttpClientSettings {
        java.util.Objects.requireNonNull(baseUrl, "baseUrl");
        java.util.Objects.requireNonNull(timeout, "timeout");
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
~~~

Đây là **cấu hình bất biến có ý nghĩa riêng**; không phải API để lấy tùy ý database, clock, logger và queue từ toàn ứng dụng. Ngược lại, một class `CheckoutDependencies` có 25 trường chỉ được tạo để tránh constructor dài vẫn có thể là **bag đóng gói kiểu**, nếu nó không biểu diễn một khái niệm gắn kết.

Một facade tốt cũng không đơn thuần trả lại các dependency qua nhiều getter:

~~~java
// Không hữu ích nếu chỉ là một túi với tên khác.
interface AllBusinessServices {
    OrderStore orderStore();
    PaymentGateway paymentGateway();
    AuditSink auditSink();
    EmailSender emailSender();
    // Hàng chục getter khác...
}
~~~

Một facade đúng nghĩa thường **cung cấp hành vi** rõ ràng, ví dụ `PaymentProcessor.authorizePayment(...)`, và có thể tự phối hợp một số dependency **nội bộ**. Consumer phụ thuộc vào hành vi ấy thay vì thấy mọi thành phần nhỏ bên dưới.

## 5. Ví dụ Java 17 hoàn chỉnh: từ túi phụ thuộc sang constructor tường minh

Ta xây dựng một use case đơn giản: đặt đơn hàng, lưu đơn và phát thông báo xác nhận. Để kết quả có thể kiểm thử ổn định, thời điểm được lấy từ `Clock` do caller cung cấp.

Phiên bản cũ `HiddenOrderService` nhận một `DependencyBag` và tra cứu `OrderStore`, `NoticeSender`, `Clock` trong mỗi lời gọi. Phiên bản mới `ExplicitOrderService` nhận đúng ba dependency bắt buộc trong constructor và lưu vào các trường `final`.

Cả hai dùng cùng hợp đồng nghiệp vụ để so sánh hành vi:

- Đơn hợp lệ được lưu.
- Trả về `Receipt` có đúng mã đơn và thời điểm.
- Gửi một thông báo xác nhận.
- Không chấp nhận lưu trùng mã đơn.
- Cấu hình thiếu dependency phải được phát hiện càng sớm càng tốt; ví dụ cho thấy bag phát hiện muộn hơn.

Lưu toàn bộ mã sau vào tệp `Main.java`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record Order(String id, String sku, int quantity) {
    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(sku, "sku");
        if (id.isBlank() || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

record Receipt(String orderId, Instant acceptedAt) {}

record Notice(String orderId, String message) {}

interface OrderStore {
    void save(Order order);

    Optional<Order> findById(String id);
}

final class InMemoryOrderStore implements OrderStore {
    private final Map<String, Order> saved = new HashMap<>();

    @Override
    public void save(Order order) {
        Objects.requireNonNull(order, "order");
        if (saved.putIfAbsent(order.id(), order) != null) {
            throw new IllegalArgumentException("Duplicate order");
        }
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(saved.get(id));
    }
}

@FunctionalInterface
interface NoticeSender {
    void send(Notice notice);
}

final class RecordingNoticeSender implements NoticeSender {
    private final List<Notice> notices = new ArrayList<>();

    @Override
    public void send(Notice notice) {
        notices.add(Objects.requireNonNull(notice, "notice"));
    }

    List<Notice> sent() {
        return List.copyOf(notices);
    }
}

// CHỐNG MẪU: registry có khả năng chứa mọi loại dịch vụ.
// register có kiểm tra kiểu, nhưng consumer vẫn phải tự require.
final class DependencyBag {
    private final Map<Class<?>, Object> values = new HashMap<>();

    <T> DependencyBag register(Class<T> type, T instance) {
        Objects.requireNonNull(type, "type");
        values.put(type, type.cast(
                Objects.requireNonNull(instance, "instance")));
        return this;
    }

    <T> T require(Class<T> type) {
        Object value = values.get(Objects.requireNonNull(type, "type"));
        if (value == null) {
            throw new IllegalStateException(
                    "Missing dependency: " + type.getSimpleName());
        }
        return type.cast(value);
    }
}

// Thiết kế cũ: chữ ký constructor không lộ ba nhu cầu thực sự.
final class HiddenOrderService {
    private final DependencyBag bag;

    HiddenOrderService(DependencyBag bag) {
        this.bag = Objects.requireNonNull(bag, "bag");
    }

    Receipt place(Order order) {
        Objects.requireNonNull(order, "order");

        // Tra cứu dependency trong logic nghiệp vụ.
        OrderStore store = bag.require(OrderStore.class);
        NoticeSender sender = bag.require(NoticeSender.class);
        Clock clock = bag.require(Clock.class);

        store.save(order);
        Receipt receipt = new Receipt(order.id(), Instant.now(clock));
        sender.send(new Notice(
                order.id(),
                "Accepted " + order.sku() + " x" + order.quantity()));
        return receipt;
    }
}

// Thiết kế đích: nhu cầu được công khai, kiểm tra ở constructor.
final class ExplicitOrderService {
    private final OrderStore store;
    private final NoticeSender sender;
    private final Clock clock;

    ExplicitOrderService(
            OrderStore store, NoticeSender sender, Clock clock) {
        this.store = Objects.requireNonNull(store, "store");
        this.sender = Objects.requireNonNull(sender, "sender");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    Receipt place(Order order) {
        Objects.requireNonNull(order, "order");

        store.save(order);
        Receipt receipt = new Receipt(order.id(), Instant.now(clock));
        sender.send(new Notice(
                order.id(),
                "Accepted " + order.sku() + " x" + order.quantity()));
        return receipt;
    }
}

public class Main {
    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-06-01T10:00:00Z"), ZoneOffset.UTC);

        // 1. Bag đủ dependency vẫn có thể chạy đúng nghiệp vụ.
        InMemoryOrderStore oldStore = new InMemoryOrderStore();
        RecordingNoticeSender oldSender = new RecordingNoticeSender();
        DependencyBag bag = new DependencyBag()
                .register(OrderStore.class, oldStore)
                .register(NoticeSender.class, oldSender)
                .register(Clock.class, clock);
        HiddenOrderService oldService = new HiddenOrderService(bag);

        Order order = new Order("O-1", "BOOK-7", 2);
        Receipt expected = new Receipt(
                "O-1", Instant.parse("2026-06-01T10:00:00Z"));
        check(oldService.place(order).equals(expected),
                "Thiết kế cũ phải trả receipt đúng");
        check(oldStore.findById("O-1").equals(Optional.of(order)),
                "Thiết kế cũ phải lưu đúng đơn");
        check(oldSender.sent().equals(List.of(
                new Notice("O-1", "Accepted BOOK-7 x2"))),
                "Thiết kế cũ phải phát thông báo");

        // 2. Bag mutable có thể đổi implementation sau khi service tạo.
        RecordingNoticeSender replacement = new RecordingNoticeSender();
        bag.register(NoticeSender.class, replacement);
        oldService.place(new Order("O-2", "PEN-1", 1));
        check(oldSender.sent().size() == 1,
                "Sender cũ không nhận thông báo thứ hai");
        check(replacement.sent().equals(List.of(
                new Notice("O-2", "Accepted PEN-1 x1"))),
                "Service cũ đã âm thầm dùng sender mới");

        // 3. Constructor tường minh: caller quyết định cùng ba collaborator.
        InMemoryOrderStore newStore = new InMemoryOrderStore();
        RecordingNoticeSender newSender = new RecordingNoticeSender();
        ExplicitOrderService service =
                new ExplicitOrderService(newStore, newSender, clock);

        check(service.place(order).equals(expected),
                "Thiết kế mới giữ nguyên kết quả công khai");
        check(newStore.findById("O-1").equals(Optional.of(order)),
                "Thiết kế mới lưu đúng đơn");
        check(newSender.sent().equals(List.of(
                new Notice("O-1", "Accepted BOOK-7 x2"))),
                "Thiết kế mới phát đúng thông báo");

        // 4. Thiếu dependency: bag tạo service xong mới lỗi khi gọi.
        DependencyBag incomplete = new DependencyBag()
                .register(OrderStore.class, new InMemoryOrderStore());
        HiddenOrderService hidden = new HiddenOrderService(incomplete);
        boolean runtimeFailure = false;
        try {
            hidden.place(new Order("M-1", "SKU", 1));
        } catch (IllegalStateException expectedFailure) {
            runtimeFailure = true;
        }
        check(runtimeFailure,
                "Thiết kế bag chỉ phát hiện thiếu dependency khi gọi");

        // 5. Constructor DI từ chối thiếu dependency ngay khi lắp ghép.
        boolean constructorFailure = false;
        try {
            new ExplicitOrderService(newStore, null, clock);
        } catch (NullPointerException expectedFailure) {
            constructorFailure = true;
        }
        check(constructorFailure,
                "Constructor phải fail fast với dependency bắt buộc");

        // 6. Repository riêng -> trạng thái riêng, do root quyết định.
        ExplicitOrderService isolated = new ExplicitOrderService(
                new InMemoryOrderStore(),
                notice -> { },
                clock);
        Receipt separate = isolated.place(
                new Order("ISO-1", "RULER", 1));
        check(separate.orderId().equals("ISO-1"),
                "Cấu hình riêng vẫn hoạt động");
        check(newStore.findById("ISO-1").isEmpty(),
                "Dependency riêng không được làm thay đổi store cũ");

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

### Các kết luận từ bài thực hành

1. **Bag không nhất thiết làm logic nghiệp vụ sai ngay.** Khi đủ dependency, `HiddenOrderService` vẫn có thể trả kết quả đúng. Lỗi thiết kế là **hợp đồng bị che giấu và wiring khó kiểm soát**, không phải mọi lần chạy đều sai.
2. **Mutable bag có thể thay hành vi mà không tạo lại service.** Sau `bag.register(NoticeSender.class, replacement)`, service cũ bắt đầu phát thông báo qua sender mới vì nó tự tra cứu trong mỗi lời gọi. Điều này có thể khiến kiểm thử khó tái lập và khó nhận biết thay đổi cấu hình.
3. **Constructor tường minh thể hiện điều kiện khởi tạo hợp lệ.** Thiếu `NoticeSender` bị phát hiện ngay khi gọi `new ExplicitOrderService(...)`, không cần đợi request đầu tiên.
4. **Kết quả nghiệp vụ được giữ lại sau refactor.** Test xác minh receipt, dữ liệu lưu và thông báo — không cần buộc service phải dùng một trình tự helper nội bộ cụ thể.
5. **Scope vẫn là quyết định của root.** Root có thể chia sẻ một repository cho nhiều service hoặc tạo các repository khác nhau khi cần cô lập. Constructor injection **không tự áp đặt singleton**.

**Giới hạn:** ví dụ chạy tuần tự và dùng `HashMap`/`ArrayList`, không phù hợp chia sẻ đa luồng nếu không có thiết kế concurrency. Bước lưu đơn rồi phát thông báo cũng không tự tạo giao dịch nguyên tử: nếu gửi thông báo thất bại sau khi lưu thành công, dữ liệu đã lưu vẫn còn. Hệ thống thực cần xem xét transaction, outbox, retry hoặc idempotency theo yêu cầu nghiệp vụ. DI không tự giải quyết các vấn đề đó.

## 6. Vì sao một “túi có type” vẫn có thể là vấn đề?

Một số người thay `Map<String, Object>` bằng một class typed:

~~~java
final class ApplicationServices {
    OrderStore orderStore() { /* ... */ return null; }
    NoticeSender noticeSender() { /* ... */ return null; }
    Clock clock() { /* ... */ return null; }
    // Sau này thêm mọi service mới vào đây.
}

final class Orders {
    Orders(ApplicationServices services) {
        // Vẫn nhận một object có quá nhiều khả năng.
    }
}
~~~

Đây là **mã minh họa chống mẫu**, không phải implementation biên dịch độc lập. Typed getter giúp giảm lỗi ép kiểu, nhưng business service vẫn có thể truy cập mọi dependency trong hệ thống. Nhu cầu thực sự bị che đi ở constructor; mỗi khi mở rộng `ApplicationServices`, không có tín hiệu nào buộc một class phải xem lại trách nhiệm.

Đánh giá đúng không phải chỉ hỏi “có `Map` không?”, mà hỏi:

- **Một consumer có thể lấy nhiều dịch vụ không liên quan qua object này không?**
- **Consumer có tự tìm dependency mới mà constructor không thay đổi không?**
- **Một test phải dựng cả environment chỉ để dùng một chức năng nhỏ không?**
- **Đây là dữ liệu/abstraction có ý nghĩa, hay một container thu nhỏ được truyền sâu vào domain?**

Một object gói **ba dependency thật sự liên quan** chưa chắc sai nếu nó biểu diễn **một hợp đồng gắn kết** và được cấu hình hợp lý. Nhưng chỉ đổi tên `DependencyBag` thành `OrderContext` mà không thu hẹp chức năng thì không làm thiết kế tốt hơn.

## 7. Refactor dependency bag bằng các bước nhỏ

Với codebase hiện hữu, không cần xóa mọi bag trong một commit. Có thể thay từng consumer và kiểm tra tính tương thích.

### Bước 1 — Ghi lại behavior và dependency thực đang được tra cứu

Đọc implementation của service và các nhánh thực thi, liệt kê những lời gọi như:

~~~text
OrderService.place(...)
  -> bag.require(OrderStore.class)
  -> bag.require(NoticeSender.class)
  -> bag.require(Clock.class)
~~~

Đồng thời ghi lại **hợp đồng nghiệp vụ**: kết quả trả về, dữ liệu được lưu, thông báo và hành vi khi lỗi. Test nên ưu tiên kết quả quan sát được, không ép số lần gọi `bag.require(...)`.

### Bước 2 — Tạo constructor đầy đủ và kiểm tra dependency

Giới thiệu constructor nhận trực tiếp những thứ bắt buộc:

~~~java
ExplicitOrderService(
        OrderStore store,
        NoticeSender sender,
        Clock clock) {
    this.store = Objects.requireNonNull(store, "store");
    this.sender = Objects.requireNonNull(sender, "sender");
    this.clock = Objects.requireNonNull(clock, "clock");
}
~~~

Đây là đoạn rút gọn từ ví dụ hoàn chỉnh. Những trường `final` được gán ở constructor tạo ra **object graph có quan hệ cố định** sau khi service khởi tạo, trừ khi bản thân dependency là mutable. Không tự thay `null` bằng giá trị mặc định trong constructor: làm vậy dễ che lỗi wiring.

### Bước 3 — Để composition root giải quyết bag tạm thời

Khi chưa thể sửa tất cả nơi gọi một lúc, có thể dùng một **adapter lắp ghép tạm** ở composition root:

~~~java
// Minh họa migration; object service ở đây là kiểu ví dụ trên.
OrderStore store = bag.require(OrderStore.class);
NoticeSender sender = bag.require(NoticeSender.class);
Clock clock = bag.require(Clock.class);

ExplicitOrderService service =
        new ExplicitOrderService(store, sender, clock);
~~~

Điểm quan trọng: việc `require(...)` chỉ còn nằm tại **composition root** hoặc migration adapter, **không nằm trong business service**. Root có thể được sửa và kiểm tra riêng, rồi dần thay bag bằng việc tạo adapter tường minh.

### Bước 4 — Chuyển caller, bỏ đường bag khỏi domain

Sửa các điểm khởi tạo service để dùng constructor mới. Khi không còn caller nào cần constructor nhận bag, xóa hoặc deprecate API cũ theo chính sách tương thích. Nếu thư viện đã phát hành public constructor `Orders(Dependencies)`, việc bỏ constructor có thể là breaking change và cần kế hoạch phiên bản.

Không nên giữ cả hai đường vô hạn vì một đường vẫn cho phép dependency ẩn quay lại.

### Bước 5 — Xem lại scope và ownership

Trước khi hoàn tất, trả lời: phiên bản cũ tra cứu dependency mỗi lần gọi hay giữ một instance từ lúc constructor? Nếu chuyển sang giữ `final` field, đó có thể là **thay đổi identity/lifecycle** nếu bag trước đây trả object theo request hoặc được thay nóng.

Không tự động cache một `RequestContext` ngắn hạn trong singleton service. Nếu cần dependency được tạo theo mỗi tác vụ, có thể inject một **factory/provider có kiểu cụ thể và hợp đồng rõ** thay vì đưa cả service registry vào class:

~~~java
// Hợp đồng rõ: chỉ tạo Session, không lấy tùy ý mọi dịch vụ.
interface SessionFactory {
    Session open();
}
~~~

Nếu `Session` giữ tài nguyên, còn phải định nghĩa **ai gọi close()** và lúc nào. Đây là lý do migration cần kiểm tra scope/vòng đời, không chỉ sửa chữ ký constructor.

## 8. Constructor có nhiều tham số: dấu hiệu cần xem lại thiết kế, không phải lý do dùng bag

Một phản biện thường gặp: “Nếu khai báo dependency tường minh, constructor dài quá”. Đó có thể là tín hiệu quan trọng.

Giả sử một `CheckoutService` nhận 12 collaborator: repository, payment gateway, fraud checker, inventory, mail, audit, clock, pricing, shipping, tax, feature flags và metrics. Có ít nhất ba khả năng:

1. **Class gánh quá nhiều trách nhiệm.** Tách use case hoặc component theo vai trò để mỗi class có tập dependency gắn kết.
2. **Một nhóm cộng tác viên thực sự tạo thành abstraction nghiệp vụ có ý nghĩa.** Ví dụ `PaymentAuthorization` có thể là port rõ ràng, phía sau port này phối hợp gateway, fraud và audit. Service bên ngoài cần hành vi “authorize” chứ không cần biết mọi chi tiết.
3. **Một số giá trị thuộc lời gọi, không thuộc trạng thái lâu dài của service.** Ví dụ user ID, locale hoặc request token có thể truyền như **tham số phương thức** thay vì inject vào singleton.

### Không đánh đồng nhóm giá trị với nhóm dịch vụ

Một `OrderSubmissionOptions(boolean dryRun, String locale)` có thể là **value object** hợp lý cho một lời gọi. Nhưng một `OrderDependencies` chỉ chứa mười getter về hạ tầng chưa chắc là abstraction tốt, dù nó có kiểu cụ thể và constructor ngắn.

Một quy tắc thực hành:

> Nếu consumer cần một **hành vi có tên rõ ràng**, cung cấp một interface thực hiện hành vi đó. Nếu consumer cần ba **cộng tác viên bắt buộc độc lập**, hãy thể hiện cả ba. Nếu chỉ cần một tập **giá trị liên quan**, có thể dùng một configuration/value object.

Đừng tạo `ServicesFacade` chỉ để ủy quyền `getStore()`, `getEmail()`, `getAudit()` và `getClock()` mà không có trách nhiệm nghiệp vụ riêng.

## 9. Phân biệt Service Locator với DI container dùng đúng chỗ

DI container thường có chức năng **resolve dependency**. Vì vậy nhìn bên ngoài, một câu lệnh như `container.resolve(OrderService.class)` không nhất thiết là chống mẫu nếu đặt **ở composition root**.

Điều cần phân biệt là **ranh giới sử dụng**:

~~~java
// Có thể phù hợp: root khởi tạo điểm vào ứng dụng.
OrderService service = container.resolve(OrderService.class);

// Cần cảnh giác: bên trong business method tự resolve tùy ý.
PaymentGateway gateway = container.resolve(PaymentGateway.class);
~~~

Đoạn này chỉ minh họa API container giả định. Trong ví dụ thứ nhất, application root chịu trách nhiệm lắp ghép và caller dùng service đã nhận. Trong ví dụ thứ hai, business service phụ thuộc vào chính container, làm dependency có thể thay đổi ngầm và khó unit test bằng Java thuần.

Một số framework có **typed provider**, **scoped proxy** hoặc factory do container cung cấp để tạo object theo yêu cầu. Việc inject `Provider<Session>` **không tự động là lỗi thiết kế** nếu consumer thực sự cần tạo session theo mỗi tác vụ, provider có **một loại sản phẩm cụ thể** và lifecycle/ownership rõ ràng.

Không nên biến mọi nhu cầu mở resource thành `Provider<Object>` hoặc truyền trực tiếp root container cho toàn bộ domain. Như thế là chuyển từ constructor injection sang Service Locator với tên khác.

## 10. Scope, thread safety và quyền sở hữu khi bỏ bag

Dependency bag có thể khiến nhiều lỗi vòng đời bị giấu bên dưới API `get()`:

| Nguy cơ | Với bag | Cách làm rõ khi dùng DI tường minh |
| --- | --- | --- |
| **Instance bị thay nóng** | Registry mutable trả implementation khác giữa các lời gọi | Inject dependency cố định hoặc một cơ chế reconfiguration có hợp đồng riêng |
| **Dependency hết scope** | Singleton giữ bag rồi lấy request context bất chấp vòng đời | Truyền request data qua method hoặc typed scoped provider |
| **Dùng chung resource không an toàn** | Mọi service lấy cùng session/connection từ registry | Root chia sẻ pool/factory phù hợp; cấp session theo tác vụ |
| **Không rõ ai đóng** | Consumer gọi `get()` không biết borrowed/owned | Mô tả ownership và cleanup của constructor/factory |
| **Không an toàn đa luồng** | Bag và các object bên trong đều có thể mutable | Đánh giá thread safety theo từng instance/scope |
| **Test nhiễm trạng thái** | Một bag singleton giữ fake hoặc cache qua nhiều test | Mỗi test lắp object graph riêng; context được đóng đúng cách |

**Constructor injection không biến một dependency mutable thành bất biến hay thread-safe.** Nó làm rõ *đối tượng nào* được cấp lúc tạo service; chất lượng implementation và scope vẫn phải được kiểm soát riêng.

Với những tài nguyên do composition root tạo như HTTP client, connection pool hoặc executor, root/lifecycle manager thường sở hữu vòng đời. Consumer nhận và sử dụng chúng nhưng không tự đóng sau mỗi request, trừ khi có hợp đồng chuyển quyền sở hữu. Với resource được tạo **mỗi lời gọi** qua factory, caller có thể cần `try-with-resources` để bảo đảm cleanup ngay cả khi lỗi.

## 11. Kiểm thử: đừng chỉ xác minh lệnh tra cứu

Một bài test tập trung sai chỗ thường cố chứng minh `HiddenOrderService` đã gọi `bag.require(OrderStore.class)` đúng một lần hoặc hỏi `Clock.class` ở vị trí thứ ba. Các assertion đó ràng buộc **cơ chế nội bộ** chứ không bảo vệ kết quả.

Nên tách hai nhóm:

**Unit test hành vi:** tạo `ExplicitOrderService` với fake `OrderStore`, recorder `NoticeSender` và `Clock.fixed(...)`; kiểm tra receipt, dữ liệu lưu, thông báo và lỗi nghiệp vụ. Ví dụ `Main.java` đã minh họa các outcome này mà không cần mock framework.

**Wiring/integration test:** tạo object graph thực theo composition root hoặc DI container, kiểm tra adapter được chọn đúng, dependency bắt buộc không thiếu, scope/lifecycle và quyền sở hữu resource hợp lệ.

Riêng trong giai đoạn migration, có thể viết **một test so sánh behavior** của đường cũ và đường mới, như ví dụ cùng trả một `Receipt`. Điều đó không có nghĩa nên giữ kiểm thử dành riêng cho dependency bag mãi mãi; sau khi bỏ đường cũ, test nên tập trung vào hợp đồng của thiết kế mới.

### Bổ sung test cho trường hợp lỗi

Ví dụ hiện tại chỉ minh họa fail-fast của **thiếu dependency**. Khi triển khai thật, nên bổ sung:

- `OrderStore.save(...)` ném lỗi: không phát xác nhận thành công.
- Đơn trùng: không ghi đè dữ liệu và không phát xác nhận mới.
- Clock cố định để kết quả timestamp dễ kiểm tra.
- Một fake sender ném lỗi sau khi lưu: xác định trạng thái đã lưu và chính sách retry/outbox nếu cần.
- Hai service được inject chung một repository có thật sự chia sẻ trạng thái theo yêu cầu không.

Những tình huống này có giá trị hơn việc đếm số lần `get(Class<T>)` xuất hiện trên bag.

## 12. Khi nào một nhóm dependency có thể được chấp nhận?

Để tránh cực đoan, có những nơi **nhóm nhiều dependency** là thiết kế hợp lý:

1. **Composition root hoặc module cấu hình:** nó thực sự có trách nhiệm lắp ghép nhiều service. Nó có thể dùng registry/container làm công cụ, nhưng không truyền API tra cứu tổng quát sâu vào domain.
2. **Factory với tập cấu hình giới hạn:** factory nhận `DatabaseSettings` và `Clock` để tạo một loại component, miễn ranh giới trách nhiệm rõ.
3. **Aggregate/facade nghiệp vụ:** tập hợp các cộng tác viên phía sau một interface hành vi có ý nghĩa như `InventoryReservation` hoặc `PaymentAuthorization`.
4. **Request context chứa dữ liệu theo request:** `RequestIdentity` hoặc `TraceMetadata` có thể là value object, được truyền đúng scope; nó không phải kho mọi service.
5. **Migration adapter tạm thời:** trong lúc refactor hệ thống cũ, một nơi lắp ghép có thể còn dùng bag để giải quyết các dependency rồi tiêm tường minh cho lớp mới.

Tiêu chí đánh giá không phải “ít tham số nhất” mà là **mức độ rõ ràng của hợp đồng và khả năng thay đổi có kiểm soát**. Một constructor ba tham số có tên rõ có thể tốt hơn một constructor một tham số chứa một ngàn khả năng.

## 13. Những lỗi sửa sai cần tránh

### 13.1. Đổi tên bag nhưng không đổi quyền tra cứu

`ApplicationContext` đổi thành `OrderContext` mà vẫn cho lấy bất cứ repository, client hay logger không làm phụ thuộc hiện ra rõ hơn.

### 13.2. Dùng fallback ngầm cho dependency thiếu

~~~java
OrderStore store = bag.find(OrderStore.class)
        .orElseGet(InMemoryOrderStore::new);
~~~

Trong production, thiếu cấu hình database có thể bị che bằng bộ nhớ tạm, gây mất dữ liệu hoặc hành vi sai. Với dependency bắt buộc, **báo lỗi wiring sớm** thay vì chọn mặc định không được phê duyệt.

### 13.3. Tạo một interface khổng lồ để tránh generic Map

Một interface `AllServices` với hàng chục getter vẫn trao cho business service quyền truy cập mọi thứ. Hãy thu hẹp theo trách nhiệm hoặc chia thành các port có hành vi rõ.

### 13.4. Bỏ bag nhưng giữ Service Locator tĩnh

Thay `bag.require(PaymentGateway.class)` bằng `GlobalServices.get(PaymentGateway.class)` khiến vấn đề tệ hơn: dependency còn bị che và giờ phụ thuộc vào trạng thái toàn cục khó cô lập.

### 13.5. Đưa dữ liệu theo request vào singleton constructor

Không phải mọi thứ từng được lấy từ bag đều nên trở thành field `final` của singleton service. Request identity, transaction hoặc session ngắn hạn cần đi theo vòng đời phù hợp.

### 13.6. Ép mọi đối tượng đều phải inject

Đối tượng giá trị, collection nội bộ hay helper thuần tính toán có thể được tạo cục bộ. DI tập trung vào **quyền chọn và sử dụng cộng tác viên** mà ứng dụng cần quản lý/chuyển đổi; không phải cấm `new` ở mọi nơi.

## 14. Bài tập thực hành

**Bài 1 — Tìm nhu cầu thật.** Một `InvoiceService` nhận `ApplicationServices` rồi gọi `get(InvoiceStore.class)`, `get(Clock.class)` và `get(TaxCalculator.class)`. Hãy viết lại chữ ký constructor bộc lộ đúng ba dependency; thêm kiểm tra `null` và cập nhật wiring tại composition root.

**Bài 2 — Phân biệt bag với config.** So sánh `HttpClientSettings(baseUrl, timeout)`, `Map<Class<?>, Object>` và `PaymentProcessor.authorize(...)`. Object nào là cấu hình có ý nghĩa, object nào là registry và object nào là abstraction hành vi? Giải thích vì sao.

**Bài 3 — Scope thay đổi ngầm.** `DependencyBag` trả một `RequestContext` mới cho từng request, nhưng sau refactor lập trình viên inject một context vào constructor của service singleton. Hãy dự đoán lỗi và sửa bằng method parameter hoặc typed scoped provider.

**Bài 4 — Test lỗi wiring.** Từ ví dụ `Main.java`, bỏ `NoticeSender` khỏi bag và kiểm tra thời điểm lỗi được phát hiện. So sánh với lời gọi constructor `new ExplicitOrderService(store, null, clock)`.

**Bài 5 — Constructor dài.** Một class có 10 dependency, trong đó 6 dependency dùng cho thanh toán và 4 dependency dùng cho gửi email. Đề xuất cách tách trách nhiệm hoặc xây hai facade có hành vi rõ ràng mà không tạo `AllServices`.

**Bài 6 — Ownership.** Một registry trả về cùng `Connection` mutable cho mọi request, trong khi các consumer gọi `close()` ở cuối request. Giải thích vì sao cách này rủi ro; đề xuất dùng pool chung và factory tạo/mượn connection theo tác vụ với quy tắc trả về pool.

## 15. Tự kiểm tra hiểu bài

**Câu 1.** Truyền `Dependencies` qua constructor có tự động là constructor injection tốt không? **Không.** Nếu service dùng object đó để tự tra cứu tùy ý, dependency thật vẫn bị che giấu.

**Câu 2.** Khi nào việc sử dụng `container.resolve(...)` có thể hợp lý? **Tại composition root hoặc phần cấu hình lắp ghép**, nơi có nhiệm vụ tạo object graph; tránh đưa container vào logic nghiệp vụ.

**Câu 3.** Nếu đổi `Map<Class<?>, Object>` thành một class có typed getter, anti-pattern có biến mất không? **Không nhất thiết.** Nếu class vẫn là kho mọi dịch vụ và consumer có quyền tra cứu rộng, vấn đề hợp đồng ẩn còn nguyên.

**Câu 4.** Vì sao constructor tường minh giúp fail fast? **Vì** nhu cầu bắt buộc hiện ra trong tham số; có thể kiểm tra thiếu dependency ngay khi tạo service và container/root có thể xác minh wiring sớm.

**Câu 5.** Constructor nhiều tham số có phải lúc nào cũng nên đổi thành dependency bag? **Không.** Hãy xem trách nhiệm class có cần tách và những nhóm nào thực sự có ý nghĩa như facade hoặc value object.

**Câu 6.** Có nên inject một `SessionFactory` thay vì một session toàn cục nếu mỗi transaction cần session riêng? **Thường có thể**, với điều kiện factory có kiểu cụ thể, scope và ownership của session được định nghĩa rõ.

**Câu 7.** Test cần ưu tiên điều gì sau khi bỏ dependency bag? **Kết quả nghiệp vụ, side effect và lỗi có ý nghĩa**, cộng một số test wiring/scope ở composition root, thay vì đếm mọi lần tra cứu nội bộ.

## Ghi nhớ

- **Dependency bag tổng quát che giấu nhu cầu thực sự** dù bản thân bag được truyền qua constructor. Nó thường là một dạng Service Locator nằm trong lớp nghiệp vụ.
- **Constructor injection tường minh** cho biết class cần chính xác những cộng tác viên nào, giúp phát hiện lỗi cấu hình sớm, kiểm thử bằng Java thuần và kiểm soát object graph tại composition root.
- **Không phải mọi nhóm dữ liệu đều sai:** value object, configuration có ý nghĩa, facade hành vi và typed factory đều có chỗ đứng nếu hợp đồng và trách nhiệm rõ ràng.
- Khi refactor, **đừng chỉ đổi cú pháp**: cần xác định liệu lookup trước đây trả instance dùng chung, theo request hay transient, và ai sở hữu/đóng tài nguyên.
- **DI container/registry nên phục vụ việc lắp ghép**, không trở thành API tra cứu toàn cục của domain. Mục tiêu của DI/IoC là tách việc sử dụng phụ thuộc khỏi việc lựa chọn, tạo và lắp ghép chúng.
