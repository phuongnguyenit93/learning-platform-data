# Checklist input, output, schema và error response

Trong chương **Checklist triển khai** của module `SECURITY_API_SECURITY`, một API chỉ sẵn sàng production khi dữ liệu đầu vào được kiểm tra, dữ liệu đầu ra được giới hạn theo quyền, schema có hợp đồng rõ ràng và lỗi được trả về an toàn. HTTPS hoặc authentication không ngăn được payload sai cấu trúc, mass assignment, lộ thuộc tính nội bộ, parser tiêu thụ quá nhiều tài nguyên hay error response tiết lộ stack trace.

Checklist này áp dụng cho từng endpoint và luồng nghiệp vụ. Cần xác định ai gọi endpoint, thao tác trên object nào, dữ liệu nào được phép đọc/ghi, giới hạn tài nguyên nào phải áp dụng và client được phép biết gì khi request thất bại. Kiểm tra ở gateway có thể giảm tải và chặn request rõ ràng không hợp lệ, nhưng service vẫn phải xác thực dữ liệu và quyền ở ranh giới sở hữu nghiệp vụ.

## 1. Xác định hợp đồng cho từng endpoint

Trước khi kiểm tra schema, cần có inventory endpoint và hợp đồng request/response được version hóa. Mỗi endpoint nên mô tả:

- HTTP method, route template, API version và loại client được phép gọi.
- Authentication mechanism, issuer/audience hoặc workload identity cần thiết.
- Function permission và object/tenant authorization được yêu cầu.
- Path parameter, query parameter, header và request body.
- Content type, encoding, body size, số phần tử và giới hạn độ sâu.
- Response schema theo status code, field được phép xuất hiện và phân loại dữ liệu.
- Error schema, mã lỗi ổn định và cách client xử lý retry.
- Rate limit, timeout, pagination, concurrency và chi phí xử lý.
- Side effect, idempotency và state transition của workflow.

Không dùng một schema chung cho toàn bộ API nếu các endpoint có quyền và dữ liệu khác nhau. Ví dụ, `GET /accounts/{id}` có thể trả số dư cho owner, trong khi endpoint quản trị cần thêm trường audit; hai response nên dùng DTO và policy riêng.

### Ma trận kiểm soát mẫu

| Khu vực | Câu hỏi cần trả lời | Bằng chứng trước deploy |
|---|---|---|
| Input | Caller được gửi field và giá trị nào? | OpenAPI/schema, validation rule và negative tests |
| Authorization | Principal có được thao tác trên object/tenant này không? | Policy test với nhiều principal và object |
| Output | Caller được nhìn thấy field nào? | Response DTO/schema và data classification review |
| Error | Client nhận mã lỗi nào, có lộ chi tiết nội bộ không? | Error contract test và log redaction test |
| Resource limits | Payload, list, file, parser và operation có giới hạn không? | Boundary tests, rate/concurrency tests |
| Observability | Có thể truy vết mà không log secret/PII không? | Structured logs, correlation IDs và dashboard |

## 2. Checklist kiểm tra input

### 2.1 Kiểm tra mọi nguồn đầu vào

Input không chỉ là JSON body. Phải kiểm tra dữ liệu đến từ:

- Path parameter, ví dụ `accountId`, `invoiceId` hoặc `tenantId`.
- Query parameter, filter, sort, pagination, search expression và field selection.
- Header do client gửi, gồm `Content-Type`, `Accept`, idempotency key và custom header.
- Request body, nested object, array, enum và dữ liệu polymorphic.
- File upload, multipart field, tên file, MIME type và metadata.
- Webhook/callback payload, message từ broker và dữ liệu từ service khác.
- URL/hostname mà server sẽ gọi tiếp hoặc resource reference trong payload.

Không mặc định dữ liệu từ service nội bộ là đáng tin cậy. Response của hệ thống khác vẫn cần schema validation và business validation trước khi được dùng để thay đổi trạng thái hoặc tạo outbound request.

### 2.2 Kiểm tra cú pháp, kiểu và miền giá trị

Với từng field, định nghĩa rõ:

- Bắt buộc hay tùy chọn; có chấp nhận `null` hay không.
- Kiểu dữ liệu và định dạng: UUID, timestamp, decimal, enum, email hoặc mã định danh.
- Độ dài tối thiểu/tối đa, range số và precision.
- Số phần tử tối đa trong array, độ sâu nested object và giới hạn tổng payload.
- Quy tắc normalize: Unicode, khoảng trắng, chữ hoa/thường và canonical representation.
- Giá trị mặc định do server áp dụng; không để client tự quyết định mặc định bảo mật.

Ví dụ, `amount` phải là số thập phân chính xác và nằm trong miền nghiệp vụ; `pageSize` phải có giới hạn trên; `status` chỉ nhận enum được công bố. Parse thành công không đồng nghĩa dữ liệu hợp lệ: số âm, số quá lớn hoặc trạng thái không thể chuyển tới vẫn phải bị từ chối.

### 2.3 Chặn mass assignment và field do server sở hữu

Không bind request body trực tiếp vào JPA entity hoặc domain object có các thuộc tính nhạy cảm. Những field sau thường phải do server xác định hoặc kiểm soát riêng:

- `id`, `ownerId`, `tenantId`, `createdBy`, `approvedBy`.
- `role`, `permissions`, `isAdmin`, `accountStatus`.
- `price`, `balance`, `riskLevel`, `verifiedAt`.
- `paymentStatus`, `settlementState`, `auditMetadata`.

Dùng request DTO chỉ chứa field caller được phép gửi, sau đó ánh xạ rõ ràng sang command/domain model. Nếu client gửi field không được phép, chọn chính sách nhất quán: từ chối theo schema đóng hoặc bỏ qua theo hợp đồng mở rộng đã công bố. Không âm thầm áp dụng các field nhạy cảm chỉ vì binder nhận ra tên thuộc tính.

Ví dụ DTO an toàn hơn:

```java
public record CreateTransferRequest(
    @NotNull UUID sourceAccountId,
    @NotNull UUID destinationAccountId,
    @NotNull @DecimalMin("0.01") @Digits(integer = 12, fraction = 2)
    BigDecimal amount,
    @NotBlank @Pattern(regexp = "VND|USD") String currency
) {}
```

Server lấy owner và tenant từ principal đã xác thực, kiểm tra quyền sử dụng tài khoản nguồn rồi mới tạo transfer. Không thêm `ownerId`, `tenantId` hoặc `status` vào DTO chỉ để client gửi giá trị thuận tiện.

### 2.4 Kiểm tra business rule và authorization độc lập

Schema validation trả lời dữ liệu có đúng hình dạng và miền giá trị hay không. Business validation kiểm tra điều kiện nghiệp vụ; authorization kiểm tra principal có được thực hiện hành động hay không. Ba bước này không thay thế nhau.

Ví dụ khi tạo transfer:

1. Validate `amount`, `currency`, UUID và idempotency key.
2. Xác thực principal và kiểm tra permission `transfer:create`.
3. Kiểm tra source account thuộc tenant và principal có quan hệ/quyền sử dụng tài khoản.
4. Kiểm tra account đang hoạt động, hạn mức, số dư và trạng thái giao dịch.
5. Ghi transaction/outbox theo cơ chế atomic và idempotent.

Không dùng một lỗi schema chung để che mọi lỗi authorization nếu điều đó làm hệ thống mất audit cần thiết. Đồng thời, response có thể dùng `404` thay cho `403` khi policy yêu cầu che sự tồn tại của object; quyết định này phải nhất quán với hợp đồng và không thay thế việc ghi nhận nội bộ.

### 2.5 Kiểm tra Content-Type, encoding và parser

- Chỉ nhận media type được endpoint công bố, ví dụ `application/json` hoặc loại multipart cụ thể.
- Trả `415 Unsupported Media Type` khi media type không được hỗ trợ theo hợp đồng.
- Kiểm tra charset/encoding và từ chối dữ liệu lỗi định dạng thay vì đoán nhiều encoding.
- Giới hạn request body ở gateway và ứng dụng; không chỉ tin `Content-Length` vì có thể thiếu hoặc không phản ánh dữ liệu thực tế.
- Giới hạn độ sâu JSON, kích thước string/number, số object/array và thời gian parse.
- Với XML, tắt DTD và external entity để ngăn XXE.
- Không bật polymorphic deserialization/default typing rộng cho dữ liệu không tin cậy.
- Giới hạn multipart count, file size, tổng kích thước, thời gian upload và giải nén.

