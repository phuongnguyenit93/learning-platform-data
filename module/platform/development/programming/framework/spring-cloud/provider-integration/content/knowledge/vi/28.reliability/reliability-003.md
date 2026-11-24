# Exponential backoff, jitter và xử lý giới hạn tốc độ

Khi nhiều instance Spring Boot cùng gọi Azure Blob Storage, Service Bus hoặc một API đối tác, một đợt lỗi ngắn có thể khiến mọi instance retry gần như đồng thời. Lượng request tăng đúng lúc dịch vụ đang quá tải, tạo ra **retry storm** và kéo dài sự cố. Ngược lại, nếu client retry quá ít hoặc không tôn trọng giới hạn tốc độ, ứng dụng có thể bỏ lỡ cơ hội phục hồi hoặc liên tục nhận HTTP 429.

**Exponential backoff** điều chỉnh khoảng chờ tăng dần giữa các lần thử; **jitter** phân tán thời điểm retry giữa các client; **rate limiting** kiểm soát tốc độ request được phép đi qua. Ba cơ chế phối hợp với retry policy, deadline, circuit breaker và concurrency limit để bảo vệ cả ứng dụng lẫn dịch vụ phụ thuộc.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao retry ngay lập tức và retry đồng bộ có thể khuếch đại tải khi dịch vụ lỗi.
2. Tính exponential backoff, phân biệt full jitter, equal jitter và decorrelated jitter.
3. Đọc và xử lý **Retry-After** theo cả dạng số giây và HTTP-date.
4. Phân biệt rate limit, quota, concurrency limit và connection pool.
5. Chọn thuật toán fixed window, sliding window, token bucket hoặc leaky bucket theo nghiệp vụ.
6. Cấu hình retry/rate limit ở Azure SDK, Resilience4j và tầng API/application mà không nhân chính sách ngoài ý muốn.
7. Xử lý rate limit phân tán giữa nhiều replica Spring Boot.
8. Kiểm thử backoff, jitter, 429, retry budget, burst và fairness bằng clock giả hoặc test server.
9. Theo dõi throttling, retry amplification, quota consumption và latency trong môi trường đa cloud.

## 2. Vì sao cần backoff và jitter?

Giả sử một dịch vụ phụ thuộc bắt đầu trả 503 trong 10 giây. Một hệ thống có 100 instance Spring Boot, mỗi instance đang xử lý 50 request. Nếu tất cả request retry ngay sau 100 ms, dịch vụ sẽ nhận một đợt tải mới gần như cùng lúc, dù nó chưa kịp phục hồi.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Client C
    participant S as Managed service
    par Retry đồng thời
        A->>S: Retry tại 1.0 s
        B->>S: Retry tại 1.0 s
        C->>S: Retry tại 1.0 s
    end
    S-->>A: 429 / 503
    S-->>B: 429 / 503
    S-->>C: 429 / 503
    Note over A,C: Các client lại cùng chờ và retry
~~~

**Backoff** tăng khoảng cách giữa các lần thử, giúp giảm tốc độ request khi sự cố kéo dài. Nhưng nếu mọi client dùng cùng một lịch cố định, chúng vẫn có thể retry đồng bộ. **Jitter** thêm ngẫu nhiên vào khoảng chờ để phân tán request.

~~~mermaid
flowchart TD
    A[Lỗi transient / throttling] --> B[Phân loại lỗi]
    B --> C[Đọc Retry-After nếu có]
    C --> D[Tính backoff và jitter]
    D --> E[Kiểm tra deadline / retry budget]
    E -->|Còn ngân sách| F[Chờ không giữ thread nếu có thể]
    E -->|Hết ngân sách| G[Trả lỗi / lên lịch xử lý sau]
    F --> H[Thử lại có giới hạn]
~~~

Backoff/jitter không làm dịch vụ khỏe lên và không giải quyết lỗi cấu hình, quyền hoặc request không hợp lệ. Chúng chỉ điều tiết **thời điểm và tần suất thử lại** khi retry có ý nghĩa.

## 3. Exponential backoff

Exponential backoff tăng thời gian chờ theo cấp số nhân. Một dạng cơ bản:

\[
d_k = \min(d_{max}, d_0 \times m^{k-1})
\]

Trong đó:

- (d_k): thời gian chờ trước lần thử thứ (k).
- (d_0): khoảng chờ ban đầu.
- (m): hệ số tăng, thường lớn hơn 1.
- (d_{max}): giới hạn khoảng chờ tối đa.

Ví dụ (d_0 = 100) ms, (m = 2), (d_{max} = 2.000) ms:

| Lần chờ | Khoảng chờ cơ sở |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |
| 6 trở đi | 2.000 ms |

Nếu không có jitter, các client dùng cùng cấu hình vẫn có thể tạo ra các đợt request đồng bộ sau 100, 200, 400 ms... Backoff đơn thuần giảm tần suất, nhưng chưa phân tán thời điểm.

### Exponential backoff có giới hạn

Không nên để khoảng chờ tăng vô hạn. Giới hạn (d_{max}) giúp dự đoán thời gian và phù hợp với retry budget. Tuy nhiên, tổng thời gian retry vẫn có thể lớn:

\[
T = \sum_{i=1}^{n} t_i + \sum_{i=1}^{n-1} d_i
\]

Trong đó (t_i) là thời gian attempt thứ (i), (d_i) là thời gian chờ trước attempt tiếp theo. Cần bảo đảm tổng thời gian không vượt **deadline** và vẫn còn thời gian cho response/cleanup.

## 4. Các kiểu jitter phổ biến

Jitter tạo ra biến thiên trong khoảng chờ. Có nhiều thuật toán; chọn theo yêu cầu tải và khả năng kiểm soát độ trễ.

