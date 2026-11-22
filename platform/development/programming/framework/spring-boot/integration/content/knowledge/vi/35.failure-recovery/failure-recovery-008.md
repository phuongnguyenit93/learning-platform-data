# Rate limit và điều tiết lưu lượng theo năng lực của hệ thống đích

## 1. Vì sao giới hạn lưu lượng là một phần của phục hồi khi lỗi?

Trong hệ thống **Spring Boot Integration**, dịch vụ có thể đồng thời gọi HTTP API đối tác, truy vấn cơ sở dữ liệu, gửi thông điệp vào RabbitMQ/Kafka, truy cập Redis và sử dụng các adapter của Spring Integration. Mỗi hệ thống đích có một năng lực hữu hạn: số yêu cầu mỗi giây, số kết nối đồng thời, tốc độ xử lý message, giới hạn quota theo phút hoặc giới hạn được chia sẻ giữa nhiều khách hàng.

Giả sử ứng dụng Order có bốn replica, mỗi replica gửi 35 yêu cầu thanh toán mỗi giây. Tổng cộng hệ thống phát **140 yêu cầu/giây**, trong khi đối tác chỉ chấp nhận 100 yêu cầu/giây cho cùng một tài khoản. Nếu không điều tiết, đối tác có thể trả HTTP `429 Too Many Requests` hoặc `503 Service Unavailable`, làm tăng timeout và kích hoạt nhiều lần retry. Các lần retry lại làm hệ thống đích quá tải hơn. Đây là **vòng khuếch đại lỗi (retry storm)**.

Rate limit giúp khống chế tốc độ **phát yêu cầu**; giới hạn đồng thời giúp khống chế số yêu cầu **đang chiếm tài nguyên**; hàng đợi và backpressure giúp ứng dụng phản ứng đúng khi lượng việc đến lớn hơn năng lực xử lý. Chúng bổ sung nhau trong chiến lược phục hồi, chứ không phải một cấu hình duy nhất thay thế được tất cả.

### Ba câu hỏi cần trả lời trước khi viết mã

1. **Đích có thể xử lý bao nhiêu?** Phân biệt quota theo tài khoản, tốc độ ổn định, mức burst cho phép, giới hạn kết nối và latency ở thời điểm tải cao.
2. **Nguồn nào tạo ra lưu lượng?** Một instance, nhiều replica, consumer broker, job chạy theo lịch, retry và các ứng dụng khác cùng dùng credentials đều phải tính vào tổng.
3. **Khi không còn khả năng nhận việc, ứng dụng cần làm gì?** Từ chối nhanh, giữ công việc trong queue bền vững, làm chậm producer, ưu tiên yêu cầu quan trọng hay trả trạng thái `PENDING`?

Ví dụ xuyên suốt bài này là **Order Service gọi Payment Provider qua HTTP**. Các nguyên tắc tương tự có thể áp dụng cho JDBC, Redis, SMTP và consumer message broker, nhưng cách thực thi phải phù hợp với khả năng của từng giao thức.

## 2. Phân biệt rate limiting, concurrency limiting và backpressure

| Cơ chế | Ràng buộc | Giải quyết | Điều không tự bảo đảm |
| --- | --- | --- | --- |
| **Rate limit** | Số lần thử trong một khoảng thời gian, chẳng hạn 20 request/giây. | Tránh vượt quota và làm phẳng tốc độ gửi. | Không giới hạn số request đang chờ nếu latency đột ngột tăng. |
| **Concurrency limit / bulkhead** | Số thao tác đang thực thi, chẳng hạn tối đa 8 HTTP call đồng thời. | Bảo vệ connection pool, thread và tài nguyên ở đích. | Không giới hạn request/giây nếu từng call cực nhanh. |
| **Queue có giới hạn** | Số việc đang chờ và thời gian chờ tối đa. | Hấp thụ burst ngắn; chuyển xử lý sang sau. | Không tăng năng lực đích; queue vô hạn chỉ chuyển quá tải thành độ trễ và bộ nhớ tiêu thụ. |
| **Backpressure** | Tín hiệu/điều khiển khiến nguồn phát giảm tốc hoặc ngừng phát thêm. | Tránh hệ thống tiếp tục nhận việc nhanh hơn khả năng xử lý. | Không thể giảm tốc mọi producer bên ngoài nếu hợp đồng không hỗ trợ. |
| **Load shedding** | Chủ động từ chối hoặc bỏ việc có ưu tiên thấp khi vượt ngưỡng. | Bảo vệ tác vụ quan trọng và độ ổn định. | Không phù hợp với yêu cầu bắt buộc phải xử lý nếu chưa lưu việc bền vững. |
| **Circuit breaker** | Dừng gọi tạm thời khi tỷ lệ lỗi/độ chậm vượt ngưỡng. | Ngăn tiếp tục gây áp lực lên đích đang hỏng. | Không thay thế quota hoặc rate limiter trong lúc đích khỏe. |
| **Retry có backoff** | Thử lại lỗi phù hợp theo khoảng cách có giới hạn. | Khắc phục lỗi tạm thời. | Có thể khuếch đại tải nếu không dùng cùng ngân sách lưu lượng và idempotency. |

Điểm quan trọng: **100 request/giây** và **100 request đồng thời** là hai đơn vị khác nhau. Nếu mỗi request chạy trung bình 2 giây, ngay cả tốc độ 50 request/giây cũng có thể tạo khoảng 100 request đang xử lý ở trạng thái ổn định.

