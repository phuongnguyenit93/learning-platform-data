# Cấu hình DLQ và xác định phạm vi bảo vệ của từng loại lỗi

Kafka Streams binder có thể đưa record không giải mã được vào dead-letter topic (DLQ), nhưng cơ chế này không tự động bắt mọi exception trong topology. Lỗi xảy ra trước khi record trở thành KStream element, lỗi trong business function, lỗi khi ghi output và lỗi của Kafka Streams runtime nằm ở các ranh giới khác nhau và cần cách xử lý khác nhau.

Điểm quan trọng khi vận hành là xác định **lỗi phát sinh ở bước nào** trước khi cấu hình DLQ. Nếu một payload không thể deserialize thành key/value, deserialization exception handler có thể gửi record lỗi tới DLQ. Nếu code trong map/filter/processor ném exception sau khi record đã vào topology, cần xử lý ở cấp ứng dụng, ví dụ RecordRecoverableProcessor hoặc DltAwareProcessor. Nếu broker từ chối ghi output, cần cơ chế xử lý production exception. Một thuộc tính DLQ không bao phủ cả ba tình huống.

## 1. Đặt DLQ đúng trong vòng đời record

Một record đi qua các giai đoạn cơ bản:

1. Consumer đọc bytes từ input topic.
2. Deserializer hoặc message conversion chuyển key/value thành kiểu dữ liệu mà topology sử dụng.
3. KStream/KTable đưa record vào các processor node.
4. Business logic biến đổi, lọc, join hoặc cập nhật state store.
5. Topology serialize và publish record đầu ra.
6. Kafka Streams quản lý offset, transaction và trạng thái task.

DLQ chỉ hoạt động tại ranh giới có error handler hoặc recovery handler tương ứng.

~~~mermaid
flowchart TD
    A[Đọc bytes từ input topic] --> B{Deserialize / convert thành công?}
    B -->|Không| C[DeserializationExceptionHandler]
    C --> D[logAndFail / logAndContinue / sendToDlq]
    B -->|Có| E[Record đi vào KStream topology]
    E --> F{Business logic thành công?}
    F -->|Không| G[RecordRecoverableProcessor / DltAwareProcessor]
    G --> H[Custom recovery hoặc DLT]
    F -->|Có| I[Serialize và publish output]
    I --> J{Publish thành công?}
    J -->|Không| K[Production exception handling]
    J -->|Có| L[Kafka Streams tiếp tục xử lý]
~~~

| Loại lỗi | Thời điểm | Cơ chế cần xem xét | DLQ của deserialization handler có tự bắt không? |
|---|---|---|---|
| Key/value bytes sai định dạng, không deserialize được | Trước khi vào topology | DeserializationExceptionHandler, có thể chọn sendToDlq | Có |
| Framework message conversion thất bại | Khi chuyển record sang kiểu ứng dụng | DeserializationExceptionHandler của Kafka Streams binder | Có, theo hỗ trợ của binder |
| Validation hoặc business function ném exception | Trong map/filter/processor | RecordRecoverableProcessor, DltAwareProcessor hoặc recovery do ứng dụng viết | Không |
| Output serialization hoặc broker publish thất bại | Khi topology ghi output | ProductionExceptionHandler / cấu hình producer và runtime | Không |
| Stream thread, state store hoặc runtime gặp lỗi | Trong quá trình chạy Kafka Streams | Cấu hình runtime, uncaught exception policy, giám sát và phục hồi ứng dụng | Không |

Vì vậy, không nên bật sendToDlq rồi kết luận rằng mọi lỗi xử lý đã được cách ly. Cần có ma trận lỗi và kiểm thử riêng cho từng giai đoạn.

## 2. Ba lựa chọn deserialization exception handler

Kafka Streams có hai handler nền tảng:

- LogAndContinueExceptionHandler: ghi log lỗi deserialize và bỏ qua record lỗi để tiếp tục đọc record sau.
- LogAndFailExceptionHandler: ghi log và làm quá trình xử lý thất bại. Đây là mặc định của Kafka Streams binder.

Spring Cloud Stream Kafka Streams binder bổ sung lựa chọn sendToDlq để publish các record lỗi deserialize vào một DLQ topic.

