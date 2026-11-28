# Retry có giới hạn với lỗi tạm thời

Tool calling có thể phụ thuộc vào nhiều dịch vụ bên ngoài: database, HTTP API, hệ thống vận chuyển, thanh toán hoặc model provider. Những dịch vụ này đôi khi lỗi tạm thời do mạng chập chờn, quá tải hoặc giới hạn lưu lượng. Retry giúp thử lại khi lỗi có khả năng tự hết, nhưng retry không giới hạn có thể làm hệ thống quá tải hơn, kéo dài request và lặp lại thao tác ghi.

Một chính sách retry an toàn cần trả lời bốn câu hỏi: lỗi nào được phép thử lại, tối đa bao nhiêu lần, chờ bao lâu giữa các lần thử và request còn đủ thời gian hay không. Với tool có tác động ghi dữ liệu, còn phải xác định thao tác có thể lặp lại an toàn hay cần idempotency key.

## Sau bài học, bạn có thể

- Phân biệt lỗi tạm thời với lỗi nghiệp vụ hoặc lỗi cấu hình không nên retry.
- Chọn đúng lớp để retry: model provider, HTTP/database client hay service được tool gọi.
- Giới hạn số lần thử, thời gian backoff và tổng thời gian thực thi.
- Dùng exponential backoff và jitter để giảm các đợt retry đồng loạt.
- Tôn trọng `Retry-After` khi upstream yêu cầu giãn cách.
- Kết hợp retry với deadline của toàn request.
- Bảo vệ thao tác ghi bằng idempotency key và cơ chế đối soát.
- Kiểm thử retry, exhausted attempts, cancellation và hành vi khi có nhiều request đồng thời.

## Retry giải quyết vấn đề gì?

Một lỗi tạm thời có thể biến mất nếu thử lại sau một khoảng ngắn. Ví dụ:

- Kết nối TCP bị reset trong lúc dịch vụ đích đang khởi động lại.
- API trả HTTP 503 do đang quá tải trong thời gian ngắn.
- API trả HTTP 429 và yêu cầu client giảm tốc độ.
- Một lần truy vấn gặp lỗi kết nối database tạm thời.
- Model provider bị timeout hoặc lỗi gateway trong một lần gọi.

Ngược lại, retry không thể sửa một yêu cầu sai hoặc một chính sách bị từ chối. Nếu model tạo JSON sai schema, người dùng không có quyền truy cập tài nguyên hoặc mã đơn hàng không tồn tại, thử lại cùng đầu vào thường chỉ tạo thêm tải mà không thay đổi kết quả.

Retry cần có giới hạn. Mục tiêu là tăng khả năng hoàn thành khi lỗi thực sự tạm thời, đồng thời giữ thời gian và tải hệ thống trong ngân sách có thể dự đoán.

## Phân loại lỗi trước khi retry

Không quyết định retry chỉ dựa vào việc có exception. Hãy ánh xạ lỗi từ thư viện hoặc upstream thành nhóm lỗi mà ứng dụng hiểu.

| Loại lỗi | Ví dụ | Retry? | Lý do |
|---|---|---:|---|
| Lỗi kết nối tạm thời | Connection reset, DNS tạm thời, connection refused trong lúc restart | Có điều kiện | Có thể tự phục hồi |
| Timeout khi đọc dịch vụ | Upstream phản hồi chậm | Có điều kiện | Chỉ thử lại nếu còn deadline và thao tác an toàn |
| HTTP 429 | Rate limit | Có, theo chính sách | Tôn trọng `Retry-After` và giới hạn tải |
| HTTP 502/503/504 | Gateway hoặc dịch vụ tạm thời không sẵn sàng | Có điều kiện | Thường là lỗi tạm thời |
| HTTP 400/422 | Payload hoặc tham số không hợp lệ | Không | Cần sửa dữ liệu hoặc schema |
| HTTP 401/403 | Chưa xác thực hoặc không đủ quyền | Không | Retry không cấp thêm quyền |
| HTTP 404 | Tài nguyên không tồn tại | Thường không | Có thể là kết quả nghiệp vụ hợp lệ |
| HTTP 409 | Xung đột trạng thái hoặc phiên bản | Không mặc định | Cần đọc lại trạng thái hoặc xử lý conflict |
| Lỗi validation nghiệp vụ | Số lượng âm, trạng thái không cho phép | Không | Đầu vào hoặc quy tắc không hợp lệ |
| Lỗi cấu hình | API key sai, endpoint sai | Không | Cần sửa cấu hình |
| Lỗi serialization/schema | Không thể parse response | Không mặc định | Có thể là lỗi hợp đồng, không phải lỗi mạng |

