# If-None-Match: * khi tạo chỉ nếu tài nguyên chưa tồn tại

## 1. Tình huống nghiệp vụ và mục tiêu học tập

Một REST API cho phép người dùng quản lý tài liệu tại URI **/api/v1/documents/{id}**. Client có quyền chọn trước ID tài liệu để đồng bộ với hệ thống bên ngoài. Tuy nhiên, hai client có thể đồng thời yêu cầu tạo tài liệu cùng ID. Nếu server dùng PUT không điều kiện, request đến sau có thể thay thế nội dung do request trước đã lưu.

Nghiệp vụ yêu cầu **chỉ được tạo nếu URI chưa có tài nguyên**, tuyệt đối không tự động ghi đè dữ liệu hiện tại. HTTP cung cấp một cơ chế diễn đạt điều kiện này:

~~~http
If-None-Match: *
~~~

Khi áp dụng cho **PUT** tới URI cụ thể, dấu sao có nghĩa: chỉ thực hiện thao tác nếu tài nguyên đích **không có representation hiện tại**. Nếu đã có, precondition không thỏa và server phản hồi **412 Precondition Failed** thay vì thay thế dữ liệu.

Đây là bài thuộc chương **Điều kiện và đồng thời** của module **INTEGRATION_API_REST**. Bài kết nối mô hình resource/URI, HTTP method và status, hợp đồng dữ liệu rõ ràng, xác thực/phân quyền, xử lý lỗi, OpenAPI và kiểm thử Java/Spring. Tư duy này đặc biệt quan trọng khi xử lý nhiều request cạnh tranh hoặc retry sau lỗi mạng.

Sau khi học xong, bạn sẽ có thể:

1. Giải thích chính xác cú pháp và ngữ nghĩa **If-None-Match: \***.
2. Thiết kế **PUT create-only** với **201**, **412** và quy tắc bắt buộc precondition.
3. Phân biệt **If-None-Match**, **If-Match**, **Idempotency-Key** và kiểm tra tồn tại thông thường.
4. Bảo đảm tạo tài nguyên nguyên tử ở database dù ứng dụng chạy nhiều instance.
5. Thiết kế cách xử lý retry khi response thành công bị thất lạc.
6. Cài đặt controller/service mẫu với Spring MVC và PostgreSQL.
7. Ghi hợp đồng vào OpenAPI và kiểm thử HTTP, đồng thời, bảo mật.

> Bài sử dụng ngữ nghĩa của **HTTP Semantics (RFC 9110)** và mã **428 Precondition Required** của **RFC 6585**. Code là minh họa kiến trúc, cần bổ sung import, dependency, bảo mật và tích hợp dữ liệu để chạy trong dự án thực.

## 2. Phiên HTTP tạo mới thành công

Client chọn UUID hợp lệ và gửi representation của tài liệu:

~~~http
PUT /api/v1/documents/7d9c4f8a-93b7-4e05-a8c1-f1735d41dc22 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
If-None-Match: *

{
  "title": "Báo cáo tháng 11",
  "content": "Nội dung ban đầu"
}
~~~

Giả sử người gọi được phép tạo tài liệu và URI đó chưa có representation hiện tại, server thực hiện tạo thành công:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/documents/7d9c4f8a-93b7-4e05-a8c1-f1735d41dc22
Content-Type: application/json
Cache-Control: no-store

{
  "id": "7d9c4f8a-93b7-4e05-a8c1-f1735d41dc22",
  "title": "Báo cáo tháng 11",
  "content": "Nội dung ban đầu",
  "version": 1
}
~~~

**201 Created** cho biết thao tác tạo tài nguyên đã hoàn tất. URI đích của PUT đã chỉ rõ tài nguyên mới; thêm **Location** là lựa chọn hữu ích để client dễ lưu tham chiếu, không phải lúc nào cũng là yêu cầu bắt buộc trong trường hợp PUT.

Nếu một client gửi lại **PUT cùng URI** và **If-None-Match: \*** khi tài nguyên đã tồn tại:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/resource-already-exists",
  "title": "Precondition Failed",
  "status": 412,
  "detail": "Tài nguyên đích đã tồn tại; thao tác tạo mới không được thực hiện."
}
~~~

**Bất biến quan trọng:** Response 412 không được làm tài liệu cũ đổi title/content/version; không ghi thêm sự kiện nghiệp vụ **DocumentCreated**, không kích hoạt tác dụng phụ dành riêng cho thao tác tạo thành công.

## 3. Ý nghĩa của dấu sao trong If-None-Match

Header **If-None-Match** có thể mang **danh sách entity-tag** hoặc dấu sao đặc biệt:

~~~http
If-None-Match: *
~~~

~~~http
If-None-Match: "v7"
~~~

~~~http
If-None-Match: W/"v7"
~~~

| Trường hợp | Ý nghĩa |
| --- | --- |
| **If-None-Match: \*** | Điều kiện đúng nếu **target resource không có representation hiện tại**. |
| **If-None-Match: "v7"** | So sánh validator hiện tại của target với entity-tag v7 theo ngữ nghĩa If-None-Match. |
| **If-None-Match: W/"v7"** | Dùng weak entity-tag trong phép so sánh tương ứng. |
| **If-None-Match: "\*"** | Đây là một entity-tag có giá trị sao, **không phải wildcard**. |

