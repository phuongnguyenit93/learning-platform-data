# Adapter Pattern trong Java: tích hợp các giao diện khác nhau

**Nhóm:** OOP → Mẫu thiết kế  
**Chủ đề:** Adapter và tích hợp giao diện khác nhau

## 1. Bài toán: hai hệ thống làm cùng việc nhưng không nói cùng “ngôn ngữ”

Ứng dụng của bạn đã chuẩn hóa việc thanh toán qua interface `PaymentGateway` với đối tượng yêu cầu và kết quả rõ ràng. Sau đó doanh nghiệp phải tích hợp một SDK thanh toán cũ:

- Ứng dụng gửi số tiền bằng `BigDecimal`, đơn vị USD; SDK cũ nhận `long`, đơn vị **cent**.
- Ứng dụng dùng `charge(PaymentRequest)`; SDK cũ dùng `execute(String merchantRef, long amountInCents)`.
- Ứng dụng cần kết quả `APPROVED` hoặc `DECLINED`; SDK cũ trả mã chuỗi `"00"`, `"05"`, `"91"`.
- Đổi toàn bộ mã `CheckoutService` để phụ thuộc SDK cũ sẽ làm chức năng nghiệp vụ bị ràng buộc vào nhà cung cấp.

**Adapter** tạo một lớp đứng giữa để biến giao diện mà SDK hiện có (*Adaptee*) thành giao diện mà ứng dụng mong đợi (*Target*). Bên sử dụng (*Client*) tiếp tục làm việc với `Target`. Lớp `Adapter` chịu trách nhiệm chuyển đổi lời gọi, tham số, phản hồi và lỗi trong phạm vi hợp đồng đã xác định.

### Thành phần của mẫu Adapter

| Vai trò | Trong ví dụ | Trách nhiệm |
|---|---|---|
| **Client** | `CheckoutService` | Gọi nghiệp vụ thanh toán thông qua interface thống nhất |
| **Target** | `PaymentGateway` | Hợp đồng mà client hiểu: `charge(PaymentRequest)` |
| **Adaptee** | `LegacyPaymentApi` / `LegacyPaymentSdk` | API cũ có chữ ký và quy ước dữ liệu riêng |
| **Adapter** | `LegacyPaymentAdapter` | Triển khai `PaymentGateway` và ủy quyền tới API cũ sau khi chuyển đổi |

~~~mermaid
classDiagram
    direction LR
    class PaymentGateway {
        <<interface>>
        +charge(PaymentRequest) PaymentReceipt
    }
    class LegacyPaymentApi {
        <<interface>>
        +execute(String, long) LegacyReply
    }
    class CheckoutService {
        -PaymentGateway gateway
        +checkout(PaymentRequest) String
    }
    class LegacyPaymentAdapter {
        -LegacyPaymentApi legacy
        +charge(PaymentRequest) PaymentReceipt
    }
    class LegacyPaymentSdk {
        +execute(String, long) LegacyReply
    }
    CheckoutService --> PaymentGateway : uses
    LegacyPaymentAdapter ..|> PaymentGateway : implements
    LegacyPaymentAdapter --> LegacyPaymentApi : delegates
    LegacyPaymentSdk ..|> LegacyPaymentApi : implements
~~~

> Đây là **Object Adapter**: giữ tham chiếu tới đối tượng được bọc bằng *composition*. Một lớp adapter không nhất thiết phải thừa kế lớp của SDK.

## 2. Xác định hợp đồng trước khi viết adapter

Cần thống nhất ý nghĩa dữ liệu trước khi chuyển đổi. Trong ví dụ học tập này:

1. `PaymentRequest` chỉ đại diện giao dịch bằng **USD**, số tiền dương và biểu diễn chính xác được bằng cent trong phạm vi `long`; mã đơn hàng khác rỗng. Dữ liệu không đáp ứng điều kiện bị từ chối ngay khi tạo request.
2. `PaymentGateway.charge` nhận request hợp lệ. Với phản hồi rõ ràng từ nhà cung cấp, nó trả `PaymentReceipt` có trạng thái `APPROVED` hoặc `DECLINED`.
3. Mã `"00"` của SDK nghĩa là duyệt, `"05"` là từ chối, `"91"` là tạm thời không xác định được kết quả. **Các mã này chỉ là quy ước giả lập của ví dụ**, không đại diện cho mọi SDK thực tế.
4. Phản hồi bị thiếu, mã không biết, hoặc lỗi hạ tầng phải được đưa ra dưới dạng lỗi rõ ràng. Không biến lỗi không xác định thành `DECLINED` hoặc `APPROVED`.
5. Client không truy cập kiểu `LegacyReply`, mã lỗi nội bộ hay phương thức đặc thù của SDK.

