# Test double và kiểm soát phụ thuộc ngoài trong Java 27

Trong chương **Kiểm thử và chất lượng** của lộ trình **Java 27**, một bài kiểm thử đáng tin cậy phải kiểm tra được **hành vi nghiệp vụ** mà không vô tình gửi email thật, tính tiền khách hàng, chờ mạng bên ngoài hoặc phụ thuộc vào thời gian hệ thống. Để làm được điều đó, ta cần xác định rõ **ranh giới giữa code đang kiểm thử và những cộng tác viên bên ngoài** rồi thay thế có kiểm soát một số cộng tác viên bằng **test double**.

*Test double* là tên gọi chung cho một đối tượng được đưa vào thay cho đối tượng cộng tác thật trong kiểm thử. Những loại thường gặp là **dummy**, **stub**, **fake**, **spy** và **mock**. Điểm cốt lõi không phải chọn được một framework tạo mock, mà là thiết kế hệ thống có ranh giới phụ thuộc rõ ràng, chọn đúng mức độ cô lập và vẫn có kiểm thử xác nhận cách hệ thống tương tác với dịch vụ thật.

Bài học dùng các đặc điểm Java vẫn phù hợp trong Java 27: `interface`, `record`, constructor injection, `java.time.Clock`, `java.net.http.HttpClient`, `java.util.concurrent` và **JUnit Jupiter** hiện hành. Code mẫu chính dùng Java thuần để có thể hiểu và chạy không cần framework; ví dụ JUnit được trình bày riêng.

> **Nguyên tắc:** test double giúp **kiểm thử nhanh, xác định và an toàn**; chúng **không chứng minh** database, HTTP API hay hệ thống thanh toán thật sẽ hành xử giống hệt. Những khác biệt ấy cần contract test và integration test.

## 1. Vấn đề: nghiệp vụ vô tình phụ thuộc thế giới bên ngoài

Giả sử một service nhắc khách hàng thanh toán hóa đơn:

```java
class ReminderService {
    void sendReminder(String invoiceId) {
        // Truy vấn database thật.
        // Đọc giờ hệ thống.
        // Gọi API email thật.
        // Cập nhật trạng thái database.
    }
}
```

Nếu test gọi thẳng service này, một lần chạy có thể:

- Gửi thông báo đến người thật hoặc tính phí API.
- Chậm/thất bại do DNS, TLS, mạng, quota hoặc dịch vụ bảo trì.
- Cho kết quả khác giữa các lần chạy vì `Instant.now()`.
- Bị ảnh hưởng bởi dữ liệu từ test khác hoặc môi trường staging.
- Khó tái hiện trường hợp email gửi thất bại tại đúng một bước.
- Làm thay đổi database cần chia sẻ với các thành phần khác.

Trong khi đó, logic mà ta muốn xác nhận thường rất nhỏ: **chỉ gửi nhắc khi hóa đơn đến hạn và chưa được nhắc; nếu gửi thành công mới đánh dấu đã gửi**.

Thay vì mô phỏng cả Internet, ta đưa những thao tác ngoài phạm vi xử lý nghiệp vụ qua **interface do ứng dụng sở hữu**.

```text
                  REMINDER SERVICE
                  (logic cần test)
                         |
        +----------------+------------------+
        |                |                  |
        v                v                  v
    InvoiceStore    Notifier            Clock
        |                |                  |
  Production:         Production:        Production:
  SQL/JDBC            Email API          systemUTC()
        |                |                  |
  Test:               Test:             Test:
  FakeStore           Spy/Stub          fixed()
```

Ở đây `Clock` đã là abstraction có sẵn của JDK, không cần tự tạo `TimeProvider` chỉ để trả về thời gian.

## 2. Xác định ranh giới SUT và collaborator

**System Under Test (SUT)** là thành phần hoặc hành vi được kiểm tra. **Collaborator** là thành phần mà SUT gọi để hoàn thành công việc.

Trong ví dụ:

- SUT: logic của `ReminderService`.
- Collaborator: kho hóa đơn (`InvoiceStore`), kênh gửi thông báo (`Notifier`), nguồn thời gian (`Clock`).
- Output quan trọng: quyết định gửi hay không, trạng thái được đánh dấu, số lần gửi.
- Lỗi cần thử: kho dữ liệu trả thiếu bản ghi, gửi thông báo thất bại, thời điểm trước/sau hạn.

Không phải collaborator nào cũng phải bị thay thế. Một `record` bất biến, một `List`, hoặc hàm thuần Java không phụ thuộc I/O thường nên được dùng **thật** trong test. Thay mọi thứ bằng mock khiến test chỉ còn kiểm tra một kịch bản do chính mock lập trình.

### 2.1. Những phụ thuộc dễ tạo nondeterminism

| Phụ thuộc | Nguồn biến động | Ranh giới kiểm soát |
| --- | --- | --- |
| Đồng hồ | Thời gian thực, timezone, ngày chuyển đổi | `Clock`/`InstantSource` |
| Network/HTTP | Latency, timeout, lỗi 4xx/5xx, redirect | HTTP gateway/transport adapter |
| Database | Schema, transaction, isolation, dữ liệu chung | Repository port và integration test DB thật |
| Filesystem | Permission, đường dẫn, file tồn tại, dung lượng | File store abstraction hoặc thư mục tạm test |
| Email/SMS/payment | Side effect, quota, dữ liệu khách hàng | Gateway port + fake/spy, sandbox integration |
| Random/UUID | Giá trị mỗi lần khác nhau | `Supplier<UUID>` hoặc abstraction sinh ID |
| Executor/async | Scheduling và race condition | Điểm submit task, latch/future/scheduler thích hợp |
| Environment | Biến môi trường, secrets, locale | Cấu hình được inject và fixture riêng |
| Cache | Shared state, TTL, eviction | Cache abstraction + test thời gian/contract |

**Chú ý:** không phải cứ có I/O là bắt buộc mock. Nếu có thể dùng file tạm hoặc một server loopback được quản lý trong test, chạy với hệ thống thật ở mức nhỏ thường cung cấp bằng chứng thực tế tốt hơn.

## 3. Năm loại test double: dummy, stub, fake, spy, mock

