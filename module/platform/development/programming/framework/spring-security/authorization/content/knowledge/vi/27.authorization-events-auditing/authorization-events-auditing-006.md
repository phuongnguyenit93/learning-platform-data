# Phân biệt audit truy cập với lịch sử thay đổi quyền

Trong **Spring Security - authorization**, câu hỏi **“Ai đã truy cập hoặc bị từ chối lúc nào?”** khác với câu hỏi **“Ai đã thay đổi quyền, thay đổi gì, có hiệu lực từ lúc nào?”**. Cả hai đều cần audit, nhưng chúng quan sát **hai loại hành vi khác nhau**. Nếu trộn lẫn chúng, đội vận hành có thể biết một yêu cầu nhận HTTP 403 mà không giải thích được quyền đã bị thu hồi bởi ai; ngược lại, có thể biết vai trò của người dùng được nâng cấp mà không biết đặc quyền đó có bị sử dụng hay chưa.

Bài thuộc nhóm **Sự kiện và audit**. Mục tiêu là thiết kế, thu thập và đối chiếu đúng **audit quyết định truy cập (access/authorization audit)** với **lịch sử thay đổi quyền (permission-change history)**, trong bối cảnh ứng dụng Servlet dùng Spring Security.

## 1. Định nghĩa chính xác hai loại bằng chứng

### 1.1. Audit truy cập: điều gì đã xảy ra ở thời điểm kiểm tra quyền?

Một **access audit event** ghi lại một lần hệ thống xem xét hoặc thực thi quyền đối với một hành động trên tài nguyên, ví dụ:

- `alice` được **ALLOW** khi yêu cầu đọc `invoice:42` lúc 10:00.
- `bob` bị **DENY** khi yêu cầu cùng hành động lúc 10:01.
- Một request bị từ chối ở tầng HTTP bởi `AuthorizationFilter`; hoặc một method bị chặn bởi `@PreAuthorize`.
- Một thao tác nhạy cảm như xuất dữ liệu, phê duyệt giao dịch, xóa tài nguyên được cấp quyền và thực sự chạy.

Cần phân biệt ba mức: **authorization decision** (ALLOW/DENY), **HTTP response** (200/401/403/404/5xx) và **business outcome** (thao tác thành công/thất bại). Chúng không đồng nhất: một decision ALLOW vẫn có thể dẫn tới 500; một method đã được cấp quyền nhưng cập nhật database thất bại; 401 có thể xảy ra trong bước xác thực trước khi có quyết định authorization đầy đủ.

Trường dữ liệu gợi ý cho **access audit**:

| Trường | Ý nghĩa |
| --- | --- |
| `eventId`, `occurredAt` | ID không trùng; thời điểm UTC của sự kiện |
| `principalId`, `principalType`, `tenantId` | Chủ thể được kiểm tra: user/service/workload; tenant nếu có |
| `action`, `resourceType`, `resourceId` | Hành động và đối tượng được xét, ví dụ `invoice:read` và `invoice:42` |
| `decision`, `reasonCode` | ALLOW/DENY và lý do được chuẩn hóa, ví dụ `MISSING_AUTHORITY` |
| `policyVersion` hoặc `entitlementVersion` | Phiên bản quy tắc/tập quyền **thực sự được dùng** khi kiểm tra, nếu hệ thống hỗ trợ |
| `requestId`, `traceId`, `serviceId` | Liên kết với request/trace và service tạo quyết định |
| `authenticationMethod`, `sessionIdHash` (nếu cần) | Ngữ cảnh xác thực tối thiểu, theo quy định bảo vệ dữ liệu |
| `operationOutcome` (nếu có) | Trạng thái thực thi nghiệp vụ sau khi ALLOW; không được trộn với `decision` |

Không cần ghi tất cả cho mọi endpoint. Chọn mức chi tiết dựa trên rủi ro, lưu lượng, bảo mật và mục tiêu điều tra. Các giá trị như URL, IP, user-agent hoặc ID có thể là dữ liệu cá nhân, cần quản lý đúng chính sách.

### 1.2. Lịch sử thay đổi quyền: cấu hình phân quyền đã biến đổi ra sao?

Một **permission-change event** ghi lại lần **thay đổi trạng thái có hiệu lực hoặc yêu cầu thay đổi** của một thành phần phân quyền, ví dụ:

- Quản trị viên gán hoặc thu hồi role `REPORT_VIEWER` cho `bob`.
- Role `REPORT_VIEWER` được thêm permission `INVOICE_EXPORT`.
- Quy tắc ABAC đổi từ “owner-only” sang “owner hoặc reviewer được chỉ định”.
- ACL của `document:19` thay đổi từ `bob:READ` sang `bob:READ,WRITE`.
- Chính sách được ban hành phiên bản mới, rollback về phiên bản trước, hoặc đổi trạng thái hiệu lực.
- Cấu hình cấp phép tạm thời hết hạn, bị thu hồi hoặc được gia hạn.

Đây là **audit của hành động quản trị thay đổi quyền**, không phải bản sao của bảng role/permission hiện tại. Bản ghi cần đủ dữ liệu để chứng minh *ai đề xuất, ai phê duyệt, ai thực thi, điều gì đã đổi, lúc nào có hiệu lực và do đâu*.

