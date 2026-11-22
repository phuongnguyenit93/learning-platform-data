# Nhận diện giới hạn khi mã lắp ghép lớn và cần được tổ chức lại

**Dependency Injection (DI) thủ công** là cách chương trình Java tự tạo, chọn và truyền các đối tượng phụ thuộc tại **composition root**, thay vì giao công việc đó cho DI container. Đây là cách tốt để hiểu **Inversion of Control (IoC)**: lớp nghiệp vụ chỉ nhận và sử dụng collaborator; mã khởi động chịu trách nhiệm xây dựng đồ thị đối tượng.

Khi ứng dụng còn nhỏ, composition root có thể chỉ vài dòng. Nhưng lúc xuất hiện nhiều module, nhiều cấu hình môi trường, tài nguyên có vòng đời khác nhau và nhiều entry point, đoạn mã lắp ghép dễ phình to. Giới hạn đáng quan tâm lúc này là **khả năng hiểu, thay đổi và kiểm chứng việc lắp ghép**, chứ không phải một con số cố định về số dòng hoặc số dependency.

Bài học trong chương **DI thủ công** giúp bạn nhận biết khi nào cần tổ chức lại mã wiring, cách tách các đồ thị con mà vẫn giữ composition root rõ ràng, kiểm soát scope/vòng đời và quyết định lúc nào một DI container có thể đem lại giá trị thực tế. Các ví dụ đều dùng Java thuần trước khi mở rộng sang framework.

Sau bài này, bạn có thể:

- Nhận diện những tín hiệu cho thấy mã khởi tạo và nối dependency đang khó bảo trì.
- Phân biệt việc **lắp ghép** đối tượng với việc **thực hiện nghiệp vụ** và với việc **quản lý tài nguyên**.
- Tổ chức mã lắp ghép thành các phần theo nhóm trách nhiệm, không đưa cơ chế khởi tạo trở lại service nghiệp vụ.
- Kiểm tra đường đi cấu hình, thứ tự tạo, scope, vòng đời và các sai sót trong đồ thị.
- Sử dụng fake để kiểm thử service và kiểm tra quá trình lắp ghép ở mức cần thiết.
- Đánh giá khi nào tiếp tục dùng DI thủ công và khi nào cân nhắc DI container.

## 1. Một composition root nhỏ có thể lớn lên như thế nào?

Giả sử ứng dụng xử lý đơn hàng bắt đầu với một service và hai adapter:

~~~java
OrderRepository orders = new InMemoryOrderRepository();
PaymentGateway payments = new DemoPaymentGateway();
CheckoutService checkout = new CheckoutService(orders, payments);
~~~

Về mặt thiết kế, đây là DI thủ công: phần bên ngoài tạo dependency và truyền qua constructor. Nhưng theo thời gian, ứng dụng có thể cần thêm:

- Cấu hình theo môi trường: địa chỉ API, giới hạn tiền, timeout, chiến lược retry.
- Các adapter lưu trữ, thanh toán, thông báo và audit.
- Những đối tượng chia sẻ tài nguyên như HTTP client, connection pool hoặc scheduler.
- Các use case có nhiều collaborator chung, chẳng hạn thanh toán, hoàn tiền và xuất báo cáo.
- Entry point khác nhau: command line, HTTP server, batch job, consumer xử lý sự kiện.
- Các phạm vi đối tượng khác nhau: dùng chung toàn ứng dụng, riêng mỗi request hoặc riêng mỗi lần chạy công việc.

Một composition root có thể biến thành đoạn mã như sau. Đây là **minh họa rút gọn**, tên các lớp được giải thích trong ví dụ chạy được ở phần sau:

~~~java
AppConfig config = new AppConfig("BIEN_NHAN", 500_000);
LocalAuditTrail audit = new LocalAuditTrail();
Clock clock = Clock.systemUTC();

OrderRepository orders = new InMemoryOrderRepository();
PaymentGateway payments = new DemoPaymentGateway(clock, audit);
ReceiptSender receipts =
        new ConsoleReceiptSender(config.receiptPrefix());
AmountRule rule = new MaxAmountRule(config.maxAmountCents());

CheckoutService checkout =
        new CheckoutService(orders, payments, receipts, rule);
// Khi có nhiều use case khác, danh sách tiếp tục dài thêm.
~~~

Đoạn trên chưa sai chỉ vì nó dài. Vấn đề xuất hiện khi một thay đổi nhỏ, chẳng hạn đổi cách tạo HTTP client, buộc chỉnh ở nhiều nơi hoặc người đọc không còn biết dependency nào dùng chung, dependency nào được tạo riêng, ai chịu trách nhiệm đóng tài nguyên.

**Kích thước mã là tín hiệu để quan sát; mức độ ghép nối và lỗi trong wiring mới là vấn đề cần giải quyết.**

## 2. Dấu hiệu mã lắp ghép cần được tổ chức lại

