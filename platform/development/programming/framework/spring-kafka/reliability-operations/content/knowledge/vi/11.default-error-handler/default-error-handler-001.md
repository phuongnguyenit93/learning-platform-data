# Vai trò của DefaultErrorHandler

Trong Spring Kafka, `DefaultErrorHandler` là error handler ở cấp listener container, dùng để xử lý exception phát sinh khi listener xử lý record hoặc batch. Nó quyết định record thất bại có được thử lại hay không, khoảng cách giữa các lần thử, khi nào chuyển sang recovery và liệu offset có được xác nhận sau khi recovery thành công hay không.

`DefaultErrorHandler` triển khai `CommonErrorHandler` và là cơ chế thay thế cho các error handler cũ như `SeekToCurrentErrorHandler` trong các phiên bản Spring Kafka hiện đại. Nó giúp ứng dụng gom chính sách retry và recovery vào cấu hình container thay vì tự viết vòng lặp retry trong từng listener.

Error handler không làm cho nghiệp vụ tự động thành công. Nó điều phối việc xử lý lỗi ở tầng Kafka listener. Ứng dụng vẫn phải phân loại lỗi, chọn backoff phù hợp, quyết định nơi lưu record không xử lý được và thiết kế idempotency cho các lần giao lại.

## 1. DefaultErrorHandler nằm ở đâu trong luồng xử lý?

Listener container quản lý consumer, poll record, gọi listener và xác nhận offset. Khi listener ném exception, container chuyển quyền xử lý lỗi cho error handler được cấu hình. Với `DefaultErrorHandler`, trình tự khái quát như sau:

```text
Kafka consumer poll()
        |
        v
Listener nhận record
        |
        v
Thực hiện nghiệp vụ
        |
        +---- thành công ----> container tiếp tục theo AckMode
        |
        +---- exception -----> DefaultErrorHandler
                                  |
                                  v
                           Phân loại exception
                                  |
                       +----------+----------+
                       |                     |
                 Retry được phép       Không retry / hết retry
                       |                     |
                       v                     v
                 BackOff rồi thử lại     Recoverer
                                             |
                                  +----------+----------+
                                  |                     |
                              Recovery OK          Recovery lỗi
                                  |                     |
                                  v                     v
                           Xử lý offset theo      Record có thể được
                           cấu hình container     giao lại / thử lại
```

Error handler làm việc trong vòng đời của listener container. Nó không phải một service nghiệp vụ và cũng không phải một listener riêng. Cấu hình handler trên container factory để các listener sử dụng factory đó có cùng chính sách xử lý lỗi.

## 2. Vai trò chính của DefaultErrorHandler

`DefaultErrorHandler` đảm nhiệm một số trách nhiệm liên quan:

- **Phân loại exception:** xác định exception nào có thể retry và exception nào được xem là không thể phục hồi bằng retry.
- **Retry:** gọi lại việc xử lý record theo chính sách retry của container.
- **Backoff:** chờ giữa các lần thử để tránh gửi yêu cầu dồn dập tới dependency đang lỗi.
- **Recovery:** sau khi hết số lần thử, gọi `ConsumerRecordRecoverer` để ghi log, đưa record sang DLT hoặc thực hiện hành động phục hồi khác.
- **Quản lý việc tiếp tục đọc:** phối hợp seek hoặc cơ chế phát lại record tùy cấu hình và phiên bản Spring Kafka.
- **Phối hợp offset:** sau khi error handler xử lý xong mà không ném exception, container quyết định xác nhận offset theo cấu hình acknowledgment.

Việc tách chính sách lỗi khỏi listener giúp listener tập trung vào nghiệp vụ. Listener chỉ cần ném exception khi không thể hoàn tất xử lý; container và handler chịu trách nhiệm retry/recovery theo cấu hình chung.

## 3. Cấu hình cơ bản

Một cấu hình thường gặp tạo `DefaultErrorHandler` với `DeadLetterPublishingRecoverer` và `FixedBackOff`:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler defaultErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

Trong ví dụ này, `FixedBackOff(1_000L, 2L)` chờ một giây giữa các lần retry và cho phép hai lần retry sau lần giao đầu tiên. Nếu lần đầu và cả hai lần retry đều thất bại, handler gọi recoverer. Tổng cộng listener có thể được gọi ba lần cho record đó trước recovery.

