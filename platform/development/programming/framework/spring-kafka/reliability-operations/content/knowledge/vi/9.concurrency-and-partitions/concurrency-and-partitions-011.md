# Scale consumer theo lag

Trong một hệ thống Spring Kafka, consumer lag cho biết consumer group đang chậm bao nhiêu so với dữ liệu đã có trên broker. Khi tốc độ producer cao hơn tốc độ xử lý của consumer trong một khoảng thời gian, lag tăng dần. Scale consumer là cách tăng năng lực xử lý bằng cách bổ sung consumer instance hoặc tăng concurrency, nhưng hiệu quả phụ thuộc vào số partition, phân bố tải, thời gian xử lý mỗi record và chi phí rebalance.

Mục tiêu vận hành không phải lúc nào cũng là đưa lag về 0 ngay lập tức. Cần giữ độ trễ xử lý trong giới hạn nghiệp vụ, có đủ năng lực hấp thụ đỉnh tải và tránh scale quá mức gây rebalance liên tục hoặc tranh chấp tài nguyên. Lag cần được đọc cùng throughput, tuổi record cũ nhất, mức sử dụng CPU/IO và số partition đang hoạt động.

## 1. Consumer lag là gì?

Kafka lưu record theo partition. Mỗi consumer group có committed offset riêng cho từng partition. Consumer lag thường được biểu diễn bằng chênh lệch giữa vị trí cuối hiện có trên broker và committed offset của group.

Ví dụ một partition:

    Log end offset:       10,000
    Committed offset:      9,700
    Consumer lag:            300 records

Group còn 300 record chưa được ghi nhận là đã xử lý. Đây là một ước lượng số lượng record đang chờ theo định nghĩa của công cụ đo. Một số exporter dùng log end offset, một số metric có thể dùng high watermark hoặc last stable offset. Với consumer dùng isolation.level=read_committed, record thuộc transaction chưa commit không được giao cho consumer, vì vậy cần hiểu định nghĩa lag của công cụ giám sát đang dùng.

Lag không trực tiếp cho biết thời gian chờ của người dùng. 300 record có thể được xử lý trong vài giây nếu consumer có throughput cao, nhưng cũng có thể mất nhiều phút nếu record cần gọi nhiều dịch vụ hoặc partition bị nghẽn. Hãy theo dõi thêm tuổi của record chưa xử lý lâu nhất (oldest record age) và thời gian từ lúc event được tạo tới lúc nghiệp vụ hoàn tất.

Lag cũng không đồng nghĩa với số record bị mất. Khi committed offset được cập nhật sớm, lag có thể thấp dù side effect chưa hoàn tất. Ngược lại, nếu consumer xử lý thành công nhưng commit chậm, lag có thể cao hơn lượng công việc thực tế còn lại. Đọc lag cùng trạng thái xử lý và offset commit sẽ giúp tránh kết luận sai.

## 2. Vì sao lag tăng?

Lag tăng khi tốc độ record đi vào lớn hơn tốc độ record được xử lý và commit trong một khoảng thời gian.

Các nguyên nhân thường gặp:

- Producer tăng lưu lượng theo giờ cao điểm hoặc một chiến dịch.
- Consumer xử lý mỗi record lâu hơn do database, HTTP service hoặc truy vấn chậm.
- Số consumer đang hoạt động thấp hơn nhu cầu.
- Topic có ít partition nên group không thể sử dụng thêm consumer.
- Một vài partition nhận phần lớn traffic do key phân bố không đều.
- Consumer bị rebalance thường xuyên, khiến thời gian xử lý bị gián đoạn.
- Consumer bị giới hạn CPU, bộ nhớ, connection pool hoặc thread pool.
- Retry và DLT tăng làm thời gian xử lý record kéo dài.
- Broker hoặc mạng chậm khiến poll, fetch hoặc commit bị trì hoãn.
- Consumer dừng hoặc crash, khiến partition tạm thời không có consumer xử lý.

