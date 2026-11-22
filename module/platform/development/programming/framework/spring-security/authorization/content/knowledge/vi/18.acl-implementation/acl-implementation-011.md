# Kiểm thử quyền trực tiếp, quyền kế thừa và ACE từ chối trong Spring Security ACL

## 1. Bài toán cần chứng minh bằng test

Trong hệ thống quản lý tài liệu, một thư mục có thể cấp quyền đọc cho một nhóm. Tài liệu con có thể kế thừa quyền đó, nhưng một tài liệu nhạy cảm có thể tắt kế thừa hoặc chứa một **Access Control Entry (ACE)** từ chối. Nếu chỉ viết test “Alice đọc được tài liệu của mình” thì rất dễ bỏ sót lỗi phân quyền ở cả ba trường hợp.

Bài học tập trung vào đúng ba loại hành vi:

1. **Quyền trực tiếp:** ACE nằm ngay trên ACL của tài nguyên được hỏi.
2. **Quyền kế thừa:** ACL con không có ACE phù hợp, có ACL cha và bật `entriesInheriting` nên có thể nhận quyết định từ cha.
3. **ACE từ chối:** một ACE phù hợp có `granting=false` khiến yêu cầu bị từ chối theo `PermissionGrantingStrategy` đang dùng.

Ví dụ nhu cầu:

- Folder 10 cấp `READ` cho Alice.
- Document 42 nằm trong Folder 10, không có ACE READ riêng; nếu bật kế thừa, Alice được READ.
- Document 43 vẫn có parent Folder 10 nhưng tắt kế thừa; không có ACE READ nên không được phép.
- Document 44 có parent Folder 10 nhưng có ACE READ với `granting=false` cho Alice; quyết định READ của nó phải bị từ chối.
- Bob không được đọc chỉ vì Alice có quyền: phép kiểm tra luôn phải xét **SID của caller**.

**Nguyên tắc kiểm thử:** không chỉ assert một kết quả boolean; phải chứng minh **ACE nào dẫn tới kết quả**, phân biệt explicit deny với missing ACE, và kiểm tra đường thực thi qua ACL service/evaluator/method security.

## 2. Các đối tượng và thuật ngữ cần dùng

```text
Authentication (caller)
  |
  v
Sid: PrincipalSid("alice") hoặc GrantedAuthoritySid("ROLE_EDITOR")
  |
  v
ObjectIdentity("demo.Document", documentId)
  |
  v
Acl của tài liệu
  |-- các ACE trực tiếp: Permission, Sid, granting
  |-- parent Acl (nếu có)
  |-- entriesInheriting: true/false
  |
  v
PermissionGrantingStrategy
  |
  +--> true: grant
  +--> false: explicit deny theo strategy
  +--> NotFoundException: thiếu quyết định có thẩm quyền
```

| Khái niệm | API Spring Security ACL | Điều test phải kiểm tra |
| --- | --- | --- |
| Resource | `ObjectIdentity`, `ObjectIdentityImpl` | Đúng loại và ID, không lẫn tenant |
| Chủ thể | `Sid`, `PrincipalSid`, `GrantedAuthoritySid` | Cùng resource nhưng user/role khác kết quả có thể khác |
| Quyền | `Permission`, `BasePermission.READ/WRITE` | Đúng permission mask; READ không tự bao hàm WRITE |
| ACE | `AccessControlEntry` | `getSid()`, `getPermission()`, `isGranting()` |
| ACL | `Acl`, `AclImpl`, `MutableAcl` | Direct entries, parent, inheritance flag |
| Đọc/lưu | `AclService`, `MutableAclService` | Persist/reload ra cùng chính sách |
| Chiến lược | `PermissionGrantingStrategy` | Quy tắc tìm ACE và diễn giải grant/deny |
| Tích hợp biểu thức | `AclPermissionEvaluator` | `hasPermission(...)` đi qua đúng ACL |
| Cơ chế method | `@EnableMethodSecurity`, `@PreAuthorize` | Lời gọi phải qua Spring AOP proxy |

Ba kiểu kết quả khác nhau khi gọi trực tiếp `acl.isGranted(...)`:

- `true`: tìm thấy chứng cứ cấp quyền.
- `false`: có quyết định từ chối phù hợp.
- `NotFoundException`: không tìm thấy thông tin ACL đủ để đưa ra quyết định có thẩm quyền. Đây **không** phải giá trị true; ở service boundary phải xử lý theo nguyên tắc mặc định từ chối hoặc hợp đồng lỗi đã định.

Ngoài ra `UnloadedSidException` biểu thị ACL chỉ được tải cho một phần SIDs mà caller kiểm tra SID chưa được load. Đừng biến exception này thành “người đó chắc chắn không có ACE” khi test coverage; nó là tín hiệu dữ liệu chưa đầy đủ.

## 3. Mô hình dữ liệu cho ba tình huống

Giả sử:

```text
Folder #10
  ACE(PrincipalSid("alice"), READ, granting=true)
        |
        +-- Document #42: parent #10, entriesInheriting=true
        |      ACE trực tiếp: không có READ cho Alice
        |
        +-- Document #43: parent #10, entriesInheriting=false
        |      ACE trực tiếp: không có READ cho Alice
        |
        +-- Document #44: parent #10, entriesInheriting=true
               ACE(PrincipalSid("alice"), READ, granting=false)
```

Với `DefaultPermissionGrantingStrategy` và yêu cầu chỉ gồm `READ`, một SID Alice:

