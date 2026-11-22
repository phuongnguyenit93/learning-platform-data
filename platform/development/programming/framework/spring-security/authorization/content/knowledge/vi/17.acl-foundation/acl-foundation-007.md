# Chủ sở hữu ACL và quyền trên đối tượng: hai khái niệm cần tách biệt

## 1. Tình huống: chủ sở hữu danh sách quyền nhưng không đọc được tài liệu

Một tài liệu `Document #42` có ba thông tin độc lập:

- **Chủ sở hữu nghiệp vụ của tài liệu** (`documents.owner_id`): `carol`.
- **Chủ sở hữu của ACL** (`Acl.getOwner()` hay `acl_object_identity.owner_sid`): `alice`.
- **Các quyền truy cập trên tài liệu** (những `AccessControlEntry`, viết tắt ACE): `bob` được `READ`, `erin` được `WRITE`, `dave` được `ADMINISTRATION`.

Câu hỏi dễ nhầm: `alice` là chủ sở hữu ACL nên có tự động được `READ` nội dung tài liệu không? **Không nên suy luận như vậy.** Với cơ chế Spring Security ACL mặc định, quyền đọc/ghi dữ liệu được đánh giá theo những ACE có hiệu lực cho SID và permission được yêu cầu; thuộc tính owner của ACL phục vụ một mục đích khác, đặc biệt là kiểm soát **ai có thể quản trị ACL** theo chiến lược được cấu hình.

Tương tự, `carol` là chủ sở hữu nghiệp vụ của `Document #42`, nhưng thông tin đó **không tự biến `carol` thành ACL owner** hay tự tạo `READ` ACE. Nếu doanh nghiệp muốn owner tài liệu luôn được đọc, hãy diễn đạt thành **quy tắc quyền rõ ràng** và bảo đảm cập nhật nhất quán.

Bài này thuộc phần **Nền tảng ACL** của Spring Security. Trọng tâm là phân biệt **ownership của ACL**, **ownership của domain object** và **quyền trên object**, sau đó áp dụng tách biệt chúng trong thiết kế, mã nguồn và kiểm thử.

Sau bài học, bạn có thể:

1. Giải thích chính xác `Acl.getOwner()` và `AccessControlEntry` phục vụ hai bài toán khác nhau.
2. Phân biệt `PrincipalSid`, `GrantedAuthoritySid`, `ObjectIdentity`, `Permission` và `MutableAclService`.
3. Hiểu hai con đường kiểm tra: **quản trị ACL** và **truy cập dữ liệu**.
4. Không nhầm `BasePermission.ADMINISTRATION` với `READ`/`WRITE`, hoặc nhầm ACL owner với chủ sở hữu nghiệp vụ.
5. Viết/chạy ví dụ Java 17 chứng minh một người có quyền quản trị ACL mà không nhất thiết đọc được dữ liệu.
6. Kết nối khái niệm với API Spring Security ACL và `hasPermission(...)`.
7. Tránh lỗi nâng quyền, lộ dữ liệu chéo tenant, quyền cấp nhầm hoặc quyền còn sót sau chuyển ownership.

**Ngữ cảnh:** các API Spring Security ACL theo dòng Spring Security 6.5.x. Phần mô phỏng Java thuần chạy độc lập không cần Spring; các đoạn tích hợp với Spring ACL được đánh dấu là **mảnh code minh họa**, cần các bean và database ACL đã cấu hình trước khi dùng trong ứng dụng thật.

## 2. Ba loại “owner” và “permission” không được gộp

| Khái niệm | Nó mô tả điều gì? | Nguồn dữ liệu điển hình | Có tự động cho `READ` không? |
| --- | --- | --- | --- |
| **Domain owner** | Ai sở hữu bản ghi theo nghiệp vụ? | `documents.owner_id`, user/tenant directory | Không, trừ khi chính sách nghiệp vụ cấp quyền |
| **ACL owner** | SID nào được ghi nhận là owner của danh sách kiểm soát quyền? | `Acl.getOwner()`, `acl_object_identity.owner_sid` | Không có bảo đảm mặc định rằng owner có `READ` |
| **Object permission** | SID nào được cấp hoặc bị từ chối hành động trên object? | ACE trong `acl_entry` hoặc policy khác | Phải đánh giá ACE/policy có hiệu lực |

Ba khái niệm có thể tình cờ thuộc cùng một người, nhưng không bắt buộc. Một công ty có thể giao bộ phận compliance (`alice`) quản trị danh sách quyền cho một tài liệu; tài liệu do nhân viên (`carol`) tạo và chỉ người được phê duyệt (`bob`) mới có quyền đọc. Thiết kế này **hợp lệ** nếu cả ứng dụng thực hiện đúng policy.

### 2.1. Chủ sở hữu domain object

Một entity có thể định nghĩa:

```java
public record Document(
        Long id,
        String ownerUserId,
        String tenantId,
        String title) {
}
```

`ownerUserId` là thuộc tính **nghiệp vụ**. Nó có thể chi phối hóa đơn, chi phí, báo cáo, quy trình chuyển quyền hay khả năng sửa bản ghi, nhưng **không phải trường của interface `Acl`**.

Nếu controller nhận `Document` từ JSON, những trường `ownerUserId`/`tenantId` trong request **không đáng tin để cấp quyền**. Hãy đọc bản ghi thật bằng ID từ repository và lấy identity/tenant của caller từ ngữ cảnh đã được xác thực.

### 2.2. Chủ sở hữu ACL

`Acl.getOwner()` trả một đối tượng `Sid` (hoặc `null` nếu implementation không dùng khái niệm owner). SID là viết tắt của **Security Identity**: có thể đại diện một principal (`PrincipalSid`) hoặc một authority/role (`GrantedAuthoritySid`).

Trong bản cài đặt ACL tiêu chuẩn, owner được lưu cùng thông tin định danh đối tượng trong `acl_object_identity`. Với `AclAuthorizationStrategyImpl`, việc là ACL owner là **một trong các căn cứ** để cho phép thao tác quản trị trên cấu trúc ACL; còn có thể cho phép nhờ authority hệ thống hoặc ACE `ADMINISTRATION`. Phạm vi thao tác hành chính thực tế vẫn phụ thuộc cấu hình chiến lược và các guard của ứng dụng.

**Điểm quan trọng:** API `Acl.getOwner()` có ghi rõ ý nghĩa ownership phụ thuộc implementation. Không nên biến cách hiểu của một implementation thành quy tắc tự động của mọi hệ thống ACL.

### 2.3. Quyền trên đối tượng: ACE

Mỗi `AccessControlEntry` (ACE) điển hình gắn:

- Một `Acl`/`ObjectIdentity` cụ thể.
- Một `Sid` nhận tác dụng của entry.
- Một `Permission` như `READ` hoặc `WRITE`.
- Một cờ `granting`: `true` để grant, `false` để deny.
- Thông tin audit success/failure nếu sử dụng.

Ví dụ khái niệm:

```text
ObjectIdentity = Document#42
ACL owner      = alice

ACE[0]  bob     READ             GRANT
ACE[1]  erin    WRITE            GRANT
ACE[2]  dave    ADMINISTRATION   GRANT
ACE[3]  guest   READ             DENY
```

Ở đây owner của ACL không phải một ACE `READ` tự động. Chỉ có `bob` được liệt kê có `READ` trực tiếp; `erin` có `WRITE` không đồng nghĩa có `READ`; `dave` có `ADMINISTRATION` không mặc nhiên tương đương đọc nội dung.

Nếu có ACE theo vai trò, ACL kế thừa hoặc chính sách tùy chỉnh khác, kết quả cuối cùng có thể thay đổi. Bảng trên chỉ mô tả những entry được cho trong ví dụ, chưa giả định bất kỳ quyền ẩn nào.

## 3. Cấu trúc ACL trong Spring Security

Spring Security có module `spring-security-acl`. Khi sử dụng bản triển khai JDBC truyền thống, các bảng cốt lõi gồm:

| Bảng | Chức năng | Trường liên quan |
| --- | --- | --- |
| `ACL_SID` | Danh sách các principal/authority nhận quyền | `sid`, `principal` |
| `ACL_CLASS` | Loại domain object dùng ACL | `class` |
| `ACL_OBJECT_IDENTITY` | Mỗi instance object gắn với một ACL | `object_id_identity`, `object_id_class`, `owner_sid`, `parent_object`, `entries_inheriting` |
| `ACL_ENTRY` | Các ACE gắn với object và SID | `acl_object_identity`, `sid`, `mask`, `granting`, `ace_order` |

`owner_sid` và các ACE không phải cùng một trường. Đọc `owner_sid` rồi suy ra `READ=1` sẽ bỏ qua thiết kế phân quyền thật. Khi tạo một ACL, ứng dụng cần quyết định ai có thể quản trị ACL và những ACE nào được cấp, thay vì trông chờ framework tự sao chép owner nghiệp vụ thành tất cả permission.

### 3.1. Những interface và class cần biết

- `Acl`: cung cấp `getOwner()`, `getEntries()`, `getObjectIdentity()`, `getParentAcl()`, `isEntriesInheriting()` và `isGranted(...)`.
- `MutableAcl`: cho phép thay owner, thêm/xóa/sửa ACE và cấu hình quan hệ ACL tùy API; hành động được kiểm soát theo chiến lược quản trị.
- `AclService`: đọc ACL theo một `ObjectIdentity`; có thể đọc theo tập để tránh N+1.
- `MutableAclService`: tạo, cập nhật và xóa ACL khi được phép.
- `ObjectIdentity`: cặp khái niệm loại object và ID; thường dùng `ObjectIdentityImpl`.
- `Sid`: interface định danh đối tượng nhận quyền; phổ biến `PrincipalSid` và `GrantedAuthoritySid`.
- `Permission`: biểu diễn quyền theo bitmask; các hằng cơ bản ở `BasePermission`.
- `AccessControlEntry`: kết hợp SID, permission và trạng thái grant/deny.
- `AclPermissionEvaluator`: dùng dịch vụ ACL để phục vụ biểu thức `hasPermission(...)`.
- `AclAuthorizationStrategy`: xét **quyền thao tác quản trị ACL**, không phải quyết định `READ` dữ liệu thông thường.
- `PermissionGrantingStrategy`: xét **quyền trên object** từ danh sách permission và SID trong ACL.

Hai chiến lược cuối cùng là nơi dễ nhầm nhất. Một bên kiểm tra **được phép thay đổi ACL không**; một bên kiểm tra **được phép truy cập object không**.

### 3.2. Quyền cơ bản là bitmask, không phải một boolean owner

`BasePermission` cung cấp năm quyền cơ bản:

| Hằng | Mask | Ý nghĩa |
| --- | ---: | --- |
| `BasePermission.READ` | 1 | Đọc |
| `BasePermission.WRITE` | 2 | Ghi |
| `BasePermission.CREATE` | 4 | Tạo |
| `BasePermission.DELETE` | 8 | Xóa |
| `BasePermission.ADMINISTRATION` | 16 | Quản trị theo policy ACL |

Một permission được lưu dưới dạng mask. Không nên tự suy luận rằng `WRITE` gồm `READ`, hay rằng `ADMINISTRATION` bao hàm tất cả quyền khác. **Các bit là những quyền khác nhau**; ngữ nghĩa kết hợp mask và grant/deny phụ thuộc `PermissionGrantingStrategy`/policy.

Với chiến lược mặc định `DefaultPermissionGrantingStrategy`, thứ tự permission, SID và ACE được xét có ảnh hưởng đến kết quả; nếu không tìm thấy ACE phù hợp, ACL có thể chuyển sang ACL cha nếu cho phép kế thừa. Vì vậy không thể quyết định quyền bằng cách quét tùy tiện và dùng `anyMatch(ACE.granting)` trên tất cả entry.

## 4. Quyền quản trị ACL khác quyền đọc dữ liệu ở điểm nào?

### 4.1. Khi kiểm tra quyền quản trị ACL

`AclAuthorizationStrategyImpl` là một implementation của `AclAuthorizationStrategy`. Nó cho phép một thao tác quản trị tùy `changeType` nếu có căn cứ phù hợp, chẳng hạn:

1. Người gọi là **ACL owner**.
2. Người gọi có **authority hệ thống** được cấu hình trong constructor.
3. Người gọi có **ACE `BasePermission.ADMINISTRATION`** trên ACL, theo chiến lược đó.

Chi tiết từng loại thay đổi như `CHANGE_GENERAL`, `CHANGE_OWNERSHIP`, `CHANGE_AUDITING` và cấu hình sử dụng cần được kiểm tra khi triển khai. Không tự suy luận rằng có role `ROLE_USER` là được quản trị ACL.

Đây là quyền **thay cấu hình quyền**: thêm hoặc xóa grant, đổi người nhận quyền, đổi ACL owner và thông tin tương tự, tùy policy. Nó không tự động đồng nghĩa có thể gọi repository để lấy nội dung bí mật của tài liệu.

### 4.2. Khi kiểm tra quyền trên domain object

Đối với lời gọi:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document readDocument(Long id) {
    // Load dữ liệu sau khi được cho phép.
}
```

Spring Method Security đánh giá biểu thức, `AclPermissionEvaluator` (nếu đã đăng ký) tìm ACL của object ID và gọi cơ chế xét permission cho các SID của `Authentication`.

Nó không hỏi **“người gọi có phải owner của ACL không?”** như phép so sánh đơn giản để tự động cấp `READ`. Nó hỏi **“dựa vào ACL/ACE/policy, caller có `READ` trên object này không?”**. Quyền owner ACL có thể quan trọng với thao tác quản trị ACL, nhưng không được đổi vai trò thành một wildcard đọc dữ liệu.

### 4.3. Ma trận tình huống

Giả sử **không có ACE kế thừa và không có quyền đặc biệt khác**:

| Người | Domain owner? | ACL owner? | ACE trên `Document#42` | Đọc? | Quản trị ACL? |
| --- | --- | --- | --- | --- | --- |
| `alice` | Không | Có | Không có `READ` | Không | Có, theo policy quản trị ví dụ |
| `bob` | Không | Không | `READ` | Có | Không |
| `carol` | Có | Không | Không có | Không | Không |
| `dave` | Không | Không | `ADMINISTRATION` | Không | Có, theo policy ví dụ |
| `erin` | Không | Không | `WRITE` | Không | Không |

