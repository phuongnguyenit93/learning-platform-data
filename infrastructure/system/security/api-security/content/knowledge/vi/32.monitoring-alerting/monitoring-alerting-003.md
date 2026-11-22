# Phát hiện truy cập object giữa tenant

Trong hệ thống multi-tenant, mỗi request thường mang theo một tenant context và truy cập dữ liệu thuộc tenant đó. Một lỗi authorization có thể khiến user của tenant A đọc, sửa, xóa hoặc export object của tenant B. Đây là dạng cross-tenant access, thường xuất hiện khi ứng dụng chỉ kiểm tra người dùng đã đăng nhập mà không ràng buộc object với tenant, khi tenant ID do client tự chọn được tin tưởng, hoặc khi một service nội bộ bỏ qua policy của service gọi nó.

Authorization và tenant isolation phải ngăn hành vi trái phép ngay tại đường xử lý. Monitoring và alerting bổ sung một lớp phát hiện: ghi nhận quyết định truy cập, so sánh tenant của actor với tenant sở hữu resource, nhận diện pattern bất thường và cảnh báo khi có dấu hiệu truy cập chéo tenant. Đặc biệt, cần phát hiện cả **attempt bị từ chối** và **truy cập đã thành công nhưng đáng lẽ phải bị từ chối**. Chỉ đếm HTTP 403 sẽ bỏ lỡ trường hợp nguy hiểm nhất: dữ liệu đã bị trả về.

## 1. Mục tiêu phát hiện cross-tenant object access

Một hệ thống giám sát tốt cần trả lời:

- Actor nào đã truy cập hoặc cố truy cập object?
- Tenant context của request là gì?
- Tenant sở hữu object thực tế là gì?
- Hành động là read, update, delete, export, download hay action nghiệp vụ khác?
- Authorization policy đã quyết định ALLOW hay DENY, theo rule và policy version nào?
- Request có đi qua luồng delegation, support access hoặc platform administration hợp lệ không?
- Có bao nhiêu object/tenant bị thử trong một khoảng thời gian?
- Nếu access thành công, dữ liệu nào đã được trả hoặc thay đổi ở mức phân loại và số lượng?
- Sự kiện có liên quan tới request, trace, job hoặc service call nào khác không?

Mục tiêu là phát hiện nhanh truy cập chéo tenant, giảm thời gian phơi nhiễm, hỗ trợ điều tra và cung cấp bằng chứng kiểm toán. Monitoring không thay thế object-level authorization, tenant-scoped query, database row-level security hoặc kiểm thử bảo mật.

## 2. Xác định rõ các tenant và object identity

Muốn phát hiện truy cập chéo tenant, hệ thống phải biết tenant của actor và tenant của resource. Không thể suy ra hai giá trị này chỉ từ URL hoặc header.

| Thành phần | Ý nghĩa | Nguồn nên dùng |
|---|---|---|
| Actor subject | User, service principal hoặc workload thực hiện hành động | Principal đã xác thực từ token, session, mTLS hoặc workload identity |
| Actor tenant | Tenant mà actor đang hoạt động trong request | Tenant context đã resolve và kiểm tra membership |
| Resource tenant | Tenant sở hữu hoặc quản lý object được truy cập | Metadata của object lấy từ storage/domain model đáng tin cậy |
| Requested tenant | Tenant selector trong path/header/host nếu API có | Input client sau khi được server xác minh |
| Effective tenant | Tenant thực sự dùng để scope truy vấn và authorization | Context immutable do server tạo sau khi kiểm tra |
| Delegation context | Lý do actor được phép truy cập ngoài tenant mặc định | Grant/policy có scope, approver, purpose và expiry |

Ví dụ, request tới /tenants/tenant-a/invoices/inv-123 không chứng minh invoice thuộc tenant A. Server phải tải hoặc truy vấn object trong phạm vi được phép và xác minh resource tenant thực tế. Nếu URL nói tenant A nhưng object thuộc tenant B, đây là tín hiệu cần được ghi nhận, kể cả khi ứng dụng trả 404 để che sự tồn tại của object.

Một số resource có thể được chia sẻ hợp lệ giữa tenant, ví dụ catalog công khai, template do platform quản lý hoặc dữ liệu đã được cấp quyền cross-tenant. Với loại này, cần phân loại resource ownership và policy rõ ràng; không áp dụng quy tắc so sánh tenant đơn giản cho mọi object.

## 3. Phân biệt attempted access và successful access

Hai nhóm sự kiện có mức độ rủi ro khác nhau:

| Kết quả | Ví dụ | Ý nghĩa giám sát |
|---|---|---|
| Denied cross-tenant attempt | User tenant A yêu cầu invoice tenant B, policy từ chối | Có thể là lỗi client, thử ID ngẫu nhiên hoặc hành vi dò quét |
| Allowed delegated access | Support agent truy cập tenant B theo grant có hiệu lực | Hợp lệ nếu đúng actor, scope, purpose và thời hạn |
| Unexpected allow | User tenant A đọc được object tenant B mà không có grant | Sự cố nghiêm trọng, dữ liệu có thể đã bị lộ |
| Inconsistent decision | Policy log ghi DENY nhưng response/data layer vẫn trả object | Có thể có đường bypass hoặc lỗi enforcement |
| Missing tenant evidence | Request truy cập object nhưng không xác định được resource tenant | Blind spot cần điều tra; không nên mặc định là an toàn |

