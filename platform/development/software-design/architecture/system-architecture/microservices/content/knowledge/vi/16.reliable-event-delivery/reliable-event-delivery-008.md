# Dọn dữ liệu outbox, inbox và bảo toàn khả năng xử lý lại

## 1. Bối cảnh: dữ liệu truyền sự kiện không thể giữ mãi, nhưng xóa quá sớm có thể làm mất tính đúng đắn

Trong kiến trúc microservices, một service có thể ghi thay đổi nghiệp vụ vào database và công bố sự kiện cho những service khác. Cặp **transactional outbox** và **inbox/idempotent consumer** là cách thông dụng để giảm rủi ro mất message và xử lý trùng khi hệ thống có lỗi mạng hoặc tiến trình bị khởi động lại.

Ví dụ:

    Order Service                       Broker                 Analytics
    ------------------------------      -----------------      ----------------
    DB transaction:
      update Order=CONFIRMED
      insert Outbox(OrderConfirmed)
                |
                v
    Outbox Publisher --publish/ACK-----> topic -------------> Consumer
            |                                               DB transaction:
            |                                                 update projection
            +--mark published                                 insert Inbox(eventId)
                                                               commit
                                                               |
                                                               v
                                                             ACK offset

Một tuần sau, bảng outbox có hàng triệu bản ghi đã gửi; bảng inbox của Analytics có hàng trăm triệu eventId. Nhóm vận hành muốn dọn để giảm chi phí lưu trữ, bloat index, thời gian backup và độ chậm của truy vấn.

Tuy nhiên:
- Một outbox record chưa được broker xác nhận có thể là **bản duy nhất** giữ nghĩa vụ phát sự kiện sau transaction nghiệp vụ.
- Một event đã được publish có thể cần **replay/backfill** để khôi phục consumer, xây lại projection hoặc điều tra sự cố.
- Một event đã xử lý ở consumer có thể lại xuất hiện do retry, broker redelivery, restore từ backup, DLQ replay hoặc tác vụ phát lại thủ công.
- Nếu xóa inbox marker quá sớm, một event cũ có thể được coi là mới và tạo tác dụng phụ lặp.
- Nếu xóa event gốc mà không có archive/snapshot đủ nghĩa, hệ thống có thể không còn cách xây lại trạng thái.

Vì vậy, **dọn dữ liệu không chỉ là câu lệnh DELETE theo created_at**. Đó là một quyết định về bằng chứng xử lý, giới hạn replay, phạm vi chống trùng, chính sách phục hồi, dữ liệu cá nhân và trách nhiệm vận hành.

### Mục tiêu học tập

Sau bài, bạn có thể:
1. Phân biệt vai trò và vòng đời của outbox, inbox, broker log, DLQ, snapshots, checkpoints và audit log.
2. Xác định điều kiện được xóa hoặc lưu trữ mỗi loại bản ghi mà không làm mất nghĩa vụ phát/xử lý.
3. Thiết kế **retention window** theo thời gian message có thể xuất hiện lại và yêu cầu khôi phục.
4. Bảo vệ idempotency khi dọn inbox hoặc phát lại event lịch sử.
5. Lập quy trình archive, partition, batch cleanup và monitoring an toàn.
6. Tổ chức replay/backfill có khả năng resume sau crash, xử lý version, ordering và dữ liệu lịch sử.
7. Xử lý ngoại lệ như consumer ngừng nhiều tuần, poison message, event tới muộn, database restore và yêu cầu xóa dữ liệu nhạy cảm.
8. Xây chiến lược thử nghiệm lỗi, ADR và runbook để việc dọn dữ liệu có thể audit và khôi phục.

---

## 2. Phân biệt những kho dữ liệu dễ bị gọi chung là “bảng sự kiện”

Không nên xây một cron job xóa tất cả các bảng có chữ event hoặc message. Mỗi kho phục vụ một mục đích khác nhau.

| Thành phần | Mục đích | Khi nào bản ghi có thể an toàn để xóa? |
|---|---|---|
| **Outbox** | Ghi bền vững ý định phát message cùng transaction nghiệp vụ | Sau khi có bằng chứng publish theo contract, và không còn cần giữ cho replay/audit theo chính sách |
| **Inbox / processed-event ledger** | Ghi message đã xử lý để chống effect trùng ở consumer | Khi mọi cách xuất hiện lại nằm ngoài phạm vi hỗ trợ hoặc đã có cơ chế chống trùng thay thế |
| **Broker topic/log** | Truyền và lưu message theo retention của broker | Theo chính sách broker và khả năng replay được cam kết; không phụ thuộc đơn giản vào outbox |
| **DLQ/quarantine** | Giữ message xử lý lỗi để điều tra hoặc phát lại | Sau khi đã xử lý, archive hoặc hết hạn theo quy trình sự cố |
| **Consumer offset/checkpoint** | Ghi tiến độ đọc theo partition/stream | Chỉ được đổi khi không làm bỏ qua message còn cần xử lý |
| **Projection/read model** | Lưu trạng thái phục vụ đọc do event tạo ra | Theo vòng đời read model và khả năng rebuild |
| **Event archive** | Giữ nguồn lịch sử cho replay, audit hoặc đối soát | Theo cam kết khôi phục, bảo mật và thời hạn lưu |
| **Audit/ledger nghiệp vụ** | Bằng chứng giao dịch hoặc nghĩa vụ pháp lý | Theo chính sách dữ liệu riêng; không được đánh đồng với outbox/inbox |

Một outbox không mặc nhiên là event store hoàn chỉnh. Nếu hệ thống muốn hỗ trợ rebuild từ nhiều năm trước, cần thiết kế nguồn lịch sử phù hợp: event store thật, archive đủ nghĩa, snapshot + delta hoặc một API snapshot có thẩm quyền.

Một inbox không phải nguồn sự thật nghiệp vụ. Nó thường chỉ lưu dấu “event X đã được xử lý theo một mục đích nhất định” để tránh xử lý lại ngoài ý muốn.

### 2.1. Tại sao chỉ nhìn trạng thái SENT chưa đủ?

Một outbox record được đánh dấu SENT có thể có nghĩa:
- Publisher đã gọi API gửi.
- Broker đã xác nhận nhận message bền vững theo cấu hình.
- Một relay chỉ ghi rằng message đã đưa vào buffer.
- Một operator chủ động đánh dấu bỏ qua sau sự cố.

Những nghĩa này không tương đương. Hợp đồng cleanup cần định nghĩa **bằng chứng xác nhận được chấp nhận**, ví dụ kết quả publish ACK đúng cấu hình của broker, kèm lưu ý rằng ACK của broker **không chứng minh tất cả consumer đã xử lý thành công**.

### 2.2. Dedupe của inbox cũng có phạm vi

Một processed-event marker có thể áp dụng cho:
- Từng consumer group.
- Từng handler nghiệp vụ.
- Từng phiên bản projection.
- Từng tenant.
- Từng loại side effect.

Nếu hai handler độc lập cùng đọc eventId, chúng không được tùy tiện chia một marker khiến handler A xử lý xong rồi handler B bỏ qua. Khóa dedupe phải bao gồm phạm vi xử lý thực sự.

---

## 3. Transactional outbox bảo đảm điều gì?

Trong một transaction cục bộ:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE tenant_id = :tenantId
  AND order_id = :orderId
  AND status = 'PENDING_PAYMENT'
  AND version = :expectedVersion;

