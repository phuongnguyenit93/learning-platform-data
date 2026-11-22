# Nhiều instance cùng một group

Trong Kafka, nhiều consumer instance có thể cùng tham gia một consumer group để chia nhau xử lý dữ liệu của một topic. Đây là cách phổ biến để mở rộng một ứng dụng Spring Kafka theo chiều ngang: chạy nhiều bản sao của ứng dụng, cấu hình chúng dùng cùng `group.id`, rồi để Kafka phân phối các partition cho những consumer đang hoạt động.

Consumer group cung cấp cơ chế chia tải và khôi phục khi thành viên rời nhóm. Mỗi partition của một topic được giao cho tối đa một consumer trong cùng group tại một thời điểm. Một consumer có thể nhận nhiều partition, còn một consumer không được gán partition nào vẫn có thể tồn tại trong group nhưng không xử lý dữ liệu. Vì thế, số partition là giới hạn quan trọng đối với mức song song của một group.

## 1. Consumer group là gì?

Consumer group là tập hợp các consumer có cùng định danh `group.id`. Kafka xem những consumer này là các thành viên cùng phối hợp đọc một tập topic. Group coordinator theo dõi thành viên và quản lý việc phân phối partition.

Ví dụ, một ứng dụng tạo ba bản sao:

```text
                 Topic: orders
             P0   P1   P2   P3   P4   P5
              \    |    |    |    |   /
               \   |    |    |    |  /
                Consumer group: order-service
                   /       |       \
                  /        |        \
             Instance A  Instance B  Instance C
```

Cả ba instance dùng cùng `group.id=order-service`. Kafka gán các partition cho ba consumer thành viên. Một cách phân phối minh họa là:

| Consumer member | Partition được gán |
|---|---|
| Instance A | `orders-0`, `orders-1` |
| Instance B | `orders-2`, `orders-3` |
| Instance C | `orders-4`, `orders-5` |

Đây chỉ là một cách phân phối ví dụ. Assignment thực tế phụ thuộc số topic đăng ký, số partition, thành viên trong group và partition assignment strategy được cấu hình.

Mỗi partition chỉ có một consumer sở hữu trong group tại một thời điểm. Quy tắc này giúp Kafka giữ thứ tự xử lý trong phạm vi partition và tránh hai consumer cùng group đồng thời đọc cùng một partition. Consumer có thể sở hữu nhiều partition nếu số partition lớn hơn số consumer.

## 2. Nhiều instance phải dùng cùng group.id

