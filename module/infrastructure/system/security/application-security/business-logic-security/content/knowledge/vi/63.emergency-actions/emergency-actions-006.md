# Emergency action notification — Thông báo hành động khẩn cấp

## 1. Thông báo khẩn cấp là một phần của kiểm soát nghiệp vụ

Một hệ thống cho phép nhân viên trực ca đóng băng tài khoản đang bị chiếm quyền, dừng hoàn tiền hàng loạt hoặc tạm ngắt thanh toán để hạn chế thiệt hại. Khả năng hành động nhanh là cần thiết, nhưng cũng tạo ra một con đường mà người có quyền có thể lạm dụng: viện lý do khẩn cấp để bỏ qua phê duyệt, thay đổi trạng thái đối tượng rồi không cho bộ phận giám sát biết.

**Emergency action notification** là cơ chế thông báo và theo dõi trách nhiệm sau hoặc trong quá trình thực hiện hành động khẩn cấp. Cơ chế này phải bảo đảm hành động hợp lệ được ghi nhận bền vững, chuyển đến đúng người có trách nhiệm, và được đưa lên cấp xử lý tiếp theo nếu chưa có người tiếp nhận.

Trong bảo mật logic nghiệp vụ, mục tiêu không dừng ở việc “gửi được một email”. Mục tiêu là bảo vệ mối liên hệ giữa:

- Ai được phép thực hiện hành động nào trên đối tượng nào.
- Hành động thực sự đã chuyển trạng thái gì và khi nào.
- Ai phải biết, ai phải tiếp nhận và ai được phép phê duyệt hoặc kết thúc hậu kiểm.
- Điều gì xảy ra khi kênh thông báo hỏng hoặc người nhận không phản hồi.

Trong bài này, “thông báo” là thông báo về một hành động khẩn cấp của ứng dụng. Việc gửi cảnh báo sơ bộ trước khi hành động thành công có thể hữu ích, nhưng phải được phân biệt rõ với thông báo xác nhận hành động đã có hiệu lực.

### Tình huống xuyên suốt

Nền tảng thanh toán có hành động `FREEZE_PAYOUTS`, tạm đóng băng việc chi trả của một merchant khi nghi ngờ tài khoản bị chiếm quyền.

Quy tắc ví dụ:

1. Nhân viên trực ca chỉ được thao tác trên merchant thuộc phạm vi mình phụ trách.
2. Đóng băng cần có mã sự cố và lý do; hệ thống xác định quyền khẩn cấp ở phía server.
3. Sau khi trạng thái đóng băng được commit, phải có sự kiện thông báo bền vững.
4. Đội ứng cứu và người giám sát độc lập phải nhận được thông tin theo chính sách.
5. Nếu chưa có người đủ thẩm quyền xác nhận tiếp nhận trong thời hạn quy định, hệ thống phải escalation.
6. Xác nhận đã nhận thông báo không đồng nghĩa phê duyệt hành động, gỡ đóng băng hoặc hoàn tất hậu kiểm.

Các thời hạn và vai trò ở đây là ví dụ thiết kế. Mỗi tổ chức phải chọn chúng theo mức thiệt hại, khả năng trực ca và quy trình ứng cứu thực tế.

## 2. Tách quyền hành động, quyền tiếp nhận và quyền phê duyệt

Một lỗi logic phổ biến là xem mọi thao tác có chữ “emergency” như cùng một quyền. Trên thực tế, các quyền sau phục vụ những mục đích khác nhau:

| Quyền | Ví dụ | Không tự suy ra quyền nào |
| --- | --- | --- |
| Thực hiện hành động khẩn cấp | Đóng băng chi trả của merchant được giao | Không tự có quyền chọn lại người giám sát |
| Xem chi tiết sự cố | Xem dữ liệu trong tenant và phạm vi được phân công | Không tự có quyền thay đổi trạng thái merchant |
| Xác nhận tiếp nhận | Nhận trách nhiệm xử lý thông báo | Không tự phê duyệt quyết định của người thực hiện |
| Phê duyệt hoặc hậu kiểm | Đánh giá tính hợp lệ của việc dùng quyền khẩn cấp | Không tự có quyền gỡ đóng băng |
| Khôi phục hoạt động | Gỡ đóng băng khi đủ điều kiện | Không được dùng việc đã gửi thông báo làm điều kiện thay thế |
| Thay đổi tuyến thông báo | Cấu hình đội trực, kênh dự phòng | Không được xóa nghĩa vụ theo dõi của hành động đã xảy ra |

Nếu một hành động bắt buộc có hai người phê duyệt trước khi thực hiện, gửi thông báo cho người thứ hai sau đó không thể thay thế bước phê duyệt. Nếu chính sách cho phép cơ chế **break-glass** — dùng quyền khẩn cấp để xử lý trước và hậu kiểm sau — ngoại lệ này phải được định nghĩa riêng, có phạm vi và bằng chứng; thông báo là một phần của ngoại lệ đó.

Tương tự, việc nhân viên nhận email không chứng minh rằng họ đã đọc, tiếp nhận hay đồng ý. Hệ thống phải có dữ liệu riêng cho từng ý nghĩa nghiệp vụ.

## 3. Các business invariant cần bảo vệ

Business invariant là điều kiện phải luôn đúng dù người dùng sửa request, gọi API trực tiếp, gửi lại yêu cầu hoặc cố tình tạo lỗi đúng thời điểm.

### 3.1. Hành động đã commit phải có nghĩa vụ thông báo bền vững

Với mỗi lần chuyển trạng thái khẩn cấp thành công, hệ thống phải có bản ghi hành động và sự kiện tương ứng được lưu bền vững.

~~~text
EmergencyActionCommitted(actionId, version)
    => ActionRecordExists(actionId, version)
       AND NotificationObligationExists(actionId, version)
