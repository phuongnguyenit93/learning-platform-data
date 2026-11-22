# Rebalance khi scale out

Khi tăng số instance của một ứng dụng Spring Kafka, các consumer mới tham gia vào consumer group và Kafka phải phân phối lại partition cho các member. Quá trình này gọi là rebalance. Rebalance giúp tận dụng thêm consumer để tăng khả năng xử lý song song, nhưng cũng có thể làm gián đoạn việc đọc record trong lúc quyền sở hữu partition được chuyển giao.

Scale out chỉ cải thiện throughput khi topic có đủ partition, consumer hiện tại đang là nút thắt và các dependency phía sau còn năng lực tiếp nhận. Nếu số consumer vượt số partition, một số consumer sẽ không được gán partition. Nếu workload tập trung vào một key hoặc một partition, thêm instance cũng không làm partition nóng xử lý nhanh hơn.

Vận hành tốt cần dự đoán thời điểm rebalance, hiểu cơ chế gán partition, bảo đảm listener dừng và tiếp tục an toàn, đồng thời đo được thời gian gián đoạn và tác động đến consumer lag.

## 1. Consumer group và partition assignment

Một consumer group là tập hợp các consumer cùng chia sẻ việc đọc một hoặc nhiều topic. Trong một group, tại một thời điểm, mỗi partition được gán cho tối đa một consumer member. Nhiều group có thể đọc cùng một topic độc lập; mỗi group có offset riêng.

Giới hạn song song cơ bản được quyết định bởi số partition:

- Một partition trong một group chỉ có một consumer sở hữu tại một thời điểm.
- Một consumer có thể sở hữu nhiều partition.
- Nếu số consumer đang hoạt động lớn hơn số partition có thể được gán, consumer dư sẽ ở trạng thái không có partition.
- Tăng số consumer không tự động tăng số partition của topic.

Ví dụ topic có 12 partition:

| Số consumer trong group | Phân phối lý tưởng | Khả năng song song tối đa |
|---:|---|---:|
| 3 | Mỗi consumer nhận khoảng 4 partition | 12 partition |
| 4 | Mỗi consumer nhận khoảng 3 partition | 12 partition |
| 6 | Mỗi consumer nhận khoảng 2 partition | 12 partition |
| 12 | Mỗi consumer nhận 1 partition | 12 partition |
| 16 | 12 consumer có partition, 4 consumer không có partition | 12 partition |

Phân phối thực tế phụ thuộc partition assignor, subscription và số partition của tất cả topic mà group đăng ký. Bảng trên chỉ minh họa trường hợp một topic có 12 partition và các consumer có cùng subscription.

### 1.1. Consumer instance trong Spring Kafka

Với `@KafkaListener`, một listener container có thể tạo nhiều consumer bằng thuộc tính `concurrency`. Nếu ứng dụng chạy nhiều replica, tổng số consumer client có thể lớn hơn số pod:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        concurrency = "3")
public void consume(OrderCreated event) {
    billingService.handle(event);
}
~~~

Nếu triển khai 4 pod và mỗi pod chạy concurrency 3, group có thể có 12 consumer member. Khi scale từ 4 lên 6 pod, tổng số member tăng từ 12 lên 18. Với topic 12 partition, số consumer có partition vẫn tối đa là 12; sáu member còn lại không làm tăng mức song song của group.

Trong cấu hình thực tế, concurrency có thể được đặt trong annotation, listener container factory hoặc cấu hình Spring Boot tùy cách ứng dụng tạo container. Cần tính tổng số consumer từ tất cả listener container tham gia cùng group, không chỉ đếm số pod.

## 2. Điều gì xảy ra khi scale out?

Giả sử group hiện có ba consumer và topic có sáu partition. Khi thêm một instance mới, consumer mới khởi tạo Kafka client, tham gia group và gửi thông tin subscription. Group coordinator nhận biết thành viên thay đổi và khởi động quá trình rebalance.

Ở mức khái quát, quy trình diễn ra như sau:

~~~text
Trước scale out
  C1: P0, P1
  C2: P2, P3
  C3: P4, P5

       Thêm consumer C4
               |
               v
        Group rebalance
               |
               v
