# Thiết kế để thay thế phụ thuộc khi kiểm thử (Java OOP)

## 1. Vì sao một lớp khó kiểm thử?

Giả sử CheckoutService xử lý thanh toán. Nếu bên trong lớp này tự tạo HTTP client, kết nối cổng thanh toán, gửi email và lấy thời gian hệ thống, mỗi lần chạy unit test có thể phải truy cập mạng, cần tài khoản thật hoặc phụ thuộc vào đồng hồ máy. Test vì vậy chậm, khó lặp lại và có thể tạo tác dụng phụ.

Giải pháp là thiết kế **điểm thay thế phụ thuộc (test seam)**: CheckoutService chỉ biết các **hợp đồng** mà nó cần, còn đối tượng cụ thể được truyền từ bên ngoài. Khi chạy thật, ứng dụng gắn adapter thực; khi kiểm thử, test gắn đối tượng giả có hành vi kiểm soát được.

Trong Java, cách thông dụng là **Dependency Injection (DI) qua constructor**, kết hợp **Dependency Inversion Principle (DIP)**. Interface giúp mô tả khả năng, còn constructor cho phép quyết định implementation lúc khởi tạo đối tượng. Không nhất thiết phải dùng Spring hay thư viện DI để áp dụng thiết kế này.

### Ranh giới cần tách

| Phụ thuộc | Khi chạy ứng dụng | Khi unit test | Lý do thay thế |
| --- | --- | --- | --- |
| Cổng thanh toán | Adapter gọi API bên ngoài | Stub trả thành công/thất bại/lỗi có chủ đích | Không gọi dịch vụ thật, kiểm soát kịch bản |
| Gửi thông báo | SMTP hoặc dịch vụ email | Spy ghi nhận các lần gửi | Kiểm chứng tương tác, tránh email thật |
| Đồng hồ | Clock.systemUTC() | Clock.fixed(...) | Thời điểm cố định, assert chính xác |
| Kho dữ liệu | JDBC/ORM | In-memory fake khi phù hợp | Cô lập business rule, chạy nhanh |

Cần phân biệt **hợp đồng của phụ thuộc** với **implementation cụ thể**. CheckoutService phải biết rằng PaymentGateway có thể charge, nhưng không cần biết nó dùng REST, gRPC hay một fake do test cung cấp.

~~~mermaid
flowchart LR
    T["JUnit test"] --> S["CheckoutService"]
    W["Ứng dụng chạy thật"] --> S
    S --> G["PaymentGateway"]
    S --> R["ReceiptSender"]
    S --> C["Clock"]
    G -. "khi chạy thật" .-> GA["Adapter API thanh toán"]
    G -. "trong test" .-> GS["StubGateway"]
    R -. "trong test" .-> RS["RecordingSender"]
    C -. "trong test" .-> FC["Clock.fixed"]
~~~

## 2. Thiết kế ví dụ: dịch vụ checkout

Hợp đồng nghiệp vụ được chọn cho bài:
1. Mã đơn hàng phải khác null và không chỉ chứa khoảng trắng; số tiền VND phải lớn hơn 0.
2. Dữ liệu không hợp lệ gây IllegalArgumentException **trước khi** gọi bất cứ phụ thuộc nào.
3. Cổng thanh toán trả true thì gửi một thông báo; trả false thì không gửi.
4. Kết quả chứa trạng thái được chấp nhận và thời điểm lấy từ Clock đã tiêm vào.
5. Nếu cổng thanh toán ném exception, lỗi được truyền ra và không gửi thông báo.

Đây là ví dụ dạy kỹ thuật kiểm thử; một hệ thống thanh toán thật phải giải quyết thêm tính idempotent, giao dịch, retry, và gửi thông báo đáng tin cậy để tránh tình huống thanh toán thành công nhưng gửi thông báo thất bại.

Ta xây dựng dự án **Java 17 + Maven + JUnit 5** với cấu trúc:

~~~text
replaceable-dependencies/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── PaymentGateway.java
    │   ├── ReceiptSender.java
    │   └── CheckoutService.java
    └── test/java/vn/example/
        └── CheckoutServiceTest.java
~~~

### 2.1. Maven: pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>replaceable-dependencies</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 2.2. Định nghĩa các hợp đồng (ports)

