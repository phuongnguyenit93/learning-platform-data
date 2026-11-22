# Phân biệt lịch sử nghiệp vụ với lịch sử sửa bản ghi

Một hệ thống có thể biết một bản ghi đang ở trạng thái nào nhưng vẫn không trả lời được hai câu hỏi quan trọng: **Điều gì đã xảy ra trong nghiệp vụ?** và **Ai đã thay đổi dữ liệu lưu trữ, thay đổi điều gì?** Hai câu hỏi này liên quan nhưng không giống nhau.

Trong Domain-Driven Design (DDD), lịch sử nghiệp vụ ghi lại những sự kiện có ý nghĩa đối với hoạt động của domain: đơn hàng được đặt, hợp đồng được gia hạn, địa chỉ giao hàng được thay đổi, khoản thanh toán được hoàn. Lịch sử sửa bản ghi (record modification history) ghi lại dấu vết thay đổi dữ liệu: người dùng hoặc tiến trình nào đã sửa trường nào, giá trị trước và sau là gì, thay đổi được ghi nhận lúc nào.

Một sự kiện nghiệp vụ có thể làm thay đổi nhiều bản ghi; một lần sửa bản ghi có thể chỉ là thao tác kỹ thuật và không tạo ra sự kiện nghiệp vụ. Thiết kế tốt cần xác định mục đích của từng loại lịch sử, dữ liệu cần lưu và cách truy vấn chúng.

Sau bài học, người học có thể:

- Phân biệt business history, audit trail, record history và change log.
- Xác định câu hỏi nghiệp vụ hoặc kiểm toán mà mỗi loại lịch sử cần trả lời.
- Mô hình hóa Domain Event và dấu vết thay đổi dữ liệu với cấu trúc phù hợp.
- Phân biệt thời điểm sự việc xảy ra, thời điểm sự việc có hiệu lực và thời điểm hệ thống ghi nhận.
- Hiểu valid time, transaction time và mô hình dữ liệu hai thời gian (bitemporal).
- Chọn cách lưu lịch sử trong bảng riêng, event log, temporal table hoặc cơ chế audit.
- Giữ lịch sử nhất quán với trạng thái hiện tại và bảo vệ dữ liệu nhạy cảm.

## 1. Hai câu hỏi khác nhau về quá khứ

Hãy xét một đơn hàng có địa chỉ giao hàng được thay đổi sau khi khách đã đặt.

Bộ phận chăm sóc khách hàng hỏi:

> Khách đã yêu cầu đổi địa chỉ giao hàng vào lúc nào? Yêu cầu đó được chấp nhận hay từ chối? Đơn hàng đã được chuyển đến địa chỉ nào theo quyết định cuối cùng?

Đây là câu hỏi về **lịch sử nghiệp vụ**. Cần biết yêu cầu, quyết định, tác nhân, lý do và kết quả có ý nghĩa trong quy trình.

Nhóm vận hành hoặc kiểm toán hỏi:

> Trường shipping_address trong bản ghi Order đã được sửa lúc nào? Tài khoản nào thực hiện? Giá trị cũ và giá trị mới là gì? Thay đổi đến từ giao diện, API hay một job tự động?

Đây là câu hỏi về **lịch sử sửa bản ghi**. Cần biết thao tác dữ liệu cụ thể, actor hoặc process, nguồn thay đổi và before/after.

Hai lịch sử có thể liên kết với nhau bằng command ID, correlation ID hoặc business event ID, nhưng chúng phục vụ hai mục đích khác nhau.

| Góc nhìn | Lịch sử nghiệp vụ (Business History) | Lịch sử sửa bản ghi (Record Modification History) |
|---|---|---|
| Câu hỏi chính | Điều gì đã xảy ra trong nghiệp vụ, vì sao và kết quả ra sao? | Dữ liệu nào đã bị thay đổi, ai/systems nào thay đổi và khi nào? |
| Đơn vị ghi nhận | Sự kiện hoặc quyết định nghiệp vụ | Thao tác tạo/sửa/xóa bản ghi hoặc field |
| Ngôn ngữ | Thuật ngữ của domain | Bảng, entity, field, operation, before/after |
| Ví dụ | OrderCancelled, ContractRenewed | Order.status: PLACED → CANCELLED |
| Tác nhân | Khách hàng yêu cầu, nhân viên phê duyệt, hệ thống xác nhận | User ID, service account, batch job, database process |
| Thời gian | Thời điểm xảy ra hoặc có hiệu lực trong nghiệp vụ | Thời điểm thay đổi được ghi vào hệ thống |
| Mục đích | Giải thích quy trình, quyết định, nghĩa vụ và kết quả | Điều tra thay đổi dữ liệu, kiểm soát truy cập, kiểm toán |
| Cách truy vấn | Timeline theo khách hàng, hợp đồng, đơn hàng hoặc quy trình | Tra cứu thay đổi theo entity, field, actor, thời gian |
| Chủ sở hữu | Domain/Bounded Context phát sinh sự kiện | Hạ tầng dữ liệu, ứng dụng hoặc hệ thống audit theo chính sách |

## 2. Lịch sử nghiệp vụ ghi lại điều có ý nghĩa với domain

