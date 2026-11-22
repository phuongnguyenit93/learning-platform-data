# Tránh khác biệt giữa thời điểm kiểm tra quyền với thời điểm sử dụng dữ liệu

## 1. Vấn đề cốt lõi: quyền đúng ở T1 chưa chắc còn đúng ở T2

Trong hệ thống Spring Security, một phương thức có thể kiểm tra rằng người dùng được sửa tài liệu, sau đó đọc dữ liệu, tính toán, gọi service khác và cuối cùng mới lưu. Giữa **thời điểm kiểm tra (time of check, T1)** và **thời điểm sử dụng hoặc ghi (time of use, T2)**, những thông tin quyết định quyền có thể thay đổi.

Đây là lỗi **TOCTOU — Time of Check to Time of Use**, một dạng race condition. Nó đặc biệt nguy hiểm với **phân quyền trên dữ liệu**, vì object ID, owner, tenant, ACL, membership và trạng thái tài nguyên là những thuộc tính có thể đổi cùng lúc bởi nhiều request, worker hoặc administrator.

~~~text
T1: Alice có quyền WRITE trên Document #42
          |
          +--> Admin thu hồi quyền / chuyển owner / khóa tài liệu
          |
T2: Alice vẫn UPDATE Document #42 bằng quyết định cũ
~~~

Một `@PreAuthorize` chạy thành công tại T1 không phải một “vé bất biến” cho mọi hành động ở T2. Ngược lại, một `@Transactional` bao quanh use case cũng **không tự bảo đảm** quyền không thể đổi: hiệu lực của transaction còn phụ thuộc isolation level, đối tượng được khóa, nơi lưu quyền và cách cập nhật.

**Mục tiêu thiết kế:** xác định rõ thời điểm quyết định quyền phải có hiệu lực; giảm hoặc loại bỏ khoảng cách giữa kiểm tra và thao tác bằng **atomic conditional operation**, **optimistic locking**, **pessimistic locking** hoặc **giao thức nhất quán phù hợp**. Khi không thể đạt tính nguyên tử, phải công khai giới hạn bảo đảm, dùng expiry/recheck và fail-closed theo rủi ro.

Bài Knowledge này trình bày nguyên nhân, các mức bảo đảm, mẫu SQL/JPA/Spring Security, quyền lưu ở DB so với service ngoài, ảnh hưởng đến read/write/delete/download/message, ví dụ Java 17 và cách test race condition có thể lặp lại.

## 2. Ba “đồng hồ” cần phân biệt

Không phải mọi mốc thời gian đều giống nhau:

| Mốc | Điều xảy ra | Câu hỏi |
|---|---|---|
| **T_authn** | Xác thực danh tính, tạo Authentication/token/session | Danh tính còn hợp lệ không, token có chứa quyền cũ? |
| **T_check** | Đánh giá policy: authority, tenant, owner, ACL, resource state | Có đủ bằng chứng cho thao tác này không? |
| **T_use** | Đọc/ghi/xóa, tải file, phát event, gọi API ngoài | Quyền được kiểm tra có còn hợp lệ đối với hành động thực tế? |

Ngoài ra còn **T_commit**, khi database transaction commit, và **T_delivery**, khi event/file/link được nhận bởi hệ bên ngoài. Một thao tác có side effect có thể kéo dài nhiều giai đoạn.

Ví dụ một API trả `200 OK` sau khi xuất một presigned URL tải file: kiểm tra quyền khi **phát URL** không nhất thiết đồng nghĩa quyền sẽ được kiểm tra lại khi người nhận URL dùng nó sau một giờ. Tương tự, sự kiện được enqueue khi actor có quyền nhưng được xử lý ngày hôm sau có thể không còn đúng policy.

Hãy viết hợp đồng:
- Quyền được xét **tại lúc bắt đầu yêu cầu**, **lúc phát sinh mỗi mutation**, hay **lúc commit**?
- Quyền có bị thu hồi ngay tức thì hay sau một cửa sổ nhất quán có công bố?
- Với thao tác chạy lâu, có cần kiểm tra lại trước side effect không thể hoàn tác?
- Chính sách từ chối khi thiếu/không xác định/quyền bị thu hồi là gì?

Không có một định nghĩa duy nhất cho mọi sản phẩm. Sai lầm là không định nghĩa rồi giả định “đã check trước đó” luôn đủ.

## 3. Những thuộc tính gây TOCTOU thường gặp

| Thuộc tính thay đổi | Ví dụ thay đổi giữa check và use | Hậu quả tiềm ẩn |
|---|---|---|
| Owner | Tài liệu chuyển từ An sang Bình | An sửa sau khi mất quyền owner |
| Tenant | Document chuyển sang tenant khác | Truy cập hoặc ghi xuyên tenant |
| Direct ACL/share | Grant WRITE bị revoke | Người nhận vẫn sửa theo kết quả cũ |
| Group membership | User rời nhóm project-review | Quyền nhóm cũ vẫn cho đọc |
| Role/authority | Admin bị hạ quyền | Token/cache chứa role cũ vẫn được dùng |
| Resource status | Tài liệu chuyển sang LOCKED/ARCHIVED | Ghi vào tài liệu đã khóa |
| Data version | Tài liệu bị người khác sửa | Lost update, cập nhật trên dữ liệu cũ |
| Business threshold | Hạn mức, giá, số dư, inventory thay đổi | Một quyết định phù hợp lúc trước trở nên sai |
| Session/token | Token bị thu hồi, kết thúc phiên | Tác vụ bất đồng bộ vẫn mang identity cũ |
| Policy version | Rule được đổi để siết quyền | Cache quyết định ALLOW lỗi thời |
| File/link expiry | Link download còn tồn tại sau revoke | Nội dung tiếp tục được tải |

**Hai lớp race khác nhau:**
1. **Race dữ liệu:** người khác sửa document sau khi ta đọc; giải quyết bằng version/locking hoặc transaction isolation.
2. **Race quyền:** quyền của actor trên document thay đổi; version chỉ của document **không đủ** nếu grant/ACL nằm ở bảng hoặc hệ khác và không cùng được version hóa/khóa.

Không chỉ kiểm tra một loại race rồi kết luận toàn bộ authorization đã an toàn.

## 4. Antipattern: check trước, ghi bằng ID trần

Ví dụ dễ mắc:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public void rename(long documentId, String title) {
    if (!documentPolicy.canWrite(currentActor(), documentId)) {
        throw new AccessDeniedException("Denied");
    }

    expensiveCalculation();
    documentRepository.updateTitleById(documentId, title);
}
~~~