**If-None-Match sử dụng weak comparison** khi đối chiếu entity-tag. Tuy nhiên, với giá trị đặc biệt **\***, câu hỏi chính là **có representation hiện tại hay không**, không cần biết giá trị ETag của nó.

Theo ngữ nghĩa HTTP:

- Khi điều kiện **đúng**, server có thể tiếp tục xử lý request nếu các điều kiện khác đều thỏa.
- Khi điều kiện **sai** đối với **PUT/PATCH/POST/DELETE**, server không thực hiện thao tác được yêu cầu và trả **412 Precondition Failed** theo quy tắc áp dụng.
- Khi điều kiện **sai** đối với **GET/HEAD**, kết quả thường là **304 Not Modified** nếu request và trạng thái cho phép xử lý conditional retrieval.

**Precondition không thay thế xác thực hay validation.** Server phải tuân thứ tự đánh giá điều kiện HTTP; một request không có quyền không được biến thành request hợp lệ chỉ nhờ wildcard.

### Target resource là gì?

Trong request:

~~~http
PUT /api/v1/documents/abc
If-None-Match: *
~~~

Tài nguyên được kiểm tra là **/api/v1/documents/abc**, không phải toàn bộ collection **/api/v1/documents** và không phải mọi tài liệu có cùng title hoặc business key. Nếu request body còn trùng một **externalReference** với tài liệu khác, đó có thể là **xung đột nghiệp vụ riêng**, không chứng minh If-None-Match trên URI abc đã thất bại.

## 4. Vì sao PUT có precondition khác PUT thông thường?

PUT nhắm tới URI tài nguyên cụ thể. Nếu client có quyền, PUT không điều kiện có thể tạo tài nguyên khi chưa tồn tại hoặc thay thế representation đang tồn tại.

| Trạng thái tại URI đích | PUT thông thường | PUT + If-None-Match: * |
| --- | --- | --- |
| Chưa có representation hiện tại | Có thể tạo, thường **201** | Có thể tạo, thường **201** |
| Đã có representation | Có thể thay thế, thành công **200/204** | Không thay thế; **412** |
| Hai client cạnh tranh cùng URI | Client sau có nguy cơ ghi đè | Một bên tạo, bên còn lại không tạo nếu điểm ghi nguyên tử |
| Retry sau lần đầu tạo thành công | Có thể thực hiện thay thế lần nữa | **412** vì URI nay đã có representation |
| Muốn sửa tài nguyên đã tồn tại | Phù hợp nếu hợp đồng cho phép và có kiểm soát đồng thời | Không phù hợp: điều kiện create-only thất bại |

Một trình tự đúng:

~~~text
PUT /documents/X + If-None-Match: *

Lần 1: chưa có X
  -> tạo X
  -> HTTP 201 Created

Lần 2: đã có X
  -> không thay đổi X
  -> HTTP 412 Precondition Failed
~~~

**Không cần status giống nhau để gọi PUT là idempotent.** Idempotency nói về **hiệu ứng dự kiến lên trạng thái**, không phải mọi lần gọi đều trả cùng response.

## 5. So sánh 201, 412, 428 và 409

| Status | Tình huống | Ý nghĩa cho client |
| --- | --- | --- |
| **201 Created** | Đã tạo thành công resource mới | Có thể lấy URI từ Location và body theo contract |
| **412 Precondition Failed** | Wildcard không thỏa vì target đã có representation | Không được tạo/ghi đè; cần kiểm tra trạng thái trước khi ra quyết định |
| **428 Precondition Required** | API yêu cầu điều kiện nhưng client không gửi | Bổ sung header bắt buộc |
| **400 Bad Request** | Header không đúng cú pháp/chính sách, ID hoặc body sai | Sửa request |
| **409 Conflict** | Xung đột khóa nghiệp vụ hoặc trạng thái khác, dù target URI còn trống | Xem nguyên nhân xung đột |
| **401 Unauthorized** | Chưa có xác thực hợp lệ | Xác thực lại |
| **403 Forbidden** | Không có quyền tạo trong namespace/tenant | Không tiếp tục thao tác trái quyền |
| **404 Not Found** | Namespace/parent không tồn tại hoặc bị che giấu theo chính sách | Không chứng minh target đã tồn tại |
| **415 Unsupported Media Type** | Content-Type không được hỗ trợ | Gửi representation đúng định dạng |
| **5xx** | Lỗi server, có thể trước hoặc sau commit | Xác minh kết quả trước retry; không mặc định chưa tạo |

### 428 khác 412 thế nào?

Nếu hợp đồng buộc mọi request create-only phải gửi wildcard, request **thiếu If-None-Match** có thể nhận:

~~~http
HTTP/1.1 428 Precondition Required
Content-Type: application/problem+json

{
  "title": "Precondition Required",
  "status": 428,
  "detail": "Hãy gửi If-None-Match: * để tạo chỉ khi tài nguyên chưa tồn tại."
}
~~~

Nếu client **đã gửi wildcard** nhưng URI có representation, kết quả là **412**, không phải 428.

