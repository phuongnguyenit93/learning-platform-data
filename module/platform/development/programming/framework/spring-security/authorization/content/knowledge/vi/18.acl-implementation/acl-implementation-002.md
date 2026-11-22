# BasicLookupStrategy và cách tải ACL trong Spring Security

## 1. Tại sao cần một chiến lược tải ACL?

Trong Spring Security, **Access Control List (ACL)** là tập hợp những quyền được cấp hoặc từ chối trên **một đối tượng nghiệp vụ cụ thể**. Một tài liệu số 42, ví dụ, có thể có nhiều ACE (Access Control Entry): Alice được READ, Bob bị từ chối WRITE, nhóm kiểm toán được READ. Để kiểm tra `hasPermission(...)`, hệ thống phải **tìm đúng ACL**, đọc ACE/SID/mask/quan hệ cha rồi áp dụng chính sách quyết định.

Với vài tài liệu, một lần truy vấn không có vẻ đáng kể. Nhưng trong màn hình có hàng trăm tài liệu, việc truy vấn ACL lặp lại cho từng đối tượng dễ tạo **N+1 queries**, tải lại các ACE giống nhau hoặc vượt giới hạn kết nối. Một ACL còn có thể có **ACL cha** với quyền kế thừa, làm vấn đề tải dữ liệu phức tạp hơn.

Spring Security chia vấn đề thành các thành phần:

- `AclService`: giao diện nghiệp vụ **đọc** ACL theo `ObjectIdentity`.
- `JdbcAclService`: một triển khai `AclService` dùng JDBC.
- `LookupStrategy`: chiến lược **tìm và lắp ráp** ACL từ nơi lưu trữ cho nhiều ObjectIdentity.
- `BasicLookupStrategy`: triển khai mặc định dựa trên **ANSI SQL**, cố gắng tối ưu bằng truy vấn theo lô (batch).
- `AclCache`: cache ACL đã tải, tránh lấy lại dữ liệu không đổi.
- `PermissionGrantingStrategy`: **đánh giá** ACE để quyết định grant/deny, không phải một chiến lược truy vấn.
- `AclPermissionEvaluator`: nối ACL với biểu thức Spring Security `hasPermission(...)`.

**Điểm trọng tâm:** `BasicLookupStrategy` chịu trách nhiệm **tải và dựng cấu trúc ACL**, không phải tự quyết định "Alice được đọc" theo một chính sách tùy ý. Quyết định cuối cùng thuộc `Acl.isGranted(...)`/`PermissionGrantingStrategy` và các điều kiện nghiệp vụ khác.

## 2. Luồng từ @PreAuthorize đến database

Một yêu cầu đọc tài liệu có thể đi theo luồng:

```text
HTTP GET /documents/42
        |
        v
Controller -> Spring-managed service proxy
        |
        v
@PreAuthorize("hasPermission(#id, 'Document', 'READ')")
        |
        v
AclPermissionEvaluator
        |
        v
AclService.readAclById(ObjectIdentity, sids)
        |
        v
JdbcAclService
        |
        v
LookupStrategy.readAclsById(List<ObjectIdentity>, List<Sid>)
        |
        +--> AclCache (ACL đã nạp)
        |
        +--> SQL qua DataSource (ACL/ACE/parent chưa có trong cache)
        |
        v
Acl đã có ObjectIdentity, owner, ACE, parent, inheritance
        |
        v
Acl.isGranted(...) / PermissionGrantingStrategy
        |
        +--> GRANT -> service method chạy
        |
        +--> DENY/thiếu bằng chứng -> method bị chặn
```

Luồng trên là sơ đồ khái niệm cho trường hợp method-security dùng ACL. Đường đi thực tế còn phụ thuộc version, cache hit, cách evaluator được cấu hình, dữ liệu SID và những lớp bảo mật khác. Không có yêu cầu HTTP vẫn có thể gọi service từ batch/job; ACL là cơ chế bảo vệ domain object chứ không lệ thuộc Servlet.

### Phân biệt rõ ba công việc

| Câu hỏi | Thành phần chính | Kết quả |
| --- | --- | --- |
| "Tôi cần ACL của Document 42" | `AclService` | `Acl` hoặc lỗi không tìm thấy |
| "Lấy ACL đó từ bảng nào, theo lô bao nhiêu, khôi phục ACE và cha thế nào?" | `LookupStrategy` / `BasicLookupStrategy` | Map `ObjectIdentity -> Acl` |
| "Alice có READ trên ACL này không?" | `Acl.isGranted` / `PermissionGrantingStrategy` | Grant, deny hoặc thiếu dữ liệu quyết định |

Tăng batch size không tự thay đổi grant/deny. Thay `PermissionGrantingStrategy` không tự làm giảm số truy vấn. Cần đặt tối ưu vào đúng tầng.

## 3. Dữ liệu nào được BasicLookupStrategy khôi phục?

Spring Security ACL thông dụng dùng bốn bảng:

| Bảng | Nội dung liên quan |
| --- | --- |
| `ACL_CLASS` | Danh tính loại domain object, ví dụ `com.example.Document` |
| `ACL_SID` | Principal hoặc granted authority được dùng làm SID |
| `ACL_OBJECT_IDENTITY` | Đối tượng, parent ACL, owner SID, `entries_inheriting` |
| `ACL_ENTRY` | Những ACE: SID, mask, granting, `ace_order` và cờ audit |

Một `ObjectIdentity` được xác định bởi **loại đối tượng** và **ID**. Hai đối tượng có cùng ID số 42 nhưng khác class phải là hai danh tính ACL khác nhau.

