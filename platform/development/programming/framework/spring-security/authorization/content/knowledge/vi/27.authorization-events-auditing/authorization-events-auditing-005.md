# Audit gồm chủ thể, tenant, tài nguyên, hành động, quyết định và lý do

> Ngữ cảnh: **Spring Security – authorization**, chủ đề **Sự kiện và audit**. Bài học dùng ứng dụng Java 17+ trên Spring Boot 3.x / Spring Security 6.x (Servlet stack) làm ví dụ. Nguyên tắc thiết kế audit dùng được cả ở service, message consumer và tác vụ nền; nguồn sự kiện ở WebFlux, STOMP hoặc phiên bản framework khác cần được tích hợp riêng.

## 1. Mục tiêu và tình huống

Giả sử người dùng `u-42` đang hoạt động trong tenant `tenant-a`, gọi thao tác `invoice.approve` trên hóa đơn `INV-7`. Server từ chối do thiếu quyền. Dòng log đơn giản `403 Forbidden` không trả lời được:

- **Ai** đã yêu cầu? User thật, tài khoản dịch vụ, hay anonymous?
- **Tenant nào** là phạm vi quyền đang áp dụng? Tenant được xác minh từ đâu?
- **Tài nguyên nào** được truy cập? Tài nguyên có thuộc tenant đó không?
- **Hành động gì** được thử? Đọc, phê duyệt, xóa hay xuất dữ liệu?
- **Kết quả phân quyền** là `ALLOW` hay `DENY`?
- **Vì sao** hệ thống ra quyết định? Thiếu permission, khác tenant, không thỏa thuộc tính hay policy không khớp?

Audit tốt ghi được **sáu chiều trên như một sự kiện có cấu trúc**, cùng dữ liệu bổ trợ đủ để điều tra và đối chiếu thay đổi policy. Nó phục vụ truy vết, phát hiện truy cập trái phép, giải thích quyết định, hỗ trợ kiểm soát nội bộ và kiểm thử chính sách. Audit không có tác dụng thay cho việc **thực sự chặn** request trái phép; phải tích hợp vào đường ra quyết định có kiểm soát.

Phân biệt ba khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Authentication event | `LOGIN_SUCCESS`, `LOGIN_FAILURE` | Danh tính vừa được xác minh hoặc xác minh thất bại |
| Authorization decision audit | `u-42` thử `invoice.approve` trên `INV-7` → `DENY` | Kết quả kiểm tra quyền **cho một hành động/tài nguyên cụ thể** |
| Business operation outcome | `invoice.approve` đã lưu thành công hoặc giao dịch lỗi | Thao tác nghiệp vụ **thực sự hoàn thành hay thất bại** |

**`ALLOW` không đồng nghĩa thao tác thành công.** Một quyết định `ALLOW` có thể theo sau bằng lỗi validation, xung đột trạng thái, timeout hoặc rollback. Cần tách `decision` (quyền) khỏi `outcome` (thực thi).

## 2. Sáu trường cốt lõi của authorization audit

| Trường | Ý nghĩa và nguồn tin cậy | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Chủ thể — subject** | Danh tính thực thi từ `Authentication/Principal` đã được xác thực và chuẩn hóa | `USER:u-42`, `SERVICE:job-8` | Không lấy `subjectId` từ request body rồi xem là identity |
| **Tenant** | Phạm vi tổ chức được **server xác minh** từ claim đáng tin, membership, context hoặc dữ liệu nội bộ | `tenant-a` | Phải phân biệt tenant yêu cầu với tenant của tài nguyên |
| **Tài nguyên — resource** | Loại, ID và nếu có, tenant sở hữu đối tượng đang được kiểm tra | `INVOICE:INV-7` | Tránh lưu toàn bộ payload hoặc dữ liệu nhạy cảm của đối tượng |
| **Hành động — action** | Tên thao tác chuẩn hóa, không phụ thuộc giao diện | `invoice.approve` | Một HTTP `POST` có thể gồm nhiều hành động nghiệp vụ |
| **Quyết định — decision** | Kết quả được policy engine/authorization guard đưa ra | `ALLOW` / `DENY` | Không suy ngược chỉ từ HTTP status; trường hợp `ABSTAIN`/lỗi đánh giá cần quy định rõ |
| **Lý do — reasonCode** | Mã nguyên nhân ổn định do nơi quyết định quyền tạo | `TENANT_MISMATCH`, `MISSING_PERMISSION` | Không ghi diễn giải chứa bí mật hoặc tự đoán lý do từ một 403 |

Sáu trường là **tối thiểu về mặt ý nghĩa**, không nhất thiết đều luôn có giá trị xác định. Ví dụ một request bị chặn tại URL trước khi tra cứu đối tượng có thể chưa biết `resourceId`; hãy ghi `null`/`UNKNOWN` và `decisionStage=HTTP`, không bịa một ID để “đủ trường”.

