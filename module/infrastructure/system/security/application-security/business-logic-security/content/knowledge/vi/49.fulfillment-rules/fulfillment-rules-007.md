# Dấu vết kiểm toán quá trình thực hiện đơn hàng (Fulfillment audit trail)

## 1. Audit trail cần trả lời được điều gì?

Trong chương **Fulfillment Rules**, audit trail là chuỗi bản ghi giúp giải thích quá trình một đơn hàng được xuất kho, giao hàng hoặc cấp quyền lợi. Khi phát hiện giao trùng, bỏ qua phê duyệt hay xuất hàng sai quyền, hệ thống cần trả lời được:

- Ai hoặc dịch vụ nào đã yêu cầu và thực hiện hành động?
- Hành động áp dụng cho đúng đơn, dòng hàng, số lượng và kho nào?
- Quyền và điều kiện nghiệp vụ nào đã được kiểm tra?
- Dữ liệu đang ở phiên bản nào khi quyết định được chấp nhận?
- Transaction nào đã commit và tác vụ nào đã được gửi ra ngoài?
- Kho hoặc đơn vị vận chuyển đã báo điều gì, qua nguồn bằng chứng nào?
- Một bản ghi là lần thực hiện mới, retry của lệnh cũ hay thông báo lặp?
- Có dấu hiệu mất, sửa, xóa hoặc truy cập trái phép lịch sử không?

Một dòng log “order shipped” thường không đủ. Nó không cho biết ai gửi lệnh, số lượng được phép xuất, phê duyệt còn hiệu lực hay thông tin “đã giao” chỉ là một callback chưa được xác minh.

Audit không thay thế cơ chế ngăn chặn. Hệ thống vẫn phải thực thi state machine, quyền theo đối tượng, transaction và idempotency. Vai trò của audit là lưu bằng chứng về những quyết định và sự kiện có liên quan, để có thể kiểm tra lại và phát hiện lạm dụng.

## 2. Phân biệt ý định, quyết định và tác động

### 2.1. Không gộp mọi thứ thành “thành công”

Xét luồng thực hiện một đơn hàng:

```text
Người dùng gửi yêu cầu
    -> hệ thống kiểm tra quyền và eligibility
    -> transaction chấp nhận fulfillment
    -> worker gửi lệnh cho kho
    -> kho tiếp nhận tác vụ
    -> hàng được bàn giao
    -> xác nhận giao đến khách
```

Mỗi bước chứng minh một sự thật khác nhau.

| Bản ghi | Điều đã biết | Điều chưa thể kết luận |
| --- | --- | --- |
| `RELEASE_ATTEMPT_RECEIVED` | Hệ thống nhận một lần thử gọi lệnh | Người gọi có quyền hoặc đơn đủ điều kiện |
| `RELEASE_REJECTED` | Lệnh bị từ chối với mã lý do | Đã có thay đổi nghiệp vụ thành công |
| `FULFILLMENT_ACCEPTED` | Transaction đã chấp nhận tác vụ và claim tài nguyên theo thiết kế | Hàng đã rời kho |
| `DISPATCH_SEND_ATTEMPTED` | Worker đã thử gửi lệnh | Bên kho đã nhận hoặc thực hiện |
| `WAREHOUSE_ACCEPTED` | Có xác nhận tiếp nhận hợp lệ từ kho | Đã bàn giao cho vận chuyển |
| `HANDOVER_CONFIRMED` | Có bằng chứng bàn giao đáp ứng chính sách | Khách đã nhận hàng |
| `DELIVERY_CONFIRMED` | Có bằng chứng giao hàng theo quy ước của tích hợp | Mọi tranh chấp về việc nhận hàng đã được giải quyết |

Tên sự kiện phải phản ánh mức bằng chứng. Không ghi `SHIPPED` chỉ vì đã tạo nhãn vận chuyển. Không ghi `FULFILLMENT_SUCCEEDED` trước khi transaction được quyết định, rồi để bản ghi đó sống độc lập sau rollback.

### 2.2. Phân biệt quan sát và sự thật nghiệp vụ được công nhận

Một callback có thể báo “đã bàn giao”, nhưng hệ thống còn phải kiểm tra:

- Nguồn phát và tính toàn vẹn thông điệp.
- Tài khoản tích hợp và phạm vi tenant.
- Mã tác vụ, vận đơn, đơn hàng và số lượng liên quan.
- Sự kiện trùng, đến trễ hoặc mâu thuẫn với lịch sử.
- Điều kiện cho phép cập nhật trạng thái.

Nên phân biệt “đã nhận thông báo” với “đã công nhận sự kiện nghiệp vụ”. Callback bị từ chối vẫn có thể cần lưu dấu vết an toàn, nhưng không được trở thành bằng chứng rằng hàng đã xuất.

Ngay cả một thông báo đã xác thực cũng chứng minh rằng nguồn tích hợp báo một sự việc, chứ không tự loại bỏ khả năng hệ thống nguồn hoặc người thao tác ở kho ghi sai. Audit cần giữ được xuất xứ và giới hạn của bằng chứng.

## 3. Audit trail, application log, outbox và event sourcing

| Thành phần | Mục đích chính | Lưu ý bảo mật nghiệp vụ |
| --- | --- | --- |
| Application log | Chẩn đoán lỗi, hiệu năng và hoạt động kỹ thuật | Có thể thiếu cấu trúc nghiệp vụ hoặc bị xoay vòng sớm |
| Security attempt log | Ghi nhận các lần thử, từ chối, giả mạo hoặc bất thường | Cần tồn tại độc lập với rollback của thao tác bị từ chối |
| Business audit trail | Lưu quyết định và chuyển đổi nghiệp vụ có thể giải thích | Cần gắn với tài nguyên, người thực hiện, phiên bản và bằng chứng |
| Transactional outbox | Lưu ý định phát sự kiện/lệnh cùng transaction cục bộ | Việc phát có thể lặp; không tự chứng minh tác động bên ngoài |
| Event sourcing | Dùng chuỗi sự kiện làm nguồn trạng thái theo thiết kế hệ thống | Audit thông thường không mặc nhiên là nguồn đầy đủ để replay |

Các thành phần có thể chia sẻ định danh để liên kết, nhưng không nên coi chúng là cùng một thứ.

Ví dụ, trường `published=true` của outbox chỉ phản ánh trạng thái phát theo quy ước của publisher. Nó không chứng minh kho đã xuất hàng. Một audit trail cũng có thể chỉ lưu phần dữ liệu cần giải thích quyết định, nên không đủ để khôi phục mọi trạng thái bằng replay.

Không cần biến toàn hệ thống thành event sourcing để có audit trail tốt. Cần xác định rõ sự thật nào được lưu, nguồn nào có thẩm quyền và cách chứng minh sự thật đó đã commit.

## 4. Xác định những invariant cần kiểm chứng bằng audit

