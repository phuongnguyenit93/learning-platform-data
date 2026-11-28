# Phân biệt lỗi xác thực, lỗi phân quyền và lỗi nghiệp vụ

## Mục tiêu và bối cảnh

Service broker nhận request từ platform để đọc catalog, provision, update, deprovision, bind hoặc unbind service instance. Một request có thể thất bại vì caller chưa chứng minh được danh tính, vì caller đã đăng nhập nhưng không có quyền trên tài nguyên, hoặc vì request hợp lệ về mặt truy cập nhưng vi phạm quy tắc nghiệp vụ.

Ba nhóm lỗi này cần được phân biệt rõ:

- **Lỗi xác thực (authentication):** broker không xác minh được caller là ai, chẳng hạn thiếu credentials hoặc credentials không hợp lệ.
- **Lỗi phân quyền (authorization):** broker đã xác thực caller nhưng caller không được phép thực hiện hành động trên broker, tenant, service instance hoặc binding cụ thể.
- **Lỗi nghiệp vụ (business error):** caller đã được xác thực và có quyền, nhưng yêu cầu không thể được thực hiện do dữ liệu, trạng thái, capability, quota hoặc quy tắc vòng đời.

Nếu gộp tất cả thành một lỗi chung, platform khó quyết định có nên gửi lại request, người vận hành khó tìm nguyên nhân và broker có thể vô tình tiết lộ thông tin nhạy cảm. Ví dụ, credentials sai cần xử lý như lỗi 401; tenant không sở hữu instance cần được từ chối theo policy; còn instance đang có operation update có thể là conflict nghiệp vụ.

Bài học này thuộc chương Lỗi và phản hồi của module Spring Cloud Service Broker. Nội dung trình bày cách phân loại lỗi, ánh xạ sang HTTP response và error body của Open Service Broker API (OSB API), tổ chức xử lý trong Spring Security/WebFlux, ghi audit và kiểm thử.

Sau bài học, bạn có thể:

- Phân biệt authentication, authorization và business validation.
- Chọn HTTP status phù hợp với nguyên nhân và hợp đồng OSB API.
- Trả error response có cấu trúc, không làm lộ thông tin nội bộ.
- Xử lý quyền ở cấp platform, tenant, instance và binding.
- Tách lỗi tại security filter khỏi lỗi trong service nghiệp vụ.
- Ánh xạ exception trong ứng dụng Spring WebFlux.
- Thiết kế retry, audit và test cho từng nhóm lỗi.

## 1. Ba câu hỏi cần trả lời theo đúng thứ tự

Trước khi xử lý một request, broker cần trả lời ba câu hỏi:

1. **Caller là ai?** Đây là authentication.
2. **Caller có quyền làm việc này trên đối tượng này không?** Đây là authorization.
3. **Yêu cầu có hợp lệ theo quy tắc của service broker không?** Đây là business validation.

~~~mermaid
flowchart TD
    A[Nhận request OSB API] --> B{Xác thực caller}
    B -->|Thất bại| E401[401 Unauthorized]
    B -->|Thành công| C{Kiểm tra quyền}
    C -->|Không được phép| E403[403 hoặc 404 theo policy]
    C -->|Được phép| D{Kiểm tra nghiệp vụ}
    D -->|Không hợp lệ| EBUS[400 / 409 / 422 theo hợp đồng]
    D -->|Hợp lệ| OK[Thực thi operation]
~~~

Các bước này có thể được triển khai ở nhiều lớp. Authentication thường diễn ra trong security filter chain trước khi controller hoặc handler OSB được gọi. Authorization có thể diễn ra ở filter, method security hoặc application policy service. Business validation thường nằm trong application/domain service vì nó cần biết trạng thái instance, plan, quota và capability.

Không nên dùng một exception hoặc một HTTP status cho cả ba nhóm.

## 2. Lỗi xác thực (authentication)

Authentication xác minh danh tính của caller. Trong tích hợp OSB API, platform thường gửi broker credentials qua HTTP Authorization header theo cơ chế đã cấu hình, phổ biến là HTTP Basic Authentication.

Ví dụ:

~~~http
GET /v2/catalog
Authorization: Basic <encoded-credentials>
X-Broker-API-Version: <supported-version>
~~~

