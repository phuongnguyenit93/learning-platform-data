# Thiết kế khóa cache theo người dùng, tenant, tài nguyên và phiên bản chính sách

## 1. Bài toán: tăng hiệu năng mà không tái sử dụng quyền sai đối tượng

Một hệ thống Spring Security có thể cần đánh giá quyền nhiều lần: người gọi có được đọc tài liệu, sửa hợp đồng, tải báo cáo, phê duyệt giao dịch hay không. Đánh giá quyền có thể phải đọc role, membership, ACL (Access Control List), tenant, thuộc tính tài nguyên và chính sách. Khi lưu **kết quả quyết định ủy quyền** (ALLOW/DENY) vào cache để giảm số lần truy vấn, điều kiện quan trọng nhất là **hai lần kiểm quyền chỉ được dùng chung một kết quả nếu mọi yếu tố quyết định quyền của chúng tương đương**.

Nếu khóa cache chỉ là mã tài nguyên, quyết định ALLOW của Alice có thể được tái sử dụng cho Bob. Nếu khóa có user và tài nguyên nhưng thiếu tenant, các ID chỉ duy nhất trong từng tenant có thể va chạm. Nếu khóa đủ danh tính nhưng không phản ánh thay đổi quyền hoặc chính sách, cache vẫn có thể trả ALLOW sau khi người dùng đã bị thu hồi quyền.

**Mục tiêu học tập:**

1. Xác định đầu vào thực sự của authorization decision và phân biệt nó với dữ liệu nghiệp vụ được trả về.
2. Xây dựng key theo **người dùng (subject), tenant, loại/ID tài nguyên (resource), hành động (action), phiên bản chính sách và phiên bản dữ liệu quyền**.
3. Hiểu lý do cần **policy version**, **subject grant version** và **resource ACL version**, cũng như lúc nào phải thêm chiều ngữ cảnh khác.
4. Thiết kế TTL, invalidation, xử lý thay đổi đồng thời và hệ thống nhiều node mà không bỏ qua yêu cầu thu hồi quyền.
5. Tích hợp vào Spring Security đúng tầng, đo hit rate và chứng minh tính cô lập bằng kiểm thử có cả trường hợp được phép lẫn bị từ chối.

Bài học tập trung vào **cache kết quả kiểm quyền** trong kiến trúc Spring Security authorization. Cache nội dung tài liệu, token, session hoặc HTTP response là bài toán liên quan nhưng có cơ chế và rủi ro riêng; một cache quyết định đúng không tự làm an toàn các cache dữ liệu khác.

## 2. Authorization decision phụ thuộc vào điều gì?

Một quyết định ủy quyền có thể biểu diễn bằng:

~~~text
Decision = Authorize(
    subject,           // người gọi đã xác thực
    tenant,            // phạm vi thuê bao tin cậy
    resource,          // loại, ID và thuộc tính tài nguyên
    action,            // READ, UPDATE, DELETE, APPROVE...
    policy,            // quy tắc/phiên bản đang áp dụng
    context            // grant, ACL, nhóm, thời gian, trạng thái, rủi ro...
)
~~~

Tùy chính sách, một user có thể được READ nhưng không được UPDATE cùng tài liệu; admin ở tenant A vẫn bị từ chối với tài liệu tenant B; tài nguyên được chia sẻ hoặc thu hồi sẽ đổi quyết định ngay cả khi user, tài nguyên và action không đổi.

**Ví dụ:** tenant **T1** có tài liệu **doc-7** của Alice, tenant **T2** cũng có tài liệu **doc-7** của một người khác. Bob ở T1 được chia sẻ doc-7 trong một giờ. Một khóa chỉ bằng **doc-7** không thể phân biệt đối tượng thực tế, người đang hỏi hoặc hiệu lực của chia sẻ.

### 2.1. Những chiều cơ bản của key

| Chiều | Giá trị minh họa | Vì sao cần phân biệt |
| --- | --- | --- |
| Namespace / service / môi trường | reports:prod:v1 | Không trộn cache của các policy domain, ứng dụng hoặc môi trường khác nhau |
| Subject ID ổn định | user-42 | Quyền của Alice không được dùng cho Bob |
| Tenant ID tin cậy | tenant-t1 | Ngăn va chạm ID và quyết định giữa tenant |
| Resource type | document | ID 7 của document không đồng nghĩa ID 7 của invoice |
| Resource ID | doc-7 | Quyền đối với từng đối tượng khác nhau |
| Action | READ / UPDATE | Được đọc không có nghĩa được sửa |
| Policy version | policy-v12 | Quy tắc thay đổi phải tạo namespace logic mới |
| Subject grants version | grants-v5 | Thay đổi role, membership, permission hoặc trạng thái người dùng |
| Resource ACL/version | acl-v9 | Thay đổi owner, share, nhãn phân loại, trạng thái bảo mật của đối tượng |
| Các chiều context khác nếu có | region, assurance, purpose | Chỉ dùng chung khi các yếu tố mà policy thực sự xét là tương đương |

