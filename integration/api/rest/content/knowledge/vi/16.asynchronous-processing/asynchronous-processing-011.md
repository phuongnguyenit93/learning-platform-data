# Ủy quyền truy cập trạng thái và kết quả công việc

> **Module:** `INTEGRATION_API_REST` — **Xử lý bất đồng bộ**. Bài này thiết kế quyền truy cập cho REST API tiếp nhận công việc chạy nền, trả trạng thái qua operation resource và cho tải kết quả khi hoàn thành. Trọng tâm là xác thực, phân quyền theo tenant/người sở hữu, bảo vệ link tải xuống và kiểm thử với Java/Spring.

## 1. Vì sao bất đồng bộ tạo ra thêm bề mặt phân quyền?

Giả sử khách hàng yêu cầu xuất toàn bộ hóa đơn của mình. Server không thể tạo file ngay trong một request nên trả `202 Accepted` và đường dẫn theo dõi:

~~~http
POST /v1/report-jobs HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-A>
Idempotency-Key: b9f4c6b1-1ff6-4c56-a5fb-7a765b491ad0
Content-Type: application/json

{"reportType":"INVOICES","month":"2026-10"}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v1/operations/op_8f7c
Retry-After: 3
Cache-Control: no-store
Content-Type: application/json

{
  "id":"op_8f7c",
  "status":"QUEUED",
  "links":{"self":"/v1/operations/op_8f7c"}
}
~~~

Giả sử người B biết hoặc đoán được `op_8f7c` rồi truy cập `GET /v1/operations/op_8f7c`. Nếu chỉ cần token hợp lệ là nhận được trạng thái, B có thể biết A vừa xuất hóa đơn. Nếu endpoint tải kết quả chỉ kiểm tra `status=SUCCEEDED` rồi trả file, B còn có thể lấy dữ liệu tài chính của A.

**Quy tắc:** operation ID chỉ là định danh, không phải quyền truy cập. **Xác thực** cho biết caller là ai; **phân quyền trên từng object (BOLA/IDOR)** quyết định caller có được xem operation, tải kết quả hoặc yêu cầu hủy **operation cụ thể** hay không.

Ba tài nguyên/hành động cần bảo vệ độc lập:

| Hành động | Câu hỏi cần kiểm tra | Hậu quả nếu thiếu |
|---|---|---|
| `GET /operations/{id}` | Caller được xem **tiến độ và metadata** của job này không? | Rò rỉ sự tồn tại, trạng thái, tên file, lỗi xử lý |
| `GET /operations/{id}/result` | Caller còn quyền đọc **dữ liệu trong kết quả** ở thời điểm tải không? | Tải trái phép báo cáo, dữ liệu cá nhân hoặc bí mật |
| `POST /operations/{id}/cancellations` | Caller được **yêu cầu dừng** công việc này không? | Người khác phá hoại job đang chạy |

Không tự suy ra “xem được trạng thái thì tải được file” hoặc “tạo được job thì có quyền hủy mãi mãi”. Các quyền có thể khác nhau theo vai trò, tenant, thời gian và loại kết quả.

### Kết quả học tập

Sau bài này, người học có thể thiết kế mô hình quyền cho operation/result/cancel; xử lý `401/403/404/410`; phân biệt quyền lúc tạo và lúc đọc; xây API Java/Spring có kiểm tra tenant/owner ở truy vấn và policy; bảo vệ signed download URL; kiểm thử truy cập chéo người dùng, chéo tenant, thay đổi quyền và vòng đời dữ liệu.

## 2. Mô hình tài nguyên và ranh giới tin cậy

~~~mermaid
flowchart LR
    C["Caller: user / service"] -->|"JWT + scope"| API["REST API"]
    API --> P["Authorization policy\ncurrent user, tenant, ACL"]
    P --> O[("Operation store\nowner, tenant, state, resultKey")]
    API --> Q["Queue"]
    Q --> W["Worker identity\nleast privilege"]
    W --> O
    W --> S[("Private result storage")]
    API -->|"authorize then mint short-lived URL"| S
    C -->|"download with scoped URL"| S
~~~

Một operation record tối thiểu có thể chứa:

~~~text
Operation
  publicId             = op_8f7c            # ID công khai ngẫu nhiên, không tuần tự
  tenantId             = tenant_7          # Ranh giới bảo mật
  ownerSubjectId       = user_A            # Chủ thể khởi tạo
  jobType              = INVOICE_EXPORT
  state                = QUEUED|RUNNING|SUCCEEDED|FAILED|CANCELLED
  progress             = 0..100            # Nếu backend có tiến độ đáng tin cậy
  resultObjectKey      = opaque internal key, nullable
  createdAt, expiresAt = timestamps
  policyContext        = phân loại dữ liệu / projectId / scope đã xét
~~~

**Không lưu access token của user để worker dùng lại về sau.** Token có thể hết hạn, bị thu hồi hoặc có quyền quá rộng. Worker xác thực bằng danh tính dịch vụ riêng, chỉ được đọc input và ghi output thuộc job được cấp, kèm kiểm soát phạm vi dữ liệu.

### 2.1. Ai sở hữu job?

Một chính sách cho ứng dụng đa tenant:

- **Owner:** người tạo có quyền xem trạng thái trong tenant của họ, nếu tài khoản vẫn hợp lệ.
- **Delegated reader:** người được cấp quyền cụ thể qua ACL hoặc quyền dự án có thể xem trạng thái; không mặc nhiên tải mọi kết quả.
- **Downloader:** phải có quyền đọc đúng loại dữ liệu/báo cáo **tại thời điểm tải**.
- **Canceller:** chủ sở hữu hoặc người vận hành được phân quyền phù hợp có thể yêu cầu hủy.
- **Worker:** dùng service identity để xử lý; không nhận quyền truy cập API của mọi user.

Quyền thường là hàm của caller, tenant, operation, action và tình trạng hiện tại:

\[
allow = Policy(caller,\ tenant,\ operation,\ action,\ currentState,\ currentEntitlements)
\]

Tham số `tenantId` do client gửi trong query/body **không** phải nguồn tin đáng tin để mở rộng quyền. Tenant thực tế phải được xác minh từ phiên đăng nhập/claims đã được kiểm chứng hoặc hệ thống membership.

### 2.2. Quyền khi tạo so với quyền khi đọc kết quả

Giả sử A được phép xuất báo cáo lúc 09:00, mất quyền lúc 09:05, còn job hoàn thành lúc 09:10. Với dữ liệu nhạy cảm, hãy **recheck ACL/tenant/data entitlement tại thời điểm xem hoặc tải**, thay vì coi quyền lúc enqueue là quyền vĩnh viễn. Mô hình giữ nguyên quyền từ lúc tạo (*authorization snapshot*) chỉ nên áp dụng khi policy cho phép rõ, có thời hạn và audit. Quyền phải bao phủ **toàn bộ nội dung kết quả**, không chỉ metadata job.

## 3. Hợp đồng HTTP cho vòng đời an toàn

### 3.1. Đọc trạng thái

~~~http
GET /v1/operations/op_8f7c HTTP/1.1
Authorization: Bearer <access-token-A>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-store
Content-Type: application/json

{
  "id":"op_8f7c",
  "status":"RUNNING",
  "progressPercent":45,
  "createdAt":"2026-11-18T09:00:00Z",
  "links":{"self":"/v1/operations/op_8f7c"}
}
~~~

`200` ở đây nghĩa là **đọc operation thành công**, không phải job đã thành công. Một job `FAILED` vẫn có thể được đọc bằng `200` với `status:"FAILED"` và mã lỗi nghiệp vụ đã được lọc an toàn. Không trả stack trace, raw SQL, storage key, email/ID của người khác hoặc thông tin secret qua trường `error`.

### 3.2. Khi job hoàn tất

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-store
Content-Type: application/json

{
  "id":"op_8f7c",
  "status":"SUCCEEDED",
  "links":{
    "self":"/v1/operations/op_8f7c",
    "result":"/v1/operations/op_8f7c/result"
  }
}
~~~

