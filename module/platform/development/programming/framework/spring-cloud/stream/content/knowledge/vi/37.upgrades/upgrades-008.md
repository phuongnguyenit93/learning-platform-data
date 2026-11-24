# Kiểm thử hồi quy hợp đồng, offset, DLQ và giao dịch khi nâng cấp

Nâng cấp một ứng dụng Spring Cloud Stream có thể thay đổi phiên bản Spring Boot, Spring Cloud Function, Spring Cloud Stream, binder Kafka/RabbitMQ/Pulsar, serializer hoặc code nghiệp vụ. Dù function vẫn chạy và unit test vẫn xanh, hệ thống có thể phát sinh lỗi khi phiên bản mới đọc message cũ, khi consumer tiếp tục từ vị trí đã lưu, khi message lỗi đi vào DLQ hoặc khi một giao dịch đang xử lý bị hủy giữa chừng.

Trong hệ thống xử lý sự kiện, một bản nâng cấp an toàn phải giữ được **hợp đồng dữ liệu**, **tiến trình tiêu thụ message**, **đường xử lý lỗi** và **bảo đảm giao nhận** đã cam kết. Kiểm thử hồi quy là quá trình chứng minh các hành vi đó bằng những tình huống kiểm thử có thể tái lập, bao gồm khi phiên bản cũ và mới cùng chạy và khi phải rollback.

Bài này tập trung vào Spring Cloud Stream theo mô hình `Supplier`/`Function`/`Consumer` với binding và binder. Kafka có offset và giao dịch; RabbitMQ dùng queue/ACK; Pulsar dùng subscription cursor và message acknowledgment. Vì vậy cần một bộ tiêu chí chung nhưng các phép kiểm chứng broker-specific phải tách biệt.

## 1. Bốn lớp hợp đồng cần giữ khi nâng cấp

| Lớp hồi quy | Câu hỏi cần trả lời | Bằng chứng kiểm thử |
|---|---|---|
| Payload và message contract | Consumer mới có đọc được message cũ? Consumer cũ có đọc được message mới trong rolling upgrade? | Test deserialization, schema compatibility, header, key, type và semantic field. |
| Tiến trình tiêu thụ | Consumer có tiếp tục đúng vị trí đã xử lý? Có mất message hoặc xử lý lại không kiểm soát? | Offset/subscription cursor trước và sau restart, rebalance, crash; business idempotency. |
| Retry và DLQ | Message lỗi có retry đúng chính sách và được chuyển đúng nơi sau khi hết lượt thử? | Số lần gọi handler, DLQ count, payload, headers, replay và failure injection. |
| Giao dịch và side effect | Khi lỗi giữa read–process–write, output và vị trí đọc có cùng commit/rollback? | Kiểm tra committed/aborted output, offset, duplicate và outbox/DB behavior. |

Đừng dùng mỗi trạng thái `ApplicationContext starts` hoặc HTTP health check làm tiêu chí thành công. Một ứng dụng đã start có thể vẫn đọc sai schema, đứng chờ offset không tồn tại, bỏ message lỗi hoặc phát output trùng.

~~~mermaid
flowchart LR
    A[Producer v1/v2] --> B[(Input topic/queue)]
    B --> C[Consumer v1/v2]
    C --> D[Output/DB]
    C --> E[Retry / DLQ]
    C --> F[Offset / ACK / Cursor]
    D --> G[Kiểm chứng nghiệp vụ]
    E --> G
    F --> G
~~~

## 2. Chuẩn bị baseline trước khi đổi phiên bản

Trước lần nâng cấp, lưu lại những dữ liệu cần thiết để so sánh:

1. **Version matrix:** Spring Boot, Spring Cloud release train, Spring Cloud Stream, Spring Cloud Function, binder, Kafka/Rabbit/Pulsar client và broker.
2. **Binding map:** `spring.cloud.function.definition`, tên input/output binding, `destination`, `group` và binder cụ thể.
3. **Contract snapshot:** schema hiện tại, content type, key/partition strategy, bắt buộc/optional fields, header và ví dụ raw message.
4. **Consumer progress:** Kafka group offset theo topic/partition; Rabbit queue ready/unacked; Pulsar subscription cursor/backlog.
5. **Error policy:** retry attempts, backoff, cấu hình DLQ/requeue, cách serialize DLQ và công cụ replay.
6. **Transaction policy:** Kafka transaction ID prefix, isolation level của downstream, ACK/commit timing và side effect ngoài Kafka.
7. **Operational baseline:** throughput, lag, redelivery, DLQ rate, duplicate business keys, p95/p99 latency.

Lưu cả thông số đã triển khai thực tế, không chỉ nội dung file cấu hình. Environment variables, profiles, binder defaults và dependency update có thể thay đổi effective configuration dù tên property vẫn giữ nguyên.

Tập dữ liệu kiểm thử nên có ID bất biến, ví dụ `evt-0001` đến `evt-0100`, để đối soát kết quả đầu vào/đầu ra. Với dữ liệu nhạy cảm, dùng fixture giả và không sao chép payload production vào test một cách tùy tiện.

## 3. Ma trận phiên bản cũ/mới

Với một producer P và consumer C, tối thiểu chạy các tổ hợp sau:

| Producer | Consumer | Mục đích |
|---|---|---|
| P1 | C1 | Baseline cũ: xác định hành vi đang được hỗ trợ. |
| P1 | C2 | Consumer mới phải đọc được message cũ và backlog lịch sử. |
| P2 | C2 | Hệ thống mục tiêu sau nâng cấp chạy end-to-end. |
| P2 | C1 | Kiểm chứng consumer cũ có đọc được message mới trong thời gian rolling upgrade hoặc rollback hay không. |