Không nên mặc định lag tăng có nghĩa là cần thêm pod. Nếu database đã quá tải, thêm consumer chỉ làm số request đồng thời tăng và khiến database chậm hơn. Nếu chỉ một partition có lag cao, tăng số consumer có thể không giúp vì một partition tại một thời điểm chỉ được gán cho một consumer trong cùng group.

## 3. Giới hạn scale do partition

Trong một consumer group, một partition chỉ được gán cho tối đa một consumer tại một thời điểm. Vì vậy, số consumer hoạt động hữu ích trong group bị giới hạn bởi số partition được subscribe.

Ví dụ topic có 6 partition:

| Số consumer trong group | Consumer có partition | Consumer nhàn rỗi |
|---:|---:|---:|
| 2 | 2 | 0 |
| 4 | 4 | 0 |
| 6 | 6 | 0 |
| 8 | 6 | 2 |
| 12 | 6 | 6 |

Thêm consumer vượt số partition không làm tăng khả năng xử lý song song của topic đó. Những consumer không được assign partition vẫn chiếm tài nguyên và có thể làm tăng chi phí vận hành.

Nếu cần xử lý song song hơn, cần xem xét tăng partition count hoặc thay đổi cách chia workload. Tăng partition là quyết định kiến trúc: nó ảnh hưởng tới số consumer có thể hoạt động, phân bố dữ liệu, tài nguyên broker, số file log và cách key được ánh xạ vào partition.

Không nên tăng partition chỉ vì lag tăng trong một thời điểm ngắn. Hãy xác nhận rằng năng lực xử lý trên mỗi partition đã được tối ưu, consumer đã scale tới giới hạn hữu ích và broker có đủ tài nguyên.

## 4. Scale consumer trong Spring Kafka

Spring Kafka có thể chạy nhiều consumer thread trong một ConcurrentMessageListenerContainer. Thuộc tính concurrency xác định số child container/consumer được tạo bởi container đó.

Ví dụ cấu hình trong Spring Boot:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Với cấu hình trên, một instance ứng dụng có thể chạy tối đa ba consumer cho listener container tương ứng, tùy số partition được assign. Nếu topic có 6 partition và chỉ có một instance, concurrency=3 có thể sử dụng tối đa ba partition đồng thời. Nếu triển khai hai instance cùng group, tổng số consumer mong muốn có thể là sáu.

Có thể cấu hình bằng Java:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener dùng factory này:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Concurrency là số consumer được tạo trong mỗi application instance/container, không phải tổng số consumer của toàn bộ hệ thống. Nếu có 4 pod và concurrency=2, group có thể có tối đa 8 consumer cho listener này, nhưng chỉ tối đa bằng số partition được assign.

Khi thay đổi concurrency động hoặc scale pod, group có thể rebalance. Hãy tính thời gian rebalance vào ngân sách xử lý lag và kiểm tra xem consumer có thực sự nhận thêm partition hay không.

## 5. Scale theo chiều ngang và chiều dọc

Có hai cách tăng năng lực consumer:

**Scale ngang (horizontal scaling):** tăng số application instance/pod cùng consumer group. Cách này tăng số consumer độc lập và có thể phân phối partition cho nhiều máy.

**Scale dọc (vertical scaling):** tăng CPU, memory hoặc tài nguyên mỗi instance, đồng thời có thể tăng concurrency nếu hệ thống còn khả năng xử lý song song. Cách này hữu ích khi mỗi consumer bị giới hạn bởi CPU hoặc bộ nhớ nhưng số partition không đủ để chia cho nhiều pod.

Ví dụ:

    Topic: 12 partitions

    2 pods x concurrency 2 = tối đa 4 consumers
    3 pods x concurrency 2 = tối đa 6 consumers
    3 pods x concurrency 4 = tối đa 12 consumers
    5 pods x concurrency 4 = tối đa 12 active consumers
                                  + 8 consumers có thể idle

Số consumer hoạt động tối đa trong ví dụ không vượt quá 12 partition. Scale ngang và concurrency cần được phối hợp để không tạo nhiều consumer dư thừa.