Ở hệ thống thật, đọc tài liệu chính thức của nhà cung cấp để xác nhận đơn vị tiền, trạng thái cuối cùng, quy tắc làm tròn, thời hạn timeout và yêu cầu idempotency. **Adapter không thể tự tạo ra bảo đảm mà dịch vụ ngoài không cung cấp**.

## 3. Java 17+: ví dụ đầy đủ, chạy độc lập

Lưu toàn bộ code thành file **`AdapterDemo.java`**. SDK bên dưới chỉ là một **stub mô phỏng** để học thiết kế; nó không gửi tiền hoặc kết nối dịch vụ thực.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

// ====== API mà nghiệp vụ của ứng dụng mong đợi (Target) ======

enum PaymentStatus {
    APPROVED,
    DECLINED
}

record PaymentRequest(String orderId, BigDecimal amountUsd) {
    PaymentRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountUsd == null) {
            throw new IllegalArgumentException("amountUsd is required");
        }

        // Không chấp nhận đơn vị nhỏ hơn 1 cent hoặc giá trị
        // không biểu diễn vừa trong long.
        try {
            long cents = amountUsd.movePointRight(2).longValueExact();
            if (cents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount must be an exact cent value within long range", ex);
        }
    }
}

record PaymentReceipt(PaymentStatus status, String reference) {
    PaymentReceipt {
        Objects.requireNonNull(status, "status");
        if (status == PaymentStatus.APPROVED &&
                (reference == null || reference.isBlank())) {
            throw new IllegalArgumentException(
                    "approved payment needs provider reference");
        }
    }
}

interface PaymentGateway {
    /**
     * Nhận PaymentRequest hợp lệ, trả APPROVED hoặc DECLINED
     * khi phản hồi đã xác định.
     *
     * @throws GatewayUnavailableException nếu chưa xác định
     *         được kết quả từ nhà cung cấp
     * @throws ProviderProtocolException nếu phản hồi phá hợp đồng
     */
    PaymentReceipt charge(PaymentRequest request);
}

final class GatewayUnavailableException extends RuntimeException {
    GatewayUnavailableException(String message) {
        super(message);
    }
}

final class ProviderProtocolException extends RuntimeException {
    ProviderProtocolException(String message) {
        super(message);
    }
}

// ====== API của SDK cũ (Adaptee) ======

record LegacyReply(String code, String transactionId) {}

interface LegacyPaymentApi {
    // Nhận cents (long), trả mã giao thức riêng.
    LegacyReply execute(String merchantRef, long amountInCents);
}

// Stub mô phỏng SDK thực tế. "00" là thành công theo quy ước demo.
final class LegacyPaymentSdk implements LegacyPaymentApi {
    @Override
    public LegacyReply execute(String merchantRef, long amountInCents) {
        return new LegacyReply("00", "LEGACY-" + merchantRef);
    }
}

// ====== Adapter: bọc SDK cũ, cung cấp API mới ======

final class LegacyPaymentAdapter implements PaymentGateway {
    private final LegacyPaymentApi legacy;

    LegacyPaymentAdapter(LegacyPaymentApi legacy) {
        this.legacy = Objects.requireNonNull(legacy, "legacy");
    }

    @Override
    public PaymentReceipt charge(PaymentRequest request) {
        Objects.requireNonNull(request, "request");

        // Request đã kiểm tra cent chính xác ngay khi khởi tạo.
        long cents = request.amountUsd()
                            .movePointRight(2)
                            .longValueExact();

        LegacyReply reply = legacy.execute(request.orderId(), cents);

        if (reply == null || reply.code() == null) {
            throw new ProviderProtocolException(
                    "legacy provider returned an invalid reply");
        }

        return switch (reply.code()) {
            case "00" -> {
                if (reply.transactionId() == null ||
                        reply.transactionId().isBlank()) {
                    throw new ProviderProtocolException(
                            "approved reply has no transaction id");
                }
                yield new PaymentReceipt(
                        PaymentStatus.APPROVED, reply.transactionId());
            }
            case "05" -> new PaymentReceipt(
                    PaymentStatus.DECLINED, reply.transactionId());
            case "91" -> throw new GatewayUnavailableException(
                    "provider result is not confirmed; reconcile first");
            default -> throw new ProviderProtocolException(
                    "unknown provider code: " + reply.code());
        };
    }
}

