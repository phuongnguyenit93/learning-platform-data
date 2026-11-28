# Ánh xạ exception của framework sang mã HTTP và nội dung lỗi

Trong Spring Cloud service broker, lỗi có thể phát sinh từ request HTTP, validation, trạng thái service instance, quota, database nội bộ, provider API hoặc quá trình xử lý reactive của Reactor. Platform giao tiếp với broker theo Open Service Broker API (OSB API), vì vậy broker cần chuyển những lỗi ở tầng Java và framework thành HTTP status cùng error response đúng hợp đồng.

Một exception trong Java không tự quyết định HTTP status mà platform nhận được. Nếu mọi exception đều bị chuyển thành HTTP 500, platform không phân biệt được request sai, tài nguyên không tồn tại, xung đột trạng thái hay provider tạm thời không khả dụng. Ngược lại, nếu broker trả HTTP 200 với nội dung mô tả lỗi, platform có thể hiểu thao tác đã thành công.

Bài học trình bày cách xây dựng quy tắc ánh xạ exception sang mã HTTP và nội dung lỗi, phân biệt lỗi của framework với lỗi nghiệp vụ, giữ nguyên nguyên nhân gốc, xử lý lỗi trong Spring WebFlux/Reactor và bảo đảm response phù hợp với OSB API. Nội dung cũng làm rõ cách phản ánh lỗi của thao tác bất đồng bộ qua last_operation sau khi request ban đầu đã nhận HTTP 202.

## 1. Vì sao cần một lớp ánh xạ lỗi?

Một service broker có nhiều lớp xử lý:

1. Spring WebFlux nhận và giải mã HTTP request.
2. Spring Cloud Open Service Broker kiểm tra request theo contract OSB.
3. Handler chuyển request thành command nghiệp vụ.
4. Application service kiểm tra tenant, service, plan, quota và trạng thái instance.
5. Repository đọc hoặc ghi dữ liệu.
6. Provider adapter gọi API nhà cung cấp.
7. Broker trả response thành công hoặc lỗi về platform.

Mỗi lớp có thể ném một loại exception khác nhau. Ví dụ:

- Request thiếu trường bắt buộc có thể tạo lỗi giải mã hoặc validation.
- Service ID không được catalog hỗ trợ tạo lỗi nghiệp vụ.
- Instance đang có update khác tạo xung đột trạng thái.
- Tenant hết quota tạo lỗi chính sách.
- Provider trả HTTP 429 tạo lỗi rate limit.
- Provider timeout sau khi nhận lệnh tạo database tạo kết quả chưa xác định.

Lớp ánh xạ lỗi chuyển những tình huống này thành một contract ổn định:

~~~text
Framework / Domain / Provider exception
                |
                v
        Error classification
                |
                v
        OSB error mapping
                |
                v
   HTTP status + error + description
                |
                v
             Platform
~~~

Lớp này giúp:

- Giữ HTTP status nhất quán giữa các endpoint.
- Phân biệt lỗi client, lỗi nghiệp vụ và lỗi hạ tầng.
- Tránh để exception hoặc SDK provider rò rỉ ra response.
- Giữ thông tin nguyên nhân gốc cho log và điều tra.
- Hỗ trợ platform quyết định sửa request, retry hoặc dừng thao tác.
- Duy trì cùng một cách xử lý lỗi khi thêm provider hoặc handler mới.

Không nên để từng handler tự chọn status và tự viết error body. Những quyết định đó cần được quản lý tập trung, có kiểm thử và phù hợp với phiên bản framework OSB đang sử dụng.

## 2. Cấu trúc error response của OSB API

Error response của OSB API thường có hai trường:

~~~json
{
  "error": "Conflict",
  "description": "A conflicting operation is already in progress"
}
~~~

Ý nghĩa:

| Trường | Vai trò |
|---|---|
| error | Mã hoặc tên lỗi để client nhận diện |
| description | Mô tả ngắn gọn nguyên nhân hoặc cách hiểu lỗi |

HTTP status nằm trong status line của response, không phải một trường thay thế cho error. Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
~~~

Body cần được serialize theo contract OSB mà endpoint và phiên bản API đang sử dụng hỗ trợ.

Trường error nên ổn định, có thể được client hoặc hệ thống vận hành phân loại. Description nên ngắn gọn, không chứa stack trace, credential, raw response của provider hoặc thông tin nhạy cảm. Không dùng thông điệp exception nội bộ làm public description một cách trực tiếp.

Một số lỗi OSB có mã hoặc quy tắc đặc thù theo endpoint và phiên bản API. Do đó, broker cần kiểm tra đúng đặc tả OSB và phiên bản Spring Cloud Open Service Broker đang dùng; không nên tự tạo mã lỗi tùy ý cho một tình huống mà contract đã quy định.

## 3. Phân loại lỗi trước khi chọn HTTP status

