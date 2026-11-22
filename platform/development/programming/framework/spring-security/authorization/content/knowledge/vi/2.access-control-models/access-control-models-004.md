# ACL: Cấp quyền cho từng chủ thể trên từng đối tượng

> **Chủ đề:** Spring Security - authorization  
> **Nhóm kiến thức:** Mô hình kiểm soát truy cập  
> **Mục tiêu:** Hiểu Access Control List (ACL), đọc được một quyền theo bộ ba *chủ thể – đối tượng – thao tác*, xây dựng quy tắc cấp/thu hồi quyền, nhận biết các điểm tích hợp ACL trong Spring Security và tránh lỗi truy cập chéo tài nguyên (IDOR/BOLA).

## 1. Vì sao cần ACL?

Giả sử hệ thống lưu trữ tài liệu có hai người dùng Alice và Bob. Cả hai đều có vai trò `USER`; tài liệu `doc-42` do Alice tạo, còn `doc-43` thuộc một dự án khác. Alice có thể chia sẻ riêng quyền xem `doc-42` cho Bob mà không cho Bob sửa. Cùng lúc, Alice có quyền sửa `doc-43` vì được giao phụ trách. Một kiểm tra đơn giản như `hasRole("USER")` không thể trả lời chính xác **ai được thực hiện thao tác nào trên tài liệu nào**.

**Access Control List (ACL)** là danh sách các mục kiểm soát truy cập gắn với một đối tượng. Mỗi mục mô tả một **chủ thể** hoặc nhóm chủ thể được cấp/từ chối **một quyền cụ thể** trên **đối tượng cụ thể**.

Ví dụ trực quan:

| Đối tượng | Chủ thể nhận quyền | Thao tác | Quyết định |
| --- | --- | --- | --- |
| `doc-42` | Alice | READ | Allow |
| `doc-42` | Alice | WRITE | Allow |
| `doc-42` | Bob | READ | Allow |
| `doc-42` | Bob | WRITE | Deny |
| `doc-43` | Alice | WRITE | Allow |
| `doc-43` | Bob | READ | Không có ACE; xử lý theo chính sách mặc định |

Đối với Alice và Bob, role là như nhau nhưng quyết định khác nhau theo từng tài liệu. ACL phù hợp khi cần **quyền tinh vi trên từng bản ghi**: chia sẻ file, giao quyền trên ticket, cho phép cộng tác trên báo cáo, phân công người xét duyệt một đề nghị cụ thể, v.v.

Ký pháp tư duy:

```text
canAccess(subject, action, resource, context) -> ALLOW / DENY

subject  = Alice / Bob / GROUP_REVIEWERS
action   = READ / WRITE / DELETE / ADMINISTER
resource = Document:42 / Ticket:19
context  = tenant, trạng thái, tổ chức, thời điểm, quan hệ nghiệp vụ
```

ACL cung cấp dữ liệu cho phần `(subject, action, resource)`. Nếu còn những điều kiện như tenant, tài liệu hết hạn, không được tự phê duyệt hoặc trạng thái đã khóa, ứng dụng vẫn phải áp dụng các luật đó.

## 2. Các khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Principal / subject** | Danh tính cần kiểm tra quyền | user `alice`, user `bob` |
| **Group / authority** | Nhóm/chức năng mà principal đang thuộc về | `TEAM_AUDITORS` |
| **Resource / domain object** | Đối tượng được bảo vệ | `Document(id=42)` |
| **Action / permission** | Hành vi cần xin phép trên đối tượng | READ, WRITE, DELETE |
| **ACL** | Danh sách quyền liên quan đến một resource | ACL của Document:42 |
| **ACE (Access Control Entry)** | Một mục quyền trong ACL | Bob được READ Document:42 |
| **Grant/allow** | ACE xác nhận được phép | Bob: READ = allow |
| **Deny** | ACE từ chối một quyền | Bob: WRITE = deny |
| **Owner** | Người sở hữu bản ghi hoặc ACL, tùy mô hình | Alice tạo tài liệu |
| **Inheritance** | ACL con có thể kế thừa quyền ACL cha theo luật cấu hình | File kế thừa quyền thư mục |
| **Default deny** | Thiếu bằng chứng cấp quyền thì ứng dụng từ chối | Carol chưa có quyền xem Document:42 |

Lưu ý: **owner của bản ghi nghiệp vụ** và **owner của ACL** không nhất thiết là một; trong Spring Security ACL, owner là thuộc tính của ACL, không phải lời khẳng định rằng owner mặc nhiên có mọi permission. Quy tắc owner được xem/sửa/xóa dữ liệu phải được quy định minh bạch.

**ACE không phải một vai trò toàn hệ thống.** Cho Bob quyền `READ` với `doc-42` không làm Bob đọc được mọi tài liệu. Cũng không nên lưu `ROLE_DOCUMENT_42_READER` vào token của mỗi người dùng: khi tài liệu tăng nhanh, lượng authority và chi phí cập nhật token sẽ trở nên khó kiểm soát.

## 3. ACL và ma trận kiểm soát truy cập

Có thể hình dung toàn bộ chính sách bằng một **access control matrix**: hàng là chủ thể, cột là đối tượng, mỗi ô là các quyền. ACL chính là cách nhìn **theo từng cột**: với một đối tượng, liệt kê ai có quyền trên nó.

| Chủ thể \ Đối tượng | Document 42 | Document 43 | Document 44 |
| --- | --- | --- | --- |
| Alice | READ, WRITE | READ, WRITE | — |
| Bob | READ | — | READ |
| Carol | — | READ | READ, WRITE |
| Nhóm Reviewers | READ | READ | — |