Ma trận cố ý tách ba vai trò. Trong sản phẩm, một người vừa có thể là domain owner vừa là ACL owner vừa có nhiều ACE. Điều quan trọng là **quyền nào được cấp phải có nguồn rõ ràng**, không gộp ngầm ba cột lại thành một.

### 4.4. Hệ quả của việc đổi ownership

**Đổi domain owner** (`Document.ownerUserId` từ `carol` sang `bob`) không tự động chuyển `acl_object_identity.owner_sid` sang `bob`. Spring Security ACL cũng không tự tạo ACE `READ` cho `bob`, không xóa grant của chủ cũ và không tự tái tính group membership.

**Đổi ACL owner** (`MutableAcl.setOwner`) không tự động chuyển `documents.owner_id`, cũng không mặc nhiên tạo ACE đọc/ghi trên tài liệu. Chỉ có một policy ứng dụng chủ động đồng bộ hai khái niệm mới làm chúng thay đổi cùng nhau.

Vì vậy, workflow chuyển sở hữu cần quy định rõ: thay đổi dữ liệu nào, thu hồi quyền nào, tạo quyền mới nào, audit ai khởi tạo, tính nhất quán và thời điểm commit.

## 5. Ví dụ Java 17 chạy độc lập: ACL owner có thể không được READ

Ví dụ sau **không cần Spring**. Mục tiêu là quan sát sự khác biệt về khái niệm và kiểm chứng stdout bằng `javac/java`. Đây là **mô phỏng tối giản**, không phải bản sao thuật toán ACL framework: không thực hiện role SID, kế thừa ACE, ACL cache, transaction hay audit của Spring Security.

Một file duy nhất **`AclOwnershipDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class AclOwnershipDemo {

    enum Permission {
        READ, WRITE, ADMINISTRATION
    }

    record Document(long id, String businessOwner, String title) {
    }

    record Ace(String sid, Permission permission, boolean granting) {
    }

    static final class SimpleAcl {
        private final long objectId;
        private final String aclOwnerSid;
        private final List<Ace> entries = new ArrayList<>();

        SimpleAcl(long objectId, String aclOwnerSid) {
            this.objectId = objectId;
            this.aclOwnerSid = Objects.requireNonNull(aclOwnerSid);
        }

        String aclOwnerSid() {
            return aclOwnerSid;
        }

        void seed(Ace ace) {
            entries.add(Objects.requireNonNull(ace));
        }

        boolean permits(String sid, Permission permission) {
            if (sid == null || permission == null) {
                return false;
            }

            // Chỉ để minh họa: một ACE khớp trực tiếp, không có ACL cha.
            for (Ace ace : entries) {
                if (ace.sid().equals(sid)
                        && ace.permission() == permission) {
                    return ace.granting();
                }
            }
            return false;
        }

        boolean mayAdminister(String sid) {
            return sid != null
                && (sid.equals(aclOwnerSid)
                    || permits(sid, Permission.ADMINISTRATION));
        }

        void replaceAce(String actor, Ace newAce) {
            if (!mayAdminister(actor)) {
                throw new SecurityException(
                    "User cannot change ACL for object " + objectId);
            }

            entries.removeIf(ace ->
                ace.sid().equals(newAce.sid())
                && ace.permission() == newAce.permission());

            entries.add(newAce);
        }
    }

    public static void main(String[] args) {
        Document document =
            new Document(42L, "carol", "Confidential report");
        SimpleAcl acl = new SimpleAcl(document.id(), "alice");

        acl.seed(new Ace("bob", Permission.READ, true));
        acl.seed(new Ace("erin", Permission.WRITE, true));
        acl.seed(new Ace("dave", Permission.ADMINISTRATION, true));

        System.out.println("DOMAIN_OWNER: " + document.businessOwner());
        System.out.println("ACL_OWNER: " + acl.aclOwnerSid());
        System.out.println("ALICE_READ: "
            + acl.permits("alice", Permission.READ));
        System.out.println("ALICE_MANAGE: "
            + acl.mayAdminister("alice"));
        System.out.println("BOB_READ: "
            + acl.permits("bob", Permission.READ));
        System.out.println("BOB_MANAGE: "
            + acl.mayAdminister("bob"));
        System.out.println("CAROL_READ: "
            + acl.permits("carol", Permission.READ));
        System.out.println("DAVE_MANAGE: "
            + acl.mayAdminister("dave"));
        System.out.println("DAVE_READ: "
            + acl.permits("dave", Permission.READ));
        System.out.println("ERIN_WRITE: "
            + acl.permits("erin", Permission.WRITE));
        System.out.println("ERIN_READ: "
            + acl.permits("erin", Permission.READ));

        // ACL owner alice thu hồi quyền READ của bob.
        acl.replaceAce(
            "alice",
            new Ace("bob", Permission.READ, false));
        System.out.println("BOB_AFTER_DENY: "
            + acl.permits("bob", Permission.READ));

        // dave có ACE ADMINISTRATION nên có thể sửa ACL trong mô phỏng.
        acl.replaceAce(
            "dave",
            new Ace("carol", Permission.READ, true));
        System.out.println("CAROL_AFTER_GRANT: "
            + acl.permits("carol", Permission.READ));

        try {
            acl.replaceAce(
                "bob",
                new Ace("bob", Permission.READ, true));
            System.out.println("BOB_CHANGE_ACL: UNEXPECTED");
        } catch (SecurityException denied) {
            System.out.println("BOB_CHANGE_ACL: DENIED");
        }

        // Chuyển owner nghiệp vụ không tự đổi aclOwnerSid.
        Document transferred = new Document(
            document.id(), "bob", document.title());
        System.out.println("TRANSFERRED_DOMAIN_OWNER: "
            + transferred.businessOwner());
        System.out.println("ACL_OWNER_STILL: " + acl.aclOwnerSid());
    }
}
```

### 5.1. Biên dịch và chạy

Cần JDK 17 trở lên. Trong thư mục chứa file:

```bash
javac AclOwnershipDemo.java
java AclOwnershipDemo
```

Trên Windows PowerShell cũng sử dụng hai lệnh này nếu `javac`/`java` đã có trong PATH.

**Stdout chính xác theo source trên:**

