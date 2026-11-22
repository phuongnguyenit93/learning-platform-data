# Điểm lắp ghép (Composition Root) và vị trí trong kiến trúc ứng dụng

## 1. Composition Root là gì?

**Composition Root** (điểm lắp ghép) là nơi ứng dụng **tạo, cấu hình và nối các đối tượng** thành một đồ thị phụ thuộc (object graph) hoàn chỉnh trước khi chuyển quyền điều khiển cho luồng xử lý chính.

Trong **Dependency Injection (DI)**, lớp nghiệp vụ nhận các cộng tác viên (dependency) từ bên ngoài, thường qua constructor. Composition Root là phía **cung cấp** những dependency đó: nó quyết định dùng implementation nào, khởi tạo theo thứ tự nào, đối tượng nào được chia sẻ và tài nguyên nào phải được đóng. Việc chuyển quyết định này ra ngoài lớp nghiệp vụ là một ứng dụng cụ thể của **Inversion of Control (IoC)**.

Ví dụ, `OrderService` cần `OrderRepository` để lưu đơn hàng và `ReceiptSender` để gửi xác nhận. Lớp nghiệp vụ chỉ cần sử dụng hai hợp đồng đó; Composition Root có thể lựa chọn bộ nhớ trong một chương trình minh họa, database và dịch vụ gửi email ở môi trường thật, hoặc fake trong bài kiểm thử.

```text
                  COMPOSITION ROOT
                (điểm khởi động)
                         |
            tạo, chọn, kết nối, quản lý
                         |
             +-----------+-------------+
             |                         |
             v                         v
       Repository adapter        Sender adapter
             |                         |
             | implements              | implements
             v                         v
       OrderRepository           ReceiptSender
             ^                         ^
             | dùng                    | dùng
             +-----------+-------------+
                         |
                    OrderService
                         ^
                         | sử dụng
                  Entry point / UI
```

**Không nên hiểu Composition Root là một “lớp siêu lớn” chứa mọi logic ứng dụng.** Nó là một ranh giới trách nhiệm: giữ quyết định về lắp ghép ở sát điểm khởi động, còn hành vi nghiệp vụ vẫn nằm trong những thành phần chuyên trách.

Sau bài này, bạn sẽ có thể:

- Xác định Composition Root đặt ở đâu trong ứng dụng CLI, web, batch job và kiểm thử.
- Tách **phần sử dụng dependency** khỏi **phần tạo và lắp ghép dependency** bằng Java thuần.
- Nhìn theo chiều phụ thuộc của mã nguồn để tránh để nghiệp vụ biết về database, framework hoặc DI container.
- Quản lý lựa chọn triển khai, scope và vòng đời tài nguyên tại ranh giới lắp ghép.
- Nhận diện các lỗi thường gặp như tạo dependency rải rác, Service Locator và dùng sai scope.

## 2. Composition Root nằm ở vị trí nào trong kiến trúc?

Điểm lắp ghép thường nằm **gần điểm vào (entry point)** của tiến trình, nơi ứng dụng có đủ thông tin cấu hình và có quyền tạo các adapter hạ tầng. Vị trí chính xác phụ thuộc vào kiểu ứng dụng.

| Kiểu ứng dụng | Vị trí Composition Root thường gặp | Việc cần thực hiện |
| --- | --- | --- |
| Chương trình Java CLI | `main(...)` hoặc hàm bootstrap được `main` gọi | Đọc cấu hình, tạo adapter, tạo service, chạy lệnh và đóng tài nguyên. |
| Web application | Bootstrap khi khởi động ứng dụng, cấu hình ứng dụng hoặc vùng cấu hình DI container | Tạo thành phần dùng chung, đăng ký controller/handler, cấu hình dependency và scope theo request. |
| Background worker / batch job | Điểm khởi động worker/job | Tạo client, repository, processor; quản lý tài nguyên và vòng đời từng job. |
| Ứng dụng desktop | Điểm khởi động UI hoặc thành phần bootstrap | Lắp service và adapter trước khi đăng ký event handler, tạo các thành phần UI theo vòng đời thích hợp. |
| Bài kiểm thử | Setup/test fixture hoặc ngay đầu mỗi bài test | Tạo đồ thị nhỏ, truyền fake/stub, cấu hình kiểm thử độc lập với môi trường thật. |

