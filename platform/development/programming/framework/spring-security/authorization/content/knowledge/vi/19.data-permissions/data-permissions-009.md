# Chia sẻ dữ liệu, ủy quyền tạm thời và giới hạn thời gian trong Spring Security

## 1. Bài toán: quyền truy cập thay đổi theo **người nhận, tài nguyên, hành động và thời điểm**

Giả sử Alice sở hữu tài liệu `Document #42` trong một hệ thống quản lý dự án. Bình thường, chỉ Alice và những thành viên có chính sách phù hợp mới được đọc tài liệu. Alice muốn **chia sẻ quyền đọc với Bob từ 09:00 đến 10:00**, sau đó tự động chấm dứt; nếu phát hiện chia sẻ nhầm, Alice cần có khả năng **thu hồi ngay** trước 10:00.

Một rule đơn giản như `hasRole('USER')` không giải quyết được bài toán này: Alice và Bob có thể cùng là USER, nhưng mỗi tài liệu có người được chia sẻ và thời hạn khác nhau. Tương tự, một quyền `document:read` ở mức chức năng không chứng minh Bob được đọc **Document #42** trong **khoảng thời gian hiện tại**.

Chính sách cần trả lời:

```text
Ai?       Bob (authenticated subject / grantee)
Làm gì?   READ
Ở đâu?    Document #42 thuộc tenant A
Vì sao?   Alice là người có quyền chia sẻ hợp lệ
Từ khi?   2026-11-05T02:00:00Z
Đến khi?  2026-11-05T03:00:00Z (không gồm thời điểm này)
Còn hiệu lực? Chưa bị thu hồi, chưa có điều kiện khác vô hiệu hóa
```

Ví dụ dùng thời gian UTC để thống nhất. Thời gian địa phương tương ứng phụ thuộc múi giờ của người dùng; **không** lưu một chuỗi `"09:00"` không kèm ngày/múi giờ rồi dựa vào đồng hồ trình duyệt để phân quyền.

**Nguyên tắc:** quyền chia sẻ chỉ là một đường **bổ sung có kiểm soát** để vượt qua quyền truy cập mặc định đối với **đúng đối tượng và hành động**, trong **khoảng thời gian hợp lệ**. Quyền đó không tự vượt qua tenant isolation, tình trạng khóa tài khoản, trạng thái tài nguyên hoặc một lệnh thu hồi.

Bài học phân biệt ba mô hình:

1. **Chia sẻ có danh tính (named-recipient grant):** người nhận Bob đăng nhập; server lưu grant cho Bob trên Document #42.
2. **Ủy quyền tạm thời cho tác nhân/app khác:** một tác nhân được cấp quyền có phạm vi và thời hạn giới hạn; phải xác minh ai cấp, ai nhận và mục đích.
3. **Link/token chia sẻ (bearer capability):** bất cứ ai sở hữu secret hợp lệ có thể dùng quyền theo thiết kế của link; cần có cách kiểm soát rò rỉ, thu hồi và thời hạn riêng.

Ba mô hình có độ tin cậy khác nhau. Không biến một URL được gửi qua email thành sự thay thế mặc định cho xác thực người nhận, và cũng không nhầm thời hạn đăng nhập/JWT với thời hạn **được phép truy cập tài nguyên**.

## 2. Phân biệt Authentication, Authority, ACL và grant có thời hạn

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang thực hiện request? | `subject=bob` từ session/JWT đã xác minh |
| Authority/role | Người này được phép dùng chức năng nào? | `document:read`, `ROLE_EDITOR` |
| Object authorization | Được phép làm gì trên **Document #42**? | Owner, member, ACL, policy |
| Sharing grant | Ai được trao thêm hành động nào đối với object nào? | Bob có READ trên #42 |
| Time window | Grant có hiệu lực **ở thời điểm này** không? | `validFrom <= now < expiresAt` |
| Revocation | Grant đã bị thu hồi/chấm dứt trước hạn chưa? | `revokedAt != null` |
| Token/session lifetime | Credential dùng để xác thực còn hợp lệ không? | JWT `exp`, session timeout |

Một JWT hợp lệ chưa chắc người dùng vẫn được đọc Document #42. Ngược lại, một grant chưa hết hạn cũng không biến một token đã hết hạn thành authentication hợp lệ.

Trong hệ thống Spring Security:

- `SecurityFilterChain` thường xử lý authentication và chặn request chưa đăng nhập.
- `authorizeHttpRequests(...)` có thể chặn quyền truy cập endpoint ở mức coarse-grained.
- `@PreAuthorize(...)` hoặc `AuthorizationManager<MethodInvocation>` có thể gọi bean policy Java với document ID.
- `AclPermissionEvaluator`/Spring ACL có thể đánh giá ACE theo người nhận; nhưng **thời hạn và thu hồi theo grant không tự có** trong ACE tiêu chuẩn, trừ khi ứng dụng bổ sung cơ chế tương ứng.
- Repository/database vẫn phải bảo vệ object và tenant; cache/search/file storage cũng phải tuân theo quyết định.

**Không** suy ra việc dùng Spring ACL tự làm mọi ACE hết hạn. Bảng `ACL_ENTRY` chuẩn có mask, granting, SID và thứ tự ACE, chứ không mặc nhiên có `expires_at` cho mỗi entry. Nếu cần thời gian sống, hãy bổ sung domain sharing grant/policy hoặc mở rộng mô hình lưu trữ một cách có chủ đích.

## 3. Một grant tạm thời cần lưu những gì?

Mô hình nền tảng cho chia sẻ theo danh tính:

| Trường | Ý nghĩa bảo mật |
| --- | --- |
| `grantId` | ID ổn định của bản ghi cấp quyền, phục vụ audit/revoke |
| `resourceType` và `resourceId` | Loại và **đúng ID tài nguyên** |
| `grantorSubjectId` | Người/tác nhân đã cấp quyền, lấy từ Authentication |
| `recipientSubjectId` | Người nhận được cấp quyền, định danh nội bộ ổn định |
| `permission` | READ, COMMENT, EDIT, DOWNLOAD hoặc quyền cụ thể |
| `validFrom` | Thời điểm bắt đầu được phép |
| `expiresAt` | Mốc **hết hiệu lực**, không bao gồm |
| `revokedAt` | Được đặt khi chủ thể có quyền thu hồi |
| `createdAt`, `updatedAt` | Audit, đối soát trạng thái |
| `tenantId` | Phạm vi tenant nếu dùng multi-tenancy |
| `createdByReason`/`source` | Lý do/ticket phục vụ vận hành, nếu cần |

Đôi khi còn cần `maxUses`, số lượt đã dùng, `allowedIpRange`, `deviceBinding`, `approvalId`, `watermark`, `externalRecipient`, `delegationDepth`, `grantVersion` hoặc `policyVersion`. Chỉ thêm nếu thực sự có requirement và cách thực thi đáng tin; thiết kế phức tạp không tự đồng nghĩa bảo mật hơn.

### Quyền READ không tự mở rộng thành EDIT

Một grant `permission=READ` không có nghĩa:

- Được sửa nội dung.
- Được tải file gốc nếu DOWNLOAD là quyền riêng.
- Được chia sẻ tiếp cho Carol.
- Được thay đổi owner hoặc tenant.
- Được xem tất cả document khác trong cùng folder.
- Được export toàn bộ tập dữ liệu.
- Được giữ quyền khi hết hạn/thu hồi.

Nếu nghiệp vụ muốn chia sẻ theo nhóm hành động, biểu diễn **permission set rõ ràng** và kiểm tra theo action. Không dùng một cờ `shared=true` với ý nghĩa mọi thao tác đều được phép.

## 4. Điều kiện cấp quyền: người chia sẻ không được tự cấp quyền vượt thẩm quyền

Một rủi ro phổ biến là bất kỳ user nào có quyền đọc một tài liệu đều được gọi:

```http
POST /api/documents/42/shares
Content-Type: application/json

{
  "recipientId": "carol",
  "permission": "ADMIN",
  "expiresAt": "2099-01-01T00:00:00Z"
}
```

Nếu server lưu nguyên body, Carol có thể được ADMIN trên tài liệu, thậm chí vượt quyền Alice. **Quyền có thể chia sẻ** phải là quyền riêng như `document:share`, không phải tự động suy ra từ READ. Việc tạo grant mới cần kiểm tra:

1. Caller đã xác thực và vẫn active.
2. Caller có quyền SHARE trên **Document #42** ở thời điểm cấp.
3. Document thuộc tenant đã xác minh; chưa bị xóa/khóa/đánh dấu confidential cấm chia sẻ.
4. Người nhận hợp lệ, được phép nhận chia sẻ trong tenant/nhóm hoặc nằm trong danh sách external recipients được duyệt.
5. Permission được đề nghị nằm trong **tập được phép ủy quyền**, có thể còn phải là tập con quyền thực tế của grantor.
6. Thời hạn không quá policy: ví dụ tối đa 24 giờ cho external share, tối đa 30 ngày cho internal share.
7. Không được tự mở rộng thời hạn từ một grant ủy quyền ban đầu: nếu Alice nhận quyền đến 10:00 thì không thể phát cho Bob đến 17:00 nếu policy không cho phép.
8. Không được tự cấp lại quyền đã bị thu hồi bằng cách lặp request thiếu idempotency/revocation policy.
9. Các điều kiện approval, quotas, classification và audit được áp dụng.

**Tùy sản phẩm:** owner có thể có SHARE dù chưa có một authority chung; hoặc một quản trị viên tenant có quyền chia sẻ trong scope của mình. Quan trọng là mọi đường cho phép đều có cơ sở server-side, không dựa vào `grantorId` hay `role` client tự khai.

## 5. Khoảng thời gian có hiệu lực: định nghĩa chính xác ranh giới

Khuyến nghị dùng **khoảng nửa mở**:

```text
[validFrom, expiresAt)
```

Nghĩa là:

- Hợp lệ khi `now >= validFrom`.
- Hợp lệ khi `now < expiresAt`.
- **Đúng tại `expiresAt`**: đã hết hạn.
- Trước `validFrom`: chưa có quyền.
- `validFrom >= expiresAt`: grant không hợp lệ, không lưu/cấp.

Java dùng `java.time.Instant` và `Clock`:

```java
static boolean withinWindow(
        Instant now, Instant validFrom, Instant expiresAt) {
    return now != null
        && validFrom != null
        && expiresAt != null
        && !now.isBefore(validFrom)
        && now.isBefore(expiresAt);
}
```

Đây là một **method fragment** cần import `java.time.Instant`. So sánh với `Instant` theo mốc thời gian tuyệt đối; việc dùng khoảng nửa mở tránh rắc rối microsecond/nanosecond ở biên. Không viết `now <= expiresAt` khiến grant vẫn được xem là hợp lệ **tại chính thời điểm hết hạn**.

### UTC, đồng hồ và độ chính xác database

- Lưu `validFrom`/`expiresAt` thành `Instant` hoặc kiểu DB biểu diễn mốc UTC có quy ước rõ.
- UI có thể hiển thị giờ địa phương theo `ZoneId` nhưng **server** chuyển về Instant để lưu và so sánh.
- Không tin `Date.now()` ở frontend để cho phép/từ chối.
- Injection `Clock` giúp tạo test cố định và dễ kiểm tra biên thời gian.
- Nhiều instance phải có đồng hồ đồng bộ; nếu cần quyết định cực kỳ chặt, cân nhắc dùng cùng nguồn giờ ở DB và giao dịch.
- Tính đến độ chính xác cột SQL (seconds/milliseconds/microseconds) và biểu diễn Instant nhất quán.
- Cấu hình clock skew cho JWT không nên tự kéo dài thời hạn **share grant** vốn phải chấm dứt đúng mốc.

Một ví dụ:

```text
validFrom = 2026-11-05T02:00:00Z
expiresAt = 2026-11-05T03:00:00Z

01:59:59.999Z  -> DENY (chưa bắt đầu)
02:00:00.000Z  -> ALLOW nếu các điều kiện khác hợp lệ
02:59:59.999Z  -> ALLOW
03:00:00.000Z  -> DENY (đã hết hạn)
```

## 6. Thu hồi quyền: revoke khác với chờ hết hạn

Giới hạn thời gian là **expiry**; thu hồi là một hành động **bất đồng bộ với mốc hết hạn**. Khi Alice bấm “Stop sharing” lúc 09:20, Bob phải bị từ chối ở lần truy cập sau theo SLA an ninh đã công bố, dù `expiresAt` vẫn là 10:00.

Mô hình đơn giản:

```text
ACTIVE:
  validFrom <= now < expiresAt
  AND revokedAt IS NULL
  AND document còn truy cập được
  AND recipient / tenant / permission còn hợp lệ

REVOKED:
  revokedAt != null

EXPIRED:
  now >= expiresAt

NOT_YET_VALID:
  now < validFrom
```

Có thể lưu `revokedAt` thay cho xóa row để giữ audit. Khi thu hồi, cập nhật trong transaction và kiểm tra caller có quyền revoke (owner, grantor hoặc admin có scope phù hợp). Các endpoint admin không được nhận `grantId` rồi thu hồi của tenant khác nếu thiếu object-level authorization.

**Lưu ý:** `revokedAt != null` là dấu hiệu đã thu hồi; nếu thiết kế cho phép lên lịch thu hồi trong tương lai, cần một field khác hoặc so sánh `now >= revokedAt`, và phải thống nhất ngữ nghĩa. Ví dụ trong bài dùng **thu hồi có hiệu lực ngay** nên mọi row có `revokedAt` khác null đều vô hiệu.

### Quyền chủ sở hữu cũng có thể đổi

Nếu Document được chuyển owner, xóa, chuyển tenant, phân loại lên mức cao hơn, hoặc project bị archived, grant cũ có thể không còn phù hợp. Policy có thể:

- Tự động revoke mọi grant khi ownership/tenant thay đổi.
- Hạn chế chỉ một phần hành động.
- Yêu cầu owner mới xác nhận chia sẻ.
- Chặn tất cả grant trên document bị xóa/locked.
- Giữ lịch sử để audit nhưng không cấp quyền.

Thời hạn còn lại không phải bằng chứng cho phép nếu trạng thái domain đã thay đổi.

## 7. Spring Security: bảo vệ ở endpoint và service

Một endpoint đọc tài liệu:

```http
GET /api/documents/42
Authorization: Bearer <access-token-bob>
```

Lớp HTTP có thể yêu cầu authenticated. Nhưng kiểm tra Bob có grant đang hiệu lực trên Document #42 nên đặt ở **service/domain authorization**, vì một service còn có thể bị gọi từ message consumer, batch hoặc một controller khác.

Cấu hình Servlet Security đơn giản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/documents/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Đây là **một phần cấu hình**: ứng dụng thật cần cơ chế authentication, CSRF/CORS, exception handling và các endpoint khác tùy requirement. `authenticated()` chỉ ngăn request chưa đăng nhập, **không xác nhận quyền đối với ID 42**.

Bật method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Và gọi một bean policy Java từ `@PreAuthorize`:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@sharingPolicy.canRead(authentication, #documentId)"
)
public DocumentView read(@P("documentId") Long documentId) {
    // Chỉ chạy sau khi policy cấp quyền.
}
```

Đây là **method fragment**, cần import `@PreAuthorize`, `@P` và các lớp domain. `@P("documentId")` giúp Spring Security tìm đúng tham số trong SpEL; ngoài ra có thể dùng biên dịch `-parameters` theo hướng dẫn chính thức.

**Quy tắc rõ ràng:** người nhận grant có thể cần authority chức năng `document:read` trước; việc nhận chia sẻ không tự cấp một authority global. Nếu sản phẩm có external guest không có authority đó, thiết kế một policy guest/capability riêng; không bỏ mọi authentication/authorization mà chưa đánh giá threat model.

## 8. Thiết kế model và repository cho sharing grant

Ví dụ các lớp thành phần dưới đây dành cho Spring Boot + Spring Security + Spring Data JPA, Java 17+. Chúng **không phải** một chương trình `javac` độc lập. Dự án cần định nghĩa entity, database schema, mapping JWT/principal, transaction và repository tương ứng.

Một entity rút gọn theo ý nghĩa:

```java
@Entity
@Table(name = "document_share_grants")
public class DocumentShareGrant {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long documentId;
    private String tenantId;
    private String grantorSubjectId;
    private String recipientSubjectId;

