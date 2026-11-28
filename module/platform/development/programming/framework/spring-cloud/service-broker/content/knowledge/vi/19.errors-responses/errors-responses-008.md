# Mô tả lỗi có thể chẩn đoán mà không lộ credentials hoặc dữ liệu khách hàng

Một service broker cần trả lời rõ ràng khi yêu cầu provision, update, bind, unbind hoặc deprovision thất bại. Người vận hành cần biết bước nào gặp lỗi, lỗi có thể thử lại hay cần sửa cấu hình, và phải tra cứu ở đâu. Nền tảng cũng cần một phản hồi phù hợp để quyết định retry hoặc hiển thị thông báo cho người dùng.

Tuy nhiên, thông tin hữu ích cho vận hành không đồng nghĩa với việc đưa toàn bộ exception, request body hoặc response của provider vào HTTP response. Các nội dung đó có thể chứa password, token, connection string, dữ liệu cá nhân, tên tài nguyên nội bộ hoặc thông tin về tenant khác. Trong module **SPRING_CLOUD_SERVICE_BROKER**, cần thiết kế hai lớp thông tin riêng: **chẩn đoán nội bộ có kiểm soát** và **mô tả lỗi an toàn dành cho bên gọi**.

Bài học này trình bày cách phân loại lỗi, ánh xạ lỗi theo Open Service Broker API (OSB API), thiết kế error code và correlation ID, ghi structured log có redaction, bảo vệ dữ liệu đa tenant, xử lý lỗi từ provider và kiểm thử để bảo đảm credentials cùng dữ liệu khách hàng không xuất hiện trong response, log hoặc trace.

## 1. Chẩn đoán được lỗi mà không tiết lộ dữ liệu nhạy cảm

Khi một request thất bại, có nhiều nhóm người cần thông tin khác nhau:

- **Nền tảng gọi broker** cần biết request không hợp lệ, tài nguyên không tồn tại, thao tác đang xung đột hay lỗi tạm thời.
- **Người dùng dịch vụ** cần biết hành động tiếp theo, chẳng hạn kiểm tra plan, chờ operation hoặc liên hệ hỗ trợ.
- **Đội vận hành broker** cần xác định operation, provider, bước xử lý và nguyên nhân kỹ thuật.
- **Đội bảo mật** cần biết lỗi có liên quan đến xác thực, phân quyền, truy cập chéo tenant hoặc rò rỉ dữ liệu hay không.

Một thông báo duy nhất không thể phục vụ mọi mục đích. Nếu trả nguyên exception message cho client, thông tin nội bộ có thể bị lộ. Nếu chỉ trả “Internal error”, nền tảng và người vận hành khó xử lý.

Hãy tách thông tin thành hai lớp:

| Lớp thông tin | Người đọc | Nội dung phù hợp |
|---|---|---|
| Public error description | Platform hoặc consumer | Mô tả ngắn, an toàn, có hướng xử lý |
| Internal diagnostic event | Đội vận hành có quyền | Error code, exception class, operation ID, provider request reference, step, retry classification và stack trace đã kiểm soát |

Ví dụ, provider trả lỗi xác thực kèm request body có username và endpoint. Public response có thể nói: “Broker không thể hoàn tất yêu cầu với nhà cung cấp. Hãy thử lại sau; nếu lỗi tiếp tục, cung cấp mã tham chiếu hỗ trợ.” Log nội bộ có thể ghi provider status, exception class, adapter, operation ID và provider request ID đã được kiểm tra, nhưng không ghi credential hoặc request body.

Nguyên tắc quan trọng: người gọi cần biết **điều gì đã xảy ra ở mức có thể hành động**, còn chi tiết nhạy cảm chỉ được lưu ở hệ thống nội bộ có kiểm soát quyền truy cập.

## 2. Hợp đồng lỗi của Open Service Broker API

OSB API định nghĩa các endpoint và hành vi phản hồi cho vòng đời service instance và binding. Khi request không thể được xử lý, broker cần trả HTTP status phù hợp và một error response theo hợp đồng API.

Dạng body lỗi phổ biến của OSB API là object JSON có trường description:

~~~json
{
  "description": "The requested service instance is not available."
}
~~~

Description cần đủ rõ để nền tảng hiểu kết quả, nhưng không chứa stack trace, tên class Java, SQL, token, password, connection string hoặc nội dung thô từ provider.

Không nên tự ý thêm một schema lỗi riêng rồi giả định mọi platform OSB đều hiểu. Nếu cần mã lỗi nội bộ hoặc mã mở rộng theo nền tảng, hãy lưu trong log hoặc dùng extension đã được hai phía thống nhất. Response chuẩn vẫn phải tương thích với phiên bản OSB API mà broker công bố.

### Chọn HTTP status theo ngữ nghĩa

Bảng dưới đây là hướng dẫn thiết kế. Status thực tế cần tuân theo endpoint, phiên bản OSB API, điều kiện request và quy tắc của platform tích hợp.