Một tiến trình thường có **một ranh giới lắp ghép chính ở điểm khởi động**, nhưng không bắt buộc tất cả thao tác `new` nằm trong một phương thức hay một file. Composition Root có thể ủy quyền cho factory hoặc các hàm cấu hình có trách nhiệm rõ ràng. Với nhiều executable (API server, CLI và worker chạy riêng), mỗi executable có thể cần Composition Root của riêng mình.

### 2.1. Vị trí trong kiến trúc phân lớp

Xét kiến trúc ứng dụng có ba nhóm thành phần:

- **Nghiệp vụ/application layer**: `OrderService`, các quy tắc xử lý đơn hàng và các hợp đồng cần dùng.
- **Adapter/hạ tầng**: implementation gọi database, HTTP, email, message broker hoặc lưu trong bộ nhớ.
- **Bootstrap/Composition Root**: chọn implementation rồi ghép chúng để phục vụ entry point.

```text
                         LÚC KHỞI ĐỘNG
                  Composition Root / Bootstrap
                     |             |
                     v             v
               Web/CLI adapter   Infrastructure adapters
                     |             |
                     v             | implements
                 OrderService      |
                     |             |
                     v             v
                 OrderRepository, ReceiptSender
                   (hợp đồng ứng dụng)
```

Ở **thời điểm chạy**, lời gọi có thể đi từ controller sang service rồi tới adapter database. Tuy nhiên, **phụ thuộc mã nguồn (compile-time dependency)** có thể hướng từ service tới những interface độc lập với hạ tầng, còn adapter triển khai các interface đó. Composition Root biết cả hai phía để nối chúng lại.

Điều này hỗ trợ **Dependency Inversion Principle (DIP)**: mã nghiệp vụ không cần nhập trực tiếp lớp `JdbcOrderRepository` hoặc `SmtpReceiptSender`. Composition Root được phép biết những implementation cụ thể; đó chính là trách nhiệm của nó.

### 2.2. Không đặt điểm lắp ghép ở mọi nơi gọi `new`

Đôi khi người học hiểu nhầm rằng cứ gọi `new` là đang tạo một Composition Root. Thực tế, tạo `new Order(...)` hoặc `new ArrayList<>()` trong nghiệp vụ thường chỉ là tạo **đối tượng giá trị hoặc dữ liệu nội bộ**. Composition Root chủ yếu xử lý các **cộng tác viên có thể thay đổi**, đối tượng cần cấu hình, phụ thuộc hạ tầng và tài nguyên có vòng đời rõ ràng.

Nếu controller, service và repository đều tự tạo HTTP client, logger, database adapter của riêng mình, ứng dụng có nhiều **điểm quyết định phụ thuộc phân tán**; những điểm ấy không nên được coi là các Composition Root ngang hàng.

## 3. Ví dụ thực hành: một Composition Root bằng Java thuần

Ta xây ứng dụng nhỏ xác nhận đơn hàng:

1. `ConsoleOrderController` nhận yêu cầu.
2. `OrderService` xác nhận đơn và điều phối hai dependency.
3. `OrderRepository` lưu đơn.
4. `ReceiptSender` thông báo xác nhận.
5. `App.main` tạo và lắp ghép toàn bộ đồ thị đối tượng.

### 3.1. Chỉ định hợp đồng, tách khỏi chi tiết hạ tầng