| Thuật toán | Công thức khái quát | Đặc điểm |
| --- | --- | --- |
| **No jitter** | (d_k) | Dễ dự đoán nhưng client dễ đồng bộ |
| **Full jitter** | (U(0, d_k)) | Chọn ngẫu nhiên từ 0 đến backoff cap; phân tán tốt |
| **Equal jitter** | (d_k/2 + U(0, d_k/2)) | Có mức chờ tối thiểu bằng một nửa backoff |
| **Decorrelated jitter** | (U(d_0, \min(d_{max}, previous \times 3))) | Khoảng chờ mới phụ thuộc khoảng chờ trước; biến thiên rộng |

(U(a,b)) là biến ngẫu nhiên phân bố đều trong khoảng từ (a) đến (b). Công thức là mô tả các biến thể thông dụng; một thư viện cụ thể có thể triển khai chi tiết khác.

### Full jitter

Với backoff cap 800 ms, full jitter chọn khoảng chờ ngẫu nhiên trong [0, 800] ms. Một số client có thể retry sớm, một số muộn; tải được phân tán tốt hơn so với cùng chờ 800 ms.

### Equal jitter

Với cap 800 ms, equal jitter luôn chờ ít nhất 400 ms và tối đa 800 ms. Phù hợp khi muốn giảm đồng bộ nhưng không muốn client tình cờ retry quá sớm.

### Decorrelated jitter

Khoảng chờ tiếp theo phụ thuộc khoảng chờ trước đó, ví dụ từ (d_0) đến ba lần khoảng trước, có giới hạn (d_{max}). Thuật toán có thể tạo phân phối khác full jitter và cần lưu trạng thái giữa các lần retry.

### Chọn thuật toán nào?

- **Full jitter** là lựa chọn dễ hiểu và thường hiệu quả để phân tán retry trong hệ thống có nhiều client.
- **Equal jitter** giữ một khoảng chờ tối thiểu.
- **Decorrelated jitter** hữu ích khi muốn giảm tương quan giữa các lần chờ liên tiếp.
- Nếu dịch vụ trả **Retry-After**, phải tôn trọng chỉ dẫn đó theo hợp đồng của dịch vụ; không áp dụng jitter khiến client retry sớm hơn thời điểm được yêu cầu.

## 5. Cài đặt backoff và jitter trong Java

Ví dụ dưới đây tính full jitter cho một lần retry. Nó không tự gửi request và không thay thế retry policy của SDK.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class BackoffPolicy {

    private final long initialMillis;
    private final long maxMillis;
    private final double multiplier;

    public BackoffPolicy(
            Duration initial,
            Duration max,
            double multiplier) {

        if (initial == null || max == null ||
                initial.isNegative() || initial.isZero() ||
                max.compareTo(initial) < 0 ||
                multiplier < 1.0) {
            throw new IllegalArgumentException("Invalid backoff settings");
        }

        this.initialMillis = initial.toMillis();
        this.maxMillis = max.toMillis();
        this.multiplier = multiplier;
    }

    public Duration fullJitter(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException(
                    "retryNumber must start at 1");
        }

        double cap = initialMillis;
        for (int i = 1; i < retryNumber && cap < maxMillis; i++) {
            cap = Math.min(maxMillis, cap * multiplier);
        }

        long upperBound = Math.max(1L, (long) Math.ceil(cap));
        long delay = ThreadLocalRandom.current()
                .nextLong(upperBound + 1L);

        return Duration.ofMillis(delay);
    }
}
~~~

Ví dụ:

~~~java
BackoffPolicy policy = new BackoffPolicy(
        Duration.ofMillis(100),
        Duration.ofSeconds(2),
        2.0);

Duration waitBeforeRetry3 = policy.fullJitter(3);
~~~

Đây là code minh họa. Khi dùng production, cần kiểm tra overflow/giới hạn Duration rất lớn, dùng random source có thể thay thế trong test và tích hợp với deadline/retry budget. Không gọi Thread.sleep() trực tiếp trong WebFlux event loop hoặc thread xử lý request reactive.

### Chờ retry trong ứng dụng

- Với code đồng bộ/blocking, có thể dùng Thread.sleep() trong một worker thread được giới hạn, nhưng phải tính thời gian chờ vào deadline và không giữ thread không cần thiết.
- Với Reactor, dùng Mono.delay hoặc retry operator có backoff phù hợp; không block event loop.
- Với background workflow, lưu nextRetryAt rồi đưa công việc vào scheduler/queue thay vì giữ một request mở trong thời gian dài.
- Với SDK, ưu tiên retry policy tích hợp khi SDK hiểu semantics của dịch vụ.

## 6. Retry-After: dịch vụ yêu cầu chờ bao lâu?

Một số dịch vụ dùng HTTP 429 hoặc 503 kèm header **Retry-After**. Theo HTTP semantics, header có thể chứa:

1. **Delay seconds**: số giây client nên chờ.
2. **HTTP-date**: thời điểm theo HTTP-date sau đó client có thể thử lại.

Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
~~~

Hoặc:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: Wed, 25 Nov 2026 10:00:00 GMT
~~~

Client nên đọc header theo contract của service/SDK. Nếu SDK đã tự tôn trọng Retry-After, không nên thêm một lớp retry với delay ngắn hơn làm mất hiệu lực chỉ dẫn.

### Quy tắc kết hợp Retry-After và jitter

Giả sử service yêu cầu chờ ít nhất 2 giây. Một cách an toàn là:

\[
d_{effective} = d_{server} + U(0, j_{max})
\]

Cách này giữ thời điểm retry **không sớm hơn** chỉ dẫn của server và thêm jitter để giảm đồng bộ. Tuy nhiên, một số service/client định nghĩa Retry-After là thời gian chính xác hoặc có giới hạn riêng; hãy tuân theo tài liệu của dịch vụ. Không cắt ngắn chỉ dẫn server nếu điều đó khiến request đến sớm hơn.