~~~

Điều kiện này không có nghĩa email hoặc tin nhắn đã đến nơi ngay tại thời điểm commit. Nó có nghĩa nghĩa vụ thông báo không thể bị mất chỉ vì tiến trình ứng dụng chết sau khi cập nhật cơ sở dữ liệu.

Chiều ngược lại cũng cần rõ ràng: thông báo khẳng định “chi trả đã bị đóng băng” chỉ được tạo từ bằng chứng chuyển trạng thái đã commit. Nếu thao tác thất bại, thông báo phải nói đó là một lần thử thất bại, không được mô tả như hành động đã hoàn tất.

### 3.2. Client không được tự quyết định người giám sát

Client có thể gửi lý do, mã sự cố hoặc đề nghị bổ sung người nhận theo chính sách. Client không được ghi đè những người bắt buộc nhận, hạ mức độ nghiêm trọng, tắt escalation hoặc tự gán trạng thái `ACKNOWLEDGED`.

Các trường như `notify=false`, `recipientOverride`, `skipSupervisor` hoặc `severity=LOW` không được trở thành lối đi tắt chỉ vì chúng xuất hiện trong request. Server phải dùng danh sách trường được phép nhận và tự tính các quyết định kiểm soát.

### 3.3. Mọi lần đọc và xác nhận phải đúng phạm vi đối tượng

Có `notificationId` không có nghĩa có quyền xem hoặc xác nhận thông báo đó. Mọi request phải kiểm tra tenant, đối tượng nghiệp vụ, nhóm trực và vai trò hiện tại.

~~~text
canAcknowledge(user, notification)
    = authenticated(user)
      AND sameTenantOrAuthorizedCentralRole(user, notification)
      AND assignedToResponseScope(user, notification)
      AND hasRequiredAcknowledgementRole(user)
      AND meetsIndependenceRule(user, notification.actionActor)
~~~

Quy tắc độc lập cuối cùng phụ thuộc chính sách. Nếu bắt buộc người tiếp nhận khác người thực hiện, tài khoản thao tác không được tự xác nhận để tắt escalation. Nếu cho phép tự nhận trách nhiệm trong tình huống nhân sự hạn chế, hệ thống vẫn phải giữ nghĩa vụ hậu kiểm độc lập riêng.

### 3.4. Gửi lại không được tạo thêm hành động hoặc thay đổi ý nghĩa

Cùng một idempotency key và cùng nội dung nghiệp vụ phải trả về cùng hành động. Dùng lại key với nội dung khác phải bị từ chối. Phạm vi key cần được xác định, chẳng hạn theo tenant, người yêu cầu và loại thao tác, thay vì dùng key do client gửi như một định danh toàn cục đáng tin cậy.

Retry thông báo phải giữ nguyên định danh sự kiện gốc. Một bản tin bị giao lại không được trở thành hành động đóng băng mới, một lần gia hạn mới hoặc một lần xác nhận mới.

### 3.5. Không thể xóa dấu vết bằng cách sửa tuyến thông báo

Đổi lịch trực hoặc kênh giao tiếp không được làm biến mất nghĩa vụ thông báo đã phát sinh. Bản ghi cần giữ phiên bản chính sách định tuyến, vai trò bắt buộc, kết quả phân giải người nhận và lịch sử các lần thay đổi tuyến.

Tại thời điểm gửi, quyền người nhận vẫn phải được kiểm tra lại. Không tiếp tục gửi dữ liệu nhạy cảm cho một người đã bị thu hồi quyền chỉ vì họ từng nằm trong lịch trực. Hệ thống cần tìm người thay thế hợp lệ hoặc đưa lên tuyến giám sát dự phòng.

### 3.6. Xác nhận tiếp nhận không được xóa nghĩa vụ hậu kiểm

Một người nhấn “đã tiếp nhận” chỉ làm thay đổi trạng thái tiếp nhận theo quyền của họ. Nó không được tự động:

- Xóa sự kiện khỏi audit log.
- Đánh dấu hành động là hợp lệ.
- Khôi phục trạng thái của đối tượng.
- Hủy mọi thông báo bắt buộc gửi cho các vai trò còn lại.
- Kết thúc hồ sơ sự cố khi điều kiện hậu kiểm chưa đủ.

## 4. Thiết kế trạng thái rõ ràng

Nên tách ít nhất ba trục trạng thái. Gộp tất cả vào một cột `status` dễ làm một thao tác như “gửi email thành công” vô tình đóng cả hồ sơ.

### 4.1. Trạng thái hành động nghiệp vụ

Ví dụ một hành động cục bộ trong cùng cơ sở dữ liệu:

~~~text
REQUESTED → AUTHORIZED → APPLIED
                     ↘ REJECTED / FAILED
~~~

`AUTHORIZED` chỉ được ghi sau kiểm tra quyền và điều kiện áp dụng. `APPLIED` chỉ được ghi khi thay đổi nghiệp vụ tương ứng đã commit.

Nếu hành động phải gọi hệ thống ngoài, cần thêm trạng thái như `PENDING_EXTERNAL` và `CONFIRMED`, kèm cơ chế đối soát. Không gọi một yêu cầu vừa được gửi tới hệ thống ngoài là “đã có hiệu lực”. Thời điểm phát sinh thông báo phải phản ánh đúng giai đoạn: yêu cầu đang chờ thực hiện hay kết quả đã được xác nhận.

### 4.2. Trạng thái giao thông báo