| Object | ACE READ trực tiếp | Có parent? | Inherit? | Kết quả API cấp thấp |
| --- | --- | --- | --- | --- |
| Folder 10 | Grant READ/Alice | Không | — | `true` |
| Document 42 | Không | Có | `true` | `true` nhờ parent |
| Document 43 | Không | Có | `false` | `NotFoundException` nếu không có ACE khác |
| Document 44 | Deny READ/Alice | Có | `true` | `false`; không dùng parent để “cứu” lần kiểm tra READ này |
| Document 42 cho Bob | Không có grant cho Bob | Có | `true` | Không tìm thấy ACE Bob → `NotFoundException` trong mô hình này |

**Chú ý:** đây là kết quả khi chỉ hỏi một permission READ và một SID Alice/Bob, dùng strategy mặc định. Khi truyền **nhiều permissions** hoặc **nhiều SIDs**, thuật toán có thứ tự ưu tiên; không thể tùy tiện mở rộng bảng thành câu “deny luôn thắng”.

## 4. Quyền trực tiếp: test cái gì?

ACE trực tiếp nằm trên chính resource ACL:

```text
Document #50
  ACE: alice + READ  + granting=true
  ACE: alice + WRITE + granting=false
```

Test mong muốn:

- Alice hỏi READ trên Document 50 → `true`.
- Alice hỏi WRITE trên Document 50 → `false`.
- Bob hỏi READ trên Document 50, không có ACE Bob/parent → không có quyết định (thường `NotFoundException`).
- Document 51 không có ACE của Alice → grant ở Document 50 **không áp dụng** lên 51.
- ROLE_EDITOR có READ trên một document không tự cấp cho người không có authority đó.

Mã ý tưởng:

```java
Acl acl = aclService.readAclById(
        new ObjectIdentityImpl("demo.Document", 50L));

boolean canRead = acl.isGranted(
        List.of(BasePermission.READ),
        List.of(new PrincipalSid("alice")),
        false);
```

Đây là **đoạn tích hợp**; `aclService` phải được ứng dụng cấu hình. Tham số cuối `administrativeMode=false` cho phép audit theo cấu hình. Test thuần logic có thể dùng `true` để không tạo audit log, nhưng boolean này **không** có nghĩa “bỏ qua authorization”.

Test nên xác minh *cả quyền và phạm vi* bằng resource type+ID, SID, permission mask. Không dùng `hasRole` để thay thế việc kiểm tra ACL theo object.

## 5. Quyền kế thừa: hai điều kiện phải cùng đúng

ACL con có thể trỏ đến ACL cha, nhưng **có parent chưa đủ để thừa hưởng ACE**. Theo `AclImpl`, cần cả:

1. `getParentAcl() != null`.
2. `isEntriesInheriting() == true` trên ACL con.

```text
child.getParentAcl() = folderAcl
child.isEntriesInheriting() = false
      |
      +--> Parent chỉ để điều hướng; không được dùng để quyết định quyền
```

Nếu bật:

```text
child.getParentAcl() = folderAcl
child.isEntriesInheriting() = true
child không có ACE phù hợp
      |
      +--> Strategy có thể xét parentAcl, rồi parent của parent...
```

Trên mô hình strategy mặc định, **trường hợp thiếu mọi ACE phù hợp ở child** là thời điểm chuyển lên parent. Nếu child đã có ACE phù hợp **deny** cho đúng permission/SID, không được tự xem grant cha như một permission override.

### Ma trận inheritance cần có

| Parent | Child có READ trực tiếp? | `entriesInheriting` | Kỳ vọng |
| --- | --- | --- | --- |
| Grant Alice READ | Không | `true` | Alice READ qua parent |
| Grant Alice READ | Không | `false` | Không inherit |
| Grant Alice READ | Deny Alice READ | `true` | Explicit deny |
| Deny Alice READ | Không | `true` | Deny từ parent |
| Không có ACE | Không | `true` | Không có grant, có thể `NotFoundException` |
| Grant ROLE_EDITOR READ | Không | `true` | Chỉ caller có SID ROLE_EDITOR tương ứng |
| Grant Alice WRITE | Không | `true` | Không suy ra Alice READ |
| Grandparent grant READ, parent không match, child inherit | Không | `true` ở cả hai cạnh | Có thể đọc từ grandparent |

Trong hierarchy nhiều cấp, cờ kế thừa ở **từng chặng** phải được kiểm tra, không chỉ leaf.

### Thay đổi parent/inheritance

`MutableAcl` hỗ trợ:

```java
MutableAcl child =
        (MutableAcl) aclService.readAclById(childObjectIdentity);

Acl parent = aclService.readAclById(folderObjectIdentity);

child.setParent(parent);
child.setEntriesInheriting(true);
aclService.updateAcl(child);
```

Đây là đoạn tích hợp cần `MutableAclService`, identity phù hợp và quyền quản trị ACL. Thao tác `setParent` cần một ACL object; không phải tự ghi một chuỗi folder ID. Việc thay đổi parent và flag phải được persist, sau đó **đọc lại** ACL để test, không chỉ assert trên object trong bộ nhớ.

## 6. ACE từ chối: đừng nhầm “không được cấp” với “explicit deny”

ACE có cấu trúc như:

```text
objectIdentity: demo.Document#44
sid: PrincipalSid("alice")
permission: BasePermission.READ (mask 1)
granting: false
```

Nó khác hoàn toàn với **không có ACE**. Với một permission READ và SID Alice, strategy mặc định trả `false` khi gặp ACE deny phù hợp. Nếu không tìm thấy ACE nào phù hợp, nó có thể thử parent; nếu vẫn thiếu, ném `NotFoundException`.

Các trường hợp cần tách:

- **Explicit deny trực tiếp:** child có ACE matching/granting=false.
- **Explicit deny kế thừa:** parent có ACE deny, child không có ACE matching, bật inheritance.
- **Missing permission:** không có ACE matching; chưa phải explicit deny.
- **ACE grant cho SID khác:** Alice không tự nhận quyền dành cho Bob.
- **ACE với mask khác:** Deny WRITE không tự deny READ, trừ khi policy khác xác định điều đó.

**Không viết quy tắc tự chế** “nếu tồn tại bất kỳ deny ACE của người dùng thì chặn mọi hành động”. Deny gắn với permission/SID/resource và được strategy áp dụng theo thuật toán.

### Cẩn trọng khi có nhiều permissions

Ví dụ method gọi:

```java
acl.isGranted(
        List.of(BasePermission.WRITE, BasePermission.READ),
        List.of(new PrincipalSid("alice")),
        true);
```

Với `DefaultPermissionGrantingStrategy`, permission list là các **lựa chọn có thứ tự**, không mặc định là phép AND “phải có cả WRITE lẫn READ”. Nếu WRITE bị deny nhưng READ được grant và strategy tiếp tục với permission kế tiếp, kết quả **có thể vẫn là true**.

Nếu nghiệp vụ yêu cầu **cả hai**:

```java
boolean canRead = acl.isGranted(
        List.of(BasePermission.READ), sids, true);

boolean canWrite = acl.isGranted(
        List.of(BasePermission.WRITE), sids, true);

boolean canReadAndWrite = canRead && canWrite;
```

Đây là đoạn minh họa; phải xử lý `NotFoundException`/`UnloadedSidException` rõ ràng, không coi missing là grant. Trong API service, có thể xây wrapper fail-closed và tái sử dụng.

## 7. Cần hiểu thứ tự SID, permission và ACE

JavaDoc `DefaultPermissionGrantingStrategy` ghi rõ **thứ tự danh sách permissions và SIDs cực kỳ quan trọng**. Thuật toán mặc định xét từng permission theo thứ tự; trong mỗi permission, xét từng SID theo thứ tự; tìm ACE đầu tiên khớp với cặp permission/SID, rồi dùng cờ granting hoặc thử permission kế tiếp tùy quyết định.

Một caller có thể có:

```text
PrincipalSid("alice")
GrantedAuthoritySid("ROLE_EDITOR")
```

Ví dụ một ACE deny READ cho Alice và một ACE grant READ cho ROLE_EDITOR trên cùng object. **Đừng kết luận bằng khẩu hiệu** “deny luôn thắng” hoặc “role grant luôn thắng”. Thứ tự SID và ACE có thể làm kết quả khác; vì thế test phải dùng đúng `SidRetrievalStrategy` và thứ tự mà production tạo ra.

Ma trận regression:

| Các ACE | Tham số `sids` | Điều cần khóa bằng test |
| --- | --- | --- |
| Alice grant READ, role không có ACE | [Alice, ROLE_EDITOR] | READ grant |
| Alice deny READ, role grant READ | [Alice, ROLE_EDITOR] | Kết quả theo strategy/ưu tiên được chọn |
| Alice deny READ, role grant READ | [ROLE_EDITOR, Alice] | Có khác kết quả không? |
| Grant READ, deny WRITE | [Alice] | READ và WRITE riêng |
| Deny WRITE, grant READ | [Alice], permissions [WRITE, READ] | Một grant khác có làm request qua không? |
| Hai ACE cùng SID + permission, granting khác nhau | [Alice] | ACE đầu tiên nào có hiệu lực? |

Với các tình huống nhiều SID/ACE, test **đường ACL thật**, không chỉ so sánh số permission mask bằng bitwise AND. Quy tắc cấp quyền phải được nhóm phát triển ghi rõ thành contract trước khi viết tests.

## 8. API kiểm tra quyền và việc xử lý exception

Điểm cấp thấp:

```java
boolean granted = acl.isGranted(
        List.of(BasePermission.READ),
        List.of(new PrincipalSid("alice")),
        true);
```

`Acl.isGranted` có thể:

- Trả `true` khi có quyết định grant.
- Trả `false` khi có quyết định deny.
- Ném `NotFoundException` khi không thể đưa ra quyết định có thẩm quyền vì thiếu ACE phù hợp.
- Ném `UnloadedSidException` khi ACL chỉ load một số SIDs, và caller hỏi SID chưa được load.

Một helper **fail-closed** ở tầng application:

```java
boolean allowed(Acl acl, Permission permission, List<Sid> sids) {
    try {
        return acl.isGranted(List.of(permission), sids, true);
    } catch (NotFoundException | UnloadedSidException missingDecision) {
        return false;
    }
}
```

Đây là đoạn tích hợp (cần import `Acl`, `Permission`, `Sid`, `NotFoundException`, `UnloadedSidException` và `List`). Đừng dùng `catch (Exception) { return true; }`. Với lỗi DB/network, production có thể trả HTTP 503 hoặc lỗi nội bộ thay vì 403, nhưng **không mặc định cho phép** truy cập.

**Lưu ý:** `AclPermissionEvaluator`, `PermissionEvaluator` hoặc tầng web có thể chuyển thiếu ACL/deny thành boolean hay `AccessDeniedException` tùy implementation. Unit test `Acl.isGranted` và integration test `hasPermission` có thể cần assert **khác loại output** dù cùng chính sách từ chối. Không đánh tráo hai cấp API khi đặt tên test.

## 9. Bộ test Java 17 với AclImpl thật, không cần database

Phần này sử dụng **`AclImpl` thật của Spring Security**, `DefaultPermissionGrantingStrategy` thật, nhưng mock `AclAuthorizationStrategy` chỉ để bỏ qua kiểm tra quyền **quản lý ACL khi dựng fixture**. Vì mục tiêu là test read authorization, nó không kiểm tra cơ chế ai được phép sửa ACL; vấn đề đó cần test riêng ở mức integration.

