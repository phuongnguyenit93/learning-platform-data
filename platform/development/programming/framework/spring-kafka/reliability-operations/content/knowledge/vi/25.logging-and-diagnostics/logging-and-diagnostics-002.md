# Commit log level

Khi vận hành một Spring Kafka consumer, câu hỏi thường xuyên xuất hiện là: **consumer đã commit offset nào, vào lúc nào, với kết quả gì?** Đây là câu hỏi cốt lõi khi một consumer group bị lag, khi record được xử lý lại sau restart, khi listener đã chạy thành công nhưng offset không tiến, hoặc khi cần phân biệt commit thông thường với offset được gửi trong Kafka transaction.

Spring Kafka cung cấp cấu hình **commitLogLevel** trong **ContainerProperties** để kiểm soát mức log cho thông tin commit offset mà listener container phát ra. Chẳng hạn, có thể chuyển thông tin commit offset từ mức DEBUG sang INFO trong một giai đoạn chẩn đoán. Tuy nhiên, một dòng log chứa offset **không phải bằng chứng tuyệt đối** rằng toàn bộ nghiệp vụ đã thành công hoặc broker đã ghi offset bền vững. Để kết luận đúng, phải hiểu **AckMode, sync/async commit, retry/recovery, rebalance và transactional offset commit**.

Bài học thuộc chương **Logging và chẩn đoán** trong module **Spring Kafka Reliability Operations**. Nội dung tập trung vào cách cấu hình commit log level, đọc log, xác định offset được commit, kiểm soát độ ồn, kết hợp metrics, và xây dựng quy trình điều tra khi log không khớp với trạng thái consumer group.

## 1. Tại sao cần quan sát offset commit?

Kafka consumer xử lý record dựa trên các offsets theo **topic-partition**. Consumer group duy trì một committed offset để các lần chạy sau biết phải tiếp tục đọc từ đâu.

Ví dụ:

~~~text
Topic: orders.events
Partition: 2

Offset 100 -> OrderCreated
Offset 101 -> OrderPaid
Offset 102 -> OrderCancelled

Consumer xử lý thành công offset 100
       |
       v
Commit offset 101
       |
       v
Khi restart, consumer group tiếp tục từ offset 101
~~~

Với Kafka, committed offset là **vị trí sẽ đọc tiếp**, không phải offset của record cuối cùng đã xử lý. Nếu record tại offset 100 đã xử lý và không có gap, consumer thường commit **101**, không phải 100.

Trong production, chẩn đoán cần biết:

- Record đã tới listener chưa?
- Listener đã hoàn thành hay ném exception?
- Container có quyết định commit offset không?
- Commit dùng sync hay async?
- Broker/coordinator đã xác nhận commit chưa?
- Consumer group thực sự lưu offset nào?
- Có rebalance, crash hoặc transaction abort làm offset không tiến không?

Commit log là một tín hiệu hữu ích, nhưng không trả lời được toàn bộ câu hỏi nếu đứng một mình.

## 2. Commit log level là gì?

**commitLogLevel** là thuộc tính của Spring Kafka **ContainerProperties** quy định mức ghi log cho thông tin offset commit phát ra bởi listener container.

Trong nhiều phiên bản Spring Kafka, thông tin commit offset được log ở **DEBUG** theo mặc định. Muốn theo dõi tại INFO, có thể gọi:

~~~java
containerProperties.setCommitLogLevel(
    LogIfLevelEnabled.Level.INFO
);
~~~

Kiểu enum **LogIfLevelEnabled.Level** nằm trong API hỗ trợ logging của Spring Kafka.

Phân biệt:

| Cấu hình | Nằm ở lớp nào? | Chức năng |
|---|---|---|
| ContainerProperties.commitLogLevel | Spring Kafka listener container | Quy định mức log dùng cho thông tin commit của container |
| logging.level.org.springframework.kafka.listener | Spring Boot logging backend | Quy định logger có phát các message ở mức đó không |
| syncCommits | Spring Kafka container | Chọn commitSync hay commitAsync trong luồng commit thông thường |
| AckMode | Spring Kafka container | Quyết định thời điểm container xem offsets đủ điều kiện commit |
| enable.auto.commit | Kafka consumer | Quyết định có dùng auto-commit của Kafka client không |
| isolation.level | Kafka consumer | Quy định consumer đọc dữ liệu transactional theo read_committed hay read_uncommitted |

**commitLogLevel không làm thay đổi offset semantics, retry policy hoặc delivery guarantee.** Nó chỉ thay đổi cách một thông tin được ghi vào logging system.

## 3. Hai lớp lọc log phải cùng cho phép

Một message của Spring Kafka chỉ xuất hiện nếu:

1. Container phát message ở mức đã chọn qua commitLogLevel.
2. Logger tương ứng của logging backend được bật ở mức đó.
3. Appender/filter không loại bỏ message trước khi ghi ra console, file hoặc collector.

Ví dụ:

~~~text
commitLogLevel = DEBUG
Logger threshold = INFO

=> Commit DEBUG messages không xuất hiện
~~~

Ngược lại:

~~~text
commitLogLevel = INFO
Logger threshold = INFO

=> Commit INFO messages có thể xuất hiện
   nếu code path có commit và không bị filter khác loại
~~~

Một trường hợp khác:

~~~text
commitLogLevel = INFO
Logger threshold = WARN

=> Commit INFO messages vẫn bị ẩn
~~~

Do đó, chỉ gọi setCommitLogLevel(INFO) chưa đủ nếu hệ thống logging đang cấu hình WARN cho package liên quan.

## 4. Ví dụ cấu hình Spring Boot bằng Java

Đối với các listener dùng **ConcurrentKafkaListenerContainerFactory**, cấu hình container properties trước khi factory tạo listener containers.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.LogIfLevelEnabled;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
        .setCommitLogLevel(LogIfLevelEnabled.Level.INFO);

    return factory;
}
~~~

Gắn factory vào listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "orders-worker",
    containerFactory = "ordersListenerContainerFactory"
)
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Lưu ý:

- Cấu hình trong factory chỉ áp dụng với containers được tạo từ factory đó.
- Nếu một listener tham chiếu factory khác, commit log level trên factory này không ảnh hưởng.
- Nếu ứng dụng có nhiều @KafkaListener factories, cần cấu hình từng factory theo nhu cầu.
- Cần kiểm tra API và kiểu enum trên đúng phiên bản Spring Kafka của dự án.
- Đừng cho rằng một listener tự tạo MessageListenerContainer bằng bean riêng sẽ tự dùng factory mặc định.

## 5. Cấu hình logging level của Spring Boot

Để cho phép Spring Kafka listener logs ở mức INFO, có thể khai báo:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

Một cấu hình đầy đủ minh họa:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092
    consumer:
      group-id: orders-worker
      enable-auto-commit: false

logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

Ứng dụng vẫn cần gọi **setCommitLogLevel(LogIfLevelEnabled.Level.INFO)** trong container factory; logging.level không tự đổi commitLogLevel mặc định từ DEBUG sang INFO.

Nếu muốn khảo sát các log mức DEBUG mà không thay commitLogLevel, có thể tạm bật:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: DEBUG
~~~

Nhưng cách này có thể bật nhiều debug messages khác trong package listener, không riêng thông tin offset commit.

Trong môi trường có lưu lượng cao, thường phù hợp hơn khi **chọn commitLogLevel có chủ đích** rồi giữ logging category ở mức ít ồn, thay vì bật DEBUG cho cả Spring Kafka trong thời gian dài.

## 6. Cấu hình hẹp theo logger category