Lưu toàn bộ mã sau vào `App.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

// Đối tượng dữ liệu: có thể tạo trực tiếp bên trong nghiệp vụ.
final class Order {
    final String id;
    final long amountVnd;

    Order(String id, long amountVnd) {
        this.id = id;
        this.amountVnd = amountVnd;
    }
}

// Các hợp đồng nằm ở ranh giới ứng dụng.
interface OrderRepository {
    void save(Order order);
}

interface ReceiptSender {
    void sendConfirmation(Order order);
}

// Logic điều phối không biết repository/sender cụ thể.
final class OrderService {
    private final OrderRepository repository;
    private final ReceiptSender sender;

    OrderService(OrderRepository repository, ReceiptSender sender) {
        this.repository = Objects.requireNonNull(repository, "repository");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void confirm(String orderId, long amountVnd) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("Mã đơn không hợp lệ");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        Order order = new Order(orderId, amountVnd);
        repository.save(order);
        sender.sendConfirmation(order);
    }
}

// Adapter minh họa: chỉ lưu trong bộ nhớ, không phải database thật.
final class InMemoryOrderRepository implements OrderRepository {
    private final List<Order> savedOrders = new ArrayList<>();

    @Override
    public void save(Order order) {
        savedOrders.add(order);
    }
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void sendConfirmation(Order order) {
        System.out.println("Đã gửi xác nhận cho " + order.id
                + ", số tiền " + order.amountVnd);
    }
}

// Entry point nhận việc từ bên ngoài; không tự chọn adapter.
final class ConsoleOrderController {
    private final OrderService orders;

    ConsoleOrderController(OrderService orders) {
        this.orders = Objects.requireNonNull(orders, "orders");
    }

    void handle(String orderId, long amountVnd) {
        orders.confirm(orderId, amountVnd);
        System.out.println("Xử lý " + orderId + " thành công");
    }
}

public class App {
    public static void main(String[] args) {
        // Composition Root: tạo và lắp ghép một lần trước khi sử dụng.
        OrderRepository repository = new InMemoryOrderRepository();
        ReceiptSender sender = new ConsoleReceiptSender();

        OrderService orders = new OrderService(repository, sender);
        ConsoleOrderController controller =
                new ConsoleOrderController(orders);

        // Chuyển quyền điều khiển sang entry point đã được lắp ghép.
        controller.handle("ORDER-42", 120_000);
    }
}
```

Biên dịch và chạy:

```bash
javac App.java
java App
```

Đầu ra dự kiến:

```text
Đã gửi xác nhận cho ORDER-42, số tiền 120000
Xử lý ORDER-42 thành công
```

Trong ví dụ:

- `OrderService` biết **hợp đồng** `OrderRepository` và `ReceiptSender`; không gọi `new InMemoryOrderRepository()` hay `new ConsoleReceiptSender()`.
- `ConsoleOrderController` chỉ giữ `OrderService`; controller không quyết định chọn repository hoặc sender.
- `App.main` là **Composition Root**: nó tạo concrete implementation, truyền chúng qua constructor, sau đó mới gọi controller.
- `Order` là dữ liệu đơn giản do nghiệp vụ tạo trong lúc xử lý. Đây không phải cộng tác viên cần inject.
- Ví dụ dùng bộ nhớ và console để tập trung vào cách lắp ghép; nó không cung cấp cơ chế lưu bền vững hoặc gửi email thực tế.

**Lưu ý về semantics:** ví dụ gọi `repository.save` rồi `sender.sendConfirmation`. Nếu bước gửi thất bại, đơn đã được lưu trong implementation tương ứng. Composition Root không tự giải quyết giao dịch đa hệ thống; hệ thống thật phải thiết kế quy tắc lỗi, idempotency, retry hoặc outbox khi cần tính nhất quán.

### 3.2. Khi thay adapter, thay ở đâu?

Giả sử ứng dụng thật có `SqlOrderRepository` và `EmailReceiptSender` đáp ứng hai interface trên. Code lắp ghép khi triển khai có thể mang hình dạng:

```java
// Mã mô tả, các adapter và cấu hình dưới đây chưa được định nghĩa
// trong App.java, nên không phải đoạn chạy độc lập.
OrderRepository repository = new SqlOrderRepository(dataSource);
ReceiptSender sender = new EmailReceiptSender(mailClient);
OrderService service = new OrderService(repository, sender);
```

Phần nghiệp vụ `OrderService` không đổi. Composition Root chịu trách nhiệm tạo `dataSource`, `mailClient` và các adapter đúng theo môi trường; nếu chúng cần đóng, phải có kế hoạch đóng. **Giá trị của DI nằm ở khả năng thay đổi cách lắp ghép mà không sửa logic sử dụng dependency.**

