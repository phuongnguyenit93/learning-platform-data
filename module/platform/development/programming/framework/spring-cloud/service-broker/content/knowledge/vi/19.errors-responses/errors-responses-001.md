# Cấu trúc lỗi OSB: error, description và phần mở rộng được hỗ trợ

Open Service Broker API (OSB API) dùng HTTP để platform gửi yêu cầu provision, update, bind, unbind và deprovision tới broker. Khi một thao tác không thể thực hiện, broker phải trả mã HTTP và nội dung lỗi theo hợp đồng OSB API để platform biết request bị từ chối, tài nguyên không tồn tại, thao tác cần chạy bất đồng bộ hay hệ thống gặp sự cố.

Với `SPRING_CLOUD_SERVICE_BROKER`, cấu trúc lỗi là một phần của API công khai. `error` giúp nhận diện mã lỗi máy đọc khi hợp đồng có định nghĩa mã tương ứng; `description` giải thích ngắn gọn cho người vận hành hoặc người dùng. Broker cần ánh xạ exception nội bộ sang phản hồi ổn định, không để tên class Java, stack trace, SQL, raw provider response hoặc bí mật lọt ra ngoài. Các trường mở rộng chỉ nên được dùng khi platform và broker đã thống nhất cách hiểu.

## 1. Một lỗi OSB API gồm những gì?

Phản hồi lỗi OSB API là một HTTP response. Cần phân biệt hai phần:

- **HTTP status code:** cho biết kết quả ở cấp giao thức, ví dụ request không hợp lệ, không tìm thấy tài nguyên, xung đột trạng thái hoặc lỗi server.
- **JSON error body:** cung cấp thông tin lỗi theo hợp đồng OSB API. Trường `description` mô tả lỗi; trường `error` có thể cung cấp mã lỗi máy đọc khi có mã phù hợp.

Ví dụ một lỗi có mã nhận diện:

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": "AsyncRequired",
  "description": "Thao tác này cần xử lý bất đồng bộ. Hãy gửi lại request với accepts_incomplete=true."
}
```

Ví dụ lỗi nghiệp vụ không cần mã tùy chỉnh:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "description": "Tham số yêu cầu không hợp lệ. Hãy kiểm tra schema của service và plan."
}
```

Theo hợp đồng lỗi OSB API, `description` là nội dung quan trọng để giải thích lỗi; `error` được dùng làm mã nhận diện khi phù hợp với quy ước của API. Không coi `error` là nơi chép nguyên exception message hoặc tên class nội bộ. Broker phải tuân thủ schema và semantics của phiên bản OSB API mà nó công bố hỗ trợ.

## 2. Phân biệt error với description

Hai trường có mục đích khác nhau:

| Trường | Vai trò | Đặc điểm |
|---|---|---|
| `error` | Mã lỗi để client hoặc platform phân loại | Nên ổn định, ngắn, máy đọc được và chỉ dùng mã đã được định nghĩa/thỏa thuận. |
| `description` | Giải thích lỗi cho người đọc | Dễ hiểu, an toàn, không phụ thuộc chi tiết triển khai nội bộ. |

Ví dụ:

```json
{
  "error": "AsyncRequired",
  "description": "Thao tác cấp phát cần xử lý bất đồng bộ."
}
```

Ở đây, platform có thể nhận diện `AsyncRequired` để quyết định gửi lại request với `accepts_incomplete=true`; description giúp người vận hành hiểu lý do. Nếu đổi câu chữ mô tả để rõ hơn, client vẫn có thể dựa vào mã lỗi ổn định.

Không nên trả:

```json
{
  "error": "com.example.broker.ProviderTimeoutException",
  "description": "org.postgresql.util.PSQLException: password=RealSecret123; host=db-prod-17.internal"
}
```

Ví dụ này làm lộ tên class, driver, hostname nội bộ và credential. Hãy ánh xạ lỗi kỹ thuật sang mã nghiệp vụ đã duyệt, rồi viết description an toàn.