Nếu Retry-After dài hơn thời gian còn lại của deadline, không nên giữ request đồng bộ chờ. Trả lỗi có kiểm soát hoặc đưa công việc vào hàng đợi với thời điểm chạy lại phù hợp.

### Xử lý HTTP-date và clock skew

HTTP-date dùng wall clock UTC. Nếu đồng hồ client lệch so với server, tính thời gian chờ từ Instant.now() có thể sai. Trong trường hợp response có header **Date**, có thể dùng chênh lệch giữa Date và Retry-After theo contract, đồng thời giới hạn giá trị chờ tối đa theo chính sách nội bộ.

Không dùng thời điểm monotonic System.nanoTime() để parse HTTP-date. Hãy chuyển Retry-After thành một duration rồi dùng monotonic deadline để kiểm soát thời gian chờ.

## 7. Rate limiting là gì?

**Rate limiting** giới hạn số request hoặc operation được phép thực hiện trong một khoảng thời gian. Nó bảo vệ:

- Quota của managed service.
- Giới hạn request/second hoặc transaction/second.
- API đối tác có hạn mức theo tenant/key.
- Connection pool, database và worker capacity.
- Chi phí và khả năng phục vụ công bằng giữa các khách hàng.

Ví dụ, một API đối tác chỉ cho phép 100 request/giây cho mỗi API key. Nếu 10 replica Spring Boot cùng phát 20 request/giây, tổng là 200 request/giây và có thể bị 429 dù mỗi replica riêng lẻ không vượt giới hạn.

### Rate limit khác quota và concurrency limit

| Cơ chế | Kiểm soát | Ví dụ |
| --- | --- | --- |
| **Rate limit** | Tốc độ request trong thời gian | 100 request/giây |
| **Quota** | Tổng lượng sử dụng trong kỳ | 1 triệu request/ngày |
| **Concurrency limit** | Số thao tác đồng thời | Tối đa 20 upload đang chạy |
| **Connection pool** | Số kết nối được giữ/cho mượn | 30 JDBC connections |
| **Queue capacity** | Số tác vụ chờ | Tối đa 5.000 job pending |

Một hệ thống có thể đáp ứng rate limit nhưng vẫn quá tải vì mỗi request mất nhiều giây và concurrency tăng quá cao. Ngược lại, concurrency limit thấp không đảm bảo rate limit nếu các request hoàn thành cực nhanh.

## 8. Các thuật toán rate limiting

### 8.1. Fixed window counter

Đếm số request trong một cửa sổ cố định, ví dụ 100 request mỗi giây.

Ưu điểm:
- Đơn giản, dễ triển khai.
- Chi phí lưu trữ thấp.
- Dễ giải thích cho người vận hành.

Nhược điểm:
- **Boundary burst**: client có thể gửi 100 request ở cuối cửa sổ và 100 request ngay đầu cửa sổ kế tiếp, tạo 200 request trong khoảng thời gian rất ngắn.

~~~text
Window A: |--------------------|
Requests:                 100
Window B:                  |--------------------|
Requests:                  100
                           ↑ burst tại ranh giới
~~~

### 8.2. Sliding window log

Lưu timestamp của từng request và đếm số request trong khoảng thời gian trượt.

Ưu điểm: kiểm soát chính xác hơn theo cửa sổ thời gian.

Nhược điểm: lưu nhiều timestamp, chi phí bộ nhớ và thao tác cao khi throughput lớn.

### 8.3. Sliding window counter

Kết hợp counter của cửa sổ hiện tại và cửa sổ trước, ước lượng số request trong khoảng trượt dựa trên tỷ lệ thời gian đã trôi qua.

Ưu điểm: giảm bộ nhớ so với log và giảm boundary burst so với fixed window.

Nhược điểm: là ước lượng; không chính xác tuyệt đối với mọi phân bố request.

### 8.4. Token bucket

Một bucket chứa tối đa (B) token. Token được bổ sung theo tốc độ (r) token/giây. Mỗi request tiêu thụ một hoặc nhiều token.

- Khi bucket còn token, request được phép đi qua.
- Khi bucket hết token, request bị từ chối hoặc chờ.
- Bucket cho phép burst tối đa gần với dung lượng (B), trong khi tốc độ dài hạn được giới hạn bởi (r).

Ví dụ: tốc độ nạp 20 token/giây, dung lượng 40 token. Một burst 40 request có thể được chấp nhận khi bucket đầy; sau đó tốc độ trung bình dài hạn không vượt tốc độ nạp nếu không có token bổ sung khác.

~~~mermaid
flowchart LR
    A[Request đến] --> B{Bucket còn token?}
    B -->|Có| C[Trừ token]
    C --> D[Cho request đi qua]
    B -->|Không| E[Từ chối / chờ / xếp hàng]
    F[Refill theo thời gian] --> G[Bucket, tối đa B token]
    G --> B
~~~

### 8.5. Leaky bucket

Request đi vào hàng đợi và được xử lý với tốc độ cố định hoặc có giới hạn. Nếu queue đầy, request mới bị từ chối.

Ưu điểm:
- Làm phẳng burst.
- Tốc độ xử lý đầu ra ổn định.

Nhược điểm:
- Có thể tăng latency do chờ queue.
- Cần giới hạn dung lượng để tránh backlog vô hạn.

### So sánh thuật toán

| Thuật toán | Cho phép burst | Độ chính xác | Độ phức tạp | Trường hợp phù hợp |
| --- | --- | --- | --- | --- |
| Fixed window | Có, tại boundary | Trung bình | Thấp | Hạn mức đơn giản |
| Sliding log | Có theo giới hạn cửa sổ | Cao | Cao | Hạn mức cần chính xác |
| Sliding counter | Có nhưng giảm boundary effect | Ước lượng | Trung bình | API throughput lớn |
| Token bucket | Có, tối đa theo bucket | Tốt cho tốc độ trung bình và burst | Trung bình | API/service client |
| Leaky bucket | Làm phẳng burst ở đầu ra | Tốc độ đầu ra ổn định | Trung bình | Worker và pipeline cần đều tải |

