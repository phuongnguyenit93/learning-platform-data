# Số luồng xử lý, task, standby replica và phạm vi mở rộng

Kafka Streams xử lý dữ liệu song song bằng cách chia topology thành các **task** gắn với partition của topic đầu vào, rồi thực thi các task trên **stream thread** của từng Kafka Streams instance. Trong Spring Cloud Stream Kafka Streams Binder, số thread trên mỗi instance có thể cấu hình bằng `num.stream.threads`. Với topology có state store, Kafka Streams còn hỗ trợ **standby task replica** để duy trì bản sao state trên instance khác; số bản sao dự phòng được cấu hình bằng `num.standby.replicas`.

Ba con số cần phân biệt là số partition của topic, số stream thread trên mỗi instance và số instance ứng dụng. Partition quyết định mức song song tối đa của topology; thread cung cấp năng lực thực thi trong một tiến trình; instance bổ sung tài nguyên máy và khả năng phân tán task. Standby replica tăng khả năng phục hồi state khi instance lỗi, nhưng không tăng số task active đang xử lý input.

Bài thuộc chương **Vận hành Kafka Streams** của module `SPRING_CLOUD_STREAM`. Nội dung tập trung vào functional topology, Kafka Streams task/thread model, state store, changelog, `num.stream.threads`, `num.standby.replicas`, mở rộng ngang/dọc, giới hạn partition, phục hồi và giám sát production.

## 1. Phân biệt partition, task, thread và instance

Các khái niệm này liên quan trực tiếp nhưng không thay thế cho nhau:

| Thành phần | Vai trò | Phạm vi |
|---|---|---|
| Topic partition | Phân đoạn dữ liệu có thứ tự trong Kafka topic | Broker/topic |
| Kafka Streams task | Đơn vị xử lý topology được gắn với partition đầu vào của một subtopology | Topology/application |
| Stream thread | Luồng thực thi các task được Kafka Streams giao cho nó | Một Kafka Streams instance |
| Kafka Streams instance | Một tiến trình/client Kafka Streams tham gia cùng application ID | Một replica ứng dụng |
| Standby task | Bản sao state của một task, được cập nhật từ changelog để có thể tiếp quản | Một instance khác với active task |

```text
Kafka topic: orders.events (6 partitions)
       |
       v
Topology: aggregateOrders
       |
       +--> Task 0 ----+
       +--> Task 1     |
       +--> Task 2     +--> Stream threads trên các instance
       +--> Task 3     |
       +--> Task 4     |
       +--> Task 5 ----+
```

Một task có thể được thực thi trên một stream thread tại một thời điểm. Một stream thread có thể xử lý nhiều task theo lịch của Kafka Streams. Vì vậy, sáu task không bắt buộc cần sáu thread; ba thread có thể xử lý sáu task, mỗi thread phụ trách nhiều task. Ngược lại, tạo nhiều thread hơn số task active có thể khiến một số thread không có task để chạy.

Task cũng không phải một thread Java được tạo thủ công trong code function. Kafka Streams quản lý việc tạo task, gán task cho instance/thread, tạm dừng và chuyển task khi rebalance.

## 2. Task được tạo từ partition của input topic

Kafka Streams chia topology thành các subtopology. Với một subtopology nguồn đơn giản, mỗi partition của input topic tạo ra một task tương ứng. Task đọc partition đó và chạy các processor trong subtopology.

Ví dụ topic có sáu partition:

```text
orders.events
  P0  P1  P2  P3  P4  P5
   |   |   |   |   |   |
   v   v   v   v   v   v
  T0  T1  T2  T3  T4  T5
```

Trong ví dụ này có sáu task cho subtopology. Số task thực tế của topology phức tạp còn phụ thuộc cấu trúc subtopology, số partition của các input topic và các repartition topic do thao tác đổi key, join hoặc group tạo ra.

Khi topology kết hợp nhiều input topic, các topic tham gia join hoặc co-partitioned operation cần có partition count và partitioning strategy tương thích. Một task có thể đọc các partition tương ứng từ nhiều topic. Không cộng đơn giản số partition của mọi input topic để suy ra tổng task của topology.

Với một topology có nhiều subtopology, mỗi subtopology có tập task riêng. Repartition topic có thể tạo ranh giới mới và làm thay đổi số task ở phần topology phía sau. Hãy xem topology description và thông tin task thực tế khi lập kế hoạch năng lực.

## 3. Partition đặt giới hạn cho mức song song

Đối với một subtopology, số partition của các input/repartition topic là yếu tố quyết định số task có thể chạy song song. Tăng số replica hoặc số stream thread không thể tạo thêm partition task mới nếu topology không có thêm partition.

