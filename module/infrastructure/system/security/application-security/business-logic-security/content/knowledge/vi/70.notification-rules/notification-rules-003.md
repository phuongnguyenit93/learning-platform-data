# Notification timing

## 1. Thời điểm gửi là một quy tắc bảo mật nghiệp vụ

Thông báo có thể tiết lộ dữ liệu, khiến người dùng hành động hoặc tạo cảm giác một giao dịch đã hoàn tất. Vì vậy, gửi đúng nội dung đến đúng người vẫn chưa đủ: hệ thống còn phải gửi vào thời điểm mà nội dung đó được phép công bố và còn ý nghĩa.

**Notification timing** là tập quy tắc xác định khi nào được tạo ý định thông báo, khi nào được cấp phép gửi, khi nào phải chờ, hủy hoặc đánh dấu hết hạn. Trong bảo mật logic nghiệp vụ, các quy tắc này giúp ngăn:

- Công bố thành công khi giao dịch chưa commit hoặc chưa đủ phê duyệt.
- Gửi nhắc việc sau khi việc đã hoàn thành, bị hủy hoặc đổi người phụ trách.
- Trì hoãn cảnh báo bằng cách liên tục sửa lịch, đổi múi giờ hoặc kích hoạt debounce.
- Gửi hàng loạt khi request bị lặp, worker retry hoặc hệ thống chạy lại sau gián đoạn.
- Gửi liên kết hành động đã hết hạn hoặc cho người đã mất quyền.
- Tiết lộ sự tồn tại của tài khoản qua khác biệt thời gian phản hồi.

Bài học tập trung vào bất biến, state machine, quyền theo đối tượng, transaction và idempotency. Scheduler và message broker hỗ trợ thực thi, nhưng không tự quyết định khi nào một thông báo là hợp lệ.

### Tình huống xuyên suốt

Một nền tảng chi trả phục vụ nhiều doanh nghiệp; mỗi doanh nghiệp là một tenant. Yêu cầu chi “pay-81” của tenant “t-acme” cần hai người có thẩm quyền duyệt.

Khi yêu cầu được tạo hợp lệ, hệ thống dự kiến:

1. Gửi thông báo “có yêu cầu chờ duyệt” đến người có trách nhiệm.
2. Nhắc sau 10 phút nếu yêu cầu vẫn chờ duyệt và người nhận vẫn có quyền.
3. Hủy nhắc khi yêu cầu đã được duyệt, từ chối hoặc thu hồi.
4. Chỉ thông báo “đã chi trả” sau khi hệ thống đã xác nhận trạng thái chi trả tương ứng, không phải ngay khi người cuối cùng bấm duyệt.

Nếu yêu cầu được duyệt lúc 10:07, job nhắc đến hạn lúc 10:10 phải được xét lại. Một worker chỉ biết “đã đến giờ” có thể gửi thông báo sai và kèm thông tin tài chính cho người đã bị thay thế.

Các trạng thái, khoảng thời gian và schema trong bài là ví dụ thiết kế, không phải thông số bắt buộc cho mọi sản phẩm.

## 2. Phân biệt các mốc thời gian và mức bảo đảm

| Mốc | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| occurred_at | Sự kiện nghiệp vụ được ghi nhận là xảy ra khi nào | Không mặc nhiên tin timestamp client |
| recorded_at | Máy chủ ghi sự kiện vào dữ liệu khi nào | Có thể nằm trước commit |
| not_before | Sớm nhất được cấp phép gửi | Hàng đợi đánh thức sớm không được bỏ qua |
| send_by | Hạn cuối cấp phép gửi theo hợp đồng local | Ví dụ dùng biên loại trừ: now < send_by |
| next_attempt_at | Lúc thử xử lý tiếp theo | Không được gia hạn send_by |
| action_expires_at | Hạn của hành động hoặc token liên quan | Phải được kiểm tra ở API thực hiện |
| permitted_at | Hệ thống cấp phép một attempt | Chưa chứng minh nhà cung cấp đã nhận |
| provider_accepted_at | Nhà cung cấp xác nhận tiếp nhận | Chưa chứng minh người nhận đã đọc |
| delivery_reported_at | Callback báo tình trạng giao | Phải xác thực và hiểu đúng ngữ nghĩa kênh |

Không dùng recorded_at như một timestamp commit chính xác nếu cơ sở dữ liệu không cung cấp bảo đảm đó. Với outbox, điều quan trọng là relay chỉ nhìn thấy bản ghi đã commit, không phải tự đặt tên một trường “committed_at”.

Ba lời hứa sau khác nhau:

- “Không cấp phép gửi trước 10:00.”
- “Gửi yêu cầu đến nhà cung cấp trước 10:02.”
- “Người dùng nhận hoặc đọc trước 10:03.”

Ứng dụng chỉ kiểm tra đồng hồ local không thể bảo đảm cả ba. Độ trễ mạng, queue của nhà cung cấp và thiết bị người nhận nằm ngoài một transaction local. Hợp đồng sản phẩm phải nói rõ mốc nào được kiểm soát; nếu cần hạn lưu ở nhà cung cấp, phải dùng khả năng tương ứng của kênh và kiểm chứng hợp đồng đó.

Một notification được enqueue đúng hạn nhưng xử lý muộn vẫn có thể hết hiệu lực. Một callback “delivered” đến muộn cũng không tự đổi thời điểm quyết định nghiệp vụ đã được ghi nhận.

## 3. Những bất biến cần thực thi

### 3.1. Chỉ thông báo sự thật đã được chấp nhận

~~~text
Thông báo "đã hoàn tất X"
  => trạng thái đủ để khẳng định X đã được lưu bền vững