Audit nên được thiết kế từ các quy tắc cần bảo vệ, thay vì thêm vài trường log sau khi hoàn thành API.

Ví dụ invariant của fulfillment:

1. Chỉ người hoặc dịch vụ được cấp quyền trên đúng đơn và kho mới được chấp nhận yêu cầu thực hiện.
2. Đơn bị hủy, chưa thanh toán đủ theo chính sách hoặc chưa được duyệt không được tạo tác vụ thực hiện mới.
3. Số lượng được claim không vượt nghĩa vụ còn lại của từng dòng hàng.
4. Một tác vụ có định danh ổn định; retry không tạo thêm tác vụ nghiệp vụ tương đương ngoài phạm vi cho phép.
5. Chấp nhận fulfillment phải đi cùng claim, chuyển trạng thái và outbox tương ứng trong cùng ranh giới nhất quán cục bộ.
6. Không công nhận bàn giao nếu chưa có bằng chứng phù hợp với đúng tác vụ.
7. Giao bù, thu hồi hoặc sửa sai phải được ghi nhận bằng hành động riêng, không xóa lịch sử ban đầu.

Từ đó suy ra bằng chứng cần giữ:

| Invariant | Bằng chứng cần có |
| --- | --- |
| Đúng quyền đối tượng | Principal đã xác thực, tenant, phạm vi kho, tham chiếu policy/quyết định quyền |
| Đủ điều kiện nghiệp vụ | Phiên bản đơn, phê duyệt, chứng cứ thanh toán, hold và policy áp dụng |
| Không vượt số lượng | Dòng hàng, số lượng được claim, claimId và phiên bản liên quan |
| Không tạo tác vụ trùng | commandId, fulfillmentRequestId, liên kết idempotency và kết quả đã chấp nhận |
| Chuyển trạng thái hợp lệ | Trạng thái trước/sau và phiên bản aggregate |
| Tác động bên ngoài có nguồn | Hệ thống nguồn, tài khoản tích hợp, mã sự kiện và tham chiếu bằng chứng đã xác minh |

Không nhất thiết sao chép toàn bộ dữ liệu nguồn vào audit. Có thể giữ snapshot tối thiểu và tham chiếu đến bằng chứng có phiên bản, miễn là chúng còn tra cứu được trong thời gian cần điều tra.

Nếu tham chiếu chỉ trỏ đến một hàng luôn bị cập nhật đè, nhiều tháng sau nó có thể không còn giải thích được quyết định ban đầu.

## 5. Thiết kế định danh để lần theo chuỗi nguyên nhân

### 5.1. Mỗi loại định danh có một vai trò

| Định danh | Ý nghĩa |
| --- | --- |
| `attemptId` | Một lần nhận request hoặc thử xử lý |
| `commandId` | Một lệnh nghiệp vụ đã được nhận diện |
| `fulfillmentRequestId` | Tác vụ thực hiện được hệ thống chấp nhận |
| `eventId` | Một bản ghi sự kiện/audit cụ thể |
| `causationId` | Sự kiện hoặc lệnh trực tiếp gây ra bản ghi hiện tại |
| `correlationId` | Nhóm các bản ghi thuộc cùng một luồng cần theo dõi |
| `aggregateVersion` | Thứ tự thay đổi đã commit trong một aggregate được quản lý |
| `sourceEventId` | Định danh sự kiện do hệ thống ngoài cung cấp |

Một client timeout và gọi lại có thể tạo hai `attemptId`, nhưng cả hai phải liên kết về cùng `commandId` và `fulfillmentRequestId` nếu đây là retry cùng lệnh đã được chấp nhận.

Không dùng `correlationId` làm bằng chứng có quyền truy cập tài nguyên. Nó chỉ là dữ liệu liên kết; giá trị do bên ngoài gửi cần được kiểm tra định dạng, giới hạn kích thước và xử lý như đầu vào không đáng tin cậy.

### 5.2. Ví dụ chuỗi liên kết

```text
attempt-a1
    -> command-c7
    -> fulfillment-f9
    -> audit-event-e1: FULFILLMENT_ACCEPTED, version 1
    -> outbox-event-o2: RequestWarehouseFulfillment
    -> send-attempt-s1: timeout
    -> send-attempt-s2: retry cùng fulfillment-f9
    -> provider-event-p8: kho xác nhận tiếp nhận
    -> audit-event-e2: WAREHOUSE_ACCEPTED, version 2
```

Hai lần gửi không có nghĩa là hai lần thực hiện. Nếu kho trả hai mã tác vụ độc lập cho cùng `fulfillment-f9`, đây là mâu thuẫn cần đối soát, không phải lý do tạo thêm một fulfillment mới.

### 5.3. Ghi rõ người khởi tạo và người thực thi

Với thao tác qua nhiều dịch vụ, cần phân biệt:

```text
initiatedBy = nhân viên đã yêu cầu xuất
executedBy = dịch vụ fulfillment
sourceSystem = hệ thống kho khi xác nhận tiếp nhận
```

Danh tính thực thi lấy từ cơ chế xác thực của máy chủ hoặc danh tính dịch vụ đã kiểm chứng. Thông tin người khởi tạo được truyền qua các hop phải được bảo vệ bằng cơ chế ủy quyền/ngữ cảnh đáng tin cậy, không lấy từ một header tùy ý rồi coi là sự thật.

Khi có thao tác thay mặt người khác, lưu chuỗi ủy quyền phù hợp: ai ủy quyền, ai thực hiện, phạm vi nào. Chỉ ghi “system” cho mọi bước sẽ làm mất khả năng phân biệt tự động hóa hợp lệ với lạm dụng đặc quyền.

## 6. Mô hình dữ liệu audit có cấu trúc

### 6.1. Những trường cốt lõi

Một bản ghi về thay đổi nghiệp vụ đã commit thường cần:

```text
identity:
    eventId, tenantId, orderId, fulfillmentRequestId

causality:
    commandId, causationId, correlationId

transition:
    eventType, fromState, toState, aggregateVersion

actor:
    actorId, actorType, initiatedBy, producerService

decision:
    reasonCode, policyVersion, businessRevision
    snapshot tối thiểu hoặc tham chiếu bằng chứng có phiên bản

external evidence:
    sourceSystem, sourceEventId, evidenceRef

time:
    occurredAt, recordedAt
```

Với sự kiện chấp nhận fulfillment, snapshot có thể gồm dòng hàng và số lượng đã claim, kho, tham chiếu reservation, bằng chứng thanh toán và phê duyệt. Không lưu token hoặc thông tin thẻ để chứng minh đã trả tiền.

Không cần lưu mọi trường cho mọi loại sự kiện, nhưng hợp đồng từng loại phải rõ. `FULFILLMENT_ACCEPTED` thiếu số lượng hoặc phiên bản policy có thể không đủ để giải thích quyết định; một sự kiện xác nhận bàn giao lại cần tham chiếu bằng chứng từ kho/vận chuyển.

