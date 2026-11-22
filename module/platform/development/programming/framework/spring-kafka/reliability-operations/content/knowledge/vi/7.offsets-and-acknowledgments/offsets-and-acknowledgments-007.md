# AckMode MANUAL_IMMEDIATE

Trong Spring Kafka, `AckMode` xác định cách listener container xác nhận offset sau khi xử lý record. Với `MANUAL_IMMEDIATE`, listener chủ động gọi `Acknowledgment.acknowledge()` để yêu cầu container commit offset ngay tại thời điểm gọi. Khi lời gọi diễn ra trên consumer thread của listener, container thực hiện commit ngay thay vì chờ hết batch của lần `poll()` như một số chế độ khác.

Chế độ này hữu ích khi ứng dụng cần kiểm soát rõ thời điểm record được xem là đã xử lý xong. Ví dụ, consumer chỉ acknowledge sau khi đã kiểm tra dữ liệu và lưu kết quả nghiệp vụ thành công. Tuy nhiên, `MANUAL_IMMEDIATE` không tự tạo exactly-once, không tự retry và không làm cho database cùng Kafka trở thành một transaction chung. Độ tin cậy vẫn phụ thuộc vào thời điểm acknowledge, cách xử lý lỗi và việc commit offset có được phối hợp với tác dụng phụ hay không.

## 1. AckMode điều khiển điều gì?

Kafka consumer đọc record theo partition và giữ vị trí đọc hiện tại. Offset được commit là vị trí tiếp theo mà consumer group sẽ đọc khi khởi động hoặc nhận lại partition. Nếu consumer xử lý record ở offset `41`, offset được commit thường là `42`.

Spring Kafka listener container quản lý việc poll, gọi listener và commit offset. `AckMode` quy định thời điểm container xác nhận các record đã xử lý thành công:

| AckMode | Thời điểm commit thông thường | Đặc điểm |
|---|---|---|
| `RECORD` | Sau mỗi record listener xử lý thành công | Ranh giới commit theo từng record. |
| `BATCH` | Sau khi xử lý xong các record nhận từ một lần poll | Commit theo batch; mặc định thường dùng nếu không cấu hình khác. |
| `TIME` | Khi đạt khoảng thời gian commit được cấu hình | Có thể gom nhiều record giữa các lần commit. |
| `COUNT` | Khi đạt số record được cấu hình | Commit theo ngưỡng số lượng. |
| `COUNT_TIME` | Khi đạt ngưỡng count hoặc time | Kết hợp hai ngưỡng. |
| `MANUAL` | Listener gọi `acknowledge()`; container áp dụng semantics commit theo batch của lần poll | Ứng dụng quyết định record nào đã hoàn tất. |
| `MANUAL_IMMEDIATE` | Listener gọi `acknowledge()` trên consumer thread | Commit ngay khi acknowledge được gọi trên đúng thread. |

`MANUAL` và `MANUAL_IMMEDIATE` đều yêu cầu listener chủ động acknowledge. Điểm khác biệt quan trọng là thời điểm commit. Với `MANUAL`, container thường chờ xử lý xong các record của poll rồi mới commit các offset đã được acknowledge. Với `MANUAL_IMMEDIATE`, lời gọi trên consumer thread yêu cầu commit ngay.

## 2. Ví dụ cơ bản với record listener

Listener nhận `Acknowledgment` cùng payload hoặc `ConsumerRecord`. Sau khi xử lý thành công, listener gọi `acknowledge()`:

```java
@Component
public class PaymentListener {

    private final PaymentService paymentService;

    public PaymentListener(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @KafkaListener(
            topics = "${app.topics.payments-in}",
            groupId = "payment-worker",
            containerFactory = "manualImmediateFactory")
    public void onPayment(
            ConsumerRecord<String, PaymentRequested> record,
            Acknowledgment acknowledgment) {

        paymentService.process(record.value());
        acknowledgment.acknowledge();
    }
}
```

Trong ví dụ này, `PaymentService.process()` phải hoàn tất công việc mà ứng dụng xem là thành công trước khi gọi `acknowledge()`. Nếu service ném exception, listener chưa acknowledge record; container có thể chuyển lỗi tới error handler để retry hoặc phục hồi theo cấu hình.

