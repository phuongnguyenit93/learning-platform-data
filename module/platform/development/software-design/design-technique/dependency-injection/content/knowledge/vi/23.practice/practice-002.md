# Lắp ghép cùng nghiệp vụ với hai adapter hạ tầng bằng Java thuần

## 1. Mục tiêu thực hành và kết quả cần đạt

**Dependency Injection (DI)** giúp tách lớp sử dụng phụ thuộc khỏi việc tạo và lắp ghép phụ thuộc. Trong **Inversion of Control (IoC)**, quyền quyết định dùng hiện thực nào được chuyển ra ngoài lớp nghiệp vụ, thường tập trung ở **composition root**. Bài thực hành này áp dụng những khái niệm đó bằng Java thuần, không dùng Spring hoặc DI container.

Ta xây dựng một chức năng thanh toán đơn giản: từ mã đơn và giá trị hàng hóa, hệ thống xác định phí vận chuyển, tính tổng tiền, tạo biên nhận rồi lưu biên nhận.

**Cùng một `CheckoutService` phải chạy được với hai adapter hạ tầng:**

1. **`InMemoryOrderStore`:** lưu biên nhận trong bộ nhớ, thích hợp để minh họa và kiểm thử nhanh.
2. **`CsvFileOrderStore`:** lưu biên nhận vào file CSV UTF-8; cần quản lý việc mở, ghi, đọc lại và đóng file.

Cả hai cùng thực hiện hợp đồng `OrderStore`. `CheckoutService` không biết nó đang lưu vào `ArrayList` hay file.

Sau bài này, bạn cần có khả năng:

- Vẽ object graph và phân biệt **business core**, **port**, **adapter** và **composition root**.
- Viết constructor injection cho phụ thuộc bắt buộc, đồng thời kiểm tra cấu hình và dữ liệu.
- Lắp **một nghiệp vụ với hai hiện thực hạ tầng** mà không có nhánh phân biệt adapter trong service.
- Xác định nơi tạo, nơi giữ tham chiếu và nơi đóng resource.
- Viết unit/contract/integration test bằng Java thuần cho hai adapter.
- Nhận ra giới hạn của demo trước khi chuyển sang database, server nhiều request hoặc DI container.

**Phạm vi:** Java 11 trở lên, chạy tuần tự, không cần thư viện ngoài JDK. Đây là bài tập về DI và lắp ghép, không phải hệ thống xử lý thanh toán production.

## 2. Đề bài nghiệp vụ và tiêu chí chấp nhận

Cho một đơn hàng với hai dữ liệu đầu vào:

- `orderId`: chuỗi chữ hoa, chữ số và dấu gạch ngang, ví dụ `ORDER-001`.
- `subtotalVnd`: số tiền hàng hóa tính bằng VND, phải lớn hơn 0.

Chính sách tính phí:

- Khi `subtotalVnd >= 200_000`: **miễn phí vận chuyển**.
- Khi `subtotalVnd < 200_000`: phí vận chuyển **20.000 VND**.
- Tổng thanh toán = tiền hàng + phí vận chuyển, sử dụng `Math.addExact` để phát hiện tràn kiểu `long`.
- Khi tạo biên nhận, lấy thời điểm từ `Clock` được cấp bên ngoài, không trực tiếp gọi `Instant.now()` trong nghiệp vụ.
- Chỉ sau khi đầu vào và kết quả hợp lệ, gọi `OrderStore.save(receipt)`.
- `checkout(...)` trả về biên nhận đã được lưu thành công theo hợp đồng của adapter.

Mã nghiệp vụ **không được**:

- Gọi `new CsvFileOrderStore(...)` bên trong `CheckoutService`.
- Chọn adapter bằng `if (mode.equals("file"))` trong service.
- Đọc biến môi trường hoặc file path trong phương thức `checkout`.
- Tự đóng repository dùng chung khi một đơn xử lý xong.
- Phụ thuộc vào API của framework DI.

### Kết quả mong đợi

Với hai đơn:

| Mã đơn | Tiền hàng | Phí vận chuyển | Tổng tiền |
| --- | ---: | ---: | ---: |
| `ORDER-001` | 150.000 VND | 20.000 VND | 170.000 VND |
| `ORDER-002` | 250.000 VND | 0 VND | 250.000 VND |

Khi chạy qua **adapter bộ nhớ** hoặc **adapter file**, kết quả nghiệp vụ phải giống nhau. Điểm khác biệt chỉ là **cách dữ liệu được lưu và thời gian tồn tại của dữ liệu**.

## 3. Thiết kế object graph: một port, hai adapter thay thế

Ta đặt `OrderStore` là **port hướng ra ngoài** của lớp nghiệp vụ. Cả hai adapter hiện thực cùng port, nên consumer không cần biết chi tiết lưu trữ.

~~~mermaid
flowchart TB
    Root["Composition root: main()"]
    Service["CheckoutService"]
    Clock["Clock"]
    Store["OrderStore (port)"]
    Memory["InMemoryOrderStore"]
    File["CsvFileOrderStore"]

    Root -->|"tạo và tiêm"| Service
    Root -->|"cấp thời gian"| Clock
    Root -->|"chọn một adapter"| Memory
    Root -->|"hoặc chọn một adapter"| File
    Service -->|"constructor injection"| Store
    Service --> Clock
    Memory -.->|"implements"| Store
    File -.->|"implements"| Store
~~~

Các vai trò:

| Vai trò | Thành phần | Trách nhiệm |
| --- | --- | --- |
| Business core | `CheckoutService` | Kiểm tra đầu vào, áp dụng chính sách phí, tạo biên nhận |
| Kết quả nghiệp vụ | `OrderReceipt` | Biểu diễn biên nhận hợp lệ, bất biến sau khi tạo |
| Port | `OrderStore` | Định nghĩa `save` và `findAll` mà core/ứng dụng cần |
| Adapter A | `InMemoryOrderStore` | Lưu danh sách biên nhận trong bộ nhớ |
| Adapter B | `CsvFileOrderStore` | Chuyển đổi biên nhận thành dòng CSV và đọc lại |
| Composition root | `AdapterPracticeDemo.main` | Chọn adapter theo chế độ chạy và quản lý vòng đời |
| Seam thời gian | `Clock` | Cấp thời điểm; test có thể dùng đồng hồ cố định |

**Chiều phụ thuộc mã nguồn:** `CheckoutService` phụ thuộc vào `OrderStore`, không import hoặc trực tiếp tạo hai adapter. `main` biết các adapter để quyết định cách lắp ghép. Đây là điểm mấu chốt của DI.

### Đồ thị có hai cách lắp ghép, không phải hai bộ quy tắc nghiệp vụ

~~~mermaid
flowchart LR
    A["Chạy mode=memory"] --> M["InMemoryOrderStore"]
    B["Chạy mode=file"] --> F["CsvFileOrderStore"]
    M --> Port["OrderStore"]
    F --> Port
    Port --> Core["Cùng CheckoutService"]
    Core --> Result["Cùng quy tắc phí và biên nhận"]
~~~

Hai adapter **không được tạo chỉ để đổi thuật toán tính phí**: chúng thay đổi **cơ chế lưu trữ**, còn phép tính vẫn thuộc use case.

## 4. Cấu trúc mã nguồn tối giản

Để người học có thể sao chép và chạy ngay, ví dụ dùng hai file Java trong cùng một thư mục:

~~~text
adapter-practice/
├── AdapterPracticeDemo.java
└── AdapterPracticeDemoTest.java
~~~

`AdapterPracticeDemo.java` chứa các lớp nhỏ lồng nhau để tránh cấu hình package/build tool. Trong dự án thật, có thể tách chúng thành những file theo cấu trúc như:

~~~text
application/
    CheckoutService.java
domain/
    OrderReceipt.java
ports/
    OrderStore.java
adapters/
    InMemoryOrderStore.java
    CsvFileOrderStore.java
bootstrap/
    Main.java
~~~

Cấu trúc thư mục ở trên **chỉ là một gợi ý**, không phải điều kiện để có DI. Độ rõ của ranh giới trách nhiệm quan trọng hơn số folder.

## 5. Ví dụ Java đầy đủ: cùng `CheckoutService`, hai adapter