**Link kết quả chỉ là hướng dẫn điều hướng.** Endpoint `/result` phải **kiểm tra quyền lại**; không được nghĩ “người gọi đã có link nên đã được cấp phép”. Nếu người xem status không có quyền tải, server có thể **không** đưa `result` vào representation của họ, nhưng việc ẩn link không thay authorization tại endpoint tải.

### 3.3. Đọc kết quả và các lỗi

| Request/kết quả | Status phù hợp | Ý nghĩa |
|---|---|---|
| Tạo job được tiếp nhận | `202 Accepted` + `Location` monitor | Chưa hứa job sẽ thành công |
| GET monitor được phép | `200 OK` | Trả trạng thái hiện tại |
| GET result đã sẵn sàng và được phép | `200 OK` với stream/file, **hoặc `303 See Other`** tới URL tải | Do contract chọn |
| GET result khi job chưa hoàn tất | `409 Conflict` theo **quy ước bài này** | Trạng thái hiện tại chưa thể tải; không tự động retry POST |
| Không có token hợp lệ | `401 Unauthorized` | Cần xác thực, `WWW-Authenticate` khi phù hợp |
| Caller đã xác thực nhưng thiếu quyền | `403 Forbidden` hoặc `404 Not Found` | Chọn chính sách không tiết lộ sự tồn tại |
| Job/result không tồn tại hoặc bị che | `404 Not Found` | Không xác nhận owner của ID lạ |
| Job/result hết hạn và được phép biết điều đó | `410 Gone` tùy chính sách | Nếu không muốn tiết lộ, có thể dùng `404` |
| Không thể hủy vì đã xong | `409 Conflict` | Xung đột vòng đời nghiệp vụ |
| Polling vượt tần suất | `429 Too Many Requests`, có thể kèm `Retry-After` | Backoff có giới hạn |

Với GET monitor `FAILED`, không dùng `500` chỉ vì worker đã thất bại: HTTP request đọc trạng thái vẫn thành công. Nếu bản thân monitor bị lỗi hạ tầng, khi đó `5xx` mới có ý nghĩa.

### 3.4. Quyền hủy là hành động riêng

~~~http
POST /v1/operations/op_8f7c/cancellations HTTP/1.1
Authorization: Bearer <access-token-A>
Content-Type: application/json

{"reason":"USER_REQUEST"}
~~~

Nếu yêu cầu hủy được chấp nhận để xử lý bất đồng bộ, có thể trả `202 Accepted`. Worker có thể đã hoàn tất đúng lúc request hủy tới; **không hứa hủy tức thời**. API kiểm tra quyền hủy và chuyển trạng thái bằng thao tác đồng thời an toàn (CAS/optimistic locking), không chỉ `GET` rồi `UPDATE` rời rạc. Sau đó caller theo dõi trạng thái `CANCELLING/CANCELLED/SUCCEEDED` theo hợp đồng.

## 4. Ngăn BOLA/IDOR và rò rỉ liên tenant

**Phản mẫu:**

~~~java
// Không dùng: mọi người đã đăng nhập đều đọc được mọi job.
@GetMapping("/v1/operations/{id}")
OperationEntity get(@PathVariable String id) {
    return repository.findByPublicId(id).orElseThrow();
}
~~~

Lỗi không biến mất dù `id` là UUID khó đoán. ID có thể xuất hiện trong log, email, lịch sử trình duyệt, URL được chia sẻ hoặc analytics. Hơn nữa, trả trực tiếp entity có thể lộ `resultObjectKey`, `ownerId` và lỗi nội bộ.

**Mẫu an toàn:** dữ liệu phải được lọc theo phạm vi tenant **và** policy trên object:

~~~sql
SELECT public_id, tenant_id, owner_subject_id,
       status, progress_percent, result_object_key
FROM operations
WHERE public_id = :operation_id
  AND tenant_id = :verified_tenant;
~~~

Sau khi lấy row trong tenant được phép, áp dụng quyết định quyền cụ thể như owner hoặc ACL đã được kiểm chứng. Có thể đưa toàn bộ policy vào truy vấn hoặc DB row-level security nếu triển khai đúng; dù chọn cách nào, **không tồn tại nhánh truy vấn vượt quyền khi có filter/cursor hoặc khi dùng service account**.

### 4.1. Không tiết lộ thông tin qua lỗi

