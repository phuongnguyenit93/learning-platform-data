# Khởi động lại consumer từ offset nào

## Mục tiêu của bài học

Trong chương **Consumer**, bài này giải thích Kafka chọn vị trí đọc nào khi consumer khởi động lần đầu, khởi động lại sau sự cố hoặc tham gia lại consumer group. Trọng tâm là committed offset, consumer position và thuộc tính auto.offset.reset.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Việc hiểu đúng offset giúp consumer phục hồi sau restart mà không vô tình bỏ qua dữ liệu hoặc đọc lại quá nhiều bản ghi.

Sau bài học, người học có thể:

- Phân biệt offset đã commit với vị trí đọc hiện tại của consumer.
- Giải thích Kafka khôi phục tiến độ theo consumer group như thế nào.
- Cấu hình auto.offset.reset bằng earliest, latest hoặc none.
- Hiểu vì sao auto.offset.reset không ghi đè offset đã commit mỗi lần ứng dụng restart.
- Nhận diện ảnh hưởng của group.id, retention, partition mới và rebalance.
- Cấu hình acknowledgment/commit phù hợp trong Spring Kafka.
- Chủ động seek hoặc reset offset khi cần replay dữ liệu.

## 1. Consumer đọc tiếp từ đâu?

Kafka lưu bản ghi theo topic và partition. Mỗi bản ghi trong một partition có offset xác định. Consumer đọc các bản ghi theo thứ tự offset trong partition được gán.

Khi consumer xử lý một bản ghi, có hai khái niệm cần phân biệt:

- **Consumer position:** vị trí tiếp theo mà consumer sẽ đọc trong phiên làm việc hiện tại.
- **Committed offset:** vị trí đã được consumer group lưu bền vững để có thể tiếp tục sau khi consumer dừng, restart hoặc partition được giao cho consumer khác.

Committed offset được lưu theo cặp consumer group và topic-partition. Nó không phải một offset chung cho toàn bộ topic.

Ví dụ, consumer đọc partition 0:

~~~text
Offset:             40   41   42   43   44   45
                    |    |    |    |    |    |
Consumer đã xử lý:  ✓    ✓
Committed offset:        42
Vị trí đọc tiếp:              42
~~~

Nếu consumer đã xử lý record offset 41 và commit offset 42, giá trị 42 biểu thị vị trí tiếp theo cần đọc. Khi consumer khởi động lại với cùng group, Kafka có thể tiếp tục từ offset 42.

Do đó, khi nói “consumer restart từ offset nào”, cần xác định offset đã commit gần nhất cho từng partition. Không thể chỉ nhìn một giá trị offset chung cho cả topic.

## 2. Kafka lưu tiến độ theo consumer group

Mỗi consumer group có một định danh group.id. Kafka quản lý tiến độ đọc riêng cho từng group và từng partition.

Ví dụ topic commerce.order.created có 3 partition và hai consumer group:

~~~text
Topic: commerce.order.created

Group: billing-service
  partition 0 -> committed offset 120
  partition 1 -> committed offset 95
  partition 2 -> committed offset 210

Group: analytics-service
  partition 0 -> committed offset 80
  partition 1 -> committed offset 95
  partition 2 -> committed offset 175
~~~

Hai group có thể đọc cùng một topic nhưng giữ tiến độ độc lập. Consumer của billing-service restart sẽ tiếp tục theo offset đã commit của billing-service; nó không dùng offset của analytics-service.

Kafka lưu consumer offsets trong topic nội bộ __consumer_offsets. Ứng dụng không cần tự ghi file offset hoặc lưu offset vào biến trong bộ nhớ để phục hồi tiến độ thông thường.

### 2.1. Giữ nguyên group.id khi restart

Nếu ứng dụng restart với cùng group.id và các partition vẫn thuộc cùng group, Kafka sử dụng committed offset hợp lệ đã lưu cho từng partition.

Ví dụ:

- Trước khi dừng, billing-service đã commit offset 500 của partition 0.
- Ứng dụng được triển khai lại với cùng group.id là billing-service.
- Consumer tham gia group và nhận partition 0.
- Consumer tiếp tục đọc từ vị trí 500.