Không coi mọi 403 là tấn công. Một số request bị từ chối là hành vi bình thường. Tuy nhiên, **một successful access có tenant mismatch và không có delegation hợp lệ** phải được ưu tiên cao vì có thể chứng minh kiểm soát đã thất bại.

## 4. Nguồn telemetry cần kết hợp

Không nên chỉ dựa vào access log của API gateway. Gateway thường không biết object ID thực tế, object owner hoặc policy decision trong domain.

| Nguồn | Tín hiệu hữu ích | Hạn chế |
|---|---|---|
| Authorization decision log | Actor, action, resource, tenant, ALLOW/DENY, policy reason | Có thể thiếu bằng chứng dữ liệu thực sự đã được đọc/ghi |
| Domain/data access audit | Object tenant, thao tác thực tế, số bản ghi và loại dữ liệu | Cần instrument đúng service và tránh log payload |
| API gateway/access log | Route, method, caller, status, source và volume | Thường không biết resource tenant |
| Database/RLS audit | Tenant predicate, row access, policy violation nếu DB hỗ trợ | Không phải mọi truy vấn đều tạo audit chi tiết |
| Service mesh/distributed trace | Quan hệ service-to-service, request/job correlation | Trace sampling có thể bỏ sót sự kiện |
| Export/download service | Số object, bytes, data classification và destination | Cần nối với actor và tenant context |
| Admin/support audit | Impersonation, break-glass, delegated grant và ticket | Cần phân biệt hoạt động được phê duyệt với bất thường |

Sự kiện authorization nên được phát ra tại nơi policy thực sự quyết định. Sự kiện data access nên được phát ra khi thao tác đọc/ghi/export được thực hiện. Ghép hai nguồn giúp phát hiện trường hợp policy nói ALLOW nhưng data layer truy cập sai tenant, hoặc policy nói DENY nhưng một đường khác vẫn trả dữ liệu.

## 5. Thiết kế security event cho tenant access

Một security event nên có schema ổn định, có thể tìm kiếm và tương quan giữa nhiều service. Ví dụ:

~~~json
{
  "eventId": "01JQ7N8W6M5Y4K3P2R1S0T9U8V",
  "eventType": "object.authorization.decision",
  "occurredAt": "2026-11-18T10:30:00Z",
  "environment": "production",
  "service": "billing-api",
  "actor": {
    "type": "user",
    "subjectRef": "hmac:v3:8b7d...",
    "tenantRef": "hmac:v3:tenant-a...",
    "clientId": "customer-portal"
  },
  "resource": {
    "type": "invoice",
    "objectRef": "hmac:v3:inv-123...",
    "tenantRef": "hmac:v3:tenant-b...",
    "classification": "confidential"
  },
  "action": "invoice.read",
  "decision": "DENY",
  "reasonCode": "TENANT_SCOPE_MISMATCH",
  "policy": {
    "id": "invoice-tenant-isolation",
    "version": "12"
  },
  "request": {
    "route": "/api/v1/tenants/{tenantId}/invoices/{invoiceId}",
    "method": "GET",
    "status": 404,
    "traceId": "trace-opaque-id"
  },
  "delegation": {
    "used": false
  }
}
~~~

Các ID trong ví dụ là reference đã được pseudonymize. Không cần ghi raw invoice payload, email, token hoặc toàn bộ URL. Schema thực tế nên có:

- Event ID duy nhất, timestamp UTC và service/environment.
- Actor type, subject reference, authenticated client/service và actor tenant.
- Resource type, object reference và resource tenant.
- Action, decision, reason code, policy ID/version.
- Request/trace/job correlation, route template và HTTP method.
- Data classification, record count/byte count khi phù hợp.
- Delegation/break-glass context nếu có.
- Source IP hoặc device signal đã chuẩn hóa khi chính sách cho phép.

Không đưa tenant ID từ request body vào event như thể đó là tenant đã xác minh. Ghi riêng requested tenant và effective/actor/resource tenant để phân tích được mismatch.

## 6. Ghi cả quyết định và thao tác dữ liệu thực tế

Một quyết định ALLOW chưa chắc đã tạo ra truy cập dữ liệu; một request có thể lỗi trước khi đọc object. Ngược lại, nếu authorization chỉ được kiểm tra ở gateway nhưng repository có đường khác, data access có thể xảy ra mà không có decision event tương ứng.

Nên phân biệt event type:

| Event | Khi phát | Dùng để trả lời |
|---|---|---|
| object.authorization.decision | Policy quyết định ALLOW/DENY | Caller có được phép theo policy không? |
| object.read.completed | Dữ liệu đã được đọc/đưa vào response | Object nào thực sự được truy cập? |
| object.write.completed | Thay đổi đã commit | Object nào đã bị sửa/xóa? |
| object.export.completed | Export/download được tạo hoặc hoàn tất | Bao nhiêu dữ liệu đã rời hệ thống? |
| tenant.context.mismatch | Requested/effective/resource tenant không nhất quán | Có dấu hiệu giả mạo hoặc lỗi context không? |
| delegation.used | Quyền support/admin cross-tenant được dùng | Ai truy cập tenant khác, theo grant nào? |

