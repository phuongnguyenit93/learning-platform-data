# Bổ sung auditing, phân quyền bản ghi và bảo vệ thông tin nhạy cảm

## 1. Ba trách nhiệm cần thiết kế riêng

Một ứng dụng Spring Data Relational R2DBC thường cần ghi nhận ai đã tạo hoặc sửa dữ liệu, giới hạn người dùng được truy cập những bản ghi nào và bảo vệ các trường có thông tin nhạy cảm. Ba yêu cầu này liên quan nhưng không thay thế cho nhau:

- **Auditing** ghi nhận metadata về vòng đời dữ liệu, chẳng hạn người tạo, thời điểm tạo, người sửa gần nhất và thời điểm sửa gần nhất.
- **Phân quyền bản ghi (row-level authorization)** quyết định người dùng hoặc service được phép đọc, cập nhật hay xóa bản ghi cụ thể nào.
- **Bảo vệ thông tin nhạy cảm** giới hạn việc thu thập, lưu trữ, truyền tải, hiển thị và ghi log dữ liệu cần bảo vệ.

Ví dụ, một bản ghi tài liệu có thể chứa:

- created_by, created_at, updated_by, updated_at: metadata auditing.
- tenant_id, owner_id: thông tin dùng để xác định phạm vi truy cập.
- customer_email, tax_number, private_note: dữ liệu cần bảo vệ theo chính sách.

Có created_by không có nghĩa người tạo là người duy nhất được phép đọc bản ghi. Có tenant_id cũng không tự bảo đảm mọi query đều giới hạn đúng tenant. Mã hóa database không thay thế authorization. Mỗi lớp cần được thực thi và kiểm thử độc lập.

## 2. Kiến trúc tổng quan

Có thể tổ chức luồng xử lý như sau:

~~~text
Authenticated request / trusted job
              |
              v
      Security identity + tenant
              |
              v
       Service authorization
       - actor is authenticated
       - tenant / owner scope
       - business permission
              |
              v
       Repository / DatabaseClient
       - scoped SELECT / UPDATE / DELETE
       - auditing callbacks
              |
              v
         R2DBC ConnectionFactory
              |
              v
            Database
       - constraints / optional RLS
       - least-privilege database role
              |
              v
       Protected data + audit metadata
              |
              v
       DTO / response projection
       - expose allowed fields only
       - redact sensitive values
~~~

Luồng này có nhiều lớp phòng vệ. Service xác định actor và quyền nghiệp vụ; query giới hạn bản ghi; database constraint bảo vệ tính toàn vẹn; Row-Level Security (RLS), nếu được dùng, tạo thêm lớp kiểm soát ở database; DTO quyết định trường nào được trả ra ngoài.

Không nên đặt toàn bộ quyền truy cập trong controller hoặc dựa vào việc giao diện không hiển thị nút sửa. Mọi request đều có thể được gửi trực tiếp đến API. Quyền phải được xác minh ở server và ở mọi đường truy cập dữ liệu có liên quan.

## 3. Auditing trong Spring Data R2DBC

Spring Data R2DBC hỗ trợ auditing metadata qua các annotation của Spring Data:

| Annotation | Ý nghĩa |
|---|---|
| @CreatedBy | Actor tạo bản ghi |
| @CreatedDate | Thời điểm tạo |
| @LastModifiedBy | Actor sửa gần nhất |
| @LastModifiedDate | Thời điểm sửa gần nhất |

Các annotation nằm trong package org.springframework.data.annotation. Auditing được kích hoạt bằng @EnableR2dbcAuditing. Khi cần lấy actor từ reactive security context, cung cấp một bean ReactiveAuditorAware<T>.

Auditing phù hợp để trả lời những câu hỏi như:

- Ai tạo bản ghi này?
- Bản ghi được tạo lúc nào?
- Ai sửa gần nhất?
- Lần sửa gần nhất diễn ra khi nào?

Nó không tự lưu toàn bộ lịch sử thay đổi. @LastModifiedBy chỉ cho biết actor gần nhất, không cho biết tất cả actor từng sửa hoặc giá trị trước/sau của từng lần sửa.

### 3.1. Khai báo auditing metadata trong entity

Ví dụ entity immutable:

~~~java
@Table("documents")
public record Document(
        @Id Long id,
        String title,
        String body,
        UUID tenantId,
        UUID ownerId,
        @CreatedBy String createdBy,
        @CreatedDate Instant createdAt,
        @LastModifiedBy String updatedBy,
        @LastModifiedDate Instant updatedAt,
        @Version Long version
) {}
~~~

Các trường có vai trò khác nhau:

- tenantId xác định tenant sở hữu dữ liệu.
- ownerId xác định chủ sở hữu nghiệp vụ nếu mô hình có khái niệm owner.
- createdBy và updatedBy ghi nhận actor.
- createdAt và updatedAt ghi nhận thời gian.
- version hỗ trợ optimistic locking theo cấu hình Spring Data R2DBC.

Không dùng createdBy thay cho ownerId nếu nghiệp vụ cho phép người khác tạo bản ghi thay mặt chủ sở hữu. Ví dụ nhân viên hỗ trợ có thể tạo hồ sơ cho khách hàng; actor tạo và owner của hồ sơ là hai người khác nhau.

Với entity mutable, các trường auditing cũng có thể được khai báo như property. Cần bảo đảm constructor/property access và kiểu dữ liệu tương thích với mapping đang dùng.

### 3.2. Bật R2DBC auditing

Cấu hình cơ bản:

~~~java
@Configuration
@EnableR2dbcAuditing
class R2dbcAuditingConfiguration {
}
~~~

Nếu muốn tự cung cấp auditor, cấu hình tham chiếu tới bean tương ứng:

~~~java
@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName)
                .filter(name -> !"anonymousUser".equals(name));
    }
}
~~~

Các import chính thường đến từ:

- org.springframework.data.domain.ReactiveAuditorAware
- org.springframework.data.r2dbc.config.EnableR2dbcAuditing
- org.springframework.security.core.Authentication
- org.springframework.security.core.context.SecurityContext
- org.springframework.security.core.context.ReactiveSecurityContextHolder

Đoạn code giả định ứng dụng dùng Spring Security reactive. Nếu ứng dụng xác thực bằng cơ chế khác, hãy cung cấp ReactiveAuditorAware dựa trên actor context đáng tin cậy của hệ thống.

ReactiveAuditorAware trả về Mono<T>. Nếu không có actor, có thể trả Mono.empty(). Khi đó auditing actor field có thể không được điền; hành vi cần được xác định rõ theo schema và nghiệp vụ. Không tự động gán một user mặc định cho mọi request vì điều đó làm mất khả năng truy vết.

### 3.3. Không lấy actor từ request body hoặc header tùy ý

Actor auditing phải đến từ identity đã được server xác thực. Không dùng các giá trị như createdBy do client gửi trong JSON hoặc X-User-Id không được xác minh.

Nếu người dùng có thể tự gửi actor ID, họ có thể ghi nhận một người khác là người tạo/sửa dữ liệu. Điều này làm sai audit trail và có thể ảnh hưởng quyết định bảo mật.

Luồng đáng tin cậy thường là:

1. Authentication filter xác thực credential/token.
2. Spring Security đặt Authentication vào reactive security context.
3. Service/repository auditing lấy actor từ context.
4. Client không được tự quyết định createdBy hoặc updatedBy.

Nếu hệ thống có impersonation hợp lệ, hãy ghi riêng actor thực hiện và subject đang được đại diện, kèm lý do/authorization context. Không ghi đè mất danh tính người thao tác thực tế.

## 4. Reactive Security Context và AuditorAware

Trong ứng dụng WebFlux, execution có thể chuyển thread. Vì vậy, không nên dựa vào ThreadLocal hoặc imperative SecurityContextHolder để lấy actor trong reactive pipeline.

ReactiveSecurityContextHolder truy xuất SecurityContext từ Reactor Context. Điều này phù hợp với ReactiveAuditorAware vì auditor được phân giải trong reactive flow.

Một số nguyên tắc:

- Không gọi block() để lấy Authentication trong auditor.
- Không gọi subscribe() riêng để đọc actor.
- Không lưu actor vào một biến mutable dùng chung giữa request.
- Không dựa vào thread hiện tại để xác định người dùng.
- Kiểm tra rằng context được truyền qua các operator và boundary tùy chỉnh.

Ví dụ lấy actor trong service:

~~~java
public Mono<String> currentActor() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
}
~~~

Auditor có thể được dùng tự động khi Spring Data thực hiện thao tác mapping/lưu entity. Nếu code chạy ngoài request, chẳng hạn scheduled job hoặc message consumer, cần xác định actor hệ thống rõ ràng.

### 4.1. Background job và service account

Background job thường không có user session. Không nên giả định ReactiveSecurityContextHolder luôn có giá trị.

Có thể định nghĩa actor riêng cho job, ví dụ service:invoice-reconciler, và đưa nó vào context theo cơ chế có kiểm soát. Một lựa chọn là tạo Authentication đại diện service account rồi dùng ReactiveSecurityContextHolder.withAuthentication(...) khi chạy publisher của job. Cách khác là dùng một actor context riêng và triển khai ReactiveAuditorAware đọc context đó.

Quan trọng là actor phải phản ánh nguồn thực thi thật:

- Người dùng đã xác thực.
- Service account.
- Scheduled job.
- Message consumer.
- Hệ thống migration hoặc vận hành.

Không gán mọi thao tác không có user thành một người dùng quản trị chung nếu cần truy vết chính xác. Có thể ghi actor type và job/message identifier trong audit event riêng.

## 5. Thời gian auditing và timezone

Nên chọn kiểu thời gian nhất quán, thường là Instant cho thời điểm tuyệt đối. Lưu trữ thời gian theo UTC và chỉ chuyển timezone khi hiển thị cho người dùng.

Ví dụ entity dùng:

~~~java
@CreatedDate
Instant createdAt;

@LastModifiedDate
Instant updatedAt;
~~~

Nếu schema dùng PostgreSQL, TIMESTAMPTZ thường phù hợp cho thời điểm tuyệt đối. Cần xác nhận mapping với driver và kiểu SQL của database đang dùng.

Các điểm cần quyết định:

- Clock nào cung cấp thời gian: application hay database?
- Có cần đồng bộ clock giữa nhiều instance không?
- Độ chính xác timestamp của database là bao nhiêu?
- Có cần test thời gian tạo và cập nhật không?
- Khi import dữ liệu cũ, có giữ timestamp gốc không?

Trong test, có thể cấu hình clock/provider phù hợp nếu cần thời gian xác định. Tránh so sánh chuỗi timestamp phụ thuộc timezone mặc định của máy.

## 6. Auditing metadata không phải audit trail đầy đủ

Auditing metadata trong entity chỉ giữ trạng thái hiện tại của các trường created/modified. Nếu cần biết lịch sử thay đổi, hãy thiết kế audit trail riêng.

Một audit event có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| event_id | ID duy nhất của event |
| occurred_at | Thời điểm sự kiện |
| actor_id | Người hoặc service thực hiện |
| actor_type | User, service, job hoặc hệ thống |
| action | CREATE, UPDATE, DELETE, EXPORT hoặc action nghiệp vụ |
| resource_type | Loại tài nguyên |
| resource_id | ID tài nguyên |
| tenant_id | Phạm vi tenant |
| correlation_id | Liên kết với request/trace |
| reason | Lý do nếu nghiệp vụ yêu cầu |
| change_summary | Mô tả thay đổi đã được lọc dữ liệu nhạy cảm |