```text
DOMAIN_OWNER: carol
ACL_OWNER: alice
ALICE_READ: false
ALICE_MANAGE: true
BOB_READ: true
BOB_MANAGE: false
CAROL_READ: false
DAVE_MANAGE: true
DAVE_READ: false
ERIN_WRITE: true
ERIN_READ: false
BOB_AFTER_DENY: false
CAROL_AFTER_GRANT: true
BOB_CHANGE_ACL: DENIED
TRANSFERRED_DOMAIN_OWNER: bob
ACL_OWNER_STILL: alice
```

Điểm học được:

- `alice` là ACL owner và được quyền quản trị trong mô phỏng, nhưng chưa có ACE `READ`.
- `bob` có ACE `READ` nên được đọc; quyền đọc không trao quyền quản trị ACL.
- `carol` là domain owner nhưng chưa có ACE `READ` cho tới khi `dave` cấp quyền.
- `dave` có ACE `ADMINISTRATION`, có thể sửa ACL theo policy mô phỏng mà không mặc nhiên đọc tài liệu.
- `erin` có `WRITE` nhưng không có `READ`; không tự áp dụng một thứ bậc permission.
- Thu hồi grant của `bob` bằng ACE `DENY` khiến `bob` không còn được đọc.
- Chuyển domain owner từ `carol` sang `bob` không làm `aclOwnerSid` đổi khỏi `alice`.

**Giới hạn bảo mật của mô phỏng:** tên actor là chuỗi truyền trực tiếp vào method, không phải danh tính đã được xác thực. Trong Spring Security thật, danh tính đến từ `Authentication` đáng tin cậy. Không chuyển `actor` từ request body thành quyền quản trị, và không sao chép thuật toán `SimpleAcl.permits` để thay thế `Acl.isGranted`.

## 6. API Spring Security ACL: đọc owner và đánh giá permission riêng biệt

Trong Spring ACL, `Acl` có owner và entries riêng biệt:

```java
// MẢNH CODE minh họa bên trong một Spring service có AclService.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 42L);
Acl acl = aclService.readAclById(oid);

Sid ownerSid = acl.getOwner();
List<AccessControlEntry> entries = acl.getEntries();
```

Các import chính:

```java
import java.util.List;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
```

`Acl.getOwner()` trả metadata ACL owner; `getEntries()` cho danh sách ACE đã nạp. Không tự so `ownerSid.equals(new PrincipalSid(authentication))` rồi mặc nhiên cho phép đọc dữ liệu.

### 6.1. Kiểm tra `READ` đúng API

```java
// MẢNH CODE minh họa, giả định acl đã được load đủ các SID cần thiết.
Sid bobSid = new PrincipalSid("bob");

boolean canBobRead;
try {
    canBobRead = acl.isGranted(
        List.of(BasePermission.READ),
        List.of(bobSid),
        false
    );
} catch (org.springframework.security.acls.model.NotFoundException ex) {
    canBobRead = false;
}
```

Phép kiểm tra trên hỏi **có ACE/hành vi kế thừa phù hợp cho `bob` và `READ` không**. Nó không dùng `acl.getOwner()` như một wildcard.

Trong dữ liệu thực tế, có thể cần nhiều SID của một principal, ví dụ `PrincipalSid` và `GrantedAuthoritySid` theo group/role. `Acl.isGranted(...)` có thể phát sinh `NotFoundException` khi không thể tìm được một quyết định và `UnloadedSidException` khi dữ liệu SID chưa được load đúng; cần xử lý phù hợp, luôn tránh biến trạng thái không xác định thành `allowed=true`.

`administrativeMode` ở tham số cuối của `Acl.isGranted(...)` **không có nghĩa “hãy cấp `ADMINISTRATION`”**. Nó biểu thị kiểm tra trong chế độ hành chính, liên quan behavior audit của strategy; quyền cần xét vẫn nằm trong danh sách `Permission` (ở đây là `READ`).

### 6.2. Thêm một ACE không đồng nghĩa đổi ACL owner

Giả sử một quản trị viên **đã được phép** cập nhật ACL muốn cấp `READ` cho `bob`:

```java
// MẢNH CODE minh họa trong service quản trị ACL có MutableAclService.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 42L);
MutableAcl acl = (MutableAcl) mutableAclService.readAclById(oid);

Sid bobSid = new PrincipalSid("bob");
acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    bobSid,
    true
);

mutableAclService.updateAcl(acl);
```

Import thêm:

```java
import org.springframework.security.acls.model.MutableAcl;
```

Đoạn này thao tác trên ACE `READ` của `bob`, **không phải** trên `Acl.getOwner()`. Một ACE `granting=false` có ý nghĩa deny. Việc tạo, đổi, xóa ACE phải được ràng buộc bởi policy quản trị, transaction, audit và xử lý duplicate/ACE order.

Vì Spring Security **không tự đồng bộ ACL với DAO/entity lifecycle**, ứng dụng chịu trách nhiệm tạo hoặc xóa ACL khi đối tượng tạo mới/xóa, cập nhật ACE khi chia sẻ quyền và xử lý ownership transfer.

### 6.3. Đổi ACL owner là thao tác khác

```java
// MẢNH CODE minh họa; caller phải có quyền quản trị tương ứng.
MutableAcl acl =
    (MutableAcl) mutableAclService.readAclById(
        new ObjectIdentityImpl(Document.class, 42L));

acl.setOwner(new PrincipalSid("alice"));
mutableAclService.updateAcl(acl);
```

`setOwner` thay metadata owner của ACL, **không phải** tạo một ACE `READ`, `WRITE` hay đổi `documents.owner_id`. Khi triển khai, cần đảm bảo chiến lược quản trị cho phép thay owner và workflow nghiệp vụ xác định rõ người owner mới được quyền gì. Đừng dựa vào việc đổi owner để tự cấp quyền đọc dữ liệu.

### 6.4. `AclAuthorizationStrategy` và `PermissionGrantingStrategy`

Hai API cùng liên quan một ACL nhưng phục vụ mục đích khác:

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| `AclAuthorizationStrategy` | Ai được phép **thay đổi ACL**? | ACL owner, authority hệ thống hoặc ACE quản trị theo chiến lược |
| `PermissionGrantingStrategy` | SID này có permission trên **domain object** không? | `isGranted(READ, SID)` dựa trên ACE và ACL cha |

Một cấu hình có thể sử dụng:

```java
// MẢNH CODE cấu hình, cần các bean ACL infrastructure phù hợp.
AclAuthorizationStrategy aclAuthorizationStrategy =
    new AclAuthorizationStrategyImpl(
        new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));

PermissionGrantingStrategy permissionGrantingStrategy =
    new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());
```

Import thêm:

```java
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.model.AclAuthorizationStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

`AclAuthorizationStrategyImpl` hỗ trợ kiểm tra người gọi có phải ACL owner, có authority hệ thống đã cấu hình hoặc có ACE `ADMINISTRATION` khi cho phép tác vụ quản trị. Cấu hình này **không tự gán `READ` cho toàn bộ người có `ROLE_ACL_ADMIN`**; muốn đọc dữ liệu, phải có một policy riêng cấp và kiểm tra quyền đọc.

Đừng tạo một endpoint `/acl/change` rồi cho client tự truyền `actorUserId` để kiểm tra quản trị. Hạ tầng quản trị cần lấy `Authentication` từ Spring Security và kiểm soát đúng ACL, tenant và tác vụ thay đổi.

## 7. `AclPermissionEvaluator` dùng trong Method Security

Một biểu thức theo object ID:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document getDocument(@P("id") Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

Các import tiêu biểu:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
```

