# Triển khai thay đổi chính sách có phiên bản, kiểm chứng và quay lui

> **Ngữ cảnh:** Spring Security — Authorization, nhóm **Hiệu năng và vận hành**. Bài này hướng dẫn đưa một thay đổi **chính sách phân quyền** vào hệ thống đang phục vụ người dùng: đánh số phiên bản, kiểm chứng trước khi kích hoạt, phát hành theo giai đoạn, quan sát quyết định thực tế và quay lại phiên bản đã được phê duyệt khi phát hiện sự cố. Ví dụ dùng Java 17+ và có phần tích hợp Spring Security 6.x/7.x.

## 1. Vì sao cần quản lý vòng đời của chính sách phân quyền?

Một thay đổi như “người duyệt được đọc báo cáo của mọi chủ sở hữu” thành “chỉ người sở hữu được đọc” có thể ảnh hưởng hàng nghìn request. Cả hai kiểu lỗi đều đáng quan tâm:

- **Nới quyền ngoài ý muốn:** người dùng hoặc tenant A đọc/sửa/xóa tài nguyên của B; nguy cơ Broken Access Control.
- **Siết quyền ngoài ý muốn:** nghiệp vụ hợp lệ bị trả `403`, job thất bại, người dùng không hoàn thành tác vụ.
- **Không nhất quán:** instance A đã dùng rule mới, instance B còn rule cũ; cùng principal và tài nguyên có kết quả khác nhau.
- **Không tái lập được sự cố:** log chỉ ghi “denied” nhưng không cho biết quyết định đến từ phiên bản chính sách nào.
- **Quay lui chậm hoặc sai:** code đã đổi, token/cache chưa cập nhật, hoặc rule cũ không còn tương thích với schema mới.

Quy tắc cốt lõi là **chính sách được đóng gói thành bản bất biến (immutable versioned snapshot)**, được kiểm chứng trước khi phát hành và được chọn thông qua một **con trỏ phiên bản đang hoạt động**. Không chỉnh sửa nội dung của phiên bản đã kích hoạt. Mọi quyết định nên ghi nhận `policyId`, `policyVersion`, hành động, loại tài nguyên và kết quả; chỉ thu thập định danh/log theo quy định bảo mật dữ liệu.

Quy trình chuẩn:

~~~text
Đề xuất thay đổi
    |
    v
Tạo bản mới (version + schema + digest)
    |
    v
Static validation + automated authorization matrix
    |
    v
Simulation / shadow evaluation (không thực thi quyền của bản mới)
    |
    v
Stage -> Canary -> Mở rộng theo từng đợt
    |              |
    |              +-- sai lệch/403/latency bất thường --> dừng, rollback
    v
Kiểm chứng toàn cụm + audit -> Hoàn tất
~~~

**Versioning không tự bảo đảm bảo mật.** Khả năng quay lui chỉ có ý nghĩa khi cấu hình, storage, policy evaluator, quyền thực tế và dữ liệu nghiệp vụ cùng được thiết kế hỗ trợ.

## 2. Phân biệt các loại phiên bản phải theo dõi

Không gộp toàn bộ thành một nhãn “v2” mơ hồ.

| Phiên bản/thành phần | Ví dụ | Dùng để làm gì |
| --- | --- | --- |
| `policyId` | `report-read` | Xác định tập quy tắc của một năng lực nghiệp vụ |
| `policyVersion` | `2026-11-06.2` | Phân biệt **nội dung chính sách** bất biến |
| `schemaVersion` | `1` | Xác nhận parser/evaluator hiểu được cấu trúc |
| `digest` SHA-256 | Hash của byte chuẩn hóa | Phát hiện nội dung cùng tên version bị thay đổi |
| `applicationVersion` | `service-3.8.4` | Xác định phiên bản code Spring đang chạy |
| `activeVersion` | `2026-11-06.2` | Con trỏ chỉ phiên bản hiện được áp dụng |
| `rolloutId` | `rollout-20261106-a` | Gom các bước canary, metrics và audit vào cùng một đợt |
| `policyDecisionVersion` | Giá trị ghi vào log/tracing | Trả lời “request này được đánh giá bởi rule nào?” |

Ví dụ một **policy bundle** ở dạng JSON minh họa (không phải cấu hình mặc định của Spring Security):

~~~json
{
  "policyId": "report-read",
  "policyVersion": "2026-11-06.2",
  "schemaVersion": 1,
  "defaultEffect": "DENY",
  "requireAuthority": "report:read",
  "allowOwner": true,
  "allowReviewerCrossOwner": false
}
~~~

Sau khi tạo bundle, tính digest SHA-256 trên **đúng byte của artifact được phát hành**, lưu trong manifest/registry và ký theo cơ chế triển khai. Không để hai nội dung khác nhau mang cùng một `policyId + policyVersion`. Nếu phát hiện cùng version nhưng hash khác, **từ chối tải** và điều tra, không tự “lấy bản mới nhất” để thay.

