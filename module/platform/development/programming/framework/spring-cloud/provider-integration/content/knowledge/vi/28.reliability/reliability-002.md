# Phân công retry giữa SDK, thư viện Spring và mã nghiệp vụ

Khi Spring Boot gọi Azure Blob Storage, Service Bus hoặc database, một lỗi mạng thoáng qua có thể khiến request thất bại dù thao tác vẫn có khả năng thành công nếu thử lại. Retry giúp tăng khả năng phục hồi, nhưng nếu **Azure SDK**, **thư viện resilience của Spring** và **mã nghiệp vụ** cùng tự retry một cách độc lập, số lần gọi có thể nhân lên, làm tăng tải, kéo dài latency và tạo tác dụng phụ trùng lặp.

Thiết kế đáng tin cậy cần phân công rõ **lớp nào chịu trách nhiệm retry cho loại lỗi nào**. SDK hiểu giao thức và lỗi transport; lớp resilience của ứng dụng quản lý hành vi ở cấp dependency; mã nghiệp vụ quyết định có nên thử lại một bước nghiệp vụ hay phải chuyển sang xử lý khác. Không phải mọi lỗi đều nên retry, và không phải mọi retry đều nên nằm ở cùng một lớp.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt retry ở **SDK**, **thư viện Spring/resilience** và **mã nghiệp vụ**.
2. Nhận diện retry tự động trong HTTP transport, Azure SDK, JDBC driver, messaging client và broker.
3. Phân loại lỗi có thể thử lại, lỗi cấu hình/quyền và lỗi nghiệp vụ không nên retry.
4. Tránh nhân số lần gọi khi nhiều lớp retry lồng nhau.
5. Kết hợp retry với deadline, backoff, jitter, circuit breaker, bulkhead và rate limit.
6. Thiết kế thao tác idempotent, deduplication, outbox/inbox và xử lý kết quả không xác định sau timeout.
7. Kiểm thử retry bằng cách đếm số request, mô phỏng lỗi, xác minh side effect và quan sát retry budget.
8. Chọn nơi đặt retry phù hợp cho Blob Storage, Service Bus, database và các dịch vụ đa cloud.

## 2. Ba lớp retry có trách nhiệm khác nhau

| Lớp | Hiểu biết chính | Phạm vi phù hợp | Ví dụ |
| --- | --- | --- | --- |
| **SDK/client của dịch vụ** | Giao thức, mã lỗi, retry header, connection reset, throttling và semantics API | Lỗi kỹ thuật tạm thời của một request/protocol exchange | Azure Storage SDK retry HTTP 429/503 theo policy; Service Bus SDK retry lỗi kết nối AMQP |
| **Thư viện resilience của Spring/ứng dụng** | Ngữ cảnh dependency, SLO, circuit breaker, bulkhead, concurrency và timeout | Bảo vệ một lời gọi dependency hoặc một ranh giới tích hợp | Resilience4j Retry/CircuitBreaker quanh BlobGateway |
| **Mã nghiệp vụ** | Trạng thái nghiệp vụ, idempotency, workflow, compensation và điều kiện thử lại | Quyết định thử lại một bước nghiệp vụ hoặc tiếp tục workflow | Thử lại xử lý đơn hàng sau khi kiểm tra trạng thái; xử lý message được giao lại |

**SDK retry** thường xử lý những lỗi mà client có thể đánh giá dựa trên protocol hoặc dịch vụ. **Spring resilience** quản lý cách ứng dụng tương tác với dependency trong tổng thể. **Business retry** quyết định liệu một hành động nghiệp vụ có còn hợp lệ và an toàn khi thực hiện lại hay không.

Ba lớp có thể cùng tồn tại, nhưng cần tránh cùng retry một lỗi giống nhau mà không có ngân sách chung.

### Sơ đồ trách nhiệm

~~~mermaid
flowchart TD
    A[Business workflow] --> B{Lỗi nghiệp vụ hay lỗi dependency?}
    B -->|Điều kiện nghiệp vụ có thể phục hồi| C[Business policy / workflow retry]
    B -->|Lỗi gọi dependency| D[Spring resilience boundary]
    D --> E{SDK có thể tự xử lý lỗi giao thức?}
    E -->|Có| F[SDK retry trong một attempt của ứng dụng]
    E -->|Không| G[Phân loại lỗi / circuit breaker / trả lỗi]
    F --> H[Azure / AWS / Google managed service]
    G --> I[Fallback hoặc trả lỗi có kiểm soát]
    C --> J[Kiểm tra trạng thái và idempotency]
    J --> A
~~~

Sơ đồ mô tả ranh giới trách nhiệm, không phải thứ tự bắt buộc cho mọi thư viện. Trong thực tế, Spring Retry có thể bao ngoài một SDK client đã bật retry; cần tính tổng số attempt của cả hai lớp.

## 3. Retry là gì và khi nào có ích?

Retry là thực hiện lại một thao tác sau khi lần thử trước thất bại hoặc kết quả chưa xác định. Retry phù hợp khi lỗi có khả năng tạm thời và lần thử lại có cơ hội thành công mà không tạo tác dụng phụ sai.

Những tình huống có thể cân nhắc retry:

- Kết nối bị reset hoặc lỗi mạng tạm thời.
- Timeout khi chưa rõ request đã được dịch vụ xử lý hay chưa, nếu thao tác idempotent hoặc có cách xác minh trạng thái.
- HTTP 408, 429 hoặc một số lỗi 5xx theo semantics dịch vụ.
- Throttling có chỉ dẫn chờ lại như **Retry-After**.
- Broker/service tạm thời unavailable hoặc lỗi chuyển tiếp trong transport.
- Database deadlock/serialization conflict nếu transaction có thể chạy lại an toàn.

Những tình huống thường **không nên retry mù quáng**:

- Dữ liệu đầu vào không hợp lệ, validation thất bại.
- 401/403 do sai credential, thiếu role hoặc quyền không hợp lệ.
- Sai endpoint, tenant, tên resource hoặc cấu hình.
- 404 khi tài nguyên không tồn tại và nghiệp vụ không có quy tắc eventual consistency cụ thể.
- Conflict nghiệp vụ như đơn hàng đã bị hủy hoặc trạng thái không cho phép chuyển tiếp.
- Lỗi schema/code deterministic, lỗi mapping hoặc serialization không thể tự phục hồi.
- Request quá lớn hoặc vượt giới hạn cố định của dịch vụ.

Mã HTTP chỉ là một tín hiệu. Ví dụ **404** đôi khi có thể tạm thời trong một workflow vừa tạo resource, nhưng trong phần lớn thao tác đọc Blob sai tên thì retry không giúp. **409** có thể là conflict nghiệp vụ, lease conflict hoặc một trạng thái dịch vụ có cách xử lý riêng. Phải đọc error code và semantics của operation.

## 4. Phân công retry theo lớp

### 4.1. Để SDK xử lý lỗi giao thức và lỗi dịch vụ tạm thời

SDK thường biết:

- Request có thể retry theo protocol/service contract không.
- Dịch vụ có trả Retry-After hoặc thông tin backoff không.
- Lỗi transport nào có thể khôi phục.
- Request đã được gửi tới endpoint nào và có thể gửi lại thế nào.
- Một API cụ thể có điều kiện retry riêng hay không.

Ví dụ:

| SDK/client | Retry phù hợp ở lớp SDK |
| --- | --- |
| Azure Blob Storage SDK | Lỗi HTTP/transport tạm thời theo Storage retry policy, throttling và lỗi dịch vụ được SDK nhận diện |
| Azure Service Bus SDK | Lỗi kết nối, lỗi AMQP tạm thời, retry operation theo messaging client policy |
| Azure Cosmos DB SDK | Throttling 429, retry theo service response và request semantics |
| AWS SDK for Java v2 | Lỗi transient/throttling theo retry strategy của AWS client |
| Google Cloud Java client | Retry theo RPC/API retry settings và mã lỗi được thư viện định nghĩa |
| JDBC driver | Một số lỗi kết nối hoặc protocol, tùy driver; không mặc định retry toàn transaction nghiệp vụ |

Không nên viết thêm một vòng lặp Spring chỉ để retry lại từng lỗi mạng mà SDK đã xử lý tốt. Nếu SDK đã retry trong một lần gọi API, hãy coi toàn bộ quá trình đó là **một attempt ở cấp application boundary**.

### 4.2. Để Spring resilience bảo vệ ranh giới dependency

Lớp Spring/resilience phù hợp để:

- Đặt **circuit breaker** khi dependency lỗi kéo dài.
- Giới hạn concurrency bằng **bulkhead**.
- Rate limit hoặc giới hạn số request theo client.
- Retry một số lỗi transient sau khi SDK đã kết thúc lần gọi và trả lỗi.
- Ghi metrics/trace thống nhất cho mỗi dependency.
- Chọn fallback có ý nghĩa ở cấp ứng dụng, ví dụ trả dữ liệu cache hoặc từ chối sớm.

Retry ở lớp này nên được dùng khi có một **lý do rõ ràng vượt ra ngoài retry transport**. Nếu SDK đã thực hiện nhiều lần retry nội bộ, Spring Retry thêm nhiều attempt có thể nhân số request và vượt deadline.

### 4.3. Để mã nghiệp vụ quyết định retry workflow

Mã nghiệp vụ cần retry khi quyết định phụ thuộc trạng thái nghiệp vụ hoặc nhiều bước phân tán, ví dụ:

- Một workflow chờ tài nguyên vừa được provision và cần kiểm tra trạng thái trước khi tiếp tục.
- Consumer nhận message nhưng một dịch vụ nghiệp vụ đang ở trạng thái tạm thời chưa sẵn sàng.
- Một bước cần chạy lại sau khi xác minh thao tác trước chưa hoàn tất.
- Một saga cần retry một command hoặc chạy compensation theo trạng thái đã lưu.

Business retry không nên là vòng lặp lặp lại cùng HTTP request mà không biết điều gì đã xảy ra. Nó phải kiểm tra **state**, **idempotency key**, **attempt count**, **next retry time**, **deadline** và điều kiện dừng.

## 5. Retry lồng nhau có thể nhân số lần gọi

Giả sử:

- SDK thực hiện tối đa 4 lần thử cho một lần gọi client.
- Spring Retry gọi phương thức tối đa 3 lần.
- Workflow nghiệp vụ chạy lại toàn bộ bước tối đa 2 lần.

Số lần request xuống dịch vụ có thể lên tới:

~~~text
4 × 3 × 2 = 24 lần thử ở tầng SDK/transport
~~~

Con số thực tế phụ thuộc cách từng thư viện định nghĩa **max attempts/max retries** và lỗi xảy ra ở giai đoạn nào. Một số cấu hình tính cả lần đầu; một số API gọi riêng số lần retry sau lần đầu. Phải xác nhận semantics trước khi tính.

### Bảng tác động của retry lồng nhau

| SDK attempts | Spring attempts | Business attempts | Tổng request tối đa theo mô hình nhân |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 1 |
| 3 | 1 | 1 | 3 |
| 3 | 2 | 1 | 6 |
| 3 | 3 | 1 | 9 |
| 4 | 3 | 2 | 24 |
| 5 | 4 | 3 | 60 |

Đây là mô hình bảo thủ để nhận diện **retry amplification**, giả định mỗi lần gọi ở lớp ngoài đều kích hoạt đủ số lần thử ở lớp trong. Một số lỗi có thể dừng sớm hoặc không đi qua toàn bộ transport, nhưng không nên dựa vào điều đó để thiết kế giới hạn tải.

### Quy tắc thực tế

