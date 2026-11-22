# DeadLetterPublishingRecoverer cho retry topic

Trong Spring Kafka, **non-blocking retry** đưa một record lỗi từ topic chính sang một hoặc nhiều retry topic để thử xử lý sau thời gian chờ đã định. Khi record đã dùng hết số lần thử mà vẫn thất bại, hệ thống có thể chuyển record sang **dead-letter topic (DLT)**. `DeadLetterPublishingRecoverer` là thành phần quan trọng của luồng này: nó tạo và publish record đến topic tiếp theo khi listener thất bại và một bước chuyển tiếp được yêu cầu.

Tên `DeadLetterPublishingRecoverer` dễ khiến người học nghĩ thành phần này chỉ gửi record vào DLT. Thực tế, trong cơ chế retry topic, Spring Kafka sử dụng recoverer cùng bộ phân giải destination để chuyển record qua **retry topic hoặc DLT**, tùy lần giao, exception, chính sách retry và trạng thái của record. Phần tính toán thời điểm retry, tạo endpoint retry và quyết định lộ trình thuộc hạ tầng retry-topic của Spring Kafka; recoverer thực hiện bước publish tương ứng.

## 1. Vị trí của recoverer trong luồng non-blocking retry

Giả sử consumer đọc sự kiện `OrderCreated` từ topic `orders`. Hệ thống cho phép tổng cộng bốn attempt, gồm lần đầu ở topic chính và ba lần tại các retry topic.

```text
               orders (topic chính)
                       |
                   listener
                       |
                     lỗi
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
              orders-retry (mốc 1)
                       |
                 listener retry
                       |
                     lỗi
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
              orders-retry (mốc 2)
                       |
                 listener retry
                       |
                     lỗi
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
              orders-retry (mốc 3)
                       |
                 listener retry
                       |
                 tiếp tục lỗi
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
                   orders-dlt
```

Sơ đồ thể hiện **các bước logic**, không bảo đảm tên retry topic thực tế. Spring Kafka có thể tạo topic với hậu tố theo thời gian chờ, theo chỉ số attempt hoặc tái sử dụng một topic tùy chính sách `SameIntervalTopicReuseStrategy` và cấu hình phiên bản. Hãy xem topic thực tế khi vận hành.

Khi một bước xử lý thành công, record không cần được chuyển sang destination tiếp theo. Khi bước xử lý thất bại, hạ tầng retry topic quyết định destination rồi gọi recoverer publish. Sau khi việc chuyển giao được xem là thành công theo cấu hình, consumer ở topic nguồn có thể hoàn tất tiến độ của record nguồn; một consumer khác sẽ đọc record đã publish ở topic đích.