// ====== Client: không biết tên SDK, mã lỗi hoặc đơn vị cents ======

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    String checkout(PaymentRequest request) {
        PaymentReceipt receipt = gateway.charge(request);

        return switch (receipt.status()) {
            case APPROVED -> "Paid: " + receipt.reference();
            case DECLINED -> "Payment declined";
        };
    }
}

public class AdapterDemo {
    public static void main(String[] args) {
        LegacyPaymentApi oldSdk = new LegacyPaymentSdk();
        PaymentGateway gateway = new LegacyPaymentAdapter(oldSdk);
        CheckoutService checkout = new CheckoutService(gateway);

        PaymentRequest order = new PaymentRequest(
                "ORDER-1001", new BigDecimal("12.34"));

        System.out.println(checkout.checkout(order));
        // Paid: LEGACY-ORDER-1001
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac AdapterDemo.java
java AdapterDemo
~~~

**Dòng dữ liệu thực tế của ví dụ:**

~~~mermaid
sequenceDiagram
    participant C as CheckoutService
    participant A as LegacyPaymentAdapter
    participant L as LegacyPaymentApi
    C->>A: charge(ORDER-1001, USD 12.34)
    Note over A: BigDecimal 12.34 → long 1234 cents
    A->>L: execute("ORDER-1001", 1234)
    L-->>A: LegacyReply("00", "LEGACY-ORDER-1001")
    Note over A: "00" → APPROVED
    A-->>C: PaymentReceipt(APPROVED, reference)
~~~

`CheckoutService` chỉ phụ thuộc `PaymentGateway`. Nếu sau này chuyển sang SDK mới, lập trình viên chỉ cần cung cấp implementation khác cho `PaymentGateway` và thay cấu hình khởi tạo/dependency injection. Nghiệp vụ checkout không cần hiểu giao thức SDK cũ.

### Tại sao `BigDecimal` và `longValueExact()`?

Thanh toán yêu cầu số tiền chính xác. Với `new BigDecimal("12.34")`:

`12.34 USD × 100 = 1234 cents`

Đoạn `movePointRight(2).longValueExact()` không tự làm tròn: `12.345` sẽ bị từ chối vì không biểu diễn nguyên cent. Đây là lựa chọn **hợp đồng dữ liệu**; nếu sản phẩm thực sự cần làm tròn, phải quy định chính xác mức làm tròn và nơi thực hiện, không tùy ý gọi `doubleValue()` rồi ép `long`.

## 4. Adapter thật sự chuyển đổi những gì?

| Khác biệt | Ở phía ứng dụng | Ở phía SDK cũ | Chuyển đổi tại adapter |
|---|---|---|---|
| Chữ ký | `charge(PaymentRequest)` | `execute(String,long)` | Tách dữ liệu từ request rồi ủy quyền |
| Đơn vị tiền | `BigDecimal` USD | `long` cents | Nhân 100 với phép chuyển chính xác |
| Đầu ra | `PaymentReceipt` | `LegacyReply` | Tạo kiểu kết quả thuộc domain |
| Kết quả | `APPROVED` / `DECLINED` | `"00"` / `"05"` | Ánh xạ mã đã thống nhất |
| Chưa rõ kết quả | Lỗi miền tích hợp | `"91"` | Ném `GatewayUnavailableException` |
| Phản hồi sai giao thức | Lỗi miền tích hợp | `null` / mã lạ | Ném `ProviderProtocolException` |
| Phụ thuộc | `PaymentGateway` | `LegacyPaymentApi` | SDK chỉ xuất hiện ở composition root và adapter |

Chú ý **`DECLINED` là một kết quả nghiệp vụ đã xác định**; sự cố mạng, timeout hay trạng thái không rõ không phải là “khách hàng bị từ chối”. Phân biệt hai trường hợp giúp tránh gửi thông báo sai hoặc thực hiện lại thanh toán bừa bãi.

## 5. Kiểm thử ở đúng ranh giới tích hợp

Để kiểm thử adapter không cần mạng thật, ví dụ trên đưa `LegacyPaymentApi` thành interface có thể thay bằng lambda. File `LegacyPaymentAdapterTest.java` dưới đây dùng JUnit Jupiter 5 (cần dependency JUnit Jupiter và cấu hình JUnit test runner trong Maven hoặc Gradle). Đặt test cùng package với demo; với cấu trúc một file Java mặc định ở trên, cả hai nằm trong default package để trình bày ngắn gọn.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class LegacyPaymentAdapterTest {

    @Test
    void convertsAmountToCentsWithoutRounding() {
        AtomicLong receivedCents = new AtomicLong(-1L);

        LegacyPaymentApi fake = (ref, cents) -> {
            assertEquals("ORDER-42", ref);
            receivedCents.set(cents);
            return new LegacyReply("00", "TX-1");
        };

        PaymentGateway gateway = new LegacyPaymentAdapter(fake);
        PaymentReceipt result = gateway.charge(
                new PaymentRequest("ORDER-42", new BigDecimal("12.34")));

        assertEquals(1234L, receivedCents.get());
        assertEquals(PaymentStatus.APPROVED, result.status());
        assertEquals("TX-1", result.reference());
    }

    @Test
    void declinedIsAResultRatherThanProviderOutage() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("05", null));

        PaymentReceipt result = gateway.charge(
                new PaymentRequest("ORDER-43", new BigDecimal("2.00")));

        assertEquals(PaymentStatus.DECLINED, result.status());
    }

