# Kiểm soát kế thừa ACL, bộ nhớ đệm và cập nhật quyền

> **Phạm vi:** Spring Security trên **Servlet stack**, Java 17+, quyền trên từng tài nguyên theo mô hình **Access Control List (ACL)**. Trọng tâm là quan hệ ACL cha–con và cờ kế thừa, thứ tự Access Control Entry (ACE), sự khác biệt giữa cache bản ghi ACL và cache quyết định phân quyền, cách cập nhật quyền/cờ kế thừa và vô hiệu hóa dữ liệu cache đúng phạm vi. Có mô tả API của **Spring Security ACL** cùng một ứng dụng **Spring Boot 3.3.5 có thể chạy** mô phỏng nguyên lý bằng ACL in-memory, HTTP Basic, CSRF và kiểm thử. Hai phần được phân biệt tường minh: mô hình Spring Security ACL thật và bài lab tự cài đặt để thấy rõ hiệu ứng thay đổi quyền.

## 1. Vì sao role là chưa đủ?

Khi phân quyền dựa trên vai trò, một user có `ROLE_EDITOR` có thể được cho phép sửa tài liệu. Nhưng yêu cầu thực tế thường tinh hơn:

- Alice được đọc thư mục Workspace và các tài liệu thuộc thư mục ấy.
- Bob không được đọc thư mục Workspace.
- Một tài liệu riêng nằm trong Workspace có thể **từ chối riêng Alice**.
- Auditor được đọc nhiều tài liệu thông qua một nhóm quyền kiểm toán.
- Quản trị viên có thể cấp/thu hồi quyền đọc cho từng người và từng tài liệu.
- Quyền cấp ở thư mục cha có thể **kế thừa xuống tài liệu con**, nhưng có thể dừng kế thừa ở một tài liệu nhạy cảm.
- Sau khi sửa quyền, request tiếp theo không được nhận quyết định cũ từ cache.

Các yêu cầu này liên quan đến **từng đối tượng tài nguyên**, không chỉ vai trò toàn cục.

Ví dụ cây tài liệu:

```text
Workspace (id=101)
  ACE: alice READ allow
  ACE: bob   READ deny
  ACE: role AUDITOR READ allow
  entriesInheriting = false
        |
        +-- Quarterly plan (id=102)
        |     entriesInheriting = true
        |     ACE local: không có
        |     => thường dùng quyết định từ parent khi local không quyết định
        |
        +-- Private draft (id=103)
              entriesInheriting = true
              ACE local: alice READ deny
              => từ chối Alice tại node này trước khi xét parent
```

Kết quả ban đầu trong **bài lab có quy tắc local-first rõ ràng**:

| User | Resource 101 | Resource 102 | Resource 103 |
| --- | --- | --- | --- |
| Alice | Cho phép | Cho phép do kế thừa | Từ chối bởi ACE local |
| Bob | Từ chối | Từ chối do kế thừa | Từ chối do kế thừa |
| Auditor | Cho phép | Cho phép do kế thừa | Cho phép do kế thừa |
| Admin | Cho phép theo ACE ví dụ | Cho phép do kế thừa | Cho phép do kế thừa |

**Cần phân biệt:** bảng này mô tả policy cụ thể của bài lab; **không phải tuyên bố mọi ACL engine đều có quy tắc “deny luôn thắng allow”**. Cách duyệt ACE, ưu tiên SID, permission mask và logic chuyển lên parent cần được xác định theo implementation thực tế. Ở phần Spring Security ACL bên dưới, ta sẽ làm rõ cơ chế đó.

## 2. Thành phần trong Spring Security ACL

Spring Security có module ACL riêng, thường được thêm qua dependency `spring-security-acl`. Nó **không tự động kích hoạt chỉ vì ứng dụng có `spring-boot-starter-security`**. Một triển khai ACL đầy đủ cần hệ thống lưu trữ, lookup, cache, định nghĩa SID/permissions và kết nối với authorization.

| Thuật ngữ / API | Ý nghĩa |
| --- | --- |
| `ObjectIdentity` | Xác định một tài nguyên bằng **kiểu** và **ID**, ví dụ `("example.Document", 102L)` |
| `Sid` | Security identity, đại diện cho **principal** hoặc **granted authority** |
| `PrincipalSid` | SID cho một người dùng, ví dụ `alice` |
| `GrantedAuthoritySid` | SID cho một authority/role, ví dụ `ROLE_AUDITOR` |
| `Permission` / `BasePermission` | Quyền được yêu cầu, thường dùng bit-mask như READ/WRITE/DELETE |
| `AccessControlEntry` (ACE) | Một mục ACL: SID, Permission, grant/deny, vị trí |
| `Acl` | ACL của một `ObjectIdentity`, có ACEs, owner, parent, cờ inheritance |
| `MutableAcl` | ACL có thể chỉnh sửa ACE, parent, inheritance flag |
| `AclService` | Đọc ACL của object từ hệ thống lưu trữ |
| `MutableAclService` | Thêm, cập nhật và xóa ACL (tùy implementation) |
| `LookupStrategy` / `BasicLookupStrategy` | Cơ chế truy vấn ACL, ACE và liên kết parent từ database |
| `AclCache` | Bộ nhớ đệm đối tượng ACL, giảm truy vấn khi phân quyền |
| `PermissionGrantingStrategy` | Xác định cách ACEs quyết định grant/deny |
| `AclPermissionEvaluator` | Cầu nối từ biểu thức `hasPermission(...)` sang ACL lookup/check |
| `AclAuthorizationStrategy` | Kiểm tra quyền thực hiện các thao tác quản lý ACL, không phải tự động là quyền đọc tài liệu |

Các package Spring Security ACL tiêu biểu:

```java
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.BasePermission;
```

Đây là đoạn **imports tham khảo** cho ứng dụng có dependency ACL; project runnable ở mục 10 là mô hình học tập tự cài đặt và **không giả danh là JdbcMutableAclService**.

### ObjectIdentity không phải username

Một ACL gắn với một object, ví dụ tài liệu 102, chứ không chỉ gắn với Alice.

```java
ObjectIdentity documentId =
        new ObjectIdentityImpl("example.Document", 102L);

Sid alice = new PrincipalSid("alice");
Sid auditorRole = new GrantedAuthoritySid("ROLE_AUDITOR");
Permission read = BasePermission.READ;
```

Fragment này phụ thuộc module ACL. `"example.Document"` chỉ là **class/type key** trong demo kiến trúc; nếu database đang dùng tên class/identifier khác thì phải giữ đúng mapping thực tế. Đừng tùy tiện dùng cùng numeric ID cho nhiều loại resource mà bỏ qua type.

### Sid khác Authority

`GrantedAuthority` được gắn vào `Authentication`; `Sid` là một khái niệm ACL dùng để tìm ACE phù hợp. `PrincipalSid("alice")` đại diện cho principal. `GrantedAuthoritySid("ROLE_AUDITOR")` đại diện cho authority/role. User có nhiều authorities có thể được ánh xạ thành nhiều SIDs khi kiểm tra quyền.

Không tin giá trị role hay username do client tự khai bằng HTTP header để tạo SID cho phép. SID dùng authorization phải xuất phát từ một `Authentication` đã được xác minh và mapping đáng tin.

## 3. Lược đồ lưu ACL và quan hệ kế thừa

Một triển khai JDBC truyền thống của Spring Security ACL thường dùng các bảng:

```text
acl_class
  id
  class

acl_sid
  id
  principal
  sid

acl_object_identity
  id
  object_id_class        -> acl_class.id
  object_id_identity     -> resource ID
  parent_object          -> acl_object_identity.id (nullable)
  owner_sid              -> acl_sid.id
  entries_inheriting     -> boolean

acl_entry
  id
  acl_object_identity    -> acl_object_identity.id
  ace_order              -> thứ tự ACE
  sid                    -> acl_sid.id
  mask                   -> permission bit mask
  granting               -> grant hoặc deny
  audit_success
  audit_failure
```

