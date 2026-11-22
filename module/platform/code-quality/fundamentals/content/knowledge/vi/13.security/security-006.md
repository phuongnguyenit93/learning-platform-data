# Giới hạn dữ liệu nhạy cảm trong log

Trong chương **Bảo mật** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu một nguyên tắc vừa liên quan đến bảo vệ thông tin vừa ảnh hưởng trực tiếp đến khả năng bảo trì: **chỉ ghi vào log những dữ liệu cần thiết cho mục đích chẩn đoán, giám sát và kiểm toán đã xác định**.

Module **CODE_QUALITY_FUNDAMENTALS** hướng đến việc hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Log là nguồn bằng chứng quan trọng khi hệ thống gặp lỗi. Tuy nhiên, một dòng log chứa mật khẩu, access token hoặc dữ liệu cá nhân có thể được sao chép sang hệ thống tập trung, bản sao lưu, công cụ cảnh báo, bảng điều khiển hay kênh trao đổi sự cố. Khi đó, phạm vi lộ lọt có thể lớn hơn nhiều so với phạm vi của một request ban đầu.

> **Nguyên tắc cốt lõi: không ghi dữ liệu nhạy cảm chỉ vì nó đang có sẵn trong một object hoặc request. Hãy thiết kế sự kiện log với những trường được phép ghi theo nhu cầu chẩn đoán cụ thể, rồi bảo vệ dữ liệu đó trong suốt vòng đời lưu trữ.**

Mục tiêu không phải ngừng ghi log. Mục tiêu là **duy trì khả năng điều tra sự cố mà không biến hệ thống quan sát thành nơi tập trung bí mật và thông tin quá mức cần thiết**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt dữ liệu cần cho chẩn đoán với bí mật, thông tin định danh và dữ liệu nghiệp vụ nhạy cảm.
2. Giải thích những đường đi khiến dữ liệu nhạy cảm vô tình xuất hiện trong log: request/response, `toString()`, exception, URL, header, MDC và thư viện bên thứ ba.
3. Thiết kế sự kiện log **theo danh sách trường được phép** (*allowlist*) thay vì ghi cả object rồi tìm cách che bớt.
4. Sử dụng logging có cấu trúc, mã lỗi ổn định và correlation ID một cách có kiểm soát.
5. Hiểu giới hạn của việc masking, redaction và pseudonymization, kể cả khi dữ liệu đã được băm.
6. Bảo vệ quyền truy cập, thời gian lưu, đường truyền và bản sao dữ liệu log.
7. Viết kiểm thử và checklist review nhằm phát hiện rò rỉ dữ liệu nhạy cảm qua log.
8. Cân bằng giữa nhu cầu điều tra, kiểm toán, hiệu năng và bảo vệ thông tin trong hệ thống Java.

## 2. Vì sao log là bề mặt rủi ro?

Log thường không chỉ nằm trên máy chạy ứng dụng. Một chuỗi xử lý có thể là:

~~~text
Ứng dụng Java
      |
      v
Logger / framework
      |
      v
File hoặc stdout của container
      |
      v
Agent thu thập log
      |
      v
Hệ thống tìm kiếm / tập trung log
      |
      +--> Dashboard và cảnh báo
      +--> Hệ thống lưu trữ dài hạn
      +--> Xuất dữ liệu để điều tra sự cố
      +--> Bản sao hoặc tích hợp của bên thứ ba
~~~

Mỗi chặng có thể có quyền truy cập, chính sách lưu trữ và cơ chế sao lưu khác nhau. Nếu một token xuất hiện ngay từ dòng đầu tiên, chỉ cấu hình quyền đọc ở dashboard cuối **không xóa được những bản sao đã tồn tại** ở các tầng trước.

### 2.1. Những hậu quả có thể xảy ra

- **Lộ bí mật xác thực:** token hoặc cookie phiên bị lộ có thể bị dùng để truy cập tài nguyên nếu còn hiệu lực và không có lớp bảo vệ khác.
- **Lộ thông tin cá nhân:** email, số điện thoại, địa chỉ, số định danh hoặc dữ liệu về hành vi người dùng trở nên tìm kiếm được ngoài phạm vi nghiệp vụ ban đầu.
- **Mở rộng phạm vi sự cố:** một bản log được chia sẻ để xử lý lỗi có thể vô tình tiết lộ thông tin của nhiều người dùng.
- **Tăng công sức quản trị:** phải kiểm soát quyền truy cập, thời gian lưu, yêu cầu xóa dữ liệu và khả năng xuất bản sao.
- **Khó thay đổi mã an toàn:** mỗi lần thêm trường vào request DTO có thể tạo thêm dữ liệu bị ghi log nếu ứng dụng đang log toàn bộ object.

Không nên xem log là dữ liệu “không quan trọng vì chỉ dùng để debug”. Nhiều tổ chức cần log để điều tra sự cố và kiểm toán; chính vì được giữ và chia sẻ rộng, nó cần hợp đồng dữ liệu rõ ràng.

## 3. Dữ liệu nào cần tránh đưa vào log?

Mức độ nhạy cảm phụ thuộc ngữ cảnh, mục đích và quy định áp dụng. Bảng sau là hướng dẫn kỹ thuật để thiết kế; không phải danh sách đầy đủ cho mọi hệ thống.