    @Enumerated(EnumType.STRING)
    private SharePermission permission;

    private Instant validFrom;
    private Instant expiresAt;
    private Instant revokedAt;

    // Constructors, getters, setters, validation và indexes
    // do ứng dụng định nghĩa phù hợp với schema.
}
```

`SharePermission` có thể là:

```java
public enum SharePermission {
    READ, COMMENT, EDIT, DOWNLOAD
}
```

Đây là **entity outline** để hiểu các trường; không copy chạy độc lập vì cần imports Jakarta Persistence/Instant, constructors, getters/setters và migration. Dù có `tenantId` trên grant, lúc kiểm tra vẫn phải xác minh tenant của **document thật** và membership/cấu hình external share: không tin một row grant sai tenant là có quyền.

### Repository chỉ hỏi grant còn hiệu lực

Một derived query trong Spring Data JPA:

```java
import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentShareGrantRepository
        extends JpaRepository<DocumentShareGrant, Long> {

    boolean existsByDocumentIdAndTenantIdAndRecipientSubjectIdAndPermissionAndRevokedAtIsNullAndValidFromLessThanEqualAndExpiresAtGreaterThan(
        Long documentId,
        String tenantId,
        String recipientSubjectId,
        SharePermission permission,
        Instant atOrAfterValidFrom,
        Instant beforeExpiresAt
    );
}
```

Tên method dài nhưng biểu diễn chính xác các predicate:

```sql
SELECT EXISTS (
    SELECT 1
    FROM document_share_grants g
    WHERE g.document_id = :document_id
      AND g.tenant_id = :verified_tenant
      AND g.recipient_subject_id = :subject
      AND g.permission = :permission
      AND g.revoked_at IS NULL
      AND g.valid_from <= :now
      AND g.expires_at > :now
);
```

SQL trên là **mô hình logic**, cú pháp `SELECT EXISTS (...)` và kiểu cột cụ thể tùy DB. Derived query trong code truyền **cùng một Instant `now` cho hai tham số thời gian**, không lấy đồng hồ hai lần ở hai ngữ cảnh khác nhau. Với các quy tắc multi-permission (EDIT bao hàm READ hoặc không), phải định nghĩa rõ và sửa truy vấn/policy thay vì mặc định `EDIT` tương đương `READ`.

Để query hiệu quả, cân nhắc index trên `(document_id, recipient_subject_id, permission)`, cùng tenant và revoked/time tùy DB và tải thực tế. Không xem index như hàng rào bảo mật; DB constraints, FK và transaction quyết định tính toàn vẹn dữ liệu.

### Vì sao nên giữ grant ở database khi cần revoke tức thì?

Nếu ứng dụng nhúng toàn bộ quyền chia sẻ trong một JWT tự chứa và chỉ xác thực chữ ký/`exp`, server có thể **không biết** grant đã bị thu hồi sớm. Với grant store database, mỗi lần policy kiểm tra có thể thấy `revokedAt` mới. Điều đó tăng truy vấn, nhưng phù hợp với yêu cầu thu hồi.

Cache nếu có cần invalidation/TTL và consistency theo SLA: không thể vừa cache grant trong 30 phút không kiểm tra, vừa hứa revoke hiệu lực dưới 1 giây trên mọi node.

## 9. SharingPolicy: đọc đúng tài nguyên, actor và thời gian

Hợp đồng danh tính tự xây của ứng dụng:

```java
public record ActorScope(
    String subjectId,
    String tenantId,
    boolean active
) {}

public interface CurrentActorService {
    ActorScope requireVerifiedActor();
}
```

`CurrentActorService` là **dịch vụ ứng dụng**, không phải class chuẩn Spring Security. Nó phải lấy identity từ `Authentication`/SecurityContext đáng tin cậy, xác minh subject và tenant membership, kiểm tra account status và từ chối nếu không có dữ liệu hợp lệ. Không trả `ActorScope` được dựng từ JSON `userId` hoặc header `X-Tenant-Id` do client tự khai.

Một policy bean minh họa:

```java
import java.time.Clock;
import java.time.Instant;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("sharingPolicy")
public class SharingPolicy {
    private final DocumentRepository documents;
    private final DocumentShareGrantRepository grants;
    private final CurrentActorService actors;
    private final Clock clock;

    public SharingPolicy(
            DocumentRepository documents,
            DocumentShareGrantRepository grants,
            CurrentActorService actors,
            Clock clock) {
        this.documents = documents;
        this.grants = grants;
        this.actors = actors;
        this.clock = clock;
    }

    public boolean canRead(Authentication auth, Long documentId) {
        if (auth == null || !auth.isAuthenticated()
                || documentId == null || documentId <= 0) {
            return false;
        }

        // Actor được xác minh từ SecurityContext thực tại server;
        // không chỉ từ auth.getName() hoặc request parameter.
        ActorScope actor = actors.requireVerifiedActor();
        if (!actor.active()) {
            return false;
        }

        var document = documents
            .findByIdAndTenantIdAndDeletedFalse(
                documentId, actor.tenantId())
            .orElse(null);

        if (document == null) {
            return false;
        }

        // Chủ sở hữu được đọc nếu policy nghiệp vụ cho phép.
        if (actor.subjectId().equals(document.getOwnerSubjectId())) {
            return true;
        }

        Instant now = clock.instant();

        return grants
            .existsByDocumentIdAndTenantIdAndRecipientSubjectIdAndPermissionAndRevokedAtIsNullAndValidFromLessThanEqualAndExpiresAtGreaterThan(
                documentId,
                actor.tenantId(),
                actor.subjectId(),
                SharePermission.READ,
                now,
                now
            );
    }
}
```

**Đây là code minh họa tích hợp**, cần `DocumentRepository`, entity `Document` với `getOwnerSubjectId()` và `findByIdAndTenantIdAndDeletedFalse`, bean `Clock` cùng security context thực. Cần bảo đảm `CurrentActorService` và `auth` đại diện cùng principal; nếu nhận `Authentication` từ API nội bộ không tin cậy mà actor service dùng context khác, việc nhầm actor có thể tạo lỗ hổng. Một thiết kế khác là để actor service nhận trực tiếp `Authentication` đã xác thực và tạo `ActorScope` từ nó theo contract rõ ràng.

Với policy này:

- Tài liệu đã deleted hoặc thuộc tenant khác bị từ chối.
- Owner có READ theo quy tắc mẫu.
- Recipient khác cần một grant READ còn hiệu lực và chưa revoke.
- Một grant EDIT không mặc định tạo READ nếu enum chưa có quy tắc kế thừa.
- Account đã inactive không được truy cập.
- External sharing cross-tenant **chưa được hỗ trợ** trong mẫu, phải thiết kế riêng với recipient identity và domain policy cụ thể.

**Lưu ý về anonymous:** `Authentication.isAuthenticated()` một mình không bảo đảm đó là người dùng đăng nhập thật (anonymous token có thể báo authenticated); `CurrentActorService.requireVerifiedActor()` phải từ chối anonymous/unsupported auth, hoặc policy kiểm tra rõ bằng trust resolver. Đừng xóa điều kiện đó chỉ để demo chạy với MockUser không đủ fixtures.

### Cấu hình Clock

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Khi test, thay bean bằng `Clock.fixed(...)` hoặc mock/inject Clock phù hợp. Điều này tạo ra các test ranh giới thời gian **đáng tin và không ngủ thật**. Server production cần đồng bộ đồng hồ trong cluster.

## 10. Gắn SharingPolicy với service và repository có scope

Service nhận ID từ caller:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {
    private final DocumentRepository documents;
    private final CurrentActorService actors;

    public DocumentReadService(
            DocumentRepository documents, CurrentActorService actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@sharingPolicy.canRead(authentication, #id)"
    )
    public DocumentView read(@P("id") Long id) {
        ActorScope actor = actors.requireVerifiedActor();

        // Defense-in-depth: không gọi findById rộng.
        var doc = documents
            .findByIdAndTenantIdAndDeletedFalse(id, actor.tenantId())
            .orElseThrow(() -> new ResourceNotVisibleException());

        return new DocumentView(doc.getId(), doc.getTitle());
    }

    public record DocumentView(Long id, String title) {}
}
```