Sau khi phân phối lại
  C1: P0, P1
  C2: P2
  C3: P3
  C4: P4, P5
~~~

Đây là ví dụ minh họa, không phải kết quả assignment cố định. Assignor có thể chọn cách phân phối khác để cân bằng số partition, giữ assignment cũ hoặc giảm số partition phải di chuyển.

Trong lúc rebalance, các consumer có thể phải dừng nhận partition, hoàn tất hoặc xử lý phần công việc đang chạy theo semantics của container, commit offset phù hợp và bàn giao quyền sở hữu. Consumer mới chỉ bắt đầu xử lý partition sau khi được gán. Khoảng thời gian này có thể làm giảm throughput hoặc tạm thời ngừng đọc record.

### 2.1. Vì sao rebalance có thể gây gián đoạn?

Consumer group cần tránh hai member cùng được xem là chủ sở hữu hợp lệ của một partition trong cùng group. Khi membership thay đổi, Kafka phải phối hợp thu hồi và gán partition. Tùy assignor và giao thức group, việc này có thể yêu cầu thu hồi toàn bộ assignment hoặc chỉ chuyển những partition cần thiết.

Các yếu tố làm rebalance kéo dài:

- Consumer mất nhiều thời gian hoàn tất listener đang xử lý.
- Consumer không gọi `poll()` đủ thường xuyên.
- Coordinator hoặc broker phản hồi chậm.
- Có nhiều partition hoặc nhiều member trong group.
- Các member khởi động, dừng hoặc mất kết nối liên tục.
- Assignment strategy cần nhiều vòng trao đổi để chuyển partition.
- Ứng dụng đang rollout hoặc autoscaling tạo nhiều thay đổi membership cùng lúc.

Nếu rebalance xảy ra thường xuyên, consumer dành nhiều thời gian cho việc rời và tham gia group thay vì xử lý record. Consumer lag có thể tăng dù số instance đã tăng.

## 3. Phân biệt eager và cooperative rebalance

Partition assignor quyết định cách partition được phân phối giữa các member. Cách chuyển assignment ảnh hưởng trực tiếp đến phạm vi gián đoạn.

### 3.1. Eager rebalance

Với eager protocol, khi cần rebalance, các member thường phải thu hồi toàn bộ partition assignment trước khi assignment mới được hoàn tất. Điều này có thể tạo một khoảng dừng đọc rộng hơn, kể cả với partition không cần chuyển sang consumer khác.

Ưu điểm là mô hình chuyển giao đơn giản và tương thích với nhiều assignor cũ. Nhược điểm là thay đổi membership nhỏ cũng có thể khiến toàn bộ group bị gián đoạn trong quá trình phân phối lại.

### 3.2. Cooperative rebalance

Cooperative rebalance hỗ trợ chuyển partition theo từng phần. Các member chỉ thu hồi những partition cần chuyển; các partition không đổi có thể tiếp tục được giữ. Việc chuyển giao có thể cần nhiều vòng rebalance để hoàn tất.

Kafka cung cấp `CooperativeStickyAssignor`, kết hợp mục tiêu giữ assignment ổn định với giao thức cooperative. Khi group scale out, assignor cố gắng giữ partition ở consumer hiện tại nếu có thể và chỉ chuyển số partition cần thiết để đưa consumer mới vào hoạt động.

Có thể cấu hình trong Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Hoặc cấu hình trực tiếp ở Kafka consumer properties:

~~~java
props.put(
        ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
        CooperativeStickyAssignor.class.getName());
~~~

Tên class và API cần khớp với phiên bản Kafka client đang dùng. Khi chuyển một group từ eager assignor sang cooperative assignor, phải triển khai thay đổi theo kế hoạch tương thích. Các member cùng group cần dùng chiến lược assignment tương thích; trộn assignor cooperative và eager không tương thích có thể khiến group không thể hoàn tất rebalance đúng cách.

Cooperative rebalance giảm phạm vi partition phải dừng, nhưng không loại bỏ mọi gián đoạn. Consumer vẫn cần xử lý revoke/assign, hoàn tất công việc đang chạy và khôi phục trạng thái cần thiết cho partition mới.

## 4. Partition assignor và tác động đến scale out

Một số assignor phổ biến của Kafka:

| Assignor | Cách phân phối | Đặc điểm vận hành |
|---|---|---|
| `RangeAssignor` | Chia các partition theo dải cho từng consumer | Có thể tạo phân phối lệch giữa nhiều topic nếu số partition không đồng đều |
| `RoundRobinAssignor` | Luân phiên partition giữa các consumer | Có thể phân phối đều hơn khi subscription tương đồng |
| `StickyAssignor` | Cân bằng assignment và cố giữ partition cũ | Giảm thay đổi assignment không cần thiết, nhưng dùng eager protocol |
| `CooperativeStickyAssignor` | Giữ assignment ổn định và chuyển partition theo từng phần | Thường phù hợp khi muốn giảm gián đoạn do rebalance |

Không có assignor tối ưu cho mọi subscription. Nếu các consumer subscribe các tập topic khác nhau, kết quả assignment có thể khác đáng kể so với ví dụ một topic. Hãy quan sát partition được gán thực tế và đánh giá phân bố tải.

Với ứng dụng Spring Kafka, assignor được cấu hình qua Kafka consumer property `partition.assignment.strategy`. Hãy xác nhận tất cả instance trong cùng group đang dùng cấu hình tương thích sau mỗi lần rollout.

## 5. Tăng concurrency hay tăng số pod?

Hai cách scale có tác động khác nhau đến tài nguyên và vòng đời consumer.

**Tăng concurrency trong một pod** tạo thêm consumer client trong cùng tiến trình. Cách này có thể tận dụng nhiều CPU core và partition hơn mà không cần thêm pod. Tuy nhiên, các consumer chia sẻ CPU, heap, connection pool và tài nguyên downstream trong cùng instance.

**Tăng số pod** phân tán consumer qua nhiều tiến trình hoặc node. Cách này tăng khả năng chịu lỗi tiến trình và phân tán tài nguyên, nhưng tạo thêm network connection, consumer membership, tài nguyên cluster và có thể làm phát sinh rebalance khi pod mới tham gia.

Ví dụ với topic 24 partition:

| Cấu hình | Tổng consumer | Số consumer tối đa có partition | Ghi chú |
|---|---:|---:|---|
| 3 pod × concurrency 2 | 6 | 6 | Mỗi consumer có thể nhận khoảng 4 partition |
| 6 pod × concurrency 2 | 12 | 12 | Có thêm mức song song |
| 12 pod × concurrency 2 | 24 | 24 | Tối đa một consumer trên mỗi partition trong ví dụ một topic |
| 16 pod × concurrency 2 | 32 | 24 | 8 consumer dư không có partition |

Số consumer hữu ích còn phụ thuộc CPU, thời gian xử lý, kết nối database, API downstream và khả năng broker. Tăng concurrency quá nhanh có thể làm database connection pool cạn, tạo nhiều request đồng thời hoặc làm downstream quá tải.

### 5.1. Tính tổng consumer trước khi scale

Với một listener group đơn giản:

~~~text
Tổng consumer member
  = số pod
    x concurrency mỗi pod
~~~

Nếu có nhiều listener container tham gia cùng group, phải cộng tất cả consumer member của các container đó. Nếu các listener dùng group id khác nhau, mỗi group có assignment và lag độc lập.

Không dùng số pod làm đại diện cho số consumer khi concurrency lớn hơn một. Dashboard vận hành nên hiển thị cả pod count, consumer member count và số partition được gán.

## 6. Điều kiện để scale out thực sự tăng throughput

Scale out hữu ích khi consumer processing là bottleneck và topic có đủ partition để chia việc.

Trước khi tăng instance, kiểm tra:

1. Consumer lag có tăng liên tục hay chỉ tăng ngắn hạn theo burst?
2. Số partition có lớn hơn hoặc bằng số consumer mục tiêu không?
3. Các partition có phân bố record và key tương đối đều không?
4. Listener có bị chậm do database, HTTP API, lock hoặc xử lý CPU không?
5. Broker có đủ năng lực phục vụ thêm fetch request và network traffic không?
6. Downstream có chịu được mức concurrency mới không?

