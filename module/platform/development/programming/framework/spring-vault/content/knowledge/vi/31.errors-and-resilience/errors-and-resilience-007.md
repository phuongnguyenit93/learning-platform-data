# Thử lại thao tác đọc và giới hạn số lần thử trong Spring Vault

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Java dùng **Spring Vault**, một lời gọi đọc cấu hình có thể thất bại tạm thời khi mạng chập chờn, Vault đang chuyển active node, máy chủ quá tải hoặc hệ thống phía sau phản hồi chậm. Nếu ứng dụng dừng ngay ở lỗi thoáng qua, một sự cố vài trăm mili giây có thể trở thành lỗi nghiệp vụ. Nếu thử lại vô hạn, chính ứng dụng lại tăng tải lên Vault, giữ nghẽn các thread xử lý request và làm sự cố kéo dài hơn.

Bài học này tập trung vào **thử lại thao tác đọc có giới hạn** khi sử dụng **VaultOperations/VaultTemplate**, đặc biệt là đọc một bản ghi **KV v2** ổn định. Đây là một phần của khả năng phục hồi của dịch vụ **SPRING_VAULT**, bên cạnh xác thực theo workload, phân quyền ACL, vòng đời token/lease, xử lý lỗi và giám sát.

Sau bài này, bạn có thể:

- Phân biệt lỗi **có thể thử lại** với lỗi cấu hình, phân quyền hoặc dữ liệu không tồn tại.
- Đặt **max attempts**, timeout, exponential backoff và jitter; tính số lần gọi tối đa thật sự.
- Xây dựng Java helper chỉ áp dụng retry cho **một thao tác đọc cụ thể**.
- Tránh thử lại nhầm một endpoint đọc **có tác dụng phụ** như cấp dynamic database credential.
- Viết kiểm thử xác nhận số lần thử, quy tắc dừng, phân loại lỗi và hành vi khi hết lượt.
- Quan sát tỷ lệ retry, độ trễ và tình trạng Vault mà không ghi lộ bí mật.

Ví dụ xuyên suốt là dịch vụ **orders-api** đọc secret cấu hình từ **KV v2**:

~~~text
Mount path:       kv-app
Logical KV path:  orders/config
HTTP API path:    kv-app/data/orders/config
Vault action:     GET
Runtime policy:   read
~~~

Secret chứa các giá trị minh họa; không dùng credential production trong code mẫu, log hoặc test.

## 2. Vì sao chỉ retry một số thao tác đọc?

**Retry** có nghĩa là gửi lại **cùng một thao tác** sau một lỗi mà ta cho là tạm thời. Điều này chỉ an toàn khi thao tác có thể thực hiện lại mà không tạo hậu quả không mong muốn.

Với **KV v2 GET một version cố định hoặc version hiện tại**, lần đọc lại không tự tạo secret/lease mới. Tuy nhiên, giữa hai lần đọc, giá trị “latest” có thể đã thay đổi do writer cập nhật. Nếu nghiệp vụ cần snapshot bất biến, hãy chọn version KV v2 cụ thể và kiểm tra metadata.

**Không thể đánh đồng tất cả GET hoặc tất cả VaultOperations.read(...) với thao tác đọc thuần túy.** Một ví dụ quan trọng là **database/creds/readonly**: gọi endpoint này có thể **tạo một bộ username/password mới kèm lease**. Nếu timeout xảy ra sau khi Vault đã cấp credential, việc gọi lại có thể cấp thêm một bộ nữa. Vì vậy chiến lược retry phải được lựa chọn theo **semantics của endpoint**, không chỉ theo HTTP verb hay tên phương thức Java.

