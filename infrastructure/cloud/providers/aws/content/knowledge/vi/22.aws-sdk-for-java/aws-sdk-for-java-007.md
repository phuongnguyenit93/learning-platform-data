# Timeout, retry, exponential backoff và jitter

Một dịch vụ Java Spring Boot gọi **Amazon DynamoDB** để đọc đơn hàng, **Amazon S3** để lưu hóa đơn và **Amazon SQS** để gửi tác vụ nền. Khi request timeout hoặc DynamoDB throttling, retry không có backoff có thể tạo retry storm.

Timeout giới hạn thời gian chờ. Retry thử lại lỗi tạm thời. Exponential backoff và jitter phân tán các lần thử lại. AWS SDK for Java 2.x có retry strategy tích hợp, nhưng ứng dụng vẫn phải bảo vệ idempotency cho side effects.

## 1. Mục tiêu học tập

- Phân biệt API call timeout và API attempt timeout.
- Hiểu standard, adaptive và legacy retry strategies.
- Cấu hình max attempts, backoff, jitter và HTTP client timeouts.
- Thiết kế idempotent writes và reconciliation.
- Tránh retry amplification, quan sát lỗi và kiểm thử.

## 2. Timeout layers

| Timeout | Phạm vi |
|---|---|
| API call timeout | Toàn bộ API operation gồm attempts và backoff |
| API call attempt timeout | Một lần gửi request |
| Connection timeout | Thiết lập TCP connection |
| TLS negotiation timeout | TLS handshake |
| Socket/read timeout | Chờ response |
| Write timeout | Gửi request body |
| Connection acquisition timeout | Chờ connection từ pool |

AWS SDK for Java 2.x không đặt mặc định API call timeout và API call attempt timeout theo tài liệu hiện hành. Hãy đặt chúng theo deadline của ứng dụng.

Nguồn: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html

## 3. Retry strategies

| Strategy | Đặc điểm |
|---|---|
| Standard | Exponential backoff, jitter, retry quota và circuit breaking |
| Adaptive | Standard cộng client-side rate limiter |
| Legacy | Hành vi retry cũ để tương thích |

Standard phù hợp với đa số workloads. Adaptive chỉ nên dùng khi client được cô lập theo một resource; throttling của resource này có thể làm chậm request tới resource khác nếu dùng chung client. Legacy chỉ nên giữ khi cần tương thích đã đánh giá.

Nguồn: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html

## 4. Mặc định từ SDK 2.58.0

Từ AWS SDK for Java 2.x 2.58.0, standard là retry strategy mặc định theo tài liệu AWS hiện hành.

- Phần lớn service clients: 3 total attempts, gồm một lần đầu và tối đa hai retries.
- DynamoDB và DynamoDB Streams: 4 total attempts theo default riêng.
- Base delay transient của phần lớn clients: 50 ms.
- Base delay throttling: 1 giây.
- Backoff có jitter, maximum delay mặc định 20 giây.
- Legacy thường có 4 total attempts cho phần lớn clients; DynamoDB legacy có thể có 9.

Kiểm tra SDK BOM/version và cấu hình runtime trước khi dựa vào default.

## 5. Max attempts và retry quota

Max attempts là tổng số attempts, bao gồm lần đầu:

| Max attempts | Retries tối đa |
|---:|---:|
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| 4 | 3 |

Standard strategy có retry quota. Mỗi retry tiêu tốn quota; request thành công bổ sung quota theo cơ chế SDK. Khi quota cạn, SDK vẫn thực hiện attempt đầu tiên nhưng có thể ngừng retries. Circuit breaker của retry strategy cũng có thể tạm tắt retries khi downstream failures tăng cao.

## 6. Exponential backoff và jitter

    delay_limit(retry) = min(max_delay, base_delay × 2^retry)
    delay = random(0, delay_limit)

Full jitter phân tán clients để tránh thundering herd. Standard strategy sử dụng exponential backoff với full jitter. Throttling và transient errors có base delay riêng; DynamoDB có default riêng theo tài liệu SDK.

## 7. Lỗi retryable và non-retryable

| Loại lỗi | Ví dụ | Retry |
|---|---|---|
| Throttling | Provisioned throughput exceeded | Thường có, kèm backoff |
| Transient network | Connection reset, socket timeout | Có thể có |
| Transient service | Một số lỗi 5xx | Thường có |
| Validation | Request sai field/parameter | Không |
| Authorization | Access denied | Không |
| Resource missing | Sai table/bucket/ARN | Không |
| Unknown write outcome | Timeout sau khi gửi write | Chỉ khi idempotent hoặc có reconciliation |

Không retry mọi exception. Retry lỗi vĩnh viễn chỉ làm tăng latency, chi phí và tải downstream.

## 8. Cấu hình environment và profile

Linux/macOS:

    export AWS_RETRY_MODE=standard
    export AWS_MAX_ATTEMPTS=3

Shared AWS config:

    [profile dev]
    region = ap-southeast-1
    retry_mode = standard
    max_attempts = 3

Thứ tự ưu tiên theo tài liệu SDK: cấu hình trực tiếp trong code, environment variables, shared config profile, SDK default.

## 9. Cấu hình Java retry

    import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
    import software.amazon.awssdk.core.retry.RetryMode;

    DynamoDbClient client = DynamoDbClient.builder()
        .overrideConfiguration(o -> o
            .retryStrategy(RetryMode.STANDARD)
        )
        .build();

