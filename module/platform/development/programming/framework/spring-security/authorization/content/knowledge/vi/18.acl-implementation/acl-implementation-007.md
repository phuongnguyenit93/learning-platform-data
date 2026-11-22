# Đổi chủ sở hữu, thay đổi ACL cha và cập nhật kế thừa trong Spring Security ACL

## 1. Mục tiêu bài học

Khi triển khai Spring Security ACL, việc cấp thêm một `AccessControlEntry` (ACE) mới chỉ giải quyết một phần bài toán. Trong ứng dụng tài liệu, thư mục, dự án hoặc tổ chức, quyền còn biến động khi **đổi chủ sở hữu ACL**, **chuyển tài nguyên sang một ACL cha khác** và **bật/tắt kế thừa quyền**. Ba thao tác này tương ứng với ba API của `MutableAcl`:

```java
mutableAcl.setOwner(new PrincipalSid("bob"));
mutableAcl.setParent(parentAcl);
mutableAcl.setEntriesInheriting(true);
mutableAclService.updateAcl(mutableAcl);
```

Đoạn mã chỉ minh họa cú pháp. Trong thực tế, phải lấy ACL đã tồn tại từ `MutableAclService`, kiểm tra quyền quản trị, xác minh cha hợp lệ, thực hiện trong transaction phù hợp, lưu lại và đọc lại để xác nhận hiệu lực.

Bài thuộc nhóm **Triển khai ACL** của Spring Security Authorization. Sau khi học, bạn sẽ:

1. Phân biệt **ACL owner** với chủ sở hữu dữ liệu nghiệp vụ và với người được cấp ACE READ/WRITE.
2. Hiểu sự khác nhau giữa `Acl.getParentAcl()` và `Acl.isEntriesInheriting()`.
3. Thực hiện thay owner, thay parent, bật/tắt inheritance bằng `MutableAcl` và `MutableAclService.updateAcl(...)`.
4. Giải thích ảnh hưởng của ACE tại ACL con, ACE tại ACL cha, explicit deny, không có ACE và nhiều tầng kế thừa.
5. Biết cách tổ chức service quản trị: authorization, transaction, kiểm tra vòng lặp, cross-tenant, cache invalidation.
6. Viết kiểm thử Java 17+ với HSQLDB và Spring Security ACL JDBC để chứng minh trạng thái **trước/sau khi thay đổi**.
7. Tránh sai lầm nguy hiểm: đổi owner tưởng là đã cấp READ, liên kết parent tưởng là tự kế thừa, hoặc sửa object trong RAM nhưng quên `updateAcl`.

**Phạm vi:** Spring Security ACL 6.5.x, Spring Boot 3.x, Java 17+; thao tác trên Spring-managed service/ACL JDBC. Những dự án dùng SQL schema, cache, SID strategy hoặc Spring Security version khác cần đối chiếu lại cấu hình và kiểm thử.

## 2. Nhắc lại mô hình ACL và những cột liên quan

Một `Acl` bảo vệ một `ObjectIdentity` cụ thể, ví dụ `demo.Document#42`. Nó gồm các ACE gắn `Sid` với `Permission` và cờ `granting`. ACL có thể có **owner**, **parent ACL** và **cờ kế thừa**.

```text
ObjectIdentity: ("demo.Document", 42L)
          |
          v
Acl của tài liệu 42
  owner                 = PrincipalSid("acl-admin")
  parentAcl             = Acl của Folder#10
  entriesInheriting     = true
  local ACEs:
      PrincipalSid("alice")  WRITE   GRANT
      PrincipalSid("bob")    READ    DENY
          |
          | nếu không có quyết định khớp ở con
          v
Acl của Folder#10
  owner                 = PrincipalSid("folder-admin")
  parentAcl             = null
  local ACEs:
      GrantedAuthoritySid("ROLE_REVIEWER") READ GRANT
      PrincipalSid("carol")                READ GRANT
```

Bốn bảng thường dùng với JDBC ACL:

| Bảng | Trường quan trọng | Ý nghĩa trong bài |
| --- | --- | --- |
| `acl_sid` | `id`, `principal`, `sid` | Lưu owner mới và SID của ACE |
| `acl_class` | `id`, `class` | Phân biệt loại domain object |
| `acl_object_identity` | `id`, `object_id_class`, `object_id_identity`, **`owner_sid`**, **`parent_object`**, **`entries_inheriting`** | Ba trường in đậm được thay khi đổi owner/parent/inheritance |
| `acl_entry` | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting` | Quy tắc quyền cục bộ của từng ACL |

Một `Document#42` có thể có ID nghiệp vụ 42, nhưng hàng `acl_object_identity` mang ID khác; `parent_object` trỏ đến **ID của hàng ACL cha**, không phải ID của folder trong bảng domain. `owner_sid` trỏ đến `acl_sid.id`.

Mặc dù các cột lưu trữ riêng, **việc thay đổi chúng phải qua API và quy trình được ủy quyền**, không khuyến khích một endpoint tự chạy `UPDATE acl_object_identity ...` bỏ qua chiến lược và cache của Spring Security.

## 3. Thao tác 1 — `setOwner(Sid)`: đổi chủ sở hữu ACL

### 3.1. Chủ sở hữu ACL là gì?

`Acl.getOwner()` trả về một `Sid`, thường là `PrincipalSid` của người quản trị ACL. Owner có thể được `AclAuthorizationStrategyImpl` dùng để xác định người có khả năng sửa quyền ACL.

**Không nhầm với quyền đối với dữ liệu nghiệp vụ:**

- `Acl.getOwner() == PrincipalSid("alice")` nói về **người sở hữu ACL** trong mô hình ACL.
- `Document.ownerId == "alice"` là một trường **nghiệp vụ**, không tự được Spring ACL đồng bộ với `acl_sid`.
- Alice có `Acl.getOwner()` **không có nghĩa** Alice tự động có `BasePermission.READ` hoặc `WRITE`; quyền domain được xác định qua ACE và `PermissionGrantingStrategy`.
- Một ACE `PrincipalSid("alice")/READ/GRANT` vẫn tồn tại khi owner chuyển sang Bob, trừ khi service quản trị cố ý thay ACE đó.