**src/main/java/vn/example/PaymentGateway.java**

~~~java
package vn.example;

/** Giao tiếp tối thiểu mà nghiệp vụ checkout cần. */
public interface PaymentGateway {
    /**
     * @return true nếu được chấp nhận; false nếu bị từ chối.
     * @throws RuntimeException khi dịch vụ phụ thuộc gặp sự cố.
     */
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/vn/example/ReceiptSender.java**

~~~java
package vn.example;

/** Gửi thông báo cho đơn hàng đã được chấp nhận. */
public interface ReceiptSender {
    void send(String orderId);
}
~~~

Đặt interface gần **nhu cầu của lớp sử dụng** thay vì để lớp nghiệp vụ import trực tiếp SDK của bên thứ ba. Chúng ta vẫn có thể viết adapter thật triển khai PaymentGateway/ReceiptSender ở lớp hạ tầng.

### 2.3. Tiêm phụ thuộc qua constructor

**src/main/java/vn/example/CheckoutService.java**

~~~java
package vn.example;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class CheckoutService {
    private final PaymentGateway gateway;
    private final ReceiptSender sender;
    private final Clock clock;

    public CheckoutService(
            PaymentGateway gateway,
            ReceiptSender sender,
            Clock clock) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.sender = Objects.requireNonNull(sender, "sender");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Result checkout(String orderId, long amountVnd) {
        // Xác thực trước khi tạo bất kỳ tác dụng phụ nào.
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }

        boolean accepted = gateway.charge(orderId, amountVnd);

        if (accepted) {
            sender.send(orderId);
        }

        return new Result(accepted, clock.instant());
    }

    public record Result(boolean accepted, Instant checkedAt) {}
}
~~~

Ba trường là final: dependency của một đối tượng được xác định khi khởi tạo. Objects.requireNonNull khiến lỗi lắp ghép xuất hiện sớm, không đợi đến lúc checkout thực sự được gọi. Clock là abstraction có sẵn trong Java; ta không cần tự thiết kế TimeProvider chỉ để thay thế Instant.now().

Điểm then chốt: CheckoutService **không gọi new đối với adapter**, không chọn môi trường trong mã nghiệp vụ và không tự tạo Clock.systemUTC(). Thành phần khởi tạo ứng dụng (**composition root**) sẽ cung cấp chúng. Chẳng hạn ở production, nơi dựng đối tượng truyền vào một PaymentGateway thật, ReceiptSender thật và Clock.systemUTC(); test có thể truyền các lớp giả ở dưới.

## 3. Viết unit test không cần mạng hay email thật

Ta dùng hai test double:
- **StubGateway**: cung cấp kết quả định trước (true/false/exception), đồng thời ghi nhận tham số và số lần gọi để kiểm tra.
- **RecordingSender**: spy tối giản lưu lại mã đơn hàng được yêu cầu gửi.
- **Clock.fixed(...)**: thay đồng hồ hệ thống bằng một thời điểm cố định.