Lưu toàn bộ đoạn sau vào **`AdapterPracticeDemo.java`**. Chương trình có thể biên dịch bằng JDK 11 trở lên.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class AdapterPracticeDemo {

    // Port mà nghiệp vụ cần: không có tên file hay lớp JDBC ở đây.
    public interface OrderStore {
        void save(OrderReceipt receipt);
        List<OrderReceipt> findAll();
    }

    // Lỗi của port: adapter file có thể chuyển IOException thành lỗi này.
    public static final class StorageException extends RuntimeException {
        public StorageException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    // Value object: không phụ thuộc file, DB, HTTP hay DI container.
    public static final class OrderReceipt {
        private final String orderId;
        private final long subtotalVnd;
        private final long shippingFeeVnd;
        private final long totalVnd;
        private final Instant createdAt;

        public OrderReceipt(
                String orderId,
                long subtotalVnd,
                long shippingFeeVnd,
                long totalVnd,
                Instant createdAt) {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (subtotalVnd <= 0 || shippingFeeVnd < 0) {
                throw new IllegalArgumentException("Số tiền không hợp lệ");
            }
            if (totalVnd != Math.addExact(subtotalVnd, shippingFeeVnd)) {
                throw new IllegalArgumentException("Tổng tiền không khớp");
            }

            this.orderId = orderId;
            this.subtotalVnd = subtotalVnd;
            this.shippingFeeVnd = shippingFeeVnd;
            this.totalVnd = totalVnd;
            this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
        }

        public String orderId() {
            return orderId;
        }

        public long subtotalVnd() {
            return subtotalVnd;
        }

        public long shippingFeeVnd() {
            return shippingFeeVnd;
        }

        public long totalVnd() {
            return totalVnd;
        }

        public Instant createdAt() {
            return createdAt;
        }
    }

    // Cùng nghiệp vụ cho cả hai adapter.
    public static final class CheckoutService {
        private final OrderStore store;
        private final Clock clock;
        private final long freeShippingFromVnd;
        private final long standardShippingFeeVnd;

        public CheckoutService(
                OrderStore store,
                Clock clock,
                long freeShippingFromVnd,
                long standardShippingFeeVnd) {
            this.store = Objects.requireNonNull(store, "store");
            this.clock = Objects.requireNonNull(clock, "clock");

            if (freeShippingFromVnd <= 0 || standardShippingFeeVnd < 0) {
                throw new IllegalArgumentException(
                        "Cấu hình vận chuyển không hợp lệ");
            }
            this.freeShippingFromVnd = freeShippingFromVnd;
            this.standardShippingFeeVnd = standardShippingFeeVnd;
        }

        public OrderReceipt checkout(String orderId, long subtotalVnd) {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException(
                        "subtotalVnd phải dương");
            }

            long shippingFeeVnd = subtotalVnd >= freeShippingFromVnd
                    ? 0 : standardShippingFeeVnd;
            long totalVnd = Math.addExact(subtotalVnd, shippingFeeVnd);

            OrderReceipt receipt = new OrderReceipt(
                    orderId, subtotalVnd, shippingFeeVnd,
                    totalVnd, clock.instant());

            // Không biết dữ liệu sẽ đến ArrayList hay CSV.
            store.save(receipt);
            return receipt;
        }
    }

    // Adapter A: dữ liệu tồn tại trong vòng đời của instance.
    public static final class InMemoryOrderStore implements OrderStore {
        private final List<OrderReceipt> receipts = new ArrayList<>();

        @Override
        public void save(OrderReceipt receipt) {
            receipts.add(Objects.requireNonNull(receipt, "receipt"));
        }

        @Override
        public List<OrderReceipt> findAll() {
            return List.copyOf(receipts);
        }
    }

    // Adapter B: ghi nối tiếp vào file UTF-8, mở một writer cho vòng đời app.
    public static final class CsvFileOrderStore
            implements OrderStore, AutoCloseable {
        private final Path file;
        private final BufferedWriter writer;
        private boolean closed;

        public CsvFileOrderStore(Path file) throws IOException {
            this.file = Objects.requireNonNull(file, "file");
            this.writer = Files.newBufferedWriter(
                    file,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }

        @Override
        public void save(OrderReceipt receipt) {
            ensureOpen();
            Objects.requireNonNull(receipt, "receipt");

            // orderId chỉ chứa A-Z, 0-9 và '-' nên không có dấu phẩy.
            String line = receipt.orderId() + ","
                    + receipt.subtotalVnd() + ","
                    + receipt.shippingFeeVnd() + ","
                    + receipt.totalVnd() + ","
                    + receipt.createdAt();

            try {
                writer.write(line);
                writer.newLine();
                writer.flush();
            } catch (IOException failure) {
                throw new StorageException(
                        "Không thể ghi biên nhận vào CSV", failure);
            }
        }

        @Override
        public List<OrderReceipt> findAll() {
            ensureOpen();
            List<OrderReceipt> result = new ArrayList<>();

            try {
                for (String line : Files.readAllLines(
                        file, StandardCharsets.UTF_8)) {
                    try {
                        String[] parts = line.split(",", -1);
                        if (parts.length != 5) {
                            throw new IllegalArgumentException(
                                    "Sai số cột CSV");
                        }

                        result.add(new OrderReceipt(
                                parts[0],
                                Long.parseLong(parts[1]),
                                Long.parseLong(parts[2]),
                                Long.parseLong(parts[3]),
                                Instant.parse(parts[4])));
                    } catch (RuntimeException invalidRow) {
                        throw new StorageException(
                                "Dữ liệu CSV không hợp lệ", invalidRow);
                    }
                }
            } catch (IOException failure) {
                throw new StorageException(
                        "Không thể đọc biên nhận từ CSV", failure);
            }

            return List.copyOf(result);
        }

        private void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("CSV store đã đóng");
            }
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                writer.close();
            }
        }
    }

    // Dùng Clock cố định để hai cách lắp ghép dễ đối chiếu.
    private static Clock demoClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                java.time.ZoneOffset.UTC);
    }

    // Luồng nghiệp vụ giữ nguyên, không cần biết loại adapter.
    private static void runScenario(OrderStore store) {
        CheckoutService checkout = new CheckoutService(
                store, demoClock(), 200_000, 20_000);

        OrderReceipt first = checkout.checkout("ORDER-001", 150_000);
        OrderReceipt second = checkout.checkout("ORDER-002", 250_000);

        System.out.println("CREATED " + first.orderId()
                + ": fee=" + first.shippingFeeVnd()
                + ", total=" + first.totalVnd());
        System.out.println("CREATED " + second.orderId()
                + ": fee=" + second.shippingFeeVnd()
                + ", total=" + second.totalVnd());
        System.out.println("STORED COUNT " + store.findAll().size());
    }

    public static void main(String[] args) throws IOException {
        String mode = args.length == 0 ? "memory" : args[0];

        if ("memory".equals(mode)) {
            // Một instance bộ nhớ riêng cho lần chạy này.
            InMemoryOrderStore store = new InMemoryOrderStore();
            runScenario(store);
            return;
        }

        if ("file".equals(mode)) {
            Path file = args.length >= 2
                    ? Path.of(args[1])
                    : Path.of("di-practice-orders.csv");

            // Composition root sở hữu và đóng adapter giữ file writer.
            try (CsvFileOrderStore store = new CsvFileOrderStore(file)) {
                runScenario(store);
            }
            return;
        }

        throw new IllegalArgumentException(
                "Mode phải là 'memory' hoặc 'file'");
    }
}
~~~

### Biên dịch và chạy adapter bộ nhớ

~~~bash
javac AdapterPracticeDemo.java
java AdapterPracticeDemo memory
~~~

Kết quả:

~~~text
CREATED ORDER-001: fee=20000, total=170000
CREATED ORDER-002: fee=0, total=250000
STORED COUNT 2
~~~

