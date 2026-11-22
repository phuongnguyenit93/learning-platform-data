# Consumer group và committed offset

Trong Kafka, consumer group cho phép nhiều consumer cùng chia nhau đọc dữ liệu của một tập topic. Kafka theo dõi tiến độ của từng group bằng **committed offset** cho mỗi partition. Hai cơ chế này kết hợp để tạo khả năng mở rộng xử lý, tiếp tục công việc sau khi consumer khởi động lại và phối hợp việc phân chia partition khi ứng dụng thay đổi số instance.

Trong Spring Kafka, `@KafkaListener` thường chạy bên trong listener container. Container quản lý Kafka consumer, poll dữ liệu, gọi listener method và commit offset theo acknowledgment mode đã cấu hình. Vì vậy, muốn vận hành consumer bền vững cần hiểu cả hành vi của Kafka consumer group lẫn cách Spring Kafka quản lý commit.

## 1. Consumer group là gì?

Consumer group là tập hợp các consumer có cùng `group.id`. Kafka xem chúng là những thành viên cùng xử lý dữ liệu của các topic được subscribe. Với mỗi partition, tại một thời điểm chỉ có tối đa một consumer trong cùng group được gán để đọc partition đó. Các group khác nhau có thể đọc độc lập cùng một topic.

Ví dụ topic `orders` có bốn partition và service `billing` chạy với ba consumer trong group `billing-service`:

```text
Topic orders
  Partition 0  --------------------> Consumer A
  Partition 1  --------------------> Consumer B
  Partition 2  --------------------> Consumer C
  Partition 3  --------------------> Consumer A

Consumer group: billing-service
```

Consumer A được gán hai partition; B và C mỗi consumer một partition. Nếu tăng group lên bốn consumer, mỗi consumer có thể nhận một partition. Nếu chạy sáu consumer nhưng topic vẫn chỉ có bốn partition, ít nhất hai consumer sẽ không được gán partition và không đọc dữ liệu từ topic đó.

Các nguyên tắc quan trọng:

- Consumer cùng `group.id` chia nhau xử lý partition và cùng chia sẻ tiến độ đọc.
- Consumer thuộc group khác có offset độc lập, nên có thể đọc lại cùng dữ liệu cho mục đích khác.
- Một partition chỉ được gán cho tối đa một consumer trong cùng group tại một thời điểm, nhưng có thể được đọc đồng thời bởi consumer thuộc các group khác nhau.
- Số consumer có ích cho một group bị giới hạn bởi số partition có thể gán cho group.
- Thứ tự bản ghi được bảo đảm trong một partition. Không có thứ tự toàn cục giữa nhiều partition.

Ví dụ, `billing-service` và `analytics-service` có thể cùng đọc topic `orders` bằng hai group ID khác nhau. Billing xử lý thanh toán; analytics tính báo cáo. Việc billing commit offset không làm analytics bỏ qua dữ liệu, vì mỗi group có tiến độ riêng.

## 2. Group ID và phạm vi tiến độ đọc

`group.id` là định danh của consumer group và cũng là khóa quan trọng để Kafka lưu tiến độ đọc. Trong Spring Kafka, có thể đặt group ID mặc định cho consumer factory hoặc ghi đè ở từng listener bằng thuộc tính `groupId`.

```properties
spring.kafka.consumer.group-id=billing-service
```