Khi chọn scale ngang, cân nhắc chi phí rebalance và việc kết nối tới database/service phụ thuộc. Khi chọn scale dọc, cân nhắc giới hạn CPU/memory của node và khả năng một instance trở thành điểm lỗi lớn hơn. Thường nên thử nghiệm cả hai cách với dữ liệu tải gần production.

## 6. Đo throughput trước khi chọn số consumer

Để xác định số consumer cần thiết, hãy đo:

- Tốc độ producer đưa record vào, ký hiệu λ (records/second).
- Throughput xử lý của một consumer, ký hiệu μ (records/second).
- Số partition có thể xử lý song song, ký hiệu P.
- Số consumer hoạt động hiện tại, ký hiệu C.
- Lag hiện tại và thời gian mong muốn để xử lý hết backlog.

Nếu các partition phân bố tương đối đều và mỗi consumer có throughput ổn định μ, năng lực xử lý gần đúng là:

    Capacity = min(C, P) * mu

Để lag không tăng dài hạn, capacity cần lớn hơn tốc độ đầu vào trung bình. Nếu capacity chỉ bằng λ, consumer có thể xử lý record mới nhưng không có dư địa để giảm backlog đã tích lũy.

Ví dụ:

- Producer tạo trung bình 1.200 record/giây.
- Một consumer xử lý được 250 record/giây.
- Topic có 8 partition.

Cần tối thiểu:

    C = ceil(1200 / 250) = 5

Năm consumer có năng lực danh nghĩa khoảng 1.250 record/giây. Biên dư 50 record/giây là quá nhỏ nếu traffic biến động hoặc thời gian xử lý không ổn định. Có thể cần thêm headroom hoặc tối ưu xử lý để giảm rủi ro lag tăng khi tải lên đỉnh.

Giả sử chọn 6 consumer:

    Capacity = 6 * 250 = 1500

Nếu tốc độ đầu vào vẫn là 1.200 record/giây, phần năng lực dư khoảng 300 record/giây có thể dùng để xử lý backlog. Đây chỉ là mô hình gần đúng; throughput thực tế còn phụ thuộc record size, key distribution, batch size, I/O, retry và thời gian chờ dịch vụ phụ thuộc.

## 7. Ước lượng thời gian xóa backlog

Khi lag đã tích lũy, capacity cần cao hơn tốc độ producer mới để backlog giảm. Với các giả định đơn giản:

    DrainRate = Capacity - lambda

    DrainTime = Lag / (Capacity - lambda)

Ví dụ:

- Lag hiện tại: 180.000 record.
- Producer tiếp tục tạo: 1.000 record/giây.
- 6 consumer, mỗi consumer xử lý 250 record/giây.
- Capacity danh nghĩa: 1.500 record/giây.

Khi đó:

    DrainRate = 1500 - 1000 = 500 records/second

    DrainTime = 180000 / 500 = 360 seconds

Thời gian lý thuyết khoảng 6 phút. Thực tế có thể lâu hơn do rebalance, partition skew, thời gian commit, batch fetch, GC, retry và sự thay đổi của producer rate. Dùng công thức để lập kế hoạch ban đầu, sau đó so sánh với tốc độ lag giảm quan sát được.

Nếu capacity nhỏ hơn hoặc bằng tốc độ đầu vào, backlog sẽ không giảm. Trong trường hợp đó, cần tăng năng lực xử lý, giảm tải đầu vào, tối ưu listener hoặc thay đổi partitioning.

## 8. Chọn metric để autoscale

Autoscaling theo CPU đơn thuần có thể bỏ lỡ tình huống consumer bị chờ I/O. Ví dụ listener dành phần lớn thời gian chờ database; CPU thấp nhưng lag tăng nhanh. Ngược lại, CPU cao có thể đến từ serialization hoặc GC mà thêm consumer chỉ làm tổng tải tăng.

Nên kết hợp nhiều tín hiệu:

| Metric | Cho biết điều gì | Cách sử dụng |
|---|---|---|
| Consumer lag tổng | Tổng backlog của group | Xác định nhu cầu xử lý chung |
| Lag theo partition | Phân bố backlog | Phát hiện partition nóng hoặc consumer lệch tải |
| Oldest record age | Tuổi record chưa xử lý lâu nhất | Đo mức trễ theo thời gian nghiệp vụ |
| Records consumed rate | Tốc độ xử lý thực tế | Ước lượng throughput mỗi consumer |
| Records produced rate | Tốc độ dữ liệu mới | Dự báo áp lực đầu vào |
| Processing duration | Thời gian xử lý mỗi record | Tìm listener hoặc dependency chậm |
| CPU và memory | Mức sử dụng tài nguyên | Phát hiện giới hạn compute/GC |
| Rebalance rate | Tần suất group thay đổi assignment | Phát hiện scale quá nhanh hoặc consumer không ổn định |
| Retry/DLT rate | Số record lỗi và thử lại | Phân biệt backlog nghiệp vụ với lỗi phụ thuộc |

Một chính sách tốt thường dùng lag và tuổi record làm tín hiệu chính, rồi dùng CPU, memory và throughput làm giới hạn hoặc điều kiện phụ. Metric cần được gắn nhãn theo consumer group, topic và partition để không trộn lag của các workload khác nhau.

Đừng chỉ dùng tổng lag. Ví dụ tổng lag 100.000 có thể phân bố đều trên 10 partition, hoặc tập trung gần như toàn bộ ở một partition. Hai tình huống cần cách xử lý khác nhau.

## 9. Tính số replica mục tiêu từ lag

Một cách đơn giản là đặt mục tiêu lag tối đa trên mỗi consumer hoặc mỗi partition. Ví dụ muốn mỗi consumer có không quá 10.000 record chờ:

    DesiredConsumers = ceil(TotalLag / TargetLagPerConsumer)

Sau đó giới hạn theo số partition:

    DesiredConsumers <= PartitionCount

Ví dụ:

- Total lag = 75.000 record.
- Target lag mỗi consumer = 10.000.
- Topic có 12 partition.

    DesiredConsumers = ceil(75000 / 10000) = 8

Mục tiêu là 8 consumer hoạt động. Nếu mỗi pod chạy concurrency=2, có thể cần 4 pod để tạo 8 consumer. Nếu pod hiện tại đã chạy concurrency=2, số replica mục tiêu có thể tính là:

    DesiredPods = ceil(DesiredConsumers / ConcurrencyPerPod)

Công thức này là điểm khởi đầu. Nó không thay thế throughput measurement. Nếu một consumer xử lý được 2.000 record/giây và target lag là 10.000, backlog có thể được xử lý trong vài giây; nếu throughput chỉ 50 record/giây, cùng target lag có thể tạo ra độ trễ vài phút.

Ngoài ra, mỗi pod có thể không nhận đúng cùng số partition do assignment strategy. Số replica mục tiêu nên được giới hạn bởi partition count và tài nguyên của downstream service.

## 10. Hysteresis, cooldown và giới hạn scale

Nếu autoscaler tăng giảm replica theo từng lần metric vượt ngưỡng nhỏ, hệ thống có thể dao động:

    Lag tăng -> scale out
       |
       v
    Rebalance -> consumer tạm dừng
       |
       v
    Lag giảm -> scale in
       |
       v
    Rebalance lần nữa
       |
       v
    Lag tăng trở lại

Mỗi lần scale có thể tạo rebalance, làm gián đoạn tiêu thụ và gây thêm duplicate do record đã xử lý nhưng offset chưa commit. Hãy dùng hysteresis và cooldown:

- Chỉ scale out khi lag vượt ngưỡng trong một khoảng thời gian hoặc oldest age vượt SLA.
- Scale out nhanh hơn scale in nếu cần hấp thụ đỉnh tải.
- Chờ đủ thời gian sau rebalance để quan sát throughput ổn định.
- Scale in khi lag thấp liên tục trong một cửa sổ dài hơn.
- Đặt minReplicas và maxReplicas rõ ràng.
- Giới hạn maxReplicas theo partition count, connection pool và năng lực downstream.
- Tránh thay đổi concurrency liên tục khi workload dao động nhẹ.

Ví dụ chính sách minh họa:

| Điều kiện | Hành động |
|---|---|
| Lag > 50.000 trong 3 phút và oldest age > 30 giây | Scale out 1-2 pod |
| Lag tiếp tục tăng sau 5 phút | Đánh giá tăng thêm nếu còn partition và capacity |
| Lag < 5.000 trong 15 phút, throughput ổn định | Cho phép scale in 1 pod |
| Rebalance liên tục hoặc database pool bão hòa | Tạm dừng scale out và điều tra dependency |

Ngưỡng thực tế phải dựa trên SLA, traffic và thời gian xử lý record. Không dùng các con số ví dụ như mặc định production.

## 11. Partition skew và hot partition

Tăng consumer chỉ giúp khi có partition chưa được xử lý song song. Nếu một key rất phổ biến khiến phần lớn record đi vào cùng partition, consumer của partition đó có thể bị quá tải trong khi các consumer khác nhàn rỗi.

Ví dụ:

    orders-0: lag 90,000
    orders-1: lag  2,000
    orders-2: lag  1,500
    orders-3: lag  1,200
    orders-4: lag  1,000
    orders-5: lag    800

Tổng lag cao nhưng phần lớn backlog nằm ở orders-0. Thêm consumer không chia một partition thành nhiều consumer. Cần điều tra key distribution, record size và thời gian xử lý theo key.

Các hướng xử lý:

- Chọn key phân bố đều hơn nếu nghiệp vụ cho phép.
- Tránh một key đại diện cho toàn bộ workload.
- Tách loại event hoặc tenant lớn sang topic riêng khi cần cô lập tải.
- Giảm thời gian xử lý của partition nóng.
- Dùng mô hình fan-out hoặc chia nhỏ aggregate nếu có thể bảo toàn yêu cầu thứ tự.
- Tăng partition và thay đổi chiến lược keying chỉ sau khi đánh giá ảnh hưởng tới thứ tự.

Không dùng random key một cách tùy tiện nếu nghiệp vụ cần thứ tự theo orderId hoặc customerId. Kafka bảo đảm thứ tự trong partition; thay đổi key có thể làm mất tính tuần tự của một aggregate nếu event cũ và mới được đưa sang partition khác nhau.

## 12. Khi nào cần tăng partition?

Nếu consumer đã scale tới gần số partition và lag vẫn tăng đều, có thể cần tăng partition count. Trước khi thay đổi, cần trả lời:

1. Throughput trên từng partition đã gần giới hạn chưa?
2. Broker có đủ CPU, network, disk và file handle cho partition mới không?
3. Producer và consumer có hỗ trợ số partition mới không?
4. Key distribution có đủ đều để sử dụng partition mới không?
5. Nghiệp vụ có phụ thuộc thứ tự theo key không?
6. Có quy trình triển khai và theo dõi rebalance khi thay đổi topology không?

Tăng partition count không di chuyển record cũ sang partition mới. Nó chỉ thay đổi cách record mới được phân bố. Với default partitioner dựa trên key, việc tăng số partition có thể khiến cùng một key trong tương lai được ánh xạ sang partition khác so với trước. Nếu hệ thống dựa vào thứ tự tuyệt đối của event theo key qua thời gian, cần kế hoạch migration hoặc cơ chế version/sequence để xử lý chuyển tiếp.

Tăng partition cũng làm tăng metadata, file log và chi phí replication. Không tăng vô hạn; xác định partition count dựa trên throughput mục tiêu, consumer concurrency, retention và khả năng broker.

## 13. Rebalance là chi phí của scale

