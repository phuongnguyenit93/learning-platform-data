# Spring Security ACL: Sid, ObjectIdentity, Permission và AccessControlEntry

Trong một ứng dụng Spring Security Servlet, người dùng Alice và Bob đều có `ROLE_USER`. Kiểm tra `hasRole("USER")` giúp xác nhận rằng họ thuộc nhóm người dùng, nhưng **không đủ để bảo đảm Alice chỉ đọc tài liệu của Alice**. Nếu API nhận mã tài liệu từ URL rồi truy vấn và trả về ngay, việc thay ID trong URL có thể dẫn đến **Broken Object Level Authorization (BOLA/IDOR)**.

**Spring Security ACL (Access Control List)** là một mô hình phân quyền cho **từng đối tượng nghiệp vụ**, chẳng hạn từng tài liệu, hóa đơn, nhiệm vụ hoặc thư mục. Một ACL cho phép mô tả người dùng nào, vai trò nào, có quyền gì trên object cụ thể và trong trường hợp cần thiết quyền nào bị từ chối.

Bốn khái niệm trung tâm:

- **Sid (Security Identity):** chủ thể áp dụng quyền. Ví dụ người dùng `alice` hoặc authority `ROLE_REVIEWER`.
- **ObjectIdentity:** đối tượng nào được bảo vệ. Ví dụ loại `com.example.acl.Document`, ID `101`.
- **Permission:** thao tác cần bảo vệ, ví dụ READ, WRITE, DELETE, được biểu diễn bằng bit mask.
- **AccessControlEntry (ACE):** bản ghi kết hợp một Sid và Permission trong ACL của đối tượng, cùng trạng thái **grant/deny**, thứ tự và audit flags.

Các ACE tập hợp trong một đối tượng `Acl`. `AclService` tải ACL, `MutableAclService` cho phép quản lý dữ liệu ACL, còn `AclPermissionEvaluator` có thể gắn việc tra cứu quyền vào method security qua biểu thức `hasPermission(...)`.

Bài học thuộc nhóm **Quyền tài nguyên**, dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet**. Ta sẽ học khái niệm, cơ chế đánh giá ACL, schema JDBC bốn bảng, cấp/thu hồi quyền, method security, ranh giới tenant, cache, inheritance, testing và một ví dụ Java 17 độc lập. Nội dung Spring ACL ở dạng code fragment cần thư viện và cấu hình persistence; những chỗ không phải chương trình chạy độc lập đều được chú thích rõ.

**Giới hạn quan trọng:** thêm dependency `spring-security-acl` không tự bật object authorization cho mọi URL. Ứng dụng phải tạo ACL đúng, thực thi kiểm tra quyền trên tất cả đường truy cập tài nguyên cần bảo vệ, và giải quyết sai lệch giữa dữ liệu object, tenant, identity và cache.

## 1. Khác nhau giữa role và quyền đối tượng

Ví dụ ba documents:

| Tài nguyên | Tenant | Owner | Ai được READ? | Ai được WRITE? |
| --- | --- | --- | --- | --- |
| Document#101 | north | alice | alice, auditor theo policy | alice |
| Document#102 | north | bob | bob | bob |
| Document#201 | south | carol | carol | carol |

Với rule chung:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").hasRole("USER")
    .anyRequest().denyAll());
~~~

Alice chỉ cần có ROLE_USER là có thể qua cổng HTTP, **bất kể ID document nào**. Nếu controller không có object-level check, API có lỗ hổng. Một chính sách cần kiểm tra:

~~~text
1. Request đã xác thực chưa?
2. User có thuộc tenant của document không?
3. User đang yêu cầu hành động nào: READ hay WRITE?
4. ACL của chính Document#101 có grant Permission cho Sid user/role không?
5. Nếu không có grant hợp lệ, hoặc dữ liệu bị thiếu: DENY.
~~~

Một ACL có thể mô tả:

~~~text
Document#101
    PrincipalSid("alice")         READ  GRANT
    PrincipalSid("alice")         WRITE GRANT
    GrantedAuthoritySid("ROLE_AUDITOR") READ GRANT

Document#102
    PrincipalSid("bob")           READ  GRANT
    PrincipalSid("bob")           WRITE GRANT
~~~

ACL không phải cách duy nhất giải quyết object-level security. Với policy chỉ có owner và tenant đơn giản, truy vấn database ràng buộc `tenant_id` và `owner_id` có thể phù hợp hơn. ACL hữu ích khi có **chia sẻ tài nguyên cho từng cá nhân, nhóm hoặc quyền ngoại lệ**, và ứng dụng sẵn sàng quản lý lifecycle quyền.

## 2. Sid — ai được áp dụng quyền?

`Sid` là abstraction cho Security Identity trong ACL. Các implementation chính:

- `PrincipalSid`: một principal xác định, thường là username hoặc user identifier do server quản lý.
- `GrantedAuthoritySid`: một GrantedAuthority, thường được chia sẻ bởi nhiều người, ví dụ `ROLE_AUDITOR`.

~~~java
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;

Sid alice = new PrincipalSid("alice");
Sid auditTeam = new GrantedAuthoritySid("ROLE_AUDITOR");
~~~

Đây là fragment Java phụ thuộc `spring-security-acl`. Sid khác với toàn bộ `Authentication`: Authentication mang principal, credentials/authorities/trạng thái xác thực; Sid là **một khóa danh tính phù hợp cho ACE**.

Khi user thực hiện request, ACL permission evaluator có thể lấy danh sách Sids từ Authentication:

~~~text
Authentication:
  principal = alice
  authorities = [ROLE_USER, ROLE_AUDITOR]

Derived Sids:
  PrincipalSid("alice")
  GrantedAuthoritySid("ROLE_USER")
  GrantedAuthoritySid("ROLE_AUDITOR")
~~~

**Không tin Sid do client tự chỉ định.** Ví dụ gửi `?user=admin`, `X-Role: ROLE_ADMIN` hoặc payload chứa `tenantId` không đủ để chứng minh authentication. Chủ thể được dùng để kiểm tra quyền phải lấy từ identity provider và dữ liệu membership đáng tin của server.

### Username và multi-tenant

Nếu username đổi tên hoặc có thể trùng giữa tenants, lưu Sid theo display username là rủi ro. Production nên dùng khóa danh tính **duy nhất và bền vững** hoặc có quy tắc namespacing/migration tường minh; cùng một Sid string ở hai tenants có thể vô tình trùng quyền nếu không có tenant boundary.

### PrincipalSid và GrantedAuthoritySid không thay thế nhau

| Loại Sid | Phạm vi | Ví dụ |
| --- | --- | --- |
| PrincipalSid | Cá nhân cụ thể | alice được READ Document#101 |
| GrantedAuthoritySid | Những Authentication có authority này | ROLE_REVIEWER được READ Document#101 |

