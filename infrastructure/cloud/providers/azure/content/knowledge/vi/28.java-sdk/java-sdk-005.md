# Tùy biến HTTP pipeline, timeout và retry policy

Giả sử một dịch vụ Java chạy trên Azure App Service xử lý đơn hàng, đọc cấu hình từ Azure App Configuration, tải tệp lên Azure Blob Storage và truy cập Key Vault để lấy bí mật. Trong điều kiện bình thường, mọi lời gọi Azure SDK hoàn tất nhanh. Nhưng khi kết nối chậm, DNS gặp vấn đề, dịch vụ Azure trả HTTP 429 hoặc mạng có lỗi thoáng qua, ứng dụng có thể chậm hàng chục giây, tạo tải retry ngoài dự kiến, thậm chí ghi trùng dữ liệu.

Để giải quyết có hệ thống, cần hiểu **HTTP pipeline** của Azure SDK for Java: chuỗi những chính sách xử lý request/response gồm telemetry, request ID, authentication, retry, HTTP logging và HTTP transport. Từ đây, lập trình viên có thể **tùy biến HTTP client, timeout, retry options và chính sách riêng** mà vẫn giữ cơ chế bảo mật, quan sát và tương thích của SDK.

Bài học thuộc chương **Azure SDK cho Java**, trong mô-đun **CLOUD_PROVIDERS_AZURE**. Nó liên hệ trực tiếp với việc triển khai ứng dụng Java trên Azure subscription/resource group, Microsoft Entra ID, mạng ảo, Storage, App Configuration, Key Vault, giám sát và kiểm soát chi phí. Nội dung tập trung vào thư viện **com.azure:azure-core** và những service clients thuộc thế hệ Azure SDK for Java hiện đại; không áp dụng nguyên vẹn cho thư viện Java đời cũ hoặc SDK của bên thứ ba.

**Phạm vi an toàn:** ví dụ có tên tài nguyên giả định, dùng môi trường lab được cấp phép và không chạy lệnh tạo/xóa tài nguyên. Các API builder, retry options và giá trị mặc định có thể khác nhau theo phiên bản SDK/thư viện dịch vụ. Hãy kiểm tra Maven dependency tree và Javadoc đúng phiên bản trước khi áp dụng production; các giá trị thời gian trong bài là ví dụ điều chỉnh, không phải SLA Azure.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích thành phần và thứ tự xử lý trong **HttpPipeline** của Azure SDK for Java.
2. Phân biệt **HttpClient transport**, **HttpPipelinePolicy** và service-specific builder.
3. Phân biệt **PER_CALL** và **PER_RETRY**, biết chính sách nào nên chạy một lần hoặc mỗi lần thử.
4. Sử dụng **DefaultAzureCredential**, service client builder, HttpLogOptions và custom HttpClient mà không tự làm hỏng authentication.
5. Tùy biến Netty **connect, response, read và write timeout**, hiểu timeout tầng transport khác deadline toàn operation.
6. Sử dụng **RetryOptions**, **ExponentialBackoffOptions** và **FixedDelayOptions** đúng ngữ cảnh.
7. Phân biệt **maxRetries** và **maxTries** của những API khác nhau.
8. Sử dụng **RequestRetryOptions** chuyên biệt cho Azure Storage khi phù hợp.
9. Phân tích HTTP 408, 429, 5xx, Retry-After, lỗi mạng, non-idempotent operations và replayability.
10. Viết **custom HttpPipelinePolicy** phục vụ metrics/tracing an toàn, có xử lý sync/async.
11. Tránh retry lồng nhau, retry storm, chặn event loop và rò rỉ credentials trong logs.
12. Tính latency budget, throughput amplification và đề xuất timeout/retry theo loại workload.
13. Thiết kế unit/integration/fault-injection tests cho HTTP pipeline mà không cần chạm production.
14. Chẩn đoán timeout, 429, 401/403, proxy/TLS, service unavailable và các hiện tượng liên quan.
15. Vận hành chính sách HTTP nhất quán qua App Service, AKS, Azure Functions và các môi trường khác.

## 2. Vì sao cần hiểu HTTP pipeline?

### 2.1. Bài toán thực tế

Một API xử lý thanh toán phải đọc cờ cấu hình từ App Configuration trước khi xử lý đơn hàng:

~~~text
HTTP request vào ứng dụng
    ↓
Java API handler
    ↓
Azure App Configuration SDK
    ↓
DNS → TLS → network → Azure service
    ↓
Cấu hình trả về
    ↓
Business processing
~~~

Khi service trả 429 hoặc network timeout, SDK có thể tự retry. Nếu ứng dụng còn dùng retry ở tầng Spring, gateway hoặc message processor, tổng số lần thử có thể nhân lên ngoài dự kiến.

Ví dụ: SDK cho phép tối đa ba lần thử, ứng dụng lại gọi SDK tối đa ba lần. Trong điều kiện lỗi liên tục, có thể phát sinh **9 HTTP attempts**, không phải 3. Nếu nhiều instances cùng retry với khoảng delay giống nhau, cả hệ thống có thể tạo **retry storm**.

### 2.2. Ba nhóm cấu hình khác nhau

| Cấp | Ví dụ | Điều khiển |
|---|---|---|
| Transport | Netty, OkHttp, JDK HTTP client; connect/read/write/response timeout | Kết nối và truyền HTTP |
| Pipeline | RetryPolicy, logging, authentication, custom policy | Hành vi request/response quanh transport |
| Application | API deadline, circuit breaker, concurrency limit, idempotency | Mục tiêu nghiệp vụ và trải nghiệm |

Không nên giải quyết mọi timeout bằng cách tăng một con số lên 120 giây. Cần xác định đang chờ **lớp nào**, request có được retry không, và deadline nghiệp vụ có còn đủ hay không.

### 2.3. Điều gì xảy ra nếu không kiểm soát?

- App threads/async requests giữ tài nguyên quá lâu.
- Thời gian p95/p99 tăng mặc dù p50 vẫn tốt.
- Tăng chi phí outbound requests và logging.
- Throttling 429 trở nên nghiêm trọng vì retries đồng loạt.
- Lỗi backend bị khuếch đại qua các tầng.
- Lệnh không idempotent có thể ghi trùng.
- Retry xảy ra sau khi HTTP client đã mất kết nối trong khi server vẫn thực hiện thành công.
- HTTP body/Authorization token bị log nếu bật debug quá mức.

Mục tiêu của chính sách chuẩn là **retry khi thực sự có khả năng hồi phục, trong giới hạn thời gian và số lần thử; không làm sai dữ liệu**.

## 3. Thành phần Azure SDK for Java

### 3.1. HttpClient là HTTP transport

Trong Azure Core, interface **com.azure.core.http.HttpClient** đại diện tầng gửi và nhận HTTP. SDK có các triển khai transport thông dụng:

- **azure-core-http-netty**: Netty; thường là mặc định trong Azure SDK for Java.
- **azure-core-http-okhttp**: tích hợp OkHttp theo dependency được chọn.
- **azure-core-http-jdk-httpclient**: triển khai dựa trên Java HTTP client khi JDK/runtime được hỗ trợ.

HTTP client xử lý kết nối, DNS/TLS, gửi body và nhận response. Nó **không thay thế tự động** toàn bộ logic authentication/authorization hoặc service-specific retry.

### 3.2. HttpPipeline và policies

~~~mermaid
flowchart LR
    A["Service client call"] --> P1["PER_CALL policies"]
    P1 --> R["Retry policy"]
    R --> P2["PER_RETRY policies"]
    P2 --> H["HttpClient transport"]
    H --> S["Azure service"]
    S --> H
    H --> P2
    P2 --> R
    R --> P1
    P1 --> A
~~~

- **HttpPipeline** gom transport và chuỗi policies.
- **HttpPipelinePolicy** xem request và/hoặc response, có thể bổ sung headers, metrics, logging hoặc thực hiện những kiểm soát thích hợp.
- **RetryPolicy** quyết định gửi lại request khi lỗi đáp ứng điều kiện retry.
- **Authentication policy** gắn hoặc cập nhật thông tin xác thực theo thư viện và loại credential.
- **HttpLoggingPolicy** log những thông tin được phép theo cấu hình.
- **Transport** thực sự gửi dữ liệu qua mạng.

Khi SDK service client được tạo bằng builder thông thường, nó thường xây pipeline sẵn với các policy phù hợp dịch vụ. Lập trình viên **nên tùy biến qua builder trước**, chỉ tự lắp toàn bộ pipeline khi có yêu cầu chuyên sâu và hiểu các policy bắt buộc.

### 3.3. Request đi xuôi, response đi ngược

~~~mermaid
sequenceDiagram
    participant C as ServiceClient
    participant P1 as Policy A
    participant R as RetryPolicy
    participant P2 as Policy B
    participant H as HttpClient
    participant S as Azure Service
    C->>P1: Request
    P1->>R: Forward
    R->>P2: Attempt 1
    P2->>H: Send HTTP
    H->>S: Request
    S-->>H: Response 503
    H-->>P2: Response
    P2-->>R: Response 503
    R->>R: Evaluate + backoff
    R->>P2: Attempt 2
    P2->>H: Retry HTTP
    H->>S: Retry
    S-->>H: Response 200
    H-->>P2: Response
    P2-->>R: Response 200
    R-->>P1: Final response
    P1-->>C: Result
~~~

Đây là hình khái niệm; vị trí thực của authentication, logging, request ID và những policies khác được SDK/service client sắp đặt theo contract. Không tự cho rằng logging luôn đứng trước hoặc sau retry nếu chưa quan sát pipeline đã cấu hình.

### 3.4. Client builder là điểm mở rộng nên dùng

Nhiều service clients cung cấp những phương thức tương tự:

| Phương thức | Tác dụng | Lưu ý |
|---|---|---|
| endpoint(...) | Chọn service endpoint | Cần đúng service/region/sovereign cloud |
| credential(...) | Chọn TokenCredential hoặc credential phù hợp | Dùng least privilege |
| httpClient(...) | Thay HTTP transport | Không tự thay mọi policy |
| retryOptions(...) | Chỉnh retry strategy | Loại RetryOptions thay đổi theo SDK |
| addPolicy(...) | Thêm custom HttpPipelinePolicy | Đúng PER_CALL/PER_RETRY |
| httpLogOptions(...) | Chọn mức logging | Không log body/secret bừa bãi |
| pipeline(...) | Cung cấp toàn bộ pipeline | Có thể ghi đè cấu hình builder khác |
| buildClient()/buildAsyncClient() | Tạo sync/async client | Không tạo client mới mỗi request |

Các phương thức **không phải mọi builder đều có**. Ví dụ azure-core RetryOptions khác **azure-storage-common RequestRetryOptions**. Đọc API của client cụ thể trước khi copy code.

## 4. PER_CALL và PER_RETRY

### 4.1. Ý nghĩa

Azure SDK for Java có enum **HttpPipelinePosition** trong package **com.azure.core.http**:

- **PER_CALL**: policy được gọi một lần cho mỗi operation/service call, trước retry loop.
- **PER_RETRY**: policy chạy trong retry loop, mỗi lần HTTP request được gửi lại.
- Nếu không override, HttpPipelinePolicy mặc định ở **PER_RETRY** trong những phiên bản Azure Core hiện hành.