-- Chỉ tiếp tục khi thao tác Order thực sự thành công.
INSERT INTO outbox (
    event_id,
    aggregate_id,
    aggregate_version,
    event_type,
    payload,
    publish_status,
    created_at
) VALUES (
    :eventId,
    :orderId,
    :aggregateVersion,
    'OrderConfirmed',
    :payload,
    'NEW',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Nếu update Order và insert outbox nằm trong cùng transaction phù hợp, có thể đảm bảo rằng khi thay đổi nghiệp vụ được commit, ý định phát event cũng được lưu bền vững. Khi database rollback, outbox tương ứng cũng không có hiệu lực.

Publisher đọc record, gửi tới broker rồi ghi lại bằng chứng publish. Vì hai bước gửi broker và cập nhật DB không có transaction nguyên tử tự động, tình huống sau luôn phải được xét:

    Publisher gửi Event E thành công
    Broker xác nhận E
    Publisher crash trước khi ghi SENT vào outbox
    Publisher restart, nhìn E còn NEW
    Publisher gửi lại E

Đó là lý do **at-least-once publication + idempotent consumption** là thiết kế thường gặp. Xóa outbox trước khi có xác nhận publish có thể mất event; giữ và retry có thể tạo duplicate. Chống trùng là một phần contract.

### 3.1. Outbox không tạo exactly-once toàn hệ thống

Ngay cả khi publisher và broker có một số cơ chế transaction, side effect tại consumer hoặc hệ ngoài có thể vượt phạm vi transaction ấy. “Message được gửi một lần” không đồng nghĩa một email, khoản thu hoặc shipment được thực hiện đúng một lần trong thế giới bên ngoài.

Sự an toàn cần được xây xuyên suốt:
- Event ID bền vững, không thay trên retry.
- Consumer dedup hoặc business idempotency.
- State transition có điều kiện.
- Transaction cục bộ nơi owner quyết định.
- Đối soát các hiệu ứng ngoài transaction.

### 3.2. Đừng phát một event mới khi chỉ retry publish

Nếu outbox eventId=evt-123 được gửi lại vì ACK bị mất, nó vẫn phải được nhận diện là **cùng một event**, không tạo eventId khác chỉ vì publisher gọi API lần hai.

Một phiên bản event mới chỉ hợp lệ nếu nó biểu diễn một sự thật nghiệp vụ mới hoặc contract cho phép tạo một bản sửa đổi mới rõ nghĩa, không phải một lần thử truyền tải.

---

## 4. Inbox bảo đảm điều gì và giới hạn của nó ở đâu?

Giả sử Analytics nhận OrderConfirmed từ broker. Consumer ghi projection rồi lưu dấu message đã xử lý.

Một pattern:

~~~text
receive message(eventId=evt-123)
  begin local DB transaction
    try INSERT processed_event(eventId, handlerScope)
    if unique conflict:
        commit/rollback according to implementation
        ACK without business side effect
        return
    validate event and aggregate version
    apply projection changes
  commit
  ACK broker offset/message
~~~

Dấu processed-event và side effect cục bộ phải được ghi trong **cùng transaction** khi có thể. Unique constraint trên khóa dedupe bảo vệ hai worker xử lý cùng event đồng thời.

Nếu consumer commit DB rồi crash trước khi ACK broker, broker có thể giao lại. Inbox phát hiện eventId đã xử lý và bỏ qua effect, sau đó ACK.

Nếu consumer ACK trước khi commit DB mà process crash, message có thể bị coi đã xử lý dù dữ liệu chưa cập nhật. Do đó cần quyết định đúng thứ tự và cơ chế at-least-once.

### 4.1. Inbox marker là một lời khẳng định theo phiên bản xử lý

Một event có thể đã được Handler V1 xử lý nhưng Handler V2 cần tái áp dụng để xây một projection khác. Không nên có một marker toàn cục “evt-123 đã xử lý” làm mọi phiên bản tương lai bỏ qua.

Dedupe key có thể gồm:

    (consumer_name, handler_or_projection_version, event_id)

hoặc một namespace/job ID do contract quy định. Chọn scope theo bản chất side effect, không chỉ theo tên class Java.

### 4.2. Inbox cleanup có thể làm mất an toàn chống trùng

Giả sử marker evt-123 bị xóa sau 7 ngày. Ngày thứ 30, một operator replay các event trong DLQ cũ; consumer nhìn thấy evt-123 như mới và thực hiện lại bước tạo shipment.

Nếu đã xóa marker, ít nhất một trong các điều sau phải đúng:
- Không còn bất kỳ đường được hỗ trợ nào có thể đưa evt-123 đến cùng handler.
- Hoặc handler có **business idempotency** bền hơn marker, ví dụ unique shipment(orderId, shipmentType), để hiệu ứng vẫn không nhân đôi.
- Hoặc replay chạy trong namespace/cơ chế xử lý chủ động tách biệt, có kiểm soát tác dụng phụ.
- Hoặc trước replay có bước phục hồi đủ dữ liệu dedupe từ archive.

Không nên xem broker retention là giới hạn duy nhất của khả năng một message cũ quay lại.

---

## 5. Lập bản đồ các con đường message có thể xuất hiện lại

Trước khi đặt retention, liệt kê mọi nguồn có thể đưa lại cùng eventId:

1. Publisher phát lại do ACK broker mất.
2. Broker redelivery khi consumer không ACK hoặc crash.
3. Consumer restart với offset/checkpoint cũ.
4. Consumer group mới đọc lại log còn trong broker.
5. DLQ được reprocess thủ công sau khi sửa lỗi schema.
6. Operator re-drive message từ quarantine hoặc backup.
7. Topic được khôi phục từ bản sao lưu.
8. Event archive được replay để xây lại projection.
9. Một data migration phát lại message lịch sử.
10. Client/service gửi lại một command tạo cùng business effect.
11. Một job reconciliation tái phát hành event để đồng bộ dữ liệu.
12. Một hệ bridge hoặc connector có cơ chế retry riêng.
13. Service ở vùng khác hồi phục sau partition dài.
14. Một replay có chọn lọc theo tenant/orderId để khắc phục mất dữ liệu.

**Mỗi con đường phải có owner, mục đích và thời hạn tối đa hoặc một cơ chế an toàn vượt thời hạn.** Nếu tổ chức muốn cho phép replay vô hạn, việc xóa mọi dấu chống trùng theo TTL hữu hạn chỉ an toàn khi business idempotency vẫn bảo vệ side effect hoặc replay được cách ly khỏi tác dụng phụ.

### 5.1. “Đã qua retention của topic” chưa đủ

Một topic giữ message 7 ngày không có nghĩa event không thể được phát lại ở ngày thứ 90. DLQ có thể giữ lâu hơn; archive có thể giữ nhiều năm; một bản sao lưu hoặc admin script có thể re-drive event cũ.

Nếu inbox TTL chỉ 7 ngày vì topic retention 7 ngày, phải xác nhận **không có đường ngoài broker** có thể tái phát event vào chính handler hoặc có cơ chế chống trùng ở cấp nghiệp vụ.

### 5.2. “Đã xử lý” phải gắn với loại side effect

Đối với read projection:
- Rebuild từ đầu có thể chủ ý apply toàn bộ event trong database mới.
- Trạng thái được tái tạo từ dữ liệu lịch sử; duplicate cần tránh trong một lần rebuild, nhưng không nên làm consumer mới bỏ qua toàn bộ event vì marker của projection cũ.

Đối với tác dụng phụ:
- Gửi email, charge payment, đặt shipment hoặc cấp quyền có thể không an toàn nếu replay tự động kích hoạt lại.
- Cần tách **projection replay** khỏi **business action replay**.

Đây là một khác biệt trọng yếu trong thiết kế khả năng xử lý lại.

---

## 6. Thiết kế chính sách retention từ yêu cầu khôi phục

Một chính sách retention không nên chỉ là “giữ 30 ngày vì dung lượng”. Hãy xác định:

- **Khả năng gửi lại:** Publisher có thể retry tối đa bao lâu?
- **Độ trễ consumer:** Consumer có thể offline tối đa bao lâu trước khi mất quyền đọc từ broker?
- **Thời hạn DLQ:** Message lỗi được giữ bao lâu để điều tra/re-drive?
- **Cửa sổ replay:** Nhóm vận hành hứa có thể rebuild dữ liệu từ thời điểm nào?
- **Backup/restore:** Có thể phục hồi một checkpoint cũ bao nhiêu ngày?
- **Độ trễ phục hồi sự cố:** Thời gian phát hiện và sửa lỗi lớn là bao lâu?
- **Dữ liệu cá nhân:** Có giới hạn lưu giữ hoặc nghĩa vụ xóa theo chính sách áp dụng không?
- **Business idempotency:** Có trạng thái nghiệp vụ duy nhất bảo vệ effect sau khi marker bị xóa không?

Một cách thiết kế bảo thủ:

    dedupe_retention >= largest_supported_duplicate_arrival_horizon
                        + operational_safety_margin

Trong đó duplicate arrival horizon không chỉ là topic retention. Nếu có manual replay từ archive vô thời hạn, “giữ marker vô thời hạn” chưa chắc là giải pháp tối ưu; có thể chuyển sang khóa duy nhất nghiệp vụ hoặc tách chế độ replay để vừa kiểm soát chi phí vừa bảo vệ side effect.

### 6.1. Ví dụ tính cửa sổ

Giả sử một hệ có các cam kết:
- Broker log giữ 7 ngày.
- DLQ có thể được xử lý lại trong 30 ngày.
- Backup có thể restore checkpoint cũ tối đa 14 ngày.
- Một quy trình điều tra sự cố có thể yêu cầu replay trong 45 ngày.
- Có biên vận hành 15 ngày.

Nếu không có biện pháp chống trùng khác, một inbox giữ 7 ngày là không phù hợp. Một chính sách có thể cân nhắc giữ marker ít nhất qua cửa sổ 45 ngày cộng biên 15 ngày, **nếu** tất cả đường replay được thống nhất phù hợp và thời hạn này thực sự là giới hạn tối đa.

Con số 60 ngày chỉ minh họa phương pháp. Không áp dụng máy móc cho sản xuất, và không khẳng định một phép lấy maximum đơn giản đủ để xử lý mọi tình huống có tác dụng phụ lâu dài.

### 6.2. Phạm vi áp dụng retention

Một tổ chức có thể có chính sách riêng cho:
- Order lifecycle events.
- Payment/ledger events.
- Audit/security events.
- Email/notification delivery markers.
- Analytics projections.
- Customer deletion/tombstone events.

Không nên ép mọi loại dữ liệu theo một TTL vì giá trị phục hồi và nghĩa vụ dữ liệu khác nhau. Một bảng inbox phục vụ payment processing có thể cần business idempotency bền lâu hơn nhiều so với dedupe của một dashboard thống kê có thể rebuild.

---

## 7. Điều kiện dọn outbox an toàn

Một outbox record có thể trải qua:

    NEW
      |
      v
    CLAIMED / IN_FLIGHT
      |
      | broker confirm
      v
    PUBLISHED
      |
      | hết thời hạn sử dụng trực tiếp
      v
    ARCHIVED / CLEANUP_ELIGIBLE
      |
      v
    PURGED

Có thể có FAILED, RETRY_SCHEDULED hoặc DEAD_LETTER/OPERATOR_REVIEW. Tên trạng thái tùy hệ; vấn đề là định nghĩa đúng semantics.

**Chỉ xem xét xóa outbox khi đã có bằng chứng đủ theo publish contract**, ví dụ:
1. Event gắn với transaction nghiệp vụ đã commit.
2. Broker xác nhận đã nhận theo mức durability yêu cầu.
3. Bằng chứng publish được lưu và vượt qua thời hạn giữ cần thiết.
4. Không có process vẫn claim record hoặc cần retry.
5. Nếu cần replay ngoài broker, đã có nguồn archive/event store/snapshot hợp lệ.
6. Các điều kiện audit, retention, riêng tư và đối soát cho phép xóa.

### 7.1. Không xóa NEW/PENDING/RETRY chỉ vì quá cũ

Outbox NEW từ 30 ngày trước có thể là một nghĩa vụ chưa được gửi do publisher lỗi. Xóa nó vì older_than_30_days làm mất sự kiện.

Bản ghi quá tuổi nên:
- Tăng mức cảnh báo.
- Được điều tra publisher/lease/serialization.
- Được chuyển vào quarantine có bảo toàn nội dung nếu thật sự không thể publish.
- Hoặc được operator quyết định bỏ qua theo một quy trình có audit và lý do nghiệp vụ.

Không tự coi “lâu ngày” là “đã hoàn thành”.

### 7.2. Broker ACK khác consumer ACK

Nếu Kafka/broker xác nhận message được ghi, outbox có thể được xem là **đã bàn giao cho broker** theo contract. Điều đó không chứng minh Analytics, Notification hoặc Shipping đã xử lý. Nếu hệ thống yêu cầu tracking consumer completion, cần một mô hình riêng: acknowledgement nghiệp vụ, workflow state, consumer lag/checkpoint hoặc audit khác.

Không dùng điều kiện “mọi consumer phải xử lý” làm mặc định để giữ outbox vô thời hạn; nó có thể không khả thi khi consumer mới được tạo liên tục. Nếu thực sự cần, phải xác định một tập consumer bắt buộc và protocol completion cụ thể.

### 7.3. Khi outbox đồng thời được dùng làm replay log

Một số đội dùng outbox như event archive bất đắc dĩ. Nếu xóa published records, khả năng replay sẽ biến mất khi broker cũng hết retention. Cần chọn rõ:
- Chuyển archive trước purge.
- Duy trì event store chuyên dụng.
- Có snapshot đáng tin và nguồn delta từ checkpoint.
- Hoặc tuyên bố replay chỉ hỗ trợ một cửa sổ hữu hạn.

Không ghi README “có thể replay mọi lúc” nếu kiến trúc đã xóa cả broker log lẫn outbox.

---

## 8. Điều kiện dọn inbox an toàn

Một inbox marker thường có các trường:

    consumer_scope
    event_id
    aggregate_id
    processed_at
    handler_version
    status
    optional_source_partition
    optional_source_offset

Không phải thiết kế nào cũng cần tất cả. Khóa duy nhất phải thể hiện phạm vi dedupe đúng.

Các bước trước khi cleanup:
1. Xác định processed marker đã thuộc **transaction thành công** cùng side effect cục bộ, không phải PENDING/FAILED.
2. Xác định message có thể xuất hiện lại tới khi nào.
3. Đánh giá khả năng restore từ backup/DLQ/archive sau TTL.
4. Xác định nếu marker bị xóa, business constraints nào vẫn ngăn effect trùng.
5. Xác định replay nào chỉ tái tạo projection và replay nào có thể gọi external systems.
6. Có cơ chế không xóa marker của job/consumer đang reprocess.
7. Theo dõi metric sau cleanup và có runbook khi event cũ tái xuất hiện.

### 8.1. Không chỉ dựa vào processed_at

Một event được xử lý năm trước vẫn có thể được re-drive hôm nay. Nếu contract cho phép replay lịch sử, tuổi marker không nói event đã hết khả năng xuất hiện lại.

Thay vì TTL thuần:
- Dùng logical dedupe ở domain, ví dụ unique order_id cho shipment ban đầu.
- Tách replay projection trong database/namespace riêng.
- Giữ marker trong archive có thể restore nhanh.
- Đặt một **replay watermark** có scope và quyền quản trị.
- Cấp generation ID mới cho việc rebuild có kiểm soát.
- Chặn kích hoạt side effect không idempotent trong replay.

### 8.2. Không dùng “consumer offset lớn nhất” làm bằng chứng mọi event trước đều xong

Nếu consumer xử lý song song:
- Offset 100 và 102 đã xong.
- Offset 101 vẫn đang xử lý hoặc đã thất bại.
- Commit offset 103 rồi cleanup dấu của 101 có thể làm mất công việc chưa xong.

Checkpoint phải đại diện cho **vùng tiến độ liên tục được xử lý an toàn** theo partition, không phải chỉ một offset max nhìn thấy. Với những hệ có reorder/parallel execution, cần quản lý outstanding offsets hoặc chuyển sang mô hình ACK/checkpoint có tính liên tục.

### 8.3. Marker của handler A không được xóa vì handler B xong

Nếu cùng topic có hai consumer:
- InvoiceProjection: xây read model.
- FraudRules: phát cảnh báo.
- Notification: gửi email.

Thời hạn, side effect và khả năng replay của ba handler khác nhau. Cleanup có thể cần chính sách và namespace riêng; không dùng một bảng processed_event chung mà thiếu consumerScope.

---

## 9. Dọn theo partition, không quét/xóa toàn bảng vô hạn

Đối với các bảng lớn, DELETE hàng triệu dòng trong một transaction có thể:
- Giữ lock và gây contention.
- Tạo WAL/binlog/replication lag lớn.
- Làm tăng bloat, chậm index và autovacuum.
- Khiến backup, truy vấn publisher/consumer và latency ứng dụng bị ảnh hưởng.
- Làm transaction log đầy hoặc gây sự cố disk.

Các kỹ thuật:
- **Batch DELETE** với kích thước giới hạn.
- **Partition by time** nếu truy vấn và retention hỗ trợ.
- **Indexes** trên status, created_at/published_at hoặc retention_expires_at để chọn ứng viên.
- **Pause/resume và rate limit** theo tải hệ thống.
- **Archive rồi purge** nếu cần giữ lịch sử.
- **Giới hạn transaction duration** và quan sát replication lag.
- **Thử nghiệm trên dữ liệu gần sản xuất** trước khi lập lịch.

### 9.1. Batch cleanup minh họa PostgreSQL

Giả sử bảng outbox có cột published_at và trạng thái được cập nhật chỉ sau publish confirm:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox
    WHERE publish_status = 'PUBLISHED'
      AND published_at < :safeCutoff
      AND archived = TRUE
    ORDER BY published_at, event_id
    LIMIT :batchSize
    FOR UPDATE SKIP LOCKED
)
DELETE FROM outbox o
USING candidates c
WHERE o.event_id = c.event_id
RETURNING o.event_id;
~~~

