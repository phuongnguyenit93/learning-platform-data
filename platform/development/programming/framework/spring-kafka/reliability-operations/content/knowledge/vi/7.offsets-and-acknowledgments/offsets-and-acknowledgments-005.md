# AckMode COUNT_TIME

Trong Spring Kafka, **AckMode.COUNT_TIME** là chế độ commit offset do listener container quản lý. Container commit các offset đang chờ khi một trong hai điều kiện xảy ra: đã xử lý đủ số record được cấu hình (**ackCount**) hoặc đã hết khoảng thời gian được cấu hình (**ackTime**) kể từ lần commit trước. Điều kiện nào đạt trước sẽ kích hoạt lần commit tiếp theo.

Chế độ này kết hợp hai cách điều khiển tần suất commit:

- **Theo số lượng:** khi lưu lượng cao, container có thể commit sau mỗi nhóm record đạt ngưỡng.
- **Theo thời gian:** khi lưu lượng thấp, container vẫn có cơ hội commit theo chu kỳ thời gian mà không phải chờ đủ số record.

**COUNT_TIME** thường phù hợp khi muốn cân bằng giữa chi phí commit và khoảng thời gian offset chưa được lưu bền vững. Nó giảm số lần commit so với commit sau từng record, đồng thời tránh phải chờ một lượng record lớn mới commit trong workload có lưu lượng thấp.

## 1. Offset và acknowledgement trong Spring Kafka

Kafka lưu offset commit theo từng consumer group và partition. Offset được commit biểu thị vị trí tiếp theo mà consumer group sẽ đọc khi tiếp tục từ checkpoint đó. Ví dụ, nếu record cuối cùng đã xử lý có offset 41, consumer thường commit offset 42.

Một lần gọi listener thành công và một lần commit offset là hai sự kiện khác nhau:

1. Kafka consumer poll record từ broker.
2. Spring Kafka chuyển record cho listener.
3. Listener thực hiện nghiệp vụ và hoàn tất thành công.
4. Container ghi nhận offset tương ứng là offset có thể commit.
5. Khi điều kiện của AckMode được đáp ứng, container gửi yêu cầu commit offset cho Kafka.

Nếu ứng dụng hoàn tất nghiệp vụ nhưng tiến trình dừng trước khi offset được commit, group có thể đọc lại record sau khi consumer khởi động hoặc được giao partition lần nữa. Đây là cơ sở của hành vi at-least-once trong nhiều cấu hình consumer.

Trong Spring Kafka, **AckMode** cho container biết khi nào offset được commit. Với các chế độ do container quản lý, listener không cần tự gọi **Acknowledgment.acknowledge()** cho mỗi record. **COUNT_TIME** là một chế độ tự động của container, không phải chế độ manual.

Spring Kafka thường tắt Kafka consumer auto commit khi container quản lý offset. Không bật **enable.auto.commit=true** một cách tùy tiện cùng với cơ chế commit của container, vì hai cơ chế có thể làm thời điểm commit khó dự đoán và phá vỡ giả định về xử lý record.

## 2. COUNT_TIME hoạt động như thế nào?

Hai ngưỡng chính là:

| Thuộc tính | Ý nghĩa |
|---|---|
| **ackCount** | Số record được nhận và xử lý kể từ lần commit trước để kích hoạt commit theo số lượng |
| **ackTime** | Khoảng thời gian tính bằng mili giây kể từ lần commit trước để kích hoạt commit theo thời gian |

Container theo dõi các offset đang chờ commit và điều kiện đếm/thời gian. Khi một trong hai ngưỡng đạt tới, container commit các offset đang chờ theo từng partition.

Ví dụ cấu hình:

- **ackCount = 100**
- **ackTime = 5000** mili giây (5 giây)

Nếu consumer xử lý 100 record chỉ trong 2 giây, ngưỡng số lượng đạt trước và container có thể commit sau khi xử lý đến ngưỡng đó. Nếu consumer chỉ xử lý 30 record trong 5 giây, ngưỡng thời gian đạt trước và container có thể commit các offset đang chờ sau khoảng thời gian đó.