Không nên gọi `acknowledge()` ở đầu listener rồi mới xử lý nghiệp vụ. Khi offset đã được commit, một lỗi xảy ra sau đó không thể làm Kafka tự đưa record trở lại trạng thái chưa xử lý. Record có thể bị mất khỏi luồng xử lý của consumer group dù nghiệp vụ chưa hoàn tất.

## 3. Cấu hình MANUAL_IMMEDIATE

Có thể tạo một listener container factory riêng và đặt `AckMode.MANUAL_IMMEDIATE` trên `ContainerProperties`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>
    manualImmediateFactory(
            ConsumerFactory<String, PaymentRequested> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
        return factory;
    }
}
```

Listener chọn factory bằng thuộc tính `containerFactory` trong `@KafkaListener`. Tên bean phải khớp chính xác với tên tham chiếu. Nếu ứng dụng có nhiều nhóm listener với chính sách xác nhận khác nhau, factory riêng giúp cấu hình rõ ràng theo từng nhóm.

Với Spring Boot, có thể cấu hình listener mặc định qua YAML:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
```

Khi cần cấu hình riêng từng listener, dùng factory tùy chỉnh sẽ rõ ràng hơn việc thay đổi ack mode mặc định của toàn ứng dụng. `enable-auto-commit: false` giúp Spring Kafka container kiểm soát commit theo ack mode. Không bật Kafka consumer auto commit nếu mục tiêu là để `Acknowledgment` quyết định thời điểm xác nhận.

## 4. Điều gì xảy ra khi acknowledge được gọi?

Với record listener chạy trên consumer thread, trình tự cơ bản là:

```text
Kafka consumer poll()
        |
        v
Listener nhận record offset 41
        |
        v
Thực hiện nghiệp vụ
        |
        +---- thất bại ----> ném exception -> error handler
        |
        v
Nghiệp vụ thành công
        |
        v
acknowledgment.acknowledge()
        |
        v
Container commit offset 42 ngay
```

Offset được commit là offset kế tiếp cần đọc, không phải offset của record vừa xử lý. Khi commit thành công, nếu consumer restart hoặc partition được giao cho consumer khác, group có thể tiếp tục từ vị trí sau record đã acknowledge.

`MANUAL_IMMEDIATE` chỉ điều khiển thời điểm container thực hiện commit. Nó không xác nhận rằng database đã ghi bền vững, API bên ngoài đã hoàn tất hoặc một sự kiện đầu ra đã được consumer downstream xử lý. Listener phải định nghĩa rõ thế nào là “xử lý thành công” trước khi acknowledge.

## 5. Consumer thread và lời gọi từ thread khác

Tên `MANUAL_IMMEDIATE` có ý nghĩa chính xác khi `acknowledge()` được gọi trên consumer thread đang chạy listener. Trong trường hợp đó, container có thể commit ngay tại thời điểm gọi.

Nếu gọi `acknowledge()` từ một thread khác, yêu cầu commit được đưa vào hàng đợi và được xử lý sau khi các record của lần poll trước đã được xử lý. Khi đó hành vi không còn là commit ngay tại vị trí gọi theo nghĩa đồng bộ trên consumer thread.

Không trộn lẫn các lời gọi acknowledge trên consumer thread và thread khác trong cùng một listener container. Spring Kafka cảnh báo rằng việc trộn hai kiểu gọi có thể dẫn đến kết quả không xác định về thời điểm commit. Hãy chọn một mô hình xử lý nhất quán.

### 5.1 Xử lý bất đồng bộ

Một số ứng dụng nhận record rồi chuyển công việc sang executor để xử lý nền. Trong mô hình này, listener có thể trả về trước khi công việc hoàn tất. Nếu muốn acknowledge sau khi xử lý bất đồng bộ, cần cấu hình và hiểu rõ semantics của phiên bản Spring Kafka đang dùng.