| Dấu hiệu | Điều có thể đang xảy ra | Hậu quả |
| --- | --- | --- |
| `main` hoặc bootstrap có hàng trăm phép tạo đối tượng không được nhóm | Nhiều đồ thị con nằm xen kẽ trong một khối mã | Khó theo dõi thay đổi và phát hiện lắp nhầm |
| Cùng một đoạn `new Client(...)` lặp lại ở nhiều entry point | Quy tắc tạo adapter bị sao chép | Mỗi môi trường dễ có cấu hình và vòng đời khác nhau |
| Một service nghiệp vụ bắt đầu gọi `new Repository(...)` hoặc đọc biến môi trường | Mã wiring đã rò vào nghiệp vụ | Test khó tách hạ tầng và thay adapter |
| Cấu hình `if (env...)` xuất hiện rải rác ở nhiều lớp | Quyết định chọn triển khai không tập trung | Khó bảo đảm mọi môi trường lắp cùng hợp đồng |
| Một dependency cần đóng nhưng không rõ ai tạo và đóng | Quyền sở hữu tài nguyên không tường minh | Có thể rò tài nguyên hoặc đóng đối tượng đang được chia sẻ |
| Có nhiều kiểu scope nhưng cùng một đối tượng bị dùng khắp nơi | Vòng đời được chọn theo sự tiện tay | Rò trạng thái giữa request hoặc lỗi đồng thời |
| Lỗi thiếu dependency chỉ lộ ra ở luồng nghiệp vụ hiếm gặp | Đồ thị chưa được kiểm tra khi khởi động | Sự cố xảy ra muộn, khó truy nguyên |
| Muốn unit test phải khởi động toàn bộ ứng dụng | Ranh giới tạo đối tượng quá cứng | Test chậm, khó dựng fake và lỗi khó cô lập |
| Một vòng phụ thuộc buộc dùng setter hoặc field để “nối sau” | Ranh giới trách nhiệm giữa các service chưa rõ | Đối tượng có thể chưa sẵn sàng hoặc khó kiểm soát |

Để quyết định có cần refactor, hãy thử trả lời những câu hỏi cụ thể:

1. Nếu thay triển khai `PaymentGateway`, phải sửa bao nhiêu điểm lắp ghép?
2. Nếu thêm một collaborator vào `CheckoutService`, có những entry point nào cần chỉnh?
3. Có thể nhìn vào composition root để biết ai tạo, ai sở hữu và ai đóng client dùng chung không?
4. Có thể tạo riêng `CheckoutService` với fake bằng Java thuần không?
5. Nếu khởi tạo giữa chừng thất bại, các tài nguyên đã tạo trước đó được xử lý thế nào?

Khi câu trả lời trở nên khó xác định, mã lắp ghép cần được tổ chức lại dù chương trình vẫn biên dịch.

## 3. Giữ ranh giới composition root khi tách mã

**Composition root** là ranh giới logic nơi chương trình chọn các implementation, xây dựng object graph và bàn giao đối tượng đã sẵn sàng cho luồng chạy. Composition root **không bắt buộc là một phương thức dài duy nhất**; nó có thể gọi những hàm dựng đồ thị con nằm ở các lớp hỗ trợ.

Một cách tổ chức thường hữu ích là tách:

1. **Cấu hình đã được xác thực:** các giá trị cần thiết để chọn và tạo dependency.
2. **Infrastructure assembly:** tạo adapter và các dependency hạ tầng dùng chung.
3. **Application assembly:** nối các adapter vào service/use case.
4. **Application runtime:** giữ các đối tượng đầu vào và quyền sở hữu tài nguyên cần đóng.

~~~mermaid
flowchart TB
    Entry["main / bootstrap"] --> Config["AppConfig: cấu hình đã xác thực"]
    Entry --> Resources["Tài nguyên dùng chung"]
    Config --> Infra["InfrastructureAssembly"]
    Resources --> Infra
    Infra --> Graph["InfrastructureGraph: các adapter"]
    Config --> App["ApplicationAssembly"]
    Graph --> App
    App --> Service["CheckoutService"]
    Entry --> Runtime["AppRuntime: giữ service và đóng tài nguyên"]
    Service --> Runtime
    Resources --> Runtime
~~~

Ý nghĩa của cách chia này:

- **Entry point** vẫn là nơi thể hiện toàn cảnh quá trình lắp ghép; nó có thể gọi nhiều hàm assembly nhỏ.
- **Assembly** chỉ biết tạo và nối dependency. Nó không nên xử lý đơn hàng, tính giá hoặc thực hiện use case.
- **Các service nghiệp vụ** nhận collaborator qua constructor. Chúng không biết container, assembly hoặc đường đi cấu hình khởi động.
- **Runtime/lifecycle owner** giải phóng tài nguyên thuộc quyền sở hữu của ứng dụng khi kết thúc vòng đời tương ứng.

