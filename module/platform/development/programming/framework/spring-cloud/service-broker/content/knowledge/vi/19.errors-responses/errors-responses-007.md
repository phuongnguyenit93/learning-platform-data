# Lỗi tạm thời của nhà cung cấp và lỗi không nên thử lại

## Bối cảnh

Service broker theo Open Service Broker API (OSB API) là lớp trung gian giữa Platform và provider thực sự cấp phát tài nguyên. Khi provision database, tạo cache, cập nhật plan hoặc thu hồi tài nguyên trên cloud/Kubernetes, broker có thể gặp lỗi từ mạng, quota, credential, policy, API provider hoặc trạng thái tài nguyên. Một số lỗi chỉ tồn tại trong thời gian ngắn và có thể tự hết; một số lỗi sẽ tiếp tục xảy ra cho đến khi cấu hình hoặc yêu cầu được sửa.

Phân loại sai lỗi gây ra hai nhóm sự cố. Nếu broker không retry lỗi tạm thời, một thao tác có thể thất bại dù provider chỉ bị gián đoạn vài giây. Nếu broker retry lỗi vĩnh viễn, hệ thống tạo tải vô ích, làm tăng chi phí, kéo dài thời gian xử lý và có thể gây side effect lặp. Vì vậy, broker phải xác định lỗi theo nguyên nhân và trạng thái nghiệp vụ, không chỉ nhìn vào HTTP status do provider trả về.

Trong module SPRING_CLOUD_SERVICE_BROKER, chính sách lỗi cần phối hợp ba lớp:

- **OSB API boundary:** chuyển lỗi thành HTTP status và JSON error response phù hợp khi request chưa được chấp nhận hoàn tất.
- **Operation lifecycle:** sau khi trả 202 Accepted, lưu lỗi vào operation và cung cấp qua last_operation.
- **Provider adapter/worker:** phân loại lỗi, retry có giới hạn, reconcile kết quả không chắc chắn và bảo đảm idempotency.

## 1. Hai thời điểm phát sinh lỗi

Điều đầu tiên cần xác định là lỗi xuất hiện trước hay sau khi broker chấp nhận một asynchronous operation.

### Lỗi trước khi chấp nhận operation

Broker chưa trả 202 và chưa cam kết thực hiện công việc nền. Nếu request không hợp lệ, caller không được phép hoặc provider từ chối vì điều kiện nghiệp vụ rõ ràng, broker có thể trả lỗi HTTP tương ứng ngay trong response của request.

Ví dụ:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 10

{
  "description": "The service provider is temporarily unavailable. Retry the request later."
}
~~~

Response 503 cho biết broker hiện không thể xử lý request vì dependency tạm thời không sẵn sàng. Platform có thể retry theo policy của nó. Broker không được trả 503 nếu request thực chất sai dữ liệu hoặc caller không có quyền.

### Lỗi sau khi đã trả 202 Accepted

Khi broker đã chấp nhận operation và trả 202, request HTTP ban đầu đã kết thúc. Nếu provider lỗi trong lúc worker chạy, broker không thể đổi response 202 cũ thành 503. Thay vào đó, broker cập nhật operation:

- Giữ state in progress khi lỗi được xem là tạm thời và còn retry trong budget.
- Chuyển sang succeeded khi provider đã đạt target state và broker xác minh được kết quả.
- Chuyển sang failed khi lỗi không thể khắc phục tự động hoặc retry budget đã hết.

Platform đọc kết quả qua endpoint last_operation:

~~~http
GET /v2/service_instances/db-42/last_operation?service_id=postgres&plan_id=standard&operation=provision-7f31a9
~~~

Trong lúc retry, response có thể là:

~~~json
{
  "state": "in progress",
  "description": "The provider is temporarily throttling requests; provisioning will continue."
}
~~~

Khi hết khả năng tự phục hồi:

~~~json
{
  "state": "failed",
  "description": "The provider rejected the requested storage configuration. Review the service parameters and try a new operation."
}
~~~

Description phải ngắn gọn, an toàn và đủ hữu ích để Platform/operator hiểu bước tiếp theo. Không đưa stack trace, access token, credential hoặc response thô của provider vào last_operation.

## 2. Phân loại lỗi theo khả năng phục hồi

Phân loại nên dựa trên nguyên nhân, khả năng sửa chữa và mức độ chắc chắn về side effect.