Gắn handler vào `ConcurrentKafkaListenerContainerFactory`:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, Order> orderListenerFactory(
        ConsumerFactory<String, Order> consumerFactory,
        DefaultErrorHandler defaultErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(defaultErrorHandler);
    return factory;
}
```

Listener sử dụng factory này bằng `containerFactory`:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "orderListenerFactory")
public void onOrder(Order order) {
    orderService.process(order);
}
```

Nếu ứng dụng có nhiều nhóm listener với yêu cầu khác nhau, có thể tạo nhiều factory và gắn error handler riêng cho từng nhóm. Tránh thay đổi chính sách retry toàn ứng dụng chỉ để đáp ứng một listener đặc biệt.

## 4. Retry và BackOff

Retry là việc container thử xử lý lại record sau khi listener thất bại. Backoff là khoảng chờ giữa các lần thử. Nếu retry ngay lập tức trong khi dependency đang gián đoạn, ứng dụng có thể tạo thêm tải và làm tình trạng lỗi kéo dài.

Spring Kafka hỗ trợ các chiến lược backoff từ Spring Framework, chẳng hạn:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| `FixedBackOff` | Chờ một khoảng thời gian cố định giữa các lần thử | Lỗi tạm thời có thời gian phục hồi tương đối ổn định. |
| `ExponentialBackOff` | Tăng thời gian chờ sau mỗi lần thất bại | Dependency cần thời gian phục hồi dài hơn khi lỗi kéo dài. |
| `ExponentialBackOffWithMaxRetries` | Backoff tăng dần nhưng giới hạn số lần retry | Cần kiểm soát cả thời gian chờ lẫn tổng số lần thử. |

Ví dụ dùng fixed backoff:

```java
var backOff = new FixedBackOff(2_000L, 3L);
var handler = new DefaultErrorHandler(recoverer, backOff);
```

Ví dụ này cho phép ba lần retry sau lần đầu, với khoảng chờ hai giây giữa các lần thử. Hãy phân biệt số lần retry với tổng số lần listener được gọi: lần giao đầu tiên không phải là một lần retry.

Với exponential backoff, có thể đặt khoảng ban đầu, hệ số nhân và giới hạn thời gian chờ:

```java
var backOff = new ExponentialBackOff(1_000L, 2.0);
backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

var handler = new DefaultErrorHandler(recoverer, backOff);
```

Giá trị cụ thể cần được chọn theo thời gian phục hồi của dependency và SLA của luồng. Retry quá lâu có thể làm partition bị giữ lại, consumer lag tăng và các record phía sau phải chờ. Retry quá ngắn có thể tạo tải lặp lên hệ thống đang lỗi.

### 4.1 Retry không phải là vòng lặp trong listener

Không nên tự viết vòng lặp `while` hoặc `for` để retry nghiệp vụ bên trong listener nếu container đã quản lý retry. Vòng lặp nội bộ có thể giữ consumer thread quá lâu, làm `max.poll.interval.ms` bị vượt và khiến việc theo dõi số lần thử trở nên khó khăn.

Thay vào đó, để exception truyền ra khỏi listener:

```java
@KafkaListener(topics = "${app.topics.orders-in}")
public void onOrder(Order order) {
    orderService.process(order); // Ném exception nếu cần retry
}
```

Nếu bắt exception để ghi log, hãy ném lại exception khi muốn container retry. Nếu bắt rồi bỏ qua, container có thể xem listener đã hoàn tất bình thường và offset có thể được xác nhận.

## 5. Phân loại exception: lỗi nào nên retry?

Không phải mọi exception đều được giải quyết bằng cách thử lại. Ví dụ timeout kết nối tới dịch vụ khách hàng có thể là lỗi tạm thời; payload thiếu trường bắt buộc thường sẽ thất bại giống nhau ở mọi lần retry.

`DefaultErrorHandler` có phân loại exception mặc định. Một số loại lỗi chuyển đổi và ánh xạ message, như lỗi deserialize hoặc message conversion, được xem là không retry theo mặc định vì thử lại cùng dữ liệu thường không làm record hợp lệ hơn. Các exception khác thường có thể retry, trừ khi ứng dụng thay đổi classification.

