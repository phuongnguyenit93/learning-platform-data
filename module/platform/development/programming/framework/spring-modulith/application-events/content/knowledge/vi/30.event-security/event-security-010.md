# Retention và xóa dữ liệu

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module trao đổi thông tin nghiệp vụ và hỗ trợ phục hồi xử lý khi có lỗi. Để làm được điều đó, hệ thống thường lưu event ở nhiều nơi: Event Publication Registry, transactional outbox, inbox hoặc deduplication store, broker, dead-letter queue, log, trace, read model và backup. Mỗi bản sao có mục đích, thời hạn lưu và cách xóa khác nhau.

**Retention** là chính sách xác định dữ liệu nào được giữ, giữ trong bao lâu, ở đâu và khi nào được xóa hoặc ẩn danh. **Data deletion** là quy trình xóa dữ liệu khỏi những nơi đang lưu hoặc xử lý dữ liệu đó, theo yêu cầu nghiệp vụ, quyền riêng tư, hợp đồng và quy định áp dụng. Hai việc phải được thiết kế cùng nhau: giữ event đủ lâu để giao nhận và phục hồi đáng tin cậy, đồng thời tránh lưu payload chứa dữ liệu cá nhân lâu hơn mục đích cần thiết.

Một chính sách tốt không chỉ đặt TTL cho broker. Nó theo dõi vòng đời của dữ liệu từ lúc event được tạo, qua publication, transport và consumer, tới các bản sao trong projection, log, archive và backup. Chính sách cũng phải xử lý message đang chờ, retry, replay và event cũ đến sau khi dữ liệu đã được xóa.

## 1. Vì sao event cần chính sách retention?

Event thường được xem là bản ghi về điều đã xảy ra. Tuy nhiên, event có thể chứa thông tin cá nhân, dữ liệu tài chính, địa chỉ giao hàng, thông tin thiết bị hoặc dữ liệu kinh doanh nhạy cảm. Một event có thể được sao chép sang nhiều hệ thống và tồn tại lâu hơn bản ghi nghiệp vụ ban đầu.

Các lý do cần retention rõ ràng:

- **Phục hồi:** giữ publication và message đủ lâu để retry sau outage hoặc restart.
- **Đối soát:** lưu dấu vết cần thiết để giải thích một quyết định nghiệp vụ.
- **Replay:** cho phép xây dựng lại projection hoặc xử lý lại event trong một khoảng thời gian được kiểm soát.
- **Vận hành:** giới hạn dung lượng của broker, registry, inbox, log và archive.
- **Quyền riêng tư:** giảm thời gian lưu dữ liệu cá nhân và hỗ trợ yêu cầu xóa khi có căn cứ.
- **Bảo mật:** giảm lượng dữ liệu có thể bị lộ nếu một kho hoặc tài khoản bị xâm phạm.

Giữ dữ liệu vô thời hạn làm tăng chi phí lưu trữ, bề mặt tấn công và phạm vi ảnh hưởng khi có sự cố. Xóa quá sớm lại có thể làm mất khả năng retry, điều tra hoặc xây dựng lại dữ liệu. Vì vậy, thời hạn phải xuất phát từ mục đích sử dụng và rủi ro cụ thể của từng loại dữ liệu.

## 2. Phân loại dữ liệu trước khi đặt thời hạn

Không phải mọi thứ liên quan đến một event đều có cùng độ nhạy hoặc cùng nhu cầu lưu trữ. Hãy phân loại riêng payload, metadata, trạng thái xử lý và telemetry.