| Nhóm tình huống | HTTP status thường phù hợp | Mô tả an toàn |
|---|---:|---|
| JSON hoặc query không hợp lệ | 400 Bad Request | Request không đúng định dạng hoặc thiếu trường bắt buộc |
| Thiếu hoặc sai thông tin xác thực | 401 Unauthorized | Broker không xác thực được caller |
| Caller không có quyền | 403 Forbidden | Caller không được phép thực hiện thao tác |
| Instance hoặc binding không tồn tại trong phạm vi được phép | 404 Not Found | Không tìm thấy tài nguyên được yêu cầu |
| Request xung đột với trạng thái hiện tại | 409 Conflict | Tài nguyên đang có operation không tương thích |
| Parameters hợp lệ về cú pháp nhưng không đáp ứng policy | 422 Unprocessable Entity | Giá trị yêu cầu không được service hoặc plan hỗ trợ |
| Broker gặp lỗi không dự kiến | 500 Internal Server Error | Broker không thể hoàn tất yêu cầu |
| Provider tạm thời không khả dụng | 502/503 theo kiến trúc và contract | Nhà cung cấp tạm thời không thể xử lý |
| Provider hoặc dependency timeout | 504 Gateway Timeout khi phù hợp với vai trò gateway | Không nhận được kết quả trong thời gian cho phép |

Không dùng status thành công chỉ để báo rằng broker đã ghi request vào queue, trừ khi endpoint và OSB API cho phép asynchronous operation. Với các thao tác hỗ trợ accepts_incomplete, broker phải tuân thủ response async và last_operation đúng hợp đồng. Với endpoint không hỗ trợ async theo cách đó, hãy trả lỗi thích hợp thay vì tự tạo một protocol riêng.

### Không tiết lộ việc tài nguyên của tenant khác có tồn tại

Khi caller yêu cầu một instance không thuộc tenant của họ, trả lời “instance tồn tại nhưng bạn không có quyền” có thể làm lộ thông tin. Tùy chính sách bảo mật và hợp đồng platform, broker có thể trả cùng một phản hồi không tìm thấy cho cả hai trường hợp: không tồn tại và không thuộc phạm vi caller.

Quy tắc này cần được áp dụng nhất quán cho instance, binding, secret và provider resource reference.

## 3. Phân loại lỗi nội bộ trước khi tạo response

Không nên ánh xạ mọi exception thành HTTP 500. Broker cần phân loại lỗi theo nguyên nhân và khả năng xử lý.

Một taxonomy nội bộ có thể gồm:

| Error category | Ví dụ | Retryable? | Hướng xử lý |
|---|---|---|---|
| REQUEST_INVALID | Thiếu field, sai kiểu dữ liệu | Không | Sửa request |
| AUTHENTICATION_FAILED | Token không hợp lệ | Không tự retry | Xác thực lại caller |
| AUTHORIZATION_DENIED | Caller không có quyền | Không | Kiểm tra role và policy |
| RESOURCE_NOT_FOUND | Instance hoặc binding không tồn tại | Thường không | Kiểm tra ID và phạm vi |
| STATE_CONFLICT | Instance đang update hoặc deprovision | Có điều kiện | Chờ operation hiện tại |
| PLAN_NOT_SUPPORTED | Plan hoặc capability không hỗ trợ | Không | Chọn plan/operation hợp lệ |
| QUOTA_EXCEEDED | Tenant hết quota | Có thể sau khi quota thay đổi | Giải phóng hoặc yêu cầu thêm quota |
| PROVIDER_RATE_LIMITED | Provider trả 429 | Có | Retry theo Retry-After/backoff |
| PROVIDER_UNAVAILABLE | Provider 5xx hoặc mất kết nối | Có | Retry có giới hạn |
| PROVIDER_TIMEOUT_UNKNOWN | Timeout sau khi có thể đã có side effect | Chưa quyết định | Reconcile trước khi retry |
| SECRET_STORE_UNAVAILABLE | Secret manager không truy cập được | Có điều kiện | Phục hồi hoặc bù trừ |
| INTERNAL_UNEXPECTED | Lỗi không phân loại | Không mặc định | Điều tra bằng correlation ID |

Phân loại này là model nội bộ, không phải danh sách error code bắt buộc của OSB API.

### Tách category khỏi exception class

Không để controller hoặc handler suy luận retryability chỉ bằng tên exception. Một WebClientResponseException có thể đại diện cho 400, 403, 429 hoặc 503; mỗi trường hợp cần xử lý khác nhau.

Hãy ánh xạ lỗi ở adapter hoặc service layer thành error descriptor ổn định:

~~~java
public enum BrokerErrorCode {
    REQUEST_INVALID,
    RESOURCE_NOT_FOUND,
    STATE_CONFLICT,
    QUOTA_EXCEEDED,
    PROVIDER_RATE_LIMITED,
    PROVIDER_UNAVAILABLE,
    PROVIDER_TIMEOUT_UNKNOWN,
    SECRET_STORE_UNAVAILABLE,
    INTERNAL_UNEXPECTED
}