### Business event không chỉ là một lần UPDATE

Giả sử một đơn hàng chuyển từ PLACED sang CANCELLED. Một câu lệnh SQL có thể cập nhật cột status. Nhưng nghiệp vụ có thể cần ghi nhận:

- Khách hàng yêu cầu hủy.
- Nhân viên xác minh đơn chưa được bàn giao cho đơn vị vận chuyển.
- Chính sách cho phép hủy.
- Đơn được hủy lúc một thời điểm cụ thể.
- Yêu cầu giữ hàng được giải phóng.
- Khoản thanh toán được yêu cầu hoàn lại.

Một UPDATE status không thể tự diễn đạt đầy đủ những sự việc này. Domain có thể phát sinh OrderCancellationRequested, OrderCancelled và RefundRequested ở những thời điểm khác nhau. Mỗi event có nghĩa riêng và có thể thuộc các aggregate hoặc context khác nhau.

### Business history trả lời được câu hỏi của chuyên gia nghiệp vụ

Một timeline nghiệp vụ có thể trình bày:

~~~text
10:02  OrderPlaced
       Khách đặt đơn ORD-1001.

10:05  PaymentAuthorized
       Khoản thanh toán được ngân hàng chấp thuận.

10:12  CancellationRequested
       Khách yêu cầu hủy vì chọn nhầm địa chỉ.

10:14  OrderCancelled
       Đơn được hủy trước khi bàn giao cho đơn vị vận chuyển.

10:15  StockReservationReleased
       Hàng đã giữ được giải phóng.

10:16  RefundRequested
       Yêu cầu hoàn tiền được gửi đến Payment Context.
~~~

Timeline này không nhất thiết tương ứng một bảng duy nhất. Nó có thể tổng hợp các sự kiện từ nhiều aggregate hoặc bounded context. Điều quan trọng là mỗi sự kiện có định danh, ngữ nghĩa và thời điểm rõ ràng.

### Business history có thể tồn tại mà không có thay đổi trên một bản ghi hiện tại

Ví dụ, một khách hàng gửi yêu cầu đổi lịch giao hàng nhưng yêu cầu bị từ chối vì hàng đã được bàn giao. Hệ thống vẫn cần ghi nhận yêu cầu và quyết định từ chối, dù địa chỉ hoặc lịch giao hàng hiện tại không đổi.

Ngược lại, một job chuẩn hóa chữ hoa/thường trong dữ liệu có thể sửa hàng nghìn bản ghi nhưng không tạo ra sự kiện nghiệp vụ riêng cho từng khách hàng. Đây là thay đổi dữ liệu cần audit theo chính sách, không nhất thiết là business event.

## 3. Lịch sử sửa bản ghi ghi lại dấu vết thay đổi dữ liệu

### Một record change thường có những thành phần nào?

Một bản ghi audit thường ghi:

- Loại đối tượng hoặc bảng bị thay đổi.
- Định danh bản ghi.
- Operation: INSERT, UPDATE hoặc DELETE.
- Thời điểm hệ thống ghi nhận thay đổi.
- Actor: user, service account hoặc job.
- Nguồn thay đổi: API, UI, import, migration hoặc batch.
- Các field thay đổi cùng giá trị trước và sau.
- Request ID, transaction ID hoặc correlation ID nếu có.

Ví dụ:

~~~json
{
  "auditId": "aud-91",
  "entityType": "Order",
  "entityId": "ORD-1001",
  "operation": "UPDATE",
  "changedAt": "2026-11-18T10:14:22Z",
  "actor": {
    "type": "USER",
    "id": "staff-72"
  },
  "source": "admin-portal",
  "changes": {
    "status": {
      "before": "PLACED",
      "after": "CANCELLED"
    },
    "cancelReasonCode": {
      "before": null,
      "after": "CUSTOMER_REQUEST"
    }
  },
  "correlationId": "req-42"
}
~~~

Đây là ví dụ về record audit. Nó mô tả dữ liệu đã được cập nhật, nhưng không giải thích toàn bộ chính sách nghiệp vụ khiến việc hủy được chấp nhận. Muốn trả lời câu hỏi đó, cần business event hoặc hồ sơ quyết định tương ứng.

### Audit log không phải là bản sao đầy đủ của bảng

Không nhất thiết lưu toàn bộ row trước và sau trong mọi lần cập nhật. Có thể lưu:

- Chỉ field thay đổi và before/after.
- Snapshot đầy đủ trước/sau khi có yêu cầu điều tra hoặc khôi phục.
- Một tập thuộc tính được chọn theo mức độ nhạy cảm và yêu cầu kiểm toán.

Lưu full row giúp khôi phục và so sánh dễ hơn nhưng tăng dung lượng, rủi ro lộ dữ liệu và chi phí quản trị. Lưu field diff tiết kiệm hơn nhưng cần schema và công cụ diễn giải ổn định.

### Không phải mọi thao tác dữ liệu đều là hành vi nghiệp vụ

Các thay đổi như:

- Sửa định dạng email do migration.
- Cập nhật cột cache hoặc search vector.
- Đổi trạng thái kỹ thuật của một job.
- Backfill một field mới.
- Sửa lỗi dữ liệu theo yêu cầu vận hành.