Để tránh cho kẻ tấn công phân biệt operation có tồn tại hay không:

- Với ID không tồn tại và ID ngoài tenant, API có thể cùng trả `404`.
- Với ID trong tenant nhưng caller không được đọc, cũng có thể trả `404` theo chính sách không công bố.
- Ghi lý do thật vào **audit log nội bộ**, không lộ owner/tenant/result key qua body.
- Đánh giá response time và cách trả metadata để giảm side channel nếu dữ liệu đặc biệt nhạy cảm.

Chính sách `403` thay vì `404` cũng hợp lý ở hệ quản trị nội bộ, khi caller đã được phép biết tài nguyên tồn tại. Quan trọng là **nhất quán và không lộ thông tin trái quyền**.

### 4.2. Phân quyền xem status, download và cancel

| Caller | Xem status | Tải kết quả | Yêu cầu hủy |
|---|---|---|---|
| Owner trong tenant, vẫn có entitlement | Có | Có nếu được đọc dữ liệu xuất | Có khi trạng thái cho phép |
| Thành viên cùng tenant, không có ACL | Không | Không | Không |
| Delegated viewer có quyền theo dõi | Có | **Không mặc định** | Không |
| Support được giao vụ việc và có permission cụ thể | Theo policy | Chỉ nếu có quyền dữ liệu tương ứng | Theo policy |
| Worker service identity | Qua API nội bộ được giới hạn riêng | Chỉ input/output job được giao | Không tự nhận quyền của owner |
| Người khác tenant | Không | Không | Không |

RBAC (vai trò) cho biết *loại* hành động được phép, ABAC/ACL cho biết **trên operation cụ thể**. Role như `SUPPORT` hoặc scope `reports.read` **không đủ** nếu thiếu ràng buộc tenant và đối tượng.

## 5. File kết quả: bảo vệ lại ở ranh giới storage

Một job được cấp phép có thể tạo tệp CSV/PDF lớn. Hai cách trả kết quả:

**A. Stream qua REST API sau khi authorize:**

~~~http
HTTP/1.1 200 OK
Content-Type: text/csv
Content-Disposition: attachment; filename="invoices-2026-10.csv"
Cache-Control: private, no-store
X-Content-Type-Options: nosniff
~~~

API kiểm soát quyền cho từng lần GET, hỗ trợ range/streaming nếu contract cần; đổi lại, API tiêu tốn băng thông.

**B. Chuyển hướng tới URL tải xuống có thời hạn:**

~~~http
HTTP/1.1 303 See Other
Location: https://download.example.test/objects/opaque?signature=short-lived-token
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Server **chỉ phát URL sau khi kiểm tra quyền tải tại thời điểm yêu cầu**. URL ký có thời hạn là một dạng **bearer capability**: ai có URL có thể tải trong thời hạn hiệu lực mà không cần gửi JWT API tới storage. Do vậy:

1. URL có TTL ngắn, đúng object và đúng operation, giới hạn method (GET) và các thuộc tính khác nếu storage hỗ trợ.
2. Không log URL đầy đủ hoặc đưa vào analytics/email công khai; tránh lộ qua `Referer`, browser history và tracing.
3. Không tự chuyển header `Authorization` từ API origin sang host tải xuống; kiểm soát redirect và HTTPS.
4. Object storage mặc định private; không vì có signed URL mà mở public bucket.
5. Khi quyền bị thu hồi **sau khi đã cấp signed URL**, URL có thể còn hiệu lực đến lúc hết hạn. Nếu yêu cầu thu hồi ngay lập tức, cân nhắc proxy tải có recheck quyền hoặc cơ chế revoke URL/key của nền tảng.

**Không nhận `objectKey` hoặc `filePath` từ client để tải trực tiếp.** API tra cứu result key từ operation đã được authorize và xác minh object thực sự thuộc job/tenant. Việc đặt tiền tố tenant trong bucket giúp quản trị nhưng **không thay** chính sách truy cập.

### 5.1. Vòng đời lưu trữ

