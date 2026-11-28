# Phân loại lỗi nhà cung cấp thành lỗi OSB phù hợp

Spring Cloud Service Broker thường đóng vai trò trung gian giữa platform và một hoặc nhiều hệ thống cung cấp tài nguyên. Khi Cloud Foundry, Kubernetes hoặc một platform khác gọi broker để provision, update, bind hay deprovision, broker tiếp tục gọi API của provider phía sau. Provider có thể trả lỗi HTTP, mã lỗi nghiệp vụ, timeout hoặc response không đúng định dạng. Broker phải phân loại các lỗi đó rồi chuyển thành response phù hợp với Open Service Broker API (OSB API).

Việc ánh xạ lỗi không đơn giản là sao chép status code và message từ provider. Broker cần xác định lỗi phát sinh từ request của platform, từ xác thực platform với broker, từ cấu hình tích hợp của broker hay từ provider. Cùng một mã HTTP có thể mang ý nghĩa khác nhau tùy thao tác và trạng thái tài nguyên. Ánh xạ đúng giúp platform biết khi nào cần sửa request, khi nào có thể retry, khi nào operation vẫn đang chạy và khi nào cần người vận hành can thiệp.

## 1. Các lớp lỗi trong một service broker

Một request OSB có thể đi qua nhiều lớp:

1. Platform gửi request đến broker.
2. Broker xác thực caller, kiểm tra phiên bản OSB API và validate dữ liệu.
3. Broker kiểm tra service instance, plan, binding và trạng thái operation trong database.
4. Adapter chuyển request thành lệnh phù hợp với provider.
5. Provider xử lý lệnh và trả response hoặc lỗi.
6. Broker cập nhật trạng thái, trả response OSB và ghi log.

Lỗi cần được phân loại theo nơi phát sinh và nguyên nhân:

| Lớp | Ví dụ | Chủ thể có thể khắc phục |
|---|---|---|
| Request/platform | JSON sai, thiếu service ID, plan không hợp lệ | Platform hoặc người gọi API |
| Xác thực platform với broker | Credential broker sai, caller không có quyền | Platform administrator hoặc người quản trị broker |
| Trạng thái nghiệp vụ broker | Instance không tồn tại, operation khác đang chạy | Platform chờ/thử lại hoặc xử lý theo trạng thái instance |
| Tích hợp broker-provider | Credential provider hết hạn, endpoint cấu hình sai | Người vận hành broker |
| Provider tạm thời lỗi | Rate limit, service unavailable, timeout | Broker retry hoặc platform retry theo response |
| Provider từ chối nghiệp vụ | Quota cạn, cấu hình không hỗ trợ, resource conflict | Platform/người dùng hoặc quản trị provider |
| Lỗi response provider | JSON không hợp lệ, thiếu external resource ID | Người phát triển/vận hành adapter |

Điểm quan trọng là phân biệt caller authentication với provider authentication. Ví dụ broker gọi provider bằng service account và nhận HTTP 401. Điều đó không có nghĩa platform đã gửi credential sai khi gọi broker. Nếu broker trả 401 cho platform trong trường hợp này, platform có thể vô tình xoay credential broker mà không giải quyết được lỗi tích hợp thực tế.

## 2. Cấu trúc error response của OSB API

OSB API sử dụng response lỗi dạng JSON với hai field chính:

    {
      "error": "ProviderUnavailable",
      "description": "The service provider is temporarily unavailable."
    }

Field error là mã lỗi ổn định để client hoặc platform có thể phân loại. Field description là thông tin giải thích an toàn cho người vận hành hoặc người gọi API. Với lỗi do broker tự định nghĩa, tên mã lỗi nên nhất quán và không phụ thuộc trực tiếp vào chuỗi message của provider.

Các nguyên tắc:

- Trả HTTP status phản ánh đúng ngữ nghĩa lỗi theo hợp đồng OSB API và HTTP.
- Dùng error code ổn định, có tài liệu và không đổi theo ngôn ngữ hoặc message của provider.
- Description ngắn gọn, không chứa stack trace, token, password, địa chỉ nội bộ hoặc payload nhạy cảm.
- Không trả nguyên văn response lỗi provider nếu response đó có thể chứa thông tin hạ tầng.
- Giữ chi tiết kỹ thuật trong log nội bộ, gắn với request ID và provider request ID nếu có.
- Chỉ trả response lỗi sau khi xác định rõ broker đã tiếp nhận operation hay chưa.

Một số error code như AsyncRequired, ConcurrencyError, InstanceAlreadyExists, BindingAlreadyExists hoặc PlanChangeNotSupported được dùng trong các tình huống OSB tương ứng. Với lỗi provider riêng, broker có thể định nghĩa mã ổn định như ProviderUnavailable, ProviderTimeout hoặc ProviderConfigurationError. Các mã tùy chỉnh phải được hiểu là quy ước của broker, không phải mã chuẩn được mọi platform OSB biết sẵn.

