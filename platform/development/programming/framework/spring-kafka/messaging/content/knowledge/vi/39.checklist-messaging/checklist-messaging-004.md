# Checklist cấu hình consumer trong Spring Kafka

Consumer chỉ vận hành ổn định khi cấu hình Kafka client, listener container và xử lý nghiệp vụ được chọn đồng bộ. Một consumer có thể kết nối broker thành công nhưng vẫn đọc sai dữ liệu do group ID hoặc offset policy không phù hợp; có thể nhận record nhưng không commit offset; hoặc bị rebalance vì listener xử lý lâu hơn poll budget. Checklist này giúp rà soát cấu hình trước khi chạy integration test và triển khai production.

Phạm vi gồm consumer đơn record và các lựa chọn thường gặp trong Spring Kafka: bootstrap server, consumer group, offset, deserializer, poll/fetch, concurrency, acknowledgment, retry/DLT, security, monitoring và shutdown. Các giá trị số trong ví dụ chỉ là điểm khởi đầu; cần đo tải và xác định yêu cầu ordering, latency, durability trước khi dùng thực tế.

## 1. Checklist tổng thể

| Nhóm | Câu hỏi cần trả lời | Bằng chứng cần có |
|---|---|---|
| Kết nối | Consumer kết nối đúng cluster và security protocol chưa? | Bootstrap servers, TLS/SASL test |
| Identity | Group ID có ổn định và tách đúng môi trường/service không? | Consumer group description |
| Offset | Khi group chưa có offset thì bắt đầu ở đâu? Khi nào commit? | Offset policy, AckMode, integration test |
| Deserialize | Payload/schema được chuyển thành kiểu Java nào? | Serializer contract và malformed-message test |
| Poll/fetch | Consumer có đủ thời gian xử lý và bộ nhớ cho batch không? | Processing duration, poll/fetch metrics |
| Concurrency | Số consumer có phù hợp partition count và downstream capacity không? | Assignment, thread-safety review |
| Error handling | Exception nào retry, exception nào đi DLT? | Error handler policy và DLT test |
| Security | Principal chỉ có quyền cần thiết không? | ACL test và secret management |
| Observability | Có thể tìm record và phát hiện lag/stuck không? | Logs, metrics, alerts |
| Lifecycle | Start, pause, stop và shutdown có an toàn không? | Lifecycle test và deployment runbook |

Không đánh dấu một mục là hoàn tất chỉ vì đã có property trong YAML. Cần có bằng chứng rằng cấu hình được bind vào đúng ConsumerFactory/container và hành vi đã được kiểm thử.

## 2. Chọn đúng bootstrap servers và môi trường

Khai báo bootstrap servers của cluster mà consumer cần đọc:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Kiểm tra:

- Địa chỉ bootstrap thuộc đúng môi trường dev, test, staging hoặc production.
- Danh sách có đủ broker endpoint để client lấy metadata khi một broker không khả dụng.
- DNS, port, network policy và firewall cho phép workload kết nối.
- Không trộn bootstrap server của cluster nguồn và cluster đích.
- Nếu dùng nhiều cluster, tạo ConsumerFactory/container factory riêng và đặt tên rõ ràng.
- Không hard-code địa chỉ production trong source code hoặc test fixture.

Bootstrap server chỉ là điểm khởi đầu để lấy metadata. Sau đó client kết nối tới broker leader/coordinator được metadata trả về; vì vậy, toàn bộ advertised listener address phải truy cập được từ môi trường chạy ứng dụng.

## 3. Xác định consumer group ID