### 2.1 Subject: ai thực hiện?

`subject` nên là ID ổn định và loại danh tính: user, service account, workload, hệ thống hoặc anonymous. `Authentication#getName()` hữu ích nhưng đôi khi là username/email có thể thay đổi hoặc chứa dữ liệu cá nhân; audit dùng lâu dài nên quy đổi sang **ID nội bộ bất biến** hoặc định danh đã được chấp thuận.

Nếu hệ thống cho phép thao tác thay mặt người khác, phân biệt:

- `actorId`: danh tính thật sự gọi hệ thống, ví dụ support agent.
- `onBehalfOfId`: chủ thể được đại diện, nếu có.
- `impersonationApproved`/mã ủy quyền: bằng chứng server đã xác minh việc ủy quyền.

Không ghi mật khẩu, bearer token, session ID, cookie, full claims hoặc đối tượng `Authentication` được serialize.

### 2.2 Tenant: trong ranh giới tổ chức nào?

Với hệ thống multi-tenant, thường có ít nhất hai thông tin: `requestedTenantId` (client chọn) và `authorizedTenantId` hoặc `effectiveTenantId` (server xác nhận). Nếu tài nguyên thuộc tenant khác, ghi thêm `resourceTenantId`. Không lấy header `X-Tenant-Id` làm quyền truy cập chỉ vì header tồn tại.

Quy trình tin cậy: xác minh token/session → tra membership và role của user trong tenant → xác định active tenant → tải tài nguyên và tenant sở hữu từ nguồn server → đánh giá policy. Tenant trong audit phải phản ánh **bối cảnh được kiểm chứng**, không tự sao chép dữ liệu chưa tin cậy từ URL/body.

### 2.3 Resource và action: “quyền lên cái gì?”

Cặp `resource.type` + `resource.id` ổn định giúp tổng hợp. Nên có thêm `resource.tenantId` nếu kiểm tra tenant-level. Hành động dùng từ vựng chính sách, chẳng hạn `invoice.read`, `invoice.approve`, `invoice.export`, `user.invite`, thay vì chỉ `GET`/`POST`; ánh xạ HTTP endpoint, STOMP message hay job action sang action nghiệp vụ một cách nhất quán.

Nếu một request xử lý nhiều đối tượng, có thể ghi **nhiều quyết định** với `decisionId` riêng và cùng `requestId`. Một bản ghi “ALLOW upload” không tự chứng minh quyền với từng file nếu policy cần kiểm tra từng file.

### 2.4 Decision và reason: kết luận và cơ sở

Dùng tập giá trị được kiểm soát:

- `ALLOW`: policy cho phép yêu cầu, **không bảo đảm kết quả nghiệp vụ**.
- `DENY`: một điều kiện bắt buộc không thỏa (mặc định từ chối nếu không tìm được quyền phù hợp).
- `INDETERMINATE`/`ERROR`: không thể đánh giá chắc chắn vì dependency lỗi hoặc dữ liệu không đủ. Với tài nguyên nhạy cảm nên **fail closed** (không cho thao tác) nhưng phân biệt lỗi đánh giá với `DENY` bình thường khi phân tích audit.

Mã `reasonCode` có thể gồm `POLICY_MATCH`, `MISSING_PERMISSION`, `TENANT_MISMATCH`, `SUBJECT_UNAUTHENTICATED`, `RESOURCE_NOT_VISIBLE`, `ATTRIBUTE_CONDITION_FAILED`, `NO_MATCHING_POLICY`, `POLICY_EVALUATION_ERROR`. Mã phải xuất phát từ **bước xác định lý do thực tế**. Đừng gắn `TENANT_MISMATCH` chỉ vì thấy HTTP 403; 403 còn có thể đến từ CSRF hay nơi khác.

Đối với trường hợp nhiều điều kiện đều thất bại, quy định **thứ tự ưu tiên nguyên nhân** (ví dụ subject → tenant → resource visibility → permission → thuộc tính) hoặc ghi danh sách mã `reasonCodes` đã được chính sách cho phép. Không tiết lộ cho client lý do nội bộ có thể xác nhận một đối tượng bí mật đang tồn tại.

## 3. Cấu trúc bản ghi audit đề xuất

Một schema dễ mở rộng có thể dùng JSON:

~~~json
{
  "schemaVersion": 1,
  "eventType": "AUTHORIZATION_DECISION",
  "eventId": "evt-a1",
  "occurredAt": "2026-11-05T10:30:00Z",
  "subject": {
    "type": "USER",
    "id": "u-42"
  },
  "tenant": {
    "effectiveId": "tenant-a",
    "source": "VERIFIED_MEMBERSHIP"
  },
  "resource": {
    "type": "INVOICE",
    "id": "INV-7",
    "tenantId": "tenant-a"
  },
  "action": "invoice.approve",
  "decision": "DENY",
  "reasonCode": "MISSING_PERMISSION",
  "policy": {
    "id": "invoice-approval",
    "version": "v3"
  },
  "decisionStage": "DOMAIN",
  "requestId": "req-19",
  "traceId": "trace-72",
  "service": "billing-service"
}
~~~