Nếu endpoint hỗ trợ nén request, cần giới hạn cả kích thước sau giải nén để tránh payload nén có tỷ lệ phình lớn. Parser phải có giới hạn tài nguyên và lỗi parse không được trả stack trace.

### 2.6 Kiểm tra URL và resource reference để tránh SSRF

Nếu input chứa URL, callback address, image URL hoặc hostname mà server sẽ truy cập:

- Ưu tiên allowlist hostname/protocol/port theo integration đã đăng ký.
- Chỉ cho scheme cần thiết, thường là HTTPS; từ chối user-info và URL có cấu trúc bất thường.
- Kiểm tra DNS resolution và IP đích, chặn loopback, private, link-local, multicast và metadata service theo chính sách mạng.
- Kiểm tra lại redirect; không follow sang host/IP ngoài allowlist.
- Chống DNS rebinding bằng cách ràng buộc kiểm tra với địa chỉ thực sự được kết nối và dùng egress control.
- Đặt timeout, response size limit và content type allowlist.

Parse URL hợp lệ không chứng minh đích an toàn. Cần network egress policy ở runtime để giảm tác động nếu validation ở ứng dụng bị bypass.

### 2.7 Giới hạn resource và chống lạm dụng

Mỗi endpoint cần giới hạn phù hợp với chi phí:

- Body size, header size, array length và nested depth.
- `pageSize`, offset, filter count, sort field và query complexity.
- Request timeout, downstream timeout và tổng deadline.
- Rate limit theo IP, identity, tenant và route.
- Concurrency cho tác vụ tốn CPU/DB hoặc chạy nền.
- File upload, archive entry count, decompressed size và parser time.
- Batch size, số object được thao tác và số side effect mỗi request.

Không cho client gửi filter/sort field tùy ý để biến API thành một query engine không giới hạn. Dùng allowlist field và parameterized query; không ghép chuỗi SQL, shell command hoặc expression từ input.

## 3. Checklist kiểm tra output

### 3.1 Dùng response DTO và allowlist field

Không trả trực tiếp JPA entity, ORM object hoặc internal domain object. Serialize một response DTO riêng cho endpoint và caller role. Chỉ đưa field đã được duyệt vào DTO.

Đặc biệt kiểm tra các field:

- Secret, token, credential reference hoặc internal key material.
- Password hash, recovery code, MFA seed và session metadata.
- Internal notes, fraud score, moderation state hoặc risk signal.
- Tenant ID, owner ID hoặc relationship không cần thiết cho caller.
- Database ID, internal path, stack details và configuration metadata.
- Trường chỉ dành cho admin/support hoặc service nội bộ.

Ẩn field ở giao diện frontend không phải biện pháp bảo vệ. Nếu API trả field trong JSON, caller có thể đọc nó bằng devtools hoặc HTTP client.

### 3.2 Kiểm tra output theo principal, object và tenant

Response phải dựa trên authorization decision đã thực hiện ở server. Kiểm tra cả:

- Object có thuộc tenant/owner mà principal được phép xem không?
- Caller có permission cho từng field hoặc loại dữ liệu nhạy cảm không?
- List/search/export có lọc tenant ở data access layer không?
- Nested object, attachment, signed URL và related resource có được kiểm tra độc lập không?
- Bulk response có chứa object từ tenant khác do thiếu filter không?
- Cache có phân tách theo principal/tenant và quyền không?

Không chỉ kiểm tra quyền ở endpoint detail rồi giả định endpoint list, count, autocomplete, export hoặc download cũng an toàn. Mỗi đường truy cập cùng một dữ liệu cần policy tương ứng.

### 3.3 Schema output và data minimization

Định nghĩa response schema cho từng status code và role. Kiểm tra:

- Field bắt buộc, kiểu dữ liệu, enum và format.
- Field nhạy cảm chỉ xuất hiện khi policy cho phép.
- Không có internal property phát sinh do serializer tự động.
- Collection có pagination và giới hạn tổng số phần tử.
- Timestamp/timezone và decimal representation nhất quán.
- Không trả dữ liệu thừa chỉ vì entity có sẵn quan hệ eager-loaded.
- Không có dữ liệu của tenant khác trong nested/list/export response.