Thuật ngữ này thường được nhắc tới trong mô hình của Gerard Meszaros và Martin Fowler:

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| **Dummy** | Điền một tham số bắt buộc nhưng test không sử dụng tới | Đối tượng không được gọi trong nhánh đang test |
| **Stub** | Trả kết quả/exception được chuẩn bị sẵn | Repository trả `Optional.empty()` hoặc gateway trả HTTP 503 |
| **Fake** | Triển khai logic hoạt động được nhưng rút gọn so với production | Repository lưu trong `HashMap` thay database |
| **Spy** | Ghi nhận các lời gọi hoặc side effect để quan sát sau | Ghi danh sách email đã “gửi” |
| **Mock** | Có kỳ vọng tương tác đã khai báo; test xác minh kỳ vọng đó | Kỳ vọng `charge()` đúng một lần với tham số cụ thể |

Trong giao tiếp hằng ngày, từ “mock” đôi khi bị dùng để chỉ mọi test double. Tuy nhiên, phân biệt chính xác giúp trả lời: **test đang kiểm tra kết quả trạng thái hay đang kiểm tra tương tác?**

### 3.1. State verification và behavior verification

**State verification** kiểm tra kết quả sau khi thực thi:

```java
// Sau khi gửi reminder, hóa đơn đã được đánh dấu.
assertTrue(store.find("INV-1").orElseThrow().sent());
```

**Behavior verification** kiểm tra tương tác giữa SUT và collaborator:

```java
// Đã gửi đúng một notification.
assertEquals(1, notifier.deliveries().size());
```

Hai phong cách có thể kết hợp. Hãy chỉ kiểm tra tương tác **mang ý nghĩa hợp đồng**: số lần thực hiện side effect, recipient, thông tin thanh toán, không gọi payment sau khi validation thất bại. Tránh xác minh mọi lệnh gọi helper nội bộ theo thứ tự nếu thứ tự đó không quan trọng với nghiệp vụ.

## 4. Dummy: điền chỗ trống nhưng không được sử dụng

Giả sử một method cần nhận `AuditSink`, nhưng test đang kiểm tra nhánh trả về sớm trước khi audit được dùng.

```java
interface AuditSink {
    void record(String event);
}

// Dùng như dummy trong test chỉ khi biết nhánh này KHÔNG gọi audit.
AuditSink unusedAudit = event -> {
    throw new AssertionError("Audit must not be called here");
};
```

Một dummy có thể là object tối giản hoặc **throwing implementation** để phát hiện nếu test bất ngờ sử dụng nó. Nhưng đừng dùng `null` vô điều kiện: null có thể khiến code thất bại vì lý do khác với hành vi cần test, và không đại diện cho contract thực tế.

Khi một tham số không cần cho nhiều test, có thể đó là dấu hiệu class đang nắm quá nhiều trách nhiệm; cân nhắc tách dependency theo chức năng.

## 5. Stub: trả kết quả được sắp đặt

Stub cung cấp **câu trả lời có kiểm soát** từ dependency, không cần triển khai toàn bộ logic của nó.

```java
import java.util.Optional;

interface UserDirectory {
    Optional<String> emailOf(String userId);
}

UserDirectory found = userId ->
    Optional.of("customer@example.invalid");

UserDirectory notFound = userId ->
    Optional.empty();
```

Có thể thử hai nhánh mà không tạo database thật. Nếu phương thức có thể ném checked exception, stub cũng có thể được cấu hình để ném exception đúng kiểu; nếu signature không khai báo checked exception, đừng ép một `IOException` sai contract.

### 5.1. Stub giúp tái hiện lỗi hiếm

```java
interface ExchangeRateGateway {
    double currentRate(String currency);
}

ExchangeRateGateway unavailable = currency -> {
    throw new IllegalStateException("Simulated rate service outage");
};
```

Test sẽ điều khiển chính xác thời điểm lỗi, thay vì tắt mạng hoặc chờ dịch vụ thật gặp sự cố. Tuy nhiên, nếu production gateway thực tế ném một exception được wrap khác, integration test phải xác nhận mapping exception từ adapter thật sang contract của port.

**Không tạo stub trả dữ liệu phi thực tế rồi kết luận nghiệp vụ đúng**. Stub phải tôn trọng những điều kiện cơ bản của interface; các dữ liệu bất hợp lệ nên là testcase có chủ ý.

## 6. Fake: một triển khai có trạng thái nhưng đơn giản hơn production

Một fake repository lưu dữ liệu trong bộ nhớ:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

interface ProductStore {
    Optional<String> findName(String id);
    void save(String id, String name);
}

final class FakeProductStore implements ProductStore {
    private final Map<String, String> values = new HashMap<>();

    @Override
    public Optional<String> findName(String id) {
        return Optional.ofNullable(values.get(id));
    }

    @Override
    public void save(String id, String name) {
        values.put(id, name);
    }
}
```

Nó có thể dùng trong nhiều test và cho phép kiểm tra **trạng thái sau thao tác**, nhưng không tương đương database thật.

### 6.1. Các hành vi fake thường không tái hiện đủ

| Hợp đồng cần kiểm tra | In-memory fake có thể khác production |
| --- | --- |
| Unique constraint | `HashMap.put` có thể overwrite thay vì reject |
| Transaction/rollback | Không có commit/rollback |
| Isolation và concurrency | `HashMap` không thread-safe |
| Query ordering | Thứ tự có thể khác nếu không được định nghĩa |
| SQL NULL, collation, timezone | Các quy tắc khác Java object semantics |
| Pagination | Fake có thể tính sai offset/limit |
| Generated IDs | Fake dùng bộ đếm khác database sequence |
| Optimistic locking | Thiếu version/check-and-update |
| Serialization | Không kiểm tra JSON hoặc database mapping thật |
| Network failure | Mọi thao tác in-memory thường thành công tức thì |

Đừng cố biến fake thành **một hệ thống database thứ hai viết lại trong Java**. Khi contract phụ thuộc tính năng database thật, tốt hơn nên có integration test trên database tương ứng, có thể khởi tạo bằng Testcontainers.

## 7. Spy và mock: quan sát tương tác quan trọng

Spy lưu lại lời gọi, thường **không gửi thông tin ra ngoài**.

```java
import java.util.ArrayList;
import java.util.List;

interface Mailer {
    void send(String recipient, String body);
}

final class RecordingMailer implements Mailer {
    record Delivery(String recipient, String body) { }

    private final List<Delivery> sent = new ArrayList<>();

    @Override
    public void send(String recipient, String body) {
        sent.add(new Delivery(recipient, body));
    }

    List<Delivery> deliveries() {
        return List.copyOf(sent);
    }
}
```

Test có thể xác minh `deliveries()` chứa đúng một email và đúng recipient. Đây là **hand-written spy**; không cần Mockito.

### 7.1. Mock với kỳ vọng xác định

Trong Mockito hoặc framework tương tự, một mock có thể được cấu hình và xác minh:

```java
// Ví dụ minh họa khi test project đã có Mockito.
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

