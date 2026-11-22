# Audit logging: Thao tác nào đã xảy ra?

## 1. Câu hỏi cốt lõi của một audit event

Trong **audit logging**, câu hỏi “**Thao tác nào đã xảy ra?**” nhằm xác định **hành động cụ thể mà một tác nhân đã yêu cầu hoặc hệ thống đã thực hiện đối với một đối tượng**, kèm kết quả và phạm vi. Một bản ghi chỉ có “đã có hoạt động” hoặc “request thành công” chưa đủ để giải trình khi điều tra sự cố.

Giả sử hệ thống quản trị người dùng:

- `user updated`: quá mơ hồ — người dùng đổi tên, đổi mật khẩu hay thay quyền?
- `ROLE_GRANT`, `target=user:u-42`, `role=REPORT_VIEWER`, `outcome=SUCCEEDED`: cho biết **hành động cấp quyền**, đối tượng, quyền cụ thể và việc thực hiện đã thành công.
- `CUSTOMER_DATA_EXPORT`, `outcome=DENIED`, `reason=MISSING_PERMISSION`: cho biết đã có **yêu cầu xuất dữ liệu** nhưng hệ thống không cho phép thực hiện. Không được diễn đạt thành “đã xuất dữ liệu”.

Một audit event có ích thường trả lời nhóm câu hỏi:

| Câu hỏi | Trường/giải thích |
| --- | --- |
| **What? — Thao tác nào?** | `action`, loại thao tác có ngữ nghĩa nghiệp vụ rõ ràng |
| **Who? — Ai?** | `actorId` từ nguồn danh tính đã xác thực, hoặc service account |
| **On what? — Tác động lên gì?** | `targetType`, `targetId`, phạm vi/tài nguyên |
| **When? — Khi nào?** | `occurredAt` (UTC, theo định dạng thời gian chuẩn) |
| **Where/how? — Từ đâu/qua kênh nào?** | service, environment, client/source, API/automation |
| **Outcome? — Kết quả?** | `SUCCEEDED`, `DENIED`, `FAILED`, `PARTIAL`, `PENDING` |
| **Why? — Lý do hoặc căn cứ?** | `reasonCode`, ticket/approval, policy ID |
| **Which operation? — Liên hệ nào?** | `eventId`, `requestId`/`correlationId`, `transactionId` |

Trọng tâm của bài là **What?**: biểu diễn thao tác đủ chính xác để người đọc, máy truy vấn và người kiểm toán hiểu cùng một nghĩa. Những trường còn lại giúp xác định liệu thao tác **thật sự đã diễn ra**, ai chịu trách nhiệm, lên dữ liệu nào và với hậu quả gì.

**Audit log** khác **debug/application log**: bản ghi audit phục vụ giải trình một hành động đáng quan tâm; debug log phục vụ tìm nguyên nhân kỹ thuật. Không phải mọi dòng `logger.info(...)` đều trở thành audit event đáng tin cậy.

## 2. Tách “hành động được yêu cầu” khỏi “hành động đã hoàn tất”

Đây là nguyên tắc quan trọng nhất để tránh một audit trail sai sự thật.

```text
Nhận yêu cầu EXPORT_CUSTOMER_DATA
       |
       +--> xác thực/ủy quyền thất bại --> DENIED
       |
       +--> kiểm tra hợp lệ thất bại ---> VALIDATION_FAILED
       |
       +--> xử lý bắt đầu --------------> PENDING / STARTED
                 |
                 +--> giao dịch commit --> SUCCEEDED
                 +--> xử lý lỗi --------> FAILED
                 +--> một phần xong ----> PARTIAL
```

**Action** mô tả loại thao tác, còn **outcome** mô tả kết quả. Ví dụ:

| Action | Outcome | Diễn giải chính xác |
| --- | --- | --- |
| `GRANT_ROLE` | `SUCCEEDED` | Quyền đã được cấp và thay đổi đã được xác nhận theo hợp đồng nghiệp vụ |
| `GRANT_ROLE` | `DENIED` | Có yêu cầu cấp quyền nhưng bị từ chối; không được khẳng định quyền đã cấp |
| `EXPORT_CUSTOMER_DATA` | `PENDING` | Yêu cầu xuất dữ liệu đã được tiếp nhận/đang xử lý, chưa xác nhận việc xuất |
| `EXPORT_CUSTOMER_DATA` | `SUCCEEDED` | Việc xuất dữ liệu đã hoàn thành theo điểm xác nhận được định nghĩa |
| `DELETE_DOCUMENT` | `FAILED` | Thao tác xóa không hoàn tất như dự kiến |
| `BULK_DISABLE_USERS` | `PARTIAL` | Một phần đối tượng đã thay đổi; phải có chi tiết hoặc liên kết đến danh sách kết quả |
| `CHANGE_LOG_LEVEL` | `SUCCEEDED` | Mức log mục tiêu đã được cập nhật và xác minh ở phạm vi đã cam kết |

Một thao tác có thể có **nhiều event vòng đời** (attempt, started, result) cùng một `operationId`, hoặc một event tổng kết có trường `requestedAction` và `outcome`. Cách nào cũng được nếu quy ước thống nhất; **không đặt tên một event `DOCUMENT_DELETED` khi mới kiểm tra quyền hoặc mới nhận yêu cầu**.

Đặc biệt với thao tác bất đồng bộ, HTTP `202 Accepted` thường chỉ chứng minh yêu cầu đã được tiếp nhận, không chứng minh tác vụ nền hoàn tất. HTTP `200` của một API cũng phải được hiểu theo hợp đồng API: có thể trả về trước khi dữ liệu được đồng bộ hết các hệ thống downstream.

