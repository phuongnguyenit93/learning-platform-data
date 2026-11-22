# Phân biệt đảo ngược phụ thuộc (DIP) và tiêm phụ thuộc (DI)

> **Chủ đề:** OOP → SOLID. Hai khái niệm thường xuất hiện cùng nhau trong Java/Spring, nhưng giải quyết **hai câu hỏi khác nhau**: *Mã nguồn nên phụ thuộc vào ai?* (DIP) và *đối tượng phụ thuộc được cung cấp bằng cách nào?* (DI).

## 1. Định nghĩa đúng bản chất

**Dependency Inversion Principle (DIP)** là chữ **D** trong SOLID. Robert C. Martin mô tả hai ý chính:

1. **Module cấp cao** (nghiệp vụ/chính sách) không nên phụ thuộc trực tiếp vào **module cấp thấp** (cơ sở dữ liệu, email, HTTP client, cổng thanh toán). Cả hai nên phụ thuộc vào **abstraction**.
2. **Abstraction không nên phụ thuộc vào chi tiết triển khai; chi tiết triển khai phải phụ thuộc vào abstraction**.

**Dependency Injection (DI)** là một kỹ thuật cung cấp các dependency cho một đối tượng từ bên ngoài, thường qua **constructor**, **setter** hoặc một cơ chế do container quản lý. Đối tượng không cần tự tạo dependency bằng `new` bên trong logic nghiệp vụ.

Ví dụ: một `CheckoutService` cần thu tiền đơn hàng. DIP gợi ý service nên biết `PaymentGateway` (hợp đồng nghiệp vụ), không biết trực tiếp `BankSdkClient`. DI là thao tác truyền một implementation của `PaymentGateway` vào constructor `CheckoutService` khi dựng ứng dụng.

| Khía cạnh | DIP: Dependency Inversion Principle | DI: Dependency Injection |
|---|---|---|
| Bản chất | Nguyên lý **thiết kế kiến trúc và hướng phụ thuộc mã nguồn** | Kỹ thuật **khởi tạo, lắp ghép đối tượng** |
| Câu hỏi chính | “Ai được phép phụ thuộc vào ai?” | “Dependency đến từ đâu?” |
| Mục tiêu trực tiếp | Nghiệp vụ độc lập hơn trước chi tiết hạ tầng, dễ thay thế và bảo trì | Bỏ việc tự khởi tạo dependency khỏi class cần sử dụng |
| Công cụ thường dùng | Interface/abstract class, phân tách module, ports/adapters | Constructor injection, setter injection, factory, DI container |
| Có cần Spring không? | Không | Không; `new CheckoutService(gateway)` cũng là DI |
| Tự nó bảo đảm điều gì? | Định hướng kiến trúc; phải kiểm tra cả package/module dependencies | Một dependency được đưa từ ngoài vào; **không tự bảo đảm DIP** |

**DIP không đồng nghĩa DI**. DI là một cách thuận tiện để triển khai thiết kế theo DIP, nhưng ứng dụng có DI vẫn có thể phụ thuộc trực tiếp vào implementation cụ thể.

## 2. Vấn đề gốc: nghiệp vụ biết quá nhiều về hạ tầng

Mã minh họa sau gắn cứng lựa chọn cổng thanh toán vào bên trong use case:

~~~java
// Minh họa thiết kế bị phụ thuộc vào lớp cụ thể
final class TightlyCoupledCheckoutService {
    private final DemoBankAdapter bank = new DemoBankAdapter();

    String checkout(String orderId, long amountVnd) {
        // Trong ví dụ rút gọn, bỏ qua bước kiểm tra đầu vào.
        return bank.charge(orderId, amountVnd);
    }
}
~~~

Giả sử `DemoBankAdapter` là adapter gọi SDK ngân hàng thật. Khi thay đổi nhà cung cấp, muốn chạy kiểm thử không gọi API thật, hoặc cần dùng một adapter khác theo môi trường, `TightlyCoupledCheckoutService` dễ bị kéo theo thay đổi. Mã nghiệp vụ đang chịu ảnh hưởng bởi chi tiết “dùng adapter nào”.

