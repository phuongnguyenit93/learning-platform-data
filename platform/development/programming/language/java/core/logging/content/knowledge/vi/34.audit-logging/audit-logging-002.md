# Sự kiện audit trong Java Core Logging

## 1. Sự kiện audit là gì?

**Sự kiện audit (audit event)** là một bản ghi có cấu trúc về **ai hoặc thành phần nào đã thực hiện hay cố thực hiện hành động gì, đối với đối tượng nào, khi nào, trong ngữ cảnh nào và kết quả ra sao**. Audit logging phục vụ truy trách nhiệm, điều tra sự cố bảo mật, đối chiếu thay đổi quan trọng và chứng minh hành động đã diễn ra theo quy trình. Một audit event có thể liên quan đến xác thực, phân quyền, cấu hình hệ thống, truy cập dữ liệu nhạy cảm hoặc thay đổi trạng thái nghiệp vụ bắt buộc theo dõi.

Ví dụ:

- Nhân viên quản trị đổi quyền của tài khoản người dùng.
- Một tài khoản cố truy cập tài nguyên nhưng bị từ chối vì thiếu quyền.
- API key được tạo, xoay vòng hoặc thu hồi.
- Cấu hình xác thực, chính sách bảo mật hoặc quyền truy cập dữ liệu được chỉnh sửa.
- Tác vụ xuất dữ liệu nhạy cảm được yêu cầu, chấp thuận, hoàn tất hoặc thất bại.
- Chính cơ chế audit bị thay đổi cấu hình, mất kết nối hoặc phát hiện tính toàn vẹn bất thường.

**Audit event khác với dòng log vận hành thông thường.** Một dòng `logger.debug("Processing request")` giúp lập trình viên debug; một audit event `permission.role.changed` phải đủ trường để trả lời người thực hiện, đối tượng bị ảnh hưởng, quyền trước/sau, kết quả, căn cứ cho phép và dấu vết đối chiếu. Audit không nên chỉ phụ thuộc vào một chuỗi message dễ thay đổi theo cách viết code.

### Phân biệt những loại dữ liệu liên quan

| Loại | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Operational log | Ứng dụng đang làm gì và có lỗi không? | Timeout khi gọi downstream |
| Security event | Có dấu hiệu truy cập hay hành vi bất thường không? | Nhiều lần đăng nhập thất bại |
| **Audit event** | Hành động nào đã xảy ra hoặc bị từ chối, bởi chủ thể nào, tác động gì? | Quyền của user-7 đổi từ READER sang EDITOR |
| Distributed trace | Một request đi qua những service/span nào? | Trace ID liên kết API gateway tới identity service |
| Business event | Trạng thái nghiệp vụ nào đã thay đổi? | Đơn hàng chuyển sang PAID |

Một sự kiện có thể đồng thời có giá trị audit, bảo mật và nghiệp vụ, nhưng **mỗi mục đích có yêu cầu lưu trữ, quyền truy cập và độ tin cậy riêng**. Đừng mặc định một trace sampled hoặc một INFO log có thể thay thế audit bắt buộc.

## 2. Những thời điểm nên tạo audit event

Audit có ý nghĩa khi được phát tại **ranh giới của một quyết định hoặc sự thay đổi có giá trị truy trách nhiệm**, thay vì phát ở mọi dòng code. Với Java service, thường cân nhắc:

| Nhóm | Tình huống | Dữ liệu tối thiểu cần làm rõ |
| --- | --- | --- |
| Xác thực | Login thành công/thất bại, logout, MFA enrollment/reset | Principal, cơ chế, kết quả, reason code, request |
| Phân quyền | Access denied, grant/revoke role, thay đổi policy | Actor, target, permission, before/after, kết quả |
| Tài khoản | Tạo, khóa, mở khóa, xóa tài khoản | Actor, subject, trạng thái cũ/mới, approval |
| Quản trị | Đổi setting quan trọng, feature flag nhạy cảm | Actor, config key, giá trị trước/sau được phép lưu |
| Credentials | Tạo/rotate/revoke token hoặc key | Key identifier/fingerprint, loại thao tác; **không lưu secret** |
| Dữ liệu nhạy cảm | Export/download, thay đổi quyền truy cập, bulk delete | Resource class/ID, scope, result, volume khi hợp lệ |
| Giao dịch quan trọng | Hoàn tất/hủy giao dịch cần đối chiếu | Entity ID, transition, correlation, transaction ID |
| Vận hành audit | Tắt audit, đổi retention/quyền xem, ingest thất bại | Actor/component, thay đổi cấu hình, ảnh hưởng |

Không phải mọi lần đọc dữ liệu đều bắt buộc audit, và không phải mọi lần truy cập bị từ chối phải giữ vĩnh viễn. Chọn **danh mục sự kiện theo threat model, trách nhiệm nghiệp vụ và chính sách pháp lý áp dụng**. Với thao tác có tần suất cực cao, phân biệt raw access logs và audit cần đầy đủ; nếu quy định yêu cầu ghi toàn bộ thì phải thiết kế hạ tầng chịu tải tương ứng, không âm thầm sampling.