| Tình huống | PER_CALL | PER_RETRY |
|---|---|---|
| Operation count | 1 | Tối đa số HTTP attempts |
| Tổng elapsed time của operation | Phù hợp | Không đầy đủ nếu tính riêng từng attempt |
| Request trace/correlation ban đầu | Thường phù hợp | Có thể giữ chung trace và thêm attempt metadata |
| Attempt-level metrics | Không đủ | Phù hợp |
| Authentication/token logic | Theo built-in auth policy/service contract | Không tự di chuyển |
| Custom signed headers | Phải hiểu request mutation và retry | Có thể cần tái tính trên từng attempt |
| HTTP request attempt logging | Không ghi mọi lần thử | Phù hợp |

### 4.2. Ví dụ ba attempts

~~~text
Client operation
    PER_CALL: bắt đầu (1 lần)
        Retry loop
            PER_RETRY: attempt #1 → 503
            Backoff
            PER_RETRY: attempt #2 → 429
            Backoff theo policy/Retry-After nếu hỗ trợ
            PER_RETRY: attempt #3 → 200
    PER_CALL: hoàn tất (1 lần)
~~~

Nếu đặt custom policy ghi số HTTP requests ở PER_CALL, số đếm có thể **thấp hơn thực tế** khi retry. Nếu đặt policy đo elapsed toàn operation ở PER_RETRY, mỗi lần tính riêng sẽ không bao gồm toàn bộ backoff.

### 4.3. Không xem policy là một interceptor tùy ý an toàn

Một policy có thể xem request/response nhưng phải:
- Không làm sai body hoặc chữ ký của dịch vụ.
- Không ghi đè Authorization header.
- Không gọi next.process() nhiều lần trừ khi chủ động thiết kế retry.
- Không blocking Thread.sleep trong async pipeline.
- Không consume response body rồi không trả lại.
- Không lưu per-request mutable state vào singleton policy.
- Không log PII, request body, token hoặc SAS.
- Không tạo custom retry loop lồng với RetryPolicy của SDK.

Một custom policy đơn giản nhất thường là **metrics/correlation có giới hạn**, không phải thay thế transport hoặc authentication.

## 5. Timeout không phải một giá trị duy nhất

### 5.1. Các loại timeout

| Timeout | Phạm vi gần đúng | Rủi ro nếu đặt quá thấp |
|---|---|---|
| DNS/proxy resolution | Tra cứu và chọn endpoint | Không tới được IP |
| Connect timeout | Thiết lập kết nối tới server | Mạng xa/cold connection có thể fail |
| TLS handshake timeout | Thỏa thuận TLS nếu transport hỗ trợ | Handshake chậm, certificate/auth issue |
| Write timeout | Gửi dữ liệu request body | Upload lớn bị cắt giữa chừng |
| Response timeout | Chờ server bắt đầu trả response | Dịch vụ chưa xử lý xong |
| Read timeout | Đọc response sau khi bắt đầu nhận | Streaming/response chậm bị ngắt |
| Per-try/attempt timeout | Một HTTP attempt | Cần retry mà vẫn còn ngân sách |
| Total operation deadline | Toàn lời gọi kể cả retry/backoff | Dễ vượt SLA nếu không đặt |
| Business/API deadline | Thời gian API/worker được phép dùng | Cần trả lỗi/cancel đúng |
| Long-running operation polling | Nhiều requests kiểm tra trạng thái | Không cùng một HTTP request |

**Không cộng các timeout trên rồi coi đó là thời gian tối đa chính xác**, vì mỗi lớp áp dụng ở giai đoạn khác nhau, một số timeout là idle/inactivity timeout, và SDK/service method có thể có policy riêng.

### 5.2. Connect timeout

Đo thời gian từ lúc transport bắt đầu thử kết nối tới khi thiết lập kết nối xong; không phải tổng thời gian làm API.

Nếu DNS đúng nhưng NSG/proxy/firewall chặn SYN packets, connect timeout có thể là triệu chứng. Tăng connect timeout vô hạn **không sửa được route sai**.

### 5.3. Response timeout

Giới hạn thời gian chờ server bắt đầu trả response sau khi request được gửi theo định nghĩa của transport. Một dịch vụ đang throttling hoặc backend quá tải có thể khiến response chậm; với upload lớn cần hiểu write và response timeout tách biệt.

### 5.4. Read và write timeout

Các transport có thể dùng read/write **inactivity timeout hoặc per-operation timeout**, không nhất thiết áp cho toàn bộ file download/upload. Ví dụ một stream liên tục nhận các chunk nhỏ có thể kéo dài hơn một read timeout đơn lẻ mà không lỗi nếu không có giai đoạn idle vượt ngưỡng.

Không thiết lập writeTimeout = 2 giây cho các upload lớn đi qua kết nối Internet có băng thông thấp chỉ vì một API GET yêu cầu phản hồi nhanh.

### 5.5. Total deadline

Nếu API HTTP của doanh nghiệp cần trả trong tối đa 5 giây, cấu hình mỗi HTTP attempt timeout 30 giây với ba retries rõ ràng mâu thuẫn.

Một total deadline có thể được áp ở tầng service method/application, ví dụ các overload nhận Duration khi SDK hỗ trợ, hoặc reactive cancellation/deadline. Nhưng **timeout ở tầng ứng dụng không làm server hoàn tác mọi write đã nhận**. Khi timeout xảy ra, phải xem operation có idempotent và có cách kiểm tra trạng thái hay không.



## 6. Cấu hình HTTP transport với Netty

### 6.1. Chọn Netty khi nào?

**azure-core-http-netty** là lựa chọn mặc định phổ biến. Tùy biến Netty khi cần:

- Connect timeout ngắn cho vùng Azure gần workload.
- Response/read/write timeouts riêng cho upload hoặc download.
- Proxy và giới hạn mạng của tổ chức.
- Kiểm soát connection pool/transport configuration ở mức nâng cao.
- Tái sử dụng một transport cho nhiều service clients.
- Điều tra DNS/TLS/connection reuse trong môi trường App Service hoặc AKS.

Không cần tự tạo một HttpClient mới chỉ để dùng mặc định; những service client builders sẽ chọn transport phù hợp theo classpath.

### 6.2. Ví dụ Java: Netty với bốn timeout

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import java.time.Duration;

public final class AzureTransportFactory {
    private AzureTransportFactory() { }

    public static HttpClient create() {
        return new NettyAsyncHttpClientBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .responseTimeout(Duration.ofSeconds(20))
            .readTimeout(Duration.ofSeconds(30))
            .writeTimeout(Duration.ofSeconds(30))
            .build();
    }
}
~~~

**Giải thích:**

- connectTimeout = 5 giây giới hạn thời gian kết nối mới trong điều kiện phù hợp.
- responseTimeout = 20 giây giới hạn chờ phản hồi bắt đầu.
- readTimeout = 30 giây điều tiết thời gian đọc phản hồi theo transport semantics.
- writeTimeout = 30 giây dành cho hoạt động truyền request data theo transport semantics.

Đây **không phải tổng deadline 85 giây** và không đảm bảo mỗi operation kết thúc trong 85 giây. Nếu có nhiều attempts và backoff, tổng latency có thể lớn hơn nhiều.

NettyAsyncHttpClientBuilder có hành vi riêng đối với duration bằng hoặc nhỏ hơn 0 và các giá trị null/default; đừng dùng Duration.ZERO để biểu thị “timeout ngay lập tức”. Theo tài liệu Netty hiện hành, những giá trị không dương có thể **tắt** loại timeout tương ứng. Dùng thời gian dương và kiểm tra tính tương thích Runtime.

### 6.3. Dùng chung transport có kiểm soát

Trong backend Java lâu dài, thường nên tạo client ở giai đoạn ứng dụng khởi động và tái sử dụng:

~~~java
HttpClient transport = AzureTransportFactory.create();

// Có thể truyền transport cho nhiều service builders
// khi transport và lifecycle tương thích.
~~~

Không tạo Netty event-loop/connection pools mới cho mọi HTTP request. Nhưng **không tái sử dụng bừa bãi một transport có proxy/TLS config nhạy cảm cho các endpoints không cùng trust/network policy**.

### 6.4. Proxy và kết nối hybrid

Doanh nghiệp có thể cần HTTP CONNECT proxy hoặc các tuyến egress riêng. Hãy dùng ProxyOptions và transport-specific builder theo API hiện hành, quản lý credentials qua secure store. Trước khi điều chỉnh timeout, kiểm tra:

1. DNS resolver có phân giải đúng private endpoint hostname không?
2. Proxy có cho đi tới Azure service hostname và port không?
3. TLS certificate chain có được xác minh không?
4. Network Security Group, Azure Firewall, VNet route có phù hợp không?
5. Private Endpoint service và Private DNS Zone có được link đúng VNet không?
6. Managed identity token endpoint có thể truy cập không?

Nếu nguyên nhân là DNS sai hoặc firewall chặn, tăng timeout từ 5 lên 120 giây chỉ khiến lỗi đến chậm hơn.

### 6.5. Không tắt TLS validation để thử nhanh

Không dùng custom trust manager kiểu “accept all certificates” hoặc tắt hostname verification để giải quyết timeout trong môi trường thật. Làm như vậy có thể tạo nguy cơ MITM, rò rỉ TokenCredential và dữ liệu nhạy cảm.

## 7. Cấu hình retry chuẩn với Azure Core

### 7.1. RetryOptions và ExponentialBackoffOptions

**com.azure.core.http.policy.RetryOptions** hỗ trợ cấu hình retry với **ExponentialBackoffOptions** hoặc **FixedDelayOptions**.

Ví dụ:

~~~java
import com.azure.core.http.policy.ExponentialBackoffOptions;
import com.azure.core.http.policy.RetryOptions;
import java.time.Duration;

ExponentialBackoffOptions backoff = new ExponentialBackoffOptions()
    .setMaxRetries(3)
    .setBaseDelay(Duration.ofMillis(500))
    .setMaxDelay(Duration.ofSeconds(8));

RetryOptions retryOptions = new RetryOptions(backoff);
~~~

**maxRetries = 3** thường nghĩa là tối đa ba **lần thử lại sau lần gửi đầu tiên**, tức tối đa **4 attempts**, nếu request đáp ứng điều kiện retry và operation chưa bị hủy. Không nhầm với các API đặt tên **maxTries**.

Giá trị baseDelay, maxDelay và maxRetries là ví dụ nhằm cân bằng độ trễ/khả năng hồi phục; không phải defaults chung của mọi Azure service.

### 7.2. Exponential backoff

Một mô hình gần đúng:

~~~text
Delay after attempt k ≈
    min(maxDelay, baseDelay × 2^(k-1))

Ví dụ baseDelay = 500 ms:
  Retry 1: ~0.5 s
  Retry 2: ~1.0 s
  Retry 3: ~2.0 s
~~~

SDK có thể áp dụng jitter hoặc server-directed delay và những giới hạn khác tùy RetryStrategy/version; không được dựa vào chính xác 0,5/1/2 giây trong test nếu implementation có thêm randomization.

**Exponential backoff** giảm xác suất nhiều clients gửi lại cùng một thời điểm khi dịch vụ đang bận. Khi server trả **Retry-After** hoặc header tương đương, policy có thể ưu tiên hướng dẫn của dịch vụ theo khả năng thư viện; phải xác minh với client cụ thể.

### 7.3. Fixed delay khi nào?

~~~java
import com.azure.core.http.policy.FixedDelayOptions;
import com.azure.core.http.policy.RetryOptions;
import java.time.Duration;

RetryOptions retryOptions = new RetryOptions(
    new FixedDelayOptions(2, Duration.ofSeconds(1))
);
~~~

Fixed delay phù hợp một số môi trường test, một số client có tải rất thấp hoặc protocol có đặc tính rõ. Nhưng trong hệ thống có hàng nghìn instances, mọi client chờ chính xác một giây dễ tạo **đồng bộ retry**, khiến quá tải lặp theo chu kỳ.

