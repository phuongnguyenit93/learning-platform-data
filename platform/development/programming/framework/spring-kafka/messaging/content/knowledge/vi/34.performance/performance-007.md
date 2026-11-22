# Tối ưu số partition

Số partition quyết định mức song song mà một consumer group có thể khai thác, cách record được phân phối và chi phí vận hành của topic. Chọn quá ít partition có thể giới hạn throughput dù ứng dụng còn CPU và consumer instance nhàn rỗi. Chọn quá nhiều lại làm tăng metadata, file handle, số replica, công việc rebalance và chi phí lưu trữ trên broker.

Trong Spring Kafka, partition là thuộc tính của topic Kafka. Listener concurrency quyết định số consumer mà một container có thể chạy; nó không tự tạo thêm partition. Muốn tối ưu, cần ước lượng tải thực tế, đo năng lực xử lý trên mỗi partition, xác định mức song song mong muốn rồi kiểm chứng bằng benchmark.

## 1. Partition ảnh hưởng đến throughput như thế nào?

Một topic được chia thành nhiều partition. Mỗi partition là một log có thứ tự riêng, được lưu trên broker và có offset độc lập. Producer ghi record vào một partition; consumer group phân phối các partition cho các consumer thành viên.

Với một consumer group, tại một thời điểm, một partition chỉ được gán cho tối đa một consumer trong group. Một consumer có thể nhận nhiều partition, nhưng hai consumer trong cùng group không đồng thời đọc cùng một partition như hai bản sao độc lập.

~~~mermaid
flowchart TD
    P[Producer] --> T[(Topic: orders)]
    T --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    T --> P3[Partition 3]
    P0 --> C0[Consumer 0]
    P1 --> C1[Consumer 1]
    P2 --> C2[Consumer 2]
    P3 --> C3[Consumer 3]
~~~

Nếu topic có bốn partition và consumer group có bốn consumer, mỗi consumer có thể nhận một partition. Nếu group chỉ có hai consumer, mỗi consumer có thể nhận hai partition. Nếu group có sáu consumer, ít nhất hai consumer sẽ không có partition để xử lý khi topic chỉ có bốn partition.

Vì vậy, partition đặt giới hạn trên cho mức song song theo partition trong một consumer group. Tuy nhiên, throughput không tăng tuyến tính vô hạn theo số partition: database, network, CPU, serialization, broker disk và dependency phía sau vẫn có giới hạn riêng.

## 2. Phân biệt số partition, concurrency và số consumer instance

Ba thông số này liên quan nhưng không giống nhau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Partition count | Số log độc lập của topic | Topic orders có 12 partition |
| Listener concurrency | Số consumer thread/container con mà Spring Kafka tạo cho listener | concurrency = 6 |
| Application instances | Số process/pod chạy ứng dụng | 3 pod |

Giả sử có ba pod, mỗi pod cấu hình concurrency bằng hai. Tổng cộng consumer group có thể có sáu consumer. Nếu topic có 12 partition, mỗi consumer có thể nhận khoảng hai partition tùy assignor và tình trạng group.

Nếu concurrency là tám trên mỗi pod, tổng số consumer có thể lên đến 24. Với topic chỉ có 12 partition, tối đa 12 consumer có assignment trong group; số consumer còn lại không tăng throughput và vẫn có thể tạo chi phí kết nối, thread và quản lý.

Ví dụ cấu hình listener:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        concurrency = "6"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Giá trị concurrency có thể lấy từ cấu hình ứng dụng thay vì hardcode. Khi scale deployment, hãy tính tổng consumer trên toàn bộ pod, không chỉ concurrency của một instance.

## 3. Ước lượng partition từ throughput mục tiêu

Một cách bắt đầu là đo throughput an toàn mà một partition có thể duy trì trong điều kiện gần production. Gọi:

- R: throughput mục tiêu của toàn topic, tính bằng record/giây.
- r_p: throughput an toàn đo được trên một partition.
- P_r: số partition cần cho mục tiêu throughput.

Ước lượng ban đầu:

~~~text
P_r = ceil(R / r_p)
~~~

Ví dụ, hệ thống cần xử lý 18.000 record/giây. Benchmark cho thấy một partition duy trì ổn định khoảng 1.500 record/giây với latency và error rate đạt yêu cầu:

~~~text
P_r = ceil(18.000 / 1.500) = 12
~~~

Kết quả 12 chỉ là điểm xuất phát. Năng lực mỗi partition phụ thuộc kích thước record, số byte/giây, batch size, compression, replication, phần cứng broker, consumer logic và tải downstream.

Nên dùng throughput an toàn ở mức tải có headroom, không lấy con số tối đa trong một lần chạy ngắn. Nếu 1.500 record/giây chỉ đạt được khi CPU gần 100% hoặc p99 latency vượt SLO, đó không phải mức throughput phù hợp để sizing production.

## 4. Ước lượng partition từ mức song song mong muốn

Ngoài throughput, cần xem số consumer muốn chạy đồng thời trong một group.

Gọi C là số consumer thực sự cần có việc trong group. Với một topic, số partition nên đủ để cấp việc cho mức song song đó:

~~~text
P_c >= C
~~~

Nếu hệ thống có ba pod và mỗi pod cần hai consumer xử lý topic, mức song song mong muốn là sáu. Topic có ít nhất sáu partition mới có thể cung cấp sáu assignment cho group đó.

Kết hợp hai điều kiện ban đầu:

~~~text
P >= max(P_r, P_c)
~~~

Trong thực tế còn cần xét headroom tăng trưởng, hot key, giới hạn broker và chi phí replication. Không nên cộng máy móc một tỷ lệ dự phòng nếu chưa biết mục tiêu scale; hãy xác định kịch bản tăng tải cụ thể rồi kiểm thử.

Lưu ý: một consumer có thể xử lý nhiều partition tuần tự hoặc theo cơ chế container. Tăng partition tạo thêm khả năng phân phối công việc, nhưng không tự tăng số thread xử lý trong ứng dụng nếu concurrency vẫn thấp.

## 5. Dùng record rate và byte rate

Record/giây không đủ để mô tả tải Kafka. Một topic chứa event 1 KB và topic chứa event 200 KB có đặc tính network, memory và disk rất khác nhau.

Cần đo ít nhất:

- Record/giây ở mức trung bình và peak.
- Byte/giây trước và sau compression.
- Kích thước record trung bình, p95 và lớn nhất.
- Tỷ lệ key và phân phối record theo key.
- Số consumer group đọc topic.
- Retention theo thời gian và dung lượng.
- Replication factor và số broker.

Ví dụ, 10.000 record/giây với payload 1 KB tương đương khoảng 10 MB/giây payload thô. Nếu payload trung bình là 100 KB, tải thô đã gần 1 GB/giây trước overhead và compression. Cùng số partition có thể phù hợp với trường hợp đầu nhưng không đủ cho trường hợp sau.

Với hệ thống bị giới hạn bởi byte throughput, hãy sizing theo byte/giây và benchmark kích thước payload thực tế. Không tăng partition chỉ để giải quyết vấn đề do record quá lớn hoặc serializer tạo payload không cần thiết.

## 6. Key quyết định phân phối partition

Khi producer gửi record có key, Kafka partitioner thường dùng key để định tuyến các record cùng key về cùng partition. Đây là cách giữ thứ tự theo key trong một topic.

Ví dụ:

~~~java
kafkaTemplate.send(
        "orders",
        order.orderId().toString(),
        order
);
~~~

Nếu key là orderId, các event của cùng đơn hàng thường được gửi về cùng partition. Consumer có thể xử lý tuần tự các event của đơn hàng đó theo thứ tự trong partition.

Chọn key cần cân bằng hai mục tiêu:

- **Ordering:** các event cần thứ tự phải dùng cùng key.
- **Distribution:** key phải đủ đa dạng để tải được phân tán qua nhiều partition.