Ví dụ:

| Số partition đầu vào | Số instance | Stream thread/instance | Tổng thread | Nhận xét |
|---:|---:|---:|---:|---|
| 4 | 1 | 4 | 4 | Có tối đa 4 task active; có thể dùng hết 4 thread |
| 4 | 2 | 2 | 4 | Có thể chia 4 task active cho 2 instance |
| 4 | 4 | 2 | 8 | Chỉ có 4 task active; có thread/instance có thể không nhận task |
| 12 | 3 | 2 | 6 | Có thể chạy tối đa 6 task đồng thời trên 6 thread đang có; còn task chờ lịch thực thi |
| 12 | 6 | 2 | 12 | Có đủ 12 thread để chạy 12 task active nếu tài nguyên và assignment phù hợp |

Các dòng là mô hình năng lực minh họa; phân phối task thực tế phụ thuộc topology, Kafka Streams assignment, số instance đang sống và tài nguyên của từng máy.

Nếu cần throughput cao hơn nhưng số partition quá ít, cần xem lại thiết kế topic/partition, key distribution và khả năng co-partitioning. Không nên chỉ tăng replica rồi kỳ vọng throughput tăng tuyến tính.

## 4. Stream thread làm gì?

Stream thread là luồng xử lý do Kafka Streams quản lý. Nó poll record từ các partition được giao, đưa record qua processor topology, cập nhật state store, xử lý punctuation và tham gia commit/transaction theo cấu hình.

Một Kafka Streams instance có thể chạy nhiều stream thread. Thuộc tính `num.stream.threads` đặt số thread xử lý trong mỗi instance. Giá trị mặc định của Kafka Streams là một stream thread nếu không cấu hình khác.

Ví dụ một instance chạy hai stream thread:

```text
Kafka Streams instance A
  applicationId = order-aggregator-v1
  num.stream.threads = 2

  StreamThread-1: Task 0, Task 2, Task 4
  StreamThread-2: Task 1, Task 3, Task 5
```

Danh sách task trong sơ đồ chỉ minh họa; Kafka Streams quyết định assignment thực tế. Một thread có thể xử lý nhiều task và luân phiên giữa chúng.

Tăng `num.stream.threads` có thể tận dụng thêm CPU trong cùng một tiến trình nếu có đủ task và tài nguyên. Nhưng tăng thread cũng làm tăng số luồng cạnh tranh CPU, context switching, bộ nhớ, kết nối và hoạt động state store. Không đặt số thread lớn chỉ vì máy có nhiều core; cần đo CPU, latency, throughput và task assignment.

## 5. Cấu hình `num.stream.threads` trong Kafka Streams Binder

Kafka Streams Binder truyền các thuộc tính Kafka Streams client thông qua nhánh `configuration` của binder. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
```

`num.stream.threads: 2` có nghĩa mỗi Kafka Streams instance tạo hai stream thread. Nếu ứng dụng chạy ba replica, tổng số stream thread được cấu hình là sáu.

Đây là thuộc tính Kafka Streams, không phải `spring.cloud.stream.bindings.<binding>.consumer.concurrency` của Kafka Binder thông thường. Không nhầm concurrency của listener container trong Kafka Binder thường với số stream thread của Kafka Streams.

Đặt cấu hình ở namespace Kafka Streams Binder. Nếu một ứng dụng dùng cả Kafka Binder thông thường và Kafka Streams Binder, cần xác định đúng binder đang phục vụ binding; cùng một thuộc tính tên gần giống có thể có phạm vi và semantics khác nhau.

## 6. Mở rộng dọc bằng stream thread

Mở rộng dọc là tăng tài nguyên của một instance, ví dụ CPU và RAM, rồi tăng `num.stream.threads` khi topology có đủ task để tận dụng.

Ưu điểm:

- Không cần tăng số pod/VM.
- Có thể tận dụng nhiều core trên một máy.
- Ít instance hơn để quản lý và có thể giảm overhead kết nối/coordination.
- Hữu ích khi số partition vừa phải và workload cần nhiều CPU trong một tiến trình.

Giới hạn:

- Một instance vẫn là một miền lỗi; khi máy hoặc process dừng, toàn bộ active task trên instance cần được gán lại.
- Số task active vẫn bị giới hạn bởi partition/subtopology.
- Thêm thread không làm tăng số partition hoặc giải quyết hot partition.
- Một tiến trình lớn có thể cần nhiều RAM, file descriptor và local disk hơn.

Mở rộng dọc phù hợp khi đo đạc cho thấy CPU là nút thắt, số task đủ lớn và máy còn khả năng cấp tài nguyên. Nếu bottleneck nằm ở network, broker, database hoặc một key nóng, thêm stream thread có thể không giúp.

## 7. Mở rộng ngang bằng application replica

Mở rộng ngang là chạy nhiều instance ứng dụng cùng tham gia một Kafka Streams application. Các instance phải dùng chung `applicationId` để Kafka Streams phối hợp task assignment.

Ví dụ triển khai ba replica:

```text
Deployment: order-aggregator
applicationId: order-aggregator-v1