public record BrokerFailure(
    BrokerErrorCode code,
    boolean retryable,
    String safeDescription,
    String operationId,
    Throwable cause
) {}
~~~

Đây là model minh họa của ứng dụng. Trong production, không nên dùng safeDescription làm nơi lưu exception message thô. Mô tả công khai nên được chọn từ template đã kiểm soát theo error code; cause chỉ được dùng trong luồng log nội bộ có redaction.

## 4. Viết public description có thể hành động

Một mô tả lỗi tốt thường trả lời ba câu hỏi:

1. Request thất bại ở mức nào?
2. Caller có thể làm gì tiếp theo?
3. Nếu cần hỗ trợ, nên cung cấp mã tham chiếu nào?

Ví dụ:

| Tình huống | Mô tả nên dùng |
|---|---|
| Parameters không hợp lệ | “Một hoặc nhiều tham số không được service plan hỗ trợ. Kiểm tra cấu hình và gửi lại yêu cầu.” |
| Instance đang có operation | “Service instance đang được xử lý bởi một thao tác khác. Hãy đợi thao tác đó hoàn tất rồi thử lại.” |
| Quota không đủ | “Yêu cầu vượt hạn mức hiện tại của tài khoản. Kiểm tra mức sử dụng hoặc yêu cầu điều chỉnh quota.” |
| Provider tạm thời lỗi | “Nhà cung cấp dịch vụ tạm thời không khả dụng. Hãy thử lại sau.” |
| Kết quả provider chưa xác định | “Broker chưa xác nhận được kết quả thao tác. Không gửi một yêu cầu thay thế; hãy kiểm tra trạng thái hoặc liên hệ hỗ trợ bằng mã tham chiếu.” |
| Lỗi nội bộ | “Broker không thể hoàn tất yêu cầu. Liên hệ hỗ trợ và cung cấp mã tham chiếu.” |
| Caller không có quyền | “Bạn không được phép thực hiện thao tác này.” |

Không đưa các giá trị request vào câu thông báo nếu chúng có thể chứa dữ liệu khách hàng. Ví dụ, thay vì phản hồi “Database orders-prod-customer-17 không thể tạo vì user alice@example.com thiếu quyền”, hãy trả thông báo tổng quát có mã tham chiếu.

### Mô tả lỗi không nên chứa

- Password, access token, API key, private key hoặc certificate.
- Authorization, Cookie, Set-Cookie hoặc session token.
- Connection string có userinfo.
- Request/response body nguyên bản của provider.
- SQL query có literal dữ liệu khách hàng.
- Tên, email, số điện thoại hoặc dữ liệu định danh khách hàng nếu không cần thiết.
- Đường dẫn file, host nội bộ, private IP hoặc tên cluster.
- Stack trace, package name, class name hoặc dòng code.
- Nội dung exception do SDK/provider trả về nếu chưa được làm sạch.
- Secret reference có thể dùng để truy cập secret manager.

## 5. Dùng error code ổn định và correlation ID

Error code nội bộ giúp nhóm vận hành phân loại lỗi mà không cần đọc nội dung nhạy cảm. Code nên ổn định qua các phiên bản, không nhúng dữ liệu khách hàng hoặc thông tin hạ tầng.

Ví dụ log nội bộ:

~~~json
{
  "timestamp": "2026-11-27T10:15:30Z",
  "level": "ERROR",
  "event": "broker_operation_failed",
  "error_code": "PROVIDER_TIMEOUT_UNKNOWN",
  "operation_type": "PROVISION",
  "operation_id": "op-opaque-72f4",
  "instance_ref": "inst-opaque-19a2",
  "provider": "database-provider",
  "provider_request_id": "req-opaque-5510",
  "retryable": false,
  "outcome": "RECONCILIATION_REQUIRED",
  "correlation_id": "corr-opaque-8d21"
}
~~~

Các định danh trong ví dụ là giá trị giả lập. Log không chứa request body, password, username, database name hoặc tenant payload.

Correlation ID kết nối log giữa gateway, broker, adapter và worker. Có thể nhận ID từ header đã được tin cậy hoặc sinh ID mới ở ranh giới request. Nếu nhận giá trị từ caller, cần giới hạn độ dài, ký tự cho phép và chống log injection. Không dùng một chuỗi tùy ý từ header làm correlation ID mà không kiểm tra.

Correlation ID không phải credential và không được dùng thay access token. Nó chỉ giúp tìm các sự kiện liên quan.

### Phân biệt các định danh

| Định danh | Dùng để làm gì | Có nên trả cho caller? |
|---|---|---|
| correlationId | Liên kết log/trace của một request | Có thể, nếu là opaque và được thiết kế cho hỗ trợ |
| operationId | Theo dõi operation OSB async | Có, theo hợp đồng OSB |
| instanceId/bindingId | Định danh tài nguyên trong API | Đã có trong request hoặc response theo contract |
| providerRequestId | Đối soát với nhà cung cấp | Chỉ trả nếu provider và policy cho phép |
| internalResourceId | ID nội bộ của database/cluster | Không cần trả |
| secretRef | Tham chiếu tới secret manager | Không trả |

