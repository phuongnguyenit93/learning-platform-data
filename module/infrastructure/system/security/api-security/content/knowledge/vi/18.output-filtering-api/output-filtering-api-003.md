# Mask secret, token, internal ID và debug data

API có thể xác thực và phân quyền đúng nhưng vẫn làm lộ thông tin qua response. Một endpoint trả toàn bộ entity có thể vô tình gửi password hash, API key, access token, refresh token, internal ID, stack trace, câu SQL hoặc dữ liệu debug mà client không cần. Thông tin này có thể giúp kẻ tấn công chiếm credential, dò cấu trúc hệ thống, liên kết dữ liệu giữa tenant hoặc tìm đường khai thác tiếp theo.

Output filtering là việc kiểm soát dữ liệu được đưa ra khỏi API theo hợp đồng response và quyền của caller. Cách an toàn là xác định rõ trường nào được phép xuất hiện, trường nào cần che một phần và trường nào tuyệt đối không được trả. Việc mask chỉ phù hợp khi người nhận thực sự cần một phần giá trị; với secret dùng để xác thực, thông thường phải loại bỏ hoàn toàn.

## 1. Vì sao response cần được lọc?

Request validation và authorization kiểm soát dữ liệu đi vào cùng hành động được phép thực hiện. Output filtering kiểm soát dữ liệu đi ra sau khi xử lý. Đây là một lớp riêng vì entity hoặc domain object thường chứa nhiều thông tin hơn response mà client cần.

Ví dụ, một bản ghi tích hợp có thể chứa:

```json
{
  "id": "db-row-882193",
  "clientId": "partner-reporting",
  "apiKey": "ak_live_...secret...",
  "refreshToken": "eyJ...",
  "webhookSecret": "whsec_...",
  "createdByInternalUserId": "usr-internal-771",
  "lastError": "SQL connection failed at db-prod-03",
  "debugContext": {
    "sql": "select * from integrations where id = 882193",
    "stackTrace": "com.example..."
  }
}
```

Một màn hình quản trị tích hợp có thể chỉ cần tên client, trạng thái, thời điểm tạo và vài ký tự cuối của key để người vận hành nhận diện. Trả toàn bộ object làm lộ nhiều dữ liệu không cần thiết.

Rủi ro phổ biến gồm:

- Secret hoặc token xuất hiện trong response, kể cả endpoint chỉ nhằm xem metadata.
- Internal ID tiết lộ cấu trúc database hoặc cho phép liên kết bản ghi giữa các API.
- Debug field tiết lộ hostname, đường dẫn, phiên bản thư viện, câu SQL, stack trace hoặc cấu hình nội bộ.
- Error response trả nguyên exception message từ thư viện hoặc hệ thống ngoài.
- Nested object, bulk response, export hoặc GraphQL field làm lộ trường mà endpoint chính đã che.
- Một thay đổi entity thêm trường mới khiến serializer tự động đưa trường đó vào response.

## 2. Phân loại trường trước khi thiết kế response

Không thể quyết định mask hay bỏ trường nếu chưa biết trường đó có ý nghĩa gì, ai cần sử dụng và hậu quả khi bị lộ. Hãy phân loại dữ liệu theo mức độ nhạy cảm và mục đích sử dụng.

| Nhóm | Ví dụ | Cách xử lý mặc định |
|---|---|---|
| Công khai | Tên sản phẩm, mã danh mục công khai | Có thể trả theo hợp đồng API |
| Nội bộ | Internal ID, mã workflow, tên service | Chỉ trả nếu client cần và có quyền phù hợp |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ | Chỉ trả phần cần thiết theo mục đích và quyền |
| Secret xác thực | Password, API key, private key, client secret | Không trả lại sau khi cấp; không mask để biến thành dữ liệu có thể dùng |
| Token/credential | Access token, refresh token, session cookie | Không trả qua endpoint metadata; chỉ phát hành trong flow xác thực được thiết kế riêng |
| Dữ liệu vận hành nhạy cảm | Host nội bộ, stack trace, SQL, filesystem path | Không đưa vào response production |
| Dữ liệu debug | Feature flag nội bộ, request context, biến môi trường | Chỉ dùng trong môi trường và kênh debug được kiểm soát |