Không nhất thiết mọi hệ thống đều có đúng các trường này. **Tiêu chuẩn là đầy đủ theo policy**, không phải thêm một danh sách cố định rồi mặc định an toàn. Ví dụ nếu quyền phụ thuộc vào tenant subscription, cần thêm tenant entitlement version; nếu quyền phụ thuộc membership của nhóm, cần phiên bản membership hiệu lực; nếu phụ thuộc thời gian, hạn chia sẻ hoặc một lần xác thực mạnh, phải thiết kế cách hết hiệu lực riêng.

Có thể biểu diễn một key rõ ràng như sau:

~~~text
authz:v2 | reports | prod
        | tenant=t1 | subject=alice
        | resourceTenant=t1 | type=document | resource=doc-7
        | action=READ
        | policy=12 | subjectGrant=5 | resourceAcl=9
~~~

Tất cả thành phần này phải được **chuẩn hóa và lấy từ nguồn tin cậy**. Tenant trong URL, trường ownerId trong JSON, role do client khai hoặc policyVersion do request truyền vào không tự trở thành dữ liệu quyền đã được xác minh.

### 2.2. Phân biệt subject, principal, user và phiên đăng nhập

- **Principal** là danh tính mà Spring Security đã xác thực; cần trích ID ổn định theo cách triển khai, không mặc định tên hiển thị luôn duy nhất.
- Một **user** có thể có nhiều session, token hoặc thiết bị. Nếu policy chỉ phụ thuộc quyền tài khoản, key theo user + các phiên bản quyền có thể đủ.
- Nếu policy phụ thuộc **mức xác thực (MFA/assurance), phạm vi OAuth2 token, delegation, session context, device trust, token audience** hoặc thời điểm đăng nhập, phải đưa thông tin tương ứng vào key hoặc **không cache** quyết định đó.
- Không nên đưa nguyên access token, session cookie, dữ liệu cá nhân hoặc email thô vào khóa Redis/log. Dùng ID nội bộ ổn định hoặc định danh đã giảm lộ thông tin, và kiểm soát quyền truy cập hạ tầng cache.

**Token đã hết hạn hoặc bị thu hồi phải bị xử lý ở tầng authentication.** Cache ALLOW không được phép thay thế bước xác thực token/session của mỗi request. Nếu quyền trong token bị thay đổi nhưng token vẫn hợp lệ, cần chính sách thu hồi và hiệu lực quyền rõ ràng; key không tự cập nhật các claim cũ.

## 3. Phân tích các thiết kế key sai và phiên bản đúng

Xét Alice và Bob cùng tenant T1, tài liệu D7 thuộc Alice, chỉ Alice được READ; Carol thuộc T2 có một tài liệu khác cũng mang ID D7.

| Key | Vấn đề | Hậu quả có thể xảy ra |
| --- | --- | --- |
| **authz:D7** | Thiếu user, tenant, action, policy | Bob nhận ALLOW của Alice; T2 dùng quyết định của T1 |
| **authz:alice:D7** | Thiếu tenant, resource type, action, version | Quyền READ bị dùng cho DELETE; cache không biết ACL thay đổi |
| **authz:T1:alice:D7:READ** | Có đủ actor/tenant/action nhưng thiếu version | Sau thu hồi quyền, ALLOW cũ vẫn có thể được trả |
| **authz:T1:alice:D7:READ:policy12** | Policy code version không đại diện ACL/grants | Quy tắc không đổi nhưng membership đã bị rút |
| **authz:T1:alice:D7:READ:policy12:grants5:acl9** | Tương đối tốt trong một policy chỉ phụ thuộc các chiều này | Vẫn phải kiểm tra các yếu tố tenant context, resource type và các thuộc tính động khác |
| **Key cấu trúc đầy đủ theo policy** | Mỗi chiều được định danh và version hóa | Chỉ có thể cache hit giữa các lần đánh giá thực sự tương đương |

Ví dụ ở hàng cuối là **mẫu tư duy**, không phải một cam kết rằng chỉ cần đủ tên trường là đã giải quyết cả thời gian, thay đổi đồng thời hoặc dữ liệu version bị trễ.

### 3.1. Chống va chạm khi đóng gói key

Nếu ghép chuỗi theo cách **tenant + ":" + user + ":" + resource**, một ID chứa dấu **:** có thể tạo ra key giống một tổ hợp thành phần khác. Trong bộ nhớ Java, ưu tiên **record key có các field riêng**; khi gửi Redis, dùng encoding có cấu trúc/độ dài, escaping có quy tắc hoặc mã hóa chuẩn; có thể hash một canonical representation với thuật toán phù hợp khi cần hạn chế lộ danh tính.

