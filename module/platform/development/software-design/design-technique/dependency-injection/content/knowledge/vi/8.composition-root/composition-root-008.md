# Kiểm tra cấu hình và đồ thị trước khi nhận công việc

Một ứng dụng có thể **biên dịch thành công**, nhưng vẫn chưa đủ điều kiện xử lý request: thiếu URL kết nối, giới hạn cấu hình sai, một cộng tác viên chưa được cấp, hoặc tài nguyên bên ngoài không sẵn sàng. Nếu chỉ phát hiện những lỗi đó khi request đầu tiên tới, người dùng sẽ là người gặp sự cố khởi động.

Trong **Dependency Injection (DI)**, *composition root* (điểm lắp ghép) là nơi chọn implementation, tạo đối tượng và nối chúng thành **object graph**. Đây cũng là vị trí thuận lợi để thực hiện các kiểm tra **trước khi công bố ứng dụng sẵn sàng nhận công việc**.

Mục tiêu của bài học thuộc chương **Điểm lắp ghép** là làm rõ:

- Kiểm tra **cấu hình** có hợp lệ trước khi tạo đối tượng phụ thuộc vào cấu hình.
- Kiểm tra **object graph** có được lắp đủ các cộng tác viên bắt buộc và đúng vòng đời.
- Kiểm tra **điều kiện sẵn sàng vận hành** tại thời điểm thích hợp, rồi mới cho request hoặc job đi vào.
- Giải phóng tài nguyên đã tạo nếu bước khởi động thất bại giữa chừng.

Ta sẽ thực hiện bằng **constructor injection và Java thuần** để hiểu thứ tự, quyền sở hữu và khả năng kiểm thử, trước khi chuyển những cơ chế tương tự sang DI container.

> **Phạm vi quan trọng:** "Đồ thị hợp lệ" không có nghĩa là hệ thống sẽ luôn hoạt động. Các kiểm tra khi khởi động giảm lỗi cấu hình và lắp ghép; chúng không thay thế cho xử lý timeout, mất kết nối, lỗi nghiệp vụ hoặc sự cố hạ tầng trong lúc chạy.

## 1. Phân biệt ba loại kiểm tra

Cùng được gọi là "kiểm tra lúc khởi động", nhưng ba nhóm sau có câu hỏi và hệ quả khác nhau.

| Loại kiểm tra | Câu hỏi cần trả lời | Ví dụ | Thời điểm phù hợp |
|---|---|---|---|
| **Cấu hình cục bộ** | Tham số khai báo có đúng cú pháp và bất biến không? | `MAX_QUANTITY` là số nguyên dương, endpoint là URI hợp lệ, tên ứng dụng không rỗng | Ngay sau khi đọc nguồn cấu hình, trước khi tạo graph |
| **Đồ thị phụ thuộc** | Các đối tượng cần thiết đã được cấp và lắp đúng hợp đồng chưa? | `OrderService` có `Inventory`, `WorkReceiver` có `OrderService`, không giữ connection đã hết scope | Khi tạo graph ở composition root |
| **Readiness bên ngoài** | Các khả năng thực sự cần để nhận công việc có sẵn sàng *lúc này* không? | Kiểm tra khả năng kết nối database, khởi tạo pool hoặc xác minh queue consumer đã đăng ký thành công | Sau khi graph được lắp, trước khi mở cổng nhận công việc, theo chính sách startup |

Một cấu hình URL hợp lệ **không chứng minh** server tại URL đó đang chạy. Một constructor nhận đủ interface **không chứng minh** implementation trỏ đúng môi trường. Ngay cả khi ping database thành công khi startup, không có gì bảo đảm request sau đó không gặp lỗi mạng.

Ta nên kiểm tra những điều **có thể biết trước** càng sớm càng tốt, và vẫn thiết kế ứng dụng chống chịu lỗi vận hành.

### Ví dụ về ranh giới kiểm tra

Với một service cần `Inventory`:

```java
final class OrderService {
    private final Inventory inventory;

    OrderService(Inventory inventory) {
        this.inventory = Objects.requireNonNull(inventory, "inventory");
    }
}
```

`Objects.requireNonNull` kiểm tra **bất biến cục bộ** của `OrderService`. Nó không gọi network và không xác minh kho dữ liệu có phản hồi. Nếu việc nhận công việc yêu cầu kho dữ liệu sẵn sàng, composition root có thể gọi một bước readiness riêng. Không nên âm thầm làm I/O trong constructor chỉ để "đảm bảo" dependency hoạt động.

## 2. Một trình tự khởi động rõ ràng

Một trình tự cơ bản cho ứng dụng có nhận công việc là:

```text
        Đọc nguồn cấu hình
                │
                ▼
       Parse + kiểm tra cục bộ
                │  lỗi → không tạo graph
                ▼
       Chọn implementation
                │
                ▼
    Tạo và lắp object graph
                │  lỗi → dọn phần đã tạo
                ▼
  Kiểm tra readiness cần thiết
                │  lỗi → dọn phần đã tạo
                ▼
    Mở nhận request / job
                │
                ▼
       Xử lý công việc
                │
                ▼
      Ngừng nhận công việc
                │
                ▼
      Giải phóng tài nguyên
```