| Thao tác | Có nên thử lại tự động? | Lý do |
| --- | --- | --- |
| GET KV v2 secret đã tồn tại | Có điều kiện | Thông thường không sinh tài nguyên mới; chỉ retry lỗi tạm thời |
| GET KV v2 version cụ thể | Có điều kiện | Có tính ổn định tốt hơn khi cần dữ liệu bất biến |
| GET metadata/health an toàn | Có điều kiện | Chú ý HTTP health status đặc biệt của Vault |
| GET database/creds/role | **Không áp dụng retry chung** | Có thể phát hành dynamic credential/lease mới |
| Gọi PKI issue, tạo token, Transit encrypt | Không dùng chính sách retry đọc | Có thể tạo chứng thư/token/ciphertext mới hoặc tác động trạng thái |
| Unwrap wrapping token | Không retry mù | Token thường chỉ dùng một lần; request trước có thể đã tiêu thụ |
| Renew/revoke token hoặc lease | Chính sách riêng | Cần xét vòng đời, tính lặp lại và kết quả khi timeout |

Trước khi gắn retry vào một client, hãy hỏi: **nếu request thứ nhất đã được Vault thực hiện nhưng response bị mất, request thứ hai có tạo thêm tài nguyên hoặc thay đổi trạng thái không?**

## 3. Phân loại lỗi trước khi retry

Bản thân một exception của Spring Vault chưa đủ để kết luận lỗi có thể phục hồi. Cần xem **HTTP status**, loại lỗi mạng, operation/path cụ thể và trạng thái Vault.

| Tình huống | Hành vi khuyến nghị | Giải thích |
| --- | --- | --- |
| **200** và có dữ liệu | Trả kết quả | Không cần retry |
| KV path không tồn tại; API trả **404** hoặc Spring Vault trả **null** | Dừng theo nghiệp vụ | Không có dữ liệu là tình huống khác với lỗi tạm thời |
| **400**, **405**, **422** do request sai | Không retry | Cần sửa path, dữ liệu hoặc HTTP method |
| **401/403** | Không retry cùng token | Có thể là token không hợp lệ, thiếu ACL hoặc authentication thất bại |
| **412** eventual consistency | Có thể retry theo ngữ cảnh | Vault có trường hợp trả precondition failed khi dữ liệu chưa hội tụ |
| **429** | Xem chính xác endpoint/nguyên nhân | Có thể liên quan quota hoặc **standby** đối với endpoint health; không tự coi là rate limit chung |
| **500**, **502**, **503**, **504** | Có thể retry **có giới hạn** cho KV read | Có thể tạm thời; **503** cũng có thể do Vault bị sealed hoặc đang bảo trì |
| Connect timeout, read timeout hoặc kết nối bị đứt | Có thể retry có giới hạn | Thao tác KV GET có thể gửi lại; cần giới hạn tổng thời gian |
| Sai CA, TLS trust/hostname verification | Không retry | Không phải sự cố có thể sửa bằng cách chờ vài trăm mili giây |
| DNS name sai, namespace/mount sai | Không retry mù | Cần sửa cấu hình |
| Token hết hạn | Xử lý authentication/session riêng | Chỉ đăng nhập lại khi cơ chế/workload được phép; không tự tăng số lần retry đọc |

### Không coi mọi HTTP 429 là một trường hợp

Đối với **/sys/health**, mã **429** theo cấu hình mặc định thường có nghĩa node đang ở trạng thái **standby**. Một số endpoint có thể trả 429 do giới hạn quota. Cùng status code nhưng cách xử lý khác nhau: với standby, điều chỉnh routing hoặc active-node discovery; với quota, giảm tốc độ và chỉ retry khi phù hợp.

Tương tự, **503** có thể là quá tải tạm thời (ứng viên retry) nhưng cũng có thể là **Vault sealed** (retry liên tục sẽ không giúp Vault tự unseal). Hạn chế retry giúp giảm tác hại, nhưng quan sát health và phân loại nguyên nhân vẫn cần thiết.

### Null khác exception

Spring Vault hỗ trợ:

~~~java
VaultResponse response = vaultOperations.read(
        "kv-app/data/orders/config");

if (response == null) {
    // Secret/path không tồn tại hoặc không có dữ liệu phù hợp.
    // Đây là nhánh nghiệp vụ, không phải một exception để retry.
}
~~~

Với **VaultKeyValueOperations**:

~~~java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;

VaultKeyValueOperations kv =
        vaultOperations.opsForKeyValue("kv-app", KeyValueBackend.KV_2);