- Chọn một **retry owner** chính cho mỗi nhóm lỗi.
- Giữ SDK retry cho lỗi transport/service transient mà SDK hiểu.
- Dùng Spring Retry chỉ khi cần retry ở ranh giới dependency và đã tính cả retry nội bộ của SDK.
- Dùng business retry cho workflow có state, lịch chạy lại và idempotency.
- Công khai attempt count và tổng thời gian trong metrics.
- Không để mỗi tầng tự đặt max attempts mà không có ngân sách tổng.

## 6. Phân loại lỗi trước khi retry

Một adapter nên chuyển lỗi cụ thể của SDK/provider thành nhóm lỗi nội bộ có ý nghĩa, ví dụ:

| Nhóm lỗi nội bộ | Ví dụ nguồn | Retry mặc định? | Hướng xử lý |
| --- | --- | --- | --- |
| **Transient transport** | Connection reset, temporary DNS/network failure | Có thể | Để SDK hoặc một lớp được chọn retry có giới hạn |
| **Throttled** | HTTP 429, service throttling | Có thể | Tôn trọng Retry-After/backoff, giảm concurrency |
| **Transient service** | Một số 5xx/service unavailable | Có thể | Retry có ngân sách và idempotency |
| **Authentication** | 401, token invalid/expired theo trường hợp | Thường không ở Spring layer | Làm mới credential theo SDK nếu hỗ trợ; nếu vẫn lỗi thì sửa identity |
| **Authorization** | 403, RBAC/access policy | Không | Sửa principal, role, scope hoặc network policy |
| **Not found/configuration** | 404 sai resource, sai endpoint | Không mặc định | Xác minh resource name, deployment order và eventual consistency |
| **Conflict** | 409, ETag/lease/state conflict | Tùy operation | Đọc mã lỗi và giải quyết conflict |
| **Validation/business rejection** | Dữ liệu không hợp lệ, trạng thái không cho phép | Không | Trả lỗi nghiệp vụ |
| **Unknown outcome** | Timeout sau khi request có thể đã được xử lý | Chỉ khi an toàn | Tra trạng thái hoặc dùng idempotency/deduplication |

**Không retry mọi RuntimeException.** Một exception không xác định có thể là lỗi lập trình, cấu hình hoặc dữ liệu. Retry broad exception làm che lỗi thật và kéo dài thời gian xử lý.

### Ví dụ phân loại Blob Storage

| Tình huống | Phân loại | Hành động |
| --- | --- | --- |
| Tạm thời mất kết nối trước khi gửi request | Transient transport | SDK có thể retry |
| Blob service trả 503 | Transient service | Dùng retry policy SDK có giới hạn |
| Storage throttling 429 | Throttled | Backoff, tôn trọng tín hiệu dịch vụ |
| Managed identity thiếu role ghi | Authorization | Không retry; cấp đúng role qua quy trình IAM |
| Sai container name | Configuration/not found | Sửa cấu hình hoặc provision container |
| Blob đã tồn tại với overwrite=false | Conflict | Xử lý nghiệp vụ hoặc dùng tên/idempotency phù hợp |
| Timeout khi commit upload | Unknown outcome | Kiểm tra trạng thái blob trước khi lặp nếu cần |

## 7. Retry ở Azure SDK và Spring Cloud Azure

Spring Cloud Azure starter có thể tự cấu hình client Azure SDK trong Spring context. Retry policy thực tế phụ thuộc **SDK dịch vụ**, **Azure Core**, **phiên bản starter** và các thuộc tính được hỗ trợ ở phiên bản đó.

### 7.1. Azure SDK là nơi hiểu service-level retry

Ví dụ Blob Storage SDK có retry options riêng; Service Bus có retry options của AMQP client; Cosmos DB có retry behavior cho throttling và request. Không giả định một property Spring chung điều khiển retry cho tất cả các dịch vụ.

Với Blob Storage, có thể cấu hình retry qua builder/service SDK khi phiên bản hỗ trợ. Hãy kiểm tra:

- Max retries/attempts có tính lần đầu hay không.
- Khoảng retry mặc định và tối đa.
- Exponential backoff hoặc fixed delay.
- Retry cho status/error nào.
- Timeout của mỗi attempt và timeout toàn operation.
- Secondary endpoint/failover có được dùng hay không.
- Retry có áp dụng cho upload nhiều block, download stream và operation cụ thể không.

**Không ghi cứng một bộ giá trị retry dùng chung cho mọi môi trường.** Môi trường dev, integration test và production có latency, throughput và SLO khác nhau.

### 7.2. Không để Spring retry lại toàn bộ SDK một cách vô thức

Ví dụ một method upload đã dùng Blob SDK có internal retry. Nếu bọc method bằng Spring Retry mà không phân loại exception, mỗi lần SDK cuối cùng thất bại có thể kích hoạt một vòng SDK retry mới. Điều này có thể làm một request nghiệp vụ tạo nhiều lần upload request hơn dự kiến.

Một số thao tác upload có thể idempotent nếu dùng blob name xác định và semantics ghi phù hợp, nhưng không nên mặc định mọi upload là idempotent. Cần xét overwrite, conditional headers/ETag, block commit và kết quả không xác định sau timeout.

### 7.3. Spring Cloud Azure không phải một retry policy thống nhất cho mọi service

Starter giúp wiring client vào Spring. Retry vẫn có thể nằm trong Azure SDK service client, hoặc được bổ sung ở lớp resilience ứng dụng. Trước khi đặt retry trong application.yml, phải xác minh property đó thuộc đúng starter/service và được version hiện tại hỗ trợ.

## 8. Retry ở thư viện Spring: Spring Retry và Resilience4j

Có hai hướng phổ biến trong ứng dụng Spring:

- **Spring Retry:** cung cấp cơ chế retry khai báo/chương trình, thường dùng annotation như **@Retryable** và cơ chế phục hồi tương ứng.
- **Resilience4j:** cung cấp Retry, CircuitBreaker, Bulkhead, RateLimiter và TimeLimiter; có tích hợp Spring Boot/annotations.