Điểm mấu chốt là **không đưa đối tượng nhận công việc ra bên ngoài** khi graph chưa hoàn thành. Với máy chủ web, điều này có thể là chưa bind listener hoặc chưa báo trạng thái ready. Với background worker, điều này có thể là chưa subscribe queue hoặc chưa bật vòng lặp lấy job.

Nếu một library tự động bắt đầu nhận request ngay khi được tạo, composition root phải hiểu hợp đồng đó và thay đổi thứ tự lắp ghép phù hợp. Đôi khi cần tách *create/configure* và *start* để tránh request đi vào trước khi readiness hoàn tất.

## 3. Kiểm tra cấu hình: chuyển chuỗi thô thành đối tượng hợp lệ

Biến môi trường, tham số dòng lệnh và file cấu hình thường cung cấp **chuỗi**. Không nên chuyền một map giá trị thô qua toàn bộ nghiệp vụ rồi để từng service tự parse lại.

Ví dụ ứng dụng nhận hai cấu hình:

- `APP_NAME`: tên dùng để hiển thị, bắt buộc không rỗng.
- `MAX_QUANTITY`: số lượng tối đa được phép cho một đơn, là số nguyên dương.

Một kiểu cấu hình bất biến có thể kiểm tra mọi điều kiện cần thiết ngay khi được tạo:

```java
record Settings(String appName, int maxQuantity) {
    Settings {
        if (appName == null || appName.isBlank()) {
            throw new IllegalArgumentException(
                "APP_NAME must not be blank");
        }
        if (maxQuantity <= 0) {
            throw new IllegalArgumentException(
                "MAX_QUANTITY must be positive");
        }
    }

    static Settings from(Map<String, String> raw) {
        Objects.requireNonNull(raw, "raw");

        String amountText = raw.get("MAX_QUANTITY");
        if (amountText == null || amountText.isBlank()) {
            throw new IllegalArgumentException(
                "MAX_QUANTITY is required");
        }

        final int limit;
        try {
            limit = Integer.parseInt(amountText);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                "MAX_QUANTITY must be an integer", error);
        }
        return new Settings(raw.get("APP_NAME"), limit);
    }
}
```

*Đây là một phần của ví dụ hoàn chỉnh ở mục 5; cần import `Map` và `Objects`.*

Các lỗi được phát hiện trước khi tạo bất kỳ client hoặc service nào. Sau khi có `Settings` hợp lệ, các thành phần không cần biết `MAX_QUANTITY` xuất phát từ biến môi trường, file YAML hay tham số CLI.

Nếu cấu hình chứa mật khẩu hoặc token, **không in cả cấu hình thô vào log khi kiểm tra lỗi**. Thông báo lỗi nên chỉ ra khóa sai và dạng giá trị được mong đợi, tránh lộ bí mật. Đối với cấu hình phân tán, cũng cần xác định rõ nguồn ưu tiên và môi trường đích; cú pháp đúng không thể thay cho việc chọn đúng database hoặc tenant.

## 4. Kiểm tra đồ thị nghĩa là gì?

Trong DI, object graph gồm các đối tượng và quan hệ tham chiếu giữa chúng. Với ứng dụng đơn giản:

```text
Composition root
      │
      ├── Settings
      │      └── maxQuantity
      │
      ├── Inventory implementation
      │      └── dữ liệu / tài nguyên của inventory
      │
      └── OrderService(inventory, maxQuantity)
                      │
                      ▼
              WorkReceiver(orderService)
```

Đồ thị đã lắp đầy đủ khi các thành phần cần thiết có instance phù hợp, constructor thành công và các ràng buộc về vòng đời được đáp ứng. Có thể kiểm tra bằng vài cách:

1. **Kiểu tại lúc biên dịch:** constructor yêu cầu `Inventory` thì caller phải truyền đối số đúng kiểu; thiếu đối số là lỗi biên dịch Java.
2. **Bất biến runtime của constructor:** `Objects.requireNonNull`, giới hạn cấu hình, đối số có quan hệ hợp lệ, collection không rỗng khi hợp đồng yêu cầu.
3. **Kiểm tra graph tại composition root:** implementation đúng theo cấu hình, các thành phần chia sẻ/dùng riêng đúng ý định, không có kết nối sống trong một transaction bị giữ vào singleton.
4. **Thử lắp graph hoàn chỉnh:** tạo thành công mọi entry point mà ứng dụng định cung cấp; với DI container, bước tương ứng có thể là kiểm tra đăng ký hoặc khởi tạo các bean cần thiết.

Constructor injection làm graph **tường minh hơn** vì yêu cầu về collaborator hiện trên chữ ký constructor. Tuy nhiên, Java không tự đảm bảo một `Inventory` cụ thể đã được cấu hình đúng môi trường, hay một collaborator thread-unsafe có an toàn để dùng chung. Người lắp ghép phải hiểu hợp đồng của các implementation.

### Những lỗi composition cần nhận diện