Replica A: 2 stream threads
Replica B: 2 stream threads
Replica C: 2 stream threads
```

Với sáu partition/task, sáu stream thread trên ba replica có thể cung cấp sáu slot xử lý active. Khi scale thêm replica, Kafka Streams rebalance task giữa các instance. Nếu số task không tăng, instance bổ sung có thể không có active task.

Tất cả replica của cùng topology phải dùng cùng application ID và cùng topology/configuration tương thích. Không thêm pod ID hoặc replica ordinal vào application ID; làm như vậy tạo các application độc lập thay vì chia tải cùng một consumer group.

## 8. Kết hợp số instance và số thread

Tổng số stream thread được cấu hình có thể tính đơn giản:

\[
T_{configured} = N_{instances} \times T_{per-instance}
\]

Trong đó:

- (N_{instances}) là số Kafka Streams instance đang chạy.
- (T_{per-instance}) là `num.stream.threads` trên mỗi instance.

Ví dụ bốn replica, mỗi replica có ba stream thread, tạo tổng cộng mười hai stream thread. Điều này không có nghĩa topology luôn chạy mười hai task song song. Số task active khả dụng vẫn phụ thuộc partition của các subtopology và assignment.

Khi task ít hơn thread, một số thread không có task. Khi task nhiều hơn thread, một thread có thể quản lý nhiều task. Cần đánh giá cả số task, số thread, CPU và trạng thái thread để xác định cấu hình hiệu quả.

## 9. Standby task replica là gì?

Topology stateful có thể duy trì state store cục bộ. Khi instance đang sở hữu active task bị lỗi, instance khác cần khôi phục state từ changelog topic trước khi xử lý tiếp. Quá trình restore có thể mất thời gian nếu state lớn hoặc changelog backlog cao.

Kafka Streams hỗ trợ standby task: một instance khác duy trì bản sao state của task thông qua việc đọc changelog topic. Standby task không xử lý input record như active task; nó cập nhật state để sẵn sàng được promote khi active task thất bại hoặc assignment thay đổi.

```text
Input partitions
      |
      v
Active task trên Replica A
      |
      +---- cập nhật state store
      |
      +---- ghi changelog topic
                    |
                    v
           Standby task trên Replica B
           cập nhật bản sao state

Khi Replica A lỗi:
  Replica B có thể nhận active task và tiếp tục sau rebalance/promotion.
```

Standby task giảm lượng state cần restore từ đầu khi failover. Nó không loại bỏ hoàn toàn rebalance, catch-up hoặc các bước phục hồi khác. Mức giảm thời gian phụ thuộc độ mới của standby state, tốc độ changelog, assignment và khả năng của instance nhận task.

## 10. Cấu hình `num.standby.replicas`

`num.standby.replicas` xác định số bản sao standby mong muốn cho mỗi stateful task. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
              num.standby.replicas: 1
```

Với `num.standby.replicas: 1`, Kafka Streams cố gắng duy trì một standby copy cho mỗi task stateful. Giá trị này không có nghĩa một task có hai active consumer hoặc throughput tăng gấp đôi.

Standby replica được phân bổ trên các Kafka Streams instance khác với instance đang chạy active task. Để có một standby độc lập, cần ít nhất một instance khác có thể nhận standby task. Để có hai standby copy trên các instance khác nhau, cần đủ instance khác nhau và tài nguyên phù hợp. Một process có nhiều stream thread không thay thế nhiều instance độc lập cho mục đích chịu lỗi process/host.

Khả năng phân bổ standby còn phụ thuộc số instance đang hoạt động, task assignment và cấu trúc topology. Nếu không đủ instance, Kafka Streams không thể đạt đủ số standby như mong muốn.

## 11. Standby replica chỉ hữu ích cho stateful processing

Standby task có ý nghĩa khi topology có state cần duy trì, chẳng hạn:

- `KTable` và materialized view.
- Aggregation như count, sum hoặc reduce.
- Windowed aggregation.
- Join cần state store.
- Processor API dùng state store.