## 3. Đặt tên action theo ngôn ngữ nghiệp vụ

Tên action phải đủ **ổn định, nhất quán, truy vấn được**, tránh phụ thuộc nội dung thông điệp tự do.

Một quy ước phổ biến dùng động từ + đối tượng:

```text
USER_LOGIN
USER_LOGOUT
PASSWORD_RESET_REQUEST
PASSWORD_RESET_COMPLETE
GRANT_ROLE
REVOKE_ROLE
CREATE_API_KEY
ROTATE_API_KEY
DISABLE_ACCOUNT
APPROVE_PAYMENT
REFUND_PAYMENT
EXPORT_CUSTOMER_DATA
DELETE_DOCUMENT
CHANGE_LOG_LEVEL
UPDATE_LOG_RETENTION
```

Có thể chọn `ROLE_GRANTED` (thì quá khứ, biểu thị sự kiện đã xảy ra) thay cho `GRANT_ROLE` (loại lệnh) **nếu schema đã thống nhất và ghi rõ trạng thái**. Hai trường hợp thiết kế:

1. **Action dạng lệnh:** `action=GRANT_ROLE`, `outcome=DENIED|SUCCEEDED`. Hữu ích để bao quát mọi nỗ lực.
2. **Event type dạng sự kiện:** `eventType=ROLE_GRANTED`, chỉ phát sau khi thành công; đồng thời có `ROLE_GRANT_DENIED` hoặc `ROLE_GRANT_ATTEMPTED` cho các nhánh khác.

Không được trộn lẫn ý nghĩa hai kiểu một cách tùy tiện. Nếu `ROLE_GRANTED` vừa dùng khi mới có yêu cầu, vừa dùng khi đã commit, dữ liệu audit trở nên mâu thuẫn.

### 3.1. Tên nào đủ cụ thể?

| Tên mơ hồ | Tên nên cân nhắc | Tại sao |
| --- | --- | --- |
| `UPDATE` | `CHANGE_USER_EMAIL` | Nêu rõ thuộc tính có ý nghĩa |
| `ACCESS` | `READ_SENSITIVE_RECORD` | Phân biệt đọc dữ liệu nhạy cảm và đăng nhập |
| `LOGIN` | `USER_LOGIN` + outcome | Biết đây là nỗ lực đăng nhập hay thành công |
| `CHANGE_SETTING` | `CHANGE_LOG_LEVEL` | Nêu đúng chính sách bị sửa |
| `TRANSACTION` | `REFUND_PAYMENT` | Giải thích tác động tài chính |
| `ADMIN_ACTION` | `REVOKE_ROLE` | Có thể xác minh quyền đã bị thu hồi |
| `DELETE` | `DELETE_API_KEY` | Có thể gắn chính xác target type |

Không tách thành vô số action cho mọi giá trị nhỏ không cần thiết. Ví dụ `CHANGE_USER_EMAIL` có thể dùng `changedFields=["email"]` hoặc `field=email` nhưng **không** tạo action riêng cho từng giá trị email. Tham số cấu hình và giá trị trước/sau nên là **thuộc tính** chứ không lồng vào tên action như `SET_LEVEL_DEBUG_FOR_PAYMENT`.

### 3.2. Danh mục action và version schema

Nên duy trì **action catalog** (danh mục thao tác) với:

- Mã action và mô tả ngữ nghĩa.
- Điều kiện đánh dấu `SUCCEEDED`/hoàn tất.
- Target type và các trường bắt buộc.
- Nguồn actor tin cậy.
- Level nhạy cảm và phạm vi cần ghi audit.
- Quy định dữ liệu được phép lưu, retention và cảnh báo.
- Schema version nếu thay đổi ý nghĩa/trường.

Ví dụ:

```text
action: GRANT_ROLE
meaning: cấp một role cho một tài khoản
success_boundary: transaction cấp role đã commit
targetType: USER
required_context: actorId, targetId, roleCode, requestId, occurredAt, outcome
restricted_fields: password, sessionToken, fullProfile
```

Một tên action nên giữ một ý nghĩa xuyên các phiên bản; khi ngữ nghĩa thay đổi đáng kể, cần schema version hoặc action mới để truy vấn lịch sử không bị hiểu sai.

## 4. Phân biệt action, object, field và outcome

Một mẫu audit event:

```json
{
  "schemaVersion": 1,
  "eventId": "evt-0001",
  "action": "GRANT_ROLE",
  "outcome": "SUCCEEDED",
  "actorId": "admin-7",
  "targetType": "USER",
  "targetId": "u-42",
  "attributes": {
    "roleCode": "REPORT_VIEWER"
  },
  "requestId": "req-100",
  "occurredAt": "2026-11-10T02:00:00Z",
  "service": "identity-service"
}
```

Trong ví dụ này:

- `action=GRANT_ROLE`: thao tác **cấp quyền**.
- `targetType=USER`, `targetId=u-42`: **đối tượng** nhận quyền.
- `attributes.roleCode`: **thuộc tính** của thao tác, không phải loại action mới.
- `outcome=SUCCEEDED`: thao tác đã **hoàn tất** theo hợp đồng nghiệp vụ.
- `occurredAt`: thời gian phát sinh event; timestamp ở đây là **minh họa**, không lấy từ hệ thống thực tế.
- `eventId` và `requestId`: nhận diện event và tương quan tới yêu cầu; hai mã không nhất thiết trùng nhau.