Trong production cloud có burst, thường ưu tiên exponential backoff có jitter hoặc chiến lược retry được service SDK đề xuất.

### 7.4. RetryPolicy và RetryOptions

**RetryPolicy** là một HttpPipelinePolicy có thể dùng **RetryOptions**. Với service client builder có **retryOptions(...)**, nên cấu hình ở đó trước.

Không nhầm:

- **RetryOptions**: dữ liệu cấu hình retry.
- **RetryPolicy**: policy quyết định và điều phối attempts trong pipeline.
- **RequestRetryOptions**: tùy chọn retry chuyên biệt của Azure Storage với một số cấu hình khác.
- **Application retry**: gọi lại toàn bộ SDK method, nằm ngoài Azure SDK pipeline.

Một builder có thể nhận retryOptions hoặc retryPolicy thay thế nhau và không cho cấu hình cả hai đồng thời. Không tự thêm một RetryPolicy bằng **addPolicy(...)** vào builder đã có retry mặc định, vì có thể tạo hai vòng retry hoặc đổi thứ tự policy khó dự đoán.

### 7.5. Bản chất retry condition

Trong Azure Core, điều kiện mặc định của RetryOptions có thể đánh giá những responses như **408, 429 và một số lỗi 5xx** cũng như exceptions theo phiên bản. Nhưng mỗi client/service có thể bổ sung hoặc giới hạn behavior.

| Status/tình huống | Hướng xử lý thường gặp | Cảnh báo |
|---|---|---|
| 200/201/204 | Thành công | Không retry |
| 400 Bad Request | Input/schema sai | Sửa request, không retry vô hạn |
| 401 Unauthorized | Sai/hết xác thực | Kiểm tra credential/token flow, không coi là lỗi tải |
| 403 Forbidden | Thiếu RBAC, ACL, network policy | Không sửa bằng retry vô hạn |
| 404 Not Found | Resource/route sai, hoặc eventual state | Chỉ retry nếu operation-specific guidance |
| 408 Request Timeout | Có thể transient | Kiểm tra semantics và deadline |
| 409 Conflict | Thường conflict nghiệp vụ | Không retry trừ trường hợp service xác định transient |
| 412 Precondition Failed | ETag/điều kiện không còn đúng | Đọc lại state, giải quyết concurrency |
| 429 Too Many Requests | Throttling/rate limit | Tôn trọng Retry-After, giảm tải |
| 500/502/503/504 | Có thể transient | Retry có giới hạn, cảnh giác server vẫn đã commit |
| Network reset/EOF | Có thể transient | Không biết server đã nhận/commit hay chưa |
| Timeout sau POST | Trạng thái kết quả mơ hồ | Dùng idempotency key hoặc verify state |

**Không phải mọi 5xx đều được default policy retry**, cũng không phải mọi 409/404 đều vĩnh viễn không retry. Hành vi phụ thuộc service-specific error codes và operation semantics. Không override điều kiện mặc định chỉ theo một bảng HTTP chung rồi vô hiệu hóa logic quan trọng của thư viện dịch vụ.

### 7.6. Retry-After là tín hiệu từ server

Khi Azure trả HTTP 429 hoặc 503 kèm **Retry-After** hoặc những header x-ms-retry-after-* theo dịch vụ, hãy để SDK tôn trọng hướng dẫn được hỗ trợ. Đừng viết vòng while sleep(100) cứng rồi đánh lại, vì nó có thể:

- Làm service throttling nặng hơn.
- Tạo thêm charges.
- Giữ thread/connection/worker.
- Kéo dài queue của application.
- Tăng thời gian timeout tổng.

Nếu Retry-After lớn hơn business deadline, ứng dụng cần **trả lỗi có kiểm soát hoặc chuyển sang queue xử lý sau**, không chờ vô hạn.

## 8. Ví dụ hoàn chỉnh: Azure App Configuration client

### 8.1. Mục tiêu

Một ứng dụng Java đọc cấu hình từ Azure App Configuration, cần:

- Xác thực qua **Microsoft Entra ID** với DefaultAzureCredential.
- Reuse Netty HttpClient có timeout cụ thể.
- Exponential retry tối đa ba lần retry sau request đầu.
- HTTP logging ở mức BASIC.
- Policy metrics theo operation, không log secret.
- Không ghi đè toàn bộ pipeline do SDK dựng sẵn.

### 8.2. Chuẩn bị dependencies

Trong Maven, quản lý các Azure SDK dependencies qua **azure-sdk-bom** được tổ chức phê duyệt và pin phiên bản tương thích. Các artifacts tham gia:

~~~text
com.azure:azure-data-appconfiguration
com.azure:azure-identity
com.azure:azure-core
com.azure:azure-core-http-netty
reactor-core (dependency do hệ sinh thái phù hợp quản lý)
~~~

Không tự chọn một phiên bản cố định cũ từ bài blog; kiểm tra JDK/Netty/runtime compatibility, Azure SDK BOM và security updates. Không cần cài tất cả HTTP transports nếu chỉ dùng Netty.

### 8.3. Java client factory

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.core.http.policy.ExponentialBackoffOptions;
import com.azure.core.http.policy.HttpLogDetailLevel;
import com.azure.core.http.policy.HttpLogOptions;
import com.azure.core.http.policy.RetryOptions;
import com.azure.data.appconfiguration.ConfigurationClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.time.Duration;

public final class AppConfigClientFactory {
    private AppConfigClientFactory() { }

    public static ConfigurationClient create(String endpoint) {
        if (endpoint == null || !endpoint.startsWith("https://")) {
            throw new IllegalArgumentException(
                "Cần endpoint Azure App Configuration dạng HTTPS"
            );
        }

        HttpClient httpClient = new NettyAsyncHttpClientBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .responseTimeout(Duration.ofSeconds(15))
            .readTimeout(Duration.ofSeconds(20))
            .writeTimeout(Duration.ofSeconds(20))
            .build();

        RetryOptions retries = new RetryOptions(
            new ExponentialBackoffOptions()
                .setMaxRetries(3)
                .setBaseDelay(Duration.ofMillis(500))
                .setMaxDelay(Duration.ofSeconds(8))
        );

        return new ConfigurationClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .httpClient(httpClient)
            .retryOptions(retries)
            .httpLogOptions(
                new HttpLogOptions()
                    .setLogLevel(HttpLogDetailLevel.BASIC)
            )
            .buildClient();
    }
}
~~~

Dùng trong service singleton/dependency injection:

~~~java
String endpoint = System.getenv("AZURE_APPCONFIG_ENDPOINT");

ConfigurationClient client =
    AppConfigClientFactory.create(endpoint);

// Đọc một key đã có khi principal được cấp App Configuration Data Reader:
// ConfigurationSetting setting = client.getConfigurationSetting("app.mode", null);
~~~

Không nhúng App Configuration connection string hoặc secrets vào source. **DefaultAzureCredential không tự cấp RBAC**: identity chạy ứng dụng phải có **App Configuration Data Reader** hoặc role phù hợp tại đúng scope. Trong development, DefaultAzureCredential có thể chọn danh tính developer khác managed identity production.

### 8.4. Tại sao không tự dựng HttpPipeline ở ví dụ trên?

**ConfigurationClientBuilder** tự biết authentication scope và service-specific policies. Khi gọi .httpClient(...), .retryOptions(...), .httpLogOptions(...) và .credential(...) riêng biệt, SDK vẫn có cơ hội lắp đúng các thành phần mặc định.

Nếu thay bằng:

~~~java
// Chỉ ví dụ khái niệm, không được build và dùng trong production
// khi thiếu auth/service policies:
// HttpPipeline pipeline = new HttpPipelineBuilder()
//     .httpClient(httpClient)
//     .policies(new RetryPolicy(retries))
//     .build();
~~~

rồi set builder.pipeline(pipeline), bạn có thể **bỏ quên authentication, telemetry, content handling, logging và service-specific behavior**. Ngoài ra .pipeline(...) có độ ưu tiên cao hơn nhiều cấu hình khác trên builder, nên các lựa chọn như .retryOptions(...) hoặc .httpClient(...) có thể bị bỏ qua. Phải đọc tài liệu builder nếu thực sự cần custom pipeline hoàn chỉnh.

### 8.5. Sync và async clients

ConfigurationClientBuilder có thể xây **buildClient()** hoặc **buildAsyncClient()**.

| Sync | Async |
|---|---|
| Dễ dùng trong ứng dụng blocking phù hợp | Phù hợp reactive/high-concurrency nếu dùng đúng |
| Thread caller có thể block | Mono/Flux và backpressure/cancellation |
| Có thể dùng policy có processSync | Cần policy process trả Mono |
| Dễ bị thread starvation nếu quá nhiều I/O | Dễ gây lỗi nếu block trên event loop |

Không gọi **.block()** trong Netty event-loop hoặc reactive callback. Nếu application sử dụng blocking framework, thiết kế thread pool và timeout theo capacity; nếu reactive, dùng async API và cancellation nhất quán.



## 9. Viết custom HttpPipelinePolicy để đo metrics

### 9.1. Yêu cầu

Một policy đo duration và response status cho mỗi operation phải:

- Chạy một lần ở **PER_CALL**.
- Không chứa state mutable dùng chung giữa requests.
- Không log URL path/query có thể chứa thông tin bí mật.
- Không in Authorization header, SAS, request/response body.
- Xử lý cả sync và async clients nếu thư viện gọi cả hai đường.
- Không ngăn request tới policy tiếp theo.
- Không tự retry hoặc nuốt exception.
- Ghi được status, exception category và thời gian.

### 9.2. Code Java: SafeTimingPolicy

~~~java
import com.azure.core.http.HttpPipelineCallContext;
import com.azure.core.http.HttpPipelineNextPolicy;
import com.azure.core.http.HttpPipelineNextSyncPolicy;
import com.azure.core.http.HttpPipelinePosition;
import com.azure.core.http.HttpResponse;
import com.azure.core.http.policy.HttpPipelinePolicy;

import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

import reactor.core.publisher.Mono;

public final class SafeTimingPolicy implements HttpPipelinePolicy {
    private static final Logger LOG =
        Logger.getLogger(SafeTimingPolicy.class.getName());

    @Override
    public HttpPipelinePosition getPipelinePosition() {
        return HttpPipelinePosition.PER_CALL;
    }

    private static long elapsedMs(long startNanos) {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startNanos
        );
    }

    @Override
    public Mono<HttpResponse> process(
        HttpPipelineCallContext context,
        HttpPipelineNextPolicy next
    ) {
        // defer: đồng hồ bắt đầu lúc có subscriber;
        // không ghi logs hoặc thay đổi request trước khi subscribe.
        return Mono.defer(() -> {
            final long start = System.nanoTime();

            return next.process()
                .doOnNext(response -> LOG.info(
                    "azure_sdk_operation status=" + response.getStatusCode()
                    + " durationMs=" + elapsedMs(start)
                ))
                .doOnError(error -> LOG.warning(
                    "azure_sdk_operation errorType="
                    + error.getClass().getSimpleName()
                    + " durationMs=" + elapsedMs(start)
                ));
        });
    }

    @Override
    public HttpResponse processSync(
        HttpPipelineCallContext context,
        HttpPipelineNextSyncPolicy next
    ) {
        final long start = System.nanoTime();

        try {
            HttpResponse response = next.processSync();

            LOG.info(
                "azure_sdk_operation status=" + response.getStatusCode()
                + " durationMs=" + elapsedMs(start)
            );

            return response;
        } catch (RuntimeException error) {
            LOG.warning(
                "azure_sdk_operation errorType="
                + error.getClass().getSimpleName()
                + " durationMs=" + elapsedMs(start)
            );
            throw error;
        }
    }
}
~~~