Dữ liệu chỉ tồn tại trong `InMemoryOrderStore` đang chạy. Khi chạy lệnh một lần nữa, Java tạo **instance bộ nhớ mới**, không có dữ liệu từ tiến trình trước.

### Chạy cùng nghiệp vụ với adapter file

~~~bash
java AdapterPracticeDemo file di-practice-orders.csv
~~~

Ở lần chạy đầu tiên với file **chưa tồn tại**, kết quả trên console giống nhánh bộ nhớ:

~~~text
CREATED ORDER-001: fee=20000, total=170000
CREATED ORDER-002: fee=0, total=250000
STORED COUNT 2
~~~

Nội dung file `di-practice-orders.csv`:

~~~text
ORDER-001,150000,20000,170000,2026-01-01T00:00:00Z
ORDER-002,250000,0,250000,2026-01-01T00:00:00Z
~~~

Nếu chạy lại lệnh với **cùng file**, chế độ `APPEND` sẽ thêm hai dòng nữa, vì vậy `STORED COUNT` tăng lên 4. Đó là chủ ý minh họa tính tồn tại của adapter file; đừng diễn giải nó là lỗi DI.

**Quan sát trọng tâm:** muốn đổi cách lưu trữ, chỉ đổi cách tạo `OrderStore` tại `main`. Không cần sửa `CheckoutService`, công thức phí hay cấu trúc `OrderReceipt`.

## 6. Đọc code theo đường phụ thuộc và nơi tạo

Các lệnh liên quan DI nằm ở những điểm sau:

**Bước 1 — Xác định hợp đồng.** `OrderStore` chỉ mô tả nhu cầu `save`/`findAll`. Nó không nêu đường dẫn, encoding hoặc cấu trúc bộ nhớ.

**Bước 2 — Viết consumer.** Constructor `CheckoutService(OrderStore store, Clock clock, ...)` khai báo mọi dependency bắt buộc và cấu hình chính sách. `Objects.requireNonNull` phát hiện thiếu dependency ngay lúc lắp ghép.

**Bước 3 — Tạo adapter tại composition root.** `new InMemoryOrderStore()` hoặc `new CsvFileOrderStore(path)` nằm ở `main`, không nằm trong phương thức nghiệp vụ.

**Bước 4 — Constructor injection.** `new CheckoutService(store, clock, ...)` nhận instance đã được chọn.

**Bước 5 — Thực thi nghiệp vụ.** `checkout` tạo value object `OrderReceipt` bằng `new` — điều này **không vi phạm DI**, vì biên nhận là kết quả nghiệp vụ, không phải adapter ẩn.

**Bước 6 — Dọn vòng đời.** Với file adapter, `main` dùng `try-with-resources`; với in-memory adapter không giữ OS resource, không cần `close()`.

Không có lý do phải thêm một interface `CheckoutServiceInterface` hoặc một factory cho `OrderReceipt` chỉ để làm ví dụ “DI đầy đủ hơn”.

## 7. Kiểm thử cùng hợp đồng đối với cả hai adapter

Một bài thực hành thuyết phục cần chứng minh không chỉ biên dịch được mà **cùng một consumer hoạt động với cả hai implementation**.

Ta viết **bộ kiểm thử hợp đồng dùng lại**: phương thức `exerciseStore(...)` nhận `OrderStore`, thực thi chính cùng hai đơn hàng và kiểm tra các đặc điểm mà port cam kết. Sau đó gọi phương thức này với `InMemoryOrderStore` và `CsvFileOrderStore`.

Lưu đoạn sau thành **`AdapterPracticeDemoTest.java`** cạnh file demo:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