Một topology stateless chỉ filter/map record và không có state store cần phục hồi thường không hưởng lợi đáng kể từ standby replica. Đặt `num.standby.replicas` lớn cho workload không có state không làm tăng throughput.

State store cần có changelogging phù hợp để Kafka Streams tái tạo state. Nếu tắt logging cho store, cần đánh giá lại khả năng restore và standby; không giả định standby state được duy trì như một store có changelog.

## 12. Active task và standby task không chia tải input

Active task đọc input partition và chạy topology. Standby task duy trì state từ changelog nhưng không nhận input partition để thực hiện cùng nghiệp vụ như một active copy.

| Tiêu chí | Active task | Standby task |
|---|---|---|
| Đọc input partition | Có | Không theo vai trò standby |
| Thực thi processor topology | Có | Không xử lý input nghiệp vụ như active task |
| Cập nhật state | Có | Cập nhật bản sao từ changelog |
| Ghi output nghiệp vụ | Có thể | Không |
| Mục tiêu | Xử lý dữ liệu | Rút ngắn phục hồi khi active task mất |
| Tác động throughput | Tạo throughput xử lý | Tăng khả năng sẵn sàng, không tăng active throughput |

Vì vậy, nếu ứng dụng chậm do thiếu năng lực xử lý, hãy xem xét partition, active task, stream thread, CPU và downstream latency. Thêm standby replica không phải cách tăng throughput.

## 13. Điều kiện để standby hoạt động hiệu quả

Để standby có thể giúp phục hồi state:

- Topology phải có state store cần phục hồi.
- State store phải có changelog phù hợp và changelog topic phải được duy trì.
- Các instance cần có kết nối Kafka và quyền đọc changelog/internal topics.
- Standby task phải được gán lên instance khác với active task.
- Instance standby cần đủ RAM, CPU, local disk và network để duy trì state.
- Changelog phải được cập nhật đủ nhanh để standby không quá lạc hậu.
- Cấu hình application ID và topology phải ổn định giữa các replica.

Standby state có thể còn lag so với active state. Khi được promote, instance nhận task có thể cần catch up thêm từ changelog trước khi xử lý bình thường. Hãy theo dõi lag/restore metrics thay vì giả định standby luôn đồng bộ tức thời.

## 14. Changelog topic và local state store

Kafka Streams state store thường được lưu cục bộ trên instance để truy cập nhanh. Changelog topic ghi lại các thay đổi state để phục hồi hoặc tái tạo state trên instance khác.

```text
Active processor
      |
      +--> Local state store (RocksDB/in-memory)
      |
      +--> Changelog topic trên Kafka
                    |
                    +--> Standby state store trên Replica B
                    |
                    +--> Restore state khi instance mới nhận task
```

Local state store là bản phục vụ xử lý nhanh; changelog topic là nguồn bền vững để phục hồi theo cơ chế Kafka Streams. Không tự xóa changelog topic hoặc đổi application ID tùy tiện khi còn cần state hiện có.

Quyền Kafka của ứng dụng cần bao gồm các internal topic phù hợp: đọc input, ghi output, consumer group và read/write/create changelog hoặc repartition topic theo chính sách cluster. Thiếu ACL cho changelog có thể làm standby không cập nhật hoặc state restore thất bại.

## 15. Cấu hình local state directory

Kafka Streams dùng `state.dir` để lưu state cục bộ. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              state.dir: /var/lib/order-stream/state
              num.stream.threads: 2
              num.standby.replicas: 1
```

Trong môi trường container, thư mục phải tồn tại hoặc có thể được tạo, có quyền ghi và đủ dung lượng. Mỗi instance cần một state directory riêng; không cho nhiều replica cùng ghi vào một thư mục dùng chung trên network volume.

Có thể dùng local disk hoặc volume riêng theo chiến lược vận hành. Dữ liệu local giúp restart cùng instance nhanh hơn nếu còn hợp lệ, nhưng khả năng phục hồi giữa instance vẫn dựa trên Kafka changelog và cơ chế Kafka Streams. Không xem volume local là bản sao thay thế changelog topic.

## 16. Ví dụ sizing với sáu partition

Giả sử topology aggregate đơn hàng đọc topic `orders.events` có sáu partition và cần một standby replica cho mỗi task.

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
              num.standby.replicas: 1
              state.dir: /var/lib/order-stream/state
```

Deployment chạy ba replica với cùng cấu hình và cùng `applicationId`:

| Replica | Stream thread | Vai trò minh họa |
|---|---:|---|
| A | 2 | Một số active task và standby task của task khác |
| B | 2 | Một số active task và standby task của task khác |
| C | 2 | Một số active task và standby task của task khác |

Sáu partition tạo tối đa sáu active task cho subtopology đơn giản này. Sáu stream thread có thể xử lý sáu task active nếu assignment và tài nguyên phù hợp. Một standby replica cho mỗi task cần các bản sao state được phân bổ trên instance khác; phân bổ cụ thể do Kafka Streams quyết định.

Nếu chỉ chạy một replica với hai stream thread, ứng dụng vẫn có thể xử lý các task active nhưng không có instance khác để duy trì standby độc lập. Tăng `num.standby.replicas` trong khi chỉ có một instance không tạo ra khả năng failover giữa các process.

## 17. Ví dụ mở rộng ngang và standby

Giả sử ban đầu chạy hai replica, mỗi replica có hai stream thread. Sau khi đo tải, nhóm vận hành tăng lên bốn replica nhưng giữ nguyên application ID:

```text
Trước:
  Replica A: 2 threads
  Replica B: 2 threads

Sau:
  Replica A: 2 threads
  Replica B: 2 threads
  Replica C: 2 threads
  Replica D: 2 threads

Tất cả cùng applicationId = order-aggregator-v1
```

Kafka Streams rebalance các task active và standby giữa các instance. Khi có thêm instance, task có thể được phân bố tốt hơn và standby có thể được đặt trên các failure domain khác. Tuy nhiên, nếu topic chỉ có hai partition, topology không có bốn active task để tận dụng tám stream thread.

Khi tăng replica, cần bảo đảm các instance chạy cùng phiên bản topology và cấu hình tương thích. Rolling deployment có thể tạm thời làm tăng rebalance; hãy đặt readiness/liveness và shutdown grace period phù hợp để giảm gián đoạn.

## 18. Chọn số stream thread như thế nào?

Không có một giá trị đúng cho mọi workload. Có thể bắt đầu bằng một hoặc hai thread mỗi instance, sau đó đo:

- Số task active được giao cho mỗi instance.
- Throughput records/second và processing latency.
- CPU utilization và garbage collection.
- Thời gian xử lý record và mức độ blocking trong user code.
- RocksDB/state store I/O và disk latency.
- Network throughput và changelog write/read.
- Stream thread state và số lần thread chuyển sang trạng thái lỗi.

Nếu mỗi thread có ít task hoặc topic chỉ có ít partition, tăng thread có thể không tạo thêm throughput. Nếu handler thực hiện I/O blocking, cần xem xét thiết kế xử lý và giới hạn của Kafka Streams; không mặc định tăng thread là giải pháp thay cho việc bỏ blocking call khỏi topology.

Nên benchmark với payload, key distribution, state store và broker tương tự production. Dùng dữ liệu đại diện để phát hiện hot key, partition skew và state restore cost.

## 19. Chọn số standby replica như thế nào?

Giá trị `num.standby.replicas` là quyết định về khả năng phục hồi và chi phí tài nguyên:

| Giá trị | Ý nghĩa | Đánh đổi |
|---:|---|---|
| 0 | Không duy trì standby task | Ít tài nguyên hơn; failover cần restore state từ changelog |
| 1 | Một bản sao standby cho mỗi stateful task | Tăng khả năng tiếp quản nhanh khi một instance lỗi; tăng disk/network/CPU |
| 2 | Hai bản sao standby cho mỗi stateful task | Chịu được nhiều instance lỗi hơn trong điều kiện assignment phù hợp; chi phí cao hơn |

Không đặt standby replicas lớn hơn nhu cầu chịu lỗi. Mỗi bản sao cần duy trì state, đọc changelog và dùng local disk. Nếu state store lớn, chi phí standby có thể đáng kể.

Để duy trì một standby trên instance khác, cần ít nhất hai Kafka Streams instance tham gia cùng application. Để có hai standby copy trên hai instance khác nhau, cần ít nhất ba instance phù hợp. Đây là điều kiện cần về số instance; việc phân bổ thành công còn phụ thuộc assignment và các ràng buộc topology.

## 20. Standby không thay thế replication của Kafka broker

Standby task và Kafka broker replication bảo vệ hai lớp khác nhau:

| Cơ chế | Bảo vệ điều gì? | Phạm vi |
|---|---|---|
| Kafka topic replication | Bản sao log/record trên các broker | Hạ tầng Kafka |
| Kafka Streams standby task | Bản sao state store trên instance ứng dụng khác | Tầng xử lý stream |
| Local state store | Trạng thái làm việc cục bộ của một instance | Một máy/volume |

