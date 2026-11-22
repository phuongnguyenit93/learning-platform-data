# Rebalance khi consumer chết

Trong Kafka, consumer group cho phép nhiều consumer cùng chia sẻ việc đọc các partition của một topic. Khi một consumer dừng đột ngột, mất kết nối hoặc không còn đáp ứng điều kiện hoạt động của group, Kafka cần phát hiện thành viên đó không còn khả dụng và phân phối lại các partition của nó cho những consumer còn lại. Quá trình phân phối lại này gọi là **rebalance**.

Rebalance giúp group tiếp tục xử lý dữ liệu sau khi một thành viên gặp lỗi. Tuy nhiên, nó có thể làm gián đoạn việc đọc, tạo thêm độ trễ và khiến một số record được giao lại. Trong Spring Kafka, listener container quản lý vòng đời consumer và phối hợp với Kafka group protocol; ứng dụng cần cấu hình timeout hợp lý, xử lý offset an toàn và bảo đảm side effect có thể chạy lại khi cần.

## 1. Điều gì xảy ra khi một consumer chết?

Mỗi consumer trong group duy trì membership với Kafka. Với group protocol truyền thống, consumer gửi heartbeat định kỳ tới group coordinator để chứng minh mình còn hoạt động. Coordinator theo dõi thời điểm heartbeat cuối cùng. Nếu một member không gửi heartbeat trong thời gian cho phép, coordinator đánh dấu member đó không còn hoạt động và bắt đầu rebalance group.

Ví dụ topic `orders` có sáu partition và group `billing-service` có ba consumer:

```text
Trước sự cố:

  Consumer A  -> P0, P1
  Consumer B  -> P2, P3
  Consumer C  -> P4, P5

Consumer B bị dừng đột ngột

Sau khi coordinator phát hiện B đã rời group:

  Consumer A  -> P0, P1, P2
  Consumer C  -> P3, P4, P5
```

Assignment thực tế phụ thuộc partition assignor và số member còn lại. Ví dụ trên chỉ minh họa việc partition của consumer bị mất được phân phối lại. Nếu group chỉ còn một consumer, consumer đó có thể nhận tất cả partition; nếu số partition nhiều hơn năng lực xử lý, lag có thể tăng dù group đã ổn định trở lại.

Với lỗi process hoặc máy chủ, consumer thường không gửi được thông báo rời group. Coordinator phải chờ cơ chế timeout phát hiện member mất kết nối. Với shutdown có kiểm soát, consumer có thể rời group rõ ràng khi đóng, giúp các member còn lại bắt đầu rebalance sớm hơn. Thời gian phát hiện lỗi vì vậy phụ thuộc loại sự cố và cấu hình group.

## 2. Các giai đoạn của rebalance

Một lần rebalance thường gồm các hoạt động sau:

1. **Phát hiện thay đổi membership:** coordinator nhận thông tin member rời group, member mới tham gia hoặc một thay đổi khác yêu cầu phân phối lại partition.
2. **Thu hồi assignment cũ:** consumer nhận biết partition nào sẽ được thu hồi và thực hiện các bước dọn dẹp cần thiết.
3. **Thỏa thuận assignment mới:** group coordinator và partition assignor xác định member nào sẽ nhận từng partition.
4. **Gán partition:** consumer nhận assignment mới và tiếp tục đọc từ committed offset tương ứng.
5. **Phục hồi xử lý:** listener container tiếp tục poll, gọi listener và commit offset theo cấu hình.

Trong lúc rebalance, một số consumer có thể tạm thời ngừng xử lý. Thời gian gián đoạn phụ thuộc giao thức group, assignor, số partition, số member, callback của ứng dụng và thời gian khôi phục state. Rebalance kéo dài hoặc xảy ra liên tục có thể làm consumer lag tăng nhanh.

Kafka có các biến thể group protocol và hành vi rebalance thay đổi theo phiên bản. Mô tả heartbeat và timeout truyền thống bên dưới chủ yếu nói về classic consumer group protocol. Với consumer group protocol mới hơn, một số thông số heartbeat và session được điều phối phía broker; hãy kiểm tra phiên bản Kafka client/broker và cấu hình đang sử dụng trước khi áp dụng một giá trị cụ thể.