### 6.2. Schema minh họa

Schema sau dùng cú pháp PostgreSQL để minh họa **các thay đổi đã commit của aggregate fulfillment**. Nó không phải migration đầy đủ cho toàn hệ thống và không dùng để trộn mọi lần thử request vào cùng chuỗi phiên bản.

```sql
CREATE TABLE fulfillment_audit (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    fulfillment_request_id UUID NOT NULL,
    order_id UUID NOT NULL,

    aggregate_version BIGINT NOT NULL
        CHECK (aggregate_version > 0),

    command_id UUID NOT NULL,
    causation_id UUID,
    correlation_id VARCHAR(128),

    event_type VARCHAR(80) NOT NULL,
    from_state VARCHAR(40),
    to_state VARCHAR(40) NOT NULL,

    actor_id VARCHAR(128) NOT NULL,
    actor_type VARCHAR(32) NOT NULL,
    initiated_by VARCHAR(128),
    producer_service VARCHAR(100) NOT NULL,

    reason_code VARCHAR(80) NOT NULL,
    policy_version VARCHAR(80),
    business_snapshot JSONB NOT NULL,

    source_system VARCHAR(100),
    source_event_id VARCHAR(160),
    evidence_ref VARCHAR(240),

    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        tenant_id,
        fulfillment_request_id,
        aggregate_version
    )
);

CREATE INDEX fulfillment_audit_order_lookup
ON fulfillment_audit (
    tenant_id,
    order_id,
    recorded_at,
    event_id
);
```

Hợp đồng đi kèm:

- Mỗi thay đổi trạng thái trong aggregate này tăng phiên bản và có đúng một sự kiện audit tương ứng.
- Retry không tạo một thay đổi trạng thái mới chỉ để ghi rằng có retry; lần thử được ghi ở luồng attempt phù hợp.
- Sự kiện đầu tiên có thể có `from_state = NULL` khi tạo tác vụ.
- Những thay đổi khác của đơn hàng thuộc aggregate order cần chuỗi phiên bản riêng, không dùng lẫn với phiên bản fulfillment.
- Nếu có khóa ngoại, chính sách xóa không được vô tình cascade xóa audit khi xóa đơn hoặc tác vụ.
- Trạng thái xuất bản, checkpoint và số lần gửi được quản lý ngoài bản ghi audit bất biến.
- Các snapshot cần schema/version và kiểm tra nội dung, không trở thành nơi chứa tùy ý toàn bộ request.

Ràng buộc duy nhất giúp phát hiện hai sự kiện cùng nhận một phiên bản. Nó không tự chứng minh rằng không thiếu một sự kiện, rằng người gọi có quyền hay rằng dữ liệu trong snapshot là đúng.

### 6.3. Không lấy trạng thái hiện tại thay cho bằng chứng lúc quyết định

Ví dụ, audit chỉ lưu:

```json
{
  "eventType": "FULFILLMENT_ACCEPTED",
  "orderId": "order-42",
  "paymentRef": "payment-8"
}
```

Nếu bản ghi `payment-8` bị cập nhật sau đó, người điều tra không biết tại thời điểm release khoản thu đã ở trạng thái nào.

Bằng chứng cần giữ được phiên bản hoặc snapshot tối thiểu, chẳng hạn:

```json
{
  "orderBusinessRevision": 12,
  "lines": [
    {
      "lineId": "line-3",
      "quantity": 2,
      "claimId": "claim-71"
    }
  ],
  "warehouseId": "warehouse-a",
  "paymentEvidenceRef": "payment-evidence-8-v4",
  "approvalRef": "approval-19",
  "reservationEvidenceRef": "reservation-27-v6",
  "policyVersion": "fulfillment-policy-7"
}
```

Ví dụ này là dữ liệu audit, không phải payload được phép gửi vào API để chứng minh eligibility. Máy chủ tự xây snapshot từ dữ liệu có thẩm quyền.

## 7. Ghi audit thành công trong cùng transaction

### 7.1. Vấn đề dual write

Thiết kế sau có khoảng trống:

```text
1. Commit chấp nhận fulfillment.
2. Gọi dịch vụ audit từ xa.
3. Dịch vụ audit lỗi hoặc tiến trình chết.
```

Kết quả là tài sản có thể được thực hiện nhưng không có bằng chứng quyết định ở nơi mong đợi.

Đảo thứ tự cũng không giải quyết được:

```text
1. Ghi audit từ xa rằng đã chấp nhận.
2. Transaction nghiệp vụ rollback.
```

Lần này lịch sử tuyên bố thành công dù tác vụ không được chấp nhận.

Với dữ liệu nằm trong cùng cơ sở dữ liệu, một ranh giới phù hợp là:

```text
BEGIN
    kiểm tra quyền và invariant trên dữ liệu được bảo vệ
    tạo fulfillment request
    claim số lượng và allocation tương ứng
    chuyển trạng thái đơn/tác vụ
    ghi business audit
    ghi outbox
COMMIT
```

Nếu audit bắt buộc không ghi được, transaction không được chấp nhận tác vụ. Nếu commit thành công, audit cục bộ đã tồn tại dù pipeline chuyển sang hệ thống phân tích đang chậm.

### 7.2. Ví dụ Java

Đoạn code là khung nghiệp vụ minh họa. Nó giả định order, claim, reservation, fulfillment, audit và outbox nằm trong cùng transaction cơ sở dữ liệu; không áp dụng nguyên xi cho các tài nguyên ở nhiều dịch vụ.

```java
@Transactional
public AcceptResult acceptFulfillment(
        VerifiedActor actor,
        ReleaseCommand command) {

    Order order = orders.lockForTenant(
                    actor.tenantId(), command.orderId())
            .orElseThrow(OrderNotFoundException::new);

    access.requireCanRelease(actor, order);

    // Thu thập và bảo vệ dữ liệu dùng để quyết định.
    ReleaseFacts facts = releaseFacts.lockAndLoad(order, command);
    EligibilityDecision decision = eligibility.evaluate(actor, facts);
    decision.requireAllowed();

    UUID fulfillmentId = ids.newFulfillmentId();
    UUID auditEventId = ids.newEventId();

    Fulfillment fulfillment = Fulfillment.accepted(
            fulfillmentId,
            order.id(),
            command.commandId(),
            1L);

    fulfillments.insert(fulfillment);
    ClaimReferences claims = quantities.claimAllOrThrow(
            fulfillmentId, facts.releasePlan());

    reservations.allocateAllOrThrow(
            fulfillmentId, facts.reservations());

    orders.markFulfillmentRequestedOrThrow(
            order.id(), command.expectedOrderVersion());

    FulfillmentAuditEvent auditEvent = auditFactory.accepted(
            auditEventId,
            actor,
            fulfillment,
            facts,
            claims,
            decision,
            trustedClock.instant());

    auditRepository.append(auditEvent);

    outbox.appendReleaseCommand(
            fulfillmentId,
            command.commandId(),
            auditEventId,
            facts.releasePlan());

    return new AcceptResult(
            fulfillmentId, "RELEASE_PENDING", auditEventId);
}
```