Standby task đọc changelog topic; nếu broker/changelog mất dữ liệu, standby cũng không thể tự tạo lại dữ liệu đã mất. Ngược lại, broker replication không tự giữ một state store đã được materialize và sẵn sàng xử lý trên instance ứng dụng khác.

Production cần cả replication/ISR phù hợp cho Kafka topic và standby strategy phù hợp cho stateful application. Cần bảo vệ input topic, output topic và internal changelog/repartition topics theo mức độ quan trọng của dữ liệu.

## 21. Rebalance khi scale hoặc instance lỗi

Khi instance tham gia/rời application, Kafka Streams phối hợp lại task assignment. Quá trình này có thể làm task tạm dừng, chuyển active/standby role và restore state nếu instance nhận task chưa có state mới nhất.

Các tình huống thường gặp:

- Scale up: instance mới tham gia, task được phân phối lại; standby assignment có thể thay đổi.
- Scale down: task trên instance bị dừng được chuyển cho instance còn lại; state có thể cần catch up.
- Process crash: task được gán lại sau khi membership/session timeout và rebalance.
- Rolling deploy: nhiều instance lần lượt restart; cấu hình shutdown và grace period ảnh hưởng mức gián đoạn.
- Network partition: instance có thể bị xem là mất kết nối; cần theo dõi rebalance và task promotion.

Standby state có thể giảm thời gian restore nhưng không loại bỏ thời gian phát hiện lỗi, rebalance và promotion. Hãy đo recovery time objective thực tế bằng thử nghiệm dừng process/instance.

## 22. Failure domain và vị trí standby

Nếu active và standby cùng nằm trên một host hoặc cùng failure domain, một sự cố host có thể làm mất cả hai bản. Khi hạ tầng hỗ trợ, phân tán replica qua node, zone hoặc rack khác nhau để tăng khả năng chịu lỗi.

Không chỉ nhìn số replica. Cần xem:

- Pod có bị đặt chung node không?
- Node có nằm cùng availability zone không?
- Persistent volume có cùng failure domain không?
- Kafka broker/changelog replica có phân tán tương ứng không?
- Network path giữa standby và Kafka có độc lập không?

Kafka Streams assignment và cơ chế rack awareness phụ thuộc phiên bản Kafka/client và cấu hình triển khai. Không khẳng định standby đã được đặt khác zone chỉ vì `num.standby.replicas` lớn hơn 0; hãy kiểm tra placement thực tế của ứng dụng.

## 23. Partition skew và hot key

Tăng task/thread/instance không giải quyết được trường hợp một partition nhận phần lớn traffic. Nếu partition key phân bố lệch, một task có thể nóng trong khi task khác nhàn rỗi.

Ví dụ:

| Partition | Tỷ lệ traffic minh họa | Hệ quả |
|---|---:|---|
| P0 | 55% | Task P0 có thể trở thành nút thắt |
| P1 | 10% | Tải thấp |
| P2 | 9% | Tải thấp |
| P3 | 9% | Tải thấp |
| P4 | 9% | Tải thấp |
| P5 | 8% | Tải thấp |

Hãy kiểm tra partition-level bytes/records, key distribution và processing latency. Có thể cần chọn lại key, tách hot key theo chiến lược nghiệp vụ hoặc thay đổi topology. Việc đổi partition key cần cân nhắc thứ tự và state migration.

## 24. Thay đổi partition count có tác động vận hành

Tăng partition có thể tạo thêm task và mức song song cho topology đọc topic đó. Tuy nhiên, thay đổi partition count cũng có thể làm thay đổi phép ánh xạ key sang partition đối với partitioner thông thường. Các message cùng key trước và sau thay đổi có thể nằm ở partition khác nhau tùy cách tính partition.

Với stateful topology, thay đổi partition count cần xem xét:

- Co-partitioning giữa các topic tham gia join.
- Số task và phân bố task mới.
- Repartition topic nội bộ.
- State store và changelog partitioning.
- Thứ tự xử lý theo key trong giai đoạn chuyển tiếp.
- Khả năng backfill/rebuild state.

Không tăng partition tùy tiện chỉ để có thêm task. Hãy kiểm thử topology và kế hoạch migration với dữ liệu đại diện.

## 25. Các thuộc tính cấu hình quan trọng