Tên cột trên là mô hình thông thường của schema ACL; kiểu dữ liệu, DDL, indexing và danh tính tài nguyên phải phù hợp database/phiên bản module. **Không chạy đoạn mô hình trên như lệnh CREATE TABLE**. Trước khi triển khai production, dùng schema chính thức tương ứng với Spring Security ACL và RDBMS đã chọn, cùng migration đã được kiểm thử.

### Parent object, owner và inheritance flag

- `parent_object` là liên kết đến **ACL của tài nguyên cha**, không phải chỉ là foreign key nghiệp vụ của một document.
- `entries_inheriting` cho biết ACL có được dùng quyết định của parent khi ACL local không giải quyết được hay không.
- `owner_sid` xác định SID chủ sở hữu ACL. **Owner ACL không tự động có mọi quyền READ/WRITE đối với resource** nếu policy không định nghĩa như vậy; không nhầm owner của ACL với `document.ownerId`.
- `ace_order` là phần quan trọng: hai ACE cùng permission/SID hoặc nhiều SID có thể tạo tác dụng khác nhau tùy thứ tự đánh giá.
- `granting` phân biệt ACE cho phép và ACE từ chối. Nó **không** đồng nghĩa mọi hệ thống luôn ưu tiên deny tuyệt đối.

Parent ACL cần là đồ thị **không có chu trình**. Nếu A kế thừa B rồi B lại kế thừa A, logic tra cứu có thể lặp vô hạn hoặc ném exception; quy trình cập nhật parent cần ngăn cycle và giới hạn độ sâu hợp lý.

## 4. Quy tắc kế thừa: thử local trước, sau đó mới lên parent

Với Spring Security ACL, ACL thường đánh giá các ACE local phù hợp cho các permissions/SIDs yêu cầu. Nếu ACL local **không có kết luận phù hợp**, và `isEntriesInheriting()` cho phép, việc đánh giá có thể tiếp tục lên `getParentAcl()`.

```text
checkAccess(object=102, SIDs=[alice, ROLE_USER], permission=READ)
    |
    v
Tải ACL 102
    |
    +-- Kiểm tra ACE local theo permission/SID/thứ tự
    |      |
    |      +-- Có grant/deny quyết định -> trả kết quả
    |      |
    |      +-- Không có kết luận
    |             |
    |             +-- entriesInheriting=false -> không kế thừa
    |             |
    |             +-- entriesInheriting=true
    |                    |
    |                    v
    |              Tải / kiểm tra parent ACL
    |                    |
    |                    +-- tiếp tục tới parent cao hơn nếu cần
    |
    v
Grant / Deny / không tìm thấy kết luận, tùy API và policy
```

**Một chi tiết cần hiểu đúng:** trong `BasicPermissionGrantingStrategy`, cách duyệt ACE và lựa chọn permission/SID phù hợp có **thứ tự cụ thể**. Một ACE grant xuất hiện sớm có thể cho phép trước ACE deny đến sau nếu cùng điều kiện được xét theo chiến lược đó. Vì vậy không nên tóm tắt thành “deny ACE luôn phủ quyết mọi allow ACE”. Hãy test thứ tự ACE và SID khi cùng resource có các quyền xung đột.

### Ví dụ với inheritance flag

| Local ACL | entriesInheriting | Parent ACL | Kỳ vọng |
| --- | --- | --- | --- |
| Không có ACE phù hợp | true | Parent grant Alice READ | Alice có thể được grant |
| Không có ACE phù hợp | false | Parent grant Alice READ | Không kế thừa: thường không có grant |
| Local deny Alice READ | true | Parent grant Alice READ | Local deny có thể kết luận trước parent |
| Local grant Alice READ | true | Parent deny Alice READ | Local grant có thể kết luận trước parent |
| Local ACE cho WRITE, yêu cầu READ | true | Parent grant READ | Tùy permission mask/strategy, nếu local không kết luận READ thì xét parent |

Ở đây “có thể” là cách diễn đạt có chủ đích: quyết định cuối phụ thuộc permission masks, SIDs được nạp, thứ tự ACE và `PermissionGrantingStrategy`. Với bài lab mục 10, ta chọn quy tắc **ACE local đầu tiên khớp sid + permission trả kết luận; nếu không có thì mới kế thừa; mặc định deny** để minh họa rõ.

### Kế thừa không phải role hierarchy

- **ACL inheritance:** tài liệu con nhận quyết định từ ACL của tài liệu/thư mục cha.
- **Role hierarchy:** một role có thể bao gồm role khác theo cấu hình role hierarchy.
- **Java class inheritance:** kế thừa type/method giữa class Java, không cấp quyền resource.

Các khái niệm này độc lập. `ROLE_ADMIN` không tự thừa hưởng ACL của mọi resource nếu SID/permission mapping không cho phép.

## 5. Permission bit masks và thứ tự ACE

`BasePermission` trong Spring Security ACL có các bit quyền phổ biến:

| Quyền | Mask thường dùng |
| --- | --- |
| `BasePermission.READ` | 1 |
| `BasePermission.WRITE` | 2 |
| `BasePermission.CREATE` | 4 |
| `BasePermission.DELETE` | 8 |
| `BasePermission.ADMINISTRATION` | 16 |

Các mask biểu diễn bit quyền, **không phải role strings**. Permission khác có thể được định nghĩa bằng bitmask riêng hoặc `PermissionFactory` phù hợp. Nếu một ứng dụng có quyền `APPROVE`, cần thống nhất mask/semantics và cách đánh giá; không tự gán \`ROLE_APPROVER\` thành mask READ.

Trong Spring Security ACL, `Acl.isGranted(permissions, sids, administrativeMode)` kiểm tra theo strategy với các permissions và SIDs được truyền. Có thể có `NotFoundException` nếu không ACE phù hợp và không có quyết định kế thừa; có thể có `UnloadedSidException` khi ACL không được nạp đầy đủ cho danh sách SID cần đánh giá.

Vì vậy trong một lớp policy của ứng dụng, đừng coi mọi exception là **grant**. Với request cần tài nguyên riêng, cách xử lý thông thường là **deny hoặc trả lỗi theo policy** khi không có quyết định phù hợp; ghi log an toàn cho sự cố dữ liệu/schema/cache.

### Tại sao thứ tự ACE quan trọng?

Giả sử một tài liệu có:

```text
ACE 0: ROLE_STAFF  READ allow
ACE 1: alice       READ deny
```

Alice vừa là principal alice vừa thuộc role STAFF. Một chiến lược đánh giá có thể kết luận từ ACE đầu tiên phù hợp. Do đó **không được giả định** deny ACE ở vị trí sau luôn được xét hoặc ưu tiên hơn grant ở vị trí trước. Thiết kế rule cần nhất quán giữa ACE ordering và SID resolution.

Hãy viết integration tests với user có **nhiều SIDs** để xác nhận outcome thực tế, đặc biệt nếu permission granting strategy hoặc custom ACL service đã được tùy biến.

## 6. Hai lớp cache: cache ACL và cache quyết định phân quyền

Đây là điểm rất dễ nhầm.

### 6.1. AclCache của Spring Security ACL

`AclCache` thường lưu **ACL đã tải** (ACL object với ACEs và quan hệ cần thiết), giúp tránh đọc các bảng ACL nhiều lần. Một số triển khai dùng `SpringCacheBasedAclCache` dựa trên Spring Cache; cấu hình cụ thể phụ thuộc version và cache provider.

```text
ACL lookup
  - ObjectIdentity("example.Document", 102)
       |
       v
AclCache?
   |             |
  HIT           MISS
   |             |
   |             v
   |        LookupStrategy / JDBC read ACL
   |             |
   |             v
   |        Populate AclCache
   +-------------+
          |
          v
   Acl.isGranted(permission, sids, ...)