Bộ JUnit 5 có thể chạy bằng Maven với Java 17. Nó bao gồm direct grant, direct deny, parent inheritance on/off, deny ở child chặn grant cha, kế thừa permission khác, missing ACE và nhiều permission.

### 9.1. Cấu trúc thư mục

```text
acl-test-lab/
├── pom.xml
└── src/test/java/demo/
    └── AclDecisionTest.java
```

Không cần class `@SpringBootApplication`. Đây là **unit test trực tiếp của mô hình ACL**; không cần H2 hoặc bốn bảng database.

### 9.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>acl-test-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-acl</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Spring Boot BOM quản lý phiên bản Spring Security và dependency kiểm thử. Khi dùng trong dự án khác, đồng bộ phiên bản Spring Security ACL với các module Spring Security còn lại. Không trộn bừa ACL 6.x với core 7.x nếu chưa kiểm tra compatibility.

### 9.3. Tệp AclDecisionTest.java

```java
package demo;

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
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.acls.model.Sid;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class AclDecisionTest {

    private final Sid alice = new PrincipalSid("alice");
    private final Sid bob = new PrincipalSid("bob");
    private final Sid owner = new PrincipalSid("acl-owner");

    // Chỉ mock quyền SỬA fixture ACL; quyền ĐỌC thật dùng strategy của Spring.
    private final AclAuthorizationStrategy mutationAuthorization =
            mock(AclAuthorizationStrategy.class);

    private final PermissionGrantingStrategy decisionStrategy =
            new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());

    private AclImpl acl(long id, Acl parent, boolean inherit) {
        return new AclImpl(
                new ObjectIdentityImpl("demo.Document", id),
                id,
                mutationAuthorization,
                decisionStrategy,
                parent,
                null,           // null nghĩa là không giới hạn tập SIDs đã load
                inherit,
                owner
        );
    }

    private boolean check(Acl acl, Sid sid,
                          org.springframework.security.acls.model.Permission p) {
        return acl.isGranted(List.of(p), List.of(sid), true);
    }

    @Test
    void directGrantIsScopedToOneObject() {
        AclImpl first = acl(50L, null, false);
        AclImpl second = acl(51L, null, false);

        first.insertAce(0, BasePermission.READ, alice, true);

        assertTrue(check(first, alice, BasePermission.READ));

        assertThrows(NotFoundException.class,
                () -> check(second, alice, BasePermission.READ));
    }

    @Test
    void explicitDenyDiffersFromMissingPermission() {
        AclImpl doc = acl(52L, null, false);
        doc.insertAce(0, BasePermission.READ, alice, true);
        doc.insertAce(1, BasePermission.WRITE, alice, false);

        assertTrue(check(doc, alice, BasePermission.READ));
        assertFalse(check(doc, alice, BasePermission.WRITE));

        // Bob không có ACE; không phải explicit deny dành cho Bob.
        assertThrows(NotFoundException.class,
                () -> check(doc, bob, BasePermission.READ));
    }

    @Test
    void parentGrantIsInheritedWhenEnabled() {
        AclImpl folder = acl(10L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(42L, folder, true);

        assertTrue(check(child, alice, BasePermission.READ));
    }

    @Test
    void parentLinkWithoutInheritingDoesNotGrant() {
        AclImpl folder = acl(11L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(43L, folder, false);

        assertThrows(NotFoundException.class,
                () -> check(child, alice, BasePermission.READ));
    }

    @Test
    void childDenyPreventsInheritedGrantForSamePermission() {
        AclImpl folder = acl(12L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(44L, folder, true);
        child.insertAce(0, BasePermission.READ, alice, false);

        assertFalse(check(child, alice, BasePermission.READ));
    }

    @Test
    void childDenyForWriteDoesNotDenyInheritedRead() {
        AclImpl folder = acl(13L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, true);

        AclImpl child = acl(45L, folder, true);
        child.insertAce(0, BasePermission.WRITE, alice, false);

        assertFalse(check(child, alice, BasePermission.WRITE));
        assertTrue(check(child, alice, BasePermission.READ));
    }

    @Test
    void directDenyInParentCanBeInherited() {
        AclImpl folder = acl(14L, null, false);
        folder.insertAce(0, BasePermission.READ, alice, false);

        AclImpl child = acl(46L, folder, true);

        assertFalse(check(child, alice, BasePermission.READ));
    }

    @Test
    void permissionListIsAlternativesNotAutomaticallyAnd() {
        AclImpl doc = acl(47L, null, false);
        doc.insertAce(0, BasePermission.WRITE, alice, false);
        doc.insertAce(1, BasePermission.READ, alice, true);

        assertTrue(doc.isGranted(
                List.of(BasePermission.WRITE, BasePermission.READ),
                List.of(alice),
                true));
    }
}
```

Giải thích các fixture:

- Constructor đầy đủ của `AclImpl` nhận `ObjectIdentity`, ID của ACL, `AclAuthorizationStrategy`, `PermissionGrantingStrategy`, parent ACL, danh sách SID đã load, cờ inheritance và owner.
- Với `loadedSids=null` trong ví dụ này, không giới hạn dữ liệu theo một phần SIDs. Trong tích hợp JDBC, có thể chọn load chỉ một tập SID; khi đó cần test `UnloadedSidException`.
- `mutationAuthorization` là mock nên `insertAce` không bị ngăn bởi quyền quản trị ACL; chỉ dùng trong unit test để dựng dữ liệu. Không thay authorization strategy thật bằng mock trong production.
- `check` gọi chính `Acl.isGranted` của Spring; không có phép bitwise tự chế thay cho framework.
- `administrativeMode=true` chỉ vô hiệu hóa audit từ check, không bỏ qua kiểm tra quyền.

