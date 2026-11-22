# Hot partition và phân phối không đều

Kafka chia topic thành các partition để lưu trữ và xử lý song song. Tuy nhiên, có partition nhận lượng record hoặc byte lớn hơn hẳn các partition còn lại. Hiện tượng này thường được gọi là **hot partition**. Nó có thể khiến một consumer xử lý một partition bị quá tải, consumer lag tăng, trong khi các consumer khác vẫn còn năng lực nhàn rỗi.

Hot partition thường xuất phát từ cách chọn key và phân phối record của producer. Một key có tần suất xuất hiện rất cao sẽ liên tục được định tuyến tới cùng partition theo partitioner mặc định. Nhưng phân phối không đều cũng có thể do producer chỉ định partition trực tiếp, custom partitioner, lưu lượng nghiệp vụ lệch, chi phí xử lý record khác nhau hoặc leader partition tập trung trên một broker.

Bài học thuộc chương **Partition và ordering** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách nhận diện nguyên nhân, thiết kế key, phân phối tải và xử lý hot partition mà vẫn hiểu rõ trade-off về thứ tự sự kiện.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích hot partition và phân biệt nó với broker hoặc consumer bị quá tải.
- Nhận diện key skew, partition skew và leader/broker skew.
- Hiểu vì sao một key thường được định tuyến ổn định tới cùng partition.
- Đo lượng record, byte, lag và thời gian xử lý theo partition.
- Thiết kế partition key phù hợp với ranh giới ordering của nghiệp vụ.
- Chọn cách xử lý hot key bằng sharding, salting hoặc tách topic.
- Đánh giá tác động của việc tăng partition tới key mapping và thứ tự.
- Biết khi nào partition reassignment giúp ích và khi nào không.
- Kiểm thử phân phối với dữ liệu có độ lệch giống tải production.

## 1. Hot partition là gì?

Hot partition là partition có lưu lượng hoặc chi phí xử lý cao hơn đáng kể so với các partition khác trong cùng topic. Ví dụ topic orders.created có 12 partition nhưng partition 3 nhận 45% tổng số record, còn các partition khác chỉ nhận khoảng 5% mỗi partition.

~~~mermaid
flowchart TB
    P[Producer records] --> D[Partitioner]
    D --> P0["Partition 0: 5%"]
    D --> P1["Partition 1: 5%"]
    D --> P2["Partition 2: 5%"]
    D --> HOT["Partition 3: 45% - HOT"]
    D --> P4["Partition 4: 5%"]
    D --> P5["Partition 5: 5%"]
    HOT --> C[One consumer member]
    C --> L[Consumer lag increases]
~~~

Partition nóng có thể gây ra:

- Consumer được gán partition đó xử lý chậm hơn các member khác.
- Lag của riêng partition tăng liên tục.
- Một broker có leader của partition nóng sử dụng CPU, disk hoặc network cao.
- Producer có thể gặp latency cao hơn khi gửi vào partition nóng.
- Các partition khác còn dư năng lực nhưng không thể chia sẻ công việc của partition nóng trong cùng consumer group.

Hot partition không nhất thiết đồng nghĩa toàn bộ topic có throughput cao. Một partition có thể bị nóng do số record ít nhưng payload lớn hoặc logic xử lý mỗi record rất nặng. Vì vậy cần xem cả số record, byte và thời gian xử lý.

## 2. Phân biệt các dạng mất cân bằng

Trước khi sửa, cần xác định mất cân bằng xảy ra ở lớp nào.

| Dạng mất cân bằng | Biểu hiện | Nguyên nhân thường gặp |
|---|---|---|
| Key skew | Một vài key chiếm phần lớn record | Một tenant, customer hoặc entity có lưu lượng vượt trội. |
| Partition traffic skew | Một partition nhận nhiều record hoặc byte hơn | Key skew, chỉ định partition trực tiếp hoặc custom partitioner. |
| Broker/leader skew | Một broker chịu tải cao hơn các broker khác | Nhiều leader partition nặng tập trung trên broker đó, replica placement hoặc tải broker khác nhau. |
| Consumer processing skew | Một consumer lag cao hơn các member khác | Partition được gán có dữ liệu nặng, xử lý chậm hoặc downstream không đồng đều. |
| Payload skew | Số record tương đương nhưng byte hoặc chi phí xử lý chênh lệch | Một số loại event có payload lớn hoặc cần nhiều thao tác nghiệp vụ. |

