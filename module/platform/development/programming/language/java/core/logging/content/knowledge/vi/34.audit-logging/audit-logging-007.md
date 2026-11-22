# Kết quả thao tác trong Audit Logging Java

## 1. Vì sao Audit Logging phải ghi kết quả thao tác?

Một audit log có giá trị phải giúp người đọc trả lời: **ai thực hiện hoặc yêu cầu hành động gì, đối với tài nguyên nào, tại thời điểm nào, và kết quả thực tế ra sao?** Ghi đơn thuần `User changed role` có thể gây hiểu nhầm: yêu cầu có thể đã bị từ chối, input không hợp lệ, database rollback, một phần dữ liệu đã cập nhật hoặc job mới được nhận để chạy sau.

Ví dụ các bản ghi:

```text
actor=admin-1 action=ROLE_CHANGE target=user-7 outcome=SUCCEEDED reason=APPLIED
actor=guest-9 action=ROLE_CHANGE target=user-7 outcome=DENIED reason=NOT_AUTHORIZED
actor=admin-1 action=ROLE_CHANGE target=user-7 outcome=NO_CHANGE reason=ALREADY_SET
```

Ba yêu cầu trên cùng nhắm tới một loại thao tác, nhưng **không mang cùng kết quả nghiệp vụ**. Sự khác biệt quyết định cách điều tra, thống kê, cảnh báo và chứng minh một thay đổi có thật đã xảy ra.

Cần tách bốn khái niệm:

- **Request/attempt:** người hoặc hệ thống đã yêu cầu thực hiện một hành động.
- **Decision:** hệ thống xác thực, kiểm tra quyền và đánh giá điều kiện nghiệp vụ.
- **Business outcome:** thao tác được thực thi và đạt hay không đạt mục tiêu theo hợp đồng.
- **Audit delivery:** bản ghi kết quả đã được gửi/lưu tới mức nào: tạo trong memory, enqueue, appender xử lý, collector xác nhận hoặc lưu bền vững.

Một event có `outcome=SUCCEEDED` có thể phản ánh đúng việc database đã commit nhưng **bản thân event vẫn mất** nếu đường logging lỗi. Ngược lại, một event `DENIED` có thể được ghi audit thành công dù không có dữ liệu nghiệp vụ nào được cập nhật.

**Nguyên tắc:** không đồng nhất `logger.info(...)` trả về, API trả HTTP 200 hay một phương thức Java không ném exception với kết quả thao tác đã được xác minh và đã có audit bền vững.

## 2. Trường kết quả trong schema audit

Một event kết quả thường chứa những thông tin sau:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `eventId` | ID của một audit event | Dùng phát hiện bản gửi trùng, cần cấp độc nhất theo phạm vi |
| `operationId` | ID của một hành động nghiệp vụ logic | Giữ chung khi có retry hoặc các bước async |
| `attemptId` / `attemptNo` | ID/lần thử của thao tác | Tách lần thử khỏi kết quả cuối |
| `actorType`, `actorId` | Ai yêu cầu hoặc thực hiện | Phải dựa vào authenticated principal/service identity |
| `action` | Tên loại thao tác chuẩn hóa | Dùng enum/danh sách do hệ thống quản lý |
| `resourceType`, `resourceId` | Đối tượng được tác động | Hạn chế dữ liệu nhạy cảm và log injection |
| `outcome` | Kết quả theo ngữ nghĩa nghiệp vụ | Chỉ chốt khi biết đủ trạng thái |
| `reasonCode` | Lý do ở dạng mã ổn định | Không copy raw exception message hoặc token |
| `occurredAt` | Thời điểm sự kiện ở nguồn | Khác với thời điểm collector ingest |
| `requestId` / `traceId` | Liên kết sự kiện với request hoặc trace | Không dùng secret làm correlation ID |
| `schemaVersion` | Phiên bản schema của event | Phục vụ tương thích consumer |
| `durationMs` | Thời gian xử lý trong ranh giới được định nghĩa | Không phải bằng chứng thao tác đã commit |

Ví dụ một event JSON:

```json
{
  "schemaVersion": 1,
  "eventId": "ev-001",
  "occurredAt": "2026-01-01T10:00:00Z",
  "service": "identity-service",
  "operationId": "op-19",
  "requestId": "req-19",
  "actor": { "type": "USER", "id": "admin-1" },
  "action": "ROLE_CHANGE",
  "resource": { "type": "USER_ROLE", "id": "user-7" },
  "outcome": "SUCCEEDED",
  "reasonCode": "APPLIED",
  "durationMs": 37
}
```

ID, thời gian và dịch vụ trong JSON chỉ để minh họa. Nếu mã định danh thực tế là dữ liệu cá nhân, phải giảm thiểu/pseudonymize, phân quyền và đặt retention phù hợp. Không đưa bearer token, session cookie hoặc credentials vào `actor.id`, `resource.id` hay `requestId`.

**Outcome** và **severity** không phải một trường: `INFO` không đồng nghĩa `SUCCEEDED`, `WARN` không tự động là `DENIED`, `ERROR` cũng không chắc có rollback. Level phục vụ chẩn đoán/vận hành; outcome mô tả kết quả nghiệp vụ.

## 3. Các giá trị outcome thường gặp

Một taxonomy có thể bắt đầu bằng:

| Outcome | Ý nghĩa nghiệp vụ | Ví dụ |
| --- | --- | --- |
| `SUCCEEDED` | Mục tiêu đã đạt, được xác nhận ở ranh giới quy định | Role mới đã commit |
| `DENIED` | Chính sách xác thực/ủy quyền không cho phép | Actor không có quyền export |
| `REJECTED` | Input hoặc điều kiện nghiệp vụ không hợp lệ trước khi thay đổi | Vai trò không tồn tại, constraint sai |
| `FAILED` | Đã cố thực thi nhưng biết rõ mục tiêu không đạt | Transaction rollback được xác nhận |
| `NO_CHANGE` | Yêu cầu hợp lệ nhưng trạng thái vốn đã đúng | Gán lại cùng role |
| `PENDING` | Yêu cầu được tiếp nhận, chưa có kết quả cuối | Job chạy nền đã enqueue |
| `PARTIALLY_SUCCEEDED` | Một phần yêu cầu đã có hiệu lực | 8/10 mục bulk update thành công |
| `CANCELED` | Quy trình đã hủy theo hợp đồng và biết trạng thái hủy | Job chờ được hủy |
| `UNKNOWN` | Chưa đủ bằng chứng xác định kết quả | Timeout sau khi gửi lệnh cho bên ngoài |

Đây là **gợi ý về schema**, không phải enum có sẵn của Java, SLF4J, JUL, Logback hay Log4j2. Một hệ thống đơn giản có thể dùng ít trạng thái hơn; một workflow nhiều bước có thể cần thêm `ROLLED_BACK`, `COMPENSATED` hoặc `EXPIRED`. Hãy định nghĩa chính xác ngữ nghĩa và quản lý version.

### Các phân biệt quan trọng

**DENIED khác REJECTED.** `DENIED` do policy/permission, còn `REJECTED` thường do request sai hoặc không thỏa điều kiện nghiệp vụ. Nếu việc trả lý do chi tiết tiết lộ tài nguyên tồn tại hay không, quy tắc audit và thông báo bên ngoài có thể khác nhau: audit nội bộ ghi mã đã phân quyền, API trả thông điệp an toàn.

**FAILED khác UNKNOWN.** Một timeout không chứng minh thao tác phía xa thất bại. Bên nhận có thể đã commit rồi response hoặc acknowledgement bị mất. Khi không chắc, dùng `UNKNOWN` hoặc trạng thái đối soát, không đánh dấu `FAILED` để sau đó retry mù.

**NO_CHANGE không mặc định là lỗi.** Với API `PUT` idempotent, không có mutation vì trạng thái đã đúng có thể đáp ứng hoàn toàn yêu cầu.

**PENDING chưa phải thành công cuối.** HTTP `202 Accepted`, queue nhận job, hoặc service bắt đầu chạy chỉ xác nhận một bước của lifecycle.

**PARTIALLY_SUCCEEDED cần thông tin định lượng.** Chỉ ghi một nhãn “partial” không đủ để dựng lại thay đổi. Có thể thêm số lượng thành công/thất bại và liên kết event từng resource, nhưng không đưa danh sách dữ liệu nhạy cảm vào log thu thập rộng.

## 4. Chốt outcome ở đúng thời điểm

Một lỗi phổ biến:

```java
// SAI: tuyên bố success trước khi transaction hoàn thành.
logger.info("Audit action=ROLE_CHANGE outcome=SUCCEEDED");
repository.updateRole(userId, role);
transaction.commit();
```

Nếu `updateRole` hoặc `commit` thất bại, event đã có kết quả sai. Đây chỉ là đoạn minh họa trong mã có sẵn logger/repository/transaction, không phải chương trình độc lập.

Quy trình đúng về mặt ngữ nghĩa:

```text
Request
   |
   +-- Kiểm tra actor/permission -- không đạt --> DENIED
   |
   +-- Validate business input ---- không đạt --> REJECTED
   |
   v
Thực thi
   |
   +-- Trạng thái đã như mong muốn -----------> NO_CHANGE
   |
   +-- Lỗi rõ ràng, rollback được xác nhận ---> FAILED
   |
   +-- Kết quả commit không rõ ---------------> UNKNOWN
   |
   +-- Commit thành công ---------------------> SUCCEEDED
```

Một vài điểm cần chú ý:

1. Phải biết **mốc commit**. Thực hiện `executeUpdate()` không ném exception trước khi transaction commit chưa đủ kết luận kết quả bền vững.
2. Đếm số hàng hoặc xác nhận điều kiện thay đổi. Lệnh update trả về 0 hàng không nên tự động thành `SUCCEEDED` nếu resource không tồn tại hoặc đã có version conflict.
3. Khi thao tác có side effect ngoài database (network, email, payment, file), rollback database không tự hoàn tác side effect ấy.
4. Nếu một lỗi xảy ra sau khi transaction có thể đã commit nhưng client mất kết nối, kết quả cần được đối soát bằng ID/idempotency key đáng tin cậy.
5. Nếu hệ thống xử lý được lỗi bằng retry, có thể có attempt thất bại nhưng logical operation cuối cùng thành công; phải phân biệt hai mức.

Đừng log cả `SUCCEEDED` và `FAILED` cho cùng **một kết quả cuối** chỉ vì hai tầng code đều có catch/finally. Nếu muốn audit nhiều attempt, dùng `attemptId` hoặc `eventType` riêng để người đọc hiểu mỗi event đang mô tả điều gì.

## 5. Không suy trực tiếp outcome từ mã HTTP hoặc exception