Đây là mẫu minh họa, không đủ để áp dụng trực tiếp mọi schema. Điều kiện archived phải có bằng chứng archive được xác minh, không chỉ một Boolean được ghi trước khi upload thành công. Nếu hệ thống không cần archive, cần bỏ điều kiện nhưng phải có một quyết định rõ ràng về replay horizon.

Các điểm bắt buộc:
- Chỉ xóa PUBLISHED theo semantics đáng tin.
- Batch nhỏ, commit từng batch.
- Index phù hợp với điều kiện tìm.
- Có throttling và ngưỡng dừng.
- Không chọn record đang có lease/claim còn hiệu lực nếu state model cho phép.
- Tránh DELETE theo một timestamp mà bỏ trạng thái.
- Giám sát row count và oldest unpublished event.

### 9.2. Dọn inbox minh họa

~~~sql
WITH candidates AS (
    SELECT consumer_scope, event_id
    FROM processed_event
    WHERE status = 'PROCESSED'
      AND processed_at < :safeCutoff
      AND replay_generation = :closedGeneration
    ORDER BY processed_at
    LIMIT :batchSize
    FOR UPDATE SKIP LOCKED
)
DELETE FROM processed_event p
USING candidates c
WHERE p.consumer_scope = c.consumer_scope
  AND p.event_id = c.event_id;
~~~

Điều kiện closedGeneration chỉ hợp lệ nếu hệ thống **thực sự quản lý generation/replay scope**. Không tự thêm field hoặc gán generation=old để cho phép xóa khi vẫn có consumer/replay khác dùng marker ấy.

Nếu không thể chứng minh cửa sổ chống trùng an toàn, tốt hơn là giữ marker hoặc thiết kế lại business idempotency trước khi cleanup.

### 9.3. Partition drop

Với dữ liệu time-partitioned, loại bỏ partition cũ có thể ít tốn hơn DELETE hàng loạt. Nhưng thao tác drop rất khó hoàn tác, cần:
- Đúng partition boundary.
- Tất cả bản ghi trong partition đã an toàn, không còn NEW/IN_FLIGHT.
- Archive/snapshot đã được xác minh khi cần.
- Không có truy vấn hoặc khóa đang dựa vào partition ấy.
- Chạy theo lịch kiểm soát và có dry-run.
- Có backup/restore hoặc quy trình phê duyệt tương ứng.

Một partition theo created_at có thể chứa cả PUBLISHED và NEW cũ. **Không được drop cả partition chỉ vì phần lớn record đã publish.** Có thể dùng partition phù hợp trạng thái/lifecycle hoặc chuyển các record chưa xử lý sang vùng active an toàn trước khi drop.

---

## 10. Archive: giữ khả năng replay mà không phải giữ mọi thứ ở hot database

Một hệ thống có thể lưu:
- Dữ liệu đang chờ phát ở outbox hot table.
- Bản ghi đã publish một thời gian ngắn để đối soát.
- Event payload lịch sử trong object storage/event store chuyên dụng.
- Metadata index giúp tìm theo eventId, aggregateId, tenant, khoảng thời gian, schema version.

Một luồng:

    Outbox PUBLISHED
          |
          +----> Archive writer
                    |
                    +-- write immutable segment
                    +-- checksum / manifest
                    +-- verify readable and complete
                    +-- mark archived
          |
          +----> Cleanup worker
                    |
                    +-- select safe records
                    +-- purge hot copies

### 10.1. Không đánh dấu archived trước khi dữ liệu bền vững

Quy trình sai:

    mark archived = TRUE
    upload object
    process crashes during upload
    cleanup deletes row

Dữ liệu có thể mất cả ở DB và archive.

Quy trình đúng hơn:
1. Ghi archive segment ở nơi bền vững.
2. Xác minh checksum, số bản ghi, phạm vi và schema metadata.
3. Commit manifest/archive pointer.
4. Đánh dấu các record tương ứng đã archive theo protocol có thể retry.
5. Cleanup chỉ chọn record đã có bằng chứng archive, cùng điều kiện publish/retention.

Nếu archive upload thành công nhưng mark DB thất bại, retry có thể tạo dữ liệu trùng trong archive. Cần thiết kế archive idempotent, tên segment/manifest ổn định hoặc quy tắc dedupe.

### 10.2. Manifest phải đủ để phục hồi

Một archive manifest có thể ghi:
- Archive batch ID.
- Source service/topic/event type.
- Mốc bắt đầu/kết thúc hoặc partition/offset range.
- First/last eventId nếu có ích.
- Số bản ghi và checksum.
- Serialization/schema version.
- Compression/encryption format.
- Object location và retention class.
- Trạng thái verification.
- Thời điểm archive và owner.
- Phiên bản công cụ tạo/đọc.

Không thể chỉ lưu một file gzip không biết chứa gì rồi cam kết “replay được mọi event”. Phải biết event nào thuộc file nào, có đủ không, và reader có giải mã được sau khi schema tiến hóa không.

### 10.3. Kiểm tra khả năng phục hồi định kỳ

