# Lưu metadata lỗi và truy vết bản ghi gốc

Khi một Kafka record bị chuyển vào Dead Letter Topic (DLT/DLQ), đội vận hành cần trả lời được: record đến từ topic nào, partition và offset nào, consumer group nào gặp lỗi, lỗi xảy ra khi nào, đã thử bao nhiêu lần, và record hiện nằm ở đâu. Nếu chỉ lưu một dòng log như “xử lý thất bại”, việc điều tra, đối soát và replay sẽ rất khó.

Metadata lỗi cần đi cùng bản ghi thất bại hoặc được lưu trong một kho tra cứu bền vững. Với Spring Cloud Stream Kafka binder, cơ chế DLQ tích hợp bổ sung các header như `x-original-topic`, `x-exception-message` và `x-exception-stacktrace`. Với Spring Kafka `DeadLetterPublishingRecoverer`, bộ header DLT chuẩn còn có thông tin original partition, offset, timestamp và consumer group. Hai cơ chế có bộ header khác nhau; cần biết ứng dụng đang dùng cơ chế nào để không đọc nhầm hoặc suy diễn thiếu dữ liệu.

Bài học này xây dựng cách lưu metadata lỗi, xác định duy nhất bản ghi gốc, giữ dấu vết qua nhiều lần retry/replay và lập chỉ mục để có thể tìm lại record.

## 1. Vì sao cần metadata lỗi?

Một message có thể thất bại vì payload không đúng schema, quy tắc nghiệp vụ không thỏa mãn hoặc dependency tạm thời không sẵn sàng. Sau khi hết retry, message có thể được publish sang DLT. Nếu DLT chỉ chứa payload, người vận hành vẫn thiếu thông tin để biết message đến từ đâu và vì sao nó bị chuyển đi.

Một hồ sơ lỗi hữu ích cần trả lời:

- **Nguồn gốc:** Kafka cluster, topic, partition, offset, timestamp và key ban đầu.
- **Ngữ cảnh tiêu thụ:** consumer group, binding, application/service và phiên bản triển khai.
- **Nguyên nhân:** exception class, cause, error code, message và stack trace đã được giới hạn.
- **Nhận dạng nghiệp vụ:** event ID, event type, correlation ID, causation ID và trace ID nếu đọc được.
- **Lịch sử xử lý:** số lần thử, thời điểm lỗi đầu/cuối, các topic trung gian và số lần replay.
- **Vị trí hiện tại:** DLT topic, partition, offset và thời điểm publish vào DLT.
- **Trạng thái vận hành:** mới nhận, đang điều tra, chờ sửa, đã replay, đã xử lý hoặc chuyển parking lot.

Không phải trường nào cũng luôn có. Ví dụ, lỗi deserialize có thể xảy ra trước khi payload thành DTO, nên event ID nằm trong JSON không đọc được. Trong trường hợp đó, giữ raw bytes và thông tin vị trí Kafka vẫn cho phép truy vết bản ghi gốc.

## 2. Phân biệt vị trí gốc và vị trí DLT

Kafka offset chỉ có ý nghĩa trong phạm vi một topic-partition. Khi record được publish sang DLT, nó trở thành một record mới và có offset mới tại DLT. Offset DLT không thay thế offset gốc.

~~~text
Topic gốc: orders.created
  cluster = kafka-prod-a
  partition = 2
  offset = 8451
  key = order-1001
  value = {...}
       |
       | consumer group order-projection xử lý lỗi
       v
DLT: orders.created.dlt
  partition = 2          <- có thể trùng partition theo mặc định
  offset = 197            <- offset mới, độc lập với topic gốc
  headers = metadata lỗi + thông tin nguồn
  value = payload gốc
~~~

Cần lưu riêng hai bộ tọa độ:

| Trường | Ý nghĩa |
|---|---|
| `originalCluster` | Định danh cluster chứa record ban đầu |
| `originalTopic` | Topic gốc |
| `originalPartition` | Partition gốc |
| `originalOffset` | Offset gốc |
| `originalTimestamp` | Timestamp của record gốc |
| `dltTopic` | Topic đang giữ record lỗi |
| `dltPartition` | Partition của record trong DLT |
| `dltOffset` | Offset mới của record trong DLT |

Không suy ra `originalOffset` từ `dltOffset`. Cũng không luôn suy ra `originalPartition` từ partition DLT: Kafka binder mặc định gửi sang cùng số partition, nhưng có thể dùng `DlqPartitionFunction` để chọn partition khác. Nếu cần truy vết chính xác, hãy ghi rõ original partition và offset vào metadata.

Một khóa truy vết vật lý thường dùng là:

`cluster + originalTopic + originalPartition + originalOffset`

