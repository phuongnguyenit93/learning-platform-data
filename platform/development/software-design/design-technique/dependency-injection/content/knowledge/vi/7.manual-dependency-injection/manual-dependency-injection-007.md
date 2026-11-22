# Quản lý việc khởi tạo và kết thúc tài nguyên trong lắp ghép thủ công

## 1. DI thủ công không chỉ là truyền tham số vào constructor

**Dependency Injection (DI)** tách lớp *sử dụng phụ thuộc* khỏi việc *tạo và lắp ghép* chúng. Với Java thuần, ta có thể tạo các đối tượng bằng `new` tại **composition root** (điểm lắp ghép gần lúc khởi động ứng dụng) rồi truyền chúng cho những service cần sử dụng qua constructor.

Khi phụ thuộc là một đối tượng tính toán thuần túy, việc lắp ghép thường rất đơn giản. Nhưng với tài nguyên có vòng đời như file, socket, client có kết nối, executor, transaction hoặc pool kết nối, còn phải trả lời ba câu hỏi:

1. **Khởi tạo lúc nào và theo thứ tự nào?** Đối tượng nào cần tồn tại trước để tạo đối tượng tiếp theo?
2. **Ai sở hữu tài nguyên?** Thành phần nào chịu trách nhiệm đóng tài nguyên và đảm bảo nó còn sống trong thời gian được sử dụng?
3. **Kết thúc lúc nào, theo thứ tự nào và xử lý lỗi ra sao?** Nếu khởi tạo được một nửa rồi thất bại, tài nguyên đã mở có được dọn dẹp không?

DI container có thể hỗ trợ một phần việc này, nhưng **scope và lifecycle là các quyết định thiết kế ngay cả khi không dùng framework**. Composition root là chỗ có đủ thông tin để thực hiện các quyết định ấy.

Ví dụ không đủ an toàn:

~~~java
final class OrderService {
    private final FileOrderStore store = new FileOrderStore(/* đường dẫn */);
    // Service nghiệp vụ phải biết cách tạo tài nguyên.
    // Không rõ ai đóng store và đóng khi nào.
}
~~~

Đoạn trên là mã phác họa, chưa biên dịch độc lập. Nó cho thấy một rủi ro về trách nhiệm: lớp xử lý đơn hàng tự chọn tài nguyên file, tự khởi tạo và phải tự giải quyết việc đóng file. Khi service được dùng chung, cần test hoặc khởi tạo một phần hệ thống, trách nhiệm trở nên khó kiểm soát.

Thay vào đó, một lớp nghiệp vụ nên nhận **hợp đồng sử dụng** từ ngoài. Điểm lắp ghép tạo tài nguyên, cung cấp nó cho lớp nghiệp vụ và chịu trách nhiệm giải phóng.

## 2. Phân biệt đối tượng thông thường, tài nguyên và quyền sở hữu

Không phải mọi đối tượng được tiêm đều cần gọi `close()`:

| Phụ thuộc | Thường cần đóng? | Quyết định vòng đời |
| --- | --- | --- |
| Calculator, formatter bất biến | Không | Có thể chia sẻ trong nhiều service nếu an toàn luồng |
| Repository dựa trên collection trong bộ nhớ | Thường không | Tùy dữ liệu cần giữ theo ứng dụng hay tác vụ |
| `BufferedWriter`, `InputStream`, socket | Có | Đóng khi kết thúc phạm vi sở hữu |
| `ExecutorService` | Có bước `shutdown()`/`awaitTermination()` | Ngừng nhận việc, xử lý tác vụ đang chạy, sau đó giải phóng |
| Connection từ pool | Có hành vi trả connection về pool khi gọi `close()` | Phải trả đúng lúc; pool có vòng đời riêng |
| Client HTTP hoặc database | Tùy thư viện và cách quản lý kết nối | Đọc hợp đồng API; nếu sở hữu tài nguyên thì đóng lúc shutdown |

Hai kiểu quan hệ cần được phân biệt:

- **Sở hữu (owning):** thành phần mở/tạo một tài nguyên hoặc nhận trách nhiệm quản lý rõ ràng; khi vòng đời kết thúc, nó phải đóng tài nguyên.
- **Mượn để sử dụng (borrowing):** thành phần nhận tham chiếu để gọi phương thức; nó không tự ý đóng vì tài nguyên có thể còn được dùng ở nơi khác.

Trong manual DI, nguyên tắc hữu ích là **composition root hoặc một đối tượng quản lý vòng đời được tạo tại composition root sở hữu tài nguyên được lắp ghép**. Các service nhận tham chiếu thường chỉ mượn để sử dụng.

Ví dụ, một `OrderService` dùng chung `FileOrderStore` và `FileAuditLog` **không nên tự gọi `close()`** sau mỗi đơn hàng. Tài nguyên được chia sẻ cho cả ứng dụng phải còn sống cho đến khi ứng dụng dừng tiếp nhận công việc.

### Hợp đồng vòng đời phải rõ

Việc một kiểu có phương thức `close()` chưa đủ để biết người nhận có được đóng nó hay không. Cần thể hiện quyền sở hữu bằng cấu trúc chương trình, tài liệu API hoặc tên phương thức như `open()`, `acquire()`, `borrow()`. Nếu caller sở hữu một tài nguyên, hãy có đường đi thực tế đảm bảo đóng tài nguyên kể cả khi ngoại lệ xảy ra.

## 3. Trình tự khởi tạo và kết thúc: đi ngược chiều đồ thị phụ thuộc

Một ví dụ có các thành phần:

- `FileOrderStore` mở file lưu đơn hàng.
- `FileAuditLog` mở file ghi sự kiện.
- `OrderService` nhận hai hợp đồng sử dụng và không sở hữu hai file.
- `ApplicationGraph` tạo, lắp ghép và giữ quyền sở hữu hai tài nguyên.

~~~mermaid
flowchart TD
    Root["ApplicationGraph / composition root"]
    Store["FileOrderStore (tài nguyên: orders.csv)"]
    Audit["FileAuditLog (tài nguyên: audit.log)"]
    Service["OrderService (nghiệp vụ)"]
    Root -->|"1. mở"| Store
    Root -->|"2. mở"| Audit
    Root -->|"3. khởi tạo"| Service
    Service -->|"mượn OrderStore"| Store
    Service -->|"mượn AuditLog"| Audit
~~~

**Khởi tạo:** mở store → mở audit → tạo service. **Kết thúc:** dừng công việc sử dụng service → đóng audit → đóng store.

Đóng theo **thứ tự ngược với thứ tự mở** là một quy tắc phổ biến, nhất là khi tài nguyên tạo sau có tham chiếu đến tài nguyên tạo trước. Tuy nhiên, điều quan trọng nhất là thứ tự đóng **thực sự tôn trọng đồ thị phụ thuộc**: không đóng tài nguyên khi vẫn còn thành phần cần sử dụng nó.

Nếu việc mở audit thất bại sau khi store đã mở, store cần được đóng ngay. Điều này gọi là **dọn dẹp khi khởi tạo một phần thất bại**. Chỉ viết `try-with-resources` cho luồng chạy chính mà quên xử lý điểm thất bại khi dựng đồ thị cũng có thể làm rò rỉ tài nguyên.

## 4. Ví dụ hoàn chỉnh bằng Java thuần: lắp ghép và sở hữu vòng đời

Ví dụ sau dùng Java 11 trở lên; không cần Spring, annotation hay DI container. Nó ghi đơn hàng vào `orders.csv` và sự kiện vào `audit.log` trong thư mục `manual-di-output`.

Lưu toàn bộ thành `ManualDiLifecycleDemo.java`:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.Objects;

public final class ManualDiLifecycleDemo {

    // Hợp đồng nghiệp vụ. Không yêu cầu service tự đóng phụ thuộc.
    public interface OrderStore {
        void save(String orderId, long amountVnd) throws IOException;
    }

    public interface AuditLog {
        void record(String event) throws IOException;
    }