## 3. HTTP status code và mã lỗi không thay thế nhau

HTTP status code biểu thị nhóm kết quả ở tầng giao thức. Trường `error` bổ sung mã nhận diện chi tiết trong body. Hai phần phải nhất quán.

| HTTP status thường dùng | Ý nghĩa tổng quát | Ví dụ xử lý broker |
|---|---|---|
| `400 Bad Request` | Request không hợp lệ về cú pháp hoặc cấu trúc | JSON sai, thiếu trường bắt buộc hoặc tham số không đúng schema. |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực | Broker credentials không hợp lệ. |
| `403 Forbidden` | Caller đã xác thực nhưng không được phép | Platform/client không có quyền thao tác trong phạm vi được yêu cầu. |
| `404 Not Found` | Endpoint hoặc tài nguyên được yêu cầu không tồn tại | Instance/binding không được tìm thấy, theo semantics của endpoint và phiên bản API. |
| `409 Conflict` | Request xung đột với trạng thái hiện tại | Có operation khác đang chạy hoặc resource state không cho phép chuyển tiếp, nếu mapping này phù hợp hợp đồng. |
| `422 Unprocessable Entity` | Request hiểu được nhưng không thể xử lý theo điều kiện nghiệp vụ | `AsyncRequired` khi broker cần async nhưng platform không chấp nhận. |
| `429 Too Many Requests` | Bị giới hạn tốc độ | Chỉ dùng khi broker/platform thống nhất semantics và có thể hướng dẫn retry phù hợp. |
| `500 Internal Server Error` | Lỗi nội bộ không dự kiến | Lỗi broker chưa phân loại được. |
| `502/503/504` | Lỗi gateway, dịch vụ phụ thuộc hoặc timeout theo vai trò HTTP của thành phần | Chỉ dùng khi phù hợp kiến trúc proxy/provider và contract của platform. |

Bảng trên là hướng dẫn phân loại HTTP tổng quát. Mỗi thao tác OSB API có quy định riêng về mã phản hồi; broker phải đối chiếu với phiên bản OSB API và mapping của Spring Cloud Open Service Broker đang dùng. Không thay tất cả lỗi thành `400` hoặc `500` chỉ để đơn giản hóa code.

Ví dụ, `AsyncRequired` là trường hợp có ý nghĩa rõ: broker cần xử lý bất đồng bộ nhưng request không cho phép. Đây không phải lỗi cú pháp JSON. Platform cần nhận đúng status và error code để có thể gửi lại request với `accepts_incomplete=true`.

## 4. Các mã lỗi OSB và mã lỗi riêng

Một số tình huống OSB API có mã lỗi máy đọc được đã được quy định trong đặc tả/phiên bản tương ứng, ví dụ `AsyncRequired`. Với các mã như xung đột concurrency hoặc xung đột maintenance metadata, chỉ dùng khi phiên bản OSB API mà broker hỗ trợ định nghĩa chúng và điều kiện thực tế khớp.

Không tự đặt một mã như `DatabasePasswordInvalid` rồi giả định mọi platform hiểu nó. Nếu cần mã riêng cho vận hành, cần phân biệt:

- **Mã OSB chuẩn:** tuân theo đặc tả và có thể được platform xử lý theo semantics đã biết.
- **Mã nội bộ:** phục vụ log, metric, dashboard và hỗ trợ; không nhất thiết xuất hiện trong response công khai.
- **Mã extension đã thỏa thuận:** mã tùy chỉnh mà broker và một platform cụ thể cùng định nghĩa cách xử lý.

Ví dụ mã nội bộ:

```text
PROVIDER_AUTH_REJECTED
PROVIDER_RATE_LIMITED
INSTANCE_STATE_CONFLICT
INVALID_PLAN_PARAMETERS
RESOURCE_RECONCILIATION_REQUIRED
```