## 9. Rate limit ở đâu trong kiến trúc?

Rate limit có thể được áp dụng tại nhiều tầng:

| Tầng | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **API gateway/ingress** | Bảo vệ endpoint khỏi client bên ngoài | Giới hạn request theo API key/tenant/IP |
| **Spring application** | Bảo vệ nghiệp vụ hoặc một dependency | Giới hạn số lần gọi Blob/partner API |
| **SDK/service client** | Tôn trọng throttling/quota của dịch vụ | SDK xử lý 429/Retry-After |
| **Message consumer** | Giới hạn tốc độ xử lý message | Tối đa 50 message/s hoặc 10 concurrent handlers |
| **Database access** | Bảo vệ DB khỏi quá tải | Bulkhead, pool và concurrency cap |
| **Distributed platform** | Chia sẻ quota giữa nhiều replica | Redis-backed token bucket |

Không đặt cùng một rate limiter ở mọi tầng nếu không có lý do. Ví dụ API gateway giới hạn 100 request/s cho người dùng, nhưng mỗi request có thể phát sinh 3 lời gọi downstream; dependency vẫn có thể nhận tới 300 operation/s. Cần tính **fan-out factor** và quota theo từng dịch vụ.

### Rate limit theo khóa nào?

Một limiter có thể áp dụng theo:

- Toàn ứng dụng hoặc toàn dependency.
- Tenant/customer ID.
- API key hoặc principal đã xác thực.
- Resource/service namespace.
- Operation type, ví dụ Blob upload khác Blob list.
- Người dùng hoặc nhóm khách hàng có tier khác nhau.

Không dùng IP đơn thuần làm khóa trong hệ thống có NAT/proxy nếu nhiều người dùng chia sẻ một IP. Không tin header user/tenant do client tự gửi; lấy identity/tenant từ ngữ cảnh đã xác thực.

## 10. Rate limiting trong Spring Boot

Có thể dùng thư viện như **Resilience4j RateLimiter**, **Bucket4j**, Spring Cloud Gateway hoặc một bộ giới hạn tập trung. Chọn theo vị trí và phạm vi cần kiểm soát.

### 10.1. Resilience4j RateLimiter

Ví dụ cấu hình một limiter cục bộ cho dependency:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      blobWrites:
        limit-for-period: 20
        limit-refresh-period: 1s
        timeout-duration: 0
~~~

Một service có thể dùng annotation:

~~~java
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import org.springframework.stereotype.Service;

@Service
public class BlobWriteService {

    private final BlobGateway gateway;

    public BlobWriteService(BlobGateway gateway) {
        this.gateway = gateway;
    }

    @RateLimiter(name = "blobWrites")
    public BlobReference upload(Document document) {
        return gateway.upload(document);
    }
}
~~~

Cấu hình này minh họa limiter trong **một instance JVM**. Nếu có 10 replica, mỗi replica có thể cho phép 20 operation/giây, tổng cộng khoảng 200 operation/giây. Nó không tự tạo một quota toàn cluster.

**timeout-duration: 0** thể hiện không chờ permit theo cấu hình minh họa; API/property cần kiểm tra theo version Resilience4j. Nếu không có permit, ứng dụng cần xử lý lỗi rate limit rõ ràng thay vì retry ngay.

### 10.2. Rate limiter cục bộ khác distributed rate limiter

Một limiter trong bộ nhớ process có phạm vi một JVM. Khi ứng dụng chạy nhiều replica:

~~~text
Replica A: 20 req/s
Replica B: 20 req/s
Replica C: 20 req/s
Replica D: 20 req/s
---------------------
Tổng có thể: 80 req/s
~~~

Nếu quota của đối tác là 50 req/s toàn hệ thống, limiter local 20 req/s ở mỗi replica không đủ. Có thể cần:

- Rate limiter phân tán qua Redis hoặc dịch vụ state chung.
- API gateway quản lý quota tập trung.
- Một dispatcher/worker duy nhất điều tiết outbound traffic.
- Phân bổ quota cố định cho từng replica và điều chỉnh khi scale.

Distributed limiter phải thực hiện cập nhật token/counter **atomic**. Một thao tác read-modify-write không atomic có thể cho phép nhiều replica cùng tiêu thụ một token hoặc vượt quota. Cần xét Redis script/transaction, clock consistency, network failure và behavior khi store limiter unavailable.

### 10.3. Token bucket bằng thư viện

Các thư viện như **Bucket4j** cung cấp token bucket và có integration với backend phân tán tùy edition/version. Ví dụ khái niệm:

~~~java
// Pseudocode: API chính xác phụ thuộc Bucket4j version/backend.
Bucket bucket = createTokenBucket(
        capacity = 40,
        refillTokens = 20,
        refillPeriod = Duration.ofSeconds(1));

if (bucket.tryConsume(1)) {
    callDependency();
} else {
    throw new RateLimitExceededException();
}
~~~

Không dùng pseudocode trên như mã Java biên dịch trực tiếp. Khi chọn thư viện, kiểm tra version, cách refill, clock, backend distributed, atomicity và license/edition của tính năng cluster.

## 11. Xử lý 429 và throttling từ dịch vụ managed

HTTP 429 **Too Many Requests** thường báo client vượt giới hạn tốc độ hoặc quota. Một số dịch vụ trả header Retry-After hoặc metadata riêng. Nhưng không phải mọi dịch vụ Azure đều biểu diễn throttling giống nhau.

### Azure

