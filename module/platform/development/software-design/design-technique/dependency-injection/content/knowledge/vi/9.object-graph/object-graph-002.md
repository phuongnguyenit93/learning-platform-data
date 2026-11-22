# Thứ tự xây dựng phụ thuộc và điều kiện hoàn tất khởi tạo

## 1. Object graph là gì và vì sao thứ tự khởi tạo quan trọng?

Trong **Dependency Injection (DI)**, một đối tượng nhận các phụ thuộc qua constructor hoặc phương thức, còn việc tạo và lắp ghép các đối tượng được tổ chức bên ngoài. Tập hợp các đối tượng và mối quan hệ phụ thuộc giữa chúng được gọi là **object graph** (đồ thị đối tượng).

Hãy xét một luồng nhận đơn hàng:

- `OrderController` tiếp nhận yêu cầu.
- `OrderService` thực hiện quy tắc nghiệp vụ.
- `OrderPolicy` kiểm tra điều kiện đơn hàng.
- `OrderStore` ghi dữ liệu.
- `AuditLog` ghi sự kiện.

`OrderController` không thể được tạo đúng hợp đồng nếu thiếu `OrderService`; `OrderService` lại cần `OrderPolicy`, `OrderStore` và `AuditLog`. Vì vậy, **thứ tự lắp ghép phải tuân theo các quan hệ phụ thuộc**: xây dựng đối tượng được cần đến trước khi truyền nó cho đối tượng sử dụng.

Bài này thuộc chương **Đồ thị đối tượng** của module **DEPENDENCY_INJECTION**. Mục tiêu là xây dựng đồ thị bằng Java thuần, biết khi nào việc khởi tạo được xem là hoàn tất, xử lý thất bại giữa chừng và xác định điểm sẵn sàng chuyển giao ứng dụng cho nơi sử dụng, trước khi cân nhắc tự động hóa bằng DI container.

**Một nguyên tắc cơ bản:** nếu `A` nhận `B` qua constructor, `B` phải có sẵn trước khi gọi constructor của `A`. Tuy nhiên, việc phụ thuộc đã được tạo xong **không đồng nghĩa** nó chắc chắn còn hoạt động tốt khi sử dụng về sau; đây là hai cam kết khác nhau.

## 2. Đọc đồ thị phụ thuộc: nút, cạnh, chiều mũi tên

Trong mô hình dùng ở bài này:

- **Nút** là một đối tượng hoặc thành phần cần khởi tạo.
- **Cạnh `A → B`** nghĩa là *A phụ thuộc vào B*, tức A cần B để được tạo hoặc thực hiện hành vi.
- **Đường đi phụ thuộc** biểu diễn các tầng phải được chuẩn bị trước khi có thể xây dựng đối tượng phía trên.

Ví dụ:

~~~mermaid
flowchart TB
    Controller["OrderController"] --> Service["OrderService"]
    Service --> Policy["OrderPolicy"]
    Service --> Store["FileOrderStore"]
    Service --> Audit["FileAuditLog"]
    Store --> WriterA["BufferedWriter: orders.csv"]
    Audit --> WriterB["BufferedWriter: events.log"]
~~~

Đồ thị dùng **chiều “bên sử dụng → bên được sử dụng”**. Do đó, khi diễn giải **thứ tự xây dựng**, ta đi từ các nút ở cuối đường phụ thuộc lên đầu: mở writer, xây adapter, tạo policy, tạo service và cuối cùng tạo controller.

Lưu ý rằng không phải mọi cặp nút đều có quan hệ thứ tự. Chẳng hạn `OrderPolicy` và `FileOrderStore` độc lập với nhau nên có thể được tạo theo bất kỳ thứ tự nào, miễn là cả hai tồn tại trước khi tạo `OrderService`.

Không nên nhầm **đồ thị phụ thuộc ở mức kiểu** với **các instance đang tồn tại**: cùng một interface `OrderStore` có thể được hiện thực bởi nhiều adapter, và cùng một instance có thể được chia sẻ cho nhiều service. Đồ thị lúc chạy cần phản ánh chính xác đối tượng **được tạo, chia sẻ và sở hữu vòng đời** nào.

## 3. Thứ tự hợp lệ là thứ tự topo, không nhất thiết là một danh sách cố định