### 9.4. Chạy và xác nhận kết quả

Tại thư mục `acl-test-lab` với JDK 17+ và Maven:

```bash
mvn -q clean test
```

Kết quả mong đợi: **8 test thành công, 0 failures và 0 errors**. Vì dùng `-q`, Maven có thể không in bảng tóm tắt như chế độ verbose; có thể kiểm tra file báo cáo Surefire trong `target/surefire-reports/`.

Chạy chi tiết hơn:

```bash
mvn test
```

Bộ test được thiết kế dựa trên API Spring Security 6.x và các trường hợp đã kiểm chứng từ JavaDoc; **không tuyên bố đã thực thi Maven trong môi trường soạn bài**. Nếu test khác kết quả sau khi đổi phiên bản hoặc strategy, cần tìm nguyên nhân thay vì chỉnh kỳ vọng để “xanh”.

### 9.5. Hạn chế của unit test này

Nó kiểm tra **hành vi thuật toán ACL trong bộ nhớ**, không chứng minh:

- Bốn bảng ACL JDBC tạo đúng.
- `JdbcMutableAclService` lưu và đọc lại ACE/inheritance đúng.
- `AclCache` được invalidate sau cấp/thu hồi quyền.
- `AclPermissionEvaluator` chuyển biểu thức `hasPermission` chính xác.
- `@PreAuthorize` chạy qua Spring proxy, hay HTTP status trả đúng.
- Quyền **sửa ACL** của người dùng thật có được bảo vệ.

Đó là lý do cần tầng integration test ở các phần sau.

## 10. Integration test với JdbcMutableAclService và database

Khi ứng dụng đã cấu hình `DataSource`, bốn bảng ACL, `AclCache`, `BasicLookupStrategy` và `JdbcMutableAclService`, test phải tạo resource và ACL ở database rồi đọc lại từ service.

Một fixture tạo ACL:

```java
ObjectIdentity folderOid =
        new ObjectIdentityImpl("demo.Folder", 10L);

ObjectIdentity docOid =
        new ObjectIdentityImpl("demo.Document", 42L);

Sid alice = new PrincipalSid("alice");

MutableAcl folder = aclService.createAcl(folderOid);
folder.insertAce(folder.getEntries().size(),
        BasePermission.READ, alice, true);
aclService.updateAcl(folder);

MutableAcl child = aclService.createAcl(docOid);
child.setParent(aclService.readAclById(folderOid));
child.setEntriesInheriting(true);
aclService.updateAcl(child);

// Đọc lại từ persistence layer, không chỉ dùng instance vừa mutate.
Acl reloaded = aclService.readAclById(docOid);
boolean inherited = reloaded.isGranted(
        List.of(BasePermission.READ),
        List.of(alice),
        true);
```

Đây là **đoạn tích hợp**, các imports và `aclService` do cấu hình ứng dụng cung cấp; cần có quyền quản trị ACL để gọi `insertAce` hoặc `setParent`. Các object IDs/type strings trong DB phải phù hợp với mapping `ACL_CLASS`. Test nên quản lý transaction/fixture teardown để không ảnh hưởng dữ liệu khác.

Các bước cần thực hiện trong integration test:

1. Dựng folder ACL với direct grant READ.
2. Dựng child ACL và parent relationship.
3. Bật `entriesInheriting=true`; lưu cả hai.
4. Clear/evict cache phù hợp hoặc reload theo hợp đồng để tránh assert trên object reference cũ.
5. Đọc ACL child bằng `AclService.readAclById` và assert READ grant.
6. Tắt `entriesInheriting`; lưu, load lại, assert không còn grant kế thừa.
7. Bật lại inheritance, thêm ACE deny READ tại child; lưu, reload, assert explicit deny.
8. Thay deny thành grant/xóa ACE; lưu, reload, assert hiệu lực mới.

**Đừng quên cleanup:** nếu `createAcl` chèn row ACL_OBJECT_IDENTITY, các test chạy song song cùng ID có thể vi phạm uniqueness. Dùng IDs riêng cho từng test, schema isolation hoặc rollback theo chiến lược của `JdbcMutableAclService`, không sửa ACL sản xuất.

### Tách kết quả JDBC khỏi kết quả mock

Unit test `AclImpl` chứng minh semantics trong bộ nhớ. Integration test JDBC chứng minh:

- ACE đã persist với `MASK` và `GRANTING` chính xác.
- `ACL_OBJECT_IDENTITY.PARENT_OBJECT` và `ENTRIES_INHERITING` đúng.
- `ACL_CLASS` và `ACL_SID` giữ đúng type/identity.
- Khi load lại từ DB, strategy vẫn trả cùng quyết định.
- Cache phản ánh policy mới sau update/delete.

Nếu update transaction bị rollback, ACL không nên đột nhiên có các thay đổi đã bị rollback sau reload. Kết quả chịu transaction manager và cache integration của ứng dụng, cần test cơ sở dữ liệu thật khi có consistency yêu cầu cao.

## 11. Kiểm thử `AclPermissionEvaluator` và method security

`AclPermissionEvaluator` đưa ACL permission vào SpEL của method security:

```java
@PreAuthorize("hasPermission(#p0, 'demo.Document', 'READ')")
public DocumentView getDocument(long documentId) {
    return repository.loadView(documentId);
}
```

Đoạn này là **snippet tích hợp**: `DocumentView` và `repository` thuộc ứng dụng, `@EnableMethodSecurity` và handler cấu hình evaluator phải tồn tại.

Test đúng phải gọi **Spring bean qua proxy**:

```java
@SpringBootTest
class DocumentSecurityIntegrationTest {

    @Autowired DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void inheritedReadIsAllowed() {
        assertDoesNotThrow(() -> service.getDocument(42L));
    }

    @Test
    @WithMockUser(username = "bob")
    void missingOrDeniedAclCannotRead() {
        assertThrows(AccessDeniedException.class,
                () -> service.getDocument(44L));
    }
}
```

Đây là **mã tích hợp cần app fixture**: phải có `DocumentService`, evaluator, method-security configuration, tài liệu và ACL đúng như data test. Không đưa snippet này vào project unit-test mục 9 rồi kỳ vọng chạy vì project đó không có Spring application, DB hay service domain.

### Hai loại lỗi cần assert khác nhau

Ở tầng ACL thấp, missing ACE có thể là `NotFoundException`. Khi đi qua `AclPermissionEvaluator` và method security, lỗi có thể được chuyển thành “không có permission”, rồi interceptor từ chối bằng `AccessDeniedException`. Test nên xác minh security behavior ở đúng tầng.

Nếu có HTTP controller, phản hồi 401/403/404 còn phụ thuộc authentication entry point và exception handling. Không đồng nhất `NotFoundException` ACL với HTTP 404: chúng là hai khái niệm khác nhau. Tránh tiết lộ sự tồn tại của resource không thuộc quyền caller khi thiết kế API.

## 12. Ma trận đầy đủ theo quyền trực tiếp, kế thừa và deny

| Case | Caller/SID | ACL trực tiếp | Parent | Inherit | Permission hỏi | Mong đợi |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Alice | Grant READ | Không | — | READ | `true` |
| 2 | Alice | Grant READ | Không | — | WRITE | Thiếu ACE → `NotFoundException` |
| 3 | Bob | Grant READ cho Alice | Không | — | READ | Không có grant Bob |
| 4 | Alice | Không | Grant READ Alice | On | READ | `true` |
| 5 | Alice | Không | Grant READ Alice | Off | READ | Không có grant |
| 6 | Alice | Deny READ | Grant READ Alice | On | READ | `false` |
| 7 | Alice | Deny WRITE | Grant READ Alice | On | READ | `true` qua parent |
| 8 | Alice | Không | Deny READ Alice | On | READ | `false` |
| 9 | Alice | Grant WRITE | Parent grant READ | On | WRITE | `true` trực tiếp |
| 10 | Alice | Grant WRITE | Parent grant READ | On | READ | `true` kế thừa |
| 11 | Alice | Không | Grandparent READ, parent không có ACE | On từng cạnh | READ | `true` |
| 12 | Alice | Không | Grandparent READ, parent inheritance Off | On tại child | READ | Không có grant |
| 13 | ROLE_EDITOR | Grant READ cho role | Không | — | READ | Grant cho người có SID role |
| 14 | Alice + role | Một SID deny, SID kia grant | Có hoặc không | Bất kỳ | READ | Kết quả theo SID order; cần test rõ |
| 15 | Alice | Deny WRITE, grant READ | Không | — | [WRITE, READ] | Có thể `true` do permission alternatives |
| 16 | Alice | Không | Không | — | READ | `NotFoundException` cấp thấp |
| 17 | SID chưa được load | ACL partial SID | Bất kỳ | Bất kỳ | READ | `UnloadedSidException` |
| 18 | Tenant B | Grant trên ObjectIdentity tenant A | Không | — | READ tenant B | Không được dùng ACL tenant A |

Phạm vi “mong đợi” của một số case thể hiện hành vi cấp thấp với `DefaultPermissionGrantingStrategy`. Khi dùng strategy tùy chỉnh, hãy thay expected theo contract của hệ thống và có regression tests đi kèm.

## 13. Dữ liệu nhiều SIDs và vấn đề ưu tiên

Hệ thống thường sử dụng `SidRetrievalStrategy` để suy ra một list SIDs từ `Authentication`:

```text
PrincipalSid("alice")
GrantedAuthoritySid("ROLE_EDITOR")
GrantedAuthoritySid("ROLE_EMPLOYEE")
```

Một tài liệu có thể có:

```text
ACE(ROLE_EDITOR, READ, true)
ACE(alice, READ, false)
```

Không nên kiểm tra đơn giản bằng:

```java
boolean anyGrant = acl.getEntries().stream()
        .anyMatch(ace -> ace.isGranting());
```

Đây là **phản ví dụ**: nó không xét permission, SID, parent, entry order hay cờ deny đúng cách; còn bỏ qua trường hợp ACL chỉ được load một phần SIDs.

Hãy:

- Xác nhận thứ tự SID production dùng.
- Xác nhận thứ tự permission list ở lời gọi `isGranted`.
- Xác nhận thứ tự ACE lưu trong ACL, nhất là khi cùng SID+permission có nhiều entry.
- Tránh thiết kế grant/deny trùng nhau không có chính sách ưu tiên.
- Test các tổ hợp allow/deny theo từng type, mỗi permission riêng; không khẳng định “deny luôn thắng” một cách tuyệt đối.
- Với policy “principal deny luôn hơn role grant”, hãy xác nhận strategy hiện tại thực hiện đúng; nếu không, tùy chỉnh hoặc chuẩn hóa entries theo một contract được kiểm thử.

Nên ưu tiên **tránh ACE trùng/conflicting** khi business không có yêu cầu rõ. Thiết kế ACL dễ hiểu hơn quan trọng hơn giảm vài dòng kiểm thử.

## 14. Test khi thay đổi chính sách: grant → deny và deny → grant

Một permission không cố định; admin có thể thay đổi.

Kịch bản A:

```text
t0: Document 42 có ACE Alice READ grant  -> allowed
t1: Admin thu hồi/xóa ACE hoặc đổi thành deny
t2: Alice gọi lại                   -> denied
```

Kịch bản B:

```text
t0: Document 44 có ACE Alice READ deny  -> denied
t1: Admin sửa/xóa ACE deny và cấp grant
t2: Alice gọi lại                    -> allowed (nếu policy cho phép)
```

Cần test ở **tầng storage + cache**:

1. Tạo ACL/ACE và commit.
2. Đọc bằng evaluator/service như production, assert kết quả ban đầu.
3. Cập nhật ACE với `MutableAclService`, commit transaction.
4. Kết thúc transaction cũ và **đọc lại** ACL từ service mới/đường gọi mới.
5. Assert kết quả sau thay đổi.
6. Kiểm tra cache không giữ grant đã thu hồi; kiểm tra nếu nhiều application instances.
7. Nếu rollback update ACL, quyết định không được đổi sau transaction đã rollback.

API `MutableAcl` hỗ trợ `updateAce(int, Permission)`, `deleteAce(int)`, `insertAce(...)`. Tùy phiên bản, đổi cờ granting có thể cần xóa và tạo lại ACE hoặc tái xây danh sách; **đừng tự nghĩ `updateAce` nhận boolean granting**, vì signature chỉ cập nhật Permission. Hãy kiểm tra API thực tế và giữ entry order đúng.

## 15. Kiểm thử ACL nhiều cấp và inheritance bị chặn ở giữa

Xét:

```text
Root Project
  ACE Alice READ grant
      |
      v
Folder A, entriesInheriting=true
  (không có ACE READ)
      |
      v
Document B, entriesInheriting=true
  (không có ACE READ)
```

Alice có thể được READ thông qua Root. Nhưng nếu **Folder A đặt entriesInheriting=false**, khi lookup từ Document B lên Folder A rồi không thể đi tiếp, grant Root không tự truyền xuống. Test nên tạo ít nhất ba cấp và tắt flag ở:

- Child trực tiếp.
- Parent trung gian.
- Parent root (nếu có parent khác).

Nếu tại Folder A có ACE Alice READ deny, Document B kế thừa và không có ACE riêng, kết quả phải là deny theo strategy thông thường. Nếu Document B có grant READ trực tiếp, cần test liệu grant child có hiệu lực trước deny parent trong mô hình đó; với strategy mặc định và một permission/SID, direct matching grant ở child quyết định mà không cần fallback parent.

**Lưu ý:** ACL inheritance là **policy hierarchy**, không tự động là Java class inheritance, ORM entity inheritance hay filesystem inheritance. Phải cấu hình parent ACL rõ.

## 16. Scope tài nguyên và multi-tenancy trong test

Một ObjectIdentity thông thường gồm type + ID, chẳng hạn:

```java
new ObjectIdentityImpl("demo.Document", 42L);
```

Nếu tenant A và tenant B đều có một document ID 42, cả hai **không được vô tình dùng chung ACL**. Hệ thống phải dùng ID duy nhất toàn cục hoặc mapping resource identity có tenant phù hợp. Trong test, cần hai tài nguyên với cùng local ID nhưng tenant khác, xác minh:

- Grant READ cho tenant A không cấp READ tenant B.
- Parent ACL của tenant A không được gán làm parent của document tenant B.
- SID/authority có tenant scope nếu nghiệp vụ cần.
- Cache key không khiến quyền của tenant A được dùng cho tenant B.
- Việc copy/chuyển document đổi parent phải cập nhật ACL/inheritance transactionally.

Đừng tin tenant lấy từ header do client tự đặt nếu identity chưa được xác thực. Việc unit test ACL grant/deny không thay thế toàn bộ kiểm thử tenant isolation.

## 17. Test concurrency, cache và giao dịch

Thao tác ghi tài liệu có thể xảy ra giữa hai lần kiểm tra quyền:

```text
T1: Alice có READ
T2: Admin thu hồi READ
T3: Alice tiếp tục request dài và đọc dữ liệu
```

ACL cache có thể giữ grant cũ. Nếu ứng dụng yêu cầu thu hồi quyền có hiệu lực ngay, phải xác định:

- Cache eviction khi `updateAcl`.
- Khả năng đồng bộ cache giữa nhiều instance.
- Phạm vi transaction và isolation.
- Thời gian tối đa quyền bị thu hồi vẫn có thể tồn tại ở cache/session.
- Quy tắc kiểm tra lại trước khi trả dữ liệu rất nhạy cảm hoặc ghi.
- Cơ chế tránh time-of-check/time-of-use, ví dụ khóa/optimistic version/conditional update ở repository.

Test có thể dùng hai transactions/threads độc lập và latches để sắp xếp thứ tự kiểm tra/cập nhật quyền. Không coi một unit test với `AclImpl` trong RAM là bằng chứng hệ thống phân tán xử lý revocation đúng.

**Sự cố DB/ACL service** cũng cần test. Fail-closed không nhất thiết là HTTP 403 cho mọi lỗi; có thể báo 503 theo API contract, nhưng không cấp quyền chỉ vì authorization backend timeout.

## 18. Chọn test layer phù hợp

| Tầng | Công cụ | Điều chứng minh | Điều chưa chứng minh |
| --- | --- | --- | --- |
| Unit model | `AclImpl` + default strategy + JUnit | Direct/inherited/deny semantics | DB schema, cache, Spring proxy |
| Unit wrapper | Mockito `AclService` + `AclPermissionEvaluator` | Mapping type/ID, SID, permission, missing ACL | DB thật |
| JDBC integration | H2/PostgreSQL + `JdbcMutableAclService` | Persist/reload/parent/entries/granting/cache | HTTP/method pointcut |
| Method security integration | `@SpringBootTest`, `@WithMockUser` | `@PreAuthorize(hasPermission...)` được gọi qua proxy | Toàn bộ HTTP response |
| HTTP integration | `MockMvc`/WebTestClient phù hợp runtime | Authentication, authorization, status, endpoint wiring | Race của DB production |
| Concurrency/contract | DB giống production, nhiều transactions | Revocation consistency, race/locking | Tất cả trạng thái mạng phân tán |