Với dữ liệu cá nhân, chỉ trả trường cần cho mục đích của endpoint. Dùng masking hoặc tokenized reference khi caller không cần giá trị đầy đủ. Output filtering không thay thế data access authorization; cả hai phải được áp dụng.

### 3.4 Cache và response header

Với response phụ thuộc user, tenant hoặc quyền, cấu hình cache phù hợp như `Cache-Control: private` hoặc `no-store` theo mức nhạy cảm. Không để shared cache lưu response riêng tư rồi phục vụ cho principal khác. Nếu response thay đổi theo `Origin`, dùng `Vary: Origin`; nếu phụ thuộc authentication context, không giả định `Vary` đơn giản đã đủ phân tách mọi cache.

Kiểm tra CDN, reverse proxy, gateway, browser cache và application cache. Cache key phải chứa context cần thiết hoặc tắt shared caching cho dữ liệu riêng tư. Khi role/permission bị thu hồi, xác định cách invalidation để response cũ không tiếp tục được phục vụ.

## 4. Checklist schema và API contract

### 4.1 OpenAPI/JSON Schema là hợp đồng, không phải toàn bộ runtime security

Schema giúp công bố kiểu, field, required, enum, format và response. Tuy nhiên, một schema hợp lệ không thể tự chứng minh caller có quyền trên object hoặc trạng thái nghiệp vụ được phép.

Trước deploy:

- OpenAPI mô tả đúng path, method, parameter, request/response và error status.
- Request schema có `required`, type, length, range, enum và collection limit phù hợp.
- Response schema không công bố field nội bộ hoặc dữ liệu nhạy cảm ngoài mục đích.
- Security scheme mô tả cơ chế xác thực, nhưng permission/tenant policy vẫn được test riêng.
- Các schema reference, discriminator và polymorphic subtype được giới hạn rõ.
- Phiên bản schema và API version có quy tắc tương thích được tài liệu hóa.
- CI kiểm tra breaking change và diff hợp đồng trước khi merge.

Lưu ý: cách validator xử lý JSON Schema `format` phụ thuộc dialect và cấu hình thư viện; không giả định `format: email`, `uri` hoặc `date-time` luôn được kiểm tra như assertion. Cần bật đúng chế độ hoặc validate riêng.

### 4.2 Unknown fields và backward compatibility

Chọn chính sách rõ ràng cho field không được nhận diện:

- Schema đóng có thể từ chối unknown fields, hữu ích với command/write endpoint để phát hiện client gửi sai hoặc cố mass assign.
- Schema mở có thể bỏ qua field mới để hỗ trợ additive evolution, nhưng phải bảo đảm field lạ không được bind vào model nội bộ.
- Không dùng một chính sách chung nếu các endpoint có yêu cầu tương thích khác nhau.

Khi thêm field response, kiểm tra client cũ có parse strict hay không. Khi xóa/đổi field request, có kế hoạch version/deprecation. Schema validation cần được kiểm thử với payload cũ, payload mới và payload không hợp lệ.

### 4.3 Kiểm tra contract giữa gateway và service

Nếu gateway validate request, service vẫn cần bảo vệ domain boundary. Gateway có thể bỏ qua hoặc không hiểu schema version mới; request nội bộ có thể gọi thẳng backend; message consumer không đi qua HTTP gateway. Hãy kiểm tra schema ở service sở hữu nghiệp vụ hoặc tại consumer boundary.

Không giả định gateway response transformation luôn an toàn. Kiểm tra header forwarding, body transformation, path rewrite, duplicate parameter và cách gateway xử lý `Content-Length`, transfer encoding, content type.

## 5. Checklist error response

### 5.1 Dùng error contract ổn định

Error response là một phần của API contract. Có thể dùng `application/problem+json` theo RFC 9457 để chuẩn hóa các trường như `type`, `title`, `status`, `detail` và `instance`, đồng thời thêm mã lỗi máy đọc được trong extension field.