```

Cache ACL **không có nghĩa là đã cache mọi quyết định cho từng user**. Nó lưu cấu trúc policy, còn kết quả kiểm tra vẫn có thể phụ thuộc request, Authentication/SIDs và danh sách permissions.

### 6.2. Decision cache tùy ứng dụng

Một hệ thống còn có thể cache **kết quả** “Alice có được READ document 102?” để tiết kiệm CPU/remote policy calls. Đây **không mặc nhiên là tính năng của `AclCache`**.

Một cache key kết quả phải bao phủ đầy đủ context ảnh hưởng quyết định:

```text
tenantId
object type + object ID
principal ID + authorities / SID set
permission
ACL revision / ancestor revision
policy version
các thuộc tính ngữ cảnh khác nếu policy dùng chúng
```

Nếu cache chỉ theo `documentId` thì lần Alice được cho phép có thể khiến Bob **nhận nhầm allow từ cache**. Nếu cache theo username + document nhưng không xét authorities hoặc scope tenant, quyết định cũng có thể sai khi role/tenant membership thay đổi.

**Negative cache** (deny results) cũng phải bị vô hiệu hóa sau khi grant mới; nếu không, người vừa được cấp quyền vẫn bị 403. **Positive cache** phải bị vô hiệu hóa sau revocation; nếu không, người vừa bị thu hồi quyền vẫn đọc được tài nguyên.

### 6.3. Kế thừa làm cache invalidation phức tạp

Một thay đổi ở ACL cha có thể làm thay đổi quyết định của **mọi descendant đang kế thừa**. Ví dụ:

```text
Trước update:
 parent 101: Bob READ deny
 child 102:  không ACE local, inherit=true
 cache decision (Bob, 102, READ) = deny

Admin cập nhật ACL 101:
 parent 101: Bob READ allow

Nếu chỉ xóa cache của parent 101:
 child 102 có thể còn cache deny hoặc cached parent snapshot cũ

Đúng:
  - vô hiệu ACL cache phù hợp cả parent và children liên quan;
  - vô hiệu decision cache các descendants chịu ảnh hưởng;
  - đảm bảo request mới đọc được policy revision đã commit.
```

Các phương án phổ biến:

1. **Invalidate subtree:** tìm descendants liên quan và evict ACL cache cùng các cached decisions của chúng.
2. **Versioning:** lưu revision theo ACL/ancestor hoặc policy generation; cache entries có revision không đúng bị bỏ qua.
3. **Global version/clear:** đơn giản, dễ đúng khi học hoặc hệ nhỏ; khi update, xóa toàn bộ cache quyết định.
4. **TTL:** lớp bảo vệ phụ để giới hạn thời gian stale, **không thay thế invalidation** khi yêu cầu thu hồi quyền ngay lập tức.
5. **Distributed invalidation:** gửi event/outbox hoặc sử dụng cache provider hỗ trợ đồng bộ giữa instances; cần xác nhận sự kiện đến mọi node, xử lý trễ/duplicate/retry.

**Tính đúng quan trọng hơn hit rate.** Với hệ thống nhạy cảm, một quyết định allow cũ sau khi quyền đã bị thu hồi có thể là lỗ hổng bảo mật.

## 7. Thay đổi ACL: cập nhật ACE, parent và cờ kế thừa

Một quy trình thay đổi quyền nên diễn ra có kiểm soát:

1. **Xác thực actor** thực hiện thay đổi.
2. **Phân quyền actor** được quyền quản lý ACL của resource và tenant tương ứng; không đủ chỉ có `authenticated()`.
3. Đọc ACL/phiên bản hiện tại bằng nguồn dữ liệu tin cậy.
4. Kiểm tra resource tồn tại, thuộc tenant được phép, parent hợp lệ, không tạo chu trình.
5. Thêm/xóa/cập nhật ACE theo SID + permission + thứ tự đã định nghĩa; tránh duplicate ACE khó đoán.
6. Thay đổi `entriesInheriting` hoặc parent ACL khi chính sách nghiệp vụ cho phép.
7. **Lưu cập nhật trong transaction** phù hợp với thay đổi domain (nếu có).
8. Invalidate cache tương ứng, gồm descendants và decisions đã phụ thuộc parent.
9. Ghi audit actor, resource, old/new policy, lý do và correlation ID mà không lộ secrets.
10. Kiểm thử ngay **request mới** cho user bị cấp/thu hồi, không chỉ kiểm tra HTTP status của API cập nhật.

### Một số cập nhật có ảnh hưởng khác nhau

| Thay đổi | Phạm vi có thể chịu ảnh hưởng |
| --- | --- |
| Thêm grant local cho child 102 | Child 102; có thể descendants kế thừa từ 102 |
| Thêm deny local cho child 102 | Child 102 và descendants nhận quyết định từ đó |
| Đổi grant/deny ở parent 101 | Tất cả descendants dùng inheritance và không bị ACE local quyết định |
| Đặt `entriesInheriting=false` trên child | Child và nhánh dưới có thể mất quyền từ ancestors |
| Đổi parent ACL của child | Child và descendants có thể đổi cả quyền |
| Thu hồi role/authority của user | Có thể ảnh hưởng tất cả ACL có SID role đó, cả khi ACL records không đổi |
| Xóa resource / ACL | ACL, children/links, caches và domain references liên quan |
| Thay đổi `PermissionGrantingStrategy` | Có thể ảnh hưởng mọi quyết định; cần policy cache version mới |

**Không có một cách evict duy nhất tối ưu cho mọi kiến trúc.** Với Spring Security ACL JDBC, hãy kiểm tra behavior của `JdbcMutableAclService` và cache implementation theo phiên bản đang dùng; cập nhật thông qua service tiêu chuẩn có cơ chế xử lý cache liên quan, nhưng custom DAO, bulk SQL và distributed caches có thể **bỏ qua** các bước đó.

## 8. API Spring Security ACL: tạo và cập nhật quyền

Các snippets sau minh họa **API Spring Security ACL thật**, nhưng là **fragments cần cấu hình sẵn** `MutableAclService`, database/schema, `LookupStrategy`, `AclCache` và transaction. Chúng không phải code của mô hình in-memory runnable ở mục 10.

### 8.1. Tải ACL theo ObjectIdentity

```java
ObjectIdentity oid =
        new ObjectIdentityImpl("example.Document", 102L);

Acl acl = aclService.readAclById(oid);
boolean inheritanceEnabled = acl.isEntriesInheriting();
Acl parentAcl = acl.getParentAcl();
```

Cần xác định `ObjectIdentity` type/ID chính xác theo bản ghi `acl_object_identity`. Nếu object chưa có ACL, `readAclById` có thể ném `NotFoundException`; đừng coi absence luôn có nghĩa public allow.

### 8.2. Thêm một ACE cấp READ cho Bob

```java
// Fragment trong service đang có MutableAclService mutableAclService,
// transaction và authorization cho actor sửa ACL.
ObjectIdentity oid =
        new ObjectIdentityImpl("example.Document", 102L);

MutableAcl acl =
        (MutableAcl) mutableAclService.readAclById(oid);

Sid bob = new PrincipalSid("bob");

// Thêm ACE tại vị trí cuối theo policy của hệ thống.
// Nếu đã có ACE Bob/READ, cần update/remove hợp lý, tránh duplicate.
acl.insertAce(acl.getEntries().size(), BasePermission.READ, bob, true);

mutableAclService.updateAcl(acl);
```

**Cần xử lý duplicate và order:** nếu ACL đã có deny Bob/READ đứng trước, thêm grant ở cuối có thể **không làm Bob được phép** vì strategy đánh giá ACE theo thứ tự. Phải tìm và thay thế ACE tương ứng theo policy, không chỉ chèn thêm.

Việc gọi `updateAcl` không thay cho validation actor, tenant, domain state hoặc cơ chế transaction. Với sản phẩm thật, bao service bởi quyền quản lý ACL riêng và kiểm soát lost update.

### 8.3. Ngắt kế thừa ở child

```java
ObjectIdentity childId =
        new ObjectIdentityImpl("example.Document", 102L);

MutableAcl child =
        (MutableAcl) mutableAclService.readAclById(childId);