- **Azure Blob Storage:** có thể trả 429 hoặc 503 cho throttling/capacity theo tình huống; Storage SDK có retry options và có thể xử lý server response theo policy.
- **Azure Cosmos DB:** throttling thường biểu hiện bằng **429 RequestRateTooLarge**; response có thể cung cấp thời gian chờ như retry-after để client điều chỉnh. Cosmos SDK có cơ chế retry riêng.
- **Azure Service Bus:** quota/throttling và transient service errors có thể xuất hiện theo operation/namespace; client có retry behavior và messaging semantics riêng.
- **Azure Event Hubs:** throughput unit/processing limits có thể dẫn tới throttling; consumer/producer cần điều chỉnh partition, batching, concurrency và retry.

Không gộp mọi lỗi 429/503 vào cùng một cách xử lý nếu SDK đã có service-specific behavior. Đọc mã lỗi chi tiết và tài liệu của dịch vụ.

### AWS và Google Cloud

- AWS SDK for Java v2 có retry strategy và retry mode phù hợp với một số loại throttling/service error. Các quota dịch vụ và retry behavior vẫn cần được kiểm tra riêng.
- Google Cloud Java client có retry settings theo RPC/API và mã lỗi; quota có thể biểu hiện bằng RESOURCE_EXHAUSTED hoặc lỗi dịch vụ cụ thể.
- Với Pub/Sub, SQS, Event Hubs và Service Bus, delivery/ack/lock không phải rate limit outbound request. Cần điều chỉnh consumer concurrency và flow control riêng.

### Không retry 429 ngay lập tức

Nếu 429 xuất hiện, retry ngay thường làm tình trạng nặng hơn. Hãy:

1. Đọc Retry-After hoặc service-specific retry delay.
2. Giảm concurrency/rate nếu quota bị vượt kéo dài.
3. Áp backoff và jitter theo contract.
4. Kiểm tra deadline và retry budget.
5. Quan sát quota, request rate và success rate.
6. Chỉ tăng quota hoặc capacity qua quy trình quản trị dịch vụ, không bằng cách tăng retry.

## 12. Kết hợp rate limit, concurrency và backpressure

Rate limit kiểm soát **tốc độ**; concurrency limit kiểm soát **số tác vụ đang chạy**. Với dependency có latency biến động, cần cả hai.

Ví dụ Little's Law ở mức khái niệm:

\[
L = \lambda \times W
\]

Trong đó:

- (L): số operation trung bình đang chạy (concurrency).
- (\lambda): throughput trung bình (operation/second).
- (W): thời gian xử lý trung bình (second).

Nếu throughput 50 operation/s và latency trung bình 0,4 giây, số operation đồng thời trung bình khoảng 20. Khi latency tăng lên 2 giây mà vẫn giữ 50 operation/s, concurrency trung bình có thể tăng lên khoảng 100. Một pool/concurrency cap phù hợp giúp giới hạn áp lực lên hệ thống.

### Backpressure

Backpressure là cơ chế để consumer/downstream báo cho upstream giảm tốc độ phát dữ liệu. Trong Reactor, backpressure có thể được thể hiện qua demand; trong messaging, có thể điều chỉnh số message prefetch/concurrent handlers; trong worker queue, có thể giới hạn số tác vụ lấy ra đồng thời.

**Không thay backpressure bằng retry.** Nếu hệ thống liên tục nhận thêm công việc nhanh hơn tốc độ xử lý, retry chỉ làm backlog và tải lớn hơn.

### Một số biện pháp phối hợp

- Rate limiter giới hạn request được phép bắt đầu.
- Bulkhead giới hạn số operation đang thực thi.
- Connection pool giới hạn kết nối thực tế.
- Queue capacity giới hạn backlog.
- Backpressure điều tiết upstream.
- Circuit breaker ngăn gọi dependency đang lỗi.
- Retry có backoff/jitter phục hồi lỗi transient trong ngân sách.

## 13. Retry, rate limit và deadline phải cùng một chính sách

Một request có deadline 2 giây nhưng nhận Retry-After 3 giây không thể chờ trong cùng request rồi retry. Tương tự, một rate limiter có thể chờ permit nhưng thời gian chờ đó cũng tiêu thụ deadline.

Quy tắc:

1. Tính deadline trước khi chờ permit hoặc bắt đầu downstream call.
2. Nếu rate limiter không cấp permit ngay, chỉ chờ nếu còn ngân sách và chính sách cho phép.
3. Nếu Retry-After vượt deadline, trả lỗi hoặc lên lịch business retry.
4. Backoff/jitter phải nằm trong retry budget.
5. Attempt mới chỉ bắt đầu nếu còn đủ thời gian cho attempt và response reserve.
6. Khi quá tải kéo dài, circuit breaker hoặc queue có thể phù hợp hơn retry đồng bộ.

~~~mermaid
flowchart TD
    A[Operation deadline bắt đầu] --> B[Rate limiter / acquire permit]
    B -->|Có permit| C[Call dependency]
    B -->|Không permit| D{Còn thời gian chờ?}
    D -->|Không| X[Reject / enqueue]
    D -->|Có| E[Wait có giới hạn]
    E --> B
    C --> F{Thành công?}
    F -->|Có| G[Trả kết quả]
    F -->|Không| H{Transient và retryable?}
    H -->|Không| X
    H -->|Có| I[Retry-After / backoff + jitter]
    I --> J{Còn retry budget?}
    J -->|Không| X
    J -->|Có| B
~~~

Rate limiter nên nằm ở vị trí phù hợp để permit được tính cho **mỗi outbound attempt** nếu quota của dịch vụ tính từng request. Nếu limiter chỉ bao ngoài một phương thức có internal SDK retry, nó có thể chỉ đếm một lần application call trong khi SDK gửi nhiều request. Khi quota áp dụng theo HTTP request thực tế, cần hiểu retry nội bộ của SDK và cách đo quota.