Có thể đánh dấu exception nghiệp vụ không retry:

```java
var handler = new DefaultErrorHandler(recoverer, backOff);
handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedCurrencyException.class);
```

Hoặc đánh dấu loại lỗi cần retry rõ ràng:

```java
var handler = new DefaultErrorHandler(recoverer, backOff);
handler.addRetryableExceptions(
        PartnerUnavailableException.class,
        TemporaryDatabaseException.class);
```

Hãy xây dựng phân loại theo nguyên nhân nghiệp vụ, không chỉ theo tên exception kỹ thuật. Một `RuntimeException` có thể bao bọc lỗi vĩnh viễn hoặc lỗi tạm thời; nếu cần, hãy phân tích cause chain và định nghĩa exception cụ thể ở tầng service.

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout, connection reset, HTTP 503 | Retry có giới hạn và backoff. |
| Lỗi dữ liệu không hợp lệ | Thiếu ID, schema không tương thích | Không retry; chuyển recovery/DLT. |
| Lỗi nghiệp vụ vĩnh viễn | Trạng thái đơn hàng không cho phép thao tác | Không retry hoặc đưa vào luồng xử lý nghiệp vụ riêng. |
| Lỗi cấu hình | Sai credentials, endpoint hoặc serializer | Cảnh báo và xử lý cấu hình; retry liên tục thường không có ích. |

## 6. Recovery sau khi hết retry

Khi số lần thử đã hết, `DefaultErrorHandler` gọi recoverer. Recoverer là thành phần quyết định phải làm gì với record không xử lý được. Có thể ghi log, lưu vào kho cách ly, phát sang Dead Letter Topic hoặc gọi một quy trình nghiệp vụ khác.

Nếu không cung cấp recoverer tùy chỉnh, handler mặc định sử dụng logging recoverer để ghi nhận record thất bại. Điều này có thể hữu ích khi đang phát triển hoặc khi chính sách vận hành yêu cầu chỉ log, nhưng log không phải nơi lưu trữ bền vững để replay record.

### 6.1 Dead Letter Topic

`DeadLetterPublishingRecoverer` gửi record thất bại sang một topic khác để điều tra hoặc xử lý lại. Cách dùng cơ bản:

```java
var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L));
```

Theo quy tắc mặc định thông dụng, record từ topic `orders` được gửi tới `orders.DLT` và giữ partition tương ứng. Topic DLT vì vậy cần có số partition đủ để nhận partition được ánh xạ từ topic nguồn. Có thể cấu hình destination resolver riêng nếu muốn đặt tên DLT khác hoặc định tuyến theo exception/topic.

DLT nên giữ thông tin giúp điều tra và replay:

- Topic, partition và offset nguồn.
- Key, timestamp và payload gốc.
- Exception type, message và stack trace trong headers do recoverer bổ sung.
- Event ID, correlation ID hoặc trace context nếu nguồn có cung cấp.

Không đưa payload nhạy cảm vào log hoặc DLT nếu chính sách dữ liệu không cho phép. DLT là một phần của data lifecycle, cần retention, quyền truy cập và quy trình xử lý rõ ràng.

### 6.2 Recovery thất bại

Nếu recoverer không thể gửi record sang DLT hoặc thao tác recovery ném exception, record chưa được phục hồi thành công. Tùy cấu hình và trạng thái container, record có thể được thử lại hoặc quay lại quy trình xử lý lỗi. Không nên xác nhận offset như thể recovery đã hoàn tất nếu record chưa được lưu an toàn.

Hãy giám sát lỗi gửi DLT riêng với lỗi listener. Một hệ thống có thể xử lý listener bình thường nhưng DLT broker/topic/serializer bị lỗi, khiến recovery không thể hoàn thành.

## 7. Offset sau recovery và acknowledgment

Sau khi error handler xử lý xong mà không ném exception, container cần quyết định có xác nhận offset của record đã được recover hay không. `DefaultErrorHandler` mặc định cho phép container acknowledge sau khi handler hoàn tất bình thường (`ackAfterHandle` mặc định là `true`). Có thể thay đổi hành vi này nếu ứng dụng có yêu cầu đặc biệt.