child.setEntriesInheriting(false);
mutableAclService.updateAcl(child);
```

Khi `entriesInheriting=false`, policy ở parent sẽ không tự được áp dụng để lấp khoảng trống của child theo cơ chế inheritance. Nếu child chưa có local grant phù hợp, người dùng có thể bị từ chối mặc dù parent cho phép.

### 8.4. Chuyển parent ACL

```java
ObjectIdentity childId =
        new ObjectIdentityImpl("example.Document", 102L);
ObjectIdentity newParentId =
        new ObjectIdentityImpl("example.Folder", 201L);

MutableAcl child =
        (MutableAcl) mutableAclService.readAclById(childId);
Acl newParent = mutableAclService.readAclById(newParentId);

// Phải kiểm tra tenant, quyền quản trị và chu trình trước.
child.setParent(newParent);
child.setEntriesInheriting(true);
mutableAclService.updateAcl(child);
```

Parent có thể thuộc type khác nếu mô hình dữ liệu và ACL schema cho phép, nhưng **không nên** cho phép cross-tenant inheritance tùy ý. Trước khi gọi `setParent`, phải kiểm tra target parent tồn tại, không làm tạo cycle và phù hợp chính sách nghiệp vụ. Cập nhật parent cần invalidate cả decisions của child/subtree liên quan.

### 8.5. AclCache và invalidation ngoài đường service chuẩn

Một `AclCache` có các thao tác evict và clear, tùy implementation. Ví dụ fragment:

```java
// Dùng khi hệ thống biết chắc ACL bị sửa ngoài service chuẩn
// và thực hiện invalidation đầy đủ, không chỉ một node.
ObjectIdentity oid =
        new ObjectIdentityImpl("example.Document", 102L);

aclCache.evictFromCache(oid);
```

**Không coi một lời gọi evict này là đủ** nếu ACL parent thay đổi hoặc app còn decision cache và nhiều nodes. Các implementation JDBC/cache thông thường có thể có logic evict cả descendants trên update tiêu chuẩn; cần xác minh nguồn dữ liệu/cache cụ thể, nhất là khi dùng SQL trực tiếp, external administration service hoặc event-driven updates.

### 8.6. hasPermission(...) tại service/HTTP authorization

Khi đã cấu hình `AclPermissionEvaluator` thông qua `MethodSecurityExpressionHandler`, một policy method có thể dùng:

```java
@PreAuthorize(
    "hasPermission(#documentId, 'example.Document', 'READ')")
public DocumentView load(long documentId) {
    return repository.load(documentId);
}
```

Đây là **fragment**, chưa runnable: cần method security, bean evaluator, ACL service, resource type string khớp và repository thực. Nếu cần check tài nguyên trong DB theo tenant, phải kết hợp policy theo tenant/ownership thay vì dùng mask ACL đơn lẻ.

Một bean cấu hình mẫu:

```java
@Bean
MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        AclService aclService) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(
            new AclPermissionEvaluator(aclService));
    return handler;
}
```

Đoạn trên cần imports và wiring theo Spring Security version đang dùng. Với `@EnableMethodSecurity`, phải xác minh handler do framework thực sự sử dụng; không giả định chỉ thêm dependency ACL là mọi biểu thức `hasPermission` tự chạy.

## 9. Bảo đảm cập nhật đồng bộ, transaction và revocation

### 9.1. Lost update

Giả sử hai admin cùng đọc ACL revision 7:

```text
Admin A: muốn grant READ cho Alice
Admin B: muốn deny READ cho Bob

Cả hai đọc revision 7.
A ghi bản ACL đã sửa.
B ghi snapshot cũ + sửa Bob.
Nếu B ghi đè không kiểm soát, grant của A có thể mất.
```

Các chiến lược:

- Optimistic locking với revision trong domain/ACL update workflow.
- Pessimistic lock hoặc transaction isolation phù hợp.
- Conditional SQL update với version check.
- Xếp hàng các ACL mutations theo một resource nếu cần.
- Dùng data model có uniqueness cho (object, SID, permission) hoặc policy ACE order rõ ràng.

Đừng giả định một cache eviction đúng sẽ tự giải quyết lost update ở database.

### 9.2. Cache invalidation và transaction commit

Một vấn đề là **khi nào** node khác thấy permission mới:

```text
T1: bắt đầu transaction sửa ACL parent
T1: sửa ACE
T1: phát event invalidate cache quá sớm
T2: nhận event, xóa cache
T2: lập tức đọc DB, vẫn thấy ACE cũ (T1 chưa commit)
T2: cache lại ACL cũ
T1: commit
=> stale cache có thể tồn tại sau commit!
```

Một chiến lược thực tế là phát sự kiện sau commit, dùng transactional outbox, hoặc cache version monotonic và xác minh khi đọc. Với transaction rollback, không được thông báo thay đổi thành công rồi để cache/tầng khác nghĩ policy đã đổi.

Trong một instance và mô hình khóa đơn giản, có thể cập nhật state rồi clear cache trong cùng critical section; đây là lựa chọn trong lab mục 10, không phải bằng chứng đã giải quyết multi-node.

### 9.3. Quyền bị thu hồi nhưng authentication còn authority cũ

ACL cache chỉ là một phần câu chuyện. Nếu user bị rút role `ROLE_AUDITOR` nhưng session hoặc JWT vẫn chứa authority đó:

- ACL chứa ACE cho `ROLE_AUDITOR` có thể **không thay đổi**.
- User vẫn có thể được chọn cùng SID từ authentication cũ.
- Xóa `AclCache` **không sửa** `Authentication.getAuthorities()` của phiên/token đã phát hành.

Muốn revoke quyền nhạy cảm tức thời, hệ thống có thể cần invalidation session, token introspection/revocation, short-lived tokens, tải lại authorities hoặc policy động theo dữ liệu mới. Điều này độc lập với việc evict ACL.

### 9.4. Phân quyền người cập nhật ACL

Một endpoint cập nhật ACE là mục tiêu leo thang đặc quyền. Không dùng:

```java
// Phản mẫu: cho mọi user đăng nhập tự grant READ cho chính họ.
@PreAuthorize("isAuthenticated()")
public void grantAcl(Long id, String username) {
    // ...
}
```

Cần một policy quản lý ACL như `ROLE_ACL_ADMIN`, `ADMINISTRATION` permission, ownership phù hợp và tenant restrictions. Quyền `ADMINISTRATION` trên ACL không phải tự động đồng nghĩa với role toàn cục `ROLE_ADMIN`; ứng dụng phải định nghĩa chính sách ai được phép thay đổi ACE/parent/inheritance.

Khi cập nhật, audit nên ghi actor, target ObjectIdentity, SID, permission, allow/deny, chính sách trước/sau, revision, lý do, thời điểm và correlation ID, nhưng **không log secrets**.

## 10. Demo chạy được: ACL inheritance + cache + permission update

Để thấy rõ logic và chủ động kiểm chứng invalidation, project sau triển khai **một mô hình ACL học tập bằng Java**, có quy tắc local-first, cho phép inheritance và **cache quyết định theo user/authorities/object/permission**. Nó **không dùng các bảng JDBC ACL, `AclService` hay `SpringCacheBasedAclCache` của Spring Security ACL**. Phần 8 mới là API tham khảo của Spring ACL module. Mục đích của demo là làm rõ **khả năng kế thừa, update, stale decision và clear cache** trong một ứng dụng Spring Security Servlet chạy được.

Ứng dụng demo có:

- HTTP Basic để xác thực tài khoản; `SessionCreationPolicy.STATELESS`.
- GET đọc tài liệu theo ACL mô hình hóa; `AccessDeniedException` thành 403 nếu xác thực đúng mà không có READ.
- POST chỉnh ACE READ hoặc bật/tắt inheritance, **chỉ `ROLE_ACL_ADMIN`** được phép.
- CSRF mặc định được bật cho các POST; `GET /api/csrf` cấp token để client gửi lại cùng cookie.
- Cache quyết định và toàn bộ dữ liệu ACL in-memory, đồng bộ trong một instance bằng methods `synchronized`. Mọi mutation đều tăng `revision` và xóa decision cache toàn cục.
- Một test khẳng định thay parent ACE làm child thay đổi quyết định ngay ở request mới.

### 10.1. Project structure

```text
acl-inheritance-demo/
├── pom.xml
├── src/main/java/example/acl/
│   ├── AclDemoApplication.java
│   ├── SecurityConfig.java
│   ├── AclPolicyService.java
│   └── AclController.java
└── src/test/java/example/acl/
    └── AclIntegrationTest.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>acl-inheritance-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. AclDemoApplication.java

