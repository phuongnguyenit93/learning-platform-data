# Phân biệt quyền đọc, tạo, sửa, xóa, duyệt và xuất dữ liệu trong Spring Security Authorization

## 1. Mục tiêu

Trong hệ thống dữ liệu doanh nghiệp, **một người được nhìn thấy bản ghi không có nghĩa họ được tạo, sửa, xóa, duyệt hoặc xuất bản ghi đó**. Sáu hành động có ảnh hưởng nghiệp vụ, rủi ro và đối tượng kiểm soát khác nhau. Nếu gộp tất cả vào một quyền `DATA_ACCESS` hoặc dựa duy nhất vào `ROLE_USER`, ứng dụng có thể vô tình cho phép thay đổi dữ liệu trái thẩm quyền, tự duyệt giao dịch hoặc trích xuất số lượng lớn thông tin.

Bài học thuộc nhóm **Quyền trên dữ liệu** của Spring Security Authorization. Sau khi học, bạn có thể:

1. Định nghĩa rõ **READ, CREATE, UPDATE, DELETE, APPROVE, EXPORT** và phân biệt chúng với HTTP verb.
2. Thiết kế quyền theo **hành động + loại tài nguyên + đối tượng cụ thể + tenant + trạng thái + trường dữ liệu**.
3. Dùng Spring Security Method Security (`@EnableMethodSecurity`, `@PreAuthorize`) kết hợp một policy bean để kiểm soát từng thao tác.
4. Áp dụng *least privilege*, *deny by default* và *separation of duties* (người tạo không tự duyệt).
5. Kiểm soát xuất dữ liệu như một quyền riêng, có giới hạn phạm vi, trường được xuất, định dạng, audit và khả năng thu hồi.
6. Viết kiểm thử Java 17+ kiểm tra cả đường cho phép và đường từ chối, đặc biệt chứng minh **thân phương thức không chạy khi before authorization từ chối**.
7. Nhận diện những lỗi như IDOR/BOLA, mass assignment, lẫn quyền READ với EXPORT, duyệt sai trạng thái, lọc dữ liệu sau phân trang và TOCTOU.

**Ngữ cảnh minh họa:** một hệ thống `Document` đa tenant, có chủ sở hữu, nội dung, nhãn nhạy cảm và trạng thái `DRAFT → SUBMITTED → APPROVED`. Java 17+, Spring Boot BOM 3.5.0, Spring Security 6.5.x, JUnit 5; đây là **một chính sách ví dụ**, không phải Spring Security tự định nghĩa sẵn sáu quyền này.

## 2. Sáu thao tác không tương đương nhau

| Thao tác | Câu hỏi chính sách | Điều kiện minh họa | Tác động/rủi ro |
| --- | --- | --- | --- |
| **READ — Đọc** | Ai được xem **bản ghi và các trường nào**? | Có `DOC_READ`; đúng tenant; tài liệu nhạy cảm cần điều kiện bổ sung | Lộ nội dung/metadata của người khác |
| **CREATE — Tạo** | Ai được tạo bản ghi **trong phạm vi nào**? | Có `DOC_CREATE`; tenant được phép; owner gán từ identity tin cậy | Tạo dữ liệu sai tenant, giả mạo owner |
| **UPDATE — Sửa** | Ai được sửa **bản ghi nào, trường nào, khi nào**? | Có `DOC_UPDATE`; là owner; bản ghi đang DRAFT; chỉ sửa content hợp lệ | Thay quyền, trạng thái, giá trị nhạy cảm trái phép |
| **DELETE — Xóa** | Ai được xóa, theo chế độ nào, với ràng buộc lưu giữ nào? | Có `DOC_DELETE`; là owner; chỉ DRAFT; kiểm tra retention | Mất dữ liệu, phá bằng chứng/audit |
| **APPROVE — Duyệt** | Ai được chuyển trạng thái **SUBMITTED → APPROVED**? | Có `DOC_APPROVE`; người duyệt khác người tạo; đúng tenant | Tự duyệt, vượt kiểm soát 2 người |
| **EXPORT — Xuất** | Ai được đưa dữ liệu **ra khỏi phạm vi xem thông thường**? | Có `DOC_EXPORT` **và** quyền đọc các dòng được xuất; chỉ dữ liệu đã duyệt, cho phép xuất | Trích xuất hàng loạt PII, rò rỉ file, tải dữ liệu nhạy cảm |

Tên `DOC_*` là **authority do ứng dụng tự quy ước**. Trong Spring Security, `hasAuthority('DOC_READ')` so chính xác với authority tên `DOC_READ`; nó không tự suy ra `DOC_EXPORT`. Nếu sử dụng `hasRole('REVIEWER')`, mặc định thường tìm authority `ROLE_REVIEWER`, không phải mọi quyền chi tiết nói trên.

### 2.1. Quyền không tự suy ra theo chiều “cao hơn”

Các kết luận sau **không an toàn nếu không được chính sách tuyên bố rõ**:

- Có `READ` không có nghĩa có `EXPORT`; xem một bản ghi trên UI khác với trích xuất 10.000 bản ghi thành file.
- Có `CREATE` không có nghĩa có `UPDATE` trên mọi bản ghi cùng loại, cũng không có nghĩa được gửi owner/tenant tùy ý.
- Có `UPDATE` không có nghĩa được đổi trạng thái `APPROVED`; duyệt phải là hành động độc lập.
- Có `APPROVE` không có nghĩa được tự duyệt tài liệu mình gửi.
- Có `DELETE` không mặc nhiên cho phép xóa tài liệu đã duyệt hoặc xóa vĩnh viễn khi đang có yêu cầu retention.
- Có `ROLE_ADMIN` cũng không nên được biến thành “mọi thao tác đều allow” nếu hệ thống yêu cầu phân tách nhiệm vụ và audit.
- Có `EXPORT` mà thiếu `READ` không nên được phép xuất nội dung của bản ghi mình vốn không được xem.

Có thể định nghĩa **role → bộ authority** bằng RBAC, nhưng quyền hiệu lực cuối cùng vẫn nên kết hợp ràng buộc ở cấp đối tượng, tenant, trạng thái và trường dữ liệu.

## 3. Chính sách phải trả lời sáu chiều, không chỉ một role

Một quyết định data authorization thường được biểu diễn theo ý tưởng:

```text
ALLOW =
    identity hợp lệ
    AND có quyền thực hiện ACTION
    AND thuộc phạm vi tenant / tổ chức
    AND được thao tác trên RESOURCE cụ thể
    AND trạng thái workflow cho phép ACTION
    AND tập trường / tập dữ liệu được phép
    AND không vi phạm điều kiện nghiệp vụ khác
```

Đây là mô hình **minh họa logic**, không phải cú pháp SpEL bắt buộc. Một chính sách thực tế có thể có nhiều điều kiện phụ thuộc hành động.

| Chiều | Câu hỏi cần kiểm tra | Lỗi khi bỏ qua |
| --- | --- | --- |
| Subject | Ai đang gọi? Người dùng, service account, job? | Tin username/owner do request tự khai |
| Action | READ hay EXPORT? UPDATE hay APPROVE? | Cấp nhầm chức năng |
| Resource | ID nào, object có tồn tại không? | Đổi ID để đọc/sửa tài nguyên khác |
| Tenant/scope | Record có thuộc phạm vi được phép không? | Truy cập chéo khách hàng |
| Workflow | DRAFT, SUBMITTED, APPROVED, ARCHIVED? | Sửa/xóa sau duyệt, duyệt sai trạng thái |
| Fields/volume/destination | Trường nào, bao nhiêu bản ghi, file gửi tới đâu? | Lộ PII, mass assignment, xuất ngoài phạm vi |

**Ba lớp kiểm soát thường đi cùng nhau:**

1. **Function-level:** user có được dùng chức năng `exportReports` hoặc `approveDocument` không?
2. **Object-level:** user có quyền trên `Document#123` trong tenant tương ứng không?
3. **Property-level:** ngay cả khi được READ, các trường `salary`, `nationalId`, `internalNote` có được lộ ra không?

OWASP phân biệt các rủi ro tương ứng là **API5 Broken Function Level Authorization**, **API1 Broken Object Level Authorization** và **API3 Broken Object Property Level Authorization**. Một API hợp lệ về chức năng vẫn có thể sai ở cấp object hoặc trường.

## 4. Đọc dữ liệu — READ

Đọc bao gồm xem chi tiết, xem danh sách, xem metadata, truy vấn tổng hợp hoặc tải bản xem trước. Đây là **quyền truy cập thông tin**, không phải giấy phép thay đổi hay xuất hàng loạt.

Ví dụ:

- Alice có `DOC_READ` trên tenant A: đọc tài liệu public của tenant A.
- Alice không có quyền đọc tenant B: đổi `GET /documents/123` thành ID thuộc tenant B phải bị từ chối (hoặc trả 404 theo chính sách không tiết lộ tồn tại).
- Alice có `DOC_READ` nhưng không có `DOC_SENSITIVE_READ`: không được đọc trường/văn bản thuộc tài liệu `sensitive=true` của người khác.
- Trường nhạy cảm có thể yêu cầu DTO riêng hoặc redaction ngay cả khi phần metadata công khai được phép đọc.

**Hãy áp dụng authorization trước khi trả nội dung.** `@PreAuthorize` có thể dùng object ID để kiểm tra qua policy/repository đáng tin. `@PostAuthorize` có thể kiểm tra `returnObject`, nhưng method đã thực thi trước khi đánh giá; không sử dụng nó như lời bảo đảm rằng dữ liệu chưa từng được truy vấn, log hoặc gây side effect.

### 4.1. Đọc danh sách và phân trang

Một điểm dễ bỏ sót là service `listDocuments(pageable)`:

- Chỉ lọc quyền ở frontend (ẩn dòng) **không bảo vệ API**.
- `@PostFilter` sau khi load một page có thể tạo page thiếu bản ghi và sai số lượng tổng.
- Với danh sách lớn, ưu tiên **WHERE tenant_id = ... AND policy-condition ...** ở repository/query hoặc mô hình row-level security được thiết kế rõ, rồi chỉ trả DTO/field được phép.
- Khi truy vấn nhiều tài nguyên, kiểm tra việc join, search, count, aggregate hoặc autocomplete có làm lộ dữ liệu người dùng không được đọc không.

Đừng cho phép đổi `sort`, filter, GraphQL selection hoặc ID trong query để vượt kiểm soát tài nguyên.

## 5. Tạo dữ liệu — CREATE

Ở CREATE, **đối tượng chưa tồn tại** nên không thể chỉ kiểm tra ACE của chính bản ghi mới. Điều kiện thường dựa trên scope nơi tạo: tenant, project, folder, quota, loại tài liệu và quyền tạo loại tương ứng.

```text
POST /tenants/TENANT_A/documents
   |
   +--> principal hiện tại có DOC_CREATE?
   +--> principal được tạo trong TENANT_A?
   +--> loại tài liệu và trạng thái ban đầu được phép?
   +--> payload chỉ chứa những trường có thể khai báo?
   |
   +--> server gán owner = authentication.name
   +--> server gán status = DRAFT
```

**Không tin `tenantId`, `ownerId`, `approved`, `createdBy`, `role` hay `aclEntries` lấy từ JSON** như những trường có thể tự thiết lập quyền. Dùng DTO dạng allowlist chỉ gồm các trường user được nhập, sau đó gán owner, tenant đã xác minh, createdAt và trạng thái tại server.

Trong hệ thống ACL, CREATE có thể cần thêm bước tạo ACL và cấp ACE ban đầu. Hãy định nghĩa transaction/lifecycle rõ: tạo domain object thành công nhưng không có ACL, hoặc ngược lại, có thể gây quyền không nhất quán.

## 6. Sửa dữ liệu — UPDATE

Sửa cần đồng thời kiểm tra **quyền UPDATE** và **trường nào được sửa**. Không nên dùng `PUT /documents/{id}` rồi bind toàn bộ entity từ request vào database.

Ví dụ một tác giả được chỉnh `text` của tài liệu DRAFT, nhưng không được chỉnh `owner`, `tenant`, `approvedBy`, `status` hoặc `sensitive` qua cùng endpoint. Nếu payload được merge tự động vào entity, attacker có thể gửi thêm `"status": "APPROVED"` để vượt quy trình duyệt — một dạng *mass assignment*.

Chính sách minh họa:

```text
canUpdate(actor, doc)
  = actor có DOC_UPDATE
    AND doc.tenant == tenant(actor)
    AND doc.owner == actor.username
    AND doc.status == DRAFT
```

Trong sản phẩm thật, kiểm tra thêm version/optimistic locking để tránh người dùng sửa một bản ghi đã được người khác duyệt **sau lúc check nhưng trước lúc ghi**. Update API nên biểu diễn rõ **operation và field whitelist**, không chấp nhận “sửa mọi thứ” vì có một quyền rộng.