`ResourceNotVisibleException` là **exception nghiệp vụ do ứng dụng định nghĩa** và mapping thành 404 trung tính khi cần che giấu existence; không phải class mặc định Spring Security. Đoạn này không chạy độc lập nếu chưa có các class ứng dụng.

**Ranh giới quan trọng:** `@PreAuthorize` chạy **trước** service method body; nó có thể kiểm tra grant ở một transaction/khoảng thời gian khác với lần fetch thực. Với dữ liệu có yêu cầu revoke nghiêm ngặt, một quyền có thể bị thu hồi giữa check và đọc. Do đó:

- Cân nhắc thực hiện **lookup tài nguyên và quyết định cấp quyền trong cùng service transaction**.
- Dùng transaction/isolation/locking hoặc query ràng buộc grant và tài liệu theo nhu cầu nhất quán.
- Chỉ đưa dữ liệu ra response sau khi tất cả điều kiện được xác minh.
- Đừng cho `@PreAuthorize` ở ngoài transaction là bảo đảm nguyên tử đối với revoke.
- Nếu mục tiêu chỉ là bảo mật read thông thường, policy trước method + query tenant-scoped là một lớp phòng vệ tốt, nhưng phải xác định SLA revoke thực.

Nếu tài liệu có bản ghi ACL đầy đủ hoặc quyền chia sẻ theo project/folder, policy cần xét mọi ràng buộc có hiệu lực. Không dùng `findById` rộng rồi trả entity chỉ vì có một grant ID “cùng số”.

## 11. Tạo grant và xác minh người cấp có quyền SHARE

Grant không nên được ghi bằng một endpoint cho phép caller tự chọn `grantorId`, `tenantId` hoặc `createdAt`. Một service tạo chia sẻ cần xử lý:

```text
Authenticated grantor
  -> resource exists in verified tenant
  -> grantor has SHARE / delegable permission
  -> recipient valid and authorized to receive
  -> permission subset allowed
  -> duration <= policy maximum
  -> validFrom < expiresAt
  -> idempotency/duplication rules
  -> database insert in transaction
  -> audit & notify after commit
```

Mô hình method minh họa:

```java
@Transactional
@PreAuthorize("hasAuthority('document:share')")
public ShareView grantRead(
        Long documentId,
        String recipientSubjectId,
        Instant requestedExpiry) {

    ActorScope actor = actors.requireVerifiedActor();
    Document document = documents
        .findByIdAndTenantIdAndDeletedFalse(
            documentId, actor.tenantId())
        .orElseThrow(ResourceNotVisibleException::new);

    if (!document.getOwnerSubjectId().equals(actor.subjectId())) {
        throw new AccessDeniedException("Sharing not permitted");
    }

    recipients.requireActiveMember(
        recipientSubjectId, actor.tenantId());

    Instant now = clock.instant();
    Instant upper = now.plus(Duration.ofHours(24));

    if (requestedExpiry == null
            || !requestedExpiry.isAfter(now)
            || requestedExpiry.isAfter(upper)) {
        throw new InvalidSharingPeriodException();
    }

    DocumentShareGrant grant = new DocumentShareGrant();
    grant.setDocumentId(documentId);
    grant.setTenantId(actor.tenantId());
    grant.setGrantorSubjectId(actor.subjectId());
    grant.setRecipientSubjectId(recipientSubjectId);
    grant.setPermission(SharePermission.READ);
    grant.setValidFrom(now);
    grant.setExpiresAt(requestedExpiry);
    grant.setRevokedAt(null);

    DocumentShareGrant saved = grants.save(grant);
    return new ShareView(saved.getId(), saved.getExpiresAt());
}
```

Đây là **method fragment**: `recipients`, `grants`, `documents`, `actors`, `clock`, DTO/exception/`Duration`/imports và entity setters phải được ứng dụng khai báo. Nó minh họa policy **owner-only SHARE**, không tự cho editor quyền share hay external guest. Hạn 24 giờ là **ví dụ**, không phải mức do Spring Security đặt ra.

Với hệ thống có chia sẻ tiếp (subdelegation), việc chỉ kiểm tra owner là quá chặt; có thể thay bằng policy phân quyền theo cấp, nhưng phải ràng buộc scope, duration, recipients và permission **không vượt grant gốc**. Nếu issuer bị revoke, có thể phải revoke toàn bộ grants phát sinh theo chuỗi ủy quyền; trường `parentGrantId` hoặc authorization graph giúp theo dõi.

### Không cho sửa grant để kéo dài vô hạn

Một PATCH `/shares/{grantId}` cũng cần authorization trên **grant và resource thật**. Không nhận request `expiresAt=2099` nếu max duration là 24 giờ. Mỗi lần gia hạn có thể yêu cầu reauthorization của grantor và xét trạng thái document/recipient hiện tại. Hãy quyết định grant đã revoke có được phép re-activate không; thiết kế an toàn thường tạo grant mới với ID mới thay vì lặng lẽ bật lại một grant đã bị thu hồi.

## 12. Thu hồi grant và bảo vệ endpoint thu hồi

Tình huống:

```http
DELETE /api/documents/42/shares/9001
Authorization: Bearer <token-alice>
```

Không chỉ tìm `grantId=9001` rồi xóa: attacker có thể đổi ID để thu hồi grant của người khác hoặc tenant khác. Server phải xác minh:

- Grant 9001 gắn đúng Document 42 theo URL.
- Document 42 thuộc tenant đã xác minh.
- Caller là owner/grantor hoặc admin được ủy quyền trong scope đó.
- Quy tắc idempotency của revoke được định nghĩa; request lặp không vô tình tái cấp quyền.
- Việc đổi trạng thái được commit và cache/authorization view được invalidated theo SLA.

Ví dụ SQL tương đương:

```sql
UPDATE document_share_grants
SET revoked_at = :now
WHERE id = :grant_id
  AND document_id = :document_id
  AND tenant_id = :verified_tenant
  AND revoked_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM documents d
      WHERE d.id = document_share_grants.document_id
        AND d.tenant_id = :verified_tenant
        AND d.owner_subject_id = :actor_subject
  );
```

SQL trên là **minh họa**, không giả định cú pháp `UPDATE ... EXISTS` giống nhau trên mọi DB. Thực tế có thể có quyền grantor/admin và quy tắc khác. Quan trọng là điều kiện resource/tenant/actor được bảo vệ **ngay khi update**, tránh chỉ kiểm tra một grant ID tự khai.

Nếu update ảnh hưởng 0 row, nguyên nhân có thể là grant không tồn tại, đã bị revoke hoặc actor không đủ quyền. API có thể trả `204` idempotent hoặc `404` trung tính theo hợp đồng; không để response phân biệt grant của tenant khác nếu thông tin đó bí mật.

## 13. Spring ACL: thời hạn không tự nằm trong ACE

Spring Security ACL mô hình hóa:

- `ObjectIdentity`: domain object.
- `Sid`: principal hoặc authority nhận quyền.
- `Permission`: bit mask hành động.
- `AccessControlEntry`: granting/denying cho SID+permission trên ACL.
- `Acl.isGranted(...)`/`PermissionGrantingStrategy`: đánh giá ACE.