Ví dụ:

~~~json
{
  "eventId": "a7f8...",
  "occurredAt": "2026-11-15T10:30:00Z",
  "actorId": "user-42",
  "actorType": "USER",
  "action": "DOCUMENT_UPDATED",
  "resourceType": "DOCUMENT",
  "resourceId": "doc-900",
  "tenantId": "tenant-7",
  "correlationId": "req-abc",
  "changeSummary": {
    "title": {
      "changed": true
    },
    "body": {
      "changed": true,
      "value": "[REDACTED]"
    }
  }
}
~~~

Ví dụ chỉ minh họa cấu trúc. Không ghi nguyên văn password, token, secret, nội dung hồ sơ nhạy cảm hoặc dữ liệu cá nhân không cần thiết vào audit event.

Nếu audit trail cần không thể sửa/xóa bởi application runtime, có thể dùng bảng append-only với quyền database chỉ cho INSERT/SELECT, quyền UPDATE/DELETE tách riêng cho vai trò vận hành được kiểm soát. Với yêu cầu chống sửa đổi mạnh, cần thêm cơ chế lưu trữ bất biến hoặc tamper-evident theo chính sách tổ chức.

## 7. Ghi audit event nhất quán với transaction

Nếu audit event là bằng chứng bắt buộc cho một thay đổi nghiệp vụ, cần quyết định quan hệ giữa dữ liệu chính và audit event.

Ví dụ, khi cập nhật tài liệu, nếu bản ghi được commit nhưng audit event bị mất thì lịch sử không đầy đủ. Ngược lại, nếu audit event được ghi trước nhưng cập nhật tài liệu rollback, trail có thể ghi nhận một thay đổi chưa xảy ra.

Một cách phổ biến là ghi dữ liệu nghiệp vụ và audit/outbox event trong cùng transaction database:

~~~text
Reactive transaction
       |
       +--> UPDATE documents
       |
       +--> INSERT audit_outbox
       |
       v
     COMMIT
       |
       v
Background publisher reads outbox
       |
       v
Append audit event / publish downstream
~~~

Nếu audit event nằm cùng database và cần atomic với bản ghi, ghi cả hai trong cùng reactive transaction. Nếu gửi event đến hệ thống ngoài, transactional outbox giúp tránh phụ thuộc vào việc network call thành công trong transaction.

Không gửi HTTP hoặc publish message trực tiếp trong callback entity rồi giả định thao tác đó atomic với commit. Callback trước/sau khi save không tự đảm bảo message chỉ được gửi sau commit.

## 8. Phân quyền bản ghi là gì?

Authorization ở mức endpoint thường trả lời “người dùng có được gọi chức năng này không?”. Row-level authorization trả lời thêm “người dùng này có được phép thao tác trên bản ghi cụ thể này không?”.

Ví dụ hai người dùng đều có quyền document:read, nhưng mỗi người chỉ được xem tài liệu thuộc tenant hoặc owner của mình.

Các phạm vi phổ biến:

- **Tenant scope:** chỉ truy cập bản ghi thuộc tenant hiện tại.
- **Owner scope:** chỉ truy cập bản ghi do user sở hữu.
- **Team/organization scope:** truy cập bản ghi thuộc nhóm hoặc đơn vị được phân quyền.
- **Relationship scope:** chỉ truy cập bản ghi có quan hệ hợp lệ với user, ví dụ nhân viên được phân công vào case.
- **Administrative scope:** actor có quyền đặc biệt và phải được ghi nhận rõ.

Không nên xem id là bí mật. Một ID khó đoán không thay thế authorization. Nếu API nhận /documents/900, server vẫn phải kiểm tra user có quyền với document 900.

Đây là cách ngăn lỗi Insecure Direct Object Reference (IDOR): user thay ID trong URL hoặc request body để đọc/sửa bản ghi của người khác.

## 9. Đưa tenant và owner scope vào query

Một cách rõ ràng là định nghĩa repository method có điều kiện tenant/owner:

~~~java
public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Document> findByIdAndTenantId(
            Long id,
            UUID tenantId
    );

    Flux<Document> findAllByTenantIdAndOwnerId(
            UUID tenantId,
            UUID ownerId
    );
}
~~~

Service lấy tenant/actor từ context đáng tin cậy rồi truyền vào query:

~~~java
public Mono<Document> findDocument(Long id) {
    return currentTenantId()
            .flatMap(tenantId ->
                    documentRepository.findByIdAndTenantId(id, tenantId)
            );
}
~~~

Đối với owner-scoped access, thêm owner ID hoặc kiểm tra permission tương ứng:

~~~java
public Mono<Document> findOwnedDocument(Long id) {
    return currentTenantId()
            .zipWith(currentUserId())
            .flatMap(tuple ->
                    documentRepository.findByIdAndTenantIdAndOwnerId(
                            id,
                            tuple.getT1(),
                            tuple.getT2()
                    )
            );
}
~~~

Các method currentTenantId() và currentUserId() là abstraction lấy thông tin từ security context/tenant resolver của ứng dụng. Không lấy tenant ID trực tiếp từ request body rồi tin tưởng nó. Nếu request có tenant selector, server phải xác minh user được phép hoạt động trong tenant đó trước.

Query scoped khiến database chỉ trả bản ghi trong phạm vi hợp lệ. Nó cũng giảm nguy cơ code vô tình load một row không thuộc tenant rồi mới kiểm tra sau.

### 9.1. Không dùng findById không giới hạn trong luồng multi-tenant

Một lỗi thường gặp:

~~~java
return documentRepository.findById(id)
        .flatMap(document -> authorize(document));