## 3. Bảng ánh xạ HTTP status và OSB error

Bảng sau là hướng dẫn phân loại phổ biến. Cần đối chiếu phiên bản OSB API và khả năng tương thích của platform đích; không tự động chuyển status của provider sang cùng status cho platform.

| Tình huống tại broker | HTTP response gợi ý | Error code gợi ý | Ý nghĩa với platform |
|---|---:|---|---|
| Request thiếu field hoặc sai cấu trúc | 400 | BadRequest | Sửa request trước khi gửi lại |
| Caller xác thực không thành công | 401 | Unauthorized | Kiểm tra credential gọi broker |
| Caller không có quyền | 403 | Forbidden | Kiểm tra quyền và phạm vi platform |
| Service, plan, instance hoặc binding không tồn tại | 404 | Service/Plan/Instance/BindingNotFound theo hợp đồng broker | Kiểm tra ID và phạm vi tài nguyên |
| Instance hoặc binding đã tồn tại với dữ liệu không tương thích | 409 | InstanceAlreadyExists hoặc BindingAlreadyExists | Xử lý xung đột tài nguyên |
| Một mutation khác đang chạy trên instance | 409 | ConcurrencyError | Chờ operation hiện tại rồi thử lại |
| Broker cần async nhưng platform không chấp nhận incomplete operation | 422 | AsyncRequired | Gửi lại với accepts_incomplete=true nếu platform hỗ trợ |
| Plan update không được hỗ trợ | 422 | PlanChangeNotSupported | Chọn plan hoặc quy trình được hỗ trợ |
| Request hợp lệ về cú pháp nhưng không đáp ứng chính sách nghiệp vụ | 422 | Mã nghiệp vụ ổn định, ví dụ QuotaExceeded | Điều chỉnh lựa chọn hoặc quota |
| Provider tạm thời không khả dụng, chưa tiếp nhận operation async | 503 | ProviderUnavailable | Có thể thử lại sau |
| Provider timeout và broker đóng vai trò gateway | 504 | ProviderTimeout | Kết quả có thể chưa xác định; cần retry an toàn |
| Provider trả response lỗi hoặc không hợp lệ | 502 | ProviderError | Broker không nhận được phản hồi upstream hợp lệ |
| Lỗi nội bộ không dự kiến của broker | 500 | InternalError | Broker gặp lỗi nội bộ |

502, 503 và 504 là các HTTP status có ngữ nghĩa gateway/service availability; chúng hữu ích khi broker hoạt động như lớp trung gian gọi provider. Nếu platform đích hoặc phiên bản OSB triển khai có giới hạn về status 5xx, cần kiểm tra tính tương thích và có thể dùng 500 với error code broker ổn định. Dù chọn status nào, không được làm sai khác giữa lỗi caller và lỗi tích hợp provider.

429 có thể phù hợp khi chính broker đang rate limit caller. Khi provider trả 429 vì giới hạn quota hoặc tốc độ gọi của broker, thường nên retry nội bộ và nếu chưa thể tiếp nhận async thì phản hồi platform bằng 503 cùng Retry-After phù hợp. Trả thẳng 429 có thể khiến platform hiểu rằng chính platform đã vượt rate limit của broker.

## 4. Phân loại lỗi 4xx từ provider

Không phải mọi 4xx của provider đều là lỗi do platform gửi. Broker tạo request upstream từ dữ liệu OSB và credential tích hợp; lỗi có thể nằm ở adapter hoặc cấu hình broker.

### 4.1. Provider trả 400 Bad Request

Khi provider trả 400, cần xác định:

- Request OSB ban đầu có thiếu hoặc sai dữ liệu theo hợp đồng broker không?
- Broker có chuyển đổi parameters sai kiểu, sai tên field hoặc sai định dạng không?
- Provider API có thay đổi version hoặc schema không?
- Provider có trả mã nghiệp vụ chi tiết cho một giới hạn cụ thể không?

Nếu broker đã xác nhận request OSB sai cú pháp hoặc thiếu field bắt buộc, trả 400 BadRequest là phù hợp. Nếu request OSB hợp lệ nhưng adapter tạo payload provider sai, đó là lỗi tích hợp broker; nên trả 502 hoặc 500 tùy nguyên nhân, đồng thời tạo cảnh báo nội bộ. Không chuyển mọi provider 400 thành OSB 400 vì điều đó có thể yêu cầu platform sửa một request vốn hợp lệ.

Nếu provider 400 cho biết một parameter người dùng không thể áp dụng cho plan đã chọn, broker có thể ánh xạ thành lỗi nghiệp vụ 422 với error code ổn định như InvalidServiceConfiguration, sau khi xác minh lỗi thực sự xuất phát từ dữ liệu người dùng và mô tả của provider đủ tin cậy.