Khi cùng một record được nhiều consumer group xử lý, thêm `consumerGroup` vào khóa để phân biệt các lần thất bại độc lập. Với truy vết nghiệp vụ, dùng thêm event ID ổn định; event ID không thay thế tọa độ Kafka vì cùng một event có thể được publish lại ở topic/offset khác.

## 3. Header DLQ mặc định của Spring Cloud Stream Kafka binder

Khi bật DLQ trên consumer binding, Kafka binder bổ sung các header mặc định sau vào record lỗi:

| Header Kafka | Kiểu | Ý nghĩa |
|---|---|---|
| `x-original-topic` | `byte[]` | Tên topic gốc |
| `x-exception-message` | `byte[]` | Thông điệp exception |
| `x-exception-stacktrace` | `byte[]` | Stack trace của lỗi |

Đây là bộ header tích hợp của Spring Cloud Stream Kafka binder. Nó không đồng nghĩa với bộ header DLT của Spring Kafka. Theo cấu hình binder mặc định, record lỗi được gửi vào cùng partition number với record gốc; do đó DLT cần đủ partition tương ứng. Nếu ứng dụng dùng partition resolver tùy chỉnh, không thể dựa vào sự trùng partition để khôi phục vị trí gốc.

Cấu hình ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            max-attempts: 3

      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlt
~~~

Các điểm cần nhớ:

- DLQ cần consumer group có tên; anonymous consumer không dùng được cơ chế DLQ này.
- `enable-dlq` bật việc chuyển record lỗi sang DLT sau retry.
- `max-attempts: 3` là tổng số lần xử lý tối đa, gồm lần đầu và hai lần retry.
- `dlq-name` đặt tên topic lỗi; nếu không khai báo, binder dùng tên mặc định `error.<destination>.<group>`.
- Mặc định partition DLT tương ứng partition gốc; hãy bảo đảm DLT có đủ partition.
- Nếu `dlq-partitions` lớn hơn 1, binder yêu cầu bean `DlqPartitionFunction` để chọn partition.
- Khi dùng `destination-is-pattern: true`, binder không hỗ trợ `enable-dlq`.
- Nếu consumer dùng native decoding, cấu hình serializer tương ứng cho DLQ producer trong `dlq-producer-properties`.

Tên property có thể được biểu diễn bằng kebab-case trong YAML hoặc camelCase theo binding metadata của phiên bản. Hãy dùng đúng property names được hỗ trợ bởi BOM và phiên bản Spring Cloud Stream của dự án.

## 4. Bật DLQ và kiểm tra record được chuyển đi

Một consumer minh họa:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService service) {
        return event -> service.process(event);
    }

    public record OrderCreated(
        String eventId,
        String orderId,
        long total
    ) {}
}
~~~

Nếu `OrderService.process` ném exception và retry hết số lần cấu hình, binder có thể chuyển record sang DLT. Khi đọc DLT bằng Kafka console consumer, kiểm tra các header `x-original-topic`, `x-exception-message` và `x-exception-stacktrace`.

Ví dụ lệnh đọc topic DLT:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created.dlt \
  --from-beginning \
  --property print.key=true \
  --property print.headers=true
~~~

Console consumer giúp quan sát nhanh key, payload và header. Với header dạng bytes, công cụ có thể hiển thị nội dung theo dạng text hoặc bytes escaped tùy phiên bản. Để điều tra chính xác, nên dùng consumer nhỏ đọc `ConsumerRecord` và in tên header, giá trị UTF-8 hợp lệ hoặc dạng hex.

## 5. Đọc metadata binder trong Spring Cloud Stream

Header từ Kafka thường được ánh xạ vào Spring `MessageHeaders`. Giá trị header có thể là `byte[]` hoặc kiểu đã được mapper chuyển đổi. Không ép kiểu trực tiếp trước khi kiểm tra.

Ví dụ consumer DLT đọc payload thô và ba header binder:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class DeadLetterInspector {

    @Bean
    Consumer<Message<byte[]>> inspectFailedRecord() {
        return message -> {
            String originalTopic = headerAsText(
                message.getHeaders().get("x-original-topic")
            );

            String exceptionMessage = headerAsText(
                message.getHeaders().get("x-exception-message")
            );

            String stackTrace = headerAsText(
                message.getHeaders().get("x-exception-stacktrace")
            );

            byte[] originalPayload = message.getPayload();

            // Lưu metadata và tham chiếu payload vào kho điều tra.
        };
    }

    private static String headerAsText(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof byte[] bytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        return value.toString();
    }
}
~~~

Ví dụ dùng `Consumer<Message<byte[]>>` để giữ payload ở dạng bytes. Cách này hữu ích khi record gốc không thể deserialize thành DTO. Nếu DLT producer dùng serializer khác hoặc binder đã chuyển payload thành kiểu khác, cần cấu hình deserializer/consumer tương ứng.