Thuộc tính auto.offset.reset không ghi đè offset 500 chỉ vì ứng dụng vừa restart.

### 2.2. Đổi group.id tạo tiến độ đọc độc lập

Nếu đổi group.id từ billing-service thành billing-service-v2, Kafka xem đây là consumer group khác. Group mới chưa có committed offset của các partition đó, nên chính sách auto.offset.reset có thể được áp dụng.

Đây là lý do một ứng dụng có thể đọc lại dữ liệu cũ sau khi đổi group.id dù topic và mã xử lý không thay đổi.

Không nên đổi group.id trong mỗi lần deploy nếu mục tiêu là tiếp tục tiến độ của group hiện tại. Nếu cần một luồng đọc độc lập, tạo group mới là hành vi có chủ đích.

## 3. auto.offset.reset quyết định điều gì?

auto.offset.reset là cấu hình của Kafka consumer. Nó xác định vị trí bắt đầu khi consumer group không có committed offset hợp lệ cho một partition hoặc offset đã commit không còn nằm trong phạm vi offset mà broker có thể phục vụ.

Ba lựa chọn phổ biến:

| Giá trị | Hành vi | Trường hợp sử dụng |
|---|---|---|
| earliest | Đọc từ offset sớm nhất còn được giữ trong partition | Muốn xử lý lại dữ liệu đang còn retention |
| latest | Bắt đầu từ cuối partition và chờ bản ghi mới | Chỉ quan tâm dữ liệu phát sinh sau khi group bắt đầu |
| none | Phát sinh lỗi nếu không có offset hợp lệ | Muốn ứng dụng dừng để người vận hành quyết định rõ vị trí |

### 3.1. earliest

Với earliest, khi group chưa có offset hợp lệ, consumer bắt đầu từ offset nhỏ nhất hiện còn được broker giữ lại.

Ví dụ partition có các offset còn tồn tại từ 100 đến 150:

~~~text
Offset còn lưu: 100 ... 150
Group chưa có committed offset
auto.offset.reset=earliest

Vị trí bắt đầu: 100
~~~

earliest không có nghĩa luôn đọc từ offset 0. Nếu retention đã xóa các segment cũ và log start offset hiện tại là 100, consumer chỉ có thể bắt đầu từ 100.

Lựa chọn này phù hợp với consumer mới cần xử lý dữ liệu lịch sử còn lưu, consumer analytics hoặc môi trường thử nghiệm muốn đọc lại topic.

### 3.2. latest

Với latest, khi group chưa có offset hợp lệ, consumer bắt đầu từ cuối partition tại thời điểm xác lập vị trí ban đầu và chờ bản ghi mới.

Ví dụ:

~~~text
Các offset đang có: 100 ... 150
Group chưa có committed offset
auto.offset.reset=latest

Vị trí ban đầu: cuối partition
Bản ghi mới sau đó: tiếp tục được đọc
~~~

Consumer không đọc lại các bản ghi lịch sử đang có trong partition khi áp dụng latest cho group mới. Đây là lựa chọn phù hợp với luồng chỉ cần xử lý sự kiện phát sinh từ lúc consumer bắt đầu theo dõi.

Cần cẩn thận khi triển khai consumer mới với latest: nếu ứng dụng cần dữ liệu lịch sử để dựng trạng thái ban đầu, các bản ghi trước thời điểm bắt đầu có thể bị bỏ qua đối với group đó.

### 3.3. none

Với none, consumer không tự chọn earliest hoặc latest khi thiếu offset hợp lệ. Kafka phát sinh lỗi, thường là NoOffsetForPartitionException, để ứng dụng hoặc người vận hành xử lý rõ ràng.

Lựa chọn này phù hợp khi việc tự chọn điểm bắt đầu có thể gây hậu quả nghiệp vụ, ví dụ xử lý tài chính hoặc migration cần kiểm soát offset.

none không có nghĩa Kafka tự khôi phục offset. Ứng dụng phải cung cấp offset hợp lệ hoặc người vận hành cần reset group trước khi consumer tiếp tục.