có thể cần record audit hoặc deployment log, nhưng không nhất thiết tạo Domain Event. Đừng đặt tên những thao tác kỹ thuật này thành các sự kiện nghiệp vụ chỉ để mọi thay đổi đều có một message.

## 4. Business History, Domain Event, Audit Log và Event Sourcing

Các khái niệm có liên hệ nhưng không thể thay thế tùy tiện.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Domain Event | Ghi nhận sự việc có ý nghĩa đã xảy ra trong một bounded context | OrderPlaced |
| Business History | Timeline hoặc hồ sơ các sự kiện/quyết định nghiệp vụ | Lịch sử đặt, hủy và hoàn tiền của đơn |
| Record Audit Trail | Ghi dấu thay đổi dữ liệu và actor | Field status đổi từ PLACED sang CANCELLED |
| Application/Technical Log | Chẩn đoán hoạt động kỹ thuật | Request timeout, SQL error |
| Event Sourcing | Dùng event stream làm nguồn dữ liệu chính để dựng trạng thái | Replay OrderPlaced, LineAdded, OrderCancelled |

### Domain Event và Business History

Domain Event là một biểu diễn có cấu trúc của sự kiện miền. Business History là góc nhìn hoặc hồ sơ lịch sử được xây dựng từ những sự kiện đó, có thể bổ sung thông tin về quyết định, actor và trạng thái quy trình.

Một domain event có thể được xử lý bởi nhiều consumer. Không phải mọi consumer đều cần toàn bộ timeline. Business History có thể là một read model được tổng hợp cho màn hình hỗ trợ hoặc kiểm toán nghiệp vụ.

### Audit Trail và Technical Log

Audit trail phải trả lời được ai đã thực hiện thay đổi nào và khi nào theo chính sách lưu trữ. Technical log chủ yếu giúp chẩn đoán lỗi và theo dõi vận hành. Log thông thường có thể bị rotate, sampling hoặc xóa theo retention ngắn; do đó không nên coi log ứng dụng là audit trail chính thức nếu chưa có bảo đảm về tính toàn vẹn và lưu giữ.

### Event Sourcing không phải điều kiện để có Business History

Có thể lưu trạng thái hiện tại trong bảng quan hệ, lưu Domain Event qua outbox và lưu lịch sử nghiệp vụ ở bảng riêng. Cách đó vẫn tạo được timeline mà không cần Event Sourcing.

Event Sourcing phù hợp khi event stream thực sự là nguồn dữ liệu chính, tổ chức cần tái dựng trạng thái từ chuỗi sự kiện và chấp nhận chi phí về versioning, replay, projection, snapshot và vận hành. Nếu chỉ cần biết ai sửa field nào, audit table thường phù hợp hơn.

## 5. Thời gian trong lịch sử: occurred, effective và recorded

Một trong những nguyên nhân khiến lịch sử khó hiểu là hệ thống dùng một cột timestamp cho nhiều ý nghĩa.

### Occurred time: sự việc xảy ra khi nào?

Occurred time là thời điểm sự kiện diễn ra theo cách định nghĩa của domain. Ví dụ, khách nhấn nút gửi yêu cầu hủy lúc 10:12:00.

### Effective time: sự việc có hiệu lực từ khi nào?

Effective time là thời điểm một sự thật hoặc quyết định bắt đầu có hiệu lực trong nghiệp vụ. Nó có thể khác thời điểm sự kiện được ghi nhận.

Ví dụ, một hợp đồng được gia hạn từ ngày 1/11 nhưng nhân viên nhập quyết định vào hệ thống ngày 3/11. Ngày 1/11 là effective date; ngày 3/11 là thời điểm hệ thống ghi nhận.

### Recorded time: hệ thống biết điều đó từ khi nào?

Recorded time là thời điểm thông tin được lưu vào hệ thống. Nó rất quan trọng khi cần giải thích hệ thống đã biết gì tại một thời điểm trong quá khứ.

Ví dụ:

| Thuộc tính | Giá trị |
|---|---|
| occurredAt | 2026-11-03T09:00:00Z |
| effectiveFrom | 2026-11-01T00:00:00Z |
| recordedAt | 2026-11-03T09:00:05Z |

Một timeline nghiệp vụ chỉ dựa vào recordedAt có thể khiến người xem nghĩ hợp đồng bắt đầu ngày 3/11. Nếu cần phản ánh thời điểm hiệu lực, phải lưu effectiveFrom riêng.

### Không nhầm thời điểm nghiệp vụ với thời điểm cập nhật database

updated_at thường chỉ cho biết row được cập nhật lần cuối. Nó không cho biết sự kiện nghiệp vụ có hiệu lực từ khi nào, ai yêu cầu thay đổi hay những lần thay đổi trước đó.

Một bản ghi có thể được cập nhật nhiều lần nhưng updated_at chỉ giữ lần cuối. Vì vậy, nó không phải lịch sử.

## 6. Valid Time và Transaction Time

Temporal data modeling thường phân biệt hai trục thời gian.