Để các bản sao của cùng một dịch vụ chia tải, tất cả phải dùng cùng một `group.id` ổn định. `group.id` là tên logic của consumer group, không phải ID riêng của từng máy hoặc từng pod.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
```

Khi triển khai ba replica của cùng ứng dụng, cả ba replica đều nhận cấu hình `group-id: order-service`. Mỗi replica tạo consumer riêng, nhưng Kafka đưa các consumer đó vào cùng group.

```text
Pod order-service-1  ─┐
Pod order-service-2  ─┼── group.id = order-service
Pod order-service-3  ─┘
```

Nếu đặt một group ID ngẫu nhiên hoặc khác nhau cho từng replica, Kafka sẽ xem chúng là các group độc lập. Mỗi group độc lập có thể đọc toàn bộ partition của topic, nên mọi replica có thể nhận cùng một sự kiện. Điều đó tạo ra hành vi fan-out, không phải chia tải.

Ngược lại, nếu hai dịch vụ có trách nhiệm nghiệp vụ khác nhau nhưng dùng chung group ID, Kafka sẽ phân phối partition giữa chúng. Một sự kiện có thể chỉ được một trong hai dịch vụ nhận. Khi cả hai dịch vụ đều cần nhận mọi sự kiện, mỗi dịch vụ phải dùng một group ID riêng.

## 3. Cùng group để chia tải, khác group để nhận độc lập

Giả sử topic `orders` có sáu partition và có hai nhu cầu: cập nhật tồn kho và tạo báo cáo doanh thu.

<table>
  <table-row>
    <table-cell width="30%">
      **Consumer group**
    </table-cell>
    <table-cell>
      **Hành vi**
    </table-cell>
  </table-row>
  <table-row>
    <table-cell>
      `inventory-service`
    </table-cell>
    <table-cell>
      Ba replica cùng group chia sáu partition. Mỗi record được một member trong group xử lý theo assignment hiện tại.
    </table-cell>
  </table-row>
  <table-row>
    <table-cell>
      `revenue-reporting`
    </table-cell>
    <table-cell>
      Group độc lập cũng đọc topic `orders`. Các member trong group này chia partition của riêng group, nên báo cáo vẫn nhận được mọi record mà group có thể đọc.
    </table-cell>
  </table-row>
</table>

Hai group có committed offset riêng. Việc `inventory-service` đã đọc đến offset nào không làm thay đổi tiến độ của `revenue-reporting`. Mỗi group có thể xử lý cùng một record ở thời điểm khác nhau và có thể có tốc độ tiêu thụ khác nhau.

| Cách cấu hình | Kết quả |
|---|---|
| Nhiều instance cùng `group.id` | Chia partition và chia tải trong cùng một group. |
| Nhiều instance có `group.id` khác nhau | Mỗi group đọc độc lập; có thể nhận toàn bộ dữ liệu của topic. |
| Nhiều dịch vụ logic khác nhau dùng chung `group.id` | Các dịch vụ tranh nhau partition; mỗi dịch vụ không được bảo đảm nhận mọi record. |

Đây là quyết định kiến trúc quan trọng. Hãy chọn group ID theo đơn vị xử lý logic cần có tiến độ đọc độc lập, không theo tên máy hoặc số replica.

## 4. Số partition giới hạn số consumer xử lý song song

Trong cùng một group, một partition chỉ được giao cho một consumer member. Vì vậy, số consumer có thể đồng thời nhận dữ liệu từ một topic bị giới hạn bởi số partition của topic đó.

Ví dụ topic có bốn partition:

| Số consumer trong group | Kết quả có thể xảy ra |
|---:|---|
| 1 | Một consumer nhận cả bốn partition. |
| 2 | Hai consumer chia nhau bốn partition. |
| 4 | Mỗi consumer có thể nhận một partition. |
| 6 | Tối đa bốn consumer có partition; hai consumer còn lại không có partition để xử lý. |

Tăng số replica từ bốn lên sáu không làm một partition được xử lý song song bởi hai consumer trong cùng group. Nếu cần tăng mức song song, cần đánh giá số partition, khả năng phân vùng dữ liệu và năng lực của hệ thống phía sau.

Tăng partition có ảnh hưởng đến cách phân phối key. Producer thường dùng record key để các sự kiện của cùng một thực thể được đưa vào cùng partition và giữ thứ tự tương đối. Khi tăng số partition, cách ánh xạ key sang partition có thể thay đổi; các sự kiện mới của một key có thể được ghi vào partition khác với sự kiện cũ. Vì vậy, việc tăng partition cần được đánh giá cùng yêu cầu thứ tự và cách ứng dụng xử lý dữ liệu đã tồn tại.

Số partition cũng không phải yếu tố duy nhất quyết định throughput. Nếu database chỉ xử lý được một lượng giao dịch nhất định, tăng consumer có thể làm database quá tải mà không tăng tốc độ hoàn tất nghiệp vụ. Hãy đo cả throughput, độ trễ và năng lực của dependency trước khi mở rộng group.

## 5. Một process Spring Kafka có thể tạo nhiều consumer

Trong Spring Kafka, cần phân biệt số replica của ứng dụng và `concurrency` của listener container:

- Mỗi replica là một process hoặc container ứng dụng độc lập.
- `concurrency` tạo nhiều consumer container con cho một listener endpoint trong mỗi replica.
- Mỗi consumer container con có Kafka consumer và poll loop riêng, tham gia group bằng cùng group ID của endpoint.

Ví dụ triển khai ba replica và đặt concurrency bằng hai:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
    listener:
      concurrency: 2
```

```text
Replica 1: consumer 1A, consumer 1B ─┐
Replica 2: consumer 2A, consumer 2B ─┼── group order-service
Replica 3: consumer 3A, consumer 3B ─┘

Tổng số consumer member tối đa: 3 replica × 2 = 6
```

Nếu topic có sáu partition, sáu consumer member có thể cùng nhận partition. Nếu topic chỉ có bốn partition, tối đa bốn member được gán partition; hai member còn lại không có dữ liệu để xử lý. Số consumer thực tế còn phụ thuộc listener endpoint có được khởi tạo, subscription và cấu hình container.

