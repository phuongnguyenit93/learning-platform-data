# Giữ nghiệp vụ có thể kiểm thử và tái sử dụng ngoài container

## 1. Mục tiêu: framework hỗ trợ lắp ghép, không sở hữu quy tắc nghiệp vụ

Trong module **DEPENDENCY_INJECTION**, ta học cách sử dụng **Dependency Injection (DI)** và **Inversion of Control (IoC)** để tách *nơi sử dụng phụ thuộc* khỏi *nơi tạo, cấu hình và lắp ghép đối tượng*. Tư duy này vẫn đúng khi ứng dụng bắt đầu dùng Spring, Jakarta CDI hoặc một DI container khác.

Một DI container có thể hỗ trợ tạo object graph, giải quyết phụ thuộc theo type/qualifier và quản lý scope. Nhưng **nghiệp vụ không nhất thiết phải biết container nào đang chạy**, và cũng không nên buộc phải khởi động toàn bộ framework mới có thể kiểm thử một quy tắc tính toán hoặc một use case.

Mục tiêu thiết kế của bài là:

> **Có thể tạo lớp nghiệp vụ bằng `new` với các phụ thuộc do bên gọi cung cấp, chạy và kiểm thử bằng Java thuần; còn framework chỉ chịu trách nhiệm lắp ghép và tích hợp với môi trường thực thi.**

Ví dụ một lớp `CheckoutService` nhận `PaymentGateway` qua constructor:

~~~java
final class CheckoutService {
    private final PaymentGateway payments;

    CheckoutService(PaymentGateway payments) {
        this.payments = java.util.Objects.requireNonNull(payments);
    }
}
~~~

Đây là constructor injection dù không có annotation nào. Một ứng dụng CLI có thể dùng `new CheckoutService(fakeGateway)`; một ứng dụng web có thể để container cấp `payments`. **Hợp đồng constructor và hành vi nghiệp vụ không cần thay đổi.**

Cần phân biệt: “không phụ thuộc container” không có nghĩa “không dùng thư viện ngoài” trong mọi tình huống. Ranh giới nên được chọn theo mục tiêu tái sử dụng và chi phí duy trì. Ở bài này, ta chủ ý xây lõi bằng Java thuần để thấy rõ cơ chế trước khi đưa DI container vào.

## 2. Những dấu hiệu nghiệp vụ đang bị gắn chặt với framework

Không phải mọi việc dùng annotation đều sai. Vấn đề nằm ở chỗ **để chi tiết của container hoặc giao thức vận chuyển quyết định cấu trúc logic nghiệp vụ**.

| Dấu hiệu trong lớp nghiệp vụ | Rủi ro | Hướng thay thế |
| --- | --- | --- |
| Inject cả `ApplicationContext` rồi gọi `getBean()` | Phụ thuộc thật bị ẩn, lỗi chọn bean xuất hiện muộn | Khai báo dependency qua constructor; tiêm factory chuyên biệt nếu cần |
| Lớp nghiệp vụ gọi `new HttpClient(...)`, mở DB hoặc đọc biến môi trường | Trộn quy tắc nghiệp vụ với tạo hạ tầng, khó dùng fake | Composition root hoặc adapter chịu trách nhiệm tạo client |
| Phương thức nghiệp vụ nhận `HttpServletRequest` hay trả `ResponseEntity` | Khó tái sử dụng trong CLI, batch, message consumer | Controller chuyển đổi HTTP thành lệnh/dữ liệu của use case |
| Core import `@Autowired` hoặc API container chỉ để nhận dependency | Unit test và module core bị phụ thuộc framework không cần thiết | Constructor Java thuần, container gọi constructor qua cấu hình |
| Domain dùng trực tiếp bean repository cụ thể có API riêng của ORM | Dính chi tiết persistence, khó test và thay adapter | Port theo nhu cầu của bên sử dụng và adapter làm ánh xạ |
| Dùng `@Value` trong domain để lấy chính sách cấu hình | Khó nhìn giá trị đầu vào và khó tạo đối tượng trong test | Tiêm một value object cấu hình đã kiểm tra |
| Test quy tắc đơn giản luôn khởi động toàn bộ application context | Chậm, nhiều điều kiện môi trường và khó chẩn đoán lỗi | Unit test trực tiếp lớp nghiệp vụ; test container ở lớp tích hợp |

Một service có thể được quản lý bởi container mà vẫn **không import framework**. Container sẽ tạo nó bằng constructor, tương tự code trong `main()`. Chỉ những lớp thực sự làm nhiệm vụ giao tiếp HTTP, persistence, messaging hoặc lifecycle framework mới cần biết các API tương ứng.

### Phân biệt IoC và Dependency Inversion Principle

