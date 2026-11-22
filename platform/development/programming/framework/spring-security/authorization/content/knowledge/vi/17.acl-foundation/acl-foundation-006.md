# Kế thừa ACL từ đối tượng cha và giới hạn quyền lan truyền

> **Chủ đề:** Spring Security – authorization · **Nhóm:** Nền tảng ACL. Bài học tập trung vào **ACL cha–con** trong mô hình bảo mật theo đối tượng: `parentAcl`, cờ `entriesInheriting`, thứ tự ACE được xét, cách cắt luồng kế thừa, giới hạn quyền chỉ được lan theo chính sách và các rủi ro khi tài nguyên thuộc nhiều tenant. Phạm vi API minh họa: Spring Security ACL 6.x/7.x trên Servlet, Spring Framework và Java 17+. Đây là cơ chế ACL của Spring Security, không đồng nhất với phân cấp role hay phân quyền thư mục mặc định của hệ điều hành.

## 1. Bài toán và kết quả học tập

Một ứng dụng lưu cấu trúc:

~~~text
Workspace A
  |
  +-- Folder F (ACL cha)
        |
        +-- Document D1 (ACL con, có kế thừa)
        |
        +-- Document D2 (ACL con, không kế thừa)
        |
        +-- Subfolder S
               |
               +-- Document D3
~~~

Nhóm `ROLE_REVIEWER` được phép **READ** Folder F. Có nên tự động đọc được D1? D2? D3? Nếu Folder F cũng được cấp **WRITE**, có được sửa D1 không? Nếu D1 chứa nội dung nhạy cảm hơn Folder F, có thể **chặn riêng WRITE tại D1** không? Nếu một ngày Folder F bị chuyển sang tenant B, điều gì cần kiểm tra?

Đó là bài toán **quyền lan truyền qua quan hệ ACL cha–con**. Đừng trả lời theo trực giác “thư mục cha có quyền gì thì mọi file con có quyền đó” vì Spring Security có cờ kế thừa và cách đánh giá ACE cụ thể.

Sau bài học, bạn sẽ:

1. Phân biệt **quan hệ cha trong domain** với **liên kết parent ACL** và **kế thừa ACE**.
2. Hiểu `Acl.getParentAcl()`, `Acl.isEntriesInheriting()` và `MutableAcl.setParent(...)`/`setEntriesInheriting(...)`.
3. Dự đoán quyết định cấp quyền khi ACL con có ACE phù hợp, khi chỉ cha có ACE, khi cắt kế thừa và khi không tìm thấy ACE ở đâu.
4. Phân biệt `NotFoundException` với một ACE DENY; không tự coi “không thấy ACE” là GRANT.
5. Cấu hình việc tạo/sửa quan hệ qua `MutableAclService`, `updateAcl` và ACL storage/cache.
6. Thiết kế biên tenant, biên tài liệu nhạy cảm, chính sách chỉ lan READ và xử lý khi reparent/revoke.
7. Kiểm thử inheritance/deny/stop ở Spring ACL và một chương trình Java 17 độc lập; biết ranh giới của mỗi bài kiểm thử.

## 2. Các khái niệm phải tách riêng

| Khái niệm | Vai trò trong Spring Security ACL |
| --- | --- |
| `ObjectIdentity` | Định danh *một đối tượng* được bảo vệ (kiểu + ID), ví dụ Document 501 |
| `Acl` | Chính sách quyền gắn với ObjectIdentity, chứa ACE trực tiếp và tham chiếu cha |
| `AccessControlEntry` (ACE) | Một mục quyền của SID trên đối tượng: permission, grant/deny, thứ tự, audit flags |
| `Sid` | Security identity: principal (`PrincipalSid`) hoặc authority (`GrantedAuthoritySid`) |
| `Permission` | Quyền như `BasePermission.READ`/`WRITE`/`DELETE`/`ADMINISTRATION` |
| `parentAcl` | ACL cha được liên kết để điều hướng/tìm quyền kế thừa |
| `entriesInheriting` | Có cho phép chuyển sang ACL cha khi cần xét quyền hay không |
| `AclService` | Đọc ACL từ nguồn dữ liệu/cache |
| `MutableAclService` | Tạo/cập nhật/xóa ACL, lưu quan hệ cha và ACE |
| `PermissionGrantingStrategy` | Thuật toán đánh giá ACE, ví dụ `DefaultPermissionGrantingStrategy` |
| `AclPermissionEvaluator` | Kết nối `hasPermission(...)` trong method security tới `AclService` |

**Quan trọng:** Một document có `folderId=12` trong bảng nghiệp vụ **không có nghĩa** ACL của document sẽ tự động có parent là ACL của Folder 12. Hai cấu trúc có thể khác nhau. Ứng dụng phải thiết lập đúng `parent_object` và `entries_inheriting` trong dữ liệu ACL, hoặc gọi API để tạo liên kết.

### 2.1. Ba lớp quan hệ

~~~text
Quan hệ dữ liệu:        Document D1.folderId = F.id
                                 |
Quan hệ ACL:            ACL(D1).parentAcl = ACL(F)
                                 |
Cờ kế thừa:            ACL(D1).entriesInheriting = true
~~~

Để D1 có thể nhận ACE từ F theo cơ chế mặc định, không đủ chỉ có quan hệ thứ nhất hoặc thứ hai: tại điểm tra cứu trên ACL con, **phải có parent ACL và inheritance được bật**. Cờ cắt ở một tầng trung gian có thể ngăn tiếp tục lên ông/bà.

### 2.2. Kế thừa ở đây không phải copy ACE

Nếu F cấp `READ` cho Alice, D1 bật kế thừa nhưng không có ACE READ của Alice, Spring có thể **đi lên ACL(F)** để tìm. Nó **không bắt buộc sao chép** một hàng ACE READ vào ACL(D1). `child.getEntries()` là danh sách ACE trực tiếp của child, không liệt kê tất cả ACE kế thừa từ các parent; để **quyết định quyền**, phải dùng `Acl.isGranted(...)` hoặc lớp evaluator phù hợp.

Từ đó có khác biệt lớn: thay đổi ACE trên F có thể ảnh hưởng nhiều con đang kế thừa mà không cần cập nhật từng con. Khi thiết kế hệ thống, đây vừa là lợi ích quản trị, vừa là **phạm vi tác động cần kiểm soát**.

## 3. Dữ liệu JDBC biểu diễn quyền lan truyền ở đâu?

Spring Security ACL có bốn bảng chính:

- `acl_sid`: principal hoặc granted authority mà hệ thống ACL nhận biết.
- `acl_class`: kiểu domain object được bảo vệ.
- `acl_object_identity`: mỗi đối tượng; có `parent_object`, `entries_inheriting` và owner SID.
- `acl_entry`: ACE trực tiếp; gồm `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting` và cờ audit.

Những cột đặc biệt liên quan:

~~~sql
-- Cấu trúc rút gọn để đọc ý nghĩa, KHÔNG phải file migration đủ constraints.
acl_object_identity (
    id,
    object_id_class,
    object_id_identity,
    parent_object,       -- FK tới một hàng ACL cha
    owner_sid,
    entries_inheriting   -- boolean: có tìm quyền ở cha khi cần không
)

acl_entry (
    acl_object_identity,
    ace_order,
    sid,
    mask,
    granting,
    audit_success,
    audit_failure
)
~~~

`parent_object` biểu diễn liên kết cha. `entries_inheriting` biểu diễn quyền được tham khảo ACE của cha khi thuật toán quyết định cần fallback. `ace_order` gắn với thứ tự ACE; không được tự suy luận rằng mọi ACE DENY “luôn thắng” mọi ACE GRANT bất kể thứ tự và SID.

Ví dụ dữ liệu khái niệm:

| ACL object | parent_object | entries_inheriting | ACE trực tiếp |
| --- | --- | --- | --- |
| Folder F | null | false | Alice READ = GRANT; Alice WRITE = GRANT |
| Document D1 | ACL(F) | true | Không có ACE |
| Document D2 | ACL(F) | false | Không có ACE |
| Document D3 | ACL(F) | true | Alice WRITE = DENY |

Với một Alice SID và từng permission được hỏi riêng:
- D1 READ và WRITE có thể được kế thừa từ F.
- D2 READ và WRITE không tìm tiếp vào F, vì `entries_inheriting=false`.
- D3 WRITE bị DENY ở local ACE, không quay lên F lấy GRANT WRITE để ghi đè.

**Đừng chỉnh trực tiếp `parent_object` trong SQL ngoài hệ thống ACL rồi mong cache tự đồng bộ.** Với ứng dụng dùng `AclCache`, thay đổi phải được cập nhật/evict đúng cách; nên dùng `MutableAclService` và kiểm thử với schema của database đang chạy.

## 4. Thuật toán mặc định: tìm ACE ở con trước, rồi mới tới cha

`Acl.isGranted(List<Permission>, List<Sid>, boolean administrativeMode)` là API quyết định quyền. Trong `AclImpl`, lời gọi này ủy quyền cho `PermissionGrantingStrategy`, thường là `DefaultPermissionGrantingStrategy`. Để hiểu đúng inheritance, hãy xem **một permission và một SID trước**.

~~~text
check(childAcl, Alice, READ)
   |
   +-- tìm ACE phù hợp tại childAcl
   |       |
   |       +-- có GRANT => true
   |       |
   |       +-- có DENY  => false
   |
   +-- không có ACE phù hợp tại childAcl
           |
           +-- entriesInheriting = false => không đi cha
           |
           +-- entriesInheriting = true và parentAcl != null
                   |
                   +-- đánh giá parentAcl
                           |
                           +-- parent có ACE phù hợp => grant/deny
                           +-- nếu vẫn không có => có thể đi grandparent
   |
   +-- hết cây mà vẫn không có ACE => NotFoundException
~~~

Chú ý ba kết quả ở cấp `Acl.isGranted` của implementation mặc định: **true**, **false** và **exception khi không có quyết định**. Việc không tìm thấy ACE **không phải** một lời cho phép mặc định. `AclPermissionEvaluator`/policy phía ngoài có thể chuyển kết quả/exception thành denial hoặc hành vi khác theo cấu hình; đừng tự đoán tất cả đều thành 403 hay cùng loại exception.

### 4.1. Bảng tình huống tối thiểu

Ký hiệu `G` = ACE GRANT, `D` = ACE DENY, `—` = không có ACE phù hợp với Alice/READ.

| Local D1 ACE READ | D1 inherits? | ACE READ ở F | `D1.isGranted(READ, Alice, false)` |
| --- | --- | --- | --- |
| — | true | G | **true** qua cha |
| — | true | D | **false** qua cha |
| — | false | G | **NotFoundException** (nếu không có nguồn quyết định khác) |
| — | true | — | **NotFoundException** nếu cả cây không có ACE |
| G | true | D | **true**, local grant được xét ở con |
| D | true | G | **false**, local deny chặn đường này |
| G | false | D | **true**, có local grant nên không cần cha |
| D | false | G | **false**, local deny |
| — | false | — | **NotFoundException** |

Bảng được cố ý giới hạn **một SID, một permission và `DefaultPermissionGrantingStrategy`**. Trong hệ thống thực, một Authentication thường có cả `PrincipalSid` và nhiều `GrantedAuthoritySid`; kết quả có thể phụ thuộc thứ tự quyền/SID và nhiều ACE. Vì thế không lấy bảng một SID làm quy tắc tuyệt đối “deny ở child cho một SID luôn chặn mọi grant ở mọi SID”.

### 4.2. Thứ tự xét Permission và SID quan trọng

Javadoc `DefaultPermissionGrantingStrategy` mô tả việc duyệt **các permission theo thứ tự yêu cầu**, rồi duyệt **các SID theo thứ tự**, tìm ACE đầu tiên phù hợp với cặp permission:SID. Trong trường hợp ACE này GRANT, thuật toán có thể trả true; khi ACE này DENY, nó xử lý theo vòng kiểm tra các permission tiếp theo. Chỉ khi **không có ACE phù hợp nào** ở ACL hiện tại mới thử parent (với cờ inheritance bật). Nếu có nhiều permission hoặc SID, quyết định còn chịu ảnh hưởng của danh sách và cách implementation so sánh mask.

Điều này dẫn tới các nguyên tắc:
- Giữ thứ tự ACE, SID và permission có chủ đích; kiểm thử với tổ hợp principal + authority thực.
- Không mô tả ACL giống firewall đơn giản nơi “DENY bất kỳ đâu trong cây luôn thắng”.
- Không trực tiếp lặp `getEntries()` rồi tự chọn ACE đầu/ cuối nếu có thể dùng `isGranted`.
- Nếu cần **deny bắt buộc cho cả tenant hay trạng thái account bị khóa**, đặt ràng buộc đó ở tầng policy độc lập, ngoài một ACE đơn lẻ có thể bị ảnh hưởng bởi nhiều SID.

### 4.3. Permission mask không phải số bit cho từng document

`BasePermission` có các quyền thường dùng: READ, WRITE, CREATE, DELETE, ADMINISTRATION. Mỗi permission là một bit mask; số lượng document có thể rất lớn mà không phải cấp một bit cho mỗi document. Cùng mask READ của Alice được đánh giá trên ObjectIdentity từng document khác nhau.

Không giả định quyền WRITE tự hàm ý quyền READ hoặc quyền ADMINISTRATION tự kế thừa mọi khả năng nếu policy không thiết kế vậy. Các mask có thể được kết hợp bằng custom `Permission` hoặc cơ chế mask matcher, nhưng cần kiểm thử chính xác ở implementation đang dùng.

## 5. Giới hạn lan quyền: không chỉ một cờ boolean