## 3. Eager rebalance và cooperative rebalance

Partition assignor quyết định cách chia partition giữa các member. Hai kiểu rebalance quan trọng là eager và cooperative.

### 3.1. Eager rebalance

Với eager protocol, khi group cần rebalance, các member thu hồi toàn bộ partition đang được gán, sau đó chờ assignment mới. Ngay cả partition không cần chuyển sang consumer khác cũng có thể bị thu hồi rồi gán lại.

```text
Trước:
  A: P0, P1
  B: P2, P3

Eager rebalance:
  A: revoke P0, P1
  B: revoke P2, P3
  group tính assignment mới

Sau:
  A: P0, P2
  B: P1, P3
```

Ưu điểm là mô hình phối hợp đơn giản. Nhược điểm là có thể tạo khoảng dừng lớn hơn vì tất cả assignment bị thu hồi, kể cả partition cuối cùng vẫn thuộc cùng consumer.

### 3.2. Cooperative rebalance

Cooperative rebalance cho phép chuyển partition theo từng bước. Consumer chỉ thu hồi những partition thực sự cần chuyển; các partition không đổi có thể tiếp tục được giữ. Cách này giảm lượng công việc phải dừng và có thể rút ngắn gián đoạn khi group thay đổi membership.

Ví dụ, nếu chỉ cần chuyển P2 từ A sang B, cooperative assignor có thể yêu cầu A thu hồi P2 trước, rồi ở vòng rebalance tiếp theo B nhận P2. Các partition P0, P1 hoặc P3 không cần chuyển có thể tiếp tục được xử lý.

`CooperativeStickyAssignor` là một lựa chọn phổ biến của Kafka client hỗ trợ cooperative protocol. Khi chuyển đổi, cần bảo đảm các member trong group dùng cấu hình assignor tương thích; triển khai rolling giữa các phiên bản client cần theo đúng hướng dẫn tương thích của Kafka. Không thay đổi assignor đồng loạt mà chưa kiểm tra khả năng phối hợp giữa các instance đang chạy.

| Đặc điểm | Eager | Cooperative |
|---|---|---|
| Partition bị thu hồi | Thường thu hồi toàn bộ assignment | Chỉ thu hồi partition cần chuyển |
| Gián đoạn | Có thể rộng hơn | Thường giảm phạm vi gián đoạn |
| Chuyển partition | Thu hồi rồi gán lại trong quá trình rebalance | Có thể cần nhiều vòng để hoàn tất chuyển giao |
| Yêu cầu tương thích | Theo assignor/protocol đã cấu hình | Các member phải hỗ trợ cooperative protocol và cấu hình tương thích |

Cooperative rebalance giảm chi phí chuyển assignment, nhưng không loại bỏ mọi gián đoạn hoặc bảo đảm không có record được giao lại. Offset và side effect vẫn phải được quản lý an toàn.

## 4. Cách Kafka phát hiện consumer không còn hoạt động

Trong classic group protocol, một số cấu hình quan trọng ảnh hưởng thời điểm phát hiện lỗi.

### 4.1. `session.timeout.ms`

`session.timeout.ms` xác định khoảng thời gian coordinator chờ heartbeat từ consumer trước khi xem member đó đã mất. Nếu consumer process bị kill, máy chủ mất điện hoặc mạng bị đứt, coordinator có thể cần chờ đến hết session timeout mới bắt đầu phân phối lại partition.

Timeout quá lớn làm thời gian phát hiện lỗi kéo dài. Timeout quá nhỏ có thể khiến consumer khỏe mạnh bị loại khỏi group khi mạng chập chờn, CPU quá tải hoặc JVM tạm dừng lâu. Khi đó, group có thể rebalance liên tục dù ứng dụng không thực sự bị chết.

### 4.2. `heartbeat.interval.ms`

Trong classic protocol, consumer gửi heartbeat định kỳ. `heartbeat.interval.ms` điều khiển khoảng cách giữa các heartbeat; giá trị thường được đặt nhỏ hơn đáng kể so với `session.timeout.ms` để có nhiều cơ hội gửi heartbeat trước khi hết session. Một quy tắc khởi điểm thường dùng là heartbeat interval không vượt quá khoảng một phần ba session timeout, nhưng phải tuân theo giới hạn broker và cấu hình của phiên bản đang chạy.