Các điều kiện triển khai không được bỏ qua:

- `VerifiedActor` được tạo từ ngữ cảnh xác thực, không deserialize trực tiếp từ body.
- `releaseFacts` và các thao tác ghi cùng thực thi giao thức khóa/phiên bản để quyết định không dựa trên dữ liệu lỗi thời.
- Các hàm claim và chuyển trạng thái kiểm tra số hàng cập nhật, trạng thái nguồn và giới hạn nghiệp vụ.
- Ngoại lệ khiến toàn bộ transaction rollback theo cấu hình thực tế.
- Lớp idempotency nhận diện lệnh trước khi tạo tác vụ mới và lưu kết quả nhất quán với transaction; ví dụ chưa thể hiện lớp đó.
- Một retry của lệnh đã commit phải tìm về tác vụ cũ, không gọi lại nhánh tạo `fulfillmentId` mới.
- Audit được dựng từ các sự thật phía máy chủ, không dùng một chuỗi JSON do client cung cấp.
- Lệnh ra kho chỉ được gửi sau commit thông qua outbox.
- `auditEventId` trong response chỉ là tham chiếu; người dùng vẫn cần quyền mới xem được chi tiết audit.

Nếu pipeline audit tập trung là thành phần bắt buộc theo chính sách hệ thống, phải định nghĩa yêu cầu bền vững và hành vi khi pipeline lỗi. Không mặc nhiên coi việc gọi HTTP đến hệ thống audit sau commit là ghi audit nguyên tử.

### 7.3. Audit khi phát lệnh ra ngoài

Một lần gửi mạng có thể có kết quả không rõ:

```text
worker gửi lệnh
kho đã nhận
response bị mất
worker chỉ thấy timeout
```

Audit phía worker nên ghi “timeout/chưa xác định kết quả”, không tự tuyên bố kho chưa thực hiện.

Khi có bằng chứng nhận lệnh hoặc hoàn tất từ kho, ghi bản ghi tương ứng theo giao thức xử lý kết quả. Nếu kho đã thực hiện nhưng ghi nhận cục bộ thất bại, dùng cùng định danh tác vụ để truy vấn/đối soát.

Không thể dùng transaction cục bộ để bảo đảm một cuộc gọi mạng và việc ghi audit ở nhiều hệ thống cùng thành công hoặc cùng rollback.

## 8. Giữ dấu vết của lần thử bị từ chối và lỗi xử lý

### 8.1. Vì sao ghi rồi ném ngoại lệ có thể mất audit?

Ví dụ dễ sai:

```java
@Transactional
public void release(...) {
    if (!allowed) {
        auditRepository.appendRejected(...);
        throw new BusinessRuleViolation(...);
    }
}
```

Nếu ngoại lệ làm rollback transaction, bản ghi từ chối cũng có thể bị rollback. Kẻ tấn công có thể tạo hàng nghìn lần thử nhưng lịch sử không giữ được chúng.

Một cách tổ chức là để ranh giới xử lý request nhận kết quả sau khi transaction nghiệp vụ đã kết thúc, rồi ghi attempt audit qua cơ chế độc lập phù hợp.

Không nên sao chép một annotation “transaction mới” mà không kiểm tra cấu hình, ranh giới lời gọi và hành vi thực tế của framework. Điều cần bảo đảm là lần ghi dấu vết không bị cuốn vào rollback của thao tác bị từ chối.

### 8.2. Phân loại kết quả đúng

| Kết quả quan sát | Loại bản ghi phù hợp |
| --- | --- |
| Chính sách xác định người gọi không có quyền | `RELEASE_REJECTED`, mã lý do quyền |
| Đơn chưa đáp ứng điều kiện đã xác minh | `RELEASE_REJECTED`, mã lý do nghiệp vụ |
| Chưa lấy được dữ liệu bắt buộc | `RELEASE_DEFERRED` hoặc trạng thái chờ theo hợp đồng |
| Lỗi kỹ thuật và xác định transaction rollback | `PROCESSING_FAILED` |
| Timeout ở ranh giới không biết commit hay chưa | `OUTCOME_UNKNOWN`, sau đó tra cứu theo commandId |
| Retry tìm thấy kết quả đã commit | `REPLAY_RESULT_RETURNED`, liên kết tác vụ cũ |

Không ghi `RELEASE_REJECTED` chỉ vì response cho client bị lỗi sau khi transaction đã commit. Điều đó sẽ làm lịch sử mâu thuẫn với tác vụ thực sự đã được chấp nhận.

### 8.3. Ghi nhận sự cố audit mà không mở quyền nghiệp vụ

Nếu cơ chế ghi nhật ký lần thử bị lỗi, yêu cầu đã bị từ chối vẫn phải bị từ chối. Không dùng lỗi audit làm lý do bỏ qua quyền hoặc eligibility.

Hệ thống cần có chính sách về bộ đệm bền vững, cảnh báo, giới hạn tải và phục hồi pipeline. Không thể tuyên bố “không mất audit” nếu chỉ ghi vào bộ nhớ rồi bỏ qua khi đầy.

Với luồng có nguy cơ bị spam, kết hợp rate limit, thống kê tổng hợp và cơ chế bảo vệ pipeline. Nếu áp dụng lấy mẫu cho dữ liệu chẩn đoán, phải phân biệt rõ với các bản ghi nghiệp vụ và bằng chứng bảo mật bắt buộc phải giữ.

## 9. Retry, sự kiện trùng và thứ tự không đồng nhất

### 9.1. Một hành động, nhiều lần quan sát

Một lệnh có thể được quan sát nhiều lần ở các ranh giới khác nhau:

```text
client retry
publisher gửi lại
broker phát lại
consumer xử lý lại
provider gửi webhook trùng
```

Audit nên giữ được những lần quan sát cần thiết mà không biến chúng thành nhiều lần thực hiện.

Ví dụ hợp lệ:

```text
attempt 1 -> command C -> fulfillment F -> ACCEPTED version 1
attempt 2 -> command C -> trả kết quả của fulfillment F
webhook P -> WAREHOUSE_ACCEPTED version 2
webhook P lặp -> ghi nhận duplicate receipt, không tăng version nghiệp vụ
```

Một `eventId` mới cho mỗi lần nhận lại webhook không đủ chống xử lý trùng. Cần giữ `sourceEventId` và phạm vi của nguồn phát, như tài khoản tích hợp cùng định danh sự kiện.

