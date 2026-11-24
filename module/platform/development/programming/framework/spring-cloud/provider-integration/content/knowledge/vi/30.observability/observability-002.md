# Đo độ trễ, tỷ lệ lỗi, throttling và số lần retry

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud**, bao gồm storage, messaging, dữ liệu, danh tính, quyền và bảo vệ secret. Khi đưa SDK cloud vào ứng dụng production, câu hỏi không chỉ là request có thành công hay không. Đội vận hành còn cần biết request mất bao lâu, lỗi xuất hiện với tần suất nào, dịch vụ có giới hạn tốc độ hay không và SDK đã phải thử lại bao nhiêu lần.

Ví dụ, một API nhận yêu cầu tạo báo cáo. API đọc metadata từ object storage, truy vấn database, sau đó gửi một message cho worker. Người dùng thấy API trả về thành công, nhưng phía sau SDK có thể đã retry hai lần vì throttling. Nếu chỉ đo thời gian HTTP ở controller, nhóm vận hành không biết cloud provider đang trả lỗi 429/503, thời gian chờ backoff đang tăng hay retry đang che giấu một dependency suy giảm.

Bài học này trình bày cách đo bốn tín hiệu quan trọng:

- **Độ trễ (latency):** một thao tác cloud mất bao lâu, tính cả retry nếu đo ở cấp logical operation.
- **Tỷ lệ lỗi (error rate):** bao nhiêu thao tác thất bại trên tổng số thao tác.
- **Throttling:** bao nhiêu thao tác bị dịch vụ giới hạn tốc độ hoặc từ chối tạm thời do quota/capacity.
- **Retry:** SDK hoặc ứng dụng đã thực hiện bao nhiêu lần thử bổ sung trước khi thành công hoặc thất bại cuối cùng.

Sau bài này, bạn có thể:

- Dùng Micrometer Timer, Counter và histogram trong Spring Boot.
- Định nghĩa metric có thể so sánh giữa AWS, Azure và Google Cloud.
- Phân biệt logical call, attempt, retry và thời gian backoff.
- Phân loại throttling theo mã HTTP, service error code hoặc gRPC status.
- Tạo dashboard/PromQL cho p95 latency, error rate, throttle rate và retry rate.
- Tránh metric cardinality cao, double counting và retry storm.

## 2. Bốn tín hiệu và cách diễn giải

Một logical operation là một hành động nghiệp vụ mà ứng dụng muốn hoàn thành, ví dụ `upload_document` hoặc `send_job`. SDK có thể tạo nhiều network attempt cho cùng logical operation.

~~~mermaid
flowchart TD
    A[Logical operation: upload document] --> B[Attempt 1]
    B -->|429 / throttled| C[Backoff]
    C --> D[Attempt 2]
    D -->|503 / transient| E[Backoff]
    E --> F[Attempt 3]
    F -->|Success| G[Logical operation completed]
    G --> H[Latency của logical call]
    B --> I[Attempt metrics]
    D --> I
    F --> I
    C --> J[Backoff duration]
    E --> J
~~~

| Tín hiệu | Đơn vị/metric điển hình | Câu hỏi vận hành |
|---|---|---|
| Latency | giây, histogram và p50/p95/p99 | Người dùng hoặc worker phải chờ bao lâu? |
| Error rate | lỗi / tổng logical calls | Tỷ lệ thao tác không hoàn thành là bao nhiêu? |
| Throttling | số lỗi throttle / tổng calls hoặc attempts | Có bị quota/rate limit/capacity giới hạn không? |
| Retry | số retry bổ sung / logical calls | SDK phải thử lại nhiều đến mức nào? |

Không nên gộp bốn tín hiệu thành một trạng thái UP/DOWN. Một dependency có thể vẫn trả thành công 99,9% request nhưng p99 latency tăng mạnh do retry; hoặc tỷ lệ lỗi thấp nhưng số lần throttle tăng và sắp chạm quota.

## 3. Đo latency ở đúng ranh giới

### 3.1. Logical-call latency và attempt latency

Có hai cách đo thời gian:

- **Logical-call latency:** từ lúc ứng dụng gọi SDK cho đến khi SDK trả kết quả cuối cùng. Khoảng thời gian này thường bao gồm serialization, network, các attempt, backoff và deserialize.
- **Attempt latency:** thời gian của từng request gửi tới cloud provider. Một logical call có thể có một hoặc nhiều attempt.

Đo logical-call latency giúp trả lời câu hỏi “ứng dụng chờ bao lâu để hoàn tất thao tác?”. Attempt latency giúp phân biệt provider/network chậm với thời gian chờ do retry.

Ví dụ:

| Thành phần | Thời gian |
|---|---:|
| Attempt 1 | 120 ms |
| Backoff 1 | 200 ms |
| Attempt 2 | 180 ms |
| Backoff 2 | 400 ms |
| Attempt 3 | 100 ms |
| **Logical-call latency** | **1.000 ms** |

Nếu chỉ đo attempt cuối cùng, dashboard sẽ báo 100 ms và che khuất việc ứng dụng thực tế đã chờ một giây.

### 3.2. Dùng Timer thay vì tự tạo Gauge thời gian