Nếu dùng một key chung như "orders" cho mọi record, toàn bộ record có thể tập trung vào một partition. Tăng partition count không khắc phục được hot partition do key không đa dạng.

## 7. Nhận diện hot partition và hot key

Một topic có 24 partition không có nghĩa tải sẽ chia đều 1/24 cho mỗi partition. Nếu một key chiếm 40% traffic, partition chứa key đó có thể trở thành điểm nghẽn.

Các dấu hiệu hot partition:

- Lag của một hoặc vài partition cao hơn hẳn phần còn lại.
- Consumer được gán partition nóng có processing time và CPU cao hơn.
- Byte rate hoặc record rate lệch lớn giữa các partition.
- Một số key xuất hiện với tần suất vượt trội.

Có thể kiểm tra phân phối bằng metric broker/client, record metadata trong consumer hoặc công cụ phân tích key. Không nên chỉ nhìn tổng lag của group vì tổng số có thể che mất một partition đang bị nghẽn.

Nếu ordering theo entity là bắt buộc, hot key cần được giải quyết ở thiết kế nghiệp vụ hoặc cách xử lý. Chia một key thành nhiều key con có thể tăng phân phối, nhưng cũng làm mất thứ tự giữa các event của entity đó. Chỉ dùng salted key khi nghiệp vụ cho phép xử lý song song và có cơ chế hợp nhất/versioning rõ ràng.

## 8. Tăng partition có thể ảnh hưởng ordering

Tăng số partition của topic hiện hữu là thao tác thường được Kafka hỗ trợ, nhưng có một hệ quả quan trọng khi producer dùng key mặc định.

Partitioner thường tính partition từ hash của key dựa trên số partition hiện tại. Khi số partition thay đổi, cùng một key có thể được ánh xạ sang partition khác cho các record mới. Record cũ vẫn nằm trong partition cũ; record mới có thể đi vào partition mới.

Ví dụ:

1. Topic có 6 partition, event của order-100 đang vào partition 2.
2. Topic được tăng lên 12 partition.
3. Cùng key order-100 được gửi tiếp và có thể vào partition 8.
4. Hai partition được consumer xử lý độc lập; thứ tự toàn cục giữa event cũ và mới không còn được bảo đảm.

Kafka chỉ bảo đảm thứ tự trong một partition. Vì vậy, mở rộng partition count có thể làm thay đổi giả định ordering theo key nếu dùng partitioner phụ thuộc số partition.

Nếu nghiệp vụ cần thứ tự nghiêm ngặt theo key, hãy chọn partition count đủ cho vòng đời dự kiến ngay từ đầu hoặc thiết kế migration sang topic mới với chiến lược routing/ordering rõ ràng. Có thể dùng partitioner ổn định hoặc mapping được quản lý, nhưng phải đảm bảo producer và consumer cùng tuân theo contract đó.

## 9. Replication factor không phải partition count

Hai cấu hình thường bị nhầm:

- **Partition count:** số partition logic của topic.
- **Replication factor:** số bản sao của mỗi partition trên các broker.

Ví dụ topic có 12 partition và replication factor 3 sẽ có tổng cộng 36 replica assignment trên cluster. Mỗi partition có một leader và các follower replica theo cấu hình.

Replication tăng khả năng chịu lỗi và ảnh hưởng chi phí disk/network; partition count ảnh hưởng mức song song, phân phối log và metadata. Tăng replication factor không tạo thêm consumer parallelism. Tăng partition count cũng không tự tăng khả năng chịu lỗi nếu replication không phù hợp.

Ví dụ khai báo topic bằng Spring Kafka:

~~~java
@Bean
NewTopic ordersTopic() {
    return TopicBuilder.name("orders")
            .partitions(12)
            .replicas(3)
            .build();
}
~~~

Spring Kafka KafkaAdmin có thể dùng các bean NewTopic để tạo topic khi ứng dụng khởi động, tùy cấu hình và quyền của broker. Trong production, việc tạo topic thường nên được quản lý qua quy trình hạ tầng để tránh mỗi application instance tự ý thay đổi topology.

## 10. Tăng số partition của topic đã tồn tại