## 3. Xác định ngân sách từ năng lực của hệ thống đích

### 3.1. Phân biệt cam kết của đối tác với kết quả đo

Giới hạn thực tế có thể đến từ hợp đồng API, gateway, đội vận hành đích hoặc load test. Đừng tự suy đoán rằng một HTTP endpoint trả lời nhanh ở môi trường thử nghiệm sẽ tiếp tục xử lý được lưu lượng lớn trong sản xuất. Cần làm rõ:

- Quota áp cho **API key, tài khoản, tenant, endpoint, phương thức hay toàn hệ thống**?
- Giới hạn là **cửa sổ một giây**, **một phút**, quota theo ngày hay **số request đồng thời**?
- Có cho phép burst không? Một burst 50 request trong 100 ms có bị từ chối dù trung bình một giây vẫn dưới 100 request?
- Các ứng dụng khác có chia sẻ cùng quota hay không? Có giới hạn chung xuyên khu vực dữ liệu hoặc tài khoản không?
- Yêu cầu tính theo **số attempt gửi đến đích**, bao gồm cả retry, hay chỉ tính request hoàn tất?

Với nhiều giới hạn cùng tồn tại, cần tuân thủ đồng thời các ràng buộc. Ví dụ đối tác giới hạn 120 request/giây và 4.000 request/phút: trung bình 120 request/giây trong một phút sẽ vi phạm giới hạn theo phút, nên phải tính cả hai ngân sách.

### 3.2. Ví dụ tính tốc độ và số call đồng thời

Giả sử đối tác công bố năng lực **100 request/giây** cho tài khoản đang dùng, không có client khác cùng chia quota. Hệ thống giữ **20% dự phòng** cho biến động và công việc ưu tiên, đặt mục tiêu phát tối đa **80 attempt/giây** trên tất cả replica.

Định luật Little cho hệ thống ở trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó `L` là số việc trung bình đang xử lý, `\lambda` là tốc độ hoàn tất trung bình và `W` là thời gian xử lý trung bình. Nếu latency bình quân ở đích là **200 ms**, với tốc độ **80 request/giây**:

\[
L \approx 80 \times 0.2 = 16 \text{ request đang xử lý}
\]

Con số 16 là **giá trị trung bình để định hướng**, không phải cấu hình concurrency an toàn tự động. Phải đo phân phối latency, p95/p99, khả năng burst, số connection thực tế và hành vi khi đích chậm. Ví dụ, nếu latency tăng lên 1 giây mà vẫn cố phát 80 request/giây, tải đang xử lý có thể tiến gần **80 request đồng thời**, gây áp lực lớn hơn nhiều.

Để lập kế hoạch, nên ghi riêng:

| Ngưỡng | Ví dụ | Vai trò |
| --- | --- | --- |
| Quota đối tác | 100 attempt/giây | Giới hạn không được vượt theo hợp đồng. |
| Ngân sách mục tiêu toàn hệ thống | 80 attempt/giây | Có vùng đệm khi có thay đổi lưu lượng. |
| Số replica gọi đích | 4 replica cố định trong ví dụ | Xác định phân bổ quota nếu dùng limiter cục bộ. |
| Ngân sách mỗi replica | 20 attempt/giây | Chỉ hợp lệ khi tất cả replica và client chia quota đã được tính. |
| Giới hạn request đồng thời/replica | Ví dụ 8 | Giá trị khởi tạo để kiểm tra bằng load test, không suy ra chỉ từ rate. |
| Thời gian chờ tối đa | Theo latency budget của endpoint | Ngăn request tích tụ vô hạn trước và trong lúc gọi đích. |

Nếu triển khai autoscaling từ 4 lên 8 replica mà giữ nguyên **20 request/giây mỗi replica**, tổng ngân sách tăng thành **160 request/giây**, vượt quota. Đây là lý do phải phân biệt rate limit **cục bộ theo instance** và **toàn cụm theo shared identity**.

## 4. Các thuật toán điều tiết lưu lượng

### 4.1. Fixed window và sliding window

**Fixed window** đếm số request trong các cửa sổ liên tiếp (ví dụ mỗi giây). Cơ chế dễ triển khai nhưng có thể cho phép một burst lớn sát ranh giới hai cửa sổ: 20 request vào cuối giây trước và 20 request ngay đầu giây sau.

**Sliding window** đánh giá một khoảng nhìn ngược từ thời điểm hiện tại, thường làm giảm hiệu ứng ranh giới nhưng cần cấu trúc dữ liệu hoặc phép xấp xỉ phức tạp hơn. Cần làm rõ cách thư viện tính toán và mức chính xác cần thiết.

### 4.2. Token bucket

**Token bucket** có dung lượng `B` token và tốc độ nạp `r` token/giây. Mỗi request tốn một hoặc nhiều token:

- Nếu còn token, request có thể đi ngay.
- Nếu hết token, hệ thống từ chối, chờ có giới hạn hoặc đưa việc vào queue.
- Sau thời gian nhàn rỗi, bucket có thể tích lũy token tới mức `B`, cho phép burst ngắn.