Group ID xác định danh tính consumer group và phạm vi offset được Kafka lưu. Các consumer cùng group chia nhau partition; consumer ở group khác có thể đọc độc lập cùng topic.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection
```

Checklist:

- Group ID ổn định giữa các lần restart của cùng logical application.
- Tách group ID giữa các ứng dụng có mục đích xử lý độc lập.
- Tách group ID giữa môi trường dev/staging/production.
- Không tạo group ID ngẫu nhiên mỗi lần khởi động nếu muốn tiếp tục offset cũ.
- Không dùng chung group ID cho hai consumer có logic nghiệp vụ khác nhau chỉ để “chia tải”.
- Ghi nhận group ID trong log và dashboard để điều tra lag.

Nếu hai listener cần nhận độc lập mọi record, chúng phải dùng group ID khác nhau. Nếu cùng group ID, Kafka phân phối partition giữa các consumer trong group thay vì broadcast từng record tới mọi listener.

## 4. Chọn auto-offset-reset đúng nghiệp vụ

`auto.offset.reset` chỉ được áp dụng khi group không có committed offset hợp lệ, hoặc offset hiện tại không còn hợp lệ theo retention/available log range. Nó không tự tua một group đã có offset về đầu topic mỗi lần ứng dụng restart.

| Giá trị | Hành vi khi không có offset hợp lệ | Trường hợp thường dùng |
|---|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất còn lưu | Consumer mới cần xử lý lịch sử còn retention |
| `latest` | Bắt đầu từ dữ liệu mới được ghi sau thời điểm khởi tạo | Chỉ quan tâm dữ liệu mới; chấp nhận bỏ qua lịch sử trước khi group bắt đầu |
| `none` | Ném lỗi nếu không tìm thấy offset hợp lệ | Muốn fail fast để operator quyết định offset |

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
```

Trước khi chọn, trả lời:

- Consumer mới có phải đọc lại dữ liệu lịch sử không?
- Topic còn retention đủ dài cho thời gian consumer có thể offline không?
- Khi offset hết hạn, hệ thống muốn tự bắt đầu lại hay cần dừng để operator quyết định?
- Replay có thể tạo side effect trùng trong database hoặc downstream không?

Không dùng `earliest` như một cách sửa lag hoặc reset offset. Muốn replay một group đã có offset, dùng quy trình reset/seek có kiểm soát, ghi lại offset cũ và đánh giá side effect trước khi thực hiện.

## 5. Cấu hình deserializer theo event contract