Trạng thái này thường được quản lý cho từng lần giao hoặc từng tuyến bắt buộc:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: Worker giữ lease
    CLAIMED --> PROVIDER_ACCEPTED: Nhà cung cấp chấp nhận
    CLAIMED --> RETRY_WAIT: Lỗi tạm thời
    CLAIMED --> UNKNOWN: Không biết kết quả sau timeout
    CLAIMED --> PENDING: Lease hết hạn
    RETRY_WAIT --> PENDING: Đến thời điểm thử lại
    UNKNOWN --> PENDING: Được phép gửi lại theo chính sách
    UNKNOWN --> PROVIDER_ACCEPTED: Đối soát được kết quả
    RETRY_WAIT --> NEEDS_INTERVENTION: Hết ngân sách retry
    UNKNOWN --> NEEDS_INTERVENTION: Không thể đối soát
    PROVIDER_ACCEPTED --> DELIVERY_CONFIRMED: Có bằng chứng giao
    PROVIDER_ACCEPTED --> NEEDS_INTERVENTION: Nhận lỗi giao muộn
~~~

Không phải kênh nào cũng cung cấp bằng chứng `DELIVERY_CONFIRMED`. Chỉ có phản hồi thành công từ API nhà cung cấp thì dùng ý nghĩa `PROVIDER_ACCEPTED`; không suy diễn thành “người trực đã nhận”. Lease cần có thời hạn và cơ chế thu hồi để worker chết không giữ bản ghi mãi mãi.

`NEEDS_INTERVENTION` là tình trạng phải xử lý, không phải cách xóa trách nhiệm gửi. Một worker tổng hợp có thể vẫn tiếp tục dùng kênh dự phòng hoặc tạo nhiệm vụ can thiệp thủ công.

### 4.3. Trạng thái trách nhiệm xử lý

~~~text
UNACKNOWLEDGED → ACKNOWLEDGED → REVIEW_PENDING → REVIEW_COMPLETED
~~~

Đây là ví dụ đơn giản của quy trình. Nếu nhiều vai trò bắt buộc xác nhận, lưu trạng thái theo từng nghĩa vụ; một lần xác nhận của đội ứng cứu không tự thay cho người giám sát độc lập.

Escalation có thể xảy ra nhiều lần khi chưa có xác nhận hợp lệ, vì vậy nên lưu như các sự kiện có cấp độ, thời điểm và người nhận. Không nhất thiết ép nó thành một trạng thái duy nhất loại trừ khả năng đã gửi qua một tuyến khác.

Một hành động có thể đồng thời là `APPLIED`, một kênh là `RETRY_WAIT`, và nghĩa vụ tiếp nhận là `UNACKNOWLEDGED`. Sự kết hợp này phải hiển thị được để người vận hành thấy hành động đã có hiệu lực nhưng việc thông báo đang gặp vấn đề.

## 5. Nối transaction với thông báo bằng transactional outbox

### 5.1. Khoảng trống nguy hiểm của cách gửi trực tiếp

Hai cách triển khai sau đều có lỗi:

~~~text
Cách A: Cập nhật merchant → commit → gửi thông báo
                                      ↑ tiến trình có thể chết trước bước này

Cách B: Gửi thông báo → cập nhật merchant → commit
                                            ↑ transaction có thể rollback
~~~

Cách A có thể làm mất thông báo. Cách B có thể gửi thông tin khẳng định một việc chưa xảy ra. Gọi API email ngay trong transaction cũng không làm API bên ngoài rollback theo cơ sở dữ liệu, đồng thời có thể giữ lock quá lâu.

Với hành động và dữ liệu nằm trong cùng cơ sở dữ liệu, **transactional outbox** giải quyết khoảng trống ghi nhận: thay đổi trạng thái, audit record, nghĩa vụ thông báo và sự kiện outbox được ghi trong cùng transaction. Worker riêng đọc những sự kiện đã commit để gửi thông báo.

~~~mermaid
sequenceDiagram
    actor Operator as Nhân viên trực
    participant API as Emergency API
    participant DB as Cơ sở dữ liệu
    participant Worker as Notification worker
    participant Channel as Kênh thông báo
    actor Responder as Người tiếp nhận

    Operator->>API: Yêu cầu đóng băng + idempotency key
    API->>DB: Bắt đầu transaction, kiểm tra và khóa dữ liệu cần thiết
    API->>DB: Ghi trạng thái, action record, nghĩa vụ, outbox
    DB-->>API: Commit thành công
    API-->>Operator: actionId + trạng thái APPLIED
    Worker->>DB: Nhận sự kiện đã commit bằng lease
    Worker->>Channel: Gửi thông báo với eventId ổn định
    Channel-->>Worker: Chấp nhận hoặc trả lỗi
    Worker->>DB: Lưu kết quả lần giao
    Responder->>API: Xác nhận tiếp nhận qua phiên đã xác thực
    API->>DB: Kiểm tra quyền và ghi acknowledgement
~~~

Outbox bảo vệ việc không mất nghĩa vụ khi commit. Nó không bảo đảm email chỉ được giao đúng một lần, không thay thế kiểm tra quyền và không tự giải quyết lỗi của hành động trên hệ thống ngoài.

### 5.2. Mã giả cho ranh giới transaction

Đoạn sau là mã giả theo phong cách Java, thể hiện thứ tự kiểm soát. Các hàm repository, lock và transaction cần được triển khai theo hệ quản trị dữ liệu thực tế.

