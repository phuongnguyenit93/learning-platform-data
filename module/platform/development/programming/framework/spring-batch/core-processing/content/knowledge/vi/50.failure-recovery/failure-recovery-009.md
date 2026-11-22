# Remote service timeout trong Spring Batch: retry, recovery và tính nhất quán dữ liệu

## 1. Bối cảnh và mục tiêu

Một Spring Batch job có thể đọc dữ liệu và ghi vào database rất ổn định, nhưng vẫn thất bại khi phải gọi một dịch vụ bên ngoài. Ví dụ, job nhập đơn hàng cần gọi dịch vụ khách hàng để bổ sung hạng thành viên; dịch vụ chậm, kết nối bị ngắt hoặc không trả response trong thời gian quy định. Hoặc job thanh toán phải gọi API chuyển tiền: server đã nhận yêu cầu nhưng client timeout trước khi nhận kết quả. Hai tình huống đều xuất hiện dưới dạng “remote service timeout”, song **khả năng retry an toàn hoàn toàn khác nhau**.

Đây là bài **Remote service timeout** trong nhóm *Failure recovery* của module *Spring Batch Core Processing*. Mục tiêu là thiết kế một step xử lý timeout có giới hạn, không tạo vòng retry vô hạn, không bỏ sót dữ liệu quan trọng và không vô tình thực hiện một side effect bên ngoài nhiều lần.

Sau bài này, bạn có thể:

- Phân biệt connect timeout, request/response timeout, deadline nghiệp vụ và lỗi HTTP.
- Phân loại lỗi tạm thời với lỗi không thể tự khắc phục để quyết định retry, skip hay fail.
- Cấu hình timeout trên HTTP client và retry/backoff trong fault-tolerant chunk step.
- Tính tổng thời gian retry để chọn ngưỡng phù hợp với chunk, transaction và SLA.
- Hiểu vì sao timeout khi gọi **HTTP POST** có thể tạo kết quả *không xác định* dù client nhận exception.
- Thiết kế idempotency key, status lookup, quarantine, reconciliation và restart an toàn.
- Kiểm thử bằng lỗi giả lập, timeout có kiểm soát và assert trên `JobExecution`/`StepExecution`.
- Quan sát số lần timeout, độ trễ dịch vụ, thời gian retry và các execution cần xử lý thủ công.

Phần code chính theo **Java 17+, Spring Boot 3.x, Spring Batch 5.2.x**. Trước khi dùng với Spring Batch 6.x cần điều chỉnh API và package tương ứng theo tài liệu phiên bản đang chạy.

---

## 2. Remote service nằm ở đâu trong pipeline?

Một batch step có thể gọi HTTP ở reader, processor hoặc writer:

```text
                  Spring Batch Job
                         │
                         ▼
                  Chunk-oriented Step
                         │
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
    ItemReader      ItemProcessor       ItemWriter
    lấy dữ liệu     bổ sung/kiểm tra     ghi kết quả
        │                │                  │
        │                ▼                  ▼
        │         Remote service A     Remote service B
        │         HTTP GET/profile     HTTP POST/payment
        │                │                  │
        └────────────────┴──────────────────┘
                         │
                  JobRepository
             checkpoint và metadata
```

Timeout ở từng vị trí có ảnh hưởng khác nhau:

| Vị trí gọi remote | Ví dụ | Rủi ro khi timeout |
|---|---|---|
| `ItemReader` | GET trang dữ liệu từ API | Không biết reader đã tiến sang trang mới hay chưa; custom reader cần bảo đảm retry lại cùng dữ liệu |
| `ItemProcessor` | GET thông tin khách hàng | Có thể retry đọc an toàn hơn, miễn GET không có side effect và cùng input |
| `ItemProcessor` | POST cập nhật hệ thống khác | Side effect có thể đã được thực hiện trước timeout; retry có thể tạo bản ghi trùng |
| `ItemWriter` | POST batch invoice | Một số item có thể được chấp nhận, số khác thất bại; rollback của DB local không rollback remote service |
| `Tasklet` | Gửi một lệnh xử lý lớn rồi chờ | Không có item-level retry/skip theo chunk mặc định; phải điều khiển ở tầng tasklet/orchestrator |

**Trong bài này, “remote service” chỉ dịch vụ HTTP mà batch gọi trong quá trình xử lý.** Không nên nhầm với tính năng **Remote Chunking** của Spring Batch, nơi manager và worker trao đổi chunk qua messaging. Remote Chunking có giao thức, transaction và cơ chế lỗi khác, dù cùng cần timeout và idempotency.

### Hai câu hỏi cần trả lời trước khi triển khai

1. **Nếu request timeout, ta có biết server chưa thực hiện hành động không?** Với GET thuần đọc thường dễ retry; với POST chuyển tiền thường không.
2. **Nếu hết số lần retry, toàn bộ job cần FAILED hay item được phép SKIPPED/quarantine?** Đây là quyết định nghiệp vụ về tính đầy đủ dữ liệu, không phải chỉ là tùy chọn kỹ thuật.

---

## 3. Phân biệt các loại timeout và lỗi

### 3.1. Connect timeout

Client không thiết lập được kết nối TCP/TLS trong thời gian giới hạn. Với Java `HttpClient`, `HttpClient.Builder.connectTimeout(Duration)` áp dụng khi cần thiết lập kết nối mới. Kết nối đang được tái sử dụng có thể không cần trải qua bước connect đó.

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
```

Nếu connect timeout xảy ra trước khi gửi request đến server đích thì có cơ sở để retry, nhưng trong hệ thống có proxy/load balancer vẫn cần hiểu đường đi của request. Không nên suy ra mọi exception `IOException` đều là connect timeout.

### 3.2. Request/response timeout

Client đã có thể gửi request nhưng không nhận được response đúng hạn. Trong Java 17:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

`HttpRequest.timeout(...)` giới hạn thời gian hoàn tất request/nhận response theo HTTP client này. Khi hết hạn, `HttpClient.send(...)` có thể ném `HttpTimeoutException`; `HttpConnectTimeoutException` là một kiểu con chuyên cho kết nối.

**Điều không thể kết luận từ response timeout:** server chắc chắn chưa xử lý gì. Khi client không nhận được response, kết quả có thể là:

- Server chưa nhận request.
- Server đã nhận nhưng chưa bắt đầu.
- Server đang xử lý.
- Server đã commit side effect, nhưng response bị mất.
- Proxy trả lỗi dù backend đã hoàn thành.

Với HTTP POST thay đổi trạng thái, tình huống cuối có thể gây **duplicate transaction** nếu client retry mù quáng.

### 3.3. Deadline tổng và timeout từng lần gọi

Nên phân biệt ba giới hạn:

- **Connection timeout:** tối đa chờ thiết lập kết nối.
- **Per-request timeout:** tối đa chờ một lần gọi remote.
- **Overall processing deadline:** tối đa cho phép cho toàn bộ lần xử lý item, kể cả retry/backoff.

Ví dụ per-request timeout 5 giây, tối đa 3 attempts và backoff 0,5 giây rồi 1 giây:

```text
Attempt 1: tối đa 5,0s
Backoff 1:        0,5s
Attempt 2: tối đa 5,0s
Backoff 2:        1,0s
Attempt 3: tối đa 5,0s
------------------------
Tổng gần nhất:   16,5s + overhead
```

Đây là **trần minh họa** nếu mỗi lần chờ hết timeout; các connection/proxy/DNS behavior và timeout khác có thể ảnh hưởng thời gian thực tế. Với chunk 100 item, nếu từng item rơi vào tình trạng đó, step có thể giữ transaction rất lâu. Deadline tổng cần được chọn theo cả SLA của job lẫn khả năng chịu tải của remote service.

### 3.4. HTTP status khác transport timeout

| Tín hiệu | Ý nghĩa thường gặp | Hành động khởi đầu |
|---|---|---|
| `HttpConnectTimeoutException` | Không kết nối được trong hạn | Retry có giới hạn nếu operation an toàn |
| `HttpTimeoutException` | Không nhận response đúng hạn | Kết quả có thể unknown; phân biệt GET/POST |
| Connection reset / EOF | Mất kết nối trong lúc truyền | Cần xem operation có side effect không |
| HTTP 408 | Request timeout phía HTTP server/proxy | Thường là ứng viên retry có giới hạn |
| HTTP 429 | Bị rate limit | Backoff, tôn trọng `Retry-After` nếu có |
| HTTP 502/503/504 | Lỗi gateway/service tạm thời | Retry có giới hạn hoặc circuit breaker |
| HTTP 500 | Internal server error | Có thể tạm thời, nhưng side effect có thể đã xảy ra |
| HTTP 400/422 | Request/schema/business validation sai | Thường fail/quarantine, không retry vô ích |
| HTTP 401/403 | Authentication/authorization sai | Dừng và sửa cấu hình/quyền; không retry liên tục |
| HTTP 404 | Không có resource | Theo hợp đồng: fail, chờ consistency, hoặc skip được phép |
| HTTP 409 | Conflict | Cần tra trạng thái/idempotency; không có một quy tắc retry chung |
| HTTP 202 | Đã chấp nhận xử lý bất đồng bộ | Poll trạng thái theo correlation ID; không coi là hoàn tất ngay |

Phân loại trong bảng là điểm bắt đầu. Hợp đồng cụ thể của remote API mới quyết định exception nào được retry và liệu việc retry có an toàn.

---

## 4. Chọn chính sách recovery trước khi viết code

Một ma trận quyết định đơn giản:

```text
Remote call lỗi hoặc timeout
           │
           ▼