Một trường có thể thuộc nhiều nhóm. Ví dụ email vừa là dữ liệu cá nhân vừa có thể là định danh đăng nhập. Chính sách phải xét mục đích của endpoint, caller và môi trường, không chỉ dựa vào tên field.

### 2.1. Phân biệt secret với dữ liệu cần nhận diện

Secret dùng để chứng minh quyền sở hữu credential phải được giữ bí mật. Sau khi tạo API key hoặc webhook secret, hệ thống thường chỉ hiển thị giá trị đầy đủ một lần. Các lần xem sau nên trả metadata và prefix/suffix nhận diện, ví dụ `ak_live_...7f3a`, nếu điều đó thực sự giúp quản trị viên chọn đúng key.

Masking không làm một secret trở nên an toàn để trả nếu phần còn lại vẫn đủ để sử dụng, hoặc nếu giá trị bị lộ ở nơi khác. Với access token, refresh token, password, private key và client secret, mặc định là không serialize ra response. Nếu cần cấp lại credential, dùng flow phát hành/rotate riêng và chỉ hiển thị secret mới một lần.

### 2.2. Internal ID không phải lúc nào cũng là secret

Internal ID như khóa số tự tăng, primary key hoặc mã định danh service không phải lúc nào cũng là bí mật. Tuy nhiên, trả chúng không cần thiết có thể làm lộ chi tiết triển khai, hỗ trợ enumeration hoặc tạo khả năng liên kết dữ liệu giữa các API.

Hãy phân biệt:

- ID công khai được thiết kế trong hợp đồng API, ví dụ UUID hoặc public resource ID.
- ID nội bộ dùng cho database, message broker hoặc hệ thống vận hành.
- ID của chủ thể khác, tenant khác hoặc hệ thống nội bộ mà caller không có quyền biết.

Nếu client cần tham chiếu resource, cung cấp public ID riêng và kiểm tra authorization trên mọi lần sử dụng. Không coi UUID khó đoán là biện pháp phân quyền. Nếu client không cần ID nội bộ, bỏ nó khỏi response thay vì chỉ đổi định dạng.

## 3. Ưu tiên response DTO allowlist

Không trả trực tiếp JPA entity, ORM model hoặc domain object từ controller. Entity có thể chứa trường bí mật, quan hệ lồng nhau, metadata audit và các trường được thêm trong tương lai. Serializer tự động có thể đưa chúng vào JSON ngoài ý muốn.

Tạo response DTO riêng với đúng những trường endpoint được phép trả:

```java
public record IntegrationSummaryResponse(
        String publicId,
        String displayName,
        String status,
        Instant createdAt,
        String keyHint) {}
```

Mapper chủ động chọn trường:

```java
public IntegrationSummaryResponse toSummary(Integration integration) {
    return new IntegrationSummaryResponse(
            integration.getPublicId(),
            integration.getDisplayName(),
            integration.getStatus().name(),
            integration.getCreatedAt(),
            maskKeyHint(integration.getKeyPrefix(), integration.getKeySuffix())
    );
}
```

`IntegrationSummaryResponse` không có thuộc tính `apiKey`, `refreshToken`, `webhookSecret`, `databaseId` hoặc `debugContext`, nên mapper không thể vô tình trả chúng qua response này.

### 3.1. Mỗi use case có response model phù hợp

Không nhất thiết phải dùng một DTO duy nhất cho mọi role và mọi endpoint. Có thể định nghĩa các response model theo use case:

| Use case | Trường được phép |
|---|---|
| Danh sách tích hợp | Public ID, tên, trạng thái, ngày tạo |
| Chi tiết tích hợp | Các trường cấu hình không bí mật, key hint, thời điểm sử dụng gần nhất |
| Tạo API key | Secret mới một lần, key ID và hướng dẫn lưu an toàn |
| Xem lại API key | Key ID, prefix/suffix, trạng thái, ngày tạo/hết hạn; không có secret |
| Điều tra sự cố nội bộ | Mã lỗi, correlation ID và dữ liệu vận hành đã lọc theo quyền đặc biệt |

Nếu một endpoint cần response khác nhau theo quyền, hãy dùng mapper/policy rõ ràng hoặc các DTO riêng. Tránh serialize toàn bộ entity rồi dùng nhiều annotation hoặc điều kiện ngầm để ẩn từng trường mà reviewer khó kiểm tra.