| Loại dữ liệu | Ví dụ | Cân nhắc retention |
|---|---|---|
| Payload nghiệp vụ | Tên, địa chỉ, số tiền, nội dung đơn hàng | Chỉ giữ trong thời gian cần cho mục đích đã xác định |
| Event metadata | eventId, eventType, occurredAt, schemaVersion | Có thể giữ lâu hơn payload nếu không nhận diện cá nhân |
| Publication state | listener, trạng thái completed/incomplete, thời điểm | Giữ theo nhu cầu retry, vận hành và audit |
| Outbox/inbox | message ID, trạng thái gửi/nhận, attempt | Giữ qua retry/replay horizon và thời gian đối soát |
| Broker message | body, headers, routing metadata | Phụ thuộc queue/topic retention, TTL và DLQ policy |
| Log và trace | exception, correlation ID, span attributes | Giới hạn thời gian, nội dung và quyền truy cập |
| Projection/cache | bản sao dữ liệu phục vụ truy vấn | Phải có cơ chế cập nhật và xóa theo nguồn |
| Backup/archive | bản sao database hoặc event store | Có lịch hết hạn và quy trình xử lý yêu cầu xóa |

Phân loại cũng cần xác định dữ liệu nào có thể nhận diện trực tiếp một người, dữ liệu nào có thể liên kết lại bằng khóa khác và dữ liệu nào thực sự đã được ẩn danh. Một mã định danh ngẫu nhiên không mặc nhiên là anonymous nếu hệ thống vẫn có bảng ánh xạ tới chủ thể.

Nên lập data inventory cho từng event type: producer, consumer, field được công bố, nơi lưu, mục đích, owner, thời hạn và cách xóa. Đây là cơ sở để đánh giá tác động khi thay đổi schema hoặc nhận yêu cầu xóa dữ liệu.

## 3. Data minimization ngay từ lúc thiết kế event

Cách hiệu quả nhất để giảm gánh nặng retention là không đưa dữ liệu không cần thiết vào event. Integration event nên chỉ chứa field mà consumer cần để thực hiện use case đã xác định.

Ví dụ, event OrderConfirmed có thể mang orderId, eventId, occurredAt và các giá trị tổng hợp cần cho consumer. Nếu consumer chỉ cần địa chỉ để tạo nhãn giao hàng, hãy cân nhắc gửi một tham chiếu tới hồ sơ giao hàng hoặc một snapshot có thời hạn phù hợp, thay vì đưa toàn bộ hồ sơ khách hàng vào mọi event.

Một số nguyên tắc:

- Không đưa mật khẩu, access token, secret hoặc thông tin xác thực vào event.
- Không sao chép toàn bộ entity hoặc object graph vào payload.
- Tách thông tin nhận diện khỏi dữ liệu nghiệp vụ khi có thể.
- Dùng reference có kiểm soát khi consumer có thể lấy dữ liệu cần thiết từ module sở hữu.
- Đặt mục đích và thời hạn cho field nhạy cảm ngay trong contract.
- Tránh đưa payload vào log, trace, metric label hoặc exception message.
- Version schema có xét tới việc loại bỏ field nhạy cảm ở phiên bản sau.

Data minimization không có nghĩa mọi consumer đều phải gọi ngược producer cho từng field. Cần cân bằng giữa coupling runtime, khả năng hoạt động độc lập và lượng dữ liệu được sao chép. Nếu snapshot là cần thiết để xử lý đúng tại thời điểm event xảy ra, hãy giới hạn snapshot ở dữ liệu thực sự cần và quản lý retention của mọi bản sao.

## 4. Retention theo từng kho dữ liệu

Một event có thể đi qua nhiều kho có vòng đời khác nhau. Bảng sau là khung thiết kế; thời hạn cụ thể phải được xác định theo SLO, retry horizon, yêu cầu nghiệp vụ và quy định áp dụng, không dùng một con số chung cho mọi hệ thống.

| Kho | Dữ liệu được giữ | Điều kiện kết thúc vòng đời |
|---|---|---|
| Event Publication Registry | Event publication và trạng thái listener | Publication hoàn tất, hết thời hạn phục hồi và qua thời gian audit cần thiết |
| Transactional outbox | Event/command chờ gửi và trạng thái gửi | Đã gửi/đối soát xong, qua retention vận hành |
| Consumer inbox/dedup | Message identity và trạng thái xử lý | Hết retry/replay horizon và không còn yêu cầu chống trùng |
| Broker queue/topic | Message body, header và offset | Hết retention hoặc đã được tiêu thụ theo chính sách |
| Retry queue/DLQ | Message lỗi và metadata điều tra | Đã xử lý, replay hoặc hết thời hạn lưu lỗi |
| Log/trace | Sự kiện vận hành và dấu vết xử lý | Hết thời hạn giám sát/điều tra |
| Read model/cache | Bản sao phục vụ truy vấn | Được cập nhật, invalidated hoặc xóa theo nguồn |
| Backup/archive | Bản sao phục hồi hoặc lưu trữ | Hết lịch backup/archive và hoàn tất xử lý deletion theo chính sách |