Operation chỉ đọc / idempotent?
   ├── Có ──► Lỗi tạm thời?
   │             ├── Có ──► Retry + backoff + giới hạn
   │             └── Không ─► Fail hoặc skip hợp đồng
   │
   └── Không / không chắc
                 │
                 ▼
       Có idempotency key và
       API tra cứu kết quả?
                 │
          ├── Có ──► Reconcile kết quả → retry có kiểm soát
          └── Không ─► Dừng/đưa vào trạng thái UNKNOWN
                       để kiểm tra hoặc bù trừ
```

### Các kết quả sau khi hết retry

- **FAILED:** dữ liệu bắt buộc chưa xử lý được. Dừng step/job và giữ checkpoint để restart khi dependency hồi phục.
- **SKIPPED:** nghiệp vụ cho phép bỏ một số item lỗi và chấp nhận output thiếu item. Cần audit/quarantine để biết item nào bị bỏ.
- **QUARANTINED:** tách bản ghi lỗi vào kho xử lý sau, ghi nguyên nhân/correlation key và tiếp tục nếu hợp đồng cho phép.
- **PENDING_CONFIRMATION:** request có thể đã tạo side effect, cần tra cứu kết quả từ remote API trước khi xử lý tiếp.
- **STOPPED:** có yêu cầu dừng có kiểm soát, khác với sự cố ném exception.
- **RETRIED_LATER:** cho quay lại queue/job khác sau cooldown, nhưng phải giữ business key để không xử lý lặp.

Không được chọn `skip` chỉ để job hiển thị `COMPLETED`. Nếu một batch chuyển tiền 1.000 bản ghi mà bỏ 3 giao dịch timeout chưa xác định, trạng thái completed không nói lên nghĩa vụ thanh toán đã được hoàn tất.

---

## 5. Ví dụ xuyên suốt: GET service khách hàng từ ItemProcessor

### 5.1. Yêu cầu

Job đọc các khoản thanh toán từ input, gọi dịch vụ khách hàng qua **HTTP GET** để lấy hạng thành viên, rồi ghi dữ liệu đã bổ sung.

Giả định của ví dụ:

- GET `/customers/{customerId}` là operation đọc, không tạo side effect.
- Dịch vụ trả JSON, ví dụ `{"tier":"GOLD"}`.
- `408`, `429` và một số `5xx` là lỗi tạm thời.
- `401/403/404` và JSON không đúng schema là lỗi không tự hồi phục trong cùng lần gọi.
- Connection timeout 2 giây, request timeout 5 giây.
- Spring Batch retry tối đa ba lần thử cho lỗi transient, có backoff.
- Hết retry thì step **FAILED**; không bỏ giao dịch khi chưa có quyết định nghiệp vụ khác.

Ví dụ này sử dụng Java `java.net.http.HttpClient` thay vì phụ thuộc vào cấu hình timeout riêng của một HTTP client thứ ba. Nếu dự án dùng Spring `RestClient`, WebClient, Feign hoặc Apache HttpClient, nguyên tắc phân loại timeout/idempotency vẫn tương tự nhưng API cấu hình sẽ khác.

### 5.2. Dependency

Gradle với Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    runtimeOnly 'com.h2database:h2'  // ví dụ cho JobRepository cục bộ

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

`spring-batch-core` dùng cơ chế retry dựa trên Spring Retry trong dòng 5.x. Khi dự án có quản lý dependency khác với starter Boot, kiểm tra sự hiện diện của thư viện Spring Retry và version tương thích với Spring Batch.

### 5.3. Model và exception có chủ đích

Đặt trong package `com.example.batch.remote`:

```java
package com.example.batch.remote;

import java.math.BigDecimal;

public final class RemoteModels {
    private RemoteModels() {}

    public record Payment(
            long id, long customerId, BigDecimal amount) {}

    public record EnrichedPayment(
            long id, long customerId,
            BigDecimal amount, String customerTier) {}

    public record CustomerResponse(String tier) {}

