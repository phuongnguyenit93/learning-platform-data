# Kế hoạch bỏ version cũ

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua hợp đồng nghiệp vụ ổn định. Khi hợp đồng thay đổi, producer và consumer có thể được triển khai ở những thời điểm khác nhau; message cũ còn nằm trong broker, retry queue, dead-letter queue hoặc kho lưu trữ để replay. Vì vậy, phát hành version mới chưa có nghĩa version cũ có thể bị xóa ngay.

**Kế hoạch bỏ version cũ** xác định cách chuyển producer và consumer sang hợp đồng mới, đo mức sử dụng version cũ, xử lý message tồn đọng và chỉ loại bỏ code/schema cũ khi mọi đường giao nhận và phục hồi đã an toàn. Mục tiêu là ngừng phát version cũ mà không làm mất event, làm hỏng consumer đang chạy hoặc khiến lịch sử không thể replay.

## 1. Phân biệt event schema version và aggregate version

Hai loại version thường xuất hiện trong event-driven system nhưng giải quyết hai vấn đề khác nhau.

| Version | Ý nghĩa | Ví dụ |
|---|---|---|
| Event schema version | Phiên bản cấu trúc và quy ước payload của hợp đồng event | OrderConfirmed v1 → v2 |
| Aggregate version | Phiên bản trạng thái của một aggregate sau mỗi thay đổi nghiệp vụ | Order 123 ở version 17 |

Schema version thay đổi khi cấu trúc hoặc cách diễn giải payload thay đổi. Aggregate version tăng khi trạng thái của một đơn hàng, tài khoản hoặc aggregate cụ thể thay đổi.

Không dùng aggregate version để xác định schema version. Một event schema v2 có thể mang aggregate version 17; một event schema v1 khác cũng có thể mang aggregate version 17. Consumer cần biết cả hai nếu phải xử lý tương thích schema và thứ tự cập nhật domain.

## 2. Khi nào cần bỏ version cũ?

Một version cũ có thể cần được loại bỏ khi:

- Producer đã chuyển sang schema mới.
- Tất cả consumer đã hỗ trợ schema mới.
- Không còn consumer hợp lệ cần đọc schema cũ.
- Các message cũ trong queue, retry và DLQ đã được xử lý hoặc có kế hoạch lưu trữ/replay.
- Hợp đồng cũ không còn được dùng cho tích hợp mới.
- Việc duy trì hai parser hoặc hai nhánh xử lý tạo chi phí và rủi ro không cần thiết.
- Chính sách bảo mật hoặc dữ liệu yêu cầu loại bỏ field cũ.

Không nên bỏ version chỉ vì producer mới đã được deploy. Consumer có thể vẫn chạy phiên bản cũ, message cũ có thể đến muộn hoặc operator có thể replay dữ liệu lịch sử sau nhiều ngày.

Cần phân biệt ba mốc:

1. **Deprecated:** công bố version cũ sắp ngừng hỗ trợ và cấm tích hợp mới.
2. **Retired for production:** producer không còn phát version cũ và consumer không còn nhận nó trong luồng vận hành thường ngày.
3. **Removed:** xóa parser, class, schema hoặc adapter cũ sau khi hết thời hạn phục hồi và replay được cam kết.

Ba mốc này có thể cách nhau đáng kể.

## 3. Lập inventory trước khi thay đổi

Bước đầu tiên là xác định toàn bộ producer, consumer và nơi lưu message của version cũ. Không thể lên lịch bỏ version nếu chưa biết ai còn sử dụng nó.

Inventory nên ghi:

| Thành phần | Cần xác định |
|---|---|
| Producer | Module/service phát event, phiên bản ứng dụng và thời điểm dự kiến chuyển đổi |
| Consumer | Module/service nhận event, owner và khả năng đọc schema |
| Event contract | Event type, schema version, field bắt buộc/tùy chọn và semantics |
| Transport | Application event nội bộ, RabbitMQ, Kafka hoặc adapter khác |
| Queue/topic | Message đang chờ, retention và chính sách redelivery |
| Retry/DLQ | Message lỗi còn giữ version cũ trong bao lâu |
| Event archive | Lịch sử được lưu và thời gian có thể replay |
| Schema Registry | Subject, compatibility policy và version đang được tham chiếu |
| Publication Registry | Publication nội bộ chưa hoàn tất có thể cần deserialize hoặc resubmit |
| Replay tooling | Job, script hoặc operator có thể phát lại event cũ |