Ví dụ dùng **record** thay cho nối chuỗi tùy tiện:

~~~java
record DecisionKey(
        String namespace,
        String subjectTenantId,
        String subjectId,
        String resourceTenantId,
        String resourceType,
        String resourceId,
        Action action,
        long policyVersion,
        long subjectGrantVersion,
        long resourceAclVersion) {
}
~~~

Java record cung cấp **equals/hashCode theo toàn bộ thành phần**; dùng làm key của **ConcurrentHashMap** thuận tiện. Khi mở rộng sang Redis, vẫn cần serializer ổn định giữa các bản deploy và nhất quán kiểu dữ liệu, chuẩn hóa ID, phiên bản schema key.

## 4. Chọn nguồn version: chính sách, người dùng và tài nguyên

### 4.1. Policy version

**Policy version** cần đổi mỗi khi các quy tắc có thể tác động đến quyết định: đổi điều kiện role, bổ sung hạn chế theo tenant, đổi business rule, cập nhật tập policy, thay logic phân loại dữ liệu, v.v.

- Chọn một ID phiên bản **không tái sử dụng** cho cùng policy scope (revision tăng đơn điệu hoặc immutable content hash của policy cùng dependencies).
- Phân biệt **deployment version** với **policy version**: deploy frontend hay sửa log không nhất thiết ảnh hưởng quyền; thay chính sách mà không bump phiên bản là nguy hiểm.
- Nếu policy mỗi tenant khác nhau, dùng policy scope/version có tenant hoặc dimension tương ứng. Một version toàn cục vẫn được nếu mọi thay đổi áp dụng cho tất cả tenant.
- Rollback không được tái sử dụng tùy tiện một epoch cũ nếu dữ liệu grants/ACL đã đổi và key có thể đụng dữ liệu cache trước đó; epoch đơn điệu dễ kiểm soát hơn.

### 4.2. Subject grant version

Cập nhật **subjectGrantVersion** khi thay role/permission trực tiếp, membership, quyền nhóm, trạng thái disable/suspend hoặc một thuộc tính subject mà policy xét. Nếu quyền thừa kế từ nhóm, chỉ bump version của người dùng là chưa đủ khi nhóm đổi mà user record không đổi: có thể dùng **effective authorization epoch**, group/membership version hoặc cơ chế invalidation bao phủ mọi thành viên.

Dữ liệu principal trong token có thể cũ hơn DB. Phải quyết định nguồn nào là quyền hiệu lực và cơ chế làm mới/thu hồi; không lấy một con số version mới nhưng vẫn đánh giá trên tập quyền cũ.

### 4.3. Resource ACL/version

Cập nhật **resourceAclVersion** khi thay chủ sở hữu, chia sẻ, classification, trạng thái tài liệu hoặc metadata mà policy sử dụng. Nếu policy phụ thuộc nhiều resource liên quan (parent folder, project, organization, hierarchy), ACL version của một document con có thể không phản ánh thay đổi ở parent. Cần version tổng hợp, dependency epoch hoặc bỏ cache cho những trường hợp không thể bảo đảm nhất quán.

Một thiết kế an toàn thường lấy thông tin **resourceTenantId, owner, aclVersion** bằng repository/tầng dữ liệu đáng tin, không dùng ID/tenant/owner được client tự khai làm cơ sở quyết định.

### 4.4. Khác biệt giữa cache invalidation và versioned key

Hai chiến lược có thể kết hợp:

- **Versioned key:** thay version làm lần truy cập tiếp theo dùng key mới, không cần tìm hết key cũ để xóa ngay. Đổi lại, key cũ tiếp tục tốn bộ nhớ cho tới eviction/TTL.
- **Eviction/event invalidation:** khi role hoặc ACL thay đổi, xóa các key bị ảnh hưởng. Với cache phân tán, sự kiện có thể đến trễ, mất hoặc sai thứ tự.
- **TTL:** giới hạn thời gian tồn tại của key, hỗ trợ quản lý bộ nhớ và giới hạn cửa sổ stale; TTL **không chứng minh** quyền bị thu hồi tức thời.

Nếu yêu cầu “thu hồi quyền phải có hiệu lực ngay”, cần một nguồn version/permission đủ nhất quán ở **mỗi lần kiểm tra**, hoặc không dùng cache cho quyết định nhạy cảm đó. Chỉ phát sự kiện xóa cache bất đồng bộ không cung cấp bảo đảm mạnh về thời điểm mọi node thôi dùng ALLOW cũ.

## 5. Lưu đồ kiểm quyền có cache