Bản archive chỉ có giá trị khi restore thật sự hoạt động:
- Chọn một khoảng dữ liệu cũ.
- Đọc manifest và checksum.
- Deserialize bằng schema/upcaster tương ứng.
- Rebuild vào môi trường cách ly.
- So sánh số bản ghi, version và kết quả với nguồn có thẩm quyền.
- Đo thời gian phục hồi và chi phí.
- Báo lỗi archive corruption hoặc missing key material.

Không chờ tới lần sự cố lớn đầu tiên mới thử restore.

---

## 11. Snapshot và event replay: hai lựa chọn khôi phục khác nhau

Nếu giữ toàn bộ integration events là quá đắt, một projection có thể được xây từ **snapshot + các sự kiện sau snapshot**.

Ví dụ:

    Snapshot OrderSummary at sourceVersion=500
       |
       +-- OrderUpdated v501
       +-- OrderUpdated v502
       +-- PaymentCaptured v... (projection-specific source)
       +-- ShipmentStatus v...
       |
       v
    New OrderSummary projection

Để đúng, phải xác định:
- Snapshot phản ánh trạng thái tại mốc nguồn nào?
- Delta stream sau mốc ấy có đầy đủ và được sắp đúng không?
- Nhiều nguồn có checkpoint độc lập hay không?
- Có trạng thái nào được sinh bởi command trực tiếp không có event trong log?
- Schema snapshot/contract có thể đọc được sau migration không?
- Có business side effects nào phải **tắt** khi rebuild không?

### 11.1. Không mặc định integration events đủ để rebuild toàn trạng thái

Một event OrderConfirmed có thể chỉ chứa orderId và timestamp; nó không chứa địa chỉ giao, giá chi tiết hoặc toàn bộ lịch sử cập nhật. Nếu chưa bao giờ phát những field đó trong integration events, không thể tái tạo chính xác mọi projection chỉ bằng log này.

Lựa chọn:
- Event sourcing với event store có đầy đủ sự kiện miền.
- Snapshot từ source-of-truth và delta có hợp đồng.
- Bulk export/backfill API từ owner.
- Data CDC có phạm vi và bảo mật phù hợp.
- Một phép tái tạo dựa trên nhiều nguồn được điều phối.

Hãy mô tả khả năng rebuild **thật** thay vì suy từ việc có Kafka topic.

### 11.2. Checkpoint đa nguồn

Một projection ghép Order và Payment không có một offset duy nhất cho toàn bộ hệ. Có thể lưu checkpoint theo:
- Topic/partition của Order.
- Topic/partition của Payment.
- Snapshot version/epoch của mỗi nguồn.
- Event schema/handler version.

Để tái tạo nhất quán, cần biết tương quan thời điểm hoặc quy tắc hội tụ giữa các nguồn. Một snapshot của Order ở T1 và Payment ở T2 có thể tạo trạng thái trung gian, nhưng điều này có thể hợp lệ nếu projection có reconciliation và source authority rõ.

---

## 12. Replay an toàn: xác định “xử lý lại” nghĩa gì

Câu “replay event” có thể chỉ ít nhất bốn thao tác:
1. **Re-drive delivery:** Gửi lại message vì consumer chưa xử lý.
2. **Rebuild projection:** Đọc lại lịch sử để dựng một read model mới.
3. **Reprocess business command:** Thực hiện lại một tác động nghiệp vụ.
4. **Audit/inspection:** Đọc lại để phân tích nhưng không tạo side effect.

Đây là các mức rủi ro khác nhau. Runbook phải ghi rõ mục đích và giới hạn, không dùng một nút “Replay all” cho mọi loại handler.

### 12.1. Rebuild projection trong môi trường cách ly

Một quy trình minh họa:
1. Tạo projection database hoặc namespace mới.
2. Cấp replayJobId/generation.
3. Nạp snapshot đã xác minh nếu cần.
4. Đọc event archive/broker theo checkpoint.
5. Deserialize và upcast đúng schema.
6. Apply idempotent với version guard.
7. So sánh kết quả với nguồn có thẩm quyền.
8. Chuyển traffic đọc sang projection mới có kiểm soát.
9. Giữ khả năng rollback và audit.
10. Cleanup projection cũ theo retention riêng.

Không nên rebuild bằng cách xóa production projection rồi chạy lại khi chưa biết thời gian hoàn tất hoặc khả năng phục hồi. Blue-green projection giúp tránh mất khả dụng.

### 12.2. Re-drive consumer có side effect

Trước khi phát lại một event cho Notification hoặc Payment adapter:
- Xác định event có thể đã tạo effect nào.
- Xác định idempotency key nghiệp vụ.
- Query nguồn có thẩm quyền hoặc ledger trước khi thử lại.
- Xác định marker inbox còn đủ tuổi hay đã purge.
- Kiểm soát replay rate, tenant scope và khoảng event.
- Có dry-run/sandbox khi hiệu quả.
- Có audit người thực hiện và reason.
- Giám sát kết quả, dừng khi xuất hiện duplicate bất thường.

Một message OrderConfirmed có thể cần rebuild analytics nhưng **không** nên tự động gửi lại email xác nhận nhiều năm sau.

### 12.3. Replay namespace/generation

Khi mục đích là xây projection mới, có thể tạo:

    consumerScope = order-summary-v2
    replayGeneration = rebuild-2026-11
    eventId = evt-123

Inbox của projection mới cần ghi nhận việc xử lý trong generation ấy, không bị marker của projection v1 ngăn lại. Ngược lại, nghiệp vụ gửi email thật vẫn sử dụng key/idempotency của email intent, không tạo generation mới để vượt chặn trùng.

---

## 13. Bảo toàn tính thứ tự và checkpoint khi replay

Với broker partitioned, thứ tự thường được cam kết trong phạm vi partition/stream theo giao thức. Không nên giả định mọi event của các topic hoặc partition có một thứ tự toàn cục.

### 13.1. Contiguous watermark

Giả sử consumer xử lý song song offsets:

    100 -> DONE
    101 -> IN_PROGRESS
    102 -> DONE
    103 -> DONE

Không được xem watermark tiến độ hoàn tất là 103 nếu việc dùng nó để bỏ qua 101. Một checkpoint an toàn cho chuỗi liên tục có thể chỉ tiến tới 100 (hoặc offset kế tiếp theo quy ước broker), cho đến khi 101 hoàn tất.

Cần thống nhất:
- Watermark là last processed hay next to read?
- Theo partition hay aggregate?
- Cơ chế xử lý in-flight và out-of-order.
- Consumer commit offset trước hay sau transaction local.
- Khôi phục sau crash ở bất kỳ mốc nào.

### 13.2. Aggregate version

Một projection nhận:

    ProductUpdated(product=7, version=12)
    ProductUpdated(product=7, version=10)

Nếu event chứa trạng thái đầy đủ, có thể dùng version guard để không lùi dữ liệu:

~~~sql
UPDATE product_projection
SET title = :title,
    source_version = :version
WHERE product_id = :id
  AND source_version < :version;
~~~

Nhưng nếu event là delta (ví dụ QuantityAdded +5), bỏ version 11 có thể làm sai số liệu. Cần bảo đảm xử lý đủ delta hoặc rebuild từ snapshot/version phù hợp.

### 13.3. Không dùng timestamp nhận để quyết định thứ tự

Replay từ archive có thể thay đổi thứ tự nhận, thời điểm gửi và offset mới. receivedAt của consumer mới không chứng minh nghiệp vụ nào xảy ra trước. Dựa vào sequence/version có thẩm quyền theo contract, hoặc thiết kế phép hội tụ không nhạy thứ tự nếu có thể.

### 13.4. Tombstones và sự kiện xóa

Nếu đã nhận CustomerDeleted(version=15), rồi replay CustomerUpdated(version=14), projection không được hồi sinh bản ghi đã xóa. Tombstone/version và chính sách dữ liệu cần được xử lý đúng, kể cả khi hot inbox marker cũ đã được cleanup.

Không chỉ dedupe theo eventId; còn cần **domain transition validity**.

---

## 14. Schema evolution: dữ liệu cũ phải còn đọc được

Một vấn đề thường bị quên: giữ byte payload 5 năm không có nghĩa ứng dụng mới giải mã được.

Ví dụ:
- Event v1 dùng amount theo đơn vị major.
- Event v2 dùng amountMinor và currency.
- Event v3 tách trạng thái payment thành authorized/captured.
- Consumer hiện tại chỉ biết v3.

Nếu replay v1 mà dùng logic v3 trực tiếp, có thể sai tiền hoặc sai trạng thái dù JSON parse thành công.

### 14.1. Upcaster/transformer

Một pipeline:

    Read archived record
         |
         v
    Identify event type + schemaVersion
         |
         v
    Decode with writer schema
         |
         v
    Upcast/transform into canonical replay model
         |
         v
    Validate semantics and version
         |
         v
    Apply to projection

Upcaster phải được kiểm thử với dữ liệu lịch sử, không chỉ happy-path samples. Nếu một trường chưa tồn tại trong v1, cần quy tắc suy ra hoặc đánh dấu unknown, không tự tạo dữ liệu không có căn cứ.

### 14.2. Giữ schema registry artifacts

Nếu event archive tham chiếu schema ID, cần bảo đảm registry/schema artifact còn có thể truy xuất trong thời gian replay được cam kết. Xóa schema cũ trước khi purge event phụ thuộc nó sẽ làm archive không đọc được.

### 14.3. Phạm vi tương thích theo contract

Một schema checker có thể xác nhận thêm optional field là tương thích về cấu trúc, nhưng không chứng minh logic nghiệp vụ tương thích. Thay đổi nghĩa STATUS_SUCCESS từ “đã capture” sang “đã nhận request” sẽ phá hủy replay dù schema không đổi.

Cần versioning cả **ngữ nghĩa**, nhất là với tiền, đơn vị, state machine và event thời điểm hiệu lực.

---

## 15. Đối soát khi dữ liệu truyền sự kiện bị mất hoặc đã purge

