# Reliability Operations trong Spring Kafka

Reliability Operations là tập hợp các thiết kế, cấu hình, quy trình giám sát và thao tác vận hành giúp hệ thống Spring Kafka tiếp tục xử lý sự kiện đúng cách khi có lỗi ứng dụng, lỗi mạng, broker mất kết nối, consumer bị khởi động lại hoặc lưu lượng tăng đột biến. Mục tiêu không chỉ là giữ cho ứng dụng luôn chạy, mà còn phải kiểm soát được ba kết quả quan trọng: không làm mất sự kiện đã được chấp nhận, hạn chế xử lý trùng gây sai lệch dữ liệu và khôi phục được các sự kiện không thể xử lý ngay.

Spring Kafka cung cấp các thành phần như KafkaTemplate, listener container, CommonErrorHandler, DefaultErrorHandler, DeadLetterPublishingRecoverer, retry topics và hỗ trợ transaction. Những thành phần này tạo nền tảng cho vận hành tin cậy, nhưng độ tin cậy cuối cùng còn phụ thuộc vào cấu hình Kafka cluster, cách quản lý offset, tính idempotent của nghiệp vụ, chiến lược retry, khả năng quan sát và quy trình xử lý sự cố.

## 1. Xác định mục tiêu tin cậy

Trước khi cấu hình Spring Kafka, cần xác định điều gì được xem là một sự kiện đã được chấp nhận, khi nào một lần xử lý được xem là hoàn tất và hệ thống phải phản ứng thế nào khi không thể xử lý một sự kiện.

| Mối quan tâm | Câu hỏi vận hành | Cơ chế thường dùng |
|---|---|---|
| Producer gửi sự kiện | Khi broker xác nhận, dữ liệu có đủ bản sao để chịu lỗi không? | `acks=all`, replication, `min.insync.replicas`, producer idempotence |
| Consumer xử lý sự kiện | Offset được xác nhận sau thời điểm nào? | Container-managed acknowledgement, `enable.auto.commit=false`, ack mode phù hợp |
| Xử lý lặp | Nếu một record được giao lại, nghiệp vụ có tạo tác động lặp không? | Idempotency key, unique constraint, inbox/deduplication |
| Lỗi tạm thời | Có nên thử lại và thử trong bao lâu? | Backoff, retry có giới hạn, retry topics |
| Lỗi không thể tự phục hồi | Làm thế nào để giữ record và tiếp tục xử lý các record khác? | Dead-letter topic (DLT), quy trình điều tra và replay |
| Sự cố diện rộng | Làm sao phát hiện trước khi người dùng bị ảnh hưởng? | Metrics, logs, tracing, alert và runbook |

Các mục tiêu nên được diễn đạt thành SLO có thể đo lường, ví dụ thời gian tối đa một sự kiện được phép nằm trong hàng đợi, tỷ lệ xử lý thành công, thời gian phục hồi sau sự cố và số lượng record lỗi tồn đọng. Ngưỡng cảnh báo cần dựa trên tải nền, đặc tính nghiệp vụ và khả năng phục hồi của hệ thống; không có một con số phù hợp cho mọi cụm Kafka.

## 2. Hiểu đúng delivery semantics

Kafka và Spring Kafka có thể hỗ trợ nhiều mức bảo đảm giao nhận. Cần phân biệt việc producer gửi thành công, broker lưu dữ liệu và consumer hoàn tất nghiệp vụ. Đây là các mốc khác nhau.

| Semantics | Hành vi | Đánh đổi |
|---|---|---|
| At-most-once | Offset hoặc trạng thái hoàn tất được xác nhận trước khi xử lý xong | Có thể mất record nếu ứng dụng dừng sau khi xác nhận nhưng trước khi hoàn tất nghiệp vụ |
| At-least-once | Record chỉ được xác nhận sau khi xử lý; record có thể được giao lại | Hạn chế mất record nhưng nghiệp vụ phải chịu được xử lý trùng |
| Exactly-once trong Kafka | Đọc, xử lý và ghi sang Kafka trong một transaction có thể được commit nguyên tử | Phạm vi bảo đảm chủ yếu nằm trong luồng Kafka; không tự động bao phủ database, HTTP API hay hệ thống bên ngoài |

Với phần lớn consumer nghiệp vụ, at-least-once kết hợp xử lý idempotent là lựa chọn thực tế. Nếu consumer hoàn tất cập nhật database nhưng chết trước khi offset được commit, Kafka có thể giao lại record. Điều đó không nhất thiết là lỗi của Kafka; đó là hệ quả bình thường của at-least-once. Ứng dụng cần nhận diện cùng một sự kiện và tránh tạo tác động nghiệp vụ lần thứ hai.

Không nên quảng bá hệ thống là exactly-once chỉ vì producer bật idempotence hoặc ứng dụng có transaction. Producer idempotence giúp hạn chế bản ghi trùng do retry ở tầng producer. Kafka transaction có thể phối hợp việc đọc offset và ghi record Kafka. Cả hai đều không tự làm cho một lệnh trừ tiền trong database hoặc một HTTP request trở nên exactly-once.