    @Test
    void ambiguousProviderResultMustNotBeTreatedAsDeclined() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("91", null));

        assertThrows(GatewayUnavailableException.class,
                () -> gateway.charge(new PaymentRequest(
                        "ORDER-44", new BigDecimal("2.00"))));
    }

    @Test
    void unknownCodeDoesNotBecomeSuccess() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("??", null));

        assertThrows(ProviderProtocolException.class,
                () -> gateway.charge(new PaymentRequest(
                        "ORDER-45", new BigDecimal("2.00"))));
    }

    @Test
    void rejectsFractionalCentAtRequestBoundary() {
        assertThrows(IllegalArgumentException.class,
                () -> new PaymentRequest(
                        "ORDER-46", new BigDecimal("12.345")));
    }

    @Test
    void approvedReplyMustHaveTransactionReference() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("00", ""));

        assertThrows(ProviderProtocolException.class,
                () -> gateway.charge(new PaymentRequest(
                        "ORDER-47", new BigDecimal("1.00"))));
    }
}
~~~

Những kiểm thử này xác minh **quy tắc chuyển đổi và ánh xạ**, không chứng minh SDK ngoài vận hành chính xác. Với tích hợp thật cần thêm contract test theo tài liệu API, sandbox integration test và kiểm thử tình huống hạ tầng: timeout trước/sau khi nhà cung cấp nhận yêu cầu, phản hồi trùng, webhook đến muộn, API thay đổi phiên bản.

### Cách tránh thanh toán trùng khi lỗi mạng

Nếu một lệnh `execute` timeout, ứng dụng có thể chưa biết tiền đã bị trừ hay chưa. Không nên tự động gọi lại chỉ vì adapter ném exception: việc retry có thể tạo giao dịch thứ hai.

Giải pháp cần được thống nhất từ thiết kế hệ thống: dùng **idempotency key** khi provider hỗ trợ, lưu trạng thái giao dịch và khóa xử lý trùng, truy vấn trạng thái/reconcile với provider trước khi retry, đồng thời xử lý webhook idempotently. Trong ví dụ, `orderId` chỉ là `merchantRef`; **không có bảo đảm tự động chống trùng**, vì stub không triển khai cơ chế idempotency.

## 6. Object Adapter và Class Adapter

Có hai hình thức Adapter thường được nhắc đến:

**Object Adapter (phổ biến trong Java):** Adapter *chứa* đối tượng Adaptee và gọi phương thức của nó. Đây là cách trong ví dụ:

~~~java
final class LegacyPaymentAdapter implements PaymentGateway {
    private final LegacyPaymentApi legacy;
    // ... chuyển đổi rồi gọi legacy.execute(...)
}
~~~