## 2. Phân biệt hai cách dùng DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` cũng thường được dùng trực tiếp với `DefaultErrorHandler` cho blocking retry:

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultErrorHandler errorHandler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
);
```

Trong trường hợp trên, handler retry tại chỗ theo `FixedBackOff`; khi hết retry, recoverer gửi record đến destination mà nó xác định, thường là DLT. Đây là cấu hình cho **blocking retry** của container.

Trong non-blocking retry qua `@RetryableTopic`, Spring Kafka tạo hạ tầng forwarding và recoverer tương ứng. Destination thay đổi theo lần thử và chính sách retry-topic. Bạn thường không cần tự tạo một `DefaultErrorHandler` chứa `DeadLetterPublishingRecoverer` để kích hoạt luồng này.

| Nội dung | Blocking retry với `DefaultErrorHandler` | Non-blocking retry với retry topic |
|---|---|---|
| Record được thử lại ở đâu? | Trong luồng xử lý consumer của topic hiện tại. | Ở consumer của một retry topic sau khi record được publish tới đó. |
| Ai quyết định thời gian chờ? | `BackOff` của error handler, ví dụ `FixedBackOff`. | Cấu hình retry-topic và lịch xử lý record của retry consumer. |
| Recoverer publish khi nào? | Thường sau khi blocking retry cạn và cần recovery. | Khi cần chuyển record đến retry topic kế tiếp hoặc DLT. |
| Khi nào DLT nhận record? | Theo chính sách recovery của handler. | Khi attempt đã hết, exception không retry hoặc bộ phân giải chọn DLT. |
| Ảnh hưởng thứ tự? | Có thể giữ partition chờ record lỗi. | Record khác có thể tiếp tục, nên thứ tự nghiệp vụ có thể thay đổi. |

Chọn cơ chế phù hợp với thời gian chờ và yêu cầu thứ tự xử lý. Việc dùng `@RetryableTopic` không đồng nghĩa bạn đã cấu hình blocking retry bổ sung; hai tầng có thể được phối hợp ở phiên bản hỗ trợ, nhưng phải tính riêng số attempt và chính sách lỗi của từng tầng.

## 3. Ví dụ @RetryableTopic và luồng chuyển tiếp

Một listener khai báo retry topic bằng annotation:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    kafkaTemplate = "retryKafkaTemplate",
    autoCreateTopics = "false"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Với cấu hình này, tổng số lần xử lý tối đa theo retry-topic là bốn: một attempt ở `orders` và tối đa ba attempt bổ sung. Các khoảng chờ dự kiến lần lượt được tạo từ giá trị 1.000 ms và multiplier 2.0. Thời gian giao thực tế phụ thuộc scheduler, mức tải và hoạt động poll của consumer.

`autoCreateTopics = "false"` có nghĩa các topic chính, retry và DLT phải được tạo sẵn theo tên, số partition và chính sách bảo lưu đã xác định. Nếu muốn framework tự tạo topic, phải cấu hình quyền và các thuộc tính tương ứng; điều đó không thay thế việc quản trị topic ở môi trường production.

Trong ví dụ trên, bean `retryKafkaTemplate` là producer template dùng để forward record. Producer cần serializer tương thích với key, value và các loại payload có thể phải chuyển sang retry/DLT. Nếu đã dùng template mặc định phù hợp, có thể trỏ `kafkaTemplate` đến tên bean đó thay vì tạo thêm template.

Ví dụ một bean `KafkaTemplate` dùng producer factory đã có trong ứng dụng:

```java
@Bean("retryKafkaTemplate")
KafkaTemplate<Object, Object> retryKafkaTemplate(
        ProducerFactory<Object, Object> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Producer factory ở đây cần được ứng dụng định nghĩa hoặc Spring Boot cung cấp và có cấu hình serializer phù hợp. Trong ví dụ thực tế, nếu chỉ nhận và phát lại một kiểu payload thì generic có thể cụ thể hơn; khi cần xử lý deserialization failure, value gửi DLT đôi khi là `byte[]`, cần chọn serializer có khả năng xử lý loại này.

## 4. Ai quyết định record đi retry topic nào?

Không nên hard-code destination trong callback nghiệp vụ. Hạ tầng non-blocking retry quản lý việc định tuyến qua các cấu phần của Spring Kafka, trong đó có `DestinationTopicResolver` và factory tạo `DeadLetterPublishingRecoverer`. Quyết định destination phụ thuộc vào:

- Topic nguồn mà record đang được xử lý.
- Thông tin attempt và thời điểm retry được lưu cùng record.
- Số lần thử tối đa, backoff và cấu hình tái sử dụng retry topic.
- Loại exception có thể retry hoặc phải chuyển thẳng đến DLT.
- Chính sách có tạo DLT hay không và cách xử lý lỗi trong DLT.

Khi một record lỗi tại topic chính, recoverer được cấu hình bởi retry-topic infrastructure sẽ publish record tới topic retry thích hợp. Khi retry consumer xử lý lỗi lần nữa, cùng cơ chế chuyển record sang destination tiếp theo. Sau lần cuối cùng, destination thường là DLT.

Nếu exception được phân loại là không retry, record có thể đi thẳng đến DLT sau lần lỗi đầu tiên. Vì vậy, `attempts = "4"` là giới hạn trên của một chuỗi retry được phép, không phải cam kết mọi record lỗi đều phải trải qua bốn lần listener invocation.

## 5. Retry metadata và header được giữ như thế nào?

Record chuyển từ topic này sang topic khác cần giữ đủ metadata để hạ tầng retry biết khi nào được thử tiếp và để đội vận hành truy vết về record ban đầu. `DeadLetterPublishingRecoverer` có khả năng thêm các header liên quan đến exception và record nguồn; hạ tầng retry-topic cũng quản lý các header đặc thù cho attempt và timestamp.

Những thông tin thường hữu ích gồm:

| Nhóm thông tin | Mục đích |
|---|---|
| Topic, partition, offset ban đầu | Tìm record gốc khi điều tra và đối chiếu committed offset. |
| Exception class, message, stack trace | Hiểu vì sao listener thất bại và record bị chuyển đi. |
| Attempt / retry timestamp | Xác định số lần thử và thời điểm record đến hạn xử lý lại. |
| Key và correlation/event ID | Ghép các lần giao với cùng một nghiệp vụ. |
| Custom headers | Giữ dữ liệu phục vụ trace, tenant hoặc định tuyến nghiệp vụ nếu được phép. |

Với record đã vào DLT, có thể đọc các header chuẩn như `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN` và `KafkaHeaders.DLT_EXCEPTION_MESSAGE` khi chúng được hạ tầng cung cấp. Header cụ thể, việc lưu header gốc hay header gần nhất, và số header lặp phụ thuộc phiên bản Spring Kafka cùng cấu hình recoverer.

Không nên giả định offset của record tại retry topic bằng offset trên topic chính. Mỗi topic-partition có dãy offset riêng. Một event đã di chuyển qua ba topic có thể có ba offset khác nhau. Để truy vết xuyên các lần publish, nên dùng event ID bền vững trong payload hoặc header, kết hợp metadata record gốc.

Header exception và stack trace có thể khá lớn; khi record qua nhiều lượt retry, cần kiểm soát việc tích lũy header để tránh tăng kích thước message ngoài ý muốn. Cần chú ý cả chính sách bảo vệ dữ liệu nhạy cảm trước khi ghi exception message hoặc stack trace vào DLT.

## 6. Cấu hình DLT handler cho retry topic

Sau khi retry cạn, record được publish đến DLT để một listener chuyên biệt xử lý. Có thể khai báo `@DltHandler` bên cạnh listener có `@RetryableTopic`:

```java
@DltHandler
public void onDeadLetter(ConsumerRecord<String, OrderCreated> record) {
    log.error(
        "Order sent to DLT: topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    incidentService.recordFailure(record.key(), record.value());
}
```

`@DltHandler` xử lý record **sau khi** đã được publish vào DLT. Nó không thực hiện publish tới DLT và cũng không phải cùng một callback với `DeadLetterPublishingRecoverer`. Nếu ứng dụng cần lưu sự kiện lỗi vào database, logic trong DLT handler phải idempotent vì bản thân DLT consumer có thể được giao record lại.

Khi không cung cấp DLT handler, Spring Kafka có các hành vi mặc định theo cơ chế retry-topic và chiến lược DLT được cấu hình. Đừng mặc định suy ra record đã được kiểm tra hoặc có người xử lý chỉ vì nó đã vào DLT. Trong production, cần có consumer hoặc quy trình quản lý DLT, thông báo và hướng dẫn replay.

Ví dụ DLT chứa payload không deserialize được cần listener và serializer/deserializer phù hợp. Không nên ép mọi DLT record về kiểu `OrderCreated` nếu có khả năng DLT nhận dữ liệu lỗi từ bước deserialization.

## 7. Tùy biến DeadLetterPublishingRecoverer do retry-topic tạo

Khi sử dụng `@RetryableTopic`, hạ tầng retry-topic có thể tạo recoverer và error handler cần thiết. Nếu cần thay đổi hành vi chung của recoverer, chẳng hạn xác nhận kết quả publish, bổ sung header hoặc đặt timeout, Spring Kafka cung cấp điểm mở rộng của `RetryTopicConfigurationSupport` trong các phiên bản hỗ trợ.

Ví dụ minh họa cách tùy biến recoverer:

```java
@Configuration
public class RetryTopicInfrastructure extends RetryTopicConfigurationSupport {

    @Override
    protected void configureCustomizers(CustomizersConfigurer customizers) {
        customizers.customizeDeadLetterPublishingRecoverer(recoverer -> {
            recoverer.setFailIfSendResultIsError(true);
            recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));
        });
    }
}
```

Trong cấu hình này, nếu phương thức và callback được hỗ trợ bởi phiên bản Spring Kafka đang chạy, recoverer được yêu cầu phát hiện lỗi gửi trả về từ producer future và giới hạn thời gian chờ kết quả. Điều này đặc biệt quan trọng vì việc publish sang retry/DLT là ranh giới chuyển giao tiến độ giữa hai topic.

`RetryTopicConfigurationSupport` là cấu hình hạ tầng; không tạo nhiều subclass và không kết hợp nó với cách kích hoạt `@EnableKafkaRetryTopic` nếu phiên bản đang dùng quy định chỉ chọn một cách cấu hình. Đối chiếu chữ ký `configureCustomizers`, `setFailIfSendResultIsError` và `setWaitForSendResultTimeout` với API của phiên bản dự án trước khi áp dụng ví dụ.

Không nên thay bộ phân giải destination chuẩn bằng logic tự viết chỉ để đổi hậu tố tên topic. Tên retry/DLT, backoff, attempts và exception classification đã có các thuộc tính cấu hình ở `@RetryableTopic` hoặc `RetryTopicConfigurationBuilder`. Chỉ tùy biến recoverer khi cần thay đổi cách publish hoặc metadata ở mức không được hỗ trợ bởi các cấu hình đó.

## 8. Tại sao lỗi publish phải được xử lý cẩn thận?

Điểm nguy hiểm trong luồng retry-topic là record có thể đã thất bại ở topic nguồn nhưng lại **không được publish thành công** sang topic kế tiếp. Nếu container vẫn ghi nhận record nguồn đã được phục hồi và commit offset nguồn quá sớm, record có nguy cơ biến mất khỏi luồng xử lý nghiệp vụ.

Xét tình huống:

1. Listener đọc event tại `orders-0`, offset `100`, rồi ném exception.
2. Recoverer chuẩn bị gửi event sang retry topic.
3. Producer gặp lỗi broker hoặc lỗi xác thực, nên publish thất bại.
4. Nếu lỗi publish bị bỏ qua, consumer nguồn có thể tiến offset qua `100` mà không có bản sao event trong retry topic.

Vì thế, cần bảo đảm lỗi gửi được phát hiện và truyền thành lỗi recovery khi cần thiết. Những biện pháp liên quan gồm cấu hình producer với `acks=all`, idempotent producer phù hợp, retries/request timeout hợp lý, và cơ chế chờ/kiểm tra kết quả publish của recoverer. Đồng thời theo dõi log publish failure, retry/DLT publish latency và committed offset của topic nguồn.

Việc recoverer báo publish thành công không tự tạo một giao dịch nguyên tử giữa commit offset topic nguồn và publish sang topic đích trong mọi cấu hình. Non-blocking retry cũng không tự mang lại exactly-once semantics cho các hiệu ứng bên ngoài như ghi database hoặc gọi API thanh toán. Cần thiết kế idempotency và phân tích điểm crash giữa publish, acknowledgment và commit.

## 9. Phân biệt lỗi listener, lỗi publish và lỗi DLT handler

Ba loại lỗi xuất hiện ở ba giai đoạn khác nhau:

| Loại lỗi | Xảy ra ở đâu? | Ý nghĩa vận hành |
|---|---|---|
| Listener failure | Listener ở topic chính hoặc retry topic ném exception. | Framework cần chọn retry topic tiếp theo, DLT hoặc bỏ qua retry theo classifier. |
| Recoverer publishing failure | Gửi record đến retry topic hoặc DLT thất bại. | Chưa thể coi bước chuyển giao record thành công; phải có chính sách xử lý recovery failure. |
| DLT handler failure | Listener tiêu thụ DLT ném exception. | Record đã vào DLT nhưng bước xử lý DLT chưa hoàn tất; hành vi thử lại tùy `DltStrategy` và cấu hình. |

Không gom mọi lỗi thành một metric `listener_error`. Nên có metric riêng cho lỗi xử lý ban đầu, số lần retry, lỗi publish retry, lỗi publish DLT, lỗi của DLT consumer và độ dài hàng đợi ở từng retry topic.

Nếu DLT handler thất bại, chiến lược xử lý lỗi DLT có thể cho phép thử lại, dừng retry hoặc không tạo DLT tùy cấu hình. Vì retry topic có thể sử dụng group ID và consumer riêng, cần theo dõi cả group và lag của các topic liên quan. Việc lag ở topic chính giảm không có nghĩa toàn bộ nghiệp vụ đã hoàn tất.

## 10. Exception classification và retry exhaustion

Một số exception là lỗi tạm thời, ví dụ dịch vụ đích trả 503 hoặc database timeout. Một số khác gần như chắc chắn không tự hết khi thử lại cùng payload, ví dụ dữ liệu sai schema nghiệp vụ hoặc một giá trị không hợp lệ.

Với retry-topic, có thể khai báo exception không retry ở annotation:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000),
    exclude = {InvalidOrderException.class, UnsupportedCurrencyException.class}
)
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    orderService.process(event);
}
```

Nếu lỗi thuộc nhóm `exclude` theo chính sách classifier, record không tiếp tục đi qua toàn bộ chuỗi retry và có thể được định tuyến đến DLT sớm. Vì vậy, số lần thử thực tế có thể nhỏ hơn `attempts`.

Tương tự, một record có thể được xử lý thành công ở attempt thứ hai; khi đó nó không đi đến retry topic tiếp theo hoặc DLT. Một lần xử lý thành công không tạo record mới chỉ để hoàn thành chuỗi retry.

Hãy xác định ranh giới giữa “lỗi có thể phục hồi” và “lỗi cần điều tra” dựa trên nghiệp vụ, thay vì retry mọi exception. Retry liên tục một payload sai có thể làm tăng chi phí và trì hoãn việc xử lý các record hợp lệ.

## 11. Serializer, partition và điều kiện tồn tại của topic đích

Recoverer muốn publish thành công phải có producer đủ quyền ghi, serializer đúng loại dữ liệu và topic đích hợp lệ. Một số tình huống cần chú ý:

- **Topic không tồn tại:** nếu auto-create bị tắt, mọi retry topic và DLT cần được tạo trước hoặc trong quy trình deploy. Tên topic phải khớp chính sách naming của Spring Kafka.
- **Số partition không đủ:** nếu recoverer publish tới partition được chọn nhưng destination không có partition đó, producer có thể thất bại. Hãy kiểm tra partition count trên retry topic và DLT.
- **Serializer không tương thích:** nếu value là POJO ở nhánh thành công nhưng là `byte[]` khi deserialization lỗi, một serializer cố định cho POJO có thể không xử lý được cả hai loại. Cân nhắc `DelegatingByTypeSerializer` hoặc template phù hợp theo loại value.
- **ACL không đủ:** consumer group có quyền đọc topic chính chưa chắc producer template có quyền ghi retry topic và DLT.
- **Payload/headers quá lớn:** nhiều lần retry, exception headers và stack trace có thể làm tăng kích thước message, dẫn đến lỗi publish theo giới hạn broker/producer.
- **Schema evolution:** retry/DLT có thể giữ record lâu hơn topic chính; serializer và consumer cần cân nhắc tương thích schema của event cũ.

Các lỗi này thường biểu hiện thành `SerializationException`, timeout, authorization failure, unknown topic/partition hoặc publish future hoàn tất với exception. Khi điều tra, ghi lại destination đã chọn, topic/partition nguồn, event ID, exception class và kết quả publish.

## 12. Thứ tự xử lý và giới hạn của retry topic

Non-blocking retry cho phép consumer topic chính tiếp tục xử lý các record khác trong khi record lỗi đang chờ ở retry topic. Đây là ưu điểm về thông lượng nhưng có ảnh hưởng đến thứ tự.

Ví dụ các event của cùng một đơn hàng ở partition chính:

```text
orders-0:  event A -> event B -> event C