| Giá trị | Hành vi | Khi phù hợp |
|---|---|---|
| logAndFail | Ghi log và fail khi gặp record không deserialize được. | Muốn dừng xử lý để điều tra schema hoặc dữ liệu hỏng, tránh âm thầm bỏ record. |
| logAndContinue | Ghi log rồi bỏ qua record lỗi, tiếp tục với record sau. | Chỉ dùng khi bỏ qua record đã được chấp nhận về mặt nghiệp vụ và có cách theo dõi riêng. |
| skipAndContinue | Bỏ qua record lỗi và tiếp tục theo chính sách skip của binder. | Khi cần cấu hình skip cho một input binding cụ thể. |
| sendToDlq | Gửi record lỗi tới dead-letter topic rồi tiếp tục theo cơ chế handler. | Khi cần giữ poison pill để điều tra hoặc sửa rồi phát lại. |

Mặc định ở binder level là logAndFail. Nếu không cấu hình handler, một record không giải mã được có thể khiến processor fail thay vì tự động vào DLQ.

## 3. Bật sendToDlq ở cấp binder

Thuộc tính ở cấp binder áp dụng cho các input binding trong toàn ứng dụng Kafka Streams binder:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
        processOrders-out-0:
          destination: orders.validated
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: sendToDlq
            applicationId: order-validation
~~~

Với cấu hình trên, nếu key hoặc value của record từ input binding không deserialize được, binder gửi record lỗi vào DLQ. Handler này hoạt động với cả native deserialization và message conversion do framework cung cấp.

Không nhầm cấu hình này với thuộc tính enableDlq của regular Kafka message-channel binder. Hai binder có namespace và phạm vi xử lý lỗi khác nhau:

| Regular Kafka binder | Kafka Streams binder |
|---|---|
| Thuộc tính enableDlq trên consumer binding. | Thuộc tính deserializationExceptionHandler. |
| DLQ thường xử lý lỗi trong message listener sau retry. | Handler sendToDlq xử lý lỗi deserialize/message conversion trước khi record vào topology. |
| Cấu hình dưới spring.cloud.stream.kafka.bindings. | Cấu hình dưới spring.cloud.stream.kafka.streams. |
| Có max-attempts của message-channel consumer. | Không dùng max-attempts của regular binder để điều khiển deserialization handler. |

Đưa enableDlq vào nhầm namespace sẽ không bật DLQ cho Kafka Streams binder.

## 4. Chọn DLQ topic bằng dlqName

Có thể đặt tên DLQ cố định cho một input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: sendToDlq
          bindings:
            processOrders-in-0:
              consumer:
                dlqName: orders-events-deserialization-dlq
~~~

Nếu không đặt dlqName và không cung cấp DlqDestinationResolver, binder dùng tên mặc định theo dạng:

~~~text
error.<input-topic-name>.<application-id>
~~~

Ví dụ input topic là orders.events và application ID là order-validation, tên mặc định là error.orders.events.order-validation.

Nên tạo và quản lý DLQ topic rõ ràng bằng hạ tầng (IaC, Kafka administration hoặc quy trình provisioning của nền tảng). Việc tạo topic tường minh giúp kiểm soát partition count, replication factor, retention, ACL và quota thay vì phụ thuộc vào quyền tự tạo topic của ứng dụng.

## 5. Định tuyến động bằng DlqDestinationResolver

Khi một ứng dụng đọc nhiều input topic hoặc cần tách DLQ theo loại dữ liệu, có thể cung cấp bean DlqDestinationResolver. Resolver nhận ConsumerRecord và exception rồi trả về tên topic đích.

~~~java
@Bean
DlqDestinationResolver dlqDestinationResolver() {
    return (record, exception) -> {
        if ("orders.events".equals(record.topic())) {
            return "orders-events-deserialization-dlq";
        }
        if ("customers.events".equals(record.topic())) {
            return "customers-events-deserialization-dlq";
        }
        return "unclassified-deserialization-dlq";
    };
}
~~~

Resolver có thể xem topic, partition, key, headers và exception để chọn đích. Chỉ nên dựa vào metadata đã được kiểm tra; không tạo tên topic trực tiếp từ dữ liệu không tin cậy nếu điều đó có thể làm phát sinh vô hạn topic.

