# Giới hạn của tăng concurrency

Trong Spring Kafka, tăng concurrency giúp một consumer group xử lý nhiều partition song song hơn bằng cách tạo thêm consumer và listener thread. Tuy nhiên, số thread tăng lên không đồng nghĩa throughput tăng tương ứng. Mức song song thực tế bị giới hạn bởi số partition được subscribe, cách Kafka phân phối partition, tải của từng partition và năng lực của các thành phần phía sau như database, API, CPU và network.

Hiểu đúng giới hạn này giúp tránh cấu hình quá nhiều consumer không có partition, làm hệ thống tốn tài nguyên, tăng rebalance và gây áp lực lên downstream mà không cải thiện tốc độ xử lý.

## 1. Concurrency trong Spring Kafka có nghĩa gì?

Một Kafka consumer xử lý các record từ những partition được giao cho nó. Trong một consumer group, mỗi partition chỉ được giao cho tối đa một consumer member tại một thời điểm ổn định. Một consumer có thể sở hữu nhiều partition, nhưng một partition không được chia đồng thời cho nhiều consumer member trong cùng group.

Spring Kafka cung cấp ConcurrentMessageListenerContainer để chạy nhiều consumer thông qua một listener container. Thuộc tính concurrency xác định số child listener container và consumer tương ứng mà container quản lý.

Ví dụ:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);
    return factory;
}
~~~

Listener sử dụng factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Factory trên tạo bốn consumer member cho listener trong group orders-service. Mỗi consumer chạy trên một luồng riêng và nhận một hoặc nhiều partition theo assignment của group.

Có thể đặt concurrency trực tiếp trên listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        concurrency = "4")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Thuộc tính concurrency trên listener cho phép cấu hình số consumer riêng cho listener đó. Nếu dùng thuộc tính này, hãy xác định rõ nó đang ghi đè mức concurrency mặc định của container factory để tránh nhầm lẫn khi vận hành.

Với Spring Boot, có thể đặt mức mặc định qua cấu hình:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 4
~~~

Concurrency là số consumer do listener container quản lý. Nó không phải số partition, số record được xử lý đồng thời bên trong một partition, hay số request mạng mà Kafka producer có thể gửi.

## 2. Partition giới hạn mức song song tối đa

Giả sử topic orders có sáu partition. Một group có thể có tối đa sáu consumer member đang sở hữu partition của topic đó cùng lúc. Nếu group chỉ có ba consumer, mỗi consumer có thể nhận hai partition. Nếu group có sáu consumer, mỗi consumer có thể nhận một partition. Nếu group có mười consumer, bốn consumer sẽ không được giao partition trong assignment ổn định.

~~~text
Topic orders có 6 partition

3 consumer:
  Consumer A: P0, P1
  Consumer B: P2, P3
  Consumer C: P4, P5

6 consumer:
  Consumer A: P0
  Consumer B: P1
  Consumer C: P2
  Consumer D: P3
  Consumer E: P4
  Consumer F: P5

10 consumer:
  Consumer A-F: mỗi consumer một partition
  Consumer G-J: không có partition
~~~

Với một topic và một subscription đồng nhất, số consumer đang hoạt động có thể nhận partition không vượt quá số partition của topic. Tăng concurrency từ 6 lên 10 trong ví dụ không tạo thêm khả năng đọc song song vì topic chỉ có sáu partition.

Đây là giới hạn quan trọng nhất khi scale consumer group: partition là đơn vị song song cơ bản của Kafka. Một consumer có thể xử lý nhiều partition, nhưng một partition không thể được chia cho hai consumer member trong cùng group chỉ bằng cách tăng concurrency.

Nếu listener subscribe nhiều topic, cần tính tổng số partition mà subscription đó có thể nhận. Tuy nhiên, mỗi member có thể subscribe tập topic khác nhau, nên số partition đủ điều kiện và assignment thực tế cần được xem xét theo từng subscription. Không lấy tổng partition của toàn cluster để dự đoán concurrency cho một listener.