### 4.2. Provider trả 401 hoặc 403

Khi broker gọi provider và nhận 401/403, hãy xem đây trước hết là lỗi credential hoặc quyền của broker đối với provider:

- Token provider có thể hết hạn hoặc bị thu hồi.
- Service account thiếu quyền tạo/xóa resource.
- Broker đang dùng nhầm account, project, namespace hoặc tenant.
- Secret reference trỏ đến credential cũ.
- Policy của provider vừa thay đổi.

Không trả 401/403 cho platform nếu caller đã xác thực thành công với broker. Có thể trả 502 hoặc 500 với mã ProviderAuthenticationFailed/ProviderAuthorizationFailed tùy chính sách, đồng thời cảnh báo đội vận hành. Description gửi platform chỉ nên nói broker không thể thực hiện thao tác với provider; không tiết lộ credential hoặc policy nội bộ.

Nếu provider từ chối quyền trên chính resource của tenant do dữ liệu consumer không hợp lệ, cần phân tích xem đó là lỗi request nghiệp vụ hay cấu hình quyền broker. Không tự động gán lỗi cho người dùng.

### 4.3. Provider trả 404 Not Found

Ngữ nghĩa 404 phụ thuộc operation:

| Operation | Provider 404 có thể có nghĩa | Cách xử lý |
|---|---|---|
| Provision | Endpoint, API version hoặc account không đúng | Xem là lỗi tích hợp; không coi provision thành công |
| Update | Resource ID đã lưu không còn tồn tại | Xác minh account/region và trạng thái instance; có thể cần reconciliation |
| Bind | Service instance hoặc resource phụ thuộc không tồn tại | Xác minh instance trước khi tạo principal/binding |
| Unbind | Principal/binding resource đã bị xóa trước đó | Có thể coi mục tiêu thu hồi đã đạt nếu đúng resource và đúng tenant |
| Deprovision | Resource chính không còn tồn tại | Có thể hoàn tất idempotent sau khi xác minh ownership |
| Retrieve/status check | Resource không tồn tại hoặc mapping sai | Phân biệt resource đã mất với lỗi account/endpoint |

Đối với DELETE, nếu provider xác nhận đúng external resource ID trong đúng account và tenant không còn tồn tại, mục tiêu thu hồi đã đạt; broker có thể đánh dấu operation thành công. Nhưng một 404 do sai endpoint hoặc sai account không phải bằng chứng resource đã bị xóa.

### 4.4. Provider trả 409 Conflict

Provider có thể trả 409 vì resource cùng tên đã tồn tại, một thao tác khác đang chạy hoặc trạng thái hiện tại không cho phép thay đổi.

- Nếu resource tồn tại do lần retry trước và metadata/owner khớp với binding hoặc instance đang xử lý, broker có thể tra cứu và tiếp tục idempotently.
- Nếu resource cùng tên thuộc tenant khác, không được nhận quyền sở hữu hoặc xóa nó; phân loại thành conflict nghiệp vụ hoặc lỗi cấu hình.
- Nếu provider báo một operation khác đang chạy, lưu provider operation ID nếu có và theo dõi thay vì tạo thao tác cạnh tranh.
- Nếu conflict là do hai request OSB mutation trên cùng instance, broker trả 409 ConcurrencyError theo trạng thái broker.

Không được ánh xạ provider 409 thành ConcurrencyError một cách máy móc. ConcurrencyError của OSB mô tả xung đột thao tác trên service instance trong broker; provider conflict có thể là resource name collision hoặc trạng thái upstream khác.

## 5. Phân loại lỗi 429 và 5xx

### 5.1. Provider rate limit: 429

Provider có thể giới hạn số request theo account, project, cluster hoặc API token. Khi nhận 429:

1. Đọc Retry-After hoặc metadata rate limit nếu provider cung cấp.
2. Áp dụng backoff và jitter.
3. Giới hạn concurrency của worker theo provider account.
4. Không retry liên tục trong cùng HTTP request.
5. Nếu platform đã chấp nhận async, giữ operation ở trạng thái in progress và lên lịch retry.
6. Nếu chưa thể tiếp nhận async, trả 503 với Retry-After phù hợp nếu có thể dự đoán thời điểm thử lại.

Nếu broker tự rate limit platform, trả 429 theo chính sách broker và có thể kèm Retry-After. Cần phân biệt hai lớp rate limit trong log và metric.

### 5.2. Provider trả 500 hoặc 502

Provider 500 thường biểu thị lỗi phía provider. Provider 502 có thể cho thấy gateway của provider không nhận được phản hồi hợp lệ từ upstream. Broker cần xác định lỗi có khả năng tạm thời hay là lỗi ổn định do payload hoặc cấu hình.