Nếu Bob được cấp ROLE_REVIEWER trong một session còn sống, Bob có thể được quyền thông qua ACE role. Khi revoke authority ở identity store, Authentication hiện tại có thể vẫn giữ authority cũ cho đến khi được refresh/reauthenticated, trừ khi ứng dụng thiết kế thu hồi realtime.

## 3. ObjectIdentity — đối tượng nào được bảo vệ?

`ObjectIdentity` mang **loại đối tượng (type/class)** và **ID**:

~~~java
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.domain.ObjectIdentityImpl;

ObjectIdentity document =
    new ObjectIdentityImpl(Document.class, 101L);

ObjectIdentity invoice =
    new ObjectIdentityImpl(Invoice.class, 101L);
~~~

Hai identity khác nhau dù cùng ID số 101. Đây là fragment; `Document` và `Invoice` do domain của ứng dụng định nghĩa.

Một mapping phổ biến:

~~~text
ObjectIdentity(Document.class, 101L)
    |
    +--> acl_class.class = "com.example.acl.Document"
    |
    +--> acl_object_identity.object_id_identity = "101"
~~~

Khi refactor package của class, đổi kiểu ID từ Long sang UUID hoặc đổi cách serialize identity, hãy kiểm tra migration ACL. Nếu database còn type name cũ, quyền có thể không tìm thấy hoặc bị áp sai.

### ObjectIdentity trong multi-tenant

Nếu hai tenants cùng có `Document#101` với ID phát sinh độc lập, chỉ dùng `Document.class + 101L` có thể gây **identity collision**. Cách thiết kế có thể là globally unique IDs, canonical identity có namespace tenant, hoặc tenant-separated ACL repositories; bất kể lựa chọn nào, **tenant boundary phải được thực thi bởi business policy**, không chỉ dựa vào role Sid.

## 4. Permission — hành động được bảo vệ

`Permission` trong Spring ACL thường dùng **bit mask**, thay vì chỉ lưu một nhãn String. `BasePermission` cung cấp bộ quyền thông dụng:

| Permission | Mask | Mục đích điển hình |
| --- | ---: | --- |
| `BasePermission.READ` | 1 | Đọc |
| `BasePermission.WRITE` | 2 | Sửa |
| `BasePermission.CREATE` | 4 | Tạo |
| `BasePermission.DELETE` | 8 | Xóa |
| `BasePermission.ADMINISTRATION` | 16 | Quản trị theo ACL policy |

~~~java
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.domain.BasePermission;

Permission read = BasePermission.READ;
Permission write = BasePermission.WRITE;

System.out.println(read.getMask());  // 1
System.out.println(write.getMask()); // 2
~~~

Đây là fragment. Permission là **hành động trên object**, không phải `ROLE_ADMIN`. `ADMINISTRATION` mask 16 **không tự cấp** ROLE_ADMIN trên mọi URL.

**Không giả định WRITE ngầm bao gồm READ.** Nếu business cần user WRITE được READ, phải cấp ACE tương ứng hoặc thiết kế PermissionGrantingStrategy biểu diễn kế thừa. Không tự coi phép OR bits bằng 3 là một quyền composite được framework mặc định hiểu giống mọi hệ thống; cách so khớp mask phụ thuộc strategy thực tế.

Custom permission như EXPORT/APPROVE có thể dùng masks bổ sung nếu không trùng. Muốn `hasPermission(..., 'EXPORT')` hoạt động, cần mapping `PermissionFactory`/resolver thích hợp; tự tạo enum EXPORT trong domain không đủ.

## 5. AccessControlEntry — bản ghi cho phép hoặc từ chối

`AccessControlEntry` (ACE) nằm trong một `Acl`, chứa:

- `getSid()` — ai?
- `getPermission()` — quyền nào?
- `isGranting()` — grant hay deny?
- `getAcl()` — thuộc ACL nào?
- `getId()` — ID ACE nếu lưu trong persistence.
- `isAuditSuccess()` / `isAuditFailure()` — audit-related flags.

Một ACE mẫu:

~~~text
ObjectIdentity = (com.example.acl.Document, 101)
Sid            = PrincipalSid("alice")
Permission     = READ (mask=1)
Granting       = true
ACE order      = 0
Audit flags    = theo policy
~~~

Quan trọng: **ACE grant/deny khác owner của ACL**. Trường `owner_sid` trong metadata ACL phục vụ mô hình quản lý ACL; nó không tự biến thành READ/WRITE granted ở mọi cấu hình.

### Cấu trúc một Acl

