# Triển khai ETag, Cache-Control và yêu cầu có điều kiện

## 1. Mục tiêu và tình huống xuyên suốt

Trong module **INTEGRATION_API_REST**, thiết kế REST API không chỉ có resource, URI, phương thức và status HTTP mà còn cần hợp đồng caching, idempotency, xác thực, phân quyền và kiểm thử. Chương **Spring MVC** đưa các quy tắc này vào endpoint Java/Spring Boot đang chạy thực tế.

Hãy xét tài nguyên **GET /api/v1/documents/{id}**: một tài liệu có thể được đọc nhiều lần trên web/mobile nhưng đôi khi được người khác cập nhật. Ta muốn **tránh gửi lại JSON không đổi** mà vẫn bảo vệ dữ liệu riêng và **ngăn một client ghi đè phiên bản mới**.

Hai bài toán cần phân biệt:

- **Cache revalidation:** client có biểu diễn cũ, gửi **If-None-Match** để hỏi có cần tải lại không; nếu chưa đổi, GET thường trả **304 Not Modified** không có body.
- **Optimistic concurrency:** client đã chỉnh sửa trên một phiên bản, gửi **If-Match** khi PUT/PATCH/DELETE; nếu dữ liệu đã đổi, server thường trả **412 Precondition Failed** và không ghi đè.

Sau bài này, bạn sẽ:

1. Thiết kế **ETag mạnh/yếu**, Last-Modified và Cache-Control đúng ngữ nghĩa HTTP.
2. Triển khai conditional GET bằng **ResponseEntity** của Spring MVC.
3. Hiểu lợi ích và giới hạn của **ShallowEtagHeaderFilter**.
4. Triển khai PUT/PATCH có **If-Match** và kiểm tra version **nguyên tử** trong DB.
5. Phân biệt **200/304/412/428/409** và response **Problem Details**.
6. Bảo vệ tenant/user, cache riêng, Vary, CORS và tránh rò dữ liệu.
7. Viết hợp đồng OpenAPI 3.1, kiểm thử MockMvc và bài tập thực hành.

**Giới hạn ví dụ:** dùng Java 17+, Spring Boot 3 / Spring MVC và JDBC hoặc JPA tương đương. Các interface lưu trữ/quyền là abstraction; mã cần đủ import, cấu hình và migration schema để chạy độc lập.

## 2. ETag, validator và HTTP cache

**ETag** là response header chứa một **entity tag** của **selected representation** mà server phát hành:

~~~http
GET /api/v1/documents/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "doc-11111111-1111-4111-8111-111111111111-v7"
Cache-Control: private, no-cache

{
  "id": "11111111-1111-4111-8111-111111111111",
  "title": "Hợp đồng dịch vụ",
  "status": "DRAFT",
  "version": 7
}
~~~

ETag **không** phải JWT, khóa phân quyền, cơ chế khóa record hay tên riêng của cột version. Nó là một validator mà HTTP dùng để so sánh biểu diễn. Cột **version** chỉ là một cách để tạo ETag ổn định nếu ứng dụng giữ các bất biến cần thiết.

### 2.1. Strong và weak entity tag

~~~http
ETag: "doc-7"
ETag: W/"doc-7"
~~~