Kafka cho phép tăng số partition nhưng không hỗ trợ giảm số partition trực tiếp bằng thao tác alter partitions thông thường. Nếu tạo topic quá nhiều partition, cách giảm thường là tạo topic mới với số partition thấp hơn rồi migrate dữ liệu/producer/consumer theo kế hoạch.

Ví dụ tăng partition bằng AdminClient:

~~~java
Map<String, NewPartitions> changes = Map.of(
        "orders",
        NewPartitions.increaseTo(18)
);

adminClient.createPartitions(changes)
        .all()
        .get(30, TimeUnit.SECONDS);
~~~

Đây là thao tác tăng từ số hiện tại lên 18, không phải đặt lại số partition tùy ý. Trước khi chạy cần kiểm tra số hiện tại, giới hạn cluster, partition assignment và tác động ordering.

Không nên gọi tăng partition tự động mỗi lần ứng dụng khởi động mà không có kiểm soát. Topic topology là quyết định hạ tầng có ảnh hưởng lâu dài đến consumer, key mapping và chi phí broker.

## 11. Chi phí của quá nhiều partition

Mỗi partition tạo ra metadata và trạng thái mà broker, controller, producer và consumer phải quản lý. Nhiều partition có thể làm tăng:

- Số leader/follower replica và công việc quản lý ISR.
- File segment, file handle và hoạt động log cleanup.
- Metadata trao đổi giữa broker và client.
- Số batch producer được gom riêng theo partition.
- Chi phí rebalance và thời gian phân phối partition.
- Bộ nhớ và cấu trúc quản lý offset của consumer group.
- Thời gian phục hồi và kiểm tra khi broker khởi động hoặc partition chuyển leader.

Partition nhiều hơn có thể giúp chia tải nhưng cũng làm mỗi partition nhận ít record hơn. Producer gom batch theo partition; khi record bị phân tán qua rất nhiều partition, mỗi batch có thể nhỏ hơn, giảm hiệu quả batching và compression.

Không có một ngưỡng partition phổ quát cho mọi cluster. Sức chứa phụ thuộc phiên bản Kafka, cấu hình broker, số broker, dung lượng disk, workload, replication và số consumer group. Hãy dựa trên giới hạn vận hành đã đo của cluster thay vì áp dụng một con số chung.

## 12. Retention và dung lượng lưu trữ

Dung lượng topic phụ thuộc throughput byte, retention, replication và mức compression. Có thể ước lượng sơ bộ:

~~~text
Dung lượng logic ≈ byte_rate * retention_seconds
Dung lượng vật lý ≈ dung_lượng_logic * replication_factor
~~~

Ví dụ topic ghi 5 MB/giây, giữ dữ liệu 24 giờ:

~~~text
5 MB/s * 86,400 s ≈ 432,000 MB ≈ 432 GB
~~~

Với replication factor 3, tổng dung lượng replica lý thuyết xấp xỉ 1,296 GB, chưa tính overhead segment, index, filesystem và headroom vận hành. Compression có thể giảm dung lượng thực tế, nhưng tỷ lệ phụ thuộc dữ liệu và cấu hình producer.

Partition count phân chia dung lượng logic thành nhiều log; nó không tự làm tổng dữ liệu biến mất. Tăng partition có thể làm số segment và index tăng, do đó cần tính retention và disk theo cả topic và cluster.

## 13. Chọn partition count theo consumer group

Một topic có thể được nhiều consumer group độc lập đọc. Partition count giới hạn mức song song của từng group, nhưng không phải tổng số consumer của tất cả group cộng lại.

Ví dụ topic orders có 12 partition:

- Group billing có 6 consumer: mỗi consumer có thể nhận khoảng 2 partition.
- Group inventory có 12 consumer: mỗi consumer có thể nhận một partition.
- Group analytics có 3 consumer: mỗi consumer có thể nhận khoảng 4 partition.

Ba group có tiến độ độc lập và mỗi group đều đọc toàn bộ topic theo cách riêng. Tăng số group không làm partition count tăng, nhưng tăng tải đọc lên broker và network.