Thứ tự ưu tiên:

1. Nếu có DlqDestinationResolver bean, resolver được ưu tiên.
2. Nếu không có resolver, binder dùng dlqName của input binding nếu được cấu hình.
3. Nếu cả hai đều không có, binder dùng tên mặc định error.<input-topic-name>.<application-id>.

**Lưu ý quan trọng:** khi dùng DlqDestinationResolver, binder không thể tự provision các topic động vì không biết trước toàn bộ tên mà resolver có thể trả về. Ứng dụng hoặc nền tảng phải tạo sẵn mọi DLQ topic có thể được chọn. Nếu thiếu topic hoặc quyền ghi, chính thao tác gửi lỗi vào DLQ cũng có thể thất bại.

## 6. Phạm vi toàn ứng dụng và cấu hình theo từng input binding

deserializationExceptionHandler ở cấp binder áp dụng cho toàn ứng dụng. Nếu ứng dụng có nhiều function hoặc nhiều input, một lựa chọn global có thể không phù hợp với mọi nguồn dữ liệu.

Ví dụ processor nhận hai input: KStream đơn hàng và KTable khách hàng:

~~~java
@Bean
BiFunction<KStream<String, OrderEvent>,
           KTable<String, CustomerProfile>,
           KStream<String, EnrichedOrder>> enrichOrders() {
    return (orders, customers) -> orders
        .leftJoin(customers, EnrichedOrder::from);
}
~~~

Giả sử input orders.events cần giữ record lỗi trong DLQ, còn customer-snapshot là bảng tham chiếu mà tổ chức chấp nhận skip record lỗi theo chính sách đã thống nhất. Có thể cấu hình riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.events
        enrichOrders-in-1:
          destination: customer-snapshot
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                deserializationExceptionHandler: sendToDlq
                dlqName: orders-deserialization-dlq
            enrichOrders-in-1:
              consumer:
                deserializationExceptionHandler: skipAndContinue
~~~

Cấu hình ở consumer binding có độ ưu tiên cao hơn cấu hình binder level. Điều này cho phép một processor có nhiều input áp dụng chính sách lỗi khác nhau cho từng nguồn. Chỉ chọn skipAndContinue nếu đã chấp nhận việc record đó không đi vào topology và có cách đo lường, cảnh báo hoặc đối soát phù hợp.

## 7. Phân vùng của DLQ

Mặc định, binder gửi record lỗi vào cùng số partition với record gốc. Vì vậy, nếu input topic có 12 partition thì DLQ cần ít nhất 12 partition để mọi record lỗi đều có partition đích tương ứng.

Giữ số partition tương ứng hữu ích khi cần truy vết partition nguồn hoặc phục hồi có kiểm soát. Tuy nhiên, DLQ là topic riêng; thứ tự giữa các record lỗi và record còn lại của topic gốc không tạo thành một thứ tự nghiệp vụ toàn cục.

### Tùy chỉnh bằng DlqPartitionFunction

Có thể cung cấp một bean DlqPartitionFunction để chọn partition đích:

~~~java
@Bean
DlqPartitionFunction dlqPartitionFunction() {
    return (group, record, exception) -> 0;
}
~~~

Hàm nhận consumer group (thường trùng application ID trong Kafka Streams), ConsumerRecord lỗi và exception. Ví dụ trên đưa mọi record lỗi vào partition 0. Chỉ có thể có một bean DlqPartitionFunction trong application context; nếu nhiều input binding cần chiến lược khác nhau, hãy dùng một hàm chung có logic phân nhánh theo topic/group.

Nếu consumer binding đặt dlqPartitions bằng 1 và binder minPartitionCount cũng bằng 1, binder có thể dùng partition 0 mà không cần DlqPartitionFunction. Nếu dlqPartitions lớn hơn 1 hoặc minPartitionCount lớn hơn 1, phải cung cấp DlqPartitionFunction, kể cả khi số partition DLQ bằng số partition nguồn.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            processOrders-in-0:
              consumer:
                deserializationExceptionHandler: sendToDlq
                dlqName: orders-deserialization-dlq
                dlqPartitions: 1
~~~