Mỗi thành phần phải có owner chịu trách nhiệm xác nhận readiness. Không dựa vào việc tìm kiếm tên class trong một repository duy nhất nếu event đã được externalize sang hệ thống khác hoặc có consumer do nhóm khác vận hành.

## 4. Xác định phạm vi tương thích

Trước khi bỏ v1, hãy phân loại thay đổi giữa v1 và v2.

| Thay đổi | Khả năng tương thích thường gặp | Hướng xử lý |
|---|---|---|
| Thêm field optional có default rõ | Consumer cũ thường có thể bỏ qua | Kiểm tra serializer và compatibility rule |
| Thêm enum value | Có thể làm consumer cũ lỗi nếu enum parser strict | Cập nhật consumer trước khi producer gửi giá trị mới |
| Thêm field bắt buộc | Consumer cũ có thể không hiểu hoặc không có dữ liệu | Dùng rollout có giai đoạn hoặc schema mới |
| Đổi tên/xóa field | Thường phá backward compatibility | Duy trì alias/adapter hoặc phát version mới |
| Đổi kiểu dữ liệu | Có thể phá parser và semantics | Dùng version mới và chuyển đổi có kiểm soát |
| Đổi ý nghĩa nghiệp vụ | Không chỉ là thay đổi cấu trúc | Cân nhắc event type mới |
| Đổi đơn vị/format | Parser có thể thành công nhưng hiểu sai dữ liệu | Định nghĩa contract mới và chuyển đổi tường minh |

Một thay đổi có thể tương thích ở mức cú pháp nhưng không tương thích về nghiệp vụ. Ví dụ field `amount` vẫn là số thập phân nhưng chuyển từ đơn vị đồng sang đơn vị nghìn đồng. Consumer cũ vẫn deserialize thành công nhưng tạo kết quả sai. Hợp đồng phải mô tả cả semantics, đơn vị, timezone, nullability và quy tắc diễn giải.

## 5. Chọn chiến lược chuyển đổi

Có ba chiến lược phổ biến. Chọn theo khả năng triển khai producer/consumer và yêu cầu vận hành.

**Consumer-first:** triển khai consumer hiểu cả v1 và v2 trước; sau đó chuyển producer sang v2. Đây thường là chiến lược đơn giản khi consumer có thể cập nhật độc lập và producer chưa phát v2.

**Adapter/upcaster:** giữ format cũ ở biên nhận, chuyển đổi v1 sang mô hình nội bộ chuẩn rồi xử lý bằng cùng một logic nghiệp vụ. Cách này giảm việc nhân đôi logic consumer, đặc biệt khi có nhiều version lịch sử.

**Dual publish có kiểm soát:** producer phát cả v1 và v2 trong giai đoạn chuyển tiếp khi có consumer chưa thể nâng cấp đồng thời. Cách này làm tăng số message và nguy cơ cùng một tác vụ bị thực hiện hai lần. Chỉ dùng khi có định danh business operation ổn định, consumer deduplicate được và có kế hoạch dừng một nhánh rõ ràng.

Không dùng dual publish theo mặc định. Nếu có thể nâng cấp consumer trước rồi chuyển producer một lần, quy trình thường dễ quan sát và ít rủi ro hơn.

## 6. Kế hoạch expand-contract

Mẫu expand-contract chia thay đổi thành hai giai đoạn lớn: mở rộng khả năng tương thích trước, sau đó thu hẹp và loại bỏ version cũ.

~~~mermaid
flowchart TD
    A[Inventory v1 producers and consumers] --> B[Define v2 contract]
    B --> C[Deploy consumers that accept v1 and v2]
    C --> D[Verify v2 readiness]
    D --> E[Switch producers to v2]
    E --> F[Observe v1 traffic and drain old messages]
    F --> G{No v1 live traffic and replay window expired?}
    G -- No --> F
    G -- Yes --> H[Remove v1 producer and consumer paths]
    H --> I[Archive or retire old schema]