| Tín hiệu | Điều có thể biết | Không được suy ra |
| --- | --- | --- |
| `200 OK` | API xử lý request theo contract | Mọi background task đã xong |
| `201 Created` | Resource được tạo theo contract | Audit sink đã lưu bền vững |
| `202 Accepted` | Đã nhận lệnh xử lý sau | Tác vụ cuối `SUCCEEDED` |
| `400 Bad Request` | Request bị coi không hợp lệ | Luôn là lỗi hạ tầng `FAILED` |
| `403 Forbidden` | Bị từ chối quyền | Audit `DENIED` đã được lưu thành công |
| `409 Conflict` | Conflict điều kiện hoặc version | Không thể xử lý qua retry/đối soát |
| `500 Internal Server Error` | Server có lỗi | Không có side effect nào được commit |
| `504 Gateway Timeout` | Gateway chờ quá hạn | Backend chắc chắn chưa xử lý |

Cũng cần phân biệt ngoại lệ từ mã Java với kết quả:

- Không ném exception **không chứng minh** một tác vụ async đã hoàn tất.
- Một exception sau commit không biến thay đổi đã commit thành thất bại; có thể là lỗi gửi response hoặc ghi audit.
- Bắt mọi `Exception` rồi luôn tạo `FAILED` có thể che trường hợp `UNKNOWN` hay `PARTIALLY_SUCCEEDED`.
- Lỗi khi ghi **audit sink** không nên được gắn sai thành outcome của thao tác nghiệp vụ, trừ khi contract quy định phải fail closed.

Audit phải bám vào một quyết định kết quả được định nghĩa rõ trong ứng dụng, không được suy bằng việc parse stack trace hay ghép message từ exception.

## 6. Reason code và event type

Nên quản lý `reasonCode` như một tập mã ổn định, có thể phân nhóm:

| Nhóm | Reason code ví dụ | Ý nghĩa |
| --- | --- | --- |
| Áp dụng thành công | `APPLIED` | Mutation đạt mục tiêu |
| Idempotent | `ALREADY_SET` | Đã đúng trạng thái, không cần đổi |
| Bảo mật | `NOT_AUTHORIZED` | Không đủ quyền |
| Validation | `INVALID_ROLE` | Tên role sai |
| Dữ liệu | `TARGET_NOT_FOUND` | Đối tượng không tồn tại (nếu policy cho phép tiết lộ) |
| Concurrency | `VERSION_CONFLICT` | Optimistic lock không còn đúng |
| Hạ tầng | `DEPENDENCY_UNAVAILABLE` | Phụ thuộc tạm không khả dụng |
| Không rõ | `RESULT_UNCONFIRMED` | Cần đối soát |
| Bulk | `PARTIAL_APPLY` | Chỉ một phần được áp dụng |

**Không dùng `exception.getMessage()` làm reason code.** Nó có thể thay đổi theo thư viện, chứa URL, SQL, token hoặc dữ liệu người dùng. Thay vào đó, dùng mã định nghĩa sẵn; nếu cần chi tiết chẩn đoán, đặt thông tin an toàn trong operational log riêng có quyền truy cập thích hợp.

Đối với workflow nhiều bước, nên tách thêm `eventType`:

- `REQUESTED`: yêu cầu xuất hiện.
- `ACCEPTED_FOR_PROCESSING`: hệ thống cam kết sẽ cố thực hiện.
- `STARTED`: worker thực sự bắt đầu.
- `ATTEMPT_FINISHED`: một lần thử đã kết thúc.
- `OPERATION_FINISHED`: kết quả cuối của logical operation.

`eventType` nói sự kiện thuộc giai đoạn nào; `outcome` nói kết quả tại giai đoạn đó. Không nhất thiết phải tạo toàn bộ event này cho mọi thao tác, nhưng khi đã tạo cần duy trì định nghĩa ổn định để consumer không đếm nhầm.

## 7. Ví dụ Java 17 độc lập: ghi kết quả thay đổi quyền

Ví dụ sau không phụ thuộc thư viện ngoài. Nó mô phỏng một thao tác `ROLE_CHANGE` và lưu các `AuditEvent` trong danh sách. Mục tiêu là chứng minh **kết quả đúng với nhánh nghiệp vụ**, không phải thể hiện một pipeline audit bền vững.

### 7.1. Tạo tệp `AuditOutcomeDemo.java`

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AuditOutcomeDemo {
    enum Outcome {
        SUCCEEDED, NO_CHANGE, DENIED, REJECTED, FAILED
    }

    record Decision(Outcome outcome, String reasonCode) {}

    record AuditEvent(
            String eventId,
            Instant occurredAt,
            String requestId,
            String actorId,
            String action,
            String resourceId,
            Outcome outcome,
            String reasonCode
    ) {}

    static final class RoleService {
        private final Map<String, String> roles =
                new HashMap<>(Map.of("user-7", "viewer"));

        Decision changeRole(
                String actorId, String targetId, String desiredRole) {

            if (!"admin-1".equals(actorId)) {
                return new Decision(
                        Outcome.DENIED, "NOT_AUTHORIZED");
            }

            if (!"viewer".equals(desiredRole)
                    && !"editor".equals(desiredRole)) {
                return new Decision(
                        Outcome.REJECTED, "INVALID_ROLE");
            }

            // Giả lập dependency lỗi trước khi thay đổi dữ liệu.
            if ("user-offline".equals(targetId)) {
                return new Decision(
                        Outcome.FAILED, "DEPENDENCY_UNAVAILABLE");
            }

            if (!roles.containsKey(targetId)) {
                return new Decision(
                        Outcome.REJECTED, "TARGET_NOT_FOUND");
            }

            if (desiredRole.equals(roles.get(targetId))) {
                return new Decision(
                        Outcome.NO_CHANGE, "ALREADY_SET");
            }

            roles.put(targetId, desiredRole);
            return new Decision(Outcome.SUCCEEDED, "APPLIED");
        }

        String currentRole(String targetId) {
            return roles.get(targetId);
        }
    }

    private static void attempt(
            RoleService service, List<AuditEvent> audit,
            String eventId, String actorId, String targetId,
            String desiredRole, String requestId) {

        Decision decision =
                service.changeRole(actorId, targetId, desiredRole);

        // Thời gian giả cố định để ví dụ tái lập được.
        Instant time = Instant.parse("2026-01-01T10:00:00Z")
                .plusSeconds(audit.size());

        AuditEvent event = new AuditEvent(
                eventId, time, requestId, actorId,
                "ROLE_CHANGE", targetId,
                decision.outcome(), decision.reasonCode());

        audit.add(event); // Chỉ trong bộ nhớ; KHÔNG durable.
        System.out.println(
                event.eventId() + " " + event.outcome()
                        + " " + event.reasonCode());
    }

    public static void main(String[] args) {
        RoleService service = new RoleService();
        List<AuditEvent> audit = new ArrayList<>();

        attempt(service, audit, "EV-001",
                "admin-1", "user-7", "editor", "req-1");
        attempt(service, audit, "EV-002",
                "admin-1", "user-7", "editor", "req-2");
        attempt(service, audit, "EV-003",
                "guest-9", "user-7", "viewer", "req-3");
        attempt(service, audit, "EV-004",
                "admin-1", "user-7", "owner", "req-4");
        attempt(service, audit, "EV-005",
                "admin-1", "user-offline", "editor", "req-5");

        System.out.println("finalRole="
                + service.currentRole("user-7"));
        System.out.println("auditEvents=" + audit.size());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AuditOutcomeDemo.java
java AuditOutcomeDemo
```

**Stdout chính xác:**

```text
EV-001 SUCCEEDED APPLIED
EV-002 NO_CHANGE ALREADY_SET
EV-003 DENIED NOT_AUTHORIZED
EV-004 REJECTED INVALID_ROLE
EV-005 FAILED DEPENDENCY_UNAVAILABLE
finalRole=editor
auditEvents=5
```

### 7.2. Diễn giải kết quả

- **EV-001:** admin hợp lệ đổi `user-7` từ viewer thành editor; map đã đổi rồi trả `SUCCEEDED`.
- **EV-002:** gán editor lần nữa, không cần mutation; `NO_CHANGE` là kết quả có ý nghĩa riêng.
- **EV-003:** guest không đủ quyền; `DENIED` được quyết định trước việc kiểm tra chi tiết role/resource, giảm khả năng tiết lộ thông tin cho actor không được phép.
- **EV-004:** admin hợp lệ nhưng `owner` không nằm trong whitelist, nên `REJECTED`.
- **EV-005:** dependency được mô phỏng là không khả dụng **trước khi mutation**, vì vậy `FAILED` là kết luận chính xác trong mô hình này. Nếu lỗi xảy ra sau side effect không đối soát, phải dùng `UNKNOWN`/`PARTIAL` thay vì mặc định không có thay đổi.
- `finalRole=editor` chứng minh chỉ request đầu tác động trạng thái; `auditEvents=5` chứng minh cả năm quyết định đều có event, không có nghĩa năm mutation.

**Giới hạn:** `ArrayList` và `HashMap` không bền vững, không thread-safe và không nguyên tử với nhau. Nếu chương trình crash hoặc `audit.add` thất bại sau mutation, có thể thiếu audit. Đồng hồ và ID được tạo cố định chỉ để có stdout tái lập. Trong hệ thống thực, cần ID/timestamp tin cậy, transaction và cơ chế lưu/đồng bộ phù hợp; không lấy ví dụ này làm implementation production.

Java `record` giúp event giữ giá trị immutable ở mức field, nhưng nếu record chứa object mutable thì bản thân object vẫn có thể bị sửa. Khi xây structured audit event, ưu tiên giá trị đơn giản/immutable và snapshot ngữ cảnh tại thời điểm kết quả được xác minh.

## 8. Audit outcome cho thao tác bất đồng bộ

Một API nhận lệnh tạo báo cáo và xử lý qua job queue:

```text
T0: POST /reports -> HTTP 202 Accepted
    eventType=REQUESTED; outcome=PENDING; operationId=op-81

T1: Worker nhận và bắt đầu chạy
    eventType=STARTED; operationId=op-81

T2: Worker tạo file và commit trạng thái
    eventType=OPERATION_FINISHED
    outcome=SUCCEEDED hoặc FAILED; operationId=op-81
```

**T0 không phải T2.** Nếu audit action là `EXPORT_REQUEST_ACCEPTED` thì kết quả `SUCCEEDED` tại T0 có thể đúng cho riêng hành động nhận request. Nhưng nếu action là `EXPORT_COMPLETED`, T0 chỉ là `PENDING`. Mọi hệ thống cần định nghĩa action rõ để tránh hai bên hiểu khác nhau.

Với audit trail append-only, phát event mới khi trạng thái chuyển:

```json
{"eventId":"ev-201","operationId":"op-81","eventType":"REQUESTED","outcome":"PENDING"}
{"eventId":"ev-202","operationId":"op-81","eventType":"OPERATION_FINISHED","outcome":"SUCCEEDED"}
```

Không âm thầm sửa `PENDING` thành `SUCCEEDED` trong bản ghi audit cũ nếu cần lịch sử chuyển trạng thái. Có thể duy trì thêm bảng `current_operation_status` để truy vấn trạng thái cuối nhanh hơn, song song với audit trail append-only.

### Khi job thất bại hoặc không báo kết quả

- Nếu worker xác nhận đã rollback và không có side effect: `FAILED`.
- Nếu job bị hủy có xác nhận: `CANCELED`.
- Nếu một phần công việc đã có hiệu lực: `PARTIALLY_SUCCEEDED` hoặc kết quả theo contract saga.
- Nếu worker mất kết nối sau khi gửi lệnh đến hệ thống khác: `UNKNOWN` cho đến khi đối soát.
- Nếu `PENDING` kéo dài quá SLA: phát cảnh báo `stale pending`; đừng tự chuyển thành `FAILED` nếu chưa có bằng chứng.
- Nếu job được retry: liên kết các attempt qua `operationId` và đảm bảo không ghi kết quả cuối nhiều lần sai nghĩa.

Với distributed system, timestamp của các máy có thể lệch; event có thể ingest không đúng thứ tự sinh. Hãy dùng ID, sequence trong phạm vi có bảo đảm, các quan hệ nhân quả và timestamp source/ingest để dựng lại hành trình.

## 9. Retry, idempotency và event trùng

Ví dụ một logical operation:

```text
operationId=op-7
 attempt=1 -> FAILED (transient dependency error)
 attempt=2 -> FAILED (transient dependency error)
 attempt=3 -> SUCCEEDED
 logical final outcome -> SUCCEEDED
```

Thống kê **attempt** có hai lỗi và một thành công; thống kê **operation** có một hành động cuối thành công. Không được trộn hai mẫu đếm và suy ra tỷ lệ lỗi của khách hàng.

| Định danh | Phạm vi | Hành vi khi retry |
| --- | --- | --- |
| `eventId` | Một sự kiện audit | Khi truyền lại cùng event do mất ack, giữ ID để dedup |
| `operationId` | Một hành động logic | Giữ nguyên qua retry và bước async |
| `attemptId` / `attemptNo` | Một lần thử thực thi | Mỗi attempt có ID hoặc số riêng |
| `requestId` | Một HTTP/request cụ thể | Có thể đổi khi client gửi request mới |
| `traceId` | Một distributed trace | Có thể đổi qua những lần retry tùy kiến trúc |

Một `eventId` nhận hai lần ở collector do replay là **duplicate delivery**, không nhất thiết có hai thao tác. Nếu consumer quan tâm tính duy nhất, cần cơ chế idempotent processing/deduplication. Retry hoặc transactional outbox thường cho khả năng at-least-once; **không tự tạo exactly-once end-to-end**.

### `NO_CHANGE` và yêu cầu idempotent

Đối với `PUT /users/7/role=editor`, request thứ hai có thể không tạo mutation vì hệ thống đã có editor. Kết quả `NO_CHANGE` giúp phân biệt:

- Yêu cầu **hợp lệ, mục tiêu đã đạt**.
- Dữ liệu **không được sửa lần nữa**.
- Không có lỗi cần báo vận hành.

Nếu API contract chỉ hiển thị HTTP 200, audit vẫn có thể ghi `outcome=NO_CHANGE` để phân tích nội bộ; đừng buộc nó thành `FAILED`.

## 10. Bulk operation, partial success và compensation

Một request có thể tác động nhiều resource. Giả sử admin cấp role cho 10 user: 8 thành công, 2 thất bại sau khi một phần thay đổi đã commit. Audit tổng thể có thể là:

```json
{
  "operationId": "op-bulk-41",
  "action": "BULK_ROLE_CHANGE",
  "outcome": "PARTIALLY_SUCCEEDED",
  "reasonCode": "PARTIAL_APPLY",
  "requestedCount": 10,
  "succeededCount": 8,
  "failedCount": 2
}
```

Kết quả aggregate nên liên kết tới event của từng item hoặc bảng chi tiết đủ quyền truy cập. Đừng log nguyên toàn bộ email/PII để diễn giải kết quả nếu có thể dùng resource ID đã đánh giá an toàn.

**Nếu toàn bộ thao tác nằm trong một transaction duy nhất và rollback**, kết quả đã commit có thể bằng 0; lúc đó không ghi `PARTIALLY_SUCCEEDED` chỉ vì code đã chạy được 8 câu `UPDATE` trước khi rollback. Partially succeeded chỉ hợp lệ khi side effect một phần đã **có hiệu lực** và không bị rollback toàn bộ.

### Saga và bù trừ

Ví dụ một bước tạo quyền truy cập đã commit, bước gửi thông báo thất bại, hệ thống chạy compensation hoàn nguyên quyền:

1. Ghi event bước cấp quyền `SUCCEEDED`.
2. Ghi event gửi thông báo `FAILED`.
3. Ghi event thử compensation và kết quả thực tế.
4. Ghi event outcome cuối của toàn operation theo contract.

Đừng xóa hay chỉnh event đầu thành “chưa từng thành công” chỉ vì trạng thái cuối quay về ban đầu. **Audit trail mô tả những gì đã xảy ra**, không chỉ snapshot hiện tại.

## 11. Lưu kết quả audit đáng tin: transaction outbox

Cách làm thiếu an toàn:

```text
COMMIT thay đổi quyền thành công
    |
    v
logger.info("ROLE_CHANGE SUCCEEDED")
    |
    X  process crash trước khi log tới sink
    |
    v
Dữ liệu đã đổi nhưng audit thiếu event
```

Khi state nghiệp vụ và audit event có thể nằm trong **cùng database transaction**, mẫu transactional outbox giúp giảm khoảng trống này:

```text
Database transaction
+--------------------------------------+
| UPDATE business state                |
| INSERT audit_outbox event            |
+--------------------------------------+
              COMMIT
                 |
                 v
         Outbox dispatcher
         retry + dedup + ack
                 |
                 v
            Audit sink
```

Pseudocode minh họa, không phải script đầy đủ cho mọi RDBMS:

```sql
BEGIN;

-- Kiểm tra quyền, điều kiện, version và số hàng cập nhật
-- theo isolation/locking đúng yêu cầu.
UPDATE user_roles
SET role = 'editor'
WHERE user_id = 'user-7';

-- Chỉ dùng SUCCEEDED nếu điều kiện cập nhật được xác minh.
INSERT INTO audit_outbox (
    event_id, operation_id, action,
    resource_id, outcome, reason_code
) VALUES (
    'ev-501', 'op-501', 'ROLE_CHANGE',
    'user-7', 'SUCCEEDED', 'APPLIED'
);

COMMIT;
```

Nếu `UPDATE` không khớp resource/version, không được ghi kết quả thành công một cách mù quáng; phải kiểm tra số hàng và điều kiện. Trong transaction, mutation và outbox insert cùng commit hoặc cùng rollback.

Dispatcher gửi các event đã commit đến collector và chỉ đánh dấu đã giao khi đạt mốc xác nhận theo giao thức. Khi collector nhận được event nhưng response/ack mất, dispatcher có thể gửi lại; event ID và dedup là cần thiết.

**Outbox không tự bảo đảm exactly-once.** Nó giải quyết bài toán atomicity giữa business state và việc lưu event chờ gửi trong một transaction. Độ bền của collector, thứ tự giao, retention và reconciliation còn là các hợp đồng riêng.

### Audit kết quả không có business commit

`DENIED` và `REJECTED` thường không tạo mutation. `FAILED` do business transaction rollback cũng không còn outbox event được insert **trong transaction đã rollback**. Vì vậy các outcome này có thể cần transaction audit riêng/kênh audit bảo mật phù hợp. Không đặt audit `DENIED` vào một transaction rồi rollback, sau đó ngạc nhiên vì không còn bản ghi.

Nếu luật nghiệp vụ yêu cầu **không hoàn thành thao tác khi không thể lưu audit**, hệ thống phải thiết kế fail closed với mốc ack/commit phù hợp. Không tự động áp dụng cho mọi log vì một collector chậm có thể làm toàn bộ API ngừng đáp ứng.

## 12. Tích hợp với SLF4J/Logback: không nhầm log message và audit contract

SLF4J là facade; backend như Logback nhận message/marker/context. Nó không cung cấp sẵn outcome nghiệp vụ. Ứng dụng phải định nghĩa event và chính sách lưu phù hợp.

Đoạn minh họa trong ứng dụng có logger và biến đã khai báo:

```java
logger.info(
    "audit action={} eventId={} operationId={} actorId={} "
        + "resourceId={} outcome={} reasonCode={}",
    "ROLE_CHANGE",
    eventId,
    operationId,
    actorId,
    resourceId,
    outcome,
    reasonCode
);
```

Cách viết này tạo **message văn bản**, không tự động thành JSON/structured event. Nếu downstream cần truy vấn riêng các field, hãy dùng structured logging API/encoder hỗ trợ và xác minh output tại collector. Đừng chỉ đặt trường vào một chuỗi text rồi tin rằng parser luôn phân tích chính xác.

Đặc biệt:

- Logger level/filter có thể làm mất một event audit ở `INFO` khi `root=WARN`.
- Async appender có thể drop event theo discard/backpressure policy.
- Queue trong memory không durable khi JVM/host crash.
- `logger.info` trả về không chứng minh collector đã nhận.
- Một exception logging có thể được backend báo qua status channel chứ không ném về thread nghiệp vụ.
- MDC hỗ trợ correlation, nhưng không tự truyền qua mọi `ExecutorService` hoặc async boundary; phải quản lý context và clear/restore trong `finally`.

Đối với audit quan trọng, nên tách luồng event có độ tin cậy/retention riêng khỏi debug logs có thể sampling/drop. Audit event có thể vẫn được xuất thêm dưới dạng log, nhưng nguồn sự thật về kết quả cần theo hợp đồng phù hợp.

## 13. Kiểm thử đúng outcome theo nghiệp vụ

Hãy kiểm tra **cả trạng thái nghiệp vụ và audit event**.

| Case | Trạng thái sau request | Outcome | Reason |
| --- | --- | --- | --- |
| Role change hợp lệ và commit | Role mới có hiệu lực | `SUCCEEDED` | `APPLIED` |
| Actor thiếu quyền | Role không đổi | `DENIED` | `NOT_AUTHORIZED` |
| Role không được phép | Role không đổi | `REJECTED` | `INVALID_ROLE` |
| Gán lại role hiện tại | Role không đổi | `NO_CHANGE` | `ALREADY_SET` |
| DB lỗi, rollback đã xác minh | Không có commit | `FAILED` | `STORAGE_ERROR` |
| Mất kết nối sau lệnh commit | Trạng thái chưa biết | `UNKNOWN` | `RESULT_UNCONFIRMED` |
| Job được enqueue | Chưa hoàn thành | `PENDING` | `ACCEPTED_FOR_PROCESSING` |
| Bulk 8/10 thành công | 8 thay đổi có hiệu lực | `PARTIALLY_SUCCEEDED` | `PARTIAL_APPLY` |

Đặt test tại ranh giới phù hợp:

1. **Unit test** ánh xạ policy/input → `Decision`, không dùng hạ tầng logging thật nếu chưa cần.
2. **Integration test** dùng repository/transaction và sink thử để đối chiếu state với event.
3. **Fault-injection test** ép rollback, lỗi commit, timeout, sink outage và kiểm tra không ghi `SUCCEEDED` giả.
4. **End-to-end test** xác minh event đến nơi lưu audit theo yêu cầu, có ID/timestamp/schema phù hợp.
5. **Security test** dùng token giả xác nhận không xuất hiện ở field/message/exception/MDC.

Một ví dụ JUnit 5 về logic của phần 7 (mã test minh họa, cần JUnit Jupiter trên classpath, không phải file độc lập chỉ chạy bằng `javac`):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RoleOutcomeTest {
    @Test
    void idempotentRoleChangeIsNotAFailure() {
        AuditOutcomeDemo.RoleService service =
                new AuditOutcomeDemo.RoleService();

        var first = service.changeRole(
                "admin-1", "user-7", "editor");
        var second = service.changeRole(
                "admin-1", "user-7", "editor");

        assertEquals(
                AuditOutcomeDemo.Outcome.SUCCEEDED, first.outcome());
        assertEquals(
                AuditOutcomeDemo.Outcome.NO_CHANGE, second.outcome());
        assertEquals("ALREADY_SET", second.reasonCode());
    }
}
```

Test này mới xác nhận **decision logic**. Nó không kiểm tra một audit event đã được ghi bền vững. Muốn chứng minh audit delivery, cần sink/repository riêng và kiểm tra điểm thành công thực tế, không chỉ mock `logger.info`.

## 14. Kiểm thử retry, concurrency và độ tin cậy

Đối với retry và transaction:

- Sau business commit nhưng trước khi dispatcher gửi, mô phỏng process restart; outbox event vẫn phải tồn tại.
- Collector nhận event rồi mất ack; retry có thể gây duplicate, cần dedup theo `eventId`.
- Worker gửi nhiều event song song; nếu không bảo đảm thứ tự toàn cục thì không assert thứ tự giữa các producer.
- Một operation timeout sau khi gọi dịch vụ ngoài cần đối soát bằng operation ID, không đổi ngay thành `FAILED`.
- Khi concurrent update tạo version conflict, request thất bại phải có outcome phù hợp, không ghi `SUCCEEDED` vì một đoạn code trước đó chạy xong.
- Nếu audit sink lỗi, quan sát metric/backlog hoặc chính sách fail closed; không lẫn lỗi đường audit với kết quả business nếu contract không quy định như vậy.

Khi test logging async, dùng `BlockingQueue` hoặc latch tại sink và `poll(timeout)`; tránh `Thread.sleep(500)` để chờ may rủi. Với các event **không được xuất hiện**, cần sentinel/barrier hoặc mốc drain dựa trên hợp đồng của backend, không kết luận chỉ vì chưa thấy event sau một thời gian ngắn.

Khi service dùng thread pool, phải capture và restore correlation ID/MDC đúng từng task; đừng để request B mang `operationId` của request A. Một event immutable chỉ an toàn ở mức dữ liệu của nó; database/queue/list được chia sẻ còn cần đồng bộ.

## 15. Bảo mật và tính toàn vẹn của audit result

**Audit không đáng tin nếu bất kỳ client nào cũng có thể tự chọn actor và outcome.**

- Lấy actor từ authenticated principal hoặc service identity đã xác minh; không tin `actorId` từ body.
- Server quyết định `outcome` sau khi kiểm tra kết quả thật; không chấp nhận chuỗi `"success"` do client tự báo.
- Xác thực/canonicalize resource ID, giới hạn độ dài và encoding để tránh log injection.
- Không ghi password, session cookie, access/refresh token, private key, raw request body hoặc stack trace chứa secret.
- Dùng reason code có kiểm soát; không tự do chép raw exception message.
- Chia quyền read/write/delete/export của audit; kiểm soát retention, backup và thay đổi policy.
- Nếu threat model cần, lưu append-only/immutable và bảo vệ hash/signature/chain of custody ở nơi đáng tin. Một hash đặt cạnh file mà attacker cũng có quyền sửa không tự bảo đảm toàn vẹn.
- Khi export hoặc điều tra, sử dụng kênh hạn chế quyền và không sao chép dữ liệu nhạy cảm sang ticket/chat rộng quyền.

Schema audit cũng cần version. Nếu đổi từ `FAILED` sang `REJECTED` cho cùng một loại điều kiện, phải ghi nhận sự thay đổi ngữ nghĩa để dashboard, alert và báo cáo lịch sử không bị diễn giải sai.

## 16. Theo dõi chất lượng kết quả audit

Một số metric có ích (tên chỉ là **ví dụ**, không phải metric tự động có trong Logback):

| Metric | Mục đích |
| --- | --- |
| `audit_events_total{action,outcome}` | Tỷ lệ kết quả theo thao tác |
| `audit_outbox_pending` | Số event đã commit nhưng chưa giao |
| `audit_oldest_pending_age_seconds` | Độ trễ backlog lớn nhất |
| `audit_delivery_errors_total` | Lỗi gửi/lưu ở sink |
| `audit_duplicate_events_total` | Event trùng được phát hiện |
| `audit_unknown_operations` | Kết quả cần đối soát |
| `audit_stale_pending_operations` | Job chưa có kết quả cuối quá SLA |
| `audit_partial_operations_total` | Operation có kết quả một phần |

Đừng đặt `eventId`, `actorId` hay `resourceId` làm nhãn metric vì cardinality rất cao và nguy cơ lộ dữ liệu. Giữ thông tin chi tiết trong audit store có kiểm soát.

Một số tín hiệu cần cảnh báo: `DENIED` tăng bất thường, `FAILED` tăng sau deployment, `UNKNOWN` kéo dài chưa được đối soát, outbox backlog không drain, hoặc số thao tác đã commit không khớp event `SUCCEEDED` theo phương pháp reconciliation đáng tin. Không quy mọi trường hợp thiếu event là do attacker xóa; filter, queue overflow, collector outage hoặc truy vấn sai cũng là nguyên nhân.

## 17. Các lỗi phổ biến khi ghi kết quả thao tác

| Sai lầm | Tác hại | Hướng xử lý |
| --- | --- | --- |
| Log success trước commit | Có thể audit sai khi rollback | Chốt kết quả sau mốc xác minh |
| Dùng boolean success/fail cho mọi việc | Mất deny/reject/no-change/partial/unknown | Taxonomy outcome phù hợp |
| Coi HTTP 202 là hoàn thành | Báo cáo sai job nền | `PENDING` và event cuối |
| Coi timeout là thất bại chắc chắn | Có thể retry gây side effect lặp | `UNKNOWN` + reconcile |
| Gán reason từ exception message | Không ổn định và có thể lộ secret | Mã an toàn được quản lý |
| Không phân biệt attempt và operation | Thống kê thất bại bị nhân đôi | Operation ID + attempt ID |
| Không ghi denied/rejected | Thiếu bằng chứng truy cập bị chặn | Audit ở đường không rollback |
| Ghi 8/10 là success hoàn toàn | Che tác dụng phụ còn tồn tại | `PARTIALLY_SUCCEEDED` + counts |
| Coi logger INFO là durable | Log bị filter/drop/mất khi crash | Outbox/ack/spool khi cần |
| Đưa client actor/outcome vào event | Có thể giả mạo kết quả | Lấy từ trusted server context |
| Kiểm thử chỉ verify logger called | Không chứng minh business state | Assert state + event + storage |
| Xóa event cũ sau compensation | Mất lịch sử những gì đã xảy ra | Event trail append-only |
| In raw request/exception để giải thích fail | Rò secret/PII, log injection | Field allowlist + reason code |

## 18. Quy trình triển khai trong dự án Java

1. **Liệt kê action phải audit**: thay đổi quyền, export, đổi cấu hình, thao tác dữ liệu nhạy cảm và hành động audit bắt buộc.
2. **Định nghĩa outcome và reasonCode** cho từng action; xác định điểm nào là `PENDING` và điểm nào mới có thể là `SUCCEEDED`.
3. **Thiết kế schema** với version, actor đáng tin, resource, event ID/operation ID, timestamp và các trường tối thiểu.
4. **Ánh xạ từng nhánh nghiệp vụ**: permission denied, input rejected, idempotent no-change, commit success, failure có rollback, trạng thái unknown.
5. **Phân biệt attempt và logical operation** với workflow retry/async; xác định consumer đếm theo mức nào.
6. **Chọn đường lưu audit**: event store/outbox/collector có ack/retention/permission phù hợp; không chỉ dựa vào một debug logger có thể drop.
7. **Tạo ma trận test** với success, deny, reject, no-change, partial, timeout, conflict, compensation, restart và collector outage.
8. **Định nghĩa reconciliation** giữa business state và audit event để phát hiện trường hợp thiếu event hoặc outcome không khớp.
9. **Thiết lập monitoring và runbook**: backlog, failure, unknown, pending quá lâu, quyền truy cập audit.
10. **Review schema qua mỗi thay đổi**: không đổi nghĩa `SUCCEEDED`, `FAILED` hoặc `reasonCode` một cách âm thầm.

## 19. Checklist kiến thức

- [ ] Mỗi event có action và outcome rõ nghĩa, không dựa vào severity để suy kết quả.
- [ ] Kết quả được chốt tại đúng ranh giới nghiệp vụ; success không được ghi trước commit.
- [ ] `DENIED`, `REJECTED`, `NO_CHANGE`, `FAILED`, `UNKNOWN` được phân biệt khi có ý nghĩa.
- [ ] Job async có trạng thái ban đầu và kết quả cuối liên kết cùng `operationId`.
- [ ] Retry tách event ID, operation ID, attempt ID và chống duplicate delivery.
- [ ] Bulk/saga giữ thông tin partial/compensation, không che thay đổi đã có hiệu lực.
- [ ] Reason code dùng danh sách quản lý; actor lấy từ security context; không log secret.
- [ ] Audit store có mức độ bền/ack và quyền truy cập phù hợp với loại hành động.
- [ ] Có test đối chiếu business state, event, transaction và delivery failure.
- [ ] Có metric/outbox reconciliation để phát hiện sự kiện thiếu, UNKNOWN hoặc PENDING kéo dài.

**Ghi nhớ:** “kết quả thao tác” không phải một chữ success/failure trong message log. Nó phải phản ánh **điều thật sự xảy ra** ở ranh giới được xác minh, bao gồm từ chối, không thay đổi, đang chờ, thành công một phần và trạng thái chưa biết. Một hệ thống audit tốt còn phải lưu được kết luận ấy theo độ bền, quyền truy cập và khả năng đối soát đã cam kết.