Khi cần giới hạn lượng log, thay vì bật toàn bộ package, có thể nhắm vào logging category của listener container, chẳng hạn:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener.KafkaMessageListenerContainer: INFO
~~~

Tên category thực tế có thể phản ánh class hoặc nested class do logger được khởi tạo trong phiên bản Spring Kafka đang chạy. Vì vậy, trước khi áp dụng ở production hãy xem **logger name** trên một dòng log đã xuất hiện.

Ví dụ pattern:

~~~text
2026-11-15 14:00:00 INFO
org.springframework.kafka.listener.KafkaMessageListenerContainer
... commit information ...
~~~

Đây là format minh họa. Chú ý, cấu hình category chính xác còn phụ thuộc logging backend, class dùng logger, việc Spring Kafka thay đổi implementation và các filters bổ sung.

Nếu đặt logging category quá hẹp nhưng không thấy message, kiểm tra:

1. commitLogLevel đang là INFO hay DEBUG?
2. Logger name thực tế thuộc class/package nào?
3. Có commit nào thật sự xảy ra không?
4. Appender có loại bỏ INFO không?
5. Container dùng đúng factory đã cấu hình chưa?

Không suy ra “consumer không commit” chỉ từ việc không có dòng log trong một category.

## 7. Default commit log level và chính sách production

Trong các phiên bản Spring Kafka thông dụng, commit log được đặt ở **DEBUG** theo mặc định để tránh làm đầy application logs ở các workload có commit thường xuyên.

Ví dụ một consumer xử lý 10.000 records/giây và commit mỗi record có thể tạo số lượng commit-related log rất lớn nếu bật INFO.

Điều này ảnh hưởng:

- I/O cho stdout hoặc file.
- Chi phí lưu trữ log tập trung.
- Tốc độ ingest của Fluent Bit/Vector/Logstash.
- Dung lượng và retention trên hệ thống quan sát.
- Độ dễ đọc của các cảnh báo WARN/ERROR quan trọng.
- CPU và allocations do logging formatting, tùy implementation.

Vì vậy, nên dùng:

- **DEBUG** cho commit details trong điều kiện vận hành bình thường nếu không cần xem liên tục.
- **INFO** trong một khoảng chẩn đoán có scope và thời hạn rõ ràng.
- **Metrics** để theo dõi commit rates và failures lâu dài.
- **Structured log** tại các boundary quan trọng thay vì log mỗi record nếu traffic lớn.

Không cần phải đặt mức ERROR cho mọi commit log; chỉ cần logging backend không bật DEBUG là thông tin chi tiết mặc định đã có thể bị ẩn.

## 8. commitLogLevel không phải Kafka consumer log level

Các thành phần có thể ghi log về commit:

~~~text
Spring Kafka listener container
      |
      +-- Container commit log (commitLogLevel)
      |
      +-- DefaultErrorHandler / rollback logs
      |
      v
KafkaConsumer.commitSync()/commitAsync()
      |
      +-- Kafka client internal debug/error logs
      |
      v
Kafka group coordinator
      |
      +-- Broker logs / metrics
      |
      v
__consumer_offsets (internal Kafka topic)
~~~

**setCommitLogLevel() không thay đổi log level của tất cả Kafka client internals và broker**. Nếu cần xem network request, offset commit request/response, coordinator changes hoặc retry logic ở Kafka client, cần logger categories của Kafka clients và broker tương ứng.

Nên bật client DEBUG chỉ khi có mục tiêu điều tra rõ, vì logs có thể rất nhiều và các internal logger names/fields thay đổi theo Kafka client version.

## 9. Log commit và commit được broker xác nhận khác nhau

Một dòng log kiểu:

~~~text
INFO ... Committing offsets:
  orders.events-0 -> 101
  orders.events-1 -> 205
~~~

chỉ là **ví dụ định dạng logic**, không phải message nguyên văn của mọi Spring Kafka version.

Nếu message được ghi **trước** một lệnh commit, nó cho biết container chuẩn bị commit các offsets đó; không tự xác nhận Kafka group coordinator đã chấp nhận.

Nếu message được ghi **sau** một lời gọi commitSync thành công, nó cung cấp evidence mạnh hơn về outcome của client call, nhưng vẫn không nói toàn bộ side effects ngoài Kafka đã an toàn.

Nếu dùng commitAsync, method có thể trả về trước callback kết quả. Khi đó log “đã gọi commit” không đồng nghĩa “commit đã hoàn thành”.

Muốn kết luận broker đã ghi committed offset:

1. Kiểm tra outcome của sync commit hoặc async commit callback.
2. Xem các exception/failures.
3. Xác minh committed offset qua consumer group tooling hoặc committed() khi phù hợp.
4. Đối chiếu rebalance, transaction và processing logs.

**Không đặt cược vào từ “Committed” hoặc “Committing” xuất hiện trong một phiên bản cụ thể của log message.** Hãy xem message và code path của phiên bản chạy thực tế.

## 10. Offset được commit là next offset

Giả sử partition 1 có các records:

~~~text
offset 200 -> R200
offset 201 -> R201
offset 202 -> R202
~~~

Listener xử lý R200 và R201, chưa xử lý R202:

~~~text
Last processed = 201
Next offset    = 202
Commit value   = 202
~~~

Nếu log cho thấy:

~~~text
orders.events-1 => offset 202
~~~

đó thường là hợp lệ. Nó **không nói** record offset 202 đã được xử lý.

Đây là điểm dễ gây nhầm khi on-call so sánh:

- Kafka log chứa offset của record được nhận.
- Application log chứa offset listener vừa xử lý.
- Container commit log chứa **offset tiếp theo**.
- Consumer group CLI CURRENT-OFFSET thường chứa **offset tiếp theo** đã commit.

Tất cả phải được đọc theo cùng convention.

## 11. TopicPartition là đơn vị commit

Offsets không tăng trên toàn topic như một số đếm duy nhất. Mỗi partition có dãy offsets riêng.

Ví dụ:

~~~text
orders.events P0: commit 105
orders.events P1: commit 560
orders.events P2: commit 41
~~~

Không có nghĩa P1 xử lý nhanh hơn P0 hoặc đã nhận nhiều business events hơn trong cùng khoảng thời gian, vì partitions có lượng dữ liệu và thời điểm bắt đầu khác nhau.

Khi đọc commit log:

1. Xác định topic.
2. Xác định partition.
3. Xác định consumer group/listener instance.
4. Xác định next offset.
5. Đối chiếu log end offset và business processing success cùng partition.

Đừng chỉ lấy “offset lớn nhất” trong toàn topic làm progress của consumer group.

## 12. AckMode ảnh hưởng thời điểm xuất hiện commit log

Spring Kafka listener container hỗ trợ nhiều **AckMode**. Điều này quyết định khi nào container đủ điều kiện commit offsets.

| AckMode | Quy tắc khái quát | Commit logs có thể xuất hiện khi |
|---|---|---|
| RECORD | Sau mỗi record xử lý thành công | Mỗi record, theo container semantics |
| BATCH | Sau toàn bộ records trong poll được xử lý theo policy | Sau một poll batch |
| TIME | Dựa vào điều kiện thời gian | Khi timer/processing state đủ điều kiện |
| COUNT | Dựa vào số lượng records | Khi đạt threshold |
| COUNT_TIME | Đạt điều kiện count hoặc time | Khi một ngưỡng xảy ra |
| MANUAL | Listener acknowledge, container commit theo quy trình manual | Sau ack hợp lệ và xử lý pending offsets |
| MANUAL_IMMEDIATE | Acknowledge trong ngữ cảnh phù hợp có thể commit ngay | Gần thời điểm gọi acknowledge |