## 3. Cấu hình producer để gửi tin cậy

Producer cần biết broker đã nhận dữ liệu ở mức nào, retry trong khoảng thời gian bao lâu và phải làm gì khi không thể gửi. Một cấu hình cơ sở cho producer quan trọng có thể được khai báo trong Spring Boot như sau:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Đây là cấu hình minh họa cần được điều chỉnh theo phiên bản Kafka client, Spring Boot, SLA và đặc điểm tải thực tế.

- `acks=all` yêu cầu broker leader chờ các replica đang nằm trong in-sync replica set (ISR) xác nhận theo giao thức Kafka. Mức bảo vệ thực tế còn phụ thuộc `min.insync.replicas` của topic hoặc broker.
- `enable.idempotence=true` giúp producer tránh tạo bản ghi trùng do retry trong phạm vi producer session và hỗ trợ giữ thứ tự với các giới hạn cấu hình tương thích.
- `retries` cho phép producer thử lại lỗi có thể phục hồi. Không nên xem số lần retry lớn là bảo đảm gửi vô hạn; `delivery.timeout.ms` vẫn giới hạn tổng thời gian giao một record.
- `max.in.flight.requests.per.connection` cần tuân theo điều kiện tương thích với idempotence. Giá trị không quá 5 là cấu hình phổ biến cho Kafka producer hiện đại.
- `request.timeout.ms` giới hạn thời gian chờ một request; `delivery.timeout.ms` bao phủ thời gian chờ, retry và gửi record. Cần đặt quan hệ giữa hai giá trị hợp lý, đồng thời tính đến độ trễ mạng và thời gian broker xử lý.

`acks=all` chỉ có ý nghĩa khi topic có replication factor phù hợp và ISR không bị thu hẹp dưới ngưỡng an toàn. Ví dụ, topic có replication factor 3 và `min.insync.replicas=2` thường cho phép chịu lỗi một replica trong khi vẫn yêu cầu ít nhất hai replica đồng bộ xác nhận. Nếu ISR xuống dưới mức tối thiểu, producer có thể nhận lỗi thay vì chấp nhận ghi với mức an toàn thấp hơn. Đây là hành vi cần thiết để bảo vệ dữ liệu, nhưng ứng dụng phải có cảnh báo và quy trình xử lý.

### 3.1. Xử lý kết quả gửi từ KafkaTemplate

Không nên coi việc gọi `KafkaTemplate.send()` là bằng chứng record đã được broker chấp nhận. Hãy quan sát kết quả bất đồng bộ và xử lý lỗi gửi:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> send =
        kafkaTemplate.send("orders", orderId, event);