~~~text
Acl(Document#101)
  ownerSid = PrincipalSid("alice")
  entriesInheriting = false
  parentAcl = null

  ACEs theo thứ tự:
    [0] PrincipalSid("alice")          READ  GRANT
    [1] PrincipalSid("alice")          WRITE GRANT
    [2] GrantedAuthoritySid(ROLE_AUDITOR) READ GRANT
~~~

ACL còn mang owner, ObjectIdentity, tùy chọn parent và flag `entriesInheriting`.

| Khái niệm | Câu hỏi |
| --- | --- |
| Sid | Ai? |
| ObjectIdentity | Đối tượng nào? |
| Permission | Làm gì? |
| ACE | Cho phép hay từ chối đối với Sid/Permission trên ACL đó? |
| Acl | Những ACE nào thuộc một đối tượng, ai quản lý, có kế thừa không? |

## 6. Kiểm tra quyền: từ request đến ACE

Một request GET tới document 101 có thể đi qua:

~~~text
GET /api/documents/101
       |
       v
Spring Security Authentication filter
       | -> Authentication alice / ROLE_USER
       v
AuthorizationFilter: route yêu cầu authenticated
       |
       v
Controller -> DocumentService.read(101)
       |
       v
@PreAuthorize("hasPermission(...)") nếu method security bật
       |
       v
AclPermissionEvaluator
       |-- ObjectIdentity(Document,101)
       |-- Sids từ Authentication
       |-- AclService.readAclById(...)
       |-- Permission READ
       |-- PermissionGrantingStrategy xét ACEs/parent
       |
       +-- ALLOW -> chạy method
       +-- DENY / thiếu ACL -> không chạy method
~~~

**Cơ chế này cần cấu hình.** Chỉ viết `@PreAuthorize("hasPermission(...)")` chưa bảo đảm nó tra đúng ACL store nếu `PermissionEvaluator` chưa được gắn vào method security.

### NotFound và UnloadedSid

`AclService.readAclById(...)` có thể không tìm thấy ACL và phát sinh `NotFoundException`. `Acl.isGranted(...)` có thể báo không có ACE khớp hoặc Sids chưa được tải đầy đủ theo contract/implementation. Một số lookup có thể gặp `UnloadedSidException`. Trong mọi trường hợp thiếu bằng chứng quyền, không được tự **fallback allow**.

Tách rõ response HTTP: một lỗi server/database có thể cần trả 5xx theo contract thay vì giả vờ 403, nhưng **hành động nhạy cảm không được chạy** khi không thể xác minh quyền.

### 401, 403 và 404

- User chưa xác thực: HTTP Basic/Bearer thường 401; form login có thể chuyển hướng 302 tới login.
- User đã xác thực nhưng thiếu ACL permission: thường 403 qua method-security exception handling.
- Resource không tồn tại hoặc bị ẩn existence theo policy: có thể 404, nhưng cần thiết kế rõ.
- 404 từ Spring MVC vì route không tồn tại **không chứng minh ACL đã chạy**.

## 7. ACE thứ tự, deny và inheritance

### ACE order có thể ảnh hưởng quyền hiệu lực

Ví dụ:

~~~text
[0] PrincipalSid("bob")     READ DENY
[1] ROLE_AUDITOR             READ GRANT
[2] PrincipalSid("alice")   READ GRANT
~~~

Nếu Bob mang ROLE_AUDITOR thì anh ấy khớp cả ACE deny cá nhân và ACE grant qua authority. **Không tự suy ra** mọi Spring ACL setup đều ưu tiên deny hoặc ưu tiên principal: kết quả phụ thuộc `PermissionGrantingStrategy`, cách duyệt ACE/permissions/Sids và thứ tự entries. Muốn chính sách “deny cá nhân luôn ưu tiên role grant”, phải định nghĩa và **kiểm thử xung đột** trước khi deploy.

Các entries có vị trí trong danh sách; `MutableAcl.insertAce(index,...)` có thể làm thay đổi thứ tự. Khi xóa hoặc cập nhật entry, đừng dùng một index cũ mà không tải và xác minh entry tương ứng.

### Parent ACL và entriesInheriting

Có thể dùng ACL của folder làm parent:

~~~text
Folder#10
  ROLE_TEAM_A READ GRANT
       |
       | child entriesInheriting = true
       v
Document#101
  Alice WRITE GRANT
~~~

Hành vi thực tế phụ thuộc `parentAcl`, flag `entriesInheriting`, entries ở child, granting strategy và Sids đã load. Test riêng local grant/deny, inherited grant/deny và thứ tự xung đột. Không mặc định quyền parent luôn thắng child hoặc child luôn override parent.

**Quan trọng khi xóa:** xóa parent ACL hoặc di chuyển object có thể ảnh hưởng hàng loạt child ACL. `MutableAclService.deleteAcl(objectIdentity, deleteChildren)` cần policy phù hợp; một lần xóa ACL không đồng nghĩa với xóa domain object.

## 8. JDBC ACL: bốn bảng quan hệ

Spring ACL JDBC thường dùng:

1. `acl_sid` — lưu Security Identities (principal/authority).
2. `acl_class` — lưu các object types.
3. `acl_object_identity` — mỗi object protected, owner, parent, inheritance.
4. `acl_entry` — mỗi ACE, thứ tự, mask, grant/deny, audit.

~~~text
acl_sid                      acl_class
  id                           id
  principal                    class
  sid                          |
    |                          |
    +-------------+------------+
                  |
           acl_object_identity
             id
             object_id_class -> acl_class.id
             object_id_identity
             owner_sid -> acl_sid.id
             parent_object -> acl_object_identity.id
             entries_inheriting
                  |
                  v
              acl_entry
                id
                acl_object_identity -> acl_object_identity.id
                ace_order
                sid -> acl_sid.id
                mask
                granting
                audit_success
                audit_failure
~~~

| Trường | Ý nghĩa |
| --- | --- |
| `acl_sid.principal` | Phân biệt principal SID với authority SID |
| `acl_class.class` | Type/class dùng làm ObjectIdentity |
| `acl_object_identity.object_id_identity` | Khóa đối tượng nghiệp vụ |
| `acl_object_identity.owner_sid` | ACL owner |
| `acl_object_identity.parent_object` | ACL cha nếu có |
| `acl_object_identity.entries_inheriting` | Có xét ACL cha theo policy? |
| `acl_entry.ace_order` | Thứ tự ACE của một ACL |
| `acl_entry.mask` | Permission bit mask |
| `acl_entry.granting` | True là grant, false là deny |
| `acl_entry.audit_success/audit_failure` | Audit metadata theo strategy |

### Ví dụ PostgreSQL DDL tham khảo

Đây là lược đồ minh họa **để hiểu quan hệ**. Trước khi chạy migration trên dự án thật, đối chiếu SQL schema và JDBC identity queries của **phiên bản Spring Security ACL/DB được khóa**. Một số versions/dialects có thêm cột, cấu hình identity generation hoặc tên sequence/query khác.

~~~sql
CREATE TABLE acl_sid (
    id BIGSERIAL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR(255) NOT NULL,
    CONSTRAINT uq_acl_sid UNIQUE (principal, sid)
);

CREATE TABLE acl_class (
    id BIGSERIAL PRIMARY KEY,
    class VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE acl_object_identity (
    id BIGSERIAL PRIMARY KEY,
    object_id_class BIGINT NOT NULL
        REFERENCES acl_class(id),
    object_id_identity VARCHAR(255) NOT NULL,
    parent_object BIGINT
        REFERENCES acl_object_identity(id),
    owner_sid BIGINT REFERENCES acl_sid(id),
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_object UNIQUE
        (object_id_class, object_id_identity)
);

CREATE TABLE acl_entry (
    id BIGSERIAL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL
        REFERENCES acl_object_identity(id),
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL REFERENCES acl_sid(id),
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_ace_order
        UNIQUE (acl_object_identity, ace_order)
);
CREATE INDEX idx_acl_entry_object
    ON acl_entry (acl_object_identity);
CREATE INDEX idx_acl_entry_sid
    ON acl_entry (sid);
~~~

Cần xem thêm generated key queries, `AclAuthorizationStrategy`, parent FKs, collations, ID lengths, migration khi rename class, phân vùng tenant, transaction/locking và cache invalidation. Không dùng SQL DDL này làm lời hứa rằng một `JdbcMutableAclService` sẽ chạy ngay trên mọi PostgreSQL/schema phiên bản.

### Đừng tạo ACL bằng SQL client tùy tiện

Khi có API `MutableAclService`, nên dùng nó để tạo ObjectIdentity, gắn Sid, quản lý entries và cache. Nếu chỉnh trực tiếp `acl_entry` mà quên cache hoặc thứ tự, request mới có thể tiếp tục dùng quyết định quyền cũ. Với data migration phải có maintenance plan, invalidation và verification.

## 9. Các API Spring ACL phải nắm

Imports tham khảo:

~~~java
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.model.Permission;

import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
~~~

### Đọc Acl

~~~java
// Fragment: aclService là Spring bean đã được inject.
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 101L);

Acl acl = aclService.readAclById(identity);
System.out.println(acl.getEntries().size());
~~~

Không có ACL record thì service có thể báo NotFoundException; đừng trả `true` vì thiếu record.

### Kiểm tra bằng Acl.isGranted

~~~java
// Fragment có variables acl, authentication hợp lệ.
Sid alice = new PrincipalSid(authentication);
Sid auditor = new GrantedAuthoritySid("ROLE_AUDITOR");

boolean granted = acl.isGranted(
    java.util.List.of(BasePermission.READ),
    java.util.List.of(alice, auditor),
    false
);
~~~

Trong ứng dụng thật phải xét **tất cả authorities đáng tin của Authentication** chứ không chỉ hardcode ROLE_AUDITOR; handle ACL missing/NotFound/UnloadedSid và tenant boundary. Tham số cuối `administrativeMode` không phải công tắc để “bật quyền admin”. Với request thông thường, sử dụng false theo contract phổ biến.

### Tạo ACL và cấp READ/WRITE

~~~java
// Fragment trong transactional Spring service.
// mutableAclService đã là bean, Document.class là type thật.
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 101L);