~~~text
Ngưỡng: ackCount = 100, ackTime = 5 giây

Lưu lượng cao:
  Commit trước ---- 100 record trong 2 giây ----> Commit
                    ^ count đạt trước

Lưu lượng thấp:
  Commit trước ---- 30 record trong 5 giây -----> Commit
                    ^ time đạt trước
~~~

**COUNT_TIME** có nghĩa là điều kiện OR: count đạt hoặc time đạt. Nó không đợi cả hai điều kiện cùng đúng. Nếu muốn commit chỉ khi đồng thời đủ số record và đủ thời gian, **COUNT_TIME** không biểu diễn chính sách đó.

Điều kiện thời gian không phải một lịch timer độc lập đảm bảo commit chính xác tại từng mili giây. Container kiểm tra và thực hiện commit trong quá trình điều phối poll và xử lý record. Thời gian xử lý listener, thời điểm poll tiếp theo, tải của consumer và thời gian phản hồi từ broker đều có thể làm commit hoàn tất muộn hơn ngưỡng cấu hình.

Nếu không có offset mới đang chờ commit, việc hết **ackTime** không tạo ra một commit có dữ liệu mới. Commit chỉ có ý nghĩa khi container có tiến độ offset cần lưu.

## 3. Phạm vi đếm và thời gian

**ackCount** và **ackTime** được áp dụng cho từng consumer container/consumer instance, không phải một bộ đếm tổng hợp cho toàn bộ ứng dụng hay toàn bộ group.

Ví dụ ứng dụng có ba listener consumer chạy với concurrency bằng 3. Mỗi consumer có tiến độ xử lý, số record đã nhận kể từ lần commit và thời điểm commit riêng. Không nên hiểu **ackCount=100** là container sẽ chờ đủ 100 record cộng dồn từ cả ba consumer.

Khi consumer sở hữu nhiều partition, các offset đang chờ của những partition đó được quản lý trong cùng consumer. Một lần commit có thể bao gồm offset cho nhiều partition mà consumer đang sở hữu. Offset vẫn được lưu riêng theo từng partition trong group.

Điều này có nghĩa:

- Một consumer xử lý nhanh có thể kích hoạt commit theo count trước các consumer khác.
- Một consumer xử lý chậm hoặc ít record có thể kích hoạt commit theo time.
- Việc một consumer commit không làm thay đổi counter hoặc timer của consumer member khác.
- Sau rebalance, consumer mới tiếp tục từ offset đã commit của từng partition được giao.

## 4. Cấu hình COUNT_TIME trong Spring Kafka

Có thể đặt AckMode và hai ngưỡng trên **ContainerProperties** của listener container factory.

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);

        ContainerProperties containerProperties =
                factory.getContainerProperties();
        containerProperties.setAckMode(ContainerProperties.AckMode.COUNT_TIME);
        containerProperties.setAckCount(100);
        containerProperties.setAckTime(5_000);

        return factory;
    }
}
~~~

Trong ví dụ:

- **setAckMode(COUNT_TIME)** chọn chế độ commit theo count hoặc time.
- **setAckCount(100)** đặt ngưỡng 100 record.
- **setAckTime(5_000)** đặt ngưỡng thời gian 5.000 mili giây.

Listener sử dụng factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Với listener trên, container ghi nhận offset sau khi listener hoàn tất theo quy tắc của container. Khi count hoặc time đạt ngưỡng, container commit các offset đang chờ.

Nếu dùng Spring Boot auto-configuration, có thể chọn AckMode bằng property listener trong các phiên bản Spring Boot hỗ trợ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
    listener:
      ack-mode: count_time
~~~

Khi cần kiểm soát chính xác **ackCount** và **ackTime**, cấu hình trực tiếp **ContainerProperties** trong factory giúp thể hiện rõ hai ngưỡng. Hãy kiểm tra API và property binding theo phiên bản Spring Boot/Spring Kafka đang dùng; không giả định mọi phiên bản đều cung cấp cùng tập property.