~~~

Các nguyên tắc:

- Consumer mới phải được deploy trước khi producer bắt đầu gửi format mới.
- Trong giai đoạn chuyển tiếp, consumer có thể đọc cả hai version nhưng chuyển về một mô hình nội bộ thống nhất.
- Producer chỉ đổi sang v2 sau khi consumer readiness được xác nhận.
- Version cũ tiếp tục được giữ cho message tồn đọng và replay trong thời gian đã cam kết.
- Chỉ xóa nhánh v1 khi có số liệu chứng minh không còn traffic và không còn nhu cầu phục hồi.

## 7. Giai đoạn 0 — Đóng băng và công bố kế hoạch

Trước rollout:

1. Ghi rõ event type và version đang bị deprecate.
2. Xác định version thay thế và ngày dự kiến ngừng phát.
3. Chỉ định owner cho producer, từng consumer, broker topic/queue và schema.
4. Thông báo cho nhóm tích hợp và người vận hành.
5. Ngừng cho phép consumer mới tích hợp với v1.
6. Ghi nhận baseline số lượng v1 event, consumer lag, retry và DLQ.
7. Định nghĩa tiêu chí dừng rollout và rollback.

Thông báo deprecation cần nêu ngày bắt đầu ngừng phát, thời hạn consumer phải chuyển đổi, ngày dự kiến ngừng nhận và ngày xóa hỗ trợ. Nếu chưa thể cam kết ngày xóa vì còn phụ thuộc retention hoặc replay, hãy ghi rõ điều kiện thay thế cho ngày cố định.

## 8. Giai đoạn 1 — Phát hành consumer tương thích

Consumer cần hiểu v1 và v2 trước khi producer gửi v2. Có thể thực hiện việc này bằng parser theo schema version, adapter hoặc upcaster.

Ví dụ mô hình nội bộ:

~~~java
record OrderConfirmedV1(
    UUID orderId,
    Instant confirmedAt
) {}

record OrderConfirmedV2(
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt,
    String salesChannel
) {}

record CanonicalOrderConfirmed(
    UUID orderId,
    Long aggregateVersion,
    Instant occurredAt,
    String salesChannel
) {}
~~~

Ví dụ trên minh họa hai kiểu payload và mô hình nội bộ. Trong code thực tế, có thể dùng mapper riêng để chuyển cả hai version thành command hoặc value object thống nhất. Không nhất thiết phải để domain model phụ thuộc vào class DTO của transport.

Trước khi bật v2, kiểm tra:

- Consumer deserialize được v1 và v2.
- Field mới có default hoặc quy tắc xử lý rõ.
- Enum hoặc discriminator chưa biết được xử lý theo policy.
- Event ID và business operation ID được giữ ổn định.
- Logic nghiệp vụ không chạy hai lần khi message được gửi lại.
- Consumer có thể quan sát số message theo version.
- Test có fixture đại diện cho payload lịch sử.

## 9. Giai đoạn 2 — Kiểm tra readiness của consumer

Không chỉ dựa vào trạng thái deploy thành công. Mỗi consumer cần cung cấp bằng chứng rằng phiên bản mới đã sẵn sàng.

Readiness có thể bao gồm:

- Tất cả instance đang chạy phiên bản hỗ trợ v2.
- Consumer group/queue đã hoạt động ổn định.
- Contract test với payload v2 thành công.
- Không còn lỗi deserialize v1/v2.
- Retry và DLQ không tăng bất thường.
- Consumer xử lý được field mới và giá trị enum mới.
- Metrics phân biệt được v1 và v2.
- Rollback image/config vẫn có thể đọc dữ liệu đang được phát.

Nếu có consumer do hệ thống ngoài tổ chức quản lý, cần xác nhận readiness từ owner của họ. Không coi việc gửi email thông báo là bằng chứng consumer đã nâng cấp.

## 10. Giai đoạn 3 — Chuyển producer sang v2

Sau khi consumer readiness đạt yêu cầu, chuyển producer sang v2 theo từng producer hoặc từng nhóm tenant nếu có thể.