Consumer phải deserialize đúng kiểu dữ liệu producer đã gửi. Cấu hình key và value deserializer rõ ràng:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.event.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders.event
```

Ví dụ dùng `ErrorHandlingDeserializer` bọc `JsonDeserializer` để lỗi deserialize có thể được chuyển vào error handling/recovery của Spring Kafka. Tên class, package và property phải khớp model cùng dependency thực tế.

Checklist:

- Key deserializer khớp với key serializer của producer.
- Value deserializer khớp format: String, JSON, Avro, Protobuf hoặc custom.
- Có event contract/schema version được quản lý.
- Trusted packages chỉ chứa package cần thiết; không dùng wildcard rộng tùy tiện.
- Nếu dùng type headers, xác định producer nào được phép cung cấp type metadata.
- Nếu không dùng type headers, cấu hình default target type hoặc converter rõ ràng.
- Có test cho payload hợp lệ, payload sai định dạng, schema cũ và field mới.
- Có chính sách cho tombstone (value null) nếu topic compacted.

Không coi lỗi deserialize là lỗi nghiệp vụ thông thường. Listener method có thể chưa được gọi khi deserialize thất bại; cần kiểm tra ErrorHandlingDeserializer, error handler và khả năng publish raw bytes vào DLT.

## 6. Kiểm soát type headers và trusted packages

JSON deserializer của Spring Kafka có thể sử dụng type information trong Kafka headers. Đây là tiện ích khi nhiều event type được trao đổi, nhưng type header đến từ producer và cần được kiểm soát.

Checklist:

- Chỉ tin cậy package chứa event DTO được phép.
- Không bật trusted packages cho toàn bộ classpath nếu không cần.
- Thống nhất type mapping giữa producer và consumer khi package/class name khác nhau.
- Nếu schema đã xác định một kiểu cố định, cân nhắc cấu hình default type và không phụ thuộc type header.
- Kiểm tra compatibility khi đổi package, đổi class hoặc triển khai nhiều phiên bản service cùng lúc.
- Không deserialize class tùy ý từ dữ liệu không tin cậy.

Nếu dùng Schema Registry với Avro/Protobuf, quản lý subject naming strategy, schema compatibility và credentials riêng. Không áp dụng cấu hình JSON deserializer cho serializer format khác.

## 7. Tắt auto commit và chọn AckMode

Với Spring Kafka listener container, nên để container quản lý commit thay vì bật Kafka auto commit:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Spring Kafka container mặc định đặt `enable.auto.commit=false` nếu chưa cấu hình khác; khai báo tường minh giúp intent dễ review. Khi auto commit tắt, container dùng AckMode để quyết định thời điểm commit.

| AckMode | Khi commit | Cần cân nhắc |
|---|---|---|
| `RECORD` | Sau khi listener xử lý xong từng record | Dễ hiểu với record listener; commit thường xuyên hơn |
| `BATCH` | Sau khi xử lý hết batch từ poll | Throughput tốt hơn; lỗi có thể ảnh hưởng batch |
| `TIME` | Khi đủ thời gian commit và batch xử lý hoàn tất | Cần hiểu chu kỳ commit |
| `COUNT` | Khi đủ số record theo ngưỡng | Cân bằng số lần commit và lượng xử lý |
| `COUNT_TIME` | Kết hợp ngưỡng count và time | Cần test tải và failure |
| `MANUAL` | Ứng dụng gọi acknowledge; commit theo semantics container | Phải đảm bảo mọi nhánh xử lý đều ack đúng |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge trên consumer thread theo điều kiện hỗ trợ | Cần tuân thủ thread/ordering contract |

`BATCH` là AckMode mặc định phổ biến của container khi auto commit tắt. Chọn `RECORD` hoặc `BATCH` tường minh theo yêu cầu, không dựa vào default ngầm.

Không acknowledge trước khi side effect nghiệp vụ hoàn tất. Nếu database đã ghi nhưng offset chưa commit, record có thể được giao lại; consumer cần idempotency hoặc inbox/deduplication nếu side effect không được phép lặp.

## 8. Chọn isolation.level khi đọc transactional topic

Nếu producer sử dụng Kafka transaction, consumer có thể cần:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

Hai lựa chọn chính:

- `read_uncommitted`: có thể đọc record thuộc transaction chưa commit hoặc đã abort.
- `read_committed`: chỉ đọc record đã commit; record thuộc transaction bị abort không được trả cho ứng dụng.

Nếu luồng nghiệp vụ yêu cầu chỉ xử lý dữ liệu đã commit từ transactional producer, chọn `read_committed`. Cần hiểu rằng consumer có thể bị giới hạn bởi last stable offset khi transaction còn mở lâu; điều này ảnh hưởng tới khả năng đọc record phía sau trên partition.

Nếu producer không dùng transaction và không cần transactional visibility, không tự động thêm cấu hình chỉ vì tên bài học có “exactly-once”. Hãy chọn theo semantics nguồn dữ liệu.

## 9. Cấu hình poll timeout và heartbeat

Ba property cần được hiểu đúng:

| Property | Vai trò |
|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần `poll()`; nếu xử lý một poll quá lâu, consumer có thể rời group |
| `session.timeout.ms` | Broker chờ heartbeat hợp lệ trước khi xem consumer là mất kết nối |
| `heartbeat.interval.ms` | Khoảng thời gian client gửi heartbeat trong classic group protocol |

Ví dụ minh họa:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.poll.interval.ms]": 300000
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
```

Không copy nguyên các con số này nếu chưa đo. Khi listener xử lý tuần tự, thời gian xử lý toàn bộ records của poll, cộng thời gian chờ dependency, retry, GC pause và overhead phải nằm trong poll budget.

`session.timeout.ms` không thay thế timeout cho HTTP/DB. `max.poll.interval.ms` không phải timeout cho một câu query. Đặt connect/read/query timeout hữu hạn ở downstream và chọn poll budget dựa trên processing duration p95/p99.

Với Kafka consumer group protocol mới (`group.protocol=consumer`), một số heartbeat/session behavior được điều khiển phía broker và property client có thể không còn áp dụng như classic protocol. Kiểm tra protocol và Kafka client version trước khi tinh chỉnh.

## 10. Chọn max.poll.records theo thời gian xử lý

`max.poll.records` giới hạn số record trả về trong một lần poll. Giá trị lớn có thể tăng throughput nhưng cũng làm batch xử lý lâu hơn và tăng bộ nhớ cần cho payload đang giữ.

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.poll.records]": 100
```

Chọn giá trị dựa trên:

- Thời gian xử lý một record và batch p95/p99.
- Payload trung bình và payload lớn nhất.
- Số record có thể chờ trong memory.
- Thời gian gọi database/API.
- `max.poll.interval.ms`.
- AckMode và semantics retry.

Giảm `max.poll.records` nếu batch xử lý quá lâu hoặc memory pressure cao. Tăng từ từ khi đo được consumer còn dư poll budget và downstream chịu được tải.

Đối với batch listener, kiểm tra batch có thể chứa record từ nhiều partition. Không giả định offset liên tục hoặc chỉ có một partition trong một poll.

## 11. Chọn fetch size và memory budget

Các property fetch ảnh hưởng lượng dữ liệu consumer nhận từ broker:

| Property | Ý nghĩa |
|---|---|
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch response |
| `fetch.max.wait.ms` | Thời gian broker tối đa chờ đủ `fetch.min.bytes` |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition |
| `fetch.max.bytes` | Giới hạn tổng dữ liệu fetch trong một request |

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
        "[max.partition.fetch.bytes]": 1048576
        "[fetch.max.bytes]": 52428800
```