Một topic có thể gặp nhiều dạng cùng lúc. Ví dụ một tenant lớn tạo key skew, khiến partition 3 nóng; leader của partition 3 nằm trên broker 1; consumer đọc partition 3 còn gọi một dịch vụ downstream chậm. Chỉ tăng số broker hoặc số consumer sẽ không tự giải quyết toàn bộ chuỗi nguyên nhân.

## 3. Vì sao key có thể tạo ra hot partition?

Với record có key, Kafka producer mặc định thường dùng key đã serialize để xác định partition. Cùng một key thường được định tuyến tới cùng partition khi số partition và partitioner không thay đổi.

Ví dụ:

~~~java
kafkaTemplate.send(
        "orders.created",
        customerId,
        event
);
~~~

Nếu một khách hàng lớn tạo 40% tổng số đơn hàng, mọi event mang customerId đó sẽ đi về cùng partition theo partitioner mặc định. Các partition còn lại có thể nhận tải thấp hơn nhiều.

Key có độ đa dạng cao không tự bảo đảm phân phối đều. Nếu 90% record thuộc một key phổ biến và 10% record thuộc hàng nghìn key khác, partition chứa key phổ biến vẫn có thể trở thành hot partition.

Các kiểu key dễ gây skew:

- Một hằng số dùng cho mọi record, ví dụ key bằng chuỗi orders.
- Một tenant ID duy nhất cho khách hàng có lưu lượng vượt trội.
- Một account ID nhận gần như toàn bộ giao dịch.
- Một category hoặc region có traffic cao hơn các nhóm còn lại.
- Key null kết hợp với producer chỉ định partition hoặc partitioner tùy chỉnh không cân bằng.

Với key null, partitioner mặc định của Kafka producer hiện đại thường sử dụng cơ chế sticky để gom record vào một partition trong một khoảng thời gian nhằm tận dụng batching, rồi chuyển partition. Vì vậy không nên mặc định rằng mọi record key null sẽ được round-robin đều tuyệt đối theo từng record.

## 4. Chọn key theo ranh giới ordering

Partition key cần phản ánh đơn vị dữ liệu mà nghiệp vụ yêu cầu giữ thứ tự. Hãy trả lời câu hỏi: những sự kiện nào bắt buộc phải được xử lý theo thứ tự tương đối?

Ví dụ:

| Nhu cầu nghiệp vụ | Key có thể phù hợp | Ordering được giữ trong phạm vi |
|---|---|---|
| Các thay đổi của cùng đơn hàng | orderId | Một đơn hàng |
| Các giao dịch của cùng tài khoản | accountId | Một tài khoản |
| Các sự kiện của cùng thiết bị | deviceId | Một thiết bị |
| Các thay đổi của cùng khách hàng | customerId | Một khách hàng |
| Sự kiện không cần ordering theo entity | Key phân phối tải hoặc null | Không có bảo đảm ordering theo entity |

Nếu dùng customerId làm key nhưng một khách hàng tạo phần lớn traffic, partition chứa khách hàng đó sẽ nóng. Nếu nghiệp vụ chỉ yêu cầu thứ tự theo orderId, có thể dùng orderId để phân phối các đơn hàng của khách hàng đó qua nhiều partition hơn.

Đổi key cần hiểu trade-off:

- Key quá thô, ví dụ tenantId, có thể gom nhiều entity vào một partition và gây skew.
- Key quá chi tiết, ví dụ eventId, có thể phân phối tốt nhưng làm mất ordering giữa các sự kiện cùng entity.
- Key phù hợp nên vừa phân phối tải hợp lý vừa giữ ordering ở đúng phạm vi nghiệp vụ yêu cầu.

Không có một key duy nhất tối ưu cho mọi loại consumer. Nếu hai use case cần hai kiểu partitioning rất khác nhau, có thể cần hai topic với mô hình key riêng hoặc một luồng xử lý trung gian.

## 5. Đo lường để xác định partition nóng

Không nên kết luận có hot partition chỉ từ tổng consumer lag. Hãy so sánh từng partition trong cùng khoảng thời gian.

Các dữ liệu nên thu thập:

- Record vào mỗi partition theo giây hoặc phút.
- Byte vào mỗi partition.
- Record được consumer đọc và xử lý theo partition.
- Consumer lag theo partition và tốc độ tăng lag.
- Thời gian xử lý p50, p95, p99 theo partition hoặc loại event.
- Leader của từng partition và broker đang giữ leader.
- CPU, disk I/O, network throughput và request latency của broker.
- Producer send latency, retry, timeout và batch size.