Mailer mailer = mock(Mailer.class);

mailer.send("customer@example.invalid", "Reminder");
verify(mailer, times(1))
    .send(eq("customer@example.invalid"), eq("Reminder"));
```

Mục tiêu của ví dụ là **mô tả kỳ vọng tương tác**. Đặt phần sử dụng Mockito vào một test class hoặc method phù hợp, không coi các lệnh `import` là có thể đặt giữa một method Java.

Mockito giúp tạo double nhanh, nhưng **không bắt buộc** trong Java 27. Trong nhiều trường hợp, một fake/spy viết tay rõ nghĩa và không phụ thuộc cơ chế bytecode instrumentation là đủ.

### 7.2. Khi nào cần xác minh “không được gọi”?

Với thanh toán hoặc side effect không thể đảo ngược, *không gọi* là một yêu cầu quan trọng:

```java
// Nếu đơn hàng không hợp lệ, payment gateway không được charge.
verify(paymentGateway, never()).charge(any());
```

Nhưng đừng biến mọi test thành “mọi helper đều được gọi đúng 1 lần” nếu thứ tự và số lần gọi không nằm trong hợp đồng. Test kiểu đó dễ thất bại chỉ vì refactor nội bộ, dù kết quả nghiệp vụ vẫn đúng.

## 8. Tạo điểm thay thế bằng dependency inversion

Production code nên phụ thuộc vào **contract** mà ứng dụng kiểm soát, không bị khóa vào một lớp SDK cụ thể:

```java
interface PaymentGateway {
    Receipt charge(PaymentRequest request);
}

record PaymentRequest(String orderId, long cents) { }
record Receipt(String providerReference) { }
```

Adapter thật:

```java
final class RemotePaymentGateway implements PaymentGateway {
    private final PaymentSdk sdk;

    RemotePaymentGateway(PaymentSdk sdk) {
        this.sdk = sdk;
    }

    @Override
    public Receipt charge(PaymentRequest request) {
        // Chuyển request/domain type sang contract của SDK.
        // Xử lý lỗi và trả lại Receipt.
        throw new UnsupportedOperationException("Adapter sketch");
    }
}
```

`PaymentSdk` là tên placeholder của một dependency bên thứ ba; đây là **phác thảo kiến trúc**, không phải đoạn code có thể biên dịch khi chưa có SDK. Phần ví dụ chạy độc lập phía sau sẽ chỉ dùng các interface và class đã định nghĩa trong cùng file.

### 8.1. Constructor injection là lựa chọn đơn giản

```java
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    Receipt checkout(PaymentRequest request) {
        return gateway.charge(request);
    }
}
```

Trong production:

```java
// CheckoutService service = new CheckoutService(realPaymentGateway);
```

Trong test:

```java
PaymentGateway fakeGateway = request -> new Receipt("TEST-REF-42");
CheckoutService service = new CheckoutService(fakeGateway);
```

**Không cần dependency injection framework** chỉ để thực hiện constructor injection. Framework có thể hữu ích trong ứng dụng nhiều component, nhưng nguyên tắc thiết kế vẫn là tách contract khỏi implementation.

## 9. Ví dụ hoàn chỉnh: service nhắc hạn thanh toán có thể test độc lập

Một bài toán minh họa gồm:

- Tìm một hóa đơn theo ID.
- Nếu chưa đến hạn hoặc đã gửi reminder, không gửi nữa.
- Nếu đến hạn và chưa gửi, gọi `Notifier`.
- Chỉ đánh dấu đã gửi sau khi lời gọi notifier trả thành công.

Dữ liệu được biểu diễn bằng `record` bất biến; `Clock.fixed` kiểm soát thời gian; repository và notifier được cung cấp qua interface.

Lưu toàn bộ chương trình dưới tên `ReminderExample.java` khi thực hành:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class ReminderExample {
    public record Invoice(
        String id,
        String email,
        Instant dueAt,
        boolean sent
    ) {
        public Invoice {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(email, "email");
            Objects.requireNonNull(dueAt, "dueAt");
        }
    }

    public interface InvoiceStore {
        Optional<Invoice> find(String id);
        void markSent(String id);
    }

    public interface Notifier {
        void send(String recipient, String body);
    }

    public static final class ReminderService {
        private final InvoiceStore store;
        private final Notifier notifier;
        private final Clock clock;

        public ReminderService(
                InvoiceStore store,
                Notifier notifier,
                Clock clock) {
            this.store = Objects.requireNonNull(store);
            this.notifier = Objects.requireNonNull(notifier);
            this.clock = Objects.requireNonNull(clock);
        }

        public boolean sendIfDue(String id) {
            Invoice invoice = store.find(id).orElseThrow(
                () -> new IllegalArgumentException("Unknown invoice: " + id)
            );

            if (invoice.sent() || clock.instant().isBefore(invoice.dueAt())) {
                return false;
            }

            notifier.send(
                invoice.email(),
                "Reminder for invoice " + invoice.id()
            );

            store.markSent(invoice.id());
            return true;
        }
    }

    // Fake lưu dữ liệu trong memory để test logic.
    public static final class FakeInvoiceStore implements InvoiceStore {
        private final Map<String, Invoice> data = new HashMap<>();

        public void put(Invoice invoice) {
            data.put(invoice.id(), invoice);
        }

        @Override
        public Optional<Invoice> find(String id) {
            return Optional.ofNullable(data.get(id));
        }

        @Override
        public void markSent(String id) {
            Invoice current = data.get(id);
            if (current == null) {
                throw new IllegalArgumentException("Unknown invoice: " + id);
            }
            data.put(id, new Invoice(
                current.id(),
                current.email(),
                current.dueAt(),
                true
            ));
        }
    }

    // Spy ghi lời gọi, không gửi email thật.
    public static final class RecordingNotifier implements Notifier {
        public record Delivery(String recipient, String body) { }

        private final List<Delivery> deliveries = new ArrayList<>();

        @Override
        public void send(String recipient, String body) {
            deliveries.add(new Delivery(recipient, body));
        }

        public List<Delivery> deliveries() {
            return List.copyOf(deliveries);
        }
    }

    public static void main(String[] args) {
        Clock fixedClock = Clock.fixed(
            Instant.parse("2026-11-27T00:00:00Z"),
            ZoneOffset.UTC
        );

        var store = new FakeInvoiceStore();
        store.put(new Invoice(
            "INV-1",
            "customer@example.invalid",
            Instant.parse("2026-11-26T00:00:00Z"),
            false
        ));

        var notifier = new RecordingNotifier();
        var service = new ReminderService(store, notifier, fixedClock);

        if (!service.sendIfDue("INV-1")) {
            throw new AssertionError("Expected reminder");
        }
        if (service.sendIfDue("INV-1")) {
            throw new AssertionError("Reminder must not be repeated");
        }
        if (notifier.deliveries().size() != 1) {
            throw new AssertionError("Expected exactly one notification");
        }
        if (!store.find("INV-1").orElseThrow().sent()) {
            throw new AssertionError("Invoice not marked as sent");
        }

        System.out.println("Reminder checks passed");
    }
}
```

