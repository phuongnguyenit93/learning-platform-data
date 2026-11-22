# BasePermission, permission mask và quyền tùy chỉnh trong Spring Security ACL

## 1. Bài toán và phạm vi

Trong hệ thống quản lý tài liệu, Alice có thể xem tài liệu số 42 nhưng không được xóa; Bob có thể xuất PDF của tài liệu số 42 nhưng không được duyệt. Kiểm tra `hasAuthority('EDITOR')` chỉ cho biết một authority chung, còn câu hỏi “người nào có quyền gì **trên đúng tài liệu này**” cần mô hình phân quyền theo resource.

**ACL (Access Control List)** trong Spring Security gắn các mục **ACE (Access Control Entry)** vào từng đối tượng. Mỗi ACE nói một **SID** (người dùng/authority) được *cấp* hay *từ chối* một **Permission** trên một **ObjectIdentity** cụ thể. `BasePermission` cung cấp năm permission phổ biến, được biểu diễn bằng bitmask.

Mục tiêu học tập:

1. Hiểu Permission, BasePermission, permission mask, SID, ACL và ACE.
2. Nhớ chính xác READ=1, WRITE=2, CREATE=4, DELETE=8, ADMINISTRATION=16.
3. Thực hành bitwise OR/AND/NOT và kiểm tra tập bit mà không nhầm với kết quả authorization.
4. Tạo quyền ứng dụng như EXPORT=32, APPROVE=64, tránh đè bit.
5. Biết dùng `CumulativePermission`, `PermissionFactory`, `AclPermissionEvaluator` và `hasPermission`.
6. Hiểu vì sao grant/deny, ACL inheritance, thứ tự permission/SID và granting strategy không thể chỉ suy ra từ số mask.
7. Kiểm thử toàn bộ vòng đời lưu ACE, đọc lại ACL, phân quyền và thu hồi quyền.

Đây là bài về **Spring Security ACL**, không phải quyền hệ điều hành, JWT scopes hay danh sách `GrantedAuthority` nói chung. Ứng dụng chỉ cần vài role và quyền theo tenant có thể chưa cần triển khai hệ thống ACL đầy đủ.

## 2. Mô hình ACL: ai, tài nguyên nào, quyền gì?

```text
Authentication:
  name = alice
  authorities = ROLE_EDITOR, DOC_READ
        |
        v
Sid (Security Identity):
  PrincipalSid("alice")
  GrantedAuthoritySid("ROLE_EDITOR")
        |
        v
ObjectIdentity:
  type = com.acme.Document
  id   = 42
        |
        v
ACL của Document 42:
  ACE Alice       READ   mask=1   granting=true
  ACE Alice       WRITE  mask=2   granting=false
  ACE ROLE_EDITOR EXPORT mask=32  granting=true
        |
        v
PermissionGrantingStrategy:
  đánh giá các ACE/SID, grant/deny, ACL cha, permission...
        |
        v
Quyết định cho phép/từ chối
```

| Khái niệm | Chức năng |
| --- | --- |
| `Permission` | Đối tượng biểu diễn quyền bằng mask và mã hiển thị |
| `BasePermission` | Các quyền chuẩn của ACL |
| `Sid` | Danh tính principal hoặc một granted authority |
| `ObjectIdentity` | Danh tính một tài nguyên theo loại + ID |
| `Acl` | Thông tin ACL cho object, danh sách ACE, owner, parent |
| `AccessControlEntry` | SID nào được grant/deny permission nào |
| `AclService` | Đọc ACL |
| `MutableAclService` | Tạo, cập nhật, xóa ACL |
| `PermissionGrantingStrategy` | Tính kết quả dựa trên nhiều ACE/SID |
| `PermissionFactory` | Chuyển tên hoặc mask thành Permission |

**Phân biệt:** `ROLE_EDITOR` là thông tin authority của user; `BasePermission.WRITE` là quyền trên một object ACL. `hasRole('EDITOR')` và `hasPermission(#id, 'com.acme.Document', 'WRITE')` không phải một phép kiểm tra.

Các lớp liên quan nằm trong `org.springframework.security.acls.domain` và `org.springframework.security.acls.model`. Thư viện Spring ACL cần dependency riêng `org.springframework.security:spring-security-acl`; không tự có mọi thứ chỉ bởi vì đã bật `spring-boot-starter-security`.

## 3. Năm quyền BasePermission mặc định

| Quyền | Bit index từ 0 | Dịch bit | Decimal mask | Binary (8 bit cuối) |
| --- | ---: | --- | ---: | --- |
| `BasePermission.READ` | 0 | `1 << 0` | **1** | `0000 0001` |
| `BasePermission.WRITE` | 1 | `1 << 1` | **2** | `0000 0010` |
| `BasePermission.CREATE` | 2 | `1 << 2` | **4** | `0000 0100` |
| `BasePermission.DELETE` | 3 | `1 << 3` | **8** | `0000 1000` |
| `BasePermission.ADMINISTRATION` | 4 | `1 << 4` | **16** | `0001 0000` |