Bước đầu tiên không phải chọn status code. Trước hết cần hiểu lỗi thuộc nhóm nào và ý nghĩa nghiệp vụ của nó.

| Nhóm | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Request | JSON sai, thiếu field, parameters không hợp lệ | Client có thể sửa request không? |
| Authentication | Broker credentials không hợp lệ | Client đã được xác thực chưa? |
| Authorization | Tenant không được phép truy cập instance | Caller có quyền thực hiện thao tác không? |
| Not found | Instance hoặc binding không tồn tại | Đối tượng được yêu cầu có tồn tại trong phạm vi này không? |
| Conflict | Instance đang có operation xung đột | Client có thể thử lại sau khi trạng thái thay đổi không? |
| Quota | Tenant đã hết tài nguyên được phép | Có thể chọn plan khác hoặc giải phóng quota không? |
| Capability | Service không hỗ trợ bind hoặc update | Thao tác có được broker công bố và triển khai không? |
| Dependency | Provider tạm thời không sẵn sàng | Có thể retry có giới hạn không? |
| Unknown outcome | Provider timeout sau khi nhận lệnh | Tác dụng phụ đã xảy ra hay chưa? |
| Internal | Lỗi lập trình hoặc dữ liệu không nhất quán | Cần điều tra và xử lý nội bộ nào? |

Một loại exception có thể cần mapping khác nhau tùy endpoint và trạng thái. Ví dụ provider trả 404 khi broker truy vấn tài nguyên đã lưu mapping có thể có nghĩa resource bị xóa ngoài hệ thống. Đây không nhất thiết là lỗi 404 trực tiếp của request platform; broker có thể phải đánh dấu trạng thái UNKNOWN và chạy reconciliation.

Vì vậy, nên phân loại theo ý nghĩa nghiệp vụ thay vì sao chép HTTP status từ provider.

## 4. Thiết kế error taxonomy dùng chung

Một enum hoặc sealed hierarchy giúp chuẩn hóa lỗi giữa application service và provider adapter.

Ví dụ:

~~~java
public enum BrokerFailureKind {
    INVALID_REQUEST,
    UNAUTHENTICATED,
    FORBIDDEN,
    RESOURCE_NOT_FOUND,
    CONFLICT,
    QUOTA_EXCEEDED,
    UNSUPPORTED_OPERATION,
    ASYNC_REQUIRED,
    PROVIDER_UNAVAILABLE,
    PROVIDER_REJECTED,
    PROVIDER_TIMEOUT_UNKNOWN,
    INTERNAL
}
~~~

Mỗi lỗi có thể mang thêm mã nội bộ, thông điệp an toàn, khả năng retry và nguyên nhân gốc:

~~~java
public class BrokerFailure extends RuntimeException {

    private final BrokerFailureKind kind;
    private final String code;
    private final boolean retryable;

    public BrokerFailure(
            BrokerFailureKind kind,
            String code,
            boolean retryable,
            String safeMessage,
            Throwable cause) {
        super(safeMessage, cause);
        this.kind = kind;
        this.code = code;
        this.retryable = retryable;
    }

    public BrokerFailureKind kind() {
        return kind;
    }

    public String code() {
        return code;
    }

    public boolean retryable() {
        return retryable;
    }
}
~~~

Mô hình này không phụ thuộc HTTP. Application service có thể ném BrokerFailure mà không cần biết framework sẽ trả 409 hay 503.

Lớp OSB error mapper chịu trách nhiệm chuyển BrokerFailureKind sang exception hoặc response model mà framework hỗ trợ. Khi thay đổi cách triển khai HTTP, quy tắc nghiệp vụ vẫn có thể được giữ nguyên.

## 5. Ánh xạ các exception phổ biến của Spring

Spring và Spring WebFlux có nhiều exception phát sinh trong quá trình giải mã, binding, validation và định tuyến request. Cần nhận diện chúng và quyết định liệu chúng có phải lỗi OSB hay lỗi HTTP chung.

Một số tình huống thường gặp:

| Nguồn exception | Tình huống | Hướng phân loại |
|---|---|---|
| JSON decoding exception | Body không phải JSON hợp lệ | INVALID_REQUEST |
| WebExchangeBindException | Binding hoặc validation lỗi trong WebFlux | INVALID_REQUEST |
| ServerWebInputException | Input không thể chuyển đổi hoặc không hợp lệ | INVALID_REQUEST |
| ConstraintViolationException | Vi phạm constraint ở tầng validation | INVALID_REQUEST hoặc lỗi nội bộ tùy vị trí |
| AccessDeniedException | Không đủ quyền | FORBIDDEN |
| AuthenticationException | Xác thực thất bại | UNAUTHENTICATED |
| DataAccessException | Database broker lỗi | INTERNAL hoặc dependency failure tùy nguyên nhân |
| OptimisticLockingFailureException | Cập nhật đồng thời xung đột | CONFLICT hoặc retry nội bộ |
| WebClientResponseException | Provider trả HTTP error | Chuẩn hóa theo status và ngữ nghĩa provider |
| TimeoutException | Dependency không phản hồi đúng hạn | Dependency failure hoặc UNKNOWN outcome |