- **Valid Time**: khoảng thời gian một sự thật có hiệu lực trong thế giới nghiệp vụ.
- **Transaction Time**: khoảng thời gian hệ thống lưu giữ và xem sự thật đó là phiên bản đang được ghi nhận.

### Ví dụ thay đổi địa chỉ có hiệu lực hồi tố

Ngày 5/11, nhân viên nhận được xác nhận rằng địa chỉ khách hàng đã thay đổi từ ngày 1/11. Hệ thống chỉ được cập nhật vào ngày 5/11.

| Trục thời gian | Bắt đầu |
|---|---|
| Valid time | 2026-11-01 |
| Transaction time | 2026-11-05 |

Nếu chỉ lưu một timestamp, hệ thống không thể trả lời đồng thời:

- Ngày 2/11, địa chỉ có hiệu lực theo thông tin hiện nay là gì?
- Ngày 2/11, hệ thống lúc đó đang biết địa chỉ nào?

Câu đầu hỏi theo valid time. Câu sau hỏi theo transaction time.

### Bitemporal: lưu cả hai trục

Một mô hình bitemporal giữ cả valid-time range và transaction-time range:

~~~text
CustomerAddressHistory
+ customer_id
+ address
+ valid_from
+ valid_to
+ recorded_from
+ recorded_to
~~~

- valid_from/valid_to: khoảng thời gian địa chỉ có hiệu lực.
- recorded_from/recorded_to: khoảng thời gian hệ thống coi phiên bản này là thông tin được ghi nhận.

Ví dụ:

| Address | Valid From | Valid To | Recorded From | Recorded To |
|---|---|---|---|---|
| 12 A Street | 01/01 | vô hạn | 01/01 | 05/11 |
| 18 B Street | 01/11 | vô hạn | 05/11 | vô hạn |

Dòng thứ hai được ghi nhận vào ngày 5/11 nhưng có hiệu lực từ ngày 1/11. Dòng đầu phản ánh điều hệ thống đã ghi nhận trước ngày 5/11. Khi truy vấn “hệ thống đã biết gì ngày 2/11?”, chọn phiên bản có recorded range chứa ngày 2/11. Khi truy vấn “địa chỉ có hiệu lực ngày 2/11 theo hiểu biết hiện nay?”, chọn valid range chứa ngày 2/11 trong phiên bản hiện hành.

Bitemporal hữu ích cho hợp đồng, giá, chính sách, bảo hiểm, thuế, quyền lợi hoặc hồ sơ cần giải thích cả hiệu lực nghiệp vụ lẫn lịch sử ghi nhận. Nó làm schema và truy vấn phức tạp hơn; chỉ dùng khi hai câu hỏi thời gian thực sự cần thiết.

## 7. Thiết kế mô hình dữ liệu cho Business History

### Bảng sự kiện nghiệp vụ

Một bảng lịch sử nghiệp vụ có thể chứa:

~~~sql
CREATE TABLE business_event (
    event_id UUID PRIMARY KEY,
    subject_type VARCHAR(80) NOT NULL,
    subject_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    event_version INTEGER NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    effective_at TIMESTAMP WITH TIME ZONE,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actor_type VARCHAR(30),
    actor_id VARCHAR(120),
    reason_code VARCHAR(80),
    correlation_id UUID,
    causation_id UUID,
    payload JSONB NOT NULL
);

CREATE INDEX ix_business_event_subject_time
    ON business_event(subject_type, subject_id, occurred_at);
~~~

Đây là schema minh họa theo PostgreSQL. Một hệ thống có thể tách event store, outbox và business-history projection thành các bảng riêng. subject_id dùng chuỗi để minh họa nhiều loại ID; production nên xác định quy tắc định danh và kiểu dữ liệu phù hợp.

Các field có ý nghĩa:

- event_id: định danh duy nhất của sự kiện.
- subject_type/subject_id: đối tượng hoặc quy trình mà sự kiện liên quan.
- event_type/event_version: loại sự kiện và phiên bản schema.
- occurred_at: thời điểm sự việc xảy ra.
- effective_at: thời điểm có hiệu lực nếu khác occurred_at.
- recorded_at: thời điểm hệ thống ghi nhận.
- actor_type/actor_id: tác nhân nghiệp vụ hoặc hệ thống.
- reason_code: lý do có mã ổn định.
- correlation_id/causation_id: liên kết các bước trong quy trình.
- payload: dữ liệu cần thiết để giải thích sự kiện.

Không nên mặc định mọi event phải chứa toàn bộ before/after. Domain Event mô tả sự việc và dữ liệu nghiệp vụ cần thiết; chi tiết thay đổi field có thể thuộc audit trail riêng.

### Bảng lịch sử chuyển trạng thái

Với một entity có state machine đơn giản, có thể lưu lịch sử chuyển trạng thái:

~~~sql
CREATE TABLE order_status_history (
    history_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actor_id VARCHAR(120),
    reason_code VARCHAR(80),
    event_id UUID,
    sequence_no BIGINT NOT NULL,
    CONSTRAINT uq_order_status_sequence
        UNIQUE (order_id, sequence_no)
);
~~~

Bảng này tập trung vào trạng thái đơn hàng, có thể là projection của Domain Event hoặc được ghi cùng transaction với Order. Nếu event store đã là nguồn chính, không nên duy trì hai lịch sử độc lập mà không có quy tắc đồng bộ.