```java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ObjectIdentity;

ObjectIdentity document42 =
    new ObjectIdentityImpl(Document.class, 42L);
```

Đây là đoạn code **trong ứng dụng** có domain class `Document` và dependency `spring-security-acl`; không phải chương trình Java độc lập.

Kết quả tải ACL có thể gồm:

- ObjectIdentity và SID của owner ACL.
- Các ACE theo thứ tự được mô hình dữ liệu lưu trữ.
- `Permission` từ bit mask và `Sid` cho mỗi ACE.
- Thông tin parent ACL nếu có.
- Cờ `entriesInheriting`, mô tả có xét các ACE kế thừa từ parent hay không.
- Các cấu trúc phục vụ `Acl.isGranted(...)`, gồm strategy cho phép và audit.

Không nhầm **ACL owner** với **owner domain object**. Owner của ACL thường liên quan quyền quản trị/sửa ACL, không chứng minh một tài liệu trong database thuộc cùng principal. Tenant/ownership nghiệp vụ vẫn phải được kiểm tra bằng dữ liệu server đáng tin cậy.

## 4. Hợp đồng của LookupStrategy.readAclsById

Giao diện `org.springframework.security.acls.jdbc.LookupStrategy` có phương thức chính:

```java
Map<ObjectIdentity, Acl> readAclsById(
    List<ObjectIdentity> objects,
    List<Sid> sids
);
```

Ở đây:

- `objects`: danh sách ObjectIdentity cần tải; đây là đầu vào **bắt buộc**.
- `sids`: danh sách SID mà caller quan tâm. **Giao diện cho phép implementation tận dụng SIDs để tối ưu**.
- Kết quả là map từ `ObjectIdentity` tới `Acl` đã tìm được. Những object không có ACL có thể **không có key**.
- Hợp đồng `LookupStrategy` không yêu cầu tự ném `NotFoundException` khi thiếu ACL: có thể dùng nhiều LookupStrategy theo chuỗi hoặc dùng cơ chế tạo bổ sung.

**Khác biệt quan trọng:** `AclService.readAclById(...)` thông thường ném `NotFoundException` khi không tìm thấy ACL yêu cầu. Vì thế cần phân biệt:
 
1. Map kết quả ở **LookupStrategy** có thể thiếu một ObjectIdentity.
2. API **AclService** có thể chuyển tình huống thiếu dữ liệu thành `NotFoundException` theo hợp đồng của nó.
3. `Acl.isGranted(...)` trên **một ACL đã tồn tại** lại có thể ném `NotFoundException` vì không tìm ra ACE/SID/permission để quyết định.
4. Domain object tồn tại hay không còn là một truy vấn nghiệp vụ khác.

Không suy diễn một `NotFoundException` liên quan ACL có nghĩa "Document #42 không tồn tại". Càng không được coi trường hợp thiếu ACL là có quyền.

### Ví dụ gọi qua AclService

```java
import java.util.List;
import java.util.Map;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;

ObjectIdentity id42 = new ObjectIdentityImpl(Document.class, 42L);
ObjectIdentity id43 = new ObjectIdentityImpl(Document.class, 43L);

List<Sid> sids = List.of(
    new PrincipalSid("alice"),
    new GrantedAuthoritySid("ROLE_READER")
);

Map<ObjectIdentity, Acl> loaded =
    aclService.readAclsById(List.of(id42, id43), sids);
```

Đoạn này cần `aclService` được Spring inject, class `Document` và bản ghi ACL thực trong database. Tùy tình trạng ACL và hợp đồng dịch vụ, thao tác có thể ném `NotFoundException`; không mặc định mọi key luôn tồn tại. SID nên được tạo từ Authentication đã xác thực bằng `SidRetrievalStrategy` hoặc policy tin cậy, **không lấy tên người dùng do client gửi**.

Sử dụng `readAclsById(...)` thay vì gọi `readAclById(...)` liên tiếp trong một vòng lặp là cơ hội để **tải theo lô**. Nhưng mức tối ưu thực tế phải đo bằng SQL counters và kích thước dữ liệu, không chỉ dựa vào việc đổi tên method.

## 5. Chi tiết rất quan trọng: BasicLookupStrategy **bỏ qua** tham số sids

Javadoc `BasicLookupStrategy.readAclsById(...)` nêu rõ implementation này **hoàn toàn bỏ qua tham số `sids`**. Điều đó có các hệ quả thực tế:

1. Truyền danh sách `List.of(new PrincipalSid("alice"))` **không làm SQL chỉ lấy ACE của Alice**.
2. ACL được nạp với thông tin SID/ACE đầy đủ cho object, không phải một bản ACL rút gọn theo user.
3. `AclCache` của BasicLookupStrategy phải chứa **các ACL đầy đủ SID** theo thiết kế này.
4. Nếu mỗi object có hàng chục nghìn SID/ACE, chi phí I/O, object allocation và cache memory có thể lớn.
5. Nếu cần SID filtering thực sự vì lượng ACE cực lớn, bạn có thể cần **LookupStrategy tùy chỉnh**, với giao thức cache và xử lý unloaded SID được thiết kế lại.

Nhận định đúng:

```text
aclService.readAclById(document42, [PrincipalSid("alice")])
                     |
                     v
              BasicLookupStrategy
                     |
                     +-- sids: KHÔNG được dùng để lọc tại lookup
                     |
                     +-- nạp ACL/ACE với tất cả SID theo cách triển khai
                     |
                     v
      Acl đầy đủ -> đánh giá quyền của Alice sau đó
```