Có thể tạo bảng quan sát:

| Partition | Records/s | Bytes/s | Consumer lag | Processing p95 |
|---|---:|---:|---:|---:|
| 0 | 850 | 1.8 MB | 120 | 18 ms |
| 1 | 910 | 1.9 MB | 150 | 20 ms |
| 2 | 4,800 | 10.5 MB | 18,000 | 95 ms |
| 3 | 870 | 1.7 MB | 130 | 19 ms |

Số liệu trên chỉ là ví dụ minh họa. Partition 2 có cả lưu lượng và lag cao hơn nhiều, cần kiểm tra key phân phối vào partition đó, payload và logic xử lý.

Một số công cụ và nguồn dữ liệu:

- Kafka consumer group description để xem lag theo partition.
- Kafka broker metrics hoặc JMX exporter để xem BytesIn, MessagesIn, request latency và tải broker.
- Producer metrics để theo dõi record gửi, batch và request latency.
- Spring Kafka listener/container metrics và application metrics để đo thời gian xử lý.
- Log có topic, partition, offset, event type và key đã được che hoặc rút gọn phù hợp.

Không dùng key có cardinality rất lớn làm label metric. Hãy dùng log hoặc trace cho event-level context và metric có tập nhãn giới hạn.

## 6. Kiểm tra producer partitioner và cách chỉ định partition

Producer có thể chọn partition theo key, dùng partitioner tùy chỉnh hoặc được ứng dụng chỉ định partition trực tiếp.

Ví dụ chỉ định partition thủ công:

~~~java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders.created",
                2,
                event.orderId(),
                event
        );

kafkaTemplate.send(record);
~~~

Trong ví dụ này, record được gửi thẳng tới partition 2. Nếu nhiều producer cùng chỉ định partition 2, partition đó có thể nóng dù key đa dạng.

Trước khi thay đổi consumer hoặc broker, hãy kiểm tra:

- Producer có truyền key hay không.
- Có producer nào truyền partition number trực tiếp không.
- Có custom partitioner nào đang được cấu hình không.
- Serializer của key có nhất quán giữa các producer không.
- Các phiên bản producer có dùng cùng quy tắc partitioning không.
- Có thay đổi số partition gần thời điểm traffic bị lệch không.

Nếu nhiều producer dùng serializer hoặc partitioner khác nhau, cùng một chuỗi key có thể không được định tuyến như mong đợi. Hợp đồng partition key cần được thống nhất giữa các producer phát vào cùng topic.

## 7. Tăng số partition có giải quyết hot key không?

Tăng số partition có thể tăng khả năng song song tổng thể của topic và giúp phân phối nhiều key khác nhau trên nhiều partition hơn. Tuy nhiên, nó **không tự chia một key nóng thành nhiều partition** khi vẫn dùng cùng key và partitioner mặc định.

Ví dụ key tenant-42 tiếp tục được hash tới một partition sau khi topic tăng từ 12 lên 24 partition. Key đó vẫn tập trung vào một partition. Một số key khác có thể được phân phối lại do số partition thay đổi.

Cần lưu ý:

- Kafka không tự chuyển record cũ sang các partition mới khi tăng partition.
- Kết quả ánh xạ key sang partition có thể thay đổi khi partition count thay đổi.
- Record cũ của một key có thể nằm ở partition cũ, còn record mới có thể nằm ở partition mới.
- Ordering giữa các record của cùng key có thể không còn được giữ xuyên suốt thay đổi đó.
- Thêm partition làm tăng tài nguyên metadata, file log, replica và công việc quản lý broker.

Vì vậy, tăng partition là giải pháp khi cần tăng năng lực song song cho nhiều key hoặc mở rộng consumer group. Nếu nguyên nhân là một key quá nóng, cần thay đổi mô hình key hoặc cô lập workload.

## 8. Sharding hoặc salting cho hot key

Khi một entity có quá nhiều record, có thể chia workload của entity đó thành nhiều shard. Thay vì dùng một key duy nhất, producer tạo một số shard key ổn định để phân phối record qua nhiều partition.

Ví dụ hệ thống có một khách hàng lớn nhưng yêu cầu ordering chỉ ở phạm vi đơn hàng. Có thể dùng orderId để chọn shard trong customer:

~~~java
int shardCount = 8;
int shard = Math.floorMod(orderId.hashCode(), shardCount);
String partitionKey = customerId + "#" + shard;

kafkaTemplate.send(
        "orders.created",
        partitionKey,
        event
);
~~~