Không cần thêm cả hai thư viện chỉ vì có nhiều dependency. Chọn một cơ chế chính theo kiến trúc, version Spring Boot và nhu cầu vận hành.

### 8.1. Ví dụ Spring Retry với lỗi nội bộ đã phân loại

Một adapter có thể chuyển lỗi SDK sang exception nội bộ **TransientDependencyException** sau khi đã xác định đó là lỗi tạm thời. Spring Retry chỉ bắt nhóm exception này:

~~~java
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class PartnerDocumentService {

    private final DocumentGateway gateway;

    public PartnerDocumentService(DocumentGateway gateway) {
        this.gateway = gateway;
    }

    @Retryable(
        retryFor = TransientDependencyException.class,
        maxAttempts = 3,
        backoff = @Backoff(
            delay = 200,
            multiplier = 2.0,
            maxDelay = 1000
        )
    )
    public DocumentReference upload(DocumentCommand command) {
        return gateway.upload(command);
    }
}
~~~

Ở ví dụ này, **maxAttempts=3** tính cả lần gọi đầu theo semantics của Spring Retry. Phải xác nhận API annotation phù hợp với version Spring Retry được quản lý trong dự án; một số bản cũ dùng tên thuộc tính khác.

**Không bọc mọi exception của Azure SDK vào TransientDependencyException.** Adapter chỉ chuyển các lỗi thật sự có thể retry; 401/403, validation, sai endpoint hoặc conflict nghiệp vụ phải giữ loại lỗi riêng.

### 8.2. Lưu ý proxy/AOP của Spring Retry

Các annotation retry thường dựa trên Spring AOP/proxy. Nếu một method trong cùng class tự gọi một method khác có annotation retry, lời gọi nội bộ có thể không đi qua proxy và annotation không được áp dụng như mong đợi.

Nên đặt ranh giới retry ở một bean riêng, được gọi qua Spring proxy, và kiểm thử số lần thực thi thực tế. Không giả định thấy annotation trong code là đã có retry ở runtime.

### 8.3. Ví dụ Resilience4j

Resilience4j có thể cấu hình số attempt và backoff:

~~~yaml
resilience4j:
  retry:
    instances:
      partnerRead:
        max-attempts: 3
        wait-duration: 200ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        retry-exceptions:
          - com.example.TransientDependencyException
        ignore-exceptions:
          - com.example.AuthorizationFailure
          - com.example.InvalidRequest
~~~

Một service có thể dùng annotation:

~~~java
import io.github.resilience4j.retry.annotation.Retry;
import org.springframework.stereotype.Service;

@Service
public class PartnerReadService {

    private final PartnerGateway gateway;

    public PartnerReadService(PartnerGateway gateway) {
        this.gateway = gateway;
    }

    @Retry(name = "partnerRead")
    public PartnerResult read(String id) {
        return gateway.read(id);
    }
}
~~~

Để chạy, dự án cần dependency tích hợp Resilience4j với Spring Boot và cấu hình AOP tương ứng. Cấu hình minh họa phải được xác minh theo phiên bản starter; tên property, exception predicate và annotation integration có thể khác theo release.

**Retry ở Spring không thay thế retry SDK.** Nếu PartnerGateway gọi một Azure SDK client đã retry nội bộ, hãy tính tổng attempt và chỉ retry exception đã được phân loại sau khi SDK hết khả năng xử lý.

## 9. Phân công Retry, Circuit Breaker và Bulkhead

Retry không phải công cụ duy nhất để xử lý dependency lỗi.

| Cơ chế | Mục đích | Khi nào phù hợp | Không giải quyết được |
| --- | --- | --- | --- |
| **Retry** | Thử lại lỗi tạm thời | Lỗi transient, operation an toàn khi lặp | Lỗi cấu hình/quyền, outage kéo dài |
| **Circuit breaker** | Tạm ngừng gọi dependency đang lỗi | Tỷ lệ lỗi cao hoặc latency kéo dài | Không sửa dependency và không bảo đảm request thành công |
| **Bulkhead** | Giới hạn tài nguyên/concurrency dành cho dependency | Ngăn một dependency chiếm hết thread/connection | Không tự retry hoặc khôi phục dữ liệu |
| **Rate limiter** | Giới hạn tốc độ gọi | Bảo vệ quota/throttling | Không tự làm request đã bị từ chối thành công |
| **Time limiter/deadline** | Giới hạn thời gian chờ | Bảo vệ SLO và ngân sách request | Không luôn hủy được remote side effect |
| **Fallback** | Cung cấp kết quả thay thế hoặc degrade | Cache/stale data, tính năng không cốt lõi | Không nên che lỗi dữ liệu bắt buộc |

### Thứ tự thường gặp

Một cấu trúc phổ biến là:

~~~text
Business service
    → Circuit breaker / bulkhead boundary
        → Retry boundary (nếu được chọn)
            → SDK client với retry protocol có giới hạn
                → Managed service
~~~

Thứ tự thực tế của decorator ảnh hưởng hành vi:

- Nếu **CircuitBreaker bao quanh Retry**, breaker có thể ghi nhận một lần gọi nghiệp vụ cuối cùng sau khi retry hoàn tất.
- Nếu **Retry bao quanh CircuitBreaker**, mỗi attempt có thể được breaker ghi nhận riêng; breaker có thể mở giữa vòng retry.
- Nếu Bulkhead nằm ngoài Retry, toàn bộ vòng retry có thể giữ một slot; nếu nằm trong, mỗi attempt có thể lấy slot riêng.

Không có thứ tự tốt cho mọi trường hợp. Chọn theo cách muốn đo lỗi, giới hạn concurrency và bảo vệ dependency. Kiểm tra event/metrics để xác nhận decorator order.

## 10. Retry phải tuân theo deadline và retry budget