Micrometer Timer được thiết kế cho các thao tác có thời lượng. Timer ghi nhận ít nhất tổng thời gian và số lần sự kiện; registry có thể xuất thêm max, histogram hoặc percentile tùy cấu hình.

Ví dụ đo một đoạn code:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class StorageOperationTimer {
    private final MeterRegistry registry;

    public StorageOperationTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public void upload(Runnable operation) {
        Timer timer = Timer.builder("cloud.dependency.duration")
                .tag("provider", "azure")
                .tag("service", "blob")
                .tag("operation", "upload")
                .register(registry);

        timer.record(operation);
    }
}
~~~

Trong ứng dụng thực, hãy dùng tên operation ổn định như upload, download, send_message, get_object thay vì tên method chứa ID hoặc tên tài nguyên. Nếu muốn đo cả thời gian retry nội bộ SDK, đặt Timer bao quanh **toàn bộ lời gọi SDK**.

### 3.3. Histogram và percentile

Các percentile thường được dùng:

- **p50:** trải nghiệm của request ở giữa phân phối.
- **p95:** 95% thao tác hoàn thành trong thời gian này hoặc nhanh hơn.
- **p99:** phần đuôi chậm, thường giúp phát hiện retry, network bất ổn hoặc contention.

Percentile client-side do từng instance tính riêng không thể cộng gộp chính xác giữa nhiều Pod. Với Prometheus, nên dùng histogram có bucket để tính percentile từ dữ liệu đã tổng hợp. Micrometer hỗ trợ publishPercentileHistogram() và serviceLevelObjectives(...).

Ví dụ cấu hình bucket theo mục tiêu của một thao tác:

~~~java
import java.time.Duration;

Timer timer = Timer.builder("cloud.dependency.duration")
        .tag("provider", "aws")
        .tag("service", "s3")
        .tag("operation", "get_object")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1),
                Duration.ofSeconds(2))
        .register(registry);
~~~

Chọn bucket theo SLO thực tế và loại operation. get_object nhỏ, upload_large_file và send_message có phân phối thời gian khác nhau; không áp dụng một ngưỡng latency cho mọi operation.

## 4. Đo error rate đúng mẫu số

### 4.1. Phân biệt lỗi cuối cùng với lỗi đã được retry thành công

Giả sử 1.000 logical calls có:

- 20 calls gặp lỗi ở attempt đầu nhưng SDK retry thành công.
- 5 calls thất bại sau khi hết retry.

Tỷ lệ lỗi cuối cùng ở cấp logical call là 5 / 1.000 = 0,5%. Tuy nhiên, 20 calls kia vẫn tạo thêm tải, tăng latency và có thể báo hiệu dependency đang suy giảm. Vì vậy cần đo cả:

- **Final error rate:** logical call kết thúc thất bại / tổng logical calls.
- **Attempt error rate:** request attempt thất bại / tổng attempts.
- **Retry rate:** số lần retry bổ sung / tổng logical calls.

Không dùng số lỗi attempt làm error rate người dùng cuối nếu SDK vẫn hoàn tất thao tác thành công.

### 4.2. Phân loại lỗi theo nhóm ổn định

Một tập nhóm có thể dùng chung cho các provider:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| throttled | AWS throttling error, Azure 429, Google RESOURCE_EXHAUSTED | Dịch vụ giới hạn tốc độ hoặc quota |
| timeout | Connect/read/API call timeout | Không nhận được kết quả trong thời hạn |
| network | DNS, connection reset, I/O | Lỗi đường truyền hoặc transport |
| authorization | IAM/RBAC/permission denied | Identity hoặc quyền không phù hợp |
| not_found | Bucket/container/queue/object không tồn tại | Resource hoặc đường dẫn sai |
| server | 5xx/service unavailable | Dịch vụ gặp lỗi phía server |
| conflict | Conditional write conflict, version/ETag conflict | Trạng thái tài nguyên đã thay đổi |
| other | Nhóm còn lại | Cần điều tra thêm |

Phân loại lỗi nên dựa trên **service error code và SDK exception**, không chỉ dựa vào HTTP status. Một số dịch vụ AWS có throttling error với HTTP 400; Azure có thể trả 503 Server Busy; Google API có thể trả gRPC RESOURCE_EXHAUSTED.

### 4.3. Đếm lỗi bằng Counter

Counter tăng đơn điệu theo số sự kiện. Backend giám sát thường tính tốc độ tăng của Counter trên một cửa sổ thời gian để tạo error rate.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CloudErrorMetrics {
    private final MeterRegistry registry;

    public CloudErrorMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordFinalError(
            String provider,
            String service,
            String operation,
            String errorType) {

        registry.counter(
                "cloud.dependency.errors",
                "provider", provider,
                "service", service,
                "operation", operation,
                "error_type", errorType)
            .increment();
    }
}
~~~

Chỉ truyền các giá trị hữu hạn như azure, blob, upload, timeout hoặc throttled. Không truyền exception message hoặc URL đầy đủ vào tag.

## 5. Throttling: phân biệt với lỗi server thông thường

**Throttling** xảy ra khi dịch vụ giới hạn tốc độ hoặc lượng tài nguyên mà caller sử dụng. Nguyên nhân có thể là:

- Vượt request rate hoặc quota.
- Quá nhiều request đồng thời.
- Vượt giới hạn partition, namespace, table hoặc resource cụ thể.
- Dịch vụ đang bảo vệ capacity hoặc chịu tải cao.