```java
@KafkaListener(topics = "orders")
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

Listener trên dùng group ID mặc định của consumer factory. Có thể khai báo rõ group riêng cho listener:

```java
@KafkaListener(topics = "orders", groupId = "invoice-service")
public void handleInvoice(OrderCreated event) {
    invoiceService.createInvoice(event);
}
```

Nếu nhiều listener cùng đọc một topic và cần chia tải, chúng phải tham gia cùng group. Nếu mỗi listener cần nhận đầy đủ bản ghi độc lập, chúng phải dùng các group ID khác nhau. Dùng nhầm cùng một group ID cho hai ứng dụng có mục đích xử lý độc lập có thể khiến chúng chia nhau record, làm mỗi ứng dụng chỉ thấy một phần dữ liệu.

Group ID cần ổn định qua các lần restart và triển khai. Đổi group ID thường tạo ra một tiến độ đọc mới. Nếu group mới chưa có committed offset, `auto.offset.reset` sẽ quyết định vị trí bắt đầu. Vì thế, đổi group ID có thể khiến ứng dụng đọc lại nhiều dữ liệu hoặc bỏ qua dữ liệu cũ tùy cấu hình reset.

## 3. Partition assignment và rebalance

Kafka group coordinator quản lý membership và quá trình phân phối partition cho các thành viên của group. Khi consumer tham gia, rời group, mất heartbeat, subscribe thay đổi hoặc số partition thay đổi, Kafka có thể thực hiện **rebalance** để phân phối lại partition.

Ví dụ group ban đầu có hai consumer và bốn partition:

```text
Trước rebalance:
  Consumer A: P0, P1
  Consumer B: P2, P3

Consumer C tham gia group

Sau rebalance:
  Consumer A: P0, P1
  Consumer B: P2
  Consumer C: P3