~~~java
ActionResult freezePayouts(Actor actor, FreezeCommand command) {
    return transaction.execute(() -> {
        TenantId tenantId = authorization.resolveTenant(actor);
        authorization.requireEmergencyScope(actor, tenantId);
        validation.requireIncidentAndReason(command);

        // Key được ràng buộc với tenant, actor và loại thao tác.
        // Database phải có unique constraint để xử lý request đồng thời.
        IdempotencySlot slot = idempotency.claimOrLoad(
            tenantId, actor.id(), "FREEZE_PAYOUTS",
            command.idempotencyKey(), command.semanticFingerprint()
        );
        if (slot.isCompleted()) {
            authorization.requireCanViewAction(actor, slot.actionId());
            return slot.previousResult();
        }

        Merchant merchant = merchants.lockByTenantAndId(
            tenantId, command.merchantId()
        );
        authorization.requireCanFreeze(actor, merchant);
        policy.requireAllowedTransition(merchant, command);

        // Áp dụng quy tắc chống tạo lại cùng một chuyển trạng thái
        // bằng key khác; không tạo action mới khi merchant đã bị đóng băng.
        merchant.freezePayouts();
        ActionRecord action = actions.recordApplied(
            actor, merchant, command.incidentId(), command.reason()
        );
        audit.recordEmergencyAction(action);

        // Chụp chính sách và nghĩa vụ nhận; việc phân giải người trực
        // và kiểm tra quyền cuối cùng diễn ra khi giao thông báo.
        NotificationObligation obligation = obligations.create(
            action, routingPolicy.snapshotFor(action)
        );
        outbox.append(EmergencyActionApplied.from(action, obligation));

        ActionResult result = ActionResult.applied(action.id());
        idempotency.complete(slot, action.id(), result);
        return result;
    });
}
~~~

`claimOrLoad` phải so sánh fingerprint, xử lý xung đột đồng thời và chỉ trả kết quả hoàn tất khi transaction chứa hành động đã commit. Không được chỉ dùng cache trong bộ nhớ để bảo vệ idempotency. Nếu cùng key nhưng payload khác, trả lỗi xung đột theo hợp đồng API, không thực hiện payload thứ hai.

Transaction bảo đảm không commit hành động nếu không ghi được nghĩa vụ và outbox. Khi cơ sở dữ liệu gặp sự cố, hệ thống cần một quy trình khẩn cấp thay thế đã được xác định trước, chẳng hạn thao tác tại một mặt phẳng điều khiển độc lập với hồ sơ sự cố riêng. Không âm thầm bỏ qua bước ghi nhận để tiếp tục qua API này.

Ngược lại, khi cơ sở dữ liệu đã commit nhưng nhà cung cấp thông báo đang lỗi, không tự động hoàn tác việc đóng băng để “khớp” trạng thái gửi. Hệ thống giữ biện pháp bảo vệ, retry và chuyển kênh theo chính sách. Hai tình huống lỗi này có ý nghĩa nghiệp vụ khác nhau.

### 5.3. Một số ràng buộc dữ liệu hữu ích

Các khóa dưới đây là ví dụ về ý nghĩa cần bảo vệ, không phải một schema dùng chung cho mọi hệ thống:

| Ràng buộc duy nhất | Ý nghĩa |
| --- | --- |
| `(tenant_id, actor_id, operation, idempotency_key)` | Ngăn một request nghiệp vụ được thực thi lại trong cùng phạm vi |
| `(tenant_id, action_id, action_version, event_type)` | Ngăn tạo nhiều sự kiện gốc cho cùng một lần chuyển trạng thái |
| `(event_id, obligation_id, recipient_id, channel, generation)` | Phân biệt một lần giao logic với các lần retry và lần escalation mới |
| `(obligation_id, acknowledgement_role, responder_id)` | Chống tạo nhiều bản ghi tiếp nhận giống nhau do retry |
| `(obligation_id, escalation_level)` | Ngăn nhiều scheduler tạo cùng một cấp escalation |

Nếu chỉ cho phép một người nhận trách nhiệm ở một vai trò, cần thêm điều kiện cập nhật hoặc ràng buộc tương ứng trên slot trách nhiệm. Khóa acknowledgement theo người xác nhận đơn thuần không ngăn hai người cùng nhận một slot.

Cần có chính sách lưu idempotency key đủ lâu so với cửa sổ retry. Sau khi key hết hạn, state machine và ràng buộc nghiệp vụ vẫn phải ngăn tạo lại một chuyển trạng thái không hợp lệ.

## 6. Nội dung thông báo và định tuyến an toàn

### 6.1. Nội dung phải đủ để hành động nhưng không lộ dữ liệu thừa

Một sự kiện nội bộ có thể chứa các trường sau:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt_7bc12",
  "eventType": "EmergencyActionApplied",
  "actionId": "act_92d31",
  "actionVersion": 1,
  "tenantId": "tenant_42",
  "actionType": "FREEZE_PAYOUTS",
  "targetType": "MERCHANT",
  "targetId": "merchant_314",
  "actorId": "operator_18",
  "occurredAt": "2026-11-22T02:15:00Z",
  "incidentId": "incident_781",
  "reasonCode": "SUSPECTED_ACCOUNT_TAKEOVER",
  "beforeState": "PAYOUTS_ENABLED",
  "afterState": "PAYOUTS_FROZEN",
  "severity": "HIGH",
  "routingPolicyVersion": "emergency-routing-v4",
  "obligationId": "obl_51a0"
}
~~~

Đây là envelope nội bộ. Khi gửi ra email, chat hoặc hệ thống bên ngoài, cần dựng nội dung theo quyền của kênh và người nhận. Không chuyển toàn bộ event vào mọi kênh.

Một thông báo ngắn có thể gồm:

~~~text
[KHẨN CẤP] Chi trả đã được đóng băng

Hành động: act_92d31
Đối tượng: merchant_314, theo phạm vi hiển thị được phép
Thời điểm có hiệu lực: 22/11/2026 09:15, UTC+07:00
Mã sự cố: incident_781
Trạng thái tiếp nhận: Chưa có người nhận trách nhiệm
Hạn tiếp nhận: 22/11/2026 09:20, UTC+07:00

Mở hồ sơ trên cổng ứng cứu để xem chi tiết và xác nhận tiếp nhận.
~~~