Một lớp assembly có thể là tập hợp phương thức tĩnh đơn giản. Không cần lập tức tạo một framework tự viết, service locator toàn cục hay hàng loạt interface factory chỉ để bao bọc mỗi toán tử `new`.

## 4. Ví dụ Java 17: chia một đồ thị lắp ghép thành hai nhóm

Ví dụ sau giữ một ứng dụng nhỏ, nhưng mô phỏng tình huống có nhiều loại dependency: kho lưu đơn, cổng thanh toán, bộ gửi biên nhận, quy tắc giới hạn số tiền, clock và audit. Mục tiêu là **quan sát cấu trúc lắp ghép**. Các adapter chỉ mô phỏng bằng bộ nhớ và console, không thu tiền thật hoặc gửi email thật.

Lưu toàn bộ đoạn mã vào `Main.java` và chạy bằng Java 17 trở lên.

~~~java
import java.time.Clock;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

// Cấu hình được xác thực ở ranh giới khởi tạo.
record AppConfig(String receiptPrefix, long maxAmountCents) {
    AppConfig {
        if (receiptPrefix == null || receiptPrefix.isBlank()) {
            throw new IllegalArgumentException("Receipt prefix is required");
        }
        if (maxAmountCents <= 0) {
            throw new IllegalArgumentException("Maximum must be positive");
        }
    }
}

record Order(String id, long amountCents) {
    Order {
        if (id == null || id.isBlank() || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

record Receipt(String reference) {}

// Các hợp đồng mà phần nghiệp vụ cần.
interface OrderRepository {
    void save(Order order);
}

interface PaymentGateway {
    Receipt charge(Order order);
}

interface ReceiptSender {
    void send(Order order, Receipt receipt);
}

interface AmountRule {
    void validate(Order order);
}

final class MaxAmountRule implements AmountRule {
    private final long maximum;

    MaxAmountRule(long maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException("Invalid maximum");
        }
        this.maximum = maximum;
    }

    @Override
    public void validate(Order order) {
        if (order.amountCents() > maximum) {
            throw new IllegalArgumentException("Order amount too large");
        }
    }
}

// Tài nguyên minh họa: phải đóng khi ứng dụng kết thúc.
final class LocalAuditTrail implements AutoCloseable {
    private boolean closed;

    void record(String message) {
        if (closed) {
            throw new IllegalStateException("Audit trail is closed");
        }
        System.out.println("AUDIT: " + message);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("AUDIT CLOSED");
        }
    }
}

// Những adapter cụ thể thuộc nhóm hạ tầng.
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        if (orders.putIfAbsent(order.id(), order) != null) {
            throw new IllegalStateException("Duplicate order: " + order.id());
        }
    }
}

final class DemoPaymentGateway implements PaymentGateway {
    private final Clock clock;
    private final LocalAuditTrail audit;

    DemoPaymentGateway(Clock clock, LocalAuditTrail audit) {
        this.clock = Objects.requireNonNull(clock);
        this.audit = Objects.requireNonNull(audit);
    }

    @Override
    public Receipt charge(Order order) {
        audit.record("Simulated charge for " + order.id());
        return new Receipt(
                "DEMO-" + order.id() + "-"
                        + clock.instant().getEpochSecond());
    }
}

final class ConsoleReceiptSender implements ReceiptSender {
    private final String prefix;

    ConsoleReceiptSender(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public void send(Order order, Receipt receipt) {
        System.out.println(
                prefix + ": " + order.id() + " / " + receipt.reference());
    }
}

// Use case nhận các collaborator; không tự dựng object graph.
final class CheckoutService {
    private final OrderRepository orders;
    private final PaymentGateway payments;
    private final ReceiptSender receipts;
    private final AmountRule amountRule;

    CheckoutService(
            OrderRepository orders,
            PaymentGateway payments,
            ReceiptSender receipts,
            AmountRule amountRule) {
        this.orders = Objects.requireNonNull(orders);
        this.payments = Objects.requireNonNull(payments);
        this.receipts = Objects.requireNonNull(receipts);
        this.amountRule = Objects.requireNonNull(amountRule);
    }