Nếu public description có mã hỗ trợ, hãy dùng correlation ID hoặc support reference ngẫu nhiên, không dùng ID database tuần tự hoặc provider resource ID.

## 6. Structured logging theo allowlist

Log có cấu trúc giúp truy vấn theo error code, operation type, provider và trạng thái. Tuy nhiên, structured logging không tự làm dữ liệu an toàn. Nếu log toàn bộ request object dưới dạng JSON, secret vẫn bị ghi lại.

Hãy chọn field theo allowlist:

**Có thể ghi khi cần thiết và đã kiểm soát**
- timestamp, log level, event name.
- error code và exception class.
- operation type và state.
- opaque operation ID, correlation ID.
- provider name hoặc adapter name.
- HTTP status từ provider.
- provider request ID nếu không nhạy cảm.
- retry attempt, duration và outcome.
- tên step nội bộ không chứa dữ liệu khách hàng.

**Không ghi mặc định**
- request/response body.
- Authorization và Cookie header.
- credentials object.
- query parameters có thể chứa secret.
- parameters do người dùng gửi.
- provider error body nguyên bản.
- SQL bind values.
- object.toString() của request, response hoặc entity.
- secret manager path nếu path chứa tenant hoặc tài nguyên nhạy cảm.

Ví dụ log an toàn trong Java:

~~~java
log.error(
    "Broker operation failed: code={}, operationType={}, "
        + "operationId={}, correlationId={}, providerStatus={}",
    failure.code(),
    operation.type(),
    operation.id(),
    correlationId,
    providerStatus
);
~~~

Không truyền toàn bộ exception message vào placeholder nếu SDK có thể đưa request hoặc response nhạy cảm vào message. Có thể log exception class và stack trace trong sink nội bộ được bảo vệ, nhưng cần kiểm tra stack trace/cause chain vì một số client library nhúng URL hoặc response body vào exception.

Nếu stack trace có nguy cơ chứa dữ liệu nhạy cảm, dùng exception đã được chuẩn hóa hoặc log chi tiết qua một sink có kiểm soát và redaction. Không bật wire logging ở mức body/header cho WebClient hoặc HTTP client trong production nếu chưa có bộ lọc được kiểm thử.

## 7. Redaction: che dữ liệu trước khi ghi log

Redaction thay thế hoặc loại bỏ dữ liệu nhạy cảm trước khi ghi. Nhưng redaction dựa trên blacklist thường dễ bỏ sót tên trường mới. Thiết kế an toàn hơn là chỉ ghi field được phép; redaction là lớp bảo vệ bổ sung.

Các trường thường cần che:

~~~text
password
passwd
client_secret
access_token
refresh_token
api_key
authorization
cookie
set-cookie
private_key
client_assertion
credential
connection_string
uri
~~~

Danh sách này chỉ là ví dụ. Tên trường có thể khác nhau giữa provider và service. Cần phân loại dữ liệu theo schema thực tế, không dựa duy nhất vào tên key.

Ví dụ cấu trúc dữ liệu trước khi redaction:

~~~json
{
  "username": "orders_app",
  "password": "very-secret",
  "host": "db.internal",
  "port": 5432
}
~~~

Log sau khi lọc:

~~~json
{
  "username": "[REDACTED]",
  "password": "[REDACTED]",
  "host": "[REDACTED]",
  "port": 5432
}
~~~

Trong nhiều hệ thống, không cần ghi cả username và host. Tốt hơn là bỏ hoàn toàn credentials object khỏi log, chỉ giữ binding ID dạng opaque và provider request ID.

### Che dữ liệu trong nhiều định dạng

Secret có thể xuất hiện trong:

- JSON field.
- URL userinfo như scheme://user:password@host.
- Query parameter như token=...
- HTTP header.
- Exception message.
- SQL statement và bind parameter.
- YAML hoặc cấu hình được serialize.
- Nested object hoặc collection.
- Multi-line text từ provider.

Một redactor chỉ tìm key password trong JSON sẽ không che token nằm trong URL hoặc header. Hãy giảm bề mặt bằng cách không log payload, sau đó kiểm thử redaction cho các định dạng thực sự được dùng.

### Không sửa dữ liệu nghiệp vụ chỉ để log

Không nên thay đổi request parameters hoặc credentials thực tế khi redaction. Hãy tạo một representation riêng dành cho logging, áp dụng allowlist/redaction trên bản sao và không truyền bản đã che vào provider adapter.

## 8. Không để dữ liệu khách hàng lọt vào exception

Một lỗi validation có thể phát sinh từ input của khách hàng. Nếu exception message ghép trực tiếp giá trị đó, log và response có thể chứa dữ liệu nhạy cảm.

Ví dụ không an toàn:

~~~java
throw new InvalidParameterException(
    "Invalid customer email: " + request.getParameters().get("email"));
~~~