Đọc giá trị bằng Java:

```java
import org.springframework.security.acls.domain.BasePermission;

int read = BasePermission.READ.getMask();                // 1
int write = BasePermission.WRITE.getMask();              // 2
int create = BasePermission.CREATE.getMask();            // 4
int delete = BasePermission.DELETE.getMask();            // 8
int administration = BasePermission.ADMINISTRATION.getMask(); // 16
```

**Nhớ hai điều:**

- Mask có số lớn hơn **không có nghĩa quyền cao hơn**. ADMINISTRATION=16 là bit khác READ=1. Nó **không tự** bao hàm READ/WRITE/DELETE. Nếu admin được nhiều hành động, policy/ACE phải quy định và test rõ ràng.
- “32-bit permission mask” **không** có nghĩa chỉ được quản lý 32 tài liệu. Mỗi bit đại diện một loại quyền; số tài liệu được biểu diễn bởi các hàng `ObjectIdentity`/`ACL_OBJECT_IDENTITY`, có thể rất lớn.

`CREATE` cũng không tự định nghĩa quyền tạo một tài liệu *chưa tồn tại*. Thường cần quyết định xem quyền tạo sẽ gắn vào folder/project cha hay một method-security policy khác.

## 4. Tính toán mask bằng các toán tử bitwise

### 4.1. Dịch trái: `1 << n`

```java
int READ = 1 << 0;      // 1
int WRITE = 1 << 1;     // 2
int CREATE = 1 << 2;    // 4
int DELETE = 1 << 3;    // 8
int ADMIN = 1 << 4;     // 16
int EXPORT = 1 << 5;    // 32 (quyền mới)
int APPROVE = 1 << 6;   // 64 (quyền mới)
```

Các bit riêng không giao nhau. Hai permission nghiệp vụ không được cấp cùng một bit nếu cùng được diễn giải trong một namespace ACL.

### 4.2. OR `|`: ghép các bit

```java
int combined = READ | WRITE | EXPORT; // 1 | 2 | 32 = 35
// binary: 0010 0011
```

Phép OR tạo một **mask tổ hợp**. Nó chưa tạo ACE và chưa cấp quyền cho bất cứ ai.

### 4.3. AND `&`: kiểm tra bit

```java
boolean read = (combined & READ) == READ;            // true
boolean export = (combined & EXPORT) == EXPORT;      // true
boolean approve = (combined & APPROVE) == APPROVE;   // false
```

Nếu yêu cầu **tất cả** bit trong mask:

```java
static boolean includesAll(int granted, int required) {
    return required != 0 && (granted & required) == required;
}
```

Nếu yêu cầu **ít nhất một** bit:

```java
static boolean includesAny(int granted, int required) {
    return required != 0 && (granted & required) != 0;
}
```

Ví dụ chỉ có READ, yêu cầu READ|EXPORT: includesAll=false, includesAny=true. AND và OR chính sách khác nhau; không thể thay thế tùy tiện.

**Bẫy required=0:** biểu thức `(granted & 0) == 0` sẽ luôn true. Nếu mask 0 không biểu diễn quyền hợp lệ, phải từ chối rõ.

### 4.4. Tắt bit bằng `& ~`

```java
int withoutWrite = combined & ~WRITE; // 35 & ~2 = 33
```

Ngược lại, `combined ^ WRITE` là phép **XOR (toggle)**, sẽ bật WRITE nếu bit đang tắt. Không dùng XOR làm hành động thu hồi quyền vì có thể vô tình cấp quyền.

Những phép toán này chỉ sửa biến `int` trong Java. Với ACL thật, thu hồi grant phải cập nhật/xóa ACE thông qua `MutableAclService`; **mask Java đã đổi không tự sửa bảng database**.

### 4.5. Bit cao và kiểu int có dấu

Mask là `int` 32-bit. `1 << 31` có bit dấu và có thể hiển thị thành số âm. Dấu âm/dương **không thể hiện grant hay deny**: ACE có cờ `granting` riêng. Hãy quản lý các bit được cấp phát và kiểm thử lưu/đọc trong DB khi cần dùng bit cao.

## 5. Ví dụ Java 17 thuần, chạy được bằng javac/java

Tệp `PermissionMaskLab.java`:

```java
public final class PermissionMaskLab {

    private static final int READ = 1 << 0;
    private static final int WRITE = 1 << 1;
    private static final int CREATE = 1 << 2;
    private static final int DELETE = 1 << 3;
    private static final int ADMINISTRATION = 1 << 4;
    private static final int EXPORT = 1 << 5;
    private static final int APPROVE = 1 << 6;

    private PermissionMaskLab() {}

    private static boolean includesAll(int granted, int required) {
        return required != 0 && (granted & required) == required;
    }

    private static boolean includesAny(int granted, int required) {
        return required != 0 && (granted & required) != 0;
    }

    public static void main(String[] args) {
        System.out.println("Base: "
                + READ + "," + WRITE + "," + CREATE + ","
                + DELETE + "," + ADMINISTRATION);

        int mask = READ | WRITE | EXPORT;
        System.out.println("combined=" + mask);
        System.out.println("read=" + includesAll(mask, READ));
        System.out.println("approve=" + includesAll(mask, APPROVE));
        System.out.println("readAndExport="
                + includesAll(mask, READ | EXPORT));
        System.out.println("readOrApprove="
                + includesAny(mask, READ | APPROVE));

        mask = mask & ~WRITE;
        System.out.println("afterRevokeWrite=" + mask);
        System.out.println("writeAfterRevoke="
                + includesAll(mask, WRITE));
        System.out.println("maskZeroAllowed="
                + includesAll(mask, 0));
    }
}
```

Tại thư mục chứa tệp, dùng JDK 17+:

```bash
javac PermissionMaskLab.java
java PermissionMaskLab
```

Stdout chính xác:

```text
Base: 1,2,4,8,16
combined=35
read=true
approve=false
readAndExport=true
readOrApprove=true
afterRevokeWrite=33
writeAfterRevoke=false
maskZeroAllowed=false
```

Sau OR mask là 35 (READ+WRITE+EXPORT). Xóa WRITE còn 33 (READ+EXPORT). Hàm includesAll có điều kiện chặn mask 0. Đây là bài toán bit thuần Java **không phải** thuật toán của Spring `Acl.isGranted`.

## 6. Tạo quyền tùy chỉnh bằng BasePermission

Giả sử nghiệp vụ có:

- EXPORT: tạo PDF/CSV.
- APPROVE: phê duyệt tài liệu.
- PUBLISH: công bố tài liệu.

Giữ các bit 0–4 cho `BasePermission`, chọn bit 5 cho EXPORT (32), bit 6 cho APPROVE (64). `BasePermission` có constructor `protected BasePermission(int mask, char code)`, nên có thể subclass.

`DocumentPermission.java`:

```java
package com.acme.security;

import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.Permission;

public final class DocumentPermission extends BasePermission {

    public static final Permission EXPORT =
            new DocumentPermission(1 << 5, 'E');

    public static final Permission APPROVE =
            new DocumentPermission(1 << 6, 'P');

    private DocumentPermission(int mask, char code) {
        super(mask, code);
    }
}
```

Đây là mã cho một ứng dụng có dependency `spring-security-acl`, không phải `javac` độc lập. Ký tự `'E'`/`'P'` được dùng để biểu diễn bit khi hiển thị `getPattern()`. **Nó không phải giá trị lưu trữ permission trong ACL_ENTRY**, và không tự ánh xạ tên string `"EXPORT"` trong biểu thức.

### Permission registry cần nhất quán

| Mask | Ý nghĩa |
| ---: | --- |
| 1 | READ |
| 2 | WRITE |
| 4 | CREATE |
| 8 | DELETE |
| 16 | ADMINISTRATION |
| 32 | EXPORT |
| 64 | APPROVE |
| 128 | PUBLISH, nếu dự án cấp phát |

Không dùng cùng mask cho EXPORT và APPROVE. Nếu hai quyền cùng mask 32, DB không có thông tin để phân biệt. Không đổi mask tùy ý sau khi ACL đã lưu: nếu EXPORT từ 32 chuyển sang 128, các ACE cũ vẫn là 32, phải có migration.

Một cách tổ chức tốt là tập trung permission constants trong module dùng chung và có unit test phát hiện hai quyền khác tên trùng mask. Với nhiều domain type cùng sử dụng ACL infrastructure, cần quy định rõ permission bit mang nghĩa toàn hệ thống hay theo domain, không tái sử dụng mập mờ.

## 7. CumulativePermission và ý nghĩa của mask tổ hợp

Spring Security ACL có `CumulativePermission` để bật/tắt các bit permission:

```java
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.CumulativePermission;

CumulativePermission permission = new CumulativePermission()
        .set(BasePermission.READ)
        .set(DocumentPermission.EXPORT);

int mask = permission.getMask();  // 33
permission.clear(BasePermission.READ);
int remaining = permission.getMask(); // 32
```

`set` bật bit và `clear` tắt bit trong đối tượng Permission. Nó không tạo/xóa ACE trong DB.

