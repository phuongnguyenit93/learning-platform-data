# Kiểm thử ACL trực tiếp, kế thừa, cache và thu hồi quyền

## 1. Mục tiêu và phạm vi

Bài học tập trung vào **kiểm thử quyết định cấp quyền trên từng đối tượng (object-level authorization)** bằng Spring Security ACL. Sau bài này, bạn có thể thiết kế bộ ca kiểm thử chứng minh: quyền gán trực tiếp hoạt động; quyền từ ACL cha chỉ được kế thừa khi cấu hình cho phép; các mục cache không làm lộ quyền đã bị thu hồi; và thao tác thu hồi có hiệu lực đối với đúng người, đúng đối tượng, đúng thời điểm.

ACL (Access Control List) gắn với **một đối tượng nghiệp vụ cụ thể**, chẳng hạn tài liệu 2002, thay vì chỉ một đường dẫn HTTP. Một ACL chứa các ACE (Access Control Entry). Mỗi ACE kết hợp **SID** (principal hoặc authority), **Permission** (READ/WRITE/...) và trạng thái **grant/deny**. Quyết định phải xét đồng thời danh tính đang truy cập, đối tượng đích và quyền được yêu cầu.

Phân biệt bốn vấn đề thường bị trộn lẫn:

- **Quyền trực tiếp:** ACE nằm ngay trong ACL của đối tượng đang được truy cập.
- **Kế thừa:** ACL của đối tượng con tham chiếu ACL cha và bật cờ kế thừa.
- **Cache:** ACL và danh sách ACE có thể được giữ trong bộ nhớ để giảm truy vấn; cache phải phản ánh dữ liệu đúng sau thay đổi.
- **Thu hồi quyền:** xóa/đổi ACE hoặc chặn quyền trực tiếp/kế thừa; phải kiểm chứng ở điểm thực thi quyền, không chỉ ở màn hình quản trị.

**Giới hạn:** Bài này kiểm thử ACL trong Spring Security và nơi tích hợp với method security. Cơ chế xác thực, cấu hình filter chain và chính sách phân quyền URL chỉ được nhắc tới ở những chỗ tác động đến việc xác minh kết quả.

## 2. Mô hình cần nắm trước khi viết test

| Thành phần | Trách nhiệm | Điều cần xác minh |
| --- | --- | --- |
| **ObjectIdentity** | Khóa đối tượng theo loại + ID nghiệp vụ | Tài liệu 2002 không nhận nhầm ACL của 2003 |
| **Sid** | Danh tính người dùng (**PrincipalSid**) hoặc nhóm/quyền (**GrantedAuthoritySid**) | Đúng username, authority; không rò quyền sang người khác |
| **Permission** | Quyền theo bit mask, ví dụ **BasePermission.READ/WRITE** | Đúng permission; READ không tự đồng nghĩa với WRITE |
| **AccessControlEntry** | Một quy tắc grant/deny gắn với SID và Permission | Đúng ACE được tìm, đúng trạng thái cấp/từ chối |
| **Acl / MutableAcl** | Tập ACE của đối tượng, liên kết cha, cờ kế thừa | Quyền trực tiếp, quyền cha, bật/tắt kế thừa |
| **AclService / MutableAclService** | Đọc, tạo, cập nhật, xóa ACL bền vững | Trạng thái sau ghi được đọc lại từ lưu trữ |
| **AclCache** | Cache ACL theo ID nội bộ/ObjectIdentity | Cache hit, eviction và không trả quyền lỗi thời |
| **AclPermissionEvaluator** | Nối ACL vào biểu thức **hasPermission(...)** | Quyết định ACL thực sự chặn/cho phép nghiệp vụ |

Với cài đặt JDBC mặc định, dữ liệu thường ở bốn bảng: **ACL_CLASS**, **ACL_SID**, **ACL_OBJECT_IDENTITY**, **ACL_ENTRY**. Khóa ID trong bảng ACL_OBJECT_IDENTITY khác với ID nghiệp vụ: phải xác định đúng cặp loại đối tượng và ID. **Owner của ACL không mặc nhiên có mọi quyền READ/WRITE**; đừng suy diễn quyền truy cập nghiệp vụ từ thuộc tính owner.