Các mã HTTP chỉ là tín hiệu ban đầu. Một số API dùng 404 cho tài nguyên tạm thời chưa được đồng bộ, hoặc dùng 409 cho một tình huống có thể thử lại sau khi đọc trạng thái mới. Hãy theo hợp đồng của dịch vụ thay vì áp dụng danh sách mã chung một cách máy móc.

Nên tạo exception có ý nghĩa trong ứng dụng, ví dụ `TransientShippingException`, `PermanentRequestException` hoặc `RateLimitException`. Lớp retry chỉ xử lý nhóm lỗi được cho phép, thay vì bắt mọi `Exception`.

## Chọn đúng nơi đặt retry

Trong một ứng dụng Spring AI, có thể có nhiều lớp thực hiện request:

~~~mermaid
flowchart TD
    A[ChatClient / ToolCallingAdvisor] --> B[Model provider client]
    A --> C[ToolCallback]
    C --> D[Service nghiệp vụ]
    D --> E[HTTP client / database client]
    B --> F[Retry của model provider]
    E --> G[Retry của dependency]
    D --> H[Quy tắc retry nghiệp vụ]
~~~

Mỗi lớp có trách nhiệm riêng:

- **Model provider client:** retry request tới model theo cấu hình của integration đang dùng.
- **HTTP/database client:** xử lý lỗi kết nối hoặc phản hồi tạm thời ở tầng transport.
- **Service được tool gọi:** áp dụng retry có hiểu biết về nghiệp vụ, deadline và idempotency.
- **Tool-calling loop:** điều phối model và tool. Không nên retry toàn bộ hội thoại chỉ vì một dependency bên trong tool gặp lỗi tạm thời.

Ví dụ tool `getShippingStatus` gọi một API vận chuyển. Nếu API bị reset kết nối, retry nên nằm trong `ShippingService` hoặc client của nó. Khi service trả kết quả, callback hoàn thành một lần và tool-calling loop tiếp tục bình thường.

Nếu retry toàn bộ `ChatClient.call()`, ứng dụng có thể gọi model lại, tạo tool call mới và thực thi lại các thao tác đã thành công trước đó. Cách này tăng chi phí token và có thể gây tác dụng phụ trùng lặp.

### Phân biệt retry model với retry tool

Cấu hình retry của model provider không tự động áp dụng cho HTTP client mà tool sử dụng. Ngược lại, retry trong service tool không làm model request được thử lại.

Ví dụ cấu hình OpenAI chat model trong Spring AI:

~~~yaml
spring:
  ai:
    openai:
      timeout: 8s
      max-retries: 1
~~~

Các property trên thuộc integration OpenAI; provider khác có cấu hình riêng. `max-retries` là số lần thử lại bổ sung theo cách provider integration định nghĩa, nên hãy kiểm tra tài liệu phiên bản đang dùng và tính tổng số lần gọi thực tế.

Không đặt retry ở nhiều tầng mà không tính tổng. Nếu model client có 2 lần thử và tool HTTP client có 3 lần thử, một request có thể tạo nhiều request outbound hơn dự kiến. Ghi rõ retry budget ở từng lớp.

## Giới hạn số lần thử

Một chính sách cần giới hạn số lần thử tối đa. Trong hầu hết cấu hình, `maxAttempts` nên được hiểu là tổng số lần gọi, bao gồm lần đầu tiên.

Ví dụ:

| Cấu hình | Ý nghĩa |
|---|---|
| `maxAttempts = 1` | Chỉ gọi một lần, không retry |
| `maxAttempts = 2` | Một lần đầu và tối đa một lần retry |
| `maxAttempts = 3` | Một lần đầu và tối đa hai lần retry |

Không nhầm số lần retry với tổng số lần thử. Tên property giữa thư viện có thể khác nhau: một thư viện nhận `maxAttempts`, thư viện khác nhận `maxRetries`. Hãy kiểm tra ý nghĩa chính xác trước khi cấu hình.

Với dependency quan trọng, bắt đầu bằng số lần thử nhỏ, thường là 2 hoặc 3 tổng lần thử. Nếu dịch vụ vẫn lỗi sau giới hạn, dừng và trả lỗi có cấu trúc để tầng trên xử lý.

## Exponential backoff và jitter

Thử lại ngay lập tức có thể làm dịch vụ đang quá tải nhận thêm một đợt request dồn dập. Exponential backoff tăng dần khoảng chờ sau mỗi lần thất bại.