```java
package example.acl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclDemoApplication.class, args);
    }
}
```

### 10.4. SecurityConfig.java

```java
package example.acl;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo123");
        return new InMemoryUserDetailsManager(
            User.withUsername("alice").password(hash)
                .authorities("ROLE_READER").build(),
            User.withUsername("bob").password(hash)
                .authorities("ROLE_READER").build(),
            User.withUsername("auditor").password(hash)
                .authorities("ROLE_AUDITOR").build(),
            User.withUsername("admin").password(hash)
                .authorities("ROLE_ACL_ADMIN").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/resources/{id}")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/acl/{id}/read")
                    .hasRole("ACL_ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/acl/{id}/inheritance")
                    .hasRole("ACL_ADMIN")
                .anyRequest().denyAll());

        http.httpBasic(Customizer.withDefaults());
        http.formLogin(form -> form.disable());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache ->
                cache.requestCache(new NullRequestCache()));

        // HTTP Basic có thể được browser tự gửi nên demo giữ CSRF.
        http.csrf(csrf -> csrf.csrfTokenRepository(
                new CookieCsrfTokenRepository()));

        return http.build();
    }
}
```

**Đọc cấu hình:** `hasRole("ACL_ADMIN")` theo role prefix mặc định kiểm tra authority `ROLE_ACL_ADMIN`. GET resource chỉ yêu cầu authenticated ở filter; quyền READ cụ thể được service kiểm tra. POST còn phải có CSRF hợp lệ; thiếu token thường bị chặn 403 **trước** khi service cập nhật. `STATELESS` không dùng session để tải SecurityContext nhưng **không tự tắt CSRF**.

### 10.5. AclPolicyService.java

```java
package example.acl;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AclPolicyService {

    private enum Permission {
        READ
    }

    private record Ace(String sid, Permission permission, boolean grant) {
    }

    private record Node(long id, String title, Long parentId,
                        boolean entriesInheriting, List<Ace> aces) {
    }

    private record CacheKey(long id, String principal,
                            List<String> authorities, Permission permission) {
    }

    public record DocumentView(long id, String title, Long parentId,
                               boolean entriesInheriting, long aclRevision) {
    }

    public record UpdateResult(long id, String username,
                               boolean grant, long aclRevision) {
    }

    public record InheritanceResult(long id, boolean enabled,
                                    long aclRevision) {
    }

    private final Map<Long, Node> nodes = new HashMap<>();
    private final Map<CacheKey, Boolean> decisions = new HashMap<>();
    private long revision = 1L;

    public AclPolicyService() {
        // ACL parent: Alice được READ, Bob bị deny,
        // auditor (qua role) và admin được READ.
        nodes.put(101L, new Node(101L, "Workspace", null, false, List.of(
            new Ace("user:alice", Permission.READ, true),
            new Ace("user:bob", Permission.READ, false),
            new Ace("role:ROLE_AUDITOR", Permission.READ, true),
            new Ace("user:admin", Permission.READ, true)
        )));

        // Child 102 không có ACE local, kế thừa quyền từ parent.
        nodes.put(102L, new Node(102L, "Quarterly plan", 101L, true,
                List.of()));

        // Child 103 từ chối Alice ngay tại local ACL, vẫn cho
        // các SID khác tiếp tục kế thừa nếu không có ACE khớp.
        nodes.put(103L, new Node(103L, "Private draft", 101L, true,
                List.of(new Ace("user:alice", Permission.READ, false))));
    }

    public synchronized DocumentView read(Authentication auth, long id) {
        Node node = find(id);

        if (auth == null || !auth.isAuthenticated()
                || !isGranted(auth, id, Permission.READ)) {
            throw new AccessDeniedException(
                    "READ permission denied for resource " + id);
        }

        return new DocumentView(node.id(), node.title(), node.parentId(),
                node.entriesInheriting(), revision);
    }

    private Node find(long id) {
        Node node = nodes.get(id);
        if (node == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Resource not found");
        }
        return node;
    }

    private boolean isGranted(Authentication auth, long id,
                              Permission permission) {
        // Cache key tách principal, authorities và loại quyền.
        // Nếu không có authorities trong key, role đã thay đổi
        // có thể dùng nhầm kết quả cũ của cùng username.
        List<String> authorities = auth.getAuthorities().stream()
                .map(a -> a.getAuthority())
                .sorted()
                .collect(Collectors.toUnmodifiableList());

        CacheKey key = new CacheKey(id, auth.getName(),
                authorities, permission);
        Boolean hit = decisions.get(key);
        if (hit != null) {
            return hit;
        }

        boolean granted = evaluate(find(id), auth, permission,
                new HashSet<>());
        decisions.put(key, granted);
        return granted;
    }

    private boolean evaluate(Node node, Authentication auth,
                             Permission permission, Set<Long> visited) {
        if (!visited.add(node.id())) {
            throw new IllegalStateException("ACL parent cycle detected");
        }

        // MÔ HÌNH LAB: ACE local đầu tiên khớp SID+permission
        // quyết định; Spring ACL thật có strategy, mask/order riêng.
        for (Ace ace : node.aces()) {
            if (ace.permission() == permission
                    && matches(ace.sid(), auth)) {
                return ace.grant();
            }
        }

        if (node.entriesInheriting() && node.parentId() != null) {
            return evaluate(find(node.parentId()), auth,
                    permission, visited);
        }

        // Fail closed nếu không có ACE local/parent nào grant.
        return false;
    }

    private boolean matches(String sid, Authentication auth) {
        if (sid.startsWith("user:")) {
            return sid.substring("user:".length()).equals(auth.getName());
        }
        if (sid.startsWith("role:")) {
            String wanted = sid.substring("role:".length());
            return auth.getAuthorities().stream().anyMatch(
                    a -> wanted.equals(a.getAuthority()));
        }
        return false;
    }

    @PreAuthorize("hasRole('ACL_ADMIN')")
    public synchronized UpdateResult setReadRule(long id, String username,
                                                   boolean grant) {
        // Không cho client tự tạo tùy ý SID của user ngoài demo.
        if (!Set.of("alice", "bob", "auditor", "admin").contains(username)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unknown demo username");
        }

        Node old = find(id);
        List<Ace> updated = new ArrayList<>(old.aces());
        String sid = "user:" + username;

        // Thay ACE cũ cùng SID+permission, tránh duplicate/order mơ hồ.
        updated.removeIf(a -> a.permission() == Permission.READ
                && a.sid().equals(sid));
        updated.add(0, new Ace(sid, Permission.READ, grant));

        nodes.put(id, new Node(old.id(), old.title(), old.parentId(),
                old.entriesInheriting(), List.copyOf(updated)));

        // Mô hình 1 instance: global revision + xóa toàn bộ
        // decision cache, bao gồm decisions trên các descendants.
        revision++;
        decisions.clear();
        return new UpdateResult(id, username, grant, revision);
    }

    @PreAuthorize("hasRole('ACL_ADMIN')")
    public synchronized InheritanceResult setInheritance(
            long id, boolean enabled) {
        Node old = find(id);

        if (old.parentId() == null && enabled) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Root ACL has no parent to inherit");
        }

        nodes.put(id, new Node(old.id(), old.title(), old.parentId(),
                enabled, old.aces()));

        revision++;
        decisions.clear();
        return new InheritanceResult(id, enabled, revision);
    }
}
```

**Độ chính xác của mô hình:**