**Giải thích kỹ thuật:**

- **HttpPipelinePolicy** có phương thức process bất đồng bộ trả **Mono<HttpResponse>**.
- **processSync** cho đường đồng bộ, chuyển tiếp qua **HttpPipelineNextSyncPolicy**.
- **getPipelinePosition** trả **HttpPipelinePosition.PER_CALL**.
- **Mono.defer** trì hoãn đo thời gian đến lúc subscriber kích hoạt phần thực thi.
- **next.process()** chỉ gọi một lần; không tạo vòng retry riêng.
- **doOnNext** và **doOnError** chỉ quan sát, không nuốt exception.
- **System.nanoTime** phù hợp đo thời lượng, không dùng System.currentTimeMillis để đo khoảng thời gian chính xác trong khi đồng hồ có thể bị chỉnh.
- Metrics ghi **status/error type**, không log URL, body hoặc headers.

Lưu ý: reactive publisher có thể được subscribe nhiều lần trong một số trường hợp; mỗi subscription có thể kích hoạt một operation mới. Nếu caller tự dùng retryWhen hoặc subscribe lại, PER_CALL áp trên mỗi **pipeline invocation**, không phải một business workflow bất kể số lần gọi lại.

### 9.3. Gắn policy vào App Configuration builder

Trong factory ở mục 8, thêm:

~~~java
return new ConfigurationClientBuilder()
    .endpoint(endpoint)
    .credential(new DefaultAzureCredentialBuilder().build())
    .httpClient(httpClient)
    .retryOptions(retries)
    .httpLogOptions(
        new HttpLogOptions()
            .setLogLevel(HttpLogDetailLevel.BASIC)
    )
    .addPolicy(new SafeTimingPolicy())
    .buildClient();
~~~

Đoạn code dựa vào những biến/import của factory mục 8. Đừng tạo một client/policy mới cho mỗi request. **HttpPipelinePolicy** có thể được chia sẻ, nên các biến đếm/timer phải được giữ theo request local hoặc dùng atomic/metrics registry thread-safe.

### 9.4. Khi muốn biết mỗi attempt

Nếu mục tiêu là đếm HTTP sends thực, tạo một policy riêng:

~~~java
@Override
public HttpPipelinePosition getPipelinePosition() {
    return HttpPipelinePosition.PER_RETRY;
}
~~~

Vị trí PER_RETRY khiến policy chạy trong mỗi retry attempt. Tuy nhiên phải kiểm tra logging policy nào của SDK đã cung cấp retryCount để không ghi trùng. Khi cần đo retries chi tiết, cân nhắc diagnostic events/metrics của Azure SDK và transport trước khi thêm custom instrumentation.

### 9.5. Khi cần header correlation

Một HTTP policy có thể gắn custom header nhưng phải xác minh header được dịch vụ chấp nhận và không làm sai canonical signature. Trong nhiều trường hợp nên dùng:

- **Context** theo method overload có hỗ trợ.
- **x-ms-client-request-id**/RequestIdPolicy hoặc cơ chế request ID của SDK khi được hỗ trợ.
- **ClientOptions** và AddHeadersFromContextPolicy theo tài liệu.
- OpenTelemetry tracing/correlation ở app layer.

Không ghi đè Authorization hoặc sửa x-ms-* headers đã được ký bởi Azure Storage. Khi cần thêm request ID, ưu tiên cơ chế SDK hỗ trợ và đặt trước authentication/signing theo pipeline đúng; tự thêm header sau signing có thể gây lỗi xác thực.

## 10. Azure Storage: RequestRetryOptions chuyên biệt

### 10.1. Không nhầm hai loại retry options

Với **Azure Blob Storage Java SDK**, builder như **BlobServiceClientBuilder** có thể chấp nhận:

- **com.azure.core.http.policy.RetryOptions** — cấu hình retry chung của azure-core.
- **com.azure.storage.common.policy.RequestRetryOptions** — cấu hình retry dành cho Azure Storage, hỗ trợ các tùy chọn như maxTries, tryTimeout và secondaryHost khi thích hợp.

Hai overload có thể được đánh dấu **mutually exclusive**. Không cấu hình cả hai trong một builder rồi cho rằng sẽ có thêm tính năng của cả hai; SDK có rules riêng về precedence.

### 10.2. Ví dụ BlobServiceClient với Storage retry

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.common.policy.RequestRetryOptions;
import com.azure.storage.common.policy.RetryPolicyType;

import java.time.Duration;

public final class StorageClientFactory {
    private StorageClientFactory() { }