## 7. Xóa dữ liệu — DELETE

DELETE thường mang rủi ro lớn hơn UPDATE: có thể xóa vĩnh viễn, soft delete, archive hoặc đặt vào queue purge. Phải làm rõ:

- **Ai được xóa?** Tác giả, quản trị viên dữ liệu hay người được ủy quyền.
- **Xóa khi nào?** Có cho xóa DRAFT không? APPROVED có bắt buộc quy trình thu hồi/huỷ riêng không?
- **Xóa theo kiểu gì?** Soft delete, tombstone, hard delete hoặc retention purge.
- **Tác động phụ?** ACL, file đính kèm, search index, downstream event, audit log, backup.
- **Khôi phục có cần quyền riêng?** RESTORE không mặc nhiên được cấp bởi DELETE.

Trong ví dụ Java, DELETE chỉ cho phép **chủ sở hữu xóa DRAFT** để thể hiện nguyên tắc. Ví dụ xóa bản ghi khỏi in-memory map, không mô phỏng toàn bộ soft delete/audit/retention. Production cần thêm transaction, audit, chính sách lưu trữ và bảo vệ trước race condition.

Đừng suy quyền từ HTTP `DELETE`: tên HTTP method là một tín hiệu endpoint, không thay cho quyền nghiệp vụ. Một endpoint `POST /documents/{id}/remove` cũng phải bị kiểm tra DELETE tương đương.

## 8. Duyệt dữ liệu — APPROVE

APPROVE là **chuyển trạng thái nghiệp vụ** sau khi kiểm tra điều kiện; khác hoàn toàn với sửa nội dung. Ví dụ:

```text
DRAFT ---submit---> SUBMITTED ---approve---> APPROVED
  ^                    |
  |                    +---reject---> REJECTED
  |
  +-------- revise <---+
```

Một quy trình có thể có nhiều mức duyệt, maker-checker, chữ ký số hoặc xác minh số tiền. Ví dụ đơn giản ở bài chỉ duyệt `SUBMITTED → APPROVED`.

Chính sách tối thiểu minh họa:

```text
canApprove(actor, doc)
  = actor có DOC_APPROVE
    AND cùng tenant
    AND doc.status == SUBMITTED
    AND doc.owner != actor.username
```

Điều cuối là **separation of duties (SoD)**: người lập không được tự duyệt bản ghi của mình, kể cả khi về mặt authority họ có cả DOC_UPDATE và DOC_APPROVE. NIST mô tả SoD như cơ chế ngăn một người có đủ đặc quyền để tự thực hiện và hợp thức hóa toàn bộ một thao tác nhạy cảm.

Cần kiểm tra thêm trong hệ thống thực:

- Người duyệt không phải người đề xuất, hoặc không nằm trong tập actor bị xung đột lợi ích.
- Bản ghi chưa bị duyệt hoặc từ chối; lần duyệt lặp phải có quy tắc idempotency rõ.
- Các điều kiện validate nghiệp vụ đã đạt; phiên bản nội dung không thay đổi kể từ khi gửi duyệt.
- Ghi `approvedBy`, `approvedAt`, version và audit; gửi event **sau commit** khi cần.
- Quy trình `REJECT`, `REVOKE_APPROVAL`, `PUBLISH` có thể là **quyền độc lập** — không suy ra tất cả từ APPROVE.

Nếu chỉ có `@PreAuthorize("hasAuthority('DOC_APPROVE')")` mà không kiểm tra owner/status, bạn chưa thực hiện đủ quy tắc duyệt.

## 9. Xuất dữ liệu — EXPORT

**EXPORT là một capability riêng, không phải biệt danh của READ.** Người được mở một bản ghi trên màn hình chưa chắc được tải CSV/Excel/JSON/PDF chứa hàng trăm hoặc hàng nghìn bản ghi, đặc biệt khi có PII/financial/health data hoặc thông tin khách hàng khác.

Một yêu cầu export phải kiểm tra **hai tầng**:

1. **Quyền gọi chức năng:** có `DOC_EXPORT` không? Chính sách có yêu cầu xác thực lại, MFA hay phê duyệt export không?
2. **Quyền đối với từng dữ liệu được xuất:** có READ trên từng dòng, từng tenant và từng trường được đưa vào file không?

Ví dụ policy mẫu trong Java:

```text
canExport(actor, doc)
  = actor có DOC_EXPORT
    AND canRead(actor, doc)
    AND doc.status == APPROVED
    AND doc.sensitive == false
```

Đây là một **chính sách minh họa thận trọng**: ngay cả user có `DOC_SENSITIVE_READ` vẫn không được export tài liệu nhạy cảm. Tổ chức có thể thêm một permission `DOC_SENSITIVE_EXPORT` và bước phê duyệt/đánh giá riêng, nhưng phải định nghĩa và kiểm thử rõ, không để hệ thống “kế thừa” từ READ.

### 9.1. Ranh giới phải kiểm tra khi export

| Ranh giới | Cần kiểm tra |
| --- | --- |
| Request | Người gọi, tenant, lý do, loại export, quyền riêng, tốc độ/tần suất |
| Query | Chỉ dòng được phép READ, scope tenant, không trả cả bảng rồi lọc phía client |
| Field | Explicit allowlist cột; không vô tình xuất `passwordHash`, `internalNote`, PII |
| Volume | Giới hạn số dòng, kích thước file, số job/giờ, timeout |
| Format | CSV/Excel injection, encoding, escaping, công thức và metadata |
| Delivery | Download URL có expiry, quyền sở hữu job, file encryption, bucket access |
| Audit | Ai xuất, lúc nào, dữ liệu/phạm vi nào, policy version, mục đích |
| Lifecycle | Thời gian lưu file, xóa file, thu hồi link, xử lý export job đang chạy |

**CSV formula injection:** nếu nội dung người dùng được đưa vào cột CSV, spreadsheet có thể diễn giải ô bắt đầu bằng `=`, `+`, `-`, `@` như công thức trong một số ứng dụng. Cần xử lý định dạng/escape theo quy tắc và phần mềm đọc đích; không nghĩ chỉ đặt dấu ngoặc kép quanh CSV cell đã xử lý mọi trường hợp.

Ví dụ Java bên dưới cố ý xuất **ba trường do hệ thống kiểm soát** (`id,tenant,state`), không xuất `text`; nó minh họa quyền và *data minimization*, **không phải** thư viện CSV production cho mọi nội dung không tin cậy.

