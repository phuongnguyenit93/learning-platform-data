# Thu thập audit, kiểm thử hồi quy và tổng hợp bằng chứng cho từng quyết định quyền

## 1. Mục tiêu: trả lời được “ai được phép làm gì, vì sao, bằng chứng ở đâu?”

Trong Spring Security, HTTP status 200/401/403 chỉ là một góc nhìn về phân quyền. Khi một yêu cầu bị chặn hoặc được chấp nhận, chúng ta cần xác minh đồng thời **ai yêu cầu**, **hành động nào trên tài nguyên nào**, **chính sách và ngữ cảnh nào đã được xét**, **kết quả và lý do**, **quyết định có được thi hành**, và **bằng chứng đủ để tái hiện**. Một request có thể trải qua nhiều kiểm tra: HTTP `AuthorizationFilter`, method `@PreAuthorize`, ACL tài nguyên và ràng buộc nghiệp vụ trước khi commit.

Ví dụ: Alice thuộc tenant `acme`, có `ROLE_REVIEWER`, yêu cầu duyệt tài liệu `D-42` thuộc tenant `beta`. Bằng chứng tốt chứng minh `document.approve` phiên bản `17` đã trả **DENY/TENANT_MISMATCH**, method không ghi tài liệu, response là 403 theo cơ chế của API và bài regression case cross-tenant đã pass. Chỉ log “request returned 403” không chỉ ra policy nào từ chối.

Sau bài học, bạn có thể:
- Thiết kế audit event có cấu trúc và correlation để nối HTTP, method, policy, giao dịch và test.
- Thu thập đúng tại điểm kiểm tra của Spring Security; hiểu giới hạn của `AuthorizationEventPublisher` và sự khác nhau giữa `PERMIT, DENY, ABSTAIN, ERROR`.
- Lập golden permission matrix độc lập với implementation cũ, kiểm thử kết quả, side effect và bảo vệ qua proxy/filter chain.
- Đóng gói `scenarioId → decisionId → traceId → policyVersion → artifact` thành hồ sơ có thể review.
- Đảm bảo audit bảo mật, có retention, failure policy, hiệu năng tốt và đo được độ đầy đủ.

**Phạm vi:** Spring Security Servlet/MVC, chủ yếu Spring Security 6.4–6.5 và Java 17+. WebFlux dùng `ServerHttpSecurity`/`SecurityWebFilterChain` và cơ chế observability tương ứng; không sao chép nguyên cấu hình Servlet sang Reactive.

## 2. Phân biệt bốn lớp kết quả

| Lớp | Dữ kiện cần quan sát | Điều không thể tự suy ra |
| --- | --- | --- |
| Authentication | Authentication type, principal reference, trạng thái, issuer | Một token hợp lệ không chứng minh có quyền trên tài nguyên |
| Authorization decision | Policy/rule, resource/action, `PERMIT / DENY / ABSTAIN / ERROR`, reason | Một quyết định grant chưa bảo đảm cả request cuối cùng được phép |
| Enforcement và business outcome | `PROCEED / BLOCK`, method chạy chưa, transaction commit/rollback | Một method được chạy chưa chắc DB đã commit |
| HTTP response | Status, entry point, exception mapping, headers | 401/403 có thể phát sinh từ cơ chế xác thực, CSRF, firewall hoặc chính sách khác |

**DENY không đồng nghĩa cứng với HTTP 403.** Với anonymous, Spring Security có thể trả 401 để yêu cầu xác thực; với người dùng đã authenticated nhưng thiếu quyền thường trả 403. Một POST thiếu CSRF có thể bị chặn trước khi đến policy dự kiến. Vì thế kiểm thử phải quan sát decision + enforcement + response + side effect, không chỉ HTTP status.

### 2.1. Một request có thể có nhiều decision

~~~text
HTTP request [traceId=t-840]
  │
  ├─ AuthorizationFilter    [decisionId=d-1, PERMIT, http:authenticated]
  │
  ├─ method @PreAuthorize   [decisionId=d-2, DENY, TENANT_MISMATCH]
  │
  ├─ business method        [NOT_EXECUTED]
  │
  └─ HTTP response          [403]
       └─ audit: trace t-840 liên kết decision d-1, d-2 và response
~~~

`traceId` nhóm những công đoạn của cùng request; `decisionId` phải phân biệt **mỗi lần đánh giá**; `scenarioId` liên kết dữ liệu trong regression test. Không dùng `traceId` làm decision ID vì nhiều advisor có thể cùng đánh giá. Không gộp các deny của HTTP và method thành một event không xác định nguồn.