Tên class và hành vi cụ thể có thể khác theo phiên bản Spring và stack Servlet/WebFlux. Ví dụ, lỗi binding trong Spring MVC và WebFlux có thể dùng class khác nhau. Hãy kiểm tra exception thực tế của phiên bản ứng dụng và test đường đi qua framework.

Không nên ánh xạ mọi DataAccessException thành 400. Lỗi kết nối database broker thường là lỗi phía server. Tương tự, không nên trả 404 cho mọi NoSuchElementException; chỉ những trường hợp đối tượng nghiệp vụ thực sự không tồn tại mới nên được phân loại not found.

## 6. Phân biệt exception của framework và exception nghiệp vụ

Exception framework thường mô tả vấn đề kỹ thuật ở tầng web hoặc persistence. Exception nghiệp vụ mô tả một điều kiện mà service broker hiểu rõ.

Ví dụ:

- WebExchangeBindException: framework không bind được request theo kiểu dữ liệu hoặc validation.
- InstanceNotFoundException: broker không tìm thấy service instance.
- PlanNotSupportedException: service hoặc plan không nằm trong catalog.
- QuotaExceededException: tenant không còn quota.
- ProviderTimeoutUnknownException: chưa xác định provider đã thực hiện thao tác hay chưa.

Nên chuyển lỗi framework sang lỗi nghiệp vụ khi cần bổ sung ngữ nghĩa. Ví dụ, repository trả Mono.empty; application service biết đó là instance không tồn tại và phát InstanceNotFoundException.

Không nên để application service phụ thuộc vào mọi exception của WebFlux. Handler hoặc adapter ở ranh giới HTTP có thể chuyển lỗi giải mã request thành lỗi invalid request trước khi gọi nghiệp vụ.

Tương tự, provider adapter nên chuyển SDK exception thành loại lỗi provider chuẩn hóa. Application service không nên phải kiểm tra từng class exception riêng của mọi SDK.

## 7. Bảng mapping HTTP status tham khảo

Bảng dưới đây là hướng dẫn thiết kế. Cần đối chiếu contract OSB và quy tắc cụ thể của endpoint trước khi triển khai.

| HTTP status | Ý nghĩa chung | Ví dụ trong broker |
|---|---|---|
| 400 Bad Request | Request không hợp lệ | JSON sai, tham số sai định dạng |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực | Platform credentials không hợp lệ |
| 403 Forbidden | Đã xác thực nhưng không có quyền | Tenant không được thao tác instance |
| 404 Not Found | Đối tượng hoặc endpoint không tồn tại | Instance/binding không tìm thấy theo semantics endpoint |
| 409 Conflict | Trạng thái hiện tại xung đột | Một operation thay đổi tài nguyên đang chạy |
| 410 Gone | Tài nguyên không còn khả dụng theo semantics endpoint | Tài nguyên đã bị thu hồi và contract cho phép biểu diễn như vậy |
| 422 Unprocessable Entity | Request đúng cú pháp nhưng không thể xử lý theo điều kiện giao thức/nghiệp vụ | Async operation bắt buộc nhưng client không chấp nhận, khi OSB contract quy định |
| 500 Internal Server Error | Lỗi không dự kiến phía broker | Bug hoặc invariant bị vi phạm |
| 502 Bad Gateway | Broker nhận phản hồi không hợp lệ từ upstream | Provider trả response không thể xử lý, theo chính sách gateway của ứng dụng |
| 503 Service Unavailable | Broker hoặc dependency tạm thời không sẵn sàng | Provider outage hoặc broker đang bảo trì |
| 504 Gateway Timeout | Upstream không phản hồi trong thời hạn | Provider request timeout, khi kết quả và contract cho phép dùng status này |

Không phải mọi status trong bảng đều được dùng cho mọi endpoint OSB. Cần ưu tiên mã và response mà đặc tả quy định. Không dùng 404 để che giấu mọi lỗi authorization nếu contract hoặc chính sách bảo mật yêu cầu phân biệt 403. Cũng không dùng 500 cho request sai chỉ vì exception chưa được phân loại.

## 8. Error code và description cần ổn định

Trường error trong body nên là mã ổn định, không nên lấy tên class Java làm contract public.

Ví dụ tốt hơn:

~~~json
{
  "error": "QuotaExceeded",
  "description": "The tenant has reached the storage quota for this service plan."
}
~~~

Thay vì:

~~~json
{
  "error": "com.example.broker.quota.TenantStorageLimitException",
  "description": "TenantStorageLimitException at QuotaService.java:142"
}
~~~