## 14. Ví dụ Spring Boot: giới hạn outbound calls

Giả sử Documents API upload Blob và gọi một API metadata bên ngoài. Đội ứng dụng muốn giới hạn 20 thao tác Blob/giây **trên mỗi JVM** và tối đa 10 upload đang chạy đồng thời.

Có thể kết hợp:

- Resilience4j RateLimiter cho tốc độ.
- Bulkhead hoặc giới hạn executor cho concurrency.
- Azure Storage SDK retry cho lỗi service/transport.
- Deadline của nghiệp vụ để giới hạn tổng thời gian.

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      blobWrites:
        limit-for-period: 20
        limit-refresh-period: 1s
        timeout-duration: 0
  bulkhead:
    instances:
      blobWrites:
        max-concurrent-calls: 10
        max-wait-duration: 0
~~~

Ví dụ service:

~~~java
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import org.springframework.stereotype.Service;

@Service
public class DocumentsUploadService {

    private final BlobGateway blobGateway;

    public DocumentsUploadService(BlobGateway blobGateway) {
        this.blobGateway = blobGateway;
    }

    @RateLimiter(name = "blobWrites")
    @Bulkhead(name = "blobWrites")
    public BlobReference upload(Document document) {
        return blobGateway.upload(document);
    }
}
~~~

Đây là ví dụ theo annotation integration của Resilience4j. Cần thêm dependency phù hợp, kiểm tra AOP/proxy và phiên bản Spring Boot. Thứ tự decorator có thể ảnh hưởng việc permit được giữ trong lúc chờ bulkhead hoặc ngược lại; kiểm tra cấu hình và metrics thực tế.

**Giới hạn phạm vi:** với 5 replica, cấu hình trên có thể cho phép tổng cộng gần 100 operation/s và tối đa khoảng 50 concurrent calls nếu mỗi instance độc lập. Nếu quota toàn storage account chỉ là 40 operation/s, cần limiter phân tán hoặc quota allocation theo replica.

### Không dùng retry để xử lý rate limit cục bộ

Nếu Resilience4j RateLimiter từ chối operation vì hết permit, việc bọc nó bằng Retry có thể tạo vòng lặp thử xin permit liên tục và tiêu thụ CPU. Nên chọn một trong các chính sách:

- Reject ngay với lỗi rate limit nội bộ.
- Chờ permit trong khoảng tối đa đã định và trong deadline.
- Đưa operation vào queue để worker điều tiết.
- Trả HTTP 429/503 phù hợp cho caller nếu API không thể nhận thêm tải.

## 15. Rate limit phân tán giữa nhiều replica

Khi quota là **toàn hệ thống**, local limiter không đủ. Giả sử 8 replica cùng gọi API đối tác có quota 100 request/s. Nếu mỗi replica cho phép 20 request/s, tổng có thể lên tới 160 request/s.

### Những phương án thường dùng

| Phương án | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| **Central API gateway** | Một điểm kiểm soát quota cho nhiều service | Cần đặt mọi request qua gateway và hiểu cách gateway tính quota |
| **Redis-backed limiter** | Chia sẻ state giữa nhiều replica, hỗ trợ atomic script | Redis là dependency mới; cần xử lý latency/failure/clock |
| **Dedicated dispatcher/worker** | Điều tiết outbound tập trung, queue hóa | Tăng độ trễ và thêm thành phần vận hành |
| **Quota allocation per replica** | Đơn giản, không cần state chia sẻ | Phải điều chỉnh khi scale và có thể lãng phí quota |
| **Service-provided quota** | Dựa vào quota thực tế của dịch vụ | Không thay thế kiểm soát outbound burst ở phía ứng dụng |

### Scale-out làm thay đổi tổng quota

Nếu mỗi replica được cấp cố định (r) request/s và số replica là (N), tổng tốc độ cho phép có thể đạt:

\[
R_{total} = N \times r
\]

Khi autoscaling tăng (N), tổng outbound rate cũng tăng. Nếu quota dịch vụ cố định, cần:

- Cấp quota theo tổng replica hiện tại.
- Dùng limiter phân tán.
- Giới hạn autoscaling theo capacity downstream.
- Hoặc dùng worker/dispatcher có concurrency/rate cap toàn cục.

### Failure mode của distributed limiter

Nếu Redis không khả dụng, ứng dụng cần quyết định **fail-open** hay **fail-closed**:

- **Fail-open:** cho request đi qua để tránh làm gián đoạn ứng dụng; có thể vượt quota dịch vụ.
- **Fail-closed:** từ chối request khi không xác minh được permit; bảo vệ quota nhưng giảm availability.
- **Degraded local mode:** dùng local limiter với quota bảo thủ; không đảm bảo tổng chính xác nhưng hạn chế rủi ro.

Quyết định phụ thuộc hậu quả của việc vượt quota và yêu cầu availability. Phải quan sát trạng thái limiter và không âm thầm chuyển fail-open nếu hệ thống cần kiểm soát chi phí nghiêm ngặt.

## 16. Rate limiting cho API bên ngoài và multi-tenant

Một API có nhiều tenant có thể cần giới hạn công bằng:

- Quota riêng cho từng tenant.
- Quota toàn hệ thống cho một dependency.
- Quota theo operation type, ví dụ read/write.
- Burst allowance khác nhau theo tier.
- Reserved capacity cho thao tác quan trọng.
- Fair scheduling để tenant lớn không chiếm toàn bộ permit.

Không dùng một bucket toàn hệ thống duy nhất nếu cần fairness giữa khách hàng. Ngược lại, chỉ dùng bucket theo tenant có thể không bảo vệ được quota chung của dependency. Có thể cần **hai tầng**: global limit và per-tenant limit.