### 9.2. Export bất đồng bộ

Nếu tạo job để xuất file sau vài phút, kiểm tra quyền **lúc submit job** thôi có thể chưa đủ: trong khi chờ, user có thể bị thu hồi quyền, bản ghi đổi tenant hoặc bị đánh dấu nhạy cảm. Thiết kế cần chính sách kiểm tra lại ở lúc xử lý và/hoặc lúc người dùng tải file — theo yêu cầu bảo mật — cùng ownership của job, expiry và audit. Không để link của user A truy cập được bởi user B chỉ vì đoán job ID.

## 10. Ma trận quyền và trạng thái minh họa

Giả định tenant A có tài liệu:

- `#1`: owner Alice, `DRAFT`, public.
- `#2`: owner Alice, `SUBMITTED`, public.
- `#4`: owner Bob, `APPROVED`, public.
- `#5`: owner Bob, `APPROVED`, **sensitive**.
- `#6`: owner Outsider, tenant B, `APPROVED`.
- `#7`: owner Bob, `DRAFT`, public.

Với các authority phù hợp, kết quả:

| Yêu cầu | Kết quả | Vì sao? |
| --- | --- | --- |
| Alice READ #4 có DOC_READ | Allow | Cùng tenant, không nhạy cảm |
| Alice READ #6 có DOC_READ | Deny | Chéo tenant |
| Alice READ #5 chỉ có DOC_READ | Deny | Nhạy cảm, không phải owner/không có quyền bổ sung |
| Alice CREATE tenant A có DOC_CREATE | Allow | Đúng scope, server gán owner Alice |
| Alice CREATE tenant B có DOC_CREATE | Deny | Không được tạo ngoài tenant |
| Alice UPDATE #1 có DOC_UPDATE | Allow | Bản nháp của chính Alice |
| Alice UPDATE #7 có DOC_UPDATE | Deny | Bản nháp thuộc Bob |
| Alice UPDATE #2 có DOC_UPDATE | Deny | Đã SUBMITTED |
| Alice DELETE #1 có DOC_DELETE | Allow | Đúng chủ, DRAFT |
| Bob DELETE #4 có DOC_DELETE | Deny | APPROVED, cần workflow khác |
| Manager APPROVE #2 có DOC_APPROVE | Allow | SUBMITTED, khác người tạo |
| Alice APPROVE #2 có DOC_APPROVE | Deny | Tự duyệt |
| Alice EXPORT #4 có READ + EXPORT | Allow | Public, APPROVED, cùng tenant |
| Alice EXPORT #4 chỉ có READ | Deny | Thiếu EXPORT |
| Alice EXPORT #5 có READ + SENSITIVE_READ + EXPORT | Deny | Ví dụ cấm xuất nhạy cảm |
| Alice EXPORT #1 có READ + EXPORT | Deny | DRAFT |

Đây là **ma trận thiết kế để học**, không phải mặc định của Spring. Cần để các quy tắc này ở một policy được test và dùng thống nhất trong controller, service, job và data access.

## 11. Triển khai Spring Security Method Security

Spring Security 6.5 kích hoạt method authorization khi có `@EnableMethodSecurity`. Với các phương thức của **Spring-managed bean**, `@PreAuthorize` có thể gọi một bean Java riêng trong SpEL:

```java
@PreAuthorize("@dataPolicy.canUpdate(authentication, #id)")
public Document update(@P("id") long id, String text) {
    // Chỉ chạy sau khi policy cho phép.
}
```

`authentication` được lấy từ method security expression context; `#id` lấy từ tham số được đánh dấu `@P("id")`. Bean `dataPolicy` phải được đăng ký với tên tương ứng trong Spring ApplicationContext.

**Không chỉ kiểm tra `hasAuthority` trên endpoint.** `DataPolicy` còn phải đọc bản ghi **phía server** để kiểm tra tenant, owner, trạng thái và sensitivity. Không tin các trường `owner`, `tenant`, `approved` do client tự gửi.

### 11.1. Đường đi qua proxy

```text
Controller -> DataService Spring proxy
              |
              v
         @PreAuthorize
              |
              +-- deny -> AccessDeniedException
              |          body chưa chạy
              |
              +-- allow -> DataService.method(...)
                            -> repository / transaction / event
```

Spring AOP proxy không tự intercept `this.update(...)` khi method gọi nội bộ trong cùng target. Đưa hành động nhạy cảm qua một Spring bean boundary rõ và kiểm thử các đường gọi thật. Cũng không tự coi `@PostAuthorize` là thay thế an toàn cho precheck của UPDATE/DELETE/APPROVE.

### 11.2. Authorization, validation và transaction là ba việc khác nhau

1. **Authorization** quyết định user có quyền với action/object không.
2. **Validation** kiểm tra payload hợp lệ theo schema và quy tắc nghiệp vụ (độ dài, trường bắt buộc, định dạng).
3. **Transaction/concurrency** đảm bảo trạng thái được cập nhật đúng khi nhiều request tranh chấp.

`@PreAuthorize` thường chạy **trước** thân method, nhưng không thay thế khóa hàng, version check hoặc transaction. Nếu bản ghi đổi từ SUBMITTED sang APPROVED giữa precheck và update, lời gọi phải xử lý conflict/stale state đúng, không lặng lẽ approve lần hai. Với dữ liệu rủi ro cao, thực hiện policy/state check trong transaction/locked resource và đặt precheck như một lớp bảo vệ bổ sung.

## 12. Project Java 17+ có kiểm thử đầy đủ

Ví dụ sử dụng Spring Security thật qua `@SpringJUnitConfig`, nhưng dùng repository **in-memory** để tập trung vào policy sáu quyền. Nó không cần database hoặc web server. Trong production thay repository bằng JPA/JDBC và bổ sung transaction, locking, audit thật.

### 12.1. Bố cục

