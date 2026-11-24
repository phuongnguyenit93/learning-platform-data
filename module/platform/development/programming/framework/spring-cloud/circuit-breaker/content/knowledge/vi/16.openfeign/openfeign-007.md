# Phối hợp timeout, ErrorDecoder và chính sách retry của Feign

Khi Spring Cloud OpenFeign gọi một dịch vụ từ xa, ba cơ chế quyết định lời gọi kết thúc như thế nào: timeout giới hạn thời gian chờ, ErrorDecoder chuyển HTTP response lỗi thành exception, còn Retryer quyết định có thử lại khi nhận được lỗi có thể retry hay không. Khi OpenFeign được bảo vệ bởi Spring Cloud CircuitBreaker, thứ tự và giới hạn của ba cơ chế này ảnh hưởng trực tiếp tới độ trễ, tải lên dependency và số liệu failure của Circuit Breaker.

Bài này thuộc chương OpenFeign trong module SPRING_CLOUD_CIRCUIT_BREAKER. Mục tiêu là cấu hình timeout cho từng Feign client, phân loại HTTP status bằng ErrorDecoder, chỉ retry những lỗi tạm thời và phối hợp retry với Circuit Breaker mà không làm vượt deadline hoặc lặp lại thao tác nghiệp vụ ngoài ý muốn.

## 1. Vai trò của ba cơ chế

| Cơ chế | Nhiệm vụ | Câu hỏi cần trả lời |
|---|---|---|
| Timeout | Giới hạn thời gian kết nối và chờ response | Một lần gọi được phép chờ bao lâu? |
| ErrorDecoder | Chuyển response HTTP không thành công thành exception | Response này là lỗi nghiệp vụ, lỗi hạ tầng hay lỗi có thể retry? |
| Retryer | Quyết định có thực hiện lại lời gọi khi gặp RetryableException | Lỗi này có thể phục hồi bằng cách thử lại không, và thử tối đa bao nhiêu lần? |
| Circuit Breaker | Theo dõi kết quả cuối của lời gọi và ngăn tiếp tục gọi dependency suy giảm | Dependency có đang lỗi hoặc chậm lặp lại không? |

Các cơ chế này bổ sung cho nhau. Timeout không quyết định retry. ErrorDecoder không tự thực hiện retry; nó chỉ tạo exception phù hợp. Retryer không phân tích trực tiếp mọi HTTP response; nó xử lý RetryableException do transport hoặc ErrorDecoder phát ra. Circuit Breaker quan sát kết quả của lời gọi được bảo vệ để cập nhật trạng thái.

Một nguyên tắc hữu ích là chỉ retry lỗi có khả năng tạm thời và thao tác có thể lặp lại an toàn. Không retry tất cả lỗi 4xx hoặc 5xx chỉ vì chúng xuất hiện dưới dạng exception.

## 2. Cấu hình connect timeout và read timeout

OpenFeign phân biệt hai khoảng thời gian:

- Connect timeout: thời gian tối đa để thiết lập kết nối tới endpoint.
- Read timeout: thời gian tối đa chờ dữ liệu response sau khi kết nối được thiết lập, theo semantics của HTTP client đang dùng.

Với Spring Cloud OpenFeign, có thể cấu hình theo tên Feign client trong application.yml:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalogClient:
            connectTimeout: 500
            readTimeout: 1200
            loggerLevel: basic
          paymentClient:
            connectTimeout: 700
            readTimeout: 1800
            loggerLevel: basic
~~~

Các giá trị timeout trong ví dụ được tính bằng millisecond. Tên catalogClient và paymentClient phải khớp với tên client mà ứng dụng khai báo. Có thể đặt cấu hình chung dưới khóa default rồi ghi đè cho client cụ thể khi cần.

Ví dụ khai báo Feign client:

~~~java
@FeignClient(name = "catalogClient")
public interface CatalogClient {
    @GetMapping("/products/{id}")
    Product findById(@PathVariable("id") String id);
}
~~~

Không nên đặt timeout chỉ dựa trên cảm giác. Hãy đo latency bình thường và p95/p99 của dependency, ngân sách thời gian của request đầu cuối, thời gian xử lý ở gateway và thời gian còn lại cho fallback. Read timeout quá ngắn tạo lỗi giả khi hệ thống chỉ có biến động ngắn; quá dài giữ thread và connection trong lúc dependency đang chậm.

Timeout của Feign áp dụng cho từng lần thực hiện request. Nếu Retryer thực hiện nhiều lần, tổng thời gian có thể lớn hơn read timeout rất nhiều. Vì vậy, phải tính cả số lần retry và khoảng backoff trong deadline tổng.