Ví dụ `r = 20` token/giây, `B = 10` token: đích có thể nhận tối đa 10 request gần như cùng lúc khi bucket đầy, rồi lưu lượng tiếp theo phải tuân theo tốc độ nạp trung bình. Nếu đích cấm burst, dung lượng bucket phải nhỏ hơn hoặc cần một cơ chế làm đều thời điểm gửi.

### 4.3. Leaky bucket và điều phối có nhịp

**Leaky bucket/shaping** phát việc với nhịp tương đối đều (ví dụ một request mỗi 50 ms), hữu ích khi đích nhạy với burst. Nếu nguồn đến nhanh hơn nhịp phát trong thời gian dài, queue sẽ tăng; cần giới hạn queue, thời gian chờ và hành vi khi tràn.

| Thuật toán | Đặc tính | Khi thường chọn |
| --- | --- | --- |
| Fixed window | Đơn giản, có burst tại ranh giới cửa sổ. | Giới hạn quản trị dễ triển khai, quota xấp xỉ. |
| Sliding window | Công bằng hơn theo khoảng thời gian nhìn ngược. | Quota cần kiểm soát chặt theo cửa sổ lăn. |
| Token bucket | Cho phép burst đã định nghĩa, giữ tốc độ trung bình. | API đích có mức burst được công bố. |
| Leaky bucket / paced queue | Làm phẳng nhịp gửi. | Đích dễ quá tải vì nhiều request đến cùng lúc. |

Đừng gọi mọi `RateLimiter` là token bucket. Chẳng hạn một cấu hình cấp `N` permission trong mỗi chu kỳ làm mới có thể thể hiện **cửa sổ cố định**, không tạo nhịp gửi đều như leaky bucket.

## 5. Đặt giới hạn ở đâu trong luồng tích hợp?

~~~mermaid
flowchart LR
    A["HTTP / scheduler / broker"] --> B["Kiểm tra hợp đồng và ưu tiên"]
    B --> C{"Có khả năng nhận việc?"}
    C -->|Không| D["429/503 hoặc queue bền vững"]
    C -->|Có| E["Outbound rate limiter"]
    E --> F["Concurrency bulkhead"]
    F --> G["HTTP client / adapter"]
    G --> H[("Hệ thống đích")]
    H --> I["Kết quả / Retry-After"]
    I --> J["Chính sách retry và cập nhật trạng thái"]
~~~

Có ít nhất ba vị trí kiểm soát:

1. **Inbound API**: giới hạn theo người dùng/tenant, API key hoặc endpoint để bảo vệ chính ứng dụng. Khi khách hàng vượt quota đã công bố, thường trả HTTP `429` và thông tin thử lại thích hợp.
2. **Outbound connector**: giới hạn theo năng lực **hệ thống đích**, bao gồm cả lưu lượng do job, broker consumer và HTTP request tạo ra. Đây là tuyến phòng vệ trực tiếp cho đối tác.
3. **Broker consumer / worker**: giới hạn số message đang xử lý và nhịp phát outbound. Có thể tạm ngừng/pause consumer, giảm concurrency hoặc định tuyến sang queue có giới hạn, tùy broker.

Chỉ giới hạn request ở API gateway đầu vào là chưa đủ nếu ứng dụng cũng phát traffic từ scheduled job, retry và message broker. Ngược lại, chỉ giới hạn outbound mà tiếp tục nhận vô hạn request sẽ khiến queue, bộ nhớ và thời gian phản hồi của chính ứng dụng bị quá tải.

## 6. Ví dụ Spring Boot: RateLimiter kết hợp giới hạn concurrent HTTP call

Ví dụ sau dùng **Spring Boot 3.2+, Java 17+, `RestClient` và Resilience4j RateLimiter 2.x**. Phần quan trọng là **mọi attempt gửi đến Payment API phải đi qua cùng một lớp connector**, kể cả attempt do retry tạo ra. Khi triển khai cần quản lý version dependency Resilience4j tương thích với nền tảng; code sau minh họa API lõi `resilience4j-ratelimiter`.

Dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-ratelimiter</artifactId>
        <version>2.2.0</version>
    </dependency>
</dependencies>
~~~

Ví dụ `application.yml`:

~~~yaml
app:
  payment:
    base-url: https://payment.example.net
    max-attempts-per-second: 20
    max-in-flight: 8
~~~

Đây là **ngân sách cho một instance** trong minh họa bốn replica. `payment.example.net` chỉ là địa chỉ giả định. Không dùng cách phân bổ 20/replica nếu số replica hoặc client cùng chia quota thay đổi mà không có bộ điều phối quota chung.

### 6.1. Khai báo các bean bảo vệ

~~~java
package com.example.integration.payment;

import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;
import java.time.Duration;
import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PaymentTrafficConfiguration {

    @Bean("paymentOutboundLimiter")
    RateLimiter paymentOutboundLimiter(
            @Value("${app.payment.max-attempts-per-second}") int attempts) {
        return RateLimiter.of(
                "payment-outbound",
                RateLimiterConfig.custom()
                        .limitForPeriod(attempts)
                        .limitRefreshPeriod(Duration.ofSeconds(1))
                        .timeoutDuration(Duration.ZERO)
                        .build());
    }

    @Bean("paymentInFlight")
    Semaphore paymentInFlight(
            @Value("${app.payment.max-in-flight}") int maxInFlight) {
        return new Semaphore(maxInFlight, true);
    }

    @Bean("paymentRestClient")
    RestClient paymentRestClient(
            RestClient.Builder builder,
            @Value("${app.payment.base-url}") String baseUrl) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1_000);
        factory.setReadTimeout(2_000);
        return builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