Với read stream hoặc export lớn, ghi nhận thời điểm bắt đầu và hoàn tất/cancel, số record/byte thực tế và kết quả. Không ghi một sự kiện read.completed ngay khi mới nhận request nếu dữ liệu chưa được trả.

## 7. Những tín hiệu phát hiện quan trọng

### Actor tenant khác resource tenant

Đây là tín hiệu trực tiếp nhất. So sánh tenant context đã xác minh của actor với tenant owner của object. Nếu khác nhau, kiểm tra delegation hoặc shared-resource policy. Không có grant hợp lệ thì tạo security finding.

### Nhiều object ID bị thử trong thời gian ngắn

Actor thử liên tục nhiều object trong cùng resource type, đặc biệt khi nhận 404/403 xen kẽ, có thể đang dò ID hoặc tìm object thuộc tenant khác. Dùng route template và object reference pseudonymized để đếm số lượng khác biệt.

### Một actor chạm nhiều tenant bất thường

User bình thường thường hoạt động trong một hoặc một số tenant được cấp. Một actor bất ngờ truy cập hàng chục tenant, nhất là qua endpoint dữ liệu nhạy cảm, có thể là token misuse, lỗi tenant resolution hoặc quyền bị cấp quá rộng. Với service account và support role, baseline có thể khác.

### Denied attempts tăng đột biến

Tăng số lần TENANT_SCOPE_MISMATCH, OBJECT_OUT_OF_SCOPE hoặc TENANT_MEMBERSHIP_MISSING có thể cho thấy client lỗi, integration sai hoặc enumeration. Kết hợp số object khác nhau, số tenant khác nhau và identity để phân loại.

### Successful access thiếu policy evidence

Nếu có object.read.completed nhưng không tìm thấy decision event tương ứng, cần điều tra đường bypass, instrumentation thiếu hoặc event bị mất. Với object nhạy cảm, đây là tín hiệu quan trọng ngay cả khi không có 403.

### Export/read volume bất thường

Một actor có thể chỉ truy cập object mà họ được phép xem nhưng export khối lượng lớn hoặc đọc liên tục nhiều tenant. So sánh record count, bytes, data classification, thời gian và baseline của actor/tenant.

## 8. Quy tắc phát hiện và ngưỡng cảnh báo

Ngưỡng phải được hiệu chỉnh theo traffic, loại endpoint, role và mức nhạy cảm dữ liệu. Các con số dưới đây là điểm khởi đầu để thử nghiệm, không phải giá trị mặc định phù hợp cho mọi hệ thống.

| Rule | Điều kiện gợi ý | Mức ưu tiên ban đầu |
|---|---|---|
| Cross-tenant allow without grant | Decision ALLOW hoặc data access thành công, actor tenant khác resource tenant, không có delegation hợp lệ | Critical |
| Repeated cross-tenant deny | Từ 5 object khác nhau trong 5 phút bởi một actor | Medium/High |
| Multi-tenant probing | Một actor thử object thuộc từ 3 tenant trở lên trong 10 phút | High |
| Object enumeration | Từ 20 object reference khác nhau trên một route trong 2 phút | Medium/High |
| Missing decision event | Data access nhạy cảm không có authorization decision tương ứng | High |
| Bulk read/export anomaly | Record count/bytes vượt baseline hoặc quota của actor/tenant | Medium/High |
| Delegation misuse | Cross-tenant access bằng grant hết hạn, sai scope hoặc thiếu purpose | Critical |
| Repeated tenant mismatch across services | Cùng actor/client có mismatch trên nhiều service | High |

Không tạo alert Critical cho mọi request 404 hoặc mọi mismatch do người dùng gõ nhầm ID. Cần kết hợp kết quả, số lượng object, tenant, data classification, quyền actor, tốc độ và lịch sử. Một lần truy cập thành công trái phép có thể quan trọng hơn hàng nghìn lần bị từ chối.

## 9. Ví dụ logic phát hiện

### Phát hiện successful cross-tenant access

Pseudocode:

~~~text
for each object.read.completed or object.write.completed:
    if actor.tenant != resource.tenant:
        if not delegation.is_valid:
            alert(
                severity = CRITICAL,
                reason = "CROSS_TENANT_ACCESS_SUCCEEDED"
            )
~~~

Điều kiện delegation.is_valid phải được xác minh từ grant server-side: actor, tenant đích, resource/action scope, purpose, approver nếu cần, thời hạn và trạng thái thu hồi. Không chấp nhận một boolean isAdmin hoặc support=true do client gửi.

### Phát hiện enumeration theo actor

~~~sql
SELECT
    actor_subject_ref,
    route_template,
    COUNT(DISTINCT object_ref) AS object_count,
    COUNT(*) AS attempts,
    COUNT(DISTINCT resource_tenant_ref) AS tenant_count
FROM security_access_events
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
  AND decision = 'DENY'
  AND reason_code IN (
      'TENANT_SCOPE_MISMATCH',
      'OBJECT_OUT_OF_SCOPE',
      'TENANT_MEMBERSHIP_MISSING'
  )
GROUP BY actor_subject_ref, route_template
HAVING COUNT(DISTINCT object_ref) >= 5;
~~~