Có thể đặt concurrency ngay trên listener:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    concurrency = "2"
)
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Khi dùng `groupId` trong `@KafkaListener`, giá trị đó xác định group cho endpoint và có thể ghi đè group ID lấy từ consumer factory. Mọi replica chạy cùng phiên bản cấu hình phải dùng cùng giá trị. Nếu dùng group ID từ cấu hình chung, tránh tạo giá trị khác nhau theo hostname hoặc pod name.

Không nên nhân concurrency một cách máy móc. Ví dụ sáu replica với concurrency bốn tạo tối đa 24 consumer member. Nếu topic chỉ có tám partition, phần lớn member sẽ không có partition. Ngoài ra, nhiều consumer có thể tăng số kết nối, request fetch, thread và áp lực lên database. Hãy chọn số replica và concurrency dựa trên partition count cùng throughput mục tiêu.

## 6. Kafka phân phối partition cho các member

Khi consumer khởi động, nó đăng ký tham gia group và khai báo subscription. Group coordinator quản lý membership; group leader thực hiện assignment theo partition assignment strategy mà các member hỗ trợ. Assignment xác định consumer nào sở hữu partition nào.

Một số chiến lược phân phối thường gặp:

| Strategy | Đặc điểm khái quát |
|---|---|
| `RangeAssignor` | Phân phối các partition theo phạm vi trong từng topic; với nhiều topic, tải giữa consumer có thể không đều. |
| `RoundRobinAssignor` | Luân phiên phân phối partition qua các consumer, thường tạo phân bố đều hơn khi subscription tương thích. |
| `StickyAssignor` | Cố gắng phân phối cân bằng đồng thời giữ lại nhiều assignment cũ khi có thể. |
| `CooperativeStickyAssignor` | Kết hợp mục tiêu sticky với incremental cooperative rebalance để giảm số partition phải thu hồi cùng lúc. |

Không nên dựa vào một thứ tự assignment cố định trong logic nghiệp vụ. Partition có thể được chuyển sang member khác khi group thay đổi. Ứng dụng cần hoạt động đúng dù một partition được xử lý bởi bất kỳ replica nào.

Với cooperative rebalance, việc chuyển assignment có thể diễn ra theo nhiều bước và chỉ thu hồi những partition cần chuyển. Cơ chế này giảm thời gian dừng xử lý trong nhiều tình huống, nhưng cần các member và cấu hình tương thích. Hãy kiểm tra phiên bản Kafka client và strategy đang chạy trước khi thay đổi cấu hình assignor.

## 7. Rebalance khi instance tham gia hoặc rời group

Group cần phân phối lại partition khi membership hoặc subscription thay đổi. Những tình huống phổ biến gồm:

- Một replica mới khởi động và tham gia group.
- Một replica dừng bình thường hoặc bị triển khai thay thế.
- Một consumer không gửi heartbeat đúng hạn hoặc vượt giới hạn tiến triển poll.
- Subscription hoặc số partition của topic thay đổi.
- Một thành viên gặp lỗi mạng hoặc process bị dừng đột ngột.

Ví dụ group đang có hai member:

```text
Trước khi scale:
  Consumer A -> P0, P1, P2
  Consumer B -> P3, P4, P5

Consumer C tham gia group
          |
          v
      Rebalance
          |
          v
Sau khi scale:
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5
```

Assignment sau rebalance chỉ mang tính minh họa. Kafka có thể tạo cách phân phối khác dựa trên assignor và trạng thái group.

Trong thời gian rebalance, partition có thể tạm thời ngừng được xử lý khi quyền sở hữu chuyển giao. Consumer cũ cần hoàn tất các bước thu hồi theo protocol, còn consumer mới nhận assignment và bắt đầu đọc từ committed offset của group. Nếu ứng dụng thường xuyên thêm/bớt replica trong thời gian ngắn, rebalance liên tục có thể làm giảm throughput và tăng lag.

Khi scale deployment, nên đặt chính sách rollout phù hợp để tránh dừng quá nhiều replica cùng lúc. Graceful shutdown giúp listener container dừng nhận công việc mới, hoàn tất hoặc xử lý phần công việc đang chạy theo thời gian cho phép, rồi rời group. Với shutdown đột ngột, group phải phát hiện member mất kết nối và phân phối lại partition theo timeout.