Producer nên có một điểm chuyển đổi rõ ràng:
- Chọn schema version theo cấu hình đã được phê duyệt.
- Tạo payload v2 từ domain data.
- Giữ event ID, correlation ID và causation ID theo cùng semantics.
- Không thay đổi business meaning trong lúc chỉ nâng schema.
- Ghi metric số event phát theo version.
- Có khả năng rollback về v1 trong thời gian consumer vẫn hỗ trợ v1.

Nếu nhiều instance producer chạy song song, cần bảo đảm chúng không phát hai version không chủ ý trong cùng giai đoạn. Cấu hình rollout phải được quản lý tập trung hoặc có cơ chế version selection nhất quán.

Không thay đổi schema bằng cách sửa class cũ trong khi message cũ vẫn tồn tại mà không có chiến lược deserialize. Khi persisted publication, queue hoặc archive còn chứa payload v1, code mới cần tiếp tục hiểu payload đó hoặc chuyển đổi nó trước khi bỏ parser cũ.

## 11. Có nên dual publish v1 và v2?

Dual publish có thể giúp consumer nâng cấp theo tiến độ riêng, nhưng cần đánh giá kỹ tác dụng phụ.

Nếu một producer phát hai message đại diện cho cùng một nghiệp vụ:
- Hai message có thể đến khác thứ tự.
- Một consumer có thể nhận cả hai và xử lý hai lần.
- Retry một version có thể xảy ra sau khi version kia đã hoàn tất.
- Metrics event count tăng gấp đôi nếu không phân biệt logical event với physical message.
- Việc rollback hoặc replay phức tạp hơn.

Nếu buộc phải dual publish:

1. Dùng business operation ID hoặc logical event ID chung để nhận diện cùng một sự thật nghiệp vụ.
2. Xác định consumer nào đọc version nào.
3. Consumer deduplicate xuyên version, không chỉ theo message ID khác nhau.
4. Không cho hai nhánh cùng thực hiện side effect không idempotent.
5. Theo dõi riêng số logical event và số message vật lý.
6. Đặt ngày dừng dual publish và owner xác nhận.

Một lựa chọn khác là giữ một canonical domain event nội bộ rồi dùng adapter ở biên để chuyển thành schema v1 hoặc v2 cho từng destination. Cách này có thể tránh làm domain code phụ thuộc vào format vận chuyển, nhưng vẫn phải bảo vệ idempotency ở consumer.

## 12. Giai đoạn 4 — Theo dõi traffic version cũ

Sau khi producer chuyển sang v2, chưa xóa v1 ngay. Theo dõi số message v1 theo producer, consumer và destination.

Các metric hữu ích:

| Metric | Câu hỏi cần trả lời |
|---|---|
| Published count by schema version | Producer còn phát v1 không? |
| Consumed count by schema version | Consumer còn nhận v1 không? |
| Incomplete publication by event type/version | Listener nội bộ còn publication v1 chưa hoàn tất không? |
| Oldest v1 message age | Message v1 cũ nhất đã chờ bao lâu? |
| Retry/DLQ count by version | Có message v1 lỗi cần xử lý không? |
| Replay count by version | Có job hoặc operator còn replay v1 không? |
| Consumer error rate by version | Parser hoặc upcaster có lỗi không? |

Không dùng schema version làm metric tag nếu tập version hoặc event type có cardinality không kiểm soát. Với một số lượng version hữu hạn, tag có thể phù hợp; event ID và business ID nên nằm trong log/trace thay vì metric label.

Đặt cảnh báo nếu producer tiếp tục phát v1 sau thời điểm ngừng phát, hoặc nếu v1 message vẫn đến sau khi dự kiến đã drain.

## 13. Xác định thời gian drain và replay window

Một message có thể còn tồn tại sau khi producer ngừng phát vì queue backlog, retry delay, DLQ retention hoặc archive policy. Do đó, cần tính thời gian drain dựa trên toàn bộ đường đi.

Thời gian giữ v1 cần tính đến:

- Queue/topic retention.
- Consumer lag tối đa.
- Retry policy và exponential backoff.
- Dead-letter retention.
- Lịch xử lý thủ công.
- Event archive và replay window.
- Backup restore có thể đưa message cũ trở lại.
- Publication nội bộ chưa hoàn tất có thể được resubmit.
- Thời gian deploy và rollback các instance.

