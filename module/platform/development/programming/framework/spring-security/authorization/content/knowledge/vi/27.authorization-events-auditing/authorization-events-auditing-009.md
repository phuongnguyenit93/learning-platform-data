# Phát hiện hành vi dò tài nguyên, bị từ chối lặp lại và vượt phạm vi quyền

> **Module:** Spring Security – authorization. **Chủ đề cha:** Sự kiện và audit. Bài này hướng dẫn nhận biết, ghi nhận, tổng hợp và xác minh các hành vi bất thường liên quan đến quyền truy cập: dò nhiều tài nguyên không thuộc quyền, bị từ chối liên tục, và thử thao tác vượt vai trò/tenant/scope được cấp. Ví dụ sử dụng Java 17+, Spring Boot 3.x / Spring Security 6.x trên Servlet, kết hợp audit event, quy tắc phát hiện theo cửa sổ thời gian và JUnit 5.

## 1. Mục tiêu học tập và ranh giới bảo mật

Sau khi thực hành, bạn cần trả lời được:

1. **Ai** thực hiện yêu cầu, tại **thời điểm nào**, trên **nhóm tài nguyên nào**, với **hành động** gì, được **cho phép hay từ chối**, bởi **chính sách** nào?
2. Một người dùng vô tình gọi sai tài nguyên một lần khác gì với một phiên liên tục thử hàng chục ID trong vài phút?
3. Khi user thuộc tenant A thử đọc dữ liệu tenant B, hoặc tài khoản thường liên tục gọi chức năng quản trị, tín hiệu “vượt phạm vi quyền” lấy từ đâu?
4. Làm sao dùng sự kiện của Spring Security mà vẫn không lưu token, cookie, dữ liệu nhạy cảm hoặc toàn bộ đường dẫn chứa định danh cá nhân?
5. Làm sao tránh cảnh báo trùng, giảm báo động giả, kiểm tra detector bằng dữ liệu có thể tái lập và vận hành khi có nhiều ứng dụng/instance?

Phải giữ hai cơ chế tách biệt về trách nhiệm:

- **Enforcement (ngăn chặn):** Spring Security và chính sách nghiệp vụ quyết định request có được phép hay không **ở thời điểm truy cập**. Quyền theo tenant/owner/role vẫn phải được kiểm tra ở HTTP và/hoặc method/đối tượng.
- **Detection/Audit (quan sát):** các sự kiện từ quyết định đó được ghi nhận và tương quan để tìm mẫu đáng ngờ. Một detector bị tắt hoặc audit sink không sẵn sàng **không được khiến request vốn bị từ chối trở thành hợp lệ**.

Một cảnh báo chỉ cho biết **dấu hiệu đáng kiểm tra**, không phải bằng chứng chắc chắn người dùng đang tấn công.

## 2. Ba mẫu hành vi phải phân biệt

### 2.1. Dò tài nguyên (resource enumeration / ID probing)

Ví dụ API:

```http
GET /api/tenants/acme/invoices/1001
GET /api/tenants/acme/invoices/1002
GET /api/tenants/acme/invoices/1003
```

Một tài khoản chỉ có quyền với hóa đơn 1001 nhưng thử liên tục các `invoiceId` khác. Điều đáng chú ý không chỉ là số lượng 403, mà còn là **số tài nguyên khác nhau** được truy cập trái quyền trong một cửa sổ thời gian.

Tín hiệu mạnh hơn khi kết hợp:

- Một principal hoặc client có nhiều **resource key khác nhau** bị từ chối.
- Các ID có vẻ liên tiếp/tăng đều hoặc được thử nhanh (phát hiện ở pipeline nội bộ, tránh log raw ID).
- Nhiều object trong các tenant khác nhau.
- Tỷ lệ deny tăng mạnh so với baseline của chính API hoặc user.
- Một chuỗi 403/404 liên quan đến tài nguyên sau các lần truy cập hợp lệ ít ỏi.

Đây là dạng rủi ro gần với **Broken Object Level Authorization (BOLA/IDOR)**. Tuy nhiên, **dò tài nguyên không đồng nghĩa hệ thống đã bị BOLA**: nếu policy luôn từ chối đúng, request chỉ là hành vi nghi vấn; nếu API trả 200 cho dữ liệu của người khác, đó là **lỗ hổng enforcement** mà chỉ nhìn sự kiện deny có thể không phát hiện được.

### 2.2. Bị từ chối lặp lại

Một tài khoản gửi 12 yêu cầu bị từ chối vào `/api/admin/reports` trong 3 phút. Các nguyên nhân khả dĩ: cố nâng quyền, script thử endpoint, UI cache quyền cũ, hệ thống gọi API với scope lỗi thời hoặc user vừa bị thu hồi quyền.

**Chỉ đếm tổng HTTP 4xx là không đủ**. 400 do validation, 401 do thiếu xác thực, 403 do phân quyền và 404 do không tồn tại tài nguyên có ý nghĩa khác nhau:

| Tín hiệu | Ý nghĩa và cách dùng |
| --- | --- |
| `AuthorizationDeniedEvent` / kết quả deny của policy | Nguồn trực tiếp cho một quyết định phân quyền không thành công |
| HTTP 403 | Tín hiệu kết quả web; có thể phát sinh từ filter, method, policy hoặc ứng dụng; không mặc định có đủ lý do |
| HTTP 401 | Tập trung ở authentication/credential; nên tương quan với audit đăng nhập, không gộp thành “thiếu quyền” |
| HTTP 404 | Có thể là tài nguyên không tồn tại **hoặc** ứng dụng cố giấu sự tồn tại của tài nguyên không được phép; cần ngữ cảnh policy |
| HTTP 429 | Rate limiter đã hạn chế tần suất, không chứng minh trước đó có lỗi authorization |
| 2xx | Một request thành công; phải kiểm tra đúng scope/owner chứ không tự coi mọi 2xx là an toàn |

### 2.3. Vượt phạm vi quyền (scope / tenant / role boundary probing)

Ví dụ:

- User tenant `north` yêu cầu bản ghi tenant `south`.
- Tài khoản `ROLE_USER` cố gọi hành động `/api/admin/users/{id}/disable`.
- Token chỉ có scope `reports:read` được dùng cho `reports:write`.
- Tài khoản có quyền đọc dữ liệu của mình thử truy cập dữ liệu của đồng nghiệp.

