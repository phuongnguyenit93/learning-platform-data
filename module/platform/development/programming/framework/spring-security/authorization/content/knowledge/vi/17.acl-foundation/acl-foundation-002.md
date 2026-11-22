# Acl, AccessControlEntry, ObjectIdentity, Sid và Permission trong Spring Security ACL

## 1. ACL giải quyết bài toán gì?

Phân quyền theo vai trò (RBAC) thường trả lời: *Người dùng có vai trò EDITOR hay không?* Nhưng một ứng dụng quản lý tài liệu thường cần trả lời câu hỏi cụ thể hơn: *Alice có được đọc tài liệu số 42 không? Bob có bị cấm đọc chính tài liệu đó không? Nhóm REVIEWER có được đọc nhưng không được xóa tài liệu này không?*

**Access Control List (ACL)** là mô hình gắn các quyền vào **từng đối tượng nghiệp vụ**. Thay vì chỉ đặt một role chung cho mọi tài liệu, hệ thống lưu các dòng quy tắc xác định người/nhóm nào có quyền gì đối với một tài liệu cụ thể.

Trong Spring Security ACL, năm khái niệm cốt lõi liên kết với nhau:

- **`Acl`**: danh sách các quy tắc truy cập của **một đối tượng**.
- **`AccessControlEntry` (ACE)**: **một dòng quy tắc** bên trong ACL, biểu thị cấp hoặc từ chối một quyền.
- **`ObjectIdentity`**: khóa nhận diện **đúng đối tượng** được bảo vệ, thông thường là cặp `type + identifier`.
- **`Sid`** (*Security Identity*): chủ thể nhận quyền, chẳng hạn một principal hoặc một `GrantedAuthority`.
- **`Permission`**: loại thao tác/quyền trên đối tượng, ví dụ `READ`, `WRITE`, `DELETE`.

Bài học thuộc nhóm **Nền tảng ACL** trong Spring Security Authorization. Mục tiêu là hiểu **quan hệ dữ liệu, ý nghĩa API và cơ chế ra quyết định**, không chỉ ghi nhớ tên interface.

Sau bài này, bạn sẽ:

1. Giải thích chính xác một ACL chứa những ACE gì và vì sao `ObjectIdentity` khác `Sid`.
2. Phân biệt `grant=true`, `grant=false` và **không có ACE khớp**.
3. Sử dụng `PrincipalSid`, `GrantedAuthoritySid`, `ObjectIdentityImpl`, `BasePermission`.
4. Hiểu quyền dạng bit mask, thứ tự ACE/SID và cơ chế kế thừa ACL cha.
5. Chạy kiểm thử Java 17+ sử dụng chính các interface/implementation của `spring-security-acl`.
6. Biết cách các đối tượng này được lưu vào bốn bảng chuẩn và đi đến `AclService`/`PermissionEvaluator`.

**Phạm vi phiên bản:** ví dụ API sử dụng Spring Security ACL 6.5.x và Java 17+; dự án Gradle dùng Spring Boot BOM 3.5.0 để quản lý phiên bản. Khi dùng Spring Security 7.x hoặc phiên bản dự án khác, hãy đối chiếu API/Javadoc tương ứng.

## 2. Một ví dụ xuyên suốt

Giả sử có tài liệu nghiệp vụ `Document(id=42, title="Budget")`. Quy tắc mong muốn:

| Người hoặc nhóm | Hành động | Quyết định |
| --- | --- | --- |
| `alice` | `READ` | Cấp |
| `alice` | `WRITE` | Cấp |
| `bob` | `READ` | Từ chối tường minh |
| `ROLE_REVIEWER` | `READ` | Cấp |
| `charlie` | `DELETE` | Chưa có quy tắc khớp |

Mô hình khái niệm:

```text
ObjectIdentity
  type       = "demo.Document"
  identifier = 42
       |
       v
Acl (quy tắc cho đúng document #42)
  owner = PrincipalSid("acl-admin")
  parentAcl = null
  entriesInheriting = false
       |
       +---- ACE 0: PrincipalSid("alice")        READ   GRANT
       +---- ACE 1: PrincipalSid("alice")        WRITE  GRANT
       +---- ACE 2: PrincipalSid("bob")          READ   DENY
       +---- ACE 3: GrantedAuthoritySid(REVIEWER) READ  GRANT
```

Lưu ý chuỗi trong code sẽ là `"ROLE_REVIEWER"`, còn chữ `REVIEWER` ở sơ đồ là tên rút gọn để dễ đọc.

**Mỗi ACE ghép ba nội dung cốt lõi:** *đúng ACL đối tượng nào* + *SID nào* + *Permission nào*, kèm cờ **`granting`** xác định cấp hay từ chối. Một ACL có thể có nhiều ACE cho cùng SID nhưng những permission khác nhau.

Điều cần tránh: `Document.owner` trong bảng nghiệp vụ **không tự đồng nghĩa** `Acl.getOwner()`. Chủ sở hữu ACL phục vụ quyền quản trị ACL theo chiến lược, trong khi quyền đọc/ghi tài liệu được xét bằng ACE và chiến lược cấp quyền; hai khái niệm có thể trùng hoặc khác nhau.

## 3. Khái niệm 1: `ObjectIdentity` — xác định đúng đối tượng

Interface:

```java
package org.springframework.security.acls.model;

public interface ObjectIdentity extends java.io.Serializable {
    java.io.Serializable getIdentifier();
    String getType();
}
```