**Một commit log cho nhiều records là bình thường.** Với AckMode.BATCH, 500 records được xử lý có thể tạo một commit offset trên partition thay vì 500 log lines.

Ngược lại, listener invocation count và commit count không nhất thiết bằng nhau. Không dùng số commit lines để suy ra số records xử lý thành công.

## 13. Ví dụ AckMode.RECORD

Cấu hình:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.RECORD
);

factory.getContainerProperties().setCommitLogLevel(
    LogIfLevelEnabled.Level.INFO
);
~~~

Giả sử consumer nhận ba records cùng partition, xử lý thành công:

~~~text
Listener processed R10
Container commits next offset 11

Listener processed R11
Container commits next offset 12

Listener processed R12
Container commits next offset 13
~~~

Đây là mô tả logic, không cam kết mỗi bước sẽ có chính xác một dòng console log. Kết quả còn phụ thuộc sync/async mode, error handling, batching nội bộ, logging filters và consumer lifecycle.

Với lưu lượng cao, AckMode.RECORD có thể tạo nhiều commits và log output; chọn mode phải dựa vào latency, duplicate risk và throughput, không chỉ vì muốn dễ đọc log.

## 14. Ví dụ AckMode.BATCH

Cấu hình:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.BATCH
);
~~~

Giả sử poll trả về:

~~~text
Partition 0: offsets 10, 11, 12
Partition 1: offsets 20, 21
~~~

Sau khi listener xử lý thành công toàn bộ poll:

~~~text
Commit map:
  orders.events-0 -> 13
  orders.events-1 -> 22
~~~

Một commit request có thể chứa offsets của nhiều partitions. Đừng đánh giá “chỉ có một commit log” là listener xử lý một record.

Nếu giữa batch có exception hoặc rollback, error handler có thể thay đổi tiến độ xử lý/commit. Không mặc định commit map trong ví dụ áp dụng cho mọi failure path.

## 15. MANUAL acknowledgement và commit log

Manual acknowledgement có thể cần khi ứng dụng muốn chủ động quyết định record nào đã hoàn thành.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );

    factory.getContainerProperties().setCommitLogLevel(
        LogIfLevelEnabled.Level.INFO
    );

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "ordersFactory"
)
public void onRecord(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());

    // Chỉ acknowledge khi xử lý nghiệp vụ hoàn tất.
    acknowledgment.acknowledge();
}
~~~

Với MANUAL_IMMEDIATE, việc acknowledge từ consumer thread có thể dẫn tới commit gần thời điểm gọi, tùy syncCommits và container conditions. Acknowledge từ thread khác có thể có behavior khác; cần kiểm tra phiên bản và quy tắc ack ordering.

**Không acknowledge trước khi side effect bền vững hoàn tất để tạo commit log sớm hơn.** Làm vậy có thể khiến Kafka group bỏ qua record nếu ứng dụng crash sau ack.

## 16. enable.auto.commit và commit logs của container

Kafka consumer có cấu hình **enable.auto.commit**, điều khiển cơ chế auto-commit offsets của Kafka client.

Trong mô hình Spring Kafka listener container phổ biến, container nên là bên quản lý offsets:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

Khi auto-commit bật, Kafka client có thể commit offsets theo khoảng thời gian của client mà không tuân theo cùng ranh giới “business processing succeeded” của container.

Hệ quả:

- Một commit có thể xảy ra do Kafka client, không phải container commit path mà commitLogLevel instrument.
- Commit log của Spring Kafka không phản ánh đầy đủ auto-commit do client thực hiện.
- Dựa vào auto-commit sai bối cảnh có thể làm lệch delivery semantics mong muốn.

Spring Kafka phiên bản hiện đại có thể tự đặt enable.auto.commit=false khi ứng dụng không override. Tuy vậy, trong cấu hình production nên kiểm tra **effective consumer properties** và tránh đồng thời hai cơ chế commit thiếu kiểm soát.

## 17. syncCommits và commitAsync

Spring Kafka container có thể dùng **synchronous** hoặc **asynchronous offset commits** trong đường commit non-transactional.

Đặt ví dụ:

~~~java
var props = factory.getContainerProperties();

props.setSyncCommits(true);
props.setCommitLogLevel(LogIfLevelEnabled.Level.INFO);
~~~

Hoặc:

~~~java
props.setSyncCommits(false);
~~~

Trong các phiên bản Spring Kafka hiện đại, syncCommits thường mặc định true; hãy xác nhận effective value ở version đang chạy.

| Chế độ | API Kafka consumer | Ý nghĩa đối với log và outcome |
|---|---|---|
| Synchronous | commitSync | Consumer thread đợi commit call hoàn thành hoặc ném lỗi |
| Asynchronous | commitAsync | Commit request được gửi, kết quả về qua callback |

Với sync commit, commit failure có thể xuất hiện trên đường thực thi trực tiếp. Với async commit, cần instrument **callback** để phân biệt attempted và successful/failed commits.

Mức log của container không làm thay đổi tính đồng bộ hay bảo đảm của commit.

## 18. Log “đã commit” chưa chắc là commit success

Giả sử logger ghi:

~~~text
INFO ... Commit offsets: {orders.events-0=101}
~~~

Một request commit có thể vẫn gặp:

~~~text
Coordinator unavailable
Group rebalance đang diễn ra
Request timeout
Producer/consumer bị đóng
Authentication/authorization error
~~~

Nếu không biết log được ghi **trước hay sau** commit call và không có outcome callback, không thể kết luận broker đã xác nhận thành công.

Để tăng độ tin cậy chẩn đoán:

- Ghi metric commit_attempts.
- Ghi metric commit_success và commit_failure ở boundary có outcome thực.
- Lưu root exception class và consumer group.
- Đối chiếu committed offset qua Kafka group tooling.
- Kiểm tra listener retries và idempotency khi commit failure.

Một log có thể hữu ích để biết **container định commit offset nào**, còn committed offset thực tế cần được xác minh độc lập khi có nghi ngờ.

## 19. commitSync failure và các loại lỗi

Một số nhóm lỗi có thể xuất hiện khi commit:

| Nhóm | Ví dụ | Ý nghĩa điều tra |
|---|---|---|
| Consumer group ownership | CommitFailedException, rebalance-related error | Consumer có thể không còn sở hữu partition/generation hợp lệ |
| Coordinator/network | Timeout/disconnect/coordinator unavailable | Commit request chưa được xác nhận |
| Authorization | Group authorization failure | Consumer thiếu quyền tương ứng |
| Client lifecycle | Wakeup/closed consumer state | Shutdown hoặc điều khiển sai thời điểm |
| Transactional path | Producer fencing, transaction abort | Commit offset nằm trong Kafka transaction khác direct consumer commit |

Exception và việc chúng được wrap/log phụ thuộc Kafka client/Spring Kafka version. Không chỉ dựa vào exception class để quyết định retry commit vô hạn.

Đặc biệt, sau **onPartitionsLost** hoặc khi consumer mất group generation, ứng dụng không được cố commit offsets như thể vẫn là owner cũ.

## 20. Commit log và rebalance

Khi một consumer group thay đổi membership hoặc partitions được giao lại, quá trình commit có thể gắn với lifecycle của partition ownership.

~~~text
Consumer A xử lý partition 0
       |
       v
Rebalance bắt đầu
       |
       v
Partition được revoke hoặc lost
       |
       v
Container có thể commit offsets đủ điều kiện
theo phase và policy
       |
       v
Consumer B nhận partition
~~~

Một dòng commit log gần thời điểm rebalance không đồng nghĩa mọi record đang chạy đã được hoàn thành.

Khi điều tra:

1. Xem timestamps của commit log và rebalance logs.
2. Đối chiếu partitions được revoke/lost.
3. Kiểm tra offsets đã được ghi nhận hay commit failed.
4. Kiểm tra listener in-flight records và async tasks.
5. Tìm records redeliver sau reassignment.

Với cooperative rebalance hoặc static membership, cách các partitions chuyển owner có thể khác eager rebalance thông thường. Không tự suy luận thiếu commit log có nghĩa không có rebalance.

## 21. Commit log và graceful shutdown

Khi nhận SIGTERM, Spring Kafka listener container thường được dừng thông qua Spring lifecycle. Container có thể hoàn tất phần processing đang có và commit các offsets đủ điều kiện trước khi consumer close.

Ví dụ:

~~~text
Container xử lý record offset 500
      |
      v
SIGTERM nhận được
      |
      v
Listener hoàn tất record
      |
      v
Container commit next offset 501
      |
      v
Consumer close
~~~

Đây là đường shutdown lý tưởng. Trên thực tế:

- Kubernetes grace period có thể hết trước khi commit.
- Listener có thể đang bị kẹt ở HTTP/database call.
- Producer hoặc broker có thể timeout.
- Commit có thể thất bại do rebalance.
- Process có thể OOMKilled hoặc SIGKILL, không có shutdown hook.

**Không thấy commit log cuối cùng** sau crash không tự chứng minh Kafka offset chưa được commit; có thể log pipeline chưa flush. Và **thấy dòng commit trước SIGKILL** cũng không chứng minh business side effect có idempotency.

## 22. Commit log trong transactional listener

Khi Spring Kafka listener container sử dụng Kafka transaction manager, việc commit consumed offsets có thể diễn ra bằng cách **đưa offsets vào cùng Kafka transaction với output**.

~~~text
Input Kafka record
      |
      v
Begin Kafka transaction
      |
      +-- Listener gửi output Kafka
      |
      +-- Container đưa consumed offsets vào transaction
      |
      v
commitTransaction()
      |
      +-- Commit success:
      |      Kafka output và consumed offsets cùng được commit
      |
      +-- Abort:
             Output transactional bị ẩn với read_committed
             Consumed offsets trong transaction không commit
~~~

Trong trường hợp này, đừng giả định một direct Consumer.commitSync log sẽ xuất hiện tương tự non-transactional listener. Container có thể dùng producer transaction APIs, và outcome cuối phụ thuộc **commit/abort transaction**.

commitLogLevel chỉ kiểm soát các commit-related logs tại Spring Kafka container theo implementation. Để chẩn đoán chính xác EOS path, cần quan sát:

- Transaction begin/commit/abort.
- Producer fencing hoặc transaction timeout.
- sendOffsetsToTransaction behavior.
- Output topic visibility với read_committed consumer.
- Committed input group offsets.

Kafka transaction không tự bao gồm database hoặc HTTP side effects; không dùng “Kafka transaction committed” làm chứng cứ một database operation đã atomic với Kafka.

## 23. Khi transaction abort nhưng listener đã chạy

Giả sử:

~~~text
Listener processed OrderCreated
      |
      +-- Update external database thành công
      |
      +-- Kafka output trong transaction
      |
      v
Kafka transaction timeout -> abort
      |
      v
Input offset chưa commit cùng transaction
      |
      v
Record được đọc lại
~~~

Ở đây có thể thấy listener success log và transaction abort log trong cùng khoảng thời gian. Nếu chỉ nhìn listener success hoặc một dòng commit intent, người vận hành có thể kết luận nhầm rằng record đã hoàn tất.

Do đó, có ba câu hỏi riêng:

1. Listener method đã return không lỗi chưa?
2. Kafka transaction/offset commit đã hoàn thành chưa?
3. Side effect bên ngoài Kafka có idempotency không?

Mức commitLogLevel không giải quyết câu hỏi thứ ba.

## 24. DefaultErrorHandler và recovery

Với listener non-transactional, khi record gây exception, **DefaultErrorHandler** có thể retry hoặc gọi recoverer để chuyển record sang DLT.

~~~text
Listener xử lý offset 100 -> lỗi
       |
       v
DefaultErrorHandler
       |
       +-- Retry
       |      |
       |      v
       |   Xử lý lại
       |
       +-- Hết retry/non-retryable
              |
              v
       DeadLetterPublishingRecoverer
              |
              v
       DLT publish xác nhận thành công
              |
              v
       Offset nguồn có thể tiến theo policy
~~~

Một commit log sau recovery không chứng minh **nghiệp vụ gốc thành công**. Nó có thể chỉ cho biết container đã xử lý record theo chính sách lỗi, ví dụ đưa record đến DLT rồi bỏ qua ở topic nguồn.

Khi điều tra, cần xem:

- Error handler classifications và backoff.
- Retry attempts.
- DLT publish success/failure.
- ackAfterHandle/commitRecovered behavior theo version/config.
- Source offset commit outcome.
- DLT consumer backlog và manual review.

Không bật commitLogLevel INFO rồi xem offset tăng là đủ để tuyên bố không có poison records.

## 25. Recovery thất bại và commit không nên vượt qua record

Giả sử DLT producer gặp authorization error:

~~~text
Listener gặp poison record
       |
       v
Recoverer cố publish DLT
       |
       v
DLT send thất bại
       |
       v
Không thể coi record đã được recover an toàn
       |
       v
Record cần được xử lý lại hoặc giữ theo policy
~~~

Nếu ứng dụng tự commit offset để giảm lag bất chấp recovery thất bại, record có thể bị bỏ qua và không còn trong đường xử lý bình thường của consumer group.

Để tránh **silent loss**, khi đọc commit logs gần error handler:

1. Xác định recovery operation đã có success outcome chưa.
2. Nếu dùng async producer, kiểm tra send future/callback.
3. Xem nguồn commit đã thực hiện theo ack policy nào.
4. Xác nhận DLT topic/record tồn tại nếu recovery dựa vào DLT.
5. Không suy từ việc offset tăng rằng toàn bộ record đã hoàn thành nghiệp vụ.

## 26. Commit log và batch listener

Batch listener có thể nhận nhiều ConsumerRecords cùng lúc:

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "ordersBatchFactory"
)
public void handleBatch(List<OrderEvent> batch) {
    orderService.processBatch(batch);
}
~~~

Nếu method nhận 200 records:

- Một batch listener invocation có thể xử lý 200 records.
- Commit map có thể chứa next offsets của nhiều partitions.
- Một exception có thể khiến batch phải retry hoặc recovery theo cấu hình.
- Database có thể đã áp dụng một phần công việc nếu không có transaction/idempotency.

Không dùng **số commit logs** làm chỉ số số records thành công. Với batch workload, nên có thêm:

- Batch size.
- Batch processing latency.
- Batch failure count.
- Record success/failure metrics nếu có.
- Committed offset per partition.
- Redeliveries sau error/rebalance.

Một commit offset tăng 200 không tự chứng minh 200 business side effects độc lập đã được commit an toàn.

## 27. Tại sao log offset có thể nhảy nhiều đơn vị?

Giả sử commit log:

~~~text
12:00:01 P0 commit 1.000
12:00:02 P0 commit 1.500
12:00:03 P0 commit 2.000
~~~

Offset nhảy 500 có thể hoàn toàn bình thường khi:

- AckMode.BATCH.
- Poll/processing có nhiều records.
- Commit được gộp theo count/time.
- Consumer xử lý backlog nhanh hơn tốc độ commit.

Tuy nhiên, nếu ứng dụng tự gọi seek/commit không đúng, offset nhảy có thể là dấu hiệu bỏ qua dữ liệu.

Để phân biệt, đối chiếu:

- Container AckMode.
- max.poll.records.
- Số records được giao/processed.
- Error handler recovery/seek.
- Manual acknowledgement behavior.
- Application-level seek/reset operations.

Không khẳng định “data loss” chỉ từ hai log lines có khoảng cách offset lớn.

## 28. Tại sao log offset có thể không tăng?

Một log commit lặp lại cùng offset hoặc không xuất hiện log mới có thể do:

- Topic không có record mới.
- Consumer đã catch up.
- Container paused/stopped.
- Consumer chưa được assign partitions.
- Listener đang xử lý record lâu.
- AckMode.TIME/COUNT chưa đạt threshold.
- Manual ack chưa được gọi.
- Error handler retry một poison record.
- Transaction abort.
- Commit request thất bại.
- Logger filtering.

Kết luận phải dựa trên **nhiều dấu hiệu**, không chỉ một logger.

Ví dụ:

~~~text
Consumer lag = 0
No new input records
No commit logs for 10 minutes

=> Có thể hoàn toàn bình thường
~~~

Ngược lại:

~~~text
Consumer lag = 50.000
Producer input rate cao
Listener success rate gần 0
No commit logs for 10 minutes

=> Cần điều tra pause, retry, poll và dependency
~~~

## 29. Commit log level không điều khiển tần suất commit

Một hiểu lầm phổ biến:

~~~text
commitLogLevel = INFO
=> Kafka commit thường xuyên hơn
~~~

Điều này **sai**. Tham số đó chỉ kiểm soát **mức log**, không thay đổi:

- AckMode.
- syncCommits.
- enable.auto.commit.
- ackCount/ackTime.
- Listener throughput.
- Kafka transaction commit.
- Retry hoặc DLT policy.

Muốn điều chỉnh tần suất commit, phải đánh giá chính sách acknowledgement/commit của container và yêu cầu delivery semantics; không chỉnh log level.

## 30. Logging pattern cho chẩn đoán

Một log line hữu ích nên có:

~~~text
time=2026-11-15T14:00:00Z
level=INFO
logger=org.springframework.kafka.listener.KafkaMessageListenerContainer
service=order-service
instance=orders-pod-3
listener=orders-listener
group=orders-worker
topic=orders.events
partition=2
nextOffset=501
action=commit_requested
~~~

Đây là **format instrumentation đề xuất**, không phải output nguyên văn mặc định Spring Kafka.

Khi cần outcome:

~~~text
action=commit_succeeded
commitMode=sync
group=orders-worker
topic=orders.events
partition=2
nextOffset=501
elapsedMs=12
~~~

Nếu dùng Logback JSON encoder hoặc OpenTelemetry logging, có thể thêm MDC/correlation fields phù hợp. Nhưng không nên giả định Spring Kafka container tự copy mọi MDC của listener vào log commit, nhất là khi commit callback chạy trên thread khác.

## 31. Correlation giữa processing và commit

Một investigation thường cần nối:

~~~text
Listener received offset 500
       |
       v
Business processing success
       |
       v
Container commit requested next offset 501
       |
       v
Commit completed
~~~