Phân biệt:

```java
// Một Permission với mask 33.
Permission combined = new CumulativePermission()
        .set(BasePermission.READ)
        .set(DocumentPermission.EXPORT);

// Hai Permission tách biệt, theo thứ tự.
List<Permission> separate =
        List.of(BasePermission.READ, DocumentPermission.EXPORT);
```

Một mask 33 **không tự có nghĩa** mỗi lệnh check READ hoặc EXPORT sẽ được grant; còn phụ thuộc `PermissionGrantingStrategy`. Ngược lại, danh sách hai permission cũng **không mặc nhiên có nghĩa bắt buộc có cả hai**: logic `isGranted` cấp thấp xét permission/SID theo strategy và thứ tự.

Muốn nghiệp vụ yêu cầu **READ và EXPORT** phải viết chính sách rõ, chẳng hạn hai phép kiểm tra độc lập kết hợp AND tại service/policy, hoặc chiến lược ACL tùy chỉnh có semantics và test đầy đủ.

## 8. PermissionFactory: liên kết tên quyền, mask và đối tượng

Trong biểu thức:

```java
@PreAuthorize("hasPermission(#p0, 'com.acme.Document', 'EXPORT')")
public byte[] export(long id) { /* ... */ }
```

`"EXPORT"` là một **tên quyền**. `PermissionFactory` phải biết nó trỏ đến `DocumentPermission.EXPORT`. `DefaultPermissionFactory()` mặc định nhận các quyền công khai trên `BasePermission`; quyền riêng cần đăng ký.

```java
import java.util.Map;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.DefaultPermissionFactory;
import org.springframework.security.acls.domain.PermissionFactory;
import org.springframework.security.acls.model.Permission;

PermissionFactory factory = new DefaultPermissionFactory(
        Map.<String, Permission>of(
            "READ", BasePermission.READ,
            "WRITE", BasePermission.WRITE,
            "CREATE", BasePermission.CREATE,
            "DELETE", BasePermission.DELETE,
            "ADMINISTRATION", BasePermission.ADMINISTRATION,
            "EXPORT", DocumentPermission.EXPORT,
            "APPROVE", DocumentPermission.APPROVE
        ));

int exportMask = factory.buildFromName("EXPORT").getMask(); // 32
int restored = factory.buildFromMask(32).getMask();          // 32
```

Đoạn tích hợp này giả định `DocumentPermission` đã được import. Các API cơ bản:

- `buildFromName(name)`: đổi tên thành Permission.
- `buildFromMask(mask)`: đổi mask thành Permission.
- `buildFromNames(names)`: đổi danh sách tên thành danh sách Permission.

Trong ACL JDBC, factory có thể được dùng ở **hai vị trí**:

1. `AclPermissionEvaluator.setPermissionFactory(factory)` khi xử lý tên quyền được truyền qua `hasPermission`.
2. `BasicLookupStrategy.setPermissionFactory(factory)` để xây permission object khi đọc dữ liệu từ DB.

Cần đồng bộ cả hai nếu ứng dụng tùy biến permission mapping. Test sau khi persist/reload để chắc chắn quyền custom không mất ý nghĩa khi đi qua các lớp.

**Lỗi phổ biến:** viết `"Export"` trong SpEL trong khi registry chỉ đăng ký `"EXPORT"`. Không giả định không phân biệt chữ hoa/thường.

## 9. Cờ granting và mask trong ACL_ENTRY là hai trường khác nhau

Một ACE có thể là:

```text
ObjectIdentity: com.acme.Document #42
SID: alice
MASK: 32
GRANTING: true
Ý nghĩa: Alice được phép EXPORT tài liệu 42
```

Một ACE khác:

```text
ObjectIdentity: com.acme.Document #42
SID: bob
MASK: 32
GRANTING: false
Ý nghĩa: Bob bị từ chối EXPORT tài liệu 42
```

Mask 32 giống nhau. Chính `GRANTING` mới phân biệt grant/deny. Đừng xét `mask > 0` và cho qua.

Spring ACL JDBC thường có bốn bảng:

| Bảng | Vai trò |
| --- | --- |
| `ACL_CLASS` | Định danh loại class/domain object |
| `ACL_SID` | SID người dùng hoặc authority |
| `ACL_OBJECT_IDENTITY` | Một instance resource, owner, parent và inheritance |
| `ACL_ENTRY` | Các entry: object, SID, mask, granting, audit, thứ tự |

`PermissionGrantingStrategy` xét một permission yêu cầu với các ACE của SID theo quy tắc framework. Theo JavaDoc `DefaultPermissionGrantingStrategy`, thứ tự danh sách permissions và SIDs rất quan trọng; cơ chế mask match mặc định được mô tả theo việc đối chiếu mask của ACE với permission. Không tự thay bằng `(aceMask & requested) != 0` ở mọi nơi mà không nghĩ tới deny, inheritance và ordering.

