# Nhận diện nơi gọi new, biến static và truy cập toàn cục gây khó kiểm thử

## 1. Vấn đề không phải từ khóa `new`, mà là phụ thuộc bị giấu

Khi một lớp nghiệp vụ **tự tạo hoặc tự tìm phụ thuộc bên ngoài**, constructor không cho thấy đầy đủ điều kiện cần để lớp hoạt động. Muốn kiểm thử một hành vi đơn giản, người viết test đôi khi phải mở file, chuẩn bị database, thay biến môi trường, chờ đồng hồ hệ thống hoặc chỉnh một singleton toàn cục.

Đó là dấu hiệu cần xem xét **Dependency Injection (DI)**: tách việc *sử dụng* phụ thuộc khỏi việc *tạo, cấu hình và lắp ghép* đối tượng. **Inversion of Control (IoC)** chuyển các quyết định tạo/lắp ghép về ranh giới thích hợp, thường là **composition root**. Với Java thuần, DI không yêu cầu DI container.

Ví dụ phác họa:

~~~java
final class OrderService {
    void place(String customerId, long amountVnd) {
        PaymentClient client = new PaymentClient(
                System.getenv("PAYMENT_ENDPOINT"));
        client.charge(customerId, amountVnd);

        AuditRegistry.getInstance().record(
                customerId, java.time.Instant.now());
    }
}
~~~

Các kiểu `PaymentClient` và `AuditRegistry` là thành phần giả định; đoạn mã chỉ minh họa cách viết, không phải chương trình độc lập. Phương thức `place` có ít nhất bốn phụ thuộc **ẩn khỏi constructor**: client thanh toán, cấu hình môi trường, audit singleton và đồng hồ hệ thống.

Test khó chọn client giả, đồng hồ cố định hoặc audit riêng. Các tác dụng phụ có thể xảy ra thật; kết quả phụ thuộc môi trường và trạng thái dùng chung.

**Mục tiêu refactor:** làm cho những phụ thuộc ảnh hưởng đến hành vi, I/O và vòng đời có thể được nhìn thấy, kiểm soát và thay thế từ bên ngoài, đồng thời **giữ nguyên quy tắc nghiệp vụ**. Mục tiêu không phải cấm mọi lệnh `new` hoặc mọi thành viên `static`.

## 2. Ba nhóm dấu hiệu cần nhận diện

| Dấu hiệu | Mẫu thường gặp | Rủi ro kiểm thử | Hướng đặt câu hỏi |
| --- | --- | --- | --- |
| Tự khởi tạo cộng tác viên | `new HttpClient(...)`, `new JdbcRepository(...)` | Chạm mạng/DB, không chọn được fake, khó đóng tài nguyên | Đây là value object hay adapter hạ tầng? |
| State static hoặc singleton toàn cục | `GlobalCache.INSTANCE`, `AppRegistry.getInstance()` | Test dùng chung state, chạy song song không an toàn | Ai thực sự sở hữu và đóng trạng thái này? |
| Truy cập môi trường qua API global | `System.getenv`, `Instant.now`, `UUID.randomUUID` | Kết quả không tất định, khó lặp lại | Nên tiêm giá trị cấu hình hay khả năng đọc/sinh dữ liệu? |

Ba nhóm có thể chồng lên nhau: một singleton kết nối database vừa là global state vừa quản lý I/O. Trong quá trình review, cần truy theo **đường gọi thật** thay vì chỉ tìm từ khóa.

### Không đánh đồng tất cả lời gọi hệ thống với lỗi thiết kế

`Math.max(a, b)` là phép tính thuần túy. `String.valueOf(...)`, `List.of(...)` hoặc hằng số bất biến thường không khiến test đụng môi trường. Ngược lại, một phương thức trông đơn giản nhưng gọi `CurrentUserHolder.get()` sẽ phụ thuộc trạng thái gắn với request, thread hoặc phiên chạy.

**Tác dụng phụ** và **tính không tất định** là hai đặc điểm cần quan sát: gửi email, ghi file, gọi database là tác dụng phụ; thời gian thực, random, locale hoặc timezone mặc định làm kết quả thay đổi. Một dependency có thể có cả hai.