### Business History không nhất thiết là event store

Bảng business_event ở ví dụ có thể chỉ lưu các sự kiện cần hiển thị và truy vấn lịch sử. Nếu hệ thống không dùng Event Sourcing, trạng thái hiện tại vẫn có thể nằm ở bảng orders. Khi đó, cần xác định nguồn nào là nguồn đáng tin cậy và cách khôi phục nếu projection history bị lỗi.

## 8. Thiết kế Record Audit Trail

### Audit table cho thay đổi field

Một schema tổng quát có thể dùng JSONB để lưu diff:

~~~sql
CREATE TABLE record_audit (
    audit_id UUID PRIMARY KEY,
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(160) NOT NULL,
    operation VARCHAR(12) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actor_type VARCHAR(30) NOT NULL,
    actor_id VARCHAR(160),
    source VARCHAR(100),
    request_id UUID,
    transaction_id UUID,
    changes JSONB NOT NULL
);

CREATE INDEX ix_record_audit_entity_time
    ON record_audit(entity_type, entity_id, changed_at DESC);

CREATE INDEX ix_record_audit_actor_time
    ON record_audit(actor_id, changed_at DESC);
~~~

Ví dụ payload changes:

~~~json
{
  "status": {
    "before": "PLACED",
    "after": "CANCELLED"
  },
  "cancelReasonCode": {
    "before": null,
    "after": "CUSTOMER_REQUEST"
  }
}
~~~

Một record audit có thể được tạo bởi ứng dụng, ORM listener, database trigger hoặc CDC pipeline. Mỗi cách có trade-off:

| Cách thu thập | Ưu điểm | Hạn chế |
|---|---|---|
| Application-level audit | Biết actor, use case và ngữ cảnh request | Có thể bị bỏ qua bởi writer khác nếu không áp dụng thống nhất |
| ORM listener/callback | Tự động theo dõi entity được ORM quản lý | Bulk SQL hoặc writer ngoài ORM có thể không đi qua callback |
| Database trigger | Ghi nhận thay đổi ở DB bất kể ứng dụng nào ghi | Khó biết ý nghĩa nghiệp vụ; actor ứng dụng cần được truyền vào DB context |
| CDC | Đọc thay đổi từ transaction log, phù hợp pipeline | Dữ liệu kỹ thuật, phụ thuộc schema và cấu hình database |

Có thể kết hợp nhiều lớp, nhưng phải tránh ghi trùng hoặc tạo hai nguồn audit có semantics khác nhau.

### Ví dụ Java về audit diff

~~~java
public record FieldChange(
        String fieldName,
        Object before,
        Object after
) {}

public record RecordAuditEntry(
        UUID auditId,
        String entityType,
        String entityId,
        String operation,
        Instant changedAt,
        String actorId,
        String source,
        List<FieldChange> changes
) {
    public RecordAuditEntry {
        changes = List.copyOf(changes);
    }
}
~~~

Đây là DTO minh họa cho audit adapter, không phải Domain Entity. Trong triển khai thực tế, before/after cần được chuẩn hóa thành kiểu có thể serialize an toàn; tránh giữ object mutable hoặc ghi trực tiếp thông tin nhạy cảm.

## 9. Mô hình Domain Event trong Java

### Event mang ý nghĩa nghiệp vụ

Ví dụ, khi khách hàng yêu cầu đổi địa chỉ giao hàng và yêu cầu được chấp nhận:

~~~java
public record OrderDeliveryAddressChanged(
        UUID eventId,
        UUID orderId,
        AddressSnapshot previousAddress,
        AddressSnapshot newAddress,
        Instant occurredAt,
        Instant effectiveAt,
        UUID requestedBy,
        String reasonCode
) implements DomainEvent {
}
~~~

Sự kiện này trả lời điều gì đã xảy ra: địa chỉ giao hàng của đơn đã thay đổi. previousAddress và newAddress là snapshot tại thời điểm quyết định; requestedBy và reasonCode giúp giải thích tác nhân và lý do. Nếu địa chỉ chứa thông tin cá nhân, payload phải được tối thiểu hóa và bảo vệ theo chính sách.

Không phải mọi event đều cần cả previousAddress và newAddress. Có thể chỉ lưu address ID/version và tham chiếu tới hồ sơ được bảo vệ nếu yêu cầu lịch sử không cần snapshot đầy đủ.

### Aggregate bảo vệ hành vi, không phát event từ setter

~~~java
public final class Order {
    private final UUID id;
    private AddressSnapshot deliveryAddress;
    private OrderStatus status;
    private final List<DomainEvent> pendingEvents = new ArrayList<>();

    public void changeDeliveryAddress(
            AddressSnapshot newAddress,
            UUID actorId,
            Instant now,
            String reasonCode
    ) {
        if (status != OrderStatus.DRAFT && status != OrderStatus.PLACED) {
            throw new IllegalStateException("Address can no longer be changed");
        }

        Objects.requireNonNull(newAddress, "newAddress");
        AddressSnapshot previous = deliveryAddress;

        if (previous.equals(newAddress)) {
            return;
        }

        deliveryAddress = newAddress;
        pendingEvents.add(new OrderDeliveryAddressChanged(
                UUID.randomUUID(),
                id,
                previous,
                newAddress,
                now,
                now,
                actorId,
                reasonCode
        ));
    }