VaultResponse response = kv.get("orders/config");
// response có thể là null nếu secret không tồn tại.
~~~

Một chính sách “nếu response null thì đọc lại 20 lần” thường chỉ tăng tải Vault, che giấu cấu hình sai và làm timeout của người dùng dài hơn.

## 4. Bốn giới hạn bắt buộc của retry

### 4.1 Max attempts: tổng số lần gọi, không phải số lần thử thêm

Nếu cấu hình **maxAttempts = 3**, nghĩa là:

1. Lần gọi ban đầu: **attempt 1**.
2. Nếu lỗi retryable: gọi lại **attempt 2**.
3. Nếu tiếp tục lỗi retryable: gọi lần cuối **attempt 3**.
4. Nếu lần ba vẫn lỗi: **dừng và trả lỗi**.

Vì vậy **maxAttempts = 3 tương đương tối đa 2 lần retry**. Một số thư viện dùng tên **maxRetries** để chỉ *số lần lặp lại ngoài lần gọi ban đầu*; phải đọc contract của thư viện để tránh cấu hình lệch một lần.

### 4.2 Exponential backoff

Khoảng chờ tăng theo số lần lỗi:

\[
d_k = \min(d_{\max}, d_0 \times 2^{k-1})
\]

Trong đó **d0** là độ trễ ban đầu, **dmax** là trần, **k** là lần chờ (sau attempt thất bại). Ví dụ **d0 = 150 ms**, **dmax = 1.000 ms**:

| Sau attempt | Độ trễ cơ bản trước lần tiếp theo |
| --- | --- |
| 1 | 150 ms |
| 2 | 300 ms |
| 3 | 600 ms (nếu vẫn còn attempt) |
| 4 trở đi | Tối đa 1.000 ms |

Với maxAttempts = 3, chỉ thực hiện **hai khoảng chờ đầu tiên**.

### 4.3 Jitter

Nếu hàng trăm instance cùng lỗi ở một thời điểm rồi chờ chính xác **150 ms**, chúng có thể cùng bắn request vào Vault ở thời điểm tiếp theo. **Jitter** thêm độ ngẫu nhiên vào khoảng chờ để tránh request được đồng bộ.

Ví dụ:

~~~text
wait = min(baseBackoff, maxBackoff) + random(0..100 ms)

Attempt 1 thất bại -> chờ khoảng 150..249 ms
Attempt 2 thất bại -> chờ khoảng 300..399 ms
Attempt 3 thất bại -> dừng
~~~

Khoảng chờ thực tế phải được cấu hình để phù hợp **latency budget**; ví dụ trên chỉ minh họa chiến lược.

### 4.4 Timeout và tổng thời gian chờ

Retry không thay thế **connect timeout**, **read timeout** hoặc deadline tổng của request.

Nếu mỗi lần gọi Vault có read timeout **1 giây**, maxAttempts = 3 và backoff tối đa khoảng **0,65 giây** cộng lại, độ trễ đầu cuối trong trường hợp xấu có thể tiến gần **3,65 giây**, chưa kể DNS, TLS, kết nối, scheduler và mã ứng dụng. Nếu request HTTP của người dùng chỉ có deadline **2 giây**, chính sách này cần được rút ngắn.

Thiết kế production nên có:

- Timeout ở HTTP client được Spring Vault sử dụng.
- Giới hạn tổng số lần thử và khoảng chờ.
- **Overall deadline** hoặc time budget của nghiệp vụ, truyền xuống các thao tác phụ thuộc.
- Không cho retry nhiều tầng cùng nhân số lần gọi lên (ví dụ client 3 lần × service 3 lần = tối đa 9 request).
- **Circuit breaker** hoặc cơ chế giảm tải khi Vault liên tục lỗi, kết hợp concurrency/bulkhead limit nếu thích hợp.

## 5. Luồng quyết định khi một lần đọc thất bại

