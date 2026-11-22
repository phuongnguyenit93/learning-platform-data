# Ai thực hiện thao tác trong Audit Logging (Java)

## 1. Câu hỏi “ai đã làm việc này?” có nghĩa gì?

Trong **audit logging**, câu hỏi **“Ai thực hiện thao tác?”** cần xác định **actor**: danh tính được xác thực hoặc được quy định rõ là vô danh/hệ thống, đã thực hiện hoặc ra lệnh cho một hành động có ý nghĩa bảo mật/nghiệp vụ. Một dòng log như `INFO User updated profile` chưa đủ làm dấu vết kiểm toán: chưa rõ chủ thể, đối tượng bị thay đổi, quyền thực tế, thời điểm hoặc kết quả cuối cùng.

Ví dụ:

```text
Người dùng user_42 đăng nhập thành công
    │
    ▼
Yêu cầu thay đổi vai trò của user_91
    │
    ▼
API kiểm tra quyền, cập nhật và commit
    │
    ▼
Audit event:
  actor.type=USER
  actor.id=user_42
  action=ASSIGN_ROLE
  target.type=USER
  target.id=user_91
  outcome=SUCCESS
```

Trong event trên, **user_42 là người thực hiện**, **user_91 là người bị tác động**. Một trường mơ hồ như `userId=user_91` có thể khiến điều tra viên hiểu sai.

Bài này tập trung vào cách trả lời đáng tin cậy:

- Chủ thể là **người dùng, tài khoản dịch vụ, tác vụ tự động hay caller vô danh**?
- Ai **khởi xướng**, ai dùng **credential thực thi**, ai bị **impersonate**, ai **phê duyệt**?
- Danh tính đến từ **security context/token đã xác minh** hay từ header client tự khai?
- Hành động **được yêu cầu, bị từ chối, đã commit hay còn chờ worker xử lý**?
- Actor ID có được lưu cùng issuer/tenant, target, event ID và request/job/trace ID để đối soát?
- Bản ghi có đủ tin cậy, toàn vẹn và được lưu đúng yêu cầu audit không?

**Actor không đồng nghĩa với IP, user-agent, thread name, logger name, request ID hoặc trace ID.** Các thông tin ấy có thể hỗ trợ điều tra nhưng không tự chứng minh danh tính người thực hiện.

## 2. Phân biệt actor, initiator, executor, subject, target và approver

Các từ `subject` hoặc `principal` có thể mang nghĩa khác nhau giữa IAM, Spring Security và nghiệp vụ. Audit schema nên **định nghĩa tường minh** các vai trò:

| Vai trò | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Actor / executor** | Danh tính thực hiện hành động tại ranh giới đang ghi event | `user_42` hoặc `svc_export` |
| **Initiator / requested_by** | Chủ thể khởi xướng chuỗi xử lý, nếu liên kết được xác minh | `user_42` yêu cầu export async |
| **Effective identity** | Credential/principal thực tế được dùng để gọi backend, đánh giá quyền | `svc_export` của worker |
| **Effective subject / acted-for user** | Tài khoản mà actor đang được phép thao tác thay | `user_91` trong phiên impersonation |
| **Target** | Tài nguyên hoặc tài khoản bị đọc/sửa/xóa | `report_17` hoặc `user_91` |
| **Approver** | Người đã chấp thuận một bước trong quy trình | `manager_7` |
| **Service/workload** | Ứng dụng/process phát event | `report-worker` |
| **Authentication source** | Issuer/phương thức đã xác minh actor | `idp_main`, `workload_identity` |
| **Correlation key** | Khóa nối request, job, trace và các event | `req_101`, `job_22` |

**Executor ≠ initiator** trong trường hợp bất đồng bộ: user yêu cầu xuất báo cáo, nhưng service chạy worker mới trực tiếp tạo file. **Actor ≠ target** khi admin thay đổi quyền của một người khác. **Approver ≠ executor** khi một người duyệt và một dịch vụ khác thi hành.

Không ghi `initiated_by=user_42` chỉ vì một message queue có trường `requestedBy` do client tùy ý gửi. Quan hệ giữa initiator và executor phải đến từ **bước đã xác thực và metadata được bảo vệ**, hoặc thể hiện rằng quan hệ đó chưa xác minh.

## 3. Các loại actor và nguyên tắc gán danh tính

### 3.1. Người dùng đã xác thực

Actor là tài khoản đã được hệ thống xác thực bằng session hợp lệ, IdP hoặc token đã kiểm tra. Nên dùng **canonical/stable actor ID** thay vì chỉ lưu email hoặc tên hiển thị: username có thể đổi, email có thể tái sử dụng.

Nếu event có `actor.id=user_42`, cần biết giá trị này do **security layer** cung cấp sau xác thực hay do controller lấy từ request body. Chỉ trường hợp thứ nhất có cơ sở tin cậy.