Không đưa mật khẩu, token, cookie, toàn bộ hồ sơ khách hàng hoặc dữ liệu thanh toán nhạy cảm vào tin nhắn. Lý do dạng văn bản tự do có thể chứa dữ liệu nhạy cảm hoặc ký tự gây chèn nội dung; cần giới hạn độ dài, escape theo định dạng đích và tránh để nội dung này tạo mention hàng loạt, giả mạo nút thao tác hoặc header email.

Thời điểm cần lưu bằng mốc thời gian thống nhất do server ghi nhận; giao diện hiển thị thêm múi giờ rõ ràng. Không lấy deadline từ đồng hồ của trình duyệt hoặc từ timestamp do client tự khai.

### 6.2. Định tuyến theo chính sách phía server

Đầu vào định tuyến thường gồm loại hành động, tenant, phạm vi đối tượng, mức độ nghiêm trọng do server tính và lịch trực. Server tạo nghĩa vụ cho những vai trò cần nhận rồi phân giải người trực hiện tại.

Ví dụ:

| Loại nghĩa vụ | Người nhận chính | Nếu không phân giải được |
| --- | --- | --- |
| Tiếp nhận ứng cứu | Nhóm trực phụ trách tenant | Nhóm trực trung tâm được cấp quyền |
| Giám sát độc lập | Quản lý rủi ro hoặc người hậu kiểm | Tuyến giám sát dự phòng |
| Theo dõi vận hành | Trung tâm vận hành có quyền phù hợp | Hàng đợi xử lý sự cố định tuyến |

Không có người trực hợp lệ là một lỗi cấu hình hoặc vận hành cần thấy được. Không được đánh dấu “đã gửi” bằng cách gửi cho người thao tác hoặc một hộp thư mặc định không có người theo dõi.

Việc sửa chính sách định tuyến cần phân quyền riêng, lưu lịch sử và có kiểm soát độc lập tương xứng. Nếu người thực hiện có thể đổi người giám sát sang chính mình rồi hành động, quy tắc độc lập đã bị vô hiệu hóa ngay từ cấu hình.

### 6.3. Link trong thông báo phải dẫn tới kiểm tra quyền

Link nên trỏ đến cổng ứng cứu trên origin được cấu hình tin cậy. Sau khi mở, hệ thống xác thực và kiểm tra quyền theo đối tượng ở server.

Không ghép URL từ `Host` hoặc URL tùy ý do request gửi lên. Không dùng `GET` mở link làm thao tác xác nhận; công cụ quét email và trình duyệt có thể truy cập trước người dùng. Thao tác xác nhận cần một request thay đổi trạng thái có bảo vệ CSRF khi dùng phiên cookie, cùng kiểm tra quyền và trạng thái hiện tại.

Nếu dùng liên kết có token cho một quy trình cụ thể, token cần giới hạn mục đích, thời hạn và phạm vi, tránh xuất hiện trong log hoặc bị chuyển tiếp ngoài ý muốn. Đối với hành động tiếp nhận có trách nhiệm, vẫn cần xác định danh tính người thực hiện; việc sở hữu link không mặc nhiên là đủ thẩm quyền.

### 6.4. Thông báo nội bộ và thông báo cho khách hàng là hai nghĩa vụ khác nhau

Thông báo nội bộ cho đội ứng cứu không nên bị trộn với email gửi chủ tài khoản. Khi tài khoản khách hàng có thể đã bị chiếm quyền, gửi chi tiết điều tra tới địa chỉ đang bị kẻ tấn công kiểm soát có thể làm lộ cách ứng phó.

Chính sách cần xác định riêng nội dung, thời điểm và kênh xác minh cho khách hàng. Việc trì hoãn thông báo ra ngoài theo quy trình ứng cứu không được trở thành lý do tắt thông báo nội bộ hoặc xóa dấu vết.

## 7. Retry, chống trùng và xử lý kết quả không xác định

### 7.1. Chấp nhận khả năng giao lặp

Giả sử worker gửi thành công tới nhà cung cấp rồi chết trước khi ghi kết quả vào cơ sở dữ liệu. Sau khi lease hết hạn, worker khác sẽ gửi lại.

Đây là khoảng trống không thể giải quyết chỉ bằng cờ `sent=true`. Thiết kế thực tế thường cho phép gửi lại và kiểm soát tác động trùng:

1. Giữ `eventId` ổn định qua các lần retry.
2. Mỗi lần gọi có `attemptId` riêng để điều tra và đo độ trễ.
3. Dùng idempotency key của nhà cung cấp nếu họ hỗ trợ với ngữ nghĩa phù hợp.
4. Dùng khóa giao logic ổn định để chống tạo nhiều công việc cùng nghĩa.
5. Hiển thị `actionId` nhất quán để người nhận biết các bản tin nói về cùng hành động.
6. Làm endpoint xác nhận idempotent theo quy tắc trách nhiệm.

Không hứa “exactly once” cho toàn bộ email, webhook và tương tác con người nếu hạ tầng không cung cấp bảo đảm đó.

### 7.2. Retry có giới hạn và có đường thoát

Lỗi tạm thời có thể retry với khoảng chờ tăng dần và độ lệch ngẫu nhiên để tránh dồn tải. Lỗi cấu hình hoặc người nhận không hợp lệ cần đi sang tuyến sửa cấu hình hoặc kênh dự phòng, thay vì thử mãi cùng một địa chỉ.

Khi hết ngân sách retry, bản ghi phải xuất hiện trong hàng đợi can thiệp, có người chịu trách nhiệm và có thể phát lại. Phát lại giữ sự kiện gốc và lưu người yêu cầu phát lại; không sửa thời điểm hành động để làm độ trễ trông ngắn hơn.

