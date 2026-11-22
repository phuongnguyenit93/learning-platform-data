# PrincipalSid, GrantedAuthoritySid và phạm vi cấp quyền

> **Chủ đề:** Spring Security – authorization → **Nền tảng ACL**. Bài này phân biệt hai dạng Security Identity (SID) của Spring Security ACL, làm rõ **ai được nhận quyền** và **quyền đó áp dụng trên đối tượng nào**, cách chuyển `Authentication` thành tập SID, và những giới hạn quan trọng của ACE, kế thừa ACL, tenant và vòng đời quyền. Ví dụ chính sử dụng Java 17+ và module `spring-security-acl`; phần tích hợp JDBC/Method Security được phân biệt rõ với chương trình chạy độc lập.

## 1. Vì sao phải có SID khi đã có username và role?

Giả sử một ứng dụng quản lý tài liệu có ba người dùng:

- **alice**: có `ROLE_REVIEWER`.
- **bob**: cũng có `ROLE_REVIEWER`.
- **carol**: chỉ có `ROLE_VIEWER`.

Hệ thống muốn diễn đạt đồng thời hai chính sách:

1. Chỉ **alice** được đọc tài liệu `Document#101`.
2. Bất kỳ người nào **hiện có** authority `ROLE_REVIEWER` đều được đọc `Document#202`.

Một ACL entry có thể chỉ định người nhận quyền bằng **danh tính người dùng** hoặc bằng **danh tính của một authority**. Spring Security ACL dùng giao diện `Sid` (Security Identity) để biểu diễn hai kiểu này:

~~~text
Document#101
  └── READ → PrincipalSid("alice")

Document#202
  └── READ → GrantedAuthoritySid("ROLE_REVIEWER")
                         │
             +-----------+-----------+
             │                       │
      Authentication alice    Authentication bob
       ROLE_REVIEWER           ROLE_REVIEWER
~~~

Trong ví dụ, bob có cùng vai trò với alice nhưng **không** được cấp quyền đối với `Document#101` chỉ vì cùng vai trò; còn cả alice và bob đều nằm trong phạm vi recipient của ACE gắn với `Document#202`. Carol không thuộc recipient `ROLE_REVIEWER`.

**SID không phải session ID**, cũng không phải permission. SID trả lời “**ai** được nhận một ACE?”, `Permission` trả lời “**được làm gì**?”, còn `ObjectIdentity` trả lời “**trên đối tượng cụ thể nào**?”.

## 2. Một quyết định ACL có bốn chiều

Đọc một ACL như tập các quy tắc cấp/từ chối quyền:

~~~text
         ObjectIdentity
              |
              v
            ACL
              |
      +-------+-------+
      |               |
  ACE #0            ACE #1
      |               |
      +-- Sid          +-- Sid
      +-- Permission   +-- Permission
      +-- Grant/Deny   +-- Grant/Deny
~~~

Ví dụ minh họa:

| ObjectIdentity | SID nhận quyền | Permission | Granting? | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `Document#101` | `PrincipalSid("alice")` | `READ` | `true` | Cấp quyền đọc chính tài liệu 101 cho alice |
| `Document#202` | `GrantedAuthoritySid("ROLE_REVIEWER")` | `READ` | `true` | Cấp quyền đọc tài liệu 202 cho người có authority ROLE_REVIEWER |
| `Document#202` | `PrincipalSid("bob")` | `WRITE` | `false` | Một quy tắc **từ chối WRITE**, không đồng nghĩa với từ chối READ |
| `Document#303` | `GrantedAuthoritySid("ROLE_EDITOR")` | `WRITE` | `true` | Chỉ ai có authority ROLE_EDITOR mới là recipient của ACE ghi tài liệu 303 |

Đây là **dữ liệu quy tắc minh họa**, không phải kết quả tính từ một bảng SQL đã dựng. Khi có ACE chồng lấn giữa nhiều SID hoặc nhiều permission, không được tự tính `(có ít nhất một grant) -> allow` mà bỏ qua deny, thứ tự xét và kế thừa. Spring ACL dùng `Acl.isGranted(...)` cùng `PermissionGrantingStrategy` để ra quyết định thật.

### Các khái niệm lõi

| Kiểu / giao diện | Vai trò |
| --- | --- |
| `Sid` | Abstraction cho danh tính nhận quyền |
| `PrincipalSid` | SID của **một principal**, thường từ `Authentication.getName()` |
| `GrantedAuthoritySid` | SID của **một authority** trong `Authentication.getAuthorities()` |
| `Permission` / `BasePermission` | Quyền READ, WRITE, CREATE, DELETE, ADMINISTRATION; biểu diễn bằng bit mask |
| `ObjectIdentity` / `ObjectIdentityImpl` | Khóa gồm **loại đối tượng và ID** |
| `AccessControlEntry` (ACE) | Một quy tắc gồm ACL, SID, permission, grant/deny và audit |
| `Acl` | Tập ACE gắn với **một** ObjectIdentity; có thể có parent ACL |
| `AclService` | Đọc ACL của object từ nguồn lưu |
| `MutableAclService` | Tạo/cập nhật/xóa ACL |
| `SidRetrievalStrategy` | Tạo các SID mà `Authentication` hiện có thể đại diện |
| `PermissionGrantingStrategy` | Chiến lược xét một danh sách permission và SID với ACL |

Một quyền có thể được kiểm tra bằng nhiều SID của cùng người đăng nhập. Ví dụ alice có cả `PrincipalSid("alice")` và `GrantedAuthoritySid("ROLE_REVIEWER")`. Điều đó **không** biến SID principal thành SID authority: đó là hai recipient khác nhau và có cách quản trị khác nhau.

## 3. `PrincipalSid`: cấp quyền cho đúng một principal

Spring Security định nghĩa:

~~~java
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Sid;

// Hai cách tạo cùng SID cho principal có tên "alice":
Sid byName = new PrincipalSid("alice");
Sid fromAuthentication = new PrincipalSid(authentication);
~~~

Ở đoạn trên, biến `authentication` giả định đã là một `Authentication` hợp lệ có `getName()` trả `"alice"`; vì vậy đây là ví dụ cú pháp, chưa phải file biên dịch độc lập.

Các constructor quan trọng:

- `new PrincipalSid(String principal)`: tạo SID từ một chuỗi định danh.
- `new PrincipalSid(Authentication authentication)`: lấy danh tính từ thông tin authentication; implementation mặc định dựa trên cách Spring biểu diễn tên principal.
- `getPrincipal()`: lấy chuỗi định danh của SID.
- `equals/hashCode`: so sánh kiểu và chuỗi SID, không so sánh reference của đối tượng Java.

### Phạm vi của `PrincipalSid`

Nếu ACE là:

~~~text
ObjectIdentity = Document#101
Sid = PrincipalSid("alice")
Permission = READ
Granting = true
~~~

thì recipient là **principal "alice"**, nhưng ACE chỉ thuộc ACL của `Document#101`. Nó không tự cho alice đọc mọi tài liệu, cũng không tự cho mọi người có `ROLE_REVIEWER` đọc tài liệu 101.

`PrincipalSid` phù hợp với các tình huống như:

- Chia sẻ một tài liệu cụ thể cho một người.
- Cấp quyền đọc một hồ sơ cho người chịu trách nhiệm.
- Cấp quyền quản lý một đối tượng cho một tài khoản dịch vụ được xác định rõ.
- Thu hồi quyền truy cập cá nhân khi người dùng không còn tham gia một dự án.

### Lưu ý cực quan trọng về định danh

`PrincipalSid` mặc định sử dụng **chuỗi** nhận diện principal. Nếu tài khoản đổi username, đổi email hoặc hệ thống có hai tenant cùng username, những SID giống nhau có thể gây mất quyền hoặc mở quyền nhầm.

Ví dụ rủi ro:

~~~text
Tenant A có user: alice
Tenant B có user: alice

Hai Authentication đều có getName() = "alice".
Nếu dùng PrincipalSid("alice") mà không có phân biệt tenant:
  -> hai người có thể khớp cùng một SID.
~~~

Với hệ thống nhiều tenant, nên thiết kế danh tính **ổn định và độc nhất toàn hệ thống** (ví dụ `tenantA:user-17` trong quy ước xác thực) hoặc triển khai cơ chế SID/persistence hỗ trợ tenant một cách nhất quán. Chỉ viết `new PrincipalSid("alice")` không thêm ranh giới tenant; mặc định schema ACL cũng không tự buộc tenant vào giá trị SID.

Nên tránh dùng email dễ đổi làm SID bền vững khi chưa có chiến lược migration. Nếu username bị tái sử dụng sau khi xóa tài khoản, một người mới có thể vô tình nhận các ACE còn sót của người cũ nếu hệ thống không dọn quyền.

## 4. `GrantedAuthoritySid`: cấp quyền cho người đang giữ một authority

Spring Security định nghĩa:

~~~java
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.acls.model.Sid;

// Hai cách biểu diễn cùng authority trong demo:
Sid byString = new GrantedAuthoritySid("ROLE_REVIEWER");
Sid byAuthority = new GrantedAuthoritySid(
        new SimpleGrantedAuthority("ROLE_REVIEWER"));
~~~

Constructor và accessor chính:

- `new GrantedAuthoritySid(String grantedAuthority)`.
- `new GrantedAuthoritySid(GrantedAuthority grantedAuthority)`.
- `getGrantedAuthority()`: chuỗi authority được lưu trong SID.

ACE:

~~~text
ObjectIdentity = Document#202
Sid = GrantedAuthoritySid("ROLE_REVIEWER")
Permission = READ
Granting = true
~~~

mang nghĩa **mọi người có authority `ROLE_REVIEWER` trong `Authentication` khi kiểm tra quyền** đều có thể là recipient cho quyền READ trên `Document#202`. Khi một người được thêm/bớt authority đó ở hệ thống xác thực, phạm vi người có khả năng khớp ACE thay đổi mà không nhất thiết phải viết lại từng ACL entry.

### Đây là phạm vi theo authority, không mặc nhiên là toàn cục

Nếu chỉ `Document#202` có ACE cho `GrantedAuthoritySid("ROLE_REVIEWER")`, role reviewer **không** tự nhận READ trên `Document#101` hay `Document#999`. Nó chỉ có hiệu lực ở những object ACL có entry phù hợp, hoặc ở những ACL con **được phép kế thừa** entry đó.

Điều này khác với:

~~~java
@PreAuthorize("hasRole('REVIEWER')")
~~~

Biểu thức trên kiểm tra role tại **điểm chặn method**; nó không tự gắn một ACE vào từng tài liệu. Trong khi ACL theo authority còn phải xét ObjectIdentity, permission, ACE và cơ chế grant/deny.

### `ROLE_REVIEWER` khác `REVIEWER`

`GrantedAuthoritySid("ROLE_REVIEWER")` và `GrantedAuthoritySid("REVIEWER")` là **hai SID khác nhau**. Spring Security `hasRole('REVIEWER')` thường đối chiếu authority `ROLE_REVIEWER` với role prefix mặc định; nhưng constructor `GrantedAuthoritySid(String)` không tự thêm `ROLE_`.

Nếu người dùng có:

~~~text
GrantedAuthority.getAuthority() = "ROLE_REVIEWER"
~~~

thì entry dùng `GrantedAuthoritySid("REVIEWER")` sẽ không tự khớp. Không đổi cách đặt tên authority trên ACL khi chưa migration toàn bộ dữ liệu và kiểm tra các cơ chế role hierarchy.

### Authority có thể đại diện nhóm, chức năng hoặc quyền

`GrantedAuthoritySid` không chỉ dành cho tên bắt đầu bằng `ROLE_`. Một hệ thống có thể dùng:

~~~text
ROLE_REVIEWER
PROJECT_42_EDITOR
DOC_SHARED_READ
TENANT_7_AUDITOR
~~~

Đây là các ví dụ **quy ước chuỗi**, không phải kiểu SID riêng của Spring. Muốn chúng có ý nghĩa bảo mật, hệ thống xác thực phải cấp authority dựa trên dữ liệu đáng tin cậy, và ACL phải có ACE với tên chính xác. Không tin một header `X-Role` hoặc chuỗi query do client tự truyền làm `GrantedAuthority`.

Nếu cơ chế cấp authority bị thổi phồng (người dùng được gán sai role), toàn bộ ACL recipient theo role đó cũng bị ảnh hưởng. Đây là **phạm vi lan truyền** của quyền theo authority và lý do phải kiểm soát vòng đời membership.

## 5. So sánh PrincipalSid và GrantedAuthoritySid

| Câu hỏi | `PrincipalSid` | `GrantedAuthoritySid` |
| --- | --- | --- |
| Đại diện cho ai? | Một principal cụ thể | Mọi principal đang giữ một authority cụ thể |
| Khóa so sánh | Chuỗi principal, thường tên user | Chuỗi authority, ví dụ `ROLE_EDITOR` |
| Khi nào nên dùng? | Chia sẻ ngoại lệ cho một người | Quyền chung của một nhóm/chức năng |
| Người mới gia nhập nhóm tự được áp dụng? | Không, trừ khi cấp ACE riêng | Có nếu authentication của họ nhận đúng authority |
| Người rời nhóm mất quyền? | Không ảnh hưởng ACE cá nhân đã cấp | Thông thường hết khớp SID nhóm khi authority bị thu hồi và authentication được cập nhật |
| Có giới hạn object? | Có, ACE thuộc từng ObjectIdentity/ACL | Có, giống PrincipalSid |
| Nguy cơ chính | Trùng/đổi tên principal, user bị xóa nhưng ACE còn | Cấp nhầm authority, nhóm quá rộng, role hierarchy |
| Có tự cho mọi đối tượng? | Không | Không |
| Có tự gắn tenant? | Không | Không |

### Không nhầm hai SID chỉ vì chuỗi giống nhau

~~~java
Sid a = new PrincipalSid("ROLE_REVIEWER");
Sid b = new GrantedAuthoritySid("ROLE_REVIEWER");

// false: một bên là principal, một bên là authority.
boolean same = a.equals(b);
~~~

Đừng lưu loại SID chỉ bằng một cột chuỗi rồi làm mất cờ `principal`. Cùng `sid = "ROLE_REVIEWER"` trong database có thể đại diện **hai recipient khác nhau** nếu cờ loại SID khác nhau.