### Dùng application.properties

Nếu chỉ cấu hình AckMode qua Spring Boot:

~~~properties
spring.kafka.consumer.group-id=orders-service
spring.kafka.listener.ack-mode=count_time
~~~

Các giá trị count/time vẫn có thể đặt trên container properties trong Java configuration. Không cần tự tạo **Acknowledgment** hoặc gọi **acknowledge()** để sử dụng **COUNT_TIME**.

## 5. So sánh COUNT_TIME với các AckMode khác

Spring Kafka cung cấp nhiều AckMode để chọn thời điểm commit phù hợp với cách listener xử lý record.

| AckMode | Thời điểm commit khái quát | Đặc điểm |
|---|---|---|
| **RECORD** | Sau khi listener xử lý xong từng record | Commit thường xuyên; giảm khoảng offset chưa commit nhưng tăng chi phí commit |
| **BATCH** | Sau khi xử lý xong tất cả record của một lần poll | Phù hợp với xử lý theo batch; commit theo ranh giới poll |
| **TIME** | Khi **ackTime** đã trôi qua kể từ lần commit trước | Điều khiển theo thời gian |
| **COUNT** | Khi số record kể từ lần commit trước đạt **ackCount** | Điều khiển theo số lượng |
| **COUNT_TIME** | Khi **ackTime** hoặc **ackCount** đạt trước | Kết hợp ngưỡng thời gian và số lượng |
| **MANUAL** | Listener xác nhận qua **Acknowledgment**; container xử lý commit theo quy tắc manual | Ứng dụng kiểm soát thời điểm xác nhận |
| **MANUAL_IMMEDIATE** | Commit ngay khi listener gọi acknowledge theo điều kiện luồng và cấu hình | Cần hiểu rõ thread và hành vi commit |

Ví dụ lựa chọn:

- Dùng **RECORD** khi muốn commit sau từng record và chấp nhận overhead cao hơn.
- Dùng **BATCH** khi xử lý trọn poll batch là một đơn vị công việc.
- Dùng **COUNT** khi lưu lượng đủ ổn định và muốn commit sau một lượng record xác định.
- Dùng **TIME** khi muốn chu kỳ commit theo thời gian.
- Dùng **COUNT_TIME** khi workload thay đổi lưu lượng và muốn một trong hai ngưỡng kích hoạt commit.
- Dùng manual mode khi nghiệp vụ cần quyết định rõ ràng thời điểm xác nhận.

**COUNT_TIME** không có nghĩa listener xác nhận record theo thời gian. Nó điều khiển thời điểm container commit offset đã được ghi nhận sau xử lý.

## 6. COUNT_TIME và listener xử lý record hoặc batch

Với record listener, container gọi listener cho từng record được poll. Sau khi listener hoàn tất, container ghi nhận tiến độ offset và đánh giá điều kiện commit theo cấu hình.

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Với batch listener, listener nhận một batch record trong một lần gọi. Container phải dựa trên kết quả xử lý batch để xác định offset nào đã được xử lý và có thể commit. Nếu listener batch ném exception, việc xử lý offset và retry phụ thuộc error handler, batch listener semantics và cấu hình container.

Ví dụ batch listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersBatchKafkaListenerContainerFactory")
public void handleBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Với batch listener, cần thiết kế **processBatch** sao cho kết quả của từng record hoặc toàn bộ batch được xử lý rõ ràng. Nếu một record trong batch lỗi sau khi các record khác đã tạo side effect, retry batch có thể chạy lại side effect của các record đã thành công. Dùng event ID hoặc cơ chế idempotency để tránh áp dụng nghiệp vụ hai lần.

Không nên chọn **COUNT_TIME** chỉ vì listener nhận **List**. Chọn AckMode theo đơn vị nghiệp vụ cần commit và cách error handler phục hồi khi một phần batch thất bại.

## 7. Điều gì xảy ra khi ứng dụng crash trước lần commit?