- **IoC** là việc chuyển quyền điều khiển/lắp ghép ra khỏi lớp đang sử dụng.
- **DI** là một kỹ thuật thực hiện sự tách biệt đó bằng cách cung cấp phụ thuộc từ bên ngoài.
- **Dependency Inversion Principle (DIP)** hướng các chính sách cấp cao tránh phụ thuộc trực tiếp vào chi tiết cấp thấp; hợp đồng phù hợp được đặt ở ranh giới cần ổn định.

Có DI container **không tự động bảo đảm DIP**. Nếu `CheckoutService` nhận trực tiếp một repository HTTP hoặc object JPA được định nghĩa trong module hạ tầng, nó vẫn có thể bị ràng buộc vào chi tiết. Ngược lại, một formatter thuần túy, ổn định, cùng module có thể được tiêm bằng lớp cụ thể mà không cần interface chỉ để “đúng DI”.

## 3. Chia trách nhiệm: core, ports, adapters và composition root

Một cấu trúc dễ kiểm soát gồm bốn vai trò:

1. **Nghiệp vụ (core/use case):** quy tắc hợp lệ, điều kiện bất biến, thứ tự các bước nghiệp vụ, ý nghĩa kết quả.
2. **Hợp đồng phụ thuộc (ports):** những khả năng core cần ở bên ngoài, ví dụ `PaymentGateway.charge` hoặc `ReceiptJournal.save`.
3. **Adapter:** hiện thực port bằng API cụ thể như HTTP, JDBC, ORM, queue, file hoặc bộ nhớ.
4. **Composition root:** nơi chọn adapter, tạo/configure instance, gắn lifecycle và đưa chúng vào constructor của core.

~~~mermaid
flowchart TB
    App["Application startup / DI container"]
    HTTP["HTTP Controller (adapter đầu vào)"]
    CLI["CLI command (adapter đầu vào)"]
    Core["CheckoutService (core)"]
    Port1["PaymentGateway (port)"]
    Port2["ReceiptJournal (port)"]
    HTTPGateway["HTTP payment adapter"]
    DbJournal["Database receipt adapter"]
    App -->|"lắp ghép"| Core
    App -->|"tạo"| HTTPGateway
    App -->|"tạo"| DbJournal
    HTTP -->|"gọi use case"| Core
    CLI -->|"gọi cùng use case"| Core
    Core -->|"phụ thuộc"| Port1
    Core -->|"phụ thuộc"| Port2
    HTTPGateway -.->|"implements"| Port1
    DbJournal -.->|"implements"| Port2
~~~

Theo hướng phụ thuộc **ở cấp mã nguồn**, core biết port, adapter biết port để hiện thực. Core không cần import adapter HTTP, database hoặc lớp cấu hình bean.

Sơ đồ không có nghĩa mỗi dự án phải tạo đủ bốn module vật lý hoặc một interface cho mọi class. Với ứng dụng nhỏ, những vai trò có thể nằm trong cùng module nhưng vẫn được phân biệt về **trách nhiệm và phụ thuộc**. Tách thành module vật lý sẽ hữu ích khi cần kiểm soát việc import framework vào lõi bằng build hoặc quy ước kiến trúc.

### Ai nên sở hữu port?

Nếu `CheckoutService` chỉ cần “thu tiền theo mã đơn và số tiền”, port nên diễn đạt đúng nhu cầu đó. Không nên buộc core nhận một client thư viện ngoài với hàng chục phương thức cấu hình, retry, tracing mà use case không sử dụng.

~~~java
interface PaymentGateway {
    void charge(String orderId, long amountVnd);
}
~~~

Một adapter có thể chuyển lời gọi thành request API cụ thể. Khi thay đổi nhà cung cấp thanh toán, core không phải biết DTO, header, token hay response code của nhà cung cấp mới.

## 4. Ví dụ Java thuần đầy đủ: cùng một use case chạy ngoài container

Ví dụ xây dựng chức năng thanh toán và lưu dấu vết biên nhận với các đặc điểm:

- `CheckoutService` nhận hai port và `Clock` qua constructor injection.
- Cấu hình số tiền tối thiểu/tối đa được kiểm tra ngay khi tạo service.
- Dữ liệu của từng thao tác được kiểm tra tại phương thức `checkout`.
- Adapter console và in-memory dùng cho chương trình nhỏ; về sau có thể đổi sang adapter thật mà không đổi core.
- Không sử dụng annotation Spring, CDI, hoặc mock framework.