Theo `AclAuthorizationStrategyImpl` mặc định, chủ sở hữu ACL, principal có một authority quản trị ACL được cấu hình, hoặc người có `BasePermission.ADMINISTRATION` phù hợp có thể đủ điều kiện thực hiện thay đổi ACL. **Không** coi điều này là một chính sách quản trị business đầy đủ; cần kiểm tra quyền gọi endpoint/service theo hợp đồng tổ chức.

### 3.2. Cách đổi owner đúng

```java
ObjectIdentity identity =
    new ObjectIdentityImpl("demo.Document", 42L);

MutableAcl acl = (MutableAcl) mutableAclService.readAclById(identity);
Sid oldOwner = acl.getOwner();

acl.setOwner(new PrincipalSid("bob"));
MutableAcl saved = mutableAclService.updateAcl(acl);

System.out.println(saved.getOwner());
```

Đây là **snippet tích hợp**, giả định `mutableAclService` đã được inject, bảng ACL tồn tại, và người gọi có quyền thay owner; không có stdout cố định vì `Sid.toString()` tùy implementation. `MutableAcl.setOwner` yêu cầu `Sid` mới **khác null**. `updateAcl` mới lưu thay đổi vào database và trả về ACL đã đọc lại.

**Trình tự an toàn cho API chuyển owner:**

1. Xác thực actor và kiểm tra actor có quyền **chuyển quyền quản trị ACL** của đối tượng này.
2. Kiểm tra object thuộc đúng tenant, owner đích tồn tại và có thể nhận ownership.
3. Đọc ACL đầy đủ, ghi nhận oldOwner, sửa `setOwner(new PrincipalSid(...))`.
4. Gọi `updateAcl` trong transaction phù hợp.
5. Đọc lại, audit actor/oldOwner/newOwner/objectId và kiểm tra policy sau chuyển.
6. Nếu nghiệp vụ yêu cầu owner mới được READ/WRITE, **cập nhật ACE rõ ràng**; nếu owner cũ phải mất quyền domain, **thu hồi ACE tương ứng rõ ràng**. Không gộp hai yêu cầu thành giả định.

**Lưu ý đặc biệt:** `AclAuthorizationStrategy` có các change type `CHANGE_OWNERSHIP`, `CHANGE_GENERAL` và `CHANGE_AUDITING`. `AclAuthorizationStrategyImpl` có thể nhận một authority dùng chung cả ba loại, hoặc ba authority khác nhau theo thứ tự ownership/auditing/general. Việc đổi owner là thao tác nhạy cảm hơn việc thêm permission thông thường, nên nên phân quyền riêng.

## 4. Thao tác 2 — `setParent(Acl)`: thay ACL cha

`Acl.getParentAcl()` là **quan hệ điều hướng** từ ACL con đến ACL cha. Nó không được tự suy ra từ `Document.folderId`: ứng dụng phải thiết lập và cập nhật ACL parent khi quan hệ nghiệp vụ thay đổi.

```java
ObjectIdentity childId =
    new ObjectIdentityImpl("demo.Document", 42L);
ObjectIdentity folderId =
    new ObjectIdentityImpl("demo.Folder", 10L);

MutableAcl child =
    (MutableAcl) mutableAclService.readAclById(childId);
Acl folderAcl = mutableAclService.readAclById(folderId);

child.setParent(folderAcl);
mutableAclService.updateAcl(child);
```

Đây là snippet tích hợp. Tham số `setParent` là **`Acl`**, không phải `ObjectIdentity`, `Long`, hay SID. Phải tải ACL cha từ service trước khi gắn. Để bỏ quan hệ cha, dùng `child.setParent(null)` rồi `updateAcl(child)`, đồng thời đảm bảo xử lý hậu quả nghiệp vụ.

### 4.1. Chuyển con từ cha A sang cha B

```text
TRƯỚC:
  Document #42 -> Folder A ACL
                    Alice READ GRANT

SAU:
  Document #42 -> Folder B ACL
                    Bob READ GRANT
```

Nếu ACL con bật kế thừa và không có ACE phù hợp của chính nó, việc đổi parent có thể khiến Alice **mất** quyền kế thừa từ A, trong khi Bob **nhận** quyền kế thừa từ B.

Nếu ACL con tắt kế thừa, quan hệ cha mới vẫn được lưu dưới `parent_object` nhưng không tự trao quyền của parent B. Đây là lý do cần xét **hai trạng thái**: parent link và inheritance flag.

### 4.2. Chống chu trình và cross-tenant

Quan hệ ACL parent nên tạo một đồ thị **không có chu trình**. Không được gắn `child.setParent(child)` hay để A → B → C → A. Cấu hình SQL foreign key tự tham chiếu không đủ chứng minh không có vòng lặp dài; nếu có vòng lặp, truy vấn quyền có nguy cơ đệ quy vô hạn hoặc lỗi tải ACL.

Trước khi chuyển:

- Xác nhận parent mới tồn tại và thuộc **đúng tenant/phạm vi quản trị** với child.
- Từ parent mới, đi theo chuỗi `getParentAcl()` hoặc truy vấn quan hệ từ dữ liệu tin cậy; nếu gặp child thì từ chối.
- Giới hạn độ sâu, phát hiện `visited ObjectIdentity` và xử lý đồng thời di chuyển cây để không tạo cycle bằng race condition.
- Cần chính sách khi domain object chuyển folder, chuyển organization hoặc xóa folder: ACL parent phải được cập nhật đúng thời điểm và trong transaction.
- Chuyển parent thường có thể thay đổi quyền của **nhiều lớp con/cháu** nếu chúng đang kế thừa; phải kiểm tra phạm vi tác động, không chỉ chính child.

**Không được sao chép ACE từ parent cũ sang child mới** như một phép “đổi parent” mặc định. Sao chép ACE là một chính sách khác (materialize quyền), có thể giữ lại quyền cũ mà tổ chức muốn thu hồi.

## 5. Thao tác 3 — `setEntriesInheriting(boolean)`: bật hoặc tắt kế thừa

`Acl.isEntriesInheriting()` là cờ quyết định ACL con có sử dụng các ACE ở cha để đánh giá quyền hay không. `setParent` chỉ tạo liên kết; **chỉ khi inheritance được bật thì ACE ở cha mới có thể ảnh hưởng** theo chiến lược đánh giá.