Sửa chỗ `new` bằng constructor **nhận chính `DemoBankAdapter`** chỉ mới đạt DI:

~~~java
final class CheckoutWithDiButWithoutDip {
    private final DemoBankAdapter bank;

    CheckoutWithDiButWithoutDip(DemoBankAdapter bank) {
        this.bank = bank; // Được truyền từ bên ngoài: có DI.
    }

    String checkout(String orderId, long amountVnd) {
        return bank.charge(orderId, amountVnd);
    }
}
~~~

Tuy đã dùng constructor injection, kiểu khai báo vẫn là `DemoBankAdapter`. Module nghiệp vụ còn phụ thuộc vào class cụ thể của hạ tầng, nên chưa đạt mục tiêu của DIP.

## 3. Thiết kế đúng: phụ thuộc vào hợp đồng do nghiệp vụ cần

Đặt abstraction theo nhu cầu của use case: “thu số tiền VND cho một mã đơn hàng, nhận mã giao dịch”. Adapter cụ thể sẽ triển khai hợp đồng đó.

~~~mermaid
flowchart TB
    subgraph Business["Nghiệp vụ / application"]
        S["CheckoutService (high-level policy)"]
        P["PaymentGateway (port/interface)"]
        S -->|"tham chiếu kiểu"| P
    end

    subgraph Infrastructure["Hạ tầng"]
        A["DemoBankAdapter (low-level detail)"]
    end

    A -->|"implements"| P

    subgraph Bootstrap["Lắp ghép khi khởi động"]
        C["Main / Spring configuration"]
    end

    C -.->|"tạo và truyền dependency"| S
    C -.->|"tạo instance"| A
~~~

**Mũi tên liền** thể hiện phụ thuộc ở mã nguồn/kiểu: `CheckoutService → PaymentGateway ← DemoBankAdapter`. **Mũi tên nét đứt** thể hiện nơi lắp ghép đối tượng, nơi được phép biết cả interface và implementation. Lúc chạy, lệnh gọi vẫn đi từ `CheckoutService` đến implementation ngân hàng thông qua interface: đảo ngược phụ thuộc mã nguồn **không có nghĩa** đảo chiều luồng gọi runtime.

### 3.1. Ví dụ Java 17 chạy độc lập (không dùng Spring)

Tạo tệp `DipDiDemo.java`:

~~~java
import java.util.Objects;

/**
 * Port do use case định nghĩa.
 *
 * Hợp đồng:
 * - orderId khác null và không rỗng;
 * - amountVnd > 0;
 * - trả về mã giao dịch khác null, không rỗng nếu thu thành công;
 * - lỗi thanh toán được báo bằng exception phù hợp chính sách ứng dụng.
 */
interface PaymentGateway {
    String charge(String orderId, long amountVnd);
}

/** Kết quả của use case. */
record Receipt(String orderId, long amountVnd, String transactionId) {}

/**
 * Chính sách nghiệp vụ: chỉ biết port; không phụ thuộc SDK ngân hàng.
 */
final class CheckoutService {
    private final PaymentGateway paymentGateway;

    // Constructor injection: dependency là bắt buộc.
    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = Objects.requireNonNull(
                paymentGateway, "paymentGateway");
    }

    Receipt checkout(String orderId, long amountVnd) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }

        String transactionId = paymentGateway.charge(orderId, amountVnd);
        if (transactionId == null || transactionId.isBlank()) {
            throw new IllegalStateException("Gateway returned invalid transaction ID");
        }

        return new Receipt(orderId, amountVnd, transactionId);
    }
}

/**
 * Adapter DEMO để mô phỏng ngân hàng; không chuyển tiền thật.
 * Khi tích hợp thực, lớp hạ tầng này sẽ bọc SDK/API của nhà cung cấp.
 */