## 3. Tính tổng số consumer qua concurrency và số replica

Concurrency được áp dụng cho từng instance ứng dụng. Khi chạy nhiều replica, tổng số consumer member trong group bằng tổng concurrency của các listener instance tham gia group đó.

Ví dụ:

| Số replica ứng dụng | Concurrency mỗi replica | Tổng consumer member |
|---:|---:|---:|
| 1 | 4 | 4 |
| 2 | 4 | 8 |
| 3 | 4 | 12 |
| 5 | 4 | 20 |

Giả sử topic orders có 12 partition và mỗi replica chạy concurrency bằng 4:

- Một replica tạo 4 consumer; cả 4 có thể nhận partition.
- Hai replica tạo 8 consumer; có thể có 8 consumer hoạt động.
- Ba replica tạo 12 consumer; có thể tận dụng đủ 12 partition.
- Năm replica tạo 20 consumer; chỉ tối đa 12 consumer nhận partition, còn lại không có partition.

Mô hình tính nhanh:

~~~text
Tổng consumer trong group
    = số replica × concurrency mỗi replica

Consumer có thể sở hữu partition
    <= số partition đủ điều kiện trong subscription

Consumer không có partition
    = tổng consumer - consumer được assignment
~~~

Đây là giới hạn trên để lập kế hoạch. Assignment có thể không cân bằng tuyệt đối nếu subscription khác nhau, nhiều topic có số partition khác nhau hoặc assignor áp dụng chiến lược riêng.

Không nên chỉ nhìn concurrency trong application.yml. Khi triển khai Kubernetes hoặc autoscaling, phải tính cả số replica tối đa mà hệ thống có thể tạo. Ví dụ concurrency bằng 3 có vẻ nhỏ, nhưng 10 replica sẽ tạo 30 consumer member trong group.

## 4. Concurrency không chia nhỏ một partition

Kafka giữ thứ tự record trong từng partition. Consumer group assignment giao toàn bộ partition cho một consumer member tại một thời điểm ổn định. Do đó, nếu một partition có tốc độ phát record cao, tăng số consumer trong group không thể chia tải của riêng partition đó cho nhiều consumer.

Ví dụ topic orders có bốn partition:

~~~text
P0:  1.000 record/giây
P1:    100 record/giây
P2:    100 record/giây
P3:    100 record/giây

Tổng: 1.300 record/giây
~~~

Nếu group có bốn consumer, mỗi consumer nhận một partition. Consumer sở hữu P0 vẫn phải xử lý 1.000 record/giây. Thêm bốn consumer nữa không giúp consumer P0 chia công việc cho một consumer thứ hai vì P0 vẫn chỉ có một owner trong group.

Tình huống này thường được gọi là partition skew hoặc hot partition. Số partition có thể được chia đều nhưng lượng record, kích thước payload và chi phí xử lý của mỗi partition lại rất khác nhau.

Các nguyên nhân phổ biến:

- Một key chiếm tỷ lệ lớn trong traffic.
- Một khách hàng hoặc một thực thể phát sinh quá nhiều event.
- Một loại event có payload lớn hoặc xử lý tốn CPU hơn các loại khác.
- Producer dùng key không phù hợp khiến nhiều record dồn vào một partition.
- Partition có dữ liệu cũ tồn đọng hoặc downstream xử lý một nhóm record chậm hơn.

Khi gặp hot partition, cần tìm nguyên nhân phân phối tải. Có thể thiết kế lại key, tăng partition, tách workload thành topic khác hoặc phân rã nghiệp vụ thành các luồng xử lý độc lập nếu yêu cầu thứ tự cho phép. Chỉ tăng concurrency sẽ không giải quyết được nút thắt nằm trong một partition.

## 5. Key và thứ tự nghiệp vụ giới hạn khả năng scale