Đây là dấu hiệu cần thêm **ngữ cảnh quyền cụ thể**:

```text
actor   = principal đã xác thực trên server
action  = invoices.read
scope   = tenant:north (theo claims/DB đã được xác minh)
target  = invoice thuộc tenant:south (theo DB đáng tin)
result  = DENY
reason  = TENANT_SCOPE_MISMATCH
```

Không suy ra `TENANT_SCOPE_MISMATCH` chỉ vì URL có tên tenant khác hoặc vì client tự gửi header `X-Tenant`. Mã lý do phải đến từ **authorization policy đáng tin**, sau khi đối chiếu subject/tenant/owner và dữ liệu server. Trường hợp thiếu role được phân loại `PRIVILEGED_OPERATION_DENIED` hoặc `MISSING_AUTHORITY`; phân biệt rõ với `INVALID_CREDENTIALS`.

## 3. Kiến trúc: từ quyết định quyền đến cảnh báo

```text
HTTP client
    │ request + credential
    ▼
Spring Security FilterChain
    ├─ Authentication (ai đang gọi?)
    ├─ AuthorizationFilter / AuthorizationManager
    └─ DispatcherServlet → controller → @PreAuthorize / policy theo object
                                  │
                 ALLOW / DENY (enforcement)
                                  │
                 AuthorizationDeniedEvent (khi có publisher)
                                  │
                  Audit event collector / outbox
                                  │
                  chuẩn hóa + che định danh + dedup
                                  │
                  luồng sự kiện / kho audit bảo vệ
                                  │
          sliding window + distinct resource + scope reason
                                  │
                 alert → triage → kiểm tra → ứng phó
```

**Thời điểm quan trọng:** event deny mô tả **quyết định quyền**. HTTP status cuối cùng do lớp web quyết định, có thể là 401/403/404 tùy policy và lớp xử lý lỗi. Nếu cần lưu cả hai, phải ghép hai tín hiệu bằng một `requestId` do **server tạo**, và chỉ lấy status sau khi response đã xử lý. Không khẳng định `AuthorizationDeniedEvent` tự có đầy đủ URL, response status hoặc mã lý do tenant.

Trong hệ thống phân tán, request có thể qua gateway → service A → service B. Cần `traceId` để tương quan và `eventId` để dedup; không cộng các lần một lỗi được ghi nhận ở 3 tầng thành 3 lần cố ý truy cập. Luồng audit có thể theo at-least-once, nên sự kiện phải có ID ổn định và consumer xử lý lặp idempotent.

## 4. Thiết kế audit record phục vụ phát hiện

Một audit record đã **chuẩn hóa** có thể có dạng:

```json
{
  "schemaVersion": 1,
  "eventType": "AUTHORIZATION_DENIED",
  "eventId": "evt-6e37f7ce",
  "occurredAt": "2026-11-05T08:12:09Z",
  "requestId": "req-c09d2",
  "traceId": "trace-a16c",
  "service": "billing-api",
  "layer": "METHOD",
  "actorKey": "hmac:9a8b...",
  "clientKey": "hmac:70d1...",
  "actorClass": "AUTHENTICATED_USER",
  "routeTemplate": "/api/tenants/{tenantId}/invoices/{invoiceId}",
  "operation": "invoice.read",
  "targetType": "invoice",
  "targetKey": "hmac:fc71...",
  "decision": "DENY",
  "policyReason": "TENANT_SCOPE_MISMATCH",
  "httpStatus": 403
}
```

Đây là **dữ liệu minh họa**, không phải một payload mà Spring Security xuất ra tự động. Muốn có `policyReason` chi tiết, ứng dụng phải gắn nó khi đánh giá policy nghiệp vụ; muốn có `httpStatus`, cần thu nhận từ kết quả web. Khi sử dụng một record duy nhất, pipeline phải xác định rõ trường nào là “chưa biết” thay vì gán giả.

| Trường | Cách lấy đáng tin | Lưu ý |
| --- | --- | --- |
| `eventId`, `requestId`, `traceId` | Tạo/tương quan phía server, middleware tracing | Không dùng duy nhất request ID do client tự khai làm khóa chống trùng |
| `actorKey` | Chủ thể từ `Authentication` xác thực, được pseudonymize | Không log password, token, cookie, raw principal/email nếu không cần |
| `clientKey` | Gateway đáng tin xác định client, sau đó pseudonymize | `X-Forwarded-For` chỉ đáng tin khi proxy được cấu hình đúng |
| `routeTemplate` | Mẫu do router/server xác định, ví dụ `/api/invoices/{id}` | Tránh ghi nguyên URL/query có ID hoặc dữ liệu cá nhân |
| `operation`, `targetType` | Tên nghiệp vụ có kiểm soát | Dùng enum/tên ổn định, không dùng chuỗi tự do từ request |
| `targetKey` | HMAC từ ID tài nguyên chuẩn hóa, cho phép đếm distinct | Tránh hash không khóa của ID đoán được; quản lý khóa |
| `policyReason` | Policy engine/authorization code nội bộ | Không suy ra lý do từ HTTP status một cách máy móc |
| `decision` | AuthorizationManager / policy | Ghi `DENY` có nguồn rõ ràng |
| `httpStatus` | Response cuối cùng sau khi xử lý web | Có thể thiếu trong event của method/non-HTTP |
| `occurredAt` | Đồng hồ server/collector UTC | Sai lệch đồng hồ cần được xét khi tổng hợp nhiều service |

**Bất biến dữ liệu audit:** đúng thời điểm; tối thiểu nhưng đủ truy vết; mã hóa truyển tải/lưu trữ; quyền truy cập audit riêng; thời gian giữ và quyền xóa theo chính sách. Không ghi `AuthorizationDeniedEvent#getObject().toString()` một cách trực tiếp, vì đối tượng có thể chứa cả request/argument nhạy cảm.

### 4.1. Vì sao dùng HMAC cho resource key?

Nếu chỉ dùng `SHA-256("1002")`, người có được log có thể tự hash toàn bộ dãy ID dễ đoán rồi đối chiếu. HMAC với khóa bí mật quản lý bên ngoài code giúp khó đoán lại ID từ digest. Chỉ lưu phần digest có đủ độ dài để đếm unique với tỷ lệ va chạm chấp nhận được; nếu dùng digest cắt ngắn phải đánh giá va chạm và chính sách bảo mật. Cùng một khóa/normalization trong một khoảng điều tra cho phép so sánh ID lặp lại; xoay khóa ảnh hưởng khả năng ghép lịch sử.

