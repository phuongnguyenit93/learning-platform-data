# Phân quyền cho tìm kiếm, batch, job và tệp đính kèm

## 1. Bối cảnh và mục tiêu

Trong module **INTEGRATION_API_REST**, một endpoint có URI, phương thức, status và xác thực hợp lệ vẫn có thể rò dữ liệu khi việc phân quyền chỉ được thực hiện ở controller. Các API **tìm kiếm, thao tác hàng loạt, tác vụ nền và tệp đính kèm** cần kiểm quyền trên **từng resource và từng bước xử lý**, không chỉ kiểm token có tồn tại.

Xét dịch vụ quản lý tài liệu SaaS đa tenant:

- **GET /api/v1/documents**: tìm kiếm theo tên, trạng thái, chủ sở hữu.
- **POST /api/v1/documents:archive-batch**: lưu trữ nhiều tài liệu.
- **POST /api/v1/export-jobs**: tạo job xuất CSV bất đồng bộ.
- **GET /api/v1/export-jobs/{id}**: xem tiến độ/kết quả.
- **POST /api/v1/documents/{id}/attachments**: đính kèm tệp.
- **GET /api/v1/documents/{id}/attachments/{attachmentId}/content**: tải nội dung tệp.

Mỗi tài liệu có **tenantId, ownerId, ACL, classification, status, revision**. Một người có thể xem tài liệu A nhưng không được xem B, lưu trữ A nhưng không có quyền với B; quyền của họ cũng có thể bị thu hồi sau khi job được đưa vào queue.

**Mục tiêu:** thiết kế authorization theo **object, action, field và tenant**; xử lý search/count/facet an toàn; batch atomic/partial; job identity và revocation; upload/download, presigned URLs; ví dụ HTTP/Java/Spring, OpenAPI, security tests và bài tập.

**Quy tắc:** quyền gọi endpoint **không** đồng nghĩa quyền trên mọi ID trong query, request body, queue payload hoặc object storage. Worker có service account mạnh cũng không tự được phép bỏ qua quyền của người đã yêu cầu export.

## 2. Threat model và ma trận quyền

~~~mermaid
flowchart LR
    C[Client + JWT] --> F[Security filter]
    F --> A[Spring Controller]
    A --> P[Permission policy]
    P --> D[(Tenant-scoped database)]
    P --> Q[Job queue]
    Q --> W[Worker + delegated scope]
    W --> P
    P --> O[Private object storage]
    W --> O
~~~

| Bề mặt | Lỗ hổng thường gặp | Quy tắc |
| --- | --- | --- |
| Search | Chỉ lọc tenant sau LIMIT hoặc trong controller | Scope **trong** DB/index query trước pagination |
| Count/facets | Tổng đếm trên dữ liệu không được xem | Aggregate trên tập dữ liệu đã authorize |
| Batch | Kiểm quyền của một ID rồi UPDATE mọi ID | Mỗi target phải được authorize và ghi có điều kiện |
| Async job | Worker dùng quyền service toàn cục | Chỉ dùng scope đã ủy nhiệm, kiểm lại khi thực thi |
| Job status/result | Đoán jobId của người khác | Kiểm tenant, owner và quyền xem kết quả |
| Attachment | Đoán storage key/URL, bypass parent ACL | Parent + attachment ACL, private storage, scan |
| Cache | Tenant A/B nhận chung kết quả | No-store/private hoặc key bao quyền/tenant |

Một mô hình permission minh họa:

| Operation | Scope đầu vào | Điều kiện object |
| --- | --- | --- |
| Search tài liệu | **documents:read** | Tenant + owner/ACL/visibility |
| Archive item | **documents:archive** | ACL archive + revision + trạng thái |
| Tạo export | **exports:create** | Field/filter/row scope được phép |
| Xem/hủy job | **exports:read/cancel** | Tenant + owner hoặc quyền quản trị cụ thể |
| Upload | **attachments:write** | Được sửa đúng parent document |
| Download | **attachments:read** | Được đọc parent và attachment đã sẵn sàng |

**Deny-by-default**: nếu thiếu quyền, không tự cho phép chỉ vì người dùng có role **ADMIN** trong một tenant khác. Đừng tin tenantId/ownerId, isAdmin hay ACL do client tự gửi.

## 3. Authentication context và enforcement ở service

Tạo một ngữ cảnh đã xác minh từ Spring Security:

~~~java
public record Caller(
        UUID userId, UUID tenantId, Set<String> permissions) {
    public boolean can(String scope) {
        return permissions.contains(scope);
    }
}

public interface CallerResolver {
    // Identity + active tenant + membership được server xác minh.
    Caller require(Authentication principal);
}