Những mã này có thể được lưu trong operation record và log. Chỉ đưa vào `error` hoặc phần mở rộng của response nếu hợp đồng tích hợp cho phép và consumer biết cách xử lý. Không dùng mã nội bộ thay thế mã chuẩn bắt buộc của OSB API.

## 5. Nội dung description nên viết như thế nào?

`description` nên trả lời ba câu hỏi ở mức cần thiết:

1. Thao tác nào không thể hoàn tất hoặc điều kiện nào không được đáp ứng?
2. Người gọi có thể làm gì tiếp theo, nếu có hành động khắc phục rõ ràng?
3. Nếu cần hỗ trợ, mã tham chiếu nào giúp đội vận hành tìm đúng log/operation?

Ví dụ:

| Tình huống | Description phù hợp |
|---|---|
| Tham số sai | `Tham số storage_gb phải nằm trong giới hạn của plan đã chọn.` |
| Plan không hỗ trợ | `Plan được yêu cầu không hỗ trợ thao tác cập nhật này.` |
| Cần async | `Thao tác cần xử lý bất đồng bộ. Hãy gửi lại request với accepts_incomplete=true.` |
| Provider tạm thời lỗi | `Không thể hoàn tất thao tác với nhà cung cấp. Mã tham chiếu: op-7f2a91.` |
| Instance đang được xử lý | `Service instance đang có một thao tác khác. Hãy kiểm tra trạng thái operation hiện tại.` |

Description không cần kể toàn bộ quá trình kỹ thuật. Tránh trả tên host nội bộ, tên database, đường dẫn file, SQL, stack trace, request body, provider response nguyên gốc hoặc chi tiết network topology.

### Không phản chiếu dữ liệu đầu vào

Nếu người dùng gửi password sai định dạng, không trả nguyên giá trị đó trong lỗi. Có thể nêu tên trường và quy tắc vi phạm:

```json
{
  "description": "Trường admin_password phải có độ dài từ 16 đến 128 ký tự."
}
```

Không trả:

```json
{
  "description": "Giá trị admin_password=MyPassword123 không hợp lệ."
}
```

Ngay cả khi request thất bại, body lỗi vẫn có thể được lưu trong platform log, ticket hoặc telemetry. Vì vậy description phải được làm sạch trước khi trả về.

## 6. Phần mở rộng được hỗ trợ là gì?

Một số tích hợp cần thông tin bổ sung ngoài `error` và `description`, ví dụ mã tham chiếu hỗ trợ hoặc chỉ dẫn retry. Tuy nhiên, một trường JSON tùy chỉnh không tự động trở thành một phần của OSB API chuẩn.

Có ba nguyên tắc:

- Chỉ thêm field khi schema/phiên bản API và platform mục tiêu cho phép hoặc khi hai bên đã thống nhất extension.
- Giữ nguyên các trường chuẩn và semantics của HTTP status; extension không được thay thế `description` hoặc mã lỗi chuẩn.
- Client không hiểu extension vẫn phải có thể xử lý response theo phần chuẩn. Không yêu cầu mọi platform đọc field riêng mới hoạt động đúng.

Ví dụ một extension có namespace riêng, chỉ dùng khi đã được platform hỗ trợ:

```json
{
  "error": "ProviderUnavailable",
  "description": "Không thể hoàn tất thao tác với nhà cung cấp. Mã tham chiếu: op-7f2a91.",
  "extensions": {
    "com.example.broker": {
      "supportReference": "op-7f2a91",
      "retryable": true,
      "retryAfterSeconds": 30
    }
  }
}
```

`ProviderUnavailable`, `extensions`, `supportReference`, `retryable` và `retryAfterSeconds` trong ví dụ là quy ước minh họa của một tích hợp riêng, không phải mã/field portable được mọi platform OSB hiểu. Nếu platform không hỗ trợ extension này, broker không được dựa vào nó để yêu cầu platform retry hoặc thay đổi hành vi.