**src/test/java/vn/example/CheckoutServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    private static final Instant FIXED_TIME =
            Instant.parse("2026-01-02T03:04:05Z");

    private final StubGateway gateway = new StubGateway();
    private final RecordingSender sender = new RecordingSender();
    private final Clock clock = Clock.fixed(FIXED_TIME, ZoneOffset.UTC);

    private CheckoutService service() {
        return new CheckoutService(gateway, sender, clock);
    }

    @Test
    void successChargesOnceAndSendsOneReceipt() {
        gateway.approved = true;

        CheckoutService.Result result =
                service().checkout("ORD-001", 150_000);

        assertTrue(result.accepted());
        assertEquals(FIXED_TIME, result.checkedAt());
        assertEquals(1, gateway.calls);
        assertEquals("ORD-001", gateway.lastOrderId);
        assertEquals(150_000, gateway.lastAmount);
        assertEquals(List.of("ORD-001"), sender.sentOrderIds);
    }

    @Test
    void declinedPaymentDoesNotSendReceipt() {
        gateway.approved = false;

        CheckoutService.Result result =
                service().checkout("ORD-002", 80_000);

        assertFalse(result.accepted());
        assertEquals(FIXED_TIME, result.checkedAt());
        assertEquals(1, gateway.calls);
        assertTrue(sender.sentOrderIds.isEmpty());
    }

    @Test
    void invalidInputNeverCallsDependencies() {
        CheckoutService checkout = service();

        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout(null, 100));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout("  ", 100));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout("ORD-003", 0));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout("ORD-003", -10));

        assertEquals(0, gateway.calls);
        assertTrue(sender.sentOrderIds.isEmpty());
    }

    @Test
    void gatewayFailurePropagatesWithoutSending() {
        IllegalStateException failure =
                new IllegalStateException("Gateway unavailable");
        gateway.failure = failure;

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                () -> service().checkout("ORD-004", 200_000));

        assertSame(failure, actual);
        assertEquals(1, gateway.calls);
        assertTrue(sender.sentOrderIds.isEmpty());
    }

    @Test
    void constructorRejectsMissingDependencies() {
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(null, sender, clock));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(gateway, null, clock));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(gateway, sender, null));
    }

    // Stub có khả năng ghi lại tương tác: dùng trong phạm vi test.
    private static final class StubGateway implements PaymentGateway {
        boolean approved = true;
        RuntimeException failure;
        int calls;
        String lastOrderId;
        long lastAmount;

        @Override
        public boolean charge(String orderId, long amountVnd) {
            calls++;
            lastOrderId = orderId;
            lastAmount = amountVnd;

            if (failure != null) {
                throw failure;
            }
            return approved;
        }
    }

    // Spy ghi nhận tác dụng phụ thay vì gửi email.
    private static final class RecordingSender implements ReceiptSender {
        final List<String> sentOrderIds = new ArrayList<>();

        @Override
        public void send(String orderId) {
            sentOrderIds.add(orderId);
        }
    }
}
~~~

### 3.1. Chạy thử

Cài JDK 17 và Maven, mở terminal tại thư mục có pom.xml, chạy:

~~~bash
mvn test
~~~

Bộ mã trên có **5 phương thức @Test**; nếu biên dịch và chạy đúng, Maven báo 5 tests, 0 failures, 0 errors. Tất cả trường hợp thực hiện trong bộ nhớ, không có HTTP request hay email thật.

JUnit Jupiter mặc định tạo instance mới của lớp test cho từng phương thức @Test. Vì vậy StubGateway và RecordingSender được khởi tạo sạch giữa các ca; không phụ thuộc vào thứ tự thực thi.

### 3.2. Những gì test thực sự chứng minh

| Kiểm thử | Hành vi cần bảo vệ | Lỗi ví dụ mà test phát hiện |
| --- | --- | --- |
| successChargesOnceAndSendsOneReceipt | Lệnh charge đúng dữ liệu; chỉ gửi khi được chấp nhận; ghi đúng thời điểm | Gọi thanh toán hai lần; truyền sai số tiền; quên gửi |
| declinedPaymentDoesNotSendReceipt | Không gửi thông báo khi cổng từ chối | Gửi email bất kể kết quả |
| invalidInputNeverCallsDependencies | Xác thực đầu vào trước khi có tác dụng phụ | Gọi API với đơn hàng rỗng hoặc tiền âm |
| gatewayFailurePropagatesWithoutSending | Không tiếp tục gửi khi charge lỗi | Nuốt exception rồi gửi thông báo thành công |
| constructorRejectsMissingDependencies | Các cộng tác viên bắt buộc tồn tại | Lắp ghép đối tượng thiếu dependency |

Không nên viết test bằng cách truy cập trường private của CheckoutService qua reflection. Các assertion hiện tại quan sát kết quả public và tương tác được ghi bởi test double, nên không buộc code phải sử dụng một thuật toán nội bộ cụ thể.

## 4. Nhận diện các loại test double

| Loại | Công dụng | Ví dụ |
| --- | --- | --- |
| Dummy | Được truyền vào để thỏa chữ ký nhưng không được sử dụng trong test đó | Một sender rỗng khi kiểm tra validation |
| Stub | Cung cấp dữ liệu hoặc kết quả cố định/có cấu hình | StubGateway.approved = false |
| Fake | Implementation đơn giản nhưng hoạt động được, thường lưu dữ liệu trong bộ nhớ | InMemoryUserRepository |
| Spy | Ghi lại lời gọi để kiểm chứng sau khi chạy | RecordingSender.sentOrderIds |
| Mock | Đối tượng với kỳ vọng tương tác được định nghĩa và xác minh, thường do thư viện tạo | Mockito mock(PaymentGateway.class) và verify(...) |