Cờ `entriesInheriting` quyết định **có thể tìm ở cha hay không khi thiếu ACE phù hợp**. Nó không phải danh sách allow-list “chỉ kế thừa READ, không kế thừa WRITE” cho sẵn. Với default ACL inheritance, nếu child không có ACE phù hợp và bật kế thừa, quyền READ/WRITE/DELETE/... có thể đi lên theo cùng cơ chế.

### 5.1. Cắt toàn bộ tại child nhạy cảm

Để D2 không thừa hưởng F:

~~~java
// Trích đoạn với MutableAcl được lấy qua MutableAclService.
childAcl.setParent(parentAcl);       // vẫn có liên kết điều hướng
childAcl.setEntriesInheriting(false); // không nhận ACE từ cha
mutableAclService.updateAcl(childAcl);
~~~

Hậu quả: D2 chỉ còn những ACE trực tiếp của nó; nếu không có ACE cho một SID/permission thì `isGranted` có thể ném `NotFoundException`, và policy phía ngoài phải xử lý theo hướng an toàn. **Không đồng nghĩa tất cả người dùng đều bị chặn** nếu D2 có ACE local GRANT.

Dùng khi:
- Tài liệu chứa dữ liệu mật hơn thư mục chung.
- Tài nguyên được “đóng băng” quyền để không chạy theo thay đổi nhóm cha.
- Tài nguyên mới được chuyển sang vùng bảo mật khác, cần ACL tách biệt.
- Một nhánh cây cần tuân thủ chính sách retention/compliance khác.

Điểm cần kiểm tra: tắt inheritance **không tự xóa** local ACE đã có. Nó cũng không bảo đảm mọi descendent của D2 đều tắt: nếu D3 inherit D2 thì D3 có thể nhận **local ACE của D2**, nhưng không vượt qua nút D2 để lấy ACE của F khi D2 không tìm tiếp lên F.

### 5.2. Chỉ muốn lan READ nhưng không lan WRITE?

Đây là yêu cầu phổ biến và cần thiết kế cụ thể. Ba lựa chọn:

**Cách A — Tắt inheritance, tạo ACE local cho quyền muốn giữ.**

- Gắn parent link để điều hướng nếu cần, nhưng `setEntriesInheriting(false)` trên tài liệu con.
- Cấp explicit READ cho các SID được phép ở tài liệu con; không cấp WRITE.
- Khi parent ACL thay đổi, cập nhật/sync các ACE local theo quy trình riêng nếu chính sách muốn quyền con thay đổi theo. **Không tự động** vì inheritance đã tắt.

Ưu điểm: ranh giới rõ, dễ audit; nhược điểm: cần quản lý đồng bộ ACE, nhiều bản ghi và độ phức tạp khi group membership thay đổi.

**Cách B — Bật inheritance, thêm ACE local ngăn WRITE phù hợp.**

- D1 kế thừa để tận dụng READ cha.
- Thêm ACE local WRITE = DENY cho đúng SID hoặc nhóm cần chặn.
- Với một SID và một WRITE permission, local DENY chặn lookup parent cho cặp đó.

**Cảnh báo:** đây **không phải cách tổng quát để bảo đảm “mọi người đều bị chặn WRITE”**. Người dùng có thể có nhiều SID và ACE khác; thứ tự xét SID/permission, nhóm quyền khác hoặc custom strategy có thể đưa ra quyết định. Cần ma trận test bao phủ tất cả principal/role có thể áp dụng; nếu rủi ro cao, ưu tiên cắt inheritance hoặc một required policy “child sensitive => deny write” đặt ngoài ACL.

**Cách C — Policy bổ sung bao quanh ACL.**

Ví dụ policy nghiệp vụ yêu cầu:
- Với READ: chấp nhận ACL READ qua cây.
- Với WRITE: ngoài kết quả ACL WRITE, phải có capability `document:write` của tầng service và state/tenant phù hợp.
- Với classified document: deny mutation bất kể parent ACL, trừ một quy trình break-glass được quản trị/audit riêng.

Cách này phù hợp khi một cờ inherited toàn bộ không đủ diễn đạt ranh giới permission theo hành động. Tuy nhiên policy phải được **enforce thật**, không chỉ ở UI/ẩn nút.

### 5.3. Quyền lan theo nhiều tầng

~~~text
Root ACL: Alice READ = G
   |
   v   entriesInheriting = true
Folder ACL: không có ACE Alice READ
   |
   v   entriesInheriting = true
Doc ACL: không có ACE Alice READ
   |
   +--> đọc từ Root => GRANT
~~~

Nếu Folder `entriesInheriting=false` nhưng Folder **không có READ local**, Doc không thể “nhảy qua” Folder lên Root theo cơ chế mặc định. Nếu Folder có READ local GRANT thì Doc vẫn có thể nhận **quyền do Folder tự cấp** khi Doc inherit Folder.

Không có toggle chuẩn “được phép nhìn ông nhưng bỏ qua cha”. Muốn hành vi đó phải thiết kế parent khác hoặc strategy riêng; làm vậy có thể phá tính dễ kiểm toán của cây.

## 6. Một thay đổi ở cha ảnh hưởng bao nhiêu đối tượng?

Khi nhiều con inherit từ F, một thay đổi như:

~~~text
Trước:
ACL(F) -> group REVIEWERS: READ = G
D1: inherits = true
D2: inherits = false
S : inherits = true, D3 inherits S

Sau:
ACL(F) -> bỏ READ của REVIEWERS
~~~

Kết quả kỳ vọng:
- D1 không còn nhận grant READ từ F, trừ khi có ACE local hoặc nguồn grant khác.
- D2 không bị ảnh hưởng **qua inheritance** từ F vì cờ đã tắt; ACE local của D2 vẫn giữ nguyên.
- D3 có thể bị ảnh hưởng nếu S và D3 đều inherit, và không có ACE ở S/D3 ngăn fallback.
- Nếu S đã có READ local GRANT, D3 có thể vẫn GRANT dù F bỏ ACE.

Ngược lại, thêm grant WRITE ở F có thể vô tình mở WRITE xuống các con đang inherit. Vì vậy khi mở rộng quyền trên một “folder chung”, phải kiểm tra **toàn bộ descendants chịu ảnh hưởng**, không chỉ chính folder.

### 6.1. Ma trận impact trước khi thay đổi ACL cha

| Thay đổi | Tác động cần khảo sát |
| --- | --- |
| Cấp thêm READ ở parent | Những child nào inherit và chưa có quyết định local? |
| Cấp WRITE/DELETE ở parent | Có tài liệu con nhạy cảm/không được mutation không? |
| Thu hồi quyền parent | Child nào dựa vào quyền kế thừa và có thể mất quyền? |
| Thêm local GRANT ở child | Có mở quyền rộng hơn parent policy không? |
| Thêm local DENY ở child | Có chặn đúng SID/permission hay còn nhánh authority khác? |
| `entriesInheriting true → false` | Quyền đang chỉ có ở parent có bị mất? |
| `entriesInheriting false → true` | Có quyền mới bất ngờ xuất hiện từ parent? |
| Reparent child sang folder khác | Tenant/scope có đổi và quyền từ parent mới là gì? |
| Xóa parent | Child ACL còn liên kết gì, policy xóa cascade có phù hợp không? |
| Sửa group membership | SID được cấp qua authority có thay đổi theo Authentication mới không? |