| Dấu hiệu | Vấn đề | Phản ứng cần thiết |
|---|---|---|
| `new OrderService(null, limit)` | Thiếu dependency bắt buộc | Từ chối ngay khi tạo |
| Tạo service trước khi có collaborator bắt buộc | Không thể hoàn thành constructor | Lắp từ đối tượng lá tới entry point |
| Hai service cùng yêu cầu nhau qua constructor | Vòng phụ thuộc khó hoặc không thể tạo trực tiếp | Xem lại ranh giới và luồng điều phối |
| Service dùng chung giữ transaction connection ngắn hạn | Sai scope/vòng đời | Inject factory hoặc sửa scope |
| Hai module dùng hai instance cache dù phải chia sẻ state | Graph có cấu trúc hợp lệ nhưng không đúng yêu cầu | Chia sẻ đúng instance trong composition root |
| Bọc tất cả dependency trong `ServiceLocator` | Phụ thuộc thực tế bị che | Khai báo trực tiếp collaborator cần thiết |
| Có instance nhưng chưa cấu hình xong đã công bố listener | Có thể nhận request trên graph chưa sẵn sàng | Giữ entry point đóng đến khi đủ điều kiện |

Không phải mọi lỗi graph đều xác định được bằng một thuật toán chung. Một graph không có `null` vẫn có thể sai về nghiệp vụ, môi trường hoặc phân quyền. Kiểm tra cần dựa trên các **invariant mà ứng dụng thực sự yêu cầu**.

## 5. Ví dụ Java thuần: chỉ nhận công việc sau khi sẵn sàng

Ví dụ sau sử dụng Java 17 trở lên. Ứng dụng quản lý một `Inventory` đơn giản và một `OrderService`; `WorkReceiver` đại diện cho entry point nhận công việc. Composition root kiểm tra cấu hình, tạo graph, thực hiện readiness check và chỉ sau đó bật receiver.

Lưu toàn bộ đoạn mã vào `StartupCompositionDemo.java`:

```java
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

public final class StartupCompositionDemo {

    record Settings(String appName, int maxQuantity) {
        Settings {
            if (appName == null || appName.isBlank()) {
                throw new IllegalArgumentException(
                    "APP_NAME must not be blank");
            }
            if (maxQuantity <= 0) {
                throw new IllegalArgumentException(
                    "MAX_QUANTITY must be positive");
            }
        }

        static Settings from(Map<String, String> raw) {
            Objects.requireNonNull(raw, "raw");
            String value = raw.get("MAX_QUANTITY");

            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                    "MAX_QUANTITY is required");
            }

            final int limit;
            try {
                limit = Integer.parseInt(value);
            } catch (NumberFormatException cause) {
                throw new IllegalArgumentException(
                    "MAX_QUANTITY must be an integer", cause);
            }
            return new Settings(raw.get("APP_NAME"), limit);
        }
    }

    // Một collaborator có vòng đời do ứng dụng quản lý.
    interface Inventory extends AutoCloseable {
        void verifyReady();
        boolean hasStock(String sku, int quantity);

        @Override
        void close(); // Hợp đồng mẫu: không khai báo checked exception.
    }

    static final class InMemoryInventory implements Inventory {
        private final Map<String, Integer> stocks;
        private boolean closed;

        InMemoryInventory(Map<String, Integer> stocks) {
            this.stocks = Map.copyOf(
                Objects.requireNonNull(stocks, "stocks"));
        }

        @Override
        public void verifyReady() {
            ensureOpen();
            System.out.println("READY inventory");
        }

        @Override
        public boolean hasStock(String sku, int quantity) {
            ensureOpen();
            return stocks.getOrDefault(sku, 0) >= quantity;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("CLOSE inventory");
        }

        private void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("Inventory is closed");
            }
        }
    }

    // Chỉ điều phối nghiệp vụ, không tự tạo Inventory.
    static final class OrderService {
        private final Inventory inventory;
        private final int maxQuantity;

        OrderService(Inventory inventory, int maxQuantity) {
            this.inventory = Objects.requireNonNull(
                inventory, "inventory");
            if (maxQuantity <= 0) {
                throw new IllegalArgumentException(
                    "maxQuantity must be positive");
            }
            this.maxQuantity = maxQuantity;
        }

        boolean canAccept(String sku, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku is required");
            }
            if (quantity <= 0 || quantity > maxQuantity) {
                throw new IllegalArgumentException(
                    "quantity is outside configured limit");
            }
            return inventory.hasStock(sku, quantity);
        }
    }

    // Mô phỏng HTTP listener / queue consumer của ứng dụng nhỏ.
    static final class WorkReceiver {
        private final OrderService orders;
        private boolean accepting;

        WorkReceiver(OrderService orders) {
            this.orders = Objects.requireNonNull(orders, "orders");
        }

        void beginAccepting() {
            accepting = true;
        }

        String handle(String sku, int quantity) {
            if (!accepting) {
                throw new IllegalStateException(
                    "Application is not ready");
            }
            return orders.canAccept(sku, quantity)
                ? "ACCEPT " + sku
                : "REJECT " + sku;
        }

        void stopAccepting() {
            accepting = false;
        }
    }

    static final class Application implements AutoCloseable {
        private final WorkReceiver receiver;
        private final Inventory inventory;
        private boolean closed;

        Application(WorkReceiver receiver, Inventory inventory) {
            this.receiver = Objects.requireNonNull(receiver);
            this.inventory = Objects.requireNonNull(inventory);
        }

        String handle(String sku, int quantity) {
            if (closed) {
                throw new IllegalStateException(
                    "Application is closed");
            }
            return receiver.handle(sku, quantity);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                receiver.stopAccepting();
                inventory.close();
            }
        }
    }

    // Composition root: tạo, lắp, kiểm tra rồi mới công bố entry point.
    static Application bootstrap(
            Map<String, String> rawSettings,
            Supplier<Inventory> inventoryFactory) {

        // 1. Fail fast với lỗi cấu hình cục bộ.
        Settings settings = Settings.from(rawSettings);
        Objects.requireNonNull(
            inventoryFactory, "inventoryFactory");

        // 2. Bắt đầu tạo tài nguyên có ownership rõ ràng.
        Inventory inventory = Objects.requireNonNull(
            inventoryFactory.get(), "inventoryFactory result");

        try {
            // 3. Lắp object graph bằng constructor injection.
            OrderService orders = new OrderService(
                inventory, settings.maxQuantity());
            WorkReceiver receiver = new WorkReceiver(orders);

            // 4. Kiểm tra điều kiện bắt buộc trước khi nhận việc.
            inventory.verifyReady();

            // 5. Chỉ sau khi mọi bước cần thiết thành công.
            receiver.beginAccepting();
            System.out.println("STARTED " + settings.appName());
            return new Application(receiver, inventory);

        } catch (RuntimeException | Error failure) {
            // Không để lại tài nguyên đã tạo khi startup thất bại.
            try {
                inventory.close();
            } catch (RuntimeException | Error closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }

    public static void main(String[] args) {
        Map<String, String> config = Map.of(
            "APP_NAME", "order-demo",
            "MAX_QUANTITY", "5"
        );

        Supplier<Inventory> inventoryFactory =
            () -> new InMemoryInventory(Map.of("PEN", 10));

        try (Application app = bootstrap(config, inventoryFactory)) {
            System.out.println(app.handle("PEN", 2));
            System.out.println(app.handle("BOOK", 1));
        }
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac StartupCompositionDemo.java
java StartupCompositionDemo
```