Producer thường dùng record key để xác định partition. Các record có cùng key thường được gửi đến cùng partition, nhờ đó Kafka giữ thứ tự của chúng trong partition đó.

Ví dụ, nếu orderId là key:

~~~text
order-1001 -> P0: Created -> Paid -> Shipped
order-1002 -> P1: Created -> Cancelled
order-1003 -> P2: Created -> Paid
~~~

Consumer group có thể xử lý các partition P0, P1 và P2 song song. Nhưng các record của order-1001 vẫn cần được xử lý theo thứ tự trong P0 nếu nghiệp vụ phụ thuộc thứ tự đó.

Tăng concurrency không cho phép xử lý Created, Paid và Shipped của cùng một partition song song mà vẫn tự động giữ đúng thứ tự hoàn tất nghiệp vụ. Nếu listener chuyển công việc sang executor bất đồng bộ, các tác vụ có thể hoàn tất khác thứ tự dù record được poll theo đúng thứ tự. Khi đó ứng dụng phải tự điều phối thứ tự hoặc bảo đảm nghiệp vụ chịu được việc hoàn tất lệch thứ tự.

Một key quá phổ biến cũng có thể tạo hot partition. Nếu tất cả event dùng cùng key, tăng partition count cũng không giúp phân phối key đó ra nhiều partition theo cách mặc định. Muốn chia tải cần xem lại ý nghĩa của key và yêu cầu thứ tự.

Tăng số partition của topic cũng cần thận trọng. Khi số partition thay đổi, phép ánh xạ key sang partition có thể thay đổi đối với các record mới. Record cũ và mới của cùng key có thể nằm ở hai partition khác nhau, làm mất một thứ tự liên tục xuyên suốt quá trình mở rộng. Hãy đánh giá tác động này trước khi tăng partition cho topic có yêu cầu thứ tự theo key.

## 6. Downstream có thể trở thành nút thắt

Kafka có thể cung cấp record nhanh hơn tốc độ ứng dụng xử lý hoặc ghi kết quả. Nếu listener xử lý bằng database, REST API, hệ thống thanh toán hoặc một service khác, throughput cuối cùng bị giới hạn bởi thành phần chậm nhất trong chuỗi.

Ví dụ:

~~~text
Kafka partitions
       |
       v
Consumer listeners
       |
       v
Database connection pool
       |
       v
Database
~~~

Giả sử mỗi consumer có thể xử lý 500 record/giây, nhưng database chỉ chịu được tổng cộng 1.500 transaction/giây. Tăng số consumer từ 3 lên 8 có thể khiến nhiều request cùng chờ connection hoặc lock database. Throughput không tăng tương ứng, trong khi latency và lỗi timeout tăng.

Các giới hạn downstream thường gặp:

- Database connection pool không đủ connection cho số listener thread.
- Database bị giới hạn CPU, IOPS, lock contention hoặc transaction duration.
- REST API có rate limit hoặc giới hạn số request đồng thời.
- Service downstream có thread pool nhỏ hoặc hàng đợi nội bộ đầy.
- Network bandwidth hoặc TLS connection setup trở thành chi phí đáng kể.
- Cache miss, truy vấn không tối ưu hoặc payload lớn làm tăng thời gian xử lý.

Nếu mỗi consumer giữ một database connection trong thời gian xử lý, số consumer tăng có thể đòi hỏi tăng pool size. Nhưng tăng connection pool không tự làm database nhanh hơn; nó có thể khiến database chịu nhiều transaction đồng thời hơn mức tối ưu.

Trước khi tăng concurrency, hãy đo thời gian xử lý listener và latency của downstream. Nếu listener đang chờ database, tăng consumer chỉ chuyển hàng đợi từ Kafka sang database.

## 7. CPU, memory và thread overhead

Mỗi consumer member có state, network activity, buffer và luồng thực thi riêng. Tăng concurrency làm tăng số thread và tài nguyên mà JVM cần quản lý.

Các chi phí có thể tăng gồm:

- Stack memory của thread.
- Consumer metadata, fetch state và network buffers.
- Chi phí serialization/deserialization.
- CPU cho polling, callback, logging và xử lý record.
- Garbage collection do nhiều object và batch cùng tồn tại.
- Context switching khi có quá nhiều thread runnable.
- Kết nối mạng và số request đồng thời đến broker.

Nếu ứng dụng bị giới hạn CPU, thêm consumer thread có thể làm thời gian xử lý của từng thread dài hơn do cạnh tranh CPU. Nếu heap hoặc GC đã là nút thắt, nhiều consumer và batch có thể làm tình hình xấu hơn.

Không nên coi một thread cho mỗi consumer là miễn phí. Hãy kiểm tra giới hạn CPU/memory của container, heap, thread count, GC pause và mức sử dụng CPU trước khi chọn concurrency.

## 8. Rebalance và chi phí khi tăng consumer

Khi tăng concurrency hoặc tăng số replica, các consumer mới tham gia group. Group phải rebalance để phân phối lại partition. Trong thời gian rebalance, một số partition có thể tạm dừng xử lý, làm consumer lag tăng.

Với eager rebalance, toàn bộ partition đang sở hữu có thể bị revoke rồi assignment mới được áp dụng. Với cooperative rebalance, chỉ partition cần chuyển owner bị thu hồi theo từng bước, giúp giảm lượng công việc bị gián đoạn. Tuy nhiên, cooperative rebalance vẫn có chi phí và không loại bỏ hoàn toàn thời gian chuyển owner.

Nếu hệ thống autoscale liên tục, group có thể rebalance nhiều lần:

~~~text
Scale up
   |
   v
Consumer mới join group
   |
   v
Rebalance
   |
   v
Partition chuyển owner
   |
   v
Consumer tiếp tục xử lý
   |
   v
Scale down / restart
   |
   v
Rebalance lần nữa
~~~

Rebalance liên tục có thể làm giảm throughput tổng thể, đặc biệt nếu thời gian xử lý partition state hoặc callback revoke dài. Vì vậy, autoscaling cần có cooldown, graceful shutdown và ngưỡng scale hợp lý. Không nên tăng giảm replica theo dao động lag trong thời gian rất ngắn.

Các thao tác revoke và assign cũng có thể làm ứng dụng phải khởi tạo lại cache hoặc state cục bộ gắn với partition. Nếu state cần phục hồi từ store, việc chuyển owner thường có thêm chi phí đọc lại state.

## 9. max.poll.interval.ms và thời gian xử lý

Consumer cần tiếp tục gọi poll để duy trì tiến độ xử lý và membership theo giao thức tương ứng. Nếu listener xử lý quá lâu giữa các lần poll, consumer có thể vượt max.poll.interval.ms và bị xem là không tiến triển. Khi đó partition có thể được giao cho member khác.

Tăng concurrency không nhất thiết làm từng record xử lý nhanh hơn. Nếu CPU hoặc downstream đã bão hòa, thời gian xử lý có thể tăng, khiến consumer khó gọi poll đúng hạn.

Ví dụ, một lần poll trả về 100 record. Listener xử lý từng record mất trung bình 300 ms và xử lý tuần tự. Tổng thời gian xử lý có thể lên đến khoảng 30 giây, chưa tính overhead. Nếu max.poll.interval.ms thấp hơn thời gian thực tế giữa hai lần poll, consumer có nguy cơ rời group.

Các hướng xử lý:

- Đo thời gian xử lý thực tế theo poll batch.
- Điều chỉnh max.poll.records để giới hạn số record trả về mỗi lần poll.
- Tối ưu thao tác database và API.
- Tăng max.poll.interval.ms khi thời gian xử lý dài là yêu cầu hợp lý và đã được kiểm soát.
- Tránh chuyển xử lý bất đồng bộ mà không có chiến lược commit offset và quản lý ownership rõ ràng.

