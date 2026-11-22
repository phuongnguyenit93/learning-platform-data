# Thời điểm audit trong Java Core Logging

## Mục tiêu học tập

Bài học thuộc nhóm **Audit logging**, với đề bài **Thời điểm audit**. Audit log là dấu vết phục vụ truy xét **ai đã làm gì, với đối tượng nào, khi nào, bằng kết quả gì và dựa trên quyền/ngữ cảnh nào**. Một event được gửi đi vào thời điểm không phù hợp có thể tạo bằng chứng sai: ghi “đã chuyển tiền thành công” trước khi giao dịch commit, ghi “đăng nhập thất bại” quá muộn để điều tra, hoặc thay timestamp gốc bằng thời điểm collector nhận khiến trình tự sự kiện bị bóp méo.

Sau bài học, bạn có thể:

- Phân biệt **thời điểm xảy ra**, **bắt đầu/hoàn thành hành động**, **quyết định xác thực/phân quyền**, **commit**, **ghi nhận audit**, **xuất bản** và **ingest**.
- Quyết định khi nào nên audit **attempt**, **denied**, **failed**, **committed** và **compensated** mà không ghi nhầm kết quả.
- Thiết kế audit nhất quán với transaction: insert audit row cùng giao dịch, transactional outbox hoặc luồng audit độc lập cho sự kiện bị từ chối.
- Hiểu sai lệch đồng hồ, timezone, timestamp source, event ordering, retry, duplicate và async delivery.
- Viết Java 17 có `Clock` được tiêm vào để kiểm tra timestamp và outcome với stdout xác định.
- Lập ma trận kiểm thử cho rollback, commit không rõ trạng thái, crash, retry, quyền truy cập và khả năng truy vết end-to-end.

**Nguyên tắc trọng tâm:** Một dấu vết audit phải mô tả **sự kiện và trạng thái thực sự đã xảy ra**, không mô tả điều ứng dụng chỉ đang dự định làm. Đồng thời, một **nỗ lực bị từ chối** vẫn là sự kiện đáng audit dù không có thay đổi nghiệp vụ nào được commit.

## 1. “Thời điểm audit” có ít nhất ba nghĩa

Khi một người nói “audit lúc 10:00”, cần hỏi đó là lúc hành động bắt đầu, lúc hệ thống ra quyết định, lúc database commit, hay lúc log đến hệ thống audit. Các mốc có thể khác nhau đáng kể.

Ví dụ một thao tác đổi vai trò:

```text
t0                 t1                  t2                 t3             t4             t5
| request received| authorization PASS| UPDATE prepared   | DB COMMIT OK   | audit shipped | index visible
|-------------------- business operation -------------------|
             |-- decision moment --|
                                 |------ durable transition --|
|------------------------- event timeline --------------------------------------->

Các mốc riêng cần cân nhắc:
- attempt_at       = lúc yêu cầu/nỗ lực được quan sát
- decision_at      = lúc hệ thống chấp nhận hoặc từ chối
- effective_at     = lúc thay đổi có hiệu lực theo nghiệp vụ
- committed_at     = mốc giao dịch đã được xác nhận commit (nếu hệ thống có thể biết)
- recorded_at      = lúc audit record được chấp nhận vào kho/luồng audit
- ingested_at      = lúc collector/backend tiếp nhận
- searchable_at    = lúc sự kiện tìm được trong index
```

Sơ đồ chỉ là **mô hình khái niệm**. Không phải công nghệ nào cũng cung cấp timestamp commit thực sự; thời điểm ứng dụng nhận câu trả lời COMMIT OK không nhất thiết chính xác bằng thời điểm cơ sở dữ liệu xác nhận commit nội bộ. Nếu không có khả năng đo mốc nào một cách đáng tin, **đừng tạo một trường tên có vẻ chính xác rồi điền thời gian suy đoán**.

Các field phổ biến:

| Thuộc tính | Ý nghĩa | Nguồn đáng tin ưu tiên |
| --- | --- | --- |
| `occurred_at` / `event_time` | Khi event được xác định là đã xảy ra theo định nghĩa nghiệp vụ | Clock tại nguồn phát hoặc timestamp authoritative được hệ thống nguồn cung cấp |
| `attempted_at` | Khi thao tác/đăng nhập bắt đầu | Điểm nhận request hoặc điểm bắt đầu xử lý, ghi rõ semantics |
| `decision_at` | Khi chính sách authn/authz đưa ra quyết định | Bên thực thi quyết định |
| `effective_at` | Khi thay đổi có hiệu lực trong miền nghiệp vụ, đôi khi là tương lai/quá khứ hợp lệ | Domain model hoặc hệ thống lưu trạng thái |
| `committed_at` | Mốc commit được xác nhận / commit timestamp nếu DB cung cấp | Cơ sở dữ liệu hoặc điểm nhận confirmation, có định nghĩa rõ |
| `recorded_at` | Khi audit subsystem nhận/lưu bản ghi | Audit writer hoặc audit store |
| `published_at` | Khi event được gửi tới broker/collector | Producer/outbox publisher |
| `ingested_at` | Khi collector/ingest pipeline tiếp nhận event | Collector |
| `searchable_at` | Khi backend cho phép truy vấn event | Backend/index |

Không cần đưa **mọi trường** vào mỗi bản ghi. Cần một schema nhất quán, trong đó field nào có ý nghĩa thì được lưu, timestamp nào không có bằng chứng thì có thể `null`/không xuất. Với một audit “quyết định truy cập bị từ chối”, `decision_at` và `outcome=DENIED` có thể quan trọng hơn `committed_at`, vì không có transaction thay đổi vai trò được commit.

### Event time khác processing time

**Event time** mô tả lúc xảy ra sự kiện gốc; **processing/ingest time** mô tả lúc một thành phần pipeline xử lý. Ví dụ:

```text
2026-11-10T09:00:04Z  role.changed committed at source
2026-11-10T09:00:05Z  audit row stored locally
2026-11-10T09:01:15Z  collector ingested after outage
2026-11-10T09:01:18Z  event became searchable
```

Nếu dashboard lấy `ingested_at` làm thời điểm hành động, thay đổi vai trò có thể trông xảy ra muộn hơn hơn một phút. Nên lưu cả **event timestamp gốc** và timestamp backend khi cần điều tra độ trễ pipeline. Không ghi đè `occurred_at` mỗi khi retry/ship lại.

## 2. Chọn mốc audit theo loại sự kiện

Có hai câu hỏi khác nhau: **“Có ai đã thử?”** và **“Thay đổi gì đã thực sự có hiệu lực?”**. Chúng cần các audit event khác nhau, với mốc được ghi rõ.

| Loại sự kiện | Thời điểm audit phù hợp | Dữ liệu cốt lõi |
| --- | --- | --- |
| Đăng nhập thử | Khi nỗ lực được nhận hoặc khi có quyết định xác thực, tùy loại event | `attempted_at`, principal/identifier đã giảm nhạy cảm, nguồn, request ID |
| Đăng nhập bị từ chối | Khi hệ thống ra quyết định từ chối | `decision_at`, `outcome=DENIED`, mã lý do an toàn |
| Đăng nhập thành công | Khi phiên hoặc credential/session state cần thiết đã được thiết lập thành công | `outcome=SUCCESS`; không ghi thành công khi mới qua bước đầu |
| Phân quyền bị từ chối | Khi policy engine/gateway từ chối hành động | Actor, resource, action, `outcome=DENIED`, policy/version |
| Thay đổi dữ liệu có transaction | Event thành công phải nhất quán với **commit** | `event=role.changed`, old/new theo chính sách, transaction/record version |
| Giao dịch rollback | Không ghi event “đã thay đổi thành công”; có thể audit nỗ lực thất bại riêng | `outcome=ROLLED_BACK` hoặc `FAILED`, lý do, correlation |
| Gọi API bên ngoài | Phân biệt **đã gửi yêu cầu**, **nhận xác nhận** và **side effect có hiệu lực** | Remote operation ID, outcome và mốc tương ứng |
| Công việc bất đồng bộ | Phân biệt **đã xếp hàng**, **đã bắt đầu**, **hoàn tất** và **thất bại** | Job ID, attempt number, event time từng state |
| Đăng xuất / thu hồi token | Khi thao tác hủy phiên/credential được xác nhận ở hệ thống có thẩm quyền | Actor, target session/credential đã ẩn dữ liệu nhạy cảm, outcome |
| Thay đổi cấu hình bảo mật | Ghi nỗ lực, quyết định, và hiệu lực cấu hình riêng nếu cần | Config version, approver, rollout status, affected scope |
| Xóa dữ liệu | Ghi yêu cầu, chấp thuận, commit hoặc hoàn tất xóa theo thực tế | Resource ID được giảm nhạy cảm, retention policy, outcome |

**Không nên gộp tất cả thành một event “SUCCESS” ngay khi controller nhận request.** HTTP `202 Accepted` thường chỉ nói job đã được nhận vào một cơ chế xử lý, chưa nói side effect cuối cùng thành công. Với luồng xử lý dài, một chuỗi audit event theo trạng thái hữu ích hơn một bản ghi sớm nhưng sai.

### Nhóm attempt, decision, outcome và effect

Một cấu trúc rõ là phân tách:

- `access.attempted`: nhận thấy nỗ lực truy cập.
- `access.denied` hoặc `access.allowed`: policy đã quyết định.
- `role.change.committed`: dữ liệu thay đổi được commit.
- `role.change.failed`: nỗ lực thất bại, không có thay đổi như yêu cầu.
- `role.change.compensated`: thao tác bù trừ được thực thi sau một thay đổi trước đó.

Tên event chỉ là ví dụ. Một tổ chức có thể dùng cấu trúc `action=role.change` cộng `outcome=DENIED/COMMITTED`; miễn là schema và thời điểm rõ ràng. **Không lẫn `attempted` với `committed`**, và không dùng một event `failed` không phân biệt lỗi xác thực, lỗi validation, rollback hay timeout chưa biết kết quả.

## 3. Thành công và transaction: ghi trước hay sau commit?

Đây là quyết định cốt lõi của **thời điểm audit**.

### 3.1. Ghi audit thành công trước commit, bên ngoài transaction

```text
Service:
  audit("role.changed", SUCCESS)  ---> audit sink nhận
  UPDATE roles ...
  COMMIT                         ---> có thể ROLLBACK!
```

Nếu commit thất bại, audit bên ngoài đã tuyên bố một thay đổi **không tồn tại**. Đây là **false success** và là lỗi tính đúng đắn. Không được xem việc “đã gọi logger.info” là bằng chứng dữ liệu đã commit.

### 3.2. Commit xong mới ghi audit ở hệ thống độc lập

```text
Service:
  UPDATE roles ...
  COMMIT                         ---> thành công
  audit("role.changed", SUCCESS) ---> có thể crash trước bước này!
```

Bây giờ record không nói sai nếu được ghi, nhưng có một **khoảng trống mất audit**: database đã đổi, process bị kill hoặc audit sink down trước khi record được lưu. Với audit chỉ mang tính observability, nhóm có thể chấp nhận rủi ro theo yêu cầu; với audit bắt buộc thì chưa đủ.

### 3.3. Ghi business state và audit row trong cùng database transaction

Khi dữ liệu nghiệp vụ và audit table nằm trong cùng DB/transaction manager có semantics phù hợp, có thể:

```sql
BEGIN;

UPDATE user_roles
SET role = 'editor'
WHERE user_id = 'user-17';

INSERT INTO audit_events (
    event_id, action, outcome, subject_id,
    occurred_at, actor_id
) VALUES (
    'evt-role-0001', 'role.change', 'COMMITTED',
    'user-17', CURRENT_TIMESTAMP, 'admin-3'
);

COMMIT;
```

Đây là **SQL minh họa**, không phải migration/ứng dụng độc lập: cần bảng, constraint, quyền và transaction isolation phù hợp. Ở hệ quản trị cơ sở dữ liệu khác nhau, `CURRENT_TIMESTAMP` có thể phản ánh thời điểm bắt đầu transaction/statement hoặc giá trị khác, **không mặc nhiên là commit timestamp chính xác**. Muốn audit thời điểm commit thực sự, phải kiểm tra khả năng DB và định nghĩa field. SQL trên cũng chưa kiểm tra `UPDATE` đã sửa đúng một row; ứng dụng thực tế phải kiểm tra row count, điều kiện/phiên bản để tránh ghi “COMMITTED” dù không có thay đổi.

Nếu `UPDATE` và `INSERT` cùng **thành công trong một transaction đã COMMIT**, chúng được commit cùng nhau; nếu transaction rollback, cả hai biến mất. Tên `outcome=COMMITTED` ở row được dựng trước commit nhưng chỉ hiện trong dữ liệu committed khi commit thành công. Điều này tốt cho **audit của thay đổi thành công** trên cùng DB.

Tuy nhiên, không thể dùng chính transaction này để giữ audit về **nỗ lực bị từ chối/rollback**, vì audit row chèn trong transaction rollback cũng sẽ mất. Những event “thử nhưng thất bại” cần một đường audit độc lập, bền vững theo yêu cầu riêng.

### 3.4. Transactional outbox: trạng thái và ý định xuất bản cùng commit

Khi hệ thống audit tập trung ở nơi khác, transactional outbox giúp tránh khoảng trống giữa commit và publish:

```text
Ứng dụng:
  BEGIN
    UPDATE business_state
    INSERT outbox_event(event_id, payload, occurred_at, ...)
  COMMIT
               |
               v
Outbox publisher (later, retryable)
               |
         broker/collector
               |
           audit store
```

**Lợi ích:** Business change và row outbox cùng transaction có thể được commit/rollback nguyên tử (trong phạm vi cùng DB). Nếu process crash sau commit nhưng trước publish, publisher có thể đọc lại outbox và tiếp tục gửi.

**Giới hạn:**

- Thường là **at-least-once delivery**, không tự đảm bảo exactly-once end-to-end. Publisher có thể gửi thành công nhưng mất ACK; retry gây duplicate.
- Consumer/audit store phải **idempotent** theo `event_id` hoặc có cơ chế dedup phù hợp.
- Timestamp gốc `occurred_at` phải được giữ nguyên qua retry; `published_at` và `ingested_at` cập nhật theo hop riêng.
- Giữ được sự kiện ở outbox không có nghĩa hệ thống audit bên ngoài đã searchable hay durable; cần metrics và reconciliation.
- Audit về attempt/denied không commit cùng business transaction có thể cần một outbox hoặc audit writer độc lập, tùy mô hình dữ liệu.

Nếu phải tuân thủ thứ tự thay đổi của một aggregate, publisher/consumer còn phải duy trì khóa/sequence/version theo aggregate; outbox tự nó không bảo đảm mọi event được giao và lưu ở cùng thứ tự dưới nhiều worker.

## 4. Audit thao tác thất bại, denied và rollback

Một quyết định **DENIED** không có state change nhưng là sự kiện quan trọng với bảo mật. Không thể đợi database transaction “thành công” để ghi một hành động bị từ chối.

Ví dụ request đổi quyền:

```text
request received
  -> identify principal
  -> check authentication
  -> check authorization
       +-> DENIED
       |     +-> emit audit(access.denied, outcome=DENIED)
       |     +-> return 403
       |
       +-> ALLOWED
             +-> BEGIN business transaction
             +-> UPDATE role, audit row or outbox
             +-> COMMIT
             +-> report outcome COMMITTED
```

Đây là sơ đồ dòng quyết định; trong sản phẩm thực tế, authn có thể thất bại trước khi biết chính xác principal và việc ghi audit còn phụ thuộc kiến trúc. Hãy ghi **identifier được phép lưu**, không cố nhét password hay bearer token vào audit để “đủ bằng chứng”.

### Những sai lầm thường gặp

- Ghi `access.allowed` ngay khi token hợp lệ nhưng policy cuối cùng vẫn từ chối.
- Ghi `role.changed` trước transaction commit.
- Tạo audit row về denied trong chính transaction sẽ rollback, khiến row cũng biến mất.
- Ghi `FAILED` khi client timeout nhưng backend có thể đã commit; kết quả có thể là **UNKNOWN** và cần reconciliation.
- Bỏ qua event denial vì “không có dữ liệu thay đổi”, làm mất chuỗi nỗ lực tấn công.
- Ghi tất cả các lần retry lỗi như những thay đổi nghiệp vụ độc lập thay vì phân biệt **attempt** và **logical operation**.

**Không phải mọi attempt đều bắt buộc thành một bản ghi vô hạn.** Hệ thống có thể cần sampling/rate limiting hoặc aggregate cho lượng request bị từ chối cực lớn, nhưng policy audit/security phải được phê duyệt và vẫn giữ đủ dấu vết theo yêu cầu. Đừng áp dụng filter của log debug vào audit trail bắt buộc mà không kiểm tra.

### Nếu chính hệ thống audit không sẵn sàng

Chọn chính sách **fail-open** (nghiệp vụ tiếp tục, ghi nhận thiếu audit để xử lý sau) hay **fail-closed** (từ chối thao tác khi không thể đảm bảo audit) theo mức độ rủi ro/pháp lý và thiết kế dịch vụ. Không có lựa chọn đúng chung:

- Thay đổi quyền quản trị nhạy cảm có thể cần một cơ chế audit bền vững trước khi trả thành công.
- Ghi thao tác read-only ít rủi ro có thể ưu tiên availability và buffering phù hợp.
- Nếu từ chối thao tác vì audit down, chính hành vi từ chối có thể cần báo cho hệ thống vận hành độc lập mà không tạo vòng lặp ghi log vô hạn.

Không biến logger thông thường thành điểm quyết định nhất quán của transaction nếu không có contract rõ về durability/error propagation.

## 5. Schema audit: timestamp và ngữ cảnh đủ chính xác

Một audit record có thể dùng schema khái niệm:

```json
{
  "event_id": "evt-4e7b",
  "event_type": "role.change",
  "outcome": "COMMITTED",
  "actor_id": "admin-3",
  "subject_id": "user-17",
  "request_id": "req-0e19",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attempted_at": "2026-11-10T09:00:01Z",
  "occurred_at": "2026-11-10T09:00:04Z",
  "recorded_at": "2026-11-10T09:00:06Z",
  "ingested_at": "2026-11-10T09:00:07Z",
  "previous_role": "viewer",
  "new_role": "editor",
  "aggregate_version": 12
}
```

Đây là **event JSON minh họa**, không phải output mặc định của Logback/Java; các ID và thời điểm chỉ phục vụ bài học. Trong hệ thống thật:

- `event_id` định danh một event logic ổn định qua retry; cần uniqueness policy và khả năng dedup.
- `event_type`/`outcome` rõ ràng, không dùng một chuỗi message mơ hồ làm nguồn duy nhất.
- `actor_id` và `subject_id` phải thỏa chính sách dữ liệu cá nhân/retention; không tự động log email đầy đủ hoặc thông tin bí mật.
- `request_id`/`trace_id` giúp ghép log nhưng không nhất thiết định danh duy nhất **mỗi audit event**.
- `aggregate_version` hoặc sequence là tín hiệu ordering theo đối tượng, không thay thế timestamp; cách sinh version phải chống race theo data model.
- `previous_role` và `new_role` chỉ minh họa before/after; chỉ lưu các giá trị cần thiết và đã được phép, tránh lưu toàn bộ object hoặc secret.
- `ingested_at` nên do collector/audit backend xác định nếu cần quan sát đúng độ trễ tiếp nhận; không copy bằng `recorded_at` nếu đó là hai hệ thống khác nhau.

**Không tự điền thời gian do phía client HTTP cung cấp như timestamp authoritative** nếu client có thể chỉnh sửa. Client có thể gửi một sự kiện offline xảy ra trong quá khứ, nhưng cần lưu cả timestamp được client khai và timestamp server nhận, đánh dấu nguồn/trust level, và áp dụng validation/reconciliation thích hợp.

## 6. Java 17 chạy độc lập: phân biệt occurredAt và recordedAt

Ví dụ Java thuần này sử dụng `java.time.Instant` và `java.time.Clock` để tạo ra output **hoàn toàn xác định**. Nó mô phỏng hai loại audit:

1. Quyết định **DENIED** khi một nỗ lực đăng nhập bị từ chối (không có thay đổi state).
2. Thay đổi vai trò **COMMITTED** sau khi mô phỏng business state đã được cập nhật.

Nguồn phát gắn `occurredAt` theo **thời điểm của sự kiện logic**, còn audit recorder gắn `recordedAt` khi nhận event. Hai mốc được tiêm vào cho ví dụ để thể hiện chênh lệch một cách nhất quán, không dựa đồng hồ thật. Chương trình sử dụng **in-memory Map/List**, không có database transaction hoặc lưu durable. Do đó nó **chỉ dạy timestamp và phân loại outcome**, không chứng minh tính nguyên tử của dữ liệu và audit khi process crash. Phần transaction thực tế xem mục 3.

Tạo file **`AuditTimeDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AuditTimeDemo {
    record AuditEvent(
            String eventId,
            String type,
            String outcome,
            String subjectId,
            Instant occurredAt,
            Instant recordedAt) {
    }

    static final class AuditRecorder {
        private final Clock clock;
        private final List<AuditEvent> events = new ArrayList<>();

        AuditRecorder(Clock clock) {
            this.clock = clock;
        }

        void record(String id, String type, String outcome,
                    String subject, Instant occurredAt) {
            events.add(new AuditEvent(id, type, outcome, subject,
                    occurredAt, Instant.now(clock)));
        }

        List<AuditEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Instant auditReceivedAt =
                Instant.parse("2026-11-10T09:00:06Z");
        Clock auditClock = Clock.fixed(
                auditReceivedAt, ZoneOffset.UTC);
        AuditRecorder recorder = new AuditRecorder(auditClock);

        Map<String, String> roles = new LinkedHashMap<>();
        roles.put("user-17", "viewer");

        // Event 1: nỗ lực đăng nhập đã bị từ chối.
        Instant denialDecisionAt =
                Instant.parse("2026-11-10T09:00:01Z");
        recorder.record("evt-1", "login", "DENIED",
                "user-17", denialDecisionAt);

        // Event 2: mô phỏng state change đã thành công.
        Instant simulatedCommitAt =
                Instant.parse("2026-11-10T09:00:04Z");
        roles.put("user-17", "editor");
        recorder.record("evt-2", "role.change", "COMMITTED",
                "user-17", simulatedCommitAt);

        List<AuditEvent> events = recorder.snapshot();
        if (events.size() != 2
                || !"editor".equals(roles.get("user-17"))
                || !events.get(0).occurredAt()
                        .isBefore(events.get(1).occurredAt())
                || !events.get(1).recordedAt()
                        .isAfter(events.get(1).occurredAt())) {
            throw new IllegalStateException("Audit timeline invalid");
        }

        for (AuditEvent event : events) {
            System.out.println("id=" + event.eventId()
                    + " type=" + event.type()
                    + " outcome=" + event.outcome()
                    + " occurred_at=" + event.occurredAt()
                    + " recorded_at=" + event.recordedAt());
        }
        System.out.println("effective_role=" + roles.get("user-17"));
        System.out.println("audit_count=" + events.size());
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac AuditTimeDemo.java
java AuditTimeDemo
```

**stdout chính xác:**

```text
id=evt-1 type=login outcome=DENIED occurred_at=2026-11-10T09:00:01Z recorded_at=2026-11-10T09:00:06Z
id=evt-2 type=role.change outcome=COMMITTED occurred_at=2026-11-10T09:00:04Z recorded_at=2026-11-10T09:00:06Z
effective_role=editor
audit_count=2
```

**Giải thích:**

1. `Clock.fixed(...)` làm thời điểm recorder nhận audit bằng một giá trị đã biết; điều này cho phép test so sánh chính xác. Production thường dùng `Clock.systemUTC()` hoặc clock/infrastructure được quản trị, nhưng vẫn nên cho phép inject Clock vào mã cần kiểm thử.
2. `Instant` giữ một thời điểm trên UTC timeline; khi `toString()` trong ví dụ, nó hiển thị dạng ISO-8601 kết thúc `Z`. Nó không phụ thuộc timezone của máy khi record đã chứa Instant.
3. `evt-1` là quyết định DENIED nên có `occurred_at` lúc quyết định, dù không có state change nào.
4. `evt-2` đánh dấu thay đổi đã **mô phỏng** thành công, nên `occurred_at` là mốc commit được giả lập, **không phải lúc bắt đầu request**.
5. `recorded_at` của cả hai event là `09:00:06Z` vì recorder nhận sau các thời điểm sự kiện; collector thực có thể còn nhận trễ hơn nữa.
6. `record(...)` append vào `ArrayList` không phải transaction hay durable write. Nếu hai hành động `roles.put` và `recorder.record` có lỗi chen giữa, chúng có thể lệch nhau. Để tránh rủi ro đó với thay đổi quan trọng, dùng transaction đồng nhất hoặc outbox như mục 3.
7. Mã trên dùng một thread và ID giả lập, không cần synchronization; hệ thống nhiều thread cần store/queue có thread-safety, ordering và idempotency phù hợp.

**Thử nghiệm học tập:** đổi `auditReceivedAt` thành `2026-11-10T09:00:08Z`. Hai field `recorded_at` đổi theo, còn `occurred_at` **giữ nguyên**, chứng minh việc gửi/ghi muộn không nên thay thời điểm gốc của sự kiện. Nếu cố đảo giá trị `simulatedCommitAt` trước `denialDecisionAt`, assertion trong chương trình sẽ báo lỗi; đây chỉ là assertion của kịch bản minh họa, không phải quy tắc rằng mọi audit event thật luôn tới theo thứ tự thời gian.

## 7. Quy tắc đồng hồ: UTC, Clock và mốc thời gian đáng tin

### 7.1. Instant, ZoneId và timestamp có offset

Trong Java 17:

- `Instant` biểu diễn một thời điểm trên UTC timeline, phù hợp cho event time và so sánh across services khi đồng hồ được đồng bộ.
- `OffsetDateTime`/`ZonedDateTime` hữu ích khi cần hiển thị giờ địa phương hoặc lưu offset/timezone có ngữ nghĩa nghiệp vụ.
- `LocalDateTime` **không có timezone/offset**, nên không đủ để diễn tả một timestamp toàn cục khi nhiều môi trường sử dụng múi giờ khác nhau.
- `Clock` cho phép inject nguồn thời gian; dùng `Clock.fixed(...)` trong test, `Clock.systemUTC()` khi phù hợp ở production.

Ví dụ trích đoạn Java, không phải chương trình độc lập:

```java
Clock clock = Clock.systemUTC();
Instant observedAt = Instant.now(clock);
String iso8601 = observedAt.toString();
```

Trong cơ sở dữ liệu, kiểu thời gian và timezone semantics tùy hệ quản trị: ví dụ PostgreSQL `TIMESTAMPTZ` lưu thời điểm tuyệt đối và hiển thị theo timezone của session; nó **không lưu tên timezone gốc**. Kiểm tra driver/JDBC mapping và precision (milliseconds/microseconds/nanoseconds), không giả định DB luôn giữ nguyên nanosecond.

**Không chỉ lưu chuỗi giờ địa phương** như `10/11/2026 09:00:00` mà thiếu offset, đặc biệt trong hệ thống đa vùng hoặc tại những vùng có daylight saving time. Khi hiển thị thời gian cho người dùng, chuyển từ timestamp chuẩn sang timezone mong muốn ở tầng giao diện.

### 7.2. Timestamp là bằng chứng có giới hạn

Đồng hồ các node có thể lệch do NTP chưa ổn định, VM pause, chỉnh thời gian thủ công, container host drift hoặc mạng. Đồng hồ tường (`Instant.now`) có thể nhảy tiến/lùi; từ đó có thể thấy `ingested_at < occurred_at` trên hai máy dù thứ tự thực tế ngược lại.

**Không dùng `System.nanoTime()` để ghi absolute event timestamp.** Nó là nguồn đo **khoảng thời gian trong phạm vi một JVM** và không có mốc epoch có thể chia sẻ giữa server. Dùng `System.nanoTime()` cho duration như time-to-append, handshake duration hoặc queue wait; không tự đổi nó thành UTC timestamp để ghép audit giữa máy.

Khi compliance cần độ chính xác thời gian cao, cần quản lý nguồn đồng hồ, độ lệch tối đa, NTP/chrony status hoặc time source chuyên dụng; không chỉ ghi thêm nhiều chữ số phần thập phân vào timestamp.

### 7.3. Các thứ tự không được đánh đồng

- **Event order:** sự kiện nào xảy ra trước ở domain; có thể dựa trên transaction version, sequence number, source offset hoặc causality.
- **Record order:** bản ghi nào đến audit store trước.
- **Ingest order:** collector nhận record nào trước.
- **Search order:** kết quả được index và hiển thị theo một field nào đó.

Async queue, retry, batch, network partition và nhiều consumer khiến các thứ tự này khác nhau. Hai event cùng `occurred_at` tới độ chính xác lưu trữ vẫn có thể khác thứ tự; cần tie-breaker/sequence nếu thứ tự là yêu cầu quan trọng.

Ví dụ thay đổi của cùng tài khoản:

```text
event_id   occurred_at        aggregate_version   ingested_at
evt-101    09:00:01Z         41                  09:00:09Z
evt-102    09:00:02Z         42                  09:00:06Z
```

Collector nhận `evt-102` trước `evt-101`; không thể suy ra dữ liệu role version 42 đã xảy ra trước version 41. Sắp theo `aggregate_version` có thể khôi phục thứ tự trong phạm vi aggregate nếu version được sinh nhất quán; không mặc định dùng version làm global ordering của toàn hệ thống.

## 8. Async audit: lúc nào thành công, lúc nào chỉ mới enqueue?

Một lời gọi `auditLogger.info(...)` thành công có thể chỉ là **publish vào queue trong bộ nhớ**. Nếu worker chưa xử lý, việc trả về không chứng minh event đã ở kho audit. Dưới tải cao:

```text
Business thread ---> enqueue audit ---> return
                        |
                        v
                worker / batch / retry
                        |
                        v
                  audit collector
                        |
                        v
                durable audit store
```

Điều cần xác định là **acknowledgement boundary**:

| Mốc | Điều có thể biết | Điều chưa chắc biết |
| --- | --- | --- |
| Event object được tạo | Có dữ liệu audit trong bộ nhớ JVM | Có được lưu/ship không |
| Enqueue thành công | Queue chấp nhận event | Worker đã xử lý, process có thể crash |
| File appender write trả về | API ghi xuống filesystem đã trả về | Đã fsync/durable hay đã được collector nhận |
| Broker ACK | Broker đã xác nhận theo cấu hình ack của nó | Consumer/audit store đã xử lý |
| HTTP 2xx từ collector | Endpoint đã trả response thành công theo contract | Dữ liệu đã index, persisted hoặc immutable ở mọi hop |
| Audit store commit/ACK | Có thể khẳng định theo semantics của store | Các bản sao downstream đã đồng bộ và searchable |

**Không thể suy ra exactly-once hoặc durability chỉ từ việc dùng TLS, HTTP hoặc AsyncAppender.** Mỗi sink có contract riêng. Với audit bắt buộc, cần yêu cầu lưu bền vững, retry, idempotency, disaster recovery và bằng chứng monitoring phù hợp.

### Lỗi thường gặp về thời điểm trong pipeline async

- Gắn `occurred_at` tại worker sau khi event đã chờ queue 30 giây: sự kiện trông xảy ra muộn.
- Retry tạo **event ID mới và occurred_at mới**: cùng một hành động trông như hai hành động.
- App audit thành công dựa trên response `202 Accepted` của một API async: công việc thực tế có thể thất bại sau đó.
- Người điều tra chỉ truy vấn theo `ingested_at` nhưng lại diễn giải là business time.
- Có event `COMMITTED` trước khi transaction commit hoặc thiếu `COMMITTED` sau commit vì process crash.
- Đồng bộ dữ liệu từ batch/offline mà không ghi nhận original time và source trust.

**Giải pháp:** Chụp event time tại ranh giới nghiệp vụ, lưu event ID ổn định, lưu cùng outbox/transaction khi cần, đẩy bất đồng bộ qua consumer idempotent và gắn thêm receiver timestamp ở downstream. Đếm queue lag và reconciliation thay vì chỉ đếm log call.

## 9. Idempotency, retry, UNKNOWN outcome và audit bù trừ

### 9.1. Retry không nhất thiết là một giao dịch mới

Giả sử người dùng gửi yêu cầu đổi role với `operation_id=op-7`. Gateway timeout, client retry ba lần. Nếu backend bảo đảm idempotency, có thể chỉ có **một thay đổi role logic** nhưng **ba request attempts**.

Tùy policy, audit có thể ghi:

- Ba record `request.attempted` có `attempt_id` khác nhau, liên kết cùng `operation_id`.
- Một record `role.change.committed` có `event_id` duy nhất cho business transition.
- Một số record `request.retried` hoặc trạng thái `duplicate_request` nếu cần chẩn đoán.

Không đánh đồng số lần request với số lần thay đổi dữ liệu. Nếu consumer nhận cùng outbox event nhiều lần, dùng cùng `event_id` và dedup tại audit store; không mặc nhiên ghi thêm một “SUCCESS” mới cho cùng transition.

### 9.2. Khi commit trả lỗi nhưng kết quả không rõ

Lỗi network đúng lúc COMMIT có thể khiến client không biết transaction đã commit hay chưa. Ghi `outcome=FAILED` ngay lập tức có thể sai; “không nhận được ACK” không đồng nghĩa rollback.

Một cách ghi an toàn hơn có thể là:

```text
transaction.commit.ack_unknown
  operation_id=op-7
  outcome=UNKNOWN
  reason=connection_lost

reconciliation completed later:
  operation_id=op-7
  observed_state=committed
  resolution=COMMITTED
```

Đây là **mẫu sự kiện minh họa**; cần thiết kế reconciliation dựa trên transaction ID, idempotency key, data version hoặc trạng thái authoritative thực tế. Nếu kết quả cuối cùng vẫn không thể xác định, không tự đổi thành COMMITTED chỉ để đóng ticket. Giữ cả bản ghi gốc và bản ghi resolution để bảo toàn lịch sử điều tra.

### 9.3. Compensating action không phải xóa dấu vết cũ

Trong saga/microservice, một bước đã commit có thể bị thao tác bù trừ đảo ngược. Nếu thay đổi role đã xảy ra rồi được thu hồi, cần giữ cả:

1. `role.change.committed` — thay đổi ban đầu.
2. `role.change.compensated` hoặc `role.revoked` — hành động bù trừ sau đó.

Không xóa, sửa đè event cũ thành “chưa từng xảy ra”, vì audit cần phản ánh trình tự thật. Thời điểm `compensated_at` không thay `occurred_at` của event ban đầu.

## 10. Audit across services: một sự kiện có nhiều đồng hồ

Trong hệ thống phân tán, API gateway, service A, service B, database, broker và collector có thể tạo timestamp ở các máy khác nhau.

Ví dụ:

```text
Gateway: request_received_at = 09:00:01.010Z
Service A: authorization_decided_at = 09:00:01.028Z
Service B: business_effect_confirmed_at = 09:00:01.085Z
Audit store: recorded_at = 09:00:01.140Z
Indexer: ingested_at = 09:00:01.870Z
```

Các số trên giả định đồng hồ đồng bộ và chỉ minh họa. Trong hệ thống thật, **clock skew** có thể khiến mốc của Service B hiển thị trước mốc Gateway dù causality thực tế ngược lại.

Vì vậy:

- Mỗi service cần định nghĩa timestamp và nguồn time rõ ràng.
- Dùng `trace_id`/`span_id` để theo luồng request, nhưng audit `event_id` vẫn phải phân biệt từng event.
- Dùng transaction version, broker offset, causal link hoặc operation ID khi cần khôi phục thứ tự theo domain.
- Theo dõi time sync/offset; cảnh báo nếu ingest latency âm bất thường hoặc clock drift vượt chính sách.
- Không ghép nội dung từ nhiều event chỉ bằng timestamp gần nhau khi có concurrent requests.
- Ghi `source_system` và version/schema để diễn giải sự kiện khi log được lưu nhiều năm.

**Đừng đánh đồng trace span status với audit outcome.** Một trace có thể cho biết HTTP 500 hoặc exception, nhưng không chứng minh state của database đã rollback; audit phải lấy outcome từ domain/transaction authoritative.

## 11. Thiết kế audit store có thể truy xét

Audit logging khác logging chẩn đoán thông thường ở yêu cầu **tính đúng đắn, giữ lịch sử và kiểm soát truy cập**. Bên cạnh timestamp, cân nhắc:

- **Append-only semantics:** hạn chế sửa/xóa trực tiếp record; thay đổi nội dung được diễn giải bằng event bổ sung/correction có link.
- **Access control:** tách quyền người ghi, người đọc, người quản lý retention; không cho ứng dụng nghiệp vụ tùy ý sửa/xóa lịch sử.
- **Integrity/tamper evidence:** có thể dùng hash chaining, signed batches, immutable/WORM storage khi yêu cầu; không tuyên bố log không thể sửa chỉ vì ghi lên file.
- **Retention và data minimization:** đủ thời gian theo nghĩa vụ; không lưu vượt nhu cầu hoặc tiết lộ dữ liệu nhạy cảm.
- **Schema versioning:** event ghi hôm nay cần đọc được trong các lần điều tra sau khi sản phẩm thay đổi.
- **Recovery và reconciliation:** phát hiện chênh lệch giữa business transition/outbox và audit sink, có quy trình backfill chính xác.
- **Monitoring:** queue lag, outbox age, failed publishes, duplicate counts, audit store write errors, clock drift, timestamp anomalies.

Nếu phải sao lưu và phục hồi audit, kiểm tra rằng restore không **viết lại timestamp sự kiện**, không làm mất event ID, và có thể xác minh dữ liệu mới/khôi phục không bị trùng.

### Log thời điểm thay đổi trước và sau

Với hoạt động quản trị, một record có thể chứa `before` và `after` nếu chính sách cho phép. Mốc `occurred_at` nên gắn với **transition** mà record mô tả, còn `effective_at` có thể khác nếu thay đổi sẽ có hiệu lực sau một thời gian.

Ví dụ tạo chính sách có hiệu lực ngày mai:

```text
policy.change.approved:
  decision_at = 2026-11-10T09:00:00Z
  effective_at = 2026-11-11T00:00:00Z
  outcome = APPROVED

policy.change.activated:
  occurred_at = 2026-11-11T00:00:00Z
  outcome = ACTIVATED
```

Đây là hai **event riêng** nếu hệ thống thực sự có hai state transition. Không nên ghi `ACTIVATED` khi mới phê duyệt và chỉ đặt `effective_at` tương lai mà không xác minh scheduler đã áp dụng chính sách đúng lúc.

## 12. Kiểm thử thời điểm audit

### 12.1. Ma trận test quan trọng

| Mã | Kịch bản | Audit kỳ vọng | Không được xảy ra |
| --- | --- | --- | --- |
| T1 | Login bị từ chối | `login/ DENIED` với decision time rõ | Không ghi `SUCCESS` hoặc token/password |
| T2 | Authorization denied | Event denial độc lập với transaction thay đổi | Không bỏ dấu vết chỉ vì không có state change |
| T3 | Role change commit thành công | Một event `role.change/COMMITTED` gắn đúng transition | Không ghi “committed” trước commit bằng chứng |
| T4 | Role change rollback | Không có `COMMITTED` tồn tại ở audit store committed; có thể có failure attempt audit riêng | Audit record success vẫn tồn tại sau rollback |
| T5 | DB commit OK nhưng process crash trước publish | Outbox/bản ghi audit vẫn có thể được phục hồi | Business change tồn tại nhưng audit bắt buộc mất vĩnh viễn |
| T6 | Publisher gửi rồi timeout ACK và retry | Same event ID, consumer dedup phù hợp | Hai event success logic khác nhau cho cùng transition |
| T7 | Chứng chỉ/collector down | Buffer/retry và alert theo policy, không tạo timestamp gốc mới | Tự ghi thời điểm nhận muộn vào `occurred_at` |
| T8 | Client retry cùng operation ID | Attempt IDs và business event IDs được phân biệt | Đếm số retry thành nhiều business commits |
| T9 | Commit outcome UNKNOWN | Pending reconciliation; không giả định failed | Sinh bản ghi kết luận sai |
| T10 | Clock skew giữa hai service | Lưu source/event time và thứ tự domain/sequence | Kết luận causality chỉ từ timestamp |
| T11 | Thay đổi có hiệu lực tương lai | `decision_at` và `effective_at` riêng | Ghi activated trước khi thật sự effective |
| T12 | Outbox/event queue backlog lớn | Event time được giữ, ingest lag tăng có số liệu | Thay timestamp hoặc âm thầm mất event |

### 12.2. Cách khẳng định end-to-end

Một bài test audit không nên chỉ assert rằng `logger.info(...)` được gọi. Hãy kiểm tra theo chuỗi:

1. **Nghiệp vụ:** trước/sau thao tác, authoritative state thay đổi hay không?
2. **Audit model:** `event_type`, `outcome`, `actor`, `subject` và timestamps phản ánh đúng kết quả?
3. **Ràng buộc transaction:** rollback xóa cả business change và audit success tương ứng? Outbox tồn tại khi commit?
4. **Publisher:** event ID và occurredAt có được giữ qua retry không?
5. **Audit store:** đã lưu event theo semantics durable của store? Có duplicate/thiếu row không?
6. **Search/backend:** event có thể truy vấn trong thời hạn, đúng tenant/namespace và không rò sang vùng khác?
7. **Security:** không ghi credential, token, PII vượt policy hoặc stack trace bí mật.
8. **Time quality:** timezone, precision, nguồn đồng hồ và clock offset đã được quan sát và dokument hóa?

Để tránh nhầm với dữ liệu thật, dùng `test_run_id`/`event_id` duy nhất trong staging. Với luồng bất đồng bộ, polling có deadline thay vì query ngay lập tức rồi kết luận thất bại. Khi test failure, mô phỏng crash và network partition trong môi trường được phép, sau đó đối chiếu **số transition nghiệp vụ đã commit** với **số audit event logic**.

### 12.3. Assert chính xác outcome

Một unit test mô phỏng các nhánh:

```text
given: no current role change
when: authorization denied
then:
  business role unchanged
  audit event outcome = DENIED
  no audit event role.change COMMITTED

given: authorized role change, DB transaction rolled back
then:
  business role unchanged
  no committed role.change audit event
  independent failed-attempt audit may exist

given: authorized role change, DB transaction committed
then:
  new role visible in authoritative store
  committed audit row/outbox persisted in same transaction
  eventual downstream audit event uses same event_id + occurred_at
```

Đây là **pseudocode kiểm thử**, không phải output của một framework. Unit test thuần có thể chứng minh logic thời điểm/field; tính nguyên tử và crash recovery cần integration/failure-injection test trên database/broker thật.

## 13. Những lỗi thường gặp khi chọn thời điểm audit

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Audit nói “SUCCESS” nhưng DB không đổi | Emit trước commit, hoặc không kiểm tra số row được UPDATE | Ghi success cùng commit/outbox hoặc sau confirmation có bảo đảm |
| DB đổi nhưng thiếu audit | Emit chỉ sau commit sang sink độc lập; crash hoặc sink lỗi | Transactional audit row/outbox, retry/reconciliation |
| Denied request không có dấu vết | Chỉ audit sau business transaction | Audit quyết định bị từ chối ở luồng độc lập |
| Sự kiện trông xảy ra vài phút sau | Thay event time bằng ingest/publish time | Giữ original occurredAt, lưu recorded/ingested riêng |
| Audit thành công hai lần sau retry | Event ID mới mỗi lần gửi hoặc consumer thiếu dedup | Stable event ID, idempotent consumer |
| Thứ tự audit khác thứ tự thay đổi | Parallel consumers, broker partitions, clock skew | Version/sequence/causal link theo aggregate |
| Log timestamp khác giờ trên dashboard | Timezone/offset parse sai, LocalDateTime mất zone | Dùng Instant/ISO-8601 offset, xác minh parser |
| “FAILED” nhưng dữ liệu đã commit | Network error sau commit ACK không rõ kết quả | UNKNOWN outcome và reconciliation |
| Không phân biệt attempted và activated | Một event cho nhiều milestone không đồng nghĩa | Event type/state transitions riêng |
| Incident investigation thiếu principal | Authn thất bại trước khi biết identity, filter hoặc dữ liệu bị ẩn | Lưu mã định danh/nguồn phù hợp policy và outcome rõ |
| Ingest lag cao nhưng app vẫn nhanh | Queue/collector tồn backlog | Theo dõi outbox age, queue lag và searchable latency |
| Source timestamp nằm trong tương lai | Clock skew hoặc client-supplied timestamp | Kiểm tra time sync, source trust, giới hạn hợp lệ |
| Process crash làm mất log cuối | Queue RAM không durable | Audit store/outbox durable, graceful shutdown và recovery |
| Audit nằm trong app log DEBUG | Filter/level/sampling của logger thông thường áp lên audit | Tách audit policy/route, kiểm thử bypass |
| Thay timestamp khi backfill | Dùng now() làm occurred_at cho sự kiện quá khứ | Giữ original event time, gắn replay/import time riêng |

## 14. Checklist thiết kế và vận hành

Trước khi xem một cơ chế audit là sẵn sàng, trả lời:

- [ ] Đã định nghĩa rõ **sự kiện** đang mô tả attempt, decision, committed effect hay processing state chưa?
- [ ] `occurred_at` được gắn tại đúng **domain boundary** và không thay đổi khi publish/retry?
- [ ] `recorded_at` và `ingested_at` có nghĩa riêng, không bị dùng thay event time?
- [ ] Dữ liệu thành công cần audit có được lưu nguyên tử với business state hoặc cùng outbox khi bắt buộc?
- [ ] Denied/rollback attempts có đường audit được quản lý độc lập với transaction rollback?
- [ ] Lỗi COMMIT ACK không rõ được biểu diễn `UNKNOWN` và reconciliation thay vì kết luận bừa?
- [ ] Event ID ổn định, consumer idempotent, duplicate/retry được phân biệt với operation mới?
- [ ] Clock sync, timezone, precision và nguồn timestamp được ghi rõ, có theo dõi clock drift?
- [ ] Các thay đổi có hiệu lực tương lai, saga compensation và approval có event riêng theo milestone?
- [ ] Auditing được tách khỏi filter DEBUG/sampling khi thuộc nhóm bắt buộc?
- [ ] Có kiểm thử crash, rollback, retry, collector down, async lag và duplicate?
- [ ] Audit store có phân quyền, retention, tamper-evidence và cơ chế phục hồi phù hợp?
- [ ] Có reconciliation định kỳ giữa business commits/outbox và audit sink, với cảnh báo sai lệch?
- [ ] Không có secret, raw token, password hoặc dữ liệu cá nhân không được phép trong audit payload?

**Tiêu chí hoàn thành:** Bạn phân biệt được thời điểm hành động, quyết định, commit, ghi nhận và ingest; không tạo audit success trước khi có kết quả authoritative; biết dùng transaction/outbox để tránh thiếu dấu vết; giữ timestamp gốc qua async/retry; và chứng minh bằng test rằng cả các nỗ lực bị từ chối lẫn các state change thành công được ghi đúng nghĩa.

## 15. Câu hỏi tự kiểm tra

1. Một sự kiện `role.changed` được ghi thành công ở log sink rồi transaction rollback: vấn đề nằm ở timestamp hay ở mô hình consistency/outcome?
2. Vì sao ghi audit ngoài transaction **sau** commit vẫn có thể làm mất record?
3. Nếu login bị từ chối và không có DB transaction, cần audit thời điểm nào?
4. Vì sao publisher retry không được thay `occurred_at` bằng thời gian hiện tại?
5. `Clock.fixed(...)` trong unit test giúp kiểm tra điều gì, và nó không chứng minh được điều gì?
6. `HTTP 202 Accepted` trong một workflow bất đồng bộ có đủ để ghi `COMMITTED` hay không?
7. Khi mất kết nối đúng lúc COMMIT, tại sao nên dùng `UNKNOWN` và reconciliation?
8. Nếu hai service có clock skew, có thể dùng event time làm thứ tự tuyệt đối giữa mọi event không?
9. Một user thay đổi role rồi rollback bằng thao tác bù trừ vài phút sau: có nên xóa event ban đầu không?
10. Làm sao phân biệt audit delivery “at-least-once” với việc business operation diễn ra hai lần?
11. Vì sao `System.nanoTime()` không dùng để ghi absolute audit timestamp across services?
12. Những bộ đếm hoặc reconciliation nào sẽ phát hiện outbox còn tồn backlog sau collector outage?

## Tài liệu tham khảo

- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — thời điểm UTC và biểu diễn ISO-8601.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) — nguồn thời gian có thể thay thế trong unit test.
- [Java SE 17 — OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html) — thời điểm có UTC offset để biểu diễn/hiển thị.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) — đo duration thay vì event timestamp toàn cục.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — sự kiện cần ghi, thời gian, đồng bộ, bảo vệ log.
- [OpenTelemetry — Semantic Conventions for Logs](https://opentelemetry.io/docs/specs/semconv/general/logs/) — thuộc tính và mối quan hệ log event với telemetry.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — `Timestamp` và `ObservedTimestamp` cùng ý nghĩa của chúng.