```text
data-actions-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/DataActionsSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'data-actions-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Dùng Gradle có JDK 17+ và quyền lấy dependency từ Maven Central. Project này không cần `@SpringBootTest`: `@SpringJUnitConfig` tạo đúng context cho security method interceptors, nên không yêu cầu cấu hình HTTP `SecurityFilterChain`.

### 12.2. Mã Java test đầy đủ

Tạo `src/test/java/demo/DataActionsSecurityTest.java`:

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(DataActionsSecurityTest.Config.class)
public class DataActionsSecurityTest {

    @Autowired DataService service;
    @Autowired Store store;
    @Autowired Probe probe;

    @BeforeEach
    void resetFixtures() {
        store.reset();
        probe.reset();
    }

    enum State { DRAFT, SUBMITTED, APPROVED }

    public record Doc(
        long id, String tenant, String owner,
        State state, boolean sensitive, String text
    ) {}

    public record ReadView(long id, State state, String text) {}

    public static class Store {
        private final Map<Long, Doc> records =
            new ConcurrentHashMap<>();
        private final AtomicLong nextId = new AtomicLong(1000);

        void reset() {
            records.clear();
            nextId.set(1000);
            put(new Doc(1L, "TENANT_A", "alice",
                State.DRAFT, false, "Alice draft"));
            put(new Doc(2L, "TENANT_A", "alice",
                State.SUBMITTED, false, "Alice submission"));
            put(new Doc(3L, "TENANT_A", "bob",
                State.SUBMITTED, false, "Bob submission"));
            put(new Doc(4L, "TENANT_A", "bob",
                State.APPROVED, false, "Public report"));
            put(new Doc(5L, "TENANT_A", "bob",
                State.APPROVED, true, "Sensitive report"));
            put(new Doc(6L, "TENANT_B", "outsider",
                State.APPROVED, false, "Tenant B report"));
            put(new Doc(7L, "TENANT_A", "bob",
                State.DRAFT, false, "Bob draft"));
        }

        private void put(Doc doc) {
            records.put(doc.id(), doc);
        }

        public Doc get(long id) {
            return records.get(id);
        }

        public int count() {
            return records.size();
        }

        Doc create(String tenant, String owner, String text) {
            long id = nextId.incrementAndGet();
            Doc created = new Doc(
                id, tenant, owner, State.DRAFT, false, text);
            records.put(id, created);
            return created;
        }

        Doc update(long id, String text) {
            return records.compute(id, (key, doc) -> {
                if (doc == null || doc.state() != State.DRAFT) {
                    throw new IllegalStateException("Stale update");
                }
                return new Doc(
                    doc.id(), doc.tenant(), doc.owner(),
                    doc.state(), doc.sensitive(), text);
            });
        }

        boolean delete(long id) {
            Doc existing = records.get(id);
            if (existing == null || existing.state() != State.DRAFT) {
                throw new IllegalStateException("Stale delete");
            }
            return records.remove(id, existing);
        }

        Doc approve(long id) {
            return records.compute(id, (key, doc) -> {
                if (doc == null || doc.state() != State.SUBMITTED) {
                    throw new IllegalStateException("Stale approve");
                }
                return new Doc(
                    doc.id(), doc.tenant(), doc.owner(),
                    State.APPROVED, doc.sensitive(), doc.text());
            });
        }
    }

    public static class Probe {
        private final Map<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();

        void mark(String action) {
            calls.computeIfAbsent(
                action, name -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String action) {
            AtomicInteger counter = calls.get(action);
            return counter == null ? 0 : counter.get();
        }

        void reset() {
            calls.clear();
        }
    }

    public static class DataPolicy {
        private final Store store;

        // Chỉ là fixture server-side tin cậy cho demo.
        // Production dùng tenant được xác minh từ identity/DB.
        private static final Map<String, String> USER_TENANTS = Map.of(
            "alice", "TENANT_A",
            "bob", "TENANT_A",
            "manager", "TENANT_A",
            "auditor", "TENANT_A",
            "outsider", "TENANT_B"
        );

        public DataPolicy(Store store) {
            this.store = store;
        }

        private boolean has(Authentication auth, String authority) {
            return auth != null
                && auth.isAuthenticated()
                && auth.getAuthorities().stream().anyMatch(
                    a -> authority.equals(a.getAuthority()));
        }

        private String tenant(Authentication auth) {
            return auth == null ? null
                : USER_TENANTS.get(auth.getName());
        }

        private boolean sameTenant(Authentication auth, Doc doc) {
            String assigned = tenant(auth);
            return doc != null && assigned != null
                && assigned.equals(doc.tenant());
        }

        public boolean canRead(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_READ")
                && sameTenant(auth, doc)
                && (!doc.sensitive()
                    || doc.owner().equals(auth.getName())
                    || has(auth, "DOC_SENSITIVE_READ"));
        }

        public boolean canCreate(
                Authentication auth, String requestedTenant) {
            String assigned = tenant(auth);
            return has(auth, "DOC_CREATE")
                && assigned != null
                && assigned.equals(requestedTenant);
        }

        public boolean canUpdate(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_UPDATE")
                && sameTenant(auth, doc)
                && doc.owner().equals(auth.getName())
                && doc.state() == State.DRAFT;
        }

        public boolean canDelete(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_DELETE")
                && sameTenant(auth, doc)
                && doc.owner().equals(auth.getName())
                && doc.state() == State.DRAFT;
        }

        public boolean canApprove(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_APPROVE")
                && sameTenant(auth, doc)
                && doc.state() == State.SUBMITTED
                && !doc.owner().equals(auth.getName());
        }

        public boolean canExport(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_EXPORT")
                && canRead(auth, id)
                && doc.state() == State.APPROVED
                && !doc.sensitive();
        }
    }

    public static class DataService {
        private final Store store;
        private final Probe probe;

        public DataService(Store store, Probe probe) {
            this.store = store;
            this.probe = probe;
        }

        @PreAuthorize("@dataPolicy.canRead(authentication, #id)")
        public ReadView read(@P("id") long id) {
            probe.mark("READ");
            Doc doc = store.get(id);
            return new ReadView(
                doc.id(), doc.state(), doc.text());
        }

        @PreAuthorize(
            "@dataPolicy.canCreate(authentication, #tenant)"
        )
        public Doc create(
                @P("tenant") String tenant, String text) {
            probe.mark("CREATE");
            String owner = SecurityContextHolder.getContext()
                .getAuthentication().getName();
            return store.create(tenant, owner, text);
        }

        @PreAuthorize("@dataPolicy.canUpdate(authentication, #id)")
        public Doc update(@P("id") long id, String text) {
            probe.mark("UPDATE");
            return store.update(id, text);
        }

        @PreAuthorize("@dataPolicy.canDelete(authentication, #id)")
        public boolean delete(@P("id") long id) {
            probe.mark("DELETE");
            return store.delete(id);
        }

        @PreAuthorize("@dataPolicy.canApprove(authentication, #id)")
        public Doc approve(@P("id") long id) {
            probe.mark("APPROVE");
            return store.approve(id);
        }

        @PreAuthorize("@dataPolicy.canExport(authentication, #id)")
        public String exportCsv(@P("id") long id) {
            probe.mark("EXPORT");
            Doc doc = store.get(id);
            // Chỉ xuất các cột đã chọn, không xuất text/sensitive.
            return "id,tenant,state\n" +
                doc.id() + "," + doc.tenant() + "," +
                doc.state() + "\n";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {
        @Bean
        Store store() {
            return new Store();
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean("dataPolicy")
        DataPolicy dataPolicy(Store store) {
            return new DataPolicy(store);
        }

        @Bean
        DataService dataService(Store store, Probe probe) {
            return new DataService(store, probe);
        }
    }

    @Test
    void serviceIsReallyProtectedBySpringAop() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readPublicDocumentInSameTenantIsAllowed() {
        assertThat(service.read(4L).text())
            .isEqualTo("Public report");
        assertThat(probe.count("READ")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readAcrossTenantIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.read(6L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readSensitiveOtherOwnerIsDenied() {
        assertThatThrownBy(() -> service.read(5L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"DOC_READ", "DOC_SENSITIVE_READ"}
    )
    void sensitiveReadNeedsExtraAuthority() {
        assertThat(service.read(5L).text())
            .isEqualTo("Sensitive report");
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_CREATE")
    void createAllowedInOwnTenantAssignsTrustedOwner() {
        Doc created = service.create("TENANT_A", "New draft");
        assertThat(created.owner()).isEqualTo("alice");
        assertThat(created.tenant()).isEqualTo("TENANT_A");
        assertThat(created.state()).isEqualTo(State.DRAFT);
        assertThat(probe.count("CREATE")).isEqualTo(1);
        assertThat(store.count()).isEqualTo(8);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_CREATE")
    void createInOtherTenantIsDenied() {
        assertThatThrownBy(
            () -> service.create("TENANT_B", "Malicious"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.count()).isEqualTo(7);
        assertThat(probe.count("CREATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readPermissionDoesNotGrantCreate() {
        assertThatThrownBy(
            () -> service.create("TENANT_A", "No create"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("CREATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void ownerCanUpdateDraftTextOnly() {
        Doc changed = service.update(1L, "Changed");
        assertThat(changed.text()).isEqualTo("Changed");
        assertThat(changed.owner()).isEqualTo("alice");
        assertThat(changed.state()).isEqualTo(State.DRAFT);
        assertThat(probe.count("UPDATE")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void cannotUpdateAnotherOwnersDraft() {
        assertThatThrownBy(() -> service.update(7L, "Attack"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(7L).text()).isEqualTo("Bob draft");
        assertThat(probe.count("UPDATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void cannotUpdateSubmittedDocument() {
        assertThatThrownBy(
            () -> service.update(2L, "Late edit"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(2L).text())
            .isEqualTo("Alice submission");
        assertThat(probe.count("UPDATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_DELETE")
    void ownerCanDeleteOnlyOwnDraft() {
        assertThat(service.delete(1L)).isTrue();
        assertThat(store.get(1L)).isNull();
        assertThat(probe.count("DELETE")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_DELETE")
    void cannotDeleteAnotherOwnersDraft() {
        assertThatThrownBy(() -> service.delete(7L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(7L)).isNotNull();
        assertThat(probe.count("DELETE")).isZero();
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_DELETE")
    void cannotDeleteApprovedDocumentEvenWhenOwner() {
        assertThatThrownBy(() -> service.delete(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(4L)).isNotNull();
    }

    @Test
    @WithMockUser(username = "manager", authorities = "DOC_APPROVE")
    void separateApproverCanApproveSubmittedDocument() {
        Doc result = service.approve(2L);
        assertThat(result.state()).isEqualTo(State.APPROVED);
        assertThat(probe.count("APPROVE")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_APPROVE")
    void creatorCannotApproveOwnDocument() {
        assertThatThrownBy(() -> service.approve(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(2L).state())
            .isEqualTo(State.SUBMITTED);
        assertThat(probe.count("APPROVE")).isZero();
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void readAuthorityDoesNotGrantApproval() {
        assertThatThrownBy(() -> service.approve(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("APPROVE")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"DOC_READ", "DOC_EXPORT"}
    )
    void exportApprovedPublicDocumentIsAllowed() {
        assertThat(service.exportCsv(4L)).isEqualTo(
            "id,tenant,state\n4,TENANT_A,APPROVED\n");
        assertThat(probe.count("EXPORT")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readAuthorityAloneDoesNotGrantExport() {
        assertThatThrownBy(() -> service.exportCsv(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_EXPORT")
    void exportAuthorityAloneDoesNotGrantRead() {
        assertThatThrownBy(() -> service.exportCsv(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {
            "DOC_READ", "DOC_SENSITIVE_READ", "DOC_EXPORT"
        }
    )
    void sensitiveDocumentCannotBeExportedByThisPolicy() {
        assertThatThrownBy(() -> service.exportCsv(5L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"DOC_READ", "DOC_EXPORT"}
    )
    void draftDocumentCannotBeExported() {
        assertThatThrownBy(() -> service.exportCsv(1L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminRoleDoesNotImplicitlyGrantAllActions() {
        assertThatThrownBy(() -> service.read(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(username = "unknown", authorities = "DOC_READ")
    void unknownTenantCannotReadAnyDocument() {
        assertThatThrownBy(() -> service.read(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingObjectIsDeniedWithoutExecutingRead() {
        assertThatThrownBy(() -> service.read(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }
}
```