    public static class TransientRemoteException
            extends RuntimeException {
        public TransientRemoteException(String message) {
            super(message);
        }

        public TransientRemoteException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class PermanentRemoteException
            extends RuntimeException {
        public PermanentRemoteException(String message) {
            super(message);
        }

        public PermanentRemoteException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class RemoteCallInterruptedException
            extends RuntimeException {
        public RemoteCallInterruptedException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

**Vì sao cần exception riêng?** Nếu cấu hình retry trên `RuntimeException.class` hoặc `Exception.class`, một lỗi authentication, lỗi JSON hoặc bug trong processor cũng có thể được retry nhiều lần. Exception được phân loại giúp policy của batch sát với tính chất lỗi.

### 5.4. HTTP client với timeout

```java
package com.example.batch.remote;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RemoteHttpConfig {

    @Bean
    HttpClient customerHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }
}
```

Dùng client chia sẻ hợp lý giúp tái sử dụng connection. Java `HttpClient` được thiết kế dùng lại cho nhiều request; không cần tạo client mới cho từng item. Nếu hệ thống cần mTLS, proxy, auth token hoặc connection pool tuning, cấu hình tại tầng client tương ứng.

### 5.5. Processor chuyển lỗi remote thành exception phù hợp

```java
package com.example.batch.remote;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.batch.item.ItemProcessor;

import com.example.batch.remote.RemoteModels.Payment;
import com.example.batch.remote.RemoteModels.EnrichedPayment;
import com.example.batch.remote.RemoteModels.CustomerResponse;
import com.example.batch.remote.RemoteModels.TransientRemoteException;
import com.example.batch.remote.RemoteModels.PermanentRemoteException;
import com.example.batch.remote.RemoteModels.RemoteCallInterruptedException;

public final class CustomerEnrichmentProcessor
        implements ItemProcessor<Payment, EnrichedPayment> {

    private final HttpClient http;
    private final ObjectMapper json;
    private final URI baseUri;

    public CustomerEnrichmentProcessor(
            HttpClient http, ObjectMapper json, URI baseUri) {
        this.http = http;
        this.json = json;
        this.baseUri = baseUri;

        // URI phải kết thúc bằng "/" để resolve(customerId)
        // được gắn đúng vào đường dẫn /api/customers/.
        if (!baseUri.toString().endsWith("/")) {
            throw new IllegalArgumentException(
                    "customer base URI must end with /");
        }
    }

    @Override
    public EnrichedPayment process(Payment payment) {
        URI uri = baseUri.resolve(
                Long.toString(payment.customerId()));

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "application/json")
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            int status = response.statusCode();

            if (status == 200) {
                CustomerResponse customer;
                try {
                    customer = json.readValue(
                            response.body(), CustomerResponse.class);
                } catch (JsonProcessingException invalidBody) {
                    throw new PermanentRemoteException(
                            "Invalid customer JSON: id="
                                    + payment.customerId(),
                            invalidBody);
                }

                if (customer.tier() == null
                        || customer.tier().isBlank()) {
                    throw new PermanentRemoteException(
                            "Missing tier: customerId="
                                    + payment.customerId());
                }

                return new EnrichedPayment(
                        payment.id(),
                        payment.customerId(),
                        payment.amount(),
                        customer.tier());
            }

            if (status == 408 || status == 429
                    || (status >= 500 && status <= 599)) {
                throw new TransientRemoteException(
                        "Temporary customer-service HTTP " + status);
            }

            throw new PermanentRemoteException(
                    "Non-retryable customer-service HTTP " + status);

        } catch (HttpTimeoutException timeout) {
            throw new TransientRemoteException(
                    "Customer-service timeout: customerId="
                            + payment.customerId(), timeout);

        } catch (IOException transportError) {
            throw new TransientRemoteException(
                    "Customer-service I/O failure: customerId="
                            + payment.customerId(), transportError);

        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new RemoteCallInterruptedException(
                    "Customer-service call interrupted", interrupted);
        }
    }
}
```

Một số chủ ý:

1. `HttpTimeoutException` được bắt trước `IOException` vì timeout là subclass của `IOException`.
2. `InterruptedException` khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` và **không** được phân loại retryable theo policy mặc định của ví dụ. Điều này cho phép luồng xử lý phản hồi yêu cầu dừng.
3. Lỗi JSON hỏng hoặc thiếu trường nghiệp vụ chuyển thành `PermanentRemoteException`, tránh retry vô ích.
4. `408/429/5xx` được xem là transient **trong ví dụ GET**. Khi API có lỗi khác, cần đối chiếu hợp đồng và điều chỉnh classifier.
5. Đoạn code gom mọi `IOException` không thuộc timeout thành transient cho dễ hiểu. Production nên phân biệt SSL certificate/configuration failure, DNS name sai cố định hoặc lỗi xác thực TLS (không retry liên tục) với lỗi I/O mạng thoáng qua.
6. Không log nguyên response body hoặc token ở lỗi; metadata như `customerId`, HTTP status và correlation ID là đủ để chẩn đoán mà hạn chế lộ dữ liệu.
7. URI ghép từ ID số, không lấy đường dẫn tùy ý từ file để gọi bất kỳ host nào. Với API thực tế phải bảo vệ service base URL và credential.

**Cần nhớ:** ví dụ chỉ gọi GET đọc dữ liệu. Đối với POST ghi tiền, không nên sao chép y nguyên bộ retry này khi chưa có idempotency và cơ chế xác minh kết quả.

### 5.6. Bean processor và fault-tolerant step

```java
package com.example.batch.remote;

import java.net.URI;
import java.net.http.HttpClient;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

import com.example.batch.remote.RemoteModels.Payment;
import com.example.batch.remote.RemoteModels.EnrichedPayment;
import com.example.batch.remote.RemoteModels.TransientRemoteException;

@Configuration(proxyBeanMethods = false)
public class EnrichmentStepConfig {

    @Bean
    CustomerEnrichmentProcessor customerEnrichmentProcessor(
            HttpClient customerHttpClient,
            ObjectMapper mapper,
            @Value("${remote.customer.base-url}") String baseUrl) {
        return new CustomerEnrichmentProcessor(
                customerHttpClient, mapper, URI.create(baseUrl));
    }

    @Bean
    ExponentialBackOffPolicy remoteBackOffPolicy() {
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();
        policy.setInitialInterval(500L);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(2_000L);
        return policy;
    }

    @Bean
    Step enrichmentStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            ItemReader<Payment> paymentReader,
            CustomerEnrichmentProcessor customerEnrichmentProcessor,
            ItemWriter<EnrichedPayment> paymentWriter,
            ExponentialBackOffPolicy remoteBackOffPolicy) {

        return new StepBuilder("enrichmentStep", repository)
                .<Payment, EnrichedPayment>chunk(50, transactionManager)
                .reader(paymentReader)
                .processor(customerEnrichmentProcessor)
                .writer(paymentWriter)
                .faultTolerant()
                .retry(TransientRemoteException.class)
                .retryLimit(3)
                .backOffPolicy(remoteBackOffPolicy)
                .build();
    }
}
```

Cấu hình `application.yml`:

```yaml
remote:
  customer:
    base-url: "https://customers.internal.example/api/customers/"

spring:
  batch:
    job:
      enabled: false
```

Tên host là ví dụ. Dự án cần tự cung cấp bean `paymentReader`, `paymentWriter` và một `Job` chứa `enrichmentStep`; ví dụ tập trung vào HTTP client, processor và chính sách retry.

**Ý nghĩa chính sách:**

- `.faultTolerant()` kích hoạt cơ chế retry/skip theo exception trong chunk step.
- `.retry(TransientRemoteException.class)` chỉ cho retry nhóm lỗi đã phân loại là tạm thời.
- `.retryLimit(3)` trong Spring Batch 5.2 giới hạn **tối đa ba lần thử tính cả lần đầu** cho một item: có thể retry thêm tối đa hai lần.
- `.backOffPolicy(...)` tránh gửi lại ngay, tăng thời gian đợi giữa các lần thử tới giới hạn.
- Không khai báo `.skip(...)` nên sau khi hết retry, exception sẽ làm step thất bại theo cơ chế fault tolerance thông thường.
- `RemoteCallInterruptedException` và `PermanentRemoteException` không nằm trong nhóm retry, nên lỗi không được thử đi thử lại liên tục.

Trong thực tế cần phối hợp với timeout của transaction và SLA. Ví dụ chunk 50 item nhưng mỗi item có thể dùng 16,5 giây lúc dịch vụ lỗi; tổng thời gian chunk có thể rất dài, gây giữ transaction/database resources và checkpoint muộn.

### 5.7. Tại sao không đặt retry ở cả ba tầng?

Một lỗi thiết kế phổ biến là:

```text
HTTP client auto retry:      3 attempts
Spring RetryTemplate:        3 attempts
Spring Batch faultTolerant:  3 attempts
------------------------------------------------
Một item có thể tạo tới 27 lần gọi remote
```

Tổng số lần gọi chỉ là mô hình worst-case nếu các tầng retry lồng nhau đầy đủ, nhưng nó minh họa **retry amplification**. Trong cùng một flow, hãy xác định nơi chịu trách nhiệm retry chính và giới hạn rõ request count, elapsed budget, circuit breaker và concurrency.

Nếu HTTP client của tổ chức đã retry 503 tự động, khi cấu hình Spring Batch cần tính cả phần retry đó vào ngân sách cuối cùng. Không để các retry policy độc lập nhân lên không kiểm soát.

---

## 6. Tính thời gian retry và backoff trước khi chọn chunk size

### 6.1. Mỗi item có thể “giữ” transaction bao lâu?

Giả sử `chunkSize=50`, mỗi request timeout 5 giây, tối đa 3 attempts và backoff 0,5 giây, 1 giây:

```text
Per item ≈ 5 + 0.5 + 5 + 1 + 5 = 16.5 seconds

50 items × 16.5 seconds ≈ 825 seconds ≈ 13.75 minutes
```

Đó là trường hợp xấu theo mô hình, chưa tính database, writer, overhead và các thay đổi trong retry logic. Với một chunk-oriented step, remote call có thể diễn ra **bên trong transaction của chunk**; một chunk giữ transaction nhiều phút là rủi ro với lock, pool, timeout và rollback.

### 6.2. Những cách giảm ảnh hưởng

- Chọn connect/request timeout ngắn theo latency SLO thực tế của dịch vụ.
- Giới hạn retries theo lỗi có khả năng hồi phục; tránh retry 400/401/422.
- Dùng backoff có giới hạn, có thể thêm jitter để giảm các worker retry cùng lúc.
- Xem xét giảm chunk size cho bước gọi remote chậm.
- Giới hạn số request đồng thời đến cùng một service.
- Áp dụng circuit breaker/bulkhead khi service liên tục lỗi.
- Nếu quy trình cho phép, tách remote interaction thành bước riêng hoặc kiến trúc outbox/asynchronous reconciliation.
- Nếu toàn bộ retry budget vượt SLA của job, cân nhắc fail sớm để scheduler xử lý ở lần chạy sau.

### 6.3. Retry-After với HTTP 429 và 503

Một service có thể trả header `Retry-After` quy định thời gian nên đợi trước khi gọi lại. Ví dụ ở mức HTTP:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

Ví dụ `ExponentialBackOffPolicy` ở trên không tự động đọc `Retry-After`. Muốn tuân thủ header, tầng HTTP adapter phải trích xuất/chuyển metadata retry và một custom policy hoặc bộ điều phối phải xử lý. Cần giới hạn tổng thời gian chờ để không giữ transaction vô hạn.

Nếu `Retry-After` rất dài (vài phút/giờ), thường tốt hơn là **dừng/requeue batch để chạy sau**, thay vì giữ một transaction, connection và worker thread ngủ hết thời gian đó.

---

## 7. Remote write và kết quả không xác định: nguy cơ lớn nhất

Tình huống chuyển tiền:

1. Batch gửi `POST /transfers` để tạo giao dịch `T-123`.
2. Remote service xác nhận trong database của nó.
3. Response bị mất hoặc chậm, HTTP client hết hạn.
4. Spring Batch thấy `HttpTimeoutException`.
5. Nếu client tự retry POST không có idempotency, remote service có thể tạo giao dịch `T-123` lần thứ hai.

```text
Spring Batch                     Payment API
     │                                │
     │ POST transfer T-123            │
     ├───────────────────────────────►│
     │                                ├── Commit T-123
     │       response bị mất          │
     │◄ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │                                │
     ├─ Timeout                       │
     ├─ Retry POST                    │
     ├───────────────────────────────►│
     │                                └── Có thể commit T-123 lần nữa
```

**Một client timeout không phải bằng chứng server rollback.** Transaction Spring Batch bao quanh chunk không kéo theo database của remote service, hệ thống HTTP, broker hoặc object storage vào cùng một giao dịch phân tán.

### 7.1. Idempotency key

Giải pháp thường dùng là gửi một khóa idempotency được xây từ **định danh nghiệp vụ ổn định**, ví dụ `transferId`:

```http
POST /transfers HTTP/1.1
Content-Type: application/json
Idempotency-Key: transfer:T-123

{"transferId":"T-123","amount":"125.00","currency":"USD"}
```

Server phải bảo đảm theo hợp đồng:

1. Lần đầu nhận key, thực hiện giao dịch và lưu kết quả cùng key một cách có tính nguyên tử phù hợp.
2. Lần sau cùng key và cùng nội dung, trả lại kết quả đã lưu hoặc trạng thái hiện tại; **không tạo giao dịch thứ hai**.
3. Cùng key nhưng payload khác phải bị từ chối (ví dụ 409) thay vì âm thầm xử lý nội dung mới.
4. Có retention window đủ dài cho retry/restart/backfill của batch.
5. Kết quả được tra cứu qua key hoặc business transaction ID nếu response bị mất.

**Chỉ thêm header `Idempotency-Key` ở client không đủ.** Remote API bắt buộc phải implement và cam kết semantics tương ứng.

### 7.2. Không dùng random key mỗi lần thử

Sai:

```java
String key = UUID.randomUUID().toString();
// Mỗi retry tạo key khác → server coi là yêu cầu mới.
```

Đúng hơn:

```java
String key = "transfer:" + transfer.businessId();
// Cùng giao dịch có cùng key qua retry/restart.
```

Nếu dùng `jobExecutionId` để tạo key, cần chú ý restart của cùng `JobInstance` thường tạo **JobExecution mới**, có thể dẫn tới key khác. Khóa idempotency cho side effect nên xuất phát từ business ID hoặc bộ định danh kỳ dữ liệu/item mà nghiệp vụ bảo đảm ổn định.

### 7.3. Reconciliation trước khi retry

Khi timeout POST, flow khuyến nghị:

```text
Gửi POST với idempotency key ổn định
                   │
                   ▼
      Nhận response rõ ràng?
          ├── 2xx success → ghi kết quả
          ├── 4xx permanent → fail/quarantine
          └── timeout/unknown
                   │
                   ▼
     GET status bằng transaction ID/key
          │
          ├── CONFIRMED → ghi nhận thành công,
          │                không POST lần nữa
          │
          ├── REJECTED  → xử lý business failure
          │
          ├── NOT_FOUND → retry POST chỉ nếu
          │                server cam kết safe
          │
          └── UNKNOWN   → giữ pending,
                           retry inquiry sau,
                           hoặc yêu cầu xử lý thủ công
```

Nếu status endpoint eventual consistency, `NOT_FOUND` ngay sau POST chưa chứng minh request chưa được xử lý. Phải theo SLA consistency của server và chính sách giao tiếp giữa hai hệ thống.

### 7.4. Outbox và bất đồng bộ

Với side effect quan trọng, thay vì gọi HTTP bên trong transaction của chunk, một mẫu kiến trúc là:

1. Spring Batch ghi trạng thái và một bản ghi outbox trong **cùng database transaction**.
2. Worker gửi outbox message/request tới remote service.
3. Worker dùng idempotency key và lưu kết quả ACK/correlation ID.
4. Reconciliation xử lý các request `UNKNOWN` hoặc chưa được ACK.
5. Job/step tổng kết khi toàn bộ item bắt buộc đạt trạng thái cuối.

Outbox không tự tạo exactly-once delivery; nó giúp điều phối reliable delivery và kết hợp với idempotency ở receiver để kiểm soát xử lý trùng.

### 7.5. Nếu remote API không hỗ trợ idempotency

Đừng tự bật retry vô điều kiện cho lệnh thanh toán/đặt vé/gửi hàng. Có thể cần:

- Quy trình query trạng thái qua business reference.
- Bảng trạng thái `PENDING_CONFIRMATION`/`UNKNOWN_OUTCOME`.
- Người vận hành xác minh trước khi gửi lại.
- API bù trừ (*compensating action*) nếu hợp đồng cho phép.
- Thiết kế lại integration contract để có idempotency hoặc correlation ID.

Trong tình huống không thể xác định outcome, **fail hoặc tạm dừng xử lý** có thể an toàn hơn một job “COMPLETED” nhưng đã nhân đôi giao dịch.

---

## 8. Retry, skip và fail trong Spring Batch

### 8.1. Retry transient, fail permanent

Với job dữ liệu bắt buộc, cấu hình ở phần 5 đã là lựa chọn khởi đầu tốt:

```java
.faultTolerant()
.retry(TransientRemoteException.class)
.retryLimit(3)
.backOffPolicy(backOffPolicy)
```

Khi exception transient tiếp tục xuất hiện sau ngân sách thử, step sẽ thất bại nếu không có skip/recovery policy phù hợp. `JobExecution` cuối cùng thường là `FAILED`, lưu exception và trạng thái theo metadata.

### 8.2. Skip chỉ khi hợp đồng cho phép

Giả sử job gửi email gợi ý không bắt buộc và có thể cho qua một số record thiếu customer profile. Khi đó có thể thêm:

```java
.faultTolerant()
.retry(TransientRemoteException.class)
.retryLimit(3)
.backOffPolicy(backOffPolicy)
.skip(PermanentRemoteException.class)
.skipLimit(10)
```

**Ý nghĩa:** những item bị lỗi permanent có thể được skip, tối đa 10 item trong phạm vi step theo chính sách mặc định; vượt ngưỡng step sẽ fail. Đây là ví dụ cho dữ liệu không bắt buộc, **không phù hợp mặc định với tiền, thuế hoặc đối soát bắt buộc**.

Không nên skip tất cả `Exception.class` vì có thể che giấu lỗi code, mất dữ liệu hoặc sai cấu hình.

### 8.3. Quarantine bản ghi lỗi

Nếu một record được phép skip, vẫn cần lưu:

- Business item ID và khóa liên kết tới nguồn.
- Job/step execution ID, tên step.
- Loại lỗi, HTTP status, số lần đã thử.
- Thời điểm phát hiện và trạng thái xử lý sau.
- Reference/correlation ID của remote request.
- Payload đã được mask hoặc tham chiếu đến dữ liệu gốc có quyền truy cập.

`SkipListener` có thể ghi nhận item bị skip:

```java
public class RemoteSkipListener
        implements SkipListener<Payment, EnrichedPayment> {

    private final QuarantineService quarantine;

    public RemoteSkipListener(QuarantineService quarantine) {
        this.quarantine = quarantine;
    }

    @Override
    public void onSkipInProcess(Payment item, Throwable error) {
        quarantine.record(
                item.id(),
                "REMOTE_ENRICHMENT",
                error.getClass().getSimpleName());
    }
}
```

Đây là phác thảo cần `Payment`/`EnrichedPayment` và `QuarantineService` từ project. Phải thiết kế lưu quarantine theo transaction/idempotency: callback có thể tham gia đường retry/rollback hoặc bị gọi lại khi restart. Dùng khóa unique phù hợp và tránh ghi một record lỗi nhiều lần.

### 8.4. Đừng nhầm retry count với skip count

Các getter như `StepExecution.getReadSkipCount()`, `getProcessSkipCount()` và `getWriteSkipCount()` thể hiện **item bị bỏ qua** theo giai đoạn, không phải tổng số HTTP request retry. Nếu cần “số lần timeout”, thêm counter/observation cho remote adapter hoặc retry listener, và giữ label có cardinality hợp lý.

Một step hoàn tất với `writeCount=990` và `processSkipCount=10` có thể vẫn là `COMPLETED` theo cấu hình. Báo cáo nghiệp vụ phải hiểu 10 item đó đang ở đâu và có cần xử lý lại hay không.

---

## 9. Remote timeout trong Reader, Processor và Writer

### 9.1. Reader gọi API phân trang

Custom reader dễ mắc lỗi:

```java
@Override
public RemoteItem read() {
    currentPage++;              // Tăng trang trước khi request thành công
    return fetchPage(currentPage); // Timeout → mất trang trước
}
```

Nếu fetch timeout và Spring Batch retry `read()`, state đã tăng có thể khiến lần đọc tiếp theo nhảy sang trang sau, **bỏ sót dữ liệu**.

Hướng an toàn:

```java
@Override
public RemoteItem read() {
    RemoteItem item = fetchNextItem(lastConfirmedPosition);
    if (item == null) {
        return null;
    }
    lastConfirmedPosition = item.position();
    return item;
}
```

Đây chỉ là ý tưởng; reader có nhiều item trên mỗi page cần quản lý page buffer, index trong page, checkpoint và ordering đầy đủ. Nguyên tắc là **không làm mất logical item khi lần fetch thất bại**. Với API cursor token, chỉ lưu token mới sau khi page đã được xử lý/commit theo hợp đồng.

### 9.2. Processor gọi GET

Processor ví dụ ở phần 5 phù hợp vì mỗi item có thể được tra cứu lại bằng customer ID. Vẫn cần xem tính nhất quán dữ liệu: nếu profile của khách hàng thay đổi giữa hai retry, output có thể khác. Khi nghiệp vụ cần snapshot cố định, remote API phải hỗ trợ version/as-of timestamp hoặc ta cần cache một kết quả được kiểm soát.

### 9.3. Writer gửi POST theo chunk

Một writer nhận chunk 100 item có thể đã gửi thành công 60 request rồi timeout ở item thứ 61. Nếu writer ném exception và transaction local rollback, Spring Batch có thể gọi lại write trong quá trình retry/restart. **60 side effect remote đầu tiên không tự rollback**.

Do đó cần một trong các chính sách:

- Remote API hỗ trợ idempotency cho từng item.
- Bulk endpoint hỗ trợ idempotency cho cả batch và trả kết quả từng item.
- Outbox/async delivery để tách commit local khỏi remote call.
- Reconciliation theo item ID và trạng thái remote trước khi retry.

Một writer không có các điều kiện này không thể được làm an toàn chỉ bằng `.retryLimit(3)`.

### 9.4. Tasklet gọi một yêu cầu lâu

`Tasklet` không sử dụng retry item-level của fault-tolerant chunk step theo mặc định. Có thể dùng một policy retry riêng ở tầng Tasklet/service, nhưng phải giới hạn tổng thời gian và có trạng thái `PENDING/UNKNOWN` nếu side effect đã gửi. Tránh ngủ nhiều phút bên trong transaction khi có thể đưa tác vụ dài vào job bất đồng bộ.

---

## 10. Restart sau remote timeout

### 10.1. Spring Batch restart dựa vào metadata

JobRepository lưu `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`. Nếu job thất bại, một lần khởi chạy lại với **cùng identifying JobParameters** có thể tạo `JobExecution` mới cho cùng `JobInstance`, miễn job/step có cấu hình restart phù hợp.

Ví dụ `businessDate=2026-11-15` là identifying parameter cho job nhập ngày đó. Nếu job thất bại do remote service timeout, không thay bằng `businessDate=2026-11-16` chỉ vì hôm sau mới khôi phục. Làm vậy là một instance khác, có thể bỏ sót ngày cũ.

### 10.2. Checkpoint không chứng minh remote side effect đã rollback

Giả sử chunk đọc 100 payment, gọi remote API thành công cho 50 rồi fail ở payment 51. Nếu chunk chưa commit:

- `ExecutionContext` có thể chưa ghi checkpoint mới.
- Local DB transaction có thể rollback.
- Remote API vẫn có thể đã xử lý 50 payment đầu.
- Khi restart, Spring Batch có thể gửi lại 50 payment đó.

Chỉ khi remote write có idempotency/reconciliation phù hợp mới có thể xử lý lại chunk mà không tạo side effect trùng. **Commit của Spring Batch và commit remote API là hai ranh giới khác nhau.**

### 10.3. Tránh tạo JobInstance mới chỉ để bỏ qua trạng thái lỗi

Một workaround sai:

```java
new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("runId", System.currentTimeMillis(), true)
        .toJobParameters();
```

Mỗi runId mới tạo một instance mới, khiến framework không dùng checkpoint/restart của instance cũ và làm mờ lịch sử xử lý một kỳ dữ liệu.

Với job cần retry có kiểm soát, dùng cùng identifying key, theo dõi execution mới và tra cứu outcome của những remote request chưa rõ. Chỉ reprocess-from-scratch khi đã có chính sách nghiệp vụ rõ, bảo đảm idempotency và biết phạm vi dữ liệu đã xử lý.

### 10.4. Có nên tự restart sau khi remote phục hồi?

Có thể, nhưng cần kiểm tra:

- Job được đánh dấu restartable.
- Timeout đã là lỗi transient; dependency có tín hiệu khỏe.
- Không có unknown side effect chưa reconcile.
- Số lần restart theo kỳ vẫn trong ngưỡng vận hành.
- Lịch chạy tiếp theo không xung đột.
- Nhân viên vận hành có thể phân biệt retry item, restart step và backfill kỳ nghiệp vụ.

Không tự cập nhật trực tiếp `BATCH_JOB_EXECUTION.STATUS` để “mở khóa” retry. Việc thay đổi metadata thủ công có thể phá logic recovery; cần dùng API và runbook phù hợp.

---

## 11. Circuit breaker, rate limiting và bulkhead

### 11.1. Circuit breaker

Khi remote service timeout liên tục, gửi hàng nghìn request retry làm dịch vụ càng quá tải. Circuit breaker giúp **fail fast** trong một khoảng thời gian để hệ thống đích phục hồi:

```text
CLOSED: gọi bình thường, thu thập lỗi
      │ lỗi vượt ngưỡng
      ▼
OPEN: từ chối request mới trong cooldown
      │ đủ thời gian
      ▼
HALF_OPEN: cho một số request thử
      │
      ├─ thành công → CLOSED
      └─ tiếp tục lỗi → OPEN
```

Có thể dùng Resilience4j hoặc cơ chế tương tự, nhưng phải phối hợp với Spring Batch retry:

- `CallNotPermittedException` khi circuit mở không nên tự động retry nhanh hàng chục lần.
- Nếu circuit mở lâu, tốt hơn fail/requeue batch thay vì giữ chunk transaction chờ.
- Cần theo dõi tỉ lệ lỗi, open duration và remote recovery.
- Không đặt hai circuit breaker/retry lồng nhau mà không biết tổng request budget.

### 11.2. Rate limiter

Lỗi `429 Too Many Requests` thường cần giảm tốc độ. Nếu batch có tám worker và mỗi worker retry ba lần, hệ thống có thể tạo một đợt retry đồng loạt (*retry storm*). Hãy giới hạn số request mỗi giây, dùng backoff + jitter và tôn trọng quota/`Retry-After` theo hợp đồng.

### 11.3. Bulkhead và concurrency

Giới hạn số request đang bay (*in-flight*) giúp bảo vệ pool, thread và remote service. Dù chunk size là 100, khi 20 partition cùng chạy và mỗi partition gọi HTTP, số request concurrent có thể cao hơn sức chịu tải của remote API. Điều chỉnh concurrency theo remote rate limit, timeout và số kết nối.

### 11.4. SLA tổng

Một service không chỉ cần retry được mà còn cần hoàn thành batch trước deadline. Cần cân bằng:

- Per-request timeout.
- Backoff/cooldown.
- Retry attempts.
- Số item và chunk size.
- Throughput của remote service.
- Thời gian nghỉ giữa các kỳ.
- Thời gian phục hồi và backfill nếu batch FAILED.

Nếu tính toán worst-case vượt SLA, xem xét kiến trúc async, queue và kiểm soát lưu lượng thay vì chỉ tăng timeout.

---

## 12. Observability: biết timeout đang xảy ra ở đâu

### 12.1. Metadata của Spring Batch

Với `JobExplorer`, có thể tìm execution đang chạy hoặc đã thất bại:

```java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    System.out.println(execution.getStatus());
    System.out.println(execution.getExitStatus());

    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
                "%s read=%d write=%d skip=%d rollback=%d%n",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount());
    }
}
```

Các bộ đếm giúp thấy kết quả của step, nhưng **không tự đếm từng lần HTTP timeout/retry**. Cần metric riêng từ remote adapter hoặc retry listener.

### 12.2. Metric gợi ý

| Metric | Kiểu | Cách dùng |
|---|---|---|
| `remote_client_requests_total` | Counter | Tổng request theo service, operation và outcome |
| `remote_client_timeouts_total` | Counter | Timeout theo connect/response |
| `remote_client_retries_total` | Counter | Retry theo service và nhóm lỗi |
| `remote_client_request_duration_seconds` | Histogram/Timer | p95/p99 latency của remote API |
| `remote_client_circuit_state` | Gauge | OPEN/HALF_OPEN/CLOSED theo service |
| `batch_remote_pending_confirmation` | Gauge | Số request cần reconcile outcome |
| `batch_remote_quarantine_total` | Counter | Số item đưa vào quarantine |
| `spring.batch.job/step...` | Built-in meter family | Thời gian job/step/item/chunk của Spring Batch |

Các tên `remote_client_*` trong bảng là **custom metric gợi ý**, không phải tên built-in tự xuất hiện. Khi dùng Micrometer/Prometheus, tên meter có thể được chuẩn hóa khi export, nên hãy kiểm tra series thực tế.

Tránh dùng `customerId`, `paymentId`, URL có ID, error message đầy đủ hoặc `jobExecutionId` như tag của mọi request; chúng tạo cardinality cao hoặc làm lộ dữ liệu. Dùng tag ổn định như service, method, operation, status family và environment.

### 12.3. Log cần có

Ví dụ event chẩn đoán:

```json
{
  "event": "REMOTE_TIMEOUT",
  "jobName": "dailyImportJob",
  "jobExecutionId": 7012,
  "stepName": "enrichmentStep",
  "businessDate": "2026-11-15",
  "service": "customer-service",
  "operation": "GET /customers/{id}",
  "attempt": 2,
  "maxAttempts": 3,
  "timeoutMs": 5000,
  "elapsedMs": 5032,
  "retryable": true,
  "outcome": "UNKNOWN",
  "correlationId": "req-55c7"
}
```

Đây là ví dụ log, không phải dữ liệu hệ thống cụ thể. `outcome=UNKNOWN` thích hợp khi chưa biết server đã xử lý đến đâu; với GET đọc thuần, nó không tạo rủi ro duplicate side effect như POST nhưng vẫn có thể gây khác biệt dữ liệu do thay đổi trạng thái nguồn.

Không log thông tin xác thực, request body nhạy cảm hoặc response chứa dữ liệu cá nhân.

### 12.4. Cảnh báo hữu ích

Tách các loại cảnh báo:

- Tỉ lệ timeout > ngưỡng trong 5 phút.
- Nhiều job cùng thất bại do một dependency.
- Một job không tiến triển lâu vì retry/backoff.
- Circuit breaker mở quá lâu.
- Số `PENDING_CONFIRMATION` hoặc quarantine tăng.
- Job thất bại sát deadline hoặc thiếu kỳ dữ liệu sau outage.

Khi dịch vụ đã phục hồi, vẫn cần đối soát các kỳ bỏ lỡ. Việc error rate trở về 0 không chứng minh dữ liệu thiếu đã được xử lý bù.

---

## 13. Kiểm thử timeout và recovery

Không nên chờ dịch vụ thật bị lỗi rồi mới kiểm tra behavior. Có thể test theo ba cấp:

1. **Unit test classifier/HTTP adapter:** một timeout trở thành exception retryable, 401 trở thành permanent, interrupt được bảo toàn.
2. **Step integration test:** fault tolerance dùng đúng retry limit/backoff, bước fail hoặc skip như mong đợi, metadata phản ánh kết quả.
3. **End-to-end/recovery test:** request POST có idempotency, response mất, restart job và reconciliation không tạo duplicate side effect.

### 13.1. Unit test HTTP processor bằng Mockito

Ví dụ sử dụng Mockito và JUnit Jupiter, mock Java `HttpClient` để ném timeout mà không cần network:

```java
package com.example.batch.remote;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import com.example.batch.remote.RemoteModels.Payment;
import com.example.batch.remote.RemoteModels.TransientRemoteException;