### Composite mask có được mặc định tách thành các quyền đơn lẻ?

**Không nên giả định.** Một ACE grant mask 33 (READ|EXPORT) không mặc nhiên tương đương hai ACE grant mask 1 và 32 khi kiểm tra qua `Acl.isGranted` trong mọi configuration. Cần test với chính `PermissionGrantingStrategy` đang được cấu hình. Trong trường hợp muốn kiểm tra từng quyền riêng, dùng các ACE riêng có mask đơn lẻ thường rõ ràng hơn.

### Không có ACE không có nghĩa được phép

Ba tình huống:

1. ACE explicit deny cho đúng SID/permission.
2. Không có ACE khớp ở object hiện tại (có thể còn xem ACL cha theo policy).
3. Không tồn tại ACL của object.

Cả ba không phải lý do cho phép. Có thể xử lý thiếu ACL/DB lỗi bằng deny hoặc exception thích hợp, nhưng **không fail-open**.

## 10. ACL inheritance và quyền tùy chỉnh

ACL của resource có thể có parent và `entriesInheriting`. Một document có thể nhận chính sách từ folder cha khi cấu hình phù hợp. Quyền EXPORT trên parent có tự áp dụng cho child không? Cần xem:

- ObjectIdentity của parent và child.
- `Acl.isEntriesInheriting()` ở child.
- ACE thuộc SID nào và granting true/false.
- `PermissionGrantingStrategy` mặc định hay đã tùy biến.
- Các quyền khác như ADMINISTRATION hoặc WRITE có ACE riêng không.

Không kết luận “deny luôn thắng mọi grant” hoặc “ACE con luôn thắng parent” mà không kiểm tra strategy/thứ tự thực tế. Với nhiều SIDs (principal + roles), thứ tự kiểm tra là một phần quan trọng của bài toán.

Khi resource chuyển folder, đổi owner hoặc tenant, parent ACL/cache có thể cần cập nhật. Một tài liệu ID 42 của tenant A và tài liệu ID 42 của tenant B không được dùng nhầm cùng ObjectIdentity; hệ thống phải bảo đảm identity đủ duy nhất.

## 11. Lưu ACE tùy chỉnh qua MutableAclService

Đoạn Java tích hợp sau minh họa cấp EXPORT cho Alice trên tài liệu 42. Nó **không tự chạy** nếu chưa có `DataSource`, bốn bảng ACL, `LookupStrategy`, `AclCache` và `MutableAclService`.

```java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;

public final class DocumentAclWriter {

    private final MutableAclService aclService;

    public DocumentAclWriter(MutableAclService aclService) {
        this.aclService = aclService;
    }

    public void grantExport(long id, String user) {
        ObjectIdentity oid =
                new ObjectIdentityImpl("com.acme.Document", id);
        Sid sid = new PrincipalSid(user);

        MutableAcl acl;
        try {
            acl = (MutableAcl) aclService.readAclById(oid);
        } catch (NotFoundException notFound) {
            acl = aclService.createAcl(oid);
        }

        acl.insertAce(
                acl.getEntries().size(),
                DocumentPermission.EXPORT,
                sid,
                true);

        aclService.updateAcl(acl);
    }
}
```

Ý nghĩa:

- `ObjectIdentityImpl` ghép type `"com.acme.Document"` với ID. Type phải khớp `ACL_CLASS` và chuỗi type trong biểu thức `hasPermission`.
- `PrincipalSid(user)` cấp quyền cho principal. Với một nhóm, dùng `GrantedAuthoritySid`.
- `insertAce(index, permission, sid, true)` tạo ACE grant; truyền `false` là ACE deny, **không** phải xóa quyền.
- `acl.getEntries()` trong API Spring Security hiện tại trả `List<AccessControlEntry>`, nên gọi `.size()`.
- `aclService.updateAcl(acl)` persist thay đổi. JDBC mutable ACL implementation có thể xóa và tạo lại các entry khi cập nhật, nên cần giao dịch, audit, khóa đồng thời khi phù hợp.

Đừng gọi method này từ endpoint công khai. **Quyền quản lý ACL** phải được bảo vệ độc lập với quyền đọc/xem/tải tài liệu; không để người có READ tự thêm EXPORT hoặc ADMINISTRATION cho chính mình.

### Lưu READ và EXPORT thành hai ACE rõ ràng

```java
acl.insertAce(acl.getEntries().size(),
        BasePermission.READ, new PrincipalSid("alice"), true);

acl.insertAce(acl.getEntries().size(),
        DocumentPermission.EXPORT, new PrincipalSid("alice"), true);

aclService.updateAcl(acl);
```