~~~mermaid
flowchart TD
    A[Request qua authentication] --> B{Principal và tenant hợp lệ?}
    B -- Không --> X[DENY]
    B -- Có --> C[Đọc snapshot quyền/ACL và version từ nguồn tin cậy]
    C --> D{Policy input có thể cache an toàn?}
    D -- Không --> E[Đánh giá policy trực tiếp]
    D -- Có --> F[Tạo DecisionKey đầy đủ]
    F --> G{Cache hit hợp lệ, chưa hết TTL?}
    G -- Có --> H[Trả quyết định đã lưu]
    G -- Không --> I[Đánh giá policy trên snapshot]
    I --> J{Có thể lưu theo chính sách TTL/consistency?}
    J -- Có --> K[Lưu ALLOW hoặc DENY với TTL giới hạn]
    J -- Không --> L[Không lưu]
    K --> M[Trả quyết định]
    L --> M
    E --> M
~~~

**Lưu ý quan trọng:** ngay cả khi key chứa version, thuật toán trên chỉ đúng khi **snapshot và các version** phản ánh cùng trạng thái đủ nhất quán, và mọi dữ kiện policy phụ thuộc đều được đưa vào cơ chế version. Nếu lấy version cũ từ local memory trong khi ACL đã đổi trên DB, key mới không giải quyết được quyền stale. Nếu đọc version ở thời điểm A nhưng policy đọc dữ liệu ở thời điểm B, cần thiết kế transaction/snapshot, recheck hoặc cơ chế đồng bộ hóa phù hợp với yêu cầu bảo mật.

Ví dụ thay đổi quyền một tài liệu:

1. Bob chưa được xem report R7; **key(T1, Bob, R7, READ, policy=12, grants=3, acl=8)** trả DENY.
2. Alice chia sẻ R7 với Bob; hệ thống commit ACL mới **acl=9**. Lần đánh giá tiếp theo đọc snapshot mới phải xây key với **acl=9**, đánh giá ALLOW và có thể cache.
3. Alice thu hồi chia sẻ; hệ thống commit **acl=10**. Nếu lần đánh giá tiếp theo lấy snapshot hiện hành, key **acl=10** không thể hit ALLOW của **acl=9**, nên phải đánh giá lại và DENY.
4. Nếu một node còn đọc **acl=9** vì cache metadata/replica lag, node đó có thể dùng ALLOW stale. Đây là vấn đề **nhất quán dữ liệu đầu vào**, không chỉ là cấu trúc key.

## 6. Ví dụ Java 17 chạy độc lập: key đúng chiều và version

Ví dụ nhỏ này không phụ thuộc Spring để tập trung vào tính đúng của key. Tất cả subject/resource là **snapshot đáng tin do server tạo**; các revision phải tăng khi permission/ACL đổi. Policy mẫu: cùng tenant thì owner được READ/EDIT, người được share chỉ READ; ADMIN của một tenant có thể READ/EDIT trong tenant ấy. Quyền admin **không vượt tenant**.

Tạo file **AuthorizationCacheDemo.java**:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class AuthorizationCacheDemo {
    enum Action {
        READ, EDIT
    }

    record Subject(
            String id,
            String tenantId,
            long grantsVersion,
            boolean admin) {
    }

    record Resource(
            String id,
            String tenantId,
            String ownerId,
            long aclVersion,
            Set<String> sharedReaders) {
        Resource {
            sharedReaders = Set.copyOf(sharedReaders);
        }
    }

    record DecisionKey(
            String namespace,
            String subjectTenantId,
            String subjectId,
            String resourceTenantId,
            String resourceType,
            String resourceId,
            Action action,
            long policyVersion,
            long grantsVersion,
            long aclVersion) {
    }

    static final class AuthorizationCache {
        private final ConcurrentHashMap<DecisionKey, Boolean> answers =
                new ConcurrentHashMap<>();
        private final AtomicInteger evaluations = new AtomicInteger();

        boolean allowed(Subject subject, Resource resource,
                        Action action, long trustedPolicyVersion) {
            DecisionKey key = new DecisionKey(
                    "report-service:prod:v1",
                    subject.tenantId(),
                    subject.id(),
                    resource.tenantId(),
                    "report",
                    resource.id(),
                    action,
                    trustedPolicyVersion,
                    subject.grantsVersion(),
                    resource.aclVersion()
            );

            return answers.computeIfAbsent(
                    key,
                    ignored -> evaluate(subject, resource, action)
            );
        }

        private boolean evaluate(Subject subject, Resource resource,
                                 Action action) {
            evaluations.incrementAndGet();

            // Luôn kiểm ranh giới tenant trước cả quyền admin.
            if (!subject.tenantId().equals(resource.tenantId())) {
                return false;
            }

            if (subject.admin()) {
                return true;
            }

            if (subject.id().equals(resource.ownerId())) {
                return true;
            }

            return action == Action.READ
                    && resource.sharedReaders().contains(subject.id());
        }

        int evaluationCount() {
            return evaluations.get();
        }
    }

    public static void main(String[] args) {
        AuthorizationCache cache = new AuthorizationCache();

        Subject alice = new Subject("alice", "T1", 1, false);
        Subject bob = new Subject("bob", "T1", 1, false);
        Subject carol = new Subject("carol", "T2", 1, true);

        Resource original = new Resource(
                "R7", "T1", "alice", 1, Set.of()
        );

        System.out.println("Alice READ: "
                + cache.allowed(alice, original, Action.READ, 1));
        System.out.println("Bob READ: "
                + cache.allowed(bob, original, Action.READ, 1));
        System.out.println("Bob READ again: "
                + cache.allowed(bob, original, Action.READ, 1));
        System.out.println("Evaluations after repeat: "
                + cache.evaluationCount());

        // ACL thay đổi, phiên bản phải tăng để tạo key mới.
        Resource shared = new Resource(
                "R7", "T1", "alice", 2, Set.of("bob")
        );
        System.out.println("Bob after share: "
                + cache.allowed(bob, shared, Action.READ, 1));

        Resource revoked = new Resource(
                "R7", "T1", "alice", 3, Set.of()
        );
        System.out.println("Bob after revoke: "
                + cache.allowed(bob, revoked, Action.READ, 1));

        // Quyền subject đổi thì grantsVersion cũng đổi.
        Subject adminBob = new Subject("bob", "T1", 2, true);
        System.out.println("Bob after admin grant: "
                + cache.allowed(adminBob, revoked, Action.READ, 1));

        // Admin T2 không tự có quyền trong T1.
        System.out.println("Other tenant admin: "
                + cache.allowed(carol, revoked, Action.READ, 1));

        // Policy version đổi khiến cache không hit key phiên bản cũ.
        System.out.println("Bob after policy version bump: "
                + cache.allowed(bob, revoked, Action.READ, 2));
        System.out.println("Evaluations total: "
                + cache.evaluationCount());
    }
}
~~~