| Nhóm lỗi | Ví dụ | Có nên retry tự động? |
|---|---|---|
| Lỗi mạng tạm thời | Connection reset, timeout ngắn, DNS lookup chập chờn | Có điều kiện, sau khi đánh giá kết quả có thể đã xảy ra |
| Provider quá tải/throttling | HTTP 429, một số 503 | Có, tôn trọng Retry-After và budget |
| Provider gián đoạn | HTTP 502/503 hoặc lỗi gateway tạm thời | Có điều kiện |
| Lock/version contention | Kubernetes resourceVersion conflict, lock tạm thời | Có, sau khi đọc lại trạng thái và tính lại thay đổi |
| Eventual consistency | Resource vừa tạo chưa xuất hiện trong lần đọc tiếp theo | Retry polling có giới hạn |
| Request sai | Thiếu tham số, sai định dạng, giá trị ngoài miền cho phép | Không |
| Plan/capability không hỗ trợ | Provider không hỗ trợ tính năng được yêu cầu | Không cho đến khi đổi plan/cấu hình |
| Quyền bị từ chối | Provider credential thiếu IAM role hoặc policy | Không retry liên tục; cần sửa quyền |
| Quota cứng | Tài khoản/region hết quota và không có dấu hiệu quota sắp được giải phóng | Không tự retry vô hạn |
| Trạng thái nghiệp vụ xung đột | Instance đang có update khác, binding thuộc consumer khác | Không retry ngay; giải quyết xung đột trước |
| Kết quả không xác định | Timeout sau khi gửi lệnh tạo/xóa tài nguyên | Reconcile trước khi quyết định retry |

Một lỗi không tự động trở thành transient chỉ vì provider trả 5xx. Ngược lại, một lỗi có HTTP 409 hoặc 429 có thể phục hồi được nếu nguyên nhân là contention hoặc throttling. Adapter cần đọc error code/provider reason và ngữ cảnh operation để phân loại.

### Lỗi tạm thời thường gặp

- Kết nối TCP bị reset trong lúc provider đang bảo trì.
- Provider API trả 429 do giới hạn request rate.
- Gateway trả 502/503 khi upstream tạm thời không khỏe.
- DNS resolver tạm thời không truy vấn được.
- Kubernetes API trả conflict vì resourceVersion đã thay đổi; broker có thể GET resource mới và tính lại patch.
- Provider chấp nhận lệnh nhưng tài nguyên cần thời gian để chuyển sang READY.
- Database failover làm một request đọc/ghi thất bại trong một khoảng ngắn.

### Lỗi không nên thử lại với cùng input

- Plan không cung cấp tính năng được yêu cầu.
- Parameter sai kiểu, sai miền giá trị hoặc vi phạm validation.
- Region không hỗ trợ loại tài nguyên.
- Provider xác nhận quota đã vượt giới hạn cứng và cần operator tăng quota hoặc đổi plan.
- Service account của broker thiếu quyền tạo resource.
- Credential đã bị revoke hoặc hết hạn mà broker không có cơ chế refresh.
- Chính sách bảo mật từ chối yêu cầu.
- Instance hoặc binding đang ở trạng thái không cho phép thao tác.

Một số lỗi có thể thay đổi nhóm khi điều kiện thay đổi. Ví dụ quota có thể được giải phóng sau khi tài nguyên khác bị xóa; tuy nhiên broker không nên polling/retry liên tục nếu không có tín hiệu quota đã thay đổi. Cần xác định điều kiện phục hồi, thời gian chờ và giới hạn số lần thử.

## 3. Phân biệt lỗi của caller với lỗi credential của broker

Không ánh xạ trực tiếp mọi HTTP 401/403 của provider thành 401/403 trả về Platform. Có hai ranh giới xác thực khác nhau:

1. Platform gọi broker và cung cấp credential của Platform.
2. Broker dùng credential/service account của chính broker để gọi provider.

Nếu Platform gửi sai credential tới broker, broker trả 401 Unauthorized. Nếu Platform đã được xác thực nhưng credential nội bộ của broker hết hạn hoặc thiếu quyền ở provider, đây là lỗi vận hành phía broker. Trả 401 cho Platform sẽ khiến Platform nghĩ rằng credential của nó sai và có thể không retry hoặc báo lỗi sai đối tượng.

Ví dụ phân loại:

| Nguồn lỗi | Ý nghĩa | Hành vi |
|---|---|---|
| Broker authentication trả 401 | Platform chưa xác thực | Trả 401 |
| Broker authorization trả 403 | Platform không có quyền gọi thao tác | Trả 403 |
| Provider trả 401 vì broker token hết hạn | Credential nội bộ cần refresh/rotate | Thử refresh theo policy; nếu không phục hồi, ghi lỗi vận hành và báo lỗi broker phù hợp |
| Provider trả 403 vì IAM role thiếu quyền | Cấu hình quyền của broker sai | Dừng retry vô ích, cảnh báo operator |