Timeout khi gọi nhà cung cấp tạo ra trạng thái không biết kết quả. Có thể đối soát qua định danh phía nhà cung cấp hoặc gửi lại theo chính sách chấp nhận trùng. Không được tự kết luận chắc chắn là thất bại, cũng không tự đánh dấu đã giao.

### 7.3. Callback cũng là một bề mặt tấn công

Callback từ nhà cung cấp báo “đã giao” chỉ cập nhật trạng thái giao. Nó không được xác nhận thay con người, phê duyệt hành động hay đóng sự cố.

Hệ thống cần xác minh nguồn callback theo cơ chế của nhà cung cấp, kiểm tra tính toàn vẹn, thời hạn và chống replay theo định danh sự kiện. Phải đối chiếu callback với lần gửi đã biết trong đúng tenant và xử lý callback lặp hoặc đến sai thứ tự bằng chuyển trạng thái có điều kiện.

Không nhận một `actionId` bất kỳ từ callback rồi cho phép cập nhật trực tiếp hồ sơ nghiệp vụ. Nếu nhà cung cấp hỗ trợ URL webhook do cấu hình, chỉ quản trị viên được cấp quyền mới được sửa đích; không cho người dùng đưa URL tùy ý vào yêu cầu khẩn cấp để máy chủ gửi dữ liệu ra ngoài.

## 8. Xác nhận tiếp nhận và escalation

### 8.1. Deadline bắt đầu từ sự kiện nghiệp vụ

Với thông báo về hành động đã có hiệu lực, deadline nên được tính từ thời điểm commit hoặc xác nhận có hiệu lực được hệ thống ghi nhận, theo chính sách. Không bắt đầu lại đồng hồ mỗi khi worker retry hoặc đổi kênh.

Ví dụ chính sách nội bộ:

| Mốc tính từ lúc hành động có hiệu lực | Điều kiện và xử lý |
| --- | --- |
| Ngay khi sự kiện sẵn sàng | Gửi nghĩa vụ ứng cứu và giám sát qua các kênh được phép |
| Sau 2 phút | Nếu chưa có bằng chứng giao theo tiêu chí kênh, thử tuyến dự phòng |
| Sau 5 phút | Nếu chưa có người đủ quyền tiếp nhận, escalation tới trưởng ca |
| Sau 15 phút | Nếu vẫn chưa tiếp nhận, mở nhiệm vụ can thiệp vận hành và gọi theo quy trình trực |
| Sau tiếp nhận | Theo dõi việc xử lý và hậu kiểm bằng deadline riêng |

Đây là các mốc minh họa. Chúng không phải tiêu chuẩn áp dụng cho mọi hệ thống. Kênh không cung cấp bằng chứng giao vẫn phải chịu deadline tiếp nhận; không chờ vô hạn ở trạng thái “đã được nhà cung cấp chấp nhận”.

### 8.2. Thao tác xác nhận phải kiểm tra lại quyền tại thời điểm thực hiện

Endpoint minh họa:

~~~http
POST /emergency-actions/act_92d31/acknowledgements
Content-Type: application/json

{
  "obligationId": "obl_51a0",
  "expectedVersion": 3
}
~~~

Danh tính người xác nhận, vai trò, tenant và thời điểm lấy từ phiên đã xác thực và dữ liệu server. Không cho client tự gửi `responderId`, `acknowledgedAt` hoặc `approved=true` để ghi thẳng vào bản ghi.

Server cần kiểm tra:

- Hành động và nghĩa vụ có thật, liên kết đúng với nhau và nằm trong phạm vi người gọi.
- Người gọi đáp ứng vai trò và quy tắc độc lập tại thời điểm hiện tại.
- Nghĩa vụ còn cho phép nhận trách nhiệm; nếu đã có người khác nhận, áp dụng quy tắc bàn giao rõ ràng.
- Phiên bản còn phù hợp hoặc request là retry hợp lệ có thể trả lại kết quả cũ.
- Kết quả xác nhận và audit record được ghi nhất quán.

Nếu nhân viên đã bị thu hồi quyền sau khi nhận tin, link cũ không được cho phép họ xác nhận tiếp. Retry sau khi đã xác nhận thành công cũng cần kiểm tra quyền trước khi trả chi tiết có thể nhạy cảm.

### 8.3. Race giữa xác nhận và escalation

Scheduler có thể kiểm tra “chưa tiếp nhận” đúng lúc người trực đang xác nhận. Có thể giảm xung đột bằng cập nhật có điều kiện theo phiên bản, khóa slot nghĩa vụ và ràng buộc duy nhất cho mỗi cấp escalation.

Dù vậy, một tin escalation đã được gửi ra ngoài ngay trước lúc commit xác nhận có thể vẫn đến muộn. Nội dung nên hướng người nhận xem trạng thái hiện tại trên cổng ứng cứu và không coi tin nhắn cũ là nguồn quyết định cuối cùng.

Scheduler phải phân biệt các nghĩa vụ. Việc một người nhận trách nhiệm ứng cứu có thể dừng escalation cho slot đó, nhưng không tự hủy thông báo hoặc deadline của hậu kiểm độc lập.

## 9. Tránh dùng thông báo để che giấu hoặc gây từ chối dịch vụ

### 9.1. Chống tạo bão thông báo

Kẻ có tài khoản hợp lệ có thể gửi nhiều yêu cầu để làm nhóm trực bỏ qua cảnh báo. Biện pháp cần đặt vào đúng lớp:

- Chống tạo hành động trùng bằng idempotency và state machine.
- Hạn chế yêu cầu không hợp lệ, theo người gọi và phạm vi phù hợp.
- Gom các cảnh báo giống nhau bằng khóa ổn định, vẫn giữ số lượng và mốc thời gian.
- Chia công suất theo tenant, ưu tiên theo mức độ được tính ở server.
- Dành dung lượng cho hành động quan trọng và kênh ứng cứu dự phòng.