Đây là dạng rút gọn các thành phần quan trọng để học, **không phải mã nguồn interface nguyên văn đầy đủ**.

Ví dụ triển khai:

```java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ObjectIdentity;

ObjectIdentity document42 =
    new ObjectIdentityImpl("demo.Document", 42L);

ObjectIdentity invoice42 =
    new ObjectIdentityImpl("demo.Invoice", 42L);
```

- `getType()`: chuỗi loại đối tượng, thường là tên lớp domain Java.
- `getIdentifier()`: ID duy nhất **trong phạm vi loại đối tượng**. `42L` là ID dạng `Long`.
- `document42` **khác** `invoice42` dù cả hai có ID 42.
- `new ObjectIdentityImpl("demo.Document", 42L)` và một instance mới với cùng type/ID đại diện cùng identity theo cách triển khai mặc định.

Cũng có constructor `new ObjectIdentityImpl(Document.class, 42L)`; constructor dựa trên class lấy tên lớp đó làm type. **Cần thống nhất cách tạo type** giữa phần ghi ACL và phần đọc quyền: `"demo.Document"`, `Document.class` hay class proxy có thể dẫn đến type khác nếu sử dụng tùy tiện.

Không nên sử dụng ID có ý nghĩa kinh doanh dễ thay đổi như tên tài liệu/slug làm định danh ACL lâu dài nếu có thể dùng primary key ổn định. Trong multi-tenant system, type và identifier phải phân biệt được đúng đối tượng/tenant; không thể giả định ID tự tăng trùng giữa hai tenant vẫn là cùng tài nguyên.

`ObjectIdentity` **không phải** toàn bộ entity `Document`, không chứa nội dung tài liệu và không tự quyết định quyền. Nó là **khóa liên kết** ACL với đúng bản ghi.

## 4. Khái niệm 2: `Sid` — ai được cấp hoặc bị chặn?

`Sid` viết tắt của *Security Identity*. Nó trừu tượng hóa chủ thể để ACL không phải lưu trực tiếp toàn bộ đối tượng `Authentication`, `UserDetails` hay token. Hai triển khai thông dụng:

```java
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.model.Sid;

Sid alice = new PrincipalSid("alice");
Sid reviewerRole = new GrantedAuthoritySid("ROLE_REVIEWER");
```

**`PrincipalSid`** đại diện cho một principal, thường được biểu diễn bằng tên `Authentication.getName()`. Khi người dùng đăng nhập là Alice, principal SID tương ứng có thể là `PrincipalSid("alice")`. Mặc định Spring Security cũng có constructor nhận `Authentication`.

**`GrantedAuthoritySid`** đại diện cho một authority được cấp cho authentication, chẳng hạn `ROLE_REVIEWER`. Nhiều người dùng có thể cùng thuộc một authority; một ACE gắn cho authority giúp không phải tạo ACE riêng cho mọi thành viên nếu chính sách của ứng dụng cho phép như vậy.

Ví dụ:

| Authentication | Danh sách SID thường xét |
| --- | --- |
| Alice có `ROLE_REVIEWER` | `PrincipalSid("alice")`, `GrantedAuthoritySid("ROLE_REVIEWER")` |
| Bob có `ROLE_EDITOR` | `PrincipalSid("bob")`, `GrantedAuthoritySid("ROLE_EDITOR")` |
| Anonymous | Cần chính sách riêng; không mặc định coi là một principal đã xác thực có quyền |

Các SID phải khớp **cùng kiểu/giá trị** được lưu trong ACL. `PrincipalSid("ROLE_REVIEWER")` **không tương đương** `GrantedAuthoritySid("ROLE_REVIEWER")`, vì một bên là tên principal và một bên là authority.

`SidRetrievalStrategy` có thể xây dựng danh sách SID từ `Authentication` (thường gồm principal và authorities). Nếu có loại identity đặc thù như tenant group hoặc organization, cần chiến lược ánh xạ/duy trì SID hợp lệ và kiểm tra không vượt phạm vi tenant.

**Cảnh báo:** `Sid` không phải session ID, token ID hay chính sách role hierarchy. Nó là đại diện danh tính **để so khớp ACE**.

## 5. Khái niệm 3: `Permission` — được làm thao tác gì?

`Permission` trong Spring Security ACL chủ yếu biểu diễn **bit mask** và ký hiệu hỗ trợ hiển thị. Các hằng chuẩn ở `BasePermission`:

| Hằng `BasePermission` | Bit | Mask thập phân | Ý nghĩa thông dụng |
| --- | ---: | ---: | --- |
| `READ` | 0 | 1 | Đọc nội dung |
| `WRITE` | 1 | 2 | Sửa nội dung |
| `CREATE` | 2 | 4 | Tạo tài nguyên |
| `DELETE` | 3 | 8 | Xóa tài nguyên |
| `ADMINISTRATION` | 4 | 16 | Quản trị quyền |

Ví dụ:

```java
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.Permission;

Permission read = BasePermission.READ;
Permission write = BasePermission.WRITE;

System.out.println(read.getMask());  // 1
System.out.println(write.getMask()); // 2
```

Các giá trị này là **mask quyền**, không phải số thứ tự tài liệu hay người dùng. 32 bit không giới hạn hệ thống chỉ được có 32 đối tượng; mỗi đối tượng có thể có một ACL riêng và nhiều ACE, còn bit mask biểu diễn **loại permission**.