Không nhất thiết ghi toàn bộ đối tượng user vào log. Audit thường cần ID ổn định, trường được phép và giá trị thay đổi **đã lọc nhạy cảm**. Bản ghi ví dụ không chứng minh đã được ghi bền vững hay bất biến; đó là yêu cầu riêng của pipeline.

## 5. Nên audit thao tác nào?

Không nên log mọi lần gọi getter như một sự kiện kiểm toán. Chọn theo rủi ro và yêu cầu điều tra/tuân thủ, ví dụ:

1. **Authentication:** đăng nhập thành công/thất bại, logout, thay đổi MFA, reset mật khẩu, session bị thu hồi.
2. **Authorization:** cấp/thu hồi role, đổi policy, thay quyền truy cập, thao tác bị từ chối vì thiếu quyền.
3. **Dữ liệu nhạy cảm:** xem, xuất, tải xuống, chia sẻ, xóa hoặc khôi phục dữ liệu nhạy cảm, nếu chính sách yêu cầu.
4. **Thay đổi quan trọng:** bật/tắt tài khoản, đổi cấu hình an ninh, cấu hình logging/audit, đổi retention, quản lý API key.
5. **Tài chính và nghiệp vụ có rủi ro:** phê duyệt, hoàn tiền, hủy giao dịch, thay thông tin thanh toán, đổi trạng thái đơn quan trọng.
6. **Quản trị hạ tầng:** deploy, rollback, truy cập privileged, thay chính sách mã hóa và đích lưu log.
7. **Nỗ lực bị chặn:** truy cập trái phép, thao tác không đủ quyền hoặc bị policy từ chối.

Với sự kiện đọc dữ liệu (read access) lưu lượng cao, cần xác định rõ **phạm vi dữ liệu được audit** để cân bằng quyền riêng tư, hiệu năng và yêu cầu pháp lý. Sampling có thể hợp lý với telemetry, nhưng **không tùy tiện sampling các audit event bắt buộc phải ghi**.

Khi thao tác gộp nhiều bước (ví dụ cấp quyền rồi gửi email thông báo), chỉ đánh dấu `GRANT_ROLE/SUCCEEDED` khi điều kiện thành công của **cấp quyền** đã thỏa. Việc gửi email có thể là sự kiện riêng `SEND_NOTIFICATION`; lỗi email không tự động có nghĩa quyền chưa được cấp.

## 6. Java 17: chương trình minh họa action và outcome chạy độc lập

Ví dụ Java 17 sau tạo hai audit event bằng `record` và `enum`, có đầu ra cố định để dễ kiểm tra:

- Một yêu cầu **cấp role** đã hoàn tất.
- Một yêu cầu **xuất dữ liệu** bị từ chối vì không đủ quyền.

Bài dùng dữ liệu cố định, **không tuyên bố có xác thực/ủy quyền thật** hoặc transaction database. Mục tiêu là minh họa cách mô tả “thao tác nào” bằng action có cấu trúc và outcome riêng.

Lưu file **`AuditActionDemo.java`**:

```java
import java.time.Instant;
import java.util.Objects;

public class AuditActionDemo {
    enum Action {
        GRANT_ROLE,
        EXPORT_CUSTOMER_DATA
    }

    enum Outcome {
        SUCCEEDED,
        DENIED,
        FAILED
    }

    record AuditEvent(
            String eventId,
            Instant occurredAt,
            String actorId,
            Action action,
            String targetType,
            String targetId,
            Outcome outcome,
            String reasonCode,
            String requestId) {

        AuditEvent {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(occurredAt);
            Objects.requireNonNull(actorId);
            Objects.requireNonNull(action);
            Objects.requireNonNull(targetType);
            Objects.requireNonNull(targetId);
            Objects.requireNonNull(outcome);
            Objects.requireNonNull(reasonCode);
            Objects.requireNonNull(requestId);
        }
    }

    static void emit(AuditEvent event) {
        // Đầu ra text cố định chỉ để học: không có durable audit sink.
        System.out.println("event=" + event.eventId()
                + " action=" + event.action()
                + " outcome=" + event.outcome()
                + " actor=" + event.actorId()
                + " target=" + event.targetType()
                + ":" + event.targetId()
                + " reason=" + event.reasonCode()
                + " request=" + event.requestId()
                + " time=" + event.occurredAt());
    }

    public static void main(String[] args) {
        emit(new AuditEvent(
                "evt-001",
                Instant.parse("2026-01-01T00:00:00Z"),
                "admin-7",
                Action.GRANT_ROLE,
                "USER",
                "u-42",
                Outcome.SUCCEEDED,
                "APPROVED",
                "req-100"));

        emit(new AuditEvent(
                "evt-002",
                Instant.parse("2026-01-01T00:00:01Z"),
                "analyst-5",
                Action.EXPORT_CUSTOMER_DATA,
                "DATASET",
                "customers",
                Outcome.DENIED,
                "MISSING_PERMISSION",
                "req-101"));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac AuditActionDemo.java
java AuditActionDemo
```

Kết quả **`stdout` chính xác**:

```text
event=evt-001 action=GRANT_ROLE outcome=SUCCEEDED actor=admin-7 target=USER:u-42 reason=APPROVED request=req-100 time=2026-01-01T00:00:00Z
event=evt-002 action=EXPORT_CUSTOMER_DATA outcome=DENIED actor=analyst-5 target=DATASET:customers reason=MISSING_PERMISSION request=req-101 time=2026-01-01T00:00:01Z
```

Giải thích:

1. `enum Action` giới hạn danh mục hành động của ví dụ, giúp tránh gõ nhầm giá trị `"update"` tùy tiện.
2. `enum Outcome` tách **loại thao tác** khỏi **trạng thái hoàn tất**.
3. `record AuditEvent` tạo mô hình bất biến nông (shallow immutable) theo ngữ nghĩa record; các trường đều là kiểu bất biến trong ví dụ.
4. `Objects.requireNonNull(...)` từ chối trường thiếu nhưng **không thay thế kiểm tra nghiệp vụ** như actor có được xác thực, action có được phép hay target có tồn tại.
5. `Instant.parse(...)` đưa ra timestamp cố định. Trong ứng dụng thật, timestamp lấy từ clock đáng tin và gắn timezone rõ.
6. Mã in một chuỗi dễ đọc nhưng không giải quyết escaping của dữ liệu đầu vào: nếu actor/target do nguồn không tin cậy cung cấp có newline, chúng có thể tạo **log injection**. Production nên dùng serializer JSON/structured log an toàn và giới hạn độ dài, kiểm tra control characters.
7. Hai event được **giả lập** để minh họa cấu trúc. `SUCCEEDED` là kết luận mô phỏng; trong nghiệp vụ thật chỉ được tạo sau khi đã xác minh điều kiện thành công.

Chương trình không cần SLF4J, Logback hay cơ sở dữ liệu. Nó minh họa **nội dung event**, không phải một audit trail chống xóa/sửa.

### 6.1. Vì sao không chỉ dùng `logger.info("Updated")`?

Thông điệp không có action code, đối tượng, actor và outcome sẽ khó truy vấn:

```text
INFO Updated
INFO Done
ERROR Something failed
```

Một truy vấn audit muốn biết “bao nhiêu lần xuất dữ liệu bị từ chối” phải dựa vào parser suy đoán nội dung văn bản. Với schema `action=EXPORT_CUSTOMER_DATA AND outcome=DENIED`, hệ thống có thể đếm và phân tích chính xác hơn mà không phụ thuộc ngôn ngữ diễn đạt của message.

Khi dùng logging framework, có thể cung cấp các trường cấu trúc thông qua API/encoder tương ứng; không mặc định mọi backend tạo JSON chỉ vì gọi `logger.info`.

## 7. Ghi audit event ở đúng ranh giới thành công

### 7.1. Thay đổi dữ liệu trong một transaction

Giả sử `GRANT_ROLE` thay đổi một bản ghi cơ sở dữ liệu. Ghi `SUCCEEDED` **trước commit** có nguy cơ nói sai:

```text
BEGIN TRANSACTION
   UPDATE user_role
   log "GRANT_ROLE SUCCEEDED"
ROLLBACK (do deadlock / constraint / exception)
```

Audit đã khẳng định vai trò được cấp dù transaction thất bại.

Một mô hình chặt hơn:

```text
BEGIN TRANSACTION
   validate + authorize
   UPDATE role mapping
   INSERT audit/outbox record cùng transaction (nếu phù hợp)
COMMIT
   -> chỉ khi commit thành công, thao tác nghiệp vụ và event tương ứng có hiệu lực
   -> publisher chuyển event đã commit tới hệ thống audit
```

**Transactional outbox** giúp lưu business state và event trong cùng một transaction database, giảm khe hở giữa cập nhật nghiệp vụ và ghi một thông điệp audit. Tuy nhiên:

- Publisher gửi sau commit có thể giao lại nhiều lần → consumer cần idempotency theo `eventId`.
- Nếu database transaction bị rollback, event trong outbox cũng rollback; nếu cần ghi **nỗ lực thất bại**, nó phải dùng đường audit riêng không bị rollback cùng nghiệp vụ.
- Nếu audit sink ngoài database không hoạt động, record outbox đã commit cần cơ chế retry, backlog, monitoring, retention và xử lý khi outbox đầy.
- Không mặc định “đã insert outbox” đồng nghĩa hệ thống audit cuối cùng đã nhận hoặc lưu bền vững.

Nếu nghiệp vụ chỉ sửa state bộ nhớ hoặc gọi API downstream, không có transaction chung với sink khác thì cần hợp đồng sự kiện và điểm xác nhận rõ ràng, không gắn `SUCCEEDED` dựa trên giả định.

### 7.2. Thao tác đọc không thay đổi state

Với `VIEW_SENSITIVE_RECORD` hay `EXPORT_CUSTOMER_DATA`, “thành công” cần định nghĩa theo **điểm dữ liệu được truy cập hoặc chuyển giao**:

- `ACCESS_REQUESTED`: request tới API đã được ghi nhận, chưa chắc dữ liệu được đọc.
- `AUTHORIZATION_DENIED`: bị chặn trước khi đọc.
- `RECORD_READ_SUCCEEDED`: dữ liệu đã được truy xuất theo tiêu chí của hệ thống, nhưng chưa chắc client đã nhận.
- `EXPORT_READY`: file xuất đã tạo xong; chưa chắc được tải xuống.
- `EXPORT_DOWNLOADED`: hệ thống ghi nhận một lượt tải theo giao thức đang dùng; không thể suy ra người dùng đã đọc nội dung.

Nếu một luồng streaming bị ngắt giữa chừng, `PARTIAL` hoặc event về lỗi truyền có thể chính xác hơn `SUCCEEDED`. Không tự suy ra tình trạng cuối từ HTTP status nếu hợp đồng không đủ.

## 8. Trạng thái phức tạp: nhiều bước, bất đồng bộ và retry

Một thao tác `REFUND_PAYMENT` có thể trải qua:

```text
Refund requested -> authorization approved
      |
      -> payment provider accepted
      |
      -> settlement completed / rejected
      |
      -> ledger updated
```

Vì vậy cần định nghĩa action tương ứng với từng **mốc nghiệp vụ**:

| Event/action | Ý nghĩa |
| --- | --- |
| `REFUND_REQUESTED` | Đã tiếp nhận ý định hoàn tiền |
| `REFUND_SUBMITTED` | Đã gửi yêu cầu tới nhà cung cấp |
| `REFUND_SETTLED` | Đã nhận bằng chứng quyết toán theo hợp đồng |
| `REFUND_FAILED` | Quy trình không hoàn tất, có mã lỗi được chuẩn hóa |

Không đánh dấu `REFUND_SETTLED` khi mới nhận HTTP `202` từ provider. Một provider có thể phản hồi nhận yêu cầu rồi xử lý bất đồng bộ; webhook/response sau mới cho biết kết quả.

### 8.1. Nhiều event cho một operation

Dùng định danh khác nhau:

- `eventId`: duy nhất cho **mỗi audit event**, phục vụ idempotency.
- `operationId`: chung cho **một thao tác nghiệp vụ** xuyên nhiều bước.
- `requestId`: định danh request vào service; một request có thể kích hoạt nhiều operation.
- `traceId`: để tương quan với distributed tracing; không thay thế `operationId` và không phải bằng chứng danh tính.
- `causationId`: liên hệ event hiện tại với event/lệnh gây ra nó.

Ví dụ:

```json
{
  "eventId": "evt-2202",
  "operationId": "refund-77",
  "action": "REFUND_PAYMENT",
  "phase": "RESULT",
  "outcome": "FAILED",
  "reasonCode": "PROVIDER_REJECTED",
  "requestId": "req-88"
}
```

Khi retry, có thể xuất hiện nhiều attempt nhưng chỉ một operation; cần biết một retry là **lần thực thi lại cùng lệnh** hay **yêu cầu nghiệp vụ mới**. Một event `SUCCEEDED` bị gửi lại do lỗi mạng vẫn là một sự kiện, không được đếm thành hai lần hoàn tiền thành công.

### 8.2. Bulk và partial success

Với một thao tác `BULK_REVOKE_ROLE` trên 100 tài khoản, `SUCCEEDED` toàn cục chỉ hợp lệ nếu điều kiện thành công đã thỏa cho cả tập mục tiêu. Nếu 98 thành công, hai thất bại thì:

- Ghi một event tổng hợp `PARTIAL` với `successCount=98`, `failureCount=2`.
- Có thể ghi event riêng theo target phục vụ truy vết, không đưa danh sách ID không giới hạn vào một message.
- Liên kết các event bằng `operationId`, không giả định mỗi event con cùng kết quả.
- Cần định nghĩa cách đếm khi retry, rollback hoặc một target được xử lý hai lần.

Không có một “thao tác nào đã xảy ra” duy nhất nếu business operation bao gồm nhiều hành động độc lập. Hãy phân rã thành những event có ranh giới có thể xác minh.

## 9. Who và What phải được ghi từ nguồn tin cậy

Một `actorId` do client gửi trong body không thể mặc nhiên được coi là danh tính đáng tin. Với audit hành động:

- Lấy actor từ **principal/token/session đã xác thực**.
- Ghi `actorType` nếu có người, service account, scheduled job hoặc automation.
- Phân biệt `initiator` (ai tạo yêu cầu), `approver` (ai phê duyệt) và `executor` (ai thực thi) nếu khác nhau.
- Với `DENIED` do chưa được xác thực, có thể không có actor đã xác thực; cần dùng `anonymous`/nhãn theo policy, không tự gán username tự khai là danh tính đã kiểm chứng.
- `targetId` phải là ID của tài nguyên thực tế, không dùng tên hiển thị dễ đổi hoặc URL chứa secret làm định danh chính.
- Với các thao tác nhạy cảm, ghi scope phù hợp như `tenantId`, `organizationId`, `environment` theo quyền và chính sách retention; không lộ thêm dữ liệu không cần thiết.

**Một log line không phải bằng chứng duy nhất để xác nhận actor và action.** Cần liên kết với authorization decision, transaction, signed request, approval hoặc nguồn sự thật khác nếu threat model yêu cầu.

## 10. Trước và sau: mô tả điều gì đã thay đổi

Một action `CHANGE_ACCOUNT_STATUS` chỉ cho biết loại thao tác. Với điều tra, có thể cần biết trạng thái trước/sau:

```json
{
  "action": "CHANGE_ACCOUNT_STATUS",
  "outcome": "SUCCEEDED",
  "targetType": "ACCOUNT",
  "targetId": "acct-52",
  "before": {"status": "ACTIVE"},
  "after": {"status": "SUSPENDED"},
  "changedFields": ["status"]
}
```

Chỉ lưu **các trường đã được cho phép**. Nhiều thay đổi cấu hình, mật khẩu, API key hoặc dữ liệu y tế/tài chính **không nên** ghi giá trị đầy đủ.

- Với password reset: `action=RESET_PASSWORD`, `outcome=SUCCEEDED`, nhưng **không ghi mật khẩu/hash mới**.
- Với API key rotation: lưu key ID, phiên bản, metadata được phép; không ghi token/secret.
- Với policy change: có thể lưu `policyId`, `fromVersion`, `toVersion`, `approvedSnapshotHash` nếu phù hợp; không dump mọi cấu hình.
- Với `GRANT_ROLE`: có thể lưu mã role và target, không ghi toàn bộ danh sách quyền có thể thay đổi rất lớn.
- Với `DELETE_DOCUMENT`: nên xác định xóa mềm, xóa cứng hay chỉ đánh dấu chờ xóa, vì nghĩa của action khác nhau.

Nếu `before/after` được đọc trước và sau thao tác trong hai thời điểm không được đồng bộ, một thay đổi đồng thời có thể làm dữ liệu audit sai. Cần gắn version/transaction ID hoặc dùng cơ chế ghi state và audit nhất quán.

## 11. Java logging framework và việc mang action vào sự kiện

### 11.1. JUL: phù hợp cho demo, không mặc định là audit storage

`java.util.logging.Logger` cho phép ghi:

```java
// Đoạn minh họa: auditLogger và event là biến trong ứng dụng.
auditLogger.info("action=" + event.action()
        + " outcome=" + event.outcome()
        + " target=" + event.targetId());
```

Nhưng việc log được JUL chấp nhận còn chịu ảnh hưởng của logger level, handler level, filter, `LogManager`, đường xuất log và lỗi sink. Một dòng `INFO` **không đảm bảo** đã ghi vào nơi lưu kiểm toán an toàn.

### 11.2. SLF4J/Logback

Trong ứng dụng dùng SLF4J, có thể có logger audit riêng:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Trường được đặt trong một class hợp lệ:
private static final Logger AUDIT =
        LoggerFactory.getLogger("com.example.audit.ActionEvents");

// Trong phương thức xử lý event, các biến đã được xác thực:
AUDIT.info("action={} outcome={} actor={} target={}",
        actionCode, outcomeCode, actorId, targetId);
```

Đây là **mảnh tích hợp**, không phải file Java độc lập; cần dependency SLF4J và backend phù hợp. Dùng placeholder tránh nối chuỗi không cần thiết, nhưng **không tự escape newline, che secret hoặc tạo JSON**. Trong production, ưu tiên encoder/event API có các trường cấu trúc và đường audit riêng.

Ví dụ `logback.xml` để **định tuyến sơ bộ** các event sang file:

```xml
<configuration>
    <appender name="AUDIT_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/audit-actions.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit.ActionEvents"
            level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>
</configuration>
```

Đây là cấu hình minh họa cho Logback Classic có các dependency thích hợp. Thư mục đích cần quyền ghi; phải bổ sung rotation, retention, log shipper và bảo vệ lưu trữ nếu môi trường yêu cầu. `additivity="false"` tránh đẩy lại audit events lên appender của logger tổ tiên, **không** tự làm bản ghi bất biến hay bền vững. `append=true` chỉ mở file theo chế độ ghi nối; người có quyền vẫn có thể sửa/xóa file.

### 11.3. Log4j 2, Spring Boot và context

Log4j 2 có API `org.apache.logging.log4j.Logger`, filters và appenders riêng; Spring Boot có thể sử dụng SLF4J cùng backend cấu hình. **Không sao chép cấu hình Logback XML sang Log4j 2 XML**.

MDC (SLF4J) hoặc `ThreadContext` (Log4j 2) giúp gắn `requestId`, `operationId`, service/tenant vào mỗi event. Nhưng:

- **MDC không tự tạo audit action**: code nghiệp vụ phải phát sự kiện với action/outcome cụ thể.
- Context trong thread pool hoặc async pipeline có thể cần được **propagate** rõ ràng.
- Phải **clear/remove** context trong `finally` hoặc scope tương ứng để không lẫn request.
- Không dùng một ID do client tự đặt làm bằng chứng xác thực danh tính.
- Đừng để giá trị MDC không kiểm duyệt làm tên file, topic hoặc đường routing tự do.

Một event action có thể được gửi tới nhiều appender; nếu hệ thống đếm số bản ghi mà không deduplicate theo `eventId`, có thể ghi nhầm một hành động thành hai hành động.

## 12. Bảo mật nội dung và chống log injection

Audit logging thường xử lý dữ liệu nhạy cảm và có giá trị cho kẻ tấn công. Dữ liệu phải được thiết kế ngay từ nguồn:

1. **Không ghi secret** như password, token, API key, private key, session cookie, credential, recovery code.
2. **Không ghi payload đầy đủ** khi chỉ cần action/target/field đã thay đổi; hạn chế PII theo chính sách.
3. **Escape/serialize an toàn**: chuỗi actor, resource name hoặc `reason` có thể chứa newline, tab, dấu quote hoặc control characters. Không nối dữ liệu không tin cậy để sinh ra log line giả.
4. **Giới hạn độ dài và loại dữ liệu**: một `reason` chứa vài MB text có thể làm đầy queue hoặc phá cấu trúc event.
5. **Không để người dùng tự chọn action code tự do** nếu hành động cần một enum/catalog; xác định action theo nghiệp vụ phía server.
6. **Ghi nhận thao tác bị từ chối** mà không lộ chi tiết bảo mật nội bộ trong message trả cho client.
7. **Phân quyền đọc bản ghi audit** khác với log ứng dụng thông thường; audit có thể tiết lộ quyền, đối tượng và dòng hoạt động nhạy cảm.
8. **Áp dụng retention và xóa theo chính sách**, không để audit lưu vô hạn mọi thông tin cá nhân.

Khi cần giữ `before/after` của đối tượng nhạy cảm, nên lưu **ID/version/field name** và tham chiếu tới snapshot được bảo vệ; không coi `hash(secret)` là tự động an toàn, nhất là với dữ liệu đầu vào có entropy thấp.

**Structured logging** với schema cố định giúp giảm rủi ro parse sai, nhưng không ngăn leak nếu chính trường structured vẫn chứa secret. Trách nhiệm lọc dữ liệu vẫn thuộc về logic tạo event và policy quản trị.

## 13. Độ tin cậy: có event không đồng nghĩa đã lưu

Một luồng xử lý thường là:

```text
operation -> AuditEvent created
               |
               v
          logger/appender
               |
          async queue (optional)
               |
        file/collector/network
               |
       durable storage / retention
```

Nếu event nằm trong RAM queue rồi process crash, event có thể mất. Nếu sink đầy, appender có thể drop hoặc chặn request. Nếu collector retry, event có thể xuất hiện **hai lần**.

Với audit bắt buộc giữ, cần xác định:

- **Mức xác nhận:** accepted into queue, accepted by remote service, persisted, replicated, hay retention enforced.
- **Failure policy:** khi audit store lỗi thì từ chối thao tác (fail-closed), chuyển vào durable outbox hoặc thực hiện quy trình ngoại lệ đã được phê duyệt.
- **Retry và idempotency:** `eventId` ổn định giúp consumer nhận diện sự kiện gửi lại.
- **Bảo vệ bằng chứng:** append-only/immutable storage, phân tách quyền, integrity, retention và giám sát.
- **Đối soát:** đối chiếu state change/transaction/outbox với trail, phát hiện missing events.
- **Bảo mật khi truyền:** TLS, xác thực producer, authorization của sink.

Không nói “không mất audit log” nếu hệ thống chỉ gọi `logger.info(...)` hoặc `queue.offer(event)` rồi kết thúc. Nếu audit là yếu tố bắt buộc của một giao dịch, cần thiết kế điều kiện commit/độ bền một cách rõ ràng.

## 14. Tìm kiếm và trả lời “Thao tác nào đã xảy ra?” khi điều tra

Những truy vấn phân tích có ích:

- “Tài khoản `u-42` đã bị **cấp hoặc thu hồi quyền nào** trong khoảng thời gian này?”
- “Ai đã yêu cầu `EXPORT_CUSTOMER_DATA` và **bao nhiêu lần bị từ chối**?”
- “Có thao tác `DELETE_DOCUMENT` nào **thành công** trước khi tài liệu biến mất?”
- “Một yêu cầu hoàn tiền có các phase nào, đã dừng ở đâu?”
- “Những `CHANGE_LOG_LEVEL` nào bật DEBUG ở production, ai phê duyệt và khi nào rollback?”

Với schema như phần đầu, truy vấn khái niệm:

```text
action = "GRANT_ROLE"
AND outcome = "SUCCEEDED"
AND targetType = "USER"
AND targetId = "u-42"
```

Đây là **bộ lọc minh họa**, không phải SQL hay truy vấn cú pháp cụ thể cho một hệ thống lưu trữ nhất định. Truy vấn chỉ đáng tin nếu event được tạo đúng thời điểm, có dữ liệu đầy đủ, không bị drop và có bảo vệ tính toàn vẹn theo mục tiêu kiểm toán.

Đừng chỉ truy vấn `message contains "role"` vì có thể bắt cả thông báo “role check failed” lẫn hành động thực sự “role granted”. Một trường `action` có ngữ nghĩa chuẩn giúp máy và con người thống nhất.

### 14.1. Sắp xếp sự kiện khi nhiều service

Các node có thể lệch đồng hồ, network có thể gửi lại hoặc giao event không đúng thứ tự. Để tái dựng hành động:

- Dùng timestamp UTC và nguồn đồng hồ đồng bộ, nhưng **không dùng timestamp đơn độc làm khóa sự kiện**.
- Dùng `eventId`, `operationId` và nếu phù hợp `sequenceNo` theo operation.
- Giữ cả `occurredAt` và `ingestedAt` để biết độ trễ.
- Phân biệt `event order` trong một transaction với thứ tự đến của collector.
- Kết hợp với state/version/transaction log đáng tin để xác nhận kết quả thực.

Nếu hai bản ghi cùng `eventId` do retry, chỉ nên tính là một sự kiện logic; nếu cùng `operationId` nhưng khác `eventId`, có thể đó là các phase/attempt khác nhau.

## 15. Kiểm thử cách ghi action và outcome

Kiểm thử nên đặt câu hỏi **người điều tra có thể kết luận đúng không?**, không chỉ “có ghi log hay không”.

| Tình huống | Audit kỳ vọng |
| --- | --- |
| Cấp quyền thành công sau commit | `GRANT_ROLE/SUCCEEDED`, target và role chính xác |
| Cấp quyền bị từ chối | `GRANT_ROLE/DENIED`, state không đổi |
| Thao tác bị validation từ chối | `VALIDATION_FAILED` và mã lý do phù hợp |
| Transaction rollback sau khi xử lý | Không có một event `SUCCEEDED` sai |
| Background job mới được xếp hàng | `PENDING` hoặc event accepted, không phải completed |
| Export xong nhưng download thất bại | Event export và delivery tách rõ theo contract |
| Bulk 98/100 thành công | `PARTIAL`, có bằng chứng theo target |
| Retry gửi cùng event hai lần | Consumer không đếm thành hai hành động |
| Actor từ body giả mạo admin | Actor audit chỉ phản ánh identity đã xác thực |
| Target chứa newline/control chars | Không sinh dòng audit giả, không làm hỏng JSON/schema |
| Một trường chứa secret | Secret không bị ghi ra file, queue, collector hoặc search index |
| Async queue đầy/sink lỗi | Chính sách ghi audit và trạng thái nghiệp vụ vẫn đúng theo contract |

Nên viết **unit test** cho action catalog, mapping outcome và redaction; **integration test** cho transaction/rollback/outbox; **end-to-end test** cho delivery và truy vấn. Test xác nhận cả **số event** lẫn **nội dung các trường**, tránh ghi trùng và thiếu sự kiện.

Với các action có hậu quả cao, đánh giá cả trường hợp audit sink không sẵn sàng: hệ thống có từ chối thao tác, ghi outbox bền vững hay đưa vào quy trình khẩn cấp được phê duyệt? Quy tắc phải có trước sự cố.

## 16. Các lỗi phổ biến

### Lỗi 1: Action chỉ là `UPDATE` hoặc `DELETE`

Không có đối tượng/ý nghĩa, khó xác định người dùng đã sửa gì. Dùng action có ngữ nghĩa hoặc bổ sung targetType và changedFields được kiểm soát.

### Lỗi 2: Ghi `SUCCEEDED` khi vừa nhận request

Một request có thể bị từ chối, rollback hoặc thất bại trong job nền. Tách attempt/accepted khỏi result và xác minh theo điểm hoàn tất thật.

### Lỗi 3: Dùng `ROLE_GRANTED` cho cả nỗ lực bị từ chối

Tên sự kiện khiến người đọc tưởng role đã được cấp. Dùng `GRANT_ROLE` + `outcome=DENIED` hoặc một event type riêng `ROLE_GRANT_DENIED`.

### Lỗi 4: Lẫn actor với target

Trong “admin cấp role cho user”, admin là **actor**, user là **target**; nếu user thực hiện yêu cầu thay người khác hoặc qua automation, còn có initiator/executor/approver.

### Lỗi 5: Audit theo câu tiếng Anh tự do

`"Updated user"`, `"User is done"`, `"Change passed"` khó phân tích tự động và có thể bị dịch/đổi wording. Giữ `action` code ổn định, message chỉ để người đọc.

### Lỗi 6: Chỉ ghi debug log sau thao tác

DEBUG có thể bị tắt hoặc mất, không có policy bảo vệ. Với audit bắt buộc, cần pipeline và retention riêng.

### Lỗi 7: Log toàn bộ before/after

Có thể lộ password, PII, token, secret hoặc dữ liệu không liên quan. Ghi những thuộc tính đã cho phép, tránh payload thô.

### Lỗi 8: Đặt thao tác nghiệp vụ trong nhánh logger

```java
// Sai: việc cấp quyền có thể bị bỏ qua khi audit logger bị tắt.
if (auditLogger.isLoggable(java.util.logging.Level.INFO)) {
    grantRole();
    auditLogger.info("GRANT_ROLE SUCCEEDED");
}
```

Đây là **đoạn minh họa tích hợp**, không phải chương trình độc lập. Logic nghiệp vụ không được phụ thuộc level logging. Một hệ thống bắt buộc audit cần policy riêng khi audit service lỗi thay vì ẩn nghiệp vụ trong guard logging.

### Lỗi 9: Dùng cùng một requestId thay cho eventId

Một request có thể kích hoạt nhiều hành động; nếu tất cả dùng requestId làm eventId sẽ khó phân biệt. Có eventId duy nhất cho mỗi event và operationId chung cho chuỗi sự kiện liên quan.

### Lỗi 10: Tin rằng gọi logger đã chứng minh hành động

Log có thể được tạo sai thời điểm, bị filter/drop, hoặc không tới sink. Audit chỉ đáng tin khi event semantics, ranh giới transaction và đường lưu trữ phù hợp với mức bảo đảm cần thiết.

## 17. Checklist triển khai

- [ ] Mỗi thao tác được audit có action code rõ ràng, ổn định, có tài liệu ngữ nghĩa.
- [ ] Phân biệt **requested/attempted** với **performed/succeeded** và các trạng thái `DENIED`, `FAILED`, `PARTIAL`.
- [ ] Xác định chính xác success boundary: commit, delivery, settlement hoặc điểm hoàn thành khác.
- [ ] Gắn target type/ID, những thuộc tính thay đổi được phép, scope và version nếu cần.
- [ ] Lấy actor từ nguồn xác thực đáng tin, không lấy từ dữ liệu client tự khai.
- [ ] Gắn eventId, operationId/requestId, UTC timestamp để truy vết và dedup.
- [ ] Không ghi secret, PII dư thừa, raw payload hoặc chuỗi đầu vào không được escape.
- [ ] Đặt audit event gần ranh giới nghiệp vụ và dùng transaction/outbox khi cần nhất quán.
- [ ] Định nghĩa hành vi khi audit sink lỗi, queue đầy, retry, shutdown hoặc crash.
- [ ] Lưu trữ audit có phân quyền, retention, integrity và khả năng đối soát tương ứng mức rủi ro.
- [ ] Kiểm thử cả thành công, bị từ chối, rollback, async, bulk/partial, lỗi đích và trùng event.
- [ ] Truy vấn được một action theo target/outcome, không phải đoán qua message text.

**Kết luận:** Để trả lời chính xác **“thao tác nào đã xảy ra?”**, audit event phải ghi một **action có ngữ nghĩa nghiệp vụ ổn định**, **đối tượng**, **kết quả thực tế** và bằng chứng tương quan. “Có yêu cầu” khác “đã thực hiện”, “đã nhận job” khác “đã hoàn tất”, và “đã gọi logger” khác “đã lưu bằng chứng”. Đó là nền tảng để audit logging có giá trị trong điều tra, bảo mật và vận hành.
