# Tính gắn kết bên trong lớp (Cohesion) trong OOP Java

> **Mục tiêu:** Hiểu tính gắn kết là gì; đánh giá liệu dữ liệu và hành vi trong một lớp có phục vụ cùng một trách nhiệm hay không; nhận biết lớp “ôm đồm”; và biết refactor thành các lớp có ranh giới rõ ràng mà không chia nhỏ quá mức.

## 1. Cohesion là gì?

**Tính gắn kết bên trong lớp (class cohesion)** mô tả mức độ các thuộc tính, phương thức và quy tắc trong **cùng một lớp** cùng phục vụ một mục tiêu có ý nghĩa. Một lớp có **cohesion cao** khi các phần tử của nó tạo thành một khái niệm nhất quán và thường thay đổi vì cùng một nhóm lý do nghiệp vụ.

Ví dụ:

- `Cart` giữ các dòng hàng, kiểm tra số lượng và tính tổng tiền hàng: các hành vi xoay quanh trạng thái giỏ hàng → cohesion thường **cao**.
- `CartManager` vừa tính giá, lưu database, gửi email, ghi log đăng nhập, xuất báo cáo CSV và kiểm tra quyền truy cập: các hành vi chịu những lý do thay đổi khác nhau → cohesion thường **thấp**.

Có thể tự hỏi: **“Nếu phải mô tả lớp này bằng một câu rõ ràng không dùng từ ‘và’, mình sẽ nói gì?”** Đây chỉ là mẹo đánh giá, không phải tiêu chuẩn máy móc. Một lớp điều phối use case có thể kết hợp nhiều bước để hoàn thành **một** nghiệp vụ, vẫn cohesive nếu không chứa chi tiết triển khai của từng bước.

**Cohesion không đồng nghĩa “có ít phương thức” hoặc “mọi phương thức đều đọc cùng một field”.** Một lớp chỉ có 2 phương thức nhưng làm hai việc không liên quan vẫn ít gắn kết. Một lớp có nhiều thao tác quanh cùng một domain concept vẫn có thể gắn kết tốt.

## 2. Phân biệt cohesion và coupling

| Tiêu chí | Cohesion – gắn kết nội bộ | Coupling – phụ thuộc giữa các thành phần |
|---|---|---|
| Câu hỏi chính | Các phần **trong cùng lớp** có liên quan chặt chẽ đến một trách nhiệm không? | Lớp này cần biết/giả định bao nhiêu về lớp khác? |
| Phạm vi quan sát | Fields, methods, invariants, lý do thay đổi | Constructor dependency, API, kiểu dữ liệu, gọi phương thức, chia sẻ trạng thái |
| Mục tiêu thiết kế thường gặp | **Cao**: trách nhiệm nhất quán | **Thấp vừa đủ**: phụ thuộc tối thiểu, giao diện ổn định |
| Dấu hiệu xấu | Một lớp xử lý việc không liên quan | Sửa một lớp bắt buộc sửa hàng loạt lớp khác |
| Cách cải thiện điển hình | Extract Class, di chuyển hành vi về đúng owner | Dependency Inversion, interface/port, giới hạn API |

Hai tính chất **khác nhau** nhưng có liên hệ. Tách một lớp thành nhiều lớp nhỏ có thể tăng cohesion cục bộ nhưng cũng làm tăng số phụ thuộc; thiết kế tốt phải cân bằng cả hai.

~~~mermaid
flowchart LR
    subgraph Low["Lớp đa trách nhiệm"]
        direction TB
        X[AccountManager]
        X1[Login]
        X2[Export CSV]
        X3[Send email]
        X4[Compute billing]
    end
    subgraph High["Các trách nhiệm rõ ràng"]
        direction TB
        A[AuthenticationService]
        B[CsvReportExporter]
        C[NotificationGateway]
        D[BillingCalculator]
    end
    Low -. tách trách nhiệm .-> High
~~~

Sơ đồ diễn đạt mục tiêu **gom các hành vi cùng thay đổi về đúng chủ thể**, không phải quy tắc “mỗi phương thức là một lớp”.