Spring Kafka hỗ trợ `asyncAcks` cho `MANUAL` và `MANUAL_IMMEDIATE` ở các phiên bản phù hợp. Tính năng này cho phép acknowledge các record của một poll không theo thứ tự. Container giữ consumer ở trạng thái pause cho tới khi nhận đủ acknowledgment còn thiếu của poll đó, sau đó mới tiếp tục tiến trình commit/đọc tiếp. Điều này giúp hỗ trợ xử lý song song, nhưng có thể làm tăng độ trễ và tạo thêm khả năng redelivery khi ứng dụng dừng trước khi mọi acknowledgment được nhận.

Ví dụ cấu hình trên listener container:

```java
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE);
factory.getContainerProperties().setAsyncAcks(true);
```

Chỉ bật `asyncAcks` khi thực sự cần xử lý song song và đã thiết kế việc quản lý kết quả bất đồng bộ. Không giữ `Acknowledgment` rồi gọi tùy tiện từ nhiều thread. Mỗi record cần có một kết quả xử lý rõ ràng; khi công việc hoàn tất, acknowledge đúng đối tượng và không acknowledge hai lần ngoài ý muốn.

## 6. MANUAL_IMMEDIATE và commit đồng bộ/bất đồng bộ

`MANUAL_IMMEDIATE` nói về thời điểm container yêu cầu commit sau lời gọi acknowledge. Cách Kafka client gửi commit có thể được cấu hình riêng:

- `syncCommits` bật commit đồng bộ (`commitSync`); đây là mặc định thông dụng của Spring Kafka container.
- Khi tắt `syncCommits`, container dùng commit bất đồng bộ (`commitAsync`) và callback tương ứng nếu được cấu hình.

Ví dụ đặt commit đồng bộ:

```java
factory.getContainerProperties().setSyncCommits(true);
```

Commit đồng bộ chờ phản hồi commit từ broker trong giới hạn timeout, vì vậy listener thread có thể mất thêm thời gian. Commit bất đồng bộ giảm thời gian chờ tại chỗ nhưng ứng dụng cần theo dõi lỗi trong callback và hiểu rõ khả năng commit thất bại.

Không nhầm `MANUAL_IMMEDIATE` với cam kết rằng broker đã xác nhận thành công ngay tại thời điểm phương thức `acknowledge()` trả về trong mọi cấu hình. Hãy xem cả `syncCommits`, timeout, callback và log commit để hiểu cách ứng dụng quan sát lỗi. Với commit đồng bộ, container chờ kết quả commit; với commit bất đồng bộ, kết quả được xử lý qua callback.

## 7. Kết hợp với transaction của Spring Kafka

Khi listener container chạy trong Kafka transaction, offset được đưa vào transaction và được commit cùng các record output khi transaction hoàn tất. `acknowledge()` vẫn biểu thị record đã được xử lý, nhưng commit offset thực tế chịu sự điều phối của transaction manager/container. Không nên xem lời gọi `MANUAL_IMMEDIATE` trong một listener transactional là cách tách offset ra khỏi transaction.