Mặt khác, mask `READ=1` **không tự cấp READ cho bất kỳ ai**. ACE phải liên kết permission đó với một SID trên đúng đối tượng, có `granting=true` hoặc `false`. Permission cũng không tự định nghĩa hiệu lực nghiệp vụ: hệ thống phải thống nhất `READ` nghĩa là xem bản nháp, tải file, hay xuất dữ liệu gì.

`BasePermission` cung cấp năm permission mặc định, nhưng ứng dụng có thể định nghĩa `Permission` tùy chỉnh. Khi dùng bit mask kết hợp, cần kiểm thử chiến lược so khớp (`PermissionGrantingStrategy`) thay vì tự kết luận “mask nào chứa bit thì chắc chắn được grant” cho mọi implementation.

## 6. Khái niệm 4: `AccessControlEntry` — một dòng cấp/từ chối

`AccessControlEntry` (ACE) là một quy tắc nằm trong ACL. Những getter cốt lõi:

```java
AccessControlEntry ace = ...; // Lấy từ acl.getEntries()

ace.getAcl();          // ACL sở hữu ACE
ace.getSid();          // Principal hoặc authority nhận quyền
ace.getPermission();   // Ví dụ BasePermission.READ
ace.isGranting();      // true = cấp, false = từ chối
ace.getId();           // ID ACE, có thể null trước khi lưu
```

Đoạn này **chỉ minh họa API**, không phải chương trình độc lập do `ace` chưa được cấp giá trị.

ACE của document #42 cho Alice đọc có thể hình dung:

```text
ACL   : Document#42
SID   : PrincipalSid("alice")
PERM  : READ (mask = 1)
GRANT : true
```

ACE của Bob là:

```text
ACL   : Document#42
SID   : PrincipalSid("bob")
PERM  : READ (mask = 1)
GRANT : false
```

**Từ chối tường minh** `granting=false` không giống **không có ACE**. Với `DefaultPermissionGrantingStrategy`, một ACE từ chối khớp có thể dẫn đến `isGranted(...) == false`. Không tìm thấy ACE khớp ở ACL hiện tại hoặc ACL cha phù hợp có thể làm `Acl.isGranted` ném `NotFoundException` — caller phải quyết định cách xử lý, thường là **deny/fail closed** trong authorization policy. <https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html>

**Thứ tự ACE có thể có ý nghĩa.** Mô hình Spring ACL có `ace_order`, và chiến lược mặc định tra quyền theo trình tự permission/SID/ACE. Nếu một principal cũng giữ `ROLE_REVIEWER`, hoặc có các ACE trùng nhau/xung đột, kết quả phụ thuộc chiến lược và thứ tự; không tuyên bố “deny luôn thắng” hay “grant luôn thắng” trên mọi policy mà chưa có test cụ thể.

Không sửa trực tiếp `AccessControlEntry` lấy từ `getEntries()`: interface ACE biểu diễn bản ghi bất biến. Muốn thay đổi quy tắc của `MutableAcl`, dùng `insertAce`, `updateAce`, `deleteAce`, sau đó lưu qua `MutableAclService.updateAcl(...)` nếu dùng kho ACL. Phân quyền **ai được sửa ACL** là trách nhiệm của `AclAuthorizationStrategy`, khác với `PermissionGrantingStrategy` dùng khi **kiểm tra quyền truy cập domain object**.

## 7. Khái niệm 5: `Acl` — tập quy tắc của một đối tượng

`Acl` gắn với **một `ObjectIdentity`** và giữ các ACE cần thiết để đánh giá quyền. Những phương thức đáng nhớ:

```java
Acl acl = ...; // Ví dụ đọc từ AclService

ObjectIdentity identity = acl.getObjectIdentity();
Sid aclOwner = acl.getOwner();
java.util.List<AccessControlEntry> localEntries = acl.getEntries();
Acl parent = acl.getParentAcl();
boolean inherit = acl.isEntriesInheriting();
boolean granted = acl.isGranted(
    java.util.List.of(BasePermission.READ),
    java.util.List.of(new PrincipalSid("alice")),
    false
);
```

Đây là **mảnh minh họa API**, không thể chạy độc lập do `acl` chưa được khởi tạo.

- `getObjectIdentity()` nói ACL bảo vệ **đối tượng nào**.
- `getOwner()` trả SID chủ sở hữu ACL. Ý nghĩa quản trị của owner tùy implementation; **owner không tự động được READ/WRITE** mọi domain object nếu không có grant theo chiến lược.
- `getEntries()` trả các ACE **trong ACL hiện tại**, không phải danh sách tự tổng hợp tất cả ACE của cha. Dùng để xem/chỉnh ACL; **không tự duyệt danh sách này để viết quyết định authorization trong business code**.
- `getParentAcl()` và `isEntriesInheriting()` phục vụ liên kết và kế thừa quy tắc từ ACL cha nếu được bật.
- `isGranted(List<Permission>, List<Sid>, boolean administrativeMode)` là API ra quyết định quyền. Tham số `administrativeMode=true` có nghĩa truy vấn quản trị để tránh ghi audit theo hỗ trợ của strategy, **không** phải cờ “bypass security/allow admin”.

Phần cốt lõi của `isGranted` do `PermissionGrantingStrategy` thực hiện, mặc định thường là `DefaultPermissionGrantingStrategy`.

Khi không có ACE phù hợp, một implementation có thể ném `NotFoundException` thay vì tự trả `false`. Khi ACL chỉ tải **một tập con SID**, gọi `isGranted` với SID chưa được tải có thể phát sinh `UnloadedSidException`. Viết policy cần phân loại đúng những kết quả này và ưu tiên **từ chối khi không có quyết định đáng tin**.