Chạy không cần JUnit hay Mockito:

```text
javac ReminderExample.java
java ReminderExample
```

Kết quả:

```text
Reminder checks passed
```

### 9.1. Vì sao ví dụ có giá trị kiểm thử?

- `ReminderService` không biết repository dùng JDBC hay `HashMap`.
- `Notifier` không biết email provider nào đang được dùng.
- `Clock` không phụ thuộc thời gian thực.
- `FakeInvoiceStore` cho phép thiết lập trạng thái đầu vào chính xác.
- `RecordingNotifier` quan sát được tác dụng phụ mà không gửi email.
- Mỗi test có thể tạo **fixture riêng**; không cần một singleton fake hoặc database dùng chung.
- Code nghiệp vụ vẫn chạy thật; chỉ thay ranh giới ngoài.

### 9.2. Hạn chế thiết kế của ví dụ

Đây là ví dụ dạy testability, **không phải mô hình gửi thông báo exactly-once production**.

Nếu hai request đồng thời đọc cùng hóa đơn trước khi một request đánh dấu đã gửi, cả hai có thể gọi `Notifier` và gây thông báo trùng. Nếu notification đã được gửi nhưng `store.markSent()` thất bại, lần retry cũng có thể gửi lại.

Production thường cần giải quyết bằng transaction/outbox, idempotency key, trạng thái có kiểm soát concurrency hoặc một giao thức phối hợp; **fake in-memory đơn luồng không kiểm tra được những bảo đảm đó**.

## 10. Viết JUnit Jupiter test cho cùng use case

Các class `ReminderExample` ở trên là Java thuần. Trong project đã cấu hình **JUnit Jupiter**, ta có thể viết `ReminderExampleTest.java`:

```java
import org.junit.jupiter.api.Test;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.*;

class ReminderExampleTest {
    private static Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-11-27T00:00:00Z"),
            ZoneOffset.UTC
        );
    }

    @Test
    void sendsOnlyOnceWhenInvoiceIsDue() {
        var store = new ReminderExample.FakeInvoiceStore();
        store.put(new ReminderExample.Invoice(
            "INV-42",
            "customer@example.invalid",
            Instant.parse("2026-11-26T00:00:00Z"),
            false
        ));

        var notifier = new ReminderExample.RecordingNotifier();
        var service = new ReminderExample.ReminderService(
            store, notifier, fixedClock()
        );

        assertTrue(service.sendIfDue("INV-42"));
        assertFalse(service.sendIfDue("INV-42"));
        assertTrue(store.find("INV-42").orElseThrow().sent());
        assertEquals(1, notifier.deliveries().size());
        assertEquals(
            "customer@example.invalid",
            notifier.deliveries().getFirst().recipient()
        );
    }

    @Test
    void doesNotSendBeforeDueTime() {
        var store = new ReminderExample.FakeInvoiceStore();
        store.put(new ReminderExample.Invoice(
            "INV-FUTURE",
            "customer@example.invalid",
            Instant.parse("2026-11-28T00:00:00Z"),
            false
        ));
        var notifier = new ReminderExample.RecordingNotifier();
        var service = new ReminderExample.ReminderService(
            store, notifier, fixedClock()
        );

        assertFalse(service.sendIfDue("INV-FUTURE"));
        assertTrue(notifier.deliveries().isEmpty());
        assertFalse(store.find("INV-FUTURE").orElseThrow().sent());
    }

    @Test
    void doesNotMarkSentWhenNotificationFails() {
        var store = new ReminderExample.FakeInvoiceStore();
        store.put(new ReminderExample.Invoice(
            "INV-FAIL",
            "customer@example.invalid",
            Instant.parse("2026-11-26T00:00:00Z"),
            false
        ));

        ReminderExample.Notifier failing = (recipient, body) -> {
            throw new IllegalStateException("Simulated provider failure");
        };
        var service = new ReminderExample.ReminderService(
            store, failing, fixedClock()
        );

        assertThrows(
            IllegalStateException.class,
            () -> service.sendIfDue("INV-FAIL")
        );
        assertFalse(store.find("INV-FAIL").orElseThrow().sent());
    }
}
```

**Để chạy:** đặt mã trong cấu trúc source/test của dự án và khai báo dependency JUnit Jupiter + test engine trong công cụ build đang dùng. Các phiên bản JUnit hiện hành dùng package `org.junit.jupiter.api`; bài này không đóng đinh một artifact version để tránh ép cấu hình không phù hợp với build của dự án.

**Lưu ý:** `List.getFirst()` có từ Java 21, nên hợp lệ với Java 27. Trên JDK cũ hơn cần một cách truy cập khác, nhưng phạm vi bài là Java 27.

### 10.1. Đặt tên test theo hành vi

Tên như `doesNotMarkSentWhenNotificationFails()` mô tả contract hơn `testReminderServiceMethod3()`.

Một test nên trả lời rõ:

1. **Given:** trạng thái nào được chuẩn bị?
2. **When:** thao tác nghiệp vụ nào được gọi?
3. **Then:** kết quả hoặc side effect nào phải đúng?

Không bắt buộc phải viết comment “Given/When/Then” trong mọi test; tính dễ đọc của fixture và assertion quan trọng hơn nghi thức.

## 11. Kiểm soát thời gian mà không gọi `Thread.sleep()`

Kiểm thử expiry, TTL, deadline hoặc khuyến mãi hết hạn bằng `Instant.now()` có thể thất bại khi chạy qua nửa đêm, timezone khác hoặc máy CI chậm.

Java có `Clock.fixed`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
    Instant.parse("2026-11-27T08:00:00Z"),
    ZoneOffset.UTC
);

Instant observed = clock.instant();
// observed luôn bằng 2026-11-27T08:00:00Z.
```

Có thể dùng `Clock.offset(base, duration)` để mô phỏng thời gian khác:

```java
import java.time.Duration;