~~~

Giải thích:

- `limitForPeriod` và `limitRefreshPeriod` đặt tối đa 20 permission trong chu kỳ một giây. Đây là cách làm theo chu kỳ làm mới, **có thể tạo burst quanh ranh giới chu kỳ**; không thay thế bộ định nhịp đều nếu đối tác cấm burst.
- `timeoutDuration(Duration.ZERO)` yêu cầu limiter **từ chối ngay** khi hết permission; không chặn thread HTTP để đợi lượt. Nếu nghiệp vụ cho phép chờ, phải đưa thời gian chờ vào latency budget và giới hạn queue/concurrency.
- `Semaphore` là giới hạn đồng thời **nội bộ process**; `tryAcquire()` cần đi kèm `release()` trong `finally`.
- Timeout kết nối và đọc không thay cho tổng deadline end-to-end khi gọi qua nhiều hop. Cần xác nhận timeout thực tế với HTTP client đang dùng.

### 6.2. Connector áp dụng cả hai giới hạn

~~~java
package com.example.integration.payment;

import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;
import java.math.BigDecimal;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record PaymentCommand(String operationId, BigDecimal amount) {}
record PaymentReply(String transactionId, String status) {}

class DownstreamBusyException extends RuntimeException {
    DownstreamBusyException(String message) {
        super(message);
    }

    DownstreamBusyException(String message, Throwable cause) {
        super(message, cause);
    }
}

@Service
public class PaymentConnector {
    private final RestClient client;
    private final RateLimiter limiter;
    private final Semaphore inFlight;

    public PaymentConnector(
            @Qualifier("paymentRestClient") RestClient client,
            @Qualifier("paymentOutboundLimiter") RateLimiter limiter,
            @Qualifier("paymentInFlight") Semaphore inFlight) {
        this.client = client;
        this.limiter = limiter;
        this.inFlight = inFlight;
    }

    public PaymentReply authorize(PaymentCommand command) {
        Supplier<PaymentReply> remoteCall = () -> {
            if (!inFlight.tryAcquire()) {
                throw new DownstreamBusyException(
                        "Payment concurrent-call capacity exhausted");
            }
            try {
                return client.post()
                        .uri("/authorizations")
                        .header("Idempotency-Key", command.operationId())
                        .body(command)
                        .retrieve()
                        .body(PaymentReply.class);
            } finally {
                inFlight.release();
            }
        };

        try {
            PaymentReply reply =
                    RateLimiter.decorateSupplier(limiter, remoteCall).get();
            if (reply == null) {
                throw new IllegalStateException("Empty payment response");
            }
            return reply;
        } catch (RequestNotPermitted ex) {
            throw new DownstreamBusyException(
                    "Payment outbound rate budget exhausted", ex);
        }
    }
}
~~~

Trong ví dụ, **mỗi lần gọi `authorize` tiêu thụ tối đa một permission** trước khi thử lấy permit semaphore; nếu concurrency đã đầy, permission rate limit có thể đã được tiêu thụ mà chưa có request HTTP. Đây là lựa chọn **bảo thủ, an toàn với quota đích**, nhưng làm giảm throughput ở lúc tải cao. Có thể phối hợp thứ tự cấp permit khác nếu đã kiểm tra rõ quy tắc hoàn trả và việc chờ.

`RestClient.retrieve()` thường ném ngoại lệ đối với phản hồi 4xx/5xx; chính sách nghiệp vụ phía trên cần phân loại lỗi `429`, `503`, timeout và lỗi không thể retry. `Idempotency-Key` chỉ chống trùng khi **Payment Provider thực sự hỗ trợ và lưu kết quả theo khóa đó**; không được giả định chỉ cần gửi header là đích sẽ xử lý đúng một lần. Với thanh toán, cùng một thao tác phải giữ **cùng khóa** qua mọi lần retry và đối soát.

> **Giới hạn của ví dụ:** `RateLimiter` và `Semaphore` ở đây chỉ tồn tại trong **một JVM**. Nếu có nhiều pod/replica, quota toàn hệ thống phải được phân bổ hoặc kiểm soát ở một điểm chung. Ví dụ cũng không tự cung cấp queue bền vững, cơ chế retry hay circuit breaker; chúng là các quyết định bổ sung theo yêu cầu nghiệp vụ.

## 7. Phản ứng đúng với HTTP 429 và Retry-After

Khi HTTP đích trả `429 Too Many Requests`, không nên lập tức gửi lại trong vòng lặp. Cần xem **`Retry-After`** nếu có, kết hợp với quota nội bộ, deadline của request và giới hạn tổng số attempt.

`Retry-After` có thể có hai dạng theo HTTP:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 12
~~~

Giá trị `12` nghĩa là thử lại sau **12 giây**. Hoặc:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: Sat, 21 Nov 2026 10:00:00 GMT
~~~

Trong dạng thứ hai, giá trị là **HTTP-date**. Không diễn giải cả hai dạng bằng cách ép chuỗi thành một số nguyên; phải parse đúng định dạng, xử lý clock skew, thời điểm đã qua, giá trị không hợp lệ và đặt giới hạn chờ tối đa.

### Phân loại kết quả và cách ứng xử