Cách an toàn hơn:

~~~java
throw new BrokerValidationException(
    BrokerErrorCode.REQUEST_INVALID,
    "A supplied parameter does not satisfy the service policy."
);
~~~

Nếu cần biết trường nào sai, ghi tên field đã được allowlist và rule code, không ghi giá trị:

~~~json
{
  "event": "parameter_validation_failed",
  "error_code": "REQUEST_INVALID",
  "field": "backup_retention_days",
  "rule": "VALUE_OUT_OF_RANGE",
  "correlation_id": "corr-opaque-8d21"
}
~~~

Tên field cũng cần được kiểm soát. Nếu request cho phép dynamic keys do khách hàng gửi, không đưa nguyên key vào log trước khi xác thực. Giới hạn độ dài và ký tự của field name để tránh log injection hoặc log flooding.

## 9. Ánh xạ lỗi từ provider sang lỗi broker

Provider thường có error code và message riêng. Không nên chuyển nguyên response body của provider sang OSB response.

Tạo lớp adapter để chuyển provider error thành category nội bộ:

| Provider result | Category broker | Public description |
|---|---|---|
| 401/403 từ provider service account | PROVIDER_AUTHORIZATION | Broker không thể hoàn tất thao tác với nhà cung cấp |
| 404 resource khi broker kỳ vọng tồn tại | PROVIDER_RESOURCE_MISSING | Không thể xác định trạng thái tài nguyên; cần kiểm tra |
| 409 resource conflict | STATE_CONFLICT hoặc PROVIDER_CONFLICT | Tài nguyên đang ở trạng thái không tương thích |
| 429 rate limit | PROVIDER_RATE_LIMITED | Nhà cung cấp đang giới hạn yêu cầu; thử lại sau |
| 5xx | PROVIDER_UNAVAILABLE | Nhà cung cấp tạm thời không khả dụng |
| Timeout sau side effect có thể xảy ra | PROVIDER_TIMEOUT_UNKNOWN | Chưa xác nhận được kết quả; kiểm tra trạng thái trước khi gửi lại |
| Validation error từ provider | REQUEST_INVALID hoặc PLAN_NOT_SUPPORTED | Yêu cầu không được service plan hỗ trợ |

Mapping cần dựa vào endpoint và semantics của provider. Ví dụ provider trả 404 có thể nghĩa là tài nguyên đã bị xóa, hoặc account/region sai; không nên luôn biến nó thành lỗi “không tìm thấy” cho người dùng.

### Giữ provider request ID, bỏ provider body

Provider request ID thường hữu ích cho support. Có thể lưu ID này nếu provider xác nhận nó không phải secret và không chứa dữ liệu khách hàng. Không lưu toàn bộ error body chỉ để giữ request ID; parse trường định danh đã biết và discard phần còn lại.

Nếu provider trả message như “authentication failed for user ... with token ...”, broker chỉ cần lưu provider status, request ID, adapter và category. Public response dùng template an toàn.

## 10. Phân biệt lỗi retry được và kết quả chưa xác định

Lỗi retry được không giống với kết quả chưa xác định.

**Retryable failure**: broker biết thao tác chưa tạo side effect hoặc provider xác nhận request bị từ chối tạm thời. Có thể retry theo backoff.

**Unknown outcome**: broker không biết provider đã thực hiện side effect hay chưa. Ví dụ timeout sau khi gửi create database. Retry ngay có thể tạo tài nguyên trùng; compensation ngay có thể xóa nhầm hoặc bỏ sót.

Với unknown outcome:

1. Lưu operation state là UNKNOWN hoặc RECONCILIATION_REQUIRED.
2. Giữ idempotency key và provider request reference.
3. Tra cứu provider bằng external reference ổn định.
4. Nếu resource tồn tại và thuộc operation, cập nhật state theo kết quả thực tế.
5. Nếu provider xác nhận chưa thực hiện, retry với cùng key nếu provider hỗ trợ.
6. Nếu không thể xác định, chuyển sang retry/reconciliation có giới hạn hoặc manual repair.

Không trả mô tả kiểu “thao tác chắc chắn thất bại” khi broker chưa có bằng chứng. Public message nên nói kết quả chưa được xác nhận và hướng dẫn caller không tạo một yêu cầu thay thế có thể gây side effect trùng.

## 11. Bảo vệ dữ liệu đa tenant

Service broker có thể quản lý nhiều organization, space, project hoặc tenant. Lỗi không được làm lộ sự tồn tại hoặc dữ liệu của tenant khác.

Các quy tắc:

- Kiểm tra tenant ownership trước khi đọc instance, binding hoặc secret.
- Truy vấn database theo cả resource ID và tenant scope khi mô hình cho phép.
- Không đưa tenant name, email, organization metadata hoặc parameters vào public error.
- Không dùng provider resource ID làm support reference công khai.
- Không trả khác biệt dễ khai thác giữa “không tồn tại” và “tồn tại nhưng thuộc tenant khác” nếu policy yêu cầu che sự tồn tại.
- Không dùng tenant ID thô làm metric label có cardinality cao.
- Tách quyền đọc log và secret theo vai trò.
- Kiểm tra tenant context được lấy từ danh tính đã xác thực, không tin trực tiếp context body do caller gửi.