| Nhóm dữ liệu | Ví dụ | Cách tiếp cận ưu tiên |
| --- | --- | --- |
| **Bí mật xác thực** | Mật khẩu, OTP, access/refresh token, API key, private key, session cookie. | Không ghi giá trị vào log; không dựa vào masking một phần như biện pháp chính. |
| **Dữ liệu thanh toán** | Số thẻ đầy đủ, mã xác thực thẻ, dữ liệu thanh toán từ nhà cung cấp. | Không log payload gốc; chỉ dùng mã trạng thái hoặc định danh giao dịch đã phân loại và cho phép. |
| **Thông tin định danh cá nhân** | Email, điện thoại, địa chỉ, số giấy tờ, thông tin định vị chính xác. | Chỉ ghi khi có mục đích rõ và được phép; ưu tiên mã tham chiếu nội bộ hạn chế truy cập. |
| **Dữ liệu đặc biệt nhạy cảm** | Hồ sơ sức khỏe, sinh trắc học, thông tin tài khoản, nội dung riêng tư. | Tránh ghi nội dung; dùng phân loại lỗi hoặc trạng thái thay thế. |
| **Dữ liệu từ request/response** | Body, query string, form, header `Authorization`, `Cookie`. | Không ghi nguyên khối; chọn trường an toàn theo schema log. |
| **Định danh kỹ thuật** | Request ID, order ID, IP, user-agent, device ID. | Có thể vẫn là dữ liệu cá nhân hoặc cho phép liên kết hoạt động; đánh giá mục đích, thời hạn và quyền truy cập. |
| **Chi tiết hệ thống nội bộ** | Chuỗi kết nối, tên host nội bộ, SQL chứa tham số, cấu hình secret. | Chỉ ghi những thông tin cần chẩn đoán; tránh tiết lộ cấu hình và dữ liệu đầu vào. |

**Hai điểm dễ nhầm:**

1. Một mã định danh không phải mật khẩu **vẫn có thể nhạy cảm** nếu dùng để truy xuất hồ sơ hoặc liên kết hành vi của người dùng.
2. Một giá trị đã được che vài ký tự hoặc đã được băm **không tự động trở thành dữ liệu vô hại**. Mức độ có thể nhận diện lại và phạm vi chia sẻ vẫn cần được xem xét.

## 4. Thiết kế từ mục đích chẩn đoán, không từ object có sẵn

Trước khi thêm dòng `log.info(...)`, hãy trả lời:

- Sự kiện nào cần được biết? Ví dụ: thanh toán bị từ chối, giao hàng không thành công, quota bị vượt.
- Người vận hành cần phân biệt những nguyên nhân nào để xử lý? Ví dụ: timeout, đầu vào sai, cấu hình chưa có.
- Cần nối những sự kiện nào trong cùng một lần xử lý?
- Trường dữ liệu nào đủ trả lời câu hỏi đó?
- Có thể quan sát bằng metrics hoặc một mã lỗi ổn định thay vì nội dung request không?

### 4.1. So sánh log quá mức với log có chủ đích

Ví dụ không nên dùng:

~~~java
// Không nên: request có thể chứa email, cardToken và các trường khác.
logger.info("Charging payment: {}", paymentRequest);
~~~

Nếu `PaymentRequest` là `record`, `toString()` mặc định có thể đưa các thành phần của record vào chuỗi biểu diễn. Việc thêm trường nhạy cảm vào record trong tương lai có thể làm log rò rỉ dữ liệu mà người sửa DTO không hề chạm đến câu lệnh logging.

Cách tốt hơn:

~~~java
logger.info("payment_attempt_completed event_id={} outcome={} error_code={}",
        eventId, outcome, errorCode);
~~~

Trong ví dụ, `eventId` là mã ngẫu nhiên do server sinh cho lần xử lý, `outcome` và `errorCode` đến từ tập giá trị đã định nghĩa. Không có email, card token, toàn bộ request hay response.

Mã sự kiện cũng cần được phân loại và có thời hạn lưu hợp lý. **Thay dữ liệu nhạy cảm bằng mã tham chiếu không loại bỏ mọi nghĩa vụ bảo vệ**, nhưng thường giúp giới hạn lượng thông tin đi vào log.

### 4.2. Allowlist tốt hơn denylist khi thiết kế schema log

**Denylist**: “Ghi toàn bộ request, ngoại trừ trường `password`, `token` và `secret`.”

**Allowlist**: “Chỉ ghi `eventId`, `operation`, `outcome`, `errorCode`.”

Nếu request có thêm trường `refreshCredential` hoặc `medicalNote`, denylist có thể bỏ sót. Với allowlist, trường mới không tự xuất hiện trong log; muốn thêm phải chủ động xem xét.

Đây là một dạng **data minimization**: chỉ thu thập dữ liệu đáp ứng mục đích đã biết.

## 5. Ví dụ Java: thiết kế ranh giới log an toàn cho thanh toán

Giả sử một dịch vụ xử lý yêu cầu thanh toán chứa email và token do nhà cung cấp thanh toán phát hành. Yêu cầu chẩn đoán là:

- Biết có bao nhiêu lần thanh toán **được chấp nhận**, **bị từ chối** hoặc **lỗi kết nối**.
- Có mã sự kiện do server tạo để liên hệ các bước xử lý trong phạm vi nội bộ.
- Không đưa email, token thanh toán hay thông điệp lỗi thô từ nhà cung cấp vào log.
- Không coi log là nguồn dữ liệu tài chính chính thức; giao dịch phải được quản lý riêng theo hợp đồng.

### 5.1. Hợp đồng dữ liệu và sự kiện chỉ chứa trường cho phép

Ví dụ dùng Java 17+ và `record`:

~~~java
import java.util.Objects;
import java.util.UUID;

record ChargeRequest(String email, String paymentToken, long amountCents) {
    ChargeRequest {
        Objects.requireNonNull(email, "email");
        Objects.requireNonNull(paymentToken, "paymentToken");
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
    }
}

enum ChargeStatus {
    APPROVED, DECLINED
}

record ChargeResult(ChargeStatus status) {}

record SafeChargeEvent(
        UUID eventId,
        String operation,
        String outcome,
        String errorCode) {}

interface ChargeEventSink {
    void record(SafeChargeEvent event);
}

interface PaymentGateway {
    ChargeResult charge(ChargeRequest request);
}

final class GatewayTimeoutException extends RuntimeException {
    GatewayTimeoutException(String message) {
        super(message);
    }
}
~~~

Chú ý **`SafeChargeEvent` không có trường email hay paymentToken**. Một khi các thành phần xử lý chỉ nhận kiểu sự kiện này, việc vô tình truyền nguyên request cho logger sẽ khó xảy ra hơn.

### 5.2. Xử lý nghiệp vụ và ghi sự kiện qua cổng riêng

~~~java
import java.util.Objects;
import java.util.UUID;