MutableAcl acl = mutableAclService.createAcl(identity);
Sid alice = new PrincipalSid("alice");

acl.insertAce(acl.getEntries().size(),
              BasePermission.READ, alice, true);
acl.insertAce(acl.getEntries().size(),
              BasePermission.WRITE, alice, true);

mutableAclService.updateAcl(acl);
~~~

**Không coi createAcl là upsert.** Nếu identity đã có ACL, lệnh create có thể thất bại; code nghiệp vụ cần quản lý lifecycle và idempotency. Một ACL mới cũng cần owner SID thích hợp, transaction và rule ai được quyền quản lý ACL.

### Grant cho role

~~~java
Sid reviewers = new GrantedAuthoritySid("ROLE_REVIEWER");
acl.insertAce(acl.getEntries().size(),
              BasePermission.READ, reviewers, true);
mutableAclService.updateAcl(acl);
~~~

Một ACE cho role sẽ áp dụng với users có authority đó theo SidRetrievalStrategy. Không đặt `ROLE_ADMIN` toàn cục vào ACL đa tenant rồi tin rằng “admin tenant nào cũng đúng scope”; kiểm tra tenant riêng.

### Revoke bằng xóa ACE

~~~java
// Fragment: index được xác định sau khi duyệt đúng
// Sid + Permission + grant/deny của ACL hiện tại.
acl.deleteAce(index);
mutableAclService.updateAcl(acl);
~~~

Đừng xóa `index=0` vì nghĩ entry 0 mãi là Alice. Thứ tự entries có thể đổi. Tìm đúng SID/mask và kiểm tra permission hiệu lực **sau** thay đổi, kể cả role grants hoặc parent inheritance.

### Xóa ACL của một object

~~~java
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 101L);

mutableAclService.deleteAcl(identity, false);
~~~

Lệnh trên xóa dữ liệu ACL theo implementation/child-policy, không xóa bản ghi Document nghiệp vụ. Xác định semantics `deleteChildren` và các parent-child relations. Với object đã xóa, dọn ACL tránh orphan/reused IDs bị gắn quyền cũ.

## 10. Kết nối Spring Security ACL với hasPermission

Một biểu thức method security phổ biến:

~~~java
@PreAuthorize(
    "hasPermission(#id, 'com.example.acldemo.Document', 'READ')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Đây là **fragment**, yêu cầu Spring-managed bean, `@EnableMethodSecurity`, import annotation và Bean PermissionEvaluator. Type string cần **khớp ObjectIdentity type** đã dùng khi tạo ACL; nếu class package đổi mà không migrate, ACL lookup có thể fail.

### MethodSecurityExpressionHandler

Một cấu hình Spring Security 6.x:

~~~java
package com.example.acldemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;

@Configuration
@EnableMethodSecurity
public class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclService aclService) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(
            new AclPermissionEvaluator(aclService));
        return handler;
    }
}
~~~

Class này cần các dependencies đúng version và **AclService bean được wiring đầy đủ**, không phải một ứng dụng standalone. Nó nối `hasPermission(...)` tới ACL lookup. Với Spring Security 6, pre/post method security thường được bật mặc định khi dùng `@EnableMethodSecurity`; `@Secured` và Jakarta `@RolesAllowed` có flags riêng nhưng **không phải trọng tâm của ACL**.

### PermissionEvaluator có hai hình thức

~~~java
// Hợp đồng PermissionEvaluator, dạng rút gọn:
boolean hasPermission(Authentication authentication,
                      Object targetDomainObject,
                      Object permission);

boolean hasPermission(Authentication authentication,
                      java.io.Serializable targetId,
                      String targetType,
                      Object permission);
~~~

Dạng `id + type` rõ ràng khi controller mới có Document ID. Dạng truyền object phụ thuộc IdentityRetrievalStrategy và object type/id extraction; không dùng nếu chưa cấu hình/test chính xác.

### Cấu hình persistence cần những gì?

Bên cạnh DataSource/JDBC schema, thường cần:

~~~text
DataSource
  + AclCache
  + PermissionGrantingStrategy
  + AclAuthorizationStrategy
  + LookupStrategy (ví dụ BasicLookupStrategy)
       |
       + JdbcAclService / JdbcMutableAclService
                  |
                  + AclPermissionEvaluator
                         |
                         + MethodSecurityExpressionHandler
~~~

Các implementation thường gặp: `BasicLookupStrategy`, `JdbcAclService`, `JdbcMutableAclService`, `DefaultPermissionGrantingStrategy`, `AclAuthorizationStrategyImpl`. Đây là **sơ đồ bean graph**, không phải lời hứa chúng được auto-configured chỉ bằng dependency. Cần wiring phù hợp với cache, audit logger, JDBC identity queries và SQL dialect đang dùng.

### Maven dependencies tiêu biểu

Trong Spring Boot 3.x project có parent/BOM phù hợp:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-acl</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Bổ sung JDBC driver và version-compatible schema/configuration. Các file Spring yêu cầu framework classpath; chương trình JDK thuần ở mục 15 mới chạy chỉ với Java 17.

## 11. Ví dụ tầng service: đọc Document có ACL

Một domain record:

~~~java
package com.example.acldemo;

public record Document(long id, String title) {}
~~~

Một service có method security, demo dữ liệu bất biến:

~~~java
package com.example.acldemo;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final Map<Long, Document> data = Map.of(
        101L, new Document(101L, "Project plan"),
        102L, new Document(102L, "Meeting notes")
    );

    @PreAuthorize(
        "hasPermission(#documentId, 'com.example.acldemo.Document', 'READ')")
    public Document readDocument(long documentId) {
        Document doc = data.get(documentId);
        if (doc == null) {
            throw new IllegalArgumentException("Document missing");
        }
        return doc;
    }
}
~~~

Điều kiện thực thi:

1. Cần ACL Document#101 / Document#102 được tạo và lưu trong ACL service; Map chứa Document **không tự tạo ACL**.
2. `@EnableMethodSecurity` bật, expression handler dùng ACL evaluator.
3. Biến `#documentId` phải được resolve từ Java method parameter name hoặc annotation mapping tương ứng; compiler `-parameters` và build config cần được kiểm tra.
4. Caller phải đi qua Spring method-security proxy. Lời gọi `this.readDocument(...)` trong cùng service có thể bypass interception.
5. Demo dùng Map bất biến; với DB thay đổi đồng thời cần xử lý TOCTOU và transaction.
6. Nếu dữ liệu nhạy cảm có tenant, method/policy phải kiểm tra tenant boundary độc lập, không tin rằng ACL role string có tenant scope.