Không cần gửi raw ID sang detector nếu thành phần sở hữu policy đã tạo `targetKey`. Các quyền truy cập nhật ký, kiểm toán ai đọc log, và chống sửa/xóa trái phép vẫn cần thiết; HMAC không thay thế các kiểm soát này.

## 5. Lấy sự kiện từ Spring Security đúng cách

### 5.1. Bật phát sự kiện authorization denial

Trong Spring Security hiện đại, thêm bean `AuthorizationEventPublisher`. `SpringAuthorizationEventPublisher` sử dụng `ApplicationEventPublisher` của Spring và mặc định tập trung vào **sự kiện từ chối**; việc phát tất cả sự kiện allow có thể tạo tải rất lớn.

Ví dụ **`src/main/java/example/audit/AuthzEventConfig.java`**:

```java
package example.audit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class AuthzEventConfig {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new SpringAuthorizationEventPublisher(applicationEvents);
    }
}
```

Trong ứng dụng có cấu hình URL bằng `SecurityFilterChain`, vẫn cần giữ **`authorizeHttpRequests`** và authorization policy ở service. Bean publisher không thay cho việc đặt rules. Với method security, phương thức phải được gọi qua **Spring AOP proxy** để `@PreAuthorize` có hiệu lực; một phương thức tự gọi phương thức khác trong cùng object (`this.method()`) có thể bỏ qua proxy.

### 5.2. Listener lấy metadata an toàn

Ví dụ **`src/main/java/example/audit/DeniedEventListener.java`** dưới đây là một điểm nối có thể biên dịch trong Spring Boot project có Spring Security/SLF4J. Nó chỉ ghi **loại nguồn** và **tên method đã kiểm soát**, để xác nhận event hoạt động. Chưa đủ cho detector tài nguyên; phần enrichment được thực hiện ở mục sau.

```java
package example.audit;

import org.aopalliance.intercept.MethodInvocation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DeniedEventListener {

    private static final Logger log =
            LoggerFactory.getLogger(DeniedEventListener.class);

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        Authentication user = event.getAuthentication().get();
        String actorClass = user == null
                || user instanceof AnonymousAuthenticationToken
                || !user.isAuthenticated()
                ? "ANONYMOUS" : "AUTHENTICATED";

        Object secured = event.getObject();
        String layer;
        String operation;

        if (secured instanceof MethodInvocation invocation) {
            layer = "METHOD";
            operation = invocation.getMethod()
                    .getDeclaringClass().getSimpleName()
                    + "#" + invocation.getMethod().getName();
        } else {
            layer = "REQUEST_OR_OTHER";
            operation = "AUTHORIZATION_CHECK";
        }

        log.warn("securityEvent=AUTHORIZATION_DENIED layer={} "
                + "operation={} actorClass={}",
                layer, operation, actorClass);
    }
}
```

**Điều listener này không làm:** không phân biệt user A/B, không đọc raw method arguments, không bắt bừa toàn bộ URL, không xác định tenant chính xác và không tự sinh mã `TENANT_SCOPE_MISMATCH`. Khi muốn đo resource probing, adapter thực tế phải gửi **record đã làm giàu từ policy** đến audit collector thông qua một giao diện như `AuditSink.publish(record)`. Không được tự động log `invocation.getArguments()` hoặc `event.getObject()`.

Thực tế có thể cùng một request bị chặn ở HTTP layer **trước** khi tới method, nên không nhận event method. Ngược lại, method có quyền nội bộ bị từ chối có thể không có HTTP request. Cần test cả hai đường và định nghĩa nguồn event.

### 5.3. Gắn reason code từ policy nghiệp vụ