Các event của cùng orderId có cùng shard key và thường đi tới cùng partition theo partitioner mặc định. Các orderId khác nhau của cùng customer có thể được phân tán qua tối đa tám nhóm shard.

Đây là một kỹ thuật sharding theo nghiệp vụ. Số shard cần được cấu hình ổn định và kiểm thử với traffic thực tế. Nếu thay shardCount, key mapping có thể đổi và ordering của entity qua giai đoạn thay đổi cần được xử lý riêng.

Trade-off:

- Tăng song song bằng cách chia workload của một entity lớn.
- Giữ được ordering trong phạm vi shard key.
- Mất ordering tổng thể giữa các shard của cùng customer.
- Consumer hoặc downstream có thể cần tổng hợp lại dữ liệu từ nhiều shard.
- Cần theo dõi shard nóng vì phân phối theo hash không bảo đảm tải hoàn toàn đều.

Không dùng salting ngẫu nhiên nếu các event của cùng order cần thứ tự. Nếu mỗi event nhận một salt ngẫu nhiên, các event của cùng order có thể rơi vào nhiều partition và được xử lý độc lập.

## 9. Chọn chiến lược theo yêu cầu ordering

Có những workload không thể chia một key nóng mà vẫn giữ thứ tự toàn cục cho key đó. Nếu mọi thay đổi của một tài khoản phải được xử lý tuần tự, accountId là key phù hợp và một partition phải xử lý chuỗi sự kiện đó theo thứ tự.

Trong trường hợp này, có một giới hạn kiến trúc: muốn giữ thứ tự tuần tự cho một key thì không thể đồng thời phân phối các record của key đó sang nhiều partition độc lập mà vẫn dựa vào ordering Kafka mặc định.

Các hướng lựa chọn:

| Yêu cầu | Chiến lược | Đánh đổi |
|---|---|---|
| Ordering toàn bộ sự kiện của một entity | Giữ entityId làm key, tối ưu xử lý partition | Throughput của entity bị giới hạn bởi một partition. |
| Chỉ cần ordering theo từng đơn hàng, không cần toàn khách hàng | Dùng orderId hoặc customerId + shard theo order | Mất ordering toàn khách hàng. |
| Không cần ordering theo key | Dùng key phân phối tải hoặc key null phù hợp | Consumer cần xử lý độc lập và chịu được thứ tự khác nhau. |
| Một tenant cực lớn có thể cô lập | Tách tenant lớn sang topic hoặc luồng riêng | Tăng độ phức tạp provisioning và vận hành. |
| Cần tổng hợp thứ tự sau fan-out | Shard xử lý song song rồi hợp nhất theo sequence/version | Cần thêm tầng điều phối và quản lý sequence. |

Nếu cần thứ tự tổng thể cho một entity nhưng tốc độ một partition không đủ, có thể phải xem lại mô hình nghiệp vụ: giảm số event, gộp event, xử lý theo snapshot, hoặc chia aggregate thành các entity độc lập. Không có cấu hình consumer nào làm một partition được nhiều consumer member trong cùng group xử lý song song mà vẫn tự giữ thứ tự mặc định.

## 10. Tách workload bằng topic hoặc tenant shard

Một tenant lớn có thể chiếm phần lớn traffic của topic dùng chung. Nếu tenant đó có yêu cầu throughput hoặc SLA riêng, tách thành topic riêng có thể giúp cô lập tải và chính sách vận hành.

Ví dụ:

- orders.created: các tenant thông thường.
- orders.created.large-tenant: workload của tenant có traffic cao.
- orders.audit: luồng audit có retention và consumer riêng.

Tách topic giúp:

- Chọn partition count riêng cho workload lớn.
- Cấu hình retention và replication theo nhu cầu.
- Đặt consumer group và scaling độc lập.
- Theo dõi lag, throughput và lỗi riêng.
- Hạn chế một tenant làm ảnh hưởng các tenant khác.

Đổi lại, producer cần định tuyến topic theo quy tắc rõ ràng, consumer có thể cần subscribe nhiều topic và hệ thống quản lý schema, ACL, retention cùng DLT phức tạp hơn. Hãy chỉ tách khi có ranh giới vận hành hoặc SLA rõ ràng.

## 11. Phân phối lại partition giữa broker

Có trường hợp record phân bố tương đối đều giữa các partition nhưng một broker vẫn nóng vì đang giữ leader của nhiều partition có traffic cao. Đây là broker/leader skew, khác với key skew.