~~~mermaid
flowchart TD
    A["Đọc KV secret"] --> B{"Có kết quả?"}
    B -->|"Có dữ liệu"| C["Trả secret"]
    B -->|"Không tìm thấy/null"| D["Xử lý secret thiếu theo nghiệp vụ"]
    B -->|"Exception"| E{"Lỗi tạm thời có thể retry?"}
    E -->|"Không"| F["Trả lỗi ngay, không retry"]
    E -->|"Có"| G{"Đã dùng hết attempts hoặc deadline?"}
    G -->|"Có"| H["Trả lỗi cuối, ghi metric"]
    G -->|"Chưa"| I["Backoff + jitter"]
    I --> A
~~~

Hai câu hỏi quan trọng nhất trong vòng lặp:

1. **Đây có thực sự là lỗi retryable của thao tác đọc thuần túy không?** Nếu không: dừng.
2. **Còn thời gian và lượt thử không?** Nếu không: dừng, giữ nguyên nguyên nhân lỗi cuối.

Không nên làm mất nguyên nhân gốc bằng exception kiểu “Vault bị lỗi” không có cause; nhưng cũng không ghi body response chứa bí mật vào log công khai.

## 6. Ví dụ Java 17: retry giới hạn ba lần cho KV read

Ví dụ dưới dùng **VaultOperations.read(...)** và chỉ thử lại khi nhận được một số lỗi HTTP tạm thời hoặc lỗi kết nối có thể nhận diện. Mã tự chứa phần retry để thấy rõ bộ đếm và khoảng chờ; hệ thống thực có thể sử dụng **Spring Retry** hoặc **Resilience4j** với cùng chính sách.

**Giả định:** Spring Boot/Spring Vault đã tạo bean **VaultOperations** trỏ tới Vault bằng TLS với xác thực workload và policy **read** trên **kv-app/data/orders/config**.

### 6.1 Helper điều khiển số lần gọi

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;

import javax.net.ssl.SSLException;

import org.springframework.web.client.HttpStatusCodeException;

public final class BoundedVaultReadRetry {

    private static final int MAX_ATTEMPTS = 3;
    private static final long INITIAL_DELAY_MS = 150;
    private static final long MAX_BACKOFF_MS = 1_000;
    private static final long JITTER_BOUND_MS = 100;

    @FunctionalInterface
    public interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    private final Sleeper sleeper;

    public BoundedVaultReadRetry(Sleeper sleeper) {
        this.sleeper = Objects.requireNonNull(sleeper);
    }

    public <T> T execute(Supplier<T> readOperation) {
        Objects.requireNonNull(readOperation);

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                // null được trả về như một kết quả nghiệp vụ, không retry.
                return readOperation.get();
            } catch (RuntimeException failure) {
                if (!isRetryable(failure) || attempt == MAX_ATTEMPTS) {
                    throw failure;
                }

                long baseDelay = Math.min(
                        MAX_BACKOFF_MS,
                        INITIAL_DELAY_MS * (1L << (attempt - 1)));
                long jitter = ThreadLocalRandom.current()
                        .nextLong(JITTER_BOUND_MS);
                long delay = baseDelay + jitter;

                try {
                    sleeper.sleep(delay);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Retry bị hủy do thread bị interrupt",
                            interrupted);
                }
            }
        }

        throw new IllegalStateException("Unreachable");
    }

    private static boolean isRetryable(Throwable error) {
        // Spring Vault có thể bọc lỗi HTTP trong VaultException;
        // chỉ phân loại theo status nếu tìm được exception HTTP.
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current instanceof HttpStatusCodeException http) {
                int status = http.getStatusCode().value();

                return status == 500
                        || status == 502
                        || status == 503
                        || status == 504;
            }
        }

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current instanceof SSLException) {
                return false; // TLS/certificate: cần điều tra.
            }
            if (current instanceof SocketTimeoutException
                    || current instanceof ConnectException) {
                return true;
            }
        }

        // Lỗi không nhận diện: fail closed, không retry mù.
        return false;
    }
}
~~~