Đây là **mảnh method minh họa**, giả định repository và `Document` của dự án thật. `targetType='demo.Document'` phải khớp `ObjectIdentity` được lưu trong `ACL_CLASS` hoặc quy tắc `ObjectIdentityGenerator` đang dùng. Không dùng tên tùy ý rồi giả định JDBC ACL sẽ tìm đúng bản ghi.

Để biểu thức chuyển đến ACL, đăng ký `AclPermissionEvaluator` trên `DefaultMethodSecurityExpressionHandler`:

```java
@Configuration
@EnableMethodSecurity
class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService service) {
        return new AclPermissionEvaluator(service);
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

**Đây chưa phải một ứng dụng Spring Boot độc lập.** Cấu hình còn cần `AclService` thật, ví dụ `JdbcMutableAclService`, `LookupStrategy`, `AclCache`, schema ACL trong database và các strategy tương ứng. Module ACL phải được khai báo trong dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-acl'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
}
```

Đây là **đoạn Gradle dependency minh họa** trong một dự án Spring Boot đã có version plugin và kho Maven; chưa gồm JDBC driver/database. Chỉ thêm dependency không làm Method Security, ACL schema hay ACL records tự xuất hiện.

`AclPermissionEvaluator` lấy `Authentication` từ Method Security và xem SID/permission tương ứng với đối tượng. Giá trị `'READ'` trong SpEL phải được permission factory biết ánh xạ sang `BasePermission.READ` (factory mặc định đăng ký tên các hằng public của `BasePermission`). Khi dùng custom permission hoặc cách biểu diễn khác, cần đăng ký factory thích hợp và kiểm thử tên/mask.

### Khi không dùng ACL framework

Bạn cũng có thể tự viết `PermissionEvaluator` kiểm tra quyền từ repository:

```java
@Override
public boolean hasPermission(
        Authentication authentication,
        Object target,
        Object permission) {

    if (!(target instanceof Document doc)) {
        return false;
    }

    return policy.canRead(authentication, doc.id(), permission);
}
```

Đây là mảnh code bên trong một class implements `PermissionEvaluator` (các type/bean `policy` phải được cung cấp). Nếu `Document` đến từ client, chỉ tin ID để tra bản ghi phía server; không tin owner do DTO gửi. Cả phương pháp ACL framework và custom evaluator đều phải tách bạch **quyền đọc dữ liệu** khỏi **quyền chỉnh ACL**.

## 8. ACE `ADMINISTRATION` có quyền gì?

Một hiểu lầm khác là: “Nếu một SID có `BasePermission.ADMINISTRATION` thì chắc chắn được tất cả `READ`, `WRITE`, `DELETE`.” Điều đó **không phải bảo đảm tổng quát**.

- `ADMINISTRATION` là một bit permission riêng, mask `16`.
- `READ`, `WRITE`, `CREATE`, `DELETE` có mask khác.
- `AclAuthorizationStrategyImpl` có thể dùng ACE `ADMINISTRATION` làm một căn cứ cho **quyền sửa ACL**.
- `Acl.isGranted(READ, sids, false)` cần đánh giá **READ** theo chiến lược permission granting. Không nên tự so `isGranted(ADMINISTRATION)` rồi tự ý cho phép mọi thao tác dữ liệu trừ khi policy nghiệp vụ yêu cầu.
- Một tổ chức có thể chủ động định nghĩa “administrator có toàn quyền đọc” bằng rule bổ sung; khi đó đó là **quyết định thiết kế của tổ chức**, không phải hệ quả chỉ từ trường owner hay mask ADMINISTRATION.

Ví dụ: `dave` có thể được ủy quyền thay đổi danh sách chia sẻ của báo cáo mà không cần được đọc nội dung báo cáo có dữ liệu y tế hoặc tài chính nhạy cảm. Tách nghĩa hai loại quyền giúp đáp ứng **least privilege** và chia tách trách nhiệm.

### Vì sao không tạo “ngầm quyền” bằng role?

Nếu code viết:

```java
// KHÔNG NÊN dùng khi doanh nghiệp không chủ ý cấp quyền đọc:
boolean canRead = isAclOwner(authentication, acl)
    || hasPermission(authentication, documentId, "READ");
```

thì mọi ACL owner sẽ đọc được object bất kể ACE. Nếu chính sách thực sự muốn điều này, phải mô tả rõ điều kiện `owner -> READ`, có test, audit và kiểm tra tenant. Nếu không, đó là lỗi nâng quyền vô tình.

Tương tự, thêm `ROLE_ADMIN` vào `AclAuthorizationStrategyImpl` để quản lý ACE **không có nghĩa** phần còn lại của ứng dụng phải cấp quyền xem toàn bộ dữ liệu cho `ROLE_ADMIN`.

## 9. SID, authority và owner theo ngữ cảnh xác thực

### 9.1. `PrincipalSid` khác `GrantedAuthoritySid`

Một ACL có thể cấp `READ` cho:

```java
Sid userSid = new PrincipalSid("bob");
Sid roleSid = new GrantedAuthoritySid("ROLE_AUDITOR");
```

Import:

```java
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
```

`PrincipalSid` đại diện một principal, còn `GrantedAuthoritySid` đại diện một authority/role. Nếu `Authentication` hiện tại có principal `"bob"` và authority `"ROLE_AUDITOR"`, các SID tương ứng có thể được dùng khi đánh giá ACE tùy `SidRetrievalStrategy`.

**Sai lầm phổ biến:** so chuỗi `"ROLE_AUDITOR"` với `"bob"` như hai identity cùng loại, hoặc gắn owner ACL bằng một role rồi mặc định đó là cùng một user. `Acl.getOwner()` trả `Sid`, nên cần giữ cả **loại SID** lẫn **giá trị SID**.

### 9.2. `Authentication` là nguồn danh tính của người gọi

Method Security dùng `Authentication` đã được hệ thống xác thực, không phải ID người gọi tự khai trong body/query/header. Các loại principal của JWT, OIDC và username/password có thể khác nhau; cần một mapping ổn định từ principal sang SID.

Trong hệ thống đa tenant, username `"bob"` có thể trùng giữa tổ chức A và B. Nếu chỉ dùng `PrincipalSid("bob")` chung toàn hệ thống trong khi ID user không globally unique, có nguy cơ trao nhầm ACE. Nên định nghĩa SID từ **stable user ID đã xác minh**, có tenant scope phù hợp với mô hình lưu trữ, hoặc quy ước namespace không thể trùng. Tất cả thao tác đọc, tạo ACE, chuyển owner và audit phải dùng cùng quy ước.