| Tín hiệu | Diễn giải | Hành động phù hợp |
| --- | --- | --- |
| `429` có `Retry-After` | Quota hoặc chính sách throttling ở đích. | Hoãn attempt đến sau thời điểm được đề nghị nếu còn deadline; chia sẻ tín hiệu giảm tốc cho các worker cùng gọi đích. |
| `429` không có `Retry-After` | Đã bị giới hạn nhưng đích không đưa thời gian phục hồi. | Backoff có jitter, giảm ngân sách phát; tránh retry ngay. |
| `503` hoặc timeout | Đích tạm không phục vụ/không rõ kết quả. | Giới hạn retry, circuit breaker, tra cứu trạng thái nếu side effect có thể đã xảy ra. |
| `400` do dữ liệu sai | Lỗi hợp đồng/validation. | Sửa dữ liệu, trả lỗi rõ ràng; retry y nguyên thường không có ích. |
| `401`/`403` | Sai cấu hình xác thực/ủy quyền hoặc quyền. | Kiểm tra credential/quyền, không tăng tải bằng retry liên tục. |
| `409` | Trạng thái xung đột hoặc kết quả nghiệp vụ tùy API. | Diễn giải theo hợp đồng của đối tác; không mặc định là lỗi tạm thời. |

Trong luồng **HTTP request/response**, nếu thời gian phải chờ vượt deadline của người dùng, tốt hơn là trả trạng thái `PENDING` khi đã lưu việc bền vững, hoặc trả lỗi phù hợp để bên gọi chủ động thử lại. Nếu ứng dụng **chưa** lưu công việc bền vững, không được trả `202 Accepted` rồi âm thầm làm mất yêu cầu khi process chết.

## 8. Retry budget: không cho retry phá quota

Một sai lầm là giới hạn **request gốc** ở 80 request/giây, sau đó cho mỗi request retry tối đa ba lần **bên trong HTTP client** mà không đi qua limiter. Khi cả ba attempt đều được phát, tải ở đích có thể tăng đến **240 attempt/giây**. Vì vậy:

1. **Mọi lần retry thực sự gửi tới đích đều phải xin permission từ outbound limiter.**
2. Quy định số attempt tối đa, thời gian backoff có jitter và deadline end-to-end.
3. Dành một **retry budget** riêng nếu cần, ví dụ chỉ cho một tỷ lệ nhỏ tổng outbound rate được dùng để retry khi có lỗi.
4. Không retry vô hạn khi broker giao lại cùng message hoặc khi một scheduled job chạy lại.
5. Áp dụng idempotency/reconciliation cho các thao tác có side effect.

Ví dụ cấu trúc điều phối:

~~~text
Đọc operationId ổn định
  -> Kiểm tra deadline và retry budget
  -> Xin permission rate limiter cho attempt hiện tại
  -> Xin chỗ xử lý đồng thời
  -> Gọi HTTP với timeout
  -> Nếu thành công: ghi trạng thái xác nhận
  -> Nếu 429/503: tính backoff + Retry-After + jitter rồi lập lịch lại
  -> Nếu kết quả không rõ: tra cứu trạng thái theo operationId
  -> Nếu hết hạn/số lần thử: chuyển trạng thái cần đối soát
~~~

Trong kiến trúc nhiều lớp, cần tránh **retry chồng tầng**: HTTP client retry 3 lần, service retry 3 lần và queue consumer redelivery 3 lần có thể dẫn tới tới **27 attempt** cho một message. Chọn nơi chịu trách nhiệm retry chính và làm rõ cách các tầng chia sẻ ngân sách.

**Exponential backoff** không phải là lý do để vượt `Retry-After`. Nếu bên đích yêu cầu chờ 12 giây, scheduler không nên thử lại sau 2 giây chỉ vì backoff nội bộ ngắn hơn. Với nhiều worker, thêm jitter ngẫu nhiên có giới hạn để giảm việc đồng loạt thức dậy và tạo burst.

## 9. Nhiều replica, nhiều tenant và quota toàn cụm

Rate limiter cục bộ thường chỉ biết traffic của **một process**. Khi quota được tính theo một API key dùng chung, ba lựa chọn phổ biến là:

| Lựa chọn | Cách hoạt động | Điểm cần kiểm soát |
| --- | --- | --- |
| **Phân bổ cố định theo replica** | Chia tổng quota thành hạn mức cho mỗi replica. | Khó khi autoscaling, rolling deploy, số replica thực và traffic không đều; phải giữ phần dự phòng. |
| **Limiter phân tán** | Mọi replica xin token/permission qua Redis hoặc dịch vụ quota tập trung. | Cần thao tác atomic, chính sách TTL/clock, latency, xử lý Redis unavailable và isolation theo key. |
| **Gateway/dispatcher tập trung** | Mọi outbound request đi qua một tầng có khả năng xếp hàng và điều tiết. | Tầng điều phối trở thành dependency cần HA, backpressure và monitoring. |

Ví dụ quota **80 request/giây toàn cụm** được chia cho 4 replica là 20 request/giây mỗi replica. Khi một replica nhàn rỗi nhưng replica khác quá tải, phân bổ cố định có thể lãng phí quota. Limiter phân tán cho phép chia sẻ năng lực linh hoạt hơn, đổi lại có chi phí mạng và một dependency vận hành mới.