Mã này cố tình **không retry 403, 404, 429 hoặc 412 mặc định**, vì các mã đó cần phân loại theo API và tình huống cụ thể. Chỉ mở thêm nhánh sau khi có chính sách rõ ràng. **isRetryable** kiểm tra exception HTTP trong cause chain; nếu version/adapter Spring Vault đang dùng **không giữ HTTP status trong cause**, hàm trả **false** để tránh retry không kiểm soát. Khi đó cần bổ sung một adapter phân loại dựa trên **exception/status API thực tế của version đang sử dụng**, không parse thông báo lỗi bằng chuỗi mơ hồ.

Với **Spring Vault 4.1+**, **VaultClientResponseException** hỗ trợ **getStatusCode()**; đó là điểm mở rộng thích hợp cho nhánh phân loại HTTP ở version này. Với các version dùng RestTemplate, HTTP exception thường xuất hiện dưới dạng **HttpStatusCodeException** trong nguyên nhân. Việc phân loại lỗi phải được xác minh bằng integration test ở version dự án.

Lớp trên dùng **Thread.sleep** thông qua **Sleeper** vì đây là ví dụ đọc **blocking**. Không dùng nguyên mẫu này trong event-loop WebFlux; với reactive pipeline, cần **retryWhen** có backoff và thời gian giới hạn, đồng thời giữ quy tắc retry theo từng endpoint.

### 6.2 Gắn helper vào service Spring Vault

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrderConfigurationReader {

    private static final String KV_READ_PATH =
            "kv-app/data/orders/config";

    private final VaultOperations vault;
    private final BoundedVaultReadRetry retry =
            new BoundedVaultReadRetry(Thread::sleep);

    public OrderConfigurationReader(VaultOperations vault) {
        this.vault = vault;
    }

    public VaultResponse loadConfiguration() {
        return retry.execute(() -> vault.read(KV_READ_PATH));
    }
}
~~~

Khi đọc KV v2 theo endpoint đầy đủ:

- Nếu lần 1 thành công, kết quả trả ngay và **không có khoảng chờ**.
- Nếu lần 1 trả **503** được phân loại là retryable, service chờ backoff rồi gọi lại.
- Nếu lần 2 thành công, service trả dữ liệu và dừng.
- Nếu lần 3 vẫn lỗi, service **ném nguyên exception lần cuối** cho tầng xử lý lỗi.
- Nếu secret không tồn tại và Spring Vault trả **null**, vòng lặp kết thúc ngay; caller tự quyết định thiếu cấu hình là lỗi startup hay trạng thái hợp lệ.

Không truyền vào helper này các operation **database/creds**, **PKI issue**, **transit encrypt**, **token create**, **unwrap**, **lease renew/revoke**. Chúng cần chính sách riêng theo semantics và idempotency.

## 7. Cấu hình timeout, giới hạn và trách nhiệm tầng gọi

Một số thư viện hỗ trợ retry ở HTTP client, SDK, framework, service mesh và API gateway. Nếu nhiều tầng đều retry, tác động có thể nhân lên.

Ví dụ:

~~~text
API gateway         retry 2 lần (3 attempts)
Service orders-api  retry 2 lần (3 attempts)
Vault HTTP client   retry 2 lần (3 attempts)

Trường hợp xấu: 3 × 3 × 3 = 27 lời gọi đến Vault
cho một lần yêu cầu nghiệp vụ.
~~~

Vì vậy nên chỉ định **một tầng sở hữu retry** cho từng đường đọc, hoặc bảo đảm các tầng có tổng budget hợp lý. Kiểm tra cấu hình của **Spring Vault HTTP client**, load balancer, proxy và tầng gọi phía trên trước khi kích hoạt policy mới.

**Đối với workload startup:** nếu ứng dụng cần secret trước khi nhận traffic, có thể fail startup khi hết retries, để orchestration xử lý restart/readiness theo chính sách. Đừng tự động dùng secret mặc định không an toàn khi Vault không sẵn sàng.

**Đối với request trực tuyến:** nếu deadline của request gần hết, trả lỗi có kiểm soát. Không nên giữ thread chờ thêm vài lần retry khi client đã hủy request hoặc không còn thời gian hoàn tất công việc.