Không để Platform đổi credential của nó để chữa một lỗi IAM của broker. Error description cũng không nên tiết lộ tên service account, policy ARN, token hoặc thông tin bảo mật của provider.

## 4. Bảng quyết định cho các HTTP status từ provider

HTTP status là tín hiệu đầu vào, không phải chính sách retry hoàn chỉnh. Adapter nên kết hợp status với provider error code, operation phase, tính idempotent của lệnh và trạng thái tài nguyên.

| Provider status | Cách diễn giải thường gặp | Quyết định phía broker |
|---|---|---|
| 400 | Request provider sai hoặc schema không hợp lệ | Kiểm tra lỗi do input hay do broker tạo request sai; không retry cùng payload |
| 401 | Provider credential không hợp lệ/hết hạn | Refresh nếu hỗ trợ; nếu không, dừng và báo vận hành |
| 403 | Thiếu quyền hoặc policy từ chối | Không retry liên tục; cần sửa quyền/policy |
| 404 | Resource không tồn tại hoặc endpoint sai | Theo operation: delete có thể đã đạt mục tiêu; read/provision cần kiểm tra scope và mapping |
| 409 | Conflict, version mismatch, resource đã tồn tại | Đọc lại trạng thái, phân biệt conflict có thể giải quyết với xung đột nghiệp vụ |
| 422 | Provider không chấp nhận cấu hình/ngữ nghĩa request | Thường là lỗi input/capability; không retry cùng payload |
| 429 | Rate limit/throttling | Retry theo Retry-After hoặc backoff, có budget |
| 500 | Provider internal error | Có thể tạm thời; cần phân loại reason và reconcile nếu kết quả không chắc chắn |
| 502 | Gateway nhận phản hồi upstream không hợp lệ | Thường transient; retry có giới hạn |
| 503 | Provider/service tạm không sẵn sàng | Retry có giới hạn, tôn trọng Retry-After |
| 504 | Gateway timeout | Kết quả có thể không xác định; reconcile trước khi lặp side effect |

### Không sao chép status provider ra OSB một cách máy móc

Ví dụ, provider trả 403 vì broker service account thiếu IAM permission. Nếu broker trả 403 cho Platform, Platform có thể hiểu caller không được phép và không báo đúng đội vận hành. Broker cần chuyển lỗi thành lỗi dependency/broker-side phù hợp, thường là 5xx khi request đồng bộ hoặc operation failed sau 202.

Tương tự, provider trả 409 do Kubernetes resourceVersion conflict có thể được giải quyết bằng GET mới và retry patch. Nhưng OSB 409 gửi cho Platform có thể biểu thị xung đột trạng thái nghiệp vụ của service instance. Hai lỗi cùng status nhưng ý nghĩa và người chịu trách nhiệm khác nhau.

## 5. Quy tắc chọn retry

Chỉ retry khi tất cả điều kiện sau được thỏa mãn:

1. Lỗi được phân loại là transient hoặc có tín hiệu phục hồi rõ ràng.
2. Thao tác có thể lặp an toàn, hoặc broker có idempotency/reconciliation đủ để tránh side effect trùng.
3. Retry còn nằm trong thời gian deadline và budget đã cấu hình.
4. Provider không yêu cầu chờ một thời điểm cụ thể lâu hơn deadline.
5. Operation chưa bị hủy hoặc thay thế bởi thao tác mới.
6. Retry không làm vượt quota, rate limit hoặc giới hạn concurrency của provider.

Nếu một điều kiện không đạt, broker nên dừng retry hoặc chuyển sang reconcile/manual intervention theo loại lỗi. Không có chính sách “retry mọi exception” trong worker.

### Retry cho thao tác đọc và thao tác có side effect

GET trạng thái provider thường an toàn để retry, nhưng vẫn cần backoff và rate limit. PUT/POST tạo tài nguyên, PATCH thay đổi cấu hình và DELETE có side effect cần thận trọng hơn.

Trước khi retry lệnh tạo tài nguyên sau timeout, broker phải xác định provider đã tạo tài nguyên chưa. Có thể dùng idempotency token do provider hỗ trợ, deterministic resource name, tag chứa operation ID hoặc truy vấn trạng thái theo owner metadata.

Đối với delete, provider trả NotFound có thể được xem là thành công nếu broker xác minh đúng resource ID và owner scope; không được xóa hoặc coi thành công chỉ dựa trên tên tài nguyên không duy nhất.