Ví dụ, một request bind tham chiếu instance của tenant khác. Broker nên dừng trước khi đọc secret hoặc gọi provider. Public response không nên chứa service name, plan, owner hoặc trạng thái của instance kia.

### Tránh lộ dữ liệu qua timing và log

Ngay cả khi response body giống nhau, thời gian xử lý khác biệt lớn có thể tiết lộ tài nguyên có tồn tại hay không. Không phải mọi endpoint đều cần timing equalization, nhưng cần tránh truy vấn hoặc log chi tiết trước khi xác thực ownership.

Audit nội bộ có thể ghi lý do thực tế như TENANT_SCOPE_MISMATCH, nhưng chỉ người có quyền phù hợp mới được xem.

## 12. Correlation ID trong Spring WebFlux

Trong ứng dụng reactive, request có thể đi qua nhiều operator và thread. Không nên dựa vào ThreadLocal tùy tiện để giữ correlation ID. Có thể dùng Reactor Context hoặc tracing integration của Spring để truyền metadata qua pipeline.

Một filter minh họa:

~~~java
@Component
public class CorrelationIdWebFilter implements WebFilter {

    private static final String HEADER = "X-Correlation-ID";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String correlationId = resolveTrustedOrGenerate(
            exchange.getRequest().getHeaders().getFirst(HEADER));

