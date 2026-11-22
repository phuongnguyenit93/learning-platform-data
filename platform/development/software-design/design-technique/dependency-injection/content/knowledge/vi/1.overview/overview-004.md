# Tách việc xây dựng đồ thị đối tượng khỏi việc thực hiện nghiệp vụ

Trong một ứng dụng Java, một chức năng hiếm khi hoạt động độc lập. Chẳng hạn, xử lý đơn hàng cần cổng thanh toán, nơi lưu đơn hàng và có thể cả dịch vụ gửi thông báo. Những đối tượng này lại có thể phụ thuộc vào HTTP client, cấu hình hoặc kết nối cơ sở dữ liệu. Tập hợp các đối tượng cùng những quan hệ phụ thuộc giữa chúng được gọi là **đồ thị đối tượng** (object graph).

Một nguyên tắc cốt lõi của **Dependency Injection (DI)** là: **mã thực hiện nghiệp vụ nhận các đối tượng cộng tác đã được chuẩn bị sẵn; mã khởi tạo ứng dụng chịu trách nhiệm chọn, tạo và nối các đối tượng đó với nhau**. Đây là cách ứng dụng Inversion of Control (IoC) vào việc quản lý phụ thuộc. Ta có thể thực hành nguyên tắc này bằng Java thuần, chưa cần DI container.

Sau bài này, bạn có thể:

- Phân biệt giai đoạn *xây dựng/lắp ghép đồ thị đối tượng* với giai đoạn *thực hiện nghiệp vụ*.
- Xác định vị trí đặt mã khởi tạo (composition root) và dùng constructor injection để nối các phụ thuộc.
- Hiểu vì sao cách tách này giúp kiểm thử, thay thế triển khai và quản lý vòng đời dễ hơn.
- Nhận diện lỗi thiết kế thường gặp khi đối tượng nghiệp vụ tự tạo hoặc tự tìm dịch vụ mà nó cần.

## 1. Hai công việc khác nhau thường bị trộn vào một lớp

Giả sử có chức năng thanh toán đơn hàng. Lớp CheckoutService cần một PaymentGateway để thu tiền và một OrderRepository để lưu kết quả.

Cách viết sau khiến CheckoutService tự quyết định cả **sử dụng** lẫn **tạo** phụ thuộc:

~~~java
final class CheckoutService {
    private final PaymentGateway paymentGateway = new DemoPaymentGateway();
    private final OrderRepository orderRepository = new InMemoryOrderRepository();

    // Phương thức checkout(...) sẽ gọi hai đối tượng ở trên.
}
~~~

Đoạn mã này minh họa vấn đề thiết kế, không phải một triển khai thanh toán hoàn chỉnh. CheckoutService đang biết các lớp triển khai cụ thể và gắn chặt với cách tạo chúng. Khi muốn dùng cổng thanh toán thật, thay bộ lưu trữ hoặc đưa đối tượng giả vào kiểm thử, ta phải sửa chính lớp xử lý nghiệp vụ.

Việc trộn hai trách nhiệm còn gây ra các hệ quả khác:

- **Cấu hình bị phân tán:** địa chỉ API, thông tin kết nối và chính sách retry có nguy cơ xuất hiện rải rác trong các service.
- **Vòng đời khó kiểm soát:** nhiều nơi có thể tự tạo client hoặc kết nối đắt đỏ, dù ứng dụng chỉ cần dùng chung một phiên bản.
- **Lỗi lắp ghép xuất hiện muộn:** thiếu cấu hình hoặc tạo phụ thuộc sai có thể chỉ lộ ra khi người dùng thực hiện một thao tác cụ thể.
- **Kiểm thử phụ thuộc vào hạ tầng:** service gắn trực tiếp với mạng hoặc cơ sở dữ liệu sẽ khó kiểm thử logic riêng của nó.

**Tách trách nhiệm** nghĩa là CheckoutService chỉ mô tả nó *cần khả năng gì* và *dùng những khả năng đó thế nào*. Phần khởi động ứng dụng quyết định *đưa triển khai nào vào*.

## 2. Đồ thị đối tượng, composition root và luồng nghiệp vụ

Hãy xem hai giai đoạn khác nhau về thời điểm và trách nhiệm:

| Giai đoạn | Câu hỏi cần trả lời | Công việc điển hình |
| --- | --- | --- |
| **Khởi tạo và lắp ghép** | Dùng triển khai nào? Ai sở hữu? Tạo một hay nhiều phiên bản? | Đọc cấu hình, tạo adapter, nối dependency qua constructor, quyết định scope và vòng đời |
| **Thực hiện nghiệp vụ** | Khi có yêu cầu, cần kiểm tra và thao tác gì? | Kiểm tra đầu vào, gọi cộng tác viên qua interface, xử lý kết quả và quy tắc nghiệp vụ |

**Composition root** là nơi tập trung việc lắp ghép các đối tượng ở ranh giới khởi động ứng dụng. Với chương trình console, đó thường là phương thức main; với ứng dụng web, đó có thể là mã bootstrap do ứng dụng hoặc framework điều phối.

~~~mermaid
flowchart TB
    subgraph Build["Khởi tạo: composition root"]
        Root["main / bootstrap"] -->|"tạo"| Gateway["PaymentGateway implementation"]
        Root -->|"tạo"| Repo["OrderRepository implementation"]
        Root -->|"constructor injection"| Service["CheckoutService"]
        Gateway -.->|"được truyền vào"| Service
        Repo -.->|"được truyền vào"| Service
    end

    Request["Yêu cầu checkout"] -->|"gọi checkout(order)"| Service
    Service -->|"charge(order)"| Gateway
    Service -->|"save(order, receipt)"| Repo
~~~

Các đường ở phần *khởi tạo* thể hiện ai tạo và nối đối tượng. Những lời gọi charge và save ở phần *thực thi* thể hiện đối tượng đã có sẵn được sử dụng ra sao. Phân biệt được hai loại quan hệ này sẽ giúp tránh đưa mã lắp ghép vào giữa luồng nghiệp vụ.

**Đồ thị đối tượng có tính bắc cầu.** Ví dụ, CheckoutService cần PaymentGateway; HttpPaymentGateway lại cần HttpClient; HttpClient có thể cần cấu hình TLS. Composition root cần bảo đảm toàn bộ chuỗi phụ thuộc được cung cấp hợp lệ, dù CheckoutService chỉ biết interface PaymentGateway.

## 3. Constructor injection với Java thuần

Ví dụ dưới đây là chương trình Java 17+ hoàn chỉnh. Các record Order và Receipt biểu diễn dữ liệu; hai interface định nghĩa khả năng cộng tác; CheckoutService không tự tạo PaymentGateway hoặc OrderRepository.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

record Order(String id, long amountInCents) {}
record Receipt(String transactionId) {}

interface PaymentGateway {
    Receipt charge(Order order);
}

interface OrderRepository {
    void save(Order order, Receipt receipt);
}

// Phần nghiệp vụ: nhận phụ thuộc từ bên ngoài.
final class CheckoutService {
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    CheckoutService(
            PaymentGateway paymentGateway,
            OrderRepository orderRepository) {
        this.paymentGateway =
                Objects.requireNonNull(paymentGateway, "paymentGateway");
        this.orderRepository =
                Objects.requireNonNull(orderRepository, "orderRepository");
    }

    Receipt checkout(Order order) {
        if (order == null || order.amountInCents() <= 0) {
            throw new IllegalArgumentException("Số tiền phải lớn hơn 0");
        }

        Receipt receipt = paymentGateway.charge(order);
        orderRepository.save(order, receipt);
        return receipt;
    }
}

// Adapter mô phỏng để chạy ví dụ, KHÔNG thu tiền thật.
final class DemoPaymentGateway implements PaymentGateway {
    @Override
    public Receipt charge(Order order) {
        return new Receipt("demo-" + order.id());
    }
}

// Bộ lưu trữ trong bộ nhớ để chạy ví dụ.
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Receipt> receipts = new HashMap<>();

    @Override
    public void save(Order order, Receipt receipt) {
        receipts.put(order.id(), receipt);
    }

    Receipt findReceipt(String orderId) {
        return receipts.get(orderId);
    }
}