Nếu dùng Redis, việc “GET số đếm rồi SET số đếm mới” qua hai lệnh riêng lẻ **không bảo đảm atomic** dưới tải đồng thời. Dùng primitive atomic phù hợp (Lua script, transaction thích hợp hoặc thư viện có hỗ trợ backend phân tán), và định nghĩa hành vi khi mất kết nối tới hệ thống quota:

- **Fail closed**: tạm từ chối/đưa vào queue để không vượt quota đích, phù hợp khi vi phạm quota có hậu quả lớn.
- **Fail open có giới hạn**: tạm cho phép lưu lượng hạn chế theo mức dự phòng, phù hợp khi ưu tiên availability và đối tác cho phép.

Phải ghi rõ chính sách; không để lỗi Redis tự động biến thành “mọi request đều được phép đi”.

### 9.1. Phân bổ công bằng theo tenant và độ ưu tiên

Một tenant có đột biến tải không nên tự ý chiếm toàn bộ ngân sách của các tenant khác. Có thể dùng limiter hai tầng:

~~~mermaid
flowchart TD
    A["Outbound operation"] --> B["Limiter theo tenant"]
    B --> C["Limiter toàn cục theo API key"]
    C --> D["Concurrency limit theo đích"]
    D --> E["Payment API"]
    B --> F["Từ chối/chờ có kiểm soát"]
    C --> F
    D --> F
~~~

Những yêu cầu có độ ưu tiên khác nhau (thanh toán đang diễn ra, gửi email quảng bá, đồng bộ báo cáo) có thể dùng queue/worker pool riêng hoặc phần quota được dành trước, tránh để tác vụ ít quan trọng chiếm hết capacity. Phải làm rõ khi có request ưu tiên cao vượt ngưỡng thì xử lý ra sao, tránh vô tình phá giới hạn chung của đích.

## 10. Queue, broker và Spring Integration: điều tiết từ nguồn phát

Khi công việc **có thể xử lý sau**, queue bền vững là công cụ hấp thụ burst tốt hơn việc chặn hàng nghìn HTTP thread. Luồng có thể là:

~~~mermaid
flowchart LR
    A["Order API"] --> B[("Database + Outbox")]
    B --> C["Relay"]
    C --> D[("Broker")]
    D --> E["Consumer có concurrency giới hạn"]
    E --> F["Outbound rate + bulkhead"]
    F --> G["Payment / Notification API"]
    E --> H["Retry có delay / DLQ"]
~~~

Trong mô hình này:

1. Ứng dụng **ghi công việc bền vững** và phản hồi `202 Accepted` kèm mã theo dõi nếu hợp đồng cho phép.
2. Consumer xử lý tối đa số message đồng thời đã định, và mỗi attempt outbound phải đi qua rate limiter.
3. Khi vượt quota, message có thể được retry sau hoặc tiếp tục chờ theo cơ chế broker. **Tránh nack/requeue liên tục ngay lập tức**, vì sẽ tạo vòng lặp CPU, log và network.
4. Phải có độ tuổi message tối đa, số lần thử tối đa và DLQ/quarantine với quy trình xử lý, không để queue tích tụ vô hạn.

Spring Integration hỗ trợ luồng dạng `IntegrationFlow`, inbound/outbound adapter, `MessageChannel`, `Gateway` và error flow. Những building block này thuận tiện để đặt limiter ở **đúng adapter gọi hệ thống đích**, nhưng không tự tạo một shared distributed quota. Chẳng hạn:

~~~mermaid
flowchart LR
    I["Inbound AMQP/Kafka adapter"] --> C["MessageChannel"]
    C --> V["Filter/validate contract"]
    V --> L["Rate-limited Service Activator"]
    L --> O["Outbound HTTP gateway"]
    L --> X["Retry/Error policy"]
~~~

Nếu dùng `DirectChannel`, các bước xử lý chạy đồng bộ trong thread gửi; nếu dùng `ExecutorChannel`, một ranh giới thread mới được tạo; nếu dùng `QueueChannel` mặc định, message có thể chỉ nằm trong bộ nhớ. **Không coi ExecutorChannel hoặc QueueChannel in-memory là queue bền vững qua lần restart**. Với broker, chọn đúng prefetch, concurrency, acknowledgment, retry/DLQ và cách gắn transaction/offset.

### 10.1. Đo tính ổn định của backlog

Khi tốc độ message vào là `\lambda` và tốc độ xử lý bền vững là `\mu`:

- Nếu `\lambda < \mu` trong dài hạn, queue có cơ hội rút dần.
- Nếu `\lambda > \mu` kéo dài, backlog sẽ tiếp tục tăng, bất kể queue lớn đến đâu.

Ví dụ incoming **150 job/giây**, đích chỉ có thể nhận **80 attempt/giây**: backlog tăng ít nhất khoảng **70 job/giây** (chưa tính retry và job có nhiều attempt). Sau 10 phút, lượng việc chờ có thể tăng thêm khoảng **42.000 job**. Không có cấu hình queue nào biến năng lực 80 thành 150; cần giảm intake, điều chỉnh thỏa thuận quota, giảm số cuộc gọi mỗi nghiệp vụ hoặc tăng năng lực đích.

## 11. Kết hợp rate limit với bulkhead, circuit breaker và timeout

Để bảo vệ một đích đang chậm, dùng cơ chế theo từng mục tiêu:

| Cơ chế | Quyết định chính | Ví dụ |
| --- | --- | --- |
| Rate limiter | **Có được tạo attempt mới lúc này không?** | Tối đa 20 attempt/giây từ một instance. |
| Semaphore bulkhead | **Đang có bao nhiêu attempt chiếm tài nguyên?** | Tối đa 8 call đồng thời tới Payment. |
| Timeout/deadline | **Mỗi attempt và toàn operation có thể chờ bao lâu?** | HTTP read timeout 2 giây; tổng deadline theo hợp đồng. |
| Circuit breaker | **Đích có dấu hiệu lỗi đủ lớn để ngừng gọi tạm thời không?** | Mở circuit khi tỷ lệ lỗi trong cửa sổ đo vượt ngưỡng đã kiểm thử. |
| Retry budget | **Có được phép thử lại hay không?** | Chỉ retry lỗi tạm thời, số lần và rate giới hạn. |
| Queue/buffer | **Nếu chưa gọi được ngay thì việc được lưu ở đâu?** | Persistent broker hoặc job table có hạn xử lý. |

Thứ tự thực thi nên được thiết kế có chủ đích: kiểm tra dữ liệu không hợp lệ trước, từ chối nhanh khi deadline đã hết hoặc circuit đã mở, xin permission để gọi đích, rồi giữ concurrency slot trong thời gian I/O. Cách xếp decorator phải bảo đảm **mỗi attempt, kể cả retry, đều được tính quota**; nếu áp limiter bên ngoài toàn bộ khối retry, các attempt phía trong có thể vượt quota.

Không giữ một transaction JDBC/JPA mở chỉ để chờ rate limiter hoặc `Retry-After`: điều đó kéo dài lock, chiếm connection và tăng khả năng lỗi dây chuyền. Với quy trình dài, lưu trạng thái nghiệp vụ và lập lịch xử lý sau bằng transaction ngắn, dùng outbox/idempotency nếu cần.

## 12. Thiết kế hợp đồng lỗi và khả năng phục hồi

### 12.1. Phản hồi với client của chính ứng dụng

Khi API của mình chủ động áp quota lên người gọi, có thể trả `429` kèm `Retry-After` nếu biết thời gian phù hợp. Khi chính hệ thống đang quá tải và không thể nhận việc, `503` hoặc phản hồi nghiệp vụ tương ứng có thể hợp lý hơn. Chọn status theo **ngữ nghĩa hợp đồng**, không rập khuôn chuyển mọi lỗi của Payment Provider thành cùng một mã HTTP.

Nếu ứng dụng nhận xử lý bất đồng bộ, trả `202 Accepted` **chỉ sau khi đã lưu được công việc** cùng mã tra cứu và quy tắc hết hạn rõ ràng. Kết quả `PENDING` không được diễn giải thành “đã thanh toán”.

### 12.2. Không đánh đồng timeout với thất bại nghiệp vụ

Với một thao tác có side effect như thu tiền hoặc tạo giao dịch:

~~~mermaid
sequenceDiagram
    participant Order as Order Service
    participant Provider as Payment Provider
    Order->>Provider: POST /authorizations, operationId=X
    Provider->>Provider: Ghi nhận thanh toán X
    Provider--xOrder: Phản hồi bị mất / timeout
    Note over Order: Không biết kết quả thực tế
    Order->>Provider: Tra cứu trạng thái X
    Provider-->>Order: X đã được ghi nhận
    Note over Order: Không thực hiện lại một payment mới
~~~

Khi gặp timeout, việc **không biết kết quả** là một trạng thái có ý nghĩa. API cần hỗ trợ `operationId`/idempotency key, tra cứu giao dịch và đối soát. Nếu đối tác không hỗ trợ, cần một chính sách thủ công hoặc workflow xác minh riêng trước khi retry một thao tác có thể trùng.

### 12.3. Tách loại lỗi trước khi retry

Phân loại `validation failure`, `quota exceeded`, `temporary unavailable`, `business rejection` và `unknown outcome`. Mỗi nhóm có trạng thái, retry policy và cách hiển thị cho người dùng khác nhau. Đưa lỗi bất khả phục hồi vào DLQ với nguyên nhân đủ chẩn đoán, nhưng không ghi secret, token, dữ liệu thẻ hoặc thông tin cá nhân nhạy cảm vào log và message không cần thiết.

## 13. Quan sát để biết limiter có thực sự bảo vệ hệ thống đích

Các chỉ số nên có nhãn `destination`, `operation`, môi trường, tenant/nhóm quota ở mức cardinality có kiểm soát:

| Nhóm chỉ số | Điều cần quan sát |
| --- | --- |
| Rate limit | Permission được cấp/từ chối, tỷ lệ phải chờ, quota hiệu dụng theo instance và toàn cụm. |
| HTTP client | Tổng attempt/giây, latency p50/p95/p99, lỗi 429/503, timeout, kết quả không rõ. |
| Concurrency | Số call đang chạy, permit còn lại, bulkhead rejection và connection pool saturation. |
| Retry | Tỷ lệ retry, số attempt trên mỗi operation, backoff, số lần vượt retry budget. |
| Queue/broker | Queue depth, consumer lag, tuổi message lớn nhất, retry backlog, DLQ và throughput. |
| Nghiệp vụ | Số payment `PENDING` quá hạn, số transaction cần đối soát, độ trễ đến kết quả cuối. |