Nhận định **sai**: "Chỉ truyền SID hiện tại là đủ bảo đảm BasicLookupStrategy thực hiện SQL WHERE sid = current_user." Javadoc cảnh báo điều ngược lại.

Đây cũng là lý do phải phân biệt **tối ưu batch theo ObjectIdentity** với **tối ưu lọc theo SID**. BasicLookupStrategy hỗ trợ kiểu thứ nhất; nó không triển khai kiểu thứ hai.

### Tại sao nhà cung cấp chọn cách này?

Khi một ACL được cache dưới khóa ObjectIdentity, việc lưu **ACL đầy đủ** tránh tình huống:

- Alice tải ACL có chỉ ACE của Alice và lưu vào cache.
- Bob dùng cùng cache key, đọc bản ACL thiếu ACE của Bob.
- Hệ thống ra quyết định dựa trên một bản dữ liệu chưa đủ.

Bản ACL đầy đủ giúp kết quả độc lập khỏi caller đã khởi tạo cache entry. Nếu xây custom lookup lọc SID, phải giải quyết cache key gồm những thông tin nào, tải bổ sung SID ra sao và khi nào phát sinh `UnloadedSidException`, không chỉ thêm một điều kiện SQL.

## 6. BasicLookupStrategy thực hiện truy vấn như thế nào?

`BasicLookupStrategy` được thiết kế tương thích ANSI SQL và cố gắng truy xuất ACL tối ưu trong giới hạn schema quan hệ chuẩn hóa. Tài liệu Javadoc mô tả hai dạng truy vấn chính bên trong:

- `lookupPrimaryKeys`: tìm khóa nội bộ cho ObjectIdentity cần đọc.
- `lookupObjectIdentities`: tìm các ObjectIdentity liên quan và lắp dữ liệu ACL.

Hai câu truy vấn sử dụng **select clause và order-by clause chung**, nhưng có **where clause khác nhau**. Vì vậy class cho phép tùy chỉnh:

- `setSelectClause(String)`
- `setLookupPrimaryKeysWhereClause(String)`
- `setLookupObjectIdentitiesWhereClause(String)`
- `setOrderByClause(String)`

**Không đồng nghĩa mỗi lời gọi luôn đúng hai round-trip SQL**. Khi có cache hit, nhiều object, phân lô, quan hệ ACL cha và những bước khôi phục dữ liệu, số round-trip thực có thể khác. Hãy đo bằng datasource proxy/SQL metrics của ứng dụng.

Đặc biệt, thứ tự `ace_order` phải được bảo toàn. Kết quả grant/deny có thể thay đổi nếu thay `ORDER BY` sai, kể cả khi số dòng ACE không đổi.

### Sơ đồ dữ liệu

```text
ObjectIdentity: Document 42
        |
        +--> ACL_CLASS: "com.example.Document"
        |
        +--> ACL_OBJECT_IDENTITY
        |       id, object_id_identity=42
        |       owner_sid, parent_object, entries_inheriting
        |
        +--> ACL_ENTRY
                ace_order=0, sid=alice, mask=READ, granting=true
                ace_order=1, sid=ROLE_AUDITOR, mask=READ, granting=true
                ace_order=2, sid=bob, mask=WRITE, granting=false
                         |
                         v
                    Acl / ACE objects
                         |
                         v
              PermissionGrantingStrategy
```

Đây là mô hình minh họa, không phải bản sao SQL schema. Tên cột thực của DB và alias trong select/where clause phải theo schema và version.

**Nơi mở rộng:** nếu dữ liệu khổng lồ và database có hierarchical query hoặc materialized view, bạn có thể viết `LookupStrategy` khác. Spring Security không khuyến khích subclass trực tiếp `BasicLookupStrategy` vì class này **không hỗ trợ subclassing** theo Javadoc; hãy **implement LookupStrategy** nếu thật sự cần thay thuật toán.

## 7. Batch loading: gom nhiều ObjectIdentity

`BasicLookupStrategy` hỗ trợ `setBatchSize(int)`. Ý nghĩa là giới hạn quy mô các nhóm ObjectIdentity mà implementation xử lý trong quá trình lookup.

Ví dụ một trang danh sách có 125 tài liệu. Nếu ứng dụng gọi ACL cho từng đối tượng một lần, bạn có thể có rất nhiều lần lookup. Với batch size 50 và một lần gọi danh sách 125 IDs, các đối tượng chưa có cache có thể được chia thành những nhóm nhỏ hơn theo cơ chế của BasicLookupStrategy.

```text
125 ObjectIdentity cần kiểm tra
          |
          v
tách các đối tượng đã có cache
          |
          v
phần còn thiếu -> lookup theo batchSize=50
          |
          +-- batch 1: tối đa 50 ObjectIdentity
          +-- batch 2: tối đa 50 ObjectIdentity
          +-- batch 3: phần còn lại
          |
          v
Map<ObjectIdentity, Acl>
```

Sơ đồ diễn tả **cách tư duy về batch size**, không bảo đảm đúng 3 câu SQL hoặc đúng 3 DB round-trip. Số truy vấn còn phụ thuộc quan hệ cha, việc tra khóa nội bộ, cache và phiên bản.

Cấu hình cơ bản:

```java
BasicLookupStrategy lookup = new BasicLookupStrategy(
    dataSource, aclCache, aclAuthorizationStrategy, permissionGrantingStrategy
);
lookup.setBatchSize(50);
```