Retry thêm latency. Nếu request có deadline 2,5 giây nhưng retry policy chờ tổng cộng 3 giây, hệ thống chỉ kéo dài tác vụ vô ích và có thể hoàn thành sau khi caller đã bỏ cuộc.

Một retry plan phải xét:

- Thời gian đã tiêu thụ.
- Thời gian còn lại của operation.
- Timeout tối đa cho attempt tiếp theo.
- Backoff trước attempt.
- Khoảng dự phòng để trả response/cleanup.
- Thời gian token acquisition và connection-pool wait nếu nằm trong lần gọi.
- Retry budget tổng thể của service.

### Công thức kiểm tra

~~~text
T_remaining >= T_backoff + T_next_attempt + T_cleanup_reserve
~~~

Nếu không đủ ngân sách, không bắt đầu attempt mới. Dừng retry và trả lỗi/đẩy công việc sang hàng đợi theo thiết kế.

### Ví dụ

Deadline còn 700 ms. SDK đã tiêu thụ 500 ms và trả lỗi 503. Spring Retry định chờ 400 ms trước attempt tiếp theo. Khi cộng timeout attempt và thời gian trả response, chắc chắn vượt deadline; không nên retry.

**Retry budget** có thể được giới hạn theo số attempt, thời gian hoặc tỷ lệ retry trên tổng request. Với hệ thống nhiều replica, budget theo instance cần được đánh giá vì tổng retry trên toàn fleet có thể cao hơn nhiều.

## 11. Backoff, jitter và Retry-After

Retry ngay lập tức có thể làm nhiều client cùng dồn request vào dịch vụ vừa phục hồi. **Exponential backoff** tăng dần khoảng nghỉ giữa các lần thử; **jitter** thêm độ ngẫu nhiên để giảm đồng bộ.

Một công thức tham khảo:

~~~text
delay(k) = min(maxDelay, initialDelay × multiplier^(k - 1))
actualDelay = delay(k) + randomJitter
~~~

Ví dụ initial delay 100 ms, multiplier 2, max delay 1.000 ms:

| Lần chờ | Backoff cơ sở |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 trở đi | Tối đa 1.000 ms |

Các giá trị chỉ minh họa. Không cộng jitter vượt giới hạn deadline hoặc chính sách dịch vụ.

### Retry-After

Một số dịch vụ trả **Retry-After** hoặc thông tin tương đương để gợi ý thời gian chờ. Khi SDK đã xử lý header đó, không nên thêm một lớp Spring Retry lại với backoff ngắn hơn khiến ứng dụng gọi sớm hơn chỉ dẫn dịch vụ.

Nếu application layer tự chịu trách nhiệm retry, cần đọc và áp dụng tín hiệu của dịch vụ theo API/exception thực tế. Nếu giá trị chờ vượt deadline, trả lỗi hoặc lên lịch xử lý sau; không ép retry ngay.

## 12. Idempotency quyết định retry có an toàn không

Một thao tác **idempotent** có cùng kết quả quan sát được khi thực hiện nhiều lần với cùng đầu vào/định danh theo hợp đồng nghiệp vụ. Retry chỉ an toàn khi tác dụng phụ được kiểm soát.

| Thao tác | Rủi ro khi retry | Cách giảm rủi ro |
| --- | --- | --- |
| Đọc Blob | Thường không có side effect dữ liệu, nhưng có thể phát sinh chi phí | Retry có giới hạn, không vượt deadline |
| Upload Blob với tên ngẫu nhiên mỗi lần | Có thể tạo nhiều object | Dùng tên xác định/idempotency key và cleanup |
| Upload cùng Blob name với overwrite=true | Có thể ghi đè nội dung đã thay đổi | ETag/conditional write, versioning hoặc kiểm tra trạng thái |
| Gửi Service Bus message | Broker có thể đã nhận message nhưng ACK bị mất | Message ID ổn định, duplicate detection nếu phù hợp, consumer idempotency |
| Tạo đơn hàng trong database | Có thể tạo hai order | Unique business key/idempotency record |
| Trừ tiền hoặc gọi payment provider | Có thể thu tiền nhiều lần | Idempotency key theo hợp đồng của provider và đối soát trạng thái |
| Gửi email/notification | Có thể gửi trùng | Outbox, deduplication hoặc nghiệp vụ chấp nhận duplicate |

### Timeout tạo ra unknown outcome

Khi client nhận timeout, không thể luôn biết server chưa xử lý hay đã xử lý nhưng response bị mất. Với thao tác ghi:

1. Tra trạng thái theo resource ID hoặc idempotency key nếu có.
2. Nếu thao tác đã hoàn thành, trả lại kết quả cũ.
3. Nếu chưa xảy ra và có thể thử lại, chạy lại với cùng key.
4. Nếu trạng thái không xác định, đưa vào quy trình reconciliation thay vì retry mù.

## 13. Business retry: workflow có trạng thái và lịch chạy lại

Có những tình huống không thể giải quyết bằng retry ngay tại SDK. Ví dụ đơn hàng cần đợi một tài nguyên downstream được provision, hoặc một hệ thống đối tác chỉ cho phép thử lại sau vài phút.

Business retry nên lưu được:

- **Operation ID / idempotency key**.
- Trạng thái workflow hiện tại.
- Số lần đã thử và lỗi gần nhất.
- **Next retry time**.
- Deadline hoặc thời điểm hết hạn nghiệp vụ.
- Chính sách dừng, chuyển DLQ hoặc yêu cầu can thiệp.
- Kết quả của các bước đã hoàn thành để không chạy lại sai.

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Running: bắt đầu xử lý
    Running --> Succeeded: bước hoàn tất
    Running --> RetryScheduled: lỗi tạm thời
    RetryScheduled --> Running: đến next retry time
    Running --> Failed: lỗi không thể retry
    RetryScheduled --> Expired: hết deadline / retry budget
    Failed --> [*]
    Succeeded --> [*]
    Expired --> [*]
~~~