    public static BlobServiceClient create(String storageEndpoint) {
        HttpClient transport = new NettyAsyncHttpClientBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .responseTimeout(Duration.ofSeconds(25))
            .readTimeout(Duration.ofSeconds(60))
            .writeTimeout(Duration.ofSeconds(60))
            .build();

        RequestRetryOptions storageRetries = new RequestRetryOptions(
            RetryPolicyType.EXPONENTIAL,
            4,                       // maxTries: gồm request đầu
            Duration.ofSeconds(30),  // tryTimeout per attempt
            Duration.ofSeconds(1),   // retryDelay
            Duration.ofSeconds(8),   // maxRetryDelay
            null                     // không tự chuyển sang secondary
        );

        return new BlobServiceClientBuilder()
            .endpoint(storageEndpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .httpClient(transport)
            .retryOptions(storageRetries)
            .buildClient();
    }
}
~~~

**Điều kiện:** ứng dụng có các dependencies azure-storage-blob, azure-storage-common, azure-identity và transport tương thích; endpoint dạng **https://storage-account.blob.core.windows.net/** của Storage account có thật. Managed identity/service principal cần Azure Storage **data-plane RBAC** phù hợp (chẳng hạn Storage Blob Data Reader/Contributor theo hoạt động). Không tự coi Azure subscription Contributor là quyền đọc/ghi Blob data mặc định.

### 10.3. maxTries khác maxRetries

| Tùy chọn | Ý nghĩa thực hành | Ví dụ |
|---|---|---|
| ExponentialBackoffOptions.setMaxRetries(3) | Ba **lần retry sau lần đầu** | Tối đa 4 attempts |
| Storage RequestRetryOptions maxTries = 4 | **Tổng số attempts**, gồm request đầu | Tối đa 4 attempts |
| App-level RetryTemplate maxAttempts = 3 | Theo cấu hình framework | Có thể nhân với SDK retries |

**Tên và semantics của tham số khác nhau**, phải đọc đúng Javadoc từng API. Không nói “maxRetries = 3 nghĩa tổng 3 lần gửi” trong mọi thư viện.

### 10.4. tryTimeout không bằng total timeout

Trong Storage RequestRetryOptions, tryTimeout thường nhắm vào **một service request attempt**. Nếu cấu hình tổng 4 attempts, mỗi attempt có timeout, backoff giữa attempts và overhead, toàn bộ operation có thể vượt tryTimeout nhiều lần.

Một ứng dụng yêu cầu API completion trước 10 giây cần thêm **total operation deadline** hoặc chọn giá trị tryTimeout/retry nhỏ hơn. Riêng các upload lớn, phải sizing per-try timeout theo kích thước payload, băng thông và sự biến động mạng.

### 10.5. Secondary host và consistency

Một số lựa chọn Storage retry có secondaryHost cho tình huống geo-redundancy thích hợp. **Không bật secondaryHost mặc định để “tăng HA”** nếu chưa hiểu:

- Secondary có thể chưa đồng bộ toàn bộ write.
- Read có thể trả dữ liệu cũ.
- Mọi operation không nhất thiết hỗ trợ secondary.
- Khi write thất bại, chuyển tùy tiện sang secondary có thể không hợp lệ.
- DNS/authorization/region/compliance ảnh hưởng tính đúng đắn.

Nếu ứng dụng cần strong read-after-write, phải thiết kế consistency theo khả năng dịch vụ thay vì chỉ đổi endpoint retries.

### 10.6. Storage chunked upload có nhiều requests

Một upload 1 GB có thể được SDK chia thành nhiều HTTP requests/blocks và có retry per block. Tổng thời gian của thao tác upload không bằng một lần HTTP request, và số requests thực có thể lớn hơn một. Cần theo dõi:

- Block size/chunk size.
- Max concurrency.
- Retry count per request.
- Stream replayability.
- Timeout cho write/read và total upload.
- Không vượt RAM/heap của Java service.
- Partial upload/commit semantics theo Storage API.

Không giả định một client-level retry policy có thể làm mọi upload lớn thành một HTTP request nguyên tử.

## 11. Timeout budget và retry storm

### 11.1. Cách tính budget gần đúng

Giả sử business API cho phép **8 giây** cho tất cả việc đọc cấu hình, gọi SQL và trả response. Nếu riêng App Configuration có:

~~~text
Initial attempt timeout: 2 seconds
Retries: 2
Backoff between retries: 300 ms, then 600 ms

Upper estimate for this dependency:
  3 × 2s + 0.3s + 0.6s
  = 6.9s (+ overhead)
~~~

Như vậy còn quá ít thời gian cho business logic và response. Cần chia budget hợp lý:

~~~text
API gateway / caller deadline: 8.0s
  ├─ auth + input validation: 0.5s
  ├─ App Configuration/cached config: 0.3s target
  ├─ DB/business work: 3.0s
  ├─ downstream queue or write: 2.0s
  └─ headroom + network/cancellation: 2.2s
~~~

Các con số chỉ là ví dụ lập ngân sách. **Không thể chứng minh worst-case latency bằng phép cộng trên** nếu SDK transport, connection pool, DNS, retries, stream reading và application scheduling không bị giới hạn. Cần đo thực nghiệm.

### 11.2. Retry amplification

Giả sử ứng dụng gửi 1.000 operations/giây tới một Azure service, 30% operations lỗi tạm thời và phải sử dụng toàn bộ ba lần retry:

~~~text
70% thành công lần đầu:
  700 operations × 1 attempt = 700 sends

30% lỗi liên tục:
  300 operations × 4 attempts = 1,200 sends

Tổng:
  1,900 HTTP sends / giây (thay vì 1,000)
~~~

Nếu **100%** calls đều lỗi và mỗi call thử tổng bốn lần, lượng HTTP sends có thể đạt khoảng **4.000 attempts/giây** trước khi xét delay, concurrency và rate limits. Retry storm có thể biến sự cố thoáng qua thành sự cố kéo dài.

### 11.3. Các biện pháp chống storm

- **Exponential backoff + jitter** để làm lệch lịch retry giữa instances.
- **Max retries** và **total deadline** rõ.
- **Retry-After** từ dịch vụ được tôn trọng.
- **Circuit breaker** cho phép fail fast khi downstream đang quá tải kéo dài.
- **Bulkhead/concurrency limit** ngăn toàn bộ app threads đổ vào một dependency.
- **Rate limiting/queue** điều tiết burst.
- **Caching** cho dữ liệu đọc có freshness semantics phù hợp.
- **Retry budgets** cấp hệ thống thay vì mỗi layer tự retry.
- **Idempotency** để retries không tạo side effects trùng.
- **Observability** biết retry rate, not chỉ error rate.

Circuit breaker phải có trạng thái/timeout/probe phù hợp; không bật quá nhạy làm dependency đang hồi phục không có cơ hội nhận traffic.

### 11.4. Không xếp retry ở mọi tầng

~~~mermaid
flowchart TD
    G["API gateway retry ×3"] --> APP["Application retry ×3"]
    APP --> SDK["Azure SDK retry ×4 attempts"]
    SDK --> S["Azure service"]
~~~

Trong điều kiện xấu, một business call có thể tạo tới **3 × 3 × 4 = 36 attempts** tới service, nếu cả ba tầng thực sự retry cùng thao tác. Đây không phải thiết kế mong muốn.

Chọn **một retry owner chính** cho mỗi loại lỗi; các tầng khác có thể chỉ timeout, circuit-break, queue hoặc trả trạng thái để caller xử lý. Nếu bắt buộc nhiều tầng có retry, phải có shared total deadline, idempotency và giới hạn số attempts cuối cùng.

## 12. Idempotency: có an toàn khi gửi lại không?

### 12.1. Retry chỉ an toàn khi kết quả có thể lặp

| Operation | Rủi ro retry | Hướng thiết kế |
|---|---|---|
| GET Blob/Key Vault secret | Thường là read | Giữ version/freshness semantics, timeout hợp lý |
| List resources | Có paging và state thay đổi | Continuation tokens, tránh quét lại không cần |
| PUT với resource ID ổn định | Có thể idempotent nếu semantics phù hợp | ETag/If-Match khi concurrent writes |
| POST tạo order mới | Có thể tạo hai orders | Idempotency key và unique constraint |
| Queue send | Có thể tạo hai messages | Stable message ID/dedup nếu service hỗ trợ |
| Delete | Có thể an toàn về trạng thái cuối nhưng khác HTTP status | Xử lý 404/409 theo business policy |
| Long-running operation kickoff | Có thể khởi tạo job lặp | Operation ID và polling/reconciliation |
| Upload stream không replayable | Request body không đọc lại được | Buffering/replay strategy hoặc không retry tùy loại |

**HTTP verb không tự đủ để kết luận tính idempotent**. Ví dụ PUT overwrite có thể gây mất cập nhật nếu hai writers cạnh tranh. GET có thể trigger side effects ở dịch vụ thiết kế sai. Kiểm tra operation contract thực tế.

### 12.2. Kết quả mơ hồ sau timeout

~~~text
Client gửi tạo entity
    ↓
Service đã commit
    ↓
Response bị mất do network
    ↓
Client nhận timeout
    ↓
Client retry tạo một entity mới
    ↓
Duplicate business record
~~~

Cách giải quyết:

1. Dùng business ID/request ID ổn định.
2. Gửi conditional create/upsert theo SDK và service.
3. Đọc lại trạng thái bằng ID trước khi tạo mới khi appropriate.
4. Có unique constraint ở storage/database, không chỉ query trước insert.
5. Với workflow nhiều services, dùng outbox/saga/reconciliation.
6. Log correlation của request mà không ghi PII.
7. Không retry không giới hạn chỉ vì exception class là timeout.

### 12.3. ETag và optimistic concurrency

Các Azure services như Blob Storage thường hỗ trợ conditional requests dựa **ETag**. Mẫu khái niệm:

~~~text
Read resource → ETag = A
Update with If-Match: A

Nếu một writer khác đã cập nhật:
  service trả precondition failure (ví dụ 412)
  → cần đọc lại, giải quyết conflict
  → không retry y nguyên mãi
~~~

Đừng tự sửa ETag để làm write thành công. Với tính toán dựa trên dữ liệu cũ, một 412 có thể yêu cầu kiểm tra lại business state và transaction logic.

### 12.4. Cancellation không phải rollback

Khi ứng dụng hết deadline và hủy publisher/request:

- Network request có thể đã tới server.
- Server có thể đã commit dữ liệu.
- SDK có thể không nhận response.
- Caller có thể retry cả business operation.

Vì thế **cancellation giúp kiểm soát tài nguyên và latency**, nhưng vẫn cần verification/idempotency cho operations có side effects.



## 13. Logging, tracing và bảo mật HTTP pipeline

### 13.1. HttpLogOptions và mức độ chi tiết

Những service client builders hiện đại thường hỗ trợ **httpLogOptions(...)** để kiểm soát những thông tin HTTP được SDK ghi lại.

| Mức | Nội dung thường ghi | Khuyến nghị |
|---|---|---|
| NONE | Không ghi HTTP request/response logs qua policy đó | Môi trường hạn chế logs |
| BASIC | Method, URL được xử lý an toàn, status, thời gian | Điểm khởi đầu tương đối an toàn |
| HEADERS | Thêm headers được cho phép | Chẩn đoán có kiểm soát |
| BODY | Thêm body theo giới hạn SDK | Tránh production có PII |
| BODY_AND_HEADERS | Body và headers | Không làm mặc định production |

**Không dùng BODY_AND_HEADERS làm mặc định production.** Redaction/allowlist của SDK rất hữu ích, nhưng body có thể chứa credentials hoặc dữ liệu cá nhân và custom headers/queries có thể chưa được phân loại đúng.

### 13.2. Cấu hình BASIC

~~~java
import com.azure.core.http.policy.HttpLogDetailLevel;
import com.azure.core.http.policy.HttpLogOptions;

HttpLogOptions logOptions = new HttpLogOptions()
    .setLogLevel(HttpLogDetailLevel.BASIC);

// Dùng với builder hỗ trợ:
// clientBuilder.httpLogOptions(logOptions);
~~~

SDK cũng có khả năng cấu hình một số log settings qua environment variables như **AZURE_HTTP_LOG_DETAIL_LEVEL** ở những client hỗ trợ. Đừng bật globally mức logging chi tiết trong production nếu chưa xem tác động lên tất cả Azure SDK clients.

### 13.3. Allowed headers và query parameters

Có thể mở rộng allowlist cho headers an toàn khi cần:

~~~java
HttpLogOptions logOptions = new HttpLogOptions()
    .setLogLevel(HttpLogDetailLevel.HEADERS)
    .addAllowedHeaderName("x-safe-business-operation");
~~~

Đây là một header placeholder; đừng cho vào allowlist những trường chứa Authorization, Cookie, SAS signature, client secret, PII hoặc token. URL có thể chứa Blob names/sensitive paths hoặc SAS query; custom logging policy tốt nhất không log raw URL khi chưa có redaction.

### 13.4. Structured metrics và traces

Một bộ đo có thể bao gồm:

~~~text
azure_dependency_requests_total
azure_dependency_attempts_total
azure_dependency_retries_total
azure_dependency_duration_ms
azure_dependency_attempt_duration_ms
azure_dependency_errors_total
azure_dependency_throttled_total
azure_dependency_in_flight
~~~

Tên metrics trên là **gợi ý kiến trúc**, không phải metrics tự có trong mọi Azure SDK version.

Tags nên có: serviceType, operation category, statusClass, errorClass, environment và region. Không gắn request ID, full URL, user ID hay Blob name tùy ý làm metric labels vì gây high cardinality và tăng nguy cơ rò rỉ dữ liệu. Correlation ID/trace ID phù hợp hơn với traces/logs có kiểm soát.

### 13.5. OpenTelemetry và Azure Monitor

Trong ứng dụng Java, có thể sử dụng instrumentation/OpenTelemetry và Azure Monitor/Application Insights theo stack đã phê duyệt để:

- Liên kết inbound request với outbound Azure SDK dependencies.
- Đo p50/p95/p99 và tỷ lệ lỗi từng dependency.
- Phân biệt 429, network timeout và RBAC error.
- So số lần retry thực với số operation ban đầu.
- Truy nguồn release/runtime gây regression.
- Phân quyền logs/traces và đặt retention phù hợp.

Không mặc định mọi service client phát một span riêng cho **từng attempt** ở mọi phiên bản. Nếu cần attempt-level telemetry, quan sát các SDK logging/tracing hooks hiện hành hoặc bổ sung policy PER_RETRY được kiểm thử kỹ.

## 14. Reactor async, total timeout và cancellation

### 14.1. Async client với Mono

Azure SDK for Java có nhiều clients bất đồng bộ trả **Mono/Flux**. Một lời gọi tạo publisher; network execution có thể bắt đầu khi có subscription.

~~~java
import com.azure.data.appconfiguration.ConfigurationAsyncClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import reactor.core.publisher.Mono;
import java.time.Duration;

ConfigurationAsyncClient client =
    new ConfigurationClientBuilder()
        .endpoint(System.getenv("AZURE_APPCONFIG_ENDPOINT"))
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildAsyncClient();

Mono<?> operation = client
    .getConfigurationSetting("app.mode", null)
    .timeout(Duration.ofSeconds(4));
~~~

**Mono.timeout(Duration.ofSeconds(4))** áp thời hạn cho publisher, không phải thiết lập Netty connect/read/write timeout. Khi timeout, request có thể bị cancel ở client nhưng server vẫn có thể đã commit một write trước đó.

### 14.2. Những bẫy reactive

- **subscribe hai lần** trên publisher lạnh có thể tạo hai network operations.
- **retryWhen(...)** ở application có thể tạo thêm vòng retry bên ngoài SDK.
- **block()** trong Reactor/Netty event-loop có thể gây starvation hoặc runtime exception.
- **Thread.sleep** trong reactive callback chặn event loop, giảm throughput.
- Timeout trên publisher không đồng nghĩa rollback transaction ở service.
- Async client vẫn cần concurrency limit, rate limit và bounded queues; async không làm Azure service có capacity vô hạn.

Ví dụ không nên làm:

~~~java
// KHÔNG làm trong reactive callback/event loop:
// sdkMono.map(value -> {
//     Thread.sleep(2000);
//     return value;
// });
~~~

Nếu cần một nghiệp vụ có nhiều bước và side effects, dùng durable state/idempotency, không chỉ Mono.timeout rồi tự gọi lại toàn bộ workflow.

### 14.3. Cấp deadline theo phụ thuộc

API user-facing cần deadline tổng, trong khi những batch/long-running jobs có thể dài hơn. Một application-level deadline có thể cần:
- Hủy dependency calls khi hết budget.
- Giới hạn số retries theo thời gian còn lại.
- Tôn trọng Retry-After chỉ khi còn kịp deadline.
- Trả lỗi hoặc queue work theo nghiệp vụ.
- Kiểm tra trạng thái sau timeout nếu operation có side effects.

Không đặt app timeout 2 giây rồi cho SDK bốn attempts, mỗi attempt response timeout 30 giây và kỳ vọng latency không bị ảnh hưởng.

## 15. Authentication, network và policy ordering

### 15.1. Không tự viết lại authentication nếu không cần

**DefaultAzureCredential** cung cấp token từ môi trường phù hợp, Azure SDK service builder thường tự cấu hình policy xác thực theo service audience/scope.

Khi dựng toàn bộ HttpPipeline thủ công, rất dễ:
- Bỏ qua token authentication policy.
- Sử dụng sai scope khi kết nối cloud khác.
- Không refresh token đúng.
- Thêm Authorization header quá sớm/muộn.
- Ghi lộ token khi debug.
- Bỏ một policy service-specific bắt buộc.

Với đa số ứng dụng, chọn **builder.credential(...) + builder.httpClient(...) + builder.retryOptions(...) + builder.addPolicy(...)** thay vì tự tạo Authorization header.

### 15.2. Những lỗi không chữa được bằng retries

| Triệu chứng | Lớp nghi ngờ | Hướng xử lý |
|---|---|---|
| 401 | Token/credential/audience | Entra identity, tenant, scope |
| 403 | RBAC/ACL/firewall/policy | Data-plane role và network |
| DNS resolution failure | Private DNS, resolver, hostname | Test DNS từ runtime |
| TLS certificate error | CA trust, hostname, clock | Không tắt TLS verification |
| Connect timeout | Proxy/firewall/route/service | Kiểm tra TCP/NSG |
| 429 | Quota/throttling | Backoff, Retry-After, giảm tải |
| Response timeout | Server chậm hoặc mạng | Đo latency, query/workload |
| Read timeout | Response/chunk chậm | Đo payload/network throughput |
| 412 | Concurrent writer / ETag | Đọc lại và giải quyết precondition |

Không cấp role Owner để giải quyết một lỗi DNS; không mở Storage public network để chữa 403 từ thiếu ACL.

### 15.3. Phân biệt management và data-plane RBAC

Một managed identity có Azure Contributor trên resource group **không mặc định** được tải Blob hoặc đọc Key Vault secret. Nó cần data-plane roles phù hợp, chẳng hạn Storage Blob Data Reader/Contributor hoặc Key Vault Secrets User theo tính năng và permission model.

Trước khi chỉnh retry hãy xác định:
1. Identity nào được DefaultAzureCredential chọn ở runtime.
2. Có đúng service endpoint/tenant/cloud không.
3. Role assignment có hiệu lực tại scope phù hợp không.
4. VNet/Private Endpoint/DNS đã chính xác không.
5. Firewall/trusted-services settings có chặn workload không.
6. Service hiện trả status/SDK exception nào.

### 15.4. Các môi trường triển khai Azure

- **App Service**: managed identity, VNet integration, outbound networking và instance scale-out.
- **AKS**: workload identity, pod DNS/egress, HPA và HTTP connection pools.
- **Azure Functions**: cold starts, trigger-level retries, host concurrency và SDK retries có thể tương tác.
- **Azure VM/Batch**: identity/proxy/TLS configuration, thread pool và worker lifecycle.

Một retry policy có thể phù hợp với user-facing App Service nhưng quá ngắn cho batch upload hàng GB, hoặc quá dài cho Azure Function có timeout nghiêm ngặt. Thiết kế theo từng workload thay vì sao chép cố định một profile.

## 16. Chọn timeout/retry theo tình huống

### 16.1. Đọc feature flag của user-facing API

Yêu cầu p95 latency thấp, flag có thể cache. Phương án:
- Singleton App Configuration client.
- Có cache/refresh theo freshness policy.
- Giới hạn total deadline ngắn.
- Retry ít hoặc không nếu đã có cache fallback an toàn.
- Circuit breaker khi service lỗi kéo dài.
- Monitor cache age và lỗi refresh.

Không bắt buộc gọi App Configuration cho **mỗi HTTP request** nếu semantic caching phù hợp.

### 16.2. Batch upload Blob lớn

Yêu cầu upload file 500 MB qua mạng biến động:
- Dùng Azure Storage SDK với chunking/concurrency thích hợp.
- Chọn RequestRetryOptions và tryTimeout theo chunk size/bandwidth.
- Không dùng per-try timeout quá ngắn cho mọi upload.
- Đảm bảo payload/stream có thể replay khi retry.
- Giữ blob name stable và dùng conditional write khi cần.
- Theo dõi tổng thời gian, số blocks, retries và cost.
- Xác minh trạng thái cuối cùng khi gặp timeout mơ hồ.

### 16.3. Lấy secret từ Key Vault

- TokenCredential và role đúng.
- Retry 429/5xx theo SDK và server hints.
- Tránh log secret body.
- Cân nhắc cache/rotation có kiểm soát.
- Giữ client singleton.
- Không retry 403 do thiếu quyền.

### 16.4. Azure Resource Manager long-running operation

Long-running operation (LRO) có thể gồm HTTP request để bắt đầu triển khai và nhiều polling requests để theo dõi provisioning. **Polling interval, HTTP retry delay và total job deadline là ba khái niệm riêng**.

Khi timeout:
- Đọc lại provisioningState/resource ID.
- Không gửi lại lệnh tạo resource với ID mới mà không kiểm tra.
- Sử dụng SDK polling APIs và retry guidance.
- Ghi correlation/activity logs và approval.

### 16.5. Ma trận lựa chọn ban đầu

| Workload | Retry | Timeout nên chú ý | Biện pháp khác |
|---|---|---|---|
| User-facing read | Ít, ngắn | Total API deadline | Cache/circuit breaker |
| Background ETL | Có kiểm soát | Per-try + job deadline | Queue/replay |
| Large Blob upload | Storage-specific | Write/read/try + total | Chunking, conditional write |
| Key Vault lookup | SDK-aware | Connect/response | Cache, secret hygiene |
| ARM resource creation | HTTP retry + LRO polling | Total job deadline | Verify state |
| Queue/event send | Service-specific | Attempt/operation | Stable IDs/dedup |
| Reactive high volume | Bounded retry | Per-dependency budget | Backpressure/rate limit |

Không có một bộ timeout/retry “tốt nhất” cho mọi ứng dụng. Đầu vào phải là SLO, p95/p99, quota dịch vụ, network và rủi ro side effects.



## 17. Kiểm thử timeout, retry và custom policies

### 17.1. Vì sao phải fault-injection test?

Một client build thành công vẫn có thể sai ở runtime: retry bị lồng nhiều tầng, request body không thể phát lại, thiếu authentication policy, per-call metrics bị đếm sai, hoặc service đã commit nhưng caller timeout dẫn tới ghi trùng.

Cần kiểm tra **số HTTP attempts, trạng thái cuối, elapsed time, tính idempotent, log redaction và khả năng phục hồi**.

| Test case | Mock server/transport giả lập | Điều kiện đạt |
|---|---|---|
| Thành công | 200 ngay | Một transport send, một per-call event |
| 503 rồi 200 | Lỗi transient rồi hồi phục | Retry đúng cap, trả thành công |
| 429 + Retry-After | Server yêu cầu chờ | Không retry sớm trái contract |
| 400 | Invalid request | Không retry vô ích |
| 403 | Forbidden | Không che lỗi RBAC bằng retry |
| Network reset | Cắt kết nối khi đang đọc | Fail/retry có giới hạn |
| Connect stall | Không thiết lập được TCP | Connect timeout có hiệu lực |
| Response delay | Chậm first byte | Response timeout có hiệu lực |
| Read stall | Đã gửi headers nhưng dừng body | Read timeout có hiệu lực |
| Write stall | Server đọc body chậm | Write timeout có hiệu lực |
| Async client | Mono được subscribe | Không block event loop |
| Sync client | buildClient được sử dụng | Custom processSync chuyển tiếp |
| Timeout sau commit | Server ghi xong, bỏ response | Không tạo duplicate |
| Retry lồng | App retry và SDK retry | Attempts trong budget |
| Logs nhạy cảm | Giả lập SAS/Authorization/PII | Không lộ credentials |
| Cancellation | Caller hủy giữa request | Trạng thái write được xác minh |

### 17.2. Test PER_CALL vs PER_RETRY

Giả lập:

~~~text
HTTP attempt #1 → 503
HTTP attempt #2 → 503
HTTP attempt #3 → 200

Expected (khi retry các status này):
  PER_CALL executions = 1
  PER_RETRY executions = 3
  HTTP transport sends = 3
  Final response = 200
~~~

Đây là kết quả của **một service-client invocation**. Nếu caller tự subscribe lại publisher hoặc retry ở application, PER_CALL có thể được gọi thêm; phải phân biệt SDK attempt và business attempt.

### 17.3. Công cụ và phạm vi kiểm thử

- Dùng mock HttpClient hoặc local HTTP stub server/WireMock/MockWebServer phù hợp dependency.
- Dùng giả lập status, Retry-After, delays, connection reset, partial body.
- Đo thời gian trong test có tolerance hợp lý; jitter khiến backoff không nhất thiết chính xác từng mili-giây.
- Test cả buildClient() và buildAsyncClient() với custom policy.
- Kiểm tra log không chứa Authorization, SAS signature, connection string hay PII.
- Với reactive chain, kiểm tra timeout và re-subscription.
- Trên staging Azure được cấp phép, kiểm tra DNS/TLS/managed identity và service quotas thật.
- Không gây sự cố throttling lên tài nguyên production của người khác.

Mock transport không tái tạo toàn bộ TLS, private DNS, connection reuse hay service-side throttling. Cần một số integration tests trên staging.

### 17.4. Test idempotency thay vì chỉ status

Một test quan trọng:
1. Server giả lập nhận POST và tạo object thành công.
2. Trước khi gửi response, server ngắt kết nối.
3. Client gặp IOException/timeout rồi retry.
4. Hệ thống dùng idempotency key/conditional create.
5. Kết quả cuối chỉ có **một** business object, không phải hai.

Nếu test chỉ assert HTTP cuối cùng là 200 mà không kiểm tra số records, nó không phát hiện lỗi double charge/double create.

## 18. Monitoring và SLO trong production

### 18.1. Những tín hiệu nên theo dõi

| Tín hiệu | Câu hỏi |
|---|---|
| Logical operations/s | App thật sự yêu cầu bao nhiêu thao tác? |
| HTTP attempts/s | Có retry amplification không? |
| Retry rate | Transient errors tăng hay không? |
| Throttling 429 | Đã vượt quotas/service limit? |
| Authentication 401/403 | Identity/permission sai sau rollout? |
| Connect timeout | DNS/network/proxy lỗi? |
| Response/read timeout | Phía server hoặc payload chậm? |
| Dependency p95/p99 | Có ảnh hưởng API SLA? |
| In-flight requests | Connection pool/thread pool có quá tải? |
| Circuit breaker state | Dependency mất sẵn sàng kéo dài? |
| SDK/transport version | Regression sau update? |
| Azure service transactions | Chi phí và hạn ngạch bị khuếch đại? |

### 18.2. SLO minh họa

~~~text
SLI: tỷ lệ valid API operations hoàn tất trong 500 ms.
SLO: >= 99.5% trên 30 ngày (mục tiêu ví dụ).
Alert: error budget burn rate hoặc dependency p99 tăng.
~~~

Đây là SLO **nội bộ minh họa**, không phải Azure service SLA. Một Azure dependency có p95 thấp không bảo đảm API tổng đạt SLO nếu còn nhiều I/O/CPU steps khác.

### 18.3. Đo hiệu quả của retry

~~~text
Logical operations:       10,000
HTTP attempts:            13,000
Retry amplification:      1.30x
Final success rate:       99.2%
First-attempt success:    94.0%
~~~

Nếu retry nâng tỷ lệ thành công nhưng p99 vượt SLO, cần giảm retries hoặc chuyển tác vụ sang queue. Nếu retry không tăng success mà 429 tăng, pipeline đang tăng tải có hại.

### 18.4. KQL minh họa

Nếu instrumentation gửi dependency records vào bảng **AppDependencies** của Application Insights workspace-based:

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize Total=count(),
            Failed=countif(Success == false),
            P95ms=percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), Target