~~~

Cách này tải row trước khi kiểm tra quyền. Nếu mọi đường code đều kiểm tra đúng thì vẫn có thể an toàn, nhưng dễ bị bỏ sót ở nhánh khác, log hoặc response. Với dữ liệu multi-tenant, nên ưu tiên query có scope:

~~~java
return documentRepository.findByIdAndTenantId(id, tenantId)
        .switchIfEmpty(Mono.error(new DocumentNotFoundException()));
~~~

Dùng cùng quy ước cho SELECT, UPDATE, DELETE, count, export và bulk operation. Không chỉ bảo vệ endpoint đọc chi tiết.

### 9.2. Tránh lộ sự tồn tại của bản ghi

Khi user không có quyền truy cập, có thể trả 404 để không tiết lộ bản ghi có tồn tại hay không, hoặc trả 403 nếu chính sách API muốn thể hiện rõ bị từ chối. Đây là quyết định bảo mật/API contract cần thống nhất.

Điều quan trọng là không trả nội dung bản ghi, tenant ID, owner ID hoặc thông tin nhạy cảm trong error message. Log nội bộ có thể ghi lý do từ chối theo cách kiểm soát, nhưng không nên đưa chi tiết đó ra response công khai.

## 10. Bảo vệ UPDATE và DELETE bằng điều kiện scope

Không chỉ SELECT mới cần tenant/owner predicate. UPDATE và DELETE cũng phải có điều kiện scope.

Ví dụ DatabaseClient update:

~~~java
public Mono<Integer> renameDocument(
        Long id,
        UUID tenantId,
        UUID ownerId,
        String title) {

    return databaseClient.sql("""
            UPDATE documents
            SET title = :title,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
              AND tenant_id = :tenantId
              AND owner_id = :ownerId
            """)
            .bind("title", title)
            .bind("id", id)
            .bind("tenantId", tenantId)
            .bind("ownerId", ownerId)
            .fetch()
            .rowsUpdated();
}
~~~

Kết quả số hàng bị tác động cần được xử lý rõ:

- 1: có một row được cập nhật.
- 0: row không tồn tại hoặc không nằm trong scope; không tiết lộ nguyên nhân nếu chính sách yêu cầu ẩn sự tồn tại.
- Lỗi: xử lý theo lỗi database/driver và chính sách retry.

Câu lệnh dùng bind parameter cho giá trị. Không nối title, ID hoặc tenant từ input vào SQL bằng string concatenation.

Đối với DELETE, áp dụng cùng điều kiện:

~~~sql
DELETE FROM documents
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :ownerId
~~~

Với native query, hãy kiểm tra từng đường code vì query tự viết có thể bỏ qua quy ước scope của repository method thông thường.

## 11. Tập trung hóa authorization để tránh quên predicate

Khi số lượng repository lớn, việc lặp lại tenant/owner predicate ở mọi service có thể dẫn đến lỗi. Có thể xây dựng các cơ chế:

- Service method yêu cầu một AuthorizedTenant hoặc context đã xác thực.
- Repository custom fragment chỉ cung cấp method scoped.
- Base repository tùy chỉnh cho những thao tác phổ biến.
- Query builder thêm tenant predicate bắt buộc.
- Database RLS làm lớp bảo vệ bổ sung.
- Integration test kiểm tra các đường SELECT/UPDATE/DELETE.

Ví dụ kiểu dữ liệu biểu diễn scope đã được xác minh:

~~~java
public record AccessScope(
        UUID tenantId,
        UUID actorId,
        Set<String> permissions
) {}
~~~

Không tạo AccessScope từ dữ liệu client một cách trực tiếp. Một component xác thực cần tạo scope sau khi xác minh principal và quyền.

Tránh một repository interface công khai cả findById(id) unrestricted và các method scoped rồi để developer tự nhớ method nào an toàn. Có thể giới hạn nơi truy cập repository, tạo facade hoặc quy ước code review rõ ràng.

## 12. Tenant isolation và tính toàn vẹn dữ liệu

Trong hệ multi-tenant, foreign key thông thường chỉ bảo đảm bản ghi tham chiếu tồn tại; nó không nhất thiết bảo đảm hai bản ghi thuộc cùng tenant.

Ví dụ bảng documents và document_comments đều có tenant_id. Có thể dùng unique key kết hợp và composite foreign key để bảo đảm comment chỉ tham chiếu document trong cùng tenant:

~~~sql
ALTER TABLE documents
ADD CONSTRAINT uq_documents_tenant_id_id
UNIQUE (tenant_id, id);

ALTER TABLE document_comments
ADD CONSTRAINT fk_comments_document_tenant
FOREIGN KEY (tenant_id, document_id)
REFERENCES documents (tenant_id, id);
~~~

Điều này tạo thêm lớp bảo vệ ở schema. Nếu ứng dụng cố ghi comment với tenant A nhưng document thuộc tenant B, database từ chối.

Index cũng cần phù hợp với query scope:

~~~sql
CREATE INDEX ix_documents_tenant_owner_updated
ON documents (tenant_id, owner_id, updated_at DESC);
~~~

Index thực tế phụ thuộc workload, selectivity và query plan. Không tạo index theo checklist mà không đo. Với unique business key theo tenant, dùng unique constraint kết hợp (tenant_id, business_key) nếu đó là quy tắc nghiệp vụ.

## 13. PostgreSQL Row-Level Security (RLS)

Ngoài authorization ở service/query, PostgreSQL cung cấp Row-Level Security để giới hạn row mà database role được phép đọc hoặc thay đổi.

Ví dụ bật RLS:

~~~sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy
ON documents
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Ý nghĩa:

- USING giới hạn row hiện có được nhìn thấy hoặc thao tác.
- WITH CHECK giới hạn row mới hoặc row sau UPDATE phải thỏa policy.
- current_setting(..., true) trả về NULL nếu setting chưa được đặt; biểu thức so sánh khi đó không cho phép row phù hợp.
- FORCE ROW LEVEL SECURITY áp dụng policy cả với table owner trong các trường hợp thông thường, nhưng superuser và role có BYPASSRLS vẫn có thể bỏ qua RLS.

Cần dùng runtime database role không phải superuser và không có BYPASSRLS. Nếu role sở hữu bảng, hãy hiểu rõ hành vi owner/RLS và kiểm thử với chính role runtime.

### 13.1. Đặt tenant context trong transaction

Có thể đặt tenant bằng transaction-local setting trước khi query:

~~~java
Mono<Map<String, Object>> setTenant =
        databaseClient.sql("""
                SELECT set_config('app.tenant_id', :tenantId, true)
                """)
                .bind("tenantId", tenantId.toString())
                .fetch()
                .one();

Mono<List<Document>> work =
        setTenant.thenMany(documentRepository.findAll())
                .collectList();

return transactionalOperator.transactional(work);
~~~

Ví dụ minh họa cần điều chỉnh kiểu trả về và repository API theo dự án. Điều quan trọng là set_config(..., true) đặt setting chỉ trong transaction hiện tại. Câu lệnh đặt context và query được bảo vệ phải chạy trong cùng transaction/connection.

Không dùng session-level setting lâu dài trên connection pooled. Nếu tenant A đặt session variable rồi connection được trả pool và dùng cho tenant B, tenant context cũ có thể rò rỉ sang request khác. Transaction-local setting giảm rủi ro này vì tự hết hiệu lực khi transaction kết thúc.

Không chạy câu lệnh set tenant trong một connection rồi query bằng một connection khác. Với pool, không có bảo đảm hai lần acquire độc lập nhận cùng connection. Hãy đặt và sử dụng context trong cùng reactive transaction.

### 13.2. RLS là defense in depth, không phải lý do bỏ query scope

RLS có thể bảo vệ khi một query vô tình thiếu tenant predicate, nhưng vẫn cần authorization ở application layer để kiểm tra quyền nghiệp vụ, owner, team và action.

Cần lưu ý:

- PostgreSQL policy có thể kết hợp nhiều policy permissive theo OR; restrictive policy được kết hợp theo AND.
- Role có quyền đặc biệt có thể bypass RLS.
- Table owner có hành vi riêng nếu không FORCE RLS.
- Migration/admin role có thể có quyền khác runtime role.
- Các view, function, partition và bảng liên quan cần được đánh giá riêng.
- Background job phải đặt tenant context đúng.
- Test phải chạy bằng runtime role thực tế.

Nếu dùng nhiều tenant policy, hãy kiểm tra cách chúng kết hợp để không vô tình mở rộng quyền. RLS không thay thế review schema, role và application authorization.

## 14. Bảo vệ thông tin nhạy cảm ở tầng API

Không trả trực tiếp entity database ra API nếu entity có trường nội bộ hoặc nhạy cảm.

Hãy dùng response DTO chỉ chứa trường cần thiết:

~~~java
public record DocumentResponse(
        Long id,
        String title,
        String bodyPreview,
        Instant createdAt,
        String ownerDisplayName
) {}
~~~

Mapping DTO:

~~~java
public Mono<DocumentResponse> getDocument(Long id) {
    return authorizedDocument(id)
            .map(document -> new DocumentResponse(
                    document.id(),
                    document.title(),
                    preview(document.body()),
                    document.createdAt(),
                    resolveOwnerDisplayName(document.ownerId())
            ));
}
~~~

Ví dụ chỉ minh họa allowlist. Không đưa tenantId, internal notes, access token, secret hoặc dữ liệu cá nhân không cần thiết vào response.

@JsonIgnore có thể hỗ trợ serialization nhưng không phải cơ chế authorization đầy đủ. Một endpoint khác, log serializer hoặc mapper khác vẫn có thể lộ trường. DTO rõ ràng giúp kiểm soát contract tốt hơn.

Với trường nhạy cảm, cân nhắc:

- Chỉ trả khi caller có permission cụ thể.
- Mask một phần khi không cần giá trị đầy đủ.
- Không đưa vào response mặc định.
- Phân tách endpoint có quyền cao.
- Kiểm tra cả export, download và bulk API.

## 15. Mã hóa, hashing và tokenization

Không phải mọi dữ liệu nhạy cảm đều được bảo vệ bằng cùng một kỹ thuật.

| Loại dữ liệu | Cách bảo vệ thường phù hợp |
|---|---|
| Password | Hash một chiều có salt bằng thuật toán chuyên dụng như Argon2id hoặc BCrypt |
| API key/secret cần xác minh | Lưu hash/HMAC nếu không cần khôi phục giá trị |
| PII cần đọc lại | Mã hóa có thể giải mã, quản lý key riêng |
| Số định danh cần tìm kiếm chính xác | Cân nhắc HMAC/blind index riêng, đánh giá rò rỉ equality |
| Payment data | Dùng tokenization và dịch vụ chuyên biệt theo yêu cầu hệ thống |
| Dữ liệu không cần thiết | Không thu thập hoặc xóa theo retention policy |

Hashing và encryption khác nhau:

- Hashing một chiều phù hợp khi cần xác minh nhưng không cần lấy lại giá trị gốc.
- Encryption có thể giải mã, cần quản lý key và quyền truy cập.
- Tokenization thay giá trị nhạy cảm bằng token, dữ liệu gốc được giữ ở hệ thống được kiểm soát.

Không mã hóa password bằng reversible encryption để có thể đọc lại. Không dùng MD5/SHA-1 hoặc hash nhanh không có salt làm password storage.