Không xóa một publication chỉ vì nó đã cũ. Publication incomplete có thể là dấu hiệu listener hoặc adapter đang gặp sự cố. Trước khi purge, cần xác định event đã được xử lý hay chưa, có thể resubmit an toàn không và có nghĩa vụ đối soát nào còn tồn tại. Publication completed có thể được dọn theo retention đã định sau khi không còn cần cho vận hành.

Với outbox, bản ghi đã gửi thường được giữ thêm một khoảng để đối soát và điều tra. Với inbox, dấu dedup phải tồn tại ít nhất trong khoảng thời gian message có thể được giao lại hoặc replay. Nếu broker cho phép replay rất lâu, cần một business ledger hoặc khóa idempotency bền vững hơn TTL ngắn của inbox.

## 5. Xác định retention window từ mục đích

Mỗi loại dữ liệu nên có một retention window được giải thích bằng mục đích, không chỉ là giá trị cấu hình.

Hãy trả lời các câu hỏi:

1. Dữ liệu cần cho mục đích nghiệp vụ hoặc pháp lý nào?
2. Consumer có thể xử lý trễ tối đa bao lâu?
3. Retry, DLQ và replay có thể kéo dài tới thời điểm nào?
4. Cần lưu lịch sử bao lâu để điều tra sự cố hoặc đối soát?
5. Có dữ liệu cá nhân hoặc bí mật nào trong payload?
6. Ai sở hữu dữ liệu và ai phê duyệt việc xóa?
7. Khi xóa bản gốc, những bản sao nào phải được cập nhật hoặc xóa?
8. Backup có hết hạn theo lịch riêng hay không?
9. Có legal hold hoặc yêu cầu lưu trữ bắt buộc đang áp dụng không?

Retention window cho inbox thường liên quan tới thời gian tối đa broker có thể redeliver hoặc operator có thể replay. Retention của log có thể ngắn hơn vì log chỉ cần phục vụ giám sát và điều tra trong một khoảng nhất định. Dữ liệu giao dịch có thể phải lưu lâu hơn theo nghĩa vụ kế toán hoặc hợp đồng, nhưng không vì thế mà mọi payload event chứa dữ liệu cá nhân cũng phải được giữ nguyên trong cùng thời gian.

Chính sách cần nêu rõ owner, thời hạn bắt đầu tính từ mốc nào, timezone, hành động khi hết hạn và ngoại lệ. Ví dụ, retention có thể tính từ lúc event được tạo, publication completed, tài khoản đóng hoặc mục đích xử lý kết thúc. Mốc bắt đầu khác nhau sẽ tạo kết quả xóa khác nhau.

## 6. Event Publication Registry và publication retention

Spring Modulith Event Publication Registry theo dõi publication của application event tới các transactional listeners. Tùy cấu hình persistence, dữ liệu publication có thể chứa hoặc tham chiếu tới event cần được listener xử lý lại. Vì vậy, registry có thể lưu payload nghiệp vụ chứ không chỉ một cờ trạng thái.

Cần thiết kế vòng đời riêng cho registry:

- Giữ publication incomplete để điều tra và phục hồi.
- Theo dõi tuổi publication, listener liên quan và lỗi cuối cùng.
- Sau khi publication completed, chỉ purge khi đã qua khoảng thời gian vận hành/audit cần thiết.
- Không xóa publication incomplete hàng loạt bằng một tác vụ cleanup không kiểm tra.
- Xem xét dữ liệu event được lưu trong registry có chứa thông tin cá nhân hay không.
- Khi có yêu cầu xóa, xác định publication còn tồn tại trong registry và khả năng resubmit sau khi xóa.