## 3. Phân loại HTTP response bằng ErrorDecoder

Feign gọi ErrorDecoder khi nhận HTTP response không thuộc nhóm thành công. ErrorDecoder chuyển response đó thành exception. Đây là nơi phù hợp để phân biệt kết quả nghiệp vụ và lỗi tạm thời của dependency.

Ví dụ, Catalog Service có thể trả:

| HTTP status | Ý nghĩa trong ví dụ | Exception mong muốn |
|---|---|---|
| 404 | Sản phẩm không tồn tại | ProductNotFoundException, không retry |
| 400 hoặc 422 | Request không hợp lệ hoặc không đạt điều kiện nghiệp vụ | CatalogRequestException, không retry |
| 401 hoặc 403 | Credential hoặc quyền truy cập của service có vấn đề | CatalogCredentialException, không retry tự động |
| 429 | Dependency đang throttling theo rate limit | RetryableException nếu hợp đồng cho phép retry |
| 502, 503, 504 | Gateway hoặc dependency tạm thời không khả dụng | Có thể retry có giới hạn |
| 500 | Lỗi phía server | Chỉ retry nếu chính sách dịch vụ xác nhận lỗi có tính tạm thời |

Ví dụ ErrorDecoder:

~~~java
import feign.Response;
import feign.Request;
import feign.RetryableException;
import feign.codec.ErrorDecoder;

public class CatalogErrorDecoder implements ErrorDecoder {
    private final ErrorDecoder defaultDecoder = new ErrorDecoder.Default();

    @Override
    public Exception decode(String methodKey, Response response) {
        int status = response.status();

        if (status == 404) {
            return new ProductNotFoundException(
                "Không tìm thấy sản phẩm"
            );
        }

        if (status == 400 || status == 422) {
            return new CatalogRequestException(
                "Request catalog không hợp lệ"
            );
        }

        if (status == 401 || status == 403) {
            return new CatalogCredentialException(
                "Credential của Catalog Service không hợp lệ"
            );
        }

        if (status == 429 || status == 503) {
            if (response.request().httpMethod() == Request.HttpMethod.GET) {
                return new RetryableException(
                    status,
                    "Catalog Service đang tạm thời giới hạn hoặc từ chối tải",
                    response.request().httpMethod(),
                    null,
                    null,
                    response.request()
                );
            }

            return new CatalogTemporarilyUnavailableException(
                "Không tự retry thao tác ghi khi chưa xác nhận tính idempotent"
            );
        }

        Exception decoded = defaultDecoder.decode(methodKey, response);
        if (decoded instanceof RetryableException
                && response.request().httpMethod() != Request.HttpMethod.GET) {
            return new CatalogTemporarilyUnavailableException(
                "Không tự retry thao tác ghi khi chưa xác nhận tính idempotent"
            );
        }
        return decoded;
    }
}
~~~

Trong ví dụ, 404 và lỗi request được chuyển thành exception nghiệp vụ; 401/403 được chuyển thành lỗi credential cần cảnh báo và sửa cấu hình; 429/503 được đánh dấu có thể retry. Những status khác được giao cho decoder mặc định.

Đây là chính sách minh họa, cần điều chỉnh theo hợp đồng API. Ví dụ, 429 có thể là quota nghiệp vụ của một tài khoản, không phải tình trạng throttling của dependency. Khi đó không nên retry. Tương tự, 503 có thể là maintenance có lịch; retry liên tục không giúp ích. Với 429/503 có header Retry-After, decoder nên đọc và truyền thời điểm retry vào RetryableException để Retryer tôn trọng thời gian server yêu cầu. Mẫu trên để null cho thời điểm retry nên dùng backoff cục bộ; khi triển khai thực tế, cần bổ sung xử lý Retry-After nếu API cung cấp header này.

ErrorDecoder chỉ xử lý HTTP response lỗi. Lỗi kết nối như DNS failure, connection refused hoặc socket timeout xảy ra trước khi có response thường do HTTP client ném exception. Các lỗi transport có thể đã được Feign chuyển thành RetryableException tùy loại lỗi và client được sử dụng; cần kiểm tra hành vi thực tế của phiên bản và transport đang chạy.

## 4. Spring Cloud OpenFeign mặc định không retry

Feign core và Spring Cloud OpenFeign có mặc định khác nhau. Feign core có Retryer mặc định có khả năng retry một số lỗi. Spring Cloud OpenFeign đăng ký Retryer.NEVER_RETRY theo mặc định, nghĩa là không tự retry các request thất bại.