Ngay cả kiến trúc có outbox vẫn cần reconciliation:
- Publisher có thể bị lỗi lâu hơn retention broker.
- Schema bug khiến consumer không áp dụng event.
- Một message có thể nằm DLQ mà không được xử lý.
- Một archive segment có thể hỏng.
- Một snapshot có thể thiếu field cần để rebuild.
- Consumer checkpoint có thể vượt qua message chưa xử lý do bug.

Đối soát không nhất thiết cần replay byte gốc nếu có API/source-of-truth có thể phát hành snapshot đúng.

### 15.1. Ví dụ đối soát OrderSummary

1. Analytics phát hiện Order=CONFIRMED ở nguồn nhưng projection vẫn PENDING.
2. Tra orderId/sourceVersion từ Order qua API được phép.
3. So sánh sourceVersion với projectionVersion.
4. Nếu projection trễ, ưu tiên catch-up từ event stream.
5. Nếu thiếu event vĩnh viễn, thực hiện backfill trạng thái từ source theo contract.
6. Ghi repair operation và bằng chứng, không giả vờ đây là event lịch sử gốc nếu chỉ tái tạo từ snapshot.
7. Theo dõi số record được sửa và nguyên nhân thiếu event.

### 15.2. Bất biến cứng không phụ thuộc vào replay của analytics

Nếu Inventory đã cấp hai reservation cho cùng một ghế, rebuild projection không giải quyết sai lầm tại nguồn. Sửa bằng constraint/atomic decision ở owner, sau đó mới dùng event/reconciliation để làm các bản sao hội tụ.

### 15.3. Không tự phát event mới với eventId cũ khi dữ liệu nghĩa khác

Một reconciliation job có thể tạo SnapshotReconciled hoặc ProductStateRebuilt với eventId và contract mới. Không giả mạo sự kiện gốc đã xảy ra với timestamp/ID cũ nếu nội dung chỉ là suy diễn từ trạng thái hiện tại. Cần audit phân biệt event lịch sử và sự kiện sửa chữa.

---

## 16. Rủi ro xóa dữ liệu inbox trong service có side effect bên ngoài

Hãy xét Notification gửi email khi nhận OrderConfirmed:

    consumer nhận evt-123
    gửi email thành công
    ghi inbox marker
    ACK

Nếu gửi email rồi crash trước khi commit marker, việc nhận lại có thể gửi email lần nữa. Transaction database không thể tự rollback email đã được gửi.

Giải pháp tốt hơn cần một **business operation ID** và trạng thái gửi có thể kiểm tra:
- notificationIntentId = order-confirmation:ord-123.
- Unique constraint cho loại thông báo/đối tượng/tenant.
- Tạo intent trong transaction cục bộ trước.
- Worker gửi email qua provider với idempotency nếu có.
- Lưu provider message ID và kết quả.
- Đối soát tình huống result unknown.
- Không chỉ dựa vào inbox eventId để bảo vệ toàn bộ side effect.

### 16.1. Dedupe marker có thể là cache của một invariant bền hơn

Nếu một shipment chỉ được tạo một lần cho một order fulfillment key, ràng buộc unique trên business key có thể tồn tại lâu dài. Khi inbox marker hết hạn, redelivery vẫn không tạo shipment thứ hai.

Với hiệu ứng **không có API truy vấn hoặc idempotency**, có thể phải giữ marker/ledger lâu hơn, hạn chế replay hoặc chấp nhận chính sách vận hành rủi ro được phê duyệt. Không có một giải pháp “xóa inbox sau N ngày” an toàn cho mọi provider.

### 16.2. Đừng xóa nghiệp vụ chỉ để giải phóng inbox

Inbox lưu thông tin dedupe; Payment ledger lưu sự thật về tiền. Khi dọn inbox không được vô tình xóa ledger hoặc trạng thái idempotency của Payment mà vẫn cần để chống thu trùng/hoàn trùng.

Mỗi loại dữ liệu có chính sách retention riêng và một owner phê duyệt.

---

## 17. DLQ, poison messages và cleanup

Một message có thể không xử lý được do:
- Schema không tương thích.
- Dữ liệu nghiệp vụ không hợp lệ.
- Consumer bug.
- Dependency unavailable lâu.
- Message vượt giới hạn tài nguyên.
- Không có quyền giải mã hoặc thiếu khóa.
- Một phiên bản event đã bị xóa khỏi schema registry.

Chuyển vào DLQ/quarantine có thể tránh chặn mọi message khác, nhưng **DLQ không phải nơi bỏ quên dữ liệu**.

### 17.1. Điều kiện xử lý DLQ

Mỗi record nên có:
- Original eventId và source coordinates.
- Lý do lỗi có phân loại.
- Lần thử và timestamp gần nhất.
- Schema/version và handler.
- Tenant/scope nếu cần.
- Trạng thái điều tra hoặc re-drive.
- Owner và hạn xử lý.
- Liên kết runbook/case.

Một record không nên tự biến mất vì quá hạn nếu nó đại diện cho giao dịch tài chính chưa được phản ánh. Với dữ liệu tùy chọn có thể bỏ theo chính sách, việc drop cũng phải có decision/audit.

### 17.2. Dedupe retention phải tính đến DLQ

Nếu DLQ giữ 60 ngày mà inbox xóa marker sau 7 ngày, khi re-drive một event đã từng tạo side effect rồi lỗi ở bước sau, consumer có thể lặp lại effect trước đó.

Vì vậy cần:
- Đánh giá side effect đã thực hiện trước khi lỗi.
- Đưa trạng thái từng bước vào operation ledger nếu quy trình nhiều bước.
- Cùng key idempotency trên re-drive.
- Hoặc giữ marker đủ lâu theo cửa sổ DLQ và recovery.

### 17.3. Không trộn poison message và retryable failure

Một schema không thể giải mã sẽ không tự sửa sau 1000 lần retry. Một database outage có thể phục hồi. Policy cần phân loại để tránh retry storm và giữ khả năng điều tra.

Cleanup chỉ được thực hiện khi message đã có quyết định cuối theo contract hoặc được archive với khả năng truy vết.

---

## 18. Một mô hình dữ liệu tham khảo

### 18.1. Outbox

~~~sql
CREATE TABLE outbox (
    event_id           VARCHAR(128) PRIMARY KEY,
    aggregate_id       VARCHAR(128) NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    event_type         VARCHAR(128) NOT NULL,
    schema_version     INTEGER NOT NULL,
    payload            TEXT NOT NULL,
    publish_status     VARCHAR(32) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    published_at       TIMESTAMP NULL,
    next_attempt_at    TIMESTAMP NULL,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    lease_owner        VARCHAR(128) NULL,
    lease_until        TIMESTAMP NULL,
    archived_at        TIMESTAMP NULL
);
~~~

Đây là schema minh họa. Production cần chọn kiểu timestamp, index, tenant scope, độ bền, constraints, partitioning, payload format/encryption và hệ thời gian phù hợp.

### 18.2. Inbox

~~~sql
CREATE TABLE processed_event (
    consumer_scope     VARCHAR(128) NOT NULL,
    event_id           VARCHAR(128) NOT NULL,
    handler_generation VARCHAR(128) NOT NULL,
    processed_at       TIMESTAMP NOT NULL,
    source_partition   INTEGER NULL,
    source_offset      BIGINT NULL,
    PRIMARY KEY (consumer_scope, handler_generation, event_id)
);
~~~

Chọn generation theo nghĩa nghiệp vụ. Nếu handler xử lý business side effect, một generation mới không được tự động cho phép tạo lại cùng hiệu ứng.

### 18.3. Archive manifest

~~~sql
CREATE TABLE event_archive_manifest (
    archive_id       VARCHAR(128) PRIMARY KEY,
    source_name      VARCHAR(128) NOT NULL,
    object_uri       TEXT NOT NULL,
    record_count     BIGINT NOT NULL,
    content_checksum VARCHAR(256) NOT NULL,
    schema_catalog   TEXT NOT NULL,
    interval_start   TIMESTAMP NOT NULL,
    interval_end     TIMESTAMP NOT NULL,
    verified_at      TIMESTAMP NULL,
    created_at       TIMESTAMP NOT NULL
);
~~~

Đường object_uri và checksum là metadata. Khi phục hồi phải xác minh object tồn tại, quyền giải mã còn hiệu lực và manifest tương ứng đúng tập record.

---

## 19. Java/Spring: publisher, consumer và cleanup nên tách trách nhiệm

Một cấu trúc gợi ý:

    order-service/
      domain/
        Order.java
        OrderEvent.java
      application/
        ConfirmOrderUseCase.java
      infrastructure/
        OutboxRepository.java
        BrokerPublisher.java
        OutboxRelayWorker.java
        OutboxArchiver.java
        OutboxCleanupJob.java

    analytics-service/
      application/
        OrderProjectionHandler.java
      infrastructure/
        InboxRepository.java
        ProjectionRepository.java
        ReplayCoordinator.java
        InboxCleanupJob.java

Không nên cho cùng một method vừa xác nhận Order, vừa publish message, vừa xóa outbox theo thời gian. Chia trách nhiệm:
- Domain transaction tạo sự thật và outbox.
- Relay chịu retry publish.
- Archive chịu chuyển dữ liệu bền vững.
- Cleanup chỉ xóa record đã đủ điều kiện.
- Consumer/inbox chịu idempotent processing.
- Replay coordinator chịu phạm vi và giới hạn replay.

### 19.1. Publisher pseudo-code

~~~java
void relayBatch() {
    List<OutboxEvent> events = outbox.claimReadyBatch(100, leaseDuration);

    for (OutboxEvent event : events) {
        try {
            broker.publishAndAwaitRequiredAck(
                event.eventId(),
                event.partitionKey(),
                event.payload()
            );
            outbox.markPublishedIfLeaseOwned(
                event.eventId(), event.leaseToken()
            );
        } catch (Exception ex) {
            outbox.scheduleRetryIfLeaseOwned(
                event.eventId(), event.leaseToken(), retryPolicy.nextDelay(ex)
            );
        }
    }
}
~~~

Đây là giả mã, không phải API có sẵn của Spring hoặc một Kafka client cụ thể.

Lưu ý:
- markPublished phải có concurrency guard/lease token.
- Nếu publish thành công rồi process crash trước mark, event được gửi lại; ID không đổi.
- Không xóa event trong catch.
- Một publisher nhận lease hết hạn cần tránh ghi đè trạng thái của publisher khác.
- Retry phải giới hạn tốc độ và có DLQ/alert cho lỗi không thể sửa.