Heartbeat thành công không chứng minh listener đang xử lý nghiệp vụ tốt. Một consumer có thể còn heartbeat nhưng listener bị nghẽn, xử lý rất chậm hoặc downstream không phản hồi. Cần theo dõi thêm `max.poll.interval.ms`, processing time và lag.

### 4.3. `max.poll.interval.ms`

`max.poll.interval.ms` giới hạn thời gian tối đa giữa các lần gọi `poll()` của consumer. Nếu ứng dụng nhận một batch rồi xử lý quá lâu mà không poll tiếp, Kafka có thể xem consumer không còn đủ khả năng tiến triển và đưa nó ra khỏi group.

Ví dụ, `max.poll.records=100` và listener xử lý từng record mất trung bình 1 giây. Một batch có thể cần gần 100 giây, chưa kể thời gian gọi database, retry hoặc GC. Nếu `max.poll.interval.ms` đặt thấp hơn thời gian xử lý thực tế ở tải cao, consumer có thể bị rebalance dù process vẫn sống.

Khi dùng static membership với `group.instance.id`, hành vi sau khi vượt max poll interval có thể khác member động: consumer ngừng heartbeat và việc thu hồi partition có thể chờ tới session timeout. Vì vậy, cần xem xét cả hai timeout và không suy luận rằng max poll interval luôn dẫn đến phân phối lại tức thì.

### 4.4. Các cấu hình minh họa

```properties
spring.kafka.consumer.properties[session.timeout.ms]=45000
spring.kafka.consumer.properties[heartbeat.interval.ms]=3000
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[max.poll.records]=100
```

Các giá trị trên chỉ là ví dụ cho classic protocol. Chúng không phải cấu hình tối ưu chung. Hãy đo thời gian xử lý batch ở tải cao, độ trễ downstream, thời gian GC và điều kiện mạng trước khi chọn timeout. Nếu listener xử lý lâu, có thể giảm `max.poll.records`, tăng thời gian xử lý cho phép hoặc thiết kế xử lý bất đồng bộ có cơ chế quản lý offset đúng cách.

## 5. Spring Kafka xử lý rebalance như thế nào?

Trong Spring Kafka, `ConcurrentMessageListenerContainer` hoặc `KafkaMessageListenerContainer` quản lý Kafka consumer và vòng poll. Khi consumer tham gia hoặc rời group, Kafka client thực hiện group protocol và container tiếp nhận partition assignment mới. Listener method chỉ xử lý record khi partition đã được gán cho consumer tương ứng.

Với `@KafkaListener`, có thể cấu hình concurrency để container tạo nhiều consumer:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        concurrency = "3")
public void handle(OrderCreated event) {
    billingService.applyIdempotently(event);
}
```

Nếu topic có sáu partition, concurrency bằng ba có thể tạo ba consumer trong group. Nếu một consumer chết, Kafka phân phối các partition của nó cho các consumer còn lại sau khi phát hiện member đã mất. Nếu tăng concurrency lên sáu, group có thể dùng tối đa sáu consumer song song cho sáu partition, miễn là các tài nguyên downstream đủ khả năng phục vụ.

Trong quá trình shutdown có kiểm soát, listener container dừng consumer theo lifecycle của Spring. Cần đặt thời gian shutdown đủ để xử lý record đang chạy và thực hiện các bước commit cần thiết. Khi process bị kill -9 hoặc máy chủ mất điện, không có callback shutdown đáng tin cậy; thiết kế phải chấp nhận khả năng record được giao lại.

Không nên tạo nhiều consumer group cho cùng một luồng chỉ để tăng concurrency. Các consumer cần chia tải phải cùng group ID; các group ID khác nhau sẽ nhận bản sao dữ liệu độc lập.

## 6. Điều gì xảy ra với record đang xử lý khi partition bị thu hồi?

Đây là điểm quan trọng nhất để tránh mất dữ liệu hoặc tạo side effect trùng. Giả sử consumer B đã poll record offset `120`, bắt đầu ghi kết quả vào database, rồi process bị dừng trước khi commit offset `121`.

```text
Consumer B:
  poll offset 120
       |
       v
  cập nhật database thành công
       |
       X consumer chết trước commit