## 6. Exponential backoff, jitter và Retry-After

Retry dồn dập có thể làm provider quá tải nặng hơn. Broker nên dùng exponential backoff với jitter, có thời gian tối thiểu/tối đa và tổng deadline rõ ràng.

Một công thức tham khảo:

\[
delay_n = \min(delay_{max}, delay_{base} \times 2^n) + jitter
\]

Trong đó:

- delay_base là thời gian chờ ban đầu.
- n là số lần retry đã thực hiện.
- delay_max giới hạn khoảng chờ tối đa.
- jitter là thành phần ngẫu nhiên để các worker không đồng loạt retry.

Ví dụ policy:

| Lần retry | Backoff cơ sở minh họa |
|---|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |

Đây chỉ là ví dụ; production cần điều chỉnh theo provider quota, latency, deadline của operation và số lượng worker.

### Tôn trọng Retry-After

Nếu provider trả 429 hoặc 503 kèm Retry-After, broker nên chờ ít nhất tới thời điểm provider chỉ định, trong giới hạn deadline và policy của mình. Retry-After có thể biểu diễn số giây hoặc HTTP date. Cần parse an toàn, xử lý giá trị sai định dạng và tránh retry sớm hơn chỉ vì backoff nội bộ ngắn hơn.

Nếu thời gian Retry-After vượt deadline còn lại, broker nên giữ operation chờ theo policy dài hạn hoặc kết thúc với lỗi có thể hành động được; không bỏ qua header rồi tiếp tục gửi request liên tục.

### Lưu thời điểm retry bền vững

Với asynchronous operation, lưu retry_count và next_attempt_at trong database. Worker không nên dùng Thread.sleep trong một thread để chờ nhiều phút. Thay vào đó, chuyển operation sang RETRY_WAIT, nhả lease và để scheduler/queue phát lại khi đến hạn. Sau restart, thời điểm retry vẫn được giữ nguyên.

## 7. Retry budget và deadline

Số lần retry không phải mục tiêu tự thân. Broker cần giới hạn theo:

- Số lần gọi provider tối đa cho từng phase.
- Tổng thời gian operation được phép chạy.
- Số lần retry liên tiếp cho cùng error category.
- Ngân sách request toàn hệ thống tới provider.
- Retry budget theo tenant/plan nếu cần bảo vệ fairness.

Ví dụ policy minh họa:

| Tham số | Giá trị ví dụ | Mục đích |
|---|---:|---|
| Max attempts | 6 | Giới hạn số lần gọi trong một phase |
| Base delay | 1 giây | Bắt đầu backoff |
| Max delay | 30 giây | Tránh chờ tăng vô hạn |
| Operation deadline | 15 phút | Giới hạn thời gian xử lý nền |
| Reconcile attempts | 3 | Xác định kết quả sau timeout |

Các giá trị phải được cấu hình theo loại service/plan và cam kết với Platform. Không áp dụng cùng deadline cho thao tác tạo database vài phút và thao tác thu hồi token vài giây.

Khi hết budget:

- Nếu provider đã đạt target state, đánh dấu succeeded.
- Nếu lỗi terminal đã rõ, đánh dấu failed với description an toàn.
- Nếu kết quả vẫn không xác định, chuyển trạng thái reconciliation/manual review theo chính sách và cảnh báo operator; không tuyên bố thành công hay thất bại khi chưa có căn cứ.

## 8. Xử lý timeout và kết quả không xác định

Timeout không chứng minh provider không thực hiện thao tác. Ví dụ:

1. Broker gửi yêu cầu tạo database.
2. Provider nhận và tạo resource.
3. Response bị mất trên mạng.
4. Broker nhận timeout.

Nếu broker retry create ngay mà provider không hỗ trợ idempotency, có thể tạo database thứ hai.

Quy trình an toàn:

1. Lưu operation ID và idempotency token trước khi gọi provider.
2. Gửi lệnh với token hoặc metadata liên kết operation nếu provider hỗ trợ.
3. Nếu timeout, đánh dấu kết quả UNKNOWN/RECONCILING.
4. Tìm resource theo token, deterministic name hoặc owner tag.
5. Nếu resource đã tồn tại và đúng target, ghi nhận resource ID và tiếp tục.
6. Nếu provider xác nhận chưa có side effect, retry lệnh theo cùng identity.
7. Nếu không thể xác định, giữ trạng thái cần reconcile và yêu cầu can thiệp theo SLA.