Throttling không đồng nghĩa với mọi HTTP 429/503 trong mọi dịch vụ. Hãy giữ cả error_type=throttled và mã/nhóm status đã chuẩn hóa để phân tích.

| Provider | Dấu hiệu có thể gặp | Lưu ý |
|---|---|---|
| **AWS** | SDK error type Throttling, service error code như ThrottlingException, RequestLimitExceeded; một số dịch vụ có mã riêng như SlowDown | Không chỉ lọc HTTP 429; dùng service error code/SDK classification |
| **Azure** | HTTP 429 Too Many Requests; một số dịch vụ trả 503 Server Busy hoặc mã lỗi service-specific | Kiểm tra Retry-After hoặc header retry tương ứng; phân biệt quota với lỗi tạm thời |
| **Google Cloud** | gRPC RESOURCE_EXHAUSTED, HTTP 429 hoặc quota-specific error | UNAVAILABLE là lỗi tạm thời nhưng không tự động đồng nghĩa throttling |

### 5.1. Metric cho throttling

Có thể tạo Counter riêng:

~~~java
registry.counter(
        "cloud.dependency.throttled.calls",
        "provider", "azure",
        "service", "blob",
        "operation", "upload")
    .increment();
~~~

Thống nhất quy tắc: tăng counter khi **một logical call hoặc một attempt** gặp throttling? Đề xuất ghi riêng:

- cloud.dependency.throttled.calls: số logical calls có ít nhất một throttle response.
- cloud.dependency.throttled.attempts: tổng số attempts bị throttle.

Hai metric trả lời câu hỏi khác nhau. Nếu chỉ có một metric, ghi rõ định nghĩa và không trộn cả hai cách đếm.

### 5.2. Theo dõi Retry-After

Khi dịch vụ gửi Retry-After hoặc header retry tương ứng, client nên tôn trọng thời gian đó theo hướng dẫn của SDK/dịch vụ. Nếu không có chỉ dẫn, exponential backoff kèm jitter giúp dàn đều request retry.

Không retry ngay lập tức sau 429. Hành vi đó có thể làm quota/capacity bị áp lực nặng hơn. Đồng thời đặt giới hạn số attempt hoặc tổng thời gian operation; retry vô hạn có thể giữ thread và request trong thời gian không kiểm soát.

## 6. Retry: đếm lần thử bổ sung và thời gian backoff

### 6.1. Attempt khác retry

Nếu một logical call có ba attempts:

- Attempt 1 là lần thử ban đầu.
- Attempt 2 và 3 là hai retries.
- Tổng attempts = 3; retry count = 2.

Định nghĩa này quan trọng khi tạo dashboard. Không đặt tên metric retry_count rồi tăng cả ở attempt đầu tiên.

### 6.2. Những gì nên đo

| Metric | Ý nghĩa |
|---|---|
| cloud.dependency.calls | Tổng logical calls |
| cloud.dependency.retries | Số lần thử bổ sung sau attempt đầu |
| cloud.dependency.retry.exhausted | Logical calls đã hết retry mà vẫn thất bại |
| cloud.dependency.backoff.duration | Tổng thời gian chờ giữa các attempts |
| cloud.dependency.attempts | Tổng request attempts nếu SDK/pipeline cung cấp |
| cloud.dependency.duration | Thời gian hoàn tất logical call, bao gồm retry/backoff nếu đo quanh SDK call |

Không phải SDK nào cũng cung cấp cùng tập metric attempt/retry. Hãy phân biệt metric do **ứng dụng tự kiểm soát** với metric do **SDK/provider telemetry** cung cấp.

### 6.3. Retry policy và backoff

Một retry policy thường cần xác định:

- Lỗi nào có thể retry: throttling, timeout tạm thời, một số lỗi 5xx hoặc transport.
- Lỗi nào không nên retry: permission denied, resource không tồn tại, payload sai, validation error.
- Số attempts tối đa hoặc tổng thời gian tối đa.
- Exponential backoff, giới hạn delay và jitter.
- Cách xử lý Retry-After.
- Hành vi khi hết retry: trả lỗi, đưa vào queue hoặc chuyển sang quy trình phục hồi.

Ví dụ lịch backoff minh họa:

~~~text
Initial delay = 100 ms
Multiplier = 2
Maximum delay = 1 s

Retry 1: khoảng 100 ms + jitter
Retry 2: khoảng 200 ms + jitter
Retry 3: khoảng 400 ms + jitter
Retry 4: tối đa khoảng 1 s + jitter
~~~

Đây chỉ là ví dụ, không phải giá trị mặc định của mọi SDK. Dùng retry strategy của provider khi phù hợp và tránh bọc thêm một vòng retry không giới hạn ở tầng service.

## 7. Thiết lập Micrometer trong Spring Boot

Spring Boot Actuator tích hợp Micrometer và tự cấu hình MeterRegistry khi có registry implementation tương ứng trên classpath. Thêm Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Nếu xuất metric sang Prometheus, thêm registry:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
  metrics:
    tags:
      application: provider-integration
~~~

Endpoint hữu ích:

- /actuator/metrics: xem meter trong registry để chẩn đoán.
- /actuator/prometheus: scrape metric nếu Prometheus registry có trên classpath và endpoint được expose.
- /actuator/health: health endpoint, không thay thế metrics.

Chỉ expose các endpoint cần thiết trong mạng quản trị. Không mở env, configprops hoặc endpoint nhạy cảm ra Internet.

## 8. Tạo bộ metric chung cho các cloud provider

Một lớp metrics chung giúp so sánh provider, nhưng adapter của từng SDK vẫn phải phân loại lỗi theo mã riêng. Ví dụ dưới đây đo logical-call latency, số logical calls, lỗi cuối cùng và throttle calls.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class CloudOperationMetrics {
    private final MeterRegistry registry;

    public CloudOperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(
            String provider,
            String service,
            String operation,
            Supplier<T> action,
            Function<RuntimeException, Failure> classifier) {

        long started = System.nanoTime();
        String outcome = "success";

        try {
            return action.get();
        } catch (RuntimeException ex) {
            outcome = "error";
            Failure failure = classifier.apply(ex);

            Counter.builder("cloud.dependency.errors")
                    .tags(
                            "provider", provider,
                            "service", service,
                            "operation", operation,
                            "error_type", failure.errorType(),
                            "status_class", failure.statusClass())
                    .register(registry)
                    .increment();

            if (failure.throttled()) {
                Counter.builder("cloud.dependency.throttled.calls")
                        .tags(
                                "provider", provider,
                                "service", service,
                                "operation", operation)
                        .register(registry)
                        .increment();
            }
            throw ex;
        } finally {
            Timer.builder("cloud.dependency.duration")
                    .tags(
                            "provider", provider,
                            "service", service,
                            "operation", operation)
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(
                            Duration.ofMillis(100),
                            Duration.ofMillis(250),
                            Duration.ofMillis(500),
                            Duration.ofSeconds(1),
                            Duration.ofSeconds(2))
                    .register(registry)
                    .record(System.nanoTime() - started, TimeUnit.NANOSECONDS);

            Counter.builder("cloud.dependency.calls")
                    .tags(
                            "provider", provider,
                            "service", service,
                            "operation", operation,
                            "outcome", outcome)
                    .register(registry)
                    .increment();
        }
    }

    public record Failure(
            String errorType,
            String statusClass,
            boolean throttled) {
    }
}
~~~

Các giá trị provider, service, operation, errorType và statusClass phải được chuẩn hóa trước khi truyền vào. classifier nên là adapter nhỏ, không ném exception mới và chỉ trả các nhóm hữu hạn như throttled, timeout, authorization, not_found, server, network, other.

Đoạn code này ghi nhận **final outcome** của logical call. Nếu SDK tự retry nội bộ rồi thành công, call được tính success; retry attempts bên trong SDK cần được lấy từ telemetry riêng nếu SDK cung cấp. Nếu muốn đo một call void, có thể tạo overload nhận Runnable hoặc bọc kết quả thành một giá trị không null.

### 8.1. Ví dụ bọc một thao tác Azure Blob

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobStorageException;
import java.io.ByteArrayInputStream;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorage {
    private final BlobClient blobClient;
    private final CloudOperationMetrics metrics;

    public DocumentStorage(
            BlobClient blobClient,
            CloudOperationMetrics metrics) {
        this.blobClient = blobClient;
        this.metrics = metrics;
    }

    public void upload(byte[] content) {
        metrics.record(
                "azure",
                "blob",
                "upload",
                () -> {
                    blobClient.upload(
                            new ByteArrayInputStream(content),
                            content.length,
                            true);
                    return Boolean.TRUE;
                },
                ex -> {
                    if (ex instanceof BlobStorageException storageException) {
                        int status = storageException.getStatusCode();
                        boolean throttled = status == 429;
                        String type = throttled ? "throttled"
                                : status == 403 ? "authorization"
                                : status == 404 ? "not_found"
                                : status >= 500 ? "server" : "other";
                        return new CloudOperationMetrics.Failure(
                                type, status / 100 + "xx", throttled);
                    }
                    return new CloudOperationMetrics.Failure(
                            "other", "unknown", false);
                });
    }
}
~~~

Ví dụ minh họa adapter cho một thao tác Azure Blob đồng bộ. Trong ứng dụng thực, không tạo BlobClient mới mỗi request; inject client đã cấu hình và quản lý vòng đời ở tầng cấu hình. Đoạn classifier coi HTTP 429 là throttling. Với HTTP 503, hãy kiểm tra service error code (chẳng hạn ServerBusy ở dịch vụ có hỗ trợ) và header retry trước khi phân loại; không phải mọi 503 đều là throttle.

## 9. Đo retry do ứng dụng kiểm soát

Nếu ứng dụng có retry wrapper riêng, tăng counter cho **mỗi lần retry bổ sung**, không tăng ở lần đầu:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class CloudRetryMetrics {
    private final MeterRegistry registry;

    public CloudRetryMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordRetry(
            String provider,
            String service,
            String operation,
            String reason) {
        registry.counter(
                "cloud.dependency.retries",
                "provider", provider,
                "service", service,
                "operation", operation,
                "reason", reason)
            .increment();
    }

    public void recordBackoff(
            String provider,
            String service,
            String operation,
            Duration delay) {
        registry.timer(
                "cloud.dependency.backoff.duration",
                "provider", provider,
                "service", service,
                "operation", operation)
            .record(delay);
    }
}
~~~