// Composition root: chọn triển khai, tạo và nối đồ thị đối tượng.
public class Main {
    public static void main(String[] args) {
        PaymentGateway gateway = new DemoPaymentGateway();
        InMemoryOrderRepository repository = new InMemoryOrderRepository();

        CheckoutService checkoutService =
                new CheckoutService(gateway, repository);

        Order order = new Order("ORD-001", 125_000);
        Receipt receipt = checkoutService.checkout(order);

        System.out.println(receipt.transactionId());
        System.out.println(
                repository.findReceipt(order.id()).transactionId());
    }
}
~~~

Lưu đoạn mã vào Main.java, sau đó chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả minh họa:

~~~text
demo-ORD-001
demo-ORD-001
~~~

Hãy nhìn rõ ranh giới trách nhiệm:

1. **Main tạo đối tượng** DemoPaymentGateway và InMemoryOrderRepository, rồi truyền chúng vào constructor của CheckoutService. Đây là lúc đồ thị đối tượng được lắp ghép.
2. **CheckoutService sử dụng đối tượng** qua interface: xác thực số tiền, gọi charge, lưu receipt. Nó không biết cổng thanh toán được tạo từ đâu.
3. **Muốn thay triển khai**, composition root có thể truyền một lớp khác cài đặt PaymentGateway hoặc OrderRepository mà không cần sửa thuật toán checkout.

Constructor injection cũng làm cho các phụ thuộc **bắt buộc** trở nên rõ ràng: muốn tạo CheckoutService thì phải cung cấp đủ hai đối tượng. Kiểm tra null ngay trong constructor giúp phát hiện lỗi lắp ghép tại thời điểm khởi tạo.

Trong ví dụ này, DemoPaymentGateway không gọi API thanh toán và InMemoryOrderRepository không ghi cơ sở dữ liệu. Chúng chỉ giúp quan sát cấu trúc DI. Đưa vào môi trường thực tế sẽ cần adapter có hành vi đúng, xử lý lỗi và bảo đảm tính nhất quán dữ liệu theo yêu cầu hệ thống.

## 4. Không cần DI container để thực hiện Inversion of Control

DI là **cách cung cấp phụ thuộc** cho một đối tượng; DI container là **công cụ có thể tự động hóa** việc tạo, nối và quản lý các phụ thuộc đó.

Trong ví dụ trên:

- CheckoutService khai báo các hợp đồng nó cần bằng interface và constructor.
- Main lựa chọn các triển khai và cung cấp chúng.
- Quyền quyết định cách tạo dependency đã chuyển ra khỏi lớp nghiệp vụ. Đây là biểu hiện của IoC trong việc lắp ghép đối tượng.

Về sau, container có thể đọc cấu hình hoặc metadata để thực hiện bước lắp ghép tương tự. Tuy nhiên, container không tự biến một thiết kế phụ thuộc chặt thành thiết kế tốt. Hiểu và thực hành composition root bằng Java thuần trước sẽ giúp bạn nhận ra container thực sự đang làm gì.

**Không phải mọi toán tử new đều sai.** Service vẫn có thể tạo một giá trị nghiệp vụ ngắn hạn, chẳng hạn new Order(...) hoặc một đối tượng kết quả thuần dữ liệu. Điều cần tách ra là việc lựa chọn, cấu hình và quản lý **các dịch vụ cộng tác** có phụ thuộc và vòng đời riêng, đặc biệt là client mạng, repository, adapter hoặc service khác.

## 5. Kiểm thử nghiệp vụ mà không khởi động hạ tầng

Vì CheckoutService nhận hai interface qua constructor, ta có thể đưa các fake đơn giản vào để xác minh hành vi. Ví dụ sau dùng lại Order, Receipt, CheckoutService, PaymentGateway và OrderRepository trong Main.java.

~~~java
final class FakePaymentGateway implements PaymentGateway {
    int callCount;
    Order chargedOrder;

    @Override
    public Receipt charge(Order order) {
        callCount++;
        chargedOrder = order;
        return new Receipt("fake-transaction");
    }
}

final class RecordingOrderRepository implements OrderRepository {
    Order savedOrder;
    Receipt savedReceipt;

    @Override
    public void save(Order order, Receipt receipt) {
        savedOrder = order;
        savedReceipt = receipt;
    }
}