Nếu nhà cung cấp phát nhiều loại sự kiện cho cùng một tác vụ, deduplicate theo sự kiện không thay thế kiểm tra nghiệp vụ theo tác vụ. Hai sự kiện khác mã vẫn có thể mô tả cùng một tác động.

### 9.2. Inbox và audit nghiệp vụ

Bộ xử lý tích hợp có thể thực hiện:

```text
BEGIN
    nhận diện source event chưa xử lý trong inbox
    tải và bảo vệ fulfillment liên quan
    xác minh sự kiện có đủ điều kiện áp dụng
    cập nhật trạng thái khi có thay đổi hợp lệ
    ghi business audit nếu có thay đổi
    ghi kết quả xử lý inbox
COMMIT
```

Nếu sự kiện bị lặp, không tạo audit chuyển trạng thái thứ hai. Có thể tăng thống kê lần nhận hoặc ghi một attempt/receipt riêng theo chính sách lưu trữ.

Nếu sự kiện hợp lệ về nguồn nhưng mâu thuẫn nghiệp vụ, giữ bằng chứng đã xác minh và kết quả “chờ đối soát” hoặc “không áp dụng” trong luồng phù hợp. Không bỏ dấu vết chỉ vì nó không khớp state machine.

Bản ghi inbox không tự chứng minh sự kiện đã được áp dụng. Cần phân biệt đã nhận, đã xác minh, đã xử lý và kết quả nghiệp vụ.

### 9.3. Có nhiều loại thời gian

| Trường thời gian | Diễn giải |
| --- | --- |
| `occurredAt` | Thời điểm nguồn hoặc ứng dụng cho rằng sự việc xảy ra |
| `recordedAt` | Thời điểm hệ thống cục bộ ghi nhận theo quy ước |
| `ingestedAt` | Thời điểm pipeline tập trung nhận bản ghi |

Đồng hồ có thể lệch, mạng có thể chậm và sự kiện có thể đến muộn. Timestamp do provider gửi cần được giữ rõ xuất xứ; không được coi là đồng hồ tuyệt đối của toàn hệ thống.

`recorded_at DEFAULT CURRENT_TIMESTAMP` trong schema cũng không phải bằng chứng về thứ tự commit toàn cục. Ngữ nghĩa timestamp tùy cơ sở dữ liệu và cách lấy thời gian.

Trong một aggregate, dùng phiên bản và quan hệ nhân quả để diễn giải thứ tự. Giữa các aggregate hoặc dịch vụ, lưu các liên kết nguyên nhân thay vì giả định sắp xếp timestamp sẽ tạo được một lịch sử toàn cục chính xác.

### 9.4. Không chèn lại quá khứ để làm lịch sử trông đẹp

Nếu hôm nay nhận bằng chứng rằng kho đã bàn giao hôm qua:

- Giữ thời điểm xảy ra do nguồn khai báo.
- Giữ thời điểm thực tế hệ thống nhận và công nhận bằng chứng.
- Ghi sự kiện ở phiên bản cục bộ mới.
- Liên kết đến tác vụ và bằng chứng liên quan.

Không sửa timestamp của một bản ghi cũ để khiến nó trông như hệ thống đã biết sự việc từ hôm qua.

Nếu phát hiện một kết luận trước đó sai, ghi sự kiện hiệu chỉnh hoặc bù trừ có tham chiếu đến bản ghi cũ. Giữ được “hệ thống đã tin gì ở từng thời điểm” là yếu tố quan trọng khi điều tra lỗi logic.

## 10. Bảo vệ audit khỏi sửa, xóa và giả mạo

### 10.1. Xác định ai có thể tác động đến bằng chứng

Các mối đe dọa có thể gồm:

- Người dùng gửi `actorId`, trạng thái hoặc lý do giả trong request.
- Nhân viên có quyền vận hành tìm cách xóa dấu vết thao tác.
- Tài khoản ứng dụng bị lộ và ghi bản ghi không hợp lệ.
- Người có quyền cơ sở dữ liệu cập nhật hoặc xóa lịch sử.
- Pipeline làm mất, phát trùng hoặc sửa dữ liệu khi chuyển hệ thống.
- Người xem audit vượt phạm vi tenant hoặc tải toàn bộ dữ liệu nhạy cảm.

Không có một biện pháp đơn lẻ giải quyết tất cả các mối đe dọa này.

### 10.2. Phân quyền append và read

Một cách tổ chức:

- Tài khoản ứng dụng chỉ được ghi thêm audit qua đường đã kiểm soát.
- Không cấp quyền sửa/xóa lịch sử cho công cụ vận hành thông thường.
- Tài khoản đọc phục vụ điều tra được giới hạn tenant và chức năng.
- Việc xuất dữ liệu diện rộng hoặc truy cập đặc quyền được ghi dấu vết.
- Quyền quản trị kho audit được tách khỏi quyền xử lý fulfillment khi phù hợp.

Append-only ở tầng ứng dụng giúp giảm sửa nhầm, nhưng không chống được mọi người có quyền cao hơn trong hạ tầng. Chính sách quyền, lưu trữ, sao lưu và kiểm chứng phải phù hợp với mô hình đe dọa.

Không dùng một bảng “history” có API cập nhật tự do rồi gọi đó là lịch sử bất biến.

### 10.3. Phát hiện sửa đổi bằng digest và hash chain

Một digest gắn với dữ liệu có thể giúp phát hiện thay đổi nếu digest gốc được bảo vệ. Tuy nhiên, lưu `hash(payload)` ngay cạnh payload không ngăn người có quyền sửa cả hai.

Một hash chain theo aggregate có dạng khái niệm:

```text
eventHash[n] =
    H(
      domain
      + canonicalEvent[n]
      + previousEventHash
    )
```

Triển khai thực tế cần định nghĩa cách mã hóa không mơ hồ, bao gồm các trường được bảo vệ, biểu diễn số/thời gian và canonicalization. Không nên ghép chuỗi tùy tiện hoặc phụ thuộc vào thứ tự field JSON không được quy định.

Những giới hạn cần hiểu:

- Cùng chuỗi phải có cơ chế tuần tự hóa để tránh hai nhánh cạnh tranh không được kiểm soát.
- Hash chain không chứng minh dữ liệu đầu vào là đúng.
- Người có quyền viết lại toàn chuỗi có thể tính lại hash nếu không có điểm kiểm chứng được bảo vệ độc lập.
- Xóa phần đuôi có thể không bị phát hiện chỉ bằng cách đọc phần còn lại.
- Chuỗi hợp lệ không chứng minh hệ thống không bỏ sót một sự kiện ngay từ đầu.

Có thể bổ sung checkpoint được bảo vệ ở miền quản trị khác, chữ ký hoặc HMAC với quản lý khóa phù hợp, và lưu trữ có cơ chế chống ghi đè theo nhu cầu. Mỗi cách vẫn cần quản lý quyền, khóa, vòng đời và quy trình kiểm tra.