## 7. Liên kết ACL cha với MutableAclService

Spring ACL JDBC có `MutableAclService` để thao tác cập nhật, thay vì gọi trực tiếp SQL rồi quên cache. Đoạn dưới là **service method minh họa trong ứng dụng đã cấu hình ACL**, không phải chương trình Spring Boot chạy độc lập. Nó yêu cầu các bean `MutableAclService`, `scopePolicy` và repository nghiệp vụ tồn tại.

~~~java
// Nằm trong @Service quản lý ACL, các dependency được inject.
// Chỉ gọi từ đường quản trị đã được xác thực và phân quyền.
@Transactional
@PreAuthorize("hasAuthority('acl:manage')")
public void reparentDocument(long documentId, long folderId,
                             boolean inheritEntries) {
    // Domain policy phải xác minh: cùng tenant, parent hợp lệ, không cycle,
    // người gọi có quyền sửa ACL của CẢ document và folder.
    scopePolicy.assertAllowedReparent(documentId, folderId);

    ObjectIdentity childId =
            new ObjectIdentityImpl("com.example.domain.Document", documentId);
    ObjectIdentity parentId =
            new ObjectIdentityImpl("com.example.domain.Folder", folderId);

    MutableAcl child = (MutableAcl) mutableAclService.readAclById(childId);
    Acl parent = mutableAclService.readAclById(parentId);

    child.setParent(parent);
    child.setEntriesInheriting(inheritEntries);
    mutableAclService.updateAcl(child);
}
~~~