Nếu một event đã bị xóa dữ liệu theo yêu cầu nhưng publication cũ vẫn có thể được resubmit, dữ liệu có thể xuất hiện lại trong consumer. Cần có cơ chế ngăn replay event đã bị thu hồi hoặc bảo đảm payload được redacted trước khi resubmit, tùy yêu cầu và kiến trúc.

API, endpoint quản lý và cơ chế cleanup cụ thể phụ thuộc phiên bản Spring Modulith cùng loại persistence đang sử dụng. Hãy kiểm tra cấu hình thực tế của ứng dụng trước khi chọn cách purge; không giả định registry tự xóa mọi publication completed hoặc tự xử lý yêu cầu xóa dữ liệu cá nhân.

## 7. Outbox, inbox và deduplication retention

Transactional outbox giữ event hoặc command cần gửi sau khi transaction nghiệp vụ commit. Bản ghi outbox chưa gửi là dữ liệu vận hành quan trọng; xóa nó có thể làm mất thông điệp cần giao. Bản ghi đã gửi có thể được archive hoặc purge sau khi đáp ứng thời gian đối soát và audit.

Inbox hoặc deduplication store giữ dấu message đã xử lý. Nếu xóa dấu quá sớm, một message cũ được redeliver hoặc replay có thể chạy tác dụng phụ lần nữa. Do đó, retention của inbox phải bao phủ retry horizon, broker retention, DLQ retention và khoảng thời gian replay được cho phép.

Một số nguyên tắc:

- Không purge outbox ở trạng thái PENDING hoặc đang được dispatcher claim.
- Chỉ dọn bản ghi SENT sau khi qua thời hạn đối soát được quy định.
- Không xóa inbox PROCESSING khi lease còn hiệu lực.
- Với inbox COMPLETED, giữ dấu ít nhất tới khi không còn đường giao lại hợp lệ.
- Nếu replay được phép vô thời hạn, cân nhắc lưu idempotency ledger lâu dài hoặc tách replay thành consumer generation mới.
- Ghi nhận số lượng và kết quả của mỗi batch cleanup.

Dọn inbox và outbox nên dùng batch nhỏ, có giới hạn và có thể tiếp tục sau lỗi. Tránh một transaction xóa hàng triệu bản ghi gây lock kéo dài, tăng replication lag hoặc ảnh hưởng xử lý event mới.

## 8. Broker retention, message TTL và dead-letter queue

Broker có thể giữ message theo nhiều chính sách: thời hạn message, thời gian lưu log/segment, giới hạn dung lượng queue, số lượng message hoặc cấu hình dead-letter. Các khái niệm này khác nhau giữa RabbitMQ, Kafka và các transport khác.

Với RabbitMQ, queue/message TTL và dead-letter topology có thể ảnh hưởng thời gian message tồn tại hoặc được chuyển sang DLQ. Với Kafka, retention theo thời gian hoặc dung lượng áp dụng cho segment của topic; consumer offset và compaction có semantics riêng. Không thể dùng một cấu hình TTL chung cho mọi broker.

Cần xác định:

- Message hết hạn có bị loại bỏ hay dead-letter?
- DLQ giữ payload trong bao lâu?
- Operator được phép replay DLQ trong khoảng thời gian nào?
- Message có thể tồn tại trong queue không hoạt động hoặc consumer bị dừng bao lâu?
- Broker backup/replication có giữ bản sao sau khi message hết retention không?
- Header có chứa thông tin cá nhân hoặc secret không?

DLQ thường chứa payload lỗi, có thể gồm dữ liệu nhạy cảm. Giới hạn quyền đọc DLQ, đặt retention, mã hóa và quy trình export. Không dùng DLQ làm kho lưu trữ vô thời hạn. Nếu cần giữ mẫu lỗi để điều tra, cân nhắc lưu metadata đã giảm thiểu hoặc payload được mã hóa trong kho có kiểm soát riêng.

## 9. Quy trình xóa dữ liệu xuyên qua các consumer