Giả sử **ackCount=100** và consumer đã xử lý thành công 80 record kể từ lần commit gần nhất. Nếu tiến trình crash trước khi đạt 100 record hoặc trước khi **ackTime** hết hạn, các offset mới có thể chưa được commit.

Khi consumer khởi động lại hoặc partition được giao cho member khác, consumer tiếp tục từ offset đã commit gần nhất. Một phần record đã được listener xử lý trước khi crash có thể được đọc lại.

Ví dụ:

~~~text
Offset đã commit: 100

Consumer xử lý:
  100 101 102 ... 179
  (80 record đã tạo side effect)

Crash trước commit tiếp theo

Consumer mới bắt đầu lại từ offset 100
  100 101 102 ... có thể được xử lý lại
~~~

Đây là hành vi at-least-once: record có thể được xử lý lại khi side effect đã hoàn tất nhưng offset chưa được commit. **COUNT_TIME** không tạo exactly-once cho database hoặc API bên ngoài Kafka.

Để chịu được việc đọc lại:

- Dùng event ID ổn định cho mỗi sự kiện nghiệp vụ.
- Thiết kế cập nhật database theo hướng idempotent.
- Có thể lưu event ID đã xử lý trong cùng transaction database với thay đổi nghiệp vụ.
- Với thao tác ngoài có tính không thể đảo ngược, dùng idempotency key do hệ thống đích hỗ trợ.
- Theo dõi offset commit và consumer lag để nhận biết tiến độ thực tế.

Nếu commit offset trước khi side effect hoàn tất, có nguy cơ mất xử lý: consumer có thể không đọc lại record đã được commit. Vì vậy, listener container thường commit sau khi listener hoàn tất theo AckMode đã chọn.

## 8. COUNT_TIME, retry và error handling

AckMode không tự quyết định record lỗi sẽ được retry bao nhiêu lần hoặc chuyển đến đâu. Cách xử lý record thất bại phụ thuộc error handler, retry topic, backoff, dead-letter topic và cấu hình container.

Với Spring Kafka, khi listener ném exception, container/error handler quyết định có retry, seek về offset, phục hồi record hay tiếp tục. Chỉ những offset được coi là đã xử lý hoặc đã phục hồi theo chính sách mới nên được commit.

Một số nguyên tắc:

- Lỗi tạm thời có thể retry với backoff hữu hạn.
- Lỗi dữ liệu không thể phục hồi bằng retry nên được chuyển đến luồng xử lý lỗi hoặc DLT theo chính sách.
- Không commit vượt qua một record chưa xử lý thành công nếu điều đó làm mất khả năng đọc lại record đó.
- Khi retry hoàn tất và record được phục hồi thành công, cần hiểu error handler ảnh hưởng đến offset được commit ra sao.
- Kiểm thử kết hợp AckMode, record listener/batch listener và error handler đang dùng.

Ví dụ cấu hình retry có giới hạn:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                new FixedBackOff(1_000L, 2L));

factory.setCommonErrorHandler(errorHandler);
~~~

Đoạn mã minh họa error handler thử lại với khoảng cách một giây và số lần retry hữu hạn theo cấu hình BackOff. Cách chuyển record hết retry sang DLT cần cấu hình recoverer riêng nếu nghiệp vụ yêu cầu.

Không nên xem **ackCount** là số lần retry. **ackCount** đếm record để điều khiển commit offset; retry là chính sách phục hồi lỗi. Hai cấu hình có mục đích khác nhau.

## 9. Tác động của COUNT_TIME đến hiệu năng và độ tin cậy

Commit offset có chi phí: consumer gửi request đến broker coordinator và Kafka lưu tiến độ group. Commit sau mỗi record làm tăng số request commit; commit quá thưa làm tăng khoảng offset chưa được lưu.

**COUNT_TIME** tạo một điểm cân bằng:

- Khi lưu lượng cao, count threshold có thể kích hoạt commit thường xuyên hơn time threshold.
- Khi lưu lượng thấp, time threshold tránh việc chờ quá lâu để đủ số record.
- Khi listener xử lý chậm, thời điểm commit thực tế có thể muộn hơn ngưỡng vì container phải hoàn tất xử lý và poll.
- Khi có nhiều consumer, mỗi consumer có counter và timer riêng nên commit không xảy ra đồng bộ toàn group.

Một **ackCount** nhỏ và **ackTime** ngắn làm commit thường xuyên hơn, giảm khoảng offset có thể bị đọc lại nhưng tăng chi phí commit. Ngưỡng lớn và thời gian dài làm giảm commit overhead nhưng tăng số record có khả năng bị replay sau crash.

Không có giá trị đúng cho mọi workload. Với hệ thống đơn hàng, cần cân nhắc chi phí xử lý lặp và idempotency. Với telemetry, có thể chấp nhận replay nhỏ nếu consumer xử lý rẻ và dữ liệu có thể khử trùng. Với hệ thống cần cập nhật database, cần tính cả chi phí transaction và khả năng xử lý lại.

## 10. Chọn ackCount và ackTime

Chọn ngưỡng dựa trên tốc độ record, thời gian xử lý và mức replay mà hệ thống có thể chịu được.

Ví dụ một workload có tốc độ trung bình 50 record/giây:

- **ackCount=100** tương ứng khoảng hai giây ở tốc độ trung bình nếu consumer xử lý đều.
- **ackTime=5000** tương ứng năm giây.
- Trong điều kiện ổn định, count có thể đạt trước time.
- Nếu lưu lượng giảm xuống 5 record/giây, time có thể đạt trước count.

Đây chỉ là phép ước lượng. Thực tế phụ thuộc poll batch, phân phối partition, thời gian listener, số consumer và tốc độ commit broker.

Một quy trình chọn giá trị:

1. Xác định số record mỗi giây trên từng consumer, không chỉ throughput tổng của topic.
2. Xác định số record tối đa có thể chấp nhận bị đọc lại sau một sự cố.
3. Ước lượng chi phí commit và khả năng xử lý của group coordinator.
4. Đặt **ackCount** để commit theo batch khi lưu lượng cao.
5. Đặt **ackTime** để giới hạn thời gian offset chờ commit khi lưu lượng thấp.
6. Kiểm tra p95/p99 thời gian xử lý listener và thời gian poll.
7. Thử nghiệm khi broker chậm, consumer restart và rebalance.
8. Điều chỉnh dựa trên commit latency, lag và tỷ lệ xử lý lặp.

Ví dụ cấu hình ban đầu:

~~~java
containerProperties.setAckMode(ContainerProperties.AckMode.COUNT_TIME);
containerProperties.setAckCount(200);
containerProperties.setAckTime(3_000);
~~~

Giá trị 200 record hoặc 3 giây chỉ là ví dụ để bắt đầu đo. Không nên đưa thẳng vào production mà chưa kiểm tra tốc độ và hậu quả xử lý lặp của workload.

## 11. Commit sync và async

Sau khi container quyết định commit offset, Kafka consumer có thể commit đồng bộ hoặc bất đồng bộ theo cấu hình container.

- **Synchronous commit:** container chờ kết quả commit. Cách này giúp nhận biết lỗi commit tại thời điểm gọi nhưng có thể làm consumer thread chờ broker.
- **Asynchronous commit:** container gửi commit và tiếp tục xử lý; callback có thể báo lỗi sau đó. Cách này giảm thời gian chờ trong luồng xử lý nhưng cần quan sát callback và thứ tự commit.

Spring Kafka có thuộc tính **syncCommits** trong **ContainerProperties**; mặc định thường là synchronous commit. Có thể cung cấp commit callback để quan sát kết quả commit. Hành vi cụ thể phụ thuộc phiên bản và cấu hình container.

**COUNT_TIME** quyết định khi nào container yêu cầu commit. **syncCommits** quyết định cách container chờ hoặc nhận kết quả commit. Hai cấu hình này độc lập:

| Cấu hình | Câu hỏi được trả lời |
|---|---|
| **AckMode.COUNT_TIME** | Khi nào offset đang chờ được đưa vào một lần commit? |
| **syncCommits** | Container chờ kết quả commit theo cách nào? |
| **ackCount** | Bao nhiêu record kể từ lần commit trước sẽ kích hoạt commit? |
| **ackTime** | Bao lâu kể từ lần commit trước sẽ kích hoạt commit? |

Không nên chuyển sang async commit chỉ để giảm latency mà không theo dõi lỗi commit. Nếu commit thất bại, group có thể đọc lại record đã xử lý.

## 12. Rebalance và COUNT_TIME

Khi partition bị revoke, consumer có thể còn offset đang chờ commit. Container cần xử lý các offset đó theo lifecycle và chính sách commit của nó. Nếu consumer bị mất ownership đột ngột, không thể giả định nó vẫn có thể commit thành công.

Ví dụ:

1. Consumer A sở hữu partition P0.
2. A xử lý 70 record, chưa đạt **ackCount=100** và **ackTime** chưa hết.
3. Group rebalance và P0 được thu hồi khỏi A.
4. Nếu offset chưa được commit, consumer mới có thể đọc lại các record kể từ commit gần nhất.
5. Consumer B tiếp tục xử lý P0 theo assignment mới.

Không nên dựa vào **COUNT_TIME** để đảm bảo commit hoàn tất trước mọi rebalance. Hãy cấu hình graceful shutdown, callback revoke và idempotency cho side effect. Cũng cần kiểm tra container có commit pending offsets theo cách nào trong phiên bản Spring Kafka đang dùng.

## 13. Quan sát trong production

Khi sử dụng **COUNT_TIME**, theo dõi cả nhịp xử lý record và nhịp commit:

- Record consume rate theo consumer/member.
- Consumer lag theo partition.
- Commit rate và tổng số commit.
- Commit latency trung bình và tối đa.
- Commit failure hoặc exception.
- Thời gian giữa các lần commit.
- Số record xử lý giữa hai lần commit.
- Thời gian listener xử lý một poll batch.
- Số lần rebalance và số record được đọc lại sau rebalance.

Kafka client thường cung cấp các metric như commit rate, commit total, commit latency và assigned partitions; tên metric cụ thể phụ thuộc phiên bản. Spring Kafka cũng có log container và callback commit để hỗ trợ điều tra.

Một số dấu hiệu:

| Dấu hiệu | Hướng điều tra |
|---|---|
| Commit rate quá cao | **ackCount** nhỏ hoặc **ackTime** ngắn; đánh giá overhead và nhu cầu replay |
| Commit rate quá thấp | Ngưỡng quá lớn, listener chậm hoặc consumer ít record; kiểm tra offset pending |
| Lag tăng dù record được xử lý | Commit có thể chậm hoặc lỗi; so sánh processing rate với commit rate |
| Replay nhiều sau restart | Offset commit cách xa tiến độ xử lý; xem lại count/time và idempotency |
| Commit latency tăng | Coordinator/broker quá tải, network chậm hoặc group có nhiều member |
| Lỗi commit xuất hiện | Kiểm tra membership, generation, ownership và kết nối coordinator |

Không chỉ nhìn tổng lag. Một partition có thể bị chậm trong khi các partition khác vẫn ổn định. Theo dõi theo partition giúp phát hiện lệch tải và member có vấn đề.

## 14. Kiểm thử hành vi COUNT_TIME

Trước khi triển khai, nên kiểm tra hành vi commit trong các tình huống đại diện:

### Count đạt trước time

Đặt count nhỏ và time dài. Gửi đủ số record nhanh hơn khoảng thời gian cấu hình. Quan sát commit xảy ra khi count đạt.

### Time đạt trước count

Đặt count lớn và time ngắn. Gửi một lượng record nhỏ rồi chờ. Quan sát container commit offset đang chờ sau khi điều kiện time được kiểm tra.

### Không có record mới