Nếu operation đã được tiếp nhận async, worker có thể retry với exponential backoff và giới hạn số lần thử. Nếu xử lý đồng bộ và provider vẫn lỗi, broker có thể trả 502/503 hoặc 500 tùy việc lỗi thuộc upstream hay nội bộ broker. Không để nguyên văn message provider đi ra ngoài.

### 5.3. Provider trả 503 Service Unavailable

503 thường biểu thị provider tạm thời không thể nhận request, có thể do maintenance hoặc quá tải. Broker nên:

- Tôn trọng Retry-After nếu có.
- Mở circuit breaker khi tỷ lệ lỗi vượt ngưỡng.
- Giảm concurrency và tránh tạo retry storm.
- Dùng async operation nếu platform đã cho phép và broker có operation store bền vững.
- Nếu không tiếp nhận operation, trả 503 cho platform để báo lỗi tạm thời.

### 5.4. Timeout và 504 Gateway Timeout

Timeout là tình huống đặc biệt vì kết quả side effect có thể chưa rõ. Broker có thể đã gửi lệnh provision và provider đã tạo database, nhưng response bị mất. Không nên kết luận chắc chắn rằng thao tác chưa xảy ra.

Broker cần đánh dấu nội bộ là OUTCOME_UNKNOWN, tra cứu resource bằng external ID hoặc idempotency key, sau đó mới quyết định retry. Nếu provider hỗ trợ idempotency key, giữ cùng key qua mọi lần retry của một operation. Nếu không, phải kiểm tra trạng thái trước khi gửi lại lệnh có side effect.

Khi xử lý đồng bộ và không thể xác minh trong timeout request, broker có thể trả 504 nếu đang đóng vai trò gateway, hoặc 503/500 theo chính sách tương thích. Khi xử lý async, operation tiếp tục ở trạng thái in progress hoặc reconciliation pending; platform không cần nhận một HTTP error mới cho từng lần worker retry.

## 6. Lỗi nghiệp vụ của provider và lỗi tạm thời

Một lỗi provider có thể là vĩnh viễn với request hiện tại hoặc chỉ tạm thời:

| Nhóm | Ví dụ | Phân loại |
|---|---|---|
| Dữ liệu không hợp lệ | Tên database chứa ký tự không hỗ trợ | Lỗi nghiệp vụ, không retry tự động |
| Plan không đáp ứng | Provider không hỗ trợ storage size được yêu cầu | Lỗi validation/422 nếu do lựa chọn người dùng |
| Quota tenant cạn | Đã vượt số database tối đa trong account | 422 nếu quota gắn với request/tenant và không tự giải phóng; 503 nếu là capacity tạm thời của provider |
| Capacity toàn provider | Region hết tài nguyên tạm thời | 503 hoặc async retry |
| Credential hết hạn | Token provider bị thu hồi | Lỗi tích hợp, cần sửa credential; không retry nhanh |
| Rate limit | Quá nhiều API calls | Retry theo Retry-After |
| Resource collision | Tên đã được dùng | Conflict hoặc tìm lại resource theo idempotency/ownership |
| Maintenance | Provider đang bảo trì | 503 hoặc giữ async operation |

Đừng chỉ dựa vào HTTP status. Dùng provider error code, operation type, request parameters, resource state và tài liệu provider để xác định nguyên nhân. Một mã 400 có thể là quota policy, một mã 409 có thể là operation pending, và một mã 404 có thể là resource đã bị xóa.

## 7. Lỗi khi operation đã được tiếp nhận bất đồng bộ

Khi broker trả 202 Accepted, platform đã được thông báo rằng operation đã được tiếp nhận. Những lỗi provider phát sinh sau đó thuộc vòng đời operation, không phải response HTTP ban đầu nữa.

Ví dụ:

    PUT /v2/service_instances/db-prod-17?accepts_incomplete=true

    HTTP/1.1 202 Accepted
    Content-Type: application/json

    {
      "operation": "provision-2026-000891"
    }

Worker sau đó gọi provider và nhận 503. Broker không đổi response đã gửi. Thay vào đó:

- Nếu lỗi tạm thời, giữ operation ở trạng thái nội bộ RETRY_WAIT và tiếp tục trả state in progress khi platform polling.
- Nếu provider nhận lệnh nhưng trả provider operation ID, lưu ID và theo dõi operation phía provider.
- Nếu lỗi vĩnh viễn hoặc hết retry budget, chuyển operation sang terminal failure.
- Nếu kết quả chưa rõ, chạy reconciliation trước khi quyết định succeeded hoặc failed.

Endpoint last_operation trả HTTP 200 khi truy vấn được trạng thái operation, kể cả khi state của operation là failed:

    {
      "state": "failed",
      "description": "The provider rejected the requested configuration."
    }

Các state OSB mà platform hiểu gồm in progress, succeeded và failed. State nội bộ như QUEUED, RETRY_WAIT, PROVIDER_PENDING hoặc RECONCILIATION_REQUIRED cần được ánh xạ sang các giá trị OSB này. Description không nên chứa stack trace hoặc raw provider payload.