Một yêu cầu xóa có thể ảnh hưởng tới nhiều module và hệ thống. Producer thường không thể tự xóa dữ liệu trong database, cache hoặc archive của tất cả consumer. Cần một quy trình phối hợp qua các hợp đồng được công bố.

Một luồng khái quát:

~~~mermaid
flowchart TD
    A["Yêu cầu xóa được xác thực"] --> B["Xác định subject và phạm vi dữ liệu"]
    B --> C["Tạo deletion operation"]
    C --> D["Ghi command/event xóa bền vững"]
    D --> E["Consumer nhận yêu cầu"]
    E --> F["Xóa hoặc ẩn danh bản sao cục bộ"]
    F --> G["Ghi nhận kết quả và version"]
    G --> H["Phát deletion acknowledgement"]
    H --> I["Theo dõi đủ consumer"]
    I --> J["Đóng yêu cầu hoặc chuyển ngoại lệ"]
~~~

Một deletion operation nên có định danh riêng, phạm vi dữ liệu, chủ thể hoặc business key được bảo vệ, thời điểm yêu cầu, trạng thái và correlation ID. Event xóa không nên chứa toàn bộ dữ liệu cá nhân cần xóa. Chỉ truyền định danh tối thiểu để consumer tìm bản sao, với kiểm soát quyền truy cập và xác thực nguồn yêu cầu.

Mỗi consumer chịu trách nhiệm xóa hoặc ẩn danh dữ liệu thuộc phạm vi mình quản lý, sau đó trả kết quả. Producer hoặc process manager theo dõi consumer nào đã xác nhận, consumer nào đang retry và trường hợp nào cần xử lý thủ công. Một lần publish deletion event thành công không đồng nghĩa toàn bộ bản sao đã được xóa.

## 10. Ngăn event cũ làm dữ liệu xuất hiện trở lại

Một rủi ro quan trọng là dữ liệu bị xóa nhưng event cũ vẫn nằm trong broker, DLQ, archive hoặc publication registry. Nếu event được replay sau khi xóa, consumer có thể tái tạo dữ liệu đã bị xóa.

Cần có cơ chế chống tái xuất hiện:

- Lưu deletion marker hoặc tombstone theo subject/business key.
- Gắn version hoặc deletion generation vào dữ liệu và event.
- Consumer kiểm tra marker trước khi áp dụng event cũ.
- Từ chối event có version thấp hơn deletion generation.
- Giữ marker đủ lâu để bao phủ mọi retry và replay có thể xảy ra.
- Khi rebuild projection, áp dụng deletion marker trước hoặc đồng bộ với event history.

Ví dụ, CustomerDeleted tạo một tombstone với customerId và generation 12. Một CustomerAddressChanged cũ mang generation 11 đến sau đó phải bị bỏ qua hoặc cách ly. Nếu chỉ xóa row hiện tại mà không lưu marker, event cũ có thể tạo lại row.

Tombstone cũng là dữ liệu và cần retention riêng. Nếu event log có thể replay vô thời hạn, marker phải tồn tại đủ lâu hoặc quá trình rebuild phải có danh sách xóa bền vững khác. Xóa tombstone quá sớm có thể làm mất hiệu lực của yêu cầu xóa.

## 11. Xóa, ẩn danh và pseudonymization

Ba hành động này có ý nghĩa khác nhau:

| Hành động | Kết quả | Lưu ý |
|---|---|---|
| Xóa (deletion) | Loại bỏ dữ liệu khỏi nơi lưu theo phạm vi xác định | Cần xét bản sao, index, cache và backup |
| Ẩn danh (anonymization) | Biến dữ liệu thành dạng không thể liên kết lại với cá nhân bằng phương tiện hợp lý | Không giữ bảng ánh xạ hoặc khóa tái nhận diện |
| Giả danh (pseudonymization) | Thay định danh trực tiếp bằng mã khác | Vẫn có thể là dữ liệu cá nhân nếu có thể liên kết lại |

Hash email hoặc mã hóa định danh không tự động biến dữ liệu thành anonymous. Nếu hệ thống vẫn có thể đối chiếu hoặc giải mã, dữ liệu thường vẫn cần được quản lý như dữ liệu có thể nhận diện.