~~~mermaid
flowchart TD
    A[Provider call timeout] --> B[Mark result UNKNOWN]
    B --> C[Reconcile by operation token/resource tag]
    C --> D{Provider outcome known?}
    D -->|Resource reached target| E[Persist provider resource ID]
    E --> F[Continue operation]
    D -->|No side effect occurred| G[Retry same idempotent command]
    G --> C
    D -->|Partial or conflicting state| H[Compensate or manual review]
    D -->|Still unknown| I[Keep RECONCILING and alert]
~~~

Không tạo operation ID mới chỉ vì một lần provider call timeout. Operation ID OSB đại diện cho công việc Platform đã yêu cầu; retry provider phải tiếp tục cùng operation và cùng idempotency identity nội bộ.

## 9. Circuit breaker, bulkhead và backpressure

Khi provider liên tục trả lỗi transient, retry từng operation có thể tạo retry storm. Circuit breaker giúp tạm ngừng gọi provider khi tỷ lệ lỗi vượt ngưỡng:

- **Closed:** cho phép request đi qua và theo dõi lỗi.
- **Open:** từ chối hoặc trì hoãn call mới trong thời gian cooldown.
- **Half-open:** cho phép một số probe để kiểm tra provider đã phục hồi chưa.

Circuit breaker nên được áp dụng theo dependency/provider/region phù hợp. Một sự cố ở region A không nhất thiết phải chặn mọi operation ở region B.

Bulkhead giới hạn concurrency để một provider chậm không chiếm hết worker hoặc connection pool. Backpressure và queue partitioning giúp broker kiểm soát lượng operation chờ. Khi queue backlog lớn, broker có thể giảm tốc độ claim job và trả 503 trước khi nhận request mới nếu chưa thể đảm bảo lưu operation.

Không dùng circuit breaker để đánh dấu operation failed ngay khi provider tạm mở circuit. Operation đã được chấp nhận có thể ở RETRY_WAIT/WAITING_PROVIDER cho tới khi deadline hoặc retry budget kết thúc.

## 10. Ánh xạ lỗi provider sang OSB API

Broker cần giữ ranh giới giữa lỗi request và lỗi dependency:

| Tình huống | Nếu xảy ra trước khi chấp nhận async | Nếu xảy ra sau khi trả 202 |
|---|---|---|
| Request parameters sai | 400 Bad Request với description phù hợp | Không áp dụng; validation phải hoàn tất trước khi accept |
| Platform credential sai | 401 Unauthorized | Worker không xác thực Platform lại; đây là lỗi broker/provider khác |
| Platform không có quyền | 403 Forbidden | Không chuyển thành provider permission error |
| Instance/binding không tồn tại | 404/410 theo endpoint OSB tương ứng | Cập nhật operation theo loại thao tác; không dùng nhầm status |
| Operation xung đột | 409 hoặc 422 ConcurrencyError theo contract | Không tạo side effect song song; lưu kết quả theo operation |
| Cần async nhưng Platform chưa chấp thuận | 422 với error AsyncRequired | Không được xảy ra nếu broker chỉ accept sau khi kiểm tra |
| Provider throttling tạm thời | 503 hoặc response phù hợp; có thể Retry-After | Giữ in progress và schedule retry |
| Provider 5xx tạm thời | 502/503 hoặc lỗi broker phù hợp | Retry/reconcile; cuối cùng succeeded hoặc failed |
| Provider credential broker sai | 5xx và cảnh báo vận hành | Retry refresh có giới hạn hoặc failed khi không phục hồi |
| Provider từ chối cấu hình vĩnh viễn do input của caller | 4xx phù hợp với ý nghĩa OSB request | Mark failed với description an toàn |

### Error response body

OSB error response nên có JSON object với description rõ ràng. Khi contract cần error code, ví dụ AsyncRequired hoặc ConcurrencyError, dùng trường error tương ứng. Không sao chép nguyên văn provider response vào body.

Ví dụ lỗi request có thể sửa:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "description": "The requested storage_size must be a positive integer."
}
~~~

Ví dụ dependency tạm thời:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 15

{
  "description": "The service provider is temporarily unavailable. Retry the request later."
}
~~~

Ví dụ concurrency:

~~~http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": "ConcurrencyError",
  "description": "Another operation is currently modifying this service instance. Retry after it completes."
}
~~~

HTTP status phải phản ánh lỗi tại ranh giới broker/Platform. Không để provider status 403 hoặc 409 tự động quyết định status OSB nếu nguyên nhân và đối tượng chịu trách nhiệm khác nhau.