    public List<DomainEvent> pullDomainEvents() {
        List<DomainEvent> result = List.copyOf(pendingEvents);
        pendingEvents.clear();
        return result;
    }
}
~~~

Đây là ví dụ khái niệm. Constructor, null checks, value object và cách khôi phục aggregate được lược bớt. Thời điểm và actor được truyền từ application layer; aggregate không tự đọc đồng hồ hệ thống hoặc lấy user session. Event chỉ được tạo sau khi điều kiện thay đổi hợp lệ.

### Ghi event cùng transaction với trạng thái

Nếu Order đã đổi địa chỉ nhưng việc lưu event thất bại, business history có thể thiếu sự kiện. Nếu event được gửi ra broker trước khi transaction commit rồi transaction rollback, consumer có thể thấy một thay đổi chưa xảy ra.

Transactional Outbox giải quyết khoảng hở này:

~~~text
Application Service
       |
       v
BEGIN TRANSACTION
  - Save Order state
  - Insert Outbox event
COMMIT
       |
       v
Outbox Relay
       |
       v
Message Broker
       |
       v
Business History / Other Context
~~~

Outbox record được ghi trong cùng transaction với aggregate. Relay gửi sau commit và có thể retry. Consumer cần idempotency vì message có thể được giao lại. Nếu business history nằm trong cùng database và cần đồng bộ tức thì, có thể ghi projection trong transaction; nếu nằm ở context riêng, event/outbox thường phù hợp hơn.

## 10. Quan hệ giữa trạng thái hiện tại và lịch sử

Một mô hình thường có hai phần:

- **Current state**: trạng thái hiện tại để xử lý use case nhanh.
- **History**: dấu vết các sự kiện hoặc phiên bản trước đó để giải thích quá trình.

Ví dụ:

~~~text
orders
+ order_id
+ status = CANCELLED
+ updated_at = 10:14

order_status_history
+ PLACED -> CANCELLED
+ occurred_at = 10:14
+ reason = CUSTOMER_REQUEST

record_audit
+ orders.status
+ before = PLACED
+ after = CANCELLED
+ actor = staff-72
+ changed_at = 10:14:22
~~~

Ba dòng trên có thể cùng nói về một lần hủy, nhưng mỗi phần trả lời một câu hỏi khác nhau:

- orders cho biết trạng thái hiện tại.
- order_status_history cho biết chuyển đổi nghiệp vụ.
- record_audit cho biết thay đổi lưu trữ và actor thực hiện.

Không phải dự án nào cũng cần cả ba bảng. Nếu business history và record audit có thể dùng chung một sự kiện với đủ thông tin và chính sách truy cập phù hợp, có thể xây một nguồn ghi nhận rồi tạo projection riêng. Nhưng đừng gộp chỉ để giảm số bảng nếu hai mục đích có yêu cầu retention, bảo mật hoặc ngữ nghĩa khác nhau.

## 11. Sửa sai lịch sử: không viết lại sự thật đã xảy ra

Một quy tắc quan trọng là phân biệt **sự kiện đã xảy ra** với **thông tin được ghi nhận là sai**.

Ví dụ, ngày 3/11 nhân viên nhập nhầm ngày hiệu lực hợp đồng là 1/11 thay vì 2/11. Ngày 5/11 phát hiện sai sót. Không nên sửa im lặng event cũ để mọi dấu vết biến mất nếu lịch sử cần phục vụ kiểm toán.

Có thể ghi một sự kiện hiệu chỉnh:

~~~text
ContractRenewalRecorded
    effectiveAt = 2026-11-01

ContractEffectiveDateCorrected
    previousEffectiveAt = 2026-11-01
    correctedEffectiveAt = 2026-11-02
    recordedAt = 2026-11-05
    reason = DATA_ENTRY_ERROR
~~~

Sự kiện thứ hai giải thích rằng dữ liệu trước đó đã được hiệu chỉnh. Hệ thống có thể dựng trạng thái hiện hành theo quy tắc correction, đồng thời vẫn giải thích được điều gì đã được ghi nhận trước khi phát hiện sai.

Không phải mọi dữ liệu đều cần event correction công khai. Một số audit field có thể được sửa theo quy trình kiểm soát riêng. Nhưng với lịch sử nghiệp vụ có giá trị chứng cứ, việc sửa phải có lý do, actor, thời điểm và liên kết tới bản ghi bị sửa.

### Correction khác với compensation

- **Correction** sửa lại một thông tin đã ghi sai, ví dụ ngày hiệu lực bị nhập nhầm.
- **Compensation** tạo hành động nghiệp vụ mới để bù cho một hành động đã xảy ra, ví dụ phát lệnh hoàn tiền sau khi đã thu tiền.

Không nên dùng correction để che giấu một giao dịch đã thực sự xảy ra. Nếu thanh toán đã được thu rồi hoàn lại, lịch sử cần thể hiện cả PaymentCaptured và RefundIssued.