Tăng max.poll.interval.ms chỉ kéo dài thời gian chờ trước khi consumer bị xem là không tiến triển. Nó không làm downstream nhanh hơn và không giải quyết việc listener bị treo.

## 10. Concurrency và cách commit offset

Mỗi consumer member quản lý offset cho các partition được giao. Khi tăng concurrency, số consumer độc lập và số partition được xử lý song song tăng lên, nhưng chính sách commit offset vẫn cần phù hợp với cách listener hoàn tất nghiệp vụ.

Với xử lý đồng bộ trong listener, container có thể commit theo ack mode đã cấu hình. Nếu listener trả về trước khi side effect bất đồng bộ hoàn tất, offset có thể được commit sớm hơn thời điểm nghiệp vụ thực sự hoàn tất, tùy cách ứng dụng tích hợp. Nếu process crash, record có thể bị mất khỏi góc nhìn nghiệp vụ dù Kafka đã coi offset là đã xử lý.

Nếu listener xử lý song song các record từ cùng partition, cần theo dõi thứ tự hoàn tất và offset commit. Commit offset vượt qua một record chưa xử lý thành công có thể làm record đó bị bỏ qua khi consumer khởi động lại.

Ví dụ:

~~~text
Offset nhận:       100   101   102
Tác vụ hoàn tất:   100   102   101

Không được commit offset 103
trước khi xử lý 101 thành công.
~~~

Kafka consumer commit offset theo vị trí tiếp theo cần đọc, không phải một tập xác nhận độc lập tùy ý cho từng record. Khi xử lý bất đồng bộ, ứng dụng phải bảo đảm chỉ commit đến offset liên tục đã hoàn tất theo đúng semantics của consumer và Spring Kafka.

Tăng concurrency giữa các partition không gây đảo thứ tự trong một partition nếu mỗi partition vẫn được xử lý tuần tự. Nhưng tăng concurrency trong logic ứng dụng bằng executor có thể tạo thứ tự hoàn tất khác nhau. Đây là hai kiểu song song khác nhau và cần được thiết kế riêng.

## 11. Ví dụ lựa chọn concurrency theo số partition

Giả sử topic orders có 12 partition và ứng dụng chạy ba replica. Có thể ước lượng:

| Concurrency mỗi replica | Tổng consumer | Consumer tối đa có partition | Consumer có thể idle |
|---:|---:|---:|---:|
| 1 | 3 | 3 | 0 |
| 2 | 6 | 6 | 0 |
| 3 | 9 | 9 | 0 |
| 4 | 12 | 12 | 0 |
| 5 | 15 | 12 | 3 |
| 6 | 18 | 12 | 6 |

Trong ví dụ này, concurrency bằng 4 tận dụng được 12 partition nếu assignment và subscription đồng nhất. Tăng lên 5 tạo thêm ba consumer member nhưng không tăng số partition có thể đọc song song.

Tuy nhiên, concurrency bằng 4 chưa chắc là cấu hình nhanh nhất. Nếu database chỉ xử lý tốt sáu luồng đồng thời, concurrency bằng 2 có thể đạt throughput tốt hơn và latency thấp hơn. Nếu mỗi partition có tải rất thấp, concurrency bằng 1 hoặc 2 có thể đã đáp ứng SLO.

Mục tiêu là tìm mức concurrency phù hợp với năng lực của toàn bộ pipeline, không phải đạt số consumer tối đa.

## 12. Cách xác định bottleneck trước khi tăng concurrency