Một checkpoint chỉ chứng thực đến vị trí mà nó bao phủ. Không nên suy ra rằng mọi bản ghi phát sinh sau checkpoint gần nhất đều đã được bảo vệ tương đương.

Không ghi khóa ký/HMAC trong log hoặc cùng vùng dữ liệu mà mọi người sửa audit đều đọc được. Khi dùng phiên bản khóa, giữ thông tin đủ để kiểm tra những bản ghi cũ theo chính sách.

### 10.4. Bổ sung bằng chứng, không xóa dấu vết sai

Ví dụ, kho gửi nhầm xác nhận bàn giao rồi rút lại. Một lịch sử phù hợp có thể là:

```text
version 3: HANDOVER_CONFIRMED
version 4: HANDOVER_DISPUTED, references event của version 3
version 5: RECONCILIATION_RESOLVED
```

Trạng thái hiện tại phải được cập nhật theo quy tắc xử lý tranh chấp. Audit giữ được các phát biểu và quyết định theo thời gian.

Đó không phải lý do để giữ mọi dữ liệu cá nhân vô thời hạn. Phải giảm dữ liệu ngay từ thiết kế và có quy trình retention/redaction rõ ràng nếu cần. Việc xử lý dữ liệu không nên âm thầm biến thành sửa lịch sử quyết định nghiệp vụ.

## 11. Quyền truy cập, dữ liệu nhạy cảm và lưu trữ

### 11.1. Audit chứa dữ liệu có giá trị với kẻ tấn công

Lịch sử có thể tiết lộ:

- Quan hệ khách hàng, đơn hàng và kho.
- Thời điểm hàng có giá trị được xuất.
- Quy tắc phê duyệt và lý do chặn.
- Định danh nhân viên và cách vận hành nội bộ.
- Tham chiếu đến chứng cứ thanh toán hoặc giao hàng.

Do đó, endpoint xem audit cần kiểm tra quyền trên tenant và tài nguyên như các API nghiệp vụ khác. Biết `eventId` hoặc `correlationId` không tạo quyền truy cập.

Trang khách hàng có thể chỉ hiển thị lịch sử phù hợp như “đã nhận đơn”, “đang xử lý”, “đã bàn giao”. Lịch sử điều tra nội bộ có thể chứa chi tiết khác nhưng vẫn phải giới hạn theo nhiệm vụ.

### 11.2. Tối thiểu hóa dữ liệu từ đầu

Nên ưu tiên:

- Định danh nội bộ hoặc tham chiếu thay cho toàn bộ địa chỉ, thông tin thanh toán.
- Reason code có cấu trúc thay cho văn bản tự do chứa bí mật.
- Tham chiếu đến evidence store có kiểm soát quyền.
- Giá trị đã làm sạch và giới hạn chiều dài cho các trường do bên ngoài cung cấp.
- Mã hóa và phân quyền truy cập cho các bằng chứng cần bảo vệ.

Nếu phải lưu dữ liệu nguồn để kiểm chứng chữ ký hoặc điều tra, tách phần bằng chứng nhạy cảm sang vùng có kiểm soát phù hợp. Audit chỉ chứa liên kết và metadata cần thiết.

Hash một email hoặc số điện thoại không tự biến dữ liệu thành không thể nhận diện; miền giá trị có thể dễ đoán và dữ liệu vẫn có thể liên kết. Không dùng việc “đã hash” làm lý do xuất dữ liệu rộng rãi.

Với dữ liệu đưa vào log hoặc giao diện, xử lý đúng ký tự điều khiển và escaping. Một reason do client gửi có thể chứa xuống dòng hoặc nội dung gây nhầm lẫn; không được để nó giả thành bản ghi hệ thống mới.

### 11.3. Retention và khả năng tra cứu

Thời gian giữ dữ liệu phải được xác định theo nhu cầu nghiệp vụ, điều tra và chính sách dữ liệu áp dụng. Không sao chép tùy ý thời gian giữ application log sang audit nghiệp vụ.

Cần tính đến:

- Thời gian tồn tại của tranh chấp, đổi trả và tác vụ đối soát.
- Việc giữ policy và bằng chứng có phiên bản.
- Dữ liệu nóng để tra cứu nhanh và dữ liệu lưu trữ dài hạn.
- Khả năng khôi phục, kiểm chứng và phân quyền sau khi archive.
- Chính sách xử lý dữ liệu cá nhân và các tham chiếu đã hết hiệu lực.

Khi cắt chuỗi audit để archive, giữ metadata về phạm vi được chuyển và điểm kiểm chứng tương ứng. Nếu hệ thống chỉ giữ một đoạn lịch sử trực tuyến, giao diện và công cụ kiểm tra phải biết rằng phần đầu đang ở archive, tránh báo nhầm là mất bản ghi.

## 12. Dùng audit để điều tra một nghi vấn giao trùng

### 12.1. Dựng lại chuỗi theo định danh, không đếm dòng log

Giả sử khách phản ánh nhận hai kiện hàng cho cùng một đơn. Lịch sử ban đầu có thể là:

```text
11:00:00  attempt A1 yêu cầu thực hiện order O42
11:00:01  fulfillment F90 được chấp nhận, version 1, claim 2 sản phẩm
11:00:03  worker gửi F90, timeout
11:00:08  worker gửi lại F90
11:00:09  kho xác nhận tác vụ W5 cho F90, version 2
11:00:12  webhook xác nhận W5 được gửi lại, không tạo chuyển trạng thái
11:15:00  bằng chứng bàn giao H1, version 3
```

Hai lần gửi và hai webhook không đủ chứng minh giao trùng. Cần xác định có bao nhiêu nghĩa vụ thực hiện, claim, tác vụ kho và bằng chứng bàn giao độc lập.

Các câu hỏi tiếp theo:

1. Có một hay nhiều `fulfillmentRequestId`?
2. Có nhiều claim cho cùng phần số lượng không?
3. Nếu có tác vụ thứ hai, nó là giao bù đã được duyệt hay tác vụ trái quy tắc?
4. Hai lần gửi cùng requestId có bị kho ánh xạ thành hai mã tác vụ khác nhau không?
5. Bằng chứng bàn giao cho từng kiện nói gì về dòng hàng và số lượng?
6. Có công cụ quản trị hoặc thao tác trực tiếp nào nằm ngoài đường audit chuẩn không?

Nếu chỉ có một fulfillment cục bộ nhưng kho tạo hai tác vụ khác nhau, trọng tâm điều tra là giao thức chống trùng và thực hiện bên kho. Nếu có hai fulfillment cục bộ cùng claim phần hàng vượt nghĩa vụ, trọng tâm là invariant, transaction và những đường ghi đã chấp nhận chúng.

### 12.2. Truy vấn lịch sử trong đúng phạm vi

Ví dụ truy vấn sau khi đã kiểm tra quyền xem audit của đơn:

```sql
SELECT
    event_id,
    fulfillment_request_id,
    aggregate_version,
    event_type,
    from_state,
    to_state,
    actor_id,
    command_id,
    causation_id,
    occurred_at,
    recorded_at,
    evidence_ref
FROM fulfillment_audit
WHERE tenant_id = :authorized_tenant_id
  AND order_id = :authorized_order_id
ORDER BY
    fulfillment_request_id,
    aggregate_version;
```

Thứ tự này giúp đọc từng aggregate, không tuyên bố có một thứ tự thời gian toàn cục giữa mọi fulfillment.

Sau đó liên kết command, outbox, receipt và bằng chứng kho qua các định danh đã định nghĩa. Đừng chỉ tìm chuỗi orderId trong application log: một bước tích hợp có thể dùng mã tác vụ hoặc vận đơn mà không lặp lại mọi định danh.

### 12.3. Ghi kết quả điều tra thành bằng chứng bổ sung

Nếu xác định một tác vụ đã bị tạo sai:

- Giữ nguyên bản ghi chấp nhận ban đầu.
- Ghi phát hiện, phạm vi ảnh hưởng và bằng chứng đối soát.
- Thực hiện lệnh xử lý phù hợp như dừng, thu hồi, hoàn trả hoặc giao bù.
- Liên kết hành động xử lý về sự kiện và tác vụ gây ra vấn đề.
- Theo dõi kết quả thực tế của biện pháp khắc phục.

Không sửa lịch sử để biến tác vụ sai thành “chưa từng tồn tại”. Điều đó làm mất nguyên nhân gốc và có thể khiến hệ thống cấp lại tài sản vì tưởng nghĩa vụ chưa được thực hiện.

## 13. Kiểm tra tính đầy đủ của pipeline audit

### 13.1. Các phép đối soát hữu ích

Với hợp đồng một sự kiện cho mỗi thay đổi phiên bản fulfillment, có thể kiểm tra:

- Aggregate đã tồn tại có sự kiện tạo tương ứng.
- Phiên bản cuối trong audit khớp phiên bản hiện tại trong phạm vi dữ liệu được kiểm tra.
- Không có khoảng trống phiên bản trong phần lịch sử chưa archive, theo hợp đồng đã định nghĩa.
- Trạng thái cuối trong audit khớp trạng thái aggregate tương ứng.
- Sự kiện chấp nhận có claim và ý định gửi kho liên quan.
- Xác nhận từ kho có nguồn bằng chứng và ánh xạ đúng tác vụ.
- Sự kiện từ pipeline tập trung truy ngược được về bản ghi cục bộ.

Một phép kiểm tra “max version bằng version hiện tại” không đủ phát hiện mất sự kiện ở giữa. Cần kiểm tra cả chuỗi, phạm vi retention và checkpoint.

Khoảng trống trong sequence kỹ thuật của cơ sở dữ liệu có thể xuất hiện do rollback hoặc cơ chế cấp số. Không coi mọi số bị thiếu là bằng chứng mất audit; phải dựa vào hợp đồng phiên bản nghiệp vụ.

### 13.2. Đối soát phải hiểu độ trễ và ranh giới đọc

Nếu lần đọc trạng thái nghiệp vụ và lần đọc kho audit tập trung diễn ra ở các thời điểm khác nhau, một chênh lệch có thể chỉ là độ trễ pipeline.

Nên đối soát theo snapshot, watermark hoặc phạm vi đã được xác nhận chuyển đủ. Báo cáo cần nêu bản ghi đang chờ ingest, bị lỗi xuất hay thực sự không tồn tại ở nguồn.

Không coi việc hệ thống tìm kiếm chưa có bản ghi là bằng chứng rằng transaction gốc không có audit. Khi cần kết luận, quay lại nguồn cục bộ có thẩm quyền và các bằng chứng liên quan.

### 13.3. Theo dõi độ trễ, lỗi và quyền truy cập

Các chỉ số và cảnh báo có thể gồm:

- Số lần ghi audit bắt buộc thất bại.
- Độ trễ chuyển audit từ nguồn đến nơi tra cứu.
- Tuổi của bản ghi chờ export lâu nhất.
- Số sự kiện sai schema hoặc không xác minh được nguồn.
- Mâu thuẫn phiên bản, trạng thái hoặc số lượng.
- Sự kiện có actor không thuộc phạm vi quyền dự kiến.
- Lượt xem hoặc export audit vượt mức sử dụng bình thường.
- Thao tác quản trị thay đổi quyền ghi, xóa hoặc cấu hình lưu trữ.

Không ghi toàn bộ audit nhạy cảm vào cảnh báo rộng rãi. Cảnh báo nên chứa định danh và liên kết điều tra theo quyền.

## 14. Ma trận kiểm thử tình huống lạm dụng và lỗi

Kiểm thử cần chứng minh cả tính đúng của bản ghi và mối liên hệ với tác động nghiệp vụ.