### Audit những lần thất bại

Chỉ ghi những thao tác thành công sẽ bỏ sót các lần truy cập trái phép. Ngược lại, chỉ log thất bại sẽ không biết **ai đã đổi quyền thành công**. Nên định nghĩa event outcome rõ ràng như `SUCCESS`, `DENIED`, `FAILED`, `PENDING` hoặc `CANCELLED`, nhưng chỉ dùng các trạng thái phù hợp vòng đời hành động thực tế.

- `DENIED`: hệ thống từ chối **trước khi thực hiện** do chính sách xác thực/phân quyền.
- `FAILED`: hành động được chấp thuận nhưng gặp lỗi và **không hoàn tất theo hợp đồng**.
- `SUCCESS`: hành động hoàn tất ở **điểm commit/quyết định thành công đã xác định**.
- `PENDING`: đã tiếp nhận yêu cầu, chưa đủ căn cứ khẳng định hoàn tất.

Không ghi `SUCCESS` ngay khi request được nhận nếu nghiệp vụ còn chạy bất đồng bộ. Với workflow dài, dùng sự kiện riêng cho `REQUESTED`, `APPROVED`, `COMPLETED` và `FAILED`, liên kết chúng bằng cùng correlation/operation ID.

## 3. Cấu trúc một audit event tốt

Một bản ghi audit nên có **schema phiên bản hóa và các trường mang nghĩa ổn định**. Ví dụ JSON:

```json
{
  "schema_version": "1",
  "event_id": "evt-100",
  "occurred_at": "2026-01-01T00:00:01Z",
  "event_type": "iam.role.change",
  "actor": {
    "id": "admin-1",
    "kind": "HUMAN",
    "authn_method": "SSO"
  },
  "target": {
    "type": "USER_ACCOUNT",
    "id": "user-7"
  },
  "action": "ROLE_CHANGE",
  "outcome": "SUCCESS",
  "reason_code": "ADMIN_POLICY",
  "changes": {
    "role": {
      "before": "READER",
      "after": "EDITOR"
    }
  },
  "service.name": "identity-api",
  "deployment.environment.name": "prod",
  "request_id": "req-10",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây là **schema minh họa do ứng dụng định nghĩa**, không phải định dạng mặc định của JDK, SLF4J hoặc hệ thống SIEM. Để tích hợp nhiều service, cần một schema contract thống nhất, validate và versioning trước khi ingest.

### Ý nghĩa của từng nhóm trường

| Trường/nhóm | Mục đích | Lưu ý |
| --- | --- | --- |
| `schema_version` | Cho phép parser hiểu cấu trúc qua các lần nâng cấp | Không thay nghĩa của trường cũ một cách âm thầm |
| `event_id` | Định danh **một sự kiện logic** để dedup/đối chiếu | Nên được tạo bởi thành phần tin cậy và ổn định khi retry |
| `occurred_at` | Thời điểm event xảy ra ở nguồn | Dùng UTC/offset, phân biệt với thời điểm ingest |
| `actor` | Ai hoặc service account nào gây ra hành động | Phải lấy từ identity đã xác minh; không chỉ tin client gửi |
| `target` | Đối tượng bị tác động | ID/type chuẩn hóa và phạm vi tenant nếu cần |
| `action` / `event_type` | Loại hành động có nghĩa ổn định | Tránh free-text quá tùy tiện |
| `outcome` / `reason_code` | Thành công, từ chối hay lỗi, với lý do máy đọc được | Không thay thế bằng message ngôn ngữ tự nhiên |
| `changes` | Thay đổi trước/sau có thể kiểm chứng | Chỉ chứa field được phép; redact data nhạy cảm |
| `service.name` / environment | Phân biệt service và môi trường sinh event | Tránh giá trị client giả mạo |
| `request_id` / `trace_id` | Nối với operational log và trace | Một request có thể phát nhiều audit event |
| `tenant_id` (khi thích hợp) | Phân định dữ liệu nhiều khách hàng | Áp quyền theo tenant ở nơi xem/lưu trữ |
| `approval_id` hoặc `policy_version` | Đối chiếu quyết định cho phép | Chỉ dùng khi có ý nghĩa thực và nguồn xác thực |

**Phân biệt actor và subject/target:** actor là chủ thể thực hiện thao tác; target là thực thể bị tác động. Một quản trị viên khóa tài khoản của người khác không có nghĩa tài khoản bị khóa là actor. Với service-to-service, actor có thể là workload identity. Nếu hành động “thay mặt” người dùng, cần cách biểu diễn rõ **initiating user**, **executing service** và thông tin delegation nếu có, không tự nhận cả hai là một.

**`event_id` khác `request_id`:** một request đổi nhiều quyền có thể tạo nhiều audit events; chỉ dùng `request_id` để dedup sẽ làm mất sự kiện hợp lệ. Với retry của cùng một *thao tác logic*, cần định nghĩa khóa/idempotency phù hợp, không tự sinh event ID mới cho từng lần gửi lại nếu muốn tránh đếm trùng.

## 4. Tính xác thực: tin ai, và tin phần nào?

Audit event có giá trị khi trường actor, action và outcome **được tạo từ trạng thái đã xác minh bởi server**, không từ chuỗi do người dùng tự khai báo. Ví dụ client có thể gửi header `X-User: admin`, nhưng điều đó không chứng minh người dùng thật là admin.

Nguồn đáng tin thường là:

1. **Authentication context** do middleware xác minh chữ ký/session rồi tạo principal ID; service không đọc trực tiếp một header chưa xác thực để làm actor.
2. **Authorization decision** do policy engine hoặc business logic tính, kèm policy/rule version khi hữu ích.
3. **Committed business state** để xác định action đã thực sự thành công hay thất bại.
4. **Server-side event generator** tạo event ID, timestamp và metadata service; tránh cho client ghi đè các trường này.
5. **Trusted deployment metadata** về service name, environment, workload identity hoặc tenant scope.

Nguồn IP, User-Agent, địa lý và thiết bị là **tín hiệu phụ**, không tự chứng minh danh tính. Nếu đứng sau reverse proxy, phải hiểu chuỗi proxy tin cậy trước khi dùng `X-Forwarded-For`; không lấy mù địa chỉ từ header do client tự tạo. Với hệ thống đa tenant, không chỉ dùng một trường `tenant_id` có thể bị client điều khiển để quyết định phạm vi audit hoặc quyền truy vấn.

### Nguy cơ log injection

Các trường như username, object name, URL path, user agent hoặc error message có thể chứa newline, dấu ngoặc kép và control characters. Khi nối chuỗi thành text log, dữ liệu này có thể trông giống nhiều dòng sự kiện khác nhau. **Structured logging qua JSON encoder được kiểm chứng**, validation và giới hạn kích thước trường giúp duy trì ranh giới event. Tuy nhiên, encoder tốt không thay thế việc xác thực trường actor/outcome.

Không log nguyên secret, mật khẩu, access token, session cookie, private key, API key, connection string chứa credential, thông tin thanh toán nhạy cảm hoặc payload cá nhân không cần thiết. Nếu ghi event `credential.rotated`, chỉ lưu credential ID hoặc fingerprint an toàn, **không lưu giá trị credential trước/sau**.

## 5. Thời điểm phát event và thứ tự sự kiện

Một thao tác nghiệp vụ có thể gồm các bước:

```text
Request arrived
  -> authenticate
  -> authorize
  -> validate
  -> execute business change
  -> commit
  -> send response