| order by TimeGenerated asc
~~~

Tùy telemetry schema, tên bảng/cột và query có thể khác. Không thấy kết quả không chứng minh không có lỗi nếu data collection/sampling chưa được thiết lập.

### 18.5. Metric cardinality và privacy

Không đưa request ID, full URI, Blob name có PII, user email hay SAS signature vào metrics labels. Dùng tags có tập giá trị giới hạn: service, operation, environment, status class, error class, region. Đưa correlation IDs vào logs/traces có RBAC và retention thích hợp.

## 19. Runbook troubleshooting

### 19.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Client build fail | Dependency/transport version lệch | Kiểm tra azure-sdk-bom, Maven tree |
| 401 sau custom pipeline | Thiếu auth policy/sai scope | Quay về builder/credential |
| 403 Blob | Storage data-plane RBAC/ACL/firewall | Kiểm tra role, network |
| DNS failure | Private DNS, resolver | Test từ App Service/Pod |
| TLS handshake failure | Certificate/clock/proxy | Kiểm tra trust chain |
| Connect timeout | Route/NSG/firewall | Đo kết nối từ runtime |
| Response timeout | Server chậm/overload | Metrics, capacity và budget |
| Read timeout | Stream/chunk bị chậm | Payload/network/read setting |
| Write timeout | Upload chậm | Chunk size/throughput |
| 429 liên tục | Throttling/retry storm | Retry-After, limit concurrency |
| 503 kéo dài | Service incident | Circuit breaker/fallback |
| 409/412 | Conflict/ETag stale | Read state, resolve concurrency |
| p99 cao | Retry × timeout × backoff | Tổng deadline và retry owners |
| Reactive app treo | block()/sleep trên event loop | Bỏ blocking |
| SDK retry sai số lần | PER_CALL/PER_RETRY, nested retries | Count actual sends |
| Upload kết quả mơ hồ | Response mất sau server commit | Verify Blob state/ETag |
| Rò rỉ token qua log | HTTP BODY/headers hoặc custom policy | Redact, rotate và audit |
| LRO tạo trùng | Retry kickoff không kiểm tra state | Poll provisioningState |