### 9.3. Anonymous không phải owner hợp lệ chỉ vì `isAuthenticated()`

`AnonymousAuthenticationToken` có thể trả `isAuthenticated() == true` theo đặc tính token; không dùng một mình thuộc tính này để suy ra quyền. Với policy tự viết, dùng `AuthenticationTrustResolver` hoặc cơ chế xác thực đáng tin, đồng thời yêu cầu đúng SID/permission. Nếu thiếu authentication, SID hoặc ACL, xử lý theo fail closed.

## 10. Kế thừa ACL và thứ tự ACE làm thay đổi quyền

Spring ACL cho phép một object ACL có **ACL cha**. Nếu `isEntriesInheriting()` là `true`, quyền từ cha có thể được xét khi ACL con không có quyết định phù hợp, tùy `PermissionGrantingStrategy`.

```text
Folder#7 ACL
   ownerSid = alice
   ACE: ROLE_READER -> READ GRANT

      |
      | parent ACL (entriesInheriting=true)
      v

Document#42 ACL
   ownerSid = bob
   ACE: carol -> WRITE GRANT
```

Nếu `Document#42` không có ACE `READ` phù hợp mà cho phép kế thừa, role reader có thể được đọc theo ACL của folder, dù ACL owner của document là `bob`. Đây là lý do không nên suy luận “owner là `bob` thì `bob` sẽ đọc được” hoặc “không có ACE con nghĩa là chắc chắn từ chối” mà không xét cấu hình cha.

**Thứ tự và deny ACE:** thuật toán mặc định xem xét danh sách permissions và SIDs theo thứ tự, đồng thời thứ tự ACE có thể ảnh hưởng đến quyết định khi nhiều entry phù hợp. Không thay toàn bộ logic bằng `entries.stream().anyMatch(AccessControlEntry::isGranting)`. Một ACE `DENY` cần được hiểu theo permission/SID, cùng chính sách kết hợp và cách nạp SID.

**Không tìm thấy ACE:** `Acl.isGranted(...)` có thể ném `NotFoundException` nếu không có đủ dữ liệu quyết định, chứ không bắt buộc trả `false`. Đó là lý do cần xử lý ngoại lệ phù hợp ở ranh giới authorization và tuyệt đối không cấp quyền khi gặp exception/thiếu thông tin.

### Chủ sở hữu ACL cha có tự thành owner ACL con không?

Không nên suy luận vậy. Mỗi ACL có trường owner riêng; kế thừa **ACE** không đồng nghĩa kế thừa `owner_sid` hay `documents.owner_id`. Nếu ứng dụng muốn ủy quyền quản trị ACL con theo folder owner, cần định nghĩa policy quản trị riêng hoặc đồng bộ ownership rõ ràng.

## 11. Tình huống nâng quyền thường gặp

### 11.1. Tự cấp quyền bằng cách đổi owner của tài liệu

Controller nhận request:

```json
{
  "documentId": 42,
  "ownerUserId": "attacker"
}
```

Nếu backend vừa tin `ownerUserId` mới vừa cấp `READ` ngay dựa trên owner do request khai, attacker có thể chiếm quyền đọc. Cần kiểm tra quyền thực hiện **chuyển sở hữu**, lấy bản ghi gốc từ server, xác thực danh tính actor và chỉ cập nhật theo workflow được phép.

### 11.2. Dùng ACL owner để bỏ qua ACE

Một `if (acl.getOwner().equals(currentSid)) return true` trong `canRead` làm ACL owner trở thành quyền đọc ngầm. Hãy tách:

```text
canManageAcl = policyForAclChange(...)
canReadData  = policyForObjectRead(...)
```

Không dùng kết quả `canManageAcl` thay thế kết quả `canReadData`, trừ khi đặc tả nghiệp vụ yêu cầu và đã được kiểm thử.

### 11.3. Quên thu hồi quyền cũ sau khi chuyển ownership

Chuyển `Document.ownerUserId` từ `carol` sang `bob` nhưng giữ ACE `READ` cũ cho `carol` có thể khiến chủ cũ tiếp tục xem dữ liệu. Đó có thể là nghiệp vụ đúng (co-owner/đã chia sẻ), hoặc là lỗ hổng. Hãy quy định chính xác ACE nào được giữ, thu hồi hay cấp thêm, và xác minh sau cập nhật.

### 11.4. Chỉ kiểm tra quyền trên endpoint, không bảo vệ service

Một endpoint quản trị ACL được bảo vệ ở URL nhưng service vẫn gọi được từ scheduler, message listener hoặc nơi khác. Hãy áp dụng `@PreAuthorize`/`AuthorizationManager` ở ranh giới service quan trọng, với quyền **quản trị ACL**, không chỉ quyền đọc. Thao tác đổi owner, thêm ACE và xóa ACE là các thao tác nhạy cảm cần audit.

### 11.5. Quản trị ACL bị self-invocation bypass

Trong cơ chế proxy, một lời gọi `this.securedChangeAcl()` bên trong cùng bean có thể bỏ qua method-security advice. Tách service quản trị ACL khỏi workflow gọi nó hoặc kiểm thử qua Spring-managed proxy; không chỉ dựa vào annotation được đặt trên method.

### 11.6. Không phân biệt quyền xem metadata ACL và quyền xem nội dung

Một admin bảo mật có thể cần xem danh sách principal/ACE để sửa cấu hình, nhưng không cần xem nội dung tài liệu; ngược lại, một user có `READ` tài liệu không nhất thiết được phép liệt kê toàn bộ người được chia sẻ hoặc quyền của người khác. Hãy phân quyền **view ACL metadata**, **modify ACL**, **read object** và **write object** theo từng use case cụ thể.

## 12. Quy trình tạo và thay đổi quyền an toàn

### 12.1. Tạo domain object

Một workflow có kiểm soát thường thực hiện:

1. Xác thực user/tenant và kiểm tra quyền tạo object.
2. Tạo domain object trong database; ID được xác định bởi server.
3. Tạo ACL cho đúng `ObjectIdentity(class, id)` nếu policy sử dụng Spring ACL.
4. Chỉ định `owner_sid` theo quy định quản trị, không mặc định phải bằng `domainOwner`.
5. Thêm ACE cần thiết, ví dụ `READ` cho người dùng phù hợp, `WRITE` cho editor, `ADMINISTRATION` cho quản trị viên được ủy quyền.
6. Commit/đồng bộ thay đổi, bảo đảm không có trạng thái object hiện hữu nhưng ACL chưa sẵn sàng mà endpoint lại cấp quyền do fallback lỏng lẻo.
7. Ghi audit: actor, thời điểm, object identity, quyền trước/sau và nguồn yêu cầu.

Spring Security **không tự tạo ACL trong JPA repository hoặc DAO** chỉ vì entity đã được lưu. Ứng dụng phải chủ động triển khai lifecycle ACL.

### 12.2. Chuyển domain owner

