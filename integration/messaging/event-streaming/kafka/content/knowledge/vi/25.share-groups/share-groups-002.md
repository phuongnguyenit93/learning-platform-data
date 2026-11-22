# Phân biệt share group với consumer group theo partition

Consumer group truyền thống phân phối **partition** cho các consumer member: trong cùng một group, tại một thời điểm, một partition chỉ do tối đa một consumer sở hữu. Share group phân phối quyền xử lý ở cấp **record**: nhiều share consumer có thể cùng đọc một partition, nhưng mỗi record đang được giao sẽ được broker theo dõi trạng thái acquire/acknowledge để tránh giao đồng thời cùng một record cho nhiều consumer.

Khác biệt này làm hai mô hình phù hợp với hai loại workload khác nhau. Consumer group thích hợp khi cần xử lý theo partition, giữ thứ tự record trong partition và xây dựng stateful stream processing. Share group phù hợp với mô hình nhiều worker cùng xử lý các record độc lập, cần chia việc ở cấp record và có cơ chế xác nhận, nhả record để retry.

## 1. Consumer group truyền thống phân phối theo partition

Trong consumer group thông thường, các consumer dùng cùng group.id phối hợp đọc topic. Group coordinator và partition assignor phân công partition cho các member.

Các quy tắc chính:

- Một partition được gán cho tối đa một consumer member trong cùng group tại một thời điểm.
- Một consumer có thể nhận nhiều partition nếu số consumer ít hơn số partition.
- Nếu số consumer lớn hơn số partition đang được subscribe, một số consumer sẽ không có partition để đọc.
- Khi member tham gia/rời group hoặc metadata subscription thay đổi, group có thể rebalance và phân phối lại partition.
- Consumer lưu tiến độ bằng committed offset theo từng topic-partition.

Ví dụ topic orders có 4 partition:

~~~text
Consumer group: order-processors

orders-0  ─────> Consumer A
orders-1  ─────> Consumer B
orders-2  ─────> Consumer C
orders-3  ─────> Consumer D
~~~

Với 4 consumer, mỗi consumer có thể nhận một partition. Nếu tăng lên 6 consumer, tối đa 4 consumer có partition trong group; hai consumer còn lại idle. Nếu chỉ có 2 consumer, mỗi consumer có thể nhận hai partition.

Đơn vị phân phối là partition chứ không phải từng record. Consumer A xử lý record của orders-0 theo thứ tự offset mà partition cung cấp. Điều này tạo nền tảng cho ordering trong partition, dù ứng dụng vẫn có thể tự làm đảo thứ tự hoàn tất nếu gửi xử lý bất đồng bộ rồi commit offset không đúng cách.

### Tiến độ offset của consumer group

Consumer group commit offset kế tiếp cần đọc cho mỗi partition. Ví dụ committed offset là 105 nghĩa là group đã xác nhận tiến độ đến trước offset 105 và lần đọc tiếp theo có thể bắt đầu từ 105.

Offset commit là tiến độ ở cấp partition. Nếu ứng dụng xử lý nhiều record song song trong cùng partition, không được commit vượt qua record chưa xử lý xong; nếu không, khi restart consumer có thể bỏ qua record đó. Với xử lý tuần tự, consumer thường hoàn tất record rồi commit offset phù hợp.

## 2. Share group phân phối theo record

Share group là mô hình consumer phối hợp khác với consumer group truyền thống. Các share consumer thuộc cùng một share group có thể cùng đọc record từ một partition. Broker quản lý trạng thái giao record và khóa (lock) record đã giao cho consumer, sau đó nhận xác nhận xử lý.

Các đặc điểm chính:

- Nhiều consumer trong cùng share group có thể cùng nhận record từ một partition.
- Một record đã được acquire sẽ được giữ quyền xử lý cho consumer nhận record đó trong thời gian lock; consumer khác không đồng thời nhận cùng record đang được khóa.
- Consumer xác nhận record đã xử lý, nhả record để có thể retry, hoặc từ chối record theo semantics của API.
- Nếu consumer biến mất hoặc không xác nhận trước khi lock hết hạn, record có thể được giao lại.
- Broker theo dõi trạng thái từng record trong share group thay vì chỉ dựa vào một committed offset tuần tự cho mỗi partition như consumer group cổ điển.

Ví dụ vẫn với topic orders có 4 partition, nhưng có 6 share consumer:

~~~text
Share group: order-workers

orders-0 ──┬──> Share consumer A nhận record offset 10
           ├──> Share consumer B nhận record offset 11
           └──> Share consumer C nhận record offset 12