Thông báo "đang chờ duyệt X"
  => tồn tại yêu cầu hợp lệ cần được duyệt
  AND điều kiện chờ vẫn đúng tại điểm cấp phép gửi

Transaction tạo/sửa X bị rollback
  => không có ý định thông báo tương ứng được công bố ra ngoài
~~~

Không phải thông báo nào cũng phải chờ toàn bộ quy trình kết thúc. Email xác nhận đã tiếp nhận yêu cầu có thể gửi sau khi việc tiếp nhận đã commit. Thông báo kết quả chi trả phải dựa vào trạng thái xác nhận chi trả. Sự kiện kích hoạt và câu chữ phải phù hợp với nhau.

Thông báo bảo mật về một lần thử đáng ngờ có thể dựa trên sự kiện thử bị chặn, không cần một giao dịch thành công. Tuy nhiên, sự kiện đó cũng phải được xác thực nguồn và lưu theo quy trình, không do client tự khai “hãy gửi cảnh báo ưu tiên cao”.

### 3.2. Đúng đối tượng, đúng quyền, đúng thời điểm

Với thông báo n, đối tượng nghiệp vụ a và người nhận r:

~~~text
eligible(n, a, r, now)
  = cùng tenant hợp lệ
  AND sự kiện/điều kiện kích hoạt đúng
  AND thế hệ thông báo chưa bị thay thế
  AND người nhận/kênh phù hợp policy hiện tại
  AND phạm vi dữ liệu được phép tiết lộ
  AND not_before <= now < send_by
  AND chưa có cùng hiệu ứng gửi được chấp nhận trước đó
~~~

Quyền ở lúc lập lịch chưa đủ cho lúc gửi. Trong mười phút chờ, người duyệt có thể bị gỡ khỏi nhóm hoặc phạm vi cửa hàng thay đổi. Cần xét lại quyền trên đúng yêu cầu chi, không chỉ kiểm tra người nhận còn là người dùng đang hoạt động.

Không nhất thiết hủy mọi thông báo khi bất kỳ field nào thay đổi. Có thể dùng notification_epoch hoặc generation để tăng thế hệ khi có thay đổi ảnh hưởng ngữ nghĩa: hoàn thành, thu hồi, đổi người nhận hoặc đổi quyền công bố. Điều này tránh việc sửa một nhãn hiển thị làm mất cảnh báo cần thiết.

### 3.3. Hành động trong thông báo vẫn cần kiểm tra riêng

Email không phải nguồn sự thật để phê duyệt hoặc thanh toán. Khi người dùng mở liên kết, API phải kiểm tra quyền, trạng thái, phiên bản và thời hạn hiện tại. Một tin đến muộn không được làm sống lại quyền đã bị thu hồi.

Đọc tin, nhận callback hoặc bấm vào liên kết theo dõi không mặc nhiên nghĩa là đã phê duyệt. Nếu có hành động một lần qua token, cần cơ chế xác thực, ràng buộc và tiêu thụ nguyên tử phù hợp với hành động đó.

## 4. Chính sách thời gian phải thuộc máy chủ

Không cho người gọi tự gán priority=CRITICAL, bypass_quiet_hours=true, send_by hoặc loại cảnh báo bằng request tùy ý. Quyền sửa lịch hiển thị không đồng nghĩa quyền trì hoãn cảnh báo bảo mật hoặc gửi thành công trước phê duyệt.

| Loại thông báo | Mốc kích hoạt | Quy tắc thời gian điển hình |
| --- | --- | --- |
| Kết quả giao dịch | Trạng thái kết quả đã được xác nhận | Sau commit, nội dung đúng trạng thái |
| Nhắc phê duyệt | Yêu cầu hợp lệ còn chờ | Có not_before, hạn gửi và điều kiện hủy |
| Cảnh báo bảo mật | Sự kiện bảo mật đã được hệ thống chấp nhận | Độ trễ tối đa ngắn, quy tắc ưu tiên riêng |
| Mời hoặc xác minh | Lời mời/challenge còn hiệu lực | Không gửi liên kết hết hạn hoặc sai người |
| Thông tin định kỳ | Kỳ dữ liệu đã chốt | Theo timezone, occurrence và chính sách gom tin |
| Nội dung tùy chọn | Mục đích gửi và lựa chọn người nhận còn hợp lệ | Theo preference và hạn mức của loại nội dung |

Đây là phân loại sản phẩm minh họa. Điều kiện áp dụng tùy chọn nhận tin, ngoại lệ khẩn cấp và chính sách dữ liệu cần được xác định cụ thể; không suy rằng mọi thông báo gắn nhãn “bảo mật” được miễn mọi kiểm soát.

### Xây dựng cửa sổ gửi

~~~text
not_before = max(
  mốc sự kiện được máy chủ chấp nhận + độ trễ theo policy,
  mốc cấm công bố trước nếu có,
  mốc được phép sau giờ yên lặng nếu policy yêu cầu
)

send_by = min(
  mốc gốc + độ trì hoãn tối đa,
  hạn xử lý nghiệp vụ - khoảng dẫn trước bắt buộc,
  hạn của nội dung/hành động liên quan,
  các hạn khác mà policy áp dụng
)

Chỉ có cửa sổ hợp lệ khi not_before < send_by.
~~~

Nếu quiet hours đẩy lịch qua send_by, không tự kéo dài deadline. Policy có thể bỏ lần nhắc, chọn kênh khác được phép hoặc tạo escalation riêng. Không để scheduler tự quyết định bỏ qua giờ yên lặng chỉ vì job đã quá hạn.

Ví dụ mốc gốc là 10:00, nhắc sớm nhất 10:10 và send_by là 10:12. Worker chạy lúc 10:11 có thể xét điều kiện gửi. Lúc 10:12 thì cửa sổ đã đóng theo quy tắc của bài. Nếu yêu cầu đã được duyệt lúc 10:07, cả hai trường hợp đều không còn đủ điều kiện nhắc.