Giá trị trên chỉ để minh họa. Tăng `fetch.min.bytes` có thể cải thiện throughput bằng batching nhưng tăng latency. Giảm `fetch.max.wait.ms` có thể giảm thời gian chờ nhưng tăng số request. Fetch limit cần phù hợp kích thước record batch và memory budget.

Kafka có thể trả batch đầu tiên lớn hơn một số fetch limit để consumer vẫn có thể tiến triển khi batch lớn hơn giới hạn cấu hình. Vì vậy, không dùng các property này như giới hạn cứng duy nhất để bảo vệ heap; cần giới hạn message size ở producer/broker/topic và theo dõi memory.

## 12. Chọn concurrency theo partition và downstream

Ví dụ cấu hình listener:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

Concurrency tạo nhiều consumer trong cùng group cho listener container. Số consumer thực sự có thể nhận partition bị giới hạn bởi partition assignment.

Checklist:

- Tổng concurrency không vượt năng lực xử lý downstream.
- Đối chiếu concurrency với số partition của các topic được subscribe.
- Chấp nhận consumer dư ở trạng thái idle nếu concurrency lớn hơn partition assignment.
- Kiểm tra partition key có phân phối đều hay tạo hot partition.
- Listener bean singleton phải thread-safe khi nhiều consumer gọi đồng thời.
- Không chia sẻ mutable state không đồng bộ giữa listener threads.
- Với database, pool size phải đủ cho concurrency nhưng không gây quá tải database.

Tăng concurrency không tự tăng throughput nếu chỉ có một partition hoặc downstream đã bão hòa. Khi cần mở rộng song song, có thể phải tăng partition count và đánh giá lại key/ordering strategy.

## 13. Cấu hình container factory rõ ràng

Spring Boot có thể tự cấu hình listener container factory từ `spring.kafka.*`. Khi cần policy riêng, tạo factory tường minh:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

Listener dùng factory:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.created.v1",
        groupId = "orders-projection",
        containerFactory = "orderListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Nếu chỉ có một policy chung, dùng Boot auto-configuration giúp giảm cấu hình trùng lặp. Nếu tạo custom factory, kiểm tra nó có kế thừa các property cần thiết như error handler, observation, converter, interceptors và common container properties hay không. Không giả định factory tự khai báo tự nhận toàn bộ `spring.kafka.listener.*`.

## 14. Record listener hay batch listener

Chọn loại listener theo semantics xử lý:

| Loại | Đặc điểm | Phù hợp |
|---|---|---|
| Record listener | Gọi method cho từng record | Logic nghiệp vụ độc lập, dễ retry từng record |
| Batch listener | Method nhận một batch records từ poll | Xử lý theo lô, bulk insert hoặc giảm overhead |

Checklist:

- `@KafkaListener` method signature khớp listener type của container factory.
- Batch listener xử lý partial failure theo policy rõ ràng.
- Không coi cả batch thành công nếu một record chưa được xử lý.
- Xác định offset commit behavior khi một phần batch thất bại.
- Có giới hạn batch size và thời gian xử lý.
- Test batch có record từ nhiều partition và record lỗi ở vị trí khác nhau.

Không đổi `factory.setBatchListener(true)` mà không sửa method signature và test error handling tương ứng.

## 15. Cấu hình error handler và retry policy

Consumer cần policy riêng cho lỗi transient và lỗi không thể tự phục hồi:

| Loại lỗi | Ví dụ | Chính sách thường dùng |
|---|---|---|
| Lỗi tạm thời | Timeout dịch vụ inventory, network chập chờn | Retry có giới hạn và backoff |
| Lỗi dữ liệu | Validation fail, field bắt buộc thiếu | Không retry hoặc retry rất hạn chế; chuyển DLT |
| Lỗi deserialize | JSON/schema không hợp lệ | ErrorHandlingDeserializer và recovery/DLT |
| Lỗi authorization | ACL không cho đọc hoặc publish DLT | Sửa quyền; retry không tự giải quyết |
| Lỗi lập trình | NullPointerException, invariant bị vi phạm | Điều tra; tránh retry vô hạn |

Với blocking retry, cấu hình `DefaultErrorHandler` và `BackOff` phù hợp. Với non-blocking retry, cấu hình `@RetryableTopic` và retry topics theo nhu cầu. Không áp dụng hai cơ chế mà không hiểu tổng số lần delivery và thứ tự xử lý.

Checklist:

- Có phân loại exception retryable/non-retryable.
- Có giới hạn attempts và backoff rõ.
- Backoff không khiến consumer vượt poll budget ngoài dự kiến.
- Có DLT hoặc recovery strategy cho record không xử lý được.
- DLT publisher có thể serialize cả record bình thường và raw bytes khi deserialize thất bại.
- Retry/DLT topic có ACL, retention, monitoring và quy trình replay.
- Không log payload nhạy cảm trong exception hoặc DLT handler.

## 16. DLT và quyền truy cập

DLT không phải nơi “ném record đi rồi quên”. Cần xác định ai xử lý, thời hạn lưu và quy trình replay:

- Topic DLT có tên và partition strategy ổn định.
- DLT đủ partition nếu recoverer giữ nguyên partition nguồn.
- Consumer/operator có quyền đọc DLT được giới hạn.
- Record giữ metadata nguồn như original topic, partition, offset và exception type.
- Có cảnh báo khi DLT tăng.
- Replay phải có event ID/idempotency để tránh side effect trùng.
- Có quy trình đóng lỗi và xóa dữ liệu theo retention policy.

Nếu dùng `DeadLetterPublishingRecoverer`, kiểm tra destination resolver và serializer của producer được dùng để publish. Nếu source record chưa deserialize, recoverer có thể cần publish `byte[]`; cấu hình template/serializer phải hỗ trợ đúng kiểu value.

## 17. Chọn isolation và transaction phù hợp

Nếu consumer tham gia Kafka transaction hoặc đọc dữ liệu từ transactional producer:

- Dùng `isolation.level=read_committed` nếu chỉ xử lý record đã commit.
- Với consume-transform-produce exactly-once, cấu hình transaction manager và listener container theo mô hình Spring Kafka.
- Không commit offset độc lập ngoài transaction khi yêu cầu cần atomically commit output và input offset.
- Không giả định Kafka transaction bao phủ database hoặc HTTP API.
- Với side effect ngoài Kafka, dùng idempotency, inbox/outbox hoặc cơ chế phối hợp phù hợp.

Nếu không cần transactional semantics, giữ cấu hình đơn giản và chọn `read_uncommitted`/default theo yêu cầu hệ thống. Đừng thêm transaction chỉ để “tăng độ an toàn” khi chưa xác định failure model.

## 18. Bảo mật consumer