### 7.1. ACL cha và thừa kế

Giả sử thư mục #10 có ACL cho phép nhóm `ROLE_STAFF` READ. Tài liệu #42 có `parentAcl` trỏ tới ACL thư mục #10:

- Nếu `entriesInheriting=true`, luật ở cha **có thể được xét** khi ACL con không có ACE match theo chiến lược triển khai.
- Nếu `entriesInheriting=false`, ACL con không nhận quyền cha chỉ vì tồn tại quan hệ cha.
- Một **explicit deny** khớp tại ACL con không được đánh đồng với “không có quy tắc”: chiến lược mặc định thường xử lý quyết định tại con trước khi thử cha.

Cần xác nhận thứ tự ACE, quy tắc kế thừa và quan hệ tenant trong integration test. Không cho phép người dùng tạo cây cha tùy tiện để thừa hưởng quyền của tenant khác.

### 7.2. Trình tự quyết định dễ hình dung

```text
Authentication
  -> các SID tương ứng (principal + authorities)
          |
          v
ObjectIdentity(type, id)
  -> AclService.readAclById(...)
          |
          v
Acl (ACE hiện tại + thông tin parent/inheritance)
          |
          v
Acl.isGranted(permissions, sids, administrativeMode)
  -> PermissionGrantingStrategy
      -> MATCH GRANT   -> true
      -> MATCH DENY    -> false
      -> NO MATCH      -> tra ACL cha nếu đủ điều kiện
                          hoặc NotFoundException
```

Đây là **luồng khái niệm**: một implementation có thể tối ưu cache, batch-load và thứ tự tra cứu. Luôn căn cứ vào `PermissionGrantingStrategy` đang được dùng, không tự giả định mọi strategy có cùng thứ tự.

## 8. Năm khái niệm liên kết với bốn bảng ACL chuẩn như thế nào?

Spring Security ACL có schema quan hệ chuẩn để lưu các quy tắc. Tên bảng thường gặp:

| Bảng | Đối tượng / dữ liệu chính | Tình huống |
| --- | --- | --- |
| `ACL_CLASS` | Loại domain object (class/type) | Lưu một hàng đại diện `demo.Document` |
| `ACL_SID` | Principal hoặc authority | Phân biệt `alice` với `ROLE_REVIEWER`; cờ loại SID |
| `ACL_OBJECT_IDENTITY` | Một instance theo `ACL_CLASS` + ID đối tượng, owner SID, parent và inheritance | ACL của document #42 |
| `ACL_ENTRY` | Từng ACE: object identity, SID, mask, granting, thứ tự, audit | Alice READ grant, Bob READ deny |

Sơ đồ quan hệ:

```text
ACL_CLASS (type)
     |
     v
ACL_OBJECT_IDENTITY (ObjectIdentity instance, owner, parent, inheritance)
     |                                              |
     |                                              v
     |                                        ACL_SID (owner)
     v
ACL_ENTRY (ACE: permission mask, granting, ace_order, audit)
     |
     v
ACL_SID (recipient: principal hoặc authority)
```

Một ACL có thể có nhiều ACE; một ACE chỉ gắn với **một** ACL và **một** SID. Các quy tắc nhiều quyền khác nhau thường là nhiều ACE, nhưng mask cho phép biểu diễn permission theo cách triển khai lựa chọn. Khóa định danh đối tượng trong schema phải ổn định và nhất quán với cách tạo `ObjectIdentity`.

Ví dụ dữ liệu **minh họa** (không phải SQL migration độc lập):

```text
ACL_CLASS:
  id=1, class="demo.Document"

ACL_SID:
  id=11, principal=true, sid="alice"
  id=12, principal=true, sid="bob"
  id=13, principal=false, sid="ROLE_REVIEWER"
  id=14, principal=true, sid="acl-admin"

ACL_OBJECT_IDENTITY:
  id=100, object_id_class=1, object_id_identity=42,
  owner_sid=14, parent_object=NULL, entries_inheriting=false

ACL_ENTRY:
  ace_order=0, acl_object_identity=100, sid=11, mask=1, granting=true
  ace_order=1, acl_object_identity=100, sid=11, mask=2, granting=true
  ace_order=2, acl_object_identity=100, sid=12, mask=1, granting=false
  ace_order=3, acl_object_identity=100, sid=13, mask=1, granting=true
```

**Ba lớp ID đừng nhầm nhau:** ID nghiệp vụ `42` nhận diện Document, ID ACL `100` nhận diện bản ghi `ACL_OBJECT_IDENTITY`, ID SID `11` nhận diện hàng trong `ACL_SID`. Chúng phục vụ những mục đích khác nhau.

Migrations SQL thực tế tùy database, dialect, khóa/cột và Spring Security version. Không lấy bảng minh họa trên để thay cho schema chính thức hay bỏ các ràng buộc duy nhất, foreign key, index và các cột audit cần thiết.

## 9. Ví dụ Java 17+ chạy được: tạo ACL trong bộ nhớ và kiểm thử quyền

Để học **đúng năm kiểu Spring ACL** mà không cần dựng database ngay, ta có thể tạo `AclImpl` trực tiếp trong test với `ObjectIdentityImpl`, `PrincipalSid`, `GrantedAuthoritySid`, `BasePermission`, rồi thêm ACE qua `MutableAcl.insertAce`.