Khi sizing, hãy lập danh sách consumer group quan trọng, concurrency dự kiến và SLA riêng. Một topic có thể đáp ứng throughput của billing nhưng không đáp ứng yêu cầu song song của analytics nếu group đó cần nhiều worker hơn số partition.

## 14. Liên hệ partition với batch và producer throughput

Producer gom record thành batch theo partition. Các cấu hình như batch.size, linger.ms, compression và số request in-flight ảnh hưởng cách producer gửi dữ liệu.

Nếu partition count quá cao so với traffic, nhiều partition có thể không đủ record để lấp batch trong thời gian ngắn. Điều này có thể làm tăng số batch nhỏ và giảm hiệu quả nén/gửi.

Nếu partition count quá thấp, producer có thể dồn traffic vào ít leader broker, tạo bottleneck network hoặc disk. Cần xem phân phối leader và tải broker khi đánh giá throughput.

Không nên tăng partition chỉ để tăng batch size. Hãy đo batch size thực tế, request rate, byte rate và broker load. Cấu hình producer cần được điều chỉnh cùng partitioning strategy.

## 15. Quy trình benchmark để chọn số partition

Một quy trình thực tế:

1. **Mô tả workload:** record/giây, byte/giây, payload size, key distribution, retention và consumer groups.
2. **Đặt mục tiêu:** throughput, p95/p99 latency, lag tối đa và mức tăng trưởng dự kiến.
3. **Chọn baseline:** tạo topic với một số partition vừa phải và replication phù hợp môi trường test.
4. **Đo một partition:** xác định throughput an toàn trong điều kiện consumer và downstream thực tế.
5. **Tăng dần partition:** thử các mức như 3, 6, 12, 18; quan sát throughput có còn tăng hay đã bão hòa.
6. **Thử concurrency:** thay đổi consumer concurrency và số application instance để xác định mức song song có ích.
7. **Kiểm tra key skew:** xác nhận traffic phân phối tương đối hợp lý và không có hot partition.
8. **Kiểm tra failure/rebalance:** dừng consumer hoặc broker theo kịch bản test để đo thời gian phục hồi.
9. **Kiểm tra chi phí:** quan sát CPU, disk, network, open files, replica và thời gian startup/rebalance.
10. **Chọn mức có headroom:** đáp ứng peak và SLO mà vẫn còn dư địa cho tăng trưởng hợp lý.

Không benchmark chỉ bằng record nhỏ, không key hoặc một consumer giả lập đơn giản nếu production dùng payload lớn và database thật. Workload thử nghiệm phải gần với cách producer chọn key, serializer nén dữ liệu và consumer gọi downstream.

## 16. Ví dụ lập bảng sizing

Giả sử workload có các số liệu sau:

| Thông số | Giá trị giả định |
|---|---:|
| Throughput mục tiêu | 12.000 record/giây |
| Throughput an toàn/partition | 1.000 record/giây |
| Pod consumer | 4 |
| Concurrency mỗi pod | 3 |
| Consumer mong muốn | 12 |
| Partition theo throughput | 12 |
| Partition theo parallelism | 12 |

Theo hai điều kiện cơ bản, baseline là 12 partition. Sau đó cần benchmark để xác nhận:

- Có đạt 12.000 record/giây khi downstream hoạt động thật không?
- Traffic có phân phối đều qua 12 partition không?
- p95/p99 latency có đạt SLO ở peak không?
- Broker có đủ disk/network và khả năng quản lý replica không?
- Khi một pod dừng, consumer còn lại có xử lý được backlog không?
- Khi mở rộng lên 6 pod, topic có đủ partition để tận dụng thêm consumer không?

Nếu benchmark cho thấy throughput chỉ đạt 8.000 record/giây do database, tăng partition lên 24 có thể không giúp. Cần xử lý bottleneck database hoặc giảm công việc trên mỗi record trước.

## 17. Khi nào nên tạo topic mới để đổi partitioning?