Nếu nghiệp vụ cần giữ số liệu tổng hợp, hãy xem xét anonymization thực sự hoặc aggregation trước khi xóa dữ liệu nhận diện. Cần đánh giá khả năng tái nhận diện khi kết hợp nhiều trường như thời gian, địa điểm, giá trị giao dịch và nhóm nhỏ.

Với dữ liệu cần giữ vì nghĩa vụ pháp lý hoặc tranh chấp, có thể cần hạn chế mục đích truy cập, tách kho lưu trữ và đặt legal hold theo quy trình được phê duyệt. Không nên gọi dữ liệu là đã xóa nếu nó vẫn còn ở một kho hoạt động mà người dùng hoặc consumer có thể truy cập.

## 12. Cryptographic erasure và giới hạn của nó

Cryptographic erasure là cách làm dữ liệu không thể giải mã bằng cách hủy khóa mã hóa cần thiết. Cách này có thể hữu ích với dữ liệu được mã hóa bằng khóa riêng theo chủ thể hoặc theo nhóm dữ liệu, nhưng chỉ hiệu quả khi mọi bản sao ciphertext đều phụ thuộc vào khóa đã hủy và không còn bản sao khóa có thể khôi phục.

Cần kiểm tra:

- Payload đã được mã hóa trước khi lưu ở tất cả kho liên quan chưa?
- Khóa có được tách biệt và quản lý qua KMS/HSM không?
- Backup có chứa bản sao khóa hoặc plaintext không?
- Log, trace, index và cache có lưu dữ liệu chưa mã hóa không?
- Khóa có được dùng chung cho nhiều chủ thể không?
- Có bản export hoặc archive bên ngoài quy trình key management không?

Nếu một khóa mã hóa được dùng chung cho nhiều khách hàng, hủy khóa sẽ ảnh hưởng tới tất cả dữ liệu dùng khóa đó. Nếu plaintext đã được ghi vào log hoặc backup, hủy khóa của database không xóa các bản plaintext đó. Cryptographic erasure cần được thiết kế từ đầu và được kiểm chứng; nó không phải cách khắc phục tự động cho hệ thống đã lưu dữ liệu không mã hóa.

## 13. Backup, archive và khôi phục sau xóa

Backup là một phần thường bị bỏ sót trong quy trình xóa. Dữ liệu có thể đã được xóa khỏi database chính nhưng vẫn tồn tại trong snapshot, backup offline, archive hoặc bản sao ở môi trường phục hồi thảm họa.

Chính sách cần xác định:

- Backup có thời hạn hết hạn tự động và được kiểm soát truy cập không?
- Yêu cầu xóa có được áp dụng trực tiếp vào mọi backup hay thông qua expiry theo lịch?
- Khi restore một backup cũ, làm thế nào áp dụng lại deletion marker và yêu cầu xóa đã phát sinh sau thời điểm backup?
- Có cách nào ngăn dữ liệu đã xóa được phục hồi vào môi trường production?
- Archive nào phải giữ vì nghĩa vụ pháp lý và ai được quyền truy cập?

Một mẫu thường dùng là giữ deletion ledger hoặc tombstone bên ngoài backup snapshot. Khi restore, hệ thống áp dụng lại các yêu cầu xóa đã ghi nhận sau thời điểm snapshot trước khi mở dữ liệu cho người dùng hoặc consumer. Ledger phải được bảo vệ và có retention phù hợp để không bị mất cùng backup cũ.

Không nên tuyên bố xóa hoàn toàn ngay khi bản ghi bị xóa khỏi database chính nếu backup còn tồn tại và chính sách yêu cầu chờ hết chu kỳ backup. Hãy mô tả chính xác trạng thái: đã xóa khỏi hệ thống hoạt động, đang chờ backup hết hạn hoặc đã hoàn tất theo quy trình đã định.

## 14. Legal hold và ngoại lệ lưu trữ