public class CheckoutServiceTest {
    public static void main(String[] args) {
        FakePaymentGateway gateway = new FakePaymentGateway();
        RecordingOrderRepository repository = new RecordingOrderRepository();
        CheckoutService service = new CheckoutService(gateway, repository);

        Order order = new Order("TEST-001", 50_000);
        Receipt receipt = service.checkout(order);

        if (gateway.callCount != 1
                || !order.equals(gateway.chargedOrder)
                || !order.equals(repository.savedOrder)
                || !receipt.equals(repository.savedReceipt)) {
            throw new AssertionError("Checkout không gọi đúng phụ thuộc");
        }

        System.out.println("PASS");
    }
}
~~~

Lưu vào CheckoutServiceTest.java trong cùng thư mục, rồi chạy:

~~~bash
javac Main.java CheckoutServiceTest.java
java CheckoutServiceTest
~~~

Kết quả: PASS.

Phép thử chỉ kiểm tra **quy tắc điều phối của CheckoutService**: gọi cổng thanh toán đúng một lần, truyền đúng đơn hàng và lưu đúng biên nhận. Không cần HTTP, database hay DI framework. Đây là lợi ích trực tiếp của việc tách mã dựng đồ thị đối tượng khỏi mã thực hiện nghiệp vụ.

Bài kiểm thử trên không chứng minh rằng adapter thanh toán thật hoặc repository thật hoạt động đúng. Các thành phần ấy cần kiểm thử tích hợp riêng. Đồng thời, thao tác thu tiền rồi lưu đơn có thể gặp lỗi ở giữa; chiến lược giao dịch, idempotency hoặc xử lý bù trừ là những vấn đề nghiệp vụ cần giải quyết độc lập với kỹ thuật DI.

## 6. Scope và vòng đời thuộc về phần lắp ghép

Khi tạo đối tượng ở composition root, ta cũng phải quyết định **bao lâu một phiên bản được sử dụng** và **ai chịu trách nhiệm giải phóng tài nguyên**.

| Kiểu vòng đời | Ví dụ phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Dùng chung trong thời gian ứng dụng chạy | Service không giữ trạng thái thay đổi, client dùng chung được | Phải an toàn khi có nhiều luồng cùng truy cập |
| Một đối tượng cho mỗi yêu cầu | Request context hoặc dữ liệu gắn với một request | Không giữ request context trong đối tượng sống lâu hơn request |
| Tạo mới cho mỗi thao tác | Bộ tích lũy trạng thái riêng của một tác vụ | Tránh vô tình chia sẻ trạng thái giữa các thao tác |

Trong Java thuần, composition root có thể tạo và truyền đối tượng theo từng nhu cầu; với hệ thống lớn, DI container thường hỗ trợ các scope tương tự. **Scope không phải thuộc tính vốn có của interface**: cùng một interface có thể được cung cấp bằng đối tượng dùng chung hoặc đối tượng tạo riêng, tùy cách lắp ghép.

Ví dụ Main tạo một InMemoryOrderRepository rồi chia sẻ nó với CheckoutService. Phiên bản dùng HashMap trong bài chỉ phù hợp với ví dụ console chạy đơn luồng; nếu nhiều request đồng thời dùng chung thì phải xét an toàn luồng hoặc thay triển khai lưu trữ thích hợp.

Nếu dependency giữ tài nguyên như file, socket hay kết nối, nơi sở hữu việc tạo nó cần quy định rõ thời điểm đóng. Với tài nguyên AutoCloseable do composition root tạo, có thể sử dụng try-with-resources ở ranh giới vòng đời tương ứng. Service không nên tự ý đóng một đối tượng dùng chung mà nó chỉ được truyền vào để sử dụng.

## 7. Những cách viết làm mờ ranh giới

| Dấu hiệu | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Trong service có new ConcreteRepository(...) hoặc tự khởi tạo HTTP client | Nghiệp vụ quyết định triển khai hạ tầng | Truyền dependency từ composition root qua constructor |
| Trong mỗi phương thức có ServiceLocator.get(PaymentGateway.class) | Phụ thuộc bị ẩn, khó nhìn thấy khi đọc constructor | Khai báo PaymentGateway thành tham số constructor |
| Service nhận DI container rồi tự gọi container.get(...) | Service vẫn phải biết cơ chế lắp ghép | Chỉ dùng container ở vùng bootstrap hoặc cấu hình |
| Mọi lớp đều giữ một đối tượng trạng thái dùng chung | Dễ rò rỉ dữ liệu giữa request, lỗi đồng thời | Chọn scope dựa trên trạng thái và vòng đời thật |
| Constructor có quá nhiều dependency không liên quan | Có thể lớp đang gánh nhiều trách nhiệm | Xem lại ranh giới nghiệp vụ trước khi thêm cơ chế DI |
| Tạo vòng phụ thuộc A → B → A | Đồ thị khó hoặc không thể khởi tạo theo constructor | Điều chỉnh phân chia trách nhiệm, trích xuất hợp đồng phù hợp |