final class DemoBankAdapter implements PaymentGateway {
    @Override
    public String charge(String orderId, long amountVnd) {
        System.out.printf(
                "[DEMO] Thu %d VND cho đơn %s%n", amountVnd, orderId);
        return "TX-DEMO-" + orderId;
    }
}

public class DipDiDemo {
    public static void main(String[] args) {
        // Composition root: chỉ tại đây chọn implementation cụ thể.
        PaymentGateway gateway = new DemoBankAdapter();

        // DI thủ công, không cần Spring.
        CheckoutService checkout = new CheckoutService(gateway);

        Receipt receipt = checkout.checkout("ORD-001", 150_000L);
        System.out.println(receipt);
    }
}
~~~

Chạy:

~~~bash
javac DipDiDemo.java
java DipDiDemo
~~~

Đầu ra minh họa:

~~~text
[DEMO] Thu 150000 VND cho đơn ORD-001
Receipt[orderId=ORD-001, amountVnd=150000, transactionId=TX-DEMO-ORD-001]
~~~

Trong ví dụ này, constructor nhận `PaymentGateway` là **DI**. Việc `CheckoutService` chỉ import/tham chiếu `PaymentGateway` và `DemoBankAdapter implements PaymentGateway` là phần thiết kế theo **DIP**. `DipDiDemo.main` là **composition root**: nơi quyết định dùng adapter nào và cấp đối tượng đó vào use case.

Mã ví dụ dùng `long` cho đơn vị VND nguyên để giữ trọng tâm ở dependency; khi xử lý nhiều loại tiền tệ, có phần lẻ, tỷ giá hoặc quy tắc làm tròn, nên thiết kế một money value object phù hợp (`BigDecimal`/minor units + currency), không dùng `double` cho số tiền.

### 3.2. Thay thế implementation không sửa use case

Ví dụ trong môi trường phát triển cần adapter mô phỏng để không tạo giao dịch thật:

~~~java
final class LocalFakePaymentGateway implements PaymentGateway {
    @Override
    public String charge(String orderId, long amountVnd) {
        return "LOCAL-" + orderId;
    }
}

// Ở composition root:
PaymentGateway gateway = new LocalFakePaymentGateway();
CheckoutService checkout = new CheckoutService(gateway);
~~~

Lúc này `CheckoutService` không có `if (gateway instanceof ...)` và không cần biết adapter hiện tại là ngân hàng, sandbox hay fake. Mọi implementation phải đáp ứng hợp đồng của `PaymentGateway` (ví dụ không trả mã giao dịch rỗng khi thành công). DIP tạo ra điểm thay thế, còn tính thay thế an toàn yêu cầu hợp đồng interface rõ ràng.

**Ranh giới quan trọng:** Nếu interface `PaymentGateway` trả về `BankSdkPaymentResponse` hoặc bắt buộc người gọi truyền `BankSdkRequest`, thì abstraction đã rò rỉ chi tiết ngân hàng. Dù service chỉ viết tên interface, module nghiệp vụ vẫn phải biết kiểu thuộc SDK. Nên dùng kiểu thuộc nghiệp vụ (`Receipt`, `PaymentId`, `PaymentRequest`...) và chuyển đổi trong adapter.

## 4. DI bằng Spring: framework lắp ghép, DIP vẫn nằm ở thiết kế

Với Spring, ta có thể cấu hình dependency bằng bean. Ví dụ này dùng **các class Java ở phần 3.1** trong cùng package, với dependency `spring-context`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CheckoutConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new DemoBankAdapter();
    }

    @Bean
    CheckoutService checkoutService(PaymentGateway gateway) {
        // Spring cấp đúng bean PaymentGateway qua method parameter.
        return new CheckoutService(gateway);
    }
}
~~~

Spring tạo `DemoBankAdapter`, đưa bean đó vào `CheckoutService` và quản lý vòng đời bean. Không có `@Autowired` cũng được vì đang dùng tham số của `@Bean` method; nếu một `@Service` có **một constructor**, Spring cũng tự chọn constructor đó để injection theo cách thông dụng.