Gọi recordRetry(...) khi retry policy quyết định thực hiện attempt tiếp theo, và recordBackoff(...) với thời gian chờ thực tế. Nếu dùng SDK auto-retry, không có callback ở tầng ứng dụng để biết từng attempt thì **không được coi counter này là số retry của SDK**.

## 10. Telemetry riêng của AWS, Azure và Google Cloud

Micrometer cung cấp cách đặt tên metric và tổng hợp ở tầng ứng dụng. SDK/provider có thêm telemetry riêng, nhưng không phải SDK nào cũng xuất cùng dữ liệu.

### 10.1. AWS SDK for Java 2.x

AWS SDK for Java 2.x hỗ trợ MetricPublisher. Khi bật SDK metrics, dữ liệu có thể gồm:

- ApiCallDuration: thời gian toàn logical call.
- ApiCallSuccessful: logical call thành công hay thất bại.
- RetryCount: số retry của logical call; giá trị 0 nghĩa là không retry.
- BackoffDelayDuration: thời gian SDK chờ trước một attempt.
- ErrorType: phân loại attempt, trong đó có Throttling, ServerError, ConfiguredTimeout, IO và Other.
- AwsRequestId và AwsExtendedRequestId: định danh request phía AWS, phù hợp để tra cứu log/trace.

SDK metrics mặc định bị tắt. Có thể dùng CloudWatchMetricPublisher cho ứng dụng chạy lâu dài hoặc publisher khác phù hợp với môi trường. AWS CRT-based S3 client hiện có giới hạn về hỗ trợ SDK metrics; xác minh client variant trước khi phụ thuộc vào telemetry này.

Ví dụ gắn một publisher vào service client:

~~~java
import software.amazon.awssdk.metrics.MetricPublisher;
import software.amazon.awssdk.services.s3.S3Client;

MetricPublisher publisher = createMetricPublisher();

S3Client s3 = S3Client.builder()
        .overrideConfiguration(config ->
                config.addMetricPublisher(publisher))
        .build();
~~~

createMetricPublisher() đại diện cho publisher được chọn và cấu hình theo tài liệu AWS SDK. Đóng publisher theo vòng đời ứng dụng khi publisher triển khai AutoCloseable; không tạo publisher mới cho từng request.

### 10.2. Azure SDK for Java

Azure SDK sử dụng HTTP pipeline và retry policy trong Azure Core. Một số cách quan sát:

- Dùng **Micrometer Timer/Counter ở wrapper ứng dụng** để đo logical-call latency và final outcome.
- Dùng distributed tracing/OpenTelemetry để liên kết operation ứng dụng với request tới Azure.
- HTTP logging mức BASIC có thể cung cấp method, URL đã sanitize, số lần thử, response code và content length để debug.
- Azure Monitor/service metrics giúp quan sát throttling và tình trạng dịch vụ ở phía cloud.

HTTP logging của Azure SDK được thiết kế cho debug. Microsoft không khuyến nghị dựa vào format log hoặc context key để tạo alert/monitoring ổn định; hãy dùng distributed tracing và metrics có contract rõ ràng.

Khi cấu hình retry cho Azure Storage SDK, xem xét RequestRetryOptions/retry policy phù hợp với client. Giữ giới hạn attempts và thời gian tổng thể, đồng thời tôn trọng thông tin retry từ dịch vụ. Nếu cần metric số lần thử ở cấp SDK, xác minh API telemetry của đúng thư viện/version đang dùng; không parse log tự do thành counter production.

### 10.3. Google Cloud Java client libraries

Google Cloud Java client libraries có thể phát telemetry qua OpenTelemetry khi được bật:

- gcp.client.request.duration: metric thời lượng request và tốc độ request.
- Trace ở tầng HTTP/gRPC.
- Log DEBUG cho các lần request transport thất bại, kể cả trường hợp cuối cùng retry thành công.

Retry settings của Google Cloud Java thường dùng exponential backoff và jitter. Cần đặt MaxAttempts hoặc TotalTimeout để giới hạn operation; không cấu hình retry vô hạn.

RESOURCE_EXHAUSTED thường là dấu hiệu cần xem xét quota/rate limit, còn UNAVAILABLE chỉ ra dịch vụ tạm thời không khả dụng và không tự động đồng nghĩa throttling. Hãy giữ error classification ở adapter theo API cụ thể.

## 11. Truy vấn metric và xây dashboard

Giả sử Prometheus nhận các metric Micrometer:

- cloud_dependency_duration_seconds_bucket
- cloud_dependency_calls_total
- cloud_dependency_errors_total
- cloud_dependency_throttled_calls_total
- cloud_dependency_retries_total

Tên thực tế được normalize theo registry và naming convention. Hãy kiểm tra /actuator/prometheus trước khi viết query.

### 11.1. p95 latency theo provider/service/operation

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, service, operation) (
    rate(cloud_dependency_duration_seconds_bucket[5m])
  )
)
~~~

Query này tính p95 từ histogram đã tổng hợp giữa các instance. Dùng rate trên bucket counter và giữ label le để hàm histogram_quantile tính phân vị.

### 11.2. Final error rate