- Mỗi `Node` chứa parent ID, `entriesInheriting` và danh sách ACE local.
- `evaluate` duyệt ACE local theo thứ tự, tìm SID user hoặc role khớp; nếu không có quyết định và inheritance bật thì lên parent.
- `HashSet` phát hiện parent cycle. Production phải **ngăn cycle tại thời điểm thay đổi parent** chứ không chỉ phát hiện lúc read.
- `CacheKey` bao gồm object ID, user name, danh sách authorities và permission, nên không dùng kết quả của Alice cho Bob. Production multi-tenant cần thêm tenant, namespace, policy/ACL revisions và các attributes tham gia quyết định.
- `decisions` là **decision cache tùy viết** trong lab, không phải `AclCache` của Spring Security ACL. Cache cả grant lẫn deny.
- Mọi method đọc/cập nhật đều `synchronized`; khi update, `revision++` và `decisions.clear()` cùng nằm trong critical section. Chúng ta chấp nhận flush toàn bộ để đảm bảo child kế thừa không giữ kết quả cũ.
- Đây chỉ là **một JVM**; không có persistence, cluster invalidation, tenant-aware ACL hay distributed transactions. Restart reset state. Không dùng code này làm ACL production.
- `@PreAuthorize("hasRole('ACL_ADMIN')")` trên service được kiểm tra qua proxy khi controller gọi service; URL cũng có policy quản trị tương tự, tạo lớp phòng vệ bổ sung.

### 10.6. AclController.java

```java
package example.acl;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class AclController {

    private final AclPolicyService policy;

    public AclController(AclPolicyService policy) {
        this.policy = policy;
    }

    @GetMapping("/api/csrf")
    public String csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }
        return token.getToken();
    }

    @GetMapping("/api/resources/{id}")
    public AclPolicyService.DocumentView read(
            @PathVariable long id, Authentication auth) {
        return policy.read(auth, id);
    }

    @PostMapping("/api/acl/{id}/read")
    public AclPolicyService.UpdateResult updateRead(
            @PathVariable long id, @RequestBody ReadRuleRequest body) {
        if (body == null || body.grant() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "grant must be true or false");
        }
        return policy.setReadRule(id, body.username(), body.grant());
    }

    @PostMapping("/api/acl/{id}/inheritance")
    public AclPolicyService.InheritanceResult updateInheritance(
            @PathVariable long id, @RequestBody InheritanceRequest body) {
        if (body == null || body.enabled() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "enabled must be true or false");
        }
        return policy.setInheritance(id, body.enabled());
    }

    public record ReadRuleRequest(String username, Boolean grant) {
    }

    public record InheritanceRequest(Boolean enabled) {
    }
}
```

HTTP route update được chặn bằng `hasRole("ACL_ADMIN")` ở filter và kiểm tra lại tại service với `@PreAuthorize`. Việc dùng Boolean object thay boolean primitive giúp từ chối request JSON thiếu field (không âm thầm hiểu là false).

### 10.7. AclIntegrationTest.java

```java
package example.acl;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AclIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void aliceCanReadInheritedChildButNotLocallyDeniedChild()
            throws Exception {
        mvc.perform(get("/api/resources/102")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(102));

        mvc.perform(get("/api/resources/103")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorInheritsRoleBasedRead() throws Exception {
        mvc.perform(get("/api/resources/103")
                .with(httpBasic("auditor", "demo123")))
                .andExpect(status().isOk());
    }

    @Test
    void userCannotChangeAclEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/acl/101/read")
                .with(httpBasic("alice", "demo123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"bob\",\"grant\":true}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void mutationWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/acl/101/read")
                .with(httpBasic("admin", "demo123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"bob\",\"grant\":true}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void parentChangeInvalidatesChildDecisionAndInheritanceToggle()
            throws Exception {
        // Lần đầu tiên tạo cached DENY cho Bob ở child 102.
        mvc.perform(get("/api/resources/102")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isForbidden());

        // Admin cập nhật parent 101; global cache phải bị clear.
        mvc.perform(post("/api/acl/101/read")
                .with(httpBasic("admin", "demo123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"bob\",\"grant\":true}"))
                .andExpect(status().isOk());

        // Request mới không được dùng stale DENY từ child cache.
        mvc.perform(get("/api/resources/102")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isOk());

        // Khi tắt inheritance ở child 102, local ACL rỗng:
        // Bob không còn được phép READ dù parent đã grant.
        mvc.perform(post("/api/acl/102/inheritance")
                .with(httpBasic("admin", "demo123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":false}"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/resources/102")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isForbidden());
    }
}
```

**Tại sao có `@DirtiesContext`?** Test mutation làm thay đổi state in-memory. Annotation đặt sau method test để Spring làm mới context sau test đó, giúp hạn chế ảnh hưởng lên test khác. Test suite thực tế có thể dùng fixtures/reset riêng, database transaction rollback hoặc tạo store mới cho mỗi test.

Test `@PreAuthorize` chạy qua Spring-managed service proxy vì controller inject `AclPolicyService`. Nếu bỏ `@EnableMethodSecurity` hoặc gọi service bằng `new`, lớp bảo vệ ở service có thể không hoạt động; bài test từ chối cập nhật ở URL vẫn pass do HTTP rule, vì vậy trong hệ thống thật nên bổ sung test service-level trực tiếp nếu muốn chứng minh defense in depth.

### 10.8. Chạy ứng dụng

Tại thư mục có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Yêu cầu JDK 17+ và Maven. Server mặc định phục vụ tại `http://localhost:8080`. Sử dụng HTTP Basic và secret demo **chỉ trên localhost**; production bắt buộc HTTPS để bảo vệ credentials, cookie và CSRF token.

## 11. Thực hành HTTP và quan sát ACL cache

### 11.1. Đọc resource theo inheritance

```bash
curl -s -u alice:demo123 http://localhost:8080/api/resources/102
```

JSON dự kiến khi chưa có cập nhật:

```json
{"id":102,"title":"Quarterly plan","parentId":101,"entriesInheriting":true,"aclRevision":1}
```

Alice được phép ở child 102 vì parent 101 có ACE Alice READ allow và child 102 kế thừa.

### 11.2. Local deny chặn Alice

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:demo123 http://localhost:8080/api/resources/103
```

Output:

```text
403
```

Child 103 có ACE Alice READ deny. Vì local check đã quyết định, bài lab không dùng grant Alice ở parent để vượt qua.

### 11.3. Auditor được kế thừa từ role SID

```bash
curl -s -u auditor:demo123 http://localhost:8080/api/resources/103
```

JSON:

```json
{"id":103,"title":"Private draft","parentId":101,"entriesInheriting":true,"aclRevision":1}
```

Auditor được kế thừa grant từ `role:ROLE_AUDITOR` ở parent 101, vì không có ACE local auditor tại child 103.

### 11.4. Bob bị deny trước update

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:demo123 http://localhost:8080/api/resources/102
```

Output:

```text
403
```

Kết quả deny được lưu trong decision cache theo key có principal Bob. Update parent sau đó phải làm cache này bị bỏ.

### 11.5. Lấy CSRF token cho POST admin

Vì API giữ CSRF, lệnh POST JSON cần **CSRF token từ server và cookie đi cùng**:

```bash
csrf_token="$(curl -fsS -c acl-cookies.txt \
  http://localhost:8080/api/csrf)"
```

Token trả về được đọc qua `CsrfToken.getToken()`; trong Spring Security 6, token có thể có dạng mask phù hợp handler hiện tại. Đừng giả định gửi raw cookie value vào header là đúng với mọi version/config. Dùng token nhận từ endpoint lab rồi gửi cùng cookie:

```bash
curl -i -u admin:demo123 -b acl-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","grant":true}' \
  http://localhost:8080/api/acl/101/read
```

Kỳ vọng status 200 và JSON:

```json
{"id":101,"username":"bob","grant":true,"aclRevision":2}
```

Admin sửa ACE READ của Bob **ở parent 101**, tăng revision từ 1 lên 2 và xóa toàn bộ decision cache trong một JVM.