### 19.2. Runbook HTTP 429

1. Xác định dependency nào thực sự trả 429.
2. Kiểm tra quotas, throughput, concurrency và tốc độ request.
3. Kiểm tra các vòng retry ở SDK, framework, gateway và worker.
4. Xem Retry-After/service-specific headers.
5. Đo HTTP attempts trên một logical operation.
6. Giảm concurrency hoặc dùng queue/backpressure.
7. Chỉnh backoff, số retries và total deadline.
8. Tăng capacity/quota nếu được hỗ trợ và phê duyệt.
9. Load test trên staging.
10. Theo dõi kết quả: 429, p95/p99, operation count, cost.

### 19.3. Runbook timeout sau khi bật Private Endpoint

1. Xác định app runtime thực (Pod/Function/App Service/VM).
2. Kiểm tra endpoint FQDN trong builder.
3. Resolve DNS từ runtime đó.
4. Kiểm tra Private DNS Zones, resolver và VNet links.
5. Kiểm tra VNet integration, NSG, route, firewall/proxy.
6. Kiểm tra TLS hostname và certificate.
7. Kiểm tra token endpoint/managed identity route.
8. Phân biệt DNS/TCP timeout với 403 data-plane.
9. Không mở public network quá mức để chữa lỗi tạm.
10. Ghi evidence và cập nhật runbook.

### 19.4. Runbook timeout sau một write

1. Ghi lại operation ID/resource ID và UTC timestamp.
2. Xác định liệu server có thể đã commit hay không.
3. Đọc lại resource state bằng một GET phù hợp.
4. Đối chiếu ETag/version/idempotency key.
5. Nếu đã commit đúng thì không ghi lại.
6. Nếu chưa commit, retry theo điều kiện an toàn.
7. Nếu trạng thái mơ hồ, chuyển reconciliation/manual review.
8. Kiểm tra không có duplicate business side effects.
9. Điều chỉnh timeout/rate/circuit breaker theo nguyên nhân.
10. Không coi client cancellation là transaction rollback.

### 19.5. Runbook regression sau upgrade SDK

- Kiểm tra azure-core, transport, library versions và dependency convergence.
- Xem retryOptions, retryPolicy và pipeline precedence.
- So per-attempt/per-operation metrics trước và sau update.
- Kiểm tra JDK/TLS/proxy changes.
- Chạy mock 429/503/timeouts tests.
- Chạy integration/canary trên staging.
- Rollback có kiểm soát nếu p99/error/cost xấu đi.
- Ghi release notes và ADR về timeout/retry profile.



## 20. Thiết kế cấu hình HTTP theo workload

### 20.1. Không dùng một timeout cho mọi dependency

- **App Configuration:** đọc cấu hình/feature flags nhỏ, latency tương tác, có thể cache.
- **Key Vault:** secret nhạy cảm, rotation, cần hạn chế requests/quota.
- **Blob Storage:** upload/download có payload lớn và multiple block requests.
- **Resource Manager:** triển khai tài nguyên có long-running operations và polling.
- **Queue/Events:** duplicate delivery, message ID, lock semantics.
- **Cosmos DB:** có SDK và retry/transport abstractions chuyên biệt, không áp máy móc mọi ví dụ azure-core chung.

Một kiến trúc Java nên xác định **retry profile theo service/operation**, có validation, đo thực tế và phê duyệt thay đổi.

### 20.2. Mẫu cấu hình minh họa

~~~json
{
  "serviceProfiles": {
    "appConfiguration": {
      "connectTimeoutMs": 3000,
      "responseTimeoutMs": 5000,
      "readTimeoutMs": 5000,
      "writeTimeoutMs": 5000,
      "maxRetries": 2,
      "baseDelayMs": 200,
      "maxDelayMs": 1200
    },
    "blobUpload": {
      "connectTimeoutMs": 5000,
      "responseTimeoutMs": 30000,
      "readTimeoutMs": 60000,
      "writeTimeoutMs": 60000,
      "maxTries": 4,
      "tryTimeoutMs": 30000
    }
  }
}
~~~

Đây là **application configuration do nhóm tự định nghĩa**, không phải JSON SDK tự nhận. Cần map vào các builders chính xác:

1. Validate Duration dương và max retry cap.
2. Không cho cấu hình tắt timeout bằng giá trị 0 tùy ý.
3. Tách total operation deadline khỏi transport timeout.
4. Ghi version/profile trong release metadata.
5. Cập nhật test fixtures khi thay retry profile.
6. Review rủi ro tăng quota/cost và latency khi rollout.

### 20.3. Client lifecycle trong Java

Một ứng dụng Spring Boot/Micronaut/Quarkus hoặc Java service lâu dài nên:
- Khởi tạo credential theo identity policy.
- Tạo transport và Azure clients lúc startup/DI.
- Reuse clients giữa nhiều HTTP requests.
- Theo dõi connection pool và in-flight operations.
- Không tạo event-loop/HttpClient mới trên mỗi request.
- Quản lý shutdown/close theo API của transport/client khi có yêu cầu.

Nếu nhiều Azure services có nhu cầu network/TLS khác nhau, không ép tất cả dùng chung một transport với proxy/certificates không tương thích.

## 21. Case study: Java Orders API trên Azure

### 21.1. Đầu bài

Một dịch vụ Java trên Azure App Service/AKS:
- Đọc feature flags từ App Configuration.
- Lấy secret từ Key Vault ở startup/rotation.
- Lưu invoice PDF lên Blob Storage.
- Ghi trạng thái đơn hàng vào Azure SQL Database.
- Có mục tiêu p95 nhỏ cho HTTP API.
- Có background invoice upload dài hơn.
- Không được tạo trùng hóa đơn vì timeout/retry.
- Có Private Endpoint/managed identity theo yêu cầu bảo mật.

~~~mermaid
flowchart LR
    C["Client"] --> APP["Java API App Service / AKS"]
    APP --> CFG["App Configuration"]
    APP --> KV["Key Vault"]
    APP --> DB["Azure SQL Database"]
    APP --> BLOB["Blob Storage"]
    APP --> MON["Azure Monitor / Application Insights"]
~~~

### 21.2. Phân chia retry ownership

| Bước | Chủ sở hữu retry | Tính đúng đắn |
|---|---|---|
| Đọc App Configuration | SDK trong deadline ngắn | Cache/fallback theo freshness policy |
| Lấy Key Vault secret | SDK theo server hints | Secret rotation và least privilege |
| Upload Blob | Storage SDK với per-try timeout | Stable blob name, ETag/conditional write |
| Azure SQL transaction | JDBC/DB logic riêng | Unique constraint/transaction/outbox |
| HTTP ingress | Gateway không tự retry POST tùy tiện | Idempotency key |
| Background invoice job | Queue/worker scheduler | Stable invoice ID và reconciliation |

**Azure SDK HTTP RetryPolicy không trực tiếp điều khiển SQL JDBC transactions**. Nếu SDK upload thành công nhưng worker không nhận response, không nên khởi tạo một invoice mới với blob name ngẫu nhiên.

### 21.3. Kịch bản 429 do scale-out

Một đợt giảm giá khiến App Service tăng từ 5 lên 50 instances. Mỗi instance đọc config từng request. Service bắt đầu trả 429; mọi instance retry cùng delay, khiến 429 và p99 tăng.

Cải thiện:
1. Cache/refresh config có kiểm soát.
2. Retry thấp trong total deadline của API.
3. Tôn trọng Retry-After.
4. Rate-limit các refresh operations.
5. Jitter để tránh retries cùng nhịp.
6. Circuit breaker/fallback nếu business cho phép.
7. Đo actual HTTP attempts thay vì chỉ SDK calls.
8. Load test trên staging sau thay đổi.

### 21.4. Kịch bản upload timeout nhưng service đã commit

~~~text
Worker tạo invoice với invoiceId ổn định.
Storage nhận và commit upload.
Network làm mất response.
Worker thấy timeout.
Lần thử lại phải kiểm tra object state/ETag
hoặc dùng conditional create và cùng blob name.
~~~

Cần giữ durable processing state và chỉ đánh dấu completed sau khi xác minh; gửi invoice email cần có idempotency key riêng để tránh duplicate notifications.

### 21.5. Tiêu chí chấp nhận

- Managed identity và quyền data plane đúng.
- Không có secrets trong logs.
- Azure service clients được reuse.
- Không lồng retry vô chủ đích.
- Timeout phân biệt connect/response/read/write/total.
- 429 được giảm tải, không làm retry storm.
- Upload không tạo duplicate invoices.
- P95/p99 và chi phí trong ngưỡng đã cam kết.
- Có fault-injection evidence và runbook.
- Có rollback nếu đổi retry settings gây regression.

## 22. Những bẫy thường gặp

1. **Thêm RetryPolicy mới bằng addPolicy:** có thể tạo retry lồng hoặc phá policy order; ưu tiên retryOptions/retryPolicy do builder hỗ trợ.
2. **Nhầm pipeline(...) với httpClient(...):** pipeline thay toàn bộ policies, có thể bỏ qua credential/retry/log settings.
3. **Duration.ZERO là timeout tức thì:** ở một số transport nó tắt timeout; dùng duration dương.
4. **Chỉ set connectTimeout:** không giới hạn response/read/write hoặc total duration.
5. **Nhầm maxRetries với maxTries:** làm số attempts nhiều hơn dự kiến.
6. **Retry mọi 4xx:** 400/401/403/412 thường yêu cầu sửa input/identity/concurrency.
7. **Bỏ Retry-After:** gây 429 liên tiếp và tăng chi phí.
8. **Coi POST tự idempotent:** có thể tạo hai entities khi response bị mất.
9. **Log BODY_AND_HEADERS production:** có thể lộ secret/PII và gây overhead.
10. **block()/Thread.sleep trong reactive event loop:** giảm throughput hoặc deadlock-like starvation.
11. **Tăng timeout để chữa DNS/firewall:** chỉ làm lỗi đến muộn hơn.
12. **Tạo HttpClient mỗi API request:** gây init/pooling overhead.
13. **Không test sau nâng BOM:** version thay đổi có thể ảnh hưởng transport/retries.
14. **Tối ưu success rate mà bỏ qua p99:** retry quá lâu làm API vi phạm SLO.
15. **Tắt TLS hostname verification:** nguy cơ lộ token/dữ liệu, không phải workaround được chấp nhận.
16. **Dùng client timeout như transaction rollback:** server có thể đã hoàn tất write.



## 23. Checklist trước production

### Dependencies và client lifecycle