```

Chọn thời điểm audit dựa trên **ý nghĩa của event**:

- Thao tác **bị từ chối**: phát event `DENIED` sau quyết định từ chối, không đợi có database change.
- Thao tác **thành công**: phát hoặc ghi bền event `SUCCESS` dựa vào **thành công thực** của transaction/operation, tránh xác nhận sai trước commit.
- Thao tác **bất đồng bộ**: phát event `REQUESTED` khi nhận yêu cầu và event `COMPLETED` hoặc `FAILED` khi kết quả cuối cùng được xác định.
- Thao tác **phức hợp**: nếu thay đổi nhiều đối tượng, nêu rõ event biểu diễn toàn bộ operation hay từng thay đổi con; không gộp làm mất khả năng đối chiếu.

Nếu API trả thành công nhưng ghi audit thất bại, có thể xuất hiện thay đổi không có bằng chứng. Nếu ghi audit trước rồi transaction rollback, có thể xuất hiện audit `SUCCESS` giả. Cần chọn **hợp đồng tính nhất quán** theo nghiệp vụ, thay vì đơn giản đặt `logger.info(...)` trước hoặc sau một dòng `repository.save(...)` rồi mặc định nguyên tử.

## 6. Ví dụ Java 17 chạy độc lập: audit khi đổi quyền thành công và bị từ chối

Ví dụ dùng JDK 17 để minh họa cấu trúc audit event, sự khác biệt giữa **actor** và **target**, before/after state, outcome và việc audit cả thao tác thành công lẫn bị từ chối. Chương trình cố ý sử dụng thời gian và ID cố định để stdout xác định.

**Lưu ý:** đây là mô hình trong bộ nhớ. Nó **không có transaction database, không có durable audit storage, không có kiểm tra auth thật, không an toàn với nhiều thread**, và không phải hệ thống kiểm soát quyền production. JSON encoder tối giản chỉ minh họa escaping; production nên dùng thư viện JSON/structured logging đã được kiểm chứng.

Lưu trong tệp `AuditEventDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class AuditEventDemo {
    record AuditEvent(
            String eventId, Instant occurredAt, String actorId,
            String action, String targetId, String outcome,
            String beforeRole, String afterRole,
            String reasonCode, String requestId) {}

    private static final Map<String, String> ROLES = new HashMap<>();
    private static final List<AuditEvent> EVENTS = new ArrayList<>();

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String field(String name, String value) {
        return quote(name) + ":" + quote(value);
    }

    private static void emit(AuditEvent event) {
        EVENTS.add(event);
        System.out.println("{"
                + field("event_id", event.eventId()) + ","
                + field("occurred_at", event.occurredAt().toString()) + ","
                + field("actor_id", event.actorId()) + ","
                + field("action", event.action()) + ","
                + field("target_id", event.targetId()) + ","
                + field("outcome", event.outcome()) + ","
                + field("before_role", event.beforeRole()) + ","
                + field("after_role", event.afterRole()) + ","
                + field("reason_code", event.reasonCode()) + ","
                + field("request_id", event.requestId())
                + "}");
    }

    private static void changeRole(
            String actor, String target, String requestedRole,
            String eventId, String requestId, Instant time) {
        String before = ROLES.get(target);
        if (before == null) {
            throw new IllegalArgumentException("Unknown target");
        }

        // Quy tắc demo; không phải authentication/authorization thật.
        boolean allowed = "admin-1".equals(actor);
        if (allowed) {
            ROLES.put(target, requestedRole);
        }
        String after = ROLES.get(target);

        emit(new AuditEvent(
                eventId, time, actor, "ROLE_CHANGE", target,
                allowed ? "SUCCESS" : "DENIED",
                before, after,
                allowed ? "ADMIN_POLICY" : "NOT_AUTHORIZED",
                requestId));
    }

    public static void main(String[] args) {
        ROLES.put("user-7", "READER");

        changeRole(
                "admin-1", "user-7", "EDITOR",
                "evt-100", "req-10",
                Instant.parse("2026-01-01T00:00:01Z"));

        changeRole(
                "user-8", "user-7", "OWNER",
                "evt-101", "req-11",
                Instant.parse("2026-01-01T00:00:02Z"));

        System.out.printf(
                "FINAL role=%s audit_events=%d%n",
                ROLES.get("user-7"), EVENTS.size());
    }
}
```

Biên dịch và chạy:

```bash
javac AuditEventDemo.java
java AuditEventDemo
```

**Stdout chính xác**:

```json
{"event_id":"evt-100","occurred_at":"2026-01-01T00:00:01Z","actor_id":"admin-1","action":"ROLE_CHANGE","target_id":"user-7","outcome":"SUCCESS","before_role":"READER","after_role":"EDITOR","reason_code":"ADMIN_POLICY","request_id":"req-10"}
{"event_id":"evt-101","occurred_at":"2026-01-01T00:00:02Z","actor_id":"user-8","action":"ROLE_CHANGE","target_id":"user-7","outcome":"DENIED","before_role":"EDITOR","after_role":"EDITOR","reason_code":"NOT_AUTHORIZED","request_id":"req-11"}
```

Dòng thứ ba trên stdout:

```text
FINAL role=EDITOR audit_events=2
```

Giải thích:

1. `admin-1` được quy tắc demo cho phép, nên role chuyển `READER → EDITOR`. Event đầu tiên ghi `SUCCESS`, before/after khác nhau và actor khác target.
2. `user-8` không có quyền thay role, nên trạng thái vẫn là `EDITOR`. Event thứ hai ghi `DENIED`, before/after giống nhau, không đánh dấu nhầm `SUCCESS`.
3. Hai event có `event_id` riêng để nhận diện từng hành động; `request_id` giúp nối với log request tương ứng.
4. `quote` escape dấu nháy, backslash, newline và các control characters cơ bản; dữ liệu ví dụ không chứa secret. Sản phẩm thật cần encoder và validation đầy đủ cho Unicode/schema.
5. `ROLES` và `EVENTS` là dữ liệu **trong RAM**. Nếu process crash sau `ROLES.put` nhưng trước `emit`, thay đổi đã xảy ra mà audit chưa được ghi. Vì vậy ví dụ chỉ minh họa **nội dung** audit, không chứng minh độ tin cậy hay tính nguyên tử.

Một lỗi thiết kế phổ biến là dùng chính ví dụ RAM/console như một “audit trail đầy đủ”. Để đảm bảo event tồn tại đồng thời với thay đổi dữ liệu, phải thiết kế thêm transaction/outbox hoặc cơ chế lưu trữ audit phù hợp.

## 7. Làm thế nào để audit event không mất khi có lỗi?

Có những cấp độ đảm bảo rất khác nhau:

| Cách ghi | Ưu điểm | Giới hạn |
| --- | --- | --- |
| `logger.info(...)` đến console | Dễ vận hành, dùng cùng pipeline với log thường | Logger level/filter/sampling, queue, runtime/agent và ingest có thể mất log |
| Appender ghi file cục bộ | Có thể làm việc khi network lỗi | File rotation, full disk, crash/flush, quyền và tính bền không chắc |
| Gửi đồng bộ đến audit service | Có thể nhận ACK rõ hơn | Timeout/partial failure; ACK ở tầng gateway chưa chắc đã durable |
| Queue/broker có durability theo hợp đồng | Hỗ trợ retry và tách producer/consumer | Phải xác định mức ack, retention, replication và recovery |
| **Transactional outbox** | Gắn sự kiện cần phát với thay đổi nghiệp vụ trong cùng DB transaction | Cần publisher, retry, dedup, cleanup, giám sát backlog |
| Audit storage chuyên dụng | Có thể có chính sách append-only, retention và phân quyền mạnh hơn | Phụ thuộc công nghệ và cấu hình; không mặc định bất biến tuyệt đối |

### Transactional outbox cho thay đổi quan trọng

Nếu nghiệp vụ dùng database có transaction, một mẫu thường gặp:

```text
BEGIN TRANSACTION
  UPDATE user_roles
    SET role = 'EDITOR'
    WHERE user_id = 'user-7';

  INSERT INTO audit_outbox (
    event_id, event_type, actor_id, target_id,
    before_role, after_role, outcome, occurred_at
  ) VALUES (...);