Nếu consumer đang chờ database, thêm consumer có thể làm tăng số truy vấn đồng thời và khiến database chậm hơn. Nếu một partition nhận phần lớn traffic, các consumer khác vẫn rảnh trong khi partition nóng trở thành giới hạn throughput.

### 6.1. Hot partition và key distribution

Kafka giữ thứ tự trong một partition. Các record có cùng key thường được định tuyến về cùng partition theo partitioner. Đây là cách phổ biến để giữ thứ tự cho một aggregate, ví dụ các sự kiện của cùng `orderId`.

Nếu một key hoặc một nhóm key chiếm phần lớn traffic, partition tương ứng có thể trở thành hot partition. Thêm consumer không thể chia một partition thành nhiều consumer trong cùng group. Hãy xem record rate, bytes in/out và lag theo từng partition.

Giải pháp có thể gồm:

- Sửa cách tạo key nếu yêu cầu thứ tự nghiệp vụ cho phép.
- Phân phối lại key hoặc thiết kế sharding cho aggregate nóng.
- Tách workload khác nhau sang topic hoặc group riêng.
- Tối ưu thời gian xử lý của record ở partition nóng.
- Tăng partition khi cần và chấp nhận đánh giá tác động đến key mapping.

Không thay key chỉ để cân bằng tải nếu điều đó làm hỏng thứ tự nghiệp vụ.

## 7. Tăng số partition có phải là scale out consumer?

Tăng partition và tăng consumer là hai thay đổi khác nhau.

- Tăng consumer làm thêm member tham gia cùng group để chia các partition hiện có.
- Tăng partition làm topic có thêm đơn vị song song và có thể cho phép nhiều consumer hơn có việc.
- Thay đổi partition count không phải là broker replica reassignment. Replica reassignment thay đổi vị trí bản sao partition giữa broker; consumer group rebalance thay đổi member sở hữu partition để đọc.

Nếu topic có 6 partition và cần 12 consumer hoạt động, tăng pod/concurrency lên 12 vẫn chỉ có tối đa 6 consumer nhận partition. Có thể cần tăng partition count, nhưng phải kiểm tra throughput broker, số file/partition, replication cost và yêu cầu thứ tự.

Việc tăng partition có thể thay đổi ánh xạ key sang partition đối với partitioner mặc định. Các record cũ của cùng key có thể nằm ở partition cũ, trong khi record mới được định tuyến sang partition khác. Vì Kafka chỉ giữ thứ tự trong từng partition, tăng partition có thể ảnh hưởng thứ tự xuyên suốt của một key trong giai đoạn chuyển đổi.

Không giảm partition count của topic hiện hữu như một thao tác scale thông thường. Nếu cần thay đổi cấu trúc lớn, hãy thiết kế topic mới và kế hoạch chuyển dữ liệu có kiểm soát.

## 8. Các nguyên nhân thường kích hoạt rebalance

Scale out là một nguyên nhân, nhưng rebalance cũng có thể xuất hiện khi consumer mất kết nối, poll quá chậm hoặc topic metadata thay đổi.

| Nguyên nhân | Điều gì xảy ra | Cách điều tra |
|---|---|---|
| Thêm consumer | Member mới tham gia group | Đối chiếu thời điểm scale với group membership log |
| Dừng hoặc crash consumer | Member rời group hoặc heartbeat mất | Kiểm tra exit code, pod restart và log shutdown |
| `max.poll.interval.ms` bị vượt | Consumer bị xem là không tiến triển poll | Đo thời gian xử lý batch và poll gap |
| Session timeout | Coordinator không nhận heartbeat trong thời gian cho phép | Kiểm tra network, GC pause, CPU starvation và timeout |
| Topic/partition thay đổi | Assignment cần cập nhật metadata | Kiểm tra thao tác tạo topic hoặc tăng partition |
| Subscription thay đổi | Member đăng ký tập topic khác | Kiểm tra pattern subscription và cấu hình |
| Rolling deployment | Nhiều member dừng và khởi động | Kiểm tra tốc độ rollout và shutdown grace period |

Không nên tăng `session.timeout.ms` hoặc `max.poll.interval.ms` một cách tùy tiện để che rebalance. Cần xác định nguyên nhân consumer không heartbeat hoặc không poll đúng hạn trước khi thay đổi timeout.