### 15.1. Mã hóa ở tầng truyền tải và lưu trữ

Các lớp thường cần xem xét:

- TLS giữa client và API.
- TLS giữa application và database khi môi trường yêu cầu.
- Encryption at rest của storage/database.
- Application-level field encryption cho trường có yêu cầu riêng.
- Key management qua KMS/HSM hoặc secret manager.
- Rotation và versioning của key.

Encryption at rest không ngăn một user đã có quyền đọc database qua ứng dụng truy cập mọi plaintext mà application giải mã. Authorization và field-level access vẫn cần thiết.

### 15.2. Quản lý encryption key

Không lưu key mã hóa cùng bảng hoặc source code chứa ciphertext. Với envelope encryption, ứng dụng có thể dùng data encryption key để mã hóa dữ liệu và key encryption key trong KMS để bảo vệ data key.

Cần xác định:

- Ai được phép yêu cầu decrypt?
- Key rotation diễn ra thế nào?
- Dữ liệu cũ được re-encrypt khi nào?
- Nếu KMS tạm thời không khả dụng, hành vi ứng dụng là gì?
- Backup/restore có giữ khả năng giải mã không?
- Có audit mỗi lần truy cập key không?

Mất key có thể làm dữ liệu không thể khôi phục. Quản lý key và backup phải được kiểm thử như một phần của kế hoạch vận hành.

## 16. Bảo vệ trường nhạy cảm khi tìm kiếm

Mã hóa randomized thông thường làm cùng một plaintext tạo ciphertext khác nhau, vì vậy không thể dùng equality index đơn giản để tìm kiếm. Deterministic encryption hoặc blind index có thể hỗ trợ một số dạng lookup nhưng làm lộ thông tin về equality/frequency.

Một pattern là lưu ciphertext và một HMAC/blind index riêng:

~~~text
sensitive_value_ciphertext
sensitive_value_lookup_hmac
encryption_key_version
~~~

Lookup HMAC phải dùng key riêng và canonicalization nhất quán. Không dùng HMAC key trùng encryption key. Phải đánh giá rủi ro dò dictionary nếu miền giá trị nhỏ, ví dụ mã vùng hoặc trạng thái.

Không thiết kế searchable encryption chỉ vì muốn giữ nguyên query cũ. Trước tiên xác định nhu cầu tìm kiếm thật, threat model và mức rò rỉ có thể chấp nhận. Có thể dùng tokenization hoặc service chuyên trách nếu yêu cầu phức tạp.

## 17. SQL injection và dynamic query

R2DBC hỗ trợ bind parameter. Luôn bind giá trị dữ liệu:

~~~java
return databaseClient.sql("""
        SELECT id, title
        FROM documents
        WHERE tenant_id = :tenantId
          AND owner_id = :ownerId
          AND status = :status
        """)
        .bind("tenantId", tenantId)
        .bind("ownerId", ownerId)
        .bind("status", status)
        .fetch()
        .all();
~~~

Không nối trực tiếp input vào SQL:

~~~java
// Không làm như vậy:
String sql = "SELECT * FROM documents WHERE title = '" + title + "'";
~~~

Bind parameter không thể thay thế tên bảng, tên cột hoặc từ khóa SQL tùy ý. Nếu cần sort động, ánh xạ lựa chọn client sang danh sách identifier được phép:

~~~java
String orderColumn = switch (sortField) {
    case "createdAt" -> "created_at";
    case "title" -> "title";
    default -> "created_at";
};
~~~

Chỉ dùng giá trị identifier từ allowlist nội bộ. Không đưa nguyên sortField vào câu SQL. Đồng thời, tenant/owner predicate phải luôn có mặt trong query được xây dựng.

## 18. Bảo vệ thông tin trong log, trace và metrics

Dữ liệu có thể bị lộ ngoài response, đặc biệt qua log và observability.

Không ghi log:

- Password, access token, refresh token hoặc API key.
- Session cookie hoặc Authorization header.
- Full payment credential.
- Nội dung PII không cần cho điều tra.
- Toàn bộ request/response body theo mặc định.
- Bind parameter nhạy cảm.
- Ciphertext cùng key hoặc thông tin đủ để giải mã.

Log nên ghi operation và metadata cần thiết:

~~~text
event=document.read
actor_id=user-42
tenant_id=tenant-7
resource_id=doc-900
outcome=denied
correlation_id=req-abc
~~~

Ví dụ chỉ minh họa cấu trúc log. Chỉ ghi identifier nếu chính sách dữ liệu cho phép; có thể dùng ID đã pseudonymize hoặc correlation token.

Metrics cần tag có cardinality thấp. Không dùng email, user ID, tenant ID không giới hạn hoặc resource ID làm label. Trace có thể mang correlation ID nhưng cần kiểm soát quyền truy cập và retention của tracing backend.

Cấu hình exception logging cũng cần chú ý. Một exception có thể chứa SQL, bind value hoặc nội dung dữ liệu. Không log toàn bộ object/stack context nhạy cảm ra nơi có nhiều người truy cập.

## 19. Database role và least privilege

Ứng dụng runtime nên dùng database role với quyền tối thiểu cần thiết.

Ví dụ phân tách:

| Role | Quyền điển hình |
|---|---|
| app_runtime | SELECT/INSERT/UPDATE/DELETE trên bảng cần thiết |
| app_migrator | DDL cần thiết để chạy migration |
| app_readonly | SELECT cho tác vụ đọc/report được giới hạn |
| app_auditor | SELECT audit log theo quyền vận hành |
| app_admin | Quyền quản trị đặc biệt, dùng có kiểm soát |

Không dùng superuser hoặc owner role cho connection pool của ứng dụng. Nếu dùng PostgreSQL RLS, runtime role không nên có BYPASSRLS; cần kiểm tra quyền thực tế thay vì chỉ nhìn tên role.