Một test double có thể mang nhiều đặc tính. StubGateway vừa cung cấp kết quả định trước vừa ghi nhận số lần gọi. Đừng cố ép mọi đối tượng giả vào một nhãn cố định; hãy chọn công cụ giúp test thể hiện rõ hợp đồng cần kiểm chứng.

**Mock không đồng nghĩa với unit test.** Ví dụ trên dùng fake/spy viết tay, đủ để kiểm chứng các tương tác đơn giản mà không cần thêm Mockito. Với nhiều phương thức hay tương tác phức tạp, thư viện mocking có thể giảm mã lặp; nhưng lạm dụng verify cho từng lời gọi nội bộ sẽ khiến test dễ hỏng khi refactor hợp lệ.

## 5. Các điểm thay thế phụ thuộc trong thiết kế OOP

### Constructor injection (ưu tiên với dependency bắt buộc)

~~~java
// Ví dụ mẫu về cú pháp; các interface tương ứng phải được khai báo.
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }
}
~~~

Lợi ích: rõ dependency bắt buộc; khó tạo đối tượng ở trạng thái chưa hợp lệ; dễ truyền implementation thật/fake; phù hợp với immutable collaborator. Constructor injection là lựa chọn tốt khi các phụ thuộc tồn tại suốt vòng đời đối tượng.

### Method injection (hữu ích khi dependency thay đổi theo từng lời gọi)

~~~java
import java.time.Clock;

final class DeadlinePolicy {
    boolean expired(java.time.Instant deadline, Clock clock) {
        return clock.instant().isAfter(deadline);
    }
}
~~~

Một policy nhỏ có thể nhận Clock như tham số vì thời gian là input cho thao tác. Tránh đẩy quá nhiều dependency xuống mọi phương thức nếu chúng thực sự thuộc về vòng đời lớp; khi đó constructor injection rõ ràng hơn.

### Adapter / Ports and Adapters

Trong kiến trúc hexagonal, interface PaymentGateway là **port** do nghiệp vụ cần; HTTP client thật và stub trong test đều là **adapter** cung cấp port đó. Luồng phụ thuộc ở cấp mã nguồn hướng về abstraction; lúc chạy có thể kết nối adapter phù hợp.

Điều này cũng giúp thay đổi nhà cung cấp dịch vụ mà không cần viết lại quy tắc checkout. Tuy nhiên, không phải mọi lớp đều cần interface riêng: nếu một phép tính thuần túy không có I/O và không có nhiều cách cung cấp hợp lý, việc trích xuất interface chỉ để mock thường làm thiết kế phức tạp hơn.

## 6. Các kiểu thiết kế làm test khó và cách cải thiện

| Dấu hiệu khó kiểm thử | Hậu quả | Cách chỉnh sửa |
| --- | --- | --- |
| Tự new HTTP client, repository hoặc SMTP client ngay trong lớp nghiệp vụ | Test buộc truy cập hệ thống thật hoặc hack thay object | Nhận port/interface qua constructor |
| Gọi Instant.now() / LocalDate.now() trực tiếp trong business rule | Kết quả không ổn định theo thời điểm | Nhận Clock và gọi clock.instant() / LocalDate.now(clock) |
| Gọi System.getenv() ở nhiều nhánh nghiệp vụ | Test lệ thuộc cấu hình máy | Đọc cấu hình tại composition root, truyền value/config bất biến |
| Dùng static mutable state hoặc singleton toàn cục | Test ảnh hưởng lẫn nhau, khó chạy song song | Giới hạn trạng thái theo instance, có lifecycle và cách reset rõ |
| Luồng nghiệp vụ gọi sâu nhiều API ngoài trong cùng một phương thức | Khó xác định đâu là nguyên nhân lỗi | Chia trách nhiệm, tách adapter và orchestration |
| Mock toàn bộ object nội bộ | Test gắn chặt thứ tự gọi và chi tiết implementation | Kiểm chứng kết quả quan sát được; mock tại ranh giới thực sự |

Đừng dùng interface để che giấu thiết kế có vấn đề. Nếu test phải dựng hàng chục mock mới gọi được một phương thức nhỏ, lớp có thể đang ôm quá nhiều trách nhiệm (vi phạm Single Responsibility Principle).