Đây là fragment cần các dependency Spring beans; `50` chỉ là một giá trị **ví dụ**, không phải số tối ưu mặc định cho mọi hệ thống. Đừng tự suy ra batch size càng lớn càng nhanh:

- Một số DB/driver giới hạn số bind parameters trong câu SQL `IN (...)`.
- ACL có nhiều ACE khiến lượng hàng trả về và memory rất lớn ngay cả với batch nhỏ.
- Parent ACL có thể phát sinh truy xuất thêm.
- Batch quá nhỏ làm nhiều round-trip; quá lớn gây câu SQL nặng và ảnh hưởng độ trễ tail.
- Cache hit ratio khác nhau giữa request thật và benchmark.

Hãy điều chỉnh sau khi đo số ObjectIdentity/request, số ACE/object, batch queries, latency, heap và tỉ lệ cache hit.

### Không coi batch lookup là tự động chữa N+1

Giả sử controller trả về 100 tài liệu rồi dùng:

```java
for (Document d : documents) {
    boolean canRead = permissionEvaluator.hasPermission(
        authentication, d.getId(), "Document", "READ");
    // ...
}
```

Đây là **mẫu minh họa tiềm ẩn N+1**, vì evaluator có thể gọi AclService riêng cho từng ID; batch size của một lần lookup với danh sách một phần tử không tự biến 100 lần gọi thành một bulk lookup.

Nếu cần lọc một tập lớn:

1. Trước hết xem có thể lọc ngay tại **query dữ liệu đã ràng buộc tenant/owner/ACL** không.
2. Nếu sử dụng module ACL, gom `ObjectIdentity` và gọi `AclService.readAclsById(...)` **theo lô** trước khi xét kết quả.
3. Bảo toàn thứ tự trả về nếu UI cần.
4. Không trả page count/total count chứa các đối tượng bị cấm.
5. Không xử lý dữ liệu private theo cách "tải tất cả rồi filter ở controller" nếu gây leak hoặc quá tải.

`@PostFilter("hasPermission(filterObject, 'READ')")` có thể hữu ích về mặt cú pháp nhưng vẫn cần đo hiệu năng với danh sách lớn và không thay thế truy vấn dữ liệu có scope.

## 8. Cache: phải lưu ACL **đầy đủ**, phải làm mới khi quyền đổi

Thư viện có giao diện `AclCache` với các thao tác thường dùng:

- `getFromCache(ObjectIdentity)` và `getFromCache(Serializable pk)`.
- `putInCache(MutableAcl)`.
- `evictFromCache(ObjectIdentity)` và `evictFromCache(pk)`.
- `clearCache()`.

Một implementation là `SpringCacheBasedAclCache`, bao bọc một `org.springframework.cache.Cache`. Tài liệu cho biết nó quản lý những trường transient bên trong `AclImpl` và giả định các ACL sử dụng cùng các instance `PermissionGrantingStrategy` và `AclAuthorizationStrategy`.

Ví dụ cache local trong ứng dụng mẫu:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.model.AclCache;

Cache springCache = new ConcurrentMapCache("aclCache");
AclCache aclCache = new SpringCacheBasedAclCache(
    springCache, permissionGrantingStrategy, aclAuthorizationStrategy);
```

Đây là **fragment cấu hình**, không chạy độc lập. `ConcurrentMapCache` dùng dữ liệu trong bộ nhớ của một JVM; phù hợp cho demo/test, không tự đồng bộ ACL giữa nhiều instance ứng dụng. Trong production có thể dùng cache chung có khả năng invalidation phù hợp, nhưng vẫn phải kiểm tra hành vi transaction và thu hồi quyền.

### Tại sao stale ACL là lỗi bảo mật?

Tình huống:

1. Bob có ACE grant READ trên Document 42.
2. ACL được cache, permission evaluator cho Bob đọc.
3. Admin thu hồi ACE của Bob trong DB.
4. Cache cũ còn grant READ.
5. Bob tiếp tục đọc trái với chính sách mới.

Giải pháp không chỉ là giảm TTL. Khi ACL thay đổi, cần **invalidation** thích hợp (và đồng bộ trên mọi node), kiểm tra quan hệ cha–con, race với transaction và xử lý cache lỗi an toàn. `JdbcMutableAclService` có hỗ trợ cập nhật và tương tác với cache, nhưng chương trình cũng phải xem các đường sửa dữ liệu khác (SQL trực tiếp, migration, admin tool, event replication) có làm cache stale không.

**Nguyên tắc:** cache là tăng tốc cho một quyết định bảo mật; việc quản lý lifecycle cache phải được xem như một phần của thiết kế phân quyền, không chỉ là tối ưu hiệu năng.

## 9. Parent ACL và entriesInheriting

Một `Acl` có thể có `getParentAcl()` và cờ `isEntriesInheriting()`. Mô hình dữ liệu cho phép tài liệu trong folder kế thừa ACE từ folder cha. `BasicLookupStrategy` phải dựng đủ cấu trúc liên quan để tầng đánh giá ACL sử dụng được parent khi chính sách cho phép.

```text
Folder A (parent ACL)
    |  ACE: ROLE_EDITOR -> READ grant
    |
    +-- Document 42 (child ACL)
          entriesInheriting = true
          ACE: Alice -> WRITE grant