Chỉ dùng cấu hình một partition khi tải, khả năng tiêu thụ DLQ và yêu cầu truy vết cho phép. Một DLQ partition đơn có thể trở thành bottleneck nếu nhiều partition nguồn đồng thời phát sinh lỗi.

## 8. DLQ deserialization không bắt exception trong business logic

Khi record đã được deserialize thành công và đi vào KStream, exception trong map, filter, flatMap, transform hoặc business function không còn là deserialization exception.

Ví dụ:

~~~java
@Bean
Function<KStream<String, OrderEvent>,
         KStream<String, OrderSummary>> processOrders() {
    return input -> input.mapValues(event -> {
        if (event.amount() < 0) {
            throw new IllegalArgumentException("Amount must be non-negative");
        }
        return OrderSummary.from(event);
    });
}
~~~

Nếu amount âm nhưng payload đã deserialize thành OrderEvent thành công, sendToDlq ở deserializationExceptionHandler không tự bắt exception này. Binder không can thiệp trực tiếp vào code nghiệp vụ trong DSL. Cần đưa logic có thể thất bại vào một cơ chế recovery ở cấp record.

Không nên bắt exception rồi trả null một cách tùy tiện. Làm vậy có thể khiến record biến mất khỏi luồng mà không có DLQ, audit hoặc metric. Hãy quyết định rõ record được bỏ qua, phát sang DLT, ghi error event hay làm processor fail.

## 9. DltAwareProcessor để đưa lỗi business logic vào DLT

Kafka Streams binder cung cấp RecordRecoverableProcessor cho xử lý lỗi ở cấp record. DltAwareProcessor là implementation có khả năng publish record lỗi tới một dead-letter topic (DLT).

Ví dụ consumer chỉ có input, xử lý từng record bằng Processor API:

~~~java
@Bean
Consumer<KStream<String, OrderEvent>> processOrders(
        DltPublishingContext dltPublishingContext,
        OrderService orderService) {
    return input -> input.process(() ->
        new DltAwareProcessor<>(
            record -> {
                orderService.validateAndEnrich(record.value());
                return record;
            },
            "orders-processing-dlt",
            dltPublishingContext
        )
    );
}
~~~

DltPublishingContext được Kafka Streams binder tự cấu hình và cung cấp hạ tầng publish. DltAwareProcessor nhận hàm xử lý record, tên DLT và context này. Khi hàm xử lý ném exception, processor gửi record thất bại tới DLT.

Khác biệt quan trọng:

- DeserializationExceptionHandler sendToDlq xử lý record không thể deserialize trước khi vào topology.
- DltAwareProcessor xử lý exception phát sinh trong logic được bọc bên trong processor.
- DltAwareProcessor không tự động bọc mọi map/filter trong topology. Muốn bảo vệ một đoạn logic, phải đưa đoạn logic đó vào processor recoverable.
- Nếu logic bên trong có side effect ngoài Kafka, DLT không rollback side effect đã thực hiện trước khi exception xảy ra.

Tên DLT trong ví dụ là topic cần được provision và cấp quyền ghi phù hợp. Nên tách DLT cho lỗi business logic khỏi DLQ deserialize nếu đội vận hành cần phân loại và redrive khác nhau.

## 10. RecordRecoverableProcessor với recovery do ứng dụng kiểm soát

Nếu không muốn tự động gửi record vào DLT, có thể dùng RecordRecoverableProcessor và cung cấp recoverer riêng. Recoverer nhận record lỗi cùng exception:

~~~java
@Bean
Consumer<KStream<String, OrderEvent>> processOrders(
        OrderService orderService,
        FailureAuditService failureAuditService) {
    return input -> input.process(() ->
        new RecordRecoverableProcessor<>(
            record -> {
                orderService.validateAndEnrich(record.value());
                return record;
            },
            (record, exception) -> {
                failureAuditService.record(
                    record.key(),
                    record.value(),
                    exception.getClass().getSimpleName(),
                    exception.getMessage()
                );
            }
        )
    );
}
~~~

Recoverer là BiConsumer nhận record và exception. Ứng dụng có thể ghi audit, gửi error event, tăng metric hoặc áp dụng quy tắc nghiệp vụ khác. Mặc định RecordRecoverableProcessor chỉ log lỗi và để ứng dụng tiếp tục; nếu cần giữ record bền vững, phải triển khai recoverer có lưu trữ hoặc publish thực sự.