send.whenComplete((result, error) -> {
    if (error != null) {
        // Ghi nhận lỗi gửi, correlation id và thông tin cần thiết để điều tra.
        // Chỉ retry ở tầng nghiệp vụ khi đã có chính sách chống gửi trùng.
        log.error("Cannot publish order event, orderId={}", orderId, error);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.debug("Published order event: topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
~~~

Trong Spring Kafka 3.x, phương thức send trả về `CompletableFuture`. Các phiên bản cũ có thể sử dụng kiểu future khác; cần đối chiếu API với phiên bản dependency của dự án.

Nếu nghiệp vụ chỉ được xác nhận với người gọi sau khi Kafka đã nhận record, hãy chờ hoặc phối hợp kết quả gửi theo cách phù hợp với luồng request. Tránh chặn thread tùy tiện trong request path hoặc trong listener. Nếu gửi thất bại sau khi nghiệp vụ đã trả về thành công, phải có cơ chế phục hồi như transactional outbox hoặc hàng đợi gửi lại có lưu trạng thái.

### 3.2. Chọn key và partition có chủ đích

Kafka chỉ bảo đảm thứ tự trong một partition. Các sự kiện cần giữ thứ tự, chẳng hạn các thay đổi trạng thái của cùng một đơn hàng, nên dùng cùng một key ổn định như `orderId`. Producer sẽ dùng key để chọn partition theo partitioner.

Key phân bố không đều có thể tạo hot partition: một partition nhận phần lớn lưu lượng, khiến consumer xử lý chậm dù các partition khác còn rảnh. Cần theo dõi lưu lượng và độ trễ theo partition. Tăng số partition có thể làm thay đổi ánh xạ key sang partition, vì vậy phải đánh giá ảnh hưởng đến thứ tự của các sự kiện đang tồn tại trước khi thay đổi.

## 4. Cấu hình consumer và quản lý offset

Consumer phải xác định thời điểm commit offset sao cho record chỉ được xem là hoàn tất sau khi nghiệp vụ đã đạt trạng thái bền vững. Cấu hình cơ sở thường tắt auto commit để listener container quản lý việc xác nhận:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[max.poll.records]": 100
        "[max.poll.interval.ms]": 300000
    listener:
      ack-mode: record
~~~

`auto-offset-reset` chỉ được dùng khi group chưa có committed offset hợp lệ hoặc offset hiện tại không còn trong phạm vi log. `earliest` giúp đọc lại dữ liệu còn giữ trên topic; `latest` bắt đầu từ dữ liệu mới. Đây không phải thiết lập thay thế cho việc quản lý offset đã commit.

### 4.1. Chọn acknowledgement mode

Với `AckMode.RECORD`, container commit offset của record sau khi listener xử lý record đó thành công. Đây là điểm bắt đầu dễ hiểu cho listener xử lý từng record.

Với `AckMode.BATCH`, offset được commit theo batch do một lần poll trả về. Nếu lỗi xảy ra trong batch, error handler và container phải phối hợp việc seek hoặc redeliver các record chưa hoàn tất.

Với `MANUAL` hoặc `MANUAL_IMMEDIATE`, ứng dụng chủ động gọi acknowledgement. Chỉ ack sau khi tác động nghiệp vụ đã được lưu bền vững. Ack quá sớm có thể làm mất khả năng xử lý lại record khi ứng dụng gặp sự cố.

Ví dụ listener xử lý một record:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consume(OrderCreated event) {
    billingService.createInvoiceIdempotently(event);
}
~~~

Nếu `createInvoiceIdempotently` ném exception, container có thể áp dụng retry hoặc error handler. Khi phương thức trả về bình thường, container mới xem record là xử lý thành công theo ack mode đã cấu hình.

### 4.2. Điều chỉnh poll và thời gian xử lý

Kafka consumer cần gọi `poll()` đủ thường xuyên. Nếu thời gian giữa các lần poll vượt `max.poll.interval.ms`, consumer có thể bị xem là không còn hoạt động và partition được phân phối lại cho member khác.

- `max.poll.records` giới hạn số record trả về trong một lần poll. Giảm giá trị này có thể giảm thời gian xử lý mỗi batch nhưng tăng số lần poll.
- `max.poll.interval.ms` phải lớn hơn thời gian xử lý batch trong tình huống chậm có thể dự đoán, cộng thêm biên an toàn.
- `session.timeout.ms` và heartbeat liên quan đến việc phát hiện consumer mất kết nối. Không nên thay đổi chúng độc lập mà không hiểu cơ chế group coordination.
- `concurrency` của Spring listener container tạo các consumer chạy song song. Trong một consumer group, số consumer đang hoạt động hữu ích thường không vượt số partition của topic.

Nếu listener thực hiện công việc lâu như gọi API ngoài, tạo báo cáo lớn hoặc xử lý file, cần cân nhắc tách công việc sang worker nội bộ và thiết kế rõ thời điểm ack. Không nên đưa record vào một executor không giới hạn rồi ack ngay; khi ứng dụng dừng, các công việc đã ack nhưng chưa hoàn tất sẽ không được Kafka giao lại.

### 4.3. Thiết kế nghiệp vụ idempotent

Một consumer at-least-once cần chịu được việc cùng một event được xử lý nhiều lần. Một cách phổ biến là lưu `eventId` vào bảng inbox với unique constraint trong cùng transaction database với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Luồng xử lý có thể thực hiện theo thứ tự:

1. Bắt đầu transaction database.
2. Thử ghi `eventId` vào bảng `processed_events`.
3. Nếu vi phạm unique constraint, sự kiện đã được xử lý; kết thúc transaction mà không lặp lại tác động.
4. Nếu ghi thành công, thực hiện cập nhật nghiệp vụ.
5. Commit database transaction rồi để listener hoàn tất và commit offset.

Việc ghi dấu event và cập nhật nghiệp vụ phải nằm trong cùng transaction database. Nếu ghi dấu trước rồi cập nhật nghiệp vụ ở transaction khác, lỗi giữa hai bước có thể khiến sự kiện bị đánh dấu đã xử lý dù tác động nghiệp vụ chưa xảy ra.

## 5. Retry và xử lý lỗi trong Spring Kafka

Không phải lỗi nào cũng nên retry. Một lỗi mạng ngắn hạn có thể tự phục hồi; dữ liệu sai định dạng hoặc vi phạm quy tắc nghiệp vụ thường không thể sửa bằng cách gửi lại cùng một record.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout database, lỗi kết nối dịch vụ phụ thuộc, broker vừa chuyển leader | Retry có backoff và giới hạn |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, giá trị không đúng miền | Không retry hoặc chỉ retry sau khi có thay đổi dữ liệu |
| Lỗi cấu hình/triển khai | Sai schema, thiếu quyền, topic chưa tồn tại | Cảnh báo và sửa nguyên nhân; tránh retry dày đặc |
| Lỗi không xác định | Exception chưa phân loại | Retry hữu hạn, sau đó đưa vào DLT để điều tra |

Retry không có giới hạn có thể giữ một partition ở trạng thái bận, làm tăng consumer lag và khiến các record phía sau chờ đợi. Backoff giúp giảm áp lực lên dịch vụ đang lỗi. Số lần retry và tổng thời gian chờ cần dựa trên khả năng phục hồi của dependency và thời hạn xử lý của nghiệp vụ.

### 5.1. Blocking retry với DefaultErrorHandler

Spring Kafka cung cấp `DefaultErrorHandler` để retry record trong listener container và chuyển record sang recoverer khi hết retry. Ví dụ sau dùng exponential backoff:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    ExponentialBackOffWithMaxRetries backOff =
            new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(1_000L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);
    handler.addNotRetryableExceptions(
            IllegalArgumentException.class);

    return handler;
}
~~~

Gắn error handler vào listener container factory đang được ứng dụng sử dụng:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Ví dụ này minh họa cách kết nối các thành phần; kiểu generic của KafkaTemplate, factory và cấu hình serializer phải khớp với ứng dụng thực tế. Trong các phiên bản Spring Kafka cũ, API error handler có thể khác.

`ExponentialBackOffWithMaxRetries(4)` biểu thị số lần retry sau lần xử lý ban đầu theo API của Spring Kafka. Cần xác nhận cách đếm attempt trong phiên bản đang dùng và tài liệu cấu hình tương ứng để tránh hiểu nhầm tổng số lần listener được gọi.

Blocking retry phù hợp khi cần giữ thứ tự xử lý trong partition và lỗi có khả năng phục hồi trong thời gian ngắn. Trong thời gian chờ retry, khả năng xử lý của consumer thread bị giảm; nếu lỗi kéo dài, lag có thể tăng nhanh.

### 5.2. Non-blocking retry với retry topics

Retry topics chuyển record lỗi sang topic retry có thời gian chờ, cho phép consumer của topic chính tiếp tục xử lý các record khác. Spring Kafka hỗ trợ cách tiếp cận này qua `@RetryableTopic`:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000),
        dltTopicSuffix = ".DLT")
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consume(OrderCreated event) {
    billingService.createInvoiceIdempotently(event);
}

@DltHandler
public void handleDlt(OrderCreated event) {
    dltOperations.recordForInvestigation(event);
}
~~~

Trong cấu hình này, `attempts` là tổng số lần thử theo quy ước của annotation, bao gồm lần xử lý ban đầu. Hãy kiểm tra phiên bản Spring Kafka và loại exception được cấu hình để biết chính xác record sẽ đi qua các topic nào.

Retry topics hữu ích khi không muốn một record lỗi chặn toàn bộ tiến trình của partition chính. Đổi lại, record được retry có thể quay lại sau các record mới hơn, nên thứ tự nghiệp vụ giữa các sự kiện cùng key có thể thay đổi. Nếu thứ tự là yêu cầu bắt buộc, cần cân nhắc blocking retry hoặc thiết kế lại luồng nghiệp vụ.

Không nên vô tình xếp chồng nhiều tầng retry độc lập, chẳng hạn retry ở listener, retry trong service, retry của HTTP client và retry topic, mà không tính tổng số lần gọi. Một record có thể tạo ra số lần gọi dependency lớn hơn nhiều so với dự kiến. Hãy chọn một tầng chịu trách nhiệm chính, đặt giới hạn tổng thời gian và truyền correlation/event id qua các lần thử.

## 6. Dead-letter topic và quy trình phục hồi

DLT giữ lại record không thể xử lý sau retry để hệ thống tiếp tục tiến lên. DLT là một hàng đợi cần vận hành, không phải nơi lưu trữ lỗi vô thời hạn.

Khi cấu hình `DeadLetterPublishingRecoverer`, Spring Kafka thường tạo tên topic đích bằng cách thêm hậu tố `.DLT` vào topic nguồn và giữ partition tương ứng theo mặc định. Vì vậy, topic DLT phải có đủ partition tương ứng với partition nguồn nếu dùng cách ánh xạ mặc định. Nếu muốn ánh xạ khác, cần cung cấp resolver phù hợp.

Khi record đi vào DLT, cần giữ thông tin giúp điều tra:

- Topic, partition và offset ban đầu.
- Key và event id để tìm các sự kiện liên quan.
- Exception class, thông điệp lỗi và thời điểm thất bại.
- Số lần thử và topic retry đã đi qua nếu có.
- Correlation id hoặc trace id để liên kết log giữa các service.

Không ghi payload nhạy cảm hoặc toàn bộ stack trace vào log ứng dụng một cách thiếu kiểm soát. Cần giới hạn quyền đọc DLT, áp dụng chính sách retention phù hợp và tuân thủ quy định dữ liệu của hệ thống.

### 6.1. Quy trình xử lý DLT

Một quy trình vận hành DLT có thể gồm các bước:

1. Alert khi số record mới vào DLT tăng bất thường hoặc tuổi của record cũ nhất vượt ngưỡng.
2. Nhóm vận hành xác định nguyên nhân theo exception, schema version, topic, partition và thời điểm triển khai.
3. Phân loại record: dữ liệu cần sửa, lỗi code cần triển khai bản vá, lỗi dependency hay sự kiện không còn hợp lệ về nghiệp vụ.
4. Sửa nguyên nhân và xác minh bằng một số record đại diện trong môi trường phù hợp.
5. Replay có kiểm soát, giới hạn tốc độ và theo dõi kết quả.
6. Đối chiếu số record đã replay, số record thành công và số record vẫn lỗi; giữ lại audit trail.

Replay phải được thiết kế idempotent vì record có thể đã tạo một phần tác động trước khi lỗi xảy ra. Không nên replay toàn bộ DLT ngay sau khi sửa code mà chưa xác định tác động của việc xử lý trùng. Với sự kiện có thứ tự, cần cân nhắc replay theo key hoặc theo thứ tự gốc.

### 6.2. Bảo đảm việc gửi DLT thành công

Không được xem việc gọi recoverer là bằng chứng DLT đã lưu record. Cần kiểm tra cấu hình và API của phiên bản Spring Kafka đang dùng để bảo đảm lỗi gửi DLT được báo ngược về container, thay vì commit offset nguồn trong khi record chưa được lưu vào DLT. Với các phiên bản hỗ trợ, có thể cấu hình recoverer chờ kết quả gửi và xem lỗi gửi là lỗi phục hồi. Hãy kiểm thử tình huống DLT broker không khả dụng trước khi triển khai.

## 7. Serialization và schema compatibility

Một record có thể không được xử lý vì consumer không deserialize được key hoặc value. Đây là lỗi xảy ra trước khi listener nhận được object nghiệp vụ, vì vậy cần thiết kế xử lý deserialization riêng.

Spring Kafka có `ErrorHandlingDeserializer`, cho phép bọc deserializer thực tế và chuyển thông tin lỗi để error handler/recoverer xử lý. Cấu hình delegate phải khớp serializer của producer và định dạng dữ liệu trên topic. Nếu dùng JSON, cần quản lý type header, trusted packages và schema evolution rõ ràng.

Các nguyên tắc vận hành quan trọng:

- Thay đổi schema theo hướng tương thích với producer và consumer đang chạy đồng thời.
- Triển khai consumer có khả năng đọc schema cũ trước khi producer bắt đầu phát schema mới.
- Không dùng class name tùy ý lấy từ message header làm ranh giới tin cậy.
- Đưa record deserialize lỗi vào luồng điều tra phù hợp, giữ raw payload khi chính sách bảo mật cho phép.
- Có kiểm soát phiên bản schema và quy trình rollback khi release gây lỗi hàng loạt.

Nếu một lần deploy làm tỷ lệ deserialize failure tăng đột biến, hãy xem đây là sự cố tương thích schema hoặc cấu hình serializer/deserializer. Retry cùng một payload với cùng một binary thường không giải quyết được nguyên nhân.

## 8. Transaction, exactly-once và Outbox/Inbox

### 8.1. Kafka transaction

Kafka transaction cho phép producer ghi nhiều record vào Kafka theo một đơn vị nguyên tử. Với luồng consume-transform-produce, Spring Kafka có thể phối hợp việc gửi output và xác nhận offset input trong transaction. Nếu transaction bị abort, output không được xem là đã commit và offset input không được tiến lên như một giao dịch thành công.

Khi bật transaction cho producer, cần cấu hình transaction id prefix duy nhất giữa các instance ứng dụng đang chạy đồng thời. Không dùng cùng một prefix theo cách gây trùng transactional id giữa các instance. Consumer đọc dữ liệu transactional với `isolation.level=read_committed` nếu chỉ muốn nhận record thuộc transaction đã commit.

Transaction Kafka phù hợp khi đầu vào và đầu ra đều nằm trong Kafka. Nó không làm cho database transaction và Kafka transaction trở thành một transaction phân tán nguyên tử.

### 8.2. Transactional outbox

Một tình huống phổ biến là ứng dụng vừa cập nhật database vừa phát sự kiện Kafka. Nếu ghi database thành công nhưng gửi Kafka thất bại, hai hệ thống mất đồng bộ. Nếu gửi Kafka trước rồi database rollback, consumer có thể nhận một sự kiện không tương ứng với trạng thái database.

Transactional outbox giải quyết vấn đề này bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng database transaction. Một publisher riêng đọc outbox và gửi sự kiện sang Kafka; sau khi gửi thành công, nó đánh dấu hoặc lưu checkpoint đã phát. Publisher có thể gửi lặp khi gặp lỗi giữa lúc broker nhận record và lúc database ghi nhận trạng thái đã gửi, vì vậy consumer vẫn cần idempotency.

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Outbox cần có quy trình vận hành riêng: theo dõi số bản ghi chưa phát, tuổi bản ghi cũ nhất, tốc độ publisher, lỗi gửi và khả năng replay. Cần có chính sách dọn dữ liệu đã phát sau thời gian lưu giữ phù hợp.

### 8.3. Inbox ở phía consumer

Inbox hoặc bảng processed events giúp consumer chống xử lý trùng khi Kafka giao lại record. Event id phải ổn định xuyên suốt producer, retry topic và DLT. Nếu event id được tạo mới ở mỗi lần retry, cơ chế deduplication sẽ không nhận ra cùng một sự kiện.

Với thao tác gọi dịch vụ ngoài như thanh toán hoặc gửi thông báo, hãy dùng idempotency key do nghiệp vụ định nghĩa và tận dụng khả năng idempotency của API đích nếu có. Nếu API đích không hỗ trợ idempotency, cần có trạng thái xử lý trung gian và quy trình đối soát để xử lý trường hợp timeout không rõ kết quả.

## 9. Độ bền của Kafka cluster và topic

Producer config không thể bù cho một topic có replication và chính sách ISR yếu. Với dữ liệu quan trọng, cần phối hợp cấu hình topic, broker và producer.

| Thiết lập | Ý nghĩa vận hành |
|---|---|
| `replication.factor` | Số bản sao của partition trên các broker |
| `min.insync.replicas` | Số replica đồng bộ tối thiểu để chấp nhận ghi khi producer dùng `acks=all` |
| `unclean.leader.election.enable` | Cho phép hay không cho phép replica không nằm trong ISR trở thành leader; bật có thể tăng khả năng sẵn sàng nhưng có nguy cơ mất dữ liệu |
| `retention.ms` / `retention.bytes` | Thời gian hoặc dung lượng dữ liệu được giữ trên topic |
| `cleanup.policy` | Cách Kafka dọn dữ liệu, ví dụ delete hoặc compact |

Một cấu hình thường gặp cho topic quan trọng là replication factor 3, `min.insync.replicas=2`, producer `acks=all` và không cho phép unclean leader election. Đây là ví dụ thiết kế phổ biến, không phải giá trị mặc định bắt buộc; cần xét số broker, vùng lỗi, dung lượng và yêu cầu sẵn sàng của cụm.

Theo dõi các chỉ số cluster như offline partitions, under-replicated partitions, ISR shrink/expand, broker disk usage, request latency và tình trạng controller. Một partition mất replica có thể vẫn phục vụ request nhưng mức chịu lỗi đã giảm. Cảnh báo cần xuất hiện trước khi broker tiếp theo gặp sự cố.

Retention phải đủ dài để consumer có thời gian phục hồi sau outage hoặc lag tăng. Nếu consumer bị dừng lâu hơn retention, offset có thể trỏ ra ngoài log còn giữ; khi đó `auto.offset.reset` có thể khiến consumer bắt đầu ở vị trí khác và cần quy trình đối soát dữ liệu. DLT cũng cần retention đủ dài để điều tra và replay theo SLA.

## 10. Rebalance, scaling và triển khai ứng dụng

Rebalance xảy ra khi consumer tham gia/rời group, heartbeat bị mất, poll quá chậm hoặc subscription thay đổi. Rebalance thường xuyên làm giảm thời gian xử lý hữu ích và có thể làm tăng duplicate delivery do công việc chưa hoàn tất được giao lại.

Để giảm tác động:

- Giữ thời gian xử lý batch trong giới hạn `max.poll.interval.ms`.
- Chọn `max.poll.records` phù hợp với thời gian xử lý và dung lượng bộ nhớ.
- Tránh tạo consumer instance liên tục do health check hoặc autoscaling dao động.
- Triển khai rolling update với shutdown grace period đủ để listener dừng nhận việc và hoàn tất xử lý đang chạy.
- Theo dõi số lần rebalance, thời gian revoke/assign partition và nguyên nhân consumer rời group.
- Chỉ tăng concurrency khi có partition và năng lực downstream tương ứng.

Nếu topic có 6 partition và group có 10 consumer instance, tối đa 6 consumer có thể được gán partition tại một thời điểm; các instance còn lại không làm tăng thông lượng của group đó. Tăng partition có thể tăng khả năng song song nhưng cũng làm thay đổi key-to-partition mapping và tăng chi phí quản lý.

Khi deploy phiên bản mới, cần xem xét khả năng tương thích giữa producer và consumer chạy song song trong thời gian rollout. Tránh đổi format message theo cách consumer cũ không thể đọc. Nếu có thay đổi lớn, dùng chiến lược expand-and-contract: triển khai consumer tương thích trước, sau đó mới chuyển producer, rồi loại bỏ hỗ trợ cũ ở một release sau.

## 11. Observability: metrics, logs và tracing

Một hệ thống Kafka đáng tin cậy phải cho biết record đang ở đâu, xử lý chậm ở bước nào và lỗi có xu hướng tăng hay không. Chỉ theo dõi trạng thái process đang chạy là chưa đủ.

| Khu vực | Chỉ số nên theo dõi | Dấu hiệu cần điều tra |
|---|---|---|
| Producer | Send rate, error rate, retry rate, request latency, record size, buffer availability | Lỗi gửi tăng, retry kéo dài, buffer cạn |
| Consumer | Consumer lag theo group/topic/partition, records consumed rate, poll interval, commit failure | Lag tăng liên tục, tốc độ xử lý giảm, commit lỗi |
| Listener | Processing duration, exception rate, retry count, records recovered | Thời gian xử lý tăng, một loại exception lặp lại |
| Retry/DLT | Số record vào retry topic và DLT, tuổi record cũ nhất | DLT tăng nhanh hoặc record bị kẹt lâu |
| Cluster | Offline/under-replicated partitions, ISR, broker disk, request latency | Mất replica, disk gần đầy, broker phản hồi chậm |
| Nghiệp vụ | Số event được chấp nhận, hoàn tất, thất bại và đối soát | Chênh lệch giữa nguồn phát và kết quả nghiệp vụ |

Spring Kafka tích hợp với Micrometer ở các phiên bản phù hợp để xuất metrics của listener và Kafka client. Tên metric và tag có thể thay đổi theo phiên bản; hãy kiểm tra endpoint metrics thực tế sau khi bật instrumentation. Tránh tạo tag có cardinality rất cao như event id, order id hoặc customer id.

Log nên có event id, topic, partition, offset, consumer group, correlation id và tên handler khi các thông tin đó sẵn có. Không log toàn bộ payload theo mặc định vì payload có thể chứa dữ liệu cá nhân hoặc bí mật. Trace context cần được truyền qua message header và được khôi phục ở consumer để liên kết producer với các bước xử lý sau.

Alert hữu ích thường tập trung vào xu hướng và tuổi tồn đọng, không chỉ một giá trị tức thời:

- Lag tăng liên tục trong một khoảng thời gian.
- Tuổi của record cũ nhất vượt thời hạn nghiệp vụ.
- Producer error rate hoặc send latency vượt baseline.
- DLT có record mới hoặc lượng record tăng nhanh.
- Offline/under-replicated partition xuất hiện.
- Rebalance tăng đột biến sau một lần deploy.
- Outbox tồn đọng lâu hơn SLA phát sự kiện.

## 12. Health check và khả năng phục hồi

Health check cần phản ánh đúng khả năng phục vụ. Nếu Kafka tạm thời mất kết nối, liveness probe không nên lập tức làm container restart liên tục; restart storm có thể làm tăng rebalance và gây thêm tải lên cluster.

Có thể phân biệt:

- **Liveness:** tiến trình và các thread chính còn hoạt động, không bị deadlock.
- **Readiness:** instance có đủ điều kiện nhận thêm công việc hay không, xét đến trạng thái dependency và khả năng xử lý.
- **Business health:** luồng sự kiện có đang hoàn tất trong thời hạn nghiệp vụ hay không; thường được theo dõi qua metrics và alert riêng.

Việc đưa Kafka vào readiness phụ thuộc kiến trúc. Nếu tất cả instance cùng bị đánh dấu not-ready khi broker lỗi, hệ thống điều phối có thể loại toàn bộ instance khỏi service dù chúng vẫn có thể phục hồi khi broker trở lại. Hãy xác định hành vi mong muốn khi Kafka unavailable và thử nghiệm tình huống đó.

Khi shutdown, listener container nên được dừng có kiểm soát để hoàn tất record đang xử lý trong thời gian grace period. Nếu quá thời hạn, chấp nhận khả năng record được giao lại và bảo đảm consumer idempotent.

## 13. Runbook cho các tình huống thường gặp

### 13.1. Producer không gửi được record

1. Kiểm tra lỗi cụ thể: timeout, authorization, serialization, unknown topic hay lỗi ISR.
2. Kiểm tra broker connectivity, ACL, metadata và tình trạng leader của partition.
3. Xem producer retry rate, request latency và buffer availability.
4. Nếu lỗi do ISR hoặc broker, xử lý cluster theo quy trình vận hành; không hạ `acks` chỉ để làm mất cảnh báo.
5. Xác định các request nghiệp vụ đã nhận kết quả gửi thất bại hoặc chưa rõ kết quả; đối soát và retry bằng event id ổn định.

### 13.2. Consumer lag tăng

1. Xác định lag nằm ở toàn group hay chỉ một vài partition.
2. So sánh incoming rate với consumed rate để biết producer tăng tải hay consumer giảm năng lực.
3. Kiểm tra processing duration, exception/retry rate, downstream latency và rebalance.
4. Kiểm tra phân bố key để tìm hot partition.
5. Tăng consumer concurrency chỉ khi số partition và downstream cho phép; nếu không, tối ưu xử lý hoặc tăng partition sau khi đánh giá ảnh hưởng thứ tự.
6. Theo dõi tuổi record cũ nhất đến khi trở lại trong SLO.

### 13.3. DLT tăng đột biến

1. Nhóm record theo exception class, topic nguồn, schema version và thời điểm phát sinh.
2. Kiểm tra thay đổi code/config gần nhất và tình trạng dependency.
3. Dừng hoặc giới hạn replay tự động nếu nó đang tạo tải hoặc lặp lỗi.
4. Sửa nguyên nhân và xác minh bằng record đại diện.
5. Replay theo batch có giới hạn, giữ event id và ghi audit.
6. Đối soát kết quả nghiệp vụ để xác nhận không mất hoặc nhân đôi tác động.

### 13.4. Rebalance liên tục

1. Kiểm tra log group coordinator và nguyên nhân rời group.
2. Đo thời gian xử lý giữa các lần poll so với `max.poll.interval.ms`.
3. Kiểm tra GC pause, CPU throttling, network interruption và downstream call bị treo.
4. Điều chỉnh batch size hoặc thời gian xử lý; chỉ thay timeout sau khi hiểu nguyên nhân.
5. Sau deploy, so sánh tần suất rebalance và lag với baseline trước deploy.

### 13.5. Broker hoặc một vùng lỗi ngừng hoạt động

1. Xác định phạm vi broker/zone và số partition bị ảnh hưởng.
2. Kiểm tra leader election, ISR và offline partition.
3. Xác nhận producer có đang bị từ chối ghi vì `min.insync.replicas` hay không.
4. Khôi phục broker theo quy trình cluster, theo dõi replica catch-up và disk.
5. Khi cluster ổn định, theo dõi producer retry, consumer lag và DLT để phát hiện lỗi tồn dư.

## 14. Kiểm thử độ tin cậy trước khi phát hành

Kiểm thử happy path không đủ để chứng minh một cấu hình Kafka đáng tin cậy. Integration test nên mô phỏng các điểm có thể lỗi:

- Broker tạm thời không khả dụng trong lúc producer gửi.
- Consumer dừng sau khi database commit nhưng trước khi offset commit.
- Listener ném exception nhiều lần rồi phục hồi.
- DLT không khả dụng khi recoverer cố gắng publish.
- Payload sai định dạng hoặc không tương thích schema.
- Consumer bị restart hoặc rebalance khi đang xử lý.
- Một downstream dependency chậm hơn thời gian bình thường.
- Retry và replay không tạo tác động nghiệp vụ trùng.

Có thể dùng Kafka Testcontainers hoặc embedded broker phù hợp với phiên bản Spring Kafka để kiểm thử tích hợp. Các kiểm thử cần xác nhận cả kết quả nghiệp vụ và trạng thái Kafka: record có được giữ, retry đúng số lần, DLT có nhận được record và offset có chỉ tiến lên sau khi phục hồi thành công hay không.

Ngoài integration test, cần có diễn tập vận hành ở môi trường gần production: tăng tải, dừng broker, tạo consumer lag, phục hồi DLT và thực hiện rolling deployment. Ghi lại thời gian phát hiện, thời gian phục hồi và các bước runbook cần cập nhật.

## 15. Checklist vận hành cho production

### Trước khi triển khai

- [ ] Topic quan trọng có replication factor, `min.insync.replicas` và retention phù hợp.
- [ ] Producer sử dụng `acks=all` và idempotence khi yêu cầu nghiệp vụ cần mức bảo vệ này.
- [ ] Consumer tắt auto commit và chọn ack mode có chủ đích.
- [ ] Listener idempotent hoặc có inbox/deduplication cho event id ổn định.
- [ ] Retry có giới hạn, backoff và phân loại exception.
- [ ] DLT có partition, ACL, retention, alert và quy trình replay.
- [ ] Schema producer/consumer tương thích trong giai đoạn rollout.
- [ ] Metrics, logs, tracing và dashboard đã được xác minh.
- [ ] Shutdown grace period và health check phản ánh đúng hành vi khi Kafka unavailable.

### Trong khi vận hành

- [ ] Theo dõi consumer lag và tuổi record cũ nhất.
- [ ] Theo dõi producer error/retry rate và tình trạng ISR.
- [ ] Theo dõi DLT, retry topics và outbox backlog.
- [ ] Điều tra rebalance bất thường và hot partition.
- [ ] Replay record lỗi theo batch có kiểm soát và có audit.
- [ ] Đối soát số lượng sự kiện với kết quả nghiệp vụ sau sự cố.

### Sau sự cố

- [ ] Xác định nguyên nhân gốc và phạm vi record bị ảnh hưởng.
- [ ] Kiểm tra duplicate, missing event và trạng thái nghiệp vụ không nhất quán.
- [ ] Xác nhận toàn bộ backlog đã trở về mức bình thường.
- [ ] Cập nhật alert, runbook, retry policy hoặc idempotency nếu cần.
- [ ] Ghi nhận bài học và hành động phòng ngừa có người phụ trách.

## Kết luận

Vận hành Spring Kafka tin cậy đòi hỏi phối hợp giữa producer acknowledgement, replication của cluster, quản lý offset, consumer idempotency, retry có giới hạn, DLT có quy trình phục hồi và observability đủ sâu. Hãy thiết kế cho tình huống record được giao lại, dependency tạm thời không khả dụng và consumer bị rebalance; sau đó kiểm thử các tình huống đó trước khi đưa vào production. Khi các cơ chế này được vận hành cùng nhau, hệ thống có thể tiếp tục xử lý phần lớn sự kiện trong điều kiện lỗi và cung cấp đủ bằng chứng để phục hồi phần còn lại một cách có kiểm soát.