**Giới hạn chủ ý:** đây là test về **ACL model và permission granting strategy**, không có JDBC và không minh họa việc lưu/đọc ACL từ database. Hệ thống production nên tạo/cập nhật ACL qua `MutableAclService` thay vì tự khởi tạo `AclImpl` trong controller/service nghiệp vụ.

### 9.1. Bố cục và dependency

```text
acl-foundations-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AclFoundationsTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'acl-foundations-demo'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.security:spring-security-acl'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-security-acl` chứa các interface và implementation ACL; module kéo theo những phụ thuộc Spring Security cần thiết. JUnit Jupiter chạy test, không cần `@SpringBootTest` hoặc database. Build dùng BOM để không trộn version tùy tiện. **Lưu ý:** cách dùng trực tiếp constructor `AclImpl` phù hợp cho học/test; nên dùng `MutableAclService.createAcl` trong ứng dụng có persistence.

### 9.2. Mã test hoàn chỉnh

Tạo `src/test/java/demo/AclFoundationsTest.java`:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.security.acls.model.NotFoundException;

public class AclFoundationsTest {

    private final Sid alice = new PrincipalSid("alice");
    private final Sid bob = new PrincipalSid("bob");
    private final Sid reviewer =
        new GrantedAuthoritySid("ROLE_REVIEWER");

    private MutableAcl acl;