## 6. `Authentication` được chuyển thành các SID như thế nào?

Spring Security cung cấp `SidRetrievalStrategy` và implementation `SidRetrievalStrategyImpl`.

~~~java
import java.util.List;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.Sid;

List<Sid> applicableSids =
        new SidRetrievalStrategyImpl().getSids(authentication);
~~~

Với authentication giả định:

~~~text
principal = "alice"
authorities = ["ROLE_REVIEWER", "DOC_EXPORT"]
~~~

danh sách SID thường tương ứng:

~~~text
PrincipalSid("alice")
GrantedAuthoritySid("ROLE_REVIEWER")
GrantedAuthoritySid("DOC_EXPORT")
~~~

Implementation mặc định đưa PrincipalSid vào trước các GrantedAuthoritySid; thứ tự các authority phụ thuộc collection/strategy. Spring ACL sử dụng danh sách recipient này để so với ACE của ObjectIdentity đang kiểm tra.

**Không tự nhét authority không được cấp** vào danh sách SID chỉ để làm phép kiểm tra thành công. Đặc biệt, không tạo `GrantedAuthoritySid("ROLE_ADMIN")` cho mọi user bằng tay tại service. SID phải được lấy từ `Authentication` đã xác thực và quyền đã kiểm soát.

Một `SidRetrievalStrategyImpl(RoleHierarchy)` cũng có thể đưa vào các authority mở rộng theo role hierarchy nếu ứng dụng cấu hình. Cần xác nhận hierarchy áp dụng ở ACL có đúng ý đồ hay không; không mặc định role prefix hay nhóm ở identity provider tự suy ra quan hệ role trong ACL.

### PrincipalSid đứng trước không đồng nghĩa “luôn thắng mọi role”

Trong `DefaultPermissionGrantingStrategy`, **thứ tự các permission, danh sách SID và các ACE** có ảnh hưởng đến cách duyệt. Một ACE grant/deny cụ thể cho principal có thể được xem trước ACE của authority trong một số phép kiểm tra. Nhưng không nên đưa ra công thức cứng như “deny luôn thắng” hoặc “role có grant sẽ vượt mọi deny”; hành vi thực phụ thuộc strategy, permission được hỏi, thứ tự và ACE hiện có.

Khi có chồng lấn, **kiểm thử bằng ACL thật** với strategy được cấu hình, không tự dùng `anyMatch(grant)` để thay thế framework.

## 7. Mức độ phạm vi: SID, object, permission và cây kế thừa

Một nhầm lẫn phổ biến là cho rằng `PrincipalSid("alice")` mang một danh sách quyền độc lập với đối tượng. Trong ACL, quyết định có thêm các trục:

~~~text
              Ai?
              |
       PrincipalSid / GrantedAuthoritySid
              |
              v
           ACE
           /  \
    Permission  ObjectIdentity
       |               |
    READ/WRITE     Document#101
                       |
                 Parent ACL?
                       |
              entriesInheriting?
~~~

### 7.1. ObjectIdentity xác định tài nguyên duy nhất

Một `ObjectIdentityImpl` được tạo từ loại tài nguyên và ID:

~~~java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ObjectIdentity;

ObjectIdentity a = new ObjectIdentityImpl("demo.Document", 101L);
ObjectIdentity b = new ObjectIdentityImpl("demo.Document", 202L);
ObjectIdentity c = new ObjectIdentityImpl("demo.Folder", 101L);
~~~

Ba object identity trên khác nhau: tài liệu 101, tài liệu 202 và thư mục 101. ID `101` đơn thuần không đủ nếu ứng dụng có nhiều loại domain object.

Lời khuyên: dùng identifier ổn định, không tái sử dụng tùy ý, và quy ước tên type nhất quán. Với domain object cụ thể, `new ObjectIdentityImpl(domainObject)` cần truy xuất được ID bằng getter theo convention (thường là `getId()`); không mặc nhiên tương thích với mọi Java record chỉ có accessor `id()`.

### 7.2. Permission là hành động, không phải SID

`BasePermission` định nghĩa một số permission phổ biến:

| Permission | Mask mặc định | Diễn giải |
| --- | --- | --- |
| `BasePermission.READ` | `1` | Đọc |
| `BasePermission.WRITE` | `2` | Ghi |
| `BasePermission.CREATE` | `4` | Tạo |
| `BasePermission.DELETE` | `8` | Xóa |
| `BasePermission.ADMINISTRATION` | `16` | Quản trị ACL / đối tượng theo policy |

Một người có ACE `READ` trên Document#101 **không tự có WRITE**. Một authority `ROLE_EDITOR` được cấp WRITE trên Document#202 **không tự có WRITE** trên mọi object cùng loại.

Bit mask là mã biểu diễn permission, không phải 32 vị trí dành cho 32 tài liệu; mỗi domain object có ACL riêng nên hệ thống có thể có rất nhiều object identity.

Một số hệ thống dùng `CumulativePermission` hay custom `Permission`; khi đó ý nghĩa mask và so khớp của strategy cần được hiểu rõ. Không tự giả định một mask ghép luôn tương đương từng bit riêng lẻ trong mọi cấu hình strategy.

### 7.3. ACL cha và kế thừa

Một ACL có thể tham chiếu `getParentAcl()`. Để ACE của parent được xét xuống child theo cơ chế mặc định, phải có `isEntriesInheriting() == true` và parent phù hợp:

~~~text
Folder#8 ACL:
  GrantedAuthoritySid("ROLE_REVIEWER") → READ (grant)

Document#202 ACL:
  parent = Folder#8
  entriesInheriting = true
  (không có entry cụ thể phù hợp)
  => Có thể nhận quyền READ từ ACL của Folder#8
~~~

Nếu `entriesInheriting = false`, chỉ có quan hệ parent **không đủ** để con kế thừa ACE. Nếu ACL con đã có entry grant/deny phù hợp, strategy có thể giải quyết ngay tại con trước khi xét parent.

Vì vậy, khi cấp một authority SID ở folder, phạm vi có thể lan tới nhiều tài liệu con **nếu bật inheritance**. Trước khi mở role chung trên folder, phải kiểm tra toàn bộ cây và các tài liệu nhạy cảm ở dưới.

### 7.4. ACL owner không tự động đồng nghĩa READ/WRITE mọi dữ liệu

`Acl.getOwner()` cho biết SID được ghi nhận là **owner của ACL**. Cơ chế `AclAuthorizationStrategy` có thể cho owner đặc quyền **quản trị/sửa ACL** theo rule của nó, nhưng đó không phải lời hứa rằng `Acl.isGranted(READ,...)` luôn trả true cho owner.

Phân biệt ba việc:

1. **Sở hữu ACL**: ai được phép quản trị policy/ACE theo `AclAuthorizationStrategy`.
2. **Quyền nghiệp vụ trên object**: READ/WRITE/DELETE... theo `Acl.isGranted`.
3. **Quyền của hệ thống bên ngoài ACL**: ví dụ quyền SUPERADMIN, điều kiện tenant, trạng thái pháp lý, workflow.

Một chủ sở hữu ACL có thể cần ACE READ riêng nếu thiết kế đòi hỏi; không đánh đồng người được quản trị quyền với người luôn được đọc nội dung.