Các import chính: `org.springframework.security.acls.model.ObjectIdentity`, `Acl`, `MutableAcl`, `org.springframework.security.acls.domain.ObjectIdentityImpl`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.security.access.prepost.PreAuthorize`.

Đây là **trích đoạn**: `scopePolicy` là đối tượng ứng dụng phải tự triển khai, không phải Spring API có sẵn. Cần phân biệt rõ chính sách sửa ACL với chính sách xem tài liệu:
- **Đọc Document** cần quyền READ trên Document.
- **Sửa parent ACL của Document** cần capability quản trị ACL đã được xác minh, nhiều khi phải có quyền với cả cha và con.
- Việc được READ parent **không tự cấp** quyền thay đổi `parentAcl` hoặc `entriesInheriting`.
- Không lấy `folderId` do người dùng gửi rồi cho phép reparent sang ACL tenant khác. Kiểm tra cả quan hệ domain và ACL dưới transaction/locking phù hợp.

### 7.1. Khi tạo ACL con mới

~~~java
// Trích đoạn nghiệp vụ (trong transaction/quy trình cấp ACL hợp lệ).
ObjectIdentity childId =
        new ObjectIdentityImpl("com.example.domain.Document", newDocumentId);
ObjectIdentity parentId =
        new ObjectIdentityImpl("com.example.domain.Folder", folderId);

Acl parent = mutableAclService.readAclById(parentId);
MutableAcl child = mutableAclService.createAcl(childId);
child.setParent(parent);
child.setEntriesInheriting(true);
mutableAclService.updateAcl(child);
~~~

`createAcl` tạo một ACL mới với ObjectIdentity, `updateAcl` lưu thay đổi. Nếu ObjectIdentity đã tồn tại, `createAcl` có thể ném `AlreadyExistsException`; `updateAcl` trên bản ghi không tồn tại có thể báo `NotFoundException`. Không dùng `new AclImpl(...)` rồi mong `updateAcl` tự động tạo hàng DB tương ứng. Với batch tạo nhiều objects, phải kiểm tra tính nhất quán nếu một bước lưu domain thành công còn ACL chưa được tạo; dùng transaction, outbox hoặc workflow bù trừ tùy hạ tầng.

### 7.2. Thay đổi permission của parent

~~~java
// Trích đoạn sau khi đã xác thực quyền quản trị ACL.
MutableAcl folderAcl =
        (MutableAcl) mutableAclService.readAclById(parentId);
folderAcl.insertAce(
        folderAcl.getEntries().size(),
        BasePermission.READ,
        new GrantedAuthoritySid("ROLE_REVIEWER"),
        true
);
mutableAclService.updateAcl(folderAcl);
~~~

`getEntries()` liệt kê local ACE, không phải effective permissions từ cha. Khi thêm ACE, thứ tự `ace_order` có ý nghĩa; thực tế cần kiểm tra ACE trùng và quy ước sắp xếp trước khi insert. Đoạn code trên giả định `getEntries()` cung cấp list hợp lệ trong implementation đang dùng; trong code robust hãy xử lý khả năng danh sách local không có entry theo API/version và không tạo duplicate.

ACL mutation trong `AclImpl` cũng chịu `AclAuthorizationStrategy`. Chỉ có `@PreAuthorize('acl:manage')` **chưa tự động bỏ qua** các yêu cầu owner/permission của strategy này. Cấu hình `AclAuthorizationStrategyImpl` với quyền quản trị phù hợp và **quyền tối thiểu**; không gắn admin authority cho mọi request để tránh lỗi bảo mật.

### 7.3. Khi cắt inheritance không cần xóa parent

~~~java
MutableAcl child =
        (MutableAcl) mutableAclService.readAclById(childId);
child.setEntriesInheriting(false);
mutableAclService.updateAcl(child);
~~~

Không cần gọi `child.setParent(null)` nếu vẫn muốn giữ quan hệ điều hướng ACL. Cờ false là ranh giới ngăn fallback tìm ACE ở cha. Mặt khác, nếu domain thực sự chuyển chủ sở hữu và parent không còn hợp lệ, nên cập nhật hoặc xóa liên kết theo thiết kế, thay vì giữ một parent không còn đúng.

### 7.4. Chu kỳ và reparent không an toàn

Một cây ACL hợp lệ thường **không được có cycle** như A → B → A; nếu có, việc duyệt parent có thể lặp vô hạn hoặc sinh lỗi. Không dựa vào việc bảng có FK parent để ngăn cycle — FK không tự chặn vòng tham chiếu. Domain service phải kiểm tra quan hệ acyclic và phạm vi tenant khi reparent; với concurrency, cần khóa/transaction để hai request không cùng tạo cycle. Đừng chấp nhận parent ObjectIdentity kiểu bất kỳ từ client.

## 8. Cấu hình Spring ACL với JDBC và method security

Trong dự án Spring Boot Servlet đã có DataSource, bảng ACL và dependency `spring-security-acl`, cơ chế phổ biến gồm `JdbcMutableAclService`, `BasicLookupStrategy`, `SpringCacheBasedAclCache`, `AclPermissionEvaluator` và `DefaultMethodSecurityExpressionHandler`. Mẫu cấu hình dưới đây được viết theo Spring Security 6.x, dựa trên các bean chuẩn; cần điều chỉnh datasource/schema/transaction và security rules cho ứng dụng thật.

Tạo `src/main/java/demo/acl/AclSecurityConfig.java`:

~~~java
package demo.acl;

import javax.sql.DataSource;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclSecurityConfig {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    JdbcMutableAclService aclService(DataSource dataSource,
                                     LookupStrategy lookup,
                                     AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(DataSource dataSource,
                                  AclCache cache,
                                  AclAuthorizationStrategy authorizationStrategy,
                                  PermissionGrantingStrategy permissionStrategy) {
        return new BasicLookupStrategy(
                dataSource, cache, authorizationStrategy, permissionStrategy);
    }

    @Bean
    AclCache aclCache(PermissionGrantingStrategy permissionStrategy,
                      AclAuthorizationStrategy authorizationStrategy) {
        Cache cache = new ConcurrentMapCache("aclCache");
        return new SpringCacheBasedAclCache(
                cache, permissionStrategy, authorizationStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());
    }
}
~~~

**Lưu ý triển khai:** Config này chỉ lắp các bean ACL vào một ứng dụng **đã có** Spring Boot Security và DataSource. Nó **chưa** tạo bốn bảng ACL, chưa định nghĩa `SecurityFilterChain`, chưa cấp role thực tế, chưa định nghĩa entity/repository hay lớp kiểm tra tenant; vì thế **không phải ứng dụng độc lập hoàn chỉnh**. Đọc schema chính thức cho DB thực tế (H2/PostgreSQL/MySQL có DDL/identity semantics khác nhau). Với Spring Security 7.x, kiểm tra thay đổi dependency và API cho phiên bản runtime đang dùng.

Khối Gradle dependencies tối thiểu về mặt thư viện trong một dự án **đã bật Spring Boot plugin và dependency management**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Bổ sung JDBC driver và cấu hình DataSource theo môi trường. `spring-security-acl` là module riêng; không cho rằng chỉ cài `spring-boot-starter-security` là đã có ACL persistence.

### 8.1. Bảo vệ service đọc bằng hasPermission

Một Document service có thể dùng:

~~~java
// Trích đoạn Spring-managed service, không phải class đầy đủ.
@PreAuthorize("hasPermission(#p0, 'com.example.domain.Document', 'READ')")
public DocumentView read(long documentId) {
    return repository.readView(documentId);
}
~~~

`'com.example.domain.Document'` phải khớp convention `ObjectIdentity`/`acl_class`. `'READ'` phải được `PermissionFactory`/evaluator diễn giải nhất quán thành `BasePermission.READ`; nếu sử dụng custom permission, cần cấu hình chuyển đổi phù hợp. Không cố tình hard-code `'Document'` ở một nơi và tên lớp đầy đủ ở nơi khác rồi chờ Spring tự tìm.

Một lời gọi `hasPermission` không xác minh mọi điều kiện nghiệp vụ: vẫn cần account active, tenant scope, data masking, transaction và business validation ở lớp phù hợp. ACL inheritance chỉ là **một chiều của authorization**.

### 8.2. Tránh lỗi cache khi quyền cha đổi

Thực tế, lookup có thể lấy ACL và parent từ cache. Khi cập nhật parent ACE hoặc `entriesInheriting`:
- Sử dụng `MutableAclService.updateAcl` và chiến lược cache invalidation phù hợp với version/framework.
- Nếu có nhiều instance ứng dụng với cache cục bộ, bảo đảm invalidation/TTL hoặc cache phân tán nhất quán; một lần cập nhật DB ở instance A không tự xóa mọi cache trong B.
- Cẩn thận kết quả kiểm tra quyền lưu lâu ở tầng ứng dụng; nếu cache decision riêng, phải có key theo principal, tenant, object, permission và policy version.
- Với quyền nhạy cảm, cần biết consistency window: grant mới và revoke cũ có hiệu lực sau bao lâu.
- Kiểm thử parent revocation qua nhiều instance hoặc làm rõ giới hạn của kiến trúc.

Không dựa vào “sau updateAcl chắc chắn mọi worker/process đã thấy revoke ngay” nếu không có cơ chế phân phối invalidation.

## 9. Test trực tiếp Spring ACL: parent, local deny, stop và NotFound

Đây là unit test **dùng chính `AclImpl`/`DefaultPermissionGrantingStrategy` của Spring ACL**, nhưng tạo object in-memory, không kết nối JDBC. Test khác với toàn bộ integration test có DB/cache/filter chain. Đặt trong dự án đã có `spring-security-acl`, JUnit Jupiter (qua `spring-boot-starter-test`).

Tạo `src/test/java/demo/acl/AclInheritanceTest.java`:

~~~java
package demo.acl;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.Sid;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AclInheritanceTest {
    private static final Sid ALICE = new PrincipalSid("alice");

    private static AclImpl acl(long id, Acl parent, boolean inherits) {
        // Test-only: cho phép mutation in-memory.
        // Production KHÔNG dùng authorization strategy no-op này.
        AclAuthorizationStrategy testOnly = (a, changeType) -> {};
        return new AclImpl(
                new ObjectIdentityImpl("demo.acl.Document", id),
                id,
                testOnly,
                new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger()),
                parent,
                null,                   // Không giới hạn subset SID trong test.
                inherits,
                new PrincipalSid("acl-admin"));
    }

    private static boolean permitted(Acl acl, Sid sid,
                                     org.springframework.security.acls.model.Permission p) {
        return acl.isGranted(List.of(p), List.of(sid), false);
    }

    @Test
    void inheritsParentWhenChildHasNoMatchingAce() {
        AclImpl parent = acl(100, null, false);
        parent.insertAce(0, BasePermission.READ, ALICE, true);
        parent.insertAce(1, BasePermission.WRITE, ALICE, true);

        AclImpl child = acl(200, parent, true);

        assertSame(parent, child.getParentAcl());
        assertTrue(child.isEntriesInheriting());
        assertTrue(permitted(child, ALICE, BasePermission.READ));
        assertTrue(permitted(child, ALICE, BasePermission.WRITE));
    }

    @Test
    void localDenyPreventsFallbackForThatPermissionAndSid() {
        AclImpl parent = acl(100, null, false);
        parent.insertAce(0, BasePermission.READ, ALICE, true);
        parent.insertAce(1, BasePermission.WRITE, ALICE, true);

        AclImpl child = acl(201, parent, true);
        child.insertAce(0, BasePermission.WRITE, ALICE, false);

        assertTrue(permitted(child, ALICE, BasePermission.READ));
        assertFalse(permitted(child, ALICE, BasePermission.WRITE));
    }

    @Test
    void canRetainParentLinkButTurnOffInheritance() {
        AclImpl parent = acl(100, null, false);
        parent.insertAce(0, BasePermission.READ, ALICE, true);

        AclImpl child = acl(202, parent, true);
        child.setEntriesInheriting(false);

        assertSame(parent, child.getParentAcl());
        assertFalse(child.isEntriesInheriting());
        assertThrows(NotFoundException.class,
                () -> permitted(child, ALICE, BasePermission.READ));

        child.insertAce(0, BasePermission.READ, ALICE, true);
        assertTrue(permitted(child, ALICE, BasePermission.READ));
    }

    @Test
    void inheritanceStopsAtIntermediateAcl() {
        AclImpl root = acl(100, null, false);
        root.insertAce(0, BasePermission.READ, ALICE, true);
        AclImpl folder = acl(110, root, false);
        AclImpl document = acl(120, folder, true);

        assertThrows(NotFoundException.class,
                () -> permitted(document, ALICE, BasePermission.READ));

        folder.insertAce(0, BasePermission.READ, ALICE, true);
        assertTrue(permitted(document, ALICE, BasePermission.READ));
    }
}
~~~

Về điểm học thuật: `NotFoundException` xảy ra vì **không có ACE tương ứng** trong đường lookup mà ta đã cho phép, chứ không phải vì có một ACE DENY. Test này chứng minh cờ inheritance và logic lookup trong `AclImpl` ở mức in-memory; chưa chứng minh JDBC lưu `parent_object`, cache evict hoặc `AclPermissionEvaluator` trong Spring method-security proxy. Những hành vi đó cần integration test riêng.

### 9.1. Test integration với DB/schema ACL

Trong dự án thật, thêm test transactional với `JdbcMutableAclService` và database thử nghiệm:

1. Tạo Folder F ACL và cấp READ cho Alice bằng `insertAce`; lưu bằng `updateAcl`.
2. Tạo Document D ACL, set parent F, bật inheritance và lưu.
3. Đọc lại D qua `AclService.readAclById(...)` với danh sách SID Alice; `isGranted(READ)` phải true.
4. Tắt inheritance của D, `updateAcl`, evict/reload như cấu hình; không còn grant từ F.
5. Bật lại inheritance, tạo local DENY READ cho Alice; test false.
6. Sửa parent và test lại cả người đọc đúng và sai tenant; test persistence/reload qua cache.
7. Thu hồi ACE READ ở F và chứng minh D kế thừa thấy thay đổi theo consistency contract.
8. Kiểm tra reparent sai tenant/cycle không được phép tại service quản trị.

Phải test dữ liệu sau **reload qua ACL service** chứ không chỉ test cùng Java object đang nằm trong memory. Cũng nên chạy bộ test với nhiều worker/instance khi kiến trúc dùng cache phân tán.

## 10. Java 17 độc lập: mô phỏng đường kế thừa có ngắt ranh giới

Đây là chương trình thuần JDK, không cần Spring dependency. Nó mô phỏng đơn giản **một user SID và một permission mỗi lần**, tìm ACE local trước, rồi đi lên parent nếu `inherit=true`. Không mô phỏng bitmask/đa SID, permission ordering, `NotFoundException` của Spring hay ACL database. Mục đích là hiểu **luồng** chứ không thay bằng Spring Security trong production.

Lưu thành `AclBoundaryDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AclBoundaryDemo {
    enum Permission { READ, WRITE }
    record Ace(String sid, Permission permission, boolean grant) {}

    static final class Node {
        final String name;
        final Node parent;
        final List<Ace> entries = new ArrayList<>();
        boolean inherits;

        Node(String name, Node parent, boolean inherits) {
            this.name = name;
            this.parent = parent;
            this.inherits = inherits;
        }

        void add(String sid, Permission permission, boolean grant) {
            entries.add(new Ace(sid, permission, grant));
        }

        boolean allows(String sid, Permission permission) {
            for (Ace ace : entries) {
                if (ace.sid().equals(sid)
                        && ace.permission() == permission) {
                    return ace.grant();
                }
            }
            if (inherits && parent != null) {
                return parent.allows(sid, permission);
            }
            // Demo fail closed; Spring ACL có thể ném NotFoundException.
            return false;
        }
    }

    public static void main(String[] args) {
        Node folder = new Node("folder", null, false);
        folder.add("alice", Permission.READ, true);
        folder.add("alice", Permission.WRITE, true);

        Node document = new Node("document", folder, true);
        System.out.println("inherited-read=" +
                document.allows("alice", Permission.READ));
        System.out.println("inherited-write=" +
                document.allows("alice", Permission.WRITE));

        document.add("alice", Permission.WRITE, false);
        System.out.println("local-deny-write=" +
                document.allows("alice", Permission.WRITE));

        document.inherits = false;
        System.out.println("stop-read=" +
                document.allows("alice", Permission.READ));

        document.add("alice", Permission.READ, true);
        System.out.println("local-read=" +
                document.allows("alice", Permission.READ));

        Node child = new Node("grandchild", document, true);
        System.out.println("grandchild-read=" +
                child.allows("alice", Permission.READ));
        System.out.println("grandchild-write=" +
                child.allows("alice", Permission.WRITE));

        folder.add("bob", Permission.READ, true);
        System.out.println("bob-after-parent-change=" +
                document.allows("bob", Permission.READ));
    }
}
~~~