Trường dữ liệu gợi ý cho **permission-change history**:

| Trường | Ý nghĩa |
| --- | --- |
| `changeId`, `occurredAt`, `effectiveAt` | ID sự kiện, thời điểm ghi nhận và thời điểm có hiệu lực |
| `operatorId`, `approverId` (nếu có) | Ai thực hiện/ai phê duyệt việc thay đổi |
| `targetType`, `targetId`, `tenantId` | Quyền của ai hoặc policy/role/resource nào được sửa |
| `changeType` | `GRANT`, `REVOKE`, `POLICY_UPDATED`, `ROLE_PERMISSION_CHANGED`, `EXPIRED`, `ROLLBACK` |
| `before`, `after` hoặc `diff` | Trạng thái cũ/mới của **đúng phạm vi thay đổi**, không phải dump toàn bộ principal |
| `oldVersion`, `newVersion` | Phiên bản quyền/policy trước và sau; hỗ trợ đối chiếu lịch sử |
| `reason`, `ticketId`, `approvalId` | Lý do nghiệp vụ và bằng chứng phê duyệt |
| `transactionId`, `deploymentId`, `source` | Liên kết commit, cấu hình, yêu cầu tự động hoặc bản triển khai |
| `result` | `APPLIED` / `REJECTED` / `FAILED`, để không ghi nhầm thao tác thất bại thành đã đổi quyền |

**Gán role cho một user**, **thay permission của một role**, **sửa policy** và **đổi ACL của một đối tượng** là các phạm vi thay đổi khác nhau. Một record phải nói rõ phạm vi. Nếu chỉ lưu “bob được thêm role” mà không lưu role đó có những quyền gì vào thời điểm ấy, sau này sẽ khó tái lập chính xác quyết định truy cập.

## 2. So sánh nhanh

| Tiêu chí | Audit truy cập | Lịch sử thay đổi quyền |
| --- | --- | --- |
| Câu hỏi cốt lõi | Ai yêu cầu làm gì trên tài nguyên nào; được cho phép hay từ chối? | Ai làm thay đổi quyền/role/policy/ACL nào? |
| Tác nhân được ghi | **Principal bị kiểm tra** | **Operator thực hiện**, **target chịu thay đổi**, approver nếu có |
| Trigger | Lần kiểm tra quyền, hành động nhạy cảm hoặc kết quả thao tác | Lệnh grant/revoke, policy publish, role edit, ACL update, rollback |
| Kết quả | `ALLOW`/`DENY` và outcome nghiệp vụ riêng | `APPLIED`/`FAILED`/`REJECTED` và before/after |
| Dữ liệu trọng tâm | `principal`, `action`, `resource`, `decision`, `policyVersion`, `requestId` | `operator`, `target`, `changeType`, `before`, `after`, `version`, `reason` |
| Tần suất | Thường rất cao | Thường thấp hơn nhưng giá trị điều tra cao |
| Nguồn phát sinh | Authorization filter, method security, service decision, business action | IAM/admin service, role store, ACL service, policy pipeline |
| Điều không chứng minh | ALLOW không đảm bảo nghiệp vụ đã thành công | Một quyền mới không chứng minh nó đã được dùng |
| Phân tích điển hình | Nhiều DENY đột biến, truy cập tài nguyên nhạy cảm | Ai cấp quyền vượt chính sách, ai sửa quy tắc trước sự cố? |

**Authentication audit** là loại khác: đăng nhập thành công/thất bại, MFA, đăng xuất hoặc token refresh. Việc xác thực thành công không đồng nghĩa được phép truy cập tài nguyên. **Data-change audit** lại trả lời “ai đã thay giá trị dữ liệu nghiệp vụ?”. Một bản sửa hóa đơn có thể vừa có access audit (được phép sửa), vừa có data-change audit (đã sửa trường gì), dù không hề thay đổi quyền.

## 3. Timeline: vì sao cần cả hai

Giả sử quyền `INVOICE_READ` được dùng để đọc `invoice:42`.

| UTC | Dấu vết | Sự kiện |
| --- | --- | --- |
| 10:00 | Access | `alice` đọc `invoice:42`: ALLOW, quyền phiên bản `v1` |
| 10:01 | Access | `bob` đọc `invoice:42`: DENY, `v1` |
| 10:02 | Permission change | `admin` GRANT `INVOICE_READ` cho `bob`; phiên bản `v1 -> v2`, ticket `T-42` |
| 10:03 | Access | `bob` đọc `invoice:42`: ALLOW, `v2` |
| 10:04 | Permission change | `admin` REVOKE `INVOICE_READ` của `bob`; `v2 -> v3`, ticket `T-99` |
| 10:05 | Access | `bob` đọc `invoice:42`: DENY, `v3` |

Nếu chỉ nhìn access audit, ta thấy quyết định cho `bob` chuyển DENY → ALLOW → DENY nhưng **không biết nguyên nhân thay đổi quyền**. Nếu chỉ nhìn history, ta thấy hai hành động cấp/thu hồi nhưng **không biết `bob` đã thực sự truy cập `invoice:42` trong khoảng được cấp quyền**. Ghép bằng `principal/target`, `action`, phạm vi tài nguyên, thời gian và `policyVersion` mới tái dựng diễn biến.