Nếu recoverer cũng thất bại, lỗi đó phải được xử lý theo chính sách riêng. Không coi việc gọi một logger là bảo đảm message đã được lưu bền vững.

## 11. DltAwareProcessor và serializer của record key

DltAwareProcessor sử dụng StreamBridge, tức đường publish qua regular Kafka binder. Payload value được Spring Cloud Stream chuyển thành byte[]; key được chuyển qua message header và không tự động chuyển thành byte[] theo cùng cách.

Vì vậy, nếu key không phải byte[] (ví dụ String), cần cấu hình key serializer cho DLT destination:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-processing-dlt:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Trong ví dụ, orders-processing-dlt là tên destination DLT đã truyền cho DltAwareProcessor. Nếu dùng key Long, UUID hoặc kiểu tùy chỉnh, chọn serializer tương ứng. Không cấu hình serializer đúng có thể gây ClassCastException hoặc lỗi serialize khi publish record lỗi; lúc đó chính việc gửi DLT lại thất bại.

Đây là cấu hình của regular Kafka binder dùng bởi StreamBridge, không phải deserializationExceptionHandler của Kafka Streams binder. Cần kiểm tra đúng namespace khi cấu hình key serializer.

## 12. Lỗi khi publish output là production exception

Nếu business function xử lý thành công nhưng Kafka producer không thể ghi output, đó là production exception. Kafka Streams binder không cung cấp cùng cơ chế first-class DLQ như deserialization handler cho loại lỗi này.

Có thể tùy chỉnh production exception handler thông qua StreamsBuilderFactoryBean customizer và cơ chế Kafka Streams tương ứng. Hướng xử lý phải xem xét:

- Lỗi tạm thời do broker mất kết nối hoặc timeout.
- Lỗi không thể phục hồi như authorization failure hoặc topic không tồn tại.
- Producer retry và delivery timeout.
- Transaction/processing guarantee đang sử dụng.
- Chính sách fail, retry hoặc tiếp tục của ứng dụng.

Không gửi input record vào DLQ chỉ vì output publish lỗi mà không kiểm tra trạng thái commit. Nếu processor tiếp tục và offset tiến trong khi output chưa được ghi, có thể mất kết quả nghiệp vụ. Với lỗi production quan trọng, thường cần fail/retry theo cơ chế producer/runtime để không xác nhận tiến độ khi output chưa được bảo đảm.

## 13. Retry, DLQ và replay có mục tiêu khác nhau

DLQ không phải retry queue tự động. Khi record được gửi vào DLQ, Kafka Streams không tự đọc lại nó sau một khoảng chờ. Cần có consumer hoặc quy trình redrive riêng.

| Cơ chế | Mục tiêu | Khi sử dụng |
|---|---|---|
| Retry tại processor | Thử lại thao tác có khả năng thành công sau lỗi tạm thời. | Timeout phụ thuộc ngoài, lỗi mạng ngắn hạn. |
| DLQ/DLT | Cách ly record không thể xử lý trong luồng hiện tại. | Payload sai schema, dữ liệu vi phạm điều kiện, lỗi cần điều tra. |
| Replay từ input topic | Xử lý lại một phạm vi dữ liệu từ nguồn gốc. | Sửa logic rồi rebuild projection hoặc phục hồi một khoảng offset. |
| Parking-lot topic | Giữ record cần người vận hành quyết định. | Lỗi nghiệp vụ hoặc dữ liệu cần can thiệp thủ công. |

Với Kafka Streams, không nên giả định thuộc tính max-attempts của regular Kafka binder điều khiển retry cho các phép toán trong topology. Nếu cần retry cho business logic, thiết kế retry ở processor hoặc một topology retry topic riêng, có backoff, giới hạn số lần và trạng thái rõ ràng.

Khi redrive, giữ event ID gốc, bổ sung metadata lần phát lại và bảo đảm consumer idempotent. Nếu xử lý lại một record đã tạo tác dụng ngoài Kafka, cần kiểm tra idempotency key để không gửi email, tạo thanh toán hoặc cập nhật database hai lần.

## 14. Metadata và thông tin cần giữ trong DLQ