### 2.2. Phân biệt null, lỗi và quyết định hiệu lực

`AuthorizationManager` có thể cho phép, từ chối, abstain (một số API trả `null` để không quyết định), hoặc ném exception vì lỗi policy. Tùy manager/composition, một abstain có thể được manager khác xử lý; nó **không mặc nhiên là DENY hay PERMIT**. Cần ghi hai trường:

- `decision`: kết quả thực của thành phần đang xét (PERMIT/DENY/ABSTAIN/ERROR).
- `enforcement`: kết quả cuối khi áp dụng toàn bộ policy và fallback (PROCEED/BLOCK/UNAVAILABLE).

Một ứng dụng nhạy cảm thường thiết kế fallback “không có quyết định cho phép rõ ràng thì chặn”, nhưng phải thể hiện trong code và test; không giả định đây là mặc định mọi phiên bản Spring Security.

## 3. Schema audit có thể đối chiếu và bảo vệ dữ liệu

| Trường | Mục đích | Lưu ý triển khai |
| --- | --- | --- |
| `schemaVersion` | Quản lý evolution của event | Không sửa ý nghĩa trường im lặng |
| `eventId` | Định danh bản ghi audit | Mỗi lần ghi có ID riêng; retry có chiến lược dedup |
| `decisionId` | Định danh chính sách được xét | Duy nhất mỗi lần evaluation |
| `traceId`, `spanId` | Liên kết với trace/HTTP | Propagate qua async khi cần |
| `occurredAt`, `durationMs` | Timeline và hiệu năng | UTC; clock đồng bộ; không coi thời gian là revision |
| `principalRef`, `authType` | Tài khoản/request được xác thực | Ref nội bộ/pseudonym; không log token/password |
| `tenantRef`, `resourceType`, `resourceRef` | Kiểm tra ranh giới quyền | Chuẩn hóa tenant/resource, lưu tối thiểu |
| `action`, `enforcementPoint` | Hoạt động và điểm kiểm tra | Ví dụ `document.approve`, `METHOD_PRE_AUTHORIZE` |
| `policyId`, `policyVersion`, `ruleId` | Policy được áp dụng | Gắn commit/config version thực, không ghi “latest” |
| `decision`, `reasonCode` | Kết luận có cấu trúc | Reason code ổn định, không chứa PII |
| `enforcement`, `businessOutcome` | Quyết định có hiệu lực không? | `BLOCK/PROCEED` và `COMMITTED/ROLLED_BACK/NOT_EXECUTED` |
| `contextVersion`, `grantVersion` | Dữ liệu phục vụ kiểm tra | Phiên bản ACL, membership snapshot, cache |
| `scenarioId`, `testRunId` | Đối chiếu test artifact | Chỉ thêm khi thực sự có test context |

Ví dụ bản ghi audit **giả lập, đã tối giản dữ liệu nhận dạng**:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-840-2",
  "decisionId": "decision-840-2",
  "traceId": "trace-840",
  "occurredAt": "2026-10-01T09:15:30Z",
  "principalRef": "actor-17",
  "tenantRef": "acme",
  "resourceType": "document",
  "resourceRef": "doc-42",
  "action": "document.approve",
  "policyId": "document-approval",
  "policyVersion": "17",
  "ruleId": "TENANT_BOUNDARY",
  "enforcementPoint": "METHOD_PRE_AUTHORIZE",
  "decision": "DENY",
  "reasonCode": "TENANT_MISMATCH",
  "enforcement": "BLOCK",
  "businessOutcome": "NOT_EXECUTED"
}
~~~

Schema này là **hợp đồng do ứng dụng định nghĩa**, không phải output có sẵn của `AuthorizationDeniedEvent`. Không serialize nguyên `Authentication`, `MethodInvocation`, `HttpServletRequest` hoặc `toString()` của object đang bảo vệ: chúng có thể chứa password/token, query string, arguments và dữ liệu nhạy cảm.

**Reason code** như `AUTH_REQUIRED`, `ROLE_MISSING`, `TENANT_MISMATCH`, `NOT_OWNER`, `POLICY_UNAVAILABLE` phải ổn định để test và dashboard dựa vào, không so chuỗi thông báo tiếng người. Đừng đưa userId/resourceId làm nhãn metrics có cardinality cao; lưu ở kho audit được phân quyền.

## 4. Thu thập ở những điểm nào trong Spring Security?

### 4.1. Authorization events của framework