Đây là SQL minh họa. Hệ thống SIEM/stream processor có thể dùng window aggregation tương đương. Bổ sung điều kiện theo tenant, client ID, resource type và severity. Tránh nhóm theo raw user-supplied ID hoặc raw URL.

### Phát hiện truy cập không có decision event

~~~text
join object_access_events with authorization_decision_events
  on trace_id + resource_ref + action
within allowed correlation window

alert if:
  access.outcome == "SUCCESS"
  and decision event is missing
  and resource.classification in ("confidential", "restricted")
~~~

Trong thực tế, join cần xử lý asynchronous trace, retries, batch access và event ordering. Nên dùng request/job ID cùng một authorization decision ID để liên kết chắc chắn hơn chỉ dựa vào timestamp.

## 10. Phân biệt cross-tenant hợp lệ và bất thường

Một số hoạt động cần truy cập nhiều tenant:

- Support engineer xử lý ticket được khách hàng yêu cầu.
- Platform operator thực hiện break-glass trong sự cố.
- Billing service tổng hợp usage của nhiều tenant theo nhiệm vụ được cấp.
- Shared catalog hoặc dữ liệu công khai được dùng chung.
- Tenant A chia sẻ một resource cụ thể với tenant B.

Các trường hợp này cần mô hình delegation/grant rõ ràng. Một grant nên có:

| Thuộc tính | Ý nghĩa |
|---|---|
| Grant ID | Định danh có thể audit |
| Actor/service | Principal được phép truy cập |
| Target tenant/resource | Phạm vi tenant/object được phép |
| Actions | Read, update, export hoặc action cụ thể |
| Purpose/ticket | Lý do nghiệp vụ hoặc incident |
| Approver | Người/quy trình phê duyệt nếu cần |
| Valid from/to | Thời hạn hiệu lực |
| Revocation state | Có bị thu hồi hay không |
| Policy version | Quy tắc đã dùng để cấp quyền |

Alert rule phải kiểm tra grant tại thời điểm access. Không whitelist toàn bộ support role hoặc service account khỏi phát hiện cross-tenant; điều đó có thể che giấu việc credential bị lạm dụng. Nên phân biệt access hợp lệ với access ngoài scope của grant.

## 11. Phát sự kiện tại authorization enforcement point

Event cần được tạo ở nơi ứng dụng có đủ thông tin và policy vừa được đánh giá. Ví dụ một service method có thể nhận principal, tenant context, resource metadata và action:

~~~java
public record AccessDecisionEvent(
    String decisionId,
    String actorRef,
    String actorTenantRef,
    String resourceRef,
    String resourceTenantRef,
    String action,
    String decision,
    String reasonCode,
    String policyId,
    String policyVersion,
    String traceId
) {}

public AccessDecision authorize(
        Principal actor,
        TenantContext tenant,
        Invoice invoice,
        String action) {

    boolean sameTenant = tenant.id().equals(invoice.tenantId());
    boolean sameTenantAllowed = sameTenant
        && permissionPolicy.allows(actor, tenant, invoice, action);
    boolean delegated = !sameTenantAllowed && delegationPolicy.allows(
        actor, invoice.tenantId(), invoice.id(), action);

    boolean allowed = sameTenantAllowed || delegated;
    String reason = sameTenantAllowed
        ? "SAME_TENANT_ALLOWED"
        : delegated ? "VALID_DELEGATION"
        : sameTenant ? "ACTION_NOT_ALLOWED" : "TENANT_SCOPE_MISMATCH";
    String decisionId = UUID.randomUUID().toString();

    AccessDecision decision = new AccessDecision(
        decisionId, allowed, reason, "invoice-tenant-isolation", "12");

    auditPublisher.publish(new AccessDecisionEvent(
        decisionId,
        idPseudonymizer.actorRef(actor.subject()),
        idPseudonymizer.tenantRef(tenant.id()),
        idPseudonymizer.objectRef(invoice.id()),
        idPseudonymizer.tenantRef(invoice.tenantId()),
        action,
        allowed ? "ALLOW" : "DENY",
        reason,
        decision.policyId(),
        decision.policyVersion(),
        traceContext.currentTraceId()
    ));

    if (!allowed) {
        throw new AccessDeniedException("Access denied");
    }
    return decision;
}
~~~

Đây là ví dụ khái niệm, cần điều chỉnh theo model và framework. Quyền cùng tenant vẫn phải kiểm tra action/object policy; tenant match không tự cấp mọi quyền. Với delegated access, delegationPolicy phải trả về grant đã xác minh và có thể ghi grantId/purpose vào event. Với tài nguyên shared, policy cần một nhánh riêng thay vì giả định mọi khác tenant đều bị cấm.

Không chỉ log trong controller vì service có thể được gọi từ message consumer, scheduled job hoặc service khác. Nên đặt instrumentation tại policy/service boundary dùng chung để giảm nguy cơ một đường gọi bị bỏ sót.

## 12. Gắn event authorization với data access

Để phát hiện access thành công, cần ghi nhận thao tác đã thực sự hoàn tất. Ví dụ:

~~~java
public void recordReadCompleted(
        Principal actor,
        TenantContext tenant,
        Invoice invoice,
        int recordCount,
        long responseBytes,
        String decisionId) {

    auditPublisher.publish(new ObjectAccessCompletedEvent(
        UUID.randomUUID().toString(),
        "object.read.completed",
        idPseudonymizer.actorRef(actor.subject()),
        idPseudonymizer.tenantRef(tenant.id()),
        idPseudonymizer.objectRef(invoice.id()),
        idPseudonymizer.tenantRef(invoice.tenantId()),
        "invoice.read",
        decisionId,
        "SUCCESS",
        invoice.classification(),
        recordCount,
        responseBytes,
        traceContext.currentTraceId()
    ));
}
~~~

Chỉ ghi SUCCESS sau khi thao tác dữ liệu/response đã đạt điểm hoàn tất được định nghĩa. Nếu stream bị client hủy, có thể ghi PARTIAL/CANCELLED cùng bytes/records đã gửi nếu có thể đo chính xác. Không ghi nội dung invoice vào event.

Với query trả nhiều object, event có thể ghi aggregate: tenant scope, resource type, số object, classification cao nhất và số byte. Nếu phát hiện tenant mismatch trong batch, ghi riêng các object sai phạm hoặc một finding tổng hợp có reference để điều tra.

## 13. Bảo vệ dữ liệu định danh trong telemetry

Log tenant ID, user ID và object ID thô có thể tạo thêm một kho dữ liệu nhạy cảm. Nhưng nếu pseudonymize quá mạnh, đội điều tra lại không thể nối sự kiện cùng actor/object.

Một cách cân bằng là dùng HMAC có key quản lý tập trung để tạo reference ổn định theo scope:

~~~text
actorRef   = HMAC-SHA-256(K_actor_v3, tenant_scope || user_id)
tenantRef  = HMAC-SHA-256(K_tenant_v3, tenant_id)
objectRef  = HMAC-SHA-256(K_object_v3, resource_type || tenant_id || object_id)
~~~

Lợi ích:

- Có thể đếm và liên kết sự kiện cùng actor/object mà không ghi ID gốc.
- Khó đảo ngược reference nếu không có key.
- Key theo scope giúp tránh dùng một hash chung cho nhiều loại định danh.
- Có thể rotate key bằng version marker như v3.

HMAC không phải mã hóa có thể giải mã. Nếu analyst cần biết object thực tế, hãy cung cấp quy trình lookup có kiểm soát trong hệ thống nguồn, yêu cầu quyền phù hợp và audit việc tra cứu. Không dùng plain SHA-256 cho ID có không gian giá trị nhỏ hoặc dễ đoán vì có thể dò ngược bằng dictionary.

Giới hạn quyền đọc telemetry, mã hóa khi truyền/lưu, retention, export và truy cập theo vai trò. Không đưa access token, cookie, payload, email hoặc thông tin thanh toán vào event chỉ để thuận tiện điều tra.

## 14. Correlation qua gateway, service và background job

Cross-tenant access có thể xảy ra trong chuỗi nhiều service:

~~~text
Client
  -> API Gateway
  -> Orders API
  -> Billing Service
  -> Database
  -> Async Worker
~~~

Mỗi service có thể tạo log riêng. Để ghép được sự kiện, hãy truyền correlation context đã chuẩn hóa:

- Trace ID theo W3C Trace Context hoặc chuẩn tracing đã chọn.
- Request ID do server tạo/kiểm tra.
- Authorization decision ID.
- Job ID/message ID cho luồng bất đồng bộ.
- Parent/causation ID để nối event phát sinh từ event trước.
- Actor/service identity đã xác minh và delegation reference.

Trace ID không phải credential và không chứng minh identity. Không dùng trace ID làm khóa duy nhất nếu một request có nhiều object hoặc nhiều quyết định authorization. Cần decision ID và resource reference để ghép chính xác.

Với message queue, consumer phải nhận tenant/actor context từ message envelope có nguồn gốc đáng tin cậy. Không tin tenantId chỉ vì nó nằm trong JSON message; xác minh producer identity, schema, chữ ký/ACL hoặc nguồn outbox theo kiến trúc. Ghi lại cả original actor và executing service để điều tra ai yêu cầu và workload nào thực thi.

## 15. Metric, log, trace và audit có mục đích khác nhau

| Loại dữ liệu | Mục đích | Nội dung phù hợp |
|---|---|---|
| Metrics | Theo dõi xu hướng và cảnh báo nhanh | Count theo decision, reason code, service, route template, resource type |
| Security logs | Tìm kiếm và phân tích pattern | Actor/object pseudonym, tenant ref, action, decision, timestamp |
| Audit trail | Chứng minh ai làm gì trên dữ liệu | Principal, resource, action, outcome, policy/grant và thời điểm theo retention |
| Distributed traces | Theo dõi request qua service | Trace/span, decision ID, route, dependency và latency đã lọc |

Không đưa raw user ID, object ID hoặc tenant ID vào metric label có cardinality cao. Điều đó có thể làm hệ thống metrics phình to hoặc mất ổn định. Dùng label có tập giá trị giới hạn như service, route template, action, decision, reason code và resource type; giữ reference chi tiết trong log/audit có kiểm soát.