Từ bảng này:

- ACL của `Document 42` chứa các entry cho Alice, Bob và nhóm Reviewers.
- Nếu cần trả lời “Bob được truy cập tài liệu nào?” thì phải **tìm theo chủ thể xuyên qua nhiều ACL**, không thể chỉ lấy ACL của một tài liệu.
- Một tài liệu có thể có ACL trống; quyết định mặc định cần được mô tả rõ và an toàn.
- Quyền hiệu lực có thể chịu ảnh hưởng của tư cách nhóm, quyền kế thừa và luật deny/allow đã chọn.

Phân biệt ba cấu trúc thường gặp:

1. **ACL (object-centric):** `resource -> subjects + permissions`. Hợp với màn hình “Chia sẻ tài liệu này cho ai?”.
2. **Capability/access grant (subject-centric):** `subject -> resources + permissions`, có thể dùng token/handle không thể giả mạo. Hợp với mô hình cấp quyền truy cập bằng capability.
3. **RBAC (role-based):** `subject -> role -> permissions` trên loại thao tác/chức năng. Hợp với quyền chung như “kế toán được tạo phiếu”.

ACL không phải lựa chọn duy nhất để kiểm soát một đối tượng; trong nhiều ứng dụng, **ACL + RBAC + điều kiện thuộc tính** cùng tham gia một quyết định.

## 4. Cách hình thành quyết định ALLOW/DENY

Một luồng logic có thể mô tả như sau:

```text
Request: Bob muốn WRITE Document:42
        |
        v
1. Bob đã được xác thực và đúng tenant?
        | no -> từ chối
        v
2. Chức năng WRITE có được phép ở mức ứng dụng?
        | no -> từ chối
        v
3. Tìm ACL của Document:42 (và ACL cha nếu cấu hình)
        |
        v
4. Thu thập các SID phù hợp của Bob và nhóm hiện có
        |
        v
5. Đánh giá ACE phù hợp với quyền WRITE
        | không có quyền hiệu lực / explicit deny -> từ chối
        v
6. Kiểm tra chính sách nghiệp vụ bổ sung, trạng thái, khóa
        | no -> từ chối
        v
7. Cho phép ghi sau các kiểm tra tính nhất quán cần thiết
```

Ở mức thiết kế, **mặc định từ chối khi không có grant hiệu lực** là nguyên tắc an toàn. Tuy nhiên, không được tự suy diễn rằng mọi công cụ ACL đều dùng cùng một quy tắc “deny luôn thắng”. Cách phối hợp ACE của user, nhóm, ACL cha và yêu cầu nhiều permission là một **thuật toán đánh giá quyền cụ thể**.

Ví dụ về những câu cần chốt trước khi triển khai:

- Alice được `WRITE` ở ACL con, nhưng bị `DENY WRITE` ở nhóm tại ACL cha: kết quả theo quy tắc nào?
- Nếu Alice là thành viên của hai nhóm, một nhóm `ALLOW READ` còn nhóm kia `DENY READ`, lấy kết quả nào?
- Nếu vừa có `READ` vừa có `WRITE`, yêu cầu `READ + WRITE` có nghĩa **cả hai** hay **một trong hai**?
- Nếu không có ACE nào cho Bob, có cho owner hoặc admin mặc nhiên đi qua không?
- Khi Bob bị loại khỏi nhóm, quyền mới có hiệu lực ngay hay phụ thuộc thời gian refresh danh tính/cache?

**Trong Spring Security ACL:** `DefaultPermissionGrantingStrategy` xét các permission và SID theo thứ tự đầu vào, tìm ACE tương ứng và áp dụng thuật toán grant/deny của nó; khi không có kết quả phù hợp có thể tiếp tục xét ACL cha nếu bật kế thừa. Đây **không phải** quy tắc deny-overrides tổng quát áp dụng bất kể vị trí. Vì vậy, không viết unit test dựa trên phỏng đoán “deny cao ưu tiên nhất” nếu chưa xác nhận chiến lược thực tế.

## 5. Mô hình ACE: cho phép theo đúng phạm vi

Đối với một hệ thống chia sẻ tài liệu, một ACE tối thiểu có thể gồm:

```text
(resource_type, resource_id, recipient_type, recipient_id, permission, granted)
(Document,      42,          USER,           bob,          READ,       true)
(Document,      42,          USER,           bob,          WRITE,      false)
(Document,      42,          GROUP,          reviewers,    READ,       true)
```

Các thiết kế thực tế thường cần thêm `tenant_id`, thời gian tạo/sửa, người cấp, nguồn cấp, thời hạn quyền, version hoặc audit event. Không phải trường nào cũng nằm trong bảng ACE của module Spring Security; với các yêu cầu đó có thể dùng bảng nghiệp vụ riêng hoặc mở rộng mô hình.

**Định danh phải ổn định:** nếu username hoặc email đổi được, đừng lấy chuỗi đó làm khóa nghiệp vụ lâu dài khi có thể dùng stable subject ID. Trong Spring Security ACL, `PrincipalSid` sử dụng chuỗi định danh principal: hãy bảo đảm chuỗi này thống nhất giữa lúc ghi ACE và lúc đánh giá quyền. Quyền cấp cho `GROUP` thường được biểu diễn qua authority có trong `Authentication`; tư cách nhóm phải được cập nhật và kiểm chứng ở nguồn tin cậy.

**Một đối tượng phải được nhận diện duy nhất:** `Document:42` không được vô tình trùng với `Invoice:42`. Trong hệ thống nhiều tenant, nếu ID chỉ duy nhất trong mỗi tenant, định danh ACL phải bao gồm tenant hoặc đảm bảo ID toàn cục duy nhất và vẫn kiểm tra tenant độc lập.