### 3.4. Phân biệt vị trí bắt đầu và phạm vi dữ liệu còn lưu

earliest chỉ đọc từ offset sớm nhất còn tồn tại. Nó không khôi phục dữ liệu đã bị xóa bởi retention, compaction hoặc thao tác quản trị.

latest cũng không xóa bản ghi cũ. Nó chỉ quyết định vị trí đọc ban đầu cho partition chưa có offset hợp lệ.

auto.offset.reset là chính sách chọn vị trí đọc, không phải chính sách xóa dữ liệu hoặc thay đổi retention của topic.

## 4. Khi nào auto.offset.reset được áp dụng?

Cấu hình này thường được dùng trong các trường hợp sau:

1. Consumer group mới chưa từng commit offset cho partition.
2. Group đã tồn tại nhưng được gán một partition mới chưa có committed offset.
3. Offset đã commit không còn hợp lệ vì log start offset đã tiến lên sau retention hoặc dữ liệu partition bị thay đổi.
4. Consumer yêu cầu một offset ngoài phạm vi mà broker có thể phục vụ.

Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ offset đó. Đây là quy tắc quan trọng nhất khi phân tích hành vi restart.

### 4.1. Ví dụ với group mới

Topic có partition 0 chứa offset 0 đến 999. Group billing-v1 chưa từng đọc topic.

- earliest: bắt đầu từ offset sớm nhất còn lưu, trong ví dụ là 0.
- latest: bắt đầu ở cuối partition, sau các bản ghi hiện có.
- none: báo lỗi do group chưa có offset hợp lệ.

### 4.2. Ví dụ với group đã có offset

Group billing-service đã commit offset 700 và partition vẫn còn offset 0 đến 999.

Dù cấu hình auto.offset.reset là earliest hay latest, consumer vẫn tiếp tục từ 700. Chính sách reset không được dùng vì committed offset vẫn hợp lệ.

### 4.3. Ví dụ offset đã bị retention loại bỏ

Group đã commit offset 100, nhưng retention xóa các segment cũ và log start offset của partition hiện là 300.

Committed offset 100 nằm ngoài phạm vi có thể đọc. Khi consumer phát hiện offset không còn hợp lệ, auto.offset.reset được áp dụng:

- earliest: chuyển về offset 300, là offset sớm nhất còn lưu.
- latest: chuyển tới cuối partition.
- none: dừng với lỗi để yêu cầu can thiệp.

Nếu dùng earliest trong tình huống này, consumer vẫn đã mất khả năng đọc các bản ghi 100 đến 299 vì broker không còn lưu chúng. Cần theo dõi retention và consumer lag để tránh mất cửa sổ dữ liệu có thể replay.

## 5. Cấu hình trong Spring Boot và Spring Kafka

Có thể cấu hình group ID và auto.offset.reset trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
~~~

Ý nghĩa:

- bootstrap-servers: địa chỉ broker mà consumer kết nối.
- group-id: tên consumer group dùng để lưu tiến độ đọc.
- auto-offset-reset: chính sách khi group chưa có offset hợp lệ.
- enable-auto-commit: false: để Spring Kafka listener container quản lý commit theo acknowledgment mode.

Trong Spring Kafka, listener container thường quản lý offset thay cho auto commit của Kafka consumer khi enable.auto.commit chưa được bật rõ ràng. Đặt false tường minh giúp cấu hình thể hiện rõ ý định và tránh commit theo timer độc lập với quá trình xử lý listener.

Có thể cấu hình trực tiếp trong @KafkaListener:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    // Xử lý sự kiện đơn hàng.
}
~~~

groupId trong annotation có thể xác định group cho listener và ghi đè group ID mặc định từ consumer factory cho endpoint đó. Hãy bảo đảm group ID ổn định qua các lần deploy nếu muốn tiếp tục tiến độ cũ.

### 5.1. Đổi auto.offset.reset có làm consumer đọc lại từ đầu không?

Không, nếu group vẫn có committed offset hợp lệ.

Ví dụ trước đây cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      auto-offset-reset: latest
~~~