final class PaymentService {
    private final PaymentGateway gateway;
    private final ChargeEventSink eventSink;

    PaymentService(PaymentGateway gateway, ChargeEventSink eventSink) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.eventSink = Objects.requireNonNull(eventSink, "eventSink");
    }

    ChargeResult charge(ChargeRequest request) {
        Objects.requireNonNull(request, "request");
        UUID eventId = UUID.randomUUID();

        try {
            ChargeResult result = gateway.charge(request);

            eventSink.record(new SafeChargeEvent(
                    eventId,
                    "PAYMENT_CHARGE",
                    result.status().name(),
                    "NONE"));

            return result;
        } catch (GatewayTimeoutException exception) {
            eventSink.record(new SafeChargeEvent(
                    eventId,
                    "PAYMENT_CHARGE",
                    "ERROR",
                    "GATEWAY_TIMEOUT"));
            throw exception;
        }
    }
}
~~~

Trong ví dụ này:

- `eventId` được server sinh, không lấy nguyên văn một chuỗi không tin cậy từ request.
- Kết quả và mã lỗi là **giá trị hữu hạn, có ý nghĩa chẩn đoán**.
- Dù `GatewayTimeoutException` có message chứa phản hồi thô từ nhà cung cấp, sự kiện không sao chép message ấy.
- Cổng `ChargeEventSink` cho phép kiểm thử nội dung log mà không gửi tới hệ thống tập trung thật.

**Giới hạn quan trọng:** mã trên chỉ minh họa **giới hạn dữ liệu của sự kiện log**, không thiết kế tính nhất quán của quy trình thanh toán. Nếu `eventSink.record(...)` ném ngoại lệ, hành vi `charge` cũng có thể thay đổi; với giao dịch thật cần quyết định log là best-effort hay có yêu cầu kiểm toán bắt buộc, đồng thời dùng cơ chế ghi sự kiện bền phù hợp. Không tự đồng nhất một dòng log ứng dụng với biên bản giao dịch không thể mất.

### 5.3. Triển khai log an toàn với SLF4J

Ví dụ dùng API `org.slf4j` và một logging provider tương thích:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class Slf4jChargeEventSink implements ChargeEventSink {
    private static final Logger LOG =
            LoggerFactory.getLogger(Slf4jChargeEventSink.class);

    @Override
    public void record(SafeChargeEvent event) {
        LOG.info(
                "payment_attempt event_id={} operation={} outcome={} error_code={}",
                event.eventId(),
                event.operation(),
                event.outcome(),
                event.errorCode());
    }
}
~~~

Ví dụ chưa lựa chọn định dạng JSON hoặc cấu hình logger; nó minh họa **lời gọi logging có các trường được phép**. Khi dùng structured logging, nên giữ tên trường và loại dữ liệu nhất quán để các hệ thống tìm kiếm/cảnh báo có thể xử lý ổn định.

**Không nên thay bằng** `LOG.info("request={}", request)`, `LOG.info("exception={}", exception)` hoặc `LOG.error("payment failed", exception)` một cách không kiểm soát: `toString()`, message hay stack trace từ thư viện bên ngoài **có thể** chứa thông tin nhạy cảm. Nếu cần stack trace, phải xác định nguồn dữ liệu, công cụ xử lý và chính sách bảo vệ phù hợp thay vì mặc định mọi exception đều an toàn để ghi.

### 5.4. Kiểm thử đúng hợp đồng log

Dùng một sink trong bộ nhớ để xác nhận nội dung sự kiện đã được chọn, không phụ thuộc vào cấu hình log bên ngoài:

~~~java
import java.util.ArrayList;
import java.util.List;

final class InMemoryChargeEventSink implements ChargeEventSink {
    final List<SafeChargeEvent> events = new ArrayList<>();

    @Override
    public void record(SafeChargeEvent event) {
        events.add(event);
    }
}
~~~

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class PaymentServiceLoggingTest {
    @Test
    void approvedPaymentProducesOnlySafeEventFields() {
        var events = new InMemoryChargeEventSink();
        PaymentGateway gateway = request ->
                new ChargeResult(ChargeStatus.APPROVED);
        var service = new PaymentService(gateway, events);

        var request = new ChargeRequest(
                "private@example.test",
                "sensitive-payment-token",
                100_000);

        ChargeResult result = service.charge(request);

        assertEquals(ChargeStatus.APPROVED, result.status());
        assertEquals(1, events.events.size());

        SafeChargeEvent event = events.events.get(0);
        assertNotNull(event.eventId());
        assertEquals("PAYMENT_CHARGE", event.operation());
        assertEquals("APPROVED", event.outcome());
        assertEquals("NONE", event.errorCode());
    }

    @Test
    void timeoutUsesStableErrorCodeInsteadOfRawMessage() {
        var events = new InMemoryChargeEventSink();
        PaymentGateway gateway = request -> {
            throw new GatewayTimeoutException(
                    "Provider response contained a credential");
        };
        var service = new PaymentService(gateway, events);

        assertThrows(GatewayTimeoutException.class,
                () -> service.charge(new ChargeRequest(
                        "private@example.test",
                        "another-sensitive-token",
                        100_000)));

        assertEquals(1, events.events.size());
        SafeChargeEvent event = events.events.get(0);
        assertEquals("ERROR", event.outcome());
        assertEquals("GATEWAY_TIMEOUT", event.errorCode());
    }
}
~~~

Những test này kiểm tra **schema sự kiện** tại ranh giới ứng dụng. Vì `SafeChargeEvent` không chứa các trường từ `ChargeRequest`, ví dụ giảm được nguy cơ đưa email và token qua cổng này.

Tuy nhiên, các test **không chứng minh toàn bộ hệ thống không rò rỉ**. Thư viện HTTP, SDK của nhà cung cấp, bộ lọc web, truy vết tự động hoặc một logger khác vẫn có thể ghi dữ liệu trước/sau lớp `PaymentService`. Cần kiểm thử cấu hình logging thực tế ở các điểm biên thích hợp.

## 6. Những đường rò rỉ phổ biến trong ứng dụng Java