Provider trả 400/422 chỉ nên được ánh xạ thành lỗi 4xx của Platform khi broker xác định nguyên nhân thực sự nằm trong input hoặc lựa chọn plan của caller. Nếu broker tự tạo request sai schema, gửi trường không hợp lệ hoặc dùng API provider sai phiên bản, đó là lỗi triển khai phía broker; hãy ghi nhận như lỗi broker/provider-side, trả 5xx nếu request còn đồng bộ hoặc cập nhật operation failed nếu đã trả 202, đồng thời cảnh báo đội vận hành.

## 11. Mô hình exception trong Spring Cloud

Provider adapter nên chuyển lỗi SDK/HTTP/client thành các exception miền có kiểu rõ ràng. Application service không nên phải phân tích chuỗi message hoặc phụ thuộc trực tiếp vào exception của từng SDK.

Một taxonomy tham khảo:

~~~java
sealed class ProviderFailure extends RuntimeException
        permits ProviderTransientFailure,
                ProviderPermanentFailure,
                ProviderPermissionFailure,
                ProviderOutcomeUnknown {

    ProviderFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

final class ProviderTransientFailure extends ProviderFailure {
    private final Duration retryAfter;

    ProviderTransientFailure(
            String message, Duration retryAfter, Throwable cause) {
        super(message, cause);
        this.retryAfter = retryAfter;
    }

    Duration retryAfter() {
        return retryAfter;
    }
}

final class ProviderPermanentFailure extends ProviderFailure {
    ProviderPermanentFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

final class ProviderPermissionFailure extends ProviderFailure {
    ProviderPermissionFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

final class ProviderOutcomeUnknown extends ProviderFailure {
    ProviderOutcomeUnknown(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là ví dụ Java minh họa; có thể dùng record, sealed interface hoặc hierarchy phù hợp với Java version của dự án. Các exception nên mang error category, provider code đã chuẩn hóa, retryAfter, operation phase và safe description. Không đưa secret hoặc raw provider body vào message.

### Chuẩn hóa trong provider adapter

~~~java
ProviderResource createDatabase(CreateDatabaseCommand command) {
    try {
        return providerClient.createDatabase(
                command.request(),
                command.idempotencyToken());
    } catch (ProviderRateLimitException ex) {
        throw new ProviderTransientFailure(
                "Provider rate limit reached",
                ex.retryAfter(),
                ex);
    } catch (ProviderValidationException ex) {
        throw new ProviderPermanentFailure(
                "Provider rejected the database configuration",
                ex);
    } catch (ProviderAuthorizationException ex) {
        throw new ProviderPermissionFailure(
                "Broker provider credentials lack permission",
                ex);
    } catch (ProviderTimeoutException ex) {
        throw new ProviderOutcomeUnknown(
                "Provider outcome is unknown after timeout",
                ex);
    }
}
~~~

Tên exception SDK ở đây là placeholder, không phải class có sẵn của mọi provider. Adapter thực tế phải map mã lỗi và response cụ thể của cloud/Kubernetes client.

## 12. Retry worker và cập nhật last_operation

Worker nên phân nhánh theo loại lỗi:

~~~java
void execute(Operation operation) {
    try {
        var result = providerWorkflow.resume(operation);
        operationService.recordProgress(operation.id(), result);
    } catch (ProviderTransientFailure ex) {
        if (retryPolicy.canRetry(operation, ex)) {
            operationService.scheduleRetry(
                    operation.id(),
                    retryPolicy.nextAttemptAt(operation, ex));
        } else {
            operationService.markFailed(
                    operation.id(),
                    "The provider remained unavailable after the retry limit.");
        }
    } catch (ProviderOutcomeUnknown ex) {
        operationService.scheduleReconciliation(
                operation.id(),
                "Provider outcome must be checked before retry.");
    } catch (ProviderPermissionFailure ex) {
        operationService.markFailed(
                operation.id(),
                "The broker could not access the provider. Contact the service operator.");
        alerting.notifyProviderPermissionFailure(operation, ex);
    } catch (ProviderPermanentFailure ex) {
        operationService.markFailed(
                operation.id(),
                "The provider rejected the requested configuration.");
    }
}
~~~

Đoạn mã là pseudocode minh họa. Trong implementation, mọi thay đổi state phải kiểm tra operation version/fencing token và được lưu bền vững. Retry scheduling không nên block worker thread bằng sleep; ghi next_attempt_at rồi để scheduler/queue phát lại.

Nếu provider transient nhưng còn budget, last_operation tiếp tục trả state in progress. Khi hết budget, worker ghi state failed và safe description. Nếu provider đã hoàn thành trong lúc broker timeout, reconciliation sẽ phát hiện và đánh dấu succeeded thay vì failed.

## 13. Không retry nhiều tầng cùng lúc

Một request có thể đi qua nhiều lớp đều có retry:

~~~text
Platform
  -> Broker HTTP client
      -> Application service
          -> Provider SDK retry
              -> HTTP transport retry
~~~

Nếu mỗi lớp retry 3 lần, số lần gọi thực tế có thể nhân lên nhanh hơn dự kiến. Ví dụ 3 lần ở ba tầng có thể tạo tới 27 lần thử cho một ý định. Điều này làm provider quá tải và khiến operation vượt deadline.

Chọn một tầng chịu trách nhiệm retry nghiệp vụ. SDK có thể retry rất ít cho lỗi transport an toàn, nhưng application layer phải biết tổng attempt/deadline và tắt hoặc giới hạn retry ngầm của SDK khi cần. Platform retry request HTTP là một cơ chế riêng; broker vẫn phải idempotent để Platform retry không tạo side effect mới.

Ghi lại attempt count ở tầng nghiệp vụ và correlation metadata để biết mỗi lần gọi thuộc cùng operation. Không cộng retry HTTP của Platform vào retry count của provider một cách mơ hồ.

## 14. Compensation và lỗi sau side effect một phần

Provision/update có thể gồm nhiều bước. Một số bước thành công rồi bước sau thất bại:

1. Tạo network rule thành công.
2. Tạo database thành công.
3. Cấp credential thất bại vì provider IAM.

Broker phải quyết định tiếp tục sửa lỗi, retry bước cấp credential, hoặc chạy compensation để dọn tài nguyên đã tạo. Không đánh dấu FAILED rồi bỏ quên network/database tồn tại mà không có mapping trong broker.

### Chọn retry hay compensation

| Trạng thái | Hành động |
|---|---|
| Lỗi transient ở bước hiện tại, các bước trước còn hợp lệ | Retry đúng bước hiện tại |
| Provider đã thực hiện bước nhưng response mất | Reconcile, không tạo lại |
| Lỗi permanent khiến target không thể đạt được | Chạy compensation nếu workflow yêu cầu rollback |
| Compensation cũng lỗi transient | Retry compensation có giới hạn và lưu trạng thái |
| Compensation không thể hoàn tất | Đánh dấu cần operator intervention và cảnh báo |

Với update có migration dữ liệu, rollback có thể không an toàn hoặc không thể thực hiện. Khi đó cần forward recovery: sửa nguyên nhân và tiếp tục đưa tài nguyên tới target state. Chính sách lỗi phải được định nghĩa theo workflow, không mặc định mọi lỗi đều rollback.

## 15. Description an toàn và hữu ích

Error description được Platform/operator đọc, nên mô tả nguyên nhân ở mức có thể hành động mà không làm lộ chi tiết nội bộ.

| Không nên trả | Nên trả |
|---|---|
| Full stack trace của SDK | "The provider is temporarily unavailable." |
| Authorization header hoặc token | "The broker could not authenticate with the provider; contact the service operator." |
| SQL query chứa dữ liệu nhạy cảm | "The provider rejected the requested database configuration." |
| Raw cloud response chứa account/resource metadata | "The requested region does not support this service plan." |
| Nội dung exception có secret | Safe description được tạo từ error category |

Chi tiết đầy đủ có thể được giữ trong log nội bộ đã kiểm soát quyền truy cập, gắn operation ID và request correlation. Log cũng phải mask credential, token, password và parameter nhạy cảm.

## 16. Kiểm thử phân loại lỗi và retry

Test phải xác nhận không chỉ số lần gọi provider mà cả trạng thái operation, response OSB và side effect.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Provider trả 429 kèm Retry-After | Operation chờ đủ thời gian, không retry sớm |
| Provider trả 503 tạm thời | Retry theo backoff khi còn budget |
| Provider trả 400 validation | Không retry cùng payload |
| Provider trả 403 do broker IAM | Không trả nhầm 403 của caller; alert operator |
| Provider trả 409 resourceVersion conflict | GET mới, tính lại và retry có giới hạn |
| Provider trả 409 xung đột nghiệp vụ | Không retry cho đến khi xung đột được giải quyết |
| Provider timeout sau create | Reconcile trước khi gọi create lại |
| Provider timeout nhưng resource đã READY | Operation được đánh dấu succeeded |
| Provider timeout và resource chưa tồn tại | Retry cùng idempotency token |
| Provider lỗi sau 202 | last_operation giữ in progress khi retry, failed khi terminal |
| Retry budget hết | Không phát thêm provider call |
| Circuit breaker open | Operation được trì hoãn, không tạo retry storm |
| Provider credential hết hạn | Refresh có giới hạn hoặc báo lỗi vận hành |
| Side effect một phần | Retry đúng phase hoặc compensation |
| Broker restart trong RETRY_WAIT | next_attempt_at và attempt count được giữ nguyên |
| Error description | Không chứa stack trace, secret hoặc raw provider response |

### Test không retry lỗi permanent

1. Mock provider adapter trả ProviderPermanentFailure.
2. Gửi provision request.
3. Xác nhận provider call chỉ xảy ra một lần cho phase đó.
4. Xác nhận operation chuyển failed nếu đã accept async, hoặc trả lỗi HTTP phù hợp nếu chưa accept.
5. Xác nhận không tạo retry event/queue message tiếp theo.
6. Xác nhận description an toàn và log nội bộ có correlation để điều tra.

### Test timeout có kết quả không xác định

Giả lập provider đã tạo resource nhưng client nhận timeout. Xác nhận worker chuyển sang reconciliation, tìm được resource theo operation token/tag và hoàn tất cùng operation ID. Kiểm tra provider không có tài nguyên trùng.

## 17. Quan sát và vận hành

Các metric nên theo dõi:

- Số lỗi provider theo provider, region và error category.
- Tỷ lệ transient/permanent/unknown outcome.
- Retry attempts và retry exhaustion.
- Thời gian chờ Retry-After.
- Operation age và số operation ở RETRY_WAIT/RECONCILING.
- Circuit breaker state và thời gian ở OPEN.
- Queue backlog, worker concurrency và provider latency.
- Số resource mồ côi được phát hiện trong reconciliation.

Log nên có operation ID, instance ID, provider request/reference ID, error category, attempt number, retry deadline và correlation ID. Tránh dùng instance ID/request identity làm metric label không giới hạn cardinality. Dùng log/trace để điều tra một operation cụ thể.

Alert phù hợp:

- Tỷ lệ 429/503 vượt ngưỡng trong một region.
- Nhiều operation hết retry budget cùng lúc.
- Operation RECONCILING quá lâu.
- Provider credential permission failure.
- Circuit breaker mở liên tục.
- Queue backlog tăng trong khi worker throughput giảm.

## 18. Checklist triển khai

- [ ] Phân biệt lỗi trước khi accept request và lỗi sau khi trả 202.
- [ ] Phân loại provider error theo nguyên nhân, không chỉ theo HTTP status.
- [ ] Tách Platform authentication khỏi provider credential của broker.
- [ ] Không retry request sai, quyền bị từ chối hoặc cấu hình không được hỗ trợ.
- [ ] Retry transient có backoff, jitter, Retry-After và deadline.
- [ ] Có retry budget theo operation/phase.
- [ ] Reconcile sau timeout hoặc kết quả provider không xác định.
- [ ] Provider side effect có idempotency token/tag hoặc cách tra cứu resource.
- [ ] Lưu retry_count, next_attempt_at và operation state bền vững.
- [ ] Không block worker thread bằng sleep khi chờ retry dài.
- [ ] Dùng circuit breaker, bulkhead và backpressure để tránh retry storm.
- [ ] Tránh retry nhân lên ở Platform, application, SDK và transport.
- [ ] Sau 202, lỗi được phản ánh qua last_operation.
- [ ] Side effect một phần có retry phase, compensation hoặc forward recovery.
- [ ] Error description không tiết lộ secret, stack trace hoặc raw provider response.
- [ ] Có test xác nhận lỗi permanent không phát retry và timeout không tạo resource trùng.

## Kết luận

Lỗi tạm thời của provider có thể được thử lại khi broker có căn cứ rằng lỗi sẽ phục hồi, thao tác lặp an toàn và vẫn còn retry budget. Lỗi do request sai, plan không hỗ trợ, quyền bị từ chối hoặc quota cứng không nên được retry liên tục với cùng điều kiện. HTTP status của provider chỉ là một tín hiệu; broker phải phân loại theo nguyên nhân, ranh giới xác thực và trạng thái side effect. Với request đồng bộ, broker trả HTTP error phù hợp; sau khi đã trả 202, broker giữ operation in progress trong lúc retry và ghi failed khi lỗi trở thành terminal. Backoff, Retry-After, reconciliation, idempotency, circuit breaker và description an toàn giúp service broker Spring Cloud phục hồi đúng cách mà không tạo tài nguyên trùng hoặc làm provider quá tải.

## Tài liệu tham khảo

- [Open Service Broker API specification — Asynchronous Operations](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#asynchronous-operations)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585)