Nếu chỉ cần gợi ý thời gian retry, cân nhắc header HTTP phù hợp như `Retry-After` khi semantics và platform hỗ trợ. Không nhất thiết phải tạo thêm JSON field. Header cũng không được dùng để khẳng định một thao tác có thể retry an toàn nếu side effect chưa được bảo vệ bằng idempotency.

## 7. Không nhầm error response với last_operation

Trong OSB API, lỗi của request HTTP và kết quả của một operation bất đồng bộ là hai trường hợp khác nhau.

### Lỗi ngay trong request

Nếu broker từ chối request trước khi chấp nhận operation, broker trả HTTP error với body lỗi. Ví dụ `AsyncRequired` khi request không cho phép xử lý bất đồng bộ.

### Operation đã được chấp nhận nhưng thất bại sau đó

Nếu broker đã trả `202 Accepted`, platform polling `GET /last_operation`. Khi worker hoàn tất với lỗi, endpoint này vẫn trả response thành công ở tầng HTTP để biểu thị việc truy vấn operation thành công; phần body mô tả trạng thái operation là `failed`.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "state": "failed",
  "description": "Không thể hoàn tất thao tác cấp phát. Mã tham chiếu: op-7f2a91."
}
```

Không trả lại một HTTP `500` chỉ vì operation đã thất bại nếu platform đang truy vấn trạng thái operation đã được chấp nhận. `last_operation` trả trạng thái theo contract riêng; HTTP error dành cho lỗi của chính request truy vấn hoặc lỗi giao thức phù hợp.

## 8. Ánh xạ lỗi từ tầng nghiệp vụ

Trong Spring Cloud Service Broker, lỗi có thể phát sinh ở controller/framework adapter, service nghiệp vụ, repository, provider client hoặc worker. Không nên để mỗi tầng tự tạo một JSON error body khác nhau.

Nên có một bước mapping tập trung:

```text
Provider / Database / Validation exception
              |
              v
       Domain error category
              |
              v
     OSB error/status mapping
              |
              v
   Safe error response (error + description)
```

Ví dụ mô hình lỗi nội bộ:

```java
public enum BrokerErrorCode {
    INVALID_PARAMETERS,
    INSTANCE_NOT_FOUND,
    PLAN_NOT_SUPPORTED,
    INSTANCE_STATE_CONFLICT,
    PROVIDER_UNAVAILABLE,
    PROVIDER_AUTH_REJECTED,
    ASYNC_REQUIRED,
    UNKNOWN_FAILURE
}

public record BrokerFailure(
        BrokerErrorCode code,
        String safeDescription,
        Throwable cause
) {}
```

`BrokerFailure` là mô hình domain nội bộ. Không trả `cause` ra response và không tự serialize toàn bộ record vì `Throwable` có thể chứa thông tin nhạy cảm.

## 9. Ví dụ error mapper trong Java

Một mapper có thể chọn HTTP status và nội dung công khai từ loại lỗi đã chuẩn hóa:

```java
public record OsbErrorPayload(String error, String description) {}

public record MappedOsbError(int httpStatus, OsbErrorPayload body) {}

public final class OsbErrorMapper {