Khi đồ thị có hướng **không chứa chu trình** (Directed Acyclic Graph – DAG), ta có thể xây dựng theo **thứ tự topo**: mỗi phụ thuộc trực tiếp phải được tạo trước thành phần sử dụng nó.

Với sơ đồ ở trên, một thứ tự hợp lệ là:

1. Xác thực cấu hình đầu vào và tạo `OrderPolicy`.
2. Mở writer cho `orders.csv`, tạo `FileOrderStore`.
3. Mở writer cho `events.log`, tạo `FileAuditLog`.
4. Tạo `OrderService` bằng cách truyền ba phụ thuộc đã có.
5. Tạo `OrderController` bằng cách truyền `OrderService`.
6. Trả về một `ApplicationGraph` hoàn chỉnh cho phần khởi động ứng dụng.

Nếu bước 2 và 3 đổi chỗ, thứ tự vẫn hợp lệ vì hai nhánh độc lập. Quan trọng là giữ đúng điều kiện **“phụ thuộc đã sẵn có trước khi gọi constructor cần nó”**.

~~~mermaid
flowchart LR
    Config["Cấu hình hợp lệ"] --> Policy["Policy"]
    Config --> Resources["Tài nguyên I/O"]
    Resources --> Adapters["Store + Audit"]
    Policy --> Service["OrderService"]
    Adapters --> Service
    Service --> Controller["OrderController"]
    Controller --> Graph["ApplicationGraph được công bố"]
~~~

Thuật toán sắp xếp topo thường xuất hiện trong công cụ build, scheduler hoặc DI container. Trong **lắp ghép thủ công**, bạn không cần tự viết thuật toán: trình tự những lệnh `new` tại composition root đã biểu diễn thứ tự xây dựng. Khi hệ thống tăng quy mô, sơ đồ và cấu trúc hàm factory giúp người đọc kiểm tra thứ tự này.

### Hai lỗi xuất hiện khi bỏ qua đồ thị

**Thiếu phụ thuộc:** constructor nhận `null` hoặc một tham chiếu chưa hợp lệ chỉ để vượt qua lỗi biên dịch. Lỗi thật có thể chuyển từ lúc khởi động sang lúc xử lý request.

**Tạo trùng thành phần dùng chung:** hai nhánh tự tạo hai client hoặc hai pool riêng mặc dù cấu hình yêu cầu dùng một instance chung. Đồ thị vẫn có thể xây dựng được nhưng tốn tài nguyên, gây lệch cache hoặc làm phân tán trạng thái.

Vì vậy, thứ tự topo là **điều kiện cần cho việc lắp ghép**, còn việc chọn đúng instance và scope là quyết định bổ sung.

## 4. Khi nào một đối tượng, một đồ thị và ứng dụng được xem là “đã khởi tạo xong”?

Ba mức độ “hoàn tất” cần phân biệt:

| Mức độ | Điều kiện hoàn tất | Điều **chưa** được bảo đảm |
| --- | --- | --- |
| **Một đối tượng** | Constructor hoặc factory trả về thành công; các bất biến nội bộ được kiểm tra | Hệ thống bên ngoài sẽ không lỗi trong tương lai |
| **Object graph** | Mọi phụ thuộc bắt buộc đã được cấp; entry point được tạo; tài nguyên do graph sở hữu có kế hoạch dọn dẹp; không có đối tượng chưa lắp xong bị công bố | Hệ thống chắc chắn đủ điều kiện nhận lưu lượng thực tế |
| **Ứng dụng sẵn sàng phục vụ** | Ngoài graph hoàn chỉnh, các điều kiện startup thực sự cần thiết đã đạt (ví dụ cấu hình, schema, khả năng truy cập tài nguyên theo yêu cầu) | Mọi request sau này đều thành công |

Ở mức đối tượng, constructor nên **fail fast** nếu thiếu phụ thuộc bắt buộc:

~~~java
this.store = java.util.Objects.requireNonNull(store, "store");
this.policy = java.util.Objects.requireNonNull(policy, "policy");
~~~

Ở mức graph, một factory nên **chỉ trả kết quả sau khi toàn bộ nhánh bắt buộc đã lắp thành công**. Không cho một module khác lấy nửa đồ thị rồi tiếp tục cấu hình bằng setter tùy ý. Nếu resource đã mở mà một bước sau thất bại, graph chưa hoàn tất và tài nguyên mở trước đó phải được đóng.