Chạy trong thư mục chứa file bằng JDK 17 trở lên:

~~~bash
javac AuthorizationCacheDemo.java
java AuthorizationCacheDemo
~~~

Kết quả stdout kỳ vọng chính xác:

~~~text
Alice READ: true
Bob READ: false
Bob READ again: false
Evaluations after repeat: 2
Bob after share: true
Bob after revoke: false
Bob after admin grant: true
Other tenant admin: false
Bob after policy version bump: false
Evaluations total: 7
~~~

Vì sao tổng số lần chạy policy là **7**? Alice và Bob tạo hai key riêng. Bob lặp lại READ với cùng key nên cache hit. Mỗi lần tăng ACL version, tăng grant version, đổi tenant/subject hoặc tăng policy version tạo key khác, dẫn tới evaluate mới. **Không có quyền chia sẻ giữa Alice và Bob chỉ vì cùng resource ID**.

**Giới hạn có chủ đích của demo:** không có TTL, max size, lưu trữ phân tán, security context thực, transaction hay xác minh snapshot version; vì vậy dùng để học cách key phân biệt đầu vào, **không copy nguyên xi thành cache production**. **trustedPolicyVersion** do mã server giả lập cung cấp; phiên bản policy và phiên bản grant/ACL không được lấy từ request chưa xác thực. Nếu input thay đổi mà revision không tăng, ví dụ vẫn có thể trả kết quả cũ.

## 7. Đưa quyết định có cache vào Spring Security đúng tầng

Ở Spring Security 6, có thể bật kiểm quyền method bằng **@EnableMethodSecurity**, sau đó dùng **@PreAuthorize** gọi một bean policy. Kiểm cache nên nằm **bên trong bộ máy đánh giá authorization**; cache HIT chỉ thay việc đánh giá lại một *decision* đã có input tương đương, không bỏ qua authentication và không thay thế cơ chế bảo vệ các đường vào service.

Luồng phù hợp:

~~~text
SecurityFilterChain
   -> xác thực user/token/session
   -> Spring-managed service method proxy
   -> @PreAuthorize gọi policy bean
   -> policy bean nạp subject + resource + version đáng tin
   -> authorization decision cache (hit hoặc đánh giá lại)
   -> nếu ALLOW mới gọi logic nghiệp vụ
~~~

Các đoạn Spring sau là **minh họa tích hợp**; các kiểu ứng dụng như **ReportDto**, **ReportRepository**, **DecisionService** và cơ chế load quyền/tenant cần định nghĩa theo hệ thống thật. Ví dụ Java độc lập ở mục 6 là chương trình runnable.

**SecurityConfig.java (đoạn class cấu hình):**

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
}
~~~

**ReportService.java (đoạn service boundary):**

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
    public ReportDto read(String reportId) {
        return repository.findDtoById(reportId);
    }
}
~~~

**ReportPolicy.java (đoạn bean policy):**

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {
    private final DecisionService decisionService;

    public ReportPolicy(DecisionService decisionService) {
        this.decisionService = decisionService;
    }

    public boolean canRead(Authentication authentication, String reportId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        // DecisionService phải lấy subject/tenant/ACL/version
        // từ principal đã xác thực và repository đáng tin.
        return decisionService.canRead(authentication, reportId);
    }
}
~~~