```

Khi hỏi READ trên Document 42, nếu ACE của child không quyết định, `Acl.isGranted` có thể đi tiếp lên parent theo chiến lược và cờ inheritance. Khi `entriesInheriting=false`, parent không tự cấp quyền cho child.

**Cần phân biệt**:

- **Tải parent ACL**: một vấn đề về `LookupStrategy`/database/cache.
- **Có kế thừa quyền parent không**: cờ `entriesInheriting` và ngữ nghĩa của `Acl.isGranted`.
- **Quyền đọc entity dữ liệu**: vẫn cần xác minh tenant/owner/ACL nghiệp vụ; parent ACL cross-tenant phải được kiểm soát.

Parent ACL có thể tăng độ sâu truy xuất, lượng object cache và độ phức tạp invalidation. Tránh cấu trúc parent có cycle hoặc tham chiếu không hợp lệ; khi thay parent/inheritance flag, phải kiểm tra tác động các ACL con.

## 10. Cấu hình BasicLookupStrategy với JdbcMutableAclService

Dưới đây là **cấu hình thành phần** theo pattern tài liệu Spring Security, phù hợp dự án Spring Boot có `spring-security-acl`, `spring-jdbc`, Spring Cache, Spring Security Method Security và DataSource. Không phải một file Java chạy độc lập bằng `javac`; phải có schema ACL và dependency phù hợp.

```java
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
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclConfiguration {

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ACL_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {
        Cache springCache = new ConcurrentMapCache("aclCache");
        return new SpringCacheBasedAclCache(
            springCache, permissionGrantingStrategy, aclAuthorizationStrategy);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource, AclCache cache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {

        BasicLookupStrategy lookup = new BasicLookupStrategy(
            dataSource, cache, aclAuthorizationStrategy,
            permissionGrantingStrategy);
        lookup.setBatchSize(50);
        return lookup;
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource, LookupStrategy lookupStrategy,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookupStrategy, cache);
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Các điểm cần hiểu rõ:

1. **DataSource** do ứng dụng cung cấp. Những bảng ACL phải đã tồn tại và có schema phù hợp (đặc biệt khóa identity, SID, mask và `ace_order`).
2. **AclCache** dùng cùng `PermissionGrantingStrategy` và `AclAuthorizationStrategy` với `BasicLookupStrategy`.
3. **LookupStrategy** nhận DataSource/cache/authorization strategy/granting strategy; `setBatchSize(50)` là tùy chọn tune sau khi đo.
4. **JdbcMutableAclService** hỗ trợ đọc lẫn thay đổi ACL. Nếu chỉ cần đọc, `JdbcAclService(dataSource, lookupStrategy)` là lựa chọn khác.
5. **AclPermissionEvaluator** dùng `AclService`.
6. **Expression handler** đưa evaluator vào method-security SpEL. `@EnableMethodSecurity` bật infrastructure tương ứng.
7. Bean `AclAuthorizationStrategyImpl` với authority `ACL_ADMIN` minh họa quyền thực hiện các thao tác quản trị ACL; phải cân nhắc kỹ ai được cấp authority này. Nó không đồng nghĩa với quyền tự đọc mọi domain object.
8. Cache ví dụ là in-memory và **không được mặc định coi an toàn cho nhiều instance production** khi ACE có thể thay đổi từ node khác.
9. Nếu ứng dụng dùng schema/tên cột khác, cần điều chỉnh SQL hoặc mapping theo Javadoc, không copy config rồi đổi ngẫu nhiên một clause.

### Gắn vào service

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasPermission(#documentId, 'com.example.Document', 'READ')"
    )
    public Document readDocument(@P("documentId") Long documentId) {
        return repository.findById(documentId).orElseThrow();
    }
}
```

Đây là **class thuộc ứng dụng**, yêu cầu `DocumentRepository`, entity `Document` và dữ liệu ACL thật. Chuỗi `'com.example.Document'` phải khớp với `ObjectIdentity`/tên class được lưu trong `ACL_CLASS`. Dự án có namespace khác phải sửa chính xác. `@P` chỉ định tên biến để SpEL có thể tham chiếu.

Điểm quan trọng: `AclPermissionEvaluator` xử lý quyền ACL, nhưng **không thay** logic tenant, soft-delete hoặc ownership nghiệp vụ của query. Với dữ liệu nhiều tenant, cần kết hợp ACL với policy truy cập tài nguyên và truy vấn có scope tin cậy. Nếu evaluator báo từ chối, method security sẽ chặn trước method; việc trả HTTP 403 hay 404 là quyết định của tầng API, không phải của BasicLookupStrategy.

## 11. Tùy biến SQL mà không phá thứ tự và mapping

Javadoc cung cấp các setter để đổi select, where và order-by:

```java
lookup.setSelectClause(customSelect);
lookup.setLookupPrimaryKeysWhereClause(customPrimaryWhere);
lookup.setLookupObjectIdentitiesWhereClause(customIdentityWhere);
lookup.setOrderByClause(customOrderBy);
```

Đây là fragment **minh họa**, các biến trên phải được định nghĩa bằng chuỗi SQL phù hợp với schema và result-set mapping, không thể copy chạy độc lập. **Không sửa một clause riêng lẻ** nếu nó khiến select/order/where không còn nhất quán. Hai nhánh `lookupPrimaryKeys` và `lookupObjectIdentities` phải đưa ra dữ liệu cùng hệ thống alias và khóa.

Các nguyên tắc:

- Dùng alias/names chính xác mà trình mapper của BasicLookupStrategy yêu cầu.
- Không xóa `ace_order` khỏi `ORDER BY` một cách thiếu kiểm soát: thứ tự ACE có thể ảnh hưởng grant/deny.
- Đảm bảo khóa ACL_OBJECT_IDENTITY, ACL_CLASS và ACL_SID được nối đúng; không để lẫn object IDs giữa các class.
- Có test JDBC thật với object có nhiều ACE, nhiều SID, parent, ACL không tồn tại và nhiều lớp domain.
- Không ghép trực tiếp đầu vào từ HTTP vào SQL clause. Các setter này dành cho cấu hình SQL **do ứng dụng kiểm soát**, không phải tham số lọc của người dùng.
- Nâng cấp Spring Security có thể thay đổi cách mapper xử lý result set; kiểm tra regression tests trước khi tùy biến sâu.

### Class ID, ObjectIdentityGenerator và ConversionService

Một số schema ACL lưu `ACL_CLASS.ID` và định danh class theo cơ chế khác với default. `BasicLookupStrategy` có các điểm mở rộng như `setAclClassIdSupported(...)`, `setObjectIdentityGenerator(...)` và `setConversionService(...)`. Đây là những cấu hình nhằm khớp **mô hình định danh và kiểu ID trong database**.

Không bật `setAclClassIdSupported(true)` tùy tiện: phải chắc chắn schema và queries đang dùng cột ID của `ACL_CLASS` theo hợp đồng phiên bản. Nếu dự án dùng UUID/string ID, cần xem kỹ hỗ trợ `ObjectIdentity` và nhiều phần mặc định giả định ID thuận tiện với kiểu long; đừng ép cast để làm mất tính đúng đắn.

## 12. Thay chiến lược khi dữ liệu quá lớn

Theo Javadoc, BasicLookupStrategy:

- Nỗ lực tối ưu trong giới hạn **ANSI SQL** và schema chuẩn hóa.
- **Bỏ qua `sids`**.
- Không hỗ trợ subclassing.
- Cho phép điều chỉnh batch và một số mảnh SQL.

Nếu có hàng triệu ACL, một object chứa rất nhiều ACE, hoặc có phân cấp ACL cực sâu, những điều kiện này có thể không phù hợp. Các lựa chọn:

1. **Tối ưu truy vấn và index**: index khóa ObjectIdentity, foreign keys ACL_ENTRY, ACL_SID và `ace_order` khi phù hợp; kiểm tra execution plan trước.
2. **Bulk prefetch**: gom các ObjectIdentity trong một request để tránh N+1.
3. **Cache theo lớp**: cache ACL đầy đủ và vô hiệu hóa khi thu hồi quyền; định lượng memory/hit ratio.
4. **Custom LookupStrategy**: dùng query phù hợp database (materialized view, hierarchical query), và thiết kế chính xác xử lý parent, thứ tự ACE/SID, đối tượng thiếu, cache.
5. **Điều chỉnh mô hình dữ liệu**: khi nhiều đối tượng dùng cùng chính sách, cân nhắc ACL cha, group, hoặc quyền domain trực tiếp để giảm số ACE riêng lẻ.
6. **Truy vấn theo scope của nguồn dữ liệu**: với danh sách lớn, đôi khi dùng SQL/JPA query ràng buộc tenant/owner/ACL hiệu quả hơn tải đầy đủ ACL về application rồi lọc.

**Cảnh báo:** tùy biến lookup để load *chỉ một phần SID* là thay đổi ngữ nghĩa dữ liệu cache. Bạn phải xử lý `Acl.isSidLoaded(...)` và `UnloadedSidException` hợp lý; nếu cache key chỉ là ObjectIdentity nhưng nội dung thay đổi theo caller, có nguy cơ trả thiếu quyền hoặc kết quả không nhất quán. Với security, một tối ưu sai có thể nguy hiểm hơn chậm.

## 13. Java 17 chạy độc lập: mô phỏng batch và cache

Chương trình dưới đây **không sử dụng Spring Security**. Nó mô phỏng ý tưởng tải nhiều đối tượng theo lô và dùng cache. Mã không mô phỏng SQL của BasicLookupStrategy, parent ACL hoặc quy tắc grant/deny; nhiệm vụ là làm rõ vì sao **số lần gọi đơn lẻ khác với một lần gọi bulk**.

Tạo file `AclBatchLoadingDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AclBatchLoadingDemo {
    private final Map<Long, List<String>> database = Map.of(
        1L, List.of("alice:READ", "team:READ"),
        2L, List.of("bob:READ"),
        3L, List.of("alice:WRITE")
    );
    private final Map<Long, List<String>> cache = new LinkedHashMap<>();
    private int databaseBatches;

    Map<Long, List<String>> load(List<Long> requested, int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        Set<Long> uniqueIds = new LinkedHashSet<>(requested);
        List<Long> missingCache = new ArrayList<>();
        for (Long id : uniqueIds) {
            if (!cache.containsKey(id)) {
                missingCache.add(id);
            }
        }

        for (int start = 0; start < missingCache.size();
                start += batchSize) {
            int end = Math.min(start + batchSize, missingCache.size());
            List<Long> batch = missingCache.subList(start, end);
            databaseBatches++;
            for (Long id : batch) {
                List<String> aces = database.get(id);
                if (aces != null) {
                    cache.put(id, aces);
                }
            }
        }

        Map<Long, List<String>> result = new LinkedHashMap<>();
        for (Long id : uniqueIds) {
            if (cache.containsKey(id)) {
                result.put(id, cache.get(id));
            }
        }
        return result;
    }

    public static void main(String[] args) {
        AclBatchLoadingDemo demo = new AclBatchLoadingDemo();

        Map<Long, List<String>> first =
            demo.load(List.of(1L, 2L, 3L, 999L), 2);
        System.out.println("First: found=" + first.size()
            + ", batches=" + demo.databaseBatches);

        Map<Long, List<String>> second =
            demo.load(List.of(1L, 2L, 3L), 2);
        System.out.println("Second: found=" + second.size()
            + ", batches=" + demo.databaseBatches);

        demo.cache.remove(2L);
        Map<Long, List<String>> third = demo.load(List.of(2L), 2);
        System.out.println("After eviction: found=" + third.size()
            + ", batches=" + demo.databaseBatches);

        System.out.println("Cached IDs: " + demo.cache.keySet());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AclBatchLoadingDemo.java
java AclBatchLoadingDemo
```

Stdout:

```text
First: found=3, batches=2
Second: found=3, batches=2
After eviction: found=1, batches=3
Cached IDs: [1, 3, 2]
```

Phân tích:

- Lần đầu có bốn IDs và batch size 2, mô phỏng hai lần truy vấn theo lô; ID 999 không có dữ liệu nên không được thêm vào kết quả.
- Lần thứ hai chỉ hỏi các ID đã cache → không tạo batch database mới.
- Xóa cache cho ID 2 rồi gọi lại tạo một batch mới.
- Kết quả chỉ chứa IDs có ACL, không cố tạo một ACL rỗng cho 999.

**Giới hạn:** ứng dụng thật của Spring ACL dùng `ObjectIdentity` thay vì `Long` đơn lẻ, có query tìm primary key, ACL parent, ACE rows, cache keys nội bộ và nhiều vấn đề khác. Con số `batches` ở chương trình chỉ là số **vòng mô phỏng**, không phải số SQL queries Spring Security cam kết thực hiện. Chương trình cũng không xử lý thay đổi DB/cache giữa những lần gọi; trong production cần kế hoạch invalidation cụ thể.

## 14. Kiểm thử cần có cho BasicLookupStrategy

### Kiểm thử tải đúng dữ liệu

| Tình huống | Điều phải chứng minh |
| --- | --- |
| Một ObjectIdentity có ACL | Đọc được owner, ACE/SID/mask/grant và thứ tự đúng |
| Hai class dùng cùng ID số | Không lấy nhầm ACL giữa class |
| ACL có nhiều ACE khác SID | Không bỏ ACE chỉ vì sids đầu vào không chứa SID ấy ở BasicLookupStrategy |
| Danh sách SIDs bằng null | Lookup vẫn hoạt động theo hợp đồng hỗ trợ |
| ACL không có trong database | `LookupStrategy` trả map thiếu key; `AclService` xử lý not-found theo API |
| Một ACL có parent | Tham chiếu parent đúng và inheritance được đánh giá đúng |
| Parent có grant, child không match | Kết quả theo `entriesInheriting` và strategy |
| Deny và grant cùng permission/SID | Thứ tự ACE sau khi load không bị đảo |
| Mask tùy biến | `PermissionFactory` chuyển mask đúng |
| SID principal và granted authority | `createSid` khôi phục đúng loại SID |
| ID dạng long và ID custom | Mapping không bị trộn kiểu/giá trị |
| Đọc qua cache hit | Dữ liệu trả ra như lần đầu, không bị mất SID |
| Cập nhật ACE rồi đọc lại | Cache được làm mới, quyền thu hồi có hiệu lực |
| Nhiều object trong một lần đọc | Đúng dữ liệu từng object, không lẫn chéo |
| Object có rất nhiều ACE | Đo latency, rows, heap và cache size |
| Database outage | Không cấp quyền, lỗi hạ tầng được giám sát |

### Kiểm thử hiệu năng

- Bật thống kê SQL của datasource hoặc dùng datasource proxy/Hibernate statistics theo cấu trúc hệ thống.
- So sánh **N lần `readAclById`** với **một `readAclsById`** cho cùng tập ID, trong tình huống cache lạnh và cache nóng.
- Kiểm tra batch size 10, 50, 100 (giá trị thử nghiệm, không mặc định tối ưu), đo DB round-trips, rows/query, time/query.
- Đo trên dữ liệu nhiều ACE/SID và phân cấp parent, không chỉ mỗi ACL có một entry.
- Quan sát `AclCache` hit/miss/eviction và memory; test thu hồi quyền ở nhiều node.
- Kiểm tra SQL execution plan sau khi tùy chỉnh select/where/order-by.
- Đo p95/p99 latency của endpoint đang trả danh sách, tránh chỉ nhìn trung bình.
- Xác minh hiệu năng cải thiện **không thay đổi kết quả cấp quyền**.

### Kiểm thử security tích hợp

Bật `@EnableMethodSecurity` và gọi service **qua Spring-managed bean** để chắc chắn `@PreAuthorize` được thực thi; lời gọi `this.securedMethod()` trong cùng bean có thể bypass proxy. Dùng user có role/authority phù hợp, user khác tenant, anonymous, ACL đã revoke, ACL thiếu và parent inheritance bật/tắt.

Nếu controller trả 403 sau deny, đừng lấy HTTP status làm chứng cứ hoàn hảo về việc chưa lộ dữ liệu. Kiểm tra service/repository chưa trả document trái quyền, không có side effect và cache không giữ bản ACL lỗi thời.

## 15. Lỗi triển khai và cách sửa

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Nghĩ truyền `sids` làm BasicLookupStrategy lọc ACE theo caller | Dự tính sai rows, memory và cache | Đọc Javadoc: implementation bỏ qua `sids` |
| Cache một ACL chỉ chứa SID của user đầu tiên theo cùng ObjectIdentity key | User khác nhận ACL không đủ dữ liệu | Cache ACL đầy đủ hoặc thiết kế custom strategy/cache key an toàn |
| Gọi evaluator từng item của list lớn | N+1, latency cao | Bulk lookup hoặc query dữ liệu đã scope |
| Coi batch size là số SQL queries | Đo sai hiệu năng | Dùng SQL logging/counters thật |
| Chọn batch size cực lớn không đo | Giới hạn bind parameter, heap và DB bottleneck | Tune theo DB/driver và ACE distribution |
| Không tải parent hoặc không xét inheritance | Kết quả quyền sai | Test parent và cờ `entriesInheriting` |
| Tự ý sửa `ORDER BY` bỏ ACE order | Grant/deny thay đổi | Giữ thứ tự và regression test |
| Tự viết SQL theo HTTP parameter | Có nguy cơ injection và lộ dữ liệu | Cấu hình SQL tĩnh/kiểm soát ở server |
| Nghĩ no ACL tương đương no business object | Lẫn lỗi, có thể rò rỉ resource existence | Phân biệt ACL not-found và domain not-found |
| Bắt mọi exception rồi cho phép | Fail-open | Deny an toàn, phân loại lỗi hạ tầng |
| Cập nhật ACL nhưng quên cache invalidation | Quyền bị thu hồi vẫn được dùng | Evict/invalidate nhất quán |
| Gắn cache local ở cluster và tin mọi node cập nhật ngay | Stale ACL giữa các node | Dùng chiến lược invalidation phân tán/consistency |
| Subclass BasicLookupStrategy để đổi thuật toán | Không được hỗ trợ theo Javadoc | Implement `LookupStrategy` riêng |
| ACL owner bị coi là domain owner | Rò rỉ đối tượng khác tenant | Tách domain policy và ACL administration |
| Chỉ có unit test mô phỏng batch | Không biết API/SQL thực tế có đúng | Integration test với schema và database thật |

## 16. Checklist trước khi chạy production

1. **Đã có bảng ACL đúng schema chưa?** `ACL_CLASS`, `ACL_SID`, `ACL_OBJECT_IDENTITY`, `ACL_ENTRY` và indexes phù hợp.
2. **ObjectIdentity có ổn định không?** Class + ID, dữ liệu kế thừa, định danh dùng long hay custom ID.
3. **LookupStrategy có đúng implementation không?** BasicLookupStrategy không lọc theo `sids`.
4. **Đã có batch lookup chưa?** Không phụ thuộc vào việc gọi từng item trong vòng lặp.
5. **Batch size được đo hay chỉ đoán?** Benchmark cache cold/hot, nhiều ACE và parent.
6. **Cache có chứa ACL đầy đủ không?** Không tạo partial ACL dưới cache key chung.
7. **Cache có invalidation lúc cập nhật/xóa/revoke quyền không?** Đặc biệt giữa nhiều node.
8. **SQL tùy chỉnh có giữ mapping và order không?** Test mask, class, SID, ACE order.
9. **Parent ACL có chính sách nhất quán không?** Kế thừa, cycle, cross-tenant, evict children.
10. **Thiếu ACL/ACE xử lý an toàn chưa?** Không có bằng chứng grant → không cấp quyền.
11. **Lỗi hạ tầng được phân biệt chưa?** Timeout không bị giả thành ACL rỗng/không tồn tại.
12. **Các lớp phân quyền khác có còn hiệu lực không?** Role, tenant, resource ownership, soft delete.
13. **Đã test interceptor thật chưa?** @EnableMethodSecurity, Spring proxy, lời gọi từ HTTP và non-HTTP.
14. **Đã giám sát được hiệu năng và lỗi?** DB metrics, cache hit ratio, quyền bị revoke, latency.
15. **Có migration plan khi đổi strategy không?** Kiểm thử trước/sau nâng Spring Security, DB schema hoặc cache.

**Tóm tắt:** `BasicLookupStrategy` là **chiến lược tải ACL qua JDBC/ANSI SQL** được `JdbcAclService` sử dụng. Nó gom các ObjectIdentity theo batch size, dùng ACL cache và lắp ráp ACL/ACE/parent, nhưng **không dùng tham số `sids` để giới hạn ACE được tải**. Sau khi có ACL đầy đủ, `PermissionGrantingStrategy` mới xử lý grant/deny. Muốn một hệ thống ACL đúng và nhanh phải xem **batch lookup, cache toàn vẹn, parent inheritance, ACE order, invalidation và dữ liệu nghiệp vụ tin cậy** như một thiết kế thống nhất.

## Tài liệu tham khảo chính thức

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): mô hình ACL, các bảng JDBC, `AclService`, `BasicLookupStrategy` và ví dụ bean config.
- [Spring Security API — BasicLookupStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html): constructor, `readAclsById`, cảnh báo bỏ qua `sids`, batch và SQL customization.
- [Spring Security API — LookupStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/LookupStrategy.html): hợp đồng đọc Map và ý nghĩa `sids`.
- [Spring Security API — JdbcAclService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcAclService.html): `readAclById`, `readAclsById`, `findChildren` và `NotFoundException`.
- [Spring Security API — AclCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AclCache.html): thao tác cache by ObjectIdentity/primary key và eviction.
- [Spring Security API — SpringCacheBasedAclCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html): dùng Spring Cache và các trường transient của `AclImpl`.
- [Spring Security — ACL database schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): bảng và các cột ACL.