Biên dịch với JDK 17 trở lên:

~~~bash
javac --release 17 AclBoundaryDemo.java
java AclBoundaryDemo
~~~

**stdout chính xác theo chương trình:**

~~~text
inherited-read=true
inherited-write=true
local-deny-write=false
stop-read=false
local-read=true
grandchild-read=true
grandchild-write=false
bob-after-parent-change=false
~~~

Phân tích:
- Khi document inherit, không có local READ/WRITE nên nhận cả READ và WRITE từ folder.
- Local WRITE DENY phủ quyết WRITE của Alice trên document trong demo một SID/permission.
- Tắt inherit làm READ từ folder biến mất, mặc dù parent link còn tồn tại.
- Local READ GRANT phục hồi quyền đọc riêng.
- Grandchild kế thừa local ACE của document, nhưng không vượt qua document lên folder để lấy grant mới.
- Sau khi folder thêm READ cho Bob, document vẫn deny Bob vì ranh giới inheritance đã bị cắt.

**Ranh giới demo:** Không xem `allows(...) == false` khi hết cây là bản sao `Acl.isGranted`. Spring ACL có thể ném `NotFoundException` khi không có ACE; demo cố ý đổi thành fail-closed boolean để dễ chạy độc lập.

## 11. Reparent: thay cha làm thay đổi quyền hiệu lực

Hãy tưởng tượng Document D đang inherit từ Folder F-A, sau đó người dùng gửi yêu cầu “move D sang F-B”.

Nếu chỉ cập nhật `document.folderId=F-B.id` mà **không** cập nhật `ACL(D).parentAcl`, quyền có thể vẫn kế thừa từ F-A. Đây là nguồn lỗi bảo mật *vì domain hiển thị ở F-B nhưng ACL thực tế vẫn do F-A cấp quyền*. Ngược lại, nếu chỉ reparent ACL mà chưa đổi domain, quyền có thể thay đổi trước khi UI/DB phản ánh đúng.