Trong **@PreAuthorize**, **#p0** trỏ tham số phương thức đầu tiên, tránh phụ thuộc tên tham số được giữ khi biên dịch. **@EnableMethodSecurity** phải có hiệu lực trong application context; lời gọi service phải đi qua Spring-managed proxy. Nếu gọi method có annotation bằng **this.method()** trên cùng bean, Spring AOP proxy có thể bị bỏ qua; đừng coi cache hoặc annotation là rào cản duy nhất nếu đường gọi thực tế bỏ interceptor.

**Quan trọng:** không tùy tiện đặt **@Cacheable** trực tiếp lên method trả **ReportDto** chỉ vì đã có **@PreAuthorize**. Một cache dữ liệu được áp dụng trước bước authorization hoặc một đường gọi khác không đi qua security proxy có thể trả dữ liệu sai chủ. Tách phần **đánh giá quyết định** và phần **lấy nội dung**; kiểm chứng thứ tự advice và mọi entry point bằng test thực tế.

Nếu chọn **@Cacheable** cho policy evaluator, cần kiểm chứng **key generator**, SpEL key, proxy interception, TTL của provider và điều kiện khi chính sách thay đổi. Spring Cache mặc định chọn key từ các tham số phương thức; nếu phương thức chỉ nhận resource ID mà đọc current user từ thread-local, key mặc định **thiếu user/tenant/action/version** và rất nguy hiểm. Tạo một **DecisionKey đầy đủ** rồi truyền vào hàm cache, hoặc dùng cache API trực tiếp để kiểm soát mọi chiều.

## 8. TTL, ALLOW/DENY và thu hồi quyền trong thực tế

### 8.1. TTL nên là hệ quả của mức chấp nhận stale

| Loại quyết định | Gợi ý chính sách cache | Rủi ro cần kiểm soát |
| --- | --- | --- |
| READ trên tài nguyên ít đổi quyền | TTL ngắn/có version và evict | ALLOW stale sau thu hồi chia sẻ |
| WRITE/DELETE/APPROVE có tác động cao | Có thể không cache hoặc yêu cầu version mạnh và tái kiểm ngay trước ghi | Lệnh ghi vẫn thành công dù role/ACL vừa đổi |
| DENY tạm thời do chưa được share | Có thể cache ngắn với version đáng tin | Sau khi được cấp quyền, DENY cũ vẫn gây lỗi trải nghiệm |
| DENY do trạng thái khẩn cấp, policy động | Thường cần kiểm lại nếu không mô hình hóa context/version | Kết quả stale không phản ánh risk level mới |
| Quyết định theo thời gian/điều kiện ngắn hạn | TTL phải không vượt thời điểm sớm nhất decision mất hiệu lực | Trả ALLOW sau hạn chia sẻ hoặc sau hết phiên MFA |

Không có con số TTL phổ quát. Đội hệ thống phải xác định **revocation SLA** (ví dụ yêu cầu hiệu lực ngay, trong vài giây hay theo phiên) và chọn chiến lược dựa trên khả năng đảm bảo thực tế của dữ liệu version, replica và các node. **TTL 30 giây chỉ là giới hạn thời gian cache**, không bảo đảm mọi node từ chối trong 0 giây.

Nếu decision phụ thuộc vào **expiresAt** của một quyền tạm thời, đặt TTL không vượt **min(TTL cấu hình, expiresAt - now)** và cẩn thận với lệch đồng hồ; đôi khi phù hợp hơn là bỏ cache hoặc dùng nguồn thời gian nhất quán. Với context khó đưa vào key (mức rủi ro theo request, IP, thiết bị), mặc định **không cache** trừ khi chứng minh được các trường hợp tương đương và giới hạn stale.

### 8.2. Sau khi thay đổi role, share hoặc policy

Một quy trình an toàn theo mức độ yêu cầu nhất quán có thể gồm:

1. Cập nhật dữ liệu quyền tại nguồn có thẩm quyền và tăng **revision/epoch** tương ứng trong cùng đơn vị nhất quán (thường là transaction).
2. Chỉ công bố version mới sau khi thay đổi được commit; xác định rõ các node sẽ đọc phiên bản nào và có cho phép stale replica hay không.
3. Phát invalidation/event hoặc thay namespace version cho những bộ nhớ đệm liên quan; có retry/deduplicate và xử lý sự kiện đến sai thứ tự.
4. Khi request kế tiếp đến, lấy **snapshot + version** đủ mới; dựng key, chỉ hit nếu mọi chiều khớp; khi không thể xác minh version, lựa chọn dựa trên risk policy: đánh giá lại từ nguồn có thẩm quyền hoặc từ chối có kiểm soát.
5. Với thao tác đặc biệt nhạy cảm, kiểm lại quyền tại thời điểm commit/transaction để tránh **time-of-check to time-of-use (TOCTOU)**: được phép lúc kiểm nhưng quyền bị rút trước khi cập nhật DB.

