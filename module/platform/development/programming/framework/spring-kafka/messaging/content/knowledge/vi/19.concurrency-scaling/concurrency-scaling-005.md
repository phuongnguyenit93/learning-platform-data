# Scale nhiều instance ứng dụng

Một ứng dụng Spring Kafka có thể chạy nhiều instance đồng thời để tăng năng lực xử lý và duy trì dịch vụ khi một instance gặp sự cố. Với consumer, cách scale phổ biến là chạy nhiều bản sao ứng dụng cùng tham gia một Kafka consumer group. Kafka phân phối các partition của topic cho các consumer member trong group; mỗi partition tại một thời điểm chỉ được gán cho tối đa một consumer đang hoạt động trong group đó.

Muốn scale hiệu quả, cần phối hợp ba cấp độ: số instance ứng dụng, concurrency của listener trong mỗi instance và số partition của topic. Tăng số instance không tự động tăng throughput nếu topic có quá ít partition hoặc bottleneck nằm ở database, HTTP service hay logic xử lý. Ngược lại, dùng group ID khác nhau cho từng instance khiến mỗi group đọc toàn bộ luồng dữ liệu riêng, tạo fan-out thay vì chia tải.

Bài học thuộc chương **Concurrency và scale** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Scale nhiều instance nghĩa là gì?

Một instance là một tiến trình ứng dụng đang chạy. Trong production, có thể triển khai nhiều instance của cùng một service trên nhiều container, pod, VM hoặc máy chủ. Các instance thường dùng chung cấu hình topic và consumer group để chia nhau công việc.

Ví dụ service `order-projection` chạy ba instance:

~~~text
order-projection-1 ─┐
order-projection-2 ─┼──> Kafka consumer group: order-projection
order-projection-3 ─┘
                         |
                         v
                  Topic: order-events
                  Partition 0..5
~~~

Các instance không tự chọn partition tùy ý. Consumer group coordinator và partition assignor phân phối partition cho các consumer member. Khi một instance tham gia hoặc rời group, assignment có thể thay đổi và group thực hiện rebalance.

Scale ngang (horizontal scaling) là tăng hoặc giảm số instance ứng dụng. Scale dọc (vertical scaling) là tăng CPU, memory hoặc tài nguyên của một instance. Hai cách có thể kết hợp, nhưng scale ngang consumer bị giới hạn bởi số partition có thể phân phối.

~~~mermaid
flowchart TD
    A[Ứng dụng có nhiều instance] --> B[Cùng group ID]
    B --> C[Kafka consumer group]
    C --> D[Partition assignment]
    D --> E[Consumer member ở instance A]
    D --> F[Consumer member ở instance B]
    D --> G[Consumer member ở instance C]
    E --> H[Listener xử lý record]
    F --> H
    G --> H
~~~

## 2. Dùng cùng group ID để chia tải

Nếu nhiều instance cần cùng xử lý một luồng event theo mô hình work-sharing, tất cả consumer phải dùng cùng group ID.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

Mỗi instance chạy cùng artifact và cấu hình group ID `order-projection`. Kafka xem các consumer đó là member của cùng một group và phân phối partition giữa chúng.

Trong một group:

- Mỗi partition được gán cho tối đa một consumer member tại một thời điểm.
- Một consumer có thể được gán nhiều partition.
- Các consumer chia sẻ tiến độ offset theo từng topic-partition.
- Khi một consumer rời group, partition của nó có thể được giao cho member khác.
- Mỗi member không nhận toàn bộ record của topic nếu group có nhiều consumer; các member chia nhau partition.

Cùng group ID là điều kiện quan trọng để chia tải. Nếu mỗi instance có group ID riêng, Kafka tạo các group độc lập và mỗi group đọc toàn bộ dữ liệu của topic theo offset riêng.

## 3. Phân biệt work-sharing và fan-out

Hai mô hình thường bị nhầm:

| Mô hình | Group ID | Kết quả |
| --- | --- | --- |
| Nhiều instance của cùng service chia tải | Giống nhau | Các consumer chia nhau partition và record. |
| Nhiều service độc lập cùng cần nhận mọi event | Khác nhau theo service | Mỗi group đọc toàn bộ luồng dữ liệu độc lập. |
| Mỗi instance vô tình dùng group ID riêng | Khác nhau theo instance | Mỗi instance nhận bản sao toàn bộ dữ liệu, không chia tải. |