### 19.2. Consumer pseudo-code

~~~java
@Transactional
void handle(OrderConfirmed event) {
    boolean first = inbox.tryInsert(
        "order-projection",
        "v2",
        event.eventId()
    );
    if (!first) {
        return;
    }

    OrderProjection projection = projections.lock(event.orderId());
    projection.applyIfNewer(event.aggregateVersion(), event);
    projections.save(projection);
}
~~~

Cần đảm bảo tryInsert và update projection nằm trong cùng transaction, unique constraint hoạt động, và lỗi ở giữa làm rollback marker. Nếu một event không hợp lệ và bị đưa DLQ, không được đánh PROCESSED nếu effect chưa được áp dụng theo policy.

### 19.3. Cleanup pseudo-code

~~~java
void cleanupOutbox() {
    if (!retentionPolicy.isApprovedAndActive()) return;

    while (systemLoad.isWithinCleanupBudget()) {
        List<EventId> deleted = outbox.deleteSafePublishedBatch(
            retentionPolicy.safeCutoff(),
            retentionPolicy.batchSize()
        );
        metrics.recordDeletion(deleted.size());

        if (deleted.isEmpty()) break;
        rateLimiter.pauseBetweenBatches();
    }
}
~~~

Điều kiện safe cutoff phải được tính từ contract và trạng thái lưu trữ/archival. Không sử dụng đơn độc currentTime minus 7 days nếu quá hạn chưa đồng nghĩa publish thành công.

---

## 20. Race conditions giữa cleanup và hệ xử lý

Cleanup là một actor đồng thời với relay, archive, consumer và replay job.

### 20.1. Relay đang gửi, cleanup chọn cùng record

Nếu cleanup chỉ lọc created_at, nó có thể xóa record khi relay chưa có broker ACK. Relay tiếp tục gửi nhưng không còn bản ghi để retry nếu gửi thất bại.

Giải pháp:
- Chỉ cleanup trạng thái đủ điều kiện.
- Row lock/lease phù hợp.
- Cập nhật trạng thái atomically.
- Không cho cleanup thay đổi record CLAIMED còn hiệu lực.
- Kiểm soát trạng thái nếu lease đã hết nhưng một worker cũ vẫn còn chạy.

### 20.2. Archive chưa hoàn thành, cleanup chạy trước

Nếu archive đánh marked=true trước upload, có thể mất message. Dùng protocol xác minh archive và pointer/manifest trước khi mark.

### 20.3. Inbox cleanup trùng lúc replay bắt đầu

Một replay operator bắt đầu re-drive 45 ngày lịch sử, trong khi cleanup xóa marker 30 ngày trước. Có thể tạo duplicate side effects bất ngờ.

Giải pháp:
- Replay plan/lease đăng ký phạm vi thời gian/event.
- Tạm khóa cleanup đối với scope liên quan hoặc giữ marker.
- Dùng replay generation/namespace cách ly cho projection.
- Dùng business idempotency nếu side effect có thể bị re-drive.
- Theo dõi owner và thời gian hết hạn replay lock.

Không nên coi một flag global “pause cleanup forever” là giải pháp dài hạn; cần cơ chế phạm vi và giám sát.

### 20.4. Database restore từ backup cũ

Sau restore:
- Outbox có thể quay về trạng thái NEW với event đã publish trước sự cố.
- Inbox có thể mất marker của các event mà side effect ngoài hệ thống đã diễn ra.
- Broker vẫn giữ offset/message mới hơn DB restore.
- Projection có thể không còn trùng với nguồn.

Runbook phải xác định:
1. Mốc phục hồi và khả năng lệch.
2. Business idempotency ngoài inbox.
3. Những outbox có thể publish trùng.
4. Cách chọn offset/replay từ checkpoint an toàn.
5. Kiểm tra đối soát với nguồn có thẩm quyền.
6. Tạm ngừng những consumer có side effect cho đến khi đánh giá được rủi ro.

Backup restore là một lý do quan trọng khiến việc giữ marker đúng TTL thôi chưa đủ để bảo vệ toàn bộ hiệu ứng.

---

## 21. Dọn dữ liệu và yêu cầu bảo mật/quyền riêng tư

Outbox, inbox và archive có thể chứa:
- Customer ID, Order ID.
- Địa chỉ/email/số điện thoại.
- Thông tin thanh toán hoặc provider references.
- Thông tin hành vi và thời điểm giao dịch.
- Token hoặc secret nếu producer thiết kế payload sai.

Không nên copy toàn bộ entity nội bộ vào event chỉ vì dễ phát. Dữ liệu lan vào broker, DLQ, log và archive sẽ khó xóa hơn.

### 21.1. Data minimization

- Chỉ gửi field cần cho consumer được phê duyệt.
- Dùng opaque IDs thay vì email/số điện thoại làm reference khi phù hợp.
- Tránh secret, credential hoặc thông tin thẻ không được phép trong payload.
- Có quy tắc mã hóa và quản lý khóa.
- Phân loại dữ liệu theo retention và mục đích.

### 21.2. Privacy deletion không chỉ xóa database nguồn

Nếu Customer bị xóa/redact theo một yêu cầu hợp lệ, bản sao có thể còn trong:
- Hot outbox.
- Broker topic.
- Inbox payload nếu hệ lưu payload.
- DLQ.
- Archive object storage.
- Projection và analytics.
- Backup.

Thiết kế cần định nghĩa quy trình xóa/redaction cho các bản sao trong phạm vi nghĩa vụ áp dụng, cân nhắc phần dữ liệu phải giữ theo yêu cầu kế toán/audit. Không thể mặc định “event log immutable nên không bao giờ được xóa PII” hoặc “xóa toàn event không cần xem nghĩa vụ lưu giữ”.

### 21.3. Tombstone và cryptographic erasure

Một số hệ có thể phát tombstone/redaction event, lưu payload đã giảm dữ liệu cá nhân, hoặc dùng mã hóa với khóa phân tách theo scope để có chính sách xóa khóa khi phù hợp. Nhưng:
- Xóa khóa không giải quyết mọi bản sao plaintext từng tạo.
- Tombstone không tự xóa payload cũ ở mọi subscriber/archive.
- Bản ghi audit có thể cần giữ metadata tối thiểu.
- Schema/replay code phải xử lý dữ liệu đã bị redact.

Hãy viết retention và privacy policy từ đầu, không đưa yêu cầu xóa vào một cron job tùy tiện.

---

## 22. Monitoring và alert cho outbox/inbox cleanup

Không nên chỉ đo “số dòng đã xóa”. Một job có thể xóa rất nhanh nhưng làm mất dữ liệu quan trọng.

| Chỉ số | Câu hỏi |
|---|---|
| Outbox NEW/RETRY/CLAIMED counts | Có nghĩa vụ chưa phát? |
| Age của oldest unpublished event | Có event bị kẹt bao lâu? |
| Publish attempts, failures và broker ACK latency | Relay có hoạt động đúng? |
| Published-to-cleanup age | Có giữ dữ liệu theo policy? |
| Archive backlog, checksum failures | Archive có bảo toàn được dữ liệu? |
| Archive bytes/records verified | Có bằng chứng coverage? |
| Cleanup eligible vs deleted counts | Job có dọn đúng tập? |
| Cleanup errors, duration, batch rate | Có ảnh hưởng hoạt động chính? |
| DB disk, WAL, index bloat và replication lag | Cleanup gây áp lực datastore? |
| Inbox markers theo consumer scope | Dedupe state tăng thế nào? |
| Duplicate delivery và dedupe hit rate | Event được gửi lại bao nhiêu? |
| Dedupe miss on historical replay | Có event cũ bị coi như mới không? |
| Replay jobs running/failed/completed | Khả năng khôi phục đang ở đâu? |
| Replay lag, time to catch up, last contiguous checkpoint | Có tiến độ xử lý thực? |
| DLQ size/oldest age/re-drive count | Có message bị bỏ quên? |
| Consumer lag và checkpoint age | Có nguy cơ vượt broker retention? |
| Reconciliation mismatches/repair actions | Projection có đúng nguồn không? |
| Unsafe deletion prevented count | Có record bị giữ do điều kiện chưa đạt? |
| Manual overrides/audit trail | Ai bỏ qua policy và vì sao? |

### 22.1. Những cảnh báo quan trọng

- Outbox NEW lâu hơn ngưỡng.
- Publisher không còn tiến độ hoặc retry tăng bất thường.
- Archive verification thất bại.
- Khoảng thiếu trong archive manifest.
- Consumer lag tiến gần retention broker.
- DLQ oldest age vượt thời hạn xử lý.
- Cleanup đụng phải record chưa publish hoặc có active lease.
- Re-drive một event đã hết marker mà business operation không có idempotency.
- Số lượng duplicate side effects tăng sau cleanup.
- Reconciliation backlog vượt giới hạn.
- Retention/privacy deletion không đáp ứng nghĩa vụ theo policy.

Một sự kiện PUBLISHED tồn tại lâu không nhất thiết là lỗi; nó có thể nằm trong retention để replay. Cần phân biệt chính sách hợp lệ với cleanup job bị kẹt.

### 22.2. SLO cho khôi phục

Ngoài retention, có thể có mục tiêu:
- Đọc lại dữ liệu 30 ngày gần nhất khi consumer lỗi.
- Rebuild một projection trong thời gian mục tiêu.
- Khôi phục từ archive với điểm mất dữ liệu chấp nhận được.
- Đối soát những message bị bỏ qua trong thời hạn nhất định.

Không tuyên bố “có archive là có thể khôi phục tức thời”. Cần đo RTO/RPO theo nghĩa áp dụng và kiểm tra restore thực tế.

---

## 23. Quy trình cleanup có kiểm soát

### Bước 1 — Chụp hiện trạng vận hành, không sửa dữ liệu

Thu thập:
- Outbox counts theo trạng thái và age.
- Inbox counts theo consumer/generation.
- Broker retention, consumer lag, DLQ backlog.
- Archive coverage và độ tươi.
- Dung lượng DB, index, replication lag.
- Các replay job đang hoạt động.
- Danh sách consumer có side effect và mức bảo vệ idempotency.