**Đối với giá trị cache:** chỉ sử dụng cached secret khi được thiết kế rõ: thời hạn hiệu lực, quyền truy cập, rotation, revoke, consistency và hậu quả nếu giá trị cũ bị dùng. Không mặc định trả “last known good” cho password/token đã bị thu hồi.

**Đối với token:** retry 403 bằng cùng token thường không có ích. Nếu lỗi đến từ token hết hạn và workload có cơ chế đăng nhập lại, **ClientAuthentication/SessionManager** chịu trách nhiệm khôi phục phiên theo quy tắc hợp lệ; không tự chuyển sang token có quyền rộng hơn. Tránh vô tình tạo vòng lặp “login retry” cộng với “read retry”.

## 8. Kiểm thử đơn vị chính sách retry, không phải chỉ kiểm tra phương thức có chạy

Vì helper nhận **Supplier** và **Sleeper**, ta có thể giả lập lỗi và kiểm đếm số lần gọi mà không phụ thuộc Vault thật và không phải chờ thực tế.

### 8.1 Hai lỗi tạm thời rồi đọc thành công

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpServerErrorException;

class BoundedVaultReadRetryTest {

    @Test
    void succeedsOnThirdAttemptAfterTransientFailures() {
        AtomicInteger calls = new AtomicInteger();
        AtomicInteger sleeps = new AtomicInteger();

        BoundedVaultReadRetry retry =
                new BoundedVaultReadRetry(ms -> sleeps.incrementAndGet());

        String value = retry.execute(() -> {
            if (calls.incrementAndGet() < 3) {
                throw new HttpServerErrorException(
                        HttpStatus.SERVICE_UNAVAILABLE);
            }
            return "config-loaded";
        });

        assertEquals("config-loaded", value);
        assertEquals(3, calls.get());  // 1 lần đầu + 2 retry
        assertEquals(2, sleeps.get()); // Không chờ sau khi thành công
    }
}
~~~

### 8.2 Lỗi 403 không được thử lại

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpClientErrorException;

class BoundedVaultReadPermissionTest {

    @Test
    void neverRetriesPermissionDenied() {
        AtomicInteger calls = new AtomicInteger();

        BoundedVaultReadRetry retry =
                new BoundedVaultReadRetry(ms -> {
                    throw new AssertionError("Không được backoff cho 403");
                });

        assertThrows(HttpClientErrorException.class, () ->
                retry.execute(() -> {
                    calls.incrementAndGet();
                    throw new HttpClientErrorException(
                            HttpStatus.FORBIDDEN);
                }));

        assertEquals(1, calls.get());
    }
}
~~~

### 8.3 Lỗi 503 liên tục dừng sau lần thứ ba

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpServerErrorException;

class BoundedVaultReadExhaustionTest {

    @Test
    void stopsAfterThreeAttempts() {
        AtomicInteger calls = new AtomicInteger();

        BoundedVaultReadRetry retry =
                new BoundedVaultReadRetry(ms -> { });

        assertThrows(HttpServerErrorException.class, () ->
                retry.execute(() -> {
                    calls.incrementAndGet();
                    throw new HttpServerErrorException(
                            HttpStatus.SERVICE_UNAVAILABLE);
                }));

        assertEquals(3, calls.get());
    }
}
~~~

Có thể thêm test cho **null**: Supplier trả **null**, kết quả là null với đúng **một lời gọi**, không sleep và không phát sinh exception. Test cho **InterruptedException** cần xác minh thread interrupt flag được khôi phục và vòng lặp không gửi thêm request.

Những test trên xác nhận *thuật toán kiểm đếm và dừng*. Chúng **không chứng minh** version Spring Vault hiện tại sẽ tạo đúng exception/cause cho mọi HTTP status; điểm đó cần integration test.

## 9. Kiểm thử tích hợp với Vault test

Một môi trường thử nghiệm phù hợp gồm Vault test đã initialized/unsealed, KV v2 mount **kv-app**, dữ liệu **orders/config** giả, token workload chỉ có **read** và HTTP client cấu hình TLS/timeouts. Không thử gây lỗi bằng cách seal Vault dùng chung hoặc thay policy production.