event A lỗi -> chuyển sang retry topic
event B thành công tại topic chính
event C thành công tại topic chính
event A được xử lý lại sau đó
```

Nếu nghiệp vụ yêu cầu A phải hoàn tất trước B và C, retry topic có thể phá vỡ giả định đó. Key giống nhau không bảo đảm giữ đúng thứ tự nghiệp vụ sau khi record đã được chuyển ra topic khác. Cân nhắc blocking retry, xử lý theo aggregate với cơ chế kiểm soát phiên bản, hoặc chuyển trạng thái nghiệp vụ qua một workflow có thứ tự rõ ràng.

Non-blocking retry của Spring Kafka cũng có các giới hạn tương thích theo phiên bản. Các phiên bản phổ biến thiết kế nó cho record listener và không hỗ trợ batch listener theo cách tương tự; việc kết hợp với Kafka transactions có hạn chế. Luôn kiểm tra hướng dẫn đúng phiên bản Spring Kafka trước khi bật retry topic cho listener dạng batch hoặc container có transaction manager.

## 13. Vận hành DLT và quy trình replay

DLT là nơi giữ record không thể xử lý sau các attempt cho phép. DLT không tự sửa dữ liệu và không bảo đảm có người xử lý. Một quy trình vận hành cần trả lời được:

1. Nhóm nào nhận cảnh báo khi DLT có record mới?
2. Ai xác định lỗi dữ liệu, lỗi code hay lỗi dependency?
3. Record có thể xử lý lại nguyên vẹn hay phải sửa dữ liệu/trạng thái trước?
4. Replay về topic chính, một topic đặc biệt hay một workflow thủ công?
5. Làm sao tránh lặp hiệu ứng nghiệp vụ khi replay?
6. Làm sao ghi nhận record nào đã được replay, thành công hay thất bại?

Ví dụ metadata cần ghi trong hệ thống theo dõi lỗi:

```text
event_id=order-7835-created
original_topic=orders
original_partition=2
original_offset=18403
current_topic=orders-dlt
exception=PaymentGatewayUnavailableException
last_attempt_time=2026-11-15T14:30:00Z
replay_status=PENDING_REVIEW
```

Đây là dữ liệu minh họa; thời điểm, topic, ID và exception trong thực tế lấy từ record và log. Không dựa vào offset tại DLT để suy ra offset của record gốc.

Khi replay, record có thể đi qua lại cùng chuỗi retry topic nếu vẫn giữ cấu hình ban đầu. Cần thiết kế giới hạn replay, cảnh báo nếu lỗi lặp và khóa idempotency, nếu không một record sai có thể tạo vòng lặp dài qua DLT và retry workflow.

## 14. Quan sát recoverer trong production

Các tín hiệu nên thu thập cho từng topic, consumer group và destination:

| Tín hiệu | Diễn giải |
|---|---|
| Số record publish đến retry topic | Mức lỗi cần retry theo từng bước của chuỗi. |
| Số record publish đến DLT | Số record không được giải quyết trong ngân sách attempt. |
| Tỷ lệ publish failure của recoverer | Rủi ro không chuyển giao được record giữa các topic. |
| Độ trễ publish | Broker/producer hoặc network có thể đang chậm. |
| Retry-topic consumer lag | Record lỗi đang chờ xử lý lại; không thể chỉ xem lag topic chính. |
| DLT consumer lag | Số record chưa được quan sát hoặc xử lý bởi quy trình DLT. |
| Phân bố delivery attempt | Cho biết lỗi thường phục hồi ở lần đầu hay kéo dài nhiều attempt. |
| Số lần rebalance và lỗi commit | Có thể tác động đến việc record được giao lại. |

Khi log, ưu tiên `eventId`, `originalTopic`, `originalPartition`, `originalOffset`, `currentTopic`, `destinationTopic`, `attempt`, `exceptionType`. Nếu có tracing, giữ correlation ID xuyên các lần publish, nhưng kiểm soát lượng header và tránh đưa dữ liệu bí mật vào log.

Đừng đánh giá hệ thống chỉ bằng việc `orders` không còn lag. Consumer chính có thể đã forward nhiều record lỗi sang retry topic hoặc DLT, khiến lag topic chính bằng 0 nhưng nghiệp vụ vẫn đang thất bại. Cần có dashboard phản ánh cả ba giai đoạn: xử lý chính, retry và DLT.

## 15. Sự cố thường gặp và cách tiếp cận

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Listener lỗi nhưng không thấy retry topic nhận record | Recoverer publish thất bại, topic đích sai hoặc exception bị phân loại không retry. | Kiểm tra log publish, destination, topic naming, serializer và classifier. |
| Record nhảy thẳng vào DLT | Không retry exception này, attempts đã cạn hoặc backoff/destination policy chọn DLT. | Kiểm tra `exclude`, số attempt, retry metadata và exception chain. |
| DLT nhận record nhưng handler không xử lý | DLT listener chưa chạy, group ID khác, lỗi deserialization hoặc DLT handler thất bại. | Kiểm tra assignment, lag của DLT group và log listener. |
| Consumer chính hết lag nhưng công việc chưa xong | Record đã được chuyển sang retry topic/DLT. | Kiểm tra lag và số record pending ở retry/DLT. |
| Publish vào retry/DLT thất bại | Serializer, ACL, timeout, topic/partition hoặc message size. | Kiểm tra producer future, exception, broker và cấu hình destination. |
| Record bị xử lý lặp | Crash giữa thao tác nghiệp vụ và commit hoặc retry/replay nhiều chu kỳ. | Dùng event ID, idempotency key, unique constraint và đối chiếu lịch sử. |
| Thứ tự nghiệp vụ bị đảo | Record lỗi bị tách sang retry topic, record đến sau tiếp tục xử lý. | Đánh giá yêu cầu ordering và kiến trúc retry phù hợp. |
| Header hoặc payload tăng sau nhiều retry | Stack trace/exception metadata được tích lũy. | Kiểm soát header retention, payload size và cấu hình recoverer. |

## 16. Quy trình triển khai an toàn

Khi đưa `DeadLetterPublishingRecoverer` vào hệ thống non-blocking retry, có thể thực hiện theo trình tự:

1. Xác định số lần thử tối đa, lịch backoff và loại exception được phép retry.
2. Đặt tên retry topic và DLT, tạo sẵn topic với partition count, retention và ACL phù hợp.
3. Cấu hình `@RetryableTopic` hoặc `RetryTopicConfigurationBuilder` cùng một producer template có serializer đúng.
4. Xác định và triển khai DLT handler hoặc quy trình vận hành DLT.
5. Cấu hình hành vi phát hiện lỗi publish của recoverer theo API phiên bản Spring Kafka đang dùng.
6. Đảm bảo consumer chỉ xem bước chuyển giao là hoàn tất sau khi recoverer thành công theo chính sách đã chọn.
7. Thiết kế nghiệp vụ idempotent và đánh giá ảnh hưởng đến thứ tự xử lý.
8. Quan sát retry-topic lag, DLT ingress, publish failure, delivery attempts và lỗi consumer sau deployment.
9. Chuẩn bị quy trình điều tra và replay có kiểm soát cho record trong DLT.

`DeadLetterPublishingRecoverer` là mắt xích chuyển giao record trong cơ chế non-blocking retry của Spring Kafka. Khi hiểu rằng recoverer có thể publish tới cả retry topic lẫn DLT, cấu hình đúng producer và destination, xử lý lỗi publish và vận hành DLT rõ ràng, ứng dụng có thể thử lại các lỗi tạm thời mà vẫn giữ được khả năng truy vết và phục hồi các record không thể xử lý.