## 8. Offset được lưu theo group và partition

Committed offset thuộc về một cặp consumer group và partition. Khi một member rời group, member khác được giao partition đó sẽ tiếp tục từ committed offset hiện có.

Ví dụ:

```text
Group: order-service
Partition: orders-2
Committed offset: 120

Consumer A xử lý record 120
Consumer A dừng trước khi commit 121
          |
          v
Rebalance giao orders-2 cho Consumer B
          |
          v
Consumer B tiếp tục từ offset 120
```

Record ở offset 120 có thể được xử lý lại. Nếu A đã tạo hiệu ứng nghiệp vụ bên ngoài nhưng chưa commit, B có thể lặp lại hiệu ứng đó. Vì vậy, listener cần có khả năng xử lý lặp an toàn, chẳng hạn dùng event ID làm khóa idempotency hoặc lưu dấu vết đã xử lý trong cùng transaction với thay đổi nghiệp vụ.

Nếu A commit offset 121 trước khi nghiệp vụ hoàn tất, B có thể bắt đầu từ 121 và record 120 bị bỏ qua theo tiến độ đã lưu. Do đó, cần xác nhận offset sau khi công việc cần bảo đảm hoàn tất. Với các nghiệp vụ ghi vào database ngoài Kafka, Kafka commit offset và transaction database không tự động trở thành một transaction nguyên tử.

Mỗi group có tiến độ riêng. Nếu tạo một group ID mới, group đó chưa có committed offset cũ và sẽ áp dụng `auto.offset.reset` khi bắt đầu đọc. Với `earliest`, group mới có thể đọc lại từ offset sớm nhất còn lưu; với `latest`, group bắt đầu ở cuối log tại thời điểm xác định offset. Vì thế, đổi group ID trong lúc triển khai có thể làm dịch vụ đọc lại nhiều dữ liệu hoặc bỏ qua phần dữ liệu cũ tùy cấu hình.

## 9. Static membership và định danh consumer

Kafka hỗ trợ static membership thông qua `group.instance.id`. Thuộc tính này cung cấp một định danh ổn định cho một member để group có thể nhận ra member đó khi nó khởi động lại trong một số tình huống. Static membership có thể giảm rebalance do restart ngắn hạn, đặc biệt trong môi trường triển khai có danh tính instance ổn định.

`group.instance.id` phải duy nhất trong một group. Không đặt cùng một giá trị cho tất cả replica, vì hai consumer cùng dùng một static member ID có thể bị xem là xung đột và một member có thể bị loại khỏi group. Khi dùng Spring Kafka với concurrency lớn hơn một, mỗi consumer member cũng cần định danh tĩnh riêng nếu cấu hình static membership được áp dụng; cần tuân theo cách Spring Kafka của phiên bản đang dùng tạo hoặc bổ sung ID cho các child container.

Static membership không thay thế heartbeat hoặc poll loop và không làm cho consumer được phép dừng vô hạn. Nó thay đổi cách group xử lý việc member tạm thời rời kết nối; phát hiện member mất hẳn có thể bị trì hoãn theo timeout. Chỉ bật khi có nhu cầu rõ ràng, có định danh ổn định và đã hiểu tác động khi replica bị thay thế.

`client.id` là thuộc tính khác, thường dùng để nhận diện client trong log, metric và quota. `group.id` xác định nhóm tiêu thụ logic; `group.instance.id` nhận diện một static member trong group; `client.id` giúp quan sát client. Không dùng ba giá trị này thay thế cho nhau.

## 10. Ví dụ triển khai nhiều replica

Giả sử dịch vụ `order-service` đọc topic `orders` có sáu partition. Mục tiêu là chạy ba replica, mỗi replica dùng một consumer cho listener.

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      concurrency: 1
      ack-mode: record