Bộ test tích hợp nên bao gồm:

1. **Đọc bình thường:** xác minh KV path đúng, có dữ liệu, thời gian phản hồi nằm trong budget; số request là một.
2. **Path thiếu:** gọi path KV v2 không tồn tại, xác nhận trả **null** hoặc tình huống not found phù hợp, không có retry.
3. **Sai quyền:** dùng token không có read permission, xác minh bị từ chối với **403** và không gửi lại bằng chính token đó.
4. **503 tạm thời:** dùng test proxy/fault injection trước Vault để trả 503 cho hai request đầu rồi chuyển tiếp lần ba; xác nhận tối đa ba lần và kết quả thành công.
5. **503 liên tục:** proxy luôn trả 503; xác nhận ba lần rồi trả lỗi, không lặp vô hạn.
6. **Timeout mạng:** proxy làm chậm response vượt read timeout; xác minh timeout và retry có giới hạn, đồng thời đo thời gian thực.
7. **Không có leak:** kiểm tra log/trace khi lỗi nhiều lần không chứa X-Vault-Token, secret value, credential hoặc response body nhạy cảm.
8. **Concurrent load:** với nhiều request đồng thời, quan sát jitter, concurrency limit và tổng request Vault để tránh retry storm.

Khi test không thể tạo lỗi HTTP qua proxy, nên kiểm tra **classification adapter** bằng test riêng với exception thực tế của version Spring Vault thay vì chỉ giả định thông điệp lỗi có số 503.

## 10. Giám sát retry và giới hạn tải

Để đánh giá retry có hiệu quả hay làm tình hình xấu hơn, ghi metric theo **operation**, **outcome**, **status class**, **attempt count** và **duration**:

| Metric gợi ý | Trả lời câu hỏi |
| --- | --- |
| **vault_read_attempts_total** | Có bao nhiêu lời gọi thật sự đến Vault? |
| **vault_read_retries_total** | Bao nhiêu lần gửi lại sau thất bại? |
| **vault_read_retry_exhausted_total** | Bao nhiêu lượt không phục hồi trong giới hạn? |
| **vault_read_latency_seconds** | Độ trễ tổng gồm retry/backoff là bao nhiêu? |
| **vault_read_failures_total{reason}** | Lỗi do timeout, 403, 404, 5xx hay TLS? |
| **vault_read_inflight** | Có bao nhiêu lời gọi đang chờ Vault cùng lúc? |

Tên metric là ví dụ minh họa, cần phù hợp quy chuẩn Micrometer/Prometheus của dự án. Không dùng **secret path đầy đủ**, token, tên người dùng hoặc nội dung secret làm label vì có thể gây lộ thông tin và tăng cardinality.

Nên phân biệt:

- **Một logical request** tới service có thể tương ứng nhiều **physical attempts** gửi Vault.
- Chỉ tính **retry** cho attempts từ lần 2 trở đi.
- **Success after retry** vẫn là dấu hiệu Vault/đường mạng có bất ổn; không chỉ nhìn tỷ lệ request cuối thành công.
- Theo dõi số lượng **403** tăng sau deploy policy/auth, **5xx** tăng khi Vault quá tải, và độ trễ p95/p99 tăng khi retry làm đầy thread pool.

Log an toàn có thể ở dạng:

~~~text
service=orders-api operation=kv-config-read attempt=2
outcome=retryable-error status=503 next_delay_ms=320
service=orders-api operation=kv-config-read attempt=3
outcome=success total_attempts=3
~~~

Đừng log **VaultResponse**, header **X-Vault-Token**, bearer token, plaintext KV hoặc mật khẩu trong exception message. Nếu đường dẫn KV là metadata nhạy cảm, chỉ dùng nhãn logic **kv-config-read**.