### Debounce không được thành công cụ trì hoãn vô hạn

Nếu mỗi lần sửa hồ sơ đều đặt lịch “sau 5 phút kể từ lần sửa cuối”, người lạm dụng có thể sửa liên tục để cảnh báo không bao giờ phát ra. Giữ một mốc đầu của đợt thay đổi và giới hạn trì hoãn:

~~~text
candidate_at = min(
  last_relevant_change_at + debounce_window,
  first_pending_at + max_deferral
)
~~~

Sau đó áp dụng cửa sổ gửi và policy ưu tiên. Không đặt lại first_pending_at khi chỉ retry hoặc chỉnh sửa tiếp trong cùng đợt. Nếu đã hết cửa sổ, phải có kết quả EXPIRED hoặc escalation được định nghĩa, không âm thầm tạo mốc gốc mới.

Cooldown chống gửi dồn và debounce gom thay đổi có mục đích khác nhau. Cooldown không nên làm cảnh báo quan trọng bị mất không dấu vết; cần policy gom, nhắc bổ sung hoặc chuyển kênh rõ ràng.

## 5. Ghi trạng thái nghiệp vụ và ý định thông báo nguyên tử

Một lỗi phổ biến:

~~~text
gửi email "yêu cầu đã được duyệt"
sau đó UPDATE payout_request
sau đó transaction rollback
~~~

Người dùng đã nhận một khẳng định không còn đúng. Đổi thứ tự thành commit rồi gọi email cũng có khoảng hở: tiến trình có thể chết sau commit nhưng trước khi gửi.