### 409 khác 412 thế nào?

Một tài liệu tại URI **/documents/new-id** chưa tồn tại, nên wildcard đúng. Nhưng body muốn dùng **externalReference=INV-01**, vốn đã được tài liệu khác sở hữu. Việc tạo sẽ vi phạm unique business key. API có thể trả **409 Conflict** và không tạo tài liệu.

Không nên bắt mọi database unique constraint violation rồi biến thành 412. Chỉ khi **target resource** đã có representation khiến precondition sai mới hợp lý để trả 412 theo điều kiện này.

## 6. Chọn PUT create-only hay POST + Idempotency-Key?

### PUT create-only

Dùng khi **client biết và được phép chọn URI**:

~~~http
PUT /api/v1/documents/external-42 HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"title":"Hợp đồng","content":"..."}
~~~

Server cần kiểm tra namespace, kiểu ID và quyền của client.

### POST vào collection

Dùng khi **server tự tạo ID** cho tài nguyên mới:

~~~http
POST /api/v1/documents HTTP/1.1
Content-Type: application/json
Idempotency-Key: 0b1358a9-5931-4a52-beb4-4e4878cefb5b

{"title":"Hợp đồng","content":"..."}
~~~

Server có thể tạo **/documents/{generatedId}** và trả 201 + Location. **Idempotency-Key** giúp phân biệt retry cùng ý định với một lệnh tạo độc lập.

**Không dùng If-None-Match: \* trên POST /documents để đòi “chỉ tạo member mới nếu member chưa tồn tại”.** Header kiểm tra **target resource** là collection /documents, không kiểm tra một thành viên mới chưa biết URI.

| Mục tiêu | Mẫu phù hợp |
| --- | --- |
| Client chọn resource URI, không cho ghi đè | **PUT /resources/{id} + If-None-Match: \*** |
| Server cấp ID, tránh trùng khi retry | **POST /resources + Idempotency-Key** |
| Sửa bản đã tồn tại nếu version vẫn đúng | **PUT/PATCH + If-Match: "etag"** |
| Upsert (chưa có tạo, đã có thay thế) | **PUT** theo hợp đồng, không sử dụng wildcard create-only |
| Tạo xử lý bất đồng bộ chưa hoàn tất | **202 Accepted** và operation/status resource thích hợp |

## 7. If-None-Match và If-Match bảo vệ các giai đoạn khác nhau

| Header | Bài toán |
| --- | --- |
| **If-None-Match: \*** | Tạo mới, không được ghi đè target hiện có |
| **If-Match: "v1"** | Chỉ sửa nếu representation hiện tại khớp validator; giảm lost update |
| **If-None-Match: "v1"** | Revalidation GET: nếu chưa đổi có thể dùng 304 |
| **If-Modified-Since** | Revalidation với validator theo thời gian |
| **If-Unmodified-Since** | Chỉ tiếp tục khi tài nguyên không thay đổi sau thời điểm được biết, theo quy tắc HTTP |

Một vòng đời đơn giản:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as API
    participant D as Database
    C->>S: PUT /documents/X + If-None-Match: *
    S->>D: INSERT X atomically if absent
    D-->>S: Inserted
    S-->>C: 201 Created
    C->>S: GET /documents/X
    S-->>C: 200 OK + ETag: "v1"
    C->>S: PATCH /documents/X + If-Match: "v1"
    S->>D: Conditional UPDATE WHERE version=1
    D-->>S: Updated to version=2
    S-->>C: 200 OK / 204 No Content
~~~

**If-Match** phù hợp cho thao tác sửa và có thể trả **412** nếu validator cũ. **If-None-Match: \*** chỉ phù hợp bước tạo khi target chưa tồn tại; nó không bảo vệ một update theo version.

### Lưu ý validator trên response PUT

Theo HTTP Semantics, một origin không được gửi validator như **ETag** hoặc **Last-Modified** trong response **PUT thành công** nếu representation của request đã bị biến đổi khi lưu, hoặc validator không phản ánh representation mới theo điều kiện chuẩn.

Nếu client gửi title/content, server tự thêm ID/version/chuẩn hóa nội dung, **đừng tự động phát ETag trên response 201 PUT** chỉ vì framework hỗ trợ. Client có thể GET sau khi tạo để lấy ETag được server cấp cho representation hiện tại.

## 8. Race condition: kiểm tra tồn tại trước không đủ

Đây là cách triển khai **sai** khi nhiều request chạy đồng thời:

~~~java
if (!repository.existsById(id)) {
    repository.save(new DocumentEntity(id, request.title(), request.content()));
    return created();
}
return preconditionFailed();
~~~

Giả sử:

~~~text
Client A                        Client B
--------                        --------
SELECT X -> không có            SELECT X -> không có
INSERT X                         INSERT X
~~~

Hai request đều có thể đọc **chưa có X** trước khi bên nào ghi. Một implementation có thể tạo bản trùng hoặc thực hiện upsert/ghi đè. **GET /documents/X rồi mới PUT** cũng có cùng lỗi kiểm tra-ghi ở hai thời điểm khác nhau.

**Giải pháp:** server cần một **điểm quyết định ghi nguyên tử** tại nguồn dữ liệu có thẩm quyền, thường bằng unique constraint và transaction.