        exchange.getResponse().getHeaders()
            .set(HEADER, correlationId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put("correlationId", correlationId));
    }

    private String resolveTrustedOrGenerate(String supplied) {
        if (supplied != null
                && supplied.matches("[A-Za-z0-9_-]{8,64}")) {
            return supplied;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Đây là ví dụ cấu trúc; cần điều chỉnh theo cách ứng dụng tích hợp Spring Security, tracing và gateway. Nếu gateway đã tạo correlation ID đáng tin cậy, có thể ưu tiên giá trị đó. Không dùng correlation ID làm cơ chế xác thực.

Khi ghi log trong reactive pipeline, lấy correlation metadata từ Reactor Context hoặc dùng Micrometer Tracing tương thích với phiên bản Spring Boot. Không tạo một ID mới ở mỗi service layer nếu muốn liên kết toàn bộ request.

Nếu worker xử lý async sau khi HTTP request kết thúc, ghi correlation ID vào operation record hoặc outbox event để worker tiếp tục gắn cùng trace/reference. Không đưa credentials vào Reactor Context hoặc baggage.

## 13. Log, trace và metric đều là nơi có thể rò rỉ dữ liệu

Không chỉ HTTP response mới cần redaction. Dữ liệu nhạy cảm có thể lọt vào nhiều hệ thống observability.

### Log

- Chọn field theo allowlist.
- Không log request body và response body mặc định.
- Giới hạn quyền đọc và retention.
- Mã hóa khi truyền và lưu theo chính sách nền tảng.
- Chống log injection bằng cách chuẩn hóa newline và ký tự điều khiển.
- Không cho người dùng gửi message tùy ý vào log ở mức không giới hạn.

### Distributed trace

- Không gắn credentials, request body hoặc SQL bind value vào span attribute.
- Dùng error code, operation type và provider name có kiểm soát.
- Exception event phải được rà soát vì message có thể chứa URL hoặc response body.
- Baggage chỉ chứa metadata không nhạy cảm và có giới hạn kích thước.

### Metrics

- Dùng label có cardinality thấp như operation type, error category, provider class.
- Không dùng instance ID, binding ID, email, tenant name hoặc token làm label.
- Đếm lỗi theo category thay vì theo message tự do.
- Không đưa description chứa dữ liệu khách hàng vào metric exemplar.

Một hệ thống có thể đã che log nhưng vẫn làm lộ dữ liệu qua trace hoặc metric. Cần kiểm thử toàn bộ đường đi observability.

## 14. Xử lý lỗi ở tầng Spring

Nên có một lớp mapping tập trung để chuyển exception nội bộ thành response an toàn. Service và provider adapter ném exception có kiểu hoặc error code rõ; lớp biên HTTP quyết định status và description theo OSB contract.

Một mapper minh họa:

~~~java
public record PublicBrokerError(
    HttpStatus status,
    String description
) {}

@Component
public class BrokerErrorMapper {

    public PublicBrokerError toPublicError(Throwable error) {
        if (error instanceof BrokerValidationException) {
            return new PublicBrokerError(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "The request does not satisfy the service policy."
            );
        }

        if (error instanceof BrokerStateConflictException) {
            return new PublicBrokerError(
                HttpStatus.CONFLICT,
                "The service instance is busy with another operation."
            );
        }

        if (error instanceof ProviderUnavailableException) {
            return new PublicBrokerError(
                HttpStatus.SERVICE_UNAVAILABLE,
                "The service provider is temporarily unavailable."
            );
        }

        return new PublicBrokerError(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "The broker could not complete the request. "
                + "Contact support with the correlation reference."
        );
    }
}
~~~

Đây là ví dụ nội bộ để minh họa mapping; không phải API có sẵn của Spring Cloud Open Service Broker. Cần ánh xạ status và body theo endpoint/OSB version và cơ chế exception handling của framework đang dùng.

### Không trả error.message trực tiếp

Không viết:

~~~java
return response.status(500)
    .bodyValue(Map.of("description", error.getMessage()));
~~~

Exception message có thể chứa provider URL, SQL, credential hoặc input người dùng. Thay vào đó, mapper chọn description từ template đã kiểm soát dựa trên loại lỗi.

### Giữ nguyên nguyên nhân cho log nội bộ

Sau khi tạo public error, vẫn cần log lỗi nội bộ với correlation ID và operation ID. Có thể ghi exception class, stack trace đã kiểm soát và error code. Không đánh mất nguyên nhân gốc khi wrap exception; giữ cause chain ở nơi an toàn để đội vận hành chẩn đoán.

Nếu framework đã cung cấp error handler cho OSB, hãy mở rộng hoặc cấu hình theo extension point được hỗ trợ. Tránh thêm một global WebExceptionHandler ghi đè toàn bộ response của framework mà không có integration test cho tất cả endpoint.

## 15. Chống log injection và dữ liệu đầu vào độc hại

Caller có thể gửi chuỗi chứa newline, tab hoặc ký tự điều khiển trong parameters, header hoặc identifier. Nếu log trực tiếp, một input có thể giả mạo nhiều dòng log hoặc làm hỏng parser.

Biện pháp:

- Giới hạn độ dài correlation ID, operation ID và field name.
- Chỉ chấp nhận ký tự phù hợp cho từng định danh.
- Dùng structured logger thay vì nối chuỗi tự do.
- Loại bỏ hoặc encode CR, LF và control characters trước khi log dữ liệu đầu vào được phép.
- Không log raw parameter value.
- Giới hạn kích thước error description.
- Không đưa JSON provider body chưa kiểm tra vào log.
- Dùng parser có giới hạn độ sâu và kích thước khi xử lý error response.

Không nên cố “sanitize” mọi chuỗi rồi cho phép log. Cách an toàn hơn là chỉ log field đã xác thực và có mục đích vận hành.

## 16. Audit và retention cho diagnostic data

Log chẩn đoán có thể chứa metadata vận hành nhạy cảm dù đã loại bỏ credentials. Cần xác định:

- Ai được đọc log và trace?
- Ai có quyền xem provider request ID hoặc tenant reference?
- Log được giữ trong bao lâu?
- Khi hết retention, dữ liệu được xóa như thế nào?
- Audit truy cập log có được ghi nhận không?
- Có cần tách log bảo mật khỏi log ứng dụng không?
- Backup của hệ thống log có áp dụng cùng chính sách bảo vệ không?

Không giữ stack trace hoặc provider payload vô thời hạn. Nếu cần lưu bằng chứng cho một incident, dùng kho có quyền truy cập hạn chế và thời hạn được phê duyệt. Không sao chép secret vào ticket, chat hoặc tài liệu hỗ trợ.

Một support reference nên cho phép nhân viên tìm operation trong hệ thống nội bộ mà không cần người dùng gửi credentials hoặc payload gốc.

## 17. Ví dụ luồng xử lý lỗi end-to-end

Giả sử nền tảng gửi provision request. Broker reserve instance, gọi provider tạo database và nhận timeout. Provider có thể đã tạo resource nhưng response bị mất.

Một luồng xử lý an toàn:

1. Broker tạo correlation ID và operation ID.
2. Ghi request fingerprint và operation state vào database.
3. Gọi provider với idempotency key ổn định.
4. Timeout xảy ra; broker phân loại PROVIDER_TIMEOUT_UNKNOWN.
5. Ghi state RECONCILIATION_REQUIRED, không đánh dấu thất bại chắc chắn.
6. Ghi structured log gồm operation ID, provider adapter, error code và correlation ID; không ghi body hoặc credentials.
7. Nếu OSB request chấp nhận async, trả response async theo contract và để nền tảng poll last operation.
8. Worker tra cứu provider theo external reference.
9. Nếu resource đã tồn tại, worker lưu provider resource ID và tiếp tục các bước provision còn lại.
10. Nếu provider xác nhận chưa tạo, worker retry bằng cùng idempotency key.
11. Khi operation đạt kết quả, last operation trả trạng thái tương ứng.
12. Nếu lỗi cuối cùng, public description dùng template an toàn và support reference giúp đội vận hành tra cứu.

Nếu request không chấp nhận async và broker không thể hoàn tất đồng bộ, hãy trả lỗi theo OSB contract. Broker vẫn phải lưu trạng thái unknown và tiếp tục reconciliation nội bộ; không xóa operation record chỉ vì HTTP request đã kết thúc.

## 18. Kiểm thử để chứng minh không rò rỉ dữ liệu

Kiểm thử bảo mật phải xác nhận cả nội dung response lẫn các sink observability.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Provider exception chứa password | Public response và log không chứa password |
| URL có userinfo | Username/password không xuất hiện trong log |
| Authorization header | Không xuất hiện trong log hoặc trace |
| Provider error body có PII | Chỉ error category và provider request ID an toàn được lưu |
| Validation error chứa input email | Response không echo email |
| Tenant scope mismatch | Không tiết lộ instance hoặc tenant khác |
| Timeout với unknown outcome | Message không khẳng định sai thao tác đã thất bại |
| Correlation ID chứa newline | Bị từ chối hoặc thay bằng ID mới |
| Error description quá dài | Bị giới hạn theo policy |
| Nested credentials object | Không xuất hiện trong structured log |
| Trace exception event | Không chứa request body hoặc secret |
| Metric labels | Không có instance ID, email hoặc tenant identifier |
| Retryable provider 429 | Category và retry policy được ghi nhận chính xác |
| Lỗi không dự kiến | Caller nhận thông báo chung và support reference |

Một test có thể dùng secret sentinel duy nhất, ví dụ TEST_SECRET_DO_NOT_LOG_9f31, đưa vào request, provider exception và response giả lập. Sau khi thực thi, tìm sentinel trong HTTP response, application log, trace export và test capture. Kết quả phải không có sentinel ở bất kỳ kênh nào không được phép.

Ngoài test tự động, cần kiểm tra cấu hình logging production: WebClient wiretap, HTTP access log, SQL logging, actuator endpoint và APM agent. Một lớp redaction trong ứng dụng không thể che dữ liệu nếu một thư viện khác tự ghi request body.

## 19. Những lỗi thường gặp

**Trả exception message trực tiếp cho caller.** Message có thể chứa provider URL, SQL, username hoặc token. Dùng error code và description template đã kiểm soát.

**Chỉ che password theo tên field.** Secret có thể nằm trong URL, header, nested object hoặc stack trace. Ưu tiên allowlist logging và kiểm thử nhiều định dạng.

**Ghi toàn bộ request/response để debug.** Điều này dễ làm lộ parameters, context và credentials. Ghi operation reference và các metadata tối thiểu.

**Dùng một message cho mọi lỗi.** Người gọi không biết nên sửa request, chờ operation hay retry. Phân loại lỗi và cung cấp hướng xử lý an toàn.

**Trả chi tiết tenant ownership.** Phản hồi có thể làm lộ instance hoặc dữ liệu của khách hàng khác. Kiểm tra tenant scope trước khi đọc tài nguyên và dùng response nhất quán.

**Coi mọi timeout là retryable.** Timeout có thể xảy ra sau side effect. Dùng UNKNOWN và reconciliation trước khi retry.

**Đưa correlation ID tùy ý vào log.** Chuỗi có newline hoặc quá dài có thể gây log injection. Validate hoặc sinh ID mới.

**Chỉ bảo vệ application log.** Trace, metric, access log, provider SDK và SQL logger cũng có thể ghi secret. Kiểm thử mọi sink.

**Đưa credentials vào support ticket.** Nhân viên hỗ trợ không cần password để tìm operation. Dùng support reference và quyền truy cập nội bộ có kiểm soát.

**Dùng metric label có dữ liệu khách hàng.** Cardinality cao và rò rỉ thông tin. Chỉ dùng category và operation type có cardinality thấp.

## 20. Nguyên tắc triển khai trong Spring Cloud Service Broker

Trong ứng dụng Spring Cloud Open Service Broker, hãy tạo error taxonomy ổn định ở tầng nghiệp vụ và provider adapter. Lớp biên HTTP ánh xạ category sang status cùng description tương thích OSB API. Public description phải đến từ template đã kiểm soát, không lấy trực tiếp từ Throwable hoặc response body của provider.

Tạo correlation ID ở ranh giới request, truyền qua Reactor Context và lưu cùng operation/outbox để worker có thể tiếp tục chẩn đoán. Structured log theo allowlist, chỉ ghi error code, operation type, state, provider reference an toàn và thời gian xử lý. Không log request body, credentials object, authorization header hoặc exception message chưa được kiểm tra.

Với lỗi provider, phân biệt lỗi permanent, transient và unknown outcome. Timeout sau side effect cần reconciliation trước khi retry hoặc compensation. Kiểm tra tenant ownership trước khi truy cập resource và không để public response tiết lộ sự tồn tại của tài nguyên ngoài phạm vi caller.

Cuối cùng, kiểm thử bằng secret sentinel trên response, log, trace và metric; kiểm tra cả cấu hình HTTP client, SQL logger và APM. Một service broker có chẩn đoán tốt phải giúp đội vận hành tìm được operation và nguyên nhân mà không cần tiết lộ credentials hay dữ liệu khách hàng cho người gọi hoặc hệ thống quan sát không được phép.