    @BeforeEach
    void createAcl() {
        // Mutation của ACL cần identity có quyền quản trị ACL.
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "acl-admin",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_ACL_ADMIN"))
            )
        );
        SecurityContextHolder.setContext(context);

        ObjectIdentity objectId =
            new ObjectIdentityImpl("demo.Document", 42L);

        AclAuthorizationStrategyImpl mutationPolicy =
            new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
            );

        acl = new AclImpl(
            objectId,
            100L, // ID giả của bản ghi ACL, không phải Document ID.
            mutationPolicy,
            new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger()
            ),
            null,  // Không có ACL cha.
            null,  // Không giới hạn chỉ một tập con SID được load.
            false, // Không kế thừa ACE từ cha.
            new PrincipalSid("acl-admin") // ACL owner.
        );

        acl.insertAce(0, BasePermission.READ, alice, true);
        acl.insertAce(1, BasePermission.WRITE, alice, true);
        acl.insertAce(2, BasePermission.READ, bob, false);
        acl.insertAce(3, BasePermission.READ, reviewer, true);
    }

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void objectIdentityUsesTypeAndIdentifier() {
        ObjectIdentity anotherDocument42 =
            new ObjectIdentityImpl("demo.Document", 42L);
        ObjectIdentity differentType =
            new ObjectIdentityImpl("demo.Invoice", 42L);

        assertThat(acl.getObjectIdentity())
            .isEqualTo(anotherDocument42)
            .isNotEqualTo(differentType);
        assertThat(acl.getObjectIdentity().getType())
            .isEqualTo("demo.Document");
        assertThat(acl.getObjectIdentity().getIdentifier())
            .isEqualTo(42L);
    }

    @Test
    void sidDistinguishesPrincipalFromAuthority() {
        assertThat(alice).isEqualTo(new PrincipalSid("alice"));
        assertThat(alice).isNotEqualTo(
            new GrantedAuthoritySid("alice")
        );
        assertThat(reviewer).isEqualTo(
            new GrantedAuthoritySid("ROLE_REVIEWER")
        );
    }

    @Test
    void basicPermissionMasksAreDistinct() {
        assertThat(BasePermission.READ.getMask()).isEqualTo(1);
        assertThat(BasePermission.WRITE.getMask()).isEqualTo(2);
        assertThat(BasePermission.CREATE.getMask()).isEqualTo(4);
        assertThat(BasePermission.DELETE.getMask()).isEqualTo(8);
        assertThat(BasePermission.ADMINISTRATION.getMask())
            .isEqualTo(16);
    }

    @Test
    void aceRecordsItsSidPermissionAndGrantFlag() {
        List<AccessControlEntry> entries = acl.getEntries();

        assertThat(entries).hasSize(4);
        AccessControlEntry first = entries.get(0);
        AccessControlEntry denial = entries.get(2);

        assertThat(first.getAcl()).isSameAs(acl);
        assertThat(first.getSid()).isEqualTo(alice);
        assertThat(first.getPermission())
            .isEqualTo(BasePermission.READ);
        assertThat(first.isGranting()).isTrue();

        assertThat(denial.getSid()).isEqualTo(bob);
        assertThat(denial.getPermission())
            .isEqualTo(BasePermission.READ);
        assertThat(denial.isGranting()).isFalse();
    }

    @Test
    void aliceHasReadAndWritePermission() {
        assertThat(acl.isGranted(
            List.of(BasePermission.READ), List.of(alice), true
        )).isTrue();

        assertThat(acl.isGranted(
            List.of(BasePermission.WRITE), List.of(alice), true
        )).isTrue();
    }

    @Test
    void bobHasExplicitReadDenial() {
        assertThat(acl.isGranted(
            List.of(BasePermission.READ), List.of(bob), true
        )).isFalse();
    }

    @Test
    void reviewerAuthorityCanRead() {
        assertThat(acl.isGranted(
            List.of(BasePermission.READ), List.of(reviewer), true
        )).isTrue();
    }

    @Test
    void missingRuleThrowsNotFoundInsteadOfReturningFalse() {
        assertThatThrownBy(() -> acl.isGranted(
            List.of(BasePermission.DELETE), List.of(alice), true
        )).isInstanceOf(NotFoundException.class);
    }

    @Test
    void aclOwnerAndContentPermissionAreDifferentConcepts() {
        assertThat(acl.getOwner())
            .isEqualTo(new PrincipalSid("acl-admin"));
        assertThat(acl.getObjectIdentity())
            .isEqualTo(new ObjectIdentityImpl("demo.Document", 42L));
        assertThat(acl.getParentAcl()).isNull();
        assertThat(acl.isEntriesInheriting()).isFalse();
    }
}
```

**Giải thích các lựa chọn quan trọng:**

1. Đây là **class test Java 17 hoàn chỉnh** gồm chín ca `@Test`. `@BeforeEach` tạo ACL mới cho mỗi test, nên thay đổi trong test này không ảnh hưởng test kia.
2. `AclImpl` là triển khai cụ thể của `MutableAcl`, giúp thêm ACE qua `insertAce(index, permission, sid, granting)`. Chỉ có `Acl` sẽ phục vụ việc đọc/kiểm tra, không biểu thị API cập nhật.
3. `AclAuthorizationStrategyImpl` kiểm soát **quyền sửa ACL**. Test thiết lập authentication `acl-admin` có `ROLE_ACL_ADMIN` để hành động `insertAce` có quyền; role này **không** tự là permission READ đối với document.
4. `DefaultPermissionGrantingStrategy` quyết định nội dung của `isGranted`; `ConsoleAuditLogger` được truyền vào constructor. Tham số `administrativeMode=true` trong test tắt auditing của truy vấn khi strategy hỗ trợ, tránh làm log test lẫn với output.
5. `ObjectIdentityImpl("demo.Document",42L)` là identity tài liệu; số `100L` trong constructor ACL là ID của chính bản ghi ACL test, không phải ID tài liệu.
6. `getEntries()` được dùng **chỉ để kiểm tra metadata ACE**, còn tất cả quyết định cấp/từ chối đều dùng `isGranted`. Đây là cách dùng đúng theo hợp đồng của `Acl`.
7. `NotFoundException` khi hỏi Alice `DELETE` là **không có ACE phù hợp**, khác với ACE `bob/READ/deny` trả `false`.
8. `@AfterEach` xóa `SecurityContextHolder` để không làm bẩn authentication của test khác. Trường hợp thực tế nên giới hạn quyền cập nhật ACL ở service quản trị, không công bố công khai khả năng sửa ACE.

### 9.3. Chạy test và kiểm tra kết quả

Tại thư mục chứa `build.gradle`:

```bash
gradle test --tests demo.AclFoundationsTest
```

Nếu có Gradle Wrapper: trên Linux/macOS `./gradlew test --tests demo.AclFoundationsTest`; Windows `gradlew.bat test --tests demo.AclFoundationsTest`.

**Kỳ vọng khi môi trường đúng:** cả **9 test** thành công, Gradle kết thúc `BUILD SUCCESSFUL`. Đây là **kỳ vọng từ mã ví dụ**, không phải stdout ghi lại từ một lần thực thi. Kết quả chi tiết của JUnit nằm ở `build/reports/tests/test/index.html`.

| Test | Điều xác minh |
| --- | --- |
| `objectIdentityUsesTypeAndIdentifier` | Type + ID phân biệt đúng tài nguyên |
| `sidDistinguishesPrincipalFromAuthority` | SID người và SID authority khác nhau |
| `basicPermissionMasksAreDistinct` | Các mask permission chuẩn |
| `aceRecordsItsSidPermissionAndGrantFlag` | ACE thực sự chứa SID, permission và granting |
| `aliceHasReadAndWritePermission` | Alice READ/WRITE có grant |
| `bobHasExplicitReadDenial` | Bob READ bị deny tường minh |
| `reviewerAuthorityCanRead` | Nhóm REVIEWER có grant |
| `missingRuleThrowsNotFoundInsteadOfReturningFalse` | Không có ACE khớp khác explicit deny |
| `aclOwnerAndContentPermissionAreDifferentConcepts` | ACL owner, ObjectIdentity, parent/inherit |

Nếu test lỗi vì Spring Security version khác, kiểm tra phiên bản `spring-security-acl` được resolve bằng `gradle dependencies --configuration testRuntimeClasspath`; không tự đổi assertion cho vừa với một hành vi bảo mật chưa hiểu.

## 10. Liên hệ với service và SpEL `hasPermission`

Thông thường, bạn không tự tạo `AclImpl` trong mỗi request. Các thành phần liên kết thực tế:

```text
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
              |
              v
MethodSecurityExpressionHandler
   + PermissionEvaluator / AclPermissionEvaluator
              |
              v
AclService.readAclById(ObjectIdentity, Sids)
              |
              v
LookupStrategy + AclCache + JDBC database
              |
              v
Acl.isGranted(permissions, sids, administrativeMode)
```

Đây là **sơ đồ ý tưởng**. Cách map chuỗi `'READ'` sang `BasePermission.READ`, cũng như map `'demo.Document'` sang `ObjectIdentity`, phụ thuộc vào evaluator/`PermissionFactory` đang được cấu hình. Không coi mọi literal SpEL tự động tương đương một constant `BasePermission`.

### 10.1. Đọc ACL

Ví dụ API minh họa:

```java
// Phụ thuộc AclService do ứng dụng cấu hình.
ObjectIdentity objectId =
    new ObjectIdentityImpl("demo.Document", 42L);