Một controller bên ngoài service:

~~~java
// Fragment trong @RestController với injected DocumentService service.
@GetMapping("/api/documents/{id}")
public Document get(@PathVariable long id) {
    return service.readDocument(id);
}
~~~

Nếu request được HTTP security cho qua nhưng method ACL từ chối, request **không được trả document**. Test cả user được grant và user không được grant trên **cùng object thực**. Không chỉ test một route không tồn tại trả 404.

### Hạn chế proxy và self-invocation

~~~java
@Service
class UnsafeService {
    public Document outer(long id) {
        return this.protectedRead(id); // thường không qua Spring proxy
    }

    @PreAuthorize("hasPermission(#id, 'com.example.acldemo.Document', 'READ')")
    public Document protectedRead(long id) {
        // ...
        throw new UnsupportedOperationException();
    }
}
~~~

Đây là ví dụ rủi ro, không phải service production. Nếu một method unprotected gọi protected method qua `this`, Spring AOP proxy có thể không intercept. Để tránh bypass, tách protected service sang bean khác, constructor-inject và test lời gọi thực. Đừng giả định annotation trên private/static/final methods tự hoạt động như public methods thông qua proxy.

## 12. Lifecycle chia sẻ và thu hồi tài nguyên

### Tạo tài liệu

~~~text
Alice xác thực -> yêu cầu CREATE document trong tenant north
  1. Business service kiểm tra CREATE policy và tenant.
  2. Transaction tạo Document#101.
  3. Tạo ObjectIdentity(Document, 101).
  4. Tạo ACL, owner SID đáng tin.
  5. Insert READ/WRITE GRANT cho Alice theo product policy.
  6. Commit cả dữ liệu domain và ACL, hoặc có cơ chế reconcile.
  7. Kiểm thử Alice được READ, Bob không được READ.
~~~

Nếu ACL persistence thất bại sau khi document đã tồn tại, **không công khai object trước khi ACL được provision**. Nếu domain DB và ACL store không chia sẻ transaction, cần outbox/saga và trạng thái pending/deny mặc định.

### Chia sẻ document cho Bob

Khi Alice muốn grant Bob READ:

- Xác thực Alice.
- Kiểm tra Alice thật sự có quyền **quản lý sharing/ACL**, không chỉ READ.
- Load Document và xác minh tenant của người cấp/người nhận.
- Xác định Bob bằng user identifier server-side, không chỉ tin payload username.
- Đọc ACL hiện tại, insert ACE `PrincipalSid("bob"), READ, GRANT`, tránh duplicate/conflict.
- Update ACL trong transaction, invalidate cache.
- Kiểm tra Bob READ được, Bob WRITE vẫn không được.

**Không để user chỉ có READ tự cấp ADMINISTRATION hoặc sửa ACL của người khác.** Cần phân biệt quyền hành động với đối tượng và quyền thay đổi hệ thống phân quyền. `AclAuthorizationStrategy` có trách nhiệm trong quản lý ACL; thiết kế business permission cho share/revoke vẫn phải rõ.

### Thu hồi quyền

Muốn revoke READ của Bob:

1. Authorize người thực hiện revoke.
2. Tìm chính xác ACE theo Sid và Permission trong ACL hiện tại.
3. Delete/update ACE, lưu qua `MutableAclService.updateAcl`.
4. Invalidate caches, phát sự kiện tới nodes khác nếu cần.
5. Đảm bảo Bob không còn một grant khác nhờ role SID hoặc parent inheritance.
6. Gửi request mới với Bob và xác nhận bị deny.

**Xóa một ACE không bảo đảm thu hồi quyền hiệu lực.** Một role ACE khác vẫn có thể grant. Test effective permission chứ không chỉ assert database row đã bị xóa.

### Chuyển owner

Khi document chuyển Alice → Bob, cần quyết định riêng owner trong domain record, ACL owner_sid, ACE READ/WRITE cũ/mới, tenant membership, inherited entries và audit/cache. `MutableAcl.setOwner(newSid)` (nếu API/implementation dùng) **không tự chuyển tất cả grant entries** theo business contract.

## 13. Multi-tenant, SID và ObjectIdentity collisions

Ví dụ hai tenants cùng có document ID 101 và user tên Alice. Nếu ứng dụng dùng:

~~~text
ObjectIdentity = (Document, 101)
Sid = PrincipalSid("alice")
~~~

thì hai identities có thể đụng nhau nếu không có namespace toàn cục. Tương tự `GrantedAuthoritySid("ROLE_ADMIN")` có thể đại diện role admin **ở mọi tenant**, không phải một tenant cụ thể.

**Thiết kế an toàn:**

- Dùng globally unique document IDs hoặc canonical ObjectIdentity có tenant scope.
- Dùng immutable principal ID hoặc Sid namespacing thích hợp.
- Kiểm tra tenant membership từ identity/DB đáng tin, độc lập với ACL.
- Tránh cấp ROLE_ADMIN toàn cục READ trên tất cả documents nếu role thực ra chỉ là tenant admin.
- Test user cùng role nhưng khác tenant, trùng local IDs và owner transfer.

Quy tắc mẫu:

~~~text
ALLOW =
    user đã xác thực
    AND trustedUserTenant == trustedResourceTenant
    AND ACL grants requested Permission for trusted Sids
~~~

Không viết `sameTenant OR ACLgrants` nếu tenant boundary là bắt buộc; nhánh OR cho phép một global role grant vượt tenant. Nếu product có superadmin cross-tenant, phải có policy, logging, approvals và tests riêng, không suy đoán từ ROLE_ADMIN.

## 14. Caching, inheritance và consistency

### Caching ACL

Caching giúp giảm queries, nhưng **quyền stale** là vấn đề an toàn:

- Node A gọi `updateAcl`, Node B còn cache ACL cũ.
- Một script cập nhật trực tiếp `acl_entry` mà quên cache eviction.
- Parent ACL thay đổi, child vẫn inherit grant cũ trong cache.
- Authentication còn authorities bị thu hồi ngoài identity provider.

Ứng dụng cần chiến lược cache phù hợp với `AclService`/`MutableAclService`, invalidation qua nodes, TTL/revocation SLA và tests. Không cache `allowed=true` bằng ObjectIdentity duy nhất mà bỏ principal/permission/tenant/policy version; sẽ tạo cross-user permission leak.

### N+1 ACL lookups

Một API trả 100 documents mà gọi DB ACL từng item có thể bị N+1 queries. Dùng batch ACL lookup hoặc query-level filtering theo quyền/tenant nếu phù hợp, đồng thời đảm bảo pagination chính xác. Đừng tải toàn bộ các documents ngoài scope rồi filter trong browser: dữ liệu đã bị lộ ở response.