### 11.6. Bob vào child ngay sau update

```bash
curl -s -u bob:demo123 http://localhost:8080/api/resources/102
```

JSON:

```json
{"id":102,"title":"Quarterly plan","parentId":101,"entriesInheriting":true,"aclRevision":2}
```

Đây là test quan trọng: **dù Bob không có ACE local ở child 102**, parent grant mới phải được dùng. Nếu một cached deny cũ vẫn được giữ, Bob có thể tiếp tục 403 dù update đã thành công — bug **cache invalidation sau thay đổi ACL parent**.

### 11.7. Tắt inheritance ở child

Dùng cùng CSRF token/cookie **nếu token còn hợp lệ** (hoặc gọi lại endpoint lấy token khi cần):

```bash
curl -i -u admin:demo123 -b acl-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}' \
  http://localhost:8080/api/acl/102/inheritance
```

Kỳ vọng:

```json
{"id":102,"enabled":false,"aclRevision":3}
```

Giờ child 102 không có ACE local cho Bob và đã tắt kế thừa:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:demo123 http://localhost:8080/api/resources/102
```

Kỳ vọng:

```text
403
```

Dù parent 101 grant Bob READ, child 102 không còn nhận quyền đó. Khi bật inheritance lại, nếu parent grant vẫn tồn tại, Bob có thể được phép trong request tiếp theo. Mỗi mutation của lab sẽ tăng revision và xóa cache.

### 11.8. Thiếu CSRF / sai actor

Thử admin POST nhưng **không gửi CSRF token**:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:demo123 \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","grant":true}' \
  http://localhost:8080/api/acl/101/read
```

Thường nhận:

```text
403
```

Đây là CSRF failure, không chứng minh actor thiếu role ACL_ADMIN. Nếu gửi token hợp lệ nhưng dùng `alice:demo123` (không có `ROLE_ACL_ADMIN`), response thường cũng 403 — **nhưng lý do là authorization**, không phải CSRF. Với request chưa có credentials, kết quả có thể là 401 nếu CSRF hợp lệ hoặc 403 nếu bị CSRF filter chặn trước; không ghép chúng thành một quy luật duy nhất.

## 12. Kết quả cache cần kiểm tra sau mỗi mutation

Bảng regression tests quan trọng:

| Trước thay đổi | Thao tác quản trị | Request mới cần kiểm tra |
| --- | --- | --- |
| Parent deny Bob; child inherit | Grant Bob ở parent | Child phải chuyển **deny → grant** |
| Parent grant Alice; child inherit | Deny Alice ở parent | Child không còn được grant nếu không có local override |
| Parent grant Alice; child inherit | Deny Alice local ở child | Child deny, parent không tự override |
| Parent grant Bob; child inherit | `entriesInheriting=false` ở child | Child mất parent permission |
| Child inherit=false, local empty | Bật `entriesInheriting=true` | Child lại nhận parent grant |
| Parent có grant cho role AUDITOR | Thu hồi role của user | Session/token stale phải được xử lý thêm |
| Child chuyển sang parent khác | Thay parent identity | Child lấy policy từ parent mới |
| ACL của resource bị xóa | Xóa ACL | Cache của object/decision không còn dữ liệu cũ |
| Nhiều instances chạy độc lập | Update tại node A | Node B không được dùng cache ACL/decision cũ |
| ACL update rollback | DB không commit | Cache/state không được biểu diễn policy chưa commit |

**Một request nhận 200 ngay sau update không chứng minh toàn bộ hệ thống đúng.** Với cache distributed, kiểm tra các node khác; với parent ACL, kiểm tra descendants; với role-based ACE, kiểm tra sessions/tokens còn cũ; với deny cache, kiểm tra grant sau update; với grant cache, kiểm tra revocation sau update.

## 13. Multi-node ACL cache: không thể chỉ xóa tại một JVM

Một mô hình phân tán:

```text
Client
   |
   v
Load Balancer
   +--> App A: AclCache_A + DecisionCache_A
   |
   +--> App B: AclCache_B + DecisionCache_B
   |
   +--> App C: AclCache_C + DecisionCache_C
               |
               v
             ACL DB
```

Nếu admin đổi ACL parent qua App A:

- App A cập nhật DB.
- App A clear cache cục bộ.
- App B/C **có thể tiếp tục dùng cached policy cũ** nếu không nhận invalidation.
- TTL dài có thể khiến quyền đã thu hồi vẫn được sử dụng thêm một khoảng thời gian không chấp nhận được.

Các giải pháp production cân nhắc:

1. **Distributed cache** hỗ trợ invalidation nhất quán hoặc TTL rất ngắn theo yêu cầu rủi ro.
2. **Versioned cache keys**: mỗi policy generation/revision sau commit được kiểm tra trước khi quyết định.
3. **Outbox/event**: database commit update cùng outbox record, worker phát event đến các instances; mỗi node evict đúng subtree/revision. Xử lý lost events, duplicate delivery, retries.
4. **Read-through từ DB** khi quyền nhạy cảm cần nhất quán mạnh hơn cache eventual.
5. **Observability**: metrics hit/miss, invalidation lag, stale reads, update conflicts, audit actor/policy revision.

**Không có giải pháp miễn phí cho cả consistency và performance.** Tần suất update, độ sâu cây ACL, số lượng users/SIDs, TTL và SLA thu hồi quyết định thiết kế cache.

## 14. Tenant boundaries và quyền cập nhật parent

Đối với SaaS, một resource có thể thuộc tenant A, còn parent được trỏ nhầm sang tenant B. Nếu bỏ qua ranh giới này, inheritance có thể đưa permission từ tổ chức khác sang resource hiện tại.

Các quy tắc nên kiểm tra:

- ObjectIdentity phải kết hợp đúng **class/type + ID**, và có tenant scope theo model.
- Chỉ cho phép parent ACL từ phạm vi nghiệp vụ được phép.
- Người sửa ACL phải có quyền manage ACL trên **resource đích**, không chỉ có quyền đọc.
- Không cho client tự chọn tên SID/role rồi cấp quyền bừa bãi.
- Khi cập nhật parent, kiểm tra cycle, độ sâu tối đa và cả descendants nếu có sự thay đổi tenant/scope.
- Khi user bị xóa hoặc role bị thu hồi, có quy trình dọn ACE/SID mồ côi và invalidation.
- Dùng ID nội bộ đáng tin cho principal/tenant; username là ví dụ đơn giản nhưng có thể trùng hoặc đổi tên.
- Cân nhắc separation-of-duties: người phê duyệt không tự cấp quyền duyệt cho mình khi nghiệp vụ cấm.

Tránh quy tắc:

```text
request.header["X-Tenant"] == acl.tenant
    => grant
```

Vì header do client tùy ý đặt không chứng minh tenant membership. Hãy lấy tenant scope từ authentication đã xác minh và datastore tin cậy, rồi đối chiếu với resource identity.