Acl acl = aclService.readAclById(objectId);
boolean allowed = acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("alice")),
    false
);
```

Đây là **mảnh tích hợp**, không phải chương trình độc lập: cần khai báo `AclService`, database, schema, lookup strategy, caching và exception handling trước khi dùng. `AclService` là API **đọc ACL**, còn `MutableAclService` hỗ trợ tạo, cập nhật và xóa ACL có persistence. `JdbcAclService` và các implementation tương ứng sử dụng `LookupStrategy`/SQL để đọc ACL hiệu quả.

### 10.2. Cập nhật ACL theo đường quản trị

Ví dụ luồng tổng quát:

```java
ObjectIdentity objectId =
    new ObjectIdentityImpl("demo.Document", 42L);

// Cần dependency MutableAclService do ứng dụng cấu hình,
// authentication có quyền thay đổi ACL và transaction phù hợp.
MutableAcl acl = mutableAclService.createAcl(objectId);

acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    new PrincipalSid("alice"),
    true
);

mutableAclService.updateAcl(acl);
```

Đây cũng là **mảnh tích hợp**, giả định ACL chưa tồn tại (nếu đã tồn tại `createAcl` có thể báo trùng); nếu cập nhật ACL cũ cần đọc ACL đó trước. Mọi thay đổi ACL phải đi qua **quyền quản trị**, transaction, auditing và cache invalidation phù hợp. Không cho phép client tự chọn SID/permission/target type rồi ghi vào ACL nếu chưa được ủy quyền.

### 10.3. `@PreAuthorize` và thời điểm bảo vệ

Ví dụ một method đọc tài liệu:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document read(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

Mảnh minh họa này cần `Document`, `repository`, `@P`, evaluator/handler và `@EnableMethodSecurity` được cấu hình trong ứng dụng thật. Nếu policy cho phép, Spring AOP đi vào body; nếu deny, body không được chạy. Quan trọng: `hasPermission` chỉ hoạt động nếu **đúng PermissionEvaluator được đăng ký với expression handler** và có thể đọc đúng ACL.

Đối với việc ghi/xóa dữ liệu, ưu tiên kiểm tra quyền **trước side effect**. Với `@PostAuthorize` kiểm tra object sau khi method trả, cần chú ý phần thân method **đã chạy**; không dùng after check làm chốt duy nhất để ngăn thay đổi trạng thái.

## 11. Các lỗi học và áp dụng thường gặp

| Hiện tượng/hiểu nhầm | Vì sao sai | Cách kiểm tra |
| --- | --- | --- |
| “`Acl` chính là entity `Document`” | ACL chỉ mang identity và rules, không phải dữ liệu tài liệu | So sánh `ObjectIdentity` và entity |
| “`Sid` là session ID” | SID là security identity của principal/authority | Dùng `PrincipalSid`/`GrantedAuthoritySid` |
| “`ObjectIdentity` chỉ là một ID số” | Type + ID cần phân biệt tài liệu và hóa đơn có ID 42 | Test cùng ID nhưng khác type |
| “`getOwner()` luôn được READ” | ACL owner chủ yếu liên quan quyền quản trị theo strategy, không tự là ACE READ | Test cả owner và ACE khi cần |
| “Có role VIEWER thì mọi tài liệu đều đọc được” | ACL phải có ACE tương ứng cho đúng ObjectIdentity | Test tài liệu được grant và tài liệu khác |
| “Không có ACE = deny ACE” | No match có thể ném `NotFoundException`; deny ACE khớp có thể trả false | Test hai tình huống riêng |
| “`getEntries()` đủ để tự viết policy” | Có thứ tự, cache, inheritance, partial SID load và strategy | Dùng `Acl.isGranted`/`PermissionEvaluator` |
| “Thứ tự ACE không quan trọng” | Chiến lược mặc định có thể ưu tiên kết quả khớp đầu tiên theo thứ tự | Test xung đột SID/permission |
| “Có parent ACL là tự kế thừa” | `isEntriesInheriting()` điều khiển inheritance | Test true và false |
| “Mask 1 là tài liệu ID 1” | Mask biểu diễn permission READ, không phải resource ID | Dùng `getMask()` và `ObjectIdentity` |
| “Lưu ACL không cần permission admin” | Sửa ACL phải được bảo vệ riêng | Kiểm tra `AclAuthorizationStrategy` |
| “Truy vấn không thấy ACL có nghĩa luôn cho phép” | Đó có thể là trạng thái thiếu rule, lỗi đồng bộ/cache hoặc sai ObjectIdentity | Fail closed; ghi audit phù hợp |
| “Gắn `hasPermission` là xong” | Phải có evaluator, handler, AclService, proxy và scope đúng | Integration test direct + denied path |
| “Đổi role là quyền ACL cập nhật ngay tức thì” | SID/authority và cache ACL cần được refresh/invalidate đúng | Test thay đổi grant/revoke và cache |

### 11.1. Một số trường hợp cần test riêng

**Tài liệu khác:** `demo.Document#42` đã grant Alice READ không có nghĩa `demo.Document#43` cũng grant; hai đối tượng có `ObjectIdentity` khác nhau.

**Trùng ID giữa loại domain:** `demo.Invoice#42` không được dùng ACL của `demo.Document#42`.

**Thay đổi role:** nếu một user bị gỡ `ROLE_REVIEWER`, danh sách SID dùng để kiểm tra phải được cập nhật theo authentication mới, và các cache liên quan không được trả quyền cũ.