### 3.2. Service account và workload identity

Một microservice, batch job, script hệ thống hoặc worker chạy bằng service identity phải được ghi nhận như **SERVICE**, không tự gán vào một tài khoản người dùng có tên `system_admin`.

Ví dụ `actor.type=SERVICE`, `actor.id=svc_cleanup`, `trigger.type=SCHEDULE` cho một job dọn dữ liệu. Người đã tạo lịch trước đây có thể được ghi ở event **CREATE_SCHEDULE** khác, nhưng không nhất thiết là người trực tiếp khởi xướng từng lần chạy sau này.

### 3.3. Người dùng yêu cầu xử lý qua service

Một request được user `user_42` xác thực, sau đó được đưa vào queue để worker `svc_export` thực hiện:

```text
user_42 (đã xác thực)
   │
   ▼
API lưu job_22, requested_by=user_42
   │
   ▼
Hàng đợi/DB có bảo vệ metadata
   │
   ▼
Worker chạy bằng credential svc_export
   │
   ▼
Audit event:
  executor.type=SERVICE
  executor.id=svc_export
  initiated_by=user_42
  job_id=job_22
  action=EXPORT_REPORT
```

**Không đổi executor thành user_42 chỉ để làm báo cáo “đẹp”.** User là người khởi xướng, còn service mới là chủ thể thực hiện ở worker. Muốn quy trách nhiệm end-to-end, phải giữ quan hệ ủy quyền đã được chứng minh.

### 3.4. Impersonation và delegated action

Nhân viên hỗ trợ `support_8` có quyền thao tác trong ngữ cảnh tài khoản `user_42`. Audit cần giữ **real actor support_8** và **effective subject user_42**; nếu chỉ ghi `actor=user_42` thì thao tác của nhân viên có thể bị quy sai cho người dùng.

Có thể cần thêm delegation session ID, thời hạn, phạm vi quyền, approval, mục đích và lý do theo chính sách. Khi không có delegation, không tự tạo thông tin giả; khi không xác minh được, ghi rõ trạng thái không biết.

### 3.5. Caller chưa xác thực

Một yêu cầu login với username `admin` bị từ chối **không** chứng minh admin đã truy cập. Actor phù hợp là **ANONYMOUS/UNAUTHENTICATED**, outcome `DENIED`; `claimed_identifier=admin` chỉ là dữ liệu client cung cấp, phải được đánh dấu untrusted và cân nhắc quyền riêng tư.

## 4. Danh tính đáng tin đến từ đâu?

Thứ tự nguồn thường đáng tin cậy hơn, tùy thiết kế:

1. **Security context** đã được xây dựng sau authentication/authorization trong ứng dụng.
2. **Verified session hoặc bearer token/JWT** qua thư viện xác thực đúng cấu hình.
3. **Workload/service identity** được xác thực bằng cơ chế phù hợp (mTLS, identity nền tảng, client credential).
4. **Thông tin delegation/initiator** từ job/workflow record đã được tạo sau xác thực và có quyền chỉnh sửa được kiểm soát.

Những nguồn **không tự xác thực actor**:

- `X-User-ID`, `X-Authenticated-User` hoặc `X-Forwarded-User` do client có thể tự gửi.
- `X-Forwarded-For`, IP hoặc `User-Agent`: không chứng minh người thật.
- `createdBy` trong request body.
- `traceparent` hoặc `X-Request-ID`: chỉ là metadata tương quan.
- MDC chứa ID do client cung cấp hoặc bị rò từ request trước.
- `Authorization` được giải mã thủ công mà **không xác minh token**.

Nếu gateway chịu trách nhiệm xác thực và chuyển identity qua header, phải xác định ranh giới tin cậy: chặn đường đi tắt, strip header identity từ client, bảo vệ/xác thực kết nối gateway-service và quy tắc xử lý khi danh tính không hợp lệ. Không dựa duy nhất vào “mạng nội bộ”.

### JWT/OIDC: `sub` không đủ nếu thiếu namespace

`sub` thường có ý nghĩa **trong phạm vi issuer**. Hai hệ thống IdP có thể cùng cấp `sub="123"` cho hai danh tính không liên quan. Để tạo actor canonical, có thể dùng cặp **(verified issuer, subject)** hoặc ánh xạ sang user ID nội bộ ổn định.

Phải xác minh chữ ký, issuer, audience, hiệu lực thời gian và yêu cầu ứng dụng với token **trước** khi dùng claim làm bằng chứng. Access token kiểu **client credentials** có thể đại diện cho một service, không phải một người. Không mặc định mọi token có `sub` đều thuộc `actor.type=USER`.

## 5. Thiết kế schema “ai làm gì với ai?”

Một event có cấu trúc nên phân biệt ít nhất:

| Trường | Ý nghĩa |
| --- | --- |
| `event.id` | ID sự kiện để kiểm tra trùng/gap; không tự đảm bảo tính toàn vẹn |
| `event.time` | Thời điểm thao tác theo nguồn, UTC/offset rõ ràng |
| `event.name` / `action` | Mã thao tác cố định như `ASSIGN_ROLE` |
| `actor.type` | `USER`, `SERVICE`, `ANONYMOUS` hoặc enum được định nghĩa |
| `actor.id` | Canonical ID hoặc giá trị nêu rõ vô danh |
| `actor.issuer` / `auth.method` | Nguồn/phương thức xác thực khi có |
| `actor.authenticated` | Chủ thể được xác thực hay chỉ là claimed identity |
| `initiated_by` | Chủ thể khởi xướng nếu có chứng cứ |
| `effective_subject` | Tài khoản được thao tác thay, nếu có |
| `tenant.id` | Tenant từ context đáng tin, có namespace |
| `target.type`, `target.id` | Tài nguyên bị tác động |
| `outcome` | `SUCCESS`, `DENIED`, `FAILED` hoặc trạng thái nghiệp vụ rõ |
| `reason.code` | Mã lý do không chứa secret |
| `request_id`, `job_id`, `trace_id` | Tương quan các bước |
| `source.service` / `source.instance` | Thành phần phát event |
| `schema.version` | Phiên bản schema/contract |

Ví dụ JSON minh họa:

```json
{
  "event.id": "evt_501",
  "event.time": "2026-11-10T03:15:00Z",
  "event.name": "ASSIGN_ROLE",
  "actor.type": "USER",
  "actor.id": "user_42",
  "actor.issuer": "idp_main",
  "actor.authenticated": true,
  "target.type": "USER",
  "target.id": "user_91",
  "outcome": "SUCCESS",
  "request_id": "req_101",
  "source.service": "identity-api",
  "schema.version": 1
}
```

Tên trường ở đây là **schema minh họa**, không khẳng định chuẩn bắt buộc của mọi hệ thống. Cần định nghĩa kiểu, nullability, mã định danh, namespace, thời gian lưu và mức nhạy cảm. JSON đẹp **không** chứng minh identity đã được xác minh hoặc event chắc chắn được lưu bền vững.

## 6. Đừng nhầm target với actor hoặc request với kết quả

Ví dụ admin cấp quyền:

```text
actor.id     = admin_7
action       = GRANT_ROLE
target.id    = user_91
role.granted = REPORT_VIEWER
outcome      = SUCCESS
```

Ví dụ service dọn dữ liệu:

```text
actor.type   = SERVICE
actor.id     = svc_cleanup
trigger.type = SCHEDULE
action       = DELETE_EXPIRED
target.type  = ARCHIVE_BATCH
outcome      = SUCCESS
```

Ví dụ một workflow cần phê duyệt: nên có event **APPROVE** với actor người duyệt và event **EXECUTE** với actor thực thi. Không ép `approver` và `executor` về một trường `userId`.

Tương tự, **REQUESTED**, **AUTHORIZED**, **COMMITTED**, **DENIED**, **FAILED** và **DELIVERED** là các mốc có ngữ nghĩa khác nhau. Một API trả 202/200 có thể chỉ tạo job, chưa thực hiện nghiệp vụ. Nếu audit ghi “user exported report” tại thời điểm enqueue, bản ghi sẽ sai khi worker thất bại.

## 7. Ví dụ Java 17 chạy độc lập: phân biệt user, service và anonymous

Chương trình sau dùng **JDK thuần**, không cần Spring/SLF4J. Nó tạo các actor giả định đã được **tầng tin cậy xác thực bên ngoài chương trình**, rồi phát event mô tả trực tiếp, xử lý thay, tác vụ nội bộ và yêu cầu chưa xác thực.

**Giới hạn:** `main` chỉ tạo đối tượng minh họa; **constructor `Actor` không xác thực danh tính**. Trong ứng dụng thật, không cho client tự tạo actor ID rồi coi đó là sự thật. Stdout cũng không phải audit store bền vững.

Lưu tệp **`AuditActorDemo.java`**:

```java
import java.time.Instant;
import java.util.Objects;
import java.util.regex.Pattern;

public final class AuditActorDemo {
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_.:-]{1,80}");

    enum ActorType {
        USER, SERVICE, ANONYMOUS
    }

    record Actor(ActorType type, String id, String verifiedBy) {
        Actor {
            Objects.requireNonNull(type);
            checked(id);
            checked(verifiedBy);
        }
    }

    record AuditEvent(
            String eventId,
            Instant time,
            Actor executor,
            String initiatedBy,
            String action,
            String target,
            String outcome,
            String requestId) {
        AuditEvent {
            checked(eventId);
            Objects.requireNonNull(time);
            Objects.requireNonNull(executor);
            checked(initiatedBy);
            checked(action);
            checked(target);
            checked(outcome);
            checked(requestId);
        }
    }

    private static void checked(String value) {
        if (value == null || !SAFE.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid audit field");
        }
    }

    private static void emit(AuditEvent event) {
        System.out.printf(
                "time=%s event=%s actor_type=%s actor_id=%s "
                        + "verified_by=%s initiated_by=%s "
                        + "action=%s target=%s outcome=%s request_id=%s%n",
                event.time(),
                event.eventId(),
                event.executor().type(),
                event.executor().id(),
                event.executor().verifiedBy(),
                event.initiatedBy(),
                event.action(),
                event.target(),
                event.outcome(),
                event.requestId());
    }

    public static void main(String[] args) {
        Instant time = Instant.parse("2026-11-10T03:15:00Z");

        // Giả định các identity đã được xác thực ở tầng tin cậy.
        Actor user = new Actor(ActorType.USER, "user_42", "idp_main");
        Actor worker = new Actor(
                ActorType.SERVICE, "svc_export", "workload_identity");
        Actor anonymous = new Actor(
                ActorType.ANONYMOUS, "unknown", "none");

        // User trực tiếp yêu cầu thao tác.
        emit(new AuditEvent(
                "evt_001", time, user, "-",
                "REQUEST_EXPORT", "report_17", "SUCCESS", "req_101"));

        // Worker thực thi job do user đã xác thực yêu cầu.
        // initiatedBy chỉ có giá trị khi job metadata được bảo vệ.
        emit(new AuditEvent(
                "evt_002", time, worker, "user_42",
                "EXPORT_REPORT", "report_17", "SUCCESS", "req_101"));

        // Service tự làm việc, không có user khởi xướng.
        emit(new AuditEvent(
                "evt_003", time, worker, "-",
                "CLEANUP_EXPORT", "archive_4", "SUCCESS", "job_22"));

        // Login thất bại: không lấy tên tự khai làm actor.
        emit(new AuditEvent(
                "evt_004", time, anonymous, "-",
                "LOGIN", "session", "DENIED", "req_102"));

        // Dữ liệu chứa ký tự xuống dòng bị chặn trước log.
        try {
            new Actor(ActorType.USER, "admin\nFAKE", "idp_main");
        } catch (IllegalArgumentException ex) {
            System.out.println("untrusted_actor_id=rejected");
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac --release 17 AuditActorDemo.java
java AuditActorDemo
```

Stdout chính xác:

```text
time=2026-11-10T03:15:00Z event=evt_001 actor_type=USER actor_id=user_42 verified_by=idp_main initiated_by=- action=REQUEST_EXPORT target=report_17 outcome=SUCCESS request_id=req_101
time=2026-11-10T03:15:00Z event=evt_002 actor_type=SERVICE actor_id=svc_export verified_by=workload_identity initiated_by=user_42 action=EXPORT_REPORT target=report_17 outcome=SUCCESS request_id=req_101
time=2026-11-10T03:15:00Z event=evt_003 actor_type=SERVICE actor_id=svc_export verified_by=workload_identity initiated_by=- action=CLEANUP_EXPORT target=archive_4 outcome=SUCCESS request_id=job_22
time=2026-11-10T03:15:00Z event=evt_004 actor_type=ANONYMOUS actor_id=unknown verified_by=none initiated_by=- action=LOGIN target=session outcome=DENIED request_id=req_102
untrusted_actor_id=rejected
```

Giải thích:

- `evt_001` mô tả user yêu cầu export.
- `evt_002` có **executor SERVICE svc_export** nhưng `initiated_by=user_42` từ quy trình có chứng cứ; không nhập nhằng hai vai trò.
- `evt_003` không bịa user cho tác vụ nội bộ.
- `evt_004` giữ `actor_type=ANONYMOUS` vì không xác minh được người đang thử login.
- `checked(...)` dùng allowlist đơn giản để chặn ký tự điều khiển khi tạo text key=value, **không xác thực actor** và không thay thế encoder JSON phù hợp. Trong production cần giới hạn/escape đúng parser và chính sách dữ liệu.
- Timestamp cố định chỉ giúp xác minh output; sự kiện thật cần thời gian thực và đồng bộ clock.
- Chương trình không thực hiện transaction, retry, outbox, queue, TLS hay phân quyền kho audit. Không xem ví dụ stdout là bằng chứng có độ bền chống sửa đổi.

## 8. Spring Security: lấy identity từ security context

Ứng dụng Spring Boot dùng Spring Security thường có `Authentication` trong security context được tạo bởi authentication filter. Trích đoạn sau cần dependencies và security config, **không phải file Java độc lập**:

```java
org.springframework.security.core.Authentication auth =
        org.springframework.security.core.context.SecurityContextHolder
                .getContext().getAuthentication();

if (auth != null) {
    String name = auth.getName();
    // Ánh xạ name theo Authentication implementation đã cấu hình.
    // Không mặc định name là canonical user ID.
}
```

**`auth != null` và `auth.isAuthenticated()` chưa đủ chứng minh người dùng thật.** Một số cấu hình Spring Security tạo `AnonymousAuthenticationToken`, trong đó cờ `isAuthenticated()` có thể true. Cần xác định đúng cơ chế thực sự xác thực user/service và phân biệt anonymous.

Khi dùng OAuth2 Resource Server JWT, có thể lấy subject từ **JwtAuthenticationToken đã được resource server xác minh**:

```java
// Trích đoạn minh họa; không phải ứng dụng độc lập.
// auth đã được tạo qua security filter chain tin cậy.
if (auth instanceof org.springframework.security.oauth2.server.resource
        .authentication.JwtAuthenticationToken jwtAuth) {
    org.springframework.security.oauth2.jwt.Jwt jwt = jwtAuth.getToken();
    String subject = jwt.getSubject();
    // Kết hợp verified issuer + subject hoặc map sang ID nội bộ.
    // Phân loại USER/SERVICE theo identity model, không chỉ nhìn sub.
}
```

Các lưu ý:

- `getName()` có thể là username, token subject hoặc service name tùy authentication provider.
- `jwt.getSubject()` chỉ có ý nghĩa sau khi chữ ký/issuer/audience/expiry và chính sách token đã được xác minh.
- Token client credentials có thể biểu diễn **workload**, không phải một con người.
- Không log token, raw `Authentication`, session secret hay toàn bộ `Principal.toString()`.
- Session auth, API key và mTLS có cách map actor riêng; nên gom logic vào một thành phần **ActorResolver** do ứng dụng định nghĩa và kiểm thử.
- Nếu authentication là anonymous hoặc token không hợp lệ, không tự tạo actor USER bằng cách đọc tên trong request.

Không sao chép mẫu xử lý HTTP security context sang worker async rồi tin rằng ThreadLocal vẫn giữ identity người dùng. Cần chuyển metadata đã xác thực đúng cách.

## 9. Background job, message consumer và scheduled task

### Yêu cầu ban đầu và metadata job

Khi user kích hoạt tác vụ bất đồng bộ:

1. Xác thực user tại request boundary, nhận canonical actor ID và tenant ID từ context tin cậy.
2. Sau khi kiểm tra quyền, ghi job record: `job_id`, `requested_by`, `tenant`, `action`, `target`, `request_id`.
3. Bảo vệ job metadata và quan hệ issuer/tenant; client không được sửa `requested_by` tùy ý.
4. Worker xác thực bằng service identity, đọc metadata được bảo vệ.
5. Audit event lúc worker thực thi có **executor service** và **initiator** nếu liên kết được kiểm chứng.
6. Đặt `operation_id` và attempt ID để phân biệt xử lý lại với hành động mới.

**Không truyền toàn bộ credential/token của user vào hàng đợi lâu dài** chỉ để worker ghi đúng actor. Khi cần ủy quyền downstream, dùng cơ chế delegation/token exchange có kiểm soát và thời hạn phù hợp.

### Lịch chạy và trigger hệ thống

Job chạy mỗi đêm không trở thành thao tác của người tạo schedule trước đó. Ghi `actor=SERVICE(svc_cleanup)`, trigger SCHEDULE và schedule/job ID. Nếu lịch bị sửa, tạo event **UPDATE_SCHEDULE** với actor người sửa tại thời điểm đó.

### MDC/ThreadLocal và dữ liệu bị lẫn

Worker dùng thread pool; `SecurityContextHolder`/MDC có thể không tự propagate hoặc bị rò nếu không restore. Một trace ID cũng không chứng minh actor. Nếu dùng MDC để đưa actor ID vào log, phải snapshot metadata đã xác thực theo event và dọn/restore đúng scope, không lấy `MDC.get("actor")` của thread consumer logging làm bằng chứng.

## 10. Impersonation: ghi người thật thực hiện và người được đại diện

Một nhân viên support `support_8` thao tác ở chế độ impersonation cho `user_42`:

```text
real_actor.type       = USER
real_actor.id         = support_8
effective_subject.id  = user_42
delegation.mode       = IMPERSONATION
delegation.session_id = imp_801
action                = UPDATE_CONTACT
target.type           = PROFILE
target.id             = profile_42
outcome               = SUCCESS
```

Audit cần thể hiện:

- **Ai đã xác thực:** support_8.
- **Dùng quyền/phiên nào:** delegation session và policy cho phép.
- **Thao tác dưới danh nghĩa ai:** user_42.
- **Đổi tài nguyên nào:** profile_42 và kết quả thực tế.
- **Ai phê duyệt:** nếu workflow yêu cầu.
- **Mục đích/expiry:** khi cần quản trị rủi ro.