### 6.1. Ghi cả request/response hoặc object bằng `toString()`

Các câu lệnh như sau cần được review cẩn thận:

~~~java
logger.debug("request={}", request);
logger.info("customer={}", customer);
logger.warn("provider response={}", response);
~~~

Nếu object có thêm trường nhạy cảm, log có thể đổi theo mà không có sửa đổi ở nơi logging. Với `record`, nhiều IDE và thư viện còn sinh sẵn `toString()` liệt kê trường.

**Cải thiện:** tạo event DTO với danh sách trường được phép; không dùng request/response object làm payload log mặc định. Nếu thật sự cần một định danh để tìm lại sự cố, chọn định danh kỹ thuật được phân loại, quản lý quyền đọc và thời hạn lưu.

### 6.2. Header, cookie và query string

Cẩn trọng với log:

- Tất cả HTTP headers, nhất là `Authorization` và `Cookie`.
- URL đầy đủ chứa query parameter như `access_token`, mã khôi phục hoặc thông tin người dùng.
- Query string của form xác thực hoặc liên kết đặt lại mật khẩu.
- Payload của các endpoint đăng nhập, thanh toán, hỗ trợ khách hàng.

Ngay cả khi ứng dụng tự ghi log an toàn, reverse proxy hoặc middleware có thể tự ghi URL đầy đủ. Cần kiểm tra cấu hình ở **toàn bộ luồng thu thập**, không chỉ dòng `logger.info` do đội ứng dụng viết.

### 6.3. Exception message, stack trace và chuỗi lỗi gốc

Một exception có thể kèm:

- URL của request tới nhà cung cấp.
- Câu SQL cùng giá trị tham số.
- Nội dung phản hồi HTTP.
- Đường dẫn nội bộ hoặc một phần dữ liệu người dùng.
- Giá trị cấu hình được đưa vào thông báo lỗi.

Vì vậy, `logger.error("failure", ex)` không phải lúc nào cũng an toàn. Một hướng thiết kế là ghi **mã lỗi phân loại** vào hệ thống log thông thường, còn chẩn đoán chi tiết chỉ được cung cấp theo cơ chế kiểm soát riêng khi thực sự cần và đã đánh giá dữ liệu.

Không nên xóa toàn bộ khả năng chẩn đoán bất chấp hậu quả; thay vào đó, xác định **đúng lớp thông tin cần thiết** và nơi được phép giữ thông tin ấy.

### 6.4. Log được tạo tự động từ framework hoặc thư viện

Nguồn rủi ro có thể nằm ở:

- HTTP client bật wire logging.
- ORM/SQL logger ghi giá trị bind parameter.
- Middleware ghi request/response body.
- Framework security ghi thông tin xác thực.
- Bộ thu thập trace tự động gắn attributes từ headers.
- Exception handler ghi lại toàn bộ request context.

**Đội phát triển không thể chỉ kiểm tra các câu lệnh logging trong code nghiệp vụ.** Cần lập danh sách những thành phần tự phát log, xem cấu hình theo môi trường và kiểm tra khi nâng cấp thư viện.

### 6.5. Dữ liệu trong MDC hoặc context dùng chung

Mapped Diagnostic Context (MDC) thường được dùng để đưa correlation ID vào nhiều dòng log. Nếu đặt email, số điện thoại hay token vào MDC, **mọi dòng log trong phạm vi đó** có thể mang theo dữ liệu này mà tác giả câu lệnh log không nhận ra.

MDC cũng có vòng đời cần được quản lý, đặc biệt với thread pool. Dữ liệu ngữ cảnh không được dọn có thể xuất hiện trong request tiếp theo khi luồng được tái sử dụng.

## 7. Correlation ID: đủ để truy vết mà không dùng bí mật

Một **correlation ID** giúp nối những sự kiện thuộc cùng một request hoặc giao dịch. Thay vì ghi email vào mỗi dòng, hệ thống có thể sử dụng một định danh ngẫu nhiên không chứa ý nghĩa nghiệp vụ trực tiếp.

Ví dụ với SLF4J MDC:

~~~java
import java.util.UUID;
import org.slf4j.MDC;

static void handleRequest(Runnable action) {
    String eventId = UUID.randomUUID().toString();
    MDC.put("event_id", eventId);
    try {
        action.run();
    } finally {
        MDC.remove("event_id");
    }
}
~~~

Điều cần chú ý:

1. ID được tạo ở phía server, thay vì đưa nguyên chuỗi không tin cậy của client vào log.
2. `remove()` trong `finally` bảo đảm dọn context sau xử lý, kể cả khi có ngoại lệ.
3. `MDC` phụ thuộc cách logging backend triển khai và thường gắn với ngữ cảnh thực thi hiện tại; **không mặc định được truyền sang thread khác** trong tác vụ bất đồng bộ.
4. ID vẫn có thể được dùng để liên kết nhiều sự kiện. Vì vậy, phân quyền và thời gian lưu vẫn cần thiết.

Nếu muốn nhận correlation ID từ hệ thống phía trước, phải có chính sách tin cậy, kiểm tra định dạng, giới hạn độ dài và xử lý ký tự điều khiển. Không tin tưởng nguyên văn ID do client gửi rồi chèn vào log.

## 8. Log injection và dữ liệu không tin cậy

Ngoài việc để lộ thông tin, log còn có rủi ro **bị làm sai lệch nội dung** nếu chèn trực tiếp giá trị do người dùng kiểm soát. Chuỗi chứa ký tự xuống dòng hoặc ký tự điều khiển có thể làm một thông điệp trông như nhiều bản ghi khác nhau trong hệ thống log dạng văn bản.

Ví dụ cần tránh:

~~~java
// userInput có thể chứa dấu xuống dòng hoặc ký tự điều khiển.
logger.info("search text: " + userInput);
~~~

Vấn đề không chỉ là dùng phép nối chuỗi thay cho placeholder. **Placeholder cũng không tự động bảo đảm mọi sink xử lý chuỗi không tin cậy an toàn**. Điều quan trọng là:

- Không ghi nội dung tìm kiếm nếu không cần thiết.
- Nếu cần giá trị từ bên ngoài, kiểm tra giới hạn độ dài, tập ký tự và yêu cầu dữ liệu được phép ghi.
- Sử dụng bộ mã hóa hoặc structured logging phù hợp với định dạng của hệ thống nhận.
- Không đưa chuỗi không tin cậy vào phần định dạng hoặc tên trường của log.
- Kiểm thử đường đi tới sink thực tế; không suy luận rằng định dạng JSON tự giải quyết mọi vấn đề.

### 8.1. Logging có cấu trúc giúp ích nhưng không xóa rủi ro

Structured logging dùng cặp khóa–giá trị như `operation=PAYMENT_CHARGE`, `outcome=DECLINED`, `error_code=GATEWAY_TIMEOUT`. Nó giúp tìm kiếm, thống kê và áp dụng chính sách lọc nhất quán.

Tuy nhiên, một trường JSON mang tên `rawAuthorizationHeader` vẫn nguy hiểm nếu chứa token. **Cấu trúc tốt không thay thế lựa chọn dữ liệu tốt**.

## 9. Masking, redaction và pseudonymization: công dụng và giới hạn

Ba thuật ngữ thường gặp:

- **Masking:** che một phần hoặc toàn bộ ký tự khi hiển thị; ví dụ chỉ hiển thị phần cuối một giá trị theo chính sách cho phép.
- **Redaction:** loại bỏ hoặc thay thế nội dung nhạy cảm khỏi thông điệp hoặc trường dữ liệu.
- **Pseudonymization:** dùng một mã thay thế để giảm việc gắn trực tiếp dữ liệu với một cá nhân, trong khi khả năng liên kết lại có thể tồn tại theo cách quản lý.

| Kỹ thuật | Lợi ích có thể có | Giới hạn cần nhớ |
| --- | --- | --- |
| Không đưa dữ liệu nhạy cảm vào sự kiện ngay từ đầu | Ngăn phát tán ở nguồn, dễ kiểm tra schema. | Cần thiết kế rõ trường cho phép và rà soát các logger khác. |
| Redaction trước khi gửi | Giảm nguy cơ từ một số trường không thể tránh. | Có thể bỏ sót định dạng mới, nội dung mã hóa hoặc biến thể tên trường. |
| Bộ lọc tại log collector | Tăng lớp phòng vệ cho dữ liệu đến từ nhiều ứng dụng. | Dữ liệu gốc có thể đã tồn tại ở ứng dụng, stdout, file tạm hoặc agent. |
| Masking khi hiển thị | Giảm mức độ lộ cho người xem dashboard. | Giá trị gốc có thể vẫn nằm trong kho lưu trữ hoặc bản xuất. |
| Mã tham chiếu/pseudonym | Hỗ trợ nối sự kiện mà không lặp lại dữ liệu gốc. | Mã có thể vẫn nhận diện được khi ghép với dữ liệu khác; phải quản lý khóa ánh xạ và quyền truy cập. |

### 9.1. Vì sao regex redaction không đủ để làm biện pháp chính?

Một regex thay `password=...` có thể không bắt được:

- `pwd`, `passphrase`, tên trường mới.
- JSON lồng nhau hoặc dữ liệu được escape theo cách khác.
- Dữ liệu nằm trong thông điệp ngoại lệ của thư viện.
- Mã bí mật được chuyển thành chuỗi URL-encoded hoặc base64.
- Một phần bí mật bị chia giữa nhiều trường hoặc nhiều dòng.

Nếu đầu vào mới xuất hiện mà bộ lọc chưa biết, dữ liệu có thể lọt qua. Vì vậy, **đưa dữ liệu đúng vào log ngay từ nguồn** đáng tin hơn việc log tất cả rồi hy vọng bộ lọc bắt hết.

### 9.2. Băm không đồng nghĩa ẩn danh an toàn

Băm một email hoặc số điện thoại bằng SHA-256 không tự bảo đảm không thể suy ra giá trị gốc. Miền giá trị có thể bị đoán và so sánh với bảng băm; cùng dữ liệu có thể tạo cùng hash, cho phép liên kết hành vi giữa các lần xuất hiện.

Nếu cần một định danh ổn định để nối sự kiện, có thể cân nhắc mã ngẫu nhiên hoặc cơ chế dẫn xuất có khóa như HMAC **sau khi được đánh giá về mục đích, quản lý khóa và khả năng liên kết**. Không nên mặc định biến dữ liệu cá nhân thành hash là đã có thể lưu vô hạn hoặc chia sẻ không hạn chế.

### 9.3. Mã hóa log không thay thế giới hạn dữ liệu

Mã hóa khi truyền và lưu trữ có thể giảm rủi ro truy cập trái phép, nhưng người có quyền giải mã vẫn có thể nhìn thấy dữ liệu. Bản sao đã giải mã, công cụ tìm kiếm và xuất dữ liệu cũng có rủi ro riêng. **Thu thập tối thiểu** vẫn là biện pháp nền tảng.

## 10. Kiểm soát vòng đời log sau khi đã ghi

Mã nguồn an toàn hơn nếu schema log hạn chế dữ liệu từ đầu, nhưng rủi ro vẫn tồn tại ở khâu thu thập và vận hành.

### 10.1. Quyền truy cập theo nhu cầu công việc

Không phải mọi kỹ sư hoặc nhóm hỗ trợ đều cần đọc toàn bộ log ở mọi môi trường. Nên áp dụng quyền truy cập phù hợp với trách nhiệm, ghi nhận hoạt động truy cập khi cần, và có quy trình rõ để cấp quyền điều tra sự cố.

Cần chú ý quyền với:

- Log production so với log test.
- Dashboard, truy vấn tìm kiếm, tải file và xuất dữ liệu.
- Công cụ cảnh báo gửi thông điệp sang chat/email.
- Tài khoản dịch vụ thu thập log và tích hợp bên thứ ba.

Một bảng điều khiển chỉ hiển thị vài trường không có nghĩa mọi người đã mất quyền đọc bản log thô từ API của hệ thống lưu trữ.

### 10.2. Thời hạn lưu và xóa dữ liệu