~~~promql
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total{outcome="error"}[5m])
)
/
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total[5m])
)
~~~

Đây là tỷ lệ logical calls thất bại cuối cùng. Cần xử lý trường hợp mẫu số bằng 0 trong dashboard/alert, ví dụ dùng clamp_min hoặc điều kiện có traffic.

### 11.3. Throttle rate

~~~promql
sum by (provider, service, operation) (
  rate(cloud_dependency_throttled_calls_total[5m])
)
/
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total[5m])
)
~~~

Metric throttled_calls nên tăng tối đa một lần trên mỗi logical call có ít nhất một throttle response. Nếu counter tăng mỗi attempt, mẫu số phải là attempt counter thay vì logical-call counter.

### 11.4. Retry rate

~~~promql
sum by (provider, service, operation) (
  rate(cloud_dependency_retries_total[5m])
)
/
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total[5m])
)
~~~

Giá trị 0,15 nghĩa là trung bình có 0,15 retry bổ sung trên mỗi logical call trong cửa sổ quan sát; nó không có nghĩa 15% call thất bại. Có thể hiển thị cùng final error rate để thấy retry đang cứu các call hay chỉ kéo dài lỗi.

### 11.5. Bảng dashboard nên có

| Panel | Group by | Dùng để |
|---|---|---|
| p50/p95/p99 logical latency | provider, service, operation | So sánh trải nghiệm và phần đuôi chậm |
| Logical call throughput | provider, service, operation | Biết lượng thao tác theo thời gian |
| Final error rate | provider, service, operation, error_type | Phát hiện lỗi người dùng cuối |
| Throttled call/attempt rate | provider, service, operation | Phát hiện quota/capacity |
| Retry per call | provider, service, operation, reason | Phát hiện retry tăng trước khi error rate tăng |
| Backoff duration | provider, service, operation | Nhận biết thời gian chờ do retry |
| Request/attempt IDs trong trace | trace/request | Điều tra một operation cụ thể |

## 12. SLO và cảnh báo

SLO nên dựa trên yêu cầu nghiệp vụ. Ví dụ một API tạo báo cáo có thể đặt mục tiêu:

- 99% logical calls tới object storage hoàn tất dưới 1 giây.
- Final error rate dưới 0,5% trong cửa sổ 30 phút.
- Throttle rate dưới 0,1% trong điều kiện tải bình thường.
- Retry trung bình dưới 0,05 lần trên mỗi logical call.

Đây là số liệu ví dụ, không phải chuẩn chung cho mọi dịch vụ. Tải lớn, kích thước object, vùng cloud, tier storage và loại operation đều ảnh hưởng SLO.

Một số cảnh báo nên kết hợp nhiều tín hiệu:

- **p95 tăng và retry tăng:** dependency đang chậm hoặc throttling khiến SDK phải thử lại.
- **Throttling tăng nhưng final error thấp:** SDK đang che giấu một vấn đề quota/capacity; xử lý trước khi hết retry.
- **Final error tăng và retry exhausted tăng:** retry không còn khắc phục được lỗi.
- **Latency tăng nhưng throttle thấp:** điều tra network, DNS, connection pool, serialization hoặc server latency.
- **Error rate tăng riêng ở một operation:** kiểm tra permission/resource path hoặc payload của operation đó.

Không alert chỉ vì một request đơn lẻ bị 429. Dùng rate, thời gian kéo dài, error budget và mức độ ảnh hưởng nghiệp vụ để tránh cảnh báo nhiễu.

## 13. Cardinality, bảo mật và dữ liệu nhạy cảm

Metric label được nhân với mỗi tổ hợp giá trị. Nếu đưa requestId, blobName, bucketName, customerId hoặc URL vào label, số time series có thể tăng rất nhanh.

**Nên dùng label có tập giá trị nhỏ và ổn định:**

- provider: aws, azure, gcp.
- service: s3, blob, queue, pubsub.
- operation: get_object, upload, send_message.
- outcome: success, error.
- error_type: throttled, timeout, authorization, not_found, server, network, other.
- status_class: 2xx, 4xx, 5xx, unknown.

**Không dùng làm metric label:**

- Request ID, trace ID, correlation ID.
- Account, project, subscription, bucket, container hoặc object name nếu số lượng không giới hạn.
- Customer/user/tenant ID.
- Exception message, URL đầy đủ, token, SAS hoặc credential.

Request ID và trace ID hữu ích trong **log/trace** để điều tra một call cụ thể, nhưng không nên làm dimension của metric. Không log Authorization header, access token, SAS query string hoặc nội dung nhạy cảm của message/object.

## 14. Tránh đo trùng và hiểu sai retry

Một call có thể được đo ở nhiều lớp:

1. HTTP server metric đo request tới Spring Boot.
2. Service metric đo nghiệp vụ generate_report.
3. Cloud dependency metric đo logical SDK call.
4. SDK telemetry đo từng request/attempt.
5. Provider-side metric đo dịch vụ ở cloud.

Đây là các góc nhìn khác nhau, không phải metric trùng nếu tên và ranh giới rõ ràng. Trùng lặp xảy ra khi cùng một operation bị instrument hai lần ở cùng tầng, ví dụ vừa dùng Spring auto-instrumentation vừa thêm @Observed lên một method đã được instrument tự động.