Ưu điểm: ít phụ thuộc hệ phân cấp lớp, có thể bọc nhiều implementation cùng interface, dễ thay fake để kiểm thử, vẫn dùng được khi SDK dùng `final class` (miễn có cơ chế bọc hoặc một lớp wrapper thích hợp).

**Class Adapter:** Adapter kế thừa lớp Adaptee đồng thời triển khai Target; Java có thể dùng `extends LegacyBaseSdk implements PaymentGateway` nếu lớp SDK cho phép kế thừa. Cách này khó áp dụng với `final`, gắn adapter chặt hơn vào chi tiết lớp cha và Java không hỗ trợ kế thừa nhiều lớp. Vì vậy **composition** thường là lựa chọn dễ bảo trì hơn.

Ví dụ hình thức Class Adapter (chỉ phác họa, không cần ghép vào demo chạy độc lập):

~~~java
class LegacyBaseSdk {
    String oldOperation(String value) { return "old:" + value; }
}
interface NewApi {
    String run(String value);
}
class InheritanceAdapter extends LegacyBaseSdk implements NewApi {
    @Override public String run(String value) {
        return oldOperation(value);
    }
}
~~~

Dù chọn cách nào, điểm xác định mẫu Adapter vẫn là **biến giao diện cũ thành giao diện mới được client mong đợi**, không phải chỉ đơn giản “có một lớp bọc”.

## 7. Adapter khác các mẫu thiết kế dễ nhầm thế nào?

| Mẫu | Mục đích chính | Tình huống nhận diện |
|---|---|---|
| **Adapter** | Làm hai giao diện không tương thích làm việc được với nhau | Domain dùng `PaymentGateway`, SDK có `execute(ref,cents)` |
| **Facade** | Cung cấp điểm truy cập đơn giản tới hệ thống con phức tạp | Một phương thức gom nhiều lời gọi thanh toán, kho, vận chuyển |
| **Decorator** | Bổ sung hành vi, vẫn giữ nguyên giao diện đang bọc | Thêm logging/metrics/retry policy quanh một `PaymentGateway` |
| **Proxy** | Đại diện và kiểm soát truy cập một đối tượng | Lazy initialization, phân quyền, remote access |
| **Bridge** | Tách abstraction khỏi phần hiện thực để hai phía thay đổi độc lập | Nhiều kiểu thông báo và nhiều kênh gửi kết hợp linh hoạt |

Các mẫu có thể phối hợp: ví dụ `MetricsPaymentGateway` dạng Decorator bao quanh `LegacyPaymentAdapter`; bên ngoài vẫn là `PaymentGateway`. Không cần gán mọi lớp wrapper vào Adapter nếu mục tiêu thực tế chỉ là đo thời gian hay kiểm soát quyền truy cập.

## 8. Khi tích hợp nhiều SDK hoặc API phiên bản khác nhau

Giả sử thêm nhà cung cấp thứ hai có JSON HTTP thay vì SDK Java:

~~~text
CheckoutService
      |
      v
  PaymentGateway (hợp đồng chung)
      |                     |
      v                     v
LegacyPaymentAdapter    HttpPaymentAdapter
      |                     |
      v                     v
 LegacyPaymentApi        HTTP/JSON API
~~~

Mỗi adapter đóng gói một bộ ánh xạ riêng, nhưng đều phải bảo toàn hợp đồng `PaymentGateway`. Việc chọn adapter có thể đặt ở lớp cấu hình hoặc dependency injection, chẳng hạn Spring:

~~~java
// Phác họa wiring với Spring; cần có các bean tương ứng.
// @Bean
// PaymentGateway paymentGateway(LegacyPaymentApi legacyPaymentApi) {
//     return new LegacyPaymentAdapter(legacyPaymentApi);
// }
//
// @Service
// class CheckoutService {
//     CheckoutService(PaymentGateway gateway) { ... }
// }
~~~

Nếu hệ thống bắt đầu có hai cách diễn giải `DECLINED` khác nhau, hoặc một nhà cung cấp chỉ hỗ trợ “tạo yêu cầu và chờ callback”, hãy kiểm tra lại **hợp đồng chung**. Không nên giả vờ một API bất đồng bộ luôn cung cấp kết quả xác định tức thời. Khi cần, tách capability, chuyển kết quả thành `PENDING` theo hợp đồng mới và cập nhật client có chủ đích, hoặc thiết kế port chuyên biệt cho luồng bất đồng bộ.