COMMIT

Background publisher:
  đọc những outbox row chưa được xác nhận
  -> xuất audit event đến đích
  -> retry khi lỗi
  -> đánh dấu hoặc dọn outbox theo cơ chế an toàn
```

Đây là **sơ đồ pseudo-SQL**, không phải script có thể chạy độc lập. Tính nguyên tử áp dụng cho **UPDATE và INSERT cùng transaction trong một database có ACID phù hợp**. Nó không làm việc xuất sang hệ thống bên ngoài tự động exactly-once.

Nếu publisher gửi event thành công nhưng ACK thất lạc, nó có thể gửi lại, tạo duplicate. Consumer/backend cần dùng `event_id` làm **idempotency key** phù hợp, hoặc truy vấn/dedup để không biến hai lần vận chuyển thành hai hành động logic. Không nhầm `retry_attempt` với một audit event mới.

### Trường hợp bị từ chối hoặc transaction rollback

Một request `DENIED` không nhất thiết có database transaction nghiệp vụ, nhưng vẫn cần audit theo chính sách. Nếu lưu audit riêng với transaction chính, phải nêu rõ hành vi khi một bên thất bại. Với hành động `FAILED` và đã rollback, **không ghi event `SUCCESS` như thể commit xong**. Có thể có event `ATTEMPTED` và event `FAILED` riêng để giữ sự thật về chuỗi xử lý.

Chọn **fail-open hay fail-closed** theo loại thao tác:

- Với log chẩn đoán thông thường, thường ưu tiên để service tiếp tục dù logging backend gặp sự cố, đồng thời đo tình trạng log bị thiếu.
- Với audit bắt buộc của một thao tác nhạy cảm, có thể phải **không chấp nhận thao tác** nếu chưa ghi bền dấu vết hoặc outbox, tùy hợp đồng nghiệp vụ và quy định.
- Không đồng bộ ghi audit tới network vô hạn trên request thread rồi hy vọng vừa bảo đảm không mất dữ liệu vừa không ảnh hưởng availability. Thiết kế deadline, retry, backpressure, queue và recovery rõ ràng.

## 8. Delivery semantics, duplicate và thứ tự

Đường đi phổ biến:

```text
Java service
  -> audit event generator
  -> durable commit / outbox / queue
  -> exporter / collector
  -> audit store
  -> index / truy vấn / báo cáo