Ví dụ owner nghiệp vụ chuyển từ `carol` sang `bob`. Hãy quyết định bằng văn bản:

- Có chuyển luôn `Acl.getOwner()` không?
- Có cấp ACE `READ`/`WRITE` cho `bob` không?
- Có thu hồi ACE của `carol` không?
- Ai được phép thực hiện chuyển quyền?
- Tenant của tài liệu có thay đổi không?
- ACL cha, group grants và cache quyền phải được cập nhật không?
- Nếu lưu domain DB và ACL DB khác nhau, dùng transaction/outbox/saga nào để đảm bảo nhất quán?

Không có câu trả lời mặc định đúng cho mọi ứng dụng. Điều sai là **gộp ba loại ownership/permission mà không có policy**.

### 12.3. Tách use case trong service

Một thiết kế rõ trách nhiệm có thể gồm:

```text
DocumentQueryService
    readDocument(id)            -- yêu cầu READ trên object

DocumentEditingService
    updateDocument(id, changes) -- yêu cầu WRITE trên object

AclAdministrationService
    grantPermission(id, sid, p)  -- yêu cầu sửa ACL
    revokePermission(id, sid,p)  -- yêu cầu sửa ACL
    transferAclOwner(id, sid)    -- yêu cầu đổi owner ACL

DocumentOwnershipService
    transferBusinessOwner(...)  -- yêu cầu nghiệp vụ chuyển owner
```

Sơ đồ này **chỉ là thiết kế interface**, không phải code runnable. Một service quản trị ACL không được tự cho caller quyền xem nội dung. Ngược lại, user có `READ` không được gọi `grantPermission` chỉ vì đang đọc object.

## 13. Kiểm thử ACL owner và quyền object phải tách riêng

Trong hệ thống Spring Security có dữ liệu ACL đầy đủ, hãy có các ca test riêng cho hai API:

- `canReadDocument(authentication, objectId)`
- `canAdministerAcl(authentication, objectId, changeType)`

### 13.1. Ma trận kiểm thử

| Scenario | `READ` dữ liệu | Quản trị ACL | Kỳ vọng |
| --- | --- | --- | --- |
| ACL owner không có READ ACE | Từ chối | Cho phép theo policy quản trị | Không ngầm cấp quyền đọc |
| User có READ ACE nhưng không phải ACL owner | Cho phép | Từ chối | Không ngầm cấp quyền sửa ACL |
| Domain owner chưa có ACE | Từ chối, trừ policy riêng | Không tự cấp | Không ngầm đồng bộ owner |
| User có ADMINISTRATION ACE nhưng không READ | Không tự cấp | Có thể cho phép theo strategy | Quyền hành chính khác quyền dữ liệu |
| User có WRITE ACE nhưng không READ | Không tự cấp | Không tự cấp | Không giả định permission hierarchy |
| User bị deny READ rõ ràng | Từ chối theo strategy | Độc lập | Không bỏ qua deny bằng owner check |
| ACE READ được thu hồi | Từ chối sau cập nhật | Độc lập | Invalidation hiệu lực |
| ACL owner đổi nhưng domain owner giữ nguyên | READ không tự thay | Owner metadata thay | Không sửa business owner ngoài ý muốn |
| Domain owner đổi nhưng ACL owner giữ nguyên | READ theo ACE/policy | ACL owner giữ nguyên | Không tự cập nhật ACL |
| Sai tenant hoặc object ID | Từ chối | Từ chối | Không lộ dữ liệu chéo tenant |
| Anonymous/unknown principal | Từ chối | Từ chối | Fail closed |

Các test quan trọng nhất là **negative cases**, vì các lỗi cấp quyền thường không thể nhìn thấy bằng test chỉ xác nhận quản trị viên được thao tác.

### 13.2. Kiểm thử qua Spring proxy

Với Method Security, dùng `@SpringBootTest` và `@WithMockUser`/`@WithAnonymousUser` của `spring-security-test`. Gọi service do Spring inject; không tự `new Service()` rồi cho rằng annotation đã bảo vệ. Khi kiểm tra `Acl.isGranted(...)`, dữ liệu SID/ACE/ACL inheritance phải được dựng hoặc seed chính xác theo kịch bản.

Trong test đổi ACL owner, hãy assert **cả ba điều**:

1. `Acl.getOwner()` thay đổi đúng yêu cầu.
2. `Document.ownerUserId` chỉ đổi nếu workflow chỉ định.
3. Tập ACE và kết quả `hasPermission(READ/WRITE)` chỉ đổi nếu quy tắc thật sự thay đổi chúng.

Trong test cập nhật ACE, assert ACL owner **không tự thay đổi** chỉ vì có grant mới.

### 13.3. Kiểm thử nguyên tắc từ chối mặc định

Không nên cấp quyền trong các tình huống: ACL không tồn tại, object không thuộc tenant đã xác minh, SID không load đủ, permission không nhận diện, ACL lookup lỗi hoặc principal không xác thực. Phân biệt lỗi quyền (403), thiếu tài nguyên (404 theo policy chống enumeration) và lỗi hạ tầng (5xx) tại HTTP layer, nhưng tuyệt đối không chuyển lỗi hạ tầng thành `allow=true`.

## 14. Performance, transaction và cache: vẫn phải giữ ranh giới

### 14.1. ACL lookup theo từng object có thể gây N+1

Với `@PostFilter("hasPermission(filterObject, 'READ')")`, evaluator có thể đọc ACL cho từng phần tử; một danh sách N bản ghi có thể sinh N lookup ACL. `AclService`/`LookupStrategy` có hỗ trợ cách nạp theo tập; với collection lớn nên cân nhắc truy vấn lọc quyền ở tầng DB hoặc batch ACL lookup.

Tối ưu không được bỏ qua deny ACE, ACL inheritance, principal SID hay authority SID. Cùng một object có thể cho các user khác nhau kết quả khác nhau; cache không được dùng key chỉ có object ID để lưu một boolean `allowed`.

### 14.2. Cache ACE và ACL owner thay đổi

Nếu ACL được cache trong Redis/Caffeine hoặc `AclCache`, việc đổi `owner_sid`, grant/revoke ACE hoặc đổi parent ACL phải invalidation phù hợp. Ngoài ra, những quyết định đã cache theo `(user, object, permission)` cũng có thể stale sau revoke hoặc thay đổi group membership.

**Cache owner != cache permission decision.** Đọc owner metadata chỉ để quyết định quyền quản trị mà dùng kết quả cho READ sẽ vừa sai nghĩa vừa có nguy cơ rò dữ liệu.

### 14.3. Race giữa quyền và thao tác ghi

`@PreAuthorize` có thể kiểm tra quyền tại thời điểm `t1`, rồi database cập nhật tại `t2`. Nếu ACL/tenant/owner thay đổi giữa hai thời điểm, có nguy cơ **TOCTOU**.