Khi tích hợp ngân hàng thật, có thể thay duy nhất bean `PaymentGateway` bằng một adapter khác (và cấu hình các dependency của adapter), miễn là chỉ có một bean phù hợp hoặc có `@Qualifier`/`@Primary` khi cần chọn nhiều implementation. Nếu khai báo đồng thời nhiều bean cùng kiểu mà không có quy tắc phân giải, Spring có thể báo lỗi ambiguity khi khởi tạo.

**Tránh nhầm:** `@Autowired`, `@Inject`, `@Component`, `@Bean` không tự biến một thiết kế phụ thuộc vào SDK thành DIP. Ví dụ dưới đây là DI nhưng vẫn coupling chặt:

~~~java
// Đây là DI, nhưng service vẫn phụ thuộc class hạ tầng cụ thể:
final class CoupledCheckout {
    private final DemoBankAdapter bank;

    CoupledCheckout(DemoBankAdapter bank) {
        this.bank = bank;
    }
}
~~~

Trong dự án nhiều module, đặt interface `PaymentGateway` ở module ứng dụng/nghiệp vụ phù hợp. Module hạ tầng phụ thuộc ngược về module chứa interface, còn module nghiệp vụ không import module hạ tầng. Nơi bootstrap hoặc cấu hình Spring được phép tham chiếu cả hai để kết nối. Đây mới là điều cần kiểm tra trên **sơ đồ module và dependencies của build**, bên cạnh chữ ký constructor.

## 5. Kiểm thử dễ hơn nhờ abstraction và DI

Không cần khởi động Spring, kết nối mạng, mở database hay gọi cổng thanh toán để kiểm thử logic `CheckoutService`. Tạo một fake ghi nhận số lần gọi; chạy test bằng JUnit Jupiter (JUnit 5).

Tệp `CheckoutServiceTest.java` (cùng package với demo):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void validOrderUsesInjectedGateway() {
        AtomicInteger calls = new AtomicInteger();

        PaymentGateway fake = (orderId, amountVnd) -> {
            assertEquals("ORD-123", orderId);
            assertEquals(150_000L, amountVnd);
            calls.incrementAndGet();
            return "FAKE-TX-123";
        };

        CheckoutService service = new CheckoutService(fake);
        Receipt receipt = service.checkout("ORD-123", 150_000L);

        assertEquals("FAKE-TX-123", receipt.transactionId());
        assertEquals(150_000L, receipt.amountVnd());
        assertEquals(1, calls.get());
    }

    @Test
    void invalidOrderIsRejectedBeforeExternalCall() {
        AtomicInteger calls = new AtomicInteger();
        PaymentGateway fake = (id, amountVnd) -> {
            calls.incrementAndGet();
            return "unexpected";
        };
        CheckoutService service = new CheckoutService(fake);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("ORD-123", 0));
        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(" ", 100));

        assertEquals(0, calls.get());
    }

    @Test
    void malformedGatewayReplyIsDetected() {
        CheckoutService service =
                new CheckoutService((id, amountVnd) -> "");

        assertThrows(IllegalStateException.class,
                () -> service.checkout("ORD-123", 100));
    }
}
~~~

Ba test này kiểm tra chính sách đầu vào, cách tương tác với abstraction và bảo vệ trước adapter sai hợp đồng. Test không chứng minh một adapter HTTP/SDK hoạt động thật; adapter thật vẫn cần integration test với sandbox hoặc môi trường kiểm thử có kiểm soát.

Một lợi ích quan trọng của **constructor injection** là dependency bắt buộc được thể hiện ngay khi khởi tạo; field `final` giúp tránh bị đổi tham chiếu sau đó. Test có thể lắp adapter giả rất rõ ràng.

## 6. Các cách DI và lựa chọn hợp lý