Nội dung bản mới cần có metadata quản trị: tác giả, người review/phê duyệt, ticket, thời gian, link ma trận kiểm thử, phiên bản code tương thích, chiến lược canary, phương án quay lui và hạn dự kiến hoàn tất. Các thông tin này được lưu trong release record/audit; không nhất thiết tất cả phải nằm trong payload rule.

### Một chính sách nên có phạm vi gì?

Đơn vị version cần đủ chặt để rollback nhất quán. Nếu một hành động đòi cả quyền endpoint và quyền trên object, có hai lựa chọn rõ ràng:

- **Đóng gói cùng bundle:** một version quản lý toàn bộ quy tắc cần thay đổi; khi kích hoạt, dùng nguyên snapshot.
- **Nhiều bundle phụ thuộc nhau:** release manifest phải pin **đúng tập version tương thích**; không để rule mới của endpoint gặp rule cũ của service.

Dù chọn cách nào, hãy ưu tiên **deny by default**, đánh giá trên identity/authority đã xác thực, và kiểm tra owner/tenant của từng tài nguyên. Không coi ẩn nút ở frontend là một policy enforce tại server.

## 3. Mô hình “prepare, verify, activate, revert”

Một vòng đời đơn giản có các trạng thái:

~~~text
DRAFT -> VALIDATED -> STAGED -> CANARY -> ACTIVE
           |             |         |        |
           v             v         v        v
        REJECTED       ABORTED   ABORTED   SUPERSEDED
                                           (rollback đến
                                            snapshot trước)
~~~

Không cần tạo máy trạng thái phức tạp cho bài toán nhỏ, nhưng hành vi phải rõ:

1. **Prepare:** tạo artifact mới, kiểm schema, field bắt buộc, giá trị hợp lệ, danh sách dependency và hash.
2. **Verify:** kiểm bảng quyết định `subject × action × resource × context`; chạy test dương/âm, regression, hiệu năng và kiểm tương thích.
3. **Stage:** phân phối snapshot tới instance, nhưng **chưa đổi con trỏ active**.
4. **Canary:** chỉ áp dụng bản mới cho nhóm request/chủ thể được chọn có chủ đích; theo dõi quyết định và tác động.
5. **Activate:** đổi con trỏ active với điều kiện phiên bản trước vẫn đúng; ghi audit.
6. **Revert:** nếu vượt ngưỡng đã thống nhất, trỏ về snapshot cũ đã được kiểm chứng, đối chiếu trạng thái sau rollback và xử lý hậu quả đã xảy ra.

**Hai bất biến quan trọng:**

- **Immutable artifact:** không sửa `version=2026-11-06.2` tại chỗ sau khi đã stage; sửa nội dung thì tạo version khác.
- **Conditional switch:** chỉ đổi active từ `v1` sang `v2` nếu active thực sự vẫn là `v1`, tránh release cũ ghi đè release khác.

Trong ứng dụng chỉ chạy **một JVM**, `AtomicReference.compareAndSet` là ví dụ dễ hiểu cho chuyển version nguyên tử. Trong hệ thống **nhiều instance**, nó **không phải cơ chế phối hợp toàn cụm**: phải dùng một registry/config store có atomic compare-and-swap, ETag/revision hoặc transaction, rồi xác nhận tất cả instance đã nhìn thấy version mong muốn.

## 4. Java 17: một ví dụ chạy độc lập từ đầu đến cuối

Ví dụ minh họa phép kiểm tra quyền đọc báo cáo:

- `policy-v1`: người sở hữu có quyền `report:read` được đọc; reviewer có cả `report:read` và `report:read:any` cũng được đọc báo cáo khác owner.
- `policy-v2`: chính sách mới bỏ ngoại lệ reviewer cross-owner; chỉ owner có `report:read` được đọc.
- Candidate phải qua ma trận kiểm chứng trước khi activate; nếu kết quả sau activate bất thường thì rollback bằng cách trỏ lại snapshot trước.

Đây là **ví dụ kỹ thuật mô phỏng policy lifecycle**, chưa phải dịch vụ phân phối policy production. Chương trình chạy bằng JDK 17, không cần Spring.