Ví dụ, một listener có thể gửi output rồi acknowledge:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "transactionalManualFactory")
public void onOrder(
        ConsumerRecord<String, Order> record,
        Acknowledgment acknowledgment) {

    EnrichedOrder output = processor.enrich(record.value());
    kafkaTemplate.send("orders.enriched", record.key(), output);
    acknowledgment.acknowledge();
}
```

Với container transactional được cấu hình đúng, output và offset đầu vào được commit trong cùng Kafka transaction. Nếu transaction rollback, output chưa commit và offset cũng không được commit. `KafkaTemplate` phải tham gia cùng transaction do container quản lý, thường thông qua cùng `ProducerFactory` và transaction manager tương ứng.

Nếu không dùng transaction, acknowledge offset và gửi output là hai thao tác riêng. Gửi output thành công rồi commit offset thất bại có thể khiến record đầu vào được đọc lại và output bị phát trùng. Nếu commit offset trước khi output được ghi bền vững, lỗi gửi có thể làm mất output. Chọn transaction khi cần tính nguyên tử trong phạm vi Kafka; dùng idempotency hoặc outbox khi tác dụng phụ nằm ngoài Kafka.

## 8. Retry và error handling

Nếu listener ném exception trước khi acknowledge, container chuyển lỗi cho error handler. Tùy cấu hình, Spring Kafka có thể retry record, seek lại vị trí đọc hoặc gọi recovery handler để chuyển record sang Dead Letter Topic (DLT).

Một cấu hình `DefaultErrorHandler` có thể giới hạn số lần retry và dùng backoff:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);
    var backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

Đoạn code minh họa cách tạo recoverer và backoff; ứng dụng cần cấu hình serializer, destination resolver và bean error handler phù hợp với kiểu key/value, topology topic và phiên bản Spring Kafka. Với transactional listener, cần dùng cấu hình xử lý lỗi tương thích với transaction và rollback processor; không áp dụng máy móc error handler non-transactional cho container transactional.

Nếu listener đã acknowledge rồi mới ném exception, offset có thể đã được commit (trong trường hợp non-transactional và acknowledge trên consumer thread). Error handler không thể tự đảo ngược commit đó để bảo đảm record được giao lại. Vì vậy, đặt `acknowledge()` sau tất cả bước bắt buộc của lần xử lý.

Phân loại lỗi để chọn chính sách:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Timeout dịch vụ phụ thuộc, broker tạm gián đoạn | Retry có giới hạn và backoff. |
| Lỗi dữ liệu vĩnh viễn | Payload thiếu trường bắt buộc, schema không hợp lệ | Cách ly hoặc DLT, kèm metadata để điều tra. |
| Lỗi nghiệp vụ | Trạng thái đơn hàng không cho phép chuyển bước | Áp dụng chính sách nghiệp vụ; tránh retry vô hạn. |
| Lỗi không thể phục hồi sau retry | Dependency ngừng dài hạn, record vẫn thất bại | Dừng/giảm tốc xử lý hoặc recovery theo chính sách vận hành. |

## 9. Rebalance, redelivery và thời điểm acknowledge

Consumer group có thể rebalance khi instance rời nhóm, mất heartbeat, thay đổi số replica hoặc vượt quá giới hạn thời gian xử lý. Nếu partition được thu hồi trước khi offset của record được commit, record có thể được giao lại cho consumer khác.

`MANUAL_IMMEDIATE` không ngăn rebalance và không bảo đảm record chỉ được gọi listener một lần. Nó chỉ giúp ứng dụng chủ động yêu cầu commit tại thời điểm acknowledge. Nếu commit thất bại vì partition ownership đã thay đổi, record có thể được giao lại. Do đó, nghiệp vụ nên idempotent ngay cả khi dùng manual immediate.

Đặc biệt chú ý `max.poll.interval.ms`. Nếu listener xử lý quá lâu mà không poll tiếp, consumer có thể bị xem là không còn hoạt động và rời group. Với xử lý dài, cân nhắc giảm `max.poll.records`, tối ưu công việc, tăng giới hạn phù hợp hoặc tách tác vụ theo một mô hình bất đồng bộ có acknowledgment được quản lý rõ ràng.

## 10. Record listener và batch listener

Ví dụ thường gặp với `MANUAL_IMMEDIATE` là record listener: mỗi lần gọi listener nhận một record và có thể acknowledge record đó sau khi hoàn tất.

Với batch listener, một lần gọi listener nhận nhiều record từ một lần poll. Acknowledgment ở batch listener có semantics theo batch. Một số phiên bản Spring Kafka cung cấp API acknowledge một phần batch, với các điều kiện sử dụng cụ thể như listener thread và `MANUAL_IMMEDIATE`. Nếu cần partial batch acknowledgment, hãy kiểm tra tài liệu của đúng phiên bản đang chạy trước khi thiết kế; không giả định rằng ví dụ record listener có thể chuyển nguyên trạng sang batch listener.

Ví dụ batch listener cơ bản:

```java
@KafkaListener(
        topics = "${app.topics.events-in}",
        containerFactory = "manualImmediateBatchFactory")