## 8. Lưu vào database: bốn bảng ACL

Spring Security ACL mặc định dùng các nhóm bảng:

| Bảng | Dữ liệu quan trọng | Tác dụng với SID |
| --- | --- | --- |
| `ACL_SID` | `id`, `principal`, `sid` | Định danh recipient, phân biệt principal và authority |
| `ACL_CLASS` | `id`, `class` | Định danh loại đối tượng |
| `ACL_OBJECT_IDENTITY` | `id`, `object_id_class`, `object_id_identity`, `parent_object`, `owner_sid`, `entries_inheriting` | Định danh object, owner ACL, parent/inheritance |
| `ACL_ENTRY` | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, audit flags | Một ACE gắn SID và quyền vào **một object ACL** |

Tên/cột cụ thể phải kiểm chứng theo script schema và phiên bản Spring Security ACL đang dùng. Ví dụ dữ liệu:

~~~text
ACL_SID
id=10, principal=true,  sid="alice"
id=11, principal=false, sid="ROLE_REVIEWER"

ACL_CLASS
id=1, class="demo.Document"

ACL_OBJECT_IDENTITY
id=1001, class=1, object_id_identity=101, owner_sid=10
id=1002, class=1, object_id_identity=202, owner_sid=10

ACL_ENTRY
acl_object_identity=1001, sid=10, mask=1, granting=true  (alice đọc 101)
acl_object_identity=1002, sid=11, mask=1, granting=true  (reviewer đọc 202)
~~~

Đây chỉ là **sơ đồ giá trị để học**, không phải SQL seed chạy ngay; các cột bắt buộc, ID, cấu trúc khóa ngoại, strategy tạo ID và cách cập nhật còn phải đáp ứng đúng database/schema.

**Điều quan trọng:** hệ thống không tìm ACE chỉ bằng `sid`. Nó tìm ACL của **ObjectIdentity** rồi xét các SID nhận quyền trong ACL ấy. Bảng `ACL_SID` không phải danh sách “role -> mọi tài nguyên”.

### Principal flag mang ý nghĩa bảo mật

Một người tên `ROLE_REVIEWER` vẫn có thể có `PrincipalSid("ROLE_REVIEWER")`, khác `GrantedAuthoritySid("ROLE_REVIEWER")`. Cột `principal` trong `ACL_SID` cho phép phân biệt. Nếu đồng bộ/migration dữ liệu làm mất cờ này, chính sách có thể cấp nhầm recipient.

### Không tự chỉnh bảng ACL bằng SQL thiếu hiểu biết

Để đảm bảo cache và trạng thái ACL nhất quán, nên dùng `MutableAclService` với các thao tác tạo/cập nhật/xóa thay vì chỉ INSERT thủ công ACE trực tiếp rồi bỏ quên cache. Nếu sửa DB trực tiếp (migration có kiểm soát), phải biết cách vô hiệu cache và kiểm tra parent/inheritance, SID row, thứ tự ACE, audit flags, unique constraints và transaction.

## 9. Ví dụ Java 17+ chạy độc lập: phân biệt SID và phạm vi object

Để kiểm chứng hai loại SID mà **không cần JDBC**, ta viết một chương trình nhỏ dùng đúng `PrincipalSid`, `GrantedAuthoritySid`, `SidRetrievalStrategyImpl`, `ObjectIdentityImpl` và `BasePermission` từ thư viện Spring Security ACL.

Chương trình có một danh sách **grants giả lập** để minh họa cách recipient khớp đối tượng. Hàm `hasIllustrativeDirectGrant` **không phải** thuật toán ACL thật: nó chỉ có grant, không có deny, audit, inheritance hay permission granting strategy. Khi xây ứng dụng thật, dùng `AclService`/`Acl.isGranted(...)`.

### 9.1. Build Gradle Java độc lập