Khi thêm hoặc bớt consumer, group cần phân phối lại partition. Trong thời gian rebalance, consumer có thể tạm ngừng xử lý. Với group lớn, topic nhiều partition hoặc assignment strategy không phù hợp, thời gian rebalance có thể đáng kể.

Các nguyên nhân rebalance thường gặp:

- Scale out/in số pod.
- Consumer restart hoặc crash.
- Heartbeat/session timeout.
- Listener xử lý quá lâu làm vượt max.poll.interval.ms.
- Thay đổi subscription hoặc partition topology.

Để giảm tác động:

- Dùng cooperative sticky assignment nếu phiên bản Kafka và cấu hình ứng dụng hỗ trợ, giúp chuyển partition dần thay vì thu hồi toàn bộ.
- Đặt thời gian xử lý và poll phù hợp.
- Dùng graceful shutdown để consumer rời group có kiểm soát.
- Tránh autoscaling dao động.
- Theo dõi rebalance duration và số lần rebalance.
- Đảm bảo listener idempotent vì record có thể được giao lại sau khi partition chuyển consumer.

Cần kiểm tra assignment strategy thực tế. Không phải mọi cluster hoặc client version đều dùng cùng một chiến lược mặc định.

## 14. Giới hạn downstream trước khi scale

Consumer không hoạt động độc lập. Một listener có thể đọc Kafka nhanh nhưng ghi vào database, gọi REST API hoặc gửi event sang hệ thống khác. Khi scale consumer, số request đồng thời tới dependency cũng tăng.

Ví dụ có 8 consumer, mỗi consumer xử lý 100 record/giây. Nếu mỗi record tạo một database transaction, database có thể phải xử lý tới 800 transaction/giây. Tăng lên 16 consumer có thể đẩy tải lên 1.600 transaction/giây mà không làm throughput tăng nếu database chỉ xử lý được 900 transaction/giây.

Trước khi scale, kiểm tra:

- Database connection pool và giới hạn connection.
- Số request đồng thời tới API bên ngoài.
- Rate limit của dịch vụ phụ thuộc.
- Lock contention và transaction duration.
- CPU, memory, garbage collection và network của consumer.
- Batch size, compression, serialization và fetch settings.
- Retry storm khi dependency lỗi.

Nếu dependency là bottleneck, hãy tối ưu query, batch write, connection pool hoặc giới hạn concurrency. Có thể đặt semaphore/bulkhead để giới hạn số request đồng thời. Tăng consumer trong khi dependency đã bão hòa có thể làm lag và error rate cùng tăng.

## 15. Cấu hình concurrency, max poll và batch

Concurrency không phải tham số duy nhất ảnh hưởng throughput. Một consumer có thể poll nhiều record mỗi lần; listener có thể xử lý record tuần tự hoặc theo batch. Các tham số cần điều chỉnh cùng nhau:

| Cấu hình | Tác động | Điều cần cân nhắc |
|---|---|---|
| spring.kafka.listener.concurrency | Số consumer thread mỗi instance | Không vượt số partition hữu ích |
| max.poll.records | Số record tối đa trả về trong một poll | Batch lớn có thể tăng thời gian xử lý trước poll tiếp theo |
| max.poll.interval.ms | Thời gian tối đa giữa các poll | Phải lớn hơn thời gian xử lý batch trong trường hợp dự kiến |
| fetch.min.bytes | Dữ liệu tối thiểu broker chờ gom trước khi trả fetch | Có thể tăng throughput nhưng thêm latency |
| fetch.max.wait.ms | Thời gian broker chờ fetch đủ dữ liệu | Cân bằng latency và batch efficiency |
| max.partition.fetch.bytes | Dữ liệu tối đa fetch cho một partition | Cần đủ cho record lớn và bộ nhớ |
| listener AckMode | Thời điểm commit offset | Ảnh hưởng duplicate và độ trễ commit |

Ví dụ cấu hình nền tảng:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 4
      ack-mode: record
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 250
~~~