Đây là **mẫu lỗi**, không phải implementation khuyến nghị. Policy có thể xác nhận tại T1, nhưng sau `expensiveCalculation()` quyền của user đã bị thu hồi hoặc document đã chuyển owner. `updateTitleById` chỉ cần ID nên bỏ qua mọi thông tin quyền cũ/mới.

Ngay cả khi thêm `@Transactional` lên method, cần kiểm tra:
- `documentPolicy.canWrite` có đọc từ **cùng database và transaction** hay không?
- Permission row có bị transaction khác cập nhật trước khi `UPDATE` không?
- Isolation level có cho transaction thấy ACL mới hoặc lock nào ngăn thay đổi trái ý muốn?
- Nếu policy service ở ngoài DB, `@Transactional` có kiểm soát được service đó không?
- Lời gọi có qua Spring proxy để transaction và method security thật sự chạy không?

Một đoạn tốt hơn về cấu trúc sẽ không coi kết quả boolean check ban đầu là điều kiện duy nhất. Các predicate quan trọng được đưa **vào cùng thao tác ghi hoặc được bảo vệ bởi protocol khóa/version phù hợp**.

## 5. Mức bảo đảm: “giảm cửa sổ” khác “loại bỏ race”

| Cách làm | Điều đạt được | Chưa bảo đảm điều gì? |
|---|---|---|
| Check ở controller, ghi sau | Có quyết định đầu vào | Không bảo vệ trước revoke/owner change sau check |
| Check lại ngay trước save | Thu hẹp khoảng cách | Hai thao tác riêng vẫn có race |
| `@Transactional` cùng một database | Gộp thao tác theo ranh giới commit/rollback | Không tự khóa ACL/owner hoặc đảm bảo snapshot phù hợp |
| `WHERE id AND tenant AND owner AND status` trong UPDATE | Predicate trên record được kiểm tra như một phần statement | Quyền ở bảng ngoài có thể đổi; DB isolation vẫn quan trọng |
| Guard version bằng `@Version` hoặc `WHERE version=:v` | Phát hiện thay đổi của record được version hóa | Không biết ACL trong bảng khác đã đổi nếu không tăng version liên quan |
| Lock document row + permission rows | Có thể tuần tự hóa các thay đổi quan trọng theo protocol khóa | Không giúp nếu luồng revoke không dùng cùng lock/protocol |
| SERIALIZABLE transaction | Một số anomaly bị phát hiện/transaction bị retry theo DB | Không bao gồm hệ ngoài, cần xử lý retry và tác động không giao dịch |
| Short-lived capability/recheck ở worker | Giới hạn thời gian dùng quyết định cũ | Không bảo đảm revoke tức thì nếu token vẫn hợp lệ |
| Policy service có version/revocation protocol | Có thể bảo đảm mức nhất quán theo hợp đồng riêng | Chỉ đúng nếu mọi consumer tuân thủ protocol |

Không có câu “dùng isolation SERIALIZABLE là hết TOCTOU” cho mọi hệ thống. Sự bảo đảm phụ thuộc **dữ liệu và nơi có side effect** nằm trong transaction nào, DB nào, và các luồng ghi quyền có cùng tham gia giao thức đồng bộ hay không.

## 6. Cách đơn giản nhất: UPDATE kèm ràng buộc quyền trên chính record

Giả sử chỉ owner thuộc tenant được đổi tiêu đề, tài liệu đang editable và record có version.

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :verified_tenant
  AND owner_user_id = :verified_actor
  AND editable = TRUE
  AND version = :expected_version;
~~~

Ở đây **tất cả điều kiện được kiểm tra trong chính statement cập nhật**, không có một bước `findById` rồi save không giới hạn. Với database có semantics UPDATE bình thường, thao tác chỉ ghi những row thỏa predicate trong execution của câu lệnh theo isolation/concurrency control của DB.

Cần đọc kết quả:
- **1 row updated:** một document thỏa tất cả predicate và được cập nhật.
- **0 row updated:** sai ID, sai tenant, sai owner, đã khóa hoặc version đã thay đổi. Không coi là thành công.
- **Nhiều hơn 1:** bất thường nếu ID đúng là duy nhất; phải kiểm tra schema/query và không báo thành công tùy tiện.

**Không được dùng `owner_user_id=:ownerFromRequest`**, vì client có thể giả owner. `verified_tenant` và `verified_actor` phải lấy từ identity đã xác thực phía server.

**Điều kiện quyết định quyền trên record phải nằm cùng statement** nếu muốn tránh tình huống check owner T1, owner đổi T2, ghi T3. Nếu chính sách còn phụ thuộc ACL/share ở bảng khác, cần giải pháp bổ sung, không chỉ guard owner.

## 7. Triển khai Spring Data JPA @Modifying

Entity minh họa có các thuộc tính:
- `id: Long`, `tenantId: String`, `ownerUserId: String`.
- `editable: boolean`, `title: String`.
- `version: long`, có thể đánh dấu `@Version` để quản lý optimistic lock trong các luồng entity.

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    @Modifying
    @Query("""
        update Document d
           set d.title = :title,
               d.version = d.version + 1
         where d.id = :id
           and d.tenantId = :tenant
           and d.ownerUserId = :actor
           and d.editable = true
           and d.version = :expectedVersion
        """)
    int renameIfOwnerAndVersion(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("actor") String actor,
            @Param("title") String title,
            @Param("expectedVersion") long expectedVersion);
}
~~~

Đây là **code tích hợp Spring Data JPA**, không phải chương trình chạy độc lập. Các property JPQL phải trùng model thực. Method `@Modifying` khai báo rõ update query; cần transaction ghi bao quanh việc gọi. `@Modifying` với `@Query` không tự tạo transaction theo ý muốn của use case.

Service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository documents;
    private final VerifiedActorResolver actors;

    public DocumentCommandService(
            DocumentRepository documents, VerifiedActorResolver actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
    @Transactional
    public void rename(Long id, String title, long expectedVersion) {
        VerifiedActor actor = actors.requireCurrent();

        if (id == null || id <= 0
                || title == null || title.isBlank()) {
            throw new IllegalArgumentException("Invalid rename request");
        }

        int rows = documents.renameIfOwnerAndVersion(
                id, actor.tenantId(), actor.userId(),
                title, expectedVersion);

        if (rows != 1) {
            throw new ScopedUpdateRejectedException();
        }
    }
}
~~~