Quy tắc kế thừa có hai điều kiện đồng thời: **getParentAcl() != null** và **isEntriesInheriting() == true**. Có liên kết cha không đồng nghĩa đã kế thừa. Để kiểm thử, đọc lại cấu hình ACL và thực hiện quyết định truy cập trên đối tượng con.

### Cách quyết định quyền hoạt động

Với **DefaultPermissionGrantingStrategy** của Spring Security ACL, thứ tự **danh sách Permission** và **danh sách Sid** ảnh hưởng đến phép đánh giá. Bộ đánh giá tìm ACE khớp theo quyền và SID trên ACL hiện tại. Nếu có ACE grant khớp, có thể cho phép; ACE deny khớp là một kết quả từ chối cụ thể. Khi **không tìm thấy ACE khớp nào tại ACL con**, bộ đánh giá mới thử ACL cha nếu kế thừa được bật. Nếu hết chuỗi cha vẫn không có ACE phù hợp, **Acl.isGranted(...)** có thể ném **NotFoundException**; điều này khác với kết quả **false** từ một ACE deny. Với ACL chỉ tải một tập SID, còn có **UnloadedSidException**. Cả tình huống không xác định quyền và dữ liệu SID thiếu đều không được mặc nhiên chuyển thành allow.

Không sử dụng quy tắc rút gọn “deny luôn thắng mọi grant” cho mọi trường hợp: thứ tự permission/SID, vị trí ACE, chiến lược xét quyền và tập SID được tải mới xác định kết quả. Khi có nhiều ACE xung đột, hãy cố định thứ tự đầu vào và kiểm thử chính cấu hình đang chạy.

## 3. Bộ dữ liệu thử nghiệm có kiểm soát

Giả sử có một thư mục cha **Folder:100**, tài liệu con **Document:2002**, tài liệu độc lập **Document:2003**, người dùng **alice**, **bob**, **eve** và nhóm **ROLE_REVIEWER**.

Trạng thái khởi tạo:

1. Folder:100 có ACE **bob → READ → grant**.
2. Document:2002 có parent là Folder:100, **entriesInheriting=true**, chưa có ACE READ riêng cho bob.
3. Document:2003 không liên quan đến Folder:100 và không có ACE READ cho bob.
4. Có một ACE **alice → WRITE → grant** gán trực tiếp trên Document:2002.
5. Nếu thử authority, đưa bob vào ROLE_REVIEWER và kiểm thử một ACE authority riêng; luôn phân biệt tên principal và tên authority trong fixture.

Giả định khi kiểm tra hành vi “không có ACE”: tầng gọi ứng dụng từ chối theo **fail closed**; tùy API và chính sách che giấu tài nguyên, kết quả HTTP có thể là 403 hoặc 404. Không tự cho rằng phương thức **Acl.isGranted(...)** sẽ trả false trong mọi trường hợp thiếu ACE.

| Mã test | Đối tượng | SID | Quyền | Biến thể | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| D1 | Document:2002 | alice | WRITE | ACE trực tiếp grant | Allow |
| D2 | Document:2002 | alice | READ | Không có ACE tương ứng | Không allow; xử lý NotFound an toàn |
| D3 | Document:2003 | alice | WRITE | Khác ObjectIdentity | Không allow |
| I1 | Document:2002 | bob | READ | Có parent, inheritance=true | Allow do ACL cha |
| I2 | Document:2002 | bob | READ | inheritance=false | Không allow |
| I3 | Document:2002 | bob | READ | Child có ACE trực tiếp deny READ | Deny tại child, không dùng grant từ parent |
| I4 | Document:2002 | bob | READ | Gỡ deny tại child; parent vẫn grant | Allow do kế thừa trở lại |
| I5 | Document:2002 | eve | READ | Cùng đối tượng, SID khác | Không allow |
| R1 | Document:2002 | bob | READ | Xóa grant READ của bob ở parent; child không có ACE riêng | Không allow sau commit + đọc mới |
| R2 | Document:2002 | bob | READ | Có direct grant READ ở child; chỉ thu hồi ở parent | Vẫn allow ở child: cần thu hồi cả grant trực tiếp |
| C1 | Document:2002 | bob | READ | Cache đã warm rồi thu hồi parent | Kết quả sau thu hồi không còn allow |
| C2 | Document:2002 | bob | READ | 2 instance ứng dụng | Instance khác cũng không được dùng cache lỗi thời |