Định nghĩa retention (ví dụ 24 giờ sau khi hoàn thành); khi hết hạn, trả `410` nếu được phép công bố hoặc `404` nếu cần che tồn tại. Xóa blob lẫn metadata/khóa theo policy. Với dữ liệu nhạy cảm, dùng mã hóa lưu trữ, HTTPS, audit lượt tải; làm sạch tên file, phòng CSV formula injection và xác minh Content-Type.

## 6. Worker có danh tính riêng, không “mượn” quyền user vô thời hạn

Một worker lấy job từ queue, đọc dữ liệu rồi ghi result. Rủi ro **confused deputy** xảy ra nếu worker có quyền hệ thống rộng, tin nguyên `tenantId`/`objectKey` từ message và vô tình xuất dữ liệu tenant khác.

Quy tắc triển khai:

- Message chứa `operationId`, không chứa JWT/refresh token hoặc quyền tùy ý do client chọn.
- Worker xác thực qua service identity; lấy metadata job từ kho đáng tin với tenant/owner/policy context đã lưu.
- Query lấy dữ liệu theo tenant, scope và loại báo cáo đã được xác nhận. Không dựa vào raw SQL/filter từ message.
- Kiểm tra lại quyền trước khi thực thi khi chính sách yêu cầu; nếu quyền đã bị thu hồi, job có thể dừng với lỗi nghiệp vụ an toàn.
- Result ghi vào vùng private, liên kết với đúng operation; commit trạng thái `SUCCEEDED` chỉ sau khi result thực sự sẵn sàng.
- Queue có thể redeliver: worker dùng idempotent processing/lease/CAS để tránh hai worker ghi hai kết quả mâu thuẫn.

~~~mermaid
sequenceDiagram
    participant U as User A
    participant API as REST API
    participant DB as Operation store
    participant W as Worker
    participant S as Private storage
    U->>API: POST report-jobs (JWT, Idempotency-Key)
    API->>API: Kiểm tra quyền tạo
    API->>DB: Lưu job owner/tenant/params an toàn
    API-->>U: 202 + Location monitor
    W->>DB: Nhận opId qua service identity
    W->>DB: Đọc metadata & scope của job
    W->>S: Ghi kết quả vào vùng private
    W->>DB: Đánh dấu SUCCEEDED + resultKey
    U->>API: GET /operations/{id}/result
    API->>DB: Scope theo tenant + recheck ACL dữ liệu
    API-->>U: 303 short-lived download URL
    U->>S: GET URL tải (không gửi JWT API)
    S-->>U: File được ký quyền và có hạn
~~~

Tài nguyên trong message/DB phải có ranh giới giao dịch để không rơi vào tình huống HTTP trả `202` nhưng queue mất công việc. Có thể dùng transactional outbox hoặc một cơ chế tiếp nhận bền vững tương đương.

## 7. Java/Spring: kiểm tra quyền trên resource, không chỉ endpoint

Ví dụ Spring Boot/Spring Security dưới đây minh họa cấu trúc chính; các interface repository, ACL và signer cần được hiện thực trong ứng dụng. Giả định **Spring OAuth2 Resource Server** đã xác minh JWT (issuer, audience, thời hạn, chữ ký) và tenant claim là đáng tin; với mô hình nhiều tenant cho một tài khoản, còn phải kiểm tra membership của tenant đang hoạt động.

### 7.1. Controller: scope chỉ là cửa đầu

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import java.net.URI;

@RestController
@RequestMapping("/v1/operations")
class OperationController {
    private final OperationAccessService operations;

    OperationController(OperationAccessService operations) {
        this.operations = operations;
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_reports.status')")
    ResponseEntity<OperationResponse> status(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        OperationResponse response =
            operations.visibleStatus(Caller.fromVerifiedJwt(jwt), id);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(response);
    }

    @GetMapping("/{id}/result")
    @PreAuthorize("hasAuthority('SCOPE_reports.download')")
    ResponseEntity<Void> result(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        URI url = operations.authorizedDownloadUrl(
            Caller.fromVerifiedJwt(jwt), id);
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
            .location(url)
            .cacheControl(CacheControl.noStore())
            .build();
    }
}

record Caller(String subject, String tenantId) {
    static Caller fromVerifiedJwt(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("Missing tenant claim");
        }
        return new Caller(jwt.getSubject(), tenant);
    }
}