### Ví dụ

API có quota đối tác 100 request/s. Tổ chức có 10 tenant, mỗi tenant tối đa 15 request/s:

- Global token bucket: 100 request/s.
- Per-tenant bucket: 15 request/s mỗi tenant.
- Burst capacity: cấu hình theo hợp đồng dịch vụ.
- Concurrency cap: tối đa 30 request đang chạy.
- Retry budget: chỉ dành một phần quota cho retry để không chiếm hết traffic mới.

Retry cũng tiêu thụ quota. Nếu chỉ rate limit request ban đầu mà không tính retry, retry traffic có thể làm vượt giới hạn.

## 17. Quan sát backoff, jitter và rate limit

Các metrics quan trọng:

| Metric | Ý nghĩa |
| --- | --- |
| retry_attempts_total | Số attempt theo dependency/operation |
| retry_delay_seconds | Phân bố thời gian backoff thực tế |
| retry_after_seconds | Thời gian server yêu cầu chờ |
| rate_limit_allowed_total | Số operation được cấp permit |
| rate_limit_rejected_total | Số operation bị từ chối |
| rate_limit_wait_seconds | Thời gian chờ permit |
| rate_limit_tokens | Số token còn lại nếu thuật toán cung cấp |
| dependency_429_total | Số phản hồi throttling |
| dependency_503_total | Số lỗi service unavailable |
| in_flight_requests | Số operation đang chạy |
| queue_depth | Số operation đang chờ |
| deadline_exceeded_total | Số thao tác hết ngân sách khi chờ/retry |

Nên phân nhóm theo dependency, operation, tenant tier hoặc instance pool. Tránh đưa user ID, request ID, blob name hoặc message ID vào metric labels có cardinality rất cao. Thông tin chi tiết có thể đặt trong log/trace với masking phù hợp.

### Dấu hiệu hệ thống cần điều chỉnh

- Tỷ lệ 429 tăng cùng lúc retry attempts tăng.
- Rate limiter từ chối nhiều request nhưng queue depth tiếp tục tăng.
- Một tenant chiếm phần lớn permit.
- Autoscaling tăng replica làm tổng outbound request vượt quota.
- Backoff duration tăng nhưng deadline exhaustion cũng tăng.
- Retry traffic chiếm tỷ trọng lớn hơn request mới.
- Concurrency cao trong khi throughput không tăng tương ứng.

Không chỉ tăng quota hoặc retry count. Cần xác định bottleneck là quota, concurrency, latency, connection pool, downstream capacity hay phân phối traffic.

## 18. Kiểm thử backoff, jitter và rate limiting

### 18.1. Unit test cho thuật toán

Dùng random source có thể inject và clock giả để kiểm tra:

- Backoff tăng đúng hệ số và dừng ở max cap.
- Full jitter luôn nằm trong [0, cap].
- Equal jitter không nhỏ hơn một nửa cap.
- Decorrelated jitter tuân thủ giới hạn và phụ thuộc previous delay.
- Retry-After không bị rút ngắn trái contract.
- Deadline hết thì không tạo attempt mới.
- Counter/token không cấp quá giới hạn trong một cửa sổ được định nghĩa.

Không dùng Thread.sleep() thật trong unit test để kiểm tra công thức. Test tính toán bằng giá trị xác định; test thời gian chờ bằng scheduler/clock giả.

### 18.2. Test rate limiter

Với token bucket capacity 10 và refill 5 token/giây:

1. Bucket ban đầu đầy, 10 request có thể lấy permit.
2. Request tiếp theo bị từ chối hoặc chờ theo policy.
3. Sau khoảng 1 giây, số token được bổ sung theo semantics refill.
4. Nhiều thread cùng xin permit không được tiêu thụ vượt capacity.
5. Test restart/replica nếu limiter cần phân tán.
6. Test khi backend limiter unavailable theo fail-open/fail-closed policy.

### 18.3. Integration test với dịch vụ managed

- Tạo workload test với Azure Storage/Service Bus/Cosmos hoặc API test có quota được kiểm soát.
- Tạo burst có giới hạn để quan sát 429/throttling.
- Đọc Retry-After hoặc service-specific retry signal.
- Đếm outbound attempts ở SDK và application layer.
- Xác nhận rate limiter áp dụng cho mỗi request thực tế, kể cả SDK retry nếu quota tính theo request.
- Không cố ý gây throttling trên production account hoặc dịch vụ dùng chung.

### 18.4. Kiểm thử distributed limiter

Khởi chạy nhiều replica/test worker dùng chung limiter backend:

- Tổng request được cấp permit không vượt quota toàn cục theo thuật toán.
- Concurrent updates không làm cấp trùng token.
- Scale replica lên/xuống không làm quota tăng ngoài dự kiến.
- Redis/network failure tuân theo fail-open/fail-closed policy.
- Đồng hồ giữa các instance không làm refill sai nghiêm trọng.
- Per-tenant fairness được giữ trong tải hỗn hợp.

## 19. So sánh Azure, AWS và Google Cloud

| Chủ đề | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Retry SDK | Azure SDK service retry options | AWS SDK retry strategies/modes | API/RPC client retry settings |
| Throttling | 429/503 và service-specific error metadata | Throttling/service error theo API | RESOURCE_EXHAUSTED hoặc quota/service errors |
| Server retry signal | Retry-After hoặc metadata theo dịch vụ | Retry headers/service guidance theo API | RPC retry settings/status/service guidance |
| Rate limit phía ứng dụng | Resilience4j, Bucket4j, gateway hoặc Redis | Cùng thư viện Spring/Redis/gateway | Cùng thư viện Spring/Redis/gateway |
| Storage | Blob throughput/partition behavior | S3 request patterns và service limits | Cloud Storage request/quota behavior |
| Messaging | Service Bus lock/receiver flow control, Event Hubs throughput | SQS visibility/polling, Kinesis shard limits | Pub/Sub flow control/ack deadline |
| Quota | Theo subscription/resource/service/region tùy dịch vụ | Theo account/region/service/API | Theo project/region/API/service |