Đối với mỗi dòng, ghi lại **setup → hành động → điểm kiểm tra → expected**. Tạo fixture riêng giữa các test để không phụ thuộc thứ tự; cùng một test có thể cố ý đổi trạng thái để chứng minh trước và sau.

## 4. Kiểm thử quyền trực tiếp

Bắt đầu với một ACL mới cho Document:2002, không có parent hoặc tắt kế thừa. Thêm ACE grant READ cho alice rồi gọi **isGranted([READ], [PrincipalSid("alice")], true)**: phải allow. Đổi sang WRITE khi không có ACE WRITE: phải là trạng thái không có quyền, không thể suy từ READ. Đổi SID sang eve và ObjectIdentity sang Document:2003: đều không được nhận quyền của alice trên 2002.

Tiếp theo tạo một ACE deny với **một quyền khác** (ví dụ WRITE) hoặc test riêng cho cùng một cặp SID/Permission. Xác minh **false** khi deny thực sự khớp, trong khi trường hợp không có ACE phù hợp dẫn đến **NotFoundException** ở tầng ACL. Hành vi cụ thể của biểu thức **hasPermission(...)** cần được kiểm thử thêm vì nó bọc kết quả/ngoại lệ của tầng ACL.

Các assertion quan trọng: kiểm tra **cả mặt dương và âm**, quyền không lan sang SID hoặc object khác, không trộn READ/WRITE, và mỗi test biết rõ ACE nào đang quyết định.

## 5. Kiểm thử kế thừa từ ACL cha

Tạo ACL cha với ACE bob:READ=grant. Tạo ACL con có **setParent(parent)** và **setEntriesInheriting(true)**; con không có ACE READ cho bob. Khi hỏi READ trên con, expected allow từ cha. Sau đó lần lượt:

1. Gọi **setEntriesInheriting(false)** và đánh giá lại: child không còn nhận quyền READ từ cha.
2. Bật lại inheritance; chèn ACE **bob:READ=deny** trực tiếp tại child: expected deny, dù parent grant.
3. Gỡ ACE deny tại child; parent vẫn grant: expected allow lại.
4. Thu hồi grant từ parent; child vẫn kế thừa nhưng không có quyền để kế thừa: expected không allow.
5. Thêm grant READ trực tiếp tại child rồi lại thu hồi parent: child vẫn allow từ quyền riêng; đây là điều kiện kiểm tra quan trọng khi người dùng nói “đã thu hồi nhưng vẫn vào được”.

Đừng bỏ sót trường hợp parent có nhiều tầng (Folder tổ chức → Folder nhóm → Document) và kiểm thử khi một tầng ở giữa tắt inheritance. Tránh chu trình parent và giới hạn quyền cập nhật cây ACL cho người/role quản trị được phép.

## 6. Mẫu unit test chạy trên Spring Security ACL

Ví dụ dưới đây kiểm tra **thuật toán xét quyền ACL trong bộ nhớ**, không dùng database, HTTP hoặc cache phân tán. Đặt file ở **src/test/java/example/AclDecisionTest.java** trong một dự án Java 17+ có các dependency **spring-security-acl** và **spring-boot-starter-test** (theo BOM của dự án). Lambda **(acl, changeType) -> {}** cố ý bỏ qua kiểm tra quyền *chỉnh sửa ACL* trong fixture test; ứng dụng thực tế phải dùng AclAuthorizationStrategy phù hợp và kiểm thử riêng quyền quản trị.

~~~java
package example;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;

import static org.junit.jupiter.api.Assertions.*;

class AclDecisionTest {
    private static AclImpl acl(String type, long id) {
        return new AclImpl(
                new ObjectIdentityImpl(type, id),
                id,
                (ignoredAcl, ignoredChangeType) -> { },
                new ConsoleAuditLogger());
    }