### Time-of-check/time-of-use

~~~text
T1: Alice được ACL READ Document#101
T2: Admin revoke READ của Alice
T3: Service đọc Document#101 và trả response
~~~

Đây có thể là TOCTOU. Với thao tác nhạy cảm, cần áp quyền đủ gần data access/commit, transaction/isolation, permission versions hoặc các cơ chế consistency phù hợp. `@PreAuthorize` **không tự biến mọi ACL lookup và document query thành một transaction atomic**.

### Parent inheritance

Nếu parent ACL grant và child entriesInheriting=true, phải kiểm tra interaction giữa local ACE grants/denies và inherited entries theo strategy. Nếu xóa parent hoặc thay quyền nhóm, child access có thể thay đổi. Không coi inheritance như một phép OR grant đơn giản, vì điều đó có thể bỏ qua local denies.

## 15. Java 17 độc lập: bốn đối tượng phối hợp ra quyết định

Chương trình sau **chạy được chỉ bằng JDK 17**. Nó mô phỏng Sid, ObjectIdentity, Permission và ACE bằng Java records, cộng một `ObjectAcl`. Policy của ví dụ: duyệt entries theo thứ tự, lấy entry đầu tiên khớp Sid và mask; thiếu entry hoặc tenant không khớp thì DENY.

**Đây không phải bản sao hoàn chỉnh của Spring Security ACL DefaultPermissionGrantingStrategy.** Nó chỉ minh họa việc kết nối bốn đối tượng và một **chiến lược được định nghĩa rõ ràng cho demo**. Trong Spring ACL thật, conflict/ordering/inheritance phải test theo PermissionGrantingStrategy đang cấu hình.