## 7. Phân biệt unit test và integration test

Các kiểm thử bên trên chứng minh CheckoutService ra quyết định đúng **khi các dependency tuân theo hợp đồng được giả lập**. Chúng chưa chứng minh adapter thanh toán thật định dạng payload đúng, email thật đến nơi, timeout được xử lý đúng hoặc hệ thống khôi phục được sau sự cố.

Phân tầng hữu ích:

~~~mermaid
flowchart TD
    U["Unit test: CheckoutService + test doubles"] --> C["Quy tắc nghiệp vụ"]
    I["Integration test: adapter + dịch vụ test/database"] --> K["Giao thức, serialization, giao dịch"]
    E["End-to-end test: luồng ứng dụng thực"] --> H["Cấu hình và phối hợp toàn hệ thống"]
~~~

Một PaymentGateway thực cần integration/contract test cho API của nhà cung cấp, nhất là mã lỗi, retry và timeout. Unit test vẫn có vai trò riêng là đưa ra phản hồi nhanh, tái lập được về các nhánh nghiệp vụ. Không nên dùng fake để kết luận adapter thực đã vận hành chính xác.

## 8. Những nguyên tắc quan trọng khi thay thế phụ thuộc

1. **Kiểm soát tính bất định:** đồng hồ, mạng, random, file, database là những ứng viên cần tách nếu ảnh hưởng tới test. Với random, có thể tiêm một Random hoặc nguồn sinh số với seed cố định nếu hợp đồng yêu cầu.
2. **Kiểm soát trạng thái:** mỗi test dùng đối tượng giả sạch; tránh chia sẻ static mutable fixture giữa test.
3. **Giữ fake khớp hợp đồng:** fake trả kết quả dễ dãi hơn API thật có thể khiến test xanh nhưng production lỗi. Hãy kiểm tra adapter bằng integration test và cập nhật fake khi hợp đồng thay đổi.
4. **Kiểm tra nhánh lỗi:** từ chối, exception, dữ liệu thiếu, timeout là những kịch bản không thể bỏ qua chỉ vì happy path đã chạy đúng.
5. **Không làm giả chính đối tượng cần kiểm thử:** muốn test CheckoutService thì tạo CheckoutService thật rồi thay các cộng tác viên phía ngoài.
6. **Ưu tiên assertion có ý nghĩa nghiệp vụ:** ví dụ không gửi biên nhận cho thanh toán bị từ chối; đừng mặc định verify mọi getter, setter hoặc thứ tự gọi nội bộ.
7. **Tách nơi dựng ứng dụng khỏi nghiệp vụ:** composition root giữ quyết định triển khai, cấu hình và vòng đời; service chỉ xử lý việc của mình.
8. **Không coi dependency injection framework là bắt buộc:** thao tác new CheckoutService(fakeGateway, recordingSender, fixedClock) đã là DI hợp lệ.

## 9. Bài tập ứng dụng

**Bài 1 — Thêm bước lưu giao dịch.** Tạo interface TransactionRepository với phương thức save(...); tiêm qua constructor. Dùng RecordingRepository trong test để xác nhận chỉ lưu khi gateway trả true. Quyết định rõ hành vi nếu lưu thất bại và test theo quy tắc đó.

**Bài 2 — Thời gian hết hạn.** Bổ sung giới hạn checkout chỉ được phép trước một hạn chót truyền vào. Dùng Clock.fixed(...) để kiểm tra thời điểm trước, bằng và sau hạn chót, làm rõ biên đúng/sai trong tài liệu.

**Bài 3 — Lỗi gửi thông báo.** Cho RecordingSender ném một exception. Quan sát trạng thái thanh toán có thể đã thành công dù checkout ném lỗi. Đề xuất thiết kế lưu trạng thái giao dịch và phát sự kiện hoặc transactional outbox để gửi lại an toàn, tránh charge thêm lần nữa.

**Tự đánh giá:** Nếu có thể dựng lớp nghiệp vụ bằng các dependency kiểm soát được, chạy được cả nhánh thành công/thất bại mà không cần dịch vụ thật, và vẫn dành kiểm thử riêng cho adapter thật, bạn đã tạo được điểm thay thế phụ thuộc đúng mục đích trong OOP.