### 12.3. Lệnh chạy

Tại thư mục chứa `build.gradle`:

```bash
gradle test --tests demo.DataActionsSecurityTest
```

Nếu project có Gradle Wrapper: dùng `./gradlew test --tests demo.DataActionsSecurityTest` trên Linux/macOS hoặc `gradlew.bat test --tests demo.DataActionsSecurityTest` trên Windows.

**Kết quả kỳ vọng:** tất cả **25 test JUnit** thành công và Gradle kết thúc `BUILD SUCCESSFUL`. Đây là **kết quả dự kiến theo mã**; không phải log được thu thập từ một lần chạy Java thực tế. Chi tiết báo cáo: `build/reports/tests/test/index.html`.

### 12.4. Những test nào chứng minh sự khác nhau của quyền?

| Cụm test | Bằng chứng |
| --- | --- |
| READ public/cross-tenant/sensitive | Quyền đọc còn phụ thuộc phạm vi và độ nhạy |
| CREATE own tenant/other tenant/READ-only | CREATE cần authority và scope, owner tạo từ identity |
| UPDATE owner draft/other owner/submitted | UPDATE không phải APPROVE và không sửa mọi trạng thái |
| DELETE own draft/other draft/approved | DELETE độc lập với UPDATE, có ràng buộc trạng thái |
| APPROVE manager/own document/missing authority | SoD, trạng thái và quyền duyệt độc lập |
| EXPORT valid/READ only/EXPORT only/sensitive/draft | EXPORT cần cả chức năng và quyền đối với dữ liệu |
| ADMIN role/unknown principal/missing ID | Không suy quyền tự động; fail closed khi thiếu dữ liệu |
| Proxy assertion và Probe | Có Spring AOP và deny xảy ra trước thân method |