~~~mermaid
flowchart TD
    R[PUT X + If-None-Match: *] --> A[Xác thực, phân quyền, validate]
    A --> B{Có wildcard đúng hợp đồng?}
    B -->|Thiếu| P[428]
    B -->|Sai| V[400]
    B -->|Đúng| I[INSERT-if-absent nguyên tử]
    I --> T{Kết quả}
    T -->|Đã insert và commit| C[201 + Location]
    T -->|Target ID đã có| F[412, không thay đổi]
    T -->|Khóa nghiệp vụ khác xung đột| K[409]
    T -->|Lỗi database| E[Lỗi phù hợp, không báo tạo thành công giả]
~~~

Không dùng **synchronized** trong một JVM làm cơ chế duy nhất nếu API chạy nhiều pod; request khác có thể đến instance khác.

## 9. Cơ sở dữ liệu: unique key và INSERT-if-absent

Ví dụ PostgreSQL lưu tài liệu:

~~~sql
CREATE TABLE documents (
    id        UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    title     TEXT NOT NULL,
    body      TEXT NOT NULL,
    version   BIGINT NOT NULL DEFAULT 1
);
~~~

Nếu ID **duy nhất toàn hệ thống**, một thao tác có thể là:

~~~sql
INSERT INTO documents
    (id, tenant_id, title, body, version)
VALUES
    (:id, :tenant_id, :title, :body, 1)
ON CONFLICT (id) DO NOTHING
RETURNING id, title, body, version;
~~~

Cách hiểu:

- **Có một hàng trả về:** insert thành công trong transaction.
- **Không có hàng trả về:** đã có xung đột trên **id**, không sửa bản cũ; ánh xạ thành **412** nếu đây là target đang được kiểm tra.
- **Lỗi unique constraint khác:** xử lý riêng, có thể là **409**.
- **Commit thất bại:** không trả 201; cần xử lý lỗi hạ tầng và khả năng retry.

**ON CONFLICT ... RETURNING là cú pháp PostgreSQL**, không phải SQL portable. Database khác cần unique constraint, khóa hoặc thao tác ghi nguyên tử tương đương. Nếu URI có namespace theo tenant và ID chỉ duy nhất trong tenant, khóa mục tiêu là **(tenant_id, id)**; cả HTTP routing lẫn constraint phải nhất quán.

Nếu còn business event **DocumentCreated**, nên ghi **transactional outbox** cùng transaction khi INSERT thành công. Khi request thua điều kiện, không ghi outbox. Consumer vẫn cần idempotency theo event ID vì event delivery có thể lặp lại.

## 10. Spring MVC: controller minh họa

Ví dụ dùng Java 17+, Spring MVC, Spring JDBC và PostgreSQL.

### Request/response DTO

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateDocumentRequest(
    @NotBlank @Size(max = 200) String title,
    @NotBlank String content
) {}

public record DocumentResponse(
    java.util.UUID id,
    String title,
    String content,
    long version
) {}
~~~

**tenantId/ownerId** không phải thuộc tính caller được phép tự gán. Server lấy phạm vi quyền từ principal đã xác minh.

### Controller bắt buộc wildcard

~~~java
@RestController
@RequestMapping("/api/v1/documents")
public class DocumentController {

    private final DocumentService service;
    private final TenantAccess tenantAccess;

    public DocumentController(
            DocumentService service,
            TenantAccess tenantAccess) {
        this.service = service;
        this.tenantAccess = tenantAccess;
    }

    @PutMapping("/{id}")
    public ResponseEntity<DocumentResponse> createOnly(
            @PathVariable UUID id,
            @RequestHeader(
                value = HttpHeaders.IF_NONE_MATCH,
                required = false) String ifNoneMatch,
            @Valid @RequestBody CreateDocumentRequest body,
            Authentication authentication) {

        if (ifNoneMatch == null) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED,
                "Yêu cầu If-None-Match: *");
        }
        if (!"*".equals(ifNoneMatch.trim())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Endpoint chỉ hỗ trợ If-None-Match: *");
        }

        String tenantId =
                tenantAccess.authorizedTenantId(authentication);

        DocumentResponse created = service
                .createIfAbsent(tenantId, id, body)
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "Tài nguyên đã tồn tại"));

        URI location = URI.create("/api/v1/documents/" + id);

        return ResponseEntity.created(location)
                .cacheControl(CacheControl.noStore())
                .body(created);
    }
}
~~~

**Giới hạn của ví dụ:** Controller chỉ hỗ trợ wildcard vì đây là hợp đồng endpoint create-only. Nếu endpoint cần hỗ trợ cả danh sách entity-tag theo ngữ nghĩa HTTP, phải dùng parser/logic precondition chuẩn thay vì chỉ so chuỗi. Cấu hình **Security**, **TenantAccess**, validation và Problem Details cần hiện thực trong project. URI Location dạng root-relative hợp lệ; không ghép host từ header proxy không đáng tin.

### Service thực hiện INSERT nguyên tử

~~~java
@Service
public class DocumentService {

    private final NamedParameterJdbcTemplate jdbc;