Mã trên giả định `acl` và `aclService` đã được tạo. Nếu hệ thống dùng danh sách permission hoặc composite mask, phải kiểm thử chính xác cách grants/denies được tính; hai ACE đơn lẻ thường dễ giải thích hơn khi nghiệp vụ kiểm tra từng quyền.

## 12. Kết nối AclPermissionEvaluator với @PreAuthorize

Luồng thực thi:

```text
@PreAuthorize("hasPermission(#p0, 'com.acme.Document', 'EXPORT')")
        |
        v
Method security expression handler
        |
        v
AclPermissionEvaluator
  -> PermissionFactory: EXPORT -> mask 32
  -> Authentication -> principal/authority SIDs
  -> ObjectIdentity("com.acme.Document", id)
        |
        v
AclService / LookupStrategy / ACL_... database
        |
        v
Acl + PermissionGrantingStrategy
        |
        v
Cho phép hoặc từ chối lời gọi method
```

Cấu hình phần liên quan trực tiếp tới quyền (ví dụ **tích hợp**, chưa bao gồm toàn bộ JDBC ACL infrastructure):

```java
@Configuration
@EnableMethodSecurity
class AclSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    PermissionFactory permissionFactory() {
        return new DefaultPermissionFactory(
                Map.<String, Permission>of(
                    "READ", BasePermission.READ,
                    "WRITE", BasePermission.WRITE,
                    "CREATE", BasePermission.CREATE,
                    "DELETE", BasePermission.DELETE,
                    "ADMINISTRATION", BasePermission.ADMINISTRATION,
                    "EXPORT", DocumentPermission.EXPORT,
                    "APPROVE", DocumentPermission.APPROVE));
    }

    @Bean
    AclPermissionEvaluator aclPermissionEvaluator(
            AclService service, PermissionFactory factory) {
        AclPermissionEvaluator evaluator =
                new AclPermissionEvaluator(service);
        evaluator.setPermissionFactory(factory);
        return evaluator;
    }
}
```

Imports tương ứng:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.DefaultPermissionFactory;
import org.springframework.security.acls.domain.PermissionFactory;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Cần import `DocumentPermission` của ứng dụng. `@Bean static` cho handler là mẫu tài liệu Spring Security khi cần cung cấp sớm handler tùy biến. Không đăng ký thêm một handler khác khiến cấu hình `RoleHierarchy` hoặc `PermissionEvaluator` bị thay thế ngoài ý muốn.

Ở `BasicLookupStrategy` có `setPermissionFactory(factory)`; ứng dụng có custom permissions cần quyết định cách factory được truyền khi tạo LookupStrategy, nhằm đồng bộ việc đọc ACL và biểu thức.

Khi dùng:

```java
@PreAuthorize("hasPermission(#p0, 'com.acme.Document', 'EXPORT')")
public byte[] exportDocument(long id) {
    return documentExportService.buildExport(id);
}
```

đoạn code là **method tích hợp**, `documentExportService` do dự án cung cấp. Method phải được gọi **qua Spring-managed proxy** trong cấu hình `@EnableMethodSecurity`, không phải `new` instance hoặc self-invocation bypass proxy.

Dạng hai đối số `hasPermission(document, 'EXPORT')` được dùng với **object đã tồn tại**, còn dạng ba đối số `hasPermission(id, type, permission)` dành cho ID. Không dùng target object do client tự khai owner/tenant làm dữ liệu xác thực quyền.

## 13. Ví dụ Java 17 dùng Spring ACL API với Maven

Dự án sau dùng `BasePermission`, `CumulativePermission` và `DefaultPermissionFactory` thật, không cần DB. Cấu trúc:

```text
spring-acl-mask-demo/
├── pom.xml
└── src/main/java/demo/
    ├── DocumentPermission.java
    └── AclMaskDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-acl-mask-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-acl</artifactId>
      <version>6.5.7</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/demo/DocumentPermission.java`:

```java
package demo;

import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.Permission;

public final class DocumentPermission extends BasePermission {
    public static final Permission EXPORT =
            new DocumentPermission(1 << 5, 'E');
    public static final Permission APPROVE =
            new DocumentPermission(1 << 6, 'P');

    private DocumentPermission(int mask, char code) {
        super(mask, code);
    }
}
```

`src/main/java/demo/AclMaskDemo.java`:

```java
package demo;

import java.util.Map;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.CumulativePermission;
import org.springframework.security.acls.domain.DefaultPermissionFactory;
import org.springframework.security.acls.domain.PermissionFactory;
import org.springframework.security.acls.model.Permission;

public final class AclMaskDemo {

    public static void main(String[] args) {
        PermissionFactory factory =
                new DefaultPermissionFactory(
                    Map.<String, Permission>of(
                        "READ", BasePermission.READ,
                        "WRITE", BasePermission.WRITE,
                        "CREATE", BasePermission.CREATE,
                        "DELETE", BasePermission.DELETE,
                        "ADMINISTRATION", BasePermission.ADMINISTRATION,
                        "EXPORT", DocumentPermission.EXPORT,
                        "APPROVE", DocumentPermission.APPROVE));

        CumulativePermission combined = new CumulativePermission()
                .set(BasePermission.READ)
                .set(BasePermission.WRITE)
                .set(DocumentPermission.EXPORT);

        System.out.println("read=" + BasePermission.READ.getMask());
        System.out.println("write=" + BasePermission.WRITE.getMask());
        System.out.println("export=" + DocumentPermission.EXPORT.getMask());
        System.out.println("combined=" + combined.getMask());
        System.out.println("factoryExport="
                + factory.buildFromName("EXPORT").getMask());
        System.out.println("factoryMask="
                + factory.buildFromMask(combined.getMask()).getMask());

        combined.clear(BasePermission.WRITE);
        System.out.println("afterClearWrite=" + combined.getMask());
        System.out.println("patternLength=" + combined.getPattern().length());
    }
}
```

Lệnh chạy với Maven và JDK 17+:

```bash
mvn -q compile
mvn -q exec:java -Dexec.mainClass=demo.AclMaskDemo
```

Những dòng ứng dụng được thiết kế in ra:

```text
read=1
write=2
export=32
combined=35
factoryExport=32
factoryMask=35
afterClearWrite=33
patternLength=32
```

Các giá trị đã được đối chiếu logic code và API Spring Security ACL. **Chưa chạy Maven build trực tiếp** khi soạn bài; cần chạy trên máy có Maven/JDK để xác minh end-to-end. Đây là ví dụ về permission representation, **không phải** integration test với DB ACL/PermissionGrantingStrategy. Phiên bản dependency được cố định phục vụ học API; production phải dùng nhánh còn hỗ trợ, đồng bộ Spring Security modules theo BOM.

## 14. Ma trận kiểm thử ACL thật

Không dừng ở unit test bitmask. Kiểm tra hệ thống bằng `AclService`, database và method security proxy.

| Tình huống | Kỳ vọng |
| --- | --- |
| BasePermission.READ mask | 1 |
| BasePermission.WRITE mask | 2 |
| BasePermission.CREATE mask | 4 |
| BasePermission.DELETE mask | 8 |
| BasePermission.ADMINISTRATION mask | 16 |
| Custom EXPORT, APPROVE | 32, 64; không trùng |
| `CumulativePermission.set(READ).set(EXPORT)` | Mask 33 |
| `factory.buildFromName("EXPORT")` | Mask 32 |
| Alice có ACE READ grant trên Document 42 | `hasPermission` READ được phép |
| Alice không có ACE EXPORT | Không được EXPORT |
| Thêm ACE EXPORT grant rồi reload | EXPORT được phép; cache cập nhật đúng |
| Bob có explicit deny EXPORT | Không được EXPORT |
| ROLE_EDITOR có ACE EXPORT trên Document 42 | Chỉ subject có SID phù hợp được grant |
| ACL cha grant và child inheriting bật/tắt | Kế thừa đúng policy |
| ACE composite 33, hỏi 1/32/33 | Assert theo strategy thật, không phỏng đoán |
| Resource khác ID/type/tenant | Không dùng nhầm ACL |
| Không có ACL, SID hoặc DB lỗi | Không fail-open |
| Caller có READ nhưng tự xin thêm ACE ADMINISTRATION | Bị từ chối ở API quản lý ACL |
| Gọi service qua proxy với `@PreAuthorize` | Deny khi thiếu permission |

Khi đổi một permission mask đã persist, cần migration và regression test quyền cũ/quyền mới. Nếu dùng cache, test thu hồi quyền phải cho thấy grant cũ không còn sau khi update/invalidation.

### Tình huống nhiều SID và deny/grant

Một người có thể có `PrincipalSid("alice")` và `GrantedAuthoritySid("ROLE_EDITOR")`. Một ACE deny cho principal và một ACE grant cho role có thể cần cách phân giải cụ thể. `DefaultPermissionGrantingStrategy` có thứ tự xét permission và SID; đừng tự kết luận “deny luôn thắng mọi grant” hoặc “role luôn thắng user” mà không đọc strategy/configuration và test.

## 15. Sai lầm và cách tránh

**1. Trùng bit mới với quyền cũ.** Nếu EXPORT và APPROVE cùng bằng 32 thì ACE không thể phân biệt. Dùng permission registry duy nhất.