Lưu toàn bộ thành **`FrameworkFreeCheckoutDemo.java`** (Java 11 trở lên):

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class FrameworkFreeCheckoutDemo {

    // Ports theo nhu cầu nghiệp vụ.
    public interface PaymentGateway {
        void charge(String orderId, long amountVnd);
    }

    public interface ReceiptJournal {
        void save(Receipt receipt);
    }

    // Kết quả nghiệp vụ, không phải HTTP response hay entity của ORM.
    public static final class Receipt {
        private final String orderId;
        private final long amountVnd;
        private final Instant createdAt;

        public Receipt(String orderId, long amountVnd, Instant createdAt) {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (amountVnd <= 0) {
                throw new IllegalArgumentException("amountVnd phải dương");
            }
            this.orderId = orderId;
            this.amountVnd = amountVnd;
            this.createdAt = Objects.requireNonNull(
                    createdAt, "createdAt");
        }

        public String orderId() {
            return orderId;
        }

        public long amountVnd() {
            return amountVnd;
        }

        public Instant createdAt() {
            return createdAt;
        }
    }

    // Use case thuần Java; không biết container, HTTP hoặc database.
    public static final class CheckoutService {
        private final PaymentGateway gateway;
        private final ReceiptJournal journal;
        private final Clock clock;
        private final long minAmountVnd;
        private final long maxAmountVnd;

        public CheckoutService(
                PaymentGateway gateway,
                ReceiptJournal journal,
                Clock clock,
                long minAmountVnd,
                long maxAmountVnd) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
            this.journal = Objects.requireNonNull(journal, "journal");
            this.clock = Objects.requireNonNull(clock, "clock");

            if (minAmountVnd <= 0 || maxAmountVnd < minAmountVnd) {
                throw new IllegalArgumentException("Hạn mức không hợp lệ");
            }

            this.minAmountVnd = minAmountVnd;
            this.maxAmountVnd = maxAmountVnd;
        }

        public Receipt checkout(String orderId, long amountVnd) {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (amountVnd < minAmountVnd || amountVnd > maxAmountVnd) {
                throw new IllegalArgumentException("Số tiền ngoài hạn mức");
            }

            // Đọc thời gian qua dependency để kết quả dễ kiểm thử.
            Receipt receipt = new Receipt(orderId, amountVnd, clock.instant());

            gateway.charge(orderId, amountVnd);
            journal.save(receipt);

            return receipt;
        }
    }

    // Adapter đơn giản cho CLI/demo.
    public static final class ConsolePaymentGateway
            implements PaymentGateway {
        @Override
        public void charge(String orderId, long amountVnd) {
            System.out.println("CHARGE " + orderId + ": " + amountVnd);
        }
    }

    public static final class InMemoryReceiptJournal
            implements ReceiptJournal {
        private final List<Receipt> receipts = new ArrayList<>();

        @Override
        public void save(Receipt receipt) {
            receipts.add(Objects.requireNonNull(receipt, "receipt"));
        }

        public List<Receipt> snapshot() {
            return List.copyOf(receipts);
        }
    }

    public static void main(String[] args) {
        // Composition root thủ công: nơi quyết định hiện thực, scope và config.
        PaymentGateway payments = new ConsolePaymentGateway();
        InMemoryReceiptJournal journal = new InMemoryReceiptJournal();
        Clock clock = Clock.systemUTC();

        CheckoutService checkout =
                new CheckoutService(payments, journal, clock, 1_000, 5_000_000);

        Receipt receipt = checkout.checkout("ORDER-001", 150_000);
        System.out.println("RECEIPT " + receipt.orderId()
                + ": " + receipt.amountVnd() + " VND");
        System.out.println("JOURNAL SIZE " + journal.snapshot().size());
    }
}
~~~

Chạy:

~~~bash
javac FrameworkFreeCheckoutDemo.java
java FrameworkFreeCheckoutDemo
~~~

Đầu ra có dạng:

~~~text
CHARGE ORDER-001: 150000
RECEIPT ORDER-001: 150000 VND
JOURNAL SIZE 1
~~~

**Lõi không biết container:** `CheckoutService` chỉ cần `PaymentGateway`, `ReceiptJournal`, `Clock` và hạn mức. `main()` có thể thay `ConsolePaymentGateway` bằng một adapter khác hoặc cho container thực hiện việc tạo graph.

**Lõi không biết transport:** không có `HttpServletRequest` hay `ResponseEntity`. CLI, HTTP controller và message consumer đều có thể gọi cùng phương thức `checkout(...)` nếu dùng đúng dữ liệu nghiệp vụ.

**Lõi không biết persistence:** `Receipt` là đối tượng kết quả Java thuần. Khi dùng JPA hoặc JDBC, adapter phía ngoài có thể ánh xạ `Receipt` sang bảng dữ liệu hoặc entity tương ứng.

**Lõi vẫn có quy tắc nghiệp vụ:** việc kiểm tra hạn mức, mã đơn và trình tự gọi hai port vẫn nằm trong `CheckoutService`. “Không phụ thuộc framework” không có nghĩa đẩy hết logic vào controller hay composition root.

### Lưu ý quan trọng về giao dịch và tác dụng phụ

Ví dụ thực hiện `gateway.charge(...)` rồi mới `journal.save(...)`. Nếu thanh toán thành công nhưng lưu journal thất bại, **không có transaction nguyên tử giữa hai hệ thống**. DI, constructor injection và việc dùng một bean transaction manager đều không tự tạo tính nguyên tử cho lời gọi mạng bên ngoài.