### 11.1. Quy tắc an toàn khi move

1. Xác thực actor có quyền move D và quyền đặt D vào F-B.
2. Kiểm tra tenant/organization của D và F-B; không chấp nhận cross-tenant parent nếu chính sách cấm.
3. Kiểm tra cấu trúc không tạo vòng ACL/domain.
4. Tính/kiểm tra quyền hiệu lực sau khi move, đặc biệt WRITE/DELETE/ADMINISTRATION kế thừa.
5. Trong transaction phù hợp, cập nhật domain parent và ACL parent/inheritance; xử lý rollback/bù trừ nếu hai nguồn lưu trữ khác transaction.
6. Evict/invalidate cache ACL và quyết định authorization liên quan theo hợp đồng nhất quán.
7. Audit ai move, thời điểm, old/new parent, cờ inheritance và lý do.
8. Test user có quyền ở cha cũ **không còn** quyền vô lý sau move, và user thuộc cha mới chỉ được quyền đúng.
9. Với storage tài liệu/file ngoài DB, kiểm tra object storage policy riêng; ACL Spring không tự cấu hình S3 bucket ACL.

### 11.2. Parent link không được dùng như cơ chế vượt tenant

Spring ACL tập trung quyết định ACE/SID; nó **không tự hiểu tenant domain** chỉ vì ObjectIdentity có ID và type. Nếu cho phép parent từ tenant A được nối tới child tenant B, ACE của A có thể lan sang B khi inheritance bật. Một row-level policy hoặc repository tenant filter và quy tắc xác minh quan hệ phải chặn cấu hình đó. Không dựa vào việc ID khác tenant là UUID khó đoán.

## 12. Khác nhau giữa quyền kế thừa và role hierarchy

**ACL inheritance:** permission trên đối tượng cụ thể có thể được tìm ở ACL parent khi thiếu ACE phù hợp ở con. Nó được điều khiển bằng `parentAcl` và `entriesInheriting`.

**Role hierarchy:** một authority có thể bao hàm authority khác (ví dụ `ROLE_ADMIN > ROLE_EDITOR`) nếu ứng dụng cấu hình `RoleHierarchy`. Đó là quan hệ giữa **các quyền của actor**, không phải quan hệ parent–child giữa các ObjectIdentity.

~~~text
Role hierarchy:        ROLE_ADMIN -> ROLE_EDITOR
                                   (actor có authority nào?)

ACL inheritance:       Folder ACL -> Document ACL
                                   (đối tượng nhận ACE từ đâu?)
~~~

Cả hai có thể cùng ảnh hưởng một quyết định, nhưng không thay thế nhau. Không suy ra “Admin thấy folder thì mọi document đều mở” khi child có local DENY, inheritance tắt hoặc tenant rule khác. Ngược lại, cấp role cao hơn không tự ghi `parent_object` hay `entries_inheriting`.

## 13. Những lỗi thường gặp và cách sửa

### Lỗi 1 — Cứ có parent là auto-inherit

Sai. `getParentAcl() != null` không đủ. Cần `isEntriesInheriting()==true` ở child tại điểm lookup. Test cả parent link tồn tại nhưng inheritance tắt.

### Lỗi 2 — Tắt inheritance nghĩa là mất sạch local quyền

Sai. `setEntriesInheriting(false)` chỉ ngắt việc tra ACE ở parent. Local ACE vẫn có thể GRANT/DENY bình thường. Nếu muốn thu hồi local quyền, phải xử lý ACE riêng.

### Lỗi 3 — Parent READ được phép thì child WRITE không bao giờ được

Không có quy tắc đó. Nếu parent cấp WRITE cho SID phù hợp và child bật inheritance mà không có local ACE phù hợp, WRITE có thể cũng lan xuống. Thiết kế ranh giới permission bằng local ACL hoặc policy bắt buộc.

### Lỗi 4 — Local DENY cho một role sẽ chặn mọi quyền tương đương

Không chắc với nhiều SID/permission. `DefaultPermissionGrantingStrategy` xét danh sách permission và SID theo thứ tự. Test principal có cả PrincipalSid lẫn nhiều GrantedAuthoritySid, và các ACE trái dấu; không suy diễn deny-always-wins toàn cục.

### Lỗi 5 — Không tìm thấy ACE nghĩa là trả true

Sai. Khi không có quyết định, `Acl.isGranted` implementation chuẩn có thể ném `NotFoundException`. Policy nên fail closed; không bắt exception rồi GRANT để “giữ tương thích”.

### Lỗi 6 — getEntries() là tập quyền hiệu lực

Sai. `getEntries()` của child chỉ liệt kê local ACE. Nếu cần quyết định đã tính inheritance, dùng `isGranted(...)` hoặc `AclPermissionEvaluator`. Khi cần hiển thị UI quyền hiệu lực, phải tính và giải thích nguồn từng quyền một cách riêng.

### Lỗi 7 — Tạo ACL cha bằng SQL FK là đủ

Sai nếu thiếu record ACL, tenant policy, inheritance flag và cập nhật cache. Dùng `MutableAclService` và transaction; test reload từ JDBC.

### Lỗi 8 — Cập nhật domain parent mà không cập nhật ACL parent

Có thể để tài liệu đã move tiếp tục hưởng quyền của folder cũ. Thiết kế reparent nghiệp vụ và ACL làm một workflow có transaction/compensation và audit.

### Lỗi 9 — Cắt quyền ở folder nhưng grandchild vẫn chắc chắn không có quyền

Chỉ đúng với ACE nguồn upstream bị cắt. Nếu folder/child có local ACE tương ứng, grandchild có thể kế thừa chúng. Kiểm thử từng node trong chuỗi và từng SID/permission.

### Lỗi 10 — Xóa parent không cần xét child

`MutableAclService.deleteAcl(objectIdentity, deleteChildren)` có tham số quyết định có xóa descendants ACL theo API hay không, và có thể từ chối khi child còn tồn tại. Không tùy tiện cascade xóa ACL của cả subtree khi chỉ định xóa folder domain. Cần policy archive/reparent/migrate riêng.

### Lỗi 11 — Lạm dụng quyền ACL admin để sửa quyền từ web

Người có READ trên một document không đồng nghĩa được phép `setParent` hay `insertAce`. Mutation cần ACL administrative authorization, method security và audit riêng. Đừng dùng admin Authentication tĩnh cho mọi request để tránh lỗi quyền.

### Lỗi 12 — Tin rằng cache tự lan revoke tức thì

Một ACL parent có thể đang nằm trong cache nhiều node. Khi sửa/revoke, cần thiết kế invalidation và kiểm chứng readback sau reload. Với thay đổi quyền nhạy cảm, ghi rõ consistency SLA và cách xử lý stale cache.

### Lỗi 13 — Nhầm ACL inheritance với copy permission ở database

Kế thừa không nhất thiết sinh local ACE mới; thay đổi grant cha có thể đổi quyết định ở con đang inherit. Nếu bạn tạo ACE con để “chụp quyền”, đó là **vật thể chính sách khác** cần quản lý suốt vòng đời.