public interface DocumentPolicy {
    void requireRead(Caller caller, UUID documentId);
    void requireArchive(Caller caller, UUID documentId);
    void requireWriteAttachment(Caller caller, UUID documentId);
}
~~~

Ở controller, **@PreAuthorize** hoặc SecurityFilterChain chặn thao tác thiếu scope:

~~~java
@PreAuthorize("hasAuthority('SCOPE_documents:read')")
@GetMapping("/api/v1/documents")
public DocumentPage search(
        @RequestParam(required = false) String status,
        @RequestParam(name = "q", required = false) String query,
        @RequestParam(defaultValue = "25") int limit,
        Authentication principal) {
    return searchService.search(
        callerResolver.require(principal), status, query, limit);
}
~~~

**Method security phải được bật** và mapping authority phải khớp cấu hình JWT thực tế. Check scope ở controller **không** kiểm được owner/ACL trên từng document; service/query vẫn phải làm điều đó. Spring method-security/transaction proxy có thể bị bypass bởi **self-invocation**; kiểm tra kiến trúc và test thực.

Nếu header **X-Tenant-Id** được dùng để chọn active tenant, server phải kiểm membership ở tenant đó. Worker hoặc microservice gọi thay người dùng cần **service identity** và **delegated user context** đã xác minh, không tin X-User-Id hoặc tenant tùy ý trong request.

## 4. Search: điều kiện quyền phải ở trong SQL/index query

~~~http
GET /api/v1/documents?status=DRAFT&q=budget&limit=25 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

Một lỗi cú pháp nguy hiểm:

~~~sql
-- SAI: OR vượt khỏi tenant/owner vì AND ưu tiên cao hơn OR.
WHERE tenant_id = :tenant
  AND owner_id = :viewer
   OR title ILIKE :pattern
~~~

Cách an toàn: predicate an ninh **AND** với filters của client:

~~~sql
SELECT d.id, d.title, d.status, d.created_at
FROM documents d
WHERE d.tenant_id = :trustedTenant
  AND d.deleted_at IS NULL
  AND (
    d.owner_id = :viewer
    OR d.visibility = 'TENANT'
    OR EXISTS (
      SELECT 1 FROM document_acl a
      WHERE a.document_id = d.id
        AND a.tenant_id = d.tenant_id
        AND a.user_id = :viewer
        AND a.can_read = TRUE
    )
  )
  AND (:status IS NULL OR d.status = :status)
  AND (:query IS NULL OR d.search_vector @@ :query)
ORDER BY d.created_at DESC, d.id DESC
LIMIT :boundedLimit;
~~~

Cú pháp **@@** minh họa PostgreSQL full-text search; implementation phải parse/bind tsquery đúng loại, dùng parameterized SQL và index. **Không nối raw WHERE/ORDER BY từ client.**

**Bất biến bảo mật search:**

1. Tenant/owner/ACL do server áp đặt, **không cho client xóa hoặc OR vượt qua**.
2. Quyền áp trước **LIMIT/OFFSET/keyset cursor**, không filter kết quả sau phân trang.
3. Chỉ cho filter, sort, aggregation trên **field có quyền**; không cho query password/secret/field nhạy cảm.
4. Bounded page size (ví dụ default 25, max 100), stable sort và cursor buộc với query, tenant và policy context.
5. Response projection cũng phải đúng quyền field: quyền xem title chưa chắc cho phép xem body.
6. Nếu dùng Elasticsearch hay cache index, authorization phải được push down vào chính truy vấn ở tầng đó; search index không tự an toàn vì DB gốc có ACL.

### 4.1. Spring service và repository scoped

~~~java
public record DocumentSummary(UUID id, String title, String status) {}
public record DocumentPage(
        List<DocumentSummary> items, String nextCursor) {}

@Service
public class DocumentSearchService {
    private final DocumentSearchRepository repository;

    public DocumentSearchService(DocumentSearchRepository repository) {
        this.repository = repository;
    }

    public DocumentPage search(
            Caller caller, String status, String query, int limit) {
        if (!caller.can("documents:read")) {
            throw new AccessDeniedException("Read scope required");
        }
        int bounded = Math.max(1, Math.min(limit, 100));
        List<DocumentSummary> items = repository.findVisible(
            caller.tenantId(), caller.userId(),
            status, query, bounded);
        // Cursor là null trong bản minh họa; production phải tạo
        // nextCursor có ràng buộc scope/filter khi còn trang tiếp theo.
        return new DocumentPage(items, null);
    }
}
~~~

**findVisible** phải thực hiện predicate tenant + ACL như SQL trên; đây là abstraction cần định nghĩa, không phải Spring Data method tự hiểu ACL. Nếu dùng **Specification**, bắt buộc **securityScope.and(clientFilters)**. Join ACL có thể tạo duplicate, ảnh hưởng paging/count; cần EXISTS/distinct và test.