## 15. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Thay parent nhưng child vẫn 403 | Decision cache child giữ deny cũ, hoặc child `entriesInheriting=false` | Kiểm tra flag và invalidate descendant decisions |
| Thu hồi READ nhưng user vẫn vào được | Cached grant stale, session/JWT còn SID role cũ | Kiểm tra ACL cache + decision cache + authentication lifecycle |
| Thêm allow mà kết quả vẫn deny | Deny ACE trước allow, duplicate/order/mask | Đọc ACE order và PermissionGrantingStrategy thực tế |
| Parent grant nhưng child deny | Child có ACE local phủ quyết | Debug local ACL, Sid/mask, inheritance flag |
| Child được grant dù đã tắt inherit | Có local ACE grant hoặc decision cache cũ | Kiểm tra entriesInheriting và invalidation |
| Auditor không nhận role-based ACE | Authority mapping không khớp GrantedAuthoritySid | Kiểm tra ROLE_ prefix và SIDs được nạp |
| Một node đúng, node khác sai | Cache distributed không được invalidated | Kiểm tra cluster events/revisions |
| Cập nhật ACL trả 200 nhưng policy cũ | Transaction chưa commit, invalidation quá sớm, cache refill race | Kiểm tra commit/outbox/version |
| Hai admin thay quyền làm mất update | Concurrent write không có version check | Optimistic locking hoặc khóa transaction |
| Đọc ACL thất bại UnloadedSidException | ACL tải không đủ SIDs yêu cầu | Kiểm tra AclService.readAclById/lookup và SIDs |
| Permission không có ACE phù hợp | Không có quyết định grant | Fail closed thay vì mặc định allow |
| ACL không tìm thấy | Resource chưa có ACL, type/id sai | Xác minh ObjectIdentity và create/migration |
| Dữ liệu cross-tenant bị lộ | Parent cross-tenant hoặc principal mapping sai | Tenant-aware policy + tests |
| Bản cache là Acl cũ sau SQL trực tiếp | Bypass MutableAclService cache logic | Invalidate đầy đủ, không chỉ update DB |
| POST sửa ACL trả 403 | Thiếu CSRF hoặc actor không đủ role | Phân biệt CSRF validation với authorization |
| Java demo restart mất quyền vừa cập nhật | In-memory state không persistence | Dùng JDBC ACL hoặc datastore production |
| Thứ tự ACE gây outcome bất ngờ | Dùng nhiều SIDs và masks, strategy order | Kiểm thử cụ thể sid/permission/ACE order |

### Debug theo trình tự

1. Xác nhận `ObjectIdentity` đúng type/ID/tenant.
2. Xác nhận Authentication/SIDs và role mapping thực tế, không tin header client.
3. Kiểm tra `Acl.getEntries()`, mask, `granting`, `ace_order`.
4. Xác nhận `isEntriesInheriting()` và `getParentAcl()`.
5. Kiểm tra parent chain không cycle và policy không vượt tenant.
6. Xác minh `AclCache` có đọc dữ liệu stale không; nếu có decision cache riêng, kiểm tra cả nó.
7. Xác nhận update ACL đã commit và revision mới thấy được trên các instances.
8. Chạy request mới cho affected principal/permission và child descendants.
9. Đối chiếu 401/403/404, không coi 403 do CSRF là bằng chứng ACL deny.
10. Ghi audit an toàn, không log Authorization header, password, session token hoặc toàn bộ tài liệu.

Trong development có thể bật log Spring Security có kiểm soát:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật raw secret/token logging ở production. Khi cần chẩn đoán policy, log resource ID, actor, permission, revision và decision thay vì chép cả object/cookie vào log.

## 16. Câu hỏi tự kiểm tra

1. **ACL khác role-based authorization ở điểm nào?** ACL gắn permission/SID với từng object cụ thể, có thể theo parent.
2. **ObjectIdentity gồm gì?** Kiểu tài nguyên và ID duy nhất trong namespace phù hợp.
3. **SID có phải chỉ là username?** Không; có PrincipalSid và GrantedAuthoritySid.
4. **ACE chứa gì?** SID, Permission/mask, grant/deny, thứ tự và metadata audit tùy schema.
5. **entriesInheriting=true có nghĩa child luôn cho phép nếu parent cho phép không?** Không; local ACE có thể quyết định trước, còn SID/mask/strategy ảnh hưởng.
6. **entriesInheriting=false có làm mọi local ACE mất hiệu lực không?** Không; nó ngắt việc fallback đến parent.
7. **Deny luôn ưu tiên hơn mọi allow trong Spring ACL?** Không được khái quát; thứ tự ACE và granting strategy quan trọng.
8. **AclCache lưu gì?** ACL object đã tải, không mặc định là cache Boolean cho từng principal.
9. **Decision cache cần khóa theo gì?** Ít nhất object, permission, principal/SIDs/authorities và policy revision/context.
10. **Vì sao sửa parent phải xét descendants?** Quyền inherited của children có thể thay đổi dù local ACE không đổi.
11. **Khi cấp quyền mới, cần vô hiệu cache grant hay deny?** Cả hai loại quyết định liên quan: deny cũ gây lỗi, grant cũ gây lỗ hổng khi revoke.
12. **Cache TTL có đủ bảo đảm revoke ngay?** Không, phải có invalidation/consistency strategy phù hợp.
13. **User bị thu hồi role nhưng JWT vẫn chứa role cũ thì sao?** ACL cache evict không cập nhật token/sessions cũ.
14. **Vì sao ACL update cần transaction và concurrency control?** Tránh lost updates và cache invalidation trước commit.
15. **Có thể chỉnh ACL bằng POST không CSRF với Basic browser?** Không trong demo; phải gửi CSRF token hợp lệ.
16. **Ai được quyền cập nhật ACL?** Một actor có manage-ACL permission/role phù hợp và tenant scope tin cậy.
17. **Vì sao demo dùng global revision và clear tất cả decisions?** Đơn giản, loại bỏ stale child decisions trong một JVM, dù chưa tối ưu.
18. **Demo đang chạy có phải Spring Security ACL JDBC không?** Không, đó là mô hình học tập; API module Spring ACL thật được giới thiệu ở mục 8.
19. **Làm sao chứng minh fix cache hiệu quả?** Tạo cached deny của child, sửa ACE ở parent, rồi request lại child phải đổi sang allow.
20. **Điều gì xảy ra nếu đổi parent sang tenant khác?** Có thể vượt ranh giới bảo mật; phải chặn theo policy.

## 17. Checklist triển khai production

- [ ] Có mô hình ObjectIdentity type/ID/tenant rõ ràng và unique.
- [ ] SID xuất phát từ authentication/authority mapping đã kiểm chứng.
- [ ] Thứ tự ACE, masks, grant/deny và PermissionGrantingStrategy được tài liệu hóa và test.
- [ ] Parent ACL tạo cấu trúc không cycle, không vượt ranh giới tenant.
- [ ] Quy tắc `entriesInheriting` được test cho cả bật và tắt.
- [ ] Cache ACL và cache quyết định được **phân biệt rõ**, không gộp nhầm key.
- [ ] Cache decision key bao phủ principal/SIDs, permission, object và revision/context.
- [ ] Mutation ACL invalidates parent/descendants chịu ảnh hưởng và cả positive/negative decisions.
- [ ] Với nhiều node, có distributed invalidation/versioning/outbox sau commit.
- [ ] ACL writes có transaction và cơ chế tránh lost update.
- [ ] Chỉ actor có quyền manage ACL và scope tenant phù hợp mới được sửa ACE, parent hoặc inheritance.
- [ ] Kiểm tra revocation của session/JWT/role cache độc lập với AclCache.
- [ ] Không bỏ qua CSRF cho API cookie/Basic mà browser có thể gửi credentials tự động.
- [ ] Bảo vệ HTTPS, tránh log credentials/token/resource nhạy cảm.
- [ ] Test parent update làm đổi child quyền, local deny, inheritance off, role SID, invalidation và multi-node nếu có.
- [ ] Sử dụng database migration/schema ACL đúng version và có indexes cho object/parent/SID.
- [ ] Theo dõi cache hit/miss, invalidation lag, database lookup và audit ACL mutations.
- [ ] Dùng demo in-memory để học, không dùng thay thế Spring Security ACL JDBC ở production.

**Kết luận:** Spring Security ACL cho phép mô tả quyền **trên từng tài nguyên** bằng `ObjectIdentity`, `Sid`, `Permission` và danh sách `ACE`. Cờ `entriesInheriting` quyết định có tiếp tục kiểm tra ACL parent khi local không kết luận hay không; thứ tự ACE/permission masks phải được hiểu đúng. Khi ACL **cha**, ACL **con** hoặc SID/role thay đổi, các cache liên quan có thể trở nên stale — đặc biệt là **cached allow sau khi quyền đã bị thu hồi**. Cần cập nhật ACL có phân quyền, transaction, invalidation descendants/decisions và consistency giữa các nodes, đồng thời kiểm thử quyền trên **request mới** sau cập nhật.