Các provider có quota, error code, retry behavior và flow-control khác nhau. Không bê nguyên một ngưỡng 100 request/s từ Azure sang S3 hoặc Pub/Sub mà không kiểm tra quota và service contract. Tương tự, **Spring Cloud Azure/AWS/GCP** không tạo một rate limit thống nhất cho mọi managed service.

## 20. Bài thực hành: bảo vệ Documents API khỏi retry storm

**Bối cảnh:** Documents API có 6 replica Spring Boot, gọi Azure Blob và một API metadata đối tác. Đối tác cho phép 120 request/s toàn hệ thống và trả 429 kèm Retry-After khi vượt quota. Mỗi request nghiệp vụ có deadline 2 giây.

### Phần A — Thiết kế retry

1. Chọn exponential backoff cap và full jitter cho lỗi transient.
2. Đọc Retry-After và không retry trước thời điểm server cho phép.
3. Tính retry budget trong deadline 2 giây.
4. Chỉ retry lỗi đã phân loại; không retry 401/403, validation hoặc lỗi cấu hình.
5. Xác định SDK đã retry nội bộ bao nhiêu lần trước khi application layer nhận lỗi.

### Phần B — Thiết kế rate limit

1. Chọn global token bucket với tốc độ dài hạn không vượt 120 request/s.
2. Đặt burst capacity theo hợp đồng đối tác.
3. Thêm per-tenant limit nếu cần fairness.
4. Đặt concurrency cap dựa trên latency và capacity.
5. Chọn Redis/gateway/dispatcher cho quota toàn cluster; không dùng local 20 request/s rồi giả định tổng không đổi khi scale.

### Phần C — Kiểm thử

1. Tạo burst test với nhiều replica/worker.
2. Làm test server trả 429 và Retry-After.
3. Xác minh không có retry trước thời gian server yêu cầu.
4. Đếm tổng request bao gồm SDK retry và Spring retry.
5. Làm Redis limiter unavailable và kiểm tra fail-open/fail-closed.
6. Tăng số replica để kiểm tra tổng outbound rate.
7. Kiểm tra deadline hết trong lúc chờ permit/backoff.
8. Kiểm tra fairness giữa hai tenant có lưu lượng rất khác nhau.

### Sản phẩm cần nộp

- Bảng backoff cap, jitter type, Retry-After handling và retry budget.
- Cấu hình rate limiter/concurrency limiter theo phạm vi local hay global.
- Kết quả burst test và distributed test.
- Metrics 429, retry attempts, wait time, rejected requests và deadline exhaustion.
- Giải thích giới hạn của phép thử so với quota production.

### Câu hỏi tự kiểm tra

1. Vì sao exponential backoff không jitter vẫn có thể tạo retry đồng bộ?
2. Full jitter và equal jitter khác nhau thế nào?
3. Nếu Retry-After là 5 giây nhưng deadline còn 1 giây, ứng dụng nên làm gì?
4. Rate limit khác quota và concurrency limit ở điểm nào?
5. Vì sao local RateLimiter không bảo vệ quota toàn cluster?
6. Token bucket cho phép burst như thế nào?
7. Leaky bucket phù hợp với trường hợp nào hơn token bucket?
8. Vì sao SDK retry nội bộ có thể khiến application rate limiter đếm thiếu request thực tế?
9. Redis limiter cần atomicity để tránh lỗi gì?
10. Vì sao retry traffic cũng phải tiêu thụ quota và retry budget?
11. Khi limiter backend lỗi, fail-open và fail-closed tạo trade-off gì?
12. Vì sao không nên retry ngay khi Resilience4j RateLimiter từ chối permit?

## 21. Ghi nhớ

- **Exponential backoff** tăng khoảng chờ; **jitter** phân tán thời điểm retry; **Retry-After** là tín hiệu từ dịch vụ cần được xử lý theo contract.
- Không retry trước thời điểm server yêu cầu. Nếu Retry-After vượt deadline, trả lỗi có kiểm soát hoặc chuyển sang business retry bất đồng bộ.
- **Rate limit** kiểm soát tốc độ, **quota** kiểm soát tổng lượng dùng trong kỳ, **concurrency limit** kiểm soát số thao tác đang chạy; connection pool và queue capacity giải quyết các giới hạn khác.
- Fixed window đơn giản nhưng có boundary burst; sliding window chính xác hơn với chi phí lớn hơn; token bucket cho phép burst có giới hạn; leaky bucket làm phẳng tốc độ đầu ra.
- Rate limiter local không phải quota toàn cluster. Với nhiều replica, dùng gateway, distributed limiter, dispatcher hoặc phân bổ quota theo scale.
- Kết hợp rate limit, concurrency, backpressure, circuit breaker, deadline và retry budget; không để retry làm tăng tải khi dịch vụ đang throttling.
- Kiểm thử cả 429, Retry-After, retry amplification, burst, multi-replica, limiter backend failure và fairness; đo request thực tế ở từng lớp.

## Tài liệu tham khảo

- [Resilience4j RateLimiter](https://resilience4j.readme.io/docs/ratelimiter)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Azure SDK for Java — Retry policy](https://learn.microsoft.com/azure/developer/java/sdk/retries)
- [Azure Storage retry policy for Java](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-java)
- [Azure Cosmos DB request units and throttling](https://learn.microsoft.com/azure/cosmos-db/request-units)
- [HTTP Retry-After header semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)
- [Token Bucket algorithm overview](https://en.wikipedia.org/wiki/Token_bucket)
- [AWS SDK for Java 2.x retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