Ví dụ với thời gian ban đầu 200 ms và hệ số nhân 2:

| Lần thử tiếp theo | Backoff trước jitter |
|---|---:|
| Sau lần thử 1 | 200 ms |
| Sau lần thử 2 | 400 ms |
| Sau lần thử 3 | 800 ms |
| Sau lần thử 4 | 1.600 ms |

Cần đặt một mức trần để backoff không tăng vô hạn. Jitter thêm một khoảng ngẫu nhiên để các client không đồng loạt retry cùng thời điểm. Một công thức full jitter thường dùng:

`delay = random(0, min(maxDelay, initialDelay × 2^(attempt - 1)) )`

Ví dụ với `initialDelay=200 ms` và `maxDelay=2 s`, lần retry thứ ba có khoảng chờ ngẫu nhiên từ 0 đến 800 ms, thay vì tất cả client cùng chờ đúng 800 ms.

Không dùng backoff dài hơn thời gian request còn lại. Nếu request chỉ còn 300 ms nhưng chính sách đề xuất chờ 800 ms, không nên ngủ rồi gọi dependency sau khi deadline đã hết.

## Ví dụ dùng Spring Retry

Spring Retry cung cấp `RetryTemplate` để đóng gói số lần thử, loại exception được retry và backoff policy. Ví dụ dưới đây retry một lỗi tạm thời của dịch vụ vận chuyển:

~~~java
import org.springframework.retry.backoff.ExponentialRandomBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Bean
RetryTemplate shippingRetryTemplate() {
    ExponentialRandomBackOffPolicy backOffPolicy =
            new ExponentialRandomBackOffPolicy();

    backOffPolicy.setInitialInterval(200L);
    backOffPolicy.setMultiplier(2.0);
    backOffPolicy.setMaxInterval(2_000L);

    SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(
            3,
            Map.of(TransientShippingException.class, true)
    );

    RetryTemplate template = new RetryTemplate();
    template.setBackOffPolicy(backOffPolicy);
    template.setRetryPolicy(retryPolicy);

    return template;
}
~~~

Sử dụng trong service:

~~~java
@Service
public class ShippingService {

    private final ShippingGateway shippingGateway;
    private final RetryTemplate shippingRetryTemplate;

    public ShippingService(
            ShippingGateway shippingGateway,
            RetryTemplate shippingRetryTemplate) {
        this.shippingGateway = shippingGateway;
        this.shippingRetryTemplate = shippingRetryTemplate;
    }

    public ShippingSnapshot getStatus(String orderId) {
        return shippingRetryTemplate.execute(
                context -> shippingGateway.fetchStatus(orderId)
        );
    }
}
~~~

Trong cấu hình này:

- `SimpleRetryPolicy(3, ...)` cho phép tối đa ba lần thử tổng cộng.
- Chỉ `TransientShippingException` được retry.
- `ExponentialRandomBackOffPolicy` tăng thời gian chờ theo cấp số nhân và thêm ngẫu nhiên.
- Nếu hết số lần thử, exception cuối cùng được ném ra cho caller.

Hãy phân loại exception ở `ShippingGateway` để chỉ ánh xạ lỗi thực sự tạm thời thành `TransientShippingException`. Không bọc mọi lỗi thành exception này, nếu không lỗi validation hoặc quyền truy cập cũng sẽ bị retry.

Spring Retry cần dependency tương ứng trong dự án. Nếu ứng dụng dùng Resilience4j hoặc retry mechanism của HTTP client, có thể dùng cơ chế đó thay thế; tránh bọc nhiều retry policy chồng lên nhau mà không có ngân sách tổng.

## Kết hợp retry với deadline toàn request

Retry phải tôn trọng deadline của request. Mỗi lần thử, thời gian còn lại giảm; cả backoff cũng tiêu thụ ngân sách.

Một quy trình phù hợp:

1. Kiểm tra deadline trước khi bắt đầu lần thử.
2. Tính timeout hiệu lực bằng giá trị nhỏ hơn giữa timeout của dependency và thời gian request còn lại.
3. Gọi dependency với timeout đó.
4. Nếu lỗi thuộc nhóm retryable và còn attempt, tính backoff.
5. Chỉ chờ nếu còn đủ thời gian cho backoff và ít nhất một lần thử có ý nghĩa.
6. Trước lần thử tiếp theo, kiểm tra deadline lại.

Ví dụ logic minh họa:

~~~text
for attempt from 1 to maxAttempts:
    if request deadline has expired:
        stop with REQUEST_DEADLINE_EXCEEDED

    timeout = min(toolTimeout, requestTimeRemaining)

    try:
        return callDependency(timeout)

    catch error:
        if error is not retryable or attempt == maxAttempts:
            rethrow error

        delay = exponentialBackoffWithJitter(attempt)

        if delay + minimumUsefulAttemptTime >= requestTimeRemaining:
            stop with the original error or deadline error

        wait(delay)
~~~

`RetryTemplate` ở ví dụ trước không tự biết deadline của request. Nếu dùng nó trong luồng có deadline nghiêm ngặt, hãy tích hợp kiểm tra budget ở từng lần thử và backoff, hoặc dùng retry policy có khả năng tính thời gian còn lại. Đừng chỉ kiểm tra deadline trước khi gọi `RetryTemplate.execute()`, vì các lần retry và backoff bên trong có thể vượt quá deadline.

Không tạo deadline mới ở mỗi lần retry. Tất cả attempt của một tool và các tool trong cùng request phải dùng chung budget do ứng dụng tạo ở đầu request.

## Tôn trọng Retry-After

Một số dịch vụ trả HTTP 429 hoặc 503 kèm header `Retry-After`. Header có thể biểu diễn số giây cần chờ hoặc một HTTP date. Khi upstream đưa ra thời điểm thử lại, client nên cân nhắc tuân thủ thay vì retry sớm hơn.

Quy tắc:

- Parse header theo định dạng HTTP hợp lệ.
- Không chờ vượt deadline của request.
- Áp dụng mức chờ tối đa do ứng dụng quy định.
- Nếu `Retry-After` lớn hơn thời gian còn lại, dừng và trả lỗi rate limit/deadline.
- Không retry trước thời điểm upstream cho phép chỉ vì backoff cục bộ ngắn hơn.

Không phải mọi upstream đều cung cấp header này. Nếu thiếu, dùng backoff policy của ứng dụng. Ghi lại số lần nhận 429 và thời gian chờ để điều chỉnh rate limit hoặc concurrency.

## Chỉ retry thao tác có thể lặp lại an toàn

Retry một truy vấn đọc thường an toàn hơn retry một thao tác ghi. Nếu client gửi yêu cầu tạo thanh toán, server có thể đã xử lý thành công nhưng response bị mất. Client thấy timeout và gửi lại có thể tạo giao dịch thứ hai.

Trước khi retry thao tác ghi, cần có cơ chế idempotency:

- Tạo một idempotency key ổn định cho cùng một ý định nghiệp vụ.
- Gửi cùng key trong tất cả attempt của cùng thao tác.
- Server lưu key cùng kết quả xử lý và trả lại kết quả cũ khi nhận request trùng.
- Không tạo key mới ở mỗi lần retry.
- Lưu trạng thái thao tác để có thể đối soát khi kết quả không xác định.

Ví dụ:

~~~java
public PaymentResult createPayment(
        CreatePaymentCommand command,
        String idempotencyKey) {

    return paymentGateway.createPayment(
            command,
            idempotencyKey
    );
}
~~~

Key phải được tạo ở application layer và giữ ổn định cho cùng một thao tác. Không dùng riêng tool call ID mới do model sinh ra làm idempotency key nếu mỗi lần model retry có thể tạo ID khác. Hãy gắn key với request nghiệp vụ hoặc operation ID do server quản lý.

Nếu upstream không hỗ trợ idempotency, không tự động retry một thao tác ghi sau timeout không rõ kết quả. Trước tiên hãy tra cứu trạng thái bằng operation reference hoặc đưa giao dịch vào quy trình đối soát.

## Xử lý khi retry đã hết lượt

Khi đã hết số lần thử, ứng dụng cần dừng và trả lỗi có thể xử lý. Không tiếp tục retry ở tầng khác mà không có chủ đích.

Một kết quả lỗi an toàn có thể chứa:

- Mã lỗi ổn định, ví dụ `SHIPPING_PROVIDER_UNAVAILABLE`.
- Tên dependency hoặc tool đã thất bại.
- Có thể retry sau hay không.
- Mã tương quan để tra log.
- Trạng thái thao tác nếu kết quả có thể chưa xác định.

Không đưa stack trace, secret, URL nội bộ hoặc payload nhạy cảm vào nội dung tool result gửi cho model. Nếu muốn model giải thích lỗi, chỉ trả thông tin đã làm sạch. Không yêu cầu model tự gọi lại tool liên tục; retry kỹ thuật nên được thực hiện trong service theo policy có giới hạn.