Điều này có chủ đích: retry có thể nhân số request trong lúc dependency đang quá tải và gây lặp thao tác nghiệp vụ. Nếu muốn retry, cần khai báo Retryer một cách tường minh và có giới hạn.

Ví dụ cấu hình Retryer riêng cho Catalog client:

~~~java
import feign.Retryer;
import org.springframework.context.annotation.Bean;

public class CatalogFeignConfiguration {
    @Bean
    Retryer catalogRetryer() {
        // period=100 ms, maxPeriod=1000 ms, maxAttempts=3
        return new Retryer.Default(100, 1000, 3);
    }

    @Bean
    ErrorDecoder catalogErrorDecoder() {
        return new CatalogErrorDecoder();
    }
}
~~~

Gắn cấu hình vào đúng client:

~~~java
@FeignClient(
    name = "catalogClient",
    configuration = CatalogFeignConfiguration.class
)
public interface CatalogClient {
    @GetMapping("/products/{id}")
    Product findById(@PathVariable("id") String id);
}
~~~

Trong cấu hình này, Retryer.Default chỉ retry khi nhận RetryableException. ErrorDecoder ở phần trước quyết định status nào tạo ra exception đó. Các exception 404, validation và credential không phải RetryableException nên không bị Retryer này thử lại.

Cấu hình client riêng nên được giữ ngoài phạm vi component scan toàn ứng dụng nếu không muốn áp dụng nhầm cho các Feign client khác. Nếu cấu hình này bị đăng ký toàn cục, các client không liên quan cũng có thể nhận cùng ErrorDecoder và Retryer.

## 5. Hiểu số lần thử và backoff

Tham số của Retryer.Default gồm:

- period: khoảng chờ ban đầu trước lần thử tiếp theo.
- maxPeriod: khoảng backoff tối đa.
- maxAttempts: số lần thử tối đa theo định nghĩa của Feign Retryer.

Với Retryer.Default, maxAttempts bằng 3 là tối đa ba lần thực hiện tổng cộng, gồm lần đầu và tối đa hai lần retry. Hãy xác nhận bằng log số attempt khi kiểm thử và đọc đúng semantics của Retryer nếu dùng implementation khác.

Backoff làm giảm tốc độ retry đồng loạt. Nếu nhiều instance cùng gặp lỗi, retry ngay lập tức có thể tạo một đợt tải mới lên dependency. Với hệ thống có lưu lượng lớn, nên có jitter để phân tán thời điểm thử lại; đồng thời tôn trọng Retry-After nếu server trả header đó.

Không retry vô hạn. Khi hết số lần thử, Retryer ném lại exception để tầng gọi xử lý. Nếu Circuit Breaker bao quanh Feign invocation, kết quả cuối cùng đó sẽ được dùng để ghi nhận thành công hoặc thất bại của lời gọi.

## 6. Retry và Circuit Breaker phối hợp theo thứ tự nào?

Khi bật Circuit Breaker cho OpenFeign, Spring Cloud OpenFeign bọc lời gọi Feign bằng Circuit Breaker. Bên trong lời gọi Feign, Retryer điều khiển các attempt của cùng một invocation. Vì vậy, thông thường Circuit Breaker quan sát kết quả cuối cùng của invocation sau khi Feign đã hoàn tất retry.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi Feign method"] --> B["Spring Cloud Circuit Breaker"]
    B --> C["Feign invocation"]
    C --> D["HTTP request với connect/read timeout"]
    D --> E{"Response hoặc lỗi"}
    E -- "Lỗi retryable" --> F["ErrorDecoder hoặc transport tạo RetryableException"]
    F --> G{"Retryer còn attempt?"}
    G -- "Có" --> H["Backoff rồi gửi attempt tiếp"]
    H --> D
    G -- "Không" --> I["Trả exception cuối cùng"]
    E -- "Thành công hoặc lỗi không retry" --> J["Kết quả cuối invocation"]
    I --> J
    J --> K["Circuit Breaker ghi nhận kết quả"]
    K --> L["Fallback hoặc trả kết quả"]
~~~

Điều này có nghĩa một invocation có thể tạo nhiều HTTP attempt nhưng Circuit Breaker thường ghi nhận một kết quả cuối cho invocation đó. Nếu lần đầu 503, lần hai thành công, breaker thấy invocation thành công. Nếu tất cả attempt đều thất bại, breaker ghi nhận invocation thất bại.

Khi breaker OPEN, lời gọi có thể bị từ chối trước khi Feign gửi request; lúc này Retryer không có cơ hội retry vì Feign invocation chưa chạy. Không retry CallNotPermittedException ở tầng ứng dụng vì việc đó chỉ tạo thêm lời gọi bị từ chối.