**Permission rõ nghĩa:** `READ` là xem nội dung, `WRITE` là chỉnh sửa, `DELETE` là xóa, `ADMINISTER` là quản lý ACL. Đừng mặc định `ADMINISTER` đồng nghĩa mọi thao tác nghiệp vụ hoặc quyền bypass tenant; mức ủy quyền của từng action phải được định nghĩa.

## 6. Ví dụ Java 17+ thuần: ACL riêng cho từng bản ghi

Ví dụ này chạy độc lập để làm rõ bộ ba **chủ thể – đối tượng – quyền**. Nó dùng mô hình đơn giản: duyệt các ACE theo thứ tự, gặp ACE đầu tiên khớp ba trường thì lấy giá trị `granted`, nếu không có thì `false`. **Đây là thuật toán minh họa tự xây dựng, không phải bản sao của `DefaultPermissionGrantingStrategy` trong Spring Security.**

Lưu toàn bộ vào file `AclExample.java`:

```java
import java.util.List;

public class AclExample {

    enum Permission {
        READ, WRITE, DELETE
    }

    record Ace(
        String resourceId,
        String recipientId,
        Permission permission,
        boolean granted
    ) {}

    static boolean can(
        List<Ace> acl,
        String recipientId,
        String resourceId,
        Permission permission
    ) {
        for (Ace entry : acl) {
            if (entry.resourceId().equals(resourceId)
                    && entry.recipientId().equals(recipientId)
                    && entry.permission() == permission) {
                return entry.granted();
            }
        }
        return false; // Default deny khi không có entry phù hợp.
    }

    public static void main(String[] args) {
        List<Ace> acl = List.of(
            new Ace("doc-42", "alice", Permission.READ, true),
            new Ace("doc-42", "alice", Permission.WRITE, false),
            new Ace("doc-42", "bob", Permission.READ, true),
            new Ace("doc-43", "alice", Permission.WRITE, true)
        );

        System.out.println("Alice READ doc-42: "
            + can(acl, "alice", "doc-42", Permission.READ));
        System.out.println("Alice WRITE doc-42: "
            + can(acl, "alice", "doc-42", Permission.WRITE));
        System.out.println("Alice WRITE doc-43: "
            + can(acl, "alice", "doc-43", Permission.WRITE));
        System.out.println("Bob READ doc-42: "
            + can(acl, "bob", "doc-42", Permission.READ));
        System.out.println("Bob READ doc-43: "
            + can(acl, "bob", "doc-43", Permission.READ));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac AclExample.java
java AclExample
```

Kết quả chuẩn:

```text
Alice READ doc-42: true
Alice WRITE doc-42: false
Alice WRITE doc-43: true
Bob READ doc-42: true
Bob READ doc-43: false
```

Điểm học được:

- Alice có thể `READ` `doc-42` nhưng không thể `WRITE` cùng tài liệu.
- Alice được `WRITE` `doc-43` nên quyền ở tài liệu này **không lan sang** tài liệu kia.
- Bob đọc được `doc-42`, còn `doc-43` không có grant nên bị từ chối.
- `granted=false` là một ACE từ chối **tường minh**; không có ACE là **thiếu grant**. Hai tình huống có thể cùng trả `false` ở mô hình đơn giản nhưng có thể khác nhau nếu áp dụng inheritance hoặc nhiều loại SID.

Đoạn chạy độc lập cố ý không có Spring Security, database, nhóm, ACL cha, tenant hay transaction. Khi triển khai thật, phải bổ sung những phần đó và thiết kế conflict/precedence rõ ràng; không đem vòng lặp demo này dùng trực tiếp để thay thế engine ACL của framework.

## 7. Spring Security hỗ trợ ACL ở đâu?

Spring Security có một **module ACL tùy chọn** (thư viện `org.springframework.security:spring-security-acl`) để lưu/đọc quyền theo từng đối tượng và tích hợp đánh giá quyền vào method security. Module này **không tự bật** chỉ vì ứng dụng có Spring Security hoặc viết `@PreAuthorize`.