Tên class có thể đổi khi refactor. Stack trace và dòng code không có ý nghĩa với platform, đồng thời làm lộ cấu trúc nội bộ.

Nên duy trì danh mục error code, ý nghĩa và cách xử lý:

| Error code nội bộ | Ý nghĩa | Retry |
|---|---|---|
| INVALID_PARAMETERS | Parameters không hợp lệ | Không |
| INSTANCE_NOT_FOUND | Instance không tồn tại | Không |
| OPERATION_CONFLICT | Có thao tác xung đột | Sau khi trạng thái thay đổi |
| TENANT_QUOTA_EXCEEDED | Tenant hết quota | Sau khi giải phóng hoặc đổi plan |
| PROVIDER_RATE_LIMITED | Provider giới hạn request | Có backoff |
| PROVIDER_UNAVAILABLE | Provider tạm thời không sẵn sàng | Có giới hạn |
| PROVIDER_RESULT_UNKNOWN | Chưa xác định tác dụng phụ đã xảy ra | Đối soát trước retry |
| INTERNAL_ERROR | Lỗi nội bộ không dự kiến | Không retry mù quáng |

Nếu OSB contract yêu cầu một error code cụ thể cho tình huống, hãy dùng đúng code đó trong response. Danh mục nội bộ có thể phong phú hơn, nhưng không được làm sai mã public mà platform mong đợi.

## 9. Tập trung ánh xạ trong một Error Mapper

Một mapper tập trung giúp tránh lặp switch-case trong từng handler. Ví dụ mô hình:

~~~java
public record OsbErrorMapping(
        int httpStatus,
        String error,
        String description) {
}

@Component
public class OsbErrorMapper {

    public OsbErrorMapping map(BrokerFailure failure) {
        return switch (failure.kind()) {
            case INVALID_REQUEST ->
                    new OsbErrorMapping(
                            400,
                            "BadRequest",
                            failure.getMessage());

            case UNAUTHENTICATED ->
                    new OsbErrorMapping(
                            401,
                            "Unauthorized",
                            "Authentication failed");

            case FORBIDDEN ->
                    new OsbErrorMapping(
                            403,
                            "Forbidden",
                            "The caller is not allowed to perform this operation");

            case RESOURCE_NOT_FOUND ->
                    new OsbErrorMapping(
                            404,
                            "NotFound",
                            "The requested resource was not found");

            case CONFLICT ->
                    new OsbErrorMapping(
                            409,
                            "Conflict",
                            failure.getMessage());

            case QUOTA_EXCEEDED ->
                    new OsbErrorMapping(
                            409,
                            "QuotaExceeded",
                            "The tenant quota has been exceeded");

            case PROVIDER_UNAVAILABLE ->
                    new OsbErrorMapping(
                            503,
                            "ServiceUnavailable",
                            "The service provider is temporarily unavailable");

            default ->
                    new OsbErrorMapping(
                            500,
                            "InternalError",
                            "The broker could not complete the request");
        };
    }
}
~~~

Đây là ví dụ minh họa về cấu trúc mapping, không phải API có sẵn của Spring Cloud Open Service Broker. Trong ứng dụng thực tế, không nhất thiết tự tạo HTTP response trực tiếp từ mapper. Có thể mapper trả về một exception chuyên biệt của framework để framework đảm nhiệm serialization theo contract OSB.

Cũng cần lưu ý failure.getMessage() chỉ được dùng làm description nếu message đã được thiết kế an toàn. Nếu exception có thể chứa dữ liệu provider hoặc request nhạy cảm, hãy dùng public message cố định theo error code.

Không để default branch che giấu một lỗi OSB đặc thù. Những trường hợp như async-required hoặc maintenance/version conflict phải được ánh xạ theo contract đúng phiên bản nếu broker hỗ trợ chúng.

## 10. Dùng exception model mà Spring Cloud Open Service Broker hỗ trợ

Spring Cloud Open Service Broker có cơ chế tích hợp request/response và xử lý exception cho OSB endpoint. Các exception cụ thể, constructor, status mapping và cách serialize có thể thay đổi theo release.

Khi triển khai:

1. Xác định chính xác phiên bản Spring Cloud Open Service Broker của dự án.
2. Kiểm tra exception types mà release đó cung cấp cho các tình huống OSB phổ biến.
3. Ưu tiên dùng exception framework khi nó diễn tả đúng lỗi theo contract.
4. Với lỗi nghiệp vụ riêng, tạo adapter chuyển BrokerFailure sang exception framework phù hợp.
5. Để framework xử lý response nếu cơ chế mặc định đã đáp ứng contract.
6. Chỉ viết custom exception handler khi có trường hợp chưa được framework bao phủ và đã xác minh không ghi đè handler OSB mặc định.

Không nên giả định class hoặc method từ một release khác luôn tồn tại. Hãy đối chiếu API của dependency thực tế. Không cần để domain layer import class exception của framework; có thể giữ việc chuyển đổi ở lớp tích hợp OSB.