Lưu ý: kết quả cũng có thể thay đổi **mà không có GRANT/REVOKE** do điều kiện ABAC, owner, giờ làm việc, trạng thái tài nguyên, feature flag, policy rollout, TTL token hay thuộc tính trong context. Vì vậy “mỗi DENY phải có một permission-change event trước đó” là giả định sai. Một thay đổi role có thể đã commit nhưng token/JWT cũ hoặc bộ đệm vẫn chứa claims trước đó; ghi **phiên bản hoặc snapshot đã dùng tại thời điểm quyết định** giúp giải thích trường hợp này.

## 4. Lớp nào trong Spring Security sinh loại sự kiện nào?

Trong ứng dụng **Spring Security Servlet**:

1. Bộ lọc xác thực và `AuthenticationManager` giải quyết danh tính/credentials; chúng có thể tạo **authentication events**. Đây chưa phải bằng chứng user có quyền đọc một tài nguyên cụ thể.
2. `AuthorizationFilter` áp dụng `authorizeHttpRequests` ở tầng request. `@EnableMethodSecurity` cùng `@PreAuthorize`/`@PostAuthorize` có thể áp dụng kiểm tra ở tầng method.
3. `AuthorizationEventPublisher` có thể công bố các **authorization events**. `SpringAuthorizationEventPublisher` phát `AuthorizationDeniedEvent` cho các lần từ chối; **granted events không được phát mặc định** vì dễ gây lưu lượng lớn. Nếu sản phẩm cần audit mọi ALLOW nhạy cảm, phải chủ động cấu hình hoặc thu thập tại điểm nghiệp vụ thích hợp.
4. `ExceptionTranslationFilter` cùng `AuthenticationEntryPoint`/`AccessDeniedHandler` giúp chuyển lỗi bảo mật thành HTTP response. HTTP status không thay thế bản ghi quyết định truy cập; cùng mã 403 có thể xuất hiện do nhiều nguyên nhân.
5. Spring Boot Actuator có **audit framework** và `AuditEventRepository`; tài liệu mô tả các sự kiện mặc định gồm authentication success/failure và access-denied exception. `InMemoryAuditEventRepository` thích hợp để thử nghiệm, **không phải lịch sử bền vững cho production**.
6. **Spring Security không tự ghi một lịch sử phiên bản bất biến về mọi lần sửa role/ACL/policy trong database ứng dụng.** Các đường cập nhật quyền phải phát sự kiện nghiệp vụ do hệ thống sở hữu, gắn với transaction và nơi lưu bền vững.

Luồng khái quát:

~~~text
                     SECURITY DECISION PATH
HTTP -> Authentication -> AuthorizationFilter / Method Authorization
                                      |
                               ALLOW hoặc DENY
                                      |
                          Authorization event/audit sink
                                      |
                   Không mặc nhiên là permission change

                     PERMISSION CHANGE PATH
Admin UI / IAM / Policy deploy -> xác thực + kiểm tra quyền quản trị
                                      |
                               cập nhật role/ACL/policy
                                      |
                             commit + audit/outbox
                                      |
                            Permission-change history
~~~

Không giả định mỗi filter luôn chạy đúng một lần cho mọi business action. Một request có thể có nhiều authorization checks (request + method + object), redirect/dispatch, retry hoặc async processing. Muốn lập báo cáo số “lần người dùng truy cập hóa đơn” cần xác định **đơn vị đếm** và cách chống đếm trùng (`eventId`, `requestId`, `decisionPoint`).

## 5. Ví dụ Java 17 chạy độc lập: một timeline, hai sổ audit

Chương trình sau **chạy bằng JDK 17+**, không cần Spring hay database. Nó mô phỏng quyết định truy cập theo tập quyền hiện hành, lưu audit truy cập, và lưu lịch sử mỗi thay đổi grant thành hai tập record **bất biến tại thời điểm ghi**. Mục tiêu là thấy dữ liệu cần lưu và cách phiên bản quyền giải thích quyết định, không phải cung cấp IAM production.