## 9. `poll()`, xử lý listener và timeout

Kafka consumer cần tiếp tục gọi `poll()` trong giới hạn `max.poll.interval.ms`. Nếu ứng dụng xử lý một batch quá lâu trước lần poll tiếp theo, consumer có thể rời group và partition được gán cho member khác.

Các thuộc tính thường cần phối hợp:

| Thuộc tính | Vai trò | Điều cần lưu ý |
|---|---|---|
| `max.poll.records` | Số record tối đa trả về mỗi lần poll | Batch lớn có thể kéo dài thời gian xử lý |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần poll trước khi consumer bị xem là không tiến triển | Phải lớn hơn thời gian xử lý batch trong tình huống chậm có thể dự đoán |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi xem member mất | Liên quan đến phát hiện member mất kết nối |
| `heartbeat.interval.ms` | Tần suất heartbeat trong classic group protocol | Thường phải nhỏ hơn session timeout theo quy tắc của Kafka |

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        "[max.poll.records]": 50
        "[max.poll.interval.ms]": 300000
        "[session.timeout.ms]": 30000
        "[heartbeat.interval.ms]": 10000
~~~

Đây là giá trị minh họa cho classic consumer group protocol. Phiên bản Kafka client/broker và group protocol đang dùng có thể ảnh hưởng cách cấu hình heartbeat và timeout; hãy đối chiếu tài liệu của phiên bản triển khai.

Nếu một record có thể mất nhiều phút để xử lý, tăng `max.poll.interval.ms` có thể giảm nguy cơ bị loại khỏi group trong lúc xử lý, nhưng cũng kéo dài thời gian phát hiện consumer thực sự bị treo. Một thiết kế khác là giới hạn thời gian xử lý, chia nhỏ công việc hoặc đưa phần việc dài vào một workflow có trạng thái bền vững. Không ack record trước khi công việc đã được lưu an toàn.

## 10. Xử lý revoke và assign trong Spring Kafka

Spring Kafka cung cấp listener hook để ứng dụng phản ứng khi partition bị thu hồi hoặc được gán. `ConsumerAwareRebalanceListener` cho phép thực hiện thao tác trước và sau quá trình revoke/assign, tùy callback:

~~~java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {
            @Override
            public void onPartitionsRevokedBeforeCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {
                log.info("Partitions revoked before commit: {}", partitions);
            }

            @Override
            public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {
                log.info("Partitions assigned: {}", partitions);
            }
        });
~~~

Đoạn code minh họa cách đăng ký listener trên `ContainerProperties` của listener container factory. Các import, kiểu factory và vị trí cấu hình phụ thuộc cách ứng dụng tạo container và phiên bản Spring Kafka.

Trong callback revoke, ứng dụng có thể:

- Dừng nhận thêm công việc cho partition sắp mất.
- Hoàn tất hoặc hủy an toàn công việc đang chạy theo thiết kế.
- Flush trạng thái hoặc checkpoint ứng dụng nếu cần.
- Ghi log partition và thời điểm bàn giao.

Trong callback assigned, ứng dụng có thể:

- Khởi tạo state hoặc cache gắn với partition.
- Khôi phục checkpoint ứng dụng.
- Ghi nhận thời điểm consumer bắt đầu sở hữu partition.
- Tiếp tục xử lý record sau khi assignment hoàn tất.

Callback rebalance không phải nơi phù hợp để thực hiện một công việc mạng kéo dài. Nếu callback block quá lâu, chính quá trình rebalance có thể bị kéo dài. Chỉ thực hiện thao tác ngắn, có timeout rõ ràng và có khả năng phục hồi.

### 10.1. Tránh xử lý bất đồng bộ không được quản lý

Một lỗi thiết kế phổ biến là listener đẩy record vào executor rồi trả về ngay. Container có thể xem listener thành công và commit offset trong khi công việc bất đồng bộ chưa hoàn tất. Nếu partition bị revoke hoặc pod dừng, công việc đó có thể bị mất.

Nếu dùng executor:

- Quản lý số lượng công việc đang chạy theo partition.
- Không ack/commit trước khi công việc được lưu hoặc hoàn tất theo cam kết.
- Khi revoke, ngừng nhận việc mới và xử lý phần việc đang chạy theo thời hạn.
- Giữ idempotency vì record vẫn có thể được giao lại sau sự cố.
- Tránh giữ thread consumer quá lâu trong callback hoặc chờ executor vô hạn.

## 11. Cooperative rebalance trong rollout và autoscaling

Cooperative assignor có thể giảm phạm vi gián đoạn khi thêm hoặc bớt member. Tuy nhiên, autoscaling vẫn nên có tốc độ thay đổi hợp lý.

Khi scale out:

1. Xác nhận lag thực sự cần thêm năng lực xử lý.
2. Kiểm tra số partition còn có thể phân phối.
3. Tăng replica theo từng bước phù hợp với thời gian khởi động và rebalance.
4. Theo dõi số member, assignment, rebalance duration và lag.
5. Xác nhận consumer mới đã nhận partition và có processing rate.
6. Dừng scale khi số consumer đã đạt giới hạn song song hoặc downstream bắt đầu quá tải.

Khi scale in:

1. Tránh giảm nhiều pod cùng lúc nếu group đang xử lý backlog lớn.
2. Cho phép container dừng có kiểm soát.
3. Đảm bảo thời gian grace period đủ cho listener hoàn tất phần việc đang chạy.
4. Theo dõi partition revoke, commit và rebalance.
5. Xác nhận consumer còn lại xử lý được incoming rate sau khi scale in.

Một HPA chỉ dựa trên CPU có thể scale sai: consumer đang chờ database có thể dùng ít CPU nhưng lag vẫn tăng. Ngược lại, CPU cao có thể do serialization hoặc GC mà thêm consumer làm tổng tải tăng. Có thể dùng consumer lag, processing rate và tuổi record cũ nhất làm tín hiệu scale, nhưng cần smoothing, cooldown và giới hạn replica để tránh dao động.

## 12. Static membership và giảm rebalance do restart

Static membership cho phép consumer có một `group.instance.id` ổn định. Khi một member tạm thời mất kết nối rồi quay lại với cùng identity trong khoảng thời gian phù hợp, group có thể giữ hoặc khôi phục assignment mà không phải xử lý membership như một member hoàn toàn mới.

Static membership hữu ích trong môi trường có restart hoặc rolling deployment thường xuyên. Nó có thể giảm rebalance không cần thiết, nhưng không làm cho mọi thay đổi scale out trở nên không cần rebalance.

Các nguyên tắc khi dùng:

- Mỗi consumer member cần một `group.instance.id` duy nhất trong group.
- Identity phải ổn định qua lần restart của cùng instance.
- Không dùng cùng một id cho nhiều pod đang chạy đồng thời.
- Cân nhắc session timeout vì coordinator có thể chờ static member quay lại trước khi phân phối partition.
- Khi tăng số pod, cấp identity mới cho member mới.

Với Spring Kafka và listener container có concurrency, cần xác nhận cách framework tạo identity riêng cho từng child consumer. Không tự ghép id chỉ theo tên service nếu nhiều consumer trong cùng pod sẽ bị trùng.

Static membership có thể làm thời gian phát hiện member thực sự mất dài hơn tùy timeout. Nếu pod bị mất vĩnh viễn, partition có thể phải chờ timeout trước khi được gán cho member khác. Hãy cân bằng giữa giảm rebalance do restart ngắn và thời gian phục hồi khi instance biến mất thật.

## 13. Graceful shutdown khi scale in

Khi orchestrator dừng pod, ứng dụng thường nhận tín hiệu termination. Spring Kafka listener container cần có thời gian dừng consumer, hoàn tất record đang xử lý và commit offset theo cấu hình. Nếu tiến trình bị kill trước khi hoàn tất, record có thể được giao lại.

Để shutdown có kiểm soát:

- Đặt `terminationGracePeriodSeconds` đủ dài cho thời gian xử lý lớn nhất có thể chấp nhận.
- Cấu hình readiness để instance ngừng nhận traffic mới trước khi shutdown nếu kiến trúc cần.
- Đảm bảo listener container được dừng trước khi các dependency như database connection pool bị đóng.
- Không để shutdown hook chờ vô hạn.
- Bảo đảm consumer idempotent vì một số record vẫn có thể được giao lại.
- Theo dõi số record đang xử lý và thời gian shutdown.