Trước khi thay đổi cấu hình, cần xác định consumer group đang bị giới hạn ở đâu.

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Lag cao trên tất cả partition, CPU consumer thấp | Consumer chờ downstream hoặc fetch/batch chưa hiệu quả | Đo listener latency, network, database wait và fetch metrics |
| Lag cao chủ yếu ở một partition | Hot partition hoặc key skew | Xem throughput theo partition và phân phối key |
| CPU consumer gần 100% | Xử lý CPU-bound | Profile code, serialization và GC; thử scale theo partition nếu còn capacity |
| Database pool wait cao | Database connection pool hoặc database quá tải | Đo active/idle connection, query latency, lock và transaction |
| API downstream trả 429/5xx | Rate limit hoặc service quá tải | Kiểm tra giới hạn concurrency, retry/backoff và capacity phía API |
| Rebalance thường xuyên | Membership thay đổi hoặc consumer không poll đúng hạn | Kiểm tra deployment, autoscaling, heartbeat, poll interval và callback |
| Nhiều consumer không có partition | Tổng consumer vượt số partition đủ điều kiện | Tính replica × concurrency và điều chỉnh số consumer |
| Throughput không tăng dù thêm consumer | Partition ceiling hoặc bottleneck khác | So sánh partition count, per-partition lag và downstream capacity |

Một số metric cần theo dõi:

- Consumer lag tổng và theo từng partition.
- Records consumed rate và bytes consumed rate.
- Listener processing time, p95 và p99.
- Consumer poll interval và thời gian xử lý giữa hai lần poll.
- Rebalance rate và thời gian rebalance.
- Commit latency và commit error rate.
- JVM CPU, heap, thread count và GC pause.
- Database pool active, pending và connection acquisition time.
- Downstream API latency, error rate và rate limit response.

Lag tổng có thể che giấu một partition bị nghẽn. Hãy quan sát lag theo partition và throughput theo consumer member để biết tải đang tập trung ở đâu.

## 13. Tăng partition có phải luôn là cách giải quyết?

Khi số partition thấp hơn mức song song mong muốn, tăng partition có thể tạo thêm đơn vị xử lý song song. Nhưng đây là quyết định về cấu trúc topic, không chỉ là điều chỉnh concurrency.

Trước khi tăng partition, cần xem xét:

- Key hiện tại có phân phối đều không?
- Các record cùng key có cần giữ thứ tự không?
- Việc tăng partition có làm thay đổi ánh xạ key sang partition cho record mới không?
- Broker có đủ CPU, disk và network để phục vụ thêm partition không?
- Số partition tăng có làm tăng chi phí metadata, file segment và replication không?
- Consumer group có đủ năng lực xử lý và downstream có đủ capacity không?

Tăng partition không tự chia một key nóng thành nhiều luồng nếu partitioner vẫn định tuyến key đó vào cùng partition. Nếu nghiệp vụ bắt buộc thứ tự theo key, việc chia key cần có thiết kế rõ ràng, chẳng hạn chia theo sub-key khi có thể chấp nhận thứ tự riêng trong từng nhánh.

Không nên tăng partition chỉ để có thể đặt concurrency cao. Hãy xác định mức throughput mục tiêu và giới hạn của producer, broker, consumer, database và downstream trước khi thay đổi topology.

## 14. Quy trình thử nghiệm concurrency

Một cách tiếp cận có kiểm soát:

1. Ghi nhận baseline: số partition, số replica, concurrency, throughput, lag, listener latency và downstream latency.
2. Tính tổng consumer member theo replica nhân concurrency.
3. So sánh tổng consumer với số partition đủ điều kiện trong subscription.
4. Tăng concurrency từng bước nhỏ, chẳng hạn từ 1 lên 2 rồi 3, thay vì nhảy ngay lên giá trị lớn.
5. Chờ group hoàn tất rebalance và hệ thống ổn định trước khi lấy số liệu.
6. Đo throughput, p95/p99 latency, lag theo partition, CPU, GC và downstream saturation.
7. Kiểm tra consumer idle, retry, commit và lỗi xử lý.
8. Chạy thử tình huống scale up, scale down và restart để đo chi phí rebalance.
9. Chọn giá trị đạt SLO với mức tài nguyên và độ ổn định phù hợp.
10. Lưu lại lý do cấu hình và giới hạn scale tối đa để tránh autoscaler tạo nhiều consumer hơn partition.