## 3. Dấu hiệu một lớp có cohesion thấp

1. **Tên quá chung:** `Manager`, `Helper`, `Processor`, `Util` mà trách nhiệm thực tế trải nhiều miền nghiệp vụ.
2. **Các nhóm method dùng các nhóm field độc lập:** phương thức `sendEmail()` chỉ dùng SMTP config, `calculateTax()` chỉ dùng taxRate và `saveOrder()` chỉ dùng JDBC connection.
3. **Có nhiều lý do thay đổi độc lập:** chính sách chiết khấu thay đổi, nhà cung cấp email đổi, schema database đổi đều bắt phải sửa cùng một file/lớp.
4. **Có nhiều dạng lỗi khác nhau trong cùng lớp:** exception mạng, xác thực đầu vào, quy tắc giá, serialization bị trộn trong một hàm lớn.
5. **Test khó độc lập:** muốn kiểm tra phép tính thuần nhưng phải khởi động database, HTTP client hoặc SMTP.
6. **Constructor chứa quá nhiều phụ thuộc không cùng phục vụ một nhiệm vụ:** đây là tín hiệu cần xem xét, không phải kết luận tuyệt đối.
7. **Các feature sửa cùng lớp nhưng ít dùng chung ngữ cảnh:** làm tăng xung đột merge và gây lan truyền thay đổi.

Đặc biệt, **đừng kết luận cohesion thấp chỉ vì một hàm dài**. Hàm dài có thể là vấn đề về độ phức tạp hoặc khả năng đọc, trong khi toàn lớp vẫn đúng một trách nhiệm. Ngược lại, tách hàm lớn thành mười hàm nhỏ bên trong một lớp vẫn không giải quyết sự trộn lẫn trách nhiệm.

## 4. Ví dụ trước refactor: một lớp làm quá nhiều việc

Ví dụ đơn giản sau có thể biên dịch trong dự án Java 17 khi tách vào `LegacyCheckoutService.java`. Nó minh họa rõ ba nhóm việc: **tính tiền**, **lưu trữ**, và **gửi thông báo**.

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record Line(String sku, int quantity, BigDecimal unitPrice) {}

// Ví dụ để phân tích thiết kế; chưa có kiểm tra dữ liệu đầu vào.
final class LegacyCheckoutService {
    private final Map<String, BigDecimal> database = new HashMap<>();

    BigDecimal calculateTotal(List<Line> lines) {
        BigDecimal total = BigDecimal.ZERO;
        for (Line line : lines) {
            total = total.add(
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())));
        }
        return total;
    }

    void saveOrder(String orderId, BigDecimal amount) {
        database.put(orderId, amount);
    }

    void sendReceipt(String email, String orderId) {
        System.out.println("Send receipt to " + email + " for " + orderId);
    }

    void checkout(String orderId, String email, List<Line> lines) {
        BigDecimal total = calculateTotal(lines);
        saveOrder(orderId, total);
        sendReceipt(email, orderId);
    }
}
~~~

Ở ví dụ này, `database` chỉ liên quan việc lưu; thuật toán tính tiền không cần nó; gửi email cũng không dùng nó. Mỗi nhóm có nguyên nhân thay đổi độc lập:

| Nhóm hành vi | Khi nào cần sửa? | Chủ thể thích hợp |
|---|---|---|
| `calculateTotal()` | Quy tắc tính tiền, cách làm tròn, giảm giá | `Cart` hoặc thành phần pricing đúng miền nghiệp vụ |
| `saveOrder()` | Đổi storage/database/schema | `OrderRepository` |
| `sendReceipt()` | Đổi nhà cung cấp email/template | `ReceiptSender` |
| `checkout()` | Đổi thứ tự và quy tắc xử lý checkout | `CheckoutService` điều phối use case |

Một lớp duy nhất bị buộc phải quan tâm cả bốn thay đổi. Đó là vấn đề cohesion, **không chỉ là số dòng mã**.

## 5. Sau refactor: mỗi lớp có trách nhiệm mạch lạc