Nên có structured logs riêng ở boundary của ứng dụng:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
        "kafka_delivery_started topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );

    orderService.process(record.value());

    log.info(
        "kafka_business_processed topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
~~~

Các logs này minh họa cách correlate, không nên bật INFO cho từng record ở workload rất lớn nếu không có sampling/retention policy. Và business_processed chỉ cho biết method return thành công; side effect durability cần được định nghĩa tại nghiệp vụ.

Container commit log giúp thấy bước sau listener, nhưng **không tạo một distributed transaction** giữa Kafka commit và database/HTTP.

## 32. MDC và listener concurrency

Khi Kafka listener có concurrency > 1, các records được xử lý trên các consumer threads khác nhau.

~~~text
orders-listener
  +-- consumer-0 => P0,P3
  +-- consumer-1 => P1,P4
  +-- consumer-2 => P2,P5
~~~

Một log line nên có:

- Listener ID.
- Consumer group.
- Consumer client ID/instance khi có.
- Topic-partition.
- Offset.
- Thread name hoặc trace context.

Với MDC:

~~~java
try {
    MDC.put("kafka.topic", record.topic());
    MDC.put("kafka.partition", Integer.toString(record.partition()));
    MDC.put("kafka.offset", Long.toString(record.offset()));

    orderService.process(record.value());
}
finally {
    MDC.remove("kafka.topic");
    MDC.remove("kafka.partition");
    MDC.remove("kafka.offset");
}
~~~

MDC có thread-local semantics trong nhiều logging backends; cần cleanup trong finally để tránh record sau kế thừa context cũ. Với async listener, MDC context phải được truyền một cách có chủ đích. Log commit do Spring Kafka thực hiện có thể không chạy trong đúng MDC scope này, nên không nên dựa vào MDC như nguồn duy nhất để nhận diện commit.

## 33. Không log payload nhạy cảm để giải thích commit

Để biết offset commit, thường chỉ cần:

- Topic.
- Partition.
- Offset/next offset.
- Group.
- Timestamp.
- Commit mode và outcome.
- Correlation ID không nhạy cảm.

Không cần in:

- Payload đầy đủ chứa thông tin khách hàng.
- Authorization headers/credentials.
- Kafka key có dữ liệu nhận dạng nhạy cảm.
- Database secrets.
- HTTP bearer tokens.

Một commit log có thể không chứa payload, nhưng application logs/exception messages xung quanh có thể vô tình tiết lộ dữ liệu. Khi bật DEBUG trong production, cần xem phạm vi logger categories và chính sách bảo vệ dữ liệu của log collector.

## 34. Sự khác biệt giữa logs và metrics

Logs hữu ích để xem offset cụ thể:

~~~text
P2 offset 501 được container định commit lúc 14:00:00
~~~

Metrics hữu ích để xem xu hướng:

~~~text
Commit attempts/sec tăng hay giảm?
Commit failures có spike không?
Commit latency p99 đang bao nhiêu?
Group lag có đang tăng không?
~~~

Không thay metrics bằng cách đếm số dòng có chữ “commit” trong log. Một commit log có thể:

- Chứa nhiều partitions.
- Bị mất do sampling/collector outage.
- Bị lọc theo logging level.
- Là requested thay vì successful commit.
- Có message text thay đổi theo version.

Thay vì log parsing làm nguồn dữ liệu duy nhất, ưu tiên Kafka client/JMX/Micrometer metrics và instrumentation có outcome rõ ràng.

## 35. Những metrics cần ghép với commit logs

| Metric | Diễn giải |
|---|---|
| records_consumed_rate | Consumer nhận records nhanh hay chậm |
| listener_success_rate | Business listener hoàn tất bao nhiêu |
| listener_failure_rate | Lỗi xử lý có tăng không |
| consumer_group_lag | Committed offset còn cách log end bao xa |
| commit_attempt_rate | Container/client đang cố commit bao nhiêu |
| commit_failure_rate | Commit thất bại bao nhiêu |
| commit_latency_p95/p99 | Commit request/callback chậm ra sao |
| rebalance_count/duration | Consumer ownership thay đổi thường xuyên không |
| paused_partition_count | Pause có làm offset đứng yên không |
| retry_count | Có record lỗi bị xử lý lại không |
| recovery/DLT_count | Có record được bỏ qua sau recovery không |
| transaction_abort_rate | Transactional offset commit có đang thất bại không |
| last_successful_commit_age | Thời gian từ lần commit được xác nhận cuối |

Một số metric tên trên là **khái niệm custom** chứ không phải tên Kafka client/Micrometer cố định. Nếu Kafka client đã cung cấp metrics tương đương, dùng nguồn đó trước khi tự tạo thêm một metric có semantics không rõ.

## 36. Kafka CLI để xác minh committed offset

Một cách kiểm tra consumer group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-worker \
  --describe
~~~

Ví dụ output:

~~~text
TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
orders.events  0         101            140            39
orders.events  1         205            205             0
orders.events  2         501            550            49
~~~

**CURRENT-OFFSET** là committed next offset của consumer group theo cách CLI trình bày. Nếu log container mới nhất nói P2 định commit 501, CLI cũng hiển thị 501, đây là một dấu hiệu tương thích. Nhưng cần xét thời điểm lấy mẫu; CLI snapshot có thể xảy ra trước/sau một commit mới.

Nếu CLI vẫn hiển thị 480:

1. Xem log đó là commit intent hay confirmed commit.
2. Kiểm tra commit failures.
3. Kiểm tra consumer group có đúng không.
4. Xác định topic/partition.
5. Xem có offset reset/rebalance giữa hai lần đọc không.
6. Xác nhận không đọc nhầm environment/cluster.

Không tự reset offsets bằng CLI để “đồng bộ” với log khi chưa hiểu records nào đã xử lý và side effects nào đã xảy ra.

## 37. Commit logs và isolation.level=read_committed

Consumer dùng **read_committed** có thể bị giới hạn bởi **Last Stable Offset (LSO)** khi có Kafka transaction còn mở.

~~~text
Log End Offset (LEO) tăng
       |
       v
Một transaction trước đó còn mở
       |
       v
LSO nằm sau so với LEO
       |
       v
read_committed consumer chưa được đọc dữ liệu sau LSO
       |
       v
Consumer có thể không nhận record mới
       |
       v
Không có commit log mới
~~~

Điều đó không tự chứng minh consumer bị lỗi. Khi điều tra “commit log không tăng nhưng lag cao”, cần kiểm tra:

- isolation.level.
- Open transactions và transaction timeout.
- LSO/HW/LEO nếu monitoring hỗ trợ.
- Producer commit/abort rates.
- Consumer poll responsiveness.

Một dashboard lag theo LEO có thể tăng trong khi read_committed consumer chưa thể đọc các records phía sau LSO.

## 38. Logging trong môi trường Kubernetes

Containerized Spring Boot thường đưa logs lên stdout để collector thu thập. Bật commitLogLevel.INFO có thể tăng logs rất lớn trong rollout nhiều replicas.

Ví dụ:

~~~text
10 pods
100 commits/second/pod
= 1.000 commit-related events/second
~~~

Nếu mỗi log event có kích thước 500 bytes:

~~~text
1.000 × 500 = 500.000 bytes/second
≈ 43 GB/day trước compression và overhead
~~~

Đây là **ước lượng minh họa**, không phải số byte cố định của Spring Kafka. Nhưng nó cho thấy chỉ một thay đổi log level cũng có thể tác động chi phí.

Khi bật INFO cho commit diagnostics:

- Giới hạn vào service/listener cần điều tra.
- Chọn sampling nếu backend hỗ trợ và vẫn giữ khả năng correlate.
- Đặt thời hạn tắt lại.
- Xác định log retention.
- Theo dõi log ingest rate.
- Không làm ngập các alert quan trọng.

Log volume budget phải là một phần của change plan.

## 39. Dynamic log level qua Spring Boot Actuator

Spring Boot Actuator có khả năng quản lý logger levels tại runtime khi endpoint được bật và bảo vệ phù hợp. Ví dụ endpoint **/actuator/loggers** có thể cho phép thay đổi configured level của một logger category.

Điều này có ích khi không muốn restart service chỉ để điều tra.

Tuy nhiên, cần hiểu hai lớp:

1. Actuator chỉnh **backend logger level**.
2. ContainerProperties.commitLogLevel quy định **mức mà container phát commit log**.

Nếu commitLogLevel vẫn là DEBUG, bật logger DEBUG có thể làm commit logs xuất hiện, đồng thời mở các DEBUG logs khác cùng category. Nếu commitLogLevel là INFO, chuyển backend logger threshold thành DEBUG không khiến commit messages trở thành DEBUG; chúng vẫn phát theo configured commitLogLevel.

Không phơi endpoint thay đổi log level công khai. Cần authentication/authorization, audit và rollback khi hết incident. Dynamic logger change không nhất thiết sửa commitLogLevel trên container đã chạy.

## 40. commitLogLevel là quyết định quan sát, không phải hành động sửa lỗi

Ví dụ consumer lag tăng vì database deadlock:

~~~text
Database lock
    |
    v
Listener blocked
    |
    v
Offset không đạt điều kiện commit
    |
    v
Không có commit log mới
~~~

Chuyển commitLogLevel từ DEBUG sang INFO **không giải phóng database lock** và không làm consumer bắt kịp backlog. Nó chỉ giúp nhìn thấy offsets khi container thực hiện commit.

Muốn giải quyết:

- Chẩn đoán listener processing latency.
- Kiểm tra database lock/statement timeout.
- Xem max.poll.interval.ms và rebalance.
- Xem error handler retry/transaction.
- Dùng idempotency khi redelivery.

Logging là công cụ quan sát, không thay đổi semantics hay business root cause.

## 41. Trường hợp “listener success nhưng không có commit log”

Triệu chứng:

~~~text
14:00:00 Business processed R100
14:00:01 Business processed R101
14:00:02 Business processed R102
Không có container commit log
~~~

Điều tra theo thứ tự:

1. commitLogLevel đang ở mức nào?
2. Backend logger có bật mức đó không?
3. Listener container dùng factory nào?
4. AckMode có phải BATCH/TIME/COUNT không?
5. Ngưỡng ackCount/ackTime đã đạt chưa?
6. enable.auto.commit có bật ngoài ý muốn không?
7. Consumer group offset qua CLI có tiến không?
8. Có Kafka transaction commit offsets qua producer không?
9. Có log collection/drop/sampling không?

Không bật retry hoặc replay để “tạo log mới” trước khi kiểm tra các câu hỏi này.

## 42. Trường hợp “commit log xuất hiện nhưng lag không giảm”

Triệu chứng:

~~~text
Commit log liên tục xuất hiện
Consumer group lag vẫn tăng
~~~

Có thể do:

- Producer ingress rate lớn hơn tốc độ consumer commit.
- Commit vẫn ở offsets thấp dù được gọi thường xuyên.
- Logger ghi request trước khi commit, các commits đang fail.
- Lag dashboard dùng group/topic khác.
- One partition stuck, những partitions khác tiến.
- Consumer đang đọc lại records do commit failure/rebalance.
- LEO tăng rất nhanh trong khi processing throughput không đổi.
- read_committed LSO/metrics definition tạo khác biệt.

So sánh **delta của committed offset** với **delta của log end offset** trên từng partition, thay vì chỉ đếm số lần commit.

## 43. Trường hợp “commit log nói 501 nhưng CLI nói 500”

Không nhất thiết là dữ liệu sai.

Các giả thuyết:

1. Log mô tả commit intent, commit thực tế fail.
2. CLI snapshot lấy trước khi commit hoàn thành.
3. Bạn đang nhìn nhầm consumer group.
4. Log thuộc một instance khác, environment khác hoặc partition khác.
5. Commit asynchronous chưa được xác nhận.
6. Kafka transaction chưa commit hoặc đã abort.
7. Sau đó có reset/seek/administrative offset change.

Checklist:

~~~text
same Kafka cluster?
same consumer group?
same topic-partition?
same observation time?
commit outcome known?
transaction committed?
rebalance occurred?
~~~

Chỉ khi đối chiếu đủ các thông tin này mới nên đưa ra kết luận.

## 44. Trường hợp “offset commit thất bại liên tục”

Khi commit failure tăng:

1. Xem root exception và consumer group coordinator.
2. Xem rebalance frequency và max.poll.interval.ms.
3. Kiểm tra listener có blocking calls quá lâu không.
4. Xem broker/network latency.
5. Xem group authorization và credential rotation.
6. Xem lifecycle stop/close/wakeup có xảy ra gần đó không.
7. Nếu transactional, xem producer fencing/transaction abort.
8. Kiểm tra source offsets có redeliver không.
9. Đảm bảo business handler idempotent trước khi retry/replay.

Không cố gọi commitSync vô hạn từ thread ngoài consumer để “bắt kịp” khi coordinator đang rebalance. KafkaConsumer không có thread-safety chung cho thao tác từ nhiều threads.

Nếu group đã mất partition ownership, dữ liệu có thể cần được xử lý lại ở owner mới từ committed offset hợp lệ.

## 45. Cách thu thập log chẩn đoán theo incident

Một quy trình an toàn:

**Bước 1 — Xác định mục tiêu**

Bạn cần biết next offsets của partition nào, hay cần xem outcome commit failure?

**Bước 2 — Thu hẹp scope**

Chọn service, consumer group, listener ID, topic-partition và khoảng thời gian.

**Bước 3 — Bật log phù hợp**

Nếu chỉ cần offsets container định commit, cấu hình commitLogLevel và backend logger phù hợp. Nếu cần request/response internals, bật client DEBUG trong phạm vi giới hạn.

**Bước 4 — Ghi timeline**

Ghi listener delivered/processed, error handler, commit intent/outcome, rebalance và transaction.

**Bước 5 — Đối chiếu broker**

Chạy consumer-groups describe hoặc sử dụng group offset metrics để xác nhận committed offset.

**Bước 6 — Khôi phục log policy**

Hạ logging level sau incident, giữ lại trace/metrics cần thiết, ghi kết luận vào runbook.

Một mức log chi tiết bật vĩnh viễn thường không tốt bằng một cơ chế metrics và incident diagnostics có thời hạn rõ ràng.

## 46. Ví dụ cấu hình chẩn đoán tương đối đầy đủ

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
diagnosticOrdersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    var props = factory.getContainerProperties();

    // Commit sau khi hoàn tất poll batch.
    props.setAckMode(ContainerProperties.AckMode.BATCH);

    // Dùng synchronous consumer commits nếu không transactional.
    props.setSyncCommits(true);

    // Đưa container commit messages lên INFO cho giai đoạn điều tra.
    props.setCommitLogLevel(LogIfLevelEnabled.Level.INFO);

    return factory;
}
~~~

Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      max-poll-records: 200

logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

Nếu dùng transactional container, cần cấu hình Kafka transaction manager thích hợp và diễn giải commit offsets theo transactional path, không mặc định setSyncCommits là yếu tố quyết định outcome.

Ví dụ này dành cho logging và chẩn đoán, không phải đề xuất mọi consumer production nên dùng BATCH + syncCommits + INFO. Chọn các cấu hình theo SLO, load và delivery requirements.

## 47. Kết hợp log với Retry/Recovery metrics

Một record có thể được retry rồi recovery:

~~~text
Offset 100 -> listener fails
      |
      v
Retry 1 -> fails
      |
      v
Retry 2 -> fails
      |
      v
DLT publish succeeds
      |
      v
Container progresses source offset to 101
~~~

Commit log cho next offset 101 không cho biết:

- Có bao nhiêu retries đã thực thi.
- Vì sao listener fail.
- DLT publish thật sự confirmed hay chưa.
- DLT consumer có xử lý record không.

Nên có metrics:

- listener_attempts_total.
- retry_attempts_started_total.
- recovery_attempts_total.
- recovery_succeeded_total.
- dlt_publish_confirmed_total.
- committed_offset_progress.

Các metric names là gợi ý, không phải đều built-in. Phân biệt recovery success với business success để không che giấu lỗi nghiệp vụ dưới commit progress.

## 48. Một bảng đối chiếu chẩn đoán nhanh

| Tín hiệu | Khả năng giải thích | Việc cần kiểm tra thêm |
|---|---|---|
| Commit INFO logs xuất hiện đều | Container đang đi qua commit logging path | Broker outcome/CLI, listener success |
| Không thấy commit logs | Logger bị lọc, chưa commit hoặc transactional path | AckMode, logger, transaction, CLI |
| Commit offset tăng ít | Processing chậm hoặc ít records | Input rate, lag, listener latency |
| Commit offset tăng nhiều | Batch processing hoặc nhiều records | AckMode, records count, recovery |
| Commit log có mà commit failed metric tăng | Log có thể là intent | Async callbacks, exceptions |
| Committed offset đứng yên và lag tăng | Consumer chưa tiến triển | Pause, retry, rebalance, dependency |
| Committed offset đứng yên và lag=0 | Có thể không có input mới | Producer rate/assignment |
| Transaction abort tăng | Offset/output có thể không commit | Producer timeout/fencing, read_committed |
| DLT recovery tăng và commit tăng | Lỗi có thể được chuyển DLT | DLT backlog và business outcome |
| Rebalance tăng cùng commit failures | Ownership/group generation biến động | max.poll.interval.ms, assignor, lifecycle |

## 49. Kiểm thử commit log level

Việc kiểm thử gồm hai mục tiêu: xác minh **mức log được cấu hình** và xác minh **cách interpret log**.

### 49.1. Mặc định DEBUG bị lọc

Chạy listener container trong test environment, đặt logger threshold INFO và giữ commitLogLevel mặc định theo version. Xác nhận không tự coi sự vắng mặt commit log là commit failure; kiểm tra committed offset riêng.

### 49.2. Bật commitLogLevel.INFO

Đặt container property INFO và backend logger INFO. Publish record, chờ listener xử lý thành công và xác nhận commit log xuất hiện theo implementation/version.

### 49.3. Logger WARN chặn commit INFO

Giữ commitLogLevel.INFO nhưng đặt backend logger WARN. Xác nhận commit behavior vẫn không đổi dù commit INFO message không còn hiển thị.

### 49.4. AckMode.RECORD so với BATCH

Gửi nhiều records từ một poll. Quan sát số lần commit/mẫu offset và xác minh committed offsets. Không áp đặt số log lines đúng bằng số records.

### 49.5. Manual acknowledgement

Đặt MANUAL_IMMEDIATE; cho listener xử lý rồi acknowledge. Kiểm tra commit sau ack và trường hợp không acknowledge trước khi process terminate.

### 49.6. Commit failure

Giả lập broker/coordinator hoặc group membership error trong test cluster. Xác nhận log attempt không bị hiểu là success và metrics/callback phản ánh exception.

### 49.7. Transactional listener

Gửi transactional output và consumed offset cùng transaction, rồi ép abort. Xác nhận read_committed visibility và committed source offset, không dùng direct commit log làm phép kiểm chứng duy nhất.

### 49.8. Rebalance và shutdown

Gây rebalance hoặc terminate một instance trong test. Xác nhận offset behavior/duplicate handling và tránh kết luận rằng một dòng log trước crash bảo đảm commit đã hoàn tất.

Các test này thuộc quy trình integration riêng của ứng dụng, không phải yêu cầu chạy Gradle hay test project trong bước soạn nội dung bài học.

## 50. Những lỗi cấu hình thường gặp