Ví dụ tạo ACE READ cho Bob:

```java
acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    new PrincipalSid("bob"),
    true
);
aclService.updateAcl(acl);
```

Đây là **fragment**, cần `MutableAcl` và `MutableAclService` cùng ACL có sẵn. ACE READ cho Bob mặc định **không biết expiresAt**. Nếu ứng dụng lưu thêm một `ShareGrant` có thời hạn, phải bảo đảm **cả hai lớp được phối hợp**:

- Nếu ACE grant READ còn tồn tại nhưng ShareGrant đã hết hạn, liệu `hasPermission(...)` thuần có còn cho Bob đọc? **Có thể có**, nếu ACE vẫn grant và không có điều kiện thời gian bổ sung.
- Nếu ứng dụng chỉ dùng grant store và custom policy, ACE có thể không cần được tạo cho mỗi lần chia sẻ.
- Nếu đồng bộ grant vào ACL, khi expiry/revoke phải thu hồi hoặc làm cho policy thời gian luôn được kiểm tra trước khi cho phép; một job chạy trễ không nên tạo cửa sổ truy cập trái quyền.

**Khuyến nghị:** chọn một **nguồn sự thật** cho sharing grant; nếu tích hợp với ACL, tránh hai bộ quyền có thể lệch nhau. Chỉ gỡ ACE bằng scheduled cleanup không đảm bảo hết hạn đúng mốc — job có thể chạy trễ, bị lỗi hoặc một node còn cache ACL cũ.

## 14. Link chia sẻ và bearer capability

Không phải mọi chia sẻ đều gửi cho tài khoản đã đăng nhập. Một số sản phẩm phát URL:

```text
https://example.invalid/share/<opaque-secret>
```

Token/link này thường là **bearer capability**: ai có secret được phép dùng những khả năng do link đại diện trong phạm vi thiết kế. Nó khác `recipientSubjectId=bob`, nơi server luôn biết Bob đang đăng nhập.

### Thiết kế một link an toàn

1. Tạo token bằng **CSPRNG** với entropy đủ lớn; dùng chuỗi opaque, không phải `documentId` tăng dần hoặc Base64 của ID.
2. Chỉ lưu **hash của token** trong database nếu có thể; so sánh theo cơ chế phù hợp, không log raw token.
3. Ràng buộc token với **một resource ID** và permission cụ thể như `DOWNLOAD`.
4. Lưu `validFrom`, `expiresAt`, `revokedAt` và các giới hạn tùy chọn.
5. Áp dụng HTTPS, không đưa token vào analytics, log, referrer ra domain khác hoặc message công khai.
6. Dùng response headers/`Referrer-Policy` phù hợp để tránh URL token bị tiết lộ.
7. Thiết lập rate limit và phát hiện thử token nếu endpoint public.
8. Định nghĩa cách thu hồi tức thì qua datastore/token blacklist khi cần.
9. Không nhúng owner/tenant/permission từ client vào token để server tin trực tiếp; các claim ký số cũng phải được xác minh phạm vi, issuer, audience và revocation theo mô hình.
10. Cân nhắc yêu cầu người nhận đăng nhập, password/OTP thứ hai hoặc hạn chế IP với tài liệu nhạy cảm.

Ví dụ hashing opaque token dùng SHA-256 có thể hợp lý khi token đủ entropy; không dùng hash nhanh thay thế password hashing cho **mật khẩu do người dùng chọn**. Với link có token ngắn/dễ đoán, hashing không sửa được vấn đề entropy gốc.

### Presigned URL tới object storage

S3/GCS presigned URL thường cho phép download trực tiếp tới storage đến khi URL hết hạn hoặc credential/policy làm nó vô hiệu. Nếu Alice revoke một grant trong database nhưng Bob đã có presigned URL còn hạn, Bob **có thể vẫn tải được** nếu storage không biết trạng thái revoke.

Nếu requirement là “revoke có hiệu lực ngay”:

- Dùng endpoint download qua backend kiểm tra grant mỗi request, hoặc
- Dùng presigned URL cực ngắn với rủi ro còn tồn tại được công bố, hoặc
- Áp dụng cơ chế storage-level revocation phù hợp.

Không hứa mọi link vừa cấp sẽ bị vô hiệu ngay chỉ vì `revokedAt` được đặt trong DB nghiệp vụ.

## 15. Delegated authorization và OAuth2/JWT: các thời hạn khác nhau

Từ “ủy quyền” đôi khi nói về **resource sharing** giữa hai người dùng; đôi khi nói về **OAuth 2.0 delegated access** cho một ứng dụng third-party. Chúng liên quan nhưng **không đồng nhất**.

Ví dụ:

- Alice cho ứng dụng báo cáo quyền `reports:read`.
- Authorization Server phát access token có scope, audience, expiry.
- Resource Server của Spring Security xác minh token và quyền tương ứng.
- Khi API yêu cầu `GET /documents/42`, server vẫn phải kiểm tra **Alice hoặc app được phép đọc Document 42 hay không** nếu dữ liệu được phân quyền theo đối tượng.

Access token còn hiệu lực không tự biến mọi document thành dữ liệu được truy cập. JWT claims có thể phản ánh scopes và thời hạn token, nhưng quyền chia sẻ theo object thường biến động hơn.

### exp, nbf, iat

Trong JWT:

- `exp`: token **không được chấp nhận vào hoặc sau** thời điểm hết hạn; `now < exp`.
- `nbf`: token không được chấp nhận trước thời điểm bắt đầu; `now >= nbf`.
- `iat`: thời điểm phát hành, **không tự quyết định** thời hạn grant.
- `aud` và `iss`: hạn chế audience và issuer, phải được kiểm tra theo cấu hình.

Spring Security OAuth2 Resource Server hỗ trợ xác minh signature, issuer và mốc `exp`/`nbf` trong cấu hình phù hợp. Clock skew khi xác thực token có thể được cấu hình ở validator. Tuy nhiên **quyền object-level vẫn phải kiểm tra ở resource server**.

### Revoke trước khi JWT hết hạn

JWT ký số tự chứa có thể tiếp tục được xác thực cho đến `exp` dù quyền chia sẻ trên database đã revoke. Các lựa chọn:

1. Mỗi request tra ACL/grant DB để xác định quyền hiện tại.
2. Access token ngắn hạn và refresh token có cơ chế thu hồi, chấp nhận độ trễ được thiết kế.
3. Introspection/opaque token hoặc một dịch vụ quyết định quyền có thể cập nhật.
4. Denylist hoặc authorization version/epoch, cần kiểm tra tại runtime.
5. Thu hồi quyền ở API, không chỉ ở token issuance.

**Không** nghĩ việc đổi password hoặc logout chắc chắn làm mọi JWT đã phát và mọi presigned URL tức thì vô hiệu. Điều đó tùy token validation, denylist, session và cơ chế của provider.

## 16. Phân quyền theo thời gian và truy vấn SQL

Với named-recipient grant, một truy vấn đúng có thể kiểm tra:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.id = :document_id
  AND d.tenant_id = :verified_tenant
  AND d.deleted = FALSE
  AND (
       d.owner_subject_id = :authenticated_subject
       OR EXISTS (
           SELECT 1
           FROM document_share_grants g
           WHERE g.document_id = d.id
             AND g.tenant_id = d.tenant_id
             AND g.recipient_subject_id = :authenticated_subject
             AND g.permission = 'READ'
             AND g.revoked_at IS NULL
             AND g.valid_from <= :now_utc
             AND g.expires_at > :now_utc
       )
  );