```

Trong lúc rebalance, việc đọc có thể tạm dừng hoặc bị gián đoạn tùy assignment strategy và giao thức group đang dùng. Container cần xử lý việc thu hồi partition cũ, hoàn tất hoặc dừng công việc đang chạy theo chính sách, sau đó tiếp tục với assignment mới. Rebalance thường xuyên có thể làm throughput giảm, consumer lag tăng và tăng khả năng một bản ghi được xử lý lại.

Các nguyên nhân thường gặp gồm:

- Instance ứng dụng liên tục khởi động lại hoặc bị health check loại bỏ.
- Listener xử lý một batch lâu hơn `max.poll.interval.ms`.
- Consumer không gửi heartbeat đúng hạn do mạng, CPU bị nghẽn hoặc luồng consumer bị chặn.
- Thay đổi số instance, subscription hoặc partition của topic.
- Lỗi xử lý khiến container dừng rồi khởi động lại liên tục.

Kafka hỗ trợ các assignment strategy khác nhau. Range assignor phân phối các partition theo topic và range; round-robin phân phối luân phiên; cooperative sticky cố gắng giữ assignment ổn định và chỉ chuyển các partition cần thiết qua rebalance hợp tác. Chiến lược cụ thể phụ thuộc cấu hình client và phiên bản Kafka. Không nên giả định mọi rebalance đều dừng toàn bộ consumer trong cùng thời gian hoặc luôn giữ nguyên assignment.

Với Spring Kafka, có thể cấu hình số consumer thread của listener container bằng `concurrency`. Đây là số consumer được tạo trong mỗi ứng dụng cho listener đó, không phải số partition. Tăng concurrency chỉ giúp khi group còn partition để gán và hệ thống downstream còn năng lực xử lý.

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        concurrency = "3")
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

Với ba partition, concurrency lớn hơn ba thường không tăng khả năng xử lý song song của listener này. Khi có nhiều topic trong subscription, số partition tổng và quy tắc assignment quyết định mức song song thực tế.

## 4. Offset và committed offset

Mỗi record trong một partition có một offset tăng dần. Offset là vị trí của record trong partition, không phải ID toàn cục của record trên toàn cluster.

Ví dụ partition 0 có các record:

| Partition | Offset | Nội dung minh họa |
|---|---:|---|
| P0 | 100 | Order A created |
| P0 | 101 | Order B created |
| P0 | 102 | Order C created |
| P0 | 103 | Order D created |
| P0 | 104 | Order E created |

Consumer group lưu committed offset cho từng cặp topic-partition. Committed offset thể hiện **vị trí tiếp theo consumer sẽ đọc**, không phải offset của record cuối cùng đã xử lý. Nếu ứng dụng đã xử lý thành công record offset `104`, vị trí cần commit thường là `105`.

```text
Record cuối đã xử lý: offset 104
Committed offset:     105
Record tiếp theo:     offset 105
```

Quy ước này giúp consumer tiếp tục từ vị trí kế tiếp sau khi restart. Khi xem công cụ quản trị hiển thị committed offset, cần nhớ giá trị đó có thể lớn hơn offset cuối cùng đã xử lý một đơn vị.

Committed offset được Kafka lưu theo group và topic-partition trong internal topic `__consumer_offsets`. Ứng dụng không cần tự tạo bảng offset trong database để Kafka biết vị trí đọc. Việc commit có thể được thực hiện tự động bởi Kafka client hoặc do Spring Kafka listener container quản lý theo acknowledgment mode.

### 4.1. Log end offset và consumer lag

Log end offset (LEO) mô tả vị trí cuối của log theo cách biểu diễn offset tiếp theo có thể được ghi. Consumer lag thường được ước tính bằng hiệu giữa log end offset và committed offset của group trên từng partition:

```text
lag xấp xỉ = log end offset - committed offset
```

Ví dụ, log end offset là `1500`, committed offset của group là `1200`, lag xấp xỉ `300` record. Đây là phép đo số lượng record đang chờ theo tiến độ commit. Nó không trực tiếp cho biết record cũ nhất đã chờ bao lâu, tốc độ xử lý hiện tại hoặc side effect nghiệp vụ đã hoàn tất chưa.

Khi xử lý bất đồng bộ hoặc commit theo batch, committed offset có thể đi sau những record đã xử lý xong trong bộ nhớ. Ngược lại, nếu commit sai thời điểm, committed offset có thể đi trước record chưa hoàn tất và gây mất xử lý. Vì vậy, cần xem lag cùng processing rate, tuổi record cũ nhất, lỗi xử lý và metric nghiệp vụ.

## 5. Khi nào consumer commit offset?

Commit offset là thao tác lưu tiến độ đọc của group lên Kafka. Điểm commit quyết định bản ghi nào có thể được giao lại sau khi consumer dừng hoặc partition được chuyển sang thành viên khác.

Có hai hướng quản lý chính:

- **Auto commit:** Kafka consumer client định kỳ commit vị trí hiện tại theo `auto.commit.interval.ms` khi `enable.auto.commit=true`.
- **Manual/container-managed commit:** ứng dụng hoặc Spring Kafka listener container quyết định thời điểm commit sau khi xử lý record theo acknowledgment mode.

Auto commit dễ cấu hình nhưng có thể commit vị trí đã poll trước khi ứng dụng hoàn tất xử lý mọi record trong batch. Nếu consumer dừng sau khi commit nhưng trước khi xử lý xong, record có thể không được gửi lại cho group. Với xử lý nghiệp vụ quan trọng, thường nên tắt auto commit và để listener container quản lý commit.

## 6. Acknowledgment mode trong Spring Kafka

Spring Kafka listener container cung cấp nhiều acknowledgment mode để điều khiển thời điểm commit offset. Từ Spring Kafka 2.3, framework đặt `enable.auto.commit=false` nếu ứng dụng không cấu hình rõ giá trị khác; nên cấu hình tường minh để tránh hiểu nhầm khi đọc application properties.

Ví dụ cấu hình cơ bản:

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.listener.ack-mode=record
```

Các mode thường dùng:

| Ack mode | Thời điểm commit | Phù hợp khi |
|---|---|---|
| `RECORD` | Sau khi listener xử lý thành công từng record | Muốn tiến độ commit sát với từng record và listener xử lý từng record |
| `BATCH` | Sau khi tất cả record của lần poll được xử lý thành công | Muốn giảm số lần commit và chấp nhận replay một phần batch khi có lỗi |
| `TIME` | Khi đạt khoảng thời gian commit đã cấu hình và batch đã được xử lý | Muốn giới hạn tần suất commit theo thời gian |
| `COUNT` | Khi đạt số lượng record đã xử lý và batch đã được xử lý | Muốn commit theo số lượng record |
| `COUNT_TIME` | Khi đạt điều kiện count hoặc time và batch đã được xử lý | Muốn kết hợp hai ngưỡng |
| `MANUAL` | Listener gọi acknowledge; container commit theo quy tắc hoàn tất batch | Muốn listener quyết định khi record được xem là đã xử lý |
| `MANUAL_IMMEDIATE` | Listener gọi acknowledge và container commit ngay khi có thể, đặc biệt khi gọi trên consumer thread | Cần kiểm soát rõ thời điểm commit từng acknowledgment |