Giá trị minh họa ở trên không phải sự kiện thật. Cả `eventId`, `requestId` và `traceId` đều do hệ thống tạo hoặc nhận từ cơ chế tracing tin cậy, được kiểm tra định dạng. Trong môi trường thật, tránh đưa trace ID tùy ý do client gửi vào log mà không chuẩn hóa.

Các trường bổ trợ có giá trị:

| Trường bổ trợ | Công dụng |
| --- | --- |
| `schemaVersion` | Cho phép nâng cấp schema mà consumer cũ vẫn đọc được |
| `eventId` / `decisionId` | Nhận diện một quyết định, chống trùng khi retry |
| `occurredAt` | Thời điểm quyết định theo UTC; thêm thời điểm ingest nếu cần |
| `requestId` / `traceId` | Ghép chuỗi sự kiện qua gateway, service, database |
| `decisionStage` | `HTTP`, `METHOD`, `DOMAIN`, `MESSAGE`… |
| `policy.id` / `policy.version` | Giải thích vì sao cùng request có thể nhận kết quả khác sau thay đổi rule |
| `service` / `environment` | Xác định nơi thực thi; không lẫn staging với production |
| `actorType`, `sessionAssurance` | Phân loại user, service, MFA/step-up nếu policy dùng yếu tố này |
| `decisionLatencyMs` | Theo dõi chi phí đánh giá policy |
| `operationId` / `outcome` riêng | Liên kết sau này với kết quả thực thi mà không đánh đồng authorization |

Ưu tiên schema **versioned, ổn định và có kiểu dữ liệu rõ**. Với trường không có do quyết định xảy ra sớm, dùng `null`/trạng thái `UNKNOWN` có ý nghĩa; không tạo chuỗi rỗng khiến người đọc tưởng lỗi thu thập.

## 4. Đường đi của một sự kiện trong kiến trúc Spring Security

~~~text
Request / message / scheduled job
          │
          ▼
Authentication: nhận diện actor
          │
          ▼
Tenant resolver: xác minh membership và effective tenant
          │
          ▼
Authorization check (URL, method, domain, resource)
          │
          ├── ALLOW ──► audit decision: ALLOW + reason/policy
          │                 │
          │                 └── chạy nghiệp vụ → outcome riêng (success/failure)
          │
          └── DENY  ──► audit decision: DENY + reason/policy
                            │
                            └── chặn thao tác / ném AccessDeniedException / trả 403
                                    (cách chuyển sang HTTP phụ thuộc auth status)
~~~

Mỗi lớp có góc nhìn khác nhau:

- **HTTP authorization** qua `authorizeHttpRequests` / `AuthorizationFilter` biết method/path, principal, thường **chưa biết resource owner hoặc tenant của bản ghi trong database**.
- **Method security** qua `@EnableMethodSecurity`, `@PreAuthorize` và `AuthorizationManagerBeforeMethodInterceptor` có thể biết tham số method nhưng chưa chắc có toàn bộ dữ liệu từ DB.
- **Domain authorization** trong service/policy guard biết quyền trên một đối tượng cụ thể sau khi tải từ nguồn đáng tin; đây thường là nơi tốt nhất để ghi đủ sáu trường và mã nguyên nhân chính xác.
- **Authentication events** và **CSRF rejections** là các loại tín hiệu bảo mật khác; không giả định mọi lỗi đăng nhập/CSRF đều xuất hiện dưới dạng `AuthorizationDeniedEvent` của quyết định domain.

Nếu cùng request bị kiểm tra ở HTTP rồi ở service, có thể có **hai audit decision khác nhau**, với `decisionStage`/`policy.id` khác nhau. Điều này hợp lệ nếu mỗi bản ghi thể hiện đúng một điểm kiểm tra và có `decisionId` riêng. Nếu yêu cầu nghiệp vụ chỉ cần một bản ghi quyết định chuẩn, hãy chọn một nguồn phát canonical và đưa các kiểm tra khác vào telemetry hỗ trợ; tránh cộng đôi thành hai lần “truy cập bị từ chối”.

### Dấu vết ALLOW không chứng minh giao dịch đã commit

Ví dụ `u-42` vượt qua policy, được `ALLOW` để duyệt hóa đơn. Sau đó database rollback vì số dư không phù hợp. Audit authorization ghi `ALLOW`, còn business audit ghi `OPERATION_FAILED`. Nếu đổi `ALLOW` thành `DENY` sau rollback thì lịch sử phân quyền bị sai. Có thể dùng cùng `operationId` để liên kết hai sự kiện.