Không nên gom một bộ test thành “unit test” rồi mô tả nó chứng minh toàn bộ hệ thống ACL. Cần test ở hai phía: **đúng thuật toán** và **đúng kết nối framework/persistence**.

## 19. Những lỗi dễ bỏ sót

**1. Chỉ kiểm tra quyền trực tiếp.** Bỏ qua quyền kế thừa và flag `entriesInheriting`; có thể vô tình mở hoặc khóa sai tài liệu.

**2. Có parent là mặc định inherit.** Không đúng: phải xem `entriesInheriting` ở child.

**3. Coi missing ACE như explicit deny.** Ở API thấp, missing có thể ném `NotFoundException`; explicit deny trả false.

**4. Coi mọi deny ACE luôn thắng mọi grant.** Sai nếu không xét thứ tự permissions/SIDs và strategy; test các trường hợp conflict.

**5. Chỉ gửi một SID trong test nhưng production có principal + roles.** Bỏ sót grant/deny chồng nhau.

**6. Dùng `List.of(READ, WRITE)` như yêu cầu có cả hai.** Thường đây là tập quyền thay thế theo `Acl.isGranted`; nếu business cần AND phải kiểm tra riêng.

**7. Suy ra permission từ số mask mà quên granting.** Mask=1 có thể là grant READ hoặc deny READ tùy ACE.

**8. Mock cả `PermissionGrantingStrategy` rồi nói đã test ACL.** Mock strategy không chứng minh thuật toán Spring. Unit ở mục 9 dùng strategy thật, chỉ mock quyền sửa fixture.

**9. Không persist/reload sau khi `setParent` hoặc `insertAce`.** Chỉ assert object Java trong RAM không chứng minh dữ liệu JDBC.

**10. Quên cache invalidation sau `updateAcl`.** Có thể stale allow khi quyền đã bị thu hồi.

**11. Dùng test quyền một object để suy ra quyền mọi object.** Mỗi `ObjectIdentity` có ACL khác nhau, tenant có thể khác.

**12. Dùng `@WithMockUser` nhưng gọi `new Service()`.** Test bỏ qua AOP method security. Phải inject bean Spring và gọi qua proxy.

**13. Quên type của `ObjectIdentity`.** `"demo.Document"` và `"Document"` khác nhau nếu ACL_CLASS được lưu khác; test phải cùng một convention.

**14. Nuốt `NotFoundException`/DB error rồi trả true.** Tạo fail-open nghiêm trọng.

**15. Dùng một ACE deny để “xóa” quyền mà không hiểu thứ tự.** Khi có nhiều ACE cùng SID/permission hoặc ACL cha, cần kiểm thử semantic thực.

**16. Thay `PermissionGrantingStrategy` mà không chạy regression.** Quyền trực tiếp, inheritance, conflict và composite masks đều có thể thay đổi.

**17. Test Mockito quá xa thực tế.** Nếu chỉ mock `AclService.readAclById` và định nghĩa `isGranted()` trả true, bạn mới kiểm tra flow gọi, chưa kiểm tra ACL rules.

## 20. Checklist khi đưa ACL vào production

- [ ] Test trực tiếp GRANT, explicit DENY, không có ACE cho từng permission.
- [ ] Test đúng SID principal và SID authority/role.
- [ ] Test `getParentAcl` cùng `entriesInheriting=true/false`.
- [ ] Test deny ở child so với grant ở parent trên cùng permission/SID.
- [ ] Test deny permission A không vô tình deny permission B.
- [ ] Test quyền nhiều cấp: parent, grandparent và chặn inheritance giữa đường.
- [ ] Test conflict khi có nhiều SID hoặc nhiều ACE cùng permission.
- [ ] Test thứ tự permissions, không nhầm danh sách permission với AND.
- [ ] Test `NotFoundException`/`UnloadedSidException` và fail-closed.
- [ ] Test type+ID, multi-tenant, không dùng ACL của resource khác.
- [ ] Test create/grant/deny/revoke/parent change qua JDBC rồi **reload**.
- [ ] Test cập nhật cache và quyền sau commit/rollback.
- [ ] Test `AclPermissionEvaluator` và Spring-managed method proxy.
- [ ] Test quyền quản trị ACL (ai được thay đổi ACE), không mock phần đó trong integration test.
- [ ] Test race condition/thu hồi quyền nếu dữ liệu nhạy cảm.
- [ ] Có tài liệu contract strategy, quyền ưu tiên, và quy định audit.

**Kết luận:** Một hệ thống ACL đúng không chỉ “có ACE grant”. Nó phải phân biệt **quyền trực tiếp**, **kế thừa chỉ khi cấu hình đúng**, **ACE từ chối**, **không tìm thấy quyết định**, **các SIDs và permission có thứ tự**, và **policy sau khi lưu/thu hồi quyền**. Unit test với `AclImpl` thật nên được nối tiếp bằng JDBC/method-security integration tests để chứng minh hành vi đến tận entry point của ứng dụng.

## Tài liệu tham khảo chính thức

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [Spring Security 6.5 — AclImpl JavaDoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html)
- [Spring Security 6.5 — Acl interface JavaDoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html)
- [Spring Security 6.5 — DefaultPermissionGrantingStrategy JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