Kafka cho phép reassignment replica và thay đổi leader placement để cân bằng tải giữa broker. Việc này có thể giảm áp lực lên một broker, nhưng không làm giảm lượng record của partition nóng và không chia một partition cho nhiều broker leader cùng lúc.

Trước khi reassignment:

1. Kiểm tra leader và replica placement.
2. Đo disk, network, CPU và request latency từng broker.
3. Xác minh replication factor, ISR và dung lượng đĩa.
4. Lập kế hoạch reassignment có giới hạn băng thông.
5. Theo dõi under-replicated partitions và ISR trong quá trình di chuyển.
6. Xác minh leader distribution và tải sau khi hoàn tất.

Nếu một partition vẫn nhận 45% traffic, reassignment chỉ chuyển nơi chịu tải của partition đó. Muốn giảm skew của dữ liệu cần giải quyết key/partitioning hoặc cô lập workload.

## 12. Tối ưu consumer và broker sau khi xử lý phân phối

Sau khi key distribution hợp lý, vẫn cần bảo đảm consumer và broker đủ năng lực.

Các hướng tối ưu có thể gồm:

- Tăng consumer concurrency khi còn partition chưa được khai thác.
- Tối ưu xử lý database và dịch vụ downstream.
- Dùng batch xử lý khi nghiệp vụ hỗ trợ bulk operation.
- Giới hạn công việc bất đồng bộ để tránh đầy bộ nhớ và commit offset sai thứ tự.
- Điều chỉnh producer batching, compression và linger để cải thiện hiệu quả network.
- Cân bằng leader và replica trên broker.
- Tăng tài nguyên broker khi bottleneck thực sự nằm ở CPU, disk hoặc network.

Consumer concurrency không vượt qua giới hạn partition assignment của group. Nếu một partition nóng, thêm consumer member vào cùng group không làm partition đó được chia cho nhiều member. Cần giảm lượng công việc trên partition hoặc thay đổi cách phân phối workload.

Compression và batching giúp giảm overhead truyền tải, nhưng không sửa được một key nóng bị dồn vào một partition. Hãy coi chúng là tối ưu hiệu quả sau khi đã hiểu nguyên nhân phân phối.

## 13. Kiểm thử phân phối với dữ liệu lệch

Một bài test chỉ tạo số lượng record bằng nhau cho mỗi key thường không phát hiện được hot partition. Cần tạo workload có độ lệch giống thực tế.

Ví dụ một test phân phối nên có:

- Một tenant tạo phần lớn traffic.
- Nhiều tenant nhỏ có lưu lượng thấp.
- Một số key có payload lớn.
- Các event cùng entity cần giữ ordering.
- Producer dùng đúng serializer và partitioner của production.

Có thể kiểm tra phân phối bằng cách đếm record theo partition:

~~~java
Map<Integer, Long> counts = new HashMap<>();

for (int i = 0; i < events.size(); i++) {
    SendResult<String, OrderCreatedEvent> result =
            kafkaTemplate.send(
                    "orders.created",
                    events.get(i).partitionKey(),
                    events.get(i)
            ).get(10, TimeUnit.SECONDS);

    int partition = result.getRecordMetadata().partition();
    counts.merge(partition, 1L, Long::sum);
}
~~~

Đây là ví dụ minh họa cho test; không nên gọi get tuần tự như vậy trong benchmark throughput vì nó làm thay đổi đặc tính tải. Khi đo tải thực, gửi bất đồng bộ với giới hạn in-flight và thu thập metadata trong callback.

Một số kiểm thử cần có:

| Kiểm thử | Điều cần xác minh |
|---|---|
| Uniform keys | Phân phối baseline trên các partition. |
| Skewed keys | Nhận diện partition nóng khi một key hoặc tenant chiếm nhiều traffic. |
| Sharded key | Workload nóng được phân tán theo số shard đã thiết kế. |
| Ordering per entity | Các event cùng entity vẫn đi theo partition và thứ tự mong đợi. |
| Partition expansion | Phát hiện key mapping thay đổi khi tăng partition. |
| Broker reassignment | Tải broker thay đổi nhưng partition traffic không tự thay đổi. |
| Consumer load | Lag và thời gian xử lý theo partition phản ánh đúng bottleneck. |

Đừng đặt ngưỡng phân phối cứng kiểu mỗi partition phải có đúng 1/N record. Workload thực tế không nhất thiết đồng đều. Hãy xác định mức lệch chấp nhận được theo SLA và năng lực xử lý.

## 14. Quy trình xử lý hot partition trong production