## 11. Các sai lầm hay gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Retry mọi **Exception** | Lặp vô ích với 403, 404, TLS lỗi và config sai | Chỉ retry lỗi đã phân loại |
| Đặt **maxAttempts** rất lớn | Làm latency vượt deadline và tăng tải Vault | Giới hạn nhỏ, ví dụ ba attempts cho KV read |
| Không backoff hoặc jitter | Nhiều instance đồng thời đánh Vault sau lỗi | Exponential backoff có jitter |
| Retry GET động sinh lease | Có thể tạo nhiều credential ngoài dự kiến | Chọn chính sách theo semantics endpoint |
| Retry cả trên gateway, SDK và service | Request nhân theo nhiều tầng | Có một tầng chịu trách nhiệm hoặc tổng budget |
| Retry mãi khi 503 do Vault sealed | Không giúp phục hồi, tạo thêm tải | Xem health và cảnh báo operator |
| Coi 429 của **/sys/health** là quota | Chẩn đoán sai trạng thái standby | Phân loại theo endpoint |
| Coi null từ **read()** là lỗi hệ thống | Retry secret không tồn tại | Dùng nhánh dữ liệu thiếu |
| Nuốt nguyên nhân cuối và trả secret rỗng | Khó chẩn đoán, nguy hiểm về nghiệp vụ | Giữ cause, map lỗi an toàn |
| Dùng Thread.sleep trên Reactor event loop | Chặn event loop, giảm throughput | Retry phi đồng bộ phù hợp với reactive |
| Dùng cached secret vô hạn khi Vault lỗi | Có thể dùng token/credential đã bị revoke | Chính sách cache, TTL, rotation và fail-safe |
| Chỉ kiểm tra unit test retry | Không thấy lỗi adapter exception của Spring Vault | Thêm integration test với Vault và test proxy |

## 12. Checklist triển khai

1. Xác định đúng **endpoint đọc**; chỉ áp dụng chính sách này cho KV read không tạo tài nguyên mới.
2. Kiểm tra **VaultOperations.read(...)** hoặc **opsForKeyValue(...)** có thể trả null khi path không tồn tại; không retry null theo mặc định.
3. Phân loại lỗi mạng và status của **version Spring Vault thực tế**; 400/403/404/TLS config lỗi phải dừng ngay.
4. Cấu hình **maxAttempts = 3** (một lần đầu và tối đa hai retry), backoff tăng dần, jitter và HTTP timeout.
5. Tính **tổng độ trễ xấu nhất** với deadline nghiệp vụ; kiểm tra các tầng bên ngoài đã có retry chưa.
6. Giữ danh tính workload và ACL nguyên tắc tối thiểu; token hết hạn được xử lý bởi authentication/session đúng trách nhiệm.
7. Dừng khi hết lượt, giữ nguyên exception cuối và trả lỗi an toàn; không log secret/token.
8. Kiểm thử cả thành công lần đầu, thành công lần ba, 403 không retry, null không retry và lỗi 503 liên tục.
9. Quan sát attempts, exhausted retries, latency, concurrent load và trạng thái Vault để chỉnh giới hạn dựa trên bằng chứng thực tế.

**Điểm cốt lõi:** trong **Spring Vault**, retry có ích khi lỗi đọc là tạm thời **và** việc thực hiện lại an toàn. Một chính sách tốt cần trả lời được ba câu hỏi: **“Có được thử lại không?”, “Còn bao nhiêu lượt?”, “Còn bao nhiêu thời gian?”**. Giới hạn rõ ràng giúp ứng dụng phục hồi sau sự cố ngắn mà vẫn bảo vệ Vault trước retry storm.

## Tài liệu tham khảo chính thức

- [Spring Vault — Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html).
- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html).
- [Spring Vault — VaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html).
- [HashiCorp Vault — HTTP API status codes](https://developer.hashicorp.com/vault/api-docs).
- [HashiCorp Vault — Server temporarily overloaded](https://developer.hashicorp.com/vault/docs/concepts/adaptive-overload-protection/vault-server-temporarily-overloaded).
- [HashiCorp Vault — System Health API](https://developer.hashicorp.com/vault/api-docs/system/health).
- [Spring Retry — RetryTemplate](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/support/RetryTemplate.html).