| Thuộc tính | Phạm vi | Tác dụng |
|---|---|---|
| `applicationId` | Kafka Streams Binder | Danh tính chung của topology và các replica |
| `num.stream.threads` | Kafka Streams client | Số stream thread trên mỗi instance |
| `num.standby.replicas` | Kafka Streams client | Số standby task replica mong muốn cho mỗi task stateful |
| `state.dir` | Kafka Streams client | Thư mục lưu state cục bộ |
| `commit.interval.ms` | Kafka Streams client | Chu kỳ commit/flush theo semantics Kafka Streams và processing mode |
| `cache.max.bytes.buffering` hoặc cấu hình cache tương ứng theo phiên bản | Kafka Streams client | Dung lượng cache record/state để tối ưu xử lý |

Các property được hỗ trợ và tên property có thể thay đổi theo phiên bản Kafka Streams. Dùng đúng release train Spring Cloud Stream và Kafka client của dự án. Với ví dụ trong bài, các property chính là `num.stream.threads`, `num.standby.replicas` và `state.dir`.

## 26. Ví dụ cấu hình theo môi trường

Có thể quản lý thread, standby và state directory qua biến môi trường:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: ${ORDERS_TOPIC:orders.events}
      kafka:
        streams:
          binder:
            applicationId: ${STREAMS_APPLICATION_ID:order-aggregator-dev}
            configuration:
              num.stream.threads: ${STREAMS_THREADS:2}
              num.standby.replicas: ${STREAMS_STANDBY_REPLICAS:1}
              state.dir: ${STREAMS_STATE_DIR:/var/lib/order-stream/state}