Trong dự án Gradle dùng quản lý version Spring Boot, có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-acl'
}
```

Cần cấu hình `DataSource`, schema SQL, bean ACL service/lookup/cache/authorization strategy và cơ chế authentication/method security. Tài liệu Spring Security 6.5 có cấu hình minh họa cho `JdbcMutableAclService`, `BasicLookupStrategy` và `AclPermissionEvaluator`. Không tự giả định rằng dependency sẽ tạo bảng, sinh ACE cho mỗi entity hoặc cấp quyền chủ sở hữu mặc định.

### Những thành phần chính

| Thành phần Spring ACL | Vai trò |
| --- | --- |
| `Acl` | Đại diện tập ACE, owner và thông tin kế thừa của một object |
| `AccessControlEntry` | Một ACE gồm SID, permission, grant/deny và thông tin audit |
| `Sid` | Security identity: principal hoặc authority |
| `PrincipalSid` | SID của một người dùng/principal |
| `GrantedAuthoritySid` | SID tương ứng với một authority/nhóm quyền |
| `ObjectIdentity` / `ObjectIdentityImpl` | Xác định object bằng loại + ID |
| `Permission` / `BasePermission` | Quyền dưới dạng bit mask |
| `AclService` | Đọc ACL của một hay nhiều object |
| `MutableAclService` | Tạo, cập nhật, xóa ACL |
| `JdbcAclService` / `JdbcMutableAclService` | Triển khai ACL dựa trên JDBC |
| `LookupStrategy` / `BasicLookupStrategy` | Tải ACL, hỗ trợ đọc batch và ACL cha |
| `AclPermissionEvaluator` | Gắn quyết định ACL với biểu thức `hasPermission(...)` |
| `PermissionGrantingStrategy` | Chiến lược quyết định grant/deny khi xét ACE |
| `AclCache` | Bộ nhớ đệm ACL, cần nhất quán khi ACL thay đổi |

`ObjectIdentity` thường được tạo bằng `new ObjectIdentityImpl(Document.class, 42L)`. Hai bản ghi có cùng ID số nhưng class khác nhau được phân biệt. Nếu dự án dùng UUID hoặc khóa ghép, phải xác nhận loại ID và cấu hình truy vấn JDBC tương thích thay vì giả định ví dụ Long chạy nguyên xi.

### Năm quyền mẫu trong BasePermission

| Permission | Bit | Giá trị mask |
| --- | ---: | ---: |
| `READ` | 0 | 1 |
| `WRITE` | 1 | 2 |
| `CREATE` | 2 | 4 |
| `DELETE` | 3 | 8 |
| `ADMINISTRATION` | 4 | 16 |

Bit mask cho phép biểu diễn quyền bằng các bit của một số nguyên. **Không có nghĩa một bit tương ứng với một tài liệu**; bit biểu diễn *loại quyền*, còn số lượng object được lưu dưới dạng những identity/ACE khác nhau. Có thể tạo permission tùy biến nhưng phải phối hợp thống nhất giữa mã quyền, ánh xạ biểu thức và dữ liệu đã lưu.

Đừng tự kết luận `WRITE` đương nhiên kéo theo `READ` chỉ vì tên quyền. Nếu chính sách cần quan hệ này, hãy định nghĩa và kiểm thử rõ.

## 8. Bốn bảng ACL JDBC tiêu biểu

Module JDBC dùng bốn bảng quan hệ, với các cột thực tế theo script migration phù hợp database:

```text
ACL_SID
  id
  principal                   # principal hay authority
  sid                         # tên/định danh chủ thể

ACL_CLASS
  id
  class                       # tên lớp domain object

ACL_OBJECT_IDENTITY
  id
  object_id_class             # FK -> ACL_CLASS
  object_id_identity          # ID của từng domain object
  parent_object               # FK -> ACL_OBJECT_IDENTITY (nếu có)
  owner_sid                   # FK -> ACL_SID
  entries_inheriting          # cờ kế thừa ACL cha

ACL_ENTRY
  id
  acl_object_identity         # FK -> ACL_OBJECT_IDENTITY
  ace_order                   # vị trí ACE
  sid                         # FK -> ACL_SID
  mask                        # bit mask quyền
  granting                    # grant hay deny
  audit_success / audit_failure
```

Luồng đọc quyết định `READ` cho `Document:42`:

1. Map `Document` vào `ACL_CLASS`, ID `42` vào `ACL_OBJECT_IDENTITY`.
2. Xác định SID tương ứng principal và các authority hiện tại của actor.
3. Tải `ACL_ENTRY` của object, và ACL cha khi có liên kết/kế thừa.
4. Áp dụng `PermissionGrantingStrategy` trên permission yêu cầu và danh sách SID.
5. Kết quả từ ACL phải tiếp tục kết hợp với giới hạn tenant và chính sách nghiệp vụ liên quan.

`ACL_OBJECT_IDENTITY` về bản chất mô tả một object được quản lý, còn `ACL_ENTRY` có thể chứa nhiều dòng cho cùng object đó. Khi object bị xóa, ứng dụng phải có quy trình dọn ACL tương ứng. Spring Security không tự đồng bộ vòng đời tạo/sửa/xóa của JPA entity với các bảng ACL.

**Chi phí dữ liệu:** 1 triệu tài liệu có thể tương ứng 1 triệu object identity và nhiều triệu ACE. Cần index trên object identity, SID và các khóa tra cứu; xây dựng chiến lược cache, batch lookup, thu hồi quyền và dọn dữ liệu trước khi hệ thống tăng trưởng.

## 9. Tích hợp với Spring Method Security

Ví dụ cấu hình **một phần** cho Spring Security 6.x, cho thấy cách nối `hasPermission` sang module ACL. Đây là snippet tích hợp, không phải Java main chạy độc lập: ứng dụng phải cung cấp bean `AclService`, schema và bean hạ tầng JDBC ACL nêu ở phần trước.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    PermissionEvaluator aclPermissionEvaluator(AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }
}
```

Điểm gọi quyền trên một service:

```java
// Snippet minh họa; Document, DocumentRepository do ứng dụng định nghĩa.
@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasPermission(#documentId, 'com.example.domain.Document', 'READ')"
    )
    public Document read(Long documentId) {
        return repository.findById(documentId)
            .orElseThrow(() -> new DocumentNotFoundException(documentId));
    }
}
```

Các điều kiện để đoạn tích hợp có nghĩa:

- `@EnableMethodSecurity` phải bật và method phải được gọi qua cơ chế interception/proxy phù hợp. Tự gọi một method có `@PreAuthorize` trên cùng bean (`this.read(...)`) thường không đi qua proxy.
- Chuỗi `com.example.domain.Document` chỉ là tên minh họa: phải trùng với loại object identity thực sự lưu trong ACL; ID phải tương thích với mô hình persistence.
- `hasPermission(id, type, permission)` gọi `PermissionEvaluator` để lấy quyết định theo object ID và loại; dạng `hasPermission(domainObject, permission)` áp dụng khi đã có object.
- Đây là **permission theo đối tượng**. Các kiểm tra tenant, trạng thái workflow, quyền tạm thời hoặc điều kiện nghiệp vụ khác vẫn cần xử lý độc lập, đúng transaction/điểm gọi.
- User chưa có quyền `READ` không nên nhận được dữ liệu trước khi quyền được kiểm tra. Tùy kiến trúc, có thể nạp bản ghi trong phạm vi tenant và gọi policy trong cùng transaction thay cho biểu thức truy vấn ACL trước service.
- Nếu `PermissionEvaluator` chưa được cấu hình, method security có thể dùng evaluator từ chối mặc định; đừng hiểu mọi `false` là do dữ liệu ACL chính xác.
- Tránh biến `@PostAuthorize` hoặc `@PostFilter` thành cách duy nhất để bảo vệ dữ liệu lớn: khi ấy dữ liệu có thể đã được tải hoặc side effect đã chạy trước khi kiểm tra.

Đối với chức năng không đi qua HTTP (scheduler, message consumer, job, command), phải thiết kế điểm kiểm tra trong use case. URL guard chỉ quản lý request đi qua filter chain, không bảo vệ tự động mọi lời gọi Java.

## 10. Tạo, cập nhật và thu hồi ACE

Có hai tầng trách nhiệm:

- **Ai có quyền sửa ACL?** Thường là owner/chủ quản trị được ủy quyền, nhưng phải được ứng dụng kiểm tra qua một policy riêng. Không cho mọi người dùng tự gọi service cấp quyền cho chính mình.
- **Sửa dữ liệu ACL thế nào?** `MutableAclService` cung cấp `createAcl`, `updateAcl` và `deleteAcl`; `MutableAcl` cho phép thêm/xóa ACE và chỉnh thông tin owner/inheritance phù hợp.

Ví dụ **một đoạn minh họa** cho lần đầu tạo ACL của tài liệu có ID số 42; chạy trong service sau khi đã xác minh người gọi có quyền chia sẻ và tài liệu tồn tại đúng tenant:

```java
// Các biến mutableAclService và Document là dependency/domain type của ứng dụng.
// Minh họa tạo ACL MỚI; createAcl sẽ thất bại nếu ACL đã tồn tại.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 42L);
MutableAcl acl = mutableAclService.createAcl(oid);

Sid bob = new PrincipalSid("bob");
acl.insertAce(0, BasePermission.READ, bob, true);
mutableAclService.updateAcl(acl);
```

Trong code thật, cần import các type từ `org.springframework.security.acls.model` và `org.springframework.security.acls.domain`, tổ chức transaction và xử lý ngoại lệ khi hai request cùng cấp quyền. Không cố gọi `createAcl` mỗi lần chia sẻ; nếu ACL đã có, dùng `readAclById` rồi sửa `MutableAcl` và gọi `updateAcl` theo đúng luật nghiệp vụ. `getEntries()` dùng để quản trị ACE; để quyết định quyền hãy dùng `Acl.isGranted(...)` hoặc `PermissionEvaluator`, không tự duyệt mảng ACE và suy luận sai thứ tự.

**Thu hồi quyền không phải chỉ đổi UI:**

1. Kiểm tra người thu hồi có quyền quản trị chính resource/ACL.
2. Tìm đúng ACE theo object identity, SID và permission.
3. Xóa hoặc sửa ACE bằng API `MutableAcl`; lưu lại bằng `MutableAclService`.
4. Đảm bảo ACL cache bị làm mới hoặc vô hiệu hóa; xác định độ trễ nếu có nhiều node.
5. Ghi sự kiện audit về người thực hiện, đối tượng, quyền cũ/mới và lý do theo quy tắc bảo mật dữ liệu.
6. Kiểm thử rằng người bị thu hồi không còn truy cập qua API, export, tải file trực tiếp hay job liên quan.

Khi xóa đối tượng, cân nhắc `MutableAclService.deleteAcl(objectIdentity, deleteChildren)`; tùy thiết kế ACL cha/con, việc xóa cha có thể bị chặn khi còn con hoặc xóa cả cây nếu chọn cascade. Không chọn `deleteChildren=true` theo thói quen mà chưa đánh giá tác động.

## 11. Quyền kế thừa: tiết kiệm ACE nhưng dễ vô tình mở rộng truy cập

Giả sử Project A có ACL cấp `READ` cho nhóm `TEAM_A`. Nhiều tài liệu của Project A kế thừa ACL cha; khỏi phải ghi lại ACE cho từng tài liệu. Một tài liệu riêng tư cần cơ chế giới hạn hoặc ngắt kế thừa.

```text
Project A (ACL cha)
  TEAM_A -> READ
    |
    +-- Document 42 (entriesInheriting = true)
    |
    +-- Document 43 (entriesInheriting = true)
    |
    +-- Document 44 (entriesInheriting = false)
            Alice -> READ
```

Cần phân định hai câu hỏi:

- **Có kế thừa hay không?** Theo thông tin `parent ACL` và `entriesInheriting`.
- **ACE cục bộ và ACE cha tương tác ra sao?** Theo permission, SID và chiến lược đánh giá đang dùng.

Không nên giả định một ACE local `DENY` sẽ luôn “phủ” mọi ACE cha/người dùng/nhóm trong mọi chiến lược. Trong triển khai mặc định của Spring Security ACL, việc có ACE match và cách đi đến parent là các bước có thứ tự cụ thể.