Không chỉ xóa key ở một node rồi giả định toàn bộ hệ thống đã thu hồi. Nếu có **L1 local cache + L2 Redis**, mỗi tầng đều có trạng thái riêng; invalidation, TTL và version đọc từ đâu phải rõ ràng.

### 8.3. Cache downtime và lỗi policy backend

- **Cache không truy cập được:** nếu có thể đánh giá policy từ nguồn chính thống, bỏ qua cache và tính lại. Nếu nguồn policy cũng lỗi, không trả **ALLOW** theo mặc định cho một thao tác nhạy cảm.
- **Có cached ALLOW nhưng không đọc được version hiện hành:** không thể khẳng định key đang còn hiệu lực. Với hệ thống yêu cầu thu hồi ngay, cần tránh dùng cached ALLOW.
- **Cache stampede:** nhiều request cùng miss có thể dồn tải lên policy backend. Dùng per-key load-coalescing, TTL có jitter, bounded cache, hạn chế batch và theo dõi độ trễ; không nới lỏng kiểm quyền chỉ để giảm tải.
- **Cache poisoning / key tampering:** namespace và key phải do server tính; không lấy raw cache key hoặc arbitrary policyVersion từ client; cache storage phải có ACL mạng, mã hóa và audit phù hợp.

## 9. Bộ kiểm thử cần có

Một test cache authorization phải kiểm **cả tính đúng quyền** lẫn **hiệu năng**. Chỉ thấy cache hit tăng không chứng minh hệ thống an toàn.

| Test case | Cùng gì? | Thay đổi gì? | Kỳ vọng |
| --- | --- | --- | --- |
| Cache HIT hợp lệ | Subject, tenant, resource, action, versions | Không đổi | Cùng quyết định; evaluator không chạy lại |
| Chặn user khác | Tenant, resource, action, versions | Alice → Bob | Không dùng ALLOW của Alice cho Bob |
| Chặn tenant khác | Resource ID dạng trùng nhau | T1 → T2 | Không va chạm/không cho truy cập chéo |
| Chặn action khác | User, tenant, resource | READ → DELETE | READ ALLOW không cấp DELETE |
| Chặn resource type khác | Tenant, user, ID | document → invoice | Không dùng chung decision |
| Thay ACL | User/resource/action | Share hoặc revoke + ACL version tăng | Key mới, quyết định được tính lại |
| Thay role/grant | User/resource/action | Subject grant version tăng | Key mới, không giữ role cũ |
| Thay policy | Mọi đầu vào nghiệp vụ khác | Policy version tăng | Quy tắc mới được đánh giá |
| Thay quan hệ parent/group | Resource/con quan hệ | Parent ACL hoặc group membership đổi | Version dependency phản ánh và không giữ quyền cũ |
| Hết hạn grant | Cùng key cơ bản | Thời gian qua expiry | Không trả ALLOW quá hạn |
| Cache lỗi | Request hợp lệ | Redis unavailable | Recompute an toàn hoặc từ chối theo policy |
| Nhiều node | Request phân phối L1/L2 | Thu hồi quyền trên node A | Node B đáp ứng revocation SLA |
| Update đồng thời | Cùng user/resource | ACL thay trong lúc evaluate/cache insert | Không hồi sinh ALLOW trái phép |
| Object deleted/recreated | Cùng resource ID | Generation của object đổi | Key/version ngăn reuse decision cho object mới |

Đối với Spring Security, viết test qua **MockMvc** hoặc test service với **@WithMockUser** và principal thật tương ứng. Phải có case **ALLOW** và **DENY** ở request, sau đó thử trực tiếp policy service qua bean Spring để chắc chắn không bị HTTP matcher che lỗi cache. Khi kiểm thao tác ghi, đối chiếu **side effect** trong DB: trả 403 sau khi dữ liệu đã thay đổi vẫn là lỗi.

Gợi ý property cho key builder: với hai bộ input khác nhau ở **một trường mà policy phụ thuộc**, key phải khác; khi mọi thành phần giống nhau, key phải bằng nhau và hashCode phải nhất quán. Cần test canonicalization cho ID có dấu phân cách hoặc ký tự Unicode. Với Redis serializer, kiểm tra giữa nhiều version ứng dụng và các field tùy chọn.

### 9.1. Test trạng thái âm và dương