Để consumer idle sau một lần commit. Hết **ackTime** không nên tạo ra một tiến độ offset mới nếu không có offset pending.

### Crash trước commit

Cho listener tạo side effect, dừng ứng dụng trước ngưỡng commit và khởi động lại. Xác nhận record chưa commit có thể được đọc lại và side effect không bị áp dụng trùng.

### Listener ném exception

Kiểm tra error handler, retry, DLT và offset commit. Xác nhận record lỗi không bị bỏ qua ngoài chính sách mong muốn.

### Rebalance trước ngưỡng

Scale consumer hoặc restart member khi vẫn còn offset pending. Quan sát partition revoke, offset commit và việc consumer mới tiếp tục đọc.

## 15. Những hiểu nhầm thường gặp

**COUNT_TIME chờ đủ cả count và time.** Không đúng. Nó commit khi một trong hai điều kiện đạt trước.

**ackTime là thời hạn chính xác để offset luôn được commit.** Không đúng. Container kiểm tra điều kiện trong chu kỳ xử lý; poll, listener và broker latency có thể làm commit hoàn tất muộn hơn.

**ackCount là số lần listener gọi acknowledge.** Không đúng. **COUNT_TIME** là chế độ container-managed; **ackCount** điều khiển số record được xử lý kể từ lần commit trước.

**COUNT_TIME commit ngay sau mỗi record.** Không đúng. Container gom offset pending cho đến khi count hoặc time đạt.

**COUNT_TIME đảm bảo không đọc lại record sau crash.** Không đúng. Nếu side effect đã hoàn tất nhưng offset chưa commit, record có thể được đọc lại.

**COUNT_TIME thay thế retry và error handler.** Không đúng. AckMode điều khiển commit; error handler điều khiển cách xử lý record lỗi.

**ackCount được chia sẻ giữa mọi consumer trong group.** Không đúng. Mỗi consumer container có tiến độ đếm và thời gian riêng.

**Khi không có record, timer vẫn tạo commit mới.** Không có offset pending thì không có tiến độ mới để commit.

**COUNT_TIME là exactly-once.** Không đúng. Nó chỉ điều khiển thời điểm commit offset. Exactly-once trong Kafka cần transaction phù hợp; side effect ở database hoặc hệ thống ngoài cần cơ chế phối hợp riêng.

## 16. Hướng dẫn thiết kế

Khi chọn **AckMode.COUNT_TIME**, hãy xác định mức commit overhead và khoảng record có thể bị replay mà nghiệp vụ chấp nhận. Chọn **ackCount** để xử lý workload có lưu lượng cao và **ackTime** để kiểm soát commit khi lưu lượng thấp.

Một cấu hình khởi đầu có thể là:

1. Đặt **AckMode.COUNT_TIME** trên listener container.
2. Chọn **ackCount** theo throughput thực tế của từng consumer.
3. Chọn **ackTime** theo giới hạn thời gian offset pending mà hệ thống chấp nhận.
4. Giữ auto commit của Kafka consumer tắt để container quản lý offset.
5. Đảm bảo listener chỉ hoàn tất khi side effect đã đạt trạng thái an toàn để commit.
6. Thiết kế xử lý idempotent để chịu được record được đọc lại.
7. Cấu hình error handler và retry theo loại lỗi.
8. Kiểm tra commit sync/async và quan sát lỗi commit.
9. Kiểm thử crash, rebalance, lưu lượng thấp/cao và listener exception.
10. Theo dõi commit rate, commit latency, consumer lag và tỷ lệ replay trong production.

**COUNT_TIME** hữu ích khi workload có lưu lượng thay đổi: count giúp commit theo lô khi có nhiều record, còn time giúp commit tiến độ đang chờ khi lưu lượng thấp. Chọn hai ngưỡng theo khả năng chịu replay và chi phí commit của hệ thống; luôn nhớ rằng offset commit là checkpoint của consumer group, còn tính an toàn của side effect cần được bảo đảm ở tầng nghiệp vụ.