orders-1 ─────> Share consumer D nhận record offset 7
orders-2 ─────> Share consumer E nhận record offset 21
orders-3 ─────> Share consumer F nhận record offset 4
~~~

Sơ đồ chỉ minh họa việc nhiều consumer có thể xử lý các record khác nhau của cùng partition. Việc broker chọn record và consumer cụ thể còn phụ thuộc số record sẵn có, lock, giới hạn acquisition, trạng thái group và phiên bản triển khai.

Điểm quan trọng: share group không gán độc quyền orders-0 cho A. B và C vẫn có thể xử lý các record khác của partition đó. Tuy vậy, cùng một record đang được khóa không được đồng thời giao cho nhiều consumer trong group.

## 3. So sánh trực tiếp theo đơn vị phân phối

| Tiêu chí | Consumer group | Share group |
|---|---|---|
| Đơn vị phân phối | Partition | Record |
| Quyền sở hữu partition | Một consumer member trong group tại một thời điểm | Không độc quyền một consumer; nhiều member có thể đọc cùng partition |
| Quyền sở hữu record | Đi theo consumer đang sở hữu partition | Broker acquire/lock record cho một consumer |
| Tiến độ | Committed offset theo topic-partition | Trạng thái acknowledgement theo record trong share group |
| Xác nhận xử lý | Commit offset | Acknowledge record |
| Retry một record | Ứng dụng thường quản lý bằng pause/seek/retry topic hoặc cơ chế riêng | Có thể release record hoặc để lock hết hạn để giao lại |
| Ordering | Thứ tự đọc trong partition; ứng dụng phải tránh xử lý song song làm đảo thứ tự hoàn tất | Nhiều consumer xử lý các record cùng partition; không nên dựa vào thứ tự hoàn tất nghiệp vụ |
| Song song vượt số partition | Không thể có nhiều consumer active cùng đọc một partition trong cùng group | Nhiều share consumer có thể cùng xử lý một partition ở cấp record |
| Phù hợp | Stream processing, xử lý theo key, stateful aggregation/join | Work queue, background workers và xử lý record độc lập |

Consumer group và share group là hai loại group/protocol có semantics khác nhau. Không thể chỉ đổi một giá trị group.id trong ứng dụng consumer truyền thống rồi kỳ vọng offset commit và partition assignment hoạt động như share group; cần client API, broker và cấu hình có hỗ trợ share consumption.

## 4. Vòng đời record trong share group: acquire và acknowledge

Broker cần biết record nào đang được giao, record nào đã hoàn tất và record nào cần giao lại. Có thể hình dung vòng đời ở mức khái niệm:

~~~mermaid
stateDiagram-v2
    [*] --> Available
    Available --> Acquired: Consumer nhận record
    Acquired --> Acknowledged: ACCEPT
    Acquired --> Available: RELEASE
    Acquired --> Available: Lock hết hạn / consumer mất kết nối
    Acquired --> Rejected: REJECT
    Acknowledged --> [*]
    Rejected --> [*]
~~~

Tên trạng thái nội bộ và chi tiết chuyển trạng thái phụ thuộc phiên bản Kafka. Sơ đồ tập trung vào semantics quan sát được ở API:

- **Acquire:** broker giao record cho một share consumer và giữ lock để consumer xử lý.
- **Accept:** consumer xác nhận đã xử lý thành công; broker ghi nhận record hoàn tất trong share group.
- **Release:** consumer nhả record, thường vì lỗi tạm thời; record có thể được giao lại cho consumer khác.
- **Reject:** consumer từ chối record; đây là quyết định lỗi không tiếp tục retry theo luồng thông thường. Cần xác minh semantics cụ thể của API/version và tự định tuyến DLQ nếu muốn lưu bản lỗi.
- **Lock timeout:** nếu consumer không acknowledge đúng hạn, record có thể trở lại trạng thái có thể được giao lại.

Share API có các kiểu acknowledgement như ACCEPT, RELEASE và REJECT. Hãy kiểm tra tài liệu đúng phiên bản client/broker để xác nhận hành vi chi tiết, giới hạn lock, delivery count và cách xử lý record bị từ chối.

## 5. Ví dụ xử lý thành công, retry và lỗi không thể phục hồi

Giả sử worker xử lý event gửi hóa đơn:

1. Nhận record và acquire lock.
2. Kiểm tra event ID, gọi nghiệp vụ idempotent và lưu kết quả.
3. Nếu thành công, acknowledge ACCEPT.
4. Nếu database tạm thời unavailable, acknowledge RELEASE để record có thể được giao lại.
5. Nếu payload sai vĩnh viễn, ghi thông tin lỗi vào DLQ theo quy trình có kiểm soát rồi acknowledge REJECT.

Mã giả:

~~~java
for (ShareRecord record : shareConsumer.poll(timeout)) {
    try {
        processIdempotently(record);
        shareConsumer.acknowledge(record, ACCEPT);
    } catch (TransientProcessingException e) {
        shareConsumer.acknowledge(record, RELEASE);
    } catch (PermanentDataException e) {
        publishToDeadLetterTopicIdempotently(record, e);
        shareConsumer.acknowledge(record, REJECT);
    }
}
~~~

Đây là mã giả mô tả luồng xử lý, không phải đoạn Java có thể biên dịch trực tiếp. Tên class, cách poll và chữ ký acknowledge cần khớp Share Consumer API của Kafka version được sử dụng.

Không acknowledge ACCEPT trước khi side effect quan trọng đã bền vững. Nếu acknowledge trước rồi process thất bại, broker có thể coi record đã hoàn tất và không giao lại. Ngược lại, nếu side effect đã thành công nhưng consumer chết trước acknowledgement, record có thể được giao lại. Vì vậy, consumer vẫn cần idempotency key hoặc unique constraint ở hệ thống đích.

### Delivery count và poison record

Share group có thể theo dõi số lần record được giao. Delivery count giúp nhận biết record liên tục thất bại và hỗ trợ chính sách xử lý poison record. Ngưỡng, cách tăng bộ đếm và hành vi khi vượt giới hạn phụ thuộc cấu hình/phiên bản broker.

Không giả định share group tự động tạo DLQ. Ứng dụng cần thiết kế:

- Lỗi transient: release để retry, có giới hạn và backoff phù hợp.
- Lỗi permanent: ghi DLQ hoặc quarantine trước khi reject.
- Quá số lần thử: cảnh báo, đưa vào luồng xử lý lỗi và tránh vòng lặp vô hạn.
- Record được giao lại: bảo đảm side effect idempotent theo event ID.

## 6. Ordering: khác biệt quan trọng nhất khi chọn mô hình

Consumer group giữ quyền sở hữu partition cho một member, do đó consumer có thể đọc record theo thứ tự offset của partition. Nếu key của event được map ổn định vào cùng partition, ứng dụng có thể dựa trên ordering đó để xử lý state theo key.

Share group cho phép nhiều consumer xử lý các record khác nhau của cùng partition. Ví dụ record offset 100 được giao cho A và offset 101 được giao cho B. B có thể xử lý xong và acknowledge trước A. Nếu cả hai record liên quan cùng một order hoặc account, side effect có thể xảy ra sai thứ tự nghiệp vụ.

Do đó:

- Không dùng share group nếu cần bảo đảm một key luôn được xử lý tuần tự mà không có cơ chế đồng bộ bổ sung.
- Nếu dùng share group cho record có quan hệ, hãy thiết kế khóa nghiệp vụ, optimistic concurrency/version check hoặc per-entity serialization ở tầng xử lý.
- Nếu chỉ cần các record độc lập hoàn thành nhanh, share group có thể tận dụng nhiều worker tốt hơn.

Consumer group cũng không tự bảo đảm side effect hoàn tất đúng thứ tự nếu ứng dụng gửi xử lý bất đồng bộ nhiều record trong một partition. Ordering ở Kafka là thứ tự log; ứng dụng phải giữ thứ tự xử lý/commit nếu nghiệp vụ yêu cầu.

## 7. Mở rộng số consumer và giới hạn throughput

Với consumer group truyền thống, số consumer active có thể đọc một topic trong group bị giới hạn bởi số partition được phân công. Thêm consumer vượt quá số partition không tạo thêm parallelism cho topic đó.

Với share group, nhiều consumer có thể chia record trong cùng partition, nên số consumer không bị ràng buộc theo kiểu một consumer cho mỗi partition. Điều này hữu ích khi record xử lý lâu và độc lập. Tuy nhiên, không có nghĩa thêm consumer vô hạn sẽ tăng throughput vô hạn.

Các giới hạn vẫn gồm:

- Throughput đọc từ broker và số partition của topic.
- Số record broker cho phép acquire/in-flight trong share group.
- Thời gian lock, acknowledgement latency và tần suất redelivery.
- CPU, connection pool, database/API downstream.
- Kích thước record, batch/fetch behavior và network.
- Share group coordinator/state management và giới hạn broker theo version.