Spring Security có `AuthorizationEventPublisher` và hai event `AuthorizationDeniedEvent`, `AuthorizationGrantedEvent`. Với Spring Security 6.5, `SpringAuthorizationEventPublisher` dựa vào Spring `ApplicationEventPublisher`; **mặc định chỉ phát sự kiện deny**, còn grant events cần cách phát có chủ đích vì lưu lượng rất lớn. Các event này chỉ có ở những đường authorization đã tích hợp publisher, không tự bảo đảm đầy đủ mọi lời gọi chính sách hoặc nhánh lỗi.

Trong `@Configuration` đã bật bảo mật, có thể đăng ký:

~~~java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher events) {
    return new SpringAuthorizationEventPublisher(events);
}
~~~

Những import liên quan: `org.springframework.context.ApplicationEventPublisher`, `org.springframework.security.authorization.AuthorizationEventPublisher`, `org.springframework.security.authorization.SpringAuthorizationEventPublisher`, `org.springframework.context.annotation.Bean`.

Listener là **đoạn tích hợp**, cần `AuditSink` do dự án hiện thực và cung cấp correlation từ tầng nghiệp vụ:

~~~java
@Component
class AuthorizationDeniedListener {

    private final AuditSink auditSink;

    AuthorizationDeniedListener(AuditSink auditSink) {
        this.auditSink = auditSink;
    }

    @EventListener
    void onDenied(AuthorizationDeniedEvent<?> event) {
        if (!event.getAuthorizationResult().isGranted()) {
            Object securedObject = event.getObject();
            String targetKind = securedObject == null
                    ? "UNKNOWN"
                    : securedObject.getClass().getSimpleName();

            // Không ghi toString() của request / MethodInvocation.
            auditSink.offerDenied("SPRING_AUTHZ", targetKind);
        }
    }
}
~~~

Import `@Component`, `@EventListener` và `AuthorizationDeniedEvent` từ Spring. Listener chưa tạo đầy đủ audit schema: `AuditSink` cần lấy correlation IDs, policy version và reference tài nguyên từ request/policy context đáng tin cậy. Không nên thực hiện network call chặn lâu trong listener. API `getAuthorizationResult()` thuộc 6.4+; đối với 6.3 và 7.x, kiểm tra Javadoc theo version.

**Bẫy về phạm vi:** `AuthorizationDeniedEvent` không tự xuất hiện khi request bị loại khỏi mọi `SecurityFilterChain`, khi service được gọi không qua AOP proxy, hoặc khi một custom policy tự ném exception trước khi tạo event. Nếu audit phải bao phủ những trường hợp này, cần điểm instrument khác cùng coverage test.

### 4.2. Domain-policy audit để ghi PERMIT, ABSTAIN, ERROR

Với quyền trên tài nguyên (`document.approve`, `invoice.pay`), nên instrument ở thành phần đánh giá policy, nơi có thể biết action, resource, tenant, rule ID và version. Contract gợi ý:

~~~text
PolicyInput(identity, action, resource, contextVersion)
      │
      ▼
evaluate() -> PolicyEvaluation(decision, reasonCode, policyVersion)
      │                    └── exception -> ERROR
      ▼
record sanitized audit(eventId, decisionId, traceId, ...)
      │
      ▼
enforce final policy (including abstain fallback and error handling)
      │
      ▼
record business outcome AFTER commit/rollback
~~~

Phải **đánh giá policy đúng một lần** cho một lần thử, rồi ghi cùng kết quả; đừng gọi policy lần hai để “audit” vì dữ liệu ACL có thể đổi hoặc đánh giá gây tác dụng phụ. Với exception, ghi reason code tổng quát và cho exception đi qua xử lý lỗi theo chính sách; không biến lỗi thành PERMIT. Nếu audit downstream lỗi, chiến lược fallback/đảm bảo lưu trữ phải do nhu cầu bảo mật quyết định, không phát sinh ngẫu nhiên từ lỗi listener.

### 4.3. HTTP, method và DB cùng một trace nhưng khác sự kiện

- HTTP `AuthorizationFilter` đánh giá rule của `authorizeHttpRequests`. Một HTTP permit chưa chứng minh business method được phép.
- `@PreAuthorize`/`@PostAuthorize` dùng AOP method security. Với `@PostAuthorize`, body có thể đã chạy trước khi bị từ chối; phải kiểm tra side effect riêng.
- Domain ACL có thể dựa trên ownership, tenant, resource state, DB grant version; ghi reference vừa đủ để tái lập.
- Kết quả DB `COMMITTED` cần được quan sát sau commit thực, bằng transaction hooks/outbox nếu đòi hỏi bằng chứng đáng tin. Một event PERMIT trước transaction không có nghĩa giao dịch thành công.

## 5. Golden permission matrix: chuẩn kiểm thử độc lập với code cũ