Log cần có **retention policy** theo mục đích: chẩn đoán lỗi ngắn hạn, phát hiện bất thường hoặc kiểm toán theo yêu cầu. Khi hết thời hạn, cần cơ chế xóa hoặc hết hạn dữ liệu trong kho chính và xem xét cách xử lý bản sao, bản xuất và sao lưu theo chính sách tổ chức.

Không nên giữ log “phòng khi một ngày nào đó cần” mà không xác định giới hạn. Lưu càng lâu làm phạm vi dữ liệu tồn tại càng lớn; lưu quá ngắn có thể làm thiếu bằng chứng điều tra. Đây là một đánh đổi cần quyết định theo rủi ro và yêu cầu thực tế.

### 10.3. Truyền và lưu trữ an toàn

Các điểm thường phải kiểm tra:

- Kênh truyền log giữa ứng dụng, agent và hệ thống tập trung được bảo vệ thích hợp.
- Kho lưu trữ và các bản sao có quyền truy cập được quản lý.
- Thao tác xuất dữ liệu có chính sách và khả năng truy vết.
- Không ghi log nhạy cảm vào file tạm hoặc nơi công khai ngoài quy trình đã chọn.
- Chính sách bảo vệ được áp dụng cả cho công cụ APM, tracing, metrics có labels và crash dump khi chúng có khả năng chứa dữ liệu tương tự.

Việc quản lý log phải bao quát **toàn bộ hành trình của dữ liệu**, không chỉ cấu hình logger trong Java.

## 11. Khi cần điều tra sự cố sâu hơn bình thường

Đôi khi một lỗi production chỉ xuất hiện trên dữ liệu hoặc hành vi khó tái hiện. Đội phát triển có thể muốn bật mức `DEBUG` và ghi toàn bộ request để điều tra nhanh. Đây là thời điểm rủi ro tăng mạnh.

Một quy trình phù hợp hơn:

1. **Đặt câu hỏi điều tra cụ thể:** cần xác nhận trạng thái nào, nhánh nào, phản hồi mã lỗi nào?
2. **Tăng khả năng quan sát bằng trường an toàn:** event ID, mã lỗi, thời điểm, khoảng thời gian xử lý, số lượng bản ghi hoặc trạng thái đã phân loại.
3. **Ưu tiên tái hiện tại môi trường kiểm thử** với dữ liệu giả hoặc dữ liệu đã được xử lý theo chính sách.
4. Nếu cần thêm thông tin production, **đánh giá và phê duyệt phạm vi thu thập**, giới hạn người truy cập, thời gian bật và thời hạn lưu theo quy trình tổ chức.
5. **Tắt chế độ chẩn đoán đặc biệt** sau khi hoàn thành; rà soát các bản log hoặc bản xuất đã được tạo.
6. Bổ sung test/hợp đồng để lần sau không cần ghi dữ liệu nhạy cảm mới nhận ra cùng một loại lỗi.

Không nên cho rằng “chỉ bật DEBUG trong vài phút” khiến việc log token hoặc dữ liệu cá nhân trở nên an toàn.

## 12. Kiểm thử và kiểm tra để giảm nguy cơ rò rỉ

Bảo vệ thông tin trong log cần **cả thiết kế và bằng chứng kiểm tra**.

### 12.1. Unit test cho schema sự kiện

Trong ví dụ `SafeChargeEvent`, test xác nhận event chỉ có những trường được phép và đúng mã kết quả. Nó giúp ngăn các thay đổi vô tình đưa `ChargeRequest` vào cổng audit của service.

Tuy nhiên, việc chỉ assert `event.outcome()` đúng chưa tự động phát hiện nếu sau này ai đó sửa logger để ghi `request.toString()` ở một vị trí khác. Vì vậy, không nên dừng ở một unit test.

### 12.2. Test tích hợp với logger và cấu hình thực

Với những luồng quan trọng, có thể dùng dữ liệu kiểm thử đặc biệt (sentinel) có hình dạng giống dữ liệu nhạy cảm nhưng **không phải bí mật thật**, thực hiện request trong môi trường cô lập, thu nhận log từ sink thực tế rồi tìm xem sentinel có xuất hiện hay không.

Ví dụ quy trình:

~~~text
Tạo request test với email/token giả có dấu hiệu riêng
                     |
                     v
Chạy qua các lớp ứng dụng và framework trong môi trường test
                     |
                     v
Thu log ở điểm sau formatter/collector được dùng
                     |
                     v
Tìm dấu hiệu sentinel và kiểm tra schema
                     |
                     v
Fail test khi phát hiện dữ liệu không được phép
~~~

Kiểm tra này có thể phát hiện cấu hình ghi body/header ngoài ý muốn. Nhưng kết quả “không thấy sentinel” **không chứng minh mọi định dạng bí mật đều được bảo vệ**; cần thiết kế nguồn log an toàn và review thay đổi liên tục.

### 12.3. Review những điểm phát log có nguy cơ cao

Trong code review, kiểm tra có chủ đích những câu lệnh:

- Ghi trực tiếp `request`, `response`, `headers`, `body` hoặc dữ liệu từ DTO.
- Ghi `exception.getMessage()` hoặc full stack trace từ phụ thuộc ngoài.
- Bật logging truy vấn SQL kèm tham số.
- Đưa user ID, email hoặc token vào MDC.
- In cấu hình, biến môi trường hoặc đối tượng kết nối.
- Thay đổi formatter, logger hoặc cài đặt thư viện HTTP/APM.

Đừng chỉ tìm chuỗi `password`. Một request object có thể chứa dữ liệu nhạy cảm trong các trường đặt tên hoàn toàn khác.

### 12.4. Phân tích tĩnh và các quy tắc đội nhóm

Một số pattern có thể được phát hiện bằng lint hoặc review tự động, ví dụ việc log trực tiếp `Authorization` header hoặc đối tượng chứa trường được đánh dấu nhạy cảm. Nhưng công cụ tự động có thể bỏ sót các đường đi dữ liệu động hoặc thư viện ngoài.