    private static boolean granted(AclImpl acl, Sid sid, Permission permission) {
        return acl.isGranted(List.of(permission), List.of(sid), true);
    }

    @Test
    void directGrantDenyAndIsolation() {
        Sid alice = new PrincipalSid("alice");
        Sid eve = new PrincipalSid("eve");
        AclImpl doc = acl("example.Document", 2002);

        doc.insertAce(0, BasePermission.READ, alice, true);
        assertTrue(granted(doc, alice, BasePermission.READ));
        assertThrows(NotFoundException.class,
                () -> granted(doc, alice, BasePermission.WRITE));
        assertThrows(NotFoundException.class,
                () -> granted(doc, eve, BasePermission.READ));

        doc.insertAce(1, BasePermission.WRITE, alice, false);
        assertFalse(granted(doc, alice, BasePermission.WRITE));
        assertThrows(NotFoundException.class,
                () -> granted(acl("example.Document", 2003),
                              alice, BasePermission.READ));
    }

    @Test
    void inheritanceLocalDenyAndSwitch() {
        Sid bob = new PrincipalSid("bob");
        AclImpl parent = acl("example.Folder", 100);
        AclImpl child = acl("example.Document", 2002);

        parent.insertAce(0, BasePermission.READ, bob, true);
        child.setParent(parent);
        child.setEntriesInheriting(true);
        assertTrue(granted(child, bob, BasePermission.READ));

        child.setEntriesInheriting(false);
        assertThrows(NotFoundException.class,
                () -> granted(child, bob, BasePermission.READ));

        child.setEntriesInheriting(true);
        child.insertAce(0, BasePermission.READ, bob, false);
        assertFalse(granted(child, bob, BasePermission.READ));

        child.deleteAce(0);
        assertTrue(granted(child, bob, BasePermission.READ));
    }

    @Test
    void revokeInheritedGrantAndKeepDirectGrant() {
        Sid bob = new PrincipalSid("bob");
        AclImpl parent = acl("example.Folder", 100);
        AclImpl child = acl("example.Document", 2002);
        parent.insertAce(0, BasePermission.READ, bob, true);
        child.setParent(parent);
        child.setEntriesInheriting(true);

        assertTrue(granted(child, bob, BasePermission.READ));
        parent.deleteAce(0);
        assertThrows(NotFoundException.class,
                () -> granted(child, bob, BasePermission.READ));

        child.insertAce(0, BasePermission.READ, bob, true);
        assertTrue(granted(child, bob, BasePermission.READ));
    }

    @Test
    void cacheEntryCanBeFoundAndEvicted() {
        AclCache cache = new SpringCacheBasedAclCache(
                new ConcurrentMapCache("acl-tests"),
                new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger()),
                (ignoredAcl, ignoredChangeType) -> { });
        AclImpl doc = acl("example.Document", 2002);

        cache.putInCache(doc);
        assertNotNull(cache.getFromCache(doc.getObjectIdentity()));
        cache.evictFromCache(doc.getObjectIdentity());
        assertNull(cache.getFromCache(doc.getObjectIdentity()));
    }
}
~~~

Đây là các kiểm thử **in-memory**: case thu hồi xác minh việc thay đổi ACE làm thay đổi quyết định trong một đối tượng ACL, còn case cache chỉ kiểm tra API **put/get/evict**. **Chúng chưa chứng minh** rằng dịch vụ JDBC đã commit, tự invalidate đúng ACL con, hay node khác không giữ giá trị cũ. Các khẳng định đó thuộc bài integration test phía dưới.

Với Gradle trong dự án đã khai báo các dependency trên, chạy từ thư mục project:

~~~bash
./gradlew test --tests "example.AclDecisionTest"
~~~

Trên Windows sử dụng **gradlew.bat** thay **./gradlew**. Không có một dòng stdout cố định nào được hứa hẹn, vì kết quả hiển thị phụ thuộc Gradle/JUnit và mức log; điều kiện đạt là bốn test pass. Nếu code ứng dụng sử dụng chính sách cấp quyền tùy biến, phải thay kỳ vọng theo triển khai đã cấu hình.