Những tình huống phải kiểm thử: thêm người vào team sau khi tạo tài liệu; gỡ người khỏi team; di chuyển tài liệu sang project khác; gỡ kế thừa ở tài liệu nhạy cảm; thay ACL cha khi nhiều con đang dùng cache. Thao tác di chuyển resource qua tenant đặc biệt nhạy cảm: phải cập nhật cả quan hệ parent, quyền hiệu lực và ranh giới tenant trong một quy trình nhất quán.

## 12. ACL so với RBAC và ABAC: chọn theo bài toán

| Khía cạnh | RBAC | ACL | ABAC/policy theo thuộc tính |
| --- | --- | --- | --- |
| Câu hỏi tiêu biểu | Người có role EDITOR không? | Bob có WRITE Document:42 không? | Actor thuộc tenant A, tài liệu DRAFT và trong giờ làm việc không? |
| Trọng tâm | Role → chức năng | Object → recipient → permission | Điều kiện từ thuộc tính actor/resource/context |
| Thay đổi quyền | Đổi role hoặc role-permission | Thêm/xóa ACE cho từng object | Thay policy và giá trị thuộc tính |
| Điểm mạnh | Quản lý đơn giản cho chức năng chung | Chia sẻ riêng từng object | Linh hoạt với điều kiện động |
| Chi phí/rủi ro | Nổ số role nếu gắn từng object | Nổ số ACE, cache và vấn đề kế thừa | Chính sách phức tạp, dữ kiện và giải thích kết quả |

Một thiết kế kết hợp hay gặp:

```text
ALLOW EDIT Document:42 khi:
    đã xác thực
AND thuộc tenant chứa Document:42
AND có quyền chức năng document:edit
AND ACL(Document:42) cho actor WRITE
AND Document:42 đang DRAFT
```

Ở đây ACL quyết định **quyền trên đối tượng**, RBAC/authority quyết định **quyền chức năng**, domain policy quyết định **điều kiện phụ thuộc trạng thái**. Đừng thay toàn bộ sự thật nghiệp vụ bằng một flag `WRITE` nếu sản phẩm yêu cầu quy tắc phê duyệt, thanh toán, hạn mức, separation-of-duties hay trạng thái chuyển bước.

**Khi không cần module ACL:** nếu mọi tài liệu chỉ do owner nhìn thấy, ít nhu cầu chia sẻ, quyền theo nhóm/tenant dễ biểu diễn bằng foreign key và query scoped, một policy service + repository query có thể đơn giản hơn. Chọn Spring Security ACL khi hệ thống thực sự cần nhiều ACE trên từng object, chia sẻ, thu hồi, quyền kế thừa và quản trị danh sách quyền.

## 13. Ranh giới tenant và dữ liệu đáng tin

Một ACL trả `ALLOW` cho Bob trên `Document:42` không đủ nếu Bob đã bị loại khỏi tổ chức chứa tài liệu.

Các ràng buộc cần giữ độc lập:

- Danh tính trong `Authentication` phải được xác minh; không lấy `userId` hoặc `role` do client gửi trong body làm principal.
- Nếu API có `tenantId` trong URL/header, phải xác minh user có quyền vào tenant đó và tài liệu thuộc tenant đó. Không coi tên tenant client đưa vào là bằng chứng.
- Với ID chỉ duy nhất trong tenant, tạo object identity có namespace không trùng; nếu dùng global ID, vẫn giới hạn tenant ở query và policy.
- ACE gắn với user đã nghỉ việc cần xử lý deactivate/xóa; ACE của group cần được cập nhật khi membership đổi.
- Token cũ, ACL cache và cache kết quả quyết định phải có quy tắc hết hạn/invalidation rõ. Thu hồi trong database nhưng cache cũ còn allow là một lỗi thực tế.
- Các đường tải file từ object storage, link export, bản sao dữ liệu hoặc search index phải áp dụng quyền nhất quán, không chỉ kiểm tra route metadata.
- Không cho phép user tự tạo ACE `ADMINISTRATION` nhằm cấp quyền cho người khác khi policy của ứng dụng chưa cho phép.

**Chống IDOR/BOLA:** attacker có thể sửa `/documents/42` thành `/documents/43`. Nếu endpoint chỉ kiểm tra `authenticated()` hoặc `ROLE_USER` thì attacker có thể truy cập dữ liệu của người khác. ACL cần được tra theo **đúng ID tài nguyên thực**, kết hợp scope tenant; không đủ nếu chỉ kiểm tra permission trên “một tài liệu nào đó”.

## 14. Danh sách, phân trang và hiệu năng

Một endpoint `GET /documents` có thể phải trả 100 tài liệu user được xem. Cách ngây thơ là tải 100.000 bản ghi rồi chạy `hasPermission` cho từng object và loại bỏ các bản ghi bị deny. Cách này có rủi ro:

- Dữ liệu nhạy cảm đã được tải quá rộng vào bộ nhớ ứng dụng.
- Nhiều truy vấn ACL riêng lẻ gây N+1 query và timeout.
- `LIMIT/OFFSET` trước khi lọc quyền làm số lượng và phân trang sai lệch.
- Việc dùng `@PostFilter` trên tập lớn có thể tốn CPU/memory, và dễ làm lộ tổng số bản ghi/metadata qua count hoặc debug log.

Các hướng giải quyết:

1. Xây dựng câu truy vấn lọc theo tenant và visibility/share condition ở database, với index phù hợp.
2. Với Spring Security ACL, cân nhắc `AclService.readAclsById(...)` và `BasicLookupStrategy` để tải nhiều ACL cùng lần thay vì gọi từng ID.
3. Nếu truy vấn danh sách cần predicate phức tạp theo ACE, thiết kế projection/index quyền xem ở mức database thay vì gọi evaluator cho từng bản ghi.
4. Giới hạn tập kết quả **trước khi** xuất nội dung; xác định rõ quyền cần dùng cho list, detail, download, export và search.
5. Cache ACL đúng khóa (object identity, SID, version/tenant khi liên quan), tránh cache ALLOW vô hạn; xóa/refresh sau grant, revoke, move, delete.
6. Đo latency khi số lượng ACE, group và mức độ kế thừa tăng, đồng thời có test tải thực tế với dữ liệu lớn.

**Đừng lưu quyền của hàng triệu object vào `GrantedAuthority` của một `Authentication`.** Giữ quyền tổng quát trong identity và tra cứu ACL theo object có thể mở rộng tốt hơn; với hệ thống rất lớn, cần đánh đổi thêm giữa ACL trực tiếp và các chỉ mục quyền được tính trước.

## 15. Quyền âm, lỗi và audit

Một chính sách an toàn phải nói rõ điều gì xảy ra khi không có grant:

- **Chưa đăng nhập/credential sai:** từ chối tại authentication; REST API thường là HTTP `401` theo contract.
- **Đã đăng nhập nhưng không có ACL grant:** từ chối thao tác; thường có thể trả HTTP `403`.
- **Resource không tồn tại hoặc không được phép nhìn thấy:** có thể trả `404` để tránh tiết lộ sự tồn tại theo chính sách dữ liệu; phải nhất quán.
- **ACL service/DB/cache gặp lỗi:** không tự chuyển thành allow; phân biệt lỗi hệ thống và lỗi “không có grant” khi logging/monitoring.
- **Thao tác được cấp quyền nhưng sai trạng thái nghiệp vụ:** trả mã lỗi miền thích hợp (ví dụ conflict) nếu contract quy định, không đánh đồng mọi invalid state thành thiếu ACL.

**Audit hai chiều:** audit thay đổi quyền (ai grant/revoke cho ai, lúc nào, resource nào) khác với audit sử dụng quyền (ai thử đọc/sửa/xóa, allow hay deny). Module ACL có các thuộc tính audit ở ACE; ứng dụng vẫn cần thiết kế audit nghiệp vụ đủ dùng, hạn chế ghi thông tin nhạy cảm và đảm bảo sự kiện quan trọng có thể truy vết.

Một API cấp quyền nên có:
- Người thực hiện có quyền `SHARE`/`ADMINISTER` hợp lệ trên đúng resource.
- Recipient tồn tại và thuộc phạm vi được phép chia sẻ.
- Permission được cấp nằm trong whitelist của loại resource và không vượt quyền ủy quyền.
- Giao dịch đảm bảo không cập nhật document thành công nhưng ghi ACL thất bại (hoặc ngược lại) nếu hai dữ liệu cần nhất quán.
- Kết quả ghi có version hoặc cơ chế phát hiện hai yêu cầu sửa ACL đồng thời, tránh last-write-wins ngoài ý muốn.
- Cache và các hệ thống phụ (search/export/download) được cập nhật theo độ trễ đã định nghĩa.

## 16. Ma trận kiểm thử ACL

Với `Document:42`, giả sử Bob được `READ` nhưng không có `WRITE`, còn Alice được `READ/WRITE`. Kiểm thử ít nhất:

| Tình huống | Kỳ vọng |
| --- | --- |
| Alice đọc Document:42 | ALLOW |
| Alice sửa Document:42 | ALLOW nếu các luật trạng thái/tenant cũng đúng |
| Bob đọc Document:42 | ALLOW |
| Bob sửa Document:42 | DENY |
| Carol chưa có ACE đọc Document:42 | DENY theo policy mặc định |
| Bob đổi ID sang Document:43 không có ACE | DENY |
| Bob bị xóa ACE READ, lặp request qua API | DENY, kể cả khi cache đang tồn tại |
| Bob bị loại khỏi nhóm được READ | DENY sau khi cập nhật membership/identity theo contract |
| Document:42 chuyển tenant khác | Không lộ quyền cross-tenant |
| Dữ liệu ACL không truy xuất được | Không được ALLOW do lỗi |
| ACL có parent, local ACE và group ACE xung đột | Kết quả đúng theo `PermissionGrantingStrategy` đã chọn |
| Cùng Document nhưng request READ/WRITE/DELETE | Mỗi permission quyết định độc lập |

Phân lớp kiểm thử:

1. **Unit test mô hình policy:** nhận actor/resource/permission/context; kiểm tra trường hợp allow, deny, thiếu ACE, explicit deny, quyền nhóm, kế thừa, xung đột, tenant.
2. **Integration test database ACL:** schema/migration, `createAcl`/`readAclById`/`updateAcl`/`deleteAcl`, principal/authority SID, bit mask, thứ tự ACE, parent/inheritance, refresh cache.
3. **Method security test:** `@EnableMethodSecurity` và `hasPermission` thực sự được gọi qua proxy; xác nhận denial không bị bỏ qua do self-invocation hoặc gọi vòng qua service khác.
4. **HTTP/end-to-end test:** user hợp lệ/ẩn danh, sửa object ID, list/detail/export/download, phân trang và trạng thái sau revoke; đảm bảo response, side effect và nội dung dữ liệu đều đúng.
5. **Concurrency/performance test:** grant và revoke đồng thời, sửa resource trong lúc check, nhiều ACE/group/ACL cha và data set lớn.