Ví dụ SASL_SSL với SCRAM:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": ${KAFKA_CONSUMER_JAAS_CONFIG}
```

Checklist:

- Secret lấy từ secret manager/config tree/environment được kiểm soát.
- Không commit JAAS password hoặc TLS private key vào repository.
- Consumer principal chỉ có READ/DESCRIBE trên topic cần thiết.
- Principal có quyền READ trên consumer group cần join/commit offset.
- Quyền đọc retry/DLT chỉ cấp khi consumer cần.
- Không dùng superuser credential chung cho mọi service.
- TLS hostname verification được giữ bật.
- Có quy trình rotation credential/certificate.
- Không log toàn bộ consumer properties vì có thể chứa secret.

Tên ACL operation cụ thể phụ thuộc Kafka authorizer/distribution; kiểm thử bằng principal thực tế trong môi trường tương đương production.

## 19. Observability cho consumer

Tối thiểu cần theo dõi:

| Tín hiệu | Mục đích |
|---|---|
| Consumer lag theo group/topic/partition | Biết consumer có tụt lại không |
| Records consumed rate | Biết tốc độ xử lý |
| Listener processing duration p95/p99 | Phát hiện listener chậm hoặc stuck |
| Commit rate/latency và commit failure | Phát hiện offset không tiến triển |
| Rebalance count | Phát hiện group không ổn định |
| Retry/DLT rate | Phát hiện lỗi nghiệp vụ hoặc dependency |
| Assigned partitions/member count | Phát hiện consumer không có assignment |
| Authentication/authorization errors | Phát hiện cấu hình bảo mật sai |

Log record-level nên có event ID, group ID, topic, partition và offset nhưng không chứa payload nhạy cảm. Metric label không nên dùng event ID, offset hoặc order ID vì cardinality tăng không giới hạn.

Alert nên xét lag duy trì trong thời gian đủ dài, offset không tiến triển khi log end offset vẫn tăng, listener duration vượt SLA hoặc rebalance lặp lại. Lag bằng 0 và không có record mới là trạng thái idle bình thường.

## 20. Shutdown và lifecycle

Khi ứng dụng shutdown hoặc deploy:

- Container được stop theo Spring lifecycle.
- Listener có cơ hội hoàn tất record đang xử lý trong shutdown timeout.
- Consumer đóng và rời group; rebalance được dự kiến.
- Offset chỉ được commit theo AckMode/transaction đã cấu hình.
- Side effect chưa commit có thể dẫn tới redelivery sau restart.
- Consumer phải idempotent hoặc có cơ chế dedup nếu redelivery có thể lặp nghiệp vụ.

Không kill process liên tục để dừng consumer nếu có thể dùng graceful shutdown. Cấu hình shutdown timeout phù hợp thời gian xử lý tối đa và nền tảng deploy termination grace period.

Nếu dùng `KafkaListenerEndpointRegistry` để pause/stop động, cần audit thao tác và xác minh container được resume/start lại đúng lúc. Không để listener bị pause vĩnh viễn do một nhánh quản trị thất bại.

## 21. Bộ cấu hình baseline để review

Đây là ví dụ tổng hợp cho một JSON record listener; các con số chỉ mang tính minh họa:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: orders-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.event.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders.event
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 100
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
    listener:
      ack-mode: record
      concurrency: 3
```

Trước khi dùng baseline, phải xác nhận:

- `earliest` có đúng yêu cầu xử lý lịch sử của group mới không.
- `read_committed` có cần thiết nếu nguồn dùng transaction không.
- JSON type header/default type khớp event contract không.
- Poll interval và max records phù hợp processing duration thực tế không.
- Concurrency phù hợp partition count và downstream capacity không.
- Error handler, retry và DLT đã được cấu hình riêng chưa; baseline không tự tạo DLT.
- Security properties và credentials đã được thêm theo môi trường chưa.
- `ConsumerFactory`/container factory thực tế có dùng đúng cấu hình này không.

## 22. Checklist trước khi merge và deploy

### Cấu hình và contract

- [ ] Bootstrap servers đúng môi trường và advertised listeners truy cập được.
- [ ] Group ID ổn định, không trùng với ứng dụng xử lý độc lập.
- [ ] Offset reset policy được chọn và có test group mới.
- [ ] Key/value deserializer đúng format và event schema.
- [ ] Trusted packages/type headers được giới hạn.
- [ ] Tombstone được xử lý nếu topic compacted.

### Poll, concurrency và commit

- [ ] Auto commit tắt; AckMode được chọn tường minh.
- [ ] `max.poll.interval.ms` phù hợp thời gian xử lý batch p99.
- [ ] `max.poll.records` phù hợp throughput và memory.
- [ ] Fetch size/wait phù hợp latency, payload và heap.
- [ ] Concurrency được so với partition count và downstream capacity.
- [ ] Listener thread-safe khi chạy concurrent.
- [ ] Side effect hoàn tất trước acknowledgment/commit.
- [ ] Consumer chịu được redelivery.

### Error handling và security

- [ ] Exception retryable/non-retryable được phân loại.
- [ ] Retry có giới hạn và backoff rõ.
- [ ] DLT destination, serializer, ACL và retention đã test.
- [ ] Transaction/isolation level đúng failure model.
- [ ] Credential lấy từ secret store và có rotation.
- [ ] ACL chỉ cấp quyền cần thiết cho topic/group.
- [ ] Log không chứa payload hoặc secret.

### Vận hành và kiểm thử