```

Một sự kiện có thể được chấp nhận ở hàng đợi RAM nhưng chưa lưu bền. ACK “received” ở Collector không tự chứng minh backend lưu xong. Vì thế cần xác định **điểm cam kết**: source accepted, durably enqueued, committed vào DB/broker, hay queryable tại nơi lưu cuối.

- **At-most-once:** có thể mất event khi lỗi nhưng tránh gửi lại gây trùng.
- **At-least-once:** có thể có duplicate attempt do retry; cần ID và dedup.
- **Exactly-once effect:** chỉ có thể khẳng định trong ranh giới đã thiết kế transaction/idempotency/commit một cách rõ ràng; logger thường không mặc định cung cấp.

**Đừng giả định thứ tự toàn cục.** Nhiều thread, nhiều instance, queue và network có thể làm event đến đích không đúng thứ tự tạo. Nếu cần xác định chuỗi thay đổi quyền, có thể dùng `entity_version` hoặc sequence tăng theo đối tượng được commit trong transaction, cùng với event time và ingestion time. Timestamp có độ phân giải cao không tự đảm bảo thứ tự tuyệt đối giữa các máy có clock skew.

Một hệ thống điều tra tốt lưu được *event occurred at*, *ingested at*, *event ID* và *correlation*, xử lý late events, retry và duplicate. Các sự kiện đã bị filter/sampling có chủ đích phải được phân biệt với **event bị mất do lỗi**.

## 9. Tính toàn vẹn, chống sửa trái phép và khả năng truy xuất

Audit trail cần bảo vệ khỏi việc bị sửa/xóa ngoài quy trình. Những kỹ thuật có thể kết hợp:

1. **Append-only theo quyền:** ứng dụng sản xuất chỉ được phép tạo sự kiện, không tự sửa hoặc xóa các bản ghi cũ. Hạn chế quyền `DELETE`/`UPDATE` và quyền quản lý retention.
2. **Lưu bền và backup:** replication, durable queue/storage, recovery sau crash, quota/ổ đĩa và kiểm thử restore theo hợp đồng.
3. **Tamper evidence:** chuỗi hash, HMAC, chữ ký số hoặc cơ chế bất biến của nền tảng để phát hiện sửa đổi. Một **hash chain đơn thuần** chỉ phát hiện thay đổi đáng tin khi điểm neo/khóa hoặc bản tóm tắt được bảo vệ độc lập; người có quyền sửa cả chuỗi và toàn bộ anchor có thể dựng lại hash.
4. **Đóng dấu thời gian và khóa:** timestamp từ nguồn tin cậy, kiểm lệch đồng hồ, quản lý khóa ký, rotation và policy xác minh chữ ký.
5. **Quyền truy vấn tách biệt:** writer không mặc định có quyền đọc audit của toàn hệ thống; người điều tra chỉ có quyền theo vai trò/tenant và có audit khi truy cập.
6. **Giám sát chính pipeline audit:** queue backlog, dropped events, exporter errors, parse failures, heartbeat, dead-letter và retention changes phải có tín hiệu cảnh báo độc lập.

Đừng quảng cáo “tamper-proof” chỉ vì file đặt ở chế độ append hay mỗi dòng có SHA-256. Tính chống sửa phải nêu rõ đối thủ có thể kiểm soát gì và cơ chế nào bảo vệ anchor/key, storage, quyền quản trị và history.

## 10. Retention, dữ liệu cá nhân và phân quyền

Audit logging thường phục vụ trách nhiệm và đối chiếu lâu dài hơn log DEBUG thông thường; tuy nhiên **thời hạn lưu không có một giá trị cố định áp dụng cho mọi quốc gia và mọi nghiệp vụ**. Tổ chức phải xác định từ mục đích xử lý, yêu cầu pháp lý/hợp đồng thực tế, loại sự kiện, rủi ro và chi phí.

Các nguyên tắc triển khai:

- **Data minimization:** lưu ID, loại hành động, outcome và thay đổi có ý nghĩa; không lưu plaintext password, token hoặc nội dung bí mật. Với giá trị nhạy cảm thay đổi, chỉ lưu tên thuộc tính hoặc dấu hiệu đã thay đổi, không lưu before/after plaintext.
- **Access control:** cấp quyền ingest, search, export, delete, policy change riêng; giới hạn phạm vi theo service/tenant/môi trường và kiểm toán quyền truy cập audit trail.
- **Transport/storage security:** dùng TLS ở ranh giới mạng cần bảo vệ, encryption at rest và key management theo nền tảng; xác thực danh tính của producer và Collector.
- **Retention và xóa:** policy có thể khác nhau theo nhóm event. Nếu có yêu cầu xóa dữ liệu cá nhân và nghĩa vụ giữ audit, cần quy trình pháp lý/kỹ thuật phù hợp; không tự giả định một bên luôn thắng.
- **Phân loại dữ liệu:** actor ID, IP, user agent, correlation ID và before/after có thể là dữ liệu nhạy cảm tùy ngữ cảnh. Không đưa chúng vào metric labels cardinality rất cao hoặc dashboard public.
- **Kiểm soát cấu hình:** ghi audit khi thay đổi retention, quyền truy cập, exporter/collector routing hoặc bật/tắt audit; quản trị audit phải chịu kiểm soát độc lập.

Lưu audit lâu hơn không đồng nghĩa càng tốt. Giá trị phải còn sử dụng được, bảo vệ được và có thể truy xuất trong thời hạn cần thiết.

## 11. Tích hợp vào Java logging stack

**SLF4J là facade**, còn backend như Logback/Log4j2 chịu trách nhiệm filter, appender, queue và formatter. JUL có `Logger`/`Handler` riêng. Khi dùng framework logging thông thường để phát audit, kiểm tra các yếu tố:

- **Level:** nếu audit được ghi ở `INFO` nhưng môi trường đặt root ở `WARN`, bản ghi có thể bị loại. Một audit path có chính sách riêng cần tránh phụ thuộc vào log level chung.
- **Sampling/filter:** nếu policy yêu cầu lưu mọi audit event, không cho chúng đi qua sampling có thể drop.
- **Structured encoder:** event type, actor, target, outcome, ID và timestamp được giữ thành trường truy vấn thay vì chỉ message text.
- **Context propagation:** `request_id`/`trace_id` từ MDC có thể không đi theo task trên `ExecutorService` hoặc reactive pipeline; phải truyền context đúng và dọn/khôi phục trong `finally`.
- **Async và flush:** log ghi vào queue RAM không tự nhiên bền qua crash. Kiểm sự kiện khi shutdown, overload và network partition.
- **Provider/bridge:** có đúng backend đang hoạt động và không có nhiều provider hoặc route log trùng.

Đoạn minh họa cho API SLF4J:

```java
auditLogger.info(
        "audit event_id={} action={} actor_id={} target_id={} outcome={}",
        eventId, action, actorId, targetId, outcome);