Ở thiết kế mới:

- `Cart` bảo vệ **danh sách mặt hàng và quy tắc tính tổng tiền từ các dòng hiện có**.
- `OrderRepository` có hợp đồng **lưu và tra cứu đơn**; implementation quyết định lưu ở đâu.
- `ReceiptSender` có hợp đồng **gửi biên nhận**; implementation quyết định kênh gửi.
- `CheckoutService` **điều phối một use case checkout** và ủy quyền các chi tiết.

~~~mermaid
classDiagram
    direction LR
    class Cart {
        -List~CartLine~ lines
        +addLine(sku, quantity, unitPrice)
        +total() BigDecimal
        +snapshot() List
    }
    class CheckoutService {
        -OrderRepository repository
        -ReceiptSender sender
        +checkout(orderId, email, cart)
    }
    class OrderRepository {
        <<interface>>
        +save(Order)
        +findById(id) Optional
    }
    class ReceiptSender {
        <<interface>>
        +sendReceipt(Order, email)
    }
    class InMemoryOrderRepository
    class ConsoleReceiptSender
    CheckoutService --> Cart : dùng giá trị
    CheckoutService --> OrderRepository : lưu đơn
    CheckoutService --> ReceiptSender : thông báo
    InMemoryOrderRepository ..|> OrderRepository
    ConsoleReceiptSender ..|> ReceiptSender
~~~