Kết quả dự kiến:

```text
READY inventory
STARTED order-demo
ACCEPT PEN
REJECT BOOK
CLOSE inventory
```

### Cách đọc thứ tự khởi động

`Settings.from(...)` chạy **trước** `inventoryFactory.get()`. Nhờ vậy, `MAX_QUANTITY` sai sẽ bị từ chối mà không tạo tài nguyên Inventory.

Sau khi có `Inventory`, composition root tạo `OrderService` và `WorkReceiver`. Đây là graph của ứng dụng:

```text
Settings ────────────── maxQuantity ─────┐
                                        ▼
Inventory instance ───────────────► OrderService
    │                                   │
    │ verifyReady()                     ▼
    └────────────────────────────► WorkReceiver
                                         │
                                   beginAccepting()
                                         │
                                         ▼
                                 Application.handle(...)
```

`verifyReady()` được gọi **sau khi graph đã lắp** nhưng **trước khi receiver được bật và trước khi `Application` được trả cho bên gọi**. Như vậy, ở đường đi thành công, caller chỉ nhận một application đã vượt qua các điều kiện startup mà ví dụ yêu cầu.

`Application` là chủ sở hữu của `Inventory` trong đường đi thành công, nên `try-with-resources` ở `main` đóng nó khi kết thúc. Nếu khởi động thất bại sau khi `Inventory` đã được tạo, nhánh `catch` của `bootstrap` đóng tài nguyên trước khi ném lỗi ra ngoài. Code mẫu giữ lỗi chính và thêm lỗi đóng vào `suppressed exceptions` nếu cần.

**Giới hạn của ví dụ:** `WorkReceiver.accepting` và `Application.closed` dùng `boolean` thông thường vì chương trình chạy tuần tự. Máy chủ nhận việc thực tế cần cơ chế đồng bộ, thiết kế trạng thái có tính an toàn luồng, drain các request đang xử lý và thứ tự shutdown phù hợp. `InMemoryInventory` chỉ là fake hạ tầng đơn giản; `verifyReady()` ở đây không thực sự kết nối mạng.

## 6. Kiểm thử cả đường thành công lẫn khởi động thất bại

Một lợi ích của DI thủ công là kiểm thử chính **composition root** bằng factory giả. Ta có thể đo được thời điểm tài nguyên được tạo, readiness được gọi và tài nguyên được đóng, không cần container hay server.