| Cách cấp dependency | Ví dụ ngắn | Khi phù hợp | Điểm cần chú ý |
|---|---|---|---|
| **Constructor injection** | `new CheckoutService(gateway)` | Dependency bắt buộc, thiết kế ưu tiên mặc định | Nếu constructor quá nhiều tham số, xem lại trách nhiệm class |
| **Setter injection** | `service.setGateway(gateway)` | Dependency tùy chọn hoặc cần thay cấu hình sau khởi tạo | Có thể tồn tại giai đoạn chưa khởi tạo đầy đủ; cần kiểm soát trạng thái |
| **Field injection** | `@Autowired private PaymentGateway gateway;` | Mã Spring cũ hoặc tình huống đặc biệt | Khó thấy dependency bắt buộc khi đọc constructor, khó tạo object thuần Java |
| **DI container** | `@Bean`, `@Service`, `@Autowired` | Ứng dụng cần cấu hình và quản lý vòng đời bean | Đây là hạ tầng lắp ghép; không thay thế tư duy thiết kế abstraction |

Ngoài constructor/setter/field, **method parameter injection** cũng phù hợp khi một dependency hay chiến lược chỉ áp dụng cho một lời gọi thay vì toàn bộ vòng đời object. Không nhất thiết biến mọi dữ liệu đầu vào của phương thức thành field trong constructor.

**Service locator** như `GlobalContainer.get(PaymentGateway.class)` gọi từ trong logic nghiệp vụ không có ưu điểm tương đương với constructor injection: nó làm dependency khó nhìn thấy và khiến việc test phụ thuộc vào trạng thái container toàn cục. Nếu cần container, nên truy cập tại ranh giới khởi tạo, rồi truyền dependency tường minh vào lớp nghiệp vụ.

## 7. DIP, DI và IoC khác nhau thế nào?

**Inversion of Control (IoC)** là khái niệm rộng: quyền điều phối một phần quá trình thực thi/khởi tạo do một thành phần bên ngoài nắm giữ, chẳng hạn Spring gọi code ứng dụng hoặc container quản lý cấu hình và vòng đời đối tượng.

**DI** là một cơ chế thực hiện IoC trong việc cung cấp dependency. **DIP** là nguyên lý về cấu trúc phụ thuộc của module. Chúng liên quan nhưng nằm ở các tầng khái niệm khác nhau:

~~~mermaid
flowchart LR
    D["DIP: thiết kế hướng phụ thuộc"] -->|"tạo ra nhu cầu về port"| P["Abstraction / interface"]
    I["DI: lắp ghép đối tượng"] -->|"truyền implementation vào"| S["Service"]
    C["IoC container (tùy chọn)"] -->|"có thể thực hiện"| I
    P -->|"là kiểu dependency của"| S
~~~

Một ứng dụng thuần Java có thể áp dụng DIP + DI thủ công mà không dùng IoC container. Ngược lại, hệ thống dùng Spring DI rất rộng rãi vẫn vi phạm DIP nếu lớp nghiệp vụ phụ thuộc trực tiếp vào các adapter, class framework hoặc DTO SDK.

## 8. Những hiểu lầm và điểm kiểm tra khi review