## 8. Ma trận ánh xạ theo thao tác OSB

Cùng một provider error có thể cần cách xử lý khác nhau tùy thao tác:

| Thao tác | Provider error | Hành động broker | Kết quả OSB có thể dùng |
|---|---|---|---|
| Catalog | Provider metadata service timeout | Dùng cache hợp lệ nếu policy cho phép; nếu không, báo upstream unavailable | 503/502 |
| Provision | Capacity tạm thời cạn | Retry async nếu được chấp nhận | 202 và last_operation in progress; nếu sync thì 503 |
| Provision | Parameters không được hỗ trợ | Không retry | 422 với error code nghiệp vụ |
| Provision | Timeout sau khi gửi create | Tra cứu theo idempotency key/resource identity | Giữ async hoặc trả lỗi gateway sau khi đối soát |
| Update | Provider báo plan không hỗ trợ | Không retry | 422 PlanChangeNotSupported nếu đúng ngữ nghĩa |
| Update | Provider đang chạy operation khác | Theo dõi hoặc conflict tùy operation ownership | 409 nếu xung đột tại broker; async tiếp tục nếu provider operation thuộc request hiện tại |
| Bind | Provider principal đã tồn tại do retry trước | Xác minh ownership rồi trả lại binding đã lưu | 200/201 theo trạng thái binding và OSB flow |
| Bind | Credential provider sai | Cảnh báo tích hợp | 502/500, không trả 401 platform |
| Unbind | Provider principal không còn tồn tại | Xác minh đúng binding và hoàn tất idempotent | 200/202 theo endpoint contract |
| Deprovision | Resource không còn tồn tại | Xác minh ownership rồi hoàn tất cleanup | 200/202 theo trạng thái operation |
| Deprovision | Provider tạm thời unavailable | Giữ deletion intent, retry | 202 + last_operation nếu async được chấp nhận; nếu không thì 503 |
| Last operation | Provider status endpoint timeout | Giữ operation chưa xác định và retry nội bộ | HTTP 200 với in progress nếu broker còn tin cậy operation; không giả succeeded |

Mã response cụ thể phải tuân theo endpoint và phiên bản OSB API. Bảng này mô tả quyết định phân loại, không phải thay thế toàn bộ đặc tả giao thức.

## 9. Thiết kế provider error classifier

Không nên đặt logic ánh xạ lỗi rải rác trong từng controller. Tách adapter provider, error classifier và OSB error mapper giúp cùng một loại lỗi được xử lý nhất quán.

Một exception nội bộ có thể chứa:

| Thuộc tính | Mục đích |
|---|---|
| provider | Tên provider hoặc adapter |
| providerStatus | HTTP status từ provider nếu có |
| providerCode | Mã lỗi nghiệp vụ do provider trả |
| operationType | PROVISION, UPDATE, BIND, DEPROVISION... |
| retryable | Lỗi có thể retry theo policy hay không |
| outcomeUnknown | Có thể provider đã thực hiện side effect nhưng broker không nhận response |
| retryAfter | Thời gian provider đề nghị chờ |
| safeMessage | Mô tả đã lọc để gửi platform |
| correlationId | Provider request ID hoặc trace reference |

Ví dụ mô hình Java:

    public record ProviderFailure(
            String provider,
            int status,
            String providerCode,
            boolean retryable,
            boolean outcomeUnknown,
            Duration retryAfter,
            String safeMessage
    ) {}

    public record OsbFailure(
            int httpStatus,
            String errorCode,
            String description,
            boolean retryable
    ) {}

Classifier nhận provider failure và ngữ cảnh operation, sau đó chọn hướng xử lý. Việc tạo response HTTP được thực hiện ở coordinator/adapter sau khi trạng thái operation đã được bảo đảm:

    public sealed interface ProviderHandling {
        record RetryAsync(String reason) implements ProviderHandling {}
        record ReturnError(OsbFailure failure) implements ProviderHandling {}
    }

    public ProviderHandling classify(
            ProviderFailure failure,
            OperationType operation,
            boolean acceptsIncomplete) {

        if (failure.outcomeUnknown() && acceptsIncomplete) {
            return new ProviderHandling.RetryAsync(
                    "Provider outcome must be reconciled.");
        }

        if (failure.outcomeUnknown()) {
            return new ProviderHandling.ReturnError(
                    new OsbFailure(
                            504, "ProviderTimeout",
                            "The provider response could not be confirmed.", true));
        }

        if (failure.retryable()) {
            return new ProviderHandling.ReturnError(
                    new OsbFailure(
                            503, "ProviderUnavailable",
                            "The service provider is temporarily unavailable.", true));
        }

        return new ProviderHandling.ReturnError(
                new OsbFailure(
                        422, "ProviderRejectedRequest",
                        failure.safeMessage(), false));
    }