    Receipt checkout(Order order) {
        Objects.requireNonNull(order, "order");
        amountRule.validate(order);

        Receipt receipt = payments.charge(order);
        orders.save(order);
        receipts.send(order, receipt);
        return receipt;
    }
}

// Một nhóm các adapter đã tạo sẵn, chỉ dùng trong lớp lắp ghép.
record InfrastructureGraph(
        OrderRepository orders,
        PaymentGateway payments,
        ReceiptSender receipts) {}

// Phần assembly hạ tầng: tạo các dependency thuộc cùng nhóm.
final class InfrastructureAssembly {
    static InfrastructureGraph build(
            AppConfig config,
            Clock clock,
            LocalAuditTrail audit) {
        OrderRepository orders = new InMemoryOrderRepository();
        PaymentGateway payments = new DemoPaymentGateway(clock, audit);
        ReceiptSender receipts =
                new ConsoleReceiptSender(config.receiptPrefix());
        return new InfrastructureGraph(orders, payments, receipts);
    }
}

// Phần assembly ứng dụng: gắn adapter với use case.
final class ApplicationAssembly {
    static CheckoutService build(
            AppConfig config,
            InfrastructureGraph infrastructure) {
        AmountRule rule = new MaxAmountRule(config.maxAmountCents());

        return new CheckoutService(
                infrastructure.orders(),
                infrastructure.payments(),
                infrastructure.receipts(),
                rule);
    }
}

// Runtime nắm quyền sở hữu tài nguyên được tạo khi bootstrap.
record AppRuntime(
        CheckoutService checkout,
        LocalAuditTrail audit) implements AutoCloseable {
    @Override
    public void close() {
        audit.close();
    }
}

// Composition root: giữ cái nhìn tổng thể về quá trình lắp ghép.
public class Main {
    static AppRuntime assemble(AppConfig config) {
        Objects.requireNonNull(config, "config");
        LocalAuditTrail audit = new LocalAuditTrail();

        try {
            InfrastructureGraph infrastructure =
                    InfrastructureAssembly.build(
                            config, Clock.systemUTC(), audit);

            CheckoutService checkout =
                    ApplicationAssembly.build(config, infrastructure);

            return new AppRuntime(checkout, audit);
        } catch (RuntimeException | Error failure) {
            // Nếu bootstrap lỗi, không để tài nguyên vừa tạo bị bỏ quên.
            audit.close();
            throw failure;
        }
    }