Tệp `AuditTimelineDemo.java`:

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AuditTimelineDemo {

    enum Decision { ALLOW, DENY }

    record AccessAudit(
            Instant time,
            String requestId,
            String principal,
            String resource,
            String permission,
            Decision decision,
            long policyVersion) {
    }

    record PermissionChange(
            Instant time,
            String changeId,
            String operator,
            String target,
            String permission,
            boolean before,
            boolean after,
            long versionBefore,
            long versionAfter,
            String reason) {
    }

    private final Map<String, Set<String>> grants = new HashMap<>();
    private final List<AccessAudit> accesses = new ArrayList<>();
    private final List<PermissionChange> changes = new ArrayList<>();
    private long policyVersion = 1;

    private static Instant at(String value) {
        return Instant.parse(value);
    }

    private void check(String requestId, String principal,
                       String resource, String permission, String time) {
        boolean allowed = grants.getOrDefault(principal, Set.of())
                .contains(permission);

        accesses.add(new AccessAudit(
                at(time), requestId, principal, resource,
                permission, allowed ? Decision.ALLOW : Decision.DENY,
                policyVersion));
    }

    private void changeGrant(
            String changeId, String operator, String target,
            String permission, boolean grant, String reason, String time) {
        Set<String> beforeSet = grants.getOrDefault(target, Set.of());
        boolean before = beforeSet.contains(permission);

        if (before == grant) {
            return; // Không có thay đổi trạng thái; xem xét audit ATTEMPT riêng.
        }

        Set<String> next = new HashSet<>(beforeSet);
        if (grant) {
            next.add(permission);
        } else {
            next.remove(permission);
        }

        long previousVersion = policyVersion;
        grants.put(target, Set.copyOf(next));
        policyVersion++;

        changes.add(new PermissionChange(
                at(time), changeId, operator, target, permission,
                before, grant, previousVersion, policyVersion, reason));
    }

    private void printReports() {
        System.out.println("=== ACCESS AUDIT ===");
        for (AccessAudit a : accesses) {
            System.out.printf(
                    "%s req=%s principal=%s resource=%s perm=%s decision=%s version=v%d%n",
                    a.time(), a.requestId(), a.principal(),
                    a.resource(), a.permission(), a.decision(),
                    a.policyVersion());
        }

        System.out.println("=== PERMISSION HISTORY ===");
        for (PermissionChange c : changes) {
            System.out.printf(
                    "%s change=%s by=%s target=%s perm=%s %s->%s version=v%d->v%d reason=%s%n",
                    c.time(), c.changeId(), c.operator(), c.target(),
                    c.permission(), c.before(), c.after(),
                    c.versionBefore(), c.versionAfter(), c.reason());
        }
    }

    public static void main(String[] args) {
        AuditTimelineDemo demo = new AuditTimelineDemo();

        // Trạng thái v1 đã tồn tại trước thời điểm mô phỏng.
        demo.grants.put("alice", Set.of("INVOICE_READ"));

        demo.check("req-101", "alice", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:00:00Z");
        demo.check("req-102", "bob", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:01:00Z");

        demo.changeGrant("chg-201", "admin", "bob", "INVOICE_READ",
                true, "T-42", "2026-01-01T10:02:00Z");
        demo.check("req-103", "bob", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:03:00Z");

        demo.changeGrant("chg-202", "admin", "bob", "INVOICE_READ",
                false, "T-99", "2026-01-01T10:04:00Z");
        demo.check("req-104", "bob", "invoice:42", "INVOICE_READ",
                "2026-01-01T10:05:00Z");

        demo.printReports();
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 AuditTimelineDemo.java
java AuditTimelineDemo
~~~

Kết quả chuẩn (thời gian cố định, không phụ thuộc đồng hồ máy):

~~~text
=== ACCESS AUDIT ===
2026-01-01T10:00:00Z req=req-101 principal=alice resource=invoice:42 perm=INVOICE_READ decision=ALLOW version=v1
2026-01-01T10:01:00Z req=req-102 principal=bob resource=invoice:42 perm=INVOICE_READ decision=DENY version=v1
2026-01-01T10:03:00Z req=req-103 principal=bob resource=invoice:42 perm=INVOICE_READ decision=ALLOW version=v2
2026-01-01T10:05:00Z req=req-104 principal=bob resource=invoice:42 perm=INVOICE_READ decision=DENY version=v3
=== PERMISSION HISTORY ===
2026-01-01T10:02:00Z change=chg-201 by=admin target=bob perm=INVOICE_READ false->true version=v1->v2 reason=T-42
2026-01-01T10:04:00Z change=chg-202 by=admin target=bob perm=INVOICE_READ true->false version=v2->v3 reason=T-99
~~~

Ở phiên bản `v1`, `bob` không có quyền. Sau khi ghi lịch sử `chg-201` và chuyển sang `v2`, lần kiểm tra `req-103` trở thành ALLOW. Khi `chg-202` thu hồi quyền, `req-104` trở lại DENY. **Không thể chứng minh hai lần sửa quyền chỉ bằng bốn access events**, và cũng **không thể biết `bob` có thực sự đọc tài nguyên hay không chỉ từ hai change events**.

Những giới hạn được cố ý giữ rõ trong mô phỏng:

- Hàm `changeGrant` là private và được gọi từ mã có sẵn, **chưa kiểm tra quyền quản trị**. Sản phẩm thật phải kiểm tra operator, approver và scope trước khi commit.
- Danh sách log và quyền chỉ ở RAM; mất khi process dừng, không có transaction, integrity protection hoặc multi-instance coordination.
- `policyVersion` chỉ tăng cho các thay đổi grant mô phỏng; hệ thống thật cần phiên bản đủ phạm vi, bao gồm role definition, policy, ACL và nguồn dữ liệu bên ngoài.
- Hàm `check` ghi **quyết định**, không chứng minh tài liệu hóa đơn đã được trả về HTTP 200 hoặc đã bị đọc thành công.
- Việc seed quyền ban đầu không có event lịch sử trong ví dụ; hệ thống thật cần baseline có thời điểm và nguồn gốc để tái dựng toàn bộ trạng thái.

## 6. Tích hợp thực tế với authorization events của Spring Security

Đối với Spring Security 6.x/7.x, Spring cung cấp `AuthorizationEventPublisher` và `SpringAuthorizationEventPublisher`. Ví dụ bên dưới là **đoạn cấu hình trong ứng dụng Spring Boot** (không phải chương trình JDK độc lập). Nó minh họa cách quan sát **từ chối quyền**:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Configuration
class AuthorizationAuditConfiguration {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new SpringAuthorizationEventPublisher(publisher);
    }
}

@Component
class DeniedAuthorizationObserver {

    @EventListener
    void onDenied(AuthorizationDeniedEvent<?> event) {
        Authentication auth = event.getAuthentication().get();
        String principal = auth == null ? "unknown" : auth.getName();

        // Chỉ là quan sát local; thay bằng audit sink có schema, bảo vệ và độ bền.
        System.out.println("AUTHORIZATION_DENIED principal=" + principal);
    }
}
~~~

Để các method checks có hiệu lực, ứng dụng cần bật `@EnableMethodSecurity` khi sử dụng `@PreAuthorize`/`@PostAuthorize`. Với request authorization, cấu hình `SecurityFilterChain` và `authorizeHttpRequests` theo nhu cầu. **Đừng dùng `event.getObject().toString()` để log bừa bãi**: object chứa chi tiết method/request, tham số hoặc dữ liệu nhạy cảm, và không phải luôn là định danh tài nguyên có thể lưu trữ an toàn.

Ví dụ trên chỉ in tên principal để minh họa event được phát. Một **access audit record production** còn cần request/correlation ID, action và resource được chuẩn hóa, tenant, reason code, phiên bản chính sách; các thông tin ấy phải được bổ sung tại điểm xử lý có đủ context. Tên người dùng không tự đủ để truy ngược một sự cố. Cũng cần kiểm tra đường đi thực tế: mọi DENY ở business service tùy biến không mặc nhiên phát Spring event nếu code tự xử lý mà không dùng `AuthorizationManager` hoặc không công bố sự kiện thích hợp.

### Vì sao không thể chỉ dựa vào AuthorizationDeniedEvent?

- Publisher mặc định chủ yếu ghi **denials**. Những lần ALLOW cũng có thể quan trọng (ví dụ xuất hàng nghìn dữ liệu hoặc xem PII), nhưng phải chọn chiến lược ghi có chủ đích vì có thể rất nhiều events.
- Một request có thể bị từ chối ở nhiều lớp; không mặc nhiên suy ra **mỗi event = một request HTTP**. Dùng decision point và correlation ID để loại trùng theo nghiệp vụ.
- Lỗi authentication (`BadCredentialsException`) thường phát sinh trước authorization. Cần hệ thống authentication audit tương ứng để điều tra nhập sai mật khẩu, khóa tài khoản hoặc token không hợp lệ.
- Quyết định ALLOW không nói hành động đã thành công; muốn biết file đã tải xong, tiền đã chuyển hay bản ghi đã sửa, cần outcome của ứng dụng/business audit.
- `AccessDeniedHandler` chỉ giải quyết phản hồi HTTP theo policy; việc nhìn thấy 403 trong access log của gateway không thay thế trường `policyVersion`, `reasonCode` hay quyền hiệu lực.
- Event từ Spring không phải bằng chứng tự động cho các lần sửa bảng role, ACL hoặc policy trong database. Những thay đổi này cần event nghiệp vụ riêng.

### Spring Boot Actuator AuditEventRepository đặt ở đâu?

Spring Boot Actuator mô tả khả năng audit authentication success/failure và các access-denied exceptions khi audit infrastructure được bật; có thể dùng `AuditEventRepository` hoặc tự publish `AuditApplicationEvent` cho nghiệp vụ riêng. Tuy nhiên, nếu mục tiêu là **lịch sử thay đổi quyền có thể kiểm chứng**, cần thiết kế schema/transaction và kho lưu trữ phù hợp. `InMemoryAuditEventRepository` không tồn tại qua restart và không thích hợp làm bằng chứng lưu giữ lâu dài trong production. Các endpoint Actuator được bảo vệ riêng, không công khai toàn bộ audit cho người dùng thông thường.

## 7. Thiết kế lưu trữ: hai bảng hoặc hai luồng, chung khóa liên kết

Một mô hình SQL tối giản có thể tách ra:

~~~sql
-- DDL minh họa, tùy biến kiểu dữ liệu theo hệ quản trị DB.
CREATE TABLE access_audit (
    event_id        VARCHAR(64) PRIMARY KEY,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    principal_id    VARCHAR(128) NOT NULL,
    tenant_id       VARCHAR(128),
    action          VARCHAR(128) NOT NULL,
    resource_type   VARCHAR(128) NOT NULL,
    resource_id     VARCHAR(128) NOT NULL,
    decision        VARCHAR(8) NOT NULL,
    reason_code     VARCHAR(128),
    policy_version  VARCHAR(128),
    request_id      VARCHAR(128)
);

CREATE TABLE permission_change_audit (
    change_id       VARCHAR(64) PRIMARY KEY,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    effective_at    TIMESTAMP WITH TIME ZONE,
    operator_id     VARCHAR(128) NOT NULL,
    target_type     VARCHAR(64) NOT NULL,
    target_id       VARCHAR(128) NOT NULL,
    change_type     VARCHAR(64) NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    version_before  VARCHAR(128),
    version_after   VARCHAR(128),
    reason          VARCHAR(256),
    ticket_id       VARCHAR(128),
    result          VARCHAR(32) NOT NULL
);
~~~

DDL trên chưa bao gồm index/partition, tenant scoping constraint, encryption, TTL, policy version lineage, cryptographic integrity hay quyền truy cập bảng; đó là **ví dụ cấu trúc**, chưa phải schema production. Tài nguyên nhạy cảm có thể không cho phép lưu resource ID dạng raw; thay bằng ID nội bộ hoặc pseudonym theo threat model. Không biến audit thành một bản sao dữ liệu cá nhân đầy đủ.

**Correlation quan trọng hơn việc “trộn vào một bảng”:**

- Từ access event lấy `principal_id`, `resource_id`, `action`, thời gian, `policy_version` và `request_id`.
- Từ permission change lấy `target_id`, target scope, `version_after` và `effective_at`.
- Từ kho chính sách lấy bản cấu hình/role mapping đã có hiệu lực ở phiên bản đó.
- Kiểm tra ngữ cảnh ảnh hưởng tới quyền: tenant, ownership, attributes, token scopes, policy rollout, cache, thời gian hiệu lực.
- Với sự cố rò rỉ hay leo thang quyền, đối chiếu cả **thời điểm cấp quyền**, **thời điểm sử dụng quyền** và **thời điểm hoàn tất hành động nghiệp vụ**.

Không join chỉ bằng chuỗi `username` có thể đổi tên, và không suy từ thời điểm gần nhau rằng chắc chắn là nguyên nhân. Dùng định danh bất biến, version, causation/correlation ID và bằng chứng transaction/deployment.

## 8. Ghi lịch sử thay đổi quyền đúng thời điểm transaction

Thay đổi quyền là nghiệp vụ đặc quyền cao. Luồng nên là:

1. Operator đăng nhập, hệ thống kiểm tra quyền **quản trị phạm vi đích**; nếu áp dụng approval, xác thực cả quyết định phê duyệt.
2. Đọc trạng thái trước thay đổi cùng version/ETag hoặc khóa phù hợp; tính toán diff rõ ràng.
3. Kiểm tra điều kiện nghiệp vụ: role nào có thể được cấp, tenant nào, thời hạn, nguyên tắc hai người kiểm soát nếu cần.
4. Trong cùng transaction với thay đổi quyền, lưu **permission-change audit** hoặc **transactional outbox** chứa đầy đủ before/after, version, operator, reason. Commit thành công mới là `APPLIED`.
5. Nếu dùng outbox, consumer chuyển event sang kho audit bất biến và xử lý duplicate bằng `changeId`; retry không được tự tạo thêm lần “cấp quyền” giả.
6. Sau commit, xử lý invalidation session/token/cache/policy; ghi hiệu lực thực tế hoặc activation/version để giải thích chênh lệch.
7. Tùy yêu cầu, ghi riêng **attempt** bị từ chối, validation failure hoặc administrative request thất bại với `result=REJECTED`, không nhập nhằng với event thay đổi đã thành công.

**Rủi ro dual write:** nếu commit database trước rồi mới `publishEvent` qua broker và tiến trình chết ở giữa, lịch sử có thể thiếu thay đổi quan trọng. Transactional outbox/CDC hoặc audit insert trong cùng database transaction là những cách thường dùng để thu hẹp khoảng trống. Một `@EventListener` chạy trong memory không tương đương lưu bền vững hoặc bảo đảm “exactly once”.

**Quyền đang có không đồng nghĩa với quyền đã có ở quá khứ.** Bảng `user_role` hiện tại chỉ trả lời “quyền bây giờ”; để giải thích một lần ALLOW hôm qua cần snapshot/diff/version và time validity. Nếu lưu `before`/`after` ở dạng JSON, phải có schema version, cơ chế redaction và khả năng đọc lại sau khi format policy đổi.

## 9. Những bảo vệ bắt buộc của audit

**Tính toàn vẹn và chống sửa lịch sử**

- Ưu tiên append-only; quyền sửa/xóa audit tách khỏi quyền cấp phát role. Quản trị viên quyền trong ứng dụng không mặc nhiên có quyền xóa dấu vết của chính mình.
- Kiểm soát quyền truy cập theo nhiệm vụ: vận hành thấy chỉ số tổng hợp; security auditor được xem event cần điều tra; quyền export audit có thể cần phê duyệt.
- Có thể thêm log bất biến/WORM, hash chaining hoặc chữ ký, storage versioning và external timestamp tùy yêu cầu tuân thủ; đừng coi một bảng append-only không có bảo vệ là bất khả giả mạo.
- Backup, retention, legal hold, reconciliation giữa source-of-truth và audit sink phải được định nghĩa rõ. Sự cố audit sink cần alert; với thao tác cấp quyền nguy hiểm phải có chính sách fail-closed hoặc outbox bền vững đã kiểm chứng.

**Tính riêng tư và giảm dữ liệu**

- Không ghi password, access/refresh token, API key, cookie, toàn bộ JWT, request body thô hoặc PII ngoài mục đích. Cẩn thận khi log URL chứa token, query string hoặc object dump.
- Dùng mã lý do cố định `MISSING_ROLE`, `OUT_OF_SCOPE` hoặc `POLICY_CONDITION_FALSE` thay vì exception message tùy ý có thể tiết lộ internals.
- Che/pseudonym hóa ID khi cần, mã hóa tại rest và transport, giới hạn retention và đảm bảo xóa/ẩn theo quy định áp dụng. Audit cũng là dữ liệu cần được bảo vệ.
- Dùng thời gian UTC với định dạng rõ, đồng bộ đồng hồ, phân biệt `occurredAt`, `ingestedAt` và `effectiveAt`. Độ trễ queue không nên khiến kết luận sai thứ tự.
- Với nhiều tenant, lưu tenant/scope và kiểm tra chéo tenant khi truy vấn audit; không để người xem audit của tenant này nhìn thấy tenant khác.

**Độ đầy đủ, độ tin cậy và chi phí**

- Chọn mức audit ALLOW theo rủi ro: sự kiện DENY, hành động admin, quyền truy cập dữ liệu nhạy cảm và thao tác có tác động cao thường đáng giữ; ghi mọi permitAll cho tài nguyên tĩnh có thể tạo lưu lượng vô ích.
- Với decision rất lớn, dùng asynchronous sink có bounded queue, cơ chế retry, backpressure và cảnh báo dropped events. Không âm thầm bỏ event thuộc loại bắt buộc.
- Gắn version của policy/entitlement thật tại điểm ra quyết định, không cập nhật bản ghi cũ theo phiên bản hiện tại.
- Có thể cần hai event cùng request: **decision** và **business outcome**; tránh tuyên bố đã hoàn tất thao tác chỉ vì quyền cho phép.
- Với hệ thống phân tán, chuẩn hóa eventId, traceId và serviceId; xác định rõ nguồn chân lý để tránh đếm trùng khi gateway và service đều log cùng request.

## 10. Phân tích sự cố qua hai chiều audit

**Tình huống A: một user từng DENY, sau đó ALLOW với cùng tài nguyên.**

Đầu tiên lấy access events theo principal/tài nguyên/thời gian. So sánh policy version và context, rồi truy vấn permission history theo subject, role, role-permission mapping, policy và ACL liên quan. Nếu có grant mới, xác minh operator, approval, ticket, effectiveAt, trạng thái cache và thời điểm quyền được sử dụng. Nếu không có grant, xét owner/ABAC và deployment/feature-flag/policy condition.

**Tình huống B: một quản trị viên bị nghi cấp quyền trái phép.**

Lấy permission-change audit theo operator và target; tìm GRANT/REVOKE/ROLLBACK, trước–sau, approval và bản policy thay đổi. Sau đó tra access audit của target trong khoảng quyền có hiệu lực để trả lời quyền ấy có được dùng, dùng trên đối tượng nào, DENY/ALLOW ra sao. Nếu cần chứng minh dữ liệu thật đã bị xuất, phải liên kết business outcome/download log, không kết luận từ ALLOW một mình.

**Tình huống C: hệ thống hiện 403 hàng loạt sau rollout.**

Tập hợp access DENY theo resource/action/service/policy version trước–sau deploy. Tra permission changes và policy deployment history. Đừng mặc định một đợt 403 là do revoke quyền: có thể do cấu hình security matcher, thiếu authority trong token, ACL lookup lỗi, CSRF hoặc service policy không khả dụng. Kiểm tra authentication và infrastructure logs khi cần.

**Tình huống D: khẳng định “chưa ai sử dụng quyền mới”.**

History chỉ xác nhận quyền đã được cấp; access audit phải bao phủ đúng **mọi đường sử dụng quyền** (UI/API/export/batch/message consumer). Nếu granted events đang bị tắt hoặc lấy mẫu, không được kết luận “không dùng quyền” từ việc không thấy event. Cần đánh giá độ phủ telemetry và bảo đảm retention trước khi đưa ra kết luận kiểm toán.

## 11. Kịch bản kiểm thử cần có

| Kịch bản | Access audit phải cho thấy | Permission history phải cho thấy |
| --- | --- | --- |
| User đọc tài nguyên được cấp quyền | ALLOW với đúng resource, action, policy version | Không phát sinh thay đổi quyền chỉ vì có đọc |
| User đọc tài nguyên bị chặn | DENY, principal và reason code an toàn | Không phát sinh grant/revoke |
| Admin cấp quyền thành công | Bản thân hành động quản trị có decision/outcome phù hợp | GRANT hoặc policy diff, before/after, operator, version, approval |
| Admin không đủ quyền cố cấp quyền | DENY hành động admin | Không có event `APPLIED`; có thể có `REJECTED ATTEMPT` riêng |
| Rollback/revoke | Các lần access sau hiệu lực phản ánh version đúng | REVOKE/ROLLBACK với version cũ/mới và lý do |
| Commit DB thất bại | Không tuyên bố thao tác quản trị thành công | Không ghi event `APPLIED` giả |
| Broker tạm ngừng | Audit bắt buộc không bị lặng lẽ mất | Outbox/retry đảm bảo event được gửi lại mà không nhân bản |
| Token cũ chứa claims trước revoke | Quyết định ghi đúng version/context thật | History vẫn cho thấy revoke đã commit và effectiveAt |
| Nhiều request trùng requestId do retry | Đếm theo eventId/decision point đúng hợp đồng | Thay đổi quyền có changeId để idempotent |
| Admin sửa role-definition thay vì user-role | Access sau thay đổi dùng policy/role version tương ứng | Diff ở role definition, không bịa là user vừa được gán role |

Các assertion quan trọng: sự kiện **không lộ bí mật**, timestamp không bị viết lại, `before` không bị thay bằng trạng thái hiện tại, event ALLOW không bị nhầm thành business success, mọi change đã commit có audit tương ứng, không có duplicate logic khi replay.

## 12. Những lỗi phổ biến và cách tránh

1. **Dùng lịch sử đăng nhập làm access audit.** `AuthenticationSuccessEvent` chứng minh một phương thức xác thực thành công, không chứng minh quyền trên `invoice:42` đã được cấp.
2. **Dùng 403 trong access log làm toàn bộ bằng chứng phân quyền.** 403 không chứa chính sách, role snapshot hay lý do có cấu trúc; một request có thể bị chặn ở nhiều tầng.
3. **Dùng quyền hiện tại để giải thích quyết định cũ.** ACL/role có thể đã thay đổi; cần effective timestamp, policy version và historical snapshot.
4. **Chỉ ghi thay đổi quyền khi UI admin gọi nút “Lưu”.** Import dữ liệu, batch script, migration, IAM sync, external policy rollout và auto-expire cũng có thể thay đổi quyền.
5. **Ghi permission-change event trước khi commit.** Nếu transaction rollback, history sẽ mô tả sai. Hãy liên kết audit/outbox với transaction và tách attempt khỏi applied.
6. **Quên operator hoặc approver.** Chỉ có target user không thể trả lời ai đã cấp đặc quyền và vì sao.
7. **Log whole Authentication hoặc toàn bộ HTTP request.** Có thể chứa credential, PII, claims, session ID; chỉ lấy trường cần thiết và áp dụng cơ chế redaction.
8. **Bật mọi ALLOW event không kiểm soát.** Tạo log flood, tăng chi phí và rủi ro mất sự kiện quan trọng; định nghĩa mức audit dựa trên dữ liệu nhạy cảm.
9. **Không phân biệt DENY với business failure.** Access ALLOW nhưng controller 500 không phải một lần DENY; cần outcome riêng.
10. **Coi @EventListener hoặc InMemoryAuditEventRepository là audit bất biến.** Cần durable storage, retention, backpressure, authorization và kiểm tra toàn vẹn.
11. **Audit chỉ ở API gateway.** Gateway không biết đủ quyền ở mức đối tượng và method; cần event ở decision point thực sự.
12. **Không gắn phiên bản cho thay đổi role definition.** Biết user có role `REPORT_VIEWER` nhưng không biết role ấy cho phép gì vào hôm sự cố.
13. **Dùng audit làm hệ thống cấp quyền hiện tại.** Policy engine nên dựa vào nguồn quyền hiện hành được quản trị; audit dùng để chứng minh lịch sử và tái dựng, có thể hỗ trợ projection nhưng không thay transaction source of truth.

## 13. Checklist nắm vững

- [ ] Giải thích được: **Access audit = lần sử dụng/kiểm tra quyền**; **permission history = thay đổi trạng thái cấp quyền/quy tắc**.
- [ ] Phân biệt authentication event, authorization decision, HTTP response và business outcome.
- [ ] Biết Spring Security có `AuthorizationDeniedEvent`, granted event không bật mặc định, và điều gì phải tự thiết kế để ghi ALLOW nhạy cảm.
- [ ] Thiết kế được trường dữ liệu tối thiểu cho từng luồng, đặc biệt operator vs target và before/after.
- [ ] Tái dựng một lần DENY/ALLOW lịch sử bằng principal, resource, context, time và policy version thật.
- [ ] Ghi permission changes gắn với commit/outbox; retry idempotent; không nhập nhằng failed attempt với applied change.
- [ ] Bảo vệ log khỏi sửa/xóa trái phép và không lưu credentials/PII thừa.
- [ ] Viết test chứng minh thay đổi quyền có audit, truy cập có decision và hai sự kiện không bị trộn.
- [ ] Không kết luận “quyền chưa được dùng” nếu thiếu coverage của ALLOW events.

### Tham khảo chính thức

- Spring Security — Authorization Events: https://docs.spring.io/spring-security/reference/servlet/authorization/events.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Boot Actuator — Auditing: https://docs.spring.io/spring-boot/reference/actuator/auditing.html