Một lỗi tinh vi khác là **biến composition root thành nơi xử lý nghiệp vụ**. Main nên tạo, cấu hình, nối đối tượng và chuyển quyền điều khiển cho tầng ứng dụng. Nó không nên tự tính phí, xác nhận đơn hay thực hiện các quy tắc mà CheckoutService phải phụ trách.

Cũng không nhất thiết phải xây dựng *toàn bộ* đối tượng ngay khi ứng dụng khởi động. Một số dependency có thể được tạo trễ hoặc tạo theo yêu cầu. Ranh giới vẫn giữ nguyên: mã điều phối vòng đời đảm nhận việc tạo, còn mã nghiệp vụ tiêu thụ dependency qua hợp đồng rõ ràng.

## 8. Cách áp dụng khi tách một service đang có

1. **Liệt kê dependency thực sự:** xem service đang tạo các adapter, repository, client nào và mỗi đối tượng có phụ thuộc bắc cầu gì.
2. **Xác định hợp đồng cần dùng:** khai báo interface hoặc kiểu trừu tượng phù hợp ở ranh giới nghiệp vụ; tránh thiết kế interface chỉ để che mọi lớp một cách máy móc.
3. **Chuyển dependency sang constructor:** truyền các đối tượng bắt buộc, lưu bằng trường final, kiểm tra null khi cần.
4. **Tạo và nối tại composition root:** chọn triển khai cho môi trường chạy, cấu hình và quyết định scope/vòng đời tại đây.
5. **Thử bằng fake hoặc stub:** xác minh một tình huống nghiệp vụ mà không bật network/database; sau đó kiểm thử adapter thật ở mức tích hợp.
6. **Rà lại ranh giới:** lớp nghiệp vụ không còn tự tìm hoặc khởi tạo hạ tầng; mã bootstrap không chứa quy tắc nghiệp vụ.

### Tự kiểm tra

**Tình huống A:** CheckoutService cần PaymentGateway và nhận nó qua constructor. Trong checkout(), service tạo một Receipt từ dữ liệu trả về. Có vi phạm DI không?

Không. Việc tạo một giá trị dữ liệu phục vụ nghiệp vụ khác với việc tự chọn và khởi tạo một dịch vụ hạ tầng có vòng đời độc lập.

**Tình huống B:** Một HttpPaymentGateway dùng chung có trạng thái mutable chứa thông tin đơn hàng vừa xử lý. Composition root tạo duy nhất một phiên bản cho tất cả request. Vấn đề có thể là gì?

Các request có thể ghi đè trạng thái của nhau. Cần làm cho adapter an toàn khi dùng chung hoặc chuyển trạng thái theo request vào đối tượng có scope thích hợp. DI giúp quản lý vòng đời, nhưng không tự bảo đảm an toàn luồng.

**Tình huống C:** Đổi từ DemoPaymentGateway sang RealPaymentGateway có nên buộc phải sửa CheckoutService không?

Không, nếu hai lớp cùng tuân theo hợp đồng PaymentGateway và các điều kiện nghiệp vụ cần thiết. Sự thay đổi thường thuộc về phần cấu hình/lắp ghép và các bài kiểm thử tích hợp tương ứng.

**Nguyên tắc cần giữ:** composition root trả lời câu hỏi **“Các đối tượng được tạo, nối và quản lý như thế nào?”**; service nghiệp vụ trả lời câu hỏi **“Các đối tượng đã được cung cấp phối hợp ra sao để hoàn thành yêu cầu?”**. Khi hai trách nhiệm này rõ ràng, constructor injection, quản lý scope và việc mở rộng sang DI container trở nên dễ hiểu và dễ kiểm chứng.