```

Đây là **mẫu SQL logic**, cần map đúng schema/DB; cũng cần ràng buộc trạng thái account, tenant membership và các field business khác tùy yêu cầu. Vì kiểm tra owner/share nằm trong **cùng query dữ liệu**, có thể giảm tình huống check grant trước rồi đọc dữ liệu rộng ở query sau.

**Ưu thế:** khi quyền/share hết hiệu lực, truy vấn không trả object; với dữ liệu nhạy cảm, điều kiện này là defense in depth bên cạnh `@PreAuthorize`.

**Cẩn trọng:** Nếu query chạy lúc `now=09:59:59` rồi trả dữ liệu lúc `10:00:01`, “hết hạn tại 10:00” không nhất thiết kéo ngược nội dung đã đọc. Phải định nghĩa chính sách ở **thời điểm quyết định** và quy tắc cho streaming/long-running operations. Muốn ngắt luồng download đang diễn ra đúng mốc cần thiết kế hỗ trợ hủy streaming; phần lớn API có ý nghĩa “quyền được kiểm tra tại lúc bắt đầu thao tác” thay vì giám sát liên tục từng byte.

### Cập nhật dữ liệu phải có điều kiện riêng

Một grant READ không đủ cho WRITE. Nếu có EDIT tạm thời:

```sql
UPDATE documents d
SET title = :new_title
WHERE d.id = :document_id
  AND d.tenant_id = :verified_tenant
  AND d.deleted = FALSE
  AND EXISTS (
      SELECT 1
      FROM document_share_grants g
      WHERE g.document_id = d.id
        AND g.tenant_id = d.tenant_id
        AND g.recipient_subject_id = :authenticated_subject
        AND g.permission = 'EDIT'
        AND g.revoked_at IS NULL
        AND g.valid_from <= :now_utc
        AND g.expires_at > :now_utc
  );
```

Đây là **mô hình SQL**, không cam kết mọi DB hỗ trợ cùng cú pháp `UPDATE ... alias ... EXISTS`; có thể dùng correlated subquery/CTE hoặc repository update tương ứng. Cần bổ sung kiểm tra authority chức năng, optimistic version, status, field-level authorization, audit và transaction phù hợp.

Nếu update ảnh hưởng 0 row, không mặc định cấp quyền; phân biệt lỗi 404/403/409 theo API contract nhưng không rò sự tồn tại tài nguyên. Với operation quan trọng, điều kiện quyền nên được giữ sát lệnh ghi để giảm TOCTOU.

## 17. Thời gian và cache: nơi quyền hết hạn hay bị kéo dài ngoài ý muốn

Giả sử Bob đọc Document #42 lúc 09:59; hệ thống cache `canRead(bob,42)=true` trong 15 phút. Đến 10:00 grant đã hết hạn nhưng cache vẫn trả true đến 10:14. Đây là lỗi cache authorization.

**Đừng cache quyết định GRANT mà không ràng buộc theo thời gian hợp lệ.** Nếu cache:

```text
positiveTTL <= min(
    configuredMaxTTL,
    expiresAt - now,
    khoảng thời gian cho phép chậm revoke
)
```

Ngay cả công thức này cũng chỉ xử lý **expiry**, không giải quyết revoke giữa kỳ nếu không có invalidation/event hoặc kiểm tra nguồn sự thật mỗi request. Với dữ liệu nhạy cảm, cân nhắc không cache quyết định grant, hoặc cache ở tầng grant object có kiểm tra lại thời hạn/revoked và version.

Những bẫy khác:

- Cache key chỉ có `documentId`, bỏ `subjectId`/`tenantId`/`permission`.
- Cache của admin được dùng cho user bình thường.
- Cache grant còn sống sau khi document chuyển owner hoặc bị xóa.
- Search index/listing/cache count trả các object từng được chia sẻ nhưng nay đã hết hạn.
- Browser/CDN cache một tài liệu đã chia sẻ thành public content.
- Frontend giữ dữ liệu đã tải trước lúc revoke: server không thể thu hồi dữ liệu đã rời khỏi hệ thống.

Nếu yêu cầu chia sẻ tạm thời đi kèm confidentiality cao, cần xem cả dữ liệu đã được download/copy, offline access, watermark và điều khoản sử dụng; phân quyền chỉ chặn **truy cập trong tương lai**, không xóa được mọi bản sao đã nhận.

## 18. Thời hạn ngắn, thao tác dài và race

Các ca cạnh tranh cần chủ động thiết kế:

### 18.1. Grant bị revoke giữa kiểm tra và trả dữ liệu

```text
T1: check grant -> true
T2: owner revokes grant
T1: database read / stream response
```

Nếu hệ thống yêu cầu “không có đọc mới sau commit revoke”, cân nhắc transaction snapshot, lock/version hoặc truy vấn hợp nhất quyền + dữ liệu. Nếu muốn **ngắt request đang thực hiện**, cần thêm cơ chế theo dõi/hủy riêng và xác định ordering guarantee.

### 18.2. Grant hết hạn giữa transaction

Một request update bắt đầu lúc `09:59:59` nhưng commit lúc `10:00:01`. Quyền được kiểm tra tại lúc bắt đầu, lúc lệnh UPDATE, hay lúc commit? Không có câu trả lời duy nhất do framework tự đặt. Thiết kế nên ghi rõ điểm thời gian ra quyết định và dùng cùng `Instant`/isolation cho các thao tác được gộp. Với tài chính hoặc dữ liệu nhạy cảm, có thể cần kiểm tra lại sát commit hoặc cơ chế DB atomic đáng tin.

### 18.3. Hai người cùng gia hạn/revoke

Nếu Alice revoke một grant trong lúc Bob hoặc một tác nhân có quyền khác gia hạn nó, phải xác định chính sách:

- Revoke là trạng thái cuối (không re-activate).
- Gia hạn sau revoke bắt buộc tạo grant mới.
- Optimistic locking/version ngăn last-write-wins vô tình bật lại quyền.
- Audit lưu ai sửa, khi nào và yêu cầu nào tạo thay đổi.

### 18.4. Grant chuỗi ủy quyền

Alice ủy quyền cho Bob đến 10:00; Bob chia sẻ tiếp cho Carol đến 11:00. Nếu sản phẩm cho phép subdelegation, Carol **không được có quyền lâu hơn Bob** trừ khi có nguồn quyền độc lập/approval hợp lệ. Điều kiện kỳ hạn có thể là:

```text
child.expiresAt <= parent.expiresAt
child.permissions subsetOf parent.delegablePermissions
child.resourceId == parent.resourceId
parent.revoked => child ineffective (theo policy)
```

Nếu hỗ trợ revoke dây chuyền, có thể cần lưu `parentGrantId` và kiểm tra cả chuỗi khi authorize, hoặc xử lý cascade an toàn. Tránh mô hình có chu kỳ delegation và cơ chế “người nhận tự cấp lại cho mình” kéo dài vô hạn.

## 19. Chia sẻ external, thư mời và bảo vệ trước enumeration

Named-recipient grant nội bộ thường dựa trên `recipientSubjectId` đã tồn tại. Nhưng chia sẻ qua email có thể xảy ra trước khi người nhận tạo tài khoản. Nên phân biệt:

- **Invitation**: lời mời chưa được chấp nhận; chưa tự động cấp quyền trên tài liệu cho bất kỳ identity nào.
- **Accepted grant**: người nhận đã chứng minh quyền sở hữu danh tính/email theo quy trình được duyệt và grant gắn với subject ổn định.
- **Public/bearer link**: secret cấp một khả năng trong phạm vi giới hạn; không cần giả định biết account identity.

Nếu Alice nhập email `bob@example.test`:

1. Server chỉ cho phép Alice mời trong policy SHARE phù hợp.
2. Email không tự chứng minh người sẽ click là Bob nếu link có thể bị forward.
3. Lời mời có token entropy cao, TTL ngắn, giới hạn hành động ACCEPT.
4. Nếu yêu cầu login, sau login xác nhận email/identity tương ứng theo quy tắc an toàn.
5. Khi accept, tạo grant gắn subject thực; ghi audit, không lộ danh sách tài khoản có tồn tại hay không.
6. Không cấp quyền chỉ vì một `recipientEmail` xuất hiện trong request.

Về response, có thể dùng thông báo trung tính khi email không có tài khoản, để tránh user enumeration. Đừng vô tình tiết lộ danh sách tài liệu hoặc tenant qua metadata email, URL preview hay việc redirect.

## 20. Ví dụ Java 17 chạy độc lập: thời hạn và thu hồi

Chương trình dưới đây **không dùng Spring Security/DB**. Nó minh họa quy tắc grant theo identity, object ID, action, tenant, cửa sổ hiệu lực nửa mở và revoke. Clock được cố định bằng `Clock.fixed` để stdout chính xác và test chạy ngay, không dùng `Thread.sleep`.

Tạo file `TimedShareGrantDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;