Broker giải mã và kiểm tra credentials theo cấu hình bảo mật. Nếu credentials thiếu, sai, hết hiệu lực hoặc không thể xác minh, request chưa được phép đi vào nghiệp vụ.

### 2.1. Dấu hiệu của lỗi xác thực

| Tình huống | Kết quả |
|---|---|
| Không có Authorization header trong endpoint yêu cầu xác thực | Authentication failure |
| Username hoặc password không đúng | Authentication failure |
| Token hết hạn hoặc chữ ký không hợp lệ | Authentication failure |
| Credentials bị thu hồi | Authentication failure |
| Cơ chế xác thực không thể xác minh danh tính | Authentication failure |

Không được cố tìm service instance hoặc gọi backend sau khi authentication thất bại. Điều đó vừa lãng phí tài nguyên vừa có thể mở ra đường dò dữ liệu.

### 2.2. HTTP 401 Unauthorized

Khi caller không được xác thực, response thường dùng HTTP 401 Unauthorized. Với HTTP Basic, server có thể gửi WWW-Authenticate challenge theo cơ chế đã cấu hình.

Ví dụ error body theo dạng OSB API:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="service-broker"
~~~

~~~json
{
  "description": "Authentication credentials are missing or invalid."
}
~~~

Description nên ngắn gọn. Không trả lời password nào sai, tài khoản có tồn tại hay không, hash credentials, token nội bộ hoặc chi tiết kết nối tới identity provider.

### 2.3. Không nhầm originating identity với authentication

OSB API có thể mang thông tin người dùng khởi tạo request qua header X-Broker-API-Originating-Identity. Header này có thể hữu ích cho audit hoặc policy bổ sung, nhưng không tự chứng minh request đến từ platform đáng tin cậy.

Broker cần:

- Xác thực platform bằng credentials hoặc cơ chế đã đăng ký.
- Chỉ tin originating identity khi nguồn request đã được xác thực và header được bảo vệ theo mô hình tích hợp.
- Parse và validate định dạng identity trước khi dùng.
- Không lấy tenant hoặc quyền từ một header tùy ý.
- Ghi actor đã xác minh vào audit theo chính sách bảo vệ dữ liệu.

Một request có originating identity hợp lệ nhưng broker credentials sai vẫn phải bị từ chối ở bước authentication.

## 3. Lỗi phân quyền (authorization)

Authorization quyết định một caller đã được xác thực có quyền thực hiện hành động cụ thể hay không.

Trong service broker, quyền có thể được kiểm tra ở nhiều cấp:

- Platform có được phép gọi broker này không?
- Platform có được quản lý tenant tương ứng không?
- Tenant có sở hữu service instance này không?
- Caller có quyền deprovision instance hay chỉ được đọc trạng thái?
- Consumer có quyền tạo hoặc thu hồi binding không?
- Operator có quyền chạy tác vụ quản trị trên backend resource không?

Authentication thành công không đồng nghĩa caller được phép truy cập mọi service instance.

### 3.1. Ví dụ lỗi phân quyền

Giả sử platform-A đã xác thực thành công và gửi:

~~~http
DELETE /v2/service_instances/instance-900?service_id=service-postgresql&plan_id=plan-standard
Authorization: Basic <platform-a-credentials>
~~~

Instance instance-900 thuộc platform-B hoặc tenant khác. Platform-A là caller hợp lệ của broker, nhưng không sở hữu instance này và không có quyền quản trị chéo tenant.

Đây là lỗi authorization, không phải authentication. Broker không được xóa resource chỉ vì credentials platform-A hợp lệ.

### 3.2. HTTP 403 và chính sách 404

Khi caller đã xác thực nhưng không có quyền, HTTP 403 Forbidden là lựa chọn trực tiếp.

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
~~~

~~~json
{
  "description": "The authenticated platform is not permitted to perform this operation."
}
~~~

Tuy nhiên, với resource đa tenant, trả 403 có thể tiết lộ rằng một instance ID tồn tại nhưng thuộc tenant khác. Theo threat model, broker có thể trả 404 Not Found cho trường hợp caller không được phép nhìn thấy tài nguyên. Đây là chính sách chống dò tìm resource; cần áp dụng nhất quán để không tạo side channel qua status, body hoặc thời gian phản hồi.