**2. Đổi ý nghĩa bit sau khi có dữ liệu.** Mask đã lưu trong ACL_ENTRY không tự migrate; cần quy trình chuyển đổi.

**3. Nghĩ mask dương là grant.** Mask chỉ nói về quyền; `granting` mới nói về cấp/từ chối.

**4. Cho rằng ADMINISTRATION tự chứa READ/WRITE/DELETE.** Các bit độc lập. Thiết kế admin override riêng nếu nghiệp vụ yêu cầu.

**5. Coi toán `(aceMask & required) != 0` là quy tắc mặc định của Spring ACL.** Chỉ là phép bit. `PermissionGrantingStrategy` mới định nghĩa semantics, bao gồm SID, deny và ACL cha.

**6. Dùng danh sách `List.of(READ, EXPORT)` như chắc chắn có nghĩa “đủ cả hai”.** Không mặc định. Cần policy AND rõ và test.

**7. Dùng XOR để revoke.** XOR có thể thêm quyền. Với persisted ACL, thao tác trên ACE; không chỉ đổi một biến.

**8. Quên đăng ký tên quyền trong PermissionFactory.** `hasPermission(..., 'EXPORT')` sẽ không tự hiểu quyền tùy chỉnh.

**9. Sai `targetType`.** `"Document"` khác `"com.acme.Document"` nếu DB ACL_CLASS lưu chuỗi thứ hai. Phải thống nhất.

**10. Đọc `ACL_ENTRY.MASK` rồi quyết định không xét SID/grant/inheritance.** Bỏ sót dữ liệu quan trọng và tạo lỗ hổng.

**11. Dùng object do client khai owner/tenant để quyết định.** Chỉ tin identity và resource metadata được xác minh phía server.

**12. Cấp quyền sửa ACL cho người chỉ có quyền dùng tài liệu.** Có nguy cơ privilege escalation. Bảo vệ admin/service mutator riêng.

**13. Bỏ qua cache/transaction khi cập nhật ACL.** Có thể tạo stale grants, lost updates hoặc ACL không nhất quán với resource.

**14. Dùng cùng ObjectIdentity cho hai tenant có ID trùng.** Phải định danh đủ duy nhất để ACL không rò chéo.

**15. Tưởng annotation tự chạy khi `new Service()` hoặc `this.method()`.** Với Spring AOP proxy mode, lời gọi cần đi qua proxy hợp lệ.

## 16. Checklist production

- [ ] Phân biệt `Permission` với role/`GrantedAuthority` và `Sid`.
- [ ] Năm mask chuẩn đúng 1, 2, 4, 8, 16.
- [ ] Quyền tùy chỉnh cấp bit trống, không trùng và không tự đổi sau khi lưu ACE.
- [ ] Biết cách ghép/kiểm tra bit bằng OR, AND, NOT nhưng không nhầm với grant/deny.
- [ ] Mọi ACE có ObjectIdentity, SID, Permission, granting và audit đúng.
- [ ] `PermissionFactory` giải được tên/mask custom; evaluator và lookup strategy dùng mapping nhất quán.
- [ ] `CumulativePermission` chỉ được dùng theo semantics đã kiểm thử.
- [ ] Có test cụ thể cho default/custom `PermissionGrantingStrategy`, thứ tự SIDs, deny và inheritance.
- [ ] ACL được tạo/cập nhật/xóa đồng bộ với resource lifecycle, transaction và cache.
- [ ] Bảo vệ API quản trị ACE/ACL độc lập với API đọc/ghi tài liệu.
- [ ] Không có grant khi thiếu ACL, người dùng, dữ liệu quyền hoặc backend lỗi.
- [ ] ObjectIdentity không va chạm giữa các tenant.
- [ ] Method security và Spring-managed proxy được cấu hình và test.
- [ ] Có unit test masks/factory và integration test ACL JDBC/hasPermission thực tế.

**Ghi nhớ:** `BasePermission` định nghĩa quyền chuẩn; **mask** chỉ là cách mã hóa bit; `CumulativePermission` giúp biểu diễn tổ hợp; `PermissionFactory` dịch tên/mask; còn **Acl + ACE + PermissionGrantingStrategy** mới quyết định *ai có quyền nào trên tài nguyên nào*. Quyền custom phải có mask ổn định, không trùng, được đăng ký và được kiểm thử như một phần của chính sách bảo mật.

## Tài liệu chính thức

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [Spring Security — BasePermission JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/BasePermission.html)
- [Spring Security — CumulativePermission JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/CumulativePermission.html)
- [Spring Security — DefaultPermissionFactory JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionFactory.html)
- [Spring Security — DefaultPermissionGrantingStrategy JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
- [Spring Security — AclPermissionEvaluator JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/AclPermissionEvaluator.html)