## 4. Kiểm thử: mỗi bài test có thể là một Composition Root nhỏ

Một bài test unit chỉ cần tạo những đối tượng phục vụ hành vi đang kiểm tra. Không cần DI container, database hoặc mạng.

Lưu `OrderServiceTest.java` cạnh `App.java`:

```java
final class RecordingRepository implements OrderRepository {
    Order saved;
    int calls;

    @Override
    public void save(Order order) {
        saved = order;
        calls++;
    }
}

final class RecordingSender implements ReceiptSender {
    Order sent;
    int calls;

    @Override
    public void sendConfirmation(Order order) {
        sent = order;
        calls++;
    }
}

public class OrderServiceTest {
    public static void main(String[] args) {
        RecordingRepository repository = new RecordingRepository();
        RecordingSender sender = new RecordingSender();

        // Composition Root nhỏ của test.
        OrderService service = new OrderService(repository, sender);
        service.confirm("TEST-1", 50_000);

        if (repository.calls != 1 || sender.calls != 1
                || repository.saved != sender.sent
                || !"TEST-1".equals(repository.saved.id)
                || repository.saved.amountVnd != 50_000) {
            throw new AssertionError("Không sử dụng đúng dependency");
        }

        boolean missingDependencyRejected = false;
        try {
            new OrderService(null, sender);
        } catch (NullPointerException expected) {
            missingDependencyRejected = true;
        }
        if (!missingDependencyRejected) {
            throw new AssertionError("Thiếu kiểm tra dependency bắt buộc");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac App.java OrderServiceTest.java
java OrderServiceTest
```

Kết quả: `PASS`.

**Điểm cần phân biệt:** test trên chứng minh `OrderService` điều phối đúng hai dependency đã nhận. Nó **không chứng minh** cấu hình thật của ứng dụng khởi động được, SQL chạy đúng hay email gửi thành công. Muốn kiểm tra việc lắp ghép ở môi trường thật, cần thêm **smoke test hoặc integration test** đi qua Composition Root tương ứng và các adapter thực.

## 5. Đồ thị phụ thuộc và thứ tự khởi tạo

Composition Root phải khởi tạo các đối tượng theo thứ tự cho phép xây dựng graph hợp lệ. Với một đồ thị không có chu trình, ta thường tạo các **dependency ở lá trước**, sau đó tạo các đối tượng sử dụng chúng.

```text
       DataSource ──────> SqlOrderRepository ──┐
                                                ├──> OrderService ──> Controller
       MailClient ──────> EmailReceiptSender ───┘
```

Mũi tên trong sơ đồ trên biểu diễn **đối tượng được truyền tiếp trong quá trình lắp ghép**, không phải yêu cầu mỗi lớp phải biết concrete class của dependency.

Thứ tự điển hình:

1. Đọc và xác thực cấu hình ở điểm khởi động.
2. Tạo các dependency nền tảng như client, connection pool, clock hoặc thư viện cấu hình.
3. Tạo adapter hạ tầng từ các dependency nền tảng.
4. Tạo application service bằng cách truyền những adapter theo hợp đồng.
5. Tạo controller, handler, job hoặc entry point.
6. Chỉ bắt đầu tiếp nhận công việc sau khi đồ thị cần thiết đã sẵn sàng.

Nếu `ServiceA` bắt buộc có `ServiceB` và `ServiceB` lại bắt buộc có `ServiceA` qua constructor, đó là một **vòng phụ thuộc** mà Composition Root không thể giải quyết chỉ bằng đổi thứ tự `new`. Cần xem lại ranh giới trách nhiệm, thiết kế sự kiện, callback hoặc phân tách hợp đồng để loại bỏ chu trình thực sự.

Đừng lạm dụng constructor injection rồi kết luận rằng constructor nhận quá nhiều tham số là “vấn đề của container”. Constructor dài có thể báo hiệu một lớp làm quá nhiều việc; container chỉ lắp các dependency và không cải thiện trách nhiệm của lớp.

## 6. Scope và vòng đời: trách nhiệm phải rõ ngay tại điểm lắp ghép