### 3.2. Không dựa vào annotation che trường như lớp bảo vệ duy nhất

Các annotation như `@JsonIgnore`, `@JsonView` hoặc custom serializer có thể hữu ích, nhưng cần hiểu phạm vi áp dụng và đường serialize thực tế. Một endpoint khác, một nested object, một export job hoặc một thư viện serialize khác có thể không áp dụng cùng rule.

DTO allowlist là ranh giới rõ ràng hơn. Nếu vẫn dùng annotation, hãy kiểm thử response thực tế ở mọi endpoint và đảm bảo field nhạy cảm không xuất hiện khi object được serialize qua đường khác.

## 4. Xử lý secret, token và credential

### 4.1. Không trả lại secret đã lưu

Với API key do hệ thống phát hành, server nên lưu digest hoặc HMAC để xác minh request, không cần lưu secret nguyên bản. Khi tạo key, response có thể hiển thị secret mới đúng một lần:

```json
{
  "keyId": "key_7f3a91c2",
  "secret": "ak_live_...one-time-value...",
  "createdAt": "2026-11-18T10:00:00Z"
}
```

Các endpoint `GET /api/keys/{id}` hoặc danh sách key chỉ trả metadata:

```json
{
  "keyId": "key_7f3a91c2",
  "keyHint": "ak_live_...91c2",
  "status": "ACTIVE",
  "createdAt": "2026-11-18T10:00:00Z",
  "lastUsedAt": "2026-11-18T10:15:00Z"
}
```

Nếu người dùng làm mất secret, cung cấp thao tác rotate/revoke để phát hành key mới. Không tạo endpoint đọc lại secret từ database chỉ để thuận tiện hỗ trợ.

### 4.2. Token chỉ xuất hiện trong flow phát hành có chủ đích

Access token và refresh token có thể cần được trả về trong token endpoint theo OAuth/OIDC hoặc flow xác thực đã thiết kế. Điều đó không có nghĩa token được phép xuất hiện trong:

- Endpoint xem hồ sơ người dùng hoặc session metadata.
- Endpoint quản lý API key hoặc cấu hình tích hợp.
- Error response, audit event hoặc debug endpoint.
- Response của endpoint proxy dữ liệu người dùng.
- Header hoặc body của API không liên quan đến việc phát hành token.

Token endpoint cần kiểm soát cache, truyền tải TLS, thời hạn, scope và cách client lưu credential theo đúng giao thức. Không dùng quy tắc “không bao giờ trả token” một cách máy móc; phải phân biệt endpoint phát hành credential được thiết kế riêng với endpoint dữ liệu thông thường.

### 4.3. Mask chỉ khi phần giá trị còn lại không thể dùng như credential

Một key hint như `sk_live_...A91C` có thể giúp phân biệt key trong giao diện quản trị. Không nên chỉ hiển thị vài ký tự đầu nếu prefix giống nhau ở mọi key; cũng không hiển thị đủ entropy để đoán hoặc khôi phục secret. Với token, không trả một phần token nếu phần đó vẫn tạo rủi ro liên kết hoặc làm lộ dữ liệu không cần thiết.

Không dùng masking thay cho kiểm soát truy cập. Người không có quyền xem metadata của key cũng không nên được xem key hint, trạng thái hoặc thời điểm sử dụng nếu các thông tin đó nhạy cảm.

## 5. Mask dữ liệu cá nhân theo mục đích

Không phải mọi dữ liệu nhạy cảm đều cần loại bỏ hoàn toàn. Một số quy trình cần hiển thị dạng rút gọn để người dùng xác nhận đúng tài khoản hoặc thông tin liên hệ.

Ví dụ:

| Dữ liệu gốc | Response được phép trong use case phù hợp |
|---|---|
| `an.nguyen@example.com` | `a***@example.com` |
| `0901234567` | `******4567` |
| Số giấy tờ định danh | Chỉ hiển thị 3–4 ký tự cuối nếu quy định cho phép |
| Số tài khoản ngân hàng | Chỉ hiển thị một phần cuối theo chuẩn của nghiệp vụ |
| Địa chỉ nhà | Chỉ hiển thị phần cần thiết cho mục đích giao nhận |

Masking phải được xác định theo loại dữ liệu, chính sách tổ chức và mục đích. Không áp dụng một hàm mask chung cho email, số điện thoại, số tài khoản và mã định danh vì mỗi loại có cấu trúc khác nhau.