    public DocumentService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<DocumentResponse> createIfAbsent(
            String tenantId, UUID id, CreateDocumentRequest body) {

        String sql = """
            INSERT INTO documents
                (id, tenant_id, title, body, version)
            VALUES
                (:id, :tenantId, :title, :body, 1)
            ON CONFLICT (id) DO NOTHING
            RETURNING id, title, body, version
            """;

        var params = new MapSqlParameterSource()
                .addValue("id", id)
                .addValue("tenantId", tenantId)
                .addValue("title", body.title())
                .addValue("body", body.content());

        List<DocumentResponse> result = jdbc.query(
                sql, params,
                (rs, n) -> new DocumentResponse(
                    rs.getObject("id", UUID.class),
                    rs.getString("title"),
                    rs.getString("body"),
                    rs.getLong("version")));

        return result.stream().findFirst();
    }
}
~~~

Cần import **Optional, List, UUID, Spring JDBC/Transaction**. Việc kiểm tra quyền tạo đã diễn ra trước khi gọi service; trong ứng dụng thực, còn cần bảo vệ ràng buộc cấp namespace, xử lý unique constraint khác và cách ánh xạ lỗi. **Chỉ trả 201 sau khi transaction service commit thành công**, không dựa vào việc đã chạy một lệnh INSERT tạm thời nhưng sau đó rollback.

### Vì sao không bắt mọi lỗi DB rồi trả 412?

Nếu database mất kết nối, dữ liệu sai constraint khác, deadlock hoặc timeout, API chưa có bằng chứng target đã tồn tại. Trả 412 cho mọi exception sẽ che lỗi hạ tầng. Hãy phân biệt **xung đột đúng target ID** với lỗi khác, giữ log nội bộ và trả status/Problem Details phù hợp.

## 11. Cạnh tranh nhiều client: chỉ một bên tạo được

Hai request cùng ID nhưng body khác:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant S as API / nhiều instance
    participant DB as Database UNIQUE(id)
    A->>S: PUT X + If-None-Match: *, body A
    B->>S: PUT X + If-None-Match: *, body B
    S->>DB: INSERT X theo request A
    S->>DB: INSERT X theo request B
    Note over DB: Constraint giải quyết xung đột nguyên tử
    DB-->>S: Một INSERT thành công
    DB-->>S: INSERT còn lại không thêm hàng
    S-->>A: Một bên 201, bên kia 412
    S-->>B: Một bên 412, bên kia 201
~~~

Không thể biết trước A hay B thắng. Kết quả đạt khi:

- **Đúng một row** đại diện target.
- Body thuộc **request đã thắng**; request còn lại không thay đổi row.
- **Version ban đầu** không bị tăng bởi request thất bại.
- Chỉ **một business event Created** được ghi.
- Kết quả đúng cả khi request đến hai API instance khác nhau.
- Không biến lỗi commit thành 201.

Nếu dùng nhiều database primary nhận ghi độc lập, một unique constraint tại từng database không bảo đảm tính duy nhất toàn hệ thống. Kiến trúc phải có nguồn ghi/cơ chế đồng thuận hoặc phân vùng quyền sở hữu phù hợp.

## 12. Retry sau khi mất response: vì sao 412 chưa đủ để kết luận?

Giả sử:

~~~text
T1: Client gửi PUT X + If-None-Match: *
T2: Database commit X thành công
T3: Response 201 bị mất trên mạng
T4: Client retry cùng PUT X + If-None-Match: *
T5: API thấy X đã tồn tại -> 412
~~~

**412 không chứng minh lần đầu của client là lệnh đã tạo X.** Có thể một client khác đã tạo X trước hoặc trong khoảng retry.

Hành vi client nên có:

1. Giữ nguyên ID và payload của cùng ý định tạo.
2. Nếu timeout/5xx khiến kết quả không rõ, có thể retry request create-only theo hợp đồng.
3. Khi retry nhận 412, nếu được phép, **GET /documents/X**.
4. So dữ liệu được trả với **business key**, nội dung chuẩn hóa, owner và **creation token** nếu API hỗ trợ.
5. Nếu đúng trạng thái mong muốn nhưng không xác minh được người tạo, phân biệt **“target đang có dữ liệu mong muốn”** với **“chắc chắn request của tôi đã thành công”**.
6. Nếu khác, báo conflict và không tự chuyển sang PUT không điều kiện để ghi đè.
7. Nếu GET không có quyền hoặc không có cơ chế đối soát, biểu diễn **unknown outcome** thay vì khẳng định thành công/thất bại.

**If-None-Match: \*** bảo vệ trạng thái không bị ghi đè; nó **không phải cơ chế replay đúng response 201 ban đầu**. Khi nghiệp vụ cần nhận lại response cũ, có thể bổ sung Idempotency-Key, operation ID hoặc mapping bền vững giữa intent và kết quả, theo chính sách bảo mật.

## 13. Soft delete, tombstone và tái sử dụng URI

“Target chưa tồn tại” không luôn đồng nghĩa “không có row trong database”.