| Tình huống | Cách thử | Kết quả bắt buộc |
| --- | --- | --- |
| Giả actor | Gửi `actorId`, `initiatedBy` hoặc header tự khai | Audit dùng danh tính/ngữ cảnh đã xác minh; không bị ghi đè |
| Sai tenant | Người tenant A thao tác hoặc xem lịch sử tenant B | Bị từ chối; không lộ bằng chứng ngoài phạm vi |
| Sai quyền kho | Nhân viên ngoài phạm vi gọi release | Không có tác vụ thành công; có dấu vết từ chối phù hợp |
| Bỏ qua phê duyệt | Xin release đơn chưa được duyệt | Không có audit thành công; ghi đúng mã lý do từ chối |
| Audit bắt buộc lỗi | Gây lỗi insert audit trong transaction | Claim, trạng thái và outbox cùng rollback |
| Outbox lỗi | Audit insert được nhưng ghi outbox lỗi | Audit thành công trong transaction đó cũng rollback |
| Lỗi sau commit | Mất response sau khi chấp nhận | Retry tìm thấy tác vụ cũ; không thêm sự kiện chấp nhận mới |
| Không rõ commit | Giả lập lỗi kết nối tại ranh giới commit | Không kết luận sai; tra cứu/đối soát theo commandId |
| Ghi từ chối rồi rollback | Từ chối lệnh và kết thúc transaction | Dấu vết từ chối vẫn tồn tại qua cơ chế độc lập đã thiết kế |
| Pipeline attempt lỗi | Làm cơ chế ghi lần thử không sẵn sàng | Không chuyển lệnh bị từ chối thành được phép; có cảnh báo |
| Retry client | Gửi cùng key và payload nhiều lần | Nhiều attempt có thể tồn tại, chỉ một tác vụ nghiệp vụ |
| Đổi key | Tạo key mới để xin thực hiện lại cùng phần hàng | State machine và quota ngăn cấp trùng; audit phản ánh kết quả thật |
| Webhook trùng | Phát lại cùng source event | Không tăng phiên bản nghiệp vụ lần hai |
| Webhook sai nguồn | Sai chữ ký/tài khoản hoặc ánh xạ tác vụ | Không công nhận trạng thái; giữ dấu vết nguồn bị từ chối phù hợp |
| Sự kiện đến trễ | Bằng chứng cũ đến sau các bước mới | Giữ cả thời điểm nguồn và thời điểm ghi nhận, không viết lại quá khứ |
| Hai cập nhật cạnh tranh | Hai lệnh thay đổi cùng fulfillment | Chuỗi phiên bản phù hợp với các transaction đã commit |
| Snapshot bị đổi về sau | Cập nhật dữ liệu nguồn sau release | Audit vẫn giải thích được dữ liệu/policy lúc quyết định |
| Sửa bản ghi | Thay một trường thuộc phạm vi được bảo vệ | Kiểm chứng phát hiện theo cơ chế toàn vẹn đã thiết kế |
| Viết lại chuỗi | Sửa dữ liệu và tính lại hash trong kho nguồn | Checkpoint/chứng thực độc lập phát hiện trong phạm vi đã được bao phủ |
| Xóa phần đuôi | Xóa các bản ghi đã được checkpoint bao phủ | Kiểm tra với checkpoint phát hiện thiếu dữ liệu |
| Log injection | Gửi reason chứa xuống dòng/ký tự điều khiển | Không tạo bản ghi giả hoặc làm hỏng hiển thị |
| Export vượt quyền | Xin tải audit/evidence ngoài nhiệm vụ | Bị chặn và ghi nhận truy cập theo chính sách |
| Archive lịch sử | Chuyển phần đầu chuỗi sang lưu trữ | Có thể tìm lại, kiểm chứng và hiểu phạm vi dữ liệu |
| Hiệu chỉnh sự kiện sai | Rút lại một xác nhận bàn giao | Có sự kiện hiệu chỉnh liên kết; lịch sử ban đầu không bị xóa âm thầm |

### 14.1. Kiểm thử điểm lỗi quanh transaction

Với lệnh chấp nhận fulfillment, chủ động gây lỗi:

```text
sau tạo request
sau claim một dòng
sau allocation
sau insert audit
sau insert outbox nhưng trước commit
sau commit nhưng trước response
```

Đọc lại dữ liệu sau khi transaction kết thúc. Trước commit, không được có một phần của tác vụ thành công bị bỏ lại. Sau commit, phải tìm lại được đầy đủ quyết định và tác vụ qua định danh ổn định.

Các bài kiểm thử cần xác minh cấu hình transaction thực tế. Chỉ nhìn thấy annotation hoặc mock trả về thành công không chứng minh được rollback và ràng buộc cơ sở dữ liệu.

### 14.2. Kiểm thử bằng câu hỏi điều tra

Chọn một tác vụ ngẫu nhiên và yêu cầu công cụ điều tra dựng lại:

```text
người khởi tạo
quyền và phạm vi được kiểm tra
dữ liệu/policy tại thời điểm chấp nhận
số lượng đã claim
lệnh đã gửi
kết quả bên ngoài
những lần retry và hiệu chỉnh
```

Nếu phải đoán từ tên trạng thái hoặc tra cứu một hàng dữ liệu đã bị ghi đè, audit chưa đáp ứng mục tiêu giải thích quyết định.

Một lịch sử có rất nhiều dòng vẫn có thể thiếu bằng chứng quan trọng. Thước đo là khả năng trả lời câu hỏi nghiệp vụ bằng dữ liệu có xuất xứ và phạm vi tin cậy rõ ràng.

## 15. Những lỗi thiết kế cần tránh

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ ghi “đã xuất” | Không phân biệt chấp nhận lệnh và tác động thực tế | Dùng loại sự kiện phản ánh đúng mức bằng chứng |
| Tin actor do client truyền | Lạm dụng có thể bị gán cho người khác | Lấy danh tính từ nguồn xác thực và ủy quyền đã kiểm chứng |
| Audit thành công ngoài transaction | Có thể có tác vụ thiếu audit hoặc audit thành công giả | Ghi audit cục bộ cùng transaction và xuất sau commit |
| Audit từ chối trong transaction rollback | Mất dấu vết lần thử tấn công | Dùng cơ chế ghi nhận độc lập phù hợp |
| Mỗi retry tạo tác vụ mới | Nhầm nhiều lần truyền tin thành nhiều nghĩa vụ | Liên kết attempt với command và request ổn định |
| Chỉ sắp xếp timestamp | Hiểu sai sự kiện đến muộn hoặc đồng hồ lệch | Dùng phiên bản cục bộ và quan hệ nhân quả |
| Lưu hash cạnh dữ liệu rồi coi bất biến | Người sửa cả hai có thể che dấu thay đổi | Phân quyền và điểm kiểm chứng độc lập theo mô hình đe dọa |
| Log nguyên request và token | Audit trở thành nguồn rò rỉ | Snapshot tối thiểu, evidence store và kiểm soát quyền |
| Xóa lịch sử khi xử lý sai | Mất khả năng điều tra và mở lại nghĩa vụ ngoài ý muốn | Ghi hiệu chỉnh/bù trừ liên kết bản ghi gốc |
| Coi audit là cơ chế ngăn chặn | Lạm dụng vẫn xảy ra dù có thể truy lại | Thực thi invariant và quyền trước khi chấp nhận hành động |

## 16. Câu hỏi tự đánh giá

1. Audit đang ghi một lần thử, một quyết định đã commit hay tác động đã được xác nhận?
2. Danh tính người thao tác đến từ đâu, có thể bị client ghi đè không?
3. Bằng chứng nào giải thích quyền và eligibility của đúng đơn, kho, dòng hàng và số lượng?
4. Audit thành công có cùng transaction với thay đổi nghiệp vụ không?
5. Lần bị từ chối có mất dấu vết khi rollback không?
6. Retry và webhook trùng được liên kết thế nào để không bị hiểu thành nhiều lần thực hiện?
7. Hệ thống có phân biệt thời điểm xảy ra, ghi nhận và ingest không?
8. Ai có thể sửa, xóa, xem hoặc export lịch sử?
9. Cơ chế kiểm chứng phát hiện được kiểu sửa/xóa nào và có giới hạn gì?
10. Bằng chứng và policy cũ có còn đọc được sau khi dữ liệu hiện tại đã thay đổi?

Audit trail của fulfillment cần giữ được quan hệ giữa ý định, quyền, quyết định và tác động. Khi các bản ghi có cấu trúc, được ghi đúng ranh giới transaction, liên kết bằng định danh ổn định và bảo vệ theo mô hình đe dọa, chúng giúp kiểm tra business invariants và điều tra lạm dụng logic bằng bằng chứng cụ thể.