Group đã commit offset 500. Sau đó đổi thành:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
~~~

Consumer vẫn tiếp tục từ offset 500. Muốn đọc lại từ đầu cần reset committed offset hoặc dùng group ID mới chưa có tiến độ, đồng thời chọn earliest.

### 5.2. Group ID thay đổi theo môi trường

Nếu group ID được tạo từ tên ứng dụng cộng environment, hãy giữ quy tắc ổn định:

~~~text
billing-service-dev
billing-service-staging
billing-service-prod
~~~

Mỗi group có tiến độ riêng. Không dùng một group ID khác nhau mỗi lần chạy local nếu muốn tiếp tục offset của lần chạy trước. Ngược lại, dùng chung group ID cho nhiều instance của cùng một ứng dụng là cách phổ biến để các instance chia sẻ partition.

## 6. Offset commit và acknowledgment trong Spring Kafka

Việc restart từ offset nào phụ thuộc trực tiếp vào thời điểm offset được commit.

Kafka consumer có thể đã đọc một bản ghi và tăng consumer position trong bộ nhớ, nhưng điều đó không đồng nghĩa group đã lưu tiến độ mới. Nếu ứng dụng dừng trước khi commit, bản ghi có thể được giao lại sau khi restart hoặc rebalance.

### 6.1. AckMode trong Spring Kafka

Spring Kafka cung cấp các chế độ acknowledgment cho listener container:

| AckMode | Cách hoạt động khái quát |
|---|---|
| RECORD | Commit sau khi listener xử lý xong từng record |
| BATCH | Commit sau khi tất cả record của lần poll được xử lý xong |
| TIME | Commit khi đã qua khoảng thời gian cấu hình và các record tương ứng đã được xử lý |
| COUNT | Commit khi đạt số record cấu hình |
| COUNT_TIME | Kết hợp điều kiện thời gian và số record |
| MANUAL | Listener chủ động acknowledge; container thực hiện commit theo semantics của chế độ |
| MANUAL_IMMEDIATE | Yêu cầu commit ngay khi acknowledge được gọi trên consumer thread |

BATCH là chế độ mặc định phổ biến của listener container. Cần kiểm tra cấu hình thực tế của container/factory nếu ứng dụng tùy chỉnh acknowledgment.

### 6.2. Ví dụ RECORD

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Với RECORD, sau khi listener xử lý thành công một record, container có thể commit offset tương ứng theo cấu hình. Nếu listener ném exception, việc commit phụ thuộc error handler và chính sách xử lý lỗi.

### 6.3. Ví dụ MANUAL

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "manualAckListenerFactory"
)
public void handle(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.process(event);

    acknowledgment.acknowledge();
}
~~~

Factory cần được cấu hình AckMode.MANUAL hoặc MANUAL_IMMEDIATE tương ứng. Chỉ acknowledge sau khi công việc nghiệp vụ cần thiết đã hoàn tất.

Nếu acknowledge trước khi ghi database thành công, consumer có thể commit offset rồi dừng; khi khởi động lại, Kafka không giao lại record đó dù nghiệp vụ chưa hoàn tất. Nếu xử lý xong nhưng chưa commit, record có thể được giao lại và cần idempotency.

### 6.4. Commit offset không phải commit database

Kafka offset commit và transaction database là hai thao tác khác nhau. Nếu listener cập nhật database rồi commit offset, sự cố giữa hai thao tác có thể khiến bản ghi được giao lại. Nếu commit offset trước khi cập nhật database, sự cố có thể làm mất cơ hội xử lý lại.

Vì vậy, listener nên thiết kế idempotent hoặc dùng mô hình tích hợp phù hợp như Inbox/Outbox khi cần phối hợp Kafka với database.

## 7. Điều gì xảy ra khi consumer restart?

Giả sử listener xử lý partition 0 theo thứ tự:

~~~text
Đã xử lý: offset 40, 41
Đã commit: offset 42
Chưa xử lý: offset 42, 43, 44
~~~

Khi tiến trình bị dừng:

1. Consumer rời group hoặc bị phát hiện không còn hoạt động.
2. Kafka có thể rebalance và phân phối partition cho consumer khác.
3. Khi consumer mới nhận partition, nó lấy committed offset của group.
4. Consumer tiếp tục từ vị trí offset 42 nếu offset còn hợp lệ.
5. Nếu không có offset hợp lệ, auto.offset.reset được áp dụng.

~~~mermaid
sequenceDiagram
    participant A as Consumer instance
    participant K as Kafka group coordinator
    participant O as __consumer_offsets
    participant B as Broker partition

    A->>B: Poll records
    B-->>A: Offset 40, 41
    A->>A: Xử lý record
    A->>K: Commit offset 42
    K->>O: Lưu committed offset
    Note over A: Process restart
    A->>K: Join consumer group
    K->>O: Đọc offset đã lưu
    O-->>K: Offset 42
    K-->>A: Assign partition và offset 42
    A->>B: Poll từ offset 42
    B-->>A: Record tiếp theo
~~~

Committed offset thể hiện vị trí tiếp theo cần đọc. Nếu broker có khoảng trống offset do compaction hoặc record control, record thực tế tiếp theo có thể có offset lớn hơn giá trị committed.

## 8. Rebalance và partition mới

Rebalance xảy ra khi thành viên consumer group thay đổi hoặc subscription/assignment thay đổi. Một partition có thể được giao cho consumer khác, nhưng tiến độ vẫn thuộc về group chứ không thuộc riêng instance.

Khi consumer mới nhận partition:

- Nếu group có committed offset hợp lệ, consumer dùng offset đó.
- Nếu group chưa có offset cho partition, auto.offset.reset quyết định vị trí.
- Nếu committed offset đã nằm ngoài phạm vi còn lưu, reset policy được áp dụng.

Trường hợp thường gặp là tăng số partition của topic. Các partition mới chưa có committed offset cho group hiện tại. Consumer được giao partition mới sẽ dùng auto.offset.reset để chọn vị trí bắt đầu.

Thay đổi concurrency hoặc số instance không tự động reset offset của các partition cũ. Kafka phân phối lại partition, còn tiến độ vẫn được quản lý theo group và partition.

## 9. Chủ động đưa consumer về offset mong muốn

Có những tình huống cần replay dữ liệu, chẳng hạn sửa lỗi xử lý, chạy lại báo cáo hoặc chuyển đổi consumer. Khi đó, có thể dùng một trong các cách:

- Tạo consumer group mới để đọc độc lập.
- Dùng công cụ kafka-consumer-groups để reset offset của group hiện tại.
- Dùng API seek trong ứng dụng để thay đổi vị trí đọc của consumer.

Cần phân biệt reset offset bền vững của group với seek trong phiên consumer đang chạy.

### 9.1. Reset bằng kafka-consumer-groups

Trước tiên, kiểm tra tiến độ hiện tại:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

Xem trước kế hoạch reset topic về earliest:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic commerce.order.created \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Sau khi xác nhận đúng group, topic và phạm vi reset, chạy:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic commerce.order.created \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Một số lựa chọn reset thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| --to-earliest | Đặt về offset sớm nhất còn lưu |
| --to-latest | Đặt về cuối partition |
| --to-offset N | Đặt tới offset cụ thể |
| --shift-by N | Dịch offset tương đối |
| --to-datetime | Chọn vị trí theo thời điểm |
| --by-duration | Chọn vị trí theo khoảng thời gian nếu phiên bản Kafka hỗ trợ |

Thông thường consumer group phải ở trạng thái inactive khi reset offset bằng công cụ này. Hãy dừng toàn bộ consumer thuộc group trước khi thực hiện; nếu group còn hoạt động, lệnh reset có thể bị từ chối hoặc tiến độ mới có thể bị consumer ghi đè.

Luôn chạy dry-run trước, lưu lại trạng thái hiện tại và chỉ dùng execute sau khi đã xác nhận. Sau khi reset, khởi động consumer để nó đọc theo offset mới.

Trên Windows, dùng script tương ứng trong thư mục bin\windows, chẳng hạn kafka-consumer-groups.bat.