Lưu `StartupCompositionCheck.java` cùng thư mục với `StartupCompositionDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class StartupCompositionCheck {
    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        AtomicInteger checks = new AtomicInteger();
        AtomicInteger workCalls = new AtomicInteger();
        AtomicInteger closes = new AtomicInteger();

        // Kiểm thử 1: cấu hình lỗi phải chặn việc tạo tài nguyên.
        try {
            StartupCompositionDemo.bootstrap(
                Map.of("APP_NAME", "demo", "MAX_QUANTITY", "0"),
                () -> {
                    creations.incrementAndGet();
                    throw new AssertionError(
                        "Factory must not be called");
                }
            );
            throw new AssertionError("Expected config error");
        } catch (IllegalArgumentException expected) {
            if (creations.get() != 0) {
                throw new AssertionError(
                    "Resource created before config validation");
            }
        }

        // Kiểm thử 2: graph sẵn sàng rồi mới nhận công việc.
        var app = StartupCompositionDemo.bootstrap(
            Map.of("APP_NAME", "demo", "MAX_QUANTITY", "3"),
            () -> {
                creations.incrementAndGet();
                return new StartupCompositionDemo.Inventory() {
                    @Override
                    public void verifyReady() {
                        checks.incrementAndGet();
                    }

                    @Override
                    public boolean hasStock(
                            String sku, int quantity) {
                        if (checks.get() != 1) {
                            throw new AssertionError(
                                "Work arrived before readiness");
                        }
                        workCalls.incrementAndGet();
                        return "PEN".equals(sku) && quantity <= 3;
                    }

                    @Override
                    public void close() {
                        closes.incrementAndGet();
                    }
                };
            }
        );

        if (checks.get() != 1 || workCalls.get() != 0) {
            throw new AssertionError(
                "Unexpected work during startup");
        }

        try (app) {
            if (!"ACCEPT PEN".equals(app.handle("PEN", 2))) {
                throw new AssertionError("Incorrect business result");
            }
        }
        if (workCalls.get() != 1 || closes.get() != 1) {
            throw new AssertionError(
                "Work or shutdown lifecycle incorrect");
        }

        // Kiểm thử 3: readiness thất bại phải dọn tài nguyên.
        try {
            StartupCompositionDemo.bootstrap(
                Map.of("APP_NAME", "demo", "MAX_QUANTITY", "3"),
                () -> {
                    creations.incrementAndGet();
                    return new StartupCompositionDemo.Inventory() {
                        @Override
                        public void verifyReady() {
                            checks.incrementAndGet();
                            throw new IllegalStateException(
                                "inventory unavailable");
                        }

                        @Override
                        public boolean hasStock(
                                String sku, int quantity) {
                            throw new AssertionError(
                                "Must not process work");
                        }

                        @Override
                        public void close() {
                            closes.incrementAndGet();
                        }
                    };
                }
            );
            throw new AssertionError(
                "Expected readiness failure");
        } catch (IllegalStateException expected) {
            if (!"inventory unavailable".equals(
                    expected.getMessage())) {
                throw expected;
            }
        }

        if (creations.get() != 2
                || checks.get() != 2
                || closes.get() != 2
                || workCalls.get() != 1) {
            throw new AssertionError(
                "Startup failure leaked resource or accepted work");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac StartupCompositionDemo.java StartupCompositionCheck.java
java StartupCompositionCheck
```

Kết quả dự kiến là chương trình in thêm các dòng `STARTED demo` của nhánh startup thành công, và kết thúc bằng `PASS`.

Kiểm thử xác nhận:

- **Cấu hình sai** không kích hoạt factory cấp tài nguyên.
- **Readiness chạy trước công việc**; việc tạo graph không tự xử lý request.
- **Đường thành công** đóng tài nguyên khi ứng dụng kết thúc.
- **Readiness thất bại** không trả `Application` cho caller và vẫn giải phóng tài nguyên đã tạo.

Đây là kiểm thử hành vi khởi động, không thay thế integration test tới database hoặc broker thật. Trong môi trường production, health/readiness check cần kiểm soát deadline và lỗi timeout để tránh startup treo vô hạn.

## 7. Kiểm tra điều gì bằng Java compiler và điều gì ở runtime?

Khi constructor nhận dependency rõ ràng, Java compiler loại bỏ được một số lỗi rất sớm:

```java
// Giả định OrderService đã được định nghĩa:
new OrderService(inventory, 5); // Đúng kiểu và số đối số.
new OrderService();             // Không biên dịch nếu thiếu constructor.
```

Tuy vậy, compiler không biết:

- `inventory` có phải `null` lúc chạy hay không.
- Endpoint hạ tầng có được cấu hình đúng cluster hay không.
- `MAX_QUANTITY` có nằm trong phạm vi nghiệp vụ yêu cầu hay không.
- Hai thành phần có đang dùng chung client theo đúng ownership hay không.
- Một collaborator có giữ tài nguyên transaction ngắn hơn vòng đời service không.
- Database sẽ còn kết nối được khi công việc đầu tiên đến hay không.

Có thể chia trách nhiệm như sau:

| Cơ chế | Bắt được gì | Không thể kết luận |
|---|---|---|
| Compiler Java | Kiểu và số lượng tham số constructor, cú pháp, thành viên truy cập | Giá trị runtime, khả dụng network |
| Constructor validation | Null, range, invariant của từng đối tượng | Sức khỏe hạ tầng theo thời gian |
| Composition root | Lựa chọn implementation và cách nối graph; kiểm soát thứ tự startup | Tất cả lỗi tiềm ẩn của nghiệp vụ |
| Readiness check | Một tập điều kiện vận hành được đo tại thời điểm kiểm tra | Tính sẵn sàng vĩnh viễn |
| Integration/end-to-end test | Một số đường đi qua hạ tầng thật và giao diện công việc | Mọi biến động của hệ thống sản xuất |

DI container có thể giúp xác minh thiếu registration, scope mismatch hoặc chu trình phụ thuộc, **tùy framework và cấu hình**. Một số bean được khởi tạo lười (lazy), nên lỗi chỉ xuất hiện khi bean đó được yêu cầu; không nên mặc định rằng "container đã start" nghĩa là toàn bộ graph của mọi nhánh đều đã được xây và kiểm chứng.