Ví dụ, nếu message có thể nằm trong DLQ 14 ngày và operator được phép replay trong 30 ngày, xóa parser v1 sau 7 ngày không an toàn. Hỗ trợ v1 phải tồn tại ít nhất đến khi hết replay window hoặc có một bước chuyển đổi/archive được kiểm soát.

Với event lưu trữ dài hạn, có thể ngừng v1 trong luồng live nhưng vẫn giữ upcaster để đọc lịch sử. Retire khỏi production và xóa hoàn toàn khả năng đọc lịch sử là hai quyết định riêng.

## 14. Xử lý retry queue, DLQ và message tồn đọng

Trước khi bỏ consumer v1, kiểm tra mọi nơi có thể giữ message cũ:

- Queue chính hoặc partition/topic chưa được consumer đọc.
- Retry queue với TTL hoặc backoff.
- Dead-letter exchange/queue.
- Message parking lot hoặc quarantine.
- Broker backup và snapshot.
- Event archive hoặc object storage.
- Công cụ replay của operator.

Với mỗi nơi, chọn một phương án:
- Drain bằng consumer còn hỗ trợ v1.
- Chuyển đổi message sang v2 bằng migration job có audit.
- Lưu archive và giữ upcaster cho replay.
- Loại bỏ message chỉ khi owner nghiệp vụ xác nhận nó hết giá trị và chính sách retention cho phép.

Không xóa DLQ chỉ để đạt tiêu chí “không còn v1 message”. DLQ có thể chứa nghiệp vụ chưa hoàn tất. Phải phân loại từng nhóm message và lưu kết quả quyết định.

## 15. Event Publication Registry và publication nội bộ

Trong Spring Modulith, Event Publication Registry theo dõi publication của application event đến từng listener trong ứng dụng. Khi bỏ version cũ, cần xem xét các publication nội bộ chưa hoàn tất và khả năng listener được resubmit.

Nếu ứng dụng lưu publication bền vững:
- Xác định publication v1 còn chưa hoàn tất.
- Kiểm tra implementation lưu event và cách deserialize khi ứng dụng nâng cấp.
- Giữ class/adapter tương thích đến khi publication cũ được xử lý hoặc chuyển đổi.
- Xác minh listener v2 có thể xử lý event đã được upcast.
- Không xóa dữ liệu publication đang cần phục hồi.
- Dùng API được Spring Modulith hỗ trợ thay vì phụ thuộc schema nội bộ.

Event Publication Registry không phải event store vô thời hạn. Nó theo dõi giao publication đến listener; lịch sử event và replay dài hạn cần cơ chế lưu trữ riêng nếu nghiệp vụ yêu cầu.

## 16. Upcasting và replay lịch sử

Nếu event v1 phải được replay sau khi producer đã chuyển sang v2, cần một bước chuyển đổi có thể tái lập. **Upcaster** chuyển payload cũ thành representation mới trước khi consumer áp dụng logic.

Ví dụ ý tưởng:

~~~java
OrderConfirmedV2 upcast(OrderConfirmedV1 oldEvent) {
    return new OrderConfirmedV2(
        oldEvent.orderId(),
        1L, // default/version policy phải được xác định từ domain
        oldEvent.confirmedAt(),
        "UNKNOWN"
    );
}
~~~

Các giá trị mặc định trong ví dụ chỉ mang tính minh họa. Không tự suy ra aggregate version hoặc sales channel nếu dữ liệu lịch sử không có căn cứ. Cần định nghĩa cách xử lý field không tồn tại dựa trên semantics domain.

Upcaster nên:
- Có version đầu vào và đầu ra rõ ràng.
- Deterministic: cùng payload cũ luôn tạo cùng kết quả.
- Không gọi dịch vụ ngoài hoặc tạo side effect.
- Có test fixture cho từng version lịch sử.
- Hỗ trợ chuỗi chuyển đổi nếu cần, ví dụ v1 → v2 → v3.
- Không sửa nội dung archive gốc.
- Ghi nhận lỗi khi payload không thể chuyển đổi.