Không được chỉ thêm rate limit cho worker rồi âm thầm bỏ các sự kiện hợp lệ khi vượt ngưỡng. Nếu cần gộp nhiều sự kiện thành một thông báo, mỗi hành động vẫn phải liên kết được tới thông báo tổng hợp và có nghĩa vụ theo dõi tương ứng.

Mức độ nghiêm trọng do client tự khai không được quyết định hoàn toàn quyền ưu tiên; nếu không, kẻ tấn công có thể tự nâng mọi yêu cầu lên khẩn cấp.

### 9.2. Không cho phép mute hoặc maintenance xóa nghĩa vụ

Mute một kênh chat không được đồng nghĩa không cần giám sát hành động khẩn cấp. Cửa sổ bảo trì cần có tuyến thay thế đã cấu hình, thời hạn hiệu lực và lịch sử thay đổi.

Các cờ tắt thông báo phải có phạm vi hẹp, có thời điểm hết hạn và không được do cùng người thao tác tùy ý đặt trong request hành động. Sự kiện vẫn cần được ghi nhận bền vững dù một kênh tạm ngừng hoạt động.

### 9.3. Theo dõi hệ thống thông báo từ một tuyến có khả năng sống độc lập

Nếu cảnh báo “worker thông báo đã chết” cũng chỉ đi qua chính worker đó, sự cố có thể không ai thấy. Cần theo dõi bên ngoài tiến trình gửi về độ trễ outbox, heartbeat, hàng đợi can thiệp và các nghĩa vụ quá hạn.

Không nhất thiết mọi tuyến phải dùng hạ tầng hoàn toàn khác, nhưng thiết kế cần chỉ ra những điểm lỗi chung và một cách can thiệp khi tuyến chính không hoạt động.

## 10. Audit, đo lường và đối soát

### 10.1. Bằng chứng cần giữ

Hồ sơ nên nối được từ hành động tới từng lần giao và lần xác nhận:

~~~text
actionId
  ├── Quyết định quyền + lý do + mã sự cố + trạng thái trước/sau
  ├── eventId + thời điểm commit + phiên bản schema
  ├── obligationId + vai trò bắt buộc + phiên bản chính sách
  │     ├── deliveryId + người nhận + kênh + attemptId + kết quả
  │     ├── escalationLevel + thời điểm + tuyến bổ sung
  │     └── acknowledgement + người tiếp nhận + thời điểm + phiên bản
  └── Kết quả hậu kiểm hoặc hành động khôi phục có kiểm soát riêng
~~~

Audit cần được bảo vệ khỏi sửa hoặc xóa bởi người chỉ có quyền thực hiện hành động khẩn cấp. Có thể dùng lưu trữ chỉ bổ sung và cơ chế phát hiện sửa đổi theo nhu cầu hệ thống. Không khẳng định một bảng tên `audit_log` tự có khả năng chống can thiệp.

Phân quyền đọc, thời hạn lưu và dữ liệu cá nhân trong audit cũng cần có chính sách. Không ghi token xác nhận hoặc thông tin bí mật chỉ để thuận tiện điều tra.

### 10.2. Chỉ số cần phản ánh kết quả nghiệp vụ

Các chỉ số hữu ích gồm:

- Số hành động `APPLIED` không tìm thấy nghĩa vụ hoặc sự kiện tương ứng; kỳ vọng là bằng không.
- Tuổi của sự kiện outbox cũ nhất chưa xử lý và độ trễ theo tenant, mức độ.
- Thời gian từ lúc có hiệu lực tới lần được nhà cung cấp chấp nhận, bằng chứng giao nếu có, và lần tiếp nhận hợp lệ.
- Số nghĩa vụ quá hạn chưa tiếp nhận, phân theo vai trò và tuyến trực.
- Số bản ghi cần can thiệp, callback không xác thực được và lỗi định tuyến.
- Tỷ lệ giao lại, phát lại thủ công và mức độ gộp cảnh báo.

“API gửi trả thành công 99%” không chứng minh đội trực đã biết và xử lý sự cố. Phải quan sát cả luồng trách nhiệm sau khi gửi.

### 10.3. Đối soát để phát hiện thiếu sót

Một tác vụ đối soát có thể so sánh các lần chuyển trạng thái khẩn cấp với action record, outbox và nghĩa vụ. Nó hữu ích khi có thao tác quản trị trực tiếp, lỗi migration hoặc hỏng logic khiến các ràng buộc trong ứng dụng bị bỏ qua.

Nếu phát hiện hành động thiếu sự kiện, cần lập sự kiện khôi phục có dấu vết, tham chiếu bằng chứng gốc và giữ thời điểm phát hiện riêng với thời điểm hành động. Không tự tạo timestamp giả như thể thông báo đã tồn tại từ trước.

Đối soát là lớp phát hiện bổ sung; nó không thay thế transaction và ràng buộc dữ liệu trong đường xử lý chính.

## 11. Kiểm thử tình huống tấn công logic

Kiểm thử cần kiểm tra invariant và bằng chứng trong dữ liệu, không chỉ kiểm tra HTTP trả mã thành công.