Khi điều tra record lỗi, tối thiểu cần xác định:

- Topic, partition và offset nguồn.
- Key và raw value gốc nếu có thể giữ an toàn.
- Application ID hoặc consumer binding gây lỗi.
- Exception type và message.
- Thời điểm phát hiện lỗi.
- Schema version hoặc content type nếu có.
- Event ID/correlation ID nếu record chứa các trường đó.
- DLQ destination và thời điểm gửi.

Với lỗi deserialize, record có thể không tạo được object Java. Do đó, công cụ điều tra cần đọc raw bytes hoặc metadata exception thay vì giả định value luôn là POJO. Không chuyển đổi rồi ghi đè payload gốc nếu cần khả năng replay chính xác.

Với lỗi business logic được xử lý bởi DltAwareProcessor, record đã có kiểu dữ liệu Java. Hãy bảo đảm DLT serializer có thể ghi lại payload và key theo schema tương ứng.

Không ghi secret, token hoặc dữ liệu cá nhân nhạy cảm vào exception message/log nếu không cần thiết. DLQ cần ACL, retention và quy trình xóa dữ liệu phù hợp với chính sách bảo mật.

## 15. Kiểm thử từng phạm vi lỗi

TopologyTestDriver hữu ích để kiểm thử business transformations, nhưng không thay thế integration test cho deserializer, Kafka broker, topic provisioning hoặc publish DLT. Cần kiểm thử với broker thật hoặc Testcontainers Kafka cho các cơ chế DLQ.

| Kịch bản | Cách tạo lỗi | Kết quả cần xác minh |
|---|---|---|
| Key deserialize thất bại | Gửi key bytes không đúng format. | Handler logAndFail, logAndContinue hoặc sendToDlq hoạt động đúng. |
| Value deserialize thất bại | Gửi payload sai schema/format. | Raw record được chuyển vào DLQ nếu chọn sendToDlq. |
| Framework message conversion lỗi | Gửi payload không chuyển được sang kiểu binding. | Handler của Kafka Streams binder xử lý theo cấu hình. |
| Một input trong processor nhiều input lỗi | Làm hỏng record của input thứ nhất hoặc thứ hai. | Per-binding handler áp dụng đúng input. |
| Resolver trả topic khác nhau | Gửi poison pill từ nhiều source topic. | Record đi đúng DLQ và mọi topic đích đã được tạo trước. |
| DLQ partitioning | Gửi lỗi từ nhiều partition nguồn. | Partition DLQ đúng, topic có đủ partition. |
| Business function ném exception | Ném exception trong logic bọc bởi DltAwareProcessor. | Record được gửi tới DLT, input key/value đúng. |
| Custom recoverer | Dùng RecordRecoverableProcessor. | Recoverer nhận đúng record và exception; audit được lưu. |
| Key DLT là String | Publish record lỗi có key String. | Key serializer đúng và không có ClassCastException. |
| Output publish thất bại | Thu hồi quyền ghi hoặc dừng broker output trong test. | Production exception được xử lý; không nhầm với deserialization DLQ. |
| DLT không tồn tại/thiếu ACL | Không tạo topic hoặc thu hồi quyền ghi. | Lỗi gửi DLT được phát hiện và cảnh báo; không giả định record đã được cách ly. |
| Replay record đã xử lý | Redrive cùng event ID. | Consumer idempotent không tạo tác dụng nghiệp vụ trùng. |

Nên xác minh cả nội dung topic DLQ/DLT, key, partition, raw payload, exception context, offset input và trạng thái processor. Chỉ kiểm tra log có dòng lỗi là chưa đủ.

## 16. Quan sát và vận hành DLQ

Các metric và cảnh báo nên có:

- Số record lỗi deserialize theo input binding, topic và exception category.
- Số record được gửi vào từng DLQ/DLT.
- Tuổi của record cũ nhất trong DLQ.
- Số lần gửi DLT thất bại.
- Tỷ lệ lỗi theo schema version hoặc event type.
- Consumer lag và trạng thái Kafka Streams processor.
- Số lần stream thread restart hoặc application fail.
- Số record được redrive, replay và đưa vào parking lot.
- Thời gian từ lúc phát hiện lỗi tới khi phục hồi xong.