Các quy tắc:

- Ghi rõ metric nào đo logical call, metric nào đo attempt.
- Không cộng RetryCount của SDK vào counter retry do ứng dụng tự ghi.
- Không đếm một final error thành nhiều logical errors chỉ vì có nhiều attempt lỗi.
- Không bọc SDK auto-retry bằng một vòng retry ứng dụng khác nếu chưa tính tổng attempts và tổng timeout.
- Dùng trace span cha/con để thấy request controller → service → cloud SDK.

Nếu SDK đã retry nội bộ, Timer bọc ngoài SDK sẽ đo thời gian tổng; muốn đo attempt cần telemetry của SDK hoặc HTTP pipeline. Nếu ứng dụng tự retry, instrument mỗi retry ở đúng nơi policy quyết định attempt tiếp theo.

## 15. Kiểm thử metric và retry behavior

Một bộ test nên xác minh cả dữ liệu metric lẫn hành vi retry:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Cloud call thành công ngay lần đầu | Calls tăng 1, errors 0, retries 0 |
| Call thất bại cuối cùng | Calls tăng 1, errors tăng 1 |
| Attempt đầu throttle, attempt sau thành công | Logical call success; throttle/retry attempt tăng theo quy ước |
| Hết retry sau nhiều lỗi | Một final error cho logical call; retry count bằng số lần thử bổ sung |
| Permission denied | Phân loại authorization; không retry vô ích |
| Timeout | Phân loại timeout; tổng thời gian không vượt ngân sách đã đặt |
| Retry-After có giá trị | Retry không diễn ra trước thời điểm dịch vụ yêu cầu |
| Không có Retry-After | Backoff có giới hạn và jitter |
| Một request có ID duy nhất | ID chỉ xuất hiện ở trace/log, không tạo metric series riêng |
| Nhiều Pod cùng chạy | Histogram có thể tổng hợp và percentile được tính trên nhóm Pod |

### 15.1. Kiểm tra Timer bằng SimpleMeterRegistry

Trong unit test, có thể dùng SimpleMeterRegistry để kiểm tra metric được ghi nhận:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CloudOperationMetricsTest {
    @Test
    void recordsSuccessfulLogicalCall() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CloudOperationMetrics metrics = new CloudOperationMetrics(registry);

        Boolean result = metrics.record(
                "azure",
                "blob",
                "upload",
                () -> Boolean.TRUE,
                ex -> new CloudOperationMetrics.Failure(
                        "other", "unknown", false));

        assertEquals(Boolean.TRUE, result);
        assertEquals(
                1.0,
                registry.get("cloud.dependency.calls")
                        .tag("provider", "azure")
                        .tag("service", "blob")
                        .tag("operation", "upload")
                        .tag("outcome", "success")
                        .counter()
                        .count());
    }
}
~~~

Test trên xác minh một logical call thành công được đếm đúng một lần. Bổ sung test cho exception, throttle và retry wrapper; kiểm tra tag có tập giá trị giới hạn. Đối với histogram Prometheus, cần integration test với registry tương ứng để xác minh bucket và tên metric đã export.

### 15.2. Kiểm thử trên cloud thật

Emulator hoặc mock không thể xác minh quota, throttling và retry behavior của dịch vụ managed ở tải production. Dùng account/project test để:

- Tạo tải có kiểm soát và quan sát response/error code của dịch vụ.
- Xác minh SDK retry policy, Retry-After, tổng timeout và số attempts.
- So sánh telemetry SDK với metric do ứng dụng ghi.
- Kiểm tra quyền IAM/RBAC và các trường hợp permission denied.
- Xác minh dashboard/alert không làm lộ resource ID hoặc secret.

Không cố tình gây quá tải production để tạo throttling. Dùng quota/load test có giới hạn trong môi trường được phép.

## 16. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| p95 thấp nhưng người dùng vẫn chờ lâu | Chỉ đo attempt cuối, không đo logical call | Đặt Timer bao quanh toàn bộ lời gọi SDK |
| Error rate thấp nhưng latency tăng | SDK retry thành công sau nhiều attempt/backoff | Theo dõi retry count, backoff và throttle rate |
| Throttling không xuất hiện dù có 429 | Chỉ phân loại theo exception class chung hoặc bỏ qua mã dịch vụ | Kiểm tra HTTP/service error code và SDK classification |
| Retry count cao bất thường | Retry lồng nhau ở SDK, service và message worker | Chọn một retry owner, tính tổng attempts và timeout |
| Counter lỗi lớn hơn tổng calls | Đang đếm từng failed attempt như final logical error | Tách attempt errors khỏi final errors |
| p95 giữa các Pod không thể gộp | Dùng client-side percentile thay vì histogram | Xuất histogram và tính percentile ở backend |
| Số time series tăng liên tục | Tag chứa request ID, object name hoặc customer ID | Thay bằng nhóm label hữu hạn |
| Metric Azure không có retry count | SDK telemetry/log không được bật hoặc không có metric ổn định | Dùng wrapper cho retry do ứng dụng sở hữu; dùng tracing/service metrics cho phần SDK |
| Metric Google client library không xuất hiện | Telemetry opt-in chưa bật hoặc exporter chưa cấu hình | Bật OpenTelemetry signals và xác minh exporter |
| AWS SDK metric không có | SDK MetricPublisher mặc định tắt | Cấu hình publisher phù hợp với client variant |
| Retry làm request vượt SLA | Backoff/attempt limit quá lớn hoặc thiếu total timeout | Đặt tổng timeout và số attempts theo ngân sách nghiệp vụ |