Ví dụ luồng chuyển đổi:

~~~text
QuotaExceededException
        |
        v
BrokerFailure(QUOTA_EXCEEDED)
        |
        v
OsbFrameworkExceptionAdapter
        |
        v
Framework-specific OSB exception
        |
        v
Framework error handler
        |
        v
HTTP 4xx + OSB error body
~~~

Cách này giữ ranh giới giữa nghiệp vụ và framework. Nếu sau này đổi phiên bản framework, phần adapter là nơi cần rà soát thay vì toàn bộ service nghiệp vụ.

## 11. Xử lý lỗi validation của request

Validation có thể diễn ra ở nhiều cấp:

- JSON decoding: body không đúng cú pháp.
- Type binding: chuỗi không chuyển được thành số hoặc enum.
- Bean Validation: field thiếu, rỗng hoặc vi phạm constraint.
- OSB semantic validation: service ID, plan ID hoặc tổ hợp trường không hợp lệ.
- Domain validation: request không phù hợp trạng thái hoặc chính sách broker.

Ví dụ DTO:

~~~java
public record ProvisionParameters(
        @NotBlank String databaseName,
        @Min(1) @Max(100) Integer maxConnections) {
}
~~~

Nếu validation thất bại, broker nên trả lỗi request phù hợp và chỉ rõ field nào không hợp lệ ở mức đủ dùng. Không trả stack trace hoặc thông tin về class DTO.

Cần tránh để validation ở tầng HTTP trở thành cơ chế duy nhất. Client có thể gọi trực tiếp endpoint mà không qua giao diện platform. Application service vẫn phải kiểm tra plan, quota, tenant và điều kiện nghiệp vụ trước khi thực hiện tác dụng phụ.

Nếu một parameters field hợp lệ về kiểu nhưng vượt giới hạn plan, đó là lỗi nghiệp vụ hoặc quota chứ không đơn thuần là lỗi JSON decoding.

## 12. Phân biệt authentication và authorization

Authentication xác minh caller là ai. Authorization xác định caller được phép làm gì.

| Tình huống | Phân loại |
|---|---|
| Basic credentials hoặc token sai | Authentication |
| Credential bị thiếu khi endpoint yêu cầu | Authentication |
| Platform đã xác thực nhưng tenant không sở hữu instance | Authorization |
| Platform không có quyền thực hiện deprovision | Authorization |
| Broker credential của chính nó gọi provider bị từ chối | Lỗi dependency/configuration phía broker |

Không nên trả cùng một thông điệp chi tiết cho mọi trường hợp. Nhưng cũng cần cân nhắc nguy cơ tiết lộ sự tồn tại của resource thuộc tenant khác. Chính sách có thể trả cùng một response bên ngoài cho instance không tồn tại và instance không thuộc quyền truy cập, nếu đó là yêu cầu bảo mật của hệ thống.

Lỗi xác thực provider không phải lỗi xác thực của platform. Ví dụ broker dùng service account cloud bị hết hạn credential; platform đã xác thực hợp lệ nhưng broker không thể truy cập provider. Trường hợp này cần được ghi nhận như dependency/configuration failure và không nên trả 401 cho platform.

## 13. Chuẩn hóa lỗi từ Provider Adapter

Mỗi provider có HTTP status và error code riêng. Adapter nên chuyển chúng thành taxonomy chung trước khi application service quyết định hành vi.

Ví dụ:

~~~java
return providerClient.createResource(command)
        .onErrorMap(WebClientResponseException.class, error -> {
            if (error.getStatusCode().value() == 429) {
                return new BrokerFailure(
                        BrokerFailureKind.PROVIDER_UNAVAILABLE,
                        "PROVIDER_RATE_LIMITED",
                        true,
                        "Provider rate limit reached",
                        error);
            }

            if (error.getStatusCode().is5xxServerError()) {
                return new BrokerFailure(
                        BrokerFailureKind.PROVIDER_UNAVAILABLE,
                        "PROVIDER_TEMPORARY_FAILURE",
                        true,
                        "Provider is temporarily unavailable",
                        error);
            }

            return new BrokerFailure(
                    BrokerFailureKind.PROVIDER_REJECTED,
                    "PROVIDER_REQUEST_REJECTED",
                    false,
                    "Provider rejected the request",
                    error);
        });
~~~

Ví dụ trên chỉ minh họa; cần phân loại riêng 401/403, 404, 409, 429, 5xx và timeout theo API provider. Không phải mọi 5xx đều có thể retry an toàn. Đặc biệt, timeout sau POST create có thể là kết quả UNKNOWN vì provider đã nhận lệnh nhưng response bị mất.

Adapter cần giữ exception gốc làm cause cho log nội bộ, nhưng không trả raw response body hoặc endpoint provider cho platform. Application service quyết định retry, reconciliation hoặc đánh dấu operation cần can thiệp.