## 8. Chọn chính sách readiness cho đúng hệ thống

Không phải mọi dịch vụ phụ thuộc đều cần khỏe tuyệt đối để ứng dụng bắt đầu chạy. Cần phân biệt **hard dependency** và **optional/degraded dependency** theo nhu cầu nghiệp vụ.

Ví dụ hệ thống đơn hàng có:

- Database lưu đơn: không kết nối được thì không thể bảo đảm ghi đơn đúng; có thể là điều kiện bắt buộc trước khi bắt đầu nhận đơn.
- Dịch vụ thống kê: nếu lỗi, ứng dụng có thể vẫn nhận đơn và ghi log để gửi thống kê sau, tùy chính sách sản phẩm.
- Cache tăng tốc: nếu cache hỏng nhưng có đường truy vấn dữ liệu gốc an toàn, ứng dụng có thể chạy ở chế độ giảm hiệu năng.

Bảng quyết định mẫu:

| Phụ thuộc | Có thể tiếp tục nhận việc khi lỗi? | Xử lý tại startup |
|---|---|---|
| Kho giao dịch bắt buộc | Thường không | Không mở nhận việc đến khi đủ điều kiện hoặc báo lỗi startup |
| Dịch vụ gửi telemetry | Tùy sản phẩm, thường có thể | Ghi nhận chế độ suy giảm, không khóa toàn ứng dụng nếu không cần |
| Cache tùy chọn | Có thể nếu fallback đã được thiết kế và kiểm thử | Cấu hình fallback và cảnh báo |
| Khóa mã hóa bắt buộc để giải mã dữ liệu | Không nếu chức năng cần nó | Không nhận công việc liên quan khi khóa chưa sẵn sàng |

Các lựa chọn trên phải dựa vào **cam kết của hệ thống**, không dựa trên việc thành phần có interface hay thuộc package nào. Một thành phần "tùy chọn" trong tính năng này có thể là bắt buộc trong tính năng khác.

### Readiness, liveness và startup khác nhau

- **Startup check:** kiểm tra một hoặc nhiều điều kiện để khởi động thành công. Nó có thể từ chối tạo ứng dụng khi thiếu cấu hình bắt buộc.
- **Readiness:** khả năng **nhận công việc mới tại thời điểm hiện tại**. Khi mất dependency quan trọng trong lúc chạy, readiness có thể cần đổi trạng thái để hệ thống điều phối ngừng gửi việc mới.
- **Liveness:** ứng dụng có còn đang chạy và có khả năng tự tiếp tục hay không. Không nên đồng nhất sự cố ngắn của dependency bên ngoài với việc tiến trình buộc phải bị kill và restart.

Trong ví dụ Java thuần, `verifyReady()` chỉ mô phỏng **startup gate một lần**. Nó chưa có health probe định kỳ và chưa phản ánh trạng thái runtime sau startup. Khi mở rộng sang web server hoặc container orchestrator, cần triển khai trạng thái readiness/liveness theo hợp đồng nền tảng cụ thể.

### Tránh biến readiness thành một truy vấn nghiệp vụ gây tác dụng phụ

Một kiểm tra kết nối nên hạn chế side effect và rủi ro; việc tạo đơn hàng thật, gửi email thật hoặc trừ tiền chỉ để thử readiness là không phù hợp. Với database, probe đọc đơn giản có timeout hoặc kiểm tra pool thường hợp lý hơn việc tạo dữ liệu nghiệp vụ rồi xóa.

Health check cũng cần tránh làm hệ thống quá tải khi nhiều instance cùng thực hiện thường xuyên. Cân nhắc tần suất, deadline, quyền truy cập và dữ liệu nhạy cảm xuất hiện trong log.

## 9. Startup thất bại giữa chừng: ai dọn tài nguyên?

Bắt đầu lắp graph có thể tạo ra nhiều tài nguyên. Giả sử ta khởi động theo thứ tự:

```text
1. Tạo database pool       → thành công
2. Tạo HTTP client         → thành công
3. Đăng ký queue consumer  → thất bại
4. Bật HTTP listener       → chưa chạy
```

Nếu bước 3 thất bại, **pool và HTTP client đã mở phải có đường đóng**. Composition root là nơi thuận lợi để tập trung ownership và đường rollback khi startup lỗi.

Một nguyên tắc là đóng các tài nguyên sở hữu theo **thứ tự ngược với khi tạo**:

```text
Tạo:  DB pool → HTTP client → queue consumer → listener
Đóng: listener → consumer → HTTP client → DB pool
```

Nếu một bước thất bại trong lúc tạo một tài nguyên, **factory hoặc constructor của tài nguyên đó** phải dọn phần đã cấp phát nội bộ trước khi báo lỗi; caller chỉ có thể đóng những tài nguyên đã được trả về thành công.

Với nhiều resource `AutoCloseable`, có thể dùng `try-with-resources` hoặc một quản lý lifecycle cụ thể. Quan trọng là không đóng một resource đã bàn giao quyền sở hữu cho thành phần khác hai lần, không để shutdown chạy song song gây race và không làm thất lạc ngoại lệ ban đầu khi cleanup cũng lỗi.

Một thiết kế phân quyền sở hữu hữu ích:

| Thành phần | Ai tạo? | Ai đóng? |
|---|---|---|
| `Settings` bất biến | Composition root | Không cần đóng |
| `OrderService` thuần điều phối | Composition root | Không cần đóng nếu không sở hữu tài nguyên |
| Database pool/client dài hạn | Composition root hoặc lifecycle manager | Chủ sở hữu tại shutdown |
| Connection/transaction theo request | Factory/transaction boundary | Scope của request hoặc unit of work |
| Consumer/listener | Startup coordinator | Shutdown coordinator, sau khi dừng nhận việc |

**Không nên inject một connection được lấy từ transaction A vào singleton service nhận nhiều request**, vì scope connection kết thúc sớm hơn service. Thay vào đó, inject factory/provider hoặc đối tượng điều phối giao dịch có hợp đồng rõ ràng.

## 10. Mã nghiệp vụ không nên tự quyết định readiness

Một phản ví dụ:

```java
final class OrderService {
    private final Inventory inventory;

    OrderService(Inventory inventory) {
        this.inventory = inventory;
        inventory.verifyReady(); // I/O bị giấu trong constructor.
    }

    boolean canAccept(String sku, int quantity) {
        return inventory.hasStock(sku, quantity);
    }
}
```

Đưa `verifyReady()` vào constructor làm mọi lần tạo `OrderService` phụ thuộc trạng thái hạ tầng hiện thời, kể cả trong unit test. Nếu nhiều service cùng dùng `Inventory`, mỗi constructor có thể probe lặp lại. Mã nghiệp vụ còn mất khả năng được lắp độc lập với kiểm tra startup.

Một phản ví dụ khác là gọi `inventory.verifyReady()` **ở mọi request** rồi mới xử lý đơn, dù yêu cầu ứng dụng chỉ cần readiness startup. Cách này thêm round trip và không giải quyết được race: dependency vẫn có thể hỏng ngay sau probe.

Thiết kế rõ hơn là:

```java
// Ở composition root:
Inventory inventory = createInventory();
OrderService orders = new OrderService(inventory, limit);
WorkReceiver receiver = new WorkReceiver(orders);
inventory.verifyReady();       // Kiểm tra có tên, có chính sách.
receiver.beginAccepting();     // Chỉ mở sau khi kiểm tra thành công.
```

Đoạn phác họa này giả định các hàm tạo và biến đã có, đồng thời **chưa minh họa cleanup**; bản `bootstrap(...)` đầy đủ ở mục 5 có đường giải phóng tài nguyên nếu thất bại.

Trong hệ thống thực tế, các thao tác `hasStock(...)` vẫn phải xử lý hạ tầng không khả dụng ở runtime. Readiness tốt giúp điều phối công việc; nó không loại trừ kiểm tra đầu vào, transaction, retry có giới hạn, idempotency hay xử lý lỗi trong use case.

## 11. Khi dùng DI container, nguyên tắc có thay đổi không?

DI container thay cách tự viết một số thao tác lắp ghép bằng cấu hình, annotation hoặc quy ước, nhưng **ranh giới trách nhiệm không thay đổi**:

```text
Java thuần:
  parse config → new dependencies → new services → readiness → start

DI container:
  parse/bind config → container tạo graph → lifecycle/readiness → start
```

Những câu hỏi vẫn phải trả lời:

1. Cấu hình nào bắt buộc? Có được kiểm tra trước khi khởi động không?
2. Các component cần thiết có được khởi tạo ngay hay lazy?
3. Có chu trình phụ thuộc hoặc trùng registration không? Container xử lý thế nào?
4. Singleton có đang nắm tham chiếu đến request-scoped component trực tiếp không?
5. Hook khởi tạo có thực hiện I/O hoặc tạo tài nguyên? Nếu một hook thất bại, tài nguyên đã cấp phát được dọn thế nào?
6. Khi nào server bắt đầu nhận request hoặc consumer bắt đầu nhận message?
7. Khi dừng ứng dụng, ai dừng nhận việc và ai đóng những tài nguyên dùng chung?

Không nên chuyển `ApplicationContext`/`Container` vào mọi lớp nghiệp vụ để tự `getBean` hoặc `resolve`. Khi lớp nghiệp vụ đi tìm collaborator ở runtime, nó đang áp dụng kiểu **Service Locator**, che khuất phụ thuộc thực tế. Constructor injection vẫn giữ hợp đồng dễ kiểm tra và dễ test; container nên thực hiện phần composition theo ranh giới đã định.

## 12. Các lỗi thường gặp khi kiểm tra trước khi nhận việc