## 12. Khi nào cần Temporal Table hoặc Bitemporal Table?

### Temporal table

Temporal table lưu các phiên bản dữ liệu theo thời gian. Một số hệ quản trị có hỗ trợ system-versioned temporal table; hệ khác có thể triển khai bằng bảng history và trigger/application logic.

Temporal table hữu ích khi cần trả lời “bản ghi này có giá trị gì tại thời điểm T theo dữ liệu hệ thống lưu?”. Nó tập trung vào phiên bản row, không tự giải thích ý nghĩa nghiệp vụ của sự thay đổi.

### Bitemporal table

Bitemporal cần khi hệ thống phải trả lời cả:

1. Sự thật có hiệu lực trong nghiệp vụ vào khoảng thời gian nào?
2. Hệ thống đã ghi nhận phiên bản sự thật đó vào khoảng thời gian nào?

Ví dụ bảng địa chỉ:

~~~sql
CREATE TABLE customer_address_bitemporal (
    version_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    address_text TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    recorded_from TIMESTAMP WITH TIME ZONE NOT NULL,
    recorded_to TIMESTAMP WITH TIME ZONE,
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (recorded_to IS NULL OR recorded_from < recorded_to)
);
~~~

Các khoảng thời gian trong ví dụ dùng quy ước nửa mở [from, to): thời điểm bắt đầu được tính, thời điểm kết thúc không được tính. Quy ước này giúp hai phiên bản liền nhau không chồng lấn ở biên.

Truy vấn địa chỉ có hiệu lực vào ngày nghiệp vụ D theo hiểu biết được ghi nhận tại thời điểm hệ thống T có thể lọc cả hai trục:

~~~sql
SELECT address_text
FROM customer_address_bitemporal
WHERE customer_id = :customer_id
  AND valid_from <= :business_date
  AND (valid_to IS NULL OR :business_date < valid_to)
  AND recorded_from <= :known_at
  AND (recorded_to IS NULL OR :known_at < recorded_to);
~~~

Schema tối thiểu ở trên chưa tự ngăn các khoảng thời gian chồng lấn. Production cần constraint exclusion, khóa hoặc transaction/logic phù hợp với database và quy tắc nghiệp vụ. Cũng cần xác định cách xử lý timezone, precision và dữ liệu hồi tố.

Không dùng bitemporal chỉ vì có hai cột timestamp. Hai trục phải có semantics rõ và có use case truy vấn thực tế.

## 13. Bảo mật, riêng tư và retention của lịch sử

Lịch sử có thể chứa nhiều thông tin nhạy cảm hơn bản ghi hiện tại vì nó giữ các giá trị cũ đã bị thay thế. Ví dụ, audit diff của email, địa chỉ, số điện thoại hoặc giấy tờ có thể làm tăng phạm vi dữ liệu cá nhân được lưu.

Cần xác định:

- Mục đích cụ thể của việc lưu lịch sử.
- Trường nào thực sự cần ghi before/after.
- Ai được xem timeline nghiệp vụ và ai được xem audit chi tiết.
- Dữ liệu nhạy cảm có cần mã hóa, tokenization hoặc masking không.
- Thời hạn lưu theo loại dữ liệu và nghĩa vụ áp dụng.
- Cách xử lý yêu cầu xóa, ẩn danh hóa hoặc hạn chế truy cập.
- Backup, replica, export và log có chứa bản sao lịch sử hay không.

Không nên ghi password, access token, secret, thông tin thẻ thanh toán đầy đủ hoặc payload nhạy cảm vào audit log. Với thông tin cần giữ để giải thích giao dịch, cân nhắc lưu snapshot tối thiểu hoặc tham chiếu đến vùng dữ liệu được bảo vệ.

Audit trail có thể cần kiểm soát chống sửa/xóa trái phép, ví dụ quyền ghi append-only, phân quyền tách biệt, checksum hoặc lưu trữ bất biến. Nhưng append-only không tự đảm bảo mọi thông tin được ghi là đúng; cần xác thực actor và nguồn phát sinh.

## 14. Chọn cách thu thập lịch sử theo mục tiêu

| Nhu cầu | Cách thường phù hợp | Điều cần xác minh |
|---|---|---|
| Timeline sự kiện nghiệp vụ | Domain Event + business history projection | Event có semantics rõ, có ID và thứ tự |
| Theo dõi ai sửa field nào | Audit table hoặc DB audit | Bao phủ mọi writer, actor context và retention |
| Xem row ở phiên bản trước | Temporal/history table | Khả năng truy vấn theo thời điểm và chi phí lưu |
| Xem sự thật có hiệu lực hồi tố và điều hệ thống từng biết | Bitemporal model | Valid time và transaction time được định nghĩa |
| Tái dựng toàn bộ aggregate từ sự kiện | Event Sourcing | Event stream là nguồn chính, có replay/versioning |
| Điều tra lỗi request | Structured application log và trace | Correlation ID, retention và quyền truy cập |