### Lỗi 14 — Không bảo vệ truy vấn danh sách

Chỉ dùng `hasPermission(id, type, READ)` trước một endpoint GET-by-id không tự lọc các record trong `findAll()` hoặc bảo vệ export/report. Phải đưa tenant/ACL predicate vào truy vấn/batch kiểm tra để tránh N+1 và lộ metadata danh sách. Đặc biệt `@PostFilter` trên dữ liệu lớn có thể làm pagination sai.

### Lỗi 15 — Chỉ test một user, một mask trong production

Bảng một SID giúp học cơ chế nhưng không đủ. Bổ sung người có nhiều roles, deny/grant trùng, permission list nhiều phần tử, missing SID, domain move và revocation với cache. Chạy các test negative để chứng minh fail closed.

## 14. Checklist triển khai trước khi phát hành

| Nhóm | Test/chứng minh bắt buộc |
| --- | --- |
| Topology | ObjectIdentity đúng type và ID; parent ACL khớp cây domain |
| Inheritance | Child inherit true nhận parent GRANT khi thiếu local ACE |
| Cut | Child inherit false không đi parent; local ACE vẫn hoạt động |
| Override | Local DENY, local GRANT, parent đối lập, đơn và đa SID |
| Missing | Không ACE ở đâu; `NotFoundException` được xử lý fail closed |
| Multi-level | Grandparent → folder → child; cắt ở intermediate |
| Security boundary | Tenant/organization, classified document, sensitive WRITE |
| Reparent | Không cycle, không cross-tenant, consistency domain và ACL |
| Mutation rights | Only authorized ACL admins/owners; audit request |
| Persistence | Update→reload qua `AclService` vẫn giữ parent/inherit/ACE |
| Cache | Evict/invalidation sau update, revoke giữa các instances |
| Method security | `AclPermissionEvaluator` được đăng ký và proxy thật chạy |
| Data access | Query scope không bỏ qua ACL khi list/export/stream |
| Concurrency | Reparent + permission update cùng lúc, transaction/locking |
| Monitoring | Quyền bị từ chối và lỗi hạ tầng được log đủ nhưng không lộ PII |

### Bài tập 1: Tài liệu riêng trong thư mục chung

Folder F cho `ROLE_EDITOR` READ và WRITE. Document D thuộc Folder F và cần cho editors **READ nhưng không WRITE**. Bạn có thể chọn thiết kế gì?

**Đáp án:** Không chỉ bật inheritance rồi kỳ vọng WRITE biến mất. Có thể tắt inheritance trên D và cấp explicit READ phù hợp; hoặc bật inheritance, cấu hình local WRITE DENY và test đầy đủ mọi SID; với dữ liệu nhạy cảm, tốt hơn đặt required business policy cấm WRITE trên D. Lựa chọn phải nhất quán với chính sách quản lý quyền khi parent thay đổi.

### Bài tập 2: Vì sao không có ACE không có nghĩa DENY ACE?

D2 không có ACE READ, parent có READ GRANT nhưng D2 `entriesInheriting=false`. `isGranted(READ, Alice, false)` sẽ trả false hay exception?

**Đáp án:** Với `DefaultPermissionGrantingStrategy` và không có bất kỳ ACE phù hợp nào, kết quả có thể là `NotFoundException`; đó không phải một ACE DENY. Tầng policy nên diễn đạt denial an toàn theo contract, không chuyển thiếu quyết định thành GRANT.

### Bài tập 3: Chặn giữa cây

Root cho Alice READ, Folder S kế thừa false và không có READ local, Document D kế thừa true từ S. Alice có xem được D nhờ Root không?

**Đáp án:** Không theo đường inheritance mặc định. D fallback tới S, nhưng S không fallback tới Root. Nếu S có READ local GRANT, D lại có thể nhận nó.

### Bài tập 4: Chuyển tài liệu tenant A sang tenant B

Dữ liệu nghiệp vụ đã move Document D sang Folder B, nhưng ACL(D).parentAcl vẫn trỏ Folder A và `entriesInheriting=true`. Nguy cơ gì?

**Đáp án:** Người thuộc tenant A có thể tiếp tục được hưởng grant từ Folder A khi đọc D, hoặc tenant B không nhìn thấy D đúng kỳ vọng. Cần đồng bộ domain parent và ACL parent, kiểm tra quyền actor và cấm cross-tenant liên kết bất hợp lệ.

### Bài tập 5: Parent ACL bị thu hồi READ

Parent F xóa ACE READ của Alice. Child D có local READ GRANT cho Alice và vẫn inherit F. D có bị chặn READ không?

**Đáp án:** Không nhất thiết. Local READ GRANT trên D đủ quyết định true cho cặp SID/permission này; sửa parent không ghi đè local ACE. Phải audit nguồn permission của các child khi cần thu hồi triệt để.

## 15. Tóm tắt

Trong Spring Security ACL, **kế thừa là fallback có điều kiện**, không phải copy quyền tự động:

- `getParentAcl()` tạo đường dẫn sang cha; `isEntriesInheriting()` quyết định có được đi đường đó khi thiếu ACE phù hợp.
- Khi ACL con có một quyết định phù hợp, kết quả ở con được xét trước; không tự quay lên cha để “tìm grant tốt hơn”.
- Với `DefaultPermissionGrantingStrategy`, khi không có ACE phù hợp sau toàn bộ đường lookup, `isGranted` có thể ném `NotFoundException`. Không nhầm absence với grant.
- `entriesInheriting=false` cắt luồng quyền từ cha nhưng giữ local ACE và có thể giữ parent link.
- Để giới hạn *chỉ một số permission* được lan xuống, cần xây policy/ACE local hoặc tách ranh giới; một cờ boolean không làm per-permission allow-list.
- Khi tạo/move/revoke trong subtree, phải kiểm tra tenant, admin rights, transaction, ACL cache và các descendants bị ảnh hưởng.

**Công thức tư duy:** *Một quyết định quyền trên child = tìm local ACE phù hợp trước; nếu không tìm thấy và child bật inheritance thì tìm parent; nếu không có quyết định thì xử lý fail closed theo policy.*

## Tài liệu tham khảo chính thức

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): mô hình ACL, bảng dữ liệu, `AclService`, `AclPermissionEvaluator` và cấu hình JDBC.
- [Spring Security – Security Database Schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): `acl_object_identity.parent_object`, `entries_inheriting` và `acl_entry`.
- [Acl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): `getParentAcl`, `isEntriesInheriting`, `isGranted`.
- [MutableAcl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAcl.html): `setParent`, `setEntriesInheriting`, `insertAce`.
- [DefaultPermissionGrantingStrategy Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): thứ tự duyệt Permission/SID, fallback lên parent và `NotFoundException`.
- [AclImpl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/AclImpl.html): thực thi quyền/parent, constructors và metadata.
- [MutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html): `createAcl`, `updateAcl`, `deleteAcl`.