Tùy chỉnh tổng số attempts:

    DynamoDbClient client = DynamoDbClient.builder()
        .overrideConfiguration(o -> o
            .retryStrategy(b -> b.maxAttempts(4))
        )
        .build();

Các cấu hình trên không tự đặt API call timeout. Cần cấu hình riêng và tránh tăng attempts để che throttling.

## 10. Cấu hình timeout với Apache HTTP client

    import java.time.Duration;
    import software.amazon.awssdk.core.retry.RetryMode;
    import software.amazon.awssdk.http.apache.ApacheHttpClient;
    import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

    DynamoDbClient client = DynamoDbClient.builder()
        .httpClientBuilder(
            ApacheHttpClient.builder()
                .connectionTimeout(Duration.ofMillis(500))
                .socketTimeout(Duration.ofMillis(1500))
                .connectionAcquisitionTimeout(Duration.ofMillis(500))
        )
        .overrideConfiguration(o -> o
            .retryStrategy(RetryMode.STANDARD)
            .apiCallAttemptTimeout(Duration.ofSeconds(2))
            .apiCallTimeout(Duration.ofSeconds(7))
        )
        .build();

Các con số là ví dụ. Chọn theo p95/p99 latency, request size, Region, VPC và service SLO. Dự án phải thêm module Apache HTTP client cùng version AWS SDK; với async client, cấu hình Netty hoặc CRT phù hợp.

## 11. Smart defaults và per-request timeout

Smart configuration defaults có các modes STANDARD, IN_REGION, CROSS_REGION, MOBILE, AUTO và LEGACY. Chúng có thể chọn HTTP transport defaults theo môi trường nhưng không thay API call timeout và attempt timeout theo deadline nghiệp vụ.

Per-request override cho một operation:

    var response = s3.listBuckets(b -> b
        .overrideConfiguration(c -> c
            .apiCallTimeout(Duration.ofSeconds(5))
            .apiCallAttemptTimeout(Duration.ofSeconds(2))
        )
    );

Chỉ request được truyền override mới dùng các timeout này.

## 12. Idempotency và unknown outcome

Timeout sau khi gửi write không chứng minh service chưa thực hiện request. Ví dụ DynamoDB có thể đã commit nhưng response bị mất trên đường về. Retry một phép cộng counter, charge payment hoặc tạo external side effect có thể thực hiện tác vụ hai lần.

Dùng idempotency token nếu service API hỗ trợ. Với nghiệp vụ riêng, dùng operation ID ổn định, unique constraint/conditional write và lưu kết quả trong cùng transaction. Khi retry, giữ nguyên token; không tạo token mới cho mỗi attempt.

## 13. SDK retry và application retry

SDK retry xử lý lỗi ở tầng AWS request. Application retry xử lý business workflow. Nếu gateway có hai attempts, application có ba và SDK có ba, tổng số request lý thuyết có thể thành 18.

- Để SDK xử lý retry transport/service mặc định.
- Chỉ retry business operation khi idempotent.
- Đặt deadline tổng xuyên suốt request.
- Tránh retry lồng nhau ở gateway, controller, service, repository và SDK.
- Chuyển tác vụ dài sang queue/DLQ nếu HTTP deadline không đủ.

## 14. Observability

Ghi service/operation, Region, AWS request ID, HTTP status/error code, exception class, total latency, retry count, timeout layer, business operation ID và trace ID. Không log credentials, PII hoặc request payload nhạy cảm.

Theo dõi API call latency, attempt timeout, API call timeout, retry rate, throttling rate, connection pool acquisition timeout, HTTP errors, 5xx và duplicate business operations. Alert khi retry tăng dù final success rate còn cao.

## 15. Kiểm thử và runbook

Unit tests cần kiểm tra attempt limit, delay, jitter, deadline, non-retryable errors và idempotency token. Integration tests mô phỏng throttling, 5xx, connection reset, read timeout, TLS failure và slow response.

Khi sự cố:
1. Xác định service, operation, Region và resource.
2. Phân loại throttling, 5xx, network, pool acquisition hay timeout.
3. Kiểm tra retry mode, max attempts và SDK version.
4. Xem request ID, CloudWatch metrics, retry rate và HTTP pool.
5. Giảm concurrency nếu downstream quá tải.
6. Reconcile write có kết quả chưa rõ bằng idempotency key.
7. Sau phục hồi, xác nhận retry rate và latency trở lại baseline.

Không tăng timeout hoặc max attempts để che hot partition, quota, pool exhaustion hay throttling kéo dài.

## 16. Tổng kết

Timeout giới hạn thời gian chờ; retry xử lý lỗi tạm thời; exponential backoff và jitter giảm retry storms. Standard là lựa chọn phù hợp cho phần lớn workloads. Adaptive cần resource isolation; legacy phục vụ tương thích.

Max attempts bao gồm lần đầu. API call timeout bao gồm attempts và backoff; attempt timeout giới hạn một lần thử. HTTP timeout kiểm soát connection, TLS, read/write và pool acquisition.

Retry không thay idempotency. Timeout sau write có thể để lại unknown outcome; cần token, conditional write hoặc reconciliation. Không để retries ở gateway, application và SDK nhân lên ngoài kiểm soát.

### Tài liệu AWS chính thức

1. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html
2. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html
3. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html
4. https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html
5. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/smart-configuration-defaults.html
6. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html
7. https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html
8. https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html
9. https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html
10. https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html
11. https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
12. https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html