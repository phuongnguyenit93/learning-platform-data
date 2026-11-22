# enable.auto.commit và chiến lược commit

## 1. Offset commit dùng để làm gì?

Consumer đọc record từ một partition theo offset. Khi xử lý xong một record hoặc một nhóm record, consumer cần lưu lại vị trí có thể tiếp tục đọc trong lần chạy sau. Thao tác lưu vị trí đó được gọi là **commit offset**.

Offset được commit là vị trí kế tiếp consumer sẽ đọc, không phải offset của record cuối cùng đã xử lý. Ví dụ, consumer xử lý thành công record có offset `41` thì offset cần commit thường là `42`.

Kafka lưu committed offset theo consumer group và partition. Vì vậy:

- Các consumer thuộc cùng group dùng chung tiến độ đọc của group đối với từng partition.
- Hai group khác nhau có committed offset độc lập, dù cùng đọc một topic.
- Khi consumer khởi động lại hoặc partition được gán cho consumer khác, consumer có thể tiếp tục từ committed offset.

Commit offset là một phần của thiết kế độ tin cậy. Commit quá sớm có thể khiến record chưa xử lý xong bị bỏ qua; commit quá muộn có thể khiến record đã xử lý bị giao lại. Chiến lược phù hợp phụ thuộc vào mức chấp nhận xử lý lặp, thông lượng và chi phí của mỗi lần commit.

## 2. enable.auto.commit của Kafka Consumer

Trong Apache Kafka Java Consumer, thuộc tính `enable.auto.commit` điều khiển việc Kafka client tự commit offset theo chu kỳ. Giá trị mặc định của Kafka consumer thuần là `true`; chu kỳ được điều chỉnh bằng `auto.commit.interval.ms` (mặc định thường là 5 giây).

Khi `enable.auto.commit=true`, client tự commit tiến độ đọc ở chế độ nền. Ứng dụng không cần gọi `commitSync()` hoặc `commitAsync()` cho mỗi lần poll. Tuy nhiên, Kafka client không biết xử lý nghiệp vụ của ứng dụng đã hoàn tất hay chưa. Việc commit được quyết định dựa trên tiến độ consumer đã poll, không dựa trên xác nhận từ service nghiệp vụ.

Điều này có thể gây mất xử lý nếu ứng dụng đang xử lý một batch nhưng offset của batch đã được commit. Ví dụ:

1. `poll()` trả về các record từ offset `100` đến `109`.
2. Ứng dụng mới xử lý thành công đến offset `103`.
3. Auto-commit lưu tiến độ đến offset kế tiếp của batch đã poll.
4. Ứng dụng dừng đột ngột trước khi xử lý offset `104` đến `109`.
5. Khi khởi động lại, consumer có thể tiếp tục sau các record đã commit, khiến một phần record chưa xử lý không được giao lại.

Vì thế, auto-commit thuận tiện cho ứng dụng đơn giản có thể chấp nhận rủi ro mất một phần xử lý, nhưng không phù hợp khi cần gắn commit với kết quả nghiệp vụ.