`VerifiedActorResolver`, `VerifiedActor` và `ScopedUpdateRejectedException` là kiểu của ứng dụng cần định nghĩa. Resolver phải lấy danh tính và tenant từ nguồn đã xác thực. Annotation `@PreAuthorize` chặn quyền chức năng, còn **UPDATE** kiểm tra ownership thực tế ở thời điểm statement.

**Lưu ý JPA:** bulk JPQL update không đi qua toàn bộ cơ chế dirty checking, optimistic locking và entity callbacks của một managed entity theo cùng cách với `save`; vì vậy code trên **chủ động** thêm điều kiện/increment version. Bulk update cũng có thể khiến entity trong persistence context đang giữ dữ liệu cũ. Đừng tùy tiện bật `clearAutomatically` nếu có thay đổi chưa flush; thiết kế transaction và persistence context theo workload.

## 8. Tránh rò rỉ qua kết quả 0 row

Một câu UPDATE có các guard trả 0 row nhưng không cho biết nguyên nhân. Nó có thể là:
- Document ID không tồn tại.
- Document ở tenant khác.
- Actor không còn là owner.
- Document bị khóa.
- Client dùng version cũ.

Không nên lập tức gọi lại `repository.findById(id)` **không scoped** chỉ để phân biệt lý do rồi trả message chứa owner hay tenant thật cho caller trái quyền.

Một hợp đồng response có thể là:
- 404 nếu document không tồn tại **trong tập actor được phép nhìn thấy**.
- 409 nếu đã xác nhận actor có quyền thấy resource và version bị stale.
- 403 nếu chính sách cố tình cho biết actor thiếu quyền, không lộ thông tin trái phép.
- 5xx nếu database/policy backend lỗi.

Chọn theo API và mức độ chống dò ID. Quan trọng là **không trả 200/204 khi affected rows = 0** và không log nội dung document ngoài scope.

## 9. Optimistic locking với @Version: chặn mất cập nhật dữ liệu

Một entity JPA có:

~~~java
@Entity
public class Document {
    @Id
    private Long id;

    @Version
    private long version;

    private String tenantId;
    private String ownerUserId;
    private String title;
}
~~~

Đây là **mảnh ghép entity**, cần các import JPA, constructors/mapping và logic domain thích hợp. Khi hai transaction cùng đọc version cũ rồi cùng cố ghi một managed entity, JPA provider thường phát hiện optimistic locking conflict nếu version đã bị tăng bởi ghi trước, thay vì lặng lẽ ghi đè.

Với lỗi concurrency, một API thường trả 409 hoặc yêu cầu client tải phiên bản mới rồi thực hiện lại theo điều kiện phù hợp. Không tự retry vô hạn với snapshot cũ và một quyết định quyền cũ.

**Nhưng @Version không tự chặn việc thu hồi quyền trong bảng khác.**

Ví dụ:
~~~text
Document #42.version = 5
document_grants: Alice WRITE=true

T1: Alice đọc Document version=5
T2: admin thu hồi Alice WRITE trong document_grants
T3: Alice ghi Document version=5
~~~

Nếu `documents.version` **không được tăng khi grant thay đổi**, optimistic locking trên Document có thể không biết T2. Phải thiết kế:
- Version của permission/ACL và check nó cùng thao tác ghi;
- Lock các row liên quan;
- Một protocol revocation thay đổi chung một guard/version trên Document;
- Hoặc semantics nhất quán được xác định theo DB isolation/transaction.

Đừng quảng bá `@Version` là giải pháp “chặn mọi permission race” chỉ vì nó xử lý lost updates.

## 10. Nếu quyền lưu ở bảng grant: dùng EXISTS nhưng phải hiểu concurrency