- [ ] Có metric lag, processing duration, commit và rebalance.
- [ ] Có alert cho offset không tiến triển và DLT tăng.
- [ ] Có integration test với broker thật hoặc Testcontainers/Embedded Kafka.
- [ ] Test malformed payload, retry, DLT, rebalance và restart.
- [ ] Test shutdown khi listener đang xử lý.
- [ ] Có runbook reset/replay offset được kiểm soát.

## 23. Kiểm thử cấu hình consumer

Không chỉ test rằng Spring context khởi động. Nên có các bài kiểm thử sau:

1. Consumer join đúng group và nhận record từ topic mong muốn.
2. Group mới áp dụng đúng `auto.offset.reset`.
3. Restart consumer tiếp tục từ committed offset.
4. Listener xử lý xong mới commit theo AckMode.
5. Crash trước commit tạo redelivery và consumer xử lý idempotent.
6. Payload sai format được error handler/DLT xử lý, không làm listener im lặng.
7. Retryable exception được retry theo số lần/backoff; non-retryable đi recovery/DLT.
8. Consumer có `read_committed` không nhận record từ transaction bị abort.
9. Concurrency và partition assignment đúng như dự kiến.
10. Listener xử lý lâu không gây rebalance ngoài policy.
11. ACL sai tạo lỗi authorization rõ ràng; không cần cấp superuser để test.
12. Shutdown/restart không làm mất record chưa commit.

Dùng topic và group riêng cho test để tránh offset của môi trường khác ảnh hưởng. Chờ điều kiện bằng polling có timeout thay vì `Thread.sleep()` cố định. Khi test offset, ghi lại topic-partition và committed offset; không chỉ kiểm tra số record trong listener mock.

## 24. Các lỗi cấu hình thường gặp

**Consumer đọc lại toàn bộ dữ liệu sau mỗi lần restart:** group ID thay đổi hoặc offset chưa được commit; `auto-offset-reset` chỉ áp dụng khi không có offset hợp lệ.

**Consumer không đọc dữ liệu cũ:** group chưa có offset và đang dùng `latest`; xác nhận có cần replay lịch sử hay không trước khi đổi sang `earliest`.

**Listener không được gọi:** kiểm tra assignment, deserialization, security và container lifecycle trước khi sửa business method.

**Consumer rebalance liên tục:** kiểm tra processing time, `max.poll.interval.ms`, heartbeat, network và instance restart.

**Offset không tiến triển:** kiểm tra AckMode, manual acknowledgment, error handler, transaction abort và commit failure.

**Tăng concurrency nhưng throughput không tăng:** kiểm tra partition count, hot key và downstream bottleneck.

**Deserialize JSON lỗi:** kiểm tra producer serializer, target type, type headers, trusted packages và schema compatibility.

**Retry vô hạn:** kiểm tra classifier và backoff; đưa lỗi dữ liệu không thể phục hồi sang DLT.

**DLT publish lỗi:** kiểm tra producer credential/ACL, destination topic, partition count và serializer cho raw bytes.

**Consumer đọc record chưa commit:** kiểm tra `isolation.level`; dùng `read_committed` khi yêu cầu transactional visibility.

**Production log lộ secret:** rà soát SASL config, exception, payload, headers và log level của Kafka client.

## 25. Checklist cuối cùng theo nguyên tắc

Một cấu hình consumer sẵn sàng production cần trả lời được năm câu hỏi:

1. **Đọc từ đâu?** Cluster, topic, group ID, partition assignment và offset reset policy đã rõ.
2. **Đọc thành gì?** Deserializer, schema, type mapping và tombstone behavior đã được kiểm chứng.
3. **Xử lý trong bao lâu?** Poll/fetch, concurrency, downstream timeout và memory budget phù hợp tải.
4. **Khi nào được xem là hoàn tất?** AckMode, commit, transaction và idempotency được thiết kế nhất quán.
5. **Khi có lỗi thì làm gì?** Retry, DLT, security, monitoring và recovery runbook đã được thử nghiệm.

Checklist cấu hình consumer không phải danh sách property cần bật tối đa. Mỗi property phải gắn với một quyết định về dữ liệu, throughput, ordering, latency, failure recovery hoặc bảo mật. Hãy lưu cấu hình có chủ đích, kiểm thử trên broker tương đương production và theo dõi offset/lag sau triển khai để xác nhận consumer thực sự vận hành đúng.

## Tài liệu tham khảo

- [Spring for Apache Kafka – Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html)
- [Spring for Apache Kafka – Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Boot – Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