Transactional outbox xử lý việc ghi dữ liệu và ý định phát sự kiện trong cùng transaction; consumer vẫn phải xử lý khả năng nhận trùng. [AWS Prescriptive Guidance: Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Một luồng local minh họa:

~~~text
BEGIN
  kiểm tra quyền trên yêu cầu chi
  kiểm tra expected revision và bước phê duyệt
  cập nhật trạng thái nghiệp vụ
  tăng notification_epoch khi cần vô hiệu hóa lịch cũ
  ghi domain event với event_id và aggregate_version
  ghi notification intent hoặc outbox để tạo intent
  ghi audit của command
COMMIT

Relay/consumer:
  chỉ xử lý event đã commit
  tạo intent idempotent nếu chưa tồn tại
  scheduler đánh thức theo lịch
  worker xét lại điều kiện trước khi cấp phép gửi
~~~

Callback after-commit trong bộ nhớ không tự tạo bảo đảm bền vững nếu tiến trình chết. Cần outbox hoặc cơ chế có bảo đảm tương đương được thiết kế rõ.

Nếu sự kiện đến từ dịch vụ ngoài, chỉ tạo thông báo kết quả sau khi hệ thống đã xác minh và áp dụng sự kiện hợp lệ. Không nhận một payload “paid=true” của client rồi gửi thông báo thành công trực tiếp.

### Chọn ngữ nghĩa snapshot hoặc trạng thái hiện tại

Với biên nhận lịch sử, nội dung có thể mô tả chính xác sự kiện đã xảy ra tại revision cụ thể. Với lời nhắc “vẫn cần bạn duyệt”, phải kiểm tra điều kiện hiện tại.

Do đó, không có quy tắc chung rằng mọi notification phải có revision bằng toàn bộ bản ghi hiện tại. Cần phân biệt:

- Sự kiện lịch sử vẫn được phép thông báo, với thời điểm và nội dung rõ.
- Lời khẳng định trạng thái hiện tại cần được kiểm tra lại.
- Lệnh mời thực hiện hành động cần cả điều kiện hiện tại lẫn hạn hiệu lực.

Nếu “yêu cầu bị hủy” đến trước một job “yêu cầu chờ duyệt”, dùng state/epoch để loại job chờ duyệt cũ. Không dựa vào timestamp client hay giả định queue luôn giữ thứ tự toàn hệ thống.

## 6. Mô hình intent và vòng đời gửi

Một notification intent nên giữ đủ thông tin để không phải suy lại danh tính và lịch theo dữ liệu tùy ý trong job:

| Trường | Mục đích |
| --- | --- |
| notification_id, logical_key | Danh tính lần thông báo cần thực hiện |
| tenant_id, aggregate_id, event_id | Ràng buộc tenant, đối tượng và sự kiện |
| notification_type, policy_version | Mục đích và quy tắc thời gian |
| notification_epoch | Thế hệ làm mất hiệu lực intent cũ |
| recipient_binding_id, binding_version | Người nhận và kênh đã được ràng buộc |
| occurrence_id | Danh tính một lần nhắc trong lịch |
| not_before, send_by, next_attempt_at | Cửa sổ và lịch thử lại |
| state, attempt_count | Tiến trình xử lý |
| lease_token, lease_until | Quyền tạm giữ job của worker |
| provider_operation_id | Liên kết với thao tác ở nhà cung cấp |

Không dùng địa chỉ email hoặc số điện thoại từ payload job làm nguồn quyết định cuối cùng. Lưu tham chiếu người nhận đã được kiểm soát và chính sách thay đổi kênh.

Một state machine minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> PLANNED
    PLANNED --> LEASED: Worker giữ job đến hạn
    LEASED --> PLANNED: Chưa đủ điều kiện thời gian, thử sau
    LEASED --> CANCELLED: Điều kiện hoặc người nhận không còn hợp lệ
    LEASED --> EXPIRED: Hết cửa sổ gửi
    LEASED --> SEND_PERMITTED: Kiểm tra cuối và cấp phép
    SEND_PERMITTED --> PROVIDER_ACCEPTED: Nhà cung cấp xác nhận nhận
    SEND_PERMITTED --> UNKNOWN: Timeout hoặc mất kết quả
    UNKNOWN --> RECONCILING: Tra cứu theo operation ID
    RECONCILING --> PROVIDER_ACCEPTED: Xác nhận đã tiếp nhận
    RECONCILING --> PLANNED: Xác nhận chưa gửi và còn cửa sổ
    RECONCILING --> EXPIRED: Xác nhận chưa gửi và đã hết hạn
~~~

Sơ đồ tập trung vào việc nộp yêu cầu gửi. Trạng thái delivery sau PROVIDER_ACCEPTED có thể được theo dõi riêng, không coi tiếp nhận đồng nghĩa người nhận đã đọc.

LEASED chỉ có nghĩa worker đang giữ job, không phải được phép tiết lộ dữ liệu. Hết lease có thể cho phép worker khác tiếp quản, nhưng cần fencing token và conditional update để worker cũ không cập nhật đè trạng thái mới. Token ở database không tự ngăn một lời gọi mạng đã bắt đầu; phần gửi ngoài hệ thống cần giao thức riêng.

## 7. Kiểm tra cuối trước khi cấp phép gửi

Một scheduler chỉ nên chọn các intent có khả năng đến hạn. Quyết định được gửi phải nằm trong một bước có kiểm soát trạng thái, quyền, lịch và cạnh tranh.

Đoạn Java dưới là mã giả tầng ứng dụng; các lớp và repository diễn tả hợp đồng cần triển khai, không phải chương trình hoàn chỉnh để biên dịch:

~~~java
PrepareResult prepareSubmission(NotificationId id, LeaseToken leaseToken) {
    return unitOfWork.inTransaction(() -> {
        NotificationIntent intent = notifications.lockById(id);

        if (intent.isFinalForSubmission()) {
            return PrepareResult.noop(intent.state());
        }
        if (intent.hasUnresolvedProviderOperation()) {
            return PrepareResult.reconcile(intent.providerOperationId());
        }

        BusinessObject subject = subjects.lockByTenantAndId(
            intent.tenantId(), intent.aggregateId());
        RecipientBinding recipient = recipients.lockBinding(
            intent.recipientBindingId());

        NotificationPolicy policy = policies.forType(intent.type());
        // Các đường đổi trạng thái/quyền dùng cùng giao thức khóa/version.
        Eligibility eligibility = policy.evaluateCurrent(
            intent, subject, recipient);

        // Lấy thời gian sau các bước có thể phải chờ khóa.
        Instant now = trustedClock.instant();
        intent.requireActiveLease(leaseToken, now);

        if (!eligibility.allowed()) {
            intent.cancel(eligibility.reasonCode());
            auditRepository.insertCancelled(intent, now);
            return PrepareResult.cancelled();
        }

        SendWindow window = policy.currentWindow(intent, recipient);
        if (!window.notBefore().isBefore(window.sendBy())
                || !now.isBefore(window.sendBy())) {
            intent.expire("WINDOW_CLOSED");
            auditRepository.insertExpired(intent, now);
            return PrepareResult.expired();
        }

        if (now.isBefore(window.notBefore())) {
            intent.deferUntil(window.notBefore());
            return PrepareResult.deferred(window.notBefore());
        }

        BudgetDecision budget = quotas.reserveOnce(
            intent.logicalKey(), intent.tenantId(), recipient, policy, now);
        if (!budget.allowed()) {
            return rescheduleOrExpire(intent, budget.nextEligibleAt(), window);
        }

        SubmissionPacket packet = templates.renderSafePacket(
            intent, subject, recipient, policy);
        SendPermit permit = permits.createOnce(
            intent, packet.fingerprint(), window.sendBy(), now);

        intent.markSendPermitted(permit.operationId());
        submissionPackets.saveProtected(permit.operationId(), packet);
        auditRepository.insertPermitted(intent, permit, now);
        return PrepareResult.permitted(permit.operationId());
    });
}
~~~

Trong ví dụ, entity được theo dõi và lưu bởi unit of work. Cập nhật intent, quota, permit và audit phải commit cùng nhau. Nếu ORM không tự quản lý thay đổi, phải gọi các thao tác save tương ứng; không coi mã giả là chi tiết triển khai đầy đủ.

Eligibility kiểm tra tenant, điều kiện kích hoạt, notification epoch và chính sách người nhận. currentWindow không được kéo dài giới hạn trì hoãn gốc chỉ vì preference vừa thay đổi. Nếu quyền hoặc policy nằm ở dịch vụ ngoài, một lần đọc từ xa không tạo tính nguyên tử; cần version, lease hoặc giao thức thu hồi rõ ràng.

SubmissionPacket là nội dung và đích nhận đã ràng buộc với permit, được lưu có bảo vệ. Không để worker giữ một operation ID nhưng tự thay body, recipient hoặc template trước khi gọi nhà cung cấp. Tuy nhiên, packet đã chuẩn bị cũng không tự có quyền gửi vô thời hạn.

Hệ thống gửi đọc packet sau commit, áp dụng giao thức permit và gọi nhà cung cấp ngoài transaction. Không giữ khóa dữ liệu nghiệp vụ qua lời gọi email/SMS/push.

### Hủy và cấp phép gửi phải có điểm tuần tự hóa

Nếu worker đọc “đang chờ duyệt”, sau đó yêu cầu được duyệt, rồi worker mới gửi, việc kiểm tra đơn thuần vẫn có race.

Thiết kế có thể tuần tự hóa command hủy và bước cấp permit theo cùng đối tượng bằng khóa hoặc coordinator. Khi hoàn thành nghiệp vụ trước điểm cấp permit, intent cũ bị hủy hoặc epoch không khớp. Khi permit đã được cấp trước, attempt đó có thể đang tiến hành.

Do vậy, cam kết local của ví dụ là:

~~~text
Không cấp send permit mới sau khi hủy có hiệu lực.
Attempt đã có permit trước đó được ghi nhận và xử lý theo policy.
~~~

Không thể thu hồi byte đã gửi hoặc bảo đảm xóa một tin mà nhà cung cấp đã nhận chỉ bằng cập nhật database. Nếu sản phẩm hứa “khi API hủy trả về thì không còn attempt đang gửi”, cần cơ chế drain hoặc gateway gửi có phối hợp và xử lý worker treo. Khả năng hủy ở nhà cung cấp cũng phải được xác nhận, không giả định.

Tương tự, kiểm tra send_by lúc cấp permit chỉ bảo đảm điểm cấp permit. Nếu yêu cầu không được bắt đầu lời gọi mạng sau send_by, cổng gửi phải kiểm tra tại điểm thực thi và không sử dụng permit hết hạn. Tiến trình có thể bị dừng giữa hai bước; cần nêu rõ mức bảo đảm thay vì tuyên bố chỉ một câu if đã kiểm soát thời gian giao tin toàn hệ thống.

### Lease và fencing có giới hạn

Lease hết không có nghĩa lời gọi bên ngoài chưa chạy. Worker mới không được tạo operation mới chỉ vì không thấy trạng thái thành công local. Fencing token bảo vệ cập nhật dữ liệu local; chống lặp bên ngoài cần idempotency hoặc đối soát với nhà cung cấp.

Nếu deadline đã qua trong lúc vẫn chưa biết kết quả, giữ dấu vết UNKNOWN/RECONCILING. Có thể đóng quyền thử mới nhưng không được kết luận “chưa gửi” khi chưa có bằng chứng.

## 8. Người nhận và nội dung có thể thay đổi trong thời gian chờ

Địa chỉ đã hợp lệ lúc tạo intent có thể không còn phù hợp lúc gửi: người duyệt rời tổ chức, số điện thoại được đổi hoặc chủ sở hữu đối tượng thay đổi.

Với nhắc phê duyệt, policy có thể yêu cầu người nhận vẫn được xem và duyệt chính yêu cầu đó. Không gửi danh sách tài khoản ngân hàng hoặc số tiền cho người vừa bị gỡ quyền chỉ vì job cũ đã chứa dữ liệu.

Không tự chuyển mọi intent cũ sang email mới nhất. Người lạm dụng có thể đổi địa chỉ để chuyển hướng thông báo nhạy cảm đã được tạo trước đó. Thay kênh có thể cần xác minh, tăng binding version, hủy intent cũ và tạo intent mới qua command được kiểm tra quyền.

Một ngoại lệ có chủ đích là cảnh báo thay đổi thông tin bảo mật qua kênh cũ đã xác minh. Khi đó, policy phải ràng buộc kênh trước thay đổi, giới hạn thời gian và nội dung; không dùng quy tắc “luôn gửi đến kênh hiện tại” khiến cảnh báo bị chuyển sang kênh do kẻ tấn công vừa thêm.

### Render sớm hay render muộn?

| Cách render | Ưu điểm | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Chụp nội dung lúc tạo intent | Giữ nội dung lịch sử nhất quán | Dữ liệu nhạy cảm nằm lâu trong queue; lời nhắc có thể lỗi thời |
| Render sát lúc gửi | Dùng dữ liệu và quyền hiện tại | Có thể biến một sự kiện cũ thành khẳng định sai về hiện tại |
| Kết hợp | Giữ ID/snapshot tối thiểu, render theo loại | Cần hợp đồng rõ cho trường lịch sử và trường hiện tại |

Với biên nhận, giữ dữ kiện của giao dịch đã xảy ra, không thay số tiền bằng giá trị hiện tại của hồ sơ. Với nhắc việc, kiểm tra nhiệm vụ vẫn tồn tại và còn cần hành động. Trong cả hai trường hợp, chỉ công bố các trường mà người nhận được phép biết theo policy tương ứng.

Nội dung tối thiểu cùng liên kết đến trang cần xác thực thường giảm tác hại nếu tin đến muộn. Trang đích vẫn kiểm tra quyền và trạng thái; không cho phép thông tin trong subject hoặc push preview vượt chính sách chỉ vì body được bảo vệ tốt hơn.

## 9. Múi giờ, giờ yên lặng và lịch lặp

“Sau 24 giờ” và “9 giờ sáng ngày mai theo múi giờ người nhận” là hai quy tắc khác nhau. Một quy tắc dựa trên thời lượng; quy tắc còn lại dựa trên lịch địa phương.

Lưu thời điểm thực thi dưới dạng Instant/UTC, đồng thời giữ ZoneId và ý định lịch khi cần. Chỉ lưu offset như +07:00 không đủ để diễn tả một lịch lặp ở nơi có quy tắc đổi giờ.

Java ZonedDateTime phân biệt thời điểm địa phương bình thường, gap không có offset hợp lệ và overlap có hai offset hợp lệ. Các phép chuyển đổi có hành vi mặc định; sản phẩm cần chọn chính sách phù hợp thay vì vô tình dựa vào mặc định thư viện. [Java SE 21: ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html).

Với một lịch “02:30 địa phương”, cần trả lời:

- Nếu ngày đó không có 02:30, bỏ lần gửi hay dời đến mốc hợp lệ nào?
- Nếu có hai lần 02:30, chọn offset nào và tạo bao nhiêu occurrence?
- Nếu người dùng đổi timezone, lịch đã tạo có được tính lại không?
- Nếu dữ liệu timezone thay đổi, những lịch tương lai nào được tái tính?
- Việc dời giờ có vượt send_by hoặc hạn xử lý nghiệp vụ không?

Một occurrence_id phải đại diện cho một lần nghiệp vụ trong lịch, không phải phút mà worker tình cờ chạy. Khi tính lại lịch, giữ hoặc chuyển thế hệ occurrence một cách có kiểm soát để không gửi cả bản cũ lẫn bản mới.

### Không cho preference trở thành quyền trì hoãn cảnh báo

Người dùng có thể được chọn giờ nhận nội dung tùy chọn, nhưng không mặc nhiên được dời cảnh báo bảo mật ra ngoài độ trễ tối đa. Thay timezone liên tục không được đặt lại mốc sự kiện hoặc first_pending_at.

Giờ yên lặng cần được xét theo phiên bản preference và policy. Nếu cho thay đổi lịch, command phải kiểm tra expected revision và audit. Không nhận chuỗi timezone không hợp lệ rồi rơi về timezone mặc định của máy chủ.

Việc bỏ qua giờ yên lặng cho loại cảnh báo quan trọng phải do policy máy chủ phân loại, có quyền cấu hình riêng. Không cho nội dung tùy chọn tự gắn nhãn ưu tiên cao để vượt hạn mức.

Theo dõi sai lệch đồng hồ giữa worker và nguồn thời gian tin cậy. Dùng đồng hồ đơn điệu để đo timeout trong tiến trình, nhưng không lưu giá trị đơn điệu làm lịch dùng chung giữa máy hoặc sau restart. Đồng hồ bị lùi không được âm thầm mở lại cửa sổ đã hết hạn.

## 10. Retry, idempotency và phục hồi sau gián đoạn

Một logical key minh họa:

~~~text
tenant_id
+ aggregate_id
+ notification_type
+ event_id hoặc occurrence_id
+ recipient_binding_id
+ channel
+ notification_generation
~~~

Khóa cụ thể tùy loại tin, nhưng phải mô tả “một lần cần gửi” ổn định. Không đưa attempt_count hoặc thời điểm worker hiện tại vào khóa để mỗi retry trở thành một thông báo mới.

Consumer tạo intent bằng unique constraint trên logical key hoặc cơ chế tương đương. Cùng event nhận hai lần phải trỏ đến một intent, không tạo hai email. Resend có chủ đích là command riêng, có quyền, quota và lý do; không giả mạo nó thành retry hạ tầng.

### Không gia hạn cửa sổ bằng retry

~~~text
next_attempt_at = now + backoff

Nếu next_attempt_at >= send_by:
  không lên lịch attempt mới trong cửa sổ đã đóng
  ghi kết quả hoặc escalation theo policy
~~~

Retry vẫn kiểm tra điều kiện nghiệp vụ, quyền người nhận và epoch. Không được có đường “retry chỉ gọi provider” bỏ qua kiểm tra cuối.

Khi nhà cung cấp hỗ trợ idempotency, giữ operation key ổn định cho cùng thao tác nộp tin và payload fingerprint tương ứng. Hiểu rõ thời hạn giữ key và ý nghĩa kết quả của nhà cung cấp. Không đổi key khi timeout nếu thao tác cũ có thể đã được nhận.

Nếu không có idempotency hoặc tra cứu đáng tin, không thể chỉ bằng outbox và một cột sent tạo ra bảo đảm giao đúng một lần xuyên hai hệ thống. Cần chính sách cho UNKNOWN: đối soát, xem xét thủ công hoặc chấp nhận nguy cơ trùng có giới hạn tùy loại tin.

Bản ghi intent và dấu vết dedup cần được giữ đủ lâu theo replay horizon của hệ thống. Xóa dấu vết xong chạy lại event cũ có thể tạo lại thông báo. Việc lưu không cần đồng nghĩa giữ payload nhạy cảm lâu như metadata chống trùng.

### Sau khi scheduler ngừng nhiều giờ

Không phát tất cả lần nhắc đã lỡ như một cơn bão thông báo. Theo loại nội dung, có thể bỏ các occurrence hết hạn, gom thành một bản tóm tắt được phép hoặc chỉ tạo lần tiếp theo còn có ích.

Tin cảnh báo quan trọng bị lỡ cần kết quả và escalation riêng, không âm thầm bỏ đi. Nội dung “vừa xảy ra” phải phản ánh thời điểm thật nếu được gửi muộn, tránh khiến người dùng hiểu sai sự kiện mới phát sinh.

Chạy lại dead-letter queue cũng là một đường thực thi cần quyền và audit. Nó phải giữ hạn và thế hệ gốc, không lấy now làm mốc mới để làm job cũ hợp lệ trở lại.

Hạn mức nên xét theo tenant, đối tượng, người nhận và kênh. Cooldown theo IP đơn lẻ không ngăn một tài khoản lạm dụng notification cho nhiều địa chỉ, và cũng có thể chặn nhầm nhiều người dùng chung mạng.

## 11. Liên kết hành động và khác biệt thời gian phản hồi

### Liên kết còn hạn khi được gửi chưa đủ

Một lời mời hoặc link xác minh có thể còn hạn lúc enqueue nhưng hết hạn trước khi gửi. Policy cần giữ khoảng thời gian tối thiểu còn lại đủ hữu ích; nếu không đủ, hủy hoặc tạo lời mời mới qua quy trình có quyền, không tự sửa expiry của token cũ.

Token mới cũng không nên được sinh vô hạn trong mỗi retry. Nếu cần phát hành lại, ràng buộc với thế hệ yêu cầu mới, vô hiệu hóa token cũ khi phù hợp và ghi audit. Queue bảo vệ dữ liệu bí mật; tránh đưa token vào log, metric label hoặc lỗi của nhà cung cấp.

Tại lúc dùng token, máy chủ kiểm tra hạn bằng thời gian tin cậy, ràng buộc người/đối tượng/hành động và tiêu thụ một lần nguyên tử với hiệu ứng nghiệp vụ. Không tin thời điểm bấm do trình duyệt gửi.

Một email nhắc phê duyệt đến sau khi đơn đã hoàn tất phải mở trang trạng thái hiện tại. Nó không được gọi lại lệnh phê duyệt chỉ vì template chứa một URL cũ.

### Thời gian phản hồi API có thể tiết lộ thông tin

Ở luồng khôi phục tài khoản, việc tài khoản tồn tại thì gọi dịch vụ gửi tin rồi mới trả lời, còn không tồn tại thì trả ngay, có thể tạo kênh dò tài khoản.

OWASP khuyến nghị phản hồi nhất quán về nội dung và thời gian cho yêu cầu khôi phục, cùng token dùng một lần có thời hạn. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Có thể tách xử lý bất đồng bộ và tránh nhánh thoát sớm quan sát được, đồng thời kiểm thử phân bố thời gian. Thêm jitter tùy ý không sửa triệt để một chênh lệch lớn có thể đo lặp lại. Không dùng sleep dài cho mỗi request để che khác biệt rồi tạo lỗ hổng cạn tài nguyên.

Job status hoặc API tra cứu notification cũng không được tiết lộ “địa chỉ này có tài khoản” cho caller chưa có quyền. Đổi toàn bộ công việc sang queue nhưng để endpoint polling trả hai trạng thái khác biệt vẫn có thể giữ nguyên kênh rò rỉ.

Giới hạn tần suất theo ngữ cảnh phù hợp để chống spam và notification bombing. Quyền yêu cầu khôi phục không đồng nghĩa quyền đọc số điện thoại, email đầy đủ hoặc nội dung job nội bộ.

## 12. Audit thời gian và quan sát vận hành

Audit nên giải thích vì sao một tin được gửi, hoãn, hủy hoặc hết hạn, không chỉ ghi “sent=true”.

| Nhóm | Dữ liệu hữu ích |
| --- | --- |
| Nguồn nghiệp vụ | Tenant, object ID, event ID, phiên bản/epoch |
| Mục đích | Notification type, logical key, occurrence ID |
| Người nhận | Binding ID/version và phạm vi quyền đã xét |
| Thời gian | not_before, send_by, next_attempt_at, permitted_at |
| Policy | Policy version, timezone/preference version, lý do ngoại lệ |
| Thực thi | Lease/attempt ID, provider operation ID, trạng thái xác nhận |
| Quyết định | DEFERRED, CANCELLED, EXPIRED, PERMITTED, UNKNOWN và reason code |
| Liên kết | Request ID, command ID, audit ID, trace ID |

Không ghi token, toàn bộ nội dung tài chính hoặc địa chỉ liên hệ đầy đủ vào mọi record. Tách metadata audit khỏi packet chứa nội dung nhạy cảm, phân quyền xem/export theo tenant và vai trò.

Các metric đáng theo dõi:

- Độ trễ từ sự kiện đã được lưu đến lúc cấp permit.
- Tỷ lệ xử lý trước not_before hoặc sau send_by theo loại thông báo.
- Số job bị hủy vì hoàn tất nghiệp vụ, đổi quyền hoặc đổi người nhận.
- Số lần retry, duplicate, UNKNOWN và thời gian ở RECONCILING.
- Độ trễ outbox, scheduler, provider và callback riêng biệt.
- Số cảnh báo vượt độ trễ tối đa hoặc bị hoãn bởi preference.
- Tốc độ tạo notification và các trường hợp chạm quota.

Không trộn provider accepted với delivered hoặc read trong dashboard. Một hệ thống có tỷ lệ tiếp nhận cao vẫn có thể gửi quá muộn, gửi sai ngữ cảnh hoặc để cảnh báo quan trọng nằm trong queue.

Thay đổi policy thời gian cũng là thay đổi nghiệp vụ cần kiểm soát: ai đổi, loại tin nào bị ảnh hưởng, áp dụng từ lúc nào và lịch đang chờ có được tính lại không. Không sửa lịch trực tiếp bằng SQL rồi để audit chỉ còn dấu vết của worker gửi.

## 13. Kiểm thử tình huống tấn công logic

Dùng clock có thể điều khiển, fake provider và barrier/latch để sắp thứ tự cạnh tranh. Không chỉ thêm sleep rồi hy vọng race xảy ra. Mỗi ca cần kiểm tra dữ liệu, intent, audit và số lần gọi provider.

| Tình huống | Cách thử | Kết quả cần khẳng định |
| --- | --- | --- |
| Gửi trước commit | Giữ transaction tạo yêu cầu chưa commit, chạy relay | Không có thông báo bên ngoài |
| Rollback | Gây lỗi sau khi tạo intent trong transaction | Trạng thái và intent cùng rollback |
| Nhầm phê duyệt với chi trả | Hoàn tất bước duyệt nhưng chưa xác nhận thanh toán | Không có tin “đã chi trả” |
| Chưa đến giờ | Đánh thức worker ngay trước not_before | Không cấp permit, lịch không bị rút ngắn |
| Biên thời hạn | Thử ngay trước, đúng và sau send_by | Đúng biên loại trừ đã công bố |
| Đã hoàn tất nhiệm vụ | Duyệt trước giờ nhắc rồi chạy job cũ | Intent bị hủy, không gọi provider |
| Race duyệt và gửi | Dùng barrier quanh bước cấp permit và command duyệt | Hành vi đúng điểm tuần tự hóa, audit rõ attempt đã cấp |
| Mất quyền sau lập lịch | Gỡ người duyệt khỏi phạm vi đối tượng | Không gửi dữ liệu cho người đã mất quyền |
| Sai tenant | Sửa ID job hoặc recipient binding sang tenant khác | Không đọc/sửa/gửi dữ liệu tenant kia |
| Đổi địa chỉ nhận | Thay contact sau khi intent đã tạo | Không tự chuyển dữ liệu nhạy cảm trái policy |
| Trì hoãn bằng debounce | Sửa liên tục trước mỗi mốc debounce | Không vượt max_deferral không dấu vết |
| Đổi timezone để trì hoãn | Thay preference nhiều lần | Mốc gốc và hạn tối đa không bị đặt lại |
| Gap/overlap lịch địa phương | Dùng zone và ngày có giờ thiếu/lặp trong bộ dữ liệu thử | Một occurrence theo policy, không gửi hai lần ngoài ý muốn |
| Hai worker | Cùng claim hoặc gửi cùng logical notification | Một hiệu ứng local; xử lý provider theo idempotency |
| Worker cũ sau hết lease | Worker mới tiếp quản, worker cũ quay lại | Fencing chặn cập nhật cũ; không tạo operation mới bừa |
| Provider nhận rồi timeout | Fake provider nhận tin nhưng làm mất response | UNKNOWN/đối soát, không tự đổi operation key |
| Retry sau hạn | Backoff vượt send_by | Không gia hạn cửa sổ |
| Scheduler phục hồi | Tích nhiều occurrence quá hạn rồi khởi động lại | Không phát bão nhắc; kết quả bỏ/gom/escalate rõ |
| Dead-letter replay | Chạy lại job thuộc epoch đã hủy | Không làm sống lại thông báo |
| Token hết hạn trong queue | Để link hết hạn trước khi gửi | Không gửi link như thể còn dùng được |
| Link cũ sau hoàn tất | Mở email nhắc sau khi đơn đã xử lý | API không thực hiện lại hành động |
| Giả ưu tiên | Client gửi cờ bypass_quiet_hours hoặc CRITICAL | Không vượt policy máy chủ |
| Timing enumeration | Đo nhiều request cho tài khoản có/không tồn tại | Không có chênh lệch đáng tin cho phép dò từ luồng này |
| Đồng hồ bị lùi | Điều khiển clock vượt giới hạn tin cậy | Không mở lại cửa sổ đã đóng âm thầm |

Với ca request trùng, kiểm tra cả unique logical key, số permit, quota đã chiếm và số operation ở provider. Hai response HTTP thành công có thể hợp lệ nếu cùng tham chiếu một hiệu ứng; điều cần ngăn là gửi thêm ngoài chủ đích.

Với ca provider timeout, không kết luận từ số record local. Fake provider cần giữ sổ operation để chứng minh hệ thống có thể đã gửi dù transaction cập nhật kết quả chưa chạy.

Các ca liên quan email/SMS/push dùng người nhận và hạ tầng thử nghiệm do nhóm kiểm soát, không cần gửi dữ liệu thật cho bên thứ ba để kiểm chứng bất biến.

## 14. Phân tích lỗi “nhắc duyệt sau khi đã duyệt”

Thiết kế ban đầu ghi một job gồm payout ID, email và send_at. Worker chỉ chờ đến giờ rồi gửi. Khi người dùng duyệt yêu cầu, ứng dụng đổi trạng thái nhưng không vô hiệu hóa job.

Vấn đề không chỉ là thiếu một câu lệnh xóa job:

1. Job có thể đã được worker giữ hoặc đã rời scheduler.
2. Email trong payload có thể không còn là kênh được phép.
3. Duyệt và gửi có thể chạy đồng thời.
4. Retry hoặc dead-letter có thể đưa job đã xóa trở lại.
5. Nhà cung cấp có thể đã nhận tin dù ứng dụng chưa ghi kết quả.

Hướng sửa cần kết hợp notification epoch, policy người nhận, cửa sổ gửi, bước cấp phép có kiểm soát cạnh tranh và idempotency. Command duyệt tăng epoch hoặc hủy intent liên quan trong transaction. Worker kiểm tra lại ngay trước điểm cấp permit. Job cũ quay lại sẽ không vượt được state/epoch hiện tại.

Nếu permit đã được cấp trước khi duyệt, audit phải chỉ ra attempt đó, thời điểm tiếp nhận ở provider và giới hạn hủy của kênh. Nội dung và API hành động vẫn phải an toàn khi tin đến muộn. Không viết lại lịch sử để trình bày rằng mọi tin cũ chắc chắn đã được thu hồi.

## 15. Tiêu chí hoàn thành thiết kế

- Mỗi loại thông báo có sự kiện kích hoạt, cửa sổ gửi, điều kiện hủy và hành vi khi bỏ lỡ lịch.
- Thông báo không khẳng định vượt quá trạng thái nghiệp vụ đã được chấp nhận và lưu bền vững.
- Worker kiểm tra lại tenant, điều kiện, người nhận, epoch và thời gian, không chỉ dựa vào lịch.
- Hủy và cấp permit có điểm tuần tự hóa rõ; attempt đã gửi ra ngoài được xử lý theo khả năng thực tế.
- Retry, resend, replay và khôi phục scheduler giữ đúng logical identity, deadline và quota.
- Preference, quiet hours, debounce và timezone không tạo đường trì hoãn vô hạn hoặc vượt ưu tiên.
- Token và hành động trong tin luôn được kiểm tra ở máy chủ khi sử dụng.
- Provider accepted, delivered và read được phân biệt trong dữ liệu và báo cáo.
- Audit đủ giải thích quyết định thời gian mà không tạo thêm nguồn rò rỉ bí mật.
- Kiểm thử bao phủ rollback, cạnh tranh, hết hạn, thay quyền, notification bombing và rò rỉ qua thời gian phản hồi.