Không dùng một vòng while/sleep trong HTTP request để chờ nhiều phút. Lưu trạng thái và đưa công việc vào scheduler/queue để xử lý bất đồng bộ. Client nhận **202 Accepted** hoặc operation reference nếu nghiệp vụ phù hợp.

### Khi nào retry nên chuyển thành compensation?

Nếu một workflow đã hoàn tất một số bước nhưng bước sau thất bại vĩnh viễn, có thể cần **compensation** thay vì thử lại toàn bộ:

- Blob đã upload nhưng không tạo được record nghiệp vụ: xóa object hoặc đánh dấu orphan theo chính sách.
- Đã ghi database nhưng gửi message thất bại: outbox worker tiếp tục publish.
- Đã giữ chỗ inventory nhưng thanh toán bị từ chối: giải phóng reservation.

Business retry phải biết trạng thái và thứ tự các bước; SDK không có đủ ngữ cảnh để quyết định compensation.

## 14. Transactional outbox và retry trong messaging

Một lỗi thường gặp:

~~~text
1. Commit order vào database
2. Gửi OrderCreated lên Service Bus
3. Service Bus tạm thời lỗi
4. API retry gửi message hoặc trả lỗi
~~~

Nếu database đã commit nhưng message chưa gửi, trạng thái hệ thống có thể không nhất quán. Nếu message đã gửi nhưng response bị mất, retry có thể tạo message trùng.

**Transactional outbox** giải quyết phần ghi dữ liệu và tạo sự kiện bằng một transaction database:

~~~mermaid
flowchart TD
    A[Order API] --> B[Database transaction]
    B --> C[Orders table]
    B --> D[Outbox table]
    D --> E[Outbox publisher]
    E --> F[Service Bus / SQS / Pub/Sub]
    F --> G[Consumer]
    G --> H[Idempotent business handler]
~~~

1. Trong một transaction, ghi order và một outbox record.
2. Publisher đọc các outbox record chưa gửi.
3. Publisher gửi message bằng một **message ID ổn định**.
4. Khi nhận acknowledgment phù hợp, đánh dấu outbox record đã gửi.
5. Nếu publisher timeout/không rõ kết quả, có thể gửi lại; consumer phải idempotent hoặc broker hỗ trợ deduplication theo cấu hình.
6. Consumer lưu inbox/processed message ID cùng thay đổi nghiệp vụ để tránh xử lý lặp.

Outbox không tự đảm bảo exactly-once end-to-end. Nó giúp bảo đảm sự kiện không bị mất giữa transaction database và bước publish; duplicate vẫn có thể xảy ra và phải được xử lý.

## 15. Retry của broker khác retry của SDK và Spring

Đối với messaging, có ít nhất ba cơ chế có thể cùng hoạt động:

| Cơ chế | Thời điểm | Trách nhiệm |
| --- | --- | --- |
| **SDK retry** | Trong lần send/receive/settlement | Khôi phục lỗi transport hoặc service tạm thời theo client policy |
| **Application retry** | Khi handler xử lý message thất bại | Quyết định xử lý lại, abandon/nack hoặc ghi trạng thái retry |
| **Broker redelivery** | Message chưa được complete/ack hoặc lock/visibility hết | Giao lại message theo delivery semantics |

Không nên vừa retry trong handler, vừa abandon message ngay, vừa tự gửi một bản sao vào queue retry mà không có quy tắc. Điều đó có thể tạo nhiều bản message cùng xử lý.

### Azure Service Bus

- SDK có thể retry một số lỗi giao tiếp với namespace.
- Khi handler nhận message và xử lý thất bại, ứng dụng có thể **abandon**, dead-letter hoặc xử lý theo chế độ settlement.
- Nếu lock hết hạn, broker có thể giao message lại.
- Cần kiểm soát **MaxDeliveryCount**, dead-letter queue, lock renewal và idempotency của consumer.
- Không coi SDK retry cho kết nối là cùng cơ chế với broker redelivery.

### AWS SQS

- SDK retry request tới SQS theo retry strategy.
- Visibility timeout quyết định thời gian message bị ẩn sau khi receive.
- Nếu không delete trước khi visibility hết, message có thể được giao lại.
- DLQ/redrive policy xử lý message vượt số lần receive được cấu hình.
- Consumer nên idempotent vì duplicate delivery có thể xảy ra.

### Google Cloud Pub/Sub

- Client có retry cho các RPC.
- Subscription ack deadline và lease extension ảnh hưởng thời gian message được giữ bởi subscriber.
- Nack hoặc không ack có thể dẫn tới redelivery theo subscription configuration.
- Dead-letter topic và delivery attempt cần được xem cùng application handler.
- Không đồng nhất ack deadline với timeout của một RPC publish/subscribe.

## 16. Ví dụ end-to-end: Blob upload và Service Bus publish

**Bối cảnh:** Documents API nhận file, upload Blob rồi phát DocumentUploaded event.

Một cách thiết kế thiếu kiểm soát:

~~~text
Controller
  → @Retryable uploadAndPublish()
      → Blob SDK tự retry
      → Service Bus SDK tự retry
      → nếu bất kỳ bước nào lỗi, chạy lại cả phương thức
~~~

Nếu Blob upload thành công nhưng Service Bus publish thất bại, Spring Retry gọi lại toàn bộ method và upload Blob lần nữa. Nếu tên Blob ngẫu nhiên, có thể tạo object trùng; nếu overwrite, có thể ghi đè dữ liệu.

### Cách phân công tốt hơn