Migration job có thể dùng credential DDL riêng. Không cần cấp CREATE/ALTER/DROP cho ứng dụng runtime nếu ứng dụng không thực hiện schema migration.

Secret database phải được lấy từ secret manager hoặc môi trường triển khai, không commit password vào repository hay log startup.

## 20. Soft delete và quyền truy cập

Soft delete thường thêm các trường như deleted_at, deleted_by hoặc is_deleted. Nó hữu ích khi cần khôi phục hoặc lưu lịch sử, nhưng không tự động bảo vệ dữ liệu.

Mọi query thông thường cần lọc bản ghi chưa xóa:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL;
~~~

Cần xác định:

- User nào được xem bản ghi đã xóa?
- Ai được khôi phục?
- Xóa mềm có tạo audit event không?
- Bản ghi đã xóa còn xuất hiện trong search/export không?
- Khi nào dữ liệu bị purge vật lý?
- Retention có áp dụng cho backup và audit log không?

Không coi deleted_at là biện pháp bảo mật. Người dùng không được phép truy cập vẫn phải bị authorization từ chối, kể cả row chưa bị xóa.

## 21. Audit log và quyền truy cập audit log

Audit log có thể chứa thông tin nhạy cảm về hành vi người dùng. Quyền đọc audit log thường cần chặt chẽ hơn quyền đọc dữ liệu nghiệp vụ thông thường.

Hãy xác định:

- Ai được xem audit event?
- Có cần giới hạn theo tenant không?
- Có cần che actor/resource identifier không?
- Ai được export?
- Audit log được lưu bao lâu?
- Ai có thể xóa hoặc sửa?
- Có lưu truy cập audit log hay không?

Không để user tự đọc audit log chỉ vì họ sở hữu bản ghi nghiệp vụ. Quyền xem lịch sử có thể là permission riêng.

Nếu cần bằng chứng không thể phủ nhận, audit event nên có timestamp đáng tin cậy, actor đã xác thực, action/resource rõ, correlation ID và storage có quyền sửa hạn chế. Không ghi dữ liệu nhạy cảm vào before/after snapshot nếu không có yêu cầu và biện pháp bảo vệ phù hợp.

## 22. Kiểm thử auditing

Auditing cần được kiểm tra qua Spring Data mapping và reactive context.

Các trường hợp nên có:

- Khi insert, createdBy và createdAt được điền.
- Khi update, updatedBy và updatedAt được cập nhật.
- createdBy và createdAt không bị ghi đè ngoài ý muốn khi update.
- Không có Authentication thì hành vi actor field đúng với chính sách.
- Background job ghi actor service/job.
- Thời gian được lưu và đọc đúng timezone/precision.
- Custom EntityCallback không làm mất auditing callback.
- Bulk/native SQL có hành vi auditing đã được định nghĩa rõ.

Test trực tiếp converter hoặc callback không đủ chứng minh toàn bộ Spring configuration đã kích hoạt. Nên có integration test khởi động context với @EnableR2dbcAuditing và database R2DBC.

Với test reactive security, có thể đặt Authentication vào Reactor Context trong publisher test. Không giả định annotation test imperative tự động truyền context vào mọi publisher tùy chỉnh.

## 23. Kiểm thử row-level authorization

Tạo ít nhất hai tenant hoặc hai user với dữ liệu tách biệt:

~~~text
Tenant A
  - User A1 owns Document A1
  - User A2 owns Document A2

Tenant B
  - User B1 owns Document B1
~~~

Các tình huống cần kiểm tra:

| Tình huống | Kết quả mong đợi |
|---|---|
| A1 đọc bản ghi A1 | Cho phép |
| A1 đọc bản ghi A2 khi chỉ owner được đọc | Từ chối/ẩn theo API policy |
| A1 đọc bản ghi B1 | Từ chối |
| A1 cập nhật bản ghi B1 | Không có row bị thay đổi |
| A1 xóa bản ghi B1 | Không có row bị xóa |
| Client gửi tenant B khi actor chỉ thuộc tenant A | Từ chối |
| Query list/export thiếu owner scope | Test phải phát hiện |
| Background job chạy tenant A | Chỉ tác động dữ liệu A |
| Tenant context không được đặt khi RLS bật | Không truy cập được row |

Kiểm tra cả SELECT, UPDATE, DELETE, count, pagination, search, export và native SQL. Một endpoint list an toàn không bảo đảm endpoint detail hoặc bulk update an toàn.

### 23.1. Kiểm thử PostgreSQL RLS bằng runtime role

Nếu dùng RLS, test phải kết nối bằng role tương tự ứng dụng runtime. Test chạy bằng superuser hoặc table owner có thể bỏ qua policy và tạo kết quả sai lệch.

Kiểm tra:

- RLS bật trên đúng bảng.
- Runtime role không bypass RLS.
- Tenant context được đặt trong cùng transaction.
- Connection được trả pool không giữ tenant context cũ.
- Policy USING và WITH CHECK chặn cả đọc lẫn ghi.
- Nhiều policy không vô tình mở rộng quyền.
- Background job đặt tenant đúng.

H2 không thay thế được kiểm thử PostgreSQL RLS. Dùng Testcontainers hoặc database test PostgreSQL thật cho các policy này.

## 24. Kiểm thử dữ liệu nhạy cảm và response contract

Viết test cho DTO/serialization để xác nhận trường không được phép không xuất hiện:

- Password hash không được trả ra API.
- Token/secret không xuất hiện trong response.
- PII chỉ xuất hiện khi endpoint và permission cho phép.
- Masking hoạt động đúng.
- Error response không chứa SQL/bind parameter.
- Audit/log không chứa dữ liệu nhạy cảm bị cấm.
- Export và file download có cùng quy tắc authorization.