| Cách làm | Vấn đề | Cách điều chỉnh |
|---|---|---|
| Chỉ đặt logging.level=INFO | Commit log mặc định DEBUG có thể bị ẩn | Set commitLogLevel(INFO) nếu muốn INFO |
| Chỉ set commitLogLevel(INFO) | Backend logger WARN vẫn lọc message | Cấu hình logger threshold tương thích |
| Đặt trên factory không được listener dùng | Không có hiệu lực với listener cần quan sát | Xác nhận containerFactory |
| Bật DEBUG cho cả Kafka clients toàn production | Logs khổng lồ, khó điều tra | Chọn category và thời hạn |
| Đếm log lines như commits thành công | Log có thể là intent, chứa nhiều partitions | Quan sát outcome và group offsets |
| Đếm log lines như records processed | AckMode.BATCH/TIME làm không tương ứng | Đo listener records riêng |
| Hiểu commit offset N là record N đã xử lý | Kafka commit lưu next offset | So sánh lastProcessed=N-1 |
| Bật enable.auto.commit ngoài ý muốn | Client và container semantics có thể lệch | Để container quản lý offsets |
| Gọi commitSync từ thread khác | KafkaConsumer không thread-safe chung | Dùng container APIs |
| Coi transaction output và offset là direct consumer commit | Hiểu sai EOS path | Xem producer transaction outcome |
| Commit sau DLT được tính là business success | Poison record chưa được xử lý nghiệp vụ | DLT/Business metrics riêng |
| Chỉ nhìn lag tổng | Partition bị kẹt bị che | Soi offsets theo partition |
| Không đối chiếu rebalance | Nhầm commit failure do mất ownership | Xem assign/revoke/lost events |
| Bật log chi tiết nhưng không tắt | Tăng chi phí log lâu dài | Incident scope và rollback level |
| Đưa payload/token vào log | Lộ dữ liệu nhạy cảm | Chỉ log metadata cần thiết |

## 51. Runbook: không thấy commit logs

**Bước 1 — Kiểm tra trạng thái container**

Listener container có running không? Có partitions assigned không? Có paused hay đang rebalance không?

**Bước 2 — Kiểm tra cấu hình log**

commitLogLevel đang là DEBUG/INFO? Backend threshold đang là INFO/DEBUG/WARN? Appender có filter hoặc sampling không?

**Bước 3 — Kiểm tra container factory**

@KafkaListener dùng đúng factory không? Configuration đã được áp dụng trước khi container khởi động không?

**Bước 4 — Kiểm tra commit semantics**

AckMode là gì? enable.auto.commit có tắt không? Listener có manual acknowledge chưa? Có transactional path không?

**Bước 5 — Đối chiếu Kafka group**

Kafka CLI CURRENT-OFFSET có tiến không? Nếu có, logging gap không đồng nghĩa commit gap.

**Bước 6 — Đối chiếu processing**

Listener success rate, failures, retry/DLT, lag, last record age và poll responsiveness ra sao?

**Bước 7 — Hành động**

Điều chỉnh logging có thời hạn nếu chỉ là thiếu visibility. Nếu commit thực sự không tiến, sửa root cause về listener, ack, broker/group hoặc transaction.

## 52. Runbook: commit failures tăng

**Bước 1:** Xác định sync hay async commit; lấy error outcome thực tế.

**Bước 2:** Xem group coordinator, network, ACL và consumer client logs.

**Bước 3:** Kiểm tra max.poll.interval.ms và listener processing time.

**Bước 4:** Đối chiếu rebalance/revocation với thời gian commit failures.

**Bước 5:** Nếu transactional, kiểm tra transaction timeout, producer fencing và commit/abort.

**Bước 6:** Xác nhận records có redeliver; bảo vệ database/HTTP side effects bằng idempotency.

**Bước 7:** Xác minh group offsets và consumer lag sau khắc phục.

Không xử lý bằng cách cưỡng ép commit vượt quá record chưa xử lý chỉ để log hoặc dashboard cho thấy lag giảm.

## 53. Runbook: commit log tăng nhưng nghiệp vụ thiếu dữ liệu

Một luồng có thể commit offsets sau khi recoverer gửi record sang DLT. Nếu downstream không xử lý DLT, người dùng có thể nhận thấy một nghiệp vụ “mất” dù Kafka group lag bằng 0.

Để điều tra:

1. Xác định source offset và key/event ID của record.
2. Xem listener attempts và failures.
3. Xem DefaultErrorHandler/recovery classification.
4. Xác nhận DLT publication và DLT consumer progress.
5. Xem business database/side effects.
6. Kiểm tra manual acknowledgements có bị gọi quá sớm không.
7. Xem transaction boundaries và offset commit order.
8. Thiết kế replay DLT có idempotency khi sửa lỗi dữ liệu.

**Consumer group lag bằng 0 không bảo đảm 100% business events đã được xử lý thành công.** Nó chỉ phản ánh tiến độ offsets theo cách group lưu trữ.

## 54. Checklist trước khi bật commitLogLevel.INFO

1. Có xác định đúng listener container và consumer group cần điều tra không?
2. ContainerProperties.commitLogLevel đã được đặt đúng API Spring Kafka version chưa?
3. Backend logger threshold có cho phép mức INFO không?
4. Logger category thực tế đã được xác minh từ logs chưa?
5. Listener có dùng đúng ConcurrentKafkaListenerContainerFactory đó không?
6. enable.auto.commit có được cấu hình theo ownership của offsets không?
7. AckMode và syncCommits có được hiểu chính xác không?
8. Nếu dùng manual ack, listener có ack sau xử lý thành công không?
9. Nếu dùng Kafka transaction, có theo dõi commit/abort và sendOffsetsToTransaction không?
10. Có biết log đang mô tả commit intent hay confirmed outcome không?
11. Có Kafka CLI/consumer group metrics để đối chiếu committed offsets không?
12. Có phân biệt committed next offset với last processed record offset không?
13. Có kết hợp retry/recovery/DLT metrics để không nhầm commit với business success không?
14. Có quan sát consumer lag theo từng partition, không chỉ group tổng không?
15. Có log/metrics cho rebalance, pause, shutdown và commit failures không?
16. Có chuẩn hóa correlation IDs và tránh payload/secrets trong logs không?
17. Có ước lượng log volume/ingest cost khi bật INFO không?
18. Có phạm vi, người chịu trách nhiệm và deadline tắt log chi tiết không?
19. Có test sync/async, AckMode, commit failure và transactional abort trong môi trường test không?
20. Có runbook cho trường hợp log commit không xuất hiện, commit failed, hoặc commit tiến nhưng business failure không?

## 55. Kết luận

**Commit log level** là một công cụ quan sát của Spring Kafka listener container, chủ yếu được cấu hình qua **ContainerProperties.setCommitLogLevel(LogIfLevelEnabled.Level)**. Nó giúp đưa thông tin offset commit lên mức log phù hợp, ví dụ INFO trong một incident. Tuy nhiên, message chỉ xuất hiện khi logging backend cũng cho phép, và việc thấy một commit log không tự động chứng minh broker đã xác nhận offset, mọi record đã xử lý thành công, hoặc mọi side effect ngoài Kafka được commit nguyên tử.

Để chẩn đoán đáng tin cậy, hãy đọc log theo **topic-partition-next offset**, hiểu **AckMode**, phân biệt **commitSync** và **commitAsync**, xem **rebalance/retry/recovery**, và xử lý riêng **Kafka transactional offset commit**. Sau đó đối chiếu với consumer group committed offsets, retry/DLT outcomes, transaction metrics và nghiệp vụ thực tế.

Trong production, cách tốt nhất là **dùng log có thời hạn và scope rõ ràng cho điều tra**, sử dụng metrics để quan sát xu hướng dài hạn, và luôn bảo vệ consumer bằng idempotency để hệ thống vẫn đúng khi commit thất bại hoặc record phải được xử lý lại.