Đặc biệt tránh viết chỉ test người có quyền. Ví dụ:
- Alice được đọc D7, Bob không được đọc D7: Bob phải DENY ngay cả sau khi cache đã lưu ALLOW của Alice.
- Bob được share D7: sau khi version tăng, Bob phải ALLOW.
- Thu hồi share D7: sau khi version tăng, Bob phải DENY và không có dữ liệu D7 trong response.
- Bob được nâng role admin **trong T1**: tài liệu thuộc T2 vẫn phải DENY.
- Khi policyVersion thay đổi, một key cũ không được truy hồi bằng phiên bản mới, kể cả khi decision cuối cùng tình cờ giống nhau.

Với thao tác nhạy cảm, tự động hóa thêm test race/invalidation bằng latch hoặc fake clock, thay vì dùng **Thread.sleep** tạo bài test flaky. Fake clock giúp thử thời điểm TTL hết hạn và quyền tạm thời bị thu hồi một cách xác định.

## 10. Theo dõi hiệu năng và an toàn vận hành

Nên đo riêng **số lần evaluate**, hit/miss theo service/action, thời gian policy check ở p50/p95/p99, TTL expirations, số lần invalidation, queue lag của sự kiện, version-fetch latency, cache memory/cardinality và số request phải fallback khi backend lỗi.

**Cache hit rate cao không phải bằng chứng hiệu năng tốt nếu key quá thô**: có thể tỷ lệ hit cao vì vô tình chia sẻ ALLOW giữa các user. Ngược lại, key đầy đủ có nhiều phiên bản có thể giảm hit rate nhưng đúng về quyền. Tối ưu dựa trên **tỷ lệ hit hợp lệ + độ trễ + mức stale thực đo**, không chỉ tối đa hóa hit.

Khi log và audit:
- Có thể ghi **namespace, action, outcome, hit/miss, policy revision, request trace ID** và các mã resource/subject đã được giảm độ nhạy theo chính sách.
- Tránh log toàn bộ token, user session, ACL nhạy cảm hoặc key chứa email/IP thô.
- Cần phân biệt **authorization denied** do chính sách với **backend unavailable**, **snapshot/version unavailable**, và **cache hit**; nếu gom hết vào một HTTP 403 hoặc một metric khó phát hiện sự cố vận hành.
- Giới hạn kích thước cache (size/weight), đặt TTL/eviction, quan sát số key cũ sau mỗi đợt bump version; versioned key giúp correctness nhưng có thể làm tăng cardinality.

### Checklist review thiết kế

1. Key có đủ **subject + tenant đáng tin + resource type/ID + action** không? Có phân biệt resource tenant nếu khác subject tenant hoặc nếu ID chỉ duy nhất trong tenant không?
2. Policy áp dụng cho decision này thuộc **scope** nào? Bản deploy/code nào làm version đổi? Có thể tái sử dụng version cũ không?
3. Mọi dữ liệu **grants, ACL, parent/group, tenant entitlement** ảnh hưởng decision có revision hoặc cơ chế invalidation bảo đảm không?
4. Phiên bản và dữ liệu quyền được đọc từ **cùng trạng thái nhất quán** hay có độ trễ replica/local cache? Có SLA thu hồi thực sự?
5. Permission phụ thuộc **thời gian, MFA, token scope, IP, risk, purpose** hoặc các điều kiện biến động khác không? Nếu có, key/TTL có bao phủ đầy đủ hay nên bỏ cache?
6. Hệ thống chặn khi **cache/version backend lỗi** như thế nào? Có return ALLOW cũ khi không còn chứng cứ hợp lệ không?
7. Nơi tích hợp có giữ authentication và method/request authorization **trước khi trả tài nguyên** hay vô tình cache cả response nghiệp vụ?
8. Có test hit đúng, cross-user/cross-tenant, action khác, policy đổi, revoke, concurrency, multi-node và side effect không?
9. Cache có **bounded size, TTL, metrics và cách xóa key cũ** không? Có bảo vệ nội dung cache và log khỏi lộ danh tính không?

## 11. Kết luận vận dụng

Một cache authorization chỉ an toàn khi **key đại diện chính xác cho mọi dữ kiện mà policy đã dùng để ra quyết định**, và các dữ kiện đó còn hiệu lực tại thời điểm dùng lại. Bốn nhóm lõi của thiết kế là **subject, tenant, resource/action và version**; version phải bao phủ cả **logic policy** lẫn các dữ liệu quyền có thể thay đổi như **role/grant** và **ACL**.

Trong Spring Security, đặt cache ở policy/decision layer, lấy subject từ security context đã xác thực, lấy tenant/resource metadata/version từ nguồn tin cậy, kiểm **negative authorization** và hành vi thu hồi bằng test. Khi không thể đảm bảo snapshot/version đủ mới cho yêu cầu bảo mật, **đánh giá lại hoặc không cache** là lựa chọn đúng hơn việc phục vụ một cached ALLOW không còn căn cứ.

### Tài liệu tra cứu

- Spring Security, Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework, Cache Abstraction và annotation @Cacheable: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework, AOP proxying và self-invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- OWASP, Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