## 7. Integration test: persistence, method security và database

Unit test thuần ACL là điều kiện cần, nhưng không đủ cho tính đúng đắn của hệ thống. Với ứng dụng thực tế, chạy integration test có **JdbcMutableAclService**, **BasicLookupStrategy**, **AclCache**, một **DataSource** thật hoặc H2/Testcontainers có schema ACL tương ứng, cấu hình **AclPermissionEvaluator**, và method security. Với Spring Security dùng annotation, một cấu hình tiêu biểu là **@EnableMethodSecurity** kết hợp **DefaultMethodSecurityExpressionHandler.setPermissionEvaluator(new AclPermissionEvaluator(aclService))**. Đây là cách nối quyết định ACL vào **hasPermission(...)**; kiểm thử qua chính method được bảo vệ, tránh chỉ tự gọi helper của test.

Ví dụ biểu thức nghiệp vụ (đoạn minh họa, cần khớp tên method, loại đối tượng và cấu hình trong dự án):

~~~java
@PreAuthorize("hasPermission(#documentId, 'example.Document', 'READ')")
public Document readDocument(long documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Các bước test end-to-end bắt buộc:

1. Trong transaction setup, tạo ACL cho Folder:100, thêm ACE bob READ grant, **updateAcl(parent)**; tạo ACL cho Document:2002, thiết lập parent và cờ kế thừa, **updateAcl(child)**. Commit fixture trước khi kiểm thử quyền ở transaction mới. **createAcl(...)** chỉ tạo ACL rỗng; sửa ACE trên object chưa đồng nghĩa đã ghi database.
2. Với Authentication của bob, gọi service/method bảo vệ Document:2002 và xác nhận thành công. Với eve hoặc Document:2003, xác nhận từ chối. Nếu test API, dùng MockMvc/WebTestClient theo web stack và assert HTTP status theo chính sách API.
3. Đọc lại parent từ **aclService.readAclById(parentOid)**, tìm đúng index ACE theo SID + Permission + loại grant, gọi **deleteAce(index)**, rồi **mutableAclService.updateAcl(parent)**. Commit. Tránh hard-code index ACE khi nhiều ACE.
4. Dùng **Authentication mới** và transaction/EntityManager mới gọi lại đúng method trên Document:2002. Expected từ chối. Đọc ACL con qua service sau cập nhật để phát hiện giá trị cache cũ. Không dùng lại biến **AclImpl** đã thay đổi trong setup làm bằng chứng.
5. Lặp lại kiểm thử với quyền direct tại child, với cờ inheritance=false, và với parent có nhiều tầng. Đoạn revocation ở bước 3 chỉ thu hồi grant của parent; nếu child có grant độc lập thì expected vẫn cho phép.

Mẫu thao tác thu hồi thông qua service (đoạn **không độc lập**, minh họa một phần method test/service; biến **mutableAclService**, **parentOid**, **bob** phải được khởi tạo từ fixture):

~~~java
MutableAcl fresh = (MutableAcl) mutableAclService.readAclById(parentOid);
int aceIndex = -1;
for (int i = 0; i < fresh.getEntries().size(); i++) {
    AccessControlEntry ace = fresh.getEntries().get(i);
    if (ace.getSid().equals(bob)
            && ace.getPermission().getMask() == BasePermission.READ.getMask()
            && ace.isGranting()) {
        aceIndex = i;
        break;
    }
}
if (aceIndex < 0) {
    throw new IllegalStateException("Expected parent READ grant is missing");
}
fresh.deleteAce(aceIndex);
mutableAclService.updateAcl(fresh);
~~~

Đừng kiểm tra sự tồn tại của ACE trong bảng rồi kết luận quyền đã bị thu hồi: phải kiểm tra **quyết định truy cập cuối cùng**, vì quyền có thể còn đến từ ACE khác hoặc từ ACL con. Đồng thời, quy định rõ transaction boundary trong test để không đọc dữ liệu chưa commit.

## 8. Kiểm thử cache: warm → mutate → read mới

**SpringCacheBasedAclCache** là adapter cho Spring Cache. Cache có thể giữ ACL được tra bằng ObjectIdentity hoặc ID nội bộ. Với dịch vụ JDBC mặc định, **JdbcMutableAclService.updateAcl(...)** có logic xóa cache của ACL được sửa và các ACL con có liên quan; vẫn phải kiểm tra bằng integration test với phiên bản/triển khai của dự án. Khi dùng custom MutableAclService, lookup strategy, cache phân tán hoặc nhiều lớp cache ứng dụng, không được tự giả định có cùng hành vi.

Thiết kế bài kiểm thử:

- **Cold read:** làm trống cache của fixture, gọi READ → expected allow; xác nhận ACL được nạp.
- **Warm read:** gọi lại cùng SID/ObjectIdentity/Permission → expected allow; nếu muốn đo số query/hit, dùng spy/metrics có kiểm soát, không gắn vào thời gian chạy không ổn định.
- **Mutation:** qua **MutableAclService.updateAcl(...)** thu hồi ACE cha, commit transaction.
- **Post-mutation:** đọc lại ACL con qua **AclService**, gọi hasPermission/method bảo vệ bằng request mới → expected từ chối. Điều này mới kiểm tra được lỗi **stale authorization**.
- **Child invalidation:** nếu đổi ACL cha, kiểm tra cả ít nhất một đối tượng con đã được cache trước đó. Nếu chính sách tùy biến yêu cầu tự evict descendant, test phải chứng minh đoạn đó được thực thi.
- **Cross-node:** trong môi trường từ hai instance trở lên, làm warm cache ở node B, thu hồi ở node A, gọi lại B. Xác định kỳ vọng nhất quán tức thời hay một ngưỡng trễ được phê duyệt; với thu hồi quyền nhạy cảm, thiết kế nên hạn chế/loại bỏ cửa sổ cho phép cũ.

Ma trận tối thiểu:

| Thời điểm | DB ACL cha | Cache con | Kỳ vọng kiểm tra |
| --- | --- | --- | --- |
| T0 | grant bob READ | Chưa nạp | bob được READ |
| T1 | grant bob READ | Đã nạp | bob được READ |
| T2 | grant đã xóa và commit | Có nguy cơ stale | Hệ thống phải invalidate/đảm bảo kết quả mới |
| T3 | không còn grant phù hợp | Đọc lại | bob bị từ chối |
| T4 | thêm grant lại có kiểm soát | cache được làm mới | bob được READ trở lại, không mắc kẹt deny cũ |

**Không dùng Thread.sleep để hy vọng cache tự hết hạn** như một chứng minh duy nhất. Hãy kích hoạt cơ chế invalidation thực tế, dùng clock giả nếu có TTL, quan sát sự kiện và xác minh quyết định truy cập. Đối với Spring Cache phân tán, cần xác nhận eviction được truyền tới mọi nơi và kiểm thử đường lỗi khi event bị mất hoặc retry.

## 9. Thu hồi quyền: ba dạng thường gặp

| Cách thay đổi | Ví dụ | Kết quả cần hiểu và test |
| --- | --- | --- |
| **Xóa ACE grant** | Bỏ bob READ khỏi parent | Nếu child không có grant khác: không còn READ; có thể rơi vào NotFound |
| **Thêm ACE deny trực tiếp** | Child deny bob READ trong khi parent grant | Child trả deny từ ACE tương ứng; không fallback sang grant cha cho cùng quyết định đó |
| **Tắt kế thừa** | Child entriesInheriting=false | Loại bỏ mọi grant chỉ đến từ parent; direct grant trên child vẫn tồn tại |

Thu hồi quyền truy cập **không đồng nghĩa xóa tài liệu** và không đồng nghĩa **deleteAcl(...)**. **deleteAcl(objectIdentity, deleteChildren)** xóa cấu trúc ACL và có thể ảnh hưởng con; sử dụng với chủ đích rõ ràng. Đối với một quyền, thường cần thao tác ở ACE/parent/inheritance đúng vị trí rồi **updateAcl(...)**.

Nên kiểm tra cả hai chiều: **grant → revoke → deny** và **deny → grant lại → allow**. Kiểm tra sau thu hồi bằng principal cũ trên phiên đăng nhập/token cũ lẫn phiên mới nếu yêu cầu sản phẩm đặt ra; permission object-level của ACL có thể thay đổi độc lập với token, nhưng các layer cache decision hoặc token claim có thể gây stale. Ghi nhận ai đã sửa, đối tượng nào, quyền nào, thời điểm commit và kết quả kiểm tra sau commit.

## 10. Kiểm thử tính đầy đủ và an toàn

**Identity và isolation:** dùng ít nhất hai principal, hai object cùng class, hai quyền. Chứng minh không rò quyền giữa tenant, kể cả khi objectId trùng ở tenant khác (nếu multi-tenant, tenant phải nằm trong mô hình tra cứu/kiểm soát quyền). Bao gồm cả PrincipalSid và GrantedAuthoritySid. Kiểm tra thứ tự SID cụ thể khi một user có nhiều authority.

**Lỗi và cạnh:** ACL chưa tồn tại, parent null, inheritance tắt, ACE deny, SID chưa được tải, thiếu quyền sửa ACL, parent nhiều cấp, xóa ACE không tồn tại, hai cập nhật đồng thời, transaction rollback, lỗi database/cache. Kỳ vọng an toàn là **không cấp quyền dựa trên trạng thái chưa xác minh**; phân biệt lỗi hạ tầng với từ chối hợp lệ để log/monitor đúng.

**Quyền quản trị ACL:** người thường không thể gọi create/update/delete ACL trái phép. Test thay đổi ownership, parent, ACE, auditing dưới Authentication không đủ quyền; riêng unit fixture ở phần 6 đã vô hiệu hóa authorization strategy của thao tác sửa, vì thế bắt buộc có integration test dùng strategy thật.

**Điểm thực thi quyền:** test method security hoặc API nơi quyền được cưỡng chế. Nếu có repository list/search trả nhiều bản ghi, kiểm tra dữ liệu trả về cũng lọc theo quyền để tránh lộ đối tượng qua endpoint khác; đừng chỉ test endpoint đọc một ID.

**Concurrency:** revoke và request đồng thời phải có quy tắc nhất quán. Chốt thời điểm có hiệu lực (ví dụ sau commit), xác định rủi ro race/TOCTOU. Nếu quyết định yêu cầu mức đảm bảo mạnh hơn eventual consistency, triển khai và test cần thiết kế cache/transaction tương ứng.

**Quan sát:** log ID nghiệp vụ, SID, permission, kết quả, nguồn ACE direct/inherited và dấu vết cache (hit/miss/invalidate) ở mức an toàn; tránh log token hoặc dữ liệu nhạy cảm. Dùng correlation ID khi theo dõi luồng thu hồi giữa nhiều node.

## 11. Checklist QA cho mỗi ca test

| Câu hỏi | Phải trả lời được |
| --- | --- |
| Quyền đang xét là gì? | READ, WRITE... và mask chính xác |
| Ai đang truy cập? | PrincipalSid/GrantedAuthoritySid và tập SID thực tế |
| Đối tượng nào? | Loại đối tượng, ID và tenant nếu có |
| Quyền đến từ đâu? | ACE trực tiếp, ACL cha hay nhiều tầng |
| Cờ inheritance và parent là gì? | Kiểm tra đúng cả hai điều kiện |
| Có ACE khác đang cấp quyền không? | Không nhầm revoke một ACE với revoke toàn bộ đường cấp quyền |
| Trạng thái DB đã commit chưa? | Có readback ở transaction mới |
| Cache nào đang được sử dụng? | ACL cache, custom cache, node khác |
| Điểm kiểm tra cuối là gì? | Acl.isGranted, hasPermission hoặc request nghiệp vụ |
| Kết quả âm là gì? | Explicit deny, NotFound/UnloadedSid hay lỗi hạ tầng |
| Điều gì thay đổi sau revoke? | Trước: allow; sau: deny; tái grant: allow |
| Test có độc lập không? | Fixture riêng và cleanup, không phụ thuộc thứ tự |

Mẫu Given–When–Then cho một regression quan trọng:

> **Given:** bob có READ từ ACL cha, ACL con đã được load vào cache.  
> **When:** quản trị viên thu hồi ACE READ của bob ở cha và transaction commit.  
> **Then:** lần truy cập mới của bob đến tài liệu con bị chặn, kể cả khi truy cập qua một instance đã warm cache từ trước.  
> **And:** alice vẫn giữ quyền WRITE trực tiếp trên tài liệu, và tài liệu khác không bị đổi quyền ngoài ý muốn.

## 12. Các lỗi phổ biến và cách khắc phục

1. **Test chỉ gọi getEntries() và khẳng định quyền:** danh sách ACE tại con không bao gồm ACE kế thừa. Dùng **isGranted(...)** hoặc điểm thực thi quyền để kiểm tra quyết định.
2. **Nhầm no-match với explicit deny:** **NotFoundException** không phải cùng trạng thái **false**. Kiểm tra cách evaluator hoặc application chuyển kết quả thành deny; không cho phép khi thiếu dữ liệu.
3. **Đổi object ACL trong bộ nhớ nhưng không updateAcl:** unit test có thể pass trong khi DB và cache vẫn cũ. Integration test phải gọi service ghi, commit rồi đọc lại.
4. **Gỡ grant cha mà quên grant trực tiếp ở con:** quyền còn hiệu lực là đúng theo ACL; xem toàn bộ đường cấp quyền, không kết luận cache lỗi vội.
5. **Chỉ xóa cache của cha:** cache của con có thể giữ ảnh hưởng kế thừa; xác minh cơ chế invalidation descendant và cache trên node khác.
6. **Test cache bằng độ trễ thời gian:** kết quả ngẫu nhiên và không chứng minh được event invalidation; dùng hành động xác định, spy/metrics và assertion quyền sau mutation.
7. **Dùng một người và một tài liệu:** không phát hiện lỗi nhầm SID/ObjectIdentity hoặc rò dữ liệu tenant. Mỗi suite phải có đối chứng âm.
8. **Giữ nguyên SecurityContext/transaction giữa các giai đoạn:** kết quả có thể đến từ state cũ; tách request/transaction và tạo lại Authentication khi cần.
9. **Cố đoán thứ tự ACE, SID hoặc semantics deny:** cần kiểm tra **DefaultPermissionGrantingStrategy** của phiên bản đang dùng và chính xác input; không xếp chồng grant/deny trùng cặp một cách mơ hồ.
10. **Chỉ test cache ở một JVM:** shared DB không bảo đảm cache tại instance khác tự nhận thay đổi. Dùng bài test đa instance và cơ chế phát sự kiện phù hợp.

## 13. Bài tập thực hành và tiêu chí hoàn thành

**Bài tập A – ACL trực tiếp:** tạo hai tài liệu, hai người dùng; thêm grant READ cho alice ở tài liệu thứ nhất và deny WRITE cho bob. Viết assertion cho allow, deny, no-match và object isolation.

**Bài tập B – ACL kế thừa:** thêm thư mục cha grant READ cho bob, tài liệu con có inheritance=true. Viết test cho ba biến thể inheritance on/off, deny ở child, gỡ deny và fallback về parent; bổ sung grandparent.

**Bài tập C – thu hồi có cache:** load quyền từ cache ở child, thu hồi ACE READ tại parent bằng **MutableAclService**, commit, kiểm tra mới qua **hasPermission(...)**, đo cache hit/miss/eviction. Lặp lại khi chạy hai instance và khi child có direct grant riêng.

Một bài làm đạt yêu cầu khi **mọi thay đổi quyền đều có kiểm tra trước–sau ở tầng authorization thực**, không còn stale allow sau thời điểm hiệu lực đã cam kết, có đầy đủ ca trực tiếp/kế thừa/cache/thu hồi, và chứng minh không làm thay đổi quyền của SID hoặc đối tượng không liên quan.

## Tài liệu đối chiếu

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [API – DefaultPermissionGrantingStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
- [API – MutableAclService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html)
- [API – JdbcMutableAclService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html)
- [API – SpringCacheBasedAclCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html)