Việc tạo đúng loại đối tượng chưa đủ: Composition Root còn phải xác định **đối tượng tồn tại trong bao lâu** và **ai sở hữu việc giải phóng tài nguyên**.

### 6.1. Những phạm vi sử dụng thường gặp

| Phạm vi | Cách tổ chức phổ biến | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Dùng chung trong ứng dụng | Tạo một instance khi khởi động và truyền vào nhiều service. | Đối tượng có trạng thái thay đổi theo request hoặc không thread-safe sẽ gây lỗi khi chia sẻ. |
| Instance riêng cho mỗi lần sử dụng | Tạo dependency hoặc service mới theo công việc. | Chi phí khởi tạo, quản lý tài nguyên và số lượng instance. |
| Theo request hoặc đơn vị công việc | Tạo object graph con khi request bắt đầu; giải phóng khi kết thúc. | Giữ nhầm dependency ngắn hạn bên trong singleton sống lâu. |

Một `OrderService` không lưu trạng thái request có thể được dùng chung **nếu chính nó và các dependency được dùng chung đều an toàn khi truy cập đồng thời**. Ví dụ `InMemoryOrderRepository` sử dụng `ArrayList` trong mục 3 **không thread-safe**; không nên đưa nguyên ví dụ đó vào web server đa luồng rồi mặc định chia sẻ cho mọi request.

Khi cần dữ liệu theo request như `CurrentUser`, `RequestContext` hay một transaction-scoped persistence context, đừng truyền instance của request đầu tiên vào một singleton để dùng mãi. Composition Root hoặc hệ thống quản lý scope phải cung cấp đúng dependency trong mỗi lần xử lý.

### 6.2. Quản lý tài nguyên có thể đóng

Đối với client, connection pool, executor hoặc thành phần nắm tài nguyên, nơi tạo phải có quy tắc đóng. Sau đây là phác thảo của một Composition Root quản lý tài nguyên:

```java
// Pseudocode: DataSource/HTTP client và adapter cụ thể
// phụ thuộc thư viện ngoài; không phải mã chạy độc lập.
try (ManagedDataSource dataSource = createDataSource(config);
     ManagedMailClient mailClient = createMailClient(config)) {

    OrderRepository repository = new SqlOrderRepository(dataSource);
    ReceiptSender sender = new EmailReceiptSender(mailClient);
    OrderService service = new OrderService(repository, sender);

    runApplication(service);
} // Đóng tài nguyên do root sở hữu khi luồng chạy kết thúc.
```

`try-with-resources` chỉ dùng trực tiếp cho các kiểu thực hiện `AutoCloseable` hoặc `Closeable`; một `DataSource` nói chung không bắt buộc là `AutoCloseable`. Trong ứng dụng web hoạt động lâu dài, việc đóng thường do lifecycle của server/container thực hiện ở thời điểm shutdown.

**DI không tự đóng tài nguyên** và không tự bảo đảm thread safety. Container có thể hỗ trợ quản lý scope/lifecycle, nhưng mỗi binding vẫn phải tuân theo quy tắc của ứng dụng và thư viện đang dùng.

## 7. Những lỗi thiết kế khiến Composition Root mất vai trò

### 7.1. Tự tạo adapter trong lớp nghiệp vụ

```java
// Ví dụ cần tránh.
final class BrokenOrderService {
    private final OrderRepository repository =
            new InMemoryOrderRepository();
}
```

`BrokenOrderService` tự quyết định implementation. Muốn đổi thành SQL repository hoặc fake trong test phải sửa lớp nghiệp vụ hoặc dùng biện pháp can thiệp khác. Hãy đưa việc chọn adapter về Composition Root và truyền dependency qua constructor.

### 7.2. Service Locator: tìm dependency ngầm khi chạy

```java
// Ví dụ mô tả mẫu nên tránh trong nghiệp vụ:
OrderRepository repository =
        GlobalRegistry.get(OrderRepository.class);
```

Registry có thể nằm trong container, nhưng khi nghiệp vụ tự tra cứu, các dependency trở nên **ẩn** và khó xác định từ chữ ký constructor. Hệ thống vẫn có một nơi đăng ký dịch vụ, nhưng quyền lựa chọn và truy xuất phụ thuộc đã bị phân tán vào logic nghiệp vụ.