Nếu ứng dụng chỉ đọc effective principal trong phiên impersonation và ghi `actor=user_42`, đó là che mất người vận hành thực sự. Ngược lại, không được tạo delegation nếu thực tế chỉ là support xem thông tin bằng quyền riêng của họ. Các trường `initiated_by`, `effective_subject` và `approver` phải có nghĩa ổn định.

## 11. Tenant, issuer và vòng đời của danh tính

**Namespace:** cùng chuỗi `user_42` có thể tồn tại ở nhiều tenant hoặc issuer. Dùng canonical global ID hoặc bổ sung verified tenant/issuer. Không lấy tenant từ raw `X-Tenant-ID` mà không so với quyền thực tế của actor.

**Đổi tên:** username/email/display name có thể đổi và bị tái sử dụng. Audit nên giữ ID không tái sử dụng; snapshot tên người dùng chỉ nếu mục đích/retention cho phép.

**Account bị khóa/xóa:** event lịch sử vẫn cần giải thích được theo đúng chính sách. Không tự xóa dấu vết cần thiết cho điều tra chỉ vì tài khoản vận hành đã bị xóa, nhưng cũng không giữ PII vô thời hạn khi không có lý do.

**Credential theft:** audit có thể chứng minh credential được sử dụng, chưa chắc người thật sở hữu credential trực tiếp thực hiện. Khi phân tích cần phân biệt “credential/identity đã xác thực” với “người ngoài đời chắc chắn đứng sau hành động”.

## 12. Khi nào một thao tác được coi là SUCCESS?

Audit **REQUESTED** không đồng nghĩa **COMMITTED**. Một request có thể được chấp nhận, sau đó job thất bại. Một transaction có thể rollback. Nên định nghĩa mốc:

```text
Request authenticated
     │
     ▼
Authorization decision  → AUTHORIZED / DENIED
     │
     ▼
Start business action    → ATTEMPTED (nếu cần)
     │
     ▼
DB transaction commit    → COMMITTED / FAILED
     │
     ▼
Async delivery/notify    → DELIVERED / DELIVERY_FAILED
```

Với audit của thay đổi dữ liệu đã commit, có thể dùng **transactional outbox**: ghi business state và outbox event trong **cùng một DB transaction**. Publisher giao event sau commit, cần retry/dedup và giám sát backlog. Outbox không tự bảo đảm exactly-once end-to-end nếu không có cơ chế toàn chuỗi.

Nếu thao tác bị từ chối trước commit, tạo security event `DENIED` riêng nếu cần. Không ghi SUCCESS giả chỉ vì controller đã nhận request. Nếu có hai người phê duyệt/thực hiện, phát các event với actor phù hợp tại từng mốc.

## 13. Audit không chỉ là một dòng application log

Để một event có giá trị, cần bảo vệ:

- **Nguồn actor:** lấy từ identity đã xác thực, không từ client header.
- **Tính đúng đắn của event:** action/target/outcome được xác định bởi business logic ở điểm phù hợp.
- **Schema/encoder an toàn:** có cấu trúc, escape ký tự điều khiển và chống log forging (CWE-117).
- **Quyền tách biệt:** service chỉ phát audit không mặc định được xóa/sửa log lịch sử.
- **Lưu và retention:** append-only/immutable storage hoặc audit store theo yêu cầu.
- **Xác thực collector và truyền tải:** bảo vệ kênh và tenant routing.
- **Phát hiện mất/trùng:** event ID, counts, queue drop, ingestion lag, đối soát giao dịch.
- **Thời gian:** event time và ingestion time nếu cần, clock synchronization.
- **Cấu hình:** ai thay filter, level, destination, masking hoặc retention.

Chữ ký/MAC/hash chain có thể hỗ trợ phát hiện sửa đổi nếu khóa được bảo vệ và kiểm tra chuẩn. Nhưng **ký một actor ID giả lấy từ request không làm nó đúng**. Mọi chứng cứ có độ tin cậy không vượt quá nguồn xác thực ban đầu.

### Log injection và field format

Đưa raw username có `\nERROR user=admin` vào log text có thể giả mạo một dòng mới. Dùng structured encoder và validate/escape. Parameterized logging giúp tránh một số lỗi dựng message, nhưng placeholder **không tự escape CRLF** trong mọi formatter text. Đừng dùng input client làm tên logger, tên file, event type hoặc source identity.

## 14. Bảo vệ dữ liệu cá nhân và bí mật

Audit log thường cần actor ID, nhưng không có lý do mặc định phải lưu:

- Password, OTP, access/refresh token, cookie, API key hoặc private key.
- Raw JWT, toàn bộ `Authentication`, `Principal` hoặc HTTP headers/body.
- Đường dẫn/query string chứa token hoặc thông tin nhạy cảm.
- Email, địa chỉ, số tài khoản và dữ liệu nhạy cảm khác ngoài mục đích audit.
- Trace baggage hoặc MDC chứa PII bị copy sang mọi event.

Dùng **field allowlist**, canonical ID và reason code thay vì message tự do chứa bí mật. Khi cần IP/thiết bị cho bảo mật, ghi nó là metadata với chính sách riêng; IP không thay cho actor. Hạn chế quyền search/export/delete, áp retention phù hợp, bảo vệ cả backup và bản export CSV.

Đừng cho `request_id` hoặc `actor.id` trở thành metric label có cardinality không giới hạn; việc này có thể làm tăng chi phí và gây nghẽn hệ thống quan sát.

## 15. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Log ghi admin nhưng token thuộc user khác | Dùng `X-User-ID` từ request | Map từ principal đã xác thực |
| Login thất bại được gán actor admin | Nhầm claimed username với authenticated identity | Actor ANONYMOUS, claimed identifier riêng |
| Job chạy lại ghi user như executor | Không tách user initiator và worker identity | Giữ executor SERVICE và initiated_by |
| Support thao tác thay nhưng audit chỉ ghi customer | Đọc effective subject làm actor | Ghi real actor và delegation context |
| Tenant A có audit ID của tenant B | MDC/ThreadLocal rò hoặc tenant từ header | Context save/restore và tenant đã xác minh |
| Transaction rollback nhưng audit SUCCESS | Ghi trước commit | Chọn mốc commit, outbox hoặc trạng thái rõ |
| Một thao tác được đếm nhiều lần | Retry/duplicate message | Operation ID, event ID, dedup |
| Sau đổi tên không tìm được người dùng | Chỉ lưu username/email | Canonical stable ID + namespace |
| Service account bị xem như người dùng | Nhầm JWT `sub` luôn là USER | Identity model phân loại đúng |
| Audit mất khi disk/collector quá tải | Queue drop, sink lỗi, chưa drain | Delivery metrics, durable path nếu cần |
| Admin xóa được audit của mình | Quyền ingest/xóa không tách | RBAC, immutable copy, tamper alerts |
| Có trace ID nhưng không biết ai | Trace chỉ để correlate | Actor từ authentication boundary |
| HTTP 200 nhưng không có thao tác thực | Async accepted hoặc rollback | Phân biệt requested/committed |
| Event bị gộp qua hai IdP | Chỉ lưu `sub` không có issuer | Dùng verified issuer + subject |
| Chuỗi actor tạo nhiều dòng log giả | Không neutralize CRLF | Structured encoding và validation |

## 16. Kiểm thử việc quy đúng actor

Một ma trận thử tối thiểu:

| Tình huống | Actor kỳ vọng | Liên kết cần ghi |
| --- | --- | --- |
| Người dùng đổi vai trò | USER user_42 | Target user_91, outcome sau commit |
| User yêu cầu export, worker thực hiện | SERVICE svc_export ở worker | initiated_by user_42 nếu có chứng cứ |
| Cron tự chạy | SERVICE svc_cleanup | Schedule/job ID, không bịa user |
| Support impersonate user | USER support_8 real actor | effective subject user_42 + delegation |
| Anonymous thử đăng nhập | ANONYMOUS | Claimed username chỉ là metadata không tin cậy |
| Service B gọi service A | SERVICE svc_b tại A | Chỉ gắn user gốc nếu có delegation đáng tin |

**Các thử nghiệm tiêu cực quan trọng:**

1. Gửi `X-User-ID: admin` nhưng không có credential hợp lệ: không được gán actor admin.
2. Hai tenant/issuer có cùng chuỗi user ID: không bị quy cùng người.
3. Username chứa newline, control character và payload dài: không được tạo log giả/overflow.
4. Hai request liên tiếp trên cùng thread pool: MDC và actor không bị rò.
5. Worker xử lý job sau khi request gốc kết thúc: initiator vẫn đúng nếu metadata đã được bảo vệ.
6. Impersonation: real actor, effective subject, session và approval được ghi riêng.
7. Rollback transaction: không có event COMMITTED/SUCCESS sai.
8. Retry worker: audit có operation ID để phân biệt một hành động và nhiều lần thử.
9. Queue đầy/collector hỏng: báo số event mất hoặc backpressure, không âm thầm giả báo đã lưu.
10. Role read-only audit không thể sửa/xóa lịch sử hoặc đọc tenant khác.
11. User đổi tên/khóa tài khoản: event lịch sử vẫn truy xuất theo stable ID.
12. Dùng token **giả/canary** kiểm tra không rò vào file, collector, SIEM, dashboard và export.