1. **Blob SDK:** xử lý retry transport/throttling cho từng request upload theo policy đã kiểm tra.
2. **Blob adapter:** ánh xạ lỗi sang transient/permanent/unknown outcome; dùng blob name ổn định và điều kiện ghi phù hợp.
3. **Application service:** không tự retry toàn bộ workflow nếu bước Blob đã hoàn thành; ghi trạng thái/outbox hoặc kiểm tra lại kết quả.
4. **Service Bus SDK:** xử lý retry transport khi publish theo policy của client.
5. **Outbox publisher:** quản lý lịch retry business-level cho message chưa publish, dùng message ID ổn định.
6. **Consumer:** idempotent theo message ID và trạng thái nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant A as Documents API
    participant B as Blob SDK
    participant DB as Database / Outbox
    participant P as Outbox publisher
    participant S as Service Bus
    A->>B: Upload blob với key ổn định
    B-->>A: Blob reference
    A->>DB: Commit document + outbox event
    DB-->>A: Commit thành công
    A-->>A: Trả kết quả nghiệp vụ
    P->>DB: Đọc outbox pending
    P->>S: Publish event, message ID ổn định
    S-->>P: ACK hoặc kết quả không xác định
    P->>DB: Đánh dấu sent khi xác nhận phù hợp
~~~

Nếu outbox publisher mất ACK, nó có thể publish lại; consumer phải chống xử lý trùng. Cách này tách retry publish khỏi request upload của người dùng và không buộc toàn bộ workflow chạy lại.

## 17. Quan sát retry và phát hiện retry amplification

Cần đo retry ở từng lớp thay vì chỉ đo số request thành công/thất bại.

| Metric | Cần biết |
| --- | --- |
| **sdk_attempts_total** | Số attempt ở SDK/transport theo dịch vụ |
| **application_retry_attempts_total** | Số lần Spring resilience gọi lại adapter |
| **business_retry_scheduled_total** | Số workflow được lên lịch chạy lại |
| **broker_delivery_attempt** | Số lần broker giao message, nếu dịch vụ cung cấp |
| **retry_delay_seconds** | Thời gian backoff thực tế |
| **retry_exhausted_total** | Số thao tác hết retry budget |
| **deadline_exceeded_total** | Số thao tác không còn đủ thời gian để retry |
| **circuit_breaker_state** | Trạng thái closed/open/half-open |
| **duplicate_detected_total** | Số message/resource trùng được phát hiện |
| **operation_duration** | Thời gian tổng bao gồm cả retry |

Nên gắn metric theo dependency, operation và nhóm lỗi. Không dùng user ID, blob name hoặc request ID làm label có cardinality cao. Request/correlation ID có thể ghi vào trace/log theo chính sách.

### Dấu hiệu retry storm

- Throughput request tăng nhưng tỷ lệ thành công không tăng.
- Latency p95/p99 tăng nhanh sau mỗi đợt lỗi.
- Số attempt trung bình trên một request tăng.
- Dependency bị throttling nhiều hơn sau khi client retry.
- Thread pool/connection pool bị giữ lâu trong backoff.
- Broker delivery count và DLQ tăng.
- Nhiều instance cùng retry theo chu kỳ giống nhau.

Khi có dấu hiệu này, cân nhắc giảm retry, thêm jitter, mở circuit breaker, giảm concurrency, áp rate limit hoặc chuyển công việc sang queue thay vì tiếp tục retry đồng bộ.

## 18. Kiểm thử retry có chủ đích

### 18.1. Unit test cho classifier

Viết test cho adapter/error classifier:

- 429/503 theo service policy được đánh dấu transient.
- 401/403 được đánh dấu permanent authorization/configuration.
- 404 và 409 được phân loại theo operation/error code.
- Unknown exception không tự động trở thành retryable.
- Retry-After được chuyển thành delay phù hợp khi application layer chịu trách nhiệm.

### 18.2. Kiểm tra số lần gọi thật

Dùng mock/fake gateway hoặc HTTP test server để xác minh:

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Lần đầu 503, lần sau thành công | Số attempt đúng với policy |
| 403 ngay lần đầu | Không có retry vô ích |
| 429 có Retry-After | Delay tuân thủ chính sách đã chọn |
| SDK retry hết rồi Spring retry | Tổng outbound request không vượt giới hạn dự kiến |
| Hết deadline trước attempt tiếp theo | Không gửi request mới |
| Timeout sau side effect | Trạng thái được kiểm tra hoặc idempotency ngăn trùng |
| Circuit breaker open | Request bị từ chối sớm, không gọi dependency |
| Message redelivery | Consumer không tạo side effect nghiệp vụ trùng |

### 18.3. Integration test với Azure dev/test

- Dùng Blob Storage/Service Bus resource test và identity riêng.
- Gây lỗi có kiểm soát bằng test proxy, cấu hình test hoặc service fault injection phù hợp.
- Đọc SDK diagnostics và application metrics để đếm attempt.
- Xác minh quyền RBAC riêng; 403 không được retry như transient.
- Kiểm tra upload và message publish sau timeout để biết trạng thái thực tế.
- Cleanup tài nguyên và dữ liệu thử nghiệm.

Azurite có thể giúp kiểm tra một phần Storage API nhưng không mô phỏng đầy đủ Azure throttling, Entra, RBAC hoặc Service Bus. Với messaging, cần test trên broker thực hoặc môi trường tương đương được hỗ trợ.

### 18.4. Test annotation/proxy

Với Spring Retry/Resilience4j:

- Gọi bean qua Spring proxy.
- Không chỉ test method nội bộ trong cùng class.
- Xác minh attempt count và backoff.
- Kiểm tra exception predicate/ignore list.
- Kiểm tra decorator order của Retry, CircuitBreaker và Bulkhead.
- Xác minh không retry lỗi validation, authentication hoặc authorization.

## 19. So sánh retry giữa AWS, Azure và Google Cloud

| Lớp | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| SDK/client | Retry options theo Storage, Service Bus, Cosmos và từng SDK | Retry strategy của AWS SDK client/service | Retry settings theo client/RPC/API |
| Spring resilience | Spring Retry, Resilience4j, Spring Cloud CircuitBreaker | Tương tự | Tương tự |
| Business workflow | State machine, scheduler, outbox, message retry | State machine, EventBridge/SQS workflow, outbox | Workflow/task queue, Pub/Sub retry, outbox |
| Messaging redelivery | Service Bus lock/abandon/DLQ, Event Hubs checkpoint | SQS visibility/DLQ, Kinesis checkpoint | Pub/Sub ack deadline/dead-letter, subscriber retry |
| Retry signal | HTTP Retry-After và service-specific behavior | Service response/retry headers và SDK behavior | RPC status, retry policy và service guidance |