Lưu file `AclFourObjectsDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AclFourObjectsDemo {
    static final int READ = 1;
    static final int WRITE = 2;

    record ObjectIdentity(String type, long id) {}
    record Sid(String value) {}
    record Permission(int mask, String name) {}
    record AccessControlEntry(
        Sid sid, Permission permission, boolean granting) {}
    record ObjectAcl(
        ObjectIdentity identity,
        String tenant,
        List<AccessControlEntry> entries) {}

    static boolean allowed(
            ObjectAcl acl,
            String principal,
            String userTenant,
            Set<String> authorities,
            Permission requested) {

        if (acl == null || principal == null ||
                userTenant == null || requested == null ||
                !userTenant.equals(acl.tenant())) {
            return false;
        }

        Sid principalSid = new Sid("P:" + principal);
        for (AccessControlEntry ace : acl.entries()) {
            boolean userMatch = ace.sid().equals(principalSid);
            boolean roleMatch = ace.sid().value().startsWith("R:")
                && authorities.contains(
                    ace.sid().value().substring(2));
            boolean permissionMatch =
                (ace.permission().mask() & requested.mask())
                    == requested.mask();

            if ((userMatch || roleMatch) && permissionMatch) {
                return ace.granting();
            }
        }
        return false;
    }

    static String label(boolean value) {
        return value ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Permission read = new Permission(READ, "READ");
        Permission write = new Permission(WRITE, "WRITE");
        ObjectIdentity id =
            new ObjectIdentity("Document", 101L);

        ObjectAcl acl = new ObjectAcl(id, "north", List.of(
            new AccessControlEntry(
                new Sid("P:bob"), read, false),
            new AccessControlEntry(
                new Sid("P:alice"), read, true),
            new AccessControlEntry(
                new Sid("R:ROLE_AUDITOR"), read, true),
            new AccessControlEntry(
                new Sid("P:bob"), write, true)
        ));

        Map<ObjectIdentity, ObjectAcl> aclStore =
            Map.of(id, acl);

        System.out.println("alice READ: " + label(
            allowed(acl, "alice", "north",
                Set.of("ROLE_USER"), read)));
        System.out.println("bob READ: " + label(
            allowed(acl, "bob", "north",
                Set.of("ROLE_AUDITOR"), read)));
        System.out.println("auditor READ: " + label(
            allowed(acl, "carol", "north",
                Set.of("ROLE_AUDITOR"), read)));
        System.out.println("bob WRITE: " + label(
            allowed(acl, "bob", "north",
                Set.of("ROLE_USER"), write)));
        System.out.println("alice WRITE: " + label(
            allowed(acl, "alice", "north",
                Set.of("ROLE_USER"), write)));
        System.out.println("cross-tenant READ: " + label(
            allowed(acl, "carol", "south",
                Set.of("ROLE_AUDITOR"), read)));

        ObjectIdentity missing =
            new ObjectIdentity("Document", 999L);
        System.out.println("unknown object READ: " + label(
            allowed(aclStore.get(missing), "alice", "north",
                Set.of("ROLE_USER"), read)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AclFourObjectsDemo.java
java AclFourObjectsDemo
~~~

Stdout **chính xác**:

~~~text
alice READ: ALLOW
bob READ: DENY
auditor READ: ALLOW
bob WRITE: ALLOW
alice WRITE: DENY
cross-tenant READ: DENY
unknown object READ: DENY
~~~

Vì sao Bob READ DENY dù có ROLE_AUDITOR? Mô hình dùng thứ tự first-match và ACE cá nhân Bob READ DENY đứng trước role grant. Đây là hành vi **của chương trình demo**, không phải lời hứa về mọi Spring ACL strategy.

Tại sao Bob WRITE ALLOW? ACE WRITE grant riêng khớp Bob, trong khi ACE READ deny có mask khác; demo phân biệt permissions độc lập.

Tại sao Alice WRITE DENY? Không có ACE WRITE grant Alice; thiếu grant thì deny.

Tại sao cross-tenant READ DENY? Kiểm tra tenant được áp trước ACE. Trong sản phẩm thật tenant phải lấy từ dữ liệu tin cậy, không từ một String do client tự gửi.

## 16. Kiểm thử Spring Security ACL

Có ba tầng kiểm thử:

1. **Unit test policy:** Sid/principal, authority SID, masks, deny/grant, thứ tự, missing ACL.
2. **JDBC integration:** schema, MutableAclService create/update/delete, lookup, owner, cache invalidation, inheritance.
3. **HTTP/method security integration:** request đi qua authentication filters, controller/service proxy và `AclPermissionEvaluator` thật; 200, 401, 403/404 theo contract.

### Ma trận test

| User | Document | Permission | ACL/setup | Kỳ vọng |
| --- | --- | --- | --- | --- |
| alice | 101 | READ | Grant Alice READ | Allow |
| bob | 101 | READ | Không grant Bob | Deny |
| bob | 101 | READ | Grant Bob READ | Allow |
| bob | 101 | WRITE | Chỉ grant READ | Deny |
| auditor | 101 | READ | Grant ROLE_AUDITOR | Allow |
| user có role+principal conflict | 101 | READ | Explicit deny + role grant | Theo strategy được xác minh |
| alice | 999 | READ | ObjectIdentity không có ACL | Deny/fail closed |
| admin tenant south | north doc | READ | Role grant nhưng khác tenant | Deny |
| member | child | READ | Parent grant, inheriting on | Theo policy inheritance |
| member | child | READ | Parent grant, inheriting off | Deny nếu không có local grant |
| bob sau revoke | 101 | READ | ACE bị xóa, cache invalidated | Deny |
| anonymous | 101 | READ | Không Authentication | Deny/entry point |

### Test service bean qua @WithMockUser

~~~java
// Fragment trong @SpringBootTest với bean DocumentService và ACL fixtures.
// Phải có @EnableMethodSecurity và AclPermissionEvaluator đúng.
@Autowired DocumentService documents;

@Test
@WithMockUser(username = "alice", roles = "USER")
void ownerCanRead() {
    Document d = documents.readDocument(101L);
    assertEquals(101L, d.id());
}

@Test
@WithMockUser(username = "bob", roles = "USER")
void otherUserCannotRead() {
    assertThrows(
        org.springframework.security.access.AccessDeniedException.class,
        () -> documents.readDocument(101L));
}
~~~

Cần imports JUnit/Spring Security Test, seed ACL READ Alice và không grant Bob. Fragment này **không tự chạy** nếu thiếu AclService bean, DB schema, ACL fixtures hoặc method-security expression handler.

`@WithMockUser` không chứng minh authentication thật; nó cung cấp principal giả đáng tin **trong test** để kiểm tra permissions. Với end-to-end, dùng HTTP Basic/form login/Bearer thực qua MockMvc và một object có ACL thật.

### Test MockMvc

~~~java
// Fragment tích hợp SpringBootTest + AutoConfigureMockMvc,
// với httpBasic users và ACL fixtures đã được chuẩn bị.
mvc.perform(get("/api/documents/101")
        .with(httpBasic("alice", "demo-password")))
    .andExpect(status().isOk());

mvc.perform(get("/api/documents/101")
        .with(httpBasic("bob", "demo-password")))
    .andExpect(status().isForbidden());
~~~

Status 403 tùy app entry point/error handling. Quan trọng nhất là dùng **cùng tài nguyên thực**, grant một principal, deny principal khác. Một GET URL không có controller trả 404 không chứng minh ACL được dùng.

### Test revoke, inheritance và cache

Sau khi grant Bob READ, test Bob đọc được; xóa ACE, cập nhật ACL, test Bob bị deny với request mới. Nếu dùng nhiều nodes, thử cả node chưa trực tiếp ghi ACL. Thêm ca Bob được role grant READ khác: revoke principal ACE chưa chắc đủ; test effective access thực.

Khi có inheritance, test mọi tổ hợp child grant/deny, parent grant/deny, entriesInheriting true/false. Khi có role hierarchy, xác minh evaluator nhận Sids theo authorities thật và role hierarchy có được áp ở lớp lấy SID hay không; đừng suy ra chỉ từ `hasRole`.

### Performance test

Với GET list, test không chỉ quyền của một object. Đo số queries ACL, batch lookup, pagination và khả năng lọc ở database. Không render/return documents ngoài scope rồi chỉ ẩn chúng trong JavaScript.

## 17. Phân biệt các loại authorization

| Công cụ | Cấp độ | Khi nào hữu ích |
| --- | --- | --- |
| `authorizeHttpRequests(...).hasRole(...)` | HTTP URL/method | Cổng cho cả nhóm endpoints |
| `@PreAuthorize("hasRole(...)")` | Lời gọi service method | Vai trò tĩnh |
| `@PreAuthorize("hasPermission(...)")` | Method + domain object | ACL theo từng resource |
| Custom `AuthorizationManager<RequestAuthorizationContext>` | HTTP request context | Quy tắc phức tạp trước controller |
| Business policy + repository condition | Dữ liệu và transaction | Owner/tenant, consistency, filtering |
| Spring Security ACL/JDBC | Persistent per-object ACLs | Chia sẻ cá nhân/nhóm, grant/revoke nhiều object |

Không nên trộn role-only với object ACL rồi tưởng một kiểm tra sẽ tự bù cho kiểm tra khác. Ví dụ, một `ROLE_ADMIN` ở API filter chỉ chứng minh role, không có nghĩa user có READ trên mọi object và mọi tenant.

### ACL không tự cấp quyền tại sao HTTP request lại bị chặn?

Bởi vì kiểm tra có thể đang thực thi ở service method, không phải URL matcher. Request có thể đã qua HTTP layer nhưng bị method-security interceptor từ chối trước khi service trả dữ liệu. Ngược lại, nếu một service được gọi ngoài HTTP và không qua proxy/policy, ACL có thể hoàn toàn **không được đánh giá**.

## 18. Lỗi phổ biến và hướng sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ check ROLE_USER cho mọi object | IDOR/BOLA | ACL/owner/tenant checks |
| Dùng Sid từ parameter client | Giả danh Sid | Authentication và identity store tin cậy |
| Dùng ObjectIdentity chỉ bằng ID không có type | Lẫn object domains | Type + ID canonical |
| Tenant có local IDs trùng | Va chạm ACL | Global IDs hoặc namespaced identity |
| Đổi class package mà không migrate ACL | Lookup miss | Migration acl_class/identity |
| Coi owner_sid là READ/WRITE | Quyền sai | ACE/policy rõ |
| Coi WRITE tự bao gồm READ | Grant thiếu/thừa | Test per-permission |
| Coi ADMINISTRATION là ROLE_ADMIN | Trộn permission và role | Tách model |
| Bỏ qua ACE order/strategy | Grant/deny xung đột | Test conflict và strategy thật |
| Quên set AclPermissionEvaluator | hasPermission không tra ACL | Expression handler config |
| Tạo ACL mà quên updateAcl | ACE chưa persist | MutableAclService.updateAcl |
| Revoke theo index cố định | Xóa nhầm entry | Tìm theo SID/mask |
| Revoke principal entry nhưng còn role grant | Vẫn truy cập được | Test effective ACL |
| Error đọc ACL DB => allow | Fail-open | Fail closed, error contract |
| ACL mới provision trễ | Object bị mở trong khoảng trống | Transaction/pending-deny |
| Sửa acl_entry trực tiếp, cache không xóa | Quyền stale | Invalidation/reconciliation |
| Bỏ ACL ở list endpoint | Leak hàng loạt records | Query-level filtering |
| @PreAuthorize tự gọi this.method() | Bypass proxy | Tách bean, test call paths |
| Method authorization không phủ queue/cron | Bypass HTTP | Policy ở service boundary |
| Cache cho phép chỉ theo ObjectIdentity | Cross-user leakage | Principal/permission/tenant-aware cache |
| Chỉ test admin được 200 | Không chứng minh deny | Test positive + negative same object |

## 19. Bài tập tự kiểm tra

**Bài 1.** Alice và Bob đều có ROLE_USER, nhưng Document#101 chỉ thuộc Alice. Vì sao hasRole USER không đủ?

**Đáp án:** Nó chỉ kiểm tra role chung; cần object-level READ permission hoặc owner/tenant rule đáng tin cho Document#101.

**Bài 2.** `PrincipalSid("alice")` khác `GrantedAuthoritySid("ROLE_USER")` thế nào?

**Đáp án:** Một cái định danh một principal; cái kia đại diện authority mà nhiều principals có thể cùng mang.

**Bài 3.** Document#101 và Invoice#101 có cùng ObjectIdentity không?

**Đáp án:** Không nếu type khác. Identity gồm type/class và ID, nên ACL domain không bị lẫn.

**Bài 4.** Masks mặc định của READ và WRITE?

**Đáp án:** READ=1, WRITE=2. Các permissions khác như CREATE=4, DELETE=8, ADMINISTRATION=16 theo BasePermission.

**Bài 5.** ACE `alice, READ, granting=false` có nghĩa gì?

**Đáp án:** Deny READ cho principal Alice trên ACL đó. Nếu Alice còn match role grant, effective result phải được kiểm tra theo ordering và PermissionGrantingStrategy.

**Bài 6.** Owner ACL có tự có READ/WRITE?

**Đáp án:** Không mặc định đồng nhất. ACL owner cho quản trị ACL; quyền đối tượng cần policy/ACE rõ ràng.

**Bài 7.** Chỉ viết `@PreAuthorize("hasPermission(...)")` có đủ để Spring ACL JDBC chạy?

**Đáp án:** Không. Cần method security enabled, AclPermissionEvaluator, AclService/LookupStrategy, JDBC schema, ACL records và bean wiring.

**Bài 8.** ACL không tồn tại thì có nên trả allow?

**Đáp án:** Không. Fail closed hoặc fallback business policy đã được thiết kế/test rõ ràng.

**Bài 9.** Vì sao rename class Document có thể làm ACL lookup fail?

**Đáp án:** ObjectIdentity type thường map sang acl_class; class/type string đổi nhưng DB ACL identity cũ không migrate.

**Bài 10.** Bob có principal READ deny và role READ grant. Kết quả phụ thuộc gì?

**Đáp án:** PermissionGrantingStrategy, thứ tự ACE và SID matching. Không tự coi deny/role mặc định luôn ưu tiên.

**Bài 11.** Xóa principal Bob READ ACE, Bob vẫn đọc được. Vì sao?

**Đáp án:** Có thể còn role SID grant, parent inheritance, ACE khác hoặc cache stale. Kiểm tra effective decision.

**Bài 12.** Admin north được role grant READ trên tài liệu south. Nếu policy cấm cross-tenant thì sao?

**Đáp án:** Phải deny nhờ tenant boundary độc lập, không coi global role grant là quyền vượt tenant.

**Bài 13.** Có ACL check ở service method nhưng controller gọi `this.method()` trong cùng bean, nguy cơ?

**Đáp án:** Self-invocation có thể bypass Spring AOP proxy, dẫn đến method-security annotation không chạy.

**Bài 14.** Tạo document thành công nhưng tạo ACL thất bại. Cách an toàn?

**Đáp án:** Rollback nếu cùng transaction; nếu không, giữ document inaccessible/pending và reconcile, không cho public.

**Bài 15.** GET list tải 10.000 documents rồi gọi ACL per row gây gì?

**Đáp án:** N+1 queries, performance, pagination không đúng và nguy cơ leak. Dùng ACL-aware query/batch strategy và tenant filter.

**Bài 16.** Node B còn grant sau revoke trên node A, bước điều tra đầu tiên?

**Đáp án:** Kiểm tra ACL cache invalidation, distributed sync, parent/role grants và trạng thái updateAcl đã commit.

**Bài 17.** Một HTTP 404 vì controller không tồn tại có chứng minh ACL hoạt động?

**Đáp án:** Không. Cần test cùng object thực với principal được cấp và không được cấp quyền.

**Bài 18.** ADMINISTRATION mask có tự biến user thành ROLE_ADMIN cho mọi API?

**Đáp án:** Không. Một cái là Permission ACL; cái kia là GrantedAuthority; kết nối chỉ tồn tại nếu business policy chủ động thiết kế.

## 20. Checklist trước khi triển khai

- [ ] Có nhu cầu object-level sharing thực sự, không dùng ACL chỉ để thay một điều kiện owner đơn giản.
- [ ] Hiểu rõ Sid, ObjectIdentity, Permission, ACE và Acl.
- [ ] Principal/authority Sids lấy từ Authentication hoặc identity store đáng tin.
- [ ] ObjectIdentity type + ID canonical, không va chạm cross-tenant/domain.
- [ ] Permission masks ổn định; không giả định WRITE kéo theo READ.
- [ ] Quy tắc GRANT/DENY, thứ tự ACE và inheritance được test theo strategy thực tế.
- [ ] ACL owner/management tách khỏi quyền READ/WRITE business.
- [ ] Schema acl_sid/acl_class/acl_object_identity/acl_entry tương thích Spring ACL JDBC version và database.
- [ ] AclService, MutableAclService, LookupStrategy, AclCache, AclAuthorizationStrategy wired đúng.
- [ ] Nếu dùng hasPermission, @EnableMethodSecurity và AclPermissionEvaluator đã được cấu hình/test.
- [ ] Spring-managed service gọi qua proxy; không bỏ qua do self-invocation.
- [ ] ACL provisioning và domain object creation có transaction/reconciliation fail closed.
- [ ] Chia sẻ/thu hồi ACL yêu cầu quyền quản trị ACL phù hợp; không nâng quyền tùy ý.
- [ ] Revoke kiểm tra mọi Sid grants và inherited rights, không chỉ một ACE.
- [ ] Tenant membership được xác minh riêng khi role SID có phạm vi rộng.
- [ ] Missing ACL, unknown Sid/permission, DB errors không dẫn tới allow.
- [ ] Test cùng object với owner/non-owner, READ/WRITE, anonymous, cross-tenant và conflict.
- [ ] Cache invalidation/propagation sau revoke đã kiểm thử với nhiều node nếu deployment yêu cầu.
- [ ] Collection APIs được lọc quyền ở server với pagination và performance hợp lý.
- [ ] Không log raw session ID, password, JWT hoặc nội dung documents nhạy cảm trong ACL audits.

**Kết luận:** Spring Security ACL mô tả phân quyền theo **Sid (ai) + ObjectIdentity (đối tượng nào) + Permission (hành động gì) + AccessControlEntry (grant hay deny)**. Acl tập hợp các entries và metadata; AclService/MutableAclService đảm nhiệm tra cứu/quản lý; PermissionEvaluator giúp gắn chúng vào method security. Muốn bảo vệ tài nguyên thật sự, phải duy trì đúng ACL lifecycle, ranh giới tenant, cache, proxy invocation và các test grant/revoke **trên chính đối tượng nghiệp vụ**.