Ứng dụng thật cần chọn chính sách nhất quán phù hợp: idempotency key, trạng thái thanh toán, retry có kiểm soát, outbox, saga hoặc bù trừ khi thích hợp. Bài này tập trung vào **ranh giới phụ thuộc và khả năng kiểm thử**, không mô tả một hệ thống thanh toán production hoàn chỉnh.

## 5. Unit test không khởi động Spring hay bất kỳ container nào

Để chứng minh core có thể kiểm thử độc lập, ta dựng `CheckoutService` trực tiếp bằng constructor, cấp fake để quan sát tác dụng phụ và dùng `Clock.fixed` để kiểm soát thời gian.

Tạo **`FrameworkFreeCheckoutDemoTest.java`** cạnh file ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class FrameworkFreeCheckoutDemoTest {

    static final class RecordingGateway
            implements FrameworkFreeCheckoutDemo.PaymentGateway {
        int calls;
        String lastOrderId;
        long lastAmountVnd;
        boolean fail;

        @Override
        public void charge(String orderId, long amountVnd) {
            calls++;
            lastOrderId = orderId;
            lastAmountVnd = amountVnd;
            if (fail) {
                throw new IllegalStateException("Thanh toán thất bại");
            }
        }
    }

    static final class RecordingJournal
            implements FrameworkFreeCheckoutDemo.ReceiptJournal {
        final List<FrameworkFreeCheckoutDemo.Receipt> saved =
                new ArrayList<>();

        @Override
        public void save(FrameworkFreeCheckoutDemo.Receipt receipt) {
            saved.add(receipt);
        }
    }

    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    static void expect(
            Class<? extends RuntimeException> type,
            Runnable action) {
        try {
            action.run();
        } catch (RuntimeException failure) {
            if (type.isInstance(failure)) {
                return;
            }
            throw new AssertionError("Sai loại ngoại lệ", failure);
        }
        throw new AssertionError("Thiếu ngoại lệ: " + type.getSimpleName());
    }

    public static void main(String[] args) {
        RecordingGateway gateway = new RecordingGateway();
        RecordingJournal journal = new RecordingJournal();

        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);

        FrameworkFreeCheckoutDemo.CheckoutService checkout =
                new FrameworkFreeCheckoutDemo.CheckoutService(
                        gateway, journal, fixed, 1_000, 1_000_000);

        FrameworkFreeCheckoutDemo.Receipt receipt =
                checkout.checkout("ORDER-100", 150_000);

        check(gateway.calls == 1, "Phải thu tiền đúng một lần");
        check("ORDER-100".equals(gateway.lastOrderId), "Sai mã đơn");
        check(gateway.lastAmountVnd == 150_000, "Sai số tiền");
        check(journal.saved.size() == 1, "Phải lưu một biên nhận");
        check(journal.saved.get(0) == receipt, "Phải lưu kết quả trả về");
        check(receipt.createdAt().equals(
                Instant.parse("2026-01-01T00:00:00Z")),
                "Thời gian phải lấy từ clock được tiêm");

        expect(IllegalArgumentException.class,
                () -> checkout.checkout("bad id", 100_000));
        expect(IllegalArgumentException.class,
                () -> checkout.checkout("ORDER-101", 500));
        check(gateway.calls == 1, "Dữ liệu sai không được gọi gateway");
        check(journal.saved.size() == 1, "Dữ liệu sai không được ghi");

        gateway.fail = true;
        expect(IllegalStateException.class,
                () -> checkout.checkout("ORDER-102", 200_000));
        check(gateway.calls == 2, "Lần lỗi vẫn thử gọi gateway");
        check(journal.saved.size() == 1,
                "Thanh toán thất bại không được ghi biên nhận");

        expect(NullPointerException.class,
                () -> new FrameworkFreeCheckoutDemo.CheckoutService(
                        null, journal, fixed, 1_000, 1_000_000));

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac FrameworkFreeCheckoutDemo.java FrameworkFreeCheckoutDemoTest.java
java FrameworkFreeCheckoutDemoTest
~~~

Bài kiểm thử thực hiện được mà không cần context, profile, annotation, database hay mạng. Nó kiểm tra cả kết quả nghiệp vụ, điều kiện đầu vào, số lần gọi port và đường lỗi khi adapter từ chối thanh toán.

Các test này **không chứng minh adapter HTTP hoặc JDBC thật hoạt động đúng**. Chúng chứng minh phần core có hành vi dự kiến với các hợp đồng đã công bố. Những hợp đồng đó cần được kiểm tra ở các tầng test khác để tránh fake và adapter thật hiểu khác nhau.

## 6. Đưa cùng core vào Spring mà không sửa code nghiệp vụ

Một DI container như Spring có thể tạo cùng object graph đã được lắp bằng `main()`. Nếu áp dụng Spring vào ứng dụng, hãy đặt cấu hình lắp ghép tại **phần ứng dụng/tích hợp** và giữ các kiểu core không import framework.

Ví dụ cấu hình dưới đây là **mã minh họa Spring**, cần dependency và một application context Spring tương ứng; **không thuộc hai tệp Java thuần** đã chạy ở phần trước.

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CheckoutWiring {

    @Bean
    FrameworkFreeCheckoutDemo.PaymentGateway paymentGateway() {
        // Trong production có thể là HTTP adapter được cấu hình.
        return new FrameworkFreeCheckoutDemo.ConsolePaymentGateway();
    }

    @Bean
    FrameworkFreeCheckoutDemo.ReceiptJournal receiptJournal() {
        // Trong production có thể là JDBC/JPA adapter.
        return new FrameworkFreeCheckoutDemo.InMemoryReceiptJournal();
    }

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    FrameworkFreeCheckoutDemo.CheckoutService checkoutService(
            FrameworkFreeCheckoutDemo.PaymentGateway gateway,
            FrameworkFreeCheckoutDemo.ReceiptJournal journal,
            Clock applicationClock) {
        return new FrameworkFreeCheckoutDemo.CheckoutService(
                gateway, journal, applicationClock, 1_000, 5_000_000);
    }
}
~~~

Tại đây, `CheckoutWiring` là một dạng **composition root được thể hiện bằng cấu hình bean**. Spring gọi factory method để tạo bean và kết nối chúng theo các tham số. `CheckoutService` không thay đổi một dòng mã nào.

Trong hệ thống thực, thay adapter demo bằng adapter production; giữ phần tạo HTTP client, cấu hình credentials, kết nối DB và giới hạn tài nguyên tại phía tích hợp. Khi có nhiều bean cùng type, cần cấu hình lựa chọn rõ ràng bằng qualifier hoặc cách giải quyết ứng viên phù hợp với framework. Đừng dựa vào tên biến tình cờ để quyết định một quy tắc nghiệp vụ quan trọng.

**Lưu ý vòng đời:** Spring có thể quản lý callback khởi tạo/hủy của bean do context sở hữu, nhưng việc tạo bean thành công **không có nghĩa** tài nguyên ngoài luôn hoạt động, và cũng không tự tạo transaction xuyên qua nhiều hệ thống. Cần xác định rõ scope, owner, shutdown và health/readiness theo ứng dụng.

### Còn controller thì sao?

Một lớp controller phụ thuộc Spring là chuyện bình thường, vì trách nhiệm của nó chính là **điểm vào HTTP**. Nó nhận dữ liệu transport, thực hiện những kiểm tra ranh giới phù hợp, trích xuất danh tính đã xác thực từ cơ chế tin cậy, chuyển đổi dữ liệu sang đối số use case và ánh xạ kết quả/lỗi thành HTTP response.

~~~java
// Phác họa ranh giới, không phải chương trình độc lập.
final class CheckoutHttpController {
    private final FrameworkFreeCheckoutDemo.CheckoutService checkout;

    CheckoutHttpController(
            FrameworkFreeCheckoutDemo.CheckoutService checkout) {
        this.checkout = checkout;
    }

    ReceiptResponse handle(CheckoutRequest request) {
        FrameworkFreeCheckoutDemo.Receipt result =
                checkout.checkout(request.orderId(), request.amountVnd());
        return ReceiptResponse.from(result);
    }
}
~~~

Các kiểu `CheckoutRequest` và `ReceiptResponse` ở đoạn phác họa là DTO thuộc adapter HTTP, cần định nghĩa trong dự án thực. Mục tiêu của ví dụ là **hướng chuyển đổi**: controller biết use case, còn use case không biết controller.

Cùng một `CheckoutService` có thể được dùng ở command-line, consumer xử lý message hoặc job chạy theo lịch bằng cách thay **adapter đầu vào**, không phải sao chép quy tắc nghiệp vụ vào từng entry point.

## 7. Nên đặt annotation và metadata của framework ở đâu?

Không cần cấm tuyệt đối mọi annotation trong lõi. Nhưng nếu mục tiêu là tái sử dụng ngoài container, hãy đánh giá mỗi phụ thuộc vào framework: **nó phục vụ quy tắc nghiệp vụ hay chỉ phục vụ cách chạy ứng dụng?**

| Thành phần | Có nên biết framework? | Vì sao |
| --- | --- | --- |
| Domain value object, tính toán, policy | Thường không | Có thể tạo và chạy bằng Java thuần |
| Application use case/service | Tốt nhất tránh phụ thuộc DI container | API constructor rõ, dễ test và dùng lại |
| Adapter JPA/JDBC/HTTP/messaging | Có, khi cần | Chức năng của nó là tích hợp với môi trường ngoài |
| REST controller | Có, khi cần | Chịu trách nhiệm giao thức HTTP và chuyển đổi DTO |
| Bean configuration/composition root | Có | Chịu trách nhiệm đăng ký, chọn bean, scope và lifecycle |
| Validation của HTTP DTO | Có thể dùng validation framework | Đầu vào transport cần ràng buộc và thông báo lỗi riêng |
| Invariant miền nghiệp vụ | Phải tồn tại trong core | Không được chỉ dựa vào annotation ở controller |

Ví dụ, `@NotBlank` ở một HTTP DTO có thể giúp phát hiện request sai định dạng, nhưng **không thay thế** kiểm tra invariant nếu cùng use case còn được gọi từ CLI hoặc message consumer. Nếu loại bỏ adapter HTTP, core vẫn phải từ chối những đầu vào vi phạm quy tắc của nó.

Tương tự, `@Transactional` có thể là cơ chế rất hữu ích cho một tác vụ ghi database khi được đặt ở **ranh giới transaction thích hợp**. Nhưng khi use case cũng gọi gateway bên ngoài, cần thiết kế consistency trên nhiều hệ thống; annotation transaction ở một class không tự biến hai tác dụng phụ thành một giao dịch nguyên tử.

### Khi core thật sự cần một khả năng do framework cung cấp

Đôi khi một use case cần gửi sự kiện, quản lý đơn vị công việc hoặc chạy chính sách retry. Hãy hỏi nó cần **khả năng** gì trước khi cho phép nó biết API framework.

Ví dụ, thay vì để core trực tiếp gọi event bus của framework, có thể cung cấp một port `OrderEventPublisher` nếu đó là ranh giới đáng bảo vệ. Adapter sẽ quyết định dùng Kafka, message broker, event bus trong bộ nhớ hay cơ chế khác.

Không nên tạo interface cho từng lời gọi `String`, `List` hoặc mỗi helper thuần túy. Chỉ thêm abstraction khi có một **điểm biến động/ranh giới trách nhiệm** thực sự.

## 8. Test theo các tầng: mỗi tầng trả lời câu hỏi khác nhau

Giữ core độc lập không có nghĩa bỏ integration test. Một chiến lược kiểm thử tốt xác định rõ **điều gì phải được bảo đảm ở mỗi tầng**:

| Tầng kiểm thử | Cách thực hiện | Điều được xác minh |
| --- | --- | --- |
| **Unit test core** | `new CheckoutService(fakeGateway, fakeJournal, fixedClock, ...)` | Quy tắc, thứ tự lời gọi, trường hợp lỗi, bất biến |
| **Contract test port/adapter** | Cùng bộ tình huống đối với fake và adapter thật khi khả thi | Adapter hiểu đúng hợp đồng, dữ liệu/ngoại lệ tương thích |
| **Integration test adapter** | Gọi HTTP sandbox, test database hoặc môi trường tích hợp cô lập | Mapping DTO, persistence, giao thức, cấu hình và kết nối |
| **DI wiring/context test** | Khởi động container với cấu hình đại diện | Bean đủ, qualifier đúng, graph dựng được, scope/hook hợp lệ |
| **End-to-end test** | Đi qua adapter đầu vào và hệ thống liên quan | Hành vi của luồng ứng dụng ở mức người dùng hoặc tác vụ |

Nếu tất cả test đều khởi động Spring context, lỗi nghiệp vụ nhỏ có thể bị che bởi cấu hình profile, database hoặc điều kiện mạng. Ngược lại, nếu **chỉ có** unit test dùng fake, một adapter production bị ánh xạ sai hoặc bean thiếu binding vẫn có thể làm ứng dụng hỏng.

Đề xuất thực hành là **nhiều unit test nhanh và độc lập, ít nhưng đủ integration/wiring test có mục đích**, cùng các test hệ thống cho hành vi quan trọng. Số lượng cụ thể phụ thuộc rủi ro và quy mô dự án; không cần một tỷ lệ cố định.

### Kiểm thử một lỗi wiring không phải kiểm thử nghiệp vụ

Ví dụ, `CheckoutService` hoạt động với fake không bảo đảm `PaymentGateway` production đã được container đăng ký. Một test context riêng nên xác nhận ứng dụng có đúng adapter cho môi trường đích, không có hai bean không phân biệt được, không giữ sai request scope, và có callback đóng tài nguyên. Đó là trách nhiệm của **bản lắp ghép**, không nên ép unit test core gánh.

## 9. Tái sử dụng ở CLI, batch và worker mà không tạo lại nghiệp vụ

Một kiến trúc tách core khỏi container cho phép tái sử dụng cùng class trong nhiều hình thức thực thi:

~~~mermaid
flowchart LR
    CLI["CLI composition root"] --> Core["CheckoutService"]
    Spring["Spring web application wiring"] --> Core
    Worker["Worker composition root"] --> Core
    Core --> Payments["PaymentGateway port"]
    Core --> Journal["ReceiptJournal port"]
    Sandbox["SandboxGateway"] -.-> Payments
    Http["HTTP Gateway adapter"] -.-> Payments
    Memory["InMemoryJournal"] -.-> Journal
    Database["DatabaseJournal"] -.-> Journal
~~~

Điều được tái sử dụng là **quy tắc và API use case**. Mỗi ứng dụng có thể tạo một object graph khác nhau:

- **CLI:** tạo adapter cục bộ, gọi use case một lần rồi kết thúc.
- **Web:** container tạo và chia sẻ các bean cần thiết, controller gọi use case khi có request.
- **Worker:** composition root riêng tạo các adapter phù hợp cho queue, transaction và job.

Không nhất thiết cả ba entry point phải sử dụng **cùng instance**, cùng config hoặc cùng scope. Việc dùng lại mã không đồng nghĩa dùng lại tài nguyên vật lý hay quyền truy cập; mỗi môi trường phải cấu hình xác thực, phân quyền, timeout và ownership theo nhu cầu của nó.

Một thư viện core độc lập giúp nhiều ứng dụng dùng chung quy tắc, nhưng cần giữ API ổn định, xử lý lỗi rõ ràng và tránh để đối tượng vận chuyển của từng framework rò rỉ vào hợp đồng public.

## 10. Những ranh giới đặc biệt: scope, transaction, thời gian và tác vụ nền

### 10.1. Scope và captive dependency

Một `CheckoutService` dùng chung có thể giữ `PaymentGateway` và `ReceiptJournal` dùng chung nếu chúng hỗ trợ việc đó. Nhưng nó **không nên giữ trực tiếp request context, session hoặc transaction chỉ sống trong một yêu cầu**, dù container cho phép tiêm tham chiếu nào đó qua cơ chế đặc biệt.

Trong Java thuần, có thể truyền dữ liệu request hợp lệ qua tham số phương thức hoặc tạo một use case request-scoped bằng factory. Trong container, scoped proxy/provider có thể giúp resolve đối tượng trong scope hiện hành, nhưng **không kéo dài thời gian sống của request**.

### 10.2. Transaction và consistency

Một use case cần transaction database có thể được thực thi bên trong một wrapper/orchestrator tại phía ứng dụng tích hợp, hoặc dùng một abstraction đơn vị công việc nếu có lợi ích kiến trúc thật. Điều quan trọng là **chọn đúng phạm vi transaction và tránh gọi tác dụng phụ ngoài hệ quản trị như thể chúng cùng một transaction**.

Không phải cứ chuyển `@Transactional` ra khỏi core là hệ thống tự đúng; phải đảm bảo cơ chế transaction thực sự bao trùm những truy cập dữ liệu cần bao trùm. Nếu dùng proxy-based transaction framework, việc gọi qua proxy, method visibility và quy tắc framework cũng ảnh hưởng đến hiệu lực của annotation.

### 10.3. Thời gian, ngẫu nhiên và cấu hình

Tránh gọi `Instant.now()` hoặc đọc biến môi trường rải rác trong logic cần kiểm thử tất định. Tiêm `Clock` hoặc value object cấu hình qua constructor giúp test cố định thời gian và thay chính sách mà không cần thay môi trường toàn tiến trình.

Không nhất thiết phải tạo interface tự chế thay cho mọi API JDK. `Clock` là một abstract class do Java cung cấp, đã đủ làm seam cho nhiều bài toán thời gian.

### 10.4. Async và request context

Khi việc xử lý được đẩy sang executor/queue, đừng giữ lại `HttpServletRequest` hay request-scoped object trong lambda chạy sau khi HTTP request kết thúc. Hãy chuyển thành **command/job data phù hợp và có vòng đời độc lập**, đồng thời áp dụng kiểm tra quyền và chính sách bảo vệ dữ liệu khi thực thi.

Một DI container có thể quản lý bean của worker nhưng không tự đảm bảo context của HTTP request tồn tại ở một thread khác, hoặc đảm bảo retry/idempotency đúng nghiệp vụ.

## 11. Checklist review: core có thực sự độc lập với container không?

Khi xem một lớp use case, thử trả lời những câu sau:

1. Tôi có thể tạo lớp bằng `new` với các dependency cần thiết mà không cần `ApplicationContext` không?
2. Constructor có nêu rõ dependency bắt buộc, các tham số cấu hình và invariant không?
3. Core có import `HttpServletRequest`, `ResponseEntity`, client SDK, entity của ORM hoặc API container chỉ để chạy nghiệp vụ không?
4. Port có mô tả khả năng bên sử dụng cần, thay vì sao chép toàn bộ API của adapter ngoài không?
5. Tôi có thể thay adapter thật bằng fake và cố định thời gian trong unit test không?
6. Những thông tin chỉ có ở request/job có được truyền và sử dụng trong đúng scope không?
7. Ai tạo, dùng và đóng pool, connection, file hoặc client dùng chung?
8. Logic xác thực và dữ liệu nhạy cảm có được xử lý tại ranh giới tin cậy, không dựa vào tên bean/qualifier không?
9. Khi thay Spring bằng một entry point CLI, phần mã nào phải thay: **wiring/adapter** hay cả thuật toán nghiệp vụ?
10. Có một test lắp ghép kiểm tra cấu hình bean quan trọng và lifecycle, ngoài unit test core hay chưa?

Nếu phần lớn câu trả lời cho thấy **chỉ adapter và composition root phụ thuộc framework**, kiến trúc đang có cơ sở tốt cho kiểm thử nhanh và tái sử dụng.

### Những sai lầm cần tránh

| Cách làm | Vì sao gây vấn đề | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| Core tự gọi `context.getBean(...)` | Ẩn dependency, làm core phụ thuộc container | Constructor injection hoặc factory chuyên biệt |
| Đưa hết nghiệp vụ vào controller | Không tái sử dụng ở CLI/worker; test HTTP phải gánh logic | Controller mỏng, use case rõ |
| Chuyển mọi thứ sang interface | Phức tạp không cần thiết cho helper/value object ổn định | Abstraction ở ranh giới biến động thực |
| Chỉ kiểm tra HTTP DTO mà không bảo vệ invariant core | Entry point khác có thể tạo trạng thái sai | Validate ranh giới và bảo vệ invariant tại core |
| Dùng bean singleton giữ dữ liệu request trong field | Sai scope, lẫn dữ liệu giữa request | Method injection, request factory hoặc scoped provider đúng |
| Test tất cả bằng `@SpringBootTest` | Chậm và dễ phụ thuộc môi trường | Unit test trực tiếp + integration test có mục đích |
| Chỉ test bằng fake, không test adapter/wiring | Không thấy lỗi mapping, thiếu bean và vấn đề lifecycle | Test port contract, adapter và context |
| Dùng `@Transactional` để “bảo đảm” cả thanh toán mạng và DB | Transaction DB không bao trùm hệ ngoài | Thiết kế consistency, retry/idempotency phù hợp |
| Service tự đóng dependency dùng chung | Các consumer khác có thể dùng resource đã đóng | Composition root/lifecycle manager sở hữu resource |
| Đẩy mọi lựa chọn adapter vào domain | Core biết môi trường, vendor, profile | Chọn adapter tại wiring, truyền hợp đồng vào core |

## 12. Bài tập thực hành

**Bài 1 — Tách framework khỏi use case.** Một `InvoiceService` đang nhận `HttpServletRequest`, gọi `getBean("invoiceRepository")`, sau đó trả `ResponseEntity`. Hãy thiết kế lại constructor, input/output của use case, một port repository và controller chuyển đổi HTTP. Giải thích lớp nào được phép import framework.

**Bài 2 — Test không có container.** Dùng `FrameworkFreeCheckoutDemo`, bổ sung một `DiscountPolicy` thuần Java vào constructor. Tạo fake gateway/journal và `Clock.fixed` để kiểm tra tổng tiền sau giảm giá, đầu vào không hợp lệ và đúng số lần gọi các port.

**Bài 3 — Thay adapter.** Viết `LoggingPaymentGateway` hoặc `SandboxPaymentGateway` khác. Giữ nguyên `CheckoutService` và thay chỉ một dòng cấu hình tại composition root. Sau đó phác họa một `@Bean` tương ứng ở lớp Spring wiring.

**Bài 4 — Tái sử dụng trong hai entry point.** Thiết kế một CLI command và một HTTP controller cùng gọi `CheckoutService`. So sánh loại input, nơi lấy danh tính đáng tin cậy, cách chuyển lỗi sang exit code/HTTP response và những quy tắc nghiệp vụ chung.

**Bài 5 — Scope và vòng đời.** Cho một bean dùng chung giữ `RequestContext` thật trong field. Hãy viết test hai request khác nhau làm lộ lỗi, sửa bằng tham số phương thức hoặc factory theo request và chỉ ra trách nhiệm đóng resource.

**Bài 6 — Phân ranh giới kiểm thử.** Lập bảng test cho một adapter lưu receipt bằng JDBC: những gì unit test của core có thể xác minh; những gì cần test với database; và những gì chỉ có test khởi động Spring context mới phát hiện.

**Bài 7 — Xử lý nhất quán nghiệp vụ.** Nếu `gateway.charge` thành công nhưng `journal.save` lỗi, hãy mô tả trạng thái thực tế có thể xảy ra. Đề xuất một cơ chế khôi phục có tính idempotent và giải thích vì sao DI container không phải cơ chế transaction xuyên hệ thống.

Điểm cốt lõi: **framework có thể tạo và quản lý object graph, nhưng hành vi nghiệp vụ nên được mô tả bằng các hợp đồng Java rõ ràng**. Khi giữ controller/adapter ở rìa, lắp ghép tại composition root, quản lý scope/vòng đời có chủ đích và kiểm thử core trực tiếp, bạn có thể chuyển từ DI thủ công sang DI container mà không đánh mất khả năng kiểm thử và tái sử dụng ở môi trường khác.