    public static void main(String[] args) {
        AppConfig config = new AppConfig("BIEN_NHAN", 500_000);

        try (AppRuntime runtime = assemble(config)) {
            runtime.checkout().checkout(new Order("ORD-01", 125_000));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Đầu ra minh họa (phần thời gian trong mã biên nhận thay đổi theo lúc chạy):

~~~text
AUDIT: Simulated charge for ORD-01
BIEN_NHAN: ORD-01 / DEMO-ORD-01-<epoch-second>
AUDIT CLOSED
~~~

Trong bài này, `LocalAuditTrail` chỉ in ra console và trạng thái đóng để dễ quan sát lifecycle. Hệ thống thực tế có thể sở hữu file writer, HTTP client, thread pool hoặc connection pool; cần chính sách đóng riêng cho từng loại tài nguyên.

### Vì sao thiết kế này dễ mở rộng hơn?

**Main** chỉ trình bày luồng tổng quát: có cấu hình, có tài nguyên audit, tạo đồ thị hạ tầng, tạo use case và đưa nó vào runtime. **InfrastructureAssembly** tập trung logic tạo adapter. **ApplicationAssembly** tập trung nối adapter với các chính sách/use case. `CheckoutService` vẫn chỉ biết các interface `OrderRepository`, `PaymentGateway`, `ReceiptSender` và `AmountRule`.

Giả sử sau này có `HttpPaymentGateway` phụ thuộc thêm HTTP client và timeout. Thay đổi thuộc về phần xây dựng payment adapter và các cấu hình liên quan. Nếu hợp đồng `PaymentGateway` không đổi, logic `CheckoutService` không cần biết HTTP client được tạo thế nào.

Điều này minh họa **Dependency Inversion Principle (DIP)**: phần nghiệp vụ phụ thuộc abstraction, còn adapter và mã assembly phụ thuộc vào các kiểu cần thiết để cung cấp abstraction đó. **DI** là thao tác truyền đối tượng vào constructor. Việc tách assembly thành nhóm chỉ tổ chức lại nhiệm vụ của composition root, không tạo một tầng nghiệp vụ mới.

## 5. Cách tách nhóm lắp ghép mà không tạo “framework thu nhỏ”

Có nhiều cách tổ chức hợp lệ. Hãy chọn mức đơn giản nhất phù hợp với mức độ thay đổi thực tế.

| Quy mô và tình huống | Cách tổ chức | Khi nào đủ dùng? |
| --- | --- | --- |
| Ứng dụng vài dependency | Một `main` và các constructor rõ ràng | Đọc một lần hiểu được toàn đồ thị |
| Một số đồ thị con lặp lại | Các phương thức `createStorage(...)`, `createPayment(...)` | Việc đặt tên các bước làm trình tự dễ đọc |
| Nhiều nhóm hạ tầng và use case | `InfrastructureAssembly`, `ApplicationAssembly` hoặc factory theo nhóm | Các phần có trách nhiệm và cấu hình riêng |
| Nhiều entry point dùng chung adapter | Hàm assembly tái sử dụng, với composition root riêng cho mỗi entry point | Tránh lặp quy tắc tạo client và xử lý lifecycle |
| Nhiều scope, provider và rule lựa chọn triển khai | Xem xét DI container sau khi hiểu đồ thị và hợp đồng | Khối lượng wiring thủ công vượt lợi ích kiểm soát trực tiếp |

Một quy tắc giúp tránh quá mức: **tách theo một nhóm dependency có quan hệ thực sự**, chẳng hạn thanh toán hoặc lưu trữ, thay vì bắt buộc tạo một factory riêng cho mỗi lớp.

Các hàm assembly nên có **đầu vào tường minh**: cấu hình cần dùng, tài nguyên chia sẻ, hoặc những port đã tạo. Không nên lấy thông tin từ singleton toàn cục hoặc biến tĩnh có thể thay đổi tùy thời điểm vì như vậy chỉ chuyển sự khó hiểu sang nơi khác.

### Composition root vẫn cần là ranh giới logic rõ ràng

Sau khi tách mã, không nên để các service nghiệp vụ tự gọi `InfrastructureAssembly.build(...)`. Nếu điều đó xảy ra, việc tạo dependency lại chui vào code thực thi use case và phá mục tiêu IoC.

Cũng không nên tạo một `Factory.get("payment")` toàn cục để service tự tìm phụ thuộc:

~~~java
// Không khuyến khích trong service nghiệp vụ.
PaymentGateway gateway =
        (PaymentGateway) GlobalServices.get("paymentGateway");
~~~

Kiểu **service locator** trên khiến dependency bị ẩn khỏi constructor, dùng string key và ép kiểu, đồng thời buộc service biết cơ chế tìm dịch vụ. Khi cần thêm dependency, hãy khai báo nó qua constructor và để composition root điều chỉnh cách lắp ghép.

Factory hợp lệ vẫn có chỗ đứng: chẳng hạn một **factory được inject rõ ràng qua constructor** để tạo đối tượng có vòng đời ngắn theo dữ liệu tại thời điểm chạy. Đó là một nhu cầu khác với việc cả ứng dụng truy cập kho dịch vụ toàn cục.

## 6. Tổ chức cấu hình cùng với mã lắp ghép

Khi có nhiều môi trường (development, test, production), logic chọn adapter và giá trị cấu hình rất dễ bị phân tán. Một cách làm sáng rõ là:

1. Đọc các nguồn cấu hình ở ranh giới khởi động.
2. Chuyển chúng sang kiểu dữ liệu có ý nghĩa, ví dụ `AppConfig` chứa giới hạn tiền dạng `long`.
3. Xác thực giá trị bắt buộc càng sớm càng tốt.
4. Chỉ truyền cấu hình mà phần assembly tương ứng thực sự cần.
5. Dùng cấu hình để **chọn implementation** ở composition root, không để service tự suy đoán môi trường.

Ví dụ đối với hạ tầng thanh toán:

~~~java
// Minh họa lựa chọn ở composition root; các kiểu là giả định.
PaymentGateway payment =
        config.useSandbox()
            ? new SandboxPaymentGateway(config.sandboxEndpoint())
            : new RealPaymentGateway(
                    sharedHttpClient, config.productionEndpoint());
~~~

Đoạn này không phải chương trình Java độc lập; nó diễn đạt vị trí thích hợp cho quyết định chọn adapter. Không nên đưa biểu thức lựa chọn vào `CheckoutService`, vì đó là chính sách lắp ghép theo môi trường, không phải quy tắc xử lý đơn hàng.

**Tránh biến cấu hình thành dependency “vạn năng”.** Nếu một adapter chỉ cần timeout, truyền thẳng giá trị hoặc cấu hình chuyên biệt của adapter có thể rõ hơn việc truyền `AppConfig` khổng lồ, khiến adapter được quyền đọc hàng chục thông số không liên quan.

### Kiểm tra đồ thị trước khi phục vụ yêu cầu

Một composition root nên phát hiện sớm những lỗi có thể xác định lúc khởi động:

- Cấu hình bắt buộc rỗng hoặc ngoài khoảng hợp lệ.
- Thiếu triển khai cho một dependency bắt buộc.
- Vòng phụ thuộc trong constructor hoặc nhánh khởi tạo không thể hoàn tất.
- Tài nguyên chia sẻ được cấp không tương thích với vòng đời của bên sử dụng.
- Adapter không khởi tạo được do cấu hình sai.

Không cần chủ động kết nối tới mọi hệ thống ngoài ngay lúc bootstrap trong mọi ứng dụng. Quyết định kiểm tra kết nối sớm hay trễ phụ thuộc yêu cầu availability và vận hành. Tuy nhiên, các bất biến có thể kiểm tra bằng Java thuần như `null`, giá trị sai và thiếu cấu hình nên được xử lý trước khi trả object graph cho luồng nghiệp vụ.

## 7. Scope và vòng đời trở nên quan trọng khi đồ thị lớn

Một trong những lý do mạnh nhất để tổ chức lại wiring là **không còn biết đối tượng nào sống bao lâu**.

| Scope | Ví dụ | Rủi ro khi lắp nhầm |
| --- | --- | --- |
| **Dùng chung toàn ứng dụng** | Client không giữ trạng thái request, bộ cấu hình bất biến | Nếu không an toàn đa luồng, các request có thể ảnh hưởng nhau |
| **Mỗi request** | Thông tin xác thực hoặc trạng thái chỉ của một lần gọi | Nếu inject vào singleton, dữ liệu request có thể bị giữ quá lâu |
| **Mỗi tác vụ** | Bộ tích lũy kết quả cho một công việc | Nếu chia sẻ vô tình, các tác vụ ghi vào trạng thái của nhau |
| **Tài nguyên cần đóng** | Writer, pool, client, scheduler | Nếu không có owner rõ ràng, dễ rò hoặc đóng quá sớm |

Trong ví dụ chạy được, `Main.assemble` tạo một `LocalAuditTrail`, dùng nó để dựng payment adapter và trả về `AppRuntime` nắm quyền đóng. `CheckoutService` được truyền gateway để sử dụng nhưng không chịu trách nhiệm gọi `audit.close()`.

Nếu bootstrap gặp lỗi sau khi tài nguyên được tạo, nhánh `catch` đóng tài nguyên trước khi ném lại lỗi. Trong ứng dụng nhiều tài nguyên, có thể dùng một cấu trúc quản lý thứ tự đóng ngược với thứ tự tạo, hoặc các lớp `AutoCloseable` được kết hợp có chủ đích. Không nên tạo tài nguyên rồi bỏ quên khi một constructor phía sau ném exception.

**Không phải cứ object được inject là nên dùng chung.** Ví dụ `InMemoryOrderRepository` trong bài giữ `HashMap`; chương trình console minh họa chạy tuần tự, nhưng chưa thiết kế an toàn cho server đa luồng. Composition root phải chọn implementation và scope tương thích với cách đối tượng sẽ được sử dụng.

### Cẩn thận với phụ thuộc vòng đời ngắn trong đối tượng sống lâu

Giả sử một service singleton giữ `RequestContext` của một request trong field. Khi request kết thúc, object đó có thể vẫn giữ thông tin cũ hoặc dùng nhầm request. Thay vì dùng `new RequestContext()` bên trong service để vá lỗi, hãy thiết kế ranh giới đúng: truyền `RequestContext` vào từng phương thức khi đó là dữ liệu của lời gọi, hoặc inject một factory/provider rõ ràng khi cần tạo đối tượng theo scope.

Một DI container có thể hỗ trợ các scope này, nhưng việc container tự lắp ghép **không tự bảo đảm** rằng lựa chọn scope đã đúng về mặt nghiệp vụ hay an toàn luồng.

## 8. Kiểm thử với các điểm thay thế tường minh

Khi tách assembly, chúng ta muốn giữ hai khả năng kiểm thử độc lập:

- **Kiểm thử nghiệp vụ:** tạo service với fake, không khởi động network, database hoặc cả application runtime.
- **Kiểm tra lắp ghép:** bảo đảm entry point tạo được đồ thị dự kiến và tài nguyên được quản lý đúng. Đây có thể là một smoke test hoặc integration test khi cần.

Trong ví dụ, `ApplicationAssembly.build` nhận `InfrastructureGraph` chứa các interface. Ta có thể cấp fake mà không cần dựng `LocalAuditTrail` hay dùng `InfrastructureAssembly`.

Lưu đoạn sau vào `CheckoutWiringTest.java` cùng thư mục với `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CheckoutWiringTest {
    public static void main(String[] args) {
        List<String> calls = new ArrayList<>();

        OrderRepository orders =
                order -> calls.add("save:" + order.id());

        PaymentGateway payments = order -> {
            calls.add("charge:" + order.id());
            return new Receipt("TEST-" + order.id());
        };

        ReceiptSender receipts = (order, receipt) ->
                calls.add("receipt:" + receipt.reference());

        InfrastructureGraph fakes =
                new InfrastructureGraph(orders, payments, receipts);

        CheckoutService checkout = ApplicationAssembly.build(
                new AppConfig("TEST", 100_000), fakes);

        checkout.checkout(new Order("T-01", 50_000));

        List<String> expected = List.of(
                "charge:T-01",
                "save:T-01",
                "receipt:TEST-T-01");

        if (!calls.equals(expected)) {
            throw new AssertionError("Unexpected call order: " + calls);
        }

        boolean rejected = false;
        try {
            checkout.checkout(new Order("T-02", 120_000));
        } catch (IllegalArgumentException expectedError) {
            rejected = true;
        }

        if (!rejected || !calls.equals(expected)) {
            throw new AssertionError(
                    "Invalid amount must be rejected before dependencies");
        }

        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java CheckoutWiringTest.java
java CheckoutWiringTest
~~~

Kết quả dự kiến: `PASS`.

Phép thử xác minh service gọi ba collaborator đúng thứ tự và không thực hiện tác dụng phụ khi số tiền vượt giới hạn. **Đây là test nghiệp vụ với fake**, không chứng minh rằng gateway, database hoặc runtime thật hoạt động đúng.

Ở mức smoke test wiring, một cách khác là gọi `Main.assemble(config)` trong `try-with-resources`, xác minh `AppRuntime` có service sử dụng được và kiểm tra hành vi đóng tài nguyên theo nhu cầu. Test này không cần lặp lại mọi quy tắc nghiệp vụ đã được kiểm tra bằng fake.

## 9. Những thay đổi dễ làm đồ thị phức tạp trở lại

### 9.1. Vòng phụ thuộc giữa hai service

~~~text
OrderService -> PaymentService -> OrderService
~~~

Nếu hai service đều yêu cầu nhau trong constructor, composition root không có trình tự xây dựng đơn giản. Dùng setter/field injection sau khi tạo có thể che giấu một đối tượng đang ở trạng thái chưa sẵn sàng.

Hướng giải quyết thường là xem lại trách nhiệm: trích xuất một hợp đồng nhỏ hơn, chuyển việc điều phối lên một use case cấp trên hoặc đưa dữ liệu cần thiết qua phương thức. Đừng tự động chọn “inject sau” chỉ để làm đồ thị biên dịch.

### 9.2. Lặp lại cùng một quyết định ở nhiều entry point

Nếu HTTP server và batch job đều tạo `DemoPaymentGateway` với cùng clock, audit, retry và cấu hình, hãy đưa quy tắc tạo adapter vào một assembly được gọi từ **hai composition root tương ứng**. Mỗi entry point vẫn phải quyết định vòng đời của các tài nguyên nó sở hữu.

### 9.3. Một factory trở thành service locator

Nếu factory vừa tạo mọi đối tượng, vừa trả về `Object` theo string key, vừa bị gọi tùy ý từ nghiệp vụ, nó làm mờ dependency. Factory tốt nên có đầu vào/đầu ra có kiểu rõ ràng và được gọi trong ranh giới lắp ghép hoặc được inject như một hợp đồng tạo đối tượng cụ thể.

### 9.4. Mã khởi tạo thực thi nghiệp vụ

Composition root không nên tự thu tiền, lưu đơn hoặc quyết định điều kiện chấp nhận đơn. Trong ví dụ, `Main` có thể gọi `runtime.checkout().checkout(...)` để chạy ứng dụng console, nhưng quy tắc giới hạn tiền và thứ tự gọi collaborator vẫn nằm trong `CheckoutService`.

### 9.5. Thêm lớp trừu tượng cho mọi toán tử `new`

Một factory chỉ bọc `return new Foo()` mà không mang quy tắc tạo hay khả năng thay thế cần thiết có thể khiến người đọc phải nhảy qua nhiều file. Hãy trích xuất khi có một **ý nghĩa lắp ghép** đáng đặt tên: nhóm tài nguyên, chính sách lựa chọn, phạm vi/vòng đời hoặc cấu hình chung.

## 10. Có nên chuyển sang DI container?

Mã lắp ghép lớn **không tự động đồng nghĩa phải dùng DI container**. Một chương trình dùng Java thuần và được chia assembly hợp lý vẫn có thể dễ hiểu, dễ kiểm thử và đủ tốt để vận hành.

| Tiếp tục DI thủ công khi... | Cân nhắc DI container khi... |
| --- | --- |
| Đồ thị đủ nhỏ hoặc có thể chia thành vài nhóm rõ ràng | Có nhiều graph, scope và quy tắc lắp ghép lặp lại |
| Cần hiểu rõ từng bước tạo và vòng đời | Cần cơ chế thống nhất cho lifecycle, cấu hình và chọn implementation |
| Entry point ít, thay đổi không quá thường xuyên | Nhiều entry point/plugin/module cùng cần quy tắc lắp ghép phức tạp |
| Test tạo collaborator bằng constructor rất đơn giản | Chi phí viết wiring thủ công đang chiếm nhiều thời gian bảo trì |
| Không muốn đưa phụ thuộc framework vào bootstrap | Nhóm đã có DI container phù hợp và quy tắc vận hành rõ ràng |

Container có thể cung cấp registration, resolution, scope và lifecycle, nhưng **không thiết kế hợp đồng nghiệp vụ thay bạn**. Một service đang phụ thuộc trực tiếp vào lớp triển khai cụ thể vẫn ghép nối chặt dù được container tạo ra. Container cũng không tự xử lý vòng phụ thuộc không hợp lý, tính nhất quán giao dịch hoặc an toàn luồng.

Một hướng chuyển đổi an toàn là giữ các **constructor tường minh** và các **interface nghiệp vụ**, sau đó thay phần wiring tại composition root bằng cấu hình của container. Khi đó những bài unit test dùng Java thuần và fake vẫn có thể tiếp tục hoạt động.

## 11. Quy trình refactor từ một `main` quá dài

1. **Vẽ đồ thị phụ thuộc hiện tại.** Ghi lại các đối tượng, các cạnh “cần dependency”, nguồn cấu hình và những đối tượng dùng chung.
2. **Tách mã nghiệp vụ bị đặt nhầm ở bootstrap.** Đưa các quy tắc và hành vi use case về lớp nghiệp vụ; giữ mã bootstrap để chọn và nối đối tượng.
3. **Xác định ownership và scope.** Đánh dấu những tài nguyên cần đóng, những đối tượng dùng chung và những object chỉ nên sống trong request/tác vụ.
4. **Đặt tên cho các đồ thị con.** Trích xuất một vài hàm assembly theo nhóm trách nhiệm có ý nghĩa, chẳng hạn `buildPaymentInfrastructure(...)` hoặc `buildOrderApplication(...)`.
5. **Truyền đầu vào rõ ràng.** Cấp typed config, interface hoặc shared resources qua tham số; tránh truy cập registry toàn cục, cấu hình ngầm hoặc mutable singleton.
6. **Giữ entry point đọc được.** Từ `main`, người đọc nên thấy được thứ tự tạo các nhóm, cách nối chúng và đối tượng nào được chạy/đóng.
7. **Kiểm thử theo ranh giới.** Test service với fake; xác minh các lựa chọn wiring và lifecycle quan trọng bằng smoke/integration test thích hợp.
8. **Đánh giá lại mức độ phức tạp.** Nếu lắp ghép vẫn chiếm nhiều công sức, xem xét container dựa trên nhu cầu thực tế về scope, lifecycle và registration.

Đừng chỉ đo số dòng trước và sau refactor. Một kết quả tốt còn phải giúp giảm số nơi cần sửa khi đổi adapter, làm rõ quyền sở hữu tài nguyên và giữ được khả năng test use case độc lập.

## 12. Câu hỏi tự kiểm tra

**Tình huống A:** Một ứng dụng có 40 dependency nhưng toàn bộ được tạo tại một bootstrap dễ đọc, không trùng lặp, và tài nguyên được đóng đúng. Có bắt buộc chuyển sang container?

**Không.** Quy mô là một tín hiệu quan sát; nếu code vẫn rõ ràng, test độc lập được và thay đổi không gây rủi ro đáng kể, DI thủ công vẫn là lựa chọn hợp lệ.

**Tình huống B:** Sau khi chia assembly, `CheckoutService` tự gọi `InfrastructureAssembly.build(...)` khi xử lý request. Cách tách đã đạt mục tiêu chưa?

**Chưa.** Service nghiệp vụ lại phải biết cách dựng dependency. Hãy tạo dependency tại composition root và truyền qua constructor hoặc một factory có hợp đồng rõ ràng nếu cần tạo theo mỗi yêu cầu.

**Tình huống C:** `ApplicationAssembly` tạo một đối tượng dùng chung chứa trạng thái của request gần nhất và đưa nó cho mọi `CheckoutService`. Điều gì cần xét lại?

Cần xem **scope** và **an toàn đa luồng**. Nếu trạng thái thuộc từng request, không nên chia sẻ một instance trên tất cả request. Phải xác định ranh giới chứa trạng thái hoặc cơ chế cấp đối tượng phù hợp.

**Tình huống D:** `HttpClient` được tạo ở composition root rồi truyền cho nhiều adapter. Adapter đầu tiên tự gọi `close()` sau khi xử lý yêu cầu. Có vấn đề gì?

**Có thể có.** Nếu client thuộc sở hữu của application runtime và được dùng chung, adapter tiêu thụ không nên tự đóng nó. Quy tắc sở hữu và kết thúc vòng đời cần được thể hiện tại nơi lắp ghép.

**Tình huống E:** Một nhóm thấy phải tạo rất nhiều factory nhỏ, mỗi factory chỉ một dòng `new`, nhưng các use case vẫn import trực tiếp adapter kỹ thuật. Nên sửa gì trước?

Hãy xem lại **hướng phụ thuộc** và các hợp đồng use case cần. Việc bọc toán tử `new` trong factory không tự giải quyết ghép nối với hạ tầng hay làm rõ trách nhiệm.

## Ghi nhớ

Giới hạn quan trọng của **DI thủ công** xuất hiện khi **mã lắp ghép khó hiểu, khó thay đổi, khó kiểm tra hoặc khó quản lý vòng đời**. Giữ composition root làm ranh giới logic, chia các đồ thị con theo trách nhiệm, truyền typed config và dependency qua constructor, đồng thời xác định rõ ai tạo và đóng tài nguyên. Khi các quy tắc scope, cấu hình và lựa chọn triển khai ngày càng nhiều, DI container có thể giảm công sức wiring; nền tảng vẫn là những hợp đồng rõ ràng và một đồ thị đối tượng được thiết kế đúng.