## 14. Xử lý lỗi trong Reactor Mono

Reactor truyền lỗi bằng onError. Các operator có mục đích khác nhau:

| Operator | Công dụng | Lưu ý |
|---|---|---|
| onErrorMap | Chuyển exception sang loại lỗi khác | Giữ cause và error category |
| onErrorResume | Chuyển sang publisher thay thế | Chỉ dùng khi có fallback hợp lệ |
| doOnError | Ghi log hoặc metric | Không tiêu thụ lỗi |
| onErrorReturn | Trả giá trị mặc định | Có thể che lỗi nếu dùng sai |
| retryWhen | Retry theo điều kiện | Chỉ retry thao tác an toàn |
| onErrorComplete | Kết thúc không phát lỗi | Không phù hợp để che lỗi OSB |

Ví dụ chuyển lỗi provider:

~~~java
return providerClient.getResource(resourceId)
        .onErrorMap(
                ProviderAccessException.class,
                error -> new BrokerFailure(
                        BrokerFailureKind.PROVIDER_UNAVAILABLE,
                        "PROVIDER_ACCESS_FAILED",
                        true,
                        "Provider is temporarily unavailable",
                        error));
~~~

Ví dụ ghi metric nhưng vẫn để lỗi truyền tiếp:

~~~java
return applicationService.execute(command)
        .doOnError(error ->
                metrics.recordFailure("provision", error));
~~~

doOnError không tạo HTTP response. Lỗi tiếp tục tới framework hoặc error adapter.

Không dùng onErrorReturn để trả một response provision rỗng khi provider thất bại. Platform có thể hiểu thao tác đã hoàn tất. Cũng không dùng onErrorComplete để bỏ qua lỗi deprovision; broker cần biết tài nguyên đã thực sự được thu hồi hay chưa.

## 15. Mono.empty và lỗi không tìm thấy tài nguyên

Mono.empty biểu diễn publisher hoàn tất mà không phát giá trị. Nó không đồng nghĩa với not found hoặc lỗi.

Ví dụ repository:

~~~java
return instanceRepository.findById(instanceId)
        .switchIfEmpty(Mono.error(
                new InstanceNotFoundException(instanceId)));
~~~

Nếu bỏ switchIfEmpty, pipeline có thể kết thúc mà không có response nghiệp vụ. Cần quyết định rõ repository trả empty có nghĩa là không tồn tại, còn service nào có thể hợp lệ với kết quả rỗng.

Không nên biến mọi empty thành 404 ở tầng global vì một số truy vấn có thể dùng empty để biểu diễn "không có dữ liệu tùy chọn". Chuyển đổi phải được thực hiện tại nơi hiểu ngữ nghĩa dữ liệu.

## 16. Lỗi đồng bộ và lỗi sau HTTP 202

Với thao tác đồng bộ, broker chưa trả response cuối cùng. Nếu handler phát onError, framework có thể chuyển lỗi thành HTTP error response cho request hiện tại.

Với thao tác bất đồng bộ, broker đã trả HTTP 202 Accepted và operation ID. Request ban đầu đã kết thúc ở cấp giao thức. Nếu worker gặp lỗi sau đó, broker không thể đổi response 202 đã gửi thành HTTP 500.

Luồng đúng:

1. Broker lưu operation và job bền vững.
2. Broker trả 202 cùng operation ID.
3. Worker gọi provider.
4. Provider hoặc worker thất bại.
5. Worker lưu operation state FAILED và error code an toàn.
6. Platform gọi last_operation.
7. Broker trả state failed theo contract OSB.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker
    participant W as Worker
    participant V as Provider
    P->>B: Provision request
    B->>B: Persist operation
    B-->>P: 202 Accepted + operation ID
    W->>V: Create resource
    V--xW: Provider error
    W->>B: Persist FAILED + safe description
    P->>B: GET last_operation
    B-->>P: state = failed
~~~

Không trả HTTP 500 cho request ban đầu sau khi 202 đã được gửi. Lỗi của operation phải được lưu và trả qua endpoint theo dõi. Ngược lại, nếu broker không thể lưu operation hoặc enqueue công việc trước khi trả 202, request tiếp nhận chưa thành công và cần được xử lý như lỗi đồng bộ.

## 17. Nội dung lỗi của last_operation

Response last_operation có schema riêng, khác với error response của request HTTP bị lỗi. Khi operation đang chạy, broker trả state tương ứng; khi hoàn tất hoặc thất bại, broker trả state cuối cùng và description phù hợp.

Ví dụ:

~~~json
{
  "state": "failed",
  "description": "The provider could not create the requested database"
}
~~~

Description nên giúp platform hoặc operator hiểu kết quả ở mức cần thiết. Không nên đưa raw stack trace, SQL, secret, private endpoint hoặc response body của provider vào đây.

Cần phân biệt:

- Request GET last_operation lỗi vì operation ID không tồn tại: đây là lỗi của request truy vấn, được ánh xạ thành HTTP error theo contract.
- Operation tồn tại và state là failed: đây là kết quả nghiệp vụ của thao tác trước đó, được trả trong last_operation response.
- Operation đang UNKNOWN vì provider timeout: không được vội đánh dấu failed nếu provider có thể đã thực hiện tác dụng phụ.

## 18. Không ghi đè OSB error handler mặc định

Spring WebFlux hỗ trợ các cơ chế như @ExceptionHandler, @ControllerAdvice và WebExceptionHandler. Tuy nhiên, service broker còn có xử lý riêng cho OSB request/response.

Một global handler bắt mọi Throwable và trả JSON tùy ý có thể:

- Làm mất cấu trúc error response OSB.
- Thay status mà framework đã chọn.
- Chuyển lỗi validation thành 500.
- Trả body không đúng schema.
- Che mất lỗi gốc hoặc gây lộ chi tiết nội bộ.

Trước khi thêm handler tùy chỉnh, cần kiểm tra cơ chế mặc định của phiên bản Spring Cloud Open Service Broker. Chỉ xử lý những loại lỗi chưa được framework bao phủ, giữ đúng content type, schema và HTTP status.

Nếu ứng dụng có API quản trị ngoài OSB, có thể cần handler riêng cho API đó. Phạm vi route và thứ tự ưu tiên phải được kiểm tra để không làm ảnh hưởng endpoint broker.

## 19. Public description và internal diagnostic

Thông tin dùng cho platform và thông tin dùng để điều tra không nên là một chuỗi duy nhất.

Ví dụ mô hình:

~~~java
public record ErrorDetails(
        String publicCode,
        String publicDescription,
        String internalCode,
        String correlationId,
        Throwable cause) {
}
~~~

Public description:

- Ngắn và dễ hiểu.
- Không chứa secret.
- Không chứa stack trace.
- Không tiết lộ tên account hoặc endpoint nội bộ.
- Có thể chứa correlation ID để operator tra cứu nếu chính sách cho phép.

Internal diagnostic:

- Lưu exception cause.
- Lưu provider code đã chuẩn hóa.
- Lưu operation ID và instance ID.
- Ghi stack trace ở log có kiểm soát truy cập.
- Redact token, password, private key và parameters nhạy cảm.

Không log toàn bộ request body chỉ để tìm nguyên nhân. Có thể log các field định danh không nhạy cảm cùng correlation ID, sau khi đánh giá chính sách dữ liệu.

## 20. Retry và status code không phải một quyết định

HTTP status không tự xác định thao tác có thể retry hay không. Broker cần phân loại lỗi và trạng thái tác dụng phụ.

| Tình huống | Hành vi |
|---|---|
| Request validation sai | Client sửa request; không retry nguyên trạng |
| Authentication thất bại | Sửa credential; không retry vô hạn |
| Quota hết | Thử lại sau khi quota thay đổi hoặc chọn plan khác |
| Conflict do operation đang chạy | Chờ trạng thái thay đổi rồi thử lại theo contract |
| Provider 429 | Retry có backoff và tôn trọng giới hạn |
| Provider 503 trước khi nhận lệnh | Có thể retry có giới hạn |
| Timeout sau lệnh create | Tra cứu operation/resource trước khi retry |
| Lỗi nội bộ không xác định | Ghi log, điều tra; không retry mù quáng |

Không nên đặt retry tự động ở global error handler. Retry thuộc chính sách của application service hoặc provider adapter, nơi hiểu thao tác có idempotent hay không.

Với provision, update hoặc delete có tác dụng phụ, cần idempotency key, operation journal hoặc reconciliation trước khi gửi lại lệnh.

## 21. Kiểm thử ánh xạ lỗi

Kiểm thử nên có hai cấp:

**Cấp Reactor/service:** xác minh exception và tín hiệu onError.

~~~java
StepVerifier.create(service.provision(command))
        .expectErrorMatches(error ->
                error instanceof BrokerFailure
                && ((BrokerFailure) error).kind()
                        == BrokerFailureKind.QUOTA_EXCEEDED)
        .verify();
~~~

**Cấp HTTP/OSB:** gọi endpoint thực tế và kiểm tra:

- HTTP status.
- Content-Type.
- Body có error và description theo contract.
- Không có stack trace hoặc secret.
- Status khác nhau đúng với lỗi request, authorization, conflict và dependency.
- Lỗi async sau 202 xuất hiện qua last_operation.

Ví dụ kiểm tra body lỗi:

~~~json
{
  "error": "QuotaExceeded",
  "description": "The tenant quota has been exceeded"
}
~~~

StepVerifier không chứng minh HTTP mapping đúng. Cần kiểm thử tích hợp bằng WebTestClient hoặc công cụ tương đương trên đúng phiên bản framework. Nên có test cho cả lỗi do framework, domain và provider adapter.