Clock tomorrow = Clock.offset(clock, Duration.ofDays(1));
```

### 11.1. Test các mốc biên

Với `expiresAt`, nên thử:
- Trước hạn một nanosecond/millisecond theo độ chính xác nghiệp vụ.
- Đúng lúc đến hạn.
- Sau hạn.
- Mốc chuyển ngày theo timezone được định nghĩa.
- Trường hợp `Duration.ZERO` hoặc deadline đã qua nếu API cho phép.

**Không xem `Clock.fixed` là một scheduler.** Nó chỉ cung cấp một thời điểm cố định khi code gọi `clock.instant()`. Nó không tự đánh thức task, không tự hoàn thành `CompletableFuture`, và không thay thế timeout thực tế của network API.

### 11.2. Khi nào dùng `InstantSource`?

`java.time.InstantSource` là interface có trong JDK hiện đại và được `Clock` triển khai. Nếu một service chỉ cần **instant**, không cần timezone, có thể phụ thuộc vào `InstantSource` thay `Clock` để contract hẹp hơn.

```java
import java.time.InstantSource;

final class TimestampService {
    private final InstantSource source;

    TimestampService(InstantSource source) {
        this.source = source;
    }

    String currentInstant() {
        return source.instant().toString();
    }
}
```

Không cần xây abstraction riêng khi JDK đã có contract đáp ứng yêu cầu.

## 12. Random và ID: ranh giới kiểm soát đúng mức

Với ID nghiệp vụ:

```java
import java.util.UUID;
import java.util.function.Supplier;

final class IdService {
    private final Supplier<UUID> newId;

    IdService(Supplier<UUID> newId) {
        this.newId = newId;
    }

    String allocate() {
        return newId.get().toString();
    }
}
```

Production:

```java
IdService service = new IdService(UUID::randomUUID);
```

Test:

```java
UUID expected = UUID.fromString(
    "00000000-0000-0000-0000-000000000042"
);
IdService service = new IdService(() -> expected);

if (!service.allocate().equals(expected.toString())) {
    throw new AssertionError();
}
```

Chỉ inject randomness khi output của nó **thực sự ảnh hưởng tính xác định của test**. Với mật mã, tuyệt đối không biến test double có giá trị dự đoán được thành **nguồn sinh key/nonce trong production**. Test vector cố định hợp lệ trong phạm vi test được cô lập, nhưng không được làm suy yếu tính an toàn của runtime.

## 13. HTTP: mock ở boundary hay dùng server cục bộ?

`HttpClient` trong `java.net.http` là API JDK có nhiều hành vi: HTTP version, TLS, redirect, timeout, body subscription và lifecycle. Unit test không nên giả vờ tái triển khai toàn bộ `HttpClient`.

Một thiết kế thường dễ kiểm thử hơn:

```java
interface CatalogGateway {
    ProductInfo load(String id);
}

record ProductInfo(String id, String name) { }

final class ProductService {
    private final CatalogGateway gateway;