Ví dụ 4 partition và 12 worker:

| Mô hình | Kết quả |
|---|---|
| Consumer group | Tối đa 4 consumer active cho topic này trong group; các consumer còn lại không có partition |
| Share group | Nhiều worker có thể cùng xử lý record từ 4 partition; throughput còn tùy record availability, broker và hệ thống đích |

Hãy benchmark bằng dữ liệu có phân bố key và thời gian xử lý giống production. Đo throughput, p95/p99 latency, redelivery, lock expiry, số record đang in-flight và tải downstream trước khi tăng worker.

## 8. Rebalance và lỗi consumer

### Consumer group

Khi consumer tham gia hoặc rời group, coordinator có thể kích hoạt rebalance. Partition bị revoke khỏi consumer cũ và assign cho consumer mới. Consumer cần dừng xử lý an toàn, commit offset phù hợp và giải phóng tài nguyên gắn với partition. Trong thời gian rebalance, throughput có thể giảm hoặc tạm ngừng.

### Share group

Share group cũng quản lý membership và trạng thái consumer, nhưng việc phân phối record không dựa trên việc giao độc quyền toàn bộ partition cho một member. Record đã acquire có trạng thái/lock riêng. Nếu consumer chết hoặc không acknowledge, record có thể được giao lại khi lock hết hạn hoặc theo cơ chế phục hồi của broker.

Ứng dụng cần xử lý tình huống:

- Worker chết sau khi nhận record nhưng trước khi side effect hoàn tất.
- Worker hoàn tất side effect nhưng chết trước khi acknowledge.
- Lock hết hạn trong khi xử lý còn đang chạy.
- Record được giao lại trong khi lần xử lý trước có thể vẫn đang thực hiện side effect.
- Nhiều record liên quan cùng entity được xử lý song song.

Đặt timeout xử lý phù hợp với thời gian lock và thiết kế side effect idempotent. Nếu công việc có thể kéo dài hơn lock timeout, cần chiến lược gia hạn/kiểm soát thời gian xử lý theo API hỗ trợ; không mặc định lock sẽ kéo dài vô hạn.

## 9. Offset commit và record acknowledgement không giống nhau

| Câu hỏi | Consumer group | Share group |
|---|---|---|
| Đánh dấu tiến độ thế nào? | Commit next offset cho từng partition | Acknowledge trạng thái từng record |
| Có thể xác nhận một record trong khi record trước chưa xong? | Có thể đọc/xử lý song song ở tầng ứng dụng, nhưng commit offset phải tránh bỏ qua gap | Có; record được acknowledge độc lập |
| Retry record lỗi | Thường cần seek/pause, retry topic hoặc logic ứng dụng | Có thể release record để broker giao lại |
| Sau restart | Bắt đầu từ committed offset hoặc offset reset policy | Broker dựa vào trạng thái record của share group và các record chưa được acknowledge |

Ví dụ consumer group đọc partition offsets 10, 11, 12. Nếu xử lý 10 và 12 xong nhưng 11 chưa xong, commit offset 13 có thể khiến 11 bị bỏ qua sau restart. Ứng dụng phải theo dõi contiguous completion trước khi commit.

Trong share group, record 10 và 12 có thể được acknowledge độc lập với record 11. Đây là điểm phù hợp cho work distribution ở cấp record, nhưng ứng dụng phải chấp nhận khả năng hoàn tất không theo thứ tự offset.

Không dùng công cụ xem committed offsets của consumer group để kết luận toàn bộ tiến độ xử lý share group. Share group có trạng thái delivery/acknowledgement riêng; công cụ giám sát cần hỗ trợ share group của Kafka version đang chạy.

## 10. Khi nào nên chọn consumer group?

Chọn consumer group khi:

- Cần ordering theo partition hoặc theo key đã được partition ổn định.
- Xử lý stateful như aggregation, join, window, KTable hoặc Kafka Streams.
- Muốn mỗi partition có một consumer owner trong group.
- Ứng dụng dựa vào committed offset để resume/replay.
- Muốn dùng hệ sinh thái consumer group truyền thống, framework và công cụ monitoring phổ biến.

Ví dụ:

- Order event được xử lý theo orderId, cần state transition đúng thứ tự.
- Payment ledger cần append theo account partition.
- Kafka Streams application xây dựng aggregate hoặc join stateful.
- Consumer ghi projection cần đảm bảo record cùng key được xử lý tuần tự.