Kafka phát hiện B mất membership
       |
       v
Partition được gán cho consumer A
       |
       v
A đọc từ committed offset cũ: 120
       |
       v
Record 120 có thể được xử lý lại
```

Đây là hành vi phù hợp với at-least-once khi commit chỉ diễn ra sau khi xử lý thành công. Ứng dụng cần idempotency để lần xử lý lại không tạo thêm khoản thanh toán, đơn hàng hoặc email trùng.

Nếu ứng dụng commit offset `121` trước khi database transaction hoàn tất rồi consumer chết, consumer mới sẽ tiếp tục từ `121`. Side effect của record `120` có thể bị mất. Vì vậy, thời điểm commit phải theo sau điểm hoàn tất nghiệp vụ đã cam kết.

Khi dùng batch, cần lưu ý offset commit là tiến độ liên tục theo partition. Không commit vượt qua một record chưa hoàn tất trong cùng partition. Với xử lý bất đồng bộ, phải theo dõi completion theo partition và commit offset liên tục cao nhất mà mọi record trước đó đã hoàn tất.

## 7. Xử lý partition revoke và lost

Kafka cung cấp `ConsumerRebalanceListener` để ứng dụng nhận callback khi partition được thu hồi hoặc gán mới. Các callback quan trọng gồm:

- `onPartitionsRevoked`: partition sắp được thu hồi trong một lần rebalance bình thường. Có thể dùng để dừng công việc mới trên partition, flush state cục bộ và lưu tiến độ đã xử lý an toàn.
- `onPartitionsAssigned`: partition mới được gán. Có thể dùng để khởi tạo state hoặc phục hồi dữ liệu cục bộ theo partition.
- `onPartitionsLost`: trên các Kafka client hỗ trợ callback này, partition đã bị mất quyền sở hữu trước khi consumer có cơ hội xử lý revoke bình thường. Không được giả định consumer còn quyền commit offset cho partition đó.

Với Kafka consumer thuần, callback có thể được dùng để lưu offset đã xử lý và giải phóng tài nguyên. Trong Spring Kafka, listener container đã quản lý commit theo acknowledgment mode và error handler. Nếu đăng ký callback rebalance tùy chỉnh qua container properties, cần phối hợp với cơ chế commit của container; tránh tự commit một offset vượt quá tiến độ xử lý hoặc cạnh tranh với container.

Một callback revoke nên thực hiện nhanh. Không gọi dịch vụ bên ngoài hoặc chờ tác vụ kéo dài vì callback chạy trong luồng điều khiển consumer và có thể kéo dài thời gian rebalance. Nếu cần flush state lớn, thiết kế checkpoint định kỳ hoặc chia nhỏ state để mỗi lần revoke chỉ còn ít công việc.

Ví dụ minh họa cách triển khai interface Kafka ở mức consumer thuần:

```java
ConsumerRebalanceListener rebalanceListener =
        new ConsumerRebalanceListener() {

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {
        // Dừng nhận công việc mới cho các partition này.
        // Chỉ commit offset của record đã xử lý hoàn tất.
        // Flush state cục bộ trong giới hạn thời gian cho phép.
    }

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {
        // Khởi tạo hoặc phục hồi state cho assignment mới.
    }
};
```

Đây là ví dụ API consumer thuần để giải thích callback. Khi dùng `@KafkaListener`, hãy để listener container quản lý consumer và dùng extension point của phiên bản Spring Kafka tương ứng nếu cần can thiệp rebalance. Không tạo Kafka consumer thứ hai trong listener chỉ để nhận callback.

Với partition lost, không được cố commit tiến độ như thể revoke diễn ra bình thường. Một consumer khác có thể đã sở hữu partition. Hãy dừng side effect chưa hoàn tất, giải phóng state local và dựa vào idempotency khi record được giao lại.

## 8. Static membership và `group.instance.id`

Mặc định, consumer thường tham gia group như dynamic member. Khi process restart, nó rời group rồi tham gia lại với membership mới, có thể tạo rebalance. Với workload có instance ổn định, **static membership** cho phép gắn một định danh bền vững cho consumer bằng `group.instance.id`.

Ví dụ cấu hình:

```properties
spring.kafka.consumer.properties[group.instance.id]=billing-instance-0
```

Static membership có thể giảm rebalance không cần thiết khi một instance khởi động lại trong thời gian ngắn. Coordinator có thể giữ membership trong thời gian session timeout thay vì lập tức xem member đã rời group. Khi instance quay lại với cùng định danh, nó có thể tiếp tục membership cũ theo protocol.

Các giới hạn cần lưu ý:

- Mỗi member đang hoạt động trong cùng group phải có `group.instance.id` duy nhất. Hai process đồng thời dùng cùng ID có thể gây lỗi thành viên trùng.
- ID nên ổn định cho cùng một logical instance qua restart, nhưng phải khác nhau giữa các replica.
- Với môi trường autoscaling hoặc replica có danh tính thay đổi liên tục, static membership cần được thiết kế cẩn thận.
- Nếu instance chết hẳn, partition có thể phải chờ session timeout trước khi được gán lại. Static membership có thể giảm rebalance khi restart ngắn nhưng làm chậm failover nếu timeout quá dài.
- Với listener concurrency lớn hơn một, cần bảo đảm mỗi Kafka consumer thực tế có định danh duy nhất. Cách Spring Kafka tạo suffix cho instance ID phụ thuộc phiên bản và cấu hình; cần xác minh thay vì cấp cùng một giá trị cho nhiều consumer.

Static membership không thay thế heartbeat, poll interval, idempotency hoặc monitoring. Nó chỉ thay đổi cách group nhận diện member qua các lần rời và tham gia.

## 9. Tuning để cân bằng phát hiện lỗi và ổn định group

Không nên giảm mọi timeout xuống thấp nhất để rebalance nhanh. Timeout ngắn làm phát hiện lỗi nhanh hơn nhưng cũng tăng nguy cơ loại nhầm consumer khỏe mạnh khi có GC pause, tải CPU cao hoặc mạng không ổn định.

| Tham số | Tác động | Khi điều chỉnh cần xem |
|---|---|---|
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trong classic protocol | Độ trễ phát hiện consumer chết, giới hạn broker, heartbeat và độ ổn định mạng |
| `heartbeat.interval.ms` | Tần suất heartbeat trong classic protocol | Tương quan với session timeout và tải mạng |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần poll | Thời gian xử lý batch ở tải cao, retry đồng bộ và GC pause |
| `max.poll.records` | Số record tối đa trong một poll | Thời gian xử lý batch, throughput, bộ nhớ và khả năng commit |
| `partition.assignment.strategy` | Cách phân phối partition và kiểu rebalance | Tính tương thích giữa các member, số partition di chuyển và phiên bản client |
| `group.instance.id` | Bật static membership cho member có định danh ổn định | Vòng đời instance, tính duy nhất và thời gian failover chấp nhận được |
| `concurrency` của listener | Số consumer thread trong ứng dụng | Số partition, CPU, database connection pool và năng lực downstream |

Một cách điều chỉnh có kiểm soát:

1. Đo p95/p99 thời gian xử lý record và batch ở tải thực tế.
2. Chọn `max.poll.records` sao cho batch có thể hoàn tất trong `max.poll.interval.ms` với headroom.
3. Đo thời gian phát hiện một consumer chết trong môi trường kiểm thử và so sánh với RTO.
4. Theo dõi rebalance rate, số partition di chuyển và lag trong khi rolling deployment.
5. Chỉ bật cooperative assignor hoặc static membership sau khi kiểm tra compatibility và uniqueness.
6. Diễn tập lại các kịch bản kill process, mất network, restart nhanh và downstream chậm sau mỗi thay đổi quan trọng.

Với classic protocol, heartbeat interval thường được đặt thấp hơn nhiều so với session timeout. Với group protocol mới, một số giá trị có thể được điều khiển phía broker; hãy dùng tài liệu của phiên bản triển khai để biết tham số nào thực sự có hiệu lực.

## 10. Cấu hình Spring Boot minh họa

Ví dụ dưới đây thể hiện một cấu hình consumer group cho listener đồng bộ. Giá trị cần điều chỉnh theo tốc độ xử lý, broker và yêu cầu phục hồi của ứng dụng.

```properties
spring.kafka.consumer.group-id=billing-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.properties[session.timeout.ms]=45000
spring.kafka.consumer.properties[heartbeat.interval.ms]=3000
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[max.poll.records]=100
spring.kafka.listener.ack-mode=record
spring.kafka.listener.concurrency=3
```

Nếu dùng cooperative sticky assignor, có thể cấu hình thuộc tính producer/consumer client tương ứng, ví dụ:

```properties
spring.kafka.consumer.properties[partition.assignment.strategy]=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Chỉ dùng cấu hình này khi tất cả consumer trong group và phiên bản Kafka client hỗ trợ cooperative protocol tương thích. Khi rolling upgrade, hãy làm theo quy trình chuyển đổi assignor mà Kafka hỗ trợ.