Với các thao tác nhạy cảm, cần transaction, optimistic locking hoặc câu lệnh UPDATE có điều kiện với identity/tenant/quyền tin cậy, đồng thời xét commit/invalidation sau thay đổi. Một request đã được phép sửa ACL lúc kiểm tra không nên mặc định giữ quyền đó mãi nếu ACL owner thay đổi trong lúc xử lý.

## 15. Những lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Coi `Acl.getOwner()` là ACE `READ` | ACL owner vô tình đọc được dữ liệu bí mật | Kiểm tra `READ` bằng ACE/PermissionGrantingStrategy riêng |
| Coi domain owner là ACL owner | Đồng bộ nhầm hai khái niệm | Duy trì ownership nghiệp vụ và ACL metadata riêng |
| Coi `ADMINISTRATION` đồng nghĩa mọi permission | Admin ACL được đọc/ghi/xóa dữ liệu ngoài policy | Chỉ cấp từng quyền khi nghiệp vụ xác định |
| Coi `WRITE` bao hàm `READ` | Người chỉ được chỉnh sửa có thể xem nội dung bí mật | Định nghĩa permission hierarchy bằng policy rõ ràng nếu cần |
| Bỏ qua deny ACE và thứ tự SID/ACE | Cho phép dù ACL có quyết định từ chối | Dùng `Acl.isGranted(...)` và strategy phù hợp |
| Tin user/tenant từ JSON | Có thể tạo ACE cho identity giả hoặc lộ tenant khác | Dùng Authentication và directory/repository server |
| Đổi owner nghiệp vụ nhưng quên xét ACE | Chủ cũ còn quyền hoặc chủ mới không có quyền | Workflow chuyển quyền có bước ACL rõ ràng |
| Đổi ACL owner rồi tưởng owner domain cũng đổi | Dữ liệu nghiệp vụ và ACL lệch | Cập nhật từng loại ownership có chủ đích |
| Chỉ dùng URL security cho thao tác đổi ACE | Service nội bộ có thể bypass endpoint | Bảo vệ service bằng Method Security |
| Gọi protected method qua `this` | Self-invocation bypass proxy | Tách bean / gọi qua Spring-managed proxy |
| ACL không tồn tại nhưng fallback cho phép | Fail-open | Từ chối và xử lý lỗi hạ tầng phù hợp |
| Cache theo object ID mà không theo user/tenant | Lộ quyền giữa principal | Key đúng scope và invalidation |
| Quên ACL parent inheritance | Kết luận sai quyền cuối cùng | Xét parent và `isEntriesInheriting()` |
| Kiểm thử chỉ một user admin | Không phát hiện cấp quyền quá rộng | Test owner ACL, ACE reader, domain owner, anonymous, cross-tenant |

## 16. Câu hỏi tự kiểm tra

1. **`Acl.getOwner()` trả dữ liệu gì?**  
   Một `Sid` đại diện owner của ACL (tùy implementation có thể null), không phải một `Permission.READ`.

2. **Domain owner có tự trở thành ACL owner không?**  
   Không. Chỉ khi ứng dụng chủ động xây dựng và đồng bộ quy tắc đó.

3. **Một người có ACE `READ` trên tài liệu có được sửa ACL không?**  
   Không mặc định. Quyền quản trị ACL có strategy/policy riêng.

4. **Một ACL owner không có ACE `READ` có đọc được object không?**  
   Không được suy luận là có. Phải đánh giá permission trên object theo ACE/policy thực tế.

5. **`BasePermission.ADMINISTRATION` có đồng nghĩa `READ | WRITE | DELETE` không?**  
   Không phải quy tắc mặc định. Các bit permission là riêng biệt.

6. **`AclAuthorizationStrategyImpl` phục vụ kiểm tra gì?**  
   Ai được thực hiện các thao tác quản trị đối với ACL, không phải tự động cho phép đọc nội dung của object.

7. **`PermissionGrantingStrategy` kiểm tra gì?**  
   Permission cụ thể của một hoặc nhiều SID trên một ACL, có thể tính ACE và kế thừa theo implementation.

8. **Vì sao `setOwner(new PrincipalSid("bob"))` không đủ để cho `bob` đọc?**  
   Vì nó đổi ACL owner metadata, không tạo ACE `READ` cho `bob`.

9. **Chuyển `Document.ownerUserId` có tự xóa ACE của chủ cũ không?**  
   Không. Ứng dụng phải quyết định có thu hồi hay giữ lại, rồi cập nhật ACL tương ứng.

10. **Cần kiểm tra gì với ACL kế thừa?**  
    ACL cha, `isEntriesInheriting()`, SID/permission phù hợp và logic granting/denial.

11. **Vì sao không lấy `"actor"` từ JSON để xét quyền sửa ACL?**  
    Vì client có thể giả mạo identity; quyền phải dựa trên authentication đã xác minh.

12. **Làm sao chứng minh không có lỗ hổng “ACL owner = READ”?**  
    Test một principal là ACL owner nhưng không có READ ACE, và kỳ vọng `hasPermission(..., READ)` bị từ chối trong policy tương ứng.

13. **Nếu cùng một người vừa là ACL owner vừa có ACE READ, điều gì xảy ra?**  
    Người đó có hai căn cứ độc lập: ownership cho quản trị ACL theo strategy và ACE cho đọc object. Không được gộp thành một quyền chung không kiểm soát.

14. **Nếu admin ACL cần xem danh sách chia sẻ nhưng không cần đọc báo cáo?**  
    Tách API/permission xem metadata ACL khỏi API đọc nội dung báo cáo; không cấp quyền đọc rộng chỉ để quản trị.

## 17. Tài liệu chính thức

- [Spring Security — Domain Object Security (ACLs), phiên bản 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): mô hình ACL, SID, owner metadata, ACE, bitmask và tích hợp method security.
- [Spring Security — ACL database schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): bảng `acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`.
- [Spring Security — `Acl` API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/model/Acl.html): `getOwner`, `getEntries`, `isGranted`, inheritance và cách hiểu ownership.
- [Spring Security — `AclAuthorizationStrategyImpl` API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html): owner/authority/ACE administration trong chính sách thay đổi ACL.
- [Spring Security — `DefaultPermissionGrantingStrategy` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): quy tắc permission, SID, deny/grant và parent ACL.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, expression handler và proxy.
- [Spring Security — `AclPermissionEvaluator` API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/acls/AclPermissionEvaluator.html): đánh giá quyền qua ACL theo object hoặc object ID.

**Tóm tắt:** trong Spring Security ACL, **owner của ACL** là metadata liên quan việc **quản trị danh sách quyền**; **quyền truy cập trên domain object** được quyết định theo ACE/permission/strategy; còn **owner nghiệp vụ** là thuộc tính domain do ứng dụng định nghĩa. Ba khái niệm có thể trùng người nhưng **không tương đương**. Khi viết hệ thống phân quyền, hãy luôn kiểm tra riêng `canManageAcl`, `canReadObject` và `businessOwner`, đồng thời ghi rõ quy tắc chuyển đổi giữa chúng nếu nghiệp vụ yêu cầu.