## 17. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — S3 chậm:** API gọi GetObject tới AWS S3. p95 latency tăng từ 150 ms lên 1,2 giây, final error rate vẫn thấp. Hãy tìm hiểu retry count, BackoffDelayDuration, attempt error type và connection pool metrics để xác định nguyên nhân.

**Tình huống B — Azure Blob throttling:** Upload Blob bắt đầu trả 429/503 theo đợt. Hãy đo logical-call latency, throttle rate, số lần retry và header Retry-After; đề xuất giới hạn concurrency hoặc điều chỉnh tải trước khi tăng retry.

**Tình huống C — Google Cloud quota:** Gọi một API Google Cloud trả RESOURCE_EXHAUSTED. Hãy phân loại lỗi, quan sát metric gcp.client.request.duration, kiểm tra quota và giới hạn MaxAttempts/TotalTimeout.

**Tình huống D — Retry lồng nhau:** Một service có 3 attempts ở tầng ứng dụng, còn SDK cũng tự retry 3 attempts. Hãy tính số request tối đa có thể phát sinh trong trường hợp xấu và thiết kế lại để có một retry owner rõ ràng.

**Tình huống E — Error rate sai:** Dashboard cho thấy 4% lỗi, nhưng người dùng chỉ thấy 0,2% request thất bại. Hãy xác định dashboard đang đếm failed attempts thay vì final logical calls và tách hai metric.

**Tình huống F — Cardinality:** Một developer thêm blobName và requestId làm tag. Hãy giải thích vì sao số time series tăng nhanh, cách chuyển các ID sang trace/log và giữ metric label ở mức hữu hạn.

### Câu hỏi tự kiểm tra

1. **Logical-call latency khác attempt latency thế nào?** Logical-call latency bao gồm toàn bộ attempts và backoff; attempt latency chỉ đo một request.
2. **Một call có ba attempts thì retry count là bao nhiêu?** Hai, vì attempt đầu tiên không phải retry.
3. **Error rate người dùng cuối nên đếm gì?** Logical calls kết thúc thất bại chia cho tổng logical calls.
4. **Vì sao cần attempt error rate riêng?** Nó phát hiện lỗi đã được SDK retry thành công nhưng vẫn tạo tải và tăng latency.
5. **HTTP 429 luôn có nghĩa throttling ở mọi provider không?** Không; cần xem service error code và semantics của SDK/dịch vụ.
6. **AWS SDK for Java 2.x có thể cung cấp retry metric nào?** RetryCount, cùng BackoffDelayDuration và ErrorType theo telemetry được bật.
7. **Vì sao không parse Azure debug log để tạo alert lâu dài?** Format log/context không phải contract ổn định; dùng metrics và distributed tracing.
8. **Google Cloud Java retry nên có giới hạn nào?** MaxAttempts hoặc TotalTimeout, cùng exponential backoff và jitter.
9. **Vì sao Prometheus nên dùng histogram để tính p95 giữa nhiều Pod?** Bucket có thể tổng hợp; percentile client-side của từng Pod không thể cộng gộp chính xác.
10. **Có nên đưa request ID vào metric tag không?** Không; ID thuộc trace/log vì tạo cardinality rất cao.

## 18. Tổng kết

Đo lường cloud dependency cần phân biệt **logical call** và **request attempt**. Timer bao quanh toàn bộ SDK call cho biết thời gian thực tế mà ứng dụng chờ; histogram giúp tổng hợp p95/p99 giữa nhiều instance; Counter đo logical calls, final errors, throttling và retries theo định nghĩa rõ ràng.

AWS SDK for Java 2.x có thể xuất RetryCount, BackoffDelayDuration và ErrorType qua MetricPublisher. Azure SDK có retry policy, tracing và HTTP logging phục vụ chẩn đoán; không dựa vào log format để làm metric production. Google Cloud Java libraries có telemetry OpenTelemetry và retry settings cần giới hạn bằng MaxAttempts hoặc TotalTimeout.

Kết hợp metric ứng dụng với telemetry SDK và provider, giữ tag cardinality thấp, phân loại throttling theo service semantics và tránh retry lồng nhau. Dashboard cần hiển thị latency, final error rate, throttle rate và retry rate cùng nhau để phát hiện suy giảm trước khi người dùng thấy lỗi.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [AWS SDK for Java 2.x — Publish SDK Metrics](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics.html)
- [AWS SDK for Java 2.x — Metrics Reference](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics-list.html)
- [AWS SDK for Java 2.x — Retry Strategies](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Microsoft Learn — Azure SDK for Java Logging](https://learn.microsoft.com/azure/developer/java/sdk/logging-overview)
- [Microsoft Learn — Azure SDK HTTP Client and Pipeline](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipeline)
- [Google Cloud — Enable Telemetry in Java Client Libraries](https://docs.cloud.google.com/java/docs/observability)
- [Google Cloud — Configure Client-side Retries for Java](https://docs.cloud.google.com/java/docs/client-retries)