Ở biên ứng dụng, container có thể thực hiện lookup để tạo entry point. Nên giữ việc phụ thuộc vào API container ở bootstrap/adapter, tránh đưa cơ chế tìm kiếm đó sâu vào domain/service.

### 7.3. Khởi tạo ở mọi controller/handler

```java
// Pseudocode: một controller tự tạo client, repository và service.
void onRequest(Request request) {
    DbClient db = new DbClient(config);
    OrderService service =
            new OrderService(new SqlOrderRepository(db), sender);
    service.confirm(request.id(), request.amountVnd());
}
```

Nếu mỗi request tự mở connection pool hoặc tạo client đắt tiền, việc quản lý tài nguyên có thể sai và cấu hình bị sao chép ở nhiều entry point. Nếu cần đối tượng theo request, hãy tạo nó qua factory/scope được thiết kế rõ ràng và dùng lại các tài nguyên phù hợp.

Không phải mọi hàm tạo instance theo request đều sai; điểm quan trọng là **quyết định lắp ghép, lifetime và ownership được tập trung và kiểm soát**.

### 7.4. Composition Root làm thay nghiệp vụ

Một root phình to với điều kiện giảm giá, quy tắc thanh toán, phân quyền và thay đổi trạng thái đơn hàng đã vượt quá vai trò của nó. Root nên lựa chọn strategy/adapter và chuyển chúng vào service; chính service hoặc các thành phần nghiệp vụ chuyên trách mới xử lý quy tắc.

### 7.5. Giấu quyết định mặc định trong constructor

```java
OrderService(OrderRepository repo, ReceiptSender sender) {
    this.repository = repo == null ? new InMemoryOrderRepository() : repo;
    this.sender = sender == null ? new ConsoleReceiptSender() : sender;
}
```

Constructor này âm thầm thay `null` bằng triển khai khác, khiến root khó nhận biết lỗi cấu hình. Nếu dependency bắt buộc, dùng `Objects.requireNonNull` để báo lỗi ngay. Nếu có chế độ demo, chính root nên **chủ động** truyền adapter demo vào.

## 8. DI container xuất hiện ở đâu?

Khi đồ thị phụ thuộc lớn, có nhiều cấu hình và phạm vi, viết toàn bộ wiring bằng `new` có thể tạo mã lặp. **DI container** tự động hóa một phần công việc: nhận định nghĩa binding, tạo instance, cung cấp dependency, quản lý một số scope và hook lifecycle theo khả năng từng framework.

Tuy nhiên:

- **Composition Root là khái niệm kiến trúc; DI container là công cụ.** Có Composition Root mà không cần container, như ví dụ Java ở trên.
- Khi có container, cấu hình/khởi tạo container và đăng ký các entry point thường vẫn thuộc trách nhiệm Composition Root hoặc bootstrap.
- Nếu một framework tự tạo controller/bean, điểm lắp ghép có thể biểu hiện qua các cấu hình và lifecycle hook của framework; không nhất thiết có một hàm `main` chứa mọi lời gọi `new`.
- Không nên inject container toàn cục vào mọi service để chúng tự lấy dependency. Container nên tham gia lúc lắp ghép; business code nhận những dependency tường minh.
- Container không tự biến graph thành kiến trúc tốt: một lớp nhận 20 dependency, chu trình khởi tạo hoặc scope sai vẫn là vấn đề thiết kế.

Một quá trình học hiệu quả là **lắp graph thủ công trong Java thuần trước**, hiểu rõ constructor injection, thứ tự khởi tạo và ownership, rồi chuyển phần lặp sang container khi có lý do cụ thể.

## 9. Quy trình thiết kế Composition Root cho một ứng dụng mới

Có thể triển khai theo trình tự:

1. **Liệt kê các entry point**: HTTP controller, CLI command, scheduled job, listener hoặc UI event; xác định thời điểm bắt đầu nhận công việc.
2. **Xác định dependency theo hướng từ nghiệp vụ ra ngoài**: service cần repository, sender, clock hay API client nào? Đặt hợp đồng nhỏ và phù hợp với nghiệp vụ.
3. **Chọn adapter theo môi trường**: production, local, test có thể sử dụng implementation khác nhau; quyết định đặt tại bootstrap.
4. **Thiết kế scope và ownership**: thành phần nào dùng chung, thành phần nào gắn với request; ai tạo và đóng tài nguyên?
5. **Lắp từ lá lên**: tạo client/config, adapter, service, cuối cùng entry point; xác thực sớm cấu hình bắt buộc.
6. **Chạy smoke test cho graph khởi động**: khởi tạo bằng cấu hình dự kiến, phát hiện thiếu binding hoặc chu trình; dùng kiểm thử tích hợp cho adapter thật khi phù hợp.
7. **Giữ root tập trung vào wiring**: chuyển nghiệp vụ ra service; khi wiring dài, tách thành các factory/module có tên rõ và được root điều phối.

Mã lắp ghép quá dài không nhất thiết phải gom trong một file khổng lồ. Một cấu trúc đơn giản có thể là:

```text
bootstrap/
    App.java                <- entry point, điều phối composition
    InfrastructureFactory  <- tạo adapter/client, định nghĩa ownership
application/
    OrderService           <- xử lý ca sử dụng, nhận interface
    OrderRepository        <- hợp đồng persistence
    ReceiptSender          <- hợp đồng notification
infrastructure/
    SqlOrderRepository     <- adapter database
    EmailReceiptSender     <- adapter email
presentation/
    OrderController        <- nhận request, gọi service
```

Sơ đồ thể hiện **trách nhiệm** của từng phần; tên folder/package có thể khác tùy quy ước dự án. Các factory ở bootstrap có thể nhận cấu hình và trả về đối tượng, nhưng việc gọi chúng vẫn được điều phối ở ranh giới lắp ghép.

## 10. Bài tập thực hành

**Bối cảnh:** một ứng dụng tạo báo cáo có `ReportService`, `ReportRepository`, `ReportFormatter` và `ReportPublisher`. Môi trường CLI cần đọc dữ liệu từ file và xuất ra console; môi trường web cần đọc database và xuất báo cáo qua email.

Hãy hoàn thành:

1. Phác thảo object graph cho CLI và web, đánh dấu những interface chung và adapter khác nhau.
2. Viết constructor `ReportService(ReportRepository repository, ReportFormatter formatter, ReportPublisher publisher)` với kiểm tra dependency bắt buộc. Cho biết lớp nào được phép biết về file system hoặc SMTP client.
3. Viết hai điểm lắp ghép (hoặc hai cấu hình entry point) để chọn adapter phù hợp mà không sửa `ReportService`.
4. Xác định những dependency có thể sống suốt ứng dụng và những dependency chỉ nên tồn tại theo request/job. Ai sẽ đóng các tài nguyên cần đóng?
5. Viết một bài test dùng fake `ReportRepository` và fake `ReportPublisher`; nêu một kiểm thử tích hợp cần thiết để xác minh wiring của ứng dụng web.
6. Nếu một `ReportService` bắt đầu yêu cầu 12 dependency, hãy phân tích vấn đề trách nhiệm trước khi quyết định thêm DI container.

**Gợi ý đối chiếu:** cả CLI và web dùng chung service cùng các hợp đồng, nhưng Composition Root của từng executable chọn adapter riêng. `ReportService` phụ thuộc vào các interface phục vụ use case. Adapter chứa chi tiết file/DB/SMTP. Test unit tự lắp graph dùng fake; test integration kiểm tra adapter thật và scope. Với nhiều dependency, xem xét chia trách nhiệm service hoặc tạo các khái niệm cộng tác viên có ý nghĩa thay vì chỉ cố tự động hóa constructor dài.

**Điểm cần nhớ:** Composition Root là **ranh giới lắp ghép gần entry point**. Nó chọn implementation, tạo và kết nối object graph, kiểm soát cấu hình, scope và ownership; nghiệp vụ chỉ sử dụng những dependency được truyền vào. Hiểu và thực hành điểm lắp ghép bằng Java thuần giúp giữ kiến trúc rõ ràng trước khi sử dụng DI container.