Nếu dùng static membership, cấu hình `group.instance.id` theo từng logical consumer và bảo đảm không trùng giữa các member đang hoạt động. Với nhiều replica chạy cùng cấu hình, không hard-code cùng một ID cho tất cả instance.

## 11. Graceful shutdown và rolling deployment

Shutdown có kiểm soát giúp consumer rời group rõ ràng và cho listener container cơ hội hoàn tất công việc đang chạy. Khi triển khai phiên bản mới, cần tránh dừng đồng thời quá nhiều consumer trong cùng group vì điều đó có thể làm giảm năng lực xử lý và gây nhiều lần rebalance.

Các nguyên tắc thực hành:

- Dùng rolling deployment với số lượng instance dừng cùng lúc được kiểm soát.
- Cấp termination grace period đủ cho container dừng listener và hoàn tất xử lý trong giới hạn đã định.
- Không commit offset trước khi side effect nghiệp vụ hoàn tất.
- Dừng nhận công việc mới khi shutdown bắt đầu và để container quản lý vòng đời consumer.
- Theo dõi rebalance, lag và processing rate trong suốt quá trình rollout.
- Có phương án rollback nếu phiên bản mới gây exception, xử lý chậm hoặc rebalance liên tục.

Nếu nền tảng gửi tín hiệu dừng nhưng sau đó kill process khi hết grace period, công việc đang chạy có thể bị gián đoạn. Vì thế, idempotency vẫn cần thiết kể cả khi có graceful shutdown.