Đây là giá trị minh họa. Nếu 250 record mất hơn 5 phút để xử lý, consumer có thể vượt max.poll.interval.ms và bị group loại bỏ. Hãy đo thời gian xử lý p95/p99 và chọn poll interval đủ lớn, đồng thời kiểm soát thời gian xử lý để consumer vẫn poll đều.

Batch lớn có thể tăng throughput nhờ giảm overhead, nhưng cũng làm tăng thời gian xử lý trước commit và lượng công việc có thể phải replay khi lỗi. Với side effect không idempotent, batch lớn làm hậu quả duplicate phức tạp hơn.

## 16. Ví dụ autoscaling theo lag

Một autoscaler có thể đọc metric consumer group lag từ Prometheus hoặc hệ thống metrics tương đương, sau đó điều chỉnh số replica của deployment. Cần phân biệt metric lag tổng, lag theo partition và số partition đang hoạt động.

Một logic mục tiêu đơn giản:

~~~text
totalLag = sum(lag for all subscribed partitions)
desiredConsumers = ceil(totalLag / targetLagPerConsumer)
desiredConsumers = min(desiredConsumers, partitionCount)
desiredPods = ceil(desiredConsumers / concurrencyPerPod)
desiredPods = clamp(desiredPods, minPods, maxPods)
~~~

Trong triển khai thực tế, cần bổ sung:

- Chỉ scale out nếu lag vượt ngưỡng đủ lâu.
- Không scale vượt partition count hoặc giới hạn downstream.
- Dùng cooldown sau scale để group ổn định.
- Chỉ scale in khi lag thấp liên tục và không có oldest record age vượt SLA.
- Theo dõi số consumer thực sự được assign partition, không chỉ số pod.
- Xử lý metric không có dữ liệu hoặc consumer group mới chưa có committed offset.

Có thể dùng Kubernetes HPA với custom/external metrics hoặc KEDA Kafka scaler tùy nền tảng. Hãy kiểm tra cách scaler xác định lag, cách xử lý partition không có offset và cách giới hạn replica. Cấu hình autoscaler phải khớp với consumer group và topic thực tế; metric tổng của nhiều group có thể dẫn tới scale sai workload.

## 17. Kế hoạch scale trong một đợt traffic tăng

Giả sử một dịch vụ xử lý đơn hàng có 12 partition và đang chạy 3 pod, mỗi pod concurrency=2. Tổng số consumer tối đa là 6, còn khả năng sử dụng thêm partition.

Khi lag tăng:

1. Xác nhận producer rate tăng hay consumer throughput giảm.
2. Xem lag từng partition để phát hiện partition nóng.
3. Kiểm tra processing duration, CPU, database pool và error rate.
4. Nếu downstream còn capacity, tăng từ 3 lên 4 pod để có tối đa 8 consumer.
5. Chờ rebalance hoàn tất và đo throughput mới.
6. Nếu lag tiếp tục tăng, có thể scale tới 6 pod, tương ứng tối đa 12 consumer.
7. Khi lag giảm dưới ngưỡng ổn định trong một khoảng thời gian, scale in từng bước.
8. Theo dõi oldest record age, duplicate, retry và DLT trong toàn bộ quá trình.

Không scale ngay từ 3 lên 20 pod nếu topic chỉ có 12 partition. Việc đó không tạo thêm consumer hoạt động hữu ích và có thể làm group phức tạp hơn.

## 18. Quy trình điều tra khi scale không làm lag giảm

Nếu đã tăng consumer nhưng lag vẫn không giảm, hãy phân tích theo thứ tự:

**Bước 1: Xác nhận consumer thực sự hoạt động.** Kiểm tra số member trong group, partition assignment, consumer idle và trạng thái rebalance. Pod tăng nhưng consumer không được assign partition thì throughput không tăng.

**Bước 2: Xem lag theo partition.** Nếu chỉ một partition tăng, tìm hot key hoặc record xử lý đặc biệt chậm. Nếu tất cả partition tăng, kiểm tra capacity tổng.