### 4.2. Count, facet, suggest cũng có thể tiết lộ dữ liệu

~~~http
GET /api/v1/documents?ownerId=victim&includeTotal=true
GET /api/v1/documents/facets?groupBy=classification
GET /api/v1/documents/suggest?q=confidential
~~~

Nếu count, facets hoặc autocomplete chạy trên toàn bảng trước khi kiểm ACL, caller có thể suy ra tài liệu bí mật tồn tại dù không nhận JSON item nào. Chỉ tính thống kê trên tập được phép xem; cân nhắc **không công bố exact total**, dùng hasNext/nextCursor thay vì rò số lượng. Cache query theo q đơn lẻ cũng nguy hiểm: dùng **private, no-store** cho dữ liệu nhạy cảm hoặc key theo tenant, caller/permission version, filter, projection.

PostgreSQL **RLS** là defense-in-depth, không thay app policy. Với connection pool phải set/reset tenant context theo transaction, tránh context của request trước rò sang request sau. Không để DB role bypass RLS ngoài chủ đích.

## 5. Batch: phân quyền từng item và chọn rõ atomicity

~~~http
POST /api/v1/documents:archive-batch HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: archive-2026-001

{
  "items": [
    {"id":"11111111-1111-4111-8111-111111111111","revision":7},
    {"id":"22222222-2222-4222-8222-222222222222","revision":3}
  ]
}
~~~

**Không** kiểm quyền trên phần tử đầu rồi archive tất cả. Với mỗi item, phải kiểm **tenant, archive permission, document ACL, state, revision**. Không nhận tenantId hoặc cờ force từ body trừ khi API có operation riêng và policy chặt.

| Chế độ | Semantics | HTTP response |
| --- | --- | --- |
| **Atomic** | Tất cả thành công hoặc rollback, transaction phù hợp | 2xx khi tất cả commit; lỗi cho toàn request khi không đạt |
| **Partial** | Mỗi item là transaction/operation độc lập | **200** với kết quả từng item hoặc **207** nếu hợp đồng chọn WebDAV semantics |
| **Async batch** | Đưa work vào queue, xử lý sau | **202 Accepted** + Location job status |

**207 Multi-Status** xuất phát từ WebDAV; không bắt buộc cho mọi REST batch và không nên dùng nếu SDK không xử lý. Một response **200** có results per item rõ ràng thường dễ tích hợp.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "results": [
    {"id":"11111111-1111-4111-8111-111111111111","status":200,"code":"ARCHIVED"},
    {"id":"22222222-2222-4222-8222-222222222222","status":404,"code":"NOT_FOUND"}
  ]
}
~~~

**404** cho item bị ẩn/không thấy trong tenant theo privacy policy; 403 có thể dùng khi được biết item tồn tại nhưng thiếu quyền archive. Không trả tên, owner, tenant hoặc dữ liệu nhạy cảm trong lỗi item không được phép.

Giới hạn **maxItems** (ví dụ 50), body bytes, rate/quota; xử lý duplicate ID nhất quán (reject/dedup), tránh batch 100 nghìn ID làm cạn DB. **If-Match** một tag ở header không tự biểu diễn revision của từng document; dùng revision per item hoặc contract preconditions rõ ràng.

## 6. Java/Spring: update từng hàng có điều kiện an toàn

~~~java
public record ArchiveItem(UUID id, long revision) {}

public record ArchiveBatchRequest(
        @NotEmpty @Size(max = 50)
        List<@Valid ArchiveItem> items) {}

public record ItemResult(UUID id, int status, String code) {}
~~~

Controller xác minh scope và chuyển Caller từ authentication:

~~~java
@PreAuthorize("hasAuthority('SCOPE_documents:archive')")
@PostMapping("/api/v1/documents:archive-batch")
public ResponseEntity<List<ItemResult>> archive(
        @Valid @RequestBody ArchiveBatchRequest body,
        Authentication authentication) {
    Caller caller = callerResolver.require(authentication);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(batchService.archiveEach(caller, body.items()));
}
~~~

Với partial success, service cho mỗi item nên là **bean riêng** có transaction riêng; đừng dùng một transaction ngoài bao toàn batch rồi kỳ vọng lỗi một item không rollback cả batch.

~~~java
@Service
public class ArchiveOneService {
    private final NamedParameterJdbcTemplate jdbc;