- **Strong ETag** không có tiền tố **W/**: thích hợp cho **If-Match** với strong comparison, và cũng dùng được cho cache revalidation.
- **Weak ETag** có **W/**: có thể dùng cho revalidation khi biểu diễn tương đương theo mức độ yếu hơn. **If-Match không coi weak ETag là khớp mạnh**.
- Với **If-None-Match**, HTTP dùng **weak comparison**; vì thế tag yếu/mạnh có opaque value tương ứng có thể thỏa điều kiện revalidation.

**Đừng bỏ dấu ngoặc kép** hoặc tiền tố W/ rồi tự so bằng số 7: điều kiện HTTP phải xét entity-tag theo ngữ nghĩa và cú pháp của chuẩn.

### 2.2. ETag phải đúng với representation

Nếu cùng một URL trả JSON khác theo **Accept-Language**, **Accept**, projection hoặc quyền đọc field, việc lấy một DB version duy nhất làm **strong ETag** cho tất cả body có thể sai: strong validator phải phản ánh selected representation. Các lựa chọn:

- Một API JSON cố định, mọi thay đổi body đều tăng revision → strong tag dựa trên resource ID, representation contract và revision.
- Nhiều variant → xây dựng validator riêng theo variant, thêm **Vary** phù hợp.
- Body được serialize không ổn định → cân nhắc canonical serialization/hash representation hoặc thiết kế weak validator khi thích hợp.

**Không phát cùng một strong tag cho hai representation không đáp ứng quy tắc strong equivalence.** ETag cũng không cần tiết lộ version nội bộ, ID người dùng, email hoặc payload nhạy cảm.

## 3. Cache-Control: lưu, tái sử dụng và xác thực lại

**Cache-Control** là nơi origin nói cho HTTP cache biết **có được lưu và dùng lại response hay không, và khi nào phải revalidate**. Nó không tự tạo cache trong Spring và không thay thế authorization.

| Directive | Ý nghĩa thực tế | Lưu ý |
| --- | --- | --- |
| **no-store** | Cache tuân thủ không được lưu response/request theo chỉ thị | Phù hợp thông tin nhạy cảm; không phải lệnh xóa mọi bản đã lưu trước đó |
| **no-cache** | Có thể lưu nhưng **phải revalidate trước mỗi lần reuse** | Khác hoàn toàn “không lưu” |
| **private** | Chỉ private cache được lưu; shared cache không được lưu | Dành cho response cá nhân hóa nếu chấp nhận browser cache |
| **public** | Đánh dấu response có thể lưu bởi shared cache theo các điều kiện HTTP | Chỉ dùng khi quyền và dữ liệu cho phép |
| **max-age=300** | Freshness tối đa 300 giây cho cache phù hợp | Khi còn fresh có thể reuse mà chưa hỏi origin |
| **s-maxage=60** | Chỉ dẫn freshness cho **shared caches** | Không thay thế kiểm soát cache key và quyền |
| **must-revalidate** | Khi stale, không reuse nếu chưa revalidate thành công theo semantics | Không làm stale response thành fresh |
| **immutable** | Gợi ý nội dung không đổi trong thời gian fresh | Phù hợp URL versioned/immutable asset, không phải tài liệu mutable thông thường |

Ví dụ cấu hình:

~~~http
Cache-Control: public, max-age=300
~~~

Có thể phù hợp một danh mục công khai mà nội dung được phép cũ tối đa 5 phút. Không áp mặc định cho hồ sơ riêng.

~~~http
Cache-Control: private, no-cache
ETag: "doc-v7"
~~~

Browser được phép lưu tài liệu nhưng phải gửi điều kiện revalidation trước khi dùng lại; **vẫn phải kiểm tra quyền khi request mới tới server**.

~~~http
Cache-Control: no-store
~~~

Phù hợp dữ liệu tài chính/PII nhạy cảm khi không muốn HTTP cache lưu. Nếu **no-store**, ETag có thể vẫn có tác dụng cho conditional write với If-Match, nhưng thông thường **không kỳ vọng cache lưu representation để tạo revalidation hit**.

### 3.1. Những nhầm lẫn thường gặp

- **no-cache** không đồng nghĩa **no-store**.
- **ETag** không tự định nghĩa thời gian fresh; muốn cache, phải xét Cache-Control/Expires, trạng thái và mặc định của HTTP.
- **304** không có nghĩa backend bỏ qua authorization hoặc không cần xem trạng thái resource.
- **max-age** không phải lock: resource có thể đổi ngay sau khi client GET, vì thế update vẫn cần If-Match nếu chống lost update.
- Browser, reverse proxy, CDN và client SDK có thể có **cache behavior khác nhau**; cần kiểm thử đúng lớp.

## 4. Conditional GET với If-None-Match và 304

Luồng phổ biến:

~~~mermaid
sequenceDiagram
    participant C as Browser/client
    participant A as Spring MVC API
    participant D as Database
    C->>A: GET /documents/d-1
    A->>D: Kiểm tra quyền + đọc snapshot v7
    A-->>C: 200 + ETag "v7" + JSON
    Note over C: Cache cục bộ lưu representation nếu được phép
    C->>A: GET + If-None-Match: "v7"
    A->>D: Kiểm tra quyền + validator hiện tại
    D-->>A: v7
    A-->>C: 304 Not Modified, không body
    C->>C: Reuse body đã lưu
~~~

Request revalidation:

~~~http
GET /api/v1/documents/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
If-None-Match: "doc-11111111-1111-4111-8111-111111111111-v7"
~~~

Nếu server xác nhận representation hiện tại khớp:

~~~http
HTTP/1.1 304 Not Modified
ETag: "doc-11111111-1111-4111-8111-111111111111-v7"
Cache-Control: private, no-cache
Vary: Accept
~~~

**304 không chứa response body.** Cache/client dùng lại body 200 đã lưu nếu có bản phù hợp; 304 đơn lẻ không thay thế JSON nếu client không có nội dung cũ.

Nếu người khác đã cập nhật thành v8, GET phải trả **200 và body/ETag mới**. Với conditional GET/HEAD, **If-None-Match** dùng weak comparison. Khi cả **If-None-Match** và **If-Modified-Since** được gửi trong trường hợp áp dụng, điều kiện ETag có ưu tiên; không tự code logic “chỉ cần một điều kiện báo không đổi là 304”.

### 4.1. Last-Modified và If-Modified-Since

~~~http
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT
~~~

~~~http
GET /api/v1/documents/d-1
If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

**Last-Modified** là validator theo thời gian; tiện cho resource không có ETag, nhưng độ chính xác giây và clock skew khiến nó kém an toàn hơn **strong ETag** khi cần phát hiện hai update liên tiếp rất gần nhau. Với GET revalidation, có thể dùng cả ETag và Last-Modified nếu nguồn dữ liệu đáng tin. Với chống mất cập nhật, ưu tiên If-Match với strong tag.

## 5. Tạo ETag ổn định trong Spring MVC

Có hai chiến lược chính:

**Version-based:** ví dụ một row có **revision=7** và server biết toàn bộ representation thay đổi tương ứng khi revision tăng.

~~~java
public final class DocumentEtags {
    private DocumentEtags() {}

    public static String strong(UUID id, long revision) {
        return "\"document-" + id + "-rev" + revision + "\"";
    }
}
~~~

**Content-hash:** tính hash từ bytes biểu diễn được trả về, phù hợp khi representation phức tạp. Cần tính nhất quán serialization, media type, encoding và biến thể:

~~~java
public static String sha256Tag(byte[] representation) {
    try {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(representation);
        return "\"" + HexFormat.of().formatHex(hash) + "\"";
    } catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException(ex);
    }
}
~~~

Đoạn hash cần **byte[] của representation**, có thể không phù hợp cho body lớn nếu materialize toàn nội dung. Với API JSON nhỏ, hash có thể chấp nhận; với binary streaming nên dùng generation/version từ storage hoặc hash đã được tính khi lưu. **Không hash request DTO rồi coi đó là ETag response** khi response chứa trường khác.

### 5.1. Điều kiện để ETag từ revision là strong

- **Mọi đường ghi**, kể cả scheduled job/native SQL, đều tăng revision khi dữ liệu hiển thị thay đổi.
- Các trường do bảng liên quan sinh ra cũng phải ảnh hưởng revision hoặc validator.
- Không đưa trường động như “thời điểm GET hiện tại” vào body mà giữ revision cũ.
- Cấu hình Jackson/serialization, content negotiation và quyền/variant không tạo nhiều body khác nhau dùng một strong tag sai.
- Version phải ổn định giữa các instance; không dùng đồng hồ JVM hiện tại làm ETag.

Chọn convention của representation ngay trong hợp đồng API và có test cho thay đổi ở mọi luồng dữ liệu.

## 6. Controller GET với ResponseEntity, ETag và Cache-Control

Các lớp giả định:

~~~java
public record DocumentView(
        UUID id, String title, String status, long revision) {}

public interface DocumentQueryService {
    DocumentView requireReadable(Authentication principal, UUID id);
}
~~~

**requireReadable** phải xác minh principal, tenant và quyền đọc ngay cả khi client gửi If-None-Match. Không cho người không đủ quyền nhận 304 chỉ vì họ đoán được một ETag.

~~~java
@RestController
@RequestMapping("/api/v1/documents")
public class DocumentController {
    private final DocumentQueryService queries;

    public DocumentController(DocumentQueryService queries) {
        this.queries = queries;
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentView> get(
            @PathVariable UUID id,
            Authentication principal) {

        DocumentView doc = queries.requireReadable(principal, id);
        String etag = DocumentEtags.strong(id, doc.revision());

        return ResponseEntity.ok()
                .eTag(etag)
                .cacheControl(CacheControl.noCache().cachePrivate())
                .body(doc);
    }
}
~~~

Spring MVC có hỗ trợ xử lý **conditional GET/HEAD** dựa trên validator của **ResponseEntity** trong pipeline phù hợp. Khi request chứa If-None-Match khớp, framework có thể trả **304** mà không serialize response body. **Tuy nhiên phương thức service vẫn được gọi**, vì phải lấy validator và kiểm tra quyền. Hãy chứng minh status và headers bằng **MockMvc integration test**, không dựa vào việc nhìn Java code rồi suy đoán.

Nếu dữ liệu quá nhạy cảm để browser cache lưu, thay bằng **CacheControl.noStore()**. Khi đó vẫn có thể gửi ETag phục vụ If-Match cho cập nhật, nhưng không trông đợi lợi ích caching từ 304.

**Lưu ý:** ví dụ có một JSON representation không thay đổi theo client/encoding, các trường phản ánh revision đồng bộ. Với API trả biểu diễn khác theo quyền, ngôn ngữ hoặc projection, phải điều chỉnh validator và **Vary**. Phân quyền không thể bị cache thay thế.

### 6.1. Khi muốn tối ưu việc truy vấn validator

Thay vì load JSON lớn, service có thể lấy **revision và quyền** bằng truy vấn nhẹ, đánh giá conditional GET rồi chỉ dựng body khi cần. Nếu chọn đường này:

1. Bảo đảm **snapshot nhất quán**: không đánh giá ETag v7 rồi trả body v8 với tag v7.
2. Dùng API conditional request của Spring như **WebRequest.checkNotModified(etag)** trong phạm vi GET thích hợp, hiểu rằng phương thức này có thể xử lý các precondition và thiết lập response.
3. Không trả cứng 304 khi phương thức checkNotModified trả true mà chưa biết HTTP status thích hợp (nó có thể biểu diễn việc **If-Match false** ở request có điều kiện).
4. Chọn transaction/read consistency khi đọc revision và body; với replica lag, cần chính sách freshness.

Trong đa số REST endpoint JSON nhỏ, **ResponseEntity với ETag** dễ giữ đúng hơn việc tự parse If-None-Match bằng chuỗi.

## 7. ShallowEtagHeaderFilter: tiện nhưng không miễn phí

Spring MVC có **ShallowEtagHeaderFilter** hỗ trợ tính ETag từ response content. Ví dụ cấu hình **chỉ áp dụng endpoint GET nhỏ, không nhạy cảm**, sau khi đã kiểm thử filter:

~~~java
@Configuration
public class EtagFilterConfig {
    @Bean
    public FilterRegistrationBean<ShallowEtagHeaderFilter> etagFilter() {
        var registration =
                new FilterRegistrationBean<ShallowEtagHeaderFilter>();
        registration.setFilter(new ShallowEtagHeaderFilter());
        registration.addUrlPatterns("/api/v1/catalog/*");
        registration.setOrder(10);
        return registration;
    }
}
~~~

**Tên “shallow” rất quan trọng:** handler thường vẫn phải chạy và **response body vẫn phải được tạo** để filter tính tag. Nó **không** thay thế kiểm tra version ở DB, không tự ngăn truy vấn tốn kém và có thể **buffer response** gây chi phí bộ nhớ.

| Cách tạo tag | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| **ResponseEntity.eTag(revision)** | Chủ động kiểm soát validator; có thể tránh serialize khi revalidate | Phải giữ revision đúng với representation |
| **ShallowEtagHeaderFilter** | Tạo validator từ output của endpoint, ít code | Handler vẫn chạy; có thể buffer body, bất lợi với streaming |
| **Hash content ở service** | Gắn với bytes đã serialize nếu làm đúng | Chi phí tính hash/serialization, memory với payload lớn |

**Không dùng filter một cách mù quáng cho StreamingResponseBody, video, tệp nhiều GiB hoặc SSE**. Nội dung private hoặc no-store vẫn phải chịu security policy, và filter không làm việc gì để phân quyền cho caller.

## 8. Vary, proxy/CDN, CORS và cache cá nhân

Cùng URL có thể trả representation khác:

~~~http
GET /api/v1/catalog
Accept-Language: vi
~~~

~~~http
HTTP/1.1 200 OK
Vary: Accept-Language
Cache-Control: public, max-age=120
ETag: "catalog-vi-r12"
~~~

Với **Accept-Language: en**, server phải cấp body/validator tương ứng. **Vary** nói cho cache biết request header nào tác động việc chọn representation; gateway và CDN phải cấu hình cache key phù hợp. Khi phiên bản API được chọn bằng media type, **Vary: Accept** đặc biệt quan trọng.

**Có Authorization không đồng nghĩa có thể shared-cache dữ liệu riêng.** Với API authenticated trả dữ liệu cá nhân, hãy ưu tiên **private, no-cache** hoặc **no-store** và kiểm tra policy của intermediary. Không áp **public, s-maxage** cho thông tin theo user/tenant chỉ để giảm tải DB.

### 8.1. CORS và việc đọc ETag từ JavaScript

ETag không nằm trong danh sách response headers mà JavaScript có thể đọc mặc định từ cross-origin Fetch. Nếu frontend ở origin khác cần giữ ETag để gửi If-Match, server có thể cấp:

~~~http
Access-Control-Expose-Headers: ETag
~~~

Đồng thời cấu hình CORS cho origin được phép, phương thức PUT/PATCH/DELETE và request headers **If-Match / If-None-Match** trong preflight khi áp dụng. Không đặt wildcard origin cùng credentials tùy tiện; CORS **không thay thế** kiểm tra xác thực/phân quyền server-side.

### 8.2. Cache invalidation không phải concurrency control

Nếu dữ liệu đổi, cache của collection/item có thể cần purge hoặc đổi key. CDN invalidation trễ có thể khiến client vừa GET đã nhận validator cũ và ngay sau đó PUT bị **412** tại origin. Điều này bảo vệ dữ liệu nhưng làm UX khó chịu. Đối với read-your-writes, cân nhắc đọc primary/consistency policy, invalidation đúng resource và theo dõi replica lag.

## 9. If-Match và ghi có điều kiện

Khác **If-None-Match** dùng trong GET revalidation, **If-Match** yêu cầu tài nguyên chưa đổi so với phiên bản client đã đọc trước khi PUT/PATCH/DELETE.

~~~http
PATCH /api/v1/documents/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "document-11111111-1111-4111-8111-111111111111-rev7"

{"title":"Bản đã rà soát"}
~~~

Khi tài liệu đã ở rev8, server thường từ chối:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{"type":"https://api.example.test/problems/stale",
 "title":"Document changed","status":412,
 "detail":"Hãy tải bản mới trước khi lưu.","code":"ETAG_MISMATCH"}
~~~

| Tình huống | Status |
| --- | --- |
| GET + If-None-Match trùng | **304**, không body |
| GET + If-None-Match cũ | **200**, representation mới |
| PATCH + If-Match sai | **412**, không thực hiện mutation |
| Thiếu If-Match khi API bắt buộc | **428 Precondition Required** |
| ETag đúng nhưng tài liệu bị khóa | **409 Conflict** |
| Chưa xác thực/không có quyền | **401/403**, hoặc 404 theo privacy policy |
| PATCH hoàn tất không có body | **204** |

**If-Match dùng strong comparison.** Weak tag **W/"..."** không được coi là strong match. Một danh sách entity tag có nghĩa **bất kỳ tag nào** khớp mạnh; **If-Match: \*** chỉ kiểm tra sự tồn tại của representation, **không chống lost update**. API cần bảo vệ phiên bản phải công bố chính sách strong tag cụ thể.

**Retry sau timeout:** một lần PATCH có thể đã commit v7→v8 dù response mất. Retry cùng ETag cũ có thể nhận 412; điều đó **không chứng minh lần đầu thất bại**. Tra GET/operation state, dùng idempotency cho side effect khi cần, không tự ép ghi lại với ETag mới.

## 10. Spring MVC: PATCH kết hợp SQL compare-and-swap

Ví dụ chỉ thay **title** qua **application/merge-patch+json**, từ chối null và string rỗng. Đặt phương thức sau vào **DocumentController** ở mục 6, inject thêm **DocumentAccess** và **DocumentUpdateService**.

~~~java
public record RenameDocumentRequest(
        @NotBlank @Size(max = 200) String title) {}

public record AuthorizedScope(UUID tenantId, UUID userId) {}

public interface DocumentAccess {
    AuthorizedScope requireWrite(Authentication principal, UUID id);
}

@PatchMapping(path = "/{id}", consumes = "application/merge-patch+json")
public ResponseEntity<Void> rename(
        @PathVariable UUID id,
        @Valid @RequestBody RenameDocumentRequest input,
        @RequestHeader(value = HttpHeaders.IF_MATCH, required = false)
        String ifMatch,
        Authentication principal) {

    var scope = access.requireWrite(principal, id);
    if (ifMatch == null || ifMatch.isBlank()) {
        throw new ResponseStatusException(
            HttpStatus.PRECONDITION_REQUIRED, "If-Match required");
    }

    updates.renameIfCurrent(scope.tenantId(), id, ifMatch, input.title());
    return ResponseEntity.noContent()
        .cacheControl(CacheControl.noStore()).build();
}
~~~

Đoạn code là **minh họa**, cần import, DTO/repository/security và exception mapping để chạy. Trả **204** không ETag; client GET lại nếu cần validator mới. Với PUT, HTTP còn điều kiện về validator khi body được biến đổi trước lúc lưu.

### 10.1. Service bảo vệ ý định phiên bản

~~~java
@Service
public class DocumentUpdateService {
    private final DocumentDao dao;

    public DocumentUpdateService(DocumentDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void renameIfCurrent(
            UUID tenantId, UUID id, String ifMatch, String title) {

        DocumentRow row = dao.requireActive(tenantId, id);
        String etag = DocumentEtags.strong(id, row.revision());

        // Giới hạn mẫu: chỉ một strong tag.
        if (!etag.equals(ifMatch)) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_FAILED, "ETag mismatch");
        }
        if (!"DRAFT".equals(row.status())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT, "Document locked");
        }

        int rows = dao.renameIfVersion(
            tenantId, id, row.revision(), title);
        if (rows != 1) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_FAILED, "Version changed");
        }
    }
}
~~~

**Giới hạn cần nêu:** phép **String.equals** không phải bộ đánh giá toàn bộ If-Match HTTP; chưa xử lý list, wildcard, weak tag và thứ tự precondition theo RFC 9110. Production phải dùng evaluator/parser phù hợp và test đầy đủ.

### 10.2. Ghi nguyên tử ở database

~~~sql
UPDATE documents
SET title = :title,
    revision = revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND tenant_id = :verifiedTenant
  AND revision = :expectedRevision
  AND status = 'DRAFT'
  AND deleted_at IS NULL;
~~~

DAO có thể dùng **NamedParameterJdbcTemplate.update(sql, params)** với tenant lấy từ principal. Nếu hai request đọc rev7, request đầu update rev8 thì request sau **không thể ghi đè rev8** qua predicate revision=7. Chỉ check header rồi UPDATE theo id là lỗi TOCTOU.

**Affected rows=0** có thể do version đổi, resource bị xóa hoặc trạng thái LOCKED; production phải phân loại **412/404/403/409** theo bằng chứng và privacy policy. Với JPA có thể dùng **@Version**, chú ý optimistic exception có thể xảy ra lúc **flush/commit**. Mọi background job/native SQL cũng phải tăng revision; chỉ trả 2xx khi transaction commit thành công.

### 10.3. Spring ProblemDetail

~~~java
// Method bên trong lớp @RestControllerAdvice.
@ExceptionHandler(DocumentStaleException.class)
ResponseEntity<ProblemDetail> stale(DocumentStaleException ex) {
    ProblemDetail p =
        ProblemDetail.forStatus(HttpStatus.PRECONDITION_FAILED);
    p.setTitle("Document changed");
    p.setProperty("code", "ETAG_MISMATCH");
    return ResponseEntity.status(412).body(p);
}
~~~

**DocumentStaleException** là exception ứng dụng cần định nghĩa. Ví dụ service dùng ResponseStatusException; hãy thống nhất mapper. Không tự chuyển DB timeout/deadlock thành 412 hoặc trả stack trace/PII.

## 11. Bảo mật và lỗi phổ biến

| Sai lầm | Hậu quả/khắc phục |
| --- | --- |
| Hiểu no-cache là không lưu | Dùng **no-store** nếu cần cấm lưu |
| Thiếu Cache-Control | Freshness khó kiểm soát |
| Shallow filter cho tệp lớn | Có thể buffer body, gây áp lực heap |
| Job sửa mà không tăng revision | Validator sai |
| 304 trước khi xác thực/phân quyền | Có thể lộ dữ liệu |
| Shared cache trộn tenant/variant | private/no-store, Vary và cache key |
| So ETag rồi UPDATE theo id | Lost update do race |
| Coi If-Match: * là version lock | Nó chỉ kiểm tra representation tồn tại |
| Retry mãi stale ETag | GET lại và merge có chủ đích |

ETag **không phải credential**. Caller có ETag của tài liệu tenant khác vẫn không được đọc/ghi. Browser cross-origin cần **Access-Control-Expose-Headers: ETag** nếu JavaScript muốn đọc header; CORS không thay authorization ở server.

## 12. OpenAPI 3.1 mô tả GET và PATCH

~~~yaml
openapi: 3.1.0
info:
  title: Document Conditional API
  version: 1.0.0
paths:
  /api/v1/documents/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema: { type: string, format: uuid }
    get:
      operationId: getDocument
      security: [{ bearerAuth: [] }]
      parameters:
        - name: If-None-Match
          in: header
          schema: { type: string }
      responses:
        '200':
          description: Representation hiện tại
          headers:
            ETag:
              schema: { type: string }
            Cache-Control:
              schema: { type: string }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Document'
        '304': { description: Không đổi, không có body }
        '401': { description: Chưa xác thực }
        '403': { description: Không đủ quyền }
        '404': { description: Không tìm thấy }
    patch:
      operationId: renameDocument
      security: [{ bearerAuth: [] }]
      parameters:
        - name: If-Match
          in: header
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              required: [title]
              additionalProperties: false
              properties:
                title: { type: string, minLength: 1, maxLength: 200 }
      responses:
        '204': { description: Đã cập nhật }
        '400': { description: Dữ liệu sai }
        '401': { description: Chưa xác thực }
        '403': { description: Không đủ quyền }
        '404': { description: Không tìm thấy }
        '409': { description: Tài liệu khóa }
        '412':
          description: ETag không còn đúng
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '428': { description: Thiếu If-Match }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    Document:
      type: object
      required: [id, title, status, revision]
      properties:
        id: { type: string, format: uuid }
        title: { type: string }
        status: { type: string }
        revision: { type: integer, minimum: 0 }
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        code: { type: string }
~~~

**OpenAPI không tự thực thi cache/security/DB CAS**; production bổ sung headers vào 304, các response 415/422 theo contract và ví dụ lỗi.

## 13. MockMvc và integration tests

~~~java
@Test
void currentEtagReturns304() throws Exception {
    UUID id = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");
    String tag = DocumentEtags.strong(id, 7L);

    mvc.perform(get("/api/v1/documents/{id}", id)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken)
            .header(HttpHeaders.IF_NONE_MATCH, tag))
        .andExpect(status().isNotModified())
        .andExpect(header().string(HttpHeaders.ETAG, tag))
        .andExpect(content().string(""));
}
~~~

Fixture có tài liệu revision 7 và principal hợp lệ. Các tình huống phải kiểm tra:

| Ca | Kết quả |
| --- | --- |
| GET đầu tiên/If-None-Match cũ | 200, JSON và ETag |
| If-None-Match đúng | 304 không body |
| Token hết hạn/tenant sai | Không trả 304 trái quyền |
| PATCH tag đúng/cũ/thiếu | 204 / 412 / 428 |
| PATCH weak tag/If-Match: * | Tuân semantics và policy |
| Hai PATCH cùng revision | Tối đa một transaction thành công |
| Tài liệu LOCKED | 409 khi tag đúng |
| Job thay đổi body | ETag đổi |
| Cache các tenant/variant | Không trộn response |
| Retry sau timeout/DB lỗi | Không tạo side effect trùng |

**MockMvc chỉ với mock service không chứng minh CAS ở DB**. Integration test dùng DB thật, hai transaction và barrier; assert version/nội dung cuối. Đo 304/412/428, p95, query count và chi phí bộ nhớ, tránh token/PII trong metric labels.

## 14. Bài thực hành

Thiết kế API Spring Boot cho **document(id, tenantId, title, status, revision)**. Hai người cùng sửa title; web thường GET lại và tài liệu không được lưu ở shared cache.

**Nhiệm vụ 100 điểm:** HTTP GET có ETag/Cache-Control/304 (25); Spring PATCH If-Match + SQL CAS hoặc @Version, 412/428/409 (30); quyền tenant, Vary/CORS (20); tối thiểu tám test gồm tag cũ, 304, concurrency, LOCKED, job, cross-tenant và retry (25).

**Hướng giải:** dùng **private, no-cache** khi cho browser lưu nhưng bắt buộc revalidate, hoặc **no-store** khi cấm lưu. Server kiểm quyền trước 304; PATCH ghi với version predicate nguyên tử. Khi nhận 412, client giữ bản sửa local, GET lại rồi quyết định merge.

## 15. Checklist và tài liệu

- [ ] Phân biệt strong/weak ETag, If-None-Match và If-Match.
- [ ] Hiểu no-cache khác no-store, private khác public.
- [ ] GET 304 không body, không bỏ auth.
- [ ] ResponseEntity/CacheControl đã được test.
- [ ] Không dùng shallow filter cho payload lớn.
- [ ] Có Vary, CORS và tenant isolation.
- [ ] PATCH có If-Match và DB version predicate.
- [ ] Trả 304/412/428/409 đúng nghĩa.

**Ghi nhớ:** ETag/Cache-Control phục vụ caching; If-None-Match xác thực lại GET; If-Match bảo vệ kỳ vọng phiên bản. Cả hai không thay thế authorization hay giao dịch nguyên tử.

**Nguồn chuẩn:** RFC 9110, RFC 9111, RFC 6585, RFC 9457, RFC 5789, OpenAPI 3.1 và Spring MVC.