Có thể có trường hợp dữ liệu cần được giữ lại vì nghĩa vụ kế toán, tranh chấp, kiểm toán hoặc yêu cầu pháp lý hợp lệ. Legal hold cần có quy trình xác nhận, phạm vi, owner, ngày bắt đầu, lý do, người phê duyệt và điều kiện kết thúc.

Khi legal hold có hiệu lực:

- Chỉ giữ đúng dữ liệu nằm trong phạm vi hold.
- Hạn chế quyền đọc và sử dụng dữ liệu theo mục đích đã phê duyệt.
- Không để hold tự động lan sang toàn bộ event hoặc mọi dữ liệu của chủ thể nếu không cần.
- Ghi audit tối thiểu cho thao tác truy cập và thay đổi trạng thái hold.
- Đánh giá lại định kỳ và giải phóng hold khi căn cứ không còn.
- Sau khi hold kết thúc, đưa dữ liệu trở lại lịch retention/xóa bình thường.

Không tự suy luận rằng mọi event giao dịch phải được giữ vĩnh viễn vì có thể cần audit. Hãy xác định nghĩa vụ thực tế theo loại dữ liệu, khu vực pháp lý và chính sách tổ chức; cần owner pháp lý hoặc compliance phê duyệt các ngoại lệ.

## 15. Audit việc xóa mà không giữ lại dữ liệu đã xóa

Hệ thống thường cần chứng minh yêu cầu xóa đã được tiếp nhận và xử lý. Audit record nên ghi metadata tối thiểu:

- deletionOperationId;
- loại dữ liệu hoặc nhóm consumer;
- thời điểm nhận và hoàn tất;
- trạng thái từng bước;
- kết quả hoặc mã lý do;
- người hoặc service khởi tạo theo định danh phù hợp;
- ngoại lệ, legal hold hoặc phần việc còn chờ.

Tránh ghi lại payload gốc, email, địa chỉ hoặc nội dung nhạy cảm trong audit chỉ để chứng minh rằng dữ liệu đã được xóa. Có thể dùng subject reference được bảo vệ, mã định danh giả danh hoặc hash có kiểm soát nếu cần liên kết tiến trình. Tuy nhiên, hash có thể vẫn cho phép liên kết hoặc dò ngược với miền giá trị nhỏ, nên không mặc định nó là anonymous.

Audit log cần có quyền truy cập hạn chế, integrity protection và retention riêng. Khi audit record tự chứa dữ liệu cá nhân, nó cũng phải nằm trong data inventory và chính sách xóa tương ứng.

## 16. Retention và cleanup an toàn trong vận hành

Tác vụ cleanup cần hoạt động như một quy trình có kiểm soát. Một câu lệnh xóa diện rộng theo timestamp có thể xóa nhầm publication chưa hoàn tất, inbox đang xử lý hoặc outbox chưa gửi.

Một cleanup job nên:

1. Chỉ chọn loại bản ghi và trạng thái đủ điều kiện purge.
2. Loại trừ legal hold, claim còn hiệu lực và dữ liệu đang phục hồi.
3. Xóa theo batch giới hạn để tránh transaction dài.
4. Ghi nhận số lượng được chọn, xóa thành công, bỏ qua và lỗi.
5. Có checkpoint để tiếp tục sau khi process dừng.
6. Có dry-run hoặc báo cáo số lượng trước khi áp dụng với thay đổi rủi ro cao.
7. Giới hạn quyền của service account chỉ trên bảng/kho cần cleanup.
8. Cảnh báo khi backlog cleanup tăng hoặc dữ liệu vượt retention.
9. Có quy trình phục hồi khi xóa nhầm, nếu bản chất dữ liệu và chính sách cho phép.

Không dùng thời gian tạo bản ghi đơn lẻ làm điều kiện duy nhất. Ví dụ, outbox createdAt đã cũ nhưng status vẫn PENDING thì chưa đủ điều kiện xóa. Inbox PROCESSING đã quá lâu có thể cần lease recovery trước khi purge. Publication incomplete cần được điều tra trước khi cleanup.

## 17. Kiểm thử retention và deletion