## 3. Phân loại lệnh `new`: đối tượng nghiệp vụ hay hạ tầng?

`new` là cú pháp Java bình thường. Constructor injection không nhằm xóa mọi thao tác tạo đối tượng. Điều quan trọng là **trách nhiệm tạo nằm ở đâu**.

| Lệnh tạo | Cách xử lý thường hợp lý | Lý do |
| --- | --- | --- |
| `new OrderSummary(...)`, `new Money(...)` | Giữ trong use case | Tạo giá trị/kết quả nghiệp vụ |
| `new ArrayList<>()`, `new StringBuilder()` | Giữ cục bộ | Không cần scope quản lý ngoài |
| `new PriceCalculator(config)` | Xem xét theo nhu cầu thay đổi | Logic thuần túy ổn định có thể dùng concrete |
| `new HttpPaymentGateway(...)` | Thường đưa ra composition root | Adapter I/O có cấu hình, cần fake hoặc dùng chung |
| `new FileOutputStream(...)` | Xác định factory/owner rõ ràng | Tài nguyên cần đóng, có thể lỗi khi mở |
| `Executors.newFixedThreadPool(...)` | Thường quản lý tại ranh giới ứng dụng | Phải shutdown và phối hợp tác vụ |
| `new Random()` ngay trong quy tắc cần test tất định | Cân nhắc tiêm nguồn random | Khó kiểm soát kết quả test |

Ví dụ **giữ `new`**:

~~~java
OrderSummary result = new OrderSummary(orderId, amountVnd, issuedAt);
~~~

Đó là việc tạo kết quả. Không có lợi ích rõ ràng nếu tạo thêm `OrderSummaryFactory` chỉ nhằm tránh từ khóa `new`.

Ví dụ cần **xem xét tách**:

~~~java
// Mã minh họa: service tự tạo HTTP adapter cho mỗi lời gọi.
HttpPaymentGateway gateway = new HttpPaymentGateway(url, token);
gateway.charge(orderId, amountVnd);
~~~

Trong trường hợp này, use case đang quyết định nhà cung cấp, cấu hình mạng và vòng đời. Constructor injection một `PaymentGateway` có thể tách trách nhiệm. Nếu cần instance mới theo mỗi tác vụ, hãy tiêm factory có hợp đồng rõ thay vì giữ một client đã mở quá lâu.

## 4. `static` không nhất thiết xấu: phân biệt immutable và mutable

| Mẫu static | Đánh giá |
| --- | --- |
| `static final int LIMIT = 100` | Hằng số bất biến, thường an toàn |
| `static long sum(long a, long b)` thuần túy | Thường an toàn, không cần interface chỉ để tránh static |
| `static final List<String> EVENTS = new ArrayList<>()` | Có **mutable state toàn cục** dù tham chiếu final |
| `static Map<String, Session> ACTIVE` | Có nguy cơ lẫn trạng thái, rò rỉ và race |
| `static final ApiClient CLIENT = ...` | Có thể che giấu kết nối, cấu hình và ownership |
| `static ThreadLocal<RequestContext> CURRENT` | Cần quản lý scope, cleanup và context propagation |

Một lỗi nhận định phổ biến:

~~~java
final class SharedEvents {
    static final java.util.List<String> EVENTS =
            new java.util.ArrayList<>();
}
~~~

`final` chỉ ngăn gán lại tham chiếu `EVENTS`; nó không ngăn `EVENTS.add(...)`. Hai test chạy chung JVM có thể thấy dữ liệu của nhau. Nếu chạy song song, `ArrayList` còn không được thiết kế để nhận ghi đồng thời không đồng bộ hóa.

Ngược lại:

~~~java
final class MoneyMath {
    private MoneyMath() {}

    static long add(long baseVnd, long feeVnd) {
        return Math.addExact(baseVnd, feeVnd);
    }
}
~~~

Không có lý do rõ để tạo `MoneyMathInterface`. Hàm không đọc/ghi shared state hay gọi hạ tầng; test có thể gọi trực tiếp.

### Singleton global khác singleton được lắp ghép có kiểm soát

Hai đối tượng có thể cùng được dùng **một instance**, nhưng cách phụ thuộc rất khác nhau:

- `GlobalNotifier.instance().send(...)`: lớp nghiệp vụ **tự tra cứu** global dependency, constructor không nêu nó.
- `new OrderService(sharedNotifier)`: composition root chọn và truyền dependency, constructor công bố nó rõ ràng.

DI không bắt buộc mỗi service có một instance riêng. Nó cho phép **quản lý việc chia sẻ và vòng đời tại nơi có trách nhiệm**, thay vì phân tán ở các lớp nghiệp vụ.

## 5. Truy cập toàn cục nào nên chuyển đến ranh giới?

| Truy cập trong nghiệp vụ | Hệ quả | Seam thường hợp lý |
| --- | --- | --- |
| `Instant.now()`, `LocalDate.now()` | Test phụ thuộc thời điểm và timezone | Tiêm `Clock` của JDK |
| `UUID.randomUUID()` | ID thay đổi mỗi lần chạy | Tiêm `IdGenerator`/`Supplier<String>` với hợp đồng rõ |
| `System.getenv(...)` / `System.getProperty(...)` | Phụ thuộc môi trường triển khai | Đọc, validate ở startup; tiêm value object cấu hình |
| `DriverManager.getConnection(...)` | Mở DB thật, cần đóng/transaction | Repository adapter và pool/factory |
| `Files.writeString(...)`, `new FileWriter(...)` | Chạm filesystem, quyền ghi và cleanup | Port lưu trữ và file adapter |
| `Services.get(SomeType.class)` | Service locator che dependency | Constructor injection hoặc factory chuyên biệt |
| `ThreadLocal.get()` | State theo thread, có thể lệch request | Truyền context qua method hoặc scope manager |
| `System.out.println(...)` cho tác vụ gửi thông báo | Kết quả gắn với console | Sender/adapter theo mục đích |

Không cần bọc mọi API JDK vào interface tự tạo. `Clock` đã là abstraction cho thời gian. Cấu hình không đổi theo request có thể được biểu diễn bằng đối tượng giá trị thay vì một `ConfigProvider` tổng quát.

`ThreadLocal` cần đặc biệt cẩn thận: thread pool tái sử dụng thread. Nếu không xóa trong `finally`, dữ liệu của request cũ có thể bị dùng ở request mới. Chuyển task sang thread khác cũng không mặc nhiên mang theo context. Thay global state bằng một `ThreadLocal` chưa chắc đã giải quyết đúng scope.

## 6. Vẽ dependency ẩn trước khi refactor

Trước:

~~~mermaid
flowchart TB
    Service["OrderService"]
    Env["System.getenv"]
    Time["Instant.now"]
    IDs["UUID.randomUUID"]
    Static["GlobalNotifier.instance"]
    Store["new FileOrderRepository"]
    Service --> Env
    Service --> Time
    Service --> IDs
    Service --> Static
    Service --> Store
~~~

Sau:

~~~mermaid
flowchart TB
    Root["App.main / Composition root"]
    Service["OrderService"]
    Repo["OrderRepository port"]
    Notify["NoticeSender port"]
    Clock["Clock"]
    ID["IdGenerator port"]
    File["FileOrderRepository"]
    Console["ConsoleNoticeSender"]
    Root -->|"tạo, chọn, tiêm"| Service
    Root -->|"mở và sở hữu"| File
    Root -->|"tạo"| Console
    Root -->|"cấp"| Clock
    Root -->|"cấp"| ID
    Service --> Repo
    Service --> Notify
    Service --> Clock
    Service --> ID
    File -.->|"implements"| Repo
    Console -.->|"implements"| Notify
~~~

**Sự thay đổi quan trọng:** service chỉ biết các khả năng cần dùng; composition root biết **cách tạo** và **đối tượng cụ thể**. Đây là constructor injection bằng Java thuần, không cần DI container.

## 7. Trước refactor: một service khó cô lập

Đoạn dưới đây là **phác họa**, không phải chương trình tự biên dịch vì các kiểu adapter/global registry do ứng dụng cụ thể định nghĩa:

~~~java
final class LegacyOrderService {
    void place(String customerId, long amountVnd) throws Exception {
        String file = System.getenv("ORDER_FILE");
        String id = java.util.UUID.randomUUID().toString();
        java.time.Instant createdAt = java.time.Instant.now();

        FileOrderRepository repo = new FileOrderRepository(file);
        repo.save(new OrderRecord(id, customerId, amountVnd, createdAt));

        GlobalNotificationService.getInstance()
                .send(customerId, "Đã nhận đơn " + id);
    }
}
~~~

Các dấu hiệu:

1. `System.getenv` khiến hành vi phụ thuộc cấu hình toàn tiến trình.
2. `UUID.randomUUID` và `Instant.now` gây khó kiểm tra kết quả chính xác.
3. `new FileOrderRepository` tự mở hạ tầng bên trong use case, không thấy quy tắc đóng.
4. `GlobalNotificationService` là một service locator/singleton ẩn; test khó thay bằng fake riêng.
5. Nếu lưu thành công nhưng gửi thông báo lỗi, không có hướng xử lý nhất quán nghiệp vụ được thể hiện.

Thay vì viết test phải sửa global field bằng reflection hoặc gọi mạng/file thật, hãy đưa các ranh giới nói trên thành **dependency tường minh**.

## 8. Sau refactor: ví dụ Java thuần với constructor injection