Không coi sampled trace là audit trail. Trace có thể bị sampling hoặc retention ngắn; sự kiện bảo mật quan trọng cần kênh audit bền vững riêng.

## 16. Alert severity và cách ưu tiên

Severity nên dựa vào kết quả, độ nhạy dữ liệu, số lượng object, phạm vi tenant, actor privilege và delegation:

| Severity | Điều kiện ví dụ | Hành động |
|---|---|---|
| Critical | Cross-tenant read/write/export thành công, không có grant hợp lệ; data restricted bị truy cập | Incident security ngay, bảo toàn evidence, cô lập/revoke theo playbook |
| High | Nhiều tenant/object bị dò; grant hết hạn vẫn được dùng; thiếu decision event cho dữ liệu nhạy cảm | Điều tra ưu tiên, xác minh actor và policy path |
| Medium | Nhiều denied mismatch, enumeration pattern, bulk read tăng bất thường | Triage theo actor/tenant/route, liên hệ owner khi cần |
| Low/Info | Một số mismatch đơn lẻ, lỗi client hoặc hoạt động đã được giải thích | Theo dõi trend, cải thiện client/policy hoặc allowlisted workflow |

Một successful cross-tenant access trái phép nên tạo finding ngay cả khi chỉ có một object. Với denied attempts, cần aggregation và baseline để tránh alert fatigue. Không tự động khóa toàn bộ tenant chỉ từ một alert chưa được xác minh; containment cần theo playbook và mức độ chắc chắn.

## 17. Ví dụ alert query và rule

### Alert khi access thành công giữa tenant không có grant

~~~sql
SELECT
    occurred_at,
    actor_subject_ref,
    actor_tenant_ref,
    resource_tenant_ref,
    resource_type,
    object_ref,
    action,
    service,
    trace_id
FROM object_access_events
WHERE outcome = 'SUCCESS'
  AND actor_tenant_ref <> resource_tenant_ref
  AND delegation_grant_id IS NULL
  AND resource_classification IN ('confidential', 'restricted');
~~~

Trong hệ thống có shared resource hoặc delegated access, điều kiện cần join với policy/grant evidence thay vì chỉ kiểm tra grant ID có null hay không. Phải xác minh grant có hiệu lực đúng thời điểm, scope, action và resource.

### Alert theo burst denied access

~~~sql
SELECT
    actor_subject_ref,
    service,
    route_template,
    COUNT(*) AS denied_attempts,
    COUNT(DISTINCT object_ref) AS distinct_objects,
    COUNT(DISTINCT resource_tenant_ref) AS distinct_tenants
FROM authorization_decisions
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
  AND decision = 'DENY'
  AND reason_code = 'TENANT_SCOPE_MISMATCH'
GROUP BY actor_subject_ref, service, route_template
HAVING COUNT(DISTINCT object_ref) >= 5
    OR COUNT(DISTINCT resource_tenant_ref) >= 3;
~~~

Các ngưỡng cần hiệu chỉnh theo baseline. Với batch job hợp lệ, số object có thể rất lớn; cần nhận diện workload identity và policy scope trước khi phát cảnh báo.

### Alert khi data access không có authorization evidence

~~~text
for each sensitive object access event:
    require matching decision_id
    require decision == ALLOW
    require decision.resource_ref == access.resource_ref
    require decision.action covers access.action
    require decision policy context matches request context

if any requirement is missing:
    emit "AUTHORIZATION_EVIDENCE_GAP"
~~~

Nếu instrumentation không thể bảo đảm event ordering, dùng durable event ID/decision ID và cửa sổ correlation phù hợp. Không tạo false alert chỉ vì log đến trễ; nhưng cũng không bỏ qua gap quá thời hạn.

## 18. Phát hiện bất thường theo baseline

Ngưỡng cố định có thể không phù hợp giữa các actor. Một support engineer có thể hợp lệ truy cập nhiều tenant; một end-user bình thường có thể chỉ hoạt động trong một tenant. Nên xây baseline theo:

- Actor type: end-user, support, admin, service account, workload.
- Tenant size và số lượng object bình thường.
- Route/action: read detail, list, export, update, delete.
- Thời gian/ngày làm việc và lịch batch.
- Resource classification và data volume.
- Client ID, service identity và deployment environment.
- Grant/delegation scope và thời hạn.

Các tín hiệu bất thường có thể gồm:

- Actor lần đầu truy cập tenant hoặc resource type mới.
- Số tenant khác nhau tăng đột biến so với baseline.
- Nhiều object ID tuần tự hoặc có pattern enumeration.
- Tỷ lệ 404/403 tăng cao so với request thành công.
- Export lớn ngoài giờ hoặc từ client chưa từng dùng.
- Service account dùng quyền rộng hơn công việc thường lệ.
- Một request tạo chuỗi truy cập object khác tenant qua nhiều service.

Machine learning hoặc anomaly detection có thể bổ sung nhưng không nên là lớp duy nhất. Rule xác định cho successful unauthorized access và grant violation cần được giữ rõ ràng, có thể giải thích và kiểm thử.

## 19. False positives và chất lượng alert

False positive thường đến từ:

- Support/admin access hợp lệ nhưng thiếu grant metadata.
- Shared resource bị gán owner tenant không chính xác.
- Tenant migration hoặc merge đang diễn ra.
- Background worker thực thi thay mặt nhiều tenant nhưng event chỉ ghi service identity.
- Data replication, analytics hoặc backup đọc dữ liệu theo phạm vi platform.
- Event đến sai thứ tự hoặc thiếu correlation do sampling/lỗi pipeline.
- User đổi tenant context hợp lệ nhưng client gửi selector cũ.

Không giải quyết false positive bằng cách tắt rule hoặc whitelist toàn bộ role. Hãy:

1. Xác minh resource ownership và business model.
2. Bổ sung delegation/grant metadata có scope và expiry.
3. Gắn actor type và service purpose.
4. Sửa instrumentation để có actor tenant, resource tenant và decision ID.
5. Tạo exception có owner, lý do, thời hạn và review.
6. Đo precision/recall và theo dõi alert bị đóng vì nguyên nhân nào.

Mọi allowlist nên hẹp theo actor, resource, action, tenant và thời hạn. Wildcard “support được truy cập mọi tenant” sẽ che khuất credential misuse hoặc support account bị chiếm.

## 20. Dashboard giám sát tenant isolation

Một dashboard hữu ích nên có các nhóm:

**Tổng quan authorization**

- ALLOW/DENY theo service, route template và action.
- Tỷ lệ reason code như TENANT_SCOPE_MISMATCH, OBJECT_NOT_FOUND, MEMBERSHIP_MISSING.
- Xu hướng theo thời gian và môi trường.

**Cross-tenant signals**

- Successful cross-tenant access không có grant.
- Denied cross-tenant attempts theo actor/client.
- Số object và tenant khác nhau bị thử.
- Actor/service có hoạt động trên nhiều tenant ngoài baseline.

**Data exposure**

- Read/export count và bytes theo classification.
- Số object bị truy cập sau decision ALLOW.
- Data access không có decision evidence.
- Export bất thường và download thất bại.

**Delegation và platform operations**

- Grant đang active, sắp hết hạn và đã bị revoke.
- Cross-tenant access theo purpose/ticket/approver.
- Break-glass access và thời gian từ mở tới đóng.

Dashboard tổng quan nên dùng metric đã aggregate và label cardinality thấp. Drill-down sang log/audit dùng quyền riêng; không hiển thị raw PII hoặc object ID cho mọi người xem dashboard.

## 21. Quy trình triage khi nhận alert

Khi nhận alert cross-tenant, analyst nên làm theo thứ tự:

1. **Xác nhận loại event:** attempt bị từ chối hay data access thành công? Có object.read.completed, write.completed hoặc export event không?
2. **Xác định actor:** user/service nào, authentication method, client ID, session/token reference và tenant context nào?
3. **Xác định resource:** object type, tenant owner, classification, số lượng record/bytes và action.
4. **Kiểm tra delegation:** grant có tồn tại, đúng actor/tenant/object/action, còn hiệu lực và chưa bị revoke không?
5. **Nối request:** trace ID, decision ID, job/message ID, gateway log và service log.
6. **Xem pattern:** actor đã thử bao nhiêu object/tenant, trong bao lâu, có enumeration hoặc export không?
7. **Xác định data exposure:** response đã gửi bytes/records chưa, thay đổi đã commit chưa, có downstream copy/export không?
8. **Đánh giá phạm vi:** tenant nào, resource nào, service nào, thời điểm bắt đầu và cuối.
9. **Containment theo playbook:** revoke session/token/grant, disable credential, chặn route hoặc cô lập workload khi có đủ căn cứ.
10. **Bảo toàn evidence:** giữ event/log/audit/trace liên quan, kiểm soát access và retention.
11. **Thông báo và khắc phục:** theo quy trình incident response, xác định nghĩa vụ thông báo và sửa policy/code.
12. **Theo dõi sau xử lý:** xác minh không còn access, rule đã phát hiện đúng và không có đường bypass khác.

Không xóa log hoặc chỉ sửa record sau sự cố. Bảo toàn timeline, policy version, deployment version và evidence trước khi thay đổi cấu hình nếu tình huống cho phép.

## 22. Containment và phối hợp với authorization team

Monitoring chỉ phát hiện; containment cần phối hợp giữa security operations, service owner, identity team và platform team.

Các hành động có thể gồm:

- Thu hồi session, refresh token hoặc access token bị nghi ngờ.
- Tạm khóa service credential hoặc workload identity có dấu hiệu bị lạm dụng.
- Thu hồi delegation grant hoặc break-glass session.
- Tắt tạm endpoint/export path bị ảnh hưởng theo change/incident process.
- Siết tenant filter, repository query hoặc database row-level policy.
- Cô lập service hoặc giới hạn egress nếu nghi ngờ lateral movement.
- Chặn client/route có pattern enumeration, nhưng tránh gây ảnh hưởng toàn bộ tenant hợp lệ.

Sau containment, cần xác minh cả API layer, background consumer, scheduled task, export service, cache và data replica. Một endpoint đã được sửa không đảm bảo mọi đường đọc dữ liệu khác đều an toàn.

## 23. Kiểm thử phát hiện cross-tenant access