Ví dụ:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "code": "VALIDATION_FAILED",
  "detail": "One or more request fields are invalid.",
  "instance": "/api/transfers",
  "errors": [
    {
      "field": "amount",
      "code": "OUT_OF_RANGE"
    }
  ],
  "requestId": "req_01J9Z8D5H4J4W0X7"
}
```

Ví dụ chỉ trả tên field và mã lỗi đã chuẩn hóa, không echo giá trị input có thể chứa PII/secret. `detail` phải an toàn để hiển thị cho client; thông tin kỹ thuật phục vụ điều tra nằm trong log có kiểm soát.

### 5.2 Chọn status code nhất quán

| Status | Cách dùng thường gặp | Lưu ý bảo mật |
|---|---|---|
| `400 Bad Request` | Request syntax hoặc cấu trúc không hợp lệ | Không trả parser stack trace hay byte offset chứa dữ liệu nhạy cảm |
| `401 Unauthorized` | Thiếu hoặc credential không hợp lệ | Dùng `WWW-Authenticate` khi phù hợp; không tiết lộ account/secret cụ thể |
| `403 Forbidden` | Đã xác thực nhưng không đủ quyền | Có thể dùng `404` nếu policy cần che sự tồn tại của object |
| `404 Not Found` | Resource không tồn tại hoặc được che theo policy | Response không nên giúp dò ID/tenant |
| `409 Conflict` | Xung đột state, version hoặc idempotency | Chỉ tiết lộ trạng thái đủ để client xử lý |
| `413 Content Too Large` | Request body/file vượt giới hạn | Giới hạn được áp dụng trước khi parser tiêu thụ quá nhiều tài nguyên |
| `415 Unsupported Media Type` | Content type không được hỗ trợ | Không cố parse nội dung theo định dạng khác một cách tùy tiện |
| `422 Unprocessable Content` | Cấu trúc hợp lệ nhưng vi phạm validation/business rule | Mã lỗi ổn định, không echo dữ liệu nhạy cảm |
| `429 Too Many Requests` | Vượt rate limit/quota theo policy | `Retry-After` nếu xác định được thời gian thử lại |
| `500 Internal Server Error` | Lỗi không dự kiến phía server | Chỉ trả thông báo chung và request ID |
| `502/503/504` | Dependency/gateway lỗi hoặc timeout | Không lộ hostname nội bộ, credentials hoặc topology |

Status code cụ thể cần nhất quán với hợp đồng hiện hành. Không dùng `200 OK` cho lỗi nghiệp vụ hoặc `500` cho mọi loại lỗi để tránh phân biệt; client cần status phù hợp để xử lý retry và hiển thị.

### 5.3 Không rò rỉ thông tin qua error detail

Không trả:

- Stack trace, class name, package, file path hoặc line number.
- SQL query, database schema/table, connection string hoặc host nội bộ.
- Token, cookie, API key, secret, signing key hoặc credential provider response.
- Request/response body nguyên vẹn, PII hoặc dữ liệu object của tenant khác.
- Chi tiết policy expression, role mapping hoặc rule nội bộ có thể hỗ trợ dò quyền.
- Nội dung exception do dependency hoặc parser trả về mà chưa được lọc.

Dùng exception mapping tập trung để chuyển lỗi nội bộ thành error code ổn định. Không để từng controller tự tạo response tùy ý, khiến một endpoint vô tình trả exception message trong khi endpoint khác đã che.

### 5.4 Không tạo oracle cho attacker

Response khác biệt quá chi tiết có thể giúp attacker dò account, token, object ID hoặc trạng thái nội bộ. Với login/reset password, tránh cho biết email có tồn tại hay không. Với object nhạy cảm, cân nhắc trả `404` cho cả object không tồn tại và object caller không được biết, trong khi audit nội bộ vẫn ghi reason code thực.

Không nhất thiết làm mọi response giống hệt nhau; cần cân bằng khả năng client xử lý, usability và rủi ro enumeration. Nếu thời gian phản hồi cũng tiết lộ trạng thái, đánh giá timing side channel cho endpoint nhạy cảm.

## 6. Ví dụ Spring: validation và error mapping

Controller nhận request DTO và kích hoạt Bean Validation:

```java
@RestController
@RequestMapping("/api/transfers")
class TransferController {
    private final TransferService transferService;

    TransferController(TransferService transferService) {
        this.transferService = transferService;
    }