Quy tắc đội nhóm đơn giản nhưng rõ có thể là: **log sự kiện theo schema cho phép, không log object nghiệp vụ tùy ý, và phải review khi bổ sung một trường mới vào sự kiện production**.

## 13. Tình huống thực tế: lỗi thanh toán kéo theo lộ token trong log

Giả sử hệ thống gặp timeout khi gọi nhà cung cấp thanh toán. Để tìm nguyên nhân, một lập trình viên thêm:

~~~java
// Không nên triển khai:
logger.error("Payment failure request={} error={}", request, exception);
~~~

`request` chứa email và token thanh toán. `exception` có thể chứa phản hồi thô của provider. Sau khi deploy, log được gửi sang bộ thu thập, cảnh báo và hệ thống lưu trữ dài hạn.

### 13.1. Phân tích sai sót

- **Mục tiêu chẩn đoán hợp lý:** biết timeout ở bước nào, tác động tới bao nhiêu request, có đang retry hay không.
- **Dữ liệu đã thu thập thừa:** email, token và thông điệp lỗi thô không cần thiết để thống kê timeout.
- **Phạm vi rủi ro:** có thể có nhiều bản sao của dòng log, không chỉ một file trên máy chủ.
- **Vấn đề thiết kế:** thay vì log một schema chẩn đoán, mã đang để kiểu dữ liệu request và exception quyết định nội dung ghi.

### 13.2. Cách cải thiện

Một sự kiện có thể chỉ cần:

~~~text
operation=PAYMENT_CHARGE
outcome=ERROR
error_code=GATEWAY_TIMEOUT
event_id=<mã ngẫu nhiên do server sinh>
duration_ms=<thời gian đã đo>
retry_decision=SCHEDULED
~~~

Các giá trị trên là **ví dụ trường chẩn đoán**, không phải log thực từ hệ thống. Nếu số lần retry hoặc thời gian xử lý có ràng buộc bảo mật riêng, chúng cũng cần được đánh giá theo chính sách.

Sau đó:

1. Loại việc ghi toàn bộ request và exception khỏi đường log thông thường.
2. Kiểm tra cấu hình HTTP client/SDK để tránh nguồn log tự động tương tự.
3. Bổ sung test kiểm tra schema và sentinel trong môi trường tích hợp.
4. Nếu thông tin nhạy cảm **đã đi vào production log**, xử lý như một sự kiện có khả năng lộ lọt: xác định hệ thống và bản sao liên quan, hạn chế truy cập, đánh giá phạm vi, thu hồi/đổi token khi phù hợp, và xóa hoặc cách ly dữ liệu theo quy trình.
5. Bổ sung quy tắc review để hạn chế việc tái diễn.

Điểm quan trọng là **xử lý cả dữ liệu đã phát tán**. Việc chỉ sửa dòng log trong phiên bản mới không tự xóa các bản sao cũ.

## 14. Đánh đổi: bảo mật và khả năng chẩn đoán

### 14.1. Quá ít log cũng có chi phí

Nếu ứng dụng chỉ ghi “error” cho mọi lỗi, người vận hành khó phân biệt timeout, đầu vào không hợp lệ, cấu hình sai và lỗi nghiệp vụ. Hậu quả có thể là điều tra chậm, sửa sai điểm hoặc thiếu bằng chứng về sự cố.

Giải pháp không phải log mọi thứ, mà là chọn **tập trường đủ khả năng chẩn đoán**: thao tác, kết quả, mã lỗi ổn định, mốc thời gian, phiên bản chính sách, độ trễ, ID tương quan nếu cần.

### 14.2. Thêm trường an toàn vẫn có chi phí

Mỗi trường log mới có thể tăng dung lượng, làm thay đổi schema dashboard, tăng số chiều trong metrics hoặc tạo thêm khả năng liên kết hoạt động. Nên xác định nhu cầu và chính sách trước khi thêm, kể cả khi trường không phải bí mật rõ ràng.

### 14.3. Kiểm toán không đồng nghĩa với ghi tự do

Một số sự kiện quan trọng cần bằng chứng kiểm toán với yêu cầu lưu giữ và tính toàn vẹn cao hơn log ứng dụng thông thường. Nếu nghiệp vụ yêu cầu ghi nhận giao dịch, cần thiết kế một **audit trail có hợp đồng và cơ chế bảo vệ riêng**: dữ liệu nào bắt buộc, ai được truy cập, khi nào ghi, có thể mất không, có cần chống sửa đổi hay không.

Không nên giải quyết yêu cầu ấy bằng việc ghi cả request chứa bí mật vào `logger.info`. **Dữ liệu kiểm toán được phép lưu** cũng phải giới hạn theo mục đích và chính sách.

## 15. Quy trình ra quyết định khi thêm một sự kiện log

Khi viết hoặc review một câu lệnh logging mới, áp dụng sáu bước:

**Bước 1 — Xác định mục đích.** Dòng log trả lời câu hỏi vận hành hoặc điều tra nào? Nếu không có mục đích cụ thể, cân nhắc không ghi.

**Bước 2 — Xác định mức nhạy cảm của dữ liệu.** Trường có chứa token, dữ liệu khách hàng, nội dung riêng tư hoặc định danh có khả năng liên kết không? Có cách diễn đạt bằng mã trạng thái không?

**Bước 3 — Thiết kế schema allowlist.** Ghi những trường an toàn thực sự cần. Tránh truyền nguyên request, exception, JSON payload hoặc object `toString()`.

**Bước 4 — Xem xét nguồn và vòng đời.** Dòng log có thể xuất hiện tại app, proxy, APM, collector, dashboard và bản xuất nào? Ai có quyền đọc và lưu bao lâu?

**Bước 5 — Kiểm tra bằng chứng.** Review mã, test schema và kiểm tra tích hợp các điểm ghi log quan trọng bằng dữ liệu giả. Đừng dựa hoàn toàn vào một bộ regex che dữ liệu.

**Bước 6 — Đánh giá lại khi hệ thống đổi.** Khi thêm field mới, cập nhật SDK, bật debug hay thay pipeline thu thập, kiểm tra khả năng rò rỉ và chính sách lưu tương ứng.