Khi phát hiện lag tăng hoặc một broker nóng, có thể xử lý theo trình tự:

1. Xác định topic và partition có lag, bytes hoặc record rate bất thường.
2. Kiểm tra consumer nào đang sở hữu partition và thời gian xử lý của listener.
3. Lấy mẫu key hoặc loại event của partition nóng; bảo vệ dữ liệu nhạy cảm khi log.
4. Đối chiếu key frequency để tìm tenant hoặc entity chiếm traffic.
5. Kiểm tra producer có chỉ định partition hoặc dùng custom partitioner không.
6. Xác định bottleneck nằm ở key skew, payload, consumer hay broker leader placement.
7. Chọn giải pháp phù hợp: tối ưu xử lý, sharding key, tách topic hoặc reassignment broker.
8. Đánh giá ảnh hưởng tới ordering và replay trước khi đổi partitioning.
9. Thử nghiệm với workload lệch trên staging.
10. Triển khai có theo dõi và so sánh metrics trước/sau.
11. Chuẩn bị phương án quay lui nếu lag hoặc lỗi tăng.
12. Cập nhật tài liệu key contract và ownership của topic.

Không thay đổi key hoặc partition count đột ngột chỉ để làm biểu đồ trông cân bằng. Nếu thứ tự sự kiện là yêu cầu nghiệp vụ, một thay đổi partitioning có thể tạo lỗi khó phát hiện hơn cả lag.

## 15. Bài tập tổng hợp: xử lý hot tenant trong orders.created

Giả sử topic orders.created có 12 partition. Một tenant chiếm 45% traffic và partition chứa key của tenant đó liên tục tăng lag.

Yêu cầu:

1. Đo records/s và bytes/s theo partition.
2. Lấy thống kê key frequency để xác định tenant gây skew.
3. Kiểm tra producer có dùng tenantId làm key hoặc chỉ định partition cố định không.
4. Xác định nghiệp vụ cần ordering theo tenant, customer hay order.
5. Thử key orderId để phân phối các đơn hàng của tenant qua nhiều partition.
6. Nếu cần ordering theo order, thiết kế shard key ổn định theo orderId.
7. So sánh workload trước/sau sharding bằng dữ liệu có cùng phân phối.
8. Kiểm tra event cùng order vẫn giữ ordering trong shard.
9. Thử tăng partition và ghi nhận các key được remap.
10. Thử tách tenant lớn sang topic riêng và đánh giá chi phí vận hành.
11. Kiểm tra consumer lag, throughput, broker load và downstream latency.
12. Viết quyết định kiến trúc nêu rõ lợi ích, trade-off ordering và kế hoạch migration.

Bài tập hoàn thành khi bạn xác định được nguyên nhân của hot partition, chọn được chiến lược phù hợp với ordering và chứng minh bằng số liệu rằng tải đã được phân phối tốt hơn mà không làm sai hợp đồng sự kiện.

## 16. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Nhận diện | Hot partition và skew | Phân biệt key, partition, broker và consumer skew. |
| 2. Key design | Key và ordering boundary | Chọn key theo đơn vị cần giữ thứ tự. |
| 3. Producer | Partitioner và explicit partition | Phát hiện cấu hình producer làm dồn traffic. |
| 4. Metrics | Records, bytes, lag, latency | Đo được mức lệch theo partition. |
| 5. Scale | Partition count và consumer concurrency | Hiểu giới hạn của việc thêm partition/consumer. |
| 6. Sharding | Salting, shard key, topic isolation | Phân phối hot workload và nêu rõ ordering trade-off. |
| 7. Broker | Leader placement và reassignment | Phân biệt broker skew với key skew. |
| 8. Testing | Skewed workload và ordering test | Kiểm thử bằng dữ liệu lệch giống production. |
| 9. Operations | Incident response và migration | Xử lý hot partition có đo lường và rollback plan. |

Bài học hoàn thành khi bạn có thể nhận diện partition nóng bằng metrics, tìm nguyên nhân từ key và producer, chọn chiến lược sharding hoặc cô lập workload phù hợp, đồng thời giải thích ảnh hưởng tới thứ tự sự kiện.

Hot partition không chỉ là vấn đề thiếu consumer. Nó thường bắt nguồn từ sự lệch trong workload và cách producer ánh xạ key vào partition. Muốn xử lý đúng, cần kết hợp thiết kế key, giới hạn ordering, số liệu theo partition, năng lực broker/consumer và một kế hoạch thay đổi có kiểm soát.