Ví dụ:

~~~text
Work-sharing:
  order-projection-1 ─┐
  order-projection-2 ─┼── group: order-projection
  order-projection-3 ─┘       mỗi event được một member trong group xử lý

Fan-out:
  billing-service ───── group: billing
  audit-service ─────── group: audit
  analytics-service ─── group: analytics
       mỗi group đều đọc toàn bộ event của topic
~~~

Fan-out phù hợp khi billing, audit và analytics đều cần dữ liệu. Work-sharing phù hợp khi nhiều replica của billing service chỉ cần chia nhau xử lý cùng một luồng. Không nên thêm pod ID hoặc hostname vào group ID nếu mục tiêu là chia tải trong cùng service.

## 4. Partition giới hạn số consumer hoạt động

Partition là đơn vị song song tối đa trong một consumer group. Nếu topic có sáu partition, tối đa sáu consumer member có thể nhận partition từ topic đó cùng lúc. Consumer dư vẫn có thể tham gia group nhưng không có partition để đọc.

Ví dụ:

| Số partition | Số consumer member | Consumer có assignment hữu ích tối đa |
| ---: | ---: | ---: |
| 6 | 1 | 1 |
| 6 | 3 | 3 |
| 6 | 6 | 6 |
| 6 | 9 | 6 |
| 6 | 12 | 6 |

Giới hạn này áp dụng cho tổng số partition được subscription của group cung cấp. Nếu group subscribe nhiều topic, số partition có thể được tính trên toàn bộ tập topic mà group đọc.

Ví dụ topic có sáu partition và ứng dụng chạy mười instance, mỗi instance một consumer. Tối đa sáu consumer nhận partition; bốn consumer còn lại idle đối với topic đó. Thêm instance không làm một partition được nhiều consumer trong cùng group xử lý song song.

Nếu một partition đang nóng hoặc xử lý chậm, các consumer idle không thể tự nhận một phần của partition đó. Cần điều tra key distribution, partition count và thời gian xử lý.

## 5. Concurrency trong mỗi instance

Một instance Spring Kafka có thể tạo nhiều consumer cho cùng listener bằng concurrency của listener container. Khi chạy nhiều instance, tổng số consumer member là tích của số instance và concurrency trên mỗi instance, nếu mỗi instance đều tạo cùng listener.

Ví dụ:

- 3 instance ứng dụng.
- Mỗi instance cấu hình concurrency = 2.
- Tổng cộng có thể có 6 consumer member trong cùng group.
- Topic có 6 partition thì group có thể phân phối đủ partition cho 6 consumer.

Sơ đồ:

~~~text
Instance A: consumer A-1, consumer A-2 ─┐
Instance B: consumer B-1, consumer B-2 ─┼── group order-projection
Instance C: consumer C-1, consumer C-2 ─┘

Topic order-events:
  P0  P1  P2  P3  P4  P5
  Mỗi partition được giao cho một consumer member
~~~

Có thể cấu hình concurrency qua container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(2);
    return factory;
}
~~~

Hoặc cấu hình concurrency trên listener endpoint nếu phiên bản Spring Kafka và cách khai báo của dự án hỗ trợ:

~~~java
@KafkaListener(
    id = "orderProjectionListener",
    topics = "order-events",
    groupId = "order-projection",
    concurrency = "2"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Không nên cấu hình concurrency ở nhiều nơi mà không hiểu precedence giữa annotation, factory và Spring Boot properties. Chọn một nơi quản lý chính để người vận hành dễ xác định số consumer được tạo trên mỗi instance.

## 6. Tính tổng số consumer khi scale

Có thể ước lượng số consumer member được tạo như sau:

\[
C_{\text{total}} = R \times C_{\text{instance}}
\]

Trong đó:

- R là số replica/instance ứng dụng.
- C_instance là concurrency của listener trên mỗi instance.

Số consumer có assignment hữu ích không vượt số partition được group subscribe:

\[
C_{\text{active}} \leq \min(C_{\text{total}}, P)
\]

Trong đó P là tổng số partition thuộc subscription của group. Công thức là giới hạn trên; assignment thực tế còn phụ thuộc subscription và partition assignor.

Ví dụ:

| Replica | Concurrency/instance | Consumer member | Partition | Consumer có assignment |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 2 | 4 | 8 | Tối đa 4 |
| 3 | 2 | 6 | 6 | Tối đa 6 |
| 4 | 2 | 8 | 6 | Tối đa 6 |
| 4 | 1 | 4 | 12 | Tối đa 4 |
| 6 | 2 | 12 | 12 | Tối đa 12 |

Đây là phép tính quy hoạch ban đầu. Nó không khẳng định mỗi consumer có cùng lượng dữ liệu hoặc throughput; partition có thể lệch tải và listener có thể xử lý với tốc độ khác nhau.

## 7. Cách Kafka phân phối partition

Partition assignor quyết định cách phân phối partition cho consumer member trong group. Một số assignor phổ biến:

- **RangeAssignor:** phân phối theo phạm vi partition của từng topic.
- **RoundRobinAssignor:** phân phối luân phiên trên tập topic-partition.
- **StickyAssignor:** cố gắng giữ assignment ổn định và cân bằng khi có thể.
- **CooperativeStickyAssignor:** hỗ trợ cooperative rebalancing để giảm số partition phải thu hồi cùng lúc.

Hành vi thực tế phụ thuộc assignor được cấu hình, phiên bản Kafka client và khả năng tương thích giữa các member. Không nên giả định mọi cluster đều dùng cùng một assignor mặc định.

Với nhiều topic, RangeAssignor có thể tạo phân phối không đều trong một số topology, còn round-robin hoặc sticky có thể tạo kết quả khác. Nếu cần assignment cụ thể, hãy thử nghiệm với số topic, partition và consumer member thực tế.

Cooperative rebalancing có thể giảm gián đoạn khi thay đổi membership, nhưng không loại bỏ hoàn toàn rebalance. Tất cả member cần dùng cấu hình assignor tương thích để quá trình chuyển đổi diễn ra đúng.

## 8. Rebalance khi scale up hoặc scale down

Khi thêm instance, consumer mới tham gia group. Coordinator cập nhật membership và group thực hiện rebalance để phân phối lại partition. Khi giảm instance hoặc một consumer bị mất kết nối, group cũng cần rebalance để giao partition còn lại cho member đang hoạt động.

Trong giai đoạn rebalance:

- Một số partition có thể tạm dừng xử lý.
- Assignment cũ được thu hồi hoặc chuyển giao.
- Consumer mới nhận partition và tiếp tục từ offset đã commit.
- Record chưa commit có thể được đọc lại.
- Throughput có thể giảm tạm thời, nhất là khi rebalance diễn ra thường xuyên.

Scale liên tục lên/xuống theo dao động ngắn có thể làm group rebalance quá nhiều. Autoscaler nên có cooldown, stabilization window hoặc ngưỡng đủ ổn định trước khi thay đổi replica.

Không nên đánh giá scale chỉ bằng việc số pod đã tăng. Hãy kiểm tra group state, member count, partition assignment, lag và thời gian rebalance sau khi scale.

## 9. Offset dùng chung trong group

Offset được lưu theo group ID và từng topic-partition. Khi một partition được chuyển từ consumer A sang consumer B trong cùng group, consumer B tiếp tục từ committed offset của group nếu offset còn hợp lệ.

Scale instance không tạo một bộ offset mới cho từng pod. Điều này cho phép consumer thay thế tiếp tục công việc của member trước đó.

Ví dụ:

~~~text
Group: order-projection

order-events-0 -> committed offset 1200
order-events-1 -> committed offset 950
order-events-2 -> committed offset 1800

Trước rebalance:
  Instance A sở hữu P0, P1
  Instance B sở hữu P2

Sau rebalance:
  Instance B có thể nhận P0
  Instance C có thể nhận P1, P2

Offset vẫn thuộc group order-projection
~~~

Nếu mỗi instance dùng group ID khác nhau, offset được theo dõi riêng cho từng group. Điều này tạo fan-out và làm tăng số lần đọc dữ liệu trên broker.

Không nên reset offset khi scale up. Việc thêm consumer không yêu cầu reset tiến độ; Kafka dùng committed offset hiện có cho từng partition.

## 10. Ordering khi chạy nhiều instance

Kafka giữ thứ tự record trong từng partition. Trong cùng group, một partition được gán cho tối đa một consumer member tại một thời điểm, giúp duy trì thứ tự đọc của partition khi consumer xử lý tuần tự.

Nếu producer dùng orderId làm key, các event cùng orderId thường được định tuyến vào cùng partition theo partitioner và topology tương ứng. Khi scale nhiều instance, partition đó có thể chuyển từ instance này sang instance khác sau rebalance, nhưng không bị chia đồng thời cho hai member của cùng group.

Tuy vậy, ordering nghiệp vụ vẫn có thể bị phá vỡ nếu:

- Listener submit công việc sang thread pool và không chờ hoàn tất.
- Consumer commit offset trước khi tác vụ nghiệp vụ hoàn tất.
- Dùng non-blocking retry khiến event sau được xử lý trước event lỗi.
- Nhiều producer phát event cùng key mà không có quy tắc sequence/coordination.
- Thay đổi số partition làm ánh xạ key sang partition thay đổi.

Scale ngang không tự giải quyết ordering. Cần giữ key ổn định, xử lý tuần tự theo partition hoặc key và thiết kế retry phù hợp.

## 11. Khi nào tăng partition?

Nếu group đã có số consumer hữu ích bằng số partition mà lag vẫn tăng, tăng instance không giúp tăng mức song song của topic đó. Có thể cần tăng partition, nhưng đây là quyết định topology cần đánh giá.

Tăng partition có thể:

- Tăng mức song song tối đa cho consumer group trong tương lai.
- Phân phối tải qua nhiều consumer hơn.
- Tăng metadata, replication traffic và tài nguyên broker.
- Thay đổi mapping key sang partition với partitioner dựa trên hash/modulo.
- Ảnh hưởng ordering theo key khi record cũ và mới có thể nằm ở partition khác nhau.

Trước khi tăng partition, kiểm tra:

1. Bottleneck thực sự nằm ở consumer capacity hay database/API downstream.
2. Partition có bị hot key hoặc skew không.
3. Có thể chấp nhận thay đổi key-to-partition mapping không.
4. Có cần drain backlog hoặc version topic không.
5. Broker có đủ disk, network và replication capacity không.

Nếu một partition nóng do một key chiếm phần lớn lưu lượng, tăng partition có thể không giúp key đó phân tán vì cùng key vẫn đi về một partition theo partitioner. Cần xem lại đơn vị key hoặc cách chia aggregate nếu nghiệp vụ cho phép.

## 12. Scale theo throughput và lag

Consumer group cần xử lý dữ liệu nhanh ít nhất bằng tốc độ dữ liệu đi vào nếu muốn giữ lag ổn định. Khi throughput producer lớn hơn throughput consumer trong thời gian dài, backlog tăng.

Một phép ước lượng capacity đơn giản:

\[
R_{\text{needed}} =
\left\lceil
\frac{\lambda_{\text{incoming}}}
{\mu_{\text{per-consumer}}}
\right\rceil
\]

Trong đó:

- λ_incoming là tốc độ record đi vào group.
- μ_per-consumer là throughput thực tế của một consumer member.
- R_needed là số consumer cần thiết theo mô hình tải đơn giản.

Sau đó phải giới hạn theo partition và kiểm tra bottleneck downstream. Throughput của consumer không nhất thiết tuyến tính khi tăng số member, vì database connection pool, broker, CPU, network và partition skew có thể giới hạn hệ thống.

Ví dụ, producer tạo 4.000 record/giây và một consumer xử lý bền vững 800 record/giây. Ước lượng ban đầu cần năm consumer hoạt động. Nếu topic chỉ có ba partition, group không thể dùng đủ năm consumer cho topic đó; cần đánh giá partition topology hoặc tối ưu throughput mỗi partition.

Để đo đúng, dùng workload gần production và theo dõi lag theo partition, records-consumed rate, listener duration, CPU, memory, database latency và rebalance.

## 13. Autoscaling dựa trên consumer lag

Có thể tự động tăng/giảm replica theo consumer lag hoặc các metric liên quan. Tuy nhiên, chỉ dùng CPU làm tín hiệu có thể không phù hợp: consumer có thể chờ I/O với CPU thấp nhưng lag vẫn tăng.

Các tín hiệu có thể dùng:

- Tổng lag hoặc lag lớn nhất theo partition.
- Tốc độ tăng/giảm lag.
- Thời gian xử lý record/batch.
- Records consumed rate và producer rate.
- CPU/memory.
- Số partition và số consumer đang có assignment.
- Trạng thái group và rebalance rate.

Một quy trình autoscaling nên:

1. Xác định ngưỡng lag dựa trên SLA và retention.
2. Scale out khi lag tăng liên tục và còn partition để sử dụng.
3. Chờ rebalance hoàn tất rồi đo lại throughput.
4. Scale in khi backlog ổn định và consumer còn dư capacity.
5. Dùng cooldown/stabilization để tránh dao động replica.
6. Không scale vượt giới hạn hữu ích của partition nếu không có lý do khác.
7. Giữ minimum replica phù hợp yêu cầu availability.

Ví dụ, topic có 12 partition và concurrency 1, autoscaler có thể scale tối đa khoảng 12 consumer member hữu ích cho group đó. Nếu concurrency 2 trên mỗi instance, chỉ cần khoảng sáu instance để tạo 12 consumer member. Con số triển khai thực tế còn phụ thuộc resource và assignment.

Khi scale về zero, group không còn consumer member. Producer vẫn có thể ghi dữ liệu; lag tăng và consumer chỉ tiếp tục khi có instance mới. Scale-to-zero chỉ phù hợp khi SLA chấp nhận độ trễ khởi động và backlog.

## 14. Cấu hình trong Spring Boot và triển khai nhiều replica

Ví dụ cấu hình một listener với concurrency hai:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      concurrency: 2
~~~

Spring Boot áp dụng concurrency cho listener container được auto-configure. Nếu ứng dụng tạo container factory riêng, hãy cấu hình concurrency trên factory đó hoặc trên endpoint tương ứng để bảo đảm giá trị thực tế đúng như dự định.

Trong Kubernetes, có thể chạy nhiều replica của cùng Deployment. Mỗi pod sử dụng cùng group ID và cùng subscription; Kafka tự phân phối partition khi pod tham gia group.

Ví dụ khái niệm:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-projection
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-projection
  template:
    metadata:
      labels:
        app: order-projection
    spec:
      containers:
        - name: app
          image: example/order-projection:1.0.0
~~~

Manifest chỉ minh họa số replica. Cần cấu hình resource request/limit, readiness/liveness, termination grace period, secret và kết nối Kafka theo tiêu chuẩn triển khai của môi trường.

Không đặt group ID có chứa tên pod nếu muốn chia tải. Nếu group ID thay đổi theo pod, mỗi pod trở thành một group độc lập và nhận toàn bộ event.

## 15. Graceful shutdown và scale down

Khi orchestrator giảm replica, pod bị terminate. Spring application cần có thời gian dừng listener container, hoàn tất hoặc hủy xử lý đang chạy theo lifecycle và đóng consumer có trật tự.

Cần phối hợp:

- Termination grace period của nền tảng.
- Spring lifecycle shutdown timeout.
- Thời gian xử lý tối đa của listener.
- `max.poll.interval.ms` và heartbeat settings.
- AckMode/commit offset.
- Retry/backoff đang chạy.
- Database hoặc dependency mà listener cần trong lúc shutdown.

Nếu pod bị kill trước khi xử lý/commit hoàn tất, record có thể được đọc lại bởi member khác. Đây là lý do handler nên idempotent và thao tác nghiệp vụ phải an toàn khi retry.

Scale down quá nhanh có thể gây nhiều rebalance liên tiếp. Nên drain theo từng bước, dùng cooldown và theo dõi group membership trong quá trình rollout.

## 16. Static membership và group.instance.id

Kafka hỗ trợ static membership thông qua `group.instance.id`. Consumer có static identity ổn định có thể giảm một số rebalance không cần thiết khi tiến trình restart trong khoảng thời gian phù hợp.

Tuy nhiên:

- Mỗi member đồng thời trong cùng group phải có group.instance.id duy nhất.
- ID nên ổn định cho cùng một instance qua lần restart nếu muốn tận dụng static membership.
- Không dùng cùng một literal ID cho tất cả replica.
- ID trùng có thể khiến consumer cũ bị fencing hoặc group gặp lỗi membership.
- Static membership không thay thế health check, graceful shutdown hoặc xử lý lỗi.

Trong môi trường container, cần tạo ID dựa trên identity ổn định của replica/pod và cấu hình qua consumer properties. Không nên hard-code cùng một group.instance.id trong application.yml dùng chung cho mọi replica.

Static membership phù hợp khi instance có identity ổn định và việc restart ngắn hạn thường xuyên gây rebalance tốn kém. Với môi trường autoscaling thay đổi replica liên tục, cần cân nhắc lifecycle và identity strategy cẩn thận.

## 17. Những bottleneck không giải quyết được bằng thêm instance

Scale consumer chỉ giúp khi consumer capacity là bottleneck. Các giới hạn khác có thể khiến thêm instance không cải thiện throughput:

| Bottleneck | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Database connection pool | Nhiều consumer chờ connection, DB latency tăng | Tối ưu query/bulk write, connection pool và transaction. |
| HTTP downstream | Request timeout, rate limit, latency cao | Dùng bulk API, giới hạn concurrency, backoff hoặc queue riêng. |
| Hot partition | Một partition lag cao, partition khác ít lag | Xem key distribution và partition strategy. |
| CPU/GC | CPU cao, pause GC, xử lý chậm | Profile, tối ưu object allocation và payload. |
| Network/broker | Fetch latency cao, request queue hoặc network saturation | Kiểm tra broker, network, replication và client fetch. |
| Lock contention | Thread chờ lock, throughput không tăng | Giảm vùng critical section hoặc partition công việc. |
| Retry storm | Retry tăng, downstream tiếp tục quá tải | Phân loại lỗi, backoff, giới hạn retry và DLT. |

Nếu tăng replica làm database quá tải, lag có thể tăng nhanh hơn. Cần scale đồng bộ toàn bộ đường xử lý và có giới hạn concurrency bảo vệ downstream.

## 18. Idempotency và duplicate khi nhiều instance

Nhiều instance không có nghĩa mỗi event chỉ được xử lý đúng một lần ở mọi tình huống. Consumer có thể xử lý record rồi crash trước khi commit offset; sau rebalance, member khác đọc lại record đó.

Các nguyên tắc:

- Dùng event ID duy nhất để nhận diện event.
- Thiết kế database update có tính idempotent hoặc lưu processed event ID.
- Đặt transaction boundary phù hợp giữa xử lý nghiệp vụ và commit offset.
- Không commit trước khi tác vụ bền vững hoàn tất.
- Với Kafka-to-Kafka, cân nhắc Kafka transactions/EOS theo đúng phạm vi hỗ trợ.
- Với database và Kafka, xem xét transactional outbox/inbox hoặc cơ chế nhất quán tương ứng.

Idempotence ở producer bảo vệ một số trường hợp retry gửi record của cùng producer session; nó không thay thế idempotency ở consumer khi record được giao lại hoặc ứng dụng chủ động phát event trùng.

## 19. Kiểm thử scale nhiều instance

Nên kiểm thử bằng broker thật qua Testcontainers hoặc môi trường Kafka tích hợp, chạy nhiều consumer member trong cùng group.

Các kịch bản:

1. Chạy hai instance cùng group ID và xác nhận partition được chia giữa chúng.
2. Tăng số instance rồi quan sát rebalance và assignment.
3. Giảm một instance và xác nhận partition được giao lại.
4. Tạo nhiều consumer hơn số partition và xác nhận member dư không có assignment.
5. Chạy cùng service với group ID khác nhau để minh họa fan-out.
6. Kiểm tra offset tiếp tục từ committed offset sau khi member thay thế.
7. Gửi nhiều key và xác nhận ordering theo partition.
8. Giả lập xử lý chậm, retry và rebalance.
9. Kiểm tra graceful shutdown khi scale down.
10. Đo throughput, lag, listener latency, CPU, memory và database load.

Trong test, không nên chỉ xác nhận số process đang chạy. Cần kiểm tra assignment thực tế và số record được xử lý. Dùng event ID để phát hiện duplicate và sequence theo aggregate để kiểm tra ordering.

## 20. Quy trình scale khi consumer lag tăng

Khi lag tăng, hãy đi theo thứ tự:

1. Xác định group, topic và partition đang lag.
2. Kiểm tra group có đủ member và assignment không.
3. So sánh số consumer member với số partition.
4. Kiểm tra listener concurrency trên từng instance.
5. Đo throughput mỗi consumer và thời gian xử lý.
6. Xác định bottleneck nằm ở consumer, partition skew, broker hay downstream.
7. Nếu còn partition và tài nguyên, scale out từng bước.
8. Chờ rebalance và đo lại lag/throughput.
9. Nếu đã đạt partition limit, tối ưu xử lý hoặc đánh giá tăng partition.
10. Khi scale down, drain có kiểm soát và xác nhận offset/lag ổn định.

Không reset offset chỉ để đưa lag về zero. Reset có thể bỏ qua dữ liệu chưa xử lý hoặc khiến event được đọc lại; đây là thao tác cần đánh giá tác động nghiệp vụ.

## 21. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| Thêm pod luôn làm throughput tăng. | Consumer hữu ích bị giới hạn bởi partition và downstream capacity. |
| Mỗi pod nên có group ID riêng. | Muốn chia tải thì các replica phải dùng cùng group ID. |
| Cùng group ID nghĩa mỗi pod nhận mọi record. | Các member chia nhau partition; mỗi group có tiến độ riêng. |
| Concurrency là số partition. | Concurrency là số consumer container tạo trên mỗi instance; partition là nguồn công việc được phân phối. |
| Consumer dư vẫn xử lý song song cùng partition. | Một partition chỉ được gán cho tối đa một member trong group tại một thời điểm. |
| Scale up không gây gián đoạn. | Membership thay đổi có thể kích hoạt rebalance và tạm giảm throughput. |
| Thêm partition luôn giải quyết hot key. | Cùng một key vẫn có thể dồn vào một partition. |
| CPU thấp nghĩa consumer còn dư capacity. | Consumer có thể bị chặn bởi I/O hoặc downstream trong khi CPU thấp. |
| Static membership cho phép dùng cùng ID trên mọi pod. | Mỗi member đồng thời cần group.instance.id duy nhất. |
| Scale down không ảnh hưởng xử lý đang chạy. | Pod bị dừng có thể gây redelivery nếu record chưa commit. |

## 22. Checklist thiết kế scale nhiều instance

Trước khi triển khai production, hãy xác nhận:

1. Các replica cần chia tải có cùng group ID.
2. Các service cần nhận bản sao độc lập dùng group ID riêng.
3. Tổng consumer member được tính từ replica nhân concurrency.
4. Số partition đủ cho mức song song hữu ích.
5. Assignment strategy phù hợp với số topic/partition và phiên bản client.
6. Mỗi consumer có client identity quan sát được.
7. group.instance.id, nếu dùng, là duy nhất và ổn định theo từng member.
8. Ordering theo key được giữ qua producer, consumer và retry.
9. Downstream có đủ connection/capacity cho tổng concurrency.
10. Autoscaler dựa trên lag/throughput và có cooldown.
11. Rebalance và graceful shutdown được theo dõi.
12. Idempotency xử lý được duplicate sau crash/rebalance.
13. Integration test xác nhận partition assignment và failover.
14. Có runbook scale up/down và điều tra lag.

Scale nhiều instance giúp Spring Kafka tăng khả năng xử lý và khả năng phục hồi bằng cách phân phối partition giữa các consumer member trong cùng group. Hiệu quả phụ thuộc vào group ID, concurrency mỗi instance, số partition, assignment strategy và năng lực downstream. Khi quy hoạch các yếu tố này cùng với ordering, rebalance, offset và idempotency, ứng dụng có thể mở rộng có kiểm soát mà không tạo thêm tải vô ích hoặc làm sai semantics xử lý event.