| Tình huống | Phản hồi có thể chọn |
|---|---|
| Caller được xác thực, thiếu quyền trên một endpoint mà sự tồn tại của endpoint được phép công khai | 403 |
| Instance tồn tại nhưng thuộc tenant/platform khác và không được tiết lộ | 404 theo policy |
| Instance không tồn tại | 404 hoặc mã tương ứng theo hợp đồng OSB API |
| Platform không được phép truy cập broker | 403 hoặc từ chối ở tầng đăng ký/credentials tùy mô hình |

Không dùng 404 để che mọi lỗi. Broker vẫn cần audit nội bộ để phân biệt resource không tồn tại với resource tồn tại nhưng caller không có quyền.

### 3.3. Kiểm tra ownership ở cấp tài nguyên

Một truy vấn an toàn nên giới hạn phạm vi ngay từ đầu:

~~~sql
SELECT instance_id,
       service_id,
       current_plan_id,
       tenant_id,
       state
FROM service_instance
WHERE instance_id = :instanceId
  AND platform_id = :authenticatedPlatformId
  AND tenant_id = :authorizedTenantId;
~~~

Nếu không có kết quả, broker có thể trả not found theo policy. Không tìm toàn cục rồi trả dữ liệu instance trước khi xác minh ownership.

Với binding, cần kiểm tra đồng thời instance_id, binding_id, platform và tenant. Không chỉ dựa vào binding ID do client gửi.

### 3.4. Phân quyền theo hành động

Quyền đọc catalog không nhất thiết đồng nghĩa quyền provision hoặc deprovision. Nếu broker có nhiều loại platform/client hoặc administrative API, nên định nghĩa quyền theo hành động:

| Hành động | Quyền cần kiểm tra |
|---|---|
| GET catalog | Được phép đọc catalog |
| PUT provision | Được phép tạo instance trong tenant |
| PATCH update | Được phép thay đổi instance và plan |
| DELETE deprovision | Được phép thu hồi instance |
| PUT binding | Được phép cấp quyền cho consumer |
| DELETE binding | Được phép thu hồi đúng binding |
| Reconciliation/admin | Quyền vận hành riêng, có audit |

Không nên suy ra quyền deprovision từ quyền tạo instance nếu policy sản phẩm tách hai hành động.

## 4. Lỗi nghiệp vụ (business errors)

Business error xuất hiện sau khi caller đã được xác thực và có quyền, nhưng yêu cầu không thỏa mãn quy tắc của broker hoặc trạng thái tài nguyên.

Ví dụ:

- service_id không khớp với service đã lưu cho instance.
- plan_id không khớp plan hiện tại.
- Parameters thiếu trường bắt buộc hoặc sai miền giá trị.
- Plan không hỗ trợ update.
- Instance đang ở trạng thái không cho phép thao tác.
- Binding đã bị thu hồi.
- Tenant đã hết quota.
- Request dùng lại instance ID với payload khác.
- Một operation không tương thích đang chạy.

Đây không phải lỗi credentials. Không yêu cầu caller đăng nhập lại để sửa một tham số sai hoặc đợi operation hiện tại hoàn tất.

### 4.1. Phân loại lỗi nghiệp vụ theo nguyên nhân

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Cú pháp/dữ liệu request | JSON sai, thiếu query bắt buộc | Sửa request |
| Validation parameters | storage âm hoặc sai kiểu | Sửa parameters |
| Identity mismatch | service_id/plan_id không khớp bản ghi | Kiểm tra ID và trạng thái |
| State conflict | Instance đang UPDATING | Chờ operation hoặc xử lý theo policy |
| Capability | Plan không hỗ trợ update | Chọn thao tác/plan được hỗ trợ |
| Quota/policy | Tenant vượt giới hạn | Giảm yêu cầu hoặc điều chỉnh quota |
| Backend transient | Provider timeout hoặc 503 | Retry có kiểm soát hoặc operation async |
| Backend permanent | Resource name bị policy từ chối | Sửa cấu hình hoặc yêu cầu operator |

### 4.2. HTTP status cho business error

Không có một status duy nhất cho mọi lỗi nghiệp vụ. Broker cần chọn mã phù hợp với ngữ nghĩa request và hợp đồng OSB API đang hỗ trợ.