**Mã Java 17+ hoàn chỉnh trong một tệp `CohesionDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

// 1) Value object: một dòng hàng hợp lệ.
record CartLine(String sku, int quantity, BigDecimal unitPrice) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid cart line");
        }
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

// 2) Domain object: quản lý trạng thái và invariant của giỏ hàng.
final class Cart {
    private final List<CartLine> lines = new ArrayList<>();

    void addLine(String sku, int quantity, BigDecimal unitPrice) {
        lines.add(new CartLine(sku, quantity, unitPrice));
    }

    List<CartLine> snapshot() {
        return List.copyOf(lines);
    }

    BigDecimal total() {
        return lines.stream()
                .map(CartLine::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    boolean isEmpty() {
        return lines.isEmpty();
    }
}

// 3) Dữ liệu đơn hàng đã đặt, bất biến.
record Order(String id, List<CartLine> lines, BigDecimal total) {
    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(total, "total");
        if (id.isBlank() || lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid order");
        }
        lines = List.copyOf(lines);
    }
}

// 4) Hợp đồng hạ tầng lưu trữ.
interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(String id);
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}

// 5) Hợp đồng thông báo.
interface ReceiptSender {
    void sendReceipt(Order order, String email);
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void sendReceipt(Order order, String email) {
        System.out.printf("Receipt %s: %s -> %s%n",
                order.id(), order.total(), email);
    }
}

// 6) Application service: điều phối use case checkout.
final class CheckoutService {
    private final OrderRepository repository;
    private final ReceiptSender receiptSender;

    CheckoutService(OrderRepository repository, ReceiptSender receiptSender) {
        this.repository = Objects.requireNonNull(repository, "repository");
        this.receiptSender = Objects.requireNonNull(receiptSender, "receiptSender");
    }

    Order checkout(String id, String email, Cart cart) {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(email, "email");
        Objects.requireNonNull(cart, "cart");

        if (id.isBlank() || email.isBlank() || cart.isEmpty()) {
            throw new IllegalArgumentException("Invalid checkout");
        }

        Order order = new Order(id, cart.snapshot(), cart.total());
        repository.save(order);
        receiptSender.sendReceipt(order, email);
        return order;
    }
}

public class CohesionDemo {
    public static void main(String[] args) {
        Cart cart = new Cart();
        cart.addLine("JAVA-BOOK", 2, new BigDecimal("125000"));
        cart.addLine("NOTEBOOK", 1, new BigDecimal("30000"));

        OrderRepository repository = new InMemoryOrderRepository();
        ReceiptSender sender = new ConsoleReceiptSender();
        CheckoutService service = new CheckoutService(repository, sender);

        Order order = service.checkout(
                "ORD-42", "user@example.com", cart);

        System.out.println(order.total());                 // 280000
        System.out.println(repository.findById("ORD-42").isPresent()); // true
    }
}
~~~

Chạy:

~~~bash
javac CohesionDemo.java
java CohesionDemo
~~~

Kết quả minh họa:

~~~text
Receipt ORD-42: 280000 -> user@example.com
280000
true
~~~

**Vì sao cohesion tốt hơn?** Phương thức của `Cart` tập trung vào trạng thái giỏ hàng; `OrderRepository` xử lý persistence; `ReceiptSender` xử lý thông báo. `CheckoutService` vẫn dùng cả lưu trữ lẫn gửi thông báo, nhưng **một mục tiêu** của nó là thực hiện luồng checkout theo thứ tự: tạo dữ liệu đơn → lưu → yêu cầu gửi biên nhận. Sự phối hợp nhiều bước không đồng nghĩa cohesion thấp.

**Giới hạn của ví dụ:** `ConsoleReceiptSender` chỉ in ra console, không gửi email thật. Mã tập trung vào thiết kế lớp, chưa xử lý tính nguyên tử giữa database và hạ tầng thông báo. Hệ thống thực cần xác định rõ hành vi khi gửi email lỗi sau khi lưu đơn, cân nhắc transaction, retry/idempotency hoặc outbox. Nếu giỏ hàng có thể được sửa đồng thời giữa lúc lấy `snapshot()` và `total()`, hai giá trị có thể lệch nhau; cần snapshot nhất quán hoặc chỉ cho phép một luồng chỉnh sửa theo vòng đời của giỏ hàng.

## 6. Cohesion liên quan thế nào tới SRP?

**Single Responsibility Principle (SRP)** thường được giải thích là “một lớp chỉ có một lý do để thay đổi”, hiểu sát hơn là **một nhóm tác nhân/nhu cầu thay đổi nghiệp vụ chủ đạo**. Cohesion là đặc điểm của sự nhất quán nội bộ; SRP là nguyên tắc về **ranh giới trách nhiệm và lý do thay đổi**.

Chúng liên quan nhưng không đồng nhất:

- `Cart` có `addLine()`, `isEmpty()`, `total()`: nhiều thao tác nhưng cùng bảo vệ quy tắc giỏ hàng.
- `CheckoutService` gọi repository và receipt sender: nó điều phối **một** use case, không tự triển khai SQL và SMTP.
- Nếu yêu cầu tính thuế quá phức tạp, nhiều vùng lãnh thổ, nhiều bản chính sách, cần xem xét trích xuất `TaxPolicy`/`PricingService`. Nhưng nếu chỉ cộng subtotal của các dòng hiện có, để `Cart.total()` là hợp lý.
- Cần tách lớp theo **lý do thay đổi thực tế**, không theo công thức một class/method.

Một câu hỏi hữu ích khi review: **“Nếu đội quản lý giá thay đổi quy tắc thuế, có cần sửa lớp gửi biên nhận hay kho lưu đơn không?”** Nếu thường xuyên có, ranh giới trách nhiệm đang bị trộn.

## 7. Các mức gắn kết trong thiết kế – cách dùng để suy nghĩ

Một số tài liệu phân loại cohesion trong thiết kế chương trình từ yếu đến mạnh. Các nhãn này vốn thường được dạy ở mức **module hoặc chức năng**; khi áp dụng vào **lớp OOP**, hãy dùng làm công cụ phân tích định tính, không coi như thang điểm chuẩn tuyệt đối.

| Loại gắn kết | Ý nghĩa | Ví dụ trong Java | Đánh giá |
|---|---|---|---|
| **Coincidental** – ngẫu nhiên | Gom việc không liên quan | `MiscUtils` chứa `sendEmail()`, `hashPassword()` và `formatMoney()` | Thường rất yếu |
| **Logical** – theo nhóm kỹ thuật | Các thao tác cùng dạng nhưng xử lý nhiều mục đích qua cờ điều khiển | `Handler.process(type)` dùng switch cho email/SMS/export CSV | Thường nên cân nhắc tách |
| **Temporal** – theo thời điểm | Các việc cùng chạy ở lúc startup/shutdown | `StartupTasks` mở cache, chạy migration, in banner | Có thể hợp lý tại điểm orchestration |
| **Procedural** – theo thứ tự | Các bước đi cùng nhau vì thứ tự gọi | `Workflow` chạy validate → save → notify | Có thể cohesive nếu cùng use case |
| **Communicational** – cùng dữ liệu | Các phương thức cùng thao tác trên một dữ liệu miền nghiệp vụ | `Cart` thêm dòng, lấy tổng, kiểm tra rỗng | Thường tốt nếu đúng domain |
| **Sequential** – đầu ra bước trước là đầu vào bước sau | Pipeline parse → normalize → validate | `ImportPipeline` xử lý một bản ghi | Có thể phù hợp hoặc cần tách chiến lược |
| **Functional** – cùng một chức năng rõ ràng | Thành phần chỉ chuyên tính thuế theo policy nhất quán | `TaxCalculator` | Thường rất mạnh |

**Không chấm điểm lớp dựa duy nhất vào tên loại:** Một `ApplicationBootstrap` cố ý thực hiện những việc cùng thời điểm khởi động là hợp lý ở *composition root*. Một `CheckoutService` cố ý gọi ba bước theo trình tự cũng hợp lý khi nó điều phối một use case. Vấn đề nảy sinh nếu coordinator vừa quản lý quy trình vừa nhồi chi tiết thuật toán của những trách nhiệm khác.

## 8. Cách tự đánh giá cohesion của một lớp

Hãy dùng một bảng **method × field** (ví dụ có 6 phương thức và 4 trường) để tìm các cụm trách nhiệm. Đây không phải công thức duy nhất: các phương thức thuần không dùng field vẫn có thể phục vụ đúng một khái niệm.

Ví dụ một lớp có bốn trường độc lập: `orders`, `smtpClient`, `taxRate`, `csvFormat`.

| Phương thức | orders | smtpClient | taxRate | csvFormat |
|---|:---:|:---:|:---:|:---:|
| `saveOrder()` | ✓ | | | |
| `findOrder()` | ✓ | | | |
| `sendReceipt()` | | ✓ | | |
| `calculateTax()` | | | ✓ | |
| `exportCsv()` | | | | ✓ |

Ma trận có các **cụm rời rạc**: hai phương thức liên quan lưu đơn, một phương thức email, một phương thức thuế, một phương thức xuất file. Đây là tín hiệu mạnh rằng lớp có nhiều trách nhiệm độc lập.

Ngược lại, với `Cart`:

| Phương thức | lines / CartLine | Quy tắc giỏ hàng |
|---|:---:|:---:|
| `addLine()` | ✓ | kiểm tra dữ liệu |
| `isEmpty()` | ✓ | ngăn checkout giỏ rỗng |
| `total()` | ✓ | tính tổng các dòng |
| `snapshot()` | ✓ | tránh lộ trạng thái mutable |

Các thao tác cùng bảo vệ một đối tượng miền nghiệp vụ.

**Nhận diện cohesion dựa vào ý nghĩa**, không chỉ mức trùng lặp trường. Chẳng hạn, `validateEmail()` không đọc field nào nhưng có thể hợp lý trong một value object `EmailAddress` vì nó bảo vệ invariant của giá trị này.

### LCOM và các metric khác

`LCOM` (*Lack of Cohesion of Methods*) là họ chỉ số đo **sự thiếu gắn kết** giữa các phương thức. Có nhiều định nghĩa như LCOM1, LCOM2, LCOM3, LCOM4 và chúng **không cho cùng một giá trị** trên cùng một lớp. Một số biến thể dựa trên việc hai phương thức có cùng sử dụng field không; một số dựa trên đồ thị liên thông giữa phương thức.

Điểm cần nắm:

- **Tên metric thôi là chưa đủ**: khi báo cáo “LCOM = 3”, phải nêu biến thể/công cụ và cách tính.
- Theo một số biến thể, LCOM cao gợi ý lớp thiếu gắn kết; không suy diễn được một ngưỡng phổ quát áp dụng cho mọi dự án.
- Static utility, immutable value object, lớp kế thừa, lớp dùng delegation, DTO, framework adapter có thể khiến chỉ số lệch so với ý nghĩa nghiệp vụ.
- Phương thức truy cập field gián tiếp qua getter/helper có thể bị các phương pháp đo tĩnh diễn giải khác nhau.
- Metric hỗ trợ **tìm lớp đáng review**, không thay thế việc hiểu trách nhiệm và lý do thay đổi.

Có thể kết hợp dấu hiệu định lượng như số lượng public methods, số trường/phụ thuộc, thay đổi theo lịch sử Git, độ phức tạp phương thức và thời gian kiểm thử. Nhưng đừng chia một lớp chỉ để làm số liệu đẹp hơn.

## 9. Quy trình refactor từ cohesion thấp thành cao

~~~mermaid
flowchart TD
    A[Chọn lớp thường xuyên thay đổi] --> B[Liệt kê method, field, caller, thay đổi]
    B --> C[Nhóm theo mục tiêu và invariant]
    C --> D{Có nhóm trách nhiệm tách biệt?}
    D -->|Không| E[Giữ lớp, cải thiện tên hoặc method nếu cần]
    D -->|Có| F[Chọn owner mới: domain/service/adapter]
    F --> G[Extract Class hoặc Move Method]
    G --> H[Cập nhật caller và DI]
    H --> I[Chạy test và kiểm tra hành vi]
    I --> J{Ổn định API và invariant?}
    J -->|Chưa| F
    J -->|Có| K[Đánh giá lại cohesion và coupling]
~~~

**Thực hiện an toàn theo từng bước:**

1. **Đọc hợp đồng hiện có:** các public method, ngoại lệ, tác dụng phụ, thread safety, transaction, thứ tự xử lý và cách caller dùng lớp.
2. **Lập bản đồ trách nhiệm:** thay vì nhìn số dòng, hãy gom các phương thức/field theo use case và “ai yêu cầu thay đổi chức năng này?”.
3. **Nhận diện invariant:** dữ liệu nào phải đổi cùng nhau để luôn hợp lệ? Đặt dữ liệu và hành vi bảo vệ invariant gần nhau. Không tùy tiện tách `Cart.lines` khỏi `Cart.addLine()` rồi để caller sửa danh sách.
4. **Tạo lớp mới có tên nói đúng nhiệm vụ:** ví dụ `ReceiptSender`, `OrderRepository`, `PricePolicy`; ưu tiên API nhỏ, ổn định.
5. **Di chuyển logic trước khi xóa đường cũ:** dùng `Extract Class`/`Move Method`; trong chuyển tiếp có thể giữ adapter/delegation tương thích có kiểm soát nếu nhiều caller phụ thuộc API cũ.
6. **Tiêm phụ thuộc qua constructor:** giúp việc kiểm thử độc lập và thể hiện rõ collaborator bắt buộc. Nhưng **đừng tạo interface cho mọi lớp** nếu không có nhu cầu thay thế implementation hay biên kiến trúc.
7. **Chạy test nghiệp vụ và integration test thích hợp:** xem xét lỗi database/email, rollback, kết quả tính tiền, thời gian/độ trễ và tương thích API.
8. **Review tác động hệ thống:** refactor có làm nhiều lớp phụ thuộc chằng chịt hơn hoặc khiến quy tắc nghiệp vụ bị phân tán không? Nếu có, điều chỉnh lại ranh giới.

Một refactor thất bại điển hình là chuyển mỗi method sang một service, sau đó mọi thao tác đơn giản phải chuyền qua 8 service. Cohesion của từng lớp có vẻ “cao”, nhưng coupling và độ khó hiểu của luồng nghiệp vụ tăng. Nên gom theo **khái niệm và invariant**, không theo kích thước file.

## 10. Kiểm thử cho thiết kế mới

Kiểm thử nên khẳng định **hành vi và ranh giới tương tác**. Với ví dụ `CohesionDemo.java`, dùng JUnit Jupiter 5.

**`CohesionDemoTest.java`** (đặt cùng package để gọi các class package-private):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

class CohesionDemoTest {
    @Test
    void cartOwnsItsPricingInvariant() {
        Cart cart = new Cart();

        cart.addLine("JAVA-BOOK", 2, new BigDecimal("125000"));
        cart.addLine("NOTEBOOK", 1, new BigDecimal("30000"));

        assertEquals(0, new BigDecimal("280000").compareTo(cart.total()));
        assertEquals(2, cart.snapshot().size());
        assertThrows(IllegalArgumentException.class,
                () -> cart.addLine("BAD", 0, BigDecimal.ONE));
        assertThrows(UnsupportedOperationException.class,
                () -> cart.snapshot().clear());
    }

    @Test
    void checkoutSavesThenSendsReceiptOnce() {
        List<String> calls = new ArrayList<>();

        OrderRepository repository = new OrderRepository() {
            @Override
            public void save(Order order) {
                calls.add("save:" + order.id());
            }

            @Override
            public Optional<Order> findById(String id) {
                return Optional.empty();
            }
        };

        ReceiptSender sender = (order, email) ->
                calls.add("send:" + order.id() + ":" + email);

        CheckoutService service = new CheckoutService(repository, sender);
        Cart cart = new Cart();
        cart.addLine("BOOK", 1, new BigDecimal("50000"));

        Order order = service.checkout("O-1", "a@example.com", cart);

        assertEquals(0, new BigDecimal("50000").compareTo(order.total()));
        assertEquals(List.of("save:O-1", "send:O-1:a@example.com"), calls);
    }

    @Test
    void invalidCheckoutDoesNotCallCollaborators() {
        List<String> calls = new ArrayList<>();
        OrderRepository repository = new OrderRepository() {
            public void save(Order order) { calls.add("saved"); }
            public Optional<Order> findById(String id) {
                return Optional.empty();
            }
        };
        ReceiptSender sender = (order, email) -> calls.add("sent");
        CheckoutService service = new CheckoutService(repository, sender);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("O-2", "a@example.com", new Cart()));
        assertTrue(calls.isEmpty());
    }
}
~~~

**Test này chứng minh được gì?**

- `Cart` bảo vệ số lượng dương, không để caller thay đổi danh sách qua snapshot và tính tổng đúng.
- `CheckoutService` điều phối đúng thứ tự, chỉ gọi các cộng tác viên qua hợp đồng đã tiêm, và không gọi chúng khi đầu vào sai.
- Không cần khởi động database hay hệ thống gửi email để kiểm tra phép tính.

**Test chưa chứng minh điều gì?** Nó chưa chứng minh có transaction đúng, dữ liệu được lưu bền vững, hay email ngoài đời được giao thành công. Cần integration test với repository/gateway thật hoặc môi trường test tương ứng. Một test chỉ kiểm tra “class có 3 field” hay “method có tên calculateTotal” không xác nhận cohesion; đó là chi tiết triển khai.

## 11. Những trường hợp không nên tách lớp máy móc

| Tình huống | Vì sao vẫn có thể cohesion tốt | Điều nên xem |
|---|---|---|
| **Aggregate/domain entity** có nhiều hành vi | Các hành vi bảo vệ cùng trạng thái và invariant | Đừng biến domain thành anemic model |
| **Application service / coordinator** gọi nhiều phụ thuộc | Các phụ thuộc phục vụ **một use case** | Có đang chứa thuật toán hạ tầng quá sâu không? |
| **Value object** có factory, parse, validate, normalize | Cùng khái niệm và dữ liệu bất biến | Tránh “utils” trộn nhiều loại giá trị |
| **Controller** có nhiều endpoint gần nhau | Cùng một resource hoặc bounded context | Tránh trộn nghiệp vụ và HTTP mapping |
| **Adapter** bao nhiều thao tác của cùng một API | Cùng một ranh giới tích hợp | Tránh lộ trực tiếp implementation vào domain |
| **Startup/composition root** tạo nhiều đối tượng | Mục đích chính là lắp ghép ứng dụng | Giữ wiring; không nhồi business rules |

Ví dụ `Money` có các phép cộng, trừ, nhân, quy đổi/định dạng cơ bản; không vì nhiều phương thức mà kết luận cần nhiều lớp. Tuy nhiên quy đổi tiền tệ phụ thuộc tỷ giá thời gian thực thường nên do một cộng tác viên có trách nhiệm riêng cung cấp, thay vì làm một value object bất biến phải gọi HTTP.

## 12. Cohesion và hiệu năng, thread safety, dữ liệu

Cohesion cao thường giúp cô lập thay đổi, nhưng **không tự bảo đảm** tốc độ chạy, an toàn luồng hoặc tránh mất dữ liệu:

- `Cart` ví dụ dùng `ArrayList` mutable và không thread-safe. Với cart trong session chỉ do một luồng chỉnh sửa tại mỗi thời điểm, có thể chấp nhận. Nếu nhiều request đồng thời thay đổi cùng cart, cần cơ chế đồng bộ hoặc thiết kế bất biến.
- Tách repository vào lớp riêng không làm giao dịch DB tự động nguyên tử. Transaction boundary nằm ở use case hoặc tầng phù hợp theo framework và nghiệp vụ.
- Nếu tính total nhiều lần trên danh sách lớn, có thể cần cache kết quả kèm invalidation khi `addLine()`. Nhưng tối ưu hóa phải dựa trên đo đạc, không phá invariant chỉ để giảm số dòng.
- `BigDecimal` được dùng cho tiền để tránh lỗi nhị phân của `double`; ứng dụng thật còn cần thống nhất currency, scale và rounding policy.

**Thiết kế lớp tốt là sự cân bằng:** cohesion cao, coupling được quản lý, invariants được bảo vệ, API dễ đọc và mức phức tạp phù hợp phạm vi bài toán.

## 13. Bài tập: cải thiện cohesion của UserManager

Cho lớp giả định có API:

~~~java
class UserManager {
    void register(String email, String password) { /* ... */ }
    boolean verifyPassword(String email, String password) { /* ... */ }
    void exportAllUsersToCsv(String path) { /* ... */ }
    void emailMonthlyNewsletter() { /* ... */ }
    long calculateRevenueForMonth(int year, int month) { /* ... */ }
}
~~~

**Yêu cầu:** Hãy phân nhóm method theo chủ thể thay đổi; đề xuất các lớp như `RegistrationService`, `PasswordVerifier`, `UserReportExporter`, `NewsletterService` và `RevenueReportService` **chỉ khi** ranh giới đó thực sự đúng trong domain. Phác thảo sơ đồ phụ thuộc; không để mọi lớp quay lại tham chiếu `UserManager` như một “god service” trá hình.

Viết tối thiểu các test sau:

1. Đăng ký hợp lệ và xác thực mật khẩu đúng quy tắc.
2. Xuất CSV không phụ thuộc SMTP; gửi newsletter không yêu cầu mở file CSV.
3. Quy tắc doanh thu thay đổi không làm thay đổi logic đăng ký và xác thực.
4. Use case điều phối vẫn có thể chạy từ một composition root rõ ràng mà không xuất hiện vòng phụ thuộc.

**Tự đánh giá:** Bạn có thể nói một câu ngắn giải thích trách nhiệm của từng lớp mới không? Phương thức và trạng thái cần bảo vệ một invariant có ở cùng chủ thể không? Đường đi từ một use case tới các cộng tác viên có dễ lần theo không?

---

**Ghi nhớ:** *Cohesion cao* là các phần bên trong lớp **cùng phục vụ một trách nhiệm có ý nghĩa**, vì vậy thay đổi nghiệp vụ dễ khoanh vùng và kiểm thử độc lập. Đánh giá cohesion phải dựa vào **ngữ nghĩa, invariant và lý do thay đổi**, không chỉ tên lớp, số method, số field hay điểm LCOM.