### Bước 2 — Viết chính sách retention theo dòng dữ liệu

Mỗi dòng phải có:
- Owner.
- Loại message và dữ liệu.
- Mức đảm bảo publish/consume.
- Retention tối thiểu/tối đa.
- Khả năng replay.
- Dedupe horizon.
- Lý do bảo mật hoặc compliance.
- Cơ chế dọn và archive.
- Điều kiện an toàn và cách rollback/recover.

### Bước 3 — Định nghĩa predicate cleanup

Đối với outbox, predicate có thể gồm:

    status == PUBLISHED
    AND publishedAt < safeCutoff
    AND archivedAndVerified (nếu cần)
    AND noActiveLease
    AND noHoldForIncidentOrCompliance

Đối với inbox, predicate cần:

    status == PROCESSED
    AND processedAt < dedupeSafeCutoff
    AND replay/restore policy allows
    AND no active replay requiring marker
    AND business duplicate effects still protected

Các điều kiện phải được thực thi/kiểm chứng trong schema thật, không chỉ là ghi chú.

### Bước 4 — Dry-run và kiểm tra mẫu

Tạo báo cáo số ứng viên, tuổi, trạng thái, type, tenant/scope, archive coverage. Kiểm tra những record lâu đời nhưng chưa publish, những event có legal hold hoặc đang nằm trong DLQ.

**Dry-run không được xóa hay sửa marker.** Đối chiếu chính sách với owner trước khi chạy.

### Bước 5 — Batch nhỏ, rate limit và khả năng dừng

Chạy theo batch có index, commit ngắn, dừng khi:
- Replication lag tăng quá giới hạn.
- DB latency chính tăng.
- Có deadlock/lock wait bất thường.
- Archive verification không đạt.
- Consumer replay được kích hoạt trong phạm vi cần giữ.
- Đã vượt khối lượng delete tối đa đã phê duyệt.

### Bước 6 — Xác minh sau cleanup

- Oldest unpublished không biến mất chỉ do cleanup.
- Không có trạng thái NEW/IN_FLIGHT bị xóa.
- Archive manifest vẫn đọc/verify được.
- Inbox không mất marker trong cửa sổ có thể re-drive.
- Consumer processing, retries và 5xx không tăng bất thường.
- DB disk/index/replication metrics cải thiện theo thời gian kỳ vọng.
- Số bản ghi xóa khớp báo cáo audit và giới hạn đã đặt.

### Bước 7 — Thử restore và replay

Ít nhất định kỳ chọn một khoảng lịch sử trong retention, phục hồi vào môi trường cách ly và xây projection. Đo số record, checksum, schema conversion, lag, thời gian bắt kịp, sai lệch kết quả. Không xem cleanup hoàn tất bền vững nếu không có bằng chứng restore trong phạm vi cam kết.

---

## 24. Những sai lầm dễ xảy ra

**Sai lầm 1 — Xóa outbox theo created_at mà không xem status.** Một event chưa từng publish có thể biến mất. Chỉ chọn record có bằng chứng publish đủ điều kiện.

**Sai lầm 2 — Xem broker ACK là đã xử lý ở mọi consumer.** Broker nhận message không có nghĩa tất cả nhóm đã hoàn tất business side effects.

**Sai lầm 3 — Inbox TTL bằng broker retention mà quên DLQ/archive.** Event cũ có thể xuất hiện lại sau nhiều tuần.

**Sai lầm 4 — Dùng marker chung cho nhiều handler.** Handler A xử lý xong khiến B bỏ qua dù B chưa thực hiện nhiệm vụ.

**Sai lầm 5 — Dùng max offset làm checkpoint an toàn.** Một offset nhỏ hơn còn in-flight có thể bị bỏ qua khi xử lý song song.

**Sai lầm 6 — Xóa record ngay sau publish rồi tuyên bố replay không giới hạn.** Khi broker cũng purge và không archive, không còn dữ liệu để replay.

**Sai lầm 7 — Archive upload chưa verified nhưng đã đánh dấu archived.** Cleanup có thể xóa bản duy nhất của event.

**Sai lầm 8 — Rebuild read model bằng cách gửi lại mọi event tới business handlers.** Có thể gửi email, tạo vận đơn hoặc thu tiền lần nữa.

**Sai lầm 9 — Dedupe theo eventId nhưng không bảo vệ tác động ngoài DB.** Crash giữa gửi email và ghi marker vẫn có thể lặp.

**Sai lầm 10 — Dùng generated new eventId ở mỗi retry publish.** Consumer không nhận diện cùng một sự kiện.

**Sai lầm 11 — Partition drop vì phần lớn record đã cũ.** Một vài outbox NEW cũ có thể bị xóa cùng partition.

**Sai lầm 12 — Không giữ schema/version đủ lâu.** Dữ liệu được archive nhưng reader không còn giải mã được.

**Sai lầm 13 — Không thử restore.** Checksum, encryption key hoặc manifest lỗi chỉ được phát hiện lúc sự cố lớn.

**Sai lầm 14 — Không có runbook cho database restore.** Inbox marker cũ quay lại, outbox có thể publish trùng, side effect đã có hiệu lực.

**Sai lầm 15 — Không giới hạn tốc độ replay.** Một replay lớn có thể quá tải broker, database và các downstream.

**Sai lầm 16 — Xóa PII khỏi Customer nhưng quên event archive.** Bản sao nhạy cảm vẫn tồn tại và được replay.

**Sai lầm 17 — Giữ tất cả marker vĩnh viễn mà không tính capacity.** Hot DB/index tăng vô hạn; thiếu kế hoạch archive, partition và business idempotency.

**Sai lầm 18 — Chỉ theo dõi số dòng được xóa.** Không biết có làm mất pending message, mất khả năng rebuild hoặc tạo effect trùng hay không.

---

## 25. Kiểm thử cleanup, replay và phục hồi

Chạy các test quan trọng trong môi trường có broker và datastore phù hợp, không chỉ mock một repository.

### 25.1. Outbox publish rồi crash trước mark

1. Order commit và outbox lưu Event E.
2. Publisher gửi E, broker xác nhận.
3. Ngắt publisher trước khi cập nhật trạng thái PUBLISHED.
4. Cleanup không xóa E khi chưa có bằng chứng trạng thái.
5. Publisher restart và gửi lại E cùng eventId.
6. Consumer xử lý một lần theo idempotency.
7. Sau khi publish được xác nhận và lưu đủ retention, cleanup có thể thực hiện theo policy.

### 25.2. Publisher lỗi lâu ngày

1. Ngắt broker hoặc publisher trong khoảng lớn hơn ngưỡng cleanup thông thường.
2. Outbox NEW/RETRY tích tụ.
3. Chạy cleanup; không record chưa publish nào bị xóa.
4. Cảnh báo oldest unpublished age và backlog hoạt động.
5. Khôi phục broker; relay tiếp tục phát.
6. Xác nhận thứ tự/aggregate version và khả năng xử lý trùng.

### 25.3. Consumer crash sau local commit trước ACK

1. Consumer áp dụng projection và insert inbox marker cùng transaction.
2. Kill consumer trước khi ACK offset.
3. Broker redeliver event.
4. Consumer phát hiện marker, không apply lần hai.
5. ACK tiếp tục an toàn.

### 25.4. Inbox marker hết hạn rồi DLQ replay

1. Có event E đã xử lý.
2. Đưa bản sao E vào DLQ theo kịch bản mô phỏng.
3. Cleanup marker theo chính sách thử nghiệm.
4. Re-drive E.
5. Nếu handler có side effect, business idempotency phải chặn effect trùng; nếu không, policy phải giữ marker hoặc từ chối re-drive.
6. Ghi metric và audit của hành vi.

### 25.5. Rebuild projection từ archive

1. Chọn khoảng event đã purge khỏi hot outbox/broker.
2. Đọc manifest và kiểm tra checksum.
3. Deserialize các schemaVersion cũ.
4. Tạo projection namespace mới.
5. Replay theo checkpoint và version guard.
6. So sánh với source-of-truth hoặc mẫu dữ liệu có chứng cứ.
7. Thử crash và resume giữa batch.
8. Xác nhận không gửi email/charge/shipment trong replay.

### 25.6. Restore database cũ

1. Tạo side effect và publish event mới.
2. Restore bản backup trước thời điểm ấy trong môi trường thử.
3. Phát hiện outbox/inbox DB khác broker và provider.
4. Chạy quy trình đối soát idempotency và offset.
5. Không phát sinh charge hoặc shipment trùng.
6. Rebuild projection theo checkpoint an toàn.

### 25.7. Xử lý race

Chạy cleanup đồng thời với relay claim và archive:
- Không xóa event IN_FLIGHT chưa có ACK.
- Không xóa event archive chưa verified.
- Không khóa kéo dài gây tắc business transaction.
- Một worker cũ không ghi đè state sau khi lease hết hạn.
- Replay lock/generation không bị cleanup bỏ qua.

### 25.8. Privacy/retention

Tạo message chứa dữ liệu giả nhạy cảm, thực hiện redaction/deletion workflow:
- Bản sao trong hot DB, broker, archive, DLQ và projection được xử lý đúng policy.
- Dữ liệu cần giữ cho audit được tách/giảm thiểu.
- Replay không tái tạo lại PII đã phải xóa.
- Các bản backup/khóa mã hóa được xử lý theo quy định.

---

## 26. Tình huống mẫu: Order, Notification và Analytics

Giả định:
- Order phát OrderConfirmed qua outbox.
- Broker giữ message 7 ngày.
- Notification gửi email xác nhận.
- Analytics xây projection phục vụ báo cáo.
- DLQ giữ lỗi tối đa 45 ngày.
- Một bản archive hỗ trợ xây lại Analytics 180 ngày.
- Inbox Notification ban đầu dọn marker sau 14 ngày.
- Inbox Analytics ban đầu dọn marker sau 30 ngày.

### 26.1. Phân tích rủi ro