Replay nên chạy trong chế độ an toàn. Nếu event cũ có thể gây gửi email, thu tiền hoặc tạo reservation mới, cần tách projection rebuild khỏi side effect hoặc áp dụng idempotency key để tránh lặp tác dụng.

## 17. Kế hoạch rollback trong thời gian chuyển đổi

Rollback cần được thiết kế trước khi bật producer v2. Trong giai đoạn consumer đã hỗ trợ cả v1 và v2, producer có thể quay lại phát v1 nếu v2 gặp lỗi và contract v1 vẫn được giữ.

Cần chuẩn bị:

- Consumer release hỗ trợ cả hai version.
- Producer có cấu hình chọn version có thể đảo ngược.
- Schema v1 vẫn được đăng ký và broker ACL/routing còn hoạt động.
- Không xóa parser, adapter hoặc fixture v1 trước khi hết rollback window.
- Theo dõi message v2 đã phát để biết có cần replay hoặc chuyển đổi.
- Có quy trình xử lý message v2 tồn đọng khi rollback producer.

Nếu v2 đã mang semantics nghiệp vụ mới, quay về v1 có thể làm mất thông tin hoặc thay đổi ý nghĩa. Khi đó không thể rollback đơn giản bằng cách đổi schema version; cần migration/compensation hoặc phát một event mới biểu đạt trạng thái phù hợp.

## 18. Tiêu chí cho phép ngừng phát v1

Định nghĩa một checklist gate trước khi tắt v1:

- Tất cả producer đã chuyển sang v2.
- Không có instance cũ còn phát v1.
- Tất cả consumer production hỗ trợ v2.
- Không còn v1 message trong queue chính hoặc partition đang hoạt động.
- Retry và DLQ v1 đã được xử lý, archive hoặc có quyết định owner.
- Publication v1 nội bộ chưa hoàn tất đã được xử lý.
- Không có replay job đang phát v1.
- Contract/serialization tests của v2 thành công.
- Metrics v1 bằng 0 trong một khoảng thời gian dài hơn retry và redelivery window.
- Owner của producer và consumer xác nhận readiness.
- Rollback plan và runbook đã được cập nhật.

Chỉ dựa vào published count bằng 0 là chưa đủ. Producer có thể ngừng phát nhưng queue vẫn còn message cũ, consumer cũ vẫn đang chạy hoặc archive vẫn có thể replay v1.

## 19. Giai đoạn 5 — Ngừng nhận và xóa hỗ trợ v1

Khi gate đã đạt:

1. Tắt cấu hình phát v1 ở tất cả producer.
2. Theo dõi để xác nhận không còn v1 publication mới.
3. Drain queue/retry và giải quyết DLQ.
4. Đóng replay job hoặc chuyển sang upcaster/archive path.
5. Chờ hết rollback window và replay window đã cam kết.
6. Loại bỏ parser/handler v1 khỏi consumer live.
7. Xóa adapter, feature flag và cấu hình không còn dùng.
8. Cập nhật schema compatibility policy và tài liệu tích hợp.
9. Giữ dữ liệu lịch sử hoặc upcaster theo retention policy.
10. Ghi audit quyết định decommission và người phê duyệt.

Nếu dùng Schema Registry, thay đổi compatibility mode hoặc xóa subject/version cần theo quy trình riêng của registry. Không xóa schema chỉ vì code consumer đã được deploy; message cũ và hệ thống replay có thể vẫn tham chiếu schema đó.

## 20. Ví dụ timeline triển khai

Timeline dưới đây minh họa một lần chuyển từ v1 sang v2. Khoảng thời gian cần điều chỉnh theo tốc độ deploy, retention và replay policy thực tế.

| Giai đoạn | Producer | Consumer | Điều kiện hoàn tất |
|---|---|---|---|
| Tuần 0: Inventory | Tiếp tục v1 | Tiếp tục v1 | Xác định owner, traffic và retention |
| Tuần 1: Expand | Tiếp tục v1 | Deploy hỗ trợ v1 + v2 | Tất cả consumer xác nhận readiness |
| Tuần 2: Switch | Bắt đầu phát v2 | Đọc v1 + v2 | Không có lỗi contract, backlog ổn định |
| Tuần 3: Drain | Chỉ phát v2 | Tiếp tục đọc cả hai | Queue/retry/DLQ v1 được xử lý |
| Sau replay window | Chỉ phát v2 | Có thể bỏ parser v1 | Traffic v1 bằng 0 và owner xác nhận |
| Decommission | Xóa publisher v1 | Xóa live handler v1 | Archive/upcaster còn đáp ứng nhu cầu lịch sử |

Không cố định lịch theo tuần nếu hệ thống có message retention dài hoặc consumer do bên thứ ba quản lý. Dùng điều kiện readiness và số liệu vận hành làm gate chính.

## 21. Rủi ro thường gặp khi bỏ version cũ

**Xóa class cũ quá sớm.** Publication hoặc message v1 đã lưu không còn deserialize được sau deploy.

**Chỉ kiểm tra producer.** Consumer hoặc replay tool vẫn có thể phát sinh v1.

**Dual publish không có dedup xuyên version.** Cùng một nghiệp vụ được thực hiện hai lần.

**Không drain DLQ.** Message lỗi v1 bị bỏ quên và không thể xử lý sau khi parser bị xóa.

**Xóa schema trong registry quá sớm.** Consumer hoặc archive không thể đọc message lịch sử.

**Đổi semantics trong một lần nâng schema.** Consumer parse được nhưng diễn giải sai dữ liệu.

**Không đo traffic theo version.** Không có bằng chứng để quyết định thời điểm decommission.

**Không tính backup restore.** Khôi phục broker/database có thể đưa message v1 trở lại sau khi code đã bị xóa.

**Không giữ rollback window.** Khi v2 lỗi, producer không còn khả năng quay lại v1 an toàn.

**Dùng migration job có side effect.** Replay hoặc upcast tạo lại hành động nghiệp vụ không mong muốn.

## 22. Checklist kế hoạch bỏ version cũ

- [ ] Đã phân biệt schema version và aggregate version.
- [ ] Có inventory đầy đủ producer, consumer, broker, registry và replay tool.
- [ ] Có owner cho từng consumer và destination.
- [ ] Đã phân loại thay đổi tương thích và thay đổi semantics.
- [ ] Đã định nghĩa v2 contract và fixture kiểm thử.
- [ ] Consumer hỗ trợ v1/v2 trước khi producer phát v2.
- [ ] Có kế hoạch upcast hoặc adapter cho message lịch sử.
- [ ] Dual publish (nếu có) được bảo vệ bằng idempotency xuyên version.
- [ ] Producer rollout có thể quan sát và rollback trong thời hạn cho phép.
- [ ] Metrics phân biệt published/consumed/retried/DLQ theo version.
- [ ] Đã drain queue, retry, DLQ và publication nội bộ chưa hoàn tất.
- [ ] Replay window, backup restore và retention đã được tính.
- [ ] Có tiêu chí traffic v1 bằng 0 đủ lâu trước khi xóa parser.
- [ ] Schema Registry và archive được xử lý theo chính sách riêng.
- [ ] Consumer v1 code chỉ bị xóa sau khi owner xác nhận gate.
- [ ] Runbook, tài liệu và audit được cập nhật.

## 23. Nguyên tắc decommission version cũ

Bỏ một event version là một thay đổi vòng đời hợp đồng, không chỉ là xóa một class hoặc đổi serializer. Hãy kiểm kê mọi producer, consumer, queue, retry, DLQ, publication chưa hoàn tất, schema registry và công cụ replay; triển khai consumer tương thích trước, chuyển producer sau, rồi theo dõi traffic và drain message cũ.

Chỉ loại bỏ parser, adapter và schema v1 khi không còn traffic live, không còn message cần xử lý, replay window đã kết thúc hoặc có upcaster được duy trì cho lịch sử, và các owner đã xác nhận. Trong Spring Modulith, cần giữ khả năng đọc các publication nội bộ chưa hoàn tất theo implementation đang dùng. Một kế hoạch expand-contract có metrics, idempotency, rollback và gate rõ ràng giúp chuyển version có kiểm soát mà không làm mất sự kiện hoặc lặp tác dụng nghiệp vụ.