Tạo topic mới thay vì tăng partition trực tiếp có thể phù hợp khi:

- Cần giảm số partition.
- Cần thay đổi key hoặc partitioner mà vẫn giữ ordering rõ ràng.
- Muốn thay đổi schema, retention hoặc replication cùng một đợt migration.
- Cần chuyển từ phân phối theo tenant sang phân phối theo aggregate.
- Muốn kiểm soát thời điểm cutover và rollback.

Một migration có thể gồm:

1. Tạo topic mới với partition count và key strategy đã chọn.
2. Triển khai consumer có thể đọc topic mới.
3. Chuyển producer sang topic mới theo chiến lược dual-publish hoặc cutover có kiểm soát.
4. Đối chiếu event ID/version để phát hiện thiếu hoặc trùng.
5. Chờ consumer group mới bắt kịp và xác nhận dữ liệu.
6. Chuyển traffic hoàn toàn, sau đó ngừng topic cũ theo retention/runbook.

Dual-publish có thể tạo duplicate hoặc lệch thứ tự nếu không có định danh và idempotency. Với yêu cầu ordering theo aggregate, cần một điểm cutover rõ ràng hoặc cơ chế version để consumer phát hiện event cũ/mới.

## 18. Những lỗi sizing thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer nhàn rỗi dù lag cao | Partition count thấp hơn mức consumer song song cần | Đánh giá tăng partition hoặc tối ưu xử lý |
| Tăng partition nhưng throughput không đổi | Bottleneck ở DB, CPU, network hoặc hot key | Đo từng dependency và phân phối key |
| Một partition lag rất cao | Hot key hoặc partition assignment lệch | Phân tích key distribution và leader load |
| Nhiều consumer idle | Concurrency/group members vượt partition count | Giảm consumer hoặc tăng partition khi có lý do |
| Ordering theo key bị thay đổi sau mở rộng | Key được ánh xạ sang partition khác sau khi tăng count | Thiết kế routing/migration bảo toàn ordering |
| Producer batching kém | Nhiều partition ít traffic, batch bị phân mảnh | Đo batch size và cân nhắc partition count |
| Broker tốn nhiều tài nguyên | Quá nhiều partition/replica | Rà soát topic topology và giới hạn cluster |
| Không thể giảm partition | Kafka không hỗ trợ giảm partition trực tiếp | Tạo topic mới và migrate |
| Group rebalance kéo dài | Nhiều partition hoặc quá nhiều consumer thay đổi cùng lúc | Đo rebalance, chọn assignor và rollout hợp lý |

## 19. Checklist trước khi chốt partition count

- [ ] Đã đo record rate và byte rate ở peak.
- [ ] Đã đo kích thước payload và compression thực tế.
- [ ] Đã benchmark throughput an toàn trên mỗi partition.
- [ ] Partition count đủ cho consumer parallelism mong muốn.
- [ ] Đã tính tổng concurrency trên tất cả application instance.
- [ ] Key phân phối đủ đều và không tạo hot partition ngoài dự kiến.
- [ ] Đã xác định yêu cầu ordering theo key.
- [ ] Đã đánh giá tác động tăng partition lên key mapping.
- [ ] Đã tách partition count khỏi replication factor.
- [ ] Broker đủ CPU, disk, network, file handle và headroom cho replica.
- [ ] Retention và dung lượng được tính cho toàn bộ replica.
- [ ] Đã xem xét các consumer group cùng đọc topic.
- [ ] Đã benchmark throughput, latency, lag, rebalance và failure recovery.
- [ ] Có kế hoạch migration nếu cần giảm partition hoặc đổi key strategy.

Tối ưu số partition là bài toán cân bằng giữa throughput, mức song song, ordering và chi phí broker. Hãy bắt đầu từ workload và consumer concurrency, đo năng lực an toàn trên mỗi partition, sau đó benchmark với key distribution và payload thực tế. Đặc biệt, hãy xem partition count là quyết định kiến trúc dài hạn: tăng partition có thể làm thay đổi key mapping, còn giảm partition thường cần migration sang topic mới.