Đây là pseudocode minh họa, không phải quy tắc ánh xạ đầy đủ cho mọi provider. Khi nhận RetryAsync, coordinator phải lưu operation và outbox bền vững trước, rồi adapter mới trả 202 Accepted cùng operation ID theo hợp đồng OSB. Nếu chưa tạo operation bền vững, broker không được trả 202 chỉ vì provider timeout. Các lỗi authentication, configuration, conflict và not found cần được phân loại riêng theo operation và resource state.

## 10. Triển khai trong Spring Cloud Service Broker

Trong ứng dụng Spring, nên tổ chức luồng xử lý thành các lớp:

- Provider client: gọi API provider và chuyển lỗi HTTP/transport thành ProviderFailure.
- Provider adapter: hiểu mã lỗi và ngữ nghĩa riêng của provider.
- Provider error classifier: xác định retryability, outcome unknown và loại lỗi nghiệp vụ.
- OSB error mapper: chuyển lỗi nội bộ thành status và body OSB.
- Operation service: lưu operation, retry schedule và kết quả khi xử lý async.
- Observability: ghi log, metric và trace an toàn.

### 10.1. Chuẩn hóa lỗi tại provider client

Không để exception của HTTP client tràn trực tiếp lên controller. Ví dụ:

    public ProviderFailure toProviderFailure(
            HttpStatusCode status,
            String providerCode,
            Duration retryAfter) {

        int code = status.value();
        boolean retryable =
                code == 429 || code == 500 || code == 502
                || code == 503 || code == 504;

        boolean outcomeUnknown = code == 504;

        return new ProviderFailure(
                "database-provider",
                code,
                providerCode,
                retryable,
                outcomeUnknown,
                retryAfter,
                "The database provider could not complete the request.");
    }

Ví dụ trên chỉ minh họa bước chuẩn hóa ban đầu. Cần bổ sung phân tích body provider, operation type và khả năng side effect. Không phải mọi 500 đều retry an toàn; cũng không phải mọi 504 đều có outcome unknown nếu timeout xảy ra trước khi request được gửi. Provider client nên ghi nhận giai đoạn lỗi: connect, write, read hoặc parse response.

### 10.2. Map sang response OSB

Có thể dùng exception mapper của Spring Cloud Open Service Broker hoặc cơ chế exception handling tương ứng của ứng dụng. Không nên tự đăng ký một handler chung ghi đè mapping chuẩn của framework mà chưa kiểm tra thứ tự xử lý.