```

Ví dụ giá trị triển khai:

| Môi trường | Replica | Threads/instance | Standby/task | Mục tiêu |
|---|---:|---:|---:|---|
| Local | 1 | 1 | 0 | Đơn giản để phát triển |
| Test tích hợp | 2 | 1 | 1 | Kiểm tra failover và standby |
| Staging | 3 | 2 | 1 | Đo throughput và phục hồi |
| Production | Theo benchmark | Theo benchmark | Theo RTO/RPO | Cân bằng năng lực và độ sẵn sàng |

Đây là giá trị minh họa; production sizing phải dựa trên partition count, kích thước state, traffic, CPU, disk, network và mục tiêu phục hồi.

## 27. Theo dõi trạng thái thread và task

Trong production, cần quan sát cả năng lực xử lý và khả năng phục hồi:

- Số active task và standby task trên mỗi instance.
- Số stream thread và trạng thái thread.
- Records/second, bytes/second và processing latency.
- Consumer lag theo partition.
- Thời gian rebalance và task migration.
- State restore duration, restore rate và changelog lag.
- Local state store size, RocksDB disk usage và I/O latency.
- CPU, heap, garbage collection và network throughput.
- Lỗi task, serialization và commit/transaction.

Nếu active task không đủ, kiểm tra partition count và topology. Nếu task đủ nhưng CPU thấp, xem thread assignment và bottleneck downstream. Nếu restore chậm, kiểm tra standby lag, changelog throughput, local disk và kích thước state.

Không chỉ theo dõi tổng throughput toàn ứng dụng. Một partition nóng hoặc một task restore chậm có thể bị che khuất bởi số liệu tổng hợp.

## 28. Kiểm thử mở rộng và phục hồi

Một bộ kiểm thử vận hành nên bao gồm:

| Kịch bản | Thực hiện | Kết quả cần xác minh |
|---|---|---|
| Một instance, nhiều thread | Đặt `num.stream.threads` lớn hơn 1 | Nhiều thread chạy task khi đủ partition |
| Nhiều instance cùng ID | Chạy nhiều replica với cùng application ID | Task được phân phối giữa instance |
| Replica khác ID | Cố ý đổi ID của một replica | Phát hiện chúng trở thành application độc lập |
| Partition ít hơn thread | Tạo topic ít partition | Thread dư không tạo thêm task active |
| Standby bằng 0 | `num.standby.replicas: 0` | Failover phải restore state từ changelog theo cơ chế Kafka Streams |
| Standby bằng 1 | Chạy ít nhất hai instance | Xác minh standby task được duy trì trên instance khác |
| Dừng active instance | Kill process đang sở hữu active task | Standby có thể được promote; đo recovery time |
| Dừng node chứa standby | Mất failure domain chứa bản standby | Xác minh task được restore/assignment lại |
| Changelog lag | Tạo tải cao hoặc hạn chế network | Đo độ trễ cập nhật standby và catch-up |
| Scale up/down | Thay số replica | Đo rebalance, task movement và throughput |
| State lớn | Tăng kích thước state store | Đo restore duration, disk và network |
| Partition skew | Tạo hot key | Xác định task/partition bottleneck |

`TopologyTestDriver` phù hợp để kiểm tra logic topology. Nó không thay thế integration/load test khi cần kiểm tra thread assignment, standby replica, rebalance và state restoration. Các kiểm thử này cần Kafka broker và nhiều Kafka Streams instance thật hoặc môi trường test tương đương.

## 29. Các lỗi sizing thường gặp

| Lựa chọn sai | Hệ quả | Cách xử lý |
|---|---|---|
| Tăng thread khi partition quá ít | Thread dư nhưng throughput không tăng | Đánh giá partition và topology trước |
| Tăng replica nhưng application ID khác nhau | Các ứng dụng đọc độc lập, có thể tạo output trùng | Dùng chung application ID cho cùng topology |
| Đặt standby nhưng chỉ chạy một instance | Không có instance khác để giữ standby độc lập | Triển khai thêm replica |
| Đặt standby quá cao | Tốn disk, network, CPU và thời gian cập nhật state | Chọn số standby theo mục tiêu phục hồi |
| Nhầm standby với active replica | Kỳ vọng throughput tăng nhưng không xảy ra | Phân biệt state copy với xử lý input |
| Không cấp ACL internal topic | Standby/restore không đọc hoặc ghi changelog được | Cấp ACL đúng cho internal topics |
| Chia sẻ `state.dir` giữa replica | Xung đột state cục bộ | Dùng thư mục riêng theo instance |
| Đặt mọi replica cùng node | Một sự cố node làm mất nhiều bản state | Phân tán qua failure domain |
| Bỏ qua hot partition | Một task quá tải dù tổng CPU còn dư | Phân tích key và partition-level metrics |
| Tăng partition thiếu kế hoạch | Thay đổi key mapping/co-partitioning/state | Migration và kiểm thử topology |

## 30. Quy trình sizing và triển khai

1. Đo records/second, payload size, state size và latency mục tiêu.
2. Xác định số partition của từng input topic và các subtopology/repartition topic.
3. Ước lượng số task active có thể được tạo.
4. Chọn số instance và `num.stream.threads` theo CPU, task và throughput benchmark.
5. Giữ một `applicationId` ổn định chung cho tất cả replica của topology.
6. Xác định topology có state store cần standby hay không.
7. Chọn `num.standby.replicas` theo RTO, số instance và chi phí state replication.
8. Bảo đảm standby nằm trên instance/failure domain khác nếu yêu cầu chịu lỗi.
9. Cấp ACL và retention phù hợp cho input/output/internal changelog topics.
10. Cấp local state directory riêng, đủ dung lượng và quyền ghi cho từng instance.
11. Kiểm thử scale, rebalance, failover, standby promotion và state restore.
12. Theo dõi task/thread state, lag, restore time, CPU, disk và network trong production.

## 31. Tự kiểm tra

- [ ] Phân biệt topic partition, Kafka Streams task, stream thread và application instance.
- [ ] Giải thích được task được tạo từ partition và subtopology như thế nào.
- [ ] Biết số partition giới hạn mức song song của topology.
- [ ] Cấu hình được `num.stream.threads` trong Kafka Streams Binder.
- [ ] Phân biệt mở rộng dọc bằng thread với mở rộng ngang bằng replica.
- [ ] Biết các replica của cùng topology phải dùng chung `applicationId`.
- [ ] Giải thích được standby task và vai trò của changelog topic.
- [ ] Cấu hình được `num.standby.replicas`.
- [ ] Hiểu standby không xử lý input như active task và không tăng active throughput.
- [ ] Biết cần nhiều instance độc lập để có standby failover thực sự.
- [ ] Phân biệt standby task với replication của Kafka broker.
- [ ] Đánh giá được ảnh hưởng của partition skew, state size và failure domain.
- [ ] Thiết kế được test scale, rebalance, failover và state restoration.

## Kết luận

Kafka Streams tạo task từ partition của các input/subtopology và thực thi task trên stream thread của từng instance. `num.stream.threads` điều chỉnh số thread trong mỗi instance; số replica mở rộng ngang năng lực và phân tán failure domain, nhưng cả hai đều bị giới hạn bởi số task active mà partition tạo ra. Với topology stateful, `num.standby.replicas` duy trì bản sao state từ changelog trên instance khác để giảm thời gian phục hồi khi active instance lỗi. Standby không xử lý input thay active và không làm tăng throughput. Sizing production cần cân bằng partition, task, thread, instance, state size, changelog, CPU, disk, network và mục tiêu phục hồi; sau đó xác minh bằng integration/load test và metrics thực tế.