## 5. Ví dụ Java 17 chạy độc lập: tạo ba quyết định audit

Ví dụ sau mô phỏng quyết định theo **tenant trước, permission sau**. Nó dùng tập quyền đã xác minh sẵn; code không chứng minh cách đăng nhập hoặc tải tenant từ database. Đặt vào file `AuthorizationAuditExample.java`:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class AuthorizationAuditExample {

    enum Decision { ALLOW, DENY }

    record Actor(
        String id,
        String tenantId,
        Set<String> permissions
    ) {}

    record Resource(
        String type,
        String id,
        String tenantId
    ) {}

    record AuditEvent(
        Instant occurredAt,
        String subjectId,
        String tenantId,
        String resourceType,
        String resourceId,
        String action,
        Decision decision,
        String reasonCode
    ) {}

    static AuditEvent evaluate(
        Actor actor,
        Resource resource,
        String action,
        String requiredPermission
    ) {
        Decision decision;
        String reason;

        if (!actor.tenantId().equals(resource.tenantId())) {
            decision = Decision.DENY;
            reason = "TENANT_MISMATCH";
        } else if (!actor.permissions().contains(requiredPermission)) {
            decision = Decision.DENY;
            reason = "MISSING_PERMISSION";
        } else {
            decision = Decision.ALLOW;
            reason = "POLICY_MATCH";
        }

        // Thời điểm cố định để output bài học luôn tái lập được.
        return new AuditEvent(
            Instant.parse("2026-01-02T09:00:00Z"),
            actor.id(),
            actor.tenantId(),
            resource.type(),
            resource.id(),
            action,
            decision,
            reason
        );
    }

    public static void main(String[] args) {
        Actor actor = new Actor(
            "u-42", "tenant-a", Set.of("invoice.read")
        );

        Resource own = new Resource("INVOICE", "INV-7", "tenant-a");
        Resource other = new Resource("INVOICE", "INV-8", "tenant-b");

        List<AuditEvent> events = List.of(
            evaluate(actor, own, "invoice.approve", "invoice.approve"),
            evaluate(actor, other, "invoice.read", "invoice.read"),
            evaluate(actor, own, "invoice.read", "invoice.read")
        );

        for (AuditEvent e : events) {
            System.out.printf(
                "subject=%s tenant=%s resource=%s:%s action=%s decision=%s reason=%s%n",
                e.subjectId(),
                e.tenantId(),
                e.resourceType(),
                e.resourceId(),
                e.action(),
                e.decision(),
                e.reasonCode()
            );
        }
    }
}
~~~

Lệnh chạy (JDK 17+):

~~~bash
javac AuthorizationAuditExample.java
java AuthorizationAuditExample
~~~

Stdout chính xác:

~~~text
subject=u-42 tenant=tenant-a resource=INVOICE:INV-7 action=invoice.approve decision=DENY reason=MISSING_PERMISSION
subject=u-42 tenant=tenant-a resource=INVOICE:INV-8 action=invoice.read decision=DENY reason=TENANT_MISMATCH
subject=u-42 tenant=tenant-a resource=INVOICE:INV-7 action=invoice.read decision=ALLOW reason=POLICY_MATCH
~~~

Chú ý:

1. Actor được phép đọc `invoice.read` nhưng không được duyệt `invoice.approve`.
2. Cùng permission `invoice.read` vẫn không đủ khi resource thuộc tenant khác.
3. Quyết định `ALLOW` chỉ nói actor được đọc resource, không cho biết thao tác đọc đã thực thi thành công.
4. Trong sản phẩm thật, thay `Instant.parse(...)` bằng `Clock.instant()`/`Instant.now()`; dùng ID tin cậy và eventId/traceId duy nhất; lưu qua audit writer có kiểm soát.
5. Code trả `AuditEvent` để minh họa; tại điểm thực thi, phải **chặn thao tác khi `DENY`**, không chỉ in log. Policy không an toàn nếu ghi DENY mà vẫn gọi service.

## 6. Kết nối với Spring Security Authorization Events

Spring Security cung cấp các sự kiện thuộc namespace `org.springframework.security.authorization.event`, đáng chú ý là `AuthorizationDeniedEvent` và `AuthorizationGrantedEvent`. Việc phát sự kiện dựa trên `AuthorizationEventPublisher`. Trong các luồng tích hợp hỗ trợ publisher, nhà phát `SpringAuthorizationEventPublisher` có thể chuyển thành Spring application events; sự kiện **DENY** được xuất bản theo cơ chế mặc định của publisher, còn **GRANT không được phát đại trà theo mặc định** vì dễ tạo khối lượng lớn.

### 6.1 Đăng ký publisher

Ví dụ cấu hình cho Spring Security tương thích:

~~~java
// AuthorizationEventsConfig.java, package và import tùy project
package example.audit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;

@Configuration
public class AuthorizationEventsConfig {
    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher events) {
        return new SpringAuthorizationEventPublisher(events);
    }
}
~~~

Đây là class cấu hình trong **dự án Spring Boot có dependency `spring-boot-starter-security`**, không phải Java độc lập để chạy bằng `javac`. Với method security, cần bật `@EnableMethodSecurity` cho ứng dụng có dùng `@PreAuthorize`. Sự hiện diện bean publisher không tự bổ sung chính sách authorization; các rule HTTP/method/domain vẫn phải được cấu hình.

### 6.2 Lắng nghe sự kiện bị từ chối, không serialize context thô

~~~java
// AuthorizationDeniedObserver.java
package example.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class AuthorizationDeniedObserver {
    private static final Logger log =
        LoggerFactory.getLogger(AuthorizationDeniedObserver.class);

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        Authentication authentication = event.getAuthentication().get();

        String actorKind =
            (authentication == null
                || authentication instanceof AnonymousAuthenticationToken)
                ? "ANONYMOUS" : "AUTHENTICATED";

        Object target = event.getObject();
        String targetKind = target == null
            ? "UNKNOWN" : target.getClass().getSimpleName();

        log.warn("authz_event=DENY actor_kind={} target_kind={}",
            actorKind, targetKind);
    }
}
~~~

**Ý nghĩa và giới hạn:** listener này quan sát tín hiệu DENY an toàn ở mức tổng quát, **chưa tạo bản ghi audit đủ sáu trường**. `event.getObject()` có thể là request context, method invocation hoặc đối tượng framework tùy chỗ kiểm tra; dùng `toString()` hay serialize toàn bộ có thể làm lộ URL nhạy cảm, header, tham số method hoặc body. Hơn nữa, sự kiện mặc định không nhất thiết mang `tenantId`, `resourceId` và `reasonCode` nghiệp vụ.

Do đó, để có audit đầy đủ, service/policy guard cần bổ sung context đáng tin cậy và **mã nguyên nhân do chính policy đánh giá**. Không được suy đoán `MISSING_PERMISSION` chỉ vì listener thấy `AuthorizationDeniedEvent`. Nếu còn cần quan sát `ALLOW`, cấu hình publisher để phát **có chọn lọc** theo loại quyết định/quyền nhạy cảm, hoặc phát domain audit ở nơi cho phép; tránh bật toàn bộ grant cho hệ thống lưu lượng cao mà chưa có thiết kế tải.

### 6.3 Mẫu ghi audit tại điểm ra quyết định nghiệp vụ

Tại nơi server đã có principal, active tenant được xác minh và resource từ database, thứ tự khuyến nghị:

~~~text
1. Xác định actorId từ Authentication/Principal tin cậy.
2. Xác minh quyền membership của actor trong effectiveTenantId.
3. Tải resource theo truy vấn có ràng buộc tenant; xác định resourceType/resourceId.
4. Đánh giá policy (bao gồm ownership, permission, trạng thái, thuộc tính).
5. Tạo decisionId, decision, reasonCode, policyVersion.
6. Gửi một AuditRecord bất biến đến AuditSink.
7. DENY → chặn theo AccessDeniedException; ALLOW → tiếp tục nghiệp vụ.
8. Ghi business outcome riêng sau khi nghiệp vụ hoàn tất/rollback.
~~~

Nếu logic ở bước 3 cố tình trả cùng 404 cho “không tồn tại” và “không được xem” để tránh enumeration, audit nội bộ cũng chỉ nên giữ thông tin tối thiểu được phép. Đừng tiết lộ lý do `RESOURCE_EXISTS_BUT_FORBIDDEN` cho client.

Ví dụ **pseudocode tích hợp** (tên `AuditSink`, `TenantMembershipService`, `InvoicePolicy` là abstraction của ứng dụng; đoạn này không phải file Java độc lập):

~~~java
EffectiveTenant tenant = tenantService.requireMembership(actor, requestedTenant);
Invoice invoice = repository.loadForAuthorization(invoiceId);
PolicyResult result = invoicePolicy.check(
    actor, tenant, invoice, "invoice.approve");

AuditRecord record = AuditRecord.of(
    actor.stableId(), tenant.id(),
    "INVOICE", invoice.stableId(),
    "invoice.approve", result.decision(), result.reasonCode(),
    result.policyVersion(), currentRequestId());

auditSink.append(record);

if (!result.allowed()) {
    throw new AccessDeniedException("Action not permitted");
}

invoiceService.approve(invoice);
~~~

Hai điểm quan trọng về logic thực tế:

- Nếu bước membership hoặc lookup resource **đã từ chối trước khi có đầy đủ đối tượng**, audit cần xảy ra trong nhánh thất bại đó và dùng trường chưa biết rõ ràng; không để `throw` xảy ra trước khi có dấu vết quyết định quan trọng.
- Nếu thao tác thuộc nhóm có yêu cầu **audit bắt buộc**, phải định nghĩa chuyện gì xảy ra khi `auditSink` thất bại (block/fail closed hay queue bền vững). Không để việc ghi log thông thường tùy ý quyết định quyền truy cập khi chưa có chính sách.

## 7. Thiết kế reasonCode nhất quán

Một hệ thống khó truy vết nếu nơi này ghi `"User missing right"`, nơi khác ghi `"permission_denied"`, nơi khác ghi cả exception message. Nên có từ điển mã có version và ý nghĩa kiểm thử được:

| `reasonCode` | Trường hợp phát sinh | Nguyên tắc |
| --- | --- | --- |
| `SUBJECT_UNAUTHENTICATED` | Không có danh tính đủ tin cậy để đánh giá | Thường thuộc authentication stage hoặc policy yêu cầu login |
| `TENANT_MEMBERSHIP_MISSING` | User không thuộc tenant đã chọn | Đối chiếu membership phía server |
| `TENANT_MISMATCH` | Tenant của tài nguyên khác phạm vi được phép | Không tin resource tenant do client khai |
| `MISSING_PERMISSION` | Thiếu `invoice.approve`/scope cần có | Permission name cần chuẩn hóa |
| `RESOURCE_NOT_VISIBLE` | Không được xem hoặc thông tin tồn tại bị che | Tránh tiết lộ ID cho client |
| `POLICY_CONDITION_FAILED` | Thuộc tính bổ sung không thỏa (thời gian, sở hữu, trạng thái…) | Có thể thêm `policyRuleId` ở audit nội bộ |
| `NO_MATCHING_POLICY` | Không có rule cho action/resource này | Thực hiện deny by default |
| `POLICY_EVALUATION_ERROR` | Không đánh giá được do dependency lỗi | Fail closed; phân biệt với deny bình thường |
| `POLICY_MATCH` | Các điều kiện cần đều thỏa | Reason cho ALLOW, không dùng làm kết quả nghiệp vụ |

Ví dụ có cả thiếu permission và tenant mismatch: nếu policy đã từ chối tại tenant guard, reason chính nên là `TENANT_MISMATCH` theo thứ tự đánh giá. Tránh suy luận ngược về permission chưa từng được kiểm tra. Nếu cần ghi nhiều reason, chỉ ghi những điều kiện đã thực sự được đánh giá và xử lý rủi ro tiết lộ thông tin.

Lưu ý: `AccessDeniedException` hoặc `AuthorizationDeniedEvent` thường chỉ chứng tỏ một quyết định từ chối; chúng **không tự cung cấp** mã `TENANT_MISMATCH`, `MISSING_PERMISSION` hay một `policyVersion` cụ thể. Đây là trách nhiệm thiết kế của tầng policy/domain hoặc của một `AuthorizationResult` tùy biến có dữ liệu giải thích theo hợp đồng ứng dụng.

## 8. Nguồn dữ liệu tin cậy và chống giả mạo trong multi-tenant

Xem tình huống attacker đã đăng nhập tenant A nhưng gửi:

~~~http
POST /api/tenants/tenant-b/invoices/INV-8/approve
X-Tenant-Id: tenant-b
Authorization: Bearer <redacted>
~~~

Header/path chỉ nêu ý định của client. Server phải:

1. Xác thực token bằng issuer, audience, chữ ký, hạn dùng hoặc session theo kiến trúc.
2. Xác định `actorId` tin cậy và kiểm tra membership thực tế với `tenant-b`.
3. Nếu không thuộc tenant B, từ chối và audit `TENANT_MEMBERSHIP_MISSING`. Chưa nhất thiết được phép tiết lộ `INV-8` có tồn tại không.
4. Nếu thuộc tenant B, tải `INV-8` theo điều kiện tenant đúng; kiểm tra resource owner và `invoice.approve`.
5. Ghi audit với actor, effective tenant được server xác minh, resource/action, decision và reason.

Không dùng `ThreadLocal`/`SecurityContext` sau khi chuyển sang async thread mà không truyền context theo cơ chế được kiểm soát. Trong message consumer/job không có HTTP request, subject có thể là service identity; tenant phải đến từ message đã được xác minh hoặc metadata từ nguồn tin cậy. Nếu context thiếu, đánh giá **fail closed** theo chính sách và audit tình trạng thiếu context.

Với hệ thống nhiều tenant, cần quản trị phân quyền **xem audit**: người vận hành tenant A không được truy vấn audit của tenant B chỉ vì biết `eventId`/`resourceId`. Ràng buộc tenant và scope ở chính hệ thống lưu trữ/search audit, không chỉ ở API nghiệp vụ gốc.