Stack trace có thể dài và chứa đường dẫn nội bộ, SQL, URL hoặc dữ liệu nhạy cảm trong exception message. Trước khi lưu hoặc hiển thị cho người dùng, cần giới hạn kích thước và che thông tin nhạy cảm.

## 6. Spring Kafka có bộ header DLT chi tiết hơn

Khi ứng dụng tự cấu hình Spring Kafka `DeadLetterPublishingRecoverer`, record DLT được bổ sung bộ header chuẩn khác. Các hằng số được khai báo trong `KafkaHeaders`:

| Hằng số Spring Kafka | Thông tin được lưu |
|---|---|
| `DLT_EXCEPTION_FQCN` | Tên lớp exception |
| `DLT_EXCEPTION_CAUSE_FQCN` | Tên lớp cause nếu có |
| `DLT_EXCEPTION_MESSAGE` | Thông điệp lỗi |
| `DLT_EXCEPTION_STACKTRACE` | Stack trace |
| `DLT_ORIGINAL_TOPIC` | Topic gốc |
| `DLT_ORIGINAL_PARTITION` | Partition gốc |
| `DLT_ORIGINAL_OFFSET` | Offset gốc |
| `DLT_ORIGINAL_TIMESTAMP` | Timestamp gốc |
| `DLT_ORIGINAL_TIMESTAMP_TYPE` | Loại timestamp gốc |
| `DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group gây lỗi |

Với lỗi deserialize key, Spring Kafka còn có nhóm header riêng `DLT_KEY_EXCEPTION_*`. Các header gốc và header exception được thêm theo semantics của `DeadLetterPublishingRecoverer`.

`DLT_EXCEPTION_CAUSE_FQCN` và `DLT_ORIGINAL_CONSUMER_GROUP` có từ Spring Kafka 2.8. Kiểm tra phiên bản Spring Kafka do BOM của dự án quản lý trước khi tham chiếu các constant này.

Không nhầm tên header Spring Kafka với tên header binder tích hợp:

| Mục tiêu | Spring Cloud Stream Kafka binder DLQ | Spring Kafka DeadLetterPublishingRecoverer |
|---|---|---|
| Topic gốc | `x-original-topic` | `KafkaHeaders.DLT_ORIGINAL_TOPIC` |
| Partition gốc | Không nằm trong bộ header binder mặc định nêu trên | `DLT_ORIGINAL_PARTITION` |
| Offset gốc | Không nằm trong bộ header binder mặc định nêu trên | `DLT_ORIGINAL_OFFSET` |
| Exception message | `x-exception-message` | `DLT_EXCEPTION_MESSAGE` |
| Stack trace | `x-exception-stacktrace` | `DLT_EXCEPTION_STACKTRACE` |
| Consumer group | Không nằm trong bộ header binder mặc định nêu trên | `DLT_ORIGINAL_CONSUMER_GROUP` |

Nếu chỉ dùng binder DLQ tích hợp, không tự giả định đã có original offset trong header. Khi cần tọa độ đầy đủ, có thể thêm metadata bằng cơ chế tùy chỉnh hoặc sử dụng custom error handler/Recoverer của Spring Kafka với sự hiểu biết rõ ràng về ranh giới quản lý retry và acknowledgment.

## 7. Thêm metadata ứng dụng với DeadLetterPublishingRecoverer

Spring Kafka cho phép thêm header tùy chỉnh bằng `setHeadersFunction`. Recoverer vẫn tạo các header DLT chuẩn; function bổ sung thông tin riêng của ứng dụng như mã lỗi, service version hoặc event ID nếu đọc được từ record.

Ví dụ dưới đây dành cho ứng dụng dùng trực tiếp Spring Kafka `DefaultErrorHandler`, không phải cấu hình binder-managed DLQ cùng lúc:

Đặt method trong một lớp cấu hình Spring có `@Configuration`:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(template);

    recoverer.setHeadersFunction((record, exception) -> {
        Headers headers = new RecordHeaders();

        headers.add(new RecordHeader(
            "failure-code",
            classify(exception).getBytes(StandardCharsets.UTF_8)
        ));

        headers.add(new RecordHeader(
            "failed-service",
            "order-projection".getBytes(StandardCharsets.UTF_8)
        ));

        return headers;
    });

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1000L, 2L)
    );
}

private String classify(Exception exception) {
    if (exception instanceof IllegalArgumentException) {
        return "INVALID_EVENT";
    }
    return "PROCESSING_FAILURE";
}
~~~

`setHeadersFunction` nhận record gốc và exception, trả về các Kafka headers bổ sung. Recoverer tự thêm các header DLT chuẩn về original topic, partition, offset, timestamp và consumer group. Nếu muốn loại bỏ hoặc thay đổi header đã copy từ record gốc, cần subclass `DeadLetterPublishingRecoverer` và tùy chỉnh `createProducerRecord`; headers function chỉ có nhiệm vụ thêm.

Không đăng ký đồng thời binder-managed retry/DLQ và một error handler khác cùng xử lý một binding mà không xác định rõ cơ chế nào sở hữu việc retry, publish DLT và commit offset. Hai lớp xử lý có thể cùng publish hoặc xác nhận record ngoài dự kiến.

## 8. Giữ payload gốc khi lỗi deserialize

Lỗi deserialize có thể xảy ra trước khi function nhận được message. Nếu consumer chỉ nhận DTO, code ứng dụng không có cơ hội đọc payload đã lỗi. Để giữ được record gốc, Kafka consumer thường dùng `ErrorHandlingDeserializer` bọc deserializer thực tế.

Ví dụ cấu hình native deserialization:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            use-native-decoding: true

      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlt
              configuration:
                key.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
                spring.deserializer.value.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
~~~

Cấu hình này minh họa `ErrorHandlingDeserializer` bao quanh String deserializer. Hãy chọn delegate đúng với định dạng record gốc và cấu hình serializer tương ứng cho DLQ producer. Nếu native decoding được bật, binder cần biết cách serialize record lỗi khi publish DLT; nếu không, lỗi có thể chuyển thành lỗi publish DLQ.

Ví dụ, nếu DLT producer nhận raw `byte[]`, có thể cần `ByteArraySerializer`; nếu nhận String hoặc DTO đã deserialize, serializer phải khớp kiểu đó. Với luồng có cả payload deserialize thành công và raw bytes từ lỗi deserialize, cần kiểm tra kiểu thực tế hoặc dùng cấu hình nhiều `KafkaTemplate` của Spring Kafka để chọn serializer theo payload type.

Khi dùng `ErrorHandlingDeserializer`, Spring Kafka lưu thông tin exception deserialize trong header nội bộ. `DeadLetterPublishingRecoverer` có thể khôi phục payload bytes gốc để publish vào DLT thay vì chỉ gửi giá trị null đã deserialize thất bại. Trường hợp key và value có deserializer khác nhau có thể cần nhiều KafkaTemplate/serializer phù hợp.

Không chuyển raw bytes thành String theo UTF-8 nếu payload thực tế là Avro, Protobuf, compressed bytes hoặc dữ liệu nhị phân khác. Lưu payload nguyên dạng và ghi serializer/schema version nếu có thể xác định.

## 9. Thiết kế hồ sơ lỗi bền vững trong database

DLT là nơi lưu record lỗi và metadata trong Kafka. Để tìm kiếm theo event ID, trạng thái xử lý, thời gian hoặc đội phụ trách, có thể xây dựng một bảng index đọc từ DLT.

Ví dụ schema:

~~~sql
CREATE TABLE kafka_failure_record (
    failure_id           VARCHAR(80) PRIMARY KEY,
    source_cluster       VARCHAR(120) NOT NULL,
    consumer_group       VARCHAR(200),
    original_topic       VARCHAR(249) NOT NULL,
    original_partition   INTEGER,
    original_offset      BIGINT,
    original_timestamp   TIMESTAMP WITH TIME ZONE,
    original_timestamp_type VARCHAR(40),
    original_key         BYTEA,
    event_id             VARCHAR(200),
    correlation_id       VARCHAR(200),
    event_type           VARCHAR(160),
    dlt_cluster          VARCHAR(120) NOT NULL,
    dlt_topic            VARCHAR(249) NOT NULL,
    dlt_partition        INTEGER NOT NULL,
    dlt_offset           BIGINT NOT NULL,
    exception_type       VARCHAR(500),
    exception_cause_type VARCHAR(500),
    error_code           VARCHAR(120),
    error_message        TEXT,
    stack_trace_excerpt  TEXT,
    failed_at            TIMESTAMP WITH TIME ZONE NOT NULL,
    attempt_count        INTEGER,
    origin_metadata_complete BOOLEAN NOT NULL DEFAULT FALSE,
    status               VARCHAR(40) NOT NULL,
    replay_count         INTEGER NOT NULL DEFAULT 0,
    last_replayed_at     TIMESTAMP WITH TIME ZONE,
    payload_reference    TEXT,
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Khi origin coordinates đầy đủ, có thể tạo unique index theo record gốc và consumer group:

~~~sql
CREATE UNIQUE INDEX uq_kafka_failure_origin
ON kafka_failure_record (
    source_cluster,
    consumer_group,
    original_topic,
    original_partition,
    original_offset
);
~~~

Khóa duy nhất theo tọa độ gốc phản ánh một lần thất bại của consumer logic trên record gốc. Index trên chỉ có ý nghĩa khi các trường origin coordinates đã được cung cấp. Với PostgreSQL, các hàng có giá trị NULL trong khóa unique có thể không xung đột; vì vậy cần thêm unique index theo vị trí DLT để indexer không ghi trùng cùng một record DLT:

~~~sql
CREATE UNIQUE INDEX uq_kafka_failure_dlt_record
ON kafka_failure_record (
    dlt_cluster,
    dlt_topic,
    dlt_partition,
    dlt_offset
);
~~~

`source_cluster` xác định cluster chứa record gốc; `dlt_cluster` xác định cluster chứa bản ghi lỗi. Chúng có thể giống hoặc khác nhau. `original_partition` và `original_offset` cho phép NULL khi cơ chế DLQ đang dùng không cung cấp hai trường đó; `origin_metadata_complete` cho biết có đủ tọa độ để truy nguyên vật lý hay chưa. `consumer_group` có thể được lấy từ header Spring Kafka hoặc cấu hình indexer; nếu không có nguồn đáng tin cậy, để trống thay vì suy diễn từ tên topic.

`original_key` dùng `BYTEA` để giữ key nguyên dạng kể cả khi key serializer không phải UTF-8. Nếu hệ thống chỉ dùng key chuỗi, có thể lưu thêm một cột hiển thị đã giải mã. `attempt_count` chỉ nên điền khi error handler cung cấp số lần thử; bộ header DLQ mặc định của Kafka binder không tự cung cấp trường này.

Nếu cùng record được gửi vào DLT nhiều lần do retry/replay hoặc vận hành thủ công, indexer có thể upsert bản ghi hiện có, tăng `attempt_count` hoặc lưu lịch sử vào bảng con. Nếu cần lưu nhiều lần thất bại riêng biệt, dùng `failure_id` cho từng lần và giữ bảng origin riêng để nhóm chúng.

Không dùng riêng event ID làm unique key của hồ sơ lỗi: một event có thể được publish lại ở offset khác, hoặc cùng một record có thể thất bại ở nhiều consumer group. Tọa độ gốc và consumer group cho biết chính xác lần xử lý nào gặp lỗi.

## 10. Xây dựng indexer đọc DLT và ghi metadata

Indexer là consumer riêng đọc topic DLT. Nó chuyển header và metadata Kafka thành bản ghi tra cứu. Consumer này cần idempotent vì chính nó cũng có thể được giao lại message.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class FailureIndexConsumer {

    @Bean
    Consumer<Message<byte[]>> indexFailure(
            FailureRecordRepository repository,
            @Value("${app.kafka.source-cluster}") String sourceCluster,
            @Value("${app.kafka.dlt-cluster}") String dltCluster,
            @Value("${app.failure.original-consumer-group:}") String configuredGroup) {

        return message -> {
            String originalTopic = text(
                message.getHeaders().get("x-original-topic")
            );
            if (originalTopic == null) {
                originalTopic = text(message.getHeaders()
                    .get(KafkaHeaders.DLT_ORIGINAL_TOPIC));
            }
            String errorMessage = text(
                message.getHeaders().get("x-exception-message")
            );
            if (errorMessage == null) {
                errorMessage = text(message.getHeaders()
                    .get(KafkaHeaders.DLT_EXCEPTION_MESSAGE));
            }
            String stackTrace = text(
                message.getHeaders().get("x-exception-stacktrace")
            );
            if (stackTrace == null) {
                stackTrace = text(message.getHeaders()
                    .get(KafkaHeaders.DLT_EXCEPTION_STACKTRACE));
            }
            String exceptionType = text(message.getHeaders()
                .get(KafkaHeaders.DLT_EXCEPTION_FQCN));
            String exceptionCauseType = text(message.getHeaders()
                .get(KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN));
            String errorCode = text(message.getHeaders().get("failure-code"));
            String eventId = text(message.getHeaders().get("event-id"));
            String correlationId = text(
                message.getHeaders().get("correlation-id")
            );
            String eventType = text(message.getHeaders().get("event-type"));

            String dltTopic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
            Integer dltPartition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
            Long dltOffset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);
            Long dltTimestamp = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TIMESTAMP, Long.class);

            // Các trường DLT_ORIGINAL_* có khi record được tạo bởi
            // Spring Kafka DeadLetterPublishingRecoverer; binder DLQ
            // mặc định không thêm original partition/offset.
            Integer originalPartition = message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_PARTITION, Integer.class);
            Long originalOffset = message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_OFFSET, Long.class);
            Long originalTimestamp = message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_TIMESTAMP, Long.class);
            String originalTimestampType = text(message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE));
            String originalGroup = text(message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP));
            if (originalGroup == null || originalGroup.isBlank()) {
                originalGroup = configuredGroup.isBlank() ? null : configuredGroup;
            }
            byte[] dltKey = keyBytes(
                message.getHeaders().get(KafkaHeaders.RECEIVED_KEY)
            );

            // Với binder mặc định, original partition/offset không nằm
            // trong bộ x-original-topic/x-exception-*.
            // Cần custom DLT headers hoặc recoverer nếu bắt buộc lưu chúng.

            repository.upsertFromDlq(
                sourceCluster,
                dltCluster,
                originalTopic,
                originalPartition,
                originalOffset,
                originalTimestamp,
                originalTimestampType,
                originalGroup,
                eventId,
                correlationId,
                eventType,
                exceptionType,
                exceptionCauseType,
                errorCode,
                errorMessage,
                stackTrace,
                dltTopic,
                dltPartition,
                dltOffset,
                dltTimestamp,
                dltKey,
                message.getPayload()
            );
        };
    }

    private static String text(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof byte[] bytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        return value.toString();
    }

    private static byte[] keyBytes(Object value) {
        if (value instanceof byte[] bytes) {
            return bytes;
        }
        if (value instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8);
        }
        return null; // Với kiểu key khác, dùng serializer/adapter tương ứng.
    }
}
~~~

Đoạn code là khung minh họa; `FailureRecordRepository` cần nhận thêm original coordinates và DLT record metadata nếu đã cấu hình các header tương ứng. Không ghi một hồ sơ “đầy đủ” nếu các trường original partition/offset chưa được cung cấp. Hãy đánh dấu các trường đó là chưa có hoặc bổ sung qua custom recoverer.

`KafkaHeaders.RECEIVED_PARTITION` và `RECEIVED_KEY` có trong các phiên bản Spring Kafka mới; ở phiên bản cũ, tên tương ứng có thể là `RECEIVED_PARTITION_ID` và `RECEIVED_MESSAGE_KEY`. `DLT_ORIGINAL_CONSUMER_GROUP` có từ Spring Kafka 2.8. Kiểm tra BOM đang dùng trước khi chọn constant. Nếu binder mapper trả key dưới dạng kiểu Java khác, hãy dùng serializer/adapter tương ứng thay vì ép kiểu sang bytes tùy tiện.

Indexer nên dùng unique key theo DLT record và upsert. Nếu indexer commit database thành công nhưng chưa commit Kafka offset, nó sẽ nhận lại đúng DLT record; unique index DLT bảo đảm không tạo hồ sơ trùng. Khi có đủ origin coordinates, unique index gốc còn giúp nhóm các lần chuyển lại của cùng record. Nếu cần đảm bảo database index và offset nhất quán, dùng transaction/offset strategy phù hợp và kiểm thử failure window.

## 11. Giữ lịch sử lỗi qua nhiều lần retry và replay

Một record có thể đi qua nhiều topic: topic gốc, retry topic, DLT, parking lot và topic replay. Khi đó cần phân biệt:

- **Origin:** record đầu tiên được tạo ở topic gốc.
- **Current location:** topic/partition/offset hiện tại.
- **Failure history:** các lần xử lý thất bại và exception tương ứng.
- **Replay history:** ai yêu cầu replay, lúc nào, từ đâu và với lý do nào.

Không ghi đè origin bằng topic trung gian mỗi lần replay. Có thể giữ các header riêng:

| Header | Mục đích |
|---|---|
| `x-origin-topic` | Topic đầu tiên |
| `x-origin-partition` | Partition đầu tiên |
| `x-origin-offset` | Offset đầu tiên |
| `x-current-attempt` | Số lần thử hiện tại |
| `x-replay-id` | ID của lần replay |
| `x-replayed-at` | Thời điểm replay |
| `x-replayed-by` | Actor hoặc service khởi chạy replay |
| `x-last-failure-code` | Mã lỗi gần nhất |

Nếu record được chuyển qua nhiều lần, không nên thêm vô hạn cùng một stack trace vào header. Kafka cho phép nhiều header cùng tên, nhưng kích thước record có giới hạn; Spring Kafka cũng lưu ý các header exception lặp có thể làm record phình to và publish thất bại. Giữ lịch sử chi tiết trong database/log/trace, còn header mang origin và trạng thái mới nhất hoặc một replay ID.

Spring Kafka `DeadLetterPublishingRecoverer` hỗ trợ chính sách append original headers và loại bỏ exception headers cũ theo cấu hình. Nếu cần thay đổi header đã copy, override `createProducerRecord`; không chỉ thêm header mới rồi để dữ liệu cũ tăng mãi.

## 12. Truy vết event nghiệp vụ và trace phân tán

Tọa độ Kafka giúp tìm record vật lý. Event ID và trace context giúp tìm hành trình nghiệp vụ qua nhiều service.

~~~text
HTTP request
    |
    v
orders-api
  eventId = evt-9001
  correlationId = corr-9001
  traceparent = 00-...
    |
    v
orders.created (partition 1, offset 400)
    |
    v
inventory-projection
    |
    +---- lỗi khi cập nhật kho
    |
    v
orders.created.dlt (partition 1, offset 88)
    |
    v
failure-indexer
  lưu origin + lỗi + vị trí DLT
~~~

Nên lưu cùng nhau nếu có:

- `eventId`: định danh event nghiệp vụ ổn định.
- `correlationId`: liên kết các event của một quy trình.
- `causationId`: định danh message/command gây ra event.
- `traceparent`: W3C Trace Context.
- `consumerGroup`: nhiệm vụ tiêu thụ đã thất bại.
- `cluster/topic/partition/offset`: vị trí record vật lý.

Không dùng correlation ID làm khóa duy nhất: nhiều event trong một quy trình có thể dùng chung correlation ID. Không dùng trace ID thay event ID. Nếu lỗi deserialize khiến không đọc được payload hoặc header nghiệp vụ, vẫn lưu tọa độ Kafka và DLT metadata để có thể điều tra raw record.

## 13. Replay và parking lot có kiểm soát

Không phải mọi record DLT đều nên gửi lại ngay. Lỗi tạm thời có thể được replay sau khi dependency phục hồi; lỗi schema hoặc dữ liệu vĩnh viễn cần sửa contract/payload trước. Nếu cứ gửi record lỗi về topic gốc mà không giới hạn, nó có thể tạo vòng lặp vô hạn.

Một quy trình vận hành có thể gồm:

1. Indexer ghi nhận DLT record và metadata.
2. Người vận hành phân loại lỗi, kiểm tra origin và payload.
3. Sửa dependency, schema hoặc dữ liệu.
4. Tạo replay request có `replayId`, actor và lý do.
5. Replay đúng payload/key tới topic đích theo chính sách.
6. Giữ nguyên event ID và origin coordinates; tăng replay count.
7. Consumer xử lý idempotent; indexer cập nhật trạng thái.
8. Nếu vượt số lần replay, chuyển parking lot để xử lý thủ công.

Ví dụ header replay:

~~~java
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> replay = MessageBuilder
    .withPayload(originalPayload)
    .setHeader("x-origin-topic", originalTopic)
    .setHeader("x-origin-partition", originalPartition)
    .setHeader("x-origin-offset", originalOffset)
    .setHeader("x-replay-id", replayId)
    .setHeader("x-replay-count", replayCount + 1)
    .setHeader("x-replayed-at", Instant.now().toString())
    .build();
~~~

Đây là metadata minh họa cho ứng dụng replay; cần ánh xạ chúng sang Kafka headers và giữ key gốc khi publish. Không mặc định `StreamBridge.send` thành công có nghĩa broker đã lưu bền vững. Nếu cần xác nhận publish, dùng cơ chế xác nhận producer của binder và ghi trạng thái replay sau khi có kết quả có thể kiểm chứng.

Spring Cloud Stream không tự cung cấp một quy trình xử lý DLT chung cho mọi nghiệp vụ. Ứng dụng cần xây dựng consumer/replay workflow và tránh chạy replay song song với luồng retry chính theo cách làm cạn retry hoặc tạo vòng lặp.

## 14. Bảo mật và giới hạn kích thước metadata

Metadata lỗi thường chứa thông tin nhạy cảm hơn event bình thường. Stack trace có thể lộ package nội bộ, SQL, URL, tên bảng, dữ liệu request hoặc đường dẫn file.

- Không lưu access token, password, cookie hoặc secret trong header.
- Che dữ liệu cá nhân và payload nhạy cảm trước khi log hoặc đưa vào dashboard.
- Giới hạn chiều dài exception message và stack trace.
- Giữ payload raw trong kho có kiểm soát quyền nếu record quá lớn.
- Dùng payload reference/checksum khi cần lưu trữ ngoài Kafka.
- Giới hạn quyền đọc DLT vì nó có thể chứa dữ liệu không hợp lệ hoặc dữ liệu cá nhân.
- Thiết lập retention cho DLT và bảng metadata theo yêu cầu nghiệp vụ.
- Ghi nhận actor và lý do khi replay thủ công.
- Không cho phép endpoint replay công khai hoặc không xác thực.

Nếu stack trace quá dài, có thể lưu stack trace đã cắt trong header và lưu bản đầy đủ trong log tập trung theo correlation/failure ID. Header chỉ cần đủ để tìm hồ sơ lỗi chi tiết.

## 15. Kiểm thử khả năng truy vết

Kiểm thử không chỉ xác nhận record đã xuất hiện trong DLT. Cần xác nhận metadata còn đủ để tìm lại bản ghi gốc.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Function ném exception sau khi deserialize | DLT có payload, key và exception metadata |
| JSON không deserialize được | Raw payload được giữ theo cấu hình deserializer/recoverer |
| Binder DLQ mặc định | Có `x-original-topic`, `x-exception-message`, `x-exception-stacktrace` |
| Spring Kafka recoverer | Có original topic/partition/offset/timestamp/group headers |
| DLT partition khác original partition | Metadata vẫn chỉ đúng partition gốc |
| Cùng record lỗi ở hai consumer group | Hồ sơ lỗi phân biệt theo group |
| Indexer nhận DLT hai lần | Upsert không tạo bản ghi trùng |
| Replay record | Origin không đổi, replay ID/count tăng |
| Stack trace quá dài | Bị giới hạn hoặc chuyển sang kho ngoài |
| Payload nhị phân | Raw bytes không bị chuyển đổi sai encoding |
| Record thiếu event ID | Vẫn truy vết được bằng cluster/topic/partition/offset |

Với Testcontainers Kafka, tạo topic gốc và DLT, gửi một record, làm consumer ném exception và đọc record trong DLT. Kiểm tra key, payload bytes, tên header và giá trị header. Thử một lỗi deserialize riêng để xác nhận ErrorHandlingDeserializer giữ được record gốc.

Kiểm tra thêm failure window: DLT publish thành công nhưng indexer dừng trước khi commit offset. Khi indexer khởi động lại, nó có thể đọc lại record; unique key/upsert phải ngăn metadata trùng.

## 16. Checklist trước khi triển khai production

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| DLT config | Binding nào bật DLQ, group nào sở hữu? |
| DLT partitioning | Có đủ partition không? Có custom resolver/function không? |
| Origin coordinates | Có lưu cluster, topic, partition, offset và timestamp gốc không? |
| Consumer context | Có consumer group, binding và application version không? |
| Error metadata | Có error code, exception class/message và stack trace giới hạn không? |
| Raw payload | Có giữ được bytes khi deserialize thất bại không? |
| Business trace | Có event ID, correlation ID, causation ID và traceparent không? |
| Metadata index | Có unique key và upsert idempotent không? |
| Replay | Có replay ID, actor, reason, attempt limit và parking lot không? |
| Security | DLT, stack trace và payload có quyền truy cập/retention phù hợp không? |
| Observability | Có metric DLT count, oldest age, replay count và failure type không? |
| Version | Đã ghi lại Spring Cloud Stream, Spring Kafka, kafka-clients và broker version chưa? |

## 17. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện bài tập với `orders.created`:

1. Tạo consumer group `order-projection` và bật DLQ cho binding.
2. Gửi một record hợp lệ và một record gây exception.
3. Đọc DLT, xác nhận payload, key và ba header mặc định của Kafka binder.
4. Dùng consumer đọc DLT dưới dạng `Message<byte[]>`, giải mã metadata an toàn.
5. So sánh header binder với bộ header chuẩn của Spring Kafka `DeadLetterPublishingRecoverer`.
6. Thiết kế khóa gốc `cluster + group + topic + partition + offset`.
7. Tạo bảng `kafka_failure_record` và unique index.
8. Viết indexer upsert metadata; gửi lại cùng DLT record để kiểm tra idempotency.
9. Mô phỏng lỗi deserialize và xác nhận raw bytes được giữ.
10. Tạo replay request có replay ID, actor, timestamp và giới hạn lần thử.
11. Chuyển record không thể sửa sang parking lot.
12. Kiểm tra dashboard/metric có thể truy từ failure ID về DLT record và record gốc.

Hoàn thành bài khi có thể xác định chính xác record gốc từ metadata; phân biệt original offset với DLT offset; giải thích khác biệt header của Kafka binder và Spring Kafka recoverer; lưu được hồ sơ lỗi bền vững; và replay có kiểm soát mà không làm mất lịch sử nguồn gốc.

## 18. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Kafka Binder — Retry and Dead Letter Processing](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html) — bật DLQ, header mặc định, partition selection và xử lý record lỗi.
- [Spring Cloud Stream Kafka Binder — Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — `enableDlq`, `dlqName`, `dlqPartitions` và `dlqProducerProperties`.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html) — `DeadLetterPublishingRecoverer`, DLT headers, header function và quản lý header khi replay.
- [Spring Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html) — giữ thông tin lỗi deserialize và phục hồi payload gốc.
- [Apache Kafka — ConsumerRecord API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html) — topic, partition, offset, timestamp, key, value và headers của record.