Tạo một **project Java Gradle mới** để thực hành, không phải thêm vào repository ứng dụng đang dùng nếu chưa có yêu cầu. `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'demo'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-acl:6.5.4'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.aclscope.SidScopeDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Phiên bản `spring-security-acl:6.5.4` được dùng để **khóa một dòng API cụ thể cho ví dụ**. Trong dự án Spring Boot có dependency management, hãy dùng phiên bản Security được Boot quản lý thay vì buộc lẻ một phiên bản có thể không tương thích với toàn bộ stack.

### 9.2. Mã hoàn chỉnh

**`src/main/java/demo/aclscope/SidScopeDemo.java`**

~~~java
package demo.aclscope;

import java.util.Arrays;
import java.util.List;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class SidScopeDemo {

    private SidScopeDemo() {
    }

    // Chỉ mô phỏng ACE GRANT đơn giản để dạy phạm vi SID/object.
    // Không thay thế Acl.isGranted(...) và không xử lý DENY/INHERITANCE.
    public record DemoGrant(
            ObjectIdentity object,
            Sid recipient,
            Permission permission) {
    }

    public static Authentication auth(String principal, String... authorityNames) {
        var authorities = Arrays.stream(authorityNames)
                .map(SimpleGrantedAuthority::new)
                .toList();

        return new UsernamePasswordAuthenticationToken(
                principal, "demo-only", authorities);
    }

    public static List<Sid> sidsOf(Authentication authentication) {
        return new SidRetrievalStrategyImpl().getSids(authentication);
    }

    public static boolean hasIllustrativeDirectGrant(
            List<DemoGrant> grants,
            ObjectIdentity object,
            Permission permission,
            Authentication authentication) {

        List<Sid> recipients = sidsOf(authentication);

        return grants.stream().anyMatch(grant ->
                grant.object().equals(object)
                && grant.permission().equals(permission)
                && recipients.contains(grant.recipient()));
    }

    public static void main(String[] args) {
        Authentication alice = auth("alice", "ROLE_REVIEWER");
        Authentication bob = auth("bob", "ROLE_REVIEWER");
        Authentication carol = auth("carol", "ROLE_VIEWER");

        ObjectIdentity doc101 = new ObjectIdentityImpl("demo.Document", 101L);
        ObjectIdentity doc202 = new ObjectIdentityImpl("demo.Document", 202L);

        var grants = List.of(
                new DemoGrant(
                        doc101, new PrincipalSid("alice"), BasePermission.READ),
                new DemoGrant(
                        doc202, new GrantedAuthoritySid("ROLE_REVIEWER"),
                        BasePermission.READ));

        System.out.println("PrincipalSid alice matches alice: "
                + sidsOf(alice).contains(new PrincipalSid("alice")));
        System.out.println("PrincipalSid alice matches bob: "
                + sidsOf(bob).contains(new PrincipalSid("alice")));
        System.out.println("AuthoritySid REVIEWER matches alice: "
                + sidsOf(alice).contains(
                        new GrantedAuthoritySid("ROLE_REVIEWER")));
        System.out.println("AuthoritySid REVIEWER matches bob: "
                + sidsOf(bob).contains(
                        new GrantedAuthoritySid("ROLE_REVIEWER")));
        System.out.println("Principal/Authority same text equal: "
                + new PrincipalSid("ROLE_REVIEWER").equals(
                        new GrantedAuthoritySid("ROLE_REVIEWER")));

        System.out.println("alice doc101 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc101, BasePermission.READ, alice));
        System.out.println("bob doc101 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc101, BasePermission.READ, bob));
        System.out.println("alice doc202 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc202, BasePermission.READ, alice));
        System.out.println("bob doc202 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc202, BasePermission.READ, bob));
        System.out.println("carol doc202 READ: "
                + hasIllustrativeDirectGrant(
                        grants, doc202, BasePermission.READ, carol));

        System.out.println("READ mask: " + BasePermission.READ.getMask());
        System.out.println("WRITE mask: " + BasePermission.WRITE.getMask());
    }
}
~~~

Trong chương trình, `auth(...)` tạo `UsernamePasswordAuthenticationToken` cho **mục đích demo/test**, không phải một cơ chế xác thực production. `SidRetrievalStrategyImpl` nhận Authentication và trả các SID tương ứng. Mỗi `DemoGrant` gắn **đúng một ObjectIdentity + recipient + permission**. Không có đoạn nào tạo quyền dựa trên username truyền từ request chưa xác thực trong ứng dụng thật.

### 9.3. Chạy và stdout mong đợi

Chạy tại thư mục project Gradle có wrapper:

~~~text
./gradlew run
~~~

Trên Windows:

~~~text
gradlew.bat run
~~~

Chương trình in các dòng nghiệp vụ chính xác sau (Gradle có thể in thêm các dòng về task/build):

~~~text
PrincipalSid alice matches alice: true
PrincipalSid alice matches bob: false
AuthoritySid REVIEWER matches alice: true
AuthoritySid REVIEWER matches bob: true
Principal/Authority same text equal: false
alice doc101 READ: true
bob doc101 READ: false
alice doc202 READ: true
bob doc202 READ: true
carol doc202 READ: false
READ mask: 1
WRITE mask: 2
~~~

Giải thích:

1. Alice và Bob có principal khác nhau.
2. Cả hai mang authority `ROLE_REVIEWER`.
3. PrincipalSid có cùng chuỗi với GrantedAuthoritySid vẫn là hai loại SID khác nhau.
4. Grant tại `doc101` chỉ dành cho alice; Bob không nhận grant này dù là reviewer.
5. Grant tại `doc202` dành cho authority reviewer nên Alice và Bob đều khớp.
6. Carol không có SID reviewer nên không khớp grant tại `doc202`.
7. `READ` có mask 1, `WRITE` có mask 2; permission là trục độc lập với object và SID.

**Ranh giới quan trọng:** `hasIllustrativeDirectGrant` được đặt tên như vậy để tránh nhầm với kết quả `Acl.isGranted` khi tồn tại deny, nhiều ACE, inheritance, auditing hay chiến lược grant riêng. Không copy hàm này vào production để thay quyết định ACL thật.

### 9.4. JUnit test kiểm tra phạm vi không bị mở rộng

**`src/test/java/demo/aclscope/SidScopeDemoTest.java`**

~~~java
package demo.aclscope;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.core.Authentication;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SidScopeDemoTest {

    @Test
    void principalIdentityIsNotAnAuthorityIdentity() {
        assertFalse(new PrincipalSid("ROLE_REVIEWER")
                .equals(new GrantedAuthoritySid("ROLE_REVIEWER")));
        assertEquals(new PrincipalSid("alice"), new PrincipalSid("alice"));
    }

    @Test
    void principalSidMatchesOnlyTheNamedUser() {
        Authentication alice = SidScopeDemo.auth("alice", "ROLE_REVIEWER");
        Authentication bob = SidScopeDemo.auth("bob", "ROLE_REVIEWER");

        assertTrue(SidScopeDemo.sidsOf(alice)
                .contains(new PrincipalSid("alice")));
        assertFalse(SidScopeDemo.sidsOf(bob)
                .contains(new PrincipalSid("alice")));
    }

    @Test
    void authoritySidMatchesEachCurrentHolder() {
        Authentication alice = SidScopeDemo.auth("alice", "ROLE_REVIEWER");
        Authentication bob = SidScopeDemo.auth("bob", "ROLE_REVIEWER");
        Authentication carol = SidScopeDemo.auth("carol", "ROLE_VIEWER");

        var reviewer = new GrantedAuthoritySid("ROLE_REVIEWER");
        assertTrue(SidScopeDemo.sidsOf(alice).contains(reviewer));
        assertTrue(SidScopeDemo.sidsOf(bob).contains(reviewer));
        assertFalse(SidScopeDemo.sidsOf(carol).contains(reviewer));
    }

    @Test
    void grantIsConstrainedByObjectAndPermission() {
        ObjectIdentity doc101 =
                new ObjectIdentityImpl("demo.Document", 101L);
        ObjectIdentity doc202 =
                new ObjectIdentityImpl("demo.Document", 202L);

        var grants = List.of(new SidScopeDemo.DemoGrant(
                doc101, new PrincipalSid("alice"), BasePermission.READ));

        Authentication alice = SidScopeDemo.auth("alice", "ROLE_REVIEWER");

        assertTrue(SidScopeDemo.hasIllustrativeDirectGrant(
                grants, doc101, BasePermission.READ, alice));
        assertFalse(SidScopeDemo.hasIllustrativeDirectGrant(
                grants, doc202, BasePermission.READ, alice));
        assertFalse(SidScopeDemo.hasIllustrativeDirectGrant(
                grants, doc101, BasePermission.WRITE, alice));
    }

    @Test
    void sameIdInDifferentTypeIsDifferentObject() {
        ObjectIdentity doc101 =
                new ObjectIdentityImpl("demo.Document", 101L);
        ObjectIdentity folder101 =
                new ObjectIdentityImpl("demo.Folder", 101L);

        assertFalse(doc101.equals(folder101));
    }
}
~~~

Chạy:

~~~text
./gradlew test --tests demo.aclscope.SidScopeDemoTest
~~~

Khi tests thành công, JUnit xác minh **đúng loại SID**, recipient theo user/role, phạm vi theo object, theo permission, và sự khác biệt giữa hai loại object có cùng ID. Test này chỉ kiểm tra demo grant selection; hãy bổ sung integration test với JDBC ACL thực để bảo đảm grant/deny/inheritance hoạt động như mong muốn.

## 10. Lưu grant thật bằng `MutableAclService`: đoạn tích hợp minh họa

Ví dụ thực hành bên trên không dùng database. Khi cần quản trị ACL thật, ứng dụng thường có:

- `spring-security-acl` trong dependencies.
- `DataSource` và bốn bảng `ACL_SID`, `ACL_CLASS`, `ACL_OBJECT_IDENTITY`, `ACL_ENTRY` được tạo đúng schema.
- `JdbcMutableAclService`, `BasicLookupStrategy`, `AclCache`, `PermissionGrantingStrategy`, `AclAuthorizationStrategy` được cấu hình phù hợp.
- Một service quản trị ACL có **chốt quyền của riêng nó** để người gọi không tùy tiện cấp quyền cho người khác.

Sau khi có `MutableAclService aclService` được inject và được phép sửa ACL, thao tác thêm ACE có hình thức:

~~~java
// MÃ MINH HỌA TRONG SERVICE ĐÃ CÓ ACL INFRASTRUCTURE.
// Không chạy độc lập; không gọi từ API công khai thiếu kiểm tra quyền quản trị.

ObjectIdentity object = new ObjectIdentityImpl("demo.Document", 101L);

MutableAcl acl;
try {
    acl = (MutableAcl) aclService.readAclById(object);
} catch (NotFoundException missing) {
    acl = aclService.createAcl(object);
}

// Chia sẻ READ cho đúng user "alice".
acl.insertAce(
        acl.getEntries().size(),
        BasePermission.READ,
        new PrincipalSid("alice"),
        true
);

// Cấp READ cho người có authority ROLE_REVIEWER trên OBJECT NÀY.
acl.insertAce(
        acl.getEntries().size(),
        BasePermission.READ,
        new GrantedAuthoritySid("ROLE_REVIEWER"),
        true
);

aclService.updateAcl(acl);
~~~

Imports cần thiết cho snippet này:

~~~java
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
~~~

Đoạn trên cố tình **không giả vờ là chương trình chạy độc lập**: còn thiếu Spring Context, DataSource, SQL schema và ACL service/configuration. Khi thêm vào service thật, phải bảo vệ đường quản trị bằng authentication, kiểm tra quyền cấp ACE, tính idempotent, tránh trùng lặp entry và xử lý cạnh tranh.

### Grant và deny không nên bị tính bằng tay

`insertAce(position, permission, sid, granting)` nhận:

- `position`: vị trí trong thứ tự ACE (thường append bằng `acl.getEntries().size()`).
- `permission`: ví dụ `BasePermission.READ`.
- `sid`: PrincipalSid hoặc GrantedAuthoritySid.
- `granting = true`: grant; `false`: deny.

Nếu cùng một object có nhiều ACE chồng lấn, đừng suy luận rằng ACE thêm cuối luôn có hiệu lực. Thứ tự ACE, SID và permission do `PermissionGrantingStrategy` sử dụng có thể ảnh hưởng kết quả. Sau cập nhật ACL, nên có test yêu cầu **một user được cấp**, **một user thiếu quyền bị từ chối**, và test xung đột deny/group grant trước khi triển khai rộng.

### Không đồng nhất ACL admin với object permission

`AclAuthorizationStrategyImpl` quản lý ai **được phép thay đổi ACL**. Nó có thể xét owner ACL, authority quản trị hoặc quyền ADMINISTRATION tùy cấu hình. Khả năng chỉnh sửa ACE khác với quyết định `Acl.isGranted(READ,...)` trên tài liệu. Service “grant READ cho alice” là thao tác nhạy cảm: chỉ những actor được phân quyền quản lý ACL mới được thực hiện.

## 11. Đánh giá quyền thật bằng `Acl.isGranted(...)`

Một ACL có thể chỉ tải các SID cần thiết để tối ưu truy vấn. API:

~~~java
boolean allowed = acl.isGranted(
        List.of(BasePermission.READ),
        sids,
        false
);
~~~

Ba tham số:

1. `List<Permission>`: các permission có thể được chấp nhận; nếu truyền nhiều permission, thứ tự có ý nghĩa theo strategy.
2. `List<Sid>`: các SID của người dùng đang xét.
3. `administrativeMode`: chế độ kiểm tra phục vụ quản trị, thông thường bỏ qua audit logging khi true; nó **không phải** cờ “người dùng là admin”.

Một đoạn tích hợp đầy đủ hơn về logic đọc là:

~~~java
// MINH HỌA: giả định aclService và Authentication đã được cung cấp an toàn.
ObjectIdentity object = new ObjectIdentityImpl("demo.Document", 101L);

List<Sid> sids = new SidRetrievalStrategyImpl().getSids(authentication);

boolean allowed;
try {
    Acl acl = aclService.readAclById(object, sids);
    allowed = acl.isGranted(List.of(BasePermission.READ), sids, false);
} catch (NotFoundException missingPermissionOrAcl) {
    // Không có kết luận cấp quyền -> fail closed.
    allowed = false;
}
~~~

Các import bổ sung:

~~~java
import java.util.List;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.Sid;
~~~

Trong ứng dụng thực, `UnloadedSidException` cũng có thể xảy ra nếu ACL chỉ được tải một phần nhưng bạn hỏi SID không nằm trong phần đã tải. Đó là dấu hiệu tải thiếu dữ liệu cần thiết, **không phải một grant**; phải sửa quá trình truy xuất hoặc xử lý lỗi an toàn, không tự trả true.

### Khác biệt quan trọng: tìm thấy ACE, bị deny và không tìm thấy ACE

Với strategy mặc định:

- Có ACE grant phù hợp thì có thể cấp quyền.
- Có ACE deny phù hợp thì quyền có thể bị từ chối tùy cách duyệt permission/SID.
- Không tìm thấy ACE nào đủ để đưa ra kết luận có thể dẫn tới `NotFoundException`, không phải “mặc định allow”.
- Có ACL parent và `entriesInheriting == true` có thể khiến quá trình xét tiếp sang parent nếu không có entry trực tiếp tương ứng.

Không nên viết một hàm production kiểu `return acl.getEntries().stream().anyMatch(ace -> ace.isGranting())`. Hàm đó bỏ qua SID, permission, thứ tự, loadedSids và inheritance.

### Khi nào nên dùng `hasPermission(...)`?

Spring Security ACL có `AclPermissionEvaluator`, có thể cắm vào `DefaultMethodSecurityExpressionHandler` để annotation `hasPermission` thực hiện truy vấn ACL mà không phải viết `aclService.readAclById` trong mọi service.

~~~java
// Trích đoạn cấu hình; cần đã có bean AclService được cấu hình đúng.
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        AclService aclService) {

    var handler = new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(new AclPermissionEvaluator(aclService));
    return handler;
}
~~~

Sau khi bật `@EnableMethodSecurity` và có bean handler, service có thể dùng:

~~~java
// Minhh họa trên method; target type và ACL ObjectIdentity phải khớp.
@PreAuthorize("hasPermission(#documentId, 'demo.Document', 'READ')")
public Document read(long documentId) {
    // ...
}
~~~

Nếu dùng `hasPermission(returnObject, 'READ')`, đối tượng trả về phải có cách lấy ID tương thích với `ObjectIdentityRetrievalStrategy`. `ObjectIdentityImpl(Object)` mặc định dùng getter như `getId()`; một Java record chỉ có `id()` không tự đáp ứng convention đó. Ngoài ra, `ObjectIdentity` trong ACL lưu phải khớp cả tên type lẫn ID với object được evaluator tạo.

Đây là phần tích hợp minh họa, không phải bản cấu hình JDBC đầy đủ. Mục tiêu bài là hiểu **SID nhận quyền và phạm vi ACE**, trước khi ghép vào ACL persistence/Method Security của một dự án thật.

## 12. Vai trò, nhóm, quyền theo tài nguyên và phạm vi hiệu lực

### Phân biệt ba câu hỏi authorization

| Câu hỏi | Cơ chế ví dụ |
| --- | --- |
| Alice đã xác thực chưa? | `Authentication.isAuthenticated()` / hệ thống xác thực |
| Alice có authority `ROLE_REVIEWER` không? | `hasAuthority('ROLE_REVIEWER')` hoặc authority từ Authentication |
| Alice được READ **Document#202** không? | `Acl.isGranted(READ, SID list)` trên ACL của Document#202 |

Chỉ câu thứ ba kết hợp **người nhận + hành động + đối tượng**. Vì vậy, ACL và RBAC không loại trừ nhau: RBAC cung cấp authority, còn ACL có thể dùng authority đó làm recipient cho những object cụ thể.

### Phạm vi theo cá nhân và theo nhóm có thể cùng tồn tại

Ví dụ:

~~~text
Document#101:
    PrincipalSid("alice")          → READ:grant
    GrantedAuthoritySid("ROLE_EDITOR") → WRITE:grant

Document#202:
    GrantedAuthoritySid("ROLE_REVIEWER") → READ:grant
    PrincipalSid("bob")            → DELETE:deny
~~~

Không nên đọc ví dụ trên thành “bob luôn không xóa được mọi tài liệu” hoặc “editor luôn sửa được mọi tài liệu”. Mỗi ACE gắn một ACL, một permission cụ thể, và tùy cơ chế kế thừa. Nếu object khác không có ACE tương đương, kết quả có thể khác.

### Khi nào chọn SID nào?

Ưu tiên `PrincipalSid` nếu:
- Cấp quyền ngoại lệ cho một người rõ ràng.
- Chia sẻ cá nhân một đối tượng.
- Cần thu hồi người nhận cụ thể mà không sửa membership nhóm.

Ưu tiên `GrantedAuthoritySid` nếu:
- Cấp quyền theo nhóm/chức năng ổn định.
- Muốn người gia nhập hoặc rời nhóm được áp dụng theo authority hiện tại.
- Có nhiều đối tượng mà cùng chính sách nhóm được cấp **theo từng ACL** hoặc thông qua cây kế thừa có chủ đích.

Không dùng nhóm quá rộng (ví dụ `ROLE_USER`) để thay thế kiểm tra tenant/owner cho tài liệu mật. Nếu role được mọi tài khoản mang, một ACE theo role trên object có thể mở object đó cho **mọi tài khoản mang role**, kể cả người ngoài nhóm dự án nếu không có ranh giới tenant khác.

## 13. Multi-tenant, phân cấp quyền và vòng đời truy cập

### 13.1. Tenant không phải thuộc tính mặc định của SID

Mặc định, `PrincipalSid` và `GrantedAuthoritySid` không có trường tenant riêng. Vì vậy:

~~~text
Tenant A: username=alice, authority=ROLE_REVIEWER
Tenant B: username=alice, authority=ROLE_REVIEWER
~~~

có nguy cơ cùng khớp SID nếu hệ thống dùng chung bảng ACL mà không phân biệt tenant. Biện pháp bảo vệ phải được thiết kế ở nhiều lớp:

- Dùng principal identifier bất biến, duy nhất toàn hệ thống trong Authentication.
- Ràng buộc tenant ở lookup ObjectIdentity/repository và use case.
- Nếu dùng authority theo tenant, tên phải được tạo/kiểm chứng bởi hệ thống đáng tin, không lấy từ request.
- Test tình huống trùng username, trùng object ID giữa tenant, inheritance folder khác tenant và role chia sẻ.

Không coi một prefix chuỗi `TENANT_7_` là đủ nếu attacker có thể tự yêu cầu authority đó hoặc ACL query không ràng buộc tenant. Đặc biệt, `ObjectIdentityImpl("demo.Document", 101L)` chỉ mang type và ID; nếu DB của hai tenant đều có tài liệu ID 101, cần chuẩn hóa ID toàn hệ thống hoặc thiết kế ACL partition tương ứng.

### 13.2. Role hierarchy có thể mở rộng tập người nhận

Nếu ứng dụng cấu hình một hierarchy cho `SidRetrievalStrategyImpl`, một người chỉ khai báo `ROLE_ADMIN` có thể được xem như cũng nắm authority `ROLE_REVIEWER` nếu hierarchy quy định. Kết quả là ACE `GrantedAuthoritySid("ROLE_REVIEWER")` có thể áp dụng cho admin dù token không liệt kê ROLE_REVIEWER trực tiếp.

Đây là hành vi có thể hợp lý trong RBAC, nhưng ACL cần test để biết **chiến lược SID retrieval thực tế** và xem việc mở rộng quyền có vượt ranh giới tenant/nhóm không. Không mặc nhiên coi hierarchy là một phần của mọi instance `SidRetrievalStrategyImpl()`.

### 13.3. Thu hồi role có hiệu lực khi nào?

Việc xóa `ROLE_REVIEWER` trong hệ thống phân quyền không có nghĩa mọi `Authentication` đã cấp trước đó được cập nhật ngay. Với session hoặc JWT có authority đã snapshot, người dùng có thể tiếp tục mang SID role cũ cho tới khi session/token được refresh, thu hồi hoặc hết hạn. Nếu yêu cầu thu hồi tức thì, phải có chiến lược token revocation, server-side authority lookup hoặc thay đổi ACL có kiểm soát.

### 13.4. Người dùng bị xóa, username đổi, role bị đổi tên

Cần có vòng đời cho `ACL_SID` và `ACL_ENTRY`:

- Khi user bị xóa, quyết định giữ lịch sử ACE hay xóa/revoke quyền; tránh SID mồ côi bị tái sử dụng sau này.
- Khi thay username hoặc canonical principal ID, phải đồng bộ SID nếu định danh lưu trong ACL thay đổi.
- Khi đổi tên role, migration cần cập nhật cả authority phát từ authentication **và** `ACL_SID`/ACE sử dụng role cũ.
- Khi đổi project membership, kiểm tra thời điểm token phản ánh membership mới.
- Khi xóa domain object, nên dọn ACL tương ứng để tránh quyền còn sót khi ID được tái sử dụng.

### 13.5. ACL cache và cập nhật quyền

Spring ACL thường dùng `AclCache` để giảm chi phí truy vấn. Khi thêm/xóa ACE qua `MutableAclService`, persistence/cache được đồng bộ theo triển khai. Nếu bypass service để sửa SQL trực tiếp, cache có thể giữ ACL cũ và tiếp tục cấp quyền ngoài ý muốn. Trong hệ thống phân tán phải xem xét invalidation giữa các node, consistency window và kiểm thử thu hồi quyền.

## 14. Lỗi phổ biến cần phát hiện bằng test

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Cấp quyền cho một người nhưng người khác cùng role cũng truy cập | Đã dùng `GrantedAuthoritySid` thay vì `PrincipalSid` | Xác định đúng recipient; test người khác cùng role |
| Đã cấp role reviewer nhưng không đọc được object | ACE không thuộc ACL của object đó hoặc inheritance chưa bật | Kiểm tra ObjectIdentity, ACL parent và entriesInheriting |
| Một người ở tenant B nhận quyền tenant A | Principal string/authority trùng giữa tenant | Dùng global user ID và ràng buộc tenant ở lookup/policy |
| `GrantedAuthoritySid("REVIEWER")` không khớp | Authentication chứa `ROLE_REVIEWER` | Lưu đúng chuỗi authority, không tự thêm prefix |
| Quyền chỉ hoạt động khi có user cụ thể | ACE là PrincipalSid, không phải authority SID | Dùng đúng loại SID cho mục tiêu |
| Quyền WRITE xuất hiện trên tài liệu khác | ACL inheritance/grant quá rộng hoặc object identity bị dùng sai | Kiểm tra cây và type/id của từng object |
| ACL owner truy cập được phần quản trị nhưng không đọc được nội dung | Quyền sửa ACL khác quyền READ trên object | Kiểm tra ACE READ riêng và policy nghiệp vụ |
| Test membership đơn giản pass nhưng ACL thật deny | Quên deny, thứ tự ACE hoặc strategy | Dùng `Acl.isGranted` và integration test grant/deny |
| `NotFoundException` khi hỏi permission | Không tìm thấy ACE đủ kết luận; có thể không có ACL | Fail closed; tạo ACL/ACE khi đúng quy trình |
| `UnloadedSidException` | ACL chỉ tải một phần SID | Tải đủ SID hoặc xử lý lỗi an toàn |
| ACL thay đổi nhưng quyền chưa đổi | Cache, session hoặc JWT còn cũ | Kiểm tra invalidation và lifecycle authentication |
| Người dùng đổi email rồi mất ACE cá nhân | PrincipalSid dùng email dễ đổi | Dùng subject ID ổn định hoặc migration |
| Permission `READ` bị nhầm với `WRITE` | Suy luận từ role, không xét bit mask | Dùng `BasePermission` đúng và test từng hành động |
| Đồng bộ SQL thủ công rồi xuất hiện lỗi | Cache/foreign keys/ace_order không khớp | Dùng MutableAclService hoặc migration có kiểm soát |
| Custom Sid lưu được trong Java nhưng JDBC không tìm thấy | Persistence/lookup mặc định chỉ hiểu SID type chuẩn | Thiết kế mở rộng strategy JDBC và schema, kiểm thử E2E |

## 15. Chiến lược kiểm thử thực tế

Để một ACL không bị mở quyền ngầm, cần test theo **ma trận bốn chiều**:

| Người dùng và authority | Object | Permission | Mong đợi |
| --- | --- | --- | --- |
| Alice, reviewer | Document#101 | READ | Allow theo PrincipalSid |
| Bob, reviewer | Document#101 | READ | Deny nếu không có ACE khác |
| Alice, reviewer | Document#202 | READ | Allow theo GrantedAuthoritySid |
| Bob, reviewer | Document#202 | READ | Allow theo GrantedAuthoritySid |
| Carol, viewer | Document#202 | READ | Deny nếu không có ACE khác |
| Alice, reviewer | Document#101 | WRITE | Deny nếu không có WRITE ACE |
| Alice tenant B với principal trùng | Document#101 tenant A | READ | Deny theo chính sách tenant |
| Role reviewer đã bị thu hồi trong auth mới | Document#202 | READ | Deny nếu không có SID khác phù hợp |
| Bob reviewer nhưng có ACE deny riêng | Document#202 | READ | Phải theo strategy/ACE order đã cấu hình |
| Alice, owner ACL nhưng thiếu READ ACE | Document#303 | READ | Không suy ra allow chỉ từ owner ACL |

Các dòng gắn “nếu không có ACE khác” nhắc rằng ACL thật có thể chứa **nhiều entry** và inheritance. Không dùng một dòng ví dụ để tuyên bố kết quả cho mọi cấu hình.

Khi làm integration test, nên:

1. Khởi tạo SQL schema ACL trên database test.
2. Tạo hai Authentication khác principal, cùng authority và một principal khác authority.
3. Tạo ACL cho hai ObjectIdentity khác nhau, thêm ACE theo user và authority.
4. Gọi `Acl.isGranted` trên các SID thực được lấy từ Authentication.
5. Thêm deny, thay đổi `ace_order` và bật/tắt `entriesInheriting` để xác nhận cơ chế đã hiểu.
6. Thu hồi một authority rồi tạo Authentication mới, test quyền thay đổi.
7. Thử hai tenant có trùng tên/ID, test không đọc chéo.
8. Kiểm tra cache và việc xóa ACE tác động tới quyết định sau cập nhật.

## 16. Bài tập thực hành

**Bài 1 – Chia sẻ cá nhân và nhóm.** Tạo ACL cho `Document#101`: cấp READ cho `PrincipalSid("alice")`. Tạo ACL cho `Document#202`: cấp READ cho `GrantedAuthoritySid("ROLE_REVIEWER")`. Viết test cho alice, bob (cùng reviewer) và carol (viewer) để giải thích tại sao phạm vi khác nhau.