### 9.2. Dùng group ID mới để replay độc lập

Nếu muốn chạy một luồng đọc lại mà không thay đổi tiến độ group đang phục vụ production, có thể dùng group ID khác:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-replay-2026"
)
public void replay(OrderCreated event) {
    // Xử lý hoặc đối soát dữ liệu theo kế hoạch replay.
}
~~~

Kết hợp với auto.offset.reset=earliest, group mới sẽ bắt đầu từ offset sớm nhất còn lưu.

Cách này tạo tiến độ độc lập, nhưng cũng có thể phát sinh tác dụng phụ nghiệp vụ nếu listener ghi dữ liệu hoặc gọi dịch vụ bên ngoài. Nên dùng consumer replay riêng, chế độ dry-run hoặc logic idempotent trước khi chạy xử lý lại.

### 9.3. Seek trong Spring Kafka

Spring Kafka cung cấp ConsumerSeekAware và ConsumerSeekCallback để listener có thể điều khiển vị trí đọc khi partition được gán hoặc theo yêu cầu của ứng dụng.

Ví dụ minh họa seek partition 0 tới offset 100 khi partition được assign:

~~~java
@Component
public class OrderReplayListener implements ConsumerSeekAware {

    @Override
    public void registerSeekCallback(ConsumerSeekCallback callback) {
        // Spring đăng ký callback để điều khiển vị trí đọc.
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        TopicPartition partition =
            new TopicPartition("commerce.order.created", 0);

        if (assignments.containsKey(partition)) {
            callback.seek(
                partition.topic(),
                partition.partition(),
                100L
            );
        }
    }
}
~~~

Đây là ví dụ minh họa cho thao tác seek có chủ đích. Nếu luôn seek về offset 100 mỗi lần partition được assign, ứng dụng sẽ đọc lại từ vị trí đó sau mỗi rebalance. Trong production, cần có điều kiện rõ ràng để tránh lặp lại ngoài ý muốn.

Seek thay đổi vị trí đọc của consumer hiện tại. Muốn quản lý tiến độ lâu dài giữa các lần restart, cần hiểu cách commit offset sau khi seek và xử lý record. Nếu offset được commit sau khi replay, committed offset của group sẽ thay đổi theo quá trình xử lý.

## 10. So sánh các cách khởi động lại

| Tình huống | Vị trí bắt đầu |
|---|---|
| Restart cùng group.id, offset còn hợp lệ | Committed offset đã lưu |
| Restart cùng group.id, offset chưa commit sau khi xử lý | Có thể đọc lại record chưa được commit |
| Group ID mới và earliest | Offset sớm nhất còn lưu |
| Group ID mới và latest | Cuối partition, chờ record mới |
| Group ID mới và none | Lỗi vì chưa có offset hợp lệ |
| Partition mới được thêm vào topic | Áp dụng auto.offset.reset cho partition chưa có offset |
| Committed offset bị retention loại bỏ | Áp dụng auto.offset.reset |
| Reset group bằng công cụ quản trị | Bắt đầu từ offset vừa reset sau khi consumer tham gia lại |
| Seek trong listener container | Dùng vị trí được seek trong phiên consumer, sau đó commit theo cấu hình |

## 11. Các lỗi thường gặp khi restart consumer

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Consumer đọc lại từ đầu sau deploy | group.id đã thay đổi hoặc group chưa có offset hợp lệ | Kiểm tra group.id và consumer group describe |
| Consumer bỏ qua dữ liệu cũ | Group mới dùng latest | Kiểm tra auto.offset.reset và thời điểm bắt đầu |
| Đổi earliest nhưng vẫn đọc tiếp offset cũ | Group vẫn có committed offset hợp lệ | Kiểm tra committed offset của từng partition |
| Consumer báo NoOffsetForPartitionException | Dùng none nhưng group chưa có offset hợp lệ | Reset offset hoặc chọn policy phù hợp |
| Consumer quay về đầu dữ liệu còn lưu | Committed offset đã bị retention loại bỏ và policy là earliest | Kiểm tra log start offset và consumer lag |
| Consumer xử lý trùng sau restart | Record đã xử lý nhưng offset chưa commit | Kiểm tra ack mode và thiết kế idempotency |
| Consumer bỏ mất record sau restart | Offset commit trước khi nghiệp vụ hoàn tất | Kiểm tra thứ tự xử lý và acknowledgment |
| Partition mới đọc từ latest | Group chưa có offset cho partition mới | Kiểm tra partition expansion và reset policy |
| Reset offset không có tác dụng | Consumer vẫn hoạt động hoặc chưa được restart sau reset | Dừng group, dry-run, execute và khởi động lại |