    public ArchiveOneService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public boolean archive(Caller caller, ArchiveItem item) {
        String sql = """
            UPDATE documents d
               SET status = 'ARCHIVED', revision = revision + 1
             WHERE d.id = :id
               AND d.tenant_id = :tenant
               AND d.revision = :revision
               AND d.status = 'DRAFT'
               AND d.deleted_at IS NULL
               AND EXISTS (
                 SELECT 1 FROM document_acl a
                  WHERE a.document_id = d.id
                    AND a.tenant_id = d.tenant_id
                    AND a.user_id = :user
                    AND a.can_archive = TRUE
               )
            """;
        var args = new MapSqlParameterSource()
            .addValue("id", item.id())
            .addValue("tenant", caller.tenantId())
            .addValue("user", caller.userId())
            .addValue("revision", item.revision());
        return jdbc.update(sql, args) == 1;
    }
}
~~~

**Đây là mẫu policy yêu cầu ACL can_archive**; nếu owner/admin cũng có quyền, phải mã hóa đúng rule đó trong predicate và kiểm scope archive ở service. Đưa ACL vào **UPDATE** giúp hạn chế race khi quyền/state đổi, nhưng isolation và thời điểm revoke vẫn cần thiết kế nhất quán.

**affectedRows=0** không chứng minh 404 hay 412: có thể thiếu quyền, bị xóa, đổi revision hoặc bị LOCKED. Chỉ phân loại sau lookup có scope an toàn; 404 che tài nguyên người khác, 409 cho state, 412 cho stale revision nếu caller được phép biết resource. Không query toàn DB để trả metadata của tenant khác.

**@Transactional(REQUIRES_NEW)** có tác dụng khi gọi qua Spring proxy từ bean khác. Service điều phối catch lỗi domain đã biết để trả ItemResult; lỗi DB down/timeout không được nuốt thành 404. Atomic batch dùng một transaction và rollback toàn bộ; partial batch phải audit từng kết quả.

## 7. Idempotency và audit cho batch

Khi POST timeout sau commit, client không biết kết quả. **Idempotency-Key** cần được server lưu theo **tenant, actor/permission scope, operation, request fingerprint, TTL**; key cũ với payload mới phải được xử lý như conflict, không chạy silently. Replay kết quả cần kiểm quyền xem lại để không tiết lộ item sau khi caller mất quyền.

Audit nên ghi **actor, tenant, target ID, action, outcome, request/job ID**; không log token, nguyên payload chứa bí mật hoặc response của tài nguyên bị cấm. Duplicate item, partial commit và retry phải có quy tắc rõ để event audit nhất quán.

## 8. Async job: quyền lúc submit không tự tồn tại mãi

Với export lớn, tạo job thay vì trả CSV ngay:

~~~http
POST /api/v1/export-jobs HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: export-2026-001

{"type":"DOCUMENTS_CSV","filters":{"status":"DRAFT"},
 "fields":["id","title","createdAt"]}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/export-jobs/33333333-3333-4333-8333-333333333333
Cache-Control: no-store
Content-Type: application/json

{"id":"33333333-3333-4333-8333-333333333333","state":"QUEUED"}
~~~

**202 chỉ xác nhận nhận xử lý**, không xác nhận kết quả cuối hoặc mọi tài liệu vẫn được phép xuất. Submit phải kiểm **exports:create**, các field/filter được phép, quota row/bytes và concurrency. Server gắn **tenantId, submittedBy, normalizedFilters, field allowlist, policyVersion, idempotency fingerprint, expiry** vào job record.

**Không lưu bearer token trong queue** để worker dùng lại sau nhiều giờ. Quyền có thể bị revoke trong lúc job chờ: với dữ liệu nhạy cảm, nên **re-evaluate authorization khi worker đọc object, và khi người dùng tải kết quả**; nếu sản phẩm cố định quyền ở thời điểm submit, phải có mô hình delegation có phạm vi và thời hạn rõ, được audit và được chấp thuận về rủi ro.

## 9. Worker: service account không phải quyền nghiệp vụ của caller

Worker có quyền kỹ thuật đọc DB hoặc object storage **không đồng nghĩa** được phép xuất mọi tài liệu. Không dùng:

~~~java
// KHÔNG AN TOÀN: đọc toàn tenant, bỏ qua ACL người tạo job.
var rows = documents.findByTenantId(job.tenantId());
~~~

Một job an toàn cần trình tự:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as API
    participant J as Job store
    participant W as Worker
    participant D as DB + policy
    participant O as Private storage
    U->>A: POST /export-jobs
    A->>D: Check exports:create + requested fields
    A->>J: Create job with trusted scope
    A-->>U: 202 + Location
    W->>J: Claim job + lease
    W->>D: Recheck membership, ACL, policy
    W->>D: Stream only visible data
    W->>O: Write private result
    W->>J: Mark COMPLETE
    U->>A: GET job result
    A->>D: Authorize tenant, owner, current rights
    A->>O: Stream result or sign short-lived URL