Đây là một chương trình hoàn chỉnh, chạy bằng **Java 11 trở lên**, không cần Spring hay mocking framework. Lưu thành **`RefactorToDiDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

public final class RefactorToDiDemo {

    public interface OrderRepository {
        void save(OrderRecord order) throws IOException;
    }

    public interface NoticeSender {
        void send(String customerId, String message);
    }

    public interface IdGenerator {
        String nextId();
    }

    // Value object do nghiệp vụ tạo: new tại use case vẫn hợp lý.
    public static final class OrderRecord {
        private final String id;
        private final String customerId;
        private final long amountVnd;
        private final Instant createdAt;

        public OrderRecord(
                String id, String customerId,
                long amountVnd, Instant createdAt) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id không hợp lệ");
            }
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId không hợp lệ");
            }
            if (amountVnd <= 0) {
                throw new IllegalArgumentException("amountVnd phải dương");
            }
            this.id = id;
            this.customerId = customerId;
            this.amountVnd = amountVnd;
            this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
        }

        public String id() { return id; }
        public String customerId() { return customerId; }
        public long amountVnd() { return amountVnd; }
        public Instant createdAt() { return createdAt; }
    }

    public static final class OrderService {
        private final OrderRepository repository;
        private final NoticeSender notices;
        private final Clock clock;
        private final IdGenerator ids;
        private final long minimumVnd;

        public OrderService(
                OrderRepository repository,
                NoticeSender notices,
                Clock clock,
                IdGenerator ids,
                long minimumVnd) {
            this.repository =
                    Objects.requireNonNull(repository, "repository");
            this.notices = Objects.requireNonNull(notices, "notices");
            this.clock = Objects.requireNonNull(clock, "clock");
            this.ids = Objects.requireNonNull(ids, "ids");
            if (minimumVnd <= 0) {
                throw new IllegalArgumentException("minimumVnd phải dương");
            }
            this.minimumVnd = minimumVnd;
        }

        public OrderRecord place(String customerId, long amountVnd)
                throws IOException {
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId không hợp lệ");
            }
            if (amountVnd < minimumVnd) {
                throw new IllegalArgumentException("Số tiền dưới mức tối thiểu");
            }

            String id = Objects.requireNonNull(ids.nextId(), "id");
            OrderRecord record = new OrderRecord(
                    id, customerId, amountVnd, clock.instant());

            repository.save(record);
            notices.send(customerId, "Đã nhận đơn " + record.id());
            return record;
        }
    }

    // Adapter sở hữu writer, có trách nhiệm đóng.
    public static final class FileOrderRepository
            implements OrderRepository, AutoCloseable {
        private final BufferedWriter writer;

        public FileOrderRepository(Path file) throws IOException {
            writer = Files.newBufferedWriter(
                    Objects.requireNonNull(file, "file"),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }

        @Override
        public void save(OrderRecord order) throws IOException {
            writer.write(order.id() + "," + order.customerId()
                    + "," + order.amountVnd()
                    + "," + order.createdAt());
            writer.newLine();
            writer.flush();
        }

        @Override
        public void close() throws IOException {
            writer.close();
        }
    }

    public static final class ConsoleNoticeSender implements NoticeSender {
        @Override
        public void send(String customerId, String message) {
            System.out.println("TO " + customerId + ": " + message);
        }
    }

    public static final class SequentialIdGenerator implements IdGenerator {
        private final AtomicLong counter = new AtomicLong();

        @Override
        public String nextId() {
            return "ORDER-" + counter.incrementAndGet();
        }
    }

    public static void main(String[] args) throws IOException {
        // Composition root: new được dùng đúng trách nhiệm lắp ghép.
        try (FileOrderRepository repository =
                new FileOrderRepository(Path.of("refactor-orders.csv"))) {
            OrderService service = new OrderService(
                    repository,
                    new ConsoleNoticeSender(),
                    Clock.systemUTC(),
                    new SequentialIdGenerator(),
                    1_000);

            OrderRecord result = service.place("customer-123", 150_000);
            System.out.println(
                    "SAVED " + result.id() + " AT " + result.createdAt());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RefactorToDiDemo.java
java RefactorToDiDemo
~~~

Kết quả minh họa trên console (thời điểm thực tế thay đổi):

~~~text
TO customer-123: Đã nhận đơn ORDER-1
SAVED ORDER-1 AT <thời điểm UTC khi chạy>
~~~

Chương trình ghi nối thêm một dòng vào `refactor-orders.csv`. Generator tuần tự chỉ minh họa: khi khởi động một tiến trình mới, nó lại bắt đầu từ `ORDER-1`, nên **không bảo đảm ID duy nhất giữa các lần chạy hay các tiến trình**. Hệ thống thực cần chiến lược ID và idempotency phù hợp.

### Những gì đã được tách

- `OrderService` không biết file path, không đọc environment và không biết console sender.
- `Clock` và `IdGenerator` được tiêm, nên kết quả test có thể tất định.
- `OrderRepository` và `NoticeSender` là các port thay được bằng fake.
- `minimumVnd` là cấu hình được kiểm tra tại constructor.
- `FileOrderRepository` được tạo và đóng tại composition root qua `try-with-resources`.
- `OrderService` vẫn dùng `new OrderRecord(...)` để tạo **kết quả nghiệp vụ**, không có vấn đề gì với lệnh `new` này.

**Giới hạn ví dụ:** nếu `repository.save(...)` thành công rồi `notices.send(...)` thất bại, đơn vẫn có thể đã lưu. DI không tạo transaction xuyên hai tác dụng phụ. Một ứng dụng thật có thể cần outbox, trạng thái xử lý và retry/idempotency theo nghiệp vụ.

## 9. Kiểm thử sau refactor bằng Java thuần

Sau khi thay dependency ẩn bằng constructor injection, unit test có thể dùng fake mà không mở file, sửa biến môi trường hoặc chạm global singleton.

Tạo **`RefactorToDiDemoTest.java`** cùng thư mục:

~~~java
import java.io.IOException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class RefactorToDiDemoTest {

    static final class MemoryOrders implements RefactorToDiDemo.OrderRepository {
        final List<RefactorToDiDemo.OrderRecord> saved = new ArrayList<>();
        boolean failNext;

        @Override
        public void save(RefactorToDiDemo.OrderRecord record)
                throws IOException {
            if (failNext) {
                throw new IOException("Lỗi lưu giả lập");
            }
            saved.add(record);
        }
    }

    static final class RecordingNotices implements RefactorToDiDemo.NoticeSender {
        int calls;
        String lastCustomer;
        String lastMessage;

        @Override
        public void send(String customerId, String message) {
            calls++;
            lastCustomer = customerId;
            lastMessage = message;
        }
    }

    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Phải từ chối dữ liệu không hợp lệ");
    }

    public static void main(String[] args) throws IOException {
        MemoryOrders repository = new MemoryOrders();
        RecordingNotices notices = new RecordingNotices();

        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
        RefactorToDiDemo.IdGenerator ids = () -> "TEST-001";
        RefactorToDiDemo.OrderService service =
                new RefactorToDiDemo.OrderService(
                        repository, notices, fixed, ids, 1_000);

        RefactorToDiDemo.OrderRecord result =
                service.place("customer-A", 150_000);

        check("TEST-001".equals(result.id()), "ID phải cố định");
        check(result.createdAt().equals(
                Instant.parse("2026-01-01T00:00:00Z")),
                "Thời gian phải cố định");
        check(repository.saved.size() == 1,
                "Phải lưu đúng một đơn");
        check(repository.saved.get(0) == result,
                "Phải lưu cùng kết quả trả về");
        check(notices.calls == 1, "Phải gửi một thông báo");
        check("customer-A".equals(notices.lastCustomer),
                "Sai người nhận");
        check(notices.lastMessage.contains("TEST-001"),
                "Thông báo không chứa ID");

        // Dữ liệu sai bị từ chối trước khi chạm adapter.
        expectInvalid(() -> {
            try {
                service.place(" ", 150_000);
            } catch (IOException unexpected) {
                throw new AssertionError(unexpected);
            }
        });
        expectInvalid(() -> {
            try {
                service.place("customer-A", 500);
            } catch (IOException unexpected) {
                throw new AssertionError(unexpected);
            }
        });
        check(repository.saved.size() == 1,
                "Đầu vào sai không được lưu");
        check(notices.calls == 1,
                "Đầu vào sai không được gửi");

        // Lỗi repository không được kéo theo thông báo.
        repository.failNext = true;
        try {
            service.place("customer-B", 200_000);
            throw new AssertionError("Phải ném IOException");
        } catch (IOException expected) {
            check(notices.calls == 1,
                    "Không gửi nếu lưu thất bại");
        }

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac RefactorToDiDemo.java RefactorToDiDemoTest.java
java RefactorToDiDemoTest
~~~

Test cố định thời gian và ID, dùng danh sách trong bộ nhớ cho repository và sender ghi nhận lời gọi. Nó kiểm tra kết quả nghiệp vụ, đầu vào sai, thứ tự tác dụng phụ và đường lỗi **không cần DI container**.

Fake `ids = () -> "TEST-001"` trả một ID cố định để kiểm tra một lần đặt đơn; không phù hợp để kiểm thử tính duy nhất qua nhiều lần gọi. Khi test yêu cầu nhiều mã khác nhau, hãy tạo fake generator phát một dãy ID được xác định trước.

Unit test của `OrderService` cũng không xác nhận file adapter có thực sự ghi đúng dữ liệu. Cần có integration test riêng cho `FileOrderRepository`, vòng đời writer và các yếu tố filesystem. Tách hai loại test giúp lỗi nghiệp vụ không bị che bởi lỗi môi trường.

## 10. Refactor từng bước để giữ hành vi hiện có

Không nên thay đồng thời toàn bộ `new`, `static` và truy cập global. Refactor có thể vô tình làm đổi thứ tự tác dụng phụ, semantics của cấu hình, quyền sở hữu hoặc scope.

Một trình tự thực tế:

1. **Chọn một luồng đang khó test.** Ghi lại hiện tại vì sao phải chạm DB/file/network hoặc reset static state để chạy test.
2. **Viết characterization test cho hành vi đang có**, trong môi trường cô lập và không phát sinh tác dụng phụ ngoài ý muốn. Xác định input/output, thông báo, trạng thái và trường hợp lỗi.
3. **Vẽ dependency thực.** Truy từ use case qua constructor, lệnh `new`, static factory, singleton, service locator và API toàn cục.
4. **Phân loại dependency.** Giữ value object và hàm thuần túy; ưu tiên seam cho I/O, thời gian, random/ID, config và state dùng chung.
5. **Chuyển một nguồn không tất định trước**, ví dụ tiêm `Clock` rồi dùng `Clock.fixed` trong test.
6. **Tách một adapter**, ví dụ `OrderRepository`, và tạo nó ở composition root. Nếu API legacy không thay được, bọc nó bằng adapter hiện thực port.
7. **Chuyển static global thành dependency được cấp rõ**, nhưng không biến request context ngắn hạn thành field của singleton.
8. **Giữ hành vi và test liên tục**, kiểm tra đường thành công, các đầu vào sai và trình tự tác dụng phụ.
9. **Xác định lifecycle**, nơi tạo, nơi mượn và nơi đóng file/client/pool, kể cả khi khởi tạo dở dang thất bại.
10. **Lặp lại** ở ranh giới tiếp theo; không tạo abstraction chỉ để đạt chỉ tiêu xóa từ khóa.

Chỉ riêng việc đổi `Instant.now()` sang `clock.instant()`, cấp `Clock.systemUTC()` tại startup và `Clock.fixed(...)` trong test đã cải thiện đáng kể khả năng kiểm thử thời gian.

## 11. Chọn seam phù hợp: constructor, method, factory hay adapter?

| Nhu cầu | Công cụ phù hợp | Điểm cần lưu ý |
| --- | --- | --- |
| Service luôn cần repository/client đã cấu hình | Constructor injection | Đảm bảo dependency sống đủ lâu |
| Mỗi request có danh tính/tenant khác nhau | Method injection hoặc request-scoped service | Không giữ request state trong singleton |
| Mỗi tác vụ cần session/transaction mới | Factory tạo resource theo tác vụ | Caller/scope manager phải đóng |
| Resolve dependency theo scope hiện hành | Scoped provider/proxy nếu môi trường hỗ trợ | Không cache đối tượng request cũ |
| Thay một API legacy khó sửa | Adapter hiện thực port | Chặn chi tiết legacy tại ranh giới |
| Cần thời gian tất định | `Clock` của Java | Không cần interface tự chế |
| Đọc cấu hình khi khởi động | Value object config | Validate tại startup, không đọc global trong use case |
| Static mutable cache đang rải rác | Owner/instance được tiêm | Xác định thread safety và scope |

Một sai lầm phổ biến là sửa `GlobalCurrentUser.get()` thành tiêm **một `RequestContext` thật** vào service dùng chung. Constructor injection có mặt, nhưng **captive dependency** vẫn xảy ra. Cần truyền thông tin theo lời gọi hoặc tạo graph theo request.

DI container về sau có thể quản lý resolve, scope và lifecycle; nó không tự thay thế các quyết định về hợp đồng, ownership và dữ liệu nghiệp vụ.

## 12. Những kiểu “refactor” không giải quyết được vấn đề

| Thay đổi | Vấn đề còn lại | Hướng tốt hơn |
| --- | --- | --- |
| `new HttpClient` → `HttpClient.INSTANCE` | Phụ thuộc global vẫn ẩn | Tiêm adapter/client |
| Thêm `static setClientForTest` | Các test có thể ảnh hưởng nhau, race | Fake theo instance test |
| Dùng reflection chỉnh private static | Phụ thuộc chi tiết triển khai | Seam qua constructor/factory |
| Thay `new` bằng `ServiceLocator.get(...)` | Chỉ đổi nơi giấu dependency | Khai báo hợp đồng ở constructor |
| Factory chung `Object create(String)` | Mất kiểu tĩnh, phải cast | Factory chuyên biệt có kiểu |
| Biến static final cache mutable, reset sau test | State vẫn chung giữa test | Chuyển về instance/scope |
| Biến singleton thành bean, vẫn giữ request state | Scope vẫn sai | Truyền theo method hoặc request factory |
| Để garbage collector “đóng” file | Rò rỉ tài nguyên | `try-with-resources`/owner rõ |
| Mock cả phép tính thuần túy | Test bám chi tiết implementation | Dùng hiện thực thật cho logic tất định |
| Sửa cả logic nghiệp vụ lẫn hạ tầng trong một commit | Khó xác định nguyên nhân lỗi | Thay từng seam, chạy test tương ứng |

Câu hỏi đúng không phải “còn `static` hay `new` không?” mà là **“các yếu tố tạo tác dụng phụ, phụ thuộc môi trường hoặc thay đổi hành vi đã được đưa vào phạm vi kiểm soát của bên lắp ghép chưa?”**

## 13. Checklist đọc một class khó test

Hãy kiểm tra theo thứ tự:

- **Constructor:** Dependency bắt buộc có hiển thị không? Có `new` HTTP/DB/file hoặc đọc environment ngay trong constructor?
- **Fields:** Có static mutable state, global singleton, cache chứa dữ liệu request hoặc tài nguyên hết hiệu lực không?
- **Methods:** Có `new` adapter, `Instant.now`, `UUID.randomUUID`, `ThreadLocal.get`, `System.getenv` hoặc service locator không?
- **Composition root:** Ai chọn implementation, cấu hình, tạo và chia sẻ instance?
- **Vòng đời:** Ai mở, ai mượn, ai đóng; nếu lỗi khởi tạo ở giữa thì cleanup thế nào; nếu nhiều thread thì ai bảo đảm an toàn?
- **Test:** Có thể tạo use case bằng `new` và fake Java thuần không? Có test riêng cho adapter, wiring và resource?
- **Giới hạn phạm vi:** Các value object và helper thuần túy có được giữ lại, thay vì tạo interface/factory không có lợi ích?

Một bảng rà soát cụ thể:

| Dependency phát hiện | Nguồn hiện tại | Có nên đưa ra ngoài? | Đích đến |
| --- | --- | --- | --- |
| Thời gian | `Instant.now()` | Có nếu cần kiểm thử tất định | `Clock` |
| ID | `UUID.randomUUID()` | Có nếu behavior/test cần kiểm soát | `IdGenerator` |
| File repository | `new` trong use case | Có | Port + adapter tại composition root |
| Thông báo | Singleton global | Có | `NoticeSender` được tiêm |
| Kết quả đơn | `new OrderRecord(...)` | Thường không | Giữ trong use case |
| Chuỗi xây tạm | `new StringBuilder()` | Không | Giữ cục bộ |

## 14. Bài tập thực hành

**Bài 1 — Phân loại `new`.** Một phương thức có `new ArrayList<>()`, `new Invoice(...)`, `new HttpClient(...)` và `new FileWriter(...)`. Chọn những lệnh nên giữ/đưa ra composition root, giải thích theo trách nhiệm và I/O chứ không chỉ dựa trên tên class.

**Bài 2 — Static final nhưng mutable.** Một dịch vụ có `static final Map<String, Cart> CARTS`. Vì sao `final` không giúp các test độc lập? Thiết kế một `CartRepository` được tiêm và xác định scope thích hợp theo nghiệp vụ.

**Bài 3 — Clock và characterization test.** Một `ReportService` gọi `Instant.now()` và ghi file. Hãy ghi nhận hành vi hiện tại trong thư mục tạm, sau đó chuyển sang `Clock` và `ReportStore` để test nghiệp vụ không cần file.

**Bài 4 — Singleton notification.** Một `EmailService` gọi `GlobalMailer.instance().send(...)`. Thiết kế port `MailSender`, tiêm qua constructor, tạo adapter tại composition root và viết fake ghi nhận lời gọi.

**Bài 5 — Executor lifecycle.** Một lớp tự tạo `ExecutorService` trong constructor nhưng không `shutdown()`. Xác định owner, scope và trình tự dừng nhận việc/chờ tác vụ/đóng executor.

**Bài 6 — DI nhưng sai scope.** Singleton `AuditService` giữ `RequestContext` thật trong field qua constructor. Tái hiện lỗi khi request B dùng context A, rồi sửa bằng method injection hoặc request factory.

**Bài 7 — Tác dụng phụ một phần.** Sửa fake sender để ném lỗi sau khi repository lưu thành công. Quan sát trạng thái còn lại và đề xuất retry/idempotency hoặc outbox. Vì sao DI không tự xử lý consistency?

**Bài 8 — Refactor theo commit nhỏ.** Lên bốn bước cho một service đang dùng `System.getenv`, `UUID.randomUUID`, `Files.writeString` và singleton notification. Mỗi bước phải mô tả seam được tạo và test đi kèm.

**Kết luận:** Refactor sang Dependency Injection không phải cuộc săn lùng mọi `new` và `static`. Hãy nhận diện những phụ thuộc **gây tác dụng phụ, phụ thuộc môi trường, giữ trạng thái dùng chung hoặc cần quản lý vòng đời**. Đưa quyết định tạo/lựa chọn ra composition root, công bố các dependency cần thiết bằng constructor và kiểm thử bằng Java thuần sẽ làm mã dễ thay đổi hơn ngay cả trước khi áp dụng DI container.