| Trạng thái | Câu hỏi cần thiết kế |
| --- | --- |
| URI chưa từng được tạo | Có cho phép PUT create-only không? |
| Đã hard delete | Có cho tái sử dụng cùng ID không? |
| Bản ghi soft-deleted | URI còn có representation hiện tại không? |
| Có tombstone để ghi nhận xóa | Có cấm tái sử dụng ID vĩnh viễn hoặc theo retention không? |
| Resource chuyển trạng thái sang archived | Nó vẫn tồn tại để GET/PUT hay bị ẩn khỏi API? |

**If-None-Match: \*** đánh giá representation hiện tại theo ngữ nghĩa HTTP, không tự quyết định chính sách **cho phép tái sử dụng ID**. Một API có thể cấm tạo lại URI từng tồn tại dù representation hiện tại không còn, nhằm bảo vệ identity và tránh lỗi **ABA** (URI cũ được dùng cho thực thể mới).

Nếu server dùng tombstone, cần ghi rõ cách trả 404/410 khi đọc và 409/412 trong tình huống tạo theo trạng thái thực, tránh nhầm lẫn giữa precondition và quy tắc nghiệp vụ.

## 14. Bảo mật và quyền truy cập

Một API có thể vô tình để lộ sự tồn tại của tài liệu người khác: URI có data thì trả 412, không có thì trả 201. Nếu quyền chưa được kiểm tra, điều này biến endpoint thành **existence oracle**.

Các nguyên tắc:

- Kiểm tra **authentication** và **authorization** trước khi cho phép tạo.
- Lấy **tenant/namespace** từ principal hoặc kiểm tra membership, không tin field tự gửi.
- Nếu client có thể chọn ID, kiểm tra format, phạm vi, quota và quyền đối với namespace.
- Không trả 412 tiết lộ target thuộc tenant khác khi caller không được phép biết nó. Có thể dùng 403/404 theo chính sách phù hợp trước khi đánh giá precondition.
- Cấu hình unique key tương thích URI: global ID hoặc **(tenant_id, id)**.
- Không dùng UUID khó đoán như biện pháp thay thế phân quyền.
- Không đưa token, PII, stack trace hoặc SQL nội bộ vào response lỗi.
- Cân nhắc **Cache-Control: no-store** cho các response nhạy cảm; cache policy không thay thế authz.

Với **/tenants/{tenantId}/documents/{id}**, một người được quyền trong tenant T1 không mặc nhiên được tạo trong T2. Test phải xác minh cả dữ liệu và việc API có tiết lộ sự tồn tại của resource ngoài phạm vi quyền không.

## 15. OpenAPI 3.1: định nghĩa rõ wildcard bắt buộc

~~~yaml
openapi: 3.1.0
info:
  title: Documents API
  version: 1.0.0
paths:
  /api/v1/documents/{id}:
    put:
      summary: Tạo tài liệu tại URI nếu chưa tồn tại
      description: >
        Chỉ tạo mới; không thay thế tài liệu đã có.
        Bắt buộc If-None-Match: *.
        Nếu target có representation hiện tại trả 412.
      operationId: createDocumentIfAbsent
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
            format: uuid
        - in: header
          name: If-None-Match
          required: true
          description: Wildcard bắt buộc, không phải entity-tag
          schema:
            type: string
            const: "*"
          example: "*"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [title, content]
              properties:
                title: { type: string, minLength: 1, maxLength: 200 }
                content: { type: string, minLength: 1 }
      responses:
        '201':
          description: Tài liệu đã được tạo
          headers:
            Location:
              description: URI-reference của tài liệu mới
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema:
                type: object
                required: [id, title, content, version]
                properties:
                  id: { type: string, format: uuid }
                  title: { type: string }
                  content: { type: string }
                  version: { type: integer, minimum: 1 }
        '400':
          description: Body, ID hoặc header không đúng hợp đồng
        '401':
          description: Thiếu xác thực hợp lệ
        '403':
          description: Không có quyền tạo
        '409':
          description: Xung đột nghiệp vụ khác
        '412':
          description: Wildcard không thỏa, target đã tồn tại
          content:
            application/problem+json:
              schema:
                type: object
                properties:
                  title: { type: string }
                  status: { type: integer, const: 412 }
                  detail: { type: string }
        '415':
          description: Media type không hỗ trợ
        '428':
          description: Thiếu precondition bắt buộc
~~~

**OpenAPI 3.1** dùng JSON Schema hiện đại nên có thể khai báo **const: "*"**. Một số tool generator hỗ trợ không đầy đủ; contract test vẫn cần kiểm tra header và status thực tế.

Ngoài ra nên mô tả **GET /documents/{id}** và quy trình đối soát retry, thêm security scheme, quy tắc namespace, response không có quyền và chính sách tái sử dụng ID. Không giả định OpenAPI tự bảo đảm atomicity trong database.

## 16. MockMvc: kiểm thử thành công và thất bại điều kiện

### 16.1. Hai lần tạo cùng một URI