~~~

**Worker checklist:**

1. Claim job với lease/attempt ID để tránh hai worker cùng chạy và ghi kết quả trùng; có retry/dedup theo trạng thái.
2. Dùng **service identity** cho hạ tầng nhưng giữ **submittedBy, trustedTenant, normalizedFilters, field allowlist** của job.
3. Kiểm lại tenant membership, **exports:create**, field permission và **ACL trên từng document** theo chính sách thực thi. Không dùng full bearer token cũ lưu trong queue.
4. Giới hạn rows/bytes/thời gian, chống CSV formula injection nếu mở bằng spreadsheet; stream theo page thay vì tải toàn bộ vào RAM.
5. Ghi output vào private storage; chỉ đánh dấu COMPLETE **sau khi output tồn tại và đã verify**.
6. Khi cancel/fail/revoke, dọn file tạm và không công bố partial output. Audit actor gốc và worker identity.

Java skeleton:

~~~java
public record ExportScope(
    UUID tenantId, UUID requesterId,
    Set<String> allowedFields, SearchInput filters) {}

public interface ExportAuthorization {
    ExportScope requireCurrentScope(ExportJob job);
}

public interface ExportDocumentRepository {
    // Truy vấn phải buộc tenant + ACL của requester.
    Stream<DocumentExportRow> streamVisible(ExportScope scope);
}

@Service
public class ExportWorkerService {
    private final ExportAuthorization authorization;
    private final ExportDocumentRepository repository;
    private final ExportStorage storage;

    public void execute(ExportJob job) {
        ExportScope scope =
            authorization.requireCurrentScope(job);

        try (Stream<DocumentExportRow> rows =
                 repository.streamVisible(scope)) {
            storage.writePrivateCsv(
                job.id(), rows, scope.allowedFields());
        }
        // Verify output, then commit job COMPLETE.
    }
}
~~~

Đây là **abstraction**, cần triển khai leasing, quota, transaction boundaries và error handling. **Không giữ DB transaction mở xuyên quá trình upload file dài hàng giờ**: đọc theo page/chunk, kiểm quyền/revocation định kỳ và commit progress. Quyền có thể bị thu hồi giữa hai chunk; nếu cần fail-closed, hủy job và xóa output tạm. Chọn snapshot delegation chỉ khi có **phạm vi và TTL rõ ràng**, đã chấp nhận rủi ro.

## 10. Job status, cancellation và result đều phải kiểm quyền

~~~http
GET /api/v1/export-jobs/33333333-3333-4333-8333-333333333333 HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id":"33333333-3333-4333-8333-333333333333",
  "state":"COMPLETE",
  "resultUrl":"/api/v1/export-jobs/33333333-3333-4333-8333-333333333333/result"
}
~~~

Job là **resource có owner, tenant và quyền riêng**. Người ở tenant khác không được đọc state, filter, output rows hay error; dùng **404** để che tồn tại theo privacy policy. **GET /result** phải kiểm **owner/tenant và quyền hiện tại đối với dữ liệu xuất**, không coi kết quả COMPLETE là public. Output cần TTL/retention và dọn orphan.

Nếu hỗ trợ **POST /api/v1/export-jobs/{id}:cancel**, chỉ owner hoặc quyền **exports:cancel** được yêu cầu; worker cần cooperative cancellation. Job COMPLETE có thể trả **409** nếu không còn hủy được. Dùng 202 cho yêu cầu hủy bất đồng bộ; phân biệt với DELETE xóa job metadata. Polling cần quota/Retry-After, lỗi FAILED không rò stack trace, internal bucket key hoặc tenant khác.

## 11. Attachments: parent ACL, metadata và an toàn nội dung

~~~http
POST /api/v1/documents/11111111-1111-4111-8111-111111111111/attachments HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="file"; filename="contract.pdf"
Content-Type: application/pdf

(binary data)
--...--
~~~

**Upload** phải kiểm quyền sửa đúng **parent document** và permission attachments:write. Không suy từ việc user được GET document rằng họ được đính kèm hoặc thay file. Trước khi công bố file:

- Bounded size, total request bytes, file count, quota/rate; kiểm **magic bytes**/content type thực, không tin filename/extension/MIME do client khai.
- Sinh **attachmentId và private object key** tại server, không dùng tên file làm path.
- Lưu metadata trusted **tenantId, documentId, uploader, size, digest, scanState, createdAt**; không tin ownerId từ body.
- Upload vào **private quarantine**, scan malware, kiểm loại tệp và decompression bomb, rồi mới chuyển **AVAILABLE**.
- Giới hạn object storage permissions, mã hóa, TTL/retention và cleanup khi upload fail hoặc tài liệu bị xóa.
- Nếu scan bất đồng bộ, **202 Accepted** hoặc resource **201 Created** với trạng thái PENDING_SCAN theo contract; không cho download trước AVAILABLE.