**Bẫy kiểm thử:** chỉ assert HTTP 403 chưa chứng minh ACL hoạt động. Endpoint PATCH có thể trả 403 vì CSRF hoặc vì request chưa xác thực. Test phải cung cấp credential/CSRF hợp lệ theo cấu hình, rồi thay đổi **duy nhất ACL hoặc object ID** để xác nhận nguyên nhân deny, đồng thời kiểm tra dữ liệu không bị sửa.

## 17. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Kiểm tra mỗi `hasRole("USER")` | User khác cùng role đọc được bản ghi không thuộc quyền | Kiểm tra ACL theo object ID thực |
| Chia sẻ quyền trên tên tài liệu thay vì ID ổn định | Trùng tên/đổi tên làm sai quyền | Dùng identity duy nhất theo type + ID + tenant |
| Nhận `ownerId` hay `recipient` từ client mà không xác minh | Leo thang đặc quyền, chia sẻ trái phép | Xác thực actor và áp dụng share policy |
| Xem `owner` là mặc định toàn quyền | Vượt chính sách xét duyệt hoặc tenant | Quy định rõ owner rights, kiểm tra tách biệt |
| Nghĩ “deny luôn thắng” khi chưa kiểm tra strategy | Quyền xung đột có kết quả bất ngờ | Test ACE order, group, parent và thứ tự SID |
| Bỏ cấp quyền khỏi bảng nhưng giữ cache cũ | Quyền bị thu hồi vẫn sử dụng được | Invalidate cache và test revoke thực tế |
| Chỉ bảo vệ controller | Job, consumer hoặc method nội bộ bypass | Đặt guard tại use case/method phù hợp |
| Chỉ xét một object rồi export toàn bộ | Lộ dữ liệu hàng loạt | Lọc quyền nhất quán cho từng operation/list/export |
| Tạo ACL khi tạo document nhưng không dọn khi xóa | ACL mồ côi và dữ liệu permission sai | Quản lý vòng đời ACL cùng domain object |
| Viết query N+1 cho mỗi tài liệu | Tăng độ trễ mạnh khi tập dữ liệu lớn | Batch ACL lookup/permission indexing |
| Nhầm `ADMINISTRATION` bit với super-admin toàn cục | Vượt phạm vi nghiệp vụ | Tách quyền quản ACL khỏi bypass domain/tenant |
| Trộn quyền vai trò với quyền từng object trong một biểu thức quá dài | Khó audit, khó bảo trì, dễ bỏ điều kiện | Policy có tên rõ, kiểm thử độc lập |

## 18. Chọn mô hình và đưa vào sản phẩm

Trước khi bật Spring Security ACL, hãy trả lời được:

1. Có thật sự cần chia sẻ quyền khác nhau trên **từng instance** hay chỉ cần owner/tenant/role?
2. Những principal/group nào được nhận ACE, và dùng stable ID nào?
3. Quyền là gì, có ngụ ý lẫn nhau không, quyền nào cho phép **sửa ACL**?
4. Nếu grant/deny xung đột giữa user–group–parent, thuật toán nào quyết định?
5. Tenant, trạng thái, nghiệp vụ có thể phủ quyết ACL trong trường hợp nào?
6. Lifecycle của ACL khi object tạo, đổi chủ, di chuyển, xóa là gì?
7. Thu hồi quyền cần có hiệu lực trong bao lâu; cache/token/replica được làm mới thế nào?
8. Query list, tìm kiếm, export và download bảo đảm chỉ đưa ra dữ liệu hợp quyền bằng cách nào?
9. Ai có thể giải thích quyết định cho người dùng và bộ phận audit khi bị deny?
10. Có test tự động cho 401/403/404, IDOR, group membership, inheritance, revoke, race và số lượng ACE lớn chưa?

**Bài tập tự kiểm tra:**

- `Document:42` chia sẻ READ cho Bob, `Document:43` không có ACE. Bob đổi ID trong URL từ 42 sang 43, hệ thống nên làm gì? → **Deny** theo ACL của 43 và quy tắc không tiết lộ dữ liệu đã thiết kế.
- Carol là thành viên `TEAM_A` được READ ở ACL cha. Khi Carol rời nhóm nhưng JWT cũ vẫn giữ authority `TEAM_A`, chuyện gì có thể xảy ra? → Quyền có thể còn hiệu lực cho đến khi identity/token hết hạn hoặc cơ chế thu hồi/kiểm tra lại membership có tác dụng. Thiết kế phải chốt độ trễ thu hồi.
- Một ACE `WRITE` được grant, nhưng tài liệu ở trạng thái `APPROVED` không cho phép sửa. Có nên cho phép? → **Không**, vì quyền ACL không vô hiệu hóa invariant/chính sách nghiệp vụ.
- Tài liệu không có ACE nào cho Alice nhưng Alice là owner record. Có được READ không? → **Chưa thể kết luận** nếu chưa biết luật owner. Hệ thống phải định nghĩa trường hợp owner một cách tường minh.

**Kết luận:** ACL biểu diễn “**chủ thể nào có quyền gì trên đối tượng cụ thể nào**”. Spring Security có thư viện ACL để lưu/truy xuất ACE và gắn vào `hasPermission`, nhưng ứng dụng vẫn sở hữu các quy tắc tenant, trạng thái và vòng đời phân quyền. Một thiết kế ACL tốt phải có định danh bền vững, deny an toàn, quản lý grant/revoke rõ ràng, kiểm tra mọi đường truy cập và kiểm thử được tình huống xung đột, thu hồi và truy cập chéo tài nguyên.

## Tài liệu tham khảo

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [API: AclPermissionEvaluator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html)
- [API: Acl / MutableAclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html)
- [API: DefaultPermissionGrantingStrategy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