    public MappedOsbError map(BrokerFailure failure) {
        return switch (failure.code()) {
            case INVALID_PARAMETERS -> new MappedOsbError(
                    400,
                    new OsbErrorPayload(
                            "InvalidParameters",
                            failure.safeDescription()
                    )
            );
            case INSTANCE_NOT_FOUND -> new MappedOsbError(
                    410,
                    new OsbErrorPayload(
                            "",
                            failure.safeDescription()
                    )
            );
            case ASYNC_REQUIRED -> new MappedOsbError(
                    422,
                    new OsbErrorPayload(
                            "AsyncRequired",
                            failure.safeDescription()
                    )
            );
            case PROVIDER_UNAVAILABLE, UNKNOWN_FAILURE -> new MappedOsbError(
                    500,
                    new OsbErrorPayload(
                            "",
                            "Không thể hoàn tất thao tác. Hãy liên hệ hỗ trợ với mã tham chiếu đã cung cấp."
                    )
            );
            default -> new MappedOsbError(
                    409,
                    new OsbErrorPayload(
                            "",
                            failure.safeDescription()
                    )
            );
        };
    }
}
```

Đây là ví dụ minh họa cấu trúc mapper, không phải bảng mapping phổ quát cho mọi thao tác OSB API. Mã `InvalidParameters` hoặc các mã lỗi riêng phải được kiểm tra theo phiên bản đặc tả và contract platform; nếu không có mã chuẩn tương ứng, không phát minh mã portable. Status cho instance không tồn tại, xung đột hoặc lỗi provider cũng phải theo semantics của endpoint cụ thể. Trong triển khai thật, có thể dùng response model và exception mapping mà Spring Cloud Open Service Broker cung cấp thay vì tự dựng `MappedOsbError`.

## 10. Tích hợp exception mapping trong Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction cho lỗi nghiệp vụ OSB và chuyển chúng thành HTTP response. Các exception class, constructor và cách đăng ký phụ thuộc phiên bản thư viện. Một số tình huống thường cần mapping gồm:

- Instance hoặc binding không tồn tại.
- Instance/binding đã tồn tại hoặc request xung đột.
- Parameters không hợp lệ.
- Service/plan không hỗ trợ thao tác.
- Operation cần xử lý bất đồng bộ nhưng request không chấp nhận async.
- Provider tạm thời không khả dụng.

Hãy dùng exception type và extension point của phiên bản dependency đang dùng. Tránh thêm một `@RestControllerAdvice` toàn cục bắt mọi exception rồi trả JSON tự định nghĩa cho toàn bộ `/v2/**`; cách đó có thể ghi đè status code, error body hoặc semantics mà framework OSB đã triển khai.

Nếu ứng dụng có API quản trị nội bộ ngoài OSB, có thể dùng `@RestControllerAdvice` riêng cho package/path đó. Với endpoint OSB, hãy để adapter OSB xử lý exception theo contract hoặc cấu hình mapping ở extension point được hỗ trợ.

### Ví dụ tách public description khỏi cause

```java
public final class SafeBrokerException extends RuntimeException {
    private final BrokerErrorCode code;
    private final String publicDescription;

    public SafeBrokerException(
            BrokerErrorCode code,
            String publicDescription,
            Throwable cause
    ) {
        super(code.name(), cause);
        this.code = code;
        this.publicDescription = publicDescription;
    }

    public BrokerErrorCode code() {
        return code;
    }

    public String publicDescription() {
        return publicDescription;
    }
}
```

Khi adapter ánh xạ exception, chỉ dùng `code` và `publicDescription` đã được duyệt. Không dùng `getMessage()` của cause làm description. Khi log, cũng không in stack trace nguyên gốc nếu provider exception có thể chứa request/response hoặc credential; cần bộ lọc chẩn đoán phù hợp.

## 11. Xử lý lỗi từ provider

Provider có thể trả lỗi rất chi tiết, nhưng broker cần chuyển nó thành lỗi ổn định và an toàn.

| Provider error | Mã nội bộ gợi ý | Nội dung công khai |
|---|---|---|
| Rate limit | `PROVIDER_RATE_LIMITED` | `Nhà cung cấp đang giới hạn yêu cầu. Hãy thử lại sau.` |
| Authentication rejected | `PROVIDER_AUTH_REJECTED` | `Broker chưa thể xác thực với nhà cung cấp. Mã tham chiếu: ...` |
| Resource quota exceeded | `PROVIDER_QUOTA_EXCEEDED` | `Không thể tạo tài nguyên do giới hạn quota của dịch vụ.` |
| Temporary unavailable | `PROVIDER_UNAVAILABLE` | `Dịch vụ phụ thuộc tạm thời không khả dụng.` |
| Resource conflict | `PROVIDER_RESOURCE_CONFLICT` | `Tài nguyên đang ở trạng thái xung đột và cần được kiểm tra.` |
| Unknown response | `PROVIDER_UNKNOWN_FAILURE` | `Không thể hoàn tất thao tác. Hãy liên hệ hỗ trợ với mã tham chiếu.` |

Mapping phải dựa trên loại lỗi và semantics provider, không chỉ dựa vào việc mọi lỗi đều là HTTP 4xx/5xx. Ví dụ provider 429 có thể cho phép retry sau `Retry-After`; provider 401 thường cần sửa credential cấu hình và không nên retry liên tục.

Không đưa raw provider error body vào `description`. Có thể lưu mã lỗi provider đã chuẩn hóa, provider request ID và operation ID trong log bảo mật để điều tra.

## 12. Retryability và header hỗ trợ

Một response lỗi có thể hướng dẫn platform hoặc operator về việc thử lại, nhưng broker cần phân biệt retry an toàn và retry có thể tạo side effect trùng.

- Lỗi validation thường không retry cho tới khi request được sửa.
- Lỗi xác thực broker/provider cần xử lý cấu hình hoặc quyền trước khi retry.
- Rate limit có thể retry sau khoảng thời gian được chỉ định nếu operation idempotent.
- Timeout sau khi provider có thể đã thực hiện side effect cần lookup/reconciliation trước khi gửi lại create.
- Conflict do operation đang chạy cần kiểm tra `last_operation` hoặc chờ trạng thái hiện tại.

`Retry-After` là header HTTP tiêu chuẩn có thể được dùng trong các tình huống phù hợp. Chỉ gửi khi broker có ước lượng đáng tin cậy và platform có thể sử dụng header đó. Không thêm custom field `retryable: true` rồi giả định client sẽ hiểu. Tính retryable còn phụ thuộc idempotency key, trạng thái provider và loại thao tác.

## 13. Phần mở rộng và tương thích ngược

Nếu cần extension riêng, hãy thiết kế theo nguyên tắc:

1. Namespace để tránh trùng key với extension của bên khác.
2. Tài liệu hóa schema, kiểu dữ liệu, semantics, version và consumer cụ thể.
3. Field extension là tùy chọn đối với client không hỗ trợ; phần chuẩn vẫn đủ để xử lý lỗi cơ bản.
4. Không đổi ý nghĩa của `error`, `description` hoặc HTTP status bằng extension.
5. Không đưa secret, stack trace hoặc internal topology vào extension.
6. Có contract test với từng platform/adapter thực sự đọc extension.
7. Có kế hoạch versioning và bỏ field khi tích hợp không còn dùng.

Ví dụ extension có thể cung cấp `supportReference` hoặc link tới trang hỗ trợ của broker. Nếu dùng URL, bảo đảm URL không chứa token và có thể truy cập đúng đối tượng. Không đưa internal admin URL hoặc đường dẫn chỉ hoạt động trong mạng riêng cho platform bên ngoài.

Không thêm các trường như `providerResponse`, `stackTrace`, `requestBody`, `debugInfo` hoặc `credentials` vào error body. Chúng vừa không cần thiết cho client vừa tạo nguy cơ rò rỉ dữ liệu.

## 14. Bảo mật và redaction trong lỗi

Error response thường được lưu ở platform log, CLI output, ticket hoặc telemetry. Broker cần bảo vệ nội dung như bảo vệ log:

- Không phản chiếu password, token, private key, Authorization header hoặc cookie.
- Không trả connection string có credential hoặc URL query chứa API key.
- Không trả SQL, stack trace, tên bảng, file path hoặc hostname nội bộ.
- Không trả raw provider response, request body hoặc serialized DTO.
- Không dùng tenant ID hoặc instance metadata nhạy cảm nếu không cần thiết.
- Dùng mã tham chiếu ngẫu nhiên/opaque để liên kết với log đã làm sạch.
- Chỉ log các trường an toàn như operation ID, error category, provider request ID đã được kiểm soát và thời gian xử lý.

Ví dụ response an toàn:

```json
{
  "error": "ProviderUnavailable",
  "description": "Không thể hoàn tất thao tác. Mã tham chiếu: op-7f2a91."
}
```

Ví dụ này vẫn dùng `ProviderUnavailable` như mã tích hợp minh họa; nếu platform không hiểu mã tùy chỉnh, broker nên dựa vào status và description phù hợp contract chuẩn. Mã tham chiếu không nên cho phép truy cập log hoặc tài nguyên nếu không có xác thực.

## 15. Kiểm thử error contract

Kiểm thử cần xác minh cả status code, body và khả năng tương thích:

1. Lỗi validation trả status và JSON body theo mapping OSB API.
2. `description` luôn có nội dung an toàn, dễ hiểu và không rỗng trong error response theo contract.
3. `error` chỉ chứa mã chuẩn hoặc mã extension đã thống nhất; không chứa class name.
4. `AsyncRequired` dùng đúng status và description để platform biết cần bật `accepts_incomplete`.
5. Lỗi operation async sau khi đã accept được biểu diễn qua `last_operation.state=failed`, không bị nhầm thành lỗi HTTP của request polling.
6. Extension có schema đúng và client không hỗ trợ extension vẫn xử lý được phần chuẩn.
7. Không có password/token sentinel trong response, log, trace hoặc metric.
8. Provider 429/5xx/timeout được phân loại đúng và không tạo retry không an toàn.
9. Exception handler không ghi đè error mapping của Spring Cloud Open Service Broker.
10. Các mã lỗi/status được kiểm thử theo từng endpoint: catalog, provision, update, bind, unbind, deprovision và last_operation.

Ví dụ test response bằng MockMvc cho một endpoint nội bộ minh họa:

```java
mockMvc.perform(post("/internal/provision")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"storage_gb\":-1}"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.description").isNotEmpty())
    .andExpect(jsonPath("$.description").value(
            not(containsString("TEST_SECRET"))));
```

Đối với endpoint OSB do framework cung cấp, nên viết contract test qua chính route OSB và xác minh JSON được serialize thực tế. Không chỉ test mapper unit vì controller advice hoặc framework handler có thể thay đổi kết quả cuối cùng.

## 16. Checklist trước khi phát hành

- HTTP status phản ánh đúng semantics của endpoint OSB API.
- Error body có `description` rõ ràng và an toàn.
- `error` dùng mã chuẩn khi đặc tả định nghĩa; mã riêng được thỏa thuận rõ.
- Không serialize exception hoặc provider response nguyên gốc.
- `AsyncRequired` và các mã chuẩn khác được xử lý theo đúng phiên bản API.
- Lỗi operation async được biểu diễn bằng `last_operation` sau khi request đã được accept.
- Extension có namespace, schema, version và consumer cụ thể.
- Client không hỗ trợ extension vẫn dùng được phần response chuẩn.
- Retry guidance không khuyến khích lặp side effect không idempotent.
- `Retry-After` chỉ được dùng khi phù hợp và có giá trị đáng tin cậy.
- Secret, stack trace, SQL và internal topology không xuất hiện trong body/log.
- Contract test chạy qua endpoint OSB thực tế và kiểm tra status/body.

Cấu trúc lỗi tốt giúp platform xử lý đúng request thất bại và giúp con người biết bước tiếp theo. Hãy giữ HTTP status đúng semantics, dùng `error` làm mã nhận diện ổn định khi hợp đồng hỗ trợ, viết `description` ngắn gọn và an toàn, đồng thời chỉ thêm extension khi platform cụ thể đã thống nhất cách sử dụng. Trong Spring Cloud Service Broker, một lớp mapping rõ ràng giữa exception nội bộ và error contract OSB sẽ giữ API nhất quán qua các provider, thao tác vòng đời và lần phát hành.