Ma trận phải do chủ sở hữu nghiệp vụ và bảo mật xác nhận, có `scenarioId`, expected decision, dữ liệu identity/tenant/resource/action và version fixture. Đừng lấy output policy cũ làm golden vì có thể hợp thức hóa lỗ hổng.

Bảng giả định của hệ thống tài liệu:

| ID | Principal | Action | Ngữ cảnh tài nguyên | Expected decision | Enforced | Business call |
| --- | --- | --- | --- | --- | --- | --- |
| `A01` | Anonymous | PUBLIC_READ | Public document | PERMIT | PROCEED | 1 |
| `A02` | Alice/STAFF | PRIVATE_READ | Owner, same tenant | PERMIT | PROCEED | 1 |
| `A03` | Anonymous | PRIVATE_READ | Private document | DENY | BLOCK | 0 |
| `A04` | Alice/STAFF | PRIVATE_READ | Cross-tenant dù owner=true | DENY | BLOCK | 0 |
| `A05` | Alice/STAFF | PRIVATE_READ | Không phải owner | DENY | BLOCK | 0 |
| `A06` | Alice/REVIEWER | APPROVE | Same tenant, DRAFT | PERMIT | PROCEED | 1 |
| `A07` | Alice/STAFF | APPROVE | Same tenant, DRAFT | DENY | BLOCK | 0 |
| `A08` | Alice/REVIEWER | APPROVE | Same tenant, PUBLISHED | DENY | BLOCK | 0 |
| `A09` | Alice | UNSUPPORTED | Không rule phù hợp | ABSTAIN | BLOCK theo fallback fixture | 0 |
| `A10` | Alice/REVIEWER | APPROVE | Policy service unavailable | ERROR | BLOCK theo failure policy | 0 |

`A09`/`A10` kiểm tra sự khác biệt giữa **kết quả policy** và **hành vi thi hành**. Fixture có fallback mặc định block cho ABSTAIN/ERROR; điều này là chính sách minh họa có chủ đích, không khẳng định mọi Spring Security interceptor xử lý `null` theo cách ấy.

Một test phải kiểm tra **expected vs actual policy**, **enforced outcome**, **side effect**, và **audit correlation/count**. Đối với permission matrix nhiều lớp, không ép một HTTP request có đúng một audit: một request có thể đi qua nhiều policy.

## 6. Java 17 chạy độc lập: kiểm tra 10 quyết định và 10 audit records

Ví dụ này chỉ dùng JDK 17. Không tạo HTTP server hoặc DB; nó mô phỏng chính sách quyền tài liệu, ghi audit in-memory, đối chiếu golden và đếm business calls. Dữ liệu cố định giúp stdout chính xác.

Tạo file **`AuthorizationAuditEvidenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class AuthorizationAuditEvidenceDemo {

    enum Action { PUBLIC_READ, PRIVATE_READ, APPROVE, UNSUPPORTED }
    enum Decision { PERMIT, DENY, ABSTAIN, ERROR }

    record Scenario(
            String id, Action action, boolean authenticated,
            String actorTenant, String resourceTenant,
            boolean owner, boolean reviewer, boolean draft,
            boolean policyAvailable, Decision expected) {}

    record PolicyResult(Decision decision, String reasonCode) {}

    record AuditEvent(
            String eventId, String decisionId, String traceId,
            String scenarioId, String policyVersion,
            Decision decision, String enforcement, String reasonCode) {}

    static PolicyResult evaluate(Scenario s) {
        if (!s.policyAvailable()) {
            return new PolicyResult(Decision.ERROR, "POLICY_UNAVAILABLE");
        }
        if (s.action() == Action.UNSUPPORTED) {
            return new PolicyResult(Decision.ABSTAIN, "NO_MATCHING_RULE");
        }
        if (s.action() == Action.PUBLIC_READ) {
            return new PolicyResult(Decision.PERMIT, "PUBLIC_RESOURCE");
        }
        if (!s.authenticated()) {
            return new PolicyResult(Decision.DENY, "AUTH_REQUIRED");
        }
        if (!Objects.equals(s.actorTenant(), s.resourceTenant())) {
            return new PolicyResult(Decision.DENY, "TENANT_MISMATCH");
        }
        return switch (s.action()) {
            case PRIVATE_READ -> s.owner()
                    ? new PolicyResult(Decision.PERMIT, "OWNER_MATCH")
                    : new PolicyResult(Decision.DENY, "NOT_OWNER");
            case APPROVE -> !s.reviewer()
                    ? new PolicyResult(Decision.DENY, "REVIEWER_REQUIRED")
                    : !s.draft()
                        ? new PolicyResult(Decision.DENY, "NOT_DRAFT")
                        : new PolicyResult(Decision.PERMIT, "REVIEWER_DRAFT");
            case PUBLIC_READ, UNSUPPORTED ->
                    throw new IllegalStateException("Handled above");
        };
    }

    public static void main(String[] args) {
        List<Scenario> cases = List.of(
            new Scenario("A01", Action.PUBLIC_READ, false, null, "acme",
                    false, false, false, true, Decision.PERMIT),
            new Scenario("A02", Action.PRIVATE_READ, true, "acme", "acme",
                    true, false, false, true, Decision.PERMIT),
            new Scenario("A03", Action.PRIVATE_READ, false, null, "acme",
                    false, false, false, true, Decision.DENY),
            new Scenario("A04", Action.PRIVATE_READ, true, "acme", "beta",
                    true, false, false, true, Decision.DENY),
            new Scenario("A05", Action.PRIVATE_READ, true, "acme", "acme",
                    false, false, false, true, Decision.DENY),
            new Scenario("A06", Action.APPROVE, true, "acme", "acme",
                    false, true, true, true, Decision.PERMIT),
            new Scenario("A07", Action.APPROVE, true, "acme", "acme",
                    false, false, true, true, Decision.DENY),
            new Scenario("A08", Action.APPROVE, true, "acme", "acme",
                    false, true, false, true, Decision.DENY),
            new Scenario("A09", Action.UNSUPPORTED, true, "acme", "acme",
                    false, false, false, true, Decision.ABSTAIN),
            new Scenario("A10", Action.APPROVE, true, "acme", "acme",
                    false, true, true, false, Decision.ERROR)
        );

        List<AuditEvent> audit = new ArrayList<>();
        Set<String> seenDecisions = new HashSet<>();
        int businessCalls = 0;
        int passed = 0;
        String version = "doc-authz-v17";

        for (Scenario s : cases) {
            PolicyResult result = evaluate(s);
            boolean proceed = result.decision() == Decision.PERMIT;

            AuditEvent event = new AuditEvent(
                    "evt-" + s.id(),
                    "decision-" + s.id(),
                    "trace-" + s.id(),
                    s.id(),
                    version,
                    result.decision(),
                    proceed ? "PROCEED" : "BLOCK",
                    result.reasonCode());
            audit.add(event);

            if (!seenDecisions.add(event.decisionId())) {
                throw new AssertionError("Duplicate decisionId");
            }
            if (!event.traceId().equals("trace-" + s.id())
                    || !event.scenarioId().equals(s.id())
                    || !event.policyVersion().equals(version)) {
                throw new AssertionError("Missing correlation");
            }
            if (result.decision() != s.expected()
                    || proceed != (s.expected() == Decision.PERMIT)) {
                throw new AssertionError("Regression failed: " + s.id());
            }

            // Mô phỏng lời gọi nghiệp vụ được bảo vệ.
            if (proceed) {
                businessCalls++;
            }
            passed++;
            System.out.printf("%s | %s | %s | %s%n",
                    s.id(), event.decision(),
                    event.enforcement(), event.reasonCode());
        }

        if (audit.size() != cases.size() || businessCalls != 3) {
            throw new AssertionError("Incomplete audit or wrong side effects");
        }
        System.out.println("Golden regression: " + passed + "/10");
        System.out.println("Audit events: " + audit.size());
        System.out.println("Business calls: " + businessCalls);
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 AuthorizationAuditEvidenceDemo.java
java AuthorizationAuditEvidenceDemo
~~~

Stdout dự kiến **chính xác**:

~~~text
A01 | PERMIT | PROCEED | PUBLIC_RESOURCE
A02 | PERMIT | PROCEED | OWNER_MATCH
A03 | DENY | BLOCK | AUTH_REQUIRED
A04 | DENY | BLOCK | TENANT_MISMATCH
A05 | DENY | BLOCK | NOT_OWNER
A06 | PERMIT | PROCEED | REVIEWER_DRAFT
A07 | DENY | BLOCK | REVIEWER_REQUIRED
A08 | DENY | BLOCK | NOT_DRAFT
A09 | ABSTAIN | BLOCK | NO_MATCHING_RULE
A10 | ERROR | BLOCK | POLICY_UNAVAILABLE
Golden regression: 10/10
Audit events: 10
Business calls: 3
~~~

**Diễn giải:** A04 deny dù owner flag true nhờ kiểm tra tenant. A06 permit khi reviewer và tài liệu còn draft. A09 ghi ABSTAIN nhưng fallback của **demo** chặn, A10 ghi ERROR riêng. Có 10 decision audit và ba business calls giả lập. Demo không bảo đảm audit storage hay transaction của hệ thống thực; nếu policy thật ném exception, adapter phải ghi ERROR và propagate/fail-safe theo chính sách. `eventId` demo cố định theo case để stdout dễ kiểm chứng; production cần ID duy nhất mỗi lần phát, kể cả retry/attempt khác nhau và cơ chế dedup phù hợp.

## 7. Kiểm thử hồi quy end-to-end với Spring Security

### 7.1. Cấu hình test

Trong một Spring Boot 3.5.x project đã có Spring plugin/BOM, dùng dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đối với service, bật `@EnableMethodSecurity` và gọi qua **Spring-managed proxy**; gọi trực tiếp `new ServiceImpl()` hoặc `this.securedMethod()` có thể bỏ qua AOP interceptor. Đối với endpoint HTTP, dùng `MockMvc` và `spring-security-test` để bảo đảm request đi qua security filter chain.

**Một đoạn test minh họa** — cần `@SpringBootTest`, `@AutoConfigureMockMvc`, controller, DB fixture, `MockMvc` và static imports:

~~~java
// Tài liệu D-42 thuộc tenant beta; principal này thuộc tenant acme.
mockMvc.perform(post("/api/documents/D-42/approve")
        .with(user("reviewer").roles("REVIEWER"))
        .with(csrf()))
    .andExpect(status().isForbidden());

// Cùng test cần xác minh:
// - document D-42 không bị mutate và message count = 0;
// - audit có DENY/TENANT_MISMATCH với policyVersion đúng;
// - decisionId/traceId gắn với request và test case;
// - không có đường gọi bypass method security.
~~~

`with(user())` chỉ tạo principal/authorities test, **không tự cấp tenant**. Tenant phải được liên kết từ nguồn đáng tin và fixture thực tế. Với POST dùng browser/session, CSRF token cần chính xác; với API bearer-only, cấu hình CSRF theo threat model thay vì tắt đại trà để test xanh.

### 7.2. Những tầng test cần có

| Tầng | Điều kiểm tra |
| --- | --- |
| Unit policy | `PERMIT/DENY/ABSTAIN/ERROR`, reason, tenant, ownership, role, state |
| Component Spring | `AuthorizationManager`, publisher/listener, `@PreAuthorize` qua proxy, exception mapping |
| HTTP integration | `SecurityFilterChain`, authentication, status, CSRF, matcher/order, request methods |
| Business integration | DB state, transaction, message/external side effect, commit/rollback |
| Evidence contract | Schema/correlation, audit count, policy version, artifact link/hash |
| Performance/failure | Queue đầy, audit sink lỗi, retry, dedupe, latency và backpressure |

Không dùng HTTP status làm bằng chứng duy nhất cho phân quyền. Một lỗi CSRF có thể tạo 403 trước rule dự kiến; một request không khớp chain có thể trả 404 do MVC mà không hề được bảo vệ. Test cần xác định đúng điểm chính sách đã thực thi.

### 7.3. Ma trận bổ sung quan trọng

- Anonymous/public/private, người dùng bị khóa, thiếu authority và role prefix khác nhau (`ROLE_ADMIN` so với `ADMIN`).
- Cross-tenant ngay cả khi owner flag hoặc role đúng; tài nguyên chuyển tenant/đổi owner.
- Permission cache cũ, ACL bị thu hồi, policy/version đổi giữa check và commit.
- `@PostAuthorize` từ chối sau khi body đã chạy; test side effect thật.
- Chain hẹp `securityMatcher("/api/**")` khiến endpoint ngoài `/api/**` không chịu bất kỳ filter chain nào.
- Một request kích hoạt nhiều advisor; audit phải có nhiều `decisionId` chung trace.
- Policy abstain hoặc ném exception, lỗi audit pipeline và cơ chế fail closed/continue theo hợp đồng.
- Đồng thời, retry và asynchronous request: correlation không trộn hai principal; eventId/attemptId không trùng ngẫu nhiên.
- Đổi `authorizeRequests` sang `authorizeHttpRequests` hoặc từ voter sang `AuthorizationManager`: golden expected không được lấy từ output legacy có thể sai.

## 8. Tổng hợp một evidence bundle có thể review

Một hồ sơ review phải nối được **scenario → phiên bản policy → quyết định → enforcement → HTTP/side effect → kết quả test → artifact**.

~~~text
evidence/
  manifest.json             # build, source revision, testRunId, policy/matrix version
  golden-matrix.json        # input/expected/approval reference
  results.json              # actual decision and pass/fail by scenario
  audit-events.ndjson       # sanitized decisions, correlation IDs
  http-results.json         # response status and business observations
  coverage.json             # filter-chain and method-security checks
  checksums.sha256          # hashes over actual finalized artifact bytes
~~~

Ví dụ `manifest.json` với dữ liệu minh họa:

~~~json
{
  "schemaVersion": 1,
  "testRunId": "integration-run-42",
  "gitRevision": "example-commit-id",
  "policyVersion": "doc-authz-v17",
  "matrixVersion": "matrix-v5",
  "javaRuntime": "17",
  "springSecurityLine": "6.5",
  "environment": "integration",
  "expectedScenarios": 10,
  "passedScenarios": 10,
  "auditEventCount": 10,
  "checksums": "checksums.sha256"
}
~~~

Không tự khai `passedScenarios`: CI phải lấy từ test runner, kiểm tra số lượng thực và schema. Hash SHA-256 của các file được tính **sau khi hoàn tất** để so sánh tính toàn vẹn bytes. Hash không chứng minh xuất xứ, nên nếu có yêu cầu chống sửa cần chữ ký/provenance được tin cậy và lưu trữ bất biến có phân quyền. Đồng bộ clock đủ tốt để nối timeline, đồng thời dựa vào trace/decision IDs thay vì chỉ timestamp.

Một bản ghi liên kết nên cho phép truy vấn:

~~~text
scenarioId=A04
  ├─ expected=DENY (matrix-v5, owner-approved)
  ├─ policyVersion=doc-authz-v17 (gitRevision)
  ├─ decisionId=decision-A04, reason=TENANT_MISMATCH
  ├─ traceId=trace-A04, enforce=BLOCK
  ├─ HTTP=403; document not updated; message count=0
  └─ regression test PASS; audit schema PASS; artifact checksums
~~~

Không ghép các log không cùng test run/fixture để tạo một câu chuyện không có thật. Khi không thể xuất dữ liệu nhạy cảm, lưu reference tới fixture version/DB snapshot trong môi trường kiểm thử có quyền và mô tả cách tái hiện.

### Cổng nghiệm thu đề xuất

| Gate | Điều kiện |
| --- | --- |
| Quyền | Critical golden cases pass; unexpected PERMIT = 0 |
| Side effect | DENY/ERROR không ghi DB hay phát message; ABSTAIN áp fallback đúng |
| Audit | Đủ event cho các policy points bắt buộc, không thiếu correlation/version |
| Coverage | HTTP filter chain/method proxy được test; không route nhạy cảm bị bỏ lọt |
| Data safety | Audit không có token, secret, raw PII, data retention hợp lệ |
| Integrity | Checksum/provenance đã đối chiếu và lưu đúng quyền |
| Vận hành | Audit sink/backpressure/retry có failure test; authorization latency trong SLO |

Diff không còn sau khi đổi policy **không tự chứng minh an toàn**: nếu golden sai, hai phiên bản cùng cấp quyền quá rộng vẫn “khớp”. Khi đổi expected cần phê duyệt và version rõ.

## 9. Vận hành audit: đầy đủ, an toàn, ít ảnh hưởng hiệu năng

### 9.1. Chiến lược lưu và lỗi sink

Ghi network/DB đồng bộ trên mọi request có thể khiến p99 authorization latency tăng cao và gây outage khi audit sink chậm. Với event thông thường, buffer/queue có backpressure và metrics; với hành động nhạy cảm bắt buộc audit, xác định rõ yêu cầu ghi đáng tin (có thể cần transactional outbox hoặc fail-closed có chủ đích). Không để exception từ listener audit bất ngờ biến một `DENY` thành `PERMIT`. Khi sink down, phải biết số event bị từ chối vào queue và backlog; không giả vờ đã lưu thành công.

Nếu business action commit, cần audit outcome sau commit bằng transaction hook/outbox phù hợp. Ghi `COMMITTED` trước khi DB commit là bằng chứng sai. Nếu có retry, phân biệt attempt ID với logical operation ID; không làm mất sự kiện hợp lệ do dedup sai.

### 9.2. Riêng tư và toàn vẹn

Audit store cần RBAC, mã hóa khi truyền/lưu, retention, quy trình xem/xuất và log người truy vấn. Không ghi full token, cookies, raw method arguments, full request body hoặc stack trace có PII. Nếu pseudonym bằng SHA-256 trần trên email dễ đoán, kẻ khác có thể đoán dictionary; dùng key-based pseudonymization như HMAC với quản lý khóa khi phù hợp. Số định danh tài nguyên có thể vẫn là dữ liệu nhạy cảm ngay cả khi không phải email.

### 9.3. Observability và cảnh báo

Theo dõi metric có cardinality giới hạn như:
- `authz_decisions_total{decision,policy,reason_group}` và `authz_decision_duration_seconds`.
- `audit_enqueue_failures_total`, queue age/depth, DLQ và lag đến storage.
- `regression_unexpected_permit_total`, policy errors, missing correlation, coverage failures.
- Tỉ lệ deny/permit theo loại action/tenant class nếu đáp ứng nguyên tắc bảo mật và cardinality.

Không đưa userId/resourceId làm metric labels. Đặt cảnh báo khi audit mất liên tục, backlog vượt ngưỡng, policy error tăng, trace thiếu, hoặc một golden critical case bất ngờ PERMIT.

## 10. Sai lầm phổ biến

1. **Chỉ log HTTP 403.** Không biết rule/tenant/version và side effect; bổ sung policy-level audit.
2. **Nghĩ granted events luôn được phát.** Publisher Spring mặc định chỉ ghi denial, grants cần cấu hình riêng và tính overhead.
3. **Log nguyên `Authentication` hoặc request.** Có nguy cơ lộ token, body, PII; thiết kế allowlist schema.
4. **Một request chỉ có một decisionId.** Một trace có thể chứa nhiều quyết định tại HTTP/method/domain.
5. **Gộp ABSTAIN/ERROR thành DENY.** Mất ranh giới chính sách và thông tin chẩn đoán; ghi evaluation và final outcome riêng.
6. **Test chỉ so status 401/403.** Lỗi có thể đến từ CSRF/entry point; assert decision và side effect.
7. **Gọi service ngoài Spring proxy.** Method security bị bypass, test xanh giả.
8. **Lấy policy cũ làm golden.** Có thể giữ lỗ hổng tenant/owner của phiên bản trước.
9. **Ghi audit PERMIT rồi tuyên bố COMMITTED.** Giao dịch có thể rollback; audit outcome sau commit.
10. **Không xử lý queue full/audit sink lỗi.** Thiếu bằng chứng và kéo dài request; cần failure policy.
11. **Đếm đủ event nhưng thiếu policyVersion/fixture.** Không chứng minh quyết định từ đúng bản code.
12. **Coi hash là chữ ký xuất xứ.** Hash chỉ xác minh toàn vẹn khi so bytes; provenance là vấn đề khác.
13. **Để userId/resourceId vào metrics labels.** Bùng nổ cardinality.
14. **Áp cứng một audit event cho mọi request.** Một request có thể có nhiều decisions hoặc route không đi qua điểm phát event.

## 11. Checklist hoàn thành

- [ ] Golden matrix có expected độc lập, scenario ID, người phê duyệt và version.
- [ ] Mỗi policy evaluation có decisionId, traceId, policy/rule ID, actor/action/resource chuẩn hóa.
- [ ] Audit tách rõ `PERMIT/DENY/ABSTAIN/ERROR` với `PROCEED/BLOCK` và business outcome.
- [ ] Kiểm tra security chain coverage, AOP proxy, authentication, HTTP status và side effects.
- [ ] Regression có cross-tenant, role, owner, disabled, stale dữ liệu, null và exception.
- [ ] Hiểu event framework: denied mặc định, granted không tự phát; bổ sung instrumentation cho nhánh khác.
- [ ] Dữ liệu audit đã được sanitize, có RBAC, retention và kiểm soát xuất.
- [ ] Audit sink có retry/queue/alert và failure policy đã kiểm thử.
- [ ] Evidence bundle liên kết case → policy → decision → response/DB → test → artifact hash.
- [ ] CI kiểm chứng unexpected PERMIT = 0 cho critical cases và checksum/provenance theo yêu cầu.

## 12. Tài liệu tham khảo

- [Spring Security 6.5 — Authorization Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/events.html): đăng ký `AuthorizationEventPublisher`, denial và grant.
- [Spring Security 6.5 — AuthorizationEventPublisher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationEventPublisher.html): `AuthorizationResult` và contract sự kiện.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và interceptor.
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` và matcher.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): `MockMvc`, `spring-security-test` và kiểm thử hiệu lực.
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): trace/span correlation và chuẩn hóa observability.

**Kết quả cuối của một bài kiểm thử phân quyền là một chuỗi bằng chứng đáng tin:** đúng actor, đúng action, đúng tài nguyên, đúng phiên bản policy; quyết định được thi hành, side effect đã kiểm tra, và audit có thể truy xuất.