public final class AdapterPracticeDemoTest {

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }

    // Cùng một tập hành vi kỳ vọng cho mọi implementation của OrderStore.
    private static void exerciseStore(AdapterPracticeDemo.OrderStore store) {
        check(store.findAll().isEmpty(), "Store mới phải rỗng");

        AdapterPracticeDemo.CheckoutService checkout =
                new AdapterPracticeDemo.CheckoutService(
                        store, fixedClock(), 200_000, 20_000);

        AdapterPracticeDemo.OrderReceipt first =
                checkout.checkout("ORDER-001", 150_000);
        AdapterPracticeDemo.OrderReceipt second =
                checkout.checkout("ORDER-002", 250_000);

        check(first.shippingFeeVnd() == 20_000, "Sai phí đơn đầu");
        check(first.totalVnd() == 170_000, "Sai tổng đơn đầu");
        check(second.shippingFeeVnd() == 0, "Đúng ngưỡng phải miễn phí");
        check(second.totalVnd() == 250_000, "Sai tổng đơn thứ hai");
        check(first.createdAt().equals(
                Instant.parse("2026-01-01T00:00:00Z")),
                "Clock cố định phải cho thời gian xác định");

        List<AdapterPracticeDemo.OrderReceipt> saved = store.findAll();
        check(saved.size() == 2, "Phải có đúng hai bản ghi");
        check("ORDER-001".equals(saved.get(0).orderId()),
                "Sai thứ tự lưu đơn đầu");
        check(saved.get(0).subtotalVnd() == 150_000,
                "Sai tiền hàng đã lưu");
        check(saved.get(0).totalVnd() == 170_000,
                "Sai tổng tiền đã lưu");
        check("ORDER-002".equals(saved.get(1).orderId()),
                "Sai thứ tự lưu đơn thứ hai");
        check(saved.get(1).shippingFeeVnd() == 0,
                "Không giữ được kết quả miễn phí");
        check(saved.get(1).createdAt().equals(second.createdAt()),
                "Không giữ được thời điểm đã lưu");
    }

    private static void testInMemoryAdapter() {
        AdapterPracticeDemo.InMemoryOrderStore store =
                new AdapterPracticeDemo.InMemoryOrderStore();
        exerciseStore(store);
    }

    private static void testFileAdapterAndReopen() throws IOException {
        Path directory = Files.createTempDirectory("di-two-adapters-");
        Path file = directory.resolve("orders.csv");

        try {
            // File mới bảo đảm exerciseStore() bắt đầu từ trạng thái rỗng.
            try (AdapterPracticeDemo.CsvFileOrderStore store =
                    new AdapterPracticeDemo.CsvFileOrderStore(file)) {
                exerciseStore(store);
            }

            // Chứng minh dữ liệu không mất sau khi đóng rồi mở adapter.
            try (AdapterPracticeDemo.CsvFileOrderStore reopened =
                    new AdapterPracticeDemo.CsvFileOrderStore(file)) {
                List<AdapterPracticeDemo.OrderReceipt> persisted =
                        reopened.findAll();
                check(persisted.size() == 2,
                        "Hai bản ghi phải còn sau khi mở lại");
                check("ORDER-002".equals(persisted.get(1).orderId()),
                        "Sai bản ghi sau khi mở lại");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }

    private static void testInvalidInputsBeforeSideEffect() {
        AdapterPracticeDemo.InMemoryOrderStore store =
                new AdapterPracticeDemo.InMemoryOrderStore();
        AdapterPracticeDemo.CheckoutService checkout =
                new AdapterPracticeDemo.CheckoutService(
                        store, fixedClock(), 200_000, 20_000);

        boolean invalidIdRejected = false;
        try {
            checkout.checkout("bad id", 150_000);
        } catch (IllegalArgumentException expected) {
            invalidIdRejected = true;
        }
        check(invalidIdRejected, "Mã đơn sai phải bị từ chối");

        boolean invalidAmountRejected = false;
        try {
            checkout.checkout("ORDER-003", 0);
        } catch (IllegalArgumentException expected) {
            invalidAmountRejected = true;
        }
        check(invalidAmountRejected, "Số tiền không hợp lệ phải bị từ chối");
        check(store.findAll().isEmpty(),
                "Đầu vào sai không được gây tác dụng phụ");
    }

    private static void testStorageFailurePropagates() {
        AdapterPracticeDemo.OrderStore broken =
                new AdapterPracticeDemo.OrderStore() {
                    @Override
                    public void save(AdapterPracticeDemo.OrderReceipt receipt) {
                        throw new AdapterPracticeDemo.StorageException(
                                "Lỗi lưu mô phỏng",
                                new IOException("Disk unavailable"));
                    }

                    @Override
                    public List<AdapterPracticeDemo.OrderReceipt> findAll() {
                        return List.of();
                    }
                };

        AdapterPracticeDemo.CheckoutService checkout =
                new AdapterPracticeDemo.CheckoutService(
                        broken, fixedClock(), 200_000, 20_000);

        boolean failed = false;
        try {
            checkout.checkout("ORDER-004", 150_000);
        } catch (AdapterPracticeDemo.StorageException expected) {
            failed = true;
        }
        check(failed, "Lỗi adapter phải được báo về caller");
    }

    public static void main(String[] args) throws IOException {
        testInMemoryAdapter();
        testFileAdapterAndReopen();
        testInvalidInputsBeforeSideEffect();
        testStorageFailurePropagates();
        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AdapterPracticeDemo.java AdapterPracticeDemoTest.java
java AdapterPracticeDemoTest
~~~

Kết quả mong đợi:

~~~text
Tất cả kiểm thử đều đạt.
~~~

Test không dùng framework. Phương thức `exerciseStore` là ví dụ **contract test** đơn giản: nó thực thi một bộ kỳ vọng chung trên nhiều adapter. Test file còn kiểm tra dữ liệu vẫn tồn tại sau khi đóng và mở lại, điều không thể kỳ vọng từ adapter bộ nhớ.

### Vì sao cần cả unit test và kiểm thử adapter?

- **Unit test nghiệp vụ** dùng in-memory hoặc fake để kiểm tra phí, tổng tiền, input sai và thứ tự lời gọi, không phụ thuộc filesystem.
- **Contract test** bảo vệ giả định chung của `OrderStore`: lưu đúng kết quả và đọc lại theo thứ tự trong bối cảnh bài học.
- **Integration test adapter** kiểm tra phần đặc thù file: mã hóa dữ liệu, I/O và khả năng mở lại.

Việc hai adapter cùng hiện thực một interface mới chỉ giúp **đúng chữ ký Java**. Cả hai phải giữ **cùng ý nghĩa hợp đồng** thì mới thay thế được nhau.

## 8. Vòng đời tài nguyên: cùng port không có nghĩa cùng cách đóng

`InMemoryOrderStore` không mở file, socket hoặc connection; khi ứng dụng không còn tham chiếu, bộ nhớ có thể được thu hồi theo cơ chế của JVM. Với demo này, nó không cần `AutoCloseable`.

`CsvFileOrderStore` mở `BufferedWriter` trong constructor, giữ nó suốt vòng đời adapter và phải đóng khi không còn được dùng. Phần code sử dụng:

~~~java
try (AdapterPracticeDemo.CsvFileOrderStore store =
        new AdapterPracticeDemo.CsvFileOrderStore(path)) {
    AdapterPracticeDemo.CheckoutService service =
            new AdapterPracticeDemo.CheckoutService(
                    store, clock, 200_000, 20_000);
    service.checkout("ORDER-005", 150_000);
}
~~~

Đây là đoạn phác họa sử dụng các kiểu `path` và `clock` đã được khai báo ở ứng dụng. `try-with-resources` đảm bảo gọi `close()` khi rời phạm vi, kể cả khi xử lý đơn ném ngoại lệ.

Cần phân biệt:

- **Lớp nghiệp vụ sử dụng resource nhưng không sở hữu nó.** `CheckoutService` chỉ nhận `OrderStore`, không gọi `close()` vì có thể còn các consumer khác.
- **Composition root sở hữu adapter file** trong demo và có trách nhiệm đóng nó.
- **File adapter sở hữu writer** vì nó đã mở writer trong constructor.
- **Nếu mở resource thất bại trước khi tạo ra adapter**, constructor/factory phải không để lộ resource đã được mở dở. Ví dụ chỉ mở một writer bằng API JDK.
- **Đọc/ghi sau khi đóng** bị từ chối bằng `IllegalStateException` để phát hiện sai vòng đời sớm.

Với nhiều tài nguyên, nên đóng theo thứ tự ngược với lúc mở, tiếp tục cố đóng các tài nguyên còn lại nếu một lần đóng thất bại và giữ lỗi gốc cùng suppressed exceptions khi thích hợp.

~~~mermaid
sequenceDiagram
    participant Root as Composition root
    participant Store as CsvFileOrderStore
    participant Service as CheckoutService
    participant Writer as BufferedWriter
    Root->>Store: new CsvFileOrderStore(path)
    Store->>Writer: Mở writer
    Root->>Service: new CheckoutService(store,...)
    Root->>Service: checkout(orderId,subtotal)
    Service->>Store: save(receipt)
    Store->>Writer: write / flush
    Store-->>Service: save hoàn tất
    Service-->>Root: trả biên nhận
    Root->>Store: close khi thoát try
    Store->>Writer: close
~~~

**Không buộc port nghiệp vụ `OrderStore` kế thừa `AutoCloseable` chỉ vì một adapter cần đóng.** Đó có thể là một lựa chọn trong ứng dụng khác, nhưng ở đây việc quản lý resource thuộc composition root và concrete adapter. Core chỉ cần hai khả năng nghiệp vụ `save` và `findAll`.

## 9. Khi adapter báo lỗi: ai xử lý và cái gì đã xảy ra?

Lỗi có thể phát sinh ở nhiều tầng:

| Nguồn lỗi | Ví dụ | Phản ứng mong đợi |
| --- | --- | --- |
| Đầu vào nghiệp vụ | ID sai, tiền hàng bằng 0 | `IllegalArgumentException` trước khi lưu |
| Bất biến kết quả | Tràn `long` khi cộng phí | Ném lỗi trước khi gọi store |
| File mở thất bại | Sai đường dẫn/quyền truy cập | `IOException` ở lúc composition root tạo adapter |
| Ghi/đọc file thất bại | Disk đầy, file mất quyền đọc | Adapter ném `StorageException` giữ nguyên cause |
| File CSV hỏng | Dòng thiếu cột, số không hợp lệ | Adapter báo `StorageException`, không âm thầm bỏ dòng |
| Vòng đời sai | Sử dụng adapter đã đóng | `IllegalStateException` |

Trong code, `CheckoutService.checkout(...)` chỉ trả về biên nhận **sau khi** `store.save(...)` trả về thành công. Nếu adapter ném `StorageException`, phương thức cũng thất bại và không báo đã lưu thành công.

Tuy nhiên, **ngoại lệ I/O không chứng minh chắc chắn chưa có byte nào được ghi**. Việc ghi có thể đã thành công một phần trước khi lỗi xuất hiện. Bài tập CSV không có transaction hoặc cơ chế bảo đảm exactly-once. Nếu gọi lại `checkout` sau lỗi, có nguy cơ ghi trùng.

Trong hệ thống thực, cần xác định cơ chế idempotency, uniqueness của `orderId`, transactional storage hoặc retry thích hợp. **DI làm dependency thay thế được, không tự tạo tính nguyên tử hay tính nhất quán dữ liệu.**

## 10. Giới hạn hạ tầng của hai adapter

Hai adapter có cùng hợp đồng **trong phạm vi bài tập**, nhưng khác những tính chất kỹ thuật quan trọng:

| Tính chất | `InMemoryOrderStore` | `CsvFileOrderStore` |
| --- | --- | --- |
| Nơi lưu | `ArrayList` trong process | File CSV UTF-8 |
| Tồn tại qua restart | Không | Có, nếu file vẫn tồn tại |
| Tài nguyên cần đóng | Không có trong demo | `BufferedWriter` |
| Khả năng kiểm thử | Nhanh, cô lập, ít phụ thuộc môi trường | Cần thư mục tạm, I/O và cleanup |
| Ghi đồng thời | **Chưa** an toàn luồng | **Chưa** có đồng bộ/khóa giữa luồng hoặc tiến trình |
| Bảo đảm transaction | Không | Không |
| Chống bản ghi trùng ID | Không | Không |
| Lưu lượng lớn | Hạn chế do bộ nhớ | Đọc toàn file mỗi `findAll`, không phù hợp quy mô lớn |

**Lưu ý về CSV:** vì mã đơn chỉ gồm chữ hoa, chữ số và dấu gạch ngang, cùng các cột số/thời gian không chứa dấu phẩy, demo có thể dùng cách ghép chuỗi đơn giản. Đây **không phải parser CSV tổng quát**; nếu thêm tên khách hàng, địa chỉ hoặc chuỗi tự do, phải xử lý escape/quoting đúng chuẩn hoặc dùng thư viện phù hợp.

**Lưu ý về concurrency:** `InMemoryOrderStore` dùng `ArrayList`, `CsvFileOrderStore` dùng một writer và cờ `closed` không đồng bộ. Không dùng hai implementation này nguyên trạng để xử lý nhiều request đồng thời. Khi mở rộng, cần thiết kế thread safety, giới hạn tài nguyên và transaction/storage chuyên dụng.

**Lưu ý về đường dẫn:** CLI trong demo chấp nhận một đường dẫn file. Trong server thật, không nên đưa đường dẫn do client tùy ý cung cấp thẳng cho adapter; cần cấu hình tin cậy và kiểm soát quyền truy cập/đường dẫn hợp lệ.

## 11. Khi nào việc thay adapter là quyết định DI, khi nào là quyết định nghiệp vụ?

**Chọn tại composition root** là đủ khi cùng một bản triển khai ứng dụng chỉ cần một nơi lưu. Ví dụ:

- Môi trường phát triển dùng `InMemoryOrderStore`.
- Chạy một chương trình demo trên máy dùng `CsvFileOrderStore`.
- Production có thể dùng `JdbcOrderStore` thực hiện cùng `OrderStore` nếu hợp đồng phù hợp.

Nếu từng request tự chọn nơi lưu, đây là quyết định **runtime**, phải có một lý do nghiệp vụ hoặc kiến trúc rõ ràng. Đừng thêm `if/else` theo loại adapter vào `CheckoutService` chỉ để phục vụ một chế độ chạy. Có thể dùng một router/factory ở ngoài core khi thực sự cần chọn động, đồng thời xác định scope và quy tắc bảo mật.

### Thay bằng adapter thứ ba

Giả sử muốn thêm `JdbcOrderStore`. Nếu giữ port hiện tại, lớp đó cần cung cấp:

~~~java
// Phác họa interface của adapter tương lai, không phải code JDBC đầy đủ.
final class JdbcOrderStore implements AdapterPracticeDemo.OrderStore {
    @Override
    public void save(AdapterPracticeDemo.OrderReceipt receipt) {
        // Thực hiện INSERT theo hợp đồng bằng JDBC.
    }

    @Override
    public java.util.List<AdapterPracticeDemo.OrderReceipt> findAll() {
        // Thực hiện SELECT và ánh xạ kết quả.
        return java.util.List.of();
    }
}
~~~

Đoạn này chỉ để minh họa nơi nối adapter: `findAll` đang trả danh sách rỗng nên **chưa đáp ứng hợp đồng thực tế** và không được dùng như implementation production. Khi xây thật, adapter cần trả dữ liệu đã lưu, bảo vệ schema/mapping và chạy được các contract test tương ứng.

Cùng `CheckoutService` tiếp tục được sử dụng mà không cần import `java.sql`. Đây là **điểm mở rộng có chủ đích** và cũng là lý do hợp lý để giữ port `OrderStore`.

## 12. Những lỗi dễ mắc khi hoàn thành bài thực hành

| Sai lầm | Biểu hiện | Cách sửa |
| --- | --- | --- |
| `CheckoutService` tự tạo `CsvFileOrderStore` | Consumer phụ thuộc đường dẫn và I/O | Tạo adapter ở composition root |
| Dùng `if (fileMode)` bên trong `checkout` | Nghiệp vụ trộn với lựa chọn hạ tầng | Lựa chọn trước khi constructor injection |
| Test chỉ một adapter | Adapter thứ hai có thể hiểu port khác | Dùng một contract test cho cả hai |
| Test file bằng file có sẵn | Kết quả phụ thuộc dữ liệu các lần chạy trước | Dùng thư mục/file tạm mới |
| Quên đóng `CsvFileOrderStore` | Writer tồn tại quá lâu, khó giải phóng file | `try-with-resources` ở owner |
| `CheckoutService` gọi `store.close()` | Service có thể đóng resource mà nó không sở hữu | Đưa trách nhiệm đóng về composition root |
| Lưu một context request thật trong singleton | Captive dependency, dữ liệu request cũ | Truyền theo method hoặc cấp scope đúng |
| Dùng `Clock.systemUTC()` trong service | Test phải phụ thuộc thời gian thực | Tiêm `Clock`, dùng `Clock.fixed` trong test |
| Cho rằng hai adapter tự động tương đương | Cùng interface nhưng khác semantics | Định nghĩa hợp đồng và chạy contract tests |
| Bắt mọi lỗi rồi trả “lưu thành công” | Che mất thất bại của adapter | Propagate/translate lỗi rõ và quản lý retry |
| Giả định `APPEND` không tạo bản ghi trùng | Chạy lại sinh bản ghi lặp | Thiết kế uniqueness/idempotency nếu cần |
| Tạo một factory vô nghĩa cho mọi value object | Tăng tầng trừu tượng không cần thiết | Dùng `new OrderReceipt` trong nghiệp vụ |
| Dùng CSV demo như database production | Thiếu transaction/concurrency/index/khóa | Chọn storage phù hợp khi mở rộng |

## 13. Bài tập mở rộng theo cấp độ

**Bài tập 1 — Đổi adapter không đổi nghiệp vụ.** Chạy hai mode `memory` và `file`; quan sát kết quả phí và tổng. Chỉ ra chính xác lệnh nào thay đổi đối tượng được tiêm vào constructor, và chứng minh không có nhánh chọn adapter trong `CheckoutService`.

**Bài tập 2 — Kiểm thử biên chính sách.** Bổ sung các đơn có tiền hàng `199_999`, `200_000` và `200_001`. Chạy cùng bộ test với hai adapter, xác nhận phí chuyển từ `20_000` sang `0` đúng ngưỡng.

**Bài tập 3 — Bảo vệ invariant.** Đặt `subtotalVnd = Long.MAX_VALUE` khi phí tiêu chuẩn vẫn dương, nhưng lưu ý nếu ngưỡng miễn phí là `200_000` thì trường hợp này sẽ được miễn phí. Hãy cấu hình ngưỡng miễn phí lớn hơn số tiền đang thử mà vẫn hợp lệ, hoặc thử một số tiền ngay dưới ngưỡng `Long.MAX_VALUE`, để kiểm tra `Math.addExact` phát hiện tràn trước khi lưu.

**Bài tập 4 — Thêm fake báo lỗi.** Tạo `FailingOrderStore` ném `StorageException` khi `save` được gọi. Kiểm tra `checkout` không trả về kết quả thành công. Thảo luận khác biệt giữa “đã ném lỗi” và “chắc chắn chưa ghi bất kỳ byte nào” trong I/O.

**Bài tập 5 — Đọc CSV hỏng.** Tạo một file chỉ chứa một dòng thiếu cột, sau đó gọi `findAll`. Xác nhận adapter báo `StorageException`. Nêu chiến lược xử lý phù hợp cho dữ liệu production: cảnh báo, dừng hay phục hồi.

**Bài tập 6 — Thêm adapter thứ ba.** Viết `JsonLineOrderStore` hoặc một adapter JDBC đơn giản. Giữ nguyên `OrderStore`/`CheckoutService`, chạy lại `exerciseStore` cho adapter mới và xử lý cleanup trong test.

**Bài tập 7 — Quản lý vòng đời và scope.** Giả sử chương trình được biến thành HTTP server xử lý đồng thời. Xác định tại sao hai adapter demo chưa thread-safe; đề xuất mô hình sở hữu repository/client, request context và chính sách đóng khi shutdown.

**Bài tập 8 — Tách file theo vai trò.** Chuyển các lớp lồng nhau thành file riêng: domain, port, application, adapters, bootstrap. Không thay đổi API công khai hoặc kết quả test. Giải thích vì sao cấu trúc thư mục không thay thế constructor injection.

**Bài tập 9 — Tránh overengineering.** Một người đề xuất `OrderReceiptFactory` chỉ gọi `new OrderReceipt(...)` và `CheckoutServiceInterface` chỉ có một implementation. Hãy đánh giá lợi ích thật, chỉ giữ abstraction nếu có lý do thay đổi, kiểm thử hoặc vòng đời rõ ràng.

## 14. Checklist hoàn thành bài

Trước khi coi phần thực hành đạt yêu cầu, hãy kiểm tra:

- [ ] Có **một** `CheckoutService` dùng được với cả hai adapter.
- [ ] `CheckoutService` chỉ nhận `OrderStore`, `Clock` và cấu hình nghiệp vụ qua constructor.
- [ ] Hai adapter thực hiện cùng hợp đồng `save/findAll` và có test chung.
- [ ] Adapter file được tạo, sử dụng và đóng ở composition root.
- [ ] Test không cần DI container, thư viện ngoài, database hoặc mạng.
- [ ] Test file dùng thư mục tạm và dọn dữ liệu sau khi hoàn tất.
- [ ] Đầu vào sai và lỗi tràn số bị từ chối trước khi lưu.
- [ ] Lỗi adapter không bị chuyển thành thông báo thành công.
- [ ] Ghi rõ giới hạn transaction, concurrency và bản ghi trùng.
- [ ] Biết cách thay một adapter khác mà không sửa core.

## 15. Tổng kết: DI được chứng minh bằng khả năng thay adapter

Điểm then chốt của bài không phải số lượng interface hay annotation. **Giá trị của Dependency Injection nằm ở chỗ cùng một luồng nghiệp vụ có thể nhận các cộng tác viên phù hợp do bên ngoài cấp**, trong khi những quyết định về cách tạo, cấu hình và vòng đời nằm ở nơi lắp ghép.

Trong ví dụ này, `CheckoutService` không phân biệt bộ nhớ với file CSV. `InMemoryOrderStore` và `CsvFileOrderStore` có cùng hợp đồng `OrderStore`, nhưng khác cách lưu trữ và quyền sở hữu tài nguyên. Composition root chọn adapter, quản lý việc đóng file, còn test cùng một bộ kỳ vọng để xác nhận **hành vi của nghiệp vụ không thay đổi**.

Khi nắm vững cách làm bằng Java thuần, bạn có thể mở rộng sang adapter HTTP/JDBC và DI container với nền tảng rõ ràng về **constructor injection, object graph, scope, lifecycle và kiểm thử** — thay vì phụ thuộc vào container để che giấu các quyết định thiết kế.