class CustomerEnrichmentProcessorTest {

    @Test
    void convertsHttpTimeoutToRetryableDomainException()
            throws Exception {

        HttpClient client = mock(HttpClient.class);

        when(client.<String>send(
                any(HttpRequest.class),
                org.mockito.ArgumentMatchers
                    .<HttpResponse.BodyHandler<String>>any()))
                .thenThrow(new HttpTimeoutException("simulated"));

        var processor = new CustomerEnrichmentProcessor(
                client,
                new ObjectMapper(),
                URI.create("https://customer.example/api/customers/"));

        var payment = new Payment(
                101L, 42L, new BigDecimal("12.00"));

        assertThrows(TransientRemoteException.class,
                () -> processor.process(payment));
    }
}
```

Test này chỉ kiểm tra processor biến timeout thành loại exception phù hợp. Nó **không** xác nhận Spring Batch đã retry đủ ba attempts; điều đó phải được xác minh trong step integration test.

Nếu muốn test HTTP status 429/500, mock `HttpResponse<String>` với `statusCode()` tương ứng. Với 200, trả JSON đúng schema; với 401, assert `PermanentRemoteException`.

### 13.2. Step integration test cho retry budget

Tạo reader fixture chỉ trả một item và writer ghi vào list test. Remote service fake có hành vi:

- Lần 1: timeout.
- Lần 2: HTTP 503.
- Lần 3: HTTP 200 với `{"tier":"GOLD"}`.

Chạy step/job thật qua `@SpringBatchTest` và `JobLauncherTestUtils`, rồi assert:

- `JobExecution` cuối là `COMPLETED`.
- Item output được ghi **đúng một lần**.
- Remote fake nhận số lần gọi đúng với policy trong cấu hình.
- `StepExecution.getReadCount()` và `getWriteCount()` đúng.
- Không có skip ngoài dự kiến.

Một test khác cho cả ba lần đều timeout phải assert `FAILED` và exception phản ánh lỗi transient sau khi hết retry, nếu không cấu hình skip.

**Chú ý:** cơ chế fault-tolerant step có thể thực hiện retry theo transaction/rollback và thay đổi số lần gọi processor/writer tùy vị trí lỗi, transaction và cache policy. Test nên xác định kỳ vọng cho **cấu hình cụ thể** thay vì dùng một con số đoán từ chung chung.

### 13.3. Test ngắt luồng

Giả lập `InterruptedException` từ HTTP client:

- Processor phải đặt lại interrupt flag.
- Exception không thuộc nhóm retryable.
- Step được phép dừng/thoát theo chính sách.
- Không nuốt interrupt rồi tiếp tục gọi HTTP mãi.

Vì interrupt flag có thể ảnh hưởng JUnit thread, test phải dọn trạng thái interrupt sau khi đã assert trong môi trường thử nghiệm phù hợp.

### 13.4. Test unknown outcome khi POST

Một fake payment service nên có behavior:

1. Nhận `Idempotency-Key: transfer:T-123`.
2. Ghi thành công giao dịch T-123.
3. Cố ý không gửi response để client timeout.
4. Client gọi status endpoint hoặc retry cùng idempotency key.
5. Server trả trạng thái T-123 đã thành công mà không tạo giao dịch thứ hai.

Assertion quan trọng là **số side effect remote = 1** và batch cuối cùng ghi nhận outcome đúng, kể cả khi request được gửi nhiều lần.

Nếu fake service không implement idempotency, test nên chứng minh vì sao retry POST mù quáng tạo duplicate. Không mang chính sách đó vào production.

### 13.5. Test restart

Dùng batch repository riêng:

- Job chạy với `businessDate` xác định.
- Remote service fake timeout tới khi step FAILED.
- Đưa fake service vào trạng thái khỏe.
- Khởi chạy lại với cùng identifying JobParameters hoặc dùng cơ chế restart phù hợp.
- Assert JobInstance giữ nguyên ID, JobExecution mới có ID khác.
- Kiểm tra output cuối không trùng/mất item.
- Với side effect POST, xác minh idempotency/reconciliation.

### 13.6. Ma trận tình huống nên bao phủ

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Connect timeout rồi hồi phục | Retry đúng hạn, job hoàn thành |
| GET response timeout liên tục | Hết retry → FAILED, không loop vô hạn |
| HTTP 429 có Retry-After | Policy chờ phù hợp hoặc requeue, không tạo retry storm |
| HTTP 401 | Fail nhanh, không thử lại liên tục |
| HTTP 404 | Tuân hợp đồng: fail/skip/chờ consistency |
| HTTP 200 với JSON sai schema | Permanent error, không retry vô ích |
| Interrupt trong lúc gọi | Interrupt flag được giữ |
| Remote POST commit nhưng response mất | Không tạo side effect trùng khi retry/restart |
| Worker chết trước local commit | Khôi phục checkpoint và reconcile remote |
| Một item bị quarantine | Có audit và thống kê skip chính xác |
| 100% item timeout | Worker, connection và transaction không bị giữ vô hạn |
| Nhiều partition retry cùng lúc | Rate limit và concurrency được kiểm soát |
| Circuit breaker mở | Fail fast/requeue theo policy, không spam HTTP |
| Monitor/repository không sẵn sàng | Có tín hiệu quan sát lỗi, không tự đánh dấu success |

---

## 14. Những lỗi thiết kế phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách tiếp cận đúng |
|---|---|---|
| Không đặt HTTP timeout | Worker có thể bị chặn quá lâu | Connect/request timeout rõ ràng |
| Chỉ đặt connect timeout | Request đã kết nối vẫn có thể chờ response quá lâu | Thêm request/response timeout và deadline |
| Retry mọi RuntimeException | Lỗi schema, auth, bug cũng bị retry | Phân loại transient/permanent |
| Timeout POST nghĩa là server chưa xử lý | Response có thể mất sau commit | Idempotency + inquiry/reconciliation |
| Dùng UUID mới mỗi retry | Mỗi request trở thành transaction mới | Business idempotency key ổn định |
| Chỉ tăng retryLimit | Tăng thời gian, tải remote và lock | Bounded retries + backoff + deadline |
| Đặt retry ở nhiều tầng | Attempts có thể nhân lên | Một chiến lược retry được tính tổng |
| Skip timeout để job COMPLETED | Có thể âm thầm mất dữ liệu | Skip chỉ theo hợp đồng, có quarantine |
| Đổi runId để restart | Tạo instance mới, mất checkpoint cũ | Giữ identifying parameters của kỳ dữ liệu |
| Coi rollback local là rollback HTTP | Hai hệ thống không chung transaction | Outbox/idempotent remote API |
| Retry lỗi reader sau khi đã tiến cursor | Có thể bỏ sót một trang/item | Chỉ advance sau khi đọc thành công và checkpoint đúng |
| Log nguyên payload/secret | Lộ dữ liệu nhạy cảm | Structured logs, masking, correlation ID |
| Không giới hạn concurrency | Retry storm làm remote service xấu hơn | Rate limiter, bulkhead, circuit breaker |
| Chỉ theo dõi BatchStatus | Không biết retries, latency, pending outcomes | Metric HTTP và trạng thái reconciliation |
| Tự sửa bảng BATCH_* để “recovery” | Phá metadata và restart semantics | API/chính sách vận hành đúng |

---

## 15. Runbook khi remote service timeout làm job dừng

Khi nhận alert, nên điều tra theo thứ tự giúp giảm rủi ro dữ liệu.

### Bước 1 — Xác định phạm vi

Ghi lại `jobName`, `JobInstance`, `JobExecution`, `StepExecution`, identifying `JobParameters`, thời điểm lỗi, remote service và operation. Kiểm tra có bao nhiêu item đã commit, bao nhiêu item timeout, bao nhiêu item đã bị skip/quarantine.

### Bước 2 — Phân biệt lỗi

Kiểm tra log/trace để phân biệt connect timeout, read/response timeout, HTTP status, lỗi TLS, authentication hoặc dữ liệu invalid. Xác định operation GET đọc hay POST thay đổi trạng thái.

### Bước 3 — Kiểm tra remote dependency

Quan sát service health, latency p95/p99, rate limit, circuit breaker, connection pool, proxy, DNS, network policy và các incident liên quan. Nếu remote API trả `Retry-After`, xác nhận batch có tôn trọng chính sách đó không.

### Bước 4 — Xác minh side effect

Với POST/PUT/PATCH thay đổi trạng thái, tra cứu theo business transaction ID/idempotency key. Nếu outcome chưa rõ, giữ `PENDING_CONFIRMATION` và đối soát, không tự gửi lại hàng loạt.

### Bước 5 — Quyết định recovery

- Lỗi transient của GET và remote đã khỏe: có thể restart/retry theo policy.
- Lỗi authentication/configuration: sửa quyền/cấu hình trước khi chạy lại.
- Lỗi dữ liệu: sửa input, quarantine hoặc skip theo nghiệp vụ.
- Side effect unknown: reconcile kết quả trước khi retry.
- Job bị FAILED nhưng có checkpoint: restart cùng identifying parameters.
- Job đã phát hành output một phần: kiểm tra khả năng ghi lại/append/idempotency trước khi chạy lại.

### Bước 6 — Đối soát và đóng sự cố

Xác minh item count, output, trạng thái giao dịch ở remote, `StepExecution` counters, backlog/quarantine còn lại và kỳ nghiệp vụ bị ảnh hưởng. Khi tất cả item bắt buộc đã có trạng thái cuối, mới đóng incident.

---

## 16. Bài tập thực hành

### Bài 1 — Cấu hình timeout

Dùng Java 17 `HttpClient`, đặt connect timeout 1 giây và request timeout 3 giây. Tạo một endpoint test trả response chậm hơn 3 giây; assert exception là `HttpTimeoutException` hoặc subclass phù hợp và batch không chờ vô hạn.

### Bài 2 — Retry tạm thời

Tạo fake customer service trả 503 hai lần rồi 200. Cấu hình `retryLimit(3)` và exponential backoff. Kiểm tra kết quả cuối đúng, số lần gọi phù hợp và không skip item.

### Bài 3 — Permanent error

Cho service trả 401 và JSON 200 nhưng thiếu `tier`. Chứng minh processor ném exception permanent và không gửi lại request hàng loạt.

### Bài 4 — Tính tổng retry budget

Một remote call timeout sau 4 giây, retryLimit 4, backoff 1 giây, 2 giây, 4 giây. Ước lượng worst-case cho một item và cho chunk 50 item. Đề xuất thay đổi chunk, timeout hay kiến trúc khi SLA chỉ 2 phút.

### Bài 5 — Side effect chưa xác định

Fake payment API commit transaction nhưng không gửi response. Triển khai idempotency key và status lookup, kiểm chứng rằng retry/restart không tạo giao dịch thứ hai.

### Bài 6 — Quarantine

Thiết kế `SkipListener` lưu bản ghi 404 được phép bỏ qua với business key, error code và audit timestamp. Xác nhận `processSkipCount` và số bản ghi quarantine, đồng thời kiểm soát duplicate khi restart.

### Bài 7 — Reader phân trang

Viết custom API reader và cố ý tăng page token trước khi fetch. Giả lập timeout để thấy dữ liệu bị nhảy trang. Sửa reader để state không tiến khi fetch thất bại và kiểm thử restart từ checkpoint.

### Bài 8 — Circuit breaker

Giả lập customer service bị outage 5 phút; theo dõi tổng attempts giữa cấu hình retry thuần và cấu hình có circuit breaker/rate limit. Đánh giá load trên service và thời gian xử lý từng chunk.

### Bài 9 — Recovery thật

Chạy một job có input cố định, làm remote service timeout tới khi step FAILED. Khôi phục service rồi restart cùng JobInstance. Đối chiếu output không trùng/mất và lịch sử JobExecution.

---

## 17. Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html): cấu hình `faultTolerant`, `retryLimit` và retryable exceptions.
- [Spring Batch 5.2 — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html): cách skip và skip limit.
- [Spring Batch 5.2 — Controlling Rollback](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/controlling-rollback.html): rollback trong chunk step.
- [Spring Batch 5.2 — Retry](https://docs.spring.io/spring-batch/reference/5.2/retry.html): stateful/stateless retry và các tình huống retry.
- [Spring Batch 5.2 — ItemStream](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html): checkpoint và restart state.
- [Spring Batch 5.2 — JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata và transaction.
- [FaultTolerantStepBuilder — API 5.2.1](https://docs.spring.io/spring-batch/docs/5.2.1/api/org/springframework/batch/core/step/builder/FaultTolerantStepBuilder.html): `retryLimit`, `retry` và `backOffPolicy`.
- [Java 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `connectTimeout`.
- [Java 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `timeout` trên request.
- [Java 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): exception khi response không đến đúng hạn.
- [Spring Retry](https://docs.spring.io/spring-retry/reference/): backoff, retry policies và cơ chế điều khiển retry.
- [Resilience4j](https://resilience4j.readme.io/): circuit breaker, rate limiter và bulkhead.

Một batch có khả năng recovery tốt cần phân biệt **lỗi tạm thời có thể retry** với **outcome không xác định khi remote side effect đã được gửi**. Timeout và backoff bảo vệ thời gian xử lý; `JobRepository` và `ExecutionContext` hỗ trợ restart; idempotency, status inquiry và reconciliation bảo vệ tính đúng đắn dữ liệu khi giao dịch trải qua nhiều hệ thống. Nếu phối hợp các tầng đó với metric và runbook, job có thể phục hồi sau remote outage mà không âm thầm tạo giao dịch trùng hoặc bỏ sót dữ liệu bắt buộc.