**Download** phải xác minh đồng thời **attachment thuộc parent ID**, parent thuộc trusted tenant, caller có quyền đọc parent **và attachment**, scan state đã AVAILABLE, file không bị revoked/deleted.

~~~sql
SELECT a.id, a.object_key, a.content_type, a.length_bytes
FROM attachments a
JOIN documents d ON d.id = a.document_id
WHERE d.id = :documentId
  AND d.tenant_id = :trustedTenant
  AND a.id = :attachmentId
  AND a.document_id = d.id
  AND a.scan_state = 'AVAILABLE'
  AND d.deleted_at IS NULL
  AND (
    d.owner_id = :viewer
    OR EXISTS (
      SELECT 1 FROM document_acl acl
      WHERE acl.document_id = d.id
        AND acl.tenant_id = d.tenant_id
        AND acl.user_id = :viewer
        AND acl.can_read = TRUE
    )
  );
~~~

Nếu attachment có classification/ACL riêng, phải **thêm predicate** tương ứng; SQL trên chỉ minh họa parent read policy. Không lấy object_key bằng attachmentId toàn cục rồi trả file. Key nội bộ không được serialize vào response.

## 12. Presigned URL: capability tạm thời phải được cấp sau ACL

Với tệp lớn, sau khi kiểm quyền ở REST API, server có thể trả **presigned URL** do private storage ký. **Ai sở hữu URL còn hạn có thể dùng URL** trong phạm vi method/object đã ký, vì vậy URL gần như một bearer capability.

- Ký đúng **object key, HTTP method GET/PUT, TTL ngắn**, checksum/size/content-type nếu provider hỗ trợ.
- Không trả raw bucket key, không nhúng URL vào analytics, log, email không bảo vệ hoặc Referer.
- Storage phải **private**, không bật public-read/list; CORS bucket không thay ACL.
- Khi quyền bị revoke, URL đã ký **có thể tiếp tục hợp lệ đến hết TTL**. Nếu cần revoke tức thời, dùng proxy kiểm quyền mỗi lần GET, hoặc giải pháp key/revocation tương thích storage.
- Signed URL cho upload không có nghĩa file được publish: cần **finalize**, verify object, scan và kiểm metadata/tenant trước khi đổi AVAILABLE.
- CDN/cache phải tuân chính sách riêng; không để file private được cache theo object key bỏ qua quyền.

Cấp URL bằng API **GET /documents/{id}/attachments/{attachmentId}/download-link** chỉ sau khi kiểm parent + attachment ACL. Với file cực kỳ nhạy cảm, có thể không cấp signed URL mà stream qua application để tăng kiểm soát audit/revocation.

## 13. Spring MVC upload/download: ví dụ ranh giới an toàn

~~~java
@PostMapping(
    path = "/api/v1/documents/{id}/attachments",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<AttachmentInfo> upload(
        @PathVariable UUID id,
        @RequestPart("file") MultipartFile file,
        Authentication authentication) {

    Caller caller = callerResolver.require(authentication);
    attachmentPolicy.requireWrite(caller, id);
    AttachmentInfo pending =
        attachmentService.stageAndScan(caller, id, file);

    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(pending);
}
~~~

**stageAndScan** cần size cap, quarantine, AV pipeline và timeout; việc parse multipart/temp file có thể xảy ra trước controller, nên cũng đặt **multipart size limits và quotas tại proxy/framework**.

~~~java
@GetMapping("/api/v1/documents/{id}/attachments/{fileId}/content")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID id,
        @PathVariable UUID fileId,
        Authentication authentication) {

    Caller caller = callerResolver.require(authentication);
    AuthorizedAttachment file =
        attachmentService.requireReadable(caller, id, fileId);

    StreamingResponseBody stream = output ->
        storage.copyTo(file.privateObjectKey(), output);

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"download.bin\"")
        .header("X-Content-Type-Options", "nosniff")
        .cacheControl(CacheControl.noStore())
        .body(stream);
}
~~~

Các class là **interfaces/DTO ứng dụng**, phải inject và triển khai. File name cố định giúp tránh header injection; production có thể tạo filename đã sanitize và encoding chuẩn. **StreamingResponseBody chạy sau controller**: cần async executor, timeout, quản lý hủy/close và chính sách revoke mid-stream. Khi response đã commit, lỗi object storage không thể đổi thành JSON 403/500; phải abort stream và log an toàn.

## 14. Cache, audit, quota và race