**Vì sao `Probe` quan trọng?** Một test chỉ kiểm tra exception có thể bỏ qua việc side effect đã xảy ra từ trước. Ở đây, nếu `@PreAuthorize` từ chối, counter của action không tăng; điều đó chứng minh **method body không được gọi** trên đường Spring proxy.

**Những gì demo chưa bảo đảm:** repository là ConcurrentHashMap, không có JPA transaction, audit logger, row lock, pagination, queue export, CSV escaping tùy nội dung, HTTP response mapper hoặc phân quyền theo tổ chức thật. Vì thế code chỉ nên dùng như **bộ kiểm thử cơ chế và policy mẫu**, không phải service production sẵn sàng triển khai.

## 13. Phần mở rộng: từ policy in-memory đến dữ liệu thật

### 13.1. Truy vấn cần được ràng buộc theo tenant

Ví dụ ý tưởng JPA repository:

```java
// Fragment minh họa, không phải interface repository độc lập.
@Query("""
    select d
    from DocumentEntity d
    where d.id = :id
      and d.tenantId = :tenantId
""")
Optional<DocumentEntity> findAllowedScope(
    @Param("id") Long id,
    @Param("tenantId") String tenantId
);
```

`tenantId` phải đến từ identity hoặc dữ liệu server tin cậy, **không** từ request chưa xác thực. Với list/search, áp dụng cùng scope ngay trong SQL, rồi xử lý cột/DTO được cấp quyền. Nếu dùng row-level security ở database, vẫn cần thiết lập tenant/session context an toàn và test mỗi connection trong pool.

### 13.2. Dùng `PermissionEvaluator` hoặc `AuthorizationManager` khi policy phức tạp

Khi hệ thống dùng ACL theo từng document, có thể diễn đạt:

```java
@PreAuthorize(
    "hasAuthority('DOC_UPDATE') and " +
    "hasPermission(#id, 'demo.Document', 'WRITE')"
)
public void update(@P("id") long id, String text) {
    // Còn phải kiểm tra status / field whitelist / transaction.
}
```

Đây là fragment minh họa, cần `PermissionEvaluator` được nối vào `MethodSecurityExpressionHandler` và `AclService` hoạt động. **Không coi `BasePermission.WRITE` tự tương đương quyền APPROVE hoặc EXPORT**: nếu có quyền workflow riêng, định nghĩa mask/authority/policy riêng.

Có thể tạo custom `AuthorizationManager<MethodInvocation>` cho các hành động, nhưng giá trị cốt lõi vẫn là rule theo **action + resource + actor + context**, không phải đặt annotation ở đâu.

### 13.3. Kiểm soát chênh lệch thời điểm (TOCTOU)

`@PreAuthorize` kiểm tra trạng thái tại một thời điểm. Sau đó, transaction khác có thể sửa trạng thái/owner/tenant trước khi câu SQL update chạy. Với approve, delete và giao dịch quan trọng:

1. Dùng `@Transactional` theo đúng ranh giới Spring proxy.
2. Lock/version đối tượng hoặc dùng conditional SQL update với trạng thái mong đợi.
3. Kiểm tra lại điều kiện ảnh hưởng đến quyền trong transaction và phản hồi conflict nếu dữ liệu đổi.
4. Không để phát event/side effect ngoài transaction trước khi commit.
5. Test hai request tranh chấp duyệt/xóa cùng object.

Ví dụ SQL cập nhật có điều kiện:

```sql
UPDATE documents
SET status = 'APPROVED',
    approved_by = :actor
WHERE id = :id
  AND tenant_id = :tenant
  AND status = 'SUBMITTED'
  AND created_by <> :actor;
```

Đây là **SQL định hướng triển khai**, không chạy độc lập. Kiểm tra số dòng affected bằng 1 mới coi thao tác thành công, đồng thời phải kiểm tra quyền `DOC_APPROVE` và policy liên quan trước lệnh này; không suy rằng câu SQL tự thay thế authentication.

## 14. Bulk operation và export bất đồng bộ

Nếu người dùng chọn 100 bản ghi để cập nhật hoặc export:

- **Bulk READ/EXPORT:** không được vì một phần tử được phép mà tự cho phép phần còn lại.
- **Bulk DELETE:** xác định toàn bộ phải được cấp quyền hay cho phép partial success; nếu partial, API phải trả kết quả từng ID và không lộ chi tiết bản ghi trái quyền.
- **Bulk APPROVE:** kiểm tra SoD và trạng thái **trên từng bản ghi**, không chỉ kiểm tra role của người duyệt một lần.
- **Bulk UPDATE:** giới hạn trường cập nhật, version và số lượng, xử lý transaction/locking.
- **Export job:** recheck ownership, tenant, sensitivity và revoke policy ở thời điểm tạo file và tải file theo mô hình rủi ro.

Ví dụ response cho bulk action phải tránh làm lộ nội dung/tên của bản ghi trái quyền. Nếu dùng `@PreFilter` hoặc `@PostFilter`, phải hiểu chúng thực thi trong method-security interceptor và không tự sửa query database; với data lớn thường nên xử lý scope tại data layer.

## 15. Bộ kiểm thử nên có trước production

Bảng trường hợp tối thiểu cho sáu thao tác:

| Nhóm | Trường hợp cần test |
| --- | --- |
| READ | Có quyền/không có quyền, owner/người khác, đúng/chéo tenant, public/sensitive, row/field redaction |
| CREATE | Đúng/chéo tenant, request tự khai owner/role/status, object chưa tồn tại, quota và loại dữ liệu |
| UPDATE | Đúng owner, owner khác, DRAFT/SUBMITTED/APPROVED, field allowlist, version conflict |
| DELETE | DRAFT/APPROVED, soft/hard delete, legal hold, dữ liệu liên quan, audit và rollback |
| APPROVE | Người duyệt khác người lập, tự duyệt, sai trạng thái, duyệt lặp, hai approver đồng thời |
| EXPORT | READ-only/EXPORT-only/đủ cả hai, sensitive, tenant, nhiều dòng, nhiều cột, link job, thu hồi quyền |
| Cross-cutting | Anonymous/role admin, self-invocation, batch/scheduler, stale cache, BOLA, log và error leakage |

Một quy tắc nghiệm thu quan trọng là **negative-path tests phải chứng minh không có side effect**: database không thay đổi, event không phát, file chưa tạo, audit ghi đúng denial. Đối với EXPORT, cần xác minh file **chỉ** chứa những record và cột được cấp quyền, thay vì chỉ kiểm tra mã HTTP 200/403.

## 16. Những sai lầm hay gặp

**Sai lầm 1 — “Có READ thì được EXPORT.”** Không đúng trừ khi chính sách cố ý định nghĩa vậy. Export có tác động ngoài hệ thống và có thể tập hợp nhiều dữ liệu; cần authority riêng cùng kiểm soát scope.

**Sai lầm 2 — “Người tạo mặc nhiên được sửa hoặc duyệt mãi.”** CREATE/UPDATE/APPROVE khác nhau. Khi tài liệu đã SUBMITTED hoặc APPROVED, quyền sửa phải thay đổi theo workflow, người tạo không được tự duyệt nếu áp dụng SoD.

**Sai lầm 3 — “Chỉ cần kiểm tra `ROLE_ADMIN`.”** Role rộng có thể bỏ qua ownership, tenant, sensitivity và các yêu cầu kiểm soát hai người. Role chỉ là một phần của policy, không thay cho object-level authorization.

**Sai lầm 4 — “ID khó đoán là đã an toàn.”** UUID ngẫu nhiên giảm khả năng đoán ID nhưng không thay thế kiểm tra quyền trên mọi object khi nhận ID từ client.

**Sai lầm 5 — “Ẩn nút là đủ.”** Frontend chỉ là UX. API, GraphQL, batch worker và service method vẫn cần kiểm tra quyền ở server.

**Sai lầm 6 — “`@PostAuthorize` chặn được giao dịch sai.”** Nó chạy sau method body. Với UPDATE/DELETE/APPROVE, cần authorization trước side effect và state/transaction kiểm soát khi ghi.

**Sai lầm 7 — “Đã chặn GET thì POST/DELETE được bảo vệ theo.”** Mỗi chức năng/HTTP method/action phải có policy riêng, kể cả custom endpoints như `/approve` hoặc `/export`.

**Sai lầm 8 — “Export chỉ cần kiểm tra từng dòng.”** Còn phải kiểm tra field/column, volume, định dạng, job ownership, URL expiry, audit và retention.

**Sai lầm 9 — “Update một entity nguyên bản từ JSON cho nhanh.”** Mass assignment có thể sửa `approved`, `owner`, `tenant` hoặc quyền. Dùng DTO allowlist và cập nhật trường được phép rõ ràng.

**Sai lầm 10 — “Kiểm tra quyền một lần là đủ.”** Quyền có thể thay đổi giữa check và commit/đến lúc export chạy. Cần transaction/lock/recheck theo rủi ro, đặc biệt với quyền bị thu hồi.

## 17. Bài tập

1. **Thêm trạng thái REJECTED:** định nghĩa quyền `DOC_REJECT` tách `DOC_APPROVE`, test người tạo không tự reject nếu sản phẩm yêu cầu.
2. **Bảo vệ trường:** mở rộng Doc có `salary` và `internalNote`; cho READ metadata nhưng kiểm tra `DOC_SENSITIVE_READ` trước khi trả trường nhạy cảm.
3. **Thêm ACL:** cho Alice chỉ được WRITE trên Doc#7 khi có ACE của Bob ủy quyền; kiểm tra authority UPDATE + permission WRITE + trạng thái DRAFT.
4. **Thử mass assignment:** cho client gửi `owner="manager", state="APPROVED"` khi UPDATE. Thiết kế DTO và test hai trường này không bao giờ bị client thay đổi.
5. **Xuất hàng loạt:** thêm `exportTenantCsv` với predicate query và column allowlist, test mỗi dòng đều có READ, không có tenant B và giới hạn số lượng.
6. **Maker-checker:** tạo user có đồng thời `DOC_UPDATE` và `DOC_APPROVE`; test người đó vẫn không tự duyệt tài liệu mình lập.
7. **Race condition:** hai người cùng duyệt một SUBMITTED document; kết hợp optimistic version hoặc conditional update, chỉ một người thành công.
8. **Revoke export job:** tạo export job với quyền hợp lệ, sau đó admin thu hồi `DOC_EXPORT`; thiết kế policy lúc download và test kết quả.

## 18. Tổng kết

Ghi nhớ theo **hành động + dữ liệu + ngữ cảnh**:

- **READ:** được xem **bản ghi và các trường** hợp lệ.
- **CREATE:** được tạo trong **phạm vi** hợp lệ; server định danh owner/tenant/trạng thái.
- **UPDATE:** được thay **trường** hợp lệ của **bản ghi** hợp lệ trong **trạng thái** hợp lệ.
- **DELETE:** được xóa theo policy riêng, lưu ý retention và khả năng khôi phục.
- **APPROVE:** được **chuyển trạng thái** theo workflow, có kiểm soát phân tách nhiệm vụ.
- **EXPORT:** được đưa **tập dữ liệu đã chọn** ra ngoài, cần quyền riêng, scope/field/volume và bảo vệ file.

Spring Security cung cấp **cơ chế thực thi** `@PreAuthorize`, `AuthorizationManager`, `PermissionEvaluator`; chính **ứng dụng** phải xác định các quy tắc trên, triển khai policy đọc dữ liệu đáng tin và kiểm thử cả allow/deny/side effect. Một quyền rộng không tự thay thế sáu quyết định nghiệp vụ khác nhau.

## Tài liệu tham khảo

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, `@PreAuthorize`, custom bean trong SpEL: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize HTTP Requests; khác biệt HTTP authorization và service authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- OWASP API1:2023 — Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API3:2023 — Broken Object Property Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP API5:2023 — Broken Function Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/
- NIST CSRC Glossary — Separation of Duty: https://csrc.nist.gov/glossary/term/separation_of_duty