Tránh đặt thêm một vòng retry bên ngoài Circuit Breaker mà không tính toán. Nếu tầng service retry toàn bộ invocation, mỗi vòng có thể đi qua breaker riêng và làm số lần gọi tăng theo cấp số nhân. Chọn một tầng sở hữu chính sách retry và giới hạn tổng attempt.

## 7. Tính deadline khi có nhiều attempt

Timeout của từng attempt không phải deadline của toàn bộ invocation. Tổng thời gian có thể xấp xỉ:

~~~text
T_total <= N × (T_connect + T_read) + T_backoff + T_overhead
~~~

Đây là cách ước lượng bảo thủ; thời gian thực tế phụ thuộc thời điểm timeout, loại lỗi và HTTP client. Ví dụ, ba attempt với read timeout 1.200 ms cùng backoff có thể vượt quá deadline 2 giây của API caller.

Trước khi bật retry, hãy tính:

1. Deadline của caller hoặc API gateway.
2. Connect timeout và read timeout của một attempt.
3. Số attempt tối đa.
4. Backoff giữa các attempt và thời gian Retry-After.
5. Thời gian dành cho Circuit Breaker fallback và serialize response.

Nếu tổng thời gian có thể vượt deadline, hãy giảm timeout hoặc số attempt. Không để Feign tiếp tục retry sau khi caller đã hủy request hoặc deadline đầu cuối đã hết.

## 8. Chỉ retry thao tác an toàn

Retry có thể làm cùng một request được gửi nhiều lần. Với GET đọc dữ liệu, việc lặp thường an toàn hơn. Với POST tạo đơn hàng, thanh toán hoặc giữ chỗ, request có thể đã được xử lý ở server nhưng response bị mất. Nếu client retry, thao tác có thể được thực hiện lần thứ hai.

Trước khi retry thao tác ghi, cần có một trong các bảo đảm:

- API hỗ trợ idempotency key và server lưu kết quả theo key.
- Thao tác có semantics idempotent được tài liệu hóa.
- Có cơ chế tra soát trạng thái bằng transaction ID trước khi gửi lại.
- Retry chỉ áp dụng cho lỗi xảy ra chắc chắn trước khi server thực hiện thao tác.

Không suy diễn timeout đồng nghĩa server chưa xử lý request. Với thanh toán, nếu không biết giao dịch đã được chấp nhận hay chưa, hãy trả trạng thái chưa xác định và tra soát thay vì tự động gửi lại một giao dịch mới.

## 9. Bật Circuit Breaker cho OpenFeign

Để Spring Cloud OpenFeign tích hợp với Spring Cloud CircuitBreaker, bật thuộc tính:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Ứng dụng cần có starter CircuitBreaker implementation tương ứng, ví dụ Resilience4j, cùng starter OpenFeign. Khi bật, các lời gọi Feign được bọc bằng Circuit Breaker. Có thể cấu hình fallback hoặc fallbackFactory cho từng client để trả kết quả thay thế khi invocation thất bại hoặc breaker từ chối lời gọi.

Ví dụ:

~~~java
@FeignClient(
    name = "catalogClient",
    configuration = CatalogFeignConfiguration.class,
    fallbackFactory = CatalogFallbackFactory.class
)
public interface CatalogClient {
    @GetMapping("/products/{id}")
    Product findById(@PathVariable("id") String id);
}
~~~

FallbackFactory cho phép xem nguyên nhân invocation thất bại để chọn kết quả phù hợp. Không biến mọi lỗi thành một đối tượng Product giả. Nếu dữ liệu cache không có hoặc fallback cũng lỗi, hãy trả lỗi dịch vụ không khả dụng theo hợp đồng API.

Tên Circuit Breaker được tạo từ Feign client và method theo naming strategy của Spring Cloud OpenFeign. Khi cấu hình Resilience4j instance hoặc xem metric, hãy kiểm tra tên breaker thực tế mà ứng dụng đang tạo; không giả định tên chỉ là service ID.

## 10. Phân loại lỗi để không retry sai

Một chính sách retry có thể bắt đầu từ bảng sau:

| Loại lỗi | ErrorDecoder/transport | Retry? | Circuit Breaker |
|---|---|---|---|
| 404 không tìm thấy | ProductNotFoundException | Không | Bỏ qua nếu là kết quả nghiệp vụ hợp lệ |
| 400/422 | Request exception | Không | Không tính là lỗi availability nếu request hợp lệ theo hợp đồng |
| 401/403 | Credential exception | Không tự retry | Cảnh báo lỗi cấu hình/quyền; quyết định ghi nhận riêng |
| 429 throttling | RetryableException nếu có thể phục hồi | Có giới hạn, tôn trọng Retry-After | Kết quả cuối thất bại được ghi nhận theo cấu hình |
| 503 tạm thời | RetryableException theo chính sách | Có giới hạn | Nếu hết retry vẫn lỗi, ghi nhận failure |
| 502/504 | Theo ErrorDecoder hoặc transport | Có thể retry có giới hạn | Ghi nhận kết quả cuối |
| DNS/connect/read timeout | Transport exception | Chỉ retry nếu loại lỗi được hỗ trợ và thao tác an toàn | Ghi nhận lỗi/slow call cuối |
| CallNotPermittedException | Breaker đang OPEN | Không | Đã bị breaker từ chối |
| Bulkhead rejection | Không còn slot cục bộ | Không retry ngay | Theo dõi riêng, không nhầm là dependency failure |

Không phải mọi exception cần được tính giống nhau trong failure rate. Có thể cấu hình Resilience4j để bỏ qua exception nghiệp vụ hoặc credential đã phân loại, nhưng không bỏ qua timeout và lỗi kết nối nếu muốn breaker phát hiện dependency suy giảm.

## 11. Kiểm tra cấu hình và hành vi retry

Một bài kiểm tra nên quan sát cả số HTTP attempt và số invocation của Circuit Breaker:

1. Trả 200: một attempt, kết quả thành công.
2. Trả 404: ErrorDecoder tạo exception nghiệp vụ; không có attempt retry.
3. Trả 503 rồi 200: ErrorDecoder tạo RetryableException, Retryer thử lại, invocation cuối thành công.
4. Trả 503 liên tục: số attempt không vượt maxAttempts; exception cuối được truyền tới Circuit Breaker.
5. Trả 429 kèm Retry-After: xác nhận Retryer chờ đúng chính sách được thiết kế.
6. Gây read timeout: xác nhận timeout mỗi attempt và tổng thời gian không vượt deadline.
7. Mở Circuit Breaker: lời gọi bị từ chối trước khi có HTTP request mới; Retryer không chạy.
8. Gọi một POST không idempotent: xác nhận không tự retry khi chưa có idempotency key hoặc cơ chế tra soát.

Ghi log method key, status, attempt number, thời gian chờ, exception class và breaker state. Tránh ghi Authorization header, token, dữ liệu thanh toán hoặc payload nhạy cảm. Metric nên tách số HTTP attempt khỏi số Feign invocation; nếu chỉ nhìn một trong hai, có thể đánh giá sai mức tải thực tế lên dependency.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Feign không retry dù ErrorDecoder trả lỗi | Spring Cloud OpenFeign dùng Retryer.NEVER_RETRY mặc định | Khai báo Retryer riêng cho client |
| 404 bị retry | ErrorDecoder biến lỗi nghiệp vụ thành RetryableException | Trả exception không retry cho 404 |
| 503 retry quá nhiều | maxAttempts hoặc backoff quá lớn | Giảm attempt, thêm backoff/jitter và tính deadline |
| Request vượt thời gian gateway | Timeout mỗi attempt nhân với số lần retry | Tính tổng ngân sách trước khi bật retry |
| POST tạo dữ liệu trùng | Retry thao tác không idempotent | Dùng idempotency key hoặc tra soát trạng thái |
| Circuit Breaker mở chậm dù có nhiều HTTP retry | Breaker ghi nhận kết quả invocation sau vòng retry nội bộ | Theo dõi cả attempt và invocation; điều chỉnh retry/window có chủ đích |
| Cấu hình retry áp dụng cho mọi client | Feign configuration bị scan toàn cục | Giới hạn cấu hình vào đúng client |

## Kết luận

Timeout giới hạn thời gian của từng lần gọi; ErrorDecoder phân loại HTTP response thành exception; Retryer chỉ thử lại những lỗi được đánh dấu có thể retry và phải có giới hạn. Spring Cloud OpenFeign mặc định không retry, vì vậy cần cấu hình tường minh theo từng client nếu thực sự cần. Khi phối hợp Circuit Breaker, hãy hiểu retry nằm bên trong một Feign invocation, tính tổng thời gian qua mọi attempt và backoff, chỉ retry thao tác an toàn, đồng thời để breaker quan sát kết quả cuối cùng. Cách phối hợp này giúp giảm lỗi dây chuyền mà vẫn giữ đúng ngữ nghĩa nghiệp vụ và deadline của request.