    // Adapter sở hữu một BufferedWriter cụ thể.
    public static final class FileOrderStore
            implements OrderStore, AutoCloseable {
        private final BufferedWriter writer;

        public FileOrderStore(Path path) throws IOException {
            this.writer = Files.newBufferedWriter(
                    Objects.requireNonNull(path, "path"),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }

        @Override
        public void save(String orderId, long amountVnd) throws IOException {
            writer.write(orderId + "," + amountVnd);
            writer.newLine();
            writer.flush();
        }

        @Override
        public void close() throws IOException {
            writer.close();
        }
    }

    public static final class FileAuditLog
            implements AuditLog, AutoCloseable {
        private final BufferedWriter writer;

        public FileAuditLog(Path path) throws IOException {
            this.writer = Files.newBufferedWriter(
                    Objects.requireNonNull(path, "path"),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }

        @Override
        public void record(String event) throws IOException {
            writer.write(event);
            writer.newLine();
            writer.flush();
        }

        @Override
        public void close() throws IOException {
            writer.close();
        }
    }

    public static final class OrderService {
        private final OrderStore orders;
        private final AuditLog audit;

        public OrderService(OrderStore orders, AuditLog audit) {
            this.orders = Objects.requireNonNull(orders, "orders");
            this.audit = Objects.requireNonNull(audit, "audit");
        }

        public void placeOrder(String orderId, long amountVnd)
                throws IOException {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("Mã đơn không hợp lệ");
            }
            if (amountVnd <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }

            orders.save(orderId, amountVnd);
            audit.record("ORDER_SAVED:" + orderId);
        }

        // Không có close(): service chỉ mượn hai phụ thuộc.
    }

    // Sở hữu các tài nguyên mở tại composition root.
    public static final class ApplicationGraph implements AutoCloseable {
        private final FileOrderStore store;
        private final FileAuditLog audit;
        private final OrderService service;
        private boolean closed;

        private ApplicationGraph(FileOrderStore store, FileAuditLog audit) {
            this.store = store;
            this.audit = audit;
            this.service = new OrderService(store, audit);
        }

        public static ApplicationGraph open(Path directory)
                throws IOException {
            Files.createDirectories(
                    Objects.requireNonNull(directory, "directory"));

            FileOrderStore store = null;
            FileAuditLog audit = null;

            try {
                store = new FileOrderStore(
                        directory.resolve("orders.csv"));
                audit = new FileAuditLog(
                        directory.resolve("audit.log"));

                return new ApplicationGraph(store, audit);
            } catch (IOException | RuntimeException failure) {
                // Ngược thứ tự mở; giữ lỗi gốc và đính kèm lỗi đóng.
                closeAfterStartFailure(audit, failure);
                closeAfterStartFailure(store, failure);
                throw failure;
            }
        }

        private static void closeAfterStartFailure(
                AutoCloseable resource, Exception failure) {
            if (resource == null) {
                return;
            }
            try {
                resource.close();
            } catch (Exception closeError) {
                failure.addSuppressed(closeError);
            }
        }

        public OrderService service() {
            if (closed) {
                throw new IllegalStateException("Graph đã đóng");
            }
            return service;
        }

        @Override
        public void close() throws IOException {
            if (closed) {
                return;
            }
            closed = true;

            IOException firstFailure = null;
            try {
                audit.close(); // Được mở sau nên đóng trước.
            } catch (IOException failure) {
                firstFailure = failure;
            }

            try {
                store.close(); // Vẫn đóng dù audit.close() lỗi.
            } catch (IOException failure) {
                if (firstFailure == null) {
                    firstFailure = failure;
                } else {
                    firstFailure.addSuppressed(failure);
                }
            }

            if (firstFailure != null) {
                throw firstFailure;
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Paths.get("manual-di-output");

        try (ApplicationGraph graph = ApplicationGraph.open(directory)) {
            graph.service().placeOrder("ORDER-001", 120_000);
            graph.service().placeOrder("ORDER-002", 250_000);
        } // graph.close() luôn được gọi khi thoát khối.
    }
}
~~~

Chạy trong thư mục chứa file nguồn:

~~~bash
javac ManualDiLifecycleDemo.java
java ManualDiLifecycleDemo
~~~

Sau khi chạy thành công, bạn có thể xem hai file được tạo trong `manual-di-output`:

~~~text
manual-di-output/
├── orders.csv
└── audit.log
~~~

`orders.csv` sẽ có hai dòng `ORDER-001,120000` và `ORDER-002,250000`. `audit.log` sẽ có hai sự kiện tương ứng. Chạy lại chương trình sẽ **ghi nối thêm** do cấu hình `StandardOpenOption.APPEND`; đây là ví dụ học tập, chưa giải quyết việc chống lưu trùng đơn hàng.

### Tại sao thiết kế này là DI thủ công?

`OrderService` chỉ nhận hai hợp đồng `OrderStore` và `AuditLog` qua constructor. Nó không biết dữ liệu được lưu vào file hay database, không biết path, không mở file, và không quyết định khi nào đóng writer.

`ApplicationGraph.open()` là mã lắp ghép thực tế: tạo hai adapter, cung cấp chúng cho service rồi lưu tham chiếu để quản lý vòng đời. Đó là một **composition root có đối tượng quản lý vòng đời**, hoàn toàn thực hiện được bằng Java thuần.

Các interface `OrderStore` và `AuditLog` hữu ích ở ranh giới lưu trữ và ghi sự kiện, nơi có I/O. Tuy nhiên, việc sử dụng DI **không bắt buộc mọi phụ thuộc phải là interface**; một calculator thuần túy có thể được tiêm trực tiếp bằng lớp cụ thể.

### Vì sao `OrderService` không được gọi `close()`?

Service chỉ **mượn** hai phụ thuộc để thực hiện nghiệp vụ. Nếu đóng `orders` sau khi tạo đơn đầu tiên, đơn thứ hai sẽ thất bại. Nếu nhiều service cùng dùng một adapter, một service không có quyền hủy tài nguyên của service khác. Quyền sở hữu tài nguyên được giữ tập trung ở `ApplicationGraph`.

## 5. Xử lý khởi tạo một phần thất bại và ngoại lệ khi đóng

Hai điểm thường bị bỏ quên trong manual DI:

**Trường hợp A — mở được một tài nguyên, mở tài nguyên sau thất bại.**

Giả sử `orders.csv` được mở thành công, nhưng mở `audit.log` ném `IOException` do thiếu quyền ghi. Nếu chỉ thoát khỏi `open()`, writer đầu tiên có thể bị bỏ lại mà không đóng. Trong ví dụ, nhánh `catch` đóng audit nếu có, rồi đóng store nếu có, trước khi ném lại ngoại lệ khởi tạo.

**Trường hợp B — đóng tài nguyên đầu tiên thất bại.**

Giả sử `audit.close()` ném `IOException`. Ta vẫn phải cố đóng `store`. Nếu cả hai đều thất bại, giữ ngoại lệ đầu tiên và thêm ngoại lệ sau bằng `addSuppressed()`. Không nên để việc đóng một tài nguyên khiến tất cả tài nguyên còn lại bị bỏ qua.

### `try-with-resources` xử lý được điều gì?

Khi một phạm vi chỉ cần mở tài nguyên để làm việc rồi đóng ngay, dùng `try-with-resources` là cách ngắn gọn nhất:

~~~java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedWriter writer = Files.newBufferedWriter(
        Path.of("result.txt"), StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
~~~

`try-with-resources` tự đóng resource khi thoát khối, kể cả nếu code trong khối ném ngoại lệ. Với nhiều resource khai báo từ trái sang phải, Java đóng theo thứ tự **từ phải sang trái**; nếu lỗi xảy ra khi đóng, Java duy trì thông tin các lỗi bổ sung dưới dạng suppressed exceptions.

Ở ví dụ `ApplicationGraph`, `try-with-resources` trong `main` đảm bảo **graph được đóng**. Phần `ApplicationGraph.open()` vẫn phải tự xử lý tình huống **chưa tạo xong graph**. Không có đối tượng graph hoàn chỉnh để đóng nếu constructor hoặc factory ném lỗi trước khi trả về.

### Vì sao giữ suppressed exceptions?

Giả sử thao tác chính thất bại vì dữ liệu bị từ chối, sau đó close cũng thất bại. Nếu chỉ giữ ngoại lệ từ close, ta mất dấu nguyên nhân ban đầu. `Throwable.addSuppressed()` cho phép lưu cả thông tin lỗi chính và lỗi phát sinh trong quá trình dọn dẹp. Có thể xem bằng `exception.getSuppressed()` hoặc stack trace đầy đủ.

Đây là đặc điểm đặc biệt hữu ích khi composition root khởi tạo nhiều resource với các bước có thể thất bại khác nhau.

## 6. Scope quyết định ai được dùng tài nguyên và dùng đến khi nào

**Scope** là phạm vi sử dụng chung một instance. **Lifecycle** là tiến trình từ tạo → dùng → đóng. Trong manual DI, cả hai do mã của chính bạn thực hiện.

| Scope | Khởi tạo ở đâu? | Kết thúc khi nào? | Ví dụ |
| --- | --- | --- | --- |
| Theo ứng dụng | Startup/composition root | Sau khi ngừng nhận và xử lý xong công việc, trước khi tiến trình kết thúc | Client dùng chung, pool kết nối, dịch vụ không giữ trạng thái request |
| Theo request/tác vụ | Đầu request hoặc job | Trong `finally`/`try-with-resources` khi request/job xong | Transaction, stream hoặc session riêng của tác vụ |
| Theo phương thức | Ngay trước thao tác I/O | Khi khối thao tác kết thúc | Đọc một file hay tải dữ liệu tạm |
| Theo đối tượng được cấp riêng | Factory tại thời điểm cần | Theo hợp đồng của đối tượng nhận ownership | Một session làm việc độc lập |

Một cách thiết kế thường gặp là **app-scope resource sống lâu**, còn service nghiệp vụ có thể sống lâu hoặc được tạo theo yêu cầu. Nếu tạo mới `OrderService` cho mỗi request nhưng nó nhận cùng `OrderStore` dùng chung, ta vẫn phải chờ mọi request hoàn thành trước khi đóng store.

Ngược lại, đưa một connection chỉ có hiệu lực trong một transaction vào service sống cả vòng đời ứng dụng có thể dẫn đến **lệch scope**: service giữ tham chiếu đến tài nguyên đã hết hạn, hoặc nhiều request dùng chung connection vốn không được thiết kế cho việc đó.

### Shared resource và thread safety

Trong ví dụ, `ApplicationGraph` dùng hai `BufferedWriter` cho cách chạy **tuần tự** trong `main`. Đừng tự suy ra hai adapter này có thể ghi đồng thời từ nhiều request mà vẫn tạo các dòng dữ liệu đúng và không bị xen kẽ. Khi chuyển sang server đa luồng, cần thiết kế cơ chế đồng bộ, hàng đợi ghi hoặc phương án lưu trữ phù hợp.

`ApplicationGraph.closed` cũng chỉ dùng cho luồng đơn trong bài học. Nó **không tạo bảo đảm shutdown an toàn với đa luồng**. Đối với server, phải phối hợp dừng nhận request, chờ tác vụ đang chạy xong và ngăn phát sinh tác vụ mới trước khi đóng resource. Chỉ thêm `volatile` cho một cờ không thay thế quy trình phối hợp đó.

## 7. Quy trình shutdown cho ứng dụng chạy lâu

Trong ứng dụng dòng lệnh ngắn, `try-with-resources` quanh toàn bộ hoạt động đủ rõ ràng. Ứng dụng web, queue consumer hoặc worker chạy lâu thường cần **graceful shutdown**:

1. **Dừng nhận công việc mới**: không mở thêm request, message hoặc job.
2. **Chờ hoặc hủy có kiểm soát công việc đang chạy**: tuân thủ timeout và chính sách nghiệp vụ. Không đóng resource khi tác vụ còn đang ghi.
3. **Đóng các tài nguyên do ứng dụng sở hữu theo thứ tự phù hợp**: consumer/worker, session, client, pool... tùy quan hệ phụ thuộc.
4. **Ghi nhận lỗi đóng và hoàn tất**: nếu một resource đóng lỗi, tiếp tục cố đóng resource còn lại; đưa các lỗi vào log/giám sát.

Một server có thể dùng shutdown hook hoặc lifecycle callback của hệ điều hành/framework, nhưng phải tránh cài đặt hai đường shutdown cùng tranh nhau đóng tài nguyên. Khi vận hành thực tế, đường đóng nên nhất quán và chịu được việc được gọi lại.

Một factory hoặc composition root có thể cung cấp `ApplicationGraph.close()` cho lớp điều phối shutdown, thay vì để từng service tự đăng ký shutdown hook. Với executor, cần dùng API ngừng nhận tác vụ, chờ và buộc hủy khi cần, không đánh đồng điều này với `close()` của mọi tài nguyên.

### `AutoCloseable` có phải luôn idempotent?

Không. **Giao diện `AutoCloseable` không bảo đảm mọi hiện thực đều có thể đóng nhiều lần mà không gây hệ quả**. Nếu muốn một đối tượng quản lý graph cho phép gọi `close()` lặp lại, hãy thiết kế và kiểm thử hành vi đó. Trong ví dụ, `ApplicationGraph` đặt cờ `closed` để tránh cố đóng writer hai lần trong ngữ cảnh một luồng, nhưng hành vi này là quyết định của `ApplicationGraph`.

## 8. Kiểm thử lắp ghép và dọn dẹp tài nguyên bằng Java thuần

DI giúp kiểm tra logic nghiệp vụ không cần mở file thật. Cùng lúc, kiểm thử lắp ghép cần xác nhận tài nguyên được mở, sử dụng và đóng đúng lúc. Hai loại kiểm thử bảo vệ hai trách nhiệm khác nhau.

### 8.1. Kiểm thử nghiệp vụ với fake không giữ tài nguyên

Tạo `ManualDiLifecycleDemoTest.java` cùng thư mục với chương trình chính:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class ManualDiLifecycleDemoTest {
    static final class InMemoryStore
            implements ManualDiLifecycleDemo.OrderStore {
        int saves;
        String lastId;

        @Override
        public void save(String orderId, long amountVnd) {
            saves++;
            lastId = orderId;
        }
    }

    static final class InMemoryAudit
            implements ManualDiLifecycleDemo.AuditLog {
        int records;

        @Override
        public void record(String event) {
            records++;
        }
    }

    static void check(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws IOException {
        InMemoryStore store = new InMemoryStore();
        InMemoryAudit audit = new InMemoryAudit();
        ManualDiLifecycleDemo.OrderService service =
                new ManualDiLifecycleDemo.OrderService(store, audit);

        service.placeOrder("ORDER-123", 75_000);
        check(store.saves == 1, "Phải lưu đúng một đơn hàng");
        check("ORDER-123".equals(store.lastId), "Sai mã đơn");
        check(audit.records == 1, "Phải ghi đúng một sự kiện");

        try {
            service.placeOrder("khong hop le", 1_000);
            throw new AssertionError("Phải từ chối mã đơn");
        } catch (IllegalArgumentException expected) {
            check(store.saves == 1, "Không được lưu đơn sai");
            check(audit.records == 1, "Không được log đơn sai");
        }

        // Kiểm tra thực tế: graph tạo, ghi và đóng file đúng scope.
        Path temporary = Files.createTempDirectory("manual-di-test-");
        try {
            try (ManualDiLifecycleDemo.ApplicationGraph graph =
                    ManualDiLifecycleDemo.ApplicationGraph.open(temporary)) {
                graph.service().placeOrder("ORDER-456", 60_000);
            }

            List<String> orders = Files.readAllLines(
                    temporary.resolve("orders.csv"),
                    StandardCharsets.UTF_8);
            List<String> events = Files.readAllLines(
                    temporary.resolve("audit.log"),
                    StandardCharsets.UTF_8);

            check(orders.size() == 1, "Phải có một dòng đơn hàng");
            check("ORDER-456,60000".equals(orders.get(0)),
                    "Nội dung đơn hàng không đúng");
            check(events.size() == 1, "Phải có một sự kiện");
            check("ORDER_SAVED:ORDER-456".equals(events.get(0)),
                    "Nội dung sự kiện không đúng");
        } finally {
            Files.deleteIfExists(temporary.resolve("audit.log"));
            Files.deleteIfExists(temporary.resolve("orders.csv"));
            Files.deleteIfExists(temporary);
        }

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ManualDiLifecycleDemo.java ManualDiLifecycleDemoTest.java
java ManualDiLifecycleDemoTest
~~~

Test nghiệp vụ dùng fake nên không cần môi trường file. Test lắp ghép dùng thư mục tạm, kiểm tra dữ liệu được ghi và đọc lại sau khi `try-with-resources` đã đóng graph, rồi dọn dữ liệu tạm.

### 8.2. Các tình huống vòng đời nên có test riêng trong dự án thật

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Mở tài nguyên thứ hai thất bại | Tài nguyên đầu tiên đã được đóng |
| Một tài nguyên ném lỗi trong `close()` | Các tài nguyên khác vẫn được cố đóng |
| Gọi `close()` lại | Hành vi đúng theo hợp đồng idempotency bạn đã công bố |
| Service dùng tài nguyên sau shutdown | Có cơ chế chặn sử dụng hoặc trả lỗi rõ ràng |
| Request đang chạy khi shutdown | Quy trình chờ, hủy và giải phóng tôn trọng thời hạn |
| Shared resource nhận nhiều lời gọi song song | Dữ liệu không bị race hoặc phá vỡ tính nhất quán |

Bài thực hành chính chưa mô phỏng lỗi đóng vì `BufferedWriter` không cung cấp một cách chắc chắn, đơn giản để chủ động gây lỗi ở môi trường học tập. Trong code production, có thể đưa một abstraction quản lý `AutoCloseable` vào lớp chịu trách nhiệm lifecycle để truyền các fake chủ động ném lỗi. Không nên phụ thuộc vào lỗi ngẫu nhiên của hệ thống file để kiểm thử đường đi này.

## 9. Lỗi thường gặp khi quản lý tài nguyên trong manual DI

| Cách làm | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Service gọi `new` để mở kết nối và giữ riêng | Khởi tạo bị phân tán, khó biết nơi đóng | Chuyển tạo và sở hữu tài nguyên về composition root hoặc factory có hợp đồng rõ |
| Service nhận shared client rồi gọi `close()` sau mỗi request | Các service/request khác mất tài nguyên | Phân biệt borrowing và ownership |
| Khởi tạo nhiều resource liên tiếp, không có `catch` dọn dẹp | Rò rỉ khi bước giữa thất bại | Dọn những resource đã mở theo thứ tự ngược |
| `close()` đầu tiên ném lỗi nên bỏ qua các resource còn lại | Rò rỉ thêm tài nguyên | Cố đóng tất cả, dùng suppressed exception |
| Cấp request-scoped connection cho singleton service | Dùng lại connection đã đóng hoặc bị chia sẻ sai scope | Điều chỉnh thời gian sống hoặc factory cho từng request |
| Đóng pool trước khi tác vụ còn đang truy cập dữ liệu hoàn tất | Request thất bại trong shutdown | Dừng nhận việc và drain request trước khi đóng pool |
| Tự coi mọi `close()` đều idempotent | Đóng lặp có thể gây lỗi | Thiết kế hợp đồng đóng cụ thể |
| Giữ trạng thái mutable của request trong singleton | Race condition, lẫn dữ liệu giữa request | Scope phù hợp và hạn chế shared mutable state |
| Mở/đóng database connection cho từng thao tác bằng cách tạo mới cả pool | Chi phí rất lớn và có thể cạn tài nguyên | Dùng pool cấp ứng dụng, acquire/release connection ở scope tác vụ |
| Giả định mở file và ghi log là một transaction | Lưu đơn hàng thành công nhưng log thất bại | Có chiến lược nhất quán nghiệp vụ, retry hoặc outbox khi cần |

Đặc biệt, **vòng đời kỹ thuật không đồng nghĩa với tính nguyên tử nghiệp vụ**. Trong ví dụ, nếu `orders.save` đã hoàn thành nhưng `audit.record` thất bại, đơn hàng vẫn có thể đã được lưu. Dù graph được đóng đúng cách, ứng dụng vẫn cần cơ chế phù hợp để xử lý trạng thái này. DI giúp phân tách trách nhiệm và kiểm thử; nó không thay cho transaction.

## 10. Khi nào cần DI container và cần giữ lại kiến thức nào?

Một composition root viết tay đủ hiệu quả khi số lượng phụ thuộc vừa phải, cách cấu hình dễ theo dõi và phạm vi sống của các resource có thể biểu đạt trực tiếp. Mã `new` tập trung ở startup dễ tìm, dễ kiểm soát và không yêu cầu framework.

Khi hệ thống có nhiều module, nhiều hiện thực theo môi trường, nhiều scope hoặc quan hệ vòng đời phức tạp, DI container có thể hỗ trợ tạo object graph, phát hiện thiếu phụ thuộc, quản lý scope và gọi callback shutdown theo cơ chế riêng của từng framework.

Nhưng kể cả với container, bạn vẫn phải quyết định:

- Phụ thuộc nào là bắt buộc và đâu là abstraction hợp lý?
- Component nào là singleton, request-scoped hoặc transient?
- Ai sở hữu connection, pool và thread? Khi nào chúng phải đóng?
- Shutdown có đợi tác vụ hoàn thành không?
- Nếu khởi tạo thất bại giữa chừng, framework có cơ chế cleanup nào, và mã adapter của bạn cần đảm bảo điều gì?

**Framework tự động hóa lắp ghép, không tự hiểu quyền sở hữu và các điều kiện nghiệp vụ ngoài hợp đồng cấu hình.** Học quản lý vòng đời bằng Java thuần giúp đọc và cấu hình container đúng hơn.

## 11. Bài tập tự luyện

**Bài 1 — Bổ sung tài nguyên thứ ba.** Thêm một `FileMetricsSink` mở `metrics.log` vào `ApplicationGraph`. Điều chỉnh thứ tự mở và đóng. Nếu mở metrics thất bại, cần đóng những tài nguyên nào? Viết bảng liệt kê từng tình huống thất bại và những handle cần được giải phóng.

**Bài 2 — Mô phỏng lỗi đóng.** Tạo một `TrackedResource implements AutoCloseable` nhận tên và danh sách sự kiện. Khi gọi `close()`, resource ghi `closed:<name>` vào danh sách. Lắp hai resource bằng `try-with-resources` để chứng minh Java đóng từ phải sang trái. Cho resource đóng đầu tiên ném ngoại lệ, quan sát `getSuppressed()` khi một thao tác bên trong cũng ném lỗi.

**Bài 3 — Thiết kế scope.** Giả sử một dịch vụ xử lý 100 request đồng thời, trong đó connection pool sống suốt vòng đời ứng dụng còn mỗi request cần transaction riêng. Hãy vẽ nơi khởi tạo pool, nơi cấp/đóng connection, thời điểm commit/rollback và thứ tự graceful shutdown.

**Bài 4 — Phân tích ownership.** Hai service dùng chung một HTTP client do composition root cấp. Một service muốn đóng client trong phương thức `process()` để “tiết kiệm tài nguyên”. Hãy giải thích tại sao có thể sai và đề xuất cách quản lý vòng đời đúng.

Để tự kiểm tra, hãy lần theo một đối tượng từ lúc được tạo đến lúc đóng và trả lời: **Ai mở nó? Ai đang sử dụng nó? Ai có quyền đóng? Nếu khởi tạo dở dang thì ai dọn? Nếu đóng thất bại thì các tài nguyên còn lại ra sao?** Khi trả lời được các câu hỏi này, bạn đã thực hiện được phần quan trọng của **manual Dependency Injection**, trước khi chuyển sang DI container.