| Lớp | Chính sách |
| --- | --- |
| **Cache HTTP/CDN** | private/no-store cho search/job/file riêng; không cache response chỉ theo query hoặc signed key |
| **Audit** | Actor, trusted tenant, resourceId, operation, outcome, requestId/jobId; không log token/URL ký |
| **Quotas** | Search page, batch size, exports/tenant, rows/bytes, upload size/count, polling |
| **DB writes** | Tenant + ACL + revision predicate, transaction boundaries |
| **Cleanup** | Expired jobs, cancelled exports, scan fail, orphan files |
| **Privacy** | Không rò qua 404/403 khác nhau tùy tiện, count, facet hoặc error details |

Authorization có thể đổi từ **T1 sang T2**. Với mutation ngắn, kết hợp kiểm quyền và UPDATE trong transaction; với job/stream dài, định nghĩa checkpoint/revoke và policy publish rõ. Không dùng một service account hay một câu check ở đầu request để coi toàn bộ workflow luôn hợp lệ.

## 15. HTTP status và Problem Details

| Tình huống | Mã HTTP |
| --- | --- |
| Search thành công, không có dữ liệu được xem | **200** với items rỗng |
| Batch partial hoàn tất | **200** và kết quả từng item; 207 chỉ theo hợp đồng WebDAV |
| Job hoặc scan tệp mới được tiếp nhận | **202** + Location, chưa phải xử lý thành công |
| Tạo metadata file đồng bộ | **201** khi phù hợp contract |
| Download hợp lệ | **200**, hoặc 206 nếu hỗ trợ Range |
| Token thiếu/sai | **401** + challenge |
| Thiếu quyền, hoặc resource không được công bố | **403/404** theo privacy policy nhất quán |
| Payload không hợp lệ | **400**, đôi khi 422 theo contract |
| Document bị khóa hoặc hủy job đã COMPLETE | **409** |
| If-Match/revision lỗi thời | **412** |
| File quá lớn, media type sai, vượt quota | **413/415/429** |
| DB hoặc object storage lỗi | **5xx** phù hợp |

Ví dụ **RFC 9457**:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.test/problems/denied",
 "title":"Action not permitted","status":403,
 "code":"ARCHIVE_DENIED"}
~~~

Không đưa tên tài liệu, tenant của người khác, signed URL, object key, token hoặc stack trace vào response. Lỗi từ gateway/Spring Security filter có thể phát sinh trước controller, nên phải thống nhất error policy ở nhiều tầng.

## 16. Hợp đồng OpenAPI 3.1

OpenAPI giúp client hiểu request/status nhưng **không tự triển khai ACL**:

~~~yaml
openapi: 3.1.0
info:
  title: Secure Documents API
  version: 1.0.0
paths:
  /api/v1/documents:
    get:
      operationId: searchDocuments
      security: [{ bearerAuth: [] }]
      parameters:
        - in: query
          name: limit
          schema: { type: integer, minimum: 1, maximum: 100, default: 25 }
      responses:
        '200':
          description: Chỉ documents caller được phép xem
          content:
            application/json:
              schema:
                type: object
                properties:
                  items: { type: array, items: { type: object } }
                  nextCursor: { type: [string, 'null'] }
        '403': { description: Không có quyền search }
  /api/v1/documents:archive-batch:
    post:
      operationId: archiveBatch
      security: [{ bearerAuth: [] }]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [items]
              additionalProperties: false
              properties:
                items:
                  type: array
                  minItems: 1
                  maxItems: 50
                  items:
                    type: object
                    required: [id, revision]
                    properties:
                      id: { type: string, format: uuid }
                      revision: { type: integer, minimum: 0 }
      responses:
        '200':
          description: Kết quả an toàn cho từng item
        '403': { description: Không có quyền batch archive }
  /api/v1/export-jobs:
    post:
      operationId: submitExportJob
      security: [{ bearerAuth: [] }]
      responses:
        '202':
          description: Nhận job và trả Location
          headers:
            Location:
              schema: { type: string }
        '403': { description: Không có quyền export }
        '429': { description: Vượt quota }
  /api/v1/export-jobs/{jobId}:
    get:
      operationId: getExportJob
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: jobId
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200': { description: Job status theo owner và tenant }
        '404': { description: Không có job được phép xem }
  /api/v1/documents/{id}/attachments/{attachmentId}/content:
    get:
      operationId: downloadAttachment
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
        - in: path
          name: attachmentId
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200':
          description: Binary chỉ sau parent + attachment ACL
          content:
            application/octet-stream:
              schema: { type: string, format: binary }
        '403': { description: Không có quyền tải }
        '404': { description: Tệp không được công bố }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
~~~