Khi test, đặt **expected actor/target/outcome** trước, kiểm tra event đã thực sự lưu theo yêu cầu và thu bằng chứng. Một dòng trong console chưa chứng minh thành công toàn pipeline.

## 17. Kiến trúc Java đề xuất

```text
HTTP Security Filter / Message Auth
  │
  └─ Verify token, session hoặc workload credential
       │
       ▼
 ActorResolver (canonical actor ID, type, issuer, tenant)
       │
       ▼
 Application Service (authorization + business action)
       │
       ├─ Business transaction / outbox nếu cần
       ▼
 AuditEventBuilder (actor, initiator, action, target, outcome)
       │
       ▼
 Trusted Audit Sink / Collector
       │
       ▼
 Protected Audit Store + Search/Investigation
```

- **Security layer** xác thực nguồn, không cho controller tự chọn actor ID từ request body.
- **ActorResolver** là abstraction do ứng dụng xây, không phải class mặc định của JDK/Spring; chịu trách nhiệm chuẩn hóa identity/tenant/issuer.
- **Business layer** biết mốc outcome và target thật.
- **Audit builder** ép schema và mã event đã định nghĩa, kiểm soát dữ liệu ngoài.
- **Audit sink** bảo vệ transport, storage, retention và quyền xem/sửa/xóa.
- **Investigators** phân biệt danh tính credential với người thật và liên kết các event bằng job/operation/trace ID.

Ngoài HTTP, message consumer, batch, CLI quản trị, migration và scheduled task phải có actor model tương ứng. Không dùng user của “request gần nhất” cho thao tác nền.

## 18. Quy trình điều tra: ai xóa tài nguyên?

Một cách điều tra có căn cứ:

1. Xác định target/resource ID và thay đổi thật trong dữ liệu nghiệp vụ.
2. Tìm audit event **ở mốc COMMITTED** tương ứng, không chỉ `REQUESTED`.
3. Kiểm tra `actor.type`, `actor.id`, verified issuer và tenant.
4. Nếu actor là SERVICE, theo job/operation ID để kiểm tra initiated_by đáng tin.
5. Nếu impersonation, kiểm tra real actor, effective subject, delegation session.
6. Đối chiếu access log, application log, trace và transaction/outbox.
7. Kiểm tra retry/duplicate, clock drift, queue drop, tamper hoặc quyền xóa log.
8. Báo cáo mức chắc chắn: “credential được sử dụng” khác “người thật chắc chắn đã thao tác”.

Ví dụ kết luận thận trọng:

> “Theo audit event phát ra sau commit từ identity-api, credential được xác thực với canonical actor ID user_42, issuer idp_main, đã yêu cầu GRANT_ROLE lên user_91 tại 03:15 UTC. Chưa có chứng cứ độc lập khẳng định người sở hữu tài khoản trực tiếp điều khiển phiên.”

## 19. Checklist để audit trả lời đúng “ai thực hiện”

- [ ] Đã định nghĩa actor/executor, initiator, effective subject, target, approver.
- [ ] Actor lấy từ security context hoặc workload identity đã xác minh, không tin raw header.
- [ ] Phân biệt USER, SERVICE, ANONYMOUS và nguồn xác thực.
- [ ] Actor ID ổn định, không chỉ dùng email/display name; có issuer/tenant namespace.
- [ ] Actor không bị nhầm với người dùng/tài nguyên là target.
- [ ] Với impersonation, real actor và người được đại diện đều có mặt.
- [ ] Với background jobs, executor là service và initiator chỉ được gắn khi liên kết được bảo vệ.
- [ ] Với cron, không tự gán user tạo lịch cho mỗi lần chạy.
- [ ] Có event ID, operation/job/request/trace ID đúng mục đích.
- [ ] Outcome tương ứng mốc xử lý thật, không nhầm accepted với committed.
- [ ] Có chống log forging và không đưa credential/PII ngoài yêu cầu.
- [ ] Có RBAC, retention, integrity và khả năng phát hiện event bị mất/sửa.
- [ ] Đã thử anonymous, đa tenant, impersonation, rollback, retry và sink failure.
- [ ] Có nguyên tắc điều tra phân biệt danh tính credential với người thật đứng sau.

**Ghi nhớ:** muốn trả lời **“ai thực hiện thao tác?”**, phải ghi **danh tính đã xác thực tại đúng ranh giới**, tách **người dùng khởi xướng** với **dịch vụ thực thi** và **tài khoản được thao tác thay**, rồi nối chúng với **action, target và outcome thực tế**. IP, trace ID, tên trong header hoặc username thử đăng nhập không thay thế được bằng chứng xác thực.

### Tài liệu tham khảo

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [Spring Security — Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Oracle — Java 17 records](https://docs.oracle.com/en/java/javase/17/language/records.html)