    ProductService(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    String title(String id) {
        return gateway.load(id).name();
    }
}
```

Unit test:

```java
CatalogGateway stub = id -> new ProductInfo(id, "Java 27");
ProductService service = new ProductService(stub);

if (!service.title("P-42").equals("Java 27")) {
    throw new AssertionError();
}
```

**Adapter `CatalogGateway` thật** sẽ chịu trách nhiệm tạo `HttpRequest`, gọi `HttpClient.send`, kiểm tra status, parse JSON và chuyển transport errors thành contract của gateway. Unit test ở tầng domain không nên quan tâm `HttpRequest.Builder` dùng option nào; phần ấy thuộc **adapter/integration tests**.

### 13.1. Khi nào dùng HTTP test server?

Nếu mục tiêu là kiểm tra **HTTP mapping** thực tế, có thể dùng một server cục bộ với cổng hệ điều hành tự cấp:

```text
Test process
    |
    | HttpClient thật
    v
Loopback HTTP server (ephemeral port)
    |
    +-- trả 200 + JSON đúng
    +-- trả 404 / 429 / 500
    +-- trả body sai định dạng
    +-- thử header / redirect / timeout có kiểm soát
```

Module JDK `jdk.httpserver` có `com.sun.net.httpserver.HttpServer`, hữu ích cho test đơn giản. Với dự án lớn có thể dùng thư viện HTTP stubbing như WireMock hoặc MockWebServer, nhưng cần kiểm soát dependency version và không thay thế integration test với API thật.

Không phụ thuộc cổng cố định `8080` hoặc Internet trong unit test thông thường; tránh đụng cổng khi test chạy song song.

### 13.2. Stub HTTP response không chứng minh parser đúng

Một stub ở `CatalogGateway` bypass cả network và JSON parsing. Vì vậy test `ProductService.title()` pass **không chứng minh** adapter xử lý được `Content-Type`, `429`, body rỗng hay schema biến đổi. Phải có test riêng cho adapter bằng HTTP server stub hoặc contract verification.

## 14. Database: fake repository khác in-memory database

Ba cách thường dùng:

| Cách | Mức độ giống production | Mục tiêu |
| --- | --- | --- |
| Fake repository bằng `Map` | Thấp với transaction/SQL semantics | Kiểm tra logic nghiệp vụ rất nhanh |
| Embedded/in-memory database | Có SQL/JDBC nhưng có thể khác engine/schema thật | Integration test nhẹ nếu tương thích |
| Database thật trong container test | Cao hơn về engine và protocol | Kiểm tra migration, constraints, query, transaction |

Một in-memory database **không phải tự động tương đương PostgreSQL, MySQL hay Oracle**. Collation, isolation, JSON, index, generated columns và SQL dialect có thể khác.

### 14.1. Testcontainers trong kiểm thử tích hợp

**Testcontainers for Java** có thể khởi chạy dịch vụ trong container dùng cho test, ví dụ database engine cùng loại với production. Test vẫn có chi phí khởi tạo và phụ thuộc runtime container, nên không nên biến **mọi unit test** thành container test.

Kiểm thử thực tế nên xác nhận:
- Schema migration chạy thành công.
- Unique constraints và khóa ngoại thực sự áp dụng.
- Transaction rollback khi exception.
- Cùng query trả dữ liệu đúng và phân trang có thứ tự xác định.
- Mapping thời gian, timezone, precision và `NULL`.
- Concurrency/optimistic locking khi logic phụ thuộc.
- Connection pool acquisition và giải phóng resource.

**Không dùng database production chung cho test.** Test fixture phải được cô lập, cleanup có kiểm soát, dùng credential cấp riêng và không tác động dữ liệu thật.

## 15. Contract test: giữ fake và adapter không bị lệch nhau

Fake có thể cho unit test pass vì nó **quá dễ dãi**. Khi đó, cần định nghĩa hành vi chung mà mọi implementation của một port phải thỏa.

Ví dụ contract cho `InvoiceStore`:

```text
1. find(id) trả empty nếu bản ghi không tồn tại.
2. Sau khi lưu fixture INV-1, find("INV-1") trả đúng dữ liệu.
3. markSent("INV-1") khiến find("INV-1").sent() là true.
4. markSent(id không tồn tại) phát lỗi theo contract đã ghi.
5. Nếu có concurrency contract, kiểm tra atomicity/isolation tương ứng.
```

Một tập contract tests có thể chạy lại với:
- `FakeInvoiceStore`.
- `JdbcInvoiceStore` trên test database thật.
- Bất kỳ implementation mới nào của cùng interface.

**Nhưng không thể giả định fake giống database chỉ vì cả hai pass bốn test đơn giản**. Contract phải bao quát những đặc điểm mà business thực sự dựa vào, nhất là transaction, error mapping và concurrency.

### 15.1. Consumer-driven contract cho dịch vụ HTTP

Với microservices, *consumer-driven contract testing* có thể xác nhận request/response mà client mong đợi được provider đáp ứng. Công cụ như Pact hỗ trợ workflow đó, nhưng điều kiện quan trọng vẫn là **xác minh contract ở provider thật hoặc môi trường provider được quản lý**.

Một fixture JSON do client tự dựng **không phải chứng cứ** provider cũng trả JSON đó. Cần sự tham gia của provider hoặc một artifact contract được thực thi đúng quy trình.

## 16. Async và virtual threads: test deterministic thay vì `sleep`

Với code bất đồng bộ, dùng `Thread.sleep(100)` rồi assert rằng callback chắc đã chạy là anti-pattern: máy CI chậm sẽ thất bại ngẫu nhiên; máy nhanh che giấu race.

Sử dụng đồng bộ hóa rõ ràng:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

CompletableFuture<String> result = new CompletableFuture<>();

// Một test double có thể hoàn tất future ngay lập tức:
result.complete("OK");

String actual = result.get(1, TimeUnit.SECONDS);
if (!actual.equals("OK")) {
    throw new AssertionError(actual);
}
```

Đối với các bước bắt buộc xảy ra theo thứ tự, `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc cơ chế quản lý task do framework cung cấp phù hợp hơn một khoảng `sleep` đoán mò.

### 16.1. Test cancellation và timeout

Một `CompletableFuture` được hoàn tất sớm giúp test nhánh thành công, nhưng không đảm bảo code xử lý đúng **request đang pending** hoặc cancellation.

Các trường hợp nên kiểm tra:

1. Dependency trả kết quả bình thường.
2. Dependency hoàn tất exceptionally.
3. Dependency không bao giờ hoàn tất, code áp dụng deadline đúng.
4. Caller cancel request, cleanup được kích hoạt.
5. Kết quả trả muộn sau timeout không tạo side effect không mong muốn.

**`orTimeout` và HTTP request timeout không phải cùng một hợp đồng.** Một future timeout không bảo đảm tác vụ I/O hoặc side effect bên ngoài đã bị hủy hoàn toàn.

### 16.2. Recording spy trong concurrency test cần thread safety

`RecordingNotifier` dùng `ArrayList` trong ví dụ đơn luồng. Nếu nhiều virtual threads cùng gọi `send`, class này **không thread-safe**.

Có thể dùng collection đồng bộ phù hợp hoặc ghi nhận qua một queue concurrent:

```java
import java.util.concurrent.ConcurrentLinkedQueue;

final class ConcurrentRecordingMailer implements Mailer {
    private final ConcurrentLinkedQueue<String> recipients =
        new ConcurrentLinkedQueue<>();

    @Override
    public void send(String recipient, String body) {
        recipients.add(recipient);
    }

    int recordedCount() {
        return recipients.size();
    }
}
```

Concurrent collection không tự làm toàn bộ test deterministic: test vẫn phải **chờ tất cả task hoàn tất** trước khi assert, và phải xác định ordering có phải requirement hay không.

## 17. Filesystem: file tạm thường tốt hơn fake filesystem

Nếu đang kiểm tra logic xử lý file thật, test có thể dùng thư mục tạm:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path dir = Files.createTempDirectory("invoice-test-");

try {
    Path file = dir.resolve("input.txt");
    Files.writeString(
        file, "hello", StandardCharsets.UTF_8
    );

    String content = Files.readString(
        file, StandardCharsets.UTF_8
    );
    if (!content.equals("hello")) {
        throw new AssertionError();
    }
} finally {
    // Phải cleanup những file test tự tạo.
    // Trong ví dụ này nên xóa file trước, sau đó xóa thư mục.
}
```

Đoạn code trên minh họa thiết lập file nhưng phần cleanup để dưới dạng comment. Trong test thật **không để lại file tạm**:

```java
Path dir = Files.createTempDirectory("invoice-test-");
Path file = dir.resolve("input.txt");

try {
    Files.writeString(file, "hello", StandardCharsets.UTF_8);
    if (!Files.readString(file, StandardCharsets.UTF_8).equals("hello")) {
        throw new AssertionError();
    }
} finally {
    Files.deleteIfExists(file);
    Files.deleteIfExists(dir);
}
```

Trong JUnit Jupiter, annotation `@TempDir` quản lý một thư mục tạm cho test và giúp tránh cleanup thủ công:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;

class FileExampleTest {
    @TempDir
    Path tempDir;