```

Đây **không phải chương trình độc lập**; cần một `auditLogger` được cấu hình trong ứng dụng. Nó vẫn chỉ tạo **log text có tham số** nếu không có encoder/structured arguments bổ sung. Không coi lời gọi này là bảo đảm bền vững. Với yêu cầu transaction/audit nghiêm ngặt, dùng **audit writer hoặc outbox** có hợp đồng lưu trữ riêng, và có thể gửi bản sao đã được chấp nhận vào logging backend để quan sát.

### Không dùng MDC làm nguồn sự thật của actor

MDC hữu ích để correlation nhưng có thể bị mất khi chuyển thread hoặc bị rò rỉ khi thread pool tái sử dụng. `actorId` của audit event phải được lấy từ context đã xác thực tại điểm xử lý hành động và truyền theo hợp đồng tin cậy. Nếu actor không được xác thực, ghi một định danh thích hợp như `ANONYMOUS` hoặc `UNKNOWN` cùng lý do, không tự gán danh tính suy đoán.

## 12. Truy vấn và đối chiếu audit event

Audit trail cần trả lời được các câu hỏi điều tra:

- Ai đã thay đổi vai trò của `user-7` trong một khoảng thời gian?
- Lệnh thay đổi có thành công không? Giá trị trước và sau là gì? Có approval và policy version tương ứng không?
- Có bao nhiêu lần truy cập bị từ chối vào tài nguyên nhạy cảm bởi một principal?
- Event có tồn tại trong storage lâu dài dù instance phát log đã restart không?
- Có sự kiện trùng do retry hoặc bị thiếu so với DB transaction/outbox không?

Ví dụ truy vấn khái niệm:

```sql
SELECT occurred_at, event_id, actor_id, action, target_id,
       outcome, before_role, after_role, request_id