## 12. Kiểm thử hành vi restart và offset

Nên kiểm thử với Kafka thật trong môi trường cô lập, bằng EmbeddedKafka hoặc Testcontainers.

Các kịch bản cần xác nhận:

1. Group mới với earliest đọc được các record đang còn lưu.
2. Group mới với latest bỏ qua dữ liệu lịch sử và nhận record mới.
3. Group đã commit offset rồi restart tiếp tục từ committed offset.
4. Thay group ID tạo tiến độ đọc độc lập.
5. Consumer xử lý record nhưng dừng trước commit có thể nhận lại record.
6. Partition mới được thêm vào topic sử dụng reset policy khi group chưa có offset.
7. Offset cũ không còn hợp lệ kích hoạt reset policy hoặc lỗi none.
8. Seek đưa consumer tới đúng partition và offset.
9. AckMode và error handler tạo ra hành vi commit phù hợp khi listener thành công hoặc thất bại.

Khi viết kiểm thử restart, cần chờ consumer group hoàn tất assignment và chờ commit offset được ghi nhận trước khi dừng consumer. Nếu dừng ngay sau khi listener được gọi, kiểm thử có thể quan sát một kết quả khác nhau tùy thời điểm commit.

Có thể dùng kafka-consumer-groups --describe để xác nhận committed offset và lag trong môi trường test. Không dựa duy nhất vào log “listener đã nhận record” để kết luận offset đã commit.

## 13. Checklist lựa chọn offset khi triển khai

- [ ] group.id có ổn định qua các lần restart và deploy không?
- [ ] Consumer group có committed offset cho từng partition không?
- [ ] auto.offset.reset được chọn rõ ràng là earliest, latest hay none?
- [ ] Đã hiểu earliest chỉ bắt đầu từ dữ liệu còn lưu?
- [ ] Đã đánh giá nguy cơ bỏ qua dữ liệu lịch sử khi dùng latest?
- [ ] enable.auto.commit và Spring Kafka AckMode có cấu hình rõ ràng?
- [ ] Offset chỉ được commit sau khi xử lý đạt điều kiện nghiệp vụ?
- [ ] Listener có thể chịu được record được giao lại không?
- [ ] Consumer lag có được theo dõi để tránh offset bị retention loại bỏ?
- [ ] Có quy trình dry-run và phê duyệt khi reset offset production?
- [ ] Có group riêng hoặc cơ chế idempotent cho replay?
- [ ] Kiểm thử đã xác nhận hành vi restart, rebalance và partition mới?

## Kết luận

Khi consumer khởi động lại, Kafka ưu tiên committed offset hợp lệ đã lưu cho từng partition của consumer group. auto.offset.reset chỉ được áp dụng khi group chưa có offset hợp lệ hoặc offset đã nằm ngoài phạm vi dữ liệu broker còn giữ. earliest đọc từ đầu dữ liệu còn lưu, latest bắt đầu ở cuối partition, còn none yêu cầu ứng dụng hoặc người vận hành cung cấp vị trí rõ ràng.

Trong Spring Kafka, hành vi này gắn chặt với group.id, acknowledgment mode và thời điểm commit offset của listener container. Muốn replay có kiểm soát, có thể reset offset bằng công cụ Kafka, tạo group mới hoặc dùng seek. Kết hợp chính sách offset với idempotency, theo dõi consumer lag và kiểm thử restart giúp luồng consumer phục hồi đúng tiến độ và hạn chế mất hoặc xử lý lặp sự kiện.