Không có một cơ chế duy nhất đáp ứng mọi mục đích. Hãy chọn theo câu hỏi cần trả lời, mức tin cậy, phạm vi writer, khả năng truy vấn và chính sách lưu giữ.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Coi updated_at là lịch sử | Chỉ biết lần cập nhật cuối, mất các lần trước | Lưu history/audit hoặc temporal versions |
| Coi mọi UPDATE là Domain Event | Timeline đầy thao tác kỹ thuật, thiếu ngữ nghĩa | Chỉ tạo event cho sự việc nghiệp vụ |
| Dùng Domain Event làm audit field diff duy nhất | Thiếu before/after hoặc actor kỹ thuật cần thiết | Bổ sung audit trail theo mục đích |
| Dùng application log làm audit chính thức | Log có thể rotate, sampling hoặc thiếu tính toàn vẹn | Dùng kho audit có retention và quyền truy cập rõ |
| Chỉ lưu occurredAt | Không giải thích được dữ liệu có hiệu lực hồi tố hoặc được ghi nhận muộn | Phân biệt occurred/effective/recorded time |
| Sửa event cũ để che lỗi | Mất dấu lịch sử và khả năng giải thích | Ghi correction/reversal event theo chính sách |
| Dùng Event Sourcing chỉ để lưu lịch sử | Tăng độ phức tạp không cần thiết | Cân nhắc bảng business history hoặc audit |
| Lưu toàn bộ row trong mọi audit entry | Dung lượng và rủi ro dữ liệu nhạy cảm tăng | Lưu field diff hoặc snapshot tối thiểu |
| Không liên kết business event và record audit | Khó truy vết từ quyết định đến thay đổi dữ liệu | Dùng correlation/causation ID hoặc event reference |
| Dùng một bảng history cho mọi loại dữ liệu | Khó áp dụng semantics, retention và quyền truy cập khác nhau | Phân loại mục đích trước khi chọn schema |
| Cho phép sửa/xóa audit không kiểm soát | Mất độ tin cậy của dấu vết | Append-only hoặc kiểm soát đặc quyền và giám sát |

## 16. Quy trình thiết kế lịch sử cho một Aggregate

1. **Xác định câu hỏi cần trả lời:** chuyên gia cần xem sự kiện nào, kiểm toán cần truy vết thay đổi nào?
2. **Phân loại dữ liệu:** business event, state transition, record audit, technical log hay temporal fact.
3. **Xác định owner:** bounded context nào phát sinh sự kiện và hệ thống nào chịu trách nhiệm audit row?
4. **Định nghĩa thời gian:** occurredAt, effectiveAt, recordedAt; có cần valid time/transaction time không?
5. **Chọn payload:** chỉ lưu dữ liệu cần để giải thích sự kiện, snapshot hoặc field diff.
6. **Thiết kế liên kết:** event ID, aggregate ID, request ID, correlation ID và causation ID.
7. **Chọn transaction boundary:** lịch sử nào phải commit cùng trạng thái hiện tại; lịch sử nào được xử lý qua outbox?
8. **Xác định truy vấn:** timeline theo aggregate, audit theo field/actor, hoặc truy vấn theo thời điểm.
9. **Đặt retention và access policy:** ai được xem, lưu bao lâu, masking/erasure ra sao?
10. **Kiểm thử:** thay đổi hợp lệ, rollback, retry, correction, event lặp và truy vấn quá khứ.

## 17. Checklist rà soát

- [ ] Đã xác định business history và record modification history phục vụ những câu hỏi khác nhau.
- [ ] Domain Event có tên và ngữ nghĩa nghiệp vụ rõ ràng.
- [ ] Audit entry ghi actor, source, operation, thời điểm và thay đổi cần thiết.
- [ ] Không coi updated_at hoặc technical log là lịch sử đầy đủ.
- [ ] Đã phân biệt occurred time, effective time và recorded time.
- [ ] Đã xác định có cần valid time, transaction time hay bitemporal không.
- [ ] Current state và history được ghi nhất quán theo transaction boundary.
- [ ] Correction và compensation được phân biệt.
- [ ] Có correlation/causation ID để truy vết giữa các bước.
- [ ] Không lưu dư thừa dữ liệu nhạy cảm trong event hoặc audit payload.
- [ ] Quyền truy cập, retention, masking và xóa/ẩn danh hóa được xác định.
- [ ] Audit trail có biện pháp bảo vệ khỏi sửa/xóa trái phép.
- [ ] Có cách đối soát history với trạng thái hiện tại.
- [ ] Cơ chế lưu lịch sử được chọn theo nhu cầu, không mặc định dùng Event Sourcing.

## Kết luận

Lịch sử nghiệp vụ và lịch sử sửa bản ghi nhìn vào quá khứ từ hai góc độ khác nhau. Business History giải thích những sự việc, quyết định và kết quả có ý nghĩa trong domain; Record Modification History giải thích dữ liệu đã được thay đổi ra sao, bởi ai và vào thời điểm nào. Domain Event, audit trail, temporal table và Event Sourcing có thể phối hợp nhưng không thay thế nhau. Khi phân biệt rõ occurred time, effective time và recorded time, chọn payload tối thiểu, liên kết sự kiện với thay đổi dữ liệu và quản lý retention phù hợp, hệ thống có thể vừa giải thích được hành trình nghiệp vụ vừa truy vết được độ tin cậy của dữ liệu.