Với Spring Kafka, container có thể được quản lý bởi Spring lifecycle. Cần thử nghiệm hành vi thực tế khi gửi SIGTERM, đặc biệt với listener xử lý lâu, batch listener và manual acknowledgement. Thời gian shutdown của ứng dụng và thời gian grace period của nền tảng phải phối hợp với nhau.

## 14. Đo lường rebalance và hiệu quả scale out

Không đánh giá thành công chỉ bằng số pod mới đã chạy. Cần xác nhận consumer group đã ổn định và throughput thực sự tăng.

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Consumer group member count | Số member tham gia group | Xác nhận scale out đã thêm consumer |
| Assigned partitions/member | Số partition mỗi consumer sở hữu | Phát hiện member dư hoặc assignment lệch |
| Rebalance count/rate | Số lần group rebalance | Phát hiện membership dao động |
| Rebalance duration | Thời gian từ khi bắt đầu đến khi assignment ổn định | Đo gián đoạn do scale |
| Consumer lag | Số record còn chờ theo partition/group | Đánh giá backlog |
| Oldest record age | Tuổi của record chưa xử lý lâu nhất | Liên hệ lag với SLA nghiệp vụ |
| Records consumed rate | Tốc độ xử lý thực tế | Xác nhận throughput có tăng |
| Listener processing duration | Thời gian xử lý mỗi record/batch | Tìm bottleneck ở nghiệp vụ |
| Poll interval / max poll gap | Khoảng cách giữa các lần poll | Phát hiện nguy cơ vượt `max.poll.interval.ms` |

Nên theo dõi lag theo từng partition thay vì chỉ xem tổng group. Tổng lag có thể giảm trong khi một partition nóng vẫn tăng. Cũng cần phân biệt lag count với record age: record age phản ánh gần hơn độ trễ người dùng có thể cảm nhận.

### 14.1. Xác định scale out có hiệu quả

So sánh trước và sau scale trong cùng điều kiện tải:

- Consumer processing rate có tăng không?
- Lag và tuổi record cũ nhất có giảm không?
- Listener p95/p99 có thay đổi không?
- Rebalance có làm throughput giảm trong thời gian đáng kể không?
- Database/API downstream có tăng latency hoặc error không?
- Có member nào không được gán partition không?

Nếu số consumer tăng nhưng processing rate không tăng, hãy kiểm tra partition limit, hot partition, broker bottleneck và downstream. Nếu lag giảm trong vài phút rồi tăng trở lại, năng lực mới có thể chưa đủ cho incoming rate hoặc autoscaler đang dao động.

## 15. Runbook khi scale out gây rebalance kéo dài

### 15.1. Consumer mới tham gia nhưng group không ổn định

1. Kiểm tra log group coordinator và member id.
2. Xác nhận tất cả instance có cùng `group.id` và subscription tương thích.
3. Kiểm tra partition assignment strategy có đồng nhất và tương thích không.
4. Kiểm tra consumer có vượt `max.poll.interval.ms` hoặc mất heartbeat không.
5. Xem pod restart, CPU throttling, GC pause và network interruption.
6. Nếu vừa đổi assignor, xác nhận rollout tuân theo kế hoạch chuyển đổi tương thích.

### 15.2. Scale out nhưng consumer mới không nhận partition

1. Đếm partition của topic và tổng consumer member trong group.
2. Kiểm tra subscription của consumer mới.
3. Xem assignment hiện tại và trạng thái member.
4. Xác định có consumer dư do tổng concurrency vượt partition count không.
5. Kiểm tra assignor và log lỗi assignment.

Nếu số consumer đã bằng hoặc lớn hơn số partition, consumer mới không nhất thiết nhận partition. Hãy xem xét tăng partition sau khi đánh giá key mapping và năng lực broker.

### 15.3. Lag tăng ngay sau khi scale

1. Xem rebalance duration và thời gian group ổn định.
2. Kiểm tra processing rate trong và sau rebalance.
3. So sánh lag từng partition để phát hiện hot partition.
4. Kiểm tra downstream có bị quá tải do concurrency tăng không.
5. Kiểm tra batch processing và thời gian giữa các lần poll.
6. Giảm tốc độ scale hoặc concurrency nếu downstream đang bị áp lực.