Không phải mọi tổ hợp đều bắt buộc thành công. Nếu hợp đồng mới chỉ có backward compatibility, P2/C1 có thể không được bảo đảm; khi đó phải nâng cấp toàn bộ consumer trước khi producer P2 bắt đầu phát schema mới.

Đặc biệt cần kiểm tra:

- **Mixed deployment:** một số instance C1 và C2 chạy chung consumer group trong thời gian rollout.
- **Restart:** C2 dừng, khởi động lại với cùng group/subscription.
- **Rollback:** đang chạy C2 rồi chuyển về C1, với cả message do P1 và P2 đã phát.
- **Replay:** consumer đọc lại message cũ sau khi offset/cursor được đưa về vị trí trước đó trong môi trường test.

Ma trận phải xét cả phiên bản ứng dụng **và** schema trên broker; một app mới chạy với schema registry, DLQ policy hoặc topic configuration cũ có thể hành xử khác app mới với hạ tầng đã thay đổi.

## 4. Kiểm thử hồi quy hợp đồng payload

Hợp đồng message rộng hơn kiểu Java của function. Với một event `OrderCreated`, cần nêu rõ:

- Event name/type, version và ý nghĩa nghiệp vụ.
- Field name, type, optional/default/nullability, units và các invariant.
- Serialization: JSON, Avro, Protobuf, primitive hoặc byte array.
- Content type của Spring Cloud Stream và Pulsar/native schema nếu được dùng.
- Message key, partition/routing key và yêu cầu ordering.
- Header phục vụ correlation, tracing, idempotency, event time, tenant hoặc content type.
- Cách xử lý unknown fields, unknown enum values và tombstone/null payload.

Ví dụ V1:

~~~json
{
  "eventId": "evt-0001",
  "orderId": "ord-100",
  "amount": 125000
}
~~~

V2 bổ sung field:

~~~json
{
  "eventId": "evt-0001",
  "orderId": "ord-100",
  "amount": 125000,
  "source": "MOBILE"
}
~~~

Nếu `source` là optional và consumer mới có giá trị mặc định hợp lý khi đọc V1, đây có thể là thay đổi tương thích. Nếu V2 đổi `amount` từ số sang chuỗi hoặc từ đơn vị đồng sang xu mà không đổi contract, mã nguồn có thể compile nhưng nghiệp vụ vẫn sai.

### 4.1. Schema compatibility không đồng nghĩa semantic compatibility

Schema Registry có thể kiểm tra kiểu dữ liệu và một số quy tắc evolution, nhưng không biết nghiệp vụ diễn giải `amount`, `status` hay `eventTime` thế nào. Test cần kiểm chứng cả contract kỹ thuật và kết quả nghiệp vụ:

| Thay đổi | Kiểm thử cần có |
|---|---|
| Thêm field optional | V1 → C2 dùng default; P2 → C1 bỏ qua field nếu được hỗ trợ. |
| Đổi tên field | Consumer cũ/new có alias/migration hay không; không tự mặc định tương thích. |
| Thay đổi kiểu dữ liệu | Schema registry chấp nhận hay từ chối; serializer và business logic có xử lý được? |
| Thêm enum value | Consumer cũ có fallback/UNKNOWN hay báo lỗi? |
| Thay đổi ý nghĩa field | So sánh kết quả tính toán, không chỉ deserialize thành công. |
| Thay đổi message key | Có ảnh hưởng partition, ordering, compaction và idempotency không? |
| Thay đổi header | Có làm mất correlation, tracing, routing hoặc content-type không? |
| Tombstone/null value | Consumer mới và cũ có xử lý đúng theo contract của topic không? |

### 4.2. Quy tắc nâng cấp theo compatibility strategy

| Chiến lược | Ý nghĩa giản lược | Thứ tự rollout thường phù hợp |
|---|---|---|
| BACKWARD | Consumer mới đọc được dữ liệu theo schema trước đó. | Consumer trước, producer sau. |
| BACKWARD_TRANSITIVE | Consumer mới đọc được toàn bộ schema lịch sử đã kiểm tra. | Consumer trước, producer sau; phù hợp replay dài hạn. |
| FORWARD | Consumer cũ đọc được dữ liệu do producer mới tạo. | Producer trước, sau đó consumer; phải xem dữ liệu cũ còn tồn tại. |
| FULL/FULL_TRANSITIVE | Tương thích hai chiều theo phạm vi phiên bản được kiểm tra. | Linh hoạt hơn cho rolling upgrade; vẫn phải test semantic contract. |

Luật chính xác phụ thuộc format và registry. Kafka không tự cung cấp Confluent Schema Registry; nếu ứng dụng dùng Avro/Protobuf/JSON Schema registry bên ngoài, phải kiểm tra compatibility ở registry đó. Pulsar có schema registry của broker và chiến lược compatibility riêng. Với JSON dùng Spring message conversion rồi đưa vào `Schema.BYTES` của Pulsar, đừng nhầm content type JSON với schema JSON được broker quản lý.

### 4.3. Fixture hồi quy cho dữ liệu lịch sử

Lưu fixture message như nó đã được phát bởi V1, gồm bytes và metadata cần thiết, rồi kiểm tra bằng V2:

~~~java
@Test
void v2ReaderAcceptsV1Json() throws Exception {
    ObjectMapper objectMapper = new ObjectMapper();
    String historicalJson = """
        {"eventId":"evt-0001","orderId":"ord-100","amount":125000}
        """;

    OrderCreatedV2 event =
        objectMapper.readValue(historicalJson, OrderCreatedV2.class);

    assertThat(event.eventId()).isEqualTo("evt-0001");
    assertThat(event.orderId()).isEqualTo("ord-100");
    assertThat(event.amount()).isEqualTo(125000);
    assertThat(event.source()).isNull();
}

record OrderCreatedV2(
    String eventId, String orderId, long amount, String source
) {}
~~~

Đây chỉ là test JSON conversion và một class contract. Với Avro, Protobuf hoặc Pulsar native schema, phải test bằng serializer/deserializer và schema ID/version thật trên broker/registry. Đối với payload mã hóa bằng key/value serializer, giữ cả key bytes, header và version metadata để phát hiện lỗi tương thích không xuất hiện khi chỉ kiểm tra JSON text.

## 5. Test Binder kiểm tra wiring và function, chưa đủ cho broker semantics

`spring-cloud-stream-test-binder` cung cấp `InputDestination`, `OutputDestination` và `@EnableTestBinder` để test luồng function/binding trong JVM. Đây là lớp kiểm thử nhanh cho một bản nâng cấp Spring Cloud Function/Spring Cloud Stream:

- Function definition và binding name có bị đổi không?
- JSON conversion, headers và routing có đúng?
- Function composition có gọi đúng thứ tự?
- Exception có được ném ra đúng chỗ để binder/container xử lý?

Ví dụ kiểm thử một function text đơn giản:

~~~java
@SpringBootTest(
    classes = WiringRegressionTest.TestApp.class,
    properties = "spring.cloud.function.definition=normalize"
)
class WiringRegressionTest {
    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void bindsFunctionWithExpectedNames() {
        Message<byte[]> request = MessageBuilder
            .withPayload("order-1".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        input.send(request, "normalize-in-0");

        Message<byte[]> result =
            output.receive(1000, "normalize-out-0");
        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("ORDER-1");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApp {
        @Bean
        Function<String, String> normalize() {
            return text -> text.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Không suy ra từ test này rằng Kafka đã commit đúng offset, Rabbit đã ACK/DLQ đúng hoặc Pulsar đã giữ subscription cursor. Những kiểm chứng đó phải chạy với binder và broker thực tế trong integration test.

## 6. Kafka: offset là tiến trình của consumer group

Với Kafka, offset tăng theo partition. Một committed offset đại diện cho vị trí consumer sẽ tiếp tục đọc; thường nó là **offset tiếp theo sau record cuối đã commit**. Ví dụ đã xử lý/commit record offset 0 đến 4 thì vị trí đã lưu thường là 5.

Spring Kafka listener container có các AckMode như `RECORD`, `BATCH` và `MANUAL`. Khi giao dịch Kafka được bật, offset được đưa vào transaction thay vì commit độc lập theo cách bình thường.

Khi nâng cấp, điều quan trọng là giữ ổn định:

- `destination` (Kafka topic) và `group` của binding.
- Serializer/deserializer, key và partitioning strategy.
- AckMode, batch mode, retry/error handler và commit behavior.
- Concurrency, số partition và quy tắc rebalance.
- Consumer authentication/authorization và visibility với transaction.

Nếu đổi `group` ngoài ý muốn, ứng dụng là một consumer group mới. Nó không kế thừa committed offset của group cũ; vị trí bắt đầu phụ thuộc `startOffset`/`auto.offset.reset`. Trong Spring Cloud Stream Kafka binder, group rõ ràng thường bắt đầu từ `earliest` khi không có offset đã commit, còn anonymous group thường bắt đầu từ `latest`. Giá trị mặc định/override cần kiểm tra theo binder version.

### 6.1. Đừng dùng resetOffsets như một bước nâng cấp thông thường

`start-offset` quyết định vị trí khởi đầu khi group chưa có committed offset hoặc offset không còn hợp lệ. `reset-offsets: true` yêu cầu binder reset vị trí theo cấu hình khi binding khởi động. Hai chức năng khác nhau:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: orders-processor
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              start-offset: earliest
              reset-offsets: false
~~~

Đây là cấu hình minh họa giữ group ổn định và không chủ động reset offsets. Không thêm `reset-offsets: true` để “đảm bảo đọc từ đầu” trong production rollout; làm vậy có thể replay lượng lớn dữ liệu, gây duplicate side effects và tăng lag.

Nếu thật sự cần replay, hãy lập kế hoạch riêng: chọn offset/time range, dùng consumer group khác hoặc công cụ quản lý offset, kiểm soát side effects và ghi rõ điểm phục hồi. Không reset offset trong lúc consumer group vẫn hoạt động mà không phối hợp theo quy trình broker.

### 6.2. Kịch bản hồi quy offset

Một test tích hợp với Kafka nên:

1. Tạo topic có nhiều partition, dùng group cố định `orders-upgrade-test`.
2. Publish 100 message có event ID duy nhất và key phân phối được vào các partition.
3. Chạy consumer V1 tới khi đã xử lý/commit một tập message xác định.
4. Ghi committed offsets theo từng partition và số business records đã xử lý.
5. Dừng V1 có kiểm soát, khởi động V2 với **cùng group**.
6. Publish thêm message và đợi V2 xử lý hết.
7. Đối soát union event IDs đã xử lý với tập input expected; không được mất event.
8. Kiểm tra committed offsets không tự nhảy về đầu hoặc cuối ngoài chính sách đã chọn.

Ở **graceful restart**, có thể kỳ vọng ít hoặc không có duplicate tùy commit mode. Ở **crash giữa xử lý và commit**, at-least-once semantics cho phép một số message xuất hiện lại. Test phải kiểm tra idempotency, không khẳng định mọi restart sẽ có zero duplicate.

### 6.3. Kiểm thử rebalance trong mixed deployment

Trong rolling upgrade, C1 và C2 có thể cùng tham gia một consumer group. Kafka phân phối partition giữa các member, nhưng không bảo đảm chúng nhận record theo tỉ lệ số instance. Cần kiểm tra:

- Consumer V1 và V2 xử lý cùng schema và cùng semantic contract.
- Không có partition bị bỏ quên sau rebalance.
- Mọi member có đủ thời gian xử lý trước `max.poll.interval.ms`.
- Khi dừng V1, partition được chuyển sang V2 và lag dần trở về ngưỡng bình thường.
- Không có side effect trùng vượt giới hạn idempotency đã thiết kế.

Nếu đổi `spring.cloud.function.definition`, tên binding hoặc `group` trong refactor, phải so sánh effective binding map trước và sau upgrade. Tên binding đổi có thể làm các cấu hình riêng cho retry, DLQ hoặc offset không còn áp dụng.

## 7. RabbitMQ và Pulsar không dùng Kafka offset

Không đặt cùng một assertion “offset trước/sau” cho mọi binder.

| Broker | Tiến trình nhận | Điều cần kiểm thử khi nâng cấp |
|---|---|---|
| Kafka | Consumer-group committed offset theo topic/partition. | Restart, rebalance, commit/seek, replay và `read_committed`. |
| RabbitMQ | Queue, delivery tag, ACK/NACK, message ready/unacked. | Queue name/binding, ACK sau xử lý, requeue, redelivery và DLX/DLQ. |
| Pulsar | Subscription cursor, message ID, ACK/NACK/redelivery. | Subscription name/type, backlog, ACK timeout, dead-letter policy và cursor. |

### 7.1. RabbitMQ: khởi động lại và ACK

Với Rabbit binder, group ảnh hưởng tới tên queue/durable subscription. Nếu đổi group có thể tạo queue khác, khiến message cũ tiếp tục nằm trong queue trước đó và consumer mới không nhận chúng.

Test nên publish các message có ID cố định, dừng consumer giữa handler trước khi ACK, sau đó khởi động V2 trên cùng queue/group. Xác minh message chưa ACK được giao lại theo cấu hình; message đã ACK không được tiêu thụ lại một cách không mong đợi. Kiểm tra cả ready/unacked count, redelivered flag, retry count và idempotent side effect.

### 7.2. Pulsar: subscription và cursor

Với Pulsar, subscription name và subscription type quyết định cách nhận/ACK và bảo đảm ordering. Thay đổi tên subscription khi nâng cấp có thể khiến consumer sử dụng cursor mới và đọc từ vị trí khác.

Test phải dùng cùng subscription theo kế hoạch rollout, xác minh ACK/NACK và subscription backlog trước/sau restart. Với `Shared` subscription, dead letter policy của Pulsar có thể hoạt động theo ngưỡng redelivery; với `Exclusive`/`Failover` cần xem cơ chế xử lý lỗi của Spring Pulsar vì native DLQ không có cùng khả năng. Không tự suy rằng mọi subscription type có DLQ behavior giống nhau.

## 8. Kiểm thử đường retry và DLQ

Một bản nâng cấp có thể thay đổi số lần retry, loại exception được retry, backoff, cách publish lỗi hoặc việc ACK/commit sau recovery. Kiểm thử phải chứng minh **message lỗi được xử lý hoặc lưu lại để replay**, không chỉ chứng minh function ném exception.

Ma trận tối thiểu:

| Input | Hành vi handler | Kết quả kỳ vọng |
|---|---|---|
| Message hợp lệ | Thành công lần đầu | Output/business side effect đúng một lần; không vào DLQ. |
| Lỗi tạm thời | Thành công sau vài lần thử | Số lần gọi/độ trễ đúng chính sách; không vào DLQ. |
| Poison message | Luôn lỗi | Hết retry thì vào đúng DLQ, giữ dữ liệu/metadata phục vụ điều tra. |
| Deserialization lỗi | Handler chưa chạy được | Đi qua error/deserialization path theo cấu hình, không làm listener chết âm thầm. |
| DLQ broker/topic lỗi | Recovery publish thất bại | Không silently ACK/commit và bỏ message; kiểm tra retry, log và alert. |
| Consumer crash trong retry | Process bị dừng | Message chưa ACK/commit được giao lại theo guarantee. |
| DLQ replay | Sửa nguyên nhân rồi phát lại | Idempotency giữ đúng; không tạo vòng poison message vô hạn. |

Các ca nên assert payload bytes hoặc schema version, event ID, original topic/queue, partition/key khi áp dụng, exception category, retry count và correlation metadata.

### 8.1. Kafka binder: cấu hình DLQ

Ví dụ cho consumer **không bật transactional binder**:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: orders-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlq
~~~

Kafka DLQ yêu cầu consumer group được khai báo; anonymous group không dùng được chức năng này. Khi `enable-dlq` bật, record lỗi sau khi hết retry có thể được chuyển sang dead-letter topic. Mặc định topic DLQ là `error.<destination>.<group>` nếu không đặt `dlq-name`.

Hãy kiểm tra serializer của producer gửi DLQ: có cấu hình sử dụng raw bytes, native payload hoặc POJO sẽ ảnh hưởng kiểu serializer cần dùng. DLQ mặc định thường chọn cùng partition number với original record, vì vậy số partition của DLQ phải phù hợp hoặc phải có partition resolver khác.

Test cùng một poison record bằng V1 và V2 để so sánh số retry, backoff, headers gốc và số record DLQ. Khi nâng cấp Spring Kafka error handler, kiểm tra cả trường hợp exception được xếp loại non-retryable và behavior sau khi recovered.

### 8.2. Rabbit binder: DLX, requeue và republish

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: orders-processor
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

`auto-bind-dlq` cho binder provision DLQ/DLX và routing phù hợp khi được cho phép. `republish-to-dlq` cho binder publish message lỗi kèm metadata exception (chẳng hạn header `x-exception-stacktrace`). `requeue-rejected: false` tránh vòng requeue vô hạn khi lỗi không được xử lý.

Khi nâng cấp, xác minh queue, DLX, routing key, TTL, dead-letter routing, queue arguments và broker policy thực tế. Nếu chuyển từ reject/requeue sang republish, hành vi ACK và headers có thể thay đổi. Message “đã đi DLQ” chưa đủ; test phải đọc được message từ đúng queue và kiểm tra metadata cần thiết.

### 8.3. Pulsar: redelivery và dead-letter policy

Pulsar native DLQ gắn với dead-letter policy của consumer, subscription type và số lần redelivery. Với subscription `Shared`, có thể thiết lập `maxRedeliverCount` cùng DLQ topic; các loại subscription khác cần đối chiếu khả năng hỗ trợ với phiên bản client/Spring Pulsar cụ thể.

Nên tạo test gồm: handler lỗi liên tục, ACK timeout hoặc negative acknowledgment theo cấu hình, chờ đủ lượt redelivery, đọc message từ DLQ, so sánh event ID/schema và xác minh backlog subscription không còn bị chặn. Với partitioned topic, nên đặt tên DLQ topic tường minh để tránh tên mặc định gồm suffix partition gây khó quản lý.

## 9. Kafka transaction: phạm vi bảo đảm chính xác

Spring Cloud Stream Kafka binder hỗ trợ transactional binder. Với processor đọc từ topic và ghi sang topic Kafka, giao dịch có thể kết hợp **records được sản xuất** và **offset của records đã tiêu thụ** trong cùng một commit.

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: orders-tx-instance-a-
~~~

Giá trị `transaction-id-prefix` phải đủ độc nhất cho các instance chạy đồng thời để tránh transaction producer fencing ngoài mong đợi. Trong processor application, listener container bắt đầu transaction; output được gửi trên consumer thread tham gia transaction; khi listener xử lý thành công, offset được gửi vào transaction và commit cùng output.

Khi dùng transactional binder, producer bindings chia sẻ producer factory có cấu hình tại `spring.cloud.stream.kafka.binder.transaction.producer.*`; các thuộc tính producer riêng của Kafka binding có thể bị bỏ qua. Kiểm thử cấu hình hiệu lực, nhất là khi upgrade binder và thay serializer/partitioning.

### 9.1. Atomic read–process–write, không phải mọi side effect

Giả sử input Kafka là `orders.created` và output Kafka là `orders.validated`:

~~~mermaid
sequenceDiagram
    participant K as Kafka input
    participant C as Processor
    participant O as Kafka output
    C->>K: Poll event E1
    C->>C: Begin Kafka transaction
    C->>O: Send validated E1
    C->>C: Stage consumed offset
    alt Success
        C->>C: Commit transaction
        Note over O: Output và offset cùng được commit
    else Exception/abort
        C->>C: Abort transaction
        Note over K,O: Offset không commit; output aborted
    end
~~~

Spring Kafka mô tả Exactly Once Semantics cho **read–process–write giữa các Kafka topic**; phần đọc/xử lý có thể vẫn được gọi lại. Giao dịch Kafka không tự làm cho cập nhật database, HTTP API, gửi email hay RabbitMQ/Pulsar output trở thành một transaction nguyên tử với Kafka.

Nếu processor vừa ghi DB vừa phát Kafka, phải có chiến lược nhất quán như transactional outbox, idempotent consumer hoặc compensation. Synchronize hai transaction managers không tương đương distributed XA atomic commit; một phía có thể commit trước khi phía kia thất bại.

### 9.2. Consumer isolation và kết quả kiểm thử

Khi kiểm tra Kafka transactional output, consumer dùng `isolation.level=read_committed` để bỏ qua record của transaction đã abort. Nếu dùng `read_uncommitted`, phép đếm output có thể bao gồm record chưa/không commit và dẫn đến kết luận sai về exactly-once.

Test nên có:

1. Xử lý E1 thành công: output xuất hiện đúng và consumed offset tiến.
2. Gây exception sau khi gửi output nhưng trước commit: transaction abort; reader `read_committed` không thấy output aborted; offset chưa commit.
3. Cho consumer xử lý lại E1 và thành công: chỉ committed output hợp lệ xuất hiện cho E1.
4. Kill processor giữa transaction: kiểm tra transaction fencing/recovery, không có output nửa vời.
5. Chạy hai instance có prefix riêng: không bị fence lẫn nhau; upgrade/rolling deployment giữ instance uniqueness.

Nếu ứng dụng bật non-blocking retries hoặc error handler riêng, phải kiểm tra chúng có tương thích transaction boundary mà binder tạo hay không.

### 9.3. Retry và DLQ trong transactional binder

Retry/DLQ thông thường ở tầng binder không được thực hiện bên trong transaction chính theo cách non-transactional; nếu gửi DLQ trong một transaction rồi transaction rollback thì record DLQ đó cũng có thể bị rollback. Transactional binder chuyển retry/recovery sang listener container, dùng `DefaultAfterRollbackProcessor` sau rollback.

Test cần xác minh thứ tự:

1. Function ném exception.
2. Transaction output/offset bị abort.
3. After-rollback processor thực hiện retry theo policy.
4. Khi hết retry, recovery gửi DLQ theo cấu hình và xử lý committed offset của record đã recover trong một transaction mới khi được hỗ trợ.

Đừng sao chép một cấu hình `enable-dlq` non-transactional sang transactional binder rồi mặc định kết quả giữ nguyên. Kiểm chứng `txCommitRecovered`, retryability của exception, transaction manager và recoverer trong binder version mục tiêu.

## 10. Bài test lỗi đúng điểm: crash và redelivery

Fault injection có ích hơn việc chỉ ném exception ở đầu handler. Với mỗi event `E42`, thử dừng process tại các điểm:

| Điểm lỗi | Kafka non-transactional | Kafka transactional | Rabbit/Pulsar |
|---|---|---|---|
| Trước business logic | Record có thể được phát lại nếu offset chưa commit. | Transaction abort, không commit offset/output. | Message chưa ACK, được giao lại theo policy. |
| Sau business logic, trước ACK/commit | Side effect ngoài broker có thể lặp. | Kafka output/offset rollback; side effect ngoài Kafka vẫn có thể đã xảy ra. | Side effect có thể lặp sau redelivery. |
| Sau publish output, trước commit | Có thể thấy output trùng sau restart. | Output aborted không visible cho `read_committed`; offset không commit. | ACK và output không tự atomic nếu khác broker/transaction. |
| Sau commit/ACK | Không đọc lại thông thường nếu progress đã được lưu. | Output và offset đã commit. | Message đã ACK thường không bị giao lại trên cùng subscription/queue. |
| Khi publish DLQ thất bại | Cần bảo đảm recovery không âm thầm mất message. | Kiểm tra after-rollback recovery, offset transaction. | Kiểm tra requeue/NACK và alert khi DLQ không khả dụng. |

Kiểm tra kết quả bằng **event ID + trạng thái nghiệp vụ + vị trí broker + output/DLQ**, không chỉ số lần gọi function. Với at-least-once, một event có thể được gọi nhiều lần nhưng business state cuối vẫn đúng nếu idempotency được thiết kế tốt.

## 11. Kafka Streams: kiểm thử stateful upgrade

Nếu ứng dụng Spring Cloud Stream dùng Kafka Streams binder, khi nâng cấp cần thêm các kiểm chứng ngoài offset consumer thường:

- Giữ hoặc thay `application.id` có chủ đích: nó định danh application và liên quan internal topics/consumer group.
- Giữ khả năng đọc state store và changelog đã được phiên bản cũ ghi.
- Không đổi tên state store, key/value serde hoặc topology tùy tiện nếu đang cần restore cùng state.
- Kiểm tra khả năng restore trên clean instance, rebalance và chuyển task khi rolling upgrade.
- Nếu có thay đổi topology/state schema không tương thích, lập kế hoạch versioning/migration/reset phù hợp.

Test nên dựng dữ liệu và state bằng version cũ, tắt instance, chạy version mới với cùng `application.id` rồi xác minh aggregate/window/join output không bị reset hoặc nhân đôi bất ngờ. Với state migration có chủ đích, giữ checkpoint và công cụ rebuild rõ ràng.

Không xóa local state hoặc internal changelog topics như một bước “sửa nhanh” khi upgrade. Hành động đó có thể làm mất state cần thiết hoặc gây replay lớn; chỉ thực hiện trong kế hoạch reset có thể kiểm chứng.

## 12. Thiết kế bộ integration test với broker thật

Sử dụng broker cô lập cho test:

- Kafka broker trong Testcontainers hoặc cluster staging với topic/group riêng.
- RabbitMQ broker với queue/DLX/DLQ riêng.
- Pulsar broker với subscription riêng; schema registry và policy phù hợp.
- Schema Registry riêng nếu kiến trúc Kafka dùng Avro/Protobuf/JSON Schema registry bên ngoài.

Không có một Test Binder in-memory nào mô phỏng đầy đủ cả Kafka transaction, Rabbit queue ACK và Pulsar cursor. Nên tách test context theo binder/driver, không trộn test binder vào cùng classpath của bài test cần broker thật nếu nó có thể được auto-configure thay binder thực.

Các nguyên tắc để test ổn định:

1. Tạo destination và group/subscription với namespace riêng cho mỗi lần chạy.
2. Xóa dữ liệu test hoặc tạo ID mới theo từng run, tránh nhìn thấy message cũ.
3. Đợi condition (poll/await) có timeout; không dùng sleep cố định để đoán broker đã xử lý.
4. Lưu committed offset, queue depth, subscription backlog ở những checkpoint xác định.
5. Thu thập output và DLQ bằng consumer độc lập, so sánh tập event ID.
6. Thử cả graceful shutdown và force kill.
7. Đối soát side effect trong DB bằng unique key/idempotency table.
8. Đảm bảo cleanup/close clients và tài nguyên test sau mỗi run.

Nếu test trực tiếp transaction, reader kiểm tra committed output phải cấu hình `read_committed`. Nếu test DLQ, có thể cần topic DLQ đủ partition, serializer phù hợp và subscription/queue riêng để tránh trộn message của những ca khác nhau.

## 13. Ma trận test tối thiểu cho một bản nâng cấp

| ID | Tình huống | Bằng chứng PASS |
|---|---|---|
| CT-01 | P1 → C2 đọc event V1 lịch sử. | Deserialize và semantic field đúng. |
| CT-02 | P2 → C1 trong mixed rollout nếu contract yêu cầu. | Old consumer đọc an toàn hoặc rollout chặn P2 theo thiết kế. |
| CT-03 | Unknown field/enum/null/tombstone. | Fallback hoặc lỗi theo contract, không silently corrupt data. |
| CT-04 | Key/header/partition routing. | Key và metadata giữ đúng, không phá ordering/idempotency. |
| OF-01 | Graceful restart cùng Kafka group. | Không reset offset; xử lý tiếp backlog còn lại. |
| OF-02 | Crash trước commit/ACK. | Không mất event; duplicate được idempotency xử lý. |
| OF-03 | Mixed C1/C2 và rebalance. | Partition ownership/lag bình thường, không mất event. |
| MQ-01 | Rabbit queue/group giữ nguyên khi nâng cấp. | Ready/unacked/ACK và redelivery đúng. |
| PS-01 | Pulsar subscription/cursor giữ nguyên. | Backlog/ACK/redelivery đúng loại subscription. |
| DL-01 | Transient error sau retry hồi phục. | Đúng số attempt; không vào DLQ. |
| DL-02 | Poison event hết retry. | Message xuất hiện đúng DLQ với metadata. |
| DL-03 | Deserializer lỗi trước function. | Không làm mất message; recovery/error path đúng. |
| DL-04 | DLQ publish lỗi rồi phục hồi. | Không silently ACK/commit và bỏ message. |
| TX-01 | Kafka read–process–write thành công. | Output và offset cùng commit. |
| TX-02 | Throw sau send trước commit. | Không có aborted output cho read_committed, offset chưa commit. |
| TX-03 | Crash và restart transactional instance. | Không có half-committed Kafka transaction; recovery đúng. |
| TX-04 | DB/API side effect cùng Kafka. | Idempotent/outbox/compensation hoạt động khi một phía fail. |
| ST-01 | Kafka Streams state restore. | State/aggregate đúng sau nâng cấp và rebalance. |
| RB-01 | Rollback C2 → C1. | Consumer cũ xử lý được contract được cam kết; progress không bị reset. |

Với mỗi test case, nên lưu cả **input fixture**, **version matrix**, **effective config**, **expected count/IDs**, **actual count/IDs**, **broker checkpoint** và **log/trace**. Điều này giúp phân biệt lỗi code nghiệp vụ với lỗi binder, broker hoặc deployment.

## 14. Canary, shadow consumer và rolling deployment

Khi thử C2 trước toàn bộ traffic, có một số cách triển khai:

### Canary cùng consumer group

Một phần replica chạy C2 cùng group với C1. Broker phân phối partition/message giữa các replica. Ưu điểm là dùng luồng xử lý thật; nhược điểm là không thể mặc định so sánh cùng một message ở C1 và C2 vì mỗi partition chỉ được giao cho một Kafka consumer trong group tại một thời điểm.

### Shadow consumer khác group

C2 thử nghiệm dùng group khác để đọc song song cùng topic. Đây là cách tốt để so sánh contract và latency trên toàn bộ luồng, nhưng nó sẽ đọc message theo start position riêng và có thể gây side effect **lần thứ hai** nếu vẫn bật ghi DB, phát output hoặc gọi API.

Shadow consumer cần:

- Tắt side effect hoặc chuyển output sang destination/DB sandbox.
- Dùng group và ACL riêng.
- Kiểm soát backlog, offset và retention.
- Không đưa dữ liệu shadow vào business metrics hoặc DLQ production một cách không phân biệt.

### Dual producer / staged schema rollout

Nếu phải thay đổi contract, có thể hỗ trợ đồng thời V1/V2 trong thời gian chuyển tiếp hoặc phát hai version vào topic khác nhau theo chiến lược được chọn. Mọi dual write phải có event ID/causal link để đối soát và tránh nhân đôi khi các consumer cùng hoạt động.

Đối với thay đổi bắt buộc thay partition key hoặc semantics, đôi khi cần topic/version mới và kế hoạch migration thay vì chỉ đổi serializer trên cùng topic.

## 15. Rollback cũng là một test contract

Rollback code không tự trả schema, offset, DLQ và Kafka transaction state về trạng thái cũ. Trước khi nâng cấp, cần xác nhận:

1. Phiên bản cũ còn đọc được event mới được producer phát trong thời gian nâng cấp hay không.
2. Nếu không, có cần ngừng producer mới, dùng dual-format hay di chuyển sang topic V2 không.
3. Committed offsets/subscription cursors có cần giữ nguyên để tránh replay hoặc skip.
4. DB schema và side effect có còn tương thích với code cũ.
5. DLQ và retry scheduler có giữ event mà version cũ không hiểu.
6. Kafka transactional ID prefix và producer epoch/fencing có ảnh hưởng rollback khi instance mới và cũ trùng thời gian.
7. Kafka Streams state/changelog có còn đọc được bằng version cũ.

Một rollback drill tốt là: chạy V1 → nâng lên V2 → xử lý một tập event mới → dừng V2 → khởi động V1 trong môi trường test và đối soát contract/progress/business state. Nếu rollback không thể an toàn, phải ghi rõ điểm không thể quay lại và có kế hoạch roll-forward.

## 16. Giám sát sau nâng cấp và điều kiện dừng rollout

Trong rollout, theo dõi:

| Chỉ số | Dấu hiệu bất thường |
|---|---|
| Kafka consumer lag / committed offset | Lag tăng không giảm, offset reset/nhảy bất thường. |
| Rabbit queue ready/unacked | Unacked bị kẹt, redelivery tăng liên tục. |
| Pulsar backlog / ack timeout | Subscription backlog tăng, message bị redeliver nhiều. |
| Deserialization/schema errors | Consumer không đọc được event từ producer khác version. |
| Retry/DLQ rate | Tăng đột biến sau version change. |
| Kafka transaction abort/fencing | Producer instance prefix xung đột hoặc transaction không commit. |
| Output uniqueness | Business event bị phát/lưu trùng bất thường. |
| Processing latency p95/p99 | Poll interval, retry hoặc blocking call gây chậm. |
| Stateful restore duration | Kafka Streams restore quá lâu hoặc state khác baseline. |

Đặt ngưỡng cho phép trước rollout, ví dụ không có deserialization error với fixture chuẩn, không mất event ID, DLQ rate không tăng ngoài mức đã biết, consumer lag trở lại baseline trong cửa sổ quan sát. Nếu vượt ngưỡng, dừng rollout, giữ artifacts và broker checkpoints trước khi tiếp tục.

Trong môi trường transactional, phân biệt metric “send attempted” với “transaction committed”. Một send được gọi không chứng minh record đã visible cho consumer `read_committed`.

## 17. Quy trình thực hành end-to-end

1. **Khóa baseline:** ghi versions, binding map, schemas, offsets/cursors, DLQ policy và transaction config hiện hành.
2. **Tạo fixture:** message V1/V2 hợp lệ, poison message, malformed bytes, unknown enum, tombstone, nhiều key/partition.
3. **Unit + contract tests:** so sánh semantic fields, defaults, nullability, key và headers.
4. **Test Binder:** chứng minh function/binding/composition/serialization ở tầng Spring vận hành đúng.
5. **Broker integration:** chạy Kafka/Rabbit/Pulsar thật cho ACK/offset/cursor, DLQ, redelivery và security.
6. **Fault injection:** lỗi trước/sau business write, trước commit/ACK, trong DLQ publish và khi restart.
7. **Kafka transactions:** kiểm tra read_committed, offset/output atomicity và external side effect protection.
8. **Mixed rollout:** chạy C1/C2 cùng group hoặc shadow group được cô lập, đo lag và output uniqueness.
9. **Rollback drill:** quay về version cũ trên tập message đã đi qua version mới.
10. **Deployment gate:** chỉ cho phép rollout nếu bộ regression và ngưỡng vận hành được thông qua.

### Checklist trước khi đánh dấu nâng cấp thành công

- [ ] V1/V2 schema được kiểm tra theo đúng registry/format và semantic contract.
- [ ] Raw message fixtures cũ vẫn đọc được bởi consumer mới.
- [ ] P2/C1 đã được test hoặc có thứ tự rollout bảo đảm không cần tổ hợp này.
- [ ] Group/destination/binding names thay đổi có chủ đích và đã được đối soát.
- [ ] Kafka committed offsets và rebalance không gây skip message.
- [ ] Rabbit queue/ACK/requeue và Pulsar subscription/cursor không đổi ngoài kế hoạch.
- [ ] Retry, DLQ, deserialization failure và DLQ-publish failure được thử với broker thật.
- [ ] Kafka transactional read–process–write và read_committed được kiểm chứng.
- [ ] Giao dịch Kafka không bị nhầm là transaction nguyên tử với database/API.
- [ ] Kafka Streams changelog/state restore được kiểm tra nếu ứng dụng có stateful topology.
- [ ] Có idempotency và cơ chế phát hiện duplicate business events.
- [ ] Có rollback drill hoặc roll-forward plan đã được kiểm chứng.
- [ ] Dashboard/alert có ngưỡng stop rollout rõ ràng.
- [ ] Test artifacts, version matrix và broker checkpoints được lưu để tái lập.

Kiểm thử hồi quy khi nâng cấp Spring Cloud Stream cần đi xa hơn việc function trả về payload đúng. Contract tests chứng minh dữ liệu cũ/mới tương thích; offset/ACK/cursor tests chứng minh không bỏ quên event; retry/DLQ tests chứng minh lỗi được cô lập; transaction tests chứng minh Kafka output và progress cùng commit hoặc rollback trong đúng phạm vi bảo đảm. Kết hợp các lớp kiểm thử với mixed deployment và rollback drill giúp phát hiện các thay đổi nguy hiểm trước khi chúng làm gián đoạn luồng sự kiện production.

## Tài liệu tham khảo

- [Spring Cloud Stream – Kafka Binder: Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
- [Spring Cloud Stream – Kafka Binder: Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)
- [Spring Cloud Stream – Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream – Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Kafka – Message Listener Containers and Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka – Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Cloud Stream Rabbit Binder – Dead-Letter Queue](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/README.html)
- [Spring Pulsar – Message Consumption and Dead Letter Policy](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Apache Pulsar – Schema Evolution and Compatibility](https://pulsar.apache.org/docs/4.2.x/schema-evolution-compatibility/)
- [Confluent – Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