## 22. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Mọi lỗi đều thành 500 | Không có error taxonomy | Phân loại lỗi trước khi ánh xạ |
| Request sai nhưng trả 200 | Exception bị thay bằng response mặc định | Giữ onError và dùng error response OSB |
| Mono.empty làm endpoint trả response rỗng | Không chuyển empty thành lỗi nghiệp vụ khi cần | Dùng switchIfEmpty |
| Provider 429 bị trả 500 | Không chuẩn hóa lỗi provider | Map rate limit và retry có giới hạn |
| Provider 401 bị trả 401 cho platform | Nhầm credential provider với credential platform | Phân loại lỗi dependency phía broker |
| Response chứa stack trace | Dùng exception message thô | Tách public description và internal diagnostic |
| Lỗi worker không hiển thị trên platform | Không lưu trạng thái operation FAILED | Cập nhật journal và last_operation |
| Global handler trả body sai schema | Ghi đè OSB exception handler | Giữ cơ chế mặc định hoặc giới hạn custom handler |
| Retry create gây duplicate resource | Retry dựa trên status mà không xét idempotency | Dùng idempotency và reconciliation |
| Not found bị dùng cho mọi lỗi authorization | Mapping không xét tenant/security semantics | Áp dụng chính sách phân quyền và che giấu resource có chủ đích |

## 23. Quy trình triển khai error mapping

Khi bổ sung hoặc thay đổi error mapping, có thể làm theo trình tự:

1. Liệt kê exception phát sinh ở WebFlux, framework OSB, domain, repository và provider adapter.
2. Định nghĩa taxonomy lỗi nghiệp vụ chung.
3. Xác định HTTP status và error code theo contract OSB cho từng trường hợp.
4. Tạo exception adapter chuyển lỗi domain sang exception framework khi phù hợp.
5. Chuẩn hóa provider error và giữ nguyên cause.
6. Dùng Reactor operator đúng mục tiêu, không nuốt lỗi ngoài ý muốn.
7. Kiểm tra framework error handler mặc định trước khi thêm global handler.
8. Xác định public description và internal diagnostic riêng.
9. Với asynchronous operation, lưu failure state và phục vụ qua last_operation.
10. Kiểm thử exception signal bằng StepVerifier.
11. Kiểm thử HTTP response và JSON body trên endpoint thực tế.
12. Kiểm thử timeout, retry, cancellation và trường hợp provider result UNKNOWN.

Khi nâng cấp Spring Cloud Open Service Broker, cần chạy lại contract test cho các exception và response mapping. Không nên giả định status hoặc serialization không thay đổi giữa các release.

## 24. Checklist rà soát

- [ ] Đã phân biệt exception của framework, domain, persistence và provider.
- [ ] Có taxonomy lỗi dùng chung.
- [ ] HTTP status được chọn theo ngữ nghĩa và contract OSB.
- [ ] Error code ổn định, không dùng tên class Java làm public contract.
- [ ] Description ngắn, an toàn và không chứa secret.
- [ ] Framework exception được chuyển qua adapter tương thích với release đang dùng.
- [ ] Provider status không bị sao chép máy móc thành status OSB.
- [ ] Mono.empty được xử lý theo ngữ nghĩa tại đúng lớp.
- [ ] onErrorMap, onErrorResume, doOnError và retryWhen được dùng đúng mục đích.
- [ ] Không dùng onErrorReturn/onErrorComplete để che lỗi vòng đời.
- [ ] Không ghi đè OSB error handler mặc định ngoài phạm vi cần thiết.
- [ ] Lỗi đồng bộ được phản ánh trong HTTP response.
- [ ] Lỗi sau 202 được lưu và trả qua last_operation.
- [ ] Timeout không rõ kết quả được xử lý bằng idempotency/reconciliation.
- [ ] Public response tách khỏi internal diagnostic.
- [ ] Có test cho Reactor signal và HTTP contract.
- [ ] Đã kiểm tra content type, status, body và dữ liệu nhạy cảm.

Ánh xạ exception của framework sang mã HTTP và nội dung lỗi là ranh giới giữa implementation Java và hợp đồng OSB mà platform tiêu thụ. Một broker đáng tin cậy phân loại lỗi theo ý nghĩa nghiệp vụ, giữ nguyên nguyên nhân gốc cho điều tra, trả status và error body đúng contract, đồng thời bảo vệ thông tin nội bộ. Với thao tác đồng bộ, lỗi được phản ánh trong HTTP response hiện tại; với thao tác đã được chấp nhận bằng 202, lỗi phát sinh sau đó phải được lưu trong operation journal và trả qua last_operation. Khi các quy tắc này được tập trung và kiểm thử, broker có thể xử lý lỗi nhất quán ngay cả khi thêm provider, handler hoặc phiên bản framework mới.