Ở mức ứng dụng, trạng thái “đã khởi tạo object graph” và **readiness** là hai khái niệm riêng. Ví dụ, việc tạo một HTTP client xong không chứng minh endpoint còn sống trong lần request kế tiếp. Một bước kiểm tra kết nối lúc startup có thể hữu ích nếu ứng dụng **thật sự phải dừng khởi động khi phụ thuộc ngoài chưa sẵn sàng**, nhưng sức khỏe của mạng vẫn có thể thay đổi sau kiểm tra. Không nên đưa toàn bộ I/O và retry phức tạp vào mọi constructor.

### Tránh công bố đối tượng chưa xây dựng xong

Không gọi phương thức của lớp khác có thể giữ tham chiếu đến `this` từ bên trong constructor trước khi invariant hoàn thành, không đăng ký callback chạy ngay hoặc khởi động thread nắm `this` quá sớm. Cách làm này có thể khiến mã khác quan sát trạng thái chưa hoàn thiện.

Một factory tĩnh là công cụ tốt khi cần nhiều bước tạo object graph:

~~~java
ApplicationGraph graph = ApplicationGraph.start(config);
// Chỉ tới đây caller mới nhận được graph đã được lắp ghép thành công.
~~~

Bảo vệ việc công bố hoàn chỉnh cũng liên quan đến đa luồng: nếu một graph được chia sẻ giữa các thread, ứng dụng vẫn phải sử dụng cơ chế **safe publication** phù hợp. Các field `final` và constructor đúng cách giúp bảo vệ trạng thái khởi tạo, nhưng không làm cho mọi trạng thái mutable và việc đóng tài nguyên trở nên thread-safe.

## 5. Ví dụ đầy đủ: xây dựng đồ thị bằng Java thuần

Ví dụ dùng **Java 11 trở lên** và không cần Spring hoặc container. Hai adapter ghi vào file; `OrderPolicy` kiểm tra dữ liệu; `OrderService` triển khai nghiệp vụ; `OrderController` là điểm gọi từ phía ngoài. `ApplicationGraph` đóng vai trò composition root và quản lý vòng đời tài nguyên.

Lưu toàn bộ đoạn sau thành `ObjectGraphDemo.java`:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.Objects;

public final class ObjectGraphDemo {
    public interface OrderStore {
        void save(String orderId, long amountVnd) throws IOException;
    }

    public interface AuditLog {
        void record(String event) throws IOException;
    }

    // Node độc lập: policy thuần túy và bất biến.
    public static final class OrderPolicy {
        private final long minimumVnd;

        public OrderPolicy(long minimumVnd) {
            if (minimumVnd <= 0) {
                throw new IllegalArgumentException("minimumVnd phải dương");
            }
            this.minimumVnd = minimumVnd;
        }