Các SDK của provider khác nhau về số attempt, error classification, default backoff và semantics. Khi chuyển provider, không bê nguyên con số retry từ Azure sang AWS/GCP. Hãy đánh giá lại:

- Request idempotency và duplicate behavior.
- Throttling/quota và Retry-After hoặc RPC retry signal.
- Broker delivery/ack/visibility/lock semantics.
- Deadline và tổng retry budget.
- Observability và cách xác minh attempt count.

## 20. Bài thực hành: phân công retry cho Documents API

**Bối cảnh:** Spring Boot Documents API upload tệp lên Blob Storage, lưu metadata vào database và phát DocumentUploaded event vào Service Bus.

### Phần A — Phân loại lỗi

Lập bảng lỗi cho từng dependency:

1. Blob: 429, 503, 403, 404, timeout khi commit upload.
2. Database: deadlock, connection reset, constraint violation, query timeout.
3. Service Bus: network failure, throttling, 401/403, timeout sau khi publish.
4. Outbox publisher: mất ACK, worker restart, hết retry budget.

Với mỗi lỗi, xác định **retryable**, **permanent**, **unknown outcome** hoặc **business conflict**.

### Phần B — Chọn retry owner

- Để SDK xử lý lỗi protocol/service transient trong giới hạn đã cấu hình.
- Chỉ dùng Resilience4j/Spring Retry ở gateway nếu có nhu cầu bảo vệ dependency và đã tính số attempt nội bộ.
- Dùng outbox publisher cho retry publish message sau khi database commit.
- Consumer dùng idempotency key/message ID để chống xử lý trùng.
- Không retry 401/403 hoặc lỗi validation.

### Phần C — Tính tổng attempt và deadline

1. Ghi rõ SDK max retries/attempts theo version thực tế.
2. Ghi Spring maxAttempts và xác định có tính lần đầu hay không.
3. Tính upper bound request khi các tầng lồng nhau.
4. Đặt deadline 2,5 giây cho API đồng bộ; không bắt đầu attempt mới nếu không còn ngân sách.
5. Đưa publish chưa hoàn thành sang outbox worker thay vì giữ HTTP request mở quá lâu.

### Phần D — Kiểm thử

1. Làm Blob trả 503 một lần rồi thành công; xác minh SDK retry và số request.
2. Làm Blob trả 403; xác minh không retry.
3. Làm Service Bus publish timeout sau khi broker có thể đã nhận; kiểm tra duplicate behavior.
4. Khởi động lại outbox worker giữa các lần gửi; xác minh message ID ổn định.
5. Gửi lại cùng event tới consumer; xác minh business state chỉ được cập nhật một lần.
6. Làm circuit breaker open; xác minh ứng dụng từ chối sớm.
7. Đo tổng latency, số attempt, retry delay và deadline exhaustion.

**Sản phẩm cần nộp:** sơ đồ retry ownership, bảng error classifier, cấu hình SDK/Spring, phép tính upper bound attempts, kết quả idempotency test và dashboard metrics.

### Câu hỏi tự kiểm tra

1. Vì sao SDK retry và Spring Retry cùng bật có thể nhân số request?
2. Khi nào nên để Azure SDK tự retry thay vì thêm @Retryable?
3. Vì sao 403 do thiếu RBAC không nên retry?
4. Spring Retry và Resilience4j có vai trò gì khác circuit breaker?
5. Nếu retry bao quanh circuit breaker, mỗi attempt được tính vào breaker như thế nào?
6. Vì sao business retry cần lưu trạng thái và next retry time?
7. Khi Service Bus broker đã nhận message nhưng client mất ACK, retry có thể gây điều gì?
8. Outbox giải quyết khoảng trống nào giữa database commit và publish message?
9. Vì sao message redelivery không phải cùng một cơ chế với SDK retry?
10. Làm thế nào xác minh upper bound attempts trong integration test?

## 21. Ghi nhớ

- **SDK** nên xử lý lỗi transport/protocol/service transient mà nó hiểu; **Spring resilience** bảo vệ ranh giới dependency và SLO; **mã nghiệp vụ** quyết định retry workflow dựa trên trạng thái và quy tắc nghiệp vụ.
- Chọn một retry owner chính cho mỗi nhóm lỗi. Nếu nhiều lớp cùng retry, tính tổng attempt theo trường hợp lồng nhau và kiểm tra semantics max attempts/max retries.
- Không retry lỗi cấu hình, validation, authentication/authorization hoặc conflict nghiệp vụ một cách mù quáng.
- Retry cần deadline, retry budget, exponential backoff, jitter và tôn trọng Retry-After; kết hợp circuit breaker, bulkhead và rate limit khi phù hợp.
- Retry thao tác ghi cần idempotency, deterministic ID, conditional write hoặc deduplication. Timeout không chứng minh side effect chưa xảy ra.
- Business retry nên có trạng thái, lịch chạy lại, deadline và đường kết thúc/DLQ; dùng outbox/inbox khi cần phối hợp database và messaging.
- Đo attempt ở SDK, Spring, business workflow và broker; kiểm thử cả trường hợp thành công, bị từ chối, timeout, duplicate và hết retry budget.

## Tài liệu tham khảo

- [Spring Retry project](https://github.com/spring-projects/spring-retry)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Azure SDK for Java — Retry policy](https://learn.microsoft.com/azure/developer/java/sdk/retries)
- [Azure Storage retry policy](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-java)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [AWS SDK for Java 2.x retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Google Cloud Pub/Sub retry policy](https://cloud.google.com/pubsub/docs/subscription-retry-policy)