Một hàm mapper minh họa:

    ResponseEntity<OsbErrorBody> toResponse(OsbFailure failure) {
        OsbErrorBody body = new OsbErrorBody(
                failure.errorCode(),
                failure.description());

        return ResponseEntity
                .status(failure.httpStatus())
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    public record OsbErrorBody(String error, String description) {}

Với endpoint async, controller/service phải xử lý operation trước: commit operation và outbox, sau đó mới trả 202 cùng operation ID. Với lỗi xảy ra trong worker sau 202, cập nhật operation state thay vì cố gửi một HTTP response lỗi mới đến request đã kết thúc.

### 10.3. Tách lỗi công khai và lỗi nội bộ

Nên có hai bản mô tả:

- Safe description: gửi platform, ngắn gọn và không tiết lộ chi tiết provider.
- Diagnostic detail: ghi nội bộ, có provider code, status, request ID, stack trace đã kiểm soát và operation ID.

Không log Authorization header, password, token, binding credentials, raw request body có secret hoặc toàn bộ provider response. Nếu cần lưu raw response để điều tra, phải mask dữ liệu nhạy cảm và áp dụng retention/access policy.

## 11. Retry, circuit breaker và idempotency

Ánh xạ lỗi phải nhất quán với cách broker retry. Nếu broker trả 503 cho một lỗi tạm thời nhưng đồng thời vẫn đang chạy một worker cho cùng request mà không có operation ID hoặc idempotency, platform có thể retry và tạo side effect trùng.

### 11.1. Quyết định retry

| Loại lỗi | Retry nội bộ? | Retry từ platform? |
|---|---|---|
| Request OSB sai | Không | Chỉ sau khi sửa request |
| Caller 401/403 | Không | Sau khi sửa credential/quyền |
| Provider 429 | Có, theo Retry-After/backoff | Chỉ khi broker chưa nhận async và response cho phép |
| Provider 503 | Có, giới hạn số lần | Có thể thử lại sau nếu broker trả lỗi tạm thời |
| Provider 504/outcome unknown | Đối soát trước khi retry side effect | Không retry mù; dùng idempotency hoặc cùng service instance intent |
| Provider credential invalid | Không retry nhanh | Không; cần sửa cấu hình broker |
| Quota vĩnh viễn cạn | Không | Chỉ sau khi quota thay đổi |
| Provider operation pending | Poll provider operation | Platform poll last_operation |

### 11.2. Exponential backoff và circuit breaker

Retry nên có initial delay, multiplier, max delay, jitter và retry budget. Khi provider lỗi diện rộng, circuit breaker có thể ngăn broker tiếp tục gửi request gây quá tải. Khi circuit mở, broker có thể:

- Giữ operation async ở trạng thái chờ và lên lịch thử lại.
- Từ chối request mới bằng 503 nếu chưa thể tiếp nhận operation.
- Cho phép thao tác đọc từ cache nếu dữ liệu còn hợp lệ và chính sách cho phép.
- Ghi metric về circuit state và số operation bị trì hoãn.

Không retry vô hạn lỗi vĩnh viễn như credential sai hoặc request không hợp lệ.

### 11.3. Idempotency khi kết quả chưa rõ

Timeout sau khi gửi create/delete có thể khiến broker không biết provider đã thực hiện hay chưa. Cần giữ idempotency key ổn định qua retry, lưu provider resource ID khi biết, tra cứu resource theo ownership marker và đối soát trước khi gửi lại lệnh có side effect.

Không dùng request identity làm idempotency key nếu platform có thể tạo một request identity mới cho lần retry. Idempotency nên dựa trên service instance, binding ID, operation ID hoặc khóa nghiệp vụ do broker quản lý.

## 12. Bảo mật và tránh rò rỉ thông tin qua error response

Lỗi provider thường chứa nhiều chi tiết hơn mức platform cần biết. Ví dụ response có thể chứa account ID, project name, endpoint nội bộ, tên cluster, SQL statement hoặc token.

Các nguyên tắc:

- Không trả raw provider message nếu chưa được lọc.
- Không trả stack trace, class name, file path hoặc câu lệnh SQL.
- Không trả token, password, connection string hoặc secret reference.
- Không chuyển provider 401/403 thành caller 401/403 khi credential platform vẫn hợp lệ.
- Dùng error code ổn định và description có thể hiểu được.
- Gắn request identity, operation ID và provider request ID trong log nội bộ.
- Giới hạn quyền đọc log và lưu trữ diagnostic payload.
- Mask resource ID hoặc tenant detail nếu thông tin đó không cần thiết cho platform.

Ví dụ response an toàn:

    {
      "error": "ProviderUnavailable",
      "description": "The service provider is temporarily unavailable. Retry later."
    }

Ví dụ nội dung không nên trả:

    {
      "error": "ProviderError",
      "description": "POST https://internal-db-control.prod.local returned 403 for token eyJ..."
    }

## 13. Quan sát và vận hành

Để phân tích lỗi, broker cần log có cấu trúc với các trường:

| Trường | Mục đích |
|---|---|
| request_identity | Liên kết request OSB nếu platform gửi |
| operation_id | Liên kết công việc async |
| platform_instance_id | Phạm vi platform |
| service_instance_id / binding_id | Đối tượng nghiệp vụ |
| operation_type | PROVISION, UPDATE, BIND, UNBIND, DEPROVISION |
| provider_name | Provider được gọi |
| provider_status | HTTP status upstream |
| provider_error_code | Mã lỗi provider đã chuẩn hóa |
| osb_status / osb_error_code | Kết quả broker trả platform |
| retryable / outcome_unknown | Quyết định xử lý |
| attempt | Số lần gọi provider |
| duration_ms | Thời gian provider call |

Metric hữu ích:

- Số lỗi provider theo provider, operation type và status.
- Tỷ lệ provider timeout, 429 và 5xx.
- Số lần retry trung bình và số operation vượt retry budget.
- Số operation ở RETRY_WAIT hoặc RECONCILIATION_REQUIRED.
- Tỷ lệ OSB 4xx/5xx theo endpoint.
- Circuit breaker state và provider latency.

Không đưa service instance ID, binding ID hoặc operation ID có cardinality cao vào metric label. Dùng log/trace để truy vấn từng request; metric nên tổng hợp theo provider, operation type, status class và error category.

## 14. Kiểm thử ánh xạ lỗi

Kiểm thử cần xác nhận cả status, error body, trạng thái operation và side effect:

1. Request OSB sai JSON trả 400 với error body đúng schema.
2. Caller không xác thực được trả 401; caller không có quyền trả 403.
3. Service/plan/instance/binding không tồn tại trả lỗi not found phù hợp.
4. Provider credential sai không bị ánh xạ nhầm thành caller 401.
5. Provider trả 429; worker tôn trọng Retry-After và không retry liên tục.
6. Provider trả 503; request async được lưu operation trước 202 hoặc request sync trả lỗi tạm thời.
7. Provider timeout sau khi nhận lệnh create; broker đánh dấu outcome unknown và đối soát trước khi tạo lại.
8. Provider 404 khi deprovision đúng resource được xử lý idempotent sau khi xác minh ownership.
9. Provider 404 do sai account không bị coi là deprovision thành công.
10. Provider 409 do operation pending được phân biệt với resource name collision.
11. Provider 400 do adapter tạo payload sai không bị đổ lỗi thành BadRequest của platform.
12. Provider lỗi sau khi broker đã trả 202 cập nhật last_operation thành in progress hoặc failed theo kết quả.
13. last_operation trả HTTP 200 với state failed khi operation kết thúc lỗi.
14. Description không chứa token, password, stack trace hoặc endpoint nội bộ.
15. Retry cùng operation không tạo resource hoặc binding trùng.
16. Circuit breaker mở khi provider lỗi kéo dài và đóng lại sau khi provider phục hồi.
17. Provider response sai schema được phân loại thành upstream error và ghi diagnostic detail nội bộ.

Nên dùng contract test cho error body OSB và integration test với provider giả lập để tạo các tình huống timeout, rate limit, conflict, not found và response lỗi.

## 15. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chuyển nguyên status provider sang platform | Platform hiểu nhầm nguyên nhân hoặc chủ thể lỗi | Phân loại theo lớp lỗi và ngữ nghĩa OSB |
| Provider 401 bị trả thành OSB 401 | Platform xoay credential sai chỗ | Nhận diện lỗi credential tích hợp broker-provider |
| Mọi provider 400 đều thành BadRequest | Platform bị yêu cầu sửa request hợp lệ | Kiểm tra payload do broker tạo và mã lỗi nghiệp vụ |
| Mọi provider 404 đều là thành công | Bỏ sót sai account hoặc sai resource mapping | Xác minh external ID, tenant và operation |
| Mọi provider 409 đều thành ConcurrencyError | Nhầm collision với operation đang chạy | Phân loại conflict theo resource và operation |
| Retry tất cả 5xx vô hạn | Tạo retry storm và làm provider quá tải | Backoff, jitter, retry budget và circuit breaker |
| Retry timeout mà không kiểm tra side effect | Tạo tài nguyên trùng | Outcome unknown, idempotency và reconciliation |
| Trả 202 trước khi lưu operation | Platform polling nhưng không có công việc | Commit operation và outbox trước response |
| Trả raw provider body | Rò rỉ secret và topology | Safe description và diagnostic log riêng |
| Dùng mã lỗi thay đổi theo message provider | Client không thể xử lý ổn định | Dùng error code broker ổn định |
| Trả 500 cho mọi lỗi | Platform không biết lỗi nào có thể retry | Dùng status và error code có ngữ nghĩa |

## 16. Quy trình quyết định ánh xạ lỗi

Khi provider trả lỗi hoặc broker gặp exception, có thể áp dụng trình tự:

1. Xác định request OSB và operation type đang xử lý.
2. Kiểm tra lỗi phát sinh trước hay sau khi broker gọi provider.
3. Xác định caller có xác thực và có quyền với broker hay không.
4. Nếu lỗi từ provider, phân tích status, provider error code, response body đã lọc và giai đoạn request.
5. Xác định side effect đã xảy ra, chưa xảy ra hay kết quả chưa rõ.
6. Phân loại lỗi thành validation, authorization, not found, conflict, transient availability, timeout, quota/capacity hoặc integration defect.
7. Quyết định retry nội bộ, tiếp nhận async, yêu cầu platform sửa request hay chuyển cho người vận hành.
8. Ánh xạ sang HTTP status và error code OSB phù hợp.
9. Tạo safe description và ghi diagnostic detail nội bộ.
10. Nếu đã tiếp nhận async, cập nhật operation state và để platform polling last_operation.

Quy trình này nên được đóng gói thành classifier và mapper có thể kiểm thử độc lập. Mỗi provider adapter chỉ cần chuyển lỗi riêng của provider thành mô hình lỗi chuẩn nội bộ; controller OSB không cần hiểu hàng chục mã lỗi upstream.

## 17. Kết luận

Phân loại lỗi provider thành lỗi OSB phù hợp đòi hỏi broker hiểu cả ngữ nghĩa HTTP, hợp đồng OSB API, loại operation và trạng thái side effect ở provider. Hãy phân biệt lỗi caller với lỗi credential tích hợp, phân loại 4xx/429/5xx theo nguyên nhân thay vì sao chép status, xử lý timeout như một kết quả có thể chưa xác định và dùng idempotency/reconciliation trước khi retry. Khi operation đã được tiếp nhận async, lỗi provider phải được phản ánh qua trạng thái operation và last_operation thay vì thay đổi response HTTP ban đầu. Với Spring Cloud Service Broker, tách provider adapter, error classifier, OSB error mapper và operation service sẽ giúp response nhất quán, an toàn và dễ vận hành trên nhiều provider khác nhau.