record OperationResponse(
    String id, String status, Integer progressPercent,
    java.util.Map<String, String> links
) {}
~~~

**Không** coi `SCOPE_reports.status` là quyền đọc mọi job: nó chỉ kiểm tra quyền thao tác tổng quát. `OperationAccessService` tiếp tục kiểm tra **operation cụ thể** theo tenant, owner và ACL. Lỗi claim không hợp lệ nên được xử lý như lỗi danh tính (`401/403` tùy chính sách), không để `IllegalArgumentException` rò thành `500` hoặc log lộ claims.

### 7.2. Service: scope theo tenant và recheck entitlement

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
class OperationAccessService {
    private final OperationRepository repository;
    private final OperationAcl acl;
    private final PrivateDownloadSigner downloads;

    OperationAccessService(OperationRepository repository,
            OperationAcl acl, PrivateDownloadSigner downloads) {
        this.repository = repository;
        this.acl = acl;
        this.downloads = downloads;
    }

    @Transactional(readOnly = true)
    OperationResponse visibleStatus(Caller caller, String publicId) {
        OperationEntity op = visibleOperation(caller, publicId);
        if (!acl.mayReadStatus(caller, op)) {
            throw new HiddenResourceException();
        }
        Map<String, String> links = new LinkedHashMap<>();
        links.put("self", "/v1/operations/" + op.publicId());
        if (op.status() == JobState.SUCCEEDED
                && acl.mayDownloadResult(caller, op)) {
            links.put("result",
                "/v1/operations/" + op.publicId() + "/result");
        }
        return new OperationResponse(
            op.publicId(), op.status().name(),
            op.progressPercent(), links);
    }

    @Transactional(readOnly = true)
    URI authorizedDownloadUrl(Caller caller, String publicId) {
        OperationEntity op = visibleOperation(caller, publicId);
        // Download là quyền riêng, phải recheck khi GET /result.
        if (!acl.mayDownloadResult(caller, op)) {
            throw new HiddenResourceException();
        }
        if (op.expiresAt().isBefore(Instant.now())) {
            throw new ResultExpiredException();
        }
        if (op.status() != JobState.SUCCEEDED) {
            throw new ResultNotReadyException();
        }
        if (op.resultObjectKey() == null) {
            throw new IllegalStateException("Missing completed result");
        }
        // Signer chỉ ký objectKey lấy từ DB thuộc operation;
        // không nhận key/path từ client.
        return downloads.signGet(op.resultObjectKey(),
            Duration.ofMinutes(2));
    }

    private OperationEntity visibleOperation(
            Caller caller, String publicId) {
        return repository
            .findByPublicIdAndTenantId(publicId, caller.tenantId())
            .orElseThrow(HiddenResourceException::new);
    }
}

interface OperationRepository {
    java.util.Optional<OperationEntity> findByPublicIdAndTenantId(
        String publicId, String tenantId);
}
interface OperationAcl {
    boolean mayReadStatus(Caller caller, OperationEntity op);
    boolean mayDownloadResult(Caller caller, OperationEntity op);
}
interface PrivateDownloadSigner {
    URI signGet(String trustedObjectKey, Duration ttl);
}
enum JobState { QUEUED, RUNNING, CANCELLING,
                CANCELLED, SUCCEEDED, FAILED }
record OperationEntity(
    String publicId, String tenantId, String ownerSubjectId,
    JobState status, Integer progressPercent,
    String resultObjectKey, Instant expiresAt
) {}
~~~

Các exception trong snippet là **loại lỗi ứng dụng cần định nghĩa** và ánh xạ ra Problem Details. `findByPublicIdAndTenantId` bảo vệ ranh giới tenant nhưng **chưa đủ** cho nhiều người trong cùng tenant; ACL phải kiểm tra owner/delegation và quyền đọc dữ liệu hiện tại. Nếu signed URL có rủi ro thu hồi quyền, có thể dùng stream/proxy thay vì redirect.