**Chỉ nhìn số lượng 429 giảm chưa đủ**: có thể hệ thống giảm 429 vì từ chối quá nhiều việc ở lớp nội bộ. Cần đo cả tỷ lệ yêu cầu hoàn tất, thời gian chờ và số việc bị bỏ/không thể xử lý. Khi thay đổi quota hoặc scale replica, dashboard cần thể hiện tổng **actual outbound attempts** theo cùng API key.

Đặt cảnh báo theo điều kiện có hành động cụ thể, ví dụ “tuổi message đang chờ vượt SLO” hoặc “tỷ lệ 429 tăng liên tục dù outbound attempts nằm dưới ngân sách kỳ vọng”. Kết hợp trace/correlation ID để truy từ request ban đầu đến retry, outbox event và lệnh gọi đích, nhưng giữ operation ID ổn định qua các attempt.

## 14. Kiểm thử tải và lỗi trước khi triển khai

| Ca kiểm thử | Kết quả mong muốn |
| --- | --- |
| Một replica nhận burst 100 request trong thời gian rất ngắn | Attempt ra đích tuân thủ đặc tính thuật toán đã chọn; phần vượt được từ chối hoặc đưa vào queue theo chính sách. |
| Bốn replica cùng gọi Payment | Tổng attempt/giây nằm trong quota dùng chung, bao gồm retry và những client chia sẻ credentials. |
| Scale từ 4 lên 8 replica | Quota tổng không tự tăng gấp đôi; limiter phân tán hoặc bộ phân bổ cập nhật đúng. |
| Đích chậm từ 200 ms lên 2 giây | In-flight call vẫn nằm trong giới hạn; thread/connection pool và queue không tăng vô hạn. |
| Đích trả 429 kèm `Retry-After: 12` | Worker không retry quá sớm, vẫn kiểm tra deadline và retry budget. |
| Đích trả 429 hàng loạt | Không hình thành retry storm; rate phát thực tế giảm theo chính sách. |
| Đích trả lỗi validation 400 | Không retry cùng dữ liệu sai; lỗi được phân loại rõ. |
| Timeout sau khi đích đã commit | Retry cùng idempotency key hoặc tra cứu kết quả; không tạo giao dịch mới trùng lặp. |
| Redis/quota service không khả dụng | Áp chính xác chính sách fail closed hoặc fail open có giới hạn đã thỏa thuận. |
| Queue đầy và consumer bị dừng | Có backpressure/load shedding, DLQ/expiry, không làm JVM tràn bộ nhớ. |
| Process restart khi còn việc đang chờ | Công việc đã được xác nhận lưu bền vững vẫn được phục hồi và xử lý tiếp. |

Load test cần phối hợp với **năng lực thực tế của đích** và môi trường được cho phép; không tạo tải cực lớn lên API production đối tác chỉ để đo giới hạn. Có thể dùng mock HTTP server có hành vi 429/503/timeout, sau đó chạy thử có kiểm soát với sandbox của nhà cung cấp. Với broker, dùng môi trường tích hợp thực để xác minh ack, redelivery, retry và DLQ.

Một bài kiểm thử quan trọng là **đếm request mà server mock thực sự nhận được**, thay vì chỉ đếm lời gọi vào service. Nếu một retry decorator nằm bên trong rate limiter, test có thể phát hiện số HTTP attempt vượt mức dù số business operation vẫn trong giới hạn.

## 15. Checklist lựa chọn cơ chế điều tiết

Trước khi cấu hình vào ứng dụng Spring Boot, xác nhận:

- [ ] Đã ghi rõ giới hạn **của đích** theo từng API key, endpoint, window, burst và concurrency; có dự phòng và người sở hữu quota.
- [ ] Mọi nguồn phát và mọi retry attempt đều đi qua chính sách outbound phù hợp; không chỉ giới hạn ở ingress.
- [ ] Đã phân biệt limiter mỗi JVM với limiter toàn cụm, xem xét autoscaling và client chia sẻ quota.
- [ ] Có giới hạn in-flight, timeout và queue có giới hạn; biết rõ khi nào trả lỗi và khi nào lưu việc bền vững.
- [ ] Có hành vi rõ với HTTP 429, `Retry-After`, 503, timeout, circuit breaker và retry budget.
- [ ] Các thao tác có side effect có idempotency key, khả năng tra cứu trạng thái và cơ chế đối soát.
- [ ] Không giữ transaction database trong lúc chờ lâu; các bước bất đồng bộ có trạng thái nghiệp vụ chính xác.
- [ ] Có metrics, alert, kiểm thử đa replica, thử lỗi có chủ đích và đánh giá khả năng phục hồi sau restart.

**Rate limit theo năng lực hệ thống đích** chỉ hiệu quả khi được đặt trong thiết kế điều phối lưu lượng toàn diện. Nó giúp ứng dụng Spring Boot tôn trọng quota, giảm nguy cơ quá tải và tạo khoảng trống để các cơ chế retry, circuit breaker, hàng đợi và phục hồi hoạt động. Đồng thời, hợp đồng dữ liệu, transaction, idempotency, giám sát và kiểm thử mới quyết định các bước tích hợp có giữ đúng kết quả nghiệp vụ hay không khi hệ thống đích chậm, từ chối hoặc tạm ngừng phục vụ.