Adapter thường là một phần của **Anti-Corruption Layer** trong DDD: giữ thuật ngữ, model, trạng thái và lỗi thuộc hệ thống ngoài tại biên tích hợp, tránh để chúng lan vào domain. Tuy nhiên Anti-Corruption Layer có thể bao gồm nhiều component hơn một adapter, như mapping, validation, translator và client/repository.

## 9. Những lỗi thiết kế cần tránh

1. **Trả trực tiếp `LegacyReply` ra domain.** Khi đó client vẫn biết mã `"00"`, `"05"`; Adapter chưa hoàn thành trách nhiệm che sự không tương thích.
2. **Rải `if (provider == ...)` khắp nghiệp vụ.** Mỗi provider mới làm client phình to và dễ sai khác hành vi. Dùng một hợp đồng rõ ràng và các implementation thích hợp.
3. **Ép kiểu tiền qua `double` hoặc làm tròn ngầm.** Ví dụ `(long)(12.345 * 100)` âm thầm làm mất phần thập phân. Phải công bố quy tắc tiền tệ trước.
4. **Bắt mọi exception rồi trả `DECLINED`.** Lỗi hạ tầng và trạng thái chưa rõ có thể khiến hệ thống đối soát sai.
5. **Gọi lại khi timeout mà chưa kiểm tra idempotency.** Với lệnh có tác dụng phụ, retry không kiểm soát có thể lặp thanh toán.
6. **Tạo “adapter” chứa luôn nghiệp vụ đặt hàng, tính giá, lưu kho.** Chuyển đổi giao thức nên ở biên; quy tắc kinh doanh nên ở tầng phù hợp.
7. **Bỏ qua bảo mật dữ liệu.** Không log số thẻ, token thanh toán hoặc thông tin bí mật; triển khai TLS, xác thực và quản lý secret theo yêu cầu API thật.
8. **Coi sự tương thích chữ ký là đủ.** Nếu implementation thứ hai trả trạng thái, lỗi hoặc đảm bảo thời gian khác với interface, nó có thể phá những kỳ vọng hợp lệ của client.

## 10. Checklist áp dụng Adapter trong dự án

- [ ] Đã xác định **Target** là hợp đồng do ứng dụng kiểm soát, đủ rõ về đầu vào, đầu ra và lỗi.
- [ ] Đã xác định đúng **Adaptee** (SDK/API cần tích hợp) và đọc quy ước chính thức của nó.
- [ ] Có phép chuyển đổi đơn vị, kiểu dữ liệu và trạng thái rõ ràng, không mất thông tin quan trọng.
- [ ] Các lỗi ngoại vi được ánh xạ sang lỗi hoặc trạng thái có ý nghĩa trong domain; không báo thành công giả.
- [ ] Client phụ thuộc interface của ứng dụng; adapter giữ riêng chi tiết SDK.
- [ ] Có unit test cho ánh xạ và giá trị biên, integration test ở sandbox cho contract bên ngoài.
- [ ] Có chiến lược timeout, đối soát, retry và idempotency tương ứng với khả năng provider.
- [ ] Khi thay provider, phần lớn thay đổi nằm ở adapter và cấu hình kết nối, không xâm nhập core business.

### Bài tập tự luyện

Viết `HttpPaymentAdapter implements PaymentGateway` cho một API giả lập nhận JSON `{"order":"ORDER-1","amountMinor":1234}` và trả `{"state":"accepted","reference":"REMOTE-1"}`. Ánh xạ `accepted → APPROVED`, `rejected → DECLINED`, `pending →` một tình huống chưa xác định theo **hợp đồng đã chọn**. Dùng fake HTTP client để kiểm thử JSON mapping, lỗi parse, timeout và transaction reference bị thiếu. Quan sát rằng `CheckoutService` vẫn không phải thay đổi.

**Điểm cần nhớ:** Adapter không sửa “cách làm việc” của bên thứ ba; nó tạo một **ranh giới dịch thuật có hợp đồng**. Nghiệp vụ nói bằng thuật ngữ của ứng dụng, còn chi tiết nhà cung cấp nằm trong lớp tích hợp.