    @Test
    void writesFile() throws Exception {
        Path file = tempDir.resolve("data.txt");
        java.nio.file.Files.writeString(file, "data");
        // assert file content...
    }
}
```

Không hard-code đường dẫn người dùng, không xóa cả thư mục tùy tiện, và không dùng cùng một file test cho nhiều test chạy song song.

## 18. Quản lý setup, teardown và tài nguyên

Nếu test double mở resource hoặc test khởi chạy một dịch vụ thật, **ownership và cleanup** vẫn cần rõ ràng.

| Resource | Cleanup cần thiết |
| --- | --- |
| JDBC `Connection` / `ResultSet` | `try-with-resources` |
| HTTP client dùng ngắn hạn | `HttpClient.close()` theo vòng đời |
| HTTP test server | `stop()` khi test kết thúc |
| Executor | `shutdown`/`close` và chờ các task đúng hạn |
| Container test | Stop/cleanup theo lifecycle Testcontainers |
| Temp files | `@TempDir` hoặc xóa có kiểm soát |
| Static test doubles | Reset hoặc tránh state dùng chung |
| Environment/system properties | Restore giá trị cũ sau test |

Một test pass rồi để lại thread, port, connection hoặc file lock có thể làm **test kế tiếp thất bại**. Test isolation bao gồm cả **vòng đời resource**, không chỉ reset object state.

### 18.1. `@BeforeEach` và `@AfterEach`

JUnit Jupiter có lifecycle callbacks để chuẩn bị/cleanup theo mỗi test. Tuy nhiên, ưu tiên fixture ngắn ngay trong test nếu nó giúp dễ đọc hơn. Khi resource implement `AutoCloseable`, dùng `try-with-resources` hoặc extension phù hợp thay vì tự viết quy trình cleanup phức tạp.

### 18.2. Không đặt thứ tự test ngầm định

Đừng để test B phụ thuộc test A đã lưu một hóa đơn trong shared fake. Một test độc lập phải có thể chạy:
- Riêng lẻ.
- Theo thứ tự bất kỳ.
- Lặp lại nhiều lần.
- Song song nếu suite cho phép và fixture thiết kế an toàn.

## 19. Mocking framework: thuận tiện nhưng có giới hạn

Các framework như Mockito giúp tạo stub/mock từ interface hoặc class và cấu hình bằng API ngắn. Nhưng trong Java 27, cần thận trọng với các kỹ thuật phụ thuộc **bytecode instrumentation**, dynamic agent attachment, static/final mocking và strong encapsulation của JPMS.

Các lời khuyên thực tế:

- Ưu tiên mock ở **interface boundary** thay vì chọc vào private internals.
- Tránh mock `String`, `List`, value objects hoặc toàn bộ domain entities.
- Tránh static mocking trên diện rộng để che giấu hard-coded dependencies.
- Nếu công cụ test cần Java agent, kiểm tra tài liệu phiên bản công cụ và cấu hình test JVM; không giả định mọi JDK/vendor hỗ trợ ngầm như nhau.
- Đừng dùng `--add-opens` tràn lan để lách encapsulation; điều chỉnh module/test integration một cách có chủ đích.
- Không đặt bí mật thực vào mock arguments, snapshots hoặc assertion output.

**Không phải mọi method final đều “không test được”.** Thường code vẫn có thể test qua public API và dependency seam. Mục tiêu là test behavior, không phải phá encapsulation bằng mọi giá.

## 20. Test double có thể gây false confidence thế nào?

Một unit test chỉ nhìn stub/fake có thể pass trong khi production hỏng:

```text
Unit test
    Service -> FakeStore
    FakeStore.find("42") -> trả đúng ngay
    => PASS

Production
    Service -> SQL adapter
    Query SQL sai column name
    => FAIL
```

Hoặc:

```text
Unit test
    Stub HTTP response: {"amount": 1200}
    => PASS

Production
    Provider đổi schema, trả {"amount": "1200"}
    => parse/mapping FAIL
```

Một tầng kiểm thử khỏe nên có nhiều mức:

| Mức | Cái gì được chạy thật? | Cái gì có thể thay? |
| --- | --- | --- |
| Unit test | Logic SUT, model, validation | DB/network/time/payment |
| Component test | Nhiều service/adapter trong cùng process | Một số hệ thống ngoài |
| Integration test | Adapter + database/test HTTP server thật | Upstream bên ngoài hoặc credential production |
| Contract test | Hợp đồng consumer/provider hoặc repository | Một số môi trường thực thi |
| End-to-end test | Luồng nghiệp vụ qua nhiều thành phần | Hạn chế tối đa, vẫn phải tránh side effect thật nguy hiểm |

Không có tỷ lệ cố định bắt buộc như “90% mock, 10% real”. Chọn theo rủi ro nghiệp vụ, chi phí triển khai, thời gian suite và các chỗ fake dễ khác production.

## 21. Phân biệt flaky test với lỗi nghiệp vụ

**Flaky test** là test có thể pass hoặc fail trên cùng code/dữ liệu vì những biến không được kiểm soát.

Các nguyên nhân:

- Dùng `sleep` để chờ async event.
- Giả định thời gian hiện tại/locale/timezone.
- Port cố định hoặc file tạm dùng chung.
- Database/Redis dùng chung giữa các test.
- Test phụ thuộc thứ tự chạy.
- Network service thật không ổn định.
- Data race trong chính fake/spy.
- Hạn thời gian test quá chặt so với môi trường CI.
- Test để lại thread hoặc process sau khi kết thúc.

### 21.1. Không sửa flaky test bằng cách retry vô hạn

Retry một test thất bại có thể giúp thu thêm thông tin, nhưng không biến test đó thành deterministic. Hãy ghi lại:
- Seed/dữ liệu đầu vào.
- Thread/task IDs và thời điểm.
- Test fixture và dependency version.
- Call stack/cause.
- Logs/traces đủ mức nhưng không lộ secret.
- Cách tái hiện và điều kiện race.

Sau khi tìm nguyên nhân, điều chỉnh synchronization, ownership, test setup hoặc ranh giới dependency. Không tăng timeout vô hạn để che một deadlock.

## 22. Lựa chọn test double theo câu hỏi cần trả lời

| Câu hỏi của test | Lựa chọn ưu tiên |
| --- | --- |
| “Service có xử lý trường hợp không tìm thấy user?” | Stub trả `Optional.empty()` |
| “Sau khi thao tác, trạng thái hóa đơn có đúng?” | Fake store có state hoặc repository test DB |
| “Có gửi email đúng một lần đến đúng người?” | Recording spy hoặc mock kỳ vọng |
| “Không được charge khi validation thất bại?” | Mock/spy xác minh **không có side effect** |
| “SQL có tôn trọng unique constraint?” | DB thật trong integration test |
| “HTTP adapter xử lý 429 và timeout?” | HTTP server cục bộ/stub server |
| “JSON parser nhận schema thật?” | Payload fixtures + provider contract |
| “Nghiệp vụ đúng ở giờ biên?” | `Clock.fixed`, `Clock.offset` |
| “Hai task có race?” | Latch/barrier + fake thread-safe khi cần; integration concurrency |
| “Email provider thật có nhận request chuẩn?” | Sandbox provider hoặc integration được cấp phép |
| “Migration DB chạy trên engine production?” | Testcontainers hoặc môi trường DB tương đương |
| “UI và dịch vụ phối hợp đúng?” | End-to-end trên môi trường cô lập |

### 22.1. Thử kiểm tra output trước khi kiểm tra interactions

Nếu có thể diễn đạt yêu cầu nghiệp vụ thành **state hoặc result**, test thường bền hơn qua refactor. Xác minh interaction khi nó chính là hợp đồng, đặc biệt **side effect ra bên ngoài** hoặc yêu cầu không gửi trùng.

Một test tốt thất bại khi có **regression hành vi**, không phải bất cứ khi nào thay đổi implementation detail.

## 23. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| SUT tự `new` mọi DB/HTTP client | Khó thay thế, unit test phải chạm I/O | Constructor injection, ports/adapters |
| Dùng mock cho mọi `record`/collection | Test xác minh mock thay vì logic thực | Dùng value objects thật |
| Fake store không có unique/transaction rules mà production phụ thuộc | False positive khi kiểm thử | Contract tests + database integration |
| Để singleton fake dùng chung toàn suite | Test chạy theo thứ tự gây lẫn state | Fixture mới cho mỗi test |
| Dùng `Instant.now()` trong logic cần kiểm thử giờ biên | Nondeterminism, CI flaky | Inject `Clock` hoặc `InstantSource` |
| Dùng `Thread.sleep` để đợi async | Race, chạy nhanh/chậm khác nhau | Future/latch và deadline rõ |
| Spy dùng `ArrayList` khi bị gọi từ nhiều threads | Data race/lỗi không ổn định | Concurrent queue + await completion |
| Mock static/native/JDK internals cho mọi testcase | Coupling và phụ thuộc agent/JPMS | Thiết kế seam ở API boundary |
| Assert mọi lời gọi helper nội bộ | Test vỡ khi refactor vô hại | Verify outcome + interactions trọng yếu |
| Tin HTTP stub là provider contract | Mismatch với API thật | Contract/provider integration tests |
| Gửi email/payment thật trong unit tests | Side effect và rủi ro | Stub/spy, sandbox integrations |
| Dùng DB production/shared cho test | Làm hỏng dữ liệu hoặc test flaky | DB cô lập/container + cleanup |
| Bỏ qua retry, timeout, cancellation | Trường hợp lỗi thật chưa được kiểm | Inject failure, kiểm tra deadline/lifecycle |
| Test pass nhưng giữ executor/port/file | Test sau fail, CI treo | `try-with-resources`, teardown |
| Dùng `null` dummy mọi nơi | `NullPointerException` che lỗi khác | Dummy có contract hoặc throwing implementation |
| Tin mock đảm bảo side effect exactly-once | Mock không tái hiện retry/crash/concurrency thật | Outbox/idempotency và integration concurrency |
| Không kiểm tra lỗi `markSent` sau `send` | Có thể gửi reminder trùng khi retry | Phân tích consistency và transaction boundary |

## 24. Checklist áp dụng trong dự án Java 27

Trước khi kết luận module đã được kiểm thử tốt, hãy xác minh:

1. [ ] SUT và external dependencies có ranh giới rõ, kiểm soát được không?
2. [ ] Dùng object thật cho logic thuần và giá trị bất biến thay vì mock mọi thứ?
3. [ ] Mỗi dependency được thay bằng dummy/stub/fake/spy/mock **đúng mục tiêu**?
4. [ ] Clock, random ID và config có được inject khi ảnh hưởng kết quả test?
5. [ ] Có test các nhánh thành công, không tìm thấy dữ liệu, lỗi và giới hạn không?
6. [ ] Có test side effect “không được xảy ra” khi request không hợp lệ?
7. [ ] Fake có contract và giới hạn được tài liệu hóa không?
8. [ ] Những hành vi SQL/transaction/JSON/HTTP thực tế có integration/contract tests không?
9. [ ] Không có email/payment/network thật ngoài phạm vi test được phép?
10. [ ] Async tests có đồng bộ hóa rõ ràng, không dựa vào `sleep` tùy ý?
11. [ ] Test doubles và fixtures có an toàn nếu suite chạy parallel?
12. [ ] Có cleanup tài nguyên và tránh shared static mutable state không?
13. [ ] Test không phụ thuộc thứ tự, timezone, tài khoản người dùng hay dữ liệu bên ngoài?
14. [ ] Những assertion interaction có gắn với hợp đồng nghiệp vụ?
15. [ ] Có chạy unit tests nhanh thường xuyên và integration tests ở môi trường phù hợp?
16. [ ] Có kiểm soát secrets, logs và dữ liệu nhạy cảm trong test reports?
17. [ ] Nếu dùng Mockito/JUnit, dependency và JVM test configuration phù hợp Java 27?
18. [ ] Khi một test fail, output có đủ thông tin để tái hiện mà không cần đoán?

**Ghi nhớ:** test double **không phải mục tiêu kiểm thử**; nó là công cụ kiểm soát phần thế giới mà test không muốn phụ thuộc. Kiểm thử tốt giữ **logic thật** ở giữa, thay ranh giới ngoài một cách có chủ đích và xác nhận lại bằng contract/integration tests nơi mà một fake không thể đảm bảo giống môi trường production.

## Tài liệu tham khảo

- [Martin Fowler — Test Double](https://martinfowler.com/bliki/TestDouble.html): thuật ngữ dummy, fake, stub, spy và mock theo Gerard Meszaros.
- [Martin Fowler — Mocks Aren't Stubs](https://martinfowler.com/articles/mocksArentStubs.html): state verification và behavior verification.
- [JUnit User Guide — JUnit Jupiter](https://docs.junit.org/current/user-guide/): `@Test`, assertions, lifecycle và parameterized tests.
- [JUnit 6 — Overview](https://docs.junit.org/6.0.2/overview): mô hình Jupiter/Platform và yêu cầu Java runtime hiện hành.
- [Java SE 27 API — `Clock`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html): `Clock.fixed`, `Clock.offset` và time injection.
- [Java SE 27 API — `InstantSource`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/InstantSource.html): nguồn instant thay thế được.
- [Java SE 27 API — `CompletableFuture`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): hoàn tất futures và xử lý lỗi bất đồng bộ.
- [Java SE 27 API — `HttpClient`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP adapter thật và lifecycle.
- [Java SE 27 API — `HttpServer` (JDK)](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback HTTP server cho kiểm thử tích hợp.
- [Java SE 27 API — `Files`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): xử lý filesystem thật với thư mục test.
- [Mockito — Documentation](https://site.mockito.org/): mocking framework và verification.
- [Testcontainers for Java — Documentation](https://java.testcontainers.org/): integration tests với database/dịch vụ thật trong container.
- [Pact — Documentation](https://docs.pact.io/): consumer-driven contract testing cho dịch vụ.