Đặc biệt tránh kiểu `findById(id)` rồi `if (op.owner.equals(...))` trong một số code path nhưng quên bước kiểm tra ở endpoint khác. Tập trung policy ở service và bao phủ **status/result/cancel** bằng integration tests. Các thay đổi trạng thái/ACL cạnh tranh cần có cơ chế transaction hoặc version check phù hợp; kiểm tra ở GET không thay quyền kiểm tra tại endpoint ghi.

### 7.3. Ánh xạ lỗi bảo mật có kiểm soát

`@RestControllerAdvice` có thể ánh xạ `HiddenResourceException` → `404`, `ResultNotReadyException` → `409` và `ResultExpiredException` → `410` nếu được phép công bố expiry; `401/403` do Spring Security xử lý theo cấu hình. Dùng `application/problem+json` với `code` ổn định, không lộ `resultObjectKey`, SQL, bucket hoặc chi tiết quyền; lưu lý do nội bộ trong audit log có kiểm soát.

## 8. OpenAPI 3.1: hợp đồng quyền và response

Ví dụ rút gọn; danh tính và phép kiểm tra ACL được thực thi ở server, không tự xuất hiện chỉ vì có `security` trong OpenAPI:

~~~yaml
openapi: 3.1.0
info:
  title: Async Report API
  version: 1.0.0