**Một người có nhiều SID:** một principal có thể nhận grant/deny qua SID cá nhân và role. Khi luật xung đột, kiểm tra `PermissionGrantingStrategy`, **thứ tự danh sách SIDs/permissions** và dữ liệu ACE. Không áp đặt “deny-overrides” như quy tắc bất biến nếu chưa cấu hình và kiểm chứng.

**Tập SID nạp thiếu:** `Acl.isSidLoaded(sids)` cho biết ACL hiện tại có dữ liệu cho các SID cần kiểm tra hay không. Nếu chưa nạp đủ, không diễn giải `UnloadedSidException` thành “allow”.

**Thừa kế ACL:** nếu cha cho READ nhưng ACL con có explicit deny, cần test theo chiến lược cụ thể. Nếu tắt inheritance, chỉ có rule ở cha không đủ để grant con.

**Hiệu năng:** việc kiểm tra quyền cho hàng nghìn đối tượng có thể dẫn tới nhiều lần tra cứu ACL. `BasicLookupStrategy`, batch loading và `AclCache` hỗ trợ tối ưu; tuy nhiên cache phải có chính sách invalidation mỗi khi thay đổi ACE/ACL hoặc SID liên quan.

## 12. Bài tập củng cố

1. **Đọc sơ đồ:** Với document #42 và bốn ACE ở đầu bài, viết kết quả `READ/WRITE/DELETE` cho Alice, Bob và REVIEWER. Phân biệt `false` với `NotFoundException`.
2. **Đổi đối tượng:** Tạo ACL khác cho `ObjectIdentityImpl("demo.Document", 43L)`, chỉ grant Bob READ. Chứng minh việc này không thay đổi quyền của Document #42.
3. **Grant và revoke:** Thử `deleteAce` hoặc `updateAce` qua `MutableAcl` trên một ACE và kiểm tra lại `isGranted`. Trong môi trường có database, lưu qua `MutableAclService` và xác minh cache được cập nhật.
4. **Role và principal:** Tạo user có cả `PrincipalSid("bob")` và `GrantedAuthoritySid("ROLE_REVIEWER")`. Đọc strategy mặc định và viết test thứ tự SID nếu grant/deny xung đột.
5. **ACL cha:** Tạo parent ACL grant READ cho `ROLE_STAFF`, gắn cho child rồi bật/tắt `setEntriesInheriting(true/false)`. Test quy tắc fallback khi con thiếu ACE.
6. **Multi-tenant:** Đề xuất chiến lược ObjectIdentity/type/ID, ownership, database query và cache key giúp tài liệu ID 42 của tenant A không bị nhầm với tenant B.
7. **Permission riêng:** Tạo permission `APPROVE` bằng cách triển khai `Permission` có mask không trùng, bổ sung ACE và test strategy hiểu đúng mask.

## 13. Checklist trước khi thiết kế ACL trong ứng dụng thật

- [ ] **ObjectIdentity:** type/ID ổn định, nhất quán giữa tạo và đọc, không nhầm tenant.
- [ ] **Sid:** xác định rõ principal/role/group; không tin dữ liệu danh tính client tự gửi.
- [ ] **Permission:** mô tả ngữ nghĩa READ/WRITE/DELETE rõ ràng, mask không trùng, test permission riêng nếu có.
- [ ] **ACE:** ghi rõ granting hay denial, thứ tự, audit và rule xung đột có test.
- [ ] **Acl:** owner, parent/inheritance và quyền quản trị ACL có chính sách độc lập.
- [ ] **Persistence:** có schema/migrations, transaction, `AclService`/`MutableAclService`, `LookupStrategy`, cache và invalidation.
- [ ] **Method security:** `PermissionEvaluator` đăng ký đúng, test trực tiếp `hasPermission` trên Spring proxy với principal khác nhau.
- [ ] **Fail closed:** no rule/not found/unloaded SID/database error không bao giờ âm thầm biến thành allow.
- [ ] **Audit:** ghi được ai sửa ACL, khi nào, vì sao; không lộ dữ liệu nhạy cảm khi log.
- [ ] **Performance:** thử tải với nhiều object, nhiều ACE, nhiều SID và phân trang lớn.

## 14. Tổng kết

Có thể ghi nhớ theo một câu:

> **`ObjectIdentity`** chỉ rõ *đối tượng nào*; **`Sid`** chỉ rõ *ai*; **`Permission`** chỉ rõ *được làm gì*; **`AccessControlEntry`** nối ba thông tin đó thành quy tắc *grant/deny*; **`Acl`** tập hợp quy tắc cho đối tượng và dùng chiến lược để quyết định quyền.

Muốn kiểm tra quyền chính xác, đi từ identity của đúng đối tượng, lấy đúng ACL, xây đúng SID và permission rồi gọi `Acl.isGranted(...)` hoặc `PermissionEvaluator` đã kết nối với ACL infrastructure. **Không có quy tắc**, **bị deny tường minh** và **có grant** phải được phân biệt trong thiết kế/test.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Domain Object Security (ACLs), mô hình và bốn bảng: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 API — `Acl`, `isGranted`, parent, loaded SID: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security 6.5 API — `AclImpl`, `insertAce` và constructor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html
- Spring Security 6.5 API — `DefaultPermissionGrantingStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html
- Spring Security API — `AccessControlEntry`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AccessControlEntry.html
- Spring Security API — `ObjectIdentity`, `Sid`, `Permission`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/package-summary.html