Đối với Analytics:
- Khi rebuild vào namespace mới, marker cũ không nhất thiết được dùng.
- Rebuild có thể chủ động apply lại toàn bộ event vào projection mới.
- Cần schema/ordering/snapshot đủ nghĩa và không gây side effects.
- TTL marker có thể ngắn hơn archive horizon **nếu** replay được cách ly và xử lý idempotent trong generation mới.

Đối với Notification:
- Replay từ DLQ 45 ngày sau có thể gặp event đã gửi email nhưng marker 14 ngày đã bị xóa.
- Nếu không có business notificationIntentId/unique constraint hoặc provider idempotency, có nguy cơ email bị gửi lại.
- Cần thay đổi chính sách giữ marker hoặc bổ sung ledger chống trùng bền lâu hơn.
- Replay Analytics không được tự động đưa OrderConfirmed cũ vào Notification production.

Đối với Order:
- Chỉ dọn outbox sau khi publish được xác nhận.
- Nếu archive đủ để rebuild Analytics, không nhất thiết giữ hot outbox 180 ngày.
- Nếu archive chưa có đầy đủ contract, không tuyên bố khả năng rebuild từ 180 ngày trước.

### 26.2. Một policy minh họa

| Thành phần | Chính sách có thể chọn | Điều kiện an toàn |
|---|---|---|
| Outbox NEW/RETRY | Không TTL-xóa mù | Chỉ hoàn tất khi publish/review theo contract |
| Outbox PUBLISHED | Giữ ngắn hạn rồi archive/purge | Broker ACK bền vững, archive verified nếu cần |
| Notification inbox | Giữ qua cửa sổ re-drive hoặc dùng business ledger dài hạn | Không gửi email trùng |
| Analytics inbox | Giữ theo nhu cầu live consumer | Replay rebuild dùng namespace/generation riêng |
| DLQ | 45 ngày theo ví dụ | Không bỏ message có nghĩa vụ chưa giải quyết |
| Archive | 180 ngày theo ví dụ | Manifest, schema, checksum, restore tests |
| Consumer checkpoint | Theo partition và processed-contiguous progress | Không skip event in-flight |

Đây là đề xuất kiến trúc minh họa để thảo luận; không phải thời hạn mặc định cho hệ sản xuất hay hướng dẫn pháp lý.

---

## 27. Checklist trước khi bật job dọn định kỳ

- [ ] Đã xác định owner của từng bảng và message type.
- [ ] Đã ghi rõ broker ACK nghĩa là gì.
- [ ] Không có outbox NEW/RETRY/CLAIMED bị chọn xóa chỉ vì tuổi.
- [ ] Mọi record cần replay có archive/event store/snapshot phù hợp.
- [ ] Archive manifest có checksum/schema và đã thử restore.
- [ ] Có hiểu biết về broker retention, DLQ retention và backup horizon.
- [ ] Inbox dedupe scope phân biệt các handler/generation cần thiết.
- [ ] Consumer có side effect có business idempotency khi cần.
- [ ] Replay không thể vô tình gửi lại email/charge/shipment.
- [ ] Watermark/checkpoint không nhảy qua offset chưa hoàn thành.
- [ ] Batch/partition cleanup không chặn transaction nghiệp vụ.
- [ ] Có rate limit, dry-run, ngưỡng dừng và audit.
- [ ] Có monitoring oldest unpublished, DLQ, lag và archive gaps.
- [ ] Có runbook restore sau sự cố hoặc sau khi dọn sai.
- [ ] Chính sách dữ liệu nhạy cảm, xóa và thời hạn lưu được áp dụng.
- [ ] Có test race, crash, duplicate, schema cũ và replay lịch sử.

Checklist này hỗ trợ triển khai nhưng không thay thế thiết kế đặc thù của hệ thống.

---

## 28. Mẫu ADR cho cleanup và replay

~~~text
ADR: Outbox/Inbox Cleanup và Replay cho <service/stream>

Bối cảnh và mục tiêu:
Service owner / consumer owners:
Business event types và side effects:
Nguồn dữ liệu có thẩm quyền:

Outbox:
  Transaction boundary:
  Publish ACK semantics:
  Retry/lease/status model:
  Eligibility cleanup:
  Retention và archive policy:

Inbox:
  Dedupe scope/unique key:
  Transaction với local side effect:
  Thời gian message có thể xuất hiện lại:
  Dedupe retention và alternative business idempotency:
  Concurrent processing và checkpoint policy:

Broker và DLQ:
  Topic retention:
  DLQ retention và re-drive:
  Consumer lag/recovery assumptions:

Archive/Snapshot:
  Mục đích replay được hỗ trợ:
  Event schema versions:
  Manifest/checksum/encryption:
  Snapshot/catch-up boundaries:
  Restore test và expected recovery time:

Replay:
  Re-drive vs rebuild vs audit:
  Có side effects không:
  Generation/namespace:
  Rate limit và access control:
  Checkpoint/ordering/reconciliation:
  Quy trình canary/rollback:

Cleanup:
  Batch size/partitioning:
  Dry-run/approval:
  Index/DB load limits:
  Pause conditions:
  Audit trail:

Security/Privacy:
  Data classification:
  Retention/deletion obligations:
  DLQ/archive/backup handling:

Observability:
  Oldest unpublished:
  Inbox dedupe failures:
  DLQ backlog:
  Archive verification:
  Replay duration/lag:
  Alerts và runbook:

Các failure tests:
Rủi ro còn lại, owner và thời điểm review:
~~~

---

## 29. Bài thực hành: khi xóa đúng theo ngày nhưng sai theo nghĩa vụ

Một nền tảng có kiến trúc:

    Payment -> Outbox -> Kafka -> OrderProjection
                             -> Notification
                             -> FraudAnalytics

Giả định:
- Payment commit PaymentCaptured và outbox trong cùng transaction.
- Relay publish với at-least-once, eventId ổn định.
- Broker topic giữ 10 ngày.
- DLQ được điều tra trong 60 ngày.
- Notification đã gửi email sau PaymentCaptured, có inbox marker giữ 14 ngày.
- FraudAnalytics giữ inbox 90 ngày và có thể replay sự kiện trong 365 ngày từ archive.
- Archive upload ghi object storage, nhưng job hiện đánh archived=TRUE **trước khi upload**.
- Một cron job xóa mọi outbox record older than 30 days, không xét status.
- Một consumer commit offset lớn nhất đã nhìn thấy dù xử lý song song.
- Sau một sự cố, operator replay PaymentCaptured từ archive vào cùng topic production.

### Yêu cầu

1. Chỉ ra vì sao cron DELETE theo created_at có thể làm mất một PaymentCaptured chưa publish.
2. Giải thích crash window giữa broker ACK và mark SENT, và vì sao consumer cần idempotency.
3. Viết predicate cleanup outbox an toàn hơn, có status và archive verification.
4. Phân tích lỗi archive đánh marked=true trước upload và thiết kế protocol archive/manifest có retry.
5. Tính rủi ro khi Notification inbox chỉ giữ 14 ngày nhưng DLQ re-drive 60 ngày.
6. Đề xuất một notificationIntentId hoặc business key giúp chặn gửi email lần hai.
7. Giải thích cách FraudAnalytics rebuild projection sau 300 ngày mà không kích hoạt Payment/Notification effects.
8. Thiết kế replay generation/namespace và cách quản lý consumer scope.
9. Với offsets 110,111,112 được xử lý song song nhưng 111 chưa xong, checkpoint nào có thể commit an toàn theo quy ước đã chọn?
10. Nêu vai trò schema registry/upcaster đối với event lịch sử có schemaVersion cũ.
11. Đề xuất batch cleanup SQL, index và ngưỡng dừng khi replication lag tăng.
12. Liệt kê metric và alert cho oldest unpublished, DLQ backlog, inbox marker expiry, archive verification và replay lag.
13. Thiết kế test publisher crash sau broker ACK, consumer crash trước ACK, restore database cũ và replay tạo side effect.
14. Giải thích cách xử lý yêu cầu xóa dữ liệu nhạy cảm trong archive và DLQ theo chính sách.
15. Soạn ADR ngắn cho retention, archive, dedupe horizon và quyền chạy re-drive.

### Gợi ý giải

Không được xóa outbox chưa publish chỉ vì record cũ. Archive phải được ghi, xác minh rồi mới đánh dấu được phép purge. Inbox TTL phải tương thích với mọi đường message có thể xuất hiện lại, hoặc có ràng buộc idempotency nghiệp vụ còn hiệu lực. Rebuild Analytics nên dùng consumer generation mới vào projection cách ly, không phát lại side effects production.

Một checkpoint offset phải phản ánh tiến độ đã xử lý liên tục theo partition, không phải offset lớn nhất đã nhận. Ngoài kiểm tra dữ liệu, cần thử khả năng restore archive thật, vì một file lưu lâu nhưng không còn schema/key hoặc bị lỗi checksum không đáp ứng mục tiêu replay.

---

## 30. Tổng kết

1. **Outbox giữ nghĩa vụ phát event cùng transaction nghiệp vụ**; không xóa NEW/RETRY chỉ vì quá tuổi.
2. **Inbox giữ bằng chứng chống trùng theo một phạm vi xử lý**; xóa marker có thể khiến event cũ gây side effect lại.
3. **Độ dài retention phải tính cả retry, broker, DLQ, replay, backup và restore**, không chỉ TTL của topic.
4. **Broker ACK không chứng minh mọi consumer đã xử lý**, và outbox published không tự có nghĩa event không bao giờ cần lại.
5. **Archive/snapshot phải đủ nghĩa và đã kiểm tra restore** trước khi purge bản hot nếu cam kết hỗ trợ replay.
6. **Replay projection và replay business side effect là hai hoạt động khác nhau**; dùng namespace/generation, idempotency và quyền thao tác phù hợp.
7. **Checkpoints cần đảm bảo tiến độ liên tục theo partition**, không nhảy qua message còn in-flight.
8. **Cleanup phải chạy theo batch/partition có điều kiện, concurrency control, rate limit và audit**, không phải một DELETE toàn bảng.
9. **Schema evolution, tombstone, ordering và quyền riêng tư** là một phần khả năng xử lý lại event lịch sử.
10. **Chỉ tuyên bố có thể khôi phục khi đã thử phục hồi thực sự**: từ archive/checkpoint đến projection đúng và không tạo tác dụng phụ trùng.