Không đánh giá kết quả ngay sau khi tăng concurrency trong lúc group đang rebalance. Cần để assignment ổn định và loại bỏ ảnh hưởng của warm-up, cache, connection pool và dữ liệu thử nghiệm.

## 15. Những hiểu nhầm thường gặp

**Tăng concurrency luôn tăng throughput.** Không đúng. Throughput có thể bị giới hạn bởi số partition, hot partition, CPU hoặc downstream.

**Concurrency bằng số partition là luôn tối ưu.** Không đúng. Đây chỉ là mức có thể tận dụng tất cả partition bằng một consumer cho mỗi partition. Nếu downstream không chịu được số luồng đó, concurrency thấp hơn có thể ổn định và nhanh hơn.

**Tăng số replica không làm thay đổi concurrency.** Không đúng. Mỗi replica tạo thêm consumer member theo concurrency của listener; tổng consumer tăng theo số replica.

**Một partition có thể được chia cho nhiều consumer trong cùng group bằng cách tăng concurrency.** Không đúng. Partition là đơn vị assignment; một consumer member sở hữu partition tại một thời điểm ổn định.

**Nhiều consumer hơn luôn làm tải cân bằng hơn.** Không đúng. Assignor cân bằng partition count theo chiến lược của nó, nhưng không biết chi phí xử lý và tốc độ record của từng partition.

**Tăng partition luôn giải quyết hot key.** Không đúng. Cùng một key thường vẫn được định tuyến vào một partition. Muốn chia tải cần thay đổi chiến lược key hoặc mô hình xử lý và đánh giá lại yêu cầu thứ tự.

**Tăng max.poll.interval.ms sẽ giải quyết listener chậm.** Không đúng. Nó chỉ thay đổi giới hạn thời gian giữa các lần poll; nguyên nhân CPU hoặc downstream chậm vẫn còn.

**Listener trả về nghĩa là nghiệp vụ bất đồng bộ đã hoàn tất.** Không đúng. Nếu ứng dụng gửi công việc sang executor rồi trả về, cần quản lý offset và ownership để không commit trước khi side effect hoàn tất.

## 16. Hướng dẫn thiết kế

Khi cấu hình consumer concurrency trong Spring Kafka, hãy bắt đầu từ số partition và throughput cần đạt. Tính tổng consumer theo số replica và concurrency, sau đó đối chiếu với partition đủ điều kiện và năng lực xử lý của downstream.

Một cấu hình triển khai nên cân nhắc:

1. Chọn partition count theo khả năng song song, thứ tự theo key và năng lực broker.
2. Đặt concurrency mặc định phù hợp với số partition và tài nguyên của một instance.
3. Tính số replica tối đa để không tạo quá nhiều consumer idle.
4. Đo tải theo từng partition để phát hiện hot partition và key skew.
5. Giới hạn database pool và downstream concurrency theo capacity thật.
6. Cấu hình max.poll.records và max.poll.interval.ms theo thời gian xử lý thực tế.
7. Dùng cooperative rebalance hoặc static membership khi phù hợp với phiên bản và quy trình triển khai.
8. Dùng graceful shutdown và xử lý revoke để chuyển ownership an toàn.
9. Giữ xử lý tuần tự trong partition nếu nghiệp vụ cần thứ tự; thiết kế idempotent khi có retry hoặc xử lý lại.
10. Tăng concurrency từng bước và đánh giá throughput, lag, latency, rebalance cùng tài nguyên.

Concurrency chỉ tạo thêm consumer member. Nó không tạo thêm partition, không chia nhỏ một partition, không làm database nhanh hơn và không loại bỏ chi phí rebalance. Tăng concurrency có ích khi còn partition chưa được khai thác và các thành phần phía sau còn đủ năng lực. Khi một trong các giới hạn đó đã chạm ngưỡng, cần xử lý đúng bottleneck thay vì tiếp tục tăng số thread.