```java
MutableAcl child =
    (MutableAcl) mutableAclService.readAclById(childIdentity);

// Giữ nguyên parent nhưng tạm tách quyền kế thừa.
child.setEntriesInheriting(false);
mutableAclService.updateAcl(child);

// Sau khi đã thẩm định quyền của parent, có thể bật lại:
child = (MutableAcl) mutableAclService.readAclById(childIdentity);
child.setEntriesInheriting(true);
mutableAclService.updateAcl(child);
```

Snippet này giả định `childIdentity` và `mutableAclService` đã có; các bước ngoài test phải đi qua service quản trị được ủy quyền. Đừng tự bật lại inheritance chỉ vì parent link tồn tại: parent ACL có thể vừa thay đổi quyền và tác động đến nhiều user.

### 5.1. Ma trận parent/inheritance

| Parent ACL có tồn tại? | `entriesInheriting` | ACE cục bộ có khớp? | Hệ quả thường gặp với strategy mặc định |
| --- | --- | --- | --- |
| Không | `false` | Có | Quyết định theo ACE tại con |
| Không | `true` | Không | Không có parent để kế thừa; thường no-match |
| Có | `false` | Không | Không xét ACE cha |
| Có | `true` | Không | Có thể xét parent, rồi tiếp tục các ancestor nếu chúng bật inheritance |
| Có | `true` | Có grant | Grant cục bộ có thể quyết định mà không cần fallback |
| Có | `true` | Có explicit deny | Deny cục bộ có thể quyết định trước ACE grant ở cha |
| Có | `false` | Có ACE cục bộ | ACE cục bộ vẫn có hiệu lực; tắt kế thừa **không xóa** local ACE |

Tính khớp và thứ tự ACE/SID/permission được quyết định bởi `PermissionGrantingStrategy`. Với strategy khác hoặc danh sách SID/permission khác, không được cứng nhắc khẳng định “deny luôn thắng” hay “grant luôn thắng” trong mọi trường hợp.

### 5.2. Grant, explicit deny và không có quy tắc

Giả sử ACL của Folder A cấp Alice READ. Với ACL con bật inheritance:

- **Con không có ACE READ cho Alice:** có thể fallback lên parent, Alice được phép READ.
- **Con có ACE READ/deny cho Alice:** chiến lược mặc định có thể trả `false`; parent grant không tự ghi đè quyết định ở con.
- **Con tắt inheritance và không có ACE READ:** không còn đường fallback lên parent; `Acl.isGranted` có thể ném `NotFoundException`, **khác** một ACE deny tường minh.
- **Con có local READ/grant cho Alice:** Alice vẫn có thể đọc ngay cả khi inheritance bị tắt.

Trong policy ứng dụng, `NotFoundException` khi không có rule phù hợp thường phải được xử lý theo nguyên tắc **fail closed**. Không chuyển exception thiếu quyết định thành allow.

### 5.3. Nhiều tầng

```text
Organization (READ cho ROLE_EMPLOYEE)
  |
  | Folder-A: entriesInheriting=true
  v
Folder-A (READ cho Alice)
  |
  | Document: entriesInheriting=true
  v
Document
```

Nếu Folder-A tắt inheritance, quyền organization không được truyền qua Folder-A theo logic kế thừa thông thường, nhưng **local ACE của Folder-A vẫn có thể được kế thừa xuống Document** nếu Document bật kế thừa. Nếu Document tắt inheritance, nó không sử dụng ACE của bất kỳ parent nào. Đây là lý do cờ nằm **trên từng ACL con**, không phải một cờ chung của cả cây.

## 6. Mẫu service quản trị: sửa ba trạng thái và lưu