`RECORD` và `BATCH` là lựa chọn phổ biến cho listener đồng bộ. `RECORD` giúp giảm lượng record có thể phải replay sau lỗi ở một record, đổi lại có thể tạo nhiều commit hơn. `BATCH` giảm commit overhead nhưng nếu batch có nhiều record và listener thất bại trước khi batch hoàn tất, các record đã xử lý trước đó có thể được gửi lại.

Với manual acknowledgment, chỉ gọi `acknowledge()` sau khi xử lý nghiệp vụ cần thiết hoàn tất. Nếu gọi acknowledge trước khi ghi database hoặc gọi dịch vụ đích thành công, consumer có thể commit offset rồi dừng, khiến Kafka không gửi lại record dù side effect chưa hoàn tất.

### 6.1. Ví dụ listener với commit theo record

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void handle(OrderCreated event) {
    billingService.applyIdempotently(event);
}
```

Kết hợp với `spring.kafka.listener.ack-mode=record`, container commit offset sau khi listener xử lý thành công từng record. Nếu listener ném exception, container chuyển lỗi sang error handler theo cấu hình và không coi record đó là đã xử lý thành công theo luồng commit thông thường.

`applyIdempotently()` biểu thị thao tác nghiệp vụ có thể chạy lại an toàn, ví dụ ghi event ID vào inbox table với unique constraint trong cùng transaction database với cập nhật trạng thái đơn hàng. Cách này xử lý trường hợp side effect đã hoàn tất nhưng tiến trình dừng trước khi offset được commit.

### 6.2. Ví dụ manual acknowledgment

Khi cần listener quyết định rõ thời điểm xác nhận, có thể dùng `Acknowledgment`:

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.listener.ack-mode=manual
```

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void handle(OrderCreated event, Acknowledgment acknowledgment) {
    billingService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
```

Trong ví dụ này, listener chỉ acknowledge sau khi `applyIdempotently()` hoàn tất. Nếu phương thức nghiệp vụ ném exception, dòng acknowledge không chạy và container xử lý lỗi theo cấu hình. Với `MANUAL`, acknowledgment được container phối hợp commit theo quy tắc batch; nếu cần commit ngay tại thời điểm acknowledge, xem xét `MANUAL_IMMEDIATE` và bảo đảm gọi acknowledgment đúng luồng theo yêu cầu của Spring Kafka.

Không nên vừa để Kafka client auto commit vừa tự commit offset trong listener. Chọn một cơ chế quản lý nhất quán để tránh hai luồng commit cạnh tranh.

## 7. Delivery semantics và hậu quả của thời điểm commit

Thời điểm xử lý nghiệp vụ so với thời điểm commit quyết định khả năng mất hoặc xử lý trùng record.

### 7.1. At-most-once

Commit offset trước khi thực hiện side effect. Nếu consumer dừng sau commit nhưng trước khi xử lý, Kafka sẽ tiếp tục từ offset mới và record chưa tạo ra kết quả nghiệp vụ. Cách này giảm khả năng xử lý trùng nhưng có thể mất xử lý.

```text
Poll record
   |
   v
Commit offset
   |
   v
Thực hiện nghiệp vụ
```

### 7.2. At-least-once

Thực hiện nghiệp vụ trước rồi mới commit offset. Nếu consumer dừng sau khi side effect hoàn tất nhưng trước commit, Kafka có thể giao lại record sau khi group phục hồi. Vì vậy, record có thể được xử lý nhiều lần. Đây là lựa chọn phổ biến khi cần tránh mất sự kiện và có thể làm side effect idempotent.

```text
Poll record
   |
   v
Thực hiện nghiệp vụ thành công
   |
   v
Commit offset
```

### 7.3. Exactly-once trong Kafka

Kafka transactions có thể kết hợp việc ghi record đầu ra và commit offset của record đầu vào trong một transaction Kafka. Với consumer đọc bằng `isolation.level=read_committed`, luồng Kafka-to-Kafka có thể đạt exactly-once semantics trong phạm vi transaction được cấu hình đúng.

Exactly-once của Kafka không tự bao gồm database, HTTP API, email hoặc hệ thống bên ngoài. Nếu listener cập nhật database rồi commit offset Kafka, hai thao tác vẫn có thể rơi vào hai thời điểm khác nhau. Với side effect bên ngoài Kafka, cần thiết kế idempotency, inbox/outbox hoặc cơ chế giao dịch phù hợp.

| Thứ tự | Nếu consumer dừng giữa hai bước | Hệ quả |
|---|---|---|
| Commit rồi xử lý | Dừng sau commit | Có thể mất side effect của record |
| Xử lý rồi commit | Dừng sau xử lý | Record có thể được xử lý lại |
| Kafka transaction gồm output và input offset | Transaction abort hoặc commit nguyên tử | Output và tiến độ input nhất quán trong phạm vi Kafka transaction |

## 8. `auto.offset.reset` và group chưa có offset

`auto.offset.reset` xác định hành vi khi group không có committed offset hợp lệ cho partition, hoặc offset đã commit không còn nằm trong log do retention. Thuộc tính này không ghi đè một committed offset hợp lệ đang tồn tại.

Các lựa chọn thường gặp:

- `earliest`: bắt đầu từ offset sớm nhất còn được lưu trong partition.
- `latest`: bắt đầu từ cuối log hiện tại, bỏ qua các record cũ hơn chưa có offset được group ghi nhận.
- `none`: phát sinh lỗi nếu không tìm thấy offset hợp lệ thay vì tự chọn vị trí bắt đầu.

Ví dụ:

```properties
spring.kafka.consumer.auto-offset-reset=earliest
```

`earliest` hữu ích khi group mới cần đọc lại dữ liệu còn retention. `latest` thường phù hợp với một số luồng chỉ quan tâm sự kiện mới phát sinh sau khi consumer bắt đầu, nhưng có thể làm ứng dụng bỏ qua record đã tồn tại khi group chưa có offset. `none` phù hợp khi muốn buộc vận hành quyết định rõ vị trí đọc thay vì tự động reset.

Ví dụ, group `billing-v2` chưa từng đọc topic `orders`, topic hiện có offset từ 0 đến 999. Với `earliest`, group bắt đầu ở offset sớm nhất còn tồn tại; với `latest`, group bắt đầu ở cuối log và chỉ nhận record mới sau đó. Nếu group `billing-service` đã có committed offset hợp lệ là 700, thay đổi `auto.offset.reset` không làm group tự quay về 0 hoặc nhảy tới 999.

Khi offset đã commit bị retention loại khỏi log, Kafka có thể áp dụng `auto.offset.reset`. Điều này có thể tạo ra khoảng dữ liệu không thể đọc lại từ topic. Vì thế, retention cần dài hơn thời gian gián đoạn tối đa và thời gian phục hồi backlog mà hệ thống dự kiến chịu được.

## 9. Commit failure, rebalance và xử lý record đang chạy

Commit có thể thất bại nếu consumer mất kết nối, group đang rebalance hoặc thành viên cũ không còn hợp lệ để commit. Khi partition bị thu hồi, consumer cần dừng nhận công việc mới từ partition đó và xử lý các record đã poll theo chính sách an toàn.

Không nên giả định một lần gọi commit thành công ở phía ứng dụng luôn có nghĩa offset đã được lưu bền vững. Với commit bất đồng bộ, callback có thể báo lỗi sau khi ứng dụng đã tiếp tục công việc khác. Với commit đồng bộ, ứng dụng có thể phải chờ broker phản hồi và cần xử lý timeout hoặc exception. Spring Kafka listener container quản lý commit theo acknowledgment mode và error handler; tránh tự gọi `consumer.commitSync()` từ listener method nếu không có thiết kế rõ ràng.

Các cấu hình ảnh hưởng đến group stability:

```properties
spring.kafka.consumer.properties[max.poll.records]=100
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[session.timeout.ms]=45000
```

Đây là giá trị minh họa, không phải khuyến nghị cố định cho mọi ứng dụng. `max.poll.records` giới hạn số record nhận trong một poll. `max.poll.interval.ms` giới hạn khoảng thời gian giữa các lần poll; nếu xử lý batch lâu hơn giá trị này, consumer có thể bị rời group và partition được gán lại. `session.timeout.ms` tham gia cơ chế phát hiện consumer mất kết nối cùng heartbeat. Cần điều chỉnh dựa trên thời gian xử lý ở tải cao, cấu hình heartbeat và giới hạn của Kafka cluster.

Nếu listener xử lý bất đồng bộ hoặc chuyển record sang executor khác, không được commit offset chỉ vì đã đưa record vào hàng đợi nội bộ. Hàng đợi có thể mất dữ liệu khi process dừng. Chỉ acknowledge khi công việc đã đạt điểm hoàn tất mà hệ thống cam kết, hoặc phải có cơ chế lưu trạng thái bền vững cho công việc đang chờ.

## 10. Quan sát consumer group và committed offset

Vận hành cần quan sát cả membership, assignment, tiến độ commit và độ trễ xử lý. Các tín hiệu hữu ích gồm:

- Số member hiện tại trong group và trạng thái group.
- Partition được gán cho từng consumer.
- Committed offset và log end offset theo partition.
- Consumer lag theo group và theo partition.
- Số lần rebalance, thời gian rebalance và lỗi commit.
- Số record xử lý mỗi giây, thời gian xử lý và tuổi record cũ nhất chưa xử lý.
- Tỷ lệ lỗi listener, retry và record chuyển vào DLT.

Consumer lag tăng liên tục có thể cho thấy consumer không theo kịp tốc độ dữ liệu mới. Lag giảm về 0 không đảm bảo nghiệp vụ đã hoàn tất nếu ứng dụng commit trước side effect hoặc xử lý bất đồng bộ không được quản lý. Nên đối chiếu metric Kafka với metric nghiệp vụ như số đơn hàng đã ghi nhận, số giao dịch còn chờ và thời gian từ event creation đến event completion.

Khi điều tra một group:

1. Xác nhận đúng `group.id`, topic và môi trường đang được kiểm tra.
2. Xem trạng thái group, số member và partition assignment.
3. So sánh committed offset với log end offset theo từng partition.
4. Kiểm tra processing rate, tuổi record cũ nhất và lỗi listener.
5. Kiểm tra rebalance, thời gian poll, heartbeat và tình trạng downstream.
6. Sau khi xử lý, xác nhận committed offset tiến triển và lag giảm theo tốc độ dự kiến.

Không chỉ dựa vào tổng lag của cả topic. Một partition có thể bị nghẽn trong khi các partition khác xử lý nhanh, khiến tổng lag che khuất vấn đề. Cần xem theo partition và key distribution.

## 11. Reset offset có kiểm soát

Đôi khi đội vận hành cần phát lại dữ liệu sau khi sửa lỗi hoặc bỏ qua một đoạn record đã được xác định là không cần xử lý. Thay đổi committed offset có thể làm group đọc lại dữ liệu hoặc bỏ qua record, nên đây là thao tác vận hành có ảnh hưởng trực tiếp tới nghiệp vụ.

Trước khi reset offset, cần:

- Xác định chính xác group, topic và partition bị ảnh hưởng.
- Quyết định mục tiêu là replay từ offset cũ hơn hay bỏ qua đến offset mới hơn.
- Kiểm tra consumer group đã dừng hoặc không còn member đang hoạt động theo yêu cầu của công cụ reset.
- Dùng chế độ dry-run để xem offset dự kiến trước khi thực hiện.
- Xác nhận consumer xử lý idempotent nếu replay có thể lặp side effect.
- Ghi lại offset cũ và offset mới để có thể điều tra hoặc khôi phục quyết định.

Reset offset về quá khứ có thể tạo duplicate processing; reset tiến lên có thể bỏ qua record. Không dùng reset offset như cách chữa consumer lag thường xuyên nếu nguyên nhân thực sự là throughput, downstream hoặc rebalance. Sau khi reset, theo dõi tiến độ và đối soát kết quả nghiệp vụ.

## 12. Ví dụ vận hành: consumer restart giữa lúc xử lý

Giả sử group `billing-service` đang xử lý partition 0. Record offset `104` đã được đọc và cập nhật thành công vào database, nhưng process dừng trước khi commit offset `105`.

```text
Lần chạy thứ nhất:
  poll offset 104
       |
       v
  database transaction thành công
       |
       X process dừng trước commit

Lần chạy tiếp theo:
  group đọc committed offset cũ (104)
       |
       v
  record offset 104 được giao lại
       |
       v
  idempotency nhận biết event đã áp dụng
       |
       v
  commit offset 105
```

Đây là tình huống điển hình của at-least-once. Kafka bảo đảm record có thể được giao lại vì tiến độ chưa commit; ứng dụng cần đảm bảo việc áp dụng event lần hai không tạo thêm một khoản thanh toán hoặc một hóa đơn trùng. Inbox table với unique constraint trên `event_id` là một cách thực hiện: lưu event ID và cập nhật trạng thái nghiệp vụ trong cùng transaction database.

Nếu ứng dụng commit offset `105` trước khi cập nhật database và process dừng ngay sau commit, record sẽ không được giao lại theo tiến độ group, dù database chưa có thay đổi. Đây là lý do thời điểm commit phải phù hợp với semantics nghiệp vụ.

## 13. Checklist thiết kế consumer group bền vững

Khi đưa consumer vào production, đội ngũ cần thống nhất và kiểm chứng các điểm sau:

1. Mỗi luồng nghiệp vụ có `group.id` ổn định và đúng phạm vi chia sẻ dữ liệu.
2. Số partition và concurrency phù hợp với throughput mong muốn; không tăng consumer vượt khả năng partition hoặc downstream.
3. Hiểu rõ partition assignment, rebalance và nguyên nhân khiến group mất ổn định.
4. Tắt auto commit khi cần kiểm soát chặt thời điểm xác nhận; chọn acknowledgment mode phù hợp với cách listener xử lý.
5. Chỉ commit sau khi công việc được xem là hoàn tất; xử lý duplicate bằng idempotency khi dùng at-least-once.
6. Chọn `auto.offset.reset` có chủ đích cho group mới hoặc offset không còn hợp lệ.
7. Cấu hình poll interval, max poll records, session timeout và thời gian xử lý đồng bộ với nhau.
8. Theo dõi committed offset, log end offset, lag theo partition, rebalance và lỗi commit.
9. Có quy trình reset offset, replay và đối soát được kiểm soát.
10. Với side effect ngoài Kafka, thiết kế inbox/outbox hoặc cơ chế nhất quán phù hợp; không giả định Kafka transaction bao trùm database hay HTTP.

Consumer group quyết định ai chia nhau đọc partition; committed offset quyết định group sẽ tiếp tục đọc từ đâu. Khi thiết kế hai phần này cùng acknowledgment và xử lý idempotent, ứng dụng Spring Kafka có thể phục hồi sau restart, rebalance và lỗi downstream mà vẫn kiểm soát được duplicate, mất xử lý và độ trễ nghiệp vụ.