Một nhận xét code review có thể viết:

> “Mục tiêu của log này là chẩn đoán timeout thanh toán. Chúng ta chỉ cần `eventId`, `operation`, `errorCode` và thời gian xử lý. Việc ghi cả `ChargeRequest` sẽ đưa token và email vào hệ thống log tập trung. Đề nghị dùng sự kiện theo schema có trường được phép, đồng thời bổ sung test xác nhận dữ liệu giả nhạy cảm không xuất hiện trong sink.”

Nhận xét như vậy nêu rõ **rủi ro, mục đích và giải pháp cụ thể**, hữu ích hơn một quy tắc chung kiểu “không log thông tin nhạy cảm”.

## 16. Bài tập tình huống

### Tình huống A: request DTO thay đổi

Một service có dòng `logger.debug("request={}", request)`. Ban đầu `request` chỉ chứa mã tác vụ. Sau vài tháng, đội khác thêm `email` và `resetToken` vào record, nhưng không sửa dòng log.

**Câu hỏi:** rủi ro xuất hiện từ đâu? Tại sao code review thay đổi DTO cũng cần quan tâm logging?

**Gợi ý:** cách biểu diễn `toString()` của record có thể thay đổi cùng cấu trúc trường; log phụ thuộc ngầm vào kiểu dữ liệu. Nên đổi sang event schema có trường cho phép và rà soát nơi khác dùng request trực tiếp.

### Tình huống B: một hệ thống che email bằng hash

Một nhóm ghi SHA-256 của email để nối các sự kiện giữa nhiều phiên. Họ khẳng định “hash không còn là dữ liệu người dùng nên có thể lưu mãi”.

**Câu hỏi:** kết luận này thiếu điều gì?

**Gợi ý:** hash có thể bị đoán bằng từ điển, đặc biệt với miền dữ liệu dễ đoán; cùng hash cho phép liên kết nhiều hoạt động. Cần cân nhắc mục đích, quyền truy cập, retention, phương pháp tạo mã và khả năng nhận diện lại.

### Tình huống C: lỗi chỉ xuất hiện ở production

Nhóm vận hành đề nghị bật HTTP wire logging cho mọi request trong một tuần để bắt lỗi kết nối.

**Câu hỏi:** những nguy cơ nào cần kiểm tra và nên thử giải pháp nào trước?

**Gợi ý:** wire logging có thể ghi headers, cookies, query string và body. Trước hết xác định tín hiệu cần thu (trạng thái, thời lượng, mã lỗi, endpoint đã phân loại); dùng log schema an toàn, metrics và trace có giới hạn, chỉ thu chi tiết hơn qua quy trình có kiểm soát nếu thật cần.

### Tình huống D: đã xóa dòng log nhưng dữ liệu vẫn lộ

Một token đã bị ghi vào log trong một ngày. Lập trình viên xóa câu lệnh và deploy bản mới, tuyên bố sự cố đã kết thúc.

**Câu hỏi:** còn những bước nào ngoài thay mã?

**Gợi ý:** phải xác định các hệ thống và bản sao đã nhận dữ liệu, giới hạn quyền truy cập, đánh giá phạm vi, xử lý token còn hiệu lực và thực hiện xóa/cách ly hoặc thông báo theo quy trình áp dụng. Việc sửa code chỉ ngăn phát sinh mới từ dòng log đó.

## 17. Checklist review logging an toàn

- [ ] Dòng log có mục đích chẩn đoán/giám sát/kiểm toán cụ thể.
- [ ] Schema chỉ gồm các trường được phép, không ghi nguyên request/response.
- [ ] Không ghi mật khẩu, OTP, API key, access/refresh token, cookie phiên hoặc bí mật thanh toán.
- [ ] Email, điện thoại, địa chỉ, IP và định danh có khả năng liên kết đã được phân loại theo ngữ cảnh.
- [ ] Tôi đã rà soát `toString()` của DTO/record và các trường có thể được thêm về sau.
- [ ] Không mặc định exception message hoặc stack trace từ thư viện ngoài là an toàn.
- [ ] Log của HTTP client, ORM, framework, proxy và APM đã được xem xét.
- [ ] Correlation ID có nguồn tin cậy, định dạng phù hợp và vòng đời MDC được dọn đúng.
- [ ] Không chèn nguyên văn dữ liệu không tin cậy vào log mà bỏ qua yêu cầu mã hóa/giới hạn độ dài.
- [ ] Redaction và masking là lớp bổ sung, không thay thế thu thập tối thiểu ở nguồn.
- [ ] Nếu dùng hash hoặc mã thay thế, đã đánh giá khả năng liên kết và nhận diện lại.
- [ ] Quyền truy cập, bản xuất, thời hạn lưu và các bản sao của log được quản lý.
- [ ] Test dùng dữ liệu giả để kiểm tra schema và các đường log quan trọng.
- [ ] Chế độ DEBUG hoặc thu thập tăng cường có kiểm soát phạm vi và thời gian bật.
- [ ] Khi phát hiện dữ liệu đã lộ, có quy trình đánh giá và xử lý cả những bản sao đã tồn tại.

## 18. Kết luận

**Giới hạn dữ liệu nhạy cảm trong log** là một phần của chất lượng bảo mật, không chỉ là một quy tắc định dạng. Log hữu ích phải cho biết **điều gì xảy ra, ở bước nào và thuộc loại lỗi nào**, nhưng không cần tự động chứa mọi dữ liệu mà ứng dụng đang xử lý.

Trong **CODE_QUALITY_FUNDAMENTALS**, một mã nguồn đáng tin cậy và dễ bảo trì nên có **hợp đồng logging rõ**, ưu tiên **allowlist dữ liệu**, tránh bí mật và nội dung request thô, kiểm soát **quyền truy cập và vòng đời log**, đồng thời kiểm thử những đường đi có rủi ro. Khả năng quan sát tốt và bảo vệ dữ liệu không đối lập nhau: một sự kiện chẩn đoán được thiết kế đúng có thể giúp điều tra nhanh hơn **với ít thông tin nhạy cảm hơn**.