Ví dụ:

```java
handler.setAckAfterHandle(false);
```

Khi tắt `ackAfterHandle`, container không tự acknowledge record chỉ vì error handler trả về bình thường. Cần hiểu rõ tác động của AckMode và cách listener container tiếp tục xử lý để tránh record bị phát lại ngoài ý muốn.

`DefaultErrorHandler` cũng có tùy chọn `commitRecovered`. Khi bật, handler có thể commit offset của record đã recover theo cơ chế được hỗ trợ; với cấu hình này, container cần dùng `AckMode.MANUAL_IMMEDIATE` để commit recovered record ngay trên consumer thread:

```java
var handler = new DefaultErrorHandler(recoverer, backOff);
handler.setCommitRecovered(true);
```

Chỉ bật `commitRecovered` khi đã cấu hình acknowledgment mode đúng và có chủ đích. Không bật cùng lúc nhiều cơ chế commit mà không hiểu rõ ai đang sở hữu việc xác nhận offset.

Với `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE`, listener chủ động acknowledge khi xử lý thành công. Nếu listener ném exception trước khi acknowledge, error handler và container phối hợp theo semantics của manual acknowledgment. Hãy kiểm thử trường hợp listener thất bại, recovery thành công và recovery thất bại với đúng AckMode đang dùng.

## 8. Record listener và batch listener

Đối với record listener, `DefaultErrorHandler` có thể xác định record gây lỗi và áp dụng retry/recovery cho record đó. Các record chưa xử lý phía sau được xử lý lại theo cơ chế seek hoặc resubmission của container.

Với batch listener, một lần gọi listener nhận nhiều record. Nếu batch listener ném exception thông thường, handler không nhất thiết biết record nào trong batch gây lỗi. Khi đó, toàn bộ batch có thể được thử lại.

Nếu listener xác định được record thất bại, có thể ném `BatchListenerFailedException` cùng vị trí record hoặc record tương ứng:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "batchListenerFactory")
public void onOrders(List<ConsumerRecord<String, Order>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.process(records.get(index).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Cannot process order in batch", ex, index);
        }
    }
}
```

`BatchListenerFailedException` cho handler biết vị trí record thất bại. Container có thể commit các record trước vị trí đó theo semantics phù hợp, rồi retry hoặc recover record lỗi cùng các record còn lại. Cách xử lý cụ thể còn phụ thuộc AckMode, listener type và phiên bản Spring Kafka.

Với batch listener, hãy xác định rõ thứ tự xử lý, khả năng một phần batch đã tạo tác dụng phụ và tính idempotent của các record được retry. Nếu xử lý record đầu tiên thành công rồi record thứ ba thất bại, lần gọi batch sau có thể chạy lại record đã xử lý trước đó.

## 9. Deserialization và lỗi xảy ra trước listener

Một record có thể thất bại trước khi phương thức `@KafkaListener` được gọi, ví dụ deserializer không thể chuyển byte thành object. Khi đó listener không nhận được payload đã giải mã để tự ném exception.

Để đưa lỗi deserialization vào luồng error handling của Spring Kafka, thường cấu hình `ErrorHandlingDeserializer` làm lớp bọc cho deserializer thực tế. Nó giữ thông tin lỗi trong header để container/error handler có thể xử lý record lỗi và chuyển sang DLT theo chính sách.

Ví dụ cấu hình YAML:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
```

Đây là ví dụ khung; ứng dụng cần cấu hình trusted packages, type mapping hoặc default target type cho JSON deserializer theo schema thực tế. Không thể sửa lỗi payload không hợp lệ bằng cách retry liên tục cùng một byte sequence; hãy chọn recovery phù hợp.

## 10. Seek và resubmission sau lỗi

Theo mặc định, `DefaultErrorHandler` dùng cơ chế seek để đưa consumer trở lại vị trí cần xử lý lại sau exception. Các record chưa được xử lý có thể được phát lại từ offset phù hợp trong partition.

Ở các phiên bản Spring Kafka hỗ trợ, có thể cấu hình `seekAfterError(false)` để container giữ các record chưa xử lý và đưa chúng lại cho listener sau một lần poll ngắn nhằm giữ consumer hoạt động. Cách này thay đổi cách container điều phối việc phát lại, nhưng không thay đổi nguyên tắc: record chưa hoàn tất phải được xử lý lại hoặc được recovery rõ ràng trước khi offset tiến qua nó.