Với direct share WRITE, truy vấn PostgreSQL minh họa:

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND editable = TRUE
  AND version = :expected_version
  AND (
      owner_user_id = :verified_actor
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = documents.id
            AND g.grantee_user_id = :verified_actor
            AND g.permission = 'WRITE'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

Đây là **mẫu PostgreSQL**; điều chỉnh theo dialect thực tế. Chỉ sử dụng `:now` từ đồng hồ server, không cho client quyết định expiry. Tất cả ID/tenant/action scope nằm trong cùng statement. `EXISTS` tránh nhân đôi target row khi nhiều grant.

Điều quan trọng: khi transaction thu hồi grant chạy **đồng thời**, một statement UPDATE và một DELETE/UPDATE grant có thể quan sát snapshot và lock khác nhau tùy database/isolation. Đưa `EXISTS` vào cùng statement giúp tránh khoảng cách tách biệt ở application layer, nhưng **không tự chứng minh revocation lập tức thắng mọi giao dịch đang chạy**.

Cần chọn “thời điểm hiệu lực” cụ thể: ví dụ, một update đã bắt đầu và lấy snapshot hợp lệ **trước khi** revoke commit có được phép hoàn tất không? Nếu yêu cầu chính sách là “sau khi revoke commit, không mutation nào của actor cũ được commit nữa”, cần thiết kế synchronization/serialization protocol nghiêm ngặt hơn.

Không nên hứa bảo đảm mạnh khi chỉ đọc predicate ở isolation `READ_COMMITTED` mà chưa kiểm chứng interleaving cụ thể của DB.

## 11. Pessimistic locking: khóa đúng hàng và đúng quy trình

Khi quyền owner/status nằm trên chính document row, có thể chọn `PESSIMISTIC_WRITE` để đọc/kiểm tra/sửa trong transaction:

~~~java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface DocumentLockingRepository
        extends JpaRepository<Document, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select d from Document d
        where d.id = :id
          and d.tenantId = :tenant
        """)
    Optional<Document> lockByIdAndTenant(
            @Param("id") Long id,
            @Param("tenant") String tenant);
}
~~~

Một use case có thể:
1. Bắt đầu transaction trên Spring-managed service.
2. Lấy document bằng query scoped kèm lock.
3. Kiểm tra owner, editable, trạng thái và business rules khi đã giữ lock.
4. Mutate managed entity.
5. Commit, rồi giải phóng lock theo semantics DB.

**Cần bảo đảm luồng chuyển owner/khóa tài liệu cũng đồng bộ trên chính document row.** Nếu một service khác sửa ACL trong bảng `document_grants` nhưng không khóa cùng tài nguyên, `PESSIMISTIC_WRITE` trên document **không bảo vệ quyền ở bảng grant**.

Nếu muốn tuần tự hóa grant/revoke và write dựa trên grant, một protocol có thể buộc cả hai luồng khóa **document row làm mutex chung trước** khi đọc/sửa grants, rồi cập nhật/commit. Khi làm vậy phải:
- Giữ thứ tự lấy lock nhất quán, tránh deadlock.
- Ràng buộc mọi writer/revoker đều tuân thủ protocol; một API bỏ lock sẽ phá bảo đảm.
- Chọn timeout, deadlock handling và retry an toàn.
- Test trên database dialect production.
- Cân nhắc throughput và thời gian giữ lock; không thực hiện network call lâu khi đang giữ lock nếu có thể tránh.

**Chỉ đọc có lock rồi trả object cho code sử dụng sau commit không còn được bảo vệ** bởi lock đó. Ranh giới transaction và side effect phải cùng được xét.

## 12. Isolation levels và semantics thực tế

Spring cung cấp `Isolation.READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`... nhưng ý nghĩa chính xác và cơ chế locking/snapshot phụ thuộc hệ quản trị cơ sở dữ liệu.

| Mức | Đặc tính khái quát | Lưu ý cho authorization TOCTOU |
|---|---|---|
| READ_COMMITTED | Mỗi statement thường thấy dữ liệu đã commit phù hợp quy tắc DB | Hai câu check và update có thể quan sát trạng thái khác nhau |
| REPEATABLE_READ | Snapshot/đọc lặp lại có độ ổn định cao hơn tùy DB | Thấy cùng dữ liệu cũ không đồng nghĩa quyền chưa bị revoke |
| SERIALIZABLE | Transaction đồng thời phải tương đương một thứ tự tuần tự theo bảo đảm DB | Có thể abort/retry; không điều phối service bên ngoài DB |

Một ví dụ Spring:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void sensitiveUpdate(...) {
    // Scoped authorization + mutation trên DB và transaction thích hợp.
}
~~~

Đây là snippet, không phải lời khuyên bật SERIALIZABLE toàn hệ thống. Mức isolation cao hơn có thể gây contention và lỗi serialization cần retry. Nếu policy chỉ nằm trên external OPA service, transaction SQL không biến external response thành dữ liệu transactional.

Một vấn đề tinh tế: nếu transaction có snapshot đã cũ, nó có thể **hợp lệ theo thứ tự serializable** nhưng không thỏa kỳ vọng “revocation đã commit trước khi update commit phải thắng”. Để bảo đảm realtime ordering chặt hơn, cần xác định điểm tuyến tính hóa giữa revoke và update, và thiết kế locking hoặc giao thức version/synchronization cho cả hai phía.

**Bắt buộc nêu rõ guarantee cần thiết trước khi chọn isolation**, thay vì gọi một mức là “an toàn tuyệt đối”.

## 13. @Transactional và @PreAuthorize không đồng nghĩa check cùng transaction

Một service thường có:

~~~java
@PreAuthorize("@documentPolicy.canWrite(authentication, #id)")
@Transactional
public void rename(Long id, String title) {
    // Mutation.
}
~~~

Spring có thể áp dụng cả **authorization advice** và **transaction advice** trên proxy. Thứ tự advice có thể do framework/configuration quyết định; không được mặc định check nằm trong transaction đang bảo vệ mutation. Nếu policy đọc ACL trước lúc transaction bắt đầu, check và use vẫn có một khoảng cách.

Ngay cả khi check diễn ra trong cùng transaction, **không bảo đảm nó khóa tất cả row quyền**. Vì vậy:
- Dùng `@PreAuthorize` cho **coarse-grained entry authorization** khi phù hợp.
- Với write, đánh giá **resource-specific permission** gần mutation, trong transaction hoặc bằng một câu guarded update.
- Nếu dùng custom `AuthorizationManager` hoặc policy bean cần DB, biết rõ transaction propagation và advice order.
- Test thật thứ tự interceptor theo Spring version/configuration; không suy luận từ vị trí annotation trong source.
- Kiểm thử self-invocation: `this.rename(...)` trong cùng bean có thể bypass AOP proxy cho cả method security và transaction.

Một cách tổ chức dễ suy luận là **tách Spring bean** cho application service có transaction và bean policy được gọi trong method body, đồng thời vẫn dùng method security để chặn quyền đầu vào. Các đường gọi trực tiếp vào repository viết dữ liệu phải được kiểm soát qua kiến trúc module/test.

## 14. Quyền mới bị thu hồi và cached Authentication/ACL

Race không nhất thiết xảy ra ngay trong SQL. Một JWT hợp lệ có thể chứa role/group từ lúc phát hành. Khi user rời nhóm, token cũ vẫn mang claim cũ cho tới khi hết hạn nếu hệ thống không có cơ chế thu hồi hoặc tra membership lại.

Các nguyên nhân thường gặp:
- Spring SecurityContext được thiết lập trước khi role đổi.
- JWT còn hiệu lực, authorities được lấy từ token và không tra lại.
- Permission cache/Redis lưu kết quả ALLOW với TTL dài.
- ACL cache chưa invalidate sau grant/revoke.
- Instance khác của service chưa thấy sự kiện revoke.
- Session không được invalidated khi hạ quyền.

Biện pháp tương ứng:
1. Xác định **mức độ tươi của quyền**: chấp nhận tối đa bao lâu sau revoke?
2. Với hành động nhạy cảm, ưu tiên query/recheck quyền hiện thời hoặc token capability ngắn hạn có revocation/version.
3. Cache key phải gồm actor, tenant, resource, action, policy version; tránh cache chỉ theo ID.
4. Khi revoke, invalidate những cache quan trọng theo cơ chế có kiểm chứng; có khả năng cache miss/hit cho kết quả nhất quán với contract.
5. Lỗi cache/backend không được chuyển thành permit.
6. Với dữ liệu pháp lý/tài chính, cân nhắc kiểm tra trực tiếp nguồn quyền ở thời điểm action thay vì chỉ dựa vào claim cũ.

Không nhất thiết phải introspect mọi JWT tại mỗi request: lựa chọn phụ thuộc mục tiêu latency, độ sẵn sàng và **revocation SLA** đã cam kết. Điều cần tránh là hứa “thu hồi tức thì” trong khi mọi nơi vẫn tin token/cache còn hạn lâu.

## 15. Khi quyền nằm ở dịch vụ bên ngoài DB

Ví dụ:
~~~text
Service A (Document DB)        Service B (Policy/ACL DB)
          |                                |
          +-- canWrite(actor, doc) ------->|   returns ALLOW
          |
          +-- expensive work / network delay
          |
          +-- UPDATE document ------------> Document DB
~~~

`@Transactional` ở Service A không khóa được ACL store của Service B theo mặc định. Hai hệ có transaction độc lập. Trừ khi được thiết kế bằng protocol phân tán thực sự, **không thể khẳng định atomic** giữa remote authorization decision và local DB mutation.

Các hướng giải quyết:
- **Recheck ngay trước side effect** để giảm cửa sổ, chấp nhận race còn lại nếu rủi ro cho phép.
- **Policy revision/version**: decision gắn với phiên bản ACL; write path xác nhận revision vẫn hợp lệ trong cùng hệ có quyền enforce. Nếu revision chỉ được kiểm tra bằng một API call riêng, vẫn còn race giữa call và write.
- **Signed short-lived capability**: giới hạn actor, tenant, object, action, expiry, nonce và phạm vi; xác minh khi dùng. Thu hồi trước expiry yêu cầu revocation checking.
- **Permission mirror/index trong cùng DB**: đồng bộ policy từ hệ ngoài và dùng conditional SQL; phải định nghĩa consistency, lag và fail-closed.
- **Distributed workflow/saga**: giao thức trạng thái, idempotency, compensation khi có hành động nhiều hệ. Compensation không luôn hoàn tác được side effect đã lộ ra ngoài.

Đừng tạo fallback “policy service timeout → grant để không ảnh hưởng hoạt động”. Nếu không thể lấy quyết định mới mà nghiệp vụ đòi bảo vệ chặt, dừng thao tác và báo lỗi phù hợp.

## 16. Read cũng có TOCTOU: kiểm tra trước khi đọc dữ liệu nhạy cảm

Mẫu:
~~~java
if (policy.canRead(actor, documentId)) {
    Document d = repository.findById(documentId).orElseThrow();
    return mapper.toDto(d);
}
~~~

Nếu document đổi tenant/owner hoặc quyền bị revoke giữa hai lời gọi, một check READ cũ có thể không còn đúng. Với điều kiện đơn giản lưu cùng database, ưu tiên **query-time scoping**:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND (
      d.owner_user_id = :verified_actor
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee_user_id = :verified_actor
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
      )
  );
~~~

Điều kiện ID, tenant và permission được đánh giá trong cùng SELECT statement theo semantics DB. Đây là một ranh giới mạnh hơn việc load object bằng ID thuần rồi check sau khi đã chuyển nó qua mapper/log/cache.

Tuy vậy, một SELECT không thể làm “bí mật bị thu hồi sau khi bắt đầu response” biến mất khỏi dữ liệu đã gửi. Cần hợp đồng rõ: quyền được xét tại thời điểm truy vấn hay tại thời điểm từng byte được stream? Nếu dữ liệu được trả bằng stream kéo dài, cần chính sách đặc biệt khi revoke giữa dòng.

**Không serialise managed JPA entity sau khi transaction kết thúc** nếu lazy loading có thể tự truy cập dữ liệu ngoài scope. Hãy map DTO với đúng projection và policy trong transaction hoặc xây query DTO scoped.

## 17. File download và presigned URL: quyền kéo dài sau check

Các bước thông thường:
1. User gọi `GET /files/42/download-link`.
2. Service kiểm tra quyền READ trên file.
3. Service tạo presigned URL cho object storage, ví dụ 30 phút.
4. Quyền user bị thu hồi sau 1 phút.
5. Người đã có URL vẫn có thể dùng URL đến khi hết hạn theo chính sách provider.

Điều này **không phải** lỗi Spring Security filter trực tiếp; presigned URL là **capability** tồn tại độc lập với session ban đầu. Nếu chính sách yêu cầu thu hồi ngay, chỉ giảm TTL có thể chưa đủ.

Các lựa chọn:
- URL rất ngắn hạn, scoped đúng object/action/method và không để rò qua log/referrer.
- Download qua một service proxy kiểm tra policy tại từng yêu cầu thay vì cấp link dài hạn.
- Gateway/token revocation check hoặc versioned access token nếu hạ tầng hỗ trợ.
- Không cache file nhạy cảm ở CDN/browser lâu hơn chính sách.
- Khi thay object storage key hoặc revoke, xác minh cách invalidation thực tế vận hành.

Không thể đảm bảo thu hồi byte đã được tải trước revoke. Hợp đồng khả thi phải nói rõ thời điểm quyền được xét và cách giới hạn quyền sử dụng sau khi được cấp link.

## 18. Message queue, job và tác vụ bất đồng bộ

Một command được enqueue lúc T1 khi actor có WRITE, nhưng tiêu thụ lúc T2 sau khi actor bị thu hồi. Nếu consumer tin cờ `authorized=true` trong message thì đó là TOCTOU qua ranh giới thời gian và trust.

~~~text
HTTP at T1 --> "user can export" --> Queue (hours later)
                                       |
                                     Worker at T2
                                       |
                              EXPORT without recheck  // nguy hiểm
~~~

Với tác vụ nhạy cảm, worker phải có:
- Origin và actor/workload identity được xác minh, không tin field userId tự khai.
- Resource/action/scope được xác định rõ; không nhập nhằng user permission và system job permission.
- Chính sách **tái đánh giá tại thời điểm thực thi** hoặc capability đã ký có expiry/revocation semantics được công bố.
- Idempotency để retry không tạo side effect trùng lặp.
- Deadline, policy revision hoặc giới hạn dữ liệu sẽ xuất.
- Audit ai yêu cầu, ai thực thi và trạng thái quyền khi thực thi.

Nếu một tác vụ được ủy quyền hợp pháp để chạy **ngay cả sau khi user rời hệ thống** (ví dụ dữ liệu kế toán phải được lưu theo quy định), hãy định nghĩa **system operation** với service identity và policy riêng. Không giả vờ đó vẫn là quyền user cũ.

`@Async` có thể làm mất `SecurityContext` khi chuyển thread; truyền context có kiểm soát không đồng nghĩa quyền không đổi. Đừng chỉ copy SecurityContext rồi xem như đã giải quyết TOCTOU.

## 19. Outbox và side effect bên ngoài transaction

Sau khi kiểm tra quyền và ghi DB, một service có thể gửi email, publish event hoặc gọi payment API. Nếu publish **trước commit**, transaction rollback sau đó nhưng event đã phát có thể gây side effect sai.

Một thiết kế hay dùng:
~~~text
transaction:
  - xác minh quyền tại mutation boundary
  - update bản ghi theo predicate/version
  - insert outbox event cùng transaction
commit
outbox publisher:
  - gửi event idempotently
~~~

**Transactional outbox** giúp không phát event cho một transaction DB bị rollback, khi outbox và mutation cùng database/transaction. Nó **không tự** đồng bộ quyền với dịch vụ ngoài, và không ngăn một consumer thực thi thao tác mới khi policy đã thay đổi. Consumer phải có hợp đồng quyền riêng nếu event yêu cầu tác động thêm lên tài nguyên khác.

Các side effect không thể rollback (email đã gửi, file đã công khai, tiền đã chuyển) cần guard trước khi thực thi, idempotency, retry và đôi khi bù trừ có kiểm soát. Tránh gọi external API trong lúc giữ DB lock lâu trừ khi có lý do và timeout rất rõ.

## 20. Thay owner, chuyển tenant, khóa document: version nào tăng?

Nếu quyền chỉ phụ thuộc owner/status nằm trên document row, mọi thay đổi đó nên tham gia cùng cơ chế version/locking với mutation nội dung.

Ví dụ:
~~~text
document#42: owner=an, editable=true, version=5

T1: An nhận version=5
T2: chuyển owner sang Bình, version=6
T3: An yêu cầu UPDATE version=5
--> affectedRows=0
~~~

Nếu một luồng chuyển owner dùng bulk SQL `UPDATE owner_user_id=...` mà **không tăng version**, guard chỉ theo version có thể bỏ qua thay đổi; tuy nhiên nếu UPDATE tại T3 còn có `owner_user_id=:verified_actor` thì owner change vẫn bị phát hiện bởi predicate. Lý tưởng là **cả guard hiện thời và version** được dùng khi cần, không chỉ một cơ chế.

Nếu chuyển tenant, query và mutation bắt buộc ràng buộc tenant của resource. Khi tenant chuyển, ACL/share grant cũ, cache và search index phải được re-scope/thu hồi. Không chỉ cập nhật một cột mà để quyền cũ còn truy cập được resource theo ID từ tenant cũ.

Với status LOCKED, policy nên có predicate `editable = TRUE` hoặc guard trong transaction theo cùng version/lock. Một check `isEditable()` trước một tác vụ lâu không đủ.

## 21. Optimistic vs pessimistic vs atomic predicate: chọn thế nào?

| Bối cảnh | Lựa chọn đáng cân nhắc | Lưu ý |
|---|---|---|
| Owner-only, status trên row, lưu lượng cao | Atomic scoped UPDATE + version | Ít round trip, kiểm tra affected rows |
| Chỉnh sửa tài liệu từ UI | `@Version` + field owner/tenant guard | User có thể nhận 409 và reload |
| Quyền lưu ở bảng share cùng DB | UPDATE có `EXISTS` + isolation đã test hoặc protocol khóa | Revoke concurrent cần semantics rõ |
| Nghiệp vụ bắt buộc tuần tự hóa grant/revoke với write | Shared lock protocol trên document/ACL rows | Deadlock/timeout/order và mọi code path phải tuân thủ |
| External policy service | Recheck/capability/version + workflow consistency | Không có atomic DB transaction xuyên service mặc định |
| Long-running batch | Chunk nhỏ, recheck theo từng item/nhóm, idempotency | Một quyết định đầu batch không bảo vệ mọi item |
| Read-only detail | Query với scoped permission predicate | Thời điểm SELECT và thời điểm streaming khác nhau |
| Bulk export/download | Query/stream có scope, short-lived capability, recheck khi cần | Tránh rò data qua cache/URL còn hạn |

Không cần khóa mọi object pessimistically. Nó có thể gây nghẽn và deadlock không cần thiết. Nhưng cũng không nên dùng optimistic version một mình cho một rule quyền nằm ở bảng khác. Hãy chọn theo **vị trí lưu quyền**, **mức bảo đảm thu hồi** và **chi phí concurrency** của use case.

## 22. Java 17 độc lập: mô phỏng check cũ và guard nguyên tử

Ví dụ sau là Java 17 thuần, không dùng Spring/JPA. Nó tạo một interleaving **cố định** để chứng minh: quyết định tại T1 có thể trở nên lỗi thời ở T2; một thao tác vừa kiểm tra vừa ghi dưới cùng một lock của object sẽ từ chối khi owner/version đã đổi.

Tạo file `AuthorizationRaceDemo.java`:

~~~java
public class AuthorizationRaceDemo {
    record Actor(String userId, String tenantId) { }

    static final class Document {
        final long id;
        final String tenantId;
        String ownerId;
        String title;
        long version;

        Document(long id, String tenantId, String ownerId,
                 String title, long version) {
            this.id = id;
            this.tenantId = tenantId;
            this.ownerId = ownerId;
            this.title = title;
            this.version = version;
        }

        synchronized boolean canWrite(Actor actor) {
            return actor != null
                    && actor.userId() != null
                    && actor.tenantId() != null
                    && actor.tenantId().equals(tenantId)
                    && actor.userId().equals(ownerId);
        }

        synchronized void transferOwner(String newOwner) {
            ownerId = newOwner;
            version++;
        }

        synchronized void unsafeWriteWithoutRecheck(String newTitle) {
            title = newTitle;
            version++;
        }

        synchronized boolean renameGuarded(
                Actor actor, long expectedVersion, String newTitle) {

            if (!canWrite(actor)
                    || version != expectedVersion
                    || newTitle == null || newTitle.isBlank()) {
                return false;
            }
            title = newTitle;
            version++;
            return true;
        }
    }

    public static void main(String[] args) {
        Actor an = new Actor("an", "north");
        Actor southAn = new Actor("an", "south");

        Document unsafe = new Document(
                42, "north", "an", "Draft", 5);
        boolean checkAtT1 = unsafe.canWrite(an);
        unsafe.transferOwner("binh");          // Revoke ownership at T2
        if (checkAtT1) {
            unsafe.unsafeWriteWithoutRecheck("Changed");
        }
        System.out.println("naive-changed="
                + unsafe.title.equals("Changed"));

        Document guarded = new Document(
                42, "north", "an", "Draft", 5);
        long expected = guarded.version;
        guarded.transferOwner("binh");         // Revoke before mutation
        boolean accepted = guarded.renameGuarded(
                an, expected, "Changed");
        System.out.println("guarded-accepted=" + accepted);
        System.out.println("guarded-title=" + guarded.title);

        Document valid = new Document(
                43, "north", "an", "Draft", 9);
        boolean validWrite = valid.renameGuarded(
                an, 9, "Approved");
        System.out.println("valid-accepted=" + validWrite);
        System.out.println("valid-title=" + valid.title);

        boolean wrongTenant = valid.renameGuarded(
                southAn, 10, "CrossTenant");
        System.out.println("cross-tenant-accepted=" + wrongTenant);

        boolean staleVersion = valid.renameGuarded(
                an, 9, "Stale");
        System.out.println("stale-version-accepted=" + staleVersion);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac AuthorizationRaceDemo.java
java AuthorizationRaceDemo
~~~

Stdout chính xác:

~~~text
naive-changed=true
guarded-accepted=false
guarded-title=Draft
valid-accepted=true
valid-title=Approved
cross-tenant-accepted=false
stale-version-accepted=false
~~~

**Vì sao demo có ý nghĩa?**

- `naive-changed=true`: đã check khi An còn owner, sau đó owner đổi sang Bình, nhưng code ghi không recheck vẫn thay title.
- `guarded-accepted=false`: kiểm tra owner hiện thời **và** expected version bên trong cùng critical section phát hiện thay đổi trước đó.
- `valid-accepted=true`: actor đúng tenant/owner và version hợp lệ thì cập nhật.
- `cross-tenant-accepted=false`: actor cùng tên nhưng ở tenant khác không được ghi.
- `stale-version-accepted=false`: phiên bản 9 đã cũ sau khi version tăng lên 10.

**Giới hạn:** `synchronized` bảo vệ object Java **trong cùng JVM** khi mọi luồng dùng chính object đó. Nó **không** khóa record ở database, không bảo vệ nhiều pod/service và không đồng bộ ACL nằm ở storage khác. Khi triển khai Spring/JPA thực tế, thay critical section trong memory bằng **guarded database statement, transaction/lock hoặc protocol nhất quán** phù hợp và test dưới concurrency thật.

## 23. Cách test race condition có thể lặp lại

Một unit test “gọi canWrite rồi gọi save ngay” thường PASS vì không có thay đổi xen giữa. Race condition cần test có **điểm đồng bộ** để ép interleaving.

Mô hình test:

~~~text
Thread A (writer)                 Thread B (revoker)
---------------------             ----------------------
start request
permission check: ALLOW
signal "checked"
wait "revoked"                    wait "checked"
                                  revoke grant / move owner
                                  commit
                                  signal "revoked"
perform mutation
commit
assert expected outcome
~~~

Dùng `CountDownLatch`/`CyclicBarrier` trong test và transaction độc lập cho mỗi thread. Không dùng `Thread.sleep(...)` làm bằng chứng concurrency vì timing không ổn định. Khi test trên Spring, mỗi thread có security context riêng; fixture phải thiết lập context đáng tin cho từng worker, không dựa vào thread-local ngẫu nhiên.

Các test cần có:

1. **Naive path** minh họa bug bằng một fixture code cố tình sai, không đưa vào production.
2. **Owner change** commit trước guarded update: writer cũ affectedRows=0.
3. **Version stale**: hai writer dùng version cũ; chỉ một thay đổi thành công hoặc một transaction nhận conflict theo contract.
4. **Grant revoke** giữa check và write: kết quả theo revocation semantics đã định nghĩa.
5. **Group membership revoke**: token/cache cũ không cấp quyền quá SLA đã công bố.
6. **Tenant move**: writer tenant cũ không thể cập nhật record sau khi chuyển tenant.
7. **Lock test**: mọi đường change owner/grant phải tuân thủ lock protocol; timeout/deadlock được xử lý.
8. **External policy outage**: khi backend không trả quyết định, không có mutation.
9. **Retry after serialization conflict**: retry re-evaluate actor/policy và re-read state, không reuse ALLOW cũ.
10. **Message worker** được enqueue trước revoke nhưng xử lý sau: không chạy hành động nếu contract đòi quyền hiện thời.
11. **File link**: TTL/revocation kiểm chứng theo storage provider thực, không suy luận từ Spring API.
12. **Database state**: kiểm tra row, version, grant, audit/outbox sau denied/rollback chứ không chỉ HTTP status.

Chạy test với database dialect production (có thể dùng Testcontainers) và cùng isolation/configuration thực. H2 và mock repository có thể không mô phỏng đúng locking/snapshot semantics của PostgreSQL, MySQL hay hệ khác.

## 24. Test Spring/JPA về transaction thật

Khi tổ chức test:
- Inject service từ Spring application context; không tự tạo bằng `new` rồi kết luận `@Transactional`/`@PreAuthorize` hoạt động.
- Dùng principal/tenant test fixture phù hợp (với JWT custom claims, `@WithMockUser` mặc định có thể chưa đủ).
- Đảm bảo transaction thử nghiệm và transaction cạnh tranh **không vô tình cùng một test transaction**. Nếu test method tự được `@Transactional` và rollback cuối test, nó có thể che hành vi commit thực.
- Kiểm tra proxy self-invocation không làm bỏ qua transaction hoặc authorization advice.
- Bắt và assert đúng exception: optimistic conflict, lock timeout, denied, not-found đều cần xử lý khác nhau.
- Kiểm tra lỗi concurrency không bị bắt rồi trả HTTP 200 giả.
- Với `@Modifying` bulk query, test cả persistence context stale và expectedVersion guard.

Ví dụ các assertion mong muốn (snippet, không phải class test độc lập):

~~~java
int affected = repository.renameIfOwnerAndVersion(
        42L, "north", "an", "New title", 5L);

assertThat(affected).isZero();
assertThat(repository.findById(42L).orElseThrow().getTitle())
        .isEqualTo("Draft");
~~~

Đoạn giả định một transaction khác đã chuyển owner hoặc version trước đó; chỉ thực thi phần `findById` không scoped trong **test fixture có quyền quan sát DB**, không đưa kiểu query này vào endpoint cho user chưa được phép.

## 25. Observability: đo rủi ro TOCTOU trong vận hành

Các sự kiện nên ghi theo phương pháp an toàn:

| Event | Dữ liệu cần ghi | Điều không ghi |
|---|---|---|
| Authorization evaluation | Actor ID, tenant đã xác minh, action, resource, decision, policy revision | JWT/raw token và ACL đầy đủ |
| Guarded update rejected | Row count 0, reason code tổng quát, expectedVersion | Owner thật của resource ngoài scope |
| Revoke/grant | Ai thay quyền, resource/tenant, time, revision | Secret hoặc thông tin không được phép lộ |
| Version conflict | Version expected và trạng thái retry, correlation ID | Dữ liệu nhạy cảm trong exception body |
| Transaction serialization/deadlock | DB error class, attempt, latency, transaction boundary | Thông tin connection credential |
| External policy timeout | Dependency status và SLA vi phạm | Token/headers bí mật |
| Async use | RequestedAt, executedAt, identity/policy version, result | Payload bí mật của actor khác |

Đo tỉ lệ update affectedRows=0, optimistic conflicts, 403/404/409/5xx, authorization policy cache staleness, thời gian từ revoke đến enforcement và retries. Các con số này giúp phát hiện thay đổi permission diễn ra nhưng client còn được cho phép quá lâu.

Một audit log không thay guard; nó chỉ hỗ trợ điều tra và chứng minh kết quả sau khi hệ thống đã thực thi chính sách.

## 26. Những anti-pattern cần tránh

**1. Check quyền một lần ở controller rồi service gọi `updateById`.** Request có thể thay đổi quyền trước save; các adapter khác có thể bỏ qua controller. **Sửa:** service boundary + guarded DB operation.

**2. Chỉ thêm `@Transactional` là coi hết race.** Transaction không tự khóa dữ liệu ACL hoặc service ngoài. **Sửa:** xác định predicate/lock/isolation và test thật.

**3. Chỉ thêm `@Version` cho Document khi quyền ở bảng khác.** Permission revoke có thể không tăng document version. **Sửa:** guard quyền hiện thời hoặc version/lock của ACL.

**4. Recheck trước save nhưng vẫn dùng hai request khác transaction.** Thu hẹp nhưng không loại race. **Sửa:** atomic statement hoặc protocol nhất quán.

**5. Dùng `@PreAuthorize` để chứng minh quyền tồn tại ở commit.** Advice order/transaction boundary có thể khác. **Sửa:** kiểm tra resource policy trong operation an toàn.

**6. Lock document nhưng revoke grant không lock document.** Hai path không chia sẻ giao thức, không loại race. **Sửa:** áp dụng cùng lock order cho mọi writer và revoker.

**7. Cache ALLOW lâu, không invalidate khi revoke.** Token/cache vẫn mang quyền cũ. **Sửa:** TTL/revision/revocation SLA và recheck cho action nhạy cảm.

**8. Worker tin `authorized=true` của message.** Cờ gửi tại T1 là dữ liệu cũ và có thể giả. **Sửa:** xác minh origin, actor, policy tại T2 hoặc capability kiểm soát.

**9. Presigned URL quá lâu nhưng hứa thu hồi ngay.** URL vẫn là capability đến expiry. **Sửa:** TTL ngắn hoặc gateway kiểm tra lại.

**10. Retry lại UPDATE bằng decision cũ.** Một optimistic/serialization failure có thể xảy ra sau khi quyền đổi. **Sửa:** retry bắt đầu use case mới với actor/policy/state được đánh giá lại.

**11. Update affectedRows=0 nhưng trả 204.** Client tưởng thao tác thành công và hệ thống che stale/denied. **Sửa:** kiểm tra row count, mapping lỗi an toàn.

**12. Chỉ test tuần tự.** Các race chỉ xảy ra dưới interleaving. **Sửa:** tests dùng latch, transaction thực, production-like DB.

## 27. Checklist thiết kế một use case có side effect

- [ ] Xác định rõ quyền cần hợp lệ tại thời điểm nào: request, mutation, commit hay external execution.
- [ ] Xác minh actor, tenant và authority bằng nguồn tin cậy.
- [ ] Tách coarse role check khỏi object permission.
- [ ] Truy vấn theo ID luôn có tenant/owner hoặc allowed scope phù hợp.
- [ ] Nếu quyền nằm trên target row, cân nhắc guarded UPDATE/DELETE trong cùng statement.
- [ ] Nếu dùng optimistic locking, bảo đảm mọi thay đổi auth-relevant tham gia guard/version cần thiết.
- [ ] Nếu dùng pessimistic locking, tất cả luồng grant/revoke/owner change tuân thủ cùng protocol.
- [ ] Kiểm tra isolation, advice order và transaction manager thực tế.
- [ ] Không coi external policy service như một phần DB transaction khi chưa có giao thức đảm bảo.
- [ ] Không tin ALLOW cache/token hơn mức revocation SLA.
- [ ] File download, queue, batch và background job có chính sách tại thời điểm sử dụng.
- [ ] Side effect bên ngoài dùng outbox/idempotency/guard tùy rủi ro.
- [ ] Với affectedRows=0, không trả success; không leak owner/tenant thật.
- [ ] Khi retry concurrency conflict, lấy quyết định quyền mới.
- [ ] Test interleaving với revoke/owner move, version conflict, wrong tenant và outage.
- [ ] Có audit/correlation/metrics nhưng không log credential hoặc tài liệu ngoài quyền.

**Kết luận:** TOCTOU trong authorization xuất hiện khi **một quyết định đúng ở quá khứ** được dùng để cho phép **một tác động ở hiện tại** mà không còn ràng buộc với dữ liệu và quyền hiện thời. Với quyền trên chính record, atomic conditional UPDATE kèm tenant/owner/status/version là mô hình rất hiệu quả. Với ACL, group hoặc policy ngoài DB, phải thiết kế thêm protocol đồng bộ, revision hoặc recheck theo mức bảo đảm mong muốn. Spring Security method security, transaction và locking hỗ trợ giải pháp, nhưng không cái nào **tự động** loại bỏ mọi race khi đứng riêng.

## Tài liệu tham khảo

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): method authorization, interceptor và cách xác định ranh giới.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, self-invocation, isolation/propagation/rollback và advice order.
- [Spring Data JPA – Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): sử dụng `@Lock` với JPA query methods.
- [Spring Data JPA – JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): `@Modifying`, JPQL update và persistence context.
- [Spring Data JPA – Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): transaction boundaries và transactional repository operations.
- [Jakarta Persistence – @Version](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic locking version trong JPA.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): vì sao ID trực tiếp không chứng minh quyền trên object.