~~~java
@Test
void createOnlyDoesNotOverwriteExistingDocument() throws Exception {
    UUID id = UUID.randomUUID();
    String uri = "/api/v1/documents/" + id;

    mockMvc.perform(put(uri)
            .header(HttpHeaders.IF_NONE_MATCH, "*")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"title":"Bản đầu","content":"Nội dung A"}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", uri))
        .andExpect(jsonPath("$.version").value(1));

    mockMvc.perform(put(uri)
            .header(HttpHeaders.IF_NONE_MATCH, "*")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"title":"Ghi đè","content":"Nội dung B"}
                """))
        .andExpect(status().isPreconditionFailed());

    mockMvc.perform(get(uri))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Bản đầu"));
}
~~~

Bài test cần fixture/transaction độc lập và principal hợp lệ. Không được tắt phân quyền để làm test pass. **GET** trong test là endpoint đọc mà dự án cần triển khai; controller create-only ở phần 10 không định nghĩa endpoint GET.

### 16.2. Thiếu header và header sai

~~~java
@Test
void wildcardIsRequired() throws Exception {
    UUID id = UUID.randomUUID();
    String uri = "/api/v1/documents/" + id;
    String body = """
        {"title":"Mới","content":"Văn bản"}
        """;

    mockMvc.perform(put(uri)
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isPreconditionRequired());

    mockMvc.perform(put(uri)
            .header(HttpHeaders.IF_NONE_MATCH, "\"v1\"")
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isBadRequest());
}
~~~

Trong hợp đồng mẫu, server **bắt buộc đúng wildcard**, không hỗ trợ entity-tag cụ thể khi tạo. Vì vậy **If-None-Match: "v1"** là đầu vào không đúng chính sách endpoint và được chọn phản hồi 400. Một endpoint hỗ trợ đầy đủ mọi dạng If-None-Match có thể có logic khác, nên docs và test phải thống nhất.

### 16.3. Test cạnh tranh qua database

Một kiểm thử thực tế nên dùng PostgreSQL (hoặc engine production) với unique constraint đã tạo. Hai request đồng thời đến cùng URI:

~~~text
ID X chưa có.

Worker A: PUT X, If-None-Match: *, body A
Worker B: PUT X, If-None-Match: *, body B

Đồng bộ bắt đầu hai request gần cùng thời điểm.

Kỳ vọng:
- Một response 201.
- Một response 412.
- Đúng một row cho target ID X.
- Row chứa body của request thắng.
- Không có outbox/event Created thứ hai.
- Không có lỗi 5xx bị che dưới 412.
~~~

**Test tuần tự qua MockMvc không đủ chứng minh atomicity**, vì code sai kiểu **exists → insert** vẫn có thể vượt qua mọi test tuần tự. Cần thử các race condition thực, kiểm chứng với database và nhiều instance nếu có thể.

### 16.4. Ma trận test đầy đủ

| Tình huống | Kỳ vọng |
| --- | --- |
| URI mới, wildcard đúng | 201, Location, một row mới |
| URI đã có, wildcard đúng | 412, không đổi body/version |
| Header vắng mặt | 428 |
| Header là entity-tag thay vì wildcard | 400 theo contract mẫu |
| Request sai JSON hoặc thiếu title | 400/validation error, không tạo |
| Caller không có quyền | 403/404 theo chính sách, không lộ dữ liệu |
| Xung đột business key khác | 409 và không tạo |
| Hai PUT đồng thời cùng ID | Một row, chỉ một request thắng |
| HTTP 201 mất sau commit | Retry không ghi đè; có đường GET/đối soát |
| Hai tenant dùng cùng ID/namespace | Kết quả đúng unique key và authz |
| Soft delete rồi tạo lại | Theo lifecycle policy, không suy đoán |
| Outbox được phát lại | Consumer idempotent; không nhân đôi side effect |
| Lỗi DB trước commit | Không trả 201 |
| Lỗi kết nối sau commit | Client đánh dấu unknown outcome, đối soát |
| GET sau tạo | Representation đúng, ETag nếu GET hỗ trợ validator |

## 17. Các sai lầm hay gặp

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| PUT không điều kiện cho create-only | Ghi đè resource hiện có | Bắt buộc wildcard và atomic insert |
| GET 404 trước rồi PUT | Race giữa hai request | Kiểm tra tại điểm ghi nguyên tử |
| So header **"*"** như wildcard | Nhầm entity-tag với ký hiệu đặc biệt | Parse và test contract |
| Đặt wildcard trên POST collection | Kiểm tra nhầm collection thay vì member | PUT URI cụ thể hoặc POST + Idempotency-Key |
| Xem 412 sau retry là bằng chứng đã tạo | Client khác có thể đã tạo | GET, fingerprint, operation token/đối soát |
| Bắt mọi unique violation thành 412 | Che xung đột khóa nghiệp vụ khác | Phân loại 412 và 409 |
| Chỉ dùng khóa trong một JVM | Nhiều pod tạo đồng thời | DB unique constraint / cơ chế phân tán tương đương |
| Phát event trước khi INSERT thắng | Event duplicate hoặc phantom | Outbox chỉ khi insert thành công |
| Không kiểm tra tenant/namespace | Lộ hoặc sửa dữ liệu trái quyền | Authorization trước khi xử lý |
| Tự động gắn ETag cho PUT đã biến đổi body | Có thể trái quy tắc validator | Chỉ gắn khi đủ điều kiện, lấy ETag bằng GET |
| Không định nghĩa soft delete và tái sử dụng ID | Dễ nhầm resource cũ và mới | Quy định lifecycle/tombstone |
| Chỉ kiểm tra status, không kiểm tra dữ liệu | Ghi đè vẫn có thể xảy ra | Assert row, version, outbox |
| Trả 201 trước commit | Thông báo thành công giả | Bảo đảm transaction hoàn tất trước response |

## 18. Bài tập thực hành: tạo cấu hình webhook không ghi đè

Một nền tảng tích hợp cho phép mỗi tenant tạo một webhook theo tên cố định **shipping-events**:

~~~http
PUT /api/v1/tenants/t-42/webhooks/shipping-events HTTP/1.1
If-None-Match: *
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "callbackUrl": "https://partner.example/callback",
  "enabled": true
}
~~~

Yêu cầu nghiệp vụ:

- Client chọn tên webhook, nhưng chỉ được tạo trong tenant có quyền.
- Nếu tên chưa dùng, API tạo mới và trả **201 Created**.
- Nếu đã tồn tại, API trả **412**, không sửa URL hoặc enabled.
- Thiếu wildcard trả **428**.
- Hai request đồng thời cùng tenant/name chỉ tạo **một** webhook.
- Sự kiện **WebhookRegistered** chỉ được ghi một lần.
- Khi response đầu bị mất, client phải có đường đối soát.
- Callback URL phải được validation, hạn chế nguy cơ SSRF và chỉ đến đích được phép theo chính sách.

### Nhiệm vụ

1. Viết request/response 201 và response 412 theo Problem Details.
2. Định nghĩa rule format của **name**, quyền tenant và cách che giấu sự tồn tại tài nguyên trái quyền.
3. Thiết kế schema có **UNIQUE (tenant_id, name)**; viết INSERT-if-absent hoặc giải pháp tương đương.
4. Giải thích cách đồng bộ hai request cạnh tranh để chỉ một request ghi thành công.
5. Tạo runbook xử lý trường hợp client nhận timeout rồi 412 khi retry; phân biệt resource của mình và của người khác.
6. Cài controller/service Spring hoặc công nghệ tương đương.
7. Viết OpenAPI cho **If-None-Match**, 201/412/428/409 và phân quyền.
8. Viết integration test concurrency, version/row count và outbox.
9. Viết ADR ngắn giải thích vì sao dùng PUT create-only thay POST + Idempotency-Key và những đánh đổi.

**Sản phẩm cần nộp:** hợp đồng HTTP, sơ đồ hoặc pseudocode ghi nguyên tử, code, OpenAPI, test cases, bảng rủi ro quyền/đồng thời và quyết định kiến trúc.

### Tiêu chí tự đánh giá

Bài đạt khi chứng minh được ba điều: **HTTP precondition chính xác**, **dữ liệu và side effect không bị nhân đôi khi cạnh tranh**, **không rò thông tin hoặc vượt quyền giữa tenant**. Response 201/412 đúng nhưng DB vẫn bị ghi đè không phải kết quả đạt.

## 19. Checklist trước khi đưa endpoint vào production

| Câu hỏi | Chỉ coi là đạt khi |
| --- | --- |
| Client có quyền xác định resource URI? | ID/name và namespace hợp lệ |
| Đây có thật sự là create-only? | PUT với If-None-Match: * |
| Header thiếu/sai xử lý rõ ràng? | 428/400 theo contract |
| Target tồn tại có chặn cập nhật? | 412, không đổi row/version/event |
| Có unique key đúng phạm vi? | Global ID hoặc tenant + ID |
| Kiểm tra và ghi có nguyên tử? | Transaction/constraint xử lý race |
| Nhiều instance vẫn đúng? | Integration test đồng thời |
| Phân biệt 412 và 409? | Target xung đột khác business constraint |
| Retry sau mất response có thể đối soát? | GET/token/operation mapping |
| Business side effect có idempotent? | Outbox và consumer dedup |
| Authn/authz trước ghi và phản hồi? | Không tạo/không lộ resource trái quyền |
| Có quy tắc xóa/tái sử dụng URI? | Lifecycle rõ ràng |
| OpenAPI và test khớp code? | Status, headers, body, quyền và concurrency |
| 201 chỉ sau commit? | Không trả thành công khi transaction thất bại |

## 20. Kết luận

**If-None-Match: \*** là cách diễn đạt điều kiện HTTP rõ ràng: **chỉ thực hiện thao tác nếu URI đích chưa có representation hiện tại**. Kết hợp với PUT, nó cho phép thiết kế **create-only**: **201 Created** khi tạo thành công, **412 Precondition Failed** khi target đã tồn tại, thay vì ghi đè ngoài ý muốn.

Muốn hợp đồng đó đúng cả khi nhiều client tranh nhau, phải có **nguồn ghi nguyên tử, unique constraint, kiểm soát quyền, xử lý retry và side effect**. Đặc biệt, 412 khi retry không tự chứng minh request trước của chính client đã thành công.

Câu hỏi cuối cùng để kiểm tra thiết kế là: **“Nếu hai client cùng tạo một URI hoặc response 201 bị mất, hệ thống có chứng minh được không ghi đè, không tạo trùng và có cách xác định trạng thái thực tế hay không?”**