**Bài 2 – Đổi role.** Thay authority của Bob từ `ROLE_REVIEWER` sang `ROLE_VIEWER`. Dựng Authentication mới, tính lại SID và test Bob không còn recipient ở ACE reviewer. Giải thích vì sao JWT/session cũ có thể chưa phản ánh thay đổi.

**Bài 3 – Phân biệt principal và authority cùng tên.** Tạo `PrincipalSid("ROLE_EDITOR")` và `GrantedAuthoritySid("ROLE_EDITOR")`. Giải thích vì sao hai SID khác nhau trong `ACL_SID` dù cùng chuỗi; viết test không bị đánh đồng.

**Bài 4 – Kế thừa.** Tạo folder ACL cấp READ cho role reviewer; liên kết child document ACL. Bật/tắt `entriesInheriting` và so sánh kết quả `Acl.isGranted`. Sau đó thêm một deny ACE ở child và kiểm tra hiệu ứng theo strategy thật.

**Bài 5 – Quyền theo tenant.** Có hai tài liệu cùng ID số học `101` ở tenant A/B. Thiết kế ObjectIdentity và principal ID không trùng, thêm kiểm tra tenant và test người ở tenant A không đọc dữ liệu tenant B.

**Bài 6 – Kiểm tra quyền quản trị ACL.** Phân biệt chủ sở hữu ACL, authority được phép thay đổi ACE, và quyền READ/WRITE trên domain object. Test rằng người có READ không đương nhiên được sửa ACL, người được sửa ACL không tự động có mọi quyền nghiệp vụ.

**Bài 7 – Thu hồi và cache.** Cấp READ theo PrincipalSid, đọc ACL lần đầu để lấp cache, sau đó xóa ACE bằng `MutableAclService`. Kiểm tra quyết định mới không tiếp tục allow vì cache cũ.

**Tiêu chí hoàn thành:** nhận diện được SID cá nhân và SID authority; chỉ ra đầy đủ recipient/object/permission/grant khi đọc ACE; hiểu `ACL_SID` và `ACL_ENTRY`; biết khi nào role membership có thể làm mở rộng phạm vi; dùng `Acl.isGranted` thay vì tự duyệt danh sách grant; nhận ra ảnh hưởng của parent, tenant, cache, danh tính không ổn định và thời điểm thu hồi quyền.

## Tài liệu tham khảo chính thức

- Spring Security – **Domain Object Security (ACLs)**: https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security API – **PrincipalSid**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/PrincipalSid.html
- Spring Security API – **GrantedAuthoritySid**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/GrantedAuthoritySid.html
- Spring Security API – **SidRetrievalStrategyImpl**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/SidRetrievalStrategyImpl.html
- Spring Security API – **Acl / isGranted**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security API – **DefaultPermissionGrantingStrategy**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html
- Spring Security API – **MutableAclService**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html