## 12. Điều tra sự cố rebalance liên tục

Rebalance liên tục (rebalance storm) thường là dấu hiệu member không duy trì được hoạt động ổn định hoặc cấu hình không phù hợp với thời gian xử lý. Không nên chỉ tăng session timeout mà chưa xác định nguyên nhân.

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Consumer liên tục rời và tham gia group | Process restart, crash loop, liveness probe quá nhạy | Kiểm tra log ứng dụng, exit code, orchestration event và lịch sử rollout |
| Rebalance sau các batch xử lý dài | Vượt `max.poll.interval.ms` | Đo thời gian xử lý batch, giảm max poll records hoặc điều chỉnh interval có kiểm soát |
| Consumer bị loại khi mạng chập chờn | Heartbeat không tới coordinator trong session timeout | Kiểm tra packet loss, DNS, broker load, CPU và GC pause |
| Group ổn định nhưng lag tăng | Throughput consumer thấp hơn tốc độ dữ liệu vào hoặc downstream chậm | So sánh processing rate, input rate, partition skew và dependency latency |
| Rebalance kéo dài sau khi thêm replica | Số member/partition lớn, callback revoke chậm hoặc assignment phức tạp | Đo callback duration, số partition di chuyển và assignor đang dùng |
| Static member chết nhưng partition chưa được gán lại | Coordinator đang chờ session timeout | Xác nhận heartbeat và session timeout; đánh giá trade-off của static membership |
| Một partition xử lý chậm hơn hẳn | Key phân bố lệch hoặc một consumer bị nghẽn | Xem lag theo partition, record size, key distribution và downstream theo luồng |

Khi điều tra, thu thập log group coordinator, consumer log, container lifecycle event và metric theo cùng một khoảng thời gian. Ghi nhận timestamp lúc process chết, lúc coordinator phát hiện member mất, lúc rebalance bắt đầu, lúc assignment hoàn tất và lúc consumer xử lý lại record đầu tiên. Các mốc này giúp xác định phần thời gian bị tiêu tốn ở detection, coordination hay khởi động listener.