- [ ] Dùng Azure SDK for Java phù hợp, không trộn nhầm SDK đời cũ.
- [ ] azure-core, transport và service SDK versions tương thích theo BOM.
- [ ] Không có conflict Netty/OkHttp/JDK HTTP transports ngoài ý muốn.
- [ ] Builder thực sự hỗ trợ httpClient/retryOptions/addPolicy như code.
- [ ] Clients được tạo qua DI/singleton, không theo từng HTTP request.
- [ ] Java runtime/TLS/transport có security patch thích hợp.
- [ ] SDK upgrades có regression tests và canary.

### HTTP pipeline

- [ ] Ưu tiên builder customization thay cho tự lắp full pipeline.
- [ ] PER_CALL/PER_RETRY được chọn theo mục tiêu operation/attempt.
- [ ] Custom policy hỗ trợ sync và async khi cần.
- [ ] Không gọi next.process nhiều lần ngoài thiết kế.
- [ ] Không thêm RetryPolicy trùng với policy SDK mặc định.
- [ ] Không ghi đè Authorization hoặc signed headers.
- [ ] Per-request state không nằm trong shared mutable fields.
- [ ] Nếu dùng pipeline(...), authentication và service policies được review.
- [ ] Có correlation/traces và metrics an toàn.

### Timeout và retry

- [ ] Connect/response/read/write timeout có lý do và giá trị dương.
- [ ] Per-try timeout khác total operation deadline.
- [ ] maxRetries khác Storage maxTries được hiểu đúng.
- [ ] Có max retry count và total time budget.
- [ ] Retry-After/server hints được tôn trọng theo khả năng SDK.
- [ ] Retry không vượt SLO business.
- [ ] Không có app/gateway/SDK retry nesting ngoài chủ đích.
- [ ] POST/PUT side effects có idempotency/conditional writes.
- [ ] Có backoff+jitter, concurrency limit/rate limiter khi cần.
- [ ] Có circuit breaker/queue khi dependency lỗi kéo dài.
- [ ] Không dựa vào cancellation như một rollback guarantee.

### Bảo mật và vận hành

- [ ] DefaultAzureCredential chọn đúng identity ở runtime.
- [ ] Data-plane RBAC/ACL theo least privilege.
- [ ] TLS hostname/certificate validation vẫn bật.
- [ ] Private DNS/VNet/Private Endpoint kiểm tra từ runtime thật.
- [ ] HttpLogOptions mức BASIC/NONE được cân nhắc cho production.
- [ ] Logs/traces không chứa SAS, token, secrets hoặc PII không cần thiết.
- [ ] Metrics có cardinality thấp và retention phù hợp.
- [ ] Có dashboards 429, 401/403, timeouts và p95/p99.
- [ ] Có fault-injection tests và mock 429/503/timeout.
- [ ] Có incident runbooks cho network/auth/retry storm.
- [ ] Có cost/quota monitoring cho số HTTP attempts tăng.
- [ ] Có approval và rollback plan khi đổi timeout/retry profile.

## 24. Câu hỏi tự kiểm tra

1. **HTTP pipeline của Azure SDK for Java gồm gì?** HTTP transport và chuỗi HTTP policies.
2. **HttpClient chịu trách nhiệm gì?** Kết nối và gửi/nhận HTTP.
3. **HttpPipelinePolicy có thể làm gì?** Quan sát/biến đổi request-response và chuyển tiếp.
4. **Policy PER_CALL chạy bao nhiêu lần?** Một lần cho mỗi pipeline invocation/service call.
5. **Policy PER_RETRY chạy khi nào?** Mỗi lần HTTP attempt trong retry loop.
6. **Vị trí mặc định của HttpPipelinePolicy ở SDK hiện hành?** PER_RETRY.
7. **Tại sao đặt metrics tổng operation ở PER_CALL?** Đo duration toàn operation có backoff.
8. **Tại sao đặt attempt count ở PER_RETRY?** Mỗi attempt cần được quan sát.
9. **Có nên tự tạo toàn bộ HttpPipeline cho mọi service client?** Không; thường dùng builder.
10. **httpClient(...) khác pipeline(...) ở đâu?** Một bên thay transport, một bên thay toàn pipeline.
11. **Vì sao pipeline(...) có rủi ro?** Có thể bỏ qua các cấu hình/auth policies của builder.
12. **Netty thường là transport mặc định không?** Có, trong nhiều Azure SDK for Java hiện đại.
13. **Connect timeout đo gì?** Giới hạn giai đoạn thiết lập kết nối.
14. **Response timeout đo gì?** Giai đoạn chờ server bắt đầu phản hồi theo transport.
15. **Read timeout có là total download timeout không?** Không mặc định; phụ thuộc read/inactivity semantics.
16. **Write timeout có nghĩa cả upload hoàn tất trong thời gian đó không?** Không nhất thiết; thường theo các hoạt động ghi.
17. **Duration.ZERO có luôn là timeout tức thì?** Không; nhiều transport có thể xem là tắt timeout.
18. **Total operation deadline khác per-try timeout thế nào?** Bao cả retries/backoff và application budget.
19. **RetryOptions dùng với đối tượng nào?** ExponentialBackoffOptions hoặc FixedDelayOptions.
20. **setMaxRetries(3) thường cho tối đa bao nhiêu HTTP attempts?** 4 kể cả lần đầu.
21. **Storage RequestRetryOptions maxTries=4 nghĩa gì?** Tối đa 4 attempts gồm lần đầu.
22. **Exponential backoff giúp gì?** Giảm burst retries khi lỗi tạm thời.
23. **Fixed delay có rủi ro gì khi nhiều clients?** Retry đồng bộ cùng nhịp.
24. **Retry-After có tác dụng gì?** Server báo thời gian nên chờ trước khi thử lại.
25. **HTTP 429 thường ám chỉ gì?** Rate limit/throttling.
26. **Có nên retry 403 để chữa thiếu role?** Không.
27. **HTTP 412 thường liên quan gì?** Precondition/ETag/concurrency mismatch.
28. **Network timeout có chắc server chưa commit không?** Không.
29. **POST có luôn idempotent không?** Không.
30. **Một cách tránh tạo đơn trùng?** Idempotency key ổn định và unique constraint.
31. **Có nên thêm RetryPolicy khác qua addPolicy nếu SDK đã có retry?** Không mặc định.
32. **Tại sao app retry × SDK retry nguy hiểm?** Nhân số attempts và latency.
33. **Circuit breaker phục vụ gì?** Fail fast khi dependency lỗi kéo dài.
34. **Bulkhead phục vụ gì?** Giới hạn concurrency/cô lập tài nguyên.
35. **Tại sao cần jitter?** Phân tán thời điểm retries giữa instances.
36. **Bật BODY_AND_HEADERS production có rủi ro?** Lộ PII/secrets, tăng chi phí/performance overhead.
37. **Metrics labels nên tránh gì?** Full URI, user ID, request ID, SAS query.
38. **Mono.timeout có thay Netty connectTimeout không?** Không.
39. **Có nên block trong Reactor event loop không?** Không.
40. **Một Mono subscribe hai lần có thể gửi hai requests không?** Có, tùy publisher/subscription.
41. **App Configuration Data Reader có khác Azure Contributor không?** Có, data-plane permission riêng.
42. **Blob upload 1GB có luôn một HTTP request không?** Không, SDK có thể chia blocks.
43. **Retry upload dùng secondaryHost luôn an toàn không?** Không, còn consistency và operation semantics.
44. **LRO polling interval có giống HTTP retry delay không?** Không.
45. **Có thể kiểm thử 429 trên mock không?** Có, không cần quá tải Azure production.
46. **Một fault-injection test nên assert gì?** Attempts, status, elapsed, side effects và redaction.
47. **Khi 401 sau custom pipeline cần kiểm tra gì?** Authentication policy, token, scope.
48. **Khi bật Private Endpoint xảy ra connect timeout cần kiểm tra gì?** DNS, VNet route, NSG/firewall từ runtime.
49. **Vì sao theo dõi HTTP attempts khác logical operations?** Để phát hiện retry amplification.
50. **Một chính sách HTTP production tốt gồm gì?** Pipeline an toàn, timeout budget, bounded retries, idempotency, least privilege, observability, test và runbook.

## 25. Tài liệu tham khảo

Các nguồn chính thức để tra cứu API chính xác theo phiên bản Azure SDK đang sử dụng:

- [HTTP clients and pipelines in Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipeline) — transport, pipeline, policy positions, builder customization.
- [Azure SDK for Java overview](https://learn.microsoft.com/azure/developer/java/sdk/overview) — phạm vi SDK và tài liệu Java.
- [Azure Core HTTP pipeline policy interface](https://learn.microsoft.com/java/api/com.azure.core.http.policy.httppipelinepolicy) — process, processSync, getPipelinePosition.
- [HTTP pipeline package](https://learn.microsoft.com/java/api/com.azure.core.http) — HttpPipeline/HttpClient/HttpPipelineBuilder.
- [HTTP policy package](https://learn.microsoft.com/java/api/com.azure.core.http.policy) — RetryPolicy, logging và policy types.
- [RetryOptions Java API](https://learn.microsoft.com/java/api/com.azure.core.http.policy.retryoptions) — RetryOptions/strategies.
- [ExponentialBackoffOptions Java API](https://learn.microsoft.com/java/api/com.azure.core.http.policy.exponentialbackoffoptions) — maxRetries/baseDelay/maxDelay.
- [RetryPolicy Java API](https://learn.microsoft.com/java/api/com.azure.core.http.policy.retrypolicy) — retry behavior.
- [NettyAsyncHttpClientBuilder Java API](https://learn.microsoft.com/java/api/com.azure.core.http.netty.nettyasynchttpclientbuilder) — connect, response, read, write timeouts.
- [RequestRetryOptions for Azure Storage](https://learn.microsoft.com/java/api/com.azure.storage.common.policy.requestretryoptions) — storage-specific maxTries/tryTimeout.
- [Implement a retry policy using Azure Storage for Java](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-java) — Blob client retry.
- [BlobServiceClientBuilder Java API](https://learn.microsoft.com/java/api/com.azure.storage.blob.blobserviceclientbuilder) — httpClient, addPolicy, retryOptions và pipeline precedence.
- [ConfigurationClientBuilder Java API](https://learn.microsoft.com/java/api/com.azure.data.appconfiguration.configurationclientbuilder) — Azure App Configuration client options.
- [Configure logging in Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/logging-overview) — HttpLogDetailLevel và redaction.
- [Troubleshooting Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/troubleshooting-overview) — diagnostics.
- [Azure Core source README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/core/azure-core/README.md) — transport, pipeline và timeout layers.
- [Azure Well-Architected retry strategy](https://learn.microsoft.com/azure/architecture/patterns/retry) — retry/backoff/idempotency.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — quan sát ngân sách và chi phí.

**Kết luận:** trong Azure SDK for Java, **HTTP transport** quyết định cách kết nối và truyền HTTP; **HttpPipelinePolicy** bổ sung xử lý ở phạm vi **PER_CALL hoặc PER_RETRY**; **RetryOptions/RetryPolicy** và những tùy chọn chuyên biệt như **Storage RequestRetryOptions** điều khiển retry. Để triển khai an toàn, hãy bắt đầu từ service client builder, cấu hình **connect/response/read/write timeout** và **total deadline** phù hợp, giữ retry **có giới hạn và tôn trọng Retry-After**, không nhân nhiều vòng retry, bảo đảm **idempotency** cho thao tác có side effects, bảo vệ credentials/logs và đo **HTTP attempts, latency p95/p99, throttling, error/cost**. Chỉ thay đổi chính sách ở production sau khi kiểm thử fault injection, xác minh quyền/network và có runbook rollback.