Không chỉ test JSON response chính. Kiểm tra cả log appender/test sink nếu có yêu cầu chống rò rỉ, và kiểm tra tracing/logging configuration ở môi trường tích hợp.

## 25. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| createdBy luôn null | Chưa bật auditing hoặc không có auditor | Kiểm tra @EnableR2dbcAuditing và ReactiveAuditorAware |
| updatedBy là user sai | Lấy actor từ input không đáng tin hoặc context sai | Lấy từ identity đã xác thực |
| Auditing hoạt động trong HTTP nhưng không có trong job | Background publisher không có actor context | Định nghĩa service/job actor rõ ràng |
| Entity callback không chạy với native SQL | Đường SQL tùy chỉnh bỏ qua lifecycle mapping | Ghi auditing tường minh hoặc dùng cơ chế phù hợp |
| User đổi ID để đọc row khác | Query không có tenant/owner predicate | Scope mọi thao tác dữ liệu |
| List đã lọc nhưng update vẫn sửa row khác tenant | UPDATE thiếu predicate | Thêm scope vào UPDATE/DELETE và kiểm thử |
| RLS không chặn runtime | Role owner/superuser/BYPASSRLS hoặc policy sai | Kiểm tra role và policy bằng credential runtime |
| Tenant A nhìn thấy dữ liệu B sau khi reuse connection | Dùng session-level tenant setting | Dùng transaction-local context và cùng connection |
| createdBy bị client giả mạo | Entity bind trực tiếp request body | Dùng DTO và actor từ security context |
| Secret xuất hiện trong log | Log toàn bộ request/entity/exception | Mask/redact và giới hạn log field |
| Password có thể giải mã | Dùng encryption thay vì password hashing | Dùng password hash chuyên dụng |
| Audit trail thiếu event sau commit | Gửi event ngoài transaction không đáng tin cậy | Dùng transactional outbox khi cần atomicity |
| Audit log có thể bị sửa bởi runtime | Runtime role có UPDATE/DELETE | Tách quyền append/read và vận hành |
| DTO lộ trường nội bộ | Trả entity trực tiếp | Dùng response DTO allowlist |

## 26. Checklist triển khai

### Auditing

- [ ] Bật @EnableR2dbcAuditing.
- [ ] Khai báo @CreatedBy, @CreatedDate, @LastModifiedBy, @LastModifiedDate phù hợp.
- [ ] Cung cấp ReactiveAuditorAware nếu cần actor.
- [ ] Lấy actor từ identity đã xác thực.
- [ ] Không dùng ThreadLocal hoặc block() trong reactive auditor.
- [ ] Xác định actor cho job/service account.
- [ ] Dùng kiểu thời gian và timezone nhất quán.
- [ ] Thiết kế audit trail riêng nếu cần lịch sử đầy đủ.

### Row-level authorization

- [ ] Tenant/owner scope đến từ context đã xác minh.
- [ ] SELECT, UPDATE, DELETE đều có scope.
- [ ] Search, count, pagination và export có cùng policy.
- [ ] Không tin ID hoặc tenant ID do client gửi.
- [ ] Có constraint/index hỗ trợ tenant isolation.
- [ ] Đã đánh giá PostgreSQL RLS nếu cần defense in depth.
- [ ] Runtime role không bypass RLS.
- [ ] Tenant context được đặt transaction-local.
- [ ] Có test truy cập chéo tenant/owner.

### Sensitive data

- [ ] Chỉ thu thập trường thực sự cần.
- [ ] Response dùng DTO allowlist.
- [ ] Password dùng password hashing chuyên dụng.
- [ ] Trường cần đọc lại được mã hóa và key quản lý riêng.
- [ ] TLS và encryption at rest được cấu hình phù hợp.
- [ ] Secret không nằm trong source/log.
- [ ] SQL dùng bind parameter.
- [ ] Dynamic identifier dùng allowlist.
- [ ] Log, trace, metrics không chứa PII/secret không cần thiết.
- [ ] Có retention, purge và backup policy.
- [ ] Quyền đọc/export audit log được giới hạn.

## 27. Kết luận

Trong Spring Data R2DBC, auditing, row-level authorization và bảo vệ thông tin nhạy cảm là ba lớp trách nhiệm khác nhau. Spring Data auditing có thể tự điền actor và timestamp qua @CreatedBy, @CreatedDate, @LastModifiedBy, @LastModifiedDate, @EnableR2dbcAuditing và ReactiveAuditorAware. Với ứng dụng reactive, actor nên được lấy từ SecurityContext trong Reactor Context hoặc một actor context đáng tin cậy dành cho job.

Phân quyền bản ghi cần được áp dụng ở mọi thao tác dữ liệu. Tenant/owner phải được xác minh từ server context, rồi đưa vào SELECT, UPDATE, DELETE, search và export. PostgreSQL RLS có thể tạo thêm lớp bảo vệ, nhưng cần cấu hình runtime role, policy và transaction-local tenant context chính xác. Auditing metadata không thay thế audit trail đầy đủ; khi cần lịch sử bất biến hoặc phát sự kiện đáng tin cậy, hãy thiết kế audit/outbox riêng.

Thông tin nhạy cảm cần được bảo vệ từ lúc thu thập, lưu trữ, truy vấn, serialize, logging đến retention. Dùng DTO allowlist, hashing cho password, encryption/tokenization cho dữ liệu cần bảo vệ, quản lý key an toàn, least-privilege database role và log redaction. Cuối cùng, kiểm thử auditing, truy cập chéo tenant, RLS, response masking và audit event trên database/driver phù hợp. Những lớp bảo vệ chỉ đáng tin cậy khi được thực thi ở server và có test chứng minh từng đường truy cập.