Đây là **bản rút gọn**; production bổ sung requestBody export, upload endpoint, error schemas, status examples, scopes và content negotiation. **additionalProperties: false không tự khiến Jackson từ chối field lạ** khi ObjectMapper cấu hình ignore; phải test runtime thực tế.

## 17. Ma trận kiểm thử bảo mật

Dùng ít nhất **hai tenant**, owners/ACL khác nhau, Spring Security và DB test thực. Đối với job/file cần worker fixture và private object storage test.

| Nhóm | Thử nghiệm | Kỳ vọng |
| --- | --- | --- |
| Search | Không có token/scope | 401/403 |
| Search | Tenant A tìm từ khóa của B | Không rò item, count, facet |
| Search | Query OR, cursor và sort không allowlist | Không bypass scope |
| Search | Được đọc title nhưng không body | Projection đúng |
| Batch | ID đầu được phép, ID sau thuộc tenant B | Không archive item B |
| Batch | Duplicate, >50 item, unknown fields | Reject/dedup theo contract |
| Batch | ACL thu hồi hoặc revision thay đổi giữa check/ghi | Không ghi trái quyền |
| Batch | Atomic lỗi một item | Không partial commit |
| Batch | Partial lỗi một item | Item khác vẫn commit đúng |
| Batch | Retry với cùng Idempotency-Key | Không mutation/audit trùng |
| Job | Export yêu cầu field cấm | Không xuất field |
| Job | Caller mất tenant membership lúc job đang chạy | Job fail/cancel theo policy |
| Job | Đổi jobId/đọc result/cancel của user khác | 403/404, không rò |
| File | Upload vào document khác tenant | Không công bố file |
| File | Fake MIME, quá size, malware | Quarantine/reject |
| File | AttachmentId của parent khác | Không tải được bytes |
| File | Signed URL hết hạn hoặc caller bị revoke | Đúng TTL/chính sách revoke |
| Chung | CDN/cache user A và B | Không trộn response |
| Chung | Lỗi storage/DB | Không lộ signed URL, token, stack trace |

Ví dụ kiểm tra search qua MockMvc:

~~~java
@Test
void searchNeverReturnsOtherTenantDocument() throws Exception {
    mvc.perform(get("/api/v1/documents")
            .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + tokenTenantA))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[*].id",
            not(hasItem(documentTenantB.toString()))));
}
~~~

Cần Hamcrest imports, fixture và DB/authorization thật; **mock service trả list an toàn chưa chứng minh SQL đúng**. Test batch phải assert DB, test job chạy worker và kiểm output, test race dùng barrier/transaction thay vì sleep.

## 18. Bài thực hành: Workspace Documents

**Bối cảnh:** một SaaS có tài liệu đa tenant, ACL theo hành động, revision, attachments và export CSV. Người dùng chỉ được export document hiện còn quyền đọc.

**Bài tập (100 điểm):** **Search (25)**: tenant/ACL trước pagination và count, limit 100. **Batch (25)**: tối đa 50 IDs, atomic hoặc partial rõ, mỗi ID dùng SQL tenant+ACL+revision, idempotency. **Job (25)**: 202/Location, requester scope, worker recheck quyền, owner ACL với status/result/cancel. **Attachment & test (25)**: upload quarantine + scan/quota, download parent+attachment ACL, 12 tests về BOLA, revoke, race, URL ký và cache.

**Hướng giải:** scope ở controller **và SQL**, batch mutation có authorization predicate, worker không dùng service account để xuất ngoài quyền requester, file private chỉ AVAILABLE sau scan. Test hai tenant, quyền bị thu hồi trong khi job chạy, kiểm DB/object storage **ngoài HTTP status**.

## 19. Checklist và tài liệu chuẩn

- [ ] Tenant/principal từ token và membership được xác minh.
- [ ] Search/count/facet scope đúng trước LIMIT/aggregate.
- [ ] Batch từng ID có quyền action/object, CAS, atomicity/idempotency.
- [ ] Job có owner/tenant, worker reauthorization và TTL.
- [ ] Attachment upload private/scan, download kiểm parent và file.
- [ ] Signed URL có scope/TTL và policy thu hồi minh bạch.
- [ ] Cache, audit, quota và lỗi không rò tenant khác.
- [ ] Có tests multi-tenant, race, worker, file, signed URL.

**Ghi nhớ:** authorization phải được thực thi **tại lúc chọn, thay đổi, xuất và tải dữ liệu**, xét **tenant + object + action + field + thời điểm**; annotation ở controller chỉ là một lớp.

**Nguồn:** OWASP API Security Top 10 (BOLA, BOPLA, resource consumption); OWASP Authorization/File Upload Cheat Sheets; RFC 9110, RFC 9457; OpenAPI 3.1; Spring Security MVC/Data/Transactions; tài liệu private storage/presigned URL của provider.