| Lỗi | Hệ quả | Cách làm phù hợp hơn |
|---|---|---|
| Chỉ kiểm tra config sau khi client đã tạo | Cấp phát resource vô ích khi cấu hình sai | Parse và validate cục bộ trước |
| Đọc biến môi trường trong từng service | Cấu hình phân tán, khó test và dễ khác nhau | Tập trung parse thành typed settings |
| Check `null` rồi cho rằng graph đã đúng | Có thể sai scope hoặc implementation | Kiểm tra hợp đồng, ownership và nhu cầu dùng chung |
| Bind HTTP port hoặc subscribe queue quá sớm | Nhận việc khi chưa có graph/readiness | Tách tạo graph khỏi bật entry point |
| Probe hạ tầng trong mọi constructor | I/O khó dự đoán, test phụ thuộc network | Tạo bước readiness ở startup có chủ đích |
| Tạo đối tượng xong nhưng không có rollback khi init lỗi | Rò connection, thread, listener | Theo dõi tài nguyên và đóng khi thất bại |
| Bắt mọi exception rồi vẫn báo ready | Chuyển lỗi khởi động thành lỗi request | Phân loại lỗi bắt buộc/tùy chọn và áp dụng chính sách rõ |
| Readiness phụ thuộc vào tác vụ gửi/trừ tiền thật | Có side effect nghiệp vụ ngoài ý muốn | Kiểm tra không làm thay đổi dữ liệu nghiệp vụ |
| Tưởng startup pass là hết lỗi | Sự cố mạng và trạng thái ngoài vẫn có thể đổi | Xử lý lỗi runtime và health monitoring |
| In toàn bộ cấu hình vào log | Có thể lộ credential/token | Chỉ log tên khóa và thông tin không nhạy cảm |

## 13. Bài tập thực hành

Dựa trên `StartupCompositionDemo`, hãy thực hiện lần lượt:

**Bài tập 1 — Cấu hình sai.** Đổi `MAX_QUANTITY` thành `"abc"`, rồi thành `"-1"`. Dự đoán lỗi được ném ở bước nào và `InMemoryInventory` có được tạo không. Đáp án mong đợi: lỗi phát sinh tại `Settings.from(...)`, trước khi factory được gọi.

**Bài tập 2 — Readiness thất bại.** Tạo implementation `Inventory` có `verifyReady()` ném `IllegalStateException` và `close()` in thông báo. Kiểm tra chương trình không in `STARTED ...` và có gọi `close()`. Khi xây dựng test, nên dùng counter để xác nhận số lần gọi thay vì chỉ nhìn console.

**Bài tập 3 — Thêm dependency bắt buộc.** `OrderService` cần thêm `AuditSink` để ghi nhận đơn được chấp nhận. Thêm interface, triển khai in-memory, sửa constructor và composition root. Kiểm tra mã lắp ghép sẽ không biên dịch nếu quên cấp collaborator mới. Cân nhắc cần kiểm tra `AuditSink` ở startup hay nó chỉ là thành phần tùy chọn.

**Bài tập 4 — Scope và ownership.** Giả sử `Inventory` dùng pool kết nối, còn mỗi `hasStock` cần mở transaction ngắn. Hãy mô tả nơi tạo/đóng pool và nơi mở/đóng transaction. Không dùng một transaction được tạo ở startup cho mọi request.

**Bài tập 5 — Chế độ suy giảm.** Thêm một `MetricsSink` tùy chọn. Nếu sink này không sẵn sàng, ứng dụng vẫn nhận đơn nhưng ghi trạng thái cảnh báo. Hãy xác định rõ điều kiện nào được xem là ready, ai chịu trách nhiệm gửi lại số liệu và khi nào lỗi đo đạc cần được nâng thành sự cố ảnh hưởng nghiệp vụ.

### Câu hỏi tự kiểm tra

1. Vì sao parse `MAX_QUANTITY` nên diễn ra trước khi tạo connection pool?
2. Tại sao một constructor có đủ tham số đúng kiểu chưa chứng minh toàn bộ object graph phù hợp?
3. Sự khác biệt giữa một startup check thành công và readiness tại thời điểm nhận request là gì?
4. Khi bước khởi tạo cuối thất bại, những tài nguyên đã tạo trước đó cần được xử lý ra sao?
5. Có thể gọi một API `container.resolve(...)` ở composition root rồi inject kết quả vào service không?
6. Nếu service chứa dữ liệu của một lần request thì điều gì xảy ra khi nó được dùng chung giữa nhiều request?

**Gợi ý:** (1) để fail sớm mà chưa cấp phát tài nguyên; (2) còn hợp đồng runtime, scope và cấu hình môi trường; (3) readiness có thể thay đổi sau startup; (4) đóng theo ownership, thường theo thứ tự ngược; (5) có, khi lookup chỉ phục vụ lắp ghép và service nhận collaborator tường minh; (6) có thể có trạng thái chia sẻ không mong muốn và lỗi đồng thời.

## Ghi nhớ

- **Composition root** là nơi chọn, tạo, lắp graph và điều phối quá trình đưa ứng dụng vào trạng thái nhận việc; lớp nghiệp vụ chỉ sử dụng những collaborator đã được cung cấp.
- **Kiểm tra cấu hình cục bộ, xác minh object graph và readiness hạ tầng là ba trách nhiệm khác nhau.** Thứ tự rõ ràng giúp phát hiện lỗi ở đúng thời điểm.
- **Chỉ công bố entry point khi các điều kiện bắt buộc hoàn tất.** Khi startup thất bại, phải dọn các tài nguyên đã tạo và không trả về một ứng dụng nửa khởi tạo.
- **Constructor injection hỗ trợ kiểm tra graph**, nhưng không tự giải quyết sai scope, lựa chọn implementation hoặc sự cố hạ tầng.
- **Readiness là đánh giá theo thời điểm.** Ứng dụng vẫn cần xử lý lỗi runtime, theo dõi sức khỏe và quy trình shutdown đúng ownership, dù dùng DI thủ công hay DI container.