## 9. Ghi và lưu audit: toàn vẹn, hiệu năng, khả năng tra cứu

### 9.1 Sự kiện bất biến, có ID và timestamp chuẩn

Dùng record/schema immutable; có `eventId` duy nhất, `occurredAt` UTC và `ingestedAt` khi pipeline nhận dữ liệu. Đừng “sửa lịch sử” bằng UPDATE cũ khi policy thay đổi; tạo sự kiện correction nếu cần. Với Kafka, outbox, queue hay sink bất đồng bộ, **at-least-once delivery** có thể gửi lại: consumer phải deduplicate theo `eventId` và lưu vết retry phù hợp.

### 9.2 Cân bằng bảo mật và độ trễ

- **Audit bắt buộc với thao tác nhạy cảm:** chọn cơ chế durable, backpressure/failover và quyết định fail closed cụ thể nếu không thể bảo đảm ghi; đánh giá khả năng thực thi, timeout và khôi phục.
- **Telemetry cho allow số lượng lớn:** có thể sampling/aggregation, nhưng **không gọi dữ liệu đã lấy mẫu là nhật ký audit đầy đủ**. Denial/security-critical events thường cần ghi đáng tin cậy hơn.
- **Tránh block request vì hệ thống log không quan trọng:** phân biệt operational log với security audit có yêu cầu bảo toàn.
- **Không ghi raw exception/HTTP body vào sink:** redact/mask/allowlist trường. Log line nên theo cấu trúc JSON hoặc định dạng parse được, giới hạn kích thước giá trị nhập từ client.

Các Spring Application Event listener thường chạy đồng bộ trong publisher thread theo cấu hình mặc định của application event multicaster. Vì vậy, gọi database/network chậm ngay trong listener có thể kéo dài request. Với sự kiện nhiều, tách bước chuẩn hóa record khỏi luồng gửi bền vững; nhưng **không làm mất bảo đảm** audit đối với nghiệp vụ buộc phải có audit.

### 9.3 Bảo vệ audit khỏi bị sửa/xóa

Áp dụng quyền ghi/tìm kiếm phân tách, retention theo chính sách, kiểm soát PII, mã hóa khi truyền/lưu, backup và cơ chế phát hiện chỉnh sửa (append-only/WORM/chữ ký/hash-chain khi yêu cầu). Đồng bộ đồng hồ và trace IDs. Khi lưu actor ID hoặc IP theo quy định riêng tư, chỉ giữ các trường cần thiết, giới hạn thời gian giữ và kiểm soát truy cập.

Audit có thể dùng cho điều tra, nên **không phụ thuộc hoàn toàn vào log của pod/container dễ bị xóa**. Centralized audit store hoặc pipeline có persistence phù hợp sẽ đáng tin hơn stdout đơn lẻ.

## 10. Kiểm thử policy và audit cùng nhau

Thiết kế test dựa trên cả hành vi thực thi lẫn event:

| Kịch bản | Quyết định mong đợi | Lý do mong đợi | Assertion về audit |
| --- | --- | --- | --- |
| Đã xác thực, cùng tenant, đủ quyền | `ALLOW` | `POLICY_MATCH` | Đúng subject/tenant/resource/action, policy version; không tự gán business success |
| Cùng tenant nhưng thiếu quyền | `DENY` | `MISSING_PERMISSION` | Một decision event chính; thao tác không được chạy |
| Đủ permission nhưng tài nguyên tenant khác | `DENY` | `TENANT_MISMATCH` | Effective tenant và resource tenant được phân biệt |
| User giả mạo `X-Tenant-Id` | `DENY` | `TENANT_MEMBERSHIP_MISSING` | Không lấy claimed tenant làm verified tenant |
| Anonymous gọi thao tác yêu cầu login | Bị chặn | `SUBJECT_UNAUTHENTICATED` nếu policy quy ước | Subject type = ANONYMOUS, không bịa user ID |
| Resource không được phép xem | Bị chặn | `RESOURCE_NOT_VISIBLE` hoặc mã policy tương đương | Không tiết lộ ID/metadata nhạy cảm cho client |
| Hệ thống policy lookup timeout | Không cho thao tác | `POLICY_EVALUATION_ERROR` | Ghi failure stage; không giả làm thiếu permission |
| Quyết định ALLOW rồi DB rollback | `ALLOW` | `POLICY_MATCH` | Audit quyền còn ALLOW; business outcome báo FAILED riêng |
| Retry phát cùng event | Không thêm bản ghi quyết định logic | Không đổi | Deduplicate bằng eventId/decisionId |
| Một request chặn ở HTTP trước service | Bị chặn | Lý do tại HTTP layer | Không khẳng định đã có resourceId/domain reason chưa được tính |

Ví dụ checklist assertion ở unit/integration test:

~~~text
assert(response is 403 or configured deny response);
assert(domainOperationWasNotExecuted);
assert(audit.eventType == "AUTHORIZATION_DECISION");
assert(audit.subject.id == authenticatedSubjectId);
assert(audit.tenant.effectiveId == verifiedTenantId);
assert(audit.resource.type == expectedResourceType);
assert(audit.action == expectedAction);
assert(audit.decision == "DENY");
assert(audit.reasonCode == expectedReasonFromPolicy);
assert(noCredentialOrSecretInAudit);
~~~

Đoạn trên là **pseudocode kiểm thử**, không phải cú pháp Java để chạy trực tiếp. Với unit test Java thực tế, có thể kiểm `AuthorizationAuditExample.evaluate(...)` trả đúng `AuditEvent`; với Spring integration test, mock audit sink rồi xác nhận event chỉ xuất khi policy đã đánh giá và lệnh nghiệp vụ bị chặn khi deny.

Nếu có yêu cầu *mỗi quyết định đúng một event*, xác định chính xác ranh giới kiểm thử (một domain guard hay toàn bộ request qua nhiều layer). Không viết test `exactly once` trên hệ thống queue vốn có thể giao hàng lặp; tại đó test xử lý idempotent mới đúng.

## 11. Những lỗi thiết kế thường gặp

1. **Chỉ ghi HTTP status**: mất actor, tenant, resource, action và nguyên nhân; 403 còn có thể do CSRF chứ không phải policy từ chối.
2. **Lấy tenant/subject trực tiếp từ request**: client có thể thay đổi; audit sai lệch và quyết định quyền có nguy cơ sai.
3. **Ghi `DENY` chung chung không có reasonCode**: khó phân biệt thiếu permission với tenant mismatch hay dependency lỗi.
4. **Suy diễn reason từ exception message**: text không ổn định, có thể chứa thông tin nội bộ; nên sử dụng mã reason do policy sản sinh.
5. **Ghi `ALLOW` như giao dịch thành công**: authorization và business outcome là hai bước độc lập.
6. **Serialize toàn bộ SecurityContext/request/method arguments**: có thể rò rỉ credential, PII hoặc dữ liệu miền nhạy cảm.
7. **Bật mọi `AuthorizationGrantedEvent`**: lưu lượng lớn, dễ tăng độ trễ/chi phí; chỉ phát chọn lọc hoặc audit domain theo yêu cầu.
8. **Chỉ bắt `AccessDeniedException` ở controller**: nhiều quyết định xảy ra trong filter/method interceptor; dễ bỏ sót. Cần ghi tại điểm kiểm tra phù hợp.
9. **Nhiều layer ghi trùng một quyết định**: không có `decisionId` và `decisionStage` để phân biệt; thống kê sai.
10. **Ghi audit rồi vẫn thực thi khi `DENY`**: audit chỉ là quan sát, không bảo vệ tài nguyên. Enforcement phải là điều kiện bắt buộc.
11. **Thất bại khi ghi audit nhưng không có chính sách xử lý**: với thao tác nhạy cảm có thể tạo lỗ hổng truy vết; với log không quan trọng lại gây giảm availability không cần thiết.
12. **Cho phép tenant xem mọi bản ghi audit**: audit store cũng là tài nguyên cần phân quyền, tenant isolation và data minimization.

## 12. Tự kiểm tra và ghi nhớ

Hãy tự trả lời các câu sau khi thiết kế một endpoint `POST /api/tenants/{tenantId}/invoices/{id}/approve`:

- Actor được lấy từ `Authentication` hay từ trường `userId` trong body?
- Tenant đã được kiểm tra membership chưa, và có khớp tenant sở hữu hóa đơn không?
- Tên action là `POST` hay `invoice.approve`; policy version nào đã được áp dụng?
- Hệ thống ghi `DENY` với reason cụ thể ở điểm nào trước khi ném lỗi?
- Nếu quyết định `ALLOW` nhưng database rollback, hai sự kiện sẽ được biểu diễn ra sao?
- Có thể điều tra bằng `requestId`/`eventId` mà không phải tìm token hoặc dữ liệu nhạy cảm không?

**Mẫu tư duy:** audit một quyết định = **chủ thể đã xác minh + tenant đã xác minh + tài nguyên xác định được + hành động chuẩn hóa + kết quả policy + mã lý do ổn định**, bổ sung thời điểm, version policy và correlation. Mỗi trường phản ánh sự thật được biết tại **thời điểm quyết định**, không phải giả định tạo sau đó.

## 13. Tài liệu tham khảo

Tài liệu chính thức Spring Security (kiểm tra phiên bản dependency trước khi dùng API):

- Authorization Events: https://docs.spring.io/spring-security/reference/servlet/authorization/events.html
- Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Authentication Events (phân biệt với authorization): https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- API AuthorizationDeniedEvent: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html