## 11. Khi nào nên chọn share group?

Chọn share group khi:

- Record tương đối độc lập, không cần ordering nghiêm ngặt giữa các record cùng partition.
- Nhiều worker cần chia việc ở cấp record thay vì đợi partition assignment.
- Thời gian xử lý mỗi record khác nhau và cần phân phối tải linh hoạt.
- Muốn broker quản lý record acquisition, acknowledgement và redelivery.
- Có thể làm side effect idempotent và xử lý record được giao lại.

Ví dụ:

- Worker tạo thumbnail cho các ảnh độc lập.
- Xử lý batch kiểm tra hồ sơ độc lập.
- Gửi notification cho các event không yêu cầu thứ tự theo entity.
- Background task xử lý từng record, có retry theo record và không giữ state tuần tự theo partition.

Share group không phải lựa chọn mặc định thay thế consumer group. Nếu dữ liệu cần ordering theo key, join/stateful processing hoặc consumer framework chưa hỗ trợ share API, consumer group vẫn là lựa chọn phù hợp hơn.

## 12. Bảng quyết định lựa chọn

| Yêu cầu | Consumer group | Share group |
|---|---|---|
| Một consumer sở hữu partition tại một thời điểm | Có | Không |
| Nhiều consumer cùng xử lý một partition | Không trong cùng group | Có, ở cấp record |
| Ordering theo partition tự nhiên | Phù hợp hơn | Không nên giả định |
| Acknowledge độc lập từng record | Không phải mô hình offset chính | Có |
| Release một record để retry | Cần logic retry của ứng dụng | Có semantics release |
| Số worker active vượt số partition | Không giúp tăng parallelism partition | Có thể |
| Stateful stream processing | Phù hợp | Thường không phù hợp |
| Work queue với record độc lập | Có thể dùng nhưng cần chia partition | Phù hợp khi broker/client hỗ trợ |
| Công cụ/framework consumer hiện hữu | Hỗ trợ rộng | Cần kiểm tra hỗ trợ share API |

## 13. Điều kiện phiên bản và khả năng tương thích

Share group là tính năng mới hơn consumer group truyền thống. Trước khi triển khai, cần xác nhận:

1. Kafka broker version hỗ trợ share group và tính năng đã được bật theo yêu cầu release.
2. Kafka client version cung cấp Share Consumer API tương thích.
3. Broker, client và thư viện tích hợp (Spring/framework) có cùng khả năng hỗ trợ.
4. Công cụ quản trị, monitoring, ACL và quota hiểu được share group.
5. Môi trường production có cấu hình phù hợp cho share group coordinator/state và giới hạn record in-flight.

Trạng thái hỗ trợ, cấu hình broker, API và mức độ ổn định có thể khác giữa các phiên bản Kafka. Không sao chép property hoặc code sample từ một release khác mà chưa kiểm tra tài liệu của đúng broker/client version. Đặc biệt, không giả định Kafka client consumer thông thường hoặc Spring Kafka listener container tự động chuyển sang share semantics.

## 14. Migration từ consumer group sang share group

Không nên coi migration chỉ là thay group ID. Cần đánh giá lại semantics:

1. Xác định ordering hiện tại có phải yêu cầu nghiệp vụ không.
2. Kiểm tra side effect có idempotent khi record được giao lại không.
3. Chuyển từ offset commit sang acknowledge/release/reject ở cấp record.
4. Thiết kế timeout/lock, retry, delivery count và DLQ.
5. Xác nhận broker/client/framework hỗ trợ share group.
6. Thử nghiệm song song trên môi trường staging với cùng phân bố dữ liệu.
7. Đối soát record đã xử lý và record còn pending trước khi chuyển luồng production.

Consumer group và share group có thể cùng đọc một topic như hai nhóm độc lập, nhưng chúng duy trì tiến độ riêng. Nếu chạy song song để kiểm thử, mỗi nhóm có thể tạo side effect riêng; dùng destination test hoặc chặn side effect để tránh xử lý nghiệp vụ hai lần.

## 15. Monitoring và troubleshooting

Với consumer group, theo dõi:

- Partition assignment theo member.
- Committed offset và consumer lag theo partition.
- Rebalance count/time, poll interval và commit latency.
- Processing latency và lỗi record.

Với share group, bổ sung:

- Số record được acquire và đang in-flight.
- Acknowledge rate theo ACCEPT/RELEASE/REJECT.
- Redelivery count và delivery count distribution.
- Lock timeout/expired acquisition.
- Thời gian từ acquire đến acknowledgement.
- Số record bị reject hoặc đưa vào DLQ.
- Throughput theo share consumer và độ lệch tải giữa worker.

Tên metric và công cụ hiển thị thay đổi theo Kafka release. Xác nhận metric thực tế trên phiên bản triển khai thay vì giả định mọi consumer group tool đều hiển thị share group state.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer group có member idle | Số member lớn hơn số partition | Giảm member hoặc tăng partition nếu phù hợp |
| Share group redelivery tăng | Worker crash, xử lý vượt lock timeout hoặc không acknowledge | Kiểm tra thời gian xử lý, lock và lỗi downstream |
| Side effect bị lặp | Worker xử lý thành công nhưng chết trước acknowledgement | Dùng event ID/unique constraint và idempotent processing |
| Share worker phân tải không đều | Thời gian xử lý khác nhau, giới hạn acquisition hoặc broker load | Theo dõi in-flight và latency theo consumer |
| Record liên quan hoàn tất sai thứ tự | Nhiều consumer xử lý cùng partition | Chuyển consumer group hoặc thêm serialization theo entity |
| Record bị reject nhiều | Payload lỗi vĩnh viễn hoặc validation sai | Kiểm tra DLQ, contract và quy tắc reject |

## 16. Những hiểu nhầm thường gặp

- **“Share group là consumer group có nhiều consumer trên một partition.”** Share group dùng record acquisition/acknowledgement; consumer group dùng partition assignment và offset commit.
- **“Một record có thể được hai share consumer xử lý cùng lúc.”** Record đã acquire được khóa cho consumer nhận nó; duplicate có thể xuất hiện ở lần giao lại sau release/timeout, không phải quyền xử lý đồng thời cùng một acquisition.
- **“Share group giữ ordering giống consumer group.”** Nhiều consumer có thể xử lý các offset khác nhau của cùng partition và hoàn tất không theo thứ tự.
- **“Share group không cần idempotency.”** Record có thể được giao lại nếu worker lỗi hoặc lock hết hạn.
- **“Thêm consumer group member vượt số partition luôn tăng throughput.”** Với consumer group truyền thống, member dư không có partition; share group mới hỗ trợ chia record trong cùng partition.
- **“Share group tự động tạo DLQ.”** DLQ và quy trình xử lý poison record vẫn cần được thiết kế.
- **“Có thể đổi group ID là chuyển xong.”** Cần đổi client API, acknowledgement, retry và kiểm tra version support.
- **“Share group phù hợp với mọi workload.”** Workload cần ordering, stateful processing hoặc framework chưa hỗ trợ share API nên tiếp tục dùng consumer group.

## 17. Checklist production

- [ ] Đã xác định workload cần partition ownership hay record-level work sharing.
- [ ] Đã đánh giá ordering theo partition/key và stateful processing.
- [ ] Broker và client version hỗ trợ share group; feature/config đã được kiểm tra.
- [ ] Share consumer API được framework/runtime hỗ trợ hoặc đã có adapter được kiểm thử.
- [ ] Xử lý record có idempotency key và chịu được redelivery.
- [ ] ACCEPT chỉ thực hiện sau khi side effect quan trọng đã bền vững.
- [ ] RELEASE có retry/backoff và giới hạn phù hợp.
- [ ] REJECT có quy trình quarantine/DLQ và audit.
- [ ] Lock timeout phù hợp với processing latency; có cảnh báo lock expiry.
- [ ] Theo dõi acquire, in-flight, acknowledgement, redelivery và delivery count.
- [ ] Đã kiểm thử worker crash trước/sau side effect và trước/sau acknowledgement.
- [ ] Đã kiểm thử record xử lý chậm, poison record và downstream outage.
- [ ] Không dùng share group cho dữ liệu cần thứ tự theo entity nếu chưa có cơ chế serialization bổ sung.
- [ ] Có kế hoạch migration, replay, rollback và đối soát.

Consumer group phân phối partition cho consumer member và lưu tiến độ bằng committed offset theo partition. Share group cho phép nhiều consumer cùng xử lý một partition ở cấp record, dùng acquire/lock và acknowledgement để theo dõi thành công, retry hoặc từ chối từng record. Chọn mô hình theo yêu cầu ordering và cách xử lý lỗi của nghiệp vụ: partition-oriented stream processing thường hợp với consumer group; record-oriented work distribution có thể hợp với share group khi broker, client và hệ sinh thái đã hỗ trợ.