    @PostMapping
    ResponseEntity<TransferResponse> create(
            @Valid @RequestBody CreateTransferRequest request,
            @AuthenticationPrincipal ApiPrincipal principal) {
        TransferResponse response = transferService.create(principal, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Service tiếp tục kiểm tra authorization và business rule; Bean Validation không thay thế hai bước đó. Response dùng DTO riêng để không serialize entity.

Với Spring Framework 6+, có thể dùng `ProblemDetail` trong exception handler:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.UNPROCESSABLE_ENTITY);
        problem.setTitle("Request validation failed");
        problem.setDetail("One or more request fields are invalid.");
        problem.setType(URI.create(
            "https://api.example.com/problems/validation-error"));
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("requestId", safeRequestId(request));
        problem.setProperty("errors", ex.getBindingResult().getFieldErrors().stream()
            .map(error -> Map.of(
                "field", safeFieldName(error.getField()),
                "code", "INVALID_VALUE"))
            .toList());
        return ResponseEntity.unprocessableEntity().body(problem);
    }
}
```

Đây là ví dụ khung; cần bổ sung import và điều chỉnh theo phiên bản Spring. Không đưa `error.getRejectedValue()` hoặc `ex.getMessage()` vào response vì giá trị bị từ chối có thể chứa PII, token hoặc payload do attacker kiểm soát. `safeRequestId` phải lấy từ correlation context nội bộ đã được kiểm tra, không phản chiếu một header tùy ý.

Trong production, handler cần bao phủ authentication failure, access denied, not found, conflict, rate limit và unexpected exception. Log nội bộ nên ghi mã lỗi, exception class đã lọc, request/trace ID và service; không log raw body hay secret.

## 7. Checklist kiểm thử trước khi deploy

### 7.1 Positive và negative input tests

- Payload hợp lệ tối thiểu và đầy đủ được chấp nhận.
- Thiếu required field, `null`, sai type, enum lạ và format lỗi bị từ chối.
- Giá trị ở đúng boundary được chấp nhận; ngoài min/max bị từ chối.
- Chuỗi quá dài, nested depth quá sâu và array quá lớn bị giới hạn.
- Duplicate JSON key, malformed encoding và content type không hỗ trợ được xử lý theo policy parser.
- Unknown field và server-owned field không gây mass assignment.
- Query filter/sort không thể inject SQL hoặc expression tùy ý.
- URL/hostname không được phép, redirect và IP private bị chặn theo SSRF policy.
- File upload/archive bị giới hạn kích thước, loại file và giải nén.

### 7.2 Authorization và output tests

- Principal không có permission bị từ chối.
- User cùng tenant nhưng không phải owner bị từ chối khi policy yêu cầu owner.
- Tenant A không đọc/sửa object Tenant B.
- List, search, nested resource, batch, export và download đều áp dụng cùng ranh giới quyền.
- Response không chứa password hash, token, internal note hoặc field chỉ dành cho admin.
- Role/permission thay đổi được phản ánh trong cache và response theo thời hạn đã định.
- Object không tồn tại và object bị che không tạo oracle ngoài policy.

### 7.3 Error response tests

- Mỗi lỗi có status code và error code ổn định theo contract.
- `401` và `403` được phân biệt theo semantics; `404` concealment nhất quán nếu áp dụng.
- Validation error không echo rejected value nhạy cảm.
- Unexpected exception không trả stack trace, SQL, host nội bộ hoặc class path.
- Dependency timeout không lộ URL/credential và có status phù hợp.
- `429` có `Retry-After` khi cần; client không bị hướng dẫn retry lỗi không thể khắc phục.
- Response lỗi có request ID để hỗ trợ điều tra nhưng không dùng ID do caller kiểm soát trực tiếp.

### 7.4 Contract, fuzz và regression

- OpenAPI lint và schema validation chạy trong CI.
- Breaking change được phát hiện trước merge.
- Contract test giữa gateway, service và consumer được cập nhật.
- Fuzz/property-based test tập trung parser, boundary, Unicode, nested data và enum.
- Regression test được tạo từ lỗi đã từng xảy ra.
- Kiểm thử concurrency, body limit, pagination, timeout và rate limit.
- Kiểm tra side effect: request bị từ chối không tạo database change, message, payment hoặc notification.

## 8. Checklist triển khai và vận hành

### Trước deploy

- [ ] Endpoint inventory và OpenAPI contract được review.
- [ ] Authentication, function-level và object-level authorization được mô tả/test.
- [ ] Request DTO tách biệt entity; field server-owned không thể bị ghi đè.
- [ ] Validation có type, required, range, length, enum và business rules.
- [ ] Content type, encoding, body size, parser depth và upload limit được cấu hình.
- [ ] URL/outbound reference có SSRF allowlist và egress policy.
- [ ] Response DTO chỉ chứa field được phép theo principal/object/tenant.
- [ ] Pagination, query complexity, rate limit, timeout và concurrency có giới hạn.
- [ ] Error schema/status code ổn định, không lộ internals.
- [ ] CI chạy OpenAPI lint, schema/contract test, security negative test và regression test.

### Sau deploy

- [ ] Smoke test qua gateway/ingress và đường truy cập backend thực tế.
- [ ] Kiểm tra status code, response schema và header cache trên success/error.
- [ ] Thử principal khác nhau trên cùng object và object thuộc tenant khác.
- [ ] Xác nhận request bị từ chối không tạo side effect.
- [ ] Theo dõi tỷ lệ `400`, `401`, `403`, `404`, `413`, `415`, `422`, `429` và `5xx` theo route template.
- [ ] Log/trace có request ID nhưng không chứa token, raw body hoặc PII ngoài policy.
- [ ] Alert cho validation spike, authorization deny bất thường, payload quá lớn và parser/resource exhaustion.
- [ ] Có rollback/feature flag và owner xử lý khi contract hoặc validation gây lỗi client diện rộng.

### Duy trì theo vòng đời API

- [ ] Schema và error contract có version, owner và compatibility policy.
- [ ] Thay đổi field/enum/status được review cùng client impact.
- [ ] Deprecation/migration có lịch và telemetry cho client cũ.
- [ ] Test được cập nhật khi thêm endpoint, field nhạy cảm hoặc workflow mới.
- [ ] Quy tắc redaction, retention và quyền truy cập log được rà soát định kỳ.
- [ ] Drift giữa OpenAPI, gateway, runtime validator và code được phát hiện tự động.

## 9. Các dấu hiệu chưa sẵn sàng production

Không nên phát hành khi còn một trong các vấn đề nghiêm trọng sau:

- Request body được bind trực tiếp vào entity có field quyền hạn hoặc tenant.
- Endpoint đọc/ghi object chỉ kiểm tra role mà không kiểm tra owner/tenant.
- Output trả entity hoặc serializer có thể lộ internal property.
- Body, pagination, nested depth hoặc upload không có giới hạn.
- URL do caller cung cấp được server gọi mà không có SSRF control.
- Error response trả stack trace, SQL, credential hoặc rejected value nhạy cảm.
- Gateway validate nhưng backend/consumer không có validation tại trust boundary.
- Không có test chứng minh request bị deny không tạo side effect.
- Log lỗi chứa raw token, cookie, request body hoặc dữ liệu tenant khác.

## 10. Bằng chứng bàn giao cho vận hành

Mỗi lần release nên lưu được một bộ bằng chứng có thể truy vết:

- OpenAPI/schema version và commit/release ID.
- Kết quả lint, contract test, schema test và security test.
- Danh sách endpoint/route đã thay đổi và data classification liên quan.
- Policy version cho authentication/authorization và cấu hình resource limit.
- Ví dụ success/error response đã được kiểm tra, không chứa dữ liệu production.
- Kết quả smoke test sau deploy và correlation ID của lần kiểm tra.
- Owner, rollback plan, feature flag và cách xử lý client incompatibility.
- Các exception còn hiệu lực, người phê duyệt và ngày hết hạn.

Không đưa secret, production payload hoặc PII vào artifact bàn giao. Bằng chứng cần đủ để xác nhận kiểm soát đã được kiểm tra mà không tạo thêm bản sao dữ liệu nhạy cảm.

Input validation, output filtering, schema contract và error response là các phần của cùng một ranh giới API. Khi từng endpoint có DTO rõ ràng, kiểm tra quyền trên object/tenant, giới hạn tài nguyên, response allowlist và lỗi an toàn, hệ thống sẽ giảm được mass assignment, data leakage, parser abuse và việc tiết lộ thông tin nội bộ. Chỉ đánh dấu sẵn sàng production khi có cả cấu hình lẫn bằng chứng kiểm thử cho các luồng thành công, thất bại và side effect.