```

Listener:

```java
@KafkaListener(topics = "orders")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    orderService.handle(record.value());

    log.info(
        "Handled order event: topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );
}
```

Khi triển khai ba replica cùng cấu hình, Kafka tạo ba consumer member trong group `order-service`. Với sáu partition, mỗi member có thể nhận hai partition. Khi tăng replica lên sáu, group có thể phân phối một partition cho mỗi member. Khi giảm replica xuống hai, mỗi member có thể nhận khoảng ba partition.

Nếu cần hai consumer trên mỗi replica, đặt `concurrency: 2`. Với ba replica, group có tối đa sáu consumer member. Hãy đảm bảo số partition đủ để sử dụng mức song song đó và database phía sau có thể chịu được số luồng xử lý tăng lên.

Trong Kubernetes, cấu hình `replicas` của Deployment quyết định số process ứng dụng, còn `concurrency` quyết định số consumer trong mỗi process cho listener đó. Hai giá trị này nhân với nhau để ước lượng số member. Khi rollout, Kubernetes có thể tạo pod mới trước khi pod cũ dừng; trong giai đoạn đó số member tạm thời có thể cao hơn số replica mong muốn và gây rebalance. Cần phối hợp `maxSurge`, `maxUnavailable`, readiness và graceful shutdown với yêu cầu sẵn sàng của dịch vụ.

## 11. Những lỗi thường gặp khi chạy nhiều instance

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi replica đều xử lý cùng một event | Mỗi replica đang dùng group ID khác nhau. | Dùng cùng một group ID ổn định cho các replica cần chia tải. |
| Một số replica không nhận record | Số consumer member lớn hơn số partition hoặc assignment không phân bố như kỳ vọng. | Kiểm tra partition count, group assignment và concurrency. |
| Hai dịch vụ cùng cần event nhưng chỉ một dịch vụ nhận | Hai dịch vụ đang dùng chung group ID. | Tạo group ID riêng cho từng đơn vị xử lý logic cần tiến độ độc lập. |
| Tăng replica nhưng throughput không tăng | Số partition không đủ, partition bị lệch tải hoặc dependency đã bão hòa. | Đo assignment, lag từng partition, thời gian listener và tải database. |
| Sau deploy xuất hiện xử lý trùng | Rebalance xảy ra khi record đã xử lý nhưng offset chưa commit. | Dùng idempotency và xác nhận offset sau khi nghiệp vụ hoàn tất. |
| Rebalance diễn ra liên tục | Replica restart thường xuyên, heartbeat/poll timeout hoặc rollout thay đổi membership quá nhanh. | Kiểm tra log group, timeout, poll loop và chiến lược rollout. |
| Một partition trở thành nút thắt | Key phân phối không đều hoặc một partition có lượng dữ liệu lớn hơn hẳn. | Xem phân bố key và lag từng partition; điều chỉnh chiến lược partitioning khi phù hợp. |

Khi điều tra, hãy xem trạng thái group và assignment theo từng member, thay vì chỉ xem tổng số replica đang chạy. Một pod có trạng thái healthy ở Kubernetes không đảm bảo nó đang được gán partition; một member có thể đang idle vì số consumer lớn hơn số partition.

## 12. Nguyên tắc vận hành

- Dùng cùng `group.id` ổn định cho các replica cần chia tải của cùng một consumer group.
- Dùng group ID riêng cho từng dịch vụ logic cần đọc độc lập toàn bộ sự kiện.
- Thiết kế số partition theo mức song song cần thiết và khả năng của các hệ thống phía sau.
- Tính tổng số consumer member từ số replica nhân với listener concurrency; kiểm tra số partition trước khi tăng concurrency.
- Không giả định partition luôn được giao cho cùng một instance. Ứng dụng phải xử lý được việc partition chuyển sang member khác.
- Theo dõi assignment, lag theo partition, rebalance, thời gian xử lý và tốc độ commit.
- Thiết kế nghiệp vụ idempotent để chịu được record được giao lại sau rebalance hoặc sự cố.
- Dùng graceful shutdown và rollout có kiểm soát để giảm rebalance không cần thiết.
- Chỉ dùng static membership khi có định danh ổn định, duy nhất cho từng consumer member và đã hiểu tác động của timeout.

Nhiều instance cùng một consumer group giúp tăng khả năng xử lý song song và duy trì dịch vụ khi một replica rời nhóm. Hiệu quả mở rộng phụ thuộc vào số partition, cách phân phối key, concurrency của Spring Kafka và năng lực của hệ thống phía sau. Khi cấu hình group ID đúng và xử lý an toàn việc giao lại partition, các replica có thể phối hợp chia tải mà vẫn giữ được tiến độ tiêu thụ độc lập với những consumer group khác.