| Tình huống | Cách kích hoạt | Kết quả cần chứng minh |
| --- | --- | --- |
| Tắt thông báo qua request | Gửi thêm `notify=false`, người nhận tự chọn hoặc mức độ thấp | Server từ chối hoặc bỏ qua trường không được phép; nghĩa vụ bắt buộc vẫn tồn tại |
| Truy cập chéo tenant | Đổi `merchantId`, `actionId` hoặc `obligationId` sang tenant khác | Không đọc, không xác nhận, không thay đổi dữ liệu ngoài quyền |
| Bỏ qua phê duyệt | Gọi trực tiếp API emergency khi chính sách chưa cho phép ngoại lệ | Không thực thi; gửi thông báo không được dùng để thay bước phê duyệt |
| Rollback transaction | Gây lỗi sau khi đổi trạng thái nhưng trước commit | Không có trạng thái mới hoặc sự kiện khẳng định đã áp dụng được commit |
| Chết sau commit | Dừng tiến trình trước khi worker gửi | Nghĩa vụ và outbox còn nguyên, worker khác tiếp tục xử lý |
| Chết sau khi gửi | Nhà cung cấp nhận nhưng worker chưa lưu kết quả | Có thể giao lặp, không tạo hành động hoặc nghĩa vụ gốc mới |
| Request đồng thời | Gửi cùng key và cùng payload từ nhiều kết nối | Chỉ một chuyển trạng thái; các request nhận kết quả hoặc xung đột theo hợp đồng |
| Tái sử dụng key sai | Gửi cùng key nhưng merchant hoặc nội dung khác | Từ chối payload mới, không trả nhầm kết quả như một yêu cầu hợp lệ |
| Dùng key mới để lặp hành động | Gửi nhiều key cho cùng merchant đã đóng băng | State machine chặn chuyển trạng thái trùng theo chính sách |
| Tự tiếp nhận để tắt giám sát | Người thực hiện xác nhận slot yêu cầu độc lập | Bị từ chối; nghĩa vụ giám sát còn hiệu lực |
| Quyền vừa bị thu hồi | Nhận tin, mất quyền, sau đó mở link xác nhận | Kiểm tra quyền hiện tại, không ghi acknowledgement trái phép |
| Công cụ quét link | Truy cập URL trong email bằng `GET` | Không làm thay đổi trạng thái tiếp nhận |
| Callback giả hoặc lặp | Gửi callback không xác thực hoặc phát lại callback cũ | Không giả trạng thái giao, không xác nhận thay con người |
| Lịch trực bị rỗng | Không tìm được người nhận hợp lệ | Dùng tuyến dự phòng hoặc tạo can thiệp; không đánh dấu hoàn tất giả |
| Timeout hoặc lỗi kênh chính | Mô phỏng kết quả không xác định hay lỗi kéo dài | Retry, đối soát và chuyển kênh giữ nguyên deadline gốc |
| Race nhận trách nhiệm | Hai người xác nhận cùng slot một lúc | Tuân thủ quy tắc một người hoặc nhiều người đã định nghĩa; không mất audit |
| Race escalation | Scheduler chạy cùng lúc với xác nhận | Không sinh lặp cùng cấp; không làm lùi trạng thái đã tiếp nhận |
| Tạo bão yêu cầu | Dồn tải hợp lệ và không hợp lệ qua nhiều tenant | Giữ dấu vết sự kiện hợp lệ và công suất ưu tiên; không tenant nào che khuất toàn bộ tuyến |
| Thay đổi tuyến có chủ đích | Đổi người giám sát, mute kênh rồi thực hiện hành động | Kiểm soát cấu hình và lịch sử phát hiện được hành vi; nghĩa vụ không biến mất |

Đối với bài toán transaction, idempotency và lease, kiểm thử tích hợp trên cơ sở dữ liệu thật có giá trị hơn việc chỉ mock repository. Với lỗi giao thông báo, nên điều khiển được thời điểm chết của worker, timeout và callback đến trễ để quan sát đúng khoảng trống có thể tạo lặp.

Một tiêu chí thực hành: sau mỗi tình huống, có thể trả lời bằng dữ liệu rằng hành động nào đã có hiệu lực, nghĩa vụ nào còn mở, ai đã nhận trách nhiệm và vì sao hệ thống cho phép chuyển trạng thái đó.

## 12. Quy trình khi kênh thông báo gặp sự cố

Khi phát hiện hàng đợi tăng hoặc nghĩa vụ quá hạn, người vận hành cần một đường xử lý rõ ràng:

1. Xác định phạm vi ảnh hưởng qua tuổi outbox, tenant, loại hành động và các nghĩa vụ chưa tiếp nhận.
2. Kiểm tra hành động nào đã có hiệu lực; không yêu cầu người dùng làm lại hành động chỉ để kích hoạt một thông báo khác.
3. Chuyển sang tuyến dự phòng được phép hoặc liên hệ thủ công theo quy trình trực, chỉ cung cấp dữ liệu tối thiểu.
4. Ghi người liên hệ, thời điểm, người được xác minh đã nhận và tham chiếu hành động; phân biệt bản ghi liên hệ thủ công với acknowledgement trên ứng dụng.
5. Khôi phục worker và phát lại sự kiện gốc, giữ định danh và lịch sử lần gửi để xử lý trùng.
6. Đối soát các nghĩa vụ bắt buộc, tiếp tục escalation với nghĩa vụ chưa được đáp ứng và hoàn thành hậu kiểm theo quyền riêng.

Không sửa hàng loạt bản ghi thành `DELIVERED` hoặc `ACKNOWLEDGED` để làm bảng theo dõi hết đỏ. Nếu cho phép ghi nhận tiếp nhận qua quy trình thủ công, cần quyền riêng và bằng chứng về danh tính, thời điểm cùng phương thức xác minh.

Một thiết kế đạt mục tiêu khi hành động khẩn cấp có thể được thực hiện đúng quyền và đúng trạng thái, đồng thời không thể âm thầm thoát khỏi giám sát vì tiến trình chết, người gọi sửa request, thông báo bị gửi lặp hoặc một người cố tình xác nhận thay vai trò độc lập. Thông báo chỉ hoàn thành vai trò kiểm soát khi được nối với nghĩa vụ, danh tính và quy trình xử lý có thể kiểm chứng.