### Ví dụ cấu hình Kafka Consumer thuần

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, true);
props.put(ConsumerConfig.AUTO_COMMIT_INTERVAL_MS_CONFIG, 5_000);

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));
```

Trong ví dụ này, consumer tự commit theo chu kỳ. Ứng dụng không có tín hiệu cho Kafka biết một record cụ thể đã hoàn tất xử lý nghiệp vụ. Nếu cần kiểm soát chính xác thời điểm commit, hãy tắt auto-commit và commit sau khi xử lý thành công.

## 3. Tắt auto-commit và commit thủ công

Với `enable.auto.commit=false`, Kafka client không tự lưu offset theo chu kỳ. Ứng dụng chịu trách nhiệm gọi commit khi đã hoàn tất xử lý ở mức mong muốn.

Hai API phổ biến:

- `commitSync()`: gửi yêu cầu commit và chờ kết quả. Cách này dễ hiểu và phù hợp khi cần biết commit đã hoàn tất trước khi tiếp tục.
- `commitAsync()`: gửi yêu cầu commit không chặn luồng hiện tại. Cách này giảm thời gian chờ nhưng cần xử lý callback và thứ tự các yêu cầu commit cẩn thận.

Ví dụ commit đồng bộ sau khi xử lý toàn bộ batch:

```java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (true) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1_000));

        for (ConsumerRecord<String, String> record : records) {
            processBusiness(record);
        }

        // Chỉ commit khi mọi record trong batch đã xử lý thành công.
        consumer.commitSync();
    }
}
```

Nếu `processBusiness` ném lỗi giữa batch, lệnh `commitSync()` ở cuối vòng lặp không được chạy. Khi consumer khởi động lại, batch có thể được giao lại từ committed offset cũ. Một số record đầu batch có thể đã được xử lý trước khi lỗi xảy ra, do đó handler cần idempotent để tránh tạo tác dụng phụ trùng lặp.

Lưu ý: `commitSync()` không tự biết record nào trong batch đã hoàn tất. Nó commit vị trí hiện tại mà consumer đã đọc. Nếu ứng dụng muốn commit sau từng record trong khi vẫn poll nhiều record, cần theo dõi offset kế tiếp đã xử lý cho từng `TopicPartition` và truyền map `TopicPartition` → `OffsetAndMetadata` cho API commit. Không được commit vị trí poll hiện tại nếu phía sau vẫn còn record chưa xử lý.

## 4. Spring Kafka quản lý commit như thế nào?

Khi dùng `@KafkaListener`, ứng dụng thường không trực tiếp gọi `KafkaConsumer.commitSync()` hoặc `commitAsync()`. Listener container của Spring Kafka quản lý consumer, vòng lặp `poll()`, việc gọi listener và commit offset.

Từ Spring Kafka 2.3, framework tự đặt `enable.auto.commit=false` nếu ứng dụng chưa cấu hình thuộc tính này. Nhờ đó, listener container có thể điều khiển thời điểm commit theo `AckMode`. Nếu bật `enable.auto.commit=true` một cách tường minh, Kafka client tự commit theo chu kỳ và ứng dụng mất cơ chế kiểm soát commit theo AckMode mà container cung cấp.

Với Spring Kafka, nên để `enable.auto.commit=false` và chọn `spring.kafka.listener.ack-mode` theo yêu cầu xử lý. Giá trị mặc định của listener container là `BATCH`.

### Cấu hình đề xuất

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: record
```

Trong Spring Boot, `enable-auto-commit` là thuộc tính dạng kebab-case ánh xạ tới Kafka client property `enable.auto.commit`. `ack-mode` cấu hình cách listener container commit offset. Hai thuộc tính có vai trò khác nhau: một thuộc tính tắt cơ chế auto-commit của Kafka client; thuộc tính còn lại chọn chiến lược commit do container quản lý.

## 5. Các chế độ AckMode trong Spring Kafka

`ContainerProperties.AckMode` quyết định khi nào listener container commit offset. Các chế độ thường dùng:

| AckMode | Thời điểm commit | Trường hợp phù hợp |
|---|---|---|
| `RECORD` | Sau khi listener xử lý thành công từng record | Cần commit sát từng record, giảm số record có thể bị phát lại khi lỗi |
| `BATCH` | Sau khi tất cả record trong một batch poll được xử lý thành công | Cần cân bằng giữa thông lượng và độ an toàn; đây là mặc định phổ biến |
| `TIME` | Commit các offset đang chờ khi đã đủ khoảng thời gian cấu hình kể từ lần commit trước | Muốn giới hạn tần suất commit theo thời gian |
| `COUNT` | Commit các offset đang chờ khi đã xử lý đủ số record cấu hình kể từ lần commit trước | Muốn commit theo ngưỡng số record |
| `COUNT_TIME` | Commit các offset đang chờ khi đạt ngưỡng thời gian hoặc số record | Kết hợp giới hạn theo thời gian và số lượng |
| `MANUAL` | Listener gọi `acknowledge()`; offset được xử lý theo cơ chế batch sau khi các record của poll hoàn tất | Ứng dụng muốn chủ động xác nhận nhưng vẫn gom commit |
| `MANUAL_IMMEDIATE` | Listener gọi `acknowledge()` và container commit ngay nếu lời gọi diễn ra trên consumer thread | Cần commit ngay sau một điều kiện xử lý cụ thể |