| HTTP status | Dùng khi nào |
|---|---|
| 400 Bad Request | Request thiếu field, sai định dạng hoặc parameters không hợp lệ theo schema |
| 404 Not Found | Resource không tồn tại hoặc được che theo policy ownership |
| 409 Conflict | Request xung đột với trạng thái hiện tại, instance ID đã được dùng cho identity khác hoặc operation không tương thích đang chạy |
| 422 Unprocessable Entity | Request có cú pháp hợp lệ nhưng không thể xử lý theo điều kiện nghiệp vụ; OSB API cũng dùng 422 cho trường hợp AsyncRequired khi broker cần async nhưng platform không chấp nhận incomplete operation |
| 429 Too Many Requests | Rate limit hoặc quota tạm thời được biểu diễn như giới hạn request; có thể kèm Retry-After theo policy |
| 503 Service Unavailable | Backend hoặc dependency tạm thời không sẵn sàng |
| 500 Internal Server Error | Lỗi nội bộ không dự kiến, không thể ánh xạ thành lỗi request cụ thể |

Các mã cụ thể còn phụ thuộc endpoint và phiên bản OSB API. Không thay thế response contract của OSB bằng một mapping tùy tiện. Ví dụ, với async operation, nếu platform đã chấp nhận incomplete operation và broker trả 202, lỗi backend xảy ra sau đó phải được lưu vào operation và phản ánh qua last_operation; không thể đổi response HTTP ban đầu đã gửi thành 500.

### 4.3. Ví dụ lỗi validation

Request gửi storage_gb bằng chuỗi:

~~~json
{
  "parameters": {
    "storage_gb": "one hundred"
  }
}
~~~

Response có thể là:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

~~~json
{
  "description": "Parameter 'storage_gb' must be an integer."
}
~~~

Description nên chỉ ra trường cần sửa, không kèm stack trace hoặc dữ liệu nhạy cảm.

### 4.4. Ví dụ state conflict

Nếu instance đang UPDATING và platform gửi deprovision trong khi broker không hỗ trợ hủy update ngay:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
~~~

~~~json
{
  "description": "The service instance has an operation in progress."
}
~~~

Platform hoặc operator có thể chờ operation hiện tại hoàn tất rồi thử lại theo hợp đồng. Broker không được gọi hai workflow backend xung đột.

## 5. Error response của OSB API

OSB API dùng error response có cấu trúc JSON với trường description để mô tả lỗi. Ví dụ tổng quát:

~~~json
{
  "description": "A concise explanation of the error."
}
~~~

Một số client có thể hiển thị description cho người dùng hoặc ghi vào log. Vì vậy, nội dung cần:

- Dễ hiểu và đủ cụ thể để xử lý.
- Không chứa stack trace, SQL hoặc tên lớp nội bộ.
- Không tiết lộ credentials, token, connection string hoặc secret.
- Không xác nhận sự tồn tại của resource thuộc tenant khác nếu policy yêu cầu che.
- Không đưa thông tin backend nhạy cảm vào response.
- Ổn định để platform có thể phân loại lỗi.

Broker có thể lưu error_code nội bộ để metrics và audit, nhưng không nên giả định platform hiểu mã riêng đó nếu nó không thuộc response contract được công bố.

### 5.1. Error code nội bộ và HTTP status

Nên giữ mã lỗi nghiệp vụ ổn định bên trong ứng dụng:

| Internal code | Nhóm | HTTP mapping gợi ý |
|---|---|---|
| AUTHENTICATION_FAILED | Authentication | 401 |
| PLATFORM_NOT_ALLOWED | Authorization | 403 hoặc 404 theo policy |
| TENANT_ACCESS_DENIED | Authorization | 403 hoặc 404 theo policy |
| INSTANCE_NOT_FOUND | Resource lookup | 404 hoặc mã OSB phù hợp |
| SERVICE_ID_MISMATCH | Business validation | 400/409 theo ngữ nghĩa và endpoint |
| PLAN_ID_MISMATCH | Business validation | 400/409 theo ngữ nghĩa và endpoint |
| INVALID_PARAMETERS | Business validation | 400 |
| INSTANCE_STATE_CONFLICT | Business state | 409 |
| QUOTA_EXCEEDED | Business policy | 400/422/429 tùy loại quota và hợp đồng |
| BACKEND_TEMPORARY_FAILURE | Dependency | 503 hoặc async operation failed |
| INTERNAL_ERROR | Internal | 500 |