**Bước 3: Đo throughput.** So sánh records consumed rate trước và sau scale. Nếu throughput không đổi, nguyên nhân có thể là partition ceiling, dependency bottleneck hoặc consumer không nhận partition.

**Bước 4: Kiểm tra dependency.** Xem database latency, connection pool, HTTP rate limit, lock contention và retry. Nếu error rate tăng sau scale, giảm concurrency có thể giúp hệ thống phục hồi.

**Bước 5: Kiểm tra rebalance và poll.** Rebalance liên tục, max.poll.interval.ms bị vượt hoặc listener quá chậm có thể làm mất phần lớn thời gian tiêu thụ.

**Bước 6: Xem kích thước và chi phí record.** Record lớn, deserialize tốn CPU, payload không đồng đều hoặc một số loại event có xử lý đắt có thể làm throughput theo record không phản ánh khối lượng công việc thực tế.

**Bước 7: Quyết định tối ưu hay tăng partition.** Chỉ tăng partition khi đã xác nhận số partition là giới hạn song song và broker có đủ tài nguyên.

## 19. Kiểm thử khả năng scale

Trước production, chạy load test với lưu lượng và phân bố key gần thực tế. Không chỉ tăng số record đồng đều; hãy mô phỏng burst, hot key, record lớn và dependency chậm.

Các kịch bản nên đo:

1. Tăng producer rate theo từng mức và xác định điểm lag bắt đầu tăng.
2. Tăng số pod trong giới hạn partition, đo throughput sau mỗi rebalance.
3. Tăng concurrency trong một pod, đo CPU, memory và processing rate.
4. Scale vượt partition count để xác nhận consumer dư thừa không tăng throughput.
5. Tạo một partition nóng và đo chênh lệch lag giữa các partition.
6. Làm database chậm hoặc trả lỗi tạm thời, xác nhận autoscaler không tạo retry storm.
7. Dừng một consumer trong lúc xử lý để đo rebalance và duplicate.
8. Tạo backlog lớn rồi đo thời gian drain thực tế so với ước lượng.
9. Scale in khi lag thấp để xác nhận group ổn định và partition được giao lại an toàn.
10. Kiểm tra DLT và retry topic để bảo đảm lỗi không bị che giấu bởi lag của topic chính.

Ghi nhận số pod, số consumer active, partition assignment, producer rate, consumer rate, lag, oldest age, rebalance duration và downstream latency. Những dữ liệu này giúp chọn ngưỡng autoscaling dựa trên kết quả đo thay vì phỏng đoán.

## 20. Nguyên tắc scale consumer theo lag

- Đọc lag cùng throughput và oldest record age; không dùng một con số lag riêng lẻ.
- Xác định partition count trước khi đặt max consumer.
- Tính concurrency tổng bằng số pod nhân concurrency mỗi pod, rồi giới hạn theo partition.
- Đo throughput mỗi consumer và năng lực downstream trước khi scale.
- Dùng lag theo partition để phát hiện hot partition.
- Scale out có kiểm soát, có hysteresis và cooldown để tránh rebalance liên tục.
- Scale in chậm hơn scale out và chỉ khi backlog ổn định thấp.
- Theo dõi max.poll.interval.ms, processing duration và rebalance.
- Tăng partition chỉ khi cần thêm khả năng song song và đã đánh giá ảnh hưởng key/order.
- Giữ consumer idempotent vì rebalance, retry và commit chưa chắc chắn có thể tạo duplicate.
- Đối chiếu lag với kết quả nghiệp vụ để phát hiện trường hợp commit sớm.
- Đặt giới hạn replica theo database, API rate limit và tài nguyên broker.

Scale consumer theo lag là bài toán cân bằng giữa tốc độ dữ liệu vào, năng lực xử lý, số partition và khả năng của các dịch vụ phụ thuộc. Khi lag tăng, hãy xác định chính xác điểm nghẽn trước khi tăng replica. Khi số consumer hoạt động phù hợp với partition và downstream, autoscaling có thể giảm thời gian chờ backlog mà vẫn giữ consumer group ổn định.