public class TimedShareGrantDemo {

    record Actor(String id, String tenant, Set<String> authorities) {}
    record Document(long id, String tenant, String owner, boolean deleted) {}
    record Grant(long documentId, String recipient, String permission,
                 Instant validFrom, Instant expiresAt, Instant revokedAt) {}

    static boolean allowed(Actor actor, Document document,
                           String permission, Instant now, Grant grant) {
        if (actor == null || document == null || document.deleted()
                || !actor.tenant().equals(document.tenant())
                || !actor.authorities().contains("document:"
                    + permission.toLowerCase())) {
            return false;
        }

        if (actor.id().equals(document.owner())) {
            return true;
        }

        return grant != null
            && grant.documentId() == document.id()
            && grant.recipient().equals(actor.id())
            && grant.permission().equals(permission)
            && grant.revokedAt() == null
            && !now.isBefore(grant.validFrom())
            && now.isBefore(grant.expiresAt());
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-05T09:00:00Z");
        Clock clock = Clock.fixed(start, ZoneOffset.UTC);

        Actor alice = new Actor("alice", "tenant-a",
            Set.of("document:read", "document:edit"));
        Actor bob = new Actor("bob", "tenant-a",
            Set.of("document:read", "document:edit"));
        Actor carol = new Actor("carol", "tenant-b",
            Set.of("document:read"));
        Document document = new Document(42, "tenant-a", "alice", false);

        Grant readGrant = new Grant(
            42, "bob", "READ", clock.instant(),
            clock.instant().plusSeconds(300), null);

        System.out.println("Bob at start: " + allowed(
            bob, document, "READ", start, readGrant));
        System.out.println("Bob before expiry: " + allowed(
            bob, document, "READ",
            start.plusSeconds(299), readGrant));
        System.out.println("Bob at expiry: " + allowed(
            bob, document, "READ",
            start.plusSeconds(300), readGrant));
        System.out.println("Bob cannot edit: " + allowed(
            bob, document, "EDIT",
            start.plusSeconds(60), readGrant));

        Grant revoked = new Grant(
            42, "bob", "READ", start,
            start.plusSeconds(300), start.plusSeconds(120));
        System.out.println("Bob after revocation: " + allowed(
            bob, document, "READ",
            start.plusSeconds(121), revoked));

        System.out.println("Carol other tenant: " + allowed(
            carol, document, "READ",
            start.plusSeconds(60), readGrant));
        System.out.println("Alice owner: " + allowed(
            alice, document, "READ",
            start.plusSeconds(300), null));
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac TimedShareGrantDemo.java
java TimedShareGrantDemo
```

Stdout chính xác:

```text
Bob at start: true
Bob before expiry: true
Bob at expiry: false
Bob cannot edit: false
Bob after revocation: false
Carol other tenant: false
Alice owner: true
```

Giải thích:

- Bob được READ tại `validFrom`, và ngay trước `expiresAt`.
- Đúng tại `expiresAt`, Bob bị từ chối do `now < expiresAt` không còn đúng.
- Grant READ không cấp EDIT dù Bob có authority chức năng `document:edit`.
- Grant có `revokedAt` đã được đặt thì không còn hiệu lực (ví dụ mã giả định revoke ngay).
- Carol khác tenant bị từ chối dù biết đúng document ID và có authority READ.
- Alice là owner và có READ theo chính sách mẫu; quyền owner không được xem như một share grant tự hết hạn.

**Giới hạn mô phỏng:** không có AOP, JWT, database, concurrency, cache hoặc logic kiểm soát ai có quyền phát grant. Hàm `allowed` mô tả **policy truy cập**, không triển khai **policy cấp/revoke grant**. Trong production phải kết hợp Spring Security/DB, account-state checks, tenant membership, transaction và các cơ chế thu hồi nêu ở trên.

## 21. Kiểm thử toàn diện: thời gian, danh tính, quyền và thu hồi

### 21.1. Bảng quyết định theo thời gian

Dùng một `Clock.fixed(...)` trong test và inject vào policy.

| Thời điểm | Trạng thái grant | Kỳ vọng |
| --- | --- | --- |
| `now < validFrom` | Chưa bắt đầu | DENY |
| `now == validFrom` | Bắt đầu | GRANT nếu các điều kiện khác đúng |
| `validFrom < now < expiresAt` | Trong cửa sổ | GRANT nếu chưa revoke |
| `now == expiresAt` | Đúng mốc hết hạn | DENY |
| `now > expiresAt` | Quá hạn | DENY |
| `revokedAt != null` | Đã thu hồi | DENY |
| `expiresAt <= validFrom` | Grant không hợp lệ | Không cho tạo grant |
| `expiresAt == null` | Không có mốc kết thúc | DENY hoặc reject theo policy có thời hạn bắt buộc |
| Clock lệch giữa các node | Không nhất quán | Kiểm tra nguồn giờ và SLA |
| Cache còn grant sau expiry | Stale allow | DENY, không dựa vào cache positive cũ |

### 21.2. Bảng quyết định theo actor, resource và action

| Tình huống | Kỳ vọng |
| --- | --- |
| Bob có READ grant cho #42 và authenticated | Cho phép READ trong thời hạn |
| Bob có READ grant cho #42 nhưng muốn EDIT | Từ chối EDIT |
| Bob có READ grant cho #42 nhưng gọi #43 | Từ chối trên #43 |
| Carol thuộc tenant khác, không có external grant policy | Từ chối |
| Alice là owner nhưng bị khóa account | Từ chối theo account state |
| Tài liệu bị xóa/archived/classified | Từ chối hoặc áp rule mới; không chỉ nhìn grant |
| Một user khác đoán đúng grantId | Không được dùng/thu hồi grant không thuộc quyền |
| Grantor không có SHARE | Không được tạo grant |
| Recipient không hợp lệ | Không tạo grant |
| Grantor muốn grant permission vượt scope | Không tạo grant |
| Grantor muốn expiry quá giới hạn | Reject |
| Owner revoke grant khi recipient đang mở màn hình | Truy cập mới bị từ chối theo SLA; dữ liệu đã tải cần xử lý riêng |
| Chỉ một route HTTP có method security, route khác đọc cùng service | Tất cả đường gọi phải áp policy |
| Batch với nhiều document IDs | Kiểm tra grant cho **từng ID**; không cấp cho cả batch từ một grant |

### 21.3. Test Spring Security thật

Đừng chỉ gọi `SharingPolicy.canRead(...)` trong unit test. Tạo integration test với:

- `@EnableMethodSecurity` thực sự bật.
- Spring-managed service proxy; tránh test chỉ bằng `new DocumentReadService(...)`.
- `MockMvc` hoặc HTTP client có security filter chain.
- `@WithMockUser`/JWT fixtures tương ứng identity **thật** của ứng dụng.
- Test DB riêng chứa Document và ShareGrant khác nhau.
- Đồng hồ có thể thay bằng `Clock.fixed(...)`.
- Assertions cho dữ liệu, body, status, rows cập nhật và side effects.
- Trường hợp guest/anonymous/JWT `exp`, `nbf` và issuer/audience sai.
- Revoke bằng một request, sau đó read bằng request khác, kể cả trên **node khác** nếu chạy cluster.

Test revoke “sau khi save” không đủ nếu cache vẫn còn cho đọc. Nên có test cập nhật/revoke với cache đang nóng và xác minh quyền bị thu hồi ở từng instance.

### 21.4. Kiểm thử đồng thời

Tạo test hai thread/transaction:

1. Request Bob bắt đầu đọc.
2. Alice revoke grant.
3. Database commit revoke.
4. Bob gửi một request mới sau commit.
5. Verify request mới bị từ chối trong SLA đã hứa.

Với thao tác ghi, test một grant EDIT vừa hết hạn đúng lúc UPDATE/commit. Kiểm tra DB không bị sửa trái quyền và không có event/file đã publish khi việc ghi thất bại. Nếu business cần serializable authorization, dùng transaction/isolation/locking hoặc điều kiện trong SQL; không hy vọng `@Transactional` mặc định giải quyết mọi race.

## 22. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gắn `share=true` trên Document rồi cho mọi người dùng được đọc | Không xác định ai, action hay thời hạn | Lưu grant theo recipient, resource, permission và thời gian |
| Chỉ kiểm tra role `USER` của Bob | Bob có thể xem tài liệu khác | Kiểm tra đúng document ID và grant |
| Nhận `grantorId` từ JSON | Kẻ gọi giả làm owner | Lấy grantor từ Authentication đã xác minh |
| Cho người chỉ READ phát grant ADMIN | Leo thang đặc quyền | Yêu cầu SHARE và giới hạn delegable permissions |
| Cho phép `expiresAt` bất kỳ từ client | Chia sẻ vô hạn | Bound theo server policy, reject giá trị bất hợp lệ |
| So sánh `now <= expiresAt` | Vẫn cấp quyền đúng lúc hết hạn | Dùng `now < expiresAt` |
| Tin giờ máy người dùng | User chỉnh đồng hồ | Server Instant/Clock, đồng bộ thời gian |
| Dùng LocalDateTime không rõ timezone | Hết hạn sai do DST/múi giờ | Lưu Instant/UTC, convert ở UI |
| Chỉ chờ cron xóa grant hết hạn | Job trễ vẫn còn quyền | Kiểm tra expiry ngay mỗi lần authorize |
| Chỉ đặt TTL cho JWT rồi cho là share có TTL | Token và grant là hai thời hạn khác nhau | Kiểm tra grant riêng, có revoke |
| Revoke DB nhưng giữ cache GRANT 30 phút | Truy cập sau revoke | Invalidate và thiết kế consistency/SLA |
| Cấp presigned URL lâu hạn rồi tuyên bố revoke tức thì | Link vẫn dùng được tới expiry | Brokered download hoặc URL rất ngắn + policy storage |
| Tạo ACE READ rồi không kiểm tra thời hạn | ACE vẫn grant sau expiry | Dùng policy/grant nguồn sự thật; thu hồi ACE/cache đúng lúc |
| Dựa vào mã ID của share để xác thực | ID dễ đoán và không phải secret | Yêu cầu identity hoặc opaque CSPRNG token |
| Dùng bearer link trong log/analytics | Secret bị rò | Redact logs, giới hạn referrer, TTL/revoke |
| Check SHARE trên Document #42 nhưng tạo grant cho #43 | IDOR khi quản trị quyền | Kiểm tra cùng resource ID xuyên suốt transaction |
| Cho subdelegation vượt expiry của grant cha | Kéo dài quyền trái ý định | Child expiry <= parent, cascade revoke |
| Cấp READ grant rồi trả mọi property của entity | Lộ dữ liệu nhạy cảm | DTO allowlist và property-level authorization |
| Chỉ bảo vệ GET, bỏ DOWNLOAD/EXPORT/EDIT | Grant lan sang hành động khác | Policy theo action cụ thể |
| Không tính status account/document | Grant tiếp tục hoạt động sau khóa/xóa | Check account, resource, tenant, classification |
| Dùng `@PostAuthorize` để bảo vệ write | Side effect có thể đã commit | Pre-check + conditional mutation + transaction |
| Cache key bỏ tenant/recipient | Cross-user/tenant leak | Key đủ scope hoặc auth mỗi lần cache hit |
| Nuốt DB timeout rồi trả ALLOW | Fail open | Mặc định từ chối, tách lỗi hạ tầng |

## 23. Checklist khi thiết kế chia sẻ tạm thời

1. **Tài nguyên nào?** Type, ID, tenant, owner, parent và trạng thái.
2. **Người chia sẻ là ai?** Identity đã xác minh, quyền SHARE và delegable scope.
3. **Người nhận là ai?** Authenticated subject, group, external guest hay bearer link; mô hình xác minh tương ứng.
4. **Hành động nào được cấp?** READ, COMMENT, EDIT, DOWNLOAD; hạn chế và ghi rõ.
5. **Bắt đầu và kết thúc khi nào?** `[validFrom, expiresAt)`, Instant UTC, max duration.
6. **Có thể thu hồi ngay không?** Cách cập nhật revoke và SLA lan truyền.
7. **Quyền thay đổi do sự kiện nào?** Document delete, owner transfer, account suspension, tenant removal.
8. **Có subdelegation không?** Depth, parentGrantId, permission/expiry ceiling, cascade revocation.
9. **Nguồn sự thật là gì?** ShareGrant DB, ACL hay capability token; tránh chồng chéo không đồng bộ.
10. **Cache có an toàn không?** Expiry-aware, revoke-aware, key theo principal/tenant/action/resource.
11. **Token/link có bí mật không?** CSPRNG, hash, TTL, rate limit, redaction, security headers.
12. **Có file presigned URL không?** Hiểu giới hạn revoke và TTL sau khi phát URL.
13. **Các đường gọi nào cần kiểm tra?** HTTP, GraphQL, message, batch, search, export, streaming.
14. **Query đã được scope chưa?** Không chỉ `findById` rồi tin một grant ID gửi từ client.
15. **Thao tác ghi có nguyên tử không?** Transaction, conditional SQL, race/revocation.
16. **Có audit không?** Ai cấp, ai nhận, permission, expiry, revoke, reason; không log secrets.
17. **Có test đúng mốc thời gian không?** Trước start, tại start, ngay trước và tại expiry.
18. **Có test revoke trên cache nóng và nhiều node không?** Không chỉ test database row.
19. **Có test hành vi thiếu quyền/khác tenant không?** Không lộ dữ liệu hoặc metadata resource.
20. **Có xử lý expiry/token vs grant đúng không?** JWT hết hạn không phải dấu hiệu grant bị xóa; grant hết hạn không được kéo dài bởi JWT còn hạn.

**Kết luận:** Chia sẻ dữ liệu và ủy quyền tạm thời đòi hỏi chính sách theo **actor + action + resource + thời gian + trạng thái thu hồi**. Spring Security cung cấp hạ tầng xác thực, HTTP/method authorization và ACL; ứng dụng vẫn phải cài đặt **grant có phạm vi/thời hạn**, xác minh người cấp có quyền, kiểm tra thời gian ở mỗi lần truy cập, thu hồi/cache nhất quán và ngăn đọc/ghi trái quyền ở tầng dữ liệu. Một grant chỉ hợp lệ khi **đúng người, đúng tài nguyên, đúng hành động và đúng thời điểm**.

## Tài liệu tham khảo chính thức

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, bean policy và cách kiểm tra theo tham số method.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` và kiểm soát truy cập theo ngữ cảnh.
- [Spring Security — ACLs](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): SID/ACE/ObjectIdentity, `PermissionEvaluator` và giới hạn dữ liệu ACE tiêu chuẩn.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): kiểm tra signature, `exp`, `nbf`, issuer và clock skew.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): ý nghĩa `exp`/`nbf`/`iat` và ranh giới thời gian.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, kiểm tra quyền mỗi request, phân quyền theo tài nguyên.
- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object-level authorization và scoped lookup.
- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm tra quyền trên từng object ID.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): nguyên tắc token bí mật có entropy, hạn dùng, single-use phù hợp khi áp dụng cho lời mời/token bảo mật.