Log nên có topic, partition, offset, application ID, binding, event ID và exception type. Dùng metric label có cardinality thấp; không đưa toàn bộ event ID hoặc exception message tự do thành metric tag.

DLQ phải có owner, retention, ACL, cảnh báo và runbook. Nếu không có người chịu trách nhiệm xử lý, DLQ chỉ chuyển lỗi khỏi luồng chính và tạo một backlog khó kiểm soát.

## 17. Lỗi cấu hình thường gặp

1. Dùng enableDlq của regular Kafka binder cho Kafka Streams binder. Hai namespace và phạm vi lỗi khác nhau.
2. Nghĩ sendToDlq bắt exception trong map/filter. Handler này dành cho deserialization/message conversion errors.
3. Không khai báo application ID ổn định. Tên DLQ mặc định dùng application ID; thay ID có thể tạo DLQ khác.
4. Dùng DlqDestinationResolver nhưng quên provision các topic mà resolver trả về.
5. DLQ có ít partition hơn input topic trong khi binder gửi cùng số partition nguồn.
6. Đặt dlqPartitions lớn hơn 1 nhưng không cung cấp DlqPartitionFunction.
7. Cấu hình handler ở binder level rồi vô tình áp dụng cho mọi input binding.
8. Bật skipAndContinue mà không có metric hoặc đối soát cho record bị bỏ qua.
9. Dùng DltAwareProcessor nhưng không cấu hình key serializer cho key không phải byte[].
10. Nghĩ DltAwareProcessor tự bọc mọi operator trong topology. Chỉ logic được đưa vào processor recoverable mới được bảo vệ.
11. Không phân biệt lỗi gửi output với lỗi deserialize. Production exception cần cơ chế riêng.
12. Xem DLQ là retry queue và để record nằm đó mà không có quy trình redrive.
13. Không kiểm thử tình huống gửi DLQ thất bại do topic, ACL hoặc serializer.

## 18. Quy trình thiết kế DLQ cho Kafka Streams

1. Liệt kê input binding, topic, application ID và kiểu key/value.
2. Phân loại lỗi deserialize, conversion, business logic, output production và runtime.
3. Chọn logAndFail, logAndContinue, skipAndContinue hoặc sendToDlq cho từng input phù hợp.
4. Dùng binder-level handler khi mọi input có cùng chính sách; dùng consumer-level handler khi cần khác biệt theo binding.
5. Đặt dlqName hoặc DlqDestinationResolver; provision mọi topic đích và ACL trước khi chạy.
6. Thiết kế số partition DLQ và DlqPartitionFunction theo số partition nguồn/tải dự kiến.
7. Với lỗi business logic, bọc phần xử lý có thể thất bại trong RecordRecoverableProcessor hoặc DltAwareProcessor.
8. Nếu dùng DltAwareProcessor, cấu hình serializer cho record key và xác minh đường publish của StreamBridge.
9. Cấu hình production exception handling riêng cho lỗi publish output.
10. Xác định retry, redrive, replay, parking lot và idempotency.
11. Integration test lỗi ở từng ranh giới và kiểm tra cả offset lẫn nội dung DLQ.
12. Thiết lập metric, alert, owner, retention và runbook xử lý lỗi.

DLQ có giá trị khi nó bảo vệ đúng ranh giới lỗi và giữ đủ thông tin để phục hồi. Trong Kafka Streams binder, sendToDlq xử lý poison pill ở bước deserialize; RecordRecoverableProcessor/DltAwareProcessor xử lý lỗi business logic ở cấp record; production exception handler xử lý lỗi ghi output. Phân chia rõ ba phạm vi này giúp tránh bỏ sót record, tránh kỳ vọng sai vào cấu hình và tạo quy trình phục hồi có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 – Kafka Streams Binder: Error Handling](https://docs.spring.io/spring-cloud-stream/reference/5.1/kafka/kafka-streams-binder/error-handling.html)
- [Spring Cloud Stream – Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream – Kafka Streams Binder Functional Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/functional.html)
- [Apache Kafka Streams – Deserialization Exception Handling](https://kafka.apache.org/documentation/streams/developer-guide/config-streams/)
- [Spring for Apache Kafka – Kafka Streams Support](https://docs.spring.io/spring-kafka/reference/streams.html)