Phân biệt các trường hợp:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Retry thành công | Một attempt sau hoàn tất | Trả kết quả bình thường |
| Hết attempt | Lỗi tạm thời vẫn còn | Trả lỗi dependency unavailable |
| Hết deadline | Không còn thời gian cho attempt/backoff | Dừng request |
| Lỗi không retryable | Validation, quyền, cấu hình | Trả lỗi ngay |
| Kết quả ghi không xác định | Có thể server đã commit nhưng response mất | Đối soát bằng operation ID |

## Retry và circuit breaker

Retry xử lý lỗi ngắn hạn bằng cách thử lại. Circuit breaker bảo vệ hệ thống khi dependency liên tục lỗi bằng cách tạm ngừng gửi request mới trong một khoảng thời gian.

Hai cơ chế giải quyết vấn đề khác nhau:

- Retry giúp một request vượt qua lỗi tạm thời.
- Circuit breaker ngăn nhiều request tiếp tục dồn tải vào dependency đang hỏng.
- Rate limiter kiểm soát tốc độ gửi request.
- Bulkhead giới hạn tài nguyên dành cho một dependency hoặc nhóm tool.

Với dependency quan trọng, có thể kết hợp circuit breaker và retry nhưng cần xác định thứ tự decorator. Nếu retry nằm bên trong circuit breaker, circuit breaker có thể ghi nhận kết quả cuối của toàn bộ chuỗi retry. Nếu circuit breaker nằm bên trong retry, mỗi attempt có thể được tính như một lời gọi riêng. Chọn cách phù hợp với metric và chính sách mở mạch của ứng dụng.

Không dùng retry để che giấu một dependency đang hỏng kéo dài. Khi circuit breaker mở, trả lỗi nhanh và để ứng dụng có fallback phù hợp.

## Kiểm thử chính sách retry

Kiểm thử cần xác minh cả số lần gọi, loại lỗi và thời gian chờ. Không cần gọi dịch vụ bên ngoài thật.

Các trường hợp nên có:

- Lần đầu lỗi transient, lần thứ hai thành công.
- Tất cả attempt đều lỗi transient và dừng đúng `maxAttempts`.
- Lỗi validation hoặc authorization không được retry.
- HTTP 429 tôn trọng `Retry-After`.
- Backoff không vượt mức trần.
- Jitter tạo khoảng chờ khác nhau trong phạm vi cho phép.
- Deadline hết trước lần thử kế tiếp thì không gửi thêm request.
- Retry của thao tác ghi dùng cùng idempotency key.
- Timeout không rõ kết quả không tạo giao dịch trùng.
- Nhiều request đồng thời không chia sẻ bộ đếm hoặc trạng thái retry.

Ví dụ unit test service với gateway giả:

~~~java
@Test
void shouldRetryTransientFailureAndThenSucceed() {
    AtomicInteger calls = new AtomicInteger();

    when(shippingGateway.fetchStatus("DH-1024"))
            .thenAnswer(invocation -> {
                if (calls.incrementAndGet() == 1) {
                    throw new TransientShippingException("temporary reset");
                }
                return expectedSnapshot;
            });

    ShippingSnapshot result = shippingService.getStatus("DH-1024");

    assertThat(result).isEqualTo(expectedSnapshot);
    assertThat(calls.get()).isEqualTo(2);
}
~~~

Test này minh họa logic lần đầu thất bại và lần sau thành công. Với test backoff, dùng policy có clock/sleeper giả hoặc cấu hình thời gian nhỏ để tránh làm test chậm và không ổn định. Không dùng `Thread.sleep()` dài trong unit test.

Một test khác xác minh lỗi vĩnh viễn không bị retry:

~~~java
@Test
void shouldNotRetryValidationFailure() {
    when(shippingGateway.fetchStatus("DH-1024"))
            .thenThrow(new InvalidShippingRequestException("invalid order"));

    assertThatThrownBy(() -> shippingService.getStatus("DH-1024"))
            .isInstanceOf(InvalidShippingRequestException.class);

    verify(shippingGateway, times(1)).fetchStatus("DH-1024");
}
~~~

Ngoài unit test, thêm integration test với mock server để xác minh mapping HTTP 429/503, header `Retry-After`, timeout và idempotency key thực sự được gửi đúng.

## Quan sát và vận hành

Ghi metric để biết retry có giúp phục hồi hay chỉ làm tăng tải:

- Số lần retry theo tool và dependency.
- Số attempt trung bình và tỷ lệ thành công sau retry.
- Số lần retry exhausted.
- Thời gian backoff tổng.
- Số lỗi 429/5xx và timeout.
- Số request dừng do hết deadline.
- Số thao tác ghi cần đối soát.
- Trạng thái circuit breaker nếu có.

Log nên có request ID, tool name, dependency, attempt number, loại lỗi và thời gian chờ. Không log token, mật khẩu, toàn bộ payload khách hàng hoặc idempotency key nếu key có thể được dùng để truy cập thao tác. Dùng correlation ID để liên kết các attempt thuộc cùng một nghiệp vụ.

Nếu tỷ lệ retry tăng liên tục, hãy xem đó là tín hiệu cần điều tra capacity, rate limit hoặc chất lượng kết nối. Tăng số lần retry không phải cách xử lý lâu dài cho một dịch vụ đang quá tải.

## Những lỗi thường gặp

- **Retry mọi exception:** lỗi quyền, validation và cấu hình không tự hết. Chỉ retry exception đã phân loại là tạm thời.
- **Retry ngay lập tức:** tạo retry storm. Dùng backoff và jitter.
- **Không giới hạn số lần thử:** request có thể treo lâu và tạo tải vô hạn. Đặt max attempts và deadline.
- **Nhầm maxRetries với maxAttempts:** số lần gọi thực tế có thể nhiều hơn dự kiến. Ghi rõ lần đầu có được tính hay không.
- **Retry toàn bộ ChatClient vì tool dependency lỗi:** có thể gọi model và thực thi tool đã thành công thêm lần nữa. Retry ở service gần dependency.
- **Retry ở nhiều tầng mà không tính tổng:** số request outbound nhân lên. Có một retry budget được ghi rõ.
- **Bỏ qua Retry-After:** client tiếp tục gửi request sớm khi upstream yêu cầu chờ.
- **Retry thao tác ghi mà không có idempotency:** có thể tạo giao dịch hoặc bản ghi trùng.
- **Không tính backoff vào deadline:** lần thử tiếp theo bắt đầu sau khi người dùng đã hết thời gian chờ.
- **Dùng trạng thái retry mutable singleton:** request đồng thời có thể ảnh hưởng nhau. Dùng context riêng cho mỗi lần thực thi.
- **Để model tự retry vô hạn:** retry kỹ thuật phải nằm trong policy có giới hạn ở backend.

## Checklist trước khi phát hành

- [ ] Đã phân loại lỗi transient và permanent theo hợp đồng dependency.
- [ ] Retry chỉ áp dụng cho exception/mã lỗi được cho phép.
- [ ] Đã xác định maxAttempts và làm rõ nó gồm lần đầu.
- [ ] Backoff tăng dần, có mức trần và jitter.
- [ ] Đã xử lý `Retry-After` khi upstream cung cấp.
- [ ] Retry dùng chung deadline của request và không vượt ngân sách.
- [ ] Retry đặt ở đúng tầng, không lặp lại toàn bộ hội thoại không cần thiết.
- [ ] Các lớp retry chồng nhau đã được tính tổng số attempt.
- [ ] Thao tác ghi có idempotency key hoặc quy trình đối soát.
- [ ] Lỗi sau khi hết attempt được chuyển thành kết quả an toàn.
- [ ] Có metric và log cho attempt, backoff, exhausted và deadline.
- [ ] Có test cho transient, permanent, max attempts, deadline và idempotency.

## Ghi nhớ khi thiết kế

Retry chỉ phù hợp với lỗi tạm thời và thao tác có thể lặp lại an toàn. Hãy phân loại lỗi trước, giới hạn tổng số attempt, dùng exponential backoff có jitter và tôn trọng `Retry-After`. Mỗi lần thử và thời gian chờ đều tiêu thụ deadline của request.

Đặt retry sát dependency trong service hoặc client, tách retry model provider khỏi retry tool, và tránh retry toàn bộ hội thoại chỉ vì một tool lỗi. Với thao tác ghi, dùng idempotency key ổn định hoặc đối soát trước khi gửi lại. Khi retry đã hết lượt, dừng rõ ràng, trả lỗi đã làm sạch và ghi nhận đủ metadata để điều tra.

## Tài liệu tham khảo

- [Spring Retry — Reference](https://github.com/spring-projects/spring-retry)
- [Spring AI — OpenAI Chat Configuration](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html)
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [HTTP Semantics — Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)
- [HTTP Semantics — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)