Ví dụ hàm mask số điện thoại:

```java
public String maskPhone(String value) {
    if (value == null || value.length() < 4) {
        return null;
    }
    return "*".repeat(value.length() - 4) + value.substring(value.length() - 4);
}
```

Đây chỉ là ví dụ đơn giản cho chuỗi đã chuẩn hóa. Trong ứng dụng thật, cần xử lý mã quốc gia, khoảng trắng, ký tự phân tách và định dạng hiển thị. Không mask dữ liệu ở tầng database nếu nghiệp vụ vẫn cần giá trị đầy đủ để xử lý; hãy tạo projection/response phù hợp tại ranh giới xuất dữ liệu.

## 6. Loại bỏ internal ID và metadata không cần thiết

Một response thường không cần trả toàn bộ khóa nội bộ của database, ID của service khác hoặc mã tham chiếu của message broker. Hãy thiết kế public resource ID và chỉ trả những định danh cần cho client.

Ví dụ response không nên chứa:

```json
{
  "id": 882193,
  "databaseShard": "orders-db-shard-07",
  "tenantInternalPk": 1402,
  "kafkaPartition": 12,
  "consumerGroup": "payment-worker-prod"
}
```

Response công khai có thể chỉ cần:

```json
{
  "orderId": "ord_01J8YQ7K3F5M",
  "status": "PAID"
}
```

Public ID vẫn phải được bảo vệ bằng object-level authorization. ID khó đoán chỉ giảm khả năng enumeration; nó không chứng minh caller có quyền truy cập resource.

Không nhất thiết phải thay mọi ID số bằng UUID. Hãy chọn public identifier theo nhu cầu API, khả năng tương thích, index và rủi ro enumeration. Quan trọng là không để internal database key trở thành một API contract ngoài ý muốn và không dựa vào độ khó đoán của ID để phân quyền.

## 7. Loại bỏ debug data và thông tin hạ tầng

Debug data hữu ích trong môi trường phát triển nhưng có thể giúp attacker hiểu cấu trúc nội bộ. Response production không nên trả:

- Stack trace, exception class và source line.
- Câu SQL, tên bảng, tên cột hoặc query parameter nội bộ.
- Hostname, IP private, port, service discovery name và đường dẫn filesystem.
- Environment variable, secret manager path hoặc tên secret.
- Tên class, package, framework version hoặc dependency version không cần thiết.
- Internal request header, trace baggage hoặc thông tin của service upstream.
- Feature flag nội bộ, debug mode, timing chi tiết hoặc dữ liệu profiling.

### 7.1. Error response ổn định