        public void validate(String orderId, long amountVnd) {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("Mã đơn không hợp lệ");
            }
            if (amountVnd < minimumVnd) {
                throw new IllegalArgumentException("Số tiền dưới mức tối thiểu");
            }
        }
    }

    // Adapter sở hữu BufferedWriter, đồng thời hiện thực OrderStore.
    public static final class FileOrderStore
            implements OrderStore, AutoCloseable {
        private final BufferedWriter writer;

        public FileOrderStore(Path file) throws IOException {
            writer = Files.newBufferedWriter(
                    Objects.requireNonNull(file, "file"),
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

        public FileAuditLog(Path file) throws IOException {
            writer = Files.newBufferedWriter(
                    Objects.requireNonNull(file, "file"),
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
        private final OrderPolicy policy;
        private final OrderStore store;
        private final AuditLog audit;

        public OrderService(OrderPolicy policy, OrderStore store, AuditLog audit) {
            this.policy = Objects.requireNonNull(policy, "policy");
            this.store = Objects.requireNonNull(store, "store");
            this.audit = Objects.requireNonNull(audit, "audit");
        }

        public void placeOrder(String orderId, long amountVnd)
                throws IOException {
            policy.validate(orderId, amountVnd);
            store.save(orderId, amountVnd);
            audit.record("ORDER_SAVED:" + orderId);
        }
    }

    public static final class OrderController {
        private final OrderService service;

        public OrderController(OrderService service) {
            this.service = Objects.requireNonNull(service, "service");
        }

        public void submit(String orderId, long amountVnd) throws IOException {
            service.placeOrder(orderId, amountVnd);
        }
    }

    // Điểm lắp ghép đồng thời là nơi sở hữu tài nguyên cấp ứng dụng.
    public static final class ApplicationGraph implements AutoCloseable {
        private final FileOrderStore store;
        private final FileAuditLog audit;
        private final OrderController controller;
        private boolean closed;

        private ApplicationGraph(
                FileOrderStore store,
                FileAuditLog audit,
                OrderController controller) {
            this.store = store;
            this.audit = audit;
            this.controller = controller;
        }

        public static ApplicationGraph start(Path directory, long minimumVnd)
                throws IOException {
            Objects.requireNonNull(directory, "directory");

            // 1. Kiểm tra quy tắc cấu hình trước khi mở tài nguyên.
            OrderPolicy policy = new OrderPolicy(minimumVnd);
            Files.createDirectories(directory);

            FileOrderStore store = null;
            FileAuditLog audit = null;

            try {
                // 2. Tạo hai nhánh I/O độc lập của object graph.
                store = new FileOrderStore(directory.resolve("orders.csv"));
                audit = new FileAuditLog(directory.resolve("events.log"));

                // 3. Lắp các nút phía trên từ phụ thuộc đã hoàn chỉnh.
                OrderService service = new OrderService(policy, store, audit);
                OrderController controller = new OrderController(service);

                // 4. Chỉ công bố graph khi tất cả bước bắt buộc thành công.
                return new ApplicationGraph(store, audit, controller);
            } catch (IOException | RuntimeException failure) {
                // Nếu khởi tạo một phần thất bại, thu hồi resource đã mở.
                closeAfterFailure(audit, failure);
                closeAfterFailure(store, failure);
                throw failure;
            }
        }

        private static void closeAfterFailure(
                AutoCloseable resource, Exception originalFailure) {
            if (resource == null) {
                return;
            }
            try {
                resource.close();
            } catch (Exception closeFailure) {
                originalFailure.addSuppressed(closeFailure);
            }
        }

        public OrderController controller() {
            if (closed) {
                throw new IllegalStateException("Graph đã đóng");
            }
            return controller;
        }

        @Override
        public void close() throws IOException {
            if (closed) {
                return;
            }
            closed = true;

            IOException firstFailure = null;

            // Đóng theo thứ tự ngược với thứ tự đã mở.
            try {
                audit.close();
            } catch (IOException failure) {
                firstFailure = failure;
            }

            try {
                store.close();
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
        Path directory = Paths.get("object-graph-output");

        // Điểm khởi động chỉ nhận graph hoàn chỉnh.
        try (ApplicationGraph graph = ApplicationGraph.start(directory, 1_000)) {
            graph.controller().submit("ORDER-001", 15_000);
            graph.controller().submit("ORDER-002", 20_000);
        }
    }
}
~~~

Chạy:

~~~bash
javac ObjectGraphDemo.java
java ObjectGraphDemo
~~~

Sau khi thực thi thành công:

~~~text
object-graph-output/
├── orders.csv
└── events.log
~~~

`orders.csv` có thêm hai dòng:

~~~text
ORDER-001,15000
ORDER-002,20000
~~~

`events.log` có thêm:

~~~text
ORDER_SAVED:ORDER-001
ORDER_SAVED:ORDER-002
~~~

Ví dụ dùng chế độ `APPEND` nên chạy lại sẽ **ghi thêm** hai dòng vào mỗi file. Dữ liệu và tên file chỉ để minh họa object graph và vòng đời; việc ghi hai file **không tạo ra transaction nguyên tử**. Nếu lưu đơn thành công nhưng ghi audit thất bại, phải xử lý tính nhất quán nghiệp vụ bằng một cơ chế phù hợp (ví dụ transaction trên cùng hệ quản trị, retry hoặc outbox).

### Đọc lại đúng thứ tự xây dựng trong code

| Bước | Nút/nhóm nút | Điều kiện cần trước đó |
| --- | --- | --- |
| 1 | `OrderPolicy` | Cấu hình `minimumVnd` hợp lệ |
| 2 | `FileOrderStore` | Thư mục đầu ra tồn tại, mở writer thành công |
| 3 | `FileAuditLog` | Thư mục đầu ra tồn tại, mở writer thành công |
| 4 | `OrderService` | Policy, store, audit đã được tạo |
| 5 | `OrderController` | Service đã được tạo |
| 6 | `ApplicationGraph` | Tất cả node bắt buộc và tài nguyên sở hữu đã có |
| 7 | `main` gọi controller | Graph đã được trả về thành công |

Các dòng `new OrderService(...)` và `new OrderController(...)` là constructor injection. `ApplicationGraph.start(...)` quyết định cách tạo và lắp ghép đối tượng: **Inversion of Control ở ranh giới khởi tạo**, không cần framework.

## 6. Khởi tạo thành công một phần chưa phải graph hoàn chỉnh

Hãy xem hai đường đi khác nhau:

**Đường đi thành công:** policy hợp lệ → mở store → mở audit → tạo service → tạo controller → trả graph → xử lý đơn → đóng graph.

**Đường đi thất bại:** policy hợp lệ → mở store → không mở được audit → đóng store → ném ngoại lệ → không trả graph.

Khi constructor hoặc factory của một node ném ngoại lệ, các node đã được tạo trước **không tự biến mất theo nghĩa giải phóng tài nguyên**. Bộ gom rác có thể thu hồi bộ nhớ khi không còn tham chiếu, nhưng không phải cơ chế đủ tin cậy để đóng file, socket hoặc pool đúng lúc.

~~~mermaid
flowchart TD
    Start["Bắt đầu build graph"] --> Validate{"Cấu hình hợp lệ?"}
    Validate -->|Không| Fail["Ném lỗi, không tạo graph"]
    Validate -->|Có| OpenA["Mở store"]
    OpenA --> OpenB{"Mở audit thành công?"}
    OpenB -->|Không| Cleanup["Đóng store, giữ lỗi gốc"]
    Cleanup --> Fail
    OpenB -->|Có| Service["Tạo service và controller"]
    Service --> Publish["Trả ApplicationGraph hoàn chỉnh"]
    Publish --> Run["Phục vụ tác vụ"]
    Run --> Stop["Dừng sử dụng và đóng graph"]
~~~

Trong Java, `try-with-resources` ở `main` giúp đóng **graph đã tạo thành công**; nó không thể đóng một graph chưa bao giờ được trả về. Vì vậy, factory `start(...)` cũng cần nhánh dọn dẹp những tài nguyên đã mở nếu một bước phía sau thất bại.

Trong ví dụ:

- `catch (IOException | RuntimeException failure)` giữ lại lỗi gốc.
- `closeAfterFailure(...)` cố đóng các tài nguyên đã tạo, theo thứ tự ngược.
- Nếu đóng cũng thất bại, lỗi đóng được lưu bằng `addSuppressed(...)` thay vì che mất lỗi khởi tạo.
- `ApplicationGraph.close()` cũng cố đóng cả hai resource dù bước đóng đầu tiên ném lỗi.

Phạm vi `catch` trong ví dụ xử lý lỗi I/O và lỗi runtime thông thường; các lỗi `Error` nghiêm trọng của JVM được đặt ngoài cơ chế dọn dẹp này. Ở sản phẩm thực tế, cần đối chiếu với loại tài nguyên và yêu cầu vận hành để xây dựng lifecycle manager thích hợp.

## 7. Dependency cycle: không có thứ tự khởi tạo constructor hợp lệ

Đồ thị đơn giản có chu trình:

~~~mermaid
flowchart LR
    A["ServiceA"] -->|"constructor cần"| B["ServiceB"]
    B -->|"constructor cần"| A
~~~

Giả sử:

~~~java
final class ServiceA {
    ServiceA(ServiceB b) { }
}
final class ServiceB {
    ServiceB(ServiceA a) { }
}
~~~

Muốn tạo `ServiceA` phải có `ServiceB`; muốn tạo `ServiceB` lại phải có `ServiceA`. Không có thứ tự topo để cấp hai phụ thuộc bắt buộc này bằng constructor thông thường mà không đưa vào một tham chiếu giả hoặc trạng thái chưa hoàn thiện.

Đây không phải là lý do để tự động truyền `null` rồi setter lại sau. Cách đó khiến mỗi instance có khoảng thời gian chưa hợp lệ, gây khó kiểm thử và có nguy cơ để lộ một phần graph.

Các hướng xử lý có thể cân nhắc:

1. **Xem lại trách nhiệm:** hai service có thể đang gọi ngược nhau vì phân tách trách nhiệm chưa hợp lý.
2. **Tách một abstraction chung:** đưa hợp đồng hoặc chức năng được chia sẻ sang thành phần thứ ba, giảm phụ thuộc hai chiều.
3. **Chuyển thành luồng điều phối một chiều:** một coordinator gọi A và B thay vì A/B gọi vòng.
4. **Dùng sự kiện hoặc callback có vòng đời rõ ràng** khi thật sự có tương tác ngược mà không cần tham chiếu hai chiều trực tiếp.

`Supplier<T>`, provider hoặc lazy initialization có thể trì hoãn thời điểm lấy phụ thuộc, nhưng **không tự giải quyết lỗi thiết kế**: nó chỉ thay đổi thời gian cần một đối tượng. Phải phân biệt một chu trình constructor thật với nhu cầu phụ thuộc ở thời điểm runtime có thể được mô hình hóa khác.

## 8. Object graph và scope: tạo một lần hay nhiều lần?

Thứ tự xây dựng chỉ xác định **ai cần ai trước**; scope xác định **bao nhiêu instance được tạo và được dùng chung cho ai**.

| Scope | Cách lắp ghép | Lưu ý |
| --- | --- | --- |
| Theo ứng dụng | Tạo một graph hoặc một nhóm resource ở startup, chia sẻ cho nhiều service | Cần bảo đảm thread safety và shutdown theo thứ tự |
| Theo request | Mỗi request tạo một nhóm đối tượng có trạng thái riêng | Không giữ tham chiếu đến resource hết hạn sau request |
| Theo tác vụ | Một job tạo và sở hữu tài nguyên cho đến khi job kết thúc | Sử dụng `try-with-resources` khi phù hợp |
| Transient | Tạo instance mới mỗi lần cần | Không vô tình nhân bản pool hoặc client đắt tiền |

Ví dụ, `OrderPolicy` trong đoạn code là immutable và có thể chia sẻ. Hai writer file được mở cho graph và sống đến khi graph đóng. Nếu mở rộng mã thành server xử lý đồng thời, **không được mặc định việc chia sẻ hai `BufferedWriter` là an toàn**: phải đồng bộ, dùng cơ chế ghi tuần tự phù hợp hoặc thay bằng giải pháp lưu trữ được thiết kế cho concurrency.

Một lỗi scope thường gặp là tạo service cấp ứng dụng nhưng tiêm một dependency thuộc request. Khi request đã kết thúc, service vẫn giữ reference tới resource đã đóng. Trật tự topo lúc tạo có thể hoàn toàn đúng nhưng vòng đời vẫn sai.

### Tại sao một graph hoàn chỉnh vẫn có thể bị dùng sai?

Ngay sau `graph.controller()`, caller có thể giữ `OrderController` lâu hơn vòng đời của `ApplicationGraph`. Ví dụ kiểm tra `closed` trong accessor chỉ ngăn **lấy controller mới** khi graph đã đóng; nó không thể thu hồi các tham chiếu đã được truyền đi. Khi shutdown, hệ thống phải ngừng nhận tác vụ và đợi tác vụ đang chạy hoàn tất trước khi đóng resource. Đây là yêu cầu điều phối vòng đời, không giải quyết được chỉ bằng constructor.

## 9. Kiểm thử thứ tự lắp ghép và trạng thái hoàn tất mà không cần DI container

Unit test của logic nghiệp vụ không cần mở file. Ta có thể thay `OrderStore` và `AuditLog` bằng các đối tượng in-memory, kiểm tra rằng một `OrderService` được tạo từ những phụ thuộc hợp lệ hoạt động đúng.

Test lắp ghép ở mức cao hơn nên kiểm tra:

- Graph được trả khi toàn bộ nhánh bắt buộc khởi tạo thành công.
- Cấu hình không hợp lệ bị từ chối sớm.
- Nếu một node I/O khởi tạo thất bại sau node khác, lỗi lan ra caller và graph không được trả.
- Resource cấp ứng dụng được đóng khi sử dụng xong.
- Hai nhánh độc lập được lắp vào đúng service và không bị tạo thừa.

Tạo `ObjectGraphDemoTest.java` trong cùng thư mục:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class ObjectGraphDemoTest {
    static final class MemoryStore implements ObjectGraphDemo.OrderStore {
        int calls;
        String lastOrder;

        @Override
        public void save(String orderId, long amountVnd) {
            calls++;
            lastOrder = orderId;
        }
    }

    static final class MemoryAudit implements ObjectGraphDemo.AuditLog {
        int calls;

        @Override
        public void record(String event) {
            calls++;
        }
    }

    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    static void testServiceWithInjectedDependencies() throws IOException {
        MemoryStore store = new MemoryStore();
        MemoryAudit audit = new MemoryAudit();
        ObjectGraphDemo.OrderPolicy policy =
                new ObjectGraphDemo.OrderPolicy(1_000);
        ObjectGraphDemo.OrderService service =
                new ObjectGraphDemo.OrderService(policy, store, audit);

        service.placeOrder("ORDER-010", 3_000);
        check(store.calls == 1, "Phải lưu đúng một đơn");
        check("ORDER-010".equals(store.lastOrder), "Sai mã đơn");
        check(audit.calls == 1, "Phải có một sự kiện audit");

        try {
            service.placeOrder("sai định dạng", 3_000);
            throw new AssertionError("Dữ liệu không hợp lệ phải bị từ chối");
        } catch (IllegalArgumentException expected) {
            check(store.calls == 1, "Không được lưu đơn sai");
            check(audit.calls == 1, "Không được audit đơn sai");
        }
    }

    static void testCompleteGraph() throws IOException {
        Path dir = Files.createTempDirectory("object-graph-ok-");
        try {
            try (ObjectGraphDemo.ApplicationGraph graph =
                    ObjectGraphDemo.ApplicationGraph.start(dir, 1_000)) {
                graph.controller().submit("ORDER-020", 5_000);
            }

            List<String> orders = Files.readAllLines(
                    dir.resolve("orders.csv"), StandardCharsets.UTF_8);
            List<String> audit = Files.readAllLines(
                    dir.resolve("events.log"), StandardCharsets.UTF_8);

            check(orders.size() == 1, "Phải có đúng một đơn");
            check("ORDER-020,5000".equals(orders.get(0)), "Sai nội dung");
            check(audit.size() == 1, "Phải có đúng một sự kiện");
        } finally {
            Files.deleteIfExists(dir.resolve("orders.csv"));
            Files.deleteIfExists(dir.resolve("events.log"));
            Files.deleteIfExists(dir);
        }
    }

    static void testFailureDuringBuild() throws IOException {
        Path dir = Files.createTempDirectory("object-graph-fail-");
        try {
            // Đường dẫn dự kiến dành cho file audit đã là thư mục.
            // Store được mở trước; mở audit sẽ thất bại.
            Files.createDirectory(dir.resolve("events.log"));

            boolean failed = false;
            try {
                ObjectGraphDemo.ApplicationGraph.start(dir, 1_000);
            } catch (IOException expected) {
                failed = true;
            }
            check(failed, "Khởi tạo graph phải thất bại");

            // Bài test kiểm tra đường lỗi và dọn thư mục sau thử nghiệm.
            // Việc close tài nguyên nên được kiểm chứng chuyên biệt
            // bằng resource giả có bộ đếm close trong bộ test lifecycle.
        } finally {
            Files.deleteIfExists(dir.resolve("orders.csv"));
            Files.deleteIfExists(dir.resolve("events.log"));
            Files.deleteIfExists(dir);
        }
    }

    public static void main(String[] args) throws IOException {
        testServiceWithInjectedDependencies();
        testCompleteGraph();
        testFailureDuringBuild();
        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ObjectGraphDemo.java ObjectGraphDemoTest.java
java ObjectGraphDemoTest
~~~

Đường thất bại mô phỏng việc mở file audit khi tên đường dẫn đã thuộc về một thư mục. Đó là một lỗi I/O có chủ ý, để kiểm tra factory không trả về graph nửa vời. Bài test này chưa đo trực tiếp số lần gọi `close()`. Muốn kiểm tra **thứ tự đóng, gọi đúng một lần, vẫn đóng các tài nguyên còn lại khi một lần đóng ném lỗi**, hãy tiêm các resource giả có khả năng ghi lại lifecycle event vào một thành phần quản lý tài nguyên chuyên biệt, thay vì phụ thuộc vào hành vi khóa file khác nhau giữa hệ điều hành.

## 10. Các sai lầm thường gặp khi xây dựng object graph

| Sai lầm | Biểu hiện | Hướng giải quyết |
| --- | --- | --- |
| Tạo service trước khi có phụ thuộc bắt buộc | Dùng `null`, setter chắp vá, lỗi xuất hiện ở request đầu tiên | Xây theo thứ tự topo, fail fast tại constructor |
| Mỗi service tự `new` dependency dùng chung | Tạo trùng pool/client/cache hoặc mâu thuẫn cấu hình | Tập trung lắp ghép tại composition root |
| Cho graph chạy khi factory vẫn cấu hình nửa chừng | Request thấy trạng thái chưa hoàn tất | Chỉ công bố graph sau khi lắp đủ các nút bắt buộc |
| Constructor khởi động thread và truyền `this` ra ngoài | Thread có thể nhìn thấy trạng thái chưa ổn định | Tách xây dựng khỏi khởi chạy; công bố an toàn sau khi hoàn tất |
| Phụ thuộc vòng giữa constructor | Không có thứ tự khởi tạo hợp lệ | Xem lại trách nhiệm, dùng coordinator hoặc tách thành phần |
| Bỏ qua cleanup nếu bước khởi tạo sau thất bại | Rò rỉ file, socket hoặc connection | Dùng factory dọn tài nguyên đã tạo, suppressed exceptions |
| Đồng nhất “graph dựng xong” với “mọi hệ thống ngoài khỏe mạnh” | Readiness báo sai, lỗi network vẫn xảy ra | Định nghĩa startup/readiness riêng và xử lý lỗi runtime |
| Giữ request resource trong singleton | Truy cập tài nguyên đã đóng hoặc dữ liệu request khác | Căn chỉnh scope và ownership |
| Đóng resource khi còn request đang chạy | Lỗi giữa tác vụ, ghi dữ liệu dở dang | Ngừng nhận việc, chờ tác vụ kết thúc, rồi đóng theo quan hệ phụ thuộc |
| Không thể giải thích ai tạo và đóng mỗi instance | Khó debug và thay adapter trong test | Ghi nhận object graph và chính sách vòng đời |

## 11. Thực hành và câu hỏi tự đánh giá

**Bài tập 1 — Vẽ đồ thị phụ thuộc.** Cho `InvoiceController` cần `InvoiceService`. Service cần `InvoiceRepository` và `TaxCalculator`. Repository cần `DataSource`. Vẽ mũi tên theo quy ước “bên sử dụng → phụ thuộc”, xác định hai thứ tự xây dựng hợp lệ và giải thích tại sao có thể thay đổi vị trí `TaxCalculator`.

**Bài tập 2 — Tìm lỗi vòng phụ thuộc.** `EmailService` nhận `UserService` qua constructor; `UserService` lại nhận `EmailService`. Thiết kế một `UserRegistrationCoordinator` hoặc cơ chế phát sự kiện để giảm phụ thuộc hai chiều. Nêu thứ tự xây dựng mới.

**Bài tập 3 — Khởi tạo một phần thất bại.** Mở ba tài nguyên A, B, C liên tiếp. Giả sử C ném lỗi; B đóng cũng ném lỗi. Thiết kế luồng cleanup bảo đảm tiếp tục đóng A, giữ ngoại lệ khởi tạo C là nguyên nhân chính và ghi lỗi đóng B qua `addSuppressed()`.

**Bài tập 4 — Readiness khác construction.** Graph đã tạo được một HTTP client, nhưng endpoint của đối tác đang ngừng phục vụ. Xác định trường hợp nào nên dừng ứng dụng khi startup, trường hợp nào nên khởi động rồi dùng retry/circuit breaker. Mô tả rõ điều kiện readiness bạn muốn cam kết.

**Bài tập 5 — Scope và shutdown.** Một singleton `ReportService` nhận một client chia sẻ và một transaction chỉ sống theo request. Chỉ ra điểm bất hợp lý, sửa lại quan hệ phụ thuộc và mô tả thứ tự dừng nhận request, chờ xử lý và đóng resource.

Ba câu hỏi cần trả lời khi kiểm tra một object graph là: **(1) Nút nào cần được dựng trước nút nào? (2) Khi factory trả về, các bất biến và phụ thuộc bắt buộc đã hoàn tất chưa? (3) Nếu bất kỳ bước nào thất bại hoặc ứng dụng kết thúc, ai đóng các tài nguyên đã tạo?** Khi hiểu ba câu hỏi này bằng Java thuần, bạn có nền tảng để sử dụng DI container một cách chủ động thay vì dựa vào container để che giấu các quyết định thiết kế.