Test cần chứng minh cả prevention và detection. Dùng tenant A và tenant B với object riêng, user/service principal riêng và các trường hợp delegation hợp lệ.

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Same-tenant allow | User A đọc object A | ALLOW và access event có tenant match |
| Cross-tenant deny | User A đọc object B | DENY, reason code mismatch; không có successful access event |
| Cross-tenant success regression | Cố tình cấu hình policy sai trong test | Alert critical được phát khi object thực sự được trả |
| Tenant selector tampering | Đổi path/header tenant A sang B | Không tạo context B nếu user không có membership |
| Object ID enumeration | Thử nhiều object ID/tenant | Aggregation rule phát hiện burst |
| Valid support grant | Support agent truy cập object B với grant đúng scope | Event ghi grant/purpose; không phát alert trái phép |
| Expired/revoked grant | Dùng grant hết hạn hoặc đã revoke | DENY và alert delegation violation |
| Shared resource | Đọc resource platform/shared theo policy | Không bị coi nhầm là cross-tenant violation |
| Bulk export | Export lượng lớn ngoài baseline/quota | Event ghi count/bytes và rule cảnh báo |
| Missing decision | Data access không có decision ID | Alert authorization evidence gap |
| Async worker | Job thực thi thay mặt actor/tenant | Event giữ original actor, executing service và job ID |
| Privacy | Kiểm tra event/log | Không có token, payload hoặc PII thô ngoài policy |
| Pipeline failure | Audit broker/log store tạm lỗi | Có retry/buffer/durable path và alert khi mất event |

Test integration nên kiểm tra event thực tế được phát ra và tới pipeline, không chỉ mock phương thức logger. Có thể dùng test container cho broker/SIEM sink hoặc fake audit publisher có thể xác nhận schema và delivery behavior.

## 24. Độ tin cậy của audit pipeline

Nếu security event bị mất, rule phát hiện sẽ không hoạt động. Với sự kiện authorization và data access quan trọng, cần định nghĩa bảo đảm delivery:

- Phân biệt best-effort telemetry với security audit cần độ bền cao.
- Dùng outbox hoặc durable queue cho event gắn với giao dịch quan trọng khi phù hợp.
- Có retry, bounded buffer và backpressure; không để logging làm treo request vô hạn.
- Cảnh báo khi event publish thất bại, consumer lag hoặc schema bị reject.
- Gắn event ID và idempotency để chống duplicate.
- Giám sát clock skew và timestamp source giữa service.
- Giữ schema version và compatibility cho event consumer.
- Hạn chế quyền sửa/xóa audit event; dùng storage retention/immutability phù hợp.

Không âm thầm bỏ qua lỗi audit. Nếu không thể ghi security event quan trọng, hệ thống cần policy rõ: từ chối thao tác nhạy cảm, dùng durable local outbox hoặc chuyển sang chế độ hạn chế. Quyết định fail-open/fail-closed phụ thuộc mức độ rủi ro và tính sẵn sàng nghiệp vụ; phải được thiết kế, không để thư viện logging tự quyết định.

## 25. Checklist phát hiện truy cập object giữa tenant

- [ ] Mỗi request có actor identity và tenant context đã xác minh.
- [ ] Resource tenant được lấy từ metadata đáng tin cậy của object/data layer.
- [ ] Requested tenant được tách khỏi effective tenant và resource tenant.
- [ ] Authorization decision event có actor, action, resource, tenant, decision, reason và policy version.
- [ ] Data access event ghi thao tác thực tế, outcome, classification và record/byte count.
- [ ] Successful cross-tenant access không có grant hợp lệ tạo alert ưu tiên cao.
- [ ] Denied mismatch được aggregation để phát hiện enumeration mà không alert quá mức.
- [ ] Delegation/support/break-glass có grant ID, scope, purpose, approver, expiry và revocation.
- [ ] Shared resource và platform operation có policy/metadata riêng, không whitelist rộng.
- [ ] Object/user/tenant reference trong telemetry được pseudonymize hoặc bảo vệ theo data policy.
- [ ] Metrics không dùng raw ID làm label cardinality cao.
- [ ] Trace/request/decision/job ID liên kết được nhiều service và consumer.
- [ ] Audit pipeline có delivery monitoring, retry, schema version và retention.
- [ ] Alert severity dựa trên successful access, data classification, volume và actor context.
- [ ] Runbook triage xác minh data exposure, delegation và phạm vi ảnh hưởng.
- [ ] Test bao gồm cross-tenant deny/allow, enumeration, grant expiry, bulk export và missing decision.
- [ ] Monitoring không thay thế tenant-scoped query, object authorization hoặc database isolation.

## Kết luận

Phát hiện truy cập object giữa tenant đòi hỏi telemetry biết được cả actor tenant lẫn resource tenant, ghi lại quyết định authorization và xác nhận thao tác dữ liệu thực tế. Hãy phát hiện riêng các attempt bị từ chối, các successful access không có grant, pattern enumeration, bulk read/export và khoảng trống giữa policy decision với data access. Delegation hợp lệ phải có scope, purpose, approver và expiry có thể kiểm chứng; telemetry cần pseudonymize định danh, giữ correlation và bảo vệ audit pipeline. Khi rule, dashboard, test và incident runbook được nối với enforcement point, đội vận hành có thể nhận ra cross-tenant exposure sớm và điều tra bằng evidence đáng tin cậy.