Đây là bảng thiết kế nội bộ, không phải danh sách error code bắt buộc của OSB API. Mỗi mapping cần được kiểm tra theo operation và API version.

### 5.2. Không trả chi tiết exception trực tiếp

Không làm như sau:

~~~json
{
  "description": "org.postgresql.util.PSQLException: password authentication failed for user broker_admin at db-prod.internal"
}
~~~

Response này tiết lộ driver, username và hostname nội bộ.

Thay vào đó:

~~~json
{
  "description": "The broker could not complete the requested operation because the backend service is temporarily unavailable."
}
~~~

Chi tiết đầy đủ hơn có thể được lưu trong log bảo vệ, liên kết bằng correlation ID hoặc operation ID. Cần che secret trước khi ghi log.

## 6. Tổ chức xử lý trong Spring Security và WebFlux

Trong Spring WebFlux, security filter chain thường xử lý authentication trước khi request tới handler của Spring Cloud Open Service Broker. Do đó, lỗi authentication và một phần lỗi authorization có thể phát sinh ngoài controller.

Một cấu hình khái niệm:

~~~java
@Bean
SecurityWebFilterChain brokerSecurity(
        ServerHttpSecurity http,
        ServerAuthenticationEntryPoint osbAuthenticationEntryPoint,
        ServerAccessDeniedHandler osbAccessDeniedHandler) {

    return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/v2/**").authenticated()
                    .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(exceptions -> exceptions
                    .authenticationEntryPoint(
                            osbAuthenticationEntryPoint
                    )
                    .accessDeniedHandler(
                            osbAccessDeniedHandler
                    )
            )
            .build();
}
~~~

Đây là cấu hình minh họa. Cần điều chỉnh theo cơ chế credentials, endpoint health/management, TLS termination và phiên bản Spring Security của ứng dụng. Không sao chép cấu hình mà không kiểm tra các route thật sự cần bảo vệ.

### 6.1. AuthenticationEntryPoint và AccessDeniedHandler

Hai thành phần này có trách nhiệm khác nhau:

- ServerAuthenticationEntryPoint: tạo response khi caller chưa được xác thực.
- ServerAccessDeniedHandler: tạo response khi caller đã xác thực nhưng bị từ chối quyền.

Có thể dùng chung một helper để ghi error body OSB:

~~~java
private Mono<Void> writeOsbError(
        ServerWebExchange exchange,
        HttpStatus status,
        String description) {

    byte[] body = objectMapper.writeValueAsBytes(
            Map.of("description", description)
    );

    exchange.getResponse().setStatusCode(status);
    exchange.getResponse().getHeaders()
            .setContentType(MediaType.APPLICATION_JSON);

    DataBuffer buffer =
            exchange.getResponse().bufferFactory().wrap(body);

    return exchange.getResponse().writeWith(
            Mono.just(buffer)
    );
}
~~~

Helper minh họa này cần xử lý serialization exception và bảo đảm response chưa được commit. Authentication entry point có thể thêm WWW-Authenticate theo cơ chế HTTP Basic. Không để một exception trong helper biến lỗi 401/403 thành lỗi 500.

### 6.2. Business exception trong application service

Business validation nên được biểu diễn bằng exception hoặc result type có mã rõ ràng:

~~~java
public class InstanceStateConflictException
        extends RuntimeException {

    public InstanceStateConflictException(String message) {
        super(message);
    }
}
~~~

Application service có thể ném exception khi state transition không hợp lệ:

~~~java
public Mono<Void> deprovision(String instanceId) {
    return instanceRepository.findById(instanceId)
            .switchIfEmpty(Mono.error(
                    new InstanceNotFoundException()
            ))
            .flatMap(instance -> {
                if (instance.state() != InstanceState.READY) {
                    return Mono.error(
                            new InstanceStateConflictException(
                                    "Instance is not ready for deprovision"
                            )
                    );
                }

                return deprovisionWorkflow.start(instance);
            });
}
~~~

Đây là pseudocode cho domain flow. Trong hệ thống đa tenant, repository lookup phải giới hạn platform/tenant scope hoặc application service phải xác minh ownership trước khi trả lỗi phân biệt. Không đọc toàn cục rồi trả thông tin instance cho caller chưa được phép.

### 6.3. Exception mapping ở WebFlux

Có thể dùng @RestControllerAdvice hoặc cơ chế exception translation được Spring Cloud Open Service Broker hỗ trợ để ánh xạ business exception thành response phù hợp. Tuy nhiên:

- Lỗi trong security filter chain cần AuthenticationEntryPoint/AccessDeniedHandler.
- Lỗi trong handler/application layer có thể được xử lý bởi exception advice hoặc framework hook.
- Không tạo một controller advice ghi đè response của mọi exception thành 400.
- Không để lỗi backend timeout bị ánh xạ thành validation error.
- Không trả exception message gốc nếu nó chứa dữ liệu nội bộ.

Ví dụ bảng mapping:

~~~java
public ErrorResponse mapBusinessException(Throwable error) {
    if (error instanceof InvalidParametersException) {
        return new ErrorResponse(
                HttpStatus.BAD_REQUEST,
                "Request parameters are invalid."
        );
    }

    if (error instanceof InstanceStateConflictException) {
        return new ErrorResponse(
                HttpStatus.CONFLICT,
                "The service instance has an incompatible operation in progress."
        );
    }

    if (error instanceof BackendUnavailableException) {
        return new ErrorResponse(
                HttpStatus.SERVICE_UNAVAILABLE,
                "The backend service is temporarily unavailable."
        );
    }

    return new ErrorResponse(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "The broker could not complete the request."
    );
}
~~~

Đoạn code là minh họa cho mapper nội bộ. Với response thực tế, cần dùng kiểu error response và exception translation mà phiên bản Spring Cloud Open Service Broker cung cấp, để giữ đúng body contract OSB.

## 7. Kiểm tra authorization trong application layer

Một số quyền không thể quyết định chỉ bằng URL hoặc role chung. Ví dụ, platform đã xác thực nhưng chỉ được phép quản lý các instance thuộc tenant của nó.

Có thể tổ chức policy service:

~~~java
public Mono<Void> authorizeDeprovision(
        AuthenticatedPlatform platform,
        ServiceInstance instance) {

    if (!platform.platformId().equals(instance.platformId())) {
        return Mono.error(new ResourceAccessDeniedException());
    }

    if (!platform.canManageTenant(instance.tenantId())) {
        return Mono.error(new ResourceAccessDeniedException());
    }

    return Mono.empty();
}
~~~

Đây là pseudocode. Quyền thực tế có thể dựa trên platform registration, tenant mapping, OAuth scope hoặc policy engine.

Application service nên thực hiện theo thứ tự:

1. Nhận identity đã được security layer xác thực.
2. Tìm resource trong phạm vi caller hoặc xác minh ownership.
3. Kiểm tra quyền đối với hành động cụ thể.
4. Validate service_id, plan_id và trạng thái nghiệp vụ.
5. Thực hiện state transition.
6. Gọi backend hoặc ghi operation.

Không dùng parameters do client gửi làm bằng chứng ownership. Không lấy tenant ID từ header không được xác thực.

## 8. Phân biệt business error với lỗi dependency

Một request có thể hợp lệ nhưng backend không sẵn sàng. Đây không phải lỗi authentication, authorization hay validation.

Ví dụ:

- Cloud provider trả 503.
- SDK timeout.
- Database backend từ chối kết nối tạm thời.
- Queue chưa sẵn sàng.
- Secret manager bị gián đoạn.

Cách phản hồi phụ thuộc request đã được chấp nhận đồng bộ hay bất đồng bộ:

| Thời điểm xảy ra lỗi | Xử lý |
|---|---|
| Trước khi operation được chấp nhận | Có thể trả 503 hoặc lỗi tạm thời phù hợp |
| Sau khi trả 202 cho async operation | Lưu operation FAILED hoặc RETRY_WAIT và phản ánh qua last_operation |
| Trong cleanup nền không ảnh hưởng kết quả giao thức đã hoàn tất | Giữ cleanup task nội bộ, retry và cảnh báo |
| Lỗi vĩnh viễn từ backend do cấu hình | Đánh dấu lỗi cuối cùng và cung cấp mô tả an toàn |

Không trả 401 khi backend credentials của broker hết hạn. Caller platform vẫn có thể đã được xác thực đúng; lỗi nằm ở credential mà broker dùng để gọi provider. Không trả 403 cho platform chỉ vì backend service account thiếu quyền.

## 9. Retry và khả năng xử lý của client

HTTP status giúp platform quyết định bước tiếp theo. Vì vậy mapping lỗi cần phân biệt lỗi có thể sửa bằng request mới với lỗi tạm thời có thể retry.

| Nhóm lỗi | Hành vi client gợi ý |
|---|---|
| 400 | Sửa request hoặc parameters; không retry nguyên trạng |
| 401 | Kiểm tra credentials và xác thực lại |
| 403 | Kiểm tra quyền hoặc tenant scope; không retry liên tục |
| 404 | Xác minh resource ID hoặc quyền nhìn thấy resource |
| 409 | Chờ operation xung đột hoặc giải quyết trạng thái hiện tại |
| 422 AsyncRequired | Gửi lại với accepts_incomplete=true nếu platform hỗ trợ async |
| 429 | Tôn trọng Retry-After và giảm tốc độ |
| 5xx | Retry có backoff nếu thao tác idempotent và hợp đồng cho phép |

Không khuyến khích platform retry liên tục lỗi 401, 403 hoặc validation. Broker cũng không nên retry lỗi authorization như thể đó là lỗi mạng.

Với operation bất đồng bộ, platform polling last_operation là cách theo dõi kết quả đã được chấp nhận. Không gửi lại provision chỉ vì operation vẫn đang in progress.

## 10. Audit, log và bảo vệ thông tin

Để điều tra một request bị từ chối, broker cần lưu được nhóm lỗi và actor mà không làm lộ dữ liệu.

Các trường audit hữu ích:

- correlation_id hoặc trace_id.
- platform_id đã xác thực.
- tenant_id đã xác minh.
- actor/originating identity nếu có và đã được tin cậy.
- operation type và resource ID theo chính sách.
- error category: AUTHENTICATION, AUTHORIZATION, BUSINESS hoặc DEPENDENCY.
- internal error code.
- HTTP status.
- thời điểm và quyết định.

Không ghi:

- Authorization header.
- Password, bearer token hoặc private key.
- Connection string có credentials.
- Raw parameters chứa secret.
- Stack trace vào response cho platform.
- Resource metadata thuộc tenant khác.

Có thể trả một correlation ID để operator tra log, nhưng không đưa thông tin nhạy cảm vào ID đó. Cần bảo đảm log có access control và retention phù hợp.

### 10.1. Metric theo nhóm lỗi

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| broker_authentication_failure_total | Số request authentication thất bại |
| broker_authorization_denied_total | Số request bị từ chối quyền |
| broker_business_validation_failure_total | Số lỗi validation nghiệp vụ |
| broker_state_conflict_total | Số state conflict |
| broker_backend_failure_total | Số lỗi dependency |
| broker_http_response_total | Số response theo status và endpoint |
| broker_async_operation_failed_total | Số operation async thất bại |

Không dùng username, tenant ID hoặc instance ID làm label có cardinality cao. Dùng label giới hạn như endpoint, error_category, status và provider.

## 11. Kiểm thử ba nhóm lỗi

Một bộ test cần xác nhận cả status code, error body và việc broker có tạo side effect hay không.

| Kịch bản | Nhóm lỗi | Kết quả mong đợi |
|---|---|---|
| Thiếu Authorization header | Authentication | 401, không vào application service |
| Password broker sai | Authentication | 401, không gọi repository/backend |
| Platform hợp lệ nhưng tenant không sở hữu instance | Authorization | 403 hoặc 404 theo policy, không gọi backend |
| Platform có quyền đọc nhưng không có quyền quản trị | Authorization | Từ chối hành động |
| Parameters sai kiểu | Business | 400, không tạo operation/backend resource |
| service_id hoặc plan_id không khớp | Business | Từ chối theo mapping đã công bố |
| Instance đang update và nhận deprovision không tương thích | Business | 409 hoặc điều phối theo policy |
| Tenant vượt quota | Business policy | Lỗi nghiệp vụ phù hợp, không gọi backend |
| Provider timeout | Dependency | 503 hoặc operation async chuyển retry/failed |
| Async không được chấp nhận nhưng broker yêu cầu async | Protocol/business condition | 422 AsyncRequired theo OSB API |
| Lỗi bất ngờ trong broker | Internal | 500 với description an toàn |

### 11.1. Test authentication và authorization

Test security filter chain cần xác nhận:

- Không có credentials thì request nhận 401.
- Credentials sai thì request nhận 401.
- Credentials hợp lệ nhưng thiếu quyền thì request nhận 403 hoặc 404 theo policy.
- Lỗi ở security filter không gọi service nghiệp vụ.
- Response có content type JSON và body đúng dạng OSB error.

### 11.2. Test business mapping

Dùng application service test hoặc WebTestClient để xác nhận:

- InvalidParametersException được ánh xạ đúng.
- State conflict không bị biến thành 500.
- BackendUnavailableException không bị biến thành 400.
- Response không chứa class name, stack trace, SQL hoặc secret.
- Request bị từ chối không tạo outbox event hoặc gọi backend.

### 11.3. Test anti-enumeration

Tạo một instance thuộc tenant khác và một instance không tồn tại. Gửi cùng request từ caller không có quyền nhìn thấy cả hai. Nếu policy dùng 404 để che existence, response nên tương đương về status và nội dung; tránh tạo khác biệt rõ ràng qua body hoặc thời gian xử lý.

## 12. Những lỗi thiết kế thường gặp

- **Trả 401 cho mọi lỗi:** làm client hiểu sai lỗi phân quyền và lỗi nghiệp vụ.
- **Trả 403 cho credentials sai:** làm mờ ranh giới authentication.
- **Coi broker credentials hợp lệ là quyền trên mọi tenant:** dẫn đến IDOR và xóa nhầm tài nguyên.
- **Dùng originating identity header thay authentication:** caller có thể giả mạo thông tin actor nếu nguồn không được xác minh.
- **Trả 404 không nhất quán:** tạo side channel tiết lộ resource.
- **Map mọi business exception thành 400:** bỏ qua state conflict, async-required và dependency failure.
- **Trả stack trace trong description:** lộ cấu trúc nội bộ và thông tin backend.
- **Retry 401/403 vô hạn:** tăng tải và che giấu lỗi cấu hình.
- **Gọi backend trước authorization:** có thể tạo side effect cho caller không có quyền.
- **Chỉ kiểm tra quyền ở controller:** worker hoặc đường gọi nội bộ có thể bỏ qua policy.
- **Để controller advice ghi đè security response:** lỗi filter chain không được ánh xạ đúng.
- **Không phân biệt lỗi sync và async:** response ban đầu có thể không phản ánh đúng trạng thái operation.

## 13. Quy trình thiết kế error handling cho broker

Khi thêm endpoint hoặc thao tác lifecycle, hãy thực hiện:

1. Xác định cơ chế authentication của platform.
2. Xác định quyền ở cấp broker, platform, tenant và resource.
3. Xác định các business invariant và state transition.
4. Xây internal error code ổn định cho từng nguyên nhân.
5. Ánh xạ lỗi sang HTTP status theo endpoint và phiên bản OSB API.
6. Trả body có description ngắn gọn, an toàn.
7. Tách Security filter error handler khỏi business exception mapper.
8. Kiểm tra ownership trước khi gọi backend.
9. Phân loại dependency failure và quyết định sync/async retry.
10. Ghi audit, correlation ID và metric không chứa secret.
11. Viết test cho 401, 403/404, business 4xx, 5xx và anti-enumeration.
12. Tài liệu hóa hành vi để platform operator biết khi nào sửa request, quyền hoặc chờ operation.

## Kết luận

Authentication, authorization và business error trả lời ba câu hỏi khác nhau: caller là ai, caller có quyền làm việc này không, và yêu cầu có hợp lệ theo trạng thái cùng quy tắc dịch vụ không. Authentication failure thường ánh xạ sang 401; authorization thường dùng 403 hoặc 404 theo chính sách chống dò tài nguyên; business error cần được phân loại theo cú pháp, validation, state conflict, capability, quota và lỗi dependency.

Trong Spring Cloud Service Broker, hãy xử lý authentication tại Spring Security, kiểm tra ownership và quyền ở application/policy layer, rồi validate quy tắc nghiệp vụ trước khi gọi backend. Dùng error response OSB API có description an toàn, internal error code ổn định, audit và test riêng cho từng nhóm. Cách phân tách này giúp platform phản ứng đúng, ngăn truy cập trái phép và giữ cho vòng đời provision, update, deprovision cùng binding có thể vận hành và chẩn đoán rõ ràng.