Không nhầm seek với retry topic. Seek-based retry giữ record trong luồng partition hiện tại và có thể chặn các record phía sau cùng partition trong thời gian retry. Retry topic là một kiến trúc khác, phát record sang topic retry để consumer tiếp tục xử lý các record sau; đổi lại, thứ tự theo partition có thể thay đổi.

## 11. DefaultErrorHandler và Kafka transaction

`DefaultErrorHandler` thường được dùng với listener container không transactional để quản lý retry/recovery trong vòng đời consumer. Với container dùng Kafka transaction, listener exception làm transaction rollback; Spring Kafka dùng `AfterRollbackProcessor`, mặc định thường là `DefaultAfterRollbackProcessor`, để điều phối việc seek, retry và recovery sau rollback.

Không coi `DefaultErrorHandler` là thay thế cho rollback processor trong mô hình transactional. Chọn cơ chế theo cách container được cấu hình:

| Mô hình listener | Cơ chế xử lý lỗi cần xem xét |
|---|---|
| Container không dùng Kafka transaction | `DefaultErrorHandler` với BackOff và recoverer. |
| Container dùng Kafka transaction | Rollback và `DefaultAfterRollbackProcessor`/`AfterRollbackProcessor`. |
| Ghi output Kafka và commit input offset cùng nhau | Transaction manager điều phối commit; exception dẫn tới rollback và quy trình after-rollback. |

Với transactional listener, recovery như gửi DLT cũng cần được thiết kế theo transaction semantics. Hãy cấu hình `AfterRollbackProcessor` phù hợp để việc publish DLT và xác nhận offset gốc không tạo ra khoảng mất dữ liệu. Không trộn cấu hình error handler non-transactional vào transactional container mà không kiểm tra tài liệu phiên bản Spring Kafka.

## 12. Retry blocking và retry topic

`DefaultErrorHandler` thường thực hiện blocking retry: consumer tiếp tục xử lý lại record lỗi trên partition đó theo backoff. Trong thời gian này, record phía sau cùng partition có thể phải chờ. Cách này phù hợp khi cần giữ thứ tự và lỗi có khả năng phục hồi trong thời gian ngắn.

Spring Kafka cũng có mô hình non-blocking retry topic, thường cấu hình qua `@RetryableTopic` hoặc cơ chế retry topic tương ứng. Record được chuyển sang retry topic với độ trễ; consumer của topic gốc có thể tiếp tục xử lý record tiếp theo. Cách này có thể tăng throughput khi lỗi kéo dài nhưng có thể làm thay đổi thứ tự xử lý và cần quản lý nhiều topic hơn.

Không dùng retry topic và `DefaultErrorHandler` như hai tên gọi cho cùng một cơ chế. Hãy quyết định dựa trên yêu cầu thứ tự, thời gian retry, khả năng chặn partition và độ phức tạp vận hành.

## 13. Quan sát và vận hành

Một chính sách retry chỉ hữu ích khi vận hành có thể nhìn thấy nó đang hoạt động như thế nào. Theo dõi:

- Số lần listener thất bại theo topic, exception type và consumer group.
- Số lần retry, tổng thời gian backoff và số record được recover.
- Số record được gửi sang DLT và lỗi gửi DLT.
- Consumer lag theo partition trong thời gian retry.
- Thời gian xử lý thành công so với thời gian xử lý sau retry.
- Exception classification để phát hiện lỗi vĩnh viễn đang bị retry hoặc lỗi tạm thời bị đưa vào DLT quá sớm.

Log nên có topic, partition, offset, key hoặc event ID, exception class và delivery attempt nếu ứng dụng bật header delivery attempt. Tránh log toàn bộ payload nhạy cảm.

DLT cần dashboard hoặc quy trình vận hành riêng. Cần biết ai xử lý record, khi nào replay, replay vào topic nào và làm thế nào ngăn tác dụng phụ bị thực hiện hai lần. Không replay toàn bộ DLT một cách tự động nếu chưa kiểm tra schema, nguyên nhân lỗi và idempotency.