Tạo file **`PolicyRolloutDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

public final class PolicyRolloutDemo {

    record Principal(String name, Set<String> authorities) {
        Principal {
            Objects.requireNonNull(name, "name");
            authorities = Set.copyOf(authorities);
        }

        boolean has(String authority) {
            return authorities.contains(authority);
        }
    }

    record Report(long id, String owner) {
    }

    record PolicySnapshot(String version, boolean allowReviewerCrossOwner) {
        PolicySnapshot {
            if (version == null || version.isBlank()) {
                throw new IllegalArgumentException("version is required");
            }
        }
    }

    record Decision(String policyVersion, boolean allowed) {
    }

    static final class PolicyRegistry {
        private final Map<String, PolicySnapshot> versions =
                new ConcurrentHashMap<>();
        private final AtomicReference<PolicySnapshot> active;

        PolicyRegistry(PolicySnapshot initial) {
            Objects.requireNonNull(initial, "initial");
            versions.put(initial.version(), initial);
            active = new AtomicReference<>(initial);
        }

        // Tạo bản bất biến mới; không được ghi đè version đã tồn tại.
        void stage(PolicySnapshot candidate) {
            Objects.requireNonNull(candidate, "candidate");
            if (versions.putIfAbsent(candidate.version(), candidate) != null) {
                throw new IllegalArgumentException("duplicate version");
            }
        }

        String activeVersion() {
            return active.get().version();
        }

        PolicySnapshot activeSnapshot() {
            return active.get();
        }

        Decision decide(Principal principal, Report report) {
            // Snapshot được lấy đúng một lần cho quyết định này.
            return evaluate(active.get(), principal, report);
        }

        Decision preview(String version, Principal principal, Report report) {
            PolicySnapshot candidate = versions.get(version);
            if (candidate == null) {
                throw new IllegalArgumentException("unknown version");
            }
            return evaluate(candidate, principal, report);
        }

        // Thao tác này dùng được cho promote lẫn rollback.
        boolean switchTo(String expectedActiveVersion, String targetVersion) {
            PolicySnapshot before = active.get();
            if (!before.version().equals(expectedActiveVersion)) {
                return false; // lệnh cũ, active đã thay đổi
            }

            PolicySnapshot target = versions.get(targetVersion);
            if (target == null) {
                throw new IllegalArgumentException("target not staged");
            }
            return active.compareAndSet(before, target);
        }

        static Decision evaluate(PolicySnapshot policy,
                                 Principal principal, Report report) {
            boolean allowed = principal != null
                    && report != null
                    && principal.has("report:read")
                    && (principal.name().equals(report.owner())
                        || (policy.allowReviewerCrossOwner()
                            && principal.has("report:read:any")));

            return new Decision(policy.version(), allowed);
        }
    }

    private static void require(boolean condition, String description) {
        if (!condition) {
            throw new IllegalStateException(description);
        }
    }

    public static void main(String[] args) {
        PolicyRegistry registry = new PolicyRegistry(
                new PolicySnapshot("policy-v1", true));

        Principal owner = new Principal("an", Set.of("report:read"));
        Principal reviewer = new Principal("reviewer",
                Set.of("report:read", "report:read:any"));
        Principal outsider = new Principal("linh", Set.of("report:read"));
        Report own = new Report(101L, "an");
        Report another = new Report(102L, "binh");

        System.out.println("v1 reviewer cross-owner: "
                + registry.decide(reviewer, another).allowed());

        registry.stage(new PolicySnapshot("policy-v2", false));

        boolean ownerAllowed = registry.preview(
                "policy-v2", owner, own).allowed();
        boolean reviewerDenied = !registry.preview(
                "policy-v2", reviewer, another).allowed();
        boolean outsiderDenied = !registry.preview(
                "policy-v2", outsider, own).allowed();

        require(ownerAllowed && reviewerDenied && outsiderDenied,
                "candidate failed authorization matrix");
        System.out.println("v2 preview: PASS");

        require(registry.switchTo("policy-v1", "policy-v2"),
                "promotion failed");
        System.out.println("promoted: " + registry.activeVersion());
        System.out.println("v2 reviewer cross-owner: "
                + registry.decide(reviewer, another).allowed());

        // Lệnh được tạo với precondition cũ không thể ghi đè active mới.
        boolean staleSucceeded = registry.switchTo(
                "policy-v1", "policy-v1");
        require(!staleSucceeded, "stale write unexpectedly succeeded");
        System.out.println("stale activation rejected: "
                + !staleSucceeded);

        require(registry.switchTo("policy-v2", "policy-v1"),
                "rollback failed");
        System.out.println("rolled back: " + registry.activeVersion());
        System.out.println("v1 reviewer cross-owner: "
                + registry.decide(reviewer, another).allowed());
    }
}
~~~

Chạy bằng:

~~~bash
javac --release 17 PolicyRolloutDemo.java
java PolicyRolloutDemo
~~~

**Stdout kỳ vọng** (kiểm chứng theo logic chương trình):

~~~text
v1 reviewer cross-owner: true
v2 preview: PASS
promoted: policy-v2
v2 reviewer cross-owner: false
stale activation rejected: true
rolled back: policy-v1
v1 reviewer cross-owner: true
~~~

Những gì mã thật sự chứng minh:

- Snapshot đã stage được preview **không thay đổi active**.
- Cùng principal và resource tạo kết quả khác nhau khi active chuyển từ `policy-v1` sang `policy-v2`.
- `switchTo(expected, target)` dùng **compare-and-set**: lệnh với precondition `policy-v1` bị từ chối nếu active đã thành `policy-v2`.
- Rollback là **đổi active pointer** về snapshot cũ có sẵn, không sửa source rule.
- `Decision` luôn kèm `policyVersion`; có thể xuất version vào audit/metrics để tái hiện quyết định.

**Giới hạn có chủ ý của ví dụ:** registry chỉ ở bộ nhớ một JVM; chưa lưu bền snapshot, chữ ký/digest, phân quyền người triển khai, canary routing, event log, điều phối nhiều node hoặc compatibility check. Những phần đó thuộc pipeline vận hành bên dưới. Không lấy ví dụ này làm production policy registry khi có nhiều instance.

**Lưu ý bảo mật khi rollback:** `policy-v1` trong ví dụ nới quyền hơn `policy-v2`. Quay lại `v1` chỉ phù hợp khi phạm vi quyền cũ đã được kiểm chứng và việc nới quyền được chấp thuận. Nếu `v1` chính là nguồn gây lộ dữ liệu, **không tự động rollback về v1**: có thể chuyển sang một **snapshot an toàn hơn** (deny với thao tác nhạy cảm) hoặc thực hiện hotfix có phiên bản mới.

## 5. Tích hợp phiên bản chính sách vào Spring Security

Đoạn ví dụ Java ở mục 4 dùng lớp lồng nhau để tiện chạy một file. Khi tích hợp Spring Boot, chuyển `PolicyRegistry`, `PolicySnapshot` và policy evaluator sang các Spring bean/package phù hợp. Mục tiêu là **mọi request đi qua cùng một policy source** đang active.

Ví dụ Spring MVC (snippet minh họa phương pháp tích hợp; giả định các interface tương ứng đã được triển khai trong dự án):

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}

// Một service được quản lý bởi Spring, gọi qua proxy.
@Service
class ReportService {

    @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
    public Report read(long reportId) {
        return reportRepository.findById(reportId).orElseThrow();
    }
}
~~~

`#p0` là tham số thứ nhất của method, không lệ thuộc tên tham số khi compile. `reportPolicy` là bean chứa logic đọc snapshot và quyết định:

~~~java
@Component("reportPolicy")
class ReportPolicy {

    private final PolicyRegistry registry;
    private final ReportRepository reports;

    boolean canRead(Authentication authentication, long id) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        Report report = reports.findById(id).orElse(null);
        if (report == null) {
            return false;
        }

        PolicySnapshot snapshot = registry.activeSnapshot();

        // Map GrantedAuthority và username từ Spring Authentication
        // sang domain Principal rồi evaluate trên snapshot đã pin.
        Principal principal = toPrincipal(authentication);
        return PolicyRegistry.evaluate(snapshot, principal, report).allowed();
    }
}
~~~

Đây là **snippet kiến trúc**, không phải file độc lập để biên dịch nguyên trạng: constructor/field wiring, `toPrincipal(...)`, domain classes và repository phải được cung cấp theo project. Điểm bắt buộc là `Authentication` lấy từ Spring Security, không phải field client `isAdmin`; kiểm tra resource owner/tenant trên server; và chỉ đọc snapshot **một lần** cho mỗi quyết định.

Phần HTTP vẫn có thể dùng:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/reports/**")
            .authenticated()
        .anyRequest().denyAll()
);
~~~

Rule HTTP ở đây kiểm tra authentication và deny-by-default; **quy tắc read theo resource nằm trong service**. Có thể tăng cường authorization ở HTTP bằng custom `AuthorizationManager` dùng cùng policy source. Tránh sao chép hai bộ quy tắc không đồng bộ giữa `SecurityFilterChain` và service. `@EnableMethodSecurity` là cơ chế Servlet; với ứng dụng WebFlux dùng `@EnableReactiveMethodSecurity` và Reactor Context, cần tích hợp tương ứng.

### Pin version cho cả một thao tác nghiệp vụ

Một lần đọc snapshot cho mỗi phép kiểm là đủ cho ví dụ đơn giản. Khi request đi qua nhiều bước (xem -> duyệt -> ghi DB) và policy có thể đổi giữa chừng, phải định nghĩa tính nhất quán:

- **Pin snapshot** đã xác thực và kiểm quyền cho cả transaction/use case, truyền version qua service boundary tin cậy.
- Hoặc **re-evaluate** tại từng hành động nhạy cảm theo active mới nếu policy yêu cầu quyền tức thời; có thể dẫn tới kết quả khác nhau giữa các bước, nên phải thiết kế nghiệp vụ xử lý rõ ràng.
- Không tin `X-Policy-Version` do client tự gửi để chọn một phiên bản có quyền rộng hơn. Chọn version ở **trusted server-side routing/config**; header do server phát ra chỉ hỗ trợ chẩn đoán.

Nếu có việc thu hồi khẩn cấp quyền truy cập, độ trễ truyền rule và cache/token cũ có thể quan trọng hơn tính nhất quán “pin lâu”. Cần quy định rõ session/token revocation, TTL và thời hạn các quyết định được cache.

## 6. Kiểm chứng trước kích hoạt: chính sách phải qua ma trận kiểm thử

Trước khi đổi con trỏ active, chạy **tập dữ liệu đại diện** qua policy đang active và candidate mới. Tập test phải có cả positive, negative, cross-tenant và trường hợp biên.

Ví dụ cho `policy-v2` của mục 4:

| Principal | Quyền | Resource | `policy-v2` kỳ vọng | Vì sao |
| --- | --- | --- | --- | --- |
| `an` | `report:read` | Report 101, owner `an` | ALLOW | Đúng quyền và đúng owner |
| `an` | `report:read` | Report 102, owner `binh` | DENY | Không đọc chéo owner |
| `reviewer` | `report:read`, `report:read:any` | Report 102 | DENY | Chính sách mới bỏ ngoại lệ reviewer |
| `reviewer` | Chỉ `report:read:any` | Report 102 | DENY | Không có quyền đọc chức năng |
| Không xác thực | Không có authority | Report 101 | DENY | Anonymous không được truy cập |
| `linh` | `report:write` | Report 101 | DENY | Quyền ghi không hàm ý quyền đọc |
| `an` | `report:read` | Resource không tồn tại | DENY/404 | Không thể cấp quyền vào object vắng mặt |
| Người dùng tenant khác | `report:read` | Report ngoài tenant | DENY | Chính sách nhiều tenant phải chặn cross-tenant |

Ma trận cuối với tenant yêu cầu mở rộng domain model và policy so với file Java demo; **không được coi là đã được kiểm trong code mẫu**. Khi thực tế có business rule theo owner/tenant/status, phải thêm dữ liệu và assertion tương ứng.

Một test nên xác minh **kết quả và policy version**: ví dụ v1 cho phép reviewer truy cập cross-owner trong khi v2 từ chối; nếu delta đó được phê duyệt, test phải cho thấy các trường hợp khác không đổi. Đừng chỉ kiểm tra status `200`; test lộ dữ liệu, tác dụng phụ DB, số lượng bản ghi và version active.

### Bốn tầng kiểm chứng

1. **Static validation:** JSON/YAML parse được, schema đúng version, trường bắt buộc, deny-by-default, không trùng policy ID/version, digest/signature hợp lệ, không mở rộng wildcard ngoài phạm vi.
2. **Automated behavior tests:** JUnit/MockMvc/WebTestClient + integration test dưới Spring Security thật; kiểm `401`/`403`, object owner, tenant, quyền ghi, inheritance, route và method.
3. **Compatibility & regression:** policy bundle tương thích với mọi application build còn chạy, role/claim mapping từ identity provider, format dữ liệu, DB/cache schema, token cũ và mới.
4. **Performance & resilience:** benchmark latency của `AuthorizationManager`/method evaluator, hit/miss cache, throughput và chế độ lỗi khi policy store không phản hồi.

**Shadow evaluation:** cho request thật tiếp tục quyết định bằng active policy, đồng thời chạy candidate ở chế độ **chỉ quan sát**, tuyệt đối không dùng kết quả shadow để cấp quyền hoặc trả nội dung cho client. Thu thập số lượng `ALLOW -> DENY`, `DENY -> ALLOW` theo nhóm nghiệp vụ, kiểm xem delta khớp changelog. Các thay đổi `DENY -> ALLOW` phải được review riêng vì có thể mở quyền không chủ ý. Shadow nên chạy theo mẫu dữ liệu hạn chế, bảo vệ thông tin nhạy cảm và không lặp lại tác dụng phụ.

### Ví dụ bộ kiểm thử tự động cho registry

Nếu chuyển các record/class ở file Java demo thành code project và có JUnit Jupiter, có thể viết những assertion sau; đây là **snippet test** dựa vào class ở mục 4, không phải file độc lập thứ hai:

~~~java
@Test
void candidateDoesNotBecomeActiveUntilPromoted() {
    var registry = new PolicyRegistry(
            new PolicySnapshot("v1", true));
    registry.stage(new PolicySnapshot("v2", false));

    assertEquals("v1", registry.activeVersion());
    assertFalse(registry.preview("v2",
            new Principal("reviewer", Set.of("report:read",
                    "report:read:any")),
            new Report(102, "binh")).allowed());
}

@Test
void staleRollbackMustNotOverwriteNewerVersion() {
    var registry = new PolicyRegistry(
            new PolicySnapshot("v1", true));
    registry.stage(new PolicySnapshot("v2", false));

    assertTrue(registry.switchTo("v1", "v2"));
    assertFalse(registry.switchTo("v1", "v1"));
    assertEquals("v2", registry.activeVersion());
}
~~~

Trong dự án thật, thêm các test cố ý từ chối **version không tồn tại**, **trùng version**, role thiếu, anonymous và xem dữ liệu tenant khác. Cần test trên `@PreAuthorize`/Spring bean thật để chắc chắn không bỏ qua AOP. Đừng dùng mock của chính evaluator khi mục tiêu kiểm tra evaluator.

## 7. Triển khai theo giai đoạn: từ canary đến toàn cụm

### A. Stage

Đưa artifact đã ký và kiểm hash vào policy registry/bộ lưu cấu hình tin cậy. Giữ snapshot trước để rollback. Các instance có thể preload candidate nhưng **không tự kích hoạt**.

Kiểm tra: ứng dụng đọc được version mới, parse đúng schema, dependencies đủ, không có lỗi đánh giá và active hiện tại không đổi. Ghi rõ người phê duyệt và thời gian của kế hoạch phát hành.

### B. Canary

Bật policy mới trước cho phạm vi nhỏ có chủ đích (ví dụ nhóm tài khoản nội bộ hoặc 1% request đủ điều kiện), **cố định lựa chọn cohort** để một user không bị hai kết quả khác nhau giữa các request liên tiếp. Với quyết định liên quan owner/tenant, tốt hơn canary theo tenant/user đã xác định thay vì random theo từng request.

Giữ nhóm đối chứng dùng version cũ; so sánh tỷ lệ allow/deny theo **tình huống nghiệp vụ**, tránh chỉ nhìn số `403` tổng. Một chiến dịch siết quyền hợp lệ có thể làm `403` tăng có chủ ý; cần phân biệt deny *đúng chính sách* và deny gây lỗi nghiệp vụ.

### C. Tăng dần và toàn bộ

Khi canary pass, mở cohort theo các nấc được duyệt, sau đó chuyển toàn bộ. Tại mỗi nấc, xác minh:

- Policy version báo cáo từ mọi instance và mọi vùng/khu vực.
- Request không được định tuyến tới version chưa được kiểm chứng.
- Decision delta khớp ma trận dự kiến; không có `DENY -> ALLOW` ngoài phạm vi.
- Tỷ lệ lỗi, latency, timeout, fallback, load của policy evaluator và áp lực lên database/remote PDP.
- Các job bất đồng bộ, cache, background consumer, API khác có cùng policy sau khi hết TTL.

**Không lấy “đã ghi active pointer” làm bằng chứng rollout hoàn tất.** Pointer ở registry đã đổi nhưng node có thể chưa đồng bộ; dùng metrics `policy_active_version{service,instance,...}` hoặc báo cáo tương đương. Khi chưa đồng nhất, chặn mở rộng/giải quyết cache và cảnh báo. Không gắn user ID hoặc report ID tùy ý làm label metrics vì cardinality rất lớn; log/tracing với cơ chế bảo vệ dữ liệu phù hợp để truy vết chi tiết.

## 8. Chọn tín hiệu quan sát, ngưỡng dừng và điều kiện hoàn tất

Định nghĩa trước khi deploy những gì sẽ khiến hệ thống **tiếp tục**, **dừng** hoặc **rollback**. Giá trị ngưỡng phải phù hợp baseline và được owner nghiệp vụ/SRE/security phê duyệt; không có ngưỡng `403` hay p95 chung cho mọi ứng dụng.

| Tín hiệu | Mục đích | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| `policy_active_version` mỗi instance | Phát hiện mixed versions | Một phần instance chưa lên version mong muốn |
| `authorization_decisions_total` theo version/action/outcome | Kiểm soát allow/deny | Delta ngoài danh sách thay đổi đã duyệt |
| `policy_evaluation_duration` p50/p95/p99 | Theo dõi hiệu năng | Tăng latency do policy lookup/DB/remote PDP |
| `policy_evaluation_errors_total` | Phát hiện evaluator hỏng | Parse error, timeout, exception, version không rõ |
| HTTP `401`/`403` theo route/cohort | Phát hiện người dùng bị chặn | Đột biến bất thường ngoài chính sách |
| Business outcome | Kiểm chứng không phá quy trình | Tỷ lệ phê duyệt/thanh toán/tạo báo cáo thất bại |
| Audit `policy_switch` | Điều tra nguyên nhân | Thiếu version, actor, thời gian, lý do, revision |

**Ví dụ ngưỡng minh họa** (không phải tiêu chuẩn dùng trực tiếp): dừng canary nếu số deny **ngoài ma trận đã duyệt** lớn hơn 0; hoặc tỷ lệ lỗi nghiệp vụ ở canary tăng vượt ngưỡng chênh lệch đã thống nhất với control. Với policy siết quyền, 403 tăng đúng kế hoạch **không nhất thiết là lỗi**; điều kiện dừng phải bám vào đối tượng bị ảnh hưởng.

Mọi quyết định có thể ghi cấu trúc như sau; đây là **mẫu event**, không phải log có dữ liệu thật:

~~~json
{
  "event": "authorization_decision",
  "policyId": "report-read",
  "policyVersion": "2026-11-06.2",
  "action": "report.read",
  "resourceType": "report",
  "outcome": "DENY",
  "reasonCode": "NOT_OWNER",
  "rolloutId": "rollout-20261106-a"
}
~~~

Không đưa raw token, mật khẩu, thông tin cá nhân nhạy cảm hoặc payload tài nguyên vào log. `reasonCode` phải được tính bởi logic bảo mật thật; không dùng thông điệp lỗi thô làm mã lý do. Để truy vết một sự cố, liên kết audit decision với trace/request ID theo chính sách dữ liệu.

## 9. Quy trình rollback an toàn

**Rollback chính sách** khác với rollback code và khác với phục hồi dữ liệu. Một thao tác đổi pointer thường nhanh, nhưng **không hoàn tác** các thay đổi dữ liệu đã được xử lý theo policy mới.

### Khi nào kích hoạt rollback?

- Có truy cập trái phép/`DENY -> ALLOW` không được phê duyệt.
- Dịch vụ nghiệp vụ hợp lệ bị chặn vượt ngưỡng.
- Policy evaluator lỗi, latency vượt SLO, không đọc được candidate, dữ liệu version trên các node lệch nhau.
- Candidate không tương thích với application build hoặc schema hiện đang chạy.

Trình tự khuyến nghị:

1. **Dừng rollout và đóng băng promotion.** Giữ log/trace và xác nhận version đang active thực tế; thông báo người phụ trách vận hành/an ninh theo quy trình sự cố.
2. **Chọn target an toàn.** Nếu version cũ đang gây lộ dữ liệu, tuyệt đối không quay lại nó chỉ vì dễ làm; có thể kích hoạt snapshot hạn chế hơn hoặc chế độ bảo vệ tạm thời.
3. **Thực hiện conditional switch** với `expectedActiveVersion`/revision, tránh lệnh rollback cũ vô tình ghi đè một hotfix mới. Ghi lý do, actor và phiên bản đích.
4. **Đồng bộ và xác minh toàn cụm.** Kiểm tra từng node, cache và job; tránh tuyên bố thành công chỉ từ response của registry.
5. **Chạy lại ma trận smoke test.** Kiểm tra quyền hợp lệ, quyền bị từ chối, owner/tenant, đường HTTP và nghiệp vụ bị ảnh hưởng; theo dõi trở lại baseline.
6. **Xử lý tác động đã xảy ra.** Rollback policy không thu hồi response đã trả ra, không tự sửa bản ghi đã xóa và không hủy mọi URL đã ký; điều tra/audit, thu hồi quyền/token, phục hồi hoặc bù trừ nếu cần.
7. **Giữ lại bản lỗi để điều tra**, không chỉnh sửa version lỗi; tạo version mới đã fix và cho qua kiểm thử/canary trước lần thử tiếp.

Ví dụ điều kiện chuyển khi đã xác minh active `v2`:

~~~text
Expected active: policy-v2
Target snapshot: policy-v1
Atomic switch: compare-and-swap(policy-v2 -> policy-v1)
Postcondition: mọi node trả policy-v1 và ma trận quyền PASS
~~~

Đây là **mô tả thao tác**, không phải câu lệnh CLI có sẵn trong Spring Security. Spring Security không cung cấp lệnh “rollback policy” cho tất cả hệ thống; registry/CI/CD/GitOps của từng tổ chức phải triển khai cơ chế này.

### Những giới hạn rollback cần xử lý từ đầu

- **Schema/code:** nếu rule mới dựa vào field/role/API chỉ build mới hiểu, phiên bản cũ có thể không chạy sau code/database migration. Dùng backwards-compatible schema hoặc rollout code trước rồi policy sau.
- **Cache/token:** quyền có thể nằm trong token, session hoặc cache; rollback registry không xóa tự động thông tin đang cache. Có chính sách TTL/invalidation và revocation rõ ràng.
- **Multi-region:** mỗi vùng có thể nhận event khác nhau; cần định nghĩa mức nhất quán, báo cáo last-applied revision, timeout và hành vi khi mất registry.
- **Fail-open:** không tự cho phép tất cả khi evaluator lỗi, policy version lạ hoặc timeout. Quy định fail-closed/dedicated fallback đã được xét duyệt.
- **Tác động ngoài hệ thống:** email đã gửi, webhook đã gọi, thanh toán đã thực hiện hoặc dữ liệu đã tải xuống sẽ không biến mất do rollback policy; có runbook khắc phục riêng.

## 10. Bài toán hiệu năng và độ tin cậy khi đọc policy

Không cần request nào cũng gọi remote policy registry. Thông thường các instance giữ **immutable snapshot** tại local memory và nhận update bằng cơ chế subscribe/poll phù hợp; request đọc con trỏ hiện hoạt động. Tuy nhiên phải giải quyết các vấn đề:

**Latency:** đánh giá authority/owner đơn giản có thể rất nhanh, nhưng policy truy cập database/remote PDP ở mỗi request sẽ ảnh hưởng p95/p99. Đo và kiểm tra hiệu năng theo workload, đặt timeout phù hợp; tránh kết hợp nhiều query lặp lại cho mỗi resource.

**Cache quyết định:** nếu cache theo role nhưng bỏ resource ID/tenant/owner, có thể trả lại ALLOW cho sai đối tượng. Key phải bao gồm ngữ cảnh ảnh hưởng quyền, **policy version** và principal/tenant an toàn; có TTL và invalidation khi quyền thay đổi. Không cache allow vô hạn.

**Tính nhất quán:** mọi request cần gắn decision với version thực sự dùng. Nếu request qua nhiều service, hoặc pin chung version được xác minh hoặc mỗi service ghi version của riêng mình để truy vết và có contract rõ ràng.

**Đọc khi registry lỗi:** không biến lỗi fetch policy thành `permitAll()`. Tiếp tục dùng snapshot cũ **chỉ nếu** đã được phê duyệt và còn trong thời hạn freshness; với thay đổi thu hồi quyền khẩn cấp, có thể cần fail-closed cho hành động nhạy cảm. Theo dõi `lastSuccessfulPolicyRefresh` và cảnh báo khi quá ngưỡng.

**Cardinality:** metrics nên gắn version, action, service, nhóm outcome; tránh gắn từng `userId`/`resourceId` vào metric label. Dùng log/tracing bảo vệ dữ liệu cho điều tra từng request.

## 11. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Sửa nội dung “v1” tại chỗ | Không thể audit/rollback chính xác | Version bất biến, digest kiểm chứng |
| Chỉ ghi version, không ghi schema/build | Parser khác nhau xử lý sai | Compatibility matrix và schemaVersion |
| Bật toàn bộ ngay sau unit test | Lỗi dữ liệu thực bùng phát toàn hệ | Shadow, canary, mở rộng có kiểm soát |
| Rollback bằng lệnh không có precondition | Ghi đè release/hotfix mới hơn | CAS/ETag/revision, audit |
| Chỉ nhìn số `403` tổng | Hiểu nhầm deny hợp lệ thành sự cố | So sánh ma trận quyền và business outcomes |
| Mỗi node tự chọn “latest” | Mixed versions, không nhất quán | Active pointer tập trung, kiểm per-instance |
| Đổi role client rồi tin ngay | Bypass authorization | Server-side trusted Authentication |
| Cache không có policyVersion/tenant | Allow sai sau đổi rule | Key đủ scope, TTL và invalidation |
| Lỗi fetch policy thì permitAll | Biến lỗi hạ tầng thành lỗ hổng | Fail-closed/safe fallback |
| Chỉ revert policy, quên dữ liệu | Thiếu xử lý hậu quả | Incident review, revoke và bù trừ |
| Bỏ qua self-invocation của `@PreAuthorize` | Một số đường gọi không thực thi policy | Kiểm thử qua Spring proxy và entry point |
| Không có test cross-tenant/IDOR | Bản mới mở quyền đọc chéo | Negative authorization matrix và kiểm object |

## 12. Checklist triển khai và tiêu chí hoàn tất

### Trước rollout

- [ ] Artifact có `policyId`, `policyVersion`, `schemaVersion`, hash và người phê duyệt; version bất biến.
- [ ] Có mô tả delta quyền (chính xác ai/action/object nào thay đổi).
- [ ] Test fail/allow, owner/tenant, anonymous, quyền ghi và default-deny đều PASS.
- [ ] Shadow/diff xác nhận các `ALLOW -> DENY` và `DENY -> ALLOW` đều có lý do.
- [ ] Code/schema/cache/token và các job tương thích với cả active và candidate.
- [ ] Có snapshot trước an toàn, quyền rollback được giới hạn, ngưỡng dừng đã được duyệt.
- [ ] Có metrics và dashboard chia theo policyVersion, action, service/cohort.

### Trong rollout

- [ ] Stage không tự kích hoạt; active version chưa đổi trong bước kiểm candidate.
- [ ] Canary theo cohort ổn định, có nhóm đối chứng.
- [ ] Chỉ tăng rollout khi điều kiện an toàn và business KPI PASS.
- [ ] Không có instance sử dụng version không rõ hoặc digest sai.
- [ ] Mọi promotion dùng conditional revision/CAS và ghi audit.

### Sau rollout hoặc rollback

- [ ] Mọi instance/vùng xác nhận active version mong muốn.
- [ ] Ma trận smoke test PASS với phiên bản thực tế.
- [ ] Tỷ lệ deny, lỗi nghiệp vụ và latency nằm trong giới hạn đã định.
- [ ] Cache, async worker, token/session và cơ chế fallback đã kiểm tra.
- [ ] Audit ghi đầy đủ previous/next version, actor, lý do, thời gian và kết quả.
- [ ] Nếu rollback do sự cố quyền, đã đánh giá dữ liệu lộ/thay đổi và cách xử lý hậu quả.

## 13. Bài tập ứng dụng

Thiết kế policy `invoice-approve` với version `v1` cho quản lý duyệt hóa đơn dưới một ngưỡng và `v2` giảm ngưỡng, đồng thời yêu cầu cùng tenant. Viết ma trận ít nhất tám ca: anonymous, thiếu authority, đúng authority/đúng tenant, khác tenant, sát ngưỡng, vượt ngưỡng, trạng thái đã duyệt và request lặp. Tạo candidate bất biến; chạy preview không ảnh hưởng active; mô phỏng canary, promote với precondition version, rồi rollback khi một ca hợp lệ bị từ chối. Trong báo cáo, giải thích vì sao rollback không tự hoàn tác hóa đơn đã phê duyệt ở phiên bản mới.

## Tài liệu tham khảo

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [OWASP — Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)

**Ghi nhớ:** Một thay đổi policy chỉ được coi là triển khai xong khi quyết định quyền theo version mới đã được kiểm chứng, toàn bộ instance áp dụng nhất quán, và nhóm vận hành biết rõ cách dừng/quay lui bằng một phiên bản an toàn.