Không trả trực tiếp `exception.getMessage()` hoặc stack trace ra client. Dùng mã lỗi ổn định và thông điệp phù hợp với hợp đồng API:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception exception) {
        String correlationId = UUID.randomUUID().toString();

        // Ghi exception đầy đủ vào hệ thống log nội bộ đã được kiểm soát.
        log.error("Unexpected API error, correlationId={}",
                correlationId, exception);

        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Internal server error");
        problem.setDetail("The request could not be completed.");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("correlationId", correlationId);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
```

Ví dụ trên cần được tích hợp với logging policy thực tế. Không ghi request header chứa token hoặc body nhạy cảm cùng exception. Correlation ID nên là mã ngẫu nhiên không chứa user ID, tenant ID hoặc thông tin nội bộ có thể suy ra.

### 7.2. Phân biệt lỗi dự kiến và lỗi bất ngờ

Lỗi validation, authentication, authorization, conflict hoặc rate limit nên có mã và status phù hợp. Lỗi bất ngờ trả thông báo chung, còn chi tiết điều tra nằm trong log nội bộ có kiểm soát.

| Loại lỗi | Response thường dùng | Dữ liệu cần tránh |
|---|---|---|
| Validation | `400` với field/code lỗi | Stack trace, payload bí mật, câu parser nội bộ |
| Authentication | `401` | Chi tiết khóa ký, token parse hoặc credential hợp lệ |
| Authorization | `403` hoặc `404` theo chính sách | Role nội bộ, policy expression, resource ngoài phạm vi |
| Conflict | `409` | Chi tiết database constraint hoặc SQL |
| Rate limit | `429` | Bộ đếm của client khác, cấu trúc kho Redis |
| Unexpected error | `500` | Exception message, stack trace, hostname, filesystem path |

Không dùng một response `500` cho mọi lỗi nghiệp vụ. Ngược lại, cũng không biến mọi exception thành response chi tiết để client dễ debug.

## 8. Lọc nested object, collection và bulk response

Output filtering phải áp dụng đệ quy và nhất quán cho các object lồng nhau. Một DTO cha an toàn vẫn có thể chứa nested entity có trường bí mật.

Ví dụ:

```json
{
  "orderId": "ord_01J8YQ7K3F5M",
  "customer": {
    "displayName": "An Nguyen",
    "email": "an.nguyen@example.com",
    "passwordHash": "$2a$..."
  },
  "payment": {
    "status": "PAID",
    "providerTransactionId": "internal-txn-778",
    "providerAccessToken": "eyJ..."
  }
}
```

Endpoint có thể cần tên khách hàng và trạng thái thanh toán nhưng không cần password hash hoặc provider token. Hãy tạo nested DTO riêng thay vì nhúng entity `Customer` hoặc `Payment`.

Với collection và bulk API:

- Áp dụng cùng response schema cho từng phần tử.
- Kiểm tra quyền trên từng resource nếu kết quả có thể chứa nhiều tenant hoặc owner.
- Không để một phần tử lỗi khiến exception trả raw object hoặc debug context của cả batch.
- Giới hạn số phần tử và kích thước response để tránh lạm dụng tài nguyên.
- Kiểm tra export CSV, Excel, PDF và file download; output filtering không chỉ áp dụng cho JSON.

Với GraphQL, client có thể chọn field cần lấy. Resolver phải kiểm tra quyền theo field và object; việc field không xuất hiện trên UI không ngăn client truy vấn trực tiếp. Với gRPC hoặc message API, định nghĩa protobuf/schema cũng cần tránh trường nội bộ không dành cho consumer.

## 9. Output filtering phải gắn với authorization

Response filtering và authorization giải quyết hai câu hỏi khác nhau:

- Authorization: caller có được truy cập resource hoặc hành động này không?
- Output filtering: trong dữ liệu được phép truy cập, những field nào được trả?

Không dùng masking để cho phép một caller không có quyền truy cập resource. Nếu user không được xem hồ sơ, trả email dạng `a***@example.com` vẫn có thể làm lộ việc hồ sơ tồn tại hoặc tiết lộ thông tin. Trước tiên phải quyết định caller có được đọc resource; sau đó mới áp dụng field-level policy.

Ví dụ policy:

```java
public CustomerView toView(Customer customer, Actor actor) {
    authorization.requireCanReadCustomer(actor, customer);

    boolean canReadFullEmail = authorization.canReadProperty(
            actor, customer, "email");

    return new CustomerView(
            customer.getPublicId(),
            customer.getDisplayName(),
            canReadFullEmail
                    ? customer.getEmail()
                    : maskEmail(customer.getEmail())
    );
}
```

Ví dụ này chỉ minh họa. Nếu caller không có quyền đọc email dưới bất kỳ hình thức nào, nên bỏ field thay vì mask. Cũng cần xem xét quyền đọc có thể thay đổi theo mục đích, quan hệ sở hữu, tenant hoặc trạng thái xác minh.

## 10. Kiểm soát cache và response header

Ngay cả khi body đã được lọc, cache hoặc header có thể làm lộ dữ liệu. Với response chứa dữ liệu cá nhân, thông tin tài khoản hoặc nội dung phụ thuộc quyền caller, cần cấu hình cache phù hợp.

Một số điểm cần xem xét:

- Dùng `Cache-Control: no-store` cho response chứa token, credential hoặc dữ liệu xác thực nhạy cảm khi phù hợp với giao thức.
- Không để shared cache lưu response riêng tư rồi trả cho caller khác.
- Nếu cho phép cache dữ liệu phụ thuộc người dùng, cache key và `Vary` phải phản ánh đúng ngữ cảnh; không chỉ dựa vào URL nếu nội dung thay đổi theo principal.
- Không đưa token, session ID hoặc secret vào `ETag`, URL hoặc custom response header.
- Kiểm tra header như `Server`, `X-Powered-By`, internal trace header và upstream metadata; loại bỏ những thông tin không cần công bố.
- Với file export, kiểm tra metadata trong tên file, thuộc tính document, hidden sheet, comment và embedded data.

Không phải mọi response đều cần `no-store`; dữ liệu công khai có thể cache để cải thiện hiệu năng. Chính sách cache cần dựa trên phân loại dữ liệu và cách xác định caller.

## 11. Log và telemetry cũng là một dạng output

Output filtering không dừng ở response HTTP. Dữ liệu được ghi ra log, trace, metric, audit event, exception tracker hoặc công cụ session replay cũng rời khỏi ranh giới của ứng dụng.

Không ghi:

- `Authorization`, `Cookie`, access token, refresh token hoặc API key.
- Password, private key, client secret, webhook secret.
- Toàn bộ request/response body nếu có dữ liệu cá nhân hoặc thanh toán.
- Stack trace hoặc SQL vào log mà người dùng hoặc hệ thống bên ngoài có thể đọc.
- Query string chứa credential hoặc dữ liệu nhạy cảm.

Có thể ghi metadata tối thiểu như method, route template, status code, duration, correlation ID, key ID hoặc client ID đã được phân loại phù hợp. Với audit event, ghi actor, action, resource reference và kết quả; không cần sao chép secret hoặc giá trị dữ liệu nhạy cảm đầy đủ.

### 11.1. Redaction ở nhiều tầng

Áp dụng redaction tại logger/application, API gateway, reverse proxy, APM và hệ thống lưu trữ log. Nếu chỉ che ở application logger nhưng gateway ghi toàn bộ `Authorization` header, credential vẫn bị lộ.

Quy tắc redaction cần được kiểm thử bằng một giá trị giả có thể tìm kiếm. Gửi request với token fixture, sau đó xác minh giá trị không xuất hiện trong log, trace, error report hoặc telemetry. Không dùng token thật để thử nghiệm redaction.

## 12. Kiểm thử output filtering

Kiểm thử cần xác minh cả trường được phép xuất hiện và trường tuyệt đối không được xuất hiện. Kiểm tra response JSON bằng schema hoặc assertion theo field sẽ ổn định hơn việc chỉ tìm một chuỗi trong response.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Xem danh sách API key | Chỉ có key ID/hint và metadata; không có secret |
| Xem chi tiết API key đã tạo | Không thể đọc lại secret gốc |
| Tạo API key mới | Secret chỉ xuất hiện trong response tạo một lần theo hợp đồng |
| Xem session metadata | Không có access token, refresh token hoặc cookie |
| User không có quyền đọc field nhạy cảm | Field bị bỏ hoặc mask đúng policy |
| User không có quyền đọc resource | Bị từ chối/che resource; không lộ field mask |
| Response có nested customer/payment | Không có password hash hoặc provider token ở object con |
| Bulk response hoặc export | Mọi phần tử và cột đều tuân thủ allowlist |
| Exception bất ngờ | Response không có stack trace, SQL hoặc hostname nội bộ |
| Validation lỗi | Chỉ trả mã/field lỗi được phép công bố |
| Cache response riêng tư | Caller khác không nhận response của người trước |
| Header response | Không có token, internal host hoặc debug header ngoài hợp đồng |
| Logging và tracing | Token fixture và secret không xuất hiện trong telemetry |
| Thêm field mới vào entity | Field không tự xuất hiện trong response DTO |
| GraphQL field hoặc gRPC message | Field nhạy cảm được bảo vệ ở resolver/schema phù hợp |

Nên có test snapshot hoặc schema contract cho response công khai, nhưng không nên lưu snapshot chứa dữ liệu thật. Dùng fixture giả và assertion cấm các field như `password`, `passwordHash`, `accessToken`, `refreshToken`, `apiKey`, `clientSecret`, `privateKey`, `stackTrace`, `sql` và các trường debug nội bộ.

### 12.1. Ví dụ test response không chứa secret

```java
@Test
void integrationSummaryDoesNotExposeSecrets() throws Exception {
    mockMvc.perform(get("/api/integrations/{id}", integrationId)
            .with(user("operator").authorities(
                    () -> "integrations:read")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.publicId").exists())
        .andExpect(jsonPath("$.keyHint").exists())
        .andExpect(jsonPath("$.apiKey").doesNotExist())
        .andExpect(jsonPath("$.refreshToken").doesNotExist())
        .andExpect(jsonPath("$.debugContext").doesNotExist());
}
```

Đây là ví dụ dùng MockMvc; cần điều chỉnh principal, authority và fixture theo ứng dụng. Nên bổ sung test cho nested field, error response, export và log redaction.

## 13. Những lỗi triển khai thường gặp

**Trả thẳng entity từ controller.** Entity thay đổi có thể làm response tự động xuất hiện field mới. Dùng DTO allowlist và mapper rõ ràng.

**Chỉ dùng `@JsonIgnore` rồi cho rằng mọi đường serialize đều an toàn.** Một exporter hoặc serializer khác có thể bỏ qua annotation. Kiểm thử contract trên mọi endpoint và định dạng.

**Mask token thay vì loại bỏ.** Một phần token có thể vẫn là thông tin nhạy cảm hoặc hỗ trợ liên kết. Credential không cần hiển thị lại thì không đưa vào response.

**Trả internal ID vì “không phải secret”.** ID có thể giúp enumeration hoặc liên kết dữ liệu không cần thiết. Chỉ công bố public ID theo hợp đồng và luôn kiểm tra authorization.

**Trả nguyên exception message để client debug.** Exception có thể chứa SQL, hostname, file path hoặc secret. Dùng error code ổn định và correlation ID.

**Chỉ lọc top-level object.** Nested entity, bulk export hoặc GraphQL resolver có thể lộ trường con. Dùng nested DTO và test đệ quy.

**Che dữ liệu ở giao diện nhưng API vẫn trả đầy đủ.** Client có thể gọi API trực tiếp. Filtering phải thực hiện ở server trước khi serialize response.

**Quên log, trace và cache.** Credential có thể không xuất hiện trong response nhưng lại bị ghi vào APM hoặc shared cache. Redaction và cache policy phải bao phủ toàn bộ đường dữ liệu.

## 14. Checklist thiết kế output filtering

Trước khi phát hành endpoint, hãy xác nhận:

- [ ] Đã phân loại dữ liệu theo mức nhạy cảm và mục đích sử dụng.
- [ ] Response dùng DTO/projection allowlist, không serialize trực tiếp entity.
- [ ] Secret, password, private key, API key và client secret không xuất hiện ngoài flow phát hành có chủ đích.
- [ ] Access token, refresh token và session cookie chỉ xuất hiện trong endpoint xác thực được thiết kế riêng.
- [ ] Key hint hoặc dữ liệu mask chỉ được trả khi có nhu cầu nghiệp vụ và caller có quyền.
- [ ] Internal ID được thay bằng public ID khi cần; không dựa vào ID khó đoán để phân quyền.
- [ ] Stack trace, SQL, hostname, filesystem path và debug context không xuất hiện trong response production.
- [ ] Nested object, collection, bulk response, export và GraphQL/gRPC được kiểm soát.
- [ ] Field-level authorization được kiểm tra sau khi caller có quyền đọc resource.
- [ ] Error response có mã ổn định và correlation ID, không lộ chi tiết nội bộ.
- [ ] Cache-Control, ETag và response header không làm lộ dữ liệu hoặc credential.
- [ ] Log, trace, metric và APM đã che credential và dữ liệu nhạy cảm.
- [ ] Có test xác nhận field được phép có mặt và field cấm không xuất hiện.
- [ ] Thêm field mới vào entity không tự động thay đổi public response contract.

## 15. Nguyên tắc thiết kế

Hãy xem mọi dữ liệu rời khỏi API là một output cần được kiểm soát, dù nó nằm trong JSON, header, file export, lỗi, log hay trace. Xác định trường nào client thực sự cần; tạo DTO allowlist; loại bỏ hoàn toàn credential; chỉ mask dữ liệu cá nhân khi use case cần nhận diện một phần; và không công bố internal metadata hoặc debug context ngoài mục đích vận hành được kiểm soát.

Output filtering phải đi cùng authorization ở mức resource và property. Không trả dữ liệu chỉ vì caller biết ID, không dùng mask để thay thế quyền truy cập và không dựa vào giao diện để ẩn field. **Response an toàn là response chỉ chứa dữ liệu mà caller được phép biết và thực sự cần cho chức năng đang sử dụng.**