public void onEvents(
        List<ConsumerRecord<String, Event>> records,
        Acknowledgment acknowledgment) {

    for (ConsumerRecord<String, Event> record : records) {
        processor.process(record.value());
    }

    acknowledgment.acknowledge();
}
```

Trong ví dụ này, chỉ acknowledge sau khi toàn bộ batch xử lý thành công. Nếu một record ném exception trước thời điểm acknowledge, error handling sẽ quyết định cách batch được retry hoặc phục hồi.

## 11. Những lỗi thường gặp

- **Acknowledge trước khi xử lý xong:** offset có thể đã commit trong khi nghiệp vụ chưa hoàn tất, dẫn đến mất xử lý.
- **Cho rằng MANUAL_IMMEDIATE tự retry:** retry do error handler và chính sách container quyết định; ack mode chỉ điều khiển commit.
- **Gọi acknowledge từ thread nền rồi mong commit tức thì:** lời gọi ngoài consumer thread được xếp hàng và xử lý theo semantics khác.
- **Trộn acknowledge trên consumer thread và thread khác:** có thể tạo kết quả commit không xác định.
- **Bật auto commit:** Kafka client có thể commit offset ngoài thời điểm do acknowledgment điều khiển.
- **Bỏ qua lỗi commit bất đồng bộ:** ứng dụng có thể tưởng offset đã được xác nhận trong khi callback báo commit thất bại.
- **Cho rằng commit offset làm database và Kafka nguyên tử:** offset commit không rollback được tác dụng phụ ngoài Kafka.
- **Không thiết kế idempotency:** record có thể được giao lại sau crash hoặc rebalance dù listener dùng `MANUAL_IMMEDIATE`.
- **Áp dụng semantics record listener cho batch listener:** một batch có nhiều offset và cách acknowledge cần được hiểu theo loại listener.

## 12. Kiểm thử MANUAL_IMMEDIATE

Kiểm thử tích hợp nên xác nhận cả thời điểm xử lý và vị trí offset đã commit. Có thể dùng Embedded Kafka hoặc Kafka Testcontainers để chạy broker trong test.

Các kịch bản quan trọng:

1. Gửi một record hợp lệ; listener xử lý rồi acknowledge; xác nhận group offset tiến tới offset kế tiếp.
2. Làm nghiệp vụ ném exception trước acknowledge; xác nhận record được retry hoặc xử lý theo error handler.
3. Gửi record mà listener cố tình acknowledge trước khi xử lý; dùng test để minh họa rằng lỗi sau acknowledge không làm offset tự quay lại.
4. Dùng `MANUAL` và `MANUAL_IMMEDIATE` với nhiều record trong một poll để quan sát khác biệt thời điểm commit.
5. Nếu bật `asyncAcks`, hoàn tất record theo thứ tự khác thứ tự nhận; xác nhận container chờ acknowledgment còn thiếu trước khi tiếp tục.
6. Mô phỏng rebalance hoặc restart trước commit; xác nhận record có thể được giao lại và nghiệp vụ idempotent.
7. Với container transactional, xác nhận offset và output cùng commit hoặc cùng rollback.

Không dựa vào `Thread.sleep()` cố định để kiểm tra offset. Hãy chờ điều kiện cụ thể như consumer group đạt offset mong đợi, output xuất hiện hoặc listener nhận được record. Dùng timeout hữu hạn để test thất bại rõ ràng khi điều kiện không xảy ra.

## 13. Khi nào nên dùng MANUAL_IMMEDIATE?

`MANUAL_IMMEDIATE` phù hợp khi listener cần quyết định rõ thời điểm xác nhận từng record và có thể acknowledge trên consumer thread ngay sau khi hoàn tất công việc. Nó cũng hữu ích khi muốn tránh chờ hết các record trong poll trước khi commit một record đã xử lý thành công.

Hãy cân nhắc `MANUAL` nếu muốn listener đánh dấu acknowledgment nhưng vẫn để container commit theo batch semantics. Dùng `RECORD` nếu mọi record đều được xử lý đồng bộ và không cần quyết định acknowledge thủ công. Dùng Kafka transaction nếu cần commit output Kafka cùng offset input. Nếu xử lý bất đồng bộ, thiết kế rõ thứ tự hoàn tất, cấu hình `asyncAcks` khi phù hợp và chấp nhận tác động của pause/redelivery.

Trước khi chọn chế độ này, hãy trả lời ba câu hỏi: listener acknowledge ở bước nào, lời gọi diễn ra trên thread nào, và điều gì sẽ xảy ra nếu ứng dụng dừng ngay trước hoặc ngay sau commit? Câu trả lời giúp xác định ranh giới xử lý thực tế và chính sách retry/idempotency cần có.