Ví dụ policy đọc tài liệu được thiết kế có điều kiện tenant/owner:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(String documentId) {
    // Logic đọc chạy sau khi policy cho phép.
}
```

Đoạn trên là **mảnh ghép minh họa**, phụ thuộc vào bean `documentPolicy` và `DocumentView` do ứng dụng cung cấp, không phải chương trình độc lập. `canRead` phải đối chiếu principal và **tenant/owner thực tế trong DB**, không tin `tenantId` do client truyền.

Một policy có thể đánh giá kết quả nội bộ theo dạng:

```text
ALLOW
DENY:RESOURCE_NOT_OWNED
DENY:TENANT_SCOPE_MISMATCH
DENY:MISSING_REQUIRED_AUTHORITY
DENY:PRIVILEGED_OPERATION
```

Một `boolean` đơn thuần trả về `false` khiến `AuthorizationDeniedEvent` thường **không mang rõ reason nghiệp vụ**. Để phân loại chính xác, dùng mô hình quyết định nội bộ `PolicyDecision(allow, reason)`, và phát một audit domain event khi deny, hoặc một enrichment contract có kiểm soát. Đừng tự suy diễn `reason` từ tên path, 403 hoặc principal role hiển thị.

**Tránh đếm đôi:** cùng request có thể tạo cả domain audit event và framework authorization event. Dùng `requestId + operation + decisionStage` hoặc `decisionId` sinh từ nơi đánh giá quyền để dedup. Quy ước rõ sự kiện nào là nguồn chuẩn cho alert.

### 5.4. Spring Boot Actuator auditing

Spring Boot Actuator hỗ trợ `AuditEventRepository`, `AuditEvent` và các audit listener liên quan đến authentication/authorization. Khi cung cấp bean repository, ứng dụng có thể lưu các sự kiện audit trong repository. `InMemoryAuditEventRepository` hữu ích khi phát triển, nhưng **không phù hợp làm kho điều tra production** vì giới hạn lưu trữ và mất dữ liệu khi restart. Nếu dùng `/actuator/auditevents`, phải kiểm soát quyền truy cập endpoint và nội dung trả về.

Framework audit hỗ trợ phần **thu thập/khả năng truy vấn**; detection theo distinct resource, scope reason hoặc pattern trên nhiều instance vẫn cần xử lý ứng dụng riêng. Không giả định một `AuditEventRepository` mặc định có đủ `targetKey`, tenant context, request correlation và cửa sổ sliding-window.

## 6. Quy tắc phát hiện: cửa sổ thời gian, số lượng và mức độ

Để hiểu cách detector hoạt động, sử dụng ngưỡng **giả định cho bài tập** (không phải best practice cố định của mọi hệ thống):

| Quy tắc | Điều kiện trong cửa sổ 5 phút | Mức gợi ý |
| --- | --- | --- |
| `REPEATED_DENIAL` | Ít nhất **6** quyết định deny riêng biệt cùng một subject | Warning |
| `RESOURCE_ENUMERATION` | Ít nhất **5 targetKey khác nhau** bị từ chối do truy cập resource | High |
| `SCOPE_BOUNDARY_PROBING` | Ít nhất **3** deny đã được policy phân loại vượt tenant/quyền đặc biệt | High |
| `MULTI_ACCOUNT_SOURCE` | Một clientKey liên quan đến nhiều subject bị deny | Correlation nâng cao, cần chống NAT giả |
| `POST_REVOKE_ACCESS` | Cố truy cập liên tiếp sau event revoke role/session | Correlation nâng cao, cần event IAM đáng tin |

**Mẫu đối chiếu:**

- Alice thử một ID sai: ghi event, **chưa cảnh báo**.
- Alice thử 7 lần cùng một ID: đủ `REPEATED_DENIAL` nhưng **chưa phải resource enumeration**.
- Alice thử 5 ID không thuộc quyền: đủ `RESOURCE_ENUMERATION`.
- Alice thử 3 lần tới tenant khác (reason từ policy): đủ `SCOPE_BOUNDARY_PROBING`.
- Nhiều nhân viên dùng chung NAT có 403: một IP không đủ để kết luận một actor, nên cảnh báo theo principal và kết hợp nguồn.
- Một client thật bị UI gửi lặp request do bug: detector có thể cảnh báo, người vận hành cần đối chiếu deployment/UI và baseline.

Đếm **request/decision duy nhất** theo khóa sinh từ server. Nếu nhiều event cùng request đến ở các tầng, dedup trước khi áp ngưỡng. Đối với tích hợp đa service, ngưỡng nên xem đồng thời subject, source, route/operation, tenant, môi trường và đặc tính lưu lượng bình thường; không dùng một limit cứng cho tất cả user và endpoint.

## 7. Java 17: detector sliding-window có thể kiểm thử độc lập

Ví dụ dưới đây tập trung vào **thuật toán quan sát**. Input `Denial` là bản ghi đã chuẩn hóa, chứa **subjectKey**, **targetKey** và **Reason** được tạo ở tầng đáng tin; nó không nhận raw HTTP request hay token. Chúng ta dùng:

- 5 phút gần nhất làm cửa sổ quan sát.
- 10 phút làm thời gian tránh gửi lại **cùng loại cảnh báo** cho subject.
- `requestId` giúp chống đếm trùng trong phần cửa sổ.
- `Clock` được inject để test thời gian mà không cần `Thread.sleep`.
- `synchronized` đảm bảo mỗi instance cập nhật bộ đếm nội bộ nhất quán.

### 7.1. Mã detector

**`src/main/java/example/audit/DenialPatternDetector.java`**

```java
package example.audit;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class DenialPatternDetector {

    public enum Reason {
        RESOURCE_FORBIDDEN,
        TENANT_SCOPE_MISMATCH,
        PRIVILEGED_OPERATION_DENIED,
        OTHER_DENIAL
    }

    public enum Pattern {
        REPEATED_DENIAL,
        RESOURCE_ENUMERATION,
        SCOPE_BOUNDARY_PROBING
    }

    public record Denial(
            String requestId,
            String subjectKey,
            String targetKey,
            Reason reason) {
        public Denial {
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(subjectKey, "subjectKey");
            Objects.requireNonNull(reason, "reason");
            if (requestId.isBlank() || subjectKey.isBlank()) {
                throw new IllegalArgumentException("Missing correlation key");
            }
        }
    }

    public record Alert(Pattern pattern, String subjectKey, int count) {}

    private record Observation(Instant at, Denial denial) {}

    private static final class Bucket {
        final Deque<Observation> window = new ArrayDeque<>();
        final Map<Pattern, Instant> lastAlert =
                new EnumMap<>(Pattern.class);
    }

    private static final Duration WINDOW = Duration.ofMinutes(5);
    private static final Duration COOLDOWN = Duration.ofMinutes(10);

    private final Clock clock;
    private final Map<String, Bucket> bySubject = new HashMap<>();

    public DenialPatternDetector(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public synchronized List<Alert> accept(Denial event) {
        Objects.requireNonNull(event);
        Instant now = clock.instant();
        Bucket bucket = bySubject.computeIfAbsent(
                event.subjectKey(), ignored -> new Bucket());

        Instant oldest = now.minus(WINDOW);
        while (!bucket.window.isEmpty()
                && bucket.window.peekFirst().at().isBefore(oldest)) {
            bucket.window.removeFirst();
        }

        // Một request chỉ được tính một lần trong cửa sổ.
        boolean duplicate = bucket.window.stream().anyMatch(
                x -> x.denial().requestId().equals(event.requestId()));
        if (duplicate) {
            return List.of();
        }

        bucket.window.addLast(new Observation(now, event));
        int totalDenials = bucket.window.size();

        Set<String> distinctTargets = new HashSet<>();
        int scopeDenials = 0;

        for (Observation observation : bucket.window) {
            Denial denial = observation.denial();

            if (denial.targetKey() != null
                    && !denial.targetKey().isBlank()
                    && (denial.reason() == Reason.RESOURCE_FORBIDDEN
                    || denial.reason() == Reason.TENANT_SCOPE_MISMATCH)) {
                distinctTargets.add(denial.targetKey());
            }

            if (denial.reason() == Reason.TENANT_SCOPE_MISMATCH
                    || denial.reason() == Reason.PRIVILEGED_OPERATION_DENIED) {
                scopeDenials++;
            }
        }

        List<Alert> alerts = new ArrayList<>();
        emit(bucket, now, event.subjectKey(), alerts,
                Pattern.REPEATED_DENIAL, totalDenials, 6);
        emit(bucket, now, event.subjectKey(), alerts,
                Pattern.RESOURCE_ENUMERATION, distinctTargets.size(), 5);
        emit(bucket, now, event.subjectKey(), alerts,
                Pattern.SCOPE_BOUNDARY_PROBING, scopeDenials, 3);
        return List.copyOf(alerts);
    }

    private static void emit(
            Bucket bucket, Instant now, String subject,
            List<Alert> alerts, Pattern pattern,
            int current, int threshold) {

        if (current < threshold) {
            return;
        }

        Instant last = bucket.lastAlert.get(pattern);
        if (last != null && now.isBefore(last.plus(COOLDOWN))) {
            return;
        }

        bucket.lastAlert.put(pattern, now);
        alerts.add(new Alert(pattern, subject, current));
    }
}
```

Đây là phiên bản **độc lập cho một process**: thuật toán chạy theo thời điểm server nhận event, không phụ thuộc timestamp do client cung cấp; các event đến lệch thứ tự vẫn được xếp theo thời điểm nhận. Với triển khai thật:

- Map `bySubject` cần TTL và hạn mức số subject để không tăng vô hạn; ví dụ này cố ý giữ đơn giản để học cơ chế.
- Các instance riêng không có bộ đếm chung; dùng stream processor/Redis có TTL/analytics store khi yêu cầu phát hiện toàn cụm.
- Dedupe bằng `requestId` là đủ cho fixture bài học; nhiều quyết định hợp lệ khác nhau trong cùng request có thể cần khóa `decisionId`. Chốt một mô hình đếm trước khi triển khai.
- Nguồn ID phải chuẩn hóa; kiểm tra giới hạn độ dài và allowlist cho các trường audit từ bên ngoài.
- `synchronized` không biến thành một hệ thống phân tán chịu tải lớn; production cần cửa sổ, backpressure, queue, durability, audit-retention riêng.
- Các cảnh báo được tạo **khi đạt ngưỡng**; không đóng băng tài khoản tự động chỉ vì một cảnh báo.

### 7.2. Unit test các mẫu hành vi

Ví dụ `src/test/java/example/audit/DenialPatternDetectorTest.java` dùng JUnit 5:

```java
package example.audit;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.Test;

import static example.audit.DenialPatternDetector.Pattern.*;
import static example.audit.DenialPatternDetector.Reason.*;
import static org.junit.jupiter.api.Assertions.*;

class DenialPatternDetectorTest {

    private DenialPatternDetector detector() {
        return new DenialPatternDetector(
                Clock.fixed(Instant.parse("2026-11-05T08:00:00Z"),
                        ZoneOffset.UTC));
    }

    private DenialPatternDetector.Denial denial(
            int request, String resource, DenialPatternDetector.Reason reason) {
        return new DenialPatternDetector.Denial(
                "request-" + request, "actor-hmac", resource, reason);
    }

    @Test
    void oneDeniedRequestIsOnlyAnEventNotAnAttackAlert() {
        var monitor = detector();
        assertTrue(monitor.accept(
                denial(1, "resource-A", RESOURCE_FORBIDDEN)).isEmpty());
    }

    @Test
    void repeatedDeniedRequestsTriggerAtSix() {
        var monitor = detector();
        for (int i = 1; i <= 5; i++) {
            assertTrue(monitor.accept(
                    denial(i, "same-resource", OTHER_DENIAL)).isEmpty());
        }
        List<DenialPatternDetector.Alert> alert =
                monitor.accept(denial(6, "same-resource", OTHER_DENIAL));

        assertEquals(1, alert.size());
        assertEquals(REPEATED_DENIAL, alert.get(0).pattern());
        assertEquals(6, alert.get(0).count());
    }

    @Test
    void fiveDistinctForbiddenResourcesTriggerEnumeration() {
        var monitor = detector();
        for (int i = 1; i <= 4; i++) {
            assertTrue(monitor.accept(
                    denial(i, "resource-" + i, RESOURCE_FORBIDDEN)).isEmpty());
        }
        var alerts = monitor.accept(
                denial(5, "resource-5", RESOURCE_FORBIDDEN));

        assertEquals(1, alerts.size());
        assertEquals(RESOURCE_ENUMERATION, alerts.get(0).pattern());
        assertEquals(5, alerts.get(0).count());
    }

    @Test
    void threeScopeViolationsTriggerScopeAlert() {
        var monitor = detector();
        for (int i = 1; i <= 2; i++) {
            assertTrue(monitor.accept(
                    denial(i, "target", TENANT_SCOPE_MISMATCH)).isEmpty());
        }
        var alerts = monitor.accept(
                denial(3, "target", TENANT_SCOPE_MISMATCH));

        assertEquals(1, alerts.size());
        assertEquals(SCOPE_BOUNDARY_PROBING, alerts.get(0).pattern());
        assertEquals(3, alerts.get(0).count());
    }

    @Test
    void sameRequestIsDeduplicated() {
        var monitor = detector();
        var first = denial(7, "resource-7", RESOURCE_FORBIDDEN);

        assertTrue(monitor.accept(first).isEmpty());
        assertTrue(monitor.accept(first).isEmpty());
        for (int i = 1; i <= 3; i++) {
            assertTrue(monitor.accept(
                    denial(i, "resource-" + i, RESOURCE_FORBIDDEN)).isEmpty());
        }
        // Có 4 request duy nhất, chưa phải 5 resource.
    }

    @Test
    void cooldownStopsIdenticalAlertFlood() {
        var monitor = detector();
        for (int i = 1; i <= 5; i++) {
            monitor.accept(denial(i, "same", OTHER_DENIAL));
        }
        assertEquals(1, monitor.accept(
                denial(6, "same", OTHER_DENIAL)).size());
        assertTrue(monitor.accept(
                denial(7, "same", OTHER_DENIAL)).isEmpty());
    }
}
```

Chạy trong Spring Boot Maven project có `spring-boot-starter-test`:

```bash
./mvnw test -Dtest=DenialPatternDetectorTest
```

**Kết quả kỳ vọng:** 6 test thành công, không cần kết nối DB/WebSocket. Đây là kiểm thử thuật toán, **chưa chứng minh** Spring Security phát sự kiện đúng hay audit sink production hoạt động. Cần bổ sung integration test.

### 7.3. Kiểm thử cửa sổ thời gian

Một vấn đề dễ bỏ sót: sau 5 phút không có deny mới, các sự kiện cũ phải hết hiệu lực; chỉ số deny không tăng mãi. Test nên cấp một `Clock` có thể tiến thời gian (ví dụ subclass `Clock` lưu `Instant` trong `AtomicReference`), gửi 5 deny ở mốc ban đầu, tiến 6 phút, gửi thêm một deny và kiểm tra **không** chạm ngưỡng 6. Sau 10 phút từ alert gần nhất có thể phát alert mới nếu cửa sổ sau đó đủ điều kiện. Không dùng `Thread.sleep` để test thời gian vì chậm và dễ flaky.

## 8. Tích hợp thực tế từ authorization policy đến detector

Ví dụ business policy cần trả “không có quyền đọc invoice” mà vẫn đảm bảo security enforcement:

```java
@PreAuthorize("@invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceView readInvoice(String invoiceId) {
    return invoiceRepository.loadView(invoiceId);
}
```

Đây là **mã tích hợp minh họa**, cần bean `invoicePolicy` và các kiểu `InvoiceView`/`invoiceRepository` của dự án để chạy. Trong policy:

1. Xác định tenant và authority của actor từ security context đã xác thực.
2. Tra cứu invoice theo ID từ nguồn đáng tin, xác định owner/tenant.
3. Ra quyết định allow/deny.
4. Khi deny, ghi `reason` có kiểm soát và `targetKey` đã HMAC; phát một domain audit event gắn `decisionId` hoặc truyền cho collector.
5. Trả kết quả deny cho Spring Security; không thay deny bằng allow để “tiện ghi audit”.

Một cách khác dùng riêng `AuthorizationDeniedEvent` của framework rồi enrichment từ request/method metadata. Tuy nhiên event kiểu tổng quát không đảm bảo đã có reason/target; khi thiếu thông tin, hãy phân loại `OTHER_DENIAL` và **không** kích hoạt rule dựa vào tenant nếu chưa biết thật.

### 8.1. Trường hợp authorization được xử lý ở nhiều tầng

Một request có thể gặp:

```text
HTTP AuthorizationFilter: ALLOW (có session)
Method @PreAuthorize: DENY (không có authority invoice:read)
Object policy: chưa chạy
HTTP response: 403
```

Cần log decision ở method đúng nguồn và chỉ đếm **một request bị deny**. Nếu HTTP layer deny trước, method chưa chạy, thiếu object/tenant key là điều bình thường. Không phát hai alert chỉ vì filter và global exception handler cùng ghi một 403. Dùng `requestId` + `decisionStage`/`decisionId` và thống nhất nơi canonical.

Một API có nhiều phương thức (REST, GraphQL, WebSocket STOMP) không thể chỉ lấy HTTP 403. Ví dụ STOMP `SUBSCRIBE` bị từ chối có thể đóng kết nối hoặc phát ERROR; authorization deny event và subscription metadata mới là nguồn phù hợp. Phải định nghĩa taxonomy theo giao thức, không gộp mọi thứ vào `httpStatus`.

### 8.2. Cần một tín hiệu độc lập cho truy cập thành công vượt quyền

Nếu một endpoint **thiếu authorization check**, nó có thể trả 200 và **không có deny event** dù đã lộ dữ liệu. Vì vậy:

- Test quyền theo đối tượng với hai user/tenant, cả case allow và deny.
- Kiểm tra cấu hình `denyAll` cho URL không được khai báo.
- Có audit riêng cho các thao tác rủi ro cao đã được phép: export hàng loạt, thay role, thay tenant, sử dụng quyền admin, download tài liệu nhạy cảm.
- Đối chiếu data access log có policy/owner với application decision; đừng dùng detector deny như phép kiểm tra BOLA duy nhất.

## 9. Tính toán cảnh báo trên kho sự kiện và metrics

Một query minh họa theo PostgreSQL khi pipeline đã chuẩn hóa, dedup và đưa vào bảng `authorization_audit`:

```sql
SELECT
    actor_key,
    COUNT(*) AS denied_requests,
    COUNT(DISTINCT target_key) FILTER (
        WHERE policy_reason IN (
            'RESOURCE_FORBIDDEN',
            'TENANT_SCOPE_MISMATCH'
        )
    ) AS distinct_forbidden_targets,
    COUNT(*) FILTER (
        WHERE policy_reason IN (
            'TENANT_SCOPE_MISMATCH',
            'PRIVILEGED_OPERATION_DENIED'
        )
    ) AS scope_denials
FROM authorization_audit
WHERE occurred_at >= now() - INTERVAL '5 minutes'
  AND event_type = 'AUTHORIZATION_DENIED'
GROUP BY actor_key
HAVING COUNT(*) >= 6
    OR COUNT(DISTINCT target_key) FILTER (
        WHERE policy_reason IN (
            'RESOURCE_FORBIDDEN',
            'TENANT_SCOPE_MISMATCH'
        )
    ) >= 5
    OR COUNT(*) FILTER (
        WHERE policy_reason IN (
            'TENANT_SCOPE_MISMATCH',
            'PRIVILEGED_OPERATION_DENIED'
        )
    ) >= 3;
```

**Giả định:** bảng được thiết kế đúng tên/cột, mỗi dòng đã đại diện cho một quyết định canonical và được dedup. Đây là ví dụ SQL truy vấn, không phải DDL schema hoặc giải pháp streaming production. Trong dữ liệu lớn cần index/partition phù hợp, xử lý late event, event-time window, khóa tenant/môi trường, và hạn chế cardinality.

**Metrics gợi ý:**

- `security_authorization_denials_total{service,operation,reason}`: counter theo nhãn hữu hạn, không gắn raw actor/URL/resource ID vào label.
- `security_audit_ingestion_lag_seconds`: độ trễ từ event đến kho.
- `security_audit_dropped_total{reason}`: số sự kiện bị mất/quá tải.
- `security_detector_alerts_total{pattern,severity}`: số cảnh báo sau dedup.
- Tỷ lệ deny/allow theo operation (nếu thu thập allow được thiết kế có sampling hoặc phạm vi rõ ràng).
- Phân phối distinct target trên mỗi actor để hiệu chỉnh threshold; nên tính trong store/stream job, không tạo mỗi actor thành một nhãn Prometheus.

Dùng trace để đào sâu một yêu cầu, metric để giám sát tổng quan, audit event để điều tra chuỗi quyết định. Không thay audit record có cấu trúc bằng một dòng log tự do.

## 10. Ma trận kiểm thử tích hợp: biết chắc sự kiện và cảnh báo đúng

Thiết lập fixture hai tenant `north`/`south`, 3 tài khoản `readerNorth`, `readerSouth`, `admin`. Mỗi tenant có một nhóm tài nguyên riêng. Đưa `AuditSink` và detector vào test cùng Spring Security thực để kiểm tra sự kiện, HTTP status và side effect.

| ID | Hành động | Kỳ vọng |
| --- | --- | --- |
| P01 | `readerNorth` đọc invoice thuộc `north` | Cho phép, không có deny; dữ liệu đúng scope |
| N01 | `readerNorth` đọc invoice thuộc `south` | Deny 403 (hoặc 404 che giấu theo policy); audit reason tenant mismatch, targetKey đã HMAC |
| N02 | Một user thử 5 invoice khác nhau không thuộc quyền trong 5 phút | Alert `RESOURCE_ENUMERATION` sau khi đủ 5 targetKey khác nhau |
| N03 | Một user gửi 6 request deny đến cùng một tài nguyên | Chỉ alert `REPEATED_DENIAL`, không nhầm thành distinct-resource probing |
| N04 | User thường thử 3 hành động quản trị | Alert `SCOPE_BOUNDARY_PROBING`; method/action thực sự bị ngăn |
| N05 | Một HTTP request bị log ở 2 tầng với cùng decisionId | Collector chỉ tính một lần |
| N06 | 5 deny rồi tiến Clock 6 phút, thêm 1 deny | Không báo lặp lại do các event cũ hết cửa sổ |
| N07 | 6 deny rồi thêm deny mới trong cooldown | Không spam cùng loại cảnh báo |
| N08 | Request đúng quyền nhưng resource thực sự không tồn tại | 404 nghiệp vụ, không tự đánh dấu tenant-scope attack |
| N09 | Token hết hạn / thiếu auth | Theo flow 401; audit authentication riêng, không gán nhầm thành BOLA |
| N10 | Mã client/UI lỗi gọi lại cùng endpoint nhiều lần | Có thể chạm repeated-deny, triage nhận diện false positive |
| N11 | Attempt bị deny khi audit sink unavailable | Quyền vẫn bị từ chối, request không được cho phép |
| N12 | User thu hồi quyền trong lúc session còn hoạt động | Các request tiếp theo bị từ chối, event reason phù hợp; không giữ quyền cũ |
| N13 | Attacker gửi ID có CRLF/giá trị rất dài | Log không bị injection, key/field được chuẩn hóa giới hạn độ dài |
| N14 | Hai user khác nhau qua cùng một NAT | Không nhập họ thành một actor chỉ dựa trên IP |
| N15 | Request không qua Spring Security / self-invocation service | Test phát hiện điểm mù event và bổ sung enforcement đúng |

**Kiểm tra đầy đủ một ca deny:** (1) HTTP/STOMP không cho phép hành động, (2) DB/broadcast không có side effect ngoài quyền, (3) audit event mang đúng actor/operation/reason từ server, (4) detector tăng đúng bộ đếm, (5) cảnh báo chỉ xuất hiện khi đủ điều kiện và (6) không có dữ liệu nhạy cảm trong body/log. Chỉ test `status().isForbidden()` hoặc chỉ test detector unit là chưa đủ.

## 11. Giảm false positive, bảo vệ người dùng và chất lượng cảnh báo

Các nguyên nhân bình thường gây nhiều deny:

- Frontend gửi các request từ giao diện chưa cập nhật khi admin vừa đổi quyền.
- Mobile SDK retry không phân biệt 403 vĩnh viễn với 5xx tạm thời.
- Cơ chế preload/prefetch gọi một loạt tài nguyên mà client không có quyền.
- Batch job dùng service account với scope thiếu.
- Proxy/client cùng IP do NAT; CDN hoặc gateway ghi clientKey không chuẩn.
- Test bảo mật, hệ thống giám sát hoặc scanner được ủy quyền.
- Cùng request bị log nhiều lần ở các service hoặc mỗi tầng bảo mật.
- Policy bị cấu hình lỗi sau deployment gây deny tăng đột biến đồng loạt.

**Chiến lược giảm nhiễu:**

1. Baseline riêng theo operation, vai trò, tenant, môi trường, khung giờ; theo dõi tỷ lệ tăng thay vì chỉ giá trị tuyệt đối.
2. Tách cá nhân đã xác thực, session, client/gateway; tương quan với nguồn IP **nhưng không lấy IP duy nhất làm danh tính**.
3. Dedup bằng ID đáng tin, xác định event canonical, xử lý retry và late event.
4. Phân loại reason rõ ràng; chỉ tính distinct target khi targetKey được chuẩn hóa và policy thật sự từ chối object access.
5. Áp dụng suppression có TTL/cooldown, giữ audit gốc dù không phát thêm alert.
6. Đánh giá hệ thống cập nhật quyền, deploy, migration và các incident đang diễn ra.
7. Điều chỉnh ngưỡng dựa trên precision, recall, thời gian phát hiện, chi phí điều tra; ghi version của rule để đối chiếu.
8. Tách mức cảnh báo: một deny là audit; nhiều deny là warning; nhiều tenant/role đặc quyền hoặc kết hợp dấu hiệu rò rỉ dữ liệu mới nâng mức khẩn cấp.

Đừng tự động khóa tài khoản khi có một alert từ IP chia sẻ; kẻ khác có thể lợi dụng để gây **denial of service** cho người vô tội. Các biện pháp can thiệp phải có ngưỡng, giới hạn tác dụng, cơ chế phục hồi và khả năng được rà soát.

## 12. Quy trình ứng phó khi detector cảnh báo

Một quy trình vận hành khả thi:

1. **Xác nhận tín hiệu:** lấy `eventId`, khung thời gian, tên rule và số lượng; đảm bảo dữ liệu đã dedup, không có log ingestion lỗi.
2. **Kiểm tra enforcement:** truy ngược quyết định và dữ liệu đã trả; có 200/rò rỉ ngoài quyền hay chỉ 403 đúng policy? Nếu policy thiếu, ưu tiên vá authorization.
3. **Tương quan bối cảnh:** request/trace từ nhiều service, authentication failures, đổi role/tenant, lịch deployment, hoạt động admin, lịch sử cùng actor.
4. **Đánh giá phạm vi:** bao nhiêu target/tenant/operation bị ảnh hưởng, có export hoặc thay đổi dữ liệu không; dùng log ít dữ liệu nhạy cảm nhất cần thiết.
5. **Phản ứng theo mức:** cảnh báo đội trực, yêu cầu xác thực lại, giảm tốc độ theo user/action, giới hạn endpoint nhạy cảm, thu hồi token nghi xâm phạm — theo chính sách vận hành và có phê duyệt phù hợp.
6. **Bảo toàn chứng cứ:** audit store có phân quyền/retention/kiểm tra integrity; lưu correlation IDs để điều tra. Không gắn token hay payload bí mật vào ticket.
7. **Rút kinh nghiệm:** cập nhật policy, test BOLA, threshold, metric thiếu, runbook; phân loại false positive và thời gian xử lý.

Nếu truy cập đã thành công trái quyền, đó là vấn đề **kiểm soát truy cập** cần xử lý và đánh giá ảnh hưởng; detection chỉ giúp tìm dấu vết. Nếu các request đều bị chặn, ưu tiên xác định nguồn bất thường mà không nhầm lẫn “cảnh báo” với “đã bị xâm nhập”.

## 13. Các lỗi thiết kế phổ biến

1. **Chỉ đọc access log HTTP 403 để quyết định attack.** Không có policy reason, actor/tenant đáng tin hay phân biệt 401/404.
2. **Chỉ nhìn `AuthorizationDeniedEvent` rồi mặc định đã có HTTP status.** Event của method không tự có response status và có thể chạy ngoài HTTP.
3. **Không bật event publisher.** Có listener nhưng không được feed dữ liệu như kỳ vọng; cần bean `AuthorizationEventPublisher` và integration test.
4. **Quên `@EnableMethodSecurity` hoặc gọi bằng `this.securedMethod()`.** Không có interception → có thể không có deny event dù thao tác cần bị chặn.
5. **Lấy mọi quyền từ header do client tự khai.** Scope/tenant cần xác thực từ token/DB và policy.
6. **Dùng hash thường cho ID dễ đoán.** Nên dùng HMAC với khóa được quản lý; không xuất raw ID vào log.
7. **Log toàn bộ `event.getObject()`/method arguments/token.** Có thể rò rỉ dữ liệu nhạy cảm, tạo nguy cơ log injection và làm kho audit trở thành mục tiêu.
8. **Gắn user ID hoặc resource ID thành Prometheus labels.** Cardinality bùng nổ; chỉ giữ label hữu hạn, điều tra chi tiết trong kho audit.
9. **Đếm mỗi event ở mọi tầng như một request tấn công.** Phải dedup request/decision.
10. **Dùng bộ đếm một instance nhưng cho rằng giám sát toàn cụm.** Scale-out cần state tập trung/stream processor hoặc cộng dồn đáng tin.
11. **Không test chính sách từ chối.** Detector chạy đúng nhưng endpoint vẫn lộ dữ liệu; cần test cross-tenant, role boundary và side effects.
12. **Không hạn chế tài nguyên của detector.** Kẻ tấn công có thể tạo vô hạn actor keys/target keys, gây đầy RAM hoặc nghẽn audit.
13. **Chặn người dùng tự động từ một IP cảnh báo.** NAT/VPN có thể làm nhiều người vô tội bị ảnh hưởng; cần điều tra và giảm mức can thiệp.
14. **Xem 404 luôn là dò ID hoặc xem mọi 2xx đều an toàn.** Cần tín hiệu authorization có ngữ cảnh và kiểm thử BOLA độc lập.
15. **Không kiểm tra thời gian giữ/audit access.** Càng nhiều dữ liệu định danh được lưu lâu, rủi ro nội bộ và tuân thủ càng cao.
16. **Để lỗi ghi audit làm thay đổi quyết định allow/deny.** Xây dựng hàng đợi, retry, circuit breaking và quy tắc vận hành rõ; không đảo kết quả security decision.

## 14. Checklist triển khai trong một dịch vụ Spring

- [ ] Có policy chặn truy cập theo resource/tenant/owner và admin action, không chỉ dựa vào URL.
- [ ] `@EnableMethodSecurity` hoạt động trên bean/proxy thật; thử cả allowed/denied paths.
- [ ] Có `AuthorizationEventPublisher` và integration test nhận `AuthorizationDeniedEvent` tại các tầng mong đợi.
- [ ] Phân biệt deny quyền với authentication failure, not-found, validation, rate-limit.
- [ ] Có audit schema chuẩn, `eventId`/`requestId`/`traceId` đáng tin, time UTC, operation/route template.
- [ ] Dùng subject/resource pseudonymized keys; không log token, cookie, credential hoặc raw method arguments.
- [ ] Có reason code được policy sinh ra, không suy diễn cross-tenant từ header/path tự khai.
- [ ] Có dedup, cửa sổ thời gian, số distinct target, rule version, cooldown và TTL cho state.
- [ ] Có test không có alert cho một deny đơn lẻ, alert đúng khi vượt ngưỡng và test reset cửa sổ.
- [ ] Có metric drop/lag, lưu trữ audit bảo vệ, phân quyền xem log và retention.
- [ ] Có runbook triage, điều tra false positive, kiểm tra side effects và response bất thường.
- [ ] Có chiến lược phát hiện toàn cụm nếu nhiều instance; không dựa duy nhất vào heap từng node.

## 15. Tài liệu tham khảo

- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html): `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher`, `AuthorizationDeniedEvent` và giới hạn của granted events.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interceptor và denied events.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): chính sách HTTP và quy tắc deny-by-default.
- [Spring Boot Actuator – Auditing](https://docs.spring.io/spring-boot/reference/actuator/auditing.html): `AuditEventRepository` và audit listener.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm soát quyền trên từng ID đối tượng.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): chọn sự kiện, lọc dữ liệu nhạy cảm, chống log injection, bảo vệ kho log và cảnh báo.
- [OWASP API Security Top 10 – Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/): phân quyền theo chức năng/role.

**Tiêu chí đạt:** hệ thống từ chối đúng truy cập ngoài quyền **và** tạo dấu vết audit đủ tin cậy để nhận biết các mẫu dò nhiều tài nguyên, bị từ chối lặp lại và thử vượt tenant/role. Cảnh báo được tính trên event đã chuẩn hóa/dedup, có ngưỡng và thời hạn cụ thể, được kiểm tra bằng test dương tính/âm tính, bảo vệ thông tin riêng tư và không thay thế chính sách phân quyền.