Với `TIME`, `COUNT` và `COUNT_TIME`, container theo dõi các offset đã xử lý thành công và commit phần đang chờ khi ngưỡng tương ứng đạt được. Các ngưỡng này không cho phép commit vượt qua record chưa xử lý. Với `MANUAL_IMMEDIATE`, nên gọi `acknowledge()` trên consumer thread để có hành vi commit ngay dễ dự đoán. Trộn cách acknowledge trên consumer thread và thread khác có thể làm thay đổi thời điểm commit.

### RECORD và BATCH

Với `RECORD`, container commit sau mỗi lần listener hoàn tất một record thành công. Nếu xử lý record offset `20` thành công và offset `21` lỗi, tiến độ có thể được lưu đến `21`; record lỗi sẽ được xử lý lại theo error handling và offset của nó.

Với `BATCH`, container đợi tất cả record trong poll được xử lý thành công rồi mới commit. Nếu một record trong batch lỗi và chưa được phục hồi, commit của batch có thể bị trì hoãn; những record trước đó trong cùng batch có thể được giao lại. Điều này thường tăng hiệu quả commit nhưng có thể làm phạm vi phát lại lớn hơn.

### MANUAL và MANUAL_IMMEDIATE

Khi chọn chế độ manual, phương thức listener nhận thêm tham số `Acknowledgment`. Ứng dụng gọi `acknowledge()` sau khi điều kiện nghiệp vụ đã đạt.

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual
```

```java
@Component
public class OrderListener {
    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrder(String payload, Acknowledgment acknowledgment) {
        orderService.process(payload); // Ném lỗi nếu nghiệp vụ chưa hoàn tất.
        acknowledgment.acknowledge();  // Chỉ xác nhận sau khi xử lý thành công.
    }
}
```

Với `MANUAL`, lời gọi `acknowledge()` đánh dấu offset để container commit theo cơ chế batch. Với `MANUAL_IMMEDIATE`, container commit ngay nếu lời gọi diễn ra trên consumer thread. Không gọi acknowledge trước khi thao tác nghiệp vụ đã hoàn tất và dữ liệu cần thiết đã được lưu bền vững.

Manual acknowledgment không làm cho hệ thống tự động exactly-once. Nếu database commit thành công nhưng ứng dụng dừng trước khi Kafka offset được commit, record có thể được giao lại. Service xử lý vẫn cần idempotency hoặc cơ chế phối hợp dữ liệu phù hợp.

## 6. Chọn chiến lược theo delivery semantics

Commit offset quyết định khi nào Kafka xem record đã được consumer xử lý đến đâu. Ba cách nhìn phổ biến:

### At-most-once

Offset được commit trước khi tác dụng phụ nghiệp vụ hoàn tất. Nếu ứng dụng dừng sau commit nhưng trước khi xử lý xong, record có thể không được giao lại. Cách này ưu tiên tránh xử lý lặp và chấp nhận nguy cơ mất xử lý.

### At-least-once

Ứng dụng xử lý record thành công trước, sau đó mới commit offset. Nếu ứng dụng dừng sau khi xử lý nhưng trước commit, record sẽ được giao lại. Cách này tránh bỏ qua record chưa hoàn tất nhưng yêu cầu handler idempotent để chịu được xử lý lặp.

### Exactly-once

Commit offset thủ công hay chọn `RECORD` không tự tạo exactly-once. Với luồng Kafka consume-transform-produce, có thể dùng Kafka transaction để ghi output record và offset trong cùng transaction; consumer downstream dùng `isolation.level=read_committed` để chỉ đọc dữ liệu đã commit. Với side effect bên ngoài Kafka như ghi database hoặc gọi API, vẫn cần outbox/inbox, transaction phù hợp hoặc idempotency để phối hợp.

| Mục tiêu | Thứ tự xử lý điển hình | Rủi ro cần xử lý |
|---|---|---|
| At-most-once | Commit rồi mới xử lý | Có thể mất record nếu xử lý lỗi sau commit |
| At-least-once | Xử lý thành công rồi commit | Có thể xử lý lặp nếu dừng trước commit |
| Exactly-once trong Kafka | Ghi output và offset trong Kafka transaction | Phải cấu hình transaction và isolation đúng; không bao gồm tự động side effect ngoài Kafka |

Trong phần lớn hệ thống nghiệp vụ, at-least-once kết hợp xử lý idempotent là lựa chọn dễ vận hành và dễ phục hồi. Chỉ chọn exactly-once khi yêu cầu và ranh giới dữ liệu thực sự cần, đồng thời hiểu rõ phạm vi bảo đảm.

## 7. Commit đồng bộ và bất đồng bộ trong listener container

Khi container thực hiện commit, Spring Kafka mặc định sử dụng commit đồng bộ (`syncCommits=true`). Commit đồng bộ chờ broker phản hồi, giúp container biết commit có thành công hay gặp lỗi. Có thể chuyển sang commit bất đồng bộ bằng cấu hình container properties nếu cần giảm thời gian chờ, nhưng phải xử lý callback và nguy cơ các lần commit hoàn tất không theo thứ tự mong muốn.

Ví dụ cấu hình factory bằng Java:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    factory.getContainerProperties().setSyncCommits(true);
    return factory;
}
```

Với `syncCommits=true`, container sử dụng `commitSync()`. Nếu đặt `false`, container sử dụng `commitAsync()` và có thể đăng ký callback để quan sát kết quả. Hãy đo độ trễ commit và thông lượng trước khi thay đổi; async commit không phải lúc nào cũng nhanh hơn tổng thể nếu broker hoặc mạng đang quá tải.

## 8. Rebalance, restart và offset đang chờ commit

Khi consumer rời group, mất kết nối hoặc partition được phân công lại, Kafka thực hiện rebalance. Partition có thể chuyển từ consumer này sang consumer khác. Consumer mới tiếp tục từ committed offset gần nhất của group.

Nếu ứng dụng đã xử lý một số record nhưng chưa commit trước khi partition bị thu hồi, các record đó có thể được consumer mới đọc lại. Listener container phối hợp với vòng đời consumer và rebalance để quản lý commit; ứng dụng không nên giả định partition luôn thuộc về cùng một instance.

Một số tình huống cần kiểm tra:

- **Ứng dụng dừng sau xử lý, trước commit:** record có thể được giao lại; cần idempotent.
- **Ứng dụng commit trước xử lý:** record có thể bị bỏ qua khi xử lý lỗi.
- **Rebalance trong khi xử lý kéo dài:** cần kiểm soát thời gian xử lý, `max.poll.interval.ms` và concurrency để tránh consumer bị xem là không còn poll kịp.
- **Consumer restart khi có retry:** xác minh error handler, ack mode và offset để hiểu record sẽ được retry tại chỗ hay được giao lại.

Không nên xử lý bất đồng bộ rồi acknowledge ngay khi mới gửi tác vụ sang executor. Nếu thread nền chưa hoàn tất mà offset đã commit, ứng dụng có thể mất xử lý khi process dừng. Nếu cần xử lý bất đồng bộ, phải phối hợp completion, thứ tự theo partition và commit offset theo đúng tiến độ đã hoàn tất.

## 9. Phân biệt các thuộc tính offset thường bị nhầm

| Thuộc tính/API | Ý nghĩa | Có quyết định thời điểm commit không? |
|---|---|---|
| `enable.auto.commit` | Bật/tắt cơ chế Kafka client tự commit nền | Có, khi bật thì Kafka client tự commit theo chu kỳ |
| `auto.commit.interval.ms` | Chu kỳ auto-commit khi `enable.auto.commit=true` | Chỉ ảnh hưởng auto-commit |
| `spring.kafka.listener.ack-mode` | Chọn chiến lược commit do Spring Kafka listener container quản lý | Có |
| `auto.offset.reset` | Chọn vị trí bắt đầu khi group không có committed offset hợp lệ | Không; không phải cơ chế commit |
| `Acknowledgment.acknowledge()` | Báo với container rằng ứng dụng đã xử lý đến offset tương ứng | Có, trong chế độ manual |
| `commitSync()` / `commitAsync()` | API commit offset trực tiếp của Kafka Consumer | Có, khi ứng dụng tự quản lý consumer |

Đặc biệt, `auto.offset.reset=earliest` không có nghĩa consumer luôn đọc lại từ đầu. Khi group đã có committed offset hợp lệ, Kafka tiếp tục từ offset đó. Muốn đọc lại dữ liệu cần thay đổi offset có chủ đích hoặc dùng group ID khác, đồng thời bảo đảm dữ liệu vẫn còn trong retention.

## 10. Kiểm thử chiến lược commit

Kiểm thử nên xác minh kết quả xử lý và vị trí offset sau các tình huống thành công, lỗi và restart. Với Spring Kafka, có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với dòng Spring Boot; một số tình huống cần broker thật hoặc container Kafka để mô phỏng rebalance và restart sát thực tế.

Các kịch bản hữu ích:

1. Gửi một record, xác nhận listener xử lý thành công và offset được commit theo `RECORD`.
2. Gửi nhiều record trong một poll, xác nhận `BATCH` chỉ commit sau khi batch hoàn tất.
3. Cấu hình `MANUAL`, xác nhận offset chưa commit trước `acknowledge()` và được commit sau lời gọi đó.
4. Làm listener ném exception, xác nhận error handler retry hoặc phục hồi theo cấu hình và offset không bị tiến qua record chưa xử lý.
5. Dừng ứng dụng sau khi side effect hoàn tất nhưng trước commit, khởi động lại và xác nhận record có thể được giao lại mà không tạo tác dụng phụ trùng.
6. Kiểm tra group mới với `auto-offset-reset=earliest` và group đã có committed offset để thấy hai hành vi khác nhau.

Không chỉ kiểm tra log “listener đã nhận message”. Cần kiểm tra kết quả nghiệp vụ, committed offset của group và hành vi sau restart để xác minh chiến lược commit thực sự hoạt động.

## 11. Lựa chọn thực tế cho ứng dụng Spring Kafka

| Nhu cầu | Cấu hình/chiến lược khuyến nghị | Lý do |
|---|---|---|
| Consumer xử lý record độc lập, cần commit sát từng record | `enable-auto-commit=false`, `AckMode.RECORD` | Container commit sau khi từng listener invocation thành công |
| Muốn cân bằng thông lượng và commit | `enable-auto-commit=false`, `AckMode.BATCH` | Gom commit theo batch poll, là mặc định phổ biến |
| Nghiệp vụ cần quyết định rõ lúc xác nhận | `enable-auto-commit=false`, `AckMode.MANUAL` | Listener chỉ acknowledge sau khi điều kiện nghiệp vụ đạt |
| Cần commit ngay tại thời điểm listener xác nhận | `enable-auto-commit=false`, `AckMode.MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread |
| Luồng consume-transform-produce cần atomic trong Kafka | Kafka transaction và listener container transactional | Output record và offset có thể được commit trong cùng transaction |

Đối với ứng dụng messaging nghiệp vụ, cấu hình khởi đầu hợp lý thường là `enable-auto-commit=false` và `AckMode.BATCH` hoặc `RECORD`. Chọn `RECORD` khi muốn ranh giới commit theo từng record; chọn `BATCH` khi muốn gom commit và chấp nhận khả năng phát lại một phần batch khi lỗi. Chỉ dùng manual acknowledgment khi có yêu cầu nghiệp vụ cụ thể cần kiểm soát thời điểm xác nhận.

## 12. Tổng kết

- `enable.auto.commit=true` cho phép Kafka client tự commit theo chu kỳ, không chờ ứng dụng xác nhận xử lý nghiệp vụ.
- Tắt auto-commit để commit sau khi xử lý thành công; Kafka Consumer cung cấp `commitSync()` và `commitAsync()`.
- Spring Kafka từ phiên bản 2.3 tự tắt auto-commit nếu không được cấu hình rõ, để listener container quản lý commit.
- `AckMode.RECORD`, `BATCH`, `TIME`, `COUNT`, `COUNT_TIME`, `MANUAL` và `MANUAL_IMMEDIATE` quy định thời điểm container commit.
- At-least-once thường yêu cầu xử lý idempotent; exactly-once cần Kafka transaction trong phạm vi Kafka và thiết kế riêng cho side effect bên ngoài.
- Rebalance, restart và xử lý bất đồng bộ đều có thể dẫn đến record được giao lại; cần kiểm thử committed offset và kết quả nghiệp vụ.

Khi lựa chọn đúng chiến lược commit, ứng dụng Spring Kafka có thể kiểm soát được sự cân bằng giữa thông lượng, độ trễ, nguy cơ mất record và xử lý lặp. Đây là nền tảng để cấu hình retry, dead-letter và transaction một cách nhất quán trong toàn bộ luồng messaging.