## 14. Kiểm thử DefaultErrorHandler

Kiểm thử tích hợp nên dùng broker thật trong môi trường test, chẳng hạn Embedded Kafka hoặc Kafka Testcontainers. Hãy xác minh hành vi quan sát được ở output, DLT và consumer offset.

Các kịch bản nên có:

1. Listener thành công ở lần đầu; xác nhận không có retry và output/side effect đúng.
2. Listener lỗi tạm thời một vài lần rồi thành công; xác nhận số lần thử và khoảng backoff.
3. Listener luôn ném exception; xác nhận recoverer được gọi sau khi hết retry.
4. Exception được phân loại non-retryable; xác nhận recovery diễn ra mà không lặp lại không cần thiết.
5. Recoverer gửi record sang DLT; xác nhận payload, key và metadata nguồn.
6. Gửi DLT thất bại; xác nhận record không bị xác nhận như thể recovery đã hoàn tất.
7. Với batch listener, ném `BatchListenerFailedException` tại một index; xác nhận record trước đó và record lỗi được xử lý theo cấu hình.
8. Gửi payload không deserialize được; xác nhận `ErrorHandlingDeserializer` và error handler chuyển record lỗi tới recovery.
9. Dừng consumer trong thời gian backoff hoặc retry; xác nhận record có thể được giao lại và nghiệp vụ idempotent.
10. Với transactional listener, kiểm tra rollback và `DefaultAfterRollbackProcessor` thay vì giả định `DefaultErrorHandler` điều khiển transaction.

Không dùng `Thread.sleep()` cố định để kết luận retry hoặc DLT đã xảy ra. Hãy chờ điều kiện cụ thể như số lần listener được gọi, record xuất hiện ở DLT hoặc offset tiến tới vị trí mong đợi, với timeout hữu hạn.

## 15. Những lỗi thường gặp

- **Nuốt exception trong listener:** container có thể xem xử lý là thành công và không gọi error handler.
- **Retry vô hạn không backoff:** làm dependency quá tải và giữ partition trong trạng thái lỗi kéo dài.
- **Retry lỗi dữ liệu vĩnh viễn:** lặp lại cùng một payload không hợp lệ mà không thể sửa nguyên nhân.
- **Không cấu hình recoverer:** record hết retry chỉ được log theo hành vi mặc định, không có luồng DLT bền vững để replay.
- **Không theo dõi lỗi DLT:** recovery có thể thất bại nhưng hệ thống không phát hiện.
- **Cho rằng mọi exception đều retry:** một số exception được phân loại fatal/non-retryable theo mặc định hoặc cấu hình ứng dụng.
- **Nhầm số retry với tổng số lần gọi:** số lần retry không tính lần giao đầu tiên.
- **Không phân biệt record và batch listener:** batch có thể được retry toàn bộ nếu handler không biết record lỗi.
- **Dùng sai cơ chế cho transactional container:** listener transaction cần rollback processor và semantics transaction phù hợp.
- **Cho rằng DLT replay luôn an toàn:** replay có thể lặp lại tác dụng phụ nếu nghiệp vụ không idempotent.

## 16. Khi nào nên dùng DefaultErrorHandler?

Dùng `DefaultErrorHandler` khi listener container không transactional cần một chính sách retry và recovery có cấu hình rõ ràng. Nó phù hợp với lỗi tạm thời cần backoff, record không hợp lệ cần DLT và ứng dụng muốn tách xử lý lỗi khỏi logic nghiệp vụ.

Hãy bắt đầu bằng việc xác định exception nào retry được, số lần thử và thời gian chờ tối đa. Sau đó chọn recoverer, quyết định cách commit offset sau recovery và bổ sung metric cho retry/DLT. Với batch listener, xác định cách báo chính xác record lỗi. Với transactional listener, dùng rollback processor phù hợp để giữ tính nguyên tử của output và input offset.

`DefaultErrorHandler` là cơ chế điều phối lỗi ở tầng listener container. Hiệu quả của nó phụ thuộc vào việc ứng dụng ném exception đúng lúc, phân loại lỗi đúng bản chất, lưu record thất bại an toàn và làm cho việc retry hoặc replay không gây tác dụng phụ trùng lặp.