Thao tác quản trị nên được tập trung tại một Spring service, không viết thẳng trong controller:

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AclAdministrationService {

    private final MutableAclService aclService;

    public AclAdministrationService(MutableAclService aclService) {
        this.aclService = aclService;
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_MANAGE')")
    public void changeOwner(long documentId, String newUsername) {
        ObjectIdentity id =
            new ObjectIdentityImpl("demo.Document", documentId);

        MutableAcl acl = (MutableAcl) aclService.readAclById(id);

        // Trước khi áp dụng production: kiểm tra tenant, actor,
        // tồn tại/trạng thái tài liệu và tính hợp lệ của newUsername.
        acl.setOwner(new PrincipalSid(newUsername));
        aclService.updateAcl(acl);
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_MANAGE')")
    public void switchParent(long documentId, long folderId) {
        ObjectIdentity childId =
            new ObjectIdentityImpl("demo.Document", documentId);
        ObjectIdentity parentId =
            new ObjectIdentityImpl("demo.Folder", folderId);

        MutableAcl child = (MutableAcl) aclService.readAclById(childId);
        Acl parent = aclService.readAclById(parentId);

        // Production: bắt buộc kiểm tra cùng tenant, không tạo
        // chu trình parent, quyền thao tác ở cả hai resource.
        child.setParent(parent);
        aclService.updateAcl(child);
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_MANAGE')")
    public void changeInheritance(long documentId, boolean inherit) {
        ObjectIdentity id =
            new ObjectIdentityImpl("demo.Document", documentId);

        MutableAcl acl = (MutableAcl) aclService.readAclById(id);
        acl.setEntriesInheriting(inherit);
        aclService.updateAcl(acl);
    }
}
```

**Đây là code cấu trúc Spring service có thể biên dịch khi project có các dependency/import tương ứng**, nhưng các kiểm tra domain/tenant/cycle được chú thích là **bắt buộc cần bổ sung trước production**. Authority `ACL_MANAGE` chỉ là guard ở entry point; `AclAuthorizationStrategy` bên trong ACL vẫn có thể yêu cầu quyền sửa cụ thể của actor. Khi dùng `AclAuthorizationStrategyImpl` với `ROLE_ACL_ADMIN`, cần định nghĩa rõ hai policy đó tương thích với nhau.

Không gọi `this.changeOwner()` từ method khác rồi giả định advice `@PreAuthorize`/`@Transactional` luôn chạy: trong Spring proxy mode, self-invocation bỏ qua interceptor của method được gọi nội bộ. Service quản trị nên được gọi qua Spring-managed bean/proxy.

### 6.1. Dùng `updateAcl` thay cho `createAcl`

`createAcl(ObjectIdentity)` dành cho ACL **chưa tồn tại**, còn đổi owner/parent/inheritance phải thao tác trên **ACL đã lưu**. Trình tự đúng:

```text
readAclById(identity)
     |
     v
MutableAcl.setOwner / setParent / setEntriesInheriting
     |
     v
MutableAclService.updateAcl(acl)
     |
     v
đọc lại và kiểm tra trạng thái + quyền thực tế
```

`MutableAclService.updateAcl` không chỉ cập nhật object trong RAM mà còn ghi dữ liệu. Với `JdbcMutableAclService`, implementation có thể **xóa và tạo lại các hàng ACE** khi cập nhật một ACL, kể cả bạn chỉ đổi owner/parent/inheritance; vì vậy không được giả định ACE row ID luôn giữ nguyên hoặc gọi update liên tục vô hại về chi phí. Cần transaction để đảm bảo tính nhất quán.

### 6.2. Không nhầm đối tượng cha

`setParent` nhận một `Acl`, không nhận `ObjectIdentity`. Nếu bạn chỉ có ID folder, cần:

```java
ObjectIdentity parentIdentity =
    new ObjectIdentityImpl("demo.Folder", folderId);
Acl parentAcl = aclService.readAclById(parentIdentity);
childAcl.setParent(parentAcl);
```

Đây là snippet có biến sẵn, không phải chương trình tự chạy. Nếu parent chưa có ACL, phải áp dụng chính sách tạo ACL hoặc từ chối; không tự tạo parent ACL rỗng mà quên thiết kế quyền kế thừa.

## 7. Quyền sửa ACL, transaction và cache

### 7.1. Quyền thay owner khác quyền đọc object

`AclAuthorizationStrategyImpl` có thể được cấu hình qua một authority dùng chung hoặc ba authority theo loại thay đổi:

```java
@Bean
AclAuthorizationStrategy aclAuthorizationStrategy() {
    return new AclAuthorizationStrategyImpl(
        new SimpleGrantedAuthority("ROLE_ACL_OWNER_ADMIN"),
        new SimpleGrantedAuthority("ROLE_ACL_AUDIT_ADMIN"),
        new SimpleGrantedAuthority("ROLE_ACL_RULE_ADMIN")
    );
}
```

Đây là **fragment bean**, không phải class cấu hình độc lập. Thứ tự trong constructor ba tham số: quyền thay **ownership**, quyền sửa **auditing**, quyền thay **các dữ liệu ACE/ACL khác**. Với một authority duy nhất, implementation sử dụng authority đó cho cả ba nhóm. Hãy luôn kết hợp kiểm tra actor có được thay ACL của **tài nguyên cụ thể** hay không, không chỉ có system role.

### 7.2. Transaction và đồng thời

Đổi owner, chuyển parent, bật/tắt kế thừa thường liên quan một hoặc nhiều hàng `acl_object_identity` và có thể phát sinh insert `acl_sid` mới. `@Transactional` cần bao trùm nghiệp vụ tương ứng. Nếu đồng thời có transaction cập nhật bảng domain (ví dụ chuyển tài liệu sang folder khác), phải bảo đảm tính nhất quán giữa `Document.folder_id` và `acl_object_identity.parent_object`.

Các ca race condition cần chú ý:

- Hai quản trị viên cùng chuyển child sang hai parent khác nhau; bản cập nhật cuối có thể ghi đè thay đổi đầu.
- Admin A kiểm tra parent không tạo cycle; admin B sửa cây trước khi A commit, khiến chu trình hình thành.
- Một luồng xóa ACL parent trong khi luồng khác gắn child vào parent đó.
- Admin thu hồi quyền, nhưng request đã dùng ACL từ cache/transaction cũ.

Cân nhắc **optimistic locking/version**, khóa domain row/ACL relation thích hợp, transaction isolation và policy retry có điều kiện. ACL schema mặc định không tự cung cấp mọi cơ chế concurrency control cần cho ứng dụng.

### 7.3. Cache khi đổi parent/owner/inheritance

`AclCache` (ví dụ `SpringCacheBasedAclCache`) giảm truy vấn SQL, nhưng quyết định quyền mới chỉ đáng tin khi dữ liệu cache được đồng bộ. `JdbcMutableAclService.updateAcl` trong implementation chuẩn có thao tác invalidation và đọc lại ACL; cần kiểm thử ảnh hưởng đến descendant ACL khi đổi parent, sửa ACE ở ancestor hoặc bật kế thừa.

**Không coi cache cục bộ một JVM là bảo đảm giữa nhiều node.** Với `ConcurrentMapCache`, node A cập nhật owner/parent còn node B có thể giữ bản ACL cũ. Thiết kế distributed invalidation/TTL hoặc cách đọc nhất quán theo mức độ rủi ro của sản phẩm.

Khi thay parent của một cây, cần xét cả cache con, cháu và quan hệ cũ. Việc cập nhật ACL đúng trong DB chưa chứng minh authorization ở mọi node đã nhìn thấy thay đổi.

## 8. Project Java 17+ kiểm thử owner, parent và inheritance bằng JDBC

Ví dụ dùng database HSQLDB in-memory và các class thật từ `spring-security-acl`. Nó tạo ba ACL:

- `Folder-A`: cấp `READ` cho `PrincipalSid("alice")`.
- `Folder-B`: cấp `READ` cho `PrincipalSid("bob")`.
- `Document`: không có local ACE, parent ban đầu là Folder-A, `entriesInheriting=true`.

Sau đó từng test đổi **owner**, **parent**, **inheritance**, thêm ACE cục bộ hoặc thay ACE ở parent và kiểm tra trạng thái từ JDBC service đã đọc lại. Điều này chứng minh ba thao tác không chỉ đổi thuộc tính ở RAM.

### 8.1. Cấu trúc và dependencies

```text
acl-hierarchy-demo/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/AclHierarchyTest.java
    └── resources/schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'acl-hierarchy-demo'
```

`build.gradle` — Java 17 và Spring Security 6.5.x từ Boot BOM:

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
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-acl'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.hsqldb:hsqldb'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Bộ test dùng HSQLDB vì JDBC ACL default ID-query `call identity()` được thiết kế cho HSQLDB. Nếu dùng PostgreSQL production, dùng schema PostgreSQL và cấu hình `JdbcMutableAclService.setClassIdentityQuery`/`setSidIdentityQuery` phù hợp. Không copy DDL của HSQLDB sang PostgreSQL.

### 8.2. Tệp schema.sql

Tạo tệp `src/test/resources/schema.sql` theo schema HSQLDB trong tài liệu chính thức:

```sql
CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT acl_sid_unique UNIQUE(sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT acl_class_unique UNIQUE(class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT acl_object_unique
        UNIQUE(object_id_class, object_id_identity),
    CONSTRAINT acl_parent_fk
        FOREIGN KEY(parent_object) REFERENCES acl_object_identity(id),
    CONSTRAINT acl_class_fk
        FOREIGN KEY(object_id_class) REFERENCES acl_class(id),
    CONSTRAINT acl_owner_fk
        FOREIGN KEY(owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT acl_entry_unique
        UNIQUE(acl_object_identity, ace_order),
    CONSTRAINT acl_entry_object_fk
        FOREIGN KEY(acl_object_identity) REFERENCES acl_object_identity(id),
    CONSTRAINT acl_entry_sid_fk
        FOREIGN KEY(sid) REFERENCES acl_sid(id)
);
```

Đây là **schema dành cho HSQLDB** với bốn bảng ACL chuẩn và foreign key/unique constraint tương ứng. Trong demo, Spring Boot test khởi tạo nó bằng `spring.sql.init.mode=always`. Production dùng migration kiểm soát, không tự động xóa/tạo lại schema sau deploy.

### 8.3. Java integration test

Tạo `src/test/java/demo/AclHierarchyTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = AclHierarchyTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:schema.sql"
    }
)
@WithMockUser(username = "acl-admin", roles = "ACL_ADMIN")
public class AclHierarchyTest {

    private static final AtomicLong IDS = new AtomicLong(20000L);

    @Autowired JdbcMutableAclService service;
    @Autowired DataSource dataSource;
    @Autowired AclCache cache;
    @Autowired DocumentService documents;

    private ObjectIdentity folderA;
    private ObjectIdentity folderB;
    private ObjectIdentity document;
    private Long docId;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class Config {
        @Bean
        static MethodSecurityExpressionHandler expressionHandler(
                AclPermissionEvaluator evaluator) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(evaluator);
            return handler;
        }

        @Bean
        static AclPermissionEvaluator evaluator(
                JdbcMutableAclService service) {
            return new AclPermissionEvaluator(service);
        }

        @Bean
        JdbcMutableAclService aclService(
                DataSource source, LookupStrategy lookup,
                AclCache cache) {
            return new JdbcMutableAclService(source, lookup, cache);
        }

        @Bean
        LookupStrategy lookupStrategy(
                DataSource source, AclCache cache,
                AclAuthorizationStrategy adminStrategy,
                PermissionGrantingStrategy grantStrategy) {
            return new BasicLookupStrategy(
                source, cache, adminStrategy, grantStrategy);
        }

        @Bean
        AclCache aclCache(
                PermissionGrantingStrategy grantStrategy,
                AclAuthorizationStrategy adminStrategy) {
            Cache springCache = new ConcurrentMapCache("aclCache");
            return new SpringCacheBasedAclCache(
                springCache, grantStrategy, adminStrategy);
        }

        @Bean
        AclAuthorizationStrategy adminStrategy() {
            return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
        }

        @Bean
        PermissionGrantingStrategy grantStrategy() {
            return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
        }

        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    public static class DocumentService {
        @PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
        public String read(@P("id") Long id) {
            return "DOC:" + id;
        }
    }

    @BeforeEach
    void prepareHierarchy() {
        long base = IDS.getAndAdd(10L);
        folderA = new ObjectIdentityImpl("demo.Folder", base);
        folderB = new ObjectIdentityImpl("demo.Folder", base + 1L);
        docId = base + 2L;
        document = new ObjectIdentityImpl("demo.Document", docId);

        MutableAcl a = service.createAcl(folderA);
        a.insertAce(0, BasePermission.READ, new PrincipalSid("alice"), true);
        service.updateAcl(a);

        MutableAcl b = service.createAcl(folderB);
        b.insertAce(0, BasePermission.READ, new PrincipalSid("bob"), true);
        service.updateAcl(b);

        MutableAcl child = service.createAcl(document);
        child.setParent(service.readAclById(folderA));
        child.setEntriesInheriting(true);
        service.updateAcl(child);
    }

    @AfterEach
    void cleanup() {
        // Xóa con trước cha để không vi phạm foreign key parent_object.
        service.deleteAcl(document, false);
        service.deleteAcl(folderA, false);
        service.deleteAcl(folderB, false);
    }

    private MutableAcl currentChild() {
        return (MutableAcl) service.readAclById(document);
    }

    private boolean canRead(ObjectIdentity oid, String username) {
        Acl acl = service.readAclById(oid);
        Sid sid = new PrincipalSid(username);
        try {
            return acl.isGranted(
                List.of(BasePermission.READ), List.of(sid), true);
        } catch (NotFoundException missingRule) {
            // Test diễn giải no-match thành deny; không phải explicit ACE deny.
            return false;
        }
    }

    @Test
    void parentAndInheritancePersist() {
        Acl child = service.readAclById(document);
        assertThat(child.getParentAcl()).isNotNull();
        assertThat(child.getParentAcl().getObjectIdentity())
            .isEqualTo(folderA);
        assertThat(child.isEntriesInheriting()).isTrue();
        assertThat(child.getEntries()).isEmpty();
    }

    @Test
    @WithMockUser(username = "alice", roles = "ACL_ADMIN")
    void aliceReadsThroughInheritedFolderGrant() {
        assertThat(canRead(document, "alice")).isTrue();
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
        assertThat(documents.read(docId)).isEqualTo("DOC:" + docId);
    }

    @Test
    @WithMockUser(username = "bob", roles = "ACL_ADMIN")
    void bobHasNoReadGrantFromFolderA() {
        assertThat(canRead(document, "bob")).isFalse();
        assertThatThrownBy(() -> documents.read(docId))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void changingAclOwnerDoesNotAutomaticallyGrantRead() {
        MutableAcl child = currentChild();
        Sid bob = new PrincipalSid("bob");

        child.setOwner(bob);
        service.updateAcl(child);

        assertThat(currentChild().getOwner()).isEqualTo(bob);
        assertThat(canRead(document, "bob")).isFalse();
        assertThat(canRead(document, "alice")).isTrue();
    }

    @Test
    void movingToFolderBChangesInheritedReadGrant() {
        assertThat(canRead(document, "alice")).isTrue();
        assertThat(canRead(document, "bob")).isFalse();

        MutableAcl child = currentChild();
        child.setParent(service.readAclById(folderB));
        service.updateAcl(child);

        assertThat(currentChild().getParentAcl().getObjectIdentity())
            .isEqualTo(folderB);
        assertThat(canRead(document, "alice")).isFalse();
        assertThat(canRead(document, "bob")).isTrue();
    }

    @Test
    void disablingInheritanceKeepsParentLinkButStopsGrant() {
        MutableAcl child = currentChild();
        child.setEntriesInheriting(false);
        service.updateAcl(child);

        Acl fresh = service.readAclById(document);
        assertThat(fresh.getParentAcl().getObjectIdentity())
            .isEqualTo(folderA);
        assertThat(fresh.isEntriesInheriting()).isFalse();
        assertThat(canRead(document, "alice")).isFalse();
    }

    @Test
    void enablingInheritanceAgainRestoresParentGrant() {
        MutableAcl child = currentChild();
        child.setEntriesInheriting(false);
        service.updateAcl(child);
        assertThat(canRead(document, "alice")).isFalse();

        child = currentChild();
        child.setEntriesInheriting(true);
        service.updateAcl(child);

        assertThat(currentChild().isEntriesInheriting()).isTrue();
        assertThat(canRead(document, "alice")).isTrue();
    }

    @Test
    void detachingParentStopsInheritedGrant() {
        MutableAcl child = currentChild();
        child.setParent(null);
        service.updateAcl(child);

        assertThat(currentChild().getParentAcl()).isNull();
        assertThat(canRead(document, "alice")).isFalse();
    }

    @Test
    void localGrantStillWorksWithoutParentInheritance() {
        MutableAcl child = currentChild();
        child.setEntriesInheriting(false);
        child.insertAce(0, BasePermission.READ,
            new PrincipalSid("bob"), true);
        service.updateAcl(child);

        assertThat(canRead(document, "bob")).isTrue();
        assertThat(canRead(document, "alice")).isFalse();
        assertThat(currentChild().getEntries()).hasSize(1);
    }

    @Test
    void localDenyTakesPriorityOverInheritedGrantForSameSid() {
        MutableAcl child = currentChild();
        child.insertAce(0, BasePermission.READ,
            new PrincipalSid("alice"), false);
        service.updateAcl(child);

        assertThat(canRead(document, "alice")).isFalse();
        assertThat(currentChild().getEntries()).hasSize(1);
        assertThat(currentChild().getEntries().get(0).isGranting()).isFalse();
    }

    @Test
    void changingParentAceIsVisibleForPreviouslyReadChild() {
        assertThat(canRead(document, "alice")).isTrue();

        MutableAcl parent = (MutableAcl) service.readAclById(folderA);
        parent.deleteAce(0);
        service.updateAcl(parent);

        assertThat(canRead(document, "alice")).isFalse();
    }

    @Test
    void databaseColumnsReflectOwnerParentAndInheritance() {
        MutableAcl child = currentChild();
        child.setOwner(new PrincipalSid("bob"));
        child.setParent(service.readAclById(folderB));
        child.setEntriesInheriting(false);
        service.updateAcl(child);

        var jdbc = new JdbcTemplate(dataSource);
        var row = jdbc.queryForMap(
            "select o.entries_inheriting as inherit_flag, " +
            "s.sid as owner_name, p.object_id_identity as parent_object " +
            "from acl_object_identity o " +
            "join acl_sid s on s.id = o.owner_sid " +
            "left join acl_object_identity p on p.id = o.parent_object " +
            "join acl_class c on c.id = o.object_id_class " +
            "where c.class = ? and o.object_id_identity = ?",
            "demo.Document", docId.toString()
        );

        assertThat(row.get("OWNER_NAME")).isEqualTo("bob");
        assertThat(row.get("INHERIT_FLAG")).isEqualTo(false);
        assertThat(String.valueOf(row.get("PARENT_OBJECT")))
            .isEqualTo(String.valueOf(
                ((ObjectIdentity) folderB).getIdentifier()));
    }
}
```

### 8.4. Giải thích thiết kế và kết quả kỳ vọng

`@BeforeEach` tạo mới hai ACL Folder và một ACL Document. Các phương thức mutator được gọi trên ACL tồn tại rồi **lưu qua `updateAcl`**. Mỗi test có identity mới; `@AfterEach` xóa Document trước hai Folder để tránh vướng foreign key self-reference.

**Authentication test:** mặc định dùng `@WithMockUser(username="acl-admin", roles="ACL_ADMIN")` để có quyền quản trị ACL fixture. Test Alice/Bob ghi đè username nhưng vẫn mang `ROLE_ACL_ADMIN` để `@BeforeEach` có thể tạo cấu trúc. Role quản trị ACL **không phải ACE READ**, nên kết quả authorization vẫn xuất phát từ grant của Alice/Bob ở đúng Folder ACL.

**`canRead` helper:** dùng `Acl.isGranted(...)` và chủ động biến `NotFoundException` (không có rule phù hợp) thành `false` ở cấp **test**, không nhầm no-match với một ACE deny tường minh. Ứng dụng cần chính sách fail closed và error handling phù hợp; không nuốt những lỗi database không liên quan.

**Test HTTP/service:** `DocumentService.read` có `@PreAuthorize("hasPermission(#id,'demo.Document','READ')")`, được gọi qua Spring proxy. Test với Alice phải chạy, test với Bob phải nhận `AccessDeniedException`.

**Test JDBC:** các test thay owner, parent, inheritance đều đọc lại qua service. Test cuối đọc cột `acl_object_identity` và `acl_sid` thật trong HSQLDB, chứng minh persistence chứ không chỉ kiểm tra state của Java object.

| Test | Hiện tượng xác minh |
| --- | --- |
| `parentAndInheritancePersist` | Link cha A và cờ inheritance=true đã được lưu |
| `aliceReadsThroughInheritedFolderGrant` | Alice kế thừa READ qua parent A |
| `bobHasNoReadGrantFromFolderA` | Bob không có rule phù hợp, service bị chặn |
| `changingAclOwnerDoesNotAutomaticallyGrantRead` | Owner thành Bob, nhưng Bob không tự được READ |
| `movingToFolderBChangesInheritedReadGrant` | Alice mất READ kế thừa từ A, Bob nhận READ từ B |
| `disablingInheritanceKeepsParentLinkButStopsGrant` | Có parent nhưng inheritance=false thì không lấy ACE cha |
| `enablingInheritanceAgainRestoresParentGrant` | Bật lại inheritance khiến grant ở parent có hiệu lực |
| `detachingParentStopsInheritedGrant` | `setParent(null)` cắt đường kế thừa |
| `localGrantStillWorksWithoutParentInheritance` | Local grant vẫn áp dụng khi tắt inheritance |
| `localDenyTakesPriorityOverInheritedGrantForSameSid` | Explicit local deny chặn grant tương ứng ở parent |
| `changingParentAceIsVisibleForPreviouslyReadChild` | Sửa parent ACL ảnh hưởng child đã từng được đọc/cache |
| `databaseColumnsReflectOwnerParentAndInheritance` | Ba cột owner/parent/inheritance được lưu vào SQL |

Chạy:

```bash
gradle test --tests demo.AclHierarchyTest
```

Nếu có Gradle Wrapper: Linux/macOS `./gradlew test --tests demo.AclHierarchyTest`; Windows `gradlew.bat test --tests demo.AclHierarchyTest`.

**Kỳ vọng:** 12 test JUnit đạt và Gradle báo `BUILD SUCCESSFUL` khi project và dependencies được thiết lập đúng. Đây là **kỳ vọng dựa trên thiết kế mẫu**, không phải stdout đã được ghi nhận từ một lượt chạy thực tế. Chi tiết test report: `build/reports/tests/test/index.html`. Nếu test thất bại, kiểm tra version Spring Security ACL, SQL identity/schema, cache invalidation, SID, proxy và query alias trước khi thay assertion.

## 9. Phân biệt ba thao tác qua ma trận tình huống

Ví dụ: Document ban đầu có parent A; A grant Alice READ, B grant Bob READ; Document không có local ACE.

| Thay đổi | Owner của Document | Parent | Inherit | Alice READ | Bob READ |
| --- | --- | --- | --- | --- | --- |
| Trạng thái ban đầu | acl-admin | A | true | Allow | Không có rule phù hợp |
| Đổi owner thành Bob | bob | A | true | **Allow** | **Không tự Allow** |
| Chuyển parent sang B | acl-admin | B | true | Không có rule phù hợp | **Allow** |
| Tắt kế thừa | acl-admin | A | false | Không lấy ACE cha | Không lấy ACE cha |
| Thay parent B nhưng tắt kế thừa | acl-admin | B | false | Không lấy ACE cha | Không lấy ACE cha |
| Ngắt parent | acl-admin | null | true | Không có nguồn kế thừa | Không có nguồn kế thừa |
| Tắt kế thừa và grant READ local cho Bob | acl-admin | A | false | Không lấy ACE cha | **Allow bằng local ACE** |
| Có local deny READ cho Alice, vẫn kế thừa từ A | acl-admin | A | true | **Deny cục bộ** | Không có rule phù hợp |

Bảng phản ánh `DefaultPermissionGrantingStrategy` và dữ liệu ACE giả định. Nếu ACL có nhiều SID/permissions khớp hoặc một strategy tùy chỉnh, kết quả có thể thay đổi theo thứ tự và quy tắc áp dụng; phải có integration tests cho hệ thống thật.

## 10. Những sai lầm đặc biệt nguy hiểm

### 10.1. Tưởng owner mới tự nhận quyền đọc

`acl.setOwner(new PrincipalSid("bob"))` không thêm `BasePermission.READ` cho Bob. Nếu business yêu cầu chuyển quyền đọc/ghi, dùng `insertAce`/`deleteAce` hoặc policy đã định nghĩa, rồi lưu. Ngược lại, owner cũ có thể còn ACE READ sau khi chuyển owner nếu không thu hồi.

### 10.2. Tưởng có parent là tự kế thừa

`setParent(folderAcl)` lưu link, nhưng `entriesInheriting=false` thì quyền ở folder không tự chảy xuống con. Test **cả `getParentAcl()` và `isEntriesInheriting()`**, cùng một principal trước/sau chuyển.

### 10.3. Chỉ thay Java object, quên `updateAcl`

`MutableAcl` là object mutable trong bộ nhớ; sau khi gọi `setOwner`, `setParent` hay `setEntriesInheriting`, phải gọi `MutableAclService.updateAcl(acl)` để persistence đồng bộ. Test bằng một lần **đọc lại** từ service và, khi cần, query SQL.

### 10.4. Nhầm local ACE và inherited ACE

`acl.getEntries()` chỉ trả các ACE **cục bộ**; các ACE từ parent không nhất thiết xuất hiện trong danh sách. Đừng kết luận “child có 0 ACE nên ai cũng bị deny” khi child có parent và inheritance=true. Ngược lại, đừng cố tự flatten ACE của tất cả ancestors để viết policy khi `Acl.isGranted` đã có strategy thực thi quyền.

### 10.5. Di chuyển ACL cha sang tenant khác

Chuyển Document sang Folder B của tenant khác có thể làm lộ dữ liệu qua quyền `READ` kế thừa nếu validation thiếu. Phải kiểm tra tenant của cả child/newParent, actor được phép di chuyển, target hợp lệ, scope được mở rộng/thu hẹp đúng yêu cầu và dữ liệu nghiệp vụ được cập nhật cùng policy.

### 10.6. Bỏ qua vòng lặp và độ sâu cây

Parent graph có vòng lặp có thể dẫn đến quá trình tra ACL lỗi/đệ quy không kết thúc. **Không tạo cycle** rồi hy vọng database foreign key chặn; cần cơ chế validation graph và kiểm soát concurrent moves.

### 10.7. Tin một JVM cache trong hệ thống nhiều node

Một instance có thể thấy owner/parent mới, instance khác vẫn dùng ACL cũ. Hãy có invalidation phát tán, TTL, monitoring và test revoke tại nhiều node. Với quyền nhạy cảm, thời gian tồn tại cache cũ phải tuân theo SLA của chính sách bảo mật.

### 10.8. Tưởng transaction tự đảm bảo tất cả

Một lần cập nhật ACL và bảng domain ở hai DataSource không tự atomic chỉ nhờ một `@Transactional`. Khi có nhiều service/DB, thiết kế transaction/outbox/compensation và hành vi khi một phần thay đổi thành công phải được xác định rõ.

### 10.9. Quên quyền quản trị tách biệt

`@PreAuthorize("hasAuthority('ACL_MANAGE')")` là guard cấp method, không thay thế `AclAuthorizationStrategy` cho mutator của ACL. Người mang `ROLE_ACL_ADMIN` trong ACL infrastructure cũng không tự có quyền di chuyển mọi document qua mọi folder: cần thêm ràng buộc tenant/ownership/resource.

## 11. Quy trình kiểm thử production

Các trường hợp nên đưa vào bộ kiểm thử tích hợp:

1. **Đổi owner:** kiểm tra giá trị `acl_sid` mới, quyền quản trị thay đổi đúng và ACE READ/WRITE không bị vô tình giữ/mất.
2. **Đổi cha:** test chuyển từ parent A sang parent B, cả người mới được grant và người cũ mất quyền khi không có local ACE.
3. **Tắt/bật inheritance:** test link parent vẫn tồn tại nhưng quyền không được kế thừa khi false; bật lại chỉ khi policy đồng ý.
4. **Local deny vs parent grant:** bảo đảm chính sách xung đột được giải thích đúng với strategy thật.
5. **Ancestor update:** cập nhật ACE ở ông/bà và kiểm tra children/grandchildren bị ảnh hưởng chính xác.
6. **Null parent:** khi bỏ parent, quyền kế thừa biến mất và child vẫn dùng local ACE.
7. **Dữ liệu không tồn tại:** `readAclById` cho object thiếu ACL có thể ném `NotFoundException`; service quản trị phải fail closed.
8. **SID chưa nạp:** `UnloadedSidException` có thể xuất hiện khi load ACL chỉ một tập SID mà lại kiểm tra SID khác; không diễn giải thành allow.
9. **Concurrency:** hai request thay parent/owner đồng thời, kiểm soát lost update và cycle.
10. **Transaction:** nếu cập nhật business folderId thất bại, ACL parent phải rollback/compensate theo hợp đồng.
11. **Cache:** kiểm tra quyền sau thay đổi ở node ghi và node khác; bảo đảm không có grant cũ vượt SLA.
12. **Audit:** ghi actor, resource, old/new owner, old/new parent, old/new inheritance, nguyên nhân và kết quả; tránh log token hoặc dữ liệu nhạy cảm.

## 12. Bài tập áp dụng

**Bài tập A — owner không phải domain permission:** Đổi ACL owner Document sang Carol, giữ nguyên các ACE. Dự đoán Carol READ có được cấp không, rồi test với `Acl.isGranted` và `@PreAuthorize`.

**Bài tập B — ba tầng ACL:** Tạo Organization → Folder → Document. Organization grant READ `ROLE_STAFF`; bật/tắt inheritance ở từng lớp rồi xác định điểm nào chặn quyền truyền xuống.

**Bài tập C — chuyển folder:** Thêm parent C grant WRITE cho Alice; di chuyển Document từ A sang C và chứng minh WRITE thay đổi theo inheritance. Thêm local deny WRITE để quan sát chiến lược giải quyết xung đột.

**Bài tập D — revoke cache:** Đọc Document để cache, sửa parent grant thành deny, rồi kiểm tra lại trên cùng instance và instance khác. Viết tiêu chí nghiệm thu cho việc thu hồi quyền.

**Bài tập E — race/cycle:** Hai admin đồng thời di chuyển A dưới B và B dưới A. Đề xuất kiểm tra graph cùng chiến lược khóa/optimistic version để không tạo chu trình.

**Bài tập F — khác loại dữ liệu:** Thử chuyển parent `demo.Document#42` sang `demo.Folder#10` đúng tenant và sang `demo.Folder#10` ở tenant khác. Cần những thông tin/trường database nào để không nhầm `ObjectIdentity`?

## 13. Checklist triển khai

- [ ] Thao tác qua **`MutableAcl` và `MutableAclService.updateAcl`**, không cập nhật SQL trực tiếp bỏ cache.
- [ ] **Owner** được lưu bằng `Sid` không null; thay owner không mặc định cấp hoặc thu hồi domain ACE.
- [ ] **Parent** được tải bằng `AclService.readAclById`; không gắn nhầm `Long` hoặc entity object vào `setParent`.
- [ ] **Inheritance** được kiểm tra độc lập với parent link; có test false/true/null parent và nhiều tầng.
- [ ] Actor được kiểm tra quyền quản trị ACL và quyền trên tài nguyên đúng tenant; không trao ACL management cho mọi user.
- [ ] Parent graph không có cycle và không dẫn cross-tenant vô ý; kiểm tra cạnh tranh cập nhật.
- [ ] Transaction bao trùm thay đổi phù hợp và nhất quán với domain data.
- [ ] Cache được evict/invalidate sau owner/parent/inheritance/ancestor update ở **mọi instance** liên quan.
- [ ] Test grant, deny tường minh, no-match, local vs inherited và `NotFoundException`.
- [ ] Audit các thay đổi owner/parent/inheritance, đặc biệt khi quyền truy cập mở rộng.
- [ ] Hệ quản trị CSDL/schema và ID-query tương thích Spring Security ACL version triển khai.

## 14. Kết luận

Ba API `setOwner`, `setParent` và `setEntriesInheriting` sửa **ba khía cạnh khác nhau** của ACL:

- **`setOwner`**: ai quản trị ACL theo chiến lược đã cấu hình; **không tự chuyển ACE READ/WRITE**.
- **`setParent`**: ACL cha nào được tham chiếu; **không tự bật kế thừa**.
- **`setEntriesInheriting`**: có cho phép tìm quyền qua ACL cha hay không; **không xóa local ACE**.

Dùng `MutableAclService.updateAcl` để lưu và kiểm thử **đường đọc lại qua JDBC**, hiệu lực `Acl.isGranted`/`hasPermission`, cache, transaction và chính sách quản trị. Khi thao tác này thay đổi quyền của cả cây tài nguyên, cần đánh giá tác động lên người dùng và tenant trước khi commit.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Domain Object Security (ACLs): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 — ACL schema (HSQLDB và database dialect): https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security 6.5 API — `MutableAcl`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/MutableAcl.html
- Spring Security 6.5 API — `Acl`, parent và `isEntriesInheriting`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security 6.5 API — `AclImpl`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html
- Spring Security 6.5 API — `AclAuthorizationStrategyImpl`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html
- Spring Security 6.5 API — `JdbcMutableAclService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security 6.5 API — `AclCache`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclCache.html