### 15.4. Rebalance lặp lại sau rolling deployment

1. Kiểm tra thời điểm dừng/khởi động pod và số member thay đổi đồng thời.
2. Xác nhận shutdown grace period và listener container stop behavior.
3. Kiểm tra static membership nếu đang sử dụng, đặc biệt identity trùng hoặc timeout.
4. Xem xét cooperative assignor để giảm phạm vi thu hồi partition.
5. Điều chỉnh rollout maxUnavailable/maxSurge hoặc cooldown để giới hạn số member thay đổi cùng lúc.

## 16. Kiểm thử scale out trước production

Một bài kiểm thử hữu ích cần có tải liên tục trong lúc thay đổi số consumer. Chỉ scale khi topic rảnh sẽ không cho thấy tác động đến backlog và SLA.

Kịch bản đề xuất:

1. Tạo topic có số partition đại diện cho production và phát record với key phân bố thực tế.
2. Chạy group với số consumer ban đầu, đo processing rate, lag, record age và rebalance.
3. Thêm consumer theo từng bước; ghi lại thời điểm member tham gia và assignment ổn định.
4. So sánh eager assignor với cooperative assignor trong môi trường test nếu đang cân nhắc chuyển đổi.
5. Dừng một consumer đang xử lý record để kiểm tra revoke, commit và redelivery.
6. Thử scale in và gửi SIGTERM để kiểm tra graceful shutdown.
7. Làm chậm database hoặc API downstream để xác định giới hạn concurrency.
8. Xác nhận không mất record và duplicate không tạo tác động nghiệp vụ lặp.

Kết quả cần có thời gian rebalance, thời gian khôi phục throughput, lag peak, tuổi record cũ nhất và số record được xử lý lại. Các giá trị này giúp thiết lập autoscaling cooldown và shutdown grace period.

## 17. Checklist scale out consumer group

### Trước khi tăng instance

- [ ] Consumer lag hoặc record age cho thấy cần thêm năng lực xử lý.
- [ ] Đã tính tổng consumer member từ pod count và listener concurrency.
- [ ] Topic có đủ partition cho số consumer mục tiêu.
- [ ] Key distribution không tạo hot partition nghiêm trọng.
- [ ] Database, API downstream, CPU và broker còn năng lực.
- [ ] Assignment strategy tương thích giữa tất cả member.

### Trong khi scale

- [ ] Tăng replica theo từng bước có kiểm soát.
- [ ] Theo dõi member count, partition assignment và rebalance duration.
- [ ] Theo dõi lag theo group và từng partition.
- [ ] Theo dõi listener duration, poll gap và downstream latency.
- [ ] Dừng scale khi đã đạt partition parallelism hoặc downstream quá tải.

### Sau khi scale

- [ ] Group đã ổn định và consumer mới có partition được gán.
- [ ] Processing rate tăng theo kỳ vọng.
- [ ] Consumer lag và tuổi record cũ nhất trở về trong SLO.
- [ ] Không có rebalance lặp lại hoặc member bị loại do timeout.
- [ ] Duplicate delivery không tạo tác động nghiệp vụ lặp.
- [ ] Cấu hình autoscaling và cooldown phản ánh kết quả đo thực tế.

## Kết luận

Scale out Spring Kafka làm consumer mới tham gia group và kích hoạt rebalance để phân phối lại partition. Mức song song tối đa bị giới hạn bởi số partition; tăng pod hoặc concurrency vượt giới hạn này không tạo thêm consumer có việc. Cooperative sticky assignment, static membership, poll timeout hợp lý và graceful shutdown có thể giảm gián đoạn do thay đổi membership. Để chứng minh scale out có ích, hãy đo rebalance duration, assignment, processing rate, consumer lag và tuổi record cũ nhất, đồng thời kiểm tra năng lực downstream. Khi scale được thực hiện theo từng bước và có dữ liệu xác nhận, hệ thống có thể tăng throughput mà vẫn giữ được khả năng xử lý lại an toàn khi partition được chuyển giao.