FROM audit_events
WHERE target_id = 'user-7'
  AND action = 'ROLE_CHANGE'
ORDER BY occurred_at, event_id;
```

SQL này chỉ minh họa một schema table đã được hệ thống thiết kế; không phải cú pháp truy vấn của mọi cloud log service. Với dữ liệu có tenant, quyền truy vấn phải được thực thi bởi backend/app, **không chỉ dựa vào người xem tự thêm `WHERE tenant_id=...`**.

Nếu outbox/broker có semantics at-least-once, hãy nhóm theo `event_id` và điều tra duplicate attempts riêng. Đối chiếu số lượng audit event với nguồn nghiệp vụ có tính bền vững (transaction/change history) thường tin cậy hơn chỉ đếm số log đã có ở backend.

## 13. Các bài kiểm thử nên có

| Tình huống | Điều phải kiểm |
| --- | --- |
| Thay đổi quyền thành công | Có đúng event `SUCCESS`, actor/target, before/after và ID |
| Bị từ chối phân quyền | Có event `DENIED`; trạng thái không thay đổi |
| Validation lỗi trước commit | Outcome đúng; không ghi sai `SUCCESS` |
| Transaction rollback | Không có audit thành công giả; policy cho attempt/failure rõ |
| Crash giữa thay đổi và phát log | Outbox/transaction vẫn cho phép phục hồi event bắt buộc |
| Retry sau mất ACK | Không tạo sự kiện logic thứ hai; dedup theo event ID |
| Nhiều request đồng thời | Actor, target và request context không bị trộn; sequence/version nhất quán khi yêu cầu |
| Nội dung có newline/dấu nháy | JSON parse được, không bị chèn dòng hoặc giả mạo event |
| Hết quota/đầy queue/mất network | Fail-open/fail-closed đúng chính sách; error, backlog và drop đo được |
| Process restart/rotation | Event đã commit bền có thể khôi phục/truy vấn |
| Thay đổi role nhạy cảm | Approval/policy version và actor thực tế được kiểm |
| Lộ dữ liệu nhạy cảm | Không có secret trong event, stack trace hay MDC |
| Retention hết hạn | Hệ thống xóa/giữ theo policy; kiểm quyền delete/export |
| Thay đổi cấu hình audit | Có event/alert về thay đổi retention, quyền hoặc collector route |
| Truy vấn theo tenant | Không đọc được audit của tenant khác khi không có quyền |

Đối với unit test Java, có thể so sánh `AuditEvent` như một record bất biến, xác nhận outcome, request ID, event type và số lượng trước/sau. Integration test cần kiểm **event thật sự được ghi** qua audit writer/DB/Collector tới nơi lưu đúng schema. Failure-injection test với restart, broker timeout và mất ACK cần kiểm hợp đồng, không chỉ giả định `logger.info` luôn thành công.

## 14. SLI/SLO và sức khỏe của audit pipeline

Nếu audit event bắt buộc bị mất mà không có ai biết, hệ thống mất khả năng truy trách nhiệm. Nên có quan sát độc lập:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `audit_events_committed_total` | Số event được ghi bền tại nguồn/outbox |
| `audit_events_exported_total` | Số event được xuất khỏi producer |
| `audit_events_ingested_total` | Số event được tầng ingest chấp nhận |
| `audit_events_queryable_total` | Số event ID độc nhất truy vấn được ở đích |
| `audit_export_errors_total` | Lỗi truyền hoặc nhận ACK |
| `audit_queue_depth` / `oldest_event_age` | Backlog và nguy cơ vượt deadline |
| `audit_duplicate_attempts_total` | Gửi trùng do retry |
| `audit_integrity_failures_total` | Vi phạm hash/signature/schema khi xác minh |
| `audit_pipeline_heartbeat` | Phát hiện tuyến audit ngừng hoạt động |

Tên metric **chỉ là ví dụ**, không có sẵn trong mọi JDK logger/Collector. SLI end-to-end có thể là **tỷ lệ event ID đã commit tại nguồn và truy vấn được ở kho audit trong thời hạn xác định**. SLO phải có thời gian đo, phạm vi event, deadline và ngoại lệ rõ. Với audit yêu cầu không mất, cần hợp đồng durability và reconciliation chứ không chỉ một mức phần trăm “đẹp”.

Alert khi producer vẫn có transaction nhưng outbox backlog tăng, Collector ngừng nhận event, identity/permission log rate đột ngột bằng không hoặc retention bị đổi ngoài quy trình. Dùng canary và metrics độc lập để phát hiện khi **chính hệ thống logging đang im lặng**.

## 15. Các sai lầm thường gặp

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Chỉ ghi `"User updated"` | Không biết ai, đối tượng nào, kết quả ra sao | Schema actor/action/target/outcome |
| Dùng IP hoặc username từ header làm actor đã xác minh | Có thể giả mạo nguồn sự kiện | Lấy từ authentication context tin cậy |
| Ghi `SUCCESS` trước commit | Rollback vẫn có audit sai | Gắn outcome với trạng thái commit |
| Chỉ log thành công | Bỏ sót denied attempts | Ghi sự kiện từ chối theo policy |
| Dùng `request_id` làm event ID duy nhất | Một request nhiều hành động có thể bị gộp nhầm | Tạo ID riêng cho từng sự kiện logic |
| Retry mà mỗi lần sinh event ID mới | Đếm trùng hành động | Giữ ID ổn định khi gửi lại |
| Gửi audit qua INFO logger chung rồi giả định bền | Level/filter/queue có thể bỏ | Audit writer, outbox và pipeline riêng khi cần |
| Đưa token/password vào `changes.before/after` | Lộ dữ liệu nhạy cảm | Redact, chỉ lưu metadata không bí mật |
| Tin rằng file append-only là tamper-proof | Admin vẫn có thể sửa/xóa | Quyền tối thiểu, anchor/hash/signature được bảo vệ |
| Dùng trace sampling cho audit bắt buộc | Có thể mất event cần giữ | Phân tách sampling policy |
| Xử lý audit đồng bộ qua mạng không timeout | Lỗi log làm treo nghiệp vụ | Deadline, policy lỗi và buffering có hợp đồng |
| Không kiểm restart/queue full/ACK loss | Không biết mất hoặc trùng event | Test failure-injection và reconciliation |
| Không audit thay đổi audit config | Kẻ có quyền có thể tắt dấu vết | Giám sát độc lập và phân quyền quản trị |

## 16. Checklist áp dụng cho Java service

- [ ] Danh mục event audit và hành động bắt buộc ghi đã được định nghĩa từ risk và yêu cầu nghiệp vụ?
- [ ] Mỗi event có `event_id`, timestamp, actor, target, action, outcome, reason và correlation ID cần thiết?
- [ ] Actor và outcome lấy từ identity/quyết định **đã xác minh**, không từ header hoặc thông điệp client tùy ý?
- [ ] Thành công, từ chối, lỗi, pending và rollback được biểu diễn đúng điểm commit?
- [ ] Có schema versioning, validation, escape và giới hạn độ dài để tránh log injection?
- [ ] Không ghi secret, credential plaintext hoặc field nhạy cảm không cần thiết?
- [ ] Có chiến lược transaction/outbox hoặc storage đủ bền khi audit bắt buộc?
- [ ] Đã thiết kế retry/idempotency/dedup và nêu rõ nghĩa của ACK?
- [ ] Đã xác định retention, quyền xem/xóa/xuất và chống sửa trái phép theo chính sách?
- [ ] Có metrics, heartbeat, end-to-end probe, đối chiếu event thiếu/trùng và cảnh báo khi pipeline lỗi?
- [ ] Integration test kiểm được cả event `SUCCESS` và `DENIED`, crash/restart và nhiều request đồng thời?

**Kết luận:** một audit event tốt là **bằng chứng có cấu trúc về hành động**, không chỉ là một dòng message. Trong Java, hãy thiết kế đúng actor–action–target–outcome, ghi trạng thái trước/sau có ý nghĩa, tách dữ liệu nhạy cảm và áp dụng cơ chế lưu trữ/đối chiếu phù hợp. Khả năng truy trách nhiệm chỉ đáng tin khi event **đúng nội dung, đúng thời điểm, đủ bền, không dễ bị sửa và truy vấn được khi cần**.