Kiểm thử cần chứng minh dữ liệu được giữ đủ lâu cho retry và được xóa đúng phạm vi khi hết hạn hoặc có yêu cầu hợp lệ. Một test chỉ xác nhận cleanup job chạy không chứng minh mọi bản sao đã được xử lý.

Các kịch bản nên có:

1. **Retention eligibility:** chỉ bản ghi vượt retention và đúng trạng thái mới được chọn purge.
2. **Incomplete publication:** publication chưa hoàn tất không bị cleanup xóa nhầm.
3. **Pending outbox:** command/event chưa gửi vẫn được giữ.
4. **Inbox horizon:** dấu dedup còn tồn tại trong toàn bộ retry/replay horizon.
5. **Broker/DLQ:** message hết TTL hoặc được chuyển DLQ theo cấu hình đã xác định.
6. **Deletion propagation:** tất cả consumer được liệt kê đều nhận và xác nhận yêu cầu xóa.
7. **Late event:** event cũ đến sau deletion marker không tái tạo dữ liệu.
8. **Projection/cache:** dữ liệu được xóa hoặc cập nhật trong read model, cache và search index.
9. **Backup restore:** deletion ledger được áp dụng trước khi dữ liệu restore được mở lại.
10. **Legal hold:** dữ liệu thuộc phạm vi hold không bị purge và được giới hạn truy cập.
11. **Audit minimization:** audit chứng minh tiến trình nhưng không lưu lại payload nhạy cảm không cần thiết.
12. **Partial failure:** consumer mất kết nối có thể retry và yêu cầu xóa tiếp tục được theo dõi.
13. **Idempotent deletion:** nhận cùng deletion operation nhiều lần không gây lỗi hoặc xóa nhầm dữ liệu khác.
14. **Cleanup recovery:** job dừng giữa batch có thể tiếp tục mà không bỏ sót hoặc xử lý sai trạng thái.

Với Spring Modulith, cần kiểm thử publication registry trong các trạng thái completed và incomplete, bao gồm tình huống resubmit sau khi dữ liệu đã bị xóa. Kiểm thử broker cần xác nhận retention, TTL, DLQ và replay theo semantics của transport đang dùng. Kiểm thử backup phải bao gồm restore rehearsal, không chỉ xác nhận file backup tồn tại.

## 18. Quy trình thiết kế retention và xóa dữ liệu event

Khi thêm một event type hoặc consumer mới, hãy thực hiện theo trình tự:

1. Liệt kê payload, metadata và dữ liệu có thể nhận diện cá nhân.
2. Xác định mục đích sử dụng và module sở hữu từng field.
3. Giảm thiểu dữ liệu công bố và xác định schema/version.
4. Lập bản đồ mọi nơi event được lưu: registry, outbox, inbox, broker, DLQ, log, trace, projection, cache, archive và backup.
5. Đặt retention window riêng cho từng kho dựa trên retry, replay, audit và nghĩa vụ áp dụng.
6. Xác định deletion operation, consumer nhận lệnh và cơ chế acknowledgement.
7. Thiết kế tombstone/version để ngăn event cũ tái tạo dữ liệu đã xóa.
8. Xác định anonymization, pseudonymization, encryption và key lifecycle nếu cần.
9. Thiết kế legal hold và audit tối thiểu.
10. Xây cleanup job có batch, checkpoint, metrics và quyền hạn giới hạn.
11. Kiểm thử retry, partial failure, late event, replay, backup restore và deletion propagation.
12. Theo dõi dữ liệu vượt retention, yêu cầu xóa còn pending và consumer chưa xác nhận.

Retention và xóa dữ liệu là một phần của vòng đời application event, từ lúc thiết kế payload đến khi mọi bản sao hết mục đích lưu trữ. Khi từng kho có owner và thời hạn rõ ràng, deletion được lan truyền có xác nhận, tombstone ngăn event cũ tái tạo dữ liệu, còn backup và audit được xử lý riêng, hệ thống có thể duy trì khả năng phục hồi mà vẫn kiểm soát lượng dữ liệu được lưu và thời gian lưu dữ liệu đó.