- **“Có interface là có DIP”:** Chưa đủ. Nếu interface nằm trong module hạ tầng khiến nghiệp vụ phải phụ thuộc hạ tầng, hướng phụ thuộc build vẫn sai. Quan trọng là abstraction thuộc về nhu cầu của tầng ổn định hơn và các module phụ thuộc vào nó đúng hướng.
- **“Đưa `new` ra constructor là DIP”:** Chỉ chắc chắn là DI. Hãy kiểm tra kiểu tham số constructor là abstraction do nghiệp vụ sở hữu hay implementation hạ tầng.
- **“DIP bắt buộc mỗi class có một interface”:** Không. Các value object, domain entity, thuật toán ổn định hoặc class nội bộ không có nhiều cách thay thế có thể không cần abstraction mới. Đặt port tại ranh giới thực sự biến động hoặc cần kiểm thử/tách module.
- **“DIP có nghĩa không được gọi code hạ tầng”:** Khi chạy, service vẫn gọi adapter hạ tầng để thực hiện công việc. Điều được đảo là **hướng phụ thuộc ở mức kiểu/module**, không phải thứ tự lời gọi.
- **“Có Spring thì không phải quản lý dependency”:** Container giúp lắp ghép nhưng phải quản lý số lượng bean, vòng đời, vòng phụ thuộc và tính an toàn luồng nếu singleton giữ trạng thái thay đổi.
- **“Để code nghiệp vụ import response/request của SDK là vô hại”:** Đây là một dạng rò rỉ chi tiết. Nên chuyển đổi ở adapter và định nghĩa kiểu dữ liệu hợp đồng theo use case.
- **“Cứ inject càng nhiều càng tốt”:** Constructor với hàng chục service khác nhau có thể báo hiệu class quá nhiều trách nhiệm. DI giúp nhìn rõ sự phức tạp; nó không làm sự phức tạp đó biến mất.

### Quy trình refactor một trường hợp thực tế

1. Xác định **chính sách/use case** cần được giữ ổn định: ví dụ xác thực đơn hàng và yêu cầu thu tiền.
2. Liệt kê chính xác **hợp đồng** nghiệp vụ muốn dùng: tham số, kết quả, exception, quy tắc idempotency, retry, timeout nếu thuộc yêu cầu hệ thống.
3. Định nghĩa **port** ở module đúng tầng, tránh kiểu dữ liệu và chú giải đặc thù nhà cung cấp trong API.
4. Viết **adapter** triển khai port; xử lý chuyển đổi DTO, mapping lỗi và giao tiếp network ở hạ tầng.
5. Dùng **constructor injection**, nối các đối tượng trong `main` hoặc cấu hình Spring.
6. Viết **unit test** use case bằng fake/mock port và **integration test** riêng cho adapter; kiểm tra đồ thị module để ngăn nghiệp vụ import hạ tầng.

Một ví dụ thực tế về hợp đồng quan trọng: nếu cổng thanh toán có thể retry sau timeout, chỉ tạo interface `charge` và thay implementation chưa đủ. Cần làm rõ khóa idempotency, trạng thái giao dịch không chắc chắn và chính sách lặp lời gọi. DIP giúp cô lập API nhà cung cấp; hợp đồng đúng mới giúp thay thế nhà cung cấp an toàn trong vận hành.

## 9. Bài tập thực hành

Cho thiết kế sau:

~~~java
class ReportService {
    private final SqlReportRepository repository = new SqlReportRepository();

    String loadReport(String id) {
        return repository.load(id);
    }
}
~~~

Hãy refactor để `ReportService` sử dụng `ReportRepository` do nghiệp vụ định nghĩa, còn `SqlReportRepository implements ReportRepository` nằm tại tầng lưu trữ. Tạo phiên bản `InMemoryReportRepository` để chạy unit test không cần database. Cuối cùng, so sánh hai biến thể:

- Truyền `SqlReportRepository` qua constructor: đã có DI, nhưng lớp nghiệp vụ vẫn phụ thuộc concrete.
- Truyền `ReportRepository` qua constructor: có DI **và** thiết kế đi theo DIP, nếu dependency giữa các module cũng đúng hướng.

**Tự kiểm tra kết quả:** Khi đổi từ SQL sang lưu trữ in-memory, có phải sửa hoặc import thêm loại repository trong `ReportService` không? Nếu có, hãy xem lại vị trí interface, chữ ký constructor và việc đặt logic khởi tạo.

---

**Điều cần nhớ:** **DIP quyết định “phụ thuộc vào abstraction nào và theo hướng nào”; DI quyết định “ai cung cấp implementation cụ thể”.** Có thể dùng DI mà chưa đạt DIP. Kết hợp abstraction đúng tầng, constructor injection và composition root rõ ràng giúp Java/Spring dễ thay đổi hạ tầng, kiểm thử nghiệp vụ và kiểm soát kiến trúc hơn.