paths:
  /v1/report-jobs:
    post:
      summary: Tạo job xuất báo cáo theo quyền hiện tại
      security: [{bearerAuth: [reports.create]}]
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string}
      responses:
        '202':
          description: Đã tiếp nhận, chưa hoàn thành
          headers:
            Location:
              required: true
              schema: {type: string, format: uri}
        '401': {description: Chưa xác thực}
        '403': {description: Không có quyền tạo}
  /v1/operations/{id}:
    get:
      summary: Xem trạng thái job trong phạm vi được phép
      security: [{bearerAuth: [reports.status]}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Operation representation
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '401': {description: Chưa xác thực}
        '403': {description: Không có quyền theo policy}
        '404': {description: Không tìm thấy hoặc không công bố}
        '429': {description: Polling vượt rate limit}
  /v1/operations/{id}/result:
    get:
      summary: Lấy kết quả sau khi kiểm tra quyền tải hiện tại
      security: [{bearerAuth: [reports.download]}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '303':
          description: URL tải riêng tư, thời hạn ngắn
          headers:
            Location:
              required: true
              schema: {type: string, format: uri}
        '401': {description: Chưa xác thực}
        '404': {description: Không tìm thấy hoặc không công bố}
        '409': {description: Job chưa sẵn sàng}
        '410': {description: Result đã hết hạn}
components:
  securitySchemes:
    bearerAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.test/oauth/token
          scopes:
            reports.create: Tạo job
            reports.status: Xem trạng thái được phép
            reports.download: Tải kết quả được phép
  schemas:
    Operation:
      type: object
      required: [id, status, links]
      properties:
        id: {type: string}
        status:
          type: string
          enum: [QUEUED, RUNNING, CANCELLING,
                 CANCELLED, SUCCEEDED, FAILED]
        progressPercent:
          type: [integer, 'null']
          minimum: 0
          maximum: 100
        links:
          type: object
          additionalProperties: {type: string}
~~~

`clientCredentials` chỉ là **cách lấy token của một kiểu client** được minh họa; ứng dụng người dùng cuối thường có authorization-code/PKCE hoặc cơ chế phù hợp khác. Dù scope đã khai báo, **không thay thế ACL/ABAC trên operation cụ thể**. Khi endpoint GET result hỗ trợ `200` stream thay cho `303`, bổ sung mã và media type tương ứng vào hợp đồng.

## 9. Kiểm thử: tập trung các đường đi vượt quyền

| Kịch bản | Kỳ vọng |
|---|---|
| A tạo job trong tenant T | `202`, Location monitor của A |
| A đọc status của mình | `200`, không lộ storage key |
| B cùng tenant, không được delegate, đọc status A | `404` theo chính sách che tồn tại |
| C ngoài tenant biết operation ID | `404` ở cả status, result, cancel |
| Người có quyền xem status nhưng không có quyền tải | `200` status, không có link result; GET result bị từ chối |
| A bị thu hồi quyền dữ liệu sau khi tạo job | GET result bị từ chối dù job đã SUCCEEDED |
| Job RUNNING, caller đủ quyền tải | GET result `409 RESULT_NOT_READY` |
| Job FAILED | GET monitor `200` + trạng thái FAILED; lỗi đã làm sạch |
| Result hết hạn | `404`/`410` đúng chính sách, file private không còn tải được |
| A gọi cancel khi job đang chạy | Chỉ cho phép nếu đúng quyền; cập nhật state có kiểm soát |
| Worker redeliver cùng job | Không ghi đè result của tenant khác, không nhân đôi tác động |
| Signed URL bị lộ hoặc hết hạn | TTL/phạm vi giới hạn; kiểm chứng hành vi revoke theo thiết kế |
| Client theo redirect sang storage | Không chuyển bearer token API qua origin khác |
| Kẻ tấn công gửi `objectKey` giả | API bỏ qua; chỉ dùng key được tra từ operation đã authorize |

Ví dụ assertion cho Spring MockMvc, với hai JWT test identity và fixture trong DB:

~~~java
// Giả định đã có security test setup và fixture op_8f7c của user_A.
mockMvc.perform(get("/v1/operations/op_8f7c")
        .with(jwt().jwt(j -> j.subject("user_B")
            .claim("tenant_id", "tenant_7"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_reports.status"))))
    .andExpect(status().isNotFound());

mockMvc.perform(get("/v1/operations/op_8f7c/result")
        .with(jwt().jwt(j -> j.subject("user_A")
            .claim("tenant_id", "tenant_7"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_reports.download"))))
    .andExpect(status().isSeeOther())
    .andExpect(header().exists("Location"));
~~~

Đây là **assertion minh họa**, chưa phải test class độc lập: phải import Spring Security Test/MockMvc, bật method security, dựng fixture `SUCCEEDED`, mock signer và bảo đảm ACL trả quyền đúng. Test quan trọng nhất là **integration test với DB thật**: đổi owner/tenant hoặc thu hồi permission giữa lúc enqueue và lúc tải, xác nhận không nhận file; kiểm tra mọi endpoint có cùng chính sách. Với signed URL, kiểm thử cả thời gian sống và khả năng chia sẻ URL trong thời hạn.

## 10. Bài thực hành

**Đề bài:** Một API xuất bảng lương trả `202 Location: /operations/op_42`. Nhân viên X tạo job cho phòng ban A. Nhân viên Y cùng công ty có quyền xem tiến độ, nhưng không có quyền xem lương. Sau đó X chuyển sang phòng ban B, job hoàn tất và tạo file CSV.

Hãy thiết kế và giải thích: (1) bảng quyền **status/result/cancel** cho X, Y và quản trị được ủy quyền; (2) cách tenant, department và quyền hiện tại được kiểm tra ở từng GET; (3) response `200` monitor khi `RUNNING`/`SUCCEEDED`, `409` result chưa sẵn sàng và `404` cho truy cập chéo tenant; (4) hai cách tải file qua API stream hoặc `303` signed URL, rủi ro khi X bị thu hồi quyền; (5) ít nhất sáu test âm và một test hủy cạnh tranh với worker.

**Gợi ý:** Với dữ liệu bảng lương, ưu tiên recheck quyền phòng ban **ngay lúc tải**, không chỉ lúc tạo. Y có thể được thấy tiến độ nếu ACL cho phép nhưng không được thấy đường dẫn tải hoặc nhận file. Signed URL đã phát có thể còn hiệu lực đến expiry, nên nếu cần thu hồi ngay lập tức phải thiết kế cơ chế khác. Không cho worker dùng identity của X đã hết hạn để vượt qua chính sách.

## 11. Ghi nhớ

**Ghi nhớ:** `202 Accepted` và `Location` chỉ cho client biết công việc đã được nhận và nơi theo dõi, **không phải giấy phép đọc mọi trạng thái hoặc kết quả**. Quyền phải gắn với **chủ thể hiện tại, tenant, object và hành động**, được kiểm tra ở mọi lần truy cập; bảo mật chỉ hoàn chỉnh khi cả REST API, worker và storage cùng giữ đúng ranh giới đó.