## 13. Diễn tập consumer chết và xác nhận phục hồi

Một quy trình kiểm thử failure nên mô phỏng nhiều dạng sự cố vì graceful shutdown và process crash có hành vi khác nhau.

### Kịch bản A: dừng một consumer có kiểm soát

1. Khởi chạy group với nhiều consumer và tạo tải ổn định.
2. Ghi nhận assignment, committed offset, lag và processing rate.
3. Dừng một instance theo lifecycle bình thường.
4. Quan sát member rời group và partition được phân phối lại.
5. Xác nhận consumer còn lại tiếp tục xử lý và lag không tăng vượt SLO.

### Kịch bản B: kill process đột ngột

1. Khởi chạy lại group với cùng cấu hình và tải kiểm thử.
2. Kill một consumer mà không chạy graceful shutdown.
3. Ghi nhận thời gian từ lúc process chết đến lúc coordinator phát hiện member mất.
4. Quan sát rebalance và assignment mới.
5. Xác nhận record chưa commit được giao lại và không tạo side effect trùng.

### Kịch bản C: consumer vẫn sống nhưng xử lý quá lâu

1. Tạo một record khiến listener xử lý lâu hơn dự kiến hoặc mô phỏng downstream timeout.
2. Quan sát poll interval, heartbeat và rebalance.
3. Xác định consumer có vượt `max.poll.interval.ms` hay không.
4. Điều chỉnh batch size, timeout hoặc thiết kế xử lý để group duy trì ổn định.

### Tiêu chí phục hồi

Sau mỗi diễn tập, xác nhận:

- Group trở lại trạng thái ổn định với số member mong đợi.
- Mọi partition cần xử lý đã được gán.
- Committed offset tiếp tục tiến triển và lag giảm theo tốc độ dự kiến.
- Record chưa commit được giao lại an toàn.
- Không có record bị bỏ qua do commit sớm.
- Side effect không bị nhân đôi nhờ idempotency hoặc deduplication.
- Thời gian phát hiện lỗi và thời gian phục hồi nằm trong mục tiêu RTO đã đặt.

Ghi lại thời gian phát hiện, thời gian rebalance, thời gian consumer tiếp tục xử lý, lượng backlog và mọi sai khác nghiệp vụ. Nếu RTO không đạt, cần xác định phần chậm do timeout, rebalance, startup, dependency hay throughput sau failover.

## 14. Nguyên tắc vận hành cần giữ

1. Consumer chết không đồng nghĩa partition được gán lại ngay lập tức; coordinator cần phát hiện member mất theo cơ chế group protocol.
2. Chọn session timeout, heartbeat interval và max poll interval dựa trên dữ liệu tải thực tế và phiên bản Kafka đang dùng.
3. Dùng cooperative rebalance khi toàn bộ group hỗ trợ và quy trình chuyển đổi assignor đã được kiểm soát.
4. Chỉ dùng static membership khi có định danh ổn định, duy nhất cho từng consumer thực tế và chấp nhận trade-off về thời gian failover.
5. Để Spring Kafka listener container quản lý vòng đời consumer và commit theo acknowledgment mode đã chọn.
6. Khi partition revoke, chỉ lưu tiến độ đã hoàn tất; khi partition lost, không giả định còn quyền commit.
7. Thiết kế listener idempotent vì record có thể được giao lại sau crash hoặc rebalance.
8. Theo dõi rebalance rate, lag theo partition, processing time, lỗi commit và thời gian phục hồi.
9. Dùng graceful shutdown và rolling deployment để giảm rebalance không cần thiết, nhưng vẫn chuẩn bị cho crash đột ngột.
10. Diễn tập kill process, mất mạng, xử lý quá lâu và restart nhanh để đo RTO thực tế.

Rebalance là cơ chế giúp consumer group tiếp tục hoạt động khi membership thay đổi. Độ tin cậy của hệ thống phụ thuộc vào việc phát hiện lỗi đúng thời điểm, phân phối lại partition ổn định, commit offset sau khi xử lý hoàn tất và bảo đảm record được giao lại không làm lặp tác động